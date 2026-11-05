"""Additive FastAPI routes; existing market URLs and CLI contracts stay intact."""
import json
import uuid
from fastapi import APIRouter,HTTPException
from fastapi.responses import FileResponse
from src.agent.orchestrator import Agent
from src.agent.providers import HybridLLM
from src.agent.tools import ToolRegistry
from src.data.prepare import ROOT
from src.market.domain import utcnow
from src.dashboard import service
from src.dashboard.schemas import SessionInput,ChatInput,PredictionInput,MeasurementContract


def create_router(store):
    service.initialize(store)
    from src.dashboard import scientific_state
    scientific_state.initialize(store)
    router=APIRouter(prefix='/api/dashboard',tags=['Dashboard'])

    def session(identifier):
        with store.connect() as con:row=con.execute('SELECT * FROM dashboard_sessions WHERE id=?',(identifier,)).fetchone()
        if row is None:raise HTTPException(404,'Chat session not found')
        return dict(row)

    @router.get('/overview')
    def overview():return service.overview(store)

    @router.get('/status')
    def status():return service.system_status(store)

    @router.get('/models/{model}/schema')
    def schema(model:str):
        if model not in service.MODEL_PATHS:raise HTTPException(404,'Model not found')
        return service.model_schema(model)

    @router.post('/predict')
    def predict(body:PredictionInput):return service.predict(store,body)

    @router.get('/economics/schema')
    def economic_schema():return service.economics_schema()

    @router.get('/reactor')
    def reactor():return {**service.get_reactor_status(),'history':[],'label':'SIMULATION / NO LIVE SENSOR DATA','commands_enabled':False}

    @router.get('/reactor/contract')
    def contract():return {'version':'1.0-draft','ingestion_enabled':False,'commands_enabled':False,
        'schema':MeasurementContract.model_json_schema(),'units':{'temperature_c':'°C','ph':'pH','moisture_fraction':'0..1 mass fraction',
        'dry_solids_fraction':'0..1 mass fraction','gas_volume_m3':'m³ (reference conditions must be supplied by integration)',
        'gas_flow_m3_h':'m³/h','methane_fraction':'0..1','mq_raw_adc':'raw ADC, uncalibrated qualitative signal'},
        'notice':'Контракт будущей интеграции. Измерения не принимаются, команды оборудованию отсутствуют. MQ не измеряет точный CH4 без отдельной измерительной системы.'}

    @router.get('/scientific')
    def scientific():return service.scientific_data()

    @router.get('/scientific/figures/{identifier}')
    def figure(identifier:str):
        path=service.FIGURES.get(identifier)
        if path is None or not (ROOT/path).is_file():raise HTTPException(404,'Figure not found')
        return FileResponse(ROOT/path,media_type='image/png')

    @router.get('/demo')
    def demo():return service.demo_data()

    @router.post('/chat/sessions',status_code=201)
    def create_session(body:SessionInput):
        identifier=uuid.uuid4().hex;now=utcnow().isoformat()
        state=None
        if body.conversation_version in {'5.6','7'}:
            from src.agent.dialogue_memory import from_context
            state=from_context(body.context,identifier).model_dump(mode='json')
            state['version']=body.conversation_version
        with store.connect() as con:con.execute('INSERT INTO dashboard_sessions(id,created_at,mode,context_json,history_json,pending_json,conversation_version,conversation_state_json) VALUES(?,?,?,?,?,?,?,?)',
            (identifier,now,body.mode,json.dumps(body.context,ensure_ascii=False),'[]','[]',body.conversation_version,json.dumps(state,ensure_ascii=False) if state else None))
        return {'id':identifier,'mode':body.mode,'created_at':now,'context':body.context,'turns':[],'conversation_version':body.conversation_version,'state_version':0,'memory':state}

    @router.get('/chat/sessions/{identifier}')
    def get_session(identifier:str):
        with store.connect() as con:
            con.execute('BEGIN')
            row=con.execute('SELECT * FROM dashboard_sessions WHERE id=?',(identifier,)).fetchone()
            if row is None:raise HTTPException(404,'Chat session not found')
            turns=con.execute('SELECT * FROM dashboard_turns WHERE session_id=? ORDER BY id DESC LIMIT 50',(identifier,)).fetchall()
        return {'id':identifier,'mode':row['mode'],'context':json.loads(row['context_json']),
            'conversation_version':row['conversation_version'],'state_version':row['state_version'],'memory':json.loads(row['conversation_state_json']) if row['conversation_state_json'] else None,
            'turns':[{**dict(t),'reply':json.loads(t['reply_json']) if t['reply_json'] else None} for t in reversed(turns)]}

    @router.post('/chat/sessions/{identifier}/upgrade')
    def upgrade_session(identifier:str):
        from src.agent.dialogue_memory import from_context
        lease='dashboard-chat:'+identifier;owner=store.acquire(lease)
        if owner is None:raise HTTPException(409,'Дождитесь завершения текущего сообщения.')
        try:
            row=session(identifier)
            if row['conversation_version'] not in {'5.6','7'}:
                state=from_context(json.loads(row['context_json']),identifier)
                from src.agent.nlu import extract
                history=json.loads(row['history_json'])
                if history:
                    try:state.intents=extract(history[-1],state).intents
                    except ValueError:pass
                if state.value('market_region') and not any(state.value('market_region') in text or any(place in text.casefold() for place in ['караганд','алматы','karaganda','almaty','қарағанд']) for text in history):
                    from src.agent.dialogue_memory import fact
                    state.assumptions['market_region']=fact(state.value('market_region'),provenance='ASSUMED_FOR_SCENARIO',evidence='Migrated profile region; not confirmed by a user message')
                    state.facts.pop('market_region',None)
                with store.connect() as con:
                    con.execute("UPDATE dashboard_sessions SET conversation_version='5.6',conversation_state_json=?,state_version=state_version+1 WHERE id=?",(state.model_dump_json(),identifier))
                    scientific_state.persist(con,identifier,state.model_dump(mode='json'),row['state_version']+1)
            return get_session(identifier)
        finally:store.release(lease,owner)

    @router.post('/chat/sessions/{identifier}/research-upgrade')
    def research_upgrade(identifier:str):
        upgrade_session(identifier)
        lease='dashboard-chat:'+identifier;owner=store.acquire(lease)
        if owner is None:raise HTTPException(409,'Дождитесь завершения текущего сообщения.')
        try:
            row=session(identifier);state=json.loads(row['conversation_state_json']);state['version']='7'
            if row['conversation_version']!='7':
                with store.connect() as con:
                    con.execute("UPDATE dashboard_sessions SET conversation_version='7',conversation_state_json=?,state_version=state_version+1 WHERE id=?",(json.dumps(state,ensure_ascii=False),identifier))
                    scientific_state.persist(con,identifier,state,row['state_version']+1)
            return get_session(identifier)
        finally:store.release(lease,owner)

    def execute_message(identifier,body,control=None,expected_version=None):
        session(identifier)
        lease='dashboard-chat:'+identifier;owner=store.acquire(lease,ttl=45 if control else 300)
        if owner is None:raise HTTPException(409,'В этой сессии уже выполняется запрос. Дождитесь ответа.')
        try:
            row=session(identifier)
            if control:
                control.leases.append((lease,owner));control.check()
            with store.connect() as con:
                prior=con.execute('SELECT * FROM dashboard_turns WHERE session_id=? AND request_id=?',(identifier,body.request_id)).fetchone()
                if prior:
                    if prior['question']!=body.message:raise HTTPException(409,'request_id already used for a different message')
                    if prior['reply_json']:return json.loads(prior['reply_json'])
                    if control is None:raise HTTPException(409,'Предыдущий запрос уже принят; проверьте историю сессии.')
                else:con.execute('INSERT INTO dashboard_turns(session_id,request_id,created_at,question,status) VALUES(?,?,?,?,?)',
                                 (identifier,body.request_id,utcnow().isoformat(),body.message,'running'))
            if expected_version is not None and row['state_version']!=expected_version:raise HTTPException(409,'Scientific state version conflict')
            llm=HybridLLM(row['mode'],strict_model=row['conversation_version']=='7') if row['mode'] in {'offline','online','auto'} else HybridLLM(providers=[])
            if row['conversation_version'] in {'5.6','7'}:
                from src.agent.conversation import ConversationAgent
                agent=ConversationAgent(context=json.loads(row['context_json']),llm=llm,registry=ToolRegistry(store,observer=control.progress if control else None),
                    state=json.loads(row['conversation_state_json']) if row['conversation_state_json'] else None,conversation_id=identifier,research_enabled=row['conversation_version']=='7')
            else:agent=Agent(context=json.loads(row['context_json']),llm=llm,registry=ToolRegistry(store))
            agent.history=json.loads(row['history_json']);agent.last_pending=json.loads(row['pending_json'])
            agent.progress=control.progress if control else None
            agent.runtime_version='9' if control else 'legacy'
            try:reply=agent.ask(body.message)
            except Exception as exc:
                from src.dashboard.jobs import ExecutionStopped
                if isinstance(exc,ExecutionStopped):raise
                reply={'mode':'error','answer':'Запрос не завершён: '+type(exc).__name__+'. Проверьте диагностику системы.',
                    'tools':[],'missing':[],'provider_status':[],'actuator_access':False}
            reply.setdefault('technical_metadata',{}).setdefault('diagnostic_events',[]).insert(0,
                {'type':'HttpRequestAccepted','phase':'dashboard_api','session_id':identifier,
                 'request_id':body.request_id,'conversation_version':row['conversation_version']})
            if control:control.progress('verifying');control.check()
            reply['state_version']=row['state_version']+1
            with store.connect() as con:
                con.execute('BEGIN IMMEDIATE')
                if control:
                    execution=con.execute('SELECT status,cancel_requested,owner FROM agent_jobs WHERE id=?',(control.job['id'],)).fetchone()
                    from src.dashboard.jobs import TERMINAL,ExecutionStopped
                    if execution['status'] in TERMINAL or execution['cancel_requested'] or execution['owner']!=control.owner:raise ExecutionStopped('cancelled_or_ownership_lost_before_commit')
                updated=con.execute('UPDATE dashboard_sessions SET state_version=state_version+1 WHERE id=? AND state_version=?',(identifier,row['state_version']))
                if updated.rowcount!=1:raise HTTPException(409,'Scientific state changed during execution')
                con.execute('UPDATE dashboard_turns SET status=?,reply_json=? WHERE session_id=? AND request_id=?',
                    ('error' if reply['mode']=='error' else 'complete',json.dumps(reply,ensure_ascii=False,allow_nan=False),identifier,body.request_id))
                con.execute('UPDATE dashboard_sessions SET context_json=?,history_json=?,pending_json=? WHERE id=?',
                    (json.dumps(agent.context,ensure_ascii=False),json.dumps(agent.history,ensure_ascii=False),json.dumps(agent.last_pending),identifier))
                if row['conversation_version'] in {'5.6','7'}:
                    con.execute('UPDATE dashboard_sessions SET conversation_state_json=? WHERE id=?',(agent.state.model_dump_json(),identifier))
                    scientific_state.persist(con,identifier,agent.state.model_dump(mode='json'),row['state_version']+1)
                    scientific_state.persist_results(con,identifier,agent.state.model_dump(mode='json'),row['state_version']+1,reply)
                    metadata=reply.get('technical_metadata',{})
                    con.execute('UPDATE dashboard_turns SET extracted_entities_json=?,confirmed_parameters_json=?,pending_question_json=?,tool_results_json=? WHERE session_id=? AND request_id=?',
                        (json.dumps(metadata.get('extracted_entities'),ensure_ascii=False),json.dumps(metadata.get('confirmed_parameters'),ensure_ascii=False),
                            json.dumps(reply.get('pending_question'),ensure_ascii=False),json.dumps(reply.get('tools',[]),ensure_ascii=False),identifier,body.request_id))
                if control:con.execute("UPDATE agent_jobs SET current_stage='persisted' WHERE id=?",(control.job['id'],))
            return reply
        except HTTPException:raise
        except Exception as exc:
            from src.dashboard.jobs import ExecutionStopped
            if isinstance(exc,ExecutionStopped):raise
            reply={'mode':'error','answer':'Анализ завершился ошибкой. Данные предыдущей задачи сохранены.',
                   'tools':[],'missing':[],'provider_status':[],'actuator_access':False,'technical_metadata':{'error_code':type(exc).__name__}}
            with store.connect() as con:
                con.execute("UPDATE dashboard_turns SET status='error',reply_json=? WHERE session_id=? AND request_id=? AND reply_json IS NULL",(json.dumps(reply,ensure_ascii=False),identifier,body.request_id))
            return reply
        finally:store.release(lease,owner)

    @router.post('/chat/sessions/{identifier}/messages')
    def message(identifier:str,body:ChatInput):
        owner=store.acquire('agent-execution-global',ttl=300)
        if owner is None:raise HTTPException(409,'Агент выполняет другой запрос. Используйте очередь заданий.')
        try:return execute_message(identifier,body)
        finally:store.release('agent-execution-global',owner)

    from src.dashboard.jobs import JobRuntime
    from src.dashboard.job_api import register
    runtime=JobRuntime(store,lambda sid,text,rid,control,version:execute_message(sid,ChatInput(message=text,request_id=rid),control,version))
    router.agent_runtime=runtime
    register(router,runtime,store)
    return router
