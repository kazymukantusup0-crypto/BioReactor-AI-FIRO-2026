# Изолированный QA-клиент для уже загруженной Qwen3 4B

Клиент `evaluations/qwen4b_manual_chat.py` создаёт локальный FastAPI TestClient с существующим dashboard job endpoint и научным агентом, отдельной SQLite и отдельными JSON-журналами в `reports/qwen4b_manual_qa/`. Он обращается только к `127.0.0.1:11434`, не отправляет команды загрузки/выгрузки и проверяет `/api/ps` перед каждым модельным запросом: должна быть ровно `qwen3:4b-q4_K_M` и `context_length=4096`. Тайм-аут job по умолчанию 120 секунд; при нарушении действующей QA-политики или тайм-ауте клиент запрашивает отмену job. Трасса инструментов находится в `result.reply.tools`, подробности — в `result.reply.technical_metadata`; ответ, события, замеры и статус сохраняются в отдельном JSON. `--session` позволяет продолжить диалог по сохранённой QA-сессии.

Дополнение 2026-11-11: теперь требуется `--confirm-experimental`; один запуск отправляет не более одной Chat job и до шести модельных вызовов в рамках этой job. Клиент передаёт `keep_alive='5m'` на каждый вызов, сохраняя модель между шагами агента, и проверяет `/api/ps` после ответа; исчезновение модели или изменение доступного digest отклоняет результат вызова. Это не гарантирует отсутствия перезагрузки того же digest между проверками. Влияние удержания на ресурсы пока не измерено.

**Текущий статус: BLOCKED.** `evaluations/qwen3_4b_resource_policy.json` не содержит подтверждённых лимитов 4B и не одобряет режим с уже загруженной моделью. Клиент проверяет политику и сообщает конкретные причины, не выполняя Chat job. Ручная загрузка модели сама по себе не даёт ресурсного допуска. Не заполняйте неизвестные значения произвольными числами и не ставьте `manual_preloaded_approved=true` без подтверждённых оснований. Потребуются измеренные границы потребления и остановки для этого варианта, достаточный резерв и проверка конкурентных клиентов. Никакого реального LLM-теста при подготовке не выполнялось.

Проверка `/api/ps` и отправка `/api/chat` не атомарны: Ollama может выгрузить модель между ними или перезагрузить при несовпадении параметров. Общий Ollama API не предлагает этому клиенту проверяемого флага «только уже загруженная модель». Поэтому проверка снижает риск случайной загрузки, но не гарантирует её отсутствие. Ограничение одного вызова обеспечивается семафором внутри этого QA-процесса; состояние `OLLAMA_NUM_PARALLEL` общего сервера и запросы других приложений он не контролирует. При неизвестном параллелизме или конкурирующей нагрузке запускать реальную проверку нельзя. Клиент не меняет глобальные настройки Ollama, оставляя загрузку и выгрузку пользователю.

## Команды PowerShell после подтверждённого ресурсного допуска

Откройте PowerShell в каталоге проекта:

```powershell
Set-Location 'C:\Users\Kazhu\Downloads\face_dataset_you_noname\face_dataset_project\BioReactor_AI'
```

Убедитесь, что другие модели не загружены и для общего Ollama подтверждён параллелизм 1. Затем вручную загрузите модель с контекстом 4096. Этот запрос действительно может загрузить модель; выполняйте его только при ресурсном допуске:

```powershell
$body = @{ model = 'qwen3:4b-q4_K_M'; prompt = ''; stream = $false; keep_alive = '10m'; options = @{ num_ctx = 4096; num_batch = 32; num_gpu = -1 } } | ConvertTo-Json -Depth 6
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:11434/api/generate' -ContentType 'application/json; charset=utf-8' -Body ([System.Text.Encoding]::UTF8.GetBytes($body))
Invoke-RestMethod 'http://127.0.0.1:11434/api/ps' | ConvertTo-Json -Depth 8
```

Проверьте, что список содержит ровно нужную модель и `context_length` равен 4096. `num_gpu=-1` означает автоматический выбор размещения, а не гарантированный полный GPU offload.

Запишите вопрос в UTF-8 и отправьте его через изолированный QA-клиент:

```powershell
[System.IO.File]::WriteAllText((Join-Path (Get-Location) 'qa_question.txt'), 'Чем лабораторный BMP отличается от фактического выхода метана в реакторе?', [System.Text.UTF8Encoding]::new($false))
python -X utf8 evaluations/qwen4b_manual_chat.py --confirm-experimental --message-file qa_question.txt
```

В выводе появятся ответ, `session_id` и путь к JSON. Для следующего вопроса перепишите файл и передайте напечатанный идентификатор:

```powershell
[System.IO.File]::WriteAllText((Join-Path (Get-Location) 'qa_question.txt'), 'Уточни ограничения этой оценки.', [System.Text.UTF8Encoding]::new($false))
python -X utf8 evaluations/qwen4b_manual_chat.py --confirm-experimental --message-file qa_question.txt --session 'ВСТАВЬТЕ_SESSION_ID'
```

Посмотреть последний сохранённый результат:

```powershell
Get-ChildItem reports/qwen4b_manual_qa/*.json | Sort-Object LastWriteTime -Descending | Select-Object -First 1 | Get-Content -Encoding UTF8
```

После теста вручную выгрузите только эту модель и проверьте состояние:

```powershell
ollama stop qwen3:4b-q4_K_M
ollama ps
nvidia-smi --query-gpu=temperature.gpu,memory.used,utilization.gpu --format=csv
```

Запуск клиента завершается сам после ответа или отмены; отдельного веб-сервера QA он не оставляет. Фактическую остановку вычислений нельзя заключить только из статуса job. История в QA SQLite и JSON не является историей production Dashboard.

## Детерминированная проверка

```powershell
python -m pytest tests/test_qwen4b_manual_chat.py tests/test_qwen4b_resource_policy.py tests/test_qwen4b_scientific_integration.py tests/test_provider_cancellation.py -q -p no:cacheprovider --basetemp=.pytest-qwen4b-manual-final-v3-20261111
```

Результат: **44 passed**, одно предупреждение Starlette/httpx. Проверены отказы при отсутствии/неверной модели, контекст, блокировка неподтверждённой политики, вызов настоящего FastAPI endpoint с детерминированным провайдером и существующие тесты отмены. Эти проверки не являются реальными ответами Qwen. FIRO остаётся NOT READY.
