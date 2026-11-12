# One-shot Qwen cancellation live test

**Scope:** one isolated asynchronous Dashboard job against the existing local Qwen3 8B / Ollama runtime. This is an instruction for a later session; it was **not run** while preparing it. Do not launch a browser suite or full acceptance from this guide.

**Method update (2026-11-09):** For QA server startup, generation detection, and Cancel, use the final “Deterministic real-time trigger” section below. It supersedes the earlier manual `n_gen` polling trigger and `reliability_qwen_server.py` startup steps. Keep the resource gate and stop/cleanup requirements above.

## Stop conditions

- If CUDA runner initialization fails before active generation, record the error/dump and stop. Do not retry the model load in the same session.
- If memory, commit, GPU, or telemetry preflight fails, do not submit the job.
- For this legacy/manual method only: if the single job completes first, mark the run `INCONCLUSIVE`; do not start another. Use the current stream-trigger method below; Ollama logs are corroboration, not its Cancel trigger.
- Bound the wait for a terminal job state after Cancel to 10 seconds. Exceeding it is `BLOCKED`; preserve the process/log state for diagnosis.
- Never stop the shared Ollama service or user applications. Stop only the isolated QA API started for this test, with Ctrl+C in its own terminal.

## 1. Resource preflight

Use a fresh PowerShell terminal at the repository root. Capture RAM and commit counters, pagefile registry values, top processes, and GPU readings:

```powershell
$mem = Get-Counter '\Memory\Available MBytes','\Memory\Committed Bytes','\Memory\Commit Limit'
$mem.CounterSamples | Select-Object Path,CookedValue | Format-Table -AutoSize
$values = @{}
foreach ($sample in $mem.CounterSamples) {
    if ($sample.Path -like '*\Memory\Available MBytes') { $values.available_mib = $sample.CookedValue }
    if ($sample.Path -like '*\Memory\Committed Bytes') { $values.committed_bytes = $sample.CookedValue }
    if ($sample.Path -like '*\Memory\Commit Limit') { $values.commit_limit_bytes = $sample.CookedValue }
}
$values.commit_headroom_bytes = $values.commit_limit_bytes - $values.committed_bytes
$values | Format-List
Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Memory Management' |
    Select-Object PagingFiles,ExistingPageFiles
Get-Counter '\Paging File(_Total)\% Usage','\Paging File(_Total)\% Usage Peak' |
    Select-Object -ExpandProperty CounterSamples | Select-Object Path,CookedValue
Get-Process | Sort-Object WorkingSet64 -Descending | Select-Object -First 15 ProcessName,Id,
    @{n='WorkingSetMiB';e={[math]::Round($_.WorkingSet64/1MB,1)}},
    @{n='PrivateMiB';e={[math]::Round($_.PrivateMemorySize64/1MB,1)}} | Format-Table -AutoSize
nvidia-smi
```

For this exact model and launch configuration, use the earlier successful load as a **case-specific comparison**, not a universal system threshold: it had 6.1 GiB free physical RAM and 20.5 GiB `free_swap` in Ollama’s log with the same 2,740 MiB `CUDA_Host` model buffer. Do not proceed if available RAM is below that successful observation, or if commit headroom/pagefile use is close to exhaustion or deteriorating. The failed load had only 2.2 GiB free and logged the same-sized model buffer as plain `CPU`.

The last preflight in this investigation was 2026-11-08 20:56:28 +05:00: 15.8 GiB physical RAM, 8.53 GiB available, 34.35 GiB commit limit, 22.8 GiB commit headroom, pagefile usage 2.09%, RTX 3070 Laptop GPU 58 °C / 16% / 644 of 8,192 MiB, target 87 °C, slowdown 98 °C, shutdown 101 °C, hardware and software thermal slowdown inactive. This is a historical snapshot; recheck immediately before the test.

Run a three-sample thermal gate. P-state is recorded but is not a pass/fail condition. Missing temperature/target/slowdown telemetry, a temperature at/above the device target, or active hardware thermal slowdown blocks the run. The total gate wait is capped at five minutes in this one-shot procedure.

```powershell
@'
import json, re, subprocess, sys
from reports.final_acceptance.gpu_gate import GPUWaitTimeout, wait_for_gpu_idle

def read_gpu_state():
    row = subprocess.check_output(
        ['nvidia-smi', '--query-gpu=temperature.gpu,utilization.gpu,pstate',
         '--format=csv,noheader,nounits'], timeout=5, text=True).strip().splitlines()[0]
    temp, util, pstate = (part.strip() for part in row.split(','))
    details = subprocess.check_output(
        ['nvidia-smi', '-q', '-d', 'TEMPERATURE,PERFORMANCE'], timeout=5, text=True)
    target = re.search(r'^\s*GPU Target Temperature\s*:\s*(\d+)\s*C\s*$', details, re.M)
    slowdown = re.search(r'^\s*HW Thermal Slowdown\s*:\s*(Active|Not Active)\s*$', details, re.M)
    return (float(temp), float(util), pstate,
            int(target.group(1)) if target else None,
            (slowdown.group(1) == 'Active') if slowdown else None)

try:
    result = wait_for_gpu_idle(read_gpu_state, timeout_seconds=300,
                               interval_seconds=10, consecutive_samples=3)
    print(json.dumps(result, indent=2))
except GPUWaitTimeout as exc:
    print(json.dumps(exc.diagnostics, indent=2))
    sys.exit(2)
'@ | python -
if ($LASTEXITCODE -ne 0) { throw 'BLOCKED: GPU thermal gate did not pass.' }
```

Then confirm there is no loaded model or other inference request before starting the isolated backend:

```powershell
ollama ps
Invoke-RestMethod http://127.0.0.1:11434/api/ps | ConvertTo-Json -Depth 5
Get-NetTCPConnection -LocalPort 11434 -State Established -ErrorAction SilentlyContinue |
    Select-Object LocalAddress,LocalPort,RemoteAddress,RemotePort,OwningProcess
```

`ollama ps`/`/api/ps` show loaded models, not every active request; also confirm that no other local QA or application job is currently calling Ollama. Do not close the apps that own those requests.

## 2. Start one isolated QA API — ARCHIVED (superseded; do not execute)

In a separate PowerShell terminal at the repository root, choose a new temporary database name and a free loopback port. The server script copies the market DB into the new temp path only if it does not exist; it does not use the active market DB for writes.

```powershell
$env:BIOREACTOR_QA_DB = Join-Path $env:TEMP ("bioreactor_cancel_one_" + (Get-Date -Format 'yyyyMMdd_HHmmss') + '.sqlite3')
$env:BIOREACTOR_QA_PORT = '8774'
python evaluations/reliability_qwen_server.py
```

Keep this terminal open. Do not set persistent Windows environment variables. If port 8774 is occupied, choose a free port and use it consistently below.

## 3. Submit a single asynchronous job — ARCHIVED (old detection method; do not execute)

In another PowerShell terminal, record the Ollama log path and start a separate log tail **before** submitting the job:

```powershell
$base = 'http://127.0.0.1:8774'
$ollamaLog = Join-Path $env:LOCALAPPDATA 'Ollama\server.log'
Get-Content -LiteralPath $ollamaLog -Tail 0 -Wait |
    Select-String -Pattern 'starting llama-server|model loaded|task|n_gen|n_tokens|stop processing|eval time|CUDA error'
```

Submit exactly one job from a second terminal:

```powershell
$base = 'http://127.0.0.1:8774'
$sessionBody = @{mode='offline';context=@{};conversation_version='7'} | ConvertTo-Json -Depth 6
$session = Invoke-RestMethod -Method Post -Uri "$base/api/dashboard/chat/sessions" `
    -ContentType 'application/json' -Body $sessionBody
$before = Invoke-RestMethod "$base/api/dashboard/chat/sessions/$($session.id)"
$request = @{
    message = 'У меня 5 кг пищевых отходов. Дай краткую научную оценку потенциального метана, отдели литературный диапазон от измерения и назови основные неизвестные.'
    request_id = [guid]::NewGuid().ToString('N')
    expected_state_version = $before.state_version
} | ConvertTo-Json -Depth 6
$job = Invoke-RestMethod -Method Post -Uri "$base/api/dashboard/chat/sessions/$($session.id)/jobs" `
    -ContentType 'application/json' -Body $request
$job | ConvertTo-Json -Depth 6
```

Wait for a **new task** in `server.log` and evidence that its generation counter has advanced (`n_gen`/token-progress entry). Record its task ID, the latest progress value, and timestamp. A `RUNNING` job, an HTTP 202, or a resident model alone is not proof of active token generation. If the response finishes or the log never exposes progress for the task, record `INCONCLUSIVE` and do not issue another Qwen request.

## 4. Cancel while generation is confirmed active — ARCHIVED (do not execute; no manual Cancel)

Only after the log confirms active token generation for this job, send one Cancel and time the HTTP operation:

```powershell
$jobId = '<ID returned by the single POST>'
$cancelClock = [Diagnostics.Stopwatch]::StartNew()
$cancel = Invoke-RestMethod -Method Post -Uri "$base/api/dashboard/jobs/$jobId/cancel" `
    -ContentType 'application/json' -Body '{}'
$cancelClock.Stop()
"cancel_http_ms=$($cancelClock.Elapsed.TotalMilliseconds)"
$cancel | ConvertTo-Json -Depth 6
```

Poll for terminal state with a strict 10-second limit:

```powershell
$deadline = [DateTime]::UtcNow.AddSeconds(10)
do {
    $status = Invoke-RestMethod "$base/api/dashboard/jobs/$jobId"
    if ($status.terminal) { break }
    Start-Sleep -Milliseconds 100
} while ([DateTime]::UtcNow -lt $deadline)
$status | ConvertTo-Json -Depth 6
if (-not $status.terminal) { throw 'BLOCKED: job did not reach a terminal state within 10 seconds.' }
```

Immediately inspect the task-specific Ollama log and TCP state. Record the last generation progress before Cancel and whether the same task emits later progress or a normal completed-generation record after Cancel. If available, record when the established client connection to port 11434 disappears; an unavailable TCP row is a limitation, not proof by itself.

```powershell
Get-NetTCPConnection -LocalPort 11434 -State Established -ErrorAction SilentlyContinue |
    Select-Object LocalAddress,LocalPort,RemoteAddress,RemotePort,OwningProcess
```

## 5. Verify no late result and release

```powershell
$result = Invoke-RestMethod "$base/api/dashboard/jobs/$jobId/result"
$after = Invoke-RestMethod "$base/api/dashboard/chat/sessions/$($session.id)"
$result | ConvertTo-Json -Depth 8
$after | Select-Object state_version,turns | ConvertTo-Json -Depth 8
ollama ps
Invoke-RestMethod http://127.0.0.1:11434/api/ps | ConvertTo-Json -Depth 5
```

Expected for a successful cancellation: job terminal status `CANCELLED`; result reply remains null; the cancelled turn has no reply and does not advance the session state version; the correlated Ollama task stops producing generation progress; the request socket closes. The Qwen model may remain resident in VRAM; that alone is not continued inference. If the Ollama log cannot distinguish progress after Cancel from delayed logging, report that part as `INCONCLUSIVE`, not `PASS`.

After preserving terminal status, result JSON, session state, task log lines, timings, and before/after RAM/GPU readings, press Ctrl+C in the isolated QA API terminal only. Leave the shared Ollama process and all user applications alone. Do not delete the temporary SQLite or dump/log artifacts.

## Later read-only resource sample

At 2026-11-08 21:07:34 +05:00, available RAM was 8,840 MiB and commit headroom was about 22.92 GiB. The RTX 3070 Laptop GPU was at 56 C, 19% utilization, and 622/8,192 MiB VRAM; target 87 C, slowdown 98 C, shutdown 101 C; HW/SW thermal slowdown was inactive. Ollama 0.40.15 was responsive and `ollama ps` was empty. This is a historical sample, not a persistent pass: repeat the documented three-sample thermal/telemetry and memory gate immediately before any live request.

## Safety note from the one-shot run - 2026-11-08

The one-job attempt in `reports/limited_qwen_cancellation_live_result.md` completed before Cancel. In that run, runner timing and `n_gen` records reached the observer only together with task completion/release output; the first status snapshot showed `RUNNING/understanding` and prompt processing, but did not prove live token generation. Do not treat `RUNNING`, `model loaded`, `processing task`, or a delayed `n_gen` line as a real-time cancellation trigger. A future separately authorized run needs an already validated real-time progress or socket signal; if none is visible before natural completion, record INCONCLUSIVE and do not submit another job.

## Deterministic real-time trigger — method current as of 2026-11-09

### Why the previous trigger failed

The 2026-11-08 run polled Dashboard status at 21:24:07.491, 15.6 seconds after job submission, and saw `RUNNING/understanding` plus task processing. That was not a generation signal. Ollama timing and `n_gen` lines appeared to the observer later with natural task completion/release; the task lines had no per-line wall-clock timestamps. The job completed at 21:24:45.071890. Its long-form prompt led to three sequential model calls (373 generated tokens total), but no Cancel was sent. The poll interval, exact time the completion log was read, and generation-start-to-detection delay were not preserved, so those delays cannot be reconstructed. The test gated on delayed log polling and encountered a completed job at its later observation.

### Trigger and evidence

The QA-only provider observer fires synchronously when the cancellable Ollama NDJSON reader parses a nonempty `message.content` chunk with `done=false`. This is a real response chunk received from an open HTTP stream. `RUNNING`, a loaded model, task-start logs, and `n_gen` are not triggers. The observer immediately sends one POST to the ordinary Dashboard Cancel endpoint from the provider worker. The endpoint's cancellation signal closes that request's socket; the provider records transport and request closure and cannot return a partial or late response. Ollama task logs corroborate post-Cancel behavior but do not trigger Cancel.

The loopback Cancel HTTP call is bounded to one second. If it errors, the QA observer attempts local socket cancellation for safety and marks telemetry `BLOCKED`. A content chunk alone does not prove the inference was still computing by the time the local Cancel route received it; natural completion can race the request. Therefore VERIFIED also requires the cancellation-caused socket close, `CANCELLED` job with no saved reply/state advance, correlated Ollama slot release, and no post-Cancel progress or normal completion record. Ambiguous runner logs mean `INCONCLUSIVE`.

### One-job setup and bounded observation

Run the existing three-sample resource gate immediately before startup. Use a fresh SQLite path and the dedicated QA wrapper; do not use the regular app database:

```powershell
$runDir = Join-Path $env:TEMP ("bioreactor_cancel_controlled_" + (Get-Date -Format 'yyyyMMdd_HHmmss'))
New-Item -ItemType Directory -Path $runDir | Out-Null
$env:BIOREACTOR_QA_DB = Join-Path $runDir 'isolated.sqlite3'
$env:BIOREACTOR_CANCEL_QA_PORT = '8775'
python evaluations/controlled_cancellation_server.py
```

In a second terminal, start capturing Ollama's server log before job submission. Keep it as evidence only; do not wait for `n_gen` to send Cancel:

```powershell
$ollamaLog = Join-Path $env:LOCALAPPDATA 'Ollama\server.log'
Get-Content -LiteralPath $ollamaLog -Tail 0 -Wait |
    Tee-Object -FilePath (Join-Path $env:TEMP 'bioreactor_cancel_controlled_ollama_tail.txt')
```

Arm one 45-second probe before creating/submitting the job. Use one concise request. The provider observer, not the polling loop, sends Cancel:

```powershell
$base = 'http://127.0.0.1:8775'
Invoke-RestMethod -Method Post -Uri "$base/__qa/cancellation/arm" `
    -ContentType 'application/json' -Body '{"timeout_seconds":45}'
$sessionBody = @{mode='offline';context=@{};conversation_version='7'} | ConvertTo-Json -Depth 5
$session = Invoke-RestMethod -Method Post -Uri "$base/api/dashboard/chat/sessions" `
    -ContentType 'application/json' -Body $sessionBody
$before = Invoke-RestMethod "$base/api/dashboard/chat/sessions/$($session.id)"
$request = @{
    message = 'Оцени предварительный потенциал метана для 5 кг пищевых отходов и обозначь допущения.'
    request_id = [guid]::NewGuid().ToString('N')
    expected_state_version = $before.state_version
} | ConvertTo-Json -Depth 5
$job = Invoke-RestMethod -Method Post -Uri "$base/api/dashboard/chat/sessions/$($session.id)/jobs" `
    -ContentType 'application/json' -Body $request
$jobId = $job.id
$deadline = [DateTime]::UtcNow.AddSeconds(55)
do {
    $probe = Invoke-RestMethod "$base/__qa/cancellation/status"
    $status = Invoke-RestMethod "$base/api/dashboard/jobs/$jobId"
    if ($probe.status -in @('CANCEL_SENT','NATURAL_DONE','INCONCLUSIVE','BLOCKED','CANCEL_REJECTED') -or $status.terminal) { break }
    Start-Sleep -Milliseconds 50
} while ([DateTime]::UtcNow -lt $deadline)
```

Do not issue a second/manual Cancel. If the probe reports `NATURAL_DONE`, a terminal job occurs before a content signal, or the 45-second wait expires, record `INCONCLUSIVE` and do not submit another inference. Telemetry failure is `BLOCKED`; the observer attempts one bounded safety Cancel and closes the local request socket. After an accepted Cancel, wait at most 10 seconds for a terminal job state; otherwise record `BLOCKED` and preserve logs.

### Final evidence and classification

Preserve the probe events and timestamps. Inspect job result, session version, task-specific Ollama log ordering and slot release, active connections if observable, and `ollama ps`/`/api/ps`. Model residency in VRAM alone is not evidence of continuing inference. The finalizer fills current job status and whether a reply was saved. Supply the other observations:

```powershell
$after = Invoke-RestMethod "$base/api/dashboard/chat/sessions/$($session.id)"
$evidence = @{
    telemetry_ok = ($probe.status -ne 'BLOCKED')
    state_version_before = $before.state_version
    state_version_after = $after.state_version
    slot_released_after_cancel = $slotReleasedAfterCancel
    ollama_progress_after_cancel = $progressAfterCancel
    normal_completion_logged = $normalCompletionLogged
} | ConvertTo-Json -Depth 4
Invoke-RestMethod -Method Post -Uri "$base/__qa/cancellation/finalize" `
    -ContentType 'application/json' -Body $evidence
```

Set the three Ollama evidence variables to explicit `$true`/`$false` only when the task-specific log supports the value. Leave them unset/`$null` when uncertain; the finalizer will return `INCONCLUSIVE`.

`VERIFIED` requires all evidence: valid nonterminal content timestamp before Cancel; exactly one accepted Dashboard Cancel; provider transport-close and request-close events after Cancel with cancellation reason; job `CANCELLED`; no saved reply and unchanged session version; correlated Ollama slot release after Cancel; no post-Cancel generation progress; and no normal-completion record. Missing or ambiguous evidence is `INCONCLUSIVE`; observed post-Cancel generation/normal completion is `FAILED`; instrumentation failure is `BLOCKED`. One verified run would not establish project-wide readiness.

Stop only the dedicated QA backend with Ctrl+C in its own terminal. Do not stop shared Ollama or user apps. Preserve the isolated database and log slice.
