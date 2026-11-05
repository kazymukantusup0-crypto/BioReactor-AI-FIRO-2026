"""Real HTTP, installed Ollama/Chrome and CLI on a SQLite backup. Never trains models."""
import main
import hashlib,json,os,sqlite3,subprocess,sys,time,urllib.request,uuid
from pathlib import Path
from contextlib import closing
from src.data.prepare import ROOT
OUT=ROOT/'reports/stage7_6';BASE='http://127.0.0.1:8776'
DB=Path(os.getenv('BIOREACTOR_STAGE7_6_QA_DB',str(ROOT/'data/runtime/stage7_6_validation.sqlite3')))

def http(path,body=None):
    req=urllib.request.Request(BASE+path,None if body is None else json.dumps(body,ensure_ascii=False).encode(),{'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=150) as r:return json.loads(r.read())
def run():
    assert not DB.exists(),'Choose a new BIOREACTOR_STAGE7_6_QA_DB; validation history is preserved'
    with closing(sqlite3.connect(OUT/'baseline.sqlite3')) as source,closing(sqlite3.connect(DB)) as target:source.backup(target)
    env={**os.environ,'PYTHONUTF8':'1','BIOREACTOR_MARKET_DB':str(DB),'BIOREACTOR_MARKET_SCHEDULER':'0','BIOREACTOR_RESEARCH_ONLINE':'0'}
    report={'version':'7.6','database':str(DB),'checks':[],'dialogues':[]};checks=report['checks']
    def check(name,condition):
        checks.append({'name':name,'passed':bool(condition)});print(name+': '+str(bool(condition)),flush=True)
        if not condition:raise AssertionError(name)
    stdout=(OUT/'server.stdout.log').open('w',encoding='utf-8');stderr=(OUT/'server.stderr.log').open('w',encoding='utf-8')
    server=subprocess.Popen([sys.executable,'main.py','dashboard','--port','8776','--no-browser','--no-scheduler'],cwd=ROOT,env=env,stdout=stdout,stderr=stderr,creationflags=0x08000000 if os.name=='nt' else 0)
    try:
        for _ in range(60):
            try:health=http('/health');break
            except OSError:time.sleep(.3)
        else:raise RuntimeError('QA server did not start')
        check('Real isolated HTTP server',Path(health['database'])==DB)
        catalog=http('/api/advisor/catalog');check('Catalog separates names and numeric profiles',catalog['recognized_categories']==15 and catalog['approved_profile_count']==3 and len(catalog['materials_with_approved_profiles'])==2)
        def session(mode='offline'):return http('/api/dashboard/chat/sessions',{'mode':mode,'conversation_version':'7'})['id']
        def ask(s,q,label,llm=True):
            start=time.perf_counter();r=http(f'/api/dashboard/chat/sessions/{s}/messages',{'message':q,'request_id':uuid.uuid4().hex});report['dialogues'].append({'label':label,'session':s,'question':q,'seconds':time.perf_counter()-start,'reply':r})
            if llm:check(label+': real local Ollama generation',any(p.get('actual_generation') for p in r['provider_status']))
            check(label+': typed Python advisor',r.get('analysis_version')=='7.6' and bool(r.get('technical_metadata',{}).get('advisor_result')))
            check(label+': human body without status codes',not any(code in r['answer'] for code in ['HYPOTHETICAL_SCENARIO','LITERATURE_ESTIMATE','INSUFFICIENT_EVIDENCE']))
            check(label+': at most one question',r.get('pending_question') is None or len(r['pending_question']['fields'])<=1)
            return r
        s=session();a=ask(s,'У меня 142 литра навозной жижи и реактор на 200 литров. Сколько получится газа, какая температура лучше и сколько времени потребуется?','A')
        r=a['technical_metadata']['advisor_result'];ref=r.get('conditional_reference_case',r)
        check('A: 142 L and total 200 L retained',a['memory']['mixture_components'][0]['quantity']==142 and a['memory']['facts']['reactor_total_volume_l']['value']==200)
        check('A: species not silently inferred',a['memory']['mixture_components'][0]['material']=='manure' and 'conditional_reference_case' in r)
        check('A: actual RM1 conditional reference',abs(ref['mixture']['additive_methane_reference_m3']['low']-2.92295072)<1e-8)
        check('A: no 37C/batch27/working200 defaults',r['temperature']['candidate'] is None and ref['duration']['recommended_batch_duration_days'] is None and r['decision_analysis']['feasibility']['working_volume_l'] is None)
        clarified=ask(s,'Коровий','A_species');check('A: species clarification retains original amount',clarified['memory']['mixture_components'][0]['material']=='cattle_manure' and clarified['memory']['mixture_components'][0]['quantity']==142)
        s=session();b=ask(s,'У меня 50 кг коровьего навоза, 20 кг пищевых отходов и 10 кг травы. Что получится, если всё смешать?','B')
        check('B: three confirmed quantities',[(x['material'],x['quantity']) for x in b['memory']['mixture_components']]==[('cattle_manure',50),('food_waste',20),('grass',10)])
        check('B: missing grass not replaced by zero',b['technical_metadata']['advisor_result']['mixture']['additive_methane_reference_m3'] is None and b['technical_metadata']['advisor_result']['mixture']['known_component_additive_subtotal_m3'] is not None)
        c=ask(s,'Добавь ещё 5 кг пищевых отходов','C');check('C: edit sums correctly to 85 kg',c['memory']['mixture_components'][1]['quantity']==25 and c['technical_metadata']['advisor_result']['mixture']['total_wet_mass_kg']['low']==85)
        d=ask(s,'Убери траву. Какая температура теперь лучше?','D');check('D: remove retains 50/25 kg and no temperature optimum',len(d['memory']['mixture_components'])==2 and d['memory']['mixture_components'][1]['quantity']==25 and d['technical_metadata']['advisor_result']['temperature']['candidate'] is None)
        e=ask(s,'Какая смесь будет наиболее выгодной?','E');comparison=e['technical_metadata']['mixture_comparison'];check('E: constrained comparison with no unsupported winner',len(comparison['candidates'])==3 and comparison['preferred_mixture'] is None)
        f=ask(s,'У меня только 200-литровый реактор. Можно загрузить всё сразу?','F');check('F: total capacity gives no loading authorization',f['memory']['facts']['reactor_total_volume_l']['value']==200 and f['technical_metadata']['advisor_result']['decision_analysis']['feasibility']['operation_authorized'] is False)
        report['browser_session']=s
        what=ask(s,'Что изменится, если увеличить навоз вдвое?','what_if');check('What-if keeps inventory separate',what['memory']['mixture_components'][0]['quantity']==50 and what['memory']['mixture_scenario_components'][0]['quantity']==100)
        check('Actual persisted history after edits',len(http(f'/api/dashboard/chat/sessions/{s}')['turns'])==6)
        for q,lang in [('I have 50 kg cattle manure, 20 kg food waste and 10 kg grass. What temperature?','en'),('Менде 50 кг сиыр көңі, 20 кг тағам қалдықтары және 10 кг шөп бар. Қандай температура?','kk')]:
            r=ask(session('no_llm'),q,lang,False);check('Actual multilingual response '+lang,r['memory']['language']==lang and len(r['memory']['mixture_components'])==3)
        r=ask(session('no_llm'),'У меня 20 кг травы. Какая температура?','offline_no_llm',False);check('No-LLM safe calculation',r['mode']=='deterministic_tools_no_llm' and r['technical_metadata']['advisor_result']['mixture']['additive_methane_reference_m3'] is None)
        legacy=http('/api/research/decision',{'material':'cattle_manure','material_state':'slurry','volume_l':142,'online':False});check('Legacy v7.5 endpoint retains methane values',abs(legacy['methane_potential_m3']['high']-4.1139956)<1e-8 and legacy['decision_analysis']['version']=='7.5')
        with closing(sqlite3.connect(DB)) as con:price_count=con.execute('SELECT COUNT(*) FROM observations').fetchone()[0]
        check('Existing market observations retained',price_count==28 and len(http('/prices/history?commodity=electricity&region=KZ-Karaganda')['prices'])>=1)
        # A real source query; failed networking is reported, never made into a profile.
        from src.market.store import Store
        from src.research.evidence_store import EvidenceStore
        from src.research.advisor_pipeline import discover
        report['live_scientific_discovery']=discover(EvidenceStore(Store(DB)),['cattle_manure','food_waste'],['BMP','co_digestion'],True)
        check('Discovery never auto-approves numerical use',all(not row['numeric_use_allowed'] for row in report['live_scientific_discovery']['discovered']))
        # Real CLI on the same isolated SQLite copy; fixtures are source data, not fake prices.
        payload={'components':[{'id':'c1','material':'cattle_manure','material_state':'slurry','quantity':142,'unit':'L'}]};inp=OUT/'cli_input.json';inp.write_text(json.dumps(payload),encoding='utf-8')
        cli=[]
        for args in [['tool','get_substrate_catalog'],['tool','analyze_substrate_mixture','--input',str(inp)],['tool','get_model_info']]:
            p=subprocess.run([sys.executable,'main.py',*args],cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8',timeout=45);value=json.loads(p.stdout);check('CLI '+args[1],p.returncode==0 and value.get('status')!='error');cli.append({'args':args,'result':value})
        (OUT/'cli_results.json').write_text(json.dumps(cli,ensure_ascii=False,indent=2),encoding='utf-8')
        report['primary_model_generations']=[p for d in report['dialogues'] for p in d['reply']['provider_status'] if p.get('actual_generation')]
        p=subprocess.run(['node','tests/advisor-browser.mjs'],cwd=ROOT/'frontend',env={**env,'BIOREACTOR_QA_ISOLATED':'1','BIOREACTOR_QA_URL':BASE,'BIOREACTOR_QA_SESSION':s},capture_output=True,text=True,encoding='utf-8',timeout=240)
        (OUT/'browser.log').write_text(p.stdout+'\n'+p.stderr,encoding='utf-8');check('Real Chrome browser workflow',p.returncode==0)
    except Exception as exc:report['error']=type(exc).__name__+': '+str(exc);raise
    finally:
        (OUT/'http_results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');server.terminate();server.wait(timeout=15);stdout.close();stderr.close()
    print(json.dumps({'passed':True,'checks':len(checks),'dialogues':len(report['dialogues'])}),flush=True)
if __name__=='__main__':run()
