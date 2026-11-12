"""New, independent acceptance scenarios against the unmodified local Qwen runtime."""
import json, os, pathlib, subprocess, time, urllib.request, uuid
from gpu_gate import GPUWaitTimeout, inference_stop_reasons, wait_for_gpu_idle
ROOT=pathlib.Path(__file__).resolve().parents[2]
BASE=os.getenv('BIOREACTOR_QA_URL','http://127.0.0.1:8781')
CASES=[
 ('onion_peel','job',['У меня 12 кг луковой шелухи и реактор 120 л. Можно ли дать предварительный диапазон метана по научным данным? Отдели литературную оценку от измерения.']),
 ('whey_economics','job',['Молокозавод предлагает забрать 25 кг сыворотки по 40 тенге за кг. Стоит ли вместо этого направить её в биореактор? Посчитай только то, что подтверждается данными, перечисли неизвестные расходы.']),
 ('apple_pomace_profile','job',['Для 10 кг сухого яблочного жмыха какой профиль из каталога научно подходит? Укажи, если это только ближайший аналог, и какие параметры не совпадают.']),
 ('horse_sawdust','job',['Есть 6 кг конского навоза с опилками, но доли компонентов неизвестны. Какой профиль допустимо применить и можно ли честно дать диапазон метана?']),
 ('broiler_litter','job',['9 кг подстилки бройлеров с соломой. Подходит ли профиль помёта кур-несушек, или такое перенесение требует оговорки?']),
 ('sewage_sludge','job',['Для 4 кг осадка городских очистных сооружений проверь научный каталог: есть ли применимый BMP профиль? Не подменяй его навозом.']),
 ('spent_grain','job',['У меня 11 кг пивной дробины. Что можно оценить по найденному профилю, а какие различия между влажной и сухой дробиной мешают точному выводу?']),
 ('beet_vs_straw','job',['Сравни только литературный потенциал метана для 3 кг свекловичного жома и 3 кг пшеничной соломы. Не делай вывод о прибыли без цен и затрат.']),
 ('methane_fraction_missing','job',['Газовый счётчик показал 0,20 м³ метана. Можно ли по этому числу узнать объём всего биогаза?']),
 ('raw_biogas_price','job',['Тариф природного газа в моей таблице — 35 KZT/м³. Можно ли оценить сырое биогазовое топливо по той же цене или нужны очистка, состав и отдельная цена продажи?']),
 ('conditional_bmp_arithmetic','job',['Для условного примера: VS масса 0,6 кг, а BMP я задаю как допущение 250 мл CH₄/г VS. Посчитай арифметический потенциал и не называй BMP измеренным.']),
 ('sunflower_husks','job',['Пять килограммов лузги подсолнечника: проверь точное покрытие научными профилями и скажи, если оценка потребует переноса с другого сырья.']),
 ('sludge_ts_missing_vs','job',['У меня 30 кг обезвоженного осадка, лабораторно измеренный TS равен 18%. VS/TS не измеряли. Какую часть расчёта метана можно выполнить без выдумывания VS?']),
 ('volume_without_density','job',['Загружаю 5 м³ жидкого коровьего навоза в реактор объёмом 6 м³. Достаточно ли этого, чтобы определить массу сырья и BMP?']),
 ('conditional_electricity','job',['Условный инженерный расчёт: 0,10 м³ CH₄, LHV 9,97 кВт·ч/м³, электрический КПД генератора 30%. Сколько электричества получится теоретически? Это не измерение установки.']),
 ('stale_price','job',['Проверь сохранённые цены на электроэнергию для Караганды: есть ли свежая подтверждённая цена, какова дата публикации, возраст и можно ли считать её текущей?']),
 ('digestate_value','legacy',['После переработки останется 80 л дигестата. Можно ли считать его удобрением и приписать ему цену минерального NPK без анализа состава и разрешений?']),
 ('measured_gas_balance','job',['Мои приборы измерили 0,42 м³ сырого биогаза и 58% CH₄ на той же сухой базе. Рассчитай измеренный объём CH₄, укажи, что это баланс измерений, а не BMP.']),
 ('temperature_transfer','job',['Температура содержимого сейчас 37 °C. Есть ли основание поднять её до 40 °C именно в моём процессе, если я не сообщал pH, состав сырья, теплопотери и стабильность?']),
 ('batch_workflow','job',[
  'Начинаем новую партию: 4 кг измельчённой пшеничной соломы, реактор 60 л. Оцени потенциальный метан и сохрани массу как подтверждённый ввод.',
  'Исправление для этой партии: масса не 4, а 4,5 кг. Пересчитай и покажи, какой task/batch обновлён.',
  'А если гипотетически было бы 8 кг? Ответь как сценарий, не заменяя записанную массу 4,5 кг.',
  'Начинаем другую партию: 7 кг молочной сыворотки, сосуд 80 л. Не смешивай её с предыдущей соломой.',
  'Для этой же новой партии я назвал и 7 кг, и 9 кг сыворотки. Не выбирай число за меня: зафиксируй конфликт и уточни массу.'
 ]),
]
NEW_CASES=[
 ('food_waste_vessel_economics','job',['У меня 5 кг пищевых отходов и реактор объёмом 90 литров. Сколько метана можно получить и выгодно ли его производить? Раздели литературную оценку, допущения и измерения; если прибыли определить нельзя, покажи доступную часть расчёта и назови недостающие цены и затраты.']),
 ('batch_transition_alignment','job',[
  'Начинаем партию: 3 кг пшеничной соломы, сосуд 60 л. Пока только сохрани исходные данные.',
  'Начинаем другую партию: 6 кг свиного навоза, бак 100 л. Сохрани отдельно и не меняй предыдущие данные.'
 ]),
 ('binding_reactor_and_feed_mass','job',['В ёмкость реактора 120 л загружаю 3,2 кг пищевых отходов. Дай только обоснованный литературный диапазон метана и объясни, почему объём сосуда не равен массе загрузки.']),
 ('economic_value_partial','job',['За 14 кг сыворотки предлагают 18 тенге за килограмм. Посчитай валовую цену продажи и сравни, что можно установить для биогазового варианта без придумывания затрат.']),
 ('profile_identity_boundary','job',['Есть 2 кг шелухи семян подсолнечника. Проверь прямое совпадение с научными профилями; не подменяй её семенами или жмыхом.']),
 ('negated_economic_routing','job',['\u041d\u0430\u0439\u0434\u0438 \u0432 \u043b\u0438\u0442\u0435\u0440\u0430\u0442\u0443\u0440\u0435 BMP-\u0434\u0438\u0430\u043f\u0430\u0437\u043e\u043d\u044b \u0434\u043b\u044f \u0441\u0432\u0435\u043a\u043b\u043e\u0432\u0438\u0447\u043d\u043e\u0433\u043e \u0436\u043e\u043c\u0430 \u0438 \u043f\u0448\u0435\u043d\u0438\u0447\u043d\u043e\u0439 \u0441\u043e\u043b\u043e\u043c\u044b, \u0441\u0440\u0430\u0432\u043d\u0438 \u043e\u0442\u0434\u0435\u043b\u044c\u043d\u043e \u0434\u043b\u044f \u043f\u0430\u0440\u0442\u0438\u0439 \u043f\u043e 3 \u043a\u0433. \u041d\u0435 \u0440\u0430\u0441\u0441\u0447\u0438\u0442\u044b\u0432\u0430\u0439 \u043f\u0440\u0438\u0431\u044b\u043b\u044c \u0438 \u043d\u0435 \u0437\u0430\u043f\u0440\u0430\u0448\u0438\u0432\u0430\u0439 \u0446\u0435\u043d\u044b: TS \u0438 VS \u044d\u0442\u0438\u0445 \u043f\u0430\u0440\u0442\u0438\u0439 \u043d\u0435 \u0438\u0437\u043c\u0435\u0440\u0435\u043d\u044b.']),
 ('measured_vs_expected_gas','job',['Счётчик измерил 0,30 м³ сырого биогаза, анализ газа показал 62% метана на той же базе. Пересчитай только измеренную долю CH4 и отдели её от BMP.']),
 ('correction_batch_workflow','job',[
  'Новая партия: 2,2 кг влажной пшеничной соломы, реактор 75 л. Сохрани текущие входы и оцени только то, что поддерживает каталог.',
  'Поправка к этой партии: фактическая масса 2,6 кг, а не 2,2. Пересчитай, прежнюю массу замени.',
  'Для сравнения гипотетически возьми 5 кг, не записывая это как новую подтверждённую массу.'
 ]),
]

def http(path,payload=None,timeout=30):
    req=urllib.request.Request(BASE+path,data=json.dumps(payload,ensure_ascii=False).encode('utf-8') if payload is not None else None,headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=timeout) as r:return json.load(r)

def gpu_state():
    try:
        values=subprocess.check_output(['nvidia-smi','--query-gpu=temperature.gpu,utilization.gpu,pstate','--format=csv,noheader,nounits'],timeout=5,text=True).strip().splitlines()[0]
        temp,util,pstate=(part.strip() for part in values.split(','));temp=float(temp);util=float(util)
        details=subprocess.check_output(['nvidia-smi','-q','-d','TEMPERATURE,PERFORMANCE'],timeout=5,text=True)
        import re
        target=re.search(r'^\s*GPU Target Temperature\s*:\s*(\d+)\s*C\s*$',details,re.M)
        thermal=re.search(r'^\s*HW Thermal Slowdown\s*:\s*(Active|Not Active)\s*$',details,re.M)
        return temp,util,pstate,int(target.group(1)) if target else None,(thermal.group(1)=='Active') if thermal else None
    except Exception:return None,None,None,None,None

out=pathlib.Path(os.getenv('BIOREACTOR_QA_RESULTS',pathlib.Path(__file__).with_name('real_qwen_scenarios.json'))).expanduser().resolve()
out.parent.mkdir(parents=True,exist_ok=True)
data=json.loads(out.read_text('utf-8')) if out.exists() else {'model':'qwen3:8b','provider':'offline (loopback Ollama)','cases':[],'scope':'New user scenarios for acceptance only; not held-out model accuracy.'}
try:
    gpu_wait_remaining=max(0.0,min(3600.0,float(os.getenv('BIOREACTOR_QA_GPU_WAIT_SECONDS','300'))))
except ValueError as exc:
    raise SystemExit('BIOREACTOR_QA_GPU_WAIT_SECONDS must be a number from 0 to 3600 seconds.') from exc
data.setdefault('gpu_gate_runs',[])
def qwen_flags(reply):
    meta=reply.get('technical_metadata') or {}
    statuses=reply.get('provider_status') or []
    qwen_configured=any(row.get('model')=='qwen3:8b' for row in statuses if isinstance(row,dict))
    actual_generation=any(row.get('model')=='qwen3:8b' and row.get('actual_generation') is True
                          for row in statuses if isinstance(row,dict))
    metrics=meta.get('provider_generation_metrics') or []
    actual_generation=actual_generation or qwen_configured and any(row.get('status')=='ok' for row in metrics if isinstance(row,dict))
    v9_final=any(row.get('model')=='qwen3:8b' and row.get('phase')=='v9_synthesis'
                 and row.get('actual_generation') is True for row in statuses if isinstance(row,dict))
    actions=meta.get('research_actions') or []
    legacy_final=bool(meta.get('original_model_synthesis')) and qwen_configured and bool(metrics) and metrics[-1].get('status')=='ok'
    final_generation=v9_final or legacy_final
    if v9_final:
        answer_from_qwen=meta.get('final_author') in {'qwen_verified','qwen_grounded_information'}
    else:
        answer_from_qwen=legacy_final and meta.get('autonomous_termination') in {'model_final','synthesis_reserved'} and not meta.get('answer_projection')
    return {'actual_qwen_generation':actual_generation,
            'actual_qwen_final_generation':final_generation,
            'final_answer_from_qwen':answer_from_qwen}

for prior_case in data.get('cases',[]):
    for prior_turn in prior_case.get('turns',[]):
        prior_reply=(prior_turn.get('result') or {}).get('reply') or {}
        prior_turn.update(qwen_flags(prior_reply))
by_name={x['case']:x for x in data['cases']}
selected=os.getenv('BIOREACTOR_QA_CASES')
selected_names={name.strip() for name in selected.split(',') if name.strip()} if selected else None
new_names={case[0] for case in NEW_CASES}
source_cases=CASES+NEW_CASES if os.getenv('BIOREACTOR_QA_INCLUDE_NEW')=='1' or selected_names and selected_names&new_names else CASES
cases=[case for case in source_cases if selected_names is None or case[0] in selected_names]
if selected_names and selected_names-{case[0] for case in source_cases}:raise RuntimeError('Unknown case names: '+', '.join(sorted(selected_names-{case[0] for case in source_cases})))
for name,route,messages in cases:
    row=by_name.get(name)
    if not row:
        session=http('/api/dashboard/chat/sessions',{'mode':'offline','context':{},'conversation_version':'7'})
        row={'case':name,'route':route,'session':session['id'],'turns':[]}
        data['cases'].append(row);by_name[name]=row
        out.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    if row['route']!=route:raise RuntimeError('route mismatch for '+name)
    for index,message in enumerate(messages):
        if index<len(row['turns']):continue
        gate_started=time.monotonic()
        def save_gate_sample(sample):
            event={'case':name,'turn':index,'sample':sample}
            data.setdefault('gpu_gate_events',[]).append(event)
            out.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
            print('GPU_GATE_SAMPLE',json.dumps(event,ensure_ascii=False),flush=True)
        try:
            gate=wait_for_gpu_idle(gpu_state,timeout_seconds=gpu_wait_remaining,
                                   interval_seconds=10,consecutive_samples=3,
                                   on_sample=save_gate_sample)
        except GPUWaitTimeout as exc:
            diagnostics={'case':name,'turn':index,**exc.diagnostics}
            data['gpu_gate_status']=diagnostics
            out.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
            print('GPU_GATE_BLOCKED',json.dumps(diagnostics,ensure_ascii=False),flush=True)
            raise SystemExit(2) from None
        gpu_wait_remaining=max(0.0,gpu_wait_remaining-gate['wait_seconds'])
        gate['case']=name;gate['turn']=index;gate['remaining_wait_budget_seconds']=round(gpu_wait_remaining,3)
        data['gpu_gate_runs'].append(gate)
        data['gpu_gate_status']={'status':'READY','remaining_wait_budget_seconds':round(gpu_wait_remaining,3),
                                 'last_case':name,'last_turn':index,'criteria':gate['criteria']}
        out.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
        temp,util,pstate,target,thermal=gpu_state()
        snap=http('/api/dashboard/chat/sessions/'+row['session'])
        rid=uuid.uuid4().hex;started=time.monotonic()
        if route=='legacy':
            reply=http('/api/dashboard/chat/sessions/'+row['session']+'/messages',{'message':message,'request_id':rid},timeout=210)
            job={'status':'SYNC_RESPONSE','terminal':True,'id':None,'request_id':rid}
            result={'reply':reply,'status':'SYNC_RESPONSE'}
        else:
            job=http('/api/dashboard/chat/sessions/'+row['session']+'/jobs',{'message':message,'request_id':rid,'expected_state_version':snap['state_version']})
            jid=job['id'];deadline=time.monotonic()+220;next_gpu_check=time.monotonic();gpu_interrupt=None
            while not job.get('terminal') and time.monotonic()<deadline:
                if gpu_interrupt is None and time.monotonic()>=next_gpu_check:
                    check_temp,check_util,check_pstate,check_target,check_slowdown=gpu_state()
                    check_sample={'temperature_c':check_temp,'utilization_pct':check_util,
                                  'power_state':check_pstate,'device_target_c':check_target,
                                  'hardware_thermal_slowdown':check_slowdown}
                    stop_reasons=inference_stop_reasons(check_sample)
                    event={'case':name,'turn':index,'observed_at_utc':__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),
                           **check_sample,'stop_reasons':stop_reasons}
                    data.setdefault('gpu_inference_checks',[]).append(event)
                    if stop_reasons:
                        try:
                            cancel=http('/api/dashboard/jobs/'+jid+'/cancel',{},timeout=10)
                            event['cancel_request_status']=cancel.get('status')
                        except Exception as exc:
                            event['cancel_request_error']=type(exc).__name__
                        gpu_interrupt=event
                        data['gpu_gate_status']={'status':'BLOCKED','reason':'inference_thermal_guard_triggered',**event}
                        print('GPU_INFERENCE_BLOCKED',json.dumps(event,ensure_ascii=False),flush=True)
                    else:
                        print('GPU_INFERENCE_SAMPLE',json.dumps(event,ensure_ascii=False),flush=True)
                    out.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
                    next_gpu_check=time.monotonic()+5
                time.sleep(1);job=http('/api/dashboard/jobs/'+jid)
            if not job.get('terminal'):raise RuntimeError('job timeout; artifact preserves previous turns: '+jid)
            result=http(job['result_reference'],timeout=30)
        elapsed=time.monotonic()-started
        snapshot=http('/api/dashboard/chat/sessions/'+row['session'])
        scientific=http('/api/dashboard/chat/sessions/'+row['session']+'/scientific-state')
        actual=result.get('reply') or {}
        qwen=qwen_flags(actual)
        after_temp,after_util,after_pstate,after_target,after_thermal=gpu_state()
        item={'prompt':message,'request_id':rid,'job':job,'result':result,'elapsed_seconds':round(elapsed,2),'gpu_temperature_before_c':temp,'gpu_temperature_target_c':target,'gpu_power_state_before':pstate,'gpu_hardware_thermal_slowdown_before':thermal,'gpu_utilization_before_pct':util,'gpu_temperature_after_c':after_temp,'gpu_temperature_target_after_c':after_target,'gpu_power_state_after':after_pstate,'gpu_hardware_thermal_slowdown_after':after_thermal,'gpu_utilization_after_pct':after_util,'gpu_inference_interrupt':gpu_interrupt if route!='legacy' else None,**qwen,'snapshot':snapshot,'scientific_state':scientific}
        row['turns'].append(item);out.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'case':name,'turn':index,'route':route,'job_status':job.get('status'),'seconds':item['elapsed_seconds'],'actual_qwen':qwen['actual_qwen_generation'],'actual_qwen_final':qwen['actual_qwen_final_generation'],'answer_from_qwen':qwen['final_answer_from_qwen'],'gpu_c_before':temp,'gpu_target_c':target,'gpu_power_state_before':pstate,'gpu_c_after':after_temp,'gpu_power_state_after':after_pstate,'hardware_thermal_slowdown_after':after_thermal,'gpu_util_after':after_util,'state_version':snapshot['state_version']},ensure_ascii=False),flush=True)
        if gpu_interrupt:
            data['gpu_gate_status']={'status':'BLOCKED','reason':'inference_thermal_guard_triggered',**gpu_interrupt}
            out.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
            raise SystemExit(2)
        if after_thermal is True or after_temp is not None and after_target is not None and after_temp>=after_target:
            raise RuntimeError(f'BLOCKED after preserving completed response: device target reached or hardware thermal slowdown active ({after_temp} C, target={after_target} C, slowdown={after_thermal})')
        if not qwen['actual_qwen_generation']: print('WARNING: NOT COUNTED as a successful real-Qwen scenario; inspect provider diagnostics.',flush=True)
    row['complete']=len(row['turns'])==len(messages)
    out.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
print('SUMMARY',json.dumps({'cases':len(data['cases']),'turns':sum(len(c['turns']) for c in data['cases']),'actual_qwen_turns':sum(bool(t.get('actual_qwen_generation')) for c in data['cases'] for t in c['turns']),'actual_qwen_final_turns':sum(bool(t.get('actual_qwen_final_generation')) for c in data['cases'] for t in c['turns']),'qwen_answer_turns':sum(bool(t.get('final_answer_from_qwen')) for c in data['cases'] for t in c['turns']),'complete_cases':sum(bool(c.get('complete')) for c in data['cases'])}),flush=True)




