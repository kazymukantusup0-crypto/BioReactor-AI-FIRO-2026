"""Deterministic fact extraction from a free-text message (ru / kk / en).

Why not only the LLM? A small local model sometimes forgets a number or a
unit. Python regexes are fast, testable and never invent anything, so the
facts are extracted here and the LLM receives them ready-made. The LLM can
still pass its own arguments to the tools.

Facts about the batch and the reactor are kept between messages
(see memory.py), so the agent does not ask again for what it already knows.
"""
from __future__ import annotations

import copy
import re

from src.agent_v10 import substrates
from src.agent_v10.units import NUMBER, find_quantities, parse_number

EMPTY_FACTS: dict = {
    "components": [],          # [{substrate, state, amount, unit, family, value, ...}]
    "reactor_volume_l": None,  # nominal reactor volume, litres
    "insulation": None,        # none | basic | good
    "ambient_c": None,         # outside temperature, °C
    "target_c": None,          # requested digestion temperature, °C
    "days": None,              # digestion time, days
    "operating_mode": None,    # batch | continuous
    "price_class": None,       # household | business (electricity tariff)
    "goal": None,              # max_gas | fastest — only when the USER asks; default is the best net energy
}

# "1000 м³ газа", "50 кВт·ч" — what the user wants to GET, not what is loaded.
OUTPUT_AFTER = re.compile(r"^\s*(?:\S+\s+)?(?:био)?газ\w*|^\s*(?:\S+\s+)?метан\w*|^\s*(?:bio)?gas\b|^\s*methane|^\s*биогаз\w*",
                          re.IGNORECASE)
# Words after an amount that are not a material name.
NOT_MATERIAL = re.compile(r"^(?:в|во|на|за|по|из|и|или|до|от|с|со|a|of|the|in|into|for|бар|болса|болады|сколько|газа?|"
                          r"биогаза?|метана?|воды|навоза?|помёта|реактор\w*|бочк\w*|ёмкост\w*|дн\w*|день|сут\w*|"
                          r"будет|получится|выйдет|нужно|надо|есть|у|меня|мне|this|that|is|will)$", re.IGNORECASE)
UNKNOWN_AFTER = re.compile(r"^\s+(?P<words>[а-яёa-zәғқңөұүһі-]{3,}(?:\s+[а-яёa-zәғқңөұүһі-]{3,})?)", re.IGNORECASE)

REACTOR_WORDS = r"(?:реактор\w*|бочк\w*|ёмкост\w*|емкост\w*|резервуар\w*|метантенк\w*|reactor|digester|tank|vessel|barrel|ыдыс\w*|бөшке\w*)"

STATE_PATTERNS = [
    ("bedded", r"подстил\w*|bedding|bedded|төсеніш\w*"),
    ("slurry", r"жидк\w*|жиж\w*|slurry|liquid|сұйық\w*"),
    # "сухое вещество" / "dry matter" is a measurement (TS), not the state "dry".
    ("dry", r"сух\w*\b(?!\s+веществ)|\bdry\b(?!\s+matter)|құрғақ\w*\b(?!\s+зат)"),
    ("fresh_solid", r"тв[её]рд\w*|\bsolid\b|қатты\w*"),
]

INSULATION_PATTERNS = [
    ("none", r"не\s*утепл\w*|неутепл\w*|без\s+утепл\w*|not\s+insulated|uninsulated|no\s+insulation|жылытылмаған|жылытусыз|оқшауланбаған"),
    ("good", r"хорошо\s+утепл\w*|толст\w*\s+утепл\w*|well[\s-]+insulated|жақсы\s+жылытылған|жақсы\s+оқшауланған"),
    ("basic", r"утепл[её]н\w*|утеплен\w*|утеплил\w*|insulated|жылытылған|оқшауланған|пенопласт\w*|минват\w*"),
]

ADD_WORDS = r"(?:добав\w*|ещ[её]|плюс|подмеша\w*|add\w*|plus|also|қос\w*|тағы)"
REPLACE_WORDS = r"(?:вместо|замен\w*|если\s+это|а\s+если\s+(?:у\s+меня\s+)?(?:будет\s+)?(?=\S+\s+навоз)|instead|replace\w*|орнына)"

AMBIENT_WORDS = r"(?:улиц\w*|снаружи|наружн\w*|мороз\w*|зим\w*|outside|outdoor\w*|ambient|winter|сырт\w*|аяз\w*|қыс\w*|ауа)"
TARGET_WORDS = r"(?:нагре\w*|держ\w*|став\w*|установ\w*|режим\w*|в\s+реакторе|внутри|setpoint|target|keep|heat\w*\s+to|ұста\w*|қызд\w*)"

# −15 °C | -15 градусов | минус 15 | 37°
TEMPERATURE_RE = re.compile(
    rf"(?P<sign>[-−–]\s*|минус\s+|minus\s+|алу\s+)?(?P<number>{NUMBER})\s*"
    r"(?P<unit>°\s*[cсCС]?|градус\w*|град\b\.?|degrees?\b|deg\b)?",
    re.IGNORECASE,
)
DAYS_RE = re.compile(rf"(?P<number>{NUMBER})\s*(?:дн\w*|день|сут\w*|days?\b|күн\w*)", re.IGNORECASE)
DENSITY_RE = re.compile(rf"(?:плотност\w*|density|тығыздығ\w*)\D{{0,12}}(?P<number>{NUMBER})", re.IGNORECASE)
TS_RE = re.compile(rf"(?:\bTS\b|сух\w*\s+веществ\w*|\bСВ\b|құрғақ\s+зат\w*)\D{{0,12}}(?P<number>{NUMBER})\s*%", re.IGNORECASE)
VS_RE = re.compile(rf"(?:\bVS\b|органическ\w*\s+веществ\w*|летуч\w*\s+\w*|\bОВ\b|органикалық\s+зат\w*)\D{{0,12}}(?P<number>{NUMBER})\s*%", re.IGNORECASE)
# operating_mode=batch.  The trailing punctuation must not become part of the value.
KEY_VALUE_RE = re.compile(r"\b(?P<key>operating_mode|insulation|режим_работы)\s*[=:]\s*(?P<value>[A-Za-zА-Яа-яЁё_]+)")


def on_topic(text: str) -> bool:
    """The message talks about the plant (state, material, amount, reactor, insulation), even if no fact changed."""
    if substrates.recognize(text) or find_quantities(text):
        return True
    patterns = [pattern for _, pattern in STATE_PATTERNS + INSULATION_PATTERNS] + [REACTOR_WORDS]
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


def empty_facts() -> dict:
    """A fresh, independent copy of the empty fact structure."""
    return copy.deepcopy(EMPTY_FACTS)


def detect_language(text: str) -> str:
    """'kk' if Kazakh-specific letters are present, 'ru' for other Cyrillic, else 'en'."""
    if re.search(r"[әғқңөұүһі]", text.lower()):
        return "kk"
    if re.search(r"[а-яё]", text.lower()):
        return "ru"
    return "en"


def _near(text: str, start: int, end: int, pattern: str, before: int = 30, after: int = 30) -> bool:
    window = text[max(0, start - before): min(len(text), end + after)]
    return re.search(pattern, window, re.IGNORECASE) is not None


def _state_near(text: str, start: int, end: int) -> str | None:
    window = text[max(0, start - 25): min(len(text), end + 10)]
    for state, pattern in STATE_PATTERNS:
        if re.search(pattern, window, re.IGNORECASE):
            return state
    return None


def _component(material: dict, quantity: dict | None, text: str) -> dict:
    substrate = substrates.resolve_material(material["material"])
    item = {"substrate": substrate, "state": _state_near(text, material["start"], material["end"])}
    if material.get("analog_of"):
        item["analog_of"] = material["analog_of"]
    elif substrates.analog_for(substrate):
        # The catalog knows the name but has no reviewed composition ("фруктовые отходы").
        item["analog_of"] = substrates.material_name(substrate, "ru")
        item["substrate"] = substrates.analog_for(substrate)
    if quantity is not None:
        item.update(amount=quantity["amount"], unit=quantity["unit_word"], family=quantity["family"],
                    value=quantity["value"], base_unit=quantity["unit"])
        if quantity.get("assumption"):
            item["unit_assumption"] = quantity["assumption"]
    return item


def _closest_material(quantity: dict, materials: list[dict]) -> dict | None:
    """Material that belongs to a quantity: right after it ('200 л навоза') or right before ('навоз 200 л')."""
    best, best_distance = None, 60
    for material in materials:
        if material["start"] >= quantity["end"]:
            distance = material["start"] - quantity["end"]
        elif material["end"] <= quantity["start"]:
            distance = quantity["start"] - material["end"] + 5  # prefer "200 л навоза" style
        else:
            distance = 0
        if distance < best_distance:
            best, best_distance = material, distance
    return best


def _temperatures(text: str, quantity_spans: list[tuple[int, int]]) -> dict:
    found: dict = {}
    for match in TEMPERATURE_RE.finditer(text):
        if any(start <= match.start("number") < end for start, end in quantity_spans):
            continue
        if text[match.end("number"):match.end("number") + 2].strip().startswith("%"):
            continue  # "8 %" is a share, not a temperature
        has_unit = bool(match.group("unit"))
        negative = bool(match.group("sign")) and not re.match(r"\d", text[max(0, match.start() - 1):match.start()] or " ")
        value = parse_number(match.group("number")) * (-1 if negative else 1)
        is_ambient = _near(text, match.start(), match.end(), AMBIENT_WORDS)
        is_target = _near(text, match.start(), match.end(), TARGET_WORDS)
        if not has_unit and not negative and not is_ambient:
            continue  # a plain number such as "200" is not a temperature
        if not -50 <= value <= 70:
            continue
        if negative or (is_ambient and not is_target):
            found["ambient_c"] = value
        elif is_target or value >= 30:
            found["target_c"] = value
        else:
            found["ambient_c"] = value
    return found


def extract(text: str, known: dict | None = None) -> dict:
    """Extract facts from one message and merge them into the known facts.

    Returns {"facts": merged facts, "updates": what this message changed,
             "language": "ru" | "kk" | "en"}.
    """
    facts = copy.deepcopy(known) if known else empty_facts()
    for key, value in EMPTY_FACTS.items():
        facts.setdefault(key, copy.deepcopy(value))
    updates: dict = {}

    materials = substrates.recognize(text)
    materials += [a for a in substrates.recognize_analogs(text)
                  if not any(a["start"] < m["end"] and a["end"] > m["start"] for m in materials)]
    materials.sort(key=lambda m: m["start"])
    # "получится 1000 м³ газа" is the expected OUTPUT, never a feedstock amount.
    quantities = [q for q in find_quantities(text) if not OUTPUT_AFTER.match(text[q["end"]:q["end"] + 30])]

    # 1. Reactor volume: a volume next to the word "reactor" / "tank".
    batch_quantities = []
    for quantity in quantities:
        near_reactor = _near(text, quantity["start"], quantity["end"], REACTOR_WORDS, before=35, after=12)
        material = _closest_material(quantity, materials)
        material_is_closer = material is not None and abs(material["start"] - quantity["end"]) < 12
        if quantity["family"] == "volume" and near_reactor and not material_is_closer:
            updates["reactor_volume_l"] = quantity["value"]
        else:
            batch_quantities.append(quantity)

    # 2. Batch components: pair each amount with its material.
    new_components = []
    used_materials = set()
    unknown_components = []
    for quantity in batch_quantities:
        material = _closest_material(quantity, materials)
        if material is None:
            # "50 кг <something we do not know>": remember the name, never guess the material.
            after = UNKNOWN_AFTER.match(text[quantity["end"]:])
            words = after.group("words") if after else ""
            first_word = words.split()[0] if words else ""
            if words and not NOT_MATERIAL.match(first_word):
                unknown_components.append({
                    "substrate": None, "unknown_name": words, "state": None, "amount": quantity["amount"],
                    "unit": quantity["unit_word"], "family": quantity["family"], "value": quantity["value"],
                    "base_unit": quantity["unit"], **({"unit_assumption": quantity["assumption"]} if quantity.get("assumption") else {})})
            continue
        used_materials.add(material["start"])
        new_components.append(_component(material, quantity, text))
    if not new_components and unknown_components:
        new_components = unknown_components
    unpaired_materials = [m for m in materials if m["start"] not in used_materials]

    is_add = re.search(ADD_WORDS, text, re.IGNORECASE) is not None
    is_replace = re.search(REPLACE_WORDS, text, re.IGNORECASE) is not None
    components = facts["components"]
    if new_components:
        if is_add and components:
            components = components + new_components
            updates["components_added"] = new_components
        else:
            components = new_components
            updates["components"] = new_components
    elif batch_quantities and len(components) == 1 and not materials:
        # "А если 300 литров?" -> new amount for the known substrate.
        quantity = batch_quantities[0]
        components = [{**components[0], "amount": quantity["amount"], "unit": quantity["unit_word"],
                       "family": quantity["family"], "value": quantity["value"], "base_unit": quantity["unit"]}]
        updates["components"] = components
    elif unpaired_materials and len(components) == 1 and (is_replace or not components[0].get("substrate")):
        # "А если это свиной навоз?" -> same amount, new substrate.
        material = unpaired_materials[0]
        replaced = {**components[0], "substrate": substrates.resolve_material(material["material"]),
                    "state": _state_near(text, material["start"], material["end"])}
        components = [replaced]
        updates["components"] = components
    elif unpaired_materials and not components:
        # Substrate without amount: remember it, the amount may come later.
        components = [_component(m, None, text) for m in unpaired_materials]
        updates["components"] = components

    # A state word without a new substrate ("навоз жидкий") refines the known component.
    if components and not new_components:
        for state, pattern in STATE_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE) and components[-1].get("state") != state:
                components = components[:-1] + [{**components[-1], "state": state}]
                updates["state"] = state
                break

    # 3. Measured properties of the (last) component.
    if components:
        last = dict(components[-1])
        for regex, key, scale in [(DENSITY_RE, "density_kg_l", 1.0), (TS_RE, "ts_percent", 1.0), (VS_RE, "vs_percent_of_ts", 1.0)]:
            match = regex.search(text)
            if match:
                value = parse_number(match.group("number")) * scale
                if key == "density_kg_l" and value > 50:
                    value = value / 1000  # 1013 kg/m3 -> 1.013 kg/L
                last[key] = value
                updates[key] = value
        components = components[:-1] + [last]
    facts["components"] = components

    # 4. Temperatures, days, insulation, mode.
    spans = [(q["start"], q["end"]) for q in quantities]
    for regex in (DAYS_RE, DENSITY_RE, TS_RE, VS_RE):
        spans += [(m.start("number"), m.end("number")) for m in regex.finditer(text)]
    updates.update(_temperatures(text, spans))
    days = DAYS_RE.search(text)
    if days:
        updates["days"] = parse_number(days.group("number"))
    for level, pattern in INSULATION_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            updates["insulation"] = level
            break
    for match in KEY_VALUE_RE.finditer(text):
        key = "operating_mode" if match.group("key") in {"operating_mode", "режим_работы"} else match.group("key")
        updates[key] = match.group("value").lower()
    if "operating_mode" not in updates:
        if re.search(r"периодическ\w*|\bbatch\b|бір\s+рет", text, re.IGNORECASE):
            updates["operating_mode"] = "batch"
        elif re.search(r"непрерывн\w*|ежедневн\w*|continuous\w*|үздіксіз", text, re.IGNORECASE):
            updates["operating_mode"] = "continuous"
    if re.search(r"больше\s+(?:всего\s+)?газа|максимум\w*\s+газ\w*|most\s+gas|max\w*\s+gas|ең\s+көп\s+газ|көбірек\s+газ",
                 text, re.IGNORECASE):
        updates["goal"] = "max_gas"
    elif re.search(r"(?:быстрее|побыстрее|скорее)\s+(?:всего\s+)?(?:сбражива|переработ|получ)\w*|fastest|быстр\w*\s+режим|"
                   r"ең\s+жылдам", text, re.IGNORECASE):
        updates["goal"] = "fastest"
    if re.search(r"предприят\w*|организац\w*|юрлиц\w*|business|company|кәсіпорын", text, re.IGNORECASE):
        updates["price_class"] = "business"

    for key in ["reactor_volume_l", "ambient_c", "target_c", "days", "insulation", "operating_mode", "price_class", "goal"]:
        if key in updates:
            facts[key] = updates[key]
    return {"facts": facts, "updates": updates, "language": detect_language(text)}


def apply_overrides(facts: dict, overrides: dict) -> dict:
    """Apply facts edited by the user in the UI panel 'What the agent knows'."""
    merged = copy.deepcopy(facts)
    for key, value in overrides.items():
        if key in EMPTY_FACTS:
            merged[key] = value
    return merged
