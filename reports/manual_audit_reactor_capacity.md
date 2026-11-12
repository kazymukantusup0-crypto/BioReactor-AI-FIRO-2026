# Manual audit: reactor capacity validation

Date: 2026-11-09
Project: BioReactor AI, existing `main` branch. No release or model bundle was changed.

## Scope and evidence

The 470 L liquid cattle-manure / 114 L nominal-reactor behavior and its prior answer are user-reported observations. They were not replayed through Qwen in this audit. Source inspection confirmed that the optimizer only emitted a `feedstock_volume_l` planning warning for strict `feedstock_volume_l > reactor_total_volume_l`; equality and lower volumes had no explicit working-volume assessment. The response builder appended its oversize warning after methane prose. `plan_batches` already required working volume, feed mode, inoculum, dilution water and resident liquid before producing a count.

## Changes

- Added shared `src/optimizer/capacity.py` volume validation. It distinguishes `EXCEEDS_NOMINAL`, `WORKING_VOLUME_UNKNOWN`, `EXCEEDS_WORKING_VOLUME`, `OCCUPANCY_INCOMPLETE`, and a declared-volume fit. It never infers working volume from nominal capacity and never converts litres to kilograms.
- Integrated this validation into `analyze_constraints`, exposing the structured `capacity_assessment` with the optimizer result.
- `ConversationAgent.ask` now checks physical capacity after deterministic parameter extraction/state binding and before model interpretation, research planning or tool execution. It records a `ReactorCapacityChecked` event. The binding assessment is also passed into model understanding and Runtime 9 planning/synthesis context.
- The deterministic capacity notice is placed at the beginning of the user-facing answer. For an oversize lot, it distinguishes whole-lot methane potential from per-cycle yield, states that simultaneous loading is impossible, offers sequential batches or a larger reactor, and declines an exact batch count without the necessary charge and process inputs. For equal/smaller lots with unknown working volume, it does not claim the full lot fits and warns against filling to the brim.

## Regression coverage

The new `tests/test_reactor_capacity_validation.py` checks:

- 470 L / 114 L: simultaneous loading is impossible, sequential batches are offered, and exact batch count remains unknown.
- 114 L / 114 L: working volume is not inferred and brim-filling is rejected.
- 100 L / 114 L and 47 L / 114 L: below nominal is not misreported as confirmed working capacity.
- Unknown working volume, including when water/inoculum are mentioned.
- Water, inoculum and resident liquid counted against a known working volume.
- No unsupported batch count.
- Structured optimizer capacity assessment.
- The actual deterministic conversation path: reported volumes are preserved over a follow-up, no mass is derived without density, and preflight occurs before tool execution.

Final focused command:

```text
python -m pytest tests/test_reactor_capacity_validation.py tests/test_optimizer.py tests/test_process_agent.py tests/test_conversation.py -q
```

Result: **84 passed**, 1 existing Starlette/httpx deprecation warning, 13.84 s. Environment: Windows, Python 3.13.13, pytest 8.4.2.

Compilation check passed:

```text
python -m py_compile src/optimizer/capacity.py src/optimizer/constraints.py src/agent/conversation.py src/agent/dialogue_response.py src/agent/runtime9.py tests/test_reactor_capacity_validation.py
```

Scoped `git diff --check` passed. Git printed existing LF-to-CRLF working-copy notices for touched Python files; no whitespace errors were reported.

## Requested cases and outcome

| Case | Deterministic result |
|---|---|
| 470 L / 114 L | `EXCEEDS_NOMINAL`; cannot load simultaneously; no batch count; whole-lot potential is not a one-cycle result |
| 114 L / 114 L | `WORKING_VOLUME_UNKNOWN`; no assertion that the lot fits; do not fill to brim |
| 100 L / 114 L | `WORKING_VOLUME_UNKNOWN`; below nominal alone does not establish loadability |
| 47 L / 114 L | `WORKING_VOLUME_UNKNOWN`; below nominal alone does not establish loadability |
| Working volume unknown | No exact count or per-cycle yield |
| Add water/inoculum | Included in occupancy when known; otherwise assessment remains incomplete |
| Sequential batches | Offered for an oversize lot; count is withheld absent working volume, water, inoculum and process constraints |
| Multi-turn dialogue | 470 L feed and 114 L reactor remain separately bound after a temperature follow-up |

The deterministic conversation regression checks the specific user-provided dimensions without a live model. It confirms the capacity check is recorded before the answer/tool phase and that the first user-facing paragraph is the capacity warning.

## Cancellation statement

The user confirms that cancelling sessions works in the browser. This is recorded as a user-reported browser observation only. It does **not** establish that an Ollama request or GPU inference stops on cancellation; no GPU or inference measurement was made for this task.

## Limits and status

No Qwen request, browser E2E, full acceptance, or GPU test was run, as requested. No user process, database, BMP model, CUDA/Ollama setting, or prior-stage result was modified. The real-Qwen synthesis behavior and any contradiction later in generated prose remain unverified. Therefore this is a **deterministic capacity-validation fix with focused tests passed**, not a project-wide READY or acceptance claim. A future real-model check should verify that model prose does not contradict the deterministic front-loaded capacity result.


## Final recheck addendum - 2026-11-09

A final combined run initially exposed two integration regressions: `DialogueState.brief()` returns a mapping (not a string), and an existing conversation regression depended on the prior Russian "cannot load all at once" wording. The preflight is now added as a mapping field; the Russian oversize notice retains that established phrase. These were fixed before final verification.

Superseding final result for the focused suite: **84 passed**, one existing Starlette/httpx deprecation warning, 13.82 s, using the command and environment recorded above. Compilation and scoped `git diff --check` passed after all edits. No Qwen or browser test was run.
## 2026-11-09 — Real Dashboard regression investigation and remediation

### Confirmed cause

The saved Dashboard turn matching the reported 470 L / 114 L prompt was inspected in the local market database. It completed at 2026-11-09T11:22:51.800999+00:00, with conversation version 7 and reply mode verified_partial. Its recorded tools were assess_process_evidence, assess_substrate_potential, and evaluate_partial_economics. The saved reply contained the reported methane/economic figures, but its diagnostics had no ReactorCapacityChecked event and its technical metadata had no reactor_capacity_assessment. The persisted state kept quantity=470, unit=L, material_volume_l=470, and reactor nominal volume 114 L; it did not contain mass_kg. Therefore the capacity warning was missing in that actual turn, while “mass 470 L” was a presentation error, not a density conversion in state.

The process currently listening on 127.0.0.1:8765 is PID **26532**, started at **2026-11-09 10:32:17 UTC**, with command:

    C:\Users\Kazhu\AppData\Local\Programs\Python\Python313\python.exe main.py dashboard --port 8765 --no-browser

Its working directory is the existing BioReactor_AI project. GET http://127.0.0.1:8765/health returned 200 and identified this project's data/market/market.sqlite3. The database has completed Chat requests from this process's operating period at 10:40, 10:45, 10:48, 10:50 and 10:52 UTC, before the capacity edits; their saved replies identify conversation_version 7 and analysis_version 9.0. src/dashboard/api.py imports ConversationAgent inside execute_message, so those earlier requests loaded conversation.py and the Runtime 9 path into the running interpreter before the later file edits. The current capacity/conversation source files were subsequently modified (capacity.py was first updated at 11:15 UTC and conversation.py at 11:13 UTC; latest remediation edits are at 11:31 and 11:37 UTC; batch_intent.py at 11:43 UTC). src/dashboard/launcher.py calls uvicorn.run without reload enabled. Therefore PID 26532 retained the pre-fix imported ConversationAgent when the 11:22 turn ran and could not see the later capacity preflight. The absent preflight event in that saved turn confirms this is the primary runtime/source mismatch. The process was not stopped.

### Actual Chat route and additional integration defects

The React Chat submits with api.submitJob from frontend/src/useChatSession.ts; the request is POST /api/dashboard/chat/sessions/{id}/jobs. src/dashboard/job_api.py registers this route under the /api/dashboard router prefix. JobRuntime calls execute_message in src/dashboard/api.py, which creates a version-7 ConversationAgent; for an async job it sets runtime_version='9'. The capacity preflight in ConversationAgent.ask runs before _ask, where Runtime 9/model/tool selection begins.

Two additional user-visible defects were found and fixed:

- The earlier capacity postprocessor updated the answer and paragraphs, but Chat prefers and renders user_facing_answer.sections[*].body when sections are present. The warning and volume correction now reach the rendered sections too, and the warning is placed first. The specific saved failing turn had zero sections and eight paragraphs, so this renderer gap was not the cause of that turn; it was a separate integration path that could hide the warning on other response shapes.
- batch_intent.confirmation called every quantity “mass”, including quantities in litres. It now labels L/m3 as feedstock volume and retains “mass” only for mass units. The final answer postprocessor remains as a safeguard.

### Changes in this remediation

- src/agent/conversation.py: normalize mistaken mass wording only when the bound state confirms volume units and has no mass measurement; attach the capacity finding to the answer, paragraphs, and rendered sections before returning it.
- src/agent/batch_intent.py: correct the new-batch confirmation terminology for volume versus mass, including assumed values.
- src/optimizer/capacity.py: provide the requested Russian over-capacity warning, sequential-batch/larger-reactor options, missing working-volume/water/inoculum caveat, and distinguish whole-lot methane potential from per-cycle output.
- tests/test_reactor_capacity_dashboard.py: exercise the Dashboard HTTP job endpoint with deterministic no_llm mode, persistence/history restoration, visible warning, correct units, and repeat result reads.
- tests/test_reactor_capacity_validation.py: cover the final rendered sections and batch confirmation units.

### Verification

Command:

    python -m pytest tests/test_reactor_capacity_validation.py tests/test_reactor_capacity_dashboard.py tests/test_optimizer.py tests/test_process_agent.py tests/test_conversation.py tests/test_stage9_jobs.py tests/test_stage9_runtime.py tests/test_acceptance_root_cause_remediation.py -q --basetemp .pytest-tmp-capacity-final

Result: **176 passed**, one existing Starlette/httpx deprecation warning, 34.00 s. The endpoint tests use FastAPI TestClient against the same registered POST /api/dashboard/chat/sessions/{id}/jobs route; they do not call Qwen or the already-running process.

| Check | Result |
|---|---|
| 470 L / 114 L via Dashboard job endpoint | PASS — EXCEEDS_NOMINAL, warning appears first in answer and rendered content |
| 47 L / 114 L, working volume unknown | PASS — no claim that it fits; dimensions remain volume |
| Saved turn and restored follow-up | PASS — first turn remains persisted with its warning and volume facts |
| Repeat result read after completion | PASS — stored reply retains warning; this is not a concurrent late-writer stress test |
| Confirmation terminology | PASS — litres render as volume; kilograms render as mass |
| Preflight ordering | PASS — capacity event precedes tool execution |
| Python compilation / scoped whitespace check | PASS — run after edits |
| Live browser after backend restart | NOT RUN |
| Real Qwen response after fix | NOT RUN |

Safe restart command for the terminal that owns PID 26532: press Ctrl+C there, then run:

    Set-Location 'C:\Users\Kazhu\Downloads\face_dataset_you_noname\face_dataset_project\BioReactor_AI'
    python main.py dashboard --port 8765 --no-browser

### Status and limits

The stale backend diagnosis and deterministic endpoint correction are confirmed. The running Dashboard still has the old code until its owner restarts it. No process was terminated. A new manual browser test after that restart is required before claiming the real Dashboard display is fixed. No Qwen, GPU, browser E2E, or full acceptance test was run. The economic and methane claims in the saved turn were observed in the user's actual Dashboard report; this remediation does not revalidate their scientific or economic correctness.

## 2026-11-09 follow-up — concise warning and nominal equality

The wider deterministic suite found duplicated capacity wording in the advanced conversation path and a floating-point boundary case that could label an effectively equal feed volume as below nominal. The shared renderer now uses a `1e-9` L wording tolerance, reports no remaining space for inoculum/headspace when the feed equals nominal full volume, and keeps unknown working volume explicitly unknown. The advanced path no longer appends a second reactor warning after the canonical preflight. Compact follow-up responses retain the methane figure and capacity caveat.

The recognized substrate-name count increased from 15 to 20 in the existing catalog without changing the approved numerical profile list (18 records across 8 materials, one complete density/TS/VS/BMP profile); the stale count assertion was corrected accordingly.

Final deterministic verification: `python -m pytest -q -p no:cacheprovider --basetemp .pytest-ai-agent-final3` — **653 passed**, no excluded tests, two existing warnings. Focused capacity/conversation/dashboard run — **16 passed**. Compilation, CLI `python main.py --help`, and scoped `git diff --check` passed. Dashboard process PID 3412 was started from this working copy on port 8766 with scheduler disabled; `/health` and `/dashboard/` both returned HTTP 200, and Edge was opened to the Dashboard. This is not a manual Chat interaction or browser persistence test. Port 8765 and any unknown processes were left untouched. Real Qwen and GPU inference were not run; the saved 470 L/114 L economic and methane claims were not scientifically reevaluated. Manual browser verification of the rendered warning after refresh/reopen remains **NOT RUN**.
