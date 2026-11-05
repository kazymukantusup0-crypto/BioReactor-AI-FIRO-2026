"""Verify the real local dashboard without retraining or overwriting old reports."""
import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request
import main

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'reports/stage4'


def write(name,value):
    (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')


def command(name,args,cwd=ROOT,env=None):
    proc=subprocess.run(args,cwd=cwd,env=env,capture_output=True)
    payload=proc.stdout+proc.stderr;(OUT/name).write_bytes(payload)
    if proc.returncode:
        print(payload.decode('utf-8',errors='replace'));raise RuntimeError('Check failed: '+name)
    return payload.decode('utf-8',errors='replace')


def run():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reuse-build',action='store_true',help='Use the successful existing production build')
    parser.add_argument('--skip-browser',action='store_true',help='Skip Chrome checks; reports this limitation explicitly')
    args=parser.parse_args();OUT.mkdir(exist_ok=True)
    npm='npm.cmd' if os.name=='nt' else 'npm'
    if not args.reuse_build:command('frontend_build.log',[npm,'run','build'],ROOT/'frontend')
    elif not (ROOT/'frontend/dist/index.html').is_file():raise RuntimeError('No production build to reuse')
    else:command('frontend_typecheck.log',[npm,'run','typecheck'],ROOT/'frontend')
    frontend=command('frontend_tests.log',[npm,'run','test'],ROOT/'frontend')
    backend=command('backend_tests.log',[sys.executable,'-m','unittest','discover','-s','tests','-v'])
    backend_count=re.search(r'Ran (\d+) tests',backend)
    frontend_count=re.search(r'Tests\s+(\d+) passed',frontend)
    cli=[]
    for index,options in enumerate([['dashboard','--help'],['market','status'],
        ['predict','--model','stage1','--input','examples/stage1_5_measured.json'],
        ['predict','--model','stage1_5','--input','examples/stage1_5_measured.json'],
        ['chat','--no-llm','--message','Какая точность у модели BMP?','--json']]):
        output=command(f'cli_{index}.log',[sys.executable,'main.py',*options])
        cli.append({'args':options,'returncode':0})
    write('cli_checks.json',cli)
    checks=[]
    with socket.socket() as probe:probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
    base=f'http://127.0.0.1:{port}'
    with tempfile.TemporaryDirectory() as temp:
        database=Path(temp)/'real_market_backup.sqlite3'
        with closing(sqlite3.connect(ROOT/'data/market/market.sqlite3')) as source,closing(sqlite3.connect(database)) as target:source.backup(target)
        env=dict(os.environ,BIOREACTOR_MARKET_DB=str(database),PYTHONUTF8='1',BIOREACTOR_QA_URL=base)
        logfile=(OUT/'http_server.log').open('wb')
        proc=subprocess.Popen([sys.executable,'main.py','dashboard','--port',str(port),'--no-browser','--no-scheduler'],cwd=ROOT,env=env,
            stdout=logfile,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        def call(method,path,body=None):
            req=urllib.request.Request(base+path,method=method,data=json.dumps(body,ensure_ascii=False).encode() if body is not None else None,headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(req,timeout=20) as response:
                raw=response.read();kind=response.headers.get('content-type','')
                checks.append({'method':method,'path':path,'http_status':response.status,'bytes':len(raw)})
            return json.loads(raw) if 'application/json' in kind else raw
        try:
            for _ in range(120):
                try:call('GET','/health');break
                except OSError:
                    if proc.poll() is not None:raise RuntimeError('Dashboard did not start')
                    time.sleep(.1)
            else:raise TimeoutError('Server readiness timeout')
            for path in ['/dashboard/','/catalog','/sources/status','/prices/current?region=KZ-Karaganda',
                '/prices/history?commodity=electricity&region=KZ-Karaganda','/analytics/price-change?commodity=electricity&region=KZ-Karaganda',
                '/api/dashboard/status','/api/dashboard/overview','/api/dashboard/models/stage1/schema','/api/dashboard/models/stage1_5/schema',
                '/api/dashboard/economics/schema','/api/dashboard/reactor','/api/dashboard/reactor/contract','/api/dashboard/scientific',
                '/api/dashboard/scientific/figures/stage1_test_errors','/api/dashboard/demo']:
                call('GET',path)
            session=call('POST','/api/dashboard/chat/sessions',{'mode':'no_llm','context':{'market_region':'KZ-Karaganda'}})
            reply=call('POST',f"/api/dashboard/chat/sessions/{session['id']}/messages",{'message':'У меня 5 кг пищевых отходов и реактор объёмом 90 литров. Сколько метана можно получить и выгодно ли его производить?','request_id':'stage4_real_http_001'})
            assert reply['mode']=='deterministic_tools_no_llm' and reply['tools']
            call('GET',f"/api/dashboard/chat/sessions/{session['id']}")
            write('actual_http_dialogue.json',reply)
            if not args.skip_browser:command('browser.log',[npm,'run','test:browser'],ROOT/'frontend',env)
        finally:
            proc.terminate()
            try:proc.wait(timeout=10)
            except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=5)
            logfile.close()
    with socket.socket() as check:server_stopped=check.connect_ex(('127.0.0.1',port))!=0
    protected=json.loads((OUT/'preserved_hashes.json').read_text(encoding='utf-8'))
    changed=[name for name,digest in protected.items() if not (ROOT/name).is_file() or hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest]
    old=json.loads((OUT/'legacy_observations.json').read_text(encoding='utf-8'))
    with closing(sqlite3.connect(ROOT/'data/market/market.sqlite3')) as connection:
        connection.row_factory=sqlite3.Row
        current={r['id']:dict(r) for r in connection.execute('SELECT * FROM observations')}
    prices_preserved=all(current.get(p['id'])==p for p in old)
    artifacts={str(p.relative_to(ROOT/'frontend/dist')):{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in (ROOT/'frontend/dist').rglob('*') if p.is_file()}
    browser=None if args.skip_browser else json.loads((OUT/'browser_checks.json').read_text(encoding='utf-8'))
    write('build_artifacts.json',artifacts)
    write('http_checks.json',{'base_url':base,'requests':len(checks),'checks':checks,'server_stopped':server_stopped,'data':'QA backup of actual market prices; no fictitious observations'})
    result={'all_passed':not changed and prices_preserved and server_stopped,'backend_tests':int(backend_count[1]) if backend_count else None,
        'frontend_tests':int(frontend_count[1]) if frontend_count else None,'typecheck_passed':True,'production_build_present':True,'existing_build_reused':args.reuse_build,
        'real_direct_http_requests':len(checks),'browser_verified':browser is not None,'browser_checks':len(browser['checks']) if browser else None,
        'browser_http_requests':browser['http_requests'] if browser else None,'chrome_version':browser['browser'] if browser else None,
        'actual_ollama_generation':any(p.get('actual_generation') and p['status']=='available' for p in browser['actual_agent']['provider_status']) if browser else False,
        'screenshots':browser['screenshots'] if browser else [],'artifacts_checked':len(protected),'changed_artifacts':changed,
        'prior_market_observations':len(old),'prior_market_observations_unchanged':prices_preserved,'production_observations':len(current),
        'production_test_observations':sum(p['is_test'] for p in current.values()),'models_retrained':False,'qa_server_stopped':server_stopped}
    write('verification.json',result);print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result['all_passed'] else 1


if __name__=='__main__':raise SystemExit(run())
