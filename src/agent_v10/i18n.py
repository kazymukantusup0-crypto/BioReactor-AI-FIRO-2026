"""Short phrases in Russian, Kazakh and English used by tools and templates.

Usage:  t("assume_state", "ru", substrate="навоз КРС", state="жидкий")
"""
from __future__ import annotations

TEXT: dict[str, dict[str, str]] = {
    # --- assumptions -------------------------------------------------------
    "assume_state": {
        "ru": "принял, что {substrate} — {state}",
        "en": "assumed that {substrate} is {state}",
        "kk": "{substrate} — {state} деп алдым",
    },
    "assume_density": {
        "ru": "плотность {substrate} {value} кг/л ({label})",
        "en": "density of {substrate} {value} kg/L ({label})",
        "kk": "{substrate} тығыздығы {value} кг/л ({label})",
    },
    "assume_composition": {
        "ru": "органическое вещество и метановый потенциал {substrate} — по {label}",
        "en": "organic matter and methane potential of {substrate} — from {label}",
        "kk": "{substrate} органикалық заты мен метан әлеуеті — {label} бойынша",
    },
    "assume_startup": {
        "ru": "первый газ — через 1–2 дня, если загрузить навоз КРС или добавить перебродившую жижу как закваску; до "
              "устойчивого процесса — от нескольких дней до нескольких недель; первый газ плохой (больше 60 % CO2), первые "
              "два заполнения газгольдера стравить (GTZ/ISAT Biogas Digest, т. II)",
        "en": "first gas in 1–2 days with cattle dung or digested slurry as inoculum; a stable process takes several days to "
              "several weeks; the first gas is poor (more than 60% CO2), vent the first two gasholder fillings (GTZ/ISAT Biogas Digest II)",
        "kk": "алғашқы газ — сиыр көңі немесе ашыған қоспа ашытқы ретінде болса 1–2 күнде; тұрақты процеске дейін — бірнеше "
              "күннен бірнеше аптаға дейін; алғашқы газ сапасыз (CO2 60 %-дан көп) (GTZ/ISAT Biogas Digest, II т.)",
    },
    "assume_full_digestion": {
        "ru": "{low}–{high} дней — время полного сбраживания партии, а не время до первого газа",
        "en": "{low}–{high} days is the time to digest the whole batch, not the time until the first gas",
        "kk": "{low}–{high} күн — партияның толық ашу уақыты, алғашқы газға дейінгі уақыт емес",
    },
    "assume_compare_volume": {
        "ru": "сравнение при одинаковом объёме {volume} л (рабочий объём демо-реактора)",
        "en": "compared at the same volume of {volume} L (working volume of the demo reactor)",
        "kk": "бірдей {volume} л көлемде салыстырылды (демо-реактордың жұмыс көлемі)",
    },
    "assume_handbook": {
        "ru": "{substrate}: измеренные пробы в базе сильно разбавлены водой (TS {ts} %, {m_low}–{m_high} л CH4/кг); для типичной "
              "жижи взят справочный выход FNR 2007: {biogas} м³ биогаза на тонну = {low}–{high} л CH4/кг",
        "en": "{substrate}: the measured samples in the base are strongly diluted (TS {ts} %, {m_low}–{m_high} L CH4/kg); for "
              "typical slurry the FNR 2007 handbook yield is used: {biogas} m³ biogas per tonne = {low}–{high} L CH4/kg",
        "kk": "{substrate}: базадағы өлшенген сынамалар қатты суйылтылған (TS {ts} %, {m_low}–{m_high} л CH4/кг); әдеттегі "
              "сұйық көң үшін FNR 2007 анықтамалық шығымы алынды: тоннаға {biogas} м³ биогаз = {low}–{high} л CH4/кг",
    },
    "assume_bmp": {
        "ru": "TS и VS — ваши данные, метановый потенциал {substrate} — по {label}",
        "en": "TS and VS are your data, methane potential of {substrate} — from {label}",
        "kk": "TS және VS — сіздің деректеріңіз, {substrate} метан әлеуеті — {label} бойынша",
    },
    "assume_regime_share": {
        "ru": "в реакторе за {days_low}–{days_high} дней ({regime}) выходит {share_low}–{share_high}% лабораторного потенциала (допущение модели)",
        "en": "in {days_low}–{days_high} days ({regime}) the reactor reaches {share_low}–{share_high}% of the laboratory potential (model assumption)",
        "kk": "{days_low}–{days_high} күнде ({regime}) реактор зертханалық әлеуеттің {share_low}–{share_high}% береді (модель жорамалы)",
    },
    "assume_ch4_share": {
        "ru": "доля метана в биогазе {low}–{high}% (литература)",
        "en": "methane share in biogas {low}–{high}% (literature)",
        "kk": "биогаздағы метан үлесі {low}–{high}% (әдебиет)",
    },
    "assume_default_batch": {
        "ru": "сырьё не указано — посчитал для демо-реактора: {litres} л жидкого навоза КРС",
        "en": "feedstock not given — calculated for the demo reactor: {litres} L of cattle slurry",
        "kk": "шикізат көрсетілмеген — демо-реактор үшін есептедім: {litres} л сұйық сиыр көңі",
    },
    "off_topic": {
        "ru": "Я помогаю только с биогазовой установкой: сырьё, выход газа, подогрев, температурный режим и выгода. "
              "Спросите, например: «Сколько газа даст 150 л навоза КРС?»",
        "en": "I only help with the biogas plant: feedstock, gas yield, heating, temperature regime and money. "
              "Try for example: \"How much gas from 150 L of cattle slurry?\"",
        "kk": "Мен тек биогаз қондырғысы бойынша көмектесемін: шикізат, газ шығымы, қыздыру, температура режимі және пайда. "
              "Мысалы, сұраңыз: «150 л сиыр көңінен қанша газ шығады?»",
    },
    "assume_bag": {
        "ru": "1 мешок ≈ 50 л (мешки бывают разные — скажите объём или вес, пересчитаю)",
        "en": "1 sack ≈ 50 L (sacks differ — tell me the volume or weight and I will recalculate)",
        "kk": "1 қап ≈ 50 л (қаптар әртүрлі — көлемін не салмағын айтыңыз, қайта есептеймін)",
    },
    "assume_analog": {
        "ru": "нет проверенных данных по «{name}» — посчитано по аналогии с «{analog}» ({why}); это грубая оценка",
        "en": "no reviewed data for \"{name}\" — calculated by analogy with \"{analog}\" ({why}); a rough estimate",
        "kk": "«{name}» бойынша тексерілген дерек жоқ — «{analog}» ұқсастығы бойынша есептелді ({why}); бұл шамамен баға",
    },
    "ask_composition": {
        "ru": "Если знаете сухое вещество (TS, %) и органическое вещество (VS, % от TS) для «{name}» — скажите, посчитаю точнее.",
        "en": "If you know the dry matter (TS, %) and organic matter (VS, % of TS) of \"{name}\", tell me and I will recalculate.",
        "kk": "«{name}» үшін құрғақ зат (TS, %) және органикалық зат (VS, TS-тен %) белгілі болса — айтыңыз, нақтырақ есептеймін.",
    },
    "no_data": {
        "ru": "По сырью «{name}» у меня нет проверенных данных и нет близкого аналога, поэтому выход газа не считаю, чтобы не выдумывать.",
        "en": "I have no reviewed data and no close analogue for \"{name}\", so I do not estimate the gas rather than invent it.",
        "kk": "«{name}» шикізаты бойынша тексерілген дерек те, жақын ұқсасы да жоқ, сондықтан ойдан шығармау үшін газды есептемеймін.",
    },
    "assume_bucket": {
        "ru": "1 ведро = 10 л",
        "en": "1 bucket = 10 L",
        "kk": "1 шелек = 10 л",
    },
    "assume_reactor_volume": {
        "ru": "реактор не указан — взял демо-реактор: бочка {volume} л, рабочий объём {working} л",
        "en": "reactor not given — used the demo reactor: barrel {volume} L, working volume {working} L",
        "kk": "реактор көрсетілмеген — демо-реактор алынды: бөшке {volume} л, жұмыс көлемі {working} л",
    },
    "assume_manure_per_animal": {
        "ru": "{name}: {low}–{high} кг навоза с мочой в сутки ({basis}; NRCS AWMFH, гл. 4) — справочное допущение",
        "en": "{name}: {low}–{high} kg of manure with urine per day (NRCS AWMFH, ch. 4) — handbook assumption",
        "kk": "{name}: тәулігіне {low}–{high} кг көң (NRCS AWMFH, 4-тарау) — анықтамалық жорамал",
    },
    "assume_continuous": {
        "ru": "непрерывный режим: каждый день загружают суточный навоз; за сутки выходит столько газа, сколько одна "
              "суточная загрузка даёт за весь срок сбраживания; 1 кг сырого навоза ≈ 1 л",
        "en": "continuous mode: the daily manure is loaded every day; per day the reactor gives what one daily load "
              "gives over the whole digestion time; 1 kg of wet manure ≈ 1 L",
        "kk": "үздіксіз режим: күн сайын тәуліктік көң жүктеледі; тәулігіне бір тәуліктік жүктеменің бүкіл ашыту "
              "мерзіміндегі газы шығады; 1 кг дымқыл көң ≈ 1 л",
    },
    "assume_batch_per_day": {
        "ru": "газ партии распределён на срок сбраживания {days} дней (в среднем за сутки)",
        "en": "the batch gas is spread over the digestion time of {days} days (average per day)",
        "kk": "партия газы {days} күндік ашыту мерзіміне бөлінді (тәулігіне орташа)",
    },
    "assume_stove": {
        "ru": "одна бытовая конфорка расходует {low}–{high} м³ биогаза в час (GTZ/ISAT Biogas Digest, т. II)",
        "en": "one household burner uses {low}–{high} m³ of biogas per hour (GTZ/ISAT Biogas Digest, vol. II)",
        "kk": "бір тұрмыстық оттық сағатына {low}–{high} м³ биогаз жұмсайды (GTZ/ISAT Biogas Digest, II т.)",
    },
    "assume_batch_too_big": {
        "ru": "партия {volume} л больше рабочего объёма реактора {working} л (реактор {reactor} л) — расчёт сделан для всей партии",
        "en": "the batch of {volume} L is larger than the working volume {working} L (reactor {reactor} L) — calculated for the whole batch",
        "kk": "{volume} л партия реактордың {working} л жұмыс көлемінен көп (реактор {reactor} л) — бүкіл партия үшін есептелді",
    },
    "assume_insulation": {
        "ru": "утепление «{level}» (не было указано)",
        "en": "insulation \"{level}\" (not specified)",
        "kk": "жылыту деңгейі «{level}» (көрсетілмеген)",
    },
    "assume_ambient": {
        "ru": "температура снаружи {value} °C (не была указана)",
        "en": "outside temperature {value} °C (not specified)",
        "kk": "сырттағы температура {value} °C (көрсетілмеген)",
    },
    "assume_feed_temperature": {
        "ru": "сырьё загружают при {value} °C",
        "en": "feed is loaded at {value} °C",
        "kk": "шикізат {value} °C кезінде жүктеледі",
    },
    "assume_geometry": {
        "ru": "реактор — цилиндр высотой с диаметр: Ø {diameter} м, поверхность {area} м²",
        "en": "reactor is a cylinder with height = diameter: Ø {diameter} m, surface {area} m²",
        "kk": "реактор — биіктігі диаметрге тең цилиндр: Ø {diameter} м, беті {area} м²",
    },
    "assume_u_value": {
        "ru": "теплопотери через стенку U = {low}–{high} Вт/(м²·К): пластиковая стенка 3–5 мм + утепление «{level}», ветер от штиля до слабого",
        "en": "wall heat loss U = {low}–{high} W/(m²·K): plastic wall 3–5 mm + insulation \"{level}\", calm to light wind",
        "kk": "қабырға арқылы жылу шығыны U = {low}–{high} Вт/(м²·К): пластик қабырға 3–5 мм + «{level}» жылыту, тымық пен әлсіз жел",
    },
    "assume_mixing": {
        "ru": "перемешивание {power} Вт по {hours} ч в сутки",
        "en": "mixing {power} W for {hours} h per day",
        "kk": "араластыру {power} Вт, тәулігіне {hours} сағ",
    },
    "assume_days": {
        "ru": "срок сбраживания {days} дней",
        "en": "digestion time {days} days",
        "kk": "ашыту мерзімі {days} күн",
    },
    "assume_boiler": {
        "ru": "газ сжигают в котле с КПД 85–90%",
        "en": "gas is burned in a boiler with 85–90% efficiency",
        "kk": "газ ПӘК 85–90% қазандықта жағылады",
    },
    "assume_generator": {
        "ru": "генератор на биогазе: КПД по электричеству 20–30%; когенерация: 25% электричество + 45% тепло",
        "en": "biogas generator: 20–30% electrical efficiency; CHP: 25% electricity + 45% heat",
        "kk": "биогаз генераторы: электр ПӘК 20–30%; когенерация: 25% электр + 45% жылу",
    },
    "price_used": {
        "ru": "цена {what}: {price} ₸ ({date}, {kind})",
        "en": "{what} price: {price} KZT ({date}, {kind})",
        "kk": "{what} бағасы: {price} ₸ ({date}, {kind})",
    },
    "word_gas": {"ru": "газа", "en": "gas", "kk": "газ"},
    "word_electricity": {"ru": "электроэнергии", "en": "electricity", "kk": "электр"},
    "price_missing": {
        "ru": "сохранённых цен нет — экономия в тенге не посчитана",
        "en": "no saved prices — savings in tenge were not calculated",
        "kk": "сақталған бағалар жоқ — теңгедегі үнем есептелмеді",
    },
    # --- labels ------------------------------------------------------------
    "label_measured": {"ru": "ваши данные", "en": "your data", "kk": "сіздің деректеріңіз"},
    "label_literature": {"ru": "литературе", "en": "literature", "kk": "әдебиет"},
    "label_assumption": {"ru": "справочным допущениям", "en": "handbook assumptions", "kk": "анықтамалық жорамалдар"},
    "badge_measured": {"ru": "измерено", "en": "measured", "kk": "өлшенген"},
    "badge_literature": {"ru": "оценка по литературе", "en": "literature estimate", "kk": "әдебиет бойынша бағалау"},
    "badge_assumption": {"ru": "допущение", "en": "assumption", "kk": "жорамал"},
    "insulation_none": {"ru": "без утепления", "en": "no insulation", "kk": "жылытусыз"},
    "insulation_basic": {"ru": "базовое (3–5 см)", "en": "basic (3–5 cm)", "kk": "негізгі (3–5 см)"},
    "insulation_good": {"ru": "хорошее (10–15 см)", "en": "good (10–15 cm)", "kk": "жақсы (10–15 см)"},
    "insulation_eps50": {"ru": "пенополистирол 50 мм", "en": "EPS foam 50 mm", "kk": "пенополистирол 50 мм"},
    # --- one clarifying question --------------------------------------------
    "ask_state": {
        "ru": "Навоз жидкий или твёрдый/с подстилкой? Если другой — скажите, пересчитаю.",
        "en": "Is the manure liquid or solid/with bedding? If different, tell me and I will recalculate.",
        "kk": "Көң сұйық па, әлде қатты/төсенішті ме? Басқаша болса, айтыңыз — қайта есептеймін.",
    },
    "ask_mass": {
        "ru": "Если знаете точную массу или плотность партии — скажите, пересчитаю точнее.",
        "en": "If you know the exact mass or density of the batch, tell me and I will refine it.",
        "kk": "Партияның нақты массасын немесе тығыздығын білсеңіз, айтыңыз — дәлірек есептеймін.",
    },
    "ask_reactor": {
        "ru": "Какой объём у реактора и утеплён ли он? Тогда посчитаю затраты на подогрев точнее.",
        "en": "What is the reactor volume and is it insulated? Then I can refine the heating cost.",
        "kk": "Реактор көлемі қандай және ол жылытылған ба? Сонда қыздыру шығынын дәлірек есептеймін.",
    },
    "ask_ambient": {
        "ru": "Какая температура на улице? От неё сильно зависят затраты на подогрев.",
        "en": "What is the outside temperature? The heating cost depends strongly on it.",
        "kk": "Сыртта температура қандай? Қыздыру шығыны соған қатты байланысты.",
    },
    "ask_substrate": {
        "ru": "Какое сырьё и сколько его (литры или кг)? Например: «200 л жидкого навоза КРС».",
        "en": "What feedstock and how much (litres or kg)? For example: \"200 L of cattle slurry\".",
        "kk": "Қандай шикізат және қанша (литр не кг)? Мысалы: «200 л сұйық сиыр көңі».",
    },
    "ask_animals": {
        "ru": "Сколько у вас животных и каких? Например: «5 коров» или «20 кур».",
        "en": "How many animals do you have and which? For example: \"5 cows\" or \"20 chickens\".",
        "kk": "Қанша және қандай малыңыз бар? Мысалы: «5 сиыр» немесе «20 тауық».",
    },
    "ask_amount": {
        "ru": "Сколько у вас {substrate} — в литрах, вёдрах или килограммах?",
        "en": "How much {substrate} do you have — in litres, buckets or kilograms?",
        "kk": "{substrate} қанша — литрмен, шелекпен немесе килограммен?",
    },
}


def t(key: str, language: str, **values) -> str:
    """Return a phrase in the requested language (Russian if unknown)."""
    row = TEXT[key]
    template = row.get(language) or row["ru"]
    return template.format(**values)


def plural_ru(n: int, forms: tuple[str, str, str]) -> str:
    """Russian plural by number: 1 загрузка, 2 загрузки, 5 загрузок, 11 загрузок, 21 загрузка."""
    tens, ones = abs(n) % 100, abs(n) % 10
    if 11 <= tens <= 14:
        return forms[2]
    if ones == 1:
        return forms[0]
    if 2 <= ones <= 4:
        return forms[1]
    return forms[2]


def badge(label: str, language: str) -> str:
    """'literature' -> 'оценка по литературе'."""
    return t(f"badge_{label}", language)
