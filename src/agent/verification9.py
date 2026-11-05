"""Independent checks of numerical outputs; no calls back into the calculators."""
import math
import re
from src.agent.scientific_tools import verify


def verify_results(results):
    checks=list(verify(results)['checks'])
    def record(name,passed,**scope):checks.append({'check':name,'passed':bool(passed),**scope})
    from src.advisor.catalog import profiles
    approved={p['id']:p for p in profiles()}
    science=results.get('assess_substrate_potential',{})
    scenarios={s['id']:s for s in science.get('scenarios',[])}
    for s in scenarios.values():
        record('no_actuation_authorized',s['engineering'].get('operation_authorized') is False,scenario=s['id'])
        for field in ['wet_mass_kg','vs_mass_kg','methane_m3']:
            bounds=s.get(field)
            if bounds:record('finite_nonnegative_ordered_'+field,all(math.isfinite(bounds[b]) for b in ['low','high']) and 0<=bounds['low']<=bounds['high'],scenario=s['id'])
        comparable=[c.get('methane_comparable_m3') for c in s['components']]
        if s.get('methane_m3') and all(comparable):
            record('independent_additive_total',all(math.isclose(sum(c[b] for c in comparable),s['methane_m3'][b],rel_tol=1e-6,abs_tol=1e-8) for b in ['low','high']),scenario=s['id'])
        geometry=s['engineering'];charge=geometry.get('complete_charge_volume_l');capacity=geometry.get('total_volume_l')
        if capacity and charge and charge['low']>capacity:
            record('capacity_violation_not_silenced',geometry['status']=='PHYSICALLY_INFEASIBLE',scenario=s['id'])
        for c in s['components']:
            profile=approved.get(c.get('profile_id'))
            if c.get('profile_id'):
                record('profile_identity_and_form',bool(profile and profile['material']==c['material'] and profile['material_state']==c['material_state']),scenario=s['id'],component=c['id'])
                source=c.get('source') or {}
                record('source_belongs_to_profile',bool(profile and source.get('id')==profile['source_id']),scenario=s['id'],component=c['id'])
            mass=c.get('wet_mass_kg');vs=c.get('vs_mass_kg')
            if mass and vs:record('vs_not_larger_than_wet_mass',0<=vs['low']<=vs['high']<=mass['high']+1e-8,scenario=s['id'])
    for row in results.get('evaluate_partial_economics',{}).get('scenarios',[]):
        analysis=row['analysis'];energy=analysis['energy'];outputs=energy['outputs']
        methane=scenarios.get(row['id'],{}).get('methane_m3')
        if methane and outputs:
            params=energy['parameters'];lhv=energy['heating_value']['value']
            for key,coefficients in [('potential_fuel_kwh',[]),('recovered_fuel_kwh',['recovery_fraction']),
                                     ('heat_only_kwh',['recovery_fraction','thermal_efficiency']),
                                     ('electricity_only_kwh',['recovery_fraction','electrical_efficiency']),
                                     ('chp_heat_kwh',['recovery_fraction','chp_thermal_efficiency']),
                                     ('chp_electricity_kwh',['recovery_fraction','chp_electrical_efficiency'])]:
                observed=outputs.get(key)
                if observed:
                    expected={bound:methane[bound]*lhv*math.prod(params[p][bound] for p in coefficients) for bound in ['low','high']}
                    record('independent_energy_'+key,all(math.isclose(expected[b],observed[b],rel_tol=1e-6,abs_tol=1e-8) for b in expected),scenario=row['id'])
        for alternative in analysis['scenarios']:
            if alternative.get('net_result_kzt') is not None and alternative['id'] in {'B_heat','C_electricity','CHP'}:
                record('net_requires_complete_operating_costs',analysis['operating_costs'].get('complete_total') is not None,scenario=row['id'],alternative=alternative['id'])
    return {'status':'error' if any(not c['passed'] for c in checks) else 'ok','checks':checks,'checked':bool(checks),
            'scope':'Arithmetic, source identity, material/form, energy allocation and cost completeness; not biological validation, interval coverage or operating safety.'}


def validate_synthesis(payload,evidence,results,state=None):
    issues=[]
    if not isinstance(payload,dict):return ['invalid_response_object']
    required={'conclusion','explanation','limitations','next_question','evidence_ids','decision'}
    if set(payload)!=required:return ['invalid_response_schema']
    texts=[payload['conclusion'],payload['explanation'],payload['next_question'] or '']
    if not isinstance(payload['limitations'],list) or len(payload['limitations'])>3:return ['invalid_limitations_schema']
    texts+=payload['limitations']
    if any(not isinstance(t,str) for t in texts):return ['invalid_text_schema']
    ids=payload['evidence_ids']
    if not isinstance(ids,list) or len(ids)>5 or any(not isinstance(i,str) or i not in evidence for i in ids):issues.append('unknown_evidence_reference')
    from src.agent.quantities9 import check
    if isinstance(ids,list) and all(isinstance(i,str) for i in ids):issues.extend(check(texts,evidence,ids,state))
    if isinstance(ids,list) and all(isinstance(i,str) and i in evidence for i in ids):
        scenario_ids={s['id'] for s in results.get('assess_substrate_potential',{}).get('scenarios',[])}
        chosen={evidence[i]['scenario'] for i in ids if evidence[i]['scenario'] in scenario_ids}
        # Separate typed references keep their scenario identity. Merely showing
        # two studies side by side is not pooling them into one distribution.
        if len(chosen)>1 and results.get('assess_substrate_potential',{}).get('comparison_mode')!='alternatives' and any(re.search(r'единый диапазон|общий интервал|усредн[её]нн|pooled range|pooled mean',t,re.I) for t in texts):
            issues.append('incompatible_scenarios_must_not_be_merged')
        methane_ids={k for k in evidence if k.endswith('.methane')}
        if methane_ids and not methane_ids.intersection(ids):issues.append('computed_methane_omitted')
    if payload['decision'] not in {'not_established','conditionally_viable','not_viable','not_applicable'}:issues.append('unknown_decision')
    if payload['decision'] in {'conditionally_viable','not_viable'} and not results.get('evaluate_partial_economics',{}).get('profit_established'):
        issues.append('economic_decision_without_complete_confirmed_basis')
    from src.agent.autonomous import _unsupported_conclusions
    issues.extend(_unsupported_conclusions(' '.join(texts),results))
    if results.get('assess_process_evidence'):
        for sentence in re.split(r'[.!?;]', ' '.join(texts)):
            if re.search(r'оптимальн|неоптимальн|\boptimal\b|\boptimum\b',sentence,re.I) and not re.search(r'не\s+(?:установ|определ|подтвержд)|неизвест|нельзя|не\s+могу|не\s+обязательно|not\s+(?:established|validated|known)|cannot|unknown',sentence,re.I):
                issues.append('temperature_optimum_not_established')
    if results.get('evaluate_partial_economics') and not results['evaluate_partial_economics'].get('profit_established'):
        for sentence in re.split(r'[.!?;]', ' '.join(texts)):
            if re.search(r'\bвыгоднее\b|\b(?:переработка|производство)\s+выгодн\w*',sentence,re.I) and not re.search(r'не\s+(?:установ|определ|подтвержд)|нельзя\s+(?:назвать|утвержд|сказать)|не\s+могу',sentence,re.I):
                issues.append('unconfirmed_profitability_ranking')
    for text in texts:
        if re.search(r'(?<!не\s)гарантирован(?:ный\s+выход|но\s+получ)|(?:загрузка|установка)\s+безопасна|можно\s+безопасно\s+загрузить',text,re.I):issues.append('unsupported_guarantee_or_safety_claim')
    if len(' '.join(texts).split())>180:issues.append('response_too_long')
    return list(dict.fromkeys(issues))
