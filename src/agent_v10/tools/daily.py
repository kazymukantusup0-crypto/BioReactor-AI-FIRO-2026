"""Tools for "how much gas PER DAY" and "is the gas enough for a gas stove".

estimate_daily_production — continuous (daily-fed) reactor:
    manure, kg/day      = animals × manure per animal per day      (NRCS AWMFH ch. 4, assumption)
    gas per day         = gas of ONE day's manure over the whole digestion time
                          (steady state: every day one load is added and one load finishes,
                           so the reactor gives per day what one daily load gives in total)
    working volume, L   = manure, kg/day × digestion days            (1 kg of wet manure ≈ 1 L)
    your reactor        = it can take at most working volume / digestion days per day;
                          if that is less than the manure, the gas is limited by the reactor.
    Without animals the remembered batch is spread over its digestion days:
    gas per day = batch gas / days (low = low gas / long time, high = high gas / short time).

gas_stove_hours — one household biogas burner uses 0.20–0.45 m³ of biogas per hour
(GTZ/ISAT Biogas Digest Vol. II):
    hours per day = biogas per day / burner consumption
    (low = low gas / high consumption, high = high gas / low consumption).
"""
from __future__ import annotations

from src.agent_v10.ranges import plain

import json
from functools import lru_cache

from src.agent_v10.config import ROOT, demo_reactor
from src.agent_v10.i18n import t
from src.agent_v10.ranges import fmt, make
from src.agent_v10.tools.common import pair, result, unique, unique_sources
from src.agent_v10.tools.methane import estimate_methane

DAILY_PATH = ROOT / "data" / "research" / "agent_v10_daily.json"


@lru_cache(maxsize=1)
def daily_data() -> dict:
    """Manure per animal per day and burner consumption (data/research/agent_v10_daily.json)."""
    return json.loads(DAILY_PATH.read_text(encoding="utf-8"))


def _sources(*ids: str) -> list[dict]:
    return [s for s in daily_data()["sources"] if s["id"] in ids]


def _animal_text(animals: list[dict], language: str) -> str:
    rows = daily_data()["animals"]
    return ", ".join(f"{plain(a['count'])} × {rows[a['species']]['names'].get(language, rows[a['species']]['names']['ru'])}"
                     for a in animals)


def _batch_per_day(components: list[dict], regime: str, language: str) -> dict:
    """The remembered batch spread over its digestion time."""
    gas = estimate_methane(components, regime=regime, language=language)
    if not gas["ok"]:
        return {**gas, "name": "estimate_daily_production"}
    days = gas["data"]["days"]
    per_day = {key: make(gas["data"][key]["low"] / days["high"], gas["data"][key]["high"] / days["low"])
               for key in ["methane_m3", "biogas_m3", "energy_kwh"]}
    data = {"status": "ok", "basis": "batch", "days": days, "methane_m3_per_day": per_day["methane_m3"],
            "biogas_m3_per_day": per_day["biogas_m3"], "energy_kwh_per_day": per_day["energy_kwh"],
            "reactor_biogas_m3_per_day": per_day["biogas_m3"], "reactor_enough": "yes"}
    llm = {"basis": "the remembered batch spread over its digestion time",
           "biogas_m3_per_day": pair(per_day["biogas_m3"]), "methane_m3_per_day": pair(per_day["methane_m3"]),
           "energy_kwh_per_day": pair(per_day["energy_kwh"]), "days": pair(days),
           "label": gas["label"], "methane_label": gas["label"]}
    assumptions = [t("assume_batch_per_day", language, days=f"{fmt(days['low'])}–{fmt(days['high'])}")] + gas["assumptions"]
    return result("estimate_daily_production", ok=True, data=data, llm=llm, assumptions=assumptions,
                  sources=gas["sources"], label=gas["label"], question=gas["question"])


def estimate_daily_production(animals: list[dict] | None, components: list[dict] | None = None,
                              reactor_volume_l: float | None = None, regime: str = "mesophilic",
                              state: str | None = None, language: str = "ru") -> dict:
    """Biogas per day from the manure of the animals (or from the remembered batch)."""
    table = daily_data()["animals"]
    animals = [a for a in animals or [] if a.get("species") in table and a.get("count")]
    if not animals:
        if components:
            return _batch_per_day(components, regime, language)
        return result("estimate_daily_production", ok=False, data={"status": "needs_animals"},
                      llm={"status": "needs_animals_or_batch"}, question=t("ask_animals", language))

    def components_for(corner: str) -> list[dict]:
        return [{"substrate": table[a["species"]]["substrate"], "amount": a["count"] * table[a["species"]]["manure_kg_per_day"][corner],
                 "unit": "kg", "state": state} for a in animals]

    low_feed, high_feed = components_for("low"), components_for("high")
    gas_low = estimate_methane(low_feed, regime=regime, language=language)
    gas_high = estimate_methane(high_feed, regime=regime, language=language)
    if not gas_low["ok"]:
        return {**gas_low, "name": "estimate_daily_production"}
    manure = make(sum(c["amount"] for c in low_feed), sum(c["amount"] for c in high_feed))
    per_day = {key: make(gas_low["data"][key]["low"], gas_high["data"][key]["high"])
               for key in ["methane_m3", "biogas_m3", "energy_kwh"]}
    days = gas_low["data"]["days"]

    # Reactor: the user's one or the demo reactor (one source for the whole dialog).
    demo = demo_reactor()
    reactor_assumed = not reactor_volume_l
    reactor = float(reactor_volume_l or demo["reactor_volume_l"])
    working = reactor * demo["fill_share"]
    needed_working = make(manure["low"] * days["low"], manure["high"] * days["high"])
    needed_reactor = make(needed_working["low"] / demo["fill_share"], needed_working["high"] / demo["fill_share"])
    max_feed = make(working / days["high"], working / days["low"])
    enough = "yes" if working >= needed_working["high"] else "no" if working < needed_working["low"] else "maybe"
    biogas_per_kg = make(per_day["biogas_m3"]["low"] / manure["low"], per_day["biogas_m3"]["high"] / manure["high"])
    in_reactor = per_day["biogas_m3"] if enough == "yes" else make(
        min(max_feed["low"], manure["low"]) * biogas_per_kg["low"], min(max_feed["high"], manure["high"]) * biogas_per_kg["high"])
    reactor_feed = make(min(max_feed["low"], manure["low"]), min(max_feed["high"], manure["high"]))

    who = _animal_text(animals, language)
    assumptions = [t("assume_manure_per_animal", language, name=table[a["species"]]["names"].get(language, table[a["species"]]["names"]["ru"]),
                     low=f"{plain(table[a['species']]['manure_kg_per_day']['low'])}", high=f"{plain(table[a['species']]['manure_kg_per_day']['high'])}",
                     basis=table[a["species"]]["basis"]) for a in animals]
    assumptions.append(t("assume_continuous", language))
    if reactor_assumed:
        assumptions.append(t("assume_reactor_volume", language, volume=fmt(reactor), working=fmt(working)))
    assumptions += gas_low["assumptions"]

    data = {"status": "ok", "basis": "animals", "animals": animals, "days": days, "manure_kg_per_day": manure,
            "methane_m3_per_day": per_day["methane_m3"], "biogas_m3_per_day": per_day["biogas_m3"],
            "energy_kwh_per_day": per_day["energy_kwh"], "needed_working_volume_l": needed_working,
            "needed_reactor_volume_l": needed_reactor, "reactor_volume_l": reactor, "reactor_working_l": working,
            "reactor_feed_kg_per_day": reactor_feed, "reactor_biogas_m3_per_day": in_reactor,
            "reactor_enough": enough, "reactor_assumed": reactor_assumed}
    llm = {
        "animals": who, "manure_kg_per_day": pair(manure),
        "biogas_m3_per_day_from_all_manure": pair(per_day["biogas_m3"]),
        "methane_m3_per_day_from_all_manure": pair(per_day["methane_m3"]),
        "digestion_days": pair(days),
        "reactor_needed_for_all_manure_m3": pair(make(needed_reactor["low"] / 1000, needed_reactor["high"] / 1000)),
        "your_reactor_l": reactor, "your_reactor_can_take_kg_per_day": pair(reactor_feed),
        "biogas_m3_per_day_in_your_reactor": pair(in_reactor), "your_reactor_is_big_enough": enough,
        "label": "assumption", "methane_label": "assumption",
    }
    return result("estimate_daily_production", ok=True, data=data, llm=llm, assumptions=unique(assumptions),
                  sources=unique_sources(_sources("nrcs-awmfh-ch4-2008") + gas_low["sources"]), label="assumption",
                  question=gas_low["question"])


def gas_stove_hours(daily: dict, language: str = "ru") -> dict:
    """How many hours a day one household burner can run on the gas of one day."""
    if not daily.get("ok"):
        return {**daily, "name": "gas_stove_hours"}
    stove = daily_data()["stove"]
    use = stove["biogas_m3_per_hour"]
    data_daily = daily["data"]

    def hours(biogas: dict) -> dict:
        return make(biogas["low"] / use["high"], biogas["high"] / use["low"])

    all_hours = hours(data_daily["biogas_m3_per_day"])
    reactor_hours = hours(data_daily["reactor_biogas_m3_per_day"])
    limited = data_daily.get("reactor_enough") != "yes"
    data = {"status": "ok", "burner_m3_per_hour": use, "biogas_m3_per_day": data_daily["biogas_m3_per_day"],
            "hours_per_day": all_hours, "reactor_hours_per_day": reactor_hours, "limited_by_reactor": limited,
            "basis": data_daily["basis"], "reactor_volume_l": data_daily.get("reactor_volume_l")}
    llm = {"burner_biogas_m3_per_hour": pair(use), "biogas_m3_per_day": pair(data_daily["biogas_m3_per_day"]),
           "one_burner_hours_per_day": pair(all_hours), "label": "assumption"}
    if limited:
        llm["one_burner_hours_per_day_in_your_reactor"] = pair(reactor_hours)
    assumptions = [t("assume_stove", language, low=fmt(use["low"]), high=fmt(use["high"]))] + daily["assumptions"]
    return result("gas_stove_hours", ok=True, data=data, llm=llm, assumptions=unique(assumptions),
                  sources=unique_sources(_sources("gtz-biogas-digest-2") + daily["sources"]), label="assumption",
                  question=daily["question"])
