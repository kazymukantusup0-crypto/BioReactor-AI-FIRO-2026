import json
import uuid
from src.agent.context import validate_context
from src.agent.conversation import ConversationAgent as Agent
from src.agent.providers import HybridLLM
from src.agent.tools import ToolRegistry


def chat(args):
    from src.market.service import get_store
    from src.dashboard.service import initialize
    from src.market.domain import utcnow
    store=get_store();initialize(store)
    context=json.loads(args.context.read_text(encoding='utf-8-sig')) if args.context else {}
    if 'model' not in context: context['model']=args.model
    identifier=getattr(args,'conversation',None) or uuid.uuid4().hex
    with store.connect() as con:existing=con.execute('SELECT * FROM dashboard_sessions WHERE id=?',(identifier,)).fetchone()
    if getattr(args,'conversation',None) and existing is None:raise ValueError('Conversation not found')
    research=getattr(args,'research',False) or bool(existing and existing['conversation_version']=='7')
    llm=HybridLLM(args.mode,providers=[] if args.no_llm else None,strict_model=research)
    if existing and not existing['conversation_state_json']:
        context={**json.loads(existing['context_json']),**(context if args.context else {})}
    agent=Agent(context=context,llm=llm,registry=ToolRegistry(store),state=json.loads(existing['conversation_state_json']) if existing and existing['conversation_state_json'] else None,
        conversation_id=identifier,research_enabled=getattr(args,'research',False) or bool(existing and existing['conversation_version']=='7'))
    if existing:
        agent.history=json.loads(existing['history_json']);agent.last_pending=json.loads(existing['pending_json'])
        if not existing['conversation_state_json'] and agent.history:
            from src.agent.nlu import extract
            agent.state.intents=extract(agent.history[-1],agent.state).intents
    else:
        with store.connect() as con:con.execute('INSERT INTO dashboard_sessions(id,created_at,mode,context_json,history_json,pending_json,conversation_version,conversation_state_json) VALUES(?,?,?,?,?,?,?,?)',
            (identifier,utcnow().isoformat(),'no_llm' if args.no_llm else args.mode,json.dumps(agent.context,ensure_ascii=False),'[]','[]','7' if agent.research_enabled else '5.6',agent.state.model_dump_json()))
    def save_state(con):
        con.execute('UPDATE dashboard_sessions SET context_json=?,history_json=?,pending_json=?,conversation_version=?,conversation_state_json=? WHERE id=?',
            (json.dumps(agent.context,ensure_ascii=False),json.dumps(agent.history,ensure_ascii=False),json.dumps(agent.last_pending),'7' if agent.research_enabled else '5.6',agent.state.model_dump_json(),identifier))
    def respond(text):
        lease='dashboard-chat:'+identifier;owner=store.acquire(lease)
        if owner is None:raise ValueError('A message is already running in this conversation')
        try:
            reply=agent.ask(text);metadata=reply.get('technical_metadata',{})
            with store.connect() as con:
                con.execute('INSERT INTO dashboard_turns(session_id,request_id,created_at,question,status,reply_json,extracted_entities_json,confirmed_parameters_json,pending_question_json,tool_results_json) VALUES(?,?,?,?,?,?,?,?,?,?)',
                    (identifier,uuid.uuid4().hex,utcnow().isoformat(),text,'complete',json.dumps(reply,ensure_ascii=False,allow_nan=False),
                        json.dumps(metadata.get('extracted_entities'),ensure_ascii=False),json.dumps(metadata.get('confirmed_parameters'),ensure_ascii=False),json.dumps(reply.get('pending_question'),ensure_ascii=False),json.dumps(reply['tools'],ensure_ascii=False)))
                save_state(con)
        finally:store.release(lease,owner)
        print(json.dumps(reply,ensure_ascii=False,indent=2,allow_nan=False) if args.json else reply['answer'])
    if args.message is not None:
        respond(args.message)
        return
    print('BioReactor AI '+('v7.7' if agent.research_enabled else 'v5.6')+'. Можно задавать обычные вопросы. /exit — выход; /reset — новая партия. Управления оборудованием нет.')
    print('Диалог сохраняется. Для продолжения: --conversation '+identifier)
    while True:
        try: text=input('Вы> ').strip()
        except (EOFError,KeyboardInterrupt): print(); break
        if text.casefold() in {'/exit','/quit'}: break
        if text.casefold()=='/reset':
            agent.reset()
            with store.connect() as con:save_state(con)
            print('Контекст партии сброшен.');continue
        if text: respond(text)


def call_tool(args):
    from src.agent.process_bridge import PROCESS_TOOLS
    from src.agent.research_bridge import RESEARCH_TOOLS
    from src.agent.advisor_tools import ADVISOR_TOOLS
    from src.advisor.focused import TOOLS as FOCUSED_TOOLS
    from src.advisor.advanced_science import TOOLS as ADVANCED_TOOLS
    data=json.loads(args.input.read_text(encoding='utf-8-sig')) if args.input else {}
    context=data if args.name in PROCESS_TOOLS+RESEARCH_TOOLS+ADVISOR_TOOLS+FOCUSED_TOOLS+ADVANCED_TOOLS else validate_context(data)
    result=ToolRegistry().execute(args.name,context,{},args.query)
    print(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False))
    return 2 if result['status']=='error' else 0
