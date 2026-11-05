"""End-to-end verification of conversational v5.6 without touching old reports."""
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

ROOT=Path(__file__).resolve().parent;OUT=ROOT/'reports/stage5_6'


def write(name,value):
    (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')


def command(name,args,cwd=ROOT,env=None):
    selected=dict(os.environ,PYTHONUTF8='1')
    if env:selected.update(env)
    proc=subprocess.run(args,cwd=cwd,env=selected,capture_output=True)
    data=proc.stdout+proc.stderr;(OUT/name).write_bytes(data)
    if proc.returncode:raise RuntimeError(f'{name} failed; inspect {OUT/name}')
    return data.decode('utf-8',errors='replace')


def run():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reuse-build',action='store_true')
    parser.add_argument('--reuse-tests',action='store_true',help='Reuse successful logs with unchanged application/test inputs')
    parser.add_argument('--skip-browser',action='store_true')
    args=parser.parse_args();OUT.mkdir(exist_ok=True)
    npm='npm.cmd' if os.name=='nt' else 'npm'
    if not args.reuse_build:command('frontend_build.log',[npm,'run','build'],ROOT/'frontend')
    else:command('frontend_typecheck.log',[npm,'run','typecheck'],ROOT/'frontend')
    if not args.reuse_tests:
        backend=command('backend_tests.log',[sys.executable,'-m','unittest','discover','-s','tests','-v'])
        frontend=command('frontend_tests.log',[npm,'run','test'],ROOT/'frontend')
    else:
        backend=(OUT/'backend_tests.log').read_text(encoding='utf-8');frontend=(OUT/'frontend_tests.log').read_text(encoding='utf-8')
        if not re.search(r'\nOK\s*$',backend) or 'failed' in frontend:raise ValueError('No successful test logs to reuse')
    with socket.socket() as selected:selected.bind(('127.0.0.1',0));port=selected.getsockname()[1]
    base=f'http://127.0.0.1:{port}';checks=[];cli=[]
    with tempfile.TemporaryDirectory() as temp:
        database=Path(temp)/'real_market_copy.sqlite3'
        with closing(sqlite3.connect(ROOT/'data/market/market.sqlite3')) as source,closing(sqlite3.connect(database)) as target:source.backup(target)
        env=dict(os.environ,BIOREACTOR_MARKET_DB=str(database),PYTHONUTF8='1',BIOREACTOR_QA_URL=base)
        for index,options in enumerate([['market','status'],['predict','--model','stage1','--input','examples/stage1_5_measured.json'],
            ['predict','--model','stage1_5','--input','examples/stage1_5_measured.json'],['knowledge','list'],
            ['chat','--no-llm','--message','800 литров навоза. Что выгоднее?','--json']]):
            data=command(f'cli_{index}.log',[sys.executable,'main.py',*options],env=env)
            cli.append({'args':options,'returncode':0})
        restored=json.loads(data)['memory']['conversation_id']
        command('cli_resume.log',[sys.executable,'main.py','chat','--no-llm','--conversation',restored,'--message','Коровий','--json'],env=env)
        logfile=(OUT/'http_server.log').open('wb')
        proc=subprocess.Popen([sys.executable,'main.py','dashboard','--port',str(port),'--no-browser','--no-scheduler'],cwd=ROOT,env=env,stdout=logfile,stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        def call(method,path,body=None):
            request=urllib.request.Request(base+path,method=method,data=json.dumps(body,ensure_ascii=False).encode() if body is not None else None,headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(request,timeout=30) as response:
                payload=response.read();content_type=response.headers.get('content-type','');checks.append({'method':method,'path':path,'status':response.status})
            return json.loads(payload) if 'application/json' in content_type else payload
        try:
            for _ in range(120):
                try:call('GET','/health');break
                except OSError:
                    if proc.poll() is not None:raise RuntimeError('QA server exited')
                    time.sleep(.1)
            else:raise TimeoutError('QA server startup timed out')
            for path in ['/dashboard/','/catalog','/prices/current?region=KZ-Karaganda','/api/dashboard/status','/api/dashboard/scientific','/api/dashboard/reactor']:
                call('GET',path)
            session=call('POST','/api/dashboard/chat/sessions',{'mode':'no_llm','conversation_version':'5.6'})
            conversation=[]
            for index,text in enumerate(['800 литров навоза. Лучше продать или переработать? Какую температуру поставить?','Коровий','Я могу продать его за 15 000 тенге','За всю партию','А если у меня свиной навоз?','А если реактор всего 90 литров?']):
                reply=call('POST',f'/api/dashboard/chat/sessions/{session["id"]}/messages',{'message':text,'request_id':f'stage5_6_http_{index:03d}'})
                conversation.append({'message':text,'reply':reply})
            after=call('GET',f'/api/dashboard/chat/sessions/{session["id"]}')
            assert after['memory']['facts']['quantity']['value']==800 and len(after['turns'])==6
            write('actual_http_dialogue.json',conversation)
            if not args.skip_browser:command('browser.log',['node','tests/conversation-browser.mjs'],ROOT/'frontend',env)
        finally:
            proc.terminate()
            try:proc.wait(timeout=10)
            except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=5)
            logfile.close()
    # LLM timing is measured AFTER browser generation, with no QA client concurrency.
    command('deterministic_eval.log',[sys.executable,'evaluate_conversation.py'])
    command('ollama_eval.log',[sys.executable,'evaluate_conversation.py','--llm'])
    deterministic=json.loads((OUT/'deterministic_eval.json').read_text(encoding='utf-8'))
    llm=json.loads((OUT/'ollama_eval.json').read_text(encoding='utf-8'))
    baseline=json.loads((OUT/'baseline_dialogues.json').read_text(encoding='utf-8'))
    comparison={'same_prescribed_case_ids':[c['id'] for c in baseline['cases']],
        'baseline':{'cases':len(baseline['cases']),'mean_tools':sum(len(c['reply']['tools']) for c in baseline['cases'])/len(baseline['cases']),
            'request_errors':sum(c['status']=='error' for c in baseline['requests']),'requests':len(baseline['requests']),
            'latency_median_seconds':__import__('statistics').median(c['latency_seconds'] for c in baseline['cases']),
            'latency_mean_seconds':__import__('statistics').mean(c['latency_seconds'] for c in baseline['cases']),
            'max_input_characters':max(c['input_characters'] for c in baseline['requests'])},
        'after':llm['summary'],'latency_limit':'Small same-day local run; cache/load and background system activity are not controlled. Not a hardware benchmark.'}
    write('comparison.json',comparison)
    protected=json.loads((OUT/'preserved_hashes.json').read_text(encoding='utf-8'))
    changed=[name for name,digest in protected.items() if not (ROOT/name).is_file() or hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest]
    previous=json.loads((OUT/'legacy_observations.json').read_text(encoding='utf-8'))
    legacy=json.loads((OUT/'legacy_chat.json').read_text(encoding='utf-8'))
    with closing(sqlite3.connect(ROOT/'data/market/market.sqlite3')) as con:
        con.row_factory=sqlite3.Row;prices={r['id']:dict(r) for r in con.execute('SELECT * FROM observations')}
        turns={r['id']:dict(r) for r in con.execute('SELECT * FROM dashboard_turns')}
    prices_ok=all(prices.get(p['id'])==p for p in previous)
    turns_ok=all(all(turns.get(row['id'],{}).get(k)==v for k,v in row.items()) for row in legacy['turns'])
    with socket.socket() as probe:stopped=probe.connect_ex(('127.0.0.1',port))!=0
    browser=None if args.skip_browser else json.loads((OUT/'conversation_browser.json').read_text(encoding='utf-8'))
    result={'all_passed':not changed and prices_ok and turns_ok and stopped and all(r['passed'] for r in deterministic['cases']+llm['cases']),
        'backend_tests':int(re.search(r'Ran (\d+) tests',backend)[1]),'frontend_tests':int(re.search(r'Tests\s+(\d+) passed',frontend)[1]),
        'deterministic_cases':deterministic['summary'],'real_ollama_cases':llm['summary'],'browser_verified':browser is not None,
        'browser_checks':len(browser['checks']) if browser else None,'direct_http_requests':len(checks),'cli_checks':len(cli)+1,
        'protected_artifacts':len(protected),'changed_artifacts':changed,'prior_prices_unchanged':prices_ok,'prior_chat_turns_unchanged':turns_ok,
        'production_observations':len(prices),'production_test_observations':sum(p['is_test'] for p in prices.values()),'models_retrained':False,
        'qa_server_stopped':stopped,'build_reused':args.reuse_build,'test_logs_reused':args.reuse_tests}
    write('http_checks.json',checks);write('cli_checks.json',cli);write('verification.json',result)
    print(json.dumps(result,ensure_ascii=False,indent=2));return 0 if result['all_passed'] else 1


if __name__=='__main__':raise SystemExit(run())
