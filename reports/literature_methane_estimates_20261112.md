# Scientific estimates with incomplete inputs — 2026-11-12

Implementation and one controlled real-agent retest completed; overall FIRO status NOT READY. Base main / 38efb3aee0b4dbea3a5feac92e90e3a0e2a7d640. Pre-existing user edits are preserved. Production model selection, resource policy and port 8766 are unchanged. Earlier checkpoints below are retained as history.

## Evidence and implementation

The shared advisor mass/TS/VS/BMP engine now supports an explicit opt-in literature density transfer from the **same matched study profile**, never an arbitrary density or a conversion of confirmed dialogue facts. Existing strict density defaults remain unchanged. The existing agent registry exposes `estimate_methane_yield`, wrapping that same engine; volumetric methane requests require scientific retrieval and this tool. Advisor API `/api/advisor/estimate`, async Dashboard Chat jobs, and experimental FIRO scenario B use it. Mode and source information persist in the existing history.

Three reported modes distinguish calculations with measured inputs (outputs still CALCULATED), named literature scenarios, and insufficient evidence. A separately supplied first-order fit can calculate timed yield only with measured batch properties, explicit rate/lag, matching temperature, applicability confirmation and a reference. No default kinetic coefficient is provided. No fitting/training is performed. The current catalog provides no matched kinetic fit for the original 30-day request.

Primary source checked online: [Oliveira et al., published online 2025, journal issue 2026](https://link.springer.com/article/10.1007/s43153-025-00592-x). The existing reviewed RM1 profile preserves density 1.013 kg/L, TS 12.69–13.91% wet mass, VS 10.16–11.44% wet mass, and coarse graph-read BMP bracket 200–250 mL CH4/g VS. The experiment used untreated refrigerated slurry at 37 °C for 27 days, gas 273.2 K / 1.01325 bar; gas moisture basis is incomplete. These are **conditional sensitivity inputs**, not a population confidence interval or the user's measured composition. Solid/bedded/stored material cannot silently borrow this density. The figure bracket was already manually reviewed in the project; this session rechecked the primary article's methods, not a new precision digitization of the figure.

Other studies inspected do not supply a complete transferable 30-day slurry profile: [Baek et al. 2020](https://pmc.ncbi.nlm.nih.gov/articles/PMC7370025/) concerns sawdust-bedded cattle manure without a usable density; [Wang et al. 2019](https://www.mdpi.com/2076-3417/9/13/2703) shows density depends on solids and bedding. Those values are not pooled into the RM1 estimate. A laboratory assay's endpoint is not an extrapolation to a full-scale reactor's 30-day yield.

142 L × 1.013 kg/L = 143.846 kg (conditional), VS 14.6147536–16.4559824 kg; existing Python engine gives 2922.95072–4113.9956 L CH4 as a source-BMP reference for the whole batch. The 30-day reactor yield remains unavailable. The UI displays both explicitly, rather than claiming this is a 30-day forecast.

## Verification so far

`python -X utf8 -m pytest tests/test_literature_methane_estimates.py tests/test_firo_demo_mvp.py tests/test_density_scope_regression.py tests/test_numeric_claim_origins.py tests/test_stage9_runtime.py tests/test_stage9_verification.py -q -p no:cacheprovider --basetemp=.pytest-lit-estimate2-20261112` — PASSED 98. First run: 96 passed / 2 failed (overstrict float equality in new test; expected batch geometry status while operating mode was unknown). Existing geometry correctly leaves unknown operating mode for review; the new estimate projection now also calls the existing volume-only simultaneous-loading check. This preserves impossible single-charge warnings without assuming batch versus continuous operation.

Next: expanded actual Chat endpoint regression, frontend tests/build and Chrome restoration check; then fresh unchanged QA resource preflight and one real Qwen3 4B test if admitted. Real-Qwen / browser checks for this change NOT RUN at this checkpoint.

## Completed deterministic and browser checks

Final backend command (not a full-project acceptance run):

```powershell
python -X utf8 -m pytest tests/test_literature_methane_estimates.py tests/test_firo_demo_mvp.py tests/test_stage9_runtime.py tests/test_stage9_verification.py tests/test_scientific_question_routing.py tests/test_numeric_claim_origins.py tests/test_density_scope_regression.py tests/test_substrate_advisor.py tests/test_scientific_provenance.py tests/test_reactor_capacity_validation.py tests/test_reactor_capacity_dashboard.py tests/test_analytical_response.py tests/test_qwen4b_manual_chat.py tests/test_stage9_jobs.py -q -p no:cacheprovider --basetemp=.pytest-lit-final2-20261112
```

**PASSED 243**, one existing Starlette/httpx deprecation warning. This includes deliberate source-coefficient tampering, independent wet-mass/TS/VS basis checks, unsupported timed forecasts, measured-input calculations, density transfer opt-in, compatible units, unsuitable physical forms, working capacity and actual Chat endpoint persistence. Synthetic kinetic-fit tests are explicitly labeled TEST, not measurements or published coefficients.

From `frontend`: `npm.cmd test -- --configLoader runner` — **80 passed**; `npm.cmd run build` — **PASSED**. No tests were counted as passed through exclusions.

```powershell
$env:BIOREACTOR_DEMO_OUT='../reports/literature_estimates_20261112/final_browser'
node tests/firo-demo-mvp-browser.mjs
```

**PASSED 14 Chrome checks** on actual network endpoints at port 8770: all three scenarios, the new literature mode/potential/unknown timed yield, reload restoration, mobile overflow and browser JS errors. Screenshots: [scenario B](literature_estimates_20261112/final_browser/offline_B.png). The real 4B Chat response below was tested via FastAPI TestClient, **not** a new browser inference test. A genuine record created before backend restart retained its exact estimate, answer and sources afterward: [restart evidence](literature_estimates_20261112/restart_restore.json).

Environment: Windows 11 build 26200, Python 3.13.13 x64, FastAPI 0.141.1, Pydantic 2.13.5, httpx 0.28.1, pytest 8.4.2, psutil 7.2.2. Ollama API reports 0.40.16, GPU RTX 3070 Laptop 8192 MiB. Qwen3 4B uses the existing QA profile: context 4096, batch 32, automatic GPU layer selection (`num_gpu=-1`), one serial request, keep_alive 5m between stages, max four calls / 120 s per scenario. No Qwen3 8B launch or parameter change.

## Resource chronology and real Qwen results

Initial three-point preflight (10 s spacing) **BLOCKED**: RAM 6400.3 / 6450.1 / 6449.1 MiB versus unchanged admission 6656 MiB; missing 205.9–255.7 MiB. GPU 56 °C, VRAM 629–635 MiB used, commit headroom 23260–23316.5 MiB, no thermal slowdown or other loaded model. This block was obeyed. [Measurements](literature_estimates_20261112/preflight.json).

After the user explicitly freed RAM, the existing QA client was run sequentially, with its own fresh safety check on each invocation:

```powershell
python -X utf8 evaluations/qwen4b_manual_chat.py --confirm-experimental --limited-chat --case C
```

| Component | First run | Corrected retest |
|---|---|---|
| Trace | `qwen4b_manual_qa/limited_chat_1794465748772069400.json` | `qwen4b_manual_qa/limited_chat_1794466093623215700.json` |
| Admission free RAM | 6709.7 MiB | 8357.6 MiB |
| Real model calls | 4 | 4 |
| NLU | Valid, grounded material span | Valid, grounded material span |
| Source and calculation tool selection | Both selected by Qwen | Both selected by Qwen |
| Python arithmetic/source-scope verifier | PASS | PASS |
| Final synthesis | Rejected: incomplete sentences | Accepted, no rejection |
| Final scientific check | FAIL: time horizon lost | PASS, checked=true |
| Delivery author | verified_engine_partial | qwen_verified |
| API job | COMPLETED | COMPLETED |
| Response elapsed | 16.623 s | 12.357 s |
| Minimum observed free RAM | 5387.8 MiB | 6997.0 MiB |
| Maximum observed system commit | 16835.4 MiB | 17175.2 MiB |
| Maximum observed VRAM used | 3864 MiB | 3877 MiB |
| Maximum GPU temperature | 67 °C | 68 °C |
| Target unload confirmation | 0.291 s | 0.271 s |
| Models after unload | Empty | Empty |

These are sampled extrema, **not guaranteed peaks**. Retest minimum commit headroom 18457.3 MiB; after unload free RAM 8363.9 MiB and used VRAM 610 MiB. No runtime resource violation, thermal slowdown or provider/CUDA failure was observed during either run. No claim is made about unlogged OS-wide CUDA events. The safety limits remain admission RAM 6656 / runtime RAM 4096 MiB, commit headroom 4096 MiB, admission free VRAM 4096 / runtime free VRAM 512 MiB, local QA temperature stop 82 °C and Windows low-memory notification.

## Confirmed defects found and corrected in the first real run

1. The model's English retrieval query replaced the authoritative user question, losing “30 days” before the calculator. `_tool_context(..., original_question=...)` now keeps retrieval wording separate from numeric task scope. Regression uses an intentionally rephrased model query through the actual Chat jobs endpoint.
2. Synthesis input contained 17290 characters with repeated state, source and provenance trees, making irrelevant/repeated/incomplete prose likely. The estimate-specific stage projection preserves the question, typed numerical evidence, unknown timed yield and loading scope in 1785 total input characters including the synthesis instruction. Full source/provenance trees remain in the saved tool trace. Context size, model, token cap and request count were not increased.
3. Supported BMP-potential numbers are not permitted as timed production claims merely because the duration is user supplied. The existing typed quantity parser now also gates this semantic role. The deterministic result and assumptions are displayed alongside any accepted Qwen explanation; a rejected model draft cannot erase them.

Additional independent source/wet-mass/solids guard tests were added after the live run. The exact stored real draft and delivered answer passed these strengthened guards in a deterministic replay; this was **not** counted as another live generation: [replay record](literature_estimates_20261112/replay_validation.json).

## Real delivered answer and independent review

The unchanged full answer, including source, arithmetic, assumptions and the model's clarification, is saved in [user_answer.txt](literature_estimates_20261112/user_answer.txt). The original synthesis was:

> Условный потенциал метана 2,92–4,11 м³ для 142 л коровьего навоза, но не может быть привязан к 30 дням без дополнительных данных.

The API delivered this explanation **with** the Python-derived 2922.95072–4113.9956 L reference, explicit 30-day unavailability, conditional slurry transfer, source conditions and working-volume limitation. Raw drafts, actual requests, all tools, verification, events, telemetry and unload evidence are in the retest trace; a convenient [summary](literature_estimates_20261112/real_chat_summary.json) preserves the same content.

| Independent content criterion | Result |
|---|---|
| Reported material/volumes retained; no invented measured mass | PASS |
| Density, solids and BMP remain one named conditional slurry study | PASS |
| TS and VS have the same wet-mass basis; deterministic unit conversion | PASS |
| Potential not substituted for 30-day yield or a single reactor cycle | PASS |
| Nominal 200 L not treated as working volume or safe fill | PASS |
| Numeric verifier checks quantity origins and matching roles | PASS, checked=true |
| Scientific verifier performs scoped checks | PASS, checked=true |
| New real Qwen explanation delivered without fallback | PASS |
| Clarification quality | PARTIAL: asks to clarify volume despite volume already known; physical form and working volume would be more useful |

This manual assessment used the actual final answer, calculation and source applicability, not just the automatic PASS. It is not independent experimental validation of the transferred profile or a blinded holdout.

## Changed files, use and remaining limits

Changed in this task: `src/advisor/schemas.py`, `mixing.py`, `evidence_engine.py`, new `estimation.py`, `api.py`; `src/agent/analytical.py`, `autonomous.py`, `runtime9.py`, `tool_manifest.py`, `verification9.py`; `src/dashboard/firo_demo.py`; `frontend/src/firoDemo.ts`, `pages/FiroDemoMvp.tsx`, `ConversationReply.tsx`; `frontend/tests/firo-demo-mvp-browser.mjs`; new `tests/test_literature_methane_estimates.py`; docs and these reports. Frontend build artifacts were regenerated. Existing model bundles, database history, source profiles and production settings were preserved.

Launch from project root: `python -X utf8 main.py dashboard --firo-demo --port 8770`, then open `http://127.0.0.1:8770/dashboard/#/demo`. Existing experimental backend is left available; the model is unloaded. API example and mode semantics are documented in `docs/firo_demo_mvp.md`.

Remaining priorities: better question selection from unresolved parameters; broader independent validation across substrate forms and source scopes; experimentally justified time-series/kinetic evidence for a real 30-day forecast; browser Chat inference checks with the new literature pathway; independent holdout and full FIRO acceptance. Sample variability, gas moisture and unmeasured reactor effects remain unresolved. A single valid Qwen scenario is not overall READY.

Final network smoke check after loading all strengthened guards: **PASSED**, including independent density/mass and source-range checks, scientific status passed, exact result persistence and empty Ollama `/api/ps`: [final HTTP evidence](literature_estimates_20261112/final_http.json). Only our experimental backend was restarted; final PID 23424 on port 8770. Production backend/processes were not stopped. `git diff --check` passed for the changed code (existing CRLF normalization notices only).
