"""Real loopback HTTP checks plus source status; fixture prices stay in a separate TEST DB."""
from pathlib import Path
import csv
import hashlib
import io
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
sys.path.insert(0,str(Path(__file__).resolve().parent))
import main
from src.market.service import get_store
from src.market.updater import Updater
from src.market.adapters import public_get
from src.market.domain import utcnow

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'reports/stage3'


def write(name,value):
    (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')


def verified_browser_observations():
    # Genuine published tariff values independently read using the web tool.
    # Effective dates are NOT substituted for unknown publication dates.
    common={'source_id':'esalmaty_business','commodity':'electricity','country':'KZ','region':'KZ-Almaty','currency':'KZT','unit':'kWh',
        'published_at':None,'price_type':'tariff','reliability':'verified_manual','consumer_class':'non_household_group2','tax_basis':'VAT_included',
        'evidence':'Manually checked on official supplier page using web tool, 2026-10-28. Non-household group 2, VAT included. Publication date not stated; not a current verified quote.'}
    return [{**common,'value':'46.25','effective_from':'2026-06-05','source_url':'https://www.esalmaty.kz/ru/i4160'},
            {**common,'value':'50.03','effective_from':'2026-09-12','source_url':'https://www.esalmaty.kz/ru/business-tariffs'}]


def http_check():
    # A separate temporary database is mandatory for TEST HTTP imports/scenarios.
    sys.path.insert(0,str(ROOT/'tests'))
    from test_market import fixture,scenario_input
    checks=[]
    with tempfile.TemporaryDirectory(prefix='bioreactor-http-TEST-') as temp:
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        base=f'http://127.0.0.1:{port}'
        env=dict(os.environ,BIOREACTOR_MARKET_DB=str(Path(temp)/'TEST.sqlite3'),BIOREACTOR_MARKET_SCHEDULER='0')
        logfile=(OUT/'http_server.log').open('w',encoding='utf-8')
        flags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
        proc=subprocess.Popen([sys.executable,str(ROOT/'main.py'),'market','serve','--port',str(port)],env=env,stdout=logfile,stderr=logfile,creationflags=flags)
        def call(method,path,body=None):
            request=urllib.request.Request(base+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json'},method=method)
            with urllib.request.urlopen(request,timeout=10) as response:
                result=json.loads(response.read());status=response.status
            checks.append({'method':method,'path':path,'http_status':status,'response':result})
            return result
        try:
            deadline=time.monotonic()+15
            while True:
                try:
                    health=call('GET','/health')
                    if health['database']!=env['BIOREACTOR_MARKET_DB']:raise RuntimeError('Connected to unexpected server')
                    break
                except OSError:
                    if time.monotonic()>deadline or proc.poll() is not None:raise
                    time.sleep(.1)
            call('GET','/catalog');call('GET','/sources')
            for ident,category in [('test_feed','organic_feedstock'),('test_power','electricity'),('test_gas','natural_gas'),('test_fert','organic_fertilizer')]:
                call('POST','/sources',dict(id=ident,name='TEST only',url='https://example.invalid/TEST',category=category))
            quotes=[fixture(),fixture('electricity',10,'kWh','test_power'),fixture('raw_biogas',30,'m3','test_gas'),fixture('digestate',1,'kg','test_fert')]
            for p in quotes:call('POST','/prices',p)
            for p in verified_browser_observations():call('POST','/prices',p)
            latest=call('GET','/prices/current?region=KZ-Almaty')['prices']
            assert len(latest)==1 and not latest[0]['usable_as_current']
            assert call('GET','/prices/history?commodity=electricity&region=KZ-Almaty')['total']==2
            actual_change=call('GET','/analytics/price-change?commodity=electricity&region=KZ-Almaty')['series'][0]['percent_change']
            assert abs(actual_change-(50.03/46.25-1)*100)<1e-9
            csv_buffer=io.StringIO();writer=csv.DictWriter(csv_buffer,fieldnames=list(quotes[0]));writer.writeheader();writer.writerow(quotes[0])
            assert call('POST','/prices/import-csv',{'csv_text':csv_buffer.getvalue()})['duplicates']==1
            assert call('POST','/prices',quotes[0])['duplicates']==1
            assert call('GET','/prices/current?region=KZ-TEST')['prices']==[]
            call('GET','/prices/history?commodity=electricity&region=KZ-TEST')
            call('GET','/analytics/price-change?commodity=electricity&region=KZ-TEST')
            result=call('POST','/scenarios/compare',scenario_input())
            assert [s['net_profit'] for s in result['scenarios']]==[38,140,240,-40]
            call('GET',f'/scenarios/{result["scenario_id"]}')
            assert call('POST','/scenarios/compare',{'mass_kg':20})['recommended_scenario'] is None
            call('GET','/updates')
            call('POST','/updates?category=organic_fertilizer')
        finally:
            proc.terminate()
            try:proc.wait(timeout=10)
            except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=5)
            logfile.close()
    write('http_checks.json',{'base_url':base,'real_tcp_requests':len(checks),'all_passed':True,'test_database_isolated':True,'server_stopped_after_verification':True,'checks':checks})
    return len(checks)


def run():
    OUT.mkdir(parents=True,exist_ok=True)
    test=subprocess.run([sys.executable,'-m','unittest','discover','-s',str(ROOT/'tests'),'-v'],capture_output=True,text=True,encoding='utf-8',errors='replace')
    (OUT/'tests.log').write_text(test.stdout+test.stderr,encoding='utf-8')
    store=get_store()
    manual=store.import_prices(verified_browser_observations())
    write('manual_verified_observations.json',{'method':'manual official-browser verification, not automated scraping','observations':verified_browser_observations(),'import_result':manual})
    updates=Updater(store).update_all()
    write('real_update_attempt.json',updates)
    source_status=[]
    gas_source=next(s for s in store.sources() if s['id']=='qazaqgaz_aimaq')
    try:
        payload=public_get(gas_source['url'])
        source_status.append({'id':gas_source['id'],'catalogue_download':'success','bytes':len(payload),'numeric_price_extraction':'not_implemented_manual_DOC_review_required'})
    except Exception as exc:
        source_status.append({'id':gas_source['id'],'catalogue_download':'error','error':str(exc),'numeric_price_extraction':'manual_DOC_review_required'})
    write('external_source_status.json',{'updates':updates,'catalogue_probes':source_status,'tls_verification_disabled':False})
    count=http_check()
    # Agent shares real saved data without depending on the HTTP server being up.
    from src.agent.orchestrator import Agent
    from src.agent.providers import HybridLLM
    from src.agent.tools import ToolRegistry
    query='У меня 20 кг пищевых отходов в Алматы. Что выгоднее: продать или переработать в биогаз?'
    reply=Agent(mode='auto',registry=ToolRegistry(store)).ask(query)
    write('actual_agent_dialogue.json',{'question':query,'reply':reply})
    (OUT/'actual_agent_dialogue.md').write_text('# Реальный вызов рыночных инструментов\n\n'+query+'\n\n'+
        ' → '.join(t['tool']+' ['+t['status']+']' for t in reply['tools'])+'\n\n'+reply['answer'],encoding='utf-8')
    protected=json.loads((OUT/'preserved_hashes.json').read_text(encoding='utf-8'))
    changed=[p for p,sha in protected.items() if not (ROOT/p).exists() or hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=sha]
    write('preservation_check.json',{'files_checked':len(protected),'changed_files':changed,'all_preserved':not changed})
    result={'all_passed':test.returncode==0 and not changed,'tests_returncode':test.returncode,'real_http_requests':count,
        'prior_artifacts_unchanged':not changed,'models_retrained':False,'production_test_price_count':len([p for p in store.prices(include_test=True) if p['is_test']]),
        'latest_known_prices':store.prices(latest=True),'external_source_status_file':'external_source_status.json'}
    write('verification.json',result)
    print(test.stdout+test.stderr)
    print(json.dumps({k:v for k,v in result.items() if k!='latest_known_prices'},indent=2,ensure_ascii=False))
    return 0 if result['all_passed'] else 1


if __name__=='__main__':raise SystemExit(run())
