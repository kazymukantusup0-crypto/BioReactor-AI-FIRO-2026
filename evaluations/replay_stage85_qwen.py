"""Repeat selected failed cases against fixed code using real saved memory.

Only the isolated evaluation DB is written. The prior trace is archived; a new
session receives the actual previous conversation snapshot, not invented facts.
Run after the main suite has stopped, e.g. python evaluations/replay_stage85_qwen.py 5 6 7 8 9 10.
"""
import json
import sqlite3
import sys
import time
from pathlib import Path
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parent))
import validate_stage85_qwen as suite

selected={int(x) for x in sys.argv[1:]}
for attempt in range(30):
    try:suite.http('/health');break
    except OSError:
        if attempt==29:raise
        time.sleep(1)
rows=json.loads(suite.OUT.read_text(encoding='utf-8'))
archive=suite.OUT.with_name('live_qwen_before_replay_'+str(int(time.time()))+'.json')
archive.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
sessions={};by_id={r['id']:r for r in rows}
for index,(group,prompt,expect) in enumerate(suite.CASES,1):
    if index not in selected:continue
    if group not in sessions:
        sid=suite.http('/api/dashboard/chat/sessions',{'mode':'offline','context':{},'conversation_version':'7'})['id']
        prior=[]
        for j,(g,_,_) in enumerate(suite.CASES[:index-1],1):
            if g==group:
                r=by_id.get(f'{j:02}_{g}',{}).get('reply',{})
                if r.get('memory'):prior.append(r)
        if prior:
            snapshot=prior[-1]['memory'];snapshot['conversation_id']=sid
            context=prior[-1].get('context',{})
            history=[p for g,p,_ in suite.CASES[:index-1] if g==group][-8:]
            with sqlite3.connect(suite.ROOT/'evaluations/stage85_live.sqlite3') as con:
                con.execute('UPDATE dashboard_sessions SET conversation_state_json=?,context_json=?,history_json=? WHERE id=?',
                    (json.dumps(snapshot,ensure_ascii=False),json.dumps(context,ensure_ascii=False),json.dumps(history,ensure_ascii=False),sid))
        sessions[group]=sid
    print('REPLAY START',index,group,flush=True)
    suite.thermal_pause()
    reply=suite.http(f'/api/dashboard/chat/sessions/{sessions[group]}/messages',{'message':prompt,'request_id':str(uuid.uuid4())})
    checks=suite.evaluate(reply,expect,group)
    key=f'{index:02}_{group}'
    replacement={'id':key,'prompt':prompt,'passed':all(checks.values()),'checks':checks,'reply':reply,
                 'replay':{'archived_attempts':archive.name,'memory_seed':'Actual saved previous conversation snapshot'}}
    by_id[key]=replacement
    rows=[by_id[r['id']] for r in rows]
    suite.OUT.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
    print(key,'PASS' if all(checks.values()) else 'FAIL',[k for k,v in checks.items() if not v],flush=True)
print('LATEST TOTAL',sum(r['passed'] for r in rows),'/',len(rows),flush=True)
