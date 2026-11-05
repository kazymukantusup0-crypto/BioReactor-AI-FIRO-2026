"""Shared evidence-scoped scenarios for API, Dashboard and chat.

Each study retains its paired solids and BMP. Unknown states are explicit
assumptions; measured properties and restrictions always take precedence.
"""
import itertools
import math
from src.advisor import catalog,mixing,engineering
from src.advisor.schemas import AdvisorRequest,Component
from src.advisor.advanced_science import summary,proxy
from src.economics import gas_composition

def variants(c, allow_transfer=True, conditional=True):
    # A measured or explicitly scoped input is never replaced by a different sample.
    if not allow_transfer or not conditional or c.data_mode=='MEASURED' or c.reference_profile_id:return [(c,[])]
    candidates=[]
    for p in catalog.profiles():
        if p['material']!=c.material or p.get('verification_stage')!='APPROVED_FOR_ESTIMATION':continue
        if c.decay_state in {'stored','rotted','composted'}:continue
        raw=c.model_dump();notes=[]
        if c.material_state=='unknown':
            raw['material_state']=p['material_state'];raw['physical_state']='unknown'
            notes.append('Physical form and preparation assumed comparable to '+p['preparation'])
        for key,restriction in [('animal','animals'),('poultry_type','poultry_types'),('bedding','beddings')]:
            allowed=p.get(restriction)
            if allowed and raw[key]=='unknown':
                raw[key]=allowed[0];notes.append(key+' assumed '+allowed[0]+' for this source scenario')
        raw['reference_profile_id']=p['id']
        if notes:raw['provenance']='ASSUMED_FOR_SCENARIO'
        try:chosen=Component.model_validate(raw)
        except ValueError:continue
        candidates.append((chosen,notes))
    # Each study remains a separate scenario, not a pooled statistical interval.
    return candidates or [(c,[])]

def scientific_request(base, mode='mixture', store=None):
    cs=base.components
    alternatives=mode=='alternatives'
    options=[variants(c,base.allow_literature_transfer,base.allow_conditional_profiles) for c in cs]
    count=sum(len(v) for v in options) if alternatives else math.prod(len(v) for v in options)
    groups=[[(v,) for v in opts] for opts in options] if alternatives else [list(itertools.islice(itertools.product(*options),8))]
    scenarios=[];sources={}
    for group in groups:
        for selected in group:
            selected_components=[v[0] for v in selected];notes=[n for v in selected for n in v[1]]
            request=base.model_copy(deep=True,update={'components':selected_components,'allow_conditional_profiles':False})
            mix=mixing.evaluate(request)
            for row in mix['components']:
                if row.get('source'):sources[row['source']['id']]=row['source']
            methane=mix['additive_methane_reference_m3']
            if any(r.get('source') for r in mix['components']):
                notes.append('Literature sample transferred to this batch; actual composition and plant recovery are unmeasured.')
            for row in mix['components']:
                notes.extend(row['assumptions'])
                if row.get('source'):
                    notes.extend(row['source'].get('limitations',[]))
            if request.assume_common_dry_gas_basis and any((r.get('source') or {}) for r in mix['components']):
                notes.append('Unknown source gas moisture treated as dry for the explicitly conditional common-basis calculation.')
            if request.assume_common_dry_gas_basis and any(r.get('source_stp_claimed') and r['gas_basis'] is None for r in mix['components']):
                notes.append('Source states STP without a full T/P definition; common dry reference is assumed, no verified normalization factor is available.')
            if len(cs)>1 and not alternatives:notes.append('Additive component reference only; synergy and inhibition are not predicted.')
            scenarios.append({'id':'s'+str(len(scenarios)+1),'result_level':'UNAVAILABLE' if methane is None and mix['known_component_additive_subtotal_m3'] is None else 'HYPOTHETICAL_SCENARIO' if notes else mix['result_level'],
                'label':' + '.join(catalog.name(c.material) for c in selected_components),
                'profile_ids':[r['profile_id'] for r in mix['components']], 'components':mix['components'],
                'methane_m3':methane,'known_component_subtotal_m3':mix['known_component_additive_subtotal_m3'],
                'complete':mix['complete_methane_reference'],'wet_mass_kg':mix['total_wet_mass_kg'],
                'vs_mass_kg':mix['total_vs_kg'],'ts_mass_kg':mix['total_ts_kg'],'gas_basis':mix['gas_basis'],'assumptions':notes,
                'missing':sorted({x for r in mix['components'] for x in r['missing'] if x!='density_kg_l' or r['wet_mass_kg'] is None}),
                'biogas':gas_composition.resolve(summary(mix),proxy(request,mix),request.decision),
                'request':request.model_dump(mode='json'),'mixture':mix,'engineering':engineering.evaluate(request,mix)})
    from src.advisor.experiment_evidence import review
    return {'status':'ok' if any(s['complete'] for s in scenarios) else 'needs_input','local_experiments':review(store,base),
        'message':'Reviewed same-material profiles evaluated as explicit scenarios; unavailable properties remain missing.',
        'catalog_checked':True,'comparison_mode':mode,'scenarios':scenarios,'sources':list(sources.values()),
        'reactor_total_volume_l':base.reactor_total_volume_l,'candidate_count':count,'truncated':count>len(scenarios),
        'reactor_role':'Vessel capacity is not feed volume, VS mass, daily throughput or methane storage capacity. Working volume, inoculum, dilution and headspace must be checked.',
        'uncertainty':'Points or sensitivity ranges from named samples; no validated prediction interval.'}
