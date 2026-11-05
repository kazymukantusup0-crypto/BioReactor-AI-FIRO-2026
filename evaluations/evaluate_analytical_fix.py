"""Real Qwen and optional HTTP regressions; keeps complete responses and memory."""
import json,os,sys,time,sqlite3,urllib.request
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.agent.conversation import ConversationAgent
from src.agent.providers import HybridLLM,JSONProvider
from src.agent.tools import ToolRegistry
from src.market.store import Store

CASES=[
 ('food_economics',['У меня 5 кг пищевых отходов и реактор 90 литров. Сколько метана и выгодно ли?']),
 ('pig_biogas',['У меня 8 кг свиного навоза, сколько биогаза?']),
 ('alternatives',['Что выгоднее: 10 кг коровьего навоза или 10 кг пищевых отходов?']),
 ('temperature',['В реакторе 30 градусов. Стоит ли повышать температуру?']),
 ('addition',['У меня 5 кг пищевых отходов, добавь 2 кг куриного помёта и пересчитай']),
 ('water_context',['У меня 5 кг пищевых отходов и реактор 90 литров. Сколько метана и выгодно ли?', 'Если я добавлю 10 литров воды, метана станет больше?']),
 ('income',['Сколько денег я заработаю на 5 кг пищевых отходов?']),
]

def request(url,data):
    req=urllib.request.Request(url,json.dumps(data,ensure_ascii=False).encode(),{'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=600) as response:return json.load(response)

def main():
    os.environ['BIOREACTOR_RESEARCH_ONLINE']='0'
    folder=ROOT/'evaluations'/'analytical_fix';folder.mkdir(exist_ok=True)
    path=folder/os.getenv('ANALYTICAL_OUTPUT','qwen_results.json')
    db=folder/'market_snapshot.sqlite3'
    if not db.exists():
        with sqlite3.connect(ROOT/'data/market/market.sqlite3') as source,sqlite3.connect(db) as dest:source.backup(dest)
    provider=JSONProvider('offline',model='qwen3:8b',timeout=180)
    store=Store(db);selected=os.getenv('ANALYTICAL_CASES','').split(',');base=os.getenv('ANALYTICAL_HTTP')
    result={'model':'qwen3:8b','started_at':datetime.now(timezone.utc).isoformat(),'gpu_layers_override':os.getenv('BIOREACTOR_LLM_GPU_LAYERS'),'http':base,'online_research':False,'market_database':os.getenv('ANALYTICAL_DB_LABEL','snapshot of existing observations; no test prices inserted'),'cases':[],'status':'running'}
    def save():path.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    for name,messages in CASES:
        if selected!=[''] and name not in selected:continue
        agent=ConversationAgent(llm=HybridLLM('offline',providers=[provider]),registry=ToolRegistry(store),research_enabled=True)
        session=request(base+'/api/dashboard/chat/sessions',{'mode':'offline','context':{},'conversation_version':'7'}) if base else None
        row={'id':name,'turns':[],'session_id':session['id'] if session else None};result['cases'].append(row)
        for i,message in enumerate(messages):
            start=time.perf_counter();before=provider.calls
            reply=request(base+'/api/dashboard/chat/sessions/'+session['id']+'/messages',{'message':message,'request_id':f'analytical-{name}-{i}'}) if base else agent.ask(message)
            row['turns'].append({'prompt':message,'latency_seconds':time.perf_counter()-start,'generation_calls':provider.calls-before if not base else None,'response':reply})
            save();print(name,i,reply.get('mode'),[(t['tool'],t['status']) for t in reply.get('tools',[])],flush=True)
            if not base:agent=ConversationAgent(llm=agent.llm,registry=agent.registry,state=agent.state.model_dump(mode='json'),research_enabled=True)
    result['status']='complete';save()
    print(path,flush=True)

if __name__=='__main__':main()
