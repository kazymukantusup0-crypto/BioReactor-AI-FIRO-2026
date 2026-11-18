"""Bridge: the Pi's core. One background thread talks to the Arduino; the HTTP server (server.py) calls the methods.

    every line from the Arduino   state -> readings, relays, history, journal; Pi protection checked
    every 2 s                      ping -> the Arduino's 10 s watchdog stays quiet
    no state for arduino_timeout_s «НЕТ СВЯЗИ С ARDUINO»: every command is refused
    port lost / cable pulled       reopen every 3 s (the Arduino resets on open: all relays OFF)
    laptop silent > laptop_timeout_s   all_off to the Arduino (second protection), once per silence

Automatic actions only switch relays OFF. Switching ON is only command(..., who="operator").
"""
from __future__ import annotations

import json
import threading
import time
from collections import deque
from collections.abc import Callable

from . import protocol, safety
from .journal import Journal
from .serial_link import LinkError

RECONNECT_S = 3.0
HISTORY_POINTS = 4000
VERSION = "0.1"


class Bridge:
    def __init__(self, config: dict, link, journal: Journal, *, simulated: bool = False,
                 clock: Callable[[], float] = time.monotonic, wall: Callable[[], float] = time.time):
        self.config = config
        self.th = config["thresholds"]
        self.link = link
        self.journal = journal
        self.simulated = simulated
        self.clock = clock
        self.wall = wall
        self._io = threading.RLock()
        self._state = threading.RLock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._next_id = 1
        self.connected = False
        self.connect_error: str | None = None
        self._last_connect_try = -1e9
        self._last_ping = -1e9
        self._last_reading_log = -1e9
        self.last_state: float | None = None
        self.arduino_ok = False
        self._arduino_was_ok: bool | None = None
        self.readings = {name: None for name in protocol.SENSORS}
        self.relays = {name: False for name in protocol.RELAYS}
        self.arduino_alarms = {name: False for name in protocol.ALARMS}
        self.firmware: str | None = None
        self.leak_latched = False
        self.leak_since: float | None = None
        self.overheat = False
        self.pressure_danger = False
        self.on_since = {name: None for name in protocol.RELAYS}
        self.total_on_s = {name: 0.0 for name in protocol.RELAYS}
        self.history: deque = deque(maxlen=HISTORY_POINTS)
        self.last_laptop: float = clock()
        self.laptop_ok = True
        self._actions: list[tuple[str, str, str]] = []
        self.bad_lines = 0

    # -- naming -----------------------------------------------------------------------
    @property
    def source(self) -> str:
        return "virtual" if self.simulated else f"arduino {self.link.port or '?'}"

    def _id(self) -> int:
        self._next_id += 1
        return self._next_id

    def _log(self, kind: str, what: str, who: str, result: str | None = None, details: dict | None = None) -> None:
        self.journal.add(kind, what, who, self.source, result, details)

    # -- connection -------------------------------------------------------------------
    def connect(self) -> bool:
        now = self.clock()
        if self.connected or now - self._last_connect_try < RECONNECT_S:
            return self.connected
        self._last_connect_try = now
        try:
            self.link.open()
        except LinkError as error:
            if self.connect_error != str(error):
                self._log("link", "usb_connect_failed", "system", str(error))
            self.connect_error = str(error)
            return False
        self.connected, self.connect_error = True, None
        self._log("link", "usb_open", "system", self.link.port)
        return True

    def _drop(self, error: str) -> None:
        self.link.close()
        self.connected = False
        self.connect_error = error
        self._last_connect_try = self.clock()
        with self._state:
            # Unknown now; the Arduino switches everything off by itself (watchdog / reset on reconnect).
            self._set_relays({name: False for name in protocol.RELAYS})
        self._log("link", "usb_lost", "system", error)

    # -- processing ---------------------------------------------------------------------
    def _set_relays(self, relays: dict) -> None:
        now = self.clock()
        for name, on in relays.items():
            was = self.relays[name]
            if on and not was:
                self.on_since[name] = now
            elif was and not on and self.on_since[name] is not None:
                self.total_on_s[name] += now - self.on_since[name]
                self.on_since[name] = None
            self.relays[name] = on

    def _want_off(self, relay: str, reason: str, who: str = "pi_safety") -> None:
        if self.relays.get(relay) and not any(a[0] == relay for a in self._actions):
            self._actions.append((relay, reason, who))

    def process(self, line: bytes) -> dict | None:
        try:
            message = protocol.parse_line(line)
        except protocol.ProtocolError:
            self.bad_lines += 1
            return None
        with self._state:
            if message["type"] == "state":
                self._on_state(message)
            elif message["type"] == "ack" and message.get("relays"):
                self._set_relays(message["relays"])
            elif message["type"] == "event":
                self._log("safety", message["code"], "arduino_safety")
            elif message["type"] == "boot":
                self.firmware = message["fw"]
                self._set_relays({name: False for name in protocol.RELAYS})
                self._log("system", "arduino_boot", "arduino", f"fw {message['fw']}")
        return message

    def _on_state(self, state: dict) -> None:
        self.last_state = self.clock()
        for name in protocol.SENSORS:
            self.readings[name] = state[name]
        self._set_relays(state["relays"])
        self.arduino_alarms = state["alarms"]
        self.history.append({"t": round(self.wall(), 1), **{name: state[name] for name in protocol.SENSORS},
                             **{f"relay_{k}": int(v) for k, v in state["relays"].items()}})
        if self.clock() - self._last_reading_log >= self.config["reading_log_every_s"]:
            self._last_reading_log = self.clock()
            self.journal.reading(state, state["relays"], self.source)
        if not self.arduino_ok:
            self._arduino_link(True)
        # Leak outside: heater OFF, alarm latched until a PERSON resets it.
        if (safety.is_leak(state["gas_out"], self.th) or state["alarms"]["leak"]) and not self.leak_latched:
            self.leak_latched, self.leak_since = True, self.wall()
            self._log("alarm", "leak", "pi_safety", "heater_off_and_locked",
                      {"gas_out": state["gas_out"], "threshold": self.th["gas_out_raw"]["leak"]})
        if self.leak_latched:
            self._want_off("heat", "leak")
        overheat = safety.is_overheat(state["temp_c"], self.th, self.overheat) or state["alarms"]["overheat"]
        if overheat and not self.overheat:
            self._log("alarm", "overheat", "pi_safety", "heater_off", {"temp_c": state["temp_c"], "threshold": self.th["overheat_c"]})
        elif self.overheat and not overheat:
            self._log("alarm", "overheat_cleared", "pi_safety", None, {"temp_c": state["temp_c"]})
        self.overheat = overheat
        if overheat:
            self._want_off("heat", "overheat")
        if state["temp_c"] is None:
            self._want_off("heat", "temp_sensor")
        danger = safety.level("p_kpa", state["p_kpa"], self.th) == "danger"
        if danger and not self.pressure_danger:
            self._log("alarm", "pressure_high", "pi_safety", "pump_needed",
                      {"p_kpa": state["p_kpa"], "threshold": self.th["pressure_kpa"]["danger"]})
        self.pressure_danger = danger
        if state["p_kpa"] is not None and state["p_kpa"] <= self.th["pressure_kpa"]["pump_stop"]:
            self._want_off("pump", "pressure_empty")

    def _arduino_link(self, ok: bool) -> None:
        self.arduino_ok = ok
        if self._arduino_was_ok is None and ok:
            self._log("link", "arduino_ok", "system")
        elif self._arduino_was_ok is not None and ok != self._arduino_was_ok:
            self._log("link" if ok else "alarm", "arduino_restored" if ok else "arduino_lost", "system")
        self._arduino_was_ok = ok

    def check_links(self) -> None:
        now = self.clock()
        with self._state:
            fresh = self.connected and self.last_state is not None and now - self.last_state <= self.config["arduino_timeout_s"]
            if self.arduino_ok and not fresh:
                self._arduino_link(False)
            laptop_fresh = now - self.last_laptop <= self.config["laptop_timeout_s"]
            if self.laptop_ok and not laptop_fresh:
                self.laptop_ok = False
                self._log("alarm", "laptop_lost", "pi_safety", "all_off",
                          {"silent_s": round(now - self.last_laptop, 1), "limit_s": self.config["laptop_timeout_s"]})
                if self.connected:
                    self._actions.append(("*", "laptop_lost", "pi_safety"))
            elif not self.laptop_ok and laptop_fresh:
                self.laptop_ok = True
                self._log("link", "laptop_restored", "system")

    def laptop_seen(self) -> None:
        """Every request from the laptop (the dashboard polls /state every second)."""
        self.last_laptop = self.clock()

    # -- one cycle of the background thread -------------------------------------------------
    def poll_once(self, wait_s: float = 0.2) -> None:
        if not self.connected and not self.connect():
            self.check_links()
            if wait_s:
                time.sleep(wait_s)
            return
        with self._io:
            try:
                line = self.link.readline(wait_s)
                if line:
                    self.process(line)
                if self.clock() - self._last_ping >= self.config["ping_every_s"]:
                    self._last_ping = self.clock()
                    self.link.write(protocol.ping(self._id()))
            except LinkError as error:
                self._drop(str(error))
        self.check_links()
        self._run_actions()

    def _run_actions(self) -> None:
        actions, self._actions = self._actions, []
        for relay, reason, who in actions:
            if relay == "*":
                result = self._send(protocol.all_off(self._id()))
                self._log("safety", "all_off", who, "ok" if result["ok"] else result["reason"], {"reason": reason})
            elif self.relays.get(relay):
                result = self._send(protocol.relay(self._id(), relay, False))
                self._log("safety", f"{relay}_off", who, "ok" if result["ok"] else result["reason"], {"reason": reason})

    def _send(self, data: bytes) -> dict:
        """Write one command and wait for its ack (other lines are processed meanwhile)."""
        identifier = json.loads(data)["id"]
        deadline = self.clock() + self.config["ack_timeout_s"]
        started = time.monotonic()
        with self._io:
            try:
                self.link.write(data)
                # Real time AND the bridge clock: a test clock that does not move still ends the wait.
                while self.clock() < deadline and time.monotonic() - started < self.config["ack_timeout_s"]:
                    line = self.link.readline(0.05)
                    if not line:
                        continue
                    message = self.process(line)
                    if message and message["type"] == "ack" and message["id"] == identifier:
                        return {"ok": message["ok"], "reason": message.get("reason")}
            except LinkError as error:
                self._drop(str(error))
                return {"ok": False, "reason": "no_link"}
        return {"ok": False, "reason": "no_ack"}

    # -- what a person can do (through the laptop) ----------------------------------------------
    def command(self, name: str, on: bool, who: str = "operator") -> dict:
        self.check_links()
        with self._state:
            reason = safety.refuse_reason(name, on, link_ok=self.arduino_ok, relays=dict(self.relays),
                                          leak_latched=self.leak_latched, overheat=self.overheat,
                                          temp_known=self.readings["temp_c"] is not None,
                                          warmup=self.arduino_alarms.get("warmup", False))
        what = f"{name}_{'on' if on else 'off'}"
        if reason:
            self._log("command", what, who, f"refused:{reason}")
            return {"ok": False, "reason": reason, "relays": dict(self.relays)}
        result = self._send(protocol.relay(self._id(), name, on))
        self._log("command", what, who, "ok" if result["ok"] else f"arduino:{result['reason']}")
        return {"ok": result["ok"], "reason": None if result["ok"] else result["reason"], "relays": dict(self.relays)}

    def reset_leak(self, who: str = "operator") -> dict:
        self.check_links()
        with self._state:
            if not self.leak_latched:
                return {"ok": True, "reason": None}
            if not self.arduino_ok:
                self._log("command", "leak_reset", who, "refused:no_link")
                return {"ok": False, "reason": "no_link"}
            if safety.is_leak(self.readings["gas_out"], self.th):
                self._log("command", "leak_reset", who, "refused:still_leaking")
                return {"ok": False, "reason": "still_leaking"}
        result = self._send(protocol.reset(self._id()))
        if not result["ok"]:
            self._log("command", "leak_reset", who, f"arduino:{result['reason']}")
            return {"ok": False, "reason": result["reason"]}
        with self._state:
            self.leak_latched, self.leak_since = False, None
        self._log("command", "leak_reset", who, "ok")
        return {"ok": True, "reason": None}

    def simulate(self, what: str, on: bool, who: str = "operator") -> dict:
        """Simulator buttons (only with the virtual Arduino): leak, broken USB cable, frozen Arduino, broken sensor."""
        if not self.simulated:
            return {"ok": False, "reason": "not_simulator"}
        if what == "leak":
            self.link.arduino.leak_on = on
        elif what == "usb":
            self.link.unplugged = on
        elif what == "arduino_silent":
            self.link.silent = on
        elif what == "temp_sensor":
            self.link.arduino.temp_sensor_broken = on
        else:
            return {"ok": False, "reason": "unknown"}
        self._log("system", f"simulate_{what}_{'on' if on else 'off'}", who, "ok")
        return {"ok": True, "reason": None}

    # -- reading --------------------------------------------------------------------------------
    def state(self) -> dict:
        self.check_links()
        now = self.clock()
        with self._state:
            ok = self.arduino_ok
            readings = {name: {"value": value if ok else None, "last": value,
                               "level": safety.level(name, value, self.th) if ok else "unknown"}
                        for name, value in self.readings.items()}
            p = self.readings["p_kpa"]
            readings["p_kpa"]["fill_share"] = (None if p is None or not ok
                                               else round(min(1.0, max(0.0, p / self.th["pressure_kpa"]["scale_max"])), 3))
            relays = {}
            for name in protocol.RELAYS:
                running = now - self.on_since[name] if self.on_since[name] is not None else 0
                relays[name] = {"on": self.relays[name], "on_for_s": round(running),
                                "total_s": round(self.total_on_s[name] + running),
                                "on_blocked": safety.refuse_reason(
                                    name, True, link_ok=ok, relays=dict(self.relays), leak_latched=self.leak_latched,
                                    overheat=self.overheat, temp_known=self.readings["temp_c"] is not None,
                                    warmup=self.arduino_alarms.get("warmup", False))}
            alarms = []
            if not ok:
                alarms.append({"code": "arduino_lost", "level": "danger", "error": self.connect_error})
            if self.leak_latched:
                alarms.append({"code": "leak", "level": "danger", "since": self.leak_since, "needs_reset": True,
                               "still_leaking": safety.is_leak(self.readings["gas_out"], self.th)})
            if self.overheat:
                alarms.append({"code": "overheat", "level": "danger"})
            if ok and self.readings["temp_c"] is None:
                alarms.append({"code": "temp_sensor", "level": "danger"})
            if ok and self.pressure_danger:
                alarms.append({"code": "pressure_high", "level": "danger"})
            if ok and self.arduino_alarms.get("warmup"):
                alarms.append({"code": "warmup", "level": "warn"})
            if not self.laptop_ok:
                alarms.append({"code": "laptop_lost", "level": "danger"})
            return {
                "bridge": {"version": VERSION, "simulated": self.simulated, "port": self.link.port,
                           "firmware": self.firmware},
                "arduino_link": {"ok": ok, "connected": self.connected, "error": self.connect_error,
                                 "seconds_since_data": None if self.last_state is None else round(now - self.last_state, 1)},
                "laptop_watchdog": {"timeout_s": self.config["laptop_timeout_s"],
                                    "seconds_since_laptop": round(now - self.last_laptop, 1), "ok": self.laptop_ok},
                "readings": readings,
                "relays": relays,
                "alarms": alarms,
                "leak_latched": self.leak_latched,
                "overheat": self.overheat,
                "arduino_alarms": dict(self.arduino_alarms),
                "thresholds": self.th,
                "simulator": ({"leak": self.link.arduino.leak_on, "usb": self.link.unplugged,
                               "arduino_silent": self.link.silent, "temp_sensor": self.link.arduino.temp_sensor_broken}
                              if self.simulated else None),
                "time": round(self.wall(), 1),
            }

    def history_window(self, window_s: int) -> list[dict]:
        cutoff = self.wall() - window_s
        with self._state:
            points = [p for p in self.history if p["t"] >= cutoff]
        stride = max(1, len(points) // 400)
        return points[::stride]

    # -- thread -----------------------------------------------------------------------------------
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self.last_laptop = self.clock()
        self._thread = threading.Thread(target=self._loop, name="bioreactor-bridge", daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.poll_once(0.2)
            except Exception as error:  # the thread must never die silently
                self._log("system", "loop_error", "system", type(error).__name__, {"error": str(error)[:200]})
                time.sleep(0.5)

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)
        if self.connected:
            try:
                self._send(protocol.all_off(self._id()))
                self._log("system", "all_off_on_exit", "system", "ok")
            except Exception:
                pass
        self.link.close()
