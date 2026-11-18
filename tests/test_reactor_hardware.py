"""Reactor hardware: Arduino -> USB -> Raspberry Pi -> network -> laptop. Every level is tested on its own.

    protocol            parse / reject lines, command format {"cmd":"relay","name":"heat","state":1}
    Arduino rules       the virtual Arduino mirrors firmware/bioreactor/bioreactor.ino: leak, overheat, broken
                        temperature sensor, interlock, 10 s watchdog, all OFF at boot, pump stop
    Pi (second layer)   with a DUMB Arduino that has no protection at all — the Pi rules are proven on their own:
                        leak -> heater off + lock until a person resets, overheat, interlock, no Arduino link,
                        laptop silent > 15 s -> all_off, ping every 2 s, USB pulled -> reconnect
    Pi HTTP API         /state, /relay (confirmation), /reset, /events (SSE), token
    laptop client       «НЕТ СВЯЗИ» on the Pi level and on the Arduino level, commands refused, source label
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


@pytest.fixture
def config():
    return pi_config.load(None)


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


# ================================================================== protocol
def state_line(**over) -> bytes:
    message = {"type": "state", "seq": 1, "uptime_ms": 1000, "temp_c": 36.5, "rh_pct": 88, "gas_in": 500, "gas_out": 90,
               "p_kpa": 1.2, "relays": {"heat": 0, "cool": 0, "pump": 0},
               "alarms": {"leak": 0, "overheat": 0, "watchdog": 0, "temp_sensor": 0, "warmup": 0}}
    message.update(over)
    return json.dumps(message).encode() + b"\n"


def test_protocol_parses_state():
    message = protocol.parse_line(state_line(relays={"heat": 1, "cool": 0, "pump": 0}))
    assert message["type"] == "state" and message["temp_c"] == 36.5 and message["relays"]["heat"] is True


def test_protocol_null_and_out_of_range_sensor_is_unknown():
    message = protocol.parse_line(state_line(temp_c=None, p_kpa=999))
    assert message["temp_c"] is None and message["p_kpa"] is None


@pytest.mark.parametrize("line", [b"", b"garbage", b"[1,2]", b'{"type":"state"}', b'{"type":"nope"}', b"\xff\xfe",
                                  state_line(relays={"heat": 1}), state_line(temp_c="hot"),
                                  state_line(relays={"heat": 2, "cool": 0, "pump": 0}), b"{" + b"x" * 600 + b"}"])
def test_protocol_rejects_bad_lines(line):
    with pytest.raises(protocol.ProtocolError):
        protocol.parse_line(line)


def test_protocol_command_format():
    assert json.loads(protocol.relay(5, "heat", True)) == {"cmd": "relay", "name": "heat", "state": 1, "id": 5}
    assert json.loads(protocol.ping(6)) == {"cmd": "ping", "id": 6}
    assert json.loads(protocol.all_off(7)) == {"cmd": "all_off", "id": 7}
    assert protocol.reset(8).endswith(b"\n")
    with pytest.raises(ValueError):
        protocol.relay(1, "valve", True)


def test_protocol_ack_with_reason():
    ack = protocol.parse_line(b'{"type":"ack","id":3,"ok":0,"reason":"interlock","relays":{"heat":1,"cool":0,"pump":0}}')
    assert ack == {"type": "ack", "id": 3, "ok": False, "reason": "interlock",
                   "relays": {"heat": True, "cool": False, "pump": False}}


# ================================================================== Arduino rules (virtual = firmware mirror)
def acks(arduino):
    return [json.loads(line) for line in arduino.take_output() if b'"ack"' in line]


def tick(arduino, seconds):
    for _ in range(seconds):
        arduino.step(1)
        arduino.handle(protocol.ping(99))


def test_arduino_boot_all_off(config):
    arduino = VirtualArduino(config)
    arduino.handle(protocol.relay(1, "pump", True))
    arduino.boot()
    assert not any(arduino.relay.values())
    assert json.loads(arduino.take_output()[0])["type"] == "boot"


def test_arduino_physics(config):
    arduino = VirtualArduino(config)
    arduino.handle(protocol.relay(1, "heat", True))
    start = arduino.temp_c
    tick(arduino, 60)
    assert arduino.temp_c > start + 1.5, "the heater slowly raises the temperature"
    arduino.handle(protocol.relay(2, "heat", False))
    arduino.handle(protocol.relay(3, "cool", True))
    hot = arduino.temp_c
    tick(arduino, 30)
    assert arduino.temp_c < hot - 1
    p = arduino.p_kpa
    tick(arduino, 9)
    assert arduino.p_kpa > p, "gas accumulates"
    arduino.handle(protocol.relay(4, "pump", True))
    p = arduino.p_kpa
    arduino.step(5)
    assert arduino.p_kpa < p, "the pump lowers the pressure"


def test_arduino_leak_heater_off_and_lock_until_reset(config):
    arduino = VirtualArduino(config)
    arduino.handle(protocol.relay(1, "heat", True))
    arduino.leak_on = True
    tick(arduino, 10)
    assert not arduino.relay["heat"] and arduino.alarm["leak"]
    arduino.take_output()
    arduino.handle(protocol.relay(2, "heat", True))
    assert acks(arduino)[-1]["reason"] == "leak_lock"
    arduino.handle(protocol.reset(3))
    assert acks(arduino)[-1]["reason"] == "still_leaking"
    arduino.leak_on = False
    tick(arduino, 15)
    arduino.take_output()
    assert arduino.alarm["leak"], "the lock stays after the gas is gone, until reset"
    arduino.handle(protocol.reset(4))
    assert acks(arduino)[-1]["ok"] == 1 and not arduino.alarm["leak"]


def test_arduino_interlock(config):
    arduino = VirtualArduino(config)
    arduino.handle(protocol.relay(1, "cool", True))
    arduino.take_output()
    arduino.handle(protocol.relay(2, "heat", True))
    assert acks(arduino)[-1]["reason"] == "interlock" and not arduino.relay["heat"]


def test_arduino_overheat_and_broken_temp_sensor(config):
    arduino = VirtualArduino(config)
    arduino.temp_c = config["thresholds"]["overheat_c"] + 0.1
    arduino.handle(protocol.relay(1, "heat", True))
    arduino.step(1)
    assert not arduino.relay["heat"] and arduino.alarm["overheat"]
    arduino.take_output()
    arduino.handle(protocol.relay(2, "heat", True))
    assert acks(arduino)[-1]["reason"] == "overheat"
    arduino = VirtualArduino(config)
    arduino.handle(protocol.relay(1, "heat", True))
    arduino.temp_sensor_broken = True
    arduino.step(1)
    assert not arduino.relay["heat"], "no temperature -> no heating (fail-safe)"
    arduino.take_output()
    arduino.handle(protocol.relay(2, "heat", True))
    assert acks(arduino)[-1]["reason"] == "temp_sensor"


def test_arduino_watchdog_10s(config):
    arduino = VirtualArduino(config)
    arduino.p_kpa = 3.0
    arduino.sim["pump_kpa_per_s"] = 0.0
    arduino.handle(protocol.relay(1, "pump", True))
    for _ in range(config["arduino_watchdog_s"] - 1):
        arduino.step(1)
    assert arduino.relay["pump"]
    arduino.step(1)
    assert not any(arduino.relay.values()) and arduino.alarm["watchdog"]


def test_arduino_pump_stops_when_empty(config):
    arduino = VirtualArduino(config)
    arduino.p_kpa = 0.3
    arduino.handle(protocol.relay(1, "pump", True))
    tick(arduino, 10)
    assert not arduino.relay["pump"]


def test_arduino_mq_warmup_blocks_heater(config):
    config["simulator"]["mq_warmup_s"] = 5
    arduino = VirtualArduino(config)
    arduino.take_output()
    arduino.handle(protocol.relay(1, "heat", True))
    assert acks(arduino)[-1]["reason"] == "warmup"
    tick(arduino, 5)
    arduino.take_output()
    arduino.handle(protocol.relay(2, "heat", True))
    assert acks(arduino)[-1]["ok"] == 1


# ================================================================== Pi (second layer) with a DUMB Arduino
class DumbArduino:
    """An Arduino WITHOUT any protection: obeys every command. Tests send its state lines by hand."""
    port = "/dev/ttyACM0"

    def __init__(self):
        self.relay = {"heat": False, "cool": False, "pump": False}
        self.lines: list[bytes] = []
        self.written: list[dict] = []
        self.is_open = False
        self.unplugged = False

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
        message = json.loads(data)
        self.written.append(message)
        if message["cmd"] == "relay":
            self.relay[message["name"]] = bool(message["state"])
        if message["cmd"] == "all_off":
            self.relay = {k: False for k in self.relay}
        self.lines.append(json.dumps({"type": "ack", "id": message["id"], "ok": 1,
                                      "relays": {k: int(v) for k, v in self.relay.items()}}).encode())

    def send(self, **over):
        self.lines.append(state_line(relays={k: int(v) for k, v in self.relay.items()}, **over))


@pytest.fixture
def dumb(config):
    clock = Clock()
    arduino = DumbArduino()
    bridge = Bridge(config, arduino, Journal(":memory:"), clock=clock, wall=lambda: 1_000_000 + clock.t)
    arduino.send()
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
    return [m for m in arduino.written if m["cmd"] == "relay"]


def test_pi_leak_heater_off_lock_and_person_reset(dumb, config):
    bridge, arduino, clock = dumb
    assert bridge.command("heat", True)["ok"] and arduino.relay["heat"]
    step(bridge, arduino, clock, gas_out=config["thresholds"]["gas_out_raw"]["leak"] + 50)
    assert not arduino.relay["heat"], "the Pi switched the heater off by itself"
    assert relay_cmds(arduino)[-1]["name"] == "heat" and relay_cmds(arduino)[-1]["state"] == 0
    state = bridge.state()
    assert state["leak_latched"] and state["relays"]["heat"]["on_blocked"] == "leak_lock"
    assert any(a["code"] == "leak" and a["needs_reset"] for a in state["alarms"])
    sent = len(relay_cmds(arduino))
    assert bridge.command("heat", True)["reason"] == "leak_lock" and len(relay_cmds(arduino)) == sent
    assert bridge.reset_leak()["reason"] == "still_leaking"
    step(bridge, arduino, clock, gas_out=80)
    assert bridge.state()["leak_latched"], "gas gone, the lock stays until a PERSON resets it"
    assert bridge.reset_leak("operator")["ok"]
    assert bridge.command("heat", True)["ok"]
    journal = bridge.journal.recent(50)
    leak = next(r for r in journal if r["what"] == "leak")
    assert leak["kind"] == "alarm" and leak["who"] == "pi_safety" and leak["source"] == "arduino /dev/ttyACM0"
    off = next(r for r in journal if r["what"] == "heat_off" and r["kind"] == "safety")
    assert off["who"] == "pi_safety" and off["details"]["reason"] == "leak"
    assert any(r["what"] == "leak_reset" and r["who"] == "operator" and r["result"] == "ok" for r in journal)


def test_pi_interlock_refuses_without_sending(dumb):
    bridge, arduino, clock = dumb
    assert bridge.command("cool", True)["ok"]
    sent = len(relay_cmds(arduino))
    assert bridge.command("heat", True)["reason"] == "interlock"
    assert len(relay_cmds(arduino)) == sent and not arduino.relay["heat"]
    assert bridge.state()["relays"]["heat"]["on_blocked"] == "interlock"
    assert bridge.command("cool", False)["ok"] and bridge.command("heat", True)["ok"]
    assert bridge.command("cool", True)["reason"] == "interlock"


def test_pi_overheat_with_hysteresis(dumb, config):
    bridge, arduino, clock = dumb
    bridge.command("heat", True)
    step(bridge, arduino, clock, temp_c=config["thresholds"]["overheat_c"] + 0.5)
    assert not arduino.relay["heat"] and bridge.state()["overheat"]
    step(bridge, arduino, clock, temp_c=config["thresholds"]["overheat_release_c"] + 0.5)
    assert bridge.command("heat", True)["reason"] == "overheat"
    step(bridge, arduino, clock, temp_c=config["thresholds"]["overheat_release_c"] - 1)
    assert bridge.command("heat", True)["ok"]


def test_pi_broken_temp_sensor_heater_off(dumb):
    bridge, arduino, clock = dumb
    bridge.command("heat", True)
    step(bridge, arduino, clock, temp_c=None)
    assert not arduino.relay["heat"] and bridge.command("heat", True)["reason"] == "temp_sensor"


def test_pi_no_arduino_data_refuses_everything(dumb, config):
    bridge, arduino, clock = dumb
    bridge.command("pump", True)
    clock.t += config["arduino_timeout_s"] + 1
    bridge.laptop_seen()
    bridge.poll_once(0)
    state = bridge.state()
    assert not state["arduino_link"]["ok"] and state["alarms"][0]["code"] == "arduino_lost"
    assert all(r["value"] is None for r in state["readings"].values()), "stale values are not shown as current"
    assert all(r["on_blocked"] == "no_link" for r in state["relays"].values())
    sent = len(relay_cmds(arduino))
    assert bridge.command("pump", False)["reason"] == "no_link" and len(relay_cmds(arduino)) == sent
    step(bridge, arduino, clock)
    assert bridge.state()["arduino_link"]["ok"]
    assert [r["what"] for r in bridge.journal.recent(50) if r["what"].startswith("arduino_")][:2] == ["arduino_restored", "arduino_lost"]


def test_pi_pings_arduino_every_2s(dumb, config):
    bridge, arduino, clock = dumb
    for _ in range(10):
        step(bridge, arduino, clock)
    pings = [m for m in arduino.written if m["cmd"] == "ping"]
    assert len(pings) >= 10 // config["ping_every_s"]


def test_pi_laptop_silent_15s_all_off(dumb, config):
    bridge, arduino, clock = dumb
    bridge.command("pump", True)
    for _ in range(config["laptop_timeout_s"]):
        step(bridge, arduino, clock, laptop=False)
    assert arduino.relay["pump"], "15 s is still allowed"
    step(bridge, arduino, clock, laptop=False)
    step(bridge, arduino, clock, laptop=False)
    assert not any(arduino.relay.values())
    assert sum(m["cmd"] == "all_off" for m in arduino.written) == 1, "once per silence"
    assert any(a["code"] == "laptop_lost" for a in bridge.state()["alarms"])
    step(bridge, arduino, clock)
    assert bridge.state()["laptop_watchdog"]["ok"]
    whats = [r["what"] for r in bridge.journal.recent(20)]
    assert "laptop_lost" in whats and "laptop_restored" in whats


def test_pi_usb_pulled_reconnects(dumb):
    bridge, arduino, clock = dumb
    bridge.command("heat", True)
    arduino.unplugged = True
    step(bridge, arduino, clock)
    assert not bridge.connected and bridge.state()["relays"]["heat"]["on"] is False
    for _ in range(5):
        step(bridge, arduino, clock)
    assert not bridge.connected, "port still missing: retry every 3 s, no crash"
    arduino.unplugged = False
    arduino.lines.clear()
    for _ in range(4):
        step(bridge, arduino, clock)
    assert bridge.connected and bridge.state()["arduino_link"]["ok"]
    whats = [r["what"] for r in bridge.journal.recent(30)]
    assert whats.count("usb_open") == 2 and "usb_lost" in whats


def test_pi_virtual_serial_unplug_and_arduino_resets(config):
    clock = Clock()
    link = VirtualSerial(config, clock=clock)
    bridge = Bridge(config, link, Journal(":memory:"), simulated=True, clock=clock, wall=lambda: 1e6 + clock.t)

    def run(n):
        for _ in range(n):
            clock.t += 1
            bridge.laptop_seen()
            bridge.poll_once(0)
            bridge.poll_once(0)
    run(3)
    assert bridge.command("pump", True)["ok"]
    bridge.simulate("usb", True)
    run(6)
    assert not bridge.state()["arduino_link"]["ok"] and bridge.command("pump", True)["reason"] == "no_link"
    bridge.simulate("usb", False)
    run(5)
    state = bridge.state()
    assert state["arduino_link"]["ok"] and not state["relays"]["pump"]["on"], "the Arduino reset on reconnect: all OFF"
    assert bridge.firmware == "virtual-0.1"


def test_pi_frozen_arduino(config):
    clock = Clock()
    link = VirtualSerial(config, clock=clock)
    bridge = Bridge(config, link, Journal(":memory:"), simulated=True, clock=clock, wall=lambda: 1e6 + clock.t)
    for _ in range(3):
        clock.t += 1
        bridge.poll_once(0)
    bridge.simulate("arduino_silent", True)
    for _ in range(config["arduino_timeout_s"] + 2):
        clock.t += 1
        bridge.laptop_seen()
        bridge.poll_once(0)
    assert bridge.connected and not bridge.state()["arduino_link"]["ok"]


def test_find_port():
    class Port:
        def __init__(self, device, vid):
            self.device, self.vid = device, vid
    assert find_port(linux_globs=["/dev/ttyACM0", "/dev/ttyUSB0"]) == "/dev/ttyACM0"
    assert find_port([Port("COM1", None), Port("COM4", 0x9999), Port("COM7", 0x1A86)], linux_globs=[]) == "COM7"
    assert find_port([Port("COM1", None)], linux_globs=[]) is None


def test_safety_levels(config):
    th = config["thresholds"]
    assert safety.level("temp_c", 37, th) == "ok"
    assert safety.level("temp_c", 31, th) == "warn"
    assert safety.level("temp_c", 20, th) == "danger"
    assert safety.level("gas_out", th["gas_out_raw"]["leak"], th) == "danger"
    assert safety.level("p_kpa", th["pressure_kpa"]["pump_warn"], th) == "warn"
    assert safety.level("temp_c", None, th) == "unknown"
    assert safety.refuse_reason("heat", False, link_ok=True, relays={"heat": True, "cool": False, "pump": False},
                                leak_latched=True, overheat=True, temp_known=False) is None, "OFF is always allowed"


# ================================================================== Pi HTTP API (real sockets)
@pytest.fixture
def pi_server(config, tmp_path):
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
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def test_pi_http_api(pi_server):
    bridge, url = pi_server
    assert http(url + "/health")[1]["ok"] is True
    assert http(url + "/state", token="wrong")[0] == 401
    code, state = http(url + "/state")
    assert code == 200 and state["arduino_link"]["ok"] and state["bridge"]["simulated"]
    assert http(url + "/relay", {"name": "heat", "state": 1})[0] == 428, "confirmation required"
    assert http(url + "/relay", {"name": "valve", "state": 1, "confirm": True})[0] == 400
    code, result = http(url + "/relay", {"name": "heat", "state": 1, "confirm": True, "who": "operator"})
    assert code == 200 and result["ok"] and result["relays"]["heat"]
    assert http(url + "/relay", {"name": "cool", "state": 1, "confirm": True})[1]["reason"] == "interlock"
    assert http(url + "/simulate", {"what": "leak", "on": True})[1]["ok"]
    deadline = time.time() + 8
    while time.time() < deadline and not http(url + "/state")[1]["leak_latched"]:
        time.sleep(0.2)
    state = http(url + "/state")[1]
    assert state["leak_latched"] and not state["relays"]["heat"]["on"]
    assert http(url + "/reset", {"confirm": True})[1]["reason"] == "still_leaking"
    assert http(url + "/history?window=600")[1]["points"]
    assert http(url + "/history?window=5")[0] == 400
    journal = http(url + "/journal?limit=100")[1]["items"]
    assert {"leak", "heat_on", "cool_on"} <= {r["what"] for r in journal}


def test_pi_sse_stream(pi_server):
    bridge, url = pi_server
    request = urllib.request.Request(url + "/events", headers={"X-Bioreactor-Token": "secret"})
    with urllib.request.urlopen(request, timeout=5) as response:
        assert response.readline().decode().startswith("event: state")
        data = response.readline().decode()
    assert json.loads(data[len("data: "):])["arduino_link"]["ok"]


# ================================================================== laptop client
def test_laptop_client_simulator_and_network_cut(tmp_path):
    client = ReactorClient({"mode": "simulator", "pi_url": "http://unused", "poll_s": 0.2, "link_timeout_s": 1.5,
                            "request_timeout_s": 1}, journal_path=tmp_path / "sim.sqlite3")
    client.start()
    try:
        deadline = time.time() + 6
        while time.time() < deadline and not client.status()["controls_enabled"]:
            time.sleep(0.1)
        status = client.status()
        assert status["source"]["kind"] == "simulator" and status["link"]["ok"]
        assert client.command("heat", True)["ok"] and client.status()["relays"]["heat"]["on"]
        assert client.check_connection()["ok"]
        client.simulate("network", True)
        time.sleep(2)
        status = client.status()
        assert status["link"]["level"] == "pi" and not status["controls_enabled"]
        assert all(r["value"] is None for r in status["readings"].values())
        assert status["alarms"][0]["code"] == "pi_lost"
        assert client.command("heat", False)["reason"] == "no_link"
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
    assert status["source"] == {"kind": "pi", "address": "127.0.0.1:9", "arduino_port": None, "firmware": None}
    assert status["link"]["level"] == "pi" and not status["controls_enabled"]
    assert client.command("heat", True)["reason"] == "no_link"
    assert client.simulate("leak", True)["reason"] == "not_simulator"


# ================================================================== the agent only reads
def test_agent_code_has_no_path_to_relays():
    """src/agent_v10 may import only src.hardware.live (a deep copy of the status)."""
    for path in (ROOT / "src/agent_v10").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for line in re.findall(r"^\s*(?:from|import)\s+src\.hardware\b.*$", text, re.MULTILINE):
            assert re.fullmatch(r"\s*(?:from src\.hardware import live|from src\.hardware\.live import \w+(?:, \w+)*)", line), \
                f"{path.name}: {line.strip()}"
        assert "bioreactor_pi" not in text and "/relay" not in text and ".command(" not in text


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
