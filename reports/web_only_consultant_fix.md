# Web-only consultant correction — 2026-11-12

Status: implemented, acceptance PARTIAL, FIRO NOT READY. Existing branch/main and models retained. No new application/site/server architecture, no model training, no resource threshold reduction. Primary FIRO UI is the existing `/dashboard/#/chat`.

## Confirmed origin of the desktop window

The parent workspace has a **different** `main.py`, outside `BioReactor_AI`. It imports Tkinter, defines `BioreactorAdvisorApp`, sets the title «БиоРеактор — помощник фермера» and adds the four reported tabs. Its old `main()` constructed `tk.Tk()` and ran `mainloop()`. Running `python main.py` from the parent directory reproduced that entry path. The actual command/button used by the user was not logged, so cannot be asserted. Motive/author/date of creation are not established by this inspection.

It uses `OLLAMA_MODEL="qwen2.5:1.5b"`, not the guarded web4B profile. It combines conversational retrieval, trained BMP input construction, batch/demo economic calculations and manual pilot-observation logging. Those scientific modules, model files and observations were not deleted. Existing web services already supply scientific retrieval, BMP prediction, substrate/energy/economic tools and durable dialogue; duplicating the desktop calculators would create another inconsistent calculation system. Legacy pilot-log file display/import is not newly exposed as live sensor ingestion; data remain intact, and the web sensor contract still honestly reports no live hardware.

The parent entry now delegates **before Tkinter/ML imports** through `launch_bioreactor_web.py` to the existing FastAPI/React Chat. If the correct8770 experimental database is already served, it opens its Chat URL; otherwise it runs the existing project CLI. An unrelated server/database is not replaced. Importable historical functions/classes remain available, while calling the public `main()` also launches the web interface. No Tk/Kivy window is started by either default entry. Existing web launcher now opens `#/chat`, including experimental mode, rather than `#/demo`.

## Web defects and fixes

- Multiple candidate temperatures are now a typed comparison list in advanced dialogue state. They do not become a measured scalar temperature. A request to compare25/35 preserves the previously assumed25°C and original78L/200L; it evaluates source variants instead of filtering everything to the first number.
- Planning retains the original compound task for a temperature follow-up/comparison, so methane/process/economic tools are executed rather than treating the turn as a bare numeric correction with0tools.
- User scenario temperature is displayed first and explicitly labelled conditional, separately from source discussion temperature and an unvalidated equipment setpoint.
- A comparison section presents source-specific potentials and a conditional conclusion. For78L pig slurry:25°C reference416LCH4 and35°C reference512.69LCH4. These are whole-lot literature endpoints, not measurements, one-cycle output or a30-day prediction.
- The existing energy module supplies a separately labelled hypothetical FNR-basis calculation:4.1475/5.1115kWh. It assumes compatible dry reference gas volumes; source normalization is not fully verified. This is not useful heat. The verifier independently checks the multiplication, method/assumption/source. No tariff, heater efficiency, heat loss or profit is invented.
- Initial heating/maintenance costs still require real charge mass, heat capacity, ambient/initial temperatures, insulation and duration. Conditional advice compares greater fuel potential against extra heating/stability burden; no unconditional optimal operating mode or heater command is issued.
- Removed duplicate gas-detail block from comparisons, shortened repeated BMP explanations, consolidated unknown heating costs and removed unsolicited55°C heat worksheets. Critical source/capacity/provenance limits remain visible.
- Guard resource traces now persist independently of a successful reply. Future cancellation writes `RESOURCE_STOP` job events with reasons/audit path, addressing the observed loss of resource diagnosis when cancellation prevents reply commit. No late answer is committed.

## Tests and actual browser results

Final deterministic command from `BioReactor_AI`:

```powershell
python -X utf8 -m pytest tests/test_web_only_consultant.py tests/test_farmer_consultation.py tests/test_firo_chat_guard.py tests/test_stage9_verification.py tests/test_stage9_runtime.py tests/test_complete_economics.py tests/test_reactor_capacity_dashboard.py -q -p no:cacheprovider --basetemp=.pytest-web-only-audit-20261112
```

**131 PASSED**,0failed/0skipped,25.46s; one existing Starlette/httpx warning. Includes actual parent-entry execution under an import fence (Tkinter/joblib/pandas cannot import), shared FastAPI three-turn state/history/scenario tests, physics/provenance and cancellation checks. This is a relevant suite, not a new full-project acceptance. Earlier90/130/131 runs overlap and are not summed. Frontend source was not changed; the existing built React renders server sections. Added actual browser test `frontend/tests/web-only-dialogue.mjs`.

Browser commands from `frontend`:

```powershell
node tests/web-only-dialogue.mjs
node tests/web-only-dialogue.mjs --no-llm
```

The first browser attempt discovered an **old backend PID14804** from17:28, older than modified source. It returned old wording and no comparison state, despite tests passing against current files. The trace is retained as `web_only_consultant_20261112/browser_stale_backend.json`. This is an environment/version failure, not accepted as proof of current code. After command/PID/idle-job checks, only our old experimental backend was restarted to PID18808; production/user processes were untouched.

| Message | Updated real Qwen attempt | Updated real web without LLM |
|---|---|---|
|78Lpig /200Lreactor, methane+temperature+economics|PASS for limited conditional answer: actual4B, four tools, accepted Qwen explanation|PASS, tools and78/200 retained|
|Only25°C|CANCELLED before commit; no delivered answer, not PASS|PASS,25°C remains ASSUMED, not actual measurement|
|Compare25°C/35°C|NOT RUN after cancellation|PASS, both source outcomes/conditional energy, costs unknown, conditional advice|

The updated real first turn took9.574s including scope cleanup; observed freeRAM5652.2MiB minimum near the end, GPU78°C, targeted unload0.180s. The second ended `CANCELLED/USER_CANCELLED`, no late reply; `/api/ps` was empty afterward. Thermal cause is plausible but **not proven**, because the old guard discarded its local telemetry on cancellation. That diagnosis gap was fixed with durable audits/events, then tested deterministically. No additional GPU inference was run to obtain a greener result. The latest audit-writing fix has not itself been live-tested during a resource stop.

The complete three-message browser run in explicit `no_llm` mode **PASSED**: same actual session, tools each turn,78L/200L retained,25°C conditional, comparison[25,35], reload after every turn, no JavaScript errors. Arithmetic verification `ok` on all turns. This is useful verified Python operation, **not successful Qwen inference**. Full delivered answers/tools/verifier output: [actual_web_answers.md](web_only_consultant_20261112/actual_web_answers.md). Original JSON and screenshots: `web_only_consultant_20261112/browser.json`, `turn_1.png`–`turn_3.png`; incomplete real-model attempt: `browser_real_qwen_incomplete.json`. All measurement/price/energy limitations remain explicit.

## Files

Parent: `main.py`, new thin `launch_bioreactor_web.py` compatibility entry (no UI). Existing project: `src/dashboard/launcher.py`, `firo_demo.py`, `api.py`; `src/agent/nlu.py`, `analytical.py`, `farmer_consultation.py`, `verification9.py`; `src/economics/energy_conversion.py`; new `tests/test_web_only_consultant.py`, resource-audit fixture in `tests/test_firo_chat_guard.py`; browser regression and this report/artifacts. No files, model bundles, pilot observations or previous conversations removed.

## Remaining acceptance

RAM admission6656MiB and thermal/runtime safeguards unchanged. The full three-turn **real-Qwen** dialogue remains incomplete. Complete it only after cooling and fresh resource admission. Verify new cancellation audit during a separately bounded stop test if needed; do not infer its live result from mocks. Broader scientific/independent holdout and full financial/thermal calibration remain outstanding. FIRO NOT READY.

Normal launch from parent: `python main.py`; explicit launch from project: `python -X utf8 main.py dashboard --firo-demo --port 8770`. Both lead to the existing web Chat. Do not start a second server when8770 is already active. No standalone desktop window is required or launched.

Final service checkpoint: our idle18808 backend was reloaded once more to16672 to load the durable audit change. Health200, correct experimental SQLite, Ollama models empty. No subsequent GPU inference; no user/production processes stopped. Scoped git diff --check passed (line-ending notices only).
