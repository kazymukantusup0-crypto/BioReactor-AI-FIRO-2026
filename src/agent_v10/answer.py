"""Final answer: numbers block, number check and template explanations.

Answer structure (rule 4 of the project):
    1. numbers block   - built by PYTHON from tool results (cards with a label);
    2. explanation     - 2–4 sentences by the LLM (or a template without LLM);
    3. one question    - optional, from the tools;
    4. assumptions and sources - shown in a collapsible block by the UI.

Number check: every number in the LLM text must be found in the tool results,
the user's message or the remembered facts (with rounding). Otherwise the agent
regenerates once and then falls back to the template explanation.
"""
from __future__ import annotations

import re

from src.agent_v10.i18n import badge
from src.agent_v10.ranges import range_text as _range_text, tidy
from src.agent_v10.tools.derived import VERDICT_TEXT

# Small numbers such as "2 варианта", "1 вопрос" are always allowed.
ALWAYS_ALLOWED = {float(n) for n in range(0, 11)}
NUMBER_RE = re.compile(r"(?<![\w.])[-−–]?\d+(?:[  ]\d{3})*(?:[.,]\d+)?")

TITLES = {
    "methane": {"ru": "Метан", "en": "Methane", "kk": "Метан"},
    "biogas": {"ru": "Биогаз", "en": "Biogas", "kk": "Биогаз"},
    "energy": {"ru": "Энергия газа", "en": "Gas energy", "kk": "Газ энергиясы"},
    "heating": {"ru": "Затраты на подогрев и перемешивание", "en": "Heating and mixing", "kk": "Қыздыру мен араластыру"},
    "regime": {"ru": "Рекомендуемый режим", "en": "Recommended regime", "kk": "Ұсынылған режим"},
    "net": {"ru": "Чистый баланс", "en": "Net balance", "kk": "Таза баланс"},
    "days": {"ru": "Срок сбраживания", "en": "Digestion time", "kk": "Ашыту мерзімі"},
    "best_use": {"ru": "Выгоднее всего", "en": "Best use", "kk": "Ең тиімдісі"},
    "value": {"ru": "Экономия (минус = убыток)", "en": "Savings (minus = loss)", "kk": "Үнем (минус = шығын)"},
    "least_loss": {"ru": "Наименьший убыток", "en": "Smallest loss", "kk": "Ең аз шығын"},
    "methane_change": {"ru": "Прибавка метана", "en": "Extra methane", "kk": "Метан өсімі"},
    "enough_gas": {"ru": "Хватит газа на подогрев?", "en": "Enough gas for heating?", "kk": "Газ қыздыруға жете ме?"},
    "gas_covers": {"ru": "Газ покрывает подогрев", "en": "Gas covers heating", "kk": "Газ қыздыруды жабады"},
}
UNITS = {
    "m3": {"ru": "м³", "en": "m³", "kk": "м³"},
    "kwh": {"ru": "кВт·ч", "en": "kWh", "kk": "кВт·сағ"},
    "days": {"ru": "дней", "en": "days", "kk": "күн"},
    "percent": {"ru": "%", "en": "%", "kk": "%"},
    "kzt": {"ru": "₸", "en": "KZT", "kk": "₸"},
}
QUESTION_PREFIX = "❓ "


def _title(key: str, language: str) -> str:
    return TITLES[key].get(language, TITLES[key]["ru"])


def _unit(key: str, language: str) -> str:
    return UNITS[key].get(language, UNITS[key]["ru"])





def _card(key: str, values: list, unit_key: str | None, label: str, language: str, title: str | None = None) -> dict:
    unit = _unit(unit_key, language) if unit_key else ""
    return {"key": key, "title": title or _title(key, language), "low": values[0], "high": values[1],
            "value": _range_text(values), "unit": unit, "label": label, "badge": badge(label, language)}


def number_cards(results: list[dict], language: str) -> list[dict]:
    """Big-number cards for the UI from the compact tool results."""
    cards: list[dict] = []
    for item in results:
        if not item.get("ok"):
            continue
        llm, label, name = item["llm"], item["label"], item["name"]
        if name == "estimate_methane":
            cards += [
                _card("methane", llm["methane_m3"], "m3", label, language),
                _card("biogas", llm["biogas_m3"], "m3", label, language),
                _card("energy", llm["energy_kwh"], "kwh", label, language),
                _card("days", llm["days"], "days", "assumption", language),
            ]
        elif name == "estimate_heating_energy":
            cards.append(_card("heating", llm["total_kwh"], "kwh", label, language))
        elif name == "recommend_temperature_regime":
            chosen = next(r for r in llm["regimes"] if r["regime"] == llm["recommended"])
            cards += [
                {"key": "regime", "title": _title("regime", language), "value": llm["recommended"], "unit": "",
                 "label": "assumption", "badge": badge("assumption", language)},
                _card("methane", chosen["methane_m3"], "m3", label, language),
                _card("heating", chosen["heating_cost_kwh"], "kwh", label, language),
                _card("net", chosen["net_kwh"], "kwh", label, language),
                _card("days", chosen["days"], "days", "assumption", language),
            ]
        elif name == "energy_balance_and_economics":
            best = next(o for o in llm["options"] if o["use"] == llm["best_use"])
            cards += [
                _card("energy", llm["gas_energy_kwh"], "kwh", label, language),
                {"key": "best_use", "title": _title("least_loss" if llm.get("all_options_lose_money") else "best_use", language),
                 "value": llm["best_use"], "unit": "",
                 "label": label, "badge": badge(label, language)},
            ]
            if best.get("value_kzt"):
                cards.append(_card("value", best["value_kzt"], "kzt", label, language))
        elif name == "gas_vs_heating":
            cards += [
                {"key": "enough_gas", "title": _title("enough_gas", language),
                 "value": VERDICT_TEXT[llm["enough_gas_for_heating"]].get(language, VERDICT_TEXT[llm["enough_gas_for_heating"]]["ru"]),
                 "unit": "", "label": label, "badge": badge(label, language)},
                _card("gas_covers", llm["gas_covers_heating_percent"], "percent", label, language),
            ]
        elif name == "compare_scenarios":
            last = llm["scenarios"][-1]
            cards += [
                _card("methane", last["methane_m3"], "m3", label, language, title=f"{_title('methane', language)}: {last['name']}"),
                _card("methane_change", last["methane_change_vs_first_m3"], "m3", label, language),
                _card("net", last["net_kwh"], "kwh", label, language, title=f"{_title('net', language)}: {last['name']}"),
            ]
    # Same card twice (e.g. methane from two tools): keep the first one.
    unique, seen = [], set()
    for card in cards:
        if card["title"] in seen:
            continue
        seen.add(card["title"])
        unique.append(card)
    return unique


def numbers_markdown(cards: list[dict]) -> str:
    """One compact line per card, for the chat text."""
    lines = []
    for card in cards:
        unit = f" {card['unit']}" if card["unit"] else ""
        lines.append(f"**{card['title']}:** {card['value']}{unit} · _{card['badge']}_")
    return "\n".join(lines)


# --- number check -----------------------------------------------------------

def _number_tokens(text: str) -> list[tuple[float, float]]:
    """Numbers in a text with the rounding tolerance implied by how they are written.

    "2,9" -> (2.9, 0.05)   "3" -> (3, 0.5)   "1050" -> (1050, 5)   "1000" -> (1000, 50)
    The tolerance of round numbers is capped at 5 % so "100" cannot stand for 140.
    """
    tokens = []
    for match in NUMBER_RE.finditer(text):
        raw = match.group().replace(" ", "").replace(" ", "").replace(",", ".")
        raw = raw.replace("−", "-").replace("–", "-")
        try:
            value = float(raw)
        except ValueError:
            continue
        digits = raw.lstrip("-")
        if "." in digits:
            tolerance = 0.5 * 10 ** -len(digits.split(".")[1])
        else:
            trailing_zeros = len(digits) - len(digits.rstrip("0")) if digits.strip("0") else 0
            tolerance = min(0.5 * 10 ** trailing_zeros, max(0.5, 0.05 * abs(value)))
        tokens.append((value, tolerance))
    return tokens


def parse_numbers(text: str) -> list[float]:
    """All numbers in a text: '2,9' -> 2.9, '−15' -> -15, '1 050' -> 1050."""
    return [value for value, _ in _number_tokens(text)]


def _collect(value, bucket: set[float]) -> None:
    if isinstance(value, bool):
        return
    if isinstance(value, (int, float)):
        bucket.add(float(value))
        bucket.add(float(tidy(value)))
    elif isinstance(value, str):
        bucket.update(parse_numbers(value))
    elif isinstance(value, dict):
        for item in value.values():
            _collect(item, bucket)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _collect(item, bucket)


def allowed_numbers(results: list[dict], user_text: str, facts: dict) -> set[float]:
    """Numbers the LLM may use: tool results, assumptions, user text, facts."""
    bucket: set[float] = set(ALWAYS_ALLOWED)
    for item in results:
        _collect(item.get("llm"), bucket)
        _collect(item.get("assumptions"), bucket)
    bucket.update(parse_numbers(user_text))
    _collect(facts, bucket)
    bucket.update({-abs(v) for v in list(bucket)})  # "−15" written with or without the sign
    bucket.update({abs(v) for v in list(bucket)})
    return bucket


def _matches(number: float, tolerance: float, allowed: set[float]) -> bool:
    """A written number matches a tool value if it is that value rounded the way it is written."""
    return any(abs(number - value) <= tolerance + 1e-9 for value in allowed)


def unknown_numbers(text: str, allowed: set[float]) -> list[float]:
    """Numbers in the text that do not come from any tool result."""
    return [number for number, tolerance in _number_tokens(text) if not _matches(number, tolerance, allowed)]


# --- templates (no-LLM mode and fallback) -------------------------------------

def template_explanation(results: list[dict], language: str) -> str:
    """2–3 plain sentences built only from tool results."""
    parts: list[str] = []
    for item in results:
        if not item.get("ok"):
            continue
        llm, name = item["llm"], item["name"]
        if name == "estimate_methane":
            parts.append({
                "ru": f"Из этой партии в реакторе ({llm['regime']}) за {_range_text(llm['days'])} дней можно ожидать "
                      f"{_range_text(llm['methane_m3'])} м³ метана, это {_range_text(llm['biogas_m3'])} м³ биогаза и "
                      f"{_range_text(llm['energy_kwh'])} кВт·ч энергии. Лабораторный максимум — "
                      f"{_range_text(llm['lab_potential_methane_m3'])} м³ метана, реактор обычно получает меньше.",
                "en": f"In the reactor ({llm['regime']}) over {_range_text(llm['days'])} days this batch should give "
                      f"{_range_text(llm['methane_m3'])} m³ of methane, i.e. {_range_text(llm['biogas_m3'])} m³ of biogas and "
                      f"{_range_text(llm['energy_kwh'])} kWh. The laboratory maximum is "
                      f"{_range_text(llm['lab_potential_methane_m3'])} m³ of methane; a real reactor gets less.",
                "kk": f"Реакторда ({llm['regime']}) {_range_text(llm['days'])} күнде бұл партиядан "
                      f"{_range_text(llm['methane_m3'])} м³ метан, яғни {_range_text(llm['biogas_m3'])} м³ биогаз және "
                      f"{_range_text(llm['energy_kwh'])} кВт·сағ энергия күтуге болады. Зертханалық максимум — "
                      f"{_range_text(llm['lab_potential_methane_m3'])} м³ метан, нақты реактор азырақ алады.",
            }.get(language, ""))
        elif name == "estimate_heating_energy":
            parts.append({
                "ru": f"Чтобы держать {llm['target_c']} °C при {llm['outside_c']} °C снаружи {llm['days']} дней, нужно "
                      f"{_range_text(llm['total_kwh'])} кВт·ч; основная часть — теплопотери через стенки "
                      f"({_range_text(llm['heat_loss_kwh'])} кВт·ч).",
                "en": f"Keeping {llm['target_c']} °C with {llm['outside_c']} °C outside for {llm['days']} days needs "
                      f"{_range_text(llm['total_kwh'])} kWh; most of it is heat loss through the walls "
                      f"({_range_text(llm['heat_loss_kwh'])} kWh).",
                "kk": f"Сыртта {llm['outside_c']} °C болғанда {llm['days']} күн бойы {llm['target_c']} °C ұстау үшін "
                      f"{_range_text(llm['total_kwh'])} кВт·сағ керек; негізгі бөлігі — қабырға арқылы жылу шығыны "
                      f"({_range_text(llm['heat_loss_kwh'])} кВт·сағ).",
            }.get(language, ""))
        elif name == "recommend_temperature_regime":
            chosen = next(r for r in llm["regimes"] if r["regime"] == llm["recommended"])
            parts.append({
                "ru": f"Рекомендую {llm['recommended']}: он {llm['reason']}. Чистый баланс "
                      f"{_range_text(chosen['net_kwh'])} кВт·ч за {_range_text(chosen['days'])} дней.",
                "en": f"I recommend {llm['recommended']}: it {llm['reason']}. Net balance "
                      f"{_range_text(chosen['net_kwh'])} kWh over {_range_text(chosen['days'])} days.",
                "kk": f"{llm['recommended']} ұсынамын: ол {llm['reason']}. Таза баланс "
                      f"{_range_text(chosen['net_kwh'])} кВт·сағ, {_range_text(chosen['days'])} күн ішінде.",
            }.get(language, ""))
            if llm.get("if_good_insulation_net_kwh"):
                parts.append({
                    "ru": f"С хорошим утеплением баланс стал бы {_range_text(llm['if_good_insulation_net_kwh'])} кВт·ч.",
                    "en": f"With good insulation the balance would be {_range_text(llm['if_good_insulation_net_kwh'])} kWh.",
                    "kk": f"Жақсы жылытумен баланс {_range_text(llm['if_good_insulation_net_kwh'])} кВт·сағ болар еді.",
                }.get(language, ""))
        elif name == "energy_balance_and_economics":
            best = next(o for o in llm["options"] if o["use"] == llm["best_use"])
            money = f" ({_range_text(best['value_kzt'])} ₸)" if best.get("value_kzt") else ""
            parts.append({
                "ru": f"Газ даёт {_range_text(llm['gas_energy_kwh'])} кВт·ч; с учётом собственных нужд выгоднее всего "
                      f"вариант «{llm['best_use']}»{money}.",
                "en": f"The gas holds {_range_text(llm['gas_energy_kwh'])} kWh; after own needs the best option is "
                      f"\"{llm['best_use']}\"{money}.",
                "kk": f"Газ {_range_text(llm['gas_energy_kwh'])} кВт·сағ береді; өз қажеттіліктерін ескергенде ең тиімдісі "
                      f"«{llm['best_use']}»{money}.",
            }.get(language, ""))
        elif name == "compare_scenarios":
            first, last = llm["scenarios"][0], llm["scenarios"][-1]
            parts.append({
                "ru": f"Вариант «{last['name']}» даёт {_range_text(last['methane_m3'])} м³ метана против "
                      f"{_range_text(first['methane_m3'])} м³ у варианта «{first['name']}»; чистый баланс "
                      f"{_range_text(last['net_kwh'])} против {_range_text(first['net_kwh'])} кВт·ч.",
                "en": f"\"{last['name']}\" gives {_range_text(last['methane_m3'])} m³ of methane versus "
                      f"{_range_text(first['methane_m3'])} m³ for \"{first['name']}\"; net balance "
                      f"{_range_text(last['net_kwh'])} versus {_range_text(first['net_kwh'])} kWh.",
                "kk": f"«{last['name']}» нұсқасы {_range_text(last['methane_m3'])} м³ метан береді, ал «{first['name']}» — "
                      f"{_range_text(first['methane_m3'])} м³; таза баланс {_range_text(last['net_kwh'])} және "
                      f"{_range_text(first['net_kwh'])} кВт·сағ.",
            }.get(language, ""))
        elif name == "gas_vs_heating":
            verdict = llm["enough_gas_for_heating"]
            covers = _range_text(llm["gas_covers_heating_percent"])
            parts.append({
                "ru": {"no": f"Газа не хватит на подогрев: он покрывает {covers}% нужного тепла, остальное — от электричества.",
                       "yes": f"Газа хватит на подогрев: он покрывает {covers}% нужного тепла.",
                       "maybe": f"Газа может хватить, а может и нет: он покрывает {covers}% нужного тепла."}[verdict],
                "en": {"no": f"The gas is not enough for heating: it covers {covers}% of the heat; the rest comes from electricity.",
                       "yes": f"The gas is enough for heating: it covers {covers}% of the heat.",
                       "maybe": f"The gas may or may not be enough: it covers {covers}% of the heat."}[verdict],
                "kk": {"no": f"Газ қыздыруға жетпейді: қажетті жылудың {covers}% жабады, қалғаны — электрден.",
                       "yes": f"Газ қыздыруға жетеді: қажетті жылудың {covers}% жабады.",
                       "maybe": f"Газ жетуі де, жетпеуі де мүмкін: қажетті жылудың {covers}% жабады."}[verdict],
            }.get(language, ""))
        elif name == "search_knowledge" and llm.get("quotes"):
            parts.append(llm["quotes"][0])
    return " ".join(part for part in parts if part)


def compose(*, explanation: str, results: list[dict], language: str, mode: str, verified: bool) -> dict:
    """The final answer object sent to the UI and saved in memory."""
    cards = number_cards(results, language)
    successful = [item for item in results if item.get("ok")]
    question = next((item["question"] for item in successful if item.get("question")), None)
    if not successful:
        question = next((item["question"] for item in results if item.get("question")), None)
    assumptions: list[str] = []
    sources: list[dict] = []
    for item in successful:
        assumptions += [a for a in item.get("assumptions", []) if a not in assumptions]
        for source in item.get("sources", []):
            if source.get("id") not in {s.get("id") for s in sources}:
                sources.append(source)
    text_parts = [numbers_markdown(cards), explanation.strip()]
    if question:
        text_parts.append(QUESTION_PREFIX + question)
    return {
        "text": "\n\n".join(part for part in text_parts if part),
        "explanation": explanation.strip(),
        "numbers": cards,
        "question": question,
        "assumptions": assumptions,
        "sources": sources,
        "tools": [item["name"] for item in results],
        "data": {item["name"]: item["data"] for item in results if item.get("ok")},
        "mode": mode,
        "verified": verified,
        "language": language,
    }
