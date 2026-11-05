"""Small read-only tool paths; conditions never invoke market/economic analysis."""
import copy
from src.advisor.schemas import AdvisorRequest
from src.advisor import catalog,mixing,temperature,duration
from src.estimation.schemas import EstimateRequest
from src.economics.gas_composition import resolve
from src.economics.feasibility import evaluate as check_geometry

TOOLS=['estimate_substrate_gas','advise_substrate_conditions']

def geometry_for(request):
    known_volume=sum(c.quantity*(1000 if c.unit=='m3' else 1) for c in request.components) if all(c.unit in {'L','m3'} and not c.evidence.startswith('Conditions-only reference') for c in request.components) else None
    proxy=EstimateRequest(material=request.components[0].material if len(request.components)==1 else 'mixture',volume_l=known_volume,reactor_total_volume_l=request.reactor_total_volume_l)
    return check_geometry(proxy,request.decision.reactor)
def run(name,context):
    request=AdvisorRequest.model_validate(context['advisor_request']);topics=context.get('topics',[])
    if set(topics)-{'temperature','duration'}:raise ValueError('Unknown condition topic')
    for c in request.components:c.material=catalog.normalized(c.material)
    if name=='advise_substrate_conditions':
        mix=mixing.evaluate(request) if request.feeding_period_days else {'olr_kg_vs_m3_day':None}
        geometry=geometry_for(request)
        result={'temperature':temperature.recommend(request,mix,geometry) if 'temperature' in topics else None,'duration':duration.recommend(request,mix) if 'duration' in topics else None,'geometry':geometry}
        ids={x['source_id'] for k,v in result.items() if k!='geometry' and v for x in v['studies']}
        result['sources']=[s for s in catalog.document()['sources'] if s['id'] in ids]
    else:
        mix=mixing.evaluate(request);single=len(request.components)==1;c=request.components[0]
        proxy=EstimateRequest(material=c.material if single else 'mixture',material_state=c.material_state if single and c.material_state in {'unknown','slurry','fresh_solid','bedded','dry','compost'} else 'unknown',decision=request.decision)
        summary={'methane_potential_m3':mix['additive_methane_reference_m3'],'structured_gas_basis':mix['gas_basis'],'result_level':mix['result_level']}
        result={'mixture':mix,'biogas':resolve(summary,proxy,request.decision),'sources':list({r['source']['id']:r['source'] for r in mix['components'] if r['source']}.values())}
        fraction=result['biogas'].get('methane_fraction') or {}
        if request.decision.methane_fraction is None and request.decision.use_reference_scenarios and proxy.material=='cattle_manure' and proxy.material_state in {'slurry','unknown'}:
            from src.research.profile_cache import read_profile
            from src.data.prepare import ROOT
            references=read_profile(ROOT/'data/research/decision_references.json')
            result['sources'] += [s for s in references['sources'] if s['id'].startswith('fnr-cattle-slurry-composition-')]
        if single and c.material=='manure' and request.allow_literature_transfer:
            hypothetical=request.model_copy(deep=True);hypothetical.components[0].material='cattle_manure';hypothetical.components[0].material_state='slurry';hypothetical.components[0].provenance='ASSUMED_FOR_SCENARIO'
            result['conditional_reference_case']=run(name,{'advisor_request':hypothetical.model_dump(mode='json')})
    return {'version':'7.7','status':'ok','message':'Requested quantities or studied conditions only; no actuator access','request':request.model_dump(mode='json'),**result,'actuator_access':False}
