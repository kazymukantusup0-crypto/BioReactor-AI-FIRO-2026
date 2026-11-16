"""RU / ҚАЗ / EN switch (manual check 3, part 2): the answer language, feed names and Python texts in 3 languages."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.agent_v10 import answer, i18n, verdicts
from src.agent_v10.agent import Agent
from src.agent_v10.api import create_router
from src.agent_v10.facts import answer_language, extract
from src.agent_v10.memory import Memory
from tests.test_agent_v10_agent import FakeLLM


@pytest.mark.parametrize("text, ui, expected", [
    ("Сколько газа?", "kk", "ru"),            # a message with words: its own language
    ("How much gas?", "ru", "en"),
    ("сиыр көңі", "en", "kk"),
    ("160", "kk", "kk"),                      # no words: the interface language
    ("200 l", "ru", "ru"),
    ("−15 °C", "en", "en"),
    ("Сколько газа?", None, "ru"),
])
def test_answer_language(text, ui, expected):
    assert answer_language(text, ui) == expected


@pytest.mark.parametrize("text, materials", [
    ("Тауық саңғырығы мен сиыр көңін салыстыр", ["poultry_manure", "cattle_manure"]),
    ("Шошқа көңі ме, сиыр көңі ме — қайсысы жақсы?", ["swine_manure", "cattle_manure"]),
    ("What is better: pig or cow manure?", ["swine_manure", "cattle_manure"]),
])
def test_feed_names_in_kazakh_and_english(text, materials):
    assert [c["substrate"] for c in extract(text)["facts"]["components"]] == materials


def test_animals_are_not_feeds():
    assert extract("I have 5 cows")["facts"]["components"] == []
    assert extract("5 сиыр бар")["facts"]["animals"] == [{"species": "cow", "count": 5.0}]


def test_python_texts_exist_in_three_languages():
    for table in [i18n.TEXT, verdicts.TEXTS, verdicts.UNIT_WORDS, verdicts.WORDS]:
        for key, row in table.items():
            assert {"ru", "en", "kk"} <= set(row), key
    for table in [answer.TRUST_TEXT, answer.FALLBACK_TEXT, answer.HISTORY_TEXT]:
        assert {"ru", "en", "kk"} <= set(table)


@pytest.mark.parametrize("language, unit", [("en", "L"), ("kk", "л")])
def test_verdict_values_use_the_answer_language(tmp_path, language, unit):
    text = {"en": "1000 litres of cattle slurry, barrel 200 litres", "kk": "1000 литр сиыр көңі, бөшке 200 литр"}[language]
    agent = Agent(Memory(tmp_path / "m.sqlite3"), FakeLLM([], available=False))
    final = next(e for e in agent.run("v", text, use_llm=False) if e["type"] == "answer")
    fits = next(v for v in final["verdicts"] if v["key"] == "fits")
    assert f" {unit}" in fits["value"] and "рабочий" not in fits["value"]


def test_api_passes_the_interface_language(tmp_path):
    app = FastAPI()
    app.include_router(create_router(Agent(Memory(tmp_path / "api.sqlite3"), FakeLLM([], available=False))))
    client = TestClient(app)
    response = client.post("/api/agent/chat", json={"message": "160", "use_llm": False, "ui_language": "kk"})
    assert response.status_code == 200 and '"language": "kk"' in response.text
    bad = client.post("/api/agent/chat", json={"message": "160", "use_llm": False, "ui_language": "de"})
    assert bad.status_code == 422
