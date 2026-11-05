"""Full v6 verification against an isolated real-database backup, never production fixtures."""
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

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'reports/stage6'
DEMO=['У меня 800 литров коровьего навоза и реактор 90 литров. Как лучше его переработать?',
      'Рабочий объём 65 литров','Сравни 35 и 38 градусов','А что выгоднее — продать или переработать?']


def write(name,data):
    (OUT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')


def command(name,args,cwd=ROOT,env=None):
    selected=dict(os.environ,PYTHONUTF8='1',**(env or {}))
    result=subprocess.run(args,cwd=cwd,env=selected,capture_output=True)
    (OUT/name).write_bytes(result.stdout+result.stderr)
    if result.returncode:raise RuntimeError(name+' failed: inspect log')
    return (result.stdout+result.stderr).decode('utf-8',errors='replace')


def preserved():
    hashes=json.loads((OUT/'preserved_hashes.json').read_text(encoding='utf-8'))
    changed=[p for p,h in hashes.items() if not (ROOT/p).is_file() or hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=h]
    old=json.loads((OUT/'legacy_sqlite.json').read_text(encoding='utf-8'))
    with closing(sqlite3.connect(ROOT/'data/market/market.sqlite3')) as con:
        con.row_factory=sqlite3.Row
        rows={table:{r['id']:dict(r) for r in con.execute('SELECT * FROM '+table)} for table in ['observations','dashboard_turns','scenarios']}
    unchanged={table:all(all(rows[table].get(r['id'],{}).get(k)==v for k,v in r.items()) for r in old[table]) for table in rows}
    return {'protected_artifacts':len(hashes),'changed_artifacts':changed,'prior_rows_unchanged':unchanged,
            'production_prices':len(rows['observations']),'production_test_prices':sum(r['is_test'] for r in rows['observations'].values())}


def run():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reuse-build',action='store_true')
    parser.add_argument('--reuse-tests',action='store_true')
    parser.add_argument('--skip-browser',action='store_true')
    args=parser.parse_args();OUT.mkdir(exist_ok=True)
    npm='npm.cmd' if os.name=='nt' else 'npm'
    command('frontend_typecheck.log' if args.reuse_build else 'frontend_build.log',[npm,'run','typecheck' if args.reuse_build else 'build'],ROOT/'frontend')
    if not args.reuse_tests:
        backend=command('backend_tests.log',[sys.executable,'-m','unittest','discover','-s','tests','-v'])
        frontend=command('frontend_tests.log',[npm,'run','test'],ROOT/'frontend')
    else:
        backend=(OUT/'backend_tests.log').read_text(encoding='utf-8');frontend=(OUT/'frontend_tests.log').read_text(encoding='utf-8')
        if not re.search(r'\nOK\s*$',backend) or 'failed' in frontend:raise ValueError('Successful test logs required')
    with socket.socket() as probe:probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
    base=f'http://127.0.0.1:{port}';checks=[];dialogues=[];cli=[]
    with tempfile.TemporaryDirectory() as temporary:
        db=Path(temporary)/'QA_real_prices.sqlite3'
        with closing(sqlite3.connect(ROOT/'data/market/market.sqlite3')) as source,closing(sqlite3.connect(db)) as target:source.backup(target)
        env={'BIOREACTOR_MARKET_DB':str(db),'BIOREACTOR_QA_URL':base,'BIOREACTOR_QA_ISOLATED':'1'}
        for index,options in enumerate([['market','status'],['predict','--model','stage1','--input','examples/stage1_5_measured.json'],
                                        ['predict','--model','stage1_5','--input','examples/stage1_5_measured.json'],
                                        ['chat','--no-llm','--message',DEMO[0],'--json']]):
            output=command(f'cli_{index}.log',[sys.executable,'main.py',*options],env=env)
            cli.append({'args':options,'returncode':0})
        identifier=json.loads(output)['memory']['conversation_id']
        command('cli_resume.log',[sys.executable,'main.py','chat','--no-llm','--conversation',identifier,'--message',DEMO[1],'--json'],env=env)
        cli.append({'resume':True,'returncode':0})
        serverlog=(OUT/'http_server.log').open('wb')
        proc=subprocess.Popen([sys.executable,'main.py','dashboard','--no-browser','--no-scheduler','--port',str(port)],
                              cwd=ROOT,env=dict(os.environ,PYTHONUTF8='1',**env),stdout=serverlog,stderr=subprocess.STDOUT,
                              creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        def call(method,path,body=None):
            request=urllib.request.Request(base+path,method=method,data=json.dumps(body,ensure_ascii=False).encode('utf-8') if body is not None else None,headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(request,timeout=120) as response:
                data=response.read();kind=response.headers.get('content-type','');checks.append({'method':method,'path':path,'http':response.status})
            return json.loads(data) if 'application/json' in kind else data
        try:
            for _ in range(150):
                try:call('GET','/health');break
                except OSError:
                    if proc.poll() is not None:raise RuntimeError('QA server exited')
                    time.sleep(.1)
            else:raise TimeoutError('QA server did not start')
            for path in ['/dashboard/','/api/dashboard/status','/api/dashboard/scientific','/api/dashboard/reactor','/api/process/scenarios','/api/experiments','/api/experiments/schema']:
                call('GET',path)
            session=call('POST','/api/dashboard/chat/sessions',{'conversation_version':'5.6','mode':'offline'})
            for index,message in enumerate(DEMO):
                started=time.perf_counter()
                reply=call('POST',f'/api/dashboard/chat/sessions/{session["id"]}/messages',{'message':message,'request_id':f'stage6_actual_{index:03d}'})
                assert reply['mode']=='llm_tools','Real Ollama did not supply a valid structured response'
                assert reply['memory']['derived']['material_volume_l']['value']==800
                assert reply['memory']['facts']['reactor_total_volume_l']['value']==90
                if index>0:assert reply['memory']['facts']['reactor_working_volume_l']['value']==65
                if index==0:assert reply['pending_question']['id']=='working_volume'
                if index==2:
                    result=next(r['result'] for r in reply['tools'] if r['tool']=='compare_process_scenarios')
                    assert len(result['scenarios'])==2
                    assert all(s['predicted_outputs']['methane']['potential_methane_m3'] is None for s in result['scenarios'])
                if index==3:assert 'get_market_prices' in reply['policy_tool_plan']
                dialogues.append({'message':message,'reply':reply,'latency_seconds':time.perf_counter()-started})
            write('actual_ollama_dialogue.json',dialogues)
            paragraphs=['# Реальный последовательный диалог v6 с Ollama','', 'Контрольные сообщения из задания; не независимый пользовательский benchmark.','']
            for row in dialogues:paragraphs.extend(['**Пользователь:** '+row['message'],'',row['reply']['answer'],''])
            (OUT/'actual_dialogue.md').write_text('\n'.join(paragraphs),encoding='utf-8')
            request={'label':'TEST hypothetical physical worksheet, not an operating recommendation','material':'cattle_manure','mass_kg':10,'feedstock_volume_l':10,
                'reactor_total_volume_l':90,'reactor_working_volume_l':65,'operating_mode':'batch','reactor_type':'TEST vessel',
                'inoculum_description':'TEST explicit inoculum scenario','gas_storage_conditions':'TEST not engineering approval','inoculum_volume_l':0,'dilution_water_l':0,'resident_liquid_volume_l':0,
                'batch_duration_days':1,'turnaround_days':0,'heated_mass_kg':10,'heat_capacity_kj_kg_k':4,'initial_temperature_c':20,'ambient_temperature_c':20,
                'heater_efficiency':.8,'heat_loss_coefficient_w_k':2,'duration_days':1,'auxiliary_energy_kwh':.1,'energy_scope':'entire_feedstock',
                'vs_mass_kg':1,'bmp_ml_ch4_g_vs':300,'bmp_unit':'mL CH4/g VS','bmp_provenance':'scenario_assumption','bmp_evidence':'TEST user-supplied arithmetic example, not measured BMP',
                'gas_volume_basis':'TEST dry gas reference, no normalization certification','objectives':['energy','methane'],
                'candidates':[{'label':f'TEST {t} C','overrides':{'temperature_c':t},'rationale':'TEST explicit temperature hypothesis'} for t in [35,38]],
                'sensitivity':[{'parameter':'temperature_c','low':35,'high':38,'provenance':'USER_DEFINED_RANGE','evidence':'TEST explicit endpoints'}]}
            first=call('POST','/api/process/optimize',request)
            second=call('POST','/api/process/optimize',{**request,'label':'TEST second snapshot'})
            call('GET','/api/process/scenarios/'+first['id'])
            compared=call('POST','/api/process/compare',{'scenario_ids':[first['id'],second['id']],'objectives':['energy','methane']})
            assert len(compared['scenarios'])==4
            write('physical_worksheet.json',first)
            item=call('POST','/api/experiments',{'name':'TEST HTTP record in temporary QA database only','origin':'user','material':'cattle_manure','volume_l':5})
            call('POST',f'/api/experiments/{item["id"]}/measurements',{'temperature_c':35,'gas_volume_m3':.002,'gas_volume_basis':'TEST input reference','measurement_method':'TEST manual record'})
            comparison=call('GET',f'/api/experiments/{item["id"]}/comparison')
            assert comparison['measured_methane_m3'] is None
            exported=call('GET',f'/api/experiments/{item["id"]}/export.csv')
            assert b'TEST' in exported
            call('PATCH',f'/api/experiments/{item["id"]}',{'name':'TEST revised HTTP record'})
            revisions=call('GET',f'/api/experiments/{item["id"]}/revisions');assert len(revisions['revisions'])==2
            if not args.skip_browser:
                command('browser.log',['node','tests/process-browser.mjs'],ROOT/'frontend',env=env)
        finally:
            proc.terminate()
            try:proc.wait(timeout=10)
            except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=5)
            serverlog.close()
    with socket.socket() as probe:stopped=probe.connect_ex(('127.0.0.1',port))!=0
    result=preserved()
    browser=None if args.skip_browser else json.loads((OUT/'browser.json').read_text(encoding='utf-8'))
    result.update(backend_tests=int(re.search(r'Ran (\d+) tests',backend)[1]),frontend_tests=int(re.search(r'Tests\s+(\d+) passed',frontend)[1]),
                  direct_http_checks=len(checks),cli_checks=len(cli),real_ollama_dialogue_turns=len(dialogues),
                  browser_checks=len(browser['checks']) if browser else None,browser_verified=browser is not None,
                  models_retrained=False,qa_server_stopped=stopped,test_database_was_isolated=True,
                  build_reused=args.reuse_build,test_logs_reused=args.reuse_tests)
    result['all_passed']=not result['changed_artifacts'] and all(result['prior_rows_unchanged'].values()) and result['production_test_prices']==0 and stopped and (browser is None or browser['passed'])
    write('http_checks.json',checks);write('cli_checks.json',cli);write('verification.json',result)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result['all_passed'] else 1


if __name__=='__main__':raise SystemExit(run())
