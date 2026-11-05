"""Compose preserved model/market services into reproducible advisory scenarios."""
import hashlib
import json
from src.optimizer.schemas import ProcessRequest
from src.optimizer.scenario_generator import generate_scenarios
from src.optimizer.scientific_conditions import scientific_conditions
from src.optimizer.constraints import analyze_constraints, plan_batches
from src.optimizer.energy_model import estimate_energy
from src.optimizer.methane_estimator import estimate_methane
from src.optimizer.economic_optimizer import evaluate_economics
from src.optimizer.ranking import compare_results
from src.optimizer.uncertainty import evaluate_sensitivity
from src.optimizer.explainability import explain_optimization


def evaluate_scenario(store, parameters):
    scientific = scientific_conditions(parameters)
    energy = estimate_energy(parameters)
    methane = estimate_methane(parameters)
    constraints = analyze_constraints(parameters, scientific, energy)
    batches = plan_batches(parameters)
    economics = evaluate_economics(store, parameters, methane, energy)
    warnings = list(dict.fromkeys([*energy.get('warnings', []), *methane.get('warnings', []), *economics.get('warnings', [])]))
    if parameters.temperature_c is not None:
        warnings.append('Target temperature is an entered or literature-study condition, not a validated optimum or equipment command.')
    if parameters.gas_storage_conditions is None:
        warnings.append('Gas containment/ventilation/pressure protections have not been assessed. No operation approval is given.')
    if parameters.assumptions:
        warnings.append('Scenario assumptions remain separate from user measurements.')
    for key, metric in [('duration_max_days', batches.get('total_duration_days')),
                        ('cost_max', next((r['total_cost'] for r in economics.get('scenarios', [])
                                          if r.get('scenario') == parameters.market.get('comparison_route') and r.get('status') == 'ok'), None))]:
        if key in parameters.user_limits:
            constraints['constraints'].append({'kind': 'USER_DEFINED_LIMIT', 'parameter': key,
                'status': 'UNKNOWN' if metric is None else 'VIOLATED' if metric > parameters.user_limits[key] else 'SATISFIED',
                'limit': parameters.user_limits[key], 'actual': metric, 'message': 'Explicit scenario limit.'})
    if any(c['status'] == 'VIOLATED' for c in constraints['constraints']):
        constraints['feasibility_status'] = 'INFEASIBLE'
        warnings.append('Numerical worksheets are counterfactual only because a declared constraint is violated; they are not executable plans.')
    constraints['critical_missing']=list(dict.fromkeys(constraints['critical_missing']+[c['parameter'] for c in constraints['constraints'] if c['kind']=='USER_DEFINED_LIMIT' and c['status']=='UNKNOWN']))
    if constraints['critical_missing'] and constraints['feasibility_status']!='INFEASIBLE':
        constraints['feasibility_status']='INSUFFICIENT_DATA'
    if constraints['feasibility_status'] in {'INFEASIBLE','INSUFFICIENT_DATA'}:
        economics['final_recommendation']=None
        economics['is_final_recommendation']=False
    body = parameters.model_dump(mode='json')
    identifier = hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()[:20]
    return {'scenario_id': identifier, 'label': '', 'input_parameters': body,
            'assumptions': parameters.assumptions, 'scientific_sources': scientific['scientific_sources'],
            'constraints': constraints['constraints'], 'critical_missing': constraints['critical_missing'],
            'feasibility_status': constraints['feasibility_status'],
            'predicted_outputs': {'methane': methane, 'energy': energy, 'economics': economics, 'batch_plan': batches,
                                  'derived_process_values': constraints['derived']},
            'uncertainty_status': 'not_quantified_no_coverage_validated_interval', 'warnings': warnings}


def optimize(store, request):
    request = request if isinstance(request, ProcessRequest) else ProcessRequest.model_validate(request)
    if store is None:
        from src.market.service import get_store
        store = get_store()
    scenarios = []
    for generated in generate_scenarios(request):
        row = evaluate_scenario(store, generated['parameters'])
        row['label'] = generated['label']
        row['rationale'] = generated['rationale']
        scenarios.append(row)
    comparison = compare_results(scenarios, request.objectives)
    sensitivity = evaluate_sensitivity(scenarios, request.sensitivity, lambda p: evaluate_scenario(store, p))
    sources = {s['url']: s for row in scenarios for s in row['scientific_sources']}
    for row in scenarios:
        for source in row['predicted_outputs']['energy']['scientific_sources']:
            sources[source['url']] = source
    result = {'version': '6.0', 'label': request.label, 'scenarios': scenarios,
              'comparison': comparison, 'sensitivity': sensitivity,
              'scientific_sources': list(sources.values()), 'actuator_access': False,
              'status_scope': 'VERIFIED means input/arithmetic checks only if used; no scenario receives an operating or safety certification.',
              'models_retrained': False, 'final_recommendation': None}
    result['explanation'] = explain_optimization(result)
    json.dumps(result, allow_nan=False)
    return result
