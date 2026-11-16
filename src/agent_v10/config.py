"""Paths and LLM settings for agent v10.

LLM settings live in ONE file, data/config/llm_selection.json, shared with
the old dashboard agent, ЗАПУСК_BioReactor.bat warm-up and the benchmark script.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "data" / "config" / "llm_selection.json"
DEFAULTS_PATH = ROOT / "data" / "research" / "agent_v10_defaults.json"
REGIMES_PATH = ROOT / "data" / "research" / "temperature_regimes.json"
MARKET_DB_PATH = ROOT / "data" / "market" / "market.sqlite3"
MEMORY_DB_PATH = ROOT / "data" / "runtime" / "agent_v10.sqlite3"
DEMO_REACTOR_PATH = ROOT / "data" / "config" / "demo_reactor.json"
ANALOGS_PATH = ROOT / "data" / "research" / "agent_v10_analogs.json"

# Lower heating value of methane, FNR "Faustzahlen Biogas" (source id fnr-energy-lhv).
METHANE_KWH_PER_M3 = 9.97

# The agent never runs more than this many LLM steps for one user message.
MAX_AGENT_STEPS = 5


@lru_cache(maxsize=1)
def llm_settings() -> dict:
    """Read data/config/llm_selection.json; environment variables can override the model."""
    settings = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    settings["model"] = os.getenv("BIOREACTOR_V10_MODEL", settings["model"])
    settings["ollama_url"] = os.getenv("BIOREACTOR_V10_OLLAMA_URL", settings["ollama_url"])
    return settings


@lru_cache(maxsize=1)
def defaults() -> dict:
    """Fallback values (density, methane share, compositions without profiles)."""
    return json.loads(DEFAULTS_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def temperature_regimes() -> dict:
    """Psychrophilic / mesophilic / thermophilic table with sources."""
    return json.loads(REGIMES_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def demo_reactor() -> dict:
    """Default reactor (200 L barrel, 160 L working volume, no insulation, cattle slurry, +5 °C).

    Used only for values the user did not give; every use is shown as an assumption.
    Replace the numbers in data/config/demo_reactor.json with the real reactor.
    """
    reactor = json.loads(DEMO_REACTOR_PATH.read_text(encoding="utf-8"))
    reactor["fill_share"] = reactor["working_volume_l"] / reactor["reactor_volume_l"]
    return reactor


@lru_cache(maxsize=1)
def analogs() -> dict:
    """Rules 'unknown material -> closest material with data' (data/research/agent_v10_analogs.json)."""
    return json.loads(ANALOGS_PATH.read_text(encoding="utf-8"))
