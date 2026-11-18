"""Reactor hardware: Arduino (firmware bioreactor-1.0) -> USB -> Raspberry Pi -> network -> laptop. Each level on its own.

    protocol            parse / reject lines of the real firmware, command text (RELAY 1 1, SET TMIN 35.0 ...)
    virtual Arduino     mirrors firmware/bioreactor/bioreactor.ino: boot, warm-up, leak (2 readings, latched, AUTO off),
                        overheat with hysteresis, no temperature sensor, interlock, link watchdog (only relays switched
                        on from the Pi), auger 10 min, E-STOP / RESET / ALLOFF, SET validation, AUTO control
    Pi (second layer)   with a DUMB Arduino that obeys everything: waits for the boot line, pings every 2 s, refuses
                        with the Arduino's reasons without sending, laptop silent -> only remote relays OFF (never
                        ALLOFF), E-STOP even when the status is late, USB pulled -> reconnect
    Pi HTTP API         /state, /relay /auto /limit /reset (confirmation), /estop (none), /events, token
    laptop client       simulator, «НЕТ СВЯЗИ» on both levels, mode auto: finds the Pi and names the route
    agent               reads a copy only; no import path to commands
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "raspberry"))

from bioreactor_pi import config as pi_config, protocol, safety  # noqa: E402
from bioreactor_pi.bridge import Bridge  # noqa: E402
from bioreactor_pi.journal import Journal  # noqa: E402
from bioreactor_pi.serial_link import LinkError, find_port  # noqa: E402
from bioreactor_pi.server import PiServer  # noqa: E402
from bioreactor_pi.virtual_arduino import VirtualArduino, VirtualSerial  # noqa: E402

from src.hardware import live  # noqa: E402
from src.hardware.client import ReactorClient  # noqa: E402

LIMITS = {"temp_min": 35.0, "temp_max": 38.0, "temp_hard_max": 45.0, "gas_out_limit": 400, "gas_in_limit": 700}
NO_ALARMS = {name: False for name in protocol.ALARMS}
OFF = {name: False for name in protocol.RELAYS}


@pytest.fixture
def config():
    return pi_config.load(None)


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


# ================================================================== protocol (lines of the real firmware)
REAL_STATUS = (b'{"type":"status","fw":"bioreactor-1.0","uptime_s":3,"mq_in":199,"mq_out":996,"humidity":15.0,"temp":23.6,'
               b'"relays":{"heat":false,"cool":true,"pump":false,"auger":false},'
               b'"remote":{"heat":false,"cool":false,"pump":false,"auger":false},"auto":true,"temp_min":20.0,'
               b'"temp_max":23.5,"temp_hard_max":45.0,"gas_out_limit":1000,"gas_in_limit":700,"alarms":{"estop":false,'
               b'"leak":false,"overheat":false,"warmup":true,"no_temp":false,"link_lost":false,"auger_timeout":false}}\r\n')


def status_line(**over) -> bytes:
    message = {"type": "status", "fw": "bioreactor-1.0", "uptime_s": 100, "mq_in": 300, "mq_out": 120, "humidity": 85.0,
               "temp": 36.5, "relays": dict(OFF), "remote": dict(OFF), "auto": False, **LIMITS, "alarms": dict(NO_ALARMS)}
    for key, value in over.items():
        if key in ("relays", "remote", "alarms"):
            message[key] = {**message[key], **value}
        else:
            message[key] = value
    return json.dumps(message).encode() + b"\r\n"


def test_protocol_parses_a_real_status_line():
    m = protocol.parse_line(REAL_STATUS)
    assert m["type"] == "status" and m["temp_c"] == 23.6 and m["rh_pct"] == 15.0
    assert m["gas_in"] == 199 and m["gas_out"] == 996, "raw MQ-9 values 0-1023"
    assert m["relays"]["cool"] is True and m["auto"] is True and m["alarms"]["warmup"] is True
    assert m["limits"] == {"temp_min": 20.0, "temp_max": 23.5, "temp_hard_max": 45.0, "gas_out_limit": 1000,
                           "gas_in_limit": 700}


def test_protocol_boot_and_acks():
    assert protocol.parse_line(b'{"type":"boot","fw":"bioreactor-1.0"}') == {"type": "boot", "fw": "bioreactor-1.0"}
    assert protocol.parse_line(b'{"type":"ack","cmd":"PING","ok":true}') == {"type": "ack", "cmd": "PING", "ok": True, "error": None}
    assert protocol.parse_line(b'{"type":"ack","cmd":"RELAY","ok":false,"error":"INTERLOCK"}')["error"] == "INTERLOCK"


def test_protocol_no_temperature_is_null():
    assert protocol.parse_line(status_line(temp=None))["temp_c"] is None
    assert protocol.parse_line(status_line(temp=-127.0))["temp_c"] is None, "out of range = not a reading"


@pytest.mark.parametrize("line", [b"", b"garbage", b"[1,2]", b'{"type":"status"}', b'{"type":"nope"}', b"\xff\xfe",
                                  b'{"type":"ack","cmd":"PING","ok":1}', b"x" * 2000,
                                  status_line(relays={"heat": 1}), status_line(auto=1)])
def test_protocol_rejects_bad_lines(line):
    with pytest.raises(protocol.ProtocolError):
        protocol.parse_line(line)


def test_protocol_command_text():
    assert protocol.relay("heat", True) == b"RELAY 1 1\n" and protocol.relay("auger", False) == b"RELAY 4 0\n"
    assert protocol.relay("pump", True) == b"RELAY 3 1\n" and protocol.relay("cool", True) == b"RELAY 2 1\n"
    assert protocol.auto(True) == b"AUTO 1\n" and protocol.ping() == b"PING\n" and protocol.get() == b"GET\n"
    assert protocol.set_limit("temp_min", 35.25) == b"SET TMIN 35.2\n" or protocol.set_limit("temp_min", 35.25) == b"SET TMIN 35.3\n"
    assert protocol.set_limit("gas_out_limit", 412.6) == b"SET GOUT 413\n"
    assert protocol.estop() == b"ESTOP\n" and protocol.reset() == b"RESET\n" and protocol.all_off() == b"ALLOFF\n"
    assert protocol.command_name(b"SET TMIN 35.0\n") == "SET"
    with pytest.raises(ValueError):
        protocol.relay("valve", True)


def test_limits_rule_is_the_sketch_rule():
    assert protocol.limits_error(LIMITS) is None
    assert protocol.limits_error({**LIMITS, "temp_min": 37.8}) == "min_above_max"
    assert protocol.limits_error({**LIMITS, "temp_hard_max": 39.0}) == "hard_max", "overheat >= temp_max + 2"
    assert protocol.limits_error({**LIMITS, "temp_hard_max": 71}) == "hard_max"
    assert protocol.limits_error({**LIMITS, "gas_in_limit": 40}) == "gas_range"
    assert protocol.limits_error({**LIMITS, "temp_max": 69}) == "temp_range"


# ================================================================== virtual Arduino = the sketch
def lines(arduino):
    return [json.loads(x) for x in arduino.take_output()]


def acks(arduino):
    return [m for m in lines(arduino) if m["type"] == "ack"]


def run(arduino, seconds):
    for _ in range(int(seconds)):
        arduino.step(1.0)


def ready(config) -> VirtualArduino:
    """After warm-up, temperature in range, manual mode."""
    arduino = VirtualArduino(config)
    arduino.temp_c = 36.5
    run(arduino, config["simulator"]["mq_warmup_s"] + 1)
    arduino.handle(b"AUTO 0\n")
    arduino.take_output()
    return arduino


def test_arduino_boot(config):
    arduino = VirtualArduino(config)
    out = lines(arduino)
    assert out[0] == {"type": "boot", "fw": "bioreactor-1.0-virtual"}
    assert arduino.relay == OFF and arduino.auto is True and arduino.warmup


def test_arduino_warmup_blocks_heater_and_pump(config):
    arduino = VirtualArduino(config)
    arduino.take_output()
    arduino.handle(b"RELAY 1 1\n")
    arduino.handle(b"RELAY 3 1\n")
    arduino.handle(b"RELAY 4 1\n")
    assert [a.get("error") for a in acks(arduino)] == ["WARMUP", "WARMUP", None], "the auger is not locked by warm-up"
    run(arduino, config["simulator"]["mq_warmup_s"] + 1)
    assert not arduino.warmup


def test_arduino_status_fields_match_the_sketch(config):
    arduino = ready(config)
    arduino.step()
    status = lines(arduino)[-1]
    assert set(status) == {"type", "fw", "uptime_s", "mq_in", "mq_out", "humidity", "temp", "relays", "remote", "auto",
                           "temp_min", "temp_max", "temp_hard_max", "gas_out_limit", "gas_in_limit", "alarms"}
    assert protocol.parse_line(json.dumps(status))["type"] == "status"


def test_arduino_auto_mode_thermostat_and_pump(config):
    arduino = VirtualArduino(config)
    arduino.temp_c = 30.0
    run(arduino, config["simulator"]["mq_warmup_s"] + 1)
    assert arduino.auto and arduino.relay["heat"], "AUTO: below temp_min -> heater"
    arduino.temp_c = 39.5
    run(arduino, 1)
    assert arduino.relay["cool"] and not arduino.relay["heat"], "AUTO: above temp_max -> cooler, never both"
    arduino.gas_in = 900
    run(arduino, 1)
    assert arduino.relay["pump"], "AUTO: gas inside > gas_in_limit -> pump"


def test_arduino_manual_relay_switches_auto_off(config):
    arduino = VirtualArduino(config)
    arduino.temp_c = 36.5
    run(arduino, config["simulator"]["mq_warmup_s"] + 1)
    arduino.take_output()
    arduino.handle(b"RELAY 4 1\n")
    assert arduino.auto, "the auger does not touch AUTO"
    arduino.handle(b"relay 2 1\n")
    assert acks(arduino)[-1]["ok"] and not arduino.auto and arduino.remote["cool"], "lower case works too"


def test_arduino_leak_all_off_latched_reset_only_when_clean(config):
    arduino = ready(config)
    arduino.handle(b"RELAY 3 1\n")
    arduino.handle(b"AUTO 1\n")
    arduino.leak_on = True
    run(arduino, 10)
    assert arduino.leak and arduino.relay == OFF and not arduino.auto
    arduino.take_output()
    arduino.handle(b"RELAY 4 1\n")
    arduino.handle(b"AUTO 1\n")
    arduino.handle(b"RESET\n")
    assert [a.get("error") for a in acks(arduino)] == ["LEAK", "LEAK", "GAS_STILL_HIGH"]
    arduino.leak_on = False
    run(arduino, 15)
    assert arduino.leak, "latched: stays until a person resets"
    arduino.handle(b"RESET\n")
    assert acks(arduino)[-1]["ok"] and not arduino.leak


def test_arduino_leak_needs_two_readings(config):
    arduino = ready(config)
    arduino.gas_out = 900
    arduino.sim["gas_out_clean"] = 900
    run(arduino, 1)
    assert not arduino.leak
    run(arduino, 1)
    assert arduino.leak


def test_arduino_interlock(config):
    arduino = ready(config)
    arduino.handle(b"RELAY 1 1\n")
    arduino.handle(b"RELAY 2 1\n")
    arduino.handle(b"RELAY 1 0\n")
    arduino.handle(b"RELAY 2 1\n")
    arduino.handle(b"RELAY 1 1\n")
    assert [a.get("error") for a in acks(arduino)] == [None, "INTERLOCK", None, None, "INTERLOCK"]


def test_arduino_overheat_hysteresis_and_no_sensor(config):
    arduino = ready(config)
    arduino.handle(b"RELAY 1 1\n")
    arduino.temp_c = 45.5
    run(arduino, 1)
    assert arduino.overheat and not arduino.relay["heat"]
    arduino.take_output()
    arduino.temp_c = 44.0
    arduino.handle(b"RELAY 1 1\n")
    assert acks(arduino)[-1]["error"] == "OVERHEAT", "until 2 °C below the limit"
    arduino.temp_c = 42.5
    run(arduino, 1)
    assert not arduino.overheat
    arduino.temp_sensor_broken = True
    run(arduino, 1)
    arduino.take_output()
    arduino.handle(b"RELAY 1 1\n")
    assert acks(arduino)[-1]["error"] == "NO_TEMP"
    arduino.step()
    assert lines(arduino)[-1]["temp"] is None and arduino.relay["heat"] is False


def test_arduino_link_watchdog_only_relays_switched_on_from_the_pi(config):
    arduino = VirtualArduino(config)
    arduino.temp_c = 30.0
    run(arduino, config["simulator"]["mq_warmup_s"] + 1)
    arduino.handle(b"RELAY 4 1\n")            # from the Pi; AUTO keeps the heater on by itself
    run(arduino, 9)
    assert arduino.relay["auger"] and not arduino.link_lost
    run(arduino, 3)
    assert not arduino.relay["auger"] and arduino.link_lost, "10 s without commands -> the Pi's relay off"
    assert arduino.relay["heat"] and arduino.auto, "the AUTO regime keeps running"
    arduino.handle(b"PING\n")
    assert not arduino.link_lost


def test_arduino_no_watchdog_without_remote_relays(config):
    arduino = ready(config)
    run(arduino, 30)
    assert not arduino.link_lost


def test_arduino_auger_timeout_reported_once(config):
    arduino = ready(config)
    arduino.handle(b"RELAY 4 1\n")
    seen = []
    for _ in range(config["simulator"]["auger_max_run_s"] + 3):
        arduino.step()
        arduino.handle(b"PING\n")             # the link is fine: only the run time is too long
        seen += [m["alarms"]["auger_timeout"] for m in lines(arduino) if m["type"] == "status"]
    assert seen.count(True) == 1 and not arduino.relay["auger"]


def test_arduino_estop_reset_alloff(config):
    arduino = ready(config)
    arduino.handle(b"RELAY 1 1\n")
    arduino.handle(b"AUTO 1\n")
    arduino.handle(b"ESTOP\n")
    assert arduino.estop and arduino.relay == OFF and not arduino.auto
    arduino.take_output()
    arduino.handle(b"RELAY 4 1\n")
    arduino.handle(b"AUTO 1\n")
    assert [a.get("error") for a in acks(arduino)] == ["ESTOP", "ESTOP"]
    arduino.handle(b"RESET\n")
    arduino.handle(b"AUTO 1\n")
    assert all(a["ok"] for a in acks(arduino)) and arduino.auto
    arduino.handle(b"ALLOFF\n")
    assert arduino.relay == OFF and not arduino.auto


def test_arduino_set_limits(config):
    arduino = ready(config)
    for line in (b"SET TMIN 36\n", b"SET TMIN 40\n", b"SET XYZ 1\n", b"SET GIN 20\n", b"SET\n", b"SET GOUT 450\n",
                 b"RELAY 9 1\n", b"FOO\n", b"AUTO 2\n"):
        arduino.handle(line)
    assert [a.get("error") for a in acks(arduino)] == [None, "OUT_OF_RANGE", "BAD_KEY", "OUT_OF_RANGE", "BAD_ARGS", None,
                                                       "BAD_ARGS", "UNKNOWN", "BAD_ARGS"]
    assert arduino.cfg["temp_min"] == 36.0 and arduino.cfg["gas_out_limit"] == 450
    arduino.boot()
    assert arduino.cfg["temp_min"] == 36.0, "EEPROM survives a reset"


def test_arduino_get_sends_status_without_ack(config):
    arduino = ready(config)
    arduino.handle(b"GET\n")
    out = lines(arduino)
    assert [m["type"] for m in out] == ["status"]


# ================================================================== Pi (second layer) with a DUMB Arduino
class DumbArduino:
    """An Arduino WITHOUT any protection: obeys every command. Tests send its status lines by hand."""
    port = "/dev/ttyUSB0"

    def __init__(self):
        self.relay = dict(OFF)
        self.remote = dict(OFF)
        self.auto = False
        self.alarms = dict(NO_ALARMS)
        self.lines: list[bytes] = []
        self.written: list[str] = []
        self.is_open = False
        self.unplugged = False
        self.answer = True

    def open(self):
        if self.unplugged:
            raise LinkError("no port")
        self.is_open = True

    def close(self):
        self.is_open = False

    def readline(self, wait_s=0.2):
        if self.unplugged:
            raise LinkError("device disconnected")
        return self.lines.pop(0) if self.lines else None

    def write(self, data):
        if self.unplugged:
            raise LinkError("device disconnected")
        text = data.decode().strip()
        self.written.append(text)
        words = text.split()
        if words[0] == "GET":
            self.send()
            return
        if words[0] == "RELAY":
            name = protocol.RELAYS[int(words[1]) - 1]
            self.relay[name] = words[2] == "1"
            self.remote[name] = words[2] == "1"
        elif words[0] == "ALLOFF":
            self.relay, self.remote, self.auto = dict(OFF), dict(OFF), False
        elif words[0] == "ESTOP":
            self.relay, self.remote, self.auto = dict(OFF), dict(OFF), False
            self.alarms["estop"] = True
        elif words[0] == "AUTO":
            self.auto = words[1] == "1"
        if self.answer:
            self.lines.append(json.dumps({"type": "ack", "cmd": words[0], "ok": True}).encode())

    def boot(self):
        self.lines.append(b'{"type":"boot","fw":"bioreactor-1.0"}\r\n')

    def send(self, **over):
        over.setdefault("relays", dict(self.relay))
        over.setdefault("remote", dict(self.remote))
        over.setdefault("auto", self.auto)
        over["alarms"] = {**self.alarms, **over.get("alarms", {})}
        self.lines.append(status_line(**over))


def make_bridge(config, arduino=None, clock=None):
    clock = clock or Clock()
    arduino = arduino or DumbArduino()
    bridge = Bridge(config, arduino, Journal(":memory:"), clock=clock, wall=lambda: 1_000_000 + clock.t)
    return bridge, arduino, clock


@pytest.fixture
def dumb(config):
    bridge, arduino, clock = make_bridge(config)
    arduino.boot()
    arduino.send()
    for _ in range(3):
        bridge.poll_once(0)
    return bridge, arduino, clock


def step(bridge, arduino, clock, laptop=True, **over):
    clock.t += 1
    if laptop:
        bridge.laptop_seen()
    arduino.send(**over)
    for _ in range(4):
        bridge.poll_once(0)


def relay_cmds(arduino):
    return [w for w in arduino.written if w.startswith("RELAY")]


def test_pi_waits_for_the_boot_line(config):
    bridge, arduino, clock = make_bridge(config)
    bridge.poll_once(0)                     # port opened -> the Mega resets
    arduino.send()
    bridge.poll_once(0)
    assert not bridge.booted and not bridge.state()["arduino_link"]["ok"], "a status before boot is not trusted"
    assert arduino.written == [], "no PING before the boot line"
    assert bridge.command("auger", True)["reason"] == "arduino_starting"
    assert bridge.state()["alarms"][0]["code"] == "arduino_starting"
    arduino.boot()
    arduino.send()
    for _ in range(3):
        bridge.poll_once(0)
    assert bridge.booted and bridge.state()["arduino_link"]["ok"] and bridge.firmware == "bioreactor-1.0"
    assert arduino.written[0] == "PING", "first PING right after boot"


def test_pi_boot_line_missing_is_accepted_after_timeout(config):
    bridge, arduino, clock = make_bridge(config)
    bridge.poll_once(0)
    clock.t += config["boot_timeout_s"] + 1
    arduino.send()
    bridge.poll_once(0)
    assert bridge.booted and bridge.state()["arduino_link"]["ok"]
    assert "no_boot_line" in [r["what"] for r in bridge.journal.recent(10)]


def test_pi_pings_every_2s(dumb, config):
    bridge, arduino, clock = dumb
    start = arduino.written.count("PING")
    for _ in range(10):
        step(bridge, arduino, clock)
    assert arduino.written.count("PING") - start in (5, 6)


def test_pi_reads_limits_auto_remote_and_levels(dumb):
    bridge, arduino, clock = dumb
    step(bridge, arduino, clock, temp=33.0, mq_out=330, mq_in=750, auto=True, relays={"cool": True}, remote={"cool": True})
    state = bridge.state()
    assert state["limits"] == LIMITS and state["auto"] is True
    assert state["relays"]["cool"] == {**state["relays"]["cool"], "on": True, "remote": True}
    assert state["readings"]["temp_c"]["level"] == "warn"
    assert state["readings"]["gas_out"]["level"] == "warn", "330 >= 80 % of 400"
    assert state["readings"]["gas_in"]["level"] == "warn"
    step(bridge, arduino, clock, temp=45.0, mq_out=401)
    state = bridge.state()
    assert state["readings"]["temp_c"]["level"] == "danger" and state["readings"]["gas_out"]["level"] == "danger"


@pytest.mark.parametrize("alarms,relay,reason", [
    ({"estop": True}, "auger", "estop"), ({"leak": True}, "pump", "leak"), ({"warmup": True}, "heat", "warmup"),
    ({"warmup": True}, "pump", "warmup"), ({"no_temp": True}, "heat", "no_temp"), ({"overheat": True}, "heat", "overheat")])
def test_pi_refuses_with_the_arduino_reason_without_sending(dumb, alarms, relay, reason):
    bridge, arduino, clock = dumb
    step(bridge, arduino, clock, alarms=alarms)
    assert bridge.command(relay, True)["reason"] == reason
    assert relay_cmds(arduino) == []
    assert bridge.command(relay, False)["ok"], "switching OFF is always allowed"


def test_pi_interlock(dumb):
    bridge, arduino, clock = dumb
    assert bridge.command("heat", True)["ok"]
    assert bridge.command("cool", True)["reason"] == "interlock"
    assert relay_cmds(arduino) == ["RELAY 1 1"]


def test_pi_relay_command_and_ack_by_name(dumb):
    bridge, arduino, clock = dumb
    result = bridge.command("auger", True, who="operator")
    assert result["ok"] and result["relays"]["auger"] and bridge.remote["auger"]
    assert "GET" in arduino.written, "the new state is read at once"
    arduino.answer = False
    assert bridge.command("auger", False)["reason"] == "no_ack"


def test_pi_arduino_refusal_reason_is_passed_on(dumb):
    bridge, arduino, clock = dumb
    arduino.answer = False
    arduino.lines.append(b'{"type":"ack","cmd":"RELAY","ok":false,"error":"INTERLOCK"}')
    assert bridge.command("cool", True)["reason"] == "interlock"


def test_pi_set_limit_checked_first(dumb):
    bridge, arduino, clock = dumb
    assert bridge.set_limit("temp_min", 37.8)["reason"] == "out_of_range"
    assert bridge.set_limit("gas_in_limit", 2000)["reason"] == "out_of_range"
    assert bridge.set_limit("valve", 1)["reason"] == "bad_key"
    assert not any(w.startswith("SET") for w in arduino.written)
    assert bridge.set_limit("temp_min", 36)["ok"] and "SET TMIN 36.0" in arduino.written
    assert bridge.set_limit("gas_out_limit", 450)["ok"] and "SET GOUT 450" in arduino.written


def test_pi_auto_refused_during_estop(dumb):
    bridge, arduino, clock = dumb
    assert bridge.estop()["ok"] and "ESTOP" in arduino.written
    step(bridge, arduino, clock)
    assert bridge.set_auto(True)["reason"] == "estop"
    assert bridge.state()["alarms"][0] == {**bridge.state()["alarms"][0], "code": "estop", "needs_reset": True}
    assert bridge.reset_alarms()["ok"] and "RESET" in arduino.written


def test_pi_estop_sent_even_when_status_is_late(dumb, config):
    bridge, arduino, clock = dumb
    clock.t += config["arduino_timeout_s"] + 5
    bridge.laptop_seen()
    assert not bridge.state()["arduino_link"]["ok"]
    assert bridge.command("heat", False)["reason"] == "no_link"
    bridge.estop()
    assert "ESTOP" in arduino.written


def test_pi_no_arduino_data_refuses_everything(dumb, config):
    bridge, arduino, clock = dumb
    clock.t += config["arduino_timeout_s"] + 1
    bridge.laptop_seen()
    state = bridge.state()
    assert not state["arduino_link"]["ok"] and state["alarms"][0]["code"] == "arduino_lost"
    assert all(r["value"] is None for r in state["readings"].values())
    for call in (lambda: bridge.command("pump", True), lambda: bridge.set_auto(True), lambda: bridge.reset_alarms(),
                 lambda: bridge.set_limit("temp_min", 36)):
        assert call()["reason"] == "no_link"
    step(bridge, arduino, clock)
    assert bridge.state()["arduino_link"]["ok"]


def test_pi_laptop_silent_switches_off_only_remote_relays(dumb, config):
    bridge, arduino, clock = dumb
    bridge.command("auger", True)
    arduino.relay["heat"] = True               # switched on by the Arduino's AUTO, not from the Pi
    arduino.auto = True
    for _ in range(config["laptop_timeout_s"] + 2):
        step(bridge, arduino, clock, laptop=False)
    assert "RELAY 4 0" in arduino.written and "RELAY 1 0" not in arduino.written
    assert "ALLOFF" not in arduino.written, "ALLOFF would also stop AUTO"
    assert arduino.relay["heat"] and arduino.auto
    state = bridge.state()
    assert {"code": "laptop_lost", "level": "danger"} in state["alarms"]
    journal = {r["what"]: r for r in bridge.journal.recent(20)}
    assert journal["laptop_lost"]["details"]["relays"] == ["auger"] and journal["auger_off"]["who"] == "pi_safety"
    step(bridge, arduino, clock, laptop=True)
    assert bridge.state()["laptop_watchdog"]["ok"]


def test_pi_laptop_silent_nothing_remote_sends_nothing(dumb, config):
    bridge, arduino, clock = dumb
    for _ in range(config["laptop_timeout_s"] + 2):
        step(bridge, arduino, clock, laptop=False)
    assert relay_cmds(arduino) == [] and "ALLOFF" not in arduino.written


def test_pi_alarms_are_journaled_and_auger_timeout_kept(dumb):
    bridge, arduino, clock = dumb
    step(bridge, arduino, clock, alarms={"leak": True}, mq_out=520)
    step(bridge, arduino, clock, alarms={"auger_timeout": True})
    step(bridge, arduino, clock)
    codes = [a["code"] for a in bridge.state()["alarms"]]
    assert "auger_timeout" in codes, "one status with the flag -> shown for 5 min"
    whats = [r["what"] for r in bridge.journal.recent(20)]
    assert "leak" in whats and "leak_cleared" in whats and "auger_timeout" in whats
    clock.t += 400
    bridge.laptop_seen()
    step(bridge, arduino, clock)
    assert "auger_timeout" not in [a["code"] for a in bridge.state()["alarms"]]


def test_pi_usb_pulled_reconnects_and_waits_for_boot(dumb):
    bridge, arduino, clock = dumb
    bridge.command("auger", True)
    arduino.unplugged = True
    step(bridge, arduino, clock)
    assert not bridge.connected and not bridge.state()["arduino_link"]["ok"]
    assert bridge.state()["relays"]["auger"]["on"] is False
    arduino.unplugged = False
    clock.t += 4
    bridge.poll_once(0)
    assert bridge.connected and not bridge.booted
    arduino.boot()
    step(bridge, arduino, clock)
    assert bridge.state()["arduino_link"]["ok"]
    whats = [r["what"] for r in bridge.journal.recent(20)]
    assert "usb_lost" in whats and "usb_open" in whats and "arduino_restored" in whats


def test_pi_virtual_serial_unplug_and_arduino_resets(config):
    clock = Clock()
    link = VirtualSerial(config, clock=clock)
    bridge = Bridge(config, link, Journal(":memory:"), simulated=True, clock=clock, wall=lambda: clock.t)
    for _ in range(config["simulator"]["mq_warmup_s"] + 3):
        clock.t += 1
        bridge.laptop_seen()
        for _ in range(6):
            bridge.poll_once(0)
    assert bridge.state()["arduino_link"]["ok"] and bridge.command("auger", True)["ok"]
    link.unplugged = True
    clock.t += 1
    bridge.poll_once(0)
    assert not bridge.connected
    link.unplugged = False
    for _ in range(6):
        clock.t += 1
        bridge.laptop_seen()
        for _ in range(6):
            bridge.poll_once(0)
    state = bridge.state()
    assert state["arduino_link"]["ok"] and state["relays"]["auger"]["on"] is False, "re-opened port reset the Arduino"
    assert state["auto"] is True and "warmup" in [a["code"] for a in state["alarms"]]


def test_pi_frozen_arduino(config):
    clock = Clock()
    link = VirtualSerial(config, clock=clock)
    bridge = Bridge(config, link, Journal(":memory:"), simulated=True, clock=clock, wall=lambda: clock.t)
    for _ in range(3):
        clock.t += 1
        for _ in range(6):
            bridge.poll_once(0)
    assert bridge.state()["arduino_link"]["ok"]
    link.silent = True
    for _ in range(config["arduino_timeout_s"] + 2):
        clock.t += 1
        bridge.laptop_seen()
        bridge.poll_once(0)
    assert bridge.state()["alarms"][0]["code"] == "arduino_lost"


def test_find_port():
    assert find_port(linux_globs=["/dev/ttyUSB0"]) == "/dev/ttyUSB0"

    class Port:
        def __init__(self, device, vid):
            self.device, self.vid = device, vid
    assert find_port(ports=[Port("COM1", None), Port("COM5", 0x1A86)], linux_globs=[]) == "COM5", "CH340 (Mega clone)"


def test_safety_levels_from_arduino_limits():
    assert safety.level("temp_c", 36.0, LIMITS) == "ok"
    assert safety.level("temp_c", 34.9, LIMITS) == "warn" and safety.level("temp_c", 38.1, LIMITS) == "warn"
    assert safety.level("temp_c", 45.0, LIMITS) == "danger"
    assert safety.level("gas_out", 401, LIMITS) == "danger" and safety.level("gas_out", 100, LIMITS) == "ok"
    assert safety.level("gas_in", 701, LIMITS) == "warn"
    assert safety.level("rh_pct", 96, LIMITS) == "warn"
    assert safety.level("temp_c", None, LIMITS) == "unknown" and safety.level("temp_c", 36.0, None) == "ok"


# ================================================================== Pi HTTP API (real sockets)
@pytest.fixture
def pi_server(config, tmp_path):
    config["simulator"]["mq_warmup_s"] = 0
    link = VirtualSerial(config)
    bridge = Bridge(config, link, Journal(tmp_path / "pi.sqlite3"), simulated=True)
    server = PiServer(bridge, "127.0.0.1", 0, token="secret")
    bridge.start()
    server.start()
    deadline = time.time() + 5
    while time.time() < deadline and not bridge.state()["arduino_link"]["ok"]:
        time.sleep(0.1)
    yield bridge, f"http://127.0.0.1:{server.port}"
    server.stop()
    bridge.stop()


def http(url, body=None, token="secret"):
    request = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "application/json", "X-Bioreactor-Token": token},
                                     method="POST" if body is not None else "GET")
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def test_pi_http_api(pi_server):
    bridge, url = pi_server
    assert http(url + "/health")[1]["ok"] is True
    assert http(url + "/state", token="wrong")[0] == 401
    code, state = http(url + "/state")
    assert code == 200 and state["arduino_link"]["ok"] and state["bridge"]["simulated"] and state["limits"]
    for path, body in (("/relay", {"name": "auger", "state": 1}), ("/auto", {"on": False}),
                       ("/limit", {"name": "temp_min", "value": 36}), ("/reset", {})):
        assert http(url + path, body)[0] == 428, f"{path}: confirmation required"
    assert http(url + "/relay", {"name": "valve", "state": 1, "confirm": True})[0] == 400
    assert http(url + "/limit", {"name": "temp_min", "value": "x", "confirm": True})[0] == 400
    code, result = http(url + "/relay", {"name": "auger", "state": 1, "confirm": True, "who": "operator"})
    assert code == 200 and result["ok"] and result["relays"]["auger"]
    assert http(url + "/auto", {"on": False, "confirm": True})[1]["ok"]
    assert http(url + "/relay", {"name": "heat", "state": 1, "confirm": True})[1]["ok"]
    assert http(url + "/relay", {"name": "cool", "state": 1, "confirm": True})[1]["reason"] == "interlock"
    assert http(url + "/limit", {"name": "temp_min", "value": 36, "confirm": True})[1]["limits"]["temp_min"] == 36.0
    assert http(url + "/limit", {"name": "temp_min", "value": 50, "confirm": True})[1]["reason"] == "out_of_range"
    code, result = http(url + "/estop", {})
    assert code == 200 and result["ok"] and not any(result["relays"].values()), "E-STOP: no confirmation needed"
    assert http(url + "/auto", {"on": True, "confirm": True})[1]["reason"] == "estop"
    assert http(url + "/reset", {"confirm": True})[1]["ok"]
    assert http(url + "/simulate", {"what": "leak", "on": True})[1]["ok"]
    deadline = time.time() + 8
    while time.time() < deadline and not http(url + "/state")[1]["arduino_alarms"]["leak"]:
        time.sleep(0.2)
    assert http(url + "/reset", {"confirm": True})[1]["reason"] == "gas_still_high"
    assert http(url + "/history?window=600")[1]["points"]
    assert http(url + "/history?window=5")[0] == 400
    journal = http(url + "/journal?limit=200")[1]["items"]
    assert {"leak", "auger_on", "heat_on", "cool_on", "estop", "set_limit", "reset"} <= {r["what"] for r in journal}


def test_pi_sse_stream(pi_server):
    bridge, url = pi_server
    request = urllib.request.Request(url + "/events", headers={"X-Bioreactor-Token": "secret"})
    with urllib.request.urlopen(request, timeout=5) as response:
        assert response.readline().decode().startswith("event: state")
        data = response.readline().decode()
    assert json.loads(data[len("data: "):])["arduino_link"]["ok"]


def test_journal_migrates_an_old_readings_table(tmp_path):
    import sqlite3
    path = tmp_path / "old.sqlite3"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE readings(id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, temp_c REAL, rh_pct REAL, "
                "gas_in REAL, gas_out REAL, p_kpa REAL, heat INTEGER, cool INTEGER, pump INTEGER, source TEXT NOT NULL)")
    con.execute("INSERT INTO readings(ts,source) VALUES('old','virtual')")
    con.commit()
    con.close()
    journal = Journal(path)
    journal.reading({"temp_c": 36.0}, {"heat": True, "cool": False, "pump": False, "auger": True}, "virtual")
    assert journal.reading_count() == 2
    journal.close()


# ================================================================== laptop client
def test_laptop_client_simulator_and_network_cut(tmp_path, monkeypatch):
    client = ReactorClient({"mode": "simulator", "pi_url": "http://unused", "poll_s": 0.2, "link_timeout_s": 1.5,
                            "request_timeout_s": 1}, journal_path=tmp_path / "sim.sqlite3")
    client.start()
    try:
        deadline = time.time() + 6
        while time.time() < deadline and not client.status()["controls_enabled"]:
            time.sleep(0.1)
        status = client.status()
        assert status["source"]["kind"] == "simulator" and status["link"]["ok"] and status["estop_enabled"]
        assert set(status["relays"]) == {"heat", "cool", "pump", "auger"} and "p_kpa" not in status["readings"]
        assert client.command("auger", True)["ok"] and client.status()["relays"]["auger"]["on"]
        assert client.set_auto(False)["ok"] and client.status()["auto"] is False
        assert client.check_connection()["ok"]
        client.simulate("network", True)
        time.sleep(2)
        status = client.status()
        assert status["link"]["level"] == "pi" and not status["controls_enabled"] and not status["estop_enabled"]
        assert all(r["value"] is None for r in status["readings"].values())
        assert status["alarms"][0]["code"] == "pi_lost"
        assert client.command("heat", False)["reason"] == "no_link"
        assert client.set_limit("temp_min", 36)["reason"] == "no_link"
        assert client.estop()["reason"] == "no_link"
        assert not client.check_connection()["ok"]
        client.simulate("network", False)
        client.simulate("usb", True)
        time.sleep(1.5)
        assert client.status()["link"]["level"] == "arduino"
        client.simulate("usb", False)
    finally:
        client.stop()


def test_laptop_client_pi_absent():
    client = ReactorClient({"mode": "pi", "pi_url": "http://127.0.0.1:9", "poll_s": 1, "link_timeout_s": 5,
                            "request_timeout_s": 0.5})
    client.poll()
    status = client.status()
    assert status["source"] == {"kind": "pi", "mode": "pi", "address": "127.0.0.1:9", "route": None,
                                "arduino_port": None, "firmware": None}
    assert status["link"]["level"] == "pi" and not status["controls_enabled"]
    assert client.command("heat", True)["reason"] == "no_link"
    assert client.simulate("leak", True)["reason"] == "not_simulator"


def test_laptop_auto_mode_finds_the_pi_and_names_the_route(pi_server):
    bridge, url = pi_server
    client = ReactorClient({"mode": "auto", "pi_url": "http://127.0.0.1:9", "token": "secret", "poll_s": 1,
                            "link_timeout_s": 5, "request_timeout_s": 1, "search_timeout_s": 0.5,
                            "pi_candidates": [{"url": "http://127.0.0.1:9", "route": "pi_wifi"},
                                              {"url": url, "route": "cable"},
                                              {"url": "http://127.0.0.1:10", "route": "lan"}]})
    assert client.pi_url == "http://127.0.0.1:9", "starts with the first candidate"
    client.poll()
    status = client.status()
    assert status["link"]["ok"] and status["source"]["route"] == "cable" and status["source"]["mode"] == "auto"
    check = client.check_connection()
    assert check["ok"] and check["route"] == "cable"


def test_laptop_auto_mode_nothing_answers():
    client = ReactorClient({"mode": "auto", "pi_url": "http://127.0.0.1:9", "poll_s": 1, "link_timeout_s": 5,
                            "request_timeout_s": 0.3, "search_timeout_s": 0.3,
                            "pi_candidates": [{"url": "http://127.0.0.1:9", "route": "pi_wifi"},
                                              {"url": "http://127.0.0.1:10", "route": "cable"}]})
    client.poll()
    status = client.status()
    assert status["link"]["level"] == "pi" and status["alarms"][0]["code"] == "pi_lost"


# ================================================================== the agent only reads
def test_agent_code_has_no_path_to_relays():
    """src/agent_v10 may import only src.hardware.live (a deep copy of the status)."""
    for path in (ROOT / "src/agent_v10").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for line in re.findall(r"^\s*(?:from|import)\s+src\.hardware\b.*$", text, re.MULTILINE):
            assert re.fullmatch(r"\s*(?:from src\.hardware import live|from src\.hardware\.live import \w+(?:, \w+)*)", line), \
                f"{path.name}: {line.strip()}"
        for forbidden in ("bioreactor_pi", "/relay", ".command(", ".estop(", ".set_auto(", ".set_limit(", "/estop"):
            assert forbidden not in text, f"{path.name}: {forbidden}"


def test_live_snapshot_is_a_copy():
    class Fake:
        def __init__(self):
            self.data = {"relays": {"heat": {"on": False}}}

        def status(self):
            return self.data
    fake = Fake()
    live.register(fake)
    try:
        snapshot = live.snapshot()
        snapshot["relays"]["heat"]["on"] = True
        assert fake.data["relays"]["heat"]["on"] is False
    finally:
        live.unregister(fake)
    assert live.snapshot() is None
