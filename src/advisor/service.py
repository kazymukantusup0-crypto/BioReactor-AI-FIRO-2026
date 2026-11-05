"""Compose substrate evidence, conditions and the preserved v7.5 energy/economics."""
from src.advisor.schemas import AdvisorRequest
from src.advisor import catalog,mixing,temperature,duration
from src.research.evidence_store import EvidenceStore
from src.research.advisor_pipeline import discover
from src.economics.complete_analysis import analyze as analyze_economics
from src.estimation.schemas import EstimateRequest
from src.market.domain import utcnow

def analyze(store,data,persist=True):
    request=data if isinstance(data,AdvisorRequest) else AdvisorRequest.model_validate(data)
    if not request.allow_conditional_profiles:
        return analyze_exact(store,request,persist)
    from src.advisor.evidence_engine import scientific_request
    science=scientific_request(request,store=store)
    cases=[]
    for scenario in science['scenarios']:
        case=analyze_exact(store,scenario['request'],persist=False)
        case['scenario_id']=scenario['id']
        case['scenario_assumptions']=scenario['assumptions']
        case['result_level']=scenario['result_level']
        cases.append(case)
    result=dict(cases[0])
    result.update(original_request=request.model_dump(mode='json'),scenario_results=cases,local_experiments=science['local_experiments'],
        scenario_count=len(cases),candidate_count=science['candidate_count'],scenarios_truncated=science['truncated'])
    if persist:result['advisor_run_id']=EvidenceStore(store).append('advisor_run',{'request':request.model_dump(mode='json'),'result':result})
    return result


def analyze_exact(store,data,persist=True):
    request=data if isinstance(data,AdvisorRequest) else AdvisorRequest.model_validate(data)
    original_request=request.model_dump(mode='json');scenario_notes=[]
    if any(c.data_mode=='ILLUSTRATIVE_ASSUMPTION' for c in request.components):
        from src.advisor.advanced_science import prepared
        request,scenario_notes=prepared(request,allow_illustrative=False)
        if request.decision.methane_fraction is None and request.decision.use_reference_scenarios:
            from src.economics.decision_schemas import Range
            request.decision.methane_fraction=Range(low=.60,high=.60,provenance='HYPOTHETICAL_SCENARIO',evidence='Explicit illustrative Dashboard mode: methane share 60%; not measured')
            scenario_notes.append({'component':'gas_composition','assumption':'Selected illustrative methane fraction 60%, not a matched composition measurement'})
    for c in request.components:c.material=catalog.normalized(c.material)
    mix=mixing.evaluate(request)
    mass=mix['total_wet_mass_kg'];volume=mix['sum_separate_volumes_l'];basis=mix['gas_basis']
    single=len(request.components)==1;material=request.components[0].material if single else 'mixture'
    proxy=EstimateRequest(material=material,material_state=request.components[0].material_state if single and request.components[0].material_state in {'unknown','slurry','fresh_solid','bedded','dry','compost'} else 'unknown',
        mass_kg=mass['low'] if mass and mass['low']==mass['high'] else None,volume_l=volume['high'] if volume else None,reactor_total_volume_l=request.reactor_total_volume_l,
        region=request.region,region_confirmed=request.region_confirmed,decision=request.decision)
    scientific_sources=list({r['source']['id']:r['source'] for r in mix['components'] if r['source']}.values())
    density_ids={row.get('properties_used',{}).get('density_kg_l',{}).get('source_id') for row in mix['components']}
    scientific_sources+=[s for s in catalog.document()['sources'] if s['id'] in density_ids and s['id'] not in {s['id'] for s in scientific_sources}]
    summary={'status':'ok' if mix['complete_methane_reference'] else 'needs_input','result_level':mix['result_level'],'wet_mass_kg':mass,'vs_mass_kg':mix['total_vs_kg'],
        'methane_potential_m3':mix['additive_methane_reference_m3'],'methane_potential_l':mixing.scale(mix['additive_methane_reference_m3'],1000) if mix['additive_methane_reference_m3'] else None,
        'structured_gas_basis':basis,'gas_reference':'component study gas reference; consult structured_gas_basis' if basis else None,
        'catalog_reference_value_kzt':None,'sources':scientific_sources,'assumptions':[],'warnings':mix['limitations']}
    # The old single cattle research request still supplies its real reference ask.
    if single and material=='cattle_manure' and request.components[0].material_state in {'unknown','slurry'}:
        from src.research.market_search import search
        from src.estimation.scenario_ranges import scale
        market=search(EvidenceStore(store),material,request.region,request.online)
        if market['offers'] and mass:summary['catalog_reference_value_kzt']=scale(mass,market['offers'][0]['normalized_value'])
        summary['market']=market
    from src.advisor.engineering import evaluate as engineering_evaluate
    summary['engineering']=engineering_evaluate(request,mix)
    economics=analyze_economics(store,proxy,summary)
    geometry=economics['feasibility'];thermal=temperature.recommend(request,mix,geometry);timing=duration.recommend(request,mix)
    materials={c.material for c in request.components}
    interactions=[r for r in catalog.document()['interaction_records'] if materials&set(r['materials'])]
    cited={r['source_id'] for r in thermal['studies']+timing['studies']+interactions}
    scientific_sources=list({s['id']:s for s in scientific_sources+[s for s in catalog.document()['sources'] if s['id'] in cited]}.values())
    stability={'validated_for_this_mixture':False if not single else None,'measured_mixture_ph':request.measured_ph,
        'inhibition_warning':request.inhibition_warning,'risks':list(dict.fromkeys(risk for c in request.components for d in catalog.DEFINITIONS if d[0]==c.material for risk in d[-1])),
        'relevant_studies':interactions,'synergy_multiplier_applied':False,'mixture_cn_ratio':mix['cn_mass_ratio'],
        'required_measurements':['pH and buffer capacity','volatile fatty acids','ammonia where relevant','actual loading and mixing','inoculum suitability'],
        'notice':'No numerical stability score or additive pH/CN average is invented.'}
    from src.agent.tools import get_reactor_status
    monitor=get_reactor_status()
    observation={'connected':monitor.get('connected',False),'mode':monitor.get('mode'),'readings':monitor.get('readings'),
                 'measurements_used':False,'actuator_access':False,'notice':'Mock/offline readings are never filled in or treated as measurements. Explicit user observations remain separate.'}
    evidence=EvidenceStore(store);research=discover(evidence,sorted(materials),['BMP','co_digestion','temperature','retention','stability'],request.online)
    result={'version':'8.1','status':summary['status'],'calculated_at':utcnow().isoformat(),'request':request.model_dump(mode='json'),'mixture':mix,'temperature':thermal,'duration':timing,'stability':stability,
            'decision_analysis':economics,'reactor_monitoring':observation,'scientific_search':research,'sources':scientific_sources,
            'recommendation':{'preferred_mixture':None,'scope':'Single substrate reference' if single else 'Additive reference only; no validated interaction model or physical operating approval'},
            'actuator_access':False,'scientific_counts':{'approved_profile_count':len(catalog.profiles()),'materials_with_approved_profiles':catalog.get_catalog()['materials_with_approved_profiles']}}
    if single and material=='manure' and request.components[0].material_state in {'unknown','slurry'} and request.allow_literature_transfer:
        hypothetical=request.components[0].model_copy(update={'material':'cattle_manure','material_state':'slurry','provenance':'ASSUMED_FOR_SCENARIO','evidence':'Conditional cattle-slurry example; species is NOT confirmed'})
        result['conditional_reference_case']=analyze(store,request.model_copy(update={'components':[hypothetical],'online':False}),persist=False)
    from src.advisor.engineering import evaluate as engineering_evaluate
    result['engineering']=engineering_evaluate(request,mix)
    result['original_request']=original_request;result['scenario_assumptions']=scenario_notes
    if persist:result['advisor_run_id']=evidence.append('advisor_run',{'request':request.model_dump(mode='json'),'result':result})
    return result
