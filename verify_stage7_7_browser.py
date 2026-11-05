"""Repeat final UI checks without replacing recorded model timing measurements."""
import main
import json,os,subprocess,sys,time,uuid
from verify_stage7_7 import http,BASE,ROOT,OUT
def run():
 report=json.loads((OUT/'http_results.json').read_text(encoding='utf-8'));db=report['database']
 assert str(ROOT/'data/runtime') in db and 'stage7_7_validation' in db
 env={**os.environ,'PYTHONUTF8':'1','BIOREACTOR_MARKET_DB':db,'BIOREACTOR_RESEARCH_ONLINE':'0','BIOREACTOR_MARKET_SCHEDULER':'0'}
 process=subprocess.Popen([sys.executable,'main.py','dashboard','--port','8777','--no-browser','--no-scheduler'],cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=0x08000000 if os.name=='nt' else 0)
 try:
  for _ in range(60):
   try:assert http('/health')['database']==db;break
   except OSError:time.sleep(.2)
  else:raise RuntimeError('QA server did not start')
  s=http('/api/dashboard/chat/sessions',{'mode':'no_llm','conversation_version':'7'})['id']
  for d in json.loads((OUT/'before_dialogue.json').read_text(encoding='utf-8')):
   r=http(f'/api/dashboard/chat/sessions/{s}/messages',{'message':d['question'],'request_id':uuid.uuid4().hex});assert r.get('smart_agent_version')=='7.7'
  p=subprocess.run(['node','tests/smart-dashboard-browser.mjs'],cwd=ROOT/'frontend',env={**env,'BIOREACTOR_QA_ISOLATED':'1','BIOREACTOR_QA_URL':BASE,'BIOREACTOR_QA_SESSION':s},capture_output=True,text=True,encoding='utf-8',timeout=240)
  (OUT/'browser.log').write_text(p.stdout+'\n'+p.stderr,encoding='utf-8');print(p.stdout);print(p.stderr);assert p.returncode==0
  report['browser_session']=s;report['browser_recheck']='Final lightweight home; fresh no-LLM browser session, original Qwen timings retained'
  (OUT/'http_results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 finally:process.terminate();process.wait(timeout=15)
if __name__=='__main__':run()
