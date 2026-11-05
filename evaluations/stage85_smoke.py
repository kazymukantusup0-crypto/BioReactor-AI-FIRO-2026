import sys,json,urllib.request,uuid,os
from pathlib import Path
base='http://127.0.0.1:8769'
def request(path,payload):
    req=urllib.request.Request(base+path,json.dumps(payload,ensure_ascii=False).encode(),{'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=240) as response:return json.load(response)
s=request('/api/dashboard/chat/sessions',{'mode':'offline','context':{},'conversation_version':'7'})
r=request('/api/dashboard/chat/sessions/'+s['id']+'/messages',{'message':'У меня 48 кг пищевых отходов и реактор 90 литров. Сколько метана и выгодно ли?','request_id':str(uuid.uuid4())})
p=Path('reports/stage8_5');p.mkdir(exist_ok=True)
(p/os.getenv('BIOREACTOR_SMOKE_OUTPUT','smoke.json')).write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')
md=r.get('technical_metadata',{})
print(json.dumps({'mode':r.get('mode'),'answer':r.get('answer'),'tools':[t['tool'] for t in r.get('tools',[])],
 'latency_seconds':md.get('latency_seconds'),'termination':md.get('autonomous_termination'),'diagnostics':md.get('diagnostics')},ensure_ascii=False,indent=2))
