"""Keep-alive ping of the model during a demo (src/agent_v10/keepalive.py) — no Ollama needed."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.agent_v10.agent import Agent
from src.agent_v10.api import create_router
from src.agent_v10.keepalive import KeepAlive, interval_from_env, ping
from src.agent_v10.memory import Memory


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def make(busy=False, last_used=1000.0, fail=False):
    clock = Clock()
    state = {"busy": busy, "last_used": last_used, "pings": 0}

    def do_ping():
        if fail:
            raise OSError("ollama is down")
        state["pings"] += 1
        return 300.0

    keepalive = KeepAlive(150, is_busy=lambda: state["busy"], last_used=lambda: state["last_used"],
                          do_ping=do_ping, clock=clock)
    return keepalive, clock, state


def test_no_ping_before_the_interval():
    keepalive, clock, state = make()
    clock.now += 149
    assert keepalive.tick() == "recent" and state["pings"] == 0


def test_ping_after_the_interval_then_wait_again():
    keepalive, clock, state = make()
    clock.now += 151
    assert keepalive.tick() == "pinged" and state["pings"] == 1
    clock.now += 60
    assert keepalive.tick() == "recent"
    clock.now += 100
    assert keepalive.tick() == "pinged" and state["pings"] == 2


def test_never_ping_while_an_answer_is_running():
    keepalive, clock, state = make(busy=True)
    clock.now += 1000
    assert keepalive.tick() == "busy" and state["pings"] == 0


def test_a_recent_answer_counts_as_activity():
    keepalive, clock, state = make()
    clock.now += 500
    state["last_used"] = clock.now - 10  # the jury asked 10 s ago
    assert keepalive.tick() == "recent" and state["pings"] == 0


def test_ollama_down_does_not_stop_the_keepalive():
    keepalive, clock, _ = make(fail=True)
    clock.now += 151
    assert keepalive.tick() == "error" and keepalive.errors == 1
    clock.now += 151
    assert keepalive.tick() == "error" and keepalive.errors == 2


def test_interval_comes_only_from_the_environment(monkeypatch):
    monkeypatch.delenv("BIOREACTOR_KEEPALIVE_S", raising=False)
    assert interval_from_env() is None
    for raw, expected in [("150", 150.0), ("0", None), ("10", None), ("abc", None)]:
        monkeypatch.setenv("BIOREACTOR_KEEPALIVE_S", raw)
        assert interval_from_env() == expected


def test_ping_uses_the_agent_prompt_tools_and_options(monkeypatch):
    """Other num_ctx -> Ollama reloads the model; another prompt -> the agent's prompt leaves the cache."""
    sent = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b"{}"

    def fake_urlopen(request, timeout):
        import json
        sent.update(json.loads(request.data))
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    from src.agent_v10.llm import OllamaClient

    llm = OllamaClient()
    ping(llm)
    assert sent["options"]["num_ctx"] == llm.options["num_ctx"] and sent["options"]["num_gpu"] == llm.options["num_gpu"]
    assert sent["options"]["num_predict"] == 1 and sent["keep_alive"] == llm.keep_alive
    assert sent["messages"][0]["role"] == "system" and "BioReactor AI" in sent["messages"][0]["content"]
    assert {t["function"]["name"] for t in sent["tools"]} >= {"estimate_methane", "gas_stove_hours"}


def test_status_shows_keepalive_only_in_demo_mode(monkeypatch, tmp_path):
    monkeypatch.delenv("BIOREACTOR_KEEPALIVE_S", raising=False)
    app = FastAPI()
    app.include_router(create_router(Agent(Memory(tmp_path / "a.sqlite3"))))
    assert TestClient(app).get("/api/agent/status").json()["keepalive"] is None

    monkeypatch.setenv("BIOREACTOR_KEEPALIVE_S", "150")
    monkeypatch.setattr("src.agent_v10.api.KeepAlive.start", lambda self: self)  # no real thread in tests
    app = FastAPI()
    app.include_router(create_router(Agent(Memory(tmp_path / "b.sqlite3"))))
    assert TestClient(app).get("/api/agent/status").json()["keepalive"] == {"interval_s": 150.0, "pings": 0, "errors": 0}
