"""Prescribed regression dialogues: deterministic pipeline and real Ollama separately.

Not an independent language benchmark. No generated training data or market prices.
"""
import argparse
from contextlib import closing
from datetime import datetime,timezone
import json
import math
from pathlib import Path
import re
import sqlite3
import statistics
import tempfile
import time
import main
from src.agent.conversation import ConversationAgent
from src.agent.providers import HybridLLM
from src.agent.tools import ToolRegistry
from src.market.store import Store

ROOT=Path(__file__).resolve().parent;OUT=ROOT/'reports/stage5_6'


def numeric_claims(reply):
    facing=reply.get('user_facing_answer',{})
    text=' '.join(facing.get('paragraphs',[]))
    values=[90.0] # Explicit unavailable 90% interval, not a coverage assertion.
    memory=reply.get('memory',{})
    for section in ['facts','derived','estimates']:
        for entry in memory.get(section,{}).values():
            if isinstance(entry['value'],(int,float)) and not isinstance(entry['value'],bool):values.append(float(entry['value']))
    for call in reply['tools']:
        result=call['result']
        for claim in result.get('claims',[]):values+=claim['values']
        for key in ['bmp','potential_methane_m3','sale_revenue','processing_net_profit']:
            if isinstance(result.get(key),(int,float)):values.append(result[key])
        for entry in result.get('accuracy',{}).values():
            if isinstance(entry,(int,float)):values.append(entry)
        for price in result.get('prices',[]):
            values.append(float(price['normalized_value']));values += [float(x) for x in price['effective_from'].split('-')]
    # Unicode superscript in m³/CH₄ is not an arithmetic claim.
    found=[float(v.replace(' ','').replace(',','.')) for v in re.findall(r'(?<![\w])\d+(?: \d{3})*(?:[.,]\d+)?',text)]
    unsupported=[v for v in found if not any(math.isclose(v,allowed,rel_tol=.00011,abs_tol=.0051) for allowed in values)]
    return {'numbers_in_answer':found,'unsupported':unsupported,'method':'Consistency against confirmed inputs, unit arithmetic, cited claim values and returned tool values; not independent scientific validation'}


def run():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--llm',action='store_true');args=parser.parse_args()
    cases=json.loads((ROOT/'evaluations/conversation_v5_6.json').read_text(encoding='utf-8'))['cases']
    rows=[];agents={};entity_correct=entity_total=intent_correct=intent_total=clarification_correct=clarification_total=0
    retained_correct=retained_total=0
    raw_intent_correct=raw_intent_total=0
    with tempfile.TemporaryDirectory() as temp:
        database=Path(temp)/'real_prices_copy.sqlite3'
        with closing(sqlite3.connect(ROOT/'data/market/market.sqlite3')) as source,closing(sqlite3.connect(database)) as dest:source.backup(dest)
        store=Store(database)
        for case in cases:
            if case['conversation'] not in agents:
                agents[case['conversation']]=ConversationAgent(llm=HybridLLM('offline',providers=None if args.llm else []),registry=ToolRegistry(store))
            agent=agents[case['conversation']];started=time.perf_counter();reply=agent.ask(case['message']);elapsed=time.perf_counter()-started
            expected=case['expected'];observed={};checks={};memory=agent.state
            for key in ['material','quantity','unit','sale_offer_amount','sale_offer_scope','reactor_total_volume_l','temperature_c','ts_percent','vs_percent','vs_basis','language']:
                if key not in expected:continue
                actual=memory.language if key=='language' else memory.value(key)
                observed[key]=actual;checks[key]=actual==expected[key];entity_total+=1;entity_correct+=checks[key]
                extracted={e['name'] for e in reply.get('technical_metadata',{}).get('extracted_entities',{}).get('entities',[])}
                if key!='language' and key not in extracted and len(agent.history)>1:
                    retained_total+=1;retained_correct+=checks[key]
            if 'intents' in expected:
                checks['intents']=set(memory.intents)==set(expected['intents']);intent_total+=1;intent_correct+=checks['intents']
                proposal=reply.get('technical_metadata',{}).get('llm_proposal')
                if proposal:
                    raw_intent_total+=1;raw_intent_correct+=set(proposal['intents'])==set(expected['intents'])
            if 'pending' in expected:
                actual=reply.get('pending_question');checks['clarification']=actual is not None and actual['id']==expected['pending'];clarification_total+=1;clarification_correct+=checks['clarification']
            if expected.get('no_fake_bmp'):checks['no_fake_bmp']=not any(c['result'].get('bmp') is not None for c in reply['tools'])
            if expected.get('no_fake_profit'):checks['no_fake_profit']=not any(c['result'].get('final_recommendation') for c in reply['tools'])
            if expected.get('invalidates_material_results'):checks['invalidated']=bool(memory.invalidated)
            if expected.get('source_required'):checks['source_attribution']=bool(reply.get('user_facing_answer',{}).get('sources'))
            claim_audit=numeric_claims(reply);checks['no_unsupported_numeric_claims']=not claim_audit['unsupported']
            checks['no_internal_fields_in_answer']=not re.search(r'bmp_ml_ch4_g_vs|vs_mass_kg|gas_volume_basis|c_vs_sub_m',reply['answer'])
            checks['no_premature_economic_calculation']=not any(c['tool']=='compare_market_scenarios' for c in reply['tools'])
            if expected.get('intents')==['temperature_recommendation']:checks['temperature_tools']= [c['tool'] for c in reply['tools']]==['analyze_substrate','search_scientific_sources','recommend_conditions']
            body=' '.join(reply.get('user_facing_answer',{}).get('paragraphs',[]));words=len(body.split())
            rows.append({'id':case['id'],'conversation':case['conversation'],'message':case['message'],'expected':expected,'observed':observed,
                'checks':checks,'passed':all(checks.values()),'reply':reply,'latency_seconds':elapsed,'answer_words_excluding_sources_and_question':words,'numeric_claim_audit':claim_audit})
            print(case['id'],reply['mode'],len(reply['tools']),round(elapsed,3),'PASS' if all(checks.values()) else 'FAIL',flush=True)
    times=[r['latency_seconds'] for r in rows];llm_calls=[q for row in rows for provider in row['reply']['provider_status'] for q in provider.get('requests',[])]
    result={'evaluation_kind':'prescribed regression cases, not independent real-world accuracy','llm_enabled':args.llm,'model':'qwen2.5:1.5b' if args.llm else None,
        'cases':rows,'summary':{'cases':len(rows),'cases_passed':sum(r['passed'] for r in rows),
            'entity_fields_correct':entity_correct,'entity_fields_total':entity_total,'entity_extraction_accuracy':entity_correct/entity_total if entity_total else None,
            'intent_correct':intent_correct,'intent_total':intent_total,'intent_accuracy':intent_correct/intent_total if intent_total else None,
            'raw_llm_intent_correct':raw_intent_correct,'raw_llm_intent_total':raw_intent_total,
            'clarifications_correct':clarification_correct,'clarifications_total':clarification_total,
            'context_fields_retained_correct':retained_correct,'context_fields_retained_total':retained_total,
            'tool_policy_cases_passed':sum(all(ok for name,ok in r['checks'].items() if name in {'no_premature_economic_calculation','temperature_tools'}) for r in rows),
            'fallback_cases':sum(r['reply']['mode']!='llm_tools' for r in rows) if args.llm else None,
            'llm_requests':len(llm_calls),'llm_request_failures':sum(c['status']!='ok' for c in llm_calls),
            'max_prompt_tokens':max((r.get('prompt_tokens') or 0 for r in llm_calls),default=None),
            'latency_median_seconds':statistics.median(times),'latency_mean_seconds':statistics.mean(times),'latency_max_seconds':max(times),
            'mean_tools_per_case':statistics.mean(len(r['reply']['tools']) for r in rows),
            'unsupported_numeric_claims':sum(len(r['numeric_claim_audit']['unsupported']) for r in rows),
            'max_answer_words':max(r['answer_words_excluding_sources_and_question'] for r in rows)}}
    name='ollama_eval' if args.llm else 'deterministic_eval';dest=OUT/(name+'.json')
    if dest.exists():
        archived=OUT/'runs';archived.mkdir(exist_ok=True)
        (archived/(name+'_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')+'.json')).write_bytes(dest.read_bytes())
    dest.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result['summary'],indent=2))
    return 0 if all(r['passed'] for r in rows) else 1


if __name__=='__main__':raise SystemExit(run())
