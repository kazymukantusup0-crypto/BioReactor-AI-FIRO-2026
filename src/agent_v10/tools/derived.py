"""Conclusions that combine two tool results, calculated by Python (not by the LLM).

gas_vs_heating — "is the gas enough to keep the reactor warm?"
    usable gas heat = gas energy × boiler efficiency 0.85–0.90
    coverage, %     = usable gas heat / heating need × 100
    pessimistic: low gas / high need;  optimistic: high gas / low need
    enough = "yes" if even the pessimistic coverage ≥ 100 %,
             "no"  if even the optimistic coverage < 100 %, otherwise "maybe".

Why: the number check only proves that every number in the LLM text comes from
a tool; it cannot see a wrong conclusion ("the gas is enough" when it covers
8 % of the need). With this result the LLM gets the verdict ready-made and the UI
shows it as a card.
"""
from __future__ import annotations

from src.agent_v10.ranges import multiply
from src.agent_v10.tools.common import pair, result, weakest
from src.agent_v10.tools.regimes import BOILER_EFFICIENCY

VERDICT_TEXT = {
    "yes": {"ru": "да", "en": "yes", "kk": "иә"},
    "no": {"ru": "нет", "en": "no", "kk": "жоқ"},
    "maybe": {"ru": "на грани", "en": "borderline", "kk": "шекарада"},
}
VERDICT_FOR_LLM = {
    "yes": "the gas covers all heating",
    "no": "the gas does NOT cover the heating; extra heat (electricity) is needed",
    "maybe": "the gas may or may not cover the heating (borderline)",
}
ASSUMPTION = {
    "ru": "газ сжигают в котле с КПД 85–90%, тепло идёт на подогрев этой же партии",
    "en": "the gas is burned in a boiler with 85–90% efficiency to heat the same batch",
    "kk": "газ ПӘК-і 85–90% қазандықта жағылады, жылу осы партияны қыздыруға жұмсалады",
}


def _first_ok(results: list[dict], name: str) -> dict | None:
    return next((item for item in results if item.get("name") == name and item.get("ok")), None)


def gas_vs_heating(results: list[dict], language: str = "ru") -> dict | None:
    """Combine estimate_methane and estimate_heating_energy; None if one of them is missing."""
    gas, heating = _first_ok(results, "estimate_methane"), _first_ok(results, "estimate_heating_energy")
    if gas is None or heating is None or _first_ok(results, "gas_vs_heating"):
        return None
    gas_heat = multiply(gas["data"]["energy_kwh"], BOILER_EFFICIENCY)
    need = heating["data"]["total_kwh"]
    if need["low"] <= 0:
        return None
    coverage = {"low": 100 * gas_heat["low"] / need["high"], "high": 100 * gas_heat["high"] / need["low"]}
    enough = "yes" if coverage["low"] >= 100 else "no" if coverage["high"] < 100 else "maybe"
    data = {"status": "ok", "gas_heat_kwh": gas_heat, "heating_need_kwh": need, "coverage_percent": coverage, "enough": enough}
    llm = {"gas_heat_kwh": pair(gas_heat), "heating_need_kwh": pair(need), "gas_covers_heating_percent": pair(coverage),
           "enough_gas_for_heating": enough, "verdict": VERDICT_FOR_LLM[enough]}
    return result("gas_vs_heating", ok=True, data=data, llm=llm, assumptions=[ASSUMPTION.get(language, ASSUMPTION["ru"])],
                  label=weakest([gas["label"], heating["label"]]))
