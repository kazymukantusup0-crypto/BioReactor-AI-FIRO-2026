"""Real HTTP + Ollama + source verification in an isolated SQLite backup."""
import main
import hashlib,json,os,sqlite3,subprocess,sys,time,urllib.request,urllib.error,uuid
from contextlib import closing
from pathlib import Path
from src.data.prepare import ROOT
from src.market.store import Store
from src.market.domain import utcnow
OUT=ROOT/'reports/stage7';DB=Path(os.getenv('BIOREACTOR_STAGE7_QA_DB',str(ROOT/'data/runtime/stage7_validation.sqlite3')));BASE='http://127.0.0.1:8768'
def request(path,body=None):
    req=urllib.request.Request(BASE+path,None if body is None else json.dumps(body,ensure_ascii=False).encode(),{'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=180) as r:return json.loads(r.read())
def run():
    report={'checked_at':utcnow().isoformat(),'database':str(DB),'http_checks':[],'llm_checks':[],'preservation':{}}
    checks=report['http_checks']
    def check(name,value):
        checks.append({'name':name,'passed':bool(value)})
        if not value:raise AssertionError(name)
    assert not DB.exists(),'Use a new verification DB, never overwrite previous history'
    DB.parent.mkdir(parents=True,exist_ok=True)
    with closing(sqlite3.connect(ROOT/'data/market/market.sqlite3')) as source,closing(sqlite3.connect(DB)) as target:source.backup(target)
    env={**os.environ,'BIOREACTOR_MARKET_DB':str(DB),'BIOREACTOR_MARKET_SCHEDULER':'0','BIOREACTOR_RESEARCH_ONLINE':'1','PYTHONUTF8':'1'}
    stdout=(OUT/'server.stdout.log').open('w',encoding='utf-8');stderr=(OUT/'server.stderr.log').open('w',encoding='utf-8')
    server=subprocess.Popen([sys.executable,'main.py','market','serve','--port','8768'],cwd=ROOT,env=env,stdout=stdout,stderr=stderr,creationflags=0x08000000 if os.name=='nt' else 0)
    try:
        for _ in range(40):
            try:
                health=request('/health');break
            except (OSError,ValueError):time.sleep(.5)
        else:raise RuntimeError('Validation server did not start')
        check('Actual isolated loopback server',Path(health['database'])==DB)
        check('Old 28 prices retained',len(request('/prices/current')['prices'])>0)
        evidence=request('/api/research/evidence');check('Primary evidence includes explicit graph method','GRAPH_READ_ENVELOPE' in evidence['profiles'][0]['values']['bmp_ml_g_vs']['method'])
        r=request('/api/research/estimate',{'volume_l':142,'reactor_total_volume_l':200,'online':True})
        report['real_source_result']=r
        check('142 L methane range from real reviewed profile',abs(r['methane_potential_m3']['low']-2.92295072)<1e-8)
        check('No real gas revenue invented',r['gas_sale_revenue'] is None and r['net_profit'] is None)
        check('Unknown form is hypothetical',r['result_level']=='HYPOTHETICAL_SCENARIO')
        check('Actual StroiTaxi request yields undated seller ask',bool(r['market']['offers']) and not r['market']['offers'][0]['is_current'])
        check('Catalogue value not income',abs(r['catalog_reference_value_kzt']['low']-100.6922)<1e-6)
        check('Actual source logs retained',len(request('/api/research/logs')['logs'])>=2)
        r2=request('/api/research/estimate',{'volume_l':142,'material_state':'slurry'})
        check('Compatible form literature level',r2['result_level']=='LITERATURE_ESTIMATE')
        check('Online cache available offline',bool(r2['market']['offers']))
        dry=request('/api/research/estimate',{'volume_l':142,'material_state':'dry'})
        check('Dry manure not extrapolated',dry['methane_potential_m3'] is None)
        try:request('/api/research/estimate',{'volume_l':-1});check('Invalid volume rejected',False)
        except urllib.error.HTTPError as exc:check('Invalid volume rejected',exc.code==422)
        s=request('/api/dashboard/chat/sessions',{'mode':'offline','conversation_version':'7'})
        questions=['Привет, у меня есть 142 литра коровьего навоза и реактор вместимостью 200 литров. Лучше продать навоз или переработать?',
                   'Можешь посчитать, сколько сейчас стоит 142 литра коровьего навоза, сколько из него выйдет газа и сколько денег можно выручить за газ?',
                   'Навозная жижа', 'Теперь у меня 65 литров коровьего навоза. Сколько метана?']
        for index,q in enumerate(questions):
            reply=request(f"/api/dashboard/chat/sessions/{s['id']}/messages",{'message':q,'request_id':uuid.uuid4().hex})
            report['llm_checks'].append({'question':q,'reply':reply})
            check('Real Ollama generated structured NLU '+str(index),any(p.get('actual_generation') for p in reply['provider_status']))
            check('v7 research tool actually called '+str(index),any(t['tool']=='research_and_estimate' for t in reply['tools']))
            check('Literature never becomes confirmed density '+str(index),'density_kg_l' not in reply['memory']['facts'])
        last=report['llm_checks'][-1]['reply'];check('Quantity correction recalculated',last['memory']['facts']['quantity']['value']==65 and last['technical_metadata']['research_result']['methane_potential_m3']['high']<2)
        check('Full reactor capacity remembered',last['memory']['facts']['reactor_total_volume_l']['value']==200)
        check('History saved',len(request(f"/api/dashboard/chat/sessions/{s['id']}")['turns'])==4)
        report['browser_session']=s['id']
        model=json.loads((ROOT/'examples/stage1_5_measured.json').read_text())
        for name in ['stage1','stage1_5']:
            prediction=request('/api/dashboard/predict',{'model':name,'context':model})
            check('Preserved model loads '+name,prediction['status']=='ok')
        report['sources_status']={'crossref':r['scientific_search']['network_status'],'stroitaxi':r['market']['status'],'publisher_fulltext':'robots denied; reviewed catalog and legal public figure asset used','other_market_categories':'Existing 28 observations retained; new live purchase bids/raw biogas prices not configured'}
        # Browser verification gets a temporary live server lease without altering production.
        if os.getenv('BIOREACTOR_STAGE7_BROWSER')=='1':
            proc=subprocess.run(['node','tests/research-browser.mjs'],cwd=ROOT/'frontend',env={**env,'BIOREACTOR_QA_ISOLATED':'1','BIOREACTOR_QA_URL':BASE,'BIOREACTOR_QA_SESSION':s['id']},capture_output=True,text=True,encoding='utf-8',timeout=240)
            (OUT/'browser.log').write_text(proc.stdout+'\n'+proc.stderr,encoding='utf-8');check('Actual Chrome research workflow',proc.returncode==0)
    except Exception as exc:report['error']=type(exc).__name__+': '+str(exc);raise
    finally:
        server.terminate()
        try:server.wait(timeout=10)
        except subprocess.TimeoutExpired:server.kill();server.wait()
        stdout.close();stderr.close()
        hashes=json.loads((OUT/'preserved_hashes.json').read_text(encoding='utf-8'))
        report['preservation']['artifact_count']=len(hashes)
        report['preservation']['changed_artifacts']=[p for p,h in hashes.items() if not (ROOT/p).is_file() or hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=h]
        legacy=json.loads((OUT/'legacy_sqlite.json').read_text(encoding='utf-8'));mismatches=[]
        with Store().connect() as con:
            for table,rows in legacy.items():
                for row in rows:
                    current=con.execute(f'SELECT * FROM {table} WHERE id=?',(row['id'],)).fetchone()
                    if current is None or any(current[k]!=v for k,v in row.items()):mismatches.append((table,row['id']))
        report['preservation']['changed_legacy_rows']=mismatches
        report['passed']=not report.get('error') and not report['preservation']['changed_artifacts'] and not mismatches
        (OUT/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
        print(json.dumps({'passed':report['passed'],'checks':len(checks),'preservation':report['preservation']},ensure_ascii=False))
if __name__=='__main__':run()
