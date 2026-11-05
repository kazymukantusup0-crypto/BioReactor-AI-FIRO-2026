"""Read existing artifacts; all ML/economics stay in their original modules."""
import csv
from functools import lru_cache
import json
import os
from pathlib import Path
import urllib.request
from src.data.prepare import ROOT
from src.agent.tools import MODEL_PATHS,get_reactor_status,predict_tool
from src.market.domain import utcnow

FIGURES={
    'stage1_test_errors':'reports/test_errors.png',
    'stage1_5_errors':'reports/stage1_5/errors.png',
    'stage1_5_importance':'reports/stage1_5/comparison_importance.png',
    'stage1_5_distributions':'reports/stage1_5/distributions.png',
    'stage1_5_stability':'reports/stage1_5/stability_support.png',
}
FEATURE_TEXT={
    'substrate':('Материал','Категория из исследования Hafner'),
    'c_vs_sub_m':('VS исследуемого субстрата','г VS / г влажного материала'),
    'c_vs_sub_f':('VS эталонного субстрата','г VS / г влажного эталона; не подставлять значение исследуемого сырья'),
    'c_vs_inoc':('VS инокулята','г VS / г влажного инокулята'),
    'ISR':('Отношение инокулят / субстрат','г VS инокулята / г VS субстрата'),
}


def read_json(path):return json.loads((ROOT/path).read_text(encoding='utf-8'))


def model_schema(model):
    meta=read_json(MODEL_PATHS[model].relative_to(ROOT).with_name('metadata.json'))
    schema=meta['schema'];fields=[]
    for name in schema['features']:
        title,unit=FEATURE_TEXT.get(name,(name,''))
        fields.append({'name':name,'label':title,'unit':unit,'type':'category' if name=='substrate' else 'number',
            'required':True,'categories':schema['categories'] if name=='substrate' else None,
            'bounds':schema.get('bounds',{}).get(name),'role':'prediction' if name in schema.get('prediction_features',schema['features']) else 'domain_diagnostic'})
    return {'model':model,'version':meta['model_version'],'algorithm':meta['selected_model'],
        'fields':fields,'unit':schema['unit'],'limitations':meta['limitations'],
        'context_fields':[
            {'name':'mass_kg','label':'Влажная масса','unit':'кг'},
            {'name':'vs_mass_kg','label':'Измеренная масса VS','unit':'кг VS'},
            {'name':'reactor_volume_l','label':'Объём реактора','unit':'л'},
            {'name':'temperature_c','label':'Температура (контекст)','unit':'°C'},
        ],'context_notice':'Температура и объём реактора не входят в BMP-модель. VS нельзя выводить из влажной массы без измерений.'}


def economics_schema():
    from typing import get_args
    from src.market.scenarios import ScenarioInput
    labels={
        'mass_kg':'Влажная масса, кг','bmp_ml_ch4_g_vs':'Измеренный / обоснованный BMP, мл CH4/г VS','bmp_unit':'Единица BMP',
        'vs_mass_kg':'Измеренная масса VS, кг','potential_methane_m3':'Обоснованный потенциал CH4, м³',
        'gas_volume_basis':'Условия приведения объёма газа','recovery_fraction':'Реальная доля извлечения, 0–1',
        'methane_fraction':'Доля CH4 в сыром биогазе, 0–1','methane_energy_kwh_per_m3':'Энергия метана, кВт·ч/м³ при заданных условиях',
        'electricity_efficiency':'Электрический КПД, 0–1','electricity_demand_kwh':'Собственная потребность, кВт·ч',
        'energy_use_kwh':'Энергопотребление установки, кВт·ч','preparation_cost':'Подготовка сырья',
        'heating_cost':'Нагрев (денежные затраты)','operating_cost':'Эксплуатация и обслуживание','storage_cost':'Хранение при переработке',
        'transport_cost':'Транспорт при переработке','gas_cleaning_cost':'Очистка газа','digestate_handling_cost':'Обращение с дигестатом',
        'sale_storage_cost':'Хранение при продаже сырья','sale_transport_cost':'Транспорт при продаже сырья','upgrading_cost':'Обогащение до биометана',
        'upgrading_recovery_fraction':'Извлечение при обогащении, 0–1','biomethane_purity':'Чистота биометана, 0–1',
        'gas_sale_product':'Продукт для продажи','gas_sale_technical_confirmed':'Продажа газа технически подтверждена',
        'gas_sale_legal_confirmed':'Продажа газа юридически подтверждена','gas_sale_evidence':'Документ / основание продажи газа',
        'digestate_mass_kg':'Масса дигестата, кг','digestate_mode':'Использование дигестата',
        'digestate_quality_confirmed':'Качество дигестата подтверждено','digestate_market_allowed':'Сбыт дигестата допустим',
        'digestate_equivalence_confirmed':'Замещение удобрения подтверждено','digestate_quality_evidence':'Документ о качестве / рынке дигестата',
        'max_price_age_days':'Максимальный возраст цены, дней','allow_stale_prices':'Разрешить устаревшие цены (только условно)',
        'consumer_class':'Профиль потребителя электричества','tax_basis':'Основание НДС'}
    groups={'physical':[],'costs':[],'eligibility':[],'pricing':[]}
    choices={'gas_sale_product':['raw_biogas','biomethane'],'digestate_mode':['sale','use'],'bmp_unit':['mL CH4/g VS']}
    properties=ScenarioInput.model_json_schema()['properties']
    for name,field in ScenarioInput.model_fields.items():
        if name in {'region','currency','feedstock_commodity','price_ids','allow_test_prices'}:continue
        args=get_args(field.annotation)
        kind='boolean' if field.annotation is bool or bool in args else 'number' if field.annotation in {int,float} or float in args or int in args else 'string'
        group='costs' if name.endswith('_cost') else 'eligibility' if name.startswith(('gas_sale_','digestate_','upgrading_','biomethane_')) else 'pricing' if name in {'consumer_class','tax_basis','max_price_age_days','allow_stale_prices'} else 'physical'
        groups[group].append({'name':name,'label':labels.get(name,name),'type':kind,'choices':choices.get(name),
            'constraints':properties[name]})
    return {'groups':groups,'notice':'Все затраты вводятся для одной партии и в одной валюте. Нули допустимы только как явное предположение пользователя. Тариф электричества оценивает собственное потребление, не продажу в сеть.'}


@lru_cache(maxsize=4)
def _load_status(path,mtime):
    import joblib
    try:
        artifact=joblib.load(path)
        if not callable(getattr(artifact.get('pipeline'),'predict',None)):raise ValueError('No estimator')
        return {'available':True,'status':'loaded','version':artifact['metadata']['model_version']}
    except Exception as exc:return {'available':False,'status':'load_failed','error':type(exc).__name__}


def models_status():
    output=[]
    for name,path in MODEL_PATHS.items():
        try:status=_load_status(str(path),path.stat().st_mtime_ns)
        except OSError:status={'available':False,'status':'missing'}
        output.append({'id':name,**status})
    return output


def ollama_status():
    from src.agent.providers import JSONProvider
    expected=JSONProvider('offline').model
    result={'model':expected,'available':False,'service_available':False,'generation_checked':False}
    try:
        # A local service probe, never an internet or credential-bearing request.
        with urllib.request.urlopen('http://127.0.0.1:11434/api/tags',timeout=2) as response:
            data=response.read(1024*1024+1)
        if len(data)>1024*1024:raise ValueError('Ollama response too large')
        names=[m.get('name') for m in json.loads(data).get('models',[])]
        result.update(service_available=True,available=expected in names or expected+':latest' in names,
            status='model_installed' if expected in names or expected+':latest' in names else 'model_not_installed')
    except (OSError,ValueError,TypeError) as exc:result.update(status='unavailable',error=type(exc).__name__)
    return result


def system_status(store):
    try:
        with store.connect() as con:
            con.execute('SELECT 1').fetchone()
            counts=con.execute('SELECT count(*) AS n,sum(is_test) AS test FROM observations').fetchone()
        database={'status':'ok','observations':counts['n'],'test_observations':counts['test'] or 0}
    except Exception as exc:database={'status':'error','error':type(exc).__name__}
    states=store.source_states();prices=store.prices(latest=True)
    return {'checked_at':utcnow().isoformat(),'fastapi':{'status':'ok'},'sqlite':database,
        'ollama':ollama_status(),'models':models_status(),'sensors':get_reactor_status(),
        'market':{'status':'available' if database['status']=='ok' else 'unavailable',
            'last_success_at':max((s['last_success_at'] for s in states if s['last_success_at']),default=None),
            'source_states':states,'validation_counts':{state:sum(p['validation_status']==state for p in prices) for state in ['VERIFIED_CURRENT','VERIFIED_HISTORICAL','STALE','UNVERIFIED','UNAVAILABLE']}},
        'network_mode':'local','internet_connection':'not_probed',
        'online_provider_configured':bool(os.getenv('BIOREACTOR_LLM_MODEL') and (os.getenv('BIOREACTOR_LLM_KEY') or os.getenv('OPENAI_API_KEY'))),
        'actuator_access':False}


def scientific_data():
    audit=read_json('reports/data_audit.json');stage1=read_json('models/metadata.json');research=read_json('models/stage1_5/metadata.json')
    def table(name):
        with (ROOT/name).open(encoding='utf-8-sig',newline='') as file:rows=list(csv.DictReader(file))
        for row in rows:
            for key in ['MAE','RMSE','R2','macro_lab_MAE','n','fold']:
                if key in row:row[key]=float(row[key])
        return rows
    return {'dataset':{'name':'Hafner 2026 interlaboratory BMP','source_url':'https://github.com/AU-BCE-EE/Hafner-2026-IL-BMP',
        'license':'CC BY 4.0','raw_rows':audit['raw_rows'],'excluded_rows':audit['invalid_rows_excluded'],
        'clean_rows':sum(p['rows'] for p in stage1['partitions'].values()),'laboratories':sum(len(p['labs']) for p in stage1['partitions'].values()),
        'substrates':stage1['schema']['categories'],'partitions':stage1['partitions']},
        'stage1':stage1,'stage1_5':research,'nested_cv_comparison':table('reports/stage1_5/nested_cv_comparison.csv'),
        'outer_folds':table('reports/stage1_5/outer_folds.csv'),
        'figures':[{'id':key,'url':f'/api/dashboard/scientific/figures/{key}'} for key in FIGURES],
        'evaluation_notice':'MAE 53.92 — training-only nested GroupKFold, не независимая проверка. MAE 80.38 — ранее просмотренный финальный test одного исследования. Метрики разных схем нельзя сравнивать как один тест.'}


def initialize(store):
    with store.connect() as con:con.executescript('''
        CREATE TABLE IF NOT EXISTS dashboard_sessions(id TEXT PRIMARY KEY,created_at TEXT NOT NULL,mode TEXT NOT NULL,context_json TEXT NOT NULL,history_json TEXT NOT NULL,pending_json TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS dashboard_turns(id INTEGER PRIMARY KEY AUTOINCREMENT,session_id TEXT NOT NULL REFERENCES dashboard_sessions(id),request_id TEXT NOT NULL,created_at TEXT NOT NULL,question TEXT NOT NULL,status TEXT NOT NULL,reply_json TEXT,UNIQUE(session_id,request_id));
        CREATE TABLE IF NOT EXISTS dashboard_predictions(id INTEGER PRIMARY KEY AUTOINCREMENT,created_at TEXT NOT NULL,model TEXT NOT NULL,input_json TEXT NOT NULL,result_json TEXT NOT NULL);
    ''')
    with store.connect() as con:
        fields={r['name'] for r in con.execute('PRAGMA table_info(dashboard_sessions)')}
        for name,kind in [('conversation_version',"TEXT NOT NULL DEFAULT '4'"),('conversation_state_json','TEXT')]:
            if name not in fields:con.execute(f'ALTER TABLE dashboard_sessions ADD COLUMN {name} {kind}')
        turn_fields={r['name'] for r in con.execute('PRAGMA table_info(dashboard_turns)')}
        for name in ['extracted_entities_json','confirmed_parameters_json','pending_question_json','tool_results_json']:
            if name not in turn_fields:con.execute(f'ALTER TABLE dashboard_turns ADD COLUMN {name} TEXT')


def predict(store,body):
    context={**body.context,'model':body.model};result=predict_tool(context)
    result['context_notice']=model_schema(body.model)['context_notice']
    with store.connect() as con:
        identifier=con.execute('INSERT INTO dashboard_predictions(created_at,model,input_json,result_json) VALUES(?,?,?,?)',
            (utcnow().isoformat(),body.model,json.dumps(context),json.dumps(result,ensure_ascii=False,allow_nan=False))).lastrowid
    return {'prediction_id':identifier,**result}


def overview(store):
    with store.connect() as con:
        last=con.execute('SELECT * FROM dashboard_predictions ORDER BY id DESC LIMIT 1').fetchone()
    if last:last={**dict(last),'input_json':json.loads(last['input_json']),'result_json':json.loads(last['result_json'])}
    scenarios=store.scenarios()
    return {'system':system_status(store),'reactor':get_reactor_status(),'sensor_history':[],
        'latest_prediction':last,'latest_economics':scenarios[0] if scenarios else None,
        'market_prices':store.prices(region='KZ-Karaganda',latest=True),'events':store.updates()[:8]}


def demo_data():
    # Existing saved inputs/transcript; not a new model or synthetic market fixture.
    return {'label':'RECORDED DEMO','recorded_at':'2026-10-28',
        'transcript':read_json('reports/stage3_5/actual_agent_dialogue.json'),
        'laboratory_example':read_json('examples/stage1_5_measured.json'),
        'example_notice':'Лабораторный пример из прежнего этапа; не измерения вашей партии. Predict выполнит новый запрос к сохранённой модели.',
        'question':'У меня 5 кг пищевых отходов и реактор объёмом 90 литров. Сколько метана можно получить и выгодно ли его производить?'}
