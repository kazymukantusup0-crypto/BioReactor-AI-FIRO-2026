"""Regression: manual check 2 (2026-11-16), bugs H–O — without the LLM, deterministic.

The live-LLM versions are dialogs 21 and 22 in scripts/eval_dialogs.py.
"""
import re

import pytest

from src.agent_v10 import answer
from src.agent_v10.agent import Agent
from src.agent_v10.facts import extract
from src.agent_v10.memory import Memory
from src.agent_v10.tools.methane import estimate_methane
from src.agent_v10.tools.registry import run_tool

DIALOG = [
    "У меня 200 литров коровьего навоза, сколько будет газа?",
    "Сколько дней ждать, пока газ пойдёт?",
    "Что лучше: куриный помёт или коровий навоз?",
    "А если 100 л навоза и 20 кг соломы?",
    "У меня 150 л свиного навоза, сколько газа?",
    "Ой, не свиного, а коровьего",
    "И не 150, а 300",
    "А что было в самом начале?",
]
LONG = [
    "У меня 200 литров коровьего навоза, сколько будет газа?", "Жидкий.", "Какую температуру ставить?",
    "Сколько электричества уйдёт на подогрев?", "Бочка 200 литров, не утеплена, на улице −15. Есть смысл?",
    "Сколько дней ждать, пока газ пойдёт?", "Что лучше: куриный помёт или коровий навоз?", "А если добавить 20 кг соломы?",
    "Почему мезофильный режим устойчивее?", "Что выгоднее: тепло или электричество?",
    "У меня 5 коров, сколько газа в день будет?", "Хватит газа на газовую плиту?", "Какая завтра погода в Астане?",
    "У меня 150 л свиного навоза, сколько газа?", "Ой, не свиного, а коровьего", "И не 150, а 300",
    "Сколько дней ждать, пока газ пойдёт?", "Какую температуру ставить?", "Сколько это в тенге?",
    "У меня 100 л свиного навоза. Сколько газа?", "Нет, не свиного, а коровьего.", "И не 100, а 250.",
    "А что было в самом начале?",
]


def play(tmp_path_factory, messages, name):
    agent = Agent(Memory(tmp_path_factory.mktemp(name) / "m.sqlite3"))
    rows = []
    for text in messages:
        events = list(agent.run(name, text, use_llm=False))
        rows.append({"final": next(e for e in events if e["type"] == "answer"),
                     "facts": next(e for e in events if e["type"] == "facts")["facts"],
                     "events": events})
    return rows


@pytest.fixture(scope="module")
def turns(tmp_path_factory):
    return play(tmp_path_factory, DIALOG, "manual2")


@pytest.fixture(scope="module")
def long_turns(tmp_path_factory):
    return play(tmp_path_factory, LONG, "long")


def verdict(turn, key):
    return next((v for v in turn["final"]["verdicts"] if v["key"] == key), None)


def feed(turn):
    return [(c["substrate"], c["amount"]) for c in turn["facts"]["components"]]


# --- H. first gas is not the digestion time -------------------------------------

def test_h_first_gas_and_full_digestion_are_two_numbers(turns):
    final = turns[1]["final"]
    cards = {c["key"]: c for c in final["numbers"]}
    assert (cards["first_gas"]["low"], cards["first_gas"]["high"]) == (1, 2)
    assert (cards["full_digestion"]["low"], cards["full_digestion"]["high"]) == (25, 35)
    assert "не ожидание газа" in final["explanation"]
    assert "gtz-biogas-digest-2-startup" in {s["id"] for s in final["sources"]}


@pytest.mark.parametrize("text,bad", [
    ("С 200 литров коровьего навоза газ начнёт выходить через ≈30 (25–35) дней.", True),
    ("Газ пойдёт через 25 дней.", True),
    ("Первый газ появится через 1–2 дня, полное сбраживание — 25–35 дней.", False),
    ("Полное сбраживание занимает около 30 дней.", False),
])
def test_h_science_check_catches_first_gas_in_30_days(text, bad):
    assert bool(answer.science_problems(text)) is bad


def test_h_no_template_calls_the_digestion_time_a_wait_for_gas():
    """All templates: the digestion time is never described as the time until the gas starts."""
    import pathlib
    texts = " ".join(p.read_text(encoding="utf-8") for p in pathlib.Path("src/agent_v10").rglob("*.py"))
    assert not re.search(r"газ\w*\s+(?:начн|пойд|появ)\w*[^\"\n]{0,30}через\s*\{", texts)


# --- I. comparing two feeds ----------------------------------------------------------

def test_i_compare_two_feeds_at_the_same_volume(turns):
    final = turns[2]["final"]
    titles = [c["title"] for c in final["numbers"]]
    assert any("Птичий помёт" in t for t in titles) and any("Навоз КРС" in t for t in titles)
    best = verdict(turns[2], "best_feed")
    assert best["code"] == "poultry_manure" and "раза" in best["text"] and "азот" in best["text"]
    assert not any("утепл" in a for a in final["assumptions"])
    data = final["data"]["compare_feedstocks"]
    assert data["volume_l"] == 200  # the remembered 200 L, the same for both feeds


def test_i_difference_card_is_not_called_extra():
    assert answer.TITLES["methane_change"]["ru"].startswith("Разница")


# --- J. mixture volume: "no" when larger, and where the litres come from -------------------

def test_j_straw_volume_is_explained_and_does_not_fit_is_no():
    facts = extract("Бочка 200 литров. У меня 100 л навоза и 20 кг соломы, сколько газа?")["facts"]
    from src.agent_v10 import verdicts
    built = verdicts.build([run_tool("estimate_methane", {}, facts)], facts, "ru", {"text": "", "updates": {"components": 1}})
    fits = next(i for i in built["data"]["items"] if i["key"] == "fits")
    assert fits["code"] == "no" and fits["value"].startswith("нет")
    assert "насыпная плотность" in fits["text"] and "0.058" in fits["text"]


# --- K. pig slurry -----------------------------------------------------------------------

def test_k_pig_slurry_step_by_step():
    """150 L × 1.0 kg/L = 150 kg; KTBL 2025 "Schweinegülle" 13 m³ biogas/t × 63 % CH4 = 8.19 L CH4/kg ± 15 %;
    a practical yield of working plants: the mesophilic regime share is NOT applied again."""
    result = estimate_methane([{"substrate": "swine_manure", "amount": 150, "unit": "l"}])
    methane = result["data"]["methane_m3"]
    assert methane["low"] == pytest.approx(150 * 13 * 0.63 * 0.85 / 1000)
    assert methane["high"] == pytest.approx(150 * 13 * 0.63 * 1.15 / 1000)
    assert any("KTBL 2025" in a and "TS 2.2–3.2" in a for a in result["assumptions"])
    assert not any("лабораторного потенциала" in a for a in result["assumptions"])
    assert "ktbl-526-2025" in {s["id"] for s in result["sources"]}


def test_k_cattle_slurry_still_uses_measured_profiles():
    result = estimate_methane([{"substrate": "cattle_manure", "amount": 200, "unit": "l"}])
    assert not any("KTBL" in a for a in result["assumptions"])


# --- L / M. corrections update the fact and recalculate -------------------------------------

def test_l_feed_correction_recalculates(turns):
    assert feed(turns[4]) == [("swine_manure", 150.0)] and feed(turns[5]) == [("cattle_manure", 150.0)]
    swine = {c["key"]: c for c in turns[4]["final"]["numbers"]}["methane"]
    cattle = {c["key"]: c for c in turns[5]["final"]["numbers"]}["methane"]
    assert (swine["low"], swine["high"]) != (cattle["low"], cattle["high"])
    assert turns[5]["final"]["data"]["estimate_methane"]["components"][0]["substrate"] == "cattle_manure"


def test_l_text_naming_another_feed_is_rejected():
    materials = {"swine_manure"}
    assert answer.wrong_material("С 150 л коровьего навоза получится 0.78 м³ биогаза.", materials, "ru")
    assert not answer.wrong_material("С 150 л свиного навоза получится 2.2 м³ метана.", materials, "ru")
    assert not answer.wrong_material("Не свиного, а коровьего — пересчитал.", {"cattle_manure"}, "ru")


def test_m_amount_correction_without_unit_recalculates(turns):
    assert feed(turns[6]) == [("cattle_manure", 300.0)]
    assert turns[6]["final"]["numbers"] and turns[6]["final"]["explanation"]


def test_m_the_answer_is_never_empty(turns, long_turns):
    for turn in turns + long_turns:
        assert turn["final"]["explanation"].strip()
    assert "Не понял" in answer.empty_fallback({}, {}, "ru")
    assert "Запомнил" in answer.empty_fallback({"components": [1]}, {"components": [
        {"substrate": "cattle_manure", "amount": 300, "base_unit": "L"}]}, "ru")


# --- N. history question ---------------------------------------------------------------------

def test_n_history_is_a_recap_without_calculation(turns):
    final = turns[7]["final"]
    assert final["mode"] == "history" and not final["numbers"] and not final["tools"]
    text = final["explanation"]
    assert "«У меня 200 литров коровьего навоза, сколько будет газа?»" in text
    assert text.index("150 л свиной навоз") < text.index("150 л навоз КРС (исправление)") < text.index("300 л навоз КРС (исправление)")


# --- O. long dialog: facts survive 23 messages -------------------------------------------------

def test_o_long_dialog_keeps_facts_and_corrections(long_turns):
    assert len(long_turns) == 23
    assert feed(long_turns[15]) == [("cattle_manure", 300.0)]
    assert feed(long_turns[19]) == [("swine_manure", 100.0)]
    assert feed(long_turns[20]) == [("cattle_manure", 100.0)]
    assert feed(long_turns[21]) == [("cattle_manure", 250.0)]
    assert long_turns[21]["facts"]["reactor_volume_l"] == 200 and long_turns[21]["facts"]["ambient_c"] == -15
    assert "250 л навоз КРС (исправление)" in long_turns[22]["final"]["explanation"]
    assert verdict(long_turns[16], "startup")["code"] == "cattle"


def test_vent_the_gas_is_not_grass():
    """"стравить" (vent) contains "травить": a material name must start a word."""
    from src.agent_v10 import substrates
    assert not substrates.recognize("Первые два заполнения газгольдера стравить.")
    assert [m["material"] for m in substrates.recognize("трава и навоз")][:1] == ["grass"]


@pytest.mark.parametrize("text", ["Ой, не свиного, а коровьего", "И не 150, а 300"])
def test_a_correction_is_recalculated_by_python(text):
    from src.agent_v10.agent import python_first
    facts = extract("У меня 150 л свиного навоза, сколько газа?")["facts"]
    updates = extract(text, facts)["updates"]
    assert [c["name"] for c in python_first(text, facts, updates)] == ["estimate_methane"]


def test_j_reactor_named_earlier_and_compare_says_nothing_about_insulation(tmp_path):
    agent = Agent(Memory(tmp_path / "m.sqlite3"))
    finals = {}
    for text in ["У меня 200 литров коровьего навоза, сколько будет газа?",
                 "Бочка 200 литров, не утеплена, на улице −15. Есть смысл?",
                 "Что лучше: куриный помёт или коровий навоз?", "А если 100 л навоза и 20 кг соломы?"]:
        events = list(agent.run("j", text, use_llm=False))
        finals[text] = next(e for e in events if e["type"] == "answer")
    worth = finals["Бочка 200 литров, не утеплена, на улице −15. Есть смысл?"]
    assert any("без утепления" in a for a in worth["assumptions"])
    assert not any("утепление «" in a for a in worth["assumptions"])
    compare = finals["Что лучше: куриный помёт или коровий навоз?"]
    assert not any("утепл" in a for a in compare["assumptions"])
    fits = next(v for v in finals["А если 100 л навоза и 20 кг соломы?"]["verdicts"] if v["key"] == "fits")
    assert fits["code"] == "no" and "насыпная плотность" in fits["text"]


@pytest.mark.parametrize("text,tools", [
    ("Сколько электричества уйдёт на подогрев?", ["estimate_heating_energy"]),
    ("Хватит газа на подогрев?", ["estimate_methane", "estimate_heating_energy"]),
    ("Почему мезофильный режим устойчивее?", ["search_knowledge"]),
    ("Что выгоднее: тепло или электричество?", ["energy_balance_and_economics"]),
    ("Сколько это в тенге?", ["energy_balance_and_economics"]),
    ("А если утеплить бочку?", []),
    ("Какую температуру ставить зимой при −15 на улице, реактор 250 литров, не утеплён?", []),
    ("Қыста сыртта −20 градус, реактор жылытылмаған, 300 литр сиыр көңі бар. Қандай температура қою керек?", []),
])
def test_python_routes_of_manual_check_2(text, tools):
    from src.agent_v10.agent import python_first
    from src.agent_v10.facts import empty_facts
    assert [c["name"] for c in python_first(text, empty_facts())] == tools


def test_why_mesophilic_is_answered_from_the_regime_table_with_sources():
    from src.agent_v10.facts import empty_facts
    result = run_tool("search_knowledge", {"query": "Почему мезофильный режим устойчивее?"}, empty_facts())
    assert result["llm"]["quotes"][0].startswith("мезофильный") and "устойчив" in result["llm"]["quotes"][0]
    assert {"fao_environment", "moset2015"} <= {s["id"] for s in result["sources"]}


def test_pig_vs_cattle_explains_dilution_with_a_source_in_one_sentence():
    from src.agent_v10 import verdicts
    from src.agent_v10.tools.feedstock import compare_feedstocks
    result = compare_feedstocks(["swine_manure", "cattle_manure"], 200)
    text = verdicts.best_feed_verdict([result], "ru")["text"]
    assert text.count("Почему:") == 1 and "разбавлена" in text and "Møller" in text
    assert "moller2004" in {s["id"] for s in result["sources"]}
    other = verdicts.best_feed_verdict([compare_feedstocks(["poultry_manure", "cattle_manure"], 200)], "ru")["text"]
    assert "Почему:" not in other
