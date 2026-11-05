"""Controlled adapter failure over real HTTP/Qwen; never use on production DB."""
import os
import sqlite3
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
for folder in ['.runtime-deps','.deps']:
    if (ROOT/folder).exists():sys.path.append(str(ROOT/folder))
os.environ.setdefault('OLLAMA_MODEL','qwen3:8b')
os.environ.setdefault('BIOREACTOR_LLM_CONTEXT','8192')
os.environ.setdefault('BIOREACTOR_LLM_GPU_LAYERS','16')
os.environ.setdefault('BIOREACTOR_AGENT_TIMEOUT','150')
os.environ.setdefault('BIOREACTOR_RESEARCH_ONLINE','0')
target=ROOT/'evaluations/stage9_fault.sqlite3'
if not target.exists():
    with sqlite3.connect(ROOT/'data/market/market.sqlite3') as original,sqlite3.connect(target) as copy:original.backup(copy)
os.environ['BIOREACTOR_MARKET_DB']=str(target)
from src.agent.tools import ToolRegistry
class ControlledFault(ToolRegistry):
    def _execute(self,name,*args):
        if name=='assess_substrate_potential':
            return {'status':'error','error_code':'TEST_CONTROLLED_ADAPTER_FAILURE','message':'TEST controlled scientific adapter failure. No observations were invented. An alternative local path may be available.'}
        return super()._execute(name,*args)
import src.dashboard.api as dashboard_api
dashboard_api.ToolRegistry=ControlledFault
from src.market.store import Store
from src.market.api import create_app
import uvicorn
uvicorn.run(create_app(Store(target),scheduler_enabled=False),host='127.0.0.1',port=8771,log_level='warning')
