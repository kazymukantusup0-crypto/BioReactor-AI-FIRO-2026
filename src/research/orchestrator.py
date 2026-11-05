"""Research results remain separate from confirmed batch facts and ML predictions."""
from src.research.evidence_store import EvidenceStore
from src.research import scientific_search,market_search
from src.research.evidence_extractor import catalog
from src.estimation.schemas import EstimateRequest
from src.estimation.methane_potential import estimate
from src.estimation.scenario_ranges import scale
from src.market.domain import utcnow

def research_and_estimate(store,request,fetcher=None):
    request=request if isinstance(request,EstimateRequest) else EstimateRequest.model_validate(request)
    evidence=EvidenceStore(store)
    scientific=scientific_search.search(evidence,request.material,request.online,fetcher)
    market=market_search.search(evidence,request.material,request.region,request.online,fetcher)
    calculation=estimate(request,scientific['reviewed_profiles'],catalog()['energy_reference'])
    calculation.update(market=market,scientific_search=scientific,region=request.region,region_confirmed=request.region_confirmed,
                       catalog_reference_value_kzt=None,calculated_at=utcnow().isoformat(),version='7',model_used=False)
    if not request.region_confirmed:calculation['assumptions'].append('KZ-Karaganda is a dashboard default region, not user-confirmed')
    if market['offers'] and calculation['wet_mass_kg']:
        offer=market['offers'][0]
        calculation['catalog_reference_value_kzt']=scale(calculation['wet_mass_kg'],offer['normalized_value'])
        calculation['warnings'].append('Catalog reference value is not a purchase bid, sale income, current confirmed price, or profit; material form and small-batch terms unverified.')
    calculation['missing']+=['comparable_raw_biogas_purchase_quote_and_technical_legal_sale_conditions','energy_conversion_efficiency_and_operating_storage_transport_digestate_costs']
    calculation['economic_comparison']={'A_sell_feedstock':{'net_profit':None,'reason':'No confirmed buyer bid and transaction costs'},
        'B_energy':{'fuel_energy_kwh':calculation['fuel_energy_kwh'],'net_profit':None,'reason':'No actual recovery, conversion efficiency, avoided tariff eligibility and costs'},
        'C_sell_gas':{'net_profit':None,'reason':'No comparable raw biogas quote and sale feasibility'},
        'D_digestate':{'net_profit':None,'reason':'No quality test, product quantity, eligible buyer quote and handling costs'},
        'ranking':None,'double_counting_policy':'Gas sale and energy use are alternative allocations, never added for the same gas; digestate revenue requires an eligible separate product.'}
    from src.research.economic_analysis import compare_explicit
    calculation['user_economic_scenario']=compare_explicit(calculation,request.economic_inputs)
    from src.economics.complete_analysis import analyze
    calculation['decision_analysis']=analyze(store,request,calculation)
    identifier=evidence.append('research_run',{'request':request.model_dump(mode='json'),'result':calculation})
    return {**calculation,'research_run_id':identifier}
