"""Tool recommend_temperature_regime: psychrophilic vs mesophilic vs thermophilic.

For each regime (data/research/temperature_regimes.json):
    gas        = estimate_methane(regime)               -> CH4 m³ and energy kWh
    heat cost  = estimate_heating_energy(setpoint, days) -> kWh for heating + mixing
    gas heat   = gas energy × boiler efficiency 0.85–0.90
    net        = gas heat − heat cost                    (positive = energy surplus)

Recommendation rule (simple and explainable):
    goal "net_energy" (default): the regime with the best middle net balance,
        but thermophilic must beat mesophilic by more than 15 % of the gas
        heat, because it is much less stable (needs ±1 °C, ammonia risk);
    goal "max_gas": most methane;  goal "fastest": shortest digestion.
If even the best regime loses energy, we say so and show what good insulation gives.
"""
from __future__ import annotations

from src.agent_v10.config import temperature_regimes
from src.agent_v10.i18n import t
from src.agent_v10.ranges import make, mid, multiply, range_text, subtract
from src.agent_v10.tools.common import pair, result, unique, unique_sources, weakest
from src.agent_v10.tools.heating import estimate_heating_over_days
from src.agent_v10.tools.methane import batch_mass_and_volume, estimate_methane

BOILER_EFFICIENCY = make(0.85, 0.90)
# Thermophilic must win by more than this share of the mesophilic gas heat.
THERMOPHILIC_MARGIN = 0.25

# Ready-made sentence for the LLM, so it does not mix up heating cost and net balance.
SUMMARY = {
    "ru": "{regime}: подогрев и перемешивание потребуют {heating} кВт·ч, газ даст {gas} кВт·ч тепла, "
          "чистый баланс {net} кВт·ч за {days} дней.",
    "en": "{regime}: heating and mixing need {heating} kWh, the gas gives {gas} kWh of heat, "
          "net balance {net} kWh over {days} days.",
    "kk": "{regime}: қыздыру мен араластыруға {heating} кВт·сағ керек, газ {gas} кВт·сағ жылу береді, "
          "таза баланс {net} кВт·сағ, {days} күн ішінде.",
}

REASONS = {
    "best_net": {
        "ru": "даёт лучший чистый энергобаланс: газа больше, чем уходит на подогрев",
        "en": "gives the best net energy balance: more gas than the heating consumes",
        "kk": "ең жақсы таза энергия балансын береді: газ қыздыруға кететіннен көп",
    },
    "stable_over_thermo": {
        "ru": "термофильный режим ненамного лучше, но гораздо капризнее — надёжнее мезофильный",
        "en": "thermophilic is only slightly better but much less stable — mesophilic is safer",
        "kk": "термофильді режим сәл ғана жақсы, бірақ әлдеқайда тұрақсыз — мезофильді сенімдірек",
    },
    "max_gas": {
        "ru": "даёт больше всего газа",
        "en": "gives the most gas",
        "kk": "ең көп газ береді",
    },
    "fastest": {
        "ru": "сбраживает быстрее всех",
        "en": "digests the fastest",
        "kk": "ең жылдам ашытады",
    },
    "deficit_insulated": {
        "ru": "даже с хорошим утеплением подогрев съедает почти весь газ — партия мала для таких холодов; держите устойчивый мезофильный режим и загружайте больше сырья",
        "en": "even with good insulation heating eats almost all the gas — the batch is small for this cold; keep the stable mesophilic regime and load more feed",
        "kk": "жақсы жылытылса да қыздыру газдың бәрін дерлік жұмсайды — бұл суыққа партия аз; тұрақты мезофильді режимде ұстап, шикізатты көбірек жүктеңіз",
    },
    "deficit": {
        "ru": "при этих условиях подогрев съедает больше энергии, чем даёт газ — сначала утеплите реактор; из режимов этот самый разумный",
        "en": "in these conditions heating needs more energy than the gas gives — insulate the reactor first; this regime is the most sensible",
        "kk": "бұл жағдайда қыздыру газ беретін энергиядан көп жұмсайды — алдымен реакторды жылытыңыз; режимдердің ішінде осы ең орынды",
    },
}


def _regime_case(components: list[dict], regime: dict, ambient_c: float | None, insulation: str | None,
                 reactor_volume_l: float | None, language: str) -> dict:
    """Gas and heating cost of one regime."""
    gas = estimate_methane(components, regime=regime["id"], language=language)
    batch = batch_mass_and_volume(components, language)
    days = regime["digestion_days"]
    setpoint = regime["setpoint_c"]
    # The same function as the tool estimate_heating_energy -> the same numbers.
    heat = estimate_heating_over_days(days, feed_mass_kg=batch["mass_kg"], feed_volume_l=batch["volume_l"],
                                      reactor_volume_l=reactor_volume_l, insulation=insulation, ambient_c=ambient_c,
                                      target_c=setpoint, language=language)
    cost = heat["data"]["total_kwh"]
    gas_heat = multiply(gas["data"]["energy_kwh"], BOILER_EFFICIENCY)
    net = subtract(gas_heat, cost)
    return {
        "id": regime["id"], "name": regime["name"].get(language, regime["name"]["ru"]),
        "setpoint_c": setpoint, "temperature_range_c": regime["temperature_range_c"], "days": days,
        "methane_m3": gas["data"]["methane_m3"], "biogas_m3": gas["data"]["biogas_m3"],
        "gas_energy_kwh": gas["data"]["energy_kwh"], "gas_heat_kwh": gas_heat,
        "heating_kwh": heat["data"]["heating_kwh"],
        "total_cost_kwh": cost, "net_kwh": net, "stability": regime["stability"],
        "risk": regime["risks"].get(language, regime["risks"]["ru"]),
        "_gas": gas, "_heat": heat,
        # Heat loss over the same span of days as the cost, so the heat-loss card is a part of the heating card.
        "_wall": heat["llm"]["wall"],
    }


def _choose(cases: list[dict], goal: str) -> tuple[dict, str]:
    """Pick the recommended regime and the reason code."""
    by_id = {case["id"]: case for case in cases}
    if goal == "max_gas":
        return max(cases, key=lambda c: mid(c["methane_m3"])), "max_gas"
    if goal == "fastest":
        return min(cases, key=lambda c: mid(c["days"])), "fastest"
    best = max(cases, key=lambda c: mid(c["net_kwh"]))
    meso = by_id.get("mesophilic")
    if mid(best["net_kwh"]) < 0:
        # Every regime loses energy: the real advice is "insulate first",
        # and the regime should be the stable one.
        return (meso or best), "deficit"
    if best["id"] == "thermophilic" and meso:
        advantage = mid(best["net_kwh"]) - mid(meso["net_kwh"])
        if advantage < THERMOPHILIC_MARGIN * mid(meso["gas_heat_kwh"]):
            return meso, "stable_over_thermo"
    return best, "best_net"


def recommend_temperature_regime(components: list[dict], ambient_c: float | None = None,
                                 insulation: str | None = None, reactor_volume_l: float | None = None,
                                 goal: str = "net_energy", language: str = "ru") -> dict:
    """Compare the three temperature regimes and recommend one."""
    if not components:
        return result("recommend_temperature_regime", ok=False, data={"status": "needs_substrate"},
                      llm={"status": "needs_substrate"}, question=t("ask_substrate", language))
    first = estimate_methane(components, language=language)
    if not first["ok"]:
        return {**first, "name": "recommend_temperature_regime"}
    cases = [_regime_case(components, regime, ambient_c, insulation, reactor_volume_l, language)
             for regime in temperature_regimes()["regimes"]]
    chosen, reason = _choose(cases, goal)
    if reason == "deficit" and insulation == "good":
        reason = "deficit_insulated"

    # "What if the reactor had good insulation?" - only when it really changes something.
    what_if = None
    if insulation != "good":
        regime = next(r for r in temperature_regimes()["regimes"] if r["id"] == chosen["id"])
        better = _regime_case(components, regime, ambient_c, "good", reactor_volume_l, language)
        gain = mid(better["net_kwh"]) - mid(chosen["net_kwh"])
        if gain > 0.1 * mid(chosen["gas_heat_kwh"]):
            what_if = {"insulation": "good", "net_kwh": better["net_kwh"], "total_cost_kwh": better["total_cost_kwh"]}

    assumptions = list(first["assumptions"])
    assumptions += cases[1]["_heat"]["assumptions"]
    assumptions.append(t("assume_boiler", language))
    sources = first["sources"] + cases[1]["_heat"]["sources"] + [
        {"id": s["id"], "title": s["title"], "year": s.get("year"), "doi": s.get("doi"), "url": s.get("url")}
        for s in temperature_regimes()["sources"]]
    question = first["question"] or cases[1]["_heat"]["question"]
    rows = [{key: value for key, value in case.items() if not key.startswith("_")} for case in cases]
    data = {"status": "ok", "regimes": rows, "recommended": chosen["id"], "reason": reason, "goal": goal,
            "what_if_good_insulation": what_if, "ambient_c": cases[1]["_heat"]["data"]["ambient_c"],
            "insulation": cases[1]["_heat"]["data"]["insulation"],
            "reactor_volume_l": cases[1]["_heat"]["data"]["reactor_volume_l"]}
    llm = {
        "recommended": f"{chosen['name']} {chosen['setpoint_c']} °C",
        "reason": REASONS[reason].get(language, REASONS[reason]["ru"]),
        "outside_c": data["ambient_c"], "insulation": data["insulation"],
        "regimes": [{
            "regime": f"{case['name']} {case['setpoint_c']} °C", "days": pair(case["days"]),
            "methane_m3": pair(case["methane_m3"]), "heating_cost_kwh": pair(case["total_cost_kwh"]),
            "gas_heat_kwh": pair(case["gas_heat_kwh"]), "net_kwh": pair(case["net_kwh"]),
            "stability": case["stability"],
        } for case in cases],
        "label": "assumption",
        # The methane card keeps the label of the methane data itself (literature / measured),
        # not the weaker label of the heating part.
        "methane_label": first["label"],
    }
    llm["summary"] = SUMMARY.get(language, SUMMARY["ru"]).format(
        regime=llm["recommended"], heating=range_text(pair(chosen["total_cost_kwh"])),
        gas=range_text(pair(chosen["gas_heat_kwh"])), net=range_text(pair(chosen["net_kwh"])),
        days=range_text(pair(chosen["days"])))
    llm["wall"] = chosen["_wall"]  # U, area, UA behind the heat loss (card "heat loss")
    if what_if:
        llm["if_good_insulation_net_kwh"] = pair(what_if["net_kwh"])
    return result("recommend_temperature_regime", ok=True, data=data, llm=llm, assumptions=unique(assumptions),
                  sources=unique_sources(sources), label=weakest([first["label"], "assumption"]), question=question)
