"""Real Qwen HTTP evaluation, resumable; preserves every first attempt."""
import argparse
import hashlib
import json
import statistics
import subprocess
import sys
import time
import uuid
from pathlib import Path
from stage9_smoke import ROOT,http

def source_hash():
    digest=hashlib.sha256()
    for folder in ['src/agent','src/dashboard','src/advisor','src/economics']:
        for path in sorted((ROOT/folder).glob('*.py')):
            digest.update(path.relative_to(ROOT).as_posix().encode());digest.update(path.read_bytes())
    return digest.hexdigest()

def check(case,reply,job):
    meta=reply.get('technical_metadata',{});tools={t['tool']:t['result'] for t in reply.get('tools',[])}
    names={'science':'assess_substrate_potential','economics':'evaluate_partial_economics','process':'assess_process_evidence'}
    facts=reply.get('memory',{}).get('facts',{})
    checks={'actual_qwen3_8b':any(p.get('model')=='qwen3:8b' and p.get('actual_generation') for p in reply.get('provider_status',[])),
        'terminal_completed':job['status']=='COMPLETED','qwen_synthesis':meta.get('final_author')=='qwen_verified',
        'no_actuation':reply.get('actuator_access') is False,'main_tools_checked':all(names[n] in tools for n in case['needs']),
        'independent_checks_passed':meta.get('verification',{}).get('status')=='ok','at_most_one_question':reply.get('answer','').count('?')<=1,
        'no_unchecked_primary_evidence':not meta.get('primary_evidence_unchecked')}
    for key in ['material','quantity']:
        if key in case:checks['final_'+key]=facts.get(key,{}).get('value')==case[key]
    scenarios=tools.get('assess_substrate_potential',{}).get('scenarios',[])
    if any(s.get('methane_m3') for s in scenarios):checks['computed_methane_displayed']=any(r['id'].endswith('.methane') for r in meta.get('verified_display_references',[]))
    if 'economics' in case['needs'] and tools.get('evaluate_partial_economics',{}).get('scenarios'):
        checks['available_economic_or_energy_numbers']=any('gross' in r['id'] or 'kwh' in r['id'] for r in meta.get('verified_display_references',[]))
    return checks

def evaluate(split,limit,label=''):
    data=json.loads((ROOT/'evaluations/stage9_cases.json').read_text(encoding='utf-8'));out=ROOT/'reports/stage9';out.mkdir(exist_ok=True)
    prefix=label+'_' if label else ''
    path=out/(prefix+split+'_live.json');rows=json.loads(path.read_text(encoding='utf-8')) if path.exists() else []
    fingerprint=source_hash();freeze=out/(prefix+'held_out_freeze.json')
    if split=='held_out':
        if not freeze.exists():freeze.write_text(json.dumps({'source_sha256':fingerprint,'case_sha256':hashlib.sha256((ROOT/'evaluations/stage9_cases.json').read_bytes()).hexdigest(),'policy':'No tuning using held-out outputs. Any later changed revision requires a new untouched set.'},indent=2),encoding='utf-8')
        elif json.loads(freeze.read_text())['source_sha256']!=fingerprint:raise RuntimeError('Held-out code changed; cannot continue this acceptance set')
    done={r['id'] for r in rows}
    for case in data[split][:limit]:
        if case['id'] in done:continue
        for _ in range(24):
            temperature=float(subprocess.check_output(['nvidia-smi','--query-gpu=temperature.gpu','--format=csv,noheader,nounits'],timeout=5).decode().splitlines()[0])
            if temperature<85:break
            print('THERMAL_PAUSE',temperature,flush=True);time.sleep(10)
        else:raise RuntimeError('GPU thermal budget unavailable; traces retained')
        sid=http('/api/dashboard/chat/sessions',{'mode':'offline','context':{},'conversation_version':'7'})['id'];turns=[]
        print('START',case['id'],flush=True)
        for message in case['messages']:
            started=time.monotonic();rid=uuid.uuid4().hex
            job=http(f'/api/dashboard/chat/sessions/{sid}/jobs',{'message':message,'request_id':rid})
            duplicate=http(f'/api/dashboard/chat/sessions/{sid}/jobs',{'message':message,'request_id':rid}) if case.get('duplicate') else job
            while time.monotonic()-started<240:
                job=http('/api/dashboard/jobs/'+job['id'])
                if job['terminal']:break
                time.sleep(2)
            result=http(job['result_reference']);reply=result.get('reply') or {}
            turns.append({'prompt':message,'job':job,'reply':reply,'partial_results':result['partial_results'],'seconds':time.monotonic()-started,
                          'same_duplicate_id':duplicate['id']==job['id']})
            http('/api/dashboard/jobs/'+job['id']+'/ack',{})
        checks=check(case,turns[-1]['reply'],turns[-1]['job']);checks['idempotent_delivery']=all(t['same_duplicate_id'] for t in turns)
        row={'id':case['id'],'session_id':sid,'split':split,'source_sha256':fingerprint,'checks':checks,'automated_pass':all(checks.values()),'turns':turns}
        rows.append(row);path.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
        print(case['id'],'PASS' if row['automated_pass'] else 'FAIL',[k for k,v in checks.items() if not v],flush=True)
        summary={'cases':len(rows),'automated_passes':sum(r['automated_pass'] for r in rows),'scope':'Automated contract checks, not exhaustive scientific or hallucination adjudication.',
                 'median_turn_latency_s':statistics.median(t['seconds'] for r in rows for t in r['turns']),
                 'qwen_synthesis_cases':sum(r['checks']['qwen_synthesis'] for r in rows),'terminal_timeouts':sum(t['job']['status']=='TIMED_OUT' for r in rows for t in r['turns'])}
        (out/(prefix+split+'_summary.json')).write_text(json.dumps(summary,indent=2),encoding='utf-8')
    return rows

if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');p=argparse.ArgumentParser();p.add_argument('--split',choices=['development','held_out'],default='development');p.add_argument('--limit',type=int,default=100);p.add_argument('--label',default='')
    args=p.parse_args()
    if args.label and not all(c.isalnum() or c in '_-' for c in args.label):p.error('Invalid artifact label')
    evaluate(args.split,args.limit,args.label)
