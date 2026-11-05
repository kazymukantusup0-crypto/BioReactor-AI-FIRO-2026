# Recorded Qwen3 8B checks

| Case | Passed | Seconds | Actual tools | Failed checks |
|---|---|---|---|---|
| 01_batch | True | 95.61615979997441 | assess_substrate_potential:ok, evaluate_partial_economics:ok |  |
| 02_batch | True | 49.39986780000618 | assess_substrate_potential:ok, evaluate_partial_economics:ok |  |
| 03_batch | True | 90.24590909999097 | assess_substrate_potential:ok, evaluate_partial_economics:ok, search_substrate_profiles:ok, calculate_dilution_plan:ok |  |
| 04_batch | True | 100.23869859997649 | assess_substrate_potential:ok, evaluate_partial_economics:ok, search_substrate_profiles:ok, calculate_dilution_plan:ok |  |
| 05_batch | True | 58.43475920002675 | assess_substrate_potential:ok, evaluate_partial_economics:ok, assess_scientific_risks:ok, calculate_dilution_plan:ok |  |
| 06_batch | True | 120.09255709999707 | assess_substrate_potential:ok, search_substrate_profiles:ok, advise_substrate_conditions:ok, calculate_dilution_plan:ok |  |
| 07_batch | True | 120.08390849997522 | assess_process_evidence:ok, search_substrate_profiles:ok, assess_scientific_risks:ok |  |
| 08_batch | True | 120.04855409997981 | assess_substrate_potential:ok, assess_process_evidence:ok, verify_scientific_sources:ok |  |
| 09_batch | True | 93.31270960002439 | assess_process_evidence:ok, search_substrate_profiles:ok, verify_scientific_sources:ok, compare_scientific_studies:ok |  |
| 10_batch | True | 120.06193090003217 | assess_substrate_potential:ok, assess_process_evidence:ok, assess_scientific_risks:ok, calculate_dilution_plan:ok |  |
| 11_dry | True | 120.05312450003112 | assess_substrate_potential:needs_input, search_substrate_profiles:ok, assess_scientific_risks:ok, compare_scientific_studies:ok |  |
| 12_pig | True | 66.14672869996866 | assess_substrate_potential:ok, search_substrate_profiles:ok |  |
| 13_pig | True | 60.18025959999068 | assess_substrate_potential:ok, search_substrate_profiles:ok |  |
| 14_compare | True | 120.11951250000857 | assess_substrate_potential:ok, evaluate_partial_economics:ok |  |
| 15_mixture | True | 66.9121769000194 | assess_substrate_potential:ok, calculate_dilution_plan:ok |  |
| 16_mixture | True | 48.53465560002951 | assess_substrate_potential:ok |  |
| 17_mixture | True | 104.79043120000279 | assess_scientific_risks:ok, assess_substrate_potential:ok, search_substrate_profiles:ok, compare_scientific_studies:ok |  |
| 18_cattle | True | 97.25849590002326 | assess_substrate_potential:ok, assess_scientific_risks:ok, calculate_dilution_plan:ok, search_substrate_profiles:ok |  |
| 19_sheep | True | 70.68098599999212 | assess_substrate_potential:ok, calculate_dilution_plan:ok |  |
| 20_goat | True | 29.565950499963947 | assess_substrate_potential:ok |  |
| 21_horse | True | 120.09767699998338 | estimate_advanced_gas:ok, search_substrate_profiles:ok, analyze_substrate_mixture:ok |  |
| 22_straw | True | 80.67000610003015 | assess_substrate_potential:ok, calculate_dilution_plan:ok, assess_scientific_risks:ok |  |
| 23_grass | True | 120.1244462999748 | assess_substrate_potential:ok, assess_scientific_risks:ok |  |
| 24_unknown | True | 120.10354940005345 | assess_substrate_potential:needs_input, search_substrate_profiles:ok, assess_scientific_risks:ok, verify_scientific_sources:ok |  |
| 25_plastic | True | 25.496156300010625 | assess_substrate_potential:needs_input, search_substrate_profiles:ok, verify_scientific_calculations:ok, assess_scientific_risks:ok |  |
| 26_small | True | 21.92198789998656 | assess_substrate_potential:ok, assess_scientific_risks:ok, calculate_dilution_plan:ok, search_substrate_profiles:ok |  |
| 27_volume | True | 21.765563900000416 | assess_substrate_potential:ok, assess_scientific_risks:ok, calculate_dilution_plan:ok |  |
| 28_water | True | 52.01350000000093 | assess_substrate_potential:ok, assess_process_evidence:ok, calculate_dilution_plan:ok, assess_scientific_risks:ok |  |
| 29_heat | True | 117.98064690001775 | assess_process_evidence:ok, search_substrate_profiles:ok, assess_scientific_risks:ok, verify_scientific_sources:ok |  |
| 30_heat | True | 120.13751030003186 | assess_substrate_potential:ok, assess_process_evidence:ok, evaluate_partial_economics:ok |  |
| 31_money | True | 120.0970167000196 | assess_substrate_potential:ok, evaluate_partial_economics:ok, assess_scientific_risks:ok |  |
| 32_money | True | 120.12271409999812 | assess_substrate_potential:ok, evaluate_partial_economics:ok, search_substrate_profiles:ok |  |
| 33_sources | True | 120.13185399997747 | assess_substrate_potential:ok, compare_scientific_studies:ok |  |
| 34_sources | True | 101.56239969999297 | assess_substrate_potential:ok |  |
| 35_limits | True | 115.2025117999874 | search_substrate_profiles:ok, assess_scientific_risks:ok, verify_scientific_sources:ok |  |
| 36_density | True | 120.08929299999727 | assess_substrate_potential:ok, assess_scientific_risks:ok, calculate_dilution_plan:ok |  |
| 37_density | True | 120.08132169995224 | assess_substrate_potential:ok, assess_scientific_risks:ok, verify_scientific_sources:ok, search_scientific_sources:ok |  |
| 38_clarify | True | 120.09156560001429 | analyze_substrate:ok, research_scientific_evidence:ok, get_substrate_catalog:ok, research_and_estimate:needs_input |  |
| 39_clarify | True | 84.59558059996925 | assess_substrate_potential:ok, assess_scientific_risks:ok, calculate_dilution_plan:ok |  |
| 40_noactuator | True | 120.08963499998208 | analyze_substrate:ok, assess_substrate_potential:ok, assess_scientific_risks:ok, calculate_dilution_plan:ok |  |
| 41_fault_or_budget | True | 120.1389063000097 | assess_substrate_potential:error, recover_local_scientific_analysis:ok, evaluate_partial_economics:ok, assess_scientific_risks:ok |  |
| 42_fault_or_budget | True | 113.75508109998191 | assess_substrate_potential:ok, evaluate_partial_economics:error, recover_partial_economics:ok |  |
| 43_fault_or_budget | True | 66.22397270001238 | assess_substrate_potential:ok |  |
| 44_fault_or_budget | True | 1.037111800047569 |  |  |
