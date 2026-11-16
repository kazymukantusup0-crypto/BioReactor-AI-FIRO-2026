"""Load the main LLM into GPU memory before the first user question.

ЗАПУСК_BioReactor.bat runs this in the background. The model is loaded with exactly the
same options as the agent uses (num_ctx, num_gpu from
data/config/llm_selection.json); otherwise Ollama would reload it on the
first real question and the jury would wait several extra seconds.
"""
import json
import sys
import urllib.request
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parents[1] / "data" / "config" / "llm_selection.json"


def main() -> int:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    payload = {
        "model": config["model"],
        "messages": [],  # empty chat = only load the model, generate nothing
        "keep_alive": config["keep_alive"],
        "options": {"num_ctx": config["num_ctx"], "num_gpu": config["num_gpu"]},
    }
    request = urllib.request.Request(
        f"{config['ollama_url']}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            response.read()
    except OSError as error:
        print(f"Warm-up failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
