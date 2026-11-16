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

import re
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


# Words the shared catalog (src/advisor/catalog.py, also used by v9) does not know, v10 only (manual check 3):
# an animal adjective without the word "навоз" ("Что лучше: свиной или коровий?") and farmer typos ("навозу каровы").
EXTRA_NAMES = [
    ("cattle_manure", r"кар[оа]в\w*|\bкрс\b|\bсиыр\w*|\bcows?\b|\bcattle\b"),
    ("swine_manure", r"свин(?:ой|ая|ое|ого|ому|ую|ым|ые|ых|ыми)\b|свиньи|свиней|\bшошқа\w*|\bpigs?\b|\bswine\b|\bhogs?\b"),
    ("poultry_manure", r"курин\w*|птич\w*|\bтауық\w*(?:\s+саңғыры\w*)?|\bchickens?\b|\bpoultry\b|\bhens?\b"),
]


def recognize(text: str) -> list[dict]:
    """Find substrate names in a free text (ru / kk / en).

    A name must start a word: the catalog pattern "трав…" also matched inside "стравить"
    (vent the gas) and made the answer check think the text named grass.
    "навоз" + an animal word next to it ("навозу каровы", "свиной навоз") is ONE material of that animal.
    """
    found = [m for m in catalog.matches(text) if m["start"] == 0 or not text[m["start"] - 1].isalpha()]
    for material, pattern in EXTRA_NAMES:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            if match.start() and text[match.start() - 1].isalpha():
                continue
            if any(match.start() < m["end"] and match.end() > m["start"] and m["material"] != "manure" for m in found):
                continue
            extra = {"material": material, "start": match.start(), "end": match.end(), "text": match.group()}
            # A generic "навоз" right before or after the animal word becomes part of this material.
            for generic in [m for m in found if m["material"] == "manure"]:
                gap = text[min(generic["end"], extra["end"]):max(generic["start"], extra["start"])]
                if (generic["start"] < extra["end"] and generic["end"] > extra["start"]) or (len(gap) <= 3 and not gap.strip()):
                    found.remove(generic)
                    extra.update(start=min(extra["start"], generic["start"]), end=max(extra["end"], generic["end"]))
                    extra["text"] = text[extra["start"]:extra["end"]]
            found.append(extra)
    return sorted(found, key=lambda m: m["start"])


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


# Mesophilic share of the laboratory potential reached in a reactor (temperature_regimes.json): used to put a
# laboratory profile and a practical handbook yield on the same footing.
def _meso_share() -> dict:
    from src.agent_v10.config import temperature_regimes
    row = next(r for r in temperature_regimes()["regimes"] if r["id"] == "mesophilic")
    return row["share_of_bmp"]


@lru_cache(maxsize=1)
def reference_table() -> dict:
    """KTBL 2025 practical biogas yields (data/research/ktbl_2025_yields.json) — one reference for all feeds."""
    import json
    from src.agent_v10.config import ROOT
    return json.loads((ROOT / "data" / "research" / "ktbl_2025_yields.json").read_text(encoding="utf-8"))


def reference_row(material: str, state: str) -> dict | None:
    """The KTBL row that directly matches a material and state (None if there is none)."""
    return next((r for r in reference_table()["rows"]
                 if r["material"] == material and r["state"] == state and r["match"] == "direct"), None)


def reference_ch4_l_per_kg(row: dict) -> float:
    """Practical methane yield of the reference, L CH4 per kg fresh mass."""
    return row["biogas_m3_t_fm"] * row["methane_percent"] / 100


def practice_equivalent(found: dict) -> dict:
    """L CH4 per kg in a mesophilic reactor: a lab yield × 75–90 %; a practical yield as it is."""
    if found.get("basis") == "practice":
        return found["yield_l_per_kg"]
    share = _meso_share()
    return make(found["yield_l_per_kg"]["low"] * share["low"], found["yield_l_per_kg"]["high"] * share["high"])


def _reference_check(material: str, state: str, found: dict) -> dict:
    """Sanity check against KTBL 2025: a profile far from the practical reference is replaced by it.

    Our mesophilic yield must overlap the reference ±30 %. Otherwise (e.g. pig slurry samples diluted
    with wash water, TS 2.2–3.2 %) the reference value ±15 % is used as a PRACTICAL yield (basis
    "practice": the regime share is not applied again) and the measured samples are shown to the user.
    """
    row = reference_row(material, state)
    if row is None or found.get("basis") == "practice":
        return found
    table = reference_table()
    reference = reference_ch4_l_per_kg(row)
    ours = practice_equivalent(found)
    corridor = make(reference * (1 - table["corridor_share"]), reference * (1 + table["corridor_share"]))
    if ours["high"] >= corridor["low"] and ours["low"] <= corridor["high"]:
        return found
    spread = table["practice_spread_share"]
    return {
        "vs_fraction_wet": None,
        "bmp_ml_g_vs": found.get("bmp_ml_g_vs"),  # still used when the user gives his own TS / VS
        "yield_l_per_kg": make(reference * (1 - spread), reference * (1 + spread)),
        "basis": "practice",
        "label": LABEL_LITERATURE,
        "profile_ids": [],
        "sources": [table["source"]],
        "reference": {"name": row["reference"], "biogas_m3_t_fm": row["biogas_m3_t_fm"],
                      "methane_percent": row["methane_percent"], "replaced_practice_l_per_kg": ours,
                      "replaced_profiles": found.get("profile_ids") or [],
                      "replaced_ts_percent": found.get("ts_percent")},
    }


def composition(material: str, state: str) -> dict | None:
    """Organic matter and methane potential of a substrate, checked against the KTBL 2025 reference.

    Returns ranges of:
        vs_fraction_wet  kg of volatile solids per kg of wet material (None for a practical reference yield)
        bmp_ml_g_vs      laboratory methane potential, mL CH4 per g VS
        yield_l_per_kg   litres of CH4 per kg of WET material (paired per study,
                         so a high VS is not combined with a BMP from another study)
        basis            "lab" (laboratory potential, the regime share is applied later) or
                         "practice" (yield of working plants: no regime share for the mesophilic regime)
    or None if nothing is known.
    """
    found = _raw_composition(material, state)
    if found is None:
        # No profile at all (e.g. solid cattle manure), but KTBL has the feed: use the reference.
        row = reference_row(material, state)
        if row is None:
            return None
        found = {"yield_l_per_kg": make(0.0, 0.0), "basis": "lab", "profile_ids": [], "vs_fraction_wet": None,
                 "bmp_ml_g_vs": None}
    return _reference_check(material, state, found)


def _raw_composition(material: str, state: str) -> dict | None:
    complete = []
    for profile in _profiles():
        if not _profile_matches(profile, material, state):
            continue
        vs = _range_of(profile.get("vs_fraction_wet"))
        bmp = _range_of(profile.get("bmp_ml_g_vs"))
        if vs and bmp:
            complete.append((profile, vs, bmp))
    if complete:
        ts_values = [v for p, _, _ in complete if p.get("ts_fraction") for v in (p["ts_fraction"]["low"], p["ts_fraction"]["high"])]
        return {
            "vs_fraction_wet": make(min(v["low"] for _, v, _ in complete), max(v["high"] for _, v, _ in complete)),
            "bmp_ml_g_vs": make(min(b["low"] for _, _, b in complete), max(b["high"] for _, _, b in complete)),
            "yield_l_per_kg": make(
                min(v["low"] * b["low"] for _, v, b in complete),
                max(v["high"] * b["high"] for _, v, b in complete),
            ),
            "basis": "lab",
            "label": LABEL_LITERATURE,
            "profile_ids": [p["id"] for p, _, _ in complete],
            "sources": [s for s in (_source_record(p.get("source")) for p, _, _ in complete) if s],
            "ts_percent": [round(min(ts_values) * 100, 1), round(max(ts_values) * 100, 1)] if ts_values else None,
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
        "basis": "lab",
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
