# Controlled Qwen cancellation live test result

**Date:** 2026-11-08, Asia/Qyzylorda (UTC+05:00)  
**Result:** **INCONCLUSIVE**  
**Scope:** Exactly one asynchronous Dashboard job was submitted to a temporary QA backend. It completed naturally before a cancellation could be issued. No second Qwen request was made.

## Summary

The three-sample resource gate passed. A real local Qwen3 8B runner loaded successfully and processed the single job, so this attempt did not reproduce the earlier CUDA initialization crash. The job made three sequential Ollama model calls and reached `COMPLETED`; the response was saved. We did not send Cancel while token generation was confirmed live. Therefore this run provides no evidence that Cancel interrupts Ollama inference, and no cancel latency, post-Cancel token count, cancellation socket-close time, or `CANCELLED` transition can be reported.

The runner's timing and `n_gen` records were received together with task completion/release records by the log-tail poll. The first status snapshot during the job showed a running `understanding` stage and a runner task processing a prompt, but no live token counter or client socket was observable in that snapshot. The later poll found the job already complete. This observation method did not give a reliable real-time cancellation trigger. The one-shot limit was honored; no retry was attempted.

## Three-sample preflight

Measurements were taken immediately before backend launch, with start times 9.958 and 10.023 seconds apart. GPU P-state was recorded only as diagnostic data. Device thermal limits were reported by the GPU itself.

| Sample start, local | Available RAM | Commit headroom | Pagefile use | GPU temperature / target | HW / SW thermal slowdown | GPU use | VRAM | Power / P-state | Ollama state |
|---|---:|---:|---:|---|---|---:|---:|---|---|
| 21:20:13.650 | 8,690 MiB | 24,653,291,520 bytes | 2.01% | 56 C / 87 C | Not Active / Not Active | 9% | 618 / 8,192 MiB | 18.05 W / P8 | Ollama 0.40.15; `ollama ps` empty; `/api/ps` empty; no established client to port 11434 |
| 21:20:23.608 | 8,626 MiB | 24,592,801,792 bytes | 2.01% | 55 C / 87 C | Not Active / Not Active | 9% | 618 / 8,192 MiB | 17.72 W / P8 | Same: no loaded model or client connection |
| 21:20:33.631 | 8,612 MiB | 24,581,529,600 bytes | 2.01% | 56 C / 87 C | Not Active / Not Active | 10% | 617 / 8,192 MiB | 17.83 W / P8 | Same: no loaded model or client connection |

Slowdown and shutdown temperatures were 98 C and 101 C. Available RAM remained above the case-specific prior successful-load observation of 6.1 GiB; commit headroom was stable and pagefile use remained low. No user application was stopped. An earlier incomplete sampling command had passed an unsupported flag to `nvidia-smi`; it produced no GPU values and was discarded. The three complete samples above were then collected before any inference.

Preflight evidence: `%TEMP%\bioreactor_qwen_cancel_preflight_20261108_verified.json`.

## Isolated test setup

- QA backend: `evaluations/reliability_qwen_server.py`, bound to `127.0.0.1:8774`; the port was free before launch.
- QA backend PID: 22660. Isolated SQLite file: `%TEMP%\bioreactor_cancel_one_20261108_212134.sqlite3`.
- No shared Ollama configuration was changed. The QA process used `qwen3:8b`, context 8192, 16 GPU layers, 150-second provider/agent timeouts, 180-second job timeout, and offline research mode.
- Before job submission, Ollama reported no loaded model, `/api/ps` returned an empty list, and no established client connection to port 11434 was observed.
- Ollama model/server version: 0.40.15. GPU: NVIDIA RTX 3070 Laptop GPU, driver 581.80.
- The monitored local Ollama server log was `%LOCALAPPDATA%\Ollama\server.log`.

## Single job and real-model evidence

The one prompt requested a detailed, long-form explanation of anaerobic digestion of food waste. It was submitted as one asynchronous Dashboard job; no parallel request was submitted.

- Session: `3128a97367464afa84958dbf39c94b1c`
- Job: `a163c4bd1a4c47aeb13248ff2c8e65a7`
- Request: `aabd17df19ca4f53b9be5be5e8869b99`
- POST started: 2026-11-08 21:23:51.859 +05:00; response returned at 21:23:51.881 (+05:00).
- Ollama logged `starting llama-server` at 21:23:55.190 +05:00, then `model loaded`. The runner command included `-c 8192 -np 1 -ngl 16 -b 64 -ub 64`; it loaded the local model blob.
- The first observed Dashboard snapshot at 21:24:07.491 +05:00 showed `RUNNING`, stage `understanding`. The runner log showed task 0 processing a prompt. At that snapshot GPU was 58 C, 25% utilization, and 3,594 MiB VRAM. No live `n_gen` line or established client socket was captured in that snapshot.
- The job's persisted `updated_at` was 2026-11-08 16:24:45.071890 UTC, equivalent to 21:24:45.071890 +05:00. Status was `COMPLETED`, attempt count 1. The result had a saved reply (337-character answer), two partial/tool results, and session state version advanced from 0 to 1.
- At the later status/log poll, the job was already complete. The runner emitted normal completion timing and `stop processing` records for its tasks. The task log records themselves had no wall-clock timestamps.

After completion, `/api/ps` identified the actual model as `qwen3:8b`, Qwen3 family, 8.2B parameters, Q4_K_M, llama.cpp runner, context 8192, with 2,906,505,870 bytes reported as VRAM-resident. The local model runner therefore did execute; this was not a fake provider result. No CUDA error appeared in the captured slice.

### Runner task records

The single Dashboard job caused three sequential model tasks in the Ollama runner:

| Ollama task | Prompt evaluation | Generated tokens and evaluation | Total runner time | End record |
|---|---|---|---:|---|
| 0 | 257 tokens, 1.629 s | 243 tokens, 24.505 s; timing entries included `n_gen=100, 131, 161, 193, 225` | 26.135 s | Normal `stop processing`, `n_tokens=499` |
| 248 | 642 tokens, 3.642 s | 61 tokens, 5.921 s | 9.563 s | Normal `stop processing`, `n_tokens=705` |
| 320 | 147 tokens, 1.219 s | 69 tokens, 7.063 s | 8.283 s | Normal `stop processing`, `n_tokens=708` |

Total generated output logged across the three sequential calls was 373 tokens. These records show that generation occurred, but the output did not reach the observer in time to send Cancel before the job completed. They are not evidence of cancellation.

## Cancellation and delivery measurements

| Requested measurement | Result |
|---|---|
| Generation start time | Runner start is timestamped 21:23:55.190; individual runner task/generation start lines have no timestamps. Exact token-generation start is not measurable from this log. |
| Cancel request time / HTTP duration | **Not sent.** The job had completed before active generation was confirmed to the observer. |
| HTTP connection close time | **Not measured.** No provider socket was visible in the sampled `Get-NetTCPConnection` snapshots; no continuous socket trace was captured. |
| Ollama generation stop time | No cancellation stop occurred. Tasks 0, 248, and 320 ended normally; exact wall-clock times are absent from runner lines. |
| Job transition to `CANCELLED` | Did not occur; job reached `COMPLETED` at 21:24:45.071890 +05:00. |
| Tokens before/after Cancel | Cancel-specific counts are **not applicable**. The three completed calls logged 243, 61, and 69 generated tokens; tokens after Cancel cannot be measured because no Cancel was sent. |
| GPU before/after Cancel | No cancel comparison is possible. During the first observed running snapshot: 58 C, 25%, 3,594 MiB. At 21:27:00.570: 57 C, 19%, 3,603 MiB. At 21:28:25.982: 56 C, 28%, 3,606 MiB; HW/SW thermal slowdown remained Not Active. |
| Partial/late answer | A normal final answer was saved after natural completion. No post-Cancel or late-result behavior was tested. |
| Inference slot | Each task logged a normal release. A cancel-triggered release was not tested. The model remained resident in VRAM with an Ollama keep-alive expiry of 21:29:44.968 +05:00; residency alone does not indicate continued generation. |

## Cleanup and preserved evidence

The created log-tail monitor was stopped. Ctrl+C closed the QA listener, but its Python process remained alive with no port listener. Its identity matched the Uvicorn PID 22660 printed at startup; only that test-owned PID was then stopped. Verification at 21:29:53.341 showed PID 22660 absent and port 8774 closed. Shared Ollama PID 20424 remained running. No other process or system setting was changed.

Preserved temporary evidence (not deleted):

- `%TEMP%\bioreactor_qwen_cancel_preflight_20261108_verified.json`
- `%TEMP%\bioreactor_cancel_live_job_20261108.json`
- `%TEMP%\bioreactor_cancel_live_final_20261108.json`
- `%TEMP%\bioreactor_cancel_ollama_log_slice_20261108.txt`
- `%TEMP%\bioreactor_cancel_one_20261108_212134.sqlite3`

## Conclusion

**Status: INCONCLUSIVE.** The preflight passed and one real Qwen3 8B Dashboard job ran without a CUDA initialization crash, but the job completed naturally before a cancellation was sent. No claim is made that Cancel stops live Ollama inference. The one-shot limit was honored; do not retry as part of this test. A future separately authorized run needs a genuinely live progress signal (or direct socket instrumentation) that can trigger Cancel before normal completion. Full acceptance and project readiness are not established.
