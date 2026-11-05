"""Verified, bounded read-only and calculation tools; no arbitrary code or paths."""
import json
import re
from src.data.prepare import ROOT, FEATURES
from src.economics.calculator import calculate_methane, calculate_profitability
from src.recommendations.knowledge import load_knowledge, normalize_material, source_records, search_scientific_sources

MODEL_PATHS={'stage1':ROOT/'models/bmp.joblib','stage1_5':ROOT/'models/stage1_5/bmp.joblib'}
TOOL_NAMES=['analyze_substrate','predict_bmp','calculate_methane','recommend_conditions',
    'calculate_profitability','calculate_vs_concentration','get_model_info','get_reactor_status','search_scientific_sources',
    'get_market_prices','get_price_history','compare_market_scenarios','explain_market_recommendation']
from src.agent.process_bridge import PROCESS_TOOLS
TOOL_NAMES += PROCESS_TOOLS
from src.agent.research_bridge import RESEARCH_TOOLS
TOOL_NAMES += RESEARCH_TOOLS
from src.agent.advisor_tools import ADVISOR_TOOLS
TOOL_NAMES += ADVISOR_TOOLS
from src.advisor.focused import TOOLS as FOCUSED_TOOLS
TOOL_NAMES += FOCUSED_TOOLS
from src.advisor.advanced_science import TOOLS as ADVANCED_TOOLS
TOOL_NAMES += ADVANCED_TOOLS
from src.agent import analytical
TOOL_NAMES += analytical.TOOLS
from src.agent.scientific_tools import TOOLS as SCIENTIFIC_TOOLS
TOOL_NAMES += SCIENTIFIC_TOOLS


def get_model_info(model='stage1_5'):
    if model not in MODEL_PATHS:
        raise ValueError('Unknown model')
    path=MODEL_PATHS[model].with_name('metadata.json')
    meta=json.loads(path.read_text(encoding='utf-8'))
    research=model=='stage1_5'
    score=meta['nested_cv'] if research else meta['test']
    metric=score.get('macro_lab_MAE',score['MAE'])
    return {'status':'ok','artifact':model,'algorithm':meta['selected_model'],'version':meta['model_version'],
        'features':meta['schema']['features'],'supported_substrates':meta['schema']['categories'],
        'accuracy':score,'evaluation':'training-only nested CV; not independent study validation' if research else 'stage1 held-out laboratories; one study',
        'limitations':meta['limitations'],'message':f"Модель {model}: {meta['selected_model']}; {'nested CV macro laboratory MAE' if research else 'test MAE'} {metric:.4g} мл CH₄/г VS. Проверки на независимых исследованиях нет; результат этапа 1.5 не доказывает улучшение на них."}


def analyze_substrate(data):
    material=data.get('material')
    if not material:
        return {'status':'needs_input','missing':['material'],'message':'Укажите точное сырьё; по объёму нельзя определить материал или BMP.'}
    material=normalize_material(material)
    record=load_knowledge()['materials'].get(material)
    supported=material in get_model_info(data.get('model','stage1_5'))['supported_substrates']
    if record is None:
        return {'status':'unsupported','material':material,'model_applicable':False,'sources':[],
            'message':'Материал или смесь не представлены в проверенной базе и обучении. Численный BMP не подтверждён; нужны идентификация, состав и лабораторное испытание.'}
    return {'status':'ok','material':material,**record,'model_applicable':supported,
        'sources':source_records(record['sources']),
        'message':f"Сырьё: {record['name_ru']}. {record['limitations']} "+('Категория есть в обучении; применимость конкретной партии ещё не подтверждена.' if supported else 'Численный прогноз Hafner для этого материала отклоняется.')}


def predict_tool(data):
    analysis=analyze_substrate(data)
    if not analysis.get('model_applicable'):
        return {'status':'needs_input' if not data.get('material') else 'unsupported','missing':analysis.get('missing',[]),
            'message':analysis['message'],'model_called':False}
    required=[f for f in FEATURES if f!='substrate']
    missing=[f for f in required if data.get(f) is None]
    if missing:
        return {'status':'needs_input','missing':missing,'model_called':False,
            'message':'Для научного BMP укажите измеренные '+', '.join(missing)+'. VS — г/г влажного материала; ISR — отношение масс VS. Эталонную VS нельзя назначать произвольно.'}
    payload={f:data[f] for f in required}
    payload['substrate']=analysis['material']
    try:
        from src.inference.predict import predict_bmp
        import joblib
        # Same preserved detector guards both stages, including legacy stage1.
        domain=joblib.load(MODEL_PATHS['stage1_5'])['domain_detector'].assess(payload)
        if domain['out_of_distribution']:
            return {'status':'out_of_distribution','domain':domain,'model_called':False,
                'message':'Комбинация характеристик вне подтверждённой области того же субстрата. Агент отказывается от численного BMP; проверьте эталонную VS и лабораторную сопоставимость.'}
        result=predict_bmp(payload,MODEL_PATHS[data.get('model','stage1_5')])
    except Exception as exc:
        # Persisted estimator libraries expose version-specific exceptions; this
        # boundary must return an explicit failure rather than an invented BMP.
        return {'status':'error','code':'model_unavailable_or_invalid_input','model_called':False,
            'error_type':type(exc).__name__,'message':'Не удалось безопасно загрузить модель или проверить входы. Численный прогноз не выдан; проверьте артефакт, зависимости и диапазоны.'}
    return {'status':'ok',**result,'domain':domain,'model_called':True,
        'message':f"Лабораторный BMP: {result['bmp']:.6g} мл CH₄/г VS ({result['model']}). Это потенциал, не фактический выход газа. 90% интервал не установлен; перенос на вашу установку не подтверждён."}


def recommend_conditions(data):
    analysis=analyze_substrate(data)
    if analysis['status']!='ok' or analysis.get('category')=='soil':
        return {'status':'insufficient_evidence','sources':analysis.get('sources',[]),
            'message':'Для этого сырья проверенных режимов в базе нет. Температура, pH, HRT и загрузка не назначаются.'}
    kb=load_knowledge()
    conditions=analysis.get('conditions')
    sources=analysis['sources']
    message='Справочные сведения, не ML-прогноз и не команда установке. '
    if analysis['material']=='food_waste':
        message+='EBMUD: pH 7–7,5 для подготовленной пищевой пульпы в описанных опытах. Это не проверенный режим вашей партии.'
    elif analysis['material']=='cattle_manure':
        message+='FAO: около 35 °C для мезофильного режима. Пример KVIC на навозе КРС: HRT 30–40 дней при окружающей температуре 20–40 °C, подача 10% TS. Это пример для указанной конструкции, не норма для batch или вашего реактора.'
    else:
        message+='Частных режимов для этого эталонного материала в базе нет. Общий ориентир FAO — мезофильный режим около 35 °C; для назначения нужны параметры установки и технолог.'
        sources+=source_records(['fao_environment'])
    return {'status':'ok','kind':'literature_guidance','material':analysis['material'],'conditions':conditions,
        'general':kb['general'],'sources':sources,'missing':['reactor_design','operating_mode','measured_TS_VS','inoculum','process_monitoring'],
        'message':message}


def get_reactor_status():
    return {'status':'ok','mode':'mock','connected':False,'readings':None,'measured_at':None,'actuator_access':False,
        'message':'Mock-режим: датчики не подключены, показаний нет. Агент не управляет нагревателем, насосом или клапанами.'}


class ToolRegistry:
    def __init__(self,market_store=None,observer=None):
        self.market_store=market_store
        self.observer=observer

    def manifest(self,names=None):
        from src.agent.tool_manifest import manifest
        return manifest(names)

    def execute(self,name,context,results,query):
        if self.observer:self.observer('tool_start',{'tool':name})
        result=self._execute(name,context,results,query)
        if self.observer:self.observer('tool_result',{'tool':name,'status':result.get('status'),'result':result})
        return result

    def _execute(self,name,context,results,query):
        if name not in TOOL_NAMES:
            return {'status':'error','code':'tool_not_allowed','message':'Инструмент не разрешён.'}
        try:
            if name in SCIENTIFIC_TOOLS:
                from src.agent.scientific_tools import execute
                return execute(name,context,results,query,self.market_store)
            if name in analytical.TOOLS:
                from src.market.service import get_store
                return analytical.execute(name,context,results,self.market_store or get_store())
            if name in ADVANCED_TOOLS:
                from src.advisor.advanced_science import run
                result=run(name,context,self.market_store);json.dumps(result,allow_nan=False);return result
            if name in FOCUSED_TOOLS:
                from src.advisor.focused import run
                result=run(name,context);json.dumps(result,allow_nan=False);return result
            if name in ADVISOR_TOOLS:
                from src.agent.advisor_tools import execute_tool
                from src.market.service import get_store
                result=execute_tool(name,context,self.market_store or get_store())
                json.dumps(result,allow_nan=False)
                return result
            if name in RESEARCH_TOOLS:
                from src.agent.research_bridge import execute_tool
                from src.market.service import get_store
                result=execute_tool(name,context,self.market_store or get_store())
                json.dumps(result,allow_nan=False)
                return result
            if name in PROCESS_TOOLS:
                from src.agent.process_bridge import execute_tool
                from src.market.service import get_store
                result=execute_tool(name,context,self.market_store or get_store())
                json.dumps(result,allow_nan=False)
                return result
            if name=='calculate_vs_concentration':
                from src.agent.dilution import calculate_vs_concentration
                result=calculate_vs_concentration(context)
                json.dumps(result,allow_nan=False)
                return result
            from src.agent.context import validate_context
            context=validate_context(context)
            if name in {'get_market_prices','get_price_history','compare_market_scenarios','explain_market_recommendation'}:
                from src.market import service
                function=getattr(service,name)
                lookup_context=dict(context)
                if name=='get_market_prices' and (re.search('выгод|прода|прибыл|эконом|profit',query,re.I) or (query.lstrip().startswith('{') and 'market_scenario' in context)):
                    lookup_context.pop('market_commodity',None)
                result=function(lookup_context,store=self.market_store) if name in {'get_market_prices','get_price_history'} else function(context,results,store=self.market_store)
            elif name=='analyze_substrate': result=analyze_substrate(context)
            elif name=='predict_bmp': result=predict_tool(context)
            elif name=='recommend_conditions': result=recommend_conditions(context)
            elif name=='get_model_info': result=get_model_info(context.get('model','stage1_5'))
            elif name=='get_reactor_status': result=get_reactor_status()
            elif name=='search_scientific_sources': result=search_scientific_sources(query)
            else:
                data=dict(context)
                if 'mass_kg' not in data and 'material_volume_l' in data and 'density_kg_l' in data:
                    data['mass_kg']=data['material_volume_l']*data['density_kg_l']
                prediction=results.get('predict_bmp',{})
                if prediction.get('status')=='ok' and 'bmp_ml_ch4_g_vs' not in data:
                    data.update(bmp_ml_ch4_g_vs=prediction['bmp'],bmp_unit='mL CH4/g VS',
                        gas_volume_basis='source BMP reference conditions; normalization not independently verified')
                if name=='calculate_methane': result=calculate_methane(data)
                else:
                    methane=results.get('calculate_methane',{})
                    if methane.get('status')=='ok' and 'potential_methane_m3' not in data:
                        data['potential_methane_m3']=methane['potential_methane_m3']
                        data['gas_volume_basis']=methane['gas_volume_basis']
                    result=calculate_profitability(data)
            json.dumps(result,allow_nan=False)
            if result.get('status') not in {'ok','error','needs_input','unsupported','out_of_distribution','insufficient_evidence'}:
                raise ValueError('Invalid tool status')
            return result
        except (ValueError,TypeError,OSError,ImportError,KeyError) as exc:
            return {'status':'error','code':'invalid_input_or_resource','message':str(exc)}
