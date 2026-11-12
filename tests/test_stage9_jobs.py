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
        assert done['status']=='COMPLETED' and done['attempt_count']==1
        assert ask.call_count==1
        assert client.get(job['result_reference']).json()['reply']['state_version']==1


def test_last_attempt_crash_after_commit_restores_result_instead_of_timeout(app):
    with patch('src.agent.conversation.ConversationAgent.ask',autospec=True,side_effect=fixture_answer) as ask,TestClient(app) as client:
        sid=new(client);job=submit(client,sid,expected=0);wait(client,job['id'])
        runtime=app.state.agent_runtime;runtime.stop()
        saved=client.get(job['result_reference']).json()['reply']
        old=(utcnow()-timedelta(seconds=100)).isoformat()
        with app.state.store.connect() as con:
            con.execute("UPDATE agent_jobs SET status='FINALIZING',current_stage='persisted',owner='dead-process',heartbeat_at=?,attempt_count=2,reply_json=NULL WHERE id=?",(old,job['id']))
        runtime.recover()
        restored=runtime.get(job['id'])
        assert restored['status']=='COMPLETED' and restored['reply']==saved
        assert ask.call_count==1
        assert client.get(f'/api/dashboard/chat/sessions/{sid}').json()['state_version']==1


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


def test_job_cancel_aborts_active_provider_and_repeated_cancel_cannot_save_late_reply(app):
    from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
    from src.agent.providers import request_json
    entered=threading.Event();client_closed=threading.Event();late_reply_attempted=threading.Event();requests=[]
    class WaitingProvider(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers.get('Content-Length','0')));requests.append(self.path);entered.set()
            try:self.connection.recv(1)
            except OSError:pass
            client_closed.set();late_reply_attempted.set()
            try:
                body=b'{"message":{"content":"{\\"late\\":true}"}}'
                self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body);self.wfile.flush()
            except OSError:pass
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),WaitingProvider);server.daemon_threads=True
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    def wait_on_provider(agent,text):
        request_json(f'http://127.0.0.1:{server.server_port}/ollama',{},timeout=10,
                     cancellation=agent.cancellation_signal)
        return fixture_answer(agent,text)
    try:
        with patch('src.agent.conversation.ConversationAgent.ask',autospec=True,side_effect=wait_on_provider) as ask,TestClient(app) as client:
            sid=new(client);request_id='TEST_CANCEL_HTTP';job=submit(client,sid,request_id)
            assert entered.wait(3)
            first=client.post('/api/dashboard/jobs/'+job['id']+'/cancel')
            second=client.post('/api/dashboard/jobs/'+job['id']+'/cancel')
            assert first.status_code==200 and second.status_code==200
            assert client_closed.wait(2)
            assert wait(client,job['id'])['status']=='CANCELLED'
            duplicate=client.post(f'/api/dashboard/chat/sessions/{sid}/jobs',json={'message':'TEST execution only','request_id':request_id})
            assert duplicate.status_code==202 and duplicate.json()['id']==job['id']
            assert ask.call_count==1 and requests==['/ollama'] and late_reply_attempted.is_set()
            result=client.get(f'/api/dashboard/jobs/{job["id"]}/result').json()
            snapshot=client.get(f'/api/dashboard/chat/sessions/{sid}').json()
            assert result['reply'] is None and snapshot['state_version']==0 and snapshot['turns'][0]['reply'] is None
    finally:server.shutdown();server.server_close();thread.join(1)


def test_job_ownership_loss_cancels_active_provider_socket(app):
    from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
    from src.dashboard.jobs import Control,ExecutionStopped
    from src.agent.providers import request_json
    entered=threading.Event();client_closed=threading.Event();outcome=[]
    class WaitingProvider(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers.get('Content-Length','0')));entered.set()
            try:self.connection.recv(1)
            except OSError:pass
            client_closed.set()
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),WaitingProvider);server.daemon_threads=True
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    def call(signal):
        try:outcome.append(request_json(f'http://127.0.0.1:{server.server_port}/ownership',{},timeout=10,cancellation=signal))
        except Exception as exc:outcome.append(exc)
    try:
        with TestClient(app) as client:
            runtime=app.state.agent_runtime;runtime.stop();sid=new(client);job=submit(client,sid)
            with app.state.store.connect() as con:
                con.execute("UPDATE agent_jobs SET status='RUNNING',current_stage='running',owner='OWNER_A' WHERE id=?",(job['id'],))
            control=Control(runtime,runtime.get(job['id']),'OWNER_A')
            request_thread=threading.Thread(target=call,args=(control.cancellation,),daemon=True);request_thread.start()
            assert entered.wait(2)
            with app.state.store.connect() as con:con.execute("UPDATE agent_jobs SET owner='OWNER_B' WHERE id=?",(job['id'],))
            with pytest.raises(ExecutionStopped,match='execution_ownership_lost'):control.check()
            request_thread.join(2)
            assert not request_thread.is_alive() and client_closed.wait(1)
            assert len(outcome)==1 and isinstance(outcome[0],ExecutionStopped)
            result=client.get(f'/api/dashboard/jobs/{job["id"]}/result').json()
            assert result['reply'] is None
    finally:server.shutdown();server.server_close();thread.join(1)


def test_job_deadline_cancels_active_provider_socket(app):
    from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
    from src.dashboard.jobs import Control,ExecutionStopped
    from src.agent.providers import request_json
    entered=threading.Event();client_closed=threading.Event();outcome=[]
    class WaitingProvider(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers.get('Content-Length','0')));entered.set()
            try:self.connection.recv(1)
            except OSError:pass
            client_closed.set()
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),WaitingProvider);server.daemon_threads=True
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    def call(signal):
        try:outcome.append(request_json(f'http://127.0.0.1:{server.server_port}/deadline',{},timeout=10,cancellation=signal))
        except Exception as exc:outcome.append(exc)
    try:
        with TestClient(app) as client:
            runtime=app.state.agent_runtime;runtime.stop();runtime.stopping.clear();sid=new(client);job=submit(client,sid)
            with app.state.store.connect() as con:
                con.execute("UPDATE agent_jobs SET status='RUNNING',current_stage='running',owner='OWNER_TIMEOUT' WHERE id=?",(job['id'],))
            control=Control(runtime,runtime.get(job['id']),'OWNER_TIMEOUT');control.started-=control.timeout+1
            request_thread=threading.Thread(target=call,args=(control.cancellation,),daemon=True);request_thread.start()
            assert entered.wait(2)
            with pytest.raises(ExecutionStopped,match='execution_deadline'):control.check()
            request_thread.join(2)
            assert not request_thread.is_alive() and client_closed.wait(1)
            assert len(outcome)==1 and isinstance(outcome[0],ExecutionStopped)
            assert runtime.get(job['id'])['status']=='TIMED_OUT'
            assert client.get(f'/api/dashboard/jobs/{job["id"]}/result').json()['reply'] is None
    finally:server.shutdown();server.server_close();thread.join(1)


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


def test_deadline_expiring_while_acquiring_commit_transaction_cannot_save_late_result(app,monkeypatch):
    """Advance only the control's elapsed clock at the SQLite writer-lock boundary."""
    from contextlib import contextmanager
    from src.dashboard.jobs import Control
    original_init=Control.__init__;original_connect=app.state.store.connect
    controls=[];injected=[]
    def capture(self,*args,**kwargs):
        original_init(self,*args,**kwargs);controls.append(self)
    class Connection:
        def __init__(self,con):self.con=con
        def __getattr__(self,key):return getattr(self.con,key)
        def execute(self,sql,*args,**kwargs):
            result=self.con.execute(sql,*args,**kwargs)
            if sql=='BEGIN IMMEDIATE' and threading.current_thread().name=='bioreactor-agent-worker' and controls and not injected:
                row=self.con.execute('SELECT current_stage FROM agent_jobs WHERE id=?',(controls[-1].job['id'],)).fetchone()
                if row and row['current_stage']=='verifying':
                    controls[-1].started-=controls[-1].timeout+1;injected.append(True)
            return result
    @contextmanager
    def connect():
        with original_connect() as con:yield Connection(con)
    monkeypatch.setattr(Control,'__init__',capture)
    monkeypatch.setattr(app.state.store,'connect',connect)
    with patch('src.agent.conversation.ConversationAgent.ask',autospec=True,side_effect=fixture_answer),TestClient(app) as client:
        sid=new(client);job=submit(client,sid)
        done=wait(client,job['id'])
        assert injected
        assert done['status']=='TIMED_OUT' and done['error_code']=='EXECUTION_DEADLINE'
        snapshot=client.get(f'/api/dashboard/chat/sessions/{sid}').json()
        assert snapshot['state_version']==0 and snapshot['turns'][0]['reply'] is None


def test_progress_losing_ownership_between_check_and_write_cannot_append_event(app,monkeypatch):
    from src.dashboard.jobs import Control,ExecutionStopped
    with TestClient(app) as client:
        runtime=app.state.agent_runtime;runtime.stop();sid=new(client);job=submit(client,sid)
        with app.state.store.connect() as con:con.execute("UPDATE agent_jobs SET owner='OLD_OWNER',status='RUNNING' WHERE id=?",(job['id'],))
        control=Control(runtime,runtime.get(job['id']),'OLD_OWNER')
        def lose():
            with app.state.store.connect() as con:con.execute("UPDATE agent_jobs SET owner='NEW_OWNER' WHERE id=?",(job['id'],))
        monkeypatch.setattr(control,'check',lose)
        before=client.get('/api/dashboard/jobs/'+job['id']+'/events').json()
        with pytest.raises(ExecutionStopped):control.progress('responding')
        assert client.get('/api/dashboard/jobs/'+job['id']+'/events').json()==before


def test_session_and_jobs_share_one_wal_snapshot_during_concurrent_commit(app,monkeypatch):
    from contextlib import contextmanager
    from src.dashboard.job_api import JobInput
    with TestClient(app) as client:
        runtime=app.state.agent_runtime;runtime.stop();sid=new(client)
        original_connect=app.state.store.connect;changed=[]
        def concurrent_write(sql):
            if sql.startswith('SELECT * FROM dashboard_turns WHERE session_id=') and not changed:
                changed.append(True)
                with original_connect() as con:con.execute('UPDATE dashboard_sessions SET state_version=1 WHERE id=?',(sid,))
                runtime.submit(sid,JobInput(message='TEST snapshot boundary',request_id='TEST_SNAPSHOT'))
        @contextmanager
        def connect():
            with original_connect() as con:
                con.set_trace_callback(concurrent_write);yield con
        monkeypatch.setattr(app.state.store,'connect',connect)
        before=client.get(f'/api/dashboard/chat/sessions/{sid}').json()
        assert changed and before['state_version']==0 and before['jobs']==[] and before['turns']==[]
        after=client.get(f'/api/dashboard/chat/sessions/{sid}').json()
        assert after['state_version']==1 and len(after['jobs'])==1 and len(after['turns'])==1


def test_cooperative_shutdown_requeues_without_late_commit_then_resumes(app):
    entered=threading.Event();calls=[]
    def stopping(agent,text):
        calls.append(text)
        if len(calls)==1:
            entered.set()
            for _ in range(300):
                agent.emit_progress('understanding');time.sleep(.01)
            raise AssertionError('Worker ignored cooperative stop')
        return fixture_answer(agent,text)
    with patch('src.agent.conversation.ConversationAgent.ask',autospec=True,side_effect=stopping),TestClient(app) as client:
        sid=new(client);job=submit(client,sid);assert entered.wait(2)
        runtime=app.state.agent_runtime;runtime.stop()
        assert not runtime.thread.is_alive() and runtime.get(job['id'])['status']=='QUEUED'
        assert client.get(f'/api/dashboard/chat/sessions/{sid}').json()['state_version']==0
        runtime.start();assert wait(client,job['id'])['status']=='COMPLETED'
        snapshot=client.get(f'/api/dashboard/chat/sessions/{sid}').json()
        assert len(calls)==2 and snapshot['state_version']==1 and len(snapshot['turns'])==1


def test_nonresponding_http_provider_is_bounded_and_next_job_executes(app):
    from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
    from src.agent.providers import request_json
    entered=threading.Event();release=threading.Event();calls=[]
    class Silent(BaseHTTPRequestHandler):
        def do_POST(self):entered.set();release.wait(3)
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Silent)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    def source(agent,text):
        calls.append(text)
        if len(calls)==1:request_json(f'http://127.0.0.1:{server.server_port}/silent',{},timeout=.05)
        return fixture_answer(agent,text)
    try:
        with patch('src.agent.conversation.ConversationAgent.ask',autospec=True,side_effect=source),TestClient(app) as client:
            sid=new(client);first=submit(client,sid,'TEST_SILENT_HTTP')
            assert wait(client,first['id'])['status']=='FAILED' and entered.is_set()
            second=submit(client,sid,'TEST_AFTER_SILENT_HTTP')
            assert wait(client,second['id'])['status']=='COMPLETED' and len(calls)==2
    finally:release.set();server.shutdown();server.server_close();thread.join(1)


def test_two_local_workers_share_global_lease_without_duplicate_execution(app):
    from src.dashboard.jobs import JobRuntime
    entered=threading.Event();release=threading.Event();calls=[];inflight=0;maximum=0
    def controlled(agent,text):
        nonlocal inflight,maximum
        inflight+=1;maximum=max(maximum,inflight);calls.append(text)
        try:
            if len(calls)==1:entered.set();assert release.wait(3)
            return fixture_answer(agent,text)
        finally:inflight-=1
    with patch('src.agent.conversation.ConversationAgent.ask',autospec=True,side_effect=controlled),TestClient(app) as client:
        other=JobRuntime(app.state.store,app.state.agent_runtime.execute);other.start()
        try:
            sid=new(client);first=submit(client,sid,'TEST_FIRST_WORKER');assert entered.wait(2)
            second=submit(client,sid,'TEST_SECOND_WORKER');release.set()
            assert wait(client,first['id'])['status']=='COMPLETED' and wait(client,second['id'])['status']=='COMPLETED'
            snapshot=client.get(f'/api/dashboard/chat/sessions/{sid}').json()
            assert maximum==1 and len(calls)==2 and snapshot['state_version']==2 and len(snapshot['turns'])==2
        finally:release.set();other.stop()


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
