"""Agent v10 loop, number check and API — with a scripted fake LLM (no Ollama needed)."""
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.agent_v10 import answer
from src.agent_v10.agent import Agent, plan_tools
from src.agent_v10.api import create_router
from src.agent_v10.facts import empty_facts
from src.agent_v10.llm import LLMUnavailable
from src.agent_v10.memory import Memory


class FakeLLM:
    """Plays back prepared LLM replies: ("tool", name, args) or ("text", "...")."""

    model = "fake-model"

    def __init__(self, script, available=True):
        self.script = list(script)
        self._available = available
        self.calls = []

    def available(self):
        return self._available

    def gpu_status(self):
        return {"loaded": True, "gpu_percent": 100}

    def chat_stream(self, messages, tools=None):
        self.calls.append({"messages": messages, "tools": tools})
        if not self.script:
            raise LLMUnavailable("script finished")
        kind, *payload = self.script.pop(0)
        stats = {"duration_ms": 1, "first_token_ms": 1, "prompt_tokens": 100, "output_tokens": 10, "tokens_per_s": 50}
        if kind == "tool":
            name, args = payload
            yield {"type": "final", "content": "", "tool_calls": [{"function": {"name": name, "arguments": args}}],
                   "stats": stats}
        else:
            yield {"type": "token", "text": payload[0]}
            yield {"type": "final", "content": payload[0], "tool_calls": [], "stats": stats}


def run(agent, conversation, text, use_llm=True):
    events = list(agent.run(conversation, text, use_llm=use_llm))
    return events, next(e for e in events if e["type"] == "answer")


@pytest.fixture
def memory(tmp_path):
    return Memory(tmp_path / "agent.sqlite3")


def test_tool_call_then_answer_emits_thinking_feed(memory):
    llm = FakeLLM([("tool", "estimate_methane", {}), ("text", "Получится 2.9–5.2 м³ метана при 37 °C.")])
    events, final = run(Agent(memory, llm), "c1-conversation", "200 л жидкого навоза КРС, сколько газа?")
    kinds = [e["type"] for e in events]
    assert kinds[:2] == ["understood", "facts"]
    assert kinds.index("tool_call") < kinds.index("tool_result") < kinds.index("answer") < kinds.index("done")
    assert final["mode"] == "llm" and final["verified"] is True
    assert final["numbers"][0]["value"] == "2.9–5.2"
    assert all(e["t_ms"] >= 0 for e in events)
    # The LLM saw the tool schemas and only the compact tool result.
    tool_message = next(m for m in llm.calls[1]["messages"] if m["role"] == "tool")
    assert "methane_m3" in json.loads(tool_message["content"]) and "components" in tool_message["content"]
    assert "formulas" not in tool_message["content"]


def test_invented_number_is_regenerated_then_replaced_by_template(memory):
    llm = FakeLLM([("tool", "estimate_methane", {}), ("text", "Будет 77 м³ метана."), ("text", "Будет 88 м³ метана.")])
    _, final = run(Agent(memory, llm), "c2-conversation", "200 л жидкого навоза КРС, сколько газа?")
    assert final["verified"] is False
    assert "77" not in final["text"] and "88" not in final["text"]
    assert "2.9–5.2" in final["explanation"]  # template built from the tool result


def test_regenerated_answer_is_accepted_when_numbers_are_correct(memory):
    llm = FakeLLM([("tool", "estimate_methane", {}), ("text", "Будет 77 м³."), ("text", "Будет 2.9–5.2 м³ метана.")])
    events, final = run(Agent(memory, llm), "c3-conversation", "200 л жидкого навоза КРС, сколько газа?")
    assert final["verified"] is True
    assert [e["ok"] for e in events if e["type"] == "verification"] == [False, True]


def test_broken_tool_calls_fall_back_to_deterministic_path(memory):
    llm = FakeLLM([("tool", "unknown_tool", {}), ("tool", "another_unknown", {})])
    events, final = run(Agent(memory, llm), "c4-conversation", "200 л жидкого навоза КРС, сколько газа?")
    assert final["mode"] == "llm_fallback"
    assert any(e["type"] == "note" and e["code"] == "bad_tool_call" for e in events)
    assert "estimate_methane" in final["tools"]


def test_no_llm_mode_uses_router_and_templates(memory):
    _, final = run(Agent(memory, FakeLLM([], available=False)), "c5-conversation",
                   "Какую температуру ставить зимой при −15 на улице, реактор 250 л не утеплён? 200 л жидкого навоза")
    assert final["mode"] == "no_llm"
    assert final["tools"] == ["recommend_temperature_regime"]
    assert "мезофильный" in final["explanation"]


def test_llm_answer_without_tools_triggers_python_tools(memory):
    llm = FakeLLM([("text", "Наверное, много газа."), ("text", "Получится 2.9–5.2 м³ метана.")])
    events, final = run(Agent(memory, llm), "c6-conversation", "200 л жидкого навоза КРС, сколько газа?")
    assert any(e["type"] == "note" and e["code"] == "forced_tools" for e in events)
    assert final["tools"] == ["estimate_methane"] and final["verified"] is True


def test_memory_keeps_the_batch_between_messages(memory):
    agent = Agent(memory, FakeLLM([], available=False))
    run(agent, "c7-conversation", "200 л жидкого навоза КРС")
    _, final = run(agent, "c7-conversation", "А если добавить 30 кг пищевых отходов?")
    assert final["tools"] == ["compare_scenarios"]
    assert [c["substrate"] for c in memory.get("c7-conversation")["facts"]["components"]] == ["cattle_manure", "food_waste"]
    assert len(memory.get("c7-conversation")["messages"]) == 4


def test_kazakh_answer_in_no_llm_mode(memory):
    _, final = run(Agent(memory, FakeLLM([], available=False)), "c8-conversation", "Сиыр көңі 200 литр, қанша газ болады?")
    assert final["language"] == "kk" and "метан" in final["explanation"]


def test_plan_tools_router():
    facts = {**empty_facts(), "components": [{"substrate": "cattle_manure", "amount": 200, "unit": "l"}]}
    assert [c["name"] for c in plan_tools("сколько газа?", facts)] == ["estimate_methane"]
    assert [c["name"] for c in plan_tools("какую температуру ставить зимой?", facts)] == ["recommend_temperature_regime"]
    assert plan_tools("привет", empty_facts()) == []


# ---------- number check ------------------------------------------------------

def test_parse_numbers_handles_comma_minus_and_thousands():
    assert answer.parse_numbers("2,9–5,2 м³, −15 °C, 1 050 кВт·ч") == [2.9, 5.2, -15, 1050]


def test_number_check_allows_rounding_but_not_invented_values():
    results = [{"ok": True, "llm": {"methane_m3": [2.9, 5.2], "energy_kwh": [29, 52]}, "assumptions": []}]
    allowed = answer.allowed_numbers(results, "у меня 200 л", empty_facts())
    assert answer.unknown_numbers("около 3 м³ из 200 л, энергия 52 кВт·ч", allowed) == []
    assert answer.unknown_numbers("будет 40 м³", allowed) == [40]
    assert answer.unknown_numbers("будет 2.7 м³", allowed) == [2.7]   # 2.7 is not a rounding of 2.9


def test_question_comes_only_from_successful_tools():
    ok = {"ok": True, "name": "search_knowledge", "llm": {"quotes": []}, "question": None, "assumptions": [], "sources": [],
          "data": {}, "label": "literature"}
    failed = {"ok": False, "name": "compare_scenarios", "llm": {}, "question": "Какое сырьё?", "assumptions": [], "sources": [], "data": {}}
    composed = answer.compose(explanation="Текст", results=[failed, ok], language="ru", mode="llm", verified=True)
    assert composed["question"] is None


# ---------- API ------------------------------------------------------------------

def test_api_streams_sse_and_manages_conversations(memory):
    app = FastAPI()
    app.include_router(create_router(Agent(memory, FakeLLM([], available=False))))
    client = TestClient(app)
    response = client.post("/api/agent/chat", json={"message": "200 л жидкого навоза КРС, сколько газа?"})
    assert response.status_code == 200 and response.headers["content-type"].startswith("text/event-stream")
    conversation_id = response.headers["x-conversation-id"]
    events = [line[7:] for line in response.text.splitlines() if line.startswith("event: ")]
    assert events[0] == "understood" and events[-1] == "done" and "answer" in events

    state = client.get(f"/api/agent/conversations/{conversation_id}").json()
    assert state["exists"] and state["facts"]["components"][0]["substrate"] == "cattle_manure"
    edited = client.post(f"/api/agent/conversations/{conversation_id}/facts", json={"facts": {"insulation": "good"}}).json()
    assert edited["facts"]["insulation"] == "good"
    assert client.post(f"/api/agent/conversations/{conversation_id}/facts", json={"facts": {"x": 1}}).json()["ok"] is False
    assert client.post("/api/agent/reset", json={"conversation_id": conversation_id}).json()["ok"]
    assert client.get(f"/api/agent/conversations/{conversation_id}").json()["exists"] is False
    assert client.get("/api/agent/status").json()["mode"] == "no_llm"
    assert client.get("/api/agent/demo-reactor").json()["working_volume_l"] == 160


def test_api_rejects_bad_fact_values(memory):
    app = FastAPI()
    app.include_router(create_router(Agent(memory, FakeLLM([], available=False))))
    client = TestClient(app)
    url = "/api/agent/conversations/test-conversation/facts"
    assert client.post(url, json={"facts": {"insulation": "very"}}).json()["ok"] is False
    assert client.post(url, json={"facts": {"ambient_c": "cold"}}).json()["ok"] is False
    assert client.post(url, json={"facts": {"reactor_volume_l": -5}}).json()["ok"] is False
    accepted = client.post(url, json={"facts": {"reactor_volume_l": 200, "ambient_c": -15, "insulation": None}}).json()
    assert accepted["ok"] and accepted["facts"]["ambient_c"] == -15


def test_gas_and_heating_question_gets_python_verdict_without_llm(memory):
    agent = Agent(memory, FakeLLM([], available=False))
    events = list(agent.run("gas-heat-test", "150 литров навоза КРС, бочка 200 л не утеплена, на улице −10. "
                                             "Сколько газа и хватит ли на подогрев?"))
    answer = next(e for e in events if e["type"] == "answer")
    assert "gas_vs_heating" in answer["tools"]
    cards = {card["key"]: card for card in answer["numbers"]}
    assert cards["enough_gas"]["value"] == "нет"
    assert "не хватит" in answer["explanation"]
