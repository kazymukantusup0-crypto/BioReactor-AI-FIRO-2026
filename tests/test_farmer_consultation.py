"""Farm questions reach the actual Chat job endpoint. No real LLM in these tests."""
import json
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from src.agent.dialogue_types import DialogueState
from src.agent.dialogue_memory import apply
from src.agent.nlu import extract
from src.agent import analytical
from src.agent.farmer_consultation import project,required_tools,compose
from src.agent.verification9 import verify_results
from src.market.store import Store
from src.market.api import create_app

QUESTION='Привет! У меня 78 литров жидкого свиного навоза и реактор объёмом 200 литров. Сколько получится метана, выгодно ли его перерабатывать и какую температуру выставить?'

def state_for(text,state=None):
    state=state or DialogueState();e=extract(text,state);s=apply(state,e);return s,e

def tools(s,text,store):
    data=analytical.context(s);data['query']=text
    result=analytical.execute('estimate_methane_yield',{'analytical_context':data},{},store)
    results={'assess_substrate_potential':result,'estimate_methane_yield':result}
    results['assess_process_evidence']=analytical.execute('assess_process_evidence',{'analytical_context':data},results,store)
    results['evaluate_partial_economics']=analytical.execute('evaluate_partial_economics',{'analytical_context':data},results,store)
    return results

def test_free_language_is_typed_and_decomposed_without_special_phrase_handler():
    s,e=state_for(QUESTION);p=project(s,e,QUESTION)
    assert p.substrate=='swine_manure' and p.feedstock_volume_l==78 and p.reactor_volume_l==200
    assert set(p.tasks)=={'methane','temperature','economics'}
    assert p.duration_days is None and p.temperature_c is None
    assert required_tools(p,s)==['search_scientific_sources','estimate_methane_yield','assess_process_evidence','evaluate_partial_economics']

@pytest.mark.parametrize('litres',[19,78,123.5])
def test_volumetric_solids_path_never_assigns_unknown_density_or_mass(tmp_path,litres):
    text=QUESTION.replace('78',str(litres));s,e=state_for(text);r=tools(s,text,Store(tmp_path/'r.sqlite3'))
    known=[x for x in r['assess_substrate_potential']['scenarios'] if x['methane_m3']]
    assert len(known)==3
    for row in known:
        assert row['wet_mass_kg'] is None and row['vs_mass_kg']['low']==pytest.approx(litres*.01631)
        c=row['components'][0];bmp=c['properties_used']['bmp_ml_g_vs']['range']['low']
        assert row['methane_m3']['low']==pytest.approx(litres*.01631*bmp/1000)
        assert row['time_yield']['days'] is None and row['time_yield']['methane_l'] is None
        assert 'density_kg_l' not in c['properties_used']
    assert verify_results(r)['all_checks_passed']
    assert all(k not in s.facts for k in ('mass_kg','density_kg_l','vs_mass_kg','bmp_ml_ch4_g_vs'))

def test_temperature_followup_preserves_batch_and_updates_only_applicable_scenarios(tmp_path):
    s,e=state_for(QUESTION);project(s,e,QUESTION)
    q='А если температура будет 25 °C?';s,e=state_for(q,s);p=project(s,e,q)
    assert p.feedstock_volume_l==78 and p.reactor_volume_l==200
    assert set(p.tasks)=={'methane','temperature','economics'}
    r=tools(s,q,Store(tmp_path/'r.sqlite3'));known=[x for x in r['assess_substrate_potential']['scenarios'] if x['methane_m3']]
    assert len(known)==1 and known[0]['components'][0]['source_conditions']['temperature_c']==25
    assert known[0]['methane_m3']['high']==pytest.approx(.41600286)

def test_composer_keeps_all_tasks_and_one_plain_question(tmp_path):
    s,e=state_for(QUESTION);project(s,e,QUESTION);r=tools(s,QUESTION,Store(tmp_path/'r.sqlite3'))
    sections,question,sources=compose(r,s)
    assert {'Оценка метана','Температура и энергия','Экономическая оценка'}<= {v['title'] for v in sections}
    answer=' '.join(s['body'] for s in sections)
    assert all(x not in answer for x in ('profile_ids','chae2008-swine','B_heat','s3','verifier'))
    assert 'неизвестные затраты не равны нулю' in answer.lower()
    assert '35 °C' in answer and 'выставить 35' not in answer
    assert question=='В каком регионе находится установка?' and sources

def test_heat_balance_uses_existing_si_engine_without_invented_parameters(tmp_path):
    from src.agent.farmer_consultation import temperature_options
    s,e=state_for(QUESTION);data=analytical.context(s)
    options=temperature_options(data,[])
    assert options['automatic_setpoint_c'] is None and options['operation_authorized'] is False
    assert all(v['heat_balance']['heating_input_kwh'] is None for v in options['options'])
    # Explicit TEST engineering case, not measurements or universal reactor values.
    data['decision']['reactor']={'heated_mass_kg':80,'heat_capacity_kj_kg_k':4,'initial_temperature_c':15,'ambient_temperature_c':15,
      'duration_days':2,'heat_loss_coefficient_w_k':1,'heater_efficiency':.8,'auxiliary_energy_kwh':.1,'heating_carrier':'electricity'}
    option=next(v for v in temperature_options(data,[])['options'] if v['temperature_c']==35)
    assert option['heat_balance']['initial_heating_kwh']==pytest.approx(80*4*20/3600/.8)
    assert option['heat_balance']['maintenance_heating_kwh']==pytest.approx(1*20*48/1000/.8)

def test_actual_chat_jobs_complete_all_parts_after_two_model_planning_actions(tmp_path):
    from test_scientific_question_routing import _fake_runtime_llm,_run_job
    with patch('src.dashboard.api.HybridLLM',side_effect=_fake_runtime_llm),TestClient(create_app(Store(tmp_path/'chat.sqlite3'),scheduler_enabled=False)) as client:
        _,sid,reply=_run_job(client,QUESTION,'TEST_FARM_MULTI')
        called={t['tool'] for t in reply['tools']}
        assert {'search_scientific_sources','estimate_methane_yield','assess_process_evidence','evaluate_partial_economics'}<=called
        assert reply['technical_metadata']['primary_evidence_unchecked']==[]
        assert len(reply['technical_metadata']['research_actions'])<=2
        assert len(reply['user_facing_answer']['sections'])>=4
        assert reply['pending_question'] and reply['answer'].count('?')<=1
        assert client.get('/api/dashboard/chat/sessions/'+sid).json()['turns'][0]['reply']['answer']==reply['answer']

def test_prepared_qa_cases_and_per_job_quota_do_not_remove_limits():
    from evaluations import qwen4b_manual_chat as qa
    from src.agent.providers import ProviderError
    events=[{'token_limit':128},{'token_limit':150},{'token_limit':150},{'token_limit':540}]
    ordinary=qa.LimitedProvider(events)
    with pytest.raises(ProviderError,match='four-call'):ordinary.generate([],{'properties':{}})
    # A new explicit two-turn experiment has its own bounded job quota.
    second=qa.LimitedProvider(events,call_offset=4)
    events.extend([{'token_limit':128},{'token_limit':150},{'token_limit':150},{'token_limit':540}])
    with pytest.raises(ProviderError,match='four-call'):second.generate([],{'properties':{}})
    assert max(map(len,qa.FARMER_CASES.values()))==2

def test_private_reference_presentation_changes_no_numeric_or_scientific_content():
    from src.agent.farmer_consultation import public_prose
    raw={'conclusion':'Метан: 0.416 м³ (сценарий s3), 0.495 м³ (s4). Это не гарантия.',
         'explanation':'','limitations':[],'next_question':None,'evidence_ids':['s3.methane'],'decision':'not_applicable'}
    changed,ids=public_prose(raw,{'assess_substrate_potential':{'scenarios':[{'id':'s3'},{'id':'s4'}]}})
    assert changed['conclusion']=='Метан: 0.416 м³, 0.495 м³. Это не гарантия.'
    assert changed['evidence_ids']==raw['evidence_ids'] and ids==['s3','s4']
    assert 's3' in raw['conclusion']

def test_existing_qa_accepts_arbitrary_utf8_question_without_prepared_case(tmp_path):
    from evaluations.qwen4b_manual_chat import read_message_file
    p=tmp_path/'question.txt';text='ә ғ қ ң ө ұ ү һ і: 23 л сырья, CH₄, 0,7 кг VS. Что делать?'
    p.write_bytes(text.encode('utf-8'));assert read_message_file(p)==text
    p.write_bytes(b'???????????????????')
    with pytest.raises(ValueError,match='INVALID_INPUT'):read_message_file(p)

def test_total_methane_cannot_be_relabelled_per_litre_or_per_day():
    from src.agent.quantities9 import check
    evidence={'gas':{'value':{'low':.84,'high':1.19},'unit':'м³ CH₄','level':'LITERATURE'}}
    for text in ['Метан: 0.84–1.19 м³/л.','Метан: 0.84 м³ CH4 per L.','Выход метана 0.84 м³/дней.']:
        assert check([text],evidence,['gas']),text
    assert check(['Потенциал метана 0.84–1.19 м³ CH4.'],evidence,['gas'])==[]

def test_mass_based_science_is_checked_in_a_compound_farming_answer(tmp_path):
    from src.agent.verification9 import verify_scientific_answer
    s,e=state_for('У меня 3 кг пищевых отходов. Сколько метана и выгодно ли?');project(s,e,'')
    data=analytical.context(s);science=analytical.scientific(data,Store(tmp_path/'r.sqlite3'))
    r={'assess_substrate_potential':science}
    result=verify_scientific_answer('Это расчётный литературный потенциал партии, не измеренный выход.',r,'Сколько метана и выгодно ли?')
    assert result['checked'] is True and result['status']=='passed'

def test_comparison_uses_both_explicit_inventory_alternatives_and_economics(tmp_path):
    q='Что выгоднее: 7 кг коровьего навоза или 7 кг пищевых отходов? Сравни метан и экономию.'
    from src.agent import advisor_bridge
    prior=DialogueState();e=extract(q,prior);e,plan=advisor_bridge.prepare(q,prior,e)
    s=advisor_bridge.commit(apply(prior,e),prior,plan,q,e);p=project(s,e,q)
    assert len(p.components)==2 and 'evaluate_partial_economics' in required_tools(p,s)
    data=analytical.context(s);store=Store(tmp_path/'r.sqlite3');science=analytical.scientific(data,store)
    assert verify_results({'assess_substrate_potential':science})['all_checks_passed']
    eco=analytical.economics(data,{'assess_substrate_potential':science},store)
    sections,question,_=compose({'assess_substrate_potential':science,'evaluate_partial_economics':eco},s)
    assert 'Экономическая оценка' in {v['title'] for v in sections}
    assert 'Сколько сырья' not in question
    from src.agent.evidence9 import collect
    from src.agent.farmer_consultation import synthesis_context
    results={'assess_substrate_potential':science,'evaluate_partial_economics':eco};evidence,_=collect(results)
    context=synthesis_context(results,s,q,evidence)
    assert any('Пищевые' in v['label'] for v in context['evidence'].values())
    assert any('Навоз' in v['label'] for v in context['evidence'].values())
    assert len(context['input_alternatives'])==2

def test_private_evidence_id_is_not_hidden_by_public_scenario_formatting():
    from src.agent.farmer_consultation import public_prose
    raw={'conclusion':'s2.methane: значение','explanation':'','limitations':[],'next_question':None,'evidence_ids':['s2.methane'],'decision':'not_applicable'}
    value,_=public_prose(raw,{'assess_substrate_potential':{'scenarios':[{'id':'s2'}]}})
    assert value['conclusion']==raw['conclusion']  # Existing verifier must reject it.

def test_scientific_limitations_are_sentences_not_character_lists(tmp_path):
    s,_=state_for(QUESTION);r=tools(s,QUESTION,Store(tmp_path/'r.sqlite3'))
    assert all(len(note)>1 for row in r['assess_substrate_potential']['scenarios'] for note in row['assumptions'])

def test_explanation_contract_hides_private_ids_but_keeps_typed_numbers(tmp_path):
    from src.agent.farmer_consultation import explanation_context,canonical_explanation
    from src.agent.evidence9 import collect
    from src.agent.verification9 import validate_synthesis
    s,e=state_for(QUESTION);project(s,e,QUESTION);results=tools(s,QUESTION,Store(tmp_path/'r.sqlite3'));evidence,_=collect(results)
    payload,refs=explanation_context(results,s,QUESTION,evidence)
    assert 's3.methane' not in json.dumps(payload,ensure_ascii=False)
    raw={'conclusion':'Это условный литературный потенциал, не измеренная выработка.','explanation':'Экономическую выгоду без полных расходов определить нельзя.'}
    candidate=canonical_explanation(raw,refs,results,s)
    assert candidate['decision']=='not_established' and candidate['evidence_ids']==refs
    assert validate_synthesis(candidate,evidence,results,s,query=QUESTION)==[]

def test_qualitative_contract_cannot_silently_publish_model_arithmetic():
    from src.agent.farmer_consultation import canonical_explanation
    from src.agent.providers import ProviderError
    with pytest.raises(ProviderError,match='numeric values'):
        canonical_explanation({'conclusion':'Получим 999 л.','explanation':''},[],{},DialogueState())

def test_contradictory_unknown_economics_cannot_negate_a_categorical_profit_claim():
    from src.agent.autonomous import unconfirmed_profitability_claim
    assert unconfirmed_profitability_claim('Переработка выгодна, но экономика не определена.')
    assert unconfirmed_profitability_claim('Переработка выгодна, прибыль не установлена.')
    assert not unconfirmed_profitability_claim('Нельзя определить, выгодна ли переработка без полных затрат.')


def test_default_region_does_not_become_confirmed_when_assumptions_are_projected(tmp_path):
    from src.agent.dialogue_types import Fact
    s,e=state_for(QUESTION);project(s,e,QUESTION)
    s.assumptions['market_region']=Fact(value='KZ-Karaganda',provenance='ASSUMED_FOR_SCENARIO',evidence='TEST default region',recorded_at='2020-01-01T00:00:00Z')
    results=tools(s,QUESTION,Store(tmp_path/'region.sqlite3'))
    assert results['evaluate_partial_economics']['region_confirmed'] is False
    assert all(not row['request']['region_confirmed'] for row in results['assess_substrate_potential']['scenarios'])
    data=analytical.context(s)
    data['input_provenance']['market_region']['provenance']='USER_CONFIRMED'
    assert analytical.market_region(data)==('KZ-Karaganda',True)


def test_verified_potential_and_unknown_production_are_different_claims(tmp_path):
    from src.agent.verification9 import validate_synthesis
    from src.agent.evidence9 import collect
    s,e=state_for(QUESTION);project(s,e,QUESTION);results=tools(s,QUESTION,Store(tmp_path/'claims.sqlite3'));evidence,_=collect(results)
    base={'conclusion':'Это литературный ориентир.','explanation':'','limitations':[],'next_question':None,'evidence_ids':[next(k for k in evidence if k.endswith('.methane'))],'decision':'not_established'}
    for text,issue in [('Метановый потенциал не определён.','computed_potential_incorrectly_reported_absent'),
                       ('Метан не выработан установкой.','unsupported_actual_production_state'),
                       ('Режим изучен, но не оптимум.','temperature_optimum_not_established')]:
        assert issue in validate_synthesis({**base,'explanation':text},evidence,results,s,query=QUESTION)
    for text in ['Фактический выход установки неизвестен.','Точный потенциал конкретной партии неизвестен.',
                 'Мезофильный вариант изучен, но оптимум не установлен.','Это не проверенный оптимум установки.']:
        assert validate_synthesis({**base,'explanation':text},evidence,results,s,query=QUESTION)==[],text


def test_temperature_only_question_does_not_demand_a_methane_batch_quantity():
    from src.agent.farmer_consultation import priority_question
    q='Какую температуру выбрать для жидкого свиного навоза?';s,e=state_for(q);project(s,e,q)
    assert 'температура сырья' in priority_question(s,{})


def test_model_task_semantics_complete_a_coordinated_request_without_new_facts():
    from src.agent.nlu import augment_requested_tasks
    from src.agent.dialogue_types import NLUProposal
    q='На ферме 52 л жидкого свиного навоза и реактор 180 л. Интересует метан, разумная температура и экономический смысл.'
    s,e=state_for(q);before=[v.model_dump() for v in e.entities]
    proposal=NLUProposal(language='ru',intents=['methane_yield','temperature_recommendation','economic_comparison'],material=None,material_evidence=None,entities=[])
    augment_requested_tasks(e,proposal,q)
    assert 'temperature_recommendation' in e.intents and 'reactor_management' in e.request_kinds
    assert [v.model_dump() for v in e.entities]==before
    # A model hint cannot create a topic absent from a conceptual question.
    concept=extract('Что такое TS и VS?',DialogueState())
    assert augment_requested_tasks(concept,proposal,'Что такое TS и VS?').intents==['scientific_explanation']


def test_compact_4b_nlu_has_task_semantics_within_existing_token_budget():
    from src.agent.providers import JSONProvider
    from src.agent.nlu import material_of
    p=JSONProvider('offline',model='qwen3:4b-q4_K_M');observed=[]
    _,span=material_of(QUESTION,DialogueState())
    def generate(messages,schema):
        observed.append((p.output_token_budget,schema))
        return {'language':'ru','material_span':span,'requested_tasks':['methane','temperature','economics']}
    p.generate=generate
    proposal=p.extract_dialogue(QUESTION,{})
    assert set(proposal.intents)=={'methane_yield','temperature_recommendation','economic_comparison'}
    assert observed[0][0]==128 and observed[0][1]['properties']['requested_tasks']['maxItems']==3
    assert not proposal.entities
