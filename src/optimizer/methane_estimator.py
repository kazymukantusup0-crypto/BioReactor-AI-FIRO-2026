"""Reuse the preserved model applicability gate and BMP-to-VS arithmetic."""
from src.agent.tools import predict_tool, get_model_info
from src.economics.calculator import calculate_methane


def estimate_methane(parameters):
    p = parameters.model_dump()
    warnings, missing = [], []
    mass = p.get('mass_kg')
    if mass is None and p.get('feedstock_volume_l') is not None and p.get('density_kg_l') is not None:
        mass = p['feedstock_volume_l'] * p['density_kg_l']
        p['mass_kg'] = mass
    vs = p.get('vs_mass_kg')
    if vs is None and mass is not None and p.get('vs_percent') is not None and p.get('vs_basis'):
        if p['vs_basis'] == 'fresh_mass':
            vs = mass * p['vs_percent'] / 100
        elif p.get('ts_percent') is not None:
            vs = mass * p['ts_percent'] / 100 * p['vs_percent'] / 100
        else:
            missing.append('ts_percent')
        if vs is not None and vs > 0:
            p['vs_mass_kg'] = vs
    if vs is None or vs <= 0:
        missing.append('vs_mass_kg')
    if p.get('mixture_components'):
        warnings.append('Mixture synergy and component BMP additivity are not validated; no mixture BMP model is applied.')
    if p.get('pretreatment'):
        warnings.append('No pretreatment effect on BMP is modeled.')
    bmp = p.get('bmp_ml_ch4_g_vs')
    source = p.get('bmp_provenance')
    model = None
    if bmp is None:
        if p.get('mixture_components') or p.get('pretreatment'):
            model = {'status': 'unsupported', 'model_called': False, 'message': 'Mixture or pretreatment transfer is unsupported; supply a matching measured BMP or explicit hypothesis.'}
        else:
            model = predict_tool(p)
        if model.get('status') == 'ok':
            bmp = model['bmp']
            p['bmp_ml_ch4_g_vs'] = bmp
            p['bmp_unit'] = 'mL CH4/g VS'
            source = 'MODEL_ESTIMATED'
            # The user must supply/verify gas conditions; model reference is not normalization.
        else:
            missing.append('applicable_measured_or_model_BMP')
            warnings.append(model.get('message', 'BMP model is not applicable.'))
    if p.get('gas_volume_basis') is None or not p['gas_volume_basis'].strip():
        missing.append('gas_volume_basis')
    if bmp is not None and vs is not None and vs > 0 and not missing:
        calculated = calculate_methane({key:value for key,value in p.items() if value is not None})
    else:
        calculated = {'status': 'needs_input', 'potential_methane_m3': None}
    potential = calculated.get('potential_methane_m3')
    recoverable = potential * p['recovery_fraction'] if potential is not None and p.get('recovery_fraction') is not None else None
    biogas = recoverable / p['methane_fraction'] if recoverable is not None and p.get('methane_fraction') is not None else None
    info = get_model_info(p['model']) if model and model.get('status') == 'ok' else None
    return {'status': calculated['status'], 'potential_methane_m3': potential,
            'recoverable_methane_scenario_m3': recoverable, 'raw_biogas_scenario_m3': biogas,
            'bmp_ml_ch4_g_vs': bmp, 'bmp_unit': p.get('bmp_unit'), 'bmp_provenance': source,
            'bmp_evidence': p.get('bmp_evidence'), 'vs_mass_kg': vs,
            'gas_volume_basis': p.get('gas_volume_basis'),
            'model_version': info['version'] if info else None, 'model_result': model,
            'missing': list(dict.fromkeys(missing)), 'warnings': warnings,
            'uncertainty_status': 'not_quantified_no_coverage_validated_interval',
            'limitations': ['BMP times VS is methane potential, not reactor productivity or measured production.',
                            'Recovery and methane fraction, if supplied, are explicit scenario inputs, not model predictions.',
                            'No temperature, HRT, OLR or pretreatment yield multiplier is used.',
                            'Measured BMP evidence and volume reference conditions are user assertions, not independently certified.'],
            'formula': 'BMP [mL CH4/g VS] * VS [kg] / 1000'}
