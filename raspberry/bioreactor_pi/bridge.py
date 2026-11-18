"""Bridge: the Pi's core. One background thread talks to the Arduino; the HTTP server (server.py) calls the methods.

    port opened                    the Arduino resets (DTR) -> wait for {"type":"boot"} (boot_timeout_s); commands
                                   and pings start only after it («Arduino starting»)
    every status line (1 s)        readings, relays, who switched them (remote), AUTO, the EEPROM limits, alarms
    every 2 s                      PING -> the Arduino's 10 s link watchdog stays quiet
    no status for arduino_timeout_s  «НЕТ СВЯЗИ С ARDUINO»: every command is refused
    port lost / cable pulled       reopen every 3 s
    laptop silent > laptop_timeout_s   switch OFF only the relays that were switched ON from the Pi (remote = true).
                                   NOT ALLOFF: that would also stop the Arduino's own AUTO regime (thermostat, pump).

The Arduino has the last word on every command (its ack); the Pi checks first only to give a clear reason.
Automatic actions of the Pi only switch relays OFF.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable

from . import protocol, safety
from .journal import Journal
from .serial_link import LinkError

RECONNECT_S = 3.0
HISTORY_POINTS = 4000
VERSION = "1.0"
AUGER_TIMEOUT_SHOW_S = 300   # the Arduino reports auger_timeout in ONE status; the Pi keeps showing it 5 min


class Bridge:
    def __init__(self, config: dict, link, journal: Journal, *, simulated: bool = False,
                 clock: Callable[[], float] = time.monotonic, wall: Callable[[], float] = time.time):
        self.config = config
        self.link = link
        self.journal = journal
        self.simulated = simulated
        self.clock = clock
        self.wall = wall
        self._io = threading.RLock()
        self._state = threading.RLock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.connected = False
        self.connect_error: str | None = None
        self._last_connect_try = -1e9
        self._last_ping = -1e9
        self._last_reading_log = -1e9
        self.opened_at: float | None = None
        self.booted = False
        self.last_status: float | None = None
        self.arduino_ok = False
        self._arduino_was_ok: bool | None = None
        self.readings = {name: None for name in protocol.SENSORS}
        self.relays = {name: False for name in protocol.RELAYS}
        self.remote = {name: False for name in protocol.RELAYS}
        self.auto = False
        self.limits: dict | None = None
        self.alarms = {name: False for name in protocol.ALARMS}
        self.alarm_since: dict[str, float] = {}
        self.auger_timeout_at: float | None = None
        self.firmware: str | None = None
        self.uptime_s: int | None = None
        self.on_since = {name: None for name in protocol.RELAYS}
        self.total_on_s = {name: 0.0 for name in protocol.RELAYS}
        self.history: deque = deque(maxlen=HISTORY_POINTS)
        self.last_laptop: float = clock()
        self.laptop_ok = True
        self._remote_off_pending: list[str] = []
        self.bad_lines = 0

    # -- naming -----------------------------------------------------------------------
    @property
    def source(self) -> str:
        return "virtual" if self.simulated else f"arduino {self.link.port or '?'}"

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
        self.opened_at, self.booted = now, False
        self._log("link", "usb_open", "system", self.link.port)
        return True

    def _drop(self, error: str) -> None:
        self.link.close()
        self.connected = False
        self.booted = False
        self.connect_error = error
        self._last_connect_try = self.clock()
        with self._state:
            # Unknown now. The Arduino switches off what the Pi switched on after 10 s without PING; its AUTO regime
            # keeps running on its own.
            self._set_relays({name: False for name in protocol.RELAYS})
            self.remote = {name: False for name in protocol.RELAYS}
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

    def process(self, line: bytes) -> dict | None:
        try:
            message = protocol.parse_line(line)
        except protocol.ProtocolError:
            self.bad_lines += 1
            return None
        with self._state:
            if message["type"] == "status":
                self._on_status(message)
            elif message["type"] == "boot":
                self.firmware = message["fw"]
                self.booted = True
                self._set_relays({name: False for name in protocol.RELAYS})
                self.remote = {name: False for name in protocol.RELAYS}
                self._last_ping = -1e9   # ping at once: the Arduino's link timer starts now
                self._log("system", "arduino_boot", "arduino", f"fw {message['fw']}")
        return message

    def _on_status(self, status: dict) -> None:
        now = self.clock()
        if not self.booted:
            # A status before the boot line: the port was opened without a reset, or the boot line was lost.
            waited = now - (self.opened_at if self.opened_at is not None else now)
            if waited < self.config["boot_timeout_s"]:
                return
            self.booted = True
            self.firmware = self.firmware or status["fw"]
            self._log("link", "no_boot_line", "system", f"status without boot after {round(waited, 1)} s")
        self.last_status = now
        self.firmware = status["fw"] or self.firmware
        self.uptime_s = status["uptime_s"]
        for name in protocol.SENSORS:
            self.readings[name] = status[name]
        self._set_relays(status["relays"])
        self.remote = status["remote"]
        if status["auto"] != self.auto and self.last_status is not None and self._arduino_was_ok is not None:
            self._log("system", f"auto_{'on' if status['auto'] else 'off'}", "arduino")
        self.auto = status["auto"]
        if self.limits is not None and status["limits"] != self.limits:
            self._log("system", "limits_changed", "arduino", None,
                      {k: v for k, v in status["limits"].items() if self.limits.get(k) != v})
        self.limits = status["limits"]
        self._on_alarms(status["alarms"], status)
        self.history.append({"t": round(self.wall(), 1), **{name: status[name] for name in protocol.SENSORS},
                             **{f"relay_{k}": int(v) for k, v in status["relays"].items()}})
        if now - self._last_reading_log >= self.config["reading_log_every_s"]:
            self._last_reading_log = now
            self.journal.reading(status, status["relays"], self.source)
        if not self.arduino_ok:
            self._arduino_link(True)

    def _on_alarms(self, alarms: dict, status: dict) -> None:
        if alarms["auger_timeout"]:
            self.auger_timeout_at = self.wall()
        for name, on in alarms.items():
            was = self.alarms.get(name, False)
            if on and not was:
                self.alarm_since[name] = self.wall()
                if name != "warmup" or self._arduino_was_ok is not None:
                    details = {"gas_out": status["gas_out"], "limit": status["limits"]["gas_out_limit"]} if name == "leak" else \
                        {"temp_c": status["temp_c"], "limit": status["limits"]["temp_hard_max"]} if name == "overheat" else None
                    self._log("alarm", name, "arduino_safety", None, details)
            elif was and not on:
                self.alarm_since.pop(name, None)
                if name not in ("warmup", "auger_timeout"):
                    self._log("alarm", f"{name}_cleared", "arduino_safety")
        self.alarms = dict(alarms)

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
            fresh = (self.connected and self.booted and self.last_status is not None
                     and now - self.last_status <= self.config["arduino_timeout_s"])
            if self.arduino_ok and not fresh:
                self._arduino_link(False)
            laptop_fresh = now - self.last_laptop <= self.config["laptop_timeout_s"]
            if self.laptop_ok and not laptop_fresh:
                self.laptop_ok = False
                remote_on = [name for name in protocol.RELAYS if self.remote[name] and self.relays[name]]
                self._log("alarm", "laptop_lost", "pi_safety", "remote_off" if remote_on else "nothing_remote",
                          {"silent_s": round(now - self.last_laptop, 1), "limit_s": self.config["laptop_timeout_s"],
                           "relays": remote_on, "auto": self.auto})
                if self.connected:
                    self._remote_off_pending = remote_on
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
                if self.booted and self.clock() - self._last_ping >= self.config["ping_every_s"]:
                    self._last_ping = self.clock()
                    self.link.write(protocol.ping())
            except LinkError as error:
                self._drop(str(error))
        self.check_links()
        self._run_remote_off()

    def _run_remote_off(self) -> None:
        pending, self._remote_off_pending = self._remote_off_pending, []
        for name in pending:
            if self.relays.get(name) and self.remote.get(name):
                result = self._send(protocol.relay(name, False))
                self._log("safety", f"{name}_off", "pi_safety", "ok" if result["ok"] else result["reason"],
                          {"reason": "laptop_lost"})

    def _send(self, data: bytes) -> dict:
        """Write one command and wait for its ack (status lines are processed meanwhile). One command at a time."""
        name = protocol.command_name(data)
        timeout = self.config["ack_timeout_s"]
        deadline = self.clock() + timeout
        started = time.monotonic()
        with self._io:
            try:
                self.link.write(data)
                # Real time AND the bridge clock: a test clock that does not move still ends the wait.
                while self.clock() < deadline and time.monotonic() - started < timeout:
                    line = self.link.readline(0.05)
                    if not line:
                        continue
                    message = self.process(line)
                    if message and message["type"] == "ack" and message["cmd"] == name:
                        return {"ok": message["ok"], "reason": None if message["ok"] else message["error"].lower()}
            except LinkError as error:
                self._drop(str(error))
                return {"ok": False, "reason": "no_link"}
        return {"ok": False, "reason": "no_ack"}

    def _refresh(self) -> None:
        """GET: the status right after a command, so the page shows the new state at once."""
        with self._io:
            try:
                self.link.write(protocol.get())
                started = time.monotonic()
                while time.monotonic() - started < 1.0:
                    line = self.link.readline(0.05)
                    if line and (message := self.process(line)) and message["type"] == "status":
                        return
            except LinkError as error:
                self._drop(str(error))

    def _ready(self) -> str | None:
        self.check_links()
        if not self.connected:
            return "no_link"
        if not self.booted:
            return "arduino_starting"
        return None if self.arduino_ok else "no_link"

    def _person(self, what: str, who: str, data: bytes, details: dict | None = None) -> dict:
        result = self._send(data)
        self._log("command", what, who, "ok" if result["ok"] else f"arduino:{result['reason']}", details)
        if result["ok"] or result["reason"] != "no_link":
            self._refresh()
        return {**result, "relays": dict(self.relays), "auto": self.auto}

    # -- what a person can do (through the laptop) ----------------------------------------------
    def command(self, name: str, on: bool, who: str = "operator") -> dict:
        not_ready = self._ready()
        with self._state:
            reason = not_ready or safety.refuse_reason(name, on, link_ok=True, relays=dict(self.relays), alarms=self.alarms)
        what = f"{name}_{'on' if on else 'off'}"
        if reason:
            self._log("command", what, who, f"refused:{reason}")
            return {"ok": False, "reason": reason, "relays": dict(self.relays), "auto": self.auto}
        return self._person(what, who, protocol.relay(name, on))

    def set_auto(self, on: bool, who: str = "operator") -> dict:
        reason = self._ready() or (("estop" if self.alarms["estop"] else "leak") if on and (self.alarms["estop"] or self.alarms["leak"]) else None)
        if reason:
            self._log("command", f"auto_{'on' if on else 'off'}", who, f"refused:{reason}")
            return {"ok": False, "reason": reason, "relays": dict(self.relays), "auto": self.auto}
        return self._person(f"auto_{'on' if on else 'off'}", who, protocol.auto(on))

    def set_limit(self, name: str, value: float, who: str = "operator") -> dict:
        reason = self._ready()
        if not reason and name not in protocol.LIMITS:
            reason = "bad_key"
        if not reason and self.limits is not None:
            new = {**self.limits, name: int(round(value)) if name in protocol.GAS_LIMITS else round(value, 1)}
            reason = "out_of_range" if protocol.limits_error(new) else None
        details = {"limit": name, "value": value, "was": (self.limits or {}).get(name)}
        if reason:
            self._log("command", "set_limit", who, f"refused:{reason}", details)
            return {"ok": False, "reason": reason, "limits": self.limits}
        result = self._person("set_limit", who, protocol.set_limit(name, value), details)
        return {**result, "limits": self.limits}

    def estop(self, who: str = "operator") -> dict:
        """Emergency stop: sent whenever the port is open — even when the status is late."""
        self.check_links()
        if not self.connected:
            self._log("command", "estop", who, "refused:no_link")
            return {"ok": False, "reason": "no_link", "relays": dict(self.relays), "auto": self.auto}
        return self._person("estop", who, protocol.estop())

    def reset_alarms(self, who: str = "operator") -> dict:
        """A person clears E-STOP / leak / link_lost on the Arduino. The leak stays while the gas outside is high."""
        reason = self._ready()
        if reason:
            self._log("command", "reset", who, f"refused:{reason}")
            return {"ok": False, "reason": reason}
        return self._person("reset", who, protocol.reset())

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
                               "level": safety.level(name, value, self.limits) if ok else "unknown"}
                        for name, value in self.readings.items()}
            relays = {}
            for name in protocol.RELAYS:
                running = now - self.on_since[name] if self.on_since[name] is not None else 0
                relays[name] = {"on": self.relays[name], "remote": self.remote[name], "on_for_s": round(running),
                                "total_s": round(self.total_on_s[name] + running),
                                "on_blocked": safety.refuse_reason(name, True, link_ok=ok, relays=dict(self.relays),
                                                                   alarms=self.alarms)}
            alarms = []
            if not ok:
                alarms.append({"code": "arduino_starting" if self.connected and not self.booted else "arduino_lost",
                               "level": "danger", "error": self.connect_error})
            if ok:
                for name in ("estop", "leak", "overheat", "no_temp", "link_lost", "warmup"):
                    if self.alarms[name]:
                        alarm = {"code": name, "level": "warn" if name == "warmup" else "danger",
                                 "since": self.alarm_since.get(name)}
                        if name in ("estop", "leak", "link_lost"):
                            alarm["needs_reset"] = True
                        if name == "leak" and self.limits and self.readings["gas_out"] is not None:
                            alarm["still_leaking"] = self.readings["gas_out"] >= self.limits["gas_out_limit"]
                        alarms.append(alarm)
            if self.auger_timeout_at is not None and self.wall() - self.auger_timeout_at <= AUGER_TIMEOUT_SHOW_S:
                alarms.append({"code": "auger_timeout", "level": "warn", "since": self.auger_timeout_at})
            if not self.laptop_ok:
                alarms.append({"code": "laptop_lost", "level": "danger"})
            return {
                "bridge": {"version": VERSION, "simulated": self.simulated, "port": self.link.port,
                           "firmware": self.firmware},
                "arduino_link": {"ok": ok, "connected": self.connected, "booted": self.booted, "error": self.connect_error,
                                 "seconds_since_data": None if self.last_status is None else round(now - self.last_status, 1),
                                 "uptime_s": self.uptime_s},
                "laptop_watchdog": {"timeout_s": self.config["laptop_timeout_s"],
                                    "seconds_since_laptop": round(now - self.last_laptop, 1), "ok": self.laptop_ok},
                "readings": readings,
                "relays": relays,
                "auto": self.auto,
                "limits": self.limits,
                "alarms": alarms,
                "arduino_alarms": dict(self.alarms),
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
        """Service stop: switch OFF what the Pi switched ON (not ALLOFF — the Arduino's AUTO regime keeps running)."""
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)
        if self.connected:
            try:
                for name in [n for n in protocol.RELAYS if self.remote[n] and self.relays[n]]:
                    result = self._send(protocol.relay(name, False))
                    self._log("safety", f"{name}_off", "pi_safety", "ok" if result["ok"] else result["reason"],
                              {"reason": "bridge_stop"})
            except Exception:
                pass
        self.link.close()
        # Release the SQLite file (Windows cannot delete an open file: a test's temporary folder, a USB backup).
        self.journal.close()
