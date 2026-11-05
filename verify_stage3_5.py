"""Real TCP checks using a backup of real prices; fixtures exist only in tests.

No BMP training, no old-report writes, no fabricated quotations or physics.
Use --update to request actual verified HTTPS adapters (source backoff applies).
"""
import argparse
import csv
from contextlib import closing
import hashlib
import io
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
import urllib.error
import urllib.request
import zipfile
from unittest.mock import patch
import main
from src.market.service import get_store
from src.market.store import Store
from src.market.scenarios import select_price,ScenarioInput
from src.market.adapters import fetch_source

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'reports/stage3_5'


def write(name,value):
    (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')


def http_check(db):
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    env=dict(os.environ,BIOREACTOR_MARKET_DB=str(db),BIOREACTOR_MARKET_SCHEDULER='0',PYTHONUTF8='1')
    logfile=(OUT/'http_server.log').open('wb')
    proc=subprocess.Popen([sys.executable,str(ROOT/'main.py'),'market','serve','--port',str(port)],cwd=ROOT,
        env=env,stdout=logfile,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    base=f'http://127.0.0.1:{port}';checks=[]
    def call(method,path,data=None,expected=200):
        req=urllib.request.Request(base+path,data=json.dumps(data).encode() if data is not None else None,
            headers={'Content-Type':'application/json'},method=method)
        try:
            with urllib.request.urlopen(req,timeout=10) as response:code=response.status;body=json.load(response)
        except urllib.error.HTTPError as exc:code=exc.code;body=json.load(exc)
        checks.append({'method':method,'path':path,'http_status':code,'expected':expected})
        assert code==expected,(path,code,body)
        return body
    try:
        for _ in range(100):
            try:call('GET','/health');break
            except urllib.error.URLError:
                if proc.poll() is not None:raise RuntimeError('Local server exited before becoming ready')
                time.sleep(.1)
        else:raise TimeoutError('Local server did not start')
        for path in ['/catalog','/sources','/sources/status','/prices/current','/prices/current?region=KZ-Karaganda',
            '/prices/current?region=KZ-Karaganda&commodity=natural_gas','/prices/current?region=KZ-Karaganda&commodity=electricity',
            '/prices/current?region=KZ-national','/prices/current?region=KZ-Karaganda-Abay-district',
            '/prices/current?region=KZ-Almaty','/prices/current?region=KZ-Karaganda&max_age_days=0',
            '/prices/history?commodity=natural_gas&region=KZ-Karaganda',
            '/prices/history?commodity=electricity&region=KZ-Karaganda',
            '/prices/history?commodity=natural_gas&region=KZ-national',
            '/prices/history?commodity=electricity&region=KZ-Almaty',
            '/analytics/price-change?commodity=natural_gas&region=KZ-Karaganda',
            '/analytics/price-change?commodity=electricity&region=KZ-Karaganda&as_of=2026-09-30',
            '/analytics/price-change?commodity=electricity&region=KZ-Karaganda&as_of=2026-08-31','/updates']:
            body=call('GET',path)
            if path=='/prices/current':assert body['prices'] and not any(p['is_test'] for p in body['prices'])
            if path=='/analytics/price-change?commodity=natural_gas&region=KZ-Karaganda':
                assert all(w['percent_change'] is None for s in body['series'] for w in s['windows_days'].values())
        result=call('POST','/scenarios/compare',{'region':'KZ-Karaganda','mass_kg':20})
        assert result['final_recommendation'] is None and result['status']=='needs_input'
        ident=result['scenario_id']
        call('GET','/scenarios');call('GET',f'/scenarios/{ident}');impact=call('GET',f'/scenarios/{ident}/price-impact')
        assert impact['current_recommendation'] is None
        call('GET','/scenarios/999999999/price-impact',expected=404)
        call('GET','/prices/history?commodity=electricity&region=KZ-Karaganda&start=bad',expected=422)
        call('POST','/prices',{'unit':'invented'},expected=422)
        call('POST','/scenarios/compare',{'mass_kg':-20},expected=422)
        call('POST','/updates?category=bad',expected=422)
        call('POST','/sources',{},expected=422)
    finally:
        proc.terminate()
        try:proc.wait(timeout=10)
        except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=5)
        logfile.close()
    result={'base_url':base,'real_tcp_requests':len(checks),'all_passed':True,
        'database':'temporary backup of production prices, no fictitious observations','server_stopped':True,'checks':checks}
    write('http_checks.json',result);return result


def reparse_saved_sources(store):
    """Recheck archived HTTPS payloads with current parsers, without extra requests."""
    results=[];sources={s['id']:s for s in store.sources()}
    for path in (store.path.parent/'raw').glob('*.bin'):
        payload=path.read_bytes()
        if not zipfile.is_zipfile(io.BytesIO(payload)):continue
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            if 'manifest.json' not in archive.namelist():continue
            manifest=json.loads(archive.read('manifest.json'))
            docs={d['url']:archive.read(d['file']) for d in manifest}
            for d in manifest:assert hashlib.sha256(docs[d['url']]).hexdigest()==d['sha256']
            if 'https://krec.kz/price' in docs:ids=['krec_district_supply']
            elif sources['bns_retail_gas']['url'] in docs:ids=['bns_retail_gas','bns_retail_electricity']
            else:continue
            for ident in ids:
                with patch('src.market.official.public_get',side_effect=lambda url:docs[url]):
                    rows,_=fetch_source(sources[ident])
                dedup=store.import_prices(rows)
                assert dedup['inserted']==0,'Reparse must not alter observation history'
                results.append({'source':ident,'archive':path.name,'parsed':len(rows),'duplicates':dedup['duplicates']})
    write('archived_reparse.json',results)


def run():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--update',action='store_true',help='Actual HTTPS update, subject to daily/backoff limits')
    parser.add_argument('--skip-tests',action='store_true',help='Reuse an existing successful tests.log while debugging verification only')
    args=parser.parse_args();OUT.mkdir(parents=True,exist_ok=True)
    store=get_store()
    if args.update:
        from src.market.updater import Updater
        write('verification_live_update.json',Updater(store).update_all())
    if args.skip_tests:
        log=(OUT/'tests.log').read_bytes()
        if not re.search(rb'\nOK\s*$',log):raise RuntimeError('No successful test run to reuse')
    else:
        tests=subprocess.run([sys.executable,'-m','unittest','discover','-s',str(ROOT/'tests'),'-v'],cwd=ROOT,capture_output=True)
        log=tests.stdout+tests.stderr;(OUT/'tests.log').write_bytes(log)
        if tests.returncode:print(log.decode(errors='replace'));return 1
    count=re.search(rb'Ran (\d+) tests',log)
    # Read-only checks on actual market records, no fabricated processing inputs.
    reparse_saved_sources(store)
    prices=store.prices();write('real_observations.json',prices);write('source_states.json',store.source_states())
    with (OUT/'real_observations.csv').open('w',encoding='utf-8-sig',newline='') as file:
        writer=csv.DictWriter(file,fieldnames=list(prices[0]));writer.writeheader();writer.writerows(prices)
    request=ScenarioInput(region='KZ-Karaganda-Abay-district',currency='KZT',consumer_class='non_household',tax_basis='VAT_included')
    quote=select_price(store,request,'electricity');assert quote['validation_status']=='VERIFIED_CURRENT'
    write('economic_quote_selection.json',{'selected_quote':quote,'profit_calculated':False,
        'reason':'No measured VS/recovery/efficiency/costs or local feedstock bids were supplied; no economic quantities invented.'})
    cli=[]
    for command in [['market','status'],['predict','--model','stage1','--input','examples/wheat_straw.json'],
        ['predict','--model','stage1_5','--input','examples/wheat_straw.json']]:
        result=subprocess.run([sys.executable,'main.py',*command],cwd=ROOT,capture_output=True)
        cli.append({'args':command,'returncode':result.returncode,'output':result.stdout.decode('utf-8',errors='replace')})
        assert result.returncode==0,command
    write('cli_checks.json',cli)
    with tempfile.TemporaryDirectory() as temp:
        db=Path(temp)/'real_prices_backup.sqlite3'
        with closing(sqlite3.connect(store.path)) as origin,closing(sqlite3.connect(db)) as target:origin.backup(target)
        http=http_check(db)
        from src.agent.orchestrator import Agent
        from src.agent.tools import ToolRegistry
        question='У меня 20 кг пищевых отходов в Караганде. Что выгоднее: продать или переработать в биогаз?'
        reply=Agent(mode='offline',registry=ToolRegistry(Store(db))).ask(question)
        write('actual_agent_dialogue.json',{'question':question,'reply':reply})
        (OUT/'actual_agent_dialogue.md').write_text('# Реальный агент и сохранённые реальные цены\n\n'+question+'\n\n'+reply['answer'],encoding='utf-8')
        assert next(t['result'] for t in reply['tools'] if t['tool']=='get_market_prices')['prices']
        assert next(t['result'] for t in reply['tools'] if t['tool']=='compare_market_scenarios')['final_recommendation'] is None
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    figure,axes=plt.subplots(2,1,figsize=(10,7))
    for ax,commodity,label in zip(axes,['natural_gas','electricity'],['Natural gas, KZT/m3','Electricity, KZT/kWh, tier 1 / electric stove']):
        for region in ['KZ-Karaganda','KZ-national']:
            series=sorted((p for p in prices if p['commodity']==commodity and p['region']==region and p['price_type']=='reference'),key=lambda p:p['effective_from'])
            ax.plot([p['effective_from'] for p in series],[float(p['normalized_value']) for p in series],marker='o',label=region)
        ax.set_ylabel(label);ax.legend();ax.grid(alpha=.3)
    figure.suptitle('BNS monthly household reference statistics, NOT trade quotes')
    figure.tight_layout();figure.savefig(OUT/'price_history.png',dpi=160);plt.close(figure)
    protected=json.loads((OUT/'preserved_hashes.json').read_text(encoding='utf-8'))
    changed=[p for p,sha in protected.items() if not (ROOT/p).exists() or hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=sha]
    old=json.loads((OUT/'legacy_observations.json').read_text(encoding='utf-8'))
    with store.connect() as con:current={r['id']:dict(r) for r in con.execute('SELECT * FROM observations')}
    old_rows_ok=all(all(current.get(p['id'],{}).get(k)==v for k,v in p.items()) for p in old)
    result={'all_passed':not changed and old_rows_ok,'tests_passed':int(count[1]) if count else None,
        'real_tcp_requests':http['real_tcp_requests'],'prior_artifacts_checked':len(protected),'changed_artifacts':changed,
        'legacy_prices_checked':len(old),'legacy_prices_unchanged':old_rows_ok,'models_retrained':False,
        'production_observations':len(prices),'production_test_observations':sum(p['is_test'] for p in store.prices(include_test=True)),
        'selected_actual_electricity_price':quote['normalized_value'],'local_agent_mode':reply['mode']}
    write('verification.json',result);print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result['all_passed'] else 1


if __name__=='__main__':raise SystemExit(run())
