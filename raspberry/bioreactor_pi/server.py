"""HTTP API of the Pi (Python standard library only: nothing to install on the Pi except pyserial).

    GET  /health                 {"ok":true,"version":"1.0","simulated":false,"arduino_ok":true,"deployed":"<commit> <time>"}
    GET  /state                  readings + levels, relays (on, how long, why blocked), alarms, links
    GET  /history?window=600     points for charts (600 = 10 min, 3600 = 1 hour)
    GET  /journal?limit=50       commands and alarms
    GET  /events                 Server-Sent Events: "event: state" with /state every second
    POST /relay                  {"name":"heat"|"cool"|"pump"|"auger","state":1,"who":"operator","confirm":true}
    POST /time                   {"epoch": <laptop time, s>}  set the Pi's clock if it is more than 5 s off
    POST /auto                   {"on":true,"confirm":true}                 the Arduino's automatic regime
    POST /limit                  {"name":"temp_min","value":35.5,"confirm":true}   one EEPROM threshold (SET)
    POST /estop                  {"who":"operator"}                         EMERGENCY STOP: no confirmation, never delayed
    POST /reset                  {"who":"operator","confirm":true}          a person clears E-STOP / leak / link_lost
    POST /simulate               {"what":"leak"|"usb"|"arduino_silent"|"temp_sensor","on":true}  --simulate only

Every request from the laptop resets the laptop watchdog (laptop silent > 15 s -> the relays switched ON from the Pi
go OFF; the Arduino's AUTO regime keeps running).
If "token" is set in the config, every request needs the header X-Bioreactor-Token: <token>.
"""
from __future__ import annotations

import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from . import protocol

MAX_BODY = 4096
STAMP = Path(__file__).resolve().parent.parent / "DEPLOYED"   # /opt/bioreactor-pi/DEPLOYED, written by bioreactor-deploy


def deployed_stamp() -> str | None:
    """Which laptop commit the running code came from (scripts/deploy_to_pi.ps1), None when unknown."""
    try:
        return STAMP.read_text(encoding="utf-8").strip()[:200] or None
    except OSError:
        return None


def make_handler(bridge, token: str = ""):
    class Handler(BaseHTTPRequestHandler):
        server_version = "BioReactorPi/1.0"
        protocol_version = "HTTP/1.1"

        def log_message(self, format, *args):  # quiet: the journal is the log
            pass

        def _json(self, code: int, payload) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _allowed(self) -> bool:
            if token and self.headers.get("X-Bioreactor-Token") != token:
                self._json(401, {"error": "token required"})
                return False
            bridge.laptop_seen()
            return True

        def _body(self) -> dict | None:
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = -1
            if not 0 < length <= MAX_BODY:
                self._json(400, {"error": "JSON body required"})
                return None
            try:
                data = json.loads(self.rfile.read(length).decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                self._json(400, {"error": "bad JSON"})
                return None
            if not isinstance(data, dict):
                self._json(400, {"error": "JSON object required"})
                return None
            return data

        def do_GET(self):
            if not self._allowed():
                return
            url = urlsplit(self.path)
            query = parse_qs(url.query)
            if url.path == "/health":
                state = bridge.state()
                return self._json(200, {"ok": True, "version": state["bridge"]["version"], "simulated": bridge.simulated,
                                        "arduino_ok": state["arduino_link"]["ok"], "port": state["bridge"]["port"],
                                        "firmware": state["bridge"]["firmware"], "deployed": deployed_stamp()})
            if url.path == "/state":
                return self._json(200, bridge.state())
            if url.path == "/history":
                try:
                    window = int(query.get("window", ["600"])[0])
                except ValueError:
                    window = 0
                if window not in (600, 3600):
                    return self._json(400, {"error": "window must be 600 or 3600"})
                return self._json(200, {"window": window, "points": bridge.history_window(window)})
            if url.path == "/journal":
                try:
                    limit = max(1, min(int(query.get("limit", ["50"])[0]), 500))
                except ValueError:
                    limit = 50
                return self._json(200, {"items": bridge.journal.recent(limit)})
            if url.path == "/events":
                return self._events()
            return self._json(404, {"error": "not found"})

        def _events(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True
            try:
                while True:
                    bridge.laptop_seen()
                    data = json.dumps(bridge.state(), ensure_ascii=False)
                    self.wfile.write(f"event: state\ndata: {data}\n\n".encode("utf-8"))
                    self.wfile.flush()
                    time.sleep(1)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                return

        def do_POST(self):
            if not self._allowed():
                return
            path = urlsplit(self.path).path
            body = self._body()
            if body is None:
                return
            who = str(body.get("who") or "operator")[:40]
            if path == "/time":
                # the laptop's clock -> the Pi's clock (no battery clock on the Pi); not a hardware command
                result = bridge.set_time(body.get("epoch"), who=who if who != "operator" else "laptop")
                return self._json(400 if result["reason"] == "bad_time" else 200, result)
            if path == "/estop":
                return self._json(200, bridge.estop(who=who))
            if body.get("confirm") is not True and path in ("/relay", "/auto", "/limit", "/reset"):
                return self._json(428, {"error": "confirmation required"})
            if path == "/relay":
                name, state = body.get("name"), body.get("state")
                if name not in protocol.RELAYS or state not in (0, 1, True, False):
                    return self._json(400, {"error": "name must be heat|cool|pump|auger and state 0|1"})
                return self._json(200, bridge.command(name, bool(state), who=who))
            if path == "/auto":
                if not isinstance(body.get("on"), bool):
                    return self._json(400, {"error": "on: true|false"})
                return self._json(200, bridge.set_auto(body["on"], who=who))
            if path == "/limit":
                name, value = body.get("name"), body.get("value")
                if name not in protocol.LIMITS or isinstance(value, bool) or not isinstance(value, (int, float)):
                    return self._json(400, {"error": "name: " + "|".join(protocol.LIMITS) + ", value: a number"})
                return self._json(200, bridge.set_limit(name, float(value), who=who))
            if path == "/reset":
                return self._json(200, bridge.reset_alarms(who=who))
            if path == "/simulate":
                if body.get("what") not in ("leak", "usb", "arduino_silent", "temp_sensor") or not isinstance(body.get("on"), bool):
                    return self._json(400, {"error": "what: leak|usb|arduino_silent|temp_sensor, on: true|false"})
                result = bridge.simulate(body["what"], body["on"], who=who)
                return self._json(409 if result["reason"] == "not_simulator" else 200, result)
            return self._json(404, {"error": "not found"})

    return Handler


class PiServer:
    """The HTTP server in a background thread (start/stop), used by __main__ and by the laptop's simulator."""

    def __init__(self, bridge, host: str = "0.0.0.0", port: int = 8780, token: str = ""):
        self.bridge = bridge
        self.httpd = ThreadingHTTPServer((host, port), make_handler(bridge, token))
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        self._thread = None

    def start(self) -> None:
        import threading
        self._thread = threading.Thread(target=self.httpd.serve_forever, name="bioreactor-pi-http", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
