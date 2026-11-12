# Ограниченный аудит GPU gate и отмены Qwen3 8B

**Дата:** 2026-11-08 (Asia/Qyzylorda)  
**Статус:** **NOT READY для полного acceptance.** Тестовая отмена асинхронной job не останавливает уже выполняющуюся генерацию Ollama.  
**Объём:** статический разбор, детерминированные проверки и один короткий контролируемый live-тест фактической отмены. Полный acceptance-набор не запускался.

## Окружение и сохранность проекта

- Ветка `main`, исходный commit `38efb3aee0b4dbea3a5feac92e90e3a0e2a7d640`.
- На момент открытия рабочее дерево уже было сильно изменено: `git status --short --untracked-files=no` показал 7,911 tracked путей со статусом modified/deleted, включая каталоги зависимостей и прежние изменения проекта. Этот аудит не менял код приложения и тесты; добавлены только отчёты. Существующие данные/результаты этапов не удалялись.
- Windows, Python 3.13.13, Ollama 0.40.15, NVIDIA driver 581.80, CUDA 13.0.
- Ноутбук по BIOS registry: Lenovo product `82RB`, `Legion 5 15IAH7H`, BIOS `J2CN57WW`.
- GPU: NVIDIA GeForce RTX 3070 Laptop GPU, VBIOS `94.04.77.00.88`, 8,192 MiB VRAM.
- `nvidia-smi -q` сообщает: target temperature 87 °C, slowdown temperature 98 °C, shutdown temperature 101 °C, maximum operating temperature 105 °C; current/default power limit 115.82/115 W, maximum reported 140 W. Параметры не изменялись.
- Температура памяти и скорость вентилятора отображаются как `N/A`. WMI запросы параметров системы вернули Access Denied; модель ноутбука прочитана из BIOS registry. Поэтому состояние вентиляторов и отдельных датчиков не подтверждено.

## Вывод о P8

Текущий pre-run helper `reports/final_acceptance/gpu_gate.py` ждёт три последовательных измерения с интервалом 10 секунд. Каждое требует доступной температуры и device target, температуры строго ниже target, `HW Thermal Slowdown: Not Active` и **строго P8**. При отсутствующем измерении или любом другом P-state запуск блокируется. Это консервативный idle gate; P8 сам по себе не показывает запас охлаждения или отсутствие риска.

Документация NVIDIA определяет P-state как производительное состояние (P0 — максимальная производительность, P12 — минимальная), а не как оценку температуры/охлаждения: [NVIDIA `nvidia-smi` reference](https://docs.nvidia.com/deploy/nvidia-smi/index.html). Реальная проверка показала обычные переходы P8 → P0/P3 во время вычисления при температуре 64–67 °C и без thermal slowdown. Строгое P8 имеет смысл лишь как признак покоя перед прогоном; как условие безопасности оно не обосновано и может блокировать запуск по безвредной активности дисплея/драйвера.

Проверка температуры, аппаратного thermal slowdown и доступности их телеметрии оправдана и должна остаться. Во время активной генерации текущая функция `inference_stop_reasons` эти проверки делает, но её cancel-сигнал не прерывает блокирующий запрос к Ollama, поэтому фактической защитой от продолжения уже начатой генерации она сейчас не является.

### Предварительная телеметрия перед последним live-тестом

Измерения были сделаны при уже резидентной, но простаивающей модели; три снимка с интервалом 5 секунд:

| Время, местное | Температура / target | Utilization | VRAM | Мощность | P-state | HW slowdown |
|---|---:|---:|---:|---:|---|---|
| 15:45:38 | 62 / 87 °C | 7% | 4,236 / 8,192 MiB | 18.29 W | P8 | Not Active |
| 15:45:43 | 62 / 87 °C | 5% | 4,236 / 8,192 MiB | 18.23 W | P8 | Not Active |
| 15:45:48 | 61 / 87 °C | 5% | 4,236 / 8,192 MiB | 18.24 W | P8 | Not Active |

P8 не был единственным критерием допуска: также проверены доступность телеметрии, фактические температура и slowdown, отсутствие активной генерации, стабильная GPU utilization и отсутствие конкурирующего запроса Ollama.

## Статический разбор отмены

Подтверждено по коду:

1. `src/dashboard/job_api.py:53-60` для выполняющейся job только записывает `cancel_requested=1` и `current_stage='cancelling'`, после чего немедленно возвращает текущее состояние.
2. `src/dashboard/jobs.py:36-43` обнаруживает этот флаг только при следующем `Control.check()`. Heartbeat-поток отдельно проверяет флаг каждые 3 секунды, однако исключение остаётся в heartbeat-потоке и не прерывает поток выполнения модели.
3. `src/agent/providers.py:102-123,183-205` выполняет блокирующий `urllib` `urlopen(...).read(...)` до получения ответа/ошибки. У запроса нет переданного cancellation token, внешнего handle или закрытия сокета при нажатии Cancel.
4. `JobRuntime.run` (`src/dashboard/jobs.py:199-217`) может завершить job как `CANCELLED` после возврата `execute`. Это защищает от фиксации позднего ответа, но не останавливает генерацию, пока `execute` ждёт Ollama.

Следствие: текущая отмена ограничивает сохранение результата, но не фактическую inference-нагрузку. Это подтверждённый дефект, не гипотеза.

## Детерминированные проверки

Точная команда:

```powershell
python -m pytest tests/test_stage9_jobs.py tests/test_acceptance_gpu_gate.py -q -p no:cacheprovider --basetemp "$env:TEMP\pytest-gpu-cancel-audit-20261108"
```

**Результат: 25 passed, 1 существующее предупреждение Starlette/httpx, 13.50 s.** Среди них `test_running_cancellation_preserves_previous_state_and_events` проверяет отмену с искусственно заблокированной функцией: тест сам снимает блокировку через `release.set()`, после чего job становится `CANCELLED`. Он проверяет fence результата/состояние, но не отмену активного HTTP-вызова Ollama. Поэтому этот тест не подтверждает остановку генерации.

## Реальная проверка Qwen и отмены

Использован изолированный QA backend `evaluations/reliability_qwen_server.py` на `127.0.0.1:8774` с отдельной SQLite в `%TEMP%\bioreactor-gpu-cancel-audit-20261108.sqlite3`. Backend настроил фактический локальный `qwen3:8b`, контекст 8,192, локальное исследование без сети и обычный API-путь job. Рабочая рыночная база и порт 8782 не использовались. В Ollama server log и ответах подтверждено реальное выполнение Qwen, не fake provider.

Две первые контрольные job успели естественно завершиться до отправки отмены и **не засчитаны как тест отмены**. Первая попытка мониторинга также содержала ошибку парсинга target; она не послужила основанием для остановки процесса или признания теста успешным. После исправления наблюдение было привязано к реальному `processing task` в логе Ollama.

Третий запрос был коротким ASCII-вопросом: `Explain anaerobic digestion in one sentence.` Условия перед ним прошли телеметрическую проверку. Обнаружена задача Ollama `task 1009` (`processing task`) в 15:45:49; в 15:45:50.135 отправлен `POST /api/dashboard/jobs/cbbc82740d1a4e3e8808a4dcfa7c440d/cancel`. Ответ endpoint: `status=RUNNING`, `current_stage=cancelling`.

| После Cancel | Job | GPU: температура / utilization | VRAM | Мощность / P-state | Ollama |
|---:|---|---:|---:|---|---|
| 1 s | RUNNING / cancelling | 66 °C / 8% | 4,236 MiB | 62.79 W / P0 | слот task 1009 не освобождён |
| 5 s | RUNNING / cancelling | 65 °C / 40% | 4,236 MiB | 34.17 W / P3 | генерация продолжалась |
| 10 s | RUNNING / cancelling | 66 °C / 33% | 4,236 MiB | 33.76 W / P3 | генерация продолжалась |
| 12 s | RUNNING / cancelling | 67 °C / 34% | 4,236 MiB | 33.55 W / P3 | слот не освобождён |
| 13 s | CANCELLED / cancelled | 67 °C / 33% | 4,236 MiB | 31.94 W / P3 | Ollama записала release/idle |

В `%LOCALAPPDATA%\Ollama\server.log` записано, что task 1009 сгенерировала 188 токенов, время eval 15.718 s, весь `POST /api/chat` завершился HTTP 200 в 15:46:05 за 16.36 s. Этот POST завершился примерно через 15 секунд после Cancel. GPU utilization оставалась 30–40% до конца генерации; затем она упала до 2%. Значит, отмена **не оборвала** inference: Qwen доработала запрос до естественного конца, после чего job стала `CANCELLED` и ответ не был сохранён. Температурный пик этой короткой проверки — 67 °C, device target — 87 °C, `HW Thermal Slowdown` всё время оставался `Not Active`.

Windows `Get-NetTCPConnection` не показывал соединение backend→11434 даже в период, который подтверждён серверным логом как активный `POST /api/chat`; этот источник счётчика активных запросов в данной конфигурации невалиден. `GET /api/ps` показывает резидентные модели, а не состояние занятости: после завершения он продолжал показывать Qwen3 8B (`context_length=8192`, `size_vram=2,906,505,870 bytes`). Для live-проверки активной работы использованы Ollama slot log, состояние job и GPU utilization; у публичного `/api/ps` отдельного поля активного запроса нет.

В 15:46:40, после окончания генерации: 64 °C, 7%, 4,236/8,192 MiB, 18.51 W, P8, target 87 °C, `HW Thermal Slowdown: Not Active`. Остановлен только созданный этим аудитом QA backend (PID 17916); Ollama и пользовательские приложения не завершались. BIOS, драйвер, power limit, охлаждение и переменные окружения сервера Ollama не изменялись.

## Параллельность и размер контекста

Фактическая стартовая конфигурация Ollama из `%LOCALAPPDATA%\Ollama\server.log` (2026-11-08 10:28:31) содержит `OLLAMA_NUM_PARALLEL:1`, `OLLAMA_MAX_LOADED_MODELS:0`, `OLLAMA_CONTEXT_LENGTH:0`, `OLLAMA_KEEP_ALIVE:5m`. В `/api/ps` у реальной Qwen сессии показывался контекст 8,192. На уровне BioReactor queued runtime также использует общий lease `agent-execution-global`, то есть текущий активный путь не пытается запускать несколько job параллельно.

Итог по параллельности: **текущий Ollama уже ограничивает одну активную генерацию модели**. Дополнительное изменение concurrency для этого аудита не нужно. Ollama FAQ отмечает, что память масштабируется с произведением `OLLAMA_NUM_PARALLEL × OLLAMA_CONTEXT_LENGTH`; это подтверждает пользу контроля параллельности и контекста, но не обосновывает менять текущие значения без измерений: [Ollama concurrency/context FAQ](https://github.com/ollama/ollama/blob/main/docs/faq.mdx).

Итог по контексту: **снижать до 4,096 и заявлять сохранение всех функций пока нельзя**. Последние фактические промпты были существенно короче 4,096 токенов (максимум в контрольной завершённой генерации — 959 prompt tokens), однако не проверены длинная история, многошаговый научный поиск, смесь сырья и экономический синтез в худшем сценарии. Текущий срез GPU не показывает VRAM pressure: 4,236 MiB общих занятых из 8,192 при резидентной Qwen; сжатие контекста не требуется для данной проверки.

## Решение и следующие действия

- **Полный acceptance не запускался и сейчас не разрешён как проверенный следующий шаг:** действующий cancel не прекращает генерацию; прежний in-flight thermal guard, отправляющий тот же cancel endpoint, не обеспечивает немедленного останова inference.
- Минимальное исправление: передать отмену в provider HTTP transport и действительно оборвать активный запрос к Ollama (с сохранением текущего commit fence результата). Затем детерминированно доказать закрытие/отмену реального клиентского запроса; после этого выполнить один live-Qwen test и проверить в Ollama log, что задача освободила слот именно вследствие отмены, а utilization упала до фона до естественного конца ответа. До такой проверки не запускать полный или batch acceptance.
- Сделать P8 справочным сигналом простоя, а не обязательным safety criterion. Сохранить fail-closed поведение для недоступной температуры/target/thermal telemetry, stop при device target/thermal slowdown, а также явно учитывать активную нагрузку перед стартом. Универсальный температурный порог здесь не вводился.
- Оставить `OLLAMA_NUM_PARALLEL=1` и контекст 8,192 до отдельного теста длинных многоходовых функций. Ничего автоматически не менять в настройках сервера, драйвера, питания, BIOS и охлаждения.

### Проверки и ограничения

| Проверка | Точный артефакт/команда | Результат |
|---|---|---|
| Статический разбор | `src/dashboard/job_api.py`, `src/dashboard/jobs.py`, `src/agent/providers.py` | **FAIL** для требования остановки фактической inference: отмена только меняет DB-флаг; provider ждёт синхронный ответ. |
| Детерминированные тесты | команда pytest выше | **PASSED**, 25 тестов, 1 существующее предупреждение. Эти mock/unit тесты не проверяют отмену сети Ollama. |
| Реальная отмена Qwen3 8B | QA API `127.0.0.1:8774`, `job=cbbc82740d1a4e3e8808a4dcfa7c440d`, Ollama `server.log`, task 1009 | **FAILED**: generation и GPU нагрузка продолжались около 15 секунд после Cancel, до естественного окончания. |
| Охлаждение/телеметрия теста | `nvidia-smi --query-gpu=temperature.gpu,utilization.gpu,memory.used,memory.total,power.draw,pstate --format=csv,noheader`; `nvidia-smi -q` | **PASSED для короткого теста**: target/thermal telemetry доступны, peak 67 °C при target87 °C, slowdown inactive; это не гарантирует длинные прогоны. |
| Полный acceptance и браузер | Не запускались | **NOT RUN** по условию пользователя; отмена не прошла критерий. |
| Проверка всего dirty git diff | `git diff --check` | **NOT VALID**: рабочее дерево уже содержит тысячи изменений и недоступные файлы зависимостей; результат не считается успешной проверкой этого аудита. |

Общий результат: GPU в покое и на короткой отменённой генерации показал нормальную телеметрию без thermal slowdown. Однако программная отмена не останавливает реальный Qwen-запрос. Поэтому **NOT READY** к полному Qwen/Chrome acceptance, несмотря на успешные детерминированные unit tests.

Финальный снимок после завершения аудита, 15:53:53 местного времени: RTX 3070 Laptop GPU, 59 °C, 5%, 1,259/8,192 MiB, 18.05 W, P8; target 87 °C, hardware thermal slowdown inactive. `GET /api/ps` сообщил 0 загруженных моделей; порт QA `8774` не слушает, созданный аудитом backend PID 17916 остановлен. Ollama пользовательской сессии не завершалась.

## Исправление отмены активного Ollama запроса — 2026-11-08

### Первопричина и изменение

Подтверждённая первопричина прежнего дефекта: `JobRuntime` записывал отмену в состояние задания, но блокирующий `urllib` запрос к Ollama не владел cancellation signal и не имел закрываемого извне HTTP handle. В результате изменялся статус/commit fence, но уже начатая inference продолжалась.

Теперь cancellation signal принадлежит одному `Control` задания и передаётся из Dashboard API в `ConversationAgent`, `AgentRuntime9`, `HybridLLM` и provider. Provider использует стандартный `http.client`, регистрирует idempotent callback для текущего socket, выполняет `shutdown`/`close` при Cancel, читает cancellable Ollama NDJSON stream и освобождает response/socket в `finally`. Сигнал проверяется до запроса, после получения заголовков, при чтении каждого чанка и перед возвратом ответа. `ExecutionStopped` не превращается в fallback-ответ; stream не возвращает неполный JSON. Существующие HTTP timeout сохранены. Provider по умолчанию ограничивает запрос 45 s; `BIOREACTOR_LLM_REQUEST_TIMEOUT` валидируется в диапазоне 1–600 s; Runtime9 дополнительно ограничивает отдельный вызов оставшимся deadline, максимум 90 s. Job deadline по умолчанию 180 s. QA runner установил provider/agent timeout 150 s и job timeout 180 s, поэтому фактический вызов Runtime9 всё равно ограничен оставшимся budget и 90 s. Общий процесс Ollama, модель и контекст не останавливаются и не изменялись.

### Изменённые файлы

- `src/agent/cancellation.py` — новый потокобезопасный одноразовый сигнал и `ExecutionStopped`.
- `src/agent/providers.py` — cancellable HTTP transport, streaming NDJSON и ресурсная очистка.
- `src/agent/runtime9.py` — проверка сигнала до вызова модели.
- `src/dashboard/jobs.py` — signal на каждое задание; отмена при пользовательском Cancel, deadline и потере владельца.
- `src/dashboard/job_api.py` — немедленно передаёт Cancel активному `Control`.
- `src/dashboard/api.py` — связывает `Control.cancellation` с LLM и агентом; сохранение по-прежнему проходит через проверку владельца и отмены.
- `tests/test_provider_cancellation.py`, `tests/test_stage9_jobs.py` — регрессии transport, jobs, late result и параллельных заданий.

### Детерминированные проверки

Команда:

```powershell
python -m pytest tests/test_provider_cancellation.py tests/test_stage9_jobs.py tests/test_agent.py tests/test_stage9_runtime.py tests/test_autonomous_agent.py tests/test_conversation.py tests/test_advanced_conversation.py tests/test_analytical_response.py tests/test_stage9_verification.py tests/test_stage85_research.py -q -p no:cacheprovider --basetemp "$env:TEMP\pytest-ollama-cancel-final3-20261108"
```

Результат: **249 passed**, одно существующее предупреждение Starlette/httpx, 35.72 s. Набор проверил отмену до запроса, при ожидании ответа, в streaming, timeout, ownership loss, deadline, повторную отмену, поздний ответ, независимые параллельные запросы и запрет двойной/поздней записи. Отдельно провёл `python -m py_compile` для затронутых модулей и тестов — **PASSED**; `git diff --check` для этого списка файлов — **PASSED** (остались только предупреждения Git о LF→CRLF).

### Короткий реальный Qwen3 8B прогон

Окружение: Windows, Python 3.13.13, Ollama 0.40.15, `qwen3:8b` Q4_K_M, context 8192, RTX 3070 Laptop GPU, driver 581.80. QA server использовал отдельную временную SQLite-копию и production Dashboard/JobRuntime handlers на `127.0.0.1:8774`; production база не использовалась. Полный acceptance не запускался.

Перед live-проверкой: три sample GPU были 63 °C/20%, 64 °C/2%, 63 °C/24%, VRAM около 3,642–3,671 MiB, thermal slowdown отсутствовал; device target 87 °C, slowdown threshold 98 °C. Использование GPU колебалось из-за уже запущенных графических приложений; их не закрывал. Ollama показывал только resident Qwen и не показывал отдельный активный запрос.

QA SQLite для этих запусков: `%TEMP%\bioreactor_ollama_cancel_20261108_162242\isolated.sqlite3`. Два первых QA job завершились до Cancel из-за ошибки наблюдателя в тестовом скрипте: `66857fb131594444ad17094556f22240` завершился за 21.6 s; `c00eb351138a4cdb91378e45fcd88530` — за 30.2 s. Сначала скрипт считал task ID уникальным, хотя Ollama переиспользовала ID; затем regex искал prompt-eval строку в неверном формате. Они **не считаются проверкой отмены** и не были записаны в основную БД. В третьем запуске task counter по приросту лога сработал, но prompt-eval строка не была замечена; job был отменён на ограниченном 12-секундном fallback после начала Ollama task. Последующий разбор server.log нашёл `n_gen=100` и `n_gen=132` до Cancel. Windows socket query не показал active connection. Это позволило подтвердить generation progress до Cancel, но оставило гонку с естественным завершением и поэтому не считается точным измерением socket-close latency.

Фактический случай: session `93a9b1a29adb4b3ab9492b44b0322163`, job `edcdf7401af3443b8566b1319d55ae18`, Ollama task `418`. В server.log перед Cancel уже были строки генерации `n_gen=100` и `n_gen=132`; перед Cancel GPU был 66 °C, 35%, 3,644/8,192 MiB, 32.86 W, P3. Cancel вызван в `2026-11-08T14:24:18.2029636Z` (19:24:18 по Asia/Qyzylorda). API Cancel занял **43.9 ms**; job стал `CANCELLED` через **244.4 ms** от начала Cancel. После этого Ollama записала `stop processing`/slot release для task 418 в ту же секунду; новых строк `n_gen` для task 418 и обычной строки финального eval timing не появилось. GPU через короткий интервал: 65 °C, 6%, 3,644 MiB, 27.18 W, P3. Qwen оставалась загруженной в VRAM (`/api/ps`, около 2.91 GB model VRAM), что ожидаемо и не считается продолжающейся генерацией.

Результат job не был записан: result reply был `null`, ход диалога имел `reply=null`, `state_version=0`. Ollama записала HTTP 200 и итоговый `n_tokens=309` при освобождении слота; это не является счётчиком токенов после Cancel. Последняя отдельная token-progress запись до Cancel — `n_gen=132`; сколько дополнительных токенов успело появиться между последним progress-log и закрытием, Ollama 0.40.15 отдельно не сообщает.

Прямой live TCP close момент **не измерен**: `Get-NetTCPConnection` не вернул строку активного соединения QA PID на снимке перед Cancel. Поэтому 43.9 ms — измеренная верхняя граница до ответа Cancel API, не независимая телеметрия сокета. Код вызывает закрывающий callback синхронно до ответа маршрута; детерминированный HTTP server тест непосредственно увидел закрытие peer socket. В live-логе Ollama slot освободился в ту же секундную отметку, что Cancel, но временная точность server.log составляет одну секунду. Продолжения `n_gen` после Cancel не наблюдалось. Эти ограничения зафиксированы, а модель и её параметры не менялись.

### Итог

**Статус: PARTIALLY FIXED для асинхронного Dashboard Job пути.** Код и детерминированные проверки подтверждают, что активный provider socket закрывается и поздний ответ не сохраняется. В реальном job Ollama логировала генерацию до `n_gen=132`, после Cancel task освободил slot, GPU utilization снизилась, job стал `CANCELLED` за 244.4 ms и ответ не сохранился. Однако ОС не показала соединение в момент Cancel; Ollama записала длительность HTTP запроса 12.75 s, тогда как Cancel пришёл примерно через 12.90 s после создания job. С точностью server.log в одну секунду нельзя исключить, что Cancel пришёл непосредственно перед естественным завершением или уже после окончания model stream. Поэтому live-прогон подтверждает остановку slot/job и отсутствие поздней записи, но не доказывает с нужной точностью, что Cancel оборвал inference до её естественного конца. Для снятия этой неопределённости требуется повторный ограниченный live-прогон с измеряемым активным socket/более точной отметкой события Cancel.

Ограничения области: legacy synchronous `/api/dashboard/chat/sessions/{id}/messages` не получает `JobRuntime` signal и остаётся non-cancellable; это отдельно от исправленного асинхронного маршрута. Полный Chrome/Qwen acceptance — **NOT RUN**. `OLLAMA_NUM_PARALLEL`, модель, квантование, контекст, cooling, BIOS и драйвер не менялись; пользовательские процессы не завершались. Созданный audit backend PID 19472 завершён, порт 8774 закрыт; общий Ollama процесс оставлен работающим. Финальная проверка: Ollama 0.40.15 отвечала, активная модель выгрузилась по keep-alive, RTX 3070 Laptop GPU была 63 °C, 32%, 671/8,192 MiB, 18.88 W, P8; HW Thermal Slowdown — Not Active.

### Ограниченный повторный прогон после неполной live-корреляции

Перед попыткой отмены по первому `n_gen=100` три sample RTX 3070 Laptop GPU: 67 °C/7%/798 MiB, 68 °C/8%/805 MiB, 67 °C/22%/807 MiB. Device target 87 °C, slowdown threshold 98 °C, HW/SW thermal slowdown неактивен; Ollama не показывала загруженной модели. Тест был ограничен одной QA job; пользовательские процессы не менялись.

Эта job не дошла до генерации и **не является тестом отмены**. QA job `63f78328b288474aa5a7ee694c15550d` завершилась как `COMPLETED`/`deterministic_partial_provider_failure`, provider `qwen3:8b` вернул HTTP 500 после 19.36 s. В `%LOCALAPPDATA%\Ollama\server.log` зафиксировано `CUDA error: shared object initialization failed`; дочерний `llama-server` завершился с Windows exit `0xc0000409`. Task 100 или `n_gen` не появился, Cancel не отправлялся. Температура после ошибки была 70 °C, utilization 17%, VRAM 840 MiB, slowdown — Not Active. Ollama API (`0.40.15`) продолжала отвечать, `/api/ps` был пуст; audit backend PID 18800 остановлен, порт 8774 закрыт. Ollama не перезапускалась; драйвер, питание, BIOS и охлаждение не менялись.

Итоговый статус остаётся **PARTIALLY FIXED**. Для завершения live-критерия нужна среда, где Qwen стабильно стартует, и короткая повторная job, отменённая по наблюдаемому `n_gen`/socket событию до обычного завершения. До этого не запускать полный acceptance; не трактовать данный HTTP 500 или две предыдущие естественно завершившиеся QA job как подтверждение отмены.

### Cancellation transport and GPU gate hardening — 2026-11-08

Исправлены две статически подтверждённые задержки отмены: callback теперь регистрируется до TCP connect; соединение устанавливается неблокирующим сокетом с проверкой cancel во время ожидания. HTTP send больше не держит lock, который блокировал callback; `auto_open=0` запрещает позднее reconnect. TLS handshake также проходит с cancellable readiness waits. В production-коде новые потоки не добавлены. Синхронный OS `getaddrinfo` остаётся неперерываемым ограничением для удалённых hostname; локальный Ollama URL использует numeric loopback.

GPU admission gate больше не требует P8. P-state остаётся в sample как диагностический параметр; thermal limit и HW slowdown checks остаются обязательными, отсутствующая thermal telemetry блокирует запуск, wait budget остаётся ограниченным.

Команда: `python -m pytest tests/test_provider_cancellation.py tests/test_stage9_jobs.py tests/test_agent.py tests/test_stage9_runtime.py tests/test_autonomous_agent.py tests/test_conversation.py tests/test_advanced_conversation.py tests/test_analytical_response.py tests/test_stage9_verification.py tests/test_stage85_research.py tests/test_acceptance_gpu_gate.py -q -p no:cacheprovider --basetemp "$env:TEMP\pytest-ollama-cancel-hardening-final-20261108"` — **260 passed**, одно прежнее предупреждение Starlette/httpx, 33.08 s. Включены детерминированные проверки pending TCP connect, blocking send, HTTPS handshake, socket cleanup, timeout, независимых jobs и late-commit fence. Полный вывод сохранён в истории инструментов; real Qwen/browser/full acceptance не запускались.

Ресурсы восстановились: последняя read-only выборка 20:56:28 — 15.8 GiB RAM, 8.53 GiB свободно, commit headroom 22.8 GiB; RTX 3070 Laptop — 58 °C, 16%, 644/8,192 MiB, thermal slowdown inactive; `ollama ps` пуст. Это выше ранее успешной той же модели выборки RAM 6.1 GiB, но CUDA root cause остаётся неизвестной.

Статус остаётся **PARTIALLY FIXED** для end-to-end cancellation: deterministic coverage улучшена, но live Qwen cancellation в этой сессии не проверялась. Статус среды **READY FOR ONE LIMITED LIVE TEST после свежего preflight**, не full acceptance. Legacy synchronous route остаётся non-cancellable; CUDA crash требует остановки без повторных запусков, если повторится. Подробные условия в `reports/memory_and_cancellation_hardening.md` и `reports/limited_qwen_cancellation_live_test.md`.

### Resource and verification correction - 2026-11-08 21:07 local

This append-only correction supersedes the 20:56 resource snapshot and the earlier 33.08-second test duration in this audit's hardening section. The verified command used basetemp `pytest-ollama-cancel-hardening-verified-20261108`; result: **260 passed**, one existing Starlette/httpx deprecation warning, **32.50 seconds**. Compile and scoped whitespace checks passed. No Qwen inference, browser E2E, or full acceptance was run.

At 21:07:34 local, read-only counters showed 8,840 MiB available RAM, commit 12,220,874,752 / 36,832,231,424 bytes (about 22.92 GiB headroom), and pagefile usage about 2.06%. RTX 3070 Laptop GPU was 56 C, 19% utilization, 622/8,192 MiB, 17.89 W; target 87 C, slowdown 98 C, shutdown 101 C, HW/SW thermal slowdown inactive. P-state P8 is diagnostic only. Ollama 0.40.15 was responsive; `ollama ps` was empty. Exact pagefile size is unavailable.

The deterministic transport and GPU-gate regressions pass, but live Ollama cancellation remains **PARTIALLY FIXED** until the bounded run in `reports/limited_qwen_cancellation_live_test.md` demonstrates cancellation during observed active generation and rules out a late result. The CUDA runner failure has no confirmed root cause. Legacy synchronous chat remains non-cancellable; full acceptance and FIRO readiness are not established.

The status above means prepared for the one-shot test only: run the documented fresh three-sample admission check immediately before inference. The single 21:07 snapshot does not itself satisfy that execution-time gate.

### Controlled Qwen cancellation attempt - 2026-11-08

**Run status: INCONCLUSIVE.** One isolated asynchronous job ran against the real local `qwen3:8b` model. The three-sample resource gate passed, the runner loaded successfully, and the model produced output, but the job reached `COMPLETED` before Cancel was sent. No second model request was made.

Preflight at 21:20:13.650, 21:20:23.608, and 21:20:33.631 +05:00: available RAM 8,690 / 8,626 / 8,612 MiB; commit headroom 24,653,291,520 / 24,592,801,792 / 24,581,529,600 bytes; pagefile use 2.01% in all samples. RTX 3070 Laptop temperatures 56 / 55 / 56 C against device target 87 C; slowdown threshold 98 C; HW/SW thermal slowdown Not Active. GPU utilization was 9 / 9 / 10%, VRAM 618 / 618 / 617 MiB, P8 recorded diagnostically only. Ollama 0.40.15 reported no loaded model, `/api/ps` empty, and no established Ollama client connections before the job.

The test used isolated backend PID 22660 on port 8774 and temporary SQLite `%TEMP%\bioreactor_cancel_one_20261108_212134.sqlite3`. Job `a163c4bd1a4c47aeb13248ff2c8e65a7` was submitted at 21:23:51.859 +05:00. Ollama started a real llama.cpp runner at 21:23:55.190 with context 8192, one parallel slot, and 16 GPU layers; `model loaded` was logged. Post-run `/api/ps` identified Qwen3 8B Q4_K_M, context 8192, with 2,906,505,870 bytes resident in VRAM. No CUDA error was logged.

The job completed at 21:24:45.071890 +05:00, status `COMPLETED`, with a saved reply, two partial/tool results, and session state version 1. One Dashboard job invoked three sequential Ollama tasks: task 0 generated 243 tokens, task 248 generated 61, and task 320 generated 69. All three logged normal `stop processing` releases. Runner `n_gen` timing records were only available to the observer along with task completion/release output; they did not provide a reliable live trigger in this run. The first status snapshot at 21:24:07.491 showed `RUNNING/understanding`, task 0 processing, but no live token counter or provider socket.

Cancel was **not sent**. Cancel latency, HTTP close timestamp, post-Cancel tokens, transition to `CANCELLED`, cancel-triggered slot release, and late-result behavior are all **NOT MEASURED**. This run is not evidence for or against live cancellation. GPU at 21:28:25.982 was 56 C, 28%, 3,606/8,192 MiB; HW/SW thermal slowdown inactive. The Qwen model remained resident under normal Ollama keep-alive.

The QA backend and its log-tail monitor were stopped. Only test-owned PID 22660 was explicitly stopped after Ctrl+C left it alive without a listener. Port 8774 was closed; shared Ollama PID 20424 remained running. Raw Ollama log slice and job/resource records are preserved under `%TEMP%` and listed in `reports/limited_qwen_cancellation_live_result.md`.

Overall cancellation remains **PARTIALLY FIXED** pending an actual live cancellation. The CUDA crash's underlying cause remains unconfirmed. Do not retry this one-shot run or treat this result as full acceptance/readiness. The detailed result and evidence paths are in `reports/limited_qwen_cancellation_live_result.md`.

### Deterministic live-trigger remediation — 2026-11-09

**Previous live-test disposition remains INCONCLUSIVE.** Review of `reports/limited_qwen_cancellation_live_result.md` confirms why: the observer saw `RUNNING/understanding` at 21:24:07.491, 15.6 s after job submission, which did not prove generation; `n_gen`/runner timing became visible only with natural task release; the job completed at 21:24:45.071890 before any Cancel. Exact poll cadence, completion-log observation time, and generation-to-detection delay were not captured. No Cancel latency or socket-close time can be inferred from that run.

The QA method now uses the first nonempty Ollama NDJSON `message.content` chunk with `done=false`, reported synchronously by the active provider stream reader. An opt-in observer on the job's `CancellationSignal` sends one loopback POST to the ordinary Dashboard Cancel endpoint; the provider records event, transport-close, and request-close timestamps. The loopback HTTP attempt is bounded to 1 s; failure invokes local socket cancellation and remains BLOCKED. Natural `done=true`, terminal jobs without a live signal, and a 45 s missing-signal timeout do not become VERIFIED. Ollama logs are only post-Cancel corroboration.

Added `evaluations/cancellation_timing.py`, `evaluations/controlled_cancellation_server.py`, and `tests/test_cancellation_timing.py`; minimal event hooks in `src/agent/cancellation.py`, `src/agent/providers.py`, and `src/dashboard/jobs.py` are inert unless the isolated QA wrapper installs the observer. Updated `reports/limited_qwen_cancellation_live_test.md` with the replacement procedure, bounded waits, evidence requirements, and conservative classification. No model inference, browser E2E, acceptance suite, Ollama setting, system setting, or user process was touched in this update.

Focused deterministic command: `python -m pytest tests/test_cancellation_timing.py tests/test_provider_cancellation.py tests/test_stage9_jobs.py -q -p no:cacheprovider --basetemp="$env:TEMP\\pytest-live-cancel-timing-final6"` — **44 PASSED**, one existing Starlette/httpx deprecation warning, 21.51 s. Covered first-chunk HTTP Cancel trigger/socket close, no trigger after natural stream completion, bounded 1 s no-signal timeout, telemetry BLOCKED, duplicate suppression, exact timestamp ordering, conservative VERIFIED requirements, late terminal state, provider cancellation, and job cancellation regressions. `python -m py_compile ...` — **PASSED**. A no-lifespan TestClient smoke of the isolated QA wrapper returned `arm=200`, `status=200`, incomplete-evidence=`INCONCLUSIVE`; it did not start an inference worker.

**Readiness:** The deterministic trigger and bounded harness are prepared for a single future controlled live run after a fresh three-sample resource gate. End-to-end real-Qwen cancellation remains **NOT VERIFIED**; no GPU preflight or Qwen request was run as part of this remediation.
