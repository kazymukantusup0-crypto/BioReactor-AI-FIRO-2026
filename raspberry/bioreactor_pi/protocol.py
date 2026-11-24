"""Arduino <-> Raspberry Pi protocol of firmware/bioreactor/bioreactor.ino ("bioreactor-1.0"). 115200 baud, one line per
message ('\\n'). Full description: docs/hardware_protocol.md.

Arduino -> Pi (JSON)
    {"type":"boot","fw":"bioreactor-1.0"}                                    after power-on / reset (all relays OFF)
    {"type":"status","fw":"bioreactor-1.0","uptime_s":12,"mq_in":197,"mq_out":120,"humidity":85.0,"temp":36.8,
     "relays":{"heat":false,"cool":false,"pump":false,"auger":false},
     "remote":{"heat":false,"cool":false,"pump":false,"auger":false},       relay switched ON by a command from the Pi
     "auto":true,"temp_min":35.0,"temp_max":38.0,"temp_hard_max":45.0,"gas_out_limit":400,"gas_in_limit":700,
     "alarms":{"estop":false,"leak":false,"overheat":false,"warmup":false,"no_temp":false,"link_lost":false,
               "auger_timeout":false}}                                          every 1 s
    {"type":"ack","cmd":"RELAY","ok":true}
    {"type":"ack","cmd":"RELAY","ok":false,"error":"INTERLOCK"}

Pi -> Arduino (plain text, any case)
    PING                     every 2 s («I am here»); GET sends a status at once (no ack)
    RELAY <1-4> <0|1>        1 heat, 2 cool, 3 pump (gas out), 4 auger (screw motor)
    AUTO <0|1>
    SET TMIN|TMAX|THARD <°C>    SET GOUT|GIN <0-1023 raw MQ-9>
    ESTOP | RESET | ALLOFF

Readings are renamed for the rest of the code: temp -> temp_c, humidity -> rh_pct, mq_in -> gas_in, mq_out -> gas_out.
The gas values are a raw MQ-9 indicator 0-1023, NOT ppm and NOT % methane.
"""
from __future__ import annotations

import json
import math

FIRMWARE_FAMILY = "bioreactor-"
RELAYS = ("heat", "cool", "pump", "auger")
RELAY_NUMBER = {"heat": 1, "cool": 2, "pump": 3, "auger": 4}
SENSORS = ("temp_c", "rh_pct", "gas_in", "gas_out")
SENSOR_FIELDS = {"temp_c": "temp", "rh_pct": "humidity", "gas_in": "mq_in", "gas_out": "mq_out"}
SENSOR_RANGES = {"temp_c": (-55.0, 125.0), "rh_pct": (0.0, 100.0), "gas_in": (0.0, 1023.0), "gas_out": (0.0, 1023.0)}
ALARMS = ("estop", "leak", "overheat", "warmup", "no_temp", "link_lost", "auger_timeout")
# Thresholds kept in the Arduino's EEPROM: status field -> SET key
LIMITS = {"temp_min": "TMIN", "temp_max": "TMAX", "temp_hard_max": "THARD", "gas_out_limit": "GOUT", "gas_in_limit": "GIN"}
GAS_LIMITS = ("gas_out_limit", "gas_in_limit")
ERRORS = ("BAD_ARGS", "UNKNOWN", "BAD_KEY", "OUT_OF_RANGE", "LOCAL_EDIT", "INTERLOCK", "NO_TEMP", "OVERHEAT", "WARMUP",
          "ESTOP", "LEAK", "GAS_STILL_HIGH")
COMMANDS = ("PING", "GET", "RELAY", "AUTO", "SET", "ESTOP", "RESET", "ALLOFF")
MAX_LINE = 1024


class ProtocolError(ValueError):
    """A line that is not a valid message."""


def _number(value, name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ProtocolError(f"{name} must be a number or null")
    low, high = SENSOR_RANGES[name]
    return float(value) if low <= value <= high else None


def _flags(value, names, what: str) -> dict:
    if not isinstance(value, dict) or any(not isinstance(value.get(n), bool) for n in names):
        raise ProtocolError(f"{what}: true/false for {', '.join(names)}")
    return {n: value[n] for n in names}


def _limit(value, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ProtocolError(f"{name} must be a number")
    return float(value)


def parse_line(line: bytes | str) -> dict:
    """One line from the Arduino -> a checked message. Raises ProtocolError."""
    if isinstance(line, bytes):
        if len(line) > MAX_LINE:
            raise ProtocolError("line too long")
        try:
            line = line.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ProtocolError("not UTF-8") from error
    line = line.strip()
    if not line or len(line) > MAX_LINE:
        raise ProtocolError("empty or too long")
    try:
        raw = json.loads(line)
    except json.JSONDecodeError as error:
        raise ProtocolError("not JSON") from error
    if not isinstance(raw, dict) or not isinstance(raw.get("type"), str):
        raise ProtocolError("no message type")
    kind = raw["type"]
    if kind == "status":
        if not isinstance(raw.get("auto"), bool):
            raise ProtocolError("auto must be true/false")
        return {"type": "status", "fw": str(raw.get("fw", ""))[:32], "uptime_s": raw.get("uptime_s"),
                **{name: _number(raw.get(field), name) for name, field in SENSOR_FIELDS.items()},
                "relays": _flags(raw.get("relays"), RELAYS, "relays"),
                "remote": _flags(raw.get("remote"), RELAYS, "remote"),
                "auto": raw["auto"],
                "limits": {name: int(_limit(raw.get(name), name)) if name in GAS_LIMITS else _limit(raw.get(name), name)
                           for name in LIMITS},
                "alarms": _flags(raw.get("alarms"), ALARMS, "alarms")}
    if kind == "ack":
        if not isinstance(raw.get("cmd"), str) or not isinstance(raw.get("ok"), bool):
            raise ProtocolError("ack needs cmd and ok true/false")
        return {"type": "ack", "cmd": raw["cmd"].upper()[:16], "ok": raw["ok"],
                "error": None if raw["ok"] else str(raw.get("error") or "REFUSED")[:24]}
    if kind == "boot":
        return {"type": "boot", "fw": str(raw.get("fw", ""))[:32]}
    raise ProtocolError(f"unknown message type {kind!r}")


# ---------------------------------------------------------------- limits (same rule as validSettings() in the sketch)
def limits_error(limits: dict) -> str | None:
    """None when the five thresholds are valid together, else a short reason (the Arduino answers OUT_OF_RANGE)."""
    t_min, t_max, hard = limits["temp_min"], limits["temp_max"], limits["temp_hard_max"]
    if t_min < 0 or t_max > 68:
        return "temp_range"
    if t_min > t_max - 0.5:
        return "min_above_max"
    if hard < t_max + 2.0 or hard > 70:
        return "hard_max"
    for name in GAS_LIMITS:
        if not 50 <= limits[name] <= 1000:
            return "gas_range"
    return None


# ---------------------------------------------------------------- commands (bytes to write)
def _line(text: str) -> bytes:
    return (text + "\n").encode("ascii")


def ping() -> bytes:
    return _line("PING")


def get() -> bytes:
    return _line("GET")


def relay(name: str, on: bool) -> bytes:
    if name not in RELAY_NUMBER:
        raise ValueError(f"unknown relay {name!r}")
    return _line(f"RELAY {RELAY_NUMBER[name]} {1 if on else 0}")


def auto(on: bool) -> bytes:
    return _line(f"AUTO {1 if on else 0}")


def set_limit(name: str, value: float) -> bytes:
    if name not in LIMITS:
        raise ValueError(f"unknown limit {name!r}")
    text = str(int(round(value))) if name in GAS_LIMITS else f"{value:.1f}"
    return _line(f"SET {LIMITS[name]} {text}")


def estop() -> bytes:
    return _line("ESTOP")


def reset() -> bytes:
    return _line("RESET")


def all_off() -> bytes:
    return _line("ALLOFF")


def command_name(data: bytes) -> str:
    """b"RELAY 1 1\\n" -> "RELAY" (the ack carries this name)."""
    return data.decode("ascii").split()[0].upper()
