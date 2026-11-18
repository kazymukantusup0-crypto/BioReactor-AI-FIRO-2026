"""Pi-side rules (the SECOND layer; the Arduino sketch is the main one and has the last word). Pure functions.

Thresholds are NOT a Pi setting any more: the Arduino keeps them in EEPROM and sends them in every status
(temp_min, temp_max, temp_hard_max, gas_out_limit, gas_in_limit). The Pi uses them for:
    level()          norm / attention / danger of a reading, for the page
    refuse_reason()  the same checks as requestRelay() in the sketch, so a command that the Arduino would refuse is
                     refused here with the same reason (and a firmware bug is caught twice)
"""
from __future__ import annotations

RH_WARN_PCT = 95.0          # condensate on the DHT11
GAS_OUT_WARN_SHARE = 0.8    # gas outside >= 80 % of the leak limit -> attention


def level(name: str, value: float | None, limits: dict | None) -> str:
    """ok / warn / danger of one reading; 'unknown' when the sensor does not answer or the limits are not known yet."""
    if value is None:
        return "unknown"
    if name == "rh_pct":
        return "warn" if value >= RH_WARN_PCT else "ok"
    if not limits:
        return "ok"
    if name == "temp_c":
        if value >= limits["temp_hard_max"]:
            return "danger"
        return "warn" if value < limits["temp_min"] or value > limits["temp_max"] else "ok"
    if name == "gas_in":
        # Inside the barrel gas is the product: above the limit only means «time to pump it out».
        return "warn" if value > limits["gas_in_limit"] else "ok"
    if name == "gas_out":
        if value > limits["gas_out_limit"]:
            return "danger"
        return "warn" if value >= GAS_OUT_WARN_SHARE * limits["gas_out_limit"] else "ok"
    raise KeyError(name)


def refuse_reason(name: str, on: bool, *, link_ok: bool, relays: dict, alarms: dict) -> str | None:
    """Why a person's relay command is refused (None = allowed). Mirrors requestRelay() in the sketch.
    Reasons are the Arduino's error codes in lower case (estop, leak, warmup, no_temp, overheat, interlock)."""
    if name not in relays:
        return "unknown_relay"
    if not link_ok:
        return "no_link"
    if not on:
        return None
    if alarms.get("estop"):
        return "estop"
    if alarms.get("leak"):
        return "leak"
    if name == "heat":
        if alarms.get("warmup"):
            return "warmup"
        if alarms.get("no_temp"):
            return "no_temp"
        if alarms.get("overheat"):
            return "overheat"
        if relays.get("cool"):
            return "interlock"
    if name == "cool" and relays.get("heat"):
        return "interlock"
    if name == "pump" and alarms.get("warmup"):
        return "warmup"
    return None
