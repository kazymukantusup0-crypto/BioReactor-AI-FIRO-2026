"""Laptop settings: data/config/reactor_hardware.json + environment (BIOREACTOR_SENSORS, BIOREACTOR_PI_URL).

BIOREACTOR_PI_URL sets one fixed address (mode "pi" unless BIOREACTOR_SENSORS says otherwise)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "data/config/reactor_hardware.json"
RASPBERRY_DIR = ROOT / "raspberry"
MODES = ("auto", "pi", "simulator")


def load_config(overrides: dict | None = None) -> dict:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    mode = os.getenv("BIOREACTOR_SENSORS")
    if os.getenv("BIOREACTOR_PI_URL"):
        config["pi_url"] = os.environ["BIOREACTOR_PI_URL"]
        if config["mode"] == "auto":
            config["mode"] = "pi"
    if mode in MODES:
        config["mode"] = mode
    config.update(overrides or {})
    if config["mode"] not in MODES:
        raise ValueError("reactor_hardware.json: mode must be auto, pi or simulator")
    return config


def pi_package():
    """The Pi bridge code (raspberry/bioreactor_pi) — the simulator runs the very same code inside the laptop."""
    if str(RASPBERRY_DIR) not in sys.path:
        sys.path.insert(0, str(RASPBERRY_DIR))
    import bioreactor_pi
    return bioreactor_pi
