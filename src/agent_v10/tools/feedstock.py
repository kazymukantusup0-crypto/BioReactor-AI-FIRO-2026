"""Two questions that the batch calculation alone answered wrongly (manual check 2):

startup_time — "Сколько дней ждать, пока газ пойдёт?"
    Two DIFFERENT times (the agent used to say "the gas starts in ≈30 days"):
      * first gas — start-up (lag) phase: with cattle dung or digested slurry from a working plant
        as inoculum, gas usually comes in 1–2 days (GTZ/ISAT Biogas Digest II, "Starting the plant");
        a stable process takes from several days to several weeks; the first gas is poor (> 60 % CO2);
      * full digestion of the batch — the digestion time of the regime (mesophilic 25–35 days).

compare_feedstocks — "Что лучше: куриный помёт или коровий навоз?"
    Every feed is calculated by estimate_methane for the SAME volume (the remembered batch volume,
    otherwise the working volume of the demo reactor). Python says which gives more methane and by
    how much; the notes on nitrogen/ammonia come from FNR (2007).
"""
from __future__ import annotations

from src.agent_v10 import substrates
from src.agent_v10.config import demo_reactor
from src.agent_v10.i18n import t
from src.agent_v10.ranges import center, make
from src.agent_v10.tools.common import pair, result, unique, unique_sources, weakest
from src.agent_v10.tools.daily import daily_data
from src.agent_v10.tools.methane import estimate_methane, regime_row


def _sources(*ids: str) -> list[dict]:
    return [s for s in daily_data()["sources"] if s["id"] in ids]


def startup_time(components: list[dict], regime: str = "mesophilic", language: str = "ru") -> dict:
    """First gas (start-up) vs full digestion of the batch."""
    data_startup = daily_data()["startup"]
    digestion = regime_row(regime)["digestion_days"]
    substrate = next((c.get("substrate") for c in components if c.get("substrate")), "cattle_manure")
    with_cattle = substrate == "cattle_manure" or any(c.get("substrate") == "cattle_manure" for c in components)
    first = data_startup["first_gas_days"]
    data = {"status": "ok", "first_gas_days": first if with_cattle else None, "full_digestion_days": digestion,
            "with_cattle_dung": with_cattle, "regime": regime}
    llm = {
        "first_gas_days": pair(first) if with_cattle else "several days to several weeks (depends on the inoculum)",
        "first_gas_condition": "cattle dung or digested slurry from a working plant as inoculum",
        "stable_process": "from several days to several weeks",
        "first_gas_quality": "poor: more than 60% CO2, may not burn yet; vent the first two gasholder fillings",
        "full_digestion_days_of_the_batch": pair(digestion),
        "important": "full_digestion_days is NOT the time until the first gas",
        "label": "literature",
    }
    assumptions = [t("assume_startup", language), t("assume_full_digestion", language,
                                                     low=f"{digestion['low']:g}", high=f"{digestion['high']:g}")]
    return result("startup_time", ok=True, data=data, llm=llm, assumptions=assumptions,
                  sources=_sources("gtz-biogas-digest-2-startup"), label="literature")


def compare_feedstocks(materials: list[str], volume_l: float | None = None, regime: str = "mesophilic",
                       language: str = "ru") -> dict:
    """The same volume of 2–3 feeds: methane of each, which is better and by how much."""
    materials = list(dict.fromkeys(m for m in materials if m))[:3]
    if len(materials) < 2:
        return result("compare_feedstocks", ok=False, data={"status": "needs_two_feeds"},
                      llm={"status": "needs_two_feeds"}, question=t("ask_substrate", language))
    volume_assumed = not volume_l
    volume = float(volume_l or demo_reactor()["working_volume_l"])
    rows, assumptions, sources, labels = [], [], [], []
    for material in materials:
        gas = estimate_methane([{"substrate": material, "amount": volume, "unit": "l"}], regime=regime, language=language)
        if not gas["ok"]:
            return {**gas, "name": "compare_feedstocks"}
        rows.append({"substrate": material, "name": substrates.material_name(material, language),
                     "methane_m3": gas["data"]["methane_m3"], "biogas_m3": gas["data"]["biogas_m3"], "label": gas["label"]})
        assumptions += gas["assumptions"]
        sources += gas["sources"]
        labels.append(gas["label"])
    ranked = sorted(rows, key=lambda r: center(pair(r["methane_m3"])), reverse=True)
    best, other = ranked[0], ranked[1]
    ratio = center(pair(best["methane_m3"])) / max(center(pair(other["methane_m3"])), 1e-9)
    overlap = best["methane_m3"]["low"] <= other["methane_m3"]["high"]
    # The same feeds in the one reference table (KTBL 2025, per tonne of fresh mass), shown next to our numbers.
    references = {}
    for row in rows:
        state = substrates.default_state(row["substrate"], "volume") or "fresh_solid"
        reference = substrates.reference_row(row["substrate"], state)
        if reference:
            references[row["substrate"]] = reference["biogas_m3_t_fm"]
    ref_best, ref_other = references.get(best["substrate"]), references.get(other["substrate"])
    # "About the same": our ranges overlap and the reference values differ by less than 25 %.
    similar = overlap and bool(ref_best and ref_other) and max(ref_best, ref_other) / min(ref_best, ref_other) < 1.25
    notes_table = daily_data()["feedstock_notes"]
    notes = {r["substrate"]: notes_table[r["substrate"]].get(language, notes_table[r["substrate"]]["ru"])
             for r in rows if r["substrate"] in notes_table}
    if volume_assumed:
        assumptions.insert(0, t("assume_compare_volume", language, volume=f"{volume:g}"))
    data = {"status": "ok", "volume_l": volume, "volume_assumed": volume_assumed, "feeds": rows, "best": best["substrate"],
            "ratio": ratio, "difference_percent": (ratio - 1) * 100, "ranges_overlap": overlap, "notes": notes,
            "references_m3_t": references, "similar": similar}
    llm = {
        "same_volume_l": volume,
        "feeds": [{"feed": r["name"], "methane_m3": pair(r["methane_m3"]), "biogas_m3": pair(r["biogas_m3"])} for r in rows],
        "more_gas": "about the same" if similar else best["name"], "times_more": round(ratio, 1), "ranges_overlap": overlap,
        "reference_ktbl_2025_biogas_m3_per_t": {substrates.material_name(k, language): v for k, v in references.items()},
        "notes": {substrates.material_name(k, language): v for k, v in notes.items()},
        "label": weakest(labels),
    }
    return result("compare_feedstocks", ok=True, data=data, llm=llm, assumptions=unique(assumptions),
                  sources=unique_sources(sources + _sources("fnr-biogas-einfuehrung-2007")
                                         + (_sources("moller2004") if {"swine_manure", "cattle_manure"} <= set(materials) else [])),
                  label=weakest(labels))
