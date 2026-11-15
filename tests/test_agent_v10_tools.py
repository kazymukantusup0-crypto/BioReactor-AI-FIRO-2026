"""Agent v10 tools: physics checked against hand calculations."""
import math
import sqlite3

import pytest

from src.agent_v10.config import METHANE_KWH_PER_M3
from src.agent_v10.tools import economics
from src.agent_v10.tools.heating import cylinder, estimate_heating_energy, u_value
from src.agent_v10.tools.knowledge import search_knowledge
from src.agent_v10.tools.methane import estimate_methane
from src.agent_v10.tools.regimes import _choose, recommend_temperature_regime
from src.agent_v10.tools.registry import TOOL_NAMES, TOOL_SCHEMAS, ToolCallError, run_tool
from src.agent_v10.tools.scenarios import compare_scenarios, default_scenarios
from src.agent_v10.facts import empty_facts

CATTLE_200L = [{"substrate": "cattle_manure", "amount": 200, "unit": "l", "state": "slurry"}]


def approx_range(result, low, high, rel=1e-3):
    return result["low"] == pytest.approx(low, rel=rel) and result["high"] == pytest.approx(high, rel=rel)


# ---------- estimate_methane ------------------------------------------------

def test_methane_200_litres_cattle_slurry_matches_hand_calculation():
    """Hand calculation:
    mass = 200 L × 1.013 kg/L = 202.6 kg  (Oliveira RM1 density)
    yield: Eftaxias 0.0701 × 276 = 19.348 L/kg; Oliveira 0.1144 × 250 = 28.6 L/kg
    potential = 202.6 × 19.348 / 1000 = 3.920 m³ ... 202.6 × 28.6 / 1000 = 5.794 m³
    mesophilic share 75–90 %  -> 2.940 ... 5.215 m³ CH4
    biogas = 2.940 / 0.60 = 4.900 ... 5.215 / 0.55 = 9.482 m³
    energy = 9.97 × CH4 = 29.31 ... 51.99 kWh
    """
    result = estimate_methane(CATTLE_200L)
    data = result["data"]
    assert result["ok"] and result["label"] == "literature"
    assert approx_range(data["wet_mass_kg"], 202.6, 202.6)
    assert approx_range(data["methane_potential_m3"], 3.920, 5.794)
    assert approx_range(data["methane_m3"], 2.940, 5.215)
    assert approx_range(data["biogas_m3"], 4.900, 9.482)
    assert approx_range(data["energy_kwh"], 2.940 * 9.97, 5.215 * 9.97)
    assert result["llm"]["methane_m3"] == [2.9, 5.2]


def test_energy_uses_fnr_methane_heating_value():
    assert METHANE_KWH_PER_M3 == 9.97


def test_mass_input_uses_no_density_and_fallback_composition_is_an_assumption():
    """30 kg food waste: VS 0.20×0.85=0.17 ... 0.30×0.95=0.285; BMP 400–500 -> 2.04 ... 4.275 m³ potential."""
    result = estimate_methane([{"substrate": "food_waste", "amount": 30, "unit": "kg"}])
    assert approx_range(result["data"]["methane_potential_m3"], 2.04, 4.275)
    assert result["label"] == "assumption"


def test_user_ts_vs_replace_literature_composition():
    """100 kg slurry, TS 10 %, VS 80 % of TS -> VS 0.08; BMP 200–276 -> 1.6 ... 2.208 m³ potential."""
    result = estimate_methane([{"substrate": "cattle_manure", "amount": 100, "unit": "kg", "state": "slurry",
                                "ts_percent": 10, "vs_percent_of_ts": 80}])
    assert approx_range(result["data"]["methane_potential_m3"], 1.6, 2.208)


def test_always_gives_a_range_and_asks_one_question_at_the_end():
    result = estimate_methane([{"substrate": "cattle_manure", "amount": 200, "unit": "литров"}])
    assert result["ok"] and result["data"]["methane_m3"]["low"] > 0
    assert any("жидкий" in a for a in result["assumptions"])
    assert result["question"] and result["question"].endswith(".")


def test_unknown_amount_returns_a_question_not_a_number():
    result = estimate_methane([{"substrate": "cattle_manure"}])
    assert not result["ok"] and "Сколько" in result["question"]


def test_mixture_is_sum_of_components():
    mix = estimate_methane(CATTLE_200L + [{"substrate": "food_waste", "amount": 30, "unit": "kg"}])
    manure = estimate_methane(CATTLE_200L)
    food = estimate_methane([{"substrate": "food_waste", "amount": 30, "unit": "kg"}])
    for key in ["low", "high"]:
        assert mix["data"]["methane_m3"][key] == pytest.approx(manure["data"]["methane_m3"][key] + food["data"]["methane_m3"][key])


def test_regime_changes_share_of_potential():
    meso = estimate_methane(CATTLE_200L, regime="mesophilic")["data"]
    psychro = estimate_methane(CATTLE_200L, regime="psychrophilic")["data"]
    assert meso["methane_potential_m3"] == psychro["methane_potential_m3"]
    assert psychro["methane_m3"]["high"] < meso["methane_m3"]["high"]


# ---------- estimate_heating_energy ---------------------------------------

def test_cylinder_geometry():
    """V = 1 m³, H = D: D = (4/π)^(1/3) = 1.0839 m, A = 1.5 π D² = 5.536 m²."""
    geometry = cylinder(1000)
    assert geometry["diameter_m"] == pytest.approx((4 / math.pi) ** (1 / 3))
    assert geometry["area_m2"] == pytest.approx(5.536, rel=1e-3)


def test_u_values_from_insulation_layer():
    """U = 1/(1/h + d/λ): basic 1/(1/6+0.05/0.035)=0.627 ... 1/(1/12+0.03/0.04)=1.2."""
    assert approx_range(u_value("none"), 6.0, 12.0)
    assert approx_range(u_value("basic"), 0.627, 1.2, rel=1e-2)
    assert u_value("good")["high"] < u_value("basic")["low"]


def test_heating_hand_calculation():
    """100 kg from 7 °C to 37 °C, 1000 L reactor, no insulation, 7 °C outside, 10 days:
    feed: 100 × 4.0 × 30 / 3600 = 3.333 kWh (eff 1.0) ... 100 × 4.18 × 30 / 3600 / 0.95 = 3.667 kWh
    losses: UA = 6 × 5.536 = 33.2 W/K; 33.2 × 30 × 240 h / 1000 = 239.1 kWh (eff 1.0)
    mixing: 100 W × 2 h × 10 d = 2 kWh
    """
    result = estimate_heating_energy(feed_mass_kg=100, reactor_volume_l=1000, insulation="none", ambient_c=7,
                                     target_c=37, days=10, feed_initial_c=7, mixing_power_w=100, mixing_hours_per_day=2)
    data = result["data"]
    assert approx_range(data["feed_heating_kwh"], 3.333, 4.18 * 30 / 36 / 0.95, rel=1e-3)
    assert data["heat_loss_kwh"]["low"] == pytest.approx(6 * 5.536 * 30 * 240 / 1000, rel=1e-3)
    assert approx_range(data["mixing_kwh"], 2.0, 2.0)


def test_insulation_reduces_heat_loss_a_lot():
    args = dict(feed_mass_kg=200, reactor_volume_l=250, ambient_c=-15, target_c=37, days=30)
    bare = estimate_heating_energy(insulation="none", **args)["data"]["total_kwh"]
    good = estimate_heating_energy(insulation="good", **args)["data"]["total_kwh"]
    assert good["high"] < bare["low"] / 5


def test_warm_weather_needs_no_heat_loss_compensation():
    data = estimate_heating_energy(feed_mass_kg=100, reactor_volume_l=150, insulation="none", ambient_c=40,
                                   target_c=37, days=10, feed_initial_c=40)["data"]
    assert data["heat_loss_kwh"]["high"] == 0 and data["feed_heating_kwh"]["high"] == 0


def test_heating_assumptions_and_question_when_reactor_unknown():
    result = estimate_heating_energy(feed_volume_l=200)
    assert result["ok"] and result["data"]["reactor_volume_l"] == 250
    assert result["question"]


# ---------- recommend_temperature_regime ---------------------------------

def test_warm_climate_prefers_psychrophilic():
    result = recommend_temperature_regime(CATTLE_200L, ambient_c=20, insulation="basic", reactor_volume_l=250)
    assert result["data"]["recommended"] == "psychrophilic"


def test_cold_uninsulated_reactor_recommends_stable_regime_and_insulation():
    result = recommend_temperature_regime(CATTLE_200L, ambient_c=-15, insulation="none", reactor_volume_l=250)
    assert result["data"]["recommended"] == "mesophilic"
    assert result["data"]["reason"] == "deficit"
    assert result["data"]["what_if_good_insulation"]["net_kwh"]["high"] > 0
    assert "summary" in result["llm"]


def _case(regime, net_low, net_high, gas=40):
    return {"id": regime, "net_kwh": {"low": net_low, "high": net_high}, "gas_heat_kwh": {"low": gas, "high": gas},
            "methane_m3": {"low": 1, "high": 2}, "days": {"low": 20, "high": 30}}


def test_thermophilic_needs_a_clear_margin_over_mesophilic():
    slightly = [_case("mesophilic", 10, 20), _case("thermophilic", 12, 24)]
    assert _choose(slightly, "net_energy") == (slightly[0], "stable_over_thermo")
    clearly = [_case("mesophilic", 10, 20), _case("thermophilic", 40, 60)]
    assert _choose(clearly, "net_energy") == (clearly[1], "best_net")


# ---------- compare_scenarios ---------------------------------------------

def test_compare_mixture_against_previous_batch():
    facts = {**empty_facts(), "components": CATTLE_200L + [{"substrate": "food_waste", "amount": 30, "unit": "kg"}]}
    result = compare_scenarios(default_scenarios(facts), ambient_c=10, insulation="good", reactor_volume_l=300)
    first, mix = result["data"]["scenarios"]
    assert len(mix["components"]) == 2 and len(first["components"]) == 1
    assert mix["methane_difference_m3"]["low"] > 0


# ---------- energy_balance_and_economics ---------------------------------

def _market_db(path):
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE observations (commodity TEXT, region TEXT, normalized_value TEXT, normalized_unit TEXT,"
                       " effective_from TEXT, price_type TEXT, consumer_class TEXT, tax_basis TEXT, source_url TEXT, is_test INT)")
    connection.executemany("INSERT INTO observations VALUES (?,?,?,?,?,?,?,?,?,0)", [
        ("electricity", "KZ-Karaganda", "20", "kWh", "2026-10-31", "reference", "household_tier1", "statistics", "u"),
        ("natural_gas", "KZ-Karaganda", "54.81", "m3", "2026-10-31", "reference", "household_statistics", "statistics", "u"),
    ])
    connection.commit()
    connection.close()


def test_economics_uses_saved_prices(tmp_path):
    database = tmp_path / "market.sqlite3"
    _market_db(database)
    result = economics.energy_balance_and_economics(CATTLE_200L, ambient_c=10, insulation="good", reactor_volume_l=250,
                                                    market_database=database)
    assert result["data"]["prices"]["electricity"]["price"] == 20
    assert result["data"]["heat_price_kzt_per_kwh"] == pytest.approx(54.81 / (9.97 * 0.9))
    heat = result["data"]["options"]["heat"]
    expected_low = heat["heat_kwh"]["low"] * 54.81 / (9.97 * 0.9) + heat["electricity_kwh"]["low"] * 20
    assert heat["value_kzt"]["low"] == pytest.approx(expected_low)


def test_economics_without_prices_says_so(tmp_path):
    result = economics.energy_balance_and_economics(CATTLE_200L, market_database=tmp_path / "missing.sqlite3")
    assert result["data"]["options"]["heat"]["value_kzt"] is None
    assert any("цен" in a for a in result["assumptions"])


def test_economics_flags_loss_in_cold_uninsulated_case(tmp_path):
    database = tmp_path / "market.sqlite3"
    _market_db(database)
    result = economics.energy_balance_and_economics(CATTLE_200L, ambient_c=-15, insulation="none",
                                                    reactor_volume_l=250, market_database=database)
    assert result["llm"]["all_options_lose_money"] is True


# ---------- search_knowledge and registry ---------------------------------

def test_search_knowledge_returns_quotes_with_sources():
    result = search_knowledge("какую температуру держать", "cattle_manure")
    assert result["ok"] and result["llm"]["quotes"] and result["sources"]


def test_registry_has_seven_tools_with_schemas():
    assert len(TOOL_SCHEMAS) == 7
    assert set(TOOL_NAMES) == {"estimate_methane", "estimate_heating_energy", "recommend_temperature_regime",
                               "compare_scenarios", "energy_balance_and_economics", "search_knowledge",
                               "extract_batch_facts"}


def test_registry_fills_arguments_from_memory_and_rejects_unknown_tools():
    facts = {**empty_facts(), "components": CATTLE_200L}
    assert run_tool("estimate_methane", {}, facts)["llm"]["methane_m3"] == [2.9, 5.2]
    with pytest.raises(ToolCallError):
        run_tool("make_coffee", {}, facts)


def test_registry_default_batch_when_feedstock_unknown():
    facts = {**empty_facts(), "ambient_c": -15, "insulation": "none"}
    result = run_tool("recommend_temperature_regime", {}, facts)
    assert result["ok"] and "типовой партии" in result["assumptions"][0]


def test_registry_normalizes_llm_state_words():
    facts = {**empty_facts()}
    result = run_tool("estimate_methane", {"components": [{"substrate": "cattle_manure", "amount": 200,
                                                           "unit": "l", "state": "liquid"}]}, facts)
    assert result["ok"] and result["data"]["components"][0]["state"] == "slurry"
