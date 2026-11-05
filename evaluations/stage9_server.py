"""Isolated v9 HTTP validation; backup real prices without modifying production."""
import os
import sqlite3
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
for folder in ['.runtime-deps','.deps']:
    if (ROOT/folder).exists():sys.path.append(str(ROOT/folder))
os.environ.setdefault('OLLAMA_MODEL','qwen3:8b')
os.environ.setdefault('BIOREACTOR_LLM_CONTEXT','8192')
os.environ.setdefault('BIOREACTOR_LLM_GPU_LAYERS','24')
os.environ.setdefault('BIOREACTOR_AGENT_TIMEOUT','150')
os.environ.setdefault('BIOREACTOR_JOB_TIMEOUT','180')
os.environ.setdefault('BIOREACTOR_RESEARCH_ONLINE','0')
target=ROOT/'evaluations/stage9_live.sqlite3'
if not target.exists():
    with sqlite3.connect(ROOT/'data/market/market.sqlite3') as original,sqlite3.connect(target) as copy:original.backup(copy)
os.environ['BIOREACTOR_MARKET_DB']=str(target)
sys.argv=['main.py','dashboard','--port','8770','--no-browser','--no-scheduler']
from main import main
main()
