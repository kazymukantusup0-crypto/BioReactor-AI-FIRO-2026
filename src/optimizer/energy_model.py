"""Sensible heat and steady heat-loss worksheet, without invented coefficients."""
import math

SOURCES = [
    {'title': 'US DOE Fundamentals Handbook, Thermodynamics, Heat Transfer, and Fluid Flow, Vol. 1',
     'url': 'https://www.energy.gov/documents/doe-hdbk-1012-92vol1',
     'year': 1992, 'scope': 'Sensible heat Q=m cp delta T; not a reactor-specific calibration'},
    {'title': 'PNNL Building Science: Introduction to Heat Flow',
     'url': 'https://basc.pnnl.gov/information/building-science-introduction-heat-flow',
     'scope': 'Steady heat-transfer relation UA delta T, not measured reactor heat loss'},
]


def estimate_energy(data):
    p = data.model_dump() if hasattr(data, 'model_dump') else dict(data)
    missing, warnings = [], []
    def needed(*keys):
        absent = [k for k in keys if p.get(k) is None]
        missing.extend(absent)
        return not absent
    target, initial, ambient = (p.get(k) for k in ['temperature_c', 'initial_temperature_c', 'ambient_temperature_c'])
    efficiency = p.get('heater_efficiency')
    sensible = initial_energy = holding = auxiliary = None
    cooling_required = False
    if needed('temperature_c', 'initial_temperature_c', 'heated_mass_kg', 'heat_capacity_kj_kg_k'):
        delta = target - initial
        sensible = p['heated_mass_kg'] * p['heat_capacity_kj_kg_k'] * max(0, delta) / 3600
        if delta < 0:
            cooling_required = True
            warnings.append('Initial cooling is required; no cooling energy or chiller efficiency was supplied.')
        if sensible == 0:
            initial_energy = 0.0
        elif needed('heater_efficiency'):
            initial_energy = sensible / efficiency
    ua = p.get('heat_loss_coefficient_w_k')
    if ua is None:
        missing.append('heat_loss_coefficient_w_k')
    elif ua == 0:
        holding = 0.0
    elif needed('temperature_c', 'ambient_temperature_c', 'duration_days'):
        if ambient > target:
            cooling_required = True
            warnings.append('Ambient temperature exceeds the target; cooling is not modeled.')
        heat = ua * max(0, target - ambient) * p['duration_days'] * 24 / 1000
        if heat == 0:
            holding = 0.0
        elif needed('heater_efficiency'):
            holding = heat / efficiency
    if p.get('auxiliary_energy_kwh') is not None:
        auxiliary = p['auxiliary_energy_kwh']
        if all(p.get(k) is not None for k in ['auxiliary_power_w', 'auxiliary_duty_fraction', 'duration_days']):
            check = p['auxiliary_power_w'] * p['auxiliary_duty_fraction'] * p['duration_days'] * 24 / 1000
            if not math.isclose(auxiliary, check, rel_tol=.01, abs_tol=1e-9):
                raise ValueError('Auxiliary power/duty/duration and explicit energy disagree')
    elif p.get('auxiliary_power_w') == 0:
        auxiliary = 0.0
    elif needed('auxiliary_power_w', 'auxiliary_duty_fraction', 'duration_days'):
        auxiliary = p['auxiliary_power_w'] * p['auxiliary_duty_fraction'] * p['duration_days'] * 24 / 1000
    if not p.get('energy_scope'):
        missing.append('energy_scope')
    known = [v for v in [initial_energy, holding, auxiliary] if v is not None]
    total = sum(known) if len(known) == 3 and not cooling_required and p.get('energy_scope') else None
    for value in [sensible, initial_energy, holding, auxiliary, total]:
        if value is not None and not math.isfinite(value):
            raise ValueError('Energy calculation overflow; check SI inputs')
    if p.get('heating_available') is False and any(v is not None and v > 0 for v in [initial_energy, holding]):
        warnings.append('Calculated heating demand cannot be met by the declared unavailable heater.')
    return {'status': 'ok' if total is not None else 'needs_input',
            'initial_thermal_kwh': sensible, 'initial_heating_kwh': initial_energy,
            'maintenance_heating_kwh': holding, 'auxiliary_kwh': auxiliary,
            'total_energy_kwh': total, 'known_subtotal_kwh': sum(known) if known else None,
            'cooling_required': cooling_required, 'missing': list(dict.fromkeys(missing)),
            'scope': p.get('energy_scope'), 'warnings': warnings,
            'formulas': {'initial_thermal_kwh': 'heated_mass_kg * cp_kJ_kg_K * max(T_target-T_initial,0) / 3600',
                         'initial_heating_kwh': 'initial_thermal_kwh / heater_efficiency',
                         'maintenance_heating_kwh': 'UA_W_K * max(T_target-T_ambient,0) * duration_days * 24 / 1000 / heater_efficiency',
                         'auxiliary_kwh': 'auxiliary_power_W * duty_fraction * duration_days * 24 / 1000, or explicit measured energy'},
            'limitations': ['Constant heat capacity; no phase change, evaporation, biological heat or heat recovery model.',
                            'UA and temperatures are user inputs; steady holding losses exclude startup transients.',
                            'Heated mass includes only the explicit input. Inoculum, water and vessel thermal mass must be included by the user.',
                            'Energy scope/duration is explicit; no automatic scaling from one charge to the entire feedstock lot.'],
            'scientific_sources': SOURCES}
