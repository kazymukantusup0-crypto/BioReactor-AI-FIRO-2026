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

Proactive advice (only when the net balance is negative or the gas is not enough):
    the same batch in the mesophilic regime is recalculated
        A) with 50 mm expanded polystyrene (λ 0.035–0.040 W/(m·K)),
        B) at 35 °C instead of 37 °C (lower edge of the mesophilic range 35–38 °C; the gas
           yield is assumed equal — a model assumption, said to the user),
        C) both;
    the best variant is shown as "before -> after".
"""
from __future__ import annotations

import re

from src.agent_v10 import substrates
from src.agent_v10.config import demo_reactor, temperature_regimes
from src.agent_v10.i18n import t
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
ADVICE = {
    "eps50": {
        "ru": "Совет: утеплите реактор пенополистиролом 50 мм — баланс станет {after} кВт·ч вместо {before} кВт·ч.",
        "en": "Advice: insulate the reactor with 50 mm EPS foam — the balance becomes {after} kWh instead of {before} kWh.",
        "kk": "Кеңес: реакторды 50 мм пенополистиролмен жылытыңыз — баланс {before} кВт·сағ орнына {after} кВт·сағ болады.",
    },
    "t35": {
        "ru": "Совет: держите 35 °C вместо 37 °C — баланс станет {after} кВт·ч вместо {before} кВт·ч.",
        "en": "Advice: keep 35 °C instead of 37 °C — the balance becomes {after} kWh instead of {before} kWh.",
        "kk": "Кеңес: 37 °C орнына 35 °C ұстаңыз — баланс {before} кВт·сағ орнына {after} кВт·сағ болады.",
    },
    "eps50_t35": {
        "ru": "Совет: утеплите реактор пенополистиролом 50 мм и держите 35 °C вместо 37 °C — баланс станет {after} кВт·ч "
              "вместо {before} кВт·ч.",
        "en": "Advice: insulate with 50 mm EPS foam and keep 35 °C instead of 37 °C — the balance becomes {after} kWh "
              "instead of {before} kWh.",
        "kk": "Кеңес: реакторды 50 мм пенополистиролмен жылытып, 37 °C орнына 35 °C ұстаңыз — баланс {before} кВт·сағ "
              "орнына {after} кВт·сағ болады.",
    },
    "still_minus": {
        "ru": " Это всё ещё минус: для такой партии в холод газа мало — загружайте больше сырья или грейте и электричеством.",
        "en": " It is still negative: this batch gives too little gas for the cold — load more feed or also heat with electricity.",
        "kk": " Бұл әлі де теріс: суықта бұл партияның газы аз — шикізатты көбірек жүктеңіз немесе электрмен де жылытыңыз.",
    },
    "assume_t35": {
        "ru": "35 °C — нижняя граница мезофильного диапазона 35–38 °C; выход газа принят как при 37 °C (допущение модели)",
        "en": "35 °C is the lower edge of the mesophilic range 35–38 °C; the gas yield is taken as at 37 °C (model assumption)",
        "kk": "35 °C — мезофильді 35–38 °C аралығының төменгі шегі; газ шығымы 37 °C-тағыдай алынды (модель жорамалы)",
    },
    "assume_eps50": {
        "ru": "пенополистирол 50 мм, теплопроводность 0.035–0.040 Вт/(м·К)",
        "en": "EPS foam 50 mm, thermal conductivity 0.035–0.040 W/(m·K)",
        "kk": "пенополистирол 50 мм, жылу өткізгіштігі 0.035–0.040 Вт/(м·К)",
    },
}

TITLES = {
    "advice": {"ru": "Совет: было → стало", "en": "Advice: before → after", "kk": "Кеңес: болды → болады"},
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


def net_source(results: list[dict]) -> tuple[str, list] | None:
    """('regime' | 'gas_heating' | 'scenarios', net balance [low, high] kWh) from the most specific result."""
    regime = _first_ok(results, "recommend_temperature_regime")
    if regime:
        chosen = next(r for r in regime["data"]["regimes"] if r["id"] == regime["data"]["recommended"])
        return "regime", pair(chosen["net_kwh"])
    both = gas_vs_heating(results)
    if both:
        return "gas_heating", pair(subtract(both["data"]["gas_heat_kwh"], both["data"]["heating_need_kwh"]))
    scenarios = _first_ok(results, "compare_scenarios")
    if scenarios:
        return "scenarios", list(scenarios["llm"]["scenarios"][-1]["net_kwh"])
    return None


def net_values(results: list[dict]) -> list | None:
    """Net balance [low, high] kWh shown to the user."""
    found = net_source(results)
    return found[1] if found else None


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
    """Only reported when the user NAMED the reactor volume and the batch does not (or may not) fit.

    Without a named reactor the heating model sizes the reactor for the batch, so a warning
    against the 200 L demo barrel would contradict the rest of the answer.
    """
    reactor = facts.get("reactor_volume_l")
    volume = batch_volume_range(facts.get("components") or [])
    if volume is None or not reactor:
        return None
    demo = demo_reactor()
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


def _variants(source: str, results: list[dict], facts: dict, language: str) -> dict:
    """Net balance [low, high] of each improvement, calculated by the SAME tool as the balance shown.

    regime      -> the regime calculation again (EPS 50 mm; mesophilic also 35 °C and both)
    gas_heating -> the heating calculation again with EPS 50 mm, the same gas
    scenarios   -> the scenario comparison again with EPS 50 mm
    """
    from src.agent_v10.tools.registry import default_batch, run_tool
    from src.agent_v10.tools.regimes import _regime_case

    insulation = facts.get("insulation") or demo_reactor()["insulation"]
    variants: dict = {}
    with_eps = {**facts, "insulation": "eps50"}
    try:
        if source == "regime":
            regime_result = _first_ok(results, "recommend_temperature_regime")
            regime_id = regime_result["data"]["recommended"]
            regime = next(r for r in temperature_regimes()["regimes"] if r["id"] == regime_id)
            components = [c for c in facts.get("components") or [] if c.get("amount") is not None and c.get("substrate")]
            components = components or default_batch(facts)
            ambient = regime_result["data"]["ambient_c"]
            reactor = facts.get("reactor_volume_l")
            if insulation != "good":
                variants["eps50"] = pair(_regime_case(components, regime, ambient, "eps50", reactor, language)["net_kwh"])
            if regime_id == "mesophilic":
                # 35 °C: the lower edge of the mesophilic range from the sources.
                low = {**regime, "setpoint_c": regime["temperature_range_c"][0]}
                variants["t35"] = pair(_regime_case(components, low, ambient, insulation, reactor, language)["net_kwh"])
                if insulation != "good":
                    variants["eps50_t35"] = pair(_regime_case(components, low, ambient, "eps50", reactor, language)["net_kwh"])
        elif insulation != "good" and source == "gas_heating":
            gas_heat = gas_vs_heating(results)["data"]["gas_heat_kwh"]
            need = run_tool("estimate_heating_energy", {}, with_eps, language)["data"]["total_kwh"]
            variants["eps50"] = pair(subtract(gas_heat, need))
        elif insulation != "good" and source == "scenarios":
            again = run_tool("compare_scenarios", {}, with_eps, language)
            if again.get("ok"):
                variants["eps50"] = list(again["llm"]["scenarios"][-1]["net_kwh"])
    except (ValueError, KeyError, TypeError, StopIteration):
        return {}
    return variants


def advice_item(results: list[dict], facts: dict, language: str) -> dict | None:
    """The simplest change that improves a negative balance most, as 'before -> after'.

    'before' is exactly the net balance shown to the user; 'after' comes from the same tool.
    """
    found = net_source(results)
    if not found:
        return None
    source, before = found
    cases = _variants(source, results, facts, language)
    if not cases:
        return None
    gains = {key: center(values) - center(before) for key, values in cases.items()}
    top = max(gains.values())
    # The simplest advice that gives at least 90 % of the best gain (one change is easier than two).
    best = next(key for key in ("eps50", "t35", "eps50_t35") if key in gains and gains[key] >= 0.9 * top)
    after = cases[best]
    if gains[best] < max(5.0, 0.1 * abs(center(before))):
        return None  # a tiny gain is noise, not advice
    text = _say(ADVICE, best, language, before=approx_text(before), after=approx_text(after))
    if after[1] < 0:
        text += _say(ADVICE, "still_minus", language)
    item = _item("advice", best, f"≈{center(before):g} → ≈{center(after):g} кВт·ч".replace("-", "−"), text, language,
                 "good" if after[0] > 0 else "warn")
    item.update(before=list(before), after=list(after),
                assumptions=[_say(ADVICE, "assume_eps50", language)] * ("eps50" in best)
                + [_say(ADVICE, "assume_t35", language)] * ("t35" in best))
    return item


def build(results: list[dict], facts: dict, language: str = "ru") -> dict | None:
    """All verdicts that apply, as one result (name "verdicts"); None if there is nothing to conclude."""
    if _first_ok(results, "verdicts"):
        return None
    items = [v for v in (regime_verdict(results, language), net_verdict(results, language),
                         enough_gas_verdict(results, language), fits_verdict(facts, language),
                         best_use_verdict(results, language)) if v]
    if not items:
        return None
    losing = any((i["key"] == "net" and i["code"] == "minus") or (i["key"] == "enough_gas" and i["code"] == "no")
                 for i in items)
    advice = advice_item(results, facts, language) if losing else None
    if advice:
        items.append(advice)
    coverage = gas_vs_heating(results, language)
    data = {"status": "ok", "items": items}
    if coverage:
        data["gas_vs_heating"] = coverage["data"]
    llm = {"verdicts": [item["text"] for item in items],
           "instruction": "Start the answer with these verdicts in your own words. Never contradict them."}
    assumptions = (coverage["assumptions"] if coverage else []) + (advice["assumptions"] if advice else [])
    return result("verdicts", ok=True, data=data, llm=llm, assumptions=assumptions, label="assumption")


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
