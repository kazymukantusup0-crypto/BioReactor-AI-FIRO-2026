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
