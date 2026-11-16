"""Rehearse the jury demo: run every scenario of frontend/src/demoScenarios.json through the real agent.

Prints, for every message, the agent's steps, the Python verdicts, the cards and the answer,
and writes them to docs/demo_rehearsal.md (a fresh temporary database, nothing is saved).

Usage:
    .venv\\Scripts\\python scripts\\run_demo_scenarios.py               # with the LLM (Ollama)
    .venv\\Scripts\\python scripts\\run_demo_scenarios.py --no-llm      # what happens if Ollama is down
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.agent_v10.agent import Agent  # noqa: E402
from src.agent_v10.memory import Memory  # noqa: E402

SCENARIOS = ROOT / "frontend" / "src" / "demoScenarios.json"


def run_message(agent: Agent, conversation: str, text: str, use_llm: bool) -> list[str]:
    lines, started = [f"**Вопрос:** {text}", ""], time.perf_counter()
    for event in agent.run(conversation, text, use_llm=use_llm):
        kind = event["type"]
        if kind == "tool_call":
            lines.append(f"- 🔧 {event['name']} (выбрал {'ИИ' if event['by'] == 'llm' else 'Python'})")
        elif kind == "verification":
            problem = event.get("contradicts") or event.get("unknown_numbers")
            lines.append(f"- {'✅' if event['ok'] else '⚠️'} проверка (попытка {event['attempt']})" + (f": {problem}" if problem else ""))
        elif kind == "note":
            lines.append(f"- ℹ️ {event['message']}")
        elif kind == "answer":
            for verdict in event.get("verdicts") or []:
                lines.append(f"- 🟢 **{verdict['title']}:** {verdict['value']}")
            if event["numbers"]:
                lines.append("- Карточки: " + "; ".join(
                    f"{c['title']} ≈{c['center']} ({c['range']}) {c['unit']}" if c.get("center") else f"{c['title']} {c['value']} {c['unit']}"
                    for c in event["numbers"]))
            lines += ["", f"> {event['explanation']}"]
            if event.get("question"):
                lines.append(f"> ❓ {event['question']}")
            lines.append(f"\n_Режим: {event['mode']}, числа и выводы сверены: {'да' if event['verified'] else 'нет, шаблон'}, "
                         f"{time.perf_counter() - started:.1f} с_")
    return lines + [""]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--no-llm", action="store_true", help="run every scenario without the LLM")
    parser.add_argument("--output", type=Path, default=ROOT / "docs" / "demo_rehearsal.md")
    args = parser.parse_args()
    scenarios = json.loads(SCENARIOS.read_text(encoding="utf-8"))["scenarios"]
    lines = [f"# Репетиция показа — {datetime.now():%Y-%m-%d %H:%M}", "",
             f"Скрипт `scripts/run_demo_scenarios.py`{' --no-llm' if args.no_llm else ''}; сценарии — "
             "`frontend/src/demoScenarios.json` (те же кнопки в режиме жюри).", ""]
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
        agent = Agent(memory=Memory(Path(folder) / "demo.sqlite3"))
        for scenario in scenarios:
            lines += [f"## {scenario['title']}", "", f"_{scenario['goal']}_", ""]
            conversation = Memory.new_id()
            for message in scenario["messages"]:
                lines += run_message(agent, conversation, message, use_llm=not (args.no_llm or scenario.get("noLlm")))
            print(f"done: {scenario['title']}")
    args.output.write_text("\n".join(lines), encoding="utf-8")
    print(f"Report: {args.output}")


if __name__ == "__main__":
    main()
