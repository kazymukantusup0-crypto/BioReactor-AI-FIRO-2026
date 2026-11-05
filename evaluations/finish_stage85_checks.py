"""Finish serial live checks after a running replay; no concurrent inference."""
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if len(sys.argv) > 1:
    pid = int(sys.argv[1])
    subprocess.run(['powershell', '-NoProfile', '-Command',
                    f'Wait-Process -Id {pid} -ErrorAction SilentlyContinue'], check=False)
os.environ.update(BIOREACTOR_QA_RESUME='1', BIOREACTOR_QA_ONLY_FAULTS='42,44',
                  BIOREACTOR_QA_COOLDOWN_SECONDS='20', BIOREACTOR_LLM_GPU_LAYERS='16',
                  BIOREACTOR_LLM_CONTEXT='8192', STAGE85_LIVE_BROWSER='1')
subprocess.run([sys.executable, '-X', 'utf8', 'evaluations/validate_stage85_qwen.py'], cwd=ROOT, check=True)
subprocess.run(['node', 'tests/stage85_browser.mjs'], cwd=ROOT/'frontend', check=True)
subprocess.run([sys.executable, '-X', 'utf8', 'evaluations/summarize_stage85.py'], cwd=ROOT, check=True)
