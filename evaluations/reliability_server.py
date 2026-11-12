"""Isolated P0 browser QA: real HTTP/SQLite/tools, explicitly labelled fault gates.

No production DB writes, no model training or fabricated scientific responses.
Run: python evaluations/reliability_server.py
"""
import os
import sqlite3
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
for folder in ['.runtime-deps','.deps']:
    if (ROOT/folder).exists():sys.path.append(str(ROOT/folder))
os.environ.setdefault('BIOREACTOR_RESEARCH_ONLINE','0')
os.environ.setdefault('BIOREACTOR_JOB_TIMEOUT','30')
target=ROOT/'evaluations/reliability_live.sqlite3'
if not target.exists():
    with sqlite3.connect(ROOT/'data/market/market.sqlite3') as original,sqlite3.connect(target) as copy:original.backup(copy)

from src.agent.conversation import ConversationAgent
from src.market.api import create_app
from src.market.store import Store

app=create_app(Store(target),scheduler_enabled=False)
original=ConversationAgent.ask

def gated(self,text):
    # Only labelled execution fixtures use a gate; ordinary questions run unchanged.
    if text.startswith('TEST_P0_CRASH '):
        control=getattr(self,'progress',None).__self__
        if control.runtime.get(control.job['id'])['attempt_count']==1:
            self.emit_progress('understanding')
            for _ in range(600):time.sleep(.05);control.check()
        return original(self,text.removeprefix('TEST_P0_CRASH '))
    if text.startswith('TEST_P0_CANCEL') or text.startswith('TEST_P0_TIMEOUT'):
        self.emit_progress('understanding')
        control=getattr(self,'progress',None).__self__
        if text.startswith('TEST_P0_TIMEOUT'):control.timeout=0.2
        for _ in range(200):
            time.sleep(.05);control.check()
        raise RuntimeError('P0 test gate unexpectedly elapsed')
    return original(self,text)

ConversationAgent.ask=gated

if __name__=='__main__':
    import uvicorn
    uvicorn.run(app,host='127.0.0.1',port=8772,log_level='info')
