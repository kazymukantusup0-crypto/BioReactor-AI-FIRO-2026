"""Intent-aware scientific tools around the preserved ToolRegistry."""
from src.agent.tools import ToolRegistry,get_model_info
from src.recommendations.retrieval import retrieve,topics_for
from src.recommendations.knowledge import search_scientific_sources


def topics(state,text):
    found=topics_for(text)
    if 'temperature_recommendation' in state.intents and 'temperature' not in found:found.append('temperature')
    if not found and 'process_guidance' in state.intents:found=['process']
    return found or ['temperature']


class DialogueTools:
    def __init__(self,base,state,text):self.base=base;self.state=state;self.text=text;self.market_store=base.market_store

    def execute(self,name,context,results,query):
        material=self.state.value('material');lang=self.state.language
        if name=='search_scientific_sources':
            return search_scientific_sources(query,material=material,topics=topics(self.state,query))
        if name=='recommend_conditions':
            found=results.get('search_scientific_sources') or retrieve(query,material=material,topics=topics(self.state,query))
            claims=found.get('claims',[])
            return {'status':'ok' if claims else 'insufficient_evidence','kind':'literature_guidance','material':material,
                'claims':claims,'sources':found.get('sources',[]),'actuator_access':False,
                'message':' '.join(c['text'][lang] for c in claims[:3]) if claims else {'ru':'В проверенной базе нет подходящего режима для этого сырья.','en':'The verified catalogue has no applicable operating regime for this material.','kk':'Тексерілген қорда бұл шикізатқа сәйкес режим жоқ.'}[lang]}
        if name=='analyze_substrate' and material in {'manure','swine_manure','poultry_manure'}:
            found=retrieve(query,material=material,topics=['process','temperature'])
            return {'status':'ok','material':material,'category':'manure','model_applicable':False,
                'dry_matter_fraction':None,'vs_fraction':None,'sources':found['sources'],'subtype_required':material=='manure',
                'message':{'ru':'Навоз распознан. Виды навоза различаются; Hafner BMP-модель для них не обучена. Можно использовать только применимые литературные сведения.','en':'Manure is recognized. Its types differ; the Hafner BMP model was not trained for them. Applicable literature guidance remains available.','kk':'Көң танылды. Оның түрлері әртүрлі; Hafner BMP моделі оларға үйретілмеген. Сәйкес әдеби нұсқаулықты қолдануға болады.'}[lang]}
        if name=='get_market_prices' and 'economic_comparison' in self.state.intents:
            context=dict(context);context.pop('market_commodity',None)
        return self.base.execute(name,context,results,query)


def initial_plan(state,context,text):
    intents=set(state.intents);names=[];material=state.value('material')
    if material or intents & {'temperature_recommendation','methane_yield','process_guidance','economic_comparison'}:names.append('analyze_substrate')
    if intents & {'temperature_recommendation','process_guidance','sources'}:names.append('search_scientific_sources')
    if material!='chernozem' and intents & {'temperature_recommendation','process_guidance'}:names.append('recommend_conditions')
    if 'methane_yield' in intents and material and context.get('bmp_ml_ch4_g_vs') is None:
        names.append('predict_bmp')
    if 'model_info' in intents:names.append('get_model_info')
    if 'reactor_status' in intents:names.append('get_reactor_status')
    if intents & {'economic_comparison','market_prices'}:names.append('get_market_prices')
    if 'price_history' in intents:names.append('get_price_history')
    return list(dict.fromkeys(names))


def methane_ready(context,results):
    measured=context.get('bmp_ml_ch4_g_vs') is not None and context.get('bmp_unit')=='mL CH4/g VS' and bool(context.get('gas_volume_basis'))
    estimated=results.get('predict_bmp',{}).get('status')=='ok'
    return context.get('vs_mass_kg') is not None and (measured or estimated)


def market_compare_ready(store,context,results):
    from src.market.domain import COMMODITIES
    from src.market.scenarios import ScenarioInput,select_price,BASE_COSTS,PriceUnavailable
    data=dict(context.get('market_scenario',{}))
    for key in ['region','currency','consumer_class','tax_basis','mass_kg','potential_methane_m3','gas_volume_basis','bmp_ml_ch4_g_vs','bmp_unit','vs_mass_kg','recovery_fraction',*BASE_COSTS,
        'energy_use_kwh','methane_energy_kwh_per_m3','electricity_efficiency','electricity_demand_kwh','gas_cleaning_cost','sale_storage_cost','sale_transport_cost']:
        if context.get(key) is not None:data.setdefault(key,context[key])
    if context.get('market_region'):data.setdefault('region',context['market_region'])
    if context.get('material') in COMMODITIES:data.setdefault('feedstock_commodity',context['material'])
    try:
        request=ScenarioInput.model_validate(data)
        def eligible(role):
            try:select_price(store,request,role);return True
            except PriceUnavailable:return False
        if all(data.get(k) is not None for k in ['mass_kg','sale_storage_cost','sale_transport_cost']):
            if eligible('feedstock'):return True
        potential=data.get('potential_methane_m3') is not None or context.get('bmp_ml_ch4_g_vs') is not None and context.get('vs_mass_kg') is not None or results.get('predict_bmp',{}).get('status')=='ok' and context.get('vs_mass_kg') is not None
        common=BASE_COSTS+['energy_use_kwh','recovery_fraction','gas_volume_basis']
        if potential and all(data.get(k) is not None for k in common):
            if data['energy_use_kwh'] and not eligible('electricity'):return False
            needed=['methane_energy_kwh_per_m3','electricity_efficiency','electricity_demand_kwh','gas_cleaning_cost']
            if all(data.get(k) is not None for k in needed) and eligible('electricity'):return True
            if request.gas_sale_technical_confirmed is True and request.gas_sale_legal_confirmed is True and request.gas_sale_evidence and request.gas_cleaning_cost is not None:
                gas_ready=request.methane_fraction is not None if request.gas_sale_product=='raw_biogas' else all(getattr(request,k) is not None for k in ['upgrading_cost','upgrading_recovery_fraction','biomethane_purity'])
                if gas_ready and eligible('gas_sale'):return True
            if request.digestate_quality_confirmed is True and request.digestate_market_allowed is True and request.digestate_quality_evidence and request.digestate_mass_kg is not None:
                if (request.digestate_mode=='sale' or request.digestate_equivalence_confirmed is True) and eligible('digestate'):return True
    except (ValueError,PriceUnavailable):pass
    return False
