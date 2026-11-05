"""Compare finite declared blends; no invented kinetic/stability optimizer."""
from src.advisor.schemas import ComparisonRequest,Candidate
from src.advisor.service import analyze
from src.research.evidence_store import EvidenceStore
def compare(store,data):
    request=data if isinstance(data,ComparisonRequest) else ComparisonRequest.model_validate(data)
    rows=[]
    for candidate in request.candidates:
        result=analyze(store,request.base.model_copy(update={'components':candidate.components}),persist=False)
        rows.append({'label':candidate.label,'result':result,'objectives':{'methane':result['mixture']['additive_methane_reference_m3'],
            'energy':{'production':result['decision_analysis']['energy']['outputs'],'reactor_demand':result['decision_analysis']['reactor_balance']},'duration':None,
            'profit':{r['id']:r.get('net_result_kzt') for r in result['decision_analysis']['scenarios']},
            'stability':None},'feasibility':result['decision_analysis']['feasibility']['status']})
    result={'version':'8.1','status':'COMPARISON_ONLY','candidates':rows,'preferred_mixture':None,'objective_selection':request.base.objectives,
            'reason':'Additive methane references do not validate co-digestion interactions, kinetics or stability. Missing objectives are not silently dropped.',
            'unsupported_optimization':['process duration without validated kinetics','stability without measured indicators and comparable mixture evidence'],
            'synergy_coefficient':None,'actuator_access':False}
    result['comparison_run_id']=EvidenceStore(store).append('advisor_comparison',{'request':request.model_dump(mode='json'),'result':result})
    return result

def suggestions(request):
    variants=[Candidate(label='Текущий состав / Current composition',components=request.components)]
    food=[c for c in request.components if c.material=='food_waste']
    if food and len(request.components)>1:
        variants.append(Candidate(label='Половина пищевого компонента / Half food component',components=[c.model_copy(update={'quantity':c.quantity*.5,'provenance':'ASSUMED_FOR_SCENARIO'}) if c.material=='food_waste' else c for c in request.components]))
        variants.append(Candidate(label='Без пищевого компонента / Without food component',components=[c for c in request.components if c.material!='food_waste']))
    return variants
