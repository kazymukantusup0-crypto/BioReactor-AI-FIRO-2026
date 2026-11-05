# BioReactor AI v8.3 - Functional platform validation

Date: 2026-11-03. Tests used an isolated SQLite copy and local server port 8767. The original market database/history and BMP model artifacts were preserved; no model retraining occurred.

## Implemented behavior

- The same evidence-scoped calculation engine now serves Qwen chat, advisor API, and Dashboard. Methane, geometry, partial mixture totals, and stable economic outputs matched in 30/30 real chat cases. Only the volatile market-observation age in seconds was excluded from equality checks.
- Dashboard inputs trigger recalculation for feed, water, reactor, energy, and costs. Separate literature scenarios can be selected. Geometry shows known versus complete charge; costs stay unknown until supplied.
- Density is never silently set to 1. Batch working capacity and total volume are checked separately; continuous throughput is not treated as a batch charge. Water adds no VS or methane potential.
- Revenue, energy use, and all costs remain separate. Market prices retain region, publication date, source, and stale/reference status.
- Mixture handoff preserves component rows and typed reactor/economic settings. Follow-up additions and quantity corrections retained the conversation inventory.

## Real Qwen3 8B / HTTP cases

30 independent cases (35 user turns) ran through the local HTTP server using Qwen3 8B. The checker verified actual tool calls, numerical outputs, unit conversions, reactor loading, conversational context, API/chat equality, and that missing profiles did not create invented methane values. Result: 30/30 cases passed.

| Case | Actual prompt | CH4 potential, m3 | Profile / outcome |
|---|---|---:|---|
| `cattle48` (1 turns) | У меня 48 литров коровьего навоза и реактор 100 литров. Сколько метана и выгодно ли? | 0.98804-1.3906, 0.87584, n/a | PASS; baek2020-bedded-cattle, eftaxias2024-cattle, oliveira-rm1-2025-v1 |
| `grass58` (1 turns) | У меня 58 кг травы и реактор 100 литров. Сколько метана можно получить? | 3.7864, 3.1813, 3.8095, 5.0557 (6 separate profiles) | PASS; lallement2023-grass-1, lallement2023-grass-2, lallement2023-grass-3, lallement2023-grass-4, lallement2023-grass-5, lallement2023-grass-6 |
| `poultry50` (1 turns) | У меня 50 кг куриного помёта и реактор 100 литров. Сколько метана и поместится ли загрузка? | 8.8736, 4.0453 | PASS; eftaxias2024-poultry, ramos2019-layers-HD-sample1 |
| `food5` (1 turns) | У меня 5 кг пищевых отходов и реактор 90 литров. Сколько метана и выгодно ли? | 0.31814 | PASS; baek2020-food-pulp |
| `mixture` (1 turns) | Смешай 4 кг коровьего навоза, 2 кг травы и 1 кг пищевых отходов. Рассчитай метан и энергию. | 0.27547-0.30859, 0.25461-0.28773, 0.27627-0.30939, 0.31924-0.35236 (8 separate profiles) | PASS; baek2020-bedded-cattle, baek2020-food-pulp, lallement2023-grass-1, lallement2023-grass-2, lallement2023-grass-3, lallement2023-grass-4, lallement2023-grass-5, lallement2023-grass-6, oliveira-rm1-2025-v1 |
| `overfill` (1 turns) | У меня 80 литров навозной жижи КРС, реактор 50 литров. Сколько метана и можно ли загрузить всё сразу? | 1.6467-2.3177, n/a | PASS; eftaxias2024-cattle, oliveira-rm1-2025-v1 |
| `water` (2 turns) | У меня 5 кг пищевых отходов и реактор 90 литров. Сколько метана? | 0.31814 | PASS; baek2020-food-pulp |
| `compare` (1 turns) | Что выгоднее: 10 кг коровьего навоза или 10 кг пищевых отходов? | 0.2032-0.286, 0.25699, 0.19348, 0.63628 | PASS; baek2020-bedded-cattle, baek2020-food-pulp, eftaxias2024-cattle, oliveira-rm1-2025-v1 |
| `temperature` (1 turns) | В реакторе 30 градусов. Стоит ли повышать температуру? |  | PASS; no applicable profile |
| `costs` (2 turns) | У меня 5 кг пищевых отходов. Сколько денег я заработаю? | 0.31814 | PASS; baek2020-food-pulp |
| `pig8` (1 turns) | У меня 8 кг свиного навоза. Сколько биогаза? | 0.037845, 0.020778 | PASS; eftaxias2024-pig, pham2013-pig-vdi |
| `horse` (1 turns) | Сколько метана из 7 кг конского навоза? | 0.25267 | PASS; monch2013-horse-dung-A |
| `goat` (1 turns) | Сколько метана из 3 кг козьего навоза? | 0.17864, 0.41269 | PASS; eftaxias2024-goat, eftaxias2024-sheep |
| `straw` (1 turns) | Оцени метан из 2 кг пшеничной соломы. | 0.32359 | PASS; monch2013-straw-A |
| `silage` (1 turns) | Сколько метана из 12 кг силоса? | n/a | PASS; no applicable profile |
| `vegetables` (1 turns) | Сколько метана из 6 кг овощных отходов? | n/a | PASS; no applicable profile |
| `fruit` (1 turns) | Сколько метана из 3 кг фруктовых отходов? | n/a | PASS; no applicable profile |
| `whey` (1 turns) | Сколько биогаза из 15 литров сыворотки? | n/a | PASS; no applicable profile |
| `plant` (1 turns) | Сколько метана из 4 кг растительных остатков? | n/a | PASS; no applicable profile |
| `unknown` (1 turns) | Сколько метана из 9 кг другого органического сырья? | n/a | PASS; no applicable profile |
| `grass_litres` (1 turns) | Сколько метана из 20 литров травы? | n/a, n/a, n/a, n/a (6 separate profiles) | PASS; lallement2023-grass-1, lallement2023-grass-2, lallement2023-grass-3, lallement2023-grass-4, lallement2023-grass-5, lallement2023-grass-6 |
| `poultry_litres` (1 turns) | Сколько метана из 20 литров куриного помёта? | 1.6682, 0.76051 | PASS; eftaxias2024-poultry, ramos2019-layers-HD-sample1 |
| `food_grams` (1 turns) | Сколько метана из 500 граммов пищевых отходов? | 0.031814 | PASS; baek2020-food-pulp |
| `pig_tonnes` (1 turns) | Сколько метана из 0,1 тонны свиного навоза? | 0.47307, 0.25972 | PASS; eftaxias2024-pig, pham2013-pig-vdi |
| `addition` (2 turns) | У меня 5 кг пищевых отходов. Сколько метана? | 0.67308 | PASS; baek2020-food-pulp, eftaxias2024-poultry |
| `correction` (2 turns) | У меня 5 кг пищевых отходов. Сколько метана? | 0.19088 | PASS; baek2020-food-pulp |
| `temperature_context` (2 turns) | У меня 8 кг свиного навоза и реактор 100 литров. Сколько метана? | 0.037845, 0.020778 | PASS; eftaxias2024-pig, pham2013-pig-vdi |
| `dry_grass` (1 turns) | Сколько метана из 2 кг сухой травы? | n/a | PASS; no applicable profile |
| `compost` (1 turns) | Сколько метана из 5 кг компоста коровьего навоза? | n/a | PASS; no applicable profile |
| `mixture_unknown` (1 turns) | Смешай 2 кг пищевых отходов и 1 кг фруктовых отходов. Сколько метана? | 0.12726 | PASS; baek2020-food-pulp |

Key required cases: 48 L cattle slurry produced distinct sample scenarios (0.988-1.391 m3 and 0.876 m3; a profile without density/basis did not yield a number). For 58 kg grass, six paired samples remain separate rather than becoming a population interval. For 50 kg poultry manure, two study samples differ (8.874 and 4.045 m3). Food pulp at 5 kg gives 0.31814 m3 under the named laboratory profile. These are transferred BMP potentials, not plant gas-production forecasts.

An 80 L cattle-slurry charge against a 50 L vessel was marked physically infeasible. Adding 10 L water left the 5 kg food-feed potential unchanged. Comparing two 10 kg feeds kept them as separate alternatives. Adding 2 kg poultry manure preserved both components and calculated only an additive literature scenario; synergy is not predicted.

No complete compatible TS/VS/BMP profile was available for the tested vegetable waste, fruit waste, silage, whey, general plant residues, or unidentified organics. For grass expressed in litres, absent density prevented a mass and methane result. The model named missing data rather than inventing them.

Economics called the market/economic tools. The stored Karaganda electricity statistic was 20.39 KZT/kWh, published 2026-10-09 for a household electric-stove category. It was 34 days old at test time and marked stale/reference, not a plant tariff. Gross energy value was available; net profit/payback remained unknown where full costs and energy balance were missing. In the follow-up cost case, preparation 100 + transport 50 + maintenance 20 KZT were retained as a 170 KZT known subtotal; unspecified items remained unknown.

## Additional backend HTTP scenarios

20/20 additional HTTP checks passed: measured paired properties; g/kg conversion; volume with density range; working-volume overflow; possible overflow under a range; continuous HRT/OLR; batch versus daily OLR; target-TS water balance; inconsistent heated mass; full economic scenario; cost/tariff sensitivities; temperature heat demand; negative net energy; wet-gas incompatibility; incomplete TS/VS/BMP; compost transfer exclusion; VS greater than TS rejection; measured-only unknown material; and exact typed handoff to chat. Any numeric tariff, efficiency, or cost in these isolated validation fixtures was marked TEST ONLY and was not written to market history.

## Browser and CLI

Installed Chrome against the real local FastAPI build passed six checks: reactive calculation from the actual food profile; equality with direct API results; dilution changes without methane increase; economic input propagation with unknown costs retained; separate selection of six grass studies; and no horizontal overflow at 390 px. Browser JavaScript errors: 0. Screenshots: `reports/stage8_3/dashboard_food.png`, `dashboard_grass.png`, `dashboard_mobile.png`. `/health` and `/api/advisor/catalog` returned HTTP 200. Catalog: 15 materials, 18 approved scoped profiles. `python main.py --help` succeeded using the project-local `.deps`.

## Evidence and limits

Six separate grass records were added from Lallement et al. (2023), Appendix A, Table A1, DOI [10.3390/waste1010014](https://doi.org/10.3390/waste1010014). TS, VS, and BMP stay paired by sample; replicate SD is not treated as prediction coverage. Sample preparation/state is incompletely described for transfer to a user batch. The article prints gas pressure as ?1.013 hPa?; the unit is ambiguous, so the software does not silently correct it or claim a verified normalization factor.

No 90% interval was constructed. Additive mixture estimates do not model synergy or inhibition. Missing material profiles stay unavailable. Nominal vessel size cannot establish methane output, retention time, or safe operating charge. No live reactor sensors/actuators or validated batch-kinetics model are connected. Economic value depends on applicable current tariffs and complete measured energy/cost inputs.

Python suite: 433 passed, 2 pre-existing warnings. Frontend Vitest: 60 passed. TypeScript/Vite production build succeeded. Model hashes match the preserved stage 1 artifacts: `models/bmp.joblib` SHA256 `dbbf33f0eca4a5f43fa00feafe6fab9fd76778a0f1804e0bea66d363879b9c4f`; `models/stage1_5/bmp.joblib` SHA256 `eb1d88854c7b5a98410ee4ae8e6513ca17ee2aceb6f250ba9e9536aab90e793e`. Validation database: `evaluations/stage83_market_snapshot.sqlite3`.

Raw outputs: `reports/stage8_3/qwen_http.json`, `qwen_checks.json`, `http_additional.json`, `browser.json`.
