"""Key conclusions ("verdicts") calculated by Python. The LLM only retells them.

Why: the number check (answer.py) proves that every number in the LLM text comes
from a tool, but not that the CONCLUSION is right. In a live test the model said
"the gas is enough for heating" when the gas covered 3–13 % of it. So every key
conclusion is decided here, given to the LLM ready-made, shown in the UI, and the
LLM text is checked against it (contradicts() -> regenerate once -> template).

Verdicts:
    regime      recommended temperature regime and why      (recommend_temperature_regime)
    net         sign of the net energy balance, ≈ and range  (regime / gas+heating / scenarios)
    enough_gas  is the gas enough to keep the reactor warm   (estimate_methane + estimate_heating_energy)
    fits        does the batch fit the working volume        (facts: batch + reactor, demo reactor if unknown)
    best_use    heat vs electricity vs CHP                   (energy_balance_and_economics)
"""
from __future__ import annotations

import re

from src.agent_v10 import substrates
from src.agent_v10.config import demo_reactor
from src.agent_v10.ranges import approx_text, center, subtract
from src.agent_v10.tools.common import pair, result
from src.agent_v10.tools.derived import gas_vs_heating
from src.agent_v10.tools.methane import component_mass, normalize_component

TEXTS = {
    "regime": {
        "ru": "Рекомендуемый режим — {regime}: {reason}.",
        "en": "Recommended regime — {regime}: {reason}.",
        "kk": "Ұсынылған режим — {regime}: {reason}.",
    },
    "net_minus": {
        "ru": "Чистый энергобаланс отрицательный: {value} кВт·ч — подогрев забирает больше энергии, чем даёт газ.",
        "en": "The net energy balance is negative: {value} kWh — heating takes more energy than the gas gives.",
        "kk": "Таза энергия балансы теріс: {value} кВт·сағ — қыздыру газ беретіннен көп энергия алады.",
    },
    "net_plus": {
        "ru": "Чистый энергобаланс положительный: {value} кВт·ч — газа больше, чем уходит на подогрев.",
        "en": "The net energy balance is positive: {value} kWh — the gas gives more than the heating takes.",
        "kk": "Таза энергия балансы оң: {value} кВт·сағ — газ қыздыруға кететіннен көп.",
    },
    "net_uncertain": {
        "ru": "Чистый энергобаланс около нуля: {value} кВт·ч — может быть и плюс, и минус.",
        "en": "The net energy balance is close to zero: {value} kWh — it can go either way.",
        "kk": "Таза энергия балансы нөлге жақын: {value} кВт·сағ — оң да, теріс те болуы мүмкін.",
    },
    "enough_no": {
        "ru": "Газа не хватит на подогрев: он покрывает {value}% нужного тепла.",
        "en": "The gas is not enough for heating: it covers {value}% of the heat needed.",
        "kk": "Газ қыздыруға жетпейді: қажетті жылудың {value}% ғана жабады.",
    },
    "enough_yes": {
        "ru": "Газа хватит на подогрев: он покрывает {value}% нужного тепла.",
        "en": "The gas is enough for heating: it covers {value}% of the heat needed.",
        "kk": "Газ қыздыруға жетеді: қажетті жылудың {value}% жабады.",
    },
    "enough_maybe": {
        "ru": "Газа может хватить на подогрев, а может и нет: он покрывает {value}% нужного тепла.",
        "en": "The gas may or may not be enough for heating: it covers {value}% of the heat needed.",
        "kk": "Газ қыздыруға жетуі де, жетпеуі де мүмкін: қажетті жылудың {value}% жабады.",
    },
    "fits_no": {
        "ru": "Партия не поместится в реактор: {volume} л при рабочем объёме {working} л (реактор {reactor} л). "
              "Загружайте не больше {working} л за раз — расчёт газа ниже сделан для всей партии.",
        "en": "The batch does not fit the reactor: {volume} L with a working volume of {working} L (reactor {reactor} L). "
              "Load at most {working} L at a time — the gas below is calculated for the whole batch.",
        "kk": "Партия реакторға сыймайды: {volume} л, ал жұмыс көлемі {working} л (реактор {reactor} л). "
              "Бір ретте {working} л-ден артық жүктемеңіз — төмендегі газ бүкіл партия үшін есептелген.",
    },
    "fits_maybe": {
        "ru": "Партия может не поместиться: {volume} л при рабочем объёме {working} л (зависит от плотности сырья).",
        "en": "The batch may not fit: {volume} L with a working volume of {working} L (depends on the density).",
        "kk": "Партия сыймауы мүмкін: {volume} л, жұмыс көлемі {working} л (тығыздыққа байланысты).",
    },
    "best_gain": {
        "ru": "Выгоднее всего — {best}: {value} ₸.",
        "en": "The best option is {best}: {value} KZT.",
        "kk": "Ең тиімдісі — {best}: {value} ₸.",
    },
    "best_loss": {
        "ru": "Сейчас любой вариант убыточен; наименьший убыток — {best}: {value} ₸.",
        "en": "Every option loses money now; the smallest loss is {best}: {value} KZT.",
        "kk": "Қазір кез келген нұсқа шығынды; ең аз шығын — {best}: {value} ₸.",
    },
    "best_no_prices": {
        "ru": "По энергии выгоднее всего — {best} (цены не сохранены, в тенге не посчитано).",
        "en": "By energy the best option is {best} (no saved prices, not converted to KZT).",
        "kk": "Энергия бойынша ең тиімдісі — {best} (бағалар сақталмаған, теңгеге есептелмеді).",
    },
}
TITLES = {
    "regime": {"ru": "Режим", "en": "Regime", "kk": "Режим"},
    "net": {"ru": "Энергобаланс", "en": "Energy balance", "kk": "Энергия балансы"},
    "enough_gas": {"ru": "Хватит газа на подогрев?", "en": "Enough gas for heating?", "kk": "Газ қыздыруға жете ме?"},
    "fits": {"ru": "Поместится в реактор?", "en": "Fits the reactor?", "kk": "Реакторға сыя ма?"},
    "best_use": {"ru": "Что выгоднее", "en": "Best use", "kk": "Не тиімді"},
}
WORDS = {
    "yes": {"ru": "да", "en": "yes", "kk": "иә"},
    "no": {"ru": "нет", "en": "no", "kk": "жоқ"},
    "maybe": {"ru": "на грани", "en": "borderline", "kk": "шекарада"},
    "plus": {"ru": "плюс", "en": "plus", "kk": "оң"},
    "minus": {"ru": "минус", "en": "minus", "kk": "теріс"},
    "uncertain": {"ru": "около нуля", "en": "near zero", "kk": "нөлге жақын"},
}


def _say(table: dict, key: str, language: str, **values) -> str:
    row = table[key]
    return row.get(language, row["ru"]).format(**values)


def _first_ok(results: list[dict], name: str) -> dict | None:
    return next((r for r in results if r.get("name") == name and r.get("ok")), None)


def _sign(values: list) -> str:
    low, high = values
    return "minus" if high < 0 else "plus" if low > 0 else "uncertain"


def _item(key: str, code: str, value: str, text: str, language: str, tone: str) -> dict:
    return {"key": key, "code": code, "title": TITLES[key].get(language, TITLES[key]["ru"]), "value": value,
            "text": text, "tone": tone}


# --- the five verdicts ----------------------------------------------------------

def regime_verdict(results: list[dict], language: str) -> dict | None:
    found = _first_ok(results, "recommend_temperature_regime")
    if not found:
        return None
    llm = found["llm"]
    text = _say(TEXTS, "regime", language, regime=llm["recommended"], reason=llm["reason"])
    return _item("regime", found["data"]["recommended"], llm["recommended"], text, language, "info")


def net_values(results: list[dict]) -> list | None:
    """Net balance [low, high] kWh from the most specific result available."""
    regime = _first_ok(results, "recommend_temperature_regime")
    if regime:
        chosen = next(r for r in regime["data"]["regimes"] if r["id"] == regime["data"]["recommended"])
        return pair(chosen["net_kwh"])
    both = gas_vs_heating(results)
    if both:
        return pair(subtract(both["data"]["gas_heat_kwh"], both["data"]["heating_need_kwh"]))
    scenarios = _first_ok(results, "compare_scenarios")
    if scenarios:
        return scenarios["llm"]["scenarios"][-1]["net_kwh"]
    return None


def net_verdict(results: list[dict], language: str) -> dict | None:
    values = net_values(results)
    if values is None:
        return None
    sign = _sign(values)
    text = _say(TEXTS, "net_" + sign, language, value=approx_text(values))
    return _item("net", sign, f"{WORDS[sign].get(language, WORDS[sign]['ru'])}: {approx_text(values)}", text, language,
                 {"minus": "bad", "plus": "good", "uncertain": "warn"}[sign])


def enough_gas_verdict(results: list[dict], language: str) -> dict | None:
    both = gas_vs_heating(results, language)
    if not both:
        return None
    enough = both["llm"]["enough_gas_for_heating"]
    covers = approx_text(both["llm"]["gas_covers_heating_percent"])
    text = _say(TEXTS, "enough_" + enough, language, value=covers)
    return _item("enough_gas", enough, f"{WORDS[enough].get(language, WORDS[enough]['ru'])} · {covers}%", text, language,
                 {"no": "bad", "yes": "good", "maybe": "warn"}[enough])


def batch_volume_range(components: list[dict]) -> tuple[float, float] | None:
    """Volume of the batch, L: litres as given; kg divided by the density range of the material."""
    low = high = 0.0
    for raw in components:
        if raw.get("amount") is None or not raw.get("substrate"):
            return None
        try:
            component = normalize_component(raw)
        except ValueError:
            return None
        if component.get("amount") is None:
            return None
        if component["family"] == "volume":
            low += component["value"]
            high += component["value"]
            continue
        state = component_mass(component)["state"]
        density = substrates.density(component["substrate"], state)
        low += component["value"] / density["high"]
        high += component["value"] / density["low"]
    return low, high


def fits_verdict(facts: dict, language: str) -> dict | None:
    """Only reported when the batch does NOT (or may not) fit — a warning, not noise."""
    volume = batch_volume_range(facts.get("components") or [])
    if volume is None:
        return None
    demo = demo_reactor()
    reactor = facts.get("reactor_volume_l") or demo["reactor_volume_l"]
    working = reactor * demo["fill_share"]
    smallest, largest = volume
    if largest <= working:
        return None
    code = "no" if smallest > working else "maybe"
    shown = f"{center([round(smallest), round(largest)]):g}" if smallest != largest else f"{round(smallest):g}"
    text = _say(TEXTS, "fits_" + code, language, volume=shown, working=f"{working:g}", reactor=f"{reactor:g}")
    return _item("fits", code, f"{WORDS[code].get(language, WORDS[code]['ru'])}: {shown} > {working:g} л", text, language,
                 "bad" if code == "no" else "warn")


def best_use_verdict(results: list[dict], language: str) -> dict | None:
    found = _first_ok(results, "energy_balance_and_economics")
    if not found:
        return None
    llm, data = found["llm"], found["data"]
    value = data["options"][data["best"]]["value_kzt"]
    if value is None:
        text = _say(TEXTS, "best_no_prices", language, best=llm["best_use"])
        return _item("best_use", data["best"], llm["best_use"], text, language, "info")
    values = pair(value)
    key = "best_loss" if llm.get("all_options_lose_money") else "best_gain"
    text = _say(TEXTS, key, language, best=llm["best_use"], value=approx_text(values))
    return _item("best_use", data["best"], f"{llm['best_use']}: {approx_text(values)} ₸", text, language,
                 "bad" if key == "best_loss" else "good")


def build(results: list[dict], facts: dict, language: str = "ru") -> dict | None:
    """All verdicts that apply, as one result (name "verdicts"); None if there is nothing to conclude."""
    if _first_ok(results, "verdicts"):
        return None
    items = [v for v in (regime_verdict(results, language), net_verdict(results, language),
                         enough_gas_verdict(results, language), fits_verdict(facts, language),
                         best_use_verdict(results, language)) if v]
    if not items:
        return None
    coverage = gas_vs_heating(results, language)
    data = {"status": "ok", "items": items}
    if coverage:
        data["gas_vs_heating"] = coverage["data"]
    llm = {"verdicts": [item["text"] for item in items],
           "instruction": "Start the answer with these verdicts in your own words. Never contradict them."}
    return result("verdicts", ok=True, data=data, llm=llm,
                  assumptions=coverage["assumptions"] if coverage else [], label="assumption")


# --- does the LLM text contradict a verdict? --------------------------------------

REGIME_WORDS = {"psychrophilic": r"психрофил", "mesophilic": r"мезофил", "thermophilic": r"термофил"}
POSITIVE_ENOUGH = r"(?<!не )(?<!не)(?<!not )\b(?:хватит|хватает|достаточно|enough|sufficient|жетеді|жетіп)(?!\s+ли)"
NEGATIVE_ENOUGH = r"не\s+хват\w*|недостаточно|не\s+покро\w*|not\s+enough|insufficient|жетпейді|жетпей"
POSITIVE_NET = r"положительн\w*\s+(?:энерго)?баланс|баланс\w*\s+(?:будет\s+)?положител\w*|в\s+плюсе|surplus|positive\s+(?:net\s+)?(?:energy\s+)?balance|оң\s+баланс|баланс\w*\s+оң"
NEGATIVE_NET = r"отрицательн\w*\s+(?:энерго)?баланс|баланс\w*\s+(?:будет\s+)?отрицател\w*|в\s+минусе|deficit|negative\s+(?:net\s+)?(?:energy\s+)?balance|теріс\s+баланс|баланс\w*\s+теріс"
POSITIVE_FITS = r"(?<!не )(?<!not )\b(?:поместится|помещается|влезет|влезает|fits|сыяды)"
BEST_WORDS = {"heat": r"тепл|кот[её]л|\bheat|жылу", "electricity": r"электр|генератор|electric",
              "chp": r"когенерац|\bchp\b"}


def contradicts(item: dict, text: str) -> bool:
    """True if the LLM text says the opposite of a verdict."""
    if not text:
        return False
    found = lambda pattern: re.search(pattern, text, re.IGNORECASE) is not None  # noqa: E731
    key, code = item["key"], item["code"]
    if key == "regime":
        others = [w for r, w in REGIME_WORDS.items() if r != code]
        return any(found(w) for w in others) and not found(REGIME_WORDS.get(code, "^$"))
    if key == "net":
        if code == "minus":
            return found(POSITIVE_NET)
        if code == "plus":
            return found(NEGATIVE_NET)
        return False
    if key == "enough_gas":
        if code == "no":
            return found(POSITIVE_ENOUGH) and not found(NEGATIVE_ENOUGH)
        if code == "yes":
            return found(NEGATIVE_ENOUGH)
        return False
    if key == "fits":
        return found(POSITIVE_FITS)
    if key == "best_use":
        best = BEST_WORDS.get(code)
        if best is None or found(best):
            return False
        return any(found(w) for option, w in BEST_WORDS.items() if option != code)
    return False


def contradictions(verdict_result: dict | None, text: str) -> list[dict]:
    """Verdicts that the text contradicts."""
    if not verdict_result:
        return []
    return [item for item in verdict_result["data"]["items"] if contradicts(item, text)]
