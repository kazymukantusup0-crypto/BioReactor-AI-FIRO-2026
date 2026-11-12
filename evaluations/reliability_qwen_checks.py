"""Resumable P1 reproductions through actual HTTP/runtime/Qwen, not held-out scoring."""
import argparse
import hashlib
import json
import os
import re
import subprocess
import time
import urllib.request
import uuid
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
BASE=os.getenv('BIOREACTOR_QA_URL','http://127.0.0.1:8773')
CASES=[
    ('swine',['У меня 8 кг свиного навоза, сколько биогаза?']),
    ('comparison',['Что выгоднее: 10 кг коровьего навоза или 10 кг пищевых отходов?']),
    ('temperature',['В реакторе 30 градусов. Стоит ли повышать температуру?']),
    ('mixture_water',['У меня 5 кг пищевых отходов. Сколько метана?',
        'Добавь 2 кг куриного помёта и пересчитай.',
        'Если я добавлю 10 литров воды, метана станет больше?']),
    ('money',['Сколько денег я заработаю на 5 кг пищевых отходов?']),
    ('batches',['У меня 478 литров жидкого коровьего навоза и реактор 700 литров. Лучше продать или переработать?',
        'У меня 47 литров жидкого коровьего навоза и реактор 114 литров.',
        'У меня 470 литров свежей травы и реактор 840 литров.',
        'Не 470, а 450 литров.', 'А если реактор будет 900 литров?',
        'В одной и той же партии одновременно 47 и 478 литров.']),
    ('unknown',['У меня 5 кг неизвестного органического сырья, сколько метана?']),
    ('ambiguous',['Исправь: 47 литров и 114 литров.']),
]

def http(path,payload=None):
    request=urllib.request.Request(BASE+path,data=json.dumps(payload,ensure_ascii=False).encode() if payload is not None else None,
        headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(request,timeout=20) as response:return json.load(response)

def fingerprint():
    digest=hashlib.sha256()
    for folder in ['src/agent','src/dashboard','src/advisor','src/economics']:
        for path in sorted((ROOT/folder).glob('*.py')):digest.update(path.relative_to(ROOT).as_posix().encode());digest.update(path.read_bytes())
    return digest.hexdigest()

def inspect_case(name,turns):
    checks={}
    for index,turn in enumerate(turns):
        reply=turn['result'].get('reply') or {};meta=reply.get('technical_metadata',{})
        checks[f'{index}.actual_qwen']=any(p.get('model')=='qwen3:8b' and p.get('actual_generation') for p in reply.get('provider_status',[]))
        checks[f'{index}.terminal']=turn['job']['status']=='COMPLETED'
        checks[f'{index}.one_turn_per_request']=len([t for t in turn['snapshot']['turns'] if t['request_id']==turn['job']['request_id']])==1
        checks[f'{index}.no_actuator']=reply.get('actuator_access') is False
        checks[f'{index}.one_question']=reply.get('answer','').count('?')<=1
        if reply.get('error_type')!='AmbiguousIntent':checks[f'{index}.runtime9']=reply.get('analysis_version')=='9.0'
        checks[f'{index}.required_evidence_checked']=not meta.get('primary_evidence_unchecked')
        checks[f'{index}.task_matches_scientific_state']=reply.get('memory',{}).get('task_id')==turn['scientific_state']['active_task_id']
        checks[f'{index}.version_matches_scientific_state']=reply.get('state_version')==turn['scientific_state']['state_version']
        details=meta.get('scientific_details',{})
        science=details.get('assess_substrate_potential',{})
        if 'methane_yield' in reply.get('memory',{}).get('intents',[]) and any(s.get('methane_m3') for s in science.get('scenarios',[])):
            checks[f'{index}.methane_displayed']=any(r['id'].endswith('.methane') for r in meta.get('verified_display_references',[]))
        economy=details.get('evaluate_partial_economics',{})
        if economy.get('scenarios'):
            checks[f'{index}.available_economic_or_energy_numbers']=any(r['id'].endswith('.gross') or r['id'].endswith('_kwh') for r in meta.get('verified_display_references',[]))
            if not economy.get('profit_established'):
                checks[f'{index}.unknown_costs_not_negative_profit']=not bool(re.search(r'не\s*выгодно|убыточн|unprofitable|loss.making',reply.get('answer',''),re.I))
        turn['review']={'final_author':meta.get('final_author'),'verification':meta.get('verification'),
                        'tools':[t['tool'] for t in reply.get('tools',[])],'answer':reply.get('answer')}
    replies=[t['result'].get('reply') or {} for t in turns]
    facts=[r.get('memory',{}).get('facts',{}) for r in replies]
    def fact(index,key):return facts[index].get(key,{}).get('value')
    if name=='temperature':checks['current_temperature_preserved']=fact(0,'temperature_c')==30
    if name=='batches' and len(turns)==6:
        for i,(material,quantity,capacity) in enumerate([('cattle_manure',478,700),('cattle_manure',47,114),('grass',470,840)]):
            checks[f'batch_{i}_active']=fact(i,'material')==material and fact(i,'quantity')==quantity and fact(i,'reactor_total_volume_l')==capacity
        checks['distinct_batch_tasks']=len({r['memory']['task_id'] for r in replies[:3]})==3
        checks['correction_keeps_task']=replies[2]['memory']['task_id']==replies[3]['memory']['task_id'] and fact(3,'quantity')==450
        checks['hypothetical_not_measurement']=fact(4,'reactor_total_volume_l')==840 and replies[4]['memory']['assumptions'].get('reactor_total_volume_l',{}).get('value')==900
        checks['real_conflict']=replies[5].get('error_type')=='ConflictingValuesInSameRequest' and fact(5,'quantity')==450
    if name=='mixture_water' and len(turns)==3:
        components=replies[1]['memory'].get('mixture_components',[])
        checks['mixture_inventory']={c['material']:c['quantity'] for c in components}=={'food_waste':5,'poultry_manure':2}
        def potentials(reply):return [(s['profile_ids'],s['methane_m3']) for s in reply.get('technical_metadata',{}).get('scientific_details',{}).get('assess_substrate_potential',{}).get('scenarios',[])]
        checks['water_does_not_create_methane']=bool(potentials(replies[1])) and potentials(replies[1])==potentials(replies[2])
        water_answer=replies[2].get('answer','').casefold()
        checks['water_effect_explained']=('0 кг vs' in water_answer or '0 kg vs' in water_answer) and ('не увеличивается' in water_answer or 'does not increase' in water_answer)
    if name=='unknown':checks['unknown_substrate_missing_identity_named']=bool(re.search(r'вид сырья|type of (?:feedstock|substrate)',replies[0].get('answer',''),re.I))
    if name=='comparison':checks['comparison_states_potential_not_profit']=bool(re.search(r'больший расчётный потенциал|greater methane potential',replies[0].get('answer',''),re.I)) and not bool(re.search(r'не\s*выгодно|убыточн|unprofitable|loss.making',replies[0].get('answer',''),re.I))
    if name=='ambiguous':checks['ambiguous_not_false_conflict']=replies[0].get('error_type')=='AmbiguousIntent'
    return checks

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--limit',type=int,default=len(CASES));parser.add_argument('--label',default='p1_rc2')
    parser.add_argument('--only',nargs='+',choices=[name for name,_ in CASES])
    args=parser.parse_args()
    if not args.label.replace('_','').replace('-','').isalnum():parser.error('Invalid artifact label')
    out=ROOT/'reports/reliability';out.mkdir(exist_ok=True)
    target=out/(args.label+'_real_qwen.json')
    data=json.loads(target.read_text(encoding='utf-8')) if target.exists() else {'source_sha256':fingerprint(),'cases':[],'scope':'Development reproductions, not held-out accuracy or scientific validation.'}
    if data['source_sha256']!=fingerprint():raise RuntimeError('Source changed; use a new label and preserve the first attempts')
    selected=[(name,dict(CASES)[name]) for name in args.only] if args.only else CASES
    for name,messages in selected[:args.limit]:
        row=next((r for r in data['cases'] if r['case']==name),None)
        if row and row.get('complete'):continue
        if not row:
            sid=http('/api/dashboard/chat/sessions',{'mode':'offline','context':{},'conversation_version':'7'})['id']
            row={'case':name,'session':sid,'turns':[]};data['cases'].append(row)
            target.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
        for index,message in enumerate(messages):
            if index<len(row['turns']):continue
            pending=row.get('pending');job=None
            if pending and pending.get('job_id'):
                if pending['index']!=index or pending['message']!=message:raise RuntimeError('Pending evaluation turn does not match the case')
                job=http('/api/dashboard/jobs/'+pending['job_id'])
            else:
                for _ in range(30):
                    temperature=float(subprocess.check_output(['nvidia-smi','--query-gpu=temperature.gpu','--format=csv,noheader,nounits'],timeout=5).decode().splitlines()[0])
                    if temperature<85:break
                    print('THERMAL_PAUSE',temperature,flush=True);time.sleep(2)
                else:raise RuntimeError('BLOCKED: GPU thermal budget unavailable; completed turns preserved')
                if not pending:
                    snapshot=http('/api/dashboard/chat/sessions/'+row['session'])
                    pending={'index':index,'message':message,'request_id':uuid.uuid4().hex,'expected_state_version':snapshot['state_version']}
                    row['pending']=pending
                    target.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
            if pending['index']!=index or pending['message']!=message:raise RuntimeError('Pending evaluation turn does not match the case')
            started=time.monotonic()
            if job is None:
                # Resume with the original UUID even when the prior POST reply was lost.
                job=http(f"/api/dashboard/chat/sessions/{row['session']}/jobs",{k:pending[k] for k in ['message','request_id','expected_state_version']})
                pending['job_id']=job['id'];target.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
                print('START',name,index,job['id'],flush=True)
            else:print('RESUME',name,index,job['id'],job['status'],flush=True)
            while not job['terminal'] and time.monotonic()-started<220:
                time.sleep(1);job=http('/api/dashboard/jobs/'+job['id'])
            turn={'prompt':message,'job':job,'result':http(job['result_reference']),'elapsed_s':time.monotonic()-started,
                  'snapshot':http('/api/dashboard/chat/sessions/'+row['session']),
                  'scientific_state':http('/api/dashboard/chat/sessions/'+row['session']+'/scientific-state')}
            row['turns'].append(turn);row.pop('pending',None)
            target.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
            print('SAVED',name,index,job['status'],round(turn['elapsed_s'],1),flush=True)
        row['checks']=inspect_case(name,row['turns']);row['complete']=True;row['automated_pass']=all(row['checks'].values())
        target.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
        failures=[key for key,value in row['checks'].items() if not value]
        with (ROOT/'reports/reliability_scientific_audit.md').open('a',encoding='utf-8') as report:
            report.write(f"\nP1 real Qwen `{args.label}` case `{name}`: {'PASSED automated checks' if not failures else 'FAILED automated checks '+str(failures)}; {len(row['turns'])} HTTP turns, artifact `reports/reliability/{target.name}`. Semantic human review is separate; P1 overall IN PROGRESS.\n")
        print('CASE',name,'PASS' if not failures else 'FAIL',failures,flush=True)

if __name__=='__main__':main()
