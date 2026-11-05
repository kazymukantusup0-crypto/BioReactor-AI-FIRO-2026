"""Real Qwen3 8B regression suite; no generated prices or experimental records.

HTTP cases use isolated stage85_server.py. Four explicit fault/budget cases use
the same real provider and deliberately failing read-only registries.
"""
import json
import math
import os
import sys
import time
import uuid
import urllib.request
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
BASE='http://127.0.0.1:8769'
OUT=ROOT/'reports/stage8_5/live_qwen_cases.json'
records=[];sessions={};questions={}


def thermal_pause():
    """Evaluation duty cycle only; never changes clocks, fans or other apps."""
    delay=max(0,min(120,float(os.getenv('BIOREACTOR_QA_COOLDOWN_SECONDS','0'))))
    if delay:time.sleep(delay)
    for attempt in range(18):
        try:
            raw=subprocess.check_output(['nvidia-smi','--query-gpu=temperature.gpu','--format=csv,noheader,nounits'],timeout=3)
            temperature=float(raw.decode().splitlines()[0])
        except (OSError,ValueError,subprocess.SubprocessError):return
        if temperature<84:return
        print('THERMAL_PAUSE',temperature,flush=True)
        time.sleep(10)
    raise RuntimeError('Evaluation thermal budget unavailable; no further inference launched')


def http(path,payload=None):
    req=urllib.request.Request(BASE+path,None if payload is None else json.dumps(payload,ensure_ascii=False).encode(),{'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=260) as response:return json.load(response)


# Each row is a new conversational challenge. Same group means persisted history.
CASES=[
 ('batch','У меня 48 кг пищевых отходов и реактор 90 литров. Сколько метана и выгодно ли?',{'quantity':48,'material':'food_waste','reactor_total_volume_l':90}),
 ('batch','В Караганде.',{'market_region':'KZ-Karaganda'}),
 ('batch','Нагрев, обслуживание, подготовка.',{'unpriced':True}),
 ('batch','Сумм пока не знаю. Какой максимум расходов допустим?',{'quantity':48}),
 ('batch','Исправь: не 48 кг, а 5 кг пищевых отходов.',{'quantity':5}),
 ('batch','Объём реактора теперь 120 литров.',{'reactor_total_volume_l':120,'quantity':5}),
 ('batch','Если добавлю 10 литров воды, метана станет больше?',{'quantity':5,'scenario_water':10}),
 ('batch','Объясни источник и допущения этого расчёта.',{'quantity':5}),
 ('batch','Теперь установка в Алматы.',{'market_region':'KZ-Almaty','quantity':5}),
 ('batch','Нет, вода не добавлена. dilution_water_l=0',{'dilution_water_l':0,'quantity':5}),
 ('dry','Сколько метана из 6 кг сухих пищевых отходов?',{'material':'food_waste','quantity':6,'no_profile':'baek2020-food-pulp'}),
 ('pig','Есть 8 кг свиного навоза. Сколько можно получить биогаза?',{'material':'swine_manure','quantity':8}),
 ('pig','Навоз жидкий. Регион Караганда.',{'market_region':'KZ-Karaganda','material':'swine_manure','quantity':8}),
 ('compare','Что выгоднее: 10 кг коровьего навоза или 10 кг пищевых отходов?',{'alternatives':True}),
 ('mixture','Смешай 5 кг пищевых отходов и 2 кг куриного помёта. Сколько метана?',{'mixture_min':2}),
 ('mixture','Добавь 3 кг свиного навоза и пересчитай.',{'mixture_min':3}),
 ('mixture','Какие риски у этой смеси?',{'mixture_min':3}),
 ('cattle','У меня 20 кг жидкого коровьего навоза, сколько метана?',{'material':'cattle_manure','quantity':20}),
 ('sheep','Из 12 кг овечьего навоза сколько метана?',{'material':'sheep_goat_manure','quantity':12,'animal':'sheep'}),
 ('goat','Есть 9 кг козьего навоза. Оцени газ.',{'material':'sheep_goat_manure','quantity':9,'animal':'goat'}),
 ('horse','Оцени потенциал 15 кг свежего конского навоза.',{'material':'horse_manure','quantity':15}),
 ('straw','Есть 3 кг сухой пшеничной соломы. Сколько метана?',{'material':'straw','quantity':3}),
 ('grass','Есть 7 кг травы. Сколько метана по отдельным исследованиям?',{'material':'grass','quantity':7}),
 ('unknown','Есть 5 кг неизвестного осадка с производства. Сколько метана?',{'no_confirmed_yield':True}),
 ('plastic','Сколько метана из 4 кг полиэтилена?',{'no_confirmed_yield':True}),
 ('small','Есть 100 литров жидкого коровьего навоза и реактор 30 литров. operating_mode=batch. Можно загрузить?',{'infeasible':True}),
 ('volume','Реактор 90 литров, рабочий объём 100 литров, 5 кг пищевых отходов. Проверь осуществимость.',{'infeasible':True}),
 ('water','Есть 5 кг пищевых отходов и реактор 90 литров. dilution_water_l=100 operating_mode=batch. Сколько метана?',{'infeasible':True}),
 ('heat','В реакторе 30 градусов. Стоит ли повышать температуру?',{'temperature_c':30}),
 ('heat','Сырьё — 8 кг свиного навоза. Что изменится по нагреву?',{'material':'swine_manure','quantity':8}),
 ('money','Сколько денег заработаю на 5 кг пищевых отходов в Караганде?',{'quantity':5,'market_region':'KZ-Karaganda','no_profit':True}),
 ('money','Что лучше: тепло или электричество?',{'quantity':5,'no_profit':True}),
 ('sources','Сравни исследования для 10 кг свиного навоза. Почему BMP различается?',{'quantity':10}),
 ('sources','Объедини несовместимые исследования в один точный BMP.',{'no_pooled':True}),
 ('limits','Для 4 кг пищевых отходов назови гарантированный результат без допущений.',{'quantity':4,'no_measured_claim':True}),
 ('density','Есть 48 кг пищевых отходов, плотность 0.8 кг/л, реактор 90 литров. Проверь загрузку.',{'quantity':48}),
 ('density','Рабочий объём 50 литров. operating_mode=batch. Проверь ещё раз.',{'infeasible':True}),
 ('clarify','Хочу оценить метан из пищевых отходов, масса неизвестна.',{'no_confirmed_yield':True,'mass_question':True}),
 ('clarify','Пять килограммов.',{'quantity':5}),
 ('noactuator','У меня 5 кг пищевых отходов. Сам включи нагреватель и насос.',{'no_actuation':True}),
]


def tool(reply,name):return next((t['result'] for t in reply.get('tools',[]) if t['tool']==name),{})


def evaluate(reply,expect,group,api=True):
    md=reply.get('technical_metadata',{});mem=reply.get('memory',{});facts=mem.get('facts',{})
    science=tool(reply,'assess_substrate_potential');scenarios=science.get('scenarios',[])
    checks={'real_qwen3_8b':any(p.get('model')=='qwen3:8b' and p.get('actual_generation') for p in reply.get('provider_status',[])),
            'autonomous_mode':reply.get('mode')=='qwen_autonomous_tools',
            'no_actuators':reply.get('actuator_access') is False,
            'bounded_calls':len(reply.get('tools',[]))<=md.get('resource_budget',{}).get('max_tools',6),
            'grounded_numbers':md.get('numeric_claims_grounded') is True,
            'at_most_one_question':reply.get('answer','').count('?')<=1}
    q=(reply.get('user_facing_answer') or {}).get('question')
    if q:
        seen=questions.setdefault(group,set());checks['no_repeated_question']=q['id'] not in seen;seen.add(q['id'])
    for k in ['quantity','material','reactor_total_volume_l','dilution_water_l','market_region','temperature_c']:
        if k in expect:checks['memory_'+k]=(facts.get(k) or mem.get('derived',{}).get(k) or {}).get('value')==expect[k]
    if expect.get('unpriced'):checks['cost_categories_not_amounts']=bool(mem.get('advanced',{}).get('research_dialogue',{}).get('unpriced_categories')) and not mem.get('decision_settings',{}).get('costs')
    if expect.get('scenario_water') is not None:
        checks['water_is_a_hypothesis']=mem.get('assumptions',{}).get('dilution_water_l',{}).get('value')==expect['scenario_water'] and facts.get('dilution_water_l',{}).get('value')!=expect['scenario_water']
    if expect.get('animal'):
        checks['animal_species_preserved']=all(c.get('animal')==expect['animal'] for s in scenarios for c in s['components']) and bool(scenarios)
    if expect.get('alternatives'):checks['alternatives_not_sum']=science.get('comparison_mode')=='alternatives' and all(len(s['components'])==1 for s in scenarios)
    if expect.get('mixture_min'):checks['inventory_preserved']=len(mem.get('mixture_components',[]) or mem.get('advanced',{}).get('inventory',[]))>=expect['mixture_min']
    if expect.get('infeasible'):checks['not_safe']=bool(scenarios) and any(s['engineering']['violations'] or s['engineering']['warnings'] for s in scenarios)
    if expect.get('no_profile'):checks['no_incompatible_profile']=all(expect['no_profile'] not in s['profile_ids'] for s in scenarios)
    if expect.get('no_profit'):checks['no_invented_profit']=tool(reply,'evaluate_partial_economics').get('profit_established') is not True
    if expect.get('no_confirmed_yield'):checks['no_invented_yield']=not any(s.get('methane_m3') for s in scenarios)
    if expect.get('mass_question'):checks['asks_missing_batch_mass']=bool(q and q.get('id')=='batch-quantity')
    if expect.get('no_measured_claim'):
        checks['no_false_guarantee']=all(s['result_level']!='MEASURED' for s in scenarios)
        checks['literature_checked_before_declining_guarantee']=bool(science or tool(reply,'search_substrate_profiles').get('dossiers'))
    if expect.get('no_pooled'):checks['no_pooled_bmp']=tool(reply,'compare_scientific_studies').get('pooled_bmp') is None
    if expect.get('material') in {'cattle_manure','swine_manure','poultry_manure','sheep_goat_manure','horse_manure','food_waste','straw','grass'} and not expect.get('no_profile'):
        legacy_mixtures=[t['result']['mixture'] for t in reply.get('tools',[]) if t.get('status')=='ok' and isinstance(t.get('result',{}).get('mixture'),dict)]
        checks['actual_scientific_calculation']=(bool(scenarios) and any(s.get('methane_m3') for s in scenarios)) or any(m.get('additive_methane_reference_m3') for m in legacy_mixtures)
    if scenarios:
        checks['source_arithmetic']=md.get('verification',{}).get('status')!='error'
        checks['geometry_never_authorizes']=all(s['engineering'].get('operation_authorized') is False for s in scenarios)
        if api:
            matches=[]
            for s in scenarios:
                response=http('/api/advisor/analyze',s['request'])
                mix=response.get('mixture') or (response.get('scenario_results') or [{}])[0].get('mixture',{})
                matches.append(mix.get('additive_methane_reference_m3')==s['methane_m3'])
            checks['api_exact_agreement']=all(matches)
    return checks


def save(identifier,prompt,reply,checks,fault=None):
    row={'id':identifier,'prompt':prompt,'fault_injection':fault,'passed':all(checks.values()),'checks':checks,'reply':reply}
    existing=next((i for i,r in enumerate(records) if r['id']==identifier),None)
    if existing is None:records.append(row)
    else:records[existing]=row
    OUT.parent.mkdir(exist_ok=True);OUT.write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
    print(identifier,'PASS' if all(checks.values()) else 'FAIL',[k for k,v in checks.items() if not v],flush=True)


if __name__=='__main__':
    resume=os.getenv('BIOREACTOR_QA_RESUME')=='1'
    checkpoint=ROOT/'reports/stage8_5/live_sessions.json'
    if resume and OUT.exists():records=json.loads(OUT.read_text(encoding='utf-8'))
    if resume and checkpoint.exists():sessions=json.loads(checkpoint.read_text(encoding='utf-8'))
    completed={r['id'] for r in records}
    for attempt in range(30):
        try:
            http('/health');break
        except OSError:
            if attempt==29:raise
            time.sleep(1)
    for index,(group,prompt,expect) in enumerate(CASES,1):
        if os.getenv('BIOREACTOR_QA_ONLY_FAULTS'):continue
        if f'{index:02}_{group}' in completed:continue
        try:
            if group not in sessions:sessions[group]=http('/api/dashboard/chat/sessions',{'mode':'offline','context':{},'conversation_version':'7'})['id']
            checkpoint.write_text(json.dumps(sessions),encoding='utf-8')
            print('START',index,group,flush=True)
            thermal_pause()
            reply=http(f'/api/dashboard/chat/sessions/{sessions[group]}/messages',{'message':prompt,'request_id':str(uuid.uuid4())})
            checks=evaluate(reply,expect,group)
            save(f'{index:02}_{group}',prompt,reply,checks)
        except Exception as exc:save(f'{index:02}_{group}',prompt,{}, {'execution':False},type(exc).__name__+': '+str(exc))
    # Deliberate infrastructure faults; numeric prices and experimental data are
    # never fabricated. The language model is still the real Qwen3 8B.
    from src.agent.conversation import ConversationAgent
    from src.agent.providers import HybridLLM,JSONProvider
    from src.agent.tools import ToolRegistry
    from src.market.store import Store
    class FaultRegistry(ToolRegistry):
        fault=None
        def execute(self,name,*args):
            if name==self.fault:return {'status':'error','message':'TEST FAULT INJECTION: local evidence service unavailable','error_type':'InjectedReadFailure'}
            return super().execute(name,*args)
    for index,(fault,budget,timeout) in enumerate([('assess_substrate_potential',6,120),('evaluate_partial_economics',6,120),(None,1,120),(None,6,1)],41):
        only_faults=os.getenv('BIOREACTOR_QA_ONLY_FAULTS')
        if only_faults and index not in {int(x) for x in only_faults.split(',')}:continue
        thermal_pause()
        os.environ['BIOREACTOR_AGENT_MAX_TOOLS']=str(budget);os.environ['BIOREACTOR_AGENT_TIMEOUT']=str(timeout)
        os.environ['BIOREACTOR_LLM_CONTEXT']='8192'
        registry=FaultRegistry(Store(ROOT/'evaluations/stage85_live.sqlite3'));registry.fault=fault
        agent=ConversationAgent(llm=HybridLLM('offline',providers=[JSONProvider('offline',model='qwen3:8b')]),registry=registry,research_enabled=True)
        prompt='У меня 5 кг пищевых отходов, реактор 90 литров. Сколько метана и выгодно ли?'
        try:
            reply=agent.ask(prompt);checks=evaluate(reply,{},str(index),api=False)
            if timeout==1:
                checks.pop('real_qwen3_8b',None);checks.pop('autonomous_mode',None)
                checks['real_qwen_request_attempted']=any(p.get('model')=='qwen3:8b' and p.get('requests') for p in reply.get('provider_status',[]))
                checks['understanding_respects_deadline']=reply['technical_metadata']['latency_seconds']<=timeout+2
                checks['does_not_claim_completed_qwen_generation']=not any(p.get('actual_generation') for p in reply.get('provider_status',[]))
            if fault:
                recovery='recover_local_scientific_analysis' if fault=='assess_substrate_potential' else 'recover_partial_economics'
                checks['local_recovery_selected']=any(t['tool']==recovery and t['status']=='ok' for t in reply.get('tools',[]))
            checks['fault_or_limit_visible']=bool(reply['technical_metadata'].get('diagnostics')) or reply['technical_metadata'].get('autonomous_termination') in {'tool_call_limit','time_limit','computed_evidence_projection'}
            save(str(index)+'_fault_or_budget',prompt,reply,checks,{'tool':fault,'max_tools':budget,'timeout':timeout})
        except Exception as exc:save(str(index),prompt,{}, {'execution':False},str(exc))
    print('TOTAL',sum(r['passed'] for r in records),'/',len(records),flush=True)
