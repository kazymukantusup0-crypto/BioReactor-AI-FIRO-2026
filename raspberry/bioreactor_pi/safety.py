"""Pi-side protection (the SECOND layer; the Arduino sketch is the main one). Pure functions.

The Pi repeats the Arduino's rules (leak, overheat, broken temperature sensor, interlock) so a command that the
Arduino would refuse is refused already here, with a clear reason, and so a firmware bug is caught twice.
It adds what the Arduino cannot know: «no link with the Arduino», and the person-only leak reset.
"""
from __future__ import annotations

LEVELS = ("ok", "warn", "danger")


def level(name: str, value: float | None, th: dict) -> str:
    """norm / attention / danger of one reading; 'unknown' when the sensor does not answer."""
    if value is None:
        return "unknown"
    if name == "temp_c":
        t = th["temp_c"]
        if value <= t["danger_low"] or value >= t["danger_high"]:
            return "danger"
        if value < t["warn_low"] or value > t["warn_high"]:
            return "warn"
        return "ok"
    if name == "rh_pct":
        t = th["rh_pct"]
        return "danger" if value >= t["danger_high"] else "warn" if value >= t["warn_high"] else "ok"
    if name == "gas_in":
        # Inside the barrel gas is the product, not a danger: very low only means «little gas is forming».
        return "warn" if value < th["gas_in_raw"]["warn_low"] else "ok"
    if name == "gas_out":
        t = th["gas_out_raw"]
        return "danger" if value >= t["leak"] else "warn" if value >= t["warn"] else "ok"
    if name == "p_kpa":
        t = th["pressure_kpa"]
        return "danger" if value >= t["danger"] else "warn" if value >= t["pump_warn"] else "ok"
    raise KeyError(name)


def is_leak(gas_out: float | None, th: dict) -> bool:
    return gas_out is not None and gas_out >= th["gas_out_raw"]["leak"]


def is_overheat(temp_c: float | None, th: dict, active: bool) -> bool:
    """With hysteresis: starts at overheat_c, ends below overheat_release_c."""
    if temp_c is None:
        return active
    return temp_c >= th["overheat_release_c"] if active else temp_c >= th["overheat_c"]


def refuse_reason(name: str, on: bool, *, link_ok: bool, relays: dict, leak_latched: bool, overheat: bool,
                  temp_known: bool = True, warmup: bool = False) -> str | None:
    """Why a person's command is refused (None = allowed). Switching OFF is always allowed when there is a link."""
    if name not in relays:
        return "unknown_relay"
    if not link_ok:
        return "no_link"
    if not on:
        return None
    if name == "heat":
        if leak_latched:
            return "leak_lock"
        if not temp_known:
            return "temp_sensor"
        if overheat:
            return "overheat"
        if warmup:
            return "warmup"
    if (name == "heat" and relays.get("cool")) or (name == "cool" and relays.get("heat")):
        return "interlock"
    return None
