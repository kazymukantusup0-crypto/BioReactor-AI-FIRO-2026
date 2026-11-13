"""Independent checks of numerical outputs; no calls back into the calculators."""
import math
import re
import json
from src.agent.scientific_tools import verify


def verify_results(results):
    """Fail closed on invalid protocols; absence of checks is never a numeric pass."""
    try:
        if not isinstance(results,dict) or any(not isinstance(r,dict) for r in results.values()):raise TypeError('Results must map tool names to objects')
        json.dumps(results,allow_nan=False)
        return _verify_results(results)
    except (AttributeError,KeyError,TypeError,ValueError,OverflowError) as exc:
        return {'status':'error','outcome':'failed','checks':[],'checked':False,
                'all_checks_passed':False,'error_code':'INVALID_TOOL_RESULT_'+type(exc).__name__}


def _verify_results(results):
    arithmetic=verify(results)
    if arithmetic['status']=='error' and not arithmetic['checks']:return arithmetic
    checks=list(arithmetic['checks'])
    def record(name,passed,**scope):checks.append({'check':name,'passed':bool(passed),**scope})
    from src.advisor.catalog import profiles
    approved={p['id']:p for p in profiles()}
    science=results.get('assess_substrate_potential',{})
    scenarios={s['id']:s for s in science.get('scenarios',[])}
    for s in scenarios.values():
        energy=s.get('conditional_reference_energy')
        if energy:
            record('conditional_reference_energy_arithmetic_and_scope',energy.get('method')=='CALCULATED_CONDITIONAL' and bool(energy.get('assumption')) and energy.get('source_url')=='https://biogas.fnr.de/daten-und-fakten/faustzahlen' and all(math.isclose(energy['value'][b],s['methane_m3'][b]*9.97,rel_tol=1e-9) for b in ['low','high']),scenario=s['id'])
        if s.get('methane_m3') is not None:
            provenance=s.get('result_provenance')
            record('calculated_methane_not_claimed_as_measured',s.get('result_level') != 'MEASURED' and (provenance is None or provenance.get('method')=='CALCULATED'),scenario=s['id'])
            if provenance is not None:
                record('no_unperformed_scientific_certification',provenance.get('verification',{}).get('status') not in {'VERIFIED','SCIENTIFICALLY_VERIFIED','BIOLOGICALLY_VERIFIED'},scenario=s['id'])
        biogas=s.get('biogas') or {}
        if biogas.get('potential_biogas_m3') is not None:
            provenance=biogas.get('result_provenance')
            record('calculated_biogas_not_claimed_as_measured',biogas.get('result_level')!='MEASURED' and (provenance is None or provenance.get('method')=='CALCULATED'),scenario=s['id'])
        record('no_actuation_authorized',s['engineering'].get('operation_authorized') is False,scenario=s['id'])
        for field in ['wet_mass_kg','vs_mass_kg','methane_m3']:
            bounds=s.get(field)
            if bounds:record('finite_nonnegative_ordered_'+field,all(math.isfinite(bounds[b]) for b in ['low','high']) and 0<=bounds['low']<=bounds['high'],scenario=s['id'])
        timed=s.get('time_yield') or {}
        if timed.get('methane_l') is not None:
            fit=timed.get('kinetic_inputs',{});days=timed.get('days');potential=s.get('potential_methane_l')
            try:
                expected={b:potential[b]*(-math.expm1(-fit['rate_per_day'][b]*max(0,days-fit['lag_days']['high' if b=='low' else 'low']))) for b in ('low','high')}
                ok=(timed.get('method')=='first_order' and fit.get('applicable_to_batch') is True
                    and all(math.isclose(expected[b],timed['methane_l'][b],rel_tol=1e-8) for b in expected))
            except (KeyError,TypeError,ValueError):ok=False
            record('independent_timed_yield_requires_applicable_fit',ok,scenario=s['id'])
        comparable=[c.get('methane_comparable_m3') for c in s['components']]
        if s.get('methane_m3') and all(comparable):
            record('independent_additive_total',all(math.isclose(sum(c[b] for c in comparable),s['methane_m3'][b],rel_tol=1e-6,abs_tol=1e-8) for b in ['low','high']),scenario=s['id'])
        geometry=s['engineering'];charge=geometry.get('complete_charge_volume_l');capacity=geometry.get('total_volume_l')
        if capacity and charge and charge['low']>capacity:
            record('capacity_violation_not_silenced',geometry['status']=='PHYSICALLY_INFEASIBLE',scenario=s['id'])
        for c in s['components']:
            if s.get('estimation_mode'):
                from src.advisor.mixing import FACTORS
                properties=c.get('properties_used',{})
                family,factor=FACTORS[c['unit']];quantity=c['quantity']*factor
                density=properties.get('density_kg_l',{}).get('range')
                if family=='volume':
                    for field,key in [('ts_mass_kg','ts_kg_l'),('vs_mass_kg','vs_kg_l')]:
                        concentration=properties.get(key,{}).get('range')
                        if concentration and c.get(field):
                            record('independent_volume_times_'+key,all(math.isclose(quantity*concentration[b],c[field][b],rel_tol=1e-9) for b in ('low','high')),scenario=s['id'],component=c['id'])
                expected_mass=({'low':quantity,'high':quantity} if family=='mass' else
                    {b:quantity*density[b] for b in ('low','high')} if density else None)
                if expected_mass and c.get('wet_mass_kg'):
                    record('independent_quantity_density_mass_basis',all(math.isclose(expected_mass[b],c['wet_mass_kg'][b],rel_tol=1e-9) for b in expected_mass),scenario=s['id'],component=c['id'])
                    ts=properties.get('ts_fraction',{}).get('range')
                    vs=properties.get('vs_fraction_wet',{}).get('range')
                    of_ts=properties.get('vs_fraction_of_ts',{}).get('range')
                    if vs is None and ts and of_ts:vs={b:ts[b]*of_ts[b] for b in ('low','high')}
                    for field,fraction in [('ts_mass_kg',ts),('vs_mass_kg',vs)]:
                        if fraction and c.get(field):
                            record('independent_'+field+'_on_wet_mass_basis',all(math.isclose(expected_mass[b]*fraction[b],c[field][b],rel_tol=1e-9) for b in expected_mass),scenario=s['id'],component=c['id'])
            if c.get('methane_reference_m3') is not None:
                provenance=c.get('result_provenance')
                record('calculated_component_not_claimed_as_measured',c.get('result_level') != 'MEASURED' and (provenance is None or provenance.get('method')=='CALCULATED'),scenario=s['id'],component=c['id'])
            profile=approved.get(c.get('profile_id'))
            if s.get('estimation_mode'):
                for key,used in c.get('properties_used',{}).items():
                    if used.get('provenance')=='LITERATURE_ESTIMATE':
                        published=(profile or {}).get(key)
                        record('literature_value_matches_reviewed_source_'+key,
                            bool(published and used.get('source_id')==profile['source_id']
                                 and all(math.isclose(used['range'][b],published[b],rel_tol=1e-10) for b in ('low','high'))),scenario=s['id'],component=c['id'])
            if c.get('profile_id'):
                record('profile_identity_and_form',bool(profile and profile['material']==c['material'] and profile['material_state']==c['material_state']),scenario=s['id'],component=c['id'])
                source=c.get('source') or {}
                record('source_belongs_to_profile',bool(profile and source.get('id')==profile['source_id']),scenario=s['id'],component=c['id'])
                density=c.get('properties_used',{}).get('density_kg_l',{})
                if density.get('provenance')=='LITERATURE_ESTIMATE' and c['unit'] in {'L','mL','m3'}:
                    record('literature_density_same_profile_and_explicit_mode',
                        s.get('request',{}).get('estimation_mode')=='LITERATURE_ESTIMATE'
                        and s.get('request',{}).get('allow_literature_density') is True
                        and bool(profile and profile.get('density_kg_l'))
                        and density.get('source_id')==profile['source_id'],scenario=s['id'])
            mass=c.get('wet_mass_kg');vs=c.get('vs_mass_kg')
            if mass and vs:record('vs_not_larger_than_wet_mass',0<=vs['low']<=vs['high']<=mass['high']+1e-8,scenario=s['id'])
    for row in results.get('evaluate_partial_economics',{}).get('scenarios',[]):
        analysis=row['analysis'];energy=analysis['energy'];outputs=energy['outputs']
        if outputs:
            provenance=energy.get('result_provenance')
            record('calculated_energy_not_claimed_as_measured',energy.get('result_level') != 'MEASURED' and (provenance is None or provenance.get('method')=='CALCULATED'),scenario=row['id'])
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
    explicit=results.get('explicit_calculations',{})
    def sale_value(row):
        offer=row['inputs']['sale_offer_amount']['value'];scope=row['inputs'].get('sale_offer_scope',{}).get('value')
        if scope=='batch':return offer
        if scope=='L':
            quantity=row['inputs']['quantity']['value'];unit=row['inputs']['unit']['value']
            return quantity*(1000 if unit=='m3' else 1)*offer
        mass=row['inputs']['mass_kg']['value']
        return mass/1000*offer if scope=='t' else mass*offer
    explicit_formulas={
        'sale_gross_value_kzt':sale_value,
        'sale_gross_value':sale_value,
        'methane_potential_m3':lambda x:x['inputs']['vs_mass_kg']['value']*x['inputs']['bmp_ml_ch4_g_vs']['value']*.001,
        'measured_methane_balance_m3':lambda x:x['inputs']['reported_biogas_volume_m3']['value']*x['inputs']['methane_fraction']['value'],
        'electricity_kwh':lambda x:x['inputs']['reported_methane_volume_m3']['value']*x['inputs']['heating_value_kwh_m3']['value']*x['inputs']['electricity_efficiency']['value'],
    }
    for row in explicit.get('calculations',[]):
        if row.get('kind') in {'sale_gross_value','sale_gross_value_kzt'}:
            inputs=row.get('inputs',{});amount=inputs.get('sale_offer_amount',{});scope=inputs.get('sale_offer_scope',{}).get('value');currency=inputs.get('sale_offer_currency',{}).get('value')
            valid_unit=amount.get('unit') in {None,f'{currency}/{scope}'}
            batch=inputs.get('batch_sale_price_kzt')
            if batch:valid_unit=valid_unit and batch.get('unit')=='KZT/batch' and batch.get('value')==amount.get('value')
            record('sale_input_role_and_unit',valid_unit,calculation_id=row.get('id'))
        try:
            expected=explicit_formulas[row['kind']](row);observed=row['value']
            passed=(isinstance(expected,(int,float)) and isinstance(observed,(int,float))
                and not isinstance(observed,bool) and math.isfinite(expected) and math.isfinite(observed)
                and expected>=0 and observed>=0 and math.isclose(expected,observed,rel_tol=1e-9,abs_tol=1e-10)
                and row.get('provenance') in {'CALCULATED_FROM_CONFIRMED','ASSUMED_FOR_SCENARIO'})
        except (KeyError,TypeError,ValueError,ZeroDivisionError):
            expected=None;observed=row.get('value');passed=False
        record('explicit_calculation_arithmetic',passed,calculation_id=row.get('id'),kind=row.get('kind'),expected=expected,observed=observed)
    informational={'assess_process_evidence','analyze_substrate','search_substrate_profiles','compare_scientific_studies',
                   'verify_scientific_sources','search_public_scientific_metadata','assess_scientific_risks',
                   'get_model_info','get_reactor_status','get_market_prices','get_price_history','search_scientific_sources'}
    covered={'assess_substrate_potential','estimate_methane_yield','evaluate_partial_economics','recover_local_scientific_analysis','recover_partial_economics',
             'verify_scientific_calculations','check_reactor_loading','calculate_dilution_plan','analyze_economic_sensitivity','explicit_calculations'}
    unsupported=set(results)-informational-covered
    numeric=set(results)&covered
    missing=[]
    for scenario in scenarios.values():
        for component in scenario['components']:
            if component.get('methane_reference_m3') and not any(c['check']=='VS_kg_times_BMP_ml_per_g_times_0.001'
                and c.get('scenario')==scenario['id'] and c.get('component')==component['id'] for c in checks):
                missing.append(scenario['id']+'.'+component['id']+'.source_basis_arithmetic')
    for name in ('assess_substrate_potential','evaluate_partial_economics'):
        if name in results and not results[name].get('scenarios'):missing.append(name+'.scenarios')
    if 'evaluate_partial_economics' in results and not scenarios:missing.append('assess_substrate_potential.scenarios')
    if 'explicit_calculations' in results and not results['explicit_calculations'].get('calculations'):
        missing.append('explicit_calculations.calculations')
    if any(not c['passed'] for c in checks):outcome='failed'
    elif unsupported or missing or numeric and not checks:outcome='insufficient_evidence'
    elif checks:outcome='passed'
    else:outcome='not_applicable'
    return {'status':{'passed':'ok','failed':'error'}.get(outcome,outcome),'outcome':outcome,
            'checks':checks,'checked':bool(checks),'all_checks_passed':outcome=='passed',
            'unsupported_tools':sorted(unsupported),'missing_verification_evidence':missing,
            'scope':'Arithmetic, source identity, material/form, energy allocation and cost completeness; not biological validation, interval coverage or operating safety.'}


def may_synthesize(verification,required_tools,results=None):
    if verification.get('status')=='ok':return verification.get('checked') is True and verification.get('all_checks_passed') is True
    if verification.get('status')=='insufficient_evidence' and results:
        search=results.get('search_scientific_sources',{})
        ids={s.get('id') for s in search.get('sources',[])}
        # Missing batch inputs prohibit forecasts, not source-bound qualitative explanation.
        return bool(search.get('claims')) and all(c.get('source_id') in ids for c in search['claims']) and not any(not c.get('passed') for c in verification.get('checks',[]))
    return verification.get('status')=='not_applicable' and not set(required_tools)&{'assess_substrate_potential','evaluate_partial_economics'}


def scientific_assertions(text):
    """Bounded RU/KK/EN proposition rules with negation and target scope.

    These rules detect known contradiction families; they are not a general
    semantic model. The matched statements and predicate scopes stay auditable.
    """
    findings=[]
    def hit(pattern,clause):return re.search(pattern,clause,re.I)
    def add(rule,statement,subject,scope,passed=False):
        findings.append({'rule':rule,'statement':statement,'subject':subject,'scope':scope,'passed':passed})
    for clause in re.split(r'(?<=[.!?])\s+|[;\n]|\b(?:но(?!\s+не\s+перенос)|but(?!\s+cannot\s+be\s+transferred)|однако|however|бірақ|алайда)\b',text,flags=re.I):
        if hit(r'^\s*(?:неверно|ошибочно)\s*,?\s*что|^\s*нельзя\s+(?:говорить|утверждать)\s*,?\s*что|^\s*it\s+is\s+(?:false|wrong)\s+that|^\s*it\s+(?:is|would\s+be)\s+wrong\s+to\s+(?:claim|say)|деу\s+(?:дұрыс\s+емес|қате)[\s.!?]*$',clause):continue
        bmp=bool(hit(r'\b(?:bmp|бмп)\b',clause))
        reactor=bool(hit(r'реактор|reactor|digester',clause))
        measurement_denied=bool(hit(
            r'(?:bmp|бмп).{0,45}(?:не\s+измеряется|не\s+измеряют|невозможно\s+измерить|нельзя\s+измерить|не\s+является\s+экспериментальн)|'
            r'(?:определить|измерить)\s+(?:bmp|бмп).{0,50}(?:нельзя|невозможно)|(?:лабораторн\w*|экспериментальн\w*).{0,20}(?:определение|измерение)\s+(?:bmp|бмп).{0,25}невозмож|'
            r'\bbmp\b.{0,35}(?:(?:is\s+not|isn.t)\s+(?:experimentally\s+)?measured|cannot\s+be\s+measured|is\s+not\s+an?\s+experimental\s+measurement)|'
            r'(?:experimental|laboratory)\s+measurement\s+of\s+bmp.{0,25}(?:impossible|not\s+possible)|\bbmp\b.{0,70}no\s+experimental\s+basis|'
            r'\bbmp\b.{0,55}(?:өлшенбейді|анықталмайды|өлшеу\s+мүмкін\s+емес|өлшенетін\s+(?:шама|көрсеткіш)\s+емес)',clause))
        if measurement_denied:add('bmp_experimental_measurement_denied',clause,'BMP','experimental assay measurement')
        ambiguous=bool(hit(r'(?:bmp|бмп).{0,85}(?:не\s+измеренн\w*\s+выработ|not\s+(?:a\s+|the\s+)?measured\s+(?:output|yield))',clause)) and not reactor
        if ambiguous:add('bmp_measurement_scope_ambiguous',clause,'BMP','unscoped denial of measured output')
        experimental=bool(hit(r'экспериментальн|измеря(?:ют|ется|ем\w*)|измеренн\w*\s+(?:потенциал|bmp)|experimentally|experimental|\bmeasured\b|өлшенеді|өлшенетін|эксперименттік|тәжірибел',clause))
        if bmp and experimental and not measurement_denied and not ambiguous:
            add('bmp_experimental_basis_explained',clause,'BMP','laboratory assay',True)
        theory=hit(r'(?:bmp|бмп).{0,65}(?:теоретическ|theoretical|теориялық).{0,30}(?:максим|maximum)|(?:bmp|бмп).{0,30}(?:исключительн|purely|only|тек).{0,30}(?:теоретическ|theoretical|теориялық)',clause)
        theory_negated=hit(r'не\s+(?:явля\w*|равен|равно)|нельзя\s+счита\w*|\bnot\b|isn.t|cannot\s+be\s+(?:equated|considered)|теориялық.{0,35}емес',clause)
        if theory and not theory_negated:add('bmp_equated_to_theoretical_maximum',clause,'BMP','stoichiometric maximum')
        numeric_inequality=hit(r'(?:\bbmp\b|бмп).{0,70}(?:не\s+равен|не\s+равно|не\s+равн\w*|не\s+совпада\w*|not\s+equal\s+to|never\s+equals?).{0,45}(?:теоретическ\w*\s+(?:выход|максимум)|theoretical\s+(?:yield|maximum))',clause)
        if numeric_inequality and not hit(r'как\s+поняти|по\s+определени|не\s+обязательно|не\s+всегда|не\s+означа|not\s+necessarily|not\s+always|as\s+concepts',clause):
            add('bmp_theoretical_values_unconditionally_unequal',clause,'BMP','unqualified numerical inequality')
        batch=hit(r'batch|батч|(?:bmp|бмп)[\s-]*(?:тест|сына|test|assay)',clause)
        kinetics=hit(r'кинетик|kinetic|услови\w*|conditions?|жағдай',clause)
        no_effect=hit(r'не\s+(?:влия\w*|отраж\w*|завис\w*)|не\s+оказыва\w*.{0,15}влия|independent\s+of|unaffected\s+by|(?:does|do)\s+not\s+affect|doesn.t\s+affect|no\s+(?:influence|effect)|әсер\s+етпейді|тәуелді\s+емес|көрсетілмейді',clause)
        if batch and kinetics and no_effect:
            target=clause[no_effect.end():]
            theoretical_target=hit(r'теоретическ|theoretical|теориялық',target) and not hit(r'batch|батч|тест|сына',target)
            reactor_target=hit(r'реактор|reactor',target) and not hit(r'batch|батч|тест|сына',target)
            if not theoretical_target and not reactor_target:
                add('batch_kinetics_or_conditions_denied',clause,'kinetics / assay conditions','batch assay observation and rate')
        guarantee=hit(r'гарантир\w*|\bguarantee\w*|кепілдік\s+бере\w*',clause)
        if bmp and guarantee:
            prefix=clause[:guarantee.start()]
            neg=hit(r'(?:не|not|no|never|cannot|doesn.t|do\s+not|does\s+not)\s*$',prefix)
            if not neg:add('bmp_guarantees_reactor_yield',clause,'BMP','guaranteed operational yield')
        transfer=hit(r'не\s+переносим\w*|не\s+переносится|невозможно\s+перенести|неприменим\w*|совсем\s+не\s+применим\w*|cannot\s+be\s+transferred|cannot\s+be\s+applied|(?:completely|entirely)\s+inapplicable',clause)
        lab=hit(r'лаборатор|испытан|batch|lab(?:orator)?y|assay|кинетик|kinetic',clause)
        plant=hit(r'промышленн|установк|реактор|industry|industrial|reactor|plant',clause)
        qualified=hit(r'автоматическ|без\s+(?:уч[её]та|проверки|адаптац)|напрямую|directly|automatically|without\s+(?:adjust|consider|validat)|в\s+этом\s+случае|данн\w*\s+реактор',clause)
        if transfer and lab and plant and not qualified:
            add('absolute_lab_transfer_denial',clause,'laboratory evidence','unqualified transfer to reactors')
        if (hit(r'метаноген\w*|methanogen\w*',clause)
            and hit(r'(?:производ\w*|образу\w*|получа\w*|использу\w*|produce\w*|use\w*)',clause)
            and hit(r'(?:только|исключительно|лишь|only|exclusively).{0,45}(?:органическ|organic)|(?:из|from)\s+органическ\w*\s+веществ|from\s+organic\s+(?:matter|substances)',clause)
            and not hit(r'некотор\w*|часть\s+метаноген|some\s+methanogen|H[₂2]\s*\+\s*CO[₂2]|водород|hydrogen',clause)):
            add('methanogenesis_only_organic_substrates',clause,'methanogens','unqualified feedstock pathways')
        pure_biogas=hit(r'биогаз\s*(?:—|–|-|это|является)\s*(?:это\s+)?(?:чист\w*|только)\s+метан|biogas\s+(?:is|equals)\s+(?:pure|only)\s+methane',clause)
        volumes_equated=hit(r'(?:объ[её]м\w*\s+(?:метан\w*|биогаз\w*).{0,30}(?:равен|равно|equals?).{0,30}объ[её]м\w*\s+(?:метан\w*|биогаз\w*)|(?:methane|biogas)\s+volume.{0,30}(?:equals?|is\s+equal\s+to).{0,30}(?:methane|biogas)\s+volume)',clause) and hit(r'метан|methane|ch[₄4]',clause) and hit(r'биогаз|biogas',clause)
        if (pure_biogas or volumes_equated) and not hit(r'не\s+(?:явля|чист|равен|равно)|\bnot\b|очищенн|upgrad',clause):
            add('methane_biogas_equated',clause,'biogas','gas composition')
        comparison=hit(r'больше|меньше|выше|ниже|превыш|равен|greater|less|higher|lower|equals?',clause)
        bmp_basis=hit(r'(?<![\w])\d+[.,]?\d*\s*(?:мл|ml)\s*(?:ch[₄4])?\s*/\s*(?:г|g)\s*vs',clause)
        absolute_gas=hit(r'(?<![\w])\d+[.,]?\d*\s*(?:л\b|литр\w*|l\b|м³|м3|m³|m3)(?!\s*/)',clause)
        neg_compare=hit(r'не(?:льзя)?\s+(?:напрямую\s+)?сравни|cannot\s+(?:directly\s+)?compare|not\s+directly\s+comparable',clause)
        if bmp and comparison and bmp_basis and absolute_gas and not neg_compare:
            add('bmp_yield_incompatible_basis',clause,'BMP versus yield','specific BMP versus absolute gas volume')
        actual=hit(r'фактическ\w*.{0,25}(?:выход|выработ)|actual.{0,25}(?:yield|output)|нақты.{0,25}(?:шығым|өнім)',clause)
        timed=hit(r'\d+\s*(?:дн\w*|сут\w*|days?|күн\w*|тәулік\w*)',clause)
        equal=hit(r'равен|равно|совпада\w*|equals?|\bтең\b',clause)
        not_equal=hit(r'не\s+(?:всегда\s+)?(?:равен|равно|совпада\w*)|(?:not|never).{0,18}(?:equal|same)|тең\s+емес|(?:может|may|might|мүмкін)',clause)
        if bmp and actual and timed and equal and not not_equal:add('fixed_time_yield_equated_to_bmp',clause,'actual methane yield','fixed time versus assay potential')
    # Oxygen checking is independent of whether the BMP abbreviation occurs.
    for clause in re.split(r'[.!?;\n]|\b(?:но|однако|but|however|бірақ)\b',text,flags=re.I):
        if re.match(r'\s*(?:неверно\s*,?\s*что|it\s+is\s+false\s+that)',clause,re.I):continue
        oxygen=hit(r'кислород\w*|\boxygen\b|оттегі\w*',clause)
        process=hit(r'метаноген\w*|анаэроб\w*|сбраж\w*|methanogen\w*|anaerobic|digestion',clause)
        requirement=hit(r'нуж\w*|необходим\w*|требу\w*|requires?|needs?|essential|қажет',clause)
        negative=hit(r'\bне\s+(?:нуж\w*|необходим\w*|требу\w*)|без\s+(?:свободн\w*\s+)?кислород\w*|(?:does\s+not|doesn.t|not)\s+(?:require|need)|without\s+oxygen|қажет\s+емес|оттегісіз',clause)
        if oxygen and process and requirement and not negative:add('oxygen_required_for_anaerobic_process',clause,'methanogenesis','free oxygen requirement')
    return findings


def verify_scientific_answer(text,results,query):
    """Scoped source/contradiction/coverage checks, never general truth certification."""
    search=results.get('search_scientific_sources',{})
    claims=search.get('claims',[])
    checks=[]
    def record(name,passed):checks.append({'check':name,'passed':bool(passed)})
    estimate=results.get('assess_substrate_potential',{}).get('estimation_mode')
    scoped_calculation=bool(results.get('assess_substrate_potential',{}).get('scenarios'))
    process=results.get('assess_process_evidence',{}).get('temperature_consultation',{})
    applicable=bool(claims or estimate or scoped_calculation or process or re.search(r'\bbmp\b|бмп|кислород|oxygen|оттегі|метаноген',query,re.I))
    if not applicable:return {'status':'not_applicable','checked':False,'checks':[],'all_checks_passed':False}
    if claims:
        ids={s.get('id') for s in search.get('sources',[])}
        record('qualitative_claims_have_sources',all(c.get('source_id') in ids for c in claims))
        from src.recommendations.retrieval import topics_for
        requested=set(topics_for(query))
        # Bounded completeness checks complement contradiction rules. They do not
        # certify scientific truth merely because a keyword is present.
        coverage={
            'ph':(r'кислот|закис|acid|қышқыл',r'буфер|щ[её]лоч|buffer|alkalin|сілті'),
            'co_digestion':(r'состав|компонент|composition|component|құрам',r'завис|может|depends|may|мүмкін|тәуел'),
            'low_gas':(r'измер|проверь|measurement|check|өлшем|тексер',r'температур|temperature'),
        }
        for topic,patterns in coverage.items():
            if topic in requested:
                record('qualitative_coverage_'+topic,all(re.search(p,text,re.I) for p in patterns))
    if estimate:
        from src.advisor.estimation import time_claim_issues
        record('no_unverified_timed_methane_amount',not time_claim_issues(text,results['assess_substrate_potential']))
    source_ids={s.get('id') for s in search.get('sources',[]) if s.get('id')}
    explicit=results.get('explicit_calculations',{}).get('calculations',[])
    concept_requested=bool(re.search(r'объясни|что\s+такое|чем.{0,50}отлич|теоретическ|explain|what\s+is|difference|theoretical|түсіндір',query,re.I))
    calculation_only=bool(explicit and not concept_requested)
    if scoped_calculation and not concept_requested:
        reviewed=verify_results({k:v for k,v in results.items() if k!='reactor_capacity'})
        record('estimate_arithmetic_and_source_scope_checked',reviewed.get('all_checks_passed') is True)
        record('literature_estimate_not_measured_output',bool(re.search(r'литературн|literature|өлше',text,re.I)) if estimate=='LITERATURE_ESTIMATE' else True)
        record('estimate_not_claimed_as_measured_production',not bool(re.search(r'(?<!не )измеренная выработка\s*[:=]\s*\d',text,re.I)))
    elif process and not concept_requested:
        record('temperature_study_scope_available',bool(process.get('sources') or results.get('assess_process_evidence',{}).get('matched_temperature_experiments')) or process.get('discussion_temperature_c') is None)
    elif not calculation_only:
        record('retrieved_claim_source_identity',search.get('status') in {'ok','partial'} and bool(claims)
               and all(c.get('source_id') in source_ids for c in claims))
    else:
        verified=verify_results({'explicit_calculations':{'status':'ok','calculations':explicit}})
        record('explicit_arithmetic_verified',verified.get('status')=='ok' and verified.get('checked') is True)
        record('input_provenance_confirmed',all(all(isinstance(item,dict) and item.get('provenance')=='USER_CONFIRMED'
               for item in calc.get('inputs',{}).values()) and bool(calc.get('inputs')) for calc in explicit))
        measured_output_claim=any(not re.search(r'(?:не\s+(?:является\s+)?|not\s+(?:a\s+|the\s+)?)$',text[max(0,m.start()-35):m.start()],re.I)
            for m in re.finditer(r'измеренн\w*\s+(?:выработ\w*|выход)|measured\s+(?:reactor\s+)?(?:yield|output)',text,re.I))
        record('potential_not_measured_output',bool(re.search(r'потенциал|potential|әлеует',text,re.I))
               and not measured_output_claim and not bool(re.search(r'(?<!не )гарантир\w*\s+(?:выход|выработ)|(?<!not )guaranteed\s+(?:yield|output)',text,re.I)))
    assertions=scientific_assertions(text)
    if process:
        record('temperature_discussion_not_actuation',process.get('operation_authorized') is False and process.get('automatic_setpoint_c') is None)
    contradictions={a['rule'] for a in assertions if not a['passed']}
    record('no_known_scientific_contradiction',not contradictions)
    if not calculation_only and re.search(r'\bbmp\b|бмп',query,re.I):
        record('bmp_experimental_basis_explained',any(a['rule']=='bmp_experimental_basis_explained' and a['passed'] for a in assertions))
    if re.search(r'теоретическ|theoretical|теориялық',query,re.I):
        record('theoretical_composition_basis_explained',bool(re.search(r'состав|хпк|стехиометр|composition|stoichiometr|\bcod\b|құрам',text,re.I)))
    if re.search(r'\d+\s*(?:дн\w*|сут\w*|days?|күн\w*|тәулік\w*)',query,re.I):
        record('time_dependent_kinetics_explained',bool(re.search(r'кинетик|kinetic|скорост\w*.{0,25}(?:разлож|накоп)|rate.{0,25}(?:degrad|accumul)|(?:ыдырау|жиналу)\s+жылдам',text,re.I)))
        record('no_guaranteed_time_yield',not bool(re.search(r'(?<!не )гарантир\w*.{0,50}\d+\s*(?:дн|сут)|\bguarantees?\b.{0,50}\d+\s*days',text,re.I)))
    if re.search(r'кислород|oxygen|оттегі|метаноген',query,re.I):
        record('anaerobic_oxygen_condition_explained',bool(re.search(r'без\s+(?:свободн\w*\s+)?кислород|кислород\w*.{0,25}не\s+(?:треб|нуж)|не\s+(?:треб\w*|нуж\w*).{0,25}кислород|without\s+(?:free\s+)?oxygen|does\s+not\s+require\s+oxygen|оттегісіз|оттегі\w*.{0,20}қажет\s+емес',text,re.I)))
    passed=all(c['passed'] for c in checks)
    groups={'arithmetic':['explicit_arithmetic_verified','estimate_arithmetic_and_source_scope_checked'],'provenance':['input_provenance_confirmed','retrieved_claim_source_identity','literature_estimate_not_measured_output','estimate_not_claimed_as_measured_production'],
            'scientific_interpretation':['potential_not_measured_output','no_known_scientific_contradiction','no_guaranteed_time_yield','no_unverified_timed_methane_amount'],
            'completeness':['bmp_experimental_basis_explained','theoretical_composition_basis_explained','time_dependent_kinetics_explained','anaerobic_oxygen_condition_explained']}
    components={name:{'status':('passed' if all(c['passed'] for c in chosen) else 'failed') if chosen else 'not_applicable',
                      'failed_checks':[c['check'] for c in chosen if not c['passed']]}
                for name,names in groups.items() for chosen in [[c for c in checks if c['check'] in names]]}
    return {'status':'passed' if passed else 'failed','checked':True,'all_checks_passed':passed,'checks':checks,'components':components,
            'contradictions':sorted(contradictions),'assertions':assertions,
            'scope':'Reviewed-source identity and limited RU/KK/EN proposition, negation and target-scope rules; not exhaustive factual verification or biological validation.'}


def validate_synthesis(payload,evidence,results,state=None,new_batch=False,*,query='',quantity_audit=None):
    issues=[]
    if not isinstance(payload,dict):return ['invalid_response_object']
    required={'conclusion','explanation','limitations','next_question','evidence_ids','decision'}
    if set(payload)!=required:return ['invalid_response_schema']
    texts=[payload['conclusion'],payload['explanation'],payload['next_question'] or '']
    if not isinstance(payload['limitations'],list) or len(payload['limitations'])>3:return ['invalid_limitations_schema']
    texts+=payload['limitations']
    if any(not isinstance(t,str) for t in texts):return ['invalid_text_schema']
    if results.get('assess_substrate_potential',{}).get('estimation_mode'):
        from src.advisor.estimation import time_claim_issues
        issues.extend(time_claim_issues(' '.join(texts),results['assess_substrate_potential']))
    from src.agent.response_integrity import check_response
    issues.extend(check_response(payload))
    for text in texts:
        issues.extend(a['rule'] for a in scientific_assertions(text) if not a['passed'])
    if state is not None and state.advanced.get('farmer_consultation'):
        from src.advisor.catalog import matches
        known_materials={c['material'] for s in results.get('assess_substrate_potential',{}).get('scenarios',[]) if s.get('methane_m3') for c in s.get('components',[])}
        for text in texts:
            for clause in re.split(r'[.!?;\n]',text):
                if known_materials and re.search(r'потенциал\w*.{0,25}(?:не\s+определ[её]н|неизвестен|не\s+рассчитан)',clause,re.I) and not re.search(r'фактическ|реальн|установк|срок|точн|гарант',clause,re.I):
                    issues.append('computed_potential_incorrectly_reported_absent')
                if re.search(r'метан|газ',clause,re.I) and re.search(r'не\s+(?:был\s+)?(?:выработан|произвед[её]н)',clause,re.I):
                    issues.append('unsupported_actual_production_state')
                if re.search(r'затрат|цен\w*|тариф|прибыл|кинетик|\bcost|\bprice|\bprofit|\bkinetic',clause,re.I):continue
                if re.search(r'не\s+(?:учтен\w*|учтён\w*|рассмотрен\w*|рассчитан\w*)|not\s+(?:considered|calculated|assessed)',clause,re.I) and any(m['material'] in known_materials for m in matches(clause)):
                    issues.append('computed_material_incorrectly_reported_absent')
    if any(re.search(r'\b[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)+\b',re.sub(r'https?://[^\s\)\]]+','',t)) for t in texts):issues.append('internal_parameter_name_in_prose')
    if (results.get('assess_substrate_potential',{}).get('status')=='needs_input'
        and re.search(r'сколько.{0,80}(?:метан|биогаз)|how\s+much.{0,80}(?:methane|biogas)|қанша.{0,80}метан',query,re.I)
        and not (payload.get('next_question') or any('?' in t for t in texts))):
        issues.append('missing_input_clarification_omitted')
    economic_intents={'economic_comparison','market_prices','price_history','digestate_management'}
    if state is not None and not economic_intents.intersection(set(state.intents)|set(state.smart_goals)):
        if new_batch:
            economic_claim=r'выгод\w*|рентаб\w*|прибыл\w*|убыт\w*|стоим\w*|затрат\w*|доход\w*|окуп\w*|profit\w*|costs?\b|revenue\w*|payback\w*'
            if any(re.search(economic_claim,t,re.I) for t in texts):issues.append('unrequested_economic_analysis')
        else:
            # Harmless limits such as "profit is not established without costs"
            # may be relevant; reject an affirmative profitability verdict.
            from src.agent.autonomous import unconfirmed_profitability_claim
            if unconfirmed_profitability_claim(' '.join(texts)):issues.append('unrequested_economic_analysis')
    for text in texts:
        for sentence in re.split(r'(?<=[.!?])\s+|[;\n]',text):
            if (re.search(r'(?:ёмкост\w*|емкост\w*|вместимост\w*|capacity)',sentence,re.I)
                and re.search(r'не\s+влия\w*|does\s+not\s+affect|has\s+no\s+effect',sentence,re.I)
                and re.search(r'загруз\w*|loading|charge',sentence,re.I)
                and re.search(r'номинальн\w*|nominal',sentence,re.I)):
                issues.append('capacity_conclusion_from_nominal_only')
            if (re.match(r'\s*(?:(?:выход|об[ъеё]м|потенциал)\s+)?(?:общ\w*\s+)?(?:биогаз\w*|biogas)\b',sentence,re.I)
                and re.search(r'\d[.,\d]*\s*(?:м³|м3|m³|m3)\s*(?:CH[₄4]|метан|methane)',sentence,re.I)
                and not re.search(r'содерж|contains?|(?:потенциал|об[ъеё]м)\s+метан|methane\s+(?:potential|volume)',sentence,re.I)):
                issues.append('biogas_methane_scope_unclear')
    ids=payload['evidence_ids']
    if not isinstance(ids,list) or len(ids)>5 or any(not isinstance(i,str) or i not in evidence for i in ids):issues.append('unknown_evidence_reference')
    profile_search=results.get('search_substrate_profiles',{})
    local_only=(profile_search.get('live_search_performed') is False or any(
        dossier.get('live_search_performed') is False or dossier.get('search_scope')=='LOCAL_REVIEWED_CORPUS'
        for dossier in profile_search.get('dossiers',[])))
    if (profile_search.get('status') in {'ok','partial'} and local_only
            and any(not dossier.get('studies') for dossier in profile_search.get('dossiers',[]))):
        absence_claim=re.compile(
            r'\b(?:no|none|absence)\b.{0,90}\b(?:scientific\s+)?(?:literature|publications?|stud(?:y|ies)|data|evidence|profiles?)\b'
            r'|\b(?:literature|publications?|stud(?:y|ies)|data|evidence|profiles?)\b.{0,70}\b(?:do\s+not\s+exist|does\s+not\s+exist|are\s+absent|were\s+not\s+found)\b'
            r'|\b(?:нет|отсутств\w*|не\s+найден\w*|не\s+обнаруж\w*).{0,90}(?:научн\w*|литератур\w*|публикац\w*|исследован\w*|данн\w*|профил\w*)'
            r'|(?:научн\w*|литератур\w*|публикац\w*|исследован\w*|данн\w*|профил\w*).{0,70}(?:не\s+найден\w*|отсутств\w*|нет\b)',re.I)
        local_scope=re.compile(r'\b(?:reviewed\s+)?local\s+(?:catalog(?:ue)?|corpus|index|profile\s+database)\b|проверенн\w*.{0,30}локальн\w*.{0,25}(?:каталог\w*|корпус\w*|индекс\w*)|локальн\w*.{0,25}(?:каталог\w*|корпус\w*|индекс\w*)',re.I)
        absence_caveat=re.compile(r'\b(?:does\s+not|doesn.t|cannot|can.t)\s+(?:establish|prove|demonstrate|imply)\b|\b(?:не\s+доказыва\w*|не\s+означа\w*|не\s+свидетельству\w*)',re.I)
        for text in texts:
            for sentence in re.split(r'(?<=[.!?])\s+|[;\n]',text):
                if absence_claim.search(sentence) and not local_scope.search(sentence) and not absence_caveat.search(sentence):
                    issues.append('local_search_scope_overstated')
                    break
            if 'local_search_scope_overstated' in issues:break
    if state is not None and {'profile_lookup','methane_yield'}& (set(state.intents)|set(state.smart_goals)):
        literature_bmp={key for key,reference in evidence.items()
                        if key.endswith('.bmp') and reference.get('level')=='LITERATURE'}
        if literature_bmp and isinstance(ids,list) and not literature_bmp.intersection(ids):
            issues.append('available_literature_value_omitted')
    scenario_ids={s.get('id') for s in results.get('assess_substrate_potential',{}).get('scenarios',[])
                  if s.get('result_level')=='HYPOTHETICAL_SCENARIO'}
    selected_hypothetical=any(isinstance(evidence.get(key),dict)
                              and evidence[key].get('scenario') in scenario_ids
                              and evidence[key].get('level')=='SCENARIO_ASSUMPTION'
                              for key in ids if isinstance(key,str)) if isinstance(ids,list) else False
    measurement_claim=re.compile(
        r'(?:\bизмерения?\b.{0,50}\b(?:показыва\w*|свидетельств\w*|подтвержда\w*)\b.{0,100}\bиз\s+\d[\d.,]*\s*кг\b|'
        r'\bпо\s+(?:моим\s+)?измерениям\b.{0,80}\bиз\s+\d[\d.,]*\s*кг\b|'
        r'\bmeasurements?\b.{0,50}\b(?:show|indicate|confirm)\b.{0,100}\bfrom\s+\d[\d.,]*\s*kg\b|'
        r'\bmeasured\s+(?:batch\s+)?(?:yield|output|result|value)\b|'
        r'\bизмеренн\w*\s+(?:выход|результат|значени\w*)\b)',re.I)
    if selected_hypothetical and any(measurement_claim.search(text) for text in texts):
        issues.append('scenario_misrepresented_as_measurement')
    from src.agent.quantities9 import check
    searched=results.get('search_scientific_sources',{})
    source_urls={source.get('url') for source in searched.get('sources',[]) if source.get('url')} if searched.get('status') in {'ok','partial'} else set()
    def retain_unverified_link(match):
        link=match.group(0);bare=link.rstrip('.,;')
        return link[len(bare):] if bare in source_urls else link
    quantity_texts=[re.sub(r'https?://[^\s\)\]]+',retain_unverified_link,t) for t in texts]
    if isinstance(ids,list) and all(isinstance(i,str) for i in ids):issues.extend(check(quantity_texts,evidence,ids,state,query=query,audit=quantity_audit))
    if isinstance(ids,list) and all(isinstance(i,str) and i in evidence for i in ids):
        scenario_ids={s['id'] for s in results.get('assess_substrate_potential',{}).get('scenarios',[])}
        chosen={evidence[i]['scenario'] for i in ids if evidence[i]['scenario'] in scenario_ids}
        # Separate typed references keep their scenario identity. Merely showing
        # two studies side by side is not pooling them into one distribution.
        if len(chosen)>1 and results.get('assess_substrate_potential',{}).get('comparison_mode')!='alternatives' and any(re.search(r'единый диапазон|общий интервал|усредн[её]нн|pooled range|pooled mean',t,re.I) for t in texts):
            issues.append('incompatible_scenarios_must_not_be_merged')
        methane_ids={k for k in evidence if k.endswith('.methane')}
        if methane_ids and not methane_ids.intersection(ids) and (state is None or 'methane_yield' in state.intents):issues.append('computed_methane_omitted')
    if payload['decision'] not in {'not_established','conditionally_viable','not_viable','not_applicable'}:issues.append('unknown_decision')
    if payload['decision'] in {'conditionally_viable','not_viable'} and not results.get('evaluate_partial_economics',{}).get('profit_established'):
        issues.append('economic_decision_without_complete_confirmed_basis')
    from src.agent.autonomous import _unsupported_conclusions
    issues.extend(_unsupported_conclusions(' '.join(texts),results))
    if results.get('assess_process_evidence'):
        for sentence in re.split(r'[.!?;]|\b(?:но|однако|but|however)\b', ' '.join(texts),flags=re.I):
            if re.search(r'оптимальн|неоптимальн|оптимум|\boptimal\b|\boptimum\b',sentence,re.I) and not re.search(r'не\s+(?:установ|определ|подтвержд|доказ|проверен)|неизвест|нельзя|не\s+могу|не\s+обязательно|not\s+(?:established|validated|known|proven)|no\s+(?:validated|established|proven|known)\s+(?:temperature\s+)?optimum|cannot|unknown',sentence,re.I):
                issues.append('temperature_optimum_not_established')
    if results.get('evaluate_partial_economics') and not results['evaluate_partial_economics'].get('profit_established'):
        from src.agent.autonomous import unconfirmed_profitability_claim
        if unconfirmed_profitability_claim(' '.join(texts)):issues.append('unconfirmed_profitability_ranking')
    for text in texts:
        if re.search(r'(?<!не\s)гарантирован(?:ный\s+выход|но\s+получ)|(?:загрузка|установка)\s+безопасна|можно\s+безопасно\s+загрузить',text,re.I):issues.append('unsupported_guarantee_or_safety_claim')
    if len(' '.join(texts).split())>180:issues.append('response_too_long')
    return list(dict.fromkeys(issues))
