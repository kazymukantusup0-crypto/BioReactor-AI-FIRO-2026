"""Real HTTP job trace, deliberately separate from the held-out evaluation."""
import json
import sys
import time
import uuid
import urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
BASE='http://127.0.0.1:8770'
def http(path,data=None):
    request=urllib.request.Request(BASE+path,None if data is None else json.dumps(data,ensure_ascii=False).encode(),{'Content-Type':'application/json'})
    with urllib.request.urlopen(request,timeout=20) as response:return json.load(response)

def run(prompt,sid=None):
    sid=sid or http('/api/dashboard/chat/sessions',{'mode':'offline','context':{},'conversation_version':'7'})['id']
    request_id=uuid.uuid4().hex;started=time.monotonic()
    job=http(f'/api/dashboard/chat/sessions/{sid}/jobs',{'message':prompt,'request_id':request_id})
    print('SUBMITTED',sid,job['id'],flush=True);last=None
    while time.monotonic()-started<230:
        job=http('/api/dashboard/jobs/'+job['id'])
        if job['current_stage']!=last:print(job['status'],job['current_stage'],round(time.monotonic()-started,1),flush=True);last=job['current_stage']
        if job['terminal']:break
        time.sleep(2)
    result=http(job['result_reference'])
    row={'question':prompt,'session_id':sid,'job':job,'result':result,'seconds':time.monotonic()-started}
    output=ROOT/'reports/stage9';output.mkdir(exist_ok=True)
    (output/('development-'+request_id+'.json')).write_text(json.dumps(row,ensure_ascii=False,indent=2),encoding='utf-8')
    reply=result.get('reply') or {};meta=reply.get('technical_metadata',{})
    print(json.dumps({'status':job['status'],'answer':reply.get('answer'),'author':meta.get('final_author'),'verification':meta.get('verification'),'rejections':meta.get('synthesis_rejections'),'diagnostics':meta.get('diagnostics'),'providers':reply.get('provider_status')},ensure_ascii=False),flush=True)
    return row

if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    run(sys.argv[1] if len(sys.argv)>1 else 'У меня 5 кг пищевых отходов и реактор 90 литров. Сколько метана и выгодно ли?')
