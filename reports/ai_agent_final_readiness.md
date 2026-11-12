# BioReactor AI — AI Agent Final Readiness

## Latest third-turn completion — 2026-11-12

Same-session real-Qwen three-turn technical check completed: only third question newly executed, first two retained. New Chrome/FastAPI/Ollama job4real calls/4tools, qwen_verified without fallback; context25°C hypothetical/78L/200L preserved; comparison/reload/persistence pass.9.361s, maxGPU59°C/VRAM4156MiB, minfreeRAM5564.2, unload0.219s, models empty. All mandatory guards unchanged. Optional baseline+2 reproducibility criterion remains available by flag, not conflated with hardware safety. Full answer and independent review: [third_turn_completion_20261112.md](third_turn_completion_20261112.md). Science is conditional; unknown costs/heat inputs and generic Qwen prose limit usefulness. Overall FIRO NOT READY; broader independent acceptance/holdout still absent.

## Latest freed-RAM real repeat — 2026-11-12

Two real Chrome/Qwen4B turns PASSED in one session, without fallback; context/reload/unload correct. Third not sent due extra bounded cooldown criterion62°C while stable64°C; main resource admission was green and RAM6892MiB. Do not call this RAM shortage or an unsafe hardware temperature. No rules changed mid-run. Qwen qualitative prose remains generic/repetitive, so natural-language usefulness PARTIAL despite correct tool-backed output. Full answers, metrics and exact distinction: [three_turn_qwen_freed_ram_20261112.md](three_turn_qwen_freed_ram_20261112.md). Overall FIRO NOT READY; three-turn acceptance incomplete.

## Latest three-turn Qwen attempt — 2026-11-12

**BLOCKED / FIRO NOT READY.** New real browser admission5548.5MiB against6656; no inference on any of the three new turns. Do not attribute the previous cancellation to RAM: that old job lacked saved guard telemetry. Confirmed USER_CANCELLED misclassification for internal stops fixed,91 relevant tests passed. Full actual no_llm browser dialogue/reload passed separately; it is not real-Qwen acceptance. Exact original log evidence, current deficit1107.5MiB, full Python answers, tools, scientific review and next condition: [three_turn_qwen_retest_20261112.md](three_turn_qwen_retest_20261112.md). No thresholds weakened or user apps closed.

## Latest checkpoint — web-only correction, 2026-11-12

FIRO NOT READY. Parent Tkinter entry redirected to existing web Chat; scientific modules/data retained. Thermal comparisons preserve assumed25°C and separate source/recommended temperatures. Relevant131tests PASSED; actual no_llm browser three-turn scenario/reload PASSED. On updated backend real Qwen turn1PASS, turn2CANCELLED, turn3NOT_RUN; exact cancellation cause not retained by previous guard, now durable audits/events added and deterministic tests passed. Do not count Python/browser success as full model acceptance. See [web_only_consultant_fix.md](web_only_consultant_fix.md) for exact commands, raw answers, stale-backend evidence and limitations. Production/gates unchanged.

## Previous checkpoint — guarded interactive farmer Chat, 2026-11-12

**Overall FIRO NOT READY. Experimental single-turn Chat functionally confirmed.** The missing safe UI binding is now implemented under existing `--firo-demo`; production configuration unchanged. Real Chrome → FastAPI8770 → Runtime9 → Ollama4B completed a new arbitrary52L/180L question with all three tasks, four tools and four real model calls. Checked Qwen explanation + Python results delivered without fallback and restored after reload;13browser assertions passed. Resource scope13.319s, min RAM5877.4MiB, max commit17328.5MiB/VRAM3856MiB/GPU72°C, targeted unload0.195s, models empty. Region remains correctly unconfirmed.

Final relevant aggregate484PASSED (not added to earlier counts), frontend81PASSED/build PASSED. Coordinated task semantics added to compact128-token NLU; no invented facts allowed. Semantic guards now reject the previously missed potential/actual-production/optimum errors. Controller reuses existing QA safety policy, per-job cancellation, budget and unload; blocked requests retain Python analysis instead of falling back to8B.

Real follow-up25°C: **model BLOCKED** at6650.4MiB<6656, no inference. Python retained52L/180L and recalculated compatible source scenario; delivered/restored correctly (28browser checks). Previous RAM-blocked6593.2MiB attempt and first partial browser answer/test defects retained. No more loads attempted. New model dialogue and independent holdout remain incomplete; commercial price/thermal applicability still limited. Exact commands, full raw/delivered answers and all statuses: [farmer_consultant_20261112.md](farmer_consultant_20261112.md), latest continuation section.

## Previous checkpoint — farmer consultation, 2026-11-12

**NOT READY / acceptance PARTIAL.** This supersedes pending statements in historical entries only for work documented in [farmer_consultant_20261112.md](farmer_consultant_20261112.md); historical acceptance/holdout limitations remain. Current relevant deterministic aggregate420PASSED; frontend81PASSED/build PASSED. Six real Qwen4B single-turn farming requests completed through common FastAPI Chat jobs with real Ollama HTTP. Independent content review still identifies ambiguous/overly general prose despite automatic verification. Second dialogue turn stopped at unchanged82°C GPU boundary, CANCELLED with no reply; unload confirmed, no further GPU attempts. Final region-provenance correction tested deterministically, not live-retested.

Chrome28checks cover genuine real-Qwen history restoration/display/mobile; fresh universal-Chat browser inference and blind independent holdout NOT RUN. QA4B profile stays isolated, production not switched, models not trained. Six exported corpus records are review candidates only, zero eligible for training. Next priorities: evidence/unknown-result consistency, useful clarification, finish interrupted dialogue after cooling and normal admission, safe UI provider binding, commercial tariff/thermal applicability, independent acceptance.

## Historical entries

> 2026-11-10, provenance: итог текущего подэтапа и карта источников — `reports/scientific_provenance_integrity.md`. Полный набор **692 passed / 1 warning**; UI-компоненты **80 passed**, typecheck PASS. Исторический helper pytest исправлен. Подэтап **PARTIALLY FIXED**: полная проверка всех legacy полей и ML через Chat endpoint не завершена; real Qwen и Browser E2E не выполнены. Общий статус **NOT READY**.

> Дополнение 2026-11-10: подробный текущий статус — в `reports/parallel_development_readiness_20261110.md`. После исправления автоматического перевода объёма в массу и обновления затронутых проверок повторный полный набор дал **687 passed, 2 warnings**, включая один ошибочно собранный pytest вспомогательный элемент. Промежуточный результат **661 passed / 26 failed** и изменения контрактов сохранены в отдельном отчёте. qwen2.5:1.5b **BLOCKED** по RAM, реальная генерация и текущая браузерная проверка не выполнялись. Маркировка рассчитанных результатов из измеренных входов требует отдельного аудита. Вердикт остаётся **NOT READY**.

**Дата проверки:** 2026-11-09  
**Вердикт:** **NOT READY**  
**Область:** аудит существующего агента, исправление воспроизведённых регрессий, полный детерминированный набор. Это не релиз и не заявление о промышленной готовности.

## Результат этой сессии

Полный тестовый набор завершился успешно: **653 passed, 0 failed, 0 deselected**, 86.33 s. Найдены и исправлены два общих дефекта вывода ограничения вместимости и один устаревший тест каталога:

- В кратких и многоходовых ответах повторялась длинная оговорка о рабочем объёме; сокращена каноническая формулировка, а в `advanced_conversation` удалено дублирование. Сохранились предупреждения, что номинальный объём не подтверждает загрузку, нельзя заполнять реактор до краёв, а выход за цикл неизвестен.
- Сравнение объёмов около равенства номиналу зависело от точного равенства float. Для отображения равенства добавлен абсолютный допуск `1e-9` л; равенство не считается подтверждением допустимой загрузки. Для полной номинальной загрузки прямо указывается отсутствие места для инокулята и газового пространства.
- Тест каталога ожидал 15 распознаваемых категорий, хотя рабочий каталог уже содержит 20; пять дополнительных названий не получают автоматически численные профили. Тест теперь отдельно проверяет 20 распознаваемых категорий, 18 одобренных записей профилей и один полный набор density/TS/VS/BMP.

Изменены в рамках этого подэтапа: `src/optimizer/capacity.py`, `src/agent/advanced_conversation.py`, `tests/test_advanced_conversation.py`, `tests/test_complete_economics.py`, `tests/test_substrate_advisor.py`, `tests/test_reactor_capacity_validation.py`. Исторические данные, модели BMP и SQLite не переобучались и не удалялись.

## Статус по уровням

| Область | Статус | Фактическое основание |
|---|---|---|
| Проверка вместимости 470/114, 47/114, равенство и multi-turn | **PASS — детерминированный backend** | End-to-end тесты проходят через `POST /api/dashboard/chat/sessions/{id}/jobs`; сохранённая история и единицы проверены. Добавлена защита сравнения на границе float. |
| Доставка и восстановление в браузере после последних изменений | **NOT RUN** | Ранее записанный браузерный тест persistence прошёл 9/9 на одном сценарии, но после последних изменений он не повторялся. Текущий запуск Dashboard и GET-запросы не являются проверкой отображения ответа после отправки/refresh. |
| Асинхронная отмена реального Ollama inference | **INCONCLUSIVE** | В последнем ограниченном прогоне реальный `qwen3:8b` завершил job до отправки Cancel; Cancel не был отправлен. Отмена реального генератора не доказана. |
| Legacy synchronous chat | **KNOWN LIMITATION / NOT READY** | `POST /api/dashboard/chat/sessions/{id}/messages` работает через legacy runtime, вне `JobRuntime`; у него нет job cancellation. В финальном acceptance один ответ этого маршрута был семантически ошибочен. |
| Текущий Runtime 9 на реальной Qwen | **FAIL / PARTIAL** | Сохранённый прогон `rc3_development_live.json`: 23 из 31 development-сценариев, 10 автоматических контрактных PASS; синтез Qwen отмечен в 14 случаях. Это контрактные проверки, не полная научная оценка. |
| Независимая научная проверка ответов | **INSUFFICIENT** | `manual_review.json` содержит 4 рассмотренных ответа: 1 `false`, 2 `partial`, 1 `pending_full_review`; review выполнен агентом разработки, не ослеплённой независимой группой. |
| Независимый held-out тест Runtime 9 | **NOT RUN** | В `stage9_cases.json` есть 31 development и 20 held-out; файлов `held_out_live.json` и `held_out_summary.json` нет. Held-out не использовался для настройки в этой сессии. Отдельного validation split нет. |
| Сохранённые BMP bundles | **PASS — совместимость по тесту** | Полный набор включает `test_real_model_and_methane_chain_both_artifacts`, который проверяет оба сохранённых bundle и связанные расчёты. Это совместимость API, не подтверждение качества на новой лаборатории. |
| Научная применимость BMP | **LIMITED** | Историческая Stage 1.5 оценка CatBoost: MAE 80.38 мл CH₄/г VS, RMSE 131.99, R² 0.173 на тесте из пяти лабораторий. Модель в этой сессии не переобучалась. Эти показатели не подтверждают точность для новых лабораторий/субстратов. |
| Каталог научных профилей | **PARTIAL COVERAGE** | Сейчас распознаются 20 категорий; 18 одобренных записей профилей относятся к 8 материалам; только 1 профиль имеет полный density/TS/VS/BMP набор. Категория названия не означает наличие численного профиля. |
| Текущая экономика/рынок | **PARTIAL** | Условные сценарии и неполные затраты маркируются; исторические market observations включают устаревшие записи. В этой сессии сбор/свежесть реальных рыночных источников не перепроверялись. Валовая ценность не равна чистой прибыли. |
| Измерения и безопасность | **PARTIAL** | В тестах actuator access выключен; датчики не подтверждают реальные параметры реактора. Литературная оценка, условный сценарий, ML-прогноз и измерение остаются разными уровнями данных, но вся поверхность ответов не проверена на реальной модели. |

## Интерпретация исторических acceptance-результатов

Последний сохранённый acceptance-отчёт датирован 2026-11-07: 19/20 сценариев завершены — **17 FAIL, 1 PARTIAL, 2 PASS**; сценарий 20 остановлен на ходе 1/5. Историческое «20/20 Chrome» означает 20 browser assertions, а не 20 независимых разговорных сценариев: артефакт показывает один пользовательский чат-запрос; последующий синтез Qwen завершился timeout и интерфейс показал fallback. Это не принимается как 20/20 научных ответов.

Четыре вручную рассмотренных записи из более позднего Stage 9 development run показывают нерешённые семантические проблемы: D01 частичный, D03 частичный и неполный, D04 содержит неподтверждённое утверждение, что 30 °C «не оптимальны», D02 ожидает полной проверки. Поздняя проверка могла отвергнуть утверждение D04, однако сохранённая первая выдача остаётся неуспешным наблюдением.

## Проверки, выполненные сейчас

| Команда / действие | Результат |
|---|---|
| `python -m pytest -q -p no:cacheprovider --basetemp .pytest-ai-agent-final3` | **653 passed**, 0 failed, 0 deselected, 86.33 s. Два предупреждения: Starlette/httpx deprecation и существующий `PytestReturnNotNoneWarning` у `test_properties`. |
| Целевой набор capacity, Dashboard endpoint, краткий multi-turn ответ и каталог (16 тестов) | **16 passed**, 1 предупреждение Starlette/httpx, 3.89 s. |
| `python -m py_compile src/optimizer/capacity.py src/agent/advanced_conversation.py tests/test_advanced_conversation.py tests/test_complete_economics.py tests/test_substrate_advisor.py tests/test_reactor_capacity_validation.py` | **PASSED**. |
| `git diff --check -- src/optimizer/capacity.py src/agent/advanced_conversation.py tests/test_advanced_conversation.py tests/test_complete_economics.py tests/test_substrate_advisor.py tests/test_reactor_capacity_validation.py` | **PASSED**; только предупреждения о LF/CRLF в двух тестовых файлах. |
| `python main.py --help` | **PASSED**; CLI перечисляет dashboard, research, chat, providers, market, tool и существующие команды. |
| Backend `GET /health`, `GET /dashboard/` на `127.0.0.1:8766` | **200 / 200**, 241 / 1,040 bytes. Сервер запущен из текущей рабочей копии на PID 3412 с `--no-scheduler`; отдельное окно Edge открыто. Это HTTP smoke, не browser E2E. |
| GPU/Ollama read-only snapshot после тестов | RTX 3070 Laptop GPU, driver 581.80, 57 °C, 6%, VRAM 716/8192 MiB, 17.97 W, P8; slowdown thresholds 98 °C, shutdown 101 °C; thermal slowdown не активен; `ollama ps` пуст. Один снимок не является предзапусковым gate; Qwen в этой сессии не запускался. |

В промежуточных полных прогонах до исправления было 649 passed/3 failed, затем 651 passed/1 failed. Ошибки воспроизведены, исправлены общим механизмом и повторно проверены итоговым полным прогоном. Исключённых тестов в итоговом полном прогоне нет.

## Среда и сохранность

- Репозиторий: `BioReactor_AI`; ветка `main`; исходный commit `38efb3aee0b4dbea3a5feac92e90e3a0e2a7d640`.
- Рабочее дерево уже было сильно изменено до этого подэтапа: около 7,976 modified/deleted/untracked записей, в основном локальные зависимости и прежние результаты; часть каталогов недоступна для чтения текущему пользователю. Ничего из них не очищалось. Новые pytest basetemp каталоги оставлены.
- Python 3.13.13, pytest 8.4.2, Ollama 0.40.15. Сохранённые модели, базы, источники и предыдущие отчёты оставлены на месте.
- Текущий локальный Dashboard запущен на `http://127.0.0.1:8766/dashboard/` для ручной проверки; планировщик рыночных обновлений выключен. Порт 8765 и неизвестные процессы не останавливались.

## Приоритет оставшейся работы

| Приоритет | Статус и следующая задача |
|---|---|
| **P0** | Детерминированная доставка результата и capacity preflight проходят; вручную подтвердить свежий Dashboard после refresh/restart. Реальный cancel во время генерации не проверен; legacy synchronous route остаётся вне отменяемых jobs. |
| **P1** | Уточнить научные acceptance-оракулы и провести слепую оценку; отдельный validation split отсутствует, а RC3 development contract PASS составляет 10/23. Held-out оставить неприкосновенным. |
| **P2** | После P0/P1 расширять сценарии и источники, оценивать модель и рынок. Переобучение BMP/цен в этом подэтапе не выполнялось и сейчас не обосновано новыми независимыми данными. |

## Что требуется до READY

1. Повторить вручную в Edge содержательный Chat-запрос с невозможным объёмом и проверить правильный порядок/единицы, затем refresh и повторное открытие сохранённого ответа после текущего backend restart.
2. Отдельно решить поддержку или ограничение legacy synchronous route; не заявлять отмену inference только по статусу job.
3. Провести один live Qwen cancellation test только после свежего установленного GPU/RAM gate и по детерминированному streaming-сигналу. Предыдущий live run был INCONCLUSIVE; CUDA crash остаётся без подтверждённой первопричины.
4. Создать независимый validation set с явными ожидаемыми фактами, запрещёнными выводами, обязательными источниками/инструментами и multi-turn state assertions; существующий held-out набор сохранить нетронутым. Затем провести слепую научную оценку real-Qwen ответов.
5. Только после этого повторять новый acceptance-набор и исправлять общие причины провалов. Не обучать модель цен и не переобучать BMP ради метрик без нового плана оценки и независимых данных.

**Итог:** текущий код прошёл детерминированный полный набор, а физическая проверка вместимости и её формулировки исправлены в общем preflight. Реальные Qwen, браузерная доставка после последней правки, held-out и отмена активной Ollama генерации не подтверждены. Поэтому статус проекта остаётся **NOT READY**.


## 2026-11-09 - Real-Qwen quality work: historical trace analysis

Readiness remains **NOT READY**. Detailed per-case records (Stage 9 13 automated non-passes plus manually reviewed D04, and all 20 prior acceptance records) are in `reports/qwen_real_quality_error_analysis.md`. The report includes raw prompts, saved tools, verifier records, displayed answers, available rejected Qwen drafts, root-cause confidence, multi-turn state and A-K classes. Where an intermediate draft was not saved, it is explicitly marked absent.

Shared historical root families are typed quantity/role binding, planner/tool completeness, fallback evidence loss, verifier coverage/reference matching, limited direct profile coverage and Qwen timeouts. The prior acceptance summary count conflicts with its detailed table; the denominator remains unresolved. Previous capacity and sale-parsing changes are not treated as current defects without fresh replay. Stage 9 held-out remains untouched.

### GPU/Ollama preflight and baseline

Preflight artifact: `reports/real_qwen_preflight_20261109.json`. Three readings at 20:49:24, 20:49:35 and 20:49:45 +05:00 passed device thermal checks (RTX 3070 Laptop, 65/64/63 C, target 87 C, hardware slowdown inactive, utilization 8/6/6%, VRAM 982/969/969 of 8192 MiB). P-state is diagnostic only. RAM was 5,337.6-5,345.0 MiB, below the exact-config prior success observation 6.1 GiB; commit headroom was stable about 17.8 GiB; pagefile use 1.11%. Ollama 0.40.15, `qwen3:8b` Q4_K_M digest `500a1f067a9f782620b40bee6f7b0c89e17ae61f686b92c24933e4ca4b2b8b41`; no active model or established Ollama client request was observed. Prior CUDA runner crash remains unrooted; no inference retry was made.

Baseline artifact `reports/real_qwen_baseline_20261109.json` is **BLOCKED / NOT RUN**. No QA backend, Chat request, Qwen inference or browser E2E was started. Existing Dashboard PID 3412 on port 8766 remains running.

### User-controlled memory analysis

A later read-only snapshot at 21:01:47 +05:00 showed 5,488 MiB (5.36 GiB) physical RAM available, about 0.74 GiB below the case-specific comparison; commit headroom was about 17.65 GiB. Process-by-process working/private memory and safe handling guidance are in `reports/qwen_memory_release_analysis_20261109.md`. The largest controllable application family was Comet (about 2.42 GiB summed working set across child processes; reclaim is not guaranteed). No application was closed. Dashboard, Ollama, VS Code and browser windows were preserved. This later reading is not a three-sample gate. Wait for user-controlled RAM release, then repeat the documented three-sample preflight; do not start inference until it passes.

### D04 deterministic guard recheck

Current code contains `temperature_optimum_not_established` in synthesis validation and blocks model synthesis when status is `ok` but `checked=false`. Targeted command: `python -m pytest tests/test_stage9_verification.py::test_current_temperature_does_not_establish_an_optimum tests/test_stage9_runtime.py::test_unchecked_ok_cannot_admit_numeric_synthesis_or_verified_display -q -p no:cacheprovider --basetemp .pytest-d04-static-check` -> **2 passed in 1.35 s**. This confirms deterministic protection, not live Qwen/Browser delivery; replay remains NOT RUN behind the RAM gate. No app code changed.

### 2026-11-09 — повторный preflight и ограниченный real-Qwen baseline

Предыдущая запись о BLOCKED/NOT RUN относится к первому запуску preflight при 5.2 GiB RAM. После освобождения памяти выполнен новый полный трёхточечный preflight: 8204.0–8247.8 MiB RAM, commit headroom 21957.1–22011.5 MiB, GPU 62–63°C при target 87°C, thermal slowdown неактивен; admission PASS. Подробные значения сохранены в `reports/real_qwen_preflight_20261109_repeat.json`.

Затем запущена последовательная проверка реального AI Chat endpoint через существующий Dashboard PID 3412: `python -u reports/final_acceptance/real_qwen_baseline_repeat.py`. Provider traces первых двух сценариев подтверждают `qwen3:8b`, `actual_generation=true`, Ollama 0.40.15:

- Концептуальный вопрос BMP против фактического выхода реактора: **FAIL, 1/3 независимых критериев**. Агент вместо объяснения потребовал тип сырья и массу; был вызван `assess_substrate_potential` со статусом `needs_input`, verifier — `insufficient_evidence`. Подтверждён дефект маршрутизации общего научного вопроса в анализ партии.
- Условная арифметика `0.6 кг VS × 250 мл CH₄/г VS`: **PASS, 3/3**. `explicit_calculations` и verifier `ok`; результат **0.15 м³ CH₄**, назван расчётным потенциалом, не измеренной выработкой.
- Новый multi-turn по пищевым отходам, 5 кг и reactor 90 л: остановлен до финального ответа. Параметры были извлечены, выполнены `search_substrate_profiles` и `assess_substrate_potential`, но RAM упала до 6102.4 MiB против локального порога 6246.4 MiB. Job отменена; ход исправления на 6 кг не отправлялся, итог не оценивается.

После отмены в журнале Ollama записаны `stop: cancel task` и `all slots are idle`; финальный ответ третьей job не сохранён. При пассивном наблюдении в 21:27:56 свободная RAM была 6222.8 MiB и оставалась ниже gate. Новых запросов после этого не запускали. Температурный slowdown и CUDA crash не наблюдались. Приложение, модель BMP, драйверы и системные параметры в этой операции не менялись; полный acceptance, browser E2E и holdout не выполнялись.

Полные трассы, независимая переоценка rubric и план минимальных исправлений находятся в `reports/real_qwen_baseline_repeat_20261109.md` и `reports/real_qwen_baseline_20261109_repeat/`. Статус readiness остаётся **NOT READY**; следующий live шаг заблокирован, пока RAM не восстановится и новый preflight не пройдёт.

### 2026-11-09 — научная маршрутизация: исправление и ограниченный live replay

**Подтверждённая первопричина старого BMP-провала.** На сохранённом пути NLU относил концептуальный вопрос к `methane_yield`; `requirements()` Runtime 9 превращал это в обязательный `assess_substrate_potential`. При этом `search_scientific_sources` отсутствовал в публичном manifest. Qwen получала неверно ограниченный список действий, а `needs_input` запускал fallback с просьбой назвать субстрат и массу вместо научного объяснения. Это дефект общей классификации и контракта инструментов, а не только формулировки system prompt.

Исправлен общий маршрут: добавлены категории научного объяснения и неопределённости; расчёт по явно введённым VS/BMP отделён от оценки конкретной партии; локальный научный поиск включён в manifest и обязательные действия для концептуальных запросов. Информационный инструмент исключён из числовой проверки, а детерминированный source-grounded ответ сохраняет найденные утверждения без выдуманных числовых значений. Добавлен локальный проверенный материал по BMP, TS/VS, температуре, HRT/batch и номинальной/рабочей вместимости. Также сохранены маршруты вопросов о температуре на английском и казахском и прежнего расчёта BMP по явному контексту.

Изменённые компоненты: `src/agent/dialogue_types.py`, `src/agent/nlu.py`, `src/agent/runtime9.py`, `src/agent/tool_manifest.py`, `src/agent/verification9.py`, `src/recommendations/retrieval.py`, `data/knowledge/imported/scientific_concepts_20261109.json`, `tests/test_scientific_question_routing.py`.

Команда целевой детерминированной проверки:

```text
pytest -q tests/test_scientific_question_routing.py tests/test_stage9_runtime.py tests/test_stage9_verification.py tests/test_conversation.py tests/test_stage9_jobs.py --basetemp .pytest_scientific_routing_after_20261109
```

**Результат: 135 passed, 0 failed, 1 существующее предупреждение Starlette/httpx, 27.05 s.** Набор прошёл через тот же FastAPI Dashboard jobs endpoint с детерминированным provider: концептуальные вопросы не вызывают оценку партии; явный расчёт `0.6 kg VS × 250 mL/g` остаётся `0.15 m³`; смешанный вопрос получает и научное основание, и расчёт; многоходовая коррекция сохраняет пищевые отходы и меняет массу с 5 на 6 кг. Это не real-Qwen и не браузерная проверка.

Новый трёхточечный preflight: 2026-11-09 23:02:58, 23:03:10 и 23:03:21 +05:00. Доступно 7,914 / 7,813 / 7,912 MiB RAM; запас commit 21,511.8 / 21,418.0 / 21,415.4 MiB. RTX 3070 Laptop — 56 °C, 0% utilization, 728/8,192 MiB VRAM, 17.66–17.68 W; HW/SW thermal slowdown неактивен; температурный target устройства 87 °C, slowdown 98 °C. Ollama 0.40.15, модель `qwen3:8b` присутствует, активных моделей и установленных запросов нет. Admission preflight — **PASS**.

Win32 CIM вернул Access Denied; доступная RAM и commit сняты штатными Windows `\Memory` performance counters, во время job — `GetPerformanceInfo`. Это не мешало получению трёх RAM-замеров.

Однако при старте первого изолированного запроса на QA endpoint `127.0.0.1:8775` доступная RAM упала с 7,900.2 до 4,773.0 MiB во время запуска llama-server, пересекла существующий gate 6,246.4 MiB и вызвала немедленную отмену. Температура была 58 °C, VRAM 3,088/8,192 MiB, slowdown неактивен. Ollama записала `client connection closed before llama-server finished loading, aborting load`, `Load failed ... context canceled` и HTTP 499; модель не загрузилась, generation/tool trace и финальный ответ не сохранены. Job `cbf3a556ee96411c8594cc595ca2b5ca` подтверждённо перешла в `CANCELLED`; после отмены RAM восстановилась до 7,803 MiB, GPU была 57 °C / 710 MiB VRAM, `/api/ps` пуст. CUDA error в этом ограниченном запуске не наблюдалась.

Дополнительное ограничение достоверности теста: исходный запрос был «Чем лабораторный BMP отличается от фактического выхода метана в реакторе? Объясни, почему результат BMP нельзя напрямую считать измеренным выходом конкретной установки». Сохранённое поле `agent_jobs.message` содержит `?` вместо кириллицы — Windows PowerShell pipeline испортил UTF-8 до отправки запроса. Поэтому этот запрос не является корректным повтором BMP-вопроса и не оценивается как ответ Qwen. Факт ошибки harness записан в `reports/scientific_qwen_baseline_20261109.json`; исходная формулировка указана в этом отчёте отдельно от реально переданного текста. Остальные три запроса не запускались по правилу остановки после resource-gate failure. Отдельный QA backend PID 11548 остановлен; Dashboard PID 3412 и общий Ollama не останавливались.

**Результат real-Qwen retest: BLOCKED / нет валидных сценариев.** Научное улучшение реальной Qwen, смешанный сценарий, два хода 5→6 кг, browser E2E и независимый holdout остаются **NOT RUN**. Наблюдавшееся снижение доступной RAM при старте llama-server составило около 3,127 MiB; это единичное измерение, а не установленная постоянная потребность модели. При следующем запуске тестовую обвязку нужно передавать как UTF-8 файл или иной проверенный UTF-8 transport и сохранить не менее 6,246.4 MiB свободной RAM во время загрузки модели; перед запросом нужен новый трёхточечный preflight. Результаты не подтверждают READY: общий статус остаётся **NOT READY**.

После остановки QA процесса проверены `GET /health` и `GET /dashboard/` существующего Dashboard на 8766: **200/200**. Это только HTTP smoke; Chat в браузере после этой правки не запускался.

### 2026-11-09 — укрепление real-Qwen test infrastructure

**Unicode.** Проверка provider-кода показала корректную сериализацию `json.dumps(..., ensure_ascii=False).encode('utf-8')`; потеря текста возникла в PowerShell pipeline до HTTP. Добавлены отдельный UTF-8 JSON fixture и Python `urllib` runner. Он строго декодирует файл, проверяет RU/KK/EN, `әғқңөұүһі`, `×`, `CH₄`, `°C`, `m³/м³`, единицы; строит HTTP JSON bytes в Python; проверяет byte-identical round-trip до отправки и сверяет принятую `job.message` с исходными UTF-8 байтами. Повреждение даёт `INVALID_INPUT`, и запрос не отправляется. Loopback echo проверяет точные HTTP body bytes.

**Resource phases и gate.** Runner фиксирует before-load, during-load, model-ready, during-inference, after-completion и after-unload sample: доступную RAM, commit headroom, GPU/VRAM/температуру/slowdown, `ollama /api/ps`, активные TCP connections, PID и working set `ollama`, `ollama app`, `llama-server`, текущую job и новые Ollama log lines. Он запускает только один QA backend после всех admission samples; не запускает Qwen по умолчанию; `run` требует явного `--allow-real-inference`. Во время job доступны runtime cancellation gate, поиск внешнего активного запроса, проверка количества runner-процессов, CUDA-сигнатур и фактических llama-server флагов. После завершённых сценариев runner запрашивает разгрузку только собственного Qwen через per-request `keep_alive=0`, не меняя глобальную настройку; затем проверяет `/api/ps`.

Текущий config из Ollama server log: `OLLAMA_NUM_PARALLEL=1`, `OLLAMA_KEEP_ALIVE=5m0s`, `OLLAMA_CONTEXT_LENGTH=0`, `OLLAMA_MAX_LOADED_MODELS=0`, `OLLAMA_MAX_QUEUE=512`, `OLLAMA_LOAD_TIMEOUT=5m0s`. Runtime QA profile передаёт `num_ctx=8192`, `num_gpu=16`, batch/ubatch 64; последняя ошибочная загрузка имела `-c 8192 -np 1 -b 64 -ub 64 -ngl 16`. Более ранний успешный Qwen-запуск имел `-b 512 -ub 512` и не содержал `-ngl 16`, поэтому его RAM minimum не является точным подтверждением текущего профиля. Ни контекст, ни модель, ни глобальные Ollama settings не менялись. Parallelism уже равен 1 и сценарии сериализованы; менять эти параметры на текущих данных не обосновано. API unload и параллельные требования к памяти документированы [в официальном FAQ Ollama](https://github.com/ollama/ollama/blob/main/docs/faq.mdx) и [API reference](https://github.com/ollama/ollama/blob/main/docs/api.md); фактические значения взяты из локального журнала версии 0.40.15.

**Admission gate.** Старый runtime floor 6,246.4 MiB оставлен для отмены активной job. Для холодного старта этого оказалось недостаточно: предыдущая загрузка на профиле `8192/16 GPU layers/batch 64` упала с 7,900.2 до 4,773.0 MiB, то есть на 3,127.2 MiB. Временный admission floor равен `6,246.4 + 3,127.2 = 9,373.6 MiB`; он помечен provisional и специфичен для этого профиля. Другой, ранее успешный запуск с флагами `batch512/no explicit -ngl` стартовал с 8,132.9 MiB и не отменяет этот профильный blocker. Gate нужно пересмотреть по PID-level телеметрии успешной загрузки, а не считать порог универсальным.

Новый ограниченный трёхточечный preflight запущен только как read-only проверка, без QA backend и inference. В `reports/qwen_resource_preflight_20261109.json` записано:

| Время +05:00 | Available RAM | Commit headroom | RTX 3070 Laptop | VRAM | Ollama/runner |
|---|---:|---:|---|---:|---|
| 23:42:49.326 | 6,566.5 MiB | 19,731.5 MiB | 58°C, slowdown inactive | 838/8,192 MiB | Qwen not loaded, no active request, no llama-server |
| 23:42:59.326 | 6,602.6 MiB | 19,775.6 MiB | 58°C, slowdown inactive | 838/8,192 MiB | Qwen not loaded, no active request, no llama-server |
| 23:43:09.327 | 6,605.0 MiB | 19,783.0 MiB | 58°C, slowdown inactive | 832/8,192 MiB | Qwen not loaded, no active request, no llama-server |

Admission **BLOCKED** по RAM: кратковременная нехватка относительно provisional floor составляет 2,768.6–2,807.1 MiB. Commit headroom не лимитировал. Ollama PID 18880 (44.0–44.5 MiB working set), GUI PID 13100 (47.1 MiB); активных запросов и runner-процессов нет. `tasklist` и Win32 CIM недоступны по Access Denied, поэтому runner использует работающий `Get-Process` источник; пользовательские процессы не менялись. Процесс-владелец RAM-спада при прошлом старте не установлен: там не снималась PID/RSS телеметрия. Новых GPU запусков не было.

GPU аварийный stop в runner задан на 82°C: это локальный запас 5°C к наблюдавшемуся device target 87°C с учётом предыдущего опыта до 86°C, а не универсальный порог. HW/SW slowdown и отсутствие телеметрии также безусловно блокируют/останавливают job; P-state остаётся диагностическим.

**Проверки test infrastructure.** Команда `pytest -q tests/test_scientific_question_routing.py tests/test_stage9_runtime.py tests/test_stage9_verification.py tests/test_conversation.py tests/test_stage9_jobs.py tests/test_real_qwen_baseline_runner.py --basetemp .pytest_qwen_infra_final_20261109` — **152 passed, 0 failed**, одно существующее предупреждение Starlette/httpx, 29.17 s. `python -X utf8 -m py_compile evaluations/real_qwen_baseline_runner.py tests/test_real_qwen_baseline_runner.py` — PASSED. `python -X utf8 evaluations/real_qwen_baseline_runner.py validate` — PASS для 4 сценариев и всех Unicode probes; inference NOT RUN. В том числе тест подтверждает, что BLOCKED preflight не стартует backend.

**Статус.** UTF-8 инфраструктура исправлена и детерминированно проверена. Real-Qwen после изменений **BLOCKED / NOT RUN** по admission RAM; model-ready, inference, post-completion и unload стадии в новом запуске не наблюдались. Предыдущая попытка остаётся невалидной по вводу и была отменена во время загрузки. Browser E2E, независимый holdout и real-Qwen baseline не выполнены. Проект **NOT READY**.

#### 2026-11-10 — заключительная проверка test harness

После документирования профильного admission gate повторно запущена та же детерминированная команда: `pytest -q tests/test_scientific_question_routing.py tests/test_stage9_runtime.py tests/test_stage9_verification.py tests/test_conversation.py tests/test_stage9_jobs.py tests/test_real_qwen_baseline_runner.py --basetemp .pytest_qwen_infra_finalverify_20261110` — **152 passed, 0 failed**, одно существующее предупреждение Starlette/httpx, 33.68 s. `py_compile`, runner `validate` и UTF-8 JSON parsing обоих fixture/preflight artifacts — **PASS**; команда runner подтвердила четыре подготовленных хода и явно `http_inference: NOT RUN`. Статический просмотр подтвердил, что ходы `batch_5kg` и `correct_batch_to_6kg` используют ключ одной conversation/session. Их фактическое состояние и ответы, разумеется, пока не проверены.

Повторный live preflight не запускался после зафиксированного BLOCKED результата 2026-11-09 и этого запуска не требуется для статической проверки harness. Никакие Qwen/Ollama inference, Dashboard E2E, изменения модели или системных настроек не выполнялись. Текущий readiness остаётся **NOT READY** до успешного свежего admission, трёх live-Qwen сценариев и независимого holdout.

### 2026-11-10 — Qwen resource profile analysis

В отдельной read-only проверке профиль текущего QA server подтверждён кодом provider: `num_ctx=8192`, `num_gpu=16`, `num_batch=64`, `num_thread=6`; локальный Ollama server использует `OLLAMA_NUM_PARALLEL=1`, global context env `0`, keep-alive `5m`. Ollama log выбирал VRAM-based context 4096, который QA override удваивает. Прямая поддержка runner options подтверждена для установленного Ollama 0.40.15 в его version-tagged API.

Свежий трёхточечный preflight 11:37 +05 **BLOCKED**: free RAM 4,625.1–4,646.7 MiB, commit headroom 19,571.0–19,581.6 MiB; GPU 59°C, 477/8,192 MiB VRAM, slowdown inactive, `/api/ps` empty. Ollama server PID 30060 ~42 MiB working set; Ollama app PID 21768 ~3,600 MiB working set (4,234 MiB private bytes in a later snapshot); Dashboard listener 8766 and `llama-server` were absent. No process was stopped and no Qwen inference was attempted.

Historical real-Qwen reference profile (`8192 / batch512 / num_gpu auto / threads auto`) completed two turns: model fully in VRAM (~6.195 GB reported, GPU peak 6,730 MiB), minimum free RAM 6,761.4 MiB, max 81°C, about 49 tokens/s. First conceptual answer failed its scientific rubric, second explicit arithmetic passed. A third turn was cancelled at 6,102.4 MiB and reached 86°C. Therefore this is a resource candidate, not a quality-approved or stable three-case profile. The exact current profile and two proposed 4096-context profiles have no successful-load data. Details: `reports/qwen_resource_optimization_20261110.md` and `evaluations/qwen_resource_profiles_20261110.json`. Readiness remains **NOT READY**.

### 2026-11-10 — Ollama app memory follow-up

A later six-point passive sample (11:49:12–11:50:03 +05) supersedes the 11:37 RAM snapshot as the latest observation: the same `ollama app.exe` PID 21768 dropped from ~3.60 GiB working set to 55.8 MiB; free RAM was 8.18–8.20 GiB and commit headroom 24.11–24.13 GiB. Ollama API remained HTTP 200 and no model was loaded. This transient release does not establish the cause or prove normal behavior. The sample clears the historical runtime floor but remains below the 9,373.6 MiB cold-start gate, so real Qwen remains blocked and readiness stays **NOT READY**. Details and limitations are recorded in `reports/ollama_memory_consumption_investigation_20261110.md`.

### 2026-11-10 — headless comparison and recovery status

An approved headless comparison confirmed Ollama 0.40.15 can serve the local API without its desktop app. The unloaded server used ~45 MiB working set and ~95 MiB private bytes; `/api/version` and `/api/ps` returned HTTP 200 in six passive samples. Three-point free RAM was 8,081.8–8,098.4 MiB, 1,275.2–1,291.8 MiB below the cold-start gate; GPU was 49 C with no thermal slowdown. Qwen was not run. Automated GUI relaunch failed, then the user reopened it manually. The restored GUI and server now answer HTTP 200; `/api/ps` is empty. Two passive samples show 7,054.7–7,075.2 MiB free RAM, still below the 9,373.6 MiB cold-start gate. Readiness remains **NOT READY**. Full data: `reports/ollama_memory_consumption_investigation_20261110.md`, `reports/ollama_memory_headless_samples_20261110.json`, `reports/ollama_headless_preflight_20261110.json`, and `reports/ollama_memory_gui_restored_20261110.json`.
# 2026-11-11: исправление участия Qwen3 4B — NOT READY

Позднейший scientific retest после ожидания 60 s: ограниченный реальный FastAPI Chat COMPLETED за 6.172 s, 2 реальных Qwen calls, валидный NLU, source tool, доставленный и сохранённый synthesis без fallback; quantity/scoped scientific checked=true/passed. Независимая научная оценка PARTIAL: «условия ... не переносимы» чрезмерно категорично, не указана сопоставимая удельная/газовая база сравнения. Ресурсы в рамках, модель выгружена, ollama ps пуст. Журнал limited_chat_1794410562196274200.json, полный ответ и пределы проверки в qwen3_4b_agent_integration.md. FIRO NOT READY.

После научной PARTIAL-приёмки уточнён source-bound контекст экспериментального BMP/batch-кинетики; verifier проверяет ограниченные семейства утверждений с subject/target/negation на RU/KK/EN. 306 детерминированных тестов PASSED. Предыдущий спорный реальный ответ теперь отвергается по двум конкретным причинам; это replay, не новый инференс. Один real limited-chat retest BLOCKED до загрузки: RAM 5669.5 < 6656 MiB, дефицит 986.5 MiB; модельных вызовов 0. Новый live научный PASS не подтверждён. Подробности и журнал limited_chat_1794409745652375100.json — в qwen3_4b_agent_integration.md. FIRO NOT READY.

Самый поздний real retest после 60 s ожидания: один настоящий FastAPI limited-chat завершён за 6.199 s, 2 Qwen calls (13+223 выходных токена). NLU valid_compact_grounded, source tool вызван, синтез принят и сохранён без fallback (`qwen_grounded_information`). Quantity и scoped scientific verifier checked=true/passed; сохранённый ответ совпадает с доставленным. Техническая интеграция одного запроса PASS; независимая научная оценка PARTIAL: формулировка «BMP — ... а не измеренная выработка» не уточняет reactor yield, а утверждение «условия ... не отражены в batch-тесте» чрезмерно категорично. Они пропущены узкими guards. Ресурсы соблюдены, модель выгружена, ollama ps пуст. Журнал limited_chat_1794407172434436200.json, полный ответ и метрики в qwen3_4b_agent_integration.md. FIRO NOT READY.

Последующее исправление quantity grounding: текущий срок вопроса передаётся как USER_INPUT/question_time_horizon с единицей day, сохраняются origins и арифметические преобразования; выдуманные газовые прогнозы, подмена единиц и сроков, неподтверждённые рекомендации отклоняются. 247 релевантных тестов PASSED. Старый реальный Qwen-черновик повторно принят новыми ограниченными checks без нового инференса. Новый real limited-chat BLOCKED до загрузки: RAM 5966.1 < 6656 MiB, дефицит 689.9 MiB. Журнал limited_chat_1794406155995582700.json; результаты numeric_revalidation_20261111.json и полное обоснование в qwen3_4b_agent_integration.md. Свежая доставка модельного синтеза пока NOT RUN; FIRO NOT READY.

Позднейший real retest после ожидания Comet: одна job завершена за 7.498 s, 2 настоящих Qwen-вызова. Компактный NLU валиден (13 токенов, material_span=null), scientific source tool выполнен, Qwen сформировала полный JSON синтеза (223 токена). Итог по-прежнему fallback: quantity validator ошибочно отверг повторение `30 дней` из вопроса, которому не соответствует typed evidence. Научный verifier прошёл только для доставленного fallback, численный checked=false. Ресурсные защиты соблюдены, модель выгружена; критерий доставленного модельного ответа НЕ ПРОЙДЕН. См. журнал limited_chat_1794404943720876600.json и отчёт интеграции. Следующий шаг — типизированный временной scope вопроса для quantity validation с запретом выдуманных чисел.

После реального limited-chat исправлены компактный NLU/проверка материала, маршрутизация научного поиска с выделением бюджета на модельный synthesis и отдельная ограниченная проверка научного ответа. 266 релевантных тестов PASSED; финальный дополнительный набор 32 PASSED. Реальный retest после этих изменений BLOCKED до загрузки: свободная RAM 5650.2 MiB против неизменного admission 6656 MiB. Реальное улучшение ответа/верификации Qwen не подтверждено. Полные изменения, точные команды, источник атрибуции Koch et al. и журнал попытки: [qwen3_4b_agent_integration.md](qwen3_4b_agent_integration.md). Ни production selection, ни ограничения безопасности не менялись. Следующий шаг — один monitored limited-chat после изменения ресурсных условий; самостоятельный holdout и браузер остаются незавершёнными.


## Literature estimates and actual Qwen3 4B retest - 2026-11-12

Bounded scenario C now PASSED through the actual async FastAPI Chat jobs endpoint (TestClient with real Ollama HTTP provider, no canned inference response). Qwen selected scientific retrieval and the shared conditional density/TS/VS/BMP calculator. 4 real calls; final author qwen_verified; numerical and scientific checks passed with checked=true. Source assumptions and no 30-day yield remain explicit. Response 12.357 s, min observed free RAM 6997 MiB, max commit 17175.2 MiB, max VRAM 3877 MiB, max GPU 68 C, unload confirmed in 0.271 s, models empty afterward. Earlier first-run incomplete prose/time-query loss remains recorded, not counted as PASS. Final regression suite: 243 passed; frontend 80 passed/build passed; Chrome offline 14 checks passed plus genuine pre-restart record restore. The last independent source/basis guards were verified by deterministic replay of the unchanged real draft, not counted as a new live inference.

Full report, commands, files, actual answer and remaining limitations: reports/literature_methane_estimates_20261112.md. New scenario forecast is a literature BMP reference (~2923-4114 L CH4), not measured gas or a scientifically validated 30-day reactor forecast. Model clarification redundantly requests an already known volume; this remains a quality issue. Broad browser Chat live coverage and independent holdout NOT RUN. Overall FIRO NOT READY; production model configuration and resource limits unchanged.
