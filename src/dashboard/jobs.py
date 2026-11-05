"""Durable local execution queue; HTTP connections do not own work or results."""
import json
import os
import threading
import time
import uuid
from datetime import timedelta
from fastapi import HTTPException
from src.market.domain import utcnow

TERMINAL={'COMPLETED','FAILED','CANCELLED','TIMED_OUT'}
ACTIVE={'RUNNING','TOOL_EXECUTION','FINALIZING'}


class ExecutionStopped(Exception):pass


class Control:
    def __init__(self,runtime,job,owner):
        self.runtime=runtime;self.job=job;self.owner=owner;self.partial=json.loads(job.get('partial_json') or '[]');self.leases=[]
        self.started=time.monotonic();self.timeout=float(os.getenv('BIOREACTOR_JOB_TIMEOUT','180'))
        self.stop_heartbeat=threading.Event();self.thread=threading.Thread(target=self.heartbeat,daemon=True)

    def check(self):
        row=self.runtime.get(self.job['id'])
        if row['current_stage']=='persisted':return
        if row['owner']!=self.owner:raise ExecutionStopped('execution_ownership_lost')
        if row['status'] in TERMINAL or row['cancel_requested'] or self.runtime.stopping.is_set():raise ExecutionStopped('execution_interrupted')
        if time.monotonic()-self.started>self.timeout:
            self.runtime.finish(self.job['id'],'TIMED_OUT',error='EXECUTION_DEADLINE',partial=self.partial,owner=self.owner)
            raise ExecutionStopped('execution_deadline')

    def heartbeat(self):
        while not self.stop_heartbeat.wait(3):
            try:
                self.runtime.store.renew('agent-execution-global',self.owner,ttl=45)
                for category,owner in self.leases:self.runtime.store.renew(category,owner,ttl=45)
                self.check()
                now=utcnow().isoformat()
                with self.runtime.store.connect() as con:
                    con.execute('UPDATE agent_jobs SET heartbeat_at=?,updated_at=? WHERE id=? AND owner=? AND status NOT IN (?,?,?,?)',
                                (now,now,self.job['id'],self.owner,*TERMINAL))
            except ExecutionStopped:continue
            except Exception as exc:
                self.runtime.last_error='HEARTBEAT_'+type(exc).__name__+': '+str(exc)[:200]
                if self.runtime.stopping.is_set():return

    def progress(self,stage,details=None):
        self.check();details=details or {}
        if stage=='tool_result':self.partial.append(details)
        status='TOOL_EXECUTION' if stage in {'tool_start','tool_result'} else 'FINALIZING' if stage in {'verifying','responding'} else 'RUNNING'
        now=utcnow().isoformat()
        with self.runtime.store.connect() as con:
            con.execute('UPDATE agent_jobs SET status=?,current_stage=?,updated_at=?,partial_json=?,preview_json=COALESCE(?,preview_json) WHERE id=? AND owner=? AND status NOT IN (?,?,?,?)',
                        (status,stage,now,json.dumps(self.partial,ensure_ascii=False),json.dumps(details['preview'],ensure_ascii=False) if 'preview' in details else None,
                         self.job['id'],self.owner,*TERMINAL))
            con.execute('INSERT INTO agent_job_events(job_id,created_at,status,details_json) VALUES(?,?,?,?)',
                        (self.job['id'],now,status,json.dumps({'stage':stage,'tool':details.get('tool')})))


class JobRuntime:
    def __init__(self,store,execute):
        self.store=store;self.execute=execute;self.stopping=threading.Event();self.wake=threading.Event();self.thread=None
        self.last_error=None
        with store.connect() as con:
            con.executescript('''
            CREATE TABLE IF NOT EXISTS agent_jobs(id TEXT PRIMARY KEY,request_id TEXT NOT NULL,conversation_id TEXT NOT NULL,task_id TEXT NOT NULL,
            message TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,status TEXT NOT NULL,current_stage TEXT NOT NULL,
            attempt_count INTEGER NOT NULL DEFAULT 0,error_code TEXT,result_reference TEXT,reply_json TEXT,partial_json TEXT NOT NULL DEFAULT '[]',
            preview_json TEXT,heartbeat_at TEXT,owner TEXT,cancel_requested INTEGER NOT NULL DEFAULT 0,acknowledged_at TEXT,
            expected_state_version INTEGER,UNIQUE(conversation_id,request_id));
            CREATE INDEX IF NOT EXISTS agent_jobs_status ON agent_jobs(status,created_at);
            CREATE TABLE IF NOT EXISTS agent_job_events(id INTEGER PRIMARY KEY AUTOINCREMENT,job_id TEXT NOT NULL,created_at TEXT NOT NULL,status TEXT NOT NULL,details_json TEXT NOT NULL);
            ''')

    def get(self,identifier):
        with self.store.connect() as con:row=con.execute('SELECT * FROM agent_jobs WHERE id=?',(identifier,)).fetchone()
        if row is None:raise HTTPException(404,'Execution not found')
        result=dict(row)
        result['reply']=json.loads(result.pop('reply_json')) if result.get('reply_json') else None
        result['partial_results']=json.loads(result.pop('partial_json'))
        result['preview']=json.loads(result.pop('preview_json')) if result.get('preview_json') else None
        result['terminal']=result['status'] in TERMINAL
        return result

    def submit(self,conversation,body):
        now=utcnow().isoformat();identifier=uuid.uuid4().hex
        with self.store.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            session=con.execute('SELECT state_version FROM dashboard_sessions WHERE id=?',(conversation,)).fetchone()
            if session is None:raise HTTPException(404,'Conversation not found')
            old=con.execute('SELECT * FROM agent_jobs WHERE conversation_id=? AND request_id=?',(conversation,body.request_id)).fetchone()
            if old:
                if old['message']!=body.message:raise HTTPException(409,'request_id already used with different content')
                return self.get(old['id'])
            expected=getattr(body,'expected_state_version',None)
            if expected is not None and expected!=session['state_version']:raise HTTPException(409,'Scientific state changed; reload the current version')
            prior=con.execute('SELECT question FROM dashboard_turns WHERE session_id=? AND request_id=?',(conversation,body.request_id)).fetchone()
            if prior and prior['question']!=body.message:raise HTTPException(409,'request_id already used with different content')
            con.execute('INSERT INTO agent_jobs(id,request_id,conversation_id,task_id,message,created_at,updated_at,status,current_stage,expected_state_version) VALUES(?,?,?,?,?,?,?,?,?,?)',
                        (identifier,body.request_id,conversation,uuid.uuid4().hex,body.message,now,now,'QUEUED','queued',expected))
            con.execute('UPDATE agent_jobs SET result_reference=? WHERE id=?',('/api/dashboard/jobs/'+identifier+'/result',identifier))
            con.execute('INSERT INTO agent_job_events(job_id,created_at,status,details_json) VALUES(?,?,?,?)',(identifier,now,'SUBMITTED','{}'))
            con.execute('INSERT INTO agent_job_events(job_id,created_at,status,details_json) VALUES(?,?,?,?)',(identifier,now,'QUEUED','{}'))
            con.execute('INSERT OR IGNORE INTO dashboard_turns(session_id,request_id,created_at,question,status) VALUES(?,?,?,?,?)',
                        (conversation,body.request_id,now,body.message,'queued'))
        self.wake.set();return self.get(identifier)

    def finish(self,identifier,status,reply=None,error=None,partial=None,owner=None):
        assert status in TERMINAL
        now=utcnow().isoformat()
        with self.store.connect() as con:
            changed=con.execute('UPDATE agent_jobs SET status=?,current_stage=?,updated_at=?,error_code=?,reply_json=COALESCE(?,reply_json),result_reference=?,partial_json=COALESCE(?,partial_json) WHERE id=? AND status NOT IN (?,?,?,?) AND (? IS NULL OR owner=?)',
                        (status,status.lower(),now,error,json.dumps(reply,ensure_ascii=False,allow_nan=False) if reply is not None else None,
                         '/api/dashboard/jobs/'+identifier+'/result',json.dumps(partial,ensure_ascii=False) if partial is not None else None,identifier,*TERMINAL,owner,owner))
            if changed.rowcount!=1:return
            con.execute('INSERT INTO agent_job_events(job_id,created_at,status,details_json) VALUES(?,?,?,?)',(identifier,now,status,json.dumps({'error_code':error})))
            row=con.execute('SELECT conversation_id,request_id FROM agent_jobs WHERE id=?',(identifier,)).fetchone()
            if row and reply is None:
                con.execute('UPDATE dashboard_turns SET status=? WHERE session_id=? AND request_id=? AND reply_json IS NULL',
                            (status.lower(),row['conversation_id'],row['request_id']))

    def recover(self):
        cutoff=(utcnow()-timedelta(seconds=45)).isoformat();now=utcnow().isoformat()
        with self.store.connect() as con:
            legacy_cutoff=(utcnow()-timedelta(seconds=300)).isoformat()
            orphans=con.execute("SELECT t.* FROM dashboard_turns t WHERE t.reply_json IS NULL AND t.status IN ('running','queued') AND t.created_at<? AND NOT EXISTS(SELECT 1 FROM agent_jobs j WHERE j.conversation_id=t.session_id AND j.request_id=t.request_id)",(legacy_cutoff,)).fetchall()
            for row in orphans:
                identifier=uuid.uuid4().hex
                inserted=con.execute("INSERT OR IGNORE INTO agent_jobs(id,request_id,conversation_id,task_id,message,created_at,updated_at,status,current_stage,error_code,result_reference) VALUES(?,?,?,?,?,?,?,'FAILED','failed','LEGACY_REQUEST_INTERRUPTED',?)",
                                    (identifier,row['request_id'],row['session_id'],uuid.uuid4().hex,row['question'],row['created_at'],now,'/api/dashboard/jobs/'+identifier+'/result'))
                if inserted.rowcount:
                    con.execute("UPDATE dashboard_turns SET status='failed' WHERE id=? AND reply_json IS NULL",(row['id'],))
                    con.execute('INSERT INTO agent_job_events(job_id,created_at,status,details_json) VALUES(?,?,?,?)',(identifier,now,'FAILED','{"reason":"legacy_request_without_recoverable_execution_state"}'))
            stale=con.execute("SELECT * FROM agent_jobs WHERE status IN ('RUNNING','TOOL_EXECUTION','FINALIZING') AND COALESCE(heartbeat_at,updated_at)<?",(cutoff,)).fetchall()
            for row in stale:
                status='QUEUED' if row['attempt_count']<2 and not row['cancel_requested'] else 'CANCELLED' if row['cancel_requested'] else 'TIMED_OUT'
                changed=con.execute('UPDATE agent_jobs SET status=?,current_stage=?,owner=NULL,error_code=?,updated_at=? WHERE id=? AND owner IS ?',
                            (status,'recovering' if status=='QUEUED' else status.lower(),'BACKEND_INTERRUPTED',now,row['id'],row['owner']))
                if not changed.rowcount:continue
                con.execute('INSERT INTO agent_job_events(job_id,created_at,status,details_json) VALUES(?,?,?,?)',(row['id'],now,status,'{"reason":"stale_heartbeat"}'))
                if status in TERMINAL:
                    con.execute('UPDATE dashboard_turns SET status=? WHERE session_id=? AND request_id=? AND reply_json IS NULL',
                                (status.lower(),row['conversation_id'],row['request_id']))

    def start(self):
        if self.thread and self.thread.is_alive():return
        self.stopping.clear();self.thread=threading.Thread(target=self.loop,name='bioreactor-agent-worker',daemon=True);self.thread.start()

    def stop(self):
        self.stopping.set();self.wake.set()
        if self.thread:self.thread.join(timeout=2)

    def loop(self):
        while not self.stopping.is_set():
            try:
                self.recover()
                with self.store.connect() as con:queued=con.execute("SELECT 1 FROM agent_jobs WHERE status='QUEUED' LIMIT 1").fetchone()
                if not queued:self.wake.wait(.5);self.wake.clear();continue
                owner=self.store.acquire('agent-execution-global',ttl=45)
                if owner is None:self.wake.wait(.5);self.wake.clear();continue
                try:
                    with self.store.connect() as con:
                        con.execute('BEGIN IMMEDIATE')
                        row=con.execute("SELECT * FROM agent_jobs WHERE status='QUEUED' ORDER BY created_at LIMIT 1").fetchone()
                        if row:
                            now=utcnow().isoformat()
                            con.execute("UPDATE agent_jobs SET status='RUNNING',current_stage='starting',owner=?,heartbeat_at=?,updated_at=?,attempt_count=attempt_count+1 WHERE id=? AND status='QUEUED'",(owner,now,now,row['id']))
                    if row:self.run(dict(row),owner)
                finally:self.store.release('agent-execution-global',owner)
                if not row:self.wake.wait(.5);self.wake.clear()
            except Exception as exc:
                self.last_error=type(exc).__name__+': '+str(exc)[:300]
                import logging
                logging.getLogger(__name__).exception('Agent queue dispatch failed')
                if self.stopping.wait(.5):break

    def run(self,job,owner):
        control=Control(self,job,owner);control.thread.start()
        try:
            reply=self.execute(job['conversation_id'],job['message'],job['request_id'],control,job['expected_state_version'])
            control.check()
            error='AGENT_FAILED' if reply.get('mode')=='error' else None
            self.finish(job['id'],'FAILED' if error else 'COMPLETED',reply=reply,error=error,partial=control.partial,owner=owner)
        except ExecutionStopped:
            current=self.get(job['id'])
            if current['owner']!=owner:return
            if current['status'] not in TERMINAL:
                if self.stopping.is_set():
                    with self.store.connect() as con:con.execute("UPDATE agent_jobs SET status='QUEUED',current_stage='recovering',owner=NULL WHERE id=?",(job['id'],))
                else:self.finish(job['id'],'CANCELLED',error='USER_CANCELLED',partial=control.partial,owner=owner)
        except Exception as exc:
            self.finish(job['id'],'FAILED',error=type(exc).__name__,partial=control.partial,owner=owner)
        finally:control.stop_heartbeat.set();control.thread.join(timeout=1)
