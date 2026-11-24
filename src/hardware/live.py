"""Read-only access to the live reactor for the AI agent.

The agent gets a COPY of the status (readings, relay states, alarms) — never the manager itself, so there is no
way from the agent to command(). tests/test_reactor_hardware.py checks that src/agent_v10 never imports
manager / api / transport.
"""
from __future__ import annotations

import copy
import threading

_lock = threading.Lock()
_manager = None


def register(manager) -> None:
    global _manager
    with _lock:
        _manager = manager


def unregister(manager=None) -> None:
    global _manager
    with _lock:
        if manager is None or _manager is manager:
            _manager = None


def snapshot() -> dict | None:
    """The current status (a deep copy), or None when no reactor connection runs in this process."""
    with _lock:
        manager = _manager
    if manager is None:
        return None
    return copy.deepcopy(manager.status())
