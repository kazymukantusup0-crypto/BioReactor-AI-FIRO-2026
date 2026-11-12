# Memory stability and Ollama cancellation hardening

**Date:** 2026-11-08 (Asia/Qyzylorda, UTC+05:00)  
**Current status:** **BLOCKED FOR LIVE CANCELLATION VERIFICATION.** The one controlled Qwen job documented in `reports/limited_qwen_cancellation_live_result.md` completed naturally before Cancel and is INCONCLUSIVE. This refresh did not launch another Qwen inference, browser E2E, or full acceptance. The current resource snapshot is not authorization or a pass for another live run.

## Starting state and preservation

- Branch: `main`. Starting commit: `38efb3a`.
- The worktree was already heavily modified before this task: `git status --short --untracked-files=no` reported 7,912 tracked paths. Existing changes were preserved; no reset, clean, commit, push, model retraining, dependency change, or version change was performed.
- The requested GPU/cancellation, root-cause, and reliability reports were reviewed. No applicable `AGENTS.md` was found in the repository or its parent directories.
- CUDA runner root cause remains unconfirmed. The earlier crash was recorded at 2026-11-08 19:38:57 local, with `CUDA error: shared object initialization failed` and child exit `0xc0000409`. A same-size 2,740 MiB host buffer was logged as CUDA_Host on a prior successful load but CPU during the failed load when free RAM had fallen from 6.1 GiB to 2.2 GiB. This is a clue, not proof of cause.

## Read-only resource observations

No user process was stopped and no system, power, driver, BIOS, cooling, Ollama, or model setting was changed.

| Local time | Available physical RAM | Commit charge / limit | GPU snapshot |
|---|---:|---:|---|
| 20:17:02 | 597-834 MiB across adjacent samples | about 61.98 / 63.07 GiB | RTX 3070 Laptop, 70 C, 32%, 783/8,192 MiB, 19 W; thermal slowdown inactive |
| 20:37-20:38 | about 8.78 GiB | 11.12 / 34.35 GiB | 62 C, 12%, 623/8,192 MiB, 18.34 W |
| 20:56:28 | 8.53 GiB | 12.42 / 34.35 GiB | 58 C, 16%, 644/8,192 MiB, 17.64 W |
| 21:04:51 | 8,795 MiB | 12,282,445,824 / 36,832,231,424 bytes | 57 C, 21%, 621/8,192 MiB, 17.71 W |
| 21:07:34 | 8,840 MiB | 12,220,874,752 / 36,832,231,424 bytes | 56 C, 19%, 622/8,192 MiB, 17.89 W, P8 |

At the latest sample, commit headroom was 24,611,356,672 bytes (about 22.92 GiB). GPU target was 87 C, slowdown temperature 98 C, and shutdown temperature 101 C. Hardware and software thermal slowdown were both `Not Active`. P-state is recorded for diagnosis only and is not a GPU admission criterion. These are time-specific observations, not universal safety thresholds. Recheck immediately before any later live test.

Windows CIM/WMI and `systeminfo.exe` memory queries were unavailable or access denied. Total RAM (15.8 GiB) was measured earlier through `GlobalMemoryStatusEx`; latest available RAM and commit values came from performance counters. Exact pagefile size was not confirmed.

### Pagefile and process observations

- Registry values showed `PagingFiles=?:\pagefile.sys` and `ExistingPageFiles=\??\C:\pagefile.sys`.
- Pagefile usage was about 2.06% at the latest sample; an earlier recorded peak was 35.05%. `Get-Item C:\pagefile.sys` did not find the file in this process view, and WMI/systeminfo access was denied.
- Top 15 processes by working set at 20:56: Code PID 17832 (544.8 MiB), Code 19120 (526.7), Code 26016 (395.6), MsMpEng 5796 (383.2), Code 20772 (277.4), Memory Compression 3744 (254.2), Code 24088 (216.0), Code 10272 (180.7), codex 9552 (174.9), Taskmgr 19752 (165.0), explorer 12536 (150.0), Code 26632 (141.8), Code 25904 (132.3), Code 15888 (125.6), Code 14000 (117.0). No process was stopped.
- Ollama is 0.40.15, NVIDIA driver 581.80, GPU RTX 3070 Laptop GPU with 8 GiB VRAM. At 21:07:34 `ollama ps` was empty; only the resident `ollama` service process was found, with no `llama-server` runner process. No model was loaded for this task.

## Changes made

### Cancellation transport

Before the change, the provider registered its close callback only after `connect()`, while a lock around `connection.request()` could block cancellation behind a pending send.

`src/agent/providers.py` now registers the per-job callback before connecting, performs TCP connection and TLS handshake using nonblocking readiness waits that check cancellation, publishes the active socket to the callback, and does not hold a lock across request send. `auto_open=0` prevents a reconnect after cancellation. Existing final cleanup closes response and connection; cancellation-related transport exceptions map to `ExecutionStopped`. Existing job ownership and commit-fence logic is retained. No production worker thread was added.

The provider timeout remains 45 seconds by default and configurable from 1 to 600 seconds. Synchronous OS `getaddrinfo` cannot be interrupted by this thread-based transport without adding a worker thread. The local Ollama URL uses numeric loopback and avoids DNS; remote hostname resolution remains a cancellation-latency limitation.

### GPU gate

`reports/final_acceptance/gpu_gate.py` no longer requires P8. P-state remains diagnostic. Temperature and device target, thermal slowdown telemetry, active hardware slowdown refusal, and bounded wait behavior remain. Missing required thermal telemetry still blocks admission. No GPU or system settings were changed.

### Files changed in this task

- `src/agent/providers.py`
- `tests/test_provider_cancellation.py`
- `reports/final_acceptance/gpu_gate.py`
- `tests/test_acceptance_gpu_gate.py`
- `reports/limited_qwen_cancellation_live_test.md`
- `reports/memory_and_cancellation_hardening.md`
- Append-only updates to `reports/gpu_gate_cancellation_audit.md` and `reports/reliability_scientific_audit.md`

No application API path, dependency, model, quantization, context setting, or project version was changed.

## Verification

Focused regression command:

    python -m pytest tests/test_provider_cancellation.py tests/test_stage9_jobs.py tests/test_agent.py tests/test_stage9_runtime.py tests/test_autonomous_agent.py tests/test_conversation.py tests/test_advanced_conversation.py tests/test_analytical_response.py tests/test_stage9_verification.py tests/test_stage85_research.py tests/test_acceptance_gpu_gate.py -q -p no:cacheprovider --basetemp "$env:TEMP\pytest-ollama-cancel-hardening-verified-20261108"

**PASSED: 260 tests, one existing Starlette/httpx deprecation warning, 32.50 seconds.** Tests cover cancellation before request, pending TCP connect, blocked send, response wait, streaming, HTTPS handshake, repeated cancellation, timeout, HTTP error cleanup, independent concurrent requests, job ownership/deadline loss, late-result commit fences, and GPU thermal/P-state gate behavior.

Compile command:

    python -m py_compile src/agent/providers.py src/agent/cancellation.py src/dashboard/jobs.py src/dashboard/job_api.py src/dashboard/api.py reports/final_acceptance/gpu_gate.py tests/test_provider_cancellation.py tests/test_stage9_jobs.py tests/test_acceptance_gpu_gate.py

**PASSED.** Scoped `git diff --check -- src/agent/providers.py src/dashboard/jobs.py src/dashboard/job_api.py src/dashboard/api.py` also passed; Git emitted only LF-to-CRLF working-copy notices.

At the time of this original deterministic verification, no real HTTP inference was run. A later one-shot real-Qwen job is documented separately and ended INCONCLUSIVE; browser E2E and full acceptance remain NOT RUN.

## Remaining limitations and status

- Real Ollama cancellation remains **PARTIALLY FIXED**. The latest one-shot job completed naturally before Cancel; its HTTP close time and cancellation behavior were not measured.
- The legacy synchronous `/api/dashboard/chat/sessions/{id}/messages` route does not use `JobRuntime` cancellation and remains non-cancellable.
- The cause of the CUDA runner crash is unconfirmed. Better current memory readings do not prove a future model load will succeed.
- Synchronous OS DNS resolution cannot be promptly cancelled for remote hostnames.
- Exact pagefile size is unavailable under current permissions.
- Full Chrome/Qwen acceptance and FIRO readiness are **NOT RUN / NOT ESTABLISHED**.

The earlier three-sample preflight supported the single attempt that has already been consumed. A future test would need separate authorization, a new fresh resource preflight, and a live progress/socket observation that can trigger Cancel before natural completion. The current instructions are in `reports/limited_qwen_cancellation_live_test.md`; that plan now records the observed real-time logging limitation. No new live request was made during this refresh.

## Follow-up status after the one-shot live attempt - 2026-11-08 23:04 local

This addendum supersedes the earlier PREPARED FOR LIVE TEST status. That earlier status predated the controlled job in `reports/limited_qwen_cancellation_live_result.md`. One real Qwen3 8B asynchronous job ran and completed naturally before Cancel; status **INCONCLUSIVE**. No second request or cancellation-after-completion was attempted. For this refresh, no Qwen, browser E2E, or full acceptance was run.

### Current read-only resources

At 23:04:18.483 +05:00: total physical RAM 15.8 GiB (previously measured with GlobalMemoryStatusEx); available RAM 8,741 MiB; commit 13,299,261,440 / 36,559,769,600 bytes, headroom 23,260,508,160 bytes (about 21.66 GiB); pagefile usage 1.73%, recorded peak 35.63%. Registry still reports `?:\pagefile.sys` and `\??\C:\pagefile.sys`; exact pagefile file size is unavailable. WMI/systeminfo restrictions remain. This single snapshot is informational, not a three-sample live-test gate.

RTX 3070 Laptop GPU, driver 581.80: 60 C, 22% utilization, 902/8,192 MiB VRAM, 18.06 W, P8. Device target 87 C, slowdown 98 C, shutdown 101 C; HW and SW thermal slowdown both Not Active. P-state remains diagnostic only. Ollama 0.40.15 was running, `ollama ps` and `/api/ps` were empty, and no established client connection to port 11434 was observed. No model was loaded at this snapshot.

Top 15 processes by working set at 23:04 (observations only; none were stopped): Memory Compression PID 3744 (787.3 MiB); Code 17832 (375.6); Code 19120 (333.5); MsMpEng 5796 (306.5); WhatsApp.Root 29048 (266.7); Code 26016 (262.9); Code 20772 (214.9); explorer 12536 (166.2); Taskmgr 19752 (160.8); PowerShell 10396 (156.0); codex 9552 (144.4); Code 24088 (140.0); PhoneExperienceHost 9328 (135.3); StartMenuExperienceHost 23072 (119.2); Code 26632 (118.6) MiB.

### Deterministic verification in this refresh

Command: `python -m pytest tests/test_provider_cancellation.py tests/test_stage9_jobs.py tests/test_agent.py tests/test_stage9_runtime.py tests/test_autonomous_agent.py tests/test_conversation.py tests/test_advanced_conversation.py tests/test_analytical_response.py tests/test_stage9_verification.py tests/test_stage85_research.py tests/test_acceptance_gpu_gate.py -q -p no:cacheprovider --basetemp "$env:TEMP\pytest-hardening-refresh-20261108b"` — **260 passed**, one existing Starlette/httpx deprecation warning, 34.80 s. The suite used deterministic providers/fixtures; it did not launch real Qwen.

`python -m py_compile src/agent/providers.py src/agent/cancellation.py src/dashboard/jobs.py src/dashboard/job_api.py src/dashboard/api.py reports/final_acceptance/gpu_gate.py tests/test_provider_cancellation.py tests/test_stage9_jobs.py tests/test_acceptance_gpu_gate.py` — **PASSED**. Scoped `git diff --check` — **PASSED**, with existing LF-to-CRLF notices.

### Confirmed implementation and remaining limits

The provider currently registers cancellation before TCP connect, uses cancellable nonblocking TCP/TLS readiness waits, allows socket shutdown during send, prevents automatic reconnect, closes response/connection in final cleanup, and maps cancellation transport errors to `ExecutionStopped`. The deterministic tests cover cancellation through connect, send, response, streaming, timeouts, ownership, late commit fences, parallel isolation, and cleanup. Synchronous OS DNS resolution remains non-interruptible; local Ollama uses numeric loopback.

The GPU gate no longer requires P8; missing thermal telemetry, temperature at/above device target, and active HW slowdown remain refusal conditions, with bounded wait. The live run nevertheless did not prove the async Cancel path: its saved report shows `n_gen`/timing output was observed together with task completion/release, no Cancel was sent, no provider socket close was timed, and the final answer was saved normally. Ollama slot release in that run was natural task completion, not cancellation evidence.

**Disposition: BLOCKED for live cancellation verification; NOT READY for full acceptance/FIRO.** The environment snapshot is favorable but not a live gate, CUDA crash cause remains unconfirmed, legacy synchronous chat remains non-cancellable, and the one-shot attempt was inconclusive. Any future live test requires a fresh preflight and a reliable real-time generation/socket signal before starting its single job. Do not rerun Qwen under this update.

Repository remains on `main` at `38efb3a`; the worktree was already dirty (7,912 tracked modified/deleted entries at this check). No code or user processes were changed/stopped during this refresh; the previously created QA backend is already stopped and the shared Ollama process remains running.

### Cancellation timing method refresh — 2026-11-09

The prior one-shot Qwen job completed naturally before Cancel and remains INCONCLUSIVE. Its first Dashboard poll was 15.6 s after submission; task-level `n_gen` and timing lines were only observed with task completion/release. The earlier report does not preserve polling cadence or the exact completion-log observation time, so those delays cannot be reconstructed. No new Qwen request was run.

The replacement test procedure and dedicated QA-only wrapper now trigger one ordinary Dashboard Cancel synchronously on the first received nonempty Ollama NDJSON content chunk (`done=false`), with a 1 s local API timeout and at-most-once cleanup. Provider timestamp events include stream content, transport close, and request close. Missing telemetry blocks; natural completion or a 45 s missing-signal timeout is inconclusive; VERIFIED requires the additional job/state/Ollama evidence in `reports/limited_qwen_cancellation_live_test.md`.

Deterministic tests: `python -m pytest tests/test_cancellation_timing.py tests/test_provider_cancellation.py tests/test_stage9_jobs.py -q -p no:cacheprovider --basetemp="$env:TEMP\\pytest-live-cancel-timing-final6"` — **44 passed**, one existing Starlette/httpx deprecation warning, 21.51 s. A no-lifespan TestClient smoke returned `arm=200`, `status=200`, and incomplete-evidence=`INCONCLUSIVE`; it did not start an inference worker. No Qwen, browser E2E, full acceptance, GPU measurement, or system/Ollama change was made. The harness is prepared for one future controlled live run after a fresh resource gate; real cancellation is still unverified.
