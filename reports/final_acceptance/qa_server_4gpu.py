"""Acceptance-only wrapper: unchanged app handlers, isolated DB, local Qwen 3 8B."""
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
for folder in ('.runtime-deps', '.deps'):
    if (ROOT / folder).exists():
        sys.path.append(str(ROOT / folder))

# Only offload differs from the prior 16-layer browser run, to keep the GPU
# below the thermal ceiling. The model/provider and production handlers remain.
for key, value in {
    'OLLAMA_MODEL': 'qwen3:8b',
    'BIOREACTOR_LLM_CONTEXT': '8192',
    'BIOREACTOR_LLM_GPU_LAYERS': '4',
    'BIOREACTOR_LLM_REQUEST_TIMEOUT': '150',
    'BIOREACTOR_AGENT_TIMEOUT': '150',
    'BIOREACTOR_JOB_TIMEOUT': '180',
    'BIOREACTOR_RESEARCH_ONLINE': '0',
}.items():
    os.environ[key] = value

target = Path(os.environ['BIOREACTOR_QA_DB']).resolve()
target.parent.mkdir(parents=True, exist_ok=True)
if not target.exists():
    with sqlite3.connect(ROOT / 'data/market/market.sqlite3') as source, sqlite3.connect(target) as dest:
        source.backup(dest)

from src.market.api import create_app
from src.market.store import Store

app = create_app(Store(target), scheduler_enabled=False)

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=int(os.getenv('BIOREACTOR_QA_PORT', '8781')), log_level='warning')
