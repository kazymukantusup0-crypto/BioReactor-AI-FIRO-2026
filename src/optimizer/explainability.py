"""Traceable short explanations without undocumented optimization claims."""


def explain_optimization(result):
    scenarios = result.get('scenarios', [])
    insufficient = sum(s['feasibility_status'] == 'INSUFFICIENT_DATA' for s in scenarios)
    infeasible = sum(s['feasibility_status'] == 'INFEASIBLE' for s in scenarios)
    comparison = result.get('comparison', {})
    return {'summary': f'{len(scenarios)} alternatives studied; {insufficient} have critical missing inputs and {infeasible} violate declared constraints.',
            'ranking_explanation': comparison.get('reason'),
            'critical_missing': sorted({name for s in scenarios for name in s.get('critical_missing', [])}),
            'safety': 'Advisory calculations only. No actuator commands. Reactor operation needs engineering protection, pressure control, ventilation and gas safety.',
            'scientific_limit': 'Methane potential is distinct from actual conversion; higher temperature is not assumed to increase methane.'}
