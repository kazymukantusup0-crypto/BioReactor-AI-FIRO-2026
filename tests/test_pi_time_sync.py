"""The Pi has no battery clock: the laptop's dashboard sets the Pi's time when it connects (> 5 s off).

    clock          VirtualClock never touches this computer's clock; SystemClock only on Linux
    bridge         set_time: within 5 s -> nothing; bad time refused; history/alarm times move with the clock;
                   no settable clock -> not_supported; no CAP_SYS_TIME -> no_permission (journalled)
    safety         a clock jump of a day does not trip the laptop watchdog and switches no relay
    HTTP           POST /time (token, 400 on a bad time), /state shows time_settable
    laptop client  syncs once per connection, again after a lost link; an old bridge (404) is logged, not fatal;
                   simulator mode: the simulated Pi starts an hour behind and is corrected
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "raspberry"))

from bioreactor_pi import config as pi_config  # noqa: E402
from bioreactor_pi.bridge import Bridge  # noqa: E402
from bioreactor_pi.clock import SystemClock, VirtualClock, default_clock  # noqa: E402
from bioreactor_pi.journal import Journal  # noqa: E402
from bioreactor_pi.server import PiServer  # noqa: E402
from bioreactor_pi.virtual_arduino import VirtualSerial  # noqa: E402

from src.hardware.client import ReactorClient  # noqa: E402

HOUR = 3600.0


@pytest.fixture
def config():
    c = pi_config.load(None)
    c["simulator"]["mq_warmup_s"] = 0
    return c


def make_bridge(config, tmp_path, time_source=None, **kw):
    return Bridge(config, VirtualSerial(config), Journal(tmp_path / "pi.sqlite3"), simulated=True,
                  time_source=time_source, **kw)


@pytest.fixture
def pi(config, tmp_path):
    """A running simulated Pi whose clock is one hour behind."""
    clock = VirtualClock(-HOUR)
    bridge = make_bridge(config, tmp_path, clock)
    server = PiServer(bridge, "127.0.0.1", 0, token="secret")
    bridge.start()
    server.start()
    deadline = time.time() + 5
    while time.time() < deadline and not bridge.state()["arduino_link"]["ok"]:
        time.sleep(0.1)
    yield bridge, clock, f"http://127.0.0.1:{server.port}"
    server.stop()
    bridge.stop()


def post(url, body, token="secret"):
    request = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json", "X-Bioreactor-Token": token})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


# ================================================================== clock
def test_virtual_clock_never_touches_the_computer_clock():
    before = time.time()
    clock = VirtualClock(-HOUR)
    assert abs(clock.now() - (before - HOUR)) < 1
    clock.set(time.time() + 10)
    assert abs(clock.now() - time.time() - 10) < 1 and abs(time.time() - before) < 5


def test_default_clock_is_real_only_on_linux(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    assert isinstance(default_clock(False), VirtualClock)
    monkeypatch.setattr(sys, "platform", "linux")
    assert isinstance(default_clock(False), SystemClock)
    assert isinstance(default_clock(True), VirtualClock)


# ================================================================== bridge
def test_set_time_moves_a_late_clock_and_the_stamps_with_it(config, tmp_path):
    clock = VirtualClock(-HOUR)
    bridge = make_bridge(config, tmp_path, clock)
    bridge.history.append({"t": round(clock.now(), 1), "temp_c": 36.0})
    bridge.alarm_since["warmup"] = clock.now()
    result = bridge.set_time(time.time(), who="laptop")
    assert result["ok"] and result["changed"] and abs(result["offset_s"] - HOUR) < 2
    assert abs(clock.now() - time.time()) < 1
    assert abs(bridge.history[-1]["t"] - time.time()) < 2           # measured now, now stamped now
    assert abs(bridge.alarm_since["warmup"] - time.time()) < 2
    assert bridge.state()["time_set_at"] is not None and bridge.state()["time_settable"]
    assert bridge.journal.recent(5)[0]["what"] == "time_set"
    bridge.journal.close()


def test_set_time_within_5_s_changes_nothing(config, tmp_path):
    clock = VirtualClock(-3)
    bridge = make_bridge(config, tmp_path, clock)
    result = bridge.set_time(time.time())
    assert result["ok"] and not result["changed"] and abs(clock.offset_s + 3) < 0.01
    bridge.journal.close()


@pytest.mark.parametrize("epoch", [0, -5, 1e12, "2026-11-22", None, True])
def test_set_time_refuses_a_broken_laptop_time(config, tmp_path, epoch):
    clock = VirtualClock(-HOUR)
    bridge = make_bridge(config, tmp_path, clock)
    assert bridge.set_time(epoch)["reason"] == "bad_time" and clock.offset_s == -HOUR
    bridge.journal.close()


def test_set_time_without_a_settable_clock_or_permission(config, tmp_path):
    bridge = make_bridge(config, tmp_path, None, wall=lambda: time.time() - HOUR)
    assert bridge.set_time(time.time())["reason"] == "not_supported"
    assert bridge.state()["time_settable"] is False
    bridge.journal.close()

    class NoCapability(VirtualClock):
        def set(self, epoch):
            raise PermissionError("Operation not permitted")

    bridge = make_bridge(config, tmp_path, NoCapability(-HOUR))
    assert bridge.set_time(time.time())["reason"] == "no_permission"
    assert bridge.journal.recent(1)[0]["result"] == "no_permission"
    bridge.journal.close()


def test_a_clock_jump_does_not_trip_the_watchdog_or_switch_relays(pi):
    bridge, clock, url = pi
    bridge.last_laptop = bridge.clock()
    relays = dict(bridge.relays)
    assert bridge.set_time(time.time() + 24 * HOUR)["changed"]       # a whole day forward
    time.sleep(0.5)
    state = bridge.state()
    assert state["laptop_watchdog"]["ok"] and state["laptop_watchdog"]["seconds_since_laptop"] < 2
    assert bridge.relays == relays
    assert not any(a["code"] == "laptop_lost" for a in state["alarms"])


# ================================================================== HTTP
def test_post_time_over_http(pi):
    bridge, clock, url = pi
    assert post(url + "/time", {"epoch": time.time()}, token="wrong")[0] == 401
    assert post(url + "/time", {"epoch": "now"})[0] == 400
    status, answer = post(url + "/time", {"epoch": time.time()})
    assert status == 200 and answer["changed"] and abs(clock.now() - time.time()) < 1


# ================================================================== laptop client
def client_for(url, **extra):
    return ReactorClient({"mode": "pi", "pi_url": url, "token": "secret", "poll_s": 1, "link_timeout_s": 5,
                          "request_timeout_s": 2, **extra})


def test_client_syncs_once_per_connection_and_again_after_a_lost_link(pi, tmp_path):
    bridge, clock, url = pi
    log = tmp_path / "client.log"
    client = client_for(url, client_log=str(log))
    client.poll()
    sync = client.status()["time_sync"]
    assert sync["checked"] and sync["changed"] and abs(sync["offset_s"] + HOUR) < 2 and sync["error"] is None
    assert abs(clock.now() - time.time()) < 1
    assert "set to the laptop's time" in log.read_text(encoding="utf-8")
    calls = []
    original = client._request
    client._request = lambda method, path, *a, **k: (calls.append(path), original(method, path, *a, **k))[1]
    clock.set(time.time() - 600)                 # drifts again: no second POST while the link stays
    client.poll()
    assert "/time" not in calls
    client.network_cut = True                    # link lost ...
    client.poll()
    client.network_cut = False                   # ... and back: checked again
    client.poll()
    assert "/time" in calls and abs(clock.now() - time.time()) < 1


def test_client_with_a_small_offset_sends_nothing(pi):
    bridge, clock, url = pi
    clock.set(time.time() + 2)
    client = client_for(url)
    client.poll()
    sync = client.status()["time_sync"]
    assert sync["checked"] and not sync["changed"] and abs(sync["offset_s"] - 2) < 1


def test_client_and_a_bridge_without_post_time(pi, monkeypatch):
    """A bridge deployed before POST /time answers 404: logged in time_sync, the reactor link stays fine."""
    from src.hardware.client import PiUnreachable
    bridge, clock, url = pi
    client = client_for(url)
    original = client._request

    def old_bridge(method, path, *a, **k):
        if path == "/time":
            raise PiUnreachable("HTTP 404: not found")
        return original(method, path, *a, **k)

    monkeypatch.setattr(client, "_request", old_bridge)
    client.poll()
    status = client.status()
    assert status["link"]["ok"] and status["controls_enabled"]
    assert "404" in status["time_sync"]["error"] and not status["time_sync"]["changed"] and clock.offset_s == -HOUR


def test_client_time_sync_can_be_switched_off(pi):
    bridge, clock, url = pi
    client = client_for(url, time_sync=False)
    client.poll()
    assert client.status()["time_sync"]["error"] == "off" and clock.offset_s == -HOUR


def test_simulator_pi_an_hour_behind_is_corrected_without_touching_the_laptop(tmp_path):
    laptop_before = time.time()
    client = ReactorClient({"mode": "simulator", "pi_url": "http://unused", "poll_s": 0.2, "link_timeout_s": 1.5,
                            "request_timeout_s": 1, "simulator_pi_offset_s": -HOUR}, journal_path=tmp_path / "sim.sqlite3")
    client.start()
    try:
        deadline = time.time() + 6
        while time.time() < deadline and not client.status()["time_sync"]["checked"]:
            time.sleep(0.1)
        sync = client.status()["time_sync"]
        assert sync["changed"] and abs(sync["offset_s"] + HOUR) < 2
        assert abs(client.sim[0].time_source.now() - time.time()) < 1
        assert abs(time.time() - laptop_before) < 30                 # the laptop's own clock was not moved
    finally:
        client.stop()
