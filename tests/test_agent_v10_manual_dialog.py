"""Regression: the 7-message dialog from the manual check (2026-11-16), bugs A–F.

Runs without Ollama (no-LLM path = the same tools and verdicts, template text), so every
number is deterministic. The live-LLM version of the same dialog is in scripts/eval_dialogs.py
(dialog "20. Ручная проверка").
"""
import pytest

from src.agent_v10.agent import Agent, plan_tools, python_first
from src.agent_v10.facts import empty_facts, extract
from src.agent_v10.i18n import t
from src.agent_v10.memory import Memory
from src.agent_v10.tools.registry import run_tool

DIALOG = [
    "У меня 200 литров коровьего навоза, сколько будет газа?",
    "Какую температуру ставить?",
    "Сколько электричества уйдёт на подогрев?",
    "Бочка 200 литров, не утеплена, на улице −15. Есть смысл?",
    "У меня 5 коров, сколько газа в день будет?",
    "У меня 5 коров, сколько газа в день будет?",
    "Хватит газа на газовую плиту?",
]
NOT_FIT = "Партия не поместится"


@pytest.fixture(scope="module")
def turns(tmp_path_factory):
    agent = Agent(Memory(tmp_path_factory.mktemp("manual") / "m.sqlite3"))
    rows = []
    for text in DIALOG:
        events = list(agent.run("manual-dialog", text, use_llm=False))
        rows.append({
            "events": events,
            "final": next(e for e in events if e["type"] == "answer"),
            "facts": next(e for e in events if e["type"] == "facts")["facts"],
            "tools": [e["name"] for e in events if e["type"] == "tool_call" and e["name"] != "verdicts"],
        })
    return rows


def verdicts(turn):
    return {v["key"]: v for v in turn["final"]["verdicts"]}


def card(turn, key):
    return next(c for c in turn["final"]["numbers"] if c["key"] == key)


# --- A. every question is a new question ------------------------------------

def test_a_each_question_gets_its_own_tools(turns):
    assert [t["tools"] for t in turns] == [
        ["estimate_methane"], ["recommend_temperature_regime"], ["estimate_heating_energy"],
        ["estimate_methane", "estimate_heating_energy"],
        ["estimate_daily_production"], ["estimate_daily_production"], ["gas_stove_hours"],
    ]


def test_a_fits_verdict_does_not_stick_to_later_answers(turns):
    for turn in turns:
        assert "fits" not in verdicts(turn)
        assert NOT_FIT not in turn["final"]["explanation"]


def test_a_answers_5_and_7_answer_their_own_question(turns):
    assert set(verdicts(turns[4])) == {"daily_capacity"}
    assert set(verdicts(turns[6])) == {"stove"}
    assert turns[4]["final"]["explanation"] != turns[6]["final"]["explanation"]
    assert "в сутки" in turns[4]["final"]["explanation"]
    assert "конфорк" in turns[6]["final"]["explanation"]


def test_a_irrelevant_verdict_becomes_an_assumption_line(turns):
    """The 200 L batch is larger than the 160 L working volume: said once as an assumption, not as a verdict."""
    assert any("больше рабочего объёма" in a for a in turns[3]["final"]["assumptions"])


def test_a_fits_verdict_still_shown_when_the_message_names_the_batch(tmp_path):
    agent = Agent(Memory(tmp_path / "m.sqlite3"))
    events = list(agent.run("fit", "Загружу 2 тонны навоза КРС в бочку на 200 литров. Сколько будет газа?", use_llm=False))
    final = next(e for e in events if e["type"] == "answer")
    assert "fits" in {v["key"] for v in final["verdicts"]}


# --- B. main demo question: "Бочка 200 литров ... Есть смысл?" --------------

def test_b_barrel_is_the_reactor_and_minus_15_is_outside(turns):
    facts = turns[3]["facts"]
    assert facts["reactor_volume_l"] == 200 and facts["ambient_c"] == -15 and facts["insulation"] == "none"
    assert [(c["substrate"], c["amount"]) for c in facts["components"]] == [("cattle_manure", 200.0)]


def test_b_is_it_worth_it_is_an_energy_balance_with_advice(turns):
    found = verdicts(turns[3])
    assert found["net"]["code"] == "minus"
    advice = found["advice"]
    assert advice["code"] == "eps50" and advice["after"][1] > advice["before"][1]
    heating = turns[3]["final"]["data"]["estimate_heating_energy"]
    assert heating["ambient_c"] == -15 and heating["reactor_volume_l"] == 200


@pytest.mark.parametrize("text,reactor,batch", [
    ("Бочка 200 литров", 200, None),
    ("бочка на 200 литров", 200, None),
    ("резервуар объёмом 300 литров", 300, None),
    ("ёмкость 150 л", 150, None),
    ("реактор 250 л", 250, None),
    ("в бочке 200 литров навоза", None, 200),
])
def test_b_reactor_volume_vs_feed_volume(text, reactor, batch):
    result = extract(text)
    assert result["updates"].get("reactor_volume_l") == reactor
    amounts = [c.get("amount") for c in result["facts"]["components"]]
    assert amounts == ([batch] if batch else [])


# --- C. one reactor source, same inputs -> same numbers -----------------------

def test_c_heating_is_the_same_in_answers_2_and_3(turns):
    regime = card(turns[1], "heating")
    heating = card(turns[2], "heating")
    assert (regime["low"], regime["high"]) == (heating["low"], heating["high"])


def test_c_demo_reactor_200_litres_everywhere(turns):
    for turn in turns[1:3]:
        text = " ".join(turn["final"]["assumptions"])
        assert "250" not in text
    assert turns[2]["final"]["data"]["estimate_heating_energy"]["reactor_volume_l"] == 200


def test_c_heating_tool_equals_regime_tool_for_same_facts():
    facts = {**empty_facts(), "components": [{"substrate": "cattle_manure", "amount": 150, "unit": "l", "state": "slurry"}],
             "reactor_volume_l": 200, "insulation": "none", "ambient_c": -15}
    heating = run_tool("estimate_heating_energy", {}, facts)["data"]["total_kwh"]
    regime = run_tool("recommend_temperature_regime", {}, facts)["data"]["regimes"]
    mesophilic = next(r for r in regime if r["id"] == "mesophilic")["total_cost_kwh"]
    assert heating == mesophilic
    again = run_tool("estimate_heating_energy", {}, facts)["data"]["total_kwh"]
    assert again == heating


# --- D. a clarifying question is asked once -----------------------------------

def test_d_state_question_is_asked_once_and_stays_an_assumption(turns):
    ask = t("ask_state", "ru")
    questions = [turn["final"]["question"] for turn in turns]
    assert questions[0] == ask
    assert ask not in questions[1:]
    assert all(questions.count(q) == 1 for q in questions if q)
    assert any("жидкий" in a for a in turns[1]["final"]["assumptions"])


# --- E. the methane label depends only on where the data comes from -----------

def test_e_methane_label_is_the_same_for_the_same_data(turns):
    labels = {card(turns[i], "methane")["label"] for i in (0, 1, 3)}
    assert labels == {"literature"}


# --- F. new abilities: gas per day from animals, gas stove ---------------------

def test_f_five_cows_per_day(turns):
    data = turns[4]["final"]["data"]["estimate_daily_production"]
    assert data["animals"] == [{"species": "cow", "count": 5.0}]
    assert (data["manure_kg_per_day"]["low"], data["manure_kg_per_day"]["high"]) == (115, 235)
    assert data["reactor_enough"] == "no"
    assert data["reactor_biogas_m3_per_day"]["high"] < data["biogas_m3_per_day"]["low"]
    sources = {s["id"] for s in turns[4]["final"]["sources"]}
    assert "nrcs-awmfh-ch4-2008" in sources
    assert card(turns[4], "manure_day")["label"] == "assumption"


def test_f_repeated_question_gives_the_same_numbers(turns):
    assert turns[4]["final"]["numbers"] == turns[5]["final"]["numbers"]


def test_f_gas_stove_hours(turns):
    data = turns[6]["final"]["data"]["gas_stove_hours"]
    use = data["burner_m3_per_hour"]
    daily = data["biogas_m3_per_day"]
    assert (use["low"], use["high"]) == (0.2, 0.45)
    assert data["hours_per_day"]["low"] == pytest.approx(daily["low"] / 0.45)
    assert data["hours_per_day"]["high"] == pytest.approx(daily["high"] / 0.2)
    assert data["limited_by_reactor"] is True
    assert "gtz-biogas-digest-2" in {s["id"] for s in turns[6]["final"]["sources"]}


def test_f_stove_without_animals_uses_the_batch_per_day():
    facts = {**empty_facts(), "components": [{"substrate": "cattle_manure", "amount": 200, "unit": "l", "state": "slurry"}]}
    result = run_tool("gas_stove_hours", {}, facts)
    assert result["ok"] and result["data"]["basis"] == "batch" and not result["data"]["limited_by_reactor"]


@pytest.mark.parametrize("text,species", [
    ("у меня 5 коров и 20 кур", {"cow": 5, "chicken": 20}),
    ("I have 10 cows and 4 pigs", {"cow": 10, "pig": 4}),
    ("Менде 3 сиыр бар", {"cow": 3}),
    ("200 литров коровьего навоза", {}),
    ("5 сиыр көңі", {}),
])
def test_f_animals_are_extracted(text, species):
    found = {a["species"]: a["count"] for a in extract(text)["updates"].get("animals", [])}
    assert found == species


@pytest.mark.parametrize("text,tools", [
    ("Хватит газа на газовую плиту?", ["gas_stove_hours"]),
    ("Сколько газа в сутки?", ["estimate_daily_production"]),
    ("Есть смысл?", ["estimate_methane", "estimate_heating_energy"]),
    ("Сколько газа будет?", []),
])
def test_router_python_first(text, tools):
    assert [c["name"] for c in python_first(text, empty_facts())] == tools


def test_heating_question_without_money_is_not_economics():
    facts = {**empty_facts(), "components": [{"substrate": "cattle_manure", "amount": 200, "unit": "l"}]}
    assert [c["name"] for c in plan_tools("Сколько электричества уйдёт на подогрев?", facts)] == ["estimate_heating_energy"]


def test_python_plan_gives_the_llm_no_tools(tmp_path):
    """For "5 коров в день" Python runs the tool; the LLM only explains and cannot call estimate_methane again."""
    from tests.test_agent_v10_agent import FakeLLM

    llm = FakeLLM([("text", "Весь навоз даст биогаз в сутки, но бочка мала.")])
    agent = Agent(Memory(tmp_path / "m.sqlite3"), llm)
    events = list(agent.run("plan", "У меня 5 коров, сколько газа в день будет?"))
    assert any(e["type"] == "note" and e["code"] == "python_plan" for e in events)
    assert [c["tools"] for c in llm.calls] == [None]
    tool_calls = [e for e in events if e["type"] == "tool_call"]
    assert [(e["name"], e["by"]) for e in tool_calls] == [("estimate_daily_production", "python"), ("verdicts", "python")]
