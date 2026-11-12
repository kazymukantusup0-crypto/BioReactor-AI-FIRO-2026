"""Result method is distinct from its inputs and from verification status."""
from copy import deepcopy
from unittest.mock import patch
from fastapi.testclient import TestClient

from src.advisor.mixing import evaluate
from src.advisor.schemas import AdvisorRequest, Component
from src.agent.verification9 import verify_results
from src.estimation.methane_potential import estimate
from src.estimation.schemas import EstimateRequest
from src.market.api import create_app
from src.market.store import Store
from test_scientific_question_routing import _fake_runtime_llm, _wait_job


def test_input_measurements_do_not_make_calculated_methane_measured():
    req=EstimateRequest(mass_kg=10,vs_mass_kg=1,bmp_ml_g_vs=250,gas_reference='TEST basis')
    result=estimate(req,[],{'id':'TEST','kwh_m3':9.97})
    assert result['result_level']=='CALCULATED'
    assert result['methane_potential_m3']['low']==0.25
    assert result['result_provenance']['method']=='CALCULATED'
    assert result['result_provenance']['inputs']['vs_mass_kg']['basis']=='USER_REPORTED'
    assert result['result_provenance']['verification']['status']=='NOT_PERFORMED'


def test_mixture_inputs_and_result_have_separate_origins():
    component=Component(id='a',material='food_waste',quantity=10,unit='kg',data_mode='MEASURED',
        properties={'vs_fraction_wet':{'low':.1,'high':.1,'provenance':'MEASURED'},
                    'bmp_ml_g_vs':{'low':250,'high':250,'provenance':'MEASURED'},
                    'gas_basis':{'temperature_k':273.2,'pressure_pa':101325,'moisture':'dry'}})
    row=evaluate(AdvisorRequest(components=[component],allow_literature_transfer=False))['components'][0]
    assert row['properties_used']['bmp_ml_g_vs']['provenance']=='MEASURED'
    assert row['result_level']=='CALCULATED'
    assert row['result_provenance']['method']=='CALCULATED'
    assert row['methane_reference_m3']['low']==.25


def test_verifier_rejects_calculated_scenario_claimed_measured():
    component={'id':'c','material':'food_waste','profile_id':None,'wet_mass_kg':{'low':10,'high':10},
        'vs_mass_kg':{'low':1,'high':1},'methane_reference_m3':{'low':.25,'high':.25},
        'methane_comparable_m3':{'low':.25,'high':.25},
        'properties_used':{'bmp_ml_g_vs':{'range':{'low':250,'high':250}}},'result_level':'CALCULATED'}
    scenario={'id':'s1','result_level':'MEASURED','methane_m3':{'low':.25,'high':.25},'components':[component],
              'engineering':{'operation_authorized':False,'status':'REQUIRES_REVIEW'}}
    result=verify_results({'assess_substrate_potential':{'scenarios':[scenario]}})
    assert result['status']=='error'
    assert any(c['check']=='calculated_methane_not_claimed_as_measured' and not c['passed'] for c in result['checks'])
    scenario=deepcopy(scenario);scenario['result_level']='CALCULATED';scenario['result_provenance']={'method':'MEASURED'}
    assert verify_results({'assess_substrate_potential':{'scenarios':[scenario]}})['status']=='error'


def test_chat_reported_bmp_is_not_automatically_measured():
    from src.agent.dialogue_types import DialogueState
    from src.agent.dialogue_memory import fact
    from src.agent.process_bridge import request_data
    state=DialogueState()
    state.facts['bmp_ml_ch4_g_vs']=fact(250,unit='mL CH4/g VS',evidence='TEST user value')
    assert request_data(state)['bmp_provenance']=='user_reported'


def test_dashboard_explicit_calculation_survives_history_reload(tmp_path):
    app=create_app(Store(tmp_path/'provenance.sqlite3'),scheduler_enabled=False)
    with patch('src.dashboard.api.HybridLLM',side_effect=_fake_runtime_llm),TestClient(app) as client:
        session=client.post('/api/dashboard/chat/sessions',json={'mode':'offline','context':{},'conversation_version':'7'}).json()
        prompt='Объясни BMP и рассчитай 0.6 кг VS × 250 мл CH4/г VS.'
        accepted=client.post(f"/api/dashboard/chat/sessions/{session['id']}/jobs",json={'message':prompt,'request_id':'provenance-explicit','expected_state_version':0})
        assert accepted.status_code==202
        job=_wait_job(client,accepted.json()['id']);assert job['status']=='COMPLETED'
        reply=client.get(job['result_reference']).json()['reply']
        assert '0.15' in reply['answer'] or '0,15' in reply['answer']
        assert 'измеренной выработкой' in reply['answer']
        snapshot=client.get(f"/api/dashboard/chat/sessions/{session['id']}").json()
        assert snapshot['turns'][0]['reply']==reply
        assert any(x['tool']=='explicit_calculations' for x in reply['tools'])
        tool=next(x for x in reply['tools'] if x['tool']=='explicit_calculations')
        row=next(x for x in tool['result']['calculations'] if x['kind']=='methane_potential_m3')
        assert row['result_provenance']['method']=='CALCULATED'
        assert row['result_provenance']['inputs']['vs_mass_kg']['provenance']=='USER_CONFIRMED'
        assert row['result_provenance']['verification']['status']=='NOT_PERFORMED'


def test_dashboard_literature_scenario_retains_result_provenance(tmp_path):
    app=create_app(Store(tmp_path/'literature.sqlite3'),scheduler_enabled=False)
    with patch('src.dashboard.api.HybridLLM',side_effect=_fake_runtime_llm),TestClient(app) as client:
        session=client.post('/api/dashboard/chat/sessions',json={'mode':'offline','context':{},'conversation_version':'7'}).json()
        prompt='У меня 5 кг пищевых отходов. Сколько метана?'
        accepted=client.post(f"/api/dashboard/chat/sessions/{session['id']}/jobs",json={'message':prompt,'request_id':'provenance-literature','expected_state_version':0})
        assert accepted.status_code==202
        job=_wait_job(client,accepted.json()['id']);assert job['status']=='COMPLETED'
        reply=client.get(job['result_reference']).json()['reply']
        tool=next(x for x in reply['tools'] if x['tool']=='assess_substrate_potential')
        scenario=next(x for x in tool['result']['scenarios'] if x.get('methane_m3') is not None)
        assert scenario['result_provenance']['method']=='CALCULATED'
        assert scenario['result_provenance']['sources']
        assert scenario['result_provenance']['assumptions']
        assert scenario['result_level']=='HYPOTHETICAL_SCENARIO'
        history=client.get(f"/api/dashboard/chat/sessions/{session['id']}").json()
        saved=next(x for x in history['turns'][0]['reply']['tools'] if x['tool']=='assess_substrate_potential')
        assert saved['result']['scenarios']==tool['result']['scenarios']
