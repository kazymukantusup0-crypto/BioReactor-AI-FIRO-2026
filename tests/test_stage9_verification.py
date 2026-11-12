"""Mutation checks on real reviewed profiles, not fabricated observations."""
from copy import deepcopy
import pytest
from src.agent import analytical
from src.agent.evidence9 import collect,render_reference
from src.agent.verification9 import verify_results,validate_synthesis
from src.agent.tool_manifest import manifest,validate_arguments
from src.agent.providers import ProviderError

@pytest.fixture
def results():
    data={'facts':{'material':'food_waste','mass_kg':5,'reactor_total_volume_l':90},'components':[],'decision':{},'mode':'mixture','language':'ru'}
    return {'assess_substrate_potential':analytical.scientific(data)}

def response(ids):
    return {'conclusion':'Условный потенциал рассчитан.','explanation':'Это оценка, фактический выход не измерен.',
            'limitations':['Прибыль без полных затрат не установлена.'],'next_question':None,'evidence_ids':ids,'decision':'not_established'}

def test_independent_source_and_arithmetic_verifier(results):
    assert verify_results(results)['status']=='ok'
    damaged=deepcopy(results);damaged['assess_substrate_potential']['scenarios'][0]['components'][0]['methane_reference_m3']['low']*=1000
    assert verify_results(damaged)['status']=='error'
    damaged=deepcopy(results);damaged['assess_substrate_potential']['scenarios'][0]['components'][0]['source']['id']='UNRELATED_SOURCE'
    assert any(c['check']=='source_belongs_to_profile' and not c['passed'] for c in verify_results(damaged)['checks'])

def test_potential_from_properties_is_not_measured_gas(results):
    evidence,_=collect(results)
    assert evidence and all(e['level']!='MEASURED' for key,e in evidence.items() if key.endswith(('.methane','.vs','.biogas')))
    assert any('м³ CH₄' in render_reference(e) for e in evidence.values())

@pytest.mark.parametrize('claim',['Вы получите 999 кубометров.','Вы получите пять литров.','Источник https://invented.example/paper'])
def test_synthesis_cannot_rewrite_numbers_or_invent_links(results,claim):
    evidence,_=collect(results);answer=response(list(evidence)[:1]);answer['conclusion']=claim
    assert validate_synthesis(answer,evidence,results)

def test_unknown_reference_and_profit_decision_rejected(results):
    evidence,_=collect(results);answer=response(['NONEXISTENT']);answer['decision']='conditionally_viable'
    assert set(validate_synthesis(answer,evidence,results))>={'unknown_evidence_reference','economic_decision_without_complete_confirmed_basis'}

def test_valid_model_prose_can_select_immutable_reference(results):
    evidence,_=collect(results)
    assert validate_synthesis(response(list(evidence)[:1]),evidence,results)==[]

def test_manifest_is_read_only_and_arguments_cannot_insert_measurements():
    tools=manifest();assert len(tools)>=15 and all(t['read_only'] for t in tools)
    with pytest.raises(ProviderError):validate_arguments({'mass_kg':99})
    assert validate_arguments({'topics':['temperature']})=={'topics':['temperature']}


def test_separate_profile_references_are_not_a_pooled_distribution():
    data={'facts':{'material':'swine_manure','mass_kg':8},'components':[],'decision':{},'mode':'mixture','language':'ru'}
    results={'assess_substrate_potential':analytical.scientific(data)}
    evidence,_=collect(results);ids=[k for k in evidence if k.endswith('.methane')]
    assert len(ids)>1 and validate_synthesis(response(ids),evidence,results)==[]
    answer=response(ids);answer['explanation']='Это единый диапазон всех публикаций.'
    assert 'incompatible_scenarios_must_not_be_merged' in validate_synthesis(answer,evidence,results)


def test_independent_energy_check_detects_unit_scale_corruption(results,tmp_path):
    from src.market.store import Store
    data={'facts':{'material':'food_waste','mass_kg':5},'components':[],'decision':{},'mode':'mixture','language':'ru'}
    results['evaluate_partial_economics']=analytical.economics(data,results,Store(tmp_path/'no_prices.sqlite3'))
    assert verify_results(results)['status']=='ok'
    outputs=results['evaluate_partial_economics']['scenarios'][0]['analysis']['energy']['outputs']
    outputs['heat_only_kwh']['low']*=1000
    checks=verify_results(results)['checks']
    assert any(c['check']=='independent_energy_heat_only_kwh' and not c['passed'] for c in checks)


def test_grounded_input_and_rounded_output_are_allowed_but_wrong_units_are_not(results):
    from src.agent.dialogue_memory import from_context
    evidence,_=collect(results);answer=response(['s1.methane'])
    answer['conclusion']='Для 5 кг пищевых отходов условный потенциал около 0,32 м³ метана.'
    state=from_context({'material':'food_waste','mass_kg':5})
    assert validate_synthesis(answer,evidence,results,state)==[]
    answer['conclusion']='Получится 0,32 кг VS.'
    assert 'ungrounded_quantity_or_wrong_unit' in validate_synthesis(answer,evidence,results,state)


def test_methane_cannot_be_relabelled_total_biogas(results):
    evidence,_=collect(results);answer=response(['s1.methane'])
    answer['conclusion']='Общий биогаз составит 0,318 м³.'
    assert 'ungrounded_quantity_or_wrong_unit' in validate_synthesis(answer,evidence,results)


def test_current_temperature_does_not_establish_an_optimum():
    from src.agent.dialogue_memory import from_context
    state=from_context({'temperature_c':30});answer=response([])
    results={'assess_process_evidence':{'status':'ok'}}
    answer['explanation']='Температура 30°C не оптимальна.'
    assert 'temperature_optimum_not_established' in validate_synthesis(answer,{},results,state)
    answer['explanation']='Оптимальная температура не установлена по имеющимся данным.'
    assert validate_synthesis(answer,{},results,state)==[]


def test_empty_verification_is_not_a_passed_calculation():
    from src.agent.scientific_tools import verify
    value=verify_results({})
    assert value['status']=='not_applicable' and value['checked'] is False
    assert verify({})['status']=='insufficient_evidence'


@pytest.mark.parametrize('value',[
    {'assess_substrate_potential':{'status':'ok','scenarios':[]}},
    {'unknown_numeric_tool':{'status':'ok','methane_m3':1}},
    {'evaluate_partial_economics':{'status':'ok','scenarios':[]}},
])
def test_unchecked_result_does_not_get_verified_by_default(value):
    assert verify_results(value)['status']=='insufficient_evidence'


@pytest.mark.parametrize('value',[None,[],{'assess_substrate_potential':None},{'assess_substrate_potential':{'status':'ok','scenarios':'wrong type'}}])
def test_invalid_verifier_input_is_an_explicit_failure_not_an_exception(value):
    assert verify_results(value)['status']=='error'


@pytest.mark.parametrize('bounds',[{'low':float('nan'),'high':1},{'low':0,'high':float('inf')},{'low':-1,'high':1},{'low':2,'high':1}])
def test_invalid_physical_bounds_fail_independent_checks(results,bounds):
    damaged=deepcopy(results);damaged['assess_substrate_potential']['scenarios'][0]['methane_m3']=bounds
    assert verify_results(damaged)['status']=='error'


def test_unknown_profile_cannot_pass_source_verification(results):
    results['assess_substrate_potential']['scenarios'][0]['components'][0]['profile_id']='UNKNOWN_PROFILE'
    value=verify_results(results)
    assert value['status']=='error'
    assert any(c['check']=='profile_identity_and_form' and not c['passed'] for c in value['checks'])


def test_numeric_result_without_required_component_arithmetic_is_not_a_pass(results):
    del results['assess_substrate_potential']['scenarios'][0]['components'][0]['properties_used']['bmp_ml_g_vs']
    assert verify_results(results)['status']=='insufficient_evidence'


def test_manual_dimensional_reference_and_mass_capacity_unit_invariants():
    def compute(**facts):
        data={'facts':{'material':'food_waste','mass_kg':5,'ts_percent':20,'vs_percent':80,'vs_basis':'TS','bmp_ml_ch4_g_vs':400,**facts},
              'components':[],'decision':{},'mode':'mixture','language':'ru'}
        return analytical.scientific(data)['scenarios'][0]['methane_m3']
    expected=.32  # 5 kg wet * .20 TS/wet * .80 VS/TS * 400 L/kg VS / 1000 L/m³
    assert compute()==pytest.approx({'low':expected,'high':expected})
    assert compute(mass_kg=10)==pytest.approx({'low':2*expected,'high':2*expected})
    assert compute(quantity=5000,unit='g')==pytest.approx(compute())
    assert compute(reactor_total_volume_l=90)==pytest.approx(compute(reactor_total_volume_l=180))
    assert compute(mass_kg=1,ts_percent=100,vs_percent=100,bmp_ml_ch4_g_vs=1)==pytest.approx({'low':.001,'high':.001})


def test_hypothetical_vessel_reference_is_not_labelled_measured():
    from src.agent.dialogue_memory import from_context,fact
    state=from_context({'material':'food_waste','mass_kg':5,'reactor_volume_l':90})
    state.assumptions['reactor_total_volume_l']=fact(900,'L','ASSUMED_FOR_SCENARIO','TEST hypothetical vessel')
    science=analytical.scientific(analytical.context(state))
    evidence,_=collect({'assess_substrate_potential':science})
    vessel=next(r for key,r in evidence.items() if key.endswith('.vessel'))
    assert vessel['value']=={'low':900,'high':900}
    assert vessel['level']=='SCENARIO_ASSUMPTION'
    assert state.facts['reactor_total_volume_l'].value==90


@pytest.mark.parametrize('claim',[
    'Производство не выгодно из-за неизвестных затрат и отсутствия подтверждения цен на газ.',
    'Производство невыгодно.', 'Переработка убыточна.', 'Биогаз окупится.',
    'Production is unprofitable.', 'Production is profitable.',
])
def test_unknown_costs_cannot_establish_positive_or_negative_profitability(claim):
    answer=response([]);answer['conclusion']=claim
    assert 'unconfirmed_profitability_ranking' in validate_synthesis(answer,{}, {'evaluate_partial_economics':{'profit_established':False}})


@pytest.mark.parametrize('claim',[
    'Нельзя утверждать, что производство выгодно или убыточно.',
    'Прибыльность не установлена.', 'Profitability is unknown.',
    'Неизвестные расходы не позволяют определить прибыльность.',
])
def test_qualified_uncertainty_about_profitability_is_allowed(claim):
    answer=response([]);answer['conclusion']=claim
    assert not validate_synthesis(answer,{}, {'evaluate_partial_economics':{'profit_established':False}})


def test_internal_field_names_are_not_public_limitations(results):
    evidence,_=collect(results);answer=response(['s1.methane']);answer['limitations']=['inoculum_volume_l','dilution_water_l']
    assert 'internal_parameter_name_in_prose' in validate_synthesis(answer,evidence,results)


def test_methane_volume_cannot_have_a_total_biogas_subject(results):
    evidence,_=collect(results);answer=response(['s1.methane'])
    answer['conclusion']='Биогаз из пищевых отходов составит 0.31814 м³ CH₄.'
    assert 'biogas_methane_scope_unclear' in validate_synthesis(answer,evidence,results)
    answer['conclusion']='Биогаз содержит метан; потенциал метана составит 0.31814 м³ CH₄.'
    assert not validate_synthesis(answer,evidence,results)


def test_economic_question_can_display_relevant_energy_without_forcing_methane_prose(results,tmp_path):
    from src.agent.dialogue_memory import from_context
    from src.market.store import Store
    state=from_context({'material':'food_waste','mass_kg':5});state.intents=['economic_comparison']
    data={'facts':{'material':'food_waste','mass_kg':5},'components':[],'decision':{},'mode':'mixture','language':'ru'}
    results['evaluate_partial_economics']=analytical.economics(data,results,Store(tmp_path/'no_prices.sqlite3'))
    evidence,_=collect(results);answer=response(['s1.heat_only_kwh'])
    answer['conclusion']='Энергетическая оценка получена; для денежной оценки нет применимой цены.'
    assert not validate_synthesis(answer,evidence,results,state)
    state.intents.append('methane_yield')
    assert 'computed_methane_omitted' in validate_synthesis(answer,evidence,results,state)
