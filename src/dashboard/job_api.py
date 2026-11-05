import json
from fastapi import HTTPException
from pydantic import Field
from src.market.domain import StrictModel
from src.dashboard.schemas import ChatInput
from src.dashboard.jobs import TERMINAL
from src.dashboard import scientific_state
from src.market.domain import utcnow


class JobInput(ChatInput):
    expected_state_version:int|None=Field(default=None,ge=0)


class DraftInput(StrictModel):
    base_state_version:int=Field(ge=0)
    expected_revision:int=Field(default=0,ge=0)
    draft:dict


def public(row):
    result={k:v for k,v in row.items() if k not in {'reply','partial_results','owner'}}
    result['partial_count']=len(row['partial_results']);result['result_available']=row['reply'] is not None
    return result


def register(router,runtime,store):
    @router.post('/chat/sessions/{identifier}/jobs',status_code=202)
    def submit(identifier:str,body:JobInput):return public(runtime.submit(identifier,body))

    @router.get('/jobs/{identifier}')
    def status(identifier:str):return public(runtime.get(identifier))

    @router.get('/jobs/{identifier}/result')
    def result(identifier:str):
        row=runtime.get(identifier)
        return {'id':identifier,'status':row['status'],'terminal':row['terminal'],'reply':row['reply'],
                'error_code':row['error_code'],'partial_results':row['partial_results']}

    @router.get('/jobs/{identifier}/events')
    def events(identifier:str):
        runtime.get(identifier)
        with store.connect() as con:rows=con.execute('SELECT id,created_at,status,details_json FROM agent_job_events WHERE job_id=? ORDER BY id',(identifier,)).fetchall()
        return {'events':[{**dict(r),'details':json.loads(r['details_json'])} for r in rows]}

    @router.post('/jobs/{identifier}/ack')
    def acknowledge(identifier:str):
        row=runtime.get(identifier)
        if not row['terminal']:raise HTTPException(409,'Execution is still active')
        with store.connect() as con:con.execute('UPDATE agent_jobs SET acknowledged_at=COALESCE(acknowledged_at,?) WHERE id=?',(utcnow().isoformat(),identifier))
        return public(runtime.get(identifier))

    @router.post('/jobs/{identifier}/cancel')
    def cancel(identifier:str):
        row=runtime.get(identifier)
        if row['terminal'] or row['current_stage']=='persisted':return public(row)
        if row['status']=='QUEUED':runtime.finish(identifier,'CANCELLED',error='USER_CANCELLED')
        else:
            with store.connect() as con:con.execute("UPDATE agent_jobs SET cancel_requested=1,current_stage='cancelling',updated_at=? WHERE id=? AND status NOT IN (?,?,?,?)",(utcnow().isoformat(),identifier,*TERMINAL))
        return public(runtime.get(identifier))

    @router.get('/chat/sessions/{identifier}/jobs')
    def session_jobs(identifier:str):
        with store.connect() as con:ids=[r['id'] for r in con.execute('SELECT id FROM agent_jobs WHERE conversation_id=? ORDER BY created_at',(identifier,))]
        return {'jobs':[public(runtime.get(i)) for i in ids]}

    @router.get('/chat/sessions/{identifier}/scientific-state')
    def state(identifier:str):
        value=scientific_state.read(store,identifier)
        if value is None:raise HTTPException(404,'Conversation not found')
        return value

    @router.put('/chat/sessions/{identifier}/draft')
    def draft(identifier:str,body:DraftInput):
        encoded=json.dumps(body.draft,ensure_ascii=False,allow_nan=False)
        if len(encoded.encode())>131072:raise HTTPException(413,'Dashboard draft exceeds local storage limit')
        with store.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            current=con.execute('SELECT state_version FROM dashboard_sessions WHERE id=?',(identifier,)).fetchone()
            if current is None:raise HTTPException(404,'Conversation not found')
            if current['state_version']!=body.base_state_version:raise HTTPException(409,'Draft belongs to an older scientific state')
            prior=con.execute('SELECT revision FROM dashboard_drafts WHERE conversation_id=?',(identifier,)).fetchone()
            revision=prior['revision'] if prior else 0
            if revision!=body.expected_revision:raise HTTPException(409,'Dashboard draft was changed by another client')
            con.execute('INSERT INTO dashboard_drafts VALUES(?,?,?,?,?) ON CONFLICT(conversation_id) DO UPDATE SET revision=excluded.revision,base_state_version=excluded.base_state_version,draft_json=excluded.draft_json,updated_at=excluded.updated_at',
                        (identifier,revision+1,body.base_state_version,encoded,utcnow().isoformat()))
        return {'revision':revision+1,'base_state_version':body.base_state_version,'draft':body.draft}

    @router.get('/runtime')
    def health():
        with store.connect() as con:counts={r['status']:r['n'] for r in con.execute('SELECT status,count(*) n FROM agent_jobs GROUP BY status')}
        return {'worker_alive':bool(runtime.thread and runtime.thread.is_alive()),'counts':counts,'last_error':runtime.last_error,'actuator_access':False}
