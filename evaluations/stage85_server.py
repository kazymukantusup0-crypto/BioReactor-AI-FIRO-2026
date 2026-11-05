"""Isolated live-Qwen server. Existing scientific models and production history stay intact."""
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
os.environ.setdefault('OLLAMA_MODEL','qwen3:8b')
os.environ.setdefault('BIOREACTOR_LLM_CONTEXT','8192')
os.environ.setdefault('BIOREACTOR_RESEARCH_ONLINE','0')
target=ROOT/'evaluations/stage85_live.sqlite3'
if not target.exists():
    with sqlite3.connect(ROOT/'data/market/market.sqlite3') as original, sqlite3.connect(target) as copy:
        original.backup(copy)
os.environ['BIOREACTOR_MARKET_DB']=str(target)
sys.argv=['main.py','dashboard','--port','8769','--no-browser','--no-scheduler']
from main import main
main()
