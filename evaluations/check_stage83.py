"""Check computations and state in real Qwen responses, then compare real HTTP API."""
import json,urllib.request,math
from pathlib import Path
FOLDER=Path('reports/stage8_3')
source=json.loads((FOLDER/'qwen_http.json').read_text(encoding='utf-8'))
checks=[]
def stable(v):
    if isinstance(v,dict):return {k:stable(x) for k,x in v.items() if k not in {'receipt_age_seconds','calculated_at','recorded_at'}}
    if isinstance(v,list):return [stable(x) for x in v]
    return v
positive={'cattle48','grass58','poultry50','food5','mixture','overfill','water','compare','costs','pig8','horse','goat','straw','poultry_litres','food_grams','pig_tonnes','addition','correction','temperature_context'}
negative={'silage','vegetables','fruit','whey','plant','unknown','grass_litres','dry_grass','compost','mixture_unknown'}
for case in source['cases']:
    row={'id':case['id'],'turns':[],'passed':True}
    for turn in case['turns']:
        response=turn['response'];meta=response.get('technical_metadata',{})
        tools={t['tool']:t['result'] for t in meta.get('tool_calls',[])}
        science=tools.get('assess_substrate_potential',{})
        scenarios=science.get('scenarios',[])
        issues=[];api_comparisons=[]
        if response.get('mode')!='qwen_autonomous_tools' or not meta.get('autonomous_action_steps'):issues.append('No real autonomous Qwen tool loop')
        if meta.get('analytical_unchecked_tools'):issues.append('Required tool was skipped')
        if case['id']!='temperature' and not science.get('catalog_checked'):issues.append('Scientific evidence was not checked')
        if case['id'] in positive and not any(s.get('methane_m3') is not None for s in scenarios):issues.append('Expected available methane was not calculated')
        if case['id'] in negative and any(s.get('methane_m3') is not None for s in scenarios):issues.append('Unexpected complete methane without applicable inputs')
        for s in scenarios:
            req=urllib.request.Request(source['http']+'/api/advisor/analyze',json.dumps(s['request']).encode(),{'Content-Type':'application/json'})
            with urllib.request.urlopen(req,timeout=60) as r:api=json.load(r)
            same=api['mixture']==s['mixture'] and api['engineering']==s['engineering']
            api_comparisons.append({'scenario':s['id'],'mixture_and_geometry_equal':same})
            if not same:issues.append('API/chat mismatch: '+s['id'])
            economic=next((x for x in tools.get('evaluate_partial_economics',{}).get('scenarios',[]) if x['id']==s['id']),None)
            if economic:
                for key in ['energy','reactor_balance','scenarios','operating_costs','prices']:
                    if stable(economic['analysis'][key])!=stable(api['decision_analysis'][key]):issues.append('Economics API/chat mismatch '+s['id']+': '+key)
        if case['id']=='overfill' and not any(s['engineering']['status']=='PHYSICALLY_INFEASIBLE' for s in scenarios):issues.append('Overfill not detected')
        if case['id']=='food_grams' and not all(s['wet_mass_kg']['low']==.5 for s in scenarios):issues.append('500g conversion failed')
        if case['id']=='pig_tonnes' and not all(s['wet_mass_kg']['low']==100 for s in scenarios):issues.append('0.1t conversion failed')
        if case['id']=='water' and 'dilution_water_l' in response.get('memory',{}).get('facts',{}):
            if not all(s['engineering']['feed_plus_water_mass_kg']['low']==15 for s in scenarios):issues.append('Water/context mass failed')
        if case['id']=='addition' and len(case['turns'])>1 and turn is case['turns'][-1]:
            if not all(s['wet_mass_kg']['low']==7 and len(s['components'])==2 for s in scenarios):issues.append('Addition lost inventory')
        if case['id']=='correction' and turn is case['turns'][-1]:
            if not all(s['wet_mass_kg']['low']==3 for s in scenarios):issues.append('Correction did not replace previous mass')
        if case['id']=='costs' and turn is case['turns'][-1]:
            econ=tools.get('evaluate_partial_economics',{}).get('scenarios',[])
            if not econ or not all(e['analysis']['operating_costs']['known_subtotal']['low']==170 for e in econ):issues.append('Explicit costs were not retained')
            if any(e['analysis']['operating_costs']['complete_total'] is not None for e in econ):issues.append('Unknown costs were zero-filled')
        if case['id']=='mixture' and not all(len(s['components'])==3 and s['wet_mass_kg']['low']==7 for s in scenarios):issues.append('Mixture quantities incorrect')
        if case['id']=='compare' and (science.get('comparison_mode')!='alternatives' or not all(len(s['components'])==1 for s in scenarios)):issues.append('Alternatives added together')
        if case['id']=='temperature' and 'assess_process_evidence' not in tools:issues.append('Temperature evidence not checked')
        if response.get('answer','').count('?')>1:issues.append('More than one clarification question')
        row['turns'].append({'tools':list(tools),'issues':issues,'api_comparisons':api_comparisons,
            'methane_m3':[s['methane_m3'] for s in scenarios],'profiles':[s['profile_ids'] for s in scenarios],
            'missing':[s['missing'] for s in scenarios],'latency_seconds':turn['latency_seconds']})
        if issues:row['passed']=False
    checks.append(row)
result={'source_status':source['status'],'cases':checks,'passed':sum(c['passed'] for c in checks),'total':len(checks)}
(FOLDER/'qwen_checks.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'passed':result['passed'],'total':result['total'],'failures':[{c['id']:[t['issues'] for t in c['turns']]} for c in checks if not c['passed']]},ensure_ascii=False))
raise SystemExit(0 if result['passed']==result['total']==30 and source['status']=='complete' else 1)
