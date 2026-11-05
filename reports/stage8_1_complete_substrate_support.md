# BioReactor AI v8.1 — Complete Substrate Intelligence

## Scope and result

Stage 8.1 extends the existing advisor and conversational agent. It does not retrain, replace, or rewrite the BMP estimators or the v8.0 reports. The market database used by the normal dashboard was not used for QA; browser checks ran against a separate SQLite file in this report directory.

The substrate form now uses the backend catalog for materials, supported forms, units, species, poultry types, bedding, decomposition state, and data mode. It supports editing and removing mixture components, within-family unit changes, density-based mass/volume conversion when evidence exists, database-backed save/load with append-only revisions, and transfer to the existing agent. The agent retains the supplied quantity, unit, axes, selected profile and assumptions.

When a gas estimate names manure but omits its physical form, the agent asks for the form before selecting a profile. A new interface checkbox controls whether gas volumes from different studies may be treated as comparable; it is unchecked by default. For mixtures whose study gas bases cannot be reconciled, the system reports the known component subtotal with a warning that it is not a lower bound or a total mixture prediction.

## Audited evidence and scope

The catalog contains 15 recognized material categories and 12 scoped numerical profiles. Six paired profiles were added from the reviewed primary studies. These are sample-level laboratory measurements, not guaranteed plant output or population intervals.

| Material and sample | TS, % wet | VS, % wet | BMP, mL CH₄/g VS | Conditions and scope |
|---|---:|---:|---:|---|
| Cattle slurry, Eftaxias et al. | 8.31 | 7.01 | 276 ± 3 | Farm sample; 38 °C, 20 d |
| Poultry solid, type/bedding unspecified, Eftaxias et al. | 69.25 ± 0.41 | 55.46 ± 0.65 | 320 ± 19 | Farm sample; 38 °C, 20 d |
| Pig slurry, Eftaxias et al. | 2.23 ± 0.25 | 1.51 ± 0.35 | 172 ± 2 | Farm sample; 38 °C, 20 d |
| Sheep solid, Eftaxias et al. | 35.22 ± 1.44 | 23.63 ± 0.89 | 252 ± 6 | Farm sample; 38 °C, 20 d |
| Goat solid, Eftaxias et al. | 71.7 ± 0.34 | 60.6 ± 2.24 | 227 ± 9 | Farm sample; 38 °C, 20 d |
| Laying-hen conveyor-belt droppings, Ramos-Suárez et al. | 38.6 ± 2.1 | 28.68 derived from paired TS and VS/TS | 282.1 ± 3.98 | Fresh sample; 37 °C, 56 d; BMP spread reported as standard error |

The `±` values above are reported by the publications. Their meaning is not consistently a standard deviation, and they are not prediction intervals or calibrated uncertainty bounds. The catalog stores the reported spread separately from the paired sample mean used for the reference calculation.

Primary sources: [Eftaxias et al., 2024](https://doi.org/10.3390/app14114957), Table 1; [Ramos-Suárez et al., 2019](https://doi.org/10.5424/sjar/2019172-14577), BMP results and Supplementary Table S1. Local reviewed source files and table locators are retained under `reports/stage8_1/sources/`.

The Eftaxias poultry sample has no reported poultry subtype or bedding. It can be used for the explicitly scoped unspecified/chicken reference, but not as a broiler, turkey, or bedding-specific study. Matching the high-solids sample to the UI’s `dry` state is marked conditional: the sample had 69.25% TS and was not a controlled post-drying sample. The laying-hen profile is separate and available only for the `layer` subtype. Broiler and turkey selections do not silently inherit either profile.

The Eftaxias paper reports an overall methane fraction across samples, not a material-specific fraction. That value is not attached to individual substrates. Numeric gas temperature/pressure/moisture normalization is incomplete for the paired studies, so mixed-study gas totals and downstream energy remain blocked unless the user explicitly opts into the visible common-basis scenario. The Ramos study’s gas normalization details are also incomplete. Neither study supplies a density for these samples. The UI does not derive density from TS or treat a dry solid as slurry.

Other missing or weakly covered characteristics include feedstock-specific density, pH, C/N, ash, lignin, particle size, bedding fraction, age/storage history, inhibitors, continuous-digester loading, and co-digestion interaction. Recognition of vegetable waste, grass, silage, and other categories does not imply a numerical BMP profile for them.

## Implementation

- Backend `/api/advisor/catalog` is the source of the form’s material and vocabulary options; the form no longer carries independent material/species/type lists.
- Compatible literature profiles can be selected explicitly. Profile IDs are checked against material, species, poultry subtype, physical state, bedding, and decay restrictions on the server.
- Editing material/state/species/subtype/bedding/decomposition/data mode clears an incompatible profile selection.
- Mass units and volume units convert exactly within their own dimensions. Cross-dimension conversion uses an explicit measured or scoped density; absent density returns `needs_input`. A literature interval is not collapsed to a midpoint in the UI.
- Mixtures persist to SQLite in `advisor_saved_mixtures` as append-only revisions. Loading restores component rows, reference IDs, options, units and quantities.
- Chat handoff writes a v7-compatible session through the existing dashboard store. It retains all component fields and opens the chat with an economics question ready to send.
- Agent intake asks a physical-form clarification for manure when species is known but state is missing. A state is not inferred from mass or volume.
- Common gas-basis comparison is now an explicit, off-by-default scenario in the builder. The agent reports partial known-substrate values without presenting them as the complete mixture result.

## Verification

- New API/agent scientific regressions: **9 passed** (profile scope, mismatches, unprofiled broilers, dry-transfer notice, unit conversion, save/revision/load, handoff, contradictory axes, and clarification of missing physical form).
- Focused substrate and agent suite: **81 passed**.
- Frontend suite: **60 passed across 10 files**.
- Frontend TypeScript check and production build: **passed**.
- Isolated local HTTP/browser run: **11 checks passed**, including catalog support, liquid pig-manure volume entry, layer-profile selection, two-component analysis, backend persistence and reload, agent handoff, axis preservation, mobile layout, and no browser JavaScript errors.
- Screenshots: [`substrate-mixture-desktop.png`](stage8_1/screenshots/substrate-mixture-desktop.png) and [`substrate-mixture-mobile.png`](stage8_1/screenshots/substrate-mixture-mobile.png). Machine-readable results: [`browser_results.json`](stage8_1/browser_results.json).

The full backend suite was also run with its temporary directory placed inside the workspace: **369 passed, 17 failed**. Nine failures require the `catboost.core` module to deserialize preserved BMP model artifacts, which is absent from the system Python used for this run. Three failures come from the installed `truststore` package not exposing `SSLContext`. One dashboard diagnostics check expects local model services to be present. Four older conversational assertions rely on numeric answers from manure prompts that omit its physical form; the v8.1 path now asks for that missing input. The focused stage 8.1 and agent suite passes. No BMP model files were altered.

The browser/API run used an isolated QA SQLite database and did not write any market observations. The local server on port 8765 was then restarted on the existing `data/market/market.sqlite3`; it now serves catalog v8.1 (15 categories, 12 profiles). Startup initialized the new empty `advisor_saved_mixtures` table. Existing market observations and saved results were not altered.

## Known limitations and next data collection

1. Collect paired fresh-mass TS, VS, BMP and density samples for Kazakhstan-relevant cattle, pig, layer/broiler poultry, sheep, and goat feedstocks; record subtype, bedding, age, storage, dilution, and sample origin.
2. Publish methane fraction and gas reference temperature, pressure, and moisture for each sample, or retain measured raw gas data so normalization can be audited.
3. Collect replicated BMP assays and report variance definitions, inoculum, blank correction, assay duration, and whether plateau was reached.
4. Add local feedstock prices, transport, preprocessing, storage, digestate quality and disposal costs before interpreting the economic comparison as a recommendation.
5. Validate co-digestion with measured mixtures. Current additive references do not model synergy, inhibition, kinetics, or full-scale conversion efficiency.

The system’s literature values remain conditional estimates for the named study samples. They are not plant guarantees, probability-calibrated intervals, or proof of legal/technical suitability for gas or digestate sale.
