# v9: выполнение научных задач

Разработка продолжается. [Отчёт и открытые критерии приёмки](../reports/stage9_autonomous_scientific_intelligence.md).
Сохранённые BMP-модели не переобучались. История и прежние API остаются доступны.

## Запуск Windows

```powershell
$env:OLLAMA_MODEL='qwen3:8b'
$env:BIOREACTOR_LLM_CONTEXT='8192'
$env:BIOREACTOR_LLM_GPU_LAYERS='16'
$env:BIOREACTOR_AGENT_TIMEOUT='150'
$env:BIOREACTOR_JOB_TIMEOUT='180'
python main.py dashboard --port 8765 --no-browser
```

Интерфейс: http://127.0.0.1:8765/dashboard/#/chat . Требуется локальная Ollama с
установленной Qwen3 8B. Число GPU-слоёв — измеренный компромисс для данного
ноутбука, не универсальная настройка производительности.
При необходимости добавьте установленные зависимости из `.runtime-deps` в
`PYTHONPATH`, как описано в `requirements-local-runtime.txt`.

Для изменения frontend:

```powershell
cd frontend
npm.cmd ci
npm.cmd run typecheck
npm.cmd test
npm.cmd run build
```

FastAPI раздаёт `frontend/dist` по `/dashboard/`. После изменения Python
перезапустите backend; один build frontend не загружает новую версию API.

## API и восстановление

1. `POST /api/dashboard/chat/sessions` с `conversation_version: "7"`.
2. `POST /api/dashboard/chat/sessions/{id}/jobs` с `message`, уникальным
   `request_id` и необязательным `expected_state_version` возвращает HTTP 202.
3. `GET /api/dashboard/jobs/{id}` возвращает сохранённый статус, heartbeat,
   попытки и ссылку `result_reference`.
4. `GET /api/dashboard/jobs/{id}/result` возвращает ответ, доступные частичные
   результаты и ошибку. `terminal: false` означает, что работа ещё продолжается.
5. `POST /api/dashboard/jobs/{id}/ack` подтверждает получение терминального
   результата. Подтверждение не удаляет ответ.

Повтор с теми же `request_id` и сообщением получает прежнюю задачу; другое
сообщение с таким идентификатором отклоняется с 409. Конфликт версии также 409.
`POST /api/dashboard/jobs/{id}/cancel` отменяет запрос. Текущий вызов провайдера
может завершаться до собственного сетевого deadline, но после отмены его ответ
не меняет научное состояние. Новые вычисления worker начинает после возврата
предыдущего вызова, сохраняя lease в этот период.

Статусы: SUBMITTED (событие), QUEUED, RUNNING, TOOL_EXECUTION, FINALIZING,
COMPLETED / FAILED / CANCELLED / TIMED_OUT. COMPLETED означает завершение
исполнения; качество ответа определяется `technical_metadata.final_author`,
`verification`, `primary_evidence_unchecked`, `diagnostics`. Частичный ответ
движка не считается успешным самостоятельным синтезом Qwen.

Frontend автоматически опрашивает активную задачу, восстанавливает её после
перезагрузки и повторяет доставку сохранённого запроса с тем же UUID. При потере
связи используется повтор с задержкой до десяти секунд. Старый процесс не
может завершить работу, уже переданную новому владельцу.
Heartbeat устаревает через 45 секунд, после чего запрос повторяется не более
двух попыток. Результат, уже записанный в сообщении, повторно не вычисляется.
Прерванные старые синхронные запросы без восстановимого execution-state
получают явную ошибку после пяти минут; их входные данные не воспроизводятся
поверх более нового контекста.

Диагностика: `/api/dashboard/runtime` и `/api/dashboard/jobs/{id}/events`.
Прежний синхронный `/messages` сохраняется для совместимости и не предоставляет
все гарантии нового протокола jobs.

## Состояние и черновики

`GET /api/dashboard/chat/sessions/{id}/scientific-state` возвращает активную
задачу, версию, подтверждённые пользователем данные, литературные сведения,
допущения, производные величины, прогнозы и отдельный черновик.
Снимки научных задач неизменяемы и не заменяют историю диалога или библиотеку
сохранённых смесей.

`PUT /api/dashboard/chat/sessions/{id}/draft` принимает `base_state_version`,
`expected_revision`, `draft`. Устаревшая версия или конкурирующее изменение —
409. Черновик не превращается в подтверждённое измерение. Калькулятор сохраняет
в браузере все поля формы; после передачи из чата синхронизирует черновик с
соответствующей версией диалога. При конфликте локальный черновик сохраняется.

## Повторение проверок

```powershell
python evaluations/stage9_server.py
python evaluations/validate_stage9.py --split development --label review
python evaluations/validate_stage9.py --split held_out --label review
```

Отдельный сервер использует порт 8770 и копию реальной рыночной базы.
Held-out запускается только после завершения разработки и заморозки кода;
его результаты нельзя использовать для настройки. Скрипт записывает первые
попытки, реальные tool traces, ошибки, версии и latency. Автоматические проверки
контрактов не заменяют экспертную оценку научной корректности и полезности.
Браузер: `node tests/stage9_browser.mjs` из `frontend`. Для контролируемого
испытания остановки backend задайте `STAGE9_CRASH_TEST=1`: скрипт запишет
`crash_ready.json`, после чего перезапускается только изолированный backend.
