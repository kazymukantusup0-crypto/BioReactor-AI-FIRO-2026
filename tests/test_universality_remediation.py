"""General role binding, qualitative evidence and continuation through real Chat jobs."""
import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from src.agent.dialogue_types import DialogueState
from src.agent.dialogue_memory import apply
from src.agent.nlu import extract
from src.agent import analytical
from src.agent.runtime9 import requirements
from src.market.api import create_app
from src.market.store import Store
from test_scientific_question_routing import _fake_runtime_llm, _run_job, _wait_job


@pytest.mark.parametrize('text', [
    'Сосед предлагает 900 тенге за всю партию. Электронагрев по 24 тенге за кВт·ч.',
    'Электронагрев по 24 тенге за кВт·ч. Сосед предлагает 900 тенге за всю партию.',
    'Electricity costs 24 KZT/kWh; buyer offers 900 KZT for the whole batch.',
    'Цена партии 900 KZT, тариф электричества 24 KZT/kWh.',
])
def test_electricity_and_sale_are_independent_typed_roles(text):
    state=apply(DialogueState(),extract(text))
    assert state.value('batch_sale_price_kzt')==900
    assert state.value('electricity_tariff_kzt_per_kwh')==24
    assert state.value('sale_offer_amount')==900
    rows=analytical.explicit_calculations(state)['calculations']
    assert next(r for r in rows if r['kind']=='sale_gross_value_kzt')['value']==900
    assert analytical.context(state)['decision']['electricity_tariff_kzt_per_kwh']['low']==24


def test_tariff_only_cannot_create_or_overwrite_batch_offer():
    state=apply(DialogueState(),extract('Продам всю партию за 1200 KZT.'))
    state=apply(state,extract('Тариф электричества 31 KZT/kWh.',state))
    assert state.value('batch_sale_price_kzt')==1200
    assert state.value('electricity_tariff_kzt_per_kwh')==31
    empty=apply(DialogueState(),extract('Электроэнергия по 24 тенге за кВт·ч.'))
    assert empty.value('sale_offer_amount') is None


def test_unknown_price_scope_is_not_borrowed_from_another_quote():
    state=apply(DialogueState(),extract('Предлагают 900 тенге. Электроэнергия 24 тенге за кВт·ч.'))
    assert state.value('sale_offer_amount')==900
    assert state.value('batch_sale_price_kzt') is None
    assert state.value('sale_offer_scope') is None


def test_verifier_rejects_tariff_relabelled_as_batch_total():
    from src.agent.verification9 import verify_results
    state=apply(DialogueState(),extract('Продам всю партию за 900 KZT.'))
    result=analytical.explicit_calculations(state)
    row=result['calculations'][0]
    row['inputs']['sale_offer_amount']['unit']='KZT/kWh'
    assert verify_results({'explicit_calculations':result})['outcome']=='failed'


@pytest.mark.skip(reason="legacy agent, replaced by agent_v10")
def test_full_economic_engine_uses_user_scenario_without_claiming_verified_contract(tmp_path):
    from src.economics.decision_schemas import DecisionInputs
    from src.economics.valuation import resolve
    from src.advisor.schemas import AdvisorRequest
    state=apply(DialogueState(),extract('Продам всю партию за 900 KZT. Электричество 24 KZT/kWh.'))
    decision=DecisionInputs.model_validate(analytical.context(state)['decision'])
    request=AdvisorRequest(material='cattle_manure',mass_kg=10,region='KZ-Karaganda')
    p=resolve(Store(tmp_path/'price.db'),request,decision,'electricity')
    assert p['value']==24 and p['status']=='scenario'
    assert decision.batch_sale_price_kzt.low==900


def test_temperature_trajectory_keeps_current_not_previous():
    state=apply(DialogueState(),extract('Температура реактора упала с 35 до 25 °C, газообразование снизилось.'))
    assert state.value('temperature_c')==25
    assert state.value('previous_temperature_c')==35


def test_unknown_mixture_amount_does_not_block_qualitative_research():
    text='Хочу смешать коровий навоз и пищевые отходы. Объясни преимущества и риски совместного сбраживания; массы пока неизвестны.'
    e=extract(text); state=apply(DialogueState(),e)
    needs=requirements(state,text,e.request_kinds)
    assert 'search_scientific_sources' in needs


@pytest.mark.parametrize('question,needles', [
    ('Хочу смешать коровий навоз и пищевые отходы. Объясни преимущества и риски совместного сбраживания; массы неизвестны.', ['буфер','кислот','состав']),
    ('У меня 120 литров пищевых отходов и реактор 250 л. Каковы риски закисления и перегрузки органикой?', ['кислот','буфер','нагруз']),
    ('Температура реактора упала с 35 до 25 °C, газообразование снизилось. Что проверить безопасно?', ['температур','измер','газ']),
])
def test_qualitative_answers_use_sources_without_invented_batch_numbers(tmp_path,question,needles):
    with patch('src.dashboard.api.HybridLLM',side_effect=_fake_runtime_llm),TestClient(create_app(Store(tmp_path/'chat.db'),scheduler_enabled=False)) as client:
        _,sid,r=_run_job(client,question,'REG_QUAL')
        assert 'search_scientific_sources' in {t['tool'] for t in r['tools']}
        assert all(s in r['answer'].casefold() for s in needles)
        assert r['user_facing_answer']['sources']
        assert 'Численные результаты не прошли' not in r['answer']
        assert client.get('/api/dashboard/chat/sessions/'+sid).json()['turns'][0]['reply']['answer']==r['answer']


def test_price_correction_and_quantity_rescale_through_actual_chat(tmp_path):
    with patch('src.dashboard.api.HybridLLM',side_effect=_fake_runtime_llm),TestClient(create_app(Store(tmp_path/'chat.db'),scheduler_enabled=False)) as client:
        sid=client.post('/api/dashboard/chat/sessions',json={'mode':'offline','context':{},'conversation_version':'7'}).json()['id']
        replies=[]
        for i,msg in enumerate([
            'У меня 10 кг жидкого свиного навоза, TS 8%, VS 70% от TS, BMP 250 мл CH4/г VS. Сколько метана? Продам всю партию за 900 KZT, электричество 24 KZT/kWh.',
            'Исправление: масса партии 20 кг вместо 10 кг, температура 28 °C. Цена новой партии 1100 KZT. Тариф электричества 27 KZT/kWh. Пересчитай метан.',
        ]):
            job=client.post('/api/dashboard/chat/sessions/'+sid+'/jobs',json={'message':msg,'request_id':f'REG_MULTI_{i}','expected_state_version':i}).json()
            assert _wait_job(client,job['id'])['status']=='COMPLETED'
            replies.append(client.get(job['result_reference']).json()['reply'])
        state=client.get('/api/dashboard/chat/sessions/'+sid).json()['memory']
        assert state['facts']['batch_sale_price_kzt']['value']==1100
        assert state['facts']['electricity_tariff_kzt_per_kwh']['value']==27
        assert state['facts']['temperature_c']['value']==28
        assert state['facts']['quantity']['value']==20
        values=[]
        for r in replies:
            rows=next(t['result']['calculations'] for t in r['tools'] if t['tool']=='explicit_calculations')
            values.append(next(x['value'] for x in rows if x['kind']=='methane_potential_m3'))
        assert values[1]==pytest.approx(2*values[0])
