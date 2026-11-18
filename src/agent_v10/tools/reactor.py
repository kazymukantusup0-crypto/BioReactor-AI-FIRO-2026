"""get_reactor_status: the agent READS the live reactor and gives advice. It never switches relays.

The data is a copy of the status from src/hardware/live.py (the server's reactor thread). The answer is written by
Python (like «откуда данные?»): every number is the sensor value, the advice is a fixed rule, and the text always
says where the readings come from (СИМУЛЯТОР / ПЛАТА (COM3)) and that only a person switches relays.

Questions that come here (agent.run, before the LLM):
    REACTOR_WORDS   «что сейчас в реакторе?», «какая температура в реакторе сейчас?», «показания датчиков»,
                    «пора откачивать?», «есть утечка?», «what do the sensors show?», «реактор қазір қандай?»
    CONTROL_WORDS   «включи подогрев», «turn on the pump», «қыздыруды қос» -> refusal + the current status
"""
from __future__ import annotations

import re

from src.agent_v10.tools.common import result

REACTOR_WORDS = (
    r"датчик\w*|показани\w*|сенсор\w*|"
    r"(?:сейчас|щас|текущ\w*)\s+(?:\w+\s+){0,3}(?:в\s+)?(?:реактор\w*|бочк\w*)|"
    r"(?:в\s+)?(?:реактор\w*|бочк\w*)\s+(?:\w+\s+){0,2}(?:сейчас|щас)|"
    r"(?:что|как)\s+(?:там\s+)?(?:сейчас\s+)?с\s+реактор\w*|состояни\w*\s+реактор\w*|"
    r"утечк\w*|пора\s+(?:ли\s+)?откачи\w*|откачи\w*\s+(?:газ\w*\s+)?(?:пора|нужно|надо)|"
    r"давлени\w*\s+(?:газа\s+)?(?:в\s+реактор\w*|сейчас)|\bреле\b|"
    r"\bsensors?\b|\breadings?\b|\bright\s+now\b|reactor\s+status|status\s+of\s+the\s+reactor|"
    r"(?:in|inside)\s+the\s+reactor\s+now|current\s+(?:temperature|pressure|humidity)|\bleak\w*|\brelays?\b|"
    r"time\s+to\s+pump|"
    r"датчик\w*|көрсеткіш\w*|реактор\w*\s+қазір|қазір\s+(?:\w+\s+){0,2}реактор\w*|газ\s+ағ\w*|ағып\s+(?:жатыр|кет\w*)"
)
CONTROL_WORDS = (
    r"(?:включи|включите|включить|выключи|выключите|выключить|запусти|запустите|останови|остановите|отключи\w*)"
    r"\s+(?:\w+\s+){0,2}(?:подогрев\w*|нагрев\w*|обогрев\w*|охлажд\w*|откачк\w*|насос\w*|реле|помп\w*)|"
    r"\b(?:turn|switch)\s+(?:on|off)\s+(?:the\s+)?(?:heater|heating|cooling|cooler|pump|relay)\w*|"
    r"\b(?:turn|switch)\s+(?:the\s+)?(?:heater|heating|cooling|cooler|pump|relay)\w*\s+(?:on|off)\b|"
    r"\b(?:start|stop)\s+(?:the\s+)?(?:heater|heating|cooling|pump)\b|"
    r"(?:қыздыр\w*|салқында\w*|сорғы\w*|реле\w*)\s+(?:\w+\s+){0,1}(?:қос|өшір|іске\s+қос)\w*"
)

NAMES = {
    "ru": {"temp_c": "температура", "rh_pct": "влажность", "gas_in": "газ внутри (индекс MQ, не % метана)",
           "gas_out": "газ снаружи (датчик утечки)", "p_kpa": "давление газа", "heat": "подогрев", "cool": "охлаждение",
           "pump": "откачка газа", "on": "вкл", "off": "выкл", "ok": "норма", "warn": "внимание", "danger": "опасно",
           "unknown": "датчик не отвечает"},
    "en": {"temp_c": "temperature", "rh_pct": "humidity", "gas_in": "gas inside (MQ index, not % methane)",
           "gas_out": "gas outside (leak sensor)", "p_kpa": "gas pressure", "heat": "heater", "cool": "cooling",
           "pump": "gas pump", "on": "on", "off": "off", "ok": "normal", "warn": "attention", "danger": "danger",
           "unknown": "sensor not answering"},
    "kk": {"temp_c": "температура", "rh_pct": "ылғалдылық", "gas_in": "ішіндегі газ (MQ индексі, метан % емес)",
           "gas_out": "сыртқы газ (ағу датчигі)", "p_kpa": "газ қысымы", "heat": "қыздыру", "cool": "салқындату",
           "pump": "газды сору", "on": "қосулы", "off": "өшірулі", "ok": "қалыпты", "warn": "назар", "danger": "қауіпті",
           "unknown": "датчик жауап бермейді"},
}
UNITS = {"temp_c": " °C", "rh_pct": " %", "gas_in": "", "gas_out": "", "p_kpa": {"ru": " кПа", "en": " kPa", "kk": " кПа"}}

TEXTS = {
    "no_manager": {
        "ru": "Живых показаний нет: связь с реактором в этом сервере не запущена. Откройте страницу «Реактор».",
        "en": "No live readings: the reactor connection is not running in this server. Open the «Reactor» page.",
        "kk": "Тікелей көрсеткіштер жоқ: бұл серверде реактормен байланыс іске қосылмаған. «Реактор» бетін ашыңыз.",
    },
    "source_sim": {
        "ru": "Датчики: СИМУЛЯТОР — это имитация, не реальный реактор.",
        "en": "Sensors: SIMULATOR — this is a simulation, not the real reactor.",
        "kk": "Датчиктер: СИМУЛЯТОР — бұл имитация, нақты реактор емес.",
    },
    "source_pi": {
        "ru": "Датчики: RASPBERRY PI → ARDUINO ({address}).", "en": "Sensors: RASPBERRY PI → ARDUINO ({address}).",
        "kk": "Датчиктер: RASPBERRY PI → ARDUINO ({address}).",
    },
    "no_link_pi": {
        "ru": "НЕТ СВЯЗИ с Raspberry Pi: показаний нет, кнопки заблокированы. Pi сам выключает все реле, если ноутбук "
              "молчит дольше 15 с, а Arduino — если 10 с нет команд.",
        "en": "NO LINK with the Raspberry Pi: no readings, the buttons are locked. The Pi switches every relay off by "
              "itself when the laptop is silent for more than 15 s, and the Arduino does after 10 s without commands.",
        "kk": "Raspberry Pi-мен БАЙЛАНЫС ЖОҚ: көрсеткіштер жоқ, батырмалар бұғатталған. Ноутбук 15 с-тан артық үнсіз "
              "болса, Pi барлық релені өзі өшіреді, ал Arduino 10 с командасыз өшіреді.",
    },
    "no_link_arduino": {
        "ru": "НЕТ СВЯЗИ Raspberry Pi с Arduino (USB): показаний нет, кнопки заблокированы. Arduino сама выключает "
              "все реле через 10 с без команд.",
        "en": "NO LINK between the Raspberry Pi and the Arduino (USB): no readings, the buttons are locked. The Arduino "
              "switches every relay off by itself after 10 s without commands.",
        "kk": "Raspberry Pi мен Arduino арасында БАЙЛАНЫС ЖОҚ (USB): көрсеткіштер жоқ, батырмалар бұғатталған. "
              "Arduino 10 с командасыз барлық релені өзі өшіреді.",
    },
    "now": {"ru": "Сейчас: {items}.", "en": "Now: {items}.", "kk": "Қазір: {items}."},
    "relays": {"ru": "Реле: {items}.", "en": "Relays: {items}.", "kk": "Реле: {items}."},
    "advice_heat": {
        "ru": "Совет: температура {temp} °C ниже режима {target} °C — рекомендую включить подогрев.",
        "en": "Advice: the temperature {temp} °C is below the {target} °C regime — I recommend switching the heater on.",
        "kk": "Кеңес: температура {temp} °C {target} °C режимінен төмен — қыздыруды қосуды ұсынамын.",
    },
    "advice_heat_running": {
        "ru": "Температура {temp} °C ниже режима {target} °C; подогрев уже включён — температура поднимается медленно.",
        "en": "The temperature {temp} °C is below the {target} °C regime; the heater is already on — it rises slowly.",
        "kk": "Температура {temp} °C {target} °C режимінен төмен; қыздыру қосулы — температура баяу көтеріледі.",
    },
    "advice_cool": {
        "ru": "Совет: температура {temp} °C выше нормы (до {limit} °C) — рекомендую выключить подогрев и включить охлаждение.",
        "en": "Advice: the temperature {temp} °C is above normal (up to {limit} °C) — switch the heater off and the cooling on.",
        "kk": "Кеңес: температура {temp} °C қалыптыдан жоғары ({limit} °C дейін) — қыздыруды өшіріп, салқындатуды қосыңыз.",
    },
    "advice_pump": {
        "ru": "Совет: давление газа {p} кПа — газ скопился, пора откачивать (порог {limit} кПа).",
        "en": "Advice: gas pressure {p} kPa — gas has accumulated, time to pump it out (threshold {limit} kPa).",
        "kk": "Кеңес: газ қысымы {p} кПа — газ жиналды, сору керек (шегі {limit} кПа).",
    },
    "advice_pump_now": {
        "ru": "ОПАСНО: давление газа {p} кПа выше {limit} кПа — откачайте газ немедленно.",
        "en": "DANGER: gas pressure {p} kPa is above {limit} kPa — pump the gas out now.",
        "kk": "ҚАУІПТІ: газ қысымы {p} кПа, {limit} кПа-дан жоғары — газды дереу сорыңыз.",
    },
    "advice_leak": {
        "ru": "ТРЕВОГА: утечка газа снаружи — подогрев выключен автоматически и заблокирован. Проветрите, не используйте "
              "огонь; тревогу сбрасывает человек на странице «Реактор», когда газ уйдёт.",
        "en": "ALARM: gas leak outside — the heater was switched off automatically and is locked. Ventilate, no open "
              "fire; a person resets the alarm on the «Reactor» page when the gas is gone.",
        "kk": "ДАБЫЛ: сыртта газ ағып жатыр — қыздыру автоматты түрде өшіріліп, бұғатталды. Желдетіңіз, от "
              "жақпаңыз; газ кеткенде дабылды адам «Реактор» бетінде өшіреді.",
    },
    "advice_overheat": {
        "ru": "ТРЕВОГА: перегрев — подогрев выключен автоматически, включить его можно после остывания.",
        "en": "ALARM: overheating — the heater was switched off automatically; it can be switched on after cooling down.",
        "kk": "ДАБЫЛ: қызып кету — қыздыру автоматты түрде өшірілді, суығаннан кейін қосуға болады.",
    },
    "all_ok": {
        "ru": "Всё в норме, действий не нужно.", "en": "Everything is normal, no action needed.",
        "kk": "Бәрі қалыпты, әрекет қажет емес.",
    },
    "human_only": {
        "ru": "Реле включает и выключает только человек кнопкой на странице «Реактор» (с подтверждением); я только читаю показания и советую.",
        "en": "Only a person switches the relays, with a button on the «Reactor» page (with confirmation); I only read the readings and advise.",
        "kk": "Релені тек адам «Реактор» бетіндегі батырмамен (растаумен) қосып-өшіреді; мен тек көрсеткіштерді оқып, кеңес беремін.",
    },
    "refuse_control": {
        "ru": "Я не управляю реле — это делает только человек.",
        "en": "I do not control the relays — only a person does.",
        "kk": "Мен релені басқармаймын — мұны тек адам жасайды.",
    },
}


def _t(key: str, language: str, **values) -> str:
    texts = TEXTS[key]
    return texts.get(language, texts["ru"]).format(**values)


def _fmt(value: float, name: str) -> str:
    if name in {"gas_in", "gas_out"}:
        return str(int(round(value)))
    if name == "p_kpa":
        return f"{value:.2f}"
    return f"{value:.1f}"


def is_reactor_question(text: str) -> bool:
    return bool(re.search(REACTOR_WORDS, text, re.IGNORECASE) or re.search(CONTROL_WORDS, text, re.IGNORECASE))


def is_control_request(text: str) -> bool:
    return bool(re.search(CONTROL_WORDS, text, re.IGNORECASE))


def advice(status: dict, language: str) -> list[dict]:
    """Fixed rules -> advice codes and texts. Advice only: nothing here can switch a relay."""
    th = status["thresholds"]
    if not status["link"]["ok"]:
        key = "no_link_arduino" if status["link"].get("level") == "arduino" else "no_link_pi"
        return [{"code": key, "level": "danger", "text": _t(key, language)}]
    out = []
    readings, relays = status["readings"], status["relays"]
    if status.get("leak_latched"):
        out.append({"code": "leak", "level": "danger", "text": _t("advice_leak", language)})
    if status.get("overheat"):
        out.append({"code": "overheat", "level": "danger", "text": _t("advice_overheat", language)})
    temp = readings["temp_c"]["value"]
    target = th["temp_c"]["target"]
    if temp is not None and temp < th["temp_c"]["warn_low"]:
        if relays["heat"]["on"]:
            out.append({"code": "heating", "level": "warn",
                        "text": _t("advice_heat_running", language, temp=_fmt(temp, "temp_c"), target=target)})
        elif not status.get("leak_latched"):
            out.append({"code": "heat_on", "level": "warn",
                        "text": _t("advice_heat", language, temp=_fmt(temp, "temp_c"), target=target)})
    elif temp is not None and temp > th["temp_c"]["warn_high"] and not status.get("overheat"):
        out.append({"code": "cool_on", "level": "warn",
                    "text": _t("advice_cool", language, temp=_fmt(temp, "temp_c"), limit=th["temp_c"]["warn_high"])})
    p = readings["p_kpa"]["value"]
    if p is not None and p >= th["pressure_kpa"]["danger"]:
        out.append({"code": "pump_now", "level": "danger",
                    "text": _t("advice_pump_now", language, p=_fmt(p, "p_kpa"), limit=th["pressure_kpa"]["danger"])})
    elif p is not None and p >= th["pressure_kpa"]["pump_warn"] and not relays["pump"]["on"]:
        out.append({"code": "pump_on", "level": "warn",
                    "text": _t("advice_pump", language, p=_fmt(p, "p_kpa"), limit=th["pressure_kpa"]["pump_warn"])})
    if not out:
        out.append({"code": "ok", "level": "ok", "text": _t("all_ok", language)})
    return out


def answer_text(output: dict, language: str, control_request: bool = False) -> str:
    """The whole answer, written by Python."""
    data = output["data"]
    parts = [_t("refuse_control", language)] if control_request else []
    if data["status"] == "no_manager":
        parts.append(_t("no_manager", language))
        parts.append(_t("human_only", language))
        return " ".join(parts)
    names = NAMES.get(language, NAMES["ru"])
    source = data["source"]
    parts.append(_t("source_sim", language) if source["kind"] == "simulator"
                 else _t("source_pi", language, address=source.get("address") or "?"))
    if data["link_ok"]:
        items = []
        for name, reading in data["readings"].items():
            unit = UNITS[name] if isinstance(UNITS[name], str) else UNITS[name].get(language, UNITS[name]["ru"])
            if reading["value"] is None:
                items.append(f"{names[name]} — {names['unknown']}")
            else:
                note = f" ({names[reading['level']]})" if reading["level"] != "ok" else ""
                items.append(f"{names[name]} {_fmt(reading['value'], name)}{unit}{note}")
        parts.append(_t("now", language, items="; ".join(items)))
        relays = ", ".join(f"{names[n]} — {names['on' if r['on'] else 'off']}" for n, r in data["relays"].items())
        parts.append(_t("relays", language, items=relays))
    parts += [item["text"] for item in data["advice"]]
    parts.append(_t("human_only", language))
    return " ".join(parts)


def get_reactor_status(language: str = "ru", status: dict | None = None) -> dict:
    """Live readings + advice. status=None reads src/hardware/live.snapshot() (a copy; read-only)."""
    if status is None:
        from src.hardware import live
        status = live.snapshot()
    if status is None:
        return result("get_reactor_status", ok=True, data={"status": "no_manager", "advice": []},
                      llm={"status": "no live connection"}, label="measured")
    readings = {name: {"value": r["value"], "level": r["level"]} for name, r in status["readings"].items()}
    data = {"status": "ok", "source": status["source"], "link_ok": status["link"]["ok"],
            "readings": readings, "relays": {n: {"on": r["on"], "on_for_s": r["on_for_s"]} for n, r in status["relays"].items()},
            "alarms": status["alarms"], "advice": advice(status, language)}
    label = "measured" if status["source"]["kind"] == "pi" else "assumption"
    return result("get_reactor_status", ok=True, data=data,
                  llm={"source": status["source"]["kind"], "link_ok": data["link_ok"],
                       "readings": {n: r["value"] for n, r in readings.items()},
                       "advice": [a["code"] for a in data["advice"]]}, label=label)
