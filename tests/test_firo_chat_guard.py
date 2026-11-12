"""Deterministic resource/cancellation tests; never load an actual model."""
import copy
import threading
from unittest.mock import Mock,patch
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from src.agent.cancellation import CancellationSignal,ExecutionStopped
from src.dashboard.firo_demo import guarded_chat
from src.market.api import create_app
from src.market.store import Store
from test_farmer_consultation import QUESTION
from test_scientific_question_routing import _fake_runtime_llm,_run_job,_wait_job


def sample(ram=8000):
    return {'free_ram_mib':ram,'commit':{'commit_headroom_mib':20000},
            'gpu':{'temperature_c':55,'vram_total_mib':8192,'vram_used_mib':600,
                   'hw_thermal_slowdown':'Not Active','sw_thermal_slowdown':'Not Active'},
            'api_version':{'version':'TEST'},'running_models':[]}


@pytest.fixture
def resources(monkeypatch,tmp_path):
    monkeypatch.setattr('src.dashboard.firo_demo.CHAT_AUDIT_DIR',tmp_path/'TEST_AUDIT')
    from evaluations import qwen4b_manual_chat as qa
    notification=Mock();notification.low.return_value=False
    monkeypatch.setattr(qa,'WindowsLowMemory',lambda:notification)
    read=Mock(return_value=sample());monkeypatch.setattr(qa.telemetry,'sample',read)
    monkeypatch.setattr(qa,'active_ollama_connections',lambda:[])
    monkeypatch.setattr(qa,'foreign_ollama_clients',lambda:[])
    unload=Mock(return_value={'status':'UNLOADED','elapsed_seconds':0.01})
    monkeypatch.setattr(qa,'unload_target_if_uncontended',unload)
    return qa,notification,read,unload


def fake_provider(events):
    provider=_fake_runtime_llm().providers[0];provider.model='TEST deterministic provider, not Qwen'
    original=provider.generate
    def generate(messages,schema):
        events.append({'phase':'TEST_ONLY','status':'ok'})
        if 'conclusion' in schema.get('properties',{}):
            return {'conclusion':'Это литературный ориентир, не измеренный выход.','explanation':'Без полных затрат прибыль не установлена.'}
        return original(messages,schema)
    provider.generate=generate
    return provider


def test_blocked_admission_uses_tools_without_loading_any_model(resources,tmp_path):
    qa,notification,read,unload=resources;read.return_value=sample(6000)
    with patch.object(qa,'LimitedProvider',side_effect=AssertionError('Must not instantiate model')),TestClient(create_app(Store(tmp_path/'blocked.sqlite3'),scheduler_enabled=False,firo_demo=True)) as client:
        _,sid,reply=_run_job(client,QUESTION,'TEST_BLOCKED_4B')
        control=reply['technical_metadata']['experimental_qwen4b']
        assert control['status']=='blocked' and control['admission_issues']==['ram_limit']
        assert control['limits']['admission_ram_mib']==6656
        assert '6000.0 MiB' in reply['answer'] and '6656 MiB' in reply['answer']
        assert '416' in reply['answer'] and reply['tools']
        assert client.get('/api/dashboard/chat/sessions/'+sid).json()['turns'][0]['reply']['answer']==reply['answer']
    unload.assert_not_called();notification.close.assert_called_once()


def test_unload_and_metrics_are_persisted_before_chat_commit(resources,tmp_path):
    qa,notification,read,unload=resources
    with patch.object(qa,'LimitedProvider',side_effect=fake_provider),TestClient(create_app(Store(tmp_path/'chat.sqlite3'),scheduler_enabled=False,firo_demo=True)) as client:
        _,sid,reply=_run_job(client,QUESTION,'TEST_GUARDED_4B')
        guard=reply['technical_metadata']['experimental_qwen4b']
        assert guard['status']=='completed' and guard['provider_calls']
        assert guard['unload']['status']=='UNLOADED'
        assert client.get('/api/dashboard/chat/sessions/'+sid).json()['turns'][0]['reply']['technical_metadata']['experimental_qwen4b']==guard
    unload.assert_called_once();notification.close.assert_called_once()


def test_runtime_memory_violation_cancels_signal_and_releases_target(resources):
    qa,notification,read,unload=resources
    read.side_effect=[sample(),sample(3000),sample()]
    signal=CancellationSignal()
    with guarded_chat(signal) as (llm,guard):
        guard['provider_calls'].append({'phase':'TEST_ONLY'})
        stopped=threading.Event();signal.register(stopped.set)
        assert stopped.wait(3)
        assert signal.cancelled and 'ram_limit' in guard['stop_reason']
    unload.assert_called_once()


def test_cancel_closes_active_job_and_no_late_answer_commits(resources,tmp_path):
    qa,notification,read,unload=resources;entered=threading.Event()
    def waiting_provider(events):
        p=fake_provider(events)
        def wait(messages,schema):
            events.append({'phase':'TEST_ONLY'});entered.set()
            stopped=threading.Event();unregister=p.cancellation_signal.register(stopped.set)
            try:
                assert stopped.wait(5)
                p.cancellation_signal.throw_if_cancelled()
            finally:unregister()
            raise AssertionError('Late reply must never commit')
        p.generate=wait;return p
    with patch.object(qa,'LimitedProvider',side_effect=waiting_provider),TestClient(create_app(Store(tmp_path/'cancel.sqlite3'),scheduler_enabled=False,firo_demo=True)) as client:
        sid=client.post('/api/dashboard/chat/sessions',json={'mode':'offline','conversation_version':'7'}).json()['id']
        job=client.post(f'/api/dashboard/chat/sessions/{sid}/jobs',json={'message':QUESTION,'request_id':'TEST_CANCEL_4B'}).json()
        assert entered.wait(5)
        client.post('/api/dashboard/jobs/'+job['id']+'/cancel')
        assert _wait_job(client,job['id'])['status']=='CANCELLED'
        assert client.get(job['result_reference']).json()['reply'] is None
        assert client.get('/api/dashboard/chat/sessions/'+sid).json()['turns'][0]['reply'] is None
        assert client.get('/health').status_code==200
    unload.assert_called_once()


def test_guard_serializes_model_scopes_and_closes_even_on_exception(resources):
    qa,notification,read,unload=resources
    with pytest.raises(ValueError,match='TEST'):
        with guarded_chat(CancellationSignal()):
            with pytest.raises(HTTPException) as exc:
                with guarded_chat(CancellationSignal()):pass
            assert exc.value.status_code==409
            raise ValueError('TEST')
    with guarded_chat(CancellationSignal()):pass


def test_production_factory_and_no_llm_are_unchanged(resources,tmp_path):
    with patch('src.dashboard.firo_demo.guarded_chat',side_effect=AssertionError('No experimental scope')),patch('src.dashboard.api.HybridLLM',side_effect=_fake_runtime_llm),TestClient(create_app(Store(tmp_path/'production.sqlite3'),scheduler_enabled=False)) as client:
        _run_job(client,QUESTION,'TEST_PRODUCTION_UNCHANGED')


def test_experimental_no_llm_still_runs_shared_tools_without_resource_probe(tmp_path):
    with patch('src.dashboard.firo_demo.guarded_chat',side_effect=AssertionError('No model requested')),TestClient(create_app(Store(tmp_path/'no_llm.sqlite3'),scheduler_enabled=False,firo_demo=True)) as client:
        sid=client.post('/api/dashboard/chat/sessions',json={'mode':'no_llm','conversation_version':'7'}).json()['id']
        job=client.post(f'/api/dashboard/chat/sessions/{sid}/jobs',json={'message':QUESTION,'request_id':'TEST_NO_MODEL'}).json()
        assert _wait_job(client,job['id'])['status']=='COMPLETED'
        reply=client.get(job['result_reference']).json()['reply']
        assert '416' in reply['answer'] and 'experimental_qwen4b' not in reply['technical_metadata']


def test_experimental_legacy_sync_route_cannot_bypass_cancellation_guard(tmp_path):
    with TestClient(create_app(Store(tmp_path/'legacy.sqlite3'),scheduler_enabled=False,firo_demo=True)) as client:
        sid=client.post('/api/dashboard/chat/sessions',json={'mode':'offline','conversation_version':'7'}).json()['id']
        response=client.post(f'/api/dashboard/chat/sessions/{sid}/messages',json={'message':QUESTION,'request_id':'TEST_LEGACY_GUARD'})
        assert response.status_code==409
        assert client.get('/api/dashboard/chat/sessions/'+sid).json()['turns']==[]

@pytest.mark.parametrize('resource,expected',[(True,'RESOURCE_GUARD_STOP'),(False,'EXECUTION_INTERRUPTED')])
def test_internal_stop_is_not_mislabelled_as_user_cancel(tmp_path,resource,expected):
    app=create_app(Store(tmp_path/'reason.sqlite3'),scheduler_enabled=False)
    def interrupted(sid,message,rid,control,version):
        if resource:
            with app.state.store.connect() as con:
                con.execute("INSERT INTO agent_job_events(job_id,created_at,status,details_json) VALUES(?,?,'RESOURCE_STOP',?)",(control.job['id'],'TEST','{"reasons":["TEST_TELEMETRY_FAILURE"]}'))
        raise ExecutionStopped('execution_interrupted')
    app.state.agent_runtime.execute=interrupted
    with TestClient(app) as client:
        sid=client.post('/api/dashboard/chat/sessions',json={'mode':'offline','conversation_version':'7'}).json()['id']
        job=client.post(f'/api/dashboard/chat/sessions/{sid}/jobs',json={'message':QUESTION,'request_id':'TEST_STOP_REASON'}).json()
        final=_wait_job(client,job['id'])
        assert final['status']=='CANCELLED' and final['error_code']==expected
        assert final['cancel_requested']==0
