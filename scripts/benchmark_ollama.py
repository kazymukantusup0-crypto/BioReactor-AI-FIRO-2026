"""Measure local Ollama speed for the agent models and write docs/benchmark.md.

What is measured for every model (same settings as the agent uses,
from data/config/llm_selection.json):
  * load time      - how long Ollama needs to put the model into VRAM;
  * first token    - time from sending a question to the first answer token;
  * tokens/second  - generation speed reported by Ollama (eval_count / eval_duration);
  * GPU share      - from /api/ps: size_vram / size (100% = whole model on GPU).

Usage:
    .venv\\Scripts\\python scripts\\benchmark_ollama.py
    .venv\\Scripts\\python scripts\\benchmark_ollama.py --models qwen3:8b --runs 5
    .venv\\Scripts\\python scripts\\benchmark_ollama.py --num-ctx 4096 8192   # context window check

"Long prompt" run: a NEW ~2000-token prompt (like the agent's system prompt + tool
schemas + history) that Ollama cannot take from its cache. Its first-token time is
the honest prompt-processing cost for one agent step.
"""
from __future__ import annotations

import argparse
import json
import platform
import statistics
import subprocess
import time
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "data" / "config" / "llm_selection.json"
REPORT_PATH = ROOT / "docs" / "benchmark.md"
MANUAL_MARKER = "<!-- manual: kept when this script rewrites the file -->"

# A typical agent task: explain tool results in plain language.
BENCHMARK_PROMPT = (
    "Объясни простым языком фермеру результат расчёта: 200 литров навоза КРС "
    "дадут 3.1–4.6 м³ биогаза (около 2.0–2.9 м³ метана) за 25 дней при 37 °C. "
    "Подогрев займёт 9–14 кВт·ч. Ответь 4–5 предложениями."
)


def load_config() -> dict:
    """Read the shared LLM settings used by the dashboard and the agent."""
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def post_json(url: str, payload: dict, timeout: float = 300.0) -> dict:
    """Send a JSON POST request and return the decoded JSON answer."""
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def get_json(url: str) -> dict:
    """Send a GET request and return the decoded JSON answer."""
    with urllib.request.urlopen(url, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def unload_model(base_url: str, model: str) -> None:
    """Ask Ollama to free the model from VRAM (keep_alive=0)."""
    post_json(f"{base_url}/api/generate", {"model": model, "keep_alive": 0})


def chat_options(config: dict) -> dict:
    """Generation options identical to what the agent sends."""
    return {
        "num_ctx": config["num_ctx"],
        "num_gpu": config["num_gpu"],
        "temperature": 0.2,
        "num_predict": 220,
    }


def long_prompt(tag: int) -> str:
    """A unique ~2000-token prompt (the tag defeats Ollama's prompt cache)."""
    line = ("Запись {i}: реактор {v} л, навоз КРС, температура 37 °C, наружный воздух {t} °C, "
            "утепление базовое, выход метана 2.9–5.2 м³ за 30 дней.")
    body = "\n".join(line.format(i=i, v=150 + i, t=tag % 20 - i % 7) for i in range(55))
    return f"Сеанс {tag}. Журнал наблюдений:\n{body}\n\nКратко, одним предложением: какой средний объём реактора?"


def run_streaming_chat(base_url: str, model: str, config: dict, prompt: str = BENCHMARK_PROMPT) -> dict:
    """Run one streamed chat request and time the first token.

    Returns a dict with first_token_s, total_s and Ollama's own counters.
    """
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": True,
        "think": config["think"],
        "keep_alive": config["keep_alive"],
        "options": chat_options(config),
    }
    request = urllib.request.Request(
        f"{base_url}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    started = time.perf_counter()
    first_token_s = None
    final_chunk: dict = {}
    with urllib.request.urlopen(request, timeout=300) as response:
        for raw_line in response:
            if not raw_line.strip():
                continue
            chunk = json.loads(raw_line)
            text = chunk.get("message", {}).get("content", "")
            if text and first_token_s is None:
                first_token_s = time.perf_counter() - started
            if chunk.get("done"):
                final_chunk = chunk
    total_s = time.perf_counter() - started
    eval_seconds = final_chunk.get("eval_duration", 0) / 1e9
    return {
        "first_token_s": first_token_s or total_s,
        "prompt_tokens": final_chunk.get("prompt_eval_count", 0),
        "total_s": total_s,
        "load_s": final_chunk.get("load_duration", 0) / 1e9,
        "output_tokens": final_chunk.get("eval_count", 0),
        "tokens_per_s": final_chunk.get("eval_count", 0) / eval_seconds if eval_seconds else 0.0,
    }


def gpu_share(base_url: str, model: str) -> dict:
    """Read /api/ps (same as `ollama ps`) and compute the share of the model in VRAM."""
    for loaded in get_json(f"{base_url}/api/ps").get("models", []):
        if loaded.get("name") == model or loaded.get("model") == model:
            size = loaded.get("size", 0)
            size_vram = loaded.get("size_vram", 0)
            return {
                "size_gb": size / 1e9,
                "vram_gb": size_vram / 1e9,
                "gpu_percent": 100.0 * size_vram / size if size else 0.0,
                "context": loaded.get("context_length"),
            }
    return {"size_gb": 0.0, "vram_gb": 0.0, "gpu_percent": 0.0, "context": None}


def gpu_name() -> str:
    """Return the GPU name from nvidia-smi, or 'unknown'."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=15, check=True,
        )
        return result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def benchmark_model(base_url: str, model: str, config: dict, runs: int) -> dict:
    """Cold start (model unloaded) + several warm runs for one model."""
    print(f"\n=== {model} ===")
    # Free VRAM completely: 8b and 4b together do not fit into 8 GB.
    for loaded in get_json(f"{base_url}/api/ps").get("models", []):
        unload_model(base_url, loaded["name"])
    time.sleep(2)
    cold = run_streaming_chat(base_url, model, config)
    print(f"cold start: load {cold['load_s']:.1f} s, first token {cold['first_token_s']:.2f} s")
    placement = gpu_share(base_url, model)
    print(f"GPU: {placement['gpu_percent']:.0f}% ({placement['vram_gb']:.2f} of {placement['size_gb']:.2f} GB)")

    warm_runs = []
    for index in range(runs):
        result = run_streaming_chat(base_url, model, config)
        warm_runs.append(result)
        print(
            f"run {index + 1}: first token {result['first_token_s']:.2f} s, "
            f"{result['tokens_per_s']:.1f} tok/s, total {result['total_s']:.1f} s"
        )
    long_runs = [run_streaming_chat(base_url, model, config, long_prompt(int(time.time()) + index))
                 for index in range(runs)]
    long_first = statistics.median(r["first_token_s"] for r in long_runs)
    print(f"long prompt (~{long_runs[0]['prompt_tokens']} tokens, no cache): first token {long_first:.2f} s")
    return {
        "model": model,
        "num_ctx": config["num_ctx"],
        "long_prompt_tokens": long_runs[0]["prompt_tokens"],
        "long_first_token_s": long_first,
        "cold": cold,
        "placement": placement,
        "first_token_s": statistics.median(r["first_token_s"] for r in warm_runs),
        "tokens_per_s": statistics.median(r["tokens_per_s"] for r in warm_runs),
        "total_s": statistics.median(r["total_s"] for r in warm_runs),
        "output_tokens": statistics.median(r["output_tokens"] for r in warm_runs),
    }


def write_report(results: list[dict], config: dict, runs: int) -> None:
    """Write a short Markdown report for the jury / documentation."""
    lines = [
        "# Скорость локальной LLM (Ollama)",
        "",
        f"Дата замера: {datetime.now():%Y-%m-%d %H:%M}  ",
        f"Железо: {gpu_name()}, {platform.processor() or platform.machine()}  ",
        f"Настройки (из `data/config/llm_selection.json`): num_ctx в таблице, "
        f"think={str(config['think']).lower()}, keep_alive=\"{config['keep_alive']}\", "
        f"num_gpu={config['num_gpu']} (все слои на GPU)  ",
        f"Скрипт: `scripts/benchmark_ollama.py`, медиана из {runs} «тёплых» запусков, "
        "ответ ~200 токенов на русском.",
        "",
        "| Модель | num_ctx | На GPU | VRAM, ГБ | Холодная загрузка, с | Первый токен, с | "
        "Первый токен, длинный промпт, с | Скорость, ток/с | Ответ целиком, с |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for item in results:
        lines.append(
            f"| {item['model']} | {item['num_ctx']} | {item['placement']['gpu_percent']:.0f}% "
            f"| {item['placement']['vram_gb']:.2f} | {item['cold']['load_s']:.1f} "
            f"| {item['first_token_s']:.2f} | {item['long_first_token_s']:.2f} (~{item['long_prompt_tokens']} ток.) "
            f"| {item['tokens_per_s']:.1f} | {item['total_s']:.1f} |"
        )
    lines += [
        "",
        "Как читать:",
        "- **На GPU 100%** — вся модель в видеопамяти, процессор не тормозит генерацию (то же, что `ollama ps`).",
        "- **Холодная загрузка** — первый запрос после старта; поэтому `ЗАПУСК_BioReactor.bat` прогревает модель заранее.",
        "- **Первый токен** — сколько ждать, пока ответ начнёт печататься (цель < 3 с).",
        "  В «тёплых» запусках вопрос одинаковый, и Ollama берёт его обработку из кэша,",
        "  поэтому первый токен почти мгновенный. Для нового вопроса с описанием",
        "  инструментов агента он будет больше; реальные времена агента — в `docs/eval.md`.",
        "- **Длинный промпт** — новый текст ~2000 токенов (как системный промпт + схемы инструментов + история),",
        "  который Ollama не может взять из кэша: честная цена одного шага агента.",
        "- **num_ctx** — окно контекста. Больше окно = больше памяти под KV-кэш. Если модель перестаёт",
        "  помещаться в 8 ГБ, «На GPU» падает ниже 100% и скорость резко проседает.",
        "",
    ]
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Keep the hand-written part (speed investigation, A/B) below the marker.
    old = REPORT_PATH.read_text(encoding="utf-8") if REPORT_PATH.exists() else ""
    if MANUAL_MARKER in old:
        lines.append(MANUAL_MARKER + old.split(MANUAL_MARKER, 1)[1])
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nReport written to {REPORT_PATH}")


def main() -> None:
    config = load_config()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--models", nargs="+", default=[config["model"], config["fallback_model"]])
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--num-ctx", type=int, nargs="+", default=[config["num_ctx"]],
                        help="context windows to compare, e.g. 4096 8192")
    args = parser.parse_args()

    base_url = config["ollama_url"]
    results = [benchmark_model(base_url, model, {**config, "num_ctx": num_ctx}, args.runs)
               for model in args.models for num_ctx in args.num_ctx]
    write_report(results, config, args.runs)
    # Leave the main model loaded for the demo.
    run_streaming_chat(base_url, config["model"], config)


if __name__ == "__main__":
    main()
