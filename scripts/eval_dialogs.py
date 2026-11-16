"""Evaluate agent v10 on 10 dialogs against the real local LLM and write docs/eval.md.

Metrics per message:
    tool ok       the LLM itself chose an expected tool (Python "forced" calls do not count)
    numbers ok    every number in the explanation is found in tool results (number check)
    language ok   the answer is in the user's language
    first token   seconds from the message to the first token of the final answer
    total         seconds until the complete answer
    prompt tokens largest prompt sent to the LLM (system + tool schemas + history + tool results)

Usage:
    .venv\\Scripts\\python scripts\\eval_dialogs.py                      # qwen3:8b from the config
    .venv\\Scripts\\python scripts\\eval_dialogs.py --model qwen3:4b-q4_K_M --output docs/eval_qwen3_4b.md
"""
from __future__ import annotations

import argparse
import statistics
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.agent_v10.agent import Agent  # noqa: E402
from src.agent_v10.config import llm_settings  # noqa: E402
from src.agent_v10.facts import detect_language  # noqa: E402
from src.agent_v10.llm import OllamaClient  # noqa: E402
from src.agent_v10.memory import Memory  # noqa: E402

# (dialog name, [(message, expected tools, expected language), ...])
DIALOGS = [
    ("1. Навоз в литрах + уточнение", [
        ("У меня 200 литров коровьего навоза, сколько будет газа?", {"estimate_methane"}, "ru"),
        ("Жидкий.", {"estimate_methane"}, "ru"),
    ]),
    ("2. Зима, реактор без утепления", [
        ("Какую температуру ставить зимой при −15 на улице, реактор 250 литров, не утеплён?", {"recommend_temperature_regime"}, "ru"),
    ]),
    ("3. Казахский: сколько газа", [
        ("Сиыр көңі 200 литр, қанша газ болады?", {"estimate_methane"}, "kk"),
    ]),
    ("4. Смесь: добавить пищевые отходы", [
        ("У меня 200 л жидкого навоза КРС. Сколько газа?", {"estimate_methane"}, "ru"),
        ("А если добавить 30 кг пищевых отходов?", {"compare_scenarios"}, "ru"),
    ]),
    ("5. English: buckets of pig slurry", [
        ("I have 2 buckets of pig slurry. How much biogas will I get?", {"estimate_methane"}, "en"),
    ]),
    ("6. Затраты на подогрев", [
        ("Сколько электроэнергии уйдёт на подогрев 300 л навоза КРС за 30 дней? Реактор 400 л, утеплён, на улице 0 °C.",
         {"estimate_heating_energy"}, "ru"),
    ]),
    ("7. Что выгоднее: тепло или электричество", [
        ("Что выгоднее из 1 тонны птичьего помёта: тепло или электричество? Сколько это в тенге?",
         {"energy_balance_and_economics"}, "ru"),
    ]),
    ("8. Смена сырья", [
        ("500 кг силоса — сколько будет метана?", {"estimate_methane"}, "ru"),
        ("А если вместо силоса будет 500 кг соломы?", {"estimate_methane", "compare_scenarios"}, "ru"),
    ]),
    ("9. Источник и обоснование", [
        ("Почему мезофильный режим считают устойчивым? Дай источник.", {"search_knowledge"}, "ru"),
    ]),
    ("10. Казахский: режим зимой", [
        ("Қыста сыртта −20 градус, реактор жылытылмаған, 300 литр сиыр көңі бар. Қандай температура қою керек?",
         {"recommend_temperature_regime"}, "kk"),
    ]),
    ("11. Хватит ли газа на подогрев", [
        ("У меня 150 литров коровьего навоза, бочка 200 литров не утеплена, на улице −10. "
         "Сколько будет газа и хватит ли его на подогрев?", {"estimate_heating_energy"}, "ru"),
    ]),
]


def run_message(agent: Agent, conversation_id: str, text: str) -> dict:
    """Run one message and collect the metrics from the event stream."""
    started = time.perf_counter()
    llm_tools, forced, prompt_tokens, final = [], False, [], None
    for event in agent.run(conversation_id, text):
        if event["type"] == "tool_call" and event.get("by") == "llm":
            llm_tools.append(event["name"])
        elif event["type"] == "note" and event.get("code") in {"forced_tools", "llm_fallback"}:
            forced = True
        elif event["type"] == "llm_step" and event.get("prompt_tokens"):
            prompt_tokens.append(event["prompt_tokens"])
        elif event["type"] == "answer":
            final = event
    total = time.perf_counter() - started
    first_token_ms = (final.get("timings") or {}).get("first_answer_token_ms")
    return {
        "tools": llm_tools, "forced": forced, "final": final, "total_s": total,
        "first_token_s": first_token_ms / 1000 if first_token_ms else None,
        "prompt_tokens": max(prompt_tokens) if prompt_tokens else 0,
    }


def evaluate(model: str) -> tuple[list[dict], dict]:
    client = OllamaClient(model=model)
    if not client.available():
        raise SystemExit(f"Ollama or model {model} is not available")
    rows = []
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
        agent = Agent(memory=Memory(Path(folder) / "eval.sqlite3"), llm=client)
        for dialog_name, turns in DIALOGS:
            conversation_id = Memory.new_id()
            for text, expected_tools, language in turns:
                metrics = run_message(agent, conversation_id, text)
                final = metrics["final"]
                explanation = final["explanation"]
                answer_language = detect_language(explanation) if explanation else "?"
                row = {
                    "dialog": dialog_name, "message": text, "expected": sorted(expected_tools),
                    "tools": metrics["tools"], "forced": metrics["forced"],
                    "tool_ok": bool(set(metrics["tools"]) & expected_tools) and not metrics["forced"],
                    "numbers_ok": final["verified"], "language": answer_language,
                    "language_ok": answer_language == language, "mode": final["mode"],
                    "first_token_s": metrics["first_token_s"], "total_s": metrics["total_s"],
                    "prompt_tokens": metrics["prompt_tokens"], "explanation": explanation,
                    "numbers": "; ".join(f"{c['title']}: {c['value']} {c['unit']}".strip() for c in final["numbers"][:3]),
                }
                rows.append(row)
                print(f"{'OK ' if row['tool_ok'] and row['numbers_ok'] and row['language_ok'] else 'BAD'} "
                      f"{row['total_s']:5.1f}s tools={row['tools']} verified={row['numbers_ok']} lang={answer_language} | {text[:60]}")
    first_tokens = [r["first_token_s"] for r in rows if r["first_token_s"]]
    summary = {
        "model": model, "messages": len(rows), "dialogs": len(DIALOGS),
        "tool_ok": sum(r["tool_ok"] for r in rows), "numbers_ok": sum(r["numbers_ok"] for r in rows),
        "language_ok": sum(r["language_ok"] for r in rows),
        "first_token_median_s": statistics.median(first_tokens) if first_tokens else None,
        "first_token_max_s": max(first_tokens) if first_tokens else None,
        "total_median_s": statistics.median(r["total_s"] for r in rows),
        "total_max_s": max(r["total_s"] for r in rows),
        "prompt_tokens_max": max(r["prompt_tokens"] for r in rows),
        "num_ctx": llm_settings()["num_ctx"],
        "gpu": client.gpu_status(),
    }
    return rows, summary


def write_report(rows: list[dict], summary: dict, output: Path) -> None:
    def seconds(value):
        return f"{value:.1f}" if value is not None else "—"

    n = summary["messages"]
    lines = [
        f"# Оценка агента v10 — {summary['model']}",
        "",
        f"Дата: {datetime.now():%Y-%m-%d %H:%M} · {summary['dialogs']} диалогов, {n} сообщений · "
        f"num_ctx={summary['num_ctx']} · GPU: {summary['gpu'].get('gpu_percent', '?')}% · "
        "скрипт `scripts/eval_dialogs.py`",
        "",
        "## Итог",
        "",
        "| Метрика | Результат | Цель |",
        "|---|---|---|",
        f"| Модель сама выбрала правильный инструмент | {summary['tool_ok']}/{n} | все |",
        f"| Числа в тексте совпадают с инструментами | {summary['numbers_ok']}/{n} | все |",
        f"| Ответ на языке пользователя | {summary['language_ok']}/{n} | все |",
        f"| Первый токен ответа, медиана / максимум | {seconds(summary['first_token_median_s'])} / "
        f"{seconds(summary['first_token_max_s'])} с | < 3 с |",
        f"| Полный ответ, медиана / максимум | {seconds(summary['total_median_s'])} / {seconds(summary['total_max_s'])} с | < 15 с |",
        f"| Самый большой промпт (системный + схемы + история + результаты) | {summary['prompt_tokens_max']} токенов | < {summary['num_ctx'] * 3 // 4} (¾ от num_ctx {summary['num_ctx']}) |",
        "",
        "«Первый токен» — от отправки сообщения до первого слова финального ответа "
        "(сюда входит шаг, на котором модель выбирает инструмент, и сам расчёт).",
        "Если модель не вызвала инструмент сама и его вызвал Python (запасной путь), это считается ошибкой выбора инструмента.",
        "",
        "**Что проверка чисел НЕ ловит.** Она подтверждает, что каждое число в тексте есть в результатах инструментов, "
        "но не что модель приписала ему правильный смысл (например, назвала теплопотери «общими затратами»). "
        "Поэтому источник правды в интерфейсе — карточки с цифрами (их строит Python), а текст модели — только пояснение.",
        "",
        "## Сообщения",
        "",
        "| Диалог | Сообщение | Ожидали | Модель вызвала | Числа | Язык | 1-й токен, с | Всего, с | Промпт |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        tools = ", ".join(r["tools"]) or "—"
        if r["forced"]:
            tools += " (+ запасной путь)"
        lines.append(
            f"| {r['dialog']} | {r['message']} | {', '.join(r['expected'])} | {'✅' if r['tool_ok'] else '❌'} {tools} "
            f"| {'✅' if r['numbers_ok'] else '❌'} | {'✅' if r['language_ok'] else '❌'} {r['language']} "
            f"| {seconds(r['first_token_s'])} | {seconds(r['total_s'])} | {r['prompt_tokens']} |")
    lines += ["", "## Ответы агента (объяснение модели)", ""]
    for r in rows:
        lines += [f"**{r['message']}**  ", f"Цифры: {r['numbers'] or '—'}  ", f"> {r['explanation']}", ""]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nReport: {output}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", default=llm_settings()["model"])
    parser.add_argument("--output", type=Path, default=ROOT / "docs" / "eval.md")
    args = parser.parse_args()
    rows, summary = evaluate(args.model)
    write_report(rows, summary, args.output)
    print({k: v for k, v in summary.items() if k != "gpu"})


if __name__ == "__main__":
    main()
