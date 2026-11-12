# Third-turn continuation — 2026-11-12

**Latest result: third real-model turn completed after the user freed RAM.** Same saved session, no first/second replay; browser delivery/reload and model unload passed. Full third answer/metrics/quality review are in the final section below. Historical blocked setup is retained, not counted as inference. Overall FIRO readiness remains unconfirmed.

## Origin and separation of cooling rules

The initial+2°C rule originated in the **browser regression**, `frontend/tests/web-only-dialogue.mjs`, top-level `for` loop, inside the per-turn preflight block (`cooled` and subsequent BLOCKED condition). It was introduced for the previous serial retest to return the GPU close to its initial thermal state and improve comparability/avoid accumulating heat. It was not taken from NVIDIA specifications, Windows/Ollama requirements or the4B production/QA resource policy. It acted only on whether the browser test submitted the next message. No corresponding baseline-relative rule exists in `evaluations/qwen4b_manual_chat.py:calibration_issues` or `src/dashboard/firo_demo.py:guarded_chat`.

The previously observed62°C was simply60°C at the start plus2°C. It is not a hardware limit.64°C alone was not a safety violation; the main policy was green in that earlier stop.

The reproducibility criterion is now optional: **`--reproducible-cooldown`** enables the former bounded60s/10s sampling and baseline+2°C rule. For resume mode it retains the original saved baseline. Default continuation uses the unchanged mandatory policy; it does not bypass its failures.

Unchanged mandatory checks: RAM admission6656MiB, runtime RAM reserve4096MiB, commit headroom, freeVRAM, local temperature guard82°C, active HW/SW thermal slowdown, telemetry/API availability, foreign clients/models, per-job timeout/call budget, cancellation propagation, ownership/late-result fencing and targeted model unload.82°C is the existing conservative local policy for this machine, not a newly claimed universal NVIDIA maximum.

## Minimal test changes

Only the existing browser test and question/artifact files changed. `--resume=FILE` restores the saved real session, verifies exactly2persisted turns and state_version2, seeds that session in localStorage and begins at index2. It refuses unexpected history rather than replaying or resetting it. `--message-file=FILE` loads the requested UTF-8 third question with round-trip validation. No new server/client architecture, model/configuration/training or business-logic rewrite.

Saved session: `26b04104b85d4d12bf5796b830692167`; source `reports/three_turn_qwen_freed_ram_20261112/browser.json`. Verified via actual FastAPI session endpoint:2turns, state_version2. Previous real turn IDs remain2bf5ff19db284f98b95473cf2e561bd7 and6e3280680cb5478abc8ded72848e335b.

Prepared actual third question: `reports/third_turn_request_20261112.txt` (exact user wording).

## Actual attempt and blocker

Command from frontend:

```powershell
$env:BIOREACTOR_DIALOGUE_OUT='../reports/third_turn_completed_20261112'
node tests/web-only-dialogue.mjs --resume=../reports/three_turn_qwen_freed_ram_20261112/browser.json --message-file=../reports/third_turn_request_20261112.txt
Remove-Item Env:BIOREACTOR_DIALOGUE_OUT
```

The new mandatory preflight with Chrome open returned:

- FreeRAM5634.1MiB against6656; deficit1021.9MiB.
- Commit headroom19887.1MiB; GPU46°C, utilization4%, VRAM982/8192MiB.
- Thermal slowdownNotActive; Ollama models empty.
- Only issue: `ram_limit`. Optional cooldown disabled, correctly not responsible.

No third message was submitted, no Qwen generation or tool calls for that turn occurred, and no synthetic third response is supplied. Original blocked attempt retained in `third_turn_completed_20261112/blocked_admission_5634_1.json`. The output's two completed prior turns are explicitly marked `reused_prior_turns=2`; they are not new generation or a three-turn PASS. Source trace was not modified.

User was informed and replied that they will free memory and continuation should wait for their next message. No apps were closed automatically. Last API confirmation: same2turn session; `/api/ps` models empty. No unloading command needed because no model was loaded during this attempt.

## Checks and next exact step

`node --check frontend/tests/web-only-dialogue.mjs` PASSED. `python -X utf8 -m pytest tests/test_firo_chat_guard.py tests/test_qwen4b_resource_policy.py -q -p no:cacheprovider --basetemp=.pytest-third-turn-policy-20261112` —21PASSED,0failed/skipped,9.64s, one existing Starlette/httpx warning. These are policy/cancellation regressions, not live scientific acceptance.

After the user's freed-memory message, invoke the exact resume command above under a fresh mandatory admission. Do not replay the first two turns. Preserve blocked snapshot. Capture third raw model synthesis, actual tools, full delivered answer, independent scientific review and unload telemetry; do not count fallback or reused turns as new model success.

## Завершённый третий ход после освобождения памяти

**Техническая трёхходовая проверка: PASS в рамках этой сохранённой сессии.** Первые два хода выполнены ранее с реальной Qwen; сейчас выполнен только третий, без пересоздания памяти и повторения первых двух. Это не три новых одновременных запроса и не общий acceptance проекта.

Выполненная команда из frontend:

```powershell
$env:BIOREACTOR_DIALOGUE_OUT='../reports/third_turn_after_memory_freed_20261112'
node tests/web-only-dialogue.mjs --resume=../reports/three_turn_qwen_freed_ram_20261112/browser.json --message-file=../reports/third_turn_request_20261112.txt
Remove-Item Env:BIOREACTOR_DIALOGUE_OUT
```

Итог браузерного теста: `interface=PASSED`, model statuses completed/completed/completed. Первые два результата взяты из сохранённой исходной трассы, третий — новая настоящая генерация. Сессия `26b04104b85d4d12bf5796b830692167`, новаяjob `e831b97ca123446da30dfc4d5383388e`. Повторный GET сессии подтвердил3turns, state_version3 и точное совпадение сохранённого ответа с полученным результатом. Три ответа отображаются после reload; screenshot `third_turn_after_memory_freed_20261112/turn_3.png` просмотрен отдельно. Новых пользовательских интерфейсов/окон не создавалось.

### Полный ответ и реальные вызовы

**[Полный третий ответ дословно, с источниками](third_turn_after_memory_freed_20261112/third_answer_verbatim.md)**. [Полная браузерная трасса](third_turn_after_memory_freed_20261112/browser.json), [фактические LLM-вызовы и исходные ответы](third_turn_after_memory_freed_20261112/third_llm_calls.json), [полные tool calls/results](third_turn_after_memory_freed_20261112/third_tool_calls.json), [сводка/хеш](third_turn_after_memory_freed_20261112/summary.json).

Qwen3 4B реально участвовала в4обращениях: compact NLU43выходных токена, tool selection100, tool selection72, scientific synthesis66; каждый `status=ok`, `done_reason=stop`, генерация получена. Итоговый автор `qwen_verified`; fallback не доставлялся. Две свободные текстовые части сформировала модель, расчётные строки/ссылки и ограничения публиковались проверяемым Python-путём. Служебные поля канонического синтеза не следует приписывать модели.

| Фактический инструмент | Происхождение выбора |
|---|---|
|search_scientific_sources|Qwen,validated_scientific_state|
|estimate_methane_yield|Qwen,validated_scientific_state|
|assess_process_evidence|controller_required_evidence|
|evaluate_partial_economics|controller_required_evidence|

Память:78L сырья, номинальные200L, `facts.temperature_c` отсутствует, `assumptions.temperature_c=25` с `ASSUMED_FOR_SCENARIO`; список сравнения[25,35]. Условные25°C не превращены в фактическое измерение.35°C отдельно обозначены как изученный литературный вариант для обсуждения, не подтверждённая уставка.

### Числа, verifier и ресурсы

Показаны416LCH₄ при25°C и512.69LCH₄ при35°C как условные исходные литературные потенциалы всей партии. Отдельно указаны4.1475/5.1115kWh условной энергии на предположительно совместимой сухой газовой базе FNR. Начальный нагрев, теплопотери, расход мешалки и чистая прибыль **не выдуманы**: без тепловых данных и применимых цен остаются неизвестными.

Арифметический verifier `ok`; scientific verifier `passed`, `checked=true`, all_checks_passed=true. Проверка чисел именно модельного качественного черновика `not_applicable/checked=false`: в нём нет числовых утверждений; это не отсутствие проверки Python-арифметики. Scientific verifier покрывает ограниченный перечень противоречий/источников/применимости, не является полной биологической валидацией; его completeness component здесь `not_applicable`, не отдельный PASS полноты.

| Фактический показатель третьего хода | Значение |
|---|---:|
|RAM при внутреннем admission|6929.7MiB|
|Минимум наблюдавшейся свободнойRAM|5564.2MiB|
|Максимум наблюдавшегося commit|18417.6MiB|
|Максимум наблюдавшейсяVRAM|4156MiB|
|МаксимумGPU|59°C|
|Время ресурсногоscope с очисткой|9.361с|
|Адресная выгрузка|0.219с|
|RAM после выгрузки|6893MiB|
|VRAM после выгрузки|880MiB|
|Модели после выгрузки и при финальной проверке|[]|

Admission6656MiB соблюдён перед запуском; runtime floor4096MiB соблюдён во время работы. Не следует ошибочно применять admission-порог повторно к каждой runtime-выборке. Остальные проверки, температурный guard, отмена, unload и бюджет не ослаблялись. Эти максимумы — наблюдавшиеся samples, не доказанные непрерывные аппаратные пики. Отдельный durable guard-аудит существует: `reports/guarded_chat_audit/f2b4e29e8f7d4fe6b6c5acbd6afd111e.json`. Ошибок модели/ресурсной остановки в этом ходе нет.

### Независимая оценка полезности

Отдельное чтение доставленного текста, не автоматический статус verifier:

- **Научная интерпретация: корректная условная оценка.** Публикационные конечные выходы не названы измерением, гарантией либо прогнозом за30дней. Плотность не выдумана: опубликованная концентрацияVS используется на литр сырья. Газовая база для энергии — явно дополнительное допущение; численную энергию нельзя считать подтверждённой полезной теплотой конкретного оборудования.
- **Контекст: PASS.** Сохранены партия, сосуд, условные25°C и оба сравниваемых варианта. Номинальная вместимость не приравнена к рабочей; автоматического нагрева и гарантии одной загрузки нет.
- **Рекомендация: полезна, но условна.** Более тёплый режим обсуждается только при доступном тепле, адаптированном инокуляте и устойчивом процессе. При ограниченном нагреве прохладный режим рассматривается отдельно с необходимостью подтвердить кинетику/производительность. Это обоснованнее категоричного «35°C выгоднее», которого текст не делает.
- **Экономическая полнота: PARTIAL.** Нет применимого тарифа, реальных тепловых параметров и всех затрат. Отсутствие численной прибыли/окупаемости честное и корректное, но окончательно выбрать режим по деньгам фермер пока не может. Нужны реальные условия установки, а не ещё одна выдуманная универсальная константа.
- **Естественное объяснение Qwen: PARTIAL.** Её качественные предложения почти совпадают с предыдущими ходами и остаются общими. Основное новое содержание сравнения даёт Python-блок. В ответе ещё много повторяющихся оговорок. Поэтому технический PASS не равен доказанной полноценной самостоятельной консультации на произвольные вопросы.

В этом продолжении код приложения/модели не менялся, тесты не пересчитывались задним числом. Основная цель ограниченного прогона выполнена: третий настоящий Qwen-ответ получен в той же памяти и доставлен без fallback. **Общая готовность FIRO: NOT READY** до независимого holdout/более широкой научной и интерфейсной проверки. Старая точная причина CANCELLED из утраченых данных не восстановлена и успешным новым запуском не объявлена доказанной.
