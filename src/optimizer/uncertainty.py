"""Deterministic one-factor sensitivity, never probabilistic uncertainty intervals."""
from src.optimizer.schemas import ProcessParameters


def evaluate_sensitivity(scenario_rows, ranges, evaluate):
    rows = []
    for scenario in scenario_rows:
        base = scenario['input_parameters']
        for interval in ranges:
            outcomes = []
            for value in [interval.low, interval.high]:
                try:
                    if interval.parameter in {'electricity_price', 'feedstock_price'}:
                        role = 'electricity' if interval.parameter == 'electricity_price' else 'feedstock'
                        econ = scenario['predicted_outputs']['economics']
                        measured = econ.get('selected_prices', {}).get(role)
                        if measured is None:
                            outcomes.append({})
                            continue
                        original = float(measured['normalized_value'])
                        values = {}
                        for ledger in econ.get('scenarios', []):
                            if ledger.get('status') != 'ok':
                                continue
                            if ledger['scenario'] == 'A':
                                slope = ledger.get('price_slope', 0) if role == 'feedstock' else 0
                            elif role == 'feedstock':
                                slope = 0
                            elif ledger['scenario'] == 'B':
                                slope = ledger.get('price_slope', 0)
                            else:
                                slope = -base['market'].get('energy_use_kwh', scenario['predicted_outputs']['energy'].get('total_energy_kwh') or 0)
                            values[f"net_profit_{ledger['scenario']}"] = ledger['net_profit']+(value-original)*slope
                        outcomes.append(values)
                        continue
                    modified = dict(base)
                    modified['assumptions'] = {**modified.get('assumptions', {}), interval.parameter: {
                        'value': value, 'provenance': 'SCENARIO_ASSUMPTION', 'evidence': interval.evidence}}
                    if interval.parameter == 'operating_cost':
                        modified['market'] = {**modified['market'], 'operating_cost': value}
                    else:
                        modified[interval.parameter] = value
                    if interval.parameter == 'bmp_ml_ch4_g_vs':
                        modified.update(bmp_provenance='scenario_assumption', bmp_evidence=interval.evidence, bmp_unit='mL CH4/g VS')
                    evaluated = evaluate(ProcessParameters.model_validate(modified))
                    outputs = evaluated['predicted_outputs']
                    values = {'potential_methane_m3': outputs['methane'].get('potential_methane_m3'),
                              'total_energy_kwh': outputs['energy'].get('total_energy_kwh')}
                    for ledger in outputs['economics'].get('scenarios', []):
                        if ledger.get('status') == 'ok':
                            values[f"net_profit_{ledger['scenario']}"] = ledger['net_profit']
                    outcomes.append(values)
                except (ValueError, TypeError):
                    outcomes.append({})
            common = set(outcomes[0]) & set(outcomes[1])
            outputs = {name: {'low': outcomes[0][name], 'high': outcomes[1][name],
                               'span': abs(outcomes[1][name]-outcomes[0][name])}
                       for name in sorted(common) if all(isinstance(o[name], (int, float)) for o in outcomes)}
            rows.append({'scenario_id': scenario['scenario_id'], 'parameter': interval.parameter,
                         'low': interval.low, 'high': interval.high, 'provenance': interval.provenance,
                         'evidence': interval.evidence, 'source_url': interval.source_url, 'outputs': outputs,
                         'status': 'CONDITIONAL' if outputs else 'INSUFFICIENT_DATA',
                         'method': 'One parameter at a time; endpoint sensitivity, not a probability interval or forecast.'})
    influence = {}
    for row in rows:
        for metric, values in row['outputs'].items():
            influence.setdefault(metric, []).append({'scenario_id': row['scenario_id'], 'parameter': row['parameter'], 'absolute_span': values['span']})
    for values in influence.values():
        values.sort(key=lambda r: r['absolute_span'], reverse=True)
    return {'rows': rows, 'influence_by_output': influence,
            'uncertainty_status': 'not_quantified_no_calibrated_probability_distribution',
            'limitations': ['Endpoint effects are compared within each output unit; no cross-unit importance score.',
                            'User/source ranges are scenario boundaries, not empirically calibrated confidence intervals.',
                            'Correlations, process kinetics and interactions are not estimated.',
                            'Temperature affects only the explicit thermal worksheet; no temperature-to-BMP response is inferred.']}
