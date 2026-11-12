"""Current unmodified production handlers on isolated QA DB; real Qwen only."""
import os
import sqlite3
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
for folder in ['.runtime-deps','.deps']:
    if (ROOT/folder).exists():sys.path.append(str(ROOT/folder))
for key,value in {'OLLAMA_MODEL':'qwen3:8b','BIOREACTOR_LLM_CONTEXT':'8192',
    'BIOREACTOR_LLM_GPU_LAYERS':'16','BIOREACTOR_LLM_REQUEST_TIMEOUT':'150','BIOREACTOR_AGENT_TIMEOUT':'150',
    'BIOREACTOR_JOB_TIMEOUT':'180','BIOREACTOR_RESEARCH_ONLINE':'0'}.items():os.environ[key]=value
target=Path(os.getenv('BIOREACTOR_QA_DB',str(ROOT/'evaluations/reliability_qwen.sqlite3'))).resolve()
target.parent.mkdir(parents=True,exist_ok=True)
if not target.exists():
    with sqlite3.connect(ROOT/'data/market/market.sqlite3') as original,sqlite3.connect(target) as copy:original.backup(copy)
from src.market.api import create_app
from src.market.store import Store
app=create_app(Store(target),scheduler_enabled=False)
if __name__=='__main__':
    import uvicorn
    uvicorn.run(app,host='127.0.0.1',port=int(os.getenv('BIOREACTOR_QA_PORT','8773')),log_level='info')
