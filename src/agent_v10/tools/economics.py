"""Tool energy_balance_and_economics: what to do with the gas and what it is worth.

One fuel stream, three alternative uses (reused: src/economics/energy_conversion.convert):
    heat only         gas energy × boiler efficiency 0.85–0.90
    electricity only  gas energy × generator efficiency 0.20–0.30
    CHP               gas energy × (0.25 electricity + 0.45 heat)

Own needs of the reactor (from estimate_heating_energy):
    heating (heat) and mixing (electricity).

Net balance per option = produced − own needs.
Value in tenge with the SAVED market prices (data/market/market.sqlite3):
    1 kWh of heat is valued like heat from a natural-gas boiler:
        price per kWh = gas price, ₸/m³ / (9.97 kWh/m³ × 0.9)
    1 kWh of electricity is valued at the electricity tariff.
"""
from __future__ import annotations

import sqlite3

from src.agent_v10.config import MARKET_DB_PATH, METHANE_KWH_PER_M3
from src.agent_v10.i18n import t
from src.agent_v10.ranges import add, make, mid, point, range_text, scale, subtract
from src.agent_v10.tools.common import pair, result, unique_sources
from src.agent_v10.tools.heating import estimate_heating_energy
from src.agent_v10.tools.methane import batch_mass_and_volume, estimate_methane
from src.economics.energy_conversion import convert

BOILER = make(0.85, 0.90)
GENERATOR = make(0.20, 0.30)
CHP_ELECTRIC = point(0.25)
CHP_HEAT = point(0.45)
GAS_BOILER_EFFICIENCY = 0.9

SUMMARY = {
    "summary_gain": {
        "ru": "газ содержит {gas} кВт·ч, на подогрев уходит {heating} кВт·ч; лучший вариант — {best}, выгода {value} ₸.",
        "en": "the gas holds {gas} kWh, heating takes {heating} kWh; best option — {best}, benefit {value} KZT.",
        "kk": "газда {gas} кВт·сағ, қыздыруға {heating} кВт·сағ кетеді; ең жақсы нұсқа — {best}, пайда {value} ₸.",
    },
    "summary_loss": {
        "ru": "газ содержит {gas} кВт·ч, а подогрев требует {heating} кВт·ч — сейчас любой вариант убыточен "
              "(наименьший убыток: {best}, {value} ₸). Сначала утеплите реактор.",
        "en": "the gas holds {gas} kWh but heating needs {heating} kWh — every option loses money now "
              "(smallest loss: {best}, {value} KZT). Insulate the reactor first.",
        "kk": "газда {gas} кВт·сағ, ал қыздыруға {heating} кВт·сағ керек — қазір кез келген нұсқа шығынды "
              "(ең аз шығын: {best}, {value} ₸). Алдымен реакторды жылытыңыз.",
    },
}

OPTION_NAMES = {
    "heat": {"ru": "только тепло (котёл)", "en": "heat only (boiler)", "kk": "тек жылу (қазандық)"},
    "electricity": {"ru": "только электричество (генератор)", "en": "electricity only (generator)", "kk": "тек электр (генератор)"},
    "chp": {"ru": "когенерация: электричество + тепло", "en": "CHP: electricity + heat", "kk": "когенерация: электр + жылу"},
}


def latest_prices(region_prefix: str = "KZ-Karaganda", price_class: str = "household",
                  database=MARKET_DB_PATH) -> dict:
    """Latest saved electricity and natural gas prices; empty dict if none are saved."""
    if not database.exists():
        return {}
    electricity_class = ("household%" if price_class == "household" else "non_household%")
    prices = {}
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    try:
        connection.row_factory = sqlite3.Row
        queries = {
            "electricity": ("electricity", electricity_class),
            "natural_gas": ("natural_gas", "%"),
        }
        for key, (commodity, consumer) in queries.items():
            row = connection.execute(
                "SELECT normalized_value, normalized_unit, effective_from, price_type, consumer_class, tax_basis, source_url "
                "FROM observations WHERE is_test = 0 AND commodity = ? AND region LIKE ? AND consumer_class LIKE ? "
                "AND (tax_basis IS NULL OR tax_basis != 'VAT_excluded') "
                "ORDER BY effective_from DESC LIMIT 1",
                (commodity, region_prefix + "%", consumer),
            ).fetchone()
            if row:
                prices[key] = {"price": float(row["normalized_value"]), "unit": row["normalized_unit"],
                               "date": row["effective_from"], "kind": row["consumer_class"], "url": row["source_url"]}
    except sqlite3.Error:
        return {}
    finally:
        connection.close()
    return prices


def energy_balance_and_economics(components: list[dict], regime: str = "mesophilic", ambient_c: float | None = None,
                                 insulation: str | None = None, reactor_volume_l: float | None = None,
                                 price_class: str | None = None, language: str = "ru",
                                 market_database=MARKET_DB_PATH) -> dict:
    """Net energy balance of the batch and its value in tenge for three gas uses."""
    gas = estimate_methane(components, regime=regime, language=language)
    if not gas["ok"]:
        return {**gas, "name": "energy_balance_and_economics"}
    batch = batch_mass_and_volume(components, language)
    days = gas["data"]["days"]
    heat = estimate_heating_energy(feed_mass_kg=batch["mass_kg"], feed_volume_l=batch["volume_l"],
                                   reactor_volume_l=reactor_volume_l, insulation=insulation, ambient_c=ambient_c,
                                   target_c=gas["data"]["temperature_c"], days=mid(days), language=language)
    heating_need = heat["data"]["heating_kwh"]
    mixing_need = heat["data"]["mixing_kwh"]

    energy = convert(gas["data"]["methane_m3"], METHANE_KWH_PER_M3, point(1.0), BOILER, GENERATOR, CHP_HEAT, CHP_ELECTRIC)
    all_needs_as_electricity = add(heating_need, mixing_need)  # electric heater + mixer
    options = {
        "heat": {"heat_kwh": subtract(energy["heat_only_kwh"], heating_need), "electricity_kwh": scale(mixing_need, -1)},
        "electricity": {"heat_kwh": point(0.0),
                        "electricity_kwh": subtract(energy["electricity_only_kwh"], all_needs_as_electricity)},
        "chp": {"heat_kwh": subtract(energy["chp_heat_kwh"], heating_need),
                "electricity_kwh": subtract(energy["chp_electricity_kwh"], mixing_need)},
    }

    assumptions = gas["assumptions"] + heat["assumptions"] + [t("assume_boiler", language), t("assume_generator", language)]
    prices = latest_prices(price_class=price_class or "household", database=market_database)
    heat_price = None
    if "natural_gas" in prices:
        heat_price = prices["natural_gas"]["price"] / (METHANE_KWH_PER_M3 * GAS_BOILER_EFFICIENCY)
        assumptions.append(t("price_used", language, what=t("word_gas", language),
                             price=prices["natural_gas"]["price"], date=prices["natural_gas"]["date"],
                             kind=prices["natural_gas"]["kind"]))
    electricity_price = prices.get("electricity", {}).get("price")
    if electricity_price is not None:
        assumptions.append(t("price_used", language, what=t("word_electricity", language),
                             price=electricity_price, date=prices["electricity"]["date"], kind=prices["electricity"]["kind"]))
    if not prices:
        assumptions.append(t("price_missing", language))

    for option in options.values():
        if heat_price is not None and electricity_price is not None:
            option["value_kzt"] = {
                "low": option["heat_kwh"]["low"] * heat_price + option["electricity_kwh"]["low"] * electricity_price,
                "high": option["heat_kwh"]["high"] * heat_price + option["electricity_kwh"]["high"] * electricity_price,
            }
        else:
            option["value_kzt"] = None
    best = max(options, key=lambda key: mid(options[key]["value_kzt"]) if options[key]["value_kzt"]
               else mid(options[key]["heat_kwh"]) + mid(options[key]["electricity_kwh"]))

    data = {
        "status": "ok", "methane_m3": gas["data"]["methane_m3"], "gas_energy_kwh": gas["data"]["energy_kwh"],
        "heating_need_kwh": heating_need, "mixing_need_kwh": mixing_need, "options": options, "best": best,
        "prices": prices, "heat_price_kzt_per_kwh": heat_price, "regime": regime, "days": days,
    }
    llm = {
        "gas_energy_kwh": pair(gas["data"]["energy_kwh"]),
        "own_heating_kwh": pair(heating_need), "own_mixing_kwh": pair(mixing_need),
        "options": [{
            "use": OPTION_NAMES[key].get(language, OPTION_NAMES[key]["ru"]),
            "net_heat_kwh": pair(value["heat_kwh"]), "net_electricity_kwh": pair(value["electricity_kwh"]),
            "value_kzt": pair(value["value_kzt"]) if value["value_kzt"] else None,
        } for key, value in options.items()],
        "best_use": OPTION_NAMES[best].get(language, OPTION_NAMES[best]["ru"]),
        "prices_saved": bool(prices), "label": "assumption",
        "wall": heat["llm"]["wall"],
    }
    best_value = options[best]["value_kzt"]
    all_negative = best_value is not None and best_value["high"] < 0
    llm["all_options_lose_money"] = all_negative
    key = "summary_loss" if all_negative else "summary_gain"
    llm["summary"] = SUMMARY[key].get(language, SUMMARY[key]["ru"]).format(
        gas=range_text(pair(gas["data"]["energy_kwh"])), heating=range_text(pair(heating_need)),
        best=llm["best_use"], value=range_text(pair(best_value)) if best_value else "?")
    return result("energy_balance_and_economics", ok=True, data=data, llm=llm, assumptions=assumptions,
                  sources=unique_sources(gas["sources"] + heat["sources"]), label="assumption",
                  question=gas["question"] or heat["question"])
