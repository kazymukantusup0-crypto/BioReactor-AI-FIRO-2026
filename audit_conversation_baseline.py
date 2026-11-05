"""Measure the unchanged v4 agent on prescribed dialogues before implementation."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
from unittest.mock import patch
import main
from src.agent.orchestrator import Agent
from src.agent.providers import HybridLLM
from src.agent.tools import ToolRegistry
from src.market.store import Store
import src.agent.providers as providers

ROOT=Path(__file__).resolve().parent;OUT=ROOT/'reports/stage5_6'


def run():
    if (OUT/'baseline_dialogues.json').exists():raise ValueError('Baseline already captured; preserve it unchanged')
    cases=json.loads((ROOT/'evaluations/conversation_v5_6.json').read_text(encoding='utf-8'))['cases']
    rows=[];calls=[];original=providers.request_json
    def measured(url,payload,timeout,key=None):
        start=time.perf_counter();record={'input_characters':sum(len(m['content']) for m in payload['messages']),
            'request_bytes':len(json.dumps(payload,ensure_ascii=False).encode()),'phase':'plan' if 'планировщик' in payload['messages'][0]['content'] else 'order'}
        try:
            response=original(url,payload,timeout,key)
            record.update(status='ok',prompt_tokens=response.get('prompt_eval_count'),output_tokens=response.get('eval_count'),
                load_seconds=response.get('load_duration',0)/1e9,done_reason=response.get('done_reason'))
            return response
        except Exception as exc:record.update(status='error',error=str(exc));raise
        finally:record['latency_seconds']=time.perf_counter()-start;calls.append(record)
    with tempfile.TemporaryDirectory() as temp:
        database=Path(temp)/'real_prices_copy.sqlite3'
        with closing(sqlite3.connect(ROOT/'data/market/market.sqlite3')) as source,closing(sqlite3.connect(database)) as dest:source.backup(dest)
        store=Store(database);agents={}
        with patch('src.agent.providers.request_json',side_effect=measured):
            for case in cases:
                agent=agents.setdefault(case['conversation'],Agent(llm=HybridLLM('offline'),context={'market_region':'KZ-Karaganda'},registry=ToolRegistry(store)))
                first=len(calls);start=time.perf_counter();reply=agent.ask(case['message'])
                rows.append({'id':case['id'],'message':case['message'],'reply':reply,'latency_seconds':time.perf_counter()-start,'requests':calls[first:]})
                print(case['id'],reply['mode'],len(reply['tools']),round(rows[-1]['latency_seconds'],3),flush=True)
    (OUT/'baseline_dialogues.json').write_text(json.dumps({'engine':'legacy_v4 before v5.6 changes','cases':rows,'requests':calls},ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':run()
