"""State/engine regressions. Real-Qwen HTTP coverage is in evaluations/."""
import pytest
from src.agent.conversation import ConversationAgent
from src.agent.dialogue_types import NLUProposal
from src.agent.providers import HybridLLM, JSONProvider
from src.agent.mixture_parser import explicit_components

A='Привет, у меня есть 478 литров жидкого коровьего навоза и реактор вместимостью 700 литров. Мне лучше продать навоз или переработать и какую температуру ставить?'
B=A.replace('478','47').replace('700','114')


def agent():
    provider=JSONProvider('offline',model='qwen3:8b')
    provider.extract_dialogue=lambda text,memory: NLUProposal(language='ru',intents=[],material=None,material_evidence=None,entities=[])
    def action(question,facts,memory,history,observations,allowed_tools,final_only=False):
        required=memory.get('required_tool_checks',[])
        name=next((n for n in required if n in allowed_tools),None)
        if name:return {'action':'call_tool','tool':name,'arguments':{},'final':''}
        return {'action':'final','tool':None,'arguments':{},'final':'Доступные результаты проверены; лабораторный потенциал не является измерением вашей партии.'}
    provider.autonomous_action=action
    return ConversationAgent(research_enabled=True,llm=HybridLLM('offline',providers=[provider]))


def science(reply):
    return next(t['result'] for t in reply['tools'] if t['tool']=='assess_substrate_potential')


@pytest.mark.parametrize('text,quantity,capacity',[(A,478,700),(B,47,114),(A.lower().replace('.',''),478,700),(B.lower().replace('.',''),47,114)])
def test_reactor_quantity_is_not_absorbed_by_later_sale_material(text,quantity,capacity):
    cs=explicit_components(text)
    assert len(cs)==1 and cs[0].quantity==quantity and cs[0].material_state=='slurry'
    bot=agent();reply=bot.ask(text)
    assert bot.state.value('quantity')==quantity and bot.state.value('reactor_total_volume_l')==capacity
    assert bot.state.value('unit')=='L'
    assert reply['mode']=='qwen_autonomous_tools'
    assert {t['tool'] for t in reply['tools']} >= {'assess_substrate_potential','evaluate_partial_economics','assess_process_evidence'}
    assert science(reply)['scenarios'][0]['methane_m3']['low']>0
    assert all(s['engineering']['operation_authorized'] is False for s in science(reply)['scenarios'])
    assert any(e['type']=='NewBatch' for e in reply['technical_metadata']['diagnostic_events'])


def test_two_complete_requests_get_distinct_task_states_not_conflicts():
    bot=agent();first=bot.ask(A);old=bot.state.task_id;second=bot.ask(B)
    assert bot.state.task_id!=old
    assert bot.state.value('quantity')==47 and bot.state.value('reactor_total_volume_l')==114
    assert len(bot.state.mixture_components)==1 and bot.state.mixture_components[0]['quantity']==47
    assert bot.state.task_history[-1]['facts']['quantity']['value']==478
    assert science(second)['scenarios'][0]['methane_m3']['low']==pytest.approx(science(first)['scenarios'][0]['methane_m3']['low']*47/478)


def test_two_unlabelled_corrections_bind_previous_roles_and_update_inventory():
    bot=agent();bot.ask(A);task=bot.state.task_id
    reply=bot.ask('исправь: 47 литров и 114 литров')
    assert bot.state.task_id==task
    assert bot.state.value('quantity')==47 and bot.state.value('reactor_total_volume_l')==114
    assert bot.state.mixture_components[0]['quantity']==47
    assert science(reply)['scenarios'][0]['request']['components'][0]['quantity']==47
    assert any(e['type']=='UpdatedPreviousValue' for e in reply['technical_metadata']['diagnostic_events'])


def test_conditional_reactor_is_not_a_confirmed_measurement():
    bot=agent();bot.ask(A);reply=bot.ask('а если реактор 900 литров?')
    assert bot.state.value('reactor_total_volume_l')==700
    assert bot.state.assumptions['reactor_total_volume_l'].value==900
    assert science(reply)['scenarios'][0]['request']['reactor_total_volume_l']==900
    assert bot.state.mixture_components[0]['quantity']==478


@pytest.mark.parametrize('text',['У меня одновременно 47 и 478 литров одной и той же партии','У меня одновременно 47 литров и 478 литров одной и той же партии'])
def test_genuine_same_request_conflict_does_not_overwrite_previous_batch(text):
    bot=agent();bot.ask(A);reply=bot.ask(text)
    assert reply['error_type']=='ConflictingValuesInSameRequest'
    assert bot.state.value('quantity')==478
    assert not any(t['tool']=='assess_substrate_potential' for t in reply['tools'])
    assert '47' in reply['answer'] and '478' in reply['answer']


def test_new_question_after_dashboard_mixture_drops_stale_composition_and_costs():
    bot=agent();bot.state.mixture_components=[{'id':'old','material':'food_waste','quantity':5,'unit':'kg','material_state':'prepared_pulp'}]
    bot.state.advisor_inventory_mode='mixture';bot.state.decision_settings={'costs':{'transport':{'low':999,'high':999,'provenance':'USER_REPORTED'}}}
    reply=bot.ask(B)
    assert bot.state.advisor_inventory_mode=='single'
    assert len(bot.state.mixture_components)==1 and bot.state.mixture_components[0]['material']=='cattle_manure'
    assert not bot.state.decision_settings.get('costs')
    assert science(reply)['scenarios']


def test_form_correction_keeps_quantity_but_invalidates_composition():
    from src.agent.dialogue_memory import fact
    bot=agent();bot.ask(A)
    bot.state.facts['density_kg_l']=fact(.8)
    bot.state.mixture_components[0]['properties']={'density_kg_l':.8}
    bot.state.mixture_components[0]['reference_profile_id']='oliveira-rm1-2025-v1'
    reply=bot.ask('исправь: теперь навоз с подстилкой')
    assert bot.state.value('quantity')==478 and bot.state.value('material_state')=='bedded'
    assert bot.state.value('density_kg_l') is None
    assert bot.state.mixture_components[0]['properties']=={}
    assert bot.state.mixture_components[0]['reference_profile_id'] is None
    assert 'oliveira-rm1-2025-v1' not in [p for s in science(reply)['scenarios'] for p in s['profile_ids']]


def test_unlabelled_pair_without_context_is_ambiguous_not_conflicting():
    reply=agent().ask('исправь: 47 литров и 114 литров')
    assert reply['error_type']=='AmbiguousIntent'
    assert 'не противоречие' not in reply['answer'] or 'неоднозначность' in reply['answer']


def test_invalid_physical_value_has_explicit_type():
    reply=agent().ask('Реактор -90 литров')
    assert reply['error_type']=='InvalidPhysicalParameters'
    assert reply['tools']==[]


def test_real_working_volume_violation_still_reaches_engineering_tools():
    reply=agent().ask(B+' Рабочий объём 200 литров.')
    assert any(s['engineering']['status']=='PHYSICALLY_INFEASIBLE' for s in science(reply)['scenarios'])
