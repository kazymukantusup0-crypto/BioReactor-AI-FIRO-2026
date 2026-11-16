"""Tool estimate_methane: how much methane, biogas and energy a batch gives.

Formula (per component, all values are low–high ranges):

    wet mass, kg        = volume, L × density, kg/L        (or the mass itself)
    CH4 potential, L    = wet mass × VS share × BMP        (= wet mass × yield, L/kg)
    CH4 in reactor, m³  = CH4 potential / 1000 × share of BMP reached in the regime
    biogas, m³          = CH4 / methane share in biogas
    energy, kWh         = CH4, m³ × 9.97 kWh/m³            (FNR lower heating value)

BMP is a laboratory potential, so the expected reactor output also depends on
the temperature regime and digestion time (data/research/temperature_regimes.json).
"""
from __future__ import annotations

from src.agent_v10 import substrates
from src.agent_v10.config import METHANE_KWH_PER_M3, temperature_regimes
from src.agent_v10.i18n import t
from src.agent_v10.ranges import add, divide, fmt, make, multiply, point, scale
from src.agent_v10.tools.common import pair, result, unique_sources, weakest
from src.agent_v10.units import normalize_unit, to_base

DEFAULT_REGIME = "mesophilic"


def regime_row(regime_id: str) -> dict:
    """One row of the temperature regime table."""
    for row in temperature_regimes()["regimes"]:
        if row["id"] == regime_id:
            return row
    raise ValueError(f"Unknown regime: {regime_id}")


def normalize_substrate(name: str | None) -> str | None:
    """Accept an id ('cattle_manure') or free words ('коровий навоз', 'cow manure')."""
    if not name:
        return None
    if name in substrates.known_materials():
        return substrates.resolve_material(name)
    matches = substrates.recognize(name)
    if matches:
        return substrates.resolve_material(matches[0]["material"])
    cleaned = name.strip().lower().replace(" ", "_")
    if cleaned in substrates.known_materials():
        return substrates.resolve_material(cleaned)
    return None


# Words the LLM may use for physical states -> our state ids.
STATE_ALIASES = {
    "slurry": "slurry", "liquid": "slurry", "wet": "slurry", "жидкий": "slurry",
    "fresh_solid": "fresh_solid", "solid": "fresh_solid", "fresh": "fresh_solid", "твердый": "fresh_solid",
    "bedded": "bedded", "bedding": "bedded", "dry": "dry", "silage": "silage", "prepared_pulp": "prepared_pulp",
}


def normalize_state(state: str | None) -> str | None:
    """'liquid' -> 'slurry'; unknown words -> None (then a default state is assumed)."""
    if not state:
        return None
    return STATE_ALIASES.get(str(state).strip().lower())


def normalize_component(raw: dict) -> dict:
    """Make one component dict uniform; raises ValueError with a clear message."""
    substrate = normalize_substrate(raw.get("substrate"))
    if substrate is None:
        raise ValueError(f"unknown substrate: {raw.get('substrate')}")
    amount = raw.get("amount")
    unit = raw.get("unit") or raw.get("base_unit")
    if amount is None or unit is None or normalize_unit(str(unit)) is None:
        return {"substrate": substrate, "state": normalize_state(raw.get("state")), "amount": None}
    base = to_base(float(amount), str(unit))
    return {
        "substrate": substrate,
        "state": normalize_state(raw.get("state")),
        "amount": float(amount),
        "unit": str(unit),
        "family": base["family"],
        "value": base["value"],
        "unit_assumption": base["assumption"],
        "density_kg_l": raw.get("density_kg_l"),
        "ts_percent": raw.get("ts_percent"),
        "vs_percent_of_ts": raw.get("vs_percent_of_ts"),
        "analog_of": raw.get("analog_of"),
    }


def component_mass(component: dict, language: str = "ru") -> dict:
    """Wet mass range of one component + labels and assumptions."""
    substrate = component["substrate"]
    family = component["family"]
    assumptions, labels, sources = [], [], []
    state = component.get("state")
    state_assumed = False
    if not state:
        state = substrates.default_state(substrate, family) or "fresh_solid"
        state_assumed = True
        assumptions.append(t("assume_state", language, substrate=substrates.material_name(substrate, language),
                             state=substrates.STATE_NAMES[language if language in substrates.STATE_NAMES else "ru"].get(state, state)))
    if component.get("unit_assumption"):
        assumptions.append(t("assume_bag" if "меш" in component["unit_assumption"] else "assume_bucket", language))
    if family == "mass":
        mass = point(component["value"])
        labels.append("measured")
        density_assumed = False
    elif component.get("density_kg_l"):
        mass = scale(point(component["value"]), float(component["density_kg_l"]))
        labels.append("measured")
        density_assumed = False
    else:
        density = substrates.density(substrate, state)
        mass = multiply(point(component["value"]), density)
        labels.append(density["label"])
        sources += density["sources"]
        density_assumed = True
        value_text = f"{density['low']:g}" if density["low"] == density["high"] else f"{density['low']:g}–{density['high']:g}"
        assumptions.append(t("assume_density", language, substrate=substrates.material_name(substrate, language),
                             value=value_text, label=t("badge_" + density["label"], language)))
    return {"mass_kg": mass, "state": state, "state_assumed": state_assumed, "density_assumed": density_assumed,
            "labels": labels, "assumptions": assumptions, "sources": sources}


def component_potential(component: dict, state: str, language: str = "ru") -> dict | None:
    """Methane yield, litres CH4 per kg wet material, for one component."""
    substrate = component["substrate"]
    ts, vs = component.get("ts_percent"), component.get("vs_percent_of_ts")
    if ts and vs:
        bmp = substrates.bmp_only(substrate, state)
        if bmp is None:
            return None
        vs_wet = point(float(ts) / 100 * float(vs) / 100)
        return {"yield_l_per_kg": multiply(vs_wet, bmp["bmp_ml_g_vs"]), "vs_fraction_wet": vs_wet,
                "bmp_ml_g_vs": bmp["bmp_ml_g_vs"], "labels": ["measured", bmp["label"]], "sources": bmp["sources"],
                "assumptions": [t("assume_bmp", language, substrate=substrates.material_name(substrate, language),
                                  label=t("label_" + bmp["label"], language))]}
    found = substrates.composition(substrate, state)
    if found is None:
        return None
    assumptions = [t("assume_composition", language, substrate=substrates.material_name(substrate, language),
                     label=t("label_" + found["label"], language))]
    labels = [found["label"]]
    if found.get("reference"):
        ref = found["reference"]
        replaced = ref["replaced_practice_l_per_kg"]
        key = ("assume_reference_none" if not ref.get("replaced_profiles") and replaced["high"] == 0 else
               "assume_reference_ts" if ref.get("replaced_ts_percent") else "assume_reference")
        assumptions = [t(key, language, substrate=substrates.material_name(substrate, language),
                         ts="–".join(dict.fromkeys(f"{v:g}" for v in ref["replaced_ts_percent"] or [])),
                         m_low=f"{replaced['low']:.1f}", m_high=f"{replaced['high']:.1f}", name=ref["name"],
                         biogas=f"{ref['biogas_m3_t_fm']:g}", percent=f"{ref['methane_percent']:g}",
                         low=f"{found['yield_l_per_kg']['low']:.1f}", high=f"{found['yield_l_per_kg']['high']:.1f}")]
    if component.get("analog_of"):
        # No data for the real material: the analogue's composition, always a rough assumption.
        assumptions.insert(0, t("assume_analog", language, name=component["analog_of"],
                                analog=substrates.material_name(substrate, language),
                                why=substrates.analog_reason(component["analog_of"], language)))
        labels = ["assumption"]
    return {"yield_l_per_kg": found["yield_l_per_kg"], "vs_fraction_wet": found["vs_fraction_wet"],
            "basis": found.get("basis", "lab"),
            "bmp_ml_g_vs": found["bmp_ml_g_vs"], "labels": labels, "sources": found["sources"],
            "profile_ids": found["profile_ids"], "assumptions": assumptions}


def estimate_methane(components: list[dict], regime: str = DEFAULT_REGIME, days: float | None = None,
                     language: str = "ru") -> dict:
    """Methane, biogas and energy of a batch (one substrate or a mixture)."""
    if not components:
        return result("estimate_methane", ok=False, data={"status": "needs_substrate"},
                      llm={"status": "needs_substrate"}, question=t("ask_substrate", language))
    unknown = next((c for c in components if not c.get("substrate") and c.get("unknown_name")), None)
    if unknown is not None:
        # Honest answer: no data and no close analogue -> no numbers.
        name = unknown["unknown_name"]
        return result("estimate_methane", ok=False, data={"status": "no_data", "substrate": name},
                      llm={"status": "no_data", "substrate": name, "message": t("no_data", language, name=name)},
                      question=t("ask_composition", language, name=name))
    regime_data = regime_row(regime)
    rows, assumptions, labels, sources = [], [], [], []
    question = None
    potential_l = point(0.0)
    methane_total = point(0.0)
    biogas = point(0.0)
    meso = regime_row("mesophilic")["share_of_bmp"]
    any_lab = False
    mass_total = point(0.0)
    fractions = []
    for raw in components:
        component = normalize_component(raw)
        name = substrates.material_name(component["substrate"], language)
        if component.get("amount") is None:
            return result("estimate_methane", ok=False, data={"status": "needs_amount", "substrate": component["substrate"]},
                          llm={"status": "needs_amount", "substrate": name},
                          question=t("ask_amount", language, substrate=name))
        mass = component_mass(component, language)
        potential = component_potential(component, mass["state"], language)
        if potential is None:
            return result("estimate_methane", ok=False, data={"status": "no_data", "substrate": component["substrate"]},
                          llm={"status": "no_data", "substrate": name, "message": t("no_data", language, name=name)},
                          question=t("ask_composition", language, name=name))
        litres = multiply(mass["mass_kg"], potential["yield_l_per_kg"])
        fraction = substrates.methane_fraction(component["substrate"])
        fractions.append(fraction)
        if potential.get("basis") == "practice":
            # A practical yield of working (mesophilic) plants: the regime share is NOT applied again;
            # other regimes scale by their share relative to the mesophilic one.
            factor = make(regime_data["share_of_bmp"]["low"] / meso["low"], regime_data["share_of_bmp"]["high"] / meso["high"])
            expected_m3 = multiply(scale(litres, 0.001), factor)
            lab_litres = scale(litres, 1 / ((meso["low"] + meso["high"]) / 2))  # rough laboratory equivalent
        else:
            expected_m3 = multiply(scale(litres, 0.001), regime_data["share_of_bmp"])
            lab_litres = litres
            any_lab = True
        component_biogas = divide(expected_m3, fraction)
        potential_l = add(potential_l, lab_litres)
        methane_total = add(methane_total, expected_m3)
        biogas = add(biogas, component_biogas)
        mass_total = add(mass_total, mass["mass_kg"])
        labels += mass["labels"] + potential["labels"]
        sources += mass["sources"] + potential["sources"] + fraction["sources"]
        assumptions += mass["assumptions"] + potential["assumptions"]
        if question is None and mass["state_assumed"] and component["substrate"].endswith("manure"):
            question = t("ask_state", language)
        elif question is None and mass["density_assumed"]:
            question = t("ask_mass", language)
        rows.append({
            "substrate": component["substrate"], "name": name, "state": mass["state"],
            "amount": component["amount"], "unit": component["unit"],
            "wet_mass_kg": mass["mass_kg"], "vs_fraction_wet": potential["vs_fraction_wet"],
            "bmp_ml_g_vs": potential["bmp_ml_g_vs"], "yield_l_ch4_per_kg": potential["yield_l_per_kg"],
            "methane_potential_m3": scale(litres, 0.001), "methane_m3": expected_m3, "biogas_m3": component_biogas,
            "methane_share": make(fraction["low"], fraction["high"]), "label": weakest(mass["labels"] + potential["labels"]),
            "analog_of": component.get("analog_of"),
        })

    potential_m3 = scale(potential_l, 0.001)
    methane_m3 = methane_total
    energy_kwh = scale(methane_m3, METHANE_KWH_PER_M3)
    digestion_days = point(float(days)) if days else regime_data["digestion_days"]
    share = regime_data["share_of_bmp"]
    regime_name = regime_data["name"].get(language, regime_data["name"]["ru"])
    if any_lab:  # a laboratory potential -> the share reached in the reactor (not for practical reference yields)
        assumptions.append(t("assume_regime_share", language, days_low=fmt(digestion_days["low"]),
                             days_high=fmt(digestion_days["high"]), regime=f"{regime_name}, {regime_data['setpoint_c']} °C",
                             share_low=round(share["low"] * 100), share_high=round(share["high"] * 100)))
    ch4_low = min(f["low"] for f in fractions)
    ch4_high = max(f["high"] for f in fractions)
    assumptions.append(t("assume_ch4_share", language, low=round(ch4_low * 100), high=round(ch4_high * 100)))
    label = weakest(labels)

    data = {
        "status": "ok", "components": rows, "regime": regime, "regime_name": regime_name,
        "temperature_c": regime_data["setpoint_c"], "days": digestion_days,
        "wet_mass_kg": mass_total, "methane_potential_m3": potential_m3, "methane_m3": methane_m3,
        "biogas_m3": biogas, "energy_kwh": energy_kwh, "methane_share": make(ch4_low, ch4_high),
        "share_of_bmp": share, "label": label,
        "formulas": [
            "масса = объём × плотность",
            "CH4 (потенциал), л = масса × VS × BMP",
            "CH4 в реакторе = потенциал × доля, достигаемая в режиме",
            "биогаз = CH4 / доля CH4 в биогазе",
            "энергия, кВт·ч = CH4, м³ × 9.97",
        ],
    }
    llm = {
        "methane_m3": pair(methane_m3),
        "biogas_m3": pair(biogas),
        "energy_kwh": pair(energy_kwh),
        "lab_potential_methane_m3": pair(potential_m3),
        "wet_mass_kg": pair(mass_total),
        "regime": f"{regime_name} {regime_data['setpoint_c']} °C",
        "days": pair(digestion_days),
        "days_meaning": "time to digest the WHOLE batch, NOT the time until the first gas (first gas: 1-2 days with inoculum)",
        "label": label,
        "components": [f"{row['name']} {fmt(row['amount'])} {row['unit']}" for row in rows],
    }
    analog_rows = [row for row in rows if row.get("analog_of")]
    if analog_rows:
        # The LLM must say "по аналогии": there is no data for the real material.
        llm["by_analogy"] = [f"no data for '{row['analog_of']}', calculated by analogy with '{row['name']}'"
                             for row in analog_rows]
    return result("estimate_methane", ok=True, data=data, llm=llm, assumptions=assumptions,
                  sources=unique_sources(sources), label=label, question=question)


def batch_mass_and_volume(components: list[dict], language: str = "ru") -> dict | None:
    """Wet mass range and an approximate volume of the whole batch (for heating)."""
    if not components:
        return None
    mass_total = point(0.0)
    volume_total = 0.0
    for raw in components:
        component = normalize_component(raw)
        if component.get("amount") is None:
            return None
        mass = component_mass(component, language)
        mass_total = add(mass_total, mass["mass_kg"])
        if component["family"] == "volume":
            volume_total += component["value"]
        else:
            volume_total += component["value"]  # ~1 kg per litre for wet feed
    return {"mass_kg": mass_total, "volume_l": volume_total}
