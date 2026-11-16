"""Agent v10: verdicts decided by Python, contradiction check, units, analogues, ≈ values."""
import pytest

from src.agent_v10 import answer, verdicts
from src.agent_v10.facts import empty_facts, extract
from src.agent_v10.ranges import approx_text, center
from src.agent_v10.tools.methane import estimate_methane
from src.agent_v10.tools.registry import run_tool
from src.agent_v10.units import to_base

CATTLE_150L = [{"substrate": "cattle_manure", "amount": 150, "unit": "l", "state": "slurry"}]


def winter_facts(**extra):
    return {**empty_facts(), "components": CATTLE_150L, "ambient_c": -10, "insulation": "none",
            "reactor_volume_l": 200, **extra}


# ---------- verdicts ----------------------------------------------------------------

def test_regime_and_negative_net_verdict_for_the_cold_barrel():
    facts = winter_facts()
    results = [run_tool("recommend_temperature_regime", {}, facts)]
    built = verdicts.build(results, facts)
    items = {item["key"]: item for item in built["data"]["items"]}
    assert items["regime"]["code"] == "mesophilic"
    assert items["net"]["code"] == "minus" and "≈" in items["net"]["text"]
    chosen = next(r for r in results[0]["data"]["regimes"] if r["id"] == "mesophilic")
    assert chosen["net_kwh"]["high"] < 0          # the verdict agrees with the tool numbers


def test_enough_gas_and_net_come_from_gas_plus_heating():
    facts = winter_facts()
    results = [run_tool("estimate_methane", {}, facts), run_tool("estimate_heating_energy", {}, facts)]
    items = {item["key"]: item for item in verdicts.build(results, facts)["data"]["items"]}
    assert items["enough_gas"]["code"] == "no" and items["net"]["code"] == "minus"


def test_fits_verdict_warns_about_two_tonnes_in_a_200_litre_barrel():
    """2000 kg of slurry / 1.0–1.02 kg/L ≈ 1960–2000 L > working volume 160 L (200 L × 0.8)."""
    facts = {**empty_facts(), "reactor_volume_l": 200,
             "components": [{"substrate": "cattle_manure", "amount": 2, "unit": "т", "state": "slurry"}]}
    item = verdicts.fits_verdict(facts, "ru")
    assert item["code"] == "no" and "не поместится" in item["text"] and "160" in item["text"]
    assert verdicts.fits_verdict({**facts, "components": CATTLE_150L}, "ru") is None   # 150 L fits: no noise


def test_fits_uses_the_demo_reactor_when_the_volume_is_unknown():
    facts = {**empty_facts(), "components": [{"substrate": "cattle_manure", "amount": 300, "unit": "l", "state": "slurry"}]}
    assert verdicts.fits_verdict(facts, "ru")["code"] == "no"


def test_best_use_verdict_follows_the_economics_tool():
    facts = {**empty_facts(), "components": [{"substrate": "poultry_manure", "amount": 1, "unit": "т"}]}
    result = run_tool("energy_balance_and_economics", {}, facts)
    item = verdicts.best_use_verdict([result], "ru")
    assert item["code"] == result["data"]["best"]


@pytest.mark.parametrize("key, code, text, expected", [
    ("enough_gas", "no", "Газа хватит на подогрев.", True),
    ("enough_gas", "no", "Газа недостаточно, нужен электронагрев.", False),
    ("enough_gas", "no", "Газа не хватит на подогрев.", False),
    ("enough_gas", "no", "Газ покрывает только 8% тепла.", False),
    ("enough_gas", "yes", "Газа не хватит.", True),
    ("net", "minus", "Баланс будет положительным.", True),
    ("net", "minus", "Баланс отрицательный: подогрев съедает газ.", False),
    ("regime", "mesophilic", "Лучше ставить термофильный режим 52 °C.", True),
    ("regime", "mesophilic", "Мезофильный режим надёжнее термофильного.", False),
    ("fits", "no", "Всё поместится в бочку.", True),
    ("fits", "no", "Партия не поместится в бочку.", False),
    ("best_use", "chp", "Выгоднее всего продавать электричество.", True),
    ("best_use", "chp", "Выгоднее когенерация: электричество и тепло.", False),
])
def test_contradiction_check(key, code, text, expected):
    assert verdicts.contradicts({"key": key, "code": code}, text) is expected


# ---------- units, outputs, analogues ----------------------------------------------------

def test_buckets_and_sacks_are_converted_with_an_assumption():
    assert to_base(5, "вёдер")["value"] == 50
    assert to_base(3, "мешка")["value"] == 150 and to_base(3, "мешка")["assumption"]
    result = estimate_methane([{"substrate": "poultry_manure", "amount": 3, "unit": "мешка"}])
    assert any("мешок" in a for a in result["assumptions"])


def test_tonnes_with_a_decimal_comma():
    component = extract("А если 1,5 тонны силоса?")["facts"]["components"][0]
    assert component["substrate"] == "silage" and component["value"] == 1500


def test_unknown_peel_is_calculated_by_analogy_and_labelled():
    component = extract("У меня 50 кг банановой кожуры")["facts"]["components"][0]
    assert component["substrate"] == "vegetable_waste" and "банан" in component["analog_of"]
    result = estimate_methane([component])
    assert result["ok"] and result["label"] == "assumption"
    assert any("аналогии" in a for a in result["assumptions"]) and result["llm"]["by_analogy"]


def test_material_without_data_and_analogue_gets_an_honest_no_data():
    component = extract("100 кг опилок")["facts"]["components"][0]
    assert component["substrate"] is None and component["unknown_name"] == "опилок"
    result = estimate_methane([component])
    assert not result["ok"] and result["data"]["status"] == "no_data" and "TS" in result["question"]


def test_correction_replaces_the_amount():
    first = extract("У меня 200 л жидкого навоза КРС")["facts"]
    corrected = extract("Нет, не 200, а 300 литров.", first)["facts"]["components"]
    assert len(corrected) == 1 and corrected[0]["value"] == 300


# ---------- ≈ values ------------------------------------------------------------------------

def test_central_estimate_text_and_cards():
    assert center([2.9, 5.2]) == 4 and approx_text([2.9, 5.2]) == "≈4 (2.9–5.2)"
    assert approx_text([-1040, -328]) == "≈−684 (−1040 … −328)"
    assert answer.approx_payload({"methane_m3": [2.9, 5.2], "label": "literature"}) == {
        "methane_m3": "≈4 (2.9–5.2)", "label": "literature"}
    card = answer.number_cards([run_tool("estimate_methane", {}, {**empty_facts(), "components": CATTLE_150L})], "ru")[0]
    assert card["center"] and card["range"] == card["value"]


# ---------- proactive advice ------------------------------------------------------------

def test_cold_barrel_gets_insulation_advice_before_and_after():
    """150 L at −15 °C without insulation: EPS 50 mm cuts U from 6–12 to ≈0.6–0.7 W/(m²·K)."""
    facts = winter_facts(ambient_c=-15)
    item = verdicts.advice_item(facts, "ru")
    assert item["code"] == "eps50" and "пенополистиролом 50 мм" in item["text"]
    assert item["before"][1] < 0 and center(item["after"]) > center(item["before"])
    built = verdicts.build([run_tool("recommend_temperature_regime", {}, facts)], facts)
    assert "advice" in {i["key"] for i in built["data"]["items"]}
    assert any("пенополистирол" in a for a in built["assumptions"])


def test_no_advice_when_the_gain_is_tiny():
    assert verdicts.advice_item(winter_facts(ambient_c=-15, insulation="good"), "ru") is None


def test_u_value_of_50_mm_eps():
    """U = 1/(1/h + d/λ): 1/(1/6 + 0.05/0.035) = 0.627 ... 1/(1/12 + 0.05/0.040) = 0.75 W/(m²·K)."""
    from src.agent_v10.tools.heating import u_value
    u = u_value("eps50")
    assert u["low"] == pytest.approx(0.627, rel=1e-2) and u["high"] == pytest.approx(0.75, rel=1e-2)
