"""Endpoint and verifier regressions with deterministic providers, never live inference."""
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from src.agent.providers import JSONProvider, HybridLLM
from src.agent.verification9 import verify_scientific_answer
from src.market.api import create_app
from src.market.store import Store
from evaluations.qwen4b_manual_chat import SCIENTIFIC_CASES
from test_scientific_question_routing import _fake_runtime_llm, _run_job, _wait_job


def test_a_scientific_routing_and_safe_public_source_representation():
    calls=[]
    def http(url,payload,*args,**kwargs):
        calls.append(payload)
        if len(calls)==1:
            content={'language':'ru','material_span':None}
        else:
            evidence=json.loads(payload['messages'][-1]['content'])
            assert evidence['reviewed_claims']
            assert all('id' not in c and 'source_id' not in c for c in evidence['reviewed_claims'])
            assert all('publication' in c and 'text' in c for c in evidence['reviewed_claims'])
            content={'conclusion':'BMP экспериментально измеряют в лабораторном испытании при заданных условиях.',
                'explanation':'Кинетика влияет на накопление метана. Лабораторные данные могут служить ориентиром, но их нельзя автоматически переносить на реактор без учёта его условий.',
                'limitations':[],'next_question':None,'evidence_ids':[],'decision':'not_applicable'}
        return {'message':{'content':json.dumps(content,ensure_ascii=False)},'done_reason':'stop','eval_count':30}
    def factory(*a,**k):
        return HybridLLM('offline',providers=[JSONProvider('offline',model='qwen3:4b-q4_K_M')],strict_model=True)
    with tempfile.TemporaryDirectory(dir=Path.cwd(),prefix='.tmp-v2-a-') as tmp:
        app=create_app(Store(Path(tmp)/'qa.sqlite3'),scheduler_enabled=False)
        with patch('src.dashboard.api.HybridLLM',side_effect=factory),patch('src.agent.providers.request_json',side_effect=http),TestClient(app) as client:
            _,_,reply=_run_job(client,SCIENTIFIC_CASES['A'][0],'TEST_V2_A')
            assert len(calls)==2
            assert reply['technical_metadata']['final_author']=='qwen_grounded_information'
            assert reply['technical_metadata']['scientific_answer_verification']['status']=='passed'
            assert [t['tool'] for t in reply['tools']]==['search_scientific_sources']


def test_b_and_c_real_dashboard_endpoint_with_deterministic_provider():
    with tempfile.TemporaryDirectory(dir=Path.cwd(),prefix='.tmp-v2-bc-') as tmp:
        app=create_app(Store(Path(tmp)/'qa.sqlite3'),scheduler_enabled=False)
        with patch('src.dashboard.api.HybridLLM',side_effect=_fake_runtime_llm),TestClient(app) as client:
            _,_,b=_run_job(client,SCIENTIFIC_CASES['B'][0],'TEST_V2_B')
            meta=b['technical_metadata'];assert '0.15' in b['answer']
            assert meta['verification']['status']=='ok'
            assert meta['scientific_answer_verification']['status']=='passed',meta['scientific_answer_verification']
            assert meta['scientific_answer_verification']['components']['arithmetic']['status']=='passed'
            assert 'TS и VS' not in b['answer']
            _,_,c=_run_job(client,SCIENTIFIC_CASES['C'][0],'TEST_V2_C')
            assert 'плотност' in c['answer'].lower() and 'кинетик' in c['answer'].lower()
            assert 'отдельный сценарий s2' not in c['answer'].lower()


def test_b_scientific_verifier_rejects_unconfirmed_input_and_bad_arithmetic():
    calc={'id':'explicit.methane_potential_m3','kind':'methane_potential_m3','value':0.15,'unit':'м³ CH₄','provenance':'CALCULATED_FROM_CONFIRMED',
          'inputs':{'vs_mass_kg':{'value':0.6,'unit':'kg VS','provenance':'USER_CONFIRMED'},
                    'bmp_ml_ch4_g_vs':{'value':250,'unit':'mL CH4/g VS','provenance':'USER_CONFIRMED'}}}
    text='Расчётный потенциал 0,15 м³ CH₄. Выход за срок зависит от кинетики.'
    result={'explicit_calculations':{'status':'ok','calculations':[calc]}}
    assert verify_scientific_answer(text,result,SCIENTIFIC_CASES['B'][0])['status']=='passed'
    assert verify_scientific_answer(text+' Это измеренная выработка реактора.',result,SCIENTIFIC_CASES['B'][0])['components']['scientific_interpretation']['status']=='failed'
    assert verify_scientific_answer(text+' Это не является измеренной выработкой реактора.',result,SCIENTIFIC_CASES['B'][0])['status']=='passed'
    calc['value']=0.5
    assert verify_scientific_answer(text,result,SCIENTIFIC_CASES['B'][0])['components']['arithmetic']['status']=='failed'
    calc['value']=0.15;calc['inputs']['vs_mass_kg']['provenance']='ASSUMED'
    assert verify_scientific_answer(text,result,SCIENTIFIC_CASES['B'][0])['components']['provenance']['status']=='failed'


def test_d_unambiguous_correction_survives_provider_failure_without_an_extra_call():
    with tempfile.TemporaryDirectory(dir=Path.cwd(),prefix='.tmp-v2-d-') as tmp:
        app=create_app(Store(Path(tmp)/'qa.sqlite3'),scheduler_enabled=False)
        with patch('src.dashboard.api.HybridLLM',side_effect=_fake_runtime_llm),TestClient(app) as client:
            _,sid,first=_run_job(client,SCIENTIFIC_CASES['D'][0],'TEST_V2_D_1')
            assert first['mode']=='deterministic_batch_confirmation' and first['technical_metadata']['final_author']=='confirmed_state'
            assert '800 л' in first['answer'] and 'reactor_total_volume_l' not in first['answer']
            snapshot=client.get(f'/api/dashboard/chat/sessions/{sid}').json()
            accepted=client.post(f'/api/dashboard/chat/sessions/{sid}/jobs',json={'message':SCIENTIFIC_CASES['D'][1],
                'request_id':'TEST_V2_D_2','expected_state_version':snapshot['state_version']})
            job=_wait_job(client,accepted.json()['id']); reply=client.get(job['result_reference']).json()['reply']
            assert '500 л' in reply['answer'] and '800 л' not in reply['answer']
            assert reply['memory']['facts']['quantity']['value']==500
            assert reply['mode']=='deterministic_parameter_correction'


def test_e_source_identifier_is_rejected_but_valid_public_title_is_not():
    from src.agent.verification9 import validate_synthesis
    from test_scientific_assertion_scope import draft
    assert 'internal_parameter_name_in_prose' in validate_synthesis(draft('Источник q4b_filer2019.'),{}, {})
    assert 'internal_parameter_name_in_prose' not in validate_synthesis(draft('Filer et al., Biochemical Methane Potential (2019).'),{}, {})
    sources={'search_scientific_sources':{'status':'ok','sources':[{'url':'https://example.org/paper_name'}]}}
    valid=validate_synthesis(draft('Статья https://example.org/paper_name.'),{},sources)
    assert 'internal_parameter_name_in_prose' not in valid and 'source_links_must_use_verified_sources' not in valid
    assert 'source_links_must_use_verified_sources' in validate_synthesis(draft('Статья https://example.org/unknown.'),{},sources)
