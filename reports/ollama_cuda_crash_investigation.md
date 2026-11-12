# Ollama CUDA runner crash investigation

**Date:** 2026-11-08 (Asia/Qyzylorda, UTC+05:00)  
**Status:** underlying cause **NOT CONFIRMED**. The best-supported contributing mechanism is host-memory pressure followed by a pinned-host-memory fallback during partial GPU offload. The native dump has not been analyzed. No inference, application test, driver change, Ollama change, or system-setting change was made in this investigation.

## Scope and repository state

- Branch `main`, starting commit `38efb3a`.
- The worktree was already extensively dirty before this report was added: existing deletions under `.deps`, application changes, untracked tests, and prior audit artifacts were present. I did not revert or edit those files. This report is the only file added for this investigation.
- No GPU inference was run. No tests were run. This was a read-only system/log/source inspection.

## Incident timeline

All timestamps below are local time, UTC+05:00.

| Time | Evidence |
|---|---|
| 19:13:11 | Ollama server started. Its logged config has `OLLAMA_NUM_PARALLEL=1`, `OLLAMA_VULKAN=true`, and no selected `OLLAMA_LLM_LIBRARY`. |
| 19:13:15 | Ollama selected `library=CUDA`, compute capability `8.6`, `libdirs=ollama,cuda_v13`, RTX 3070 Laptop GPU, 8.0 GiB total and 6.9 GiB available. |
| 19:17:27–19:17:32 | Qwen3 8B runner loaded successfully with the same 8192 context, `-np 1`, `-ngl 16`, batch 64, and CUDA backend. At load, Ollama logged 6.1 GiB system RAM free and 20.5 GiB free swap. Its 2,740.15 MiB host model buffer was `CUDA_Host`. The runner reported `model loaded`; subsequent `/api/chat` calls returned HTTP 200. |
| 19:38:49.989 | A new runner for the same model and options started on port 61371. Ollama logged 2.2 GiB system RAM free and 3.2 GiB free swap; GPU memory remained 6.9 GiB free. |
| 19:38:56–19:38:57 | During empty model warmup, CUDA reported `shared object initialization failed` in `ggml_cuda_kernel_can_use_pdl` at `cudaFuncGetAttributes(&attr, kernel)`. Windows Application Error 1000 recorded the crash at 19:38:57. |
| 19:39:07–19:39:08 | WER recorded Event 1001; Ollama reported runner exit `0xc0000409`, failed model load, and returned HTTP 500 for `/api/chat` after 19.35 seconds. The runner had not reached a ready state or user-token generation. |

The strongest local comparison is the host buffer line: the successful load used `CUDA_Host model buffer size = 2740.15 MiB`; the failed load used `CPU model buffer size = 2740.15 MiB`. GPU model/KV/compute allocations were approximately 2,237/480/54 MiB in both logs. This matches a host-memory/pinned-allocation fallback pattern, but the Ollama log does not explicitly say that pinned allocation failed, so this is not proof of the underlying cause.

## Environment findings

### Versions and package

- `ollama --version` and `GET /api/version`: **0.40.15**.
- NVIDIA driver: **581.80**. `nvidia-smi` reports CUDA compatibility version **13.0**; Ollama selected its bundled `cuda_v13` backend. This does not establish which CUDA DLLs were actually mapped into the crashed process.
- GPU: NVIDIA GeForce RTX 3070 Laptop GPU, 8,192 MiB, compute capability 8.6.
- The crash event identifies `ucrtbase.dll` version `10.0.26100.9711`; the user identifies the OS as Windows 11. WMI OS details could not be read under this account.
- Ollama CLI and `llama-server.exe` have valid Authenticode signatures from Ollama Inc. The runner and CLI file timestamps are 2026-11-06 01:20. This verifies those executable signatures, not the integrity/version match of every bundled dependency.
- The Ollama installation contains a `cuda_v13` directory and CUDA runtime/library files. The crash dump’s loaded-module list was not available, so actual DLL paths and any DLL search-order conflict remain unverified.
- In the current shell, `CUDA_PATH` and `CUDA_HOME` are unset and its PATH has no standalone CUDA Toolkit entry. This is not a reconstruction of the Ollama process environment at crash time.

Ollama’s hardware table lists RTX 3070/compute capability 8.6 as supported and its NVIDIA guidance states driver 550 or newer. NVIDIA’s CUDA 13 compatibility table states a minimum driver of 580 for CUDA 13.x. Driver 581.80 satisfies those published minimums. This makes an unsupported GPU or obviously-too-old driver an unlikely explanation; it does not exclude a driver defect. [Ollama GPU support](https://github.com/ollama/ollama/blob/main/docs/gpu.mdx), [NVIDIA CUDA 13.0 release notes](https://docs.nvidia.com/cuda/archive/13.0.0/cuda-toolkit-release-notes/)

### GPU and host resources

At 20:17:02, after the incident and without model inference:

- RTX 3070 Laptop GPU: 70 °C, 32% utilization, 783/8,192 MiB VRAM, 19 W, P8.
- Thermal slowdown was `Not Active`; reported slowdown and shutdown temperatures were 98 °C and 101 °C. The earlier pre-test sample recorded in the prior audit was 67–68 °C with no active thermal slowdown. There is no temperature/utilization sample at the exact crash second, so thermal conditions at that instant are not fully reconstructed.
- `nvidia-smi` listed Windows shell, search, phone integration, and NVIDIA overlay graphics processes; it listed no Ollama CUDA process. The source of the measured GPU utilization is not attributed from this list. `/api/ps` was empty and the only Ollama process observed was the main `ollama.exe` PID 20424. The runner was no longer present.
- At 20:16–20:17, Windows memory counters reported only 597–834 MiB available RAM. At the 20:16 sample, committed memory was about 61.98 GiB of a 63.07 GiB limit. This is current pressure, not a measurement of the exact crash-time commit state. No applications were stopped.

The 2.2 GiB RAM free at the failed load is below the 2.74 GiB host model buffer that had succeeded as `CUDA_Host` when 6.1 GiB was free. This makes host-memory pressure a strong candidate. The data do not establish a universal safe threshold, and current low RAM/commit headroom means another model start should not be attempted now.

## Windows crash records and dump

- Application Error, Event ID 1000, at **2026-11-08 19:38:57**: `llama-server.exe`, PID `0x729C` (29340), faulting module `C:\Windows\System32\ucrtbase.dll`, exception `0xc0000409`, offset `0xA527E`.
- Windows Error Reporting, Event ID 1001: event name `BEX64`, P8 `c0000409`, P9 `0000000000000007`, report ID `58482db2-85c8-41a4-827f-13f448b0d462`.
- `0xc0000409` is a fail-fast exception. Microsoft documents that exception parameter 0 is a subcode and that the value is application/scenario-specific; the exception code alone does **not** prove a stack-buffer overrun. The WER event records subcode value 7, but without the exception record and dump analysis I am not assigning a more specific meaning to it. [Microsoft: Fail Fast Exception C0000409](https://learn.microsoft.com/en-us/shows/inside/c0000409)
- A local dump exists at `%LOCALAPPDATA%\CrashDumps\llama-server.exe.29340.dmp`, size 239,832,355 bytes. No `cdb.exe`, WinDbg, or `dumpchk.exe` was found. Reading the WER ReportArchive directory was denied. Therefore exception details, stack, and loaded DLL list remain **BLOCKED**. The dump was not modified or moved.
- The Application log contains the crash records above. The System log query around 19:34–19:44 found no matching level 1–3 events. No contemporaneous NVIDIA driver reset or WHEA event was found in that query.

## Confirmed facts, likely causes, and hypotheses

### Confirmed

1. The failing component was Ollama’s native `llama-server.exe`, not the Python HTTP provider process.
2. The immediate CUDA failure was during model warmup, in the PDL capability probe `ggml_cuda_kernel_can_use_pdl` → `cudaFuncGetAttributes`; the runner then failed fast with `0xc0000409`.
3. The same Ollama daemon, model, and launch options had successfully loaded Qwen earlier that evening. The successful and failed runs differ in logged free host memory and the placement label for an identically sized host model buffer (`CUDA_Host` versus `CPU`).
4. The crash request was not cancelled. It failed during runner initialization before a completed model response. No evidence links the socket-cancellation path to this native CUDA failure.
5. Ollama configured one parallel sequence (`OLLAMA_NUM_PARALLEL=1`) and the incident log shows one runner start for the failed load. Multiple simultaneous Ollama runners are not supported by the evidence; an unlogged process in another account/session cannot be excluded with certainty.

### Most plausible mechanism, still unconfirmed

Host RAM/commit pressure may have prevented or changed a pinned host-memory allocation during partial GPU offload. A public Ollama issue reports a closely matching Windows `cuda_v13` warmup failure, including the same `cudaFuncGetAttributes` PDL probe on a supported RTX 3060 Ti, correlated with a plain `CPU` host buffer and host-memory pressure. That is independent anecdotal evidence, not a diagnosis of this machine. The report itself has mixed observations around possible workarounds, so I do not recommend copying its environment-variable experiments. [Related Ollama issue #17380](https://github.com/ollama/ollama/issues/17380)

### Not established or not supported

- **Not established:** that host-memory/pinned-memory fallback is the root cause; exact allocation failure, exception stack, and loaded CUDA DLLs are missing.
- **Not established:** a CUDA driver bug, Ollama 0.40.15 regression, or a mismatch/corruption among bundled CUDA DLLs.
- **Ollama update:** the executable timestamp predates the incident, and the same running daemon successfully loaded Qwen at 19:17 before failing at 19:38. This argues against an update immediately before the failure. It does not rule out a version-specific defect introduced in an earlier installation; no controlled version comparison was performed.
- **Driver update:** no driver-install event or driver reset was found around the incident, but driver change history was not available. The current driver meets the documented CUDA 13 minimum.
- **HTTP provider change:** the application request reached Ollama and triggered a cold runner start. The provider could determine when a request is made, but no cancellation occurred and the failure is logged inside native CUDA warmup. There is no evidence that the HTTP implementation caused the CUDA error.
- **VRAM exhaustion:** not supported by Ollama’s 6.9 GiB free estimate and the logged approximately 2.77 GiB model+KV+compute CUDA allocation. This does not rule out a CUDA runtime/module issue.
- **Thermal shutdown/slowdown:** not indicated by nearby measurements or current thermal flags. Exact crash-time GPU telemetry is missing.
- **Unsupported GPU / driver below documented minimum:** not supported; the architecture and current driver meet the cited support requirements.
- **Vulkan conflict:** server config logged `OLLAMA_VULKAN=true`, but the selected inference backend was CUDA `cuda_v13`; no evidence ties Vulkan to this crash.

## Static review of cancellation and result delivery

Read-only review covered `src/dashboard/jobs.py`, `src/dashboard/job_api.py`, `src/dashboard/api.py`, `src/agent/cancellation.py`, `src/agent/providers.py`, and existing cancellation tests. Tests were not executed in this investigation.

| Concern | Static finding |
|---|---|
| Transport | The provider uses Python stdlib `http.client.HTTPConnection` / `HTTPSConnection`; it creates a new connection for each request and has no shared connection pool. |
| Timeout | Provider default is 45 seconds; `BIOREACTOR_LLM_REQUEST_TIMEOUT` can set 1–600 seconds. The timeout is passed to the socket connection; this is not a strict total wall-clock deadline. JobRuntime has a separate deadline/cancel signal. |
| Cancellation propagation | `Control` owns a per-job `CancellationSignal`; the dashboard binds it to `HybridLLM` and the agent; the provider checks it before the request and while reading. |
| Closing active I/O | The registered callback calls `shutdown(SHUT_RDWR)`, closes the socket, and closes the connection. The `finally` path closes the response and connection. Stream parsing only returns after a terminal `done=true` record; cancellation/short stream does not return partial content. Non-2xx responses such as the observed HTTP 500 become provider errors. |
| Cancellation gaps | The callback is registered **after** `connection.connect()`, so cancellation during connect cannot close that socket. `connection.request()` holds the same lock used by the cancellation callback, so a blocked send can delay cancellation until the lock is released. Loopback connect/send are normally short, but this path is not proven to have zero cancellation latency. |
| Late commit / isolation | The job execution checks cancellation/ownership after execution, and the dashboard persistence transaction rechecks terminal state, cancel flag, owner, deadline, and shutdown before writing the answer. Each job has a separate signal and each HTTP call has its own connection. Existing tests cover socket cancellation, streaming, timeout, parallel independent signals, ownership/deadline fences, and late-result prevention; these were inspected, not run here. |

Static files: [providers.py](../src/agent/providers.py), [cancellation.py](../src/agent/cancellation.py), [jobs.py](../src/dashboard/jobs.py), [api.py](../src/dashboard/api.py), [test_provider_cancellation.py](../tests/test_provider_cancellation.py).

The CUDA crash does not prove or disprove the provider cancellation implementation. The prior [GPU gate/cancellation audit](gpu_gate_cancellation_audit.md) remains **PARTIALLY FIXED** for the live cancellation criterion; this diagnostic did not re-run the live test.

## Checks and outcomes

| Check | Command/method | Result |
|---|---|---|
| Current GPU / driver / temperature / processes | `nvidia-smi`, `nvidia-smi --query-gpu=...`, `nvidia-smi -q -d PERFORMANCE,TEMPERATURE` | **PASSED** for telemetry. No Ollama runner now; only Windows graphics processes were listed, and the source of current utilization is not attributed. Current RAM pressure makes inference unsuitable. |
| Ollama version and service status | `ollama --version`; `GET /api/version`; `GET /api/ps` | **PASSED**. Version 0.40.15, API responsive, model list empty. |
| CUDA/backend selection | `%LOCALAPPDATA%\Ollama\server.log` | **PASSED**. CUDA compute 8.6, `cuda_v13` selected. |
| Application/WER events | `Get-WinEvent` Application log, Event IDs 1000/1001, 19:35–19:45 | **PASSED**. Crash records and subcode present. |
| Native crash dump analysis | `Get-Command cdb.exe,windbg.exe,dumpchk.exe`; inspect dump | **BLOCKED**. Debugger tools absent; WER archive access denied. Dump exists but is not decoded. |
| System log around crash | `Get-WinEvent` System log, 19:34–19:44, levels 1–3 | **PASSED** as a query; no matching events. This cannot establish absence of all driver-side diagnostics elsewhere. |
| Binary signature/hash | `Get-AuthenticodeSignature`; `Get-FileHash -Algorithm SHA256` | **PASSED** for executable signatures. Does not validate all bundled DLLs against an official manifest. |
| Provider/cancellation | Static source inspection | **PARTIAL**. Socket closure and commit fences exist; connect/send timing gaps remain. No tests run in this diagnostic. |
| Qwen inference / controlled replay | Not run | **SKIPPED** deliberately. No repeated launches after the crash; current available RAM 597 MiB and commit headroom about 1.1 GiB, while the prior host model buffer was 2.74 GiB. GPU utilization was 32% in the 20:17 sample. |

## Safe next steps

1. Do not launch Qwen under the current observed memory pressure. Do not stop applications automatically.
2. Preserve the existing dump and server/WER logs. If an already-installed WinDbg becomes available or the owner authorizes access to the protected WER archive, inspect `.exr -1`, `!analyze -v`, and the loaded-module list. This is the shortest path to the exception subcode/stack and actual DLL evidence; do not install tools as part of this report.
3. Before any live retry, wait for available host RAM/commit headroom to recover beyond the previous model’s logged host-buffer demand and for GPU telemetry to be idle/stable with no active thermal slowdown. This is a case-specific guard based on the observed 2.74 GiB allocation, not a universal RAM or temperature threshold.
4. If the owner later authorizes one test, perform only one cold Qwen start with existing model/context/backend settings unchanged. Record Ollama memory-buffer placement, host memory/commit, `nvidia-smi`, and runner logs. Stop after a recurrence; do not retry repeatedly.
5. Do not change driver, Ollama, BIOS, cooling, persistent environment variables, model, quantization, or context yet. In particular, do not apply `CUDA_MODULE_LOADING=EAGER` as a generic fix: external reports are inconsistent and one report describes a discovery hang.
6. If a single controlled attempt fails again, compare the CUDA_Host/CPU host-buffer line and dump before considering a reversible one-variable workaround. No root-cause fix should be claimed until this evidence is captured.

## Conclusion

The **immediate failure site** is confirmed: CUDA module/function introspection in the `cuda_v13` llama.cpp runner during Qwen warmup, followed by a Windows fail-fast exit. The **underlying cause is not confirmed**. The local before/after buffer placement and free-memory comparison strongly support host-memory/pinned-allocation pressure as a contributing mechanism, but only decoded dump/module evidence or a carefully controlled comparison can raise this beyond a hypothesis.

No inference or configuration change was made. A short controlled test is **not recommended now** because available host RAM is currently below 1 GiB and Windows commit is close to its limit. Reassess only after resource conditions recover; if another attempt reproduces the same crash, stop and analyze the dump rather than retrying.
