"""Background "ping" of the local model during a demo, so the GPU and the model do not fall asleep.

Why: in the final eval one answer took 19.4 s instead of ~3.5 s — the first step waited while the
idle GPU climbed back from 210 MHz. A tiny request every 2–3 minutes keeps the model in VRAM and
the GPU awake between the jury's questions.

How:
  * enabled only when the environment variable BIOREACTOR_KEEPALIVE_S is set (ЗАПУСК_BioReactor.bat
    sets 150 s); tests and scripts never ping;
  * a ping is skipped while an answer is running or if the last answer was less than the interval
    ago — a ping must never make a jury question wait in Ollama's queue;
  * the ping uses the agent's own system prompt, tool schemas and options (num_ctx, num_gpu):
    with other options Ollama would reload the model, with another prompt it would drop the agent's
    prompt from its cache — both would make the next real answer slower;
  * num_predict = 1: the model writes one token (~0.3 s of GPU work).
It cannot stop thermal throttling of a hot laptop: see the checklist in docs/demo_script.md.
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.request
from collections.abc import Callable

from src.agent_v10.facts import empty_facts

ENV_VARIABLE = "BIOREACTOR_KEEPALIVE_S"


def interval_from_env() -> float | None:
    """Seconds between pings from BIOREACTOR_KEEPALIVE_S; None = keep-alive is off."""
    raw = os.getenv(ENV_VARIABLE, "").strip()
    try:
        seconds = float(raw)
    except ValueError:
        return None
    return seconds if seconds >= 30 else None


def ping(llm) -> float:
    """One-token request with the agent's prompt, tools and options; returns milliseconds."""
    from src.agent_v10.agent import system_prompt
    from src.agent_v10.tools.registry import TOOL_SCHEMAS

    payload = {
        "model": llm.model, "stream": False, "think": llm.think, "keep_alive": llm.keep_alive,
        "messages": [{"role": "system", "content": system_prompt(empty_facts(), "ru")},
                     {"role": "user", "content": "ok"}],
        "tools": TOOL_SCHEMAS, "options": {**llm.options, "num_predict": 1},
    }
    request = urllib.request.Request(f"{llm.base_url}/api/chat", data=json.dumps(payload).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
    started = time.perf_counter()
    with urllib.request.urlopen(request, timeout=60) as response:
        response.read()
    return (time.perf_counter() - started) * 1000


class KeepAlive:
    """Pings the model when nobody used it for `interval` seconds."""

    def __init__(self, interval: float, is_busy: Callable[[], bool], last_used: Callable[[], float],
                 do_ping: Callable[[], float], clock: Callable[[], float] = time.monotonic):
        self.interval = interval
        self.is_busy = is_busy
        self.last_used = last_used
        self.do_ping = do_ping
        self.clock = clock
        self.last_ping = clock()
        self.pings = 0
        self.errors = 0
        self._stop = threading.Event()

    def tick(self) -> str:
        """One check: 'busy', 'recent', 'pinged' or 'error'."""
        now = self.clock()
        if self.is_busy():
            return "busy"
        if now - max(self.last_used(), self.last_ping) < self.interval:
            return "recent"
        self.last_ping = now
        try:
            self.do_ping()
        except Exception:  # Ollama stopped or answered oddly: never kill the thread; the agent has its own fallback
            self.errors += 1
            return "error"
        self.pings += 1
        return "pinged"

    def run(self) -> None:
        # Check often, ping rarely: a check is free, a ping only when idle for the whole interval.
        while not self._stop.wait(min(15.0, self.interval / 4)):
            self.tick()

    def start(self) -> "KeepAlive":
        threading.Thread(target=self.run, name="llm-keepalive", daemon=True).start()
        return self

    def stop(self) -> None:
        self._stop.set()
