"""Deterministic bidirectional conversion with explicit density provenance."""
from src.advisor.mixing import FACTORS,ratio
from src.economics.energy_conversion import pair,multiply,scale
from src.research.profile_cache import read_profile
from src.data.prepare import ROOT

def document():return read_profile(ROOT/'data/research/advanced_profiles.json')

def density_for(c,allow=True):
    if c.properties.density_kg_l:
        p=c.properties.density_kg_l
        mode='ILLUSTRATIVE_ASSUMPTION' if p.provenance=='HYPOTHETICAL_SCENARIO' else 'MEASURED' if p.provenance in {'MEASURED','USER_REPORTED'} else 'LITERATURE_ESTIMATE'
        return {'low':p.low,'high':p.high,'mode':mode,'evidence':p.evidence,'source':None,'limitations':['User-reported density; accuracy not independently verified']}
    if not allow or c.data_mode=='MEASURED':return None
    for p in document()['density_profiles']:
        if p['material']!=c.material or c.physical_state not in p['physical_states']:continue
        if c.decay_state in {'rotted','composted'}:continue
        if p.get('beddings') and c.bedding not in p['beddings']:continue
        return {**p['value'],'mode':'LITERATURE_ESTIMATE','source':next(s for s in document()['sources'] if s['id']==p['source_id']),'evidence':p['locator'],'limitations':p['limitations']}
    if c.physical_state=='unknown':
        from src.advisor.catalog import choose
        profile,assumed=choose(c,allow)
        forms={'slurry':'liquid','fresh_solid':'solid','dry':'dry','bedded':'bedded'}
        if profile and assumed and profile['material_state'] in forms:
            effective=c.model_copy(update={'physical_state':forms[profile['material_state']],'material_state':profile['material_state']})
            d=density_for(effective,allow)
            if d:return {**d,'mode':'ILLUSTRATIVE_ASSUMPTION','limitations':d['limitations']+['Unspecified form is conditionally treated as '+profile['material_state']]}
    return None

def convert(c,target_unit,allow=True):
    if target_unit not in FACTORS:raise ValueError('Unknown target unit')
    family,factor=FACTORS[c.unit];target,divisor=FACTORS[target_unit];value=pair(c.quantity*factor);density=None
    if family!=target:
        density=density_for(c,allow)
        if density is None:
            # Existing coherent study density is also allowed, with state matching.
            from src.advisor.catalog import choose
            p,_=choose(c,allow)
            if p and p.get('density_kg_l') and c.data_mode!='MEASURED':density={**p['density_kg_l'],'mode':'LITERATURE_ESTIMATE','source':p['source'],'evidence':p['density_kg_l'].get('locator'),'limitations':['Specific study sample; packing and moisture may differ']}
        if density is None:return {'status':'needs_input','value':None,'target_unit':target_unit,'density':None,'missing':['measured_density_or_explicit_illustrative_density'],'message':'Density for this material and state is unknown; no slurry substitution.'}
        value=multiply(value,density) if family=='volume' else ratio(value,density)
    return {'status':'ok','value':scale(value,1/divisor),'target_unit':target_unit,'density':density,'formula':'mass = volume × density; volume = mass / density','message':'Same-family SI conversion or explicitly scoped density conversion'}
