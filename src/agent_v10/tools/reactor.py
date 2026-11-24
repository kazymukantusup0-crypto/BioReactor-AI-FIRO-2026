"""get_reactor_status: the agent READS the live reactor and gives advice. It never switches relays.

The data is a copy of the status from src/hardware/live.py (the server's reactor thread). The answer is written by
Python (like «откуда данные?»): every number is the sensor value, the advice is a fixed rule, and the text always
says where the readings come from (СИМУЛЯТОР / RASPBERRY PI → ARDUINO) and that only a person switches relays.

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
    r"\s+(?:\w+\s+){0,2}(?:подогрев\w*|нагрев\w*|обогрев\w*|охлажд\w*|откачк\w*|насос\w*|реле|помп\w*|шнек\w*|автоматик\w*)|"
    r"\b(?:turn|switch)\s+(?:on|off)\s+(?:the\s+)?(?:heater|heating|cooling|cooler|pump|relay|auger)\w*|"
    r"\b(?:turn|switch)\s+(?:the\s+)?(?:heater|heating|cooling|cooler|pump|relay|auger)\w*\s+(?:on|off)\b|"
    r"\b(?:start|stop)\s+(?:the\s+)?(?:heater|heating|cooling|pump|auger)\b|"
    r"(?:қыздыр\w*|салқында\w*|сорғы\w*|реле\w*|шнек\w*)\s+(?:\w+\s+){0,1}(?:қос|өшір|іске\s+қос)\w*"
)

NAMES = {
    "ru": {"temp_c": "температура", "rh_pct": "влажность", "gas_in": "газ внутри (индикатор MQ, сырое значение 0–1023, не % метана)",
           "gas_out": "газ снаружи (датчик утечки, сырое значение 0–1023)", "heat": "подогрев", "cool": "охлаждение",
           "pump": "откачка газа", "auger": "шнек", "on": "вкл", "off": "выкл", "ok": "норма", "warn": "внимание",
           "danger": "опасно", "unknown": "датчик не отвечает", "auto": "автоматика Arduino", "manual": "ручной режим",
           "from_pi": "включено с ноутбука"},
    "en": {"temp_c": "temperature", "rh_pct": "humidity", "gas_in": "gas inside (MQ indicator, raw 0–1023, not % methane)",
           "gas_out": "gas outside (leak sensor, raw 0–1023)", "heat": "heater", "cool": "cooling", "pump": "gas pump",
           "auger": "auger", "on": "on", "off": "off", "ok": "normal", "warn": "attention", "danger": "danger",
           "unknown": "sensor not answering", "auto": "Arduino automatic mode", "manual": "manual mode",
           "from_pi": "switched on from the laptop"},
    "kk": {"temp_c": "температура", "rh_pct": "ылғалдылық", "gas_in": "ішіндегі газ (MQ индикаторы, шикі мән 0–1023, метан % емес)",
           "gas_out": "сыртқы газ (ағу датчигі, шикі мән 0–1023)", "heat": "қыздыру", "cool": "салқындату",
           "pump": "газды сору", "auger": "шнек", "on": "қосулы", "off": "өшірулі", "ok": "қалыпты", "warn": "назар",
           "danger": "қауіпті", "unknown": "датчик жауап бермейді", "auto": "Arduino автоматикасы", "manual": "қолмен режим",
           "from_pi": "ноутбуктан қосылған"},
}
UNITS = {"temp_c": " °C", "rh_pct": " %", "gas_in": "", "gas_out": ""}

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
    "source_pi_virtual": {
        "ru": "Датчики: RASPBERRY PI ({address}) → ВИРТУАЛЬНЫЙ ARDUINO — показания имитированы.",
        "en": "Sensors: RASPBERRY PI ({address}) → VIRTUAL ARDUINO — the readings are simulated.",
        "kk": "Датчиктер: RASPBERRY PI ({address}) → ВИРТУАЛДЫ ARDUINO — көрсеткіштер имитацияланған.",
    },
    "no_link_pi": {
        "ru": "НЕТ СВЯЗИ с Raspberry Pi: показаний нет, кнопки заблокированы. Если ноутбук молчит дольше 15 с, Pi сама "
              "выключает реле, включённые с ноутбука; автоматика Arduino продолжает работать.",
        "en": "NO LINK with the Raspberry Pi: no readings, the buttons are locked. When the laptop is silent for more than "
              "15 s, the Pi switches off the relays switched on from the laptop; the Arduino's automatic mode keeps working.",
        "kk": "Raspberry Pi-мен БАЙЛАНЫС ЖОҚ: көрсеткіштер жоқ, батырмалар бұғатталған. Ноутбук 15 с-тан артық үнсіз "
              "болса, Pi ноутбуктан қосылған релені өзі өшіреді; Arduino автоматикасы жұмысын жалғастырады.",
    },
    "no_link_arduino": {
        "ru": "НЕТ СВЯЗИ Raspberry Pi с Arduino (USB): показаний нет, кнопки заблокированы. Arduino через 10 с без связи "
              "сама выключает реле, включённые с Pi; её автоматика и защита работают и без Pi.",
        "en": "NO LINK between the Raspberry Pi and the Arduino (USB): no readings, the buttons are locked. After 10 s "
              "without a link the Arduino switches off the relays switched on from the Pi; its automatic mode and "
              "protection work without the Pi.",
        "kk": "Raspberry Pi мен Arduino арасында БАЙЛАНЫС ЖОҚ (USB): көрсеткіштер жоқ, батырмалар бұғатталған. Arduino "
              "10 с байланыссыз Pi-дан қосылған релені өзі өшіреді; оның автоматикасы мен қорғанысы Pi-сыз да жұмыс істейді.",
    },
    "now": {"ru": "Сейчас: {items}.", "en": "Now: {items}.", "kk": "Қазір: {items}."},
    "relays": {"ru": "Реле: {items}.", "en": "Relays: {items}.", "kk": "Реле: {items}."},
    "mode": {"ru": "Режим: {mode}.", "en": "Mode: {mode}.", "kk": "Режим: {mode}."},
    "advice_estop": {
        "ru": "АВАРИЙНАЯ ОСТАНОВКА (E-STOP): все реле выключены, автоматика выключена. Снимает её только человек — "
              "кнопка «Сбросить тревоги» на странице «Реактор» или удержание кнопки энкодера 3 с на Arduino.",
        "en": "EMERGENCY STOP (E-STOP): every relay is off, automatic mode is off. Only a person clears it — the «Reset "
              "alarms» button on the «Reactor» page or holding the encoder button for 3 s on the Arduino.",
        "kk": "АПАТТЫҚ ТОҚТАТУ (E-STOP): барлық реле өшірулі, автоматика өшірулі. Оны тек адам алады — «Реактор» "
              "бетіндегі «Дабылдарды тастау» батырмасы немесе Arduino энкодер батырмасын 3 с ұстау.",
    },
    "advice_leak": {
        "ru": "ТРЕВОГА: утечка газа снаружи — Arduino выключила все реле и автоматику. Проветрите, не используйте огонь; "
              "тревогу сбрасывает человек, когда газ снаружи станет ниже порога.",
        "en": "ALARM: gas leak outside — the Arduino switched every relay and the automatic mode off. Ventilate, no open "
              "fire; a person resets the alarm when the gas outside is below the limit.",
        "kk": "ДАБЫЛ: сыртта газ ағып жатыр — Arduino барлық релені және автоматиканы өшірді. Желдетіңіз, от "
              "жақпаңыз; сыртқы газ шектен төмендегенде дабылды адам тастайды.",
    },
    "advice_overheat": {
        "ru": "ТРЕВОГА: перегрев (порог {limit} °C) — подогрев выключен и заблокирован, пока температура не опустится на 2 °C.",
        "en": "ALARM: overheating (limit {limit} °C) — the heater is off and locked until the temperature drops by 2 °C.",
        "kk": "ДАБЫЛ: қызып кету (шегі {limit} °C) — қыздыру өшірулі және температура 2 °C төмендегенше бұғатталған.",
    },
    "advice_no_temp": {
        "ru": "Датчик температуры не отвечает — подогрев выключен и заблокирован (так безопаснее). Проверьте DS18B20 (пин 28).",
        "en": "The temperature sensor does not answer — the heater is off and locked (fail-safe). Check the DS18B20 (pin 28).",
        "kk": "Температура датчигі жауап бермейді — қыздыру өшірулі және бұғатталған. DS18B20 (28-пин) тексеріңіз.",
    },
    "advice_warmup": {
        "ru": "Датчики газа прогреваются после включения Arduino: подогрев и откачка пока заблокированы, утечка ещё не проверяется.",
        "en": "The gas sensors are warming up after the Arduino started: heater and pump are locked, leaks are not checked yet.",
        "kk": "Arduino қосылғаннан кейін газ датчиктері қызып жатыр: қыздыру мен сору әзірге бұғатталған.",
    },
    "advice_link_lost": {
        "ru": "Arduino сообщает о потере связи с Pi: реле, включённые с ноутбука, она выключила. Сбросить отметку — «Сбросить тревоги».",
        "en": "The Arduino reports a lost link with the Pi: it switched off the relays switched on from the laptop. Clear it with «Reset alarms».",
        "kk": "Arduino Pi-мен байланыс үзілгенін хабарлайды: ноутбуктан қосылған релені өшірді. «Дабылдарды тастау» батырмасымен алыңыз.",
    },
    "advice_auger_timeout": {
        "ru": "Шнек выключен автоматически: он работал без перерыва дольше 10 минут.",
        "en": "The auger was switched off automatically: it ran without a break for more than 10 minutes.",
        "kk": "Шнек автоматты түрде өшірілді: ол 10 минуттан артық үздіксіз жұмыс істеді.",
    },
    "advice_heat": {
        "ru": "Совет: температура {temp} °C ниже нижнего порога {low} °C — рекомендую включить подогрев или автоматику.",
        "en": "Advice: the temperature {temp} °C is below the lower limit {low} °C — I recommend switching the heater or the automatic mode on.",
        "kk": "Кеңес: температура {temp} °C төменгі {low} °C шегінен төмен — қыздыруды немесе автоматиканы қосуды ұсынамын.",
    },
    "advice_heat_running": {
        "ru": "Температура {temp} °C ниже нижнего порога {low} °C; подогрев включён — температура поднимается медленно.",
        "en": "The temperature {temp} °C is below the lower limit {low} °C; the heater is on — it rises slowly.",
        "kk": "Температура {temp} °C төменгі {low} °C шегінен төмен; қыздыру қосулы — температура баяу көтеріледі.",
    },
    "advice_cool": {
        "ru": "Совет: температура {temp} °C выше верхнего порога {high} °C — рекомендую выключить подогрев и включить охлаждение.",
        "en": "Advice: the temperature {temp} °C is above the upper limit {high} °C — switch the heater off and the cooling on.",
        "kk": "Кеңес: температура {temp} °C жоғарғы {high} °C шегінен жоғары — қыздыруды өшіріп, салқындатуды қосыңыз.",
    },
    "advice_auto_temp": {
        "ru": "Температура {temp} °C вне диапазона {low}–{high} °C; автоматика Arduino сама включает подогрев или охлаждение.",
        "en": "The temperature {temp} °C is outside {low}–{high} °C; the Arduino's automatic mode switches heating or cooling itself.",
        "kk": "Температура {temp} °C {low}–{high} °C аралығынан тыс; Arduino автоматикасы қыздыруды не салқындатуды өзі қосады.",
    },
    "advice_pump": {
        "ru": "Совет: газ внутри {gas} (сырое значение) выше порога откачки {limit} — пора откачивать газ.",
        "en": "Advice: gas inside {gas} (raw value) is above the pump limit {limit} — time to pump the gas out.",
        "kk": "Кеңес: ішіндегі газ {gas} (шикі мән) сору шегінен {limit} жоғары — газды сору керек.",
    },
    "advice_pump_auto": {
        "ru": "Газ внутри {gas} выше порога откачки {limit}; откачка: {state}.",
        "en": "Gas inside {gas} is above the pump limit {limit}; pump: {state}.",
        "kk": "Ішіндегі газ {gas} сору шегінен {limit} жоғары; сору: {state}.",
    },
    "all_ok": {
        "ru": "Всё в норме, действий не нужно.", "en": "Everything is normal, no action needed.",
        "kk": "Бәрі қалыпты, әрекет қажет емес.",
    },
    "human_only": {
        "ru": "Реле, автоматику и пороги меняет только человек кнопкой на странице «Реактор» (с подтверждением); я только читаю показания и советую.",
        "en": "Only a person switches the relays, the automatic mode and the limits, with a button on the «Reactor» page (with confirmation); I only read the readings and advise.",
        "kk": "Релені, автоматиканы және шектерді тек адам «Реактор» бетіндегі батырмамен (растаумен) өзгертеді; мен тек көрсеткіштерді оқып, кеңес беремін.",
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
    return f"{value:.1f}"


def _num(value: float) -> str:
    return f"{value:g}"


def is_reactor_question(text: str) -> bool:
    return bool(re.search(REACTOR_WORDS, text, re.IGNORECASE) or re.search(CONTROL_WORDS, text, re.IGNORECASE))


def is_control_request(text: str) -> bool:
    return bool(re.search(CONTROL_WORDS, text, re.IGNORECASE))


def advice(status: dict, language: str) -> list[dict]:
    """Fixed rules -> advice codes and texts. Advice only: nothing here can switch a relay."""
    if not status["link"]["ok"]:
        key = "no_link_arduino" if status["link"].get("level") == "arduino" else "no_link_pi"
        return [{"code": key, "level": "danger", "text": _t(key, language)}]
    out = []
    flags = status.get("arduino_alarms") or {}
    limits = status.get("limits") or {}
    readings, relays, auto = status["readings"], status["relays"], bool(status.get("auto"))
    if flags.get("estop"):
        out.append({"code": "estop", "level": "danger", "text": _t("advice_estop", language)})
    if flags.get("leak"):
        out.append({"code": "leak", "level": "danger", "text": _t("advice_leak", language)})
    if flags.get("overheat"):
        out.append({"code": "overheat", "level": "danger",
                    "text": _t("advice_overheat", language, limit=_num(limits.get("temp_hard_max", 45)))})
    if flags.get("no_temp"):
        out.append({"code": "no_temp", "level": "danger", "text": _t("advice_no_temp", language)})
    if flags.get("link_lost"):
        out.append({"code": "link_lost", "level": "warn", "text": _t("advice_link_lost", language)})
    if any(a.get("code") == "auger_timeout" for a in status.get("alarms", [])):
        out.append({"code": "auger_timeout", "level": "warn", "text": _t("advice_auger_timeout", language)})
    if flags.get("warmup"):
        out.append({"code": "warmup", "level": "warn", "text": _t("advice_warmup", language)})
    stopped = flags.get("estop") or flags.get("leak")
    temp = readings["temp_c"]["value"]
    if temp is not None and limits and not stopped and not flags.get("overheat"):
        low, high = limits["temp_min"], limits["temp_max"]
        values = {"temp": _fmt(temp, "temp_c"), "low": _num(low), "high": _num(high)}
        if (temp < low or temp > high) and auto:
            out.append({"code": "auto_temp", "level": "warn", "text": _t("advice_auto_temp", language, **values)})
        elif temp < low:
            if relays["heat"]["on"]:
                out.append({"code": "heating", "level": "warn", "text": _t("advice_heat_running", language, **values)})
            elif not flags.get("warmup"):
                out.append({"code": "heat_on", "level": "warn", "text": _t("advice_heat", language, **values)})
        elif temp > high:
            out.append({"code": "cool_on", "level": "warn", "text": _t("advice_cool", language, **values)})
    gas = readings["gas_in"]["value"]
    if gas is not None and limits and gas > limits["gas_in_limit"] and not stopped:
        values = {"gas": _fmt(gas, "gas_in"), "limit": int(limits["gas_in_limit"])}
        names = NAMES.get(language, NAMES["ru"])
        if relays["pump"]["on"] or auto:
            state = names["on"] if relays["pump"]["on"] else names["auto"]
            out.append({"code": "pumping", "level": "warn", "text": _t("advice_pump_auto", language, state=state, **values)})
        elif not flags.get("warmup"):
            out.append({"code": "pump_on", "level": "warn", "text": _t("advice_pump", language, **values)})
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
    if source["kind"] == "simulator":
        parts.append(_t("source_sim", language))
    elif source.get("arduino_port") == "virtual":
        parts.append(_t("source_pi_virtual", language, address=source.get("address") or "?"))
    else:
        parts.append(_t("source_pi", language, address=source.get("address") or "?"))
    if data["link_ok"]:
        items = []
        for name, reading in data["readings"].items():
            if reading["value"] is None:
                items.append(f"{names[name]} — {names['unknown']}")
            else:
                note = f" ({names[reading['level']]})" if reading["level"] != "ok" else ""
                items.append(f"{names[name]} {_fmt(reading['value'], name)}{UNITS[name]}{note}")
        parts.append(_t("now", language, items="; ".join(items)))
        relays = ", ".join(f"{names[n]} — {names['on' if r['on'] else 'off']}"
                           + (f" ({names['from_pi']})" if r.get("remote") and r["on"] else "")
                           for n, r in data["relays"].items())
        parts.append(_t("relays", language, items=relays))
        if data.get("auto") is not None:
            parts.append(_t("mode", language, mode=names["auto" if data["auto"] else "manual"]))
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
            "readings": readings, "relays": {n: {"on": r["on"], "remote": r.get("remote", False), "on_for_s": r["on_for_s"]}
                                             for n, r in status["relays"].items()},
            "auto": status.get("auto"), "limits": status.get("limits"),
            "alarms": status["alarms"], "advice": advice(status, language)}
    real = status["source"]["kind"] == "pi" and status["source"].get("arduino_port") != "virtual"
    label = "measured" if real else "assumption"
    return result("get_reactor_status", ok=True, data=data,
                  llm={"source": status["source"]["kind"], "link_ok": data["link_ok"],
                       "readings": {n: r["value"] for n, r in readings.items()},
                       "advice": [a["code"] for a in data["advice"]]}, label=label)
