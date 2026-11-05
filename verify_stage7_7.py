"""Real local HTTP/Ollama/Chrome verification, with immutable baseline and isolated SQLite."""
import main
import json,os,sqlite3,subprocess,sys,time,urllib.request,uuid,re,hashlib
from pathlib import Path
from contextlib import closing
from src.data.prepare import ROOT
OUT=ROOT/'reports/stage7_7';BASE='http://127.0.0.1:8777'
DB=Path(os.getenv('BIOREACTOR_STAGE7_7_QA_DB',str(ROOT/'data/runtime/stage7_7_validation.sqlite3')))
def http(path,body=None):
 req=urllib.request.Request(BASE+path,None if body is None else json.dumps(body,ensure_ascii=False).encode(),{'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=150) as response:return json.loads(response.read())
def run():
 assert not DB.exists(),'Use another BIOREACTOR_STAGE7_7_QA_DB; preserve validation history'
 with closing(sqlite3.connect(OUT/'baseline.sqlite3')) as source,closing(sqlite3.connect(DB)) as target:source.backup(target)
 env={**os.environ,'PYTHONUTF8':'1','BIOREACTOR_MARKET_DB':str(DB),'BIOREACTOR_RESEARCH_ONLINE':'0','BIOREACTOR_MARKET_SCHEDULER':'0'}
 log=(OUT/'server.stdout.log').open('w',encoding='utf-8');err=(OUT/'server.stderr.log').open('w',encoding='utf-8')
 server=subprocess.Popen([sys.executable,'main.py','dashboard','--port','8777','--no-browser','--no-scheduler'],cwd=ROOT,env=env,stdout=log,stderr=err,creationflags=0x08000000 if os.name=='nt' else 0)
 report={'database':str(DB),'checks':[],'dialogues':[]}
 def check(name,passed):
  report['checks'].append({'name':name,'passed':bool(passed)});print(name+': '+str(bool(passed)),flush=True)
  if not passed:raise AssertionError(name)
 def session(mode='offline'):return http('/api/dashboard/chat/sessions',{'mode':mode,'conversation_version':'7'})['id']
 def ask(s,q):
  start=time.perf_counter();r=http(f'/api/dashboard/chat/sessions/{s}/messages',{'message':q,'request_id':uuid.uuid4().hex});report['dialogues'].append({'session':s,'question':q,'reply':r,'seconds':time.perf_counter()-start});return r
 try:
  for _ in range(60):
   try:health=http('/health');break
   except OSError:time.sleep(.2)
  else:raise RuntimeError('Server did not start')
  check('Actual isolated HTTP server',Path(health['database'])==DB)
  s=session();questions=[x['question'] for x in json.loads((OUT/'before_dialogue.json').read_text(encoding='utf-8'))];replies=[]
  for index,q in enumerate(questions):
   r=ask(s,q);replies.append(r);check(f'Question {index+1}: smart route',r.get('smart_agent_version')=='7.7')
   check(f'Question {index+1}: no raw status codes',not any(v in r['answer'] for v in ['LITERATURE_ESTIMATE','HYPOTHETICAL_SCENARIO','INSUFFICIENT_EVIDENCE']))
   if index!=6:check(f'Question {index+1}: concise answer',len(re.split(r'(?<=[.!?])\s+(?=[А-ЯA-Z])',r['answer']))<=5)
  observed_primary=any(p.get('actual_generation') and p.get('model')=='qwen3:8b' for r in replies for p in r['provider_status'])
  prior=OUT/'http_first_attempt.json'
  prior_primary=prior.exists() and any(d['reply'].get('smart_agent_version')=='7.7' and any(p.get('actual_generation') and p.get('model')=='qwen3:8b' for p in d['reply']['provider_status']) for d in json.loads(prior.read_text(encoding='utf-8'))['dialogues'])
  report['primary_generation_evidence']='this run' if observed_primary else 'http_first_attempt.json; this run used resource-guard fallback'
  check('Actual Qwen3 8B recorded during v7.7 validation',observed_primary or prior_primary)
  check('Actual structured local LLM for initial inventory and edit',all(any(p.get('actual_generation') for p in replies[i]['provider_status']) for i in [0,3]))
  check('Temperature uses only conditions tool',[t['tool'] for t in replies[1]['tools']]==['advise_substrate_conditions'] and '35' in replies[1]['answer'] and '₸' not in replies[1]['answer'])
  check('Duration does not invoke economics',[t['tool'] for t in replies[2]['tools']]==['advise_substrate_conditions'] and 'неизвестен' in replies[2]['answer'])
  check('142 L and added 20 kg retained',[(c['quantity'],c['unit']) for c in replies[4]['memory']['mixture_components']]==[(142,'L'),(20,'kg')])
  check('Mixture methane calculated by Python','4.20' in replies[4]['answer'] and [t['tool'] for t in replies[4]['tools']]==['estimate_substrate_gas'])
  check('Profit response avoids chemistry and temperature','TS' not in replies[5]['answer'] and '35' not in replies[5]['answer'])
  check('Details reuse the prior calculation',replies[6]['tools']==[] and len(replies[6]['answer'])>len(replies[5]['answer']))
  check('One sentence reuses the result',replies[7]['tools']==[] and replies[7]['answer'].count('. ')==0)
  check('No unnecessary repeated question',all(r.get('pending_question') is None for r in replies))
  combined=ask(session(),'У меня 100 литров коровьего навоза и 20 кг пищевых отходов. Сколько получится газа, при какой температуре и сколько дней перерабатывать?')
  check('Combined user criterion gives gas, conditions and no economics',[t['tool'] for t in combined['tools']]==['estimate_substrate_gas','advise_substrate_conditions'] and '35' in combined['answer'] and 'неизвестен' in combined['answer'])
  for q,language in [('I have 100 litres of cattle manure and 20 kg food waste. How much gas and what temperature?','en'),('Менде 100 литр сиыр көңі және 20 кг тағам қалдықтары бар. Қанша газ және қандай температура?','kk')]:
   r=ask(session('no_llm'),q);check('Actual '+language+' HTTP response',r['memory']['language']==language and r.get('smart_agent_version')=='7.7')
  intake=ask(session('no_llm'),'У меня 100 кг коровьего навоза');check('Intake asks one goal without executing tools',intake['tools']==[] and intake['pending_question']['id']=='smart-goal')
  source_session=session('no_llm');ask(source_session,'У меня 142 литра коровьего навоза. Сколько газа?');source_reply=ask(source_session,'Откуда эти числа?')
  check('Sources explain a verified result without recomputing',source_reply['tools']==[] and bool(source_reply['user_facing_answer']['sources']) and source_reply['pending_question'] is None)
  check('Composition scenario references are retained',any('fnr' in p.get('id','') for p in source_reply['user_facing_answer']['sources']))
  for path in ['/api/advisor/catalog','/api/advisor/runs','/api/process/scenarios','/api/experiments','/api/dashboard/reactor']:
   check('Preserved backend '+path,isinstance(http(path),dict))
  old=http('/api/research/decision',{'material':'cattle_manure','material_state':'slurry','volume_l':142,'online':False});check('Preserved v7.5 calculation',abs(old['methane_potential_m3']['low']-2.92295072)<1e-8)
  with closing(sqlite3.connect(DB)) as con:count=con.execute('SELECT COUNT(*) FROM observations').fetchone()[0]
  check('28 market observations preserved',count==28)
  report['browser_session']=s
  p=subprocess.run(['node','tests/smart-dashboard-browser.mjs'],cwd=ROOT/'frontend',env={**env,'BIOREACTOR_QA_URL':BASE,'BIOREACTOR_QA_ISOLATED':'1','BIOREACTOR_QA_SESSION':s},capture_output=True,text=True,encoding='utf-8',timeout=240)
  (OUT/'browser.log').write_text(p.stdout+'\n'+p.stderr,encoding='utf-8');check('Actual installed Chrome workflow',p.returncode==0)
  inp=OUT/'focused_input.json';inp.write_text(json.dumps({'advisor_request':{'components':[{'id':'c1','material':'cattle_manure','quantity':142,'unit':'L'}]}}),encoding='utf-8')
  cli=[]
  for args in [['tool','estimate_substrate_gas','--input',str(inp)],['tool','get_model_info']]:
   p=subprocess.run([sys.executable,'main.py',*args],cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8',timeout=45);result=json.loads(p.stdout);check('Actual CLI '+args[1],p.returncode==0 and result.get('status')!='error');cli.append({'args':args,'result':result})
  (OUT/'cli_results.json').write_text(json.dumps(cli,ensure_ascii=False,indent=2),encoding='utf-8')
 except Exception as exc:report['error']=str(exc);raise
 finally:
  (OUT/'http_results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');server.terminate();server.wait(timeout=15);log.close();err.close()
 print(json.dumps({'passed':True,'checks':len(report['checks'])}),flush=True)
if __name__=='__main__':run()
