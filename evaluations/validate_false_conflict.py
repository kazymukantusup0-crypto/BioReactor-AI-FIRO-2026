"""Real HTTP/Qwen regressions A-H; branch only actual saved A conversation state."""
import json
from pathlib import Path
import sqlite3
import time
import uuid
import urllib.request
import subprocess

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'reports/false_conflict/live.json'
BASE='http://127.0.0.1:8769'
A='Привет, у меня есть 478 литров жидкого коровьего навоза и реактор вместимостью 700 литров. Мне лучше продать навоз или переработать и какую температуру ставить?'
B=A.replace('478','47').replace('700','114')
rows=json.loads(OUT.read_text(encoding='utf-8')) if OUT.exists() else []
by_id={r['id']:r for r in rows}


def http(path,payload=None):
    req=urllib.request.Request(BASE+path,None if payload is None else json.dumps(payload,ensure_ascii=False).encode(),{'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=280) as r:return json.load(r)


def session():
    return http('/api/dashboard/chat/sessions',{'mode':'offline','context':{},'conversation_version':'7'})['id']


def branch():
    original=by_id['A']['reply']
    sid=session();state=dict(original['memory']);state['conversation_id']=sid
    with sqlite3.connect(ROOT/'evaluations/stage85_live.sqlite3') as con:
        con.execute('UPDATE dashboard_sessions SET conversation_state_json=?,context_json=?,history_json=? WHERE id=?',
                    (json.dumps(state,ensure_ascii=False),json.dumps(original['context'],ensure_ascii=False),json.dumps([A],ensure_ascii=False),sid))
    return sid


def pause():
    for _ in range(18):
        temperature=float(subprocess.check_output(['nvidia-smi','--query-gpu=temperature.gpu','--format=csv,noheader,nounits'],timeout=5).decode().splitlines()[0])
        if temperature<84:return
        print('THERMAL_PAUSE',temperature,flush=True);time.sleep(10)
    raise RuntimeError('Thermal budget unavailable; no additional generation started')


def tool(reply,name):
    return next((t['result'] for t in reply.get('tools',[]) if t['tool']==name),{})


def run(identifier,sid,prompt,quantity=None,capacity=None,conflict=False,scenario=False):
    if identifier in by_id:return by_id[identifier]['reply']
    pause();print('START',identifier,flush=True)
    reply=http(f'/api/dashboard/chat/sessions/{sid}/messages',{'message':prompt,'request_id':uuid.uuid4().hex})
    facts=reply.get('memory',{}).get('facts',{});sc=tool(reply,'assess_substrate_potential');ss=sc.get('scenarios',[])
    checks={'actual_qwen3_8b':any(p.get('model')=='qwen3:8b' and p.get('actual_generation') for p in reply.get('provider_status',[])),
            'no_actuation':reply.get('actuator_access') is False,'diagnostic_events':bool(reply.get('technical_metadata',{}).get('diagnostic_events')),
            'one_question':reply.get('answer','').count('?')<=1}
    if conflict:
        checks.update(real_conflict=reply.get('error_type')=='ConflictingValuesInSameRequest',no_ambiguous_yield=not ss,
                      profile_lookup=bool(tool(reply,'search_substrate_profiles').get('dossiers')))
    else:
        checks.update(no_false_conflict=reply.get('mode')=='qwen_autonomous_tools',scientific_computation=bool(ss and any(s['methane_m3'] for s in ss)),
                      unit_litres=facts.get('unit',{}).get('value')=='L',material=facts.get('material',{}).get('value')=='cattle_manure',
                      geometry_not_safety=all(s['engineering']['operation_authorized'] is False for s in ss))
        if identifier=='H_form':
            # This turn changes form, not the measured density of the bedded
            # manure. Evidence may correctly be incomplete for litres.
            checks.pop('scientific_computation')
            checks['form_and_evidence_updated']=bool(ss) and all(c['material_state']=='bedded' for c in reply['memory']['mixture_components'])
            checks['old_liquid_profile_not_reused']=all('oliveira-rm1-2025-v1' not in s['profile_ids'] for s in ss)
        if quantity is not None:checks['quantity']=facts.get('quantity',{}).get('value')==quantity
        if capacity is not None:
            actual=(reply['memory'].get('assumptions',{}) if scenario else facts).get('reactor_total_volume_l',{}).get('value')
            checks['reactor_capacity']=actual==capacity
        if scenario:checks['original_capacity_retained']=facts.get('reactor_total_volume_l',{}).get('value')==700
        matches=[]
        for s in ss:
            api=http('/api/advisor/analyze',s['request'])
            mix=api.get('mixture') or api['scenario_results'][0]['mixture']
            matches.append(mix['additive_methane_reference_m3']==s['methane_m3'])
        checks['shared_api_exact_methane']=bool(matches) and all(matches)
        if identifier in {'A','B','C','G','H'}:
            checks['partial_economy']=bool(tool(reply,'evaluate_partial_economics').get('scenarios'))
            checks['temperature_evidence']=bool(tool(reply,'assess_process_evidence').get('matched_temperature_experiments'))
            checks['substantive_answer']=bool(__import__('re').search(r'м³|м3',reply.get('answer','')))
        if identifier=='C':checks['new_task_id']=reply['memory']['task_id']!=by_id['A']['reply']['memory']['task_id']
        if identifier in {'G','H'}:
            checks['old_inventory_removed']=len(reply['memory']['mixture_components'])==1 and reply['memory']['mixture_components'][0]['material']=='cattle_manure'
    row={'id':identifier,'session_id':sid,'prompt':prompt,'checks':checks,'passed':all(checks.values()),'reply':reply,
         'memory_branch':'Exact saved actual A reply' if identifier in {'C','D','E','F','H_form'} else None}
    rows.append(row);by_id[identifier]=row
    OUT.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
    print(identifier,'PASS' if row['passed'] else 'FAIL',[k for k,v in checks.items() if not v],flush=True)
    return reply


for _ in range(30):
    try:http('/health');break
    except OSError:time.sleep(1)
run('A',session(),A,478,700)
run('B',session(),B,47,114)
run('C',branch(),B,47,114)
run('D',branch(),'исправь: 47 литров и 114 литров',47,114)
run('E',branch(),'а если реактор 900 литров?',478,900,scenario=True)
run('F',branch(),'У меня одновременно 47 и 478 литров одной и той же партии',conflict=True)
if 'G' not in by_id:
    saved=http('/api/advisor/handoff',{'mode':'offline','request':{'components':[
        {'id':'c1','material':'food_waste','quantity':5,'unit':'kg','material_state':'prepared_pulp'},
        {'id':'c2','material':'poultry_manure','quantity':2,'unit':'kg'}], 'reactor_total_volume_l':90}})
    run('G',saved['session_id'],B,47,114)
if 'H' not in by_id:
    sid=by_id.get('H_form',{}).get('session_id') or branch()
    run('H_form',sid,'исправь: теперь навоз с подстилкой',478,700)
    run('H',sid,B,47,114)
print('TOTAL',sum(r['passed'] for r in rows),'/',len(rows),flush=True)
