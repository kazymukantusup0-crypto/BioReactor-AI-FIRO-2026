"""Experimental deterministic-first demo using the existing scientific tools."""
import json
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
CHAT_AUDIT_DIR=Path(__file__).resolve().parents[2]/'reports/guarded_chat_audit'
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict
from typing import Literal
from src.market.domain import utcnow
from src.agent.analytical import explicit_calculations
from src.agent.dialogue_memory import apply
from src.agent.dialogue_types import DialogueState
from src.agent.nlu import extract
from src.agent.verification9 import verify_results, verify_scientific_answer, validate_synthesis
from src.agent.evidence9 import collect
from src.optimizer.capacity import assess_dialogue_state, render_capacity_notice
from src.recommendations.knowledge import search_scientific_sources

CASES={
    'methane':{'title':'A · Потенциал метана','question':'Для 0,6 кг VS при BMP 250 мл CH₄/г VS рассчитай потенциал метана. Гарантирован ли этот выход за 30 дней?',
               'inputs':[{'label':'Масса VS','value':0.6,'unit':'кг VS'},{'label':'BMP','value':250,'unit':'мл CH₄/г VS'}]},
    'incomplete':{'title':'B · Литературная оценка','question':'У меня 142 л коровьего навоза и реактор номинальной вместимостью 200 л. Сколько метана получится за 30 дней?',
                  'inputs':[{'label':'Объём коровьего навоза','value':142,'unit':'л'},{'label':'Номинальная ёмкость реактора','value':200,'unit':'л'}]},
    'oxygen':{'title':'C · Научная консультация','question':'Нужен ли кислород для получения метана в анаэробном биореакторе?', 'inputs':[]},
}
_LOCK=threading.Lock()
_ACTIVE={}


@contextmanager
def guarded_chat(signal):
    """Reuse the bounded 4B QA provider for this experimental app's real Chat.

    The job owns cancellation; this scope owns monitoring and targeted unload.
    Admission failure yields deterministic tools, never the production provider.
    """
    from evaluations import qwen4b_manual_chat as qa
    from src.agent.providers import HybridLLM
    if not _LOCK.acquire(blocking=False):raise HTTPException(409,'Дождитесь завершения текущего эксперимента Qwen.')
    record={'audit_id':uuid.uuid4().hex,'model':qa.MODEL,'status':'admission','provider_calls':[],'samples':[],
            'limits':{'admission_ram_mib':qa.CAL_ADMISSION_RAM_MIB,'runtime_ram_mib':qa.CAL_RAM_FLOOR_MIB,
                      'num_ctx':4096,'num_batch':32,'num_gpu':-1,'parallel_requests':1,'keep_alive':'5m',
                      'max_model_calls':4,'timeout_seconds':120}}
    notification=None;monitor=None;stop=threading.Event();started=time.monotonic()
    try:
        try:
            notification=qa.WindowsLowMemory();before=qa.telemetry.sample(0);record['before']=before
            issues=qa.calibration_issues(before,notification.low(),admission=True)
            if qa.active_ollama_connections():issues.append('other_ollama_client')
        except Exception as exc:issues=['telemetry_error:'+type(exc).__name__]
        if issues:
            record.update(status='blocked',admission_issues=issues)
            yield HybridLLM(providers=[]),record
            return
        provider=qa.LimitedProvider(record['provider_calls'])
        llm=HybridLLM('offline',providers=[provider],strict_model=True)
        llm.bind_cancellation(signal)
        def watch():
            while not stop.wait(.5):
                try:
                    row=qa.telemetry.sample(len(record['samples'])+1)
                    if stop.is_set():return
                    record['samples'].append(row)
                    failures=qa.calibration_issues(row,notification.low())
                    if qa.foreign_ollama_clients():failures.append('other_ollama_client')
                    if time.monotonic()-started>=120:failures.append('experimental_chat_timeout')
                except Exception as exc:failures=['telemetry_error:'+type(exc).__name__]
                if stop.is_set():return
                if failures:
                    record.update(status='stopped',stop_reason=failures);signal.cancel();return
        monitor=threading.Thread(target=watch,name='firo-chat-resource-monitor',daemon=True);monitor.start()
        record['status']='running'
        yield llm,record
        if signal.cancelled:record['status']='cancelled'
        elif record['status']=='running':record['status']='completed' if record['provider_calls'] else 'not_required'
    finally:
        stop.set()
        if monitor:
            monitor.join(timeout=3)
            if monitor.is_alive():
                record.update(status='stopped',stop_reason=['resource_monitor_not_finished']);signal.cancel()
        if record['provider_calls']:
            try:record['unload']=qa.unload_target_if_uncontended()
            except Exception as exc:record['unload']={'status':'ERROR','error':type(exc).__name__}
            try:record['after']=qa.telemetry.sample(999)
            except Exception as exc:record['after_error']=type(exc).__name__
        record['elapsed_seconds']=round(time.monotonic()-started,3)
        try:
            CHAT_AUDIT_DIR.mkdir(parents=True,exist_ok=True)
            audit_path=CHAT_AUDIT_DIR/(record['audit_id']+'.json')
            record['audit_path']=str(audit_path)
            audit_path.write_text(json.dumps(record,ensure_ascii=False,allow_nan=False),encoding='utf8')
        except Exception as exc:record['audit_write_error']=type(exc).__name__
        if notification:
            try:notification.close()
            except Exception as exc:record['notification_close_error']=type(exc).__name__
        _LOCK.release()


def build_result(case):
    """No LLM, no ML loading, no density or literature transfer into batch facts."""
    spec=CASES[case]
    state=apply(DialogueState(),extract(spec['question'],DialogueState()))
    tools={};trace=[];results=[];missing=[];questions=[];capacity=None;estimate=None
    if case=='methane':
        calc=explicit_calculations(state);tools['explicit_calculations']=calc
        row=next(c for c in calc['calculations'] if c['kind']=='methane_potential_m3')
        # Unit identities applied to the existing tool output, not a new BMP model.
        m3=row['value'];litres=m3*1000;ml=m3*1_000_000
        results=[{'label':'Потенциал метана','value':litres,'unit':'л CH₄','provenance':'CALCULATED',
                  'formula':f"600 г VS × 250 мл CH₄/г VS = {ml:g} мл = {litres:g} л = {m3:g} м³ CH₄"}]
        answer=(f'По заданным массе VS и BMP рассчитан потенциал {litres:g} л CH₄. '
                'Это расчёт из введённых данных, а не измеренная выработка реактора. '
                'Выход за 30 дней не установлен: он зависит от кинетики и условий реактора; потенциал не гарантирует выработку к этому сроку.')
        missing=['Кинетика накопления метана и подтверждённые условия конкретного реактора — для прогноза за срок.']
    elif case=='incomplete':
        capacity=assess_dialogue_state(state);tools['reactor_capacity']=capacity
        from src.agent import analytical
        data=analytical.context(state);data['query']=spec['question']
        source=search_scientific_sources(spec['question']);tools['search_scientific_sources']=source
        estimate=analytical.execute('estimate_methane_yield',{'analytical_context':data},{},None)
        tools['estimate_methane_yield']=estimate;tools['assess_substrate_potential']=estimate
        from src.advisor.estimation import span
        usable=next((s for s in estimate['scenarios'] if s['potential_methane_l']),None)
        results=[{'label':'BMP-ориентир всей партии (не выход за 30 дней)','value':span(usable['potential_methane_l']) if usable else None,'unit':'л CH₄','provenance':'LITERATURE_ESTIMATE'},
                 {'label':'Выход за 30 дней','value':None,'unit':'л CH₄','provenance':'UNAVAILABLE'}]
        missing=['Масса сырья или измеренная плотность для перевода литров в массу.',
                 'Масса VS либо TS и VS/TS с указанной основой.',
                 'BMP этого сырья в мл CH₄/г VS и условия его определения.',
                 'Для загрузки: рабочий объём, вода, инокулят и газовое пространство.',
                 'Для выхода за 30 дней: кинетика и условия процесса.']
        questions=['Это навозная жижа без подстилки, свежий плотный навоз или разбавленная смесь?', 'Какой рабочий объём допускается изготовителем реактора?']
        answer=estimate['answer']
    else:
        source=search_scientific_sources(spec['question']);tools['search_scientific_sources']=source
        wanted={'q4b_anaerobic_no_oxygen','q4b_methanogenesis_pathways_claim'}
        claims=[c for c in source['claims'] if c['id'] in wanted]
        if {c['id'] for c in claims}!=wanted:raise ValueError('Reviewed methanogenesis claims unavailable')
        answer=' '.join(c['text']['ru'] for c in claims)
        results=[{'label':'Научный вывод','value':'Свободный кислород не требуется','unit':'','provenance':'LITERATURE'}]
    for name,result in tools.items():trace.append({'tool':name,'status':result.get('status','ok'),'result':result})
    arithmetic=verify_results({k:v for k,v in tools.items() if k!='reactor_capacity'}) if case in {'methane','incomplete'} else {'status':'not_applicable','checked':False}
    scientific=verify_scientific_answer(answer,tools,spec['question'])
    if case=='methane' and (arithmetic['status']!='ok' or scientific['status']!='passed'):raise ValueError('Calculation verification failed')
    if case=='oxygen' and scientific['status']!='passed':raise ValueError('Scientific source verification failed')
    source_data=tools.get('search_scientific_sources',{})
    used={c['source_id'] for c in source_data.get('claims',[]) if c['id'] in {'q4b_anaerobic_no_oxygen','q4b_methanogenesis_pathways_claim'}}
    sources=[{k:s[k] for k in ('title','authors','year','url') if s.get(k)} for s in source_data.get('sources',[]) if s['id'] in used]
    if estimate:sources=[{k:s[k] for k in ('title','authors','year','url') if s.get(k)} for s in estimate['sources']]
    return {'case':case,'title':spec['title'],'question':spec['question'],'inputs':spec['inputs'],
            'input_notice':'Демонстрационные входные данные; это не измерения подключённого реактора.',
            'results':results,'answer':answer,'missing':missing,'questions':questions,'sources':sources,'tools':trace,'estimate':estimate,
            'verification':{'label':'Литературный потенциал; выход за срок не установлен' if case=='incomplete' else 'Арифметика и интерпретация проверены' if case=='methane' else 'Проверено по научным источникам',
                            'arithmetic':arithmetic,'scientific':scientific,'capacity':capacity},
            'explanation':{'status':'not_requested','text':None,'message':'Основной ответ готов без локальной модели.'},
            'state':state.model_dump(mode='json'),'tool_results':tools}


def explain_with_qwen(record, signal):
    """One bounded explanation, using the established QA safety policy/stop path."""
    from evaluations import qwen4b_manual_chat as qa
    from src.agent.providers import JSONProvider, ProviderError
    from src.agent.cancellation import ExecutionStopped
    from src.agent.response_integrity import check_response
    telemetry={'samples':[],'model':'qwen3:4b-q4_K_M','options':{'num_ctx':4096,'num_batch':32,'num_gpu':-1,'parallel_requests':1,'max_calls':1,'num_predict':400,'timeout_seconds':45}};notification=None;started=False;stop=threading.Event();monitor=None
    try:
        notification=qa.WindowsLowMemory()
        before=qa.telemetry.sample(0);telemetry['before']=before
        issues=qa.calibration_issues(before,notification.low(),admission=True)
        if qa.active_ollama_connections():issues.append('other_ollama_client')
        if issues:
            telemetry['admission_issues']=issues
            if 'ram_limit' in issues:
                message=f"Для пояснения Qwen недостаточно свободной RAM: {before['free_ram_mib']:.1f} MiB, требуется {qa.CAL_ADMISSION_RAM_MIB} MiB. Основной ответ готов без модели."
            elif 'other_ollama_client' in issues or 'model_already_loaded' in issues:
                message='Ollama занята другим запросом или моделью. Основной ответ готов без неё.'
            else:message='Пояснение Qwen сейчас недоступно: проверка ресурсов не пройдена. Основной ответ готов без модели.'
            return {'status':'blocked','text':None,'message':message,'telemetry':telemetry}
        def watch():
            while not stop.wait(.5):
                try:
                    row=qa.telemetry.sample(len(telemetry['samples'])+1);telemetry['samples'].append(row)
                    failures=qa.calibration_issues(row,notification.low())
                    if qa.foreign_ollama_clients():failures.append('other_ollama_client')
                    if failures:telemetry['stop_reason']=failures;signal.cancel();return
                except Exception as exc:
                    telemetry['stop_reason']=['telemetry_error:'+type(exc).__name__];signal.cancel();return
        monitor=threading.Thread(target=watch,daemon=True);monitor.start()
        class DemoProvider(JSONProvider):
            def payload(self,messages,schema=None):
                body=super().payload(messages,schema);body['keep_alive']='5m';body['options'].update(num_ctx=4096,num_batch=32,num_gpu=-1)
                return body
        provider=DemoProvider('offline',model=qa.MODEL);provider.num_ctx=4096;provider.timeout=45
        provider.output_token_budget=400;provider.capture_public_output=True;provider.cancellation_signal=signal
        schema={'type':'object','properties':{'explanation':{'type':'string','maxLength':600}},'required':['explanation'],'additionalProperties':False}
        public={'question':record['question'],'verified_answer':record['answer'],'verified_results':record['results'],'missing':record['missing'],'sources':record['sources']}
        messages=[{'role':'system','content':qa.CONTEXT+' Explain the supplied verified result in Russian, at most 60 words. Do not calculate, introduce quantities or parameters, repeat the full answer, cite internal IDs or claim safety. Use only verified_answer and supplied facts. Acknowledge unknown inputs. Different methanogens use different pathways; no universal substrate claim. Return schema JSON.'},
                  {'role':'user','content':json.dumps(public,ensure_ascii=False)}]
        signal.throw_if_cancelled();started=True;t=time.monotonic()
        try:draft=provider.generate(messages,schema)
        finally:
            telemetry['provider_metrics']=provider.metrics;telemetry['request']=public;telemetry['elapsed_seconds']=round(time.monotonic()-t,3)
        text=draft.get('explanation','');telemetry['raw_draft']=draft
        candidate={'conclusion':text,'explanation':'','limitations':[],'next_question':None,'evidence_ids':[],'decision':'not_applicable'}
        evidence,_=collect(record['tool_results'])
        if record['case'] in {'methane','incomplete'}:candidate['evidence_ids']=list(evidence)[:5]
        state=DialogueState.model_validate(record['state']);audit=[]
        issues=validate_synthesis(candidate,evidence,record['tool_results'],state,query=record['question'],quantity_audit=audit)
        issues+=check_response(candidate,finish_reason=provider.metrics[-1].get('done_reason'),limits={'conclusion':600})
        # Core facts remain displayed from Python; check the model's statements
        # against the same evidence without demanding that it repeat the core.
        scientific=verify_scientific_answer(record['answer']+' '+text,record['tool_results'],record['question'])
        issues+=scientific.get('contradictions',[])
        telemetry['validation']={'issues':list(dict.fromkeys(issues)),'numeric_claims':audit,'scientific':scientific}
        if issues:return {'status':'rejected','text':None,'message':'Пояснение модели не прошло проверку. Основной ответ из проверенных данных доступен выше.','telemetry':telemetry}
        signal.throw_if_cancelled()
        return {'status':'accepted','text':text,'message':'Пояснение Qwen3 4B проверено по доступным данным.','telemetry':telemetry}
    except ExecutionStopped:
        return {'status':'cancelled','text':None,'message':'Пояснение остановлено. Проверенные результаты сохранены.','telemetry':telemetry}
    except Exception as exc:
        telemetry['error']=type(exc).__name__+': '+str(exc)[:300]
        return {'status':'unavailable','text':None,'message':'Локальная модель недоступна. Проверенные результаты готовы без неё.','telemetry':telemetry}
    finally:
        stop.set()
        if monitor:monitor.join(timeout=3)
        if started:
            telemetry['unload']=qa.unload_target_if_uncontended()
            try:telemetry['after']=qa.telemetry.sample(999)
            except Exception as exc:telemetry['after_error']=type(exc).__name__
        if notification:notification.close()


def create_router(store, enabled=False):
    router=APIRouter(prefix='/api/dashboard/firo-demo',tags=['Experimental FIRO Demo'])
    if enabled:
        with store.connect() as con:con.execute('CREATE TABLE IF NOT EXISTS firo_demo_runs(id TEXT PRIMARY KEY,created_at TEXT NOT NULL,payload_json TEXT NOT NULL)')
    def require():
        if not enabled:raise HTTPException(409,'Запустите экспериментальный Dashboard с --firo-demo.')
    def read(identifier):
        with store.connect() as con:row=con.execute('SELECT payload_json FROM firo_demo_runs WHERE id=?',(identifier,)).fetchone()
        if row is None:raise HTTPException(404,'Demo run not found')
        return json.loads(row['payload_json'])
    def save(record):
        with store.connect() as con:con.execute('INSERT OR REPLACE INTO firo_demo_runs VALUES(?,?,?)',(record['id'],record['created_at'],json.dumps(record,ensure_ascii=False)))
    def public(record):return {k:v for k,v in record.items() if k not in {'state','tool_results'}}
    class RunInput(BaseModel):
        model_config=ConfigDict(extra='forbid')
        case:Literal['methane','incomplete','oxygen']
    @router.get('/scenarios')
    def scenarios():return {'enabled':enabled,'model':'qwen3:4b-q4_K_M','scenarios':[{'id':key,**value} for key,value in CASES.items()]}
    @router.post('/runs',status_code=201)
    def run(body:RunInput):
        require();record=build_result(body.case);record.update(id=uuid.uuid4().hex,created_at=utcnow().isoformat());save(record);return public(record)
    @router.get('/runs/{identifier}')
    def get(identifier:str):
        require();record=read(identifier)
        if record['explanation']['status']=='generating' and identifier not in _ACTIVE:
            record['explanation']={'status':'interrupted','text':None,'message':'Пояснение прервано перезапуском. Проверенные результаты сохранены.'};save(record)
        return public(record)
    @router.post('/runs/{identifier}/cancel')
    def cancel(identifier:str):
        require();record=read(identifier)
        signal=_ACTIVE.get(identifier)
        if signal:signal.cancel()
        if record['explanation']['status']=='generating':
            record['explanation']={'status':'cancelled','text':None,'message':'Отмена запрошена; основной результат сохранён.'};save(record)
        return public(record)
    @router.post('/runs/{identifier}/explain')
    def explain(identifier:str):
        require();record=read(identifier)
        if not _LOCK.acquire(blocking=False):raise HTTPException(409,'Дождитесь завершения текущего пояснения.')
        lease=None
        from src.agent.cancellation import CancellationSignal
        signal=CancellationSignal()
        try:
            lease=store.acquire('agent-execution-global',ttl=120)
            if lease is None:raise HTTPException(409,'Дождитесь завершения текущей работы агента.')
            _ACTIVE[identifier]=signal
            record['explanation']={'status':'generating','text':None,'message':'Qwen объясняет проверенный результат…'};save(record)
            explanation=explain_with_qwen(record,signal)
            with store.connect() as con:
                con.execute('BEGIN IMMEDIATE')
                latest=json.loads(con.execute('SELECT payload_json FROM firo_demo_runs WHERE id=?',(identifier,)).fetchone()['payload_json'])
                if latest['explanation']['status']=='cancelled' or signal.cancelled:
                    explanation.update(status='cancelled',text=None,message='Пояснение остановлено; основной результат сохранён.')
                latest['explanation']=explanation
                con.execute('UPDATE firo_demo_runs SET payload_json=? WHERE id=?',(json.dumps(latest,ensure_ascii=False),identifier))
            return public(latest)
        finally:
            _ACTIVE.pop(identifier,None)
            if lease:store.release('agent-execution-global',lease)
            _LOCK.release()
    return router
