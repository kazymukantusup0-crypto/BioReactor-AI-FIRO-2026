# Actual browser / real Qwen3 4B independent baseline

Original frozen questions; application code unchanged. Raw requests, responses, tools, verifiers and resource samples: live_browser_settled/browser.json. No fallback is classified as a successful model answer.

## food

### User question

У меня 120 литров пищевых отходов из столовой, реактор номинально 250 литров. Хочу понять возможный выход метана, подходящий температурный режим и риск закисления. Что можно оценить сейчас и как действовать, если состав отходов я ещё не измерял?

### Delivered answer (verbatim)

Научные профили проверены; надёжный численный ориентир пока не получен.

Метановый потенциал не определен, температура мезофильная, но оптимум не проверен. Метан не рассчитан, температура изучена, но оптимум не подтвержден, затраты неизвестны.

Совместимой цепочки пока нет. Можно уточнить вид и состояние сырья; самостоятельно подбирать научные коэффициенты фермеру не требуется.
Срок выработки не задан; число дней не назначаю.
Это отдельные литературные варианты, не доверительный интервал и не гарантия. Состав и подготовка партии должны быть сопоставимы с исследованием. Метан не равен всему биогазу.

Отправной точкой для обсуждения может быть мезофильный режим около 35 °C: он представлен в исследованиях этого сырья. Это не проверенная уставка оборудования; нужны адаптированный инокулят и стабильный контроль.
Мезофильный вариант требует меньше подогрева, чем более горячий термофильный при прочих равных. Повышение температуры может менять аммиачный риск и устойчивость; оно не гарантирует улучшение процесса.
Затраты на подогрев пока неизвестны. Нужны масса загрузки с водой и инокулятом, начальная и наружная температура, утепление, длительность и расход мешалки. Начальный нагрев и теплопотери учитываются отдельно; номинальный объём не заменяет массу. Команды нагревателю не отправляются.

Номинальная вместимость не равна рабочему объёму. До загрузки проверьте объём сырья вместе с водой, инокулятом и остатком, газовое пространство и конструкцию установки. Оценка всей партии не является выходом одного цикла; литературные параметры не становятся вашими измерениями.

Сырьё жидкое и разбавленное, плотное или содержит подстилку?

### Structured display (verbatim)

{
  "paragraphs": [
    "Научные профили проверены; надёжный численный ориентир пока не получен.",
    "Метановый потенциал не определен, температура мезофильная, но оптимум не проверен. Метан не рассчитан, температура изучена, но оптимум не подтвержден, затраты неизвестны.",
    "Совместимой цепочки пока нет. Можно уточнить вид и состояние сырья; самостоятельно подбирать научные коэффициенты фермеру не требуется.\nСрок выработки не задан; число дней не назначаю.\nЭто отдельные литературные варианты, не доверительный интервал и не гарантия. Состав и подготовка партии должны быть сопоставимы с исследованием. Метан не равен всему биогазу.",
    "Отправной точкой для обсуждения может быть мезофильный режим около 35 °C: он представлен в исследованиях этого сырья. Это не проверенная уставка оборудования; нужны адаптированный инокулят и стабильный контроль.\nМезофильный вариант требует меньше подогрева, чем более горячий термофильный при прочих равных. Повышение температуры может менять аммиачный риск и устойчивость; оно не гарантирует улучшение процесса.\nЗатраты на подогрев пока неизвестны. Нужны масса загрузки с водой и инокулятом, начальная и наружная температура, утепление, длительность и расход мешалки. Начальный нагрев и теплопотери учитываются отдельно; номинальный объём не заменяет массу. Команды нагревателю не отправляются.",
    "Номинальная вместимость не равна рабочему объёму. До загрузки проверьте объём сырья вместе с водой, инокулятом и остатком, газовое пространство и конструкцию установки. Оценка всей партии не является выходом одного цикла; литературные параметры не становятся вашими измерениями."
  ],
  "sections": [
    {
      "title": "Краткий вывод",
      "body": "Научные профили проверены; надёжный численный ориентир пока не получен."
    },
    {
      "title": "Объяснение консультанта",
      "body": "Метановый потенциал не определен, температура мезофильная, но оптимум не проверен. Метан не рассчитан, температура изучена, но оптимум не подтвержден, затраты неизвестны."
    },
    {
      "title": "Оценка метана",
      "body": "Совместимой цепочки пока нет. Можно уточнить вид и состояние сырья; самостоятельно подбирать научные коэффициенты фермеру не требуется.\nСрок выработки не задан; число дней не назначаю.\nЭто отдельные литературные варианты, не доверительный интервал и не гарантия. Состав и подготовка партии должны быть сопоставимы с исследованием. Метан не равен всему биогазу."
    },
    {
      "title": "Температура и энергия",
      "body": "Отправной точкой для обсуждения может быть мезофильный режим около 35 °C: он представлен в исследованиях этого сырья. Это не проверенная уставка оборудования; нужны адаптированный инокулят и стабильный контроль.\nМезофильный вариант требует меньше подогрева, чем более горячий термофильный при прочих равных. Повышение температуры может менять аммиачный риск и устойчивость; оно не гарантирует улучшение процесса.\nЗатраты на подогрев пока неизвестны. Нужны масса загрузки с водой и инокулятом, начальная и наружная температура, утепление, длительность и расход мешалки. Начальный нагрев и теплопотери учитываются отдельно; номинальный объём не заменяет массу. Команды нагревателю не отправляются."
    },
    {
      "title": "Практические ограничения",
      "body": "Номинальная вместимость не равна рабочему объёму. До загрузки проверьте объём сырья вместе с водой, инокулятом и остатком, газовое пространство и конструкцию установки. Оценка всей партии не является выходом одного цикла; литературные параметры не становятся вашими измерениями."
    }
  ],
  "question": {
    "id": "v9-f29c0606dddd3c",
    "text": "Сырьё жидкое и разбавленное, плотное или содержит подстилку?",
    "options": [],
    "fields": [],
    "reason": "Model-selected next useful clarification"
  },
  "sources": [
    {
      "title": "EBMUD / US EPA — Anaerobic Digestion of Food Waste",
      "url": "https://www.epa.gov/system/files/documents/2024-08/ebmud-final-report-anaerobic-digestion-of-food-waste-2008-03.pdf"
    },
    {
      "title": "FAO / Marchaim — Biogas processes for sustainable development: Environmental factors",
      "url": "https://www.fao.org/4/t0541e/T0541E06.htm"
    },
    {
      "title": "Koch et al. — Power and Limitations of Biochemical Methane Potential (BMP) Tests",
      "url": "https://www.frontiersin.org/journals/energy-research/articles/10.3389/fenrg.2020.00063/full"
    },
    {
      "title": "US EPA AgSTAR — Anaerobic Digester/Biogas System Operator Guidebook",
      "url": "https://www.epa.gov/sites/default/files/2020-11/documents/agstar-operator-guidebook.pdf"
    },
    {
      "title": "US EPA — Risk Analysis and Technical Review Checklist for Preparing Biogas Project Plans",
      "url": "https://nepis.epa.gov/Exe/ZyPURL.cgi?Dockey=P10105XN.TXT"
    },
    {
      "title": "Treatment of Cattle Manure by Anaerobic Co-Digestion with Food Waste and Pig Manure: Methane Yield and Synergistic Effect",
      "url": "https://www.mdpi.com/1660-4601/17/13/4737"
    },
    {
      "title": "US DOE Fundamentals Handbook, Thermodynamics, Heat Transfer, and Fluid Flow, Vol. 1",
      "url": "https://www.energy.gov/documents/doe-hdbk-1012-92vol1"
    },
    {
      "title": "PNNL Building Science: Introduction to Heat Flow",
      "url": "https://basc.pnnl.gov/information/building-science-introduction-heat-flow"
    }
  ],
  "modes": [
    "verified_model_synthesis",
    "INSUFFICIENT_EVIDENCE",
    "farmer_consultation"
  ],
  "assumptions": [
    "market_region",
    "reactor_total_volume_l"
  ]
}

### Actual tools and their origins

`json
[
  {
    "tool": "search_scientific_sources",
    "status": "ok",
    "input_origin": "validated_scientific_state",
    "query": "methane yield from food waste, reactor volume 250l, 120l load, temperature recommendation, risk of acidification",
    "result": {
      "status": "ok",
      "search_mode": "curated_local_catalogue_with_structured_claims",
      "query": "methane yield from food waste, reactor volume 250L, 120L load, temperature recommendation, risk of acidification",
      "sources": [
        {
          "id": "ebmud",
          "title": "EBMUD / US EPA — Anaerobic Digestion of Food Waste",
          "url": "https://www.epa.gov/system/files/documents/2024-08/ebmud-final-report-anaerobic-digestion-of-food-waste-2008-03.pdf",
          "year": 2008,
          "doi": null,
          "locator": "Section 3.3 pH; bench-scale prepared food-waste pulp",
          "reviewed_by": "Primary report rechecked, 2026-10-28",
          "verified_on": "2026-10-28",
          "provenance": "SOURCE_VERIFIED"
        },
        {
          "id": "fao_environment",
          "title": "FAO / Marchaim — Biogas processes for sustainable development: Environmental factors",
          "url": "https://www.fao.org/4/t0541e/T0541E06.htm",
          "year": 1992,
          "doi": null,
          "locator": "Temperature and pH sections",
          "reviewed_by": "Codex primary-source inspection, 2026-10-28",
          "verified_on": "2026-10-28",
          "provenance": "SOURCE_VERIFIED"
        },
        {
          "id": "q4b_koch2020",
          "title": "Power and Limitations of Biochemical Methane Potential (BMP) Tests",
          "url": "https://www.frontiersin.org/journals/energy-research/articles/10.3389/fenrg.2020.00063/full",
          "year": 2020,
          "doi": "10.3389/fenrg.2020.00063",
          "locator": "Anaerobic biodegradability and Conclusions",
          "reviewed_by": "Codex source review",
          "verified_on": "2026-11-11",
          "provenance": "SOURCE_VERIFIED"
        },
        {
          "id": "bmp_limits_2020",
          "title": "Koch et al. — Power and Limitations of Biochemical Methane Potential (BMP) Tests",
          "url": "https://www.frontiersin.org/journals/energy-research/articles/10.3389/fenrg.2020.00063/full",
          "year": 2020,
          "doi": "10.3389/fenrg.2020.00063",
          "locator": "Sections on inappropriate applications and conclusions; batch BMP limits for actual yield, process stability, OLR and HRT",
          "reviewed_by": "Primary-source review, 2026-11-09",
          "verified_on": "2026-11-09",
          "provenance": "SOURCE_VERIFIED"
        },
        {
          "id": "epa_agstar_operator_2020",
          "title": "US EPA AgSTAR — Anaerobic Digester/Biogas System Operator Guidebook",
          "url": "https://www.epa.gov/sites/default/files/2020-11/documents/agstar-operator-guidebook.pdf",
          "year": 2020,
          "doi": null,
          "locator": "Sections 3.1–3.4 (retention, loading, temperature and VS); 5.0 (TS/VS); 7.1 (headspace)",
          "reviewed_by": "Primary-source review, 2026-11-09",
          "verified_on": "2026-11-09",
          "provenance": "SOURCE_VERIFIED"
        },
        {
          "id": "epa_biogas_plan_checklist_2020",
          "title": "US EPA — Risk Analysis and Technical Review Checklist for Preparing Biogas Project Plans",
          "url": "https://nepis.epa.gov/Exe/ZyPURL.cgi?Dockey=P10105XN.TXT",
          "year": 2020,
          "doi": null,
          "locator": "Sections 6–8: operating volume/daily influent HRT, dilution volume, TS and VS loading calculations",
          "reviewed_by": "Primary-source review, 2026-11-09",
          "verified_on": "2026-11-09",
          "provenance": "SOURCE_VERIFIED"
        }
      ],
      "claims": [
        {
          "id": "mesophilic_reference",
          "source_id": "fao_environment",
          "topics": [
            "temperature"
          ],
          "materials": [
            "manure",
            "cattle_manure",
            "swine_manure",
            "poultry_manure",
            "food_waste",
            "Wheat straw",
            "Whey",
            "Cellulose"
          ],
          "category": "anaerobic_digestion",
          "process_type": "general anaerobic digestion",
          "values": [
            35
          ],
          "unit": "°C",
          "scope": "General literature reference, not a verified optimum or control setpoint for this installation",
          "text": {
            "ru": "FAO описывает мезофильное сбраживание около 35 °C. Это общий литературный ориентир, а не доказанный оптимум вашего реактора.",
            "en": "FAO describes mesophilic digestion at about 35 °C. This is a general literature reference, not a verified optimum for your reactor.",
            "kk": "FAO мезофильді ашытуды шамамен 35 °C деңгейінде сипаттайды. Бұл жалпы әдеби бағдар, сіздің реакторыңыздың дәлелденген оңтайлы температурасы емес."
          }
        },
        {
          "id": "temperature_stability",
          "source_id": "fao_environment",
          "topics": [
            "temperature",
            "low_gas"
          ],
          "materials": [
            "manure",
            "cattle_manure",
            "swine_manure",
            "poultry_manure",
            "food_waste"
          ],
          "category": "anaerobic_digestion",
          "process_type": "general anaerobic digestion",
          "values": [],
          "unit": null,
          "scope": "General sensitivity of methanogenic populations; no diagnosis without measurements",
          "text": {
            "ru": "Метаногены чувствительны к температурным колебаниям; важна стабильность режима.",
            "en": "Methanogens are sensitive to temperature changes; stability matters.",
            "kk": "Метаногендер температура өзгерісіне сезімтал; режимнің тұрақтылығы маңызды."
          }
        },
        {
          "id": "q4b_bmp_not_theoretical_maximum",
          "source_id": "q4b_koch2020",
          "topics": [
            "bmp"
          ],
          "materials": [
            "general"
          ],
          "category": "process",
          "process_type": "anaerobic digestion",
          "values": [],
          "unit": null,
          "scope": "Properly conducted BMP assays and theoretical methane potential; real reactor performance depends on operating conditions.",
          "text": {
            "ru": "BMP — экспериментально измеряемый в лабораторном batch-тесте метановый потенциал образца при заданных условиях; теоретический выход рассчитывают отдельно по составу или ХПК с допущениями. Это разные понятия, хотя их численные значения могут совпасть; BMP не гарантирует выработку конкретного реактора.",
            "en": "BMP is an experimentally measured sample methane potential in a laboratory batch assay under specified conditions. Theoretical yield is calculated separately from composition or COD with assumptions. These concepts differ, though their numerical values can coincide; BMP does not guarantee reactor output.",
            "kk": "BMP — берілген жағдайдағы зертханалық batch сынағында эксперименттік жолмен өлшенетін үлгінің метан әлеуеті. Теориялық шығым құрам немесе ХПК бойынша жорамалдармен есептеледі. Бұл — әртүрлі ұғымдар, алайда олардың сандық мәндері сәйкес келуі мүмкін; BMP нақты реактор шығымына кепілдік бермейді."
          }
        },
        {
          "id": "q4b_timed_reactor_yield_kinetics",
          "source_id": "q4b_koch2020",
          "topics": [
            "bmp"
          ],
          "materials": [
            "general"
          ],
          "category": "process",
          "process_type": "anaerobic digestion",
          "values": [],
          "unit": null,
          "scope": "Time-limited reactor yield; batch assay kinetics do not establish continuous reactor performance.",
          "text": {
            "ru": "Фактический выход за заданный срок зависит от кинетики, доступности разлагаемого вещества и условий реактора; BMP не гарантирует такой выход за этот срок.",
            "en": "Actual yield by a given time depends on kinetics, accessible degradable matter and reactor conditions; BMP does not guarantee the yield at that time.",
            "kk": "Белгілі мерзімдегі нақты шығым кинетикаға, ыдырайтын заттың қолжетімділігіне және реактор жағдайына байланысты; BMP сол мерзімдегі шығымға кепілдік бермейді."
          }
        },
        {
          "id": "q4b_batch_conditions_and_rate",
          "source_id": "q4b_koch2020",
          "topics": [
            "bmp"
          ],
          "materials": [
            "general"
          ],
          "category": "process",
          "process_type": "laboratory batch assay",
          "values": [],
          "unit": null,
          "scope": "Observed assay yield and accumulation rate; not a claim that rates alone change ultimate stoichiometric yield.",
          "text": {
            "ru": "Условия batch-теста влияют на наблюдаемый BMP, а кинетика — на скорость накопления метана и выход к моменту наблюдения. Кинетические параметры лабораторного опыта нельзя автоматически переносить на рабочий реактор.",
            "en": "Batch assay conditions affect observed BMP; kinetics affects methane accumulation rate and yield at the observation time. Assay kinetic parameters do not automatically transfer to an operating reactor.",
            "kk": "Batch сынағының жағдайлары байқалатын BMP-ге, ал кинетика метан жиналу жылдамдығына және бақылау сәтіндегі шығымға әсер етеді. Зертханалық кинетикалық параметрлер нақты реакторға автоматты түрде көшірілмейді."
          }
        },
        {
          "id": "bmp_is_batch_potential",
          "source_id": "bmp_limits_2020",
          "topics": [
            "bmp"
          ],
          "materials": [
            "manure",
            "cattle_manure",
            "swine_manure",
            "poultry_manure",
            "food_waste",
            "Wheat straw",
            "Whey",
            "Cellulose"
          ],
          "category": "anaerobic_digestion",
          "process_type": "laboratory batch assay",
          "values": [],
          "unit": null,
          "scope": "Laboratory batch measurement of substrate methane potential under assay conditions; not a plant measurement",
          "text": {
            "ru": "BMP — лабораторно измеренный биохимический потенциал образования метана в batch-тесте при заданных условиях опыта. Это потенциальная характеристика испытанного образца, а не измеренная выработка конкретного реактора.",
            "en": "BMP is a laboratory measurement of a substrate's biochemical methane potential in a batch test under stated assay conditions. It describes the tested sample's potential, not methane measured from a particular reactor.",
            "kk": "BMP — көрсетілген зертханалық жағдайларда batch-тестте өлшенетін субстраттың метан түзу биохимиялық әлеуеті. Бұл сыналған үлгінің әлеуеті, нақты реакторда өлшенген өнім емес."
          }
        },
        {
          "id": "bmp_does_not_predict_continuous_stability",
          "source_id": "bmp_limits_2020",
          "topics": [
            "bmp",
            "retention",
            "loading"
          ],
          "materials": [
            "manure",
            "cattle_manure",
            "swine_manure",
            "poultry_manure",
            "food_waste",
            "Wheat straw",
            "Whey",
            "Cellulose"
          ],
          "category": "anaerobic_digestion",
          "process_type": "batch BMP versus continuous digestion",
          "values": [],
          "unit": null,
          "scope": "A batch BMP does not establish continuous-system actual yield, process stability, OLR or HRT",
          "text": {
            "ru": "Однократная batch-подача в BMP не показывает устойчивость длительной непрерывной работы, допустимую органическую нагрузку или HRT. Эти характеристики зависят от конструкции и режима реактора и требуют данных непрерывного процесса либо сопоставимой установки.",
            "en": "A single batch feed in a BMP test does not establish long-term continuous stability, achievable organic loading, or HRT. These depend on reactor design and operation and require continuous-process data or a comparable installation.",
            "kk": "BMP-тесттегі бір реттік batch беру ұзақ мерзімді үздіксіз жұмыстың тұрақтылығын, органикалық жүктемені немесе HRT-ті анықтамайды. Бұлар реактордың құрылымы мен режиміне тәуелді және үздіксіз процесс деректерін не ұқсас қондырғыны қажет етеді."
          }
        },
        {
          "id": "temperature_changes_rates_and_microbes",
          "source_id": "epa_agstar_operator_2020",
          "topics": [
            "temperature"
          ],
          "materials": [
            "manure",
            "cattle_manure",
            "swine_manure",
            "poultry_manure",
            "food_waste",
            "Wheat straw",
            "Whey",
            "Cellulose"
          ],
          "category": "anaerobic_digestion",
          "process_type": "temperature-dependent biological digestion",
          "values": [],
          "unit": null,
          "scope": "General temperature effect; no installation-specific optimum or control setpoint",
          "text": {
            "ru": "Температура влияет на скорость разложения и на то, какие группы метаногенов преобладают. Реактор проектируют под определённый режим; само по себе повышение температуры не обосновывает новый setpoint и не гарантирует лучшую работу.",
            "en": "Temperature affects decomposition rate and which methanogen populations predominate. Digesters are designed for a particular regime, so raising temperature alone does not justify a new setpoint or guarantee better operation.",
            "kk": "Температура ыдырау жылдамдығына және метаногендердің қай топтары басым болатынына әсер етеді. Реактор белгілі бір режимге жобаланады; температураны жай ғана көтеру жаңа мақсатты мәнді негіздемейді және жұмыстың жақсаруына кепіл болмайды."
          }
        },
        {
          "id": "reactor_volume_not_charge_volume",
          "source_id": "epa_biogas_plan_checklist_2020",
          "topics": [
            "capacity",
            "loading"
          ],
          "materials": [
            "manure",
            "cattle_manure",
            "swine_manure",
            "poultry_manure",
            "food_waste",
            "Wheat straw",
            "Whey",
            "Cellulose"
          ],
          "category": "anaerobic_digestion",
          "process_type": "engineered digester loading and volume",
          "values": [],
          "unit": null,
          "scope": "Nominal vessel volume alone does not establish allowable feed charge; working/operating volume and complete influent matter",
          "text": {
            "ru": "Номинальная вместимость корпуса не равна допустимому объёму загрузки. В расчётах используют рабочий объём; учитывают сырьё и добавляемые воду и инокулят, а также предусмотренное конструкцией газовое пространство. Допуск загрузки задают проект и инструкция реактора, поэтому нельзя заполнять его до краёв.",
            "en": "Nominal vessel capacity is not the same as allowable charge volume. Design calculations use working volume; feed, added water and inoculum, and the vessel's gas space matter. The design and reactor instructions set loading limits, so the vessel should not be filled to the brim.",
            "kk": "Корпустың номинал сыйымдылығы рұқсат етілген жүктеу көлеміне тең емес. Есепте жұмыс көлемі алынады; шикізат, қосылатын су мен инокулят және конструкциядағы газ кеңістігі ескеріледі. Жүктеу шегін жоба мен реактор нұсқаулығы анықтайды, сондықтан оны ернеуіне дейін толтыруға болмайды."
          }
        }
      ],
      "filters": {
        "material": "food_waste",
        "topics": [
          "temperature",
          "bmp",
          "capacity"
        ],
        "category": null,
        "process_type": null
      },
      "live_web_search": false,
      "message": "Поиск по локально проверенному каталогу; свежий поиск публикаций в интернете не выполнялся."
    }
  },
  {
    "tool": "assess_process_evidence",
    "status": "ok",
    "input_origin": "validated_scientific_state",
    "query": null,
    "result": {
      "status": "ok",
      "message": "Process effects separated from unmeasured yield changes.",
      "temperature_consultation": {
        "discussion_temperature_c": 35,
        "user_temperature_c": null,
        "options": [
          {
            "temperature_c": 35,
            "kind": "LITERATURE_DISCUSSION",
            "heat_balance": {
              "status": "needs_input",
              "result_provenance": null,
              "initial_thermal_kwh": null,
              "initial_heating_kwh": null,
              "maintenance_heating_kwh": null,
              "auxiliary_kwh": null,
              "total_energy_kwh": null,
              "known_subtotal_kwh": null,
              "cooling_required": false,
              "missing": [
                "initial_temperature_c",
                "heated_mass_kg",
                "heat_capacity_kj_kg_k",
                "heat_loss_coefficient_w_k",
                "auxiliary_power_w",
                "auxiliary_duty_fraction",
                "duration_days",
                "energy_scope"
              ],
              "scope": null,
              "warnings": [],
              "formulas": {
                "initial_thermal_kwh": "heated_mass_kg * cp_kJ_kg_K * max(T_target-T_initial,0) / 3600",
                "initial_heating_kwh": "initial_thermal_kwh / heater_efficiency",
                "maintenance_heating_kwh": "UA_W_K * max(T_target-T_ambient,0) * duration_days * 24 / 1000 / heater_efficiency",
                "auxiliary_kwh": "auxiliary_power_W * duty_fraction * duration_days * 24 / 1000, or explicit measured energy"
              },
              "limitations": [
                "Constant heat capacity; no phase change, evaporation, biological heat or heat recovery model.",
                "UA and temperatures are user inputs; steady holding losses exclude startup transients.",
                "Heated mass includes only the explicit input. Inoculum, water and vessel thermal mass must be included by the user.",
                "Energy scope/duration is explicit; no automatic scaling from one charge to the entire feedstock lot."
              ],
              "scientific_sources": [
                {
                  "title": "US DOE Fundamentals Handbook, Thermodynamics, Heat Transfer, and Fluid Flow, Vol. 1",
                  "url": "https://www.energy.gov/documents/doe-hdbk-1012-92vol1",
                  "year": 1992,
                  "scope": "Sensible heat Q=m cp delta T; not a reactor-specific calibration"
                },
                {
                  "title": "PNNL Building Science: Introduction to Heat Flow",
                  "url": "https://basc.pnnl.gov/information/building-science-introduction-heat-flow",
                  "scope": "Steady heat-transfer relation UA delta T, not measured reactor heat loss"
                }
              ],
              "heating_input_kwh": null,
              "electricity_input_kwh": null,
              "heating_carrier": null,
              "process_heat_draw_kwh": null,
              "loads": [],
              "known_load_subtotal_kwh": null,
              "input_provenance": "HYPOTHETICAL_SCENARIO",
              "scope_valid_for_batch": false
            },
            "operation_authorized": false
          }
        ],
        "process_studies": [],
        "sources": [
          {
            "title": "US DOE Fundamentals Handbook, Thermodynamics, Heat Transfer, and Fluid Flow, Vol. 1",
            "url": "https://www.energy.gov/documents/doe-hdbk-1012-92vol1",
            "year": 1992,
            "scope": "Sensible heat Q=m cp delta T; not a reactor-specific calibration"
          },
          {
            "title": "PNNL Building Science: Introduction to Heat Flow",
            "url": "https://basc.pnnl.gov/information/building-science-introduction-heat-flow",
            "scope": "Steady heat-transfer relation UA delta T, not measured reactor heat loss"
          }
        ],
        "automatic_setpoint_c": null,
        "operation_authorized": false,
        "interpretation": "A study-based starting point for engineering discussion; not a validated setpoint or optimum."
      },
      "temperature_c": null,
      "dilution_water_l": null,
      "added_water_vs_kg": null,
      "added_water_methane_potential_m3": null,
      "water_effect": "Clean water adds no organic VS; potential from the original feed remains unchanged. Actual conversion may change through dilution/inhibition; extra liquid requires capacity and heating checks.",
      "temperature_effect": "Temperature alone does not establish an optimum. Increasing it raises heat demand and may change kinetics and ammonia risk; gradual change requires acclimated inoculum and monitoring.",
      "matched_temperature_experiments": [
        {
          "profile_id": "baek2020-food-pulp",
          "source_id": "baek2020",
          "physical_state": "prepared_pulp",
          "temperature_c": 35,
          "evidence_level": "PUBLISHED_EXPERIMENT_NOT_AN_OPERATING_SETPOINT"
        }
      ],
      "mesophilic_discussion_reference_c": 35,
      "reference_scope": "Around 35 C can be discussed as a mesophilic scenario where supported by the material corpus; the exact liquid/solid study conditions above take precedence. Neither is a validated optimum or automatic setpoint.",
      "heating_missing": [
        "heated_mass_kg",
        "initial_temperature_c",
        "heat_capacity_kj_kg_k",
        "heating_efficiency",
        "heat_losses"
      ],
      "heating_formula": "Q = heated_mass_kg * heat_capacity_kj_kg_k * temperature_change_c / 3600 / efficiency",
      "missing": [
        "substrate",
        "current_gas_rate",
        "pH_VFA_alkalinity",
        "inoculum_adaptation",
        "heat_losses_and_energy_cost"
      ],
      "sources": [
        {
          "id": "baek2020",
          "doi": "10.3390/ijerph17134737",
          "title": "Treatment of Cattle Manure by Anaerobic Co-Digestion with Food Waste and Pig Manure: Methane Yield and Synergistic Effect",
          "authors": [
            "Gahyun Baek",
            "Danbee Kim",
            "Jinsu Kim",
            "Hanwoong Kim",
            "Changsoo Lee"
          ],
          "year": 2020,
          "published_at": "2020-07-01",
          "url": "https://www.mdpi.com/1660-4601/17/13/4737",
          "review_url": "https://pdfs.semanticscholar.org/8c32/8da3dc70a2964a51e0cfd2807c009edd691c.pdf",
          "reviewed_sections": [
            "Tables 1-2, Methods 2.1-2.3, Results 3.2, Equations 1-2"
          ],
          "verification_stage": "NUMERIC_DATA_VERIFIED",
          "review_method": "Primary article PDF read through browser document extraction. Programmatic mirror download redirected across origins and was not followed. Publisher 429 and PMC CAPTCHA were not bypassed.",
          "conditions": {
            "temperature_c": 35,
            "duration_days": 30,
            "duration_kind": "BMP_INCUBATION",
            "reactor_type": "250 mL bottles, 200 mL working volume; triplicate and blank corrected",
            "inoculum": "Digestate from mesophilic food/pig-manure plant; 100 mL inoculum plus 100 mL substrate diluted to 10 g VS/L",
            "mixing": "daily manual shaking",
            "gas_basis": {
              "temperature_k": 273.15,
              "pressure_pa": 101325,
              "moisture": "unknown"
            },
            "mixing_ratio_basis": "total solids, not wet mass"
          }
        }
      ],
      "actuator_access": false
    }
  },
  {
    "tool": "estimate_methane_yield",
    "status": "needs_input",
    "input_origin": "controller_required_evidence",
    "result": {
      "status": "needs_input",
      "local_experiments": {
        "status": "checked",
        "records_checked": 0,
        "candidates": [],
        "automatic_transfer": false,
        "reason": "Existing experiment schema records gas observations, not a reviewed substrate BMP profile with preparation, blank correction and structured gas basis. Matching names alone cannot establish transferability."
      },
      "message": "Reviewed same-material profiles evaluated as explicit scenarios; unavailable properties remain missing.",
      "catalog_checked": true,
      "comparison_mode": "mixture",
      "scenarios": [
        {
          "id": "s1",
          "result_level": "UNAVAILABLE",
          "result_provenance": null,
          "label": "Пищевые отходы",
          "profile_ids": [
            "baek2020-food-pulp"
          ],
          "components": [
            {
              "id": "c1",
              "material": "food_waste",
              "display_name": "Пищевые отходы",
              "material_state": "prepared_pulp",
              "animal": "unknown",
              "physical_state": "unknown",
              "decay_state": "unknown",
              "bedding": "unknown",
              "quantity": 120,
              "unit": "L",
              "wet_mass_kg": null,
              "volume_l": {
                "low": 120,
                "high": 120
              },
              "ts_mass_kg": null,
              "vs_mass_kg": null,
              "methane_reference_m3": null,
              "carbon_mass_kg": null,
              "nitrogen_mass_kg": null,
              "gas_basis": {
                "temperature_k": 273.15,
                "pressure_pa": 101325,
                "moisture": "unknown"
              },
              "result_level": "LITERATURE_ESTIMATE",
              "result_provenance": null,
              "profile_id": "baek2020-food-pulp",
              "properties_used": {
                "ts_fraction": {
                  "range": {
                    "low": 0.1264,
                    "high": 0.1264
                  },
                  "provenance": "LITERATURE_ESTIMATE",
                  "source_id": "baek2020",
                  "locator": "Table 1",
                  "original_value": "126.4 (SD 4.5)",
                  "original_unit": "g TS/kg wet"
                },
                "vs_fraction_wet": {
                  "range": {
                    "low": 0.1206,
                    "high": 0.1206
                  },
                  "provenance": "LITERATURE_ESTIMATE",
                  "source_id": "baek2020",
                  "locator": "Table 1",
                  "original_value": "120.6 (SD 3.7)",
                  "original_unit": "g VS/kg wet"
                },
                "bmp_ml_g_vs": {
                  "range": {
                    "low": 527.5,
                    "high": 527.5
                  },
                  "provenance": "LITERATURE_ESTIMATE",
                  "source_id": "baek2020",
                  "locator": "Results 3.2, pure FW run 2, PDF page 5",
                  "original_value": "527.5",
                  "original_unit": "L CH4/kg VS"
                }
              },
              "assumptions": [
                "ts_fraction transferred from baek2020-food-pulp",
                "vs_fraction_wet transferred from baek2020-food-pulp",
                "bmp_ml_g_vs transferred from baek2020-food-pulp"
              ],
              "missing": [
                "density_kg_l"
              ],
              "source": {
                "id": "baek2020",
                "doi": "10.3390/ijerph17134737",
                "title": "Treatment of Cattle Manure by Anaerobic Co-Digestion with Food Waste and Pig Manure: Methane Yield and Synergistic Effect",
                "authors": [
                  "Gahyun Baek",
                  "Danbee Kim",
                  "Jinsu Kim",
                  "Hanwoong Kim",
                  "Changsoo Lee"
                ],
                "year": 2020,
                "published_at": "2020-07-01",
                "url": "https://www.mdpi.com/1660-4601/17/13/4737",
                "review_url": "https://pdfs.semanticscholar.org/8c32/8da3dc70a2964a51e0cfd2807c009edd691c.pdf",
                "reviewed_sections": [
                  "Tables 1-2, Methods 2.1-2.3, Results 3.2, Equations 1-2"
                ],
                "verification_stage": "NUMERIC_DATA_VERIFIED",
                "review_method": "Primary article PDF read through browser document extraction. Programmatic mirror download redirected across origins and was not followed. Publisher 429 and PMC CAPTCHA were not bypassed.",
                "conditions": {
                  "temperature_c": 35,
                  "duration_days": 30,
                  "duration_kind": "BMP_INCUBATION",
                  "reactor_type": "250 mL bottles, 200 mL working volume; triplicate and blank corrected",
                  "inoculum": "Digestate from mesophilic food/pig-manure plant; 100 mL inoculum plus 100 mL substrate diluted to 10 g VS/L",
                  "mixing": "daily manual shaking",
                  "gas_basis": {
                    "temperature_k": 273.15,
                    "pressure_pa": 101325,
                    "moisture": "unknown"
                  },
                  "mixing_ratio_basis": "total solids, not wet mass"
                }
              },
              "source_stp_claimed": false,
              "source_basis_missing": false,
              "cn_ratio_reference": 17.9,
              "ph_reference": 4.5,
              "notice": "Single-component literature/measurement reference. A published sample point is not a universal population mean; no unreported SD is invented.",
              "methane_comparable_m3": null,
              "wet_mass_fraction": null,
              "source_conditions": {
                "temperature_c": 35,
                "duration_days": 30,
                "duration_kind": "BMP_INCUBATION",
                "reactor_type": "250 mL bottles, 200 mL working volume; triplicate and blank corrected",
                "inoculum": "Digestate from mesophilic food/pig-manure plant; 100 mL inoculum plus 100 mL substrate diluted to 10 g VS/L",
                "mixing": "daily manual shaking",
                "gas_basis": {
                  "temperature_k": 273.15,
                  "pressure_pa": 101325,
                  "moisture": "unknown"
                },
                "mixing_ratio_basis": "total solids, not wet mass"
              }
            }
          ],
          "methane_m3": null,
          "known_component_subtotal_m3": null,
          "complete": false,
          "wet_mass_kg": null,
          "vs_mass_kg": null,
          "ts_mass_kg": null,
          "gas_basis": {
            "temperature_k": 273.2,
            "pressure_pa": 101325,
            "moisture": "dry",
            "description": "Conditional common dry reference; not a measured mixture output"
          },
          "assumptions": [
            "Physical form and preparation assumed comparable to Ground cafeteria food mainly rice, flour products, soup, vegetables and meat; diluted BMP, not an untreated mixed municipal waste",
            "Literature sample transferred to this batch; actual composition and plant recovery are unmeasured.",
            "ts_fraction transferred from baek2020-food-pulp",
            "vs_fraction_wet transferred from baek2020-food-pulp",
            "bmp_ml_g_vs transferred from baek2020-food-pulp",
            "Unknown source gas moisture treated as dry for the explicitly conditional common-basis calculation.",
            "User hypothetical process input reactor_total_volume_l=250.0; not a measured process change."
          ],
          "missing": [
            "density_kg_l"
          ],
          "biogas": {
            "potential_biogas_m3": null,
            "methane_fraction": null,
            "gas_basis": {
              "temperature_k": 273.2,
              "pressure_pa": 101325,
              "moisture": "dry",
              "description": "Conditional common dry reference; not a measured mixture output"
            },
            "result_provenance": null,
            "status": "needs_input",
            "result_level": null,
            "compatibility": "missing_gas_basis",
            "assumptions": [],
            "scope": "Potential gas corresponding to laboratory methane potential, not collected plant gas. CH4 is part of biogas and must not be added again.",
            "uncertainty": "Independent extrema envelope; unknown correlation and no validated probability coverage."
          },
          "request": {
            "components": [
              {
                "id": "c1",
                "material": "food_waste",
                "material_state": "prepared_pulp",
                "quantity": 120,
                "unit": "L",
                "animal": "unknown",
                "poultry_type": "unknown",
                "reference_profile_id": "baek2020-food-pulp",
                "physical_state": "unknown",
                "decay_state": "unknown",
                "bedding": "unknown",
                "data_mode": "LITERATURE_ESTIMATE",
                "properties": {
                  "density_kg_l": null,
                  "ts_fraction": null,
                  "vs_fraction_wet": null,
                  "vs_fraction_of_ts": null,
                  "ts_kg_l": null,
                  "vs_kg_l": null,
                  "bmp_ml_g_vs": null,
                  "carbon_fraction_wet": null,
                  "nitrogen_fraction_wet": null,
                  "gas_basis": null
                },
                "provenance": "USER_CONFIRMED",
                "evidence": "У меня 120 литров пищевых отходов из столовой, реактор номинально 250 литров. Хочу понять возможный выход метана, подходящий те"
              }
            ],
            "allow_literature_transfer": true,
            "allow_conditional_profiles": false,
            "estimation_mode": "LITERATURE_ESTIMATE",
            "allow_literature_density": true,
            "use_literature_volume_concentrations": true,
            "target_days": null,
            "process_temperature_c": null,
            "kinetic_evidence": null,
            "target_ts_fraction": null,
            "assume_common_dry_gas_basis": true,
            "assume_unreported_gas_basis": false,
            "reactor_total_volume_l": 250,
            "decision": {
              "gas_use": "unknown",
              "gas_basis": null,
              "methane_fraction": null,
              "composition_basis": null,
              "assume_reference_compatibility": false,
              "recovery_fraction": null,
              "thermal_efficiency": null,
              "electrical_efficiency": null,
              "chp_thermal_efficiency": null,
              "chp_electrical_efficiency": null,
              "use_reference_scenarios": true,
              "heating_value_kwh_m3": null,
              "heating_value_type": "LHV",
              "heating_value_basis": null,
              "equipment_evidence": null,
              "reactor": {
                "reactor_working_volume_l": null,
                "headspace_l": null,
                "inoculum_volume_l": null,
                "dilution_water_l": null,
                "resident_liquid_volume_l": null,
                "operating_mode": null,
                "reactor_type": null,
                "engineering_review_confirmed": false,
                "safety_review_required": false,
                "temperature_c": null,
                "initial_temperature_c": null,
                "ambient_temperature_c": null,
                "heated_mass_kg": null,
                "heat_capacity_kj_kg_k": null,
                "heat_loss_coefficient_w_k": null,
                "u_w_m2_k": null,
                "area_m2": null,
                "duration_days": null,
                "heater_efficiency": null,
                "heating_carrier": null,
                "auxiliary_energy_kwh": null,
                "loads": [],
                "loads_complete": false,
                "energy_scope": null,
                "provenance": "HYPOTHETICAL_SCENARIO"
              },
              "quotes": {},
              "price_ids": {},
              "consumer_class": null,
              "tax_basis": null,
              "max_price_age_days": 30,
              "costs": {},
              "all_operating_costs_included": false,
              "include_capital": false,
              "capital_cost_per_batch": null,
              "heat_demand_kwh": null,
              "electricity_demand_kwh": null,
              "assume_full_self_consumption": false,
              "replacement_heat_source": "unknown",
              "gas_sale_technical_confirmed": false,
              "gas_sale_legal_confirmed": false,
              "gas_quality_confirmed": false,
              "gas_storage_transport_confirmed": false,
              "digestate_mass_kg": null,
              "digestate_quality_confirmed": false,
              "digestate_market_allowed": false
            },
            "feeding_period_days": null,
            "total_daily_liquid_feed_l": null,
            "daily_feed_includes_all_liquid": false,
            "inoculum_description": null,
            "inoculum_adapted_temperature_c": null,
            "temperature_control_confirmed": false,
            "mixing_available": null,
            "measured_ph": null,
            "monitoring_confirmed": false,
            "inhibition_warning": false,
            "region": "KZ-Karaganda",
            "region_confirmed": false,
            "online": false,
            "objectives": [
              "methane",
              "stability"
            ]
          },
          "mixture": {
            "components": [
              {
                "id": "c1",
                "material": "food_waste",
                "display_name": "Пищевые отходы",
                "material_state": "prepared_pulp",
                "animal": "unknown",
                "physical_state": "unknown",
                "decay_state": "unknown",
                "bedding": "unknown",
                "quantity": 120,
                "unit": "L",
                "wet_mass_kg": null,
                "volume_l": {
                  "low": 120,
                  "high": 120
                },
                "ts_mass_kg": null,
                "vs_mass_kg": null,
                "methane_reference_m3": null,
                "carbon_mass_kg": null,
                "nitrogen_mass_kg": null,
                "gas_basis": {
                  "temperature_k": 273.15,
                  "pressure_pa": 101325,
                  "moisture": "unknown"
                },
                "result_level": "LITERATURE_ESTIMATE",
                "result_provenance": null,
                "profile_id": "baek2020-food-pulp",
                "properties_used": {
                  "ts_fraction": {
                    "range": {
                      "low": 0.1264,
                      "high": 0.1264
                    },
                    "provenance": "LITERATURE_ESTIMATE",
                    "source_id": "baek2020",
                    "locator": "Table 1",
                    "original_value": "126.4 (SD 4.5)",
                    "original_unit": "g TS/kg wet"
                  },
                  "vs_fraction_wet": {
                    "range": {
                      "low": 0.1206,
                      "high": 0.1206
                    },
                    "provenance": "LITERATURE_ESTIMATE",
                    "source_id": "baek2020",
                    "locator": "Table 1",
                    "original_value": "120.6 (SD 3.7)",
                    "original_unit": "g VS/kg wet"
                  },
                  "bmp_ml_g_vs": {
                    "range": {
                      "low": 527.5,
                      "high": 527.5
                    },
                    "provenance": "LITERATURE_ESTIMATE",
                    "source_id": "baek2020",
                    "locator": "Results 3.2, pure FW run 2, PDF page 5",
                    "original_value": "527.5",
                    "original_unit": "L CH4/kg VS"
                  }
                },
                "assumptions": [
                  "ts_fraction transferred from baek2020-food-pulp",
                  "vs_fraction_wet transferred from baek2020-food-pulp",
                  "bmp_ml_g_vs transferred from baek2020-food-pulp"
                ],
                "missing": [
                  "density_kg_l"
                ],
                "source": {
                  "id": "baek2020",
                  "doi": "10.3390/ijerph17134737",
                  "title": "Treatment of Cattle Manure by Anaerobic Co-Digestion with Food Waste and Pig Manure: Methane Yield and Synergistic Effect",
                  "authors": [
                    "Gahyun Baek",
                    "Danbee Kim",
                    "Jinsu Kim",
                    "Hanwoong Kim",
                    "Changsoo Lee"
                  ],
                  "year": 2020,
                  "published_at": "2020-07-01",
                  "url": "https://www.mdpi.com/1660-4601/17/13/4737",
                  "review_url": "https://pdfs.semanticscholar.org/8c32/8da3dc70a2964a51e0cfd2807c009edd691c.pdf",
                  "reviewed_sections": [
                    "Tables 1-2, Methods 2.1-2.3, Results 3.2, Equations 1-2"
                  ],
                  "verification_stage": "NUMERIC_DATA_VERIFIED",
                  "review_method": "Primary article PDF read through browser document extraction. Programmatic mirror download redirected across origins and was not followed. Publisher 429 and PMC CAPTCHA were not bypassed.",
                  "conditions": {
                    "temperature_c": 35,
                    "duration_days": 30,
                    "duration_kind": "BMP_INCUBATION",
                    "reactor_type": "250 mL bottles, 200 mL working volume; triplicate and blank corrected",
                    "inoculum": "Digestate from mesophilic food/pig-manure plant; 100 mL inoculum plus 100 mL substrate diluted to 10 g VS/L",
                    "mixing": "daily manual shaking",
                    "gas_basis": {
                      "temperature_k": 273.15,
                      "pressure_pa": 101325,
                      "moisture": "unknown"
                    },
                    "mixing_ratio_basis": "total solids, not wet mass"
                  }
                },
                "source_stp_claimed": false,
                "source_basis_missing": false,
                "cn_ratio_reference": 17.9,
                "ph_reference": 4.5,
                "notice": "Single-component literature/measurement reference. A published sample point is not a universal population mean; no unreported SD is invented.",
                "methane_comparable_m3": null,
                "wet_mass_fraction": null,
                "source_conditions": {
                  "temperature_c": 35,
                  "duration_days": 30,
                  "duration_kind": "BMP_INCUBATION",
                  "reactor_type": "250 mL bottles, 200 mL working volume; triplicate and blank corrected",
                  "inoculum": "Digestate from mesophilic food/pig-manure plant; 100 mL inoculum plus 100 mL substrate diluted to 10 g VS/L",
                  "mixing": "daily manual shaking",
                  "gas_basis": {
                    "temperature_k": 273.15,
                    "pressure_pa": 101325,
                    "moisture": "unknown"
                  },
                  "mixing_ratio_basis": "total solids, not wet mass"
                }
              }
            ],
            "total_wet_mass_kg": null,
            "sum_separate_volumes_l": {
              "low": 120,
              "high": 120
            },
            "total_ts_kg": null,
            "total_vs_kg": null,
            "cn_mass_ratio": null,
            "mixture_ph": null,
            "result_provenance": {
              "method": "CALCULATED",
              "inputs": {
                "components": [
                  null
                ]
              },
              "unit": "mixed; see individual fields",
              "sources": [],
              "assumptions": [],
              "limitations": [
                "Derived totals, not independent measurements."
              ],
              "verification": {
                "status": "NOT_PERFORMED",
                "scope": null
              }
            },
            "additive_methane_reference_m3": null,
            "known_component_additive_subtotal_m3": null,
            "complete_methane_reference": false,
            "gas_basis": {
              "temperature_k": 273.2,
              "pressure_pa": 101325,
              "moisture": "dry",
              "description": "Conditional common dry reference; not a measured mixture output"
            },
            "normalization": [],
            "olr_kg_vs_m3_day": null,
            "synergy_factor": null,
            "measured_mixture_bmp": null,
            "result_level": "LITERATURE_ESTIMATE",
            "limitations": [
              "Additive component references are not a validated methane yield of the mixture. No synergy coefficient is assumed.",
              "Known-part subtotal is neither the full mixture prediction nor a lower bound on actual co-digestion yield.",
              "Separate volumes may not add to final packed/liquid mixture volume; verify actual charge.",
              "C/N requires carbon and nitrogen masses. pH cannot be averaged. Batch loading is not a daily OLR.",
              "Sensitivity bounds have no verified probability coverage."
            ]
          },
          "engineering": {
            "status": "REQUIRES_REVIEW",
            "total_volume_l": 250,
            "working_volume_l": null,
            "headspace_required_l": null,
            "known_feed_volume_l": {
              "low": 120,
              "high": 120
            },
            "known_charge_present": true,
            "known_charge_volume_l": {
              "low": 120,
              "high": 120
            },
            "complete_charge_volume_l": null,
            "remaining_total_volume_l": null,
            "fill_fraction": null,
            "missing": [
              "inoculum_volume_l",
              "dilution_water_l",
              "resident_liquid_volume_l",
              "operating_mode",
              "reactor_working_volume_l",
              "headspace_l"
            ],
            "violations": [],
            "warnings": [],
            "feed_plus_water_mass_kg": null,
            "feed_plus_water_ts_fraction": null,
            "feed_plus_water_vs_fraction": null,
            "additional_water_to_target_ts_kg": null,
            "target_ts_fraction": null,
            "water_density_assumption_kg_l": null,
            "necessary_mean_feed_density_kg_l": null,
            "density_constraint_scope": "Necessary mean density for the unvolumed feed to fit after known volumes only. Unmeasured inoculum/water still reduce capacity; this is not measured density or authorization to load.",
            "scope": "Separate volumes are additive bookkeeping, not a packing measurement. Dilution solids exclude inoculum/resident material: their TS/VS are unknown. Water density 1 kg/L is an explicit approximation. Target TS is user-selected, not an operating recommendation.",
            "operation_authorized": false
          },
          "loading": {
            "status": "WORKING_VOLUME_UNKNOWN",
            "simultaneous_load_possible": null,
            "exact_batch_count": null,
            "feedstock_volume_l": 120,
            "reactor_total_volume_l": 250,
            "reactor_working_volume_l": null
          },
          "estimation_mode": "INSUFFICIENT_EVIDENCE",
          "potential_methane_l": null,
          "time_yield": {
            "days": null,
            "methane_l": null,
            "mode": "INSUFFICIENT_EVIDENCE",
            "method": null,
            "missing": [],
            "source_assay_conditions": [
              {
                "temperature_c": 35,
                "duration_days": 30,
                "duration_kind": "BMP_INCUBATION",
                "reactor_type": "250 mL bottles, 200 mL working volume; triplicate and blank corrected",
                "inoculum": "Digestate from mesophilic food/pig-manure plant; 100 mL inoculum plus 100 mL substrate diluted to 10 g VS/L",
                "mixing": "daily manual shaking",
                "gas_basis": {
                  "temperature_k": 273.15,
                  "pressure_pa": 101325,
                  "moisture": "unknown"
                },
                "mixing_ratio_basis": "total solids, not wet mass"
              }
            ]
          }
        }
      ],
      "sources": [
        {
          "id": "baek2020",
          "doi": "10.3390/ijerph17134737",
          "title": "Treatment of Cattle Manure by Anaerobic Co-Digestion with Food Waste and Pig Manure: Methane Yield and Synergistic Effect",
          "authors": [
            "Gahyun Baek",
            "Danbee Kim",
            "Jinsu Kim",
            "Hanwoong Kim",
            "Changsoo Lee"
          ],
          "year": 2020,
          "published_at": "2020-07-01",
          "url": "https://www.mdpi.com/1660-4601/17/13/4737",
          "review_url": "https://pdfs.semanticscholar.org/8c32/8da3dc70a2964a51e0cfd2807c009edd691c.pdf",
          "reviewed_sections": [
            "Tables 1-2, Methods 2.1-2.3, Results 3.2, Equations 1-2"
          ],
          "verification_stage": "NUMERIC_DATA_VERIFIED",
          "review_method": "Primary article PDF read through browser document extraction. Programmatic mirror download redirected across origins and was not followed. Publisher 429 and PMC CAPTCHA were not bypassed.",
          "conditions": {
            "temperature_c": 35,
            "duration_days": 30,
            "duration_kind": "BMP_INCUBATION",
            "reactor_type": "250 mL bottles, 200 mL working volume; triplicate and blank corrected",
            "inoculum": "Digestate from mesophilic food/pig-manure plant; 100 mL inoculum plus 100 mL substrate diluted to 10 g VS/L",
            "mixing": "daily manual shaking",
            "gas_basis": {
              "temperature_k": 273.15,
              "pressure_pa": 101325,
              "moisture": "unknown"
            },
            "mixing_ratio_basis": "total solids, not wet mass"
          }
        }
      ],
      "reactor_total_volume_l": 250,
      "candidate_count": 1,
      "truncated": false,
      "reactor_role": "Vessel capacity is not feed volume, VS mass, daily throughput or methane storage capacity. Working volume, inoculum, dilution and headspace must be checked.",
      "uncertainty": "Points or sensitivity ranges from named samples; no validated prediction interval.",
      "estimation_mode": "INSUFFICIENT_EVIDENCE",
      "target_days": null,
      "answer": "Партия 120 л меньше номинальных 250 л; рабочий объём не указан, загрузка и выход за цикл не подтверждены. Не заполняйте реактор до краёв: учтите воду, инокулят, остаточную жидкость и газовое пространство.\n\nЧисленный диапазон не обоснован доступными совместимыми данными. Не хватает: плотность сырья.\n\nНоминальная вместимость не равна рабочему объёму. Возможность загрузки сырья вместе с водой и инокулятом проверяется отдельно; расчёт всей партии не является выходом одного цикла.\n\nЧто измерить: физическую форму и разбавление, массу или плотность, TS и VS на указанной основе, BMP, температуру и кривую накопления метана; уточнить рабочий объём, воду и инокулят.",
      "scenario_process_inputs": {
        "reactor_total_volume_l": 250
      }
    }
  }
]
`

### Qwen call: compact_nlu

`json
{
  "response": {
    "language": "ru",
    "material_span": "пищевых отходов",
    "requested_tasks": [
      "methane",
      "temperature",
      "economics"
    ]
  },
  "metrics": [
    {
      "input_characters": 552,
      "request_bytes": 1674,
      "status": "ok",
      "generation_received": true,
      "prompt_tokens": 201,
      "output_tokens": 46,
      "done_reason": "stop",
      "load_seconds": 3.2175452,
      "generation_seconds": 0.642997,
      "tokens_per_second": 71.5399916329314,
      "latency_seconds": 4.266530699998839,
      "raw_public_response": "{\n  \"language\": \"ru\",\n  \"material_span\": \"пищевых отходов\",\n  \"requested_tasks\": [\n    \"methane\",\n    \"temperature\",\n    \"economics\"\n  ]\n}",
      "nlu_validation": "valid_compact_grounded"
    }
  ]
}
`

### Qwen call: tool_selection

`json
{
  "response": {
    "action": "tool",
    "tool": "search_scientific_sources",
    "arguments": {
      "query": "methane yield from food waste, reactor volume 250L, 120L load, temperature recommendation, risk of acidification"
    },
    "purpose": "Identify relevant scientific evidence for methane yield, temperature recommendation, and acidification risk for food waste in a 250L reactor",
    "ready_after_tool": true
  },
  "metrics": [
    {
      "input_characters": 4150,
      "request_bytes": 5988,
      "status": "ok",
      "generation_received": true,
      "prompt_tokens": 1173,
      "output_tokens": 104,
      "done_reason": "stop",
      "load_seconds": 0.0079626,
      "generation_seconds": 1.241722,
      "tokens_per_second": 83.7546568394536,
      "latency_seconds": 1.9179084999923361,
      "raw_public_response": "{\n  \"action\": \"tool\",\n  \"tool\": \"search_scientific_sources\",\n  \"arguments\": {\n    \"query\": \"methane yield from food waste, reactor volume 250L, 120L load, temperature recommendation, risk of acidification\"\n  },\n  \"purpose\": \"Identify relevant scientific evidence for methane yield, temperature recommendation, and acidification risk for food waste in a 250L reactor\",\n  \"ready_after_tool\": true\n}"
    }
  ]
}
`

### Qwen call: tool_selection

`json
{
  "response": {
    "action": "tool",
    "tool": "assess_process_evidence",
    "arguments": {
      "topics": [
        "temperature",
        "temperature"
      ]
    },
    "purpose": "Assess temperature recommendations and risk of acidification based on confirmed inputs and scientific evidence",
    "ready_after_tool": true
  },
  "metrics": [
    {
      "input_characters": 9589,
      "request_bytes": 12877,
      "status": "ok",
      "generation_received": true,
      "prompt_tokens": 3028,
      "output_tokens": 69,
      "done_reason": "stop",
      "load_seconds": 0.0071808,
      "generation_seconds": 0.938907,
      "tokens_per_second": 73.48970664826228,
      "latency_seconds": 2.1749923000024864,
      "raw_public_response": "{\n  \"action\": \"tool\",\n  \"tool\": \"assess_process_evidence\",\n  \"arguments\": {\n    \"topics\": [\"temperature\", \"temperature\"]\n  },\n  \"purpose\": \"Assess temperature recommendations and risk of acidification based on confirmed inputs and scientific evidence\",\n  \"ready_after_tool\": true\n}"
    }
  ]
}
`

### Qwen call: scientific_synthesis

`json
{
  "response": {
    "conclusion": "Метановый потенциал не определен, температура мезофильная, но оптимум не проверен.",
    "explanation": "Метан не рассчитан, температура изучена, но оптимум не подтвержден, затраты неизвестны."
  },
  "metrics": [
    {
      "input_characters": 1643,
      "request_bytes": 3649,
      "status": "ok",
      "generation_received": true,
      "prompt_tokens": 623,
      "output_tokens": 82,
      "done_reason": "stop",
      "load_seconds": 0.0063698,
      "generation_seconds": 0.930211,
      "tokens_per_second": 88.15204292359475,
      "latency_seconds": 1.4517526999989059,
      "raw_public_response": "{\n  \"conclusion\": \"Метановый потенциал не определен, температура мезофильная, но оптимум не проверен.\",\n  \"explanation\": \"Метан не рассчитан, температура изучена, но оптимум не подтвержден, затраты неизвестны.\"\n}"
    }
  ]
}
`

### Verifier, synthesis and rejection traces

`json
{
  "final_author": "qwen_verified",
  "verification": {
    "status": "ok",
    "outcome": "passed",
    "checks": [
      {
        "check": "no_actuation_authorized",
        "passed": true,
        "scenario": "s1"
      },
      {
        "check": "literature_value_matches_reviewed_source_ts_fraction",
        "passed": true,
        "scenario": "s1",
        "component": "c1"
      },
      {
        "check": "literature_value_matches_reviewed_source_vs_fraction_wet",
        "passed": true,
        "scenario": "s1",
        "component": "c1"
      },
      {
        "check": "literature_value_matches_reviewed_source_bmp_ml_g_vs",
        "passed": true,
        "scenario": "s1",
        "component": "c1"
      },
      {
        "check": "profile_identity_and_form",
        "passed": true,
        "scenario": "s1",
        "component": "c1"
      },
      {
        "check": "source_belongs_to_profile",
        "passed": true,
        "scenario": "s1",
        "component": "c1"
      }
    ],
    "checked": true,
    "all_checks_passed": true,
    "unsupported_tools": [],
    "missing_verification_evidence": [],
    "scope": "Arithmetic, source identity, material/form, energy allocation and cost completeness; not biological validation, interval coverage or operating safety."
  },
  "scientific_answer_verification": {
    "status": "passed",
    "checked": true,
    "all_checks_passed": true,
    "checks": [
      {
        "check": "no_unverified_timed_methane_amount",
        "passed": true
      },
      {
        "check": "estimate_arithmetic_and_source_scope_checked",
        "passed": true
      },
      {
        "check": "literature_estimate_not_measured_output",
        "passed": true
      },
      {
        "check": "estimate_not_claimed_as_measured_production",
        "passed": true
      },
      {
        "check": "temperature_discussion_not_actuation",
        "passed": true
      },
      {
        "check": "no_known_scientific_contradiction",
        "passed": true
      }
    ],
    "components": {
      "arithmetic": {
        "status": "passed",
        "failed_checks": []
      },
      "provenance": {
        "status": "passed",
        "failed_checks": []
      },
      "scientific_interpretation": {
        "status": "passed",
        "failed_checks": []
      },
      "completeness": {
        "status": "not_applicable",
        "failed_checks": []
      }
    },
    "contradictions": [],
    "assertions": [],
    "scope": "Reviewed-source identity and limited RU/KK/EN proposition, negation and target-scope rules; not exhaustive factual verification or biological validation."
  },
  "quantity_verification": {
    "status": "not_applicable",
    "checked": false,
    "claims": [],
    "scope": "Last model draft: typed numeric grounding and supported unit conversion, not biological verification."
  },
  "model_synthesis": {
    "conclusion": "Метановый потенциал не определен, температура мезофильная, но оптимум не проверен.",
    "explanation": "Метан не рассчитан, температура изучена, но оптимум не подтвержден, затраты неизвестны.",
    "limitations": [],
    "next_question": "Сырьё жидкое и разбавленное, плотное или содержит подстилку?",
    "evidence_ids": [
      "temperature.discussion"
    ],
    "decision": "not_applicable"
  },
  "synthesis_rejections": [],
  "synthesis_review_history": [
    {
      "attempt": 1,
      "status": "passed",
      "issues": [],
      "feedback": []
    }
  ],
  "diagnostics": [
    {
      "stage": "typed_consultation_tasks",
      "inputs": {
        "substrate": "food_waste",
        "feedstock_volume_l": 120,
        "reactor_volume_l": null,
        "temperature_c": null,
        "operating_mode": null,
        "duration_days": null,
        "intended_use": "unknown",
        "region": null,
        "measured_parameters": {},
        "literature_assumptions": [],
        "components": [
          {
            "id": "c1",
            "material": "food_waste",
            "material_state": "unknown",
            "quantity": 120,
            "unit": "L",
            "animal": "unknown",
            "poultry_type": "unknown",
            "reference_profile_id": null,
            "physical_state": "unknown",
            "decay_state": "unknown",
            "bedding": "unknown",
            "data_mode": "LITERATURE_ESTIMATE",
            "properties": {
              "density_kg_l": null,
              "ts_fraction": null,
              "vs_fraction_wet": null,
              "vs_fraction_of_ts": null,
              "ts_kg_l": null,
              "vs_kg_l": null,
              "bmp_ml_g_vs": null,
              "carbon_fraction_wet": null,
              "nitrogen_fraction_wet": null,
              "gas_basis": null
            },
            "provenance": "USER_CONFIRMED",
            "evidence": "У меня 120 литров пищевых отходов из столовой, реактор номинально 250 литров. Хочу понять возможный выход метана, подходящий те"
          }
        ],
        "tasks": [
          "methane",
          "temperature"
        ]
      },
      "required_tools": [
        "search_scientific_sources",
        "estimate_methane_yield",
        "assess_process_evidence"
      ]
    },
    {
      "stage": "required_evidence_preflight",
      "tool": "estimate_methane_yield",
      "reason": "planning_stage_budget_reserved_for_synthesis"
    },
    {
      "stage": "typed_result_publication",
      "evidence_origin": "python_tool_results",
      "decision_origin": "economic_constraints",
      "model_role": "qualitative_explanation",
      "raw_model_explanation": {
        "conclusion": "Метановый потенциал не определен, температура мезофильная, но оптимум не проверен.",
        "explanation": "Метан не рассчитан, температура изучена, но оптимум не подтвержден, затраты неизвестны."
      }
    }
  ]
}
`

### Observed resources (samples, not guaranteed peaks)

`json
{
  "case": "food",
  "model_status": "ACCEPTED_PENDING_INDEPENDENT_REVIEW",
  "actual_calls": 4,
  "model_phases": [
    "compact_nlu",
    "tool_selection",
    "tool_selection",
    "scientific_synthesis"
  ],
  "admission_ram_mib": 6689.5,
  "minimum_observed_free_ram_mib": 5368.3,
  "maximum_observed_commit_mib": 17336.4,
  "minimum_observed_commit_headroom_mib": 18296.1,
  "maximum_observed_vram_mib": 3848,
  "maximum_observed_gpu_c": 67,
  "elapsed_seconds": 10.589,
  "unload": {
    "status": "UNLOADED",
    "elapsed_seconds": 0.32
  },
  "guard_status": "completed",
  "admission_issues": [],
  "history_restored": true
}
`

## mixture

### User question

Хочу совместно сбраживать коровий навоз и пищевые остатки столовой. Количества пока не выбрал. Какие плюсы и риски у такой смеси, можно ли заранее оценить метан и с каких данных начать? Не назначай универсальную долю смешивания без обоснования.

### Delivered answer (verbatim)

Для научной оценки не хватает исходных данных:

Для пересчёта профиля на вашу партию нужна её масса или объём.

Какова масса партии в килограммах?

### Structured display (verbatim)

{
  "paragraphs": [
    "Для научной оценки не хватает исходных данных:",
    "Для пересчёта профиля на вашу партию нужна её масса или объём."
  ],
  "sections": [],
  "question": {
    "id": "batch-quantity",
    "text": "Какова масса партии в килограммах?",
    "fields": [
      "quantity",
      "unit"
    ],
    "options": [],
    "reason": "Quantity is the missing input needed to scale the available scientific evidence."
  },
  "sources": [],
  "modes": [
    "explicit_engine_partial"
  ],
  "assumptions": [
    "market_region"
  ]
}

### Actual tools and their origins

`json
[
  {
    "tool": "assess_substrate_potential",
    "status": "needs_input",
    "input_origin": "validated_scientific_state",
    "query": null,
    "result": {
      "status": "needs_input",
      "message": "The local profile index was inspected; specific missing batch inputs are listed.",
      "missing": [
        "batch_quantity"
      ],
      "scenarios": [],
      "catalog_checked": true,
      "available_profile_ids": [
        "oliveira-rm1-2025-v1",
        "baek2020-bedded-cattle",
        "eftaxias2024-cattle"
      ],
      "known_quantity": null
    }
  }
]
`

### Qwen call: compact_nlu

`json
{
  "response": {
    "language": "ru",
    "material_span": "коровий",
    "requested_tasks": [
      "methane",
      "temperature",
      "economics"
    ]
  },
  "metrics": [
    {
      "input_characters": 551,
      "request_bytes": 1664,
      "status": "ok",
      "generation_received": true,
      "prompt_tokens": 205,
      "output_tokens": 43,
      "done_reason": "stop",
      "load_seconds": 2.1131863,
      "generation_seconds": 0.598345,
      "tokens_per_second": 71.86489399928135,
      "latency_seconds": 2.9795168999989983,
      "raw_public_response": "{\n  \"language\": \"ru\",\n  \"material_span\": \"коровий\", \"requested_tasks\": [\n    \"methane\",\n    \"temperature\",\n    \"economics\"\n  ]\n}",
      "nlu_validation": "valid_compact_grounded"
    }
  ]
}
`

### Qwen call: tool_selection

`json
{
  "response": {
    "action": "tool",
    "tool": "assess_substrate_potential",
    "arguments": {
      "query": "cattle_manure, food_waste",
      "topics": [
        "duration",
        "temperature"
      ]
    },
    "purpose": "assess_substrate_potential",
    "ready_after_tool": true
  },
  "metrics": [
    {
      "input_characters": 2595,
      "request_bytes": 3994,
      "status": "ok",
      "generation_received": true,
      "prompt_tokens": 695,
      "output_tokens": 77,
      "done_reason": "stop",
      "load_seconds": 0.0074613,
      "generation_seconds": 1.031684,
      "tokens_per_second": 74.63525653203888,
      "latency_seconds": 1.4313450000045123,
      "raw_public_response": "{\n  \"action\": \"tool\",\n  \"tool\": \"assess_substrate_potential\",\n  \"arguments\": {\n    \"query\": \"cattle_manure, food_waste\",\n    \"topics\": [\"duration\", \"temperature\"]\n  },\n  \"purpose\": \"assess_substrate_potential\",\n  \"ready_after_tool\": true\n}"
    }
  ]
}
`

### Verifier, synthesis and rejection traces

`json
{
  "final_author": "verified_engine_partial",
  "verification": {
    "status": "insufficient_evidence",
    "outcome": "insufficient_evidence",
    "checks": [],
    "checked": false,
    "all_checks_passed": false,
    "unsupported_tools": [],
    "missing_verification_evidence": [
      "assess_substrate_potential.scenarios"
    ],
    "scope": "Arithmetic, source identity, material/form, energy allocation and cost completeness; not biological validation, interval coverage or operating safety."
  },
  "scientific_answer_verification": {
    "status": "not_applicable",
    "checked": false,
    "checks": [],
    "all_checks_passed": false
  },
  "quantity_verification": {
    "status": "not_applicable",
    "checked": false,
    "claims": [],
    "scope": "Last model draft: typed numeric grounding and supported unit conversion, not biological verification."
  },
  "model_synthesis": null,
  "synthesis_rejections": [],
  "synthesis_review_history": [],
  "diagnostics": []
}
`

### Observed resources (samples, not guaranteed peaks)

`json
{
  "case": "mixture",
  "model_status": "REJECTED_OR_FALLBACK",
  "actual_calls": 2,
  "model_phases": [
    "compact_nlu",
    "tool_selection"
  ],
  "admission_ram_mib": 6679.3,
  "minimum_observed_free_ram_mib": 5783.3,
  "maximum_observed_commit_mib": 16963.9,
  "minimum_observed_commit_headroom_mib": 18668.6,
  "maximum_observed_vram_mib": 3881,
  "maximum_observed_gpu_c": 69,
  "elapsed_seconds": 4.929,
  "unload": {
    "status": "UNLOADED",
    "elapsed_seconds": 0.216
  },
  "guard_status": "completed",
  "admission_issues": [],
  "history_restored": true
}
`

## economics

### User question

Для условного сценария есть 62 литра жидкого коровьего навоза и реактор 180 литров. Сосед предлагает 900 тенге за всю партию. Альтернатива — биогаз для отопления вместо электронагрева по 24 тенге за кВт·ч. Это мои сценарные входные данные, не проверенные рыночные цены. Как сравнить варианты и найти максимальные общие расходы переработки для безубыточности относительно продажи? Теплопотери и фактический расход на подогрев ещё неизвестны.

### Delivered answer (verbatim)

Qwen3 4B сейчас недоступна: проверка ресурсов не пройдена. Ниже результаты Python и научной базы без языковой модели. Свободная RAM 6651.3 MiB, требуется 6656 MiB.

Предварительная оценка по доступным данным:

Валовая цена предложения за всю партию: 24 KZT (условный сценарий). Валовая цена до расходов; это не прибыль.

### Structured display (verbatim)

{
  "paragraphs": [
    "Qwen3 4B сейчас недоступна: проверка ресурсов не пройдена. Ниже результаты Python и научной базы без языковой модели. Свободная RAM 6651.3 MiB, требуется 6656 MiB.",
    "Предварительная оценка по доступным данным:",
    "Валовая цена предложения за всю партию: 24 KZT (условный сценарий). Валовая цена до расходов; это не прибыль."
  ],
  "sections": [],
  "question": null,
  "sources": [],
  "modes": [
    "explicit_engine_partial"
  ],
  "assumptions": [
    "market_region",
    "material",
    "physical_state",
    "material_state",
    "market_commodity",
    "quantity",
    "unit",
    "reactor_total_volume_l",
    "intended_use",
    "sale_offer_amount",
    "sale_offer_currency",
    "sale_offer_scope"
  ]
}

### Actual tools and their origins

`json
[
  {
    "tool": "explicit_calculations",
    "status": "ok",
    "input_origin": "typed_inputs_deterministic",
    "result": {
      "status": "ok",
      "calculations": [
        {
          "id": "explicit.sale_gross_value_kzt",
          "kind": "sale_gross_value_kzt",
          "label": "Валовая цена предложения за всю партию",
          "value": 24,
          "unit": "KZT",
          "formula": "quoted amount for the whole batch",
          "inputs": {
            "sale_offer_amount": {
              "value": 24,
              "unit": "KZT/batch",
              "provenance": "ASSUMED_FOR_SCENARIO",
              "evidence": "по 24 тенге"
            },
            "sale_offer_scope": {
              "value": "batch",
              "unit": null,
              "provenance": "ASSUMED_FOR_SCENARIO",
              "evidence": "Для условного сценария есть 62 литра жидкого коровьего навоза и реактор 180 литров. Сосед предлагает 900 тенге за всю партию. Альтернатива — биогаз для отопления вместо электронагрева по 24 тенге за кВт·ч. Это мои сценарные входные данные, не проверенные рыночные цены. Как сравнить варианты и найти максимальные общие расходы переработки для безубыточности относительно продажи? Теплопотери и фактический расход на подогрев ещё неизвестны."
            },
            "sale_offer_currency": {
              "value": "KZT",
              "unit": null,
              "provenance": "ASSUMED_FOR_SCENARIO",
              "evidence": "по 24 тенге"
            }
          },
          "result_provenance": {
            "method": "CALCULATED",
            "inputs": {
              "sale_offer_amount": {
                "value": 24,
                "unit": "KZT/batch",
                "provenance": "ASSUMED_FOR_SCENARIO",
                "evidence": "по 24 тенге"
              },
              "sale_offer_scope": {
                "value": "batch",
                "unit": null,
                "provenance": "ASSUMED_FOR_SCENARIO",
                "evidence": "Для условного сценария есть 62 литра жидкого коровьего навоза и реактор 180 литров. Сосед предлагает 900 тенге за всю партию. Альтернатива — биогаз для отопления вместо электронагрева по 24 тенге за кВт·ч. Это мои сценарные входные данные, не проверенные рыночные цены. Как сравнить варианты и найти максимальные общие расходы переработки для безубыточности относительно продажи? Теплопотери и фактический расход на подогрев ещё неизвестны."
              },
              "sale_offer_currency": {
                "value": "KZT",
                "unit": null,
                "provenance": "ASSUMED_FOR_SCENARIO",
                "evidence": "по 24 тенге"
              }
            },
            "unit": "KZT",
            "sources": [],
            "assumptions": [
              "User-supplied scenario assumptions."
            ],
            "limitations": [
              "Calculated value; not an independent measurement."
            ],
            "verification": {
              "status": "NOT_PERFORMED",
              "scope": null
            }
          },
          "provenance": "ASSUMED_FOR_SCENARIO",
          "level": "SCENARIO_ASSUMPTION",
          "description": "Валовая цена до расходов; это не прибыль."
        }
      ]
    }
  },
  {
    "tool": "get_market_prices",
    "status": "needs_input",
    "input_origin": "controller_required_evidence",
    "result": {
      "status": "needs_input",
      "missing": [
        "verified_market_observations"
      ],
      "region": "KZ-Karaganda",
      "prices": [],
      "geographic_scope_warning": null,
      "sources": [],
      "message": "В регионе нет подходящих сохранённых цен; нужен проверенный импорт или успешное обновление источника."
    }
  }
]
`

### Verifier, synthesis and rejection traces

`json
{
  "final_author": "verified_engine_partial",
  "verification": {
    "status": "ok",
    "outcome": "passed",
    "checks": [
      {
        "check": "explicit_calculation_arithmetic",
        "passed": true,
        "calculation_id": "explicit.sale_gross_value_kzt",
        "kind": "sale_gross_value_kzt",
        "expected": 24,
        "observed": 24
      }
    ],
    "checked": true,
    "all_checks_passed": true,
    "unsupported_tools": [],
    "missing_verification_evidence": [],
    "scope": "Arithmetic, source identity, material/form, energy allocation and cost completeness; not biological validation, interval coverage or operating safety."
  },
  "scientific_answer_verification": {
    "status": "not_applicable",
    "checked": false,
    "checks": [],
    "all_checks_passed": false
  },
  "quantity_verification": {
    "status": "not_applicable",
    "checked": false,
    "claims": [],
    "scope": "Last model draft: typed numeric grounding and supported unit conversion, not biological verification."
  },
  "model_synthesis": null,
  "synthesis_rejections": [],
  "synthesis_review_history": [],
  "diagnostics": [
    {
      "stage": "selection",
      "error": "No valid active provider after NLU"
    },
    {
      "stage": "required_evidence_preflight",
      "tool": "get_market_prices",
      "reason": "planning_budget_or_provider_error"
    },
    {
      "stage": "synthesis",
      "error": "No valid active provider after NLU"
    }
  ]
}
`

### Observed resources (samples, not guaranteed peaks)

`json
{
  "case": "economics",
  "model_status": "NO_MODEL_GENERATION",
  "actual_calls": 0,
  "model_phases": [],
  "admission_ram_mib": 6651.3,
  "minimum_observed_free_ram_mib": 6651.3,
  "maximum_observed_commit_mib": 12591.1,
  "minimum_observed_commit_headroom_mib": 23041.4,
  "maximum_observed_vram_mib": 600,
  "maximum_observed_gpu_c": 65,
  "elapsed_seconds": 0.236,
  "unload": null,
  "guard_status": "blocked",
  "admission_issues": [
    "ram_limit"
  ],
  "history_restored": true
}
`
