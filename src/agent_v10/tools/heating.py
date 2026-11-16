"""Tool estimate_heating_energy: electricity/heat needed to keep the reactor warm.

Physics is reused from src/optimizer/energy_model.py (estimate_energy):
    heating the feed, kWh  = mass × cp × (T_target − T_feed) / 3600 / efficiency
    heat losses, kWh       = UA × (T_target − T_outside) × days × 24 / 1000 / efficiency
    mixing, kWh            = power × hours per day × days / 1000

What is new here is how UA (W/K) is estimated when nobody measured it:
    * the reactor is a cylinder with height = diameter:
          D = (4 V / π)^(1/3),   surface A = π D H + 2 π D² / 4 = 1.5 π D²
    * U (W/m²K) of the wall: outside air film + plastic wall + insulation layer
          U = 1 / (1 / h_outside + d_wall / λ_wall + d_insulation / λ_insulation)
      h_outside = 6–12 W/m²K: still air ... light wind, convection 2–7 plus long-wave
          radiation 4εσT³ ≈ 4.4 W/m²K at +5 °C (ISO 6946 uses 25 = design wind 4 m/s,
          so 6–12 is NOT an overstatement for a sheltered barrel);
      plastic wall (HDPE barrel) 3–5 mm, λ = 0.29–0.48 W/mK;
      insulation λ = 0.035–0.040 W/mK (EPS foam / mineral wool).
      The liquid film inside (h > 100 W/m²K) adds < 1 % and is left out.
    Bare barrel: U = 5.4–11.2;  EPS 50 mm: U = 0.62–0.75 W/m²K (see U_SOURCES).
"""
from __future__ import annotations

import math

from src.agent_v10.config import demo_reactor
from src.agent_v10.i18n import t
from src.agent_v10.ranges import add, fmt, make, point, scale
from src.agent_v10.tools.common import pair, result
from src.optimizer.energy_model import SOURCES as ENERGY_SOURCES, estimate_energy

# Outside air film coefficient, W/(m²·K): still air ... light wind.
H_OUTSIDE = (6.0, 12.0)
# Thermal conductivity of foam / mineral wool, W/(m·K).
LAMBDA_INSULATION = (0.035, 0.040)
# Plastic wall of the barrel (HDPE): thickness, m, and conductivity, W/(m·K).
WALL_THICKNESS = (0.003, 0.005)
LAMBDA_WALL = (0.29, 0.48)
# Insulation thickness, m.
# "eps50" = expanded polystyrene 50 mm: the concrete advice the agent gives for a cold barrel.
INSULATION_THICKNESS = {"none": (0.0, 0.0), "basic": (0.03, 0.05), "good": (0.10, 0.15), "eps50": (0.05, 0.05)}

HEAT_CAPACITY_KJ_KG_K = (4.0, 4.18)   # wet feed is mostly water
HEATER_EFFICIENCY = (0.95, 1.0)       # electric heater
DEFAULT_MIXING_W = 100.0
DEFAULT_MIXING_HOURS = 2.0
# Reactor volume, insulation, outside temperature, days and fill share of the
# demo reactor come from data/config/demo_reactor.json (see config.demo_reactor).
MIN_FEED_TEMPERATURE_C = 5.0          # manure is usually stored above freezing

SOURCES = [{"id": f"energy_model_{index}", "title": source["title"], "year": source.get("year"), "doi": None,
            "url": source.get("url")} for index, source in enumerate(ENERGY_SOURCES)]


# Where the U values come from (shown in the answer next to the heat-loss card).
U_SOURCES = [
    {"id": "iso_6946", "title": "ISO 6946:2017 Building components — Thermal resistance and transmittance, "
     "Annex C: external surface resistance Rse = 0.04 m²·K/W (h ≈ 25 W/m²K at wind 4 m/s)", "year": 2017,
     "doi": None, "url": None},
    {"id": "hdpe_lambda", "title": "MatWeb: HDPE, injection molded — thermal conductivity 0.288–0.480 W/m·K",
     "year": None, "doi": None, "url": "https://www.matweb.com/"},
    {"id": "eps_lambda", "title": "EN 13163: expanded polystyrene (EPS) — declared λ 0.031–0.040 W/m·K",
     "year": 2012, "doi": None, "url": None},
]


def cylinder(volume_l: float) -> dict:
    """Diameter and outer surface of a cylinder with height = diameter."""
    volume_m3 = volume_l / 1000.0
    diameter = (4.0 * volume_m3 / math.pi) ** (1.0 / 3.0)
    area = 1.5 * math.pi * diameter ** 2
    return {"diameter_m": diameter, "height_m": diameter, "area_m2": area}


def u_value(insulation: str) -> dict:
    """Range of the wall heat transfer coefficient U, W/(m²·K)."""
    thin, thick = INSULATION_THICKNESS[insulation]
    low = 1.0 / (1.0 / H_OUTSIDE[0] + WALL_THICKNESS[1] / LAMBDA_WALL[0] + thick / LAMBDA_INSULATION[0])
    high = 1.0 / (1.0 / H_OUTSIDE[1] + WALL_THICKNESS[0] / LAMBDA_WALL[1] + thin / LAMBDA_INSULATION[1])
    return make(low, high)


def wall_info(geometry: dict, insulation: str, loss_kwh: dict, delta_t: float) -> dict:
    """Everything behind the heat loss, for the card: area, U (this case, bare, EPS 50 mm), UA."""
    u = u_value(insulation)
    return {"insulation": insulation, "area_m2": round(geometry["area_m2"], 2),
            "u_w_m2k": [round(u["low"], 2), round(u["high"], 2)],
            "u_none_w_m2k": [round(v, 2) for v in (u_value("none")["low"], u_value("none")["high"])],
            "u_eps50_w_m2k": [round(v, 2) for v in (u_value("eps50")["low"], u_value("eps50")["high"])],
            "ua_w_k": [round(u["low"] * geometry["area_m2"], 1), round(u["high"] * geometry["area_m2"], 1)],
            "delta_t_k": round(delta_t, 1), "heat_loss_kwh": pair(loss_kwh)}


def _energy(mass_kg: float, cp: float, ua: float, efficiency: float, target_c: float, feed_c: float,
            ambient_c: float, days: float, mixing_w: float, mixing_hours: float) -> dict:
    """One corner of the range, calculated by the existing energy worksheet."""
    return estimate_energy({
        "temperature_c": target_c,
        "initial_temperature_c": min(feed_c, target_c),
        "ambient_temperature_c": min(ambient_c, target_c),
        "heated_mass_kg": mass_kg,
        "heat_capacity_kj_kg_k": cp,
        "heat_loss_coefficient_w_k": ua,
        "heater_efficiency": efficiency,
        "duration_days": days,
        "auxiliary_power_w": mixing_w,
        "auxiliary_duty_fraction": mixing_hours / 24.0,
        "energy_scope": "entire_batch",
    })


def estimate_heating_energy(feed_mass_kg: dict | float | None = None, feed_volume_l: float | None = None,
                            reactor_volume_l: float | None = None, insulation: str | None = None,
                            ambient_c: float | None = None, target_c: float = 37.0, days: float | None = None,
                            feed_initial_c: float | None = None, mixing_power_w: float | None = None,
                            mixing_hours_per_day: float | None = None, language: str = "ru") -> dict:
    """Energy for heating the feed, covering heat losses and mixing during digestion."""
    assumptions: list[str] = []
    question = None
    if feed_mass_kg is None and feed_volume_l is None and reactor_volume_l is None:
        return result("estimate_heating_energy", ok=False, data={"status": "needs_batch"},
                      llm={"status": "needs_batch_or_reactor_volume"}, question=t("ask_substrate", language))
    if isinstance(feed_mass_kg, (int, float)):
        feed_mass_kg = point(float(feed_mass_kg))
    demo = demo_reactor()
    fill_share = demo["fill_share"]
    if feed_mass_kg is None:
        # Only the reactor is known: assume it is filled like the demo reactor with water-like feed.
        feed_mass_kg = point((feed_volume_l or reactor_volume_l * fill_share) * 1.0)
    if reactor_volume_l is None:
        # ONE source of reactor parameters for the whole dialog: the demo reactor
        # (data/config/demo_reactor.json). A reactor "sized for the feed" (e.g. 250 L)
        # made two answers of one dialog disagree.
        reactor_volume_l = float(demo["reactor_volume_l"])
        assumptions.append(t("assume_reactor_volume", language, volume=fmt(reactor_volume_l),
                             working=fmt(demo["working_volume_l"])))
        question = t("ask_reactor", language)
    if insulation not in INSULATION_THICKNESS:
        insulation = demo["insulation"]
        assumptions.append(t("assume_insulation", language, level=t("insulation_" + insulation, language)))
        question = question or t("ask_reactor", language)
    if ambient_c is None:
        ambient_c = float(demo["ambient_c"])
        assumptions.append(t("assume_ambient", language, value=fmt(ambient_c)))
        question = question or t("ask_ambient", language)
    if days is None:
        days = float(demo["days"])
        assumptions.append(t("assume_days", language, days=fmt(days)))
    if feed_initial_c is None:
        feed_initial_c = max(ambient_c, MIN_FEED_TEMPERATURE_C)
        assumptions.append(t("assume_feed_temperature", language, value=fmt(feed_initial_c)))
    mixing_w = DEFAULT_MIXING_W if mixing_power_w is None else float(mixing_power_w)
    mixing_hours = DEFAULT_MIXING_HOURS if mixing_hours_per_day is None else float(mixing_hours_per_day)
    if mixing_power_w is None or mixing_hours_per_day is None:
        assumptions.append(t("assume_mixing", language, power=fmt(mixing_w), hours=fmt(mixing_hours)))

    geometry = cylinder(reactor_volume_l)
    u = u_value(insulation)
    ua = scale(u, geometry["area_m2"])
    assumptions.append(t("assume_geometry", language, diameter=f"{geometry['diameter_m']:.2f}",
                         area=f"{geometry['area_m2']:.1f}"))
    assumptions.append(t("assume_u_value", language, low=f"{u['low']:.2f}", high=f"{u['high']:.2f}",
                         level=t("insulation_" + insulation, language)))

    low = _energy(feed_mass_kg["low"], HEAT_CAPACITY_KJ_KG_K[0], ua["low"], HEATER_EFFICIENCY[1],
                  target_c, feed_initial_c, ambient_c, days, mixing_w, mixing_hours)
    high = _energy(feed_mass_kg["high"], HEAT_CAPACITY_KJ_KG_K[1], ua["high"], HEATER_EFFICIENCY[0],
                   target_c, feed_initial_c, ambient_c, days, mixing_w, mixing_hours)
    feed_kwh = make(low["initial_heating_kwh"], high["initial_heating_kwh"])
    loss_kwh = make(low["maintenance_heating_kwh"], high["maintenance_heating_kwh"])
    mixing_kwh = make(low["auxiliary_kwh"], high["auxiliary_kwh"])
    heating_kwh = add(feed_kwh, loss_kwh)
    total_kwh = add(heating_kwh, mixing_kwh)
    delta_outside = max(0.0, target_c - ambient_c)
    loss_power_w = scale(ua, delta_outside)

    data = {
        "status": "ok", "target_c": target_c, "ambient_c": ambient_c, "days": days, "insulation": insulation,
        "reactor_volume_l": reactor_volume_l, "feed_mass_kg": feed_mass_kg, "feed_initial_c": feed_initial_c,
        "geometry": geometry, "u_w_m2k": u, "ua_w_k": ua, "heat_loss_power_w": loss_power_w,
        "feed_heating_kwh": feed_kwh, "heat_loss_kwh": loss_kwh, "heating_kwh": heating_kwh,
        "mixing_kwh": mixing_kwh, "total_kwh": total_kwh,
        "formulas": low["formulas"], "limitations": low["limitations"],
    }
    llm = {
        "total_kwh": pair(total_kwh), "feed_heating_kwh": pair(feed_kwh), "heat_loss_kwh": pair(loss_kwh),
        "mixing_kwh": pair(mixing_kwh), "heat_loss_power_w": pair(loss_power_w),
        "wall": wall_info(geometry, insulation, loss_kwh, delta_outside),
        "target_c": target_c, "outside_c": ambient_c, "days": days, "insulation": insulation,
        "reactor_volume_l": reactor_volume_l, "label": "assumption" if assumptions else "measured",
    }
    return result("estimate_heating_energy", ok=True, data=data, llm=llm, assumptions=assumptions,
                  sources=SOURCES + U_SOURCES, label="assumption", question=question)


def estimate_heating_over_days(days: dict, **kwargs) -> dict:
    """Heating for a digestion time given as a range (e.g. mesophilic 25–35 days).

    low  = the low corner with the SHORT time, high = the high corner with the LONG time.
    Every tool (heating, regimes, scenarios, economics) uses this one function, so the
    same batch, reactor and weather always give the same heating number in one dialog.
    """
    short = estimate_heating_energy(days=days["low"], **kwargs)
    if not short["ok"] or days["low"] == days["high"]:
        return short
    long = estimate_heating_energy(days=days["high"], **kwargs)
    data = dict(long["data"])
    for key in ["feed_heating_kwh", "heat_loss_kwh", "heating_kwh", "mixing_kwh", "total_kwh"]:
        data[key] = make(short["data"][key]["low"], long["data"][key]["high"])
    data["days"] = days
    llm = dict(long["llm"])
    for key in ["total_kwh", "feed_heating_kwh", "heat_loss_kwh", "mixing_kwh"]:
        llm[key] = pair(data[key])
    llm["days"] = pair(days)
    llm["wall"] = {**long["llm"]["wall"], "heat_loss_kwh": pair(data["heat_loss_kwh"])}
    assumptions = [a for a in long["assumptions"]]
    return result("estimate_heating_energy", ok=True, data=data, llm=llm, assumptions=assumptions,
                  sources=long["sources"], label=long["label"], question=long["question"])
