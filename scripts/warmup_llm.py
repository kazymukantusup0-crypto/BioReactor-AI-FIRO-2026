"""Warm up the local LLM before the first user question.

ЗАПУСК_BioReactor.bat runs this in the background.
  1. Load the model into GPU memory with exactly the options of the agent
     (num_ctx, num_gpu from data/config/llm_selection.json); otherwise Ollama
     would reload it on the first real question.
  2. Ask the real agent one demo question (temporary database, nothing is saved).
     Ollama then keeps the agent's system prompt and tool descriptions in its
     prompt cache, so the first question of the jury does not pay for them.

Usage:  .venv\\Scripts\\python scripts\\warmup_llm.py [--load-only]
"""
import json
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "data" / "config" / "llm_selection.json"
WARMUP_QUESTION = "У меня 150 литров навоза КРС, сколько будет газа?"


def load_model(config: dict) -> None:
    payload = {
        "model": config["model"],
        "messages": [],  # empty chat = only load the model, generate nothing
        "keep_alive": config["keep_alive"],
        "options": {"num_ctx": config["num_ctx"], "num_gpu": config["num_gpu"]},
    }
    request = urllib.request.Request(f"{config['ollama_url']}/api/chat", data=json.dumps(payload).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=180) as response:
        response.read()


def prime_agent() -> float:
    """One full agent turn; returns seconds."""
    sys.path.insert(0, str(ROOT))
    from src.agent_v10.agent import Agent
    from src.agent_v10.memory import Memory

    started = time.perf_counter()
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
        agent = Agent(memory=Memory(Path(folder) / "warmup.sqlite3"))
        for _ in agent.run("warmup", WARMUP_QUESTION):
            pass
    return time.perf_counter() - started


def main() -> int:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    try:
        started = time.perf_counter()
        load_model(config)
        print(f"Model {config['model']} loaded in {time.perf_counter() - started:.1f} s")
        if "--load-only" not in sys.argv:
            print(f"Agent primed in {prime_agent():.1f} s (system prompt and tools are in the Ollama cache)")
    except Exception as error:  # warm-up must never break the start
        print(f"Warm-up failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
