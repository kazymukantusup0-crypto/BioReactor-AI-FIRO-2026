"""Settings of the Pi bridge: default_config.json next to this file, overridden by a user file (e.g. /etc/bioreactor-pi/config.json)."""
from __future__ import annotations

import copy
import json
from pathlib import Path

DEFAULT_PATH = Path(__file__).with_name("default_config.json")


def merge(base: dict, extra: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = merge(out[key], value)
        else:
            out[key] = value
    return out


def load(path: str | Path | None = None, overrides: dict | None = None) -> dict:
    config = json.loads(DEFAULT_PATH.read_text(encoding="utf-8"))
    if path and Path(path).is_file():
        config = merge(config, json.loads(Path(path).read_text(encoding="utf-8")))
    return merge(config, overrides or {})
