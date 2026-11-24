"""The «Сырьё и смеси» page and the agent give EQUAL numbers for equal input.

The farmer writes a batch in the chat -> the agent (no-LLM mode, the same Python tools) answers with estimate_methane.
The same batch typed on the page -> POST /api/substrates/estimate. Every number must be the same.
"""
import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.advisor.catalog import get_catalog
from src.agent_v10.agent import Agent
from src.agent_v10.api import create_router as agent_router
from src.agent_v10.memory import Memory
from src.dashboard.substrates_api import create_router as page_router


class NoLLM:
    model = "none"

    def available(self):
        return False

    def __getattr__(self, name):  # the agent never calls the model when it is not available
        raise AssertionError(f"LLM call {name} in no-LLM mode")


@pytest.fixture()
def client(tmp_path):
    app = FastAPI()
    app.include_router(agent_router(Agent(Memory(tmp_path / "agent.sqlite3"), NoLLM())))
    app.include_router(page_router())
    return TestClient(app)


def agent_numbers(client, message):
    response = client.post("/api/agent/chat", json={"message": message})
    for block in response.text.split("\n\n"):
        lines = block.splitlines()
        if lines and lines[0] == "event: answer":
            return json.loads(lines[1][len("data: "):])["data"]["estimate_methane"]
    raise AssertionError("no answer event")


KEYS = ["methane_m3", "biogas_m3", "energy_kwh", "methane_potential_m3", "wet_mass_kg", "days"]
CASES = [
    ("200 л жидкого навоза КРС, сколько газа?", "ru", [{"material": "cattle_manure", "quantity": 200, "unit": "L", "state": "slurry"}]),
    ("100 кг навоза КРС и 20 кг пищевых отходов, сколько газа?", "ru",
     [{"material": "cattle_manure", "quantity": 100, "unit": "kg"}, {"material": "food_waste", "quantity": 20, "unit": "kg"}]),
    ("10 кг соломы, сколько газа?", "ru", [{"material": "straw", "quantity": 10, "unit": "kg"}]),
    ("2 т свиного навоза, сколько газа?", "ru", [{"material": "swine_manure", "quantity": 2, "unit": "t"}]),
    ("How much gas from 50 kg of cow manure?", "en", [{"material": "cattle_manure", "quantity": 50, "unit": "kg"}]),
    ("Сиыр көңі 200 литр, қанша газ болады?", "kk", [{"material": "cattle_manure", "quantity": 200, "unit": "L"}]),
]


@pytest.mark.parametrize("message,language,page", CASES)
def test_page_and_agent_give_equal_numbers(client, message, language, page):
    agent = agent_numbers(client, message)
    assert agent["status"] == "ok"
    result = client.post("/api/substrates/estimate", json={"components": page, "language": language}).json()
    assert result["ok"] and result["status"] == "ok"
    for key in KEYS:
        assert result["data"][key] == pytest.approx(agent[key], rel=1e-12), key
    for mine, theirs in zip(result["data"]["components"], agent["components"]):
        assert mine["substrate"] == theirs["substrate"]
        assert mine["methane_m3"] == pytest.approx(theirs["methane_m3"], rel=1e-12)


def test_grams_and_millilitres_are_the_same_batch(client):
    estimate = lambda quantity, unit: client.post("/api/substrates/estimate", json={"components": [
        {"material": "cattle_manure", "quantity": quantity, "unit": unit}]}).json()["data"]["methane_m3"]
    assert estimate(5000, "g") == pytest.approx(estimate(5, "kg"))
    assert estimate(20000, "mL") == pytest.approx(estimate(20, "L"))


def test_contribution_shares_add_up_to_one(client):
    rows = client.post("/api/substrates/estimate", json={"components": [
        {"material": "cattle_manure", "quantity": 100, "unit": "kg"},
        {"material": "food_waste", "quantity": 20, "unit": "kg"},
        {"material": "straw", "quantity": 10, "unit": "kg"}]}).json()["data"]["components"]
    assert sum(row["share_of_methane"] for row in rows) == pytest.approx(1.0)


@pytest.mark.parametrize("quantity", [0, -5, 1e12])
def test_bad_amounts_are_refused(client, quantity):
    response = client.post("/api/substrates/estimate", json={"components": [
        {"material": "cattle_manure", "quantity": quantity, "unit": "kg"}]})
    assert response.status_code == 422


TEMPLATES = json.loads((Path(__file__).resolve().parents[1] / "frontend/src/askAgentTemplates.json").read_text(encoding="utf-8"))


def ask_agent_question(rows: list[dict], language: str) -> str:
    """Python copy of askAgentQuestion() in SubstrateAdvisorV81.tsx: the text the «Спросить ИИ» button puts in the chat."""
    words = TEMPLATES[language]
    names = {m["id"]: (m["name"].get(language) if isinstance(m["name"], dict) else m["name"]) for m in get_catalog()["materials"]}
    items = []
    for row in rows:
        state = words["states"].get(row.get("state") or "")
        items.append(" ".join(part for part in [f"{row['quantity']:g}", words["units"][row["unit"]], state, names[row["material"]].lower()] if part))
    joined = items[0] if len(items) == 1 else ", ".join(items[:-1]) + f" {words['and']} " + items[-1]
    return f"{words['intro']} {joined}. {words['ask']}"


ASK_CASES = [
    ([{"material": "cattle_manure", "quantity": 200, "unit": "L", "state": "slurry"}], "ru"),
    ([{"material": "cattle_manure", "quantity": 100, "unit": "kg"}, {"material": "food_waste", "quantity": 20, "unit": "kg"},
      {"material": "straw", "quantity": 10, "unit": "kg"}], "ru"),
    ([{"material": "swine_manure", "quantity": 2.5, "unit": "t", "state": "slurry"}], "ru"),
    ([{"material": "poultry_manure", "quantity": 40, "unit": "kg", "state": "dry"}, {"material": "grass", "quantity": 30, "unit": "kg"}], "kk"),
    ([{"material": "cattle_manure", "quantity": 1, "unit": "m3", "state": "slurry"}], "kk"),
    ([{"material": "horse_manure", "quantity": 60, "unit": "kg"}, {"material": "vegetable_waste", "quantity": 15, "unit": "kg"}], "en"),
    ([{"material": "sheep_goat_manure", "quantity": 80, "unit": "kg", "state": "fresh_solid"}, {"material": "silage", "quantity": 25, "unit": "kg"}], "en"),
]


@pytest.mark.parametrize("rows,language", ASK_CASES)
def test_ask_ai_button_question_gives_the_page_numbers(client, rows, language):
    agent = agent_numbers(client, ask_agent_question(rows, language))
    page = client.post("/api/substrates/estimate", json={"components": rows, "language": language}).json()["data"]
    assert agent["status"] == "ok", ask_agent_question(rows, language)
    for key in KEYS:
        assert page[key] == pytest.approx(agent[key], rel=1e-12), (key, ask_agent_question(rows, language))


def test_materials_with_data_are_the_agent_table(client):
    with_data = client.get("/api/substrates/materials").json()["with_data"]
    assert {"cattle_manure", "swine_manure", "poultry_manure", "food_waste", "straw", "grass"} <= set(with_data)
    assert "other_organic" not in with_data and "manure" not in with_data


def test_no_data_material_gets_an_honest_answer(client):
    result = client.post("/api/substrates/estimate", json={"components": [
        {"material": "other_organic", "quantity": 5, "unit": "kg"}]}).json()
    assert result["ok"] is False and result["status"] == "no_data" and result["question"]
