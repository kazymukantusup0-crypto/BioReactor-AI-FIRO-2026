"""Agent + live reactor: questions about the reactor are answered by Python from a read-only copy of the sensors;
«включи подогрев» is refused (only a person switches relays); calculation questions are not affected."""
from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

from src.agent_v10.agent import Agent
from src.agent_v10.memory import Memory
from src.agent_v10.tools import reactor as reactor_tool
from src.hardware import live

ROOT = Path(__file__).resolve().parents[1]

THRESHOLDS = {"temp_c": {"target": 37, "danger_low": 25, "warn_low": 33, "warn_high": 40, "danger_high": 43},
              "overheat_c": 45, "overheat_release_c": 43, "rh_pct": {"warn_high": 95, "danger_high": 99},
              "gas_in_raw": {"warn_low": 150}, "gas_out_raw": {"warn": 300, "leak": 400},
              "pressure_kpa": {"pump_warn": 2.0, "danger": 3.0, "scale_max": 3.5, "pump_stop": 0.1}}


def status(temp=31.2, p=1.2, gas_out=80, heat=False, link=True, level=None, kind="simulator", leak=False):
    def reading(value, lvl="ok"):
        return {"value": value if link else None, "last": value, "level": lvl if link else "unknown"}
    return {"source": {"kind": kind, "address": "192.168.50.2:8780" if kind == "pi" else None},
            "link": {"ok": link, "level": level},
            "readings": {"temp_c": reading(temp, "warn" if temp < 33 else "ok"), "rh_pct": reading(87.0),
                         "gas_in": reading(420), "gas_out": reading(gas_out, "danger" if gas_out >= 400 else "ok"),
                         "p_kpa": reading(p, "warn" if p >= 2 else "ok")},
            "relays": {n: {"on": n == "heat" and heat, "on_for_s": 0, "total_s": 0, "on_blocked": None}
                       for n in ("heat", "cool", "pump")},
            "alarms": [{"code": "leak", "level": "danger"}] if leak else [], "leak_latched": leak, "overheat": False,
            "thresholds": THRESHOLDS}


class FakeManager:
    def __init__(self, data):
        self.data = data
        self.commands = []

    def status(self):
        return copy.deepcopy(self.data)

    def command(self, *args, **kwargs):  # must never be called by the agent
        self.commands.append(args)
        raise AssertionError("the agent tried to switch a relay")


class FakeLLM:
    """Says it is available; any call means the reactor question went to the model (it must not)."""
    model = "fake"

    def available(self):
        return True

    def chat_stream(self, *args, **kwargs):
        raise AssertionError("reactor questions are answered by Python, not by the LLM")


@pytest.fixture
def agent(tmp_path):
    return Agent(Memory(tmp_path / "m.sqlite3"), FakeLLM())


@pytest.fixture
def manager():
    fake = FakeManager(status())
    live.register(fake)
    yield fake
    live.unregister(fake)


def ask(agent, text, cid="conv-reactor-1"):
    events = list(agent.run(cid, text, use_llm=True))
    return events, next(e for e in events if e["type"] == "answer")


@pytest.mark.parametrize("text", ["Что сейчас в реакторе?", "Какая температура в реакторе сейчас?", "Покажи показания датчиков",
                                  "Пора откачивать газ?", "Есть утечка?", "Какое давление в реакторе?",
                                  "What do the sensors show?", "Реактор қазір қандай?"])
def test_reactor_questions_read_the_sensors(agent, manager, text):
    events, answer = ask(agent, text)
    assert answer["mode"] == "reactor" and answer["tools"] == ["get_reactor_status"] and answer["verified"]
    assert any(e["type"] == "tool_call" and e["name"] == "get_reactor_status" and e["by"] == "python" for e in events)
    assert manager.commands == []


def test_answer_says_simulator_and_advises_heating(agent, manager):
    _, answer = ask(agent, "Что сейчас в реакторе?")
    text = answer["explanation"]
    assert "СИМУЛЯТОР" in text and "31.2 °C" in text
    assert "рекомендую включить подогрев" in text and "только человек" in text
    assert "не % метана" in text, "MQ is an index, never «% methane»"


@pytest.mark.parametrize("text,language", [("Включи подогрев", "ru"), ("Выключи насос", "ru"), ("Turn on the heater", "en"),
                                           ("Қыздыруды қос", "kk")])
def test_control_requests_are_refused(agent, manager, text, language):
    _, answer = ask(agent, text)
    first = {"ru": "Я не управляю реле", "en": "I do not control the relays", "kk": "Мен релені басқармаймын"}[language]
    assert answer["explanation"].startswith(first)
    assert manager.commands == [] and manager.data["relays"]["heat"]["on"] is False


def test_real_pi_source_and_no_link(agent):
    fake = FakeManager(status(kind="pi"))
    live.register(fake)
    try:
        _, answer = ask(agent, "Что сейчас в реакторе?")
        assert "RASPBERRY PI → ARDUINO (192.168.50.2:8780)" in answer["explanation"]
        fake.data = status(kind="pi", link=False, level="arduino")
        _, answer = ask(agent, "Что сейчас в реакторе?", "conv-reactor-2")
        assert "НЕТ СВЯЗИ Raspberry Pi с Arduino" in answer["explanation"] and "°C (" not in answer["explanation"]
    finally:
        live.unregister(fake)


def test_advice_rules():
    codes = lambda s: [a["code"] for a in reactor_tool.advice(s, "ru")]
    assert codes(status(temp=37.0)) == ["ok"]
    assert codes(status(temp=31.0)) == ["heat_on"]
    assert codes(status(temp=31.0, heat=True)) == ["heating"]
    assert codes(status(temp=41.0)) == ["cool_on"]
    assert codes(status(temp=37.0, p=2.2)) == ["pump_on"]
    assert codes(status(temp=37.0, p=3.1)) == ["pump_now"]
    assert codes(status(temp=31.0, leak=True)) == ["leak"], "never advise heating during a leak"
    assert codes(status(link=False, level="pi")) == ["no_link_pi"]


def test_no_live_connection(agent):
    live.unregister()
    _, answer = ask(agent, "Что сейчас в реакторе?")
    assert answer["mode"] == "reactor" and "Живых показаний нет" in answer["explanation"]


def test_calculation_questions_are_not_reactor_questions():
    """No phrase of the eval dialogs and demo scenarios goes to the reactor tool."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import eval_dialogs
    phrases = [turn[0] for _, turns in eval_dialogs.DIALOGS for turn in turns]
    assert len(phrases) > 50
    hits = [p for p in phrases if reactor_tool.is_reactor_question(p)]
    assert hits == []


def test_batch_with_reactor_word_stays_a_calculation(tmp_path, manager):
    class NoLLM(FakeLLM):
        def available(self):
            return False
    agent = Agent(Memory(tmp_path / "calc.sqlite3"), NoLLM())
    _, answer = ask(agent, "Сейчас в реакторе 200 литров коровьего навоза, сколько будет газа?", "conv-reactor-3")
    assert answer["mode"] != "reactor" and answer["tools"] == ["estimate_methane"]
