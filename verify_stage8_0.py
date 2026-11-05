"""Real HTTP + Ollama + Chrome + CLI on a separate copy of the user's database."""
import main,json,os,sqlite3,subprocess,sys,time,urllib.request,uuid,hashlib
from pathlib import Path
from contextlib import closing
from src.data.prepare import ROOT
OUT=ROOT/'reports/stage8_0';BASE='http://127.0.0.1:8780'
DB=ROOT/'data/runtime'/('stage8_0_validation_'+uuid.uuid4().hex[:8]+'.sqlite3')
MAIN='У меня 156 литров навоза с подстилкой и реактор на 200 литров. Рассчитай биогаз, тепло, электричество, затраты и выгоду'
def http(path,body=None):
 req=urllib.request.Request(BASE+path,None if body is None else json.dumps(body,ensure_ascii=False).encode(),{'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=150) as response:return json.loads(response.read())
def run():
 with closing(sqlite3.connect(OUT/'baseline.sqlite3')) as source,closing(sqlite3.connect(DB)) as target:source.backup(target)
 env={**os.environ,'PYTHONUTF8':'1','BIOREACTOR_MARKET_DB':str(DB),'BIOREACTOR_RESEARCH_ONLINE':'0','BIOREACTOR_MARKET_SCHEDULER':'0'}
 log=(OUT/'server.stdout.log').open('w',encoding='utf-8');err=(OUT/'server.stderr.log').open('w',encoding='utf-8')
 server=subprocess.Popen([sys.executable,'main.py','dashboard','--port','8780','--no-browser','--no-scheduler'],cwd=ROOT,env=env,stdout=log,stderr=err,creationflags=0x08000000)
 report={'database':str(DB),'checks':[],'dialogues':[],'cli':[]}
 def check(name,passed):
  report['checks'].append({'name':name,'passed':bool(passed)});print(name+': '+str(bool(passed)),flush=True)
  if not passed:raise AssertionError(name)
 def session(mode='offline'):return http('/api/dashboard/chat/sessions',{'mode':mode,'conversation_version':'7'})['id']
 def ask(s,q):
  start=time.perf_counter();r=http(f'/api/dashboard/chat/sessions/{s}/messages',{'message':q,'request_id':uuid.uuid4().hex});report['dialogues'].append({'session':s,'question':q,'reply':r,'seconds':time.perf_counter()-start});return r
 try:
  for _ in range(80):
   try:health=http('/health');break
   except OSError:time.sleep(.2)
  else:raise RuntimeError('QA server failed to start')
  check('Isolated real HTTP server',Path(health['database'])==DB)
  s=session();first=ask(s,MAIN);check('Species clarification retains all goals',set(first['memory']['advanced']['task']['goals'])=={'gas','heat','electricity','economics'} and first['pending_question']['id']=='advanced-species')
  r=ask(s,'Коровий');check('Clarification resumes full original task without goal question',r.get('pending_question') is None and len(r['tools'])==3 and 'Что рассчитать' not in r['answer'])
  result=r['technical_metadata']['results'];mix=result['gas']['mixture'];check('Bedded mass 110.76 kg, not slurry',abs(mix['total_wet_mass_kg']['low']-110.76)<1e-9 and mix['components'][0]['material_state']=='bedded' and 'oliveira' not in (mix['components'][0]['profile_id'] or ''))
  check('Python methane and biogas with explicit cross-study assumptions',abs(mix['additive_methane_reference_m3']['low']-110.76*.2353*.1092*273.2/273.15)<1e-9 and bool(result['gas']['scenario_assumptions']) and 'условно принятых' in r['answer'])
  check('Heat electricity costs and profit addressed',all(x in r['answer'] for x in ['тепла','электричества','Чистая выгода','затраты','свободное пространство']))
  report['browser_session']=s
  direct=ask(session(),MAIN.replace('навоза','коровьего навоза'));check('Exact main request with known species completes available chain',len(direct['tools'])==3 and direct['pending_question'] is None)
  q=session();questions=['У меня 50 кг сухого коровьего навоза','А если он свежий?','Добавь 20 кг пищевых отходов','Переведи всё в литры','Какая температура лучше?','Сколько дней потребуется?','Что выгоднее — продать или переработать?','Объясни простыми словами','Ответь одним предложением','Почему ты использовал такую плотность?']
  replies=[ask(q,text) for text in questions]
  check('All ten followups complete with no HTTP/tool errors',all(r.get('mode')!='error' and not any(t['status']=='error' for t in r['tools']) for r in replies))
  component=replies[1]['memory']['advanced']['scenario'][0];check('Dry and fresh preserved independently',component['physical_state']=='dry' and component['decay_state']=='fresh')
  check('Added food preserves dry manure component',len(replies[2]['memory']['advanced']['scenario'])==2 and replies[2]['memory']['advanced']['scenario'][0]['physical_state']=='dry')
  check('No fabricated dry-manure density or volume',replies[3]['technical_metadata']['results']['conversion']['conversions'][0]['value'] is None and 'объём неизвестен' in replies[3]['answer'])
  check('Temperature only calls matched condition tool',[t['tool'] for t in replies[4]['tools']]==['get_matched_substrate_conditions'] and '35' in replies[4]['answer'])
  check('Days distinguish laboratory experiment from plant cycle','Лабораторные испытания' in replies[5]['answer'] and 'пока не рассчитан' in replies[5]['answer'])
  check('Profit remains unknown without full costs','Чистая выгода' in replies[6]['answer'] and all(x['net_result_kzt'] is None for x in replies[6]['technical_metadata']['results']['economics']['decision_analysis']['scenarios']))
  check('Simple and one sentence are short, no recomputation',len(replies[7]['answer'])<800 and len(replies[8]['answer'])<400 and replies[7]['tools']==[] and replies[8]['tools']==[])
  primary=[p for d in report['dialogues'] for p in d['reply']['provider_status'] if p.get('model')=='qwen3:8b' and p.get('actual_generation') and p.get('status')=='available']
  check('Actual local Qwen3 8B structured generations',len(primary)>=1);report['qwen3_primary_generations']=len(primary)
  component={'id':'c1','material':'cattle_manure','material_state':'bedded','quantity':156,'unit':'L'}
  cv=http('/api/advisor/convert',{'request':{'components':[component]},'target_unit':'kg'});check('Real unit conversion API',abs(cv['conversions'][0]['value']['low']-110.76)<1e-9)
  for path in ['/api/advisor/catalog','/api/advisor/runs','/api/process/scenarios','/api/experiments','/api/dashboard/reactor']:check('Preserved API '+path,isinstance(http(path),dict))
  legacy=http('/api/research/decision',{'material':'cattle_manure','material_state':'slurry','volume_l':142,'online':False});check('Preserved RM1 calculation unchanged',abs(legacy['methane_potential_m3']['low']-2.92295072)<1e-8)
  browser_session=session('no_llm');ask(browser_session,MAIN);report['browser_session']=browser_session
  p=subprocess.run(['node','tests/advanced-browser.mjs'],cwd=ROOT/'frontend',env={**env,'BIOREACTOR_QA_ISOLATED':'1','BIOREACTOR_QA_URL':BASE,'BIOREACTOR_QA_SESSION':browser_session},capture_output=True,text=True,encoding='utf-8',timeout=180)
  (OUT/'browser.log').write_text(p.stdout+'\n'+p.stderr,encoding='utf-8');check('Actual Chrome browser workflow',p.returncode==0)
  inp=OUT/'conversion_input.json';inp.write_text(json.dumps({'advisor_request':{'components':[component]},'target_unit':'kg'}),encoding='utf-8')
  for args in [['tool','convert_substrate_units','--input',str(inp)],['tool','get_model_info']]:
   p=subprocess.run([sys.executable,'main.py',*args],cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8',timeout=45);data=json.loads(p.stdout);check('CLI '+args[1],p.returncode==0 and data['status']!='error');report['cli'].append({'args':args,'result':data})
  check('No MAE or tool JSON in conversational prose',all(not any(x in d['reply']['answer'] for x in ['MAE','CatBoost','Nested CV','HYPOTHETICAL_SCENARIO']) for d in report['dialogues']))
  report['passed']=True
 except Exception as exc:report['error']=str(exc);raise
 finally:
  (OUT/'http_results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');server.terminate();server.wait(timeout=15);log.close();err.close()
 print('PASS: '+str(len(report['checks']))+' real HTTP/LLM/CLI checks',flush=True)
if __name__=='__main__':run()
