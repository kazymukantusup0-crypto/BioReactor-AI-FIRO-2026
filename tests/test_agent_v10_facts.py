"""Agent v10: units and deterministic fact extraction (ru / kk / en)."""
import pytest

from src.agent_v10.facts import detect_language, extract
from src.agent_v10.units import find_quantities, to_base


@pytest.mark.parametrize("amount, unit, family, value", [
    (200, "литров", "volume", 200),
    (2, "ведра", "volume", 20),        # 1 bucket = 10 L (assumption)
    (0.5, "м³", "volume", 500),
    (1.5, "т", "mass", 1500),
    (30, "кг", "mass", 30),
    (3, "buckets", "volume", 30),
])
def test_units_are_normalized_to_litres_or_kilograms(amount, unit, family, value):
    base = to_base(amount, unit)
    assert base["family"] == family
    assert base["value"] == pytest.approx(value)


def test_bucket_assumption_is_reported():
    assert to_base(1, "ведро")["assumption"] == "1 ведро = 10 л"


def test_quantities_with_comma_decimal_and_trailing_dot():
    found = find_quantities("Есть 1,5 т навоза и 200 л.")
    assert [(q["family"], q["value"]) for q in found] == [("mass", 1500), ("volume", 200)]


def test_scenario_1_cattle_manure_in_litres():
    facts = extract("У меня 200 литров коровьего навоза, сколько будет газа?")["facts"]
    component = facts["components"][0]
    assert component["substrate"] == "cattle_manure"
    assert component["value"] == 200 and component["family"] == "volume"
    assert component["state"] is None  # not said -> the tool assumes and asks at the end


def test_scenario_2_winter_uninsulated():
    updates = extract("Какую температуру ставить зимой при −15 на улице, реактор не утеплён?")["updates"]
    assert updates["ambient_c"] == -15
    assert updates["insulation"] == "none"


def test_scenario_4_add_food_waste_keeps_previous_batch():
    first = extract("200 л жидкого навоза КРС")["facts"]
    second = extract("А если добавить 30 кг пищевых отходов?", first)
    substrates = [c["substrate"] for c in second["facts"]["components"]]
    assert substrates == ["cattle_manure", "food_waste"]
    assert second["facts"]["components"][0]["state"] == "slurry"


def test_kazakh_message_is_understood():
    result = extract("Сиыр көңі 200 литр, қанша газ болады?")
    assert result["language"] == "kk"
    assert result["facts"]["components"][0]["substrate"] == "cattle_manure"


def test_reactor_volume_is_not_mistaken_for_the_batch():
    facts = extract("Реактор 470 л, загрузка 114 л навоза КРС, держать 37 °C")["facts"]
    assert facts["reactor_volume_l"] == 470
    assert facts["components"][0]["value"] == 114
    assert facts["target_c"] == 37


def test_new_amount_and_new_substrate_follow_ups():
    facts = extract("200 л навоза КРС")["facts"]
    facts = extract("а если 300 литров?", facts)["facts"]
    assert facts["components"][0]["value"] == 300
    facts = extract("А если это свиной навоз?", facts)["facts"]
    assert facts["components"][0]["substrate"] == "swine_manure"
    assert facts["components"][0]["value"] == 300


def test_measured_properties_and_dry_matter_is_not_dry_state():
    facts = extract("200 л навоза")["facts"]
    result = extract("плотность 1,05, сухое вещество 9 %, органическое вещество 80 %", facts)
    component = result["facts"]["components"][0]
    assert component["density_kg_l"] == 1.05
    assert component["ts_percent"] == 9 and component["vs_percent_of_ts"] == 80
    assert component["state"] != "dry"


def test_days_are_not_taken_as_temperature():
    updates = extract("зимой 30 дней при минус 20 градусов")["updates"]
    assert updates == {"ambient_c": -20, "days": 30}


# Requirement carried over from the old agent bug (tests/test_stage85_research.py):
# sentence punctuation must not change the parsed value.
@pytest.mark.parametrize("text", ["operating_mode=batch. Какой режим?", "operating_mode=batch, сколько газа", "operating_mode = batch!"])
def test_sentence_punctuation_does_not_change_the_operating_mode(text):
    assert extract(text)["facts"]["operating_mode"] == "batch"


@pytest.mark.parametrize("text, language", [("сколько газа", "ru"), ("қанша газ", "kk"), ("how much gas", "en")])
def test_language_detection(text, language):
    assert detect_language(text) == language
