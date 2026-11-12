# Qwen3 8B: resource optimization investigation

**Status: BLOCKED for new inference; no profile is approved as the production default.** This pass was read-only apart from writing the report and profile manifest. No model load, generation, Dashboard restart, system setting change, or process termination was performed.

## Findings from the current machine

| Observation | Measured result | Meaning / limitation |
|---|---:|---|
| Ollama version / model | 0.40.15; `qwen3:8b`, Q4_K_M, 8.2B, 5.2 GB on disk | Confirmed by local CLI and `/api/show`; model digest prefix `500a1f067a9f`. |
| Dashboard at 127.0.0.1:8766 | No listener | Dashboard server is not running at the expected port, so its current RAM use is unavailable. Historical PID 3412 is not treated as current evidence. |
| Ollama server, unloaded | PID 30060, 42.0–46.9 MiB working set; about 98 MiB private bytes in a separate process snapshot | One server process only. `/api/ps` is empty. No `llama-server` process or active Ollama request. |
| Ollama desktop app | PID 21768, 3,600.2–3,600.3 MiB working set in the last preflight; 4,234.2 MiB private bytes in a later snapshot | This is the largest measured named process relevant to Ollama. It grew from about 1,611 MiB working set at 11:30 to 3,600 MiB at 11:37. This correlation does not prove a leak or explain the whole system RAM change. It was left running. |
| Available physical RAM | 4,625.1–4,646.7 MiB across three samples 10 seconds apart | Below both the 6,246.4 MiB runtime floor and the current 9,373.6 MiB provisional cold-start floor. Admission BLOCKED. |
| Commit headroom | 19,571.0–19,581.6 MiB | Not the limiting resource in this snapshot. |
| GPU at last preflight | RTX 3070 Laptop, 477/8,192 MiB VRAM used, 59 °C, utilization 9–21%, slowdown inactive | About 7.5 GiB was unallocated. The modest nonzero utilization came from desktop/system GPU clients; no Ollama runner was listed. A few Windows GPU process entries did not disclose names due permissions. |
| Ollama process duplication | One `ollama.exe`, one `ollama app.exe`, zero `llama-server` | No duplicate inference runner. The desktop app is a separate large RAM consumer. |

The current three-point record is [qwen_resource_preflight_20261110_repeat.json](qwen_resource_preflight_20261110_repeat.json). No load was attempted because free RAM was already below the runtime safety floor. The earlier 11:30 sample was also blocked and is retained at [qwen_resource_preflight_20261110.json](qwen_resource_preflight_20261110.json).

### What is known about model memory

There is no valid measurement of a **completed model load's host-RAM requirement** for the present QA profile. The failed `8192 / batch 64 / 16 GPU layers` attempt began at 7,900.2 MiB free and fell to 4,773.0 MiB before the model became ready; that 3,127.2 MiB change is an incomplete-load observation, not a model requirement.

A prior real-Qwen run provides useful but limited evidence for a different profile. With 8,166.8 MiB free before the first request, the full model appeared in `/api/ps` with `size_vram=6,194,766,806` bytes. NVIDIA telemetry reached 6,718 MiB for the first answer and 6,730 MiB for the second. The two completed turns had minimum free RAM of 7,134.0 and 6,761.4 MiB. A third turn was cancelled after free RAM reached 6,102.4 MiB and temperature reached 86 °C. Therefore, 8,166.8 MiB is a historically observed starting point for one partially successful sequence, not a certified minimum or a stable three-request threshold.

## Ollama parameters and current request path

The installed Ollama 0.40.15 source/API definition accepts `num_ctx`, `num_batch`, `num_gpu`, and `num_thread` as runner options on a generate request. `num_gpu=-1` leaves placement to llama-server auto-detection; `num_gpu=16` explicitly constrains offload to 16 layers. `num_thread=0` leaves thread selection automatic. The `keep_alive` field controls post-request residency. These semantics are confirmed in the [0.40.15 API options](https://github.com/ollama/ollama/blob/v0.40.15/docs/api.md), [0.40.15 API types](https://github.com/ollama/ollama/blob/v0.40.15/api/types.go), and [0.40.15 llama-server launch code](https://github.com/ollama/ollama/blob/v0.40.15/llm/llama_server.go).

The current QA server sets `BIOREACTOR_LLM_CONTEXT=8192` and `BIOREACTOR_LLM_GPU_LAYERS=16`. The provider maps those to `num_ctx=8192`, `num_gpu=16`, `num_batch=64`, and `num_thread=6`. In the current Ollama startup log, `OLLAMA_CONTEXT_LENGTH=0`, `OLLAMA_NUM_PARALLEL=1`, and the server calculated a VRAM-based default context of 4096. Thus the QA profile overrides the detected 4096 default with an 8192 context and forces partial GPU placement. The effective global values observed were keep-alive 5 minutes, parallelism 1, and context env 0. They were not changed.

Ollama documents that memory grows with `OLLAMA_NUM_PARALLEL × OLLAMA_CONTEXT_LENGTH`; parallelism is already 1 and should remain 1 for this experiment. Reducing context is the most defensible first memory experiment, though the impact on BioReactor's large tool prompts and multi-turn context must be evaluated. A smaller `num_batch` may reduce prompt-evaluation workspace and/or throughput; it does not remove model weights, and no local A/B measurement isolates its effect. `num_thread=6` is explicit in the current QA path; there is no evidence that changing it saves meaningful memory, so candidate profiles leave the CPU thread choice unchanged unless they explicitly use runtime auto. A five-minute keep-alive affects how long an idle model remains resident, not its peak load requirement; the QA harness can unload its own model with per-request `keep_alive=0` after a case without changing the global setting. See the [version-matched Ollama FAQ](https://github.com/ollama/ollama/blob/v0.40.15/docs/faq.mdx) and [API load/unload behavior](https://github.com/ollama/ollama/blob/v0.40.15/docs/api.md).

## Experimental profiles

The exact machine-readable settings are in [qwen_resource_profiles_20261110.json](../evaluations/qwen_resource_profiles_20261110.json). Resource numbers below are historical observations only where stated; otherwise they are **NOT MEASURED**.

| Profile | `num_ctx / num_batch / num_gpu / num_thread` | RAM / VRAM / temperature / latency | Result and status |
|---|---|---|---|
| **A — current QA baseline** | `8192 / 64 / 16 / 6` | Failed load: free RAM 7,900.2→4,773.0 MiB; VRAM up to 3,088 MiB; 58 °C. Load time and response time unavailable. | Cancelled before model-ready; no generation. Admission remains provisionally 9,373.6 MiB for this exact profile. |
| **B — memory-efficient candidate** | `4096 / 32 / 16 / 6` | NOT MEASURED | Halves context and halves batch versus A. Expected lower context allocation and prompt workspace; likely slower prompt evaluation. Keeping 16 GPU layers may leave substantial model weights in host RAM. No admission threshold below the existing conservative threshold is justified yet. |
| **C — GPU-oriented historical reference** | `8192 / 512 / -1 / auto` | First two completed turns: starts 8,166.8 and 7,114.5 MiB free; minima 7,134.0 and 6,761.4 MiB; VRAM peaks 6,718 and 6,730 MiB; temperatures 72 and 81 °C; job times 12.175 and 16.182 s; provider reported about 49.1 and 49.5 generated tokens/s. Initial request load component was about 5.0 s. | Real generations occurred, and full model size was reported in VRAM. First conceptual answer **failed** its quality rubric; explicit arithmetic answer **passed**. Third turn was cancelled at 6,102.4 MiB and reached 86 °C. This is the strongest resource evidence, but not a passing stable sequence or quality profile. |
| **D — balanced candidate** | `4096 / 128 / -1 / auto` | NOT MEASURED | Uses Ollama's locally logged 4096 context default, an intermediate batch, and automatic placement. Auto placement does not guarantee full GPU offload. Context fit, memory, latency and quality remain unknown. Keep the conservative 9,373.6 MiB admission threshold until profile-specific telemetry supports a lower value. |

For all profiles, keep `OLLAMA_NUM_PARALLEL=1`, preserve the runtime free-RAM floor of 6,246.4 MiB, cancel on unavailable telemetry or thermal slowdown, and use the local 82 °C stop. Do not use P-state as a safety gate. Do not lower admission thresholds based only on expected savings. Profile B/D cold-start thresholds are unestablished; C's historical 8,166.8 MiB is a single observed start, not an approved threshold.

## Decision and next step

No profile is approved as production default: A has no completed inference; B/D are untested; C completed only two requests, failed one scientific rubric, and did not finish the three-turn run under today's stricter runtime/thermal policy. C is the best **next experimental candidate** because it has actual full-GPU-placement and response measurements, not because it is accepted.

The present blocker is specifically free physical RAM: the latest sample is about 4.63 GiB, below the existing runtime floor. The Ollama desktop app is using roughly 3.60 GiB working set; it was not closed. The system Dashboard is absent on port 8766. No Qwen requests should be started in this state. When available RAM and other gates pass, run one short C-profile load/generation with per-second telemetry and cancellation. Only then test a single-variable context reduction (8192→4096), followed by batch changes. Record actual `ollama ps` processor placement, process private bytes, VRAM, response timing and independent scientific rubric before selecting a profile.

No RAM upgrade is justified from these data alone: Qwen3 8B has previously generated on this 8-GiB GPU, but current free RAM is constrained by other running processes. If this machine repeatedly cannot provide the measured historical start reserve without closing needed applications, a compatible 32-GiB system-RAM upgrade could create more headroom; laptop upgradeability is unknown and must be checked before purchase. A smaller locally installed Qwen2.5 1.5B occupies 1.1 GB on disk, but its scientific/tool-routing quality has not been evaluated here and it is not recommended as an equivalent replacement. No model, settings, or hardware were changed.

## Verification

- Read-only three-point preflight, 10 seconds apart: **BLOCKED** by available RAM; no backend or model started.
- Local `ollama --version`, `ollama list`, `ollama show qwen3:8b --modelfile`, `/api/show`, `/api/ps`, Windows process/listener sampling and `nvidia-smi`: completed. `/api/ps` empty; 1 Ollama server, 1 app, no llama-server; no Dashboard listener on 8766.
- No generation, browser test, or full acceptance was run in this investigation.
- The historical profile C traces are real Qwen evidence but do not replace a new profile-specific baseline or independent acceptance.

## 2026-11-10 addendum: passive Ollama app memory follow-up

The 11:37 RAM/app snapshot above is superseded as the latest observation by a six-point passive series at 11:49:12–11:50:03 +05. The same Ollama app PID 21768 had fallen from about 3,600 MiB working set to 55.8 MiB working set and 58.0 MiB private bytes; free RAM was 8,183.6–8,196.8 MiB, commit headroom 24,105.8–24,125.9 MiB, API returned HTTP 200 throughout, and `/api/ps` stayed empty. This is a transient high-memory episode, not evidence of a sustained leak or a confirmed cause. It clears the 6,246.4 MiB runtime floor in those samples but remains below the provisional 9,373.6 MiB cold-start admission threshold. No model load was attempted. See `reports/ollama_memory_consumption_investigation_20261110.md` and the raw `reports/ollama_memory_snapshots_20261110.json`.

## 2026-11-10 addendum: approved headless comparison

The standalone Ollama 0.40.15 server ran without the GUI and served its local API throughout six passive samples; no model was loaded. It used about 45 MiB working set and 95 MiB private bytes. A three-point preflight measured 8,081.8–8,098.4 MiB free RAM, below the 9,373.6 MiB cold-start gate by 1,275.2–1,291.8 MiB. GPU remained at 49 C with no hardware/software thermal slowdown. No Qwen load or generation was attempted. The headless server was stopped gracefully. Automated GUI restore did not work, but the user manually reopened Ollama afterward. The restored GUI/API now answers 0.40.15; two more passive samples show 7,054.7–7,075.2 MiB free RAM and no loaded model. This supersedes the earlier snapshots as current RAM evidence; cold-start remains blocked.

## 2026-11-10 addendum: model placement and runner options

### Current runtime versus project QA profiles

At audit time, the local daemon is Ollama 0.40.15 with GUI PID 19592 and server PID 18852. Its environment does not set `OLLAMA_CONTEXT_LENGTH`, `OLLAMA_NUM_PARALLEL`, `OLLAMA_KEEP_ALIVE`, `OLLAMA_FLASH_ATTENTION`, or `OLLAMA_KV_CACHE_TYPE`; `/api/ps` is empty. No BioReactor backend was listening on 8765/8766, so there is no live AI Chat request profile to inspect and no actual Qwen runner placement to report. The installed Qwen3 metadata reports 36 transformer blocks, Q4_K_M, 8.2B parameters, and 5.2 GB model files. Idle VRAM alone is not evidence of model placement.

The project QA code does cap offload at 16 layers in the 16-layer profile: `stage9_fault_server.py` sets `BIOREACTOR_LLM_GPU_LAYERS=16`, and `src/agent/providers.py` converts that to request option `num_gpu=16`, alongside `num_batch=64` and `num_thread=6`. Ollama 0.40.15 maps a positive `num_gpu` to `llama-server -ngl N`, so this is an explicit 16-layer cap, not an estimate based on free VRAM. Qwen3 has 36 transformer blocks, making this a partial-offload request. It must not be interpreted as exactly 16/36 of the model's bytes residing in VRAM; offload accounting, embeddings/output tensors, layer sizes, and runtime buffers affect the split. There is no running BioReactor QA backend currently applying that profile. Other preserved QA wrappers use 24, 8, or 4 layers, so the actual wrapper must be recorded for any future run.

### Supported options and evidence status

| Setting | Ollama 0.40.15 support and project use | Current effective evidence |
|---|---|---|
| `num_ctx` | Per-request runner option. Provider sends it on every offline chat. Code defaults from `BIOREACTOR_LLM_CONTEXT` or local config 4096; strict Qwen mode raises it to at least 8192 when unset. Stage 9 QA wrappers explicitly use 8192. | No AI request is active. Daemon environment is unset; earlier startup on this GPU selected 4096 as its automatic default. |
| `num_batch` | Per-request runner option. Provider sets 64 when the optional GPU-layer override is present; the historical full-auto run used 512. Smaller batch can lower prompt workspace but can reduce prompt throughput. | No runner; no local memory effect measured. |
| `num_gpu` | Per-request runner option. Positive N maps to `-ngl N`; 0 requests CPU-only; -1/automatic omits a fixed layer flag and lets llama-server fit placement. | Stage 9 fault profile caps at 16/36. No live backend sends it now. |
| `num_thread` | Per-request runner option. Provider sets 6 with the GPU-layer override; otherwise it leaves thread selection automatic. | No active request. |
| `num_parallel` | Server environment `OLLAMA_NUM_PARALLEL`; version source default is 1. This is distinct from GPU-layer count. | Environment unset, so default 1 applies; no concurrent requests observed. |
| `keep_alive` | Supported as request field and `OLLAMA_KEEP_ALIVE`; server default is 5 minutes. Provider does not set it, so default applies. A request-level zero unloads after the call. | Environment unset; no model is resident. |
| Flash Attention | `OLLAMA_FLASH_ATTENTION` is supported. When not explicitly forced on/off, v0.40.15 chooses auto if the backend reports support. | Environment unset; no runner exists to confirm the selected mode. |
| K/V cache | `OLLAMA_KV_CACHE_TYPE` is supported, server default `f16`; it is a global server choice. Quantized cache modes require Flash Attention and change numerical precision. | Environment unset; default is `f16`. No KV cache is allocated while unloaded. |
| `use_mmap` | Runner option is supported; provider does not send it. | No per-runner mapping/offload evidence. GPU offload must not be assumed to remove all host mappings or staging copies. |

Version-matched definitions: [API runner fields](https://github.com/ollama/ollama/blob/v0.40.15/api/types.go), [layer, batch, cache and thread argument mapping](https://github.com/ollama/ollama/blob/v0.40.15/llm/llama_server.go), [environment defaults](https://github.com/ollama/ollama/blob/v0.40.15/envconfig/config.go), and [FAQ for keep-alive, parallelism and KV cache](https://github.com/ollama/ollama/blob/v0.40.15/docs/faq.mdx).

### Placement and memory estimate limits

Historical profile C (`num_ctx=8192`, `num_batch=512`, auto GPU placement, automatic threads) loaded the full model in VRAM according to `/api/ps` (`size_vram=6,194,766,806` bytes); total NVIDIA usage peaked at 6,730/8,192 MiB. Two real answers completed, but temperatures reached 81 C and a third request was cancelled at 86 C. This establishes that auto placement has fit this model on this GPU before; it does not prove a safe current load, lower host RAM, or a stable accepted profile. This historical run is not the proposed 4096/32 candidate below.

From Qwen3 metadata (36 blocks, 8 KV heads, key/value width 128), the ideal unpadded FP16 K+V cache is approximately 144 KiB/token: about 576 MiB at 4096 context and 1,152 MiB at 8192. These are arithmetic estimates, not observed allocations; alignment, backend layout, attention mode, batching, other buffers and CPU/GPU split alter runtime use. The 5.2 GB on-disk weight file is likewise not the runtime RAM or VRAM requirement. Offloading more weights can reduce CPU-resident layer work, but does not guarantee lower system RAM because file mappings, staging, scheduler buffers and shared pages may remain. Only per-process and system telemetry during a successful load can establish the net effect.

### Profile comparison for a future controlled test

| Profile | Proposed runner options `num_ctx / num_batch / num_gpu / num_thread` | Expected trade-off (not a measured result) | Evidence/status |
|---|---|---|---|
| **A Current QA** | `8192 / 64 / 16 / 6` | Large context; explicitly leaves most of the 36 blocks off GPU, which may keep more layer data on host. | Exact project profile; one load was cancelled before ready when free RAM fell 7,900.2 to 4,773.0 MiB. Not a completed requirement measurement. |
| **B Compact** | `4096 / 32 / 16 / 6` | Half the context and batch of A; smaller theoretical FP16 KV and prompt workspace, but retains the same 16-layer cap. | Not measured. Keep current 9,373.6 MiB cold-start gate. |
| **C GPU-oriented** | `4096 / 32 / -1 / 6` | Differs from B only in placement. Ollama can select the layers that fit; may move more weights to VRAM and reduce CPU layer residency, but placement and host-RAM benefit are not guaranteed. | Not measured as this exact profile. Historical auto-placement at 8192/512 fully loaded the model but did not satisfy current thermal/acceptance policy. |
| **D Conservative short query** | `4096 / 16 / -1 / 6` | Lower context-workspace pressure than B/C. Intended only for one short, non-multiturn, non-tool scientific answer; may not fit the full BioReactor system prompt or tool schema. | Not measured. No admission threshold established. |

### Admission and recommended experiment

Latest free physical RAM after GUI recovery was 7,054.7–7,075.2 MiB, below the preserved 9,373.6 MiB cold-start gate by about 2,298–2,319 MiB. It is above the 6,246.4 MiB runtime floor, but that is not sufficient to start a cold model. Do not run any profile now and do not reduce either gate based on the profile arithmetic.

When a fresh three-point preflight (10 seconds apart) meets the existing admission gate and thermal telemetry is healthy, use an isolated, sequential direct Ollama API test with no parallel requests to isolate placement. The current BioReactor provider cannot express these exact B/C values through its environment wrapper: it rejects negative `BIOREACTOR_LLM_GPU_LAYERS` and hardcodes batch 64 whenever that override is set. A test-only request harness can send the supported `options` directly without changing the app: first compare B and C sequentially, holding `num_ctx=4096`, `num_batch=32`, and `num_thread=6` constant while changing only `num_gpu` from 16 to -1. This would validate placement/memory, not the full AI Chat path. Record host free RAM/commit and Ollama process private bytes during load, model-ready status, `ollama ps` processor split and `size_vram`, GPU used VRAM/temperature/thermal slowdown, then one short answer and unload. Stop if telemetry disappears, free RAM reaches the runtime floor, a runner/CUDA error occurs, or temperature reaches the existing 82 C stop. A successful load still needs independent answer-quality review. Only after B/C can be compared should D's batch 16 be tested. No settings were changed, no Qwen inference was run, and no profile is approved as safe or production-ready.

## 2026-11-10 controlled GPU offload A/B experiment

### Test definition

The isolated harness is `evaluations/qwen_offload_ab_harness.py`; its static run manifest is `evaluations/qwen_offload_ab_profiles_20261110.json`. It sends one identical scientific prompt serially with explicit per-request parameters:

| Profile | num_ctx | num_batch | num_gpu | num_thread | Execution status |
|---|---:|---:|---:|---:|---|
| A | 4096 | 32 | 16 | 6 | Not loaded; admission blocked |
| B | 4096 | 32 | -1 | 6 | Not loaded; admission blocked |

For Ollama 0.40.15, positive `num_gpu` maps to a fixed `-ngl N`; `num_gpu=-1` omits that fixed layer count so `llama-server` can auto-select offload. It does not guarantee full GPU placement. This follows the tagged [v0.40.15 runner mapping](https://github.com/ollama/ollama/blob/v0.40.15/llm/llama_server.go).

The harness is separate from the BioReactor provider and Dashboard. It records the exact request options, UTF-8 prompt hash, Ollama log deltas, periodic system/process telemetry, `/api/ps` placement data, and pre/post-unload samples. Load/unload use the v0.40.15 `/api/generate` empty-prompt path; model-answer collection uses streaming `/api/chat`. Cancellation closes only this harness-owned HTTP socket, records request/closure timestamps, and has no force-thread termination. If the request worker does not stop, it marks cancellation unconfirmed and does not begin the next profile. Version-matched empty-prompt behavior is visible in the [v0.40.15 route source](https://github.com/ollama/ollama/blob/v0.40.15/server/routes.go).

### Latest three-point admission preflight

Read-only preflight ran 2026-11-10 15:31:56?15:32:16 +05, 10 seconds between points. Raw measurements are in `reports/qwen_offload_preflight_20261110_controlled_ab_final.json`.

| Sample | Free physical RAM MiB | Commit headroom MiB | GPU temp | VRAM used MiB | GPU utilization |
|---|---:|---:|---:|---:|---:|
| 1 | 7489.2 | 22975.5 | 60 C | 230 / 8192 | 11% |
| 2 | 7555.4 | 23039.9 | 60 C | 230 / 8192 | 10% |
| 3 | 7543.0 | 23045.3 | 60 C | 224 / 8192 | 10% |

Ollama 0.40.15 API returned HTTP 200 at each point; `/api/ps` was empty. Thermal slowdown telemetry was `Not Active` at all points. The existing cold-start gate remains 9373.6 MiB, so the three points were short by 1884.4, 1818.2, and 1830.6 MiB. Preflight is **BLOCKED**. The runtime floor of 6246.4 MiB is not a substitute for cold-start admission, and neither threshold was changed.

### Results and disposition

No model load or inference was attempted. Therefore profile A/B RAM or VRAM use, actual layer placement, load/generation time, unload release, cancellation response, and answer quality are all **NOT MEASURED**. No Ollama profile log delta exists because the harness did not submit a model request. The process/API and empty model list were only observed passively. No production provider, Dashboard, Ollama setting, driver, or system setting was changed. Project status remains **NOT READY**.

The prepared next action is a new three-point preflight immediately before execution. Only if every point meets the existing cold-start gate and thermal/telemetry checks should profile A run, unload be confirmed and resources rechecked, then a fresh three-point preflight precede profile B. If the gate still fails, leave both profiles unrun; do not lower the gate based on the available idle VRAM or commit headroom.

### Harness validation

- `python -X utf8 -m py_compile evaluations/qwen_offload_ab_harness.py` ? PASS.
- `check_unicode()` compared UTF-8 JSON request-body round-trips; exact prompt hash `da7e0d769adfae99d94151f9186d346f10bddda00e95ccad99e901515d46f99f`; multilingual/unit probe hash `952b2ed45d68c0ac2efcc4a29ef1ec83801ab7242e7a456e4a26b9ee3f135611` ? PASS.
- `python -X utf8 evaluations/qwen_offload_ab_harness.py --help` ? PASS.
- The harness's guarded `compare` command was intentionally **NOT RUN**, because the fresh preflight failed admission.


Offline cancellation smoke check: **PASS**. A stub HTTP response blocked in streaming read; calling `StreamJob.cancel()` closed the fake response/socket, the worker exited, and request/connection-close timestamps were recorded. This validates the harness cancellation path only; it is not a live Ollama cancellation test. No Ollama inference was submitted.

## 2026-11-10 decision: do not repeat the same blocked run

### Decision

**INSUFFICIENT_EVIDENCE** ? the profile-only admission gate is closed. No Qwen load was attempted. The current state does not support a safe load-only test of profile B.

The previous three-point preflight (15:31:56?15:32:16 +05) is still the latest three-point admission check: free RAM was 7,489.2?7,555.4 MiB, all below the unchanged 9,373.6 MiB cold-start gate. A later single passive sample at 15:41:52 +05 showed free RAM 6,374.5 MiB, commit headroom 21,681.2 MiB, temperature 61 C, VRAM 332/8,192 MiB, utilization 10%, no thermal slowdown, Ollama 0.40.15 responding, and `/api/ps` empty. That one sample is only 128.1 MiB above the 6,246.4 MiB runtime floor and is not an admission pass. No profile was loaded.

Profile B (`4096 / 32 / -1 / 6`) may use less KV-cache and prompt workspace than A, and automatic GPU placement may reduce host-resident layer work. Neither effect gives a measured upper bound for its physical RAM or commit increase. The previous 3,127.2 MiB RAM drop (7,900.2 to 4,773.0 MiB) came from an incomplete load of a different profile; it is not a completed peak or an upper bound. A different historical full-auto run completed answers but reached 6,102.4 MiB free RAM and 86 C on a later turn. It is not evidence that this profile or a load-only test is safe. The previous live cancellation audit also observed Qwen continue generating after Cancel until natural completion; HTTP close is not treated as an instantaneous safety guarantee. The offline fake-transport smoke test validates only that the harness closes its own socket.

### Separate profiling admission rule

Production remains on its existing gates: cold-start 9,373.6 MiB and runtime floor 6,246.4 MiB. No values were relaxed. For a profiling-only B load, use a distinct, fail-closed condition:

`minimum 3-point free RAM >= runtime floor + validated upper bound of B's peak physical-RAM increase + abort/cancellation margin`

Also require:

- commit headroom to cover a validated upper bound of B's peak commit increase plus margin;
- available VRAM to cover B's measured or conservatively bounded peak, with a reserve for desktop usage;
- GPU telemetry available, temperature below the existing project stop at 82 C, and both thermal slowdown flags inactive;
- Ollama 0.40.15 healthy, `/api/ps` empty before load, and no competing inference;
- during load, sample telemetry continuously; stop at the runtime floor, missing telemetry, thermal slowdown, temperature stop, runner/CUDA error, or if the request worker does not close after cancellation. Do not count Cancel as protective until actual Ollama load cancellation latency is established.

The project runtime floor is retained as the minimum remaining free-RAM reserve; it is not an independently certified Windows OS minimum. The profile-B peak RAM/commit bounds and real Ollama load-cancellation bound are currently **unknown**, so this rule has no defensible numeric threshold yet. The current 15:41 snapshot fails even the reserve-only part by 128.1 MiB. Reaching 9,373.6 MiB is a necessary return to the existing cold-start admission condition, not sufficient proof for profile B until its peak/cancellation terms are bounded.

### Manual RAM release options

At 15:41:52 +05, these application groups were observed (working set is resident memory; Private bytes are committed private memory and do not equal immediately reclaimable RAM):

| App group | Processes | Working set MiB | Private bytes MiB | Safe user action, if applicable |
|---|---:|---:|---:|---|
| Perplexity Comet browser | 18 | 2,055.6 | 1,380.0 | Close unneeded windows/tabs through the app only if it is not hosting the current work and tabs are saved. |
| Microsoft VS Code | 13 | 2,262.9 | 2,506.0 | Save work first; close unused VS Code windows/workspaces only. Do not close the active BioReactor workspace if it contains ongoing work. |
| NVIDIA Overlay | 5 | 323.1 | 354.7 | Quit the overlay normally if unused; do not change driver or cooling settings. |
| Microsoft Edge | 5 | 291.3 | 144.9 | Close unneeded tabs/windows normally. |
| OneDrive | 1 | 181.8 | 158.7 | Exit only after confirming sync is complete. |
| Phone Link | 1 | 162.6 | 89.3 | Close normally if not in use. |
| WhatsApp Desktop | 1 | 156.9 | 87.0 | Close normally if not in use. |
| Windows Settings | 1 | 175.9 | 128.4 | Close the Settings window if no change is in progress. |

Comet and VS Code are the largest user-controlled groups. These totals include multiple browser/renderer or editor processes; working-set and private-byte totals must not be summed as guaranteed memory savings. I did not close any process. Do not close Memory Compression, Windows Defender, Explorer, Ollama, or system processes. At the latest single snapshot, reaching the existing cold-start gate would require about 2,999 MiB more available RAM; closing Comet alone is unlikely to provide that amount. After any manual changes, take fresh passive measurements rather than assuming a particular release amount.

### Practical next step

1. If comfortable, manually close Comet windows/tabs that are not needed for this session, then unused VS Code windows only after saving, followed by idle Edge/WhatsApp/Phone Link; wait for OneDrive sync before considering it.
2. Check available RAM and commit headroom again. A three-point series at least 10 seconds apart must reach the unchanged cold-start gate before even considering a model load.
3. Do not launch B just because the generic gate passes. First establish a conservative B-specific RAM/commit peak and the time from Cancel to actual runner/load stop, or perform the profiling on a machine with enough measured reserve to tolerate the full plausible load without relying on cancellation.
4. Once those conditions are met, the minimal test is profile B only: load with explicit `4096 / 32 / -1 / 6`, no generation, record `/api/ps` placement and resource peak, request unload, verify `/api/ps` empty, then compare resource recovery. Keep production provider/Dashboard untouched. The current `compare` mode runs A and B plus generations, so do not use it for that minimal load-only step without a future narrow extension to the same harness.

### Alternatives if the laptop cannot provide repeatable margin

| Option | Advantage | Limitation / scientific effect |
|---|---|---|
| Upgrade host RAM to 32 GB, if this exact laptop supports it | More physical headroom for model mappings, runner buffers, OS and development tools while keeping Qwen3 8B. | Laptop model/SKU and upgradeability are unknown; check the manufacturer specification before buying. It does not add VRAM or resolve CUDA/thermal issues, and still needs measured acceptance. |
| Use a smaller local model | The already installed `qwen2.5:1.5b` occupies 1.1 GB on disk. Ollama lists `qwen3:4b` at 2.5 GB on disk as another candidate. | On-disk size is not peak RAM. Smaller models may reduce reasoning and tool-routing reliability; they must be independently evaluated and cannot certify Qwen3 8B quality. [Ollama Qwen3 model list](https://ollama.com/library/qwen3). |
| Separate compute machine | Keep the current laptop for the Dashboard and run the same Qwen model on a host with a measured memory/VRAM reserve. | Additional hardware/network setup and operating cost; remote access and data handling require explicit configuration. The agent still needs the same scientific evaluation. |
| Hybrid: local deterministic science + external LLM for language | BMP/economic calculations and physical constraints can remain locally validated while the LLM handles explanation and dialogue. | Needs internet and a paid/external service may incur cost; user data leaves the laptop. Deterministic tools remain authoritative; LLM prose is not evidence. |

No model was pulled, no application was closed, and no system setting was changed. Project remains **NOT READY**. The current passive snapshot and decision are also recorded in `evaluations/qwen_offload_ab_profiles_20261110.json`.

