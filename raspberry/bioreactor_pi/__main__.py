"""Run the bridge:  python -m bioreactor_pi [--config /etc/bioreactor-pi/config.json] [--simulate] [--port 8780]

    --simulate   no Arduino: the virtual Arduino (same protections) — to test the Pi and the network without hardware
"""
from __future__ import annotations

import argparse
import signal
import sys
import threading

from . import config as config_module
from .bridge import Bridge
from .journal import Journal
from .serial_link import SerialLink
from .server import PiServer


def build(config: dict, simulate: bool):
    if simulate:
        from .virtual_arduino import VirtualSerial
        link = VirtualSerial(config)
    else:
        link = SerialLink(config["serial"]["port"], int(config["serial"]["baud"]))
    return Bridge(config, link, Journal(config["journal_path"]), simulated=simulate)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="bioreactor_pi", description="Arduino <-> network bridge of BioReactor AI")
    parser.add_argument("--config", default="/etc/bioreactor-pi/config.json")
    parser.add_argument("--simulate", action="store_true", help="virtual Arduino instead of the USB board")
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)
    parser.add_argument("--journal", help="SQLite journal path (default from the config)")
    args = parser.parse_args(argv)
    overrides = {}
    if args.journal:
        overrides["journal_path"] = args.journal
    config = config_module.load(args.config, overrides)
    host = args.host or config["http"]["host"]
    port = args.port or config["http"]["port"]
    bridge = build(config, args.simulate)
    server = PiServer(bridge, host, port, config["http"].get("token", ""))
    bridge.start()
    server.start()
    print(f"BioReactor Pi bridge {'(SIMULATED Arduino) ' if args.simulate else ''}on http://{host}:{server.port}  "
          f"serial={config['serial']['port']}  journal={config['journal_path']}", flush=True)
    stop = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, lambda *_: stop.set())
    while not stop.wait(1):
        pass
    server.stop()
    bridge.stop()  # all relays OFF on exit
    return 0


if __name__ == "__main__":
    sys.exit(main())
