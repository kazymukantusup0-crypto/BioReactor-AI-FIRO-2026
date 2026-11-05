"""Execution fault fixtures only: no invented scientific or market observations."""
import json
import threading
import time
from datetime import timedelta
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from src.market.api import create_app
from src.market.store import Store
from src.market.domain import utcnow


@pytest.fixture
def app(tmp_path):return create_app(Store(tmp_path/'jobs.sqlite3'),scheduler_enabled=False)


def new(client):return client.post('/api/dashboard/chat/sessions',json={'mode':'no_llm','context':{},'conversation_version':'7'}).json()['id']


def submit(client,sid,rid='TEST_REQUEST',expected=None):
    body={'message':'TEST execution only','request_id':rid}
    if expected is not None:body['expected_state_version']=expected
    response=client.post(f'/api/dashboard/chat/sessions/{sid}/jobs',json=body)
    assert response.status_code==202,response.text
    return response.json()


def wait(client,jid):
    deadline=time.monotonic()+5
    while time.monotonic()<deadline:
        row=client.get('/api/dashboard/jobs/'+jid).json()
        if row['terminal']:return row
        time.sleep(.02)
    raise AssertionError(row)


def fixture_answer(agent,text):
    agent.registry.execute('get_reactor_status',{}, {},text)
    return {'mode':'TEST_FIXTURE','answer':'TEST execution result, no scientific claim','tools':[],
            'missing':[],'provider_status':[],'context_updated':True,'actuator_access':False,
            'memory':agent.state.model_dump(mode='json')}


def test_durable_result_idempotency_ack_and_state_version(app):
    with patch('src.agent.conversation.ConversationAgent.ask',autospec=True,side_effect=fixture_answer) as ask,TestClient(app) as client:
        sid=new(client);job=submit(client,sid,expected=0)
        same=submit(client,sid,expected=0)
        assert same['id']==job['id']
        assert wait(client,job['id'])['status']=='COMPLETED'
        assert ask.call_count==1
        result=client.get(job['result_reference']).json()
        assert result['reply']['answer'].startswith('TEST')
        assert client.post('/api/dashboard/jobs/'+job['id']+'/ack').status_code==200
        assert client.get(job['result_reference']).json()['reply']==result['reply']
        snapshot=client.get('/api/dashboard/chat/sessions/'+sid).json()
        assert snapshot['state_version']==1 and snapshot['turns'][0]['reply']['state_version']==1
        assert client.post(f'/api/dashboard/chat/sessions/{sid}/jobs',json={'message':'Different TEST content','request_id':'TEST_REQUEST'}).status_code==409


def test_constructor_error_is_terminal_and_persisted(app):
    with patch('src.dashboard.api.HybridLLM',side_effect=RuntimeError('TEST injected construction failure')),TestClient(app) as client:
        sid=client.post('/api/dashboard/chat/sessions',json={'mode':'offline','context':{},'conversation_version':'7'}).json()['id']
        job=submit(client,sid)
        assert wait(client,job['id'])['status']=='FAILED'
        assert client.get(job['result_reference']).json()['reply']['mode']=='error'
        assert submit(client,sid)['id']==job['id']


def test_queued_cancel_does_not_execute(app):
    with TestClient(app) as client:
        app.state.agent_runtime.stop();sid=new(client);job=submit(client,sid)
        assert client.post('/api/dashboard/jobs/'+job['id']+'/cancel').json()['status']=='CANCELLED'
        assert wait(client,job['id'])['attempt_count']==0


def test_restart_replays_committed_turn_without_second_execution(app):
    with patch('src.agent.conversation.ConversationAgent.ask',autospec=True,side_effect=fixture_answer) as ask,TestClient(app) as client:
        sid=new(client);job=submit(client,sid,expected=0);wait(client,job['id'])
        runtime=app.state.agent_runtime;runtime.stop()
        old=(utcnow()-timedelta(seconds=100)).isoformat()
        with app.state.store.connect() as con:
            con.execute("UPDATE agent_jobs SET status='FINALIZING',owner='dead-process',heartbeat_at=?,reply_json=NULL WHERE id=?",(old,job['id']))
        runtime.recover();runtime.start()
        done=wait(client,job['id'])
        assert done['status']=='COMPLETED' and done['attempt_count']==2
        assert ask.call_count==1
        assert client.get(job['result_reference']).json()['reply']['state_version']==1


def test_stale_expected_version_cannot_overwrite_current_state(app):
    with patch('src.agent.conversation.ConversationAgent.ask') as ask,TestClient(app) as client:
        runtime=app.state.agent_runtime;runtime.stop();sid=new(client);job=submit(client,sid,expected=0)
        with app.state.store.connect() as con:con.execute('UPDATE dashboard_sessions SET state_version=1 WHERE id=?',(sid,))
        runtime.start()
        assert wait(client,job['id'])['status']=='FAILED'
        ask.assert_not_called()


def test_grass_starts_new_task_before_llm_observes_memory():
    from src.agent.nlu import extract
    from src.agent.task_state import prepare
    from src.agent.dialogue_memory import from_context
    state=from_context({'material':'cattle_manure','material_volume_l':47,'reactor_volume_l':114});state.version='7'
    text='У меня 470 л свежей травы и реактор 840 л. Стоит ли производить биогаз?'
    extraction=extract(text,state);fresh,events,issues=prepare(text,state,extraction)
    assert not issues and any(e['type']=='NewBatch' for e in events)
    assert any(e.name=='material' and e.value=='grass' for e in extraction.entities)
    assert fresh.value('material') is None and fresh.task_history[-1]['facts']['quantity']['value']==47


def test_draft_revision_and_state_are_separate_from_confirmed_measurements(app):
    with TestClient(app) as client:
        sid=new(client);endpoint=f'/api/dashboard/chat/sessions/{sid}/draft'
        draft={'base_state_version':0,'expected_revision':0,'draft':{'TEST_local_edit':True}}
        assert client.put(endpoint,json=draft).json()['revision']==1
        assert client.put(endpoint,json=draft).status_code==409
        snapshot=client.get(f'/api/dashboard/chat/sessions/{sid}/scientific-state').json()
        assert 'TEST_local_edit' not in snapshot['confirmed_measurements']
        with app.state.store.connect() as con:con.execute('UPDATE dashboard_sessions SET state_version=1 WHERE id=?',(sid,))
        assert client.put(endpoint,json={**draft,'expected_revision':1}).status_code==409


def test_timeout_and_cancel_fence_cannot_commit_late_answer(app,monkeypatch):
    monkeypatch.setenv('BIOREACTOR_JOB_TIMEOUT','0.03')
    def slow(agent,text):
        time.sleep(.06)
        return fixture_answer(agent,text)
    with patch('src.agent.conversation.ConversationAgent.ask',autospec=True,side_effect=slow),TestClient(app) as client:
        sid=new(client);job=submit(client,sid)
        assert wait(client,job['id'])['status']=='TIMED_OUT'
        snapshot=client.get(f'/api/dashboard/chat/sessions/{sid}').json()
        assert snapshot['state_version']==0 and snapshot['turns'][0]['reply'] is None


def test_running_cancellation_preserves_previous_state_and_events(app):
    entered=threading.Event();release=threading.Event()
    def slow(agent,text):
        entered.set();release.wait(3)
        return fixture_answer(agent,text)
    with patch('src.agent.conversation.ConversationAgent.ask',autospec=True,side_effect=slow),TestClient(app) as client:
        sid=new(client);job=submit(client,sid);assert entered.wait(3)
        assert client.post('/api/dashboard/jobs/'+job['id']+'/cancel').status_code==200
        release.set();assert wait(client,job['id'])['status']=='CANCELLED'
        assert client.get(f'/api/dashboard/chat/sessions/{sid}').json()['state_version']==0
        events=client.get('/api/dashboard/jobs/'+job['id']+'/events').json()['events']
        assert events[0]['status']=='SUBMITTED' and events[-1]['status']=='CANCELLED'


def test_legacy_orphan_gets_terminal_diagnostics_without_replaying_old_input(app):
    with TestClient(app) as client:
        app.state.agent_runtime.stop();sid=new(client);old=(utcnow()-timedelta(seconds=400)).isoformat()
        with app.state.store.connect() as con:con.execute("INSERT INTO dashboard_turns(session_id,request_id,created_at,question,status) VALUES(?,?,?,?,'running')",(sid,'TEST_ORPHAN',old,'TEST interrupted legacy execution'))
        app.state.agent_runtime.recover()
        job=client.get(f'/api/dashboard/chat/sessions/{sid}/jobs').json()['jobs'][0]
        assert job['status']=='FAILED' and job['error_code']=='LEGACY_REQUEST_INTERRUPTED' and job['attempt_count']==0


def test_retired_worker_cannot_finish_new_owners_execution(app):
    with TestClient(app) as client:
        runtime=app.state.agent_runtime;runtime.stop();sid=new(client);job=submit(client,sid)
        with app.state.store.connect() as con:con.execute("UPDATE agent_jobs SET owner='NEW_OWNER',status='RUNNING' WHERE id=?",(job['id'],))
        runtime.finish(job['id'],'COMPLETED',reply={'mode':'TEST_FIXTURE'},owner='OLD_OWNER')
        current=runtime.get(job['id'])
        assert current['status']=='RUNNING' and current['owner']=='NEW_OWNER' and current['reply'] is None


def test_profile_evidence_is_retained_separately_from_confirmed_batch_values(app):
    def with_science(agent,text):
        from src.agent import analytical
        from src.agent.dialogue_memory import from_context
        agent.state=from_context({'material':'food_waste','mass_kg':5},agent.state.conversation_id)
        agent.state.task_id='TEST_SCOPED_SCIENTIFIC_TASK'
        data=analytical.context(agent.state);result=analytical.scientific(data)
        return {'mode':'TEST_EXECUTION_FIXTURE','answer':'TEST protocol fixture with real reviewed-profile calculations','tools':[],
                'context_updated':True,'memory':agent.state.model_dump(mode='json'),
                'technical_metadata':{'scientific_details':{'assess_substrate_potential':result}}}
    with patch('src.agent.conversation.ConversationAgent.ask',autospec=True,side_effect=with_science),TestClient(app) as client:
        sid=new(client);job=submit(client,sid);assert wait(client,job['id'])['status']=='COMPLETED'
        state=client.get(f'/api/dashboard/chat/sessions/{sid}/scientific-state').json()
        rows=state['scoped_result_fields']
        assert any(r['layer']=='literature' and r['source'].get('source',{}).get('id') for r in rows)
        assert any(r['field']=='s1.methane_m3' and r['provenance']=='CALCULATED_POTENTIAL_NOT_MEASURED_YIELD' for r in rows)
        assert 'bmp_ml_ch4_g_vs' not in state['confirmed_measurements']
