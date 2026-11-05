"""Full v7.5 workflow against real HTTP/Ollama/sources and isolated preserved SQLite."""
import main
import hashlib,json,os,sqlite3,subprocess,sys,time,urllib.request,uuid
from contextlib import closing
from pathlib import Path
from src.data.prepare import ROOT
from src.market.domain import utcnow
from src.market.store import Store
from src.agent.conversation import ConversationAgent
from src.agent.providers import JSONProvider,HybridLLM
from src.agent.tools import ToolRegistry
OUT=ROOT/'reports/stage7_5';DB=Path(os.getenv('BIOREACTOR_STAGE7_5_QA_DB',str(ROOT/'data/runtime/stage7_5_validation.sqlite3')));BASE='http://127.0.0.1:8775'
def http(path,body=None):
    req=urllib.request.Request(BASE+path,None if body is None else json.dumps(body,ensure_ascii=False).encode(),{'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=150) as r:return json.loads(r.read())
def run():
    assert not DB.exists(),'Refuse to overwrite validation history; choose BIOREACTOR_STAGE7_5_QA_DB'
    with closing(sqlite3.connect(ROOT/'data/market/market.sqlite3')) as source,closing(sqlite3.connect(DB)) as target:source.backup(target)
    env={**os.environ,'BIOREACTOR_MARKET_DB':str(DB),'BIOREACTOR_MARKET_SCHEDULER':'0','BIOREACTOR_RESEARCH_ONLINE':'0','PYTHONUTF8':'1'}
    stdout=(OUT/'server.stdout.log').open('w',encoding='utf-8');stderr=(OUT/'server.stderr.log').open('w',encoding='utf-8')
    server=subprocess.Popen([sys.executable,'main.py','market','serve','--port','8775'],cwd=ROOT,env=env,stdout=stdout,stderr=stderr,creationflags=0x08000000 if os.name=='nt' else 0)
    report={'at':utcnow().isoformat(),'database':str(DB),'checks':[],'dialogues':[]};checks=report['checks']
    def check(name,passed):
        checks.append({'name':name,'passed':bool(passed)})
        if not passed:raise AssertionError(name)
    try:
        for _ in range(40):
            try:health=http('/health');break
            except OSError:time.sleep(.3)
        else:raise RuntimeError('Server did not start')
        check('Real isolated HTTP server',Path(health['database'])==DB)
        started=time.perf_counter()
        request={'material':'cattle_manure','material_state':'slurry','volume_l':142,'reactor_total_volume_l':200,'region':'KZ-Karaganda','region_confirmed':False,'online':False}
        r=http('/api/research/decision',request);a=r['decision_analysis'];report['calculation_latency_seconds']=time.perf_counter()-started
        (OUT/'reference_result.json').write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')
        check('Original density and wet mass preserved',abs(r['wet_mass_kg']['low']-143.846)<1e-8)
        check('VS wet basis preserved',abs(r['vs_mass_kg']['low']-14.6147536)<1e-8)
        check('Original methane range preserved',abs(r['methane_potential_m3']['low']-2.92295072)<1e-8 and abs(r['methane_potential_m3']['high']-4.1139956)<1e-8)
        check('Literature result level',r['result_level']=='LITERATURE_ESTIMATE')
        check('Biogas explicitly hypothetical',a['biogas']['result_level']=='HYPOTHETICAL_SCENARIO' and abs(a['biogas']['potential_biogas_m3']['low']-2.92295072/.6)<1e-8)
        check('Useful heat independently computed',abs(a['energy']['outputs']['heat_only_kwh']['low']-2.92295072*9.97*.6*.8)<1e-8)
        check('Electricity independently computed',abs(a['energy']['outputs']['electricity_only_kwh']['high']-4.1139956*9.97*.8*.25)<1e-8)
        check('Unknown heating is not zero',a['reactor_balance']['total_energy_kwh'] is None)
        check('Actual saved statistical price is reference',a['prices']['electricity']['status']=='reference' and a['prices']['electricity']['value']==20.39)
        check('Reference feedstock ask not guaranteed income',a['scenarios'][0]['net_result_kzt'] is None and abs(r['catalog_reference_value_kzt']['low']-100.6922)<1e-6)
        check('No fictitious raw gas income',next(x for x in a['scenarios'] if x['id']=='D_sell_gas')['revenue_kzt'] is None)
        check('Conditional decision and break even',a['decision']['status']=='CONDITIONALLY_PROCESSING_PREFERRED' and a['decision'].get('required_total_cost_below_kzt') is not None)
        # Explicit engineering illustration, no invented measurement/tariff.
        reactor={'temperature_c':35,'initial_temperature_c':15,'ambient_temperature_c':15,'heated_mass_kg':143.846,'heat_capacity_kj_kg_k':4,'heat_loss_coefficient_w_k':1,'duration_days':20,'heater_efficiency':1,'heating_carrier':'electricity','auxiliary_energy_kwh':.48,'energy_scope':'entire_batch','provenance':'HYPOTHETICAL_SCENARIO'}
        illustrated=http('/api/research/decision',{**request,'decision':{'gas_use':'heat','reactor':reactor}})
        energy=illustrated['decision_analysis']['reactor_balance']
        check('Actual HTTP reactor worksheet',abs(energy['total_energy_kwh']-(143.846*4*20/3600+1*20*480/1000+.48))<1e-8)
        check('Unknown other costs still block net profit',all(x.get('net_result_kzt') is None for x in illustrated['decision_analysis']['scenarios']))
        (OUT/'engineering_scenario_result.json').write_text(json.dumps(illustrated,ensure_ascii=False,indent=2),encoding='utf-8')
        old=http('/api/research/estimate',request);check('v7 API and top-level quantities compatible',old['methane_potential_m3']==r['methane_potential_m3'] and old['version']=='7')
        session=http('/api/dashboard/chat/sessions',{'mode':'offline','conversation_version':'7'})
        questions=['У меня 142 литра коровьего навоза и реактор на 200 литров. Сколько примерно получится биогаза, сколько стоит мой навоз и выгоднее ли его продать или переработать?',
                   'Навозная жижа','Для отопления','Для электричества']
        for index,q in enumerate(questions):
            reply=http(f"/api/dashboard/chat/sessions/{session['id']}/messages",{'message':q,'request_id':uuid.uuid4().hex})
            report['dialogues'].append({'question':q,'reply':reply})
            check('Real Ollama structured generation '+str(index),any(p.get('actual_generation') for p in reply['provider_status']))
            check('Python decision output '+str(index),reply.get('analysis_version')=='7.5' and bool(reply.get('technical_metadata',{}).get('research_result',{}).get('decision_analysis')))
            check('At most one next question '+str(index),reply.get('pending_question') is None or len(reply['pending_question']['fields'])==1)
        replies=[x['reply'] for x in report['dialogues']]
        check('Form clarification is shorter',len(replies[1]['answer'])<len(replies[0]['answer']) and 'таблица 1' not in replies[1]['answer'])
        check('142 L / 200 L retained',replies[-1]['memory']['facts']['quantity']['value']==142 and replies[-1]['memory']['facts']['reactor_total_volume_l']['value']==200)
        check('Usage switch persisted',replies[-1]['memory']['decision_settings']['gas_use']=='electricity')
        check('Scenario efficiencies not real facts','thermal_efficiency' not in replies[-1]['memory']['facts'])
        check('All HTTP conversation turns retained',len(http(f"/api/dashboard/chat/sessions/{session['id']}")['turns'])==4)
        report['browser_session']=session['id']
        # An actual refused socket, without stopping the user's Ollama service.
        unavailable=JSONProvider('offline',model='qwen3:8b',url='http://127.0.0.1:11439/api/chat',timeout=.3)
        agent=ConversationAgent(llm=HybridLLM(providers=[unavailable]),registry=ToolRegistry(Store(DB)),research_enabled=True)
        with __import__('unittest.mock',fromlist=['patch']).patch.dict(os.environ,{'BIOREACTOR_RESEARCH_ONLINE':'0'}):offline=agent.ask(questions[0])
        check('Actual refused Ollama connection uses deterministic fallback',offline['mode']=='deterministic_tools_no_llm' and offline.get('analysis_version')=='7.5')
        report['unavailable_ollama_status']=offline['provider_status']
        for language,q in [('en','I have 142 litres of cattle manure and a 200 litre reactor. How much biogas?'),('kk','Менде 142 литр сиыр көңі және 200 литр реактор бар. Қанша биогаз?')]:
            s=http('/api/dashboard/chat/sessions',{'mode':'no_llm','conversation_version':'7'})
            reply=http(f"/api/dashboard/chat/sessions/{s['id']}/messages",{'message':q,'request_id':uuid.uuid4().hex})
            check('Actual multilingual HTTP '+language,reply['memory']['language']==language and '2.92' in reply['answer'])
        # Read-only live source check obeys the existing robots/TLS adapter.
        from src.market.adapters import public_get
        from src.research.market_search import URL,parse_manure
        try:
            offer=parse_manure(public_get(URL));report['live_source_check']={'status':'success','offer':offer}
        except Exception as exc:report['live_source_check']={'status':'unavailable','error':str(exc)}
        if os.getenv('BIOREACTOR_STAGE7_5_BROWSER')=='1':
            p=subprocess.run(['node','tests/decision-browser.mjs'],cwd=ROOT/'frontend',env={**env,'BIOREACTOR_QA_ISOLATED':'1','BIOREACTOR_QA_URL':BASE,'BIOREACTOR_QA_SESSION':session['id']},capture_output=True,text=True,encoding='utf-8',timeout=180)
            (OUT/'browser.log').write_text(p.stdout+'\n'+p.stderr,encoding='utf-8');check('Real Chrome decision workflow',p.returncode==0)
    except Exception as exc:report['error']=type(exc).__name__+': '+str(exc);raise
    finally:
        server.terminate()
        try:server.wait(timeout=10)
        except subprocess.TimeoutExpired:server.kill();server.wait()
        stdout.close();stderr.close()
        hashes=json.loads((OUT/'preserved_hashes.json').read_text(encoding='utf-8'));legacy=json.loads((OUT/'legacy_sqlite.json').read_text(encoding='utf-8'))
        changed_files=[p for p,h in hashes.items() if not (ROOT/p).is_file() or hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=h];changed_rows=[]
        with Store().connect() as con:
            for table,rows in legacy.items():
                for row in rows:
                    current=con.execute(f'SELECT * FROM {table} WHERE id=?',(row['id'],)).fetchone()
                    if current is None or any(current[k]!=v for k,v in row.items()):changed_rows.append([table,row['id']])
        report['preservation']={'artifact_count':len(hashes),'changed_files':changed_files,'changed_rows':changed_rows}
        report['passed']=not report.get('error') and not changed_files and not changed_rows
        (OUT/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'passed':report['passed'],'checks':len(checks),'preservation':report['preservation']}))
if __name__=='__main__':run()
