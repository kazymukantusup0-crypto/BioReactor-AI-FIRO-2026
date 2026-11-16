"""Sanity check of every feed against ONE reference table (KTBL 2025) -> docs/substrate_sanity.md.

For each material/state of the agent the mesophilic estimate of 1 t of fresh mass (estimate_methane,
the same code the agent uses) is compared with the practical biogas yield of KTBL-Schrift 526 (2025):
    in corridor   our biogas range overlaps the reference ±30 %
    order         for every pair of directly matched feeds whose references differ by more than 25 %,
                  our central estimates are in the same order ("which gives more gas").

Usage:  .venv\\Scripts\\python scripts\\substrate_sanity.py   (also checked by tests/test_agent_v10_substrate_sanity.py)
"""
from __future__ import annotations

import sys
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.agent_v10 import substrates  # noqa: E402
from src.agent_v10.ranges import make  # noqa: E402
from src.agent_v10.tools.methane import estimate_methane  # noqa: E402

ORDER_MARGIN = 1.25  # references closer than 25 % are "about the same" — no order is required
OUR_FEEDS = [("cattle_manure", "slurry"), ("cattle_manure", "fresh_solid"), ("cattle_manure", "bedded"),
             ("swine_manure", "slurry"), ("poultry_manure", "fresh_solid"), ("poultry_manure", "dry"),
             ("sheep_goat_manure", "fresh_solid"), ("horse_manure", "fresh_solid"), ("food_waste", "fresh_solid"),
             ("vegetable_waste", "fresh_solid"), ("grass", "fresh_solid"), ("silage", "silage"), ("straw", "dry")]


def ours(material: str, state: str) -> dict | None:
    """Our mesophilic estimate per tonne of fresh mass."""
    result = estimate_methane([{"substrate": material, "amount": 1000, "unit": "kg", "state": state}])
    if not result["ok"]:
        return None
    found = substrates.composition(material, state)
    data = result["data"]
    return {"biogas": data["biogas_m3"], "methane": data["methane_m3"], "label": result["label"],
            "basis": found.get("basis"), "profiles": found.get("profile_ids") or [],
            "replaced": found.get("reference")}


def rows() -> list[dict]:
    table = substrates.reference_table()
    out = []
    for material, state in OUR_FEEDS:
        estimate = ours(material, state)
        reference = next((r for r in table["rows"] if r["material"] == material and r["state"] == state), None)
        row = {"material": material, "state": state, "ours": estimate, "reference": reference}
        if estimate and reference:
            corridor = make(reference["biogas_m3_t_fm"] * (1 - table["corridor_share"]),
                            reference["biogas_m3_t_fm"] * (1 + table["corridor_share"]))
            row["corridor"] = corridor
            row["in_corridor"] = estimate["biogas"]["high"] >= corridor["low"] and estimate["biogas"]["low"] <= corridor["high"]
        out.append(row)
    return out


def center(value: dict) -> float:
    return (value["low"] + value["high"]) / 2


def order_problems(table_rows: list[dict]) -> list[str]:
    """Pairs of directly matched feeds whose order differs from the reference."""
    direct = [r for r in table_rows if r["ours"] and r["reference"] and r["reference"]["match"] == "direct"]
    problems = []
    for a, b in combinations(direct, 2):
        ra, rb = a["reference"]["biogas_m3_t_fm"], b["reference"]["biogas_m3_t_fm"]
        if ra == rb or max(ra, rb) / min(ra, rb) < ORDER_MARGIN:
            continue
        if (ra > rb) != (center(a["ours"]["biogas"]) > center(b["ours"]["biogas"])):
            problems.append(f"{a['material']}/{a['state']} vs {b['material']}/{b['state']}")
    return problems


def fmt(value: dict) -> str:
    return f"{value['low']:.0f}–{value['high']:.0f}"


def write(output: Path) -> tuple[list[dict], list[str]]:
    table_rows = rows()
    problems = order_problems(table_rows)
    source = substrates.reference_table()["source"]
    lines = [
        "# Проверка здравого смысла: выход газа по каждому сырью",
        "",
        f"Справочник — одна таблица: **{source['title']}**. Это выход работающих установок на тонну свежей массы; "
        "значения считаны по длине столбиков графика (±3 Nm³/т). Наш выход — мезофильный расчёт агента "
        "(`estimate_methane`, 1 т свежей массы). **Коридор = справочное ±30 %** — наш допуск, не из источника. "
        "Скрипт: `scripts/substrate_sanity.py`, тест: `tests/test_agent_v10_substrate_sanity.py`.",
        "",
        "| Сырьё (состояние) | Наш выход, м³ биогаза/т | л CH4/кг | Справочник KTBL 2025 | м³/т | Коридор ±30 % | В коридоре | Основа нашего числа |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in table_rows:
        name = f"{substrates.material_name(r['material'], 'ru')} ({substrates.STATE_NAMES['ru'].get(r['state'], r['state'])})"
        o, ref = r["ours"], r["reference"]
        if not o:
            lines.append(f"| {name} | нет данных | — | — | — | — | — | — |")
            continue
        basis = ("справочник KTBL 2025 (профиль заменён)" if o["basis"] == "practice"
                 else ("измеренные профили: " + ", ".join(o["profiles"])) if o["profiles"] else "справочные допущения (FNR)")
        if ref:
            match = "" if ref["match"] == "direct" else " *(приблизительно)*"
            verdict = "✅ да" if r["in_corridor"] else "❌ нет"
            lines.append(f"| {name} | {fmt(o['biogas'])} | {fmt(o['methane'])} | {ref['reference']}{match} | "
                         f"{ref['biogas_m3_t_fm']} | {fmt(r['corridor'])} | {verdict} | {basis} |")
        else:
            lines.append(f"| {name} | {fmt(o['biogas'])} | {fmt(o['methane'])} | нет в таблице | — | — | — | {basis} |")
    lines += ["", "## Порядок «что даёт больше газа»", ""]
    lines.append("Для каждой пары сырья с прямым соответствием, у которых справочные значения отличаются больше чем на 25 %, "
                 "порядок наших центральных оценок должен совпадать со справочником.")
    lines.append("")
    lines.append("**Нарушений нет.**" if not problems else "**Нарушения:** " + "; ".join(problems))
    lines += ["", "## Пояснения", "",
              "- **Свиная жижа.** Две измеренные пробы в базе (Pham 2013: TS 3.18 %; Eftaxias 2024: TS 2.23 %) сильно "
              "разбавлены водой и дают 2–4 л CH4/кг в реакторе — ниже коридора. Взят справочный выход KTBL (13 м³/т, 63 % CH4). "
              "Старый справочник FNR 2007 давал 28 м³/т — в новой таблице KTBL свиная жижа даёт МЕНЬШЕ коровьей (13 против 29).",
              "- **Навоз КРС с подстилкой.** Измеренный профиль (Baek 2020) даёт 32–42 м³/т против 95 у «Rindermist» KTBL — "
              "взят справочный выход.",
              "- **Солома.** В коридоре, но по KTBL — только как добавка и обычно после предобработки.",
              "- **Овощные отходы** сравниваются с «Bioabfall», а **свежая трава** — с травяным силосом: прямого соответствия "
              "нет (в овощах и свежей траве больше воды), поэтому они не участвуют в проверке порядка.",
              "- **Овечий/козий и конский навоз** в таблице KTBL нет — проверить не с чем.",
              "- Справочное значение заменяет профиль, только если диапазоны не пересекаются; тогда диапазон = справочное ±15 % "
              "(наше допущение о разбросе), а доля режима к мезофильному расчёту повторно не применяется."]
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return table_rows, problems


if __name__ == "__main__":
    table_rows, problems = write(ROOT / "docs" / "substrate_sanity.md")
    outside = [f"{r['material']}/{r['state']}" for r in table_rows if r.get("in_corridor") is False]
    print("outside corridor:", outside or "none")
    print("order problems:", problems or "none")
