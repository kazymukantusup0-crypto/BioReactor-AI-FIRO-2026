"""Transparent Pareto fronts; incomplete or unequal-basis data are not ranked."""
import math

METRICS = {'methane': ('potential_methane_m3', 'max'), 'energy': ('total_energy_kwh', 'min'),
           'cost': ('processing_cost', 'min'), 'profit': ('net_profit', 'max'),
           'duration': ('total_duration_days', 'min'), 'uncertainty': ('uncertainty_score', 'min')}


def metrics(scenario):
    outputs = scenario.get('predicted_outputs', {})
    econ = outputs.get('economics', {})
    # A user must select a common economic route to compare process alternatives.
    route = scenario.get('input_parameters', {}).get('market', {}).get('comparison_route')
    # comparison_route is handled by v6, not passed to legacy ScenarioInput.
    row = next((r for r in econ.get('scenarios', []) if r.get('scenario') == route and r.get('status') == 'ok'), None)
    return {'potential_methane_m3': outputs.get('methane', {}).get('potential_methane_m3'),
            'total_energy_kwh': outputs.get('energy', {}).get('total_energy_kwh'),
            'processing_cost': row.get('total_cost') if row else None,
            'net_profit': row.get('net_profit') if row else None,
            'total_duration_days': outputs.get('batch_plan', {}).get('total_duration_days'),
            'uncertainty_score': None}


def compare_results(scenarios, objectives=None):
    objectives = objectives or []
    if set(objectives)-set(METRICS):
        raise ValueError('Unknown optimization objective')
    rows = [{'scenario_id': s.get('scenario_id'), 'label': s.get('label'),
             'feasibility_status': s.get('feasibility_status'), **metrics(s)} for s in scenarios]
    result = {'method': 'tradeoff_table', 'objectives': objectives, 'rows': rows,
              'pareto_fronts': [], 'recommended_scenario_id': None,
              'weights': None, 'ranking_status': 'INSUFFICIENT_DATA'}
    if len(scenarios) < 2:
        result['reason'] = 'At least two alternatives are needed for comparison.'
        return result
    if not objectives:
        result['reason'] = 'Choose objectives explicitly; no arbitrary weights or objective priorities are assigned.'
        return result
    if any(s.get('feasibility_status') in {'INFEASIBLE', 'INSUFFICIENT_DATA'} for s in scenarios):
        result['reason'] = 'One or more alternatives violate constraints or lack critical process inputs; show tradeoffs without ranking.'
        return result
    for key in ['material', 'mass_kg', 'feedstock_volume_l', 'gas_volume_basis', 'energy_scope']:
        values = [s.get('input_parameters', {}).get(key) for s in scenarios]
        if any(v != values[0] for v in values[1:]):
            result['reason'] = f'Alternatives have different {key}; a common comparison basis is required.'
            return result
    base = scenarios[0].get('input_parameters', {})
    if set(objectives) & {'cost','profit'}:
        markets=[s.get('input_parameters',{}).get('market',{}) for s in scenarios]
        for key in ['comparison_route','currency','region']:
            values=[m.get(key,'KZT' if key=='currency' else None) for m in markets]
            if any(value!=values[0] for value in values[1:]) or key=='comparison_route' and values[0] not in {'A','B','C','D'}:
                result['reason']='Economic comparisons require the same explicit route, currency and region.'
                return result
    if not base.get('material') or (base.get('mass_kg') is None and base.get('feedstock_volume_l') is None):
        result['reason'] = 'An explicit common material and quantity basis is required.'
        return result
    if any(not isinstance(row[METRICS[o][0]], (float, int)) or not math.isfinite(row[METRICS[o][0]]) for o in objectives for row in rows):
        result['reason'] = 'Some selected objectives are unknown. Uncertainty has no calibrated numeric score; missing values are not treated as zero.'
        return result
    vectors = [[row[METRICS[o][0]] * (-1 if METRICS[o][1] == 'max' else 1) for o in objectives] for row in rows]
    def dominates(a, b):
        return all(x <= y for x, y in zip(a, b)) and any(x < y for x, y in zip(a, b))
    remaining = set(range(len(rows)))
    while remaining:
        front = sorted(i for i in remaining if not any(dominates(vectors[j], vectors[i]) for j in remaining if j != i))
        result['pareto_fronts'].append([rows[i]['scenario_id'] for i in front])
        for i in front:
            rows[i]['pareto_rank'] = len(result['pareto_fronts'])
        remaining.difference_update(front)
    result.update(method='pareto_non_dominated_sort', ranking_status='CONDITIONAL',
                  reason='Pareto fronts under the entered assumptions and selected objectives; no unique operational optimum or weights are claimed.')
    return result
