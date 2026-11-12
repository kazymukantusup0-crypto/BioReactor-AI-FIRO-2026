# Farmer consultation — implementation audit, 2026-11-12

Implemented, acceptance PARTIAL; FIRO NOT READY. Existing main / starting HEAD 38efb3aee0b4dbea3a5feac92e90e3a0e2a7d640; substantial user changes already existed and are preserved. No model training, release, dependency change, production model switch or resource-gate change. The initial checkpoints below are historical; the final assessment at the end supersedes their pending-test statements.

**Последнее продолжение:** интерактивный экспериментальный Chat теперь действительно подключён к защищённой Qwen3 4B. Новый браузерный запрос52л/180л прошёл с NLU трёх задач, четырьмя инструментами, принятым синтезом, выгрузкой и восстановлением после reload. Финальный backend-агрегат484PASSED; frontend81PASSED/build PASSED. Продолжение того же диалога до25°C прошло на Python с сохранением52л/180л; модельный ход BLOCKED при6650.4MiB<6656MiB. Подробности и ограничения — в последнем разделе «Продолжение: настоящий интерактивный Chat». Ранние ограничения ниже о неподключённом UI/непроверенном регионе пересмотрены именно этим экспериментом, а не удалены.

## Confirmed gaps and implementation checkpoint

The previous literature-estimate final projection replaced the economic and process parts of a compound answer. The model-selection loop could also spend the four-call QA budget before synthesis. Added a typed projection of the current farming task and a two-selection-stage budget for these compound tasks; remaining required existing tools execute deterministically before the reserved synthesis. Each tool's actual origin remains in the trace. This is the existing runtime/registry, not a second agent or per-question scenario handler.

The reviewed pig profiles had no density. A compatible primary volumetric-solids path was identified in Chae et al. (2008), DOI [10.1016/j.biortech.2006.11.063](https://doi.org/10.1016/j.biortech.2006.11.063): source feed VS 16310 mg/L and observed ultimate batch methane yields at 25/30/35 °C. Source-specific scenarios use volume × kgVS/L × mLCH4/gVS with Python unit conversion, without inventing density or wet mass. Full publisher page returned403; the indexed primary abstract and Feed characteristics section supplied these values. No access bypass. Gas-reference numerical details and a fixed duration remain unverified, so these are conditional endpoint references, not guaranteed day-yields or a user-reactor calibration.

For temperature comparison, [Lin et al.2016](https://link.springer.com/article/10.1186/s12934-016-0491-x) was reviewed. Its seeded semi-continuous pig-slurry experiment informs qualitative mesophilic/thermophilic tradeoffs, not a transferable yield multiplier or automatic heater setpoint. The existing SI heat engine is reused; absent thermal mass, insulation, ambient temperature and duration remain unknown rather than guessed.

Current changes: typed consultation projection and shared-tool result composition; concentration-based source route in the existing advisor calculator; three distinct temperature-indexed source profiles; multi-part answer sections; duration/use/mode entities; shared process-energy worksheet; regression tests. First smoke suite:126 passed /3 failed (two compatibility issues in single economic request behavior and an expected source-catalog count change). Fixed single-request planning order and preserved the existing partial-response heading; profile-count assertion updated from18 to21 for three newly reviewed entries. Final regression and real-Qwen evaluation remain pending at this checkpoint.

## Safety and pending evidence

Real inference has NOT RUN for this change yet. Existing Qwen3 4B QA admission6656MiB, runtime RAM/commit/VRAM limits, temperature/thermal checks, one serial request, cancellation and targeted unload are unchanged. Production API11434 is used; no second Ollama server or new QA client is created. Next: finish deterministic regressions, extend the existing QA client's limited mode to unfamiliar farming cases and a two-turn task, then run sequentially only when its fresh admission permits.

## Farmer consultation checkpoint - 2026-11-12

Existing runtime now decomposes general farm questions into methane, temperature and economics, reserves synthesis after at most2 model-selected tools, and executes remaining required Python checks within the existing tool/time cap. Reviewed volumetric-solids source path allows pig-slurry references without guessed density. Arbitrary UTF-8 question and optional follow-up are accepted by the existing limited QA client; no new server/client or production model switch.

Deterministic suites passed213 (later scoped verifier tests pending final aggregate). Real Qwen baseline: pig mandatory case first PARTIAL (private scenario IDs in model prose), corrected public formatting retest accepted without fallback; cow FAIL (unsupported unprofitability and wrong m3/L units, rejected and safe Python content delivered); food technical PASS / automatic science PARTIAL (mass-based science was not_applicable). Strengthened denominator validation and scientific-check coverage; original traces preserved. Source facts and numerical/scientific checks were not weakened. Next: unfamiliar straw/comparison/dialogue cases with unchanged6656MiB admission and targeted unload; report reports/farmer_consultant_20261112.md. Overall NOT READY.

## Промежуточный результат перед подключением интерактивного Chat — 2026-11-12

**Общий статус: PARTIAL / FIRO NOT READY.** Работает общий многозадачный маршрут существующего Chat, не обработчик одной фразы. Настоящая Qwen выбирает инструменты и формирует отдельный краткий вывод. Python публикует расчёты, единицы, применимость, источники, ограничения и вопрос. Содержательные результаты инструментов сохраняются при отклонении модельного текста. Это программная интеграция, не обучение модели и не независимая научная сертификация.

Шесть новых одноходовых запросов последнего замороженного варианта завершены с настоящей Ollama; начальный ход седьмого выполнен, второй остановлен при достижении существующей локальной температурной границы82°C. Повторных GPU-запусков после этого не было. Последующий статус `/api/ps`: `models=[]`. Отдельная поздняя поправка происхождения региона проверена детерминированно, но после неё новый live-запрос не запускался.

### Реализованные общие механизмы

- `ConsultationInputs`: сырьё, объём сырья, номинальный объём, температура, режим, срок, использование газа, регион, происхождение параметров, литературные допущения и отдельные задачи. Пользовательское значение не становится лабораторно измеренным только потому, что пользователь его подтвердил.
- Существующий Runtime9: компактный NLU, максимум2 модельных шага выбора инструментов, затем обязательные недостающие проверки и зарезервированный синтез. В QA максимум4 реальных обращения на job; явно выбранный двухходовый эксперимент ограничен8 обращениями и240с суммарно. Не создавался второй агент, калькулятор или Ollama server. Контроллерные вызовы отмечаются `controller_required_evidence`, не приписываются модели.
- Подключены существующие `search_scientific_sources`, `estimate_methane_yield` / `assess_substrate_potential`, `assess_process_evidence`, `evaluate_partial_economics`. Вложенные расчёты по-прежнему используют advisor/economics/SI heat engine.
- Финальный модельный контракт содержит два поля качественного объяснения. Модель видит результаты инструментов при планировании; на этапе публикации получает короткую проекцию проверенных выводов. Числовые блоки и ссылки выбирает Python; это явно отмечено в диагностике. Не следует считать эти ссылки модельным выбором. Числа, новые количественные прогнозы и внутренние ID в модельном тексте не допускаются этим контрактом; арифметический и научный verifier не отключались.
- Сравнительный контекст сначала охватывает каждый материал, затем повторные исследования. Это устраняет фактическое выпадение пищевых отходов из контекста сравнения.
- Типизированные величины различают объём сырья/реактора/CH₄ и длительность; новая защита запрещает подменять суммарный объём газа удельным `м³/л` или `м³/день`.
- Температурный консультант возвращает обсуждаемые варианты, неопределённость и общую тепловую ведомость. Он не вычисляет универсальный оптимум, не подставляет массу из номинальных литров, не управляет нагревателем. Без теплоёмкости, фактической загрузки, утепления, температуры среды и срока полный расход остаётся неизвестным.
- Экономика использует существующее рыночное хранилище и расчётные альтернативы. Если отсутствуют применимые цены и полные расходы, не выдаёт прибыль. Исправлена обнаруженная при просмотре реального лога ошибка: наличие условного региона в проекции `facts` больше не превращает его в пользовательски подтверждённый регион. При прямом старом внутреннем вызове без provenance сохранена совместимость; типизированный Chat передаёт provenance.
- Память сохраняет партию при изменении температуры; литературный температурный вариант выбирается заново. Условные25°C остаются допущением. При новом материале/партии старые материально-зависимые параметры инвалидируются существующим механизмом.
- Dashboard использует существующие секции ответа, добавлен режим «Консультация для хозяйства», понятные обозначения срока/использования газа/жидкого состояния/жижи. Источники видны по ссылкам, диагностика закрыта. История хранит исходные tool outputs и модельный черновик отдельно от публичного текста.

### Научная база и пример78л

В существующий каталог добавлены три различных температурных профиля одного исходного опыта Chae et al.2008, не три независимые публикации. Указанные в источнике концентрации TS23.885г/л и VS16.31г/л позволяют обойти отсутствие плотности без её выдумывания:

```text
78 L × 16.31 gVS/L = 1272.18 gVS
1272.18 × 327 mLCH4/gVS / 1000 = 416.00286 LCH4  (25°C в опыте)
1272.18 × 389 mLCH4/gVS / 1000 = 494.87802 LCH4  (30°C в опыте)
1272.18 × 403 mLCH4/gVS / 1000 = 512.68854 LCH4  (35°C в опыте)
```

Это **отдельные условные литературные конечные выходы**, не статистический диапазон, не фактические измерения этой партии, не прогноз за30дней. Исходное сырьё — разбавленная свиная жижа из конкретного хозяйства; экспериментальные умеренные загрузки5–20% об./об. нельзя автоматически переносить на78л в200л сосуде. В ответе это ограничение указано. Для рабочего объёма, воды, инокулята и числа циклов данных нет; число партий не назначается. Подтверждённая концентрация на литр используется только при явном включении литературного режима, с применимостью и источником. Измеренные/массовые маршруты не получили неявную плотность.

Первоисточник: [Chae et al., The effects of digestion temperature and temperature shock on the biogas yields from the mesophilic anaerobic digestion of swine manure](https://doi.org/10.1016/j.biortech.2006.11.063). Доступный индекс первичного издателя содержал abstract и Feed characteristics; прямой доступ издателя403, обход не выполнялся. Полная кривая накопления, точное определение STP и влажность не проверены по доступным разделам. Поэтому для новых концентрационных вариантов корректная абсолютная энергетическая/денежная оценка не установлена; её отсутствие не подменено универсальной константой.

Для обсуждения мезофильного/термофильного режима добавлен [Lin et al.2016, Microorganism-regulated mechanisms of temperature effects on the performance of anaerobic digestion](https://link.springer.com/article/10.1186/s12934-016-0491-x). Это другое исследование со своими условиями: количественные множители выработки из него не переносятся на Chae или пользовательскую установку. Около35°C предложено как отправная точка инженерного обсуждения, не доказанная уставка. База нагрева — существующие формулы DOE/PNNL, не универсальная теплоёмкость навоза.

Рыночное QA-хранилище изолировано и не содержит подходящего тарифа. В реальных ответах нет выдуманного дохода вKZT. Для старых совместимых газовых профилей рассчитаны условные энергетические альтернативы, с явно указанными сценарными коэффициентами сбора газа/КПД. Для свиной концентрационной цепочки остаются формула и ограничения. Проверка настоящего коммерческого тарифа/операционных расходов на живом запросе **NOT RUN**; наличие вызванного экономического инструмента не означает подтверждённую прибыль.

### Последняя реальная серия и независимый просмотр содержания

В этой таблице «независимый» означает отдельное чтение разработчиком по исходному вопросу и инструментальным данным, вне автоматического verifier. Это не слепая внешняя экспертиза и не untouched holdout. PASS автоматического verifier не подменяет качество ответа. Полные исходные запросы, необработанный синтез Qwen, все доставленные ответы, ссылки, имена инструментов, происхождение вызовов и метаданные генерации: [actual_answers.md](farmer_consultant_20261112/actual_answers.md). Машинная таблица/хеши: [live_summary.json](farmer_consultant_20261112/live_summary.json).

| Сценарий | FastAPI + модель | Проверенные данные пользователю | Независимая оценка всей консультации | Ограничение |
|---|---|---|---|---|
| Свиной навоз78л /200л, метан+экономика+температура | PASS,4 вызова | PASS:416/494.88/512.69л, отдельные условия, рабочий объём неизвестен | PARTIAL | Вывод Qwen слишком общий. В недоставленном поле explanation ошибочно написано «потенциал не определён», хотя он рассчитан. Verifier это не обнаружил. Денежная и полная тепловая оценка отсутствуют обоснованно. |
| Коровья жижа41л /260л,30дней | PASS,4 | PASS:843.95–1187.84л потенциала; выход за30дней не установлен | PARTIAL | «Режим изучен, но не оптимум» двусмысленно: проверенного оптимума нет, это не доказательство неоптимальности. |
| Пищевые отходы3.2кг /85л, обогрев | PASS,4 | PASS:203.57л условного потенциала; энергетические сценарии, без прибыли | PASS для доставленного ответа; сырой синтез PARTIAL | Недоставленная фраза «метан не выработан установкой» утверждает неизвестное состояние установки; не использовать как обучающий target. |
| Сухая солома4.2кг /250л | PASS,4 | PASS:679.54л условного потенциала,6.775кВт·ч условной энергии | PARTIAL | Та же двусмысленная фраза «не оптимум». Полезная энергия не названа прибылью; экспериментальная подготовка остаётся условием. |
| По7кг навоза КРС и пищевых отходов | PASS,4 | PASS:показаны оба материала; больший потенциал опубликованного образца пищевых отходов не объявлен лидером по чистой прибыли | PASS для этой ограниченной задачи | Нет подходящего тарифа и расходов; фактическая форма сырья требует уточнения. |
| Температура свиной жижи, без чисел | PASS,4 | PASS:обсуждение35/55°C, без выдуманной массы/выработки и команд | PARTIAL | Нерелевантное вступление о численном ориентире метана; вопрос о количестве менее полезен, чем о температуре/теплопотерях. |
|63л /210л → «А если25°C?» | Первый ход PASS; второй CANCELLED | Первый ответ сохранён;25°C видно как ASSUMED в preview,63л/210л не потеряны | BLOCKED/INCOMPLETE | Температура GPU достигла82°C во втором ходе; итоговый ответ второго хода не создан. Не засчитывается как успешный диалог. |

Автоматический научный verifier: `checked=true`, status`passed` у всех шести завершённых ответов и первого хода диалога. Независимая арифметическая проверка прошла у расчётных ответов. Для вопроса без чисел арифметика `not_applicable`, не PASS. Проверка чисел **модельного** качественного черновика `checked=false/not_applicable`, потому что в нём нет количественных утверждений; числа из Python проверены отдельно. Эти статусы нельзя объединять в «всё научно верифицировано».

### Фактические ресурсы последней серии

| Сценарий / конец имени trace | Время первого запроса,с | Минимальная свободнаяRAM,MiB | Макс.commit,MiB | Макс.VRAM,MiB | Макс.GPU,°C | Адресная выгрузка,с |
|---|---:|---:|---:|---:|---:|---:|
|pig /1794471880875053300|8.857|6753.1|17337.1|3873|66|0.197|
|cow /1794471892152417300|9.811|6934.1|17164.2|3873|70|0.186|
|food /1794471904262217500|8.185|6922.7|17175.5|3873|72|0.198|
|straw /1794471914850370900|8.458|6909.2|17175.0|3874|75|0.185|
|compare /1794471926100467800|10.807|6754.1|17325.5|3873|77|0.200|
|no_numbers /1794471939974119000|8.316|6884.9|17202.0|3873|79|0.185|
|dialogue /1794471950929741800|9.012 первый ход; второй прерван|6436.1|17647.3|3872|82|0.257|

Все значения — наблюдавшиеся выборки, не доказанные непрерывные аппаратные пики. Перед каждым сценарием выполнен свежий допуск существующего QA. После каждого `after.running_models=[]`; проверка выгрузки подтверждена, не выведена из одного падения utilization. Отсутствие модели после выгрузки и явный CANCELLED без reply второго хода сохранены. При82°C thermal slowdown был `Not Active`, но существующая более ранняя локальная защитная граница всё равно соблюдена. Это не универсальный предел RTX3070. Последующая отдельная проверка: GPU57°C, VRAM871MiB, Ollama models пустой; часть VRAM используется Dashboard/Chrome/рабочим столом. CUDA crash в этой серии не наблюдался.

Сохранены admissionRAM6656MiB, runtimeRAM4096MiB, commit headroom4096MiB, свободнаяVRAM4096MiB до запуска/512MiB во время, температурная граница82°C и thermal/telemetry checks. Профиль4096context, batch32, num_gpu=-1, think=false, keep_alive5m между этапами, один последовательный запрос; адресная выгрузка вfinally. Глобальный параллелизм Ollama не менялся. Отсутствие других соединений проверяется в допуске, но не даёт математической гарантии, что внешний клиент никогда не подключится позднее. Несколько моделей одновременно не запускались.

### Исторические провалы в этой работе сохранены

Ранние traces в `reports/qwen4b_manual_qa/limited_chat_1794469*.json` и `1794470*.json` не объявляются успешными задним числом. В них подтверждены: ID в прозе, выдуманная невыгодность, перепутанные м³ и м³/л, выдуманный выход, исключение плотности при исходных килограммах, выпадение второго материала из контекста, неподтверждённый оптимум, неверный evidence ID. Исправлены общие маршруты, не подготовлены ответы на каждую фразу. Поздний опыт с запретом цифр регулярным выражением внутри JSON-schema вызвал повторение до лимита540токенов (`1794471403128704500`); эта схема удалена. Осталась простая двухполевая схема и отдельная строгая проверка контракта. Промежуточный англоязычный вывод (`1794471615682983400`) не засчитан русскоязычным PASS; финальный контекст локализован. Все эти raw responses остаются доступны.

### Проверки, команды и окружение

Windows11 build26200, RAM15.8GiB по API; Python3.13.13; FastAPI0.141.1; Pydantic2.13.5; httpx0.28.1; pytest8.4.2; psutil7.2.2; Ollama0.40.16; NVIDIA581.80; RTX3070Laptop8192MiB. Frontend Vite7.3.7/Vitest3.2.7. Ветка и исходный HEAD не изменены, новые release/tag не создавались. Имеющиеся пользовательские изменения не откатывались; полный git diff включает работу предыдущих этапов и не является перечнем только этого задания.

Все команды ниже выполняются из `BioReactor_AI`, кроме явно указанного frontend:

```powershell
python -X utf8 -m pytest tests/test_farmer_consultation.py tests/test_literature_methane_estimates.py tests/test_substrate_advisor.py tests/test_stage9_runtime.py tests/test_stage9_verification.py tests/test_stage9_jobs.py tests/test_acceptance_root_cause_remediation.py tests/test_scientific_question_routing.py tests/test_scientific_provenance.py tests/test_scientific_assertion_scope.py tests/test_reactor_capacity_validation.py tests/test_reactor_capacity_dashboard.py tests/test_qwen4b_grounded_synthesis.py tests/test_qwen4b_scientific_integration.py tests/test_qwen4b_resource_policy.py tests/test_qwen4b_manual_chat.py tests/test_provider_cancellation.py tests/test_complete_economics.py -q -p no:cacheprovider --basetemp=.pytest-farmer-final-frozen-20261112
```

**PASSED420,0failed,0skipped,51.74с**, одна существующая Starlette deprecation warning о httpx. Это релевантный агрегат, не полный acceptance/holdout. Ранее419-тестовый запуск имел1старое строковое ожидание вместо содержательной проверки отсутствия30-дневного прогноза; тест обновлён с проверкой `target_days=30` и отсутствующих time_yield для всех сценариев. Следующий420-тестовый запуск имел ошибку нового test fixture (`recorded_at`); исправлена фикстура, финальный агрегат выше полностью пройден. Исключённые тесты не засчитывались.

```powershell
Set-Location frontend
npm.cmd test -- --configLoader runner
npm.cmd run build -- --configLoader runner
node tests/farmer-history-browser.mjs
```

Frontend **81PASSED**, build/typecheck **PASSED**, Chrome history test **28PASSED**. Первый typecheck выявил некорректный тип `duration_days` вUI; добавлена явная числовая проверка. Новый UI-test первоначально был без DisplayModeProvider и попадал в legacy-режим; исправлена тестовая среда. Один обычный Vite config-loader запуск упал на ограничении чтения родительского каталога окружения; штатный `--configLoader runner` собрал проект без изменения зависимостей/настроек Windows. Не скрывается за успешной командой.

Browser проверяет **восстановление настоящего завершённого pig-ответа** изQASQLite, добавленного в отдельную demoDB без удаления других сессий. Исходные trace/SQLite неизменны. Никаких route mocks или новых LLM-запросов в браузерной проверке. Проверены секции, цифры/единицы, источник Chae, ровно один вопрос, отсутствие внутренних ID в нормальной прозе, предупреждение рабочего объёма, reload, mobile иJS errors. Это28 интерфейсных утверждений вокруг одного реального сохранённого ответа, не28 научных сценариев и **не новый browser live-inference E2E**. Артефакты: `farmer_consultant_20261112/browser_history.json`, `chat_history_desktop.png`, `chat_history_mobile.png`. Браузерную генерацию текущего универсального Chat после остановкиGPU не запускали.

Реальная последняя серия запускалась существующим клиентом:

```powershell
foreach ($farmCase in @('pig','cow','food','straw','compare','no_numbers','dialogue')) {
  python -X utf8 evaluations/qwen4b_manual_chat.py --confirm-experimental --limited-chat --farmer-case $farmCase
  if ($LASTEXITCODE -ne 0) { break }
}
```

Это фактические `/api/dashboard/chat/sessions`, `/sessions/{id}/jobs`, `/api/dashboard/jobs/{id}/result` через FastAPI TestClient, а внутри — реальные HTTP-запросы на основной Ollama11434. Инъекция фабрики provider выбирает настоящий `LimitedProvider`; она не возвращает заранее подготовленные ответы модели. Common Chat business logic и научные инструменты реальные. После достижения температурного предела цикл остановлен. Повторять весь цикл сейчас не предлагается.

Произвольный вопрос поддерживается тем же клиентом, без добавления ещё одного сценария в код:

```powershell
# Сначала сохраните вопрос UTF-8 в редакторе. Только после нового допуска и охлаждения:
python -X utf8 evaluations/qwen4b_manual_chat.py --confirm-experimental --limited-chat --message-file reports/farmer_custom_question_20261112.txt
# При необходимости второй ход в отдельном UTF-8 файле: --followup-file PATH
```

Файл с новым примером52л/180л подготовлен. Его ранний real trace отклонён за повторение/неподтверждённые величины; после окончательного изменения контракта новый live не выполнен из-за остановки серии. Не засчитывается в последние шесть PASS транспорта. RU/KK/математические символы проходят детерминированную побайтную UTF-8 проверку, повреждённый ввод INVALID_INPUT не отправляется.

Запуск существующего экспериментального Dashboard, когда8770 свободен:

```powershell
python -X utf8 main.py dashboard --firo-demo --port 8770
```

Экспериментальная база `data/runtime/firo_demo.sqlite3`, scheduler выключен. На момент проверки запущен нами PID27148 с теми же флагами и `--no-browser`; адрес `http://127.0.0.1:8770/dashboard/#/chat`. Старый наш PID23424 уже отсутствовал, его не завершали. Production8766 не перезапускался и его модель не переключалась. Общий UI использует прежнюю систему выбора provider: **безопасный экспериментальный4B гарантирован в указанном QA-вызове; прямую browser-генерацию нельзя считать автоматически привязанной к QA gate**. Эта интеграционная граница остаётся открытой задачей, а не поводом обходить защиту.

### Изменённые компоненты этого задания

Новые: `src/agent/farmer_consultation.py`, `data/research/farmer_profiles.json`, `tests/test_farmer_consultation.py`, `frontend/tests/farmer-history-browser.mjs`, `evaluations/export_farmer_training_candidates.py`, `datasets/farmer_consultant/README.md`/`candidates.jsonl`, этот отчёт и артефакты.

Доработаны существующие: `src/agent/analytical.py`, `runtime9.py`, `nlu.py`, `dialogue_types.py`, `context.py`, `dialogue_memory.py`, `quantities9.py`, `verification9.py`, `autonomous.py`; `src/advisor/schemas.py`, `mixing.py`, `catalog.py`, `evidence_engine.py`, `estimation.py`, `api.py`; `src/research/dossiers.py`; `evaluations/qwen4b_manual_chat.py`; `frontend/src/ConversationFacts.tsx`, `ConversationReply.tsx`, `frontend/tests/conversation.test.tsx`; `tests/test_substrate_advisor.py`, `test_qwen4b_scientific_integration.py`; readiness/integration/persistent audit reports. Собран frontend/dist. Изолированная demoDB пополнена одной подлинной QA-сессией для проверки восстановления. ProductionDB, веса моделей и системные настройки не изменялись.

### Датасет и следующие действия

Экспортированы6 trace-backed **кандидатов на ручную проверку**,0готовых к обучению. Единственный исходный pig-вопрос помечен пользовательским acceptance; остальные — авторские development-вопросы, не реальные обращения фермеров. В каждом сохранены raw model synthesis, delivered answer, tools, автоматические проверки, SHA256 trace и `eligible_for_training=false`. Формулировки, о которых выше есть замечания, не одобрены как LoRA targets. Обучение не запускалось; независимый blind holdout не использован.

Приоритет дальнейшей работы:

1. Смысловая согласованность качественного Qwen-текста с наличием рассчитанного ориентира: не путать «неизвестна фактическая выработка» и «не определён даже литературный потенциал». Отклонять утверждение о неоптимальности без исследования оптимума. Проверять и недоставленные explanation-поля, не признавать их проверенными по одному автоматическому статусу.
2. Улучшить релевантность пояснения/единственного вопроса без назначения отсутствующих параметров: для чистого вопроса о температуре не начинать с отсутствия метанового числа.
3. После достаточного охлаждения и нового штатного допуска завершить только прерванный двухходовый запрос и независимый arbitrary-file вопрос. Не повторять всю уже выполненную серию ради новых зелёных статусов.
4. Подтвердить библиографию/газовую базу концентрационных профилей по полному источнику либо оставить энергетическую оценку неизвестной. Проверить применимые реальные тарифы/класс потребителя и документированные расходы, не выдумыватьKZT.
5. Подключить безопасный ограниченный4B provider к интерактивному экспериментальному Dashboard через существующий контроллер с теми же лимитами; затем новый browser live E2E. Не менять основной production profile автоматически.
6. Независимая внешняя оценка/неиспользованный holdout и более широкие проверки проекта. Только после них обсуждать FIRO READY.

## Продолжение: настоящий интерактивный Chat — 2026-11-12

### Разрыв между QA и Dashboard устранён

`--firo-demo` теперь явно включает защищённый4B provider и в **обычном AI Chat** этого экспериментального приложения. Production без флага сохранил прежнюю фабрику/настройки. Новый сервер, клиент или расчётная система не созданы. Повторно используется `LimitedProvider` из существующего QA-клиента; ресурсный scope находится в существующем `src/dashboard/firo_demo.py`.

Перед каждой job проверяются6656MiB RAM, commit, VRAM, температура, thermal slowdown, API и отсутствие чужих клиентов/загруженных моделей. Во время запроса работает монитор; отмена идёт от JobRuntime к HTTP provider. На один запрос максимум4модельных вызова,1358запрошенных выходных токенов,120с. `keep_alive=5m` между этапами. Адресная выгрузка и итоговая телеметрия выполняются **до сохранения ответа**. Неуспешное завершение монитора отменяет job; поздний результат не сохраняется. Синхронный экспериментальный LLM-route отклоняется409 до создания turn, чтобы нельзя было обойти отмену или оставить ложный running turn. Production synchronous route сохранён с его прежними ограничениями.

Если допуск не пройден, не происходит переключения на8B или внешний provider. Общий Runtime9 выполняет научные Python-инструменты без LLM и явно сообщает недоступность4B. Регрессия обнаружила ранний обход Runtime9 старым no-LLM путём; для экспериментального приложения он устранён. Реальное поведение без модели также подтверждено ниже, не только mock-тестом.

Изменения этого продолжения: `src/dashboard/firo_demo.py`, `src/dashboard/api.py`, `src/market/api.py`, `src/agent/conversation.py`, `src/agent/providers.py`, `src/agent/nlu.py`, `src/agent/verification9.py`, `src/agent/farmer_consultation.py`, `src/agent/runtime9.py`; `frontend/src/pages/ChatV9.tsx`, `frontend/src/types.ts`; `tests/test_firo_chat_guard.py`, дополнения к `test_farmer_consultation.py`, `test_qwen4b_grounded_synthesis.py`; существующий браузерный тест и эти отчёты. UI получает фактический экспериментальный профиль из statusAPI вместо строки `qwen3:8b` в коде.

### Подтверждённые дополнительные причины и исправления

1. Смысловое противоречие «потенциал не определён» при уже рассчитанном литературном потенциале теперь отклоняется. Неизвестный фактический выход и неизвестный точный потенциал конкретной партии разрешены как отдельные утверждения. Отклоняется также безосновательное «метан не выработан установкой» — это неизвестное фактическое состояние. Никаких новых датчиков/измерений не выдумывается.
2. Русское «оптимум» отсутствовало в прежнем лексическом покрытии. Теперь необоснованное «не оптимум» отклоняется вместе с положительным объявлением оптимума; корректные «оптимум не установлен» и «не проверенный оптимум» проходят. Старые неоднозначные черновики не объявлены хорошими задним числом.
3. В первом настоящем браузерном вопросе «оцени метан, разумную температуру и экономический смысл» пропущена температура: компактный NLU вообще не возвращал задачи, а буквальная грамматика распознала только две части. В существующую компактную схему добавлен ограниченный `requested_tasks` с тремя разрешёнными категориями. ЛимитNLU остался128токенов. Модельный смысл задач дополняет частично распознанный список при наличии тематической опоры; не создаёт чисел, материала или оборудования. Чистый концептуальный вопрос защищён от превращения в оценку партии. Результат реального нового NLU: `['methane','temperature','economics']`. Это общий механизм, не правило для слова «разумная» и не ответ на конкретную фразу.
4. Для чистого вопроса о температуре единственный приоритетный вопрос теперь касается температур сырья/помещения, а не количества сырья. Уже отклонённые научные утверждения не исправляются бесконечным циклом; проверенные Python-результаты остаются доступны.

### Настоящий браузерный запрос — PASS в ограниченном объёме

Вопрос из произвольного UTF-8 файла: «На ферме накопилось52литра жидкого свиного навоза. Есть реактор на180л, газ хочу использовать для обогрева. Оцени возможный метан, разумную температуру и экономический смысл без выдуманных тарифов».

Пройден **настоящий Chrome → FastAPI на8770 → Runtime9 → Ollama11434**, не TestClient и не fake-provider. NLU валидный, материал привязан к слову пользователя, все три задачи распознаны. Фактические инструменты:

| Инструмент | Кто выбрал |
|---|---|
|estimate_methane_yield|Qwen|
|search_scientific_sources|Qwen|
|assess_process_evidence|обязательная проверка контроллера с резервом синтеза|
|evaluate_partial_economics|обязательная проверка контроллера с резервом синтеза|

Всего4настоящих вызова Qwen: компактное понимание, два этапа выбора инструментов, синтез. Статус автора `qwen_verified`; no fallback. Обе части модельного синтеза после проверки доставлены вместе с Python-блоками:

> Оценка метана условная, температура изучена, экономика не определена. Метановый потенциал не измерен, температура мезофильная, затраты неизвестны.

Полный, неизменённый доставленный ответ и сырые ответы всех модельных этапов: [browser_actual_answers.md](farmer_consultant_20261112/browser_actual_answers.md), запись `browser_full_pass`. Исходный JSON: [browser_live_initial_pass.json](farmer_consultant_20261112/browser_live_initial_pass.json); снимок [browser_live_initial.png](farmer_consultant_20261112/browser_live_initial.png).

Python вернул277.34/329.92/341.79лCH₄ для52л по отдельным литературным опытам25/30/35°C, без плотности и без выдуманной влажной массы. Рекомендация около35°C явно названа отправной точкой, не уставкой. Неизвестные газовая база/теплопотери/цены/полные расходы не превратились в выручку или прибыль. Номинальные180л не объявлены рабочими. Источники доступны по ссылкам; один вопрос о регионе. Реальная экономическая трасса теперь содержит `region_confirmed=false` для условного региона, что подтверждает и позднее исправление provenance.

Отдельный просмотр содержания: **PASS для этой условной консультации**, с ограничениями полноты экономики и отсутствием натурной валидации. Текст модели остаётся кратким и общим; это не доказательство надёжности произвольного научного рассуждения. Литературная применимость должна проверяться до инженерного решения.

| Компонент | Результат |
|---|---|
|Реальный NLU и grounded material|PASS|
|Все три задачи и фактические инструменты|PASS|
|Независимая арифметическая проверка|PASS|
|Числа в модельном черновике|NOT_APPLICABLE: числовые блоки поступили из Python, не из Qwen|
|Scientific verifier|PASS,checked=true|
|Просмотр научного содержания отдельно от verifier|PASS с явно указанными ограничениями|
|Доставка нового ответа без fallback|PASS|
|Восстановление нового ответа после reload|PASS|
|Контролируемая выгрузка|PASS|
|Полная экономика, прибыль, срок окупаемости|NOT_ESTABLISHED|
|Blind external holdout/общая готовность FIRO|NOT_RUN / NOT_READY|

### Телеметрия и блокировки не скрыты

До первого браузерного запуска выполнены три свежих замера через10с: RAM7644.0/7642.0/7613.3MiB, commit headroom23574.2–23598.1MiB, GPU57°C, VRAM541MiB, thermal slowdownNotActive, моделей/других клиентов нет. Между более поздними попытками действовал ещё и свежий допуск внутри каждого реального backend-запроса.

Успешный окончательный запрос: admissionRAM7035.6MiB; минимум5877.4MiB; максимум наблюдавшегося commit17328.5MiB, VRAM3856MiB, GPU72°C; весь ресурсный scope13.319с, включая выгрузку. Остановка/выгрузка0.195с; после неё RAM7208.9MiB, VRAM578MiB, `models=[]`. `/api/ps` во время запроса показал context4096, size3224109055 и size_vram3224109055 — полный offload по данным сервера для этого запуска. Это не гарантия будущих пиков. CUDA errors/thermal slowdown в этом запросе не наблюдались.

Сохранены и неудачные попытки:

- Первый browser request реально сгенерировал ответ, но имел только три инструмента из-за пропущенной температуры. Кроме того, тест при reload сам принудительно записывал старый sessionID. Исправлен тестовый init: существующая сессия не перезаписывается. Восстановление первого нового ответа отдельно прошло26проверок без повторной генерации. Исходный ответ сохранён в `browser_live_result_first.json`; первоначальный stack trace assertion имеется в журнале выполнения, исходный JSON browser-check был позднее перезаписан — его не воссоздавали.
- Следующая попытка, перед которой открывался старый большой диалог, заблокирована при6593.2MiB: недоставало62.8MiB до6656. Никаких LLM-вызовов. `browser_live_result_ram_blocked.json` и `browser_history_ram_blocked.json` сохранены. Удалён лишний предварительный replay старой истории из **live-теста**, не ослаблен gate. Чистая сессия после этого прошла с7035.6MiB.
- Продолжение успешного диалога «А если температура будет25°C?» заблокировано до модели при6650.4MiB, дефицит5.6MiB. Повторных попыток загрузки не было. Реальный Python-путь сохранил52л/180л, принял25°C как `ASSUMED_FOR_SCENARIO`, выбрал совместимый25°C источник и пересчитал277.34л литературного потенциала. Ответ доставлен и восстановлен; модельная часть **BLOCKED**, не PASS. Полный результат: `browser_followup_ram_blocked.json`. Отдельно28проверок browser-restore этого реального немодельного ответа PASSED в `browser_blocked_followup.json`. Вначале тесту понадобились две корректировки для многоходовой истории: область поиска badge ограничена последним ответом; требование «ровно один вопрос» заменено соответствием сохранённому ответу с максимум одним вопросом, так как повтор прежнего вопроса справедливо подавлен.

`browser_history.json` относится к последней попытке **LLM-продолжения**, где строгий live-check ожидаемо не прошёл из-за gate. Успешные13browser-checks нового полного модельного ответа сохранены отдельно в `browser_initial_pass_checks.json`. Эти статусы не объединяются. Текущее `/api/ps` пусто, backend14804 работает, runtime не имеет активных jobs. Старый наш8932 перед обновлением остановлен только после проверки команды/PID и отсутствия активных запросов; пользовательские процессы и production8766 не останавливались.

Минимальное действие для следующего модельного хода: сохранить свободную RAM **выше6656MiB уже при открытом Dashboard**, а не до открытия браузера; практический запас нужен больше последнего дефицита5.6MiB. Закрывать приложения должен пользователь. Никакой границы не снижали, очередной бесконечный preflight не запущен. Даже при блокировке научные Python-результаты доступны.

### Последняя детерминированная проверка и воспроизведение

**484PASSED**,0failed/0skipped,67.30с, одна прежняя Starlette/httpx deprecation warning. Это предыдущий агрегат плюс проверки контроллера/общего ConversationAgent; числа420/482/484 не складываются. Точная последняя команда:

```powershell
python -X utf8 -m pytest tests/test_farmer_consultation.py tests/test_literature_methane_estimates.py tests/test_substrate_advisor.py tests/test_stage9_runtime.py tests/test_stage9_verification.py tests/test_stage9_jobs.py tests/test_acceptance_root_cause_remediation.py tests/test_scientific_question_routing.py tests/test_scientific_provenance.py tests/test_scientific_assertion_scope.py tests/test_reactor_capacity_validation.py tests/test_reactor_capacity_dashboard.py tests/test_qwen4b_grounded_synthesis.py tests/test_qwen4b_scientific_integration.py tests/test_qwen4b_resource_policy.py tests/test_qwen4b_manual_chat.py tests/test_provider_cancellation.py tests/test_complete_economics.py tests/test_firo_chat_guard.py tests/test_firo_demo_mvp.py tests/test_conversation.py -q -p no:cacheprovider --basetemp=.pytest-farmer-completed-20261112
```

В промежуточном484-тестовом запуске два старых ожидания схемыNLU из двух полей упали. Они обновлены под компактный список задач без ослабления проверок выдуманного материала, отсечения JSON и двухвызовного концептуального маршрута. Отдельная новая фикстура проверки смысла первоначально не указывала существующий methane-reference; исправлена фикстура, защита полноты результата сохранена. Frontend81PASSED, build/typecheck PASSED, кодUI после этой сборки не менялся. Поздние изменения браузерного теста проверены его фактическими запусками, не LLM-моками.

Точные команды последних проверок интерфейса из `frontend`:

```powershell
# Первый полный реальный запрос из чистой сессии; повторять только после допуска:
node tests/farmer-history-browser.mjs --live-only --live-message-file=../reports/farmer_custom_question_20261112.txt
# Продолжение сохранённой сессии: последняя попытка модели BLOCKED поRAM
node tests/farmer-history-browser.mjs --restore-live --followup-message-file=../reports/farmer_followup_temperature_20261112.txt
# Восстановление фактически доставленного немодельного продолжения, без inference:
node tests/farmer-history-browser.mjs --restore-no-model
```

Запуск для пользователя одной командой из корня проекта не изменился:

```powershell
python -X utf8 main.py dashboard --firo-demo --port 8770
```

Затем `http://127.0.0.1:8770/dashboard/#/chat`, режим «Локальная модель» — защищённая4B; «Расчёт без языковой модели» — тот же экспериментальный Runtime9 с научными инструментами, без загрузкиLLM. При уже работающем8770 второй экземпляр запускать не нужно. Без `--firo-demo` настройки основного приложения сохранены. Статус **экспериментального одноходового консультанта: функционально подтверждён**, общей готовностиFIRO — **NOT_READY**. Следующие задачи: закончить модельное продолжение при достаточной RAM, оценить новую семантику на неиспользованных формулировках, проверить коммерческую экономику и тепловые исходные данные, выполнить независимый holdout. Больше реальных запусков в этом продолжении не требуется.
