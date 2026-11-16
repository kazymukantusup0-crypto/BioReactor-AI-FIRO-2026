"""Typical substrate properties for a quick but honest estimate.

Order of priority for every property (density, organic matter VS, BMP):
    1. what the user measured / told us             -> label "measured"
    2. reviewed literature profiles in data/research -> label "literature"
    3. data/research/agent_v10_defaults.json        -> label "assumption"

The reviewed profiles and the material recognition (ru/kk/en synonyms) are
reused from the existing science core: src/advisor/catalog.py and
src/advisor/conversion.py.
"""
from __future__ import annotations

from functools import lru_cache

from src.advisor import catalog
from src.advisor.conversion import document as density_document
from src.agent_v10.config import defaults
from src.agent_v10.ranges import make

LABEL_MEASURED = "measured"
LABEL_LITERATURE = "literature"
LABEL_ASSUMPTION = "assumption"

# Physical states used in density profiles have different names.
STATE_TO_DENSITY_STATE = {
    "slurry": "liquid",
    "prepared_pulp": "liquid",
    "fresh_solid": "solid",
    "bedded": "bedded",
    "dry": "dry",
    "silage": "solid",
}

# Simple words for states, used in assumptions shown to the user.
STATE_NAMES = {
    "ru": {"slurry": "жидкий", "fresh_solid": "свежий твёрдый", "bedded": "с подстилкой", "dry": "сухой",
           "prepared_pulp": "измельчённый в пульпу", "silage": "силос"},
    "en": {"slurry": "liquid slurry", "fresh_solid": "fresh solid", "bedded": "with bedding", "dry": "dry",
           "prepared_pulp": "pulped", "silage": "silage"},
    "kk": {"slurry": "сұйық", "fresh_solid": "жаңа қатты", "bedded": "төсеніші бар", "dry": "құрғақ",
           "prepared_pulp": "ұнтақталған", "silage": "сүрлем"},
}


def material_word(material: str, language: str = "ru") -> str:
    """Name inside a sentence: 'Навоз КРС' -> 'навоз КРС' (abbreviations keep their capitals)."""
    name = material_name(material, language)
    return name[:1].lower() + name[1:] if name[1:2].islower() else name


def material_name(material: str, language: str = "ru") -> str:
    """Human name of a material in ru / en / kk (from the existing catalog)."""
    return catalog.name(material, language)


def recognize(text: str) -> list[dict]:
    """Find substrate names in a free text (ru / kk / en)."""
    return catalog.matches(text)


def known_materials() -> list[str]:
    """All material ids the catalog can recognise."""
    return [row[0] for row in catalog.DEFINITIONS]


def resolve_material(material: str) -> str:
    """Generic 'manure' becomes cattle manure (the most common case, an assumption)."""
    if material == "manure":
        return defaults()["generic_manure_material"]
    return material


def default_state(material: str, family: str) -> str | None:
    """Physical state assumed when the user did not say it."""
    row = defaults()["default_state"].get(material)
    if row is None:
        return None
    return row.get(family) or row.get("mass")


@lru_cache(maxsize=1)
def _profiles() -> list[dict]:
    return catalog.profiles()


def _source_record(source: dict | None) -> dict | None:
    if not source:
        return None
    return {
        "id": source.get("id"),
        "title": source.get("title"),
        "year": source.get("year"),
        "doi": source.get("doi"),
        "url": source.get("url"),
    }


def _profile_matches(profile: dict, material: str, state: str) -> bool:
    if profile["material"] != material:
        return False
    states = profile.get("matching_states") or [profile["material_state"]]
    return state in states or profile["material_state"] == state


def _range_of(value) -> dict | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return make(value["low"], value["high"])
    return make(value, value)


def _handbook_check(material: str, state: str, measured: dict) -> dict | None:
    """Typical handbook yield instead of strongly diluted measured samples.

    Pig slurry in the base: two measured samples with TS 2.2–3.2 % (Pham 2013, Eftaxias 2024)
    give 2.6–4.7 L CH4 per kg — 3.5–7 times less than the FNR handbook value for typical pig
    slurry (28 m³ biogas per tonne of fresh mass × 60–65 % CH4 = 16.8–18.2 L CH4/kg). The samples
    are real but diluted with wash water; for a farmer's slurry the handbook value is the typical one.
    Rule: if the measured high value is below half of the handbook low value, use the handbook value.
    """
    row = defaults().get("handbook_check", {}).get(f"{material}/{state}")
    if not row:
        return None
    share = methane_fraction(material)
    handbook = make(row["biogas_m3_per_t_fm"] * share["low"], row["biogas_m3_per_t_fm"] * share["high"])
    if measured["yield_l_per_kg"]["high"] >= 0.5 * handbook["low"]:
        return None
    ts_values = [v for t in measured["ts_fraction"] if t for v in (t["low"], t["high"])]
    return {
        "vs_fraction_wet": None,
        "bmp_ml_g_vs": measured["bmp_ml_g_vs"],  # still used when the user gives his own TS / VS
        "yield_l_per_kg": handbook,
        "label": LABEL_LITERATURE,
        "profile_ids": [],
        "sources": [_defaults_source(row["source_id"])],
        "handbook": {"biogas_m3_per_t_fm": row["biogas_m3_per_t_fm"], "measured_yield_l_per_kg": measured["yield_l_per_kg"],
                     "measured_ts_percent": [round(min(ts_values) * 100, 1), round(max(ts_values) * 100, 1)] if ts_values else None},
    }


def composition(material: str, state: str) -> dict | None:
    """Organic matter and methane potential of a substrate.

    Returns ranges of:
        vs_fraction_wet  kg of volatile solids per kg of wet material
        bmp_ml_g_vs      laboratory methane potential, mL CH4 per g VS
        yield_l_per_kg   litres of CH4 per kg of WET material (paired per study,
                         so a high VS is not combined with a BMP from another study)
    or None if nothing is known.
    """
    complete = []
    for profile in _profiles():
        if not _profile_matches(profile, material, state):
            continue
        vs = _range_of(profile.get("vs_fraction_wet"))
        bmp = _range_of(profile.get("bmp_ml_g_vs"))
        if vs and bmp:
            complete.append((profile, vs, bmp))
    if complete:
        measured = {
            "vs_fraction_wet": make(min(v["low"] for _, v, _ in complete), max(v["high"] for _, v, _ in complete)),
            "bmp_ml_g_vs": make(min(b["low"] for _, _, b in complete), max(b["high"] for _, _, b in complete)),
            "yield_l_per_kg": make(min(v["low"] * b["low"] for _, v, b in complete),
                                   max(v["high"] * b["high"] for _, v, b in complete)),
            "ts_fraction": [p.get("ts_fraction") for p, _, _ in complete],
        }
        handbook = _handbook_check(material, state, measured)
        if handbook:
            return handbook
        return {
            "vs_fraction_wet": make(min(v["low"] for _, v, _ in complete), max(v["high"] for _, v, _ in complete)),
            "bmp_ml_g_vs": make(min(b["low"] for _, _, b in complete), max(b["high"] for _, _, b in complete)),
            "yield_l_per_kg": make(
                min(v["low"] * b["low"] for _, v, b in complete),
                max(v["high"] * b["high"] for _, v, b in complete),
            ),
            "label": LABEL_LITERATURE,
            "profile_ids": [p["id"] for p, _, _ in complete],
            "sources": [s for s in (_source_record(p.get("source")) for p, _, _ in complete) if s],
        }
    fallback = defaults()["fallback_composition"]
    row = fallback.get(f"{material}/{state}") or fallback.get(material)
    if row is None:
        return None
    vs = make(row["ts_fraction"]["low"] * row["vs_fraction_of_ts"]["low"],
              row["ts_fraction"]["high"] * row["vs_fraction_of_ts"]["high"])
    bmp = make(row["bmp_ml_g_vs"]["low"], row["bmp_ml_g_vs"]["high"])
    return {
        "vs_fraction_wet": vs,
        "bmp_ml_g_vs": bmp,
        "yield_l_per_kg": make(vs["low"] * bmp["low"], vs["high"] * bmp["high"]),
        "label": LABEL_ASSUMPTION,
        "profile_ids": [],
        "sources": [_defaults_source(row["source_id"])],
        "note": row["label"],
    }


def bmp_only(material: str, state: str) -> dict | None:
    """Literature BMP range, used when the user gives his own TS / VS."""
    found = composition(material, state)
    return None if found is None else {**found, "vs_fraction_wet": None, "yield_l_per_kg": None}


def density(material: str, state: str) -> dict:
    """Density in kg/L: density profiles -> study profile -> defaults file."""
    density_state = STATE_TO_DENSITY_STATE.get(state, state)
    document = density_document()
    for row in document["density_profiles"]:
        if row["material"] == material and density_state in row["physical_states"]:
            source = next((s for s in document["sources"] if s["id"] == row["source_id"]), None)
            return {**make(row["value"]["low"], row["value"]["high"]), "label": LABEL_LITERATURE,
                    "sources": [_source_record(source)] if source else []}
    for profile in _profiles():
        if _profile_matches(profile, material, state) and profile.get("density_kg_l"):
            value = _range_of(profile["density_kg_l"])
            return {**value, "label": LABEL_LITERATURE, "sources": [_source_record(profile.get("source"))]}
    row = defaults()["density_kg_l"].get(state) or defaults()["density_kg_l"]["fresh_solid"]
    sources = [_defaults_source(row["source_id"])] if row.get("source_id") else []
    return {**make(row["low"], row["high"]), "label": LABEL_ASSUMPTION, "sources": sources, "note": row["note"]}


def methane_fraction(material: str) -> dict:
    """Share of methane in biogas (literature reference range)."""
    row = defaults()["methane_fraction"].get(material) or defaults()["methane_fraction"]["cattle_manure"]
    return {**make(row["low"], row["high"]), "label": LABEL_LITERATURE,
            "sources": [_defaults_source(row["source_id"])]}


def _defaults_source(source_id: str) -> dict:
    source = next((s for s in defaults()["sources"] if s["id"] == source_id), None)
    if source is None:
        return {"id": source_id, "title": source_id, "year": None, "doi": None, "url": None}
    return {"id": source["id"], "title": source["title"], "year": source.get("year"), "doi": None, "url": source.get("url")}


# --- materials without data: calculate by analogy (data/research/agent_v10_analogs.json) ---

def recognize_analogs(text: str) -> list[dict]:
    """Unknown materials that have a rule 'similar to X': [{material: X, analog_of: words, start, end, rule}]."""
    import re
    from src.agent_v10.config import analogs

    found = []
    for rule in analogs()["rules"]:
        for match in re.finditer(rule["pattern"], text, re.IGNORECASE):
            # Take the whole noun phrase around the hit ("банановой кожуры", "картофельные очистки").
            start, end = match.start(), match.end()
            tail = re.match(r"(?:\s+[а-яёa-zәғқңөұүһі]{3,})?", text[end:], re.IGNORECASE)
            words = text[start:end + (tail.end() if tail else 0)].strip()
            found.append({"material": rule["analog"], "start": start, "end": end + (tail.end() if tail else 0),
                          "text": words, "analog_of": words, "rule": rule["id"]})
    accepted = []
    for item in sorted(found, key=lambda x: x["start"]):
        if not any(item["start"] < x["end"] and item["end"] > x["start"] for x in accepted):
            accepted.append(item)
    return accepted


def analog_for(material: str) -> str | None:
    """Catalog material without reviewed composition -> material with data, or None."""
    from src.agent_v10.config import analogs

    return analogs()["catalog_without_data"].get(material)


def analog_reason(analog_of: str, language: str = "ru") -> str:
    """Why the analogue was chosen, for the assumption text."""
    import re
    from src.agent_v10.config import analogs

    for rule in analogs()["rules"]:
        if re.search(rule["pattern"], analog_of, re.IGNORECASE):
            return rule["why"].get(language, rule["why"]["ru"])
    return {"ru": "похожий материал", "en": "a similar material", "kk": "ұқсас материал"}.get(language, "похожий материал")
