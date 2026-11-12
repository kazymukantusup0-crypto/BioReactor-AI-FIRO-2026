# Actual FastAPI Chat + Qwen3 4B: recorded answers, 2026-11-12

These are new local Ollama responses through the real async Chat jobs endpoint using FastAPI TestClient. No fake inference. Original JSON/SQLite files are retained. Independent judgement is in the parent report; COMPLETED is a transport status, not scientific acceptance.

## pig

Trace: `reports\qwen4b_manual_qa\limited_chat_1794471880875053300.json` SHA256 `af1895d8f064fe67c3930eb83e7412bec38515638a254b603abdfe1220d7fc43`

Question: Привет! У меня 78 литров жидкого свиного навоза и реактор объёмом 200 литров. Сколько получится метана, выгодно ли его перерабатывать и какую температуру выставить?

### Model calls

| Phase | Actual status | Input tokens | Output tokens | Completion reason |
|---|---|---:|---:|---|
| compact_nlu | ok | 151 | 16 | stop |
| tool_selection | ok | 1243 | 89 | stop |
| tool_selection | ok | 2932 | 73 | stop |
| scientific_synthesis | ok | 586 | 73 | stop |

### Tool calls and origin

```json
[
  {
    "tool": "search_scientific_sources",
    "status": "ok",
    "input_origin": "validated_scientific_state",
    "query": "methane yield from swine manure in anaerobic digestion"
  },
  {
    "tool": "estimate_methane_yield",
    "status": "ok",
    "input_origin": "validated_scientific_state",
    "query": null
  },
  {
    "tool": "assess_process_evidence",
    "status": "ok",
    "input_origin": "controller_required_evidence"
  },
  {
    "tool": "evaluate_partial_economics",
    "status": "ok",
    "input_origin": "controller_required_evidence"
  }
]
```

### Raw final model call (not the Python result blocks)

```json
{
  "conclusion": "Оценка метана, температуры и экономики неоднозначна.",
  "explanation": "Метановый потенциал не определён, температура изучена, но не оптимизирована, экономика не проверена."
}
```

### Verification and telemetry

```json
{
  "case": "pig",
  "trace": "reports\\qwen4b_manual_qa\\limited_chat_1794471880875053300.json",
  "status": "COMPLETED",
  "started": "2026-11-12T13:24:40.875064+05:00",
  "finished": "2026-11-12T13:24:50.897763+05:00",
  "first_job_seconds": 8.857,
  "calls": 4,
  "admission_free_ram_mib": 8109.8,
  "min_free_ram_mib": 6753.1,
  "max_commit_mib": 17337.1,
  "min_commit_headroom_mib": 18295.4,
  "max_vram_used_mib": 3873,
  "max_gpu_c": 66.0,
  "unload": {
    "status": "UNLOADED",
    "elapsed_seconds": 0.197
  },
  "after_models": [],
  "after_free_ram_mib": 8069.4,
  "after_vram_used_mib": 606,
  "final_author": "qwen_verified",
  "arithmetic": {
    "status": "ok",
    "checked": true,
    "all_checks_passed": true
  },
  "numeric_model_draft": {
    "status": "not_applicable",
    "checked": false,
    "claims": [],
    "scope": "Last model draft: typed numeric grounding and supported unit conversion, not biological verification."
  },
  "scientific": {
    "status": "passed",
    "checked": true,
    "all_checks_passed": true
  },
  "synthesis_rejections": [],
  "stop_reason": null
}
```

### Delivered answer (verbatim)

Партия 78 л меньше номинальных 200 л; рабочий объём не указан, загрузка и выход за цикл не подтверждены. Не заполняйте реактор до краёв: учтите воду, инокулят, остаточную жидкость и газовое пространство.

Литературный ориентир метана рассчитан; это не измеренная выработка установки. Экономическую выгоду определяют полезное использование газа и полные расходы; прибыль пока не подтверждена.

Оценка метана, температуры и экономики неоднозначна.

Свиной навоз, при 25 °C в источнике: 416 л CH₄ для всей партии.
Вся партия относительно номинальной ёмкости уже превышает умеренную объёмную загрузку этого опыта. Литературный потенциал относится ко всему сырью, не к одной такой загрузке; рабочий объём и разделение на партии требуют проверки.
Органическое сухое вещество источника 16.31 г/л; по указанному объёму рассчитано 1.2722 кг. Плотность и масса влажного навоза не подставлялись: используется концентрация на литр.
Лабораторный метановый ориентир 327 мл CH₄/г органического сухого вещества; расчёт объёма из его массы и коэффициента выполнил Python.
Свиной навоз, при 30 °C в источнике: 494.88 л CH₄ для всей партии.
Лабораторный метановый ориентир 389 мл CH₄/г органического сухого вещества; расчёт объёма из его массы и коэффициента выполнил Python.
Свиной навоз, при 35 °C в источнике: 512.69 л CH₄ для всей партии.
Лабораторный метановый ориентир 403 мл CH₄/г органического сухого вещества; расчёт объёма из его массы и коэффициента выполнил Python.
Срок выработки не задан; число дней не назначаю.
Это отдельные литературные варианты, не доверительный интервал и не гарантия. Состав и подготовка партии должны быть сопоставимы с исследованием. Метан не равен всему биогазу.

Отправной точкой для обсуждения может быть мезофильный режим около 35 °C: он представлен в исследованиях этого сырья. Это не проверенная уставка оборудования; нужны адаптированный инокулят и стабильный контроль.
Мезофильный вариант требует меньше подогрева, чем более горячий термофильный при прочих равных. Повышение температуры может менять аммиачный риск и устойчивость; оно не гарантирует улучшение процесса.
Подогрев для варианта 35 °C: полный расход не определён.
Подогрев для варианта 55 °C: полный расход не определён.
Python считает начальный нагрев и теплопотери отдельно. Нужны фактическая нагреваемая загрузка с водой и инокулятом, начальная и наружная температура, утепление, длительность и потребление мешалки. Номинальный объём не считается массой. Команды нагревателю не отправляются.

Рыночные записи проверены; без применимого газового ориентира денежный результат пока не установлен.
В небольшой установке теплопотери и работа мешалки могут поглотить полезный выход. Переработка может иметь смысл при спросе на тепло и достаточно малых полных расходах. Прибыль и окупаемость без этих расходов не подтверждены; неизвестные затраты не равны нулю.
Чувствительность: при неизменных условиях валовая ценность пропорциональна полезной энергии и применимому тарифу. Для безубыточности все расходы должны быть ниже полезной валовой ценности. Тариф природного газа не служит ценой продажи сырого биогаза.

Номинальная вместимость не равна рабочему объёму. До загрузки проверьте объём сырья вместе с водой, инокулятом и остатком, газовое пространство и конструкцию установки. Оценка всей партии не является выходом одного цикла; литературные параметры не становятся вашими измерениями.

Новая партия зафиксирована: свиной навоз; объём сырья 78 л; ёмкость сосуда 200 л.

В каком регионе находится установка?

### Delivered source links

- [Koch et al. — Power and Limitations of Biochemical Methane Potential (BMP) Tests](https://www.frontiersin.org/journals/energy-research/articles/10.3389/fenrg.2020.00063/full)
- [Validation and Recommendation of Methods to Measure Biogas Production Potential of Animal Manure](https://doi.org/10.5713/ajas.2012.12623)
- [Techno-Economic Assessment of Anaerobic Digestion Technology for Small- and Medium-Sized Animal Husbandry Enterprises](https://doi.org/10.3390/app14114957)
- [The effects of digestion temperature and temperature shock on the biogas yields from the mesophilic anaerobic digestion of swine manure](https://doi.org/10.1016/j.biortech.2006.11.063)
- [Treatment of Cattle Manure by Anaerobic Co-Digestion with Food Waste and Pig Manure: Methane Yield and Synergistic Effect](https://www.mdpi.com/1660-4601/17/13/4737)
- [Microorganism-regulated mechanisms of temperature effects on the performance of anaerobic digestion](https://link.springer.com/article/10.1186/s12934-016-0491-x)
- [DOE Fundamentals Handbook, Thermodynamics, Heat Transfer and Fluid Flow, Vol. 1](https://www.energy.gov/documents/doe-hdbk-1012-92vol1)
- [Building Science: Introduction to Heat Flow](https://basc.pnnl.gov/information/building-science-introduction-heat-flow)
- [Basisdaten Bioenergie Deutschland 2024](https://www.fnr.de/fileadmin/Projekte/2023/Mediathek/Broschuere_Basisdaten_Bioenergie_2023_web.pdf)
- [Handreichung Biogasgewinnung und -nutzung](https://www.big-east.eu/downloads/FNR_HR_Biogas.pdf)
- [Faustzahlen Biogas](https://biogas.fnr.de/daten-und-fakten/faustzahlen)

## cow

Trace: `reports\qwen4b_manual_qa\limited_chat_1794471892152417300.json` SHA256 `a11e1ed95289bde2437b49b8532a87dd8f71052f21d2f5572e6427b392109f70`

Question: Есть 41 л жидкого коровьего навоза, реактор 260 л. Какой ориентир метана за 30 дней, какую температуру выбрать и выгодна ли переработка?

### Model calls

| Phase | Actual status | Input tokens | Output tokens | Completion reason |
|---|---|---:|---:|---|
| compact_nlu | ok | 146 | 17 | stop |
| tool_selection | ok | 1276 | 78 | stop |
| tool_selection | ok | 4014 | 91 | stop |
| scientific_synthesis | ok | 580 | 86 | stop |

### Tool calls and origin

```json
[
  {
    "tool": "estimate_methane_yield",
    "status": "ok",
    "input_origin": "validated_scientific_state",
    "query": null
  },
  {
    "tool": "assess_process_evidence",
    "status": "ok",
    "input_origin": "validated_scientific_state",
    "query": null
  },
  {
    "tool": "search_scientific_sources",
    "status": "ok",
    "input_origin": "controller_required_evidence"
  },
  {
    "tool": "evaluate_partial_economics",
    "status": "ok",
    "input_origin": "controller_required_evidence"
  }
]
```

### Raw final model call (not the Python result blocks)

```json
{
  "conclusion": "Температурный режим изучен, но не оптимум. Экономический смысл неясен из-за неизвестных затрат.",
  "explanation": "Мезофильный вариант рассмотрен, но оптимум не проверен. Прибыль не подтверждена, затраты неизвестны."
}
```

### Verification and telemetry

```json
{
  "case": "cow",
  "trace": "reports\\qwen4b_manual_qa\\limited_chat_1794471892152417300.json",
  "status": "COMPLETED",
  "started": "2026-11-12T13:24:52.152429+05:00",
  "finished": "2026-11-12T13:25:03.036879+05:00",
  "first_job_seconds": 9.811,
  "calls": 4,
  "admission_free_ram_mib": 8094.0,
  "min_free_ram_mib": 6934.1,
  "max_commit_mib": 17164.2,
  "min_commit_headroom_mib": 18468.3,
  "max_vram_used_mib": 3873,
  "max_gpu_c": 70.0,
  "unload": {
    "status": "UNLOADED",
    "elapsed_seconds": 0.186
  },
  "after_models": [],
  "after_free_ram_mib": 8083.1,
  "after_vram_used_mib": 605,
  "final_author": "qwen_verified",
  "arithmetic": {
    "status": "ok",
    "checked": true,
    "all_checks_passed": true
  },
  "numeric_model_draft": {
    "status": "not_applicable",
    "checked": false,
    "claims": [],
    "scope": "Last model draft: typed numeric grounding and supported unit conversion, not biological verification."
  },
  "scientific": {
    "status": "passed",
    "checked": true,
    "all_checks_passed": true
  },
  "synthesis_rejections": [],
  "stop_reason": null
}
```

### Delivered answer (verbatim)

Партия 41 л меньше номинальных 260 л; рабочий объём не указан, загрузка и выход за цикл не подтверждены. Не заполняйте реактор до краёв: учтите воду, инокулят, остаточную жидкость и газовое пространство.

Литературный ориентир метана рассчитан; это не измеренная выработка установки. Экономическую выгоду определяют полезное использование газа и полные расходы; прибыль пока не подтверждена.

Температурный режим изучен, но не оптимум. Экономический смысл неясен из-за неизвестных затрат.

Навоз КРС, при 37 °C в источнике: 843.95–1187.8 л CH₄ для всей партии.
Расчётная масса органического сухого вещества 4.2198–4.7514 кг; влажная масса 41.533 кг.
Лабораторный метановый ориентир 200–250 мл CH₄/г органического сухого вещества; расчёт объёма из его массы и коэффициента выполнил Python.
Выход за 30 дней: не установлен: применимая кинетика отсутствует. Потенциал не подменяет выход за срок.
Это отдельные литературные варианты, не доверительный интервал и не гарантия. Состав и подготовка партии должны быть сопоставимы с исследованием. Метан не равен всему биогазу.

Отправной точкой для обсуждения может быть мезофильный режим около 37 °C: он представлен в исследованиях этого сырья. Это не проверенная уставка оборудования; нужны адаптированный инокулят и стабильный контроль.
Мезофильный вариант требует меньше подогрева, чем более горячий термофильный при прочих равных. Повышение температуры может менять аммиачный риск и устойчивость; оно не гарантирует улучшение процесса.
Подогрев для варианта 37 °C: полный расход не определён.
Python считает начальный нагрев и теплопотери отдельно. Нужны фактическая нагреваемая загрузка с водой и инокулятом, начальная и наружная температура, утепление, длительность и потребление мешалки. Номинальный объём не считается массой. Команды нагревателю не отправляются.

Навоз КРС (опыт при 37 °C): энергия метана 8.4142–11.843 кВт·ч; полезное тепло 4.0388–7.5794 кВт·ч ИЛИ электричество 1.2621–2.3686 кВт·ч. Эти альтернативы не складываются.
Сбор газа и КПД приняты как условные сценарии оборудования, не измерены. Теплота сгорания и база объёма газа должны быть совместимы.
Принятые допущения: сбор газа 60–80%, КПД получения тепла 80%, электричества 25%. Это примеры оборудования, не универсальные свойства навоза.
Применимый тариф в рыночном хранилище не найден. Цену не подставляю: экономия = полезная энергия × ваш применимый тариф.
В небольшой установке теплопотери и работа мешалки могут поглотить полезный выход. Переработка может иметь смысл при спросе на тепло и достаточно малых полных расходах. Прибыль и окупаемость без этих расходов не подтверждены; неизвестные затраты не равны нулю.
Чувствительность: при неизменных условиях валовая ценность пропорциональна полезной энергии и применимому тарифу. Для безубыточности все расходы должны быть ниже полезной валовой ценности. Тариф природного газа не служит ценой продажи сырого биогаза.

Номинальная вместимость не равна рабочему объёму. До загрузки проверьте объём сырья вместе с водой, инокулятом и остатком, газовое пространство и конструкцию установки. Оценка всей партии не является выходом одного цикла; литературные параметры не становятся вашими измерениями.

В каком регионе находится установка?

### Delivered source links

- [Moderate thermal, alkaline and thermal-alkaline pretreatment of cattle manure: effects on methane production and economic feasibility](https://link.springer.com/article/10.1007/s43153-025-00592-x)
- [Techno-Economic Assessment of Anaerobic Digestion Technology for Small- and Medium-Sized Animal Husbandry Enterprises](https://doi.org/10.3390/app14114957)
- [Treatment of Cattle Manure by Anaerobic Co-Digestion with Food Waste and Pig Manure: Methane Yield and Synergistic Effect](https://www.mdpi.com/1660-4601/17/13/4737)
- [DOE Fundamentals Handbook, Thermodynamics, Heat Transfer and Fluid Flow, Vol. 1](https://www.energy.gov/documents/doe-hdbk-1012-92vol1)
- [Building Science: Introduction to Heat Flow](https://basc.pnnl.gov/information/building-science-introduction-heat-flow)
- [FAO / Marchaim — Biogas processes for sustainable development: Environmental factors](https://www.fao.org/4/t0541e/T0541E06.htm)
- [FAO / Marchaim — Anaerobic processes, plant design and control](https://www.fao.org/4/t0541e/T0541E09.htm)
- [Hafner et al. — Reliable biochemical methane potential testing (2026), original repository and dictionary](https://github.com/AU-BCE-EE/Hafner-2026-IL-BMP)
- [Koch et al. — Power and Limitations of Biochemical Methane Potential (BMP) Tests](https://www.frontiersin.org/journals/energy-research/articles/10.3389/fenrg.2020.00063/full)
- [US EPA AgSTAR — Anaerobic Digester/Biogas System Operator Guidebook](https://www.epa.gov/sites/default/files/2020-11/documents/agstar-operator-guidebook.pdf)
- [Basisdaten Bioenergie Deutschland 2024](https://www.fnr.de/fileadmin/Projekte/2023/Mediathek/Broschuere_Basisdaten_Bioenergie_2023_web.pdf)
- [Handreichung Biogasgewinnung und -nutzung](https://www.big-east.eu/downloads/FNR_HR_Biogas.pdf)
- [Faustzahlen Biogas](https://biogas.fnr.de/daten-und-fakten/faustzahlen)

## food

Trace: `reports\qwen4b_manual_qa\limited_chat_1794471904262217500.json` SHA256 `6ce1874804e246c88929e91b6dc5e08cc9291692aff2977be06bfa8ce9016537`

Question: У меня 3,2 кг пищевых отходов, реактор 85 л. Сколько метана можно получить, какую температуру выбрать и выгодно ли использовать газ для обогрева?

### Model calls

| Phase | Actual status | Input tokens | Output tokens | Completion reason |
|---|---|---:|---:|---|
| compact_nlu | ok | 141 | 19 | stop |
| tool_selection | ok | 1174 | 77 | stop |
| tool_selection | ok | 1840 | 84 | stop |
| scientific_synthesis | ok | 587 | 114 | stop |

### Tool calls and origin

```json
[
  {
    "tool": "assess_substrate_potential",
    "status": "ok",
    "input_origin": "validated_scientific_state",
    "query": null
  },
  {
    "tool": "assess_process_evidence",
    "status": "ok",
    "input_origin": "validated_scientific_state",
    "query": null
  },
  {
    "tool": "search_scientific_sources",
    "status": "ok",
    "input_origin": "controller_required_evidence"
  },
  {
    "tool": "evaluate_partial_economics",
    "status": "ok",
    "input_origin": "controller_required_evidence"
  }
]
```

### Raw final model call (not the Python result blocks)

```json
{
  "conclusion": "Метановый потенциал оценен, но не подтвержден. Температура мезофильная, но оптимум не доказан. Экономика неясна из-за неизвестных затрат.",
  "explanation": "Метан не выработан установкой, температура изучена, но не оптимизирована. Затраты не определены, поэтому экономика неясна."
}
```

### Verification and telemetry

```json
{
  "case": "food",
  "trace": "reports\\qwen4b_manual_qa\\limited_chat_1794471904262217500.json",
  "status": "COMPLETED",
  "started": "2026-11-12T13:25:04.262229+05:00",
  "finished": "2026-11-12T13:25:13.543733+05:00",
  "first_job_seconds": 8.185,
  "calls": 4,
  "admission_free_ram_mib": 8098.5,
  "min_free_ram_mib": 6922.7,
  "max_commit_mib": 17175.5,
  "min_commit_headroom_mib": 18457.0,
  "max_vram_used_mib": 3873,
  "max_gpu_c": 72.0,
  "unload": {
    "status": "UNLOADED",
    "elapsed_seconds": 0.198
  },
  "after_models": [],
  "after_free_ram_mib": 8084.9,
  "after_vram_used_mib": 606,
  "final_author": "qwen_verified",
  "arithmetic": {
    "status": "ok",
    "checked": true,
    "all_checks_passed": true
  },
  "numeric_model_draft": {
    "status": "not_applicable",
    "checked": false,
    "claims": [],
    "scope": "Last model draft: typed numeric grounding and supported unit conversion, not biological verification."
  },
  "scientific": {
    "status": "passed",
    "checked": true,
    "all_checks_passed": true
  },
  "synthesis_rejections": [],
  "stop_reason": null
}
```

### Delivered answer (verbatim)

Литературный ориентир метана рассчитан; это не измеренная выработка установки. Экономическую выгоду определяют полезное использование газа и полные расходы; прибыль пока не подтверждена.

Метановый потенциал оценен, но не подтвержден. Температура мезофильная, но оптимум не доказан. Экономика неясна из-за неизвестных затрат.

Пищевые отходы, при 35 °C в источнике: 203.61 л CH₄ для всей партии.
Расчётная масса органического сухого вещества 0.38592 кг; влажная масса 3.2 кг.
Лабораторный метановый ориентир 527.5 мл CH₄/г органического сухого вещества; расчёт объёма из его массы и коэффициента выполнил Python.
Срок выработки не задан; число дней не назначаю.
Это отдельные литературные варианты, не доверительный интервал и не гарантия. Состав и подготовка партии должны быть сопоставимы с исследованием. Метан не равен всему биогазу.

Отправной точкой для обсуждения может быть мезофильный режим около 35 °C: он представлен в исследованиях этого сырья. Это не проверенная уставка оборудования; нужны адаптированный инокулят и стабильный контроль.
Мезофильный вариант требует меньше подогрева, чем более горячий термофильный при прочих равных. Повышение температуры может менять аммиачный риск и устойчивость; оно не гарантирует улучшение процесса.
Подогрев для варианта 35 °C: полный расход не определён.
Python считает начальный нагрев и теплопотери отдельно. Нужны фактическая нагреваемая загрузка с водой и инокулятом, начальная и наружная температура, утепление, длительность и потребление мешалки. Номинальный объём не считается массой. Команды нагревателю не отправляются.

Пищевые отходы: энергия метана 2.03 кВт·ч; полезное тепло 0.9744–1.2992 кВт·ч ИЛИ электричество 0.3045–0.406 кВт·ч. Эти альтернативы не складываются.
Сбор газа и КПД приняты как условные сценарии оборудования, не измерены. Теплота сгорания и база объёма газа должны быть совместимы.
Принятые допущения: сбор газа 60–80%, КПД получения тепла 80%, электричества 25%. Это примеры оборудования, не универсальные свойства навоза.
Применимый тариф в рыночном хранилище не найден. Цену не подставляю: экономия = полезная энергия × ваш применимый тариф.
В небольшой установке теплопотери и работа мешалки могут поглотить полезный выход. Переработка может иметь смысл при спросе на тепло и достаточно малых полных расходах. Прибыль и окупаемость без этих расходов не подтверждены; неизвестные затраты не равны нулю.
Чувствительность: при неизменных условиях валовая ценность пропорциональна полезной энергии и применимому тарифу. Для безубыточности все расходы должны быть ниже полезной валовой ценности. Тариф природного газа не служит ценой продажи сырого биогаза.

Номинальная вместимость не равна рабочему объёму. До загрузки проверьте объём сырья вместе с водой, инокулятом и остатком, газовое пространство и конструкцию установки. Оценка всей партии не является выходом одного цикла; литературные параметры не становятся вашими измерениями.

Новая партия зафиксирована: пищевые отходы; масса 3,2 кг; ёмкость сосуда 85 л.

Сырьё жидкое и разбавленное, плотное или содержит подстилку?

### Delivered source links

- [Treatment of Cattle Manure by Anaerobic Co-Digestion with Food Waste and Pig Manure: Methane Yield and Synergistic Effect](https://www.mdpi.com/1660-4601/17/13/4737)
- [DOE Fundamentals Handbook, Thermodynamics, Heat Transfer and Fluid Flow, Vol. 1](https://www.energy.gov/documents/doe-hdbk-1012-92vol1)
- [Building Science: Introduction to Heat Flow](https://basc.pnnl.gov/information/building-science-introduction-heat-flow)
- [EBMUD / US EPA — Anaerobic Digestion of Food Waste](https://www.epa.gov/system/files/documents/2024-08/ebmud-final-report-anaerobic-digestion-of-food-waste-2008-03.pdf)
- [Hafner et al. — Reliable biochemical methane potential testing (2026), original repository and dictionary](https://github.com/AU-BCE-EE/Hafner-2026-IL-BMP)
- [FAO / Marchaim — Biogas processes for sustainable development: Environmental factors](https://www.fao.org/4/t0541e/T0541E06.htm)
- [Koch et al. — Power and Limitations of Biochemical Methane Potential (BMP) Tests](https://www.frontiersin.org/journals/energy-research/articles/10.3389/fenrg.2020.00063/full)
- [US EPA AgSTAR — Anaerobic Digester/Biogas System Operator Guidebook](https://www.epa.gov/sites/default/files/2020-11/documents/agstar-operator-guidebook.pdf)
- [Basisdaten Bioenergie Deutschland 2024](https://www.fnr.de/fileadmin/Projekte/2023/Mediathek/Broschuere_Basisdaten_Bioenergie_2023_web.pdf)
- [Handreichung Biogasgewinnung und -nutzung](https://www.big-east.eu/downloads/FNR_HR_Biogas.pdf)
- [Faustzahlen Biogas](https://biogas.fnr.de/daten-und-fakten/faustzahlen)

## straw

Trace: `reports\qwen4b_manual_qa\limited_chat_1794471914850370900.json` SHA256 `412d400985d3418946d993b2adc863a21ce11c7468fafbda8ffa1334d8055f39`

Question: Есть 4,2 кг сухой соломы и реактор 250 л. Как оценить метан, какую температуру выбрать и выгодна ли переработка?

### Model calls

| Phase | Actual status | Input tokens | Output tokens | Completion reason |
|---|---|---:|---:|---|
| compact_nlu | ok | 139 | 17 | stop |
| tool_selection | ok | 1206 | 75 | stop |
| tool_selection | ok | 1788 | 67 | stop |
| scientific_synthesis | ok | 578 | 86 | stop |

### Tool calls and origin

```json
[
  {
    "tool": "assess_substrate_potential",
    "status": "ok",
    "input_origin": "validated_scientific_state",
    "query": null
  },
  {
    "tool": "assess_process_evidence",
    "status": "ok",
    "input_origin": "validated_scientific_state",
    "query": null
  },
  {
    "tool": "search_scientific_sources",
    "status": "ok",
    "input_origin": "controller_required_evidence"
  },
  {
    "tool": "evaluate_partial_economics",
    "status": "ok",
    "input_origin": "controller_required_evidence"
  }
]
```

### Raw final model call (not the Python result blocks)

```json
{
  "conclusion": "Температурный режим изучен, но не оптимум. Экономический смысл неясен из-за неизвестных затрат.",
  "explanation": "Мезофильный вариант рассмотрен, но оптимум не проверен. Прибыль не подтверждена, затраты неизвестны."
}
```

### Verification and telemetry

```json
{
  "case": "straw",
  "trace": "reports\\qwen4b_manual_qa\\limited_chat_1794471914850370900.json",
  "status": "COMPLETED",
  "started": "2026-11-12T13:25:14.850382+05:00",
  "finished": "2026-11-12T13:25:24.511563+05:00",
  "first_job_seconds": 8.458,
  "calls": 4,
  "admission_free_ram_mib": 8083.9,
  "min_free_ram_mib": 6909.2,
  "max_commit_mib": 17175.0,
  "min_commit_headroom_mib": 18457.4,
  "max_vram_used_mib": 3874,
  "max_gpu_c": 75.0,
  "unload": {
    "status": "UNLOADED",
    "elapsed_seconds": 0.185
  },
  "after_models": [],
  "after_free_ram_mib": 8044.9,
  "after_vram_used_mib": 606,
  "final_author": "qwen_verified",
  "arithmetic": {
    "status": "ok",
    "checked": true,
    "all_checks_passed": true
  },
  "numeric_model_draft": {
    "status": "not_applicable",
    "checked": false,
    "claims": [],
    "scope": "Last model draft: typed numeric grounding and supported unit conversion, not biological verification."
  },
  "scientific": {
    "status": "passed",
    "checked": true,
    "all_checks_passed": true
  },
  "synthesis_rejections": [],
  "stop_reason": null
}
```

### Delivered answer (verbatim)

Литературный ориентир метана рассчитан; это не измеренная выработка установки. Экономическую выгоду определяют полезное использование газа и полные расходы; прибыль пока не подтверждена.

Температурный режим изучен, но не оптимум. Экономический смысл неясен из-за неизвестных затрат.

Солома, при 37 °C в источнике: 679.54 л CH₄ для всей партии.
Расчётная масса органического сухого вещества 3.1756 кг; влажная масса 4.2 кг.
Лабораторный метановый ориентир 214 мл CH₄/г органического сухого вещества; расчёт объёма из его массы и коэффициента выполнил Python.
Срок выработки не задан; число дней не назначаю.
Это отдельные литературные варианты, не доверительный интервал и не гарантия. Состав и подготовка партии должны быть сопоставимы с исследованием. Метан не равен всему биогазу.

Отправной точкой для обсуждения может быть мезофильный режим около 37 °C: он представлен в исследованиях этого сырья. Это не проверенная уставка оборудования; нужны адаптированный инокулят и стабильный контроль.
Мезофильный вариант требует меньше подогрева, чем более горячий термофильный при прочих равных. Повышение температуры может менять аммиачный риск и устойчивость; оно не гарантирует улучшение процесса.
Подогрев для варианта 37 °C: полный расход не определён.
Python считает начальный нагрев и теплопотери отдельно. Нужны фактическая нагреваемая загрузка с водой и инокулятом, начальная и наружная температура, утепление, длительность и потребление мешалки. Номинальный объём не считается массой. Команды нагревателю не отправляются.

Солома: энергия метана 6.775 кВт·ч; полезное тепло 3.252–4.336 кВт·ч ИЛИ электричество 1.0163–1.355 кВт·ч. Эти альтернативы не складываются.
Сбор газа и КПД приняты как условные сценарии оборудования, не измерены. Теплота сгорания и база объёма газа должны быть совместимы.
Принятые допущения: сбор газа 60–80%, КПД получения тепла 80%, электричества 25%. Это примеры оборудования, не универсальные свойства навоза.
Применимый тариф в рыночном хранилище не найден. Цену не подставляю: экономия = полезная энергия × ваш применимый тариф.
В небольшой установке теплопотери и работа мешалки могут поглотить полезный выход. Переработка может иметь смысл при спросе на тепло и достаточно малых полных расходах. Прибыль и окупаемость без этих расходов не подтверждены; неизвестные затраты не равны нулю.
Чувствительность: при неизменных условиях валовая ценность пропорциональна полезной энергии и применимому тарифу. Для безубыточности все расходы должны быть ниже полезной валовой ценности. Тариф природного газа не служит ценой продажи сырого биогаза.

Номинальная вместимость не равна рабочему объёму. До загрузки проверьте объём сырья вместе с водой, инокулятом и остатком, газовое пространство и конструкцию установки. Оценка всей партии не является выходом одного цикла; литературные параметры не становятся вашими измерениями.

В каком регионе находится установка?

### Delivered source links

- [Investigation of the methane potential of horse manure](https://cigrjournal.org/index.php/Ejounral/article/view/2445)
- [DOE Fundamentals Handbook, Thermodynamics, Heat Transfer and Fluid Flow, Vol. 1](https://www.energy.gov/documents/doe-hdbk-1012-92vol1)
- [Building Science: Introduction to Heat Flow](https://basc.pnnl.gov/information/building-science-introduction-heat-flow)
- [Hafner et al. — Reliable biochemical methane potential testing (2026), original repository and dictionary](https://github.com/AU-BCE-EE/Hafner-2026-IL-BMP)
- [FAO, Marchaim (1992), Biogas processes for sustainable development — Environmental factors](https://www.fao.org/4/t0541e/T0541E06.htm)
- [FAO, Marchaim (1992) — Anaerobic processes, plant design and control](https://www.fao.org/4/t0541e/T0541E09.htm)
- [Power and Limitations of Biochemical Methane Potential (BMP) Tests](https://www.frontiersin.org/journals/energy-research/articles/10.3389/fenrg.2020.00063/full)
- [Basisdaten Bioenergie Deutschland 2024](https://www.fnr.de/fileadmin/Projekte/2023/Mediathek/Broschuere_Basisdaten_Bioenergie_2023_web.pdf)
- [Handreichung Biogasgewinnung und -nutzung](https://www.big-east.eu/downloads/FNR_HR_Biogas.pdf)
- [Faustzahlen Biogas](https://biogas.fnr.de/daten-und-fakten/faustzahlen)

## compare

Trace: `reports\qwen4b_manual_qa\limited_chat_1794471926100467800.json` SHA256 `5813784092231c7db306acac2f194c3b3733ef4743cc727436c9eb9ec7fbc405`

Question: Что выгоднее: 7 кг коровьего навоза или 7 кг пищевых отходов? Сравни метан и экономию.

### Model calls

| Phase | Actual status | Input tokens | Output tokens | Completion reason |
|---|---|---:|---:|---|
| compact_nlu | ok | 128 | 51 | stop |
| tool_selection | ok | 885 | 114 | stop |
| tool_selection | ok | 2786 | 103 | stop |
| scientific_synthesis | ok | 592 | 80 | stop |

### Tool calls and origin

```json
[
  {
    "tool": "assess_substrate_potential",
    "status": "ok",
    "input_origin": "validated_scientific_state",
    "query": null
  },
  {
    "tool": "evaluate_partial_economics",
    "status": "ok",
    "input_origin": "validated_scientific_state",
    "query": null
  }
]
```

### Raw final model call (not the Python result blocks)

```json
{
  "conclusion": "Экономический смысл не определён.",
  "explanation": "Полезная энергия оценена, но полные затраты неизвестны. Литературный ориентир есть, но не доказан оптимум. Срок не указан, выгоды не подтверждены."
}
```

### Verification and telemetry

```json
{
  "case": "compare",
  "trace": "reports\\qwen4b_manual_qa\\limited_chat_1794471926100467800.json",
  "status": "COMPLETED",
  "started": "2026-11-12T13:25:26.100479+05:00",
  "finished": "2026-11-12T13:25:38.448521+05:00",
  "first_job_seconds": 10.807,
  "calls": 4,
  "admission_free_ram_mib": 8075.8,
  "min_free_ram_mib": 6754.1,
  "max_commit_mib": 17325.5,
  "min_commit_headroom_mib": 18307.0,
  "max_vram_used_mib": 3873,
  "max_gpu_c": 77.0,
  "unload": {
    "status": "UNLOADED",
    "elapsed_seconds": 0.2
  },
  "after_models": [],
  "after_free_ram_mib": 8051.6,
  "after_vram_used_mib": 605,
  "final_author": "qwen_verified",
  "arithmetic": {
    "status": "ok",
    "checked": true,
    "all_checks_passed": true
  },
  "numeric_model_draft": {
    "status": "not_applicable",
    "checked": false,
    "claims": [],
    "scope": "Last model draft: typed numeric grounding and supported unit conversion, not biological verification."
  },
  "scientific": {
    "status": "passed",
    "checked": true,
    "all_checks_passed": true
  },
  "synthesis_rejections": [],
  "stop_reason": null
}
```

### Delivered answer (verbatim)

Литературный ориентир метана рассчитан; это не измеренная выработка установки. Экономическую выгоду определяют полезное использование газа и полные расходы; прибыль пока не подтверждена.

Экономический смысл не определён.

Навоз КРС, при 37 °C в источнике: 142.24–200.2 л CH₄ для всей партии.
Расчётная масса органического сухого вещества 0.7112–0.8008 кг; влажная масса 7 кг.
Лабораторный метановый ориентир 200–250 мл CH₄/г органического сухого вещества; расчёт объёма из его массы и коэффициента выполнил Python.
Навоз КРС, при 35 °C в источнике: 179.9 л CH₄ для всей партии.
Расчётная масса органического сухого вещества 1.6471 кг; влажная масса 7 кг.
Лабораторный метановый ориентир 109.2 мл CH₄/г органического сухого вещества; расчёт объёма из его массы и коэффициента выполнил Python.
Навоз КРС, при 38 °C в источнике: 135.43 л CH₄ для всей партии.
Расчётная масса органического сухого вещества 0.4907 кг; влажная масса 7 кг.
Лабораторный метановый ориентир 276 мл CH₄/г органического сухого вещества; расчёт объёма из его массы и коэффициента выполнил Python.
Пищевые отходы, при 35 °C в источнике: 445.4 л CH₄ для всей партии.
Расчётная масса органического сухого вещества 0.8442 кг; влажная масса 7 кг.
Лабораторный метановый ориентир 527.5 мл CH₄/г органического сухого вещества; расчёт объёма из его массы и коэффициента выполнил Python.
Срок выработки не задан; число дней не назначаю.
Это отдельные литературные варианты, не доверительный интервал и не гарантия. Состав и подготовка партии должны быть сопоставимы с исследованием. Метан не равен всему биогазу.

По рассмотренным литературным образцам больший условный потенциал метана у Пищевые отходы. Это сравнение газового ориентира; лидер по чистой прибыли без полных затрат не установлен.
Навоз КРС: энергия метана 1.4181–1.996 кВт·ч; полезное тепло 0.6807–1.2774 кВт·ч ИЛИ электричество 0.21272–0.3992 кВт·ч. Эти альтернативы не складываются.
Сбор газа и КПД приняты как условные сценарии оборудования, не измерены. Теплота сгорания и база объёма газа должны быть совместимы.
Принятые допущения: сбор газа 60–80%, КПД получения тепла 80%, электричества 25%. Это примеры оборудования, не универсальные свойства навоза.
Применимый тариф в рыночном хранилище не найден. Цену не подставляю: экономия = полезная энергия × ваш применимый тариф.
Навоз КРС: энергия метана 1.7936 кВт·ч; полезное тепло 0.86091–1.1479 кВт·ч ИЛИ электричество 0.26903–0.35871 кВт·ч. Эти альтернативы не складываются.
Навоз КРС: энергия метана 1.3503 кВт·ч; полезное тепло 0.64813–0.86417 кВт·ч ИЛИ электричество 0.20254–0.27005 кВт·ч. Эти альтернативы не складываются.
Пищевые отходы: энергия метана 4.4406 кВт·ч; полезное тепло 2.1315–2.842 кВт·ч ИЛИ электричество 0.66609–0.88812 кВт·ч. Эти альтернативы не складываются.
В небольшой установке теплопотери и работа мешалки могут поглотить полезный выход. Переработка может иметь смысл при спросе на тепло и достаточно малых полных расходах. Прибыль и окупаемость без этих расходов не подтверждены; неизвестные затраты не равны нулю.
Чувствительность: при неизменных условиях валовая ценность пропорциональна полезной энергии и применимому тарифу. Для безубыточности все расходы должны быть ниже полезной валовой ценности. Тариф природного газа не служит ценой продажи сырого биогаза.

Номинальная вместимость не равна рабочему объёму. До загрузки проверьте объём сырья вместе с водой, инокулятом и остатком, газовое пространство и конструкцию установки. Оценка всей партии не является выходом одного цикла; литературные параметры не становятся вашими измерениями.

В каком виде доступно каждое из сравниваемых видов сырья?

### Delivered source links

- [Moderate thermal, alkaline and thermal-alkaline pretreatment of cattle manure: effects on methane production and economic feasibility](https://link.springer.com/article/10.1007/s43153-025-00592-x)
- [Treatment of Cattle Manure by Anaerobic Co-Digestion with Food Waste and Pig Manure: Methane Yield and Synergistic Effect](https://www.mdpi.com/1660-4601/17/13/4737)
- [Techno-Economic Assessment of Anaerobic Digestion Technology for Small- and Medium-Sized Animal Husbandry Enterprises](https://doi.org/10.3390/app14114957)
- [Basisdaten Bioenergie Deutschland 2024](https://www.fnr.de/fileadmin/Projekte/2023/Mediathek/Broschuere_Basisdaten_Bioenergie_2023_web.pdf)
- [Handreichung Biogasgewinnung und -nutzung](https://www.big-east.eu/downloads/FNR_HR_Biogas.pdf)
- [Faustzahlen Biogas](https://biogas.fnr.de/daten-und-fakten/faustzahlen)
- [DOE Fundamentals Handbook, Thermodynamics, Heat Transfer and Fluid Flow, Vol. 1](https://www.energy.gov/documents/doe-hdbk-1012-92vol1)
- [Building Science: Introduction to Heat Flow](https://basc.pnnl.gov/information/building-science-introduction-heat-flow)

## no_numbers

Trace: `reports\qwen4b_manual_qa\limited_chat_1794471939974119000.json` SHA256 `3b44bb752e4f1335535adfd5b4b5617ce2d85c9591192d8303849e7cfff40aad`

Question: Какую температуру выбрать для жидкого свиного навоза и почему более горячий режим не всегда лучше?

### Model calls

| Phase | Actual status | Input tokens | Output tokens | Completion reason |
|---|---|---:|---:|---|
| compact_nlu | ok | 120 | 16 | stop |
| tool_selection | ok | 719 | 85 | stop |
| tool_selection | ok | 1926 | 72 | stop |
| scientific_synthesis | ok | 575 | 80 | stop |

### Tool calls and origin

```json
[
  {
    "tool": "search_scientific_sources",
    "status": "ok",
    "input_origin": "validated_scientific_state",
    "query": "temperature recommendation for liquid swine manure, why higher temperature not always better"
  },
  {
    "tool": "assess_process_evidence",
    "status": "ok",
    "input_origin": "validated_scientific_state",
    "query": null
  }
]
```

### Raw final model call (not the Python result blocks)

```json
{
  "conclusion": "Температурный режим не определён, но мезофильный вариант изучен.",
  "explanation": "Мезофильная температура рассмотрена, но оптимум не проверен. Экономика не определена. Метан-потенциал не измерен."
}
```

### Verification and telemetry

```json
{
  "case": "no_numbers",
  "trace": "reports\\qwen4b_manual_qa\\limited_chat_1794471939974119000.json",
  "status": "COMPLETED",
  "started": "2026-11-12T13:25:39.974129+05:00",
  "finished": "2026-11-12T13:25:49.397076+05:00",
  "first_job_seconds": 8.316,
  "calls": 4,
  "admission_free_ram_mib": 8068.3,
  "min_free_ram_mib": 6884.9,
  "max_commit_mib": 17202.0,
  "min_commit_headroom_mib": 18430.5,
  "max_vram_used_mib": 3873,
  "max_gpu_c": 79.0,
  "unload": {
    "status": "UNLOADED",
    "elapsed_seconds": 0.185
  },
  "after_models": [],
  "after_free_ram_mib": 8074.1,
  "after_vram_used_mib": 600,
  "final_author": "qwen_grounded_information",
  "arithmetic": {
    "status": "not_applicable",
    "checked": false,
    "all_checks_passed": false
  },
  "numeric_model_draft": {
    "status": "not_applicable",
    "checked": false,
    "claims": [],
    "scope": "Last model draft: typed numeric grounding and supported unit conversion, not biological verification."
  },
  "scientific": {
    "status": "passed",
    "checked": true,
    "all_checks_passed": true
  },
  "synthesis_rejections": [],
  "stop_reason": null
}
```

### Delivered answer (verbatim)

Научные профили проверены; надёжный численный ориентир пока не получен.

Температурный режим не определён, но мезофильный вариант изучен.

Отправной точкой для обсуждения может быть мезофильный режим около 35 °C: он представлен в исследованиях этого сырья. Это не проверенная уставка оборудования; нужны адаптированный инокулят и стабильный контроль.
Мезофильный вариант требует меньше подогрева, чем более горячий термофильный при прочих равных. Повышение температуры может менять аммиачный риск и устойчивость; оно не гарантирует улучшение процесса.
Подогрев для варианта 35 °C: полный расход не определён.
Подогрев для варианта 55 °C: полный расход не определён.
Python считает начальный нагрев и теплопотери отдельно. Нужны фактическая нагреваемая загрузка с водой и инокулятом, начальная и наружная температура, утепление, длительность и потребление мешалки. Номинальный объём не считается массой. Команды нагревателю не отправляются.

Номинальная вместимость не равна рабочему объёму. До загрузки проверьте объём сырья вместе с водой, инокулятом и остатком, газовое пространство и конструкцию установки. Оценка всей партии не является выходом одного цикла; литературные параметры не становятся вашими измерениями.

Сколько сырья вы планируете перерабатывать за одну загрузку?

### Delivered source links

- [FAO / Marchaim — Biogas processes for sustainable development: Environmental factors](https://www.fao.org/4/t0541e/T0541E06.htm)
- [US EPA AgSTAR — Anaerobic Digester/Biogas System Operator Guidebook](https://www.epa.gov/sites/default/files/2020-11/documents/agstar-operator-guidebook.pdf)
- [Validation and Recommendation of Methods to Measure Biogas Production Potential of Animal Manure](https://doi.org/10.5713/ajas.2012.12623)
- [Techno-Economic Assessment of Anaerobic Digestion Technology for Small- and Medium-Sized Animal Husbandry Enterprises](https://doi.org/10.3390/app14114957)
- [The effects of digestion temperature and temperature shock on the biogas yields from the mesophilic anaerobic digestion of swine manure](https://doi.org/10.1016/j.biortech.2006.11.063)
- [Treatment of Cattle Manure by Anaerobic Co-Digestion with Food Waste and Pig Manure: Methane Yield and Synergistic Effect](https://www.mdpi.com/1660-4601/17/13/4737)
- [Microorganism-regulated mechanisms of temperature effects on the performance of anaerobic digestion](https://link.springer.com/article/10.1186/s12934-016-0491-x)
- [US DOE Fundamentals Handbook, Thermodynamics, Heat Transfer, and Fluid Flow, Vol. 1](https://www.energy.gov/documents/doe-hdbk-1012-92vol1)
- [PNNL Building Science: Introduction to Heat Flow](https://basc.pnnl.gov/information/building-science-introduction-heat-flow)

## dialogue

Trace: `reports\qwen4b_manual_qa\limited_chat_1794471950929741800.json` SHA256 `1b4e4087f7d5b472e22f3b4a0b8a2a285363353ec61642f1a4a2724199fa2834`

Question: У меня 63 л жидкого свиного навоза, реактор 210 л. Сколько метана, выгодно ли перерабатывать и какую температуру выбрать?

### Model calls

| Phase | Actual status | Input tokens | Output tokens | Completion reason |
|---|---|---:|---:|---|
| compact_nlu | ok | 138 | 16 | stop |
| tool_selection | ok | 1220 | 89 | stop |
| tool_selection | ok | 3067 | 78 | stop |
| scientific_synthesis | ok | 586 | 73 | stop |
| compact_nlu | ok | 104 | 13 | stop |
| tool_selection | ok | 1282 | 73 | stop |
| tool_selection | error | None | None | None |

### Tool calls and origin

```json
[
  {
    "tool": "search_scientific_sources",
    "status": "ok",
    "input_origin": "validated_scientific_state",
    "query": "methane yield from swine manure, liquid, 63 l, reactor 210 l, temperature recommendation"
  },
  {
    "tool": "estimate_methane_yield",
    "status": "ok",
    "input_origin": "validated_scientific_state",
    "query": null
  },
  {
    "tool": "assess_process_evidence",
    "status": "ok",
    "input_origin": "controller_required_evidence"
  },
  {
    "tool": "evaluate_partial_economics",
    "status": "ok",
    "input_origin": "controller_required_evidence"
  }
]
```

### Raw final model call (not the Python result blocks)

```json
{
  "conclusion": "Оценка метана, температуры и экономики неоднозначна.",
  "explanation": "Метановый потенциал не определён, температура изучена, но не оптимизирована, экономика не проверена."
}
```

### Verification and telemetry

```json
{
  "case": "dialogue",
  "trace": "reports\\qwen4b_manual_qa\\limited_chat_1794471950929741800.json",
  "status": "INCOMPLETE",
  "started": "2026-11-12T13:25:50.929753+05:00",
  "finished": "2026-11-12T13:26:04.602738+05:00",
  "first_job_seconds": 9.012,
  "calls": 7,
  "admission_free_ram_mib": 8069.4,
  "min_free_ram_mib": 6436.1,
  "max_commit_mib": 17647.3,
  "min_commit_headroom_mib": 17985.2,
  "max_vram_used_mib": 3872,
  "max_gpu_c": 82.0,
  "unload": {
    "status": "UNLOADED",
    "elapsed_seconds": 0.257
  },
  "after_models": [],
  "after_free_ram_mib": 8060.0,
  "after_vram_used_mib": 600,
  "final_author": "qwen_verified",
  "arithmetic": {
    "status": "ok",
    "checked": true,
    "all_checks_passed": true
  },
  "numeric_model_draft": {
    "status": "not_applicable",
    "checked": false,
    "claims": [],
    "scope": "Last model draft: typed numeric grounding and supported unit conversion, not biological verification."
  },
  "scientific": {
    "status": "passed",
    "checked": true,
    "all_checks_passed": true
  },
  "synthesis_rejections": [],
  "stop_reason": [
    "gpu_temperature_limit"
  ],
  "second_job": {
    "id": "68235db3759944eea2bf46e3c5c8e0c3",
    "status": "CANCELLED",
    "reply_json": null,
    "cancel_requested": 1,
    "updated_at": "2026-11-12T08:26:04.157541+00:00"
  }
}
```

### Delivered answer (verbatim)

Партия 63 л меньше номинальных 210 л; рабочий объём не указан, загрузка и выход за цикл не подтверждены. Не заполняйте реактор до краёв: учтите воду, инокулят, остаточную жидкость и газовое пространство.

Литературный ориентир метана рассчитан; это не измеренная выработка установки. Экономическую выгоду определяют полезное использование газа и полные расходы; прибыль пока не подтверждена.

Оценка метана, температуры и экономики неоднозначна.

Свиной навоз, при 25 °C в источнике: 336 л CH₄ для всей партии.
Вся партия относительно номинальной ёмкости уже превышает умеренную объёмную загрузку этого опыта. Литературный потенциал относится ко всему сырью, не к одной такой загрузке; рабочий объём и разделение на партии требуют проверки.
Органическое сухое вещество источника 16.31 г/л; по указанному объёму рассчитано 1.0275 кг. Плотность и масса влажного навоза не подставлялись: используется концентрация на литр.
Лабораторный метановый ориентир 327 мл CH₄/г органического сухого вещества; расчёт объёма из его массы и коэффициента выполнил Python.
Свиной навоз, при 30 °C в источнике: 399.71 л CH₄ для всей партии.
Лабораторный метановый ориентир 389 мл CH₄/г органического сухого вещества; расчёт объёма из его массы и коэффициента выполнил Python.
Свиной навоз, при 35 °C в источнике: 414.09 л CH₄ для всей партии.
Лабораторный метановый ориентир 403 мл CH₄/г органического сухого вещества; расчёт объёма из его массы и коэффициента выполнил Python.
Срок выработки не задан; число дней не назначаю.
Это отдельные литературные варианты, не доверительный интервал и не гарантия. Состав и подготовка партии должны быть сопоставимы с исследованием. Метан не равен всему биогазу.

Отправной точкой для обсуждения может быть мезофильный режим около 35 °C: он представлен в исследованиях этого сырья. Это не проверенная уставка оборудования; нужны адаптированный инокулят и стабильный контроль.
Мезофильный вариант требует меньше подогрева, чем более горячий термофильный при прочих равных. Повышение температуры может менять аммиачный риск и устойчивость; оно не гарантирует улучшение процесса.
Подогрев для варианта 35 °C: полный расход не определён.
Подогрев для варианта 55 °C: полный расход не определён.
Python считает начальный нагрев и теплопотери отдельно. Нужны фактическая нагреваемая загрузка с водой и инокулятом, начальная и наружная температура, утепление, длительность и потребление мешалки. Номинальный объём не считается массой. Команды нагревателю не отправляются.

Рыночные записи проверены; без применимого газового ориентира денежный результат пока не установлен.
В небольшой установке теплопотери и работа мешалки могут поглотить полезный выход. Переработка может иметь смысл при спросе на тепло и достаточно малых полных расходах. Прибыль и окупаемость без этих расходов не подтверждены; неизвестные затраты не равны нулю.
Чувствительность: при неизменных условиях валовая ценность пропорциональна полезной энергии и применимому тарифу. Для безубыточности все расходы должны быть ниже полезной валовой ценности. Тариф природного газа не служит ценой продажи сырого биогаза.

Номинальная вместимость не равна рабочему объёму. До загрузки проверьте объём сырья вместе с водой, инокулятом и остатком, газовое пространство и конструкцию установки. Оценка всей партии не является выходом одного цикла; литературные параметры не становятся вашими измерениями.

Новая партия зафиксирована: свиной навоз; объём сырья 63 л; ёмкость сосуда 210 л.

В каком регионе находится установка?

### Delivered source links

- [FAO / Marchaim — Biogas processes for sustainable development: Environmental factors](https://www.fao.org/4/t0541e/T0541E06.htm)
- [Koch et al. — Power and Limitations of Biochemical Methane Potential (BMP) Tests](https://www.frontiersin.org/journals/energy-research/articles/10.3389/fenrg.2020.00063/full)
- [US EPA AgSTAR — Anaerobic Digester/Biogas System Operator Guidebook](https://www.epa.gov/sites/default/files/2020-11/documents/agstar-operator-guidebook.pdf)
- [Validation and Recommendation of Methods to Measure Biogas Production Potential of Animal Manure](https://doi.org/10.5713/ajas.2012.12623)
- [Techno-Economic Assessment of Anaerobic Digestion Technology for Small- and Medium-Sized Animal Husbandry Enterprises](https://doi.org/10.3390/app14114957)
- [The effects of digestion temperature and temperature shock on the biogas yields from the mesophilic anaerobic digestion of swine manure](https://doi.org/10.1016/j.biortech.2006.11.063)
- [Treatment of Cattle Manure by Anaerobic Co-Digestion with Food Waste and Pig Manure: Methane Yield and Synergistic Effect](https://www.mdpi.com/1660-4601/17/13/4737)
- [Microorganism-regulated mechanisms of temperature effects on the performance of anaerobic digestion](https://link.springer.com/article/10.1186/s12934-016-0491-x)
- [DOE Fundamentals Handbook, Thermodynamics, Heat Transfer and Fluid Flow, Vol. 1](https://www.energy.gov/documents/doe-hdbk-1012-92vol1)
- [Building Science: Introduction to Heat Flow](https://basc.pnnl.gov/information/building-science-introduction-heat-flow)
- [Basisdaten Bioenergie Deutschland 2024](https://www.fnr.de/fileadmin/Projekte/2023/Mediathek/Broschuere_Basisdaten_Bioenergie_2023_web.pdf)
- [Handreichung Biogasgewinnung und -nutzung](https://www.big-east.eu/downloads/FNR_HR_Biogas.pdf)
- [Faustzahlen Biogas](https://biogas.fnr.de/daten-und-fakten/faustzahlen)
