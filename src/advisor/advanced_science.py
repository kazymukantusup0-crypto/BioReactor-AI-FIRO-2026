"""Composable v8 tools. Python owns every numerical value and its evidence."""
import copy
from src.advisor import catalog,mixing,conversion
from src.advisor.schemas import AdvisorRequest,Component
from src.economics import energy_conversion,gas_composition,complete_analysis
from src.estimation.schemas import EstimateRequest
from src.advisor.focused import geometry_for

TOOLS=['convert_substrate_units','estimate_advanced_gas','estimate_advanced_energy','evaluate_advanced_economics','get_matched_substrate_conditions']

def prepared(request,allow_illustrative=True):
    r=request.model_copy(deep=True);notes=[]
    baek=next(p for p in catalog.profiles() if p['material']=='cattle_manure' and p['material_state']=='bedded')
    for c in r.components:
        if c.data_mode=='MEASURED' or not r.allow_literature_transfer:continue
        # No dry-manure density is invented. A separate, named dry-solids scenario
        # may transfer VS/TS and B0, with an explicitly illustrative TS point.
        if c.material=='cattle_manure' and c.physical_state in {'dry','bedded'} and c.decay_state not in {'stored','rotted','composted'}:
            if (c.physical_state=='dry' or c.bedding in {'straw','other'}) and (allow_illustrative or c.data_mode=='ILLUSTRATIVE_ASSUMPTION'):
                detail='Illustrative drying scenario: TS=80% assumed; VS/TS and B0 from undried Baek sawdust-bedded sample; drying/storage effects unmeasured' if c.physical_state=='dry' else 'Illustrative straw-bedding scenario: TS/VS/B0 transferred from Baek sawdust-bedded sample; straw fraction and response unknown'
                values={'ts_fraction':.8 if c.physical_state=='dry' else .31,'vs_fraction_of_ts':.2353/.31,'bmp_ml_g_vs':109.2}
                raw=c.properties.model_dump()
                for key,value in values.items():
                    if getattr(c.properties,key) is None and not (key=='vs_fraction_of_ts' and c.properties.vs_fraction_wet is not None):
                        raw[key]={'low':value,'high':value,'provenance':'HYPOTHETICAL_SCENARIO','evidence':detail}
                # Revalidation turns scenario dicts into typed Range objects.
                c.properties=type(c.properties).model_validate(raw)
                if c.properties.gas_basis is None:
                    from src.economics.decision_schemas import GasBasis
                    c.properties.gas_basis=GasBasis(**baek['conditions']['gas_basis'])
                notes.append({'component':c.id,'source':baek['source'],'assumption':detail})
        if c.material=='straw' and c.physical_state=='unknown':c.physical_state='dry';c.material_state='dry';notes.append({'component':c.id,'assumption':'Straw treated as dry milled study material; not a measured preparation'})
        if c.material=='cattle_manure' and c.physical_state=='bedded':
            d=conversion.density_for(c,True)
            if d and c.properties.density_kg_l is None:
                # Reference density and BMP were measured on different materials.
                from src.economics.decision_schemas import Range
                c.properties.density_kg_l=Range(low=d['low'],high=d['high'],provenance='HYPOTHETICAL_SCENARIO',evidence=d['evidence']+'; cross-study density/BMP transfer')
                notes.append({'component':c.id,'source':d['source'],'assumption':'Alberta density at 68% moisture combined conditionally with Baek sample at 69% moisture; bedding/packing differ'})
    return r,notes

def summary(mix):
    return {'wet_mass_kg':mix['total_wet_mass_kg'],'vs_mass_kg':mix['total_vs_kg'],'methane_potential_m3':mix['additive_methane_reference_m3'],'structured_gas_basis':mix['gas_basis'],'result_level':mix['result_level'],'catalog_reference_value_kzt':None}

def proxy(r,mix):
    c=r.components[0];mass=mix['total_wet_mass_kg'];v=mix['sum_separate_volumes_l']
    return EstimateRequest(material=c.material if len(r.components)==1 else 'mixture',material_state=c.material_state if len(r.components)==1 and c.material_state in {'unknown','slurry','fresh_solid','bedded','dry','compost'} else 'unknown',mass_kg=mass['low'] if mass and mass['low']==mass['high'] else None,volume_l=v['high'] if v else None,reactor_total_volume_l=r.reactor_total_volume_l,region=r.region,region_confirmed=r.region_confirmed,decision=r.decision)

def run(name,context,store=None):
    request=AdvisorRequest.model_validate(context['advisor_request'])
    if name=='convert_substrate_units':
        target=context.get('target_unit','kg')
        return {'status':'ok','message':'Explicit conversion with scoped density','conversions':[{'id':c.id,'material':c.material,**conversion.convert(c,target,request.allow_literature_transfer)} for c in request.components],'target_unit':target,'actuator_access':False}
    r,notes=prepared(request)
    if name=='get_matched_substrate_conditions':
        studies=[]
        for c in r.components:
            p,_=catalog.choose(c,r.allow_literature_transfer)
            # Dry/straw cattle cases get only a labelled transfer reference.
            if p is None and any(n['component']==c.id for n in notes) and c.material=='cattle_manure':p=next(p for p in catalog.profiles() if p['material']=='cattle_manure' and p['material_state']=='bedded')
            if p:
                cond=p['conditions'];studies.append({'component':c.id,'source':p['source'],'temperature_c':cond.get('temperature_c'),'duration_days':cond.get('duration_days'),'kind':'BMP_INCUBATION','applies_to_actual_operation':False,'preparation':p.get('preparation'),'transfer_assumptions':[n['assumption'] for n in notes if n['component']==c.id]})
        return {'status':'ok','message':'Matched study conditions, not operating instructions','studies':studies,'geometry':geometry_for(r),'actuator_access':False}
    mix=context.get('mixture') or mixing.evaluate(r)
    if name=='estimate_advanced_gas':
        sources=list({s['id']:s for s in [row['source'] for row in mix['components'] if row['source']]+[n['source'] for n in notes if n.get('source')]}.values())
        # User BMP overrides keep their original reference basis. The optional
        # common dry basis is a visible scenario; known wet gas stays blocked.
        from src.economics.decision_schemas import Range
        decision=r.decision.model_copy(deep=True);assumed=decision.methane_fraction is None and decision.use_reference_scenarios
        if assumed:decision.methane_fraction=Range(low=.60,high=.60,provenance='HYPOTHETICAL_SCENARIO',evidence='Selected composition illustration; not measured')
        return {'status':'ok','message':'Additive laboratory reference; assumptions remain separate','mixture':mix,'biogas':gas_composition.resolve(summary(mix),proxy(r,mix),decision),'methane_fraction_assumed':assumed,'scenario_assumptions':notes,'sources':sources,'geometry':geometry_for(r),'actuator_access':False}
    s=summary(mix);p=proxy(r,mix)
    if name=='estimate_advanced_energy':
        decision=r.decision.model_copy(deep=True);fraction_assumed=False
        if decision.methane_fraction is None and decision.use_reference_scenarios:
            from src.economics.decision_schemas import Range
            decision.methane_fraction=Range(low=.60,high=.60,provenance='HYPOTHETICAL_SCENARIO',evidence='Selected 60% methane illustration, not a measurement or matched composition study');fraction_assumed=True
        return {'status':'ok','message':'Alternative uses of one fuel stream, not additive revenues','energy':energy_conversion.resolve(s,decision),'biogas':gas_composition.resolve(s,p,decision),'methane_fraction_assumed':fraction_assumed,'actuator_access':False}
    if name=='evaluate_advanced_economics':
        if store is None:
            from src.market.service import get_store
            store=get_store()
        return {'status':'ok','message':'Current saved market evidence and missing costs; no invented profit','decision_analysis':complete_analysis.analyze(store,p,s),'region_assumption':None if r.region_confirmed else r.region,'actuator_access':False}
    raise ValueError('Unknown advanced tool')
