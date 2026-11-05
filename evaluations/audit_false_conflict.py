"""Audit recorded real replies; never invokes or invents a model response."""
import json
from collections import Counter
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'reports/false_conflict'
path=OUT/'live.json'
rows=json.loads(path.read_text(encoding='utf-8'))
initial=OUT/'live_before_final_audit.json'
if not initial.exists():initial.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
by_id={r['id']:r for r in rows}


def scenarios(row):
    return next((t['result'].get('scenarios',[]) for t in row['reply']['tools'] if t['tool']=='assess_substrate_potential'),[])


old_question=(by_id['A']['reply'].get('user_facing_answer') or {}).get('question')
for row in rows:
    reply=row['reply'];checks=row['checks']
    if row['id'] in {'D','E','F','H_form'}:
        q=(reply.get('user_facing_answer') or {}).get('question')
        checks['no_repeated_question_after_A']=not q or not old_question or q['id']!=old_question['id']
    if row['id']=='E':
        checks['methane_unchanged_by_vessel_only']=[s['methane_m3'] for s in scenarios(row)]==[s['methane_m3'] for s in scenarios(by_id['A'])]
    if row['id']=='H_form':
        checks.pop('scientific_computation',None)
        checks['form_and_evidence_updated']=bool(scenarios(row)) and all(c['material_state']=='bedded' for c in reply['memory']['mixture_components'])
        checks['old_liquid_profile_not_reused']=all('oliveira-rm1-2025-v1' not in s['profile_ids'] for s in scenarios(row))
        row['audit_note']='Form correction may lack measured bedded-manure density; it must check compatible evidence, not invent a numerical yield.'
    row['passed']=all(checks.values())
path.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
main=[r for r in rows if r['id'] in set('ABCDEFGH')]
summary={'main_passed':sum(r['passed'] for r in main),'main_total':len(main),
         'all_recorded_passed':sum(r['passed'] for r in rows),'all_recorded_total':len(rows),
         'python':ET.parse(OUT/'python_results.xml').getroot().find('testsuite').attrib,
         'terminations':dict(Counter(r['reply'].get('technical_metadata',{}).get('autonomous_termination') for r in rows)),
         'cases':[{'id':r['id'],'passed':r['passed'],'failed':[k for k,v in r['checks'].items() if not v],
                   'tools':[(t['tool'],t['status']) for t in r['reply']['tools']],
                   'seconds':r['reply'].get('technical_metadata',{}).get('latency_seconds'),
                   'methane_m3':[s['methane_m3'] for s in scenarios(r)]} for r in rows]}
(OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False,indent=2))
