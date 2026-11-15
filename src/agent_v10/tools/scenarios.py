"""Tool compare_scenarios: 2–3 variants side by side in one table.

A scenario can change the feedstock (or mixture), the temperature regime or
the insulation. Every scenario is calculated by the same tools, so the table
is consistent:  methane, biogas, heating cost and net balance (gas heat − cost).
"""
from __future__ import annotations

from src.agent_v10.i18n import t
from src.agent_v10.ranges import make, mid, multiply, subtract
from src.agent_v10.tools.common import pair, result, unique, unique_sources
from src.agent_v10.tools.heating import estimate_heating_energy
from src.agent_v10.tools.methane import batch_mass_and_volume, estimate_methane, normalize_component
from src.agent_v10.tools.regimes import BOILER_EFFICIENCY

MAX_SCENARIOS = 3


def default_scenarios(facts: dict, language: str = "ru") -> list[dict]:
    """Scenarios built from memory when the LLM did not give any.

    * 2+ components: "first substrate only" vs "the whole mixture"
      (this answers "what if I add 30 kg of food waste?")
    * 1 component: mesophilic vs thermophilic
    """
    components = facts.get("components") or []
    if len(components) >= 2:
        first = components[0]
        without = {"ru": "без добавки", "en": "without the addition", "kk": "қоспасыз"}
        with_mix = {"ru": "смесь", "en": "mixture", "kk": "қоспа"}
        return [
            {"label": without.get(language, without["ru"]), "components": [first]},
            {"label": with_mix.get(language, with_mix["ru"]), "components": components},
        ]
    if components:
        return [
            {"label": "37 °C", "components": components, "regime": "mesophilic"},
            {"label": "52 °C", "components": components, "regime": "thermophilic"},
        ]
    return []


def compare_scenarios(scenarios: list[dict], ambient_c: float | None = None, insulation: str | None = None,
                      reactor_volume_l: float | None = None, language: str = "ru") -> dict:
    """Calculate every scenario and the difference to the first one."""
    if len(scenarios) < 2:
        return result("compare_scenarios", ok=False, data={"status": "needs_two_scenarios"},
                      llm={"status": "needs_two_scenarios"}, question=t("ask_substrate", language))
    rows, assumptions, sources = [], [], []
    question = None
    for scenario in scenarios[:MAX_SCENARIOS]:
        components = [normalize_component(c) for c in scenario.get("components") or []]
        regime = scenario.get("regime") or "mesophilic"
        gas = estimate_methane(components, regime=regime, language=language)
        if not gas["ok"]:
            return {**gas, "name": "compare_scenarios"}
        batch = batch_mass_and_volume(components, language)
        heat = estimate_heating_energy(
            feed_mass_kg=batch["mass_kg"], feed_volume_l=batch["volume_l"],
            reactor_volume_l=scenario.get("reactor_volume_l", reactor_volume_l),
            insulation=scenario.get("insulation", insulation), ambient_c=scenario.get("ambient_c", ambient_c),
            target_c=gas["data"]["temperature_c"], days=mid(gas["data"]["days"]), language=language)
        net = subtract(multiply(gas["data"]["energy_kwh"], BOILER_EFFICIENCY), heat["data"]["total_kwh"])
        rows.append({
            "label": scenario.get("label") or f"#{len(rows) + 1}",
            "components": gas["llm"]["components"], "regime": gas["data"]["regime_name"],
            "temperature_c": gas["data"]["temperature_c"],
            "methane_m3": gas["data"]["methane_m3"], "biogas_m3": gas["data"]["biogas_m3"],
            "energy_kwh": gas["data"]["energy_kwh"], "heating_kwh": heat["data"]["total_kwh"], "net_kwh": net,
        })
        assumptions += gas["assumptions"] + heat["assumptions"]
        sources += gas["sources"] + heat["sources"]
        question = question or gas["question"]
    base = rows[0]
    for row in rows:
        row["methane_difference_m3"] = make(row["methane_m3"]["low"] - base["methane_m3"]["low"],
                                            row["methane_m3"]["high"] - base["methane_m3"]["high"])
    data = {"status": "ok", "scenarios": rows}
    llm = {
        "scenarios": [{
            "name": row["label"], "feed": row["components"], "regime": f"{row['regime']} {row['temperature_c']} °C",
            "methane_m3": pair(row["methane_m3"]), "biogas_m3": pair(row["biogas_m3"]),
            "heating_cost_kwh": pair(row["heating_kwh"]), "net_kwh": pair(row["net_kwh"]),
            "methane_change_vs_first_m3": pair(row["methane_difference_m3"]),
        } for row in rows],
        "label": "assumption",
    }
    return result("compare_scenarios", ok=True, data=data, llm=llm, assumptions=unique(assumptions),
                  sources=unique_sources(sources), label="assumption", question=question)
