"""Arduino <-> Raspberry Pi protocol v1: one JSON object per line ('\\n'), UTF-8, 115200 baud.

Arduino -> Pi
    {"type":"boot","fw":"0.1","proto":1}                                          after reset (all relays OFF)
    {"type":"state","seq":12,"uptime_ms":24000,"temp_c":36.8,"rh_pct":88.0,"gas_in":512,"gas_out":95,
     "p_kpa":1.42,"relays":{"heat":1,"cool":0,"pump":0},
     "alarms":{"leak":0,"overheat":0,"watchdog":0,"temp_sensor":0,"warmup":0}}      every 1 s
    {"type":"ack","id":17,"ok":1,"relays":{...}}                                   command done
    {"type":"ack","id":17,"ok":0,"reason":"interlock","relays":{...}}             command refused + why
    {"type":"event","code":"leak_heat_off"}                                        Arduino protection fired

Pi -> Arduino
    {"cmd":"relay","name":"heat","state":1,"id":17}
    {"cmd":"ping","id":18}            every 2 s; 10 s without any command -> Arduino switches all relays OFF
    {"cmd":"all_off","id":19}
    {"cmd":"reset","id":20}           clear the leak lock (only when the gas outside is below the threshold)

A sensor that does not answer is sent as null. Full description: docs/hardware_protocol.md.
"""
from __future__ import annotations

import json
import math

PROTOCOL_VERSION = 1
RELAYS = ("heat", "cool", "pump")
SENSORS = ("temp_c", "rh_pct", "gas_in", "gas_out", "p_kpa")
ALARMS = ("leak", "overheat", "watchdog", "temp_sensor", "warmup")
# Plausible ranges: a value outside is a broken sensor or a broken line, not a reading.
SENSOR_RANGES = {"temp_c": (-40.0, 125.0), "rh_pct": (0.0, 100.0), "gas_in": (0.0, 4095.0),
                 "gas_out": (0.0, 4095.0), "p_kpa": (-20.0, 50.0)}
REASONS = ("interlock", "leak_lock", "overheat", "temp_sensor", "warmup", "bad_cmd", "unknown_relay", "still_leaking")
MAX_LINE = 512


class ProtocolError(ValueError):
    """A line that is not a valid message."""


def _number(value, name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ProtocolError(f"{name} must be a number or null")
    low, high = SENSOR_RANGES[name]
    return float(value) if low <= value <= high else None


def _flag(value, name: str) -> bool:
    if value in (0, 1) and not isinstance(value, float):
        return bool(value)
    raise ProtocolError(f"{name} must be 0 or 1")


def _relays(value) -> dict:
    if not isinstance(value, dict) or any(name not in value for name in RELAYS):
        raise ProtocolError("the state of every relay is needed")
    return {name: _flag(value[name], f"relays.{name}") for name in RELAYS}


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
    if kind == "state":
        alarms = raw.get("alarms") or {}
        if not isinstance(alarms, dict):
            raise ProtocolError("alarms must be an object")
        return {"type": "state", "seq": raw.get("seq"), "uptime_ms": raw.get("uptime_ms"),
                **{name: _number(raw.get(name), name) for name in SENSORS},
                "relays": _relays(raw.get("relays")),
                "alarms": {name: _flag(alarms.get(name, 0), f"alarms.{name}") for name in ALARMS}}
    if kind == "ack":
        if not isinstance(raw.get("id"), int) or raw.get("ok") not in (0, 1, True, False):
            raise ProtocolError("ack needs an integer id and ok 0/1")
        ok = bool(raw["ok"])
        relays = _relays(raw["relays"]) if isinstance(raw.get("relays"), dict) else None
        return {"type": "ack", "id": raw["id"], "ok": ok, "reason": None if ok else str(raw.get("reason") or "refused")[:40],
                "relays": relays}
    if kind == "event":
        if not isinstance(raw.get("code"), str):
            raise ProtocolError("event without code")
        return {"type": "event", "code": raw["code"][:40]}
    if kind == "boot":
        return {"type": "boot", "fw": str(raw.get("fw", ""))[:20], "proto": raw.get("proto")}
    raise ProtocolError(f"unknown message type {kind!r}")


def encode(message: dict) -> bytes:
    return (json.dumps(message, separators=(",", ":"), ensure_ascii=True) + "\n").encode("ascii")


def relay(identifier: int, name: str, on: bool) -> bytes:
    if name not in RELAYS:
        raise ValueError(f"unknown relay {name!r}")
    return encode({"cmd": "relay", "name": name, "state": 1 if on else 0, "id": identifier})


def ping(identifier: int) -> bytes:
    return encode({"cmd": "ping", "id": identifier})


def all_off(identifier: int) -> bytes:
    return encode({"cmd": "all_off", "id": identifier})


def reset(identifier: int) -> bytes:
    return encode({"cmd": "reset", "id": identifier})
