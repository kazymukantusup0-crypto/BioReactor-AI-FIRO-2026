"""Mass/solids conservation and an additive reference, never a synergy prediction."""
import math
from src.advisor import catalog
from src.economics.energy_conversion import pair,add,multiply,scale
from src.economics.gas_composition import compatible
FACTORS={'kg':('mass',1),'g':('mass',.001),'t':('mass',1000),'mL':('volume',.001),'L':('volume',1),'m3':('volume',1000)}
TARGET={'temperature_k':273.2,'pressure_pa':101325,'moisture':'dry','description':'Conditional common dry reference; not a measured mixture output'}
def normalized_quantity(component):
    family,factor=FACTORS[component.unit]
    return family,component.quantity*factor
def normalize_inventory(components):
    result={}
    for c in components:
        family,value=normalized_quantity(c);key=(c.id,c.material,c.material_state,c.animal,c.physical_state,c.decay_state,c.bedding,family)
        result[key]=result.get(key,0)+value
    return result
def bounds(value):return {'low':value.low,'high':value.high} if hasattr(value,'low') else {k:value[k] for k in ['low','high']}
def ratio(a,b):
    if b['low']<=0:return None
    return {'low':a['low']/b['high'],'high':a['high']/b['low']}
def total(rows,key):
    values=[r.get(key) for r in rows]
    if any(v is None for v in values):return None
    result=pair(0)
    for v in values:result=add(result,v)
    return result

def component_result(c,request):
    profile,state_assumed=catalog.choose(c,request.allow_literature_transfer)
    props=c.properties;used={};assumptions=[];missing=[]
    def resolve(key):
        explicit=getattr(props,key,None)
        if explicit is not None:
            used[key]={'range':bounds(explicit),'provenance':explicit.provenance,'evidence':explicit.evidence};return bounds(explicit)
        if profile and profile.get(key) is not None:
            original=profile[key];used[key]={'range':bounds(original),'provenance':'LITERATURE_ESTIMATE','source_id':profile['source_id'],'locator':original.get('locator'),'original_value':original.get('original_value'),'original_unit':original.get('original_unit')};assumptions.append(key+' transferred from '+profile['id']);return bounds(original)
        if key=='density_kg_l':
            from src.advisor.conversion import density_for
            d=density_for(c,request.allow_literature_transfer)
            if d:
                cross=bool(profile and d.get('source') and d['source']['id']!=profile['source_id'])
                used[key]={'range':bounds(d),'provenance':'HYPOTHETICAL_SCENARIO' if cross or d['mode']=='ILLUSTRATIVE_ASSUMPTION' else d['mode'],'source_id':(d.get('source') or {}).get('id'),'locator':d['evidence']}
                assumptions.extend(d['limitations']);return bounds(d)
        missing.append(key);return None
    family,q=normalized_quantity(c);mass=pair(q) if family=='mass' else None;volume=pair(q) if family=='volume' else None
    density=resolve('density_kg_l')
    if family=='volume' and density:mass=multiply(volume,density)
    if family=='mass' and density:volume=ratio(mass,density)
    ts=resolve('ts_fraction')
    if props.vs_fraction_wet:vsf=resolve('vs_fraction_wet')
    elif props.vs_fraction_of_ts:
        vsf=multiply(ts,bounds(props.vs_fraction_of_ts)) if ts else None
        used['vs_fraction_of_ts']={'range':bounds(props.vs_fraction_of_ts),'provenance':props.vs_fraction_of_ts.provenance}
    elif props.ts_fraction:vsf=None;missing.append('vs_fraction_on_explicit_TS_or_wet_basis')
    else:vsf=resolve('vs_fraction_wet')
    bmp=resolve('bmp_ml_g_vs');ts_mass=multiply(mass,ts) if mass and ts else None;vs_mass=multiply(mass,vsf) if mass and vsf else None
    methane=scale(multiply(vs_mass,bmp),.001) if vs_mass and bmp else None
    basis=props.gas_basis.model_dump() if props.gas_basis else (profile['conditions'].get('gas_basis') if profile else None)
    if profile and profile['id']=='oliveira-rm1-2025-v1' and props.bmp_ml_g_vs is None:basis={'temperature_k':273.2,'pressure_pa':101325,'moisture':'unknown','description':profile['conditions']['gas_reference']}
    if props.bmp_ml_g_vs is not None and props.gas_basis is None:basis=None
    if state_assumed:assumptions.append('Material state is assumed comparable to '+profile['material_state'])
    if profile and profile.get('state_transfer_note') and c.material_state in profile.get('conditional_states',[]):assumptions.append(profile['state_transfer_note'])
    if c.provenance=='ASSUMED_FOR_SCENARIO':assumptions.append('Quantity is hypothetical, not confirmed inventory')
    for key,v in used.items():
        if v['provenance']=='HYPOTHETICAL_SCENARIO':assumptions.append('Explicit scenario property: '+key)
    level='HYPOTHETICAL_SCENARIO' if state_assumed or c.provenance=='ASSUMED_FOR_SCENARIO' or any(x.get('provenance')=='HYPOTHETICAL_SCENARIO' for x in used.values()) else 'LITERATURE_ESTIMATE' if any(x.get('provenance')=='LITERATURE_ESTIMATE' for x in used.values()) else 'MEASURED'
    carbon=multiply(mass,bounds(props.carbon_fraction_wet)) if mass and props.carbon_fraction_wet else None
    nitrogen=multiply(mass,bounds(props.nitrogen_fraction_wet)) if mass and props.nitrogen_fraction_wet else None
    return {'id':c.id,'material':c.material,'display_name':catalog.name(c.material),'material_state':c.material_state,'animal':c.animal,'physical_state':c.physical_state,'decay_state':c.decay_state,'bedding':c.bedding,'quantity':c.quantity,'unit':c.unit,'wet_mass_kg':mass,'volume_l':volume,'ts_mass_kg':ts_mass,'vs_mass_kg':vs_mass,'methane_reference_m3':methane,
            'carbon_mass_kg':carbon,'nitrogen_mass_kg':nitrogen,'gas_basis':basis,'result_level':level,'profile_id':profile['id'] if profile else None,'properties_used':used,'assumptions':assumptions,'missing':list(dict.fromkeys(missing)),
            'source':profile['source'] if profile else None,'source_stp_claimed':bool(profile and profile.get('source_stp_claimed')),'source_basis_missing':bool(profile and basis is None),'cn_ratio_reference':profile.get('cn_ratio') if profile else None,'ph_reference':profile.get('ph') if profile else None,
            'notice':'Single-component literature/measurement reference. A published sample point is not a universal population mean; no unreported SD is invented.'}

def evaluate(request):
    rows=[component_result(c,request) for c in request.components];known=[];normalization=[];all_gas_known=True
    source_ids={r['source']['id'] for r in rows if r['source']};same_protocol=len(source_ids)==1 and len([r for r in rows if r['source']])==len(rows)
    bases=[r['gas_basis'] for r in rows];common=bases[0] if bases and bases[0] and all(b is not None and (b==bases[0] or compatible(bases[0],b,False)[0]) for b in bases) else None
    for row in rows:
        value=row['methane_reference_m3'];b=row['gas_basis']
        if value is not None and b is None and (request.assume_unreported_gas_basis or request.assume_common_dry_gas_basis and row.get('source_stp_claimed')):
            row['methane_comparable_m3']=value;known.append(value);normalization.append({'component':row['id'],'factor':None,'assumption':'Unreported gas T/P/moisture explicitly treated as common dry reference; no normalization factor can be inferred'});continue
        if value is not None and b is None and len(rows)==1 and row.get('source_basis_missing'):
            row['methane_comparable_m3']=value;known.append(value);normalization.append({'component':row['id'],'factor':None,'assumption':'Single-component native study volume only; unknown gas basis blocks energy and pooling'});continue
        if value is None or b is None:all_gas_known=False;row['methane_comparable_m3']=None;continue
        if request.assume_common_dry_gas_basis:
            if b['moisture']=='wet':row['methane_comparable_m3']=None;all_gas_known=False;normalization.append('Known wet gas cannot be silently dried');continue
            factor=(b['pressure_pa']/TARGET['pressure_pa'])*(TARGET['temperature_k']/b['temperature_k'])
            normalized=scale(value,factor);normalization.append({'component':row['id'],'factor':factor,'assumption':'Unknown source moisture treated as comparable dry gas; ideal-gas T/P normalization only'})
        elif len(rows)==1 or same_protocol and common is not None:normalized=value
        else:
            match,_=compatible(common,b,False)
            if not match:row['methane_comparable_m3']=None;all_gas_known=False;continue
            normalized=value
        row['methane_comparable_m3']=normalized;known.append(normalized)
    subtotal=pair(0)
    for value in known:subtotal=add(subtotal,value)
    methane=subtotal if all_gas_known and len(known)==len(rows) else None
    mass=total(rows,'wet_mass_kg');volume=total(rows,'volume_l');ts=total(rows,'ts_mass_kg');vs=total(rows,'vs_mass_kg')
    for row in rows:row['wet_mass_fraction']=ratio(row['wet_mass_kg'],mass) if row['wet_mass_kg'] and mass else None
    carbon=total(rows,'carbon_mass_kg');nitrogen=total(rows,'nitrogen_mass_kg');cn=ratio(carbon,nitrogen) if carbon and nitrogen else None
    olr=None
    if request.decision.reactor.operating_mode=='continuous' and request.decision.reactor.reactor_working_volume_l and request.feeding_period_days and vs:
        olr=scale(vs,1/request.feeding_period_days/(request.decision.reactor.reactor_working_volume_l/1000))
    return {'components':rows,'total_wet_mass_kg':mass,'sum_separate_volumes_l':volume,'total_ts_kg':ts,'total_vs_kg':vs,'cn_mass_ratio':cn,'mixture_ph':None,
            'additive_methane_reference_m3':methane,'known_component_additive_subtotal_m3':subtotal if known else None,'complete_methane_reference':methane is not None,
            'gas_basis':TARGET if request.assume_common_dry_gas_basis and all(r['gas_basis'] or request.assume_unreported_gas_basis or r.get('source_stp_claimed') for r in rows) or request.assume_unreported_gas_basis else common,'normalization':normalization,'olr_kg_vs_m3_day':olr,
            'synergy_factor':None,'measured_mixture_bmp':None,'result_level':'HYPOTHETICAL_SCENARIO' if len(rows)>1 or normalization or any(r['result_level']=='HYPOTHETICAL_SCENARIO' for r in rows) else rows[0]['result_level'],
            'limitations':['Additive component references are not a validated methane yield of the mixture. No synergy coefficient is assumed.',
                          'Known-part subtotal is neither the full mixture prediction nor a lower bound on actual co-digestion yield.',
                          'Separate volumes may not add to final packed/liquid mixture volume; verify actual charge.',
                          'C/N requires carbon and nitrogen masses. pH cannot be averaged. Batch loading is not a daily OLR.',
                          'Sensitivity bounds have no verified probability coverage.']}
