# BioReactor AI v8.0

Advanced conversational tasks now retain the original gas/energy/economics request across clarifications. Manure has independent animal, physical, decay and bedding axes, with bidirectional unit conversion and explicit literature/illustrative provenance. The existing models, prices, history and APIs remain in place.

See [v8.0 launch and API instructions](docs/advanced_conversation.md) and [the scientific verification report](reports/stage8_0_advanced_conversational_ai.md). New evidence is kept in data/research/advanced_profiles.json; earlier source files are preserved. Scientific coverage is partial: six approved numerical profiles for five material categories, with one coherent full density/TS/VS/BMP profile. Conditional transfer scenarios are counted separately.

# BioReactor AI v7.5

The existing research agent now includes gas composition, heat/electricity/CHP, reactor energy demand, A-E alternatives, cost budgets and deterministic conditional decisions. Original v7 BMP values, 28 market observations, models and conversation history are preserved.

```powershell
python main.py dashboard --port 8765
python main.py chat --research --mode offline
```

Open http://127.0.0.1:8765/dashboard/#/chat . Ask about 142 L of cattle manure, clarify slurry, then choose heating or electricity. The response is concise; current calculation cards, sources and previous results are expandable. Enter known reactor data and batch costs through the parameter form. Blank costs stay unknown.

[Complete scientific/economic report](reports/stage7_5_complete_economics.md) includes real test results, dialogues, source limitations and the reference JSON. POST /api/research/decision accepts the existing EstimateRequest plus optional decision settings; /api/research/estimate remains compatible. Top-level v7 scientific outputs are preserved; v7.5 validated energy/economic results are under decision_analysis. A reference asking value or statistical tariff is never guaranteed income or an individual billing tariff. Scenarios remain separate from measured facts; interval coverage is not claimed. No equipment controls are exposed.

Earlier version notes follow for historical compatibility.

---

# BioReactor AI v7

Current implementation: autonomous sourced research, deterministic literature estimates, and local qwen3:8b (Q4_K_M, context 2048), with qwen2.5:1.5b fallback. Existing BMP artifacts, market prices, experiments and conversation history are preserved. Earlier version sections below document their original configurations.

```powershell
python main.py dashboard --port 8765
python main.py chat --research --mode offline
```

Open http://127.0.0.1:8765/dashboard/#/chat . New dashboard sessions use v7; legacy CLI remains compatible unless --research is selected. offline means local LLM; set BIOREACTOR_RESEARCH_ONLINE=0 to disable public research downloads as well. Published evidence and saved prices remain available locally, with age and limitations.

See [v7 scientific report](reports/stage7_autonomous_research.md) for real measurements, source status, API examples and verification evidence. Estimates use explicit MEASURED / LITERATURE_ESTIMATE / HYPOTHETICAL_SCENARIO labels. A seller ask is not a buyer bid or profit. No validated interval coverage is claimed. Python performs the arithmetic; unsupported manure is never passed to Hafner as an invented trained category.

Research API: GET /api/research/evidence; POST /api/research/estimate; GET /api/research/runs, /offers, /logs. Optional PDF-text extraction dependencies: requirements-research.txt. The bundled local dependencies are already installed. Do not rerun training for this upgrade.

---

# BioReactor AI

## Process Optimizer и Experiment Lab — этап 6

Оптимизатор сравнивает явно заданные технологические сценарии: проверяет объёмы и
ограничения, рассчитывает доступные компоненты энергии и потенциал CH₄, обращается к
прежнему Market Intelligence и показывает компромиссы. При неполных данных оптимум не
назначается. Температура сама по себе не повышает BMP в модели.

```powershell
python BioReactor_AI/main.py dashboard
python BioReactor_AI/main.py chat --mode offline
python BioReactor_AI/main.py tool optimize_process --input BioReactor_AI/examples/process_optimizer.json
python BioReactor_AI/verify_stage6.py
```

Изнутри папки `BioReactor_AI` уберите префикс `BioReactor_AI/` из путей. Локальные страницы:
[Process Optimizer](http://127.0.0.1:8765/dashboard/#/optimizer),
[Experiment Lab](http://127.0.0.1:8765/dashboard/#/experiments),
[AI Chat](http://127.0.0.1:8765/dashboard/#/chat). Схемы API — `/docs`.
Повторно собирать frontend для обычного запуска не требуется.

Чат сохраняет контекст: **800 L сырья, 90 L полного и 65 L рабочего объёма** — разные
величины. План загрузок требует режима, объёмов инокулята/воды и времени цикла.
Пример JSON содержит условия из задания и явно выбранные температурные гипотезы,
а не результаты реального эксперимента. Снимки исследований сохраняются в прежней SQLite.

Журнал экспериментов хранит неизвестные значения пустыми, отделяет пользовательское
происхождение от лабораторного, сохраняет версии записей/моделей и наблюдения во времени,
поддерживает CSV. Биогаз без количественно измеренной доли CH₄ не сравнивается с BMP метана;
показания MQ не считаются точным измерением CH₄. Из журнала не запускается переобучение.

Новые API: `/api/process/optimize`, `/api/process/scenarios`, `/api/process/compare`,
`/api/experiments`. Старые endpoints сохранены. Оптимизатор не управляет оборудованием.

Проверочный скрипт использует отдельную копию SQLite, реальную установленную Ollama и
Chrome. Демонстрационные записи `TEST` остаются в изолированной базе. `--reuse-build`
повторяет TypeScript с готовой сборкой; `--skip-browser` фиксирует пропуск Chrome.

[Подробный отчёт этапа 6](reports/stage6_process_optimizer.md) ·
[Результаты проверки](reports/stage6/verification.json) ·
[Реальный диалог Ollama](reports/stage6/actual_dialogue.md).

Проверено: **212 backend-тестов, 26 frontend-тестов, 32 проверки Chrome, 23 HTTP-проверки**
и обязательный последовательный диалог с реальной Ollama. Все 196 прежних защищённых
файлов и 28 цен сохранены. Эти проверки не являются независимой научной валидацией.

## Conversational Intelligence — этап 5.6

Существующий AI Chat понимает обычные сообщения на русском, казахском и английском,
хранит параметры партии между сообщениями и задаёт один приоритетный вопрос. После
«800 литров навоза» → «Коровий» сохраняются **800 L**. Литры не заменяются килограммами
без плотности. Научная справка с источником отделена от ML-прогноза и условной экономики.

```powershell
python BioReactor_AI/main.py dashboard
python BioReactor_AI/main.py chat --mode offline
python BioReactor_AI/main.py chat --no-llm
python BioReactor_AI/main.py chat --conversation <conversation_id> --mode offline
python BioReactor_AI/main.py knowledge list
python BioReactor_AI/main.py knowledge import --input C:/path/reviewed_document.json
```

Команды выше выполняются из родительской папки проекта. Внутри `BioReactor_AI`
используйте `python main.py ...`. `offline` использует локальную Ollama, по умолчанию
`qwen2.5:1.5b`; `--no-llm` оставляет детерминированное извлечение и Python-инструменты.
История обоих режимов хранится в прежней SQLite. Идентификатор продолжения показывает CLI;
интерфейс восстанавливает свою сессию автоматически. Прежние ответы сохраняются при
обновлении сессии. Новые многогигабайтные модели для этого этапа не требуются.

В чате доступны кнопки уточнений, данные партии, исправление материала/количества и
свёрнутые технические подробности. Сохранены дизайн v4 и прежние разделы. Караганда из
профиля — видимое допущение до подтверждения; тариф природного газа не считается ценой
продажи сырого биогаза. Без необходимых измерений и затрат агент не выдаёт точную прибыль.
Общий литературный ориентир температуры не является командой оборудованию.

Импорт научных сведений требует предварительной проверки оператором; формат описан в
[JSON Schema](examples/scientific_document.schema.json). Схема проверяет структуру,
происхождение и численные поля, но не истинность публикации автоматически.

Полная воспроизводимая проверка:

```powershell
python BioReactor_AI/verify_stage5_6.py
```

Она использует временную копию рабочей базы и установленный Chrome, выполняет сборку,
тесты, HTTP/CLI/браузерные проверки и последовательные прогоны реальной Ollama.
Для проверки Ollama должна быть запущена с установленной `qwen2.5:1.5b`.
`--reuse-build` использует готовый build и повторяет TypeScript-проверку;
`--skip-browser` явно отмечает отсутствие браузерной проверки.

Фактически прошли **160 backend-тестов, 20 frontend-тестов, 27 проверок Chrome и
18 диалоговых случаев с реальной Ollama**. Все 28 прежних цен, прежние сообщения и
142 файла предыдущих результатов сохранены. BMP-модели не переобучались.

[Отчёт 5.6](reports/stage5_6_conversational_ai.md) ·
[Фактические диалоги](reports/stage5_6/actual_dialogues.md) ·
[До/после](reports/stage5_6/before_after.md) ·
[Результаты проверки](reports/stage5_6/verification.json).

## Intelligent Control Dashboard — этап 4

```powershell
python BioReactor_AI/main.py dashboard
```

Команда запускает **существующий FastAPI**, обслуживает собранный React-интерфейс
и открывает `http://127.0.0.1:8765/dashboard/`. Vite dev server и Node.js для обычной
работы не нужны. Остановка — **Ctrl+C** в том же терминале. Если порт занят, выберите
`--port 8767`. `--no-browser` отключает открытие браузера; `--no-scheduler` отключает
фоновые рыночные обновления. По умолчанию планировщик прежний, ежедневный.

Реализованы Overview, AI Chat, Reactor Monitoring, Methane Prediction, Market
Intelligence, Economic Comparison, Scientific Analytics, System Status и FIRO Demo.
React/TypeScript/Vite/Tailwind/Recharts/Motion/Lucide работают из локального build;
внешние CDN и шрифты не требуются. Backend остаётся источником расчётов и метрик.

Чат вызывает существующего агента на Ollama, хранит историю в той же SQLite и
показывает только фактически выполненные инструменты. При недоступной Ollama
включается обозначенный расчётный режим; его можно выбрать явно. Dashboard Chat
не отправляет контекст внешнему LLM. Запустите Ollama с установленной
`qwen2.5:1.5b` для локального планирования инструментов.

Без датчиков интерфейс показывает **SIMULATION / NO LIVE SENSOR DATA**. Схема
симуляции иллюстрирует путь сигнала, числовые показания не генерируются. Команд
оборудованию и endpoint приёма измерений пока нет. В FIRO запись диалога отделена
и помечена RECORDED DEMO; лабораторный пример не выдаётся за вашу партию.

Проверено в настоящем Chrome: **38 браузерных проверок**, 1366×768, 1920×1080 и
390×844. Прошли **117 backend-тестов, 13 frontend-тестов**, TypeScript и production
build. Реальная Ollama вернула план; сохранены скриншоты, API trace и результаты
проверок. Все 28 рыночных наблюдений и 112 прежних файлов сохранены, модели не
переобучались.

[Отчёт этапа 4](reports/stage4_dashboard.md) ·
[Скриншот Overview](reports/stage4/overview_1366.png) ·
[Результаты проверки](reports/stage4/verification.json).

Для разработки и повторной сборки (Node.js 24 использован при проверке):

```powershell
Set-Location BioReactor_AI/frontend
npm.cmd ci
npm.cmd run dev
npm.cmd run typecheck
npm.cmd run test
npm.cmd run build
```

Для Vite dev server запустите backend в другом терминале командой
`python BioReactor_AI/main.py market serve`: Vite проксирует API на порт 8765.
Production build сохраняется в `frontend/dist` и автоматически доступен также
через `market serve`. На Windows используется `npm.cmd`, чтобы не менять системную
политику выполнения PowerShell ради npm.ps1.

Полная воспроизводимая проверка:

```powershell
python BioReactor_AI/verify_stage4.py
```

Она запускает отдельный сервер на свободном порту с временной копией настоящей
базы, проверяет прежний CLI и останавливает свой сервер. Браузерная часть использует
установленный Chrome через Playwright Core, без скачивания браузера. Другой путь
можно задать в `CHROME_PATH`. Если Chrome недоступен: `--skip-browser`; отчёт
явно отметит отсутствие браузерной проверки. `--reuse-build` повторно использует
готовую сборку с проверкой TypeScript. Старые verify-скрипты не перезаписывают
отчёты этапов 1–3.5 при запуске нового проверочного скрипта.

## Market Intelligence — этап 3.5: реальные источники

```powershell
python -m pip install -r BioReactor_AI/requirements-market.txt
python BioReactor_AI/main.py market update
python BioReactor_AI/main.py market status
python BioReactor_AI/main.py market serve
```

Локальный API: `http://127.0.0.1:8765`, схема — `/docs`. FastAPI и SQLite хранят
историю цен и экономических сценариев; ежедневный планировщик обновляет настроенные
источники. `market update` запускает ручную попытку, `market import-csv --input ...`
принимает проверенные наблюдения. Переменные `BIOREACTOR_MARKET_DB`,
`BIOREACTOR_MARKET_INTERVAL_SECONDS` и `BIOREACTOR_MARKET_SCHEDULER` задают базу,
период (по умолчанию сутки) и включение планировщика.

Агент получил get_market_prices, get_price_history, compare_market_scenarios и
explain_market_recommendation. Экономический вопрос автоматически вызывает рынок;
точные параметры сравнения A/B/C/D передаются под ключом market_scenario.
Пустой шаблон — `examples/market_scenario_template.json`; CSV-заголовок —
`examples/market_prices_template.csv`. Прежний ручной calculate_profitability доступен.

На Windows HTTPS проверяется через **truststore и системное хранилище доверия**.
Проверка сертификата и имени сервера включена. Для явно настроенного доверенного PEM
можно задать `BIOREACTOR_MARKET_CA_BUNDLE`; неверный файл останавливает запрос.
Глобальная конфигурация SSL и системные CA не изменяются приложением.

28.10.2026 реальные адаптеры БНС, Қарағанды Жарық, КРЭК и Энергосбыта Алматы
успешно получили цены. В SQLite **28 наблюдений, 0 тестовых**. Прежние два тарифа
сохранены. БНС для Караганды: газ **54,81 ₸/м³**, электроэнергия **20,39 ₸/кВт·ч**
за сентябрь 2026, публикация 09.10.2026. Это бытовая статистика, исключённая из
окончательного коммерческого расчёта. КРЭК: **45,47 ₸/кВт·ч с НДС** для небытовых
потребителей пяти районов области с 15.10.2026; город Караганда в этот тариф
не входит. Городской тариф 38,87 ₸ имеет старую дату и неизвестную публикацию.
Для текущей сделки с сырьём/удобрениями нужны проверенные предложения или CSV/API.

Статусы: VERIFIED_CURRENT, VERIFIED_HISTORICAL, STALE, UNVERIFIED, UNAVAILABLE.
`/prices/current` возвращает последние сохранённые данные: смотрите статус, возраст,
профиль, регион и тип цены. VERIFIED_CURRENT у статистики означает свежесть публикации,
а не пригодность для сделки. После ошибки источника сохранённая цена получает
UNAVAILABLE. Успех обновления не делает старый или недатированный тариф свежим.

После успеха источник проверяется раз в сутки; после ошибок — через 5/10/20 минут,
затем раз в сутки. CLI и API соблюдают ту же паузу и блокировку категории в SQLite.
Сервер проверяет наступление срока раз в минуту. Он работает, пока запущен процесс;
во время выключения ноутбука обновлений нет. `rate_limited` показывает срок следующей
попытки. История цен и исходные документы с SHA-256 остаются в `data/market/`.

```powershell
Invoke-RestMethod 'http://127.0.0.1:8765/prices/current?region=KZ-Karaganda'
Invoke-RestMethod 'http://127.0.0.1:8765/prices/history?commodity=natural_gas&region=KZ-Karaganda'
Invoke-RestMethod 'http://127.0.0.1:8765/analytics/price-change?commodity=natural_gas&region=KZ-Karaganda'
Invoke-RestMethod 'http://127.0.0.1:8765/sources/status'
python BioReactor_AI/main.py chat --mode offline --message 'В Караганде 20 кг пищевых отходов. Что выгоднее: продать или переработать?'
python BioReactor_AI/main.py market import-csv --input C:/path/verified_quotes.csv
python BioReactor_AI/verify_stage3_5.py --update
```

`windows_days` содержит изменения за 7/30/90 дней только при наличии точных
датированных наблюдений на обоих концах периода; иначе `insufficient_history`.
Параметр `as_of=2026-09-30` задаёт дату сравнения. Новая ручка
`GET /scenarios/{id}/price-impact` пересчитывает сохранённый сценарий по новым ценам
тех же источников и объясняет изменения прибыли/рекомендации, сохраняя прежний результат.
Чувствительность и точка безубыточности доступны в `/scenarios/compare` при полных данных.

Наблюдения не перезаписываются; свежесть, регион, товар, единицы, НДС и тип цены
проверяются перед расчётом. Тестовые цены исключены из обычной выдачи. Не выполняются
автоматическая замена цены природного газа ценой биогаза, оценка дигестата по цене
минеральных удобрений и суммирование доходов взаимоисключающих сценариев.

[Отчёт этапа 3.5, источники и ручной импорт](reports/stage3_5_market_sources.md) ·
[Реальный диалог](reports/stage3_5/actual_agent_dialogue.md) ·
[Итоговая проверка](reports/stage3_5/verification.json).

```powershell
python BioReactor_AI/diagnose_market_tls.py
python BioReactor_AI/verify_stage3_5.py
```

Проверка включает 96 тестов, 30 настоящих HTTP-запросов к временному Uvicorn-серверу,
оба сохранённых BMP-артефакта через CLI и SHA-256 79 прежних файлов. Проверочный сервер
использует резервную копию реальных цен и останавливается после завершения.
Для обычной работы оставьте `market serve` запущенным в своём терминале.
Предыдущий этап: [отчёт 3](reports/stage3_market.md), 73 теста / 26 HTTP-проверок;
его отчёты и артефакты сохранены без изменений. Прогноз будущих цен не обучался.

## Agent v2 — этап 2

```powershell
python BioReactor_AI/main.py chat
```

Реализованы восемь проверяемых Python-инструментов, локальная LLM через Ollama,
онлайн-адаптер из переменных окружения и расчётный режим без LLM. Локальная
`qwen2.5:1.5b` проверена реальными запросами; реальная онлайн-генерация пока не
проверена, поскольку ключ и модель не настроены. Модели BMP не переобучались.

[Отчёт, архитектура и настройка](reports/stage2_agent.md) ·
[Настоящие диалоги и вызовы инструментов](reports/stage2/actual_dialogues.md).

```powershell
python BioReactor_AI/main.py providers --mode auto
python BioReactor_AI/main.py chat --mode offline
python BioReactor_AI/main.py chat --no-llm
python BioReactor_AI/main.py chat --context BioReactor_AI/examples/stage1_5_measured.json --message "Оцени BMP" --json
python BioReactor_AI/main.py tool get_reactor_status
python BioReactor_AI/verify_stage2.py
```

По умолчанию агент использует stage1_5; `chat --model stage1` выбирает исходный
CatBoost. `/reset` начинает новую партию, `/exit` завершает диалог. Научные
измерения и цены вводятся явно в JSON или полями `имя=значение`, а не выводятся
из догадок LLM. Переход к другому сырью сбрасывает характеристики и цены партии.
Оба ML-артефакта остаются доступны прежней командой `predict`.

Онлайн: задайте `BIOREACTOR_LLM_KEY` (или `OPENAI_API_KEY`),
`BIOREACTOR_LLM_MODEL` и при необходимости полный `BIOREACTOR_LLM_URL`.
Используйте модель, поддерживающую Chat Completions и JSON mode. В `auto` при
ошибке онлайн пробуется Ollama, затем ограниченный расчётный режим. Онлайн
отправляет вопрос, контекст партии и результаты инструментов выбранному API.
Локальная модель задаётся `OLLAMA_MODEL`, по умолчанию `qwen2.5:1.5b`.

47 тестов проходят; реальный trace, проверка CLI и контроль 57 прежних
артефактов сохранены в `reports/stage2/`. Mock датчиков возвращает пустые
показания; доступ к исполнительным устройствам отсутствует. Поиск научных
сведений работает по проверенному каталогу, не по всему интернету.

Экономика требует явных затрат, цен, даты, валюты, массы и доли извлечения;
условия объёма `gas_volume_basis` и тарифа `price_gas_volume_basis` должны
совпадать. Неизвестные TS/VS не подставляются. Для чернозёма и неподдерживаемых
смесей BMP и режим переработки не назначаются. Все прежние ограничения ML
сохраняются; независимого подтверждения улучшения этапа 1.5 нет.

## Этап 1.5: научный аудит и сравнение моделей

Разработка продолжена в той же структуре. Полный [научный отчёт](reports/stage1_5.md)
содержит nested GroupKFold, сравнение восьми семейств/контрольных конфигураций,
графики, ошибки редких категорий, диагностику области применимости и калибровку.

По nested CV на исходных train-лабораториях выиграл **SubstrateMedian**:
macro laboratory MAE 53.92 против 66.16 у исходной конфигурации CatBoost.
Это обученная на train медиана по категории, а не универсальная модель состава.
Числовые признаки используются для проверки применимости, но не меняют прогноз
этого baseline. Validation MAE 21.99 носит описательный характер: validation
и финальный test уже просматривались на этапе 1. Новый test не оценивался.

```powershell
python BioReactor_AI/main.py research
python BioReactor_AI/main.py predict --model stage1_5 --input BioReactor_AI/examples/stage1_5_measured.json
python BioReactor_AI/verify_stage1_5.py
```

`research` сохраняет результат в `models/stage1_5/` и `reports/stage1_5/`,
не перезаписывая исходные модели, исходники, разбиение и отчёты этапа 1.
Сетка поиска и протокол сохранены; повторный запуск повторяет те же fold.
Без `--model stage1_5` CLI продолжает загружать исходный CatBoost.
Проверка совместимости: 23 теста; журнал и реальные CLI-ответы в
`reports/stage1_5/verification.json` и `tests.log`.

`stage1_5_measured.json` содержит реальные входы бутылки 902 лаборатории E02
из исходного train. Это проверка загрузки модели, а не независимый эксперимент
или замеры вашей партии. Старый `wheat_straw.json` сохранён как пример формата;
его эталонная VS=0.91 отличается от эталона пшеничной соломы в наборе, поэтому
новый детектор правильно помечает его вне условного распределения.

Детектор OOD использует только train; выдаёт предупреждения о необычных
сочетаниях и ограниченной поддержке категории. Он не доказывает применимость.
90% интервал остаётся null. Экспериментальная полоса с радиусом 164 мл/г VS
покрыла 5/5 прежних validation-лабораторий, что не подтверждает её покрытие
в популяции. Синтетические обучающие наблюдения не создавались.

Ниже сохранена документация этапа 1.

Здесь находится отдельный исследовательский CLI и реально обученная BMP-модель.
Существующее приложение в родительской папке не подключено к новой модели.
Модули экономики, рекомендаций, LLM и датчиков относятся к следующим этапам.

## Что выполнено

Использованы оригинальные локальные файлы Hafner et al., сохранённые ранее в
`../biogas_ai_dataset/data/raw/hafner_2026_il_bmp`. Снимок скопирован вместе с
README, лицензией и SHA-256; повторная загрузка с GitHub в этом запуске не выполнялась.
Источник: <https://github.com/AU-BCE-EE/Hafner-2026-IL-BMP>,
статья: <https://doi.org/10.1016/j.biortech.2026.134136>. Атрибуция авторов —
в оригинальном README в `data/raw/hafner_2026_il_bmp`. Лицензия CC BY 4.0.

619 исходных бутылочных измерений; 6 строк с физически недопустимыми значениями
VS исключены и сохранены для проверки в `reports/excluded_rows.csv`.
Осталось 613 измерений из 31 лаборатории, шесть субстратов.
10 совпадений признаков и цели в исходных данных отмечены в аудите: разные
бутылочные повторы сохранены; одна лаборатория целиком попадает в одну часть.
Результат выше 1000 мл/г отмечен для проверки и не удаляется автоматически.

Mendeley <https://data.mendeley.com/datasets/g6z68g9ytb/1> описывает 1128 строк
из 59 источников и теоретические производные. Запрос к public-api 28.10.2026
вернул HTTP 403 Forbidden. Оригинальный `dataset_v1_theoretical.csv` отсутствует
локально и не использован. Структура этого CSV не исследована; описание сайта
не заменяет проверку файла. Необходимо проверить словарь, единицы, идентификаторы
источников и исключить признаки, вычисленные с использованием измеренного BMP
(например, коэффициент биоразлагаемости), прежде чем обучаться на нём.

BMP-data не добавлен без подтверждения лицензии. Zenodo 21079219 закрыт эмбарго
до 26.12.2026; его данные не использованы. Разные источники не объединялись.

## Запуск (из родительской рабочей папки)

Python 3.11+; фактический запуск — Python 3.13.13 на Windows. Для чистой среды:

```powershell
python -m venv BioReactor_AI/.venv
BioReactor_AI/.venv/Scripts/python.exe -m pip install -r BioReactor_AI/requirements.txt
BioReactor_AI/.venv/Scripts/python.exe BioReactor_AI/main.py train
BioReactor_AI/.venv/Scripts/python.exe BioReactor_AI/main.py predict --input BioReactor_AI/examples/wheat_straw.json
BioReactor_AI/.venv/Scripts/python.exe -m unittest discover -s BioReactor_AI/tests -v
```

В текущей среде CatBoost и Graphviz установлены локально в `.deps`, остальные
версии доступны в системном Python. `main.py` добавляет `.deps` при наличии.
Песочница Codex ограничивает чтение установленных с повышенными правами пакетов;
обучение и проверки здесь выполняются с разрешённым доступом вне песочницы.
Все фактические версии зафиксированы в `models/metadata.json`.

Повторное обучение перезаписывает артефакты внутри этой папки. Для исходников
из другого места: `main.py train --source C:/path/to/Hafner-2026-IL-BMP`.
Ожидаются README.md, LICENSE, data/BMP_calc.csv и data/setup.csv. Исходники
не меняются. Для повторной подготовки из скопированного снимка можно указать
`--source BioReactor_AI/data/raw/hafner_2026_il_bmp`.

Ручной импорт основного CSV:

```powershell
python BioReactor_AI/main.py import-csv --input C:/path/dataset_v1_theoretical.csv --dictionary C:/path/data_dictionary.md
```

Файл сохраняется отдельно с инвентаризацией и хешем; импорт не включает его
автоматически в обучение. Требуется научный аудит схемы и лицензии.

## Метод и фактический результат

Seed 2026. Разбиение по лабораториям: train 304 строки / 17 лабораторий;
validation 96 / 5; calibration 104 / 4; test 109 / 5.
Внутри train: GroupKFold(4), подбор двух вариантов RandomForest и CatBoost.
Импутация медианой и OneHotEncoder обучаются внутри каждого fold.
Алгоритм выбирается по validation MAE; модель замораживается перед calibration
и test, не переобучается на остальных частях. XGBoost не добавлялся: уже
сравниваются baseline, случайный лес и градиентный бустинг CatBoost.

На validation выбран CatBoost (MAE 23.84). На отложенных лабораториях:
MAE **80.38**, RMSE **131.99** мл CH4/г VS; R² **0.1732**.
Ухудшение на test существенно: перенос между лабораториями ограничен.
Это одно межлабораторное исследование, а не проверка на независимых публикациях.
Гиперпараметры и выбор модели после просмотра test не менялись. Повторный запуск
был нужен для исправления сохранения индексов исключённых строк; разбиение,
параметры и выбранная модель остались прежними.

Для 90% conformal-интервала используются максимальные ошибки по лаборатории,
чтобы не считать зависимые бутылки независимыми примерами. При четырёх
калибровочных лабораториях корректный конечный 90% интервал недоступен: CLI
возвращает null с объяснением. Числовой интервал не выдумывается.

Полное сравнение: `reports/test_metrics.csv`, `reports/validation_metrics.csv`,
`reports/train_cv.csv`. Ошибки по субстратам и индивидуальные прогнозы сохранены,
график — `reports/test_errors.png`; происхождение — `reports/provenance.json`.

## Ввод и ограничения

Все пять признаков обязательны: `substrate`, `c_vs_sub_m`, `c_vs_sub_f`,
`c_vs_inoc`, `ISR`. Первые три числовых параметра — концентрации VS в г/г
влажного материала; ISR — отношение масс VS инокулята и субстрата.
Фиксированная концентрация `c_vs_sub_f` относится к общему эталонному субстрату
оригинального исследования: нельзя произвольно назначать её другому сырью.
Пример wheat_straw.json демонстрирует формат, его числа не являются измерениями
вашей партии, обучающими данными или подтверждённым прогнозом для вашего сырья.

Допустимые категории и границы признаков находятся в `models/features.json`.
Проверка диапазонов отдельных признаков не доказывает применимость новой
комбинации: только аналогичные лабораторные условия и общие субстраты.
Чернозём, навоз, food_waste и смеси этой моделью не поддерживаются.
Масса, температура и объём реактора не заменяют лабораторные признаки.
Неизвестные поля контекста перечисляются как неиспользованные.

Если отдельно задана измеренная `vs_mass_kg`, потенциальный объём CH4 считается
по формуле `BMP * vs_mass_kg / 1000` в м³ при условиях приведения исходного BMP.
Влажная масса без VS не даёт объём метана. Это не прогноз фактической выработки
реактора. Модель не назначает температуру, pH, HRT, OLR и не управляет установкой.

## Следующие этапы

Получить основной CSV и словарь, провести аудит и проверку по независимым
исследованиям; накопить измерения собственной установки. Затем отдельно добавить
экономику с пользовательскими ценами и датами и рекомендации с источниками.
Будущий агент вызывает Python-инструменты predict_bmp, analyze_substrate,
recommend_conditions, calculate_profitability, get_reactor_status,
search_scientific_sources; результаты не должны вычисляться текстовой моделью.


## Substrate Advisor v7.6

В существующий Dashboard добавлены Substrate Advisor, Mixture Builder и режимы Simple/Scientific.

```powershell
python main.py dashboard --port 8765 --no-scheduler
```

[Инструкция и API](docs/substrate_advisor.md) · [Научный отчёт v7.6](reports/stage7_6_substrate_advisor.md).

15 распознаваемых категорий не означают 15 численных профилей. Сумма отдельных потенциалов не является измеренным выходом смеси.


## Dashboard и Smart Agent v7.7

Единый раздел «Сырьё и смеси», короткие ответы по текущему вопросу, память состава и переключение Simple/Scientific. Старые ссылки перенаправляются в объединённый раздел; прежние backend API и модели сохранены.

Запуск: python main.py dashboard --port 8765 --no-scheduler. Адрес: http://127.0.0.1:8765/dashboard/#/substrates.

[Инструкция](docs/smart_dashboard.md) · [Отчёт, тесты и измерения](reports/stage7_7_smart_agent_dashboard.md).

## Автономный научный агент v8.5

Чат использует Qwen3 8B, научные профили, инженерную проверку загрузки и частичную
экономическую оценку. Литературный потенциал, условный сценарий и измеренный
результат имеют разные статусы. Неизвестные расходы не считаются нулевыми.

```powershell
python -m pip install --upgrade --target .runtime-deps -r requirements-local-runtime.txt
$env:OLLAMA_MODEL='qwen3:8b'
$env:BIOREACTOR_LLM_CONTEXT='8192'
python main.py dashboard --port 8765
```

Ollama должна быть запущена с установленной моделью `qwen3:8b`. При недоступности
модели агент показывает причину и доступные локальные расчёты. Для ограничения
выгрузки слоёв на GPU можно задать `BIOREACTOR_LLM_GPU_LAYERS=16`; это замедляет
ответ, но не заменяет модель меньшей. По умолчанию бюджет анализа — 120 секунд
и четыре инструмента (`BIOREACTOR_AGENT_TIMEOUT`, `BIOREACTOR_AGENT_MAX_TOOLS`).

`BIOREACTOR_RESEARCH_ONLINE=0` отключает поиск метаданных публикаций в интернете.
Новые найденные публикации требуют проверки перед использованием их чисел.
Полный набор тестов: `python -m pytest tests -q`.

[Архитектура, реальные испытания и ограничения v8.5](reports/stage8_5_autonomous_scientific_agent.md).
