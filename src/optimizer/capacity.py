"""Volume-only reactor charge checks; these do not certify process safety."""

from math import isclose, isfinite


def assess_reactor_capacity(*, feedstock_volume_l=None, reactor_total_volume_l=None,
                            reactor_working_volume_l=None, dilution_water_l=None,
                            inoculum_volume_l=None, resident_liquid_volume_l=None):
    """Assess whether a reported liquid lot fits, preserving unknown working capacity.

    Nominal vessel volume is only a hard upper bound. It is never treated as
    working volume, and this check never converts volume to mass.
    """
    values = {
        "feedstock_volume_l": feedstock_volume_l,
        "reactor_total_volume_l": reactor_total_volume_l,
        "reactor_working_volume_l": reactor_working_volume_l,
        "dilution_water_l": dilution_water_l,
        "inoculum_volume_l": inoculum_volume_l,
        "resident_liquid_volume_l": resident_liquid_volume_l,
    }
    for key, value in values.items():
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or value < 0):
            return {"status": "INVALID_INPUT", "simultaneous_load_possible": None,
                    "exact_batch_count": None, "invalid_field": key}

    feed = feedstock_volume_l
    total = reactor_total_volume_l
    working = reactor_working_volume_l
    if feed is None or total is None:
        return {"status": "NOT_ASSESSED", "simultaneous_load_possible": None,
                "exact_batch_count": None, "missing": [k for k, v in (("feedstock_volume_l", feed), ("reactor_total_volume_l", total)) if v is None]}
    if feed > total:
        return {"status": "EXCEEDS_NOMINAL", "simultaneous_load_possible": False,
                "exact_batch_count": None, "feedstock_volume_l": feed,
                "reactor_total_volume_l": total, "reactor_working_volume_l": working}
    if working is not None and working > total:
        return {"status": "INVALID_VESSEL_GEOMETRY", "simultaneous_load_possible": False,
                "exact_batch_count": None, "feedstock_volume_l": feed,
                "reactor_total_volume_l": total, "reactor_working_volume_l": working}
    if working is None:
        return {"status": "WORKING_VOLUME_UNKNOWN", "simultaneous_load_possible": None,
                "exact_batch_count": None, "feedstock_volume_l": feed,
                "reactor_total_volume_l": total, "reactor_working_volume_l": None}
    if feed > working:
        return {"status": "EXCEEDS_WORKING_VOLUME", "simultaneous_load_possible": False,
                "exact_batch_count": None, "feedstock_volume_l": feed,
                "reactor_total_volume_l": total, "reactor_working_volume_l": working}

    occupancy = (inoculum_volume_l, dilution_water_l, resident_liquid_volume_l)
    declared = sum(v for v in occupancy if v is not None)
    if feed + declared > working:
        return {"status": "EXCEEDS_WORKING_VOLUME", "simultaneous_load_possible": False,
                "exact_batch_count": None, "feedstock_volume_l": feed,
                "declared_other_liquid_l": declared, "reactor_total_volume_l": total,
                "reactor_working_volume_l": working}
    if any(v is None for v in occupancy):
        return {"status": "OCCUPANCY_INCOMPLETE", "simultaneous_load_possible": None,
                "exact_batch_count": None, "feedstock_volume_l": feed,
                "declared_other_liquid_l": declared, "reactor_total_volume_l": total,
                "reactor_working_volume_l": working,
                "missing": [k for k, v in (("inoculum_volume_l", inoculum_volume_l),
                                           ("dilution_water_l", dilution_water_l),
                                           ("resident_liquid_volume_l", resident_liquid_volume_l)) if v is None]}
    return {"status": "WITHIN_DECLARED_WORKING_VOLUME", "simultaneous_load_possible": True,
            "exact_batch_count": None, "feedstock_volume_l": feed,
            "declared_other_liquid_l": declared, "reactor_total_volume_l": total,
            "reactor_working_volume_l": working,
            "note": "Volume consistency only; not process or safety approval."}


def assess_dialogue_state(state):
    """Read normalized litres from dialogue facts without inferring density."""
    feed = state.value("material_volume_l")
    total = state.value("reactor_total_volume_l")
    working = state.value("reactor_working_volume_l")
    def value(name):
        fact = state.facts.get(name)
        return fact.value if fact is not None else None
    return assess_reactor_capacity(
        feedstock_volume_l=feed,
        reactor_total_volume_l=total,
        reactor_working_volume_l=working,
        dilution_water_l=value("dilution_water_l"),
        inoculum_volume_l=value("inoculum_volume_l"),
        resident_liquid_volume_l=value("resident_liquid_volume_l"),
    )


def render_capacity_notice(assessment, language="ru"):
    """Render the deterministic capacity gate before any model prose."""
    status = assessment.get("status")
    if status in {None, "NOT_ASSESSED", "INVALID_INPUT"}:
        return None
    feed = assessment.get("feedstock_volume_l")
    total = assessment.get("reactor_total_volume_l")
    working = assessment.get("reactor_working_volume_l")
    fmt = lambda n: (f"{n:g}").replace(".", ",") if language in {"ru", "kk"} else f"{n:g}"
    if language == "en":
        if status == "EXCEEDS_NOMINAL":
            return f"The {fmt(feed)} L lot exceeds the reactor's nominal total volume of {fmt(total)} L, so it cannot be loaded all at once. Nominal volume is not working volume. Use sequential batches or a larger reactor; I cannot give an exact batch count without confirmed working volume, water, inoculum and process constraints. Any whole-lot methane potential is not a one-cycle yield; the cycle output is unknown."
        if status == "INVALID_VESSEL_GEOMETRY":
            return "The reported working volume exceeds nominal vessel volume. The geometry inputs conflict, so no simultaneous-loading or per-cycle conclusion is valid."
        if status == "EXCEEDS_WORKING_VOLUME":
            return f"The declared liquid charge exceeds the confirmed working volume ({fmt(working)} L). Do not load it simultaneously; use staged batches or a larger reactor. An exact batch count is unavailable until all liquid inputs and process constraints are confirmed."
        if status == "WORKING_VOLUME_UNKNOWN":
            equal = isclose(feed, total, rel_tol=0.0, abs_tol=1e-9)
            if equal:
                return f"The {fmt(feed)} L lot equals the reactor's nominal total volume ({fmt(total)} L), but working volume is unknown. Filling to nominal leaves no room for inoculum or gas headspace; do not fill to the brim. Per-cycle yield is unconfirmed."
            return f"The {fmt(feed)} L lot is below nominal volume ({fmt(total)} L); working volume is unknown, so simultaneous loading is unconfirmed. Do not fill to the brim; account for water, inoculum, resident liquid and headspace. Per-cycle yield and batch count remain unknown."
        if status == "OCCUPANCY_INCOMPLETE":
            return f"The feed volume is below the confirmed working volume ({fmt(working)} L), but the full liquid occupancy is not specified. Water, inoculum and resident contents also use working volume, so simultaneous loading is not yet confirmed."
        return f"The declared liquid volumes total {fmt(feed + assessment.get('declared_other_liquid_l', 0))} L within the {fmt(working)} L working volume. This is a volume check only, not an operating or safety approval; it does not establish methane yield per cycle."
    if language == "kk":
        if status == "EXCEEDS_NOMINAL":
            return (f"{fmt(feed)} л партия реактордың {fmt(total)} л номинал толық көлемінен асады, сондықтан оны бір мезгілде толық тиеу мүмкін емес. Номинал көлем жұмыс көлеміне тең емес. Кезең-кезеңмен бірнеше партия өңдеңіз немесе үлкен реактор таңдаңыз; жұмыс көлемі, су, инокулят және технологиялық шектеулер анықталмайынша партия санын есептемеймін. Бүкіл партияның ықтимал метаны бір циклдің шығымы емес; циклдік шығым белгісіз.")
        if status == "INVALID_VESSEL_GEOMETRY":
            return "Көрсетілген жұмыс көлемі реактордың толық көлемінен үлкен. Геометрия деректері қайшы болғандықтан, бір мезгілде тиеу немесе циклдік шығым туралы қорытынды жасауға болмайды."
        if status == "EXCEEDS_WORKING_VOLUME":
            return f"Көрсетілген сұйық жүктеме расталған {fmt(working)} л жұмыс көлемінен асады. Оны бір мезгілде тиеуге болмайды; бірнеше кезеңмен өңдеу немесе үлкен реактор қажет."
        if status == "WORKING_VOLUME_UNKNOWN":
            if isclose(feed, total, rel_tol=0.0, abs_tol=1e-9):
                return f"{fmt(feed)} л партия реактордың {fmt(total)} л номинал толық көлеміне тең, бірақ жұмыс көлемі белгісіз. Номинал деңгейге дейін толтырса, инокулят пен газ кеңістігіне орын қалмайды; реакторды ернеуіне дейін толтырмаңыз. Циклдік шығым расталмаған."
            return f"{fmt(feed)} л партия {fmt(total)} л номинал көлемнен аз, бірақ жұмыс көлемі белгісіз, тиеу расталмаған. Реакторды ернеуіне дейін толтырмаңыз; су, инокулят, қалған сұйықтық пен газ кеңістігін ескеріңіз. Циклдік шығым белгісіз."
        if status == "OCCUPANCY_INCOMPLETE":
            return f"Шикізат көлемі расталған {fmt(working)} л жұмыс көлемінен аз, бірақ сұйықтықтардың толық көлемі белгісіз. Су, инокулят және реактордағы сұйықтық та жұмыс көлемін алады; бірге тиеу расталмаған."
        return f"Көрсетілген сұйық көлемдер {fmt(working)} л жұмыс көлеміне сыяды. Бұл тек көлем сәйкестігін тексеру, пайдалану қауіпсіздігін растау емес; бір циклдегі метан шығымын анықтамайды."
    if language == "ru" and status == "EXCEEDS_NOMINAL":
        return f"{fmt(feed)} \u043b\u0438\u0442\u0440\u043e\u0432 \u0441\u044b\u0440\u044c\u044f \u043d\u0435\u0432\u043e\u0437\u043c\u043e\u0436\u043d\u043e \u043e\u0434\u043d\u043e\u0432\u0440\u0435\u043c\u0435\u043d\u043d\u043e \u0437\u0430\u0433\u0440\u0443\u0437\u0438\u0442\u044c \u0432 \u0440\u0435\u0430\u043a\u0442\u043e\u0440 \u043d\u043e\u043c\u0438\u043d\u0430\u043b\u044c\u043d\u043e\u0439 \u0432\u043c\u0435\u0441\u0442\u0438\u043c\u043e\u0441\u0442\u044c\u044e {fmt(total)} \u043b\u0438\u0442\u0440\u043e\u0432. \u0422\u0440\u0435\u0431\u0443\u0435\u0442\u0441\u044f \u043d\u0435\u0441\u043a\u043e\u043b\u044c\u043a\u043e \u043f\u043e\u0441\u043b\u0435\u0434\u043e\u0432\u0430\u0442\u0435\u043b\u044c\u043d\u044b\u0445 \u043f\u0430\u0440\u0442\u0438\u0439 \u0438\u043b\u0438 \u0440\u0435\u0430\u043a\u0442\u043e\u0440 \u0431\u043e\u043b\u044c\u0448\u0435\u0433\u043e \u043e\u0431\u044a\u0451\u043c\u0430. \u0422\u043e\u0447\u043d\u044b\u0439 \u043e\u0431\u044a\u0451\u043c \u043e\u0434\u043d\u043e\u0439 \u043f\u0430\u0440\u0442\u0438\u0438 \u0437\u0430\u0432\u0438\u0441\u0438\u0442 \u043e\u0442 \u043f\u043e\u0434\u0442\u0432\u0435\u0440\u0436\u0434\u0451\u043d\u043d\u043e\u0433\u043e \u0440\u0430\u0431\u043e\u0447\u0435\u0433\u043e \u043e\u0431\u044a\u0451\u043c\u0430, \u0432\u043e\u0434\u044b \u0438 \u0438\u043d\u043e\u043a\u0443\u043b\u044f\u0442\u0430. \u0427\u0438\u0441\u043b\u043e \u043f\u0430\u0440\u0442\u0438\u0439 \u0431\u0435\u0437 \u0442\u0435\u0445\u043d\u043e\u043b\u043e\u0433\u0438\u0447\u0435\u0441\u043a\u0438\u0445 \u043e\u0433\u0440\u0430\u043d\u0438\u0447\u0435\u043d\u0438\u0439 \u043d\u0435 \u0440\u0430\u0441\u0441\u0447\u0438\u0442\u044b\u0432\u0430\u044e. \u041f\u043e\u0442\u0435\u043d\u0446\u0438\u0430\u043b \u043c\u0435\u0442\u0430\u043d\u0430 \u0432\u0441\u0435\u0439 \u043f\u0430\u0440\u0442\u0438\u0438 \u043d\u0435 \u044f\u0432\u043b\u044f\u0435\u0442\u0441\u044f \u0432\u044b\u0445\u043e\u0434\u043e\u043c \u043e\u0434\u043d\u043e\u0433\u043e \u0446\u0438\u043a\u043b\u0430; \u0432\u044b\u0445\u043e\u0434 \u0437\u0430 \u0446\u0438\u043a\u043b \u043d\u0435\u0438\u0437\u0432\u0435\u0441\u0442\u0435\u043d."
    if status == "EXCEEDS_NOMINAL":
        return (f"Партия объёмом {fmt(feed)} л превышает номинальный полный объём реактора {fmt(total)} л, поэтому загрузить её целиком одновременно невозможно. Номинальный объём не равен рабочему. Разделите сырьё на последовательные партии либо используйте реактор большего объёма; точное число партий нельзя определить без рабочего объёма, воды, инокулята и технологических ограничений. Потенциал метана всей партии не является выходом одного цикла; выход за цикл неизвестен.")
    if status == "INVALID_VESSEL_GEOMETRY":
        return "Указанный рабочий объём больше номинального объёма реактора. Геометрические данные противоречивы, поэтому вывод о загрузке и выходе за цикл невозможен."
    if status == "EXCEEDS_WORKING_VOLUME":
        return f"Заявленный объём жидкой загрузки превышает подтверждённый рабочий объём реактора {fmt(working)} л. Загружать всё одновременно нельзя; нужны последовательные партии или реактор большего объёма. Точное число партий неизвестно без всех объёмов жидких компонентов и технологических ограничений."
    if status == "WORKING_VOLUME_UNKNOWN":
        if isclose(feed, total, rel_tol=0.0, abs_tol=1e-9):
            return f"Партия {fmt(feed)} л равна номинальной полной вместимости реактора {fmt(total)} л, но рабочий объём не указан. При заполнении до номинала места нет для инокулята и газового пространства; не заполняйте реактор до краёв. Выход за цикл не подтверждён."
        return f"Партия {fmt(feed)} л меньше номинальных {fmt(total)} л; рабочий объём не указан, загрузка и выход за цикл не подтверждены. Не заполняйте реактор до краёв: учтите воду, инокулят, остаточную жидкость и газовое пространство."
    if status == "OCCUPANCY_INCOMPLETE":
        return f"Объём сырья меньше подтверждённого рабочего объёма {fmt(working)} л, но полный объём жидкой загрузки не задан. Вода, инокулят и остаточная жидкость тоже занимают рабочий объём, поэтому возможность загрузить всё одновременно пока не подтверждена."
    return f"Заявленные жидкие объёмы укладываются в рабочий объём {fmt(working)} л. Это только проверка объёмов, а не подтверждение безопасного режима или фактического выхода метана за цикл."
