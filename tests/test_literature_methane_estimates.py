"""No model loading. Literature envelopes are not plant forecasts or measurements."""
import copy
import math
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from src.advisor.schemas import AdvisorRequest
from src.advisor.evidence_engine import scientific_request
from src.agent.verification9 import verify_results,verify_scientific_answer
from src.dashboard.firo_demo import build_result
from src.market.api import create_app
from src.market.store import Store

def request(**changes):
    data={'components':[{'id':'c1','material':'cattle_manure','quantity':142,'unit':'L'}],
          'estimation_mode':'LITERATURE_ESTIMATE','allow_literature_density':True,'allow_conditional_profiles':True,
          'reactor_total_volume_l':200,'target_days':30}
    data.update(changes)
    return AdvisorRequest.model_validate(data)

def known(result):return next(s for s in result['scenarios'] if s['potential_methane_l'])

def test_original_volume_has_conditional_potential_not_invented_30_day_yield():
    r=scientific_request(request());s=known(r);c=s['components'][0]
    assert s['potential_methane_l']==pytest.approx({'low':2922.95072,'high':4113.9956})
    assert c['wet_mass_kg']==pytest.approx({'low':143.846,'high':143.846})
    assert c['vs_mass_kg']==pytest.approx({'low':14.6147536,'high':16.4559824})
    assert s['time_yield']['methane_l'] is None and s['time_yield']['mode']=='INSUFFICIENT_EVIDENCE'
    assert s['estimation_mode']=='LITERATURE_ESTIMATE'
    assert c['source_conditions']['duration_days']==27
    assert c['properties_used']['density_kg_l']['source_id']==c['source']['id']
    assert c['properties_used']['vs_fraction_wet']['range']['low']==.1016
    assert s['engineering']['working_volume_l'] is None
    assert s['engineering']['operation_authorized'] is False
    assert verify_results({'assess_substrate_potential':r})['all_checks_passed']

def test_density_transfer_is_opt_in_and_never_leaks_into_measured_mode():
    for args in ({'allow_literature_density':False},{'estimation_mode':'MEASURED'},{'estimation_mode':None}):
        r=scientific_request(request(**args))
        assert all(s['methane_m3'] is None for s in r['scenarios'])

@pytest.mark.parametrize('field',['wet_mass_kg','vs_mass_kg','ts_mass_kg'])
def test_independent_verifier_rejects_mass_basis_corruption(field):
    r=scientific_request(request());known(r)['components'][0][field]['low']*=1.01
    assert verify_results({'assess_substrate_potential':r})['status']=='error'

def test_unreviewed_value_cannot_be_laundered_as_a_reviewed_literature_coefficient():
    r=scientific_request(request())
    known(r)['components'][0]['properties_used']['ts_fraction']['range']['low']=.1
    checked=verify_results({'assess_substrate_potential':r})
    assert any(c['check']=='literature_value_matches_reviewed_source_ts_fraction' and not c['passed'] for c in checked['checks'])

@pytest.mark.parametrize('unit,quantity',[('L',142),('mL',142000),('m3',.142)])
def test_volume_units_share_same_mass_basis(unit,quantity):
    r=scientific_request(request(components=[{'id':'c1','material':'cattle_manure','quantity':quantity,'unit':unit}]))
    assert known(r)['potential_methane_l']['high']==pytest.approx(4113.9956)

@pytest.mark.parametrize('extra',[{'bedding':'sawdust','material_state':'bedded'},{'decay_state':'composted'},{'material_state':'fresh_solid'}])
def test_incompatible_manure_form_never_borrows_slurry_density(extra):
    r=scientific_request(request(components=[{'id':'c1','material':'cattle_manure','quantity':142,'unit':'L',**extra}]))
    assert r['estimation_mode']=='INSUFFICIENT_EVIDENCE'
    assert all(s['methane_m3'] is None for s in r['scenarios'])

def measured(**changes):
    def m(v):return {'low':v,'high':v,'provenance':'MEASURED','evidence':'User laboratory measurement; calibration test fixture, not real plant data'}
    args={'estimation_mode':'MEASURED','process_temperature_c':37,
          'components':[{'id':'c1','material':'cattle_manure','quantity':10,'unit':'kg','data_mode':'MEASURED',
            'properties':{'density_kg_l':m(1),'ts_fraction':m(.1),'vs_fraction_of_ts':m(.8),'bmp_ml_g_vs':m(250),
            'gas_basis':{'temperature_k':273.15,'pressure_pa':101325,'moisture':'dry'}}}],
          'kinetic_evidence':{'rate_per_day':m(.1),'lag_days':m(0),'reference':'User independently validated batch first-order fit (TEST)',
                             'temperature_c':37,'applicable_to_batch':True}}
    args.update(changes);return request(**args)

def test_measured_inputs_derive_calculated_not_measured_gas_and_explicit_time_fit():
    r=scientific_request(measured());s=known(r)
    assert r['estimation_mode']=='MEASURED'
    assert s['potential_methane_l']==pytest.approx({'low':200,'high':200})
    assert s['time_yield']['methane_l']['low']==pytest.approx(200*(1-math.exp(-3)))
    assert s['result_provenance']['method']=='CALCULATED'
    assert s['time_yield']['result_method']=='CALCULATED'
    assert verify_results({'assess_substrate_potential':r})['all_checks_passed']
    tampered=copy.deepcopy(r);known(tampered)['time_yield']['methane_l']['low']=200
    assert verify_results({'assess_substrate_potential':tampered})['status']=='error'

def test_no_time_extrapolation_for_unmatched_temperature_or_missing_fit():
    for args in ({'process_temperature_c':30},{'kinetic_evidence':None}):
        assert known(scientific_request(measured(**args)))['time_yield']['methane_l'] is None

def test_real_endpoints_persist_source_mode_and_preserve_input_facts(tmp_path):
    with TestClient(create_app(Store(tmp_path/'estimate.sqlite3'),scheduler_enabled=False,firo_demo=True)) as client:
        response=client.post('/api/advisor/estimate',json=request().model_dump(mode='json'))
        assert response.status_code==200,response.text
        assert response.json()['verification']['all_checks_passed']
        with patch('src.agent.providers.JSONProvider.generate',side_effect=AssertionError('no inference')):
            run=client.post('/api/dashboard/firo-demo/runs',json={'case':'incomplete'}).json()
        assert run['estimate']['estimation_mode']=='LITERATURE_ESTIMATE'
        assert run['verification']['scientific']['checked'] is True
        restored=client.get('/api/dashboard/firo-demo/runs/'+run['id']).json()
        assert restored==run and restored['sources']
        internal=build_result('incomplete')
        for k in ('mass_kg','density_kg_l','vs_mass_kg','bmp_ml_ch4_g_vs'):
            assert k not in internal['state']['facts'] and k not in internal['state']['derived']
        assert all(word not in run['answer'] for word in ('source_id','profile_ids',"'duration_days'"))

def test_capacity_exceedance_remains_visible_not_authorized():
    r=scientific_request(request(reactor_total_volume_l=114,components=[{'id':'c1','material':'cattle_manure','quantity':470,'unit':'L'}]))
    assert known(r)['loading']['simultaneous_load_possible'] is False
    assert known(r)['engineering']['operation_authorized'] is False

def test_original_actual_chat_job_endpoint_preserves_literature_mode_and_history(tmp_path):
    from test_scientific_question_routing import _fake_runtime_llm,_run_job
    def rephrasing_model(*args,**kwargs):
        llm=_fake_runtime_llm(*args,**kwargs);provider=llm.providers[0];generate=provider.generate
        def rewritten(messages,schema):
            result=generate(messages,schema)
            if result.get('tool')=='estimate_methane_yield':result['arguments']={'query':'methane yield from cattle manure'}
            return result
        provider.generate=rewritten;return llm
    with patch('src.dashboard.api.HybridLLM',side_effect=rephrasing_model),TestClient(create_app(Store(tmp_path/'chat.sqlite3'),scheduler_enabled=False)) as client:
        _,sid,reply=_run_job(client,'У меня 142 литра коровьего навоза и реактор номинальным объёмом 200 литров. Сколько метана за 30 дней?','TEST_LITERATURE_CHAT')
        assert {'search_scientific_sources','estimate_methane_yield'} <= {t['tool'] for t in reply['tools']}
        assert '2922.95' in reply['answer'] and '4114' in reply['answer']
        assert 'INSUFFICIENT_EVIDENCE'==known(reply['technical_metadata']['scientific_details']['assess_substrate_potential'])['time_yield']['mode']
        assert 'LITERATURE_ESTIMATE' in reply['user_facing_answer']['modes']
        saved=client.get('/api/dashboard/chat/sessions/'+sid).json()
        assert saved['turns'][0]['reply']['answer']==reply['answer']
        assert reply['technical_metadata']['scientific_answer_verification']['status']=='passed'
        assert reply['technical_metadata']['scientific_details']['assess_substrate_potential']['target_days']==30

def test_small_context_preserves_authoritative_question_and_quantitative_scope():
    from src.advisor.estimation import model_context
    from src.agent.evidence9 import collect
    import json
    r=scientific_request(request());evidence,_=collect({'assess_substrate_potential':r})
    payload=model_context(r,'142 л навоза, реактор 200 л; выход за 30 дней?',evidence)
    assert len(json.dumps(payload,ensure_ascii=False))<4000
    assert payload['target_days']==30 and payload['verified_scenarios'][0]['time_yield'] is None
    assert all(key.endswith('.methane') for key in payload['evidence'])

@pytest.mark.parametrize('text',[
    'За 30 дней получится 4114 л CH4.',
    'За 30 дней ожидается 2922.95–4114 л CH4.',
    'За 30 дней образуется 150 л CH4, кинетика неизвестна.',
    'Выход метана за 30 дней составит 4.114 м³.',
])
def test_potential_cannot_be_reused_as_timed_yield(text):
    from src.advisor.estimation import time_claim_issues
    r=scientific_request(request())
    assert time_claim_issues(text,r)==['unsupported_time_resolved_methane_claim']
    checked=verify_scientific_answer(text,{'assess_substrate_potential':r},'Сколько метана за 30 дней?')
    assert checked['status']=='failed'

def test_correct_negative_timed_claim_retains_potential():
    from src.advisor.estimation import time_claim_issues
    r=scientific_request(request())
    assert time_claim_issues('Потенциал 4114 л CH4 не является выходом за 30 дней.',r)==[]
    assert time_claim_issues('У меня 142 л навоза, реактор 200 л, срок 30 дней.',r)==[]
    assert time_claim_issues('Условный потенциал метана 2,92–4,11 м³ для 142 л коровьего навоза, но не может быть привязан к 30 дням без дополнительных данных.',r)==[]
