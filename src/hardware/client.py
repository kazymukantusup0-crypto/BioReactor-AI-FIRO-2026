"""Laptop -> Raspberry Pi: a background thread polls GET /state every second (this also feeds the Pi's 15 s laptop
watchdog). Commands go to POST /relay. Two places where the link can break, both shown on the page:

    laptop -X- Pi       no answer for link_timeout_s   -> link.level "pi"       «НЕТ СВЯЗИ С RASPBERRY PI»
    Pi -X- Arduino      the Pi reports arduino_link.ok = false -> link.level "arduino"  «НЕТ СВЯЗИ С ARDUINO»
Either way: values are not shown as current, every button is disabled and every command is refused (E-STOP is still
sent while the Pi answers and its USB port is open).

Mode "auto": the Pi is looked for at each address of pi_candidates in turn (Wi-Fi of the Pi 10.42.0.1, the direct cable
192.168.50.2, bioreactor.local in a shared network); the first that answers /health is used until it stops answering,
then the search starts again. The page shows the route: «Wi-Fi Pi», «кабель», «общая сеть». Mode "pi": one fixed pi_url.

Mode "simulator": the SAME Pi bridge code (raspberry/bioreactor_pi) with the virtual Arduino runs inside this
server on 127.0.0.1 and this client talks to it over HTTP — the whole chain works without hardware, and the page
always says СИМУЛЯТОР. The «оборвать сеть» simulator button stops this client's requests, so the Pi's own
laptop watchdog can be shown (after 15 s it switches off the relays that were switched on from the Pi).
"""
from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime
from pathlib import Path
import urllib.error
import urllib.request
from collections.abc import Callable
from urllib.parse import urlsplit

RELAYS = ("heat", "cool", "pump", "auger")
SENSORS = ("temp_c", "rh_pct", "gas_in", "gas_out")


class PiUnreachable(OSError):
    pass


class ReactorClient:
    def __init__(self, config: dict, *, journal_path=None, clock: Callable[[], float] = time.monotonic):
        self.config = config
        self.mode = config["mode"]
        self.clock = clock
        self.token = config.get("token") or ""
        self.timeout = float(config.get("request_timeout_s", 2.5))
        self.network_cut = False          # simulator button: «оборвать сеть ноутбук ↔ Pi»
        self.sim = None                   # (bridge, server) of the in-process simulated Pi
        self._journal_path = journal_path
        self.pi_url = config["pi_url"].rstrip("/")
        self.candidates = [dict(c, url=c["url"].rstrip("/")) for c in config.get("pi_candidates", [])]
        if self.mode == "auto" and self.candidates:
            self.pi_url = self.candidates[0]["url"]
        self.searching = False
        self.route_seen: str | None = None
        self._last_not_found_log = -1e9
        self.last_state: dict | None = None
        self.last_ok: float | None = None
        self.error: str | None = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._history_cache: dict[int, list] = {}

    # -- simulator --------------------------------------------------------------------------
    def _start_simulator(self) -> None:
        from src.hardware.config import ROOT, pi_package
        pi_package()
        from bioreactor_pi import config as pi_config
        from bioreactor_pi.bridge import Bridge
        from bioreactor_pi.journal import Journal
        from bioreactor_pi.server import PiServer
        from bioreactor_pi.virtual_arduino import VirtualSerial
        config = pi_config.load()
        journal = Journal(self._journal_path or ROOT / "data/runtime/reactor_simulator_journal.sqlite3")
        bridge = Bridge(config, VirtualSerial(config), journal, simulated=True)
        server = PiServer(bridge, "127.0.0.1", 0)
        bridge.start()
        server.start()
        self.sim = (bridge, server)
        self.pi_url = f"http://127.0.0.1:{server.port}"

    # -- HTTP ----------------------------------------------------------------------------------
    def _request(self, method: str, path: str, body: dict | None = None, timeout: float | None = None) -> dict:
        if self.network_cut:
            raise PiUnreachable("network cut (simulator)")
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(self.pi_url + path, data=data, method=method,
                                         headers={"Content-Type": "application/json",
                                                  **({"X-Bioreactor-Token": self.token} if self.token else {})})
        try:
            with urllib.request.urlopen(request, timeout=timeout or self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            try:
                detail = json.loads(error.read().decode("utf-8")).get("error")
            except Exception:
                detail = None
            raise PiUnreachable(f"HTTP {error.code}: {detail or error.reason}") from error
        except (urllib.error.URLError, OSError, ValueError) as error:
            raise PiUnreachable(str(getattr(error, "reason", error))) from error

    def route(self) -> str | None:
        """How the laptop reaches the Pi: pi_wifi | cable | lan (from pi_candidates), None if the address is not listed."""
        return next((c["route"] for c in self.candidates if c["url"] == self.pi_url), None)

    def _health(self, url: str, timeout: float) -> bool:
        request = urllib.request.Request(url + "/health", headers={**({"X-Bioreactor-Token": self.token} if self.token else {})})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return bool(json.loads(response.read().decode("utf-8")).get("ok"))
        except Exception:      # any failure (URLError, timeout, HTTPException, bad JSON) = this address does not answer
            return False

    def find_pi(self) -> bool:
        """Mode auto: ask every candidate AT ONCE (each in its own thread); the first in priority order that answers
        /health becomes pi_url. In parallel, a name that Windows resolves slowly (bioreactor.local while the networks
        change) cannot hold up the cable or the Pi's Wi-Fi."""
        if self.network_cut or not self.candidates:
            return False
        timeout = float(self.config.get("search_timeout_s", 1.5))
        self.searching = True
        started = time.monotonic()
        try:
            pool = ThreadPoolExecutor(max_workers=len(self.candidates), thread_name_prefix="find-pi")
            futures = [pool.submit(self._health, c["url"], timeout) for c in self.candidates]
            wait(futures, timeout=timeout + 1.0)
            pool.shutdown(wait=False)          # a hung name lookup finishes later in the background
            answers = [f.done() and f.result() for f in futures]
            for candidate, ok in zip(self.candidates, answers):
                if ok:
                    if candidate["url"] != self.pi_url or self.route_seen != candidate["route"]:
                        self._log(f"Pi found via {candidate['route']} ({candidate['url']}) in "
                                  f"{time.monotonic() - started:.1f} s; answers: {dict(zip([c['route'] for c in self.candidates], answers))}")
                    self.pi_url, self.route_seen = candidate["url"], candidate["route"]
                    return True
            now = time.monotonic()
            if now - self._last_not_found_log >= 30:      # once per 30 s, not every second of a reboot
                self._log(f"Pi not found ({now - started:.1f} s): no candidate answered")
                self._last_not_found_log = now
            return False
        finally:
            self.searching = False

    def _log(self, text: str) -> None:
        """data/runtime/reactor_client.log (config client_log): searches and route changes, with the laptop's time."""
        path = self.config.get("client_log")
        if not path:
            return
        try:
            full = Path(path) if Path(path).is_absolute() else Path(__file__).resolve().parents[2] / path
            full.parent.mkdir(parents=True, exist_ok=True)
            with open(full, "a", encoding="utf-8") as f:
                f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {text}\n")
        except OSError:
            pass

    def poll(self) -> None:
        try:
            state = self._request("GET", "/state")
        except PiUnreachable as error:
            if self.last_ok is not None and self.error is None:
                self._log(f"lost the Pi at {self.pi_url}: {error}")
            if self.mode == "auto" and self.find_pi():
                try:
                    state = self._request("GET", "/state")
                except PiUnreachable as error2:
                    with self._lock:
                        self.error = str(error2)
                    return
            else:
                with self._lock:
                    self.error = str(error)
                return
        if self.error is not None or self.last_ok is None:
            self._log(f"data from the Pi via {self.route() or self.pi_url}")
        with self._lock:
            self.last_state, self.last_ok, self.error = state, self.clock(), None

    # -- link -----------------------------------------------------------------------------------
    def network_ok(self) -> bool:
        return self.last_ok is not None and self.clock() - self.last_ok <= self.config["link_timeout_s"]

    def address(self) -> str:
        return urlsplit(self.pi_url).netloc

    def status(self) -> dict:
        with self._lock:
            state, error = self.last_state, self.error
            since = None if self.last_ok is None else round(self.clock() - self.last_ok, 1)
        net = self.network_ok()
        arduino = bool(net and state and state["arduino_link"]["ok"])
        level = None if arduino else "pi" if not net else "arduino"
        source = {"kind": "simulator" if self.mode == "simulator" else "pi", "mode": self.mode,
                  "address": None if self.mode == "simulator" else self.address(),
                  "route": None if self.mode == "simulator" else self.route(),
                  "arduino_port": (state or {}).get("bridge", {}).get("port"),
                  "firmware": (state or {}).get("bridge", {}).get("firmware")}
        if state is None:
            return {"source": source, "link": {"ok": False, "level": "pi", "network_ok": False, "arduino_ok": False,
                                               "seconds_since_pi": since, "error": error},
                    "readings": {n: {"value": None, "last": None, "level": "unknown"} for n in SENSORS},
                    "relays": {n: {"on": False, "remote": False, "on_for_s": 0, "total_s": 0, "on_blocked": "no_link"}
                               for n in RELAYS},
                    "alarms": [{"code": "pi_lost", "level": "danger", "error": error}], "auto": None, "limits": None,
                    "arduino_alarms": None, "controls_enabled": False, "estop_enabled": False, "laptop_watchdog": None,
                    "simulator": self._simulator_flags(None), "time": time.time()}
        out = json.loads(json.dumps(state))
        out.pop("bridge", None)
        if not net:
            for reading in out["readings"].values():
                reading["value"], reading["level"] = None, "unknown"
            for relay in out["relays"].values():
                relay["on_blocked"] = "no_link"
            out["alarms"] = [{"code": "pi_lost", "level": "danger", "error": error}] + [
                a for a in out["alarms"] if a["code"] in {"leak", "estop"}]
        out["source"] = source
        out["link"] = {"ok": arduino, "level": level, "network_ok": net, "arduino_ok": arduino,
                       "seconds_since_pi": since, "error": error,
                       "seconds_since_data": out["arduino_link"]["seconds_since_data"]}
        out["controls_enabled"] = arduino
        # E-STOP is tried whenever the Pi answers and its USB port is open — even if the Arduino status is late
        out["estop_enabled"] = bool(net and state["arduino_link"].get("connected"))
        out["simulator"] = self._simulator_flags(out.get("simulator"))
        return out

    def _simulator_flags(self, pi_flags: dict | None) -> dict | None:
        if self.mode != "simulator":
            return None
        return {**(pi_flags or {}), "network": self.network_cut}

    # -- actions of a person ------------------------------------------------------------------------
    def command(self, name: str, on: bool, who: str = "operator") -> dict:
        if not self.status()["controls_enabled"]:
            return {"ok": False, "reason": "no_link"}
        try:
            result = self._request("POST", "/relay", {"name": name, "state": 1 if on else 0, "who": who, "confirm": True},
                                   timeout=self.timeout + 3)
        except PiUnreachable as error:
            return {"ok": False, "reason": "no_link", "error": str(error)}
        self.poll()  # the page and the agent see the new relay state at once, not after the next poll
        return result

    def _post(self, path: str, body: dict) -> dict:
        try:
            result = self._request("POST", path, body, timeout=self.timeout + 3)
        except PiUnreachable as error:
            return {"ok": False, "reason": "no_link", "error": str(error)}
        self.poll()
        return result

    def set_auto(self, on: bool, who: str = "operator") -> dict:
        if not self.status()["controls_enabled"]:
            return {"ok": False, "reason": "no_link"}
        return self._post("/auto", {"on": on, "who": who, "confirm": True})

    def set_limit(self, name: str, value: float, who: str = "operator") -> dict:
        if not self.status()["controls_enabled"]:
            return {"ok": False, "reason": "no_link"}
        return self._post("/limit", {"name": name, "value": value, "who": who, "confirm": True})

    def estop(self, who: str = "operator") -> dict:
        """No confirmation and no «controls enabled» check: the Pi decides; an emergency stop is never held back here."""
        return self._post("/estop", {"who": who})

    def reset_alarms(self, who: str = "operator") -> dict:
        return self._post("/reset", {"who": who, "confirm": True})

    def simulate(self, what: str, on: bool, who: str = "operator") -> dict:
        if self.mode != "simulator":
            return {"ok": False, "reason": "not_simulator"}
        if what == "network":
            self.network_cut = on
            if self.sim:
                self.sim[0].journal.add("system", f"simulate_network_{'on' if on else 'off'}", who, "virtual", "ok")
            return {"ok": True, "reason": None}
        try:
            return self._request("POST", "/simulate", {"what": what, "on": on, "who": who})
        except PiUnreachable as error:
            return {"ok": False, "reason": "no_link", "error": str(error)}

    def check_connection(self) -> dict:
        """The «Проверить связь» button: one /health request, with the time it took."""
        started = time.perf_counter()
        try:
            health = self._request("GET", "/health", timeout=3)
        except PiUnreachable as error:
            if not (self.mode == "auto" and self.find_pi()):
                return {"ok": False, "url": self.pi_url, "mode": self.mode, "route": self.route(), "error": str(error),
                        "latency_ms": round((time.perf_counter() - started) * 1000)}
            started = time.perf_counter()
            try:
                health = self._request("GET", "/health", timeout=3)
            except PiUnreachable as error2:
                return {"ok": False, "url": self.pi_url, "mode": self.mode, "route": self.route(), "error": str(error2),
                        "latency_ms": round((time.perf_counter() - started) * 1000)}
        return {"ok": True, "url": self.pi_url, "mode": self.mode, "route": self.route(),
                "latency_ms": round((time.perf_counter() - started) * 1000),
                "arduino_ok": health.get("arduino_ok"), "port": health.get("port"), "firmware": health.get("firmware"),
                "simulated": health.get("simulated"), "version": health.get("version")}

    def history(self, window: int) -> dict:
        try:
            points = self._request("GET", f"/history?window={window}")["points"]
            self._history_cache[window] = points
            return {"window": window, "points": points, "live": True}
        except PiUnreachable:
            return {"window": window, "points": self._history_cache.get(window, []), "live": False}

    def journal(self, limit: int = 50) -> dict:
        try:
            return {"items": self._request("GET", f"/journal?limit={limit}")["items"], "live": True}
        except PiUnreachable as error:
            return {"items": [], "live": False, "error": str(error)}

    # -- thread ------------------------------------------------------------------------------------------
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        if self.mode == "simulator" and self.sim is None:
            self._start_simulator()
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="reactor-client", daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        while not self._stop.is_set():
            started = self.clock()
            try:
                self.poll()
            except Exception as error:      # the polling thread must never die (the page would freeze on old data)
                with self._lock:
                    self.error = f"{type(error).__name__}: {error}"
                self._log(f"poll error {type(error).__name__}: {error}")
            self._stop.wait(max(0.05, self.config["poll_s"] - (self.clock() - started)))

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        if self.sim:
            bridge, server = self.sim
            server.stop()
            bridge.stop()
            self.sim = None
