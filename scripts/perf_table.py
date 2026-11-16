"""Markdown table from saved eval runs (docs/perf/eval_<tag>.json) and GPU traces (trace_<tag>.csv).

    .venv\\Scripts\\python scripts\\perf_table.py 8b_cold 8b_warm 4b_cold 4b_warm 8b_pace20

Accuracy = all four checks of a message passed (tool chosen by the model, numbers match the
tools, language, meaning checks). Times are per message. "Thermal" = share of busy seconds
when the driver lowered the clock because the GPU reached its target temperature (87 °C).
"""
from __future__ import annotations

import csv
import json
import statistics
import sys
from pathlib import Path

PERF = Path(__file__).resolve().parents[1] / "docs" / "perf"


def trace_stats(tag: str) -> dict:
    path = PERF / f"trace_{tag}.csv"
    if not path.exists():
        return {}
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    busy = [r for r in rows if (r.get("util_pct") or "").strip().isdigit() and int(r["util_pct"]) > 50]
    if not busy:
        return {}
    temps = [float(r["temp_c"]) for r in busy]
    clocks = sorted(float(r["sm_mhz"]) for r in busy)
    thermal = sum(r.get("sw_thermal", "").startswith("Active") or r.get("hw_thermal", "").startswith("Active") for r in busy)
    return {"temp_max": max(temps), "clock_median": clocks[len(clocks) // 2], "thermal_share": thermal / len(busy)}


def row(tag: str) -> str:
    data = json.loads((PERF / f"eval_{tag}.json").read_text(encoding="utf-8"))
    summary, rows = data["summary"], data["rows"]
    good = sum(r["tool_ok"] and r["numbers_ok"] and r["language_ok"] and r["checks_ok"] for r in rows)
    speeds = [r["tokens_per_s"] for r in rows if r.get("tokens_per_s")]
    trace = trace_stats(tag)
    thermal = f"{trace['thermal_share']:.0%}" if trace else "—"
    return (f"| {tag} | {summary['model']} | {summary['tool_ok']}/{len(rows)} | {summary['numbers_ok']}/{len(rows)} | "
            f"{summary['language_ok']}/{len(rows)} | {summary['checks_ok']}/{summary['checks_total']} | **{good}/{len(rows)}** | "
            f"{summary['first_token_median_s']:.1f} / {summary['first_token_max_s']:.1f} | "
            f"**{summary['total_median_s']:.1f}** / {summary['total_max_s']:.1f} | "
            f"{statistics.median(speeds):.0f} | {summary['gpu_temperature']} | {thermal} |")


def main() -> None:
    tags = sys.argv[1:] or sorted(p.stem[5:] for p in PERF.glob("eval_*.json"))
    print("| Прогон | Модель | Инструмент | Числа | Язык | Проверки смысла | Всё верно | 1-й токен, медиана / макс, с "
          "| Ответ, медиана / макс, с | Ток/с (медиана) | Видеокарта: начало → конец | Тепловой сброс частоты |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for tag in tags:
        print(row(tag))


if __name__ == "__main__":
    main()
