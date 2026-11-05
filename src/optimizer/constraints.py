"""Physical consistency, explicit user limits and missing engineering information."""
import math


def analyze_constraints(p, scientific=None, energy=None):
    rows = []
    def add(kind, parameter, status, message, **extra):
        rows.append({'kind': kind, 'parameter': parameter, 'status': status, 'message': message, **extra})
    for field in ['material', 'reactor_total_volume_l', 'reactor_working_volume_l', 'reactor_type',
                  'operating_mode', 'inoculum_description', 'gas_storage_conditions']:
        if getattr(p, field) is None:
            add('UNKNOWN', field, 'UNKNOWN', f'{field} is not supplied; no operating approval is inferred.')
    total, working = p.reactor_total_volume_l, p.reactor_working_volume_l
    if total is not None and working is not None:
        add('HARD_CONSTRAINT', 'reactor_working_volume_l', 'VIOLATED' if working > total else 'SATISFIED',
            'Working liquid volume must not exceed total vessel volume.')
    if total is not None and working is not None and p.headspace_l is not None:
        add('HARD_CONSTRAINT', 'headspace_l', 'VIOLATED' if working + p.headspace_l > total + 1e-9 else 'SATISFIED',
            'Working liquid plus declared headspace must fit inside total volume; headspace is not gas-storage capacity.')
    if working is not None and p.liquid_charge_volume_l is not None:
        add('HARD_CONSTRAINT', 'liquid_charge_volume_l', 'VIOLATED' if p.liquid_charge_volume_l > working else 'SATISFIED',
            'Explicit simultaneous liquid charge cannot exceed working volume.')
    if p.feedstock_volume_l is not None and total is not None and p.feedstock_volume_l > total:
        add('HARD_CONSTRAINT', 'feedstock_volume_l', 'PLANNING_REQUIRED',
            'The feedstock lot cannot be charged simultaneously into this vessel. This alone does not make staged processing infeasible.')
    if working is not None and all(v is not None for v in [p.inoculum_volume_l, p.dilution_water_l, p.resident_liquid_volume_l]):
        available = working-p.inoculum_volume_l-p.dilution_water_l-p.resident_liquid_volume_l
        add('HARD_CONSTRAINT', 'charge_occupancy', 'VIOLATED' if available <= 0 else 'SATISFIED',
            'Feedstock, inoculum, dilution and resident liquid share the working volume.', feedstock_capacity_l=available)
    if p.heating_available is False:
        heating = ((p.temperature_c is not None and p.initial_temperature_c is not None and p.temperature_c > p.initial_temperature_c)
                   or (energy and energy.get('maintenance_heating_kwh') is not None and energy['maintenance_heating_kwh'] > 0))
        add('HARD_CONSTRAINT', 'heating_available', 'VIOLATED' if heating else 'UNKNOWN',
            'A positive heating demand needs an available heat source; no heater command is generated.')
    if p.operating_mode == 'batch' and p.hrt_days is not None:
        add('HARD_CONSTRAINT', 'hrt_days', 'NOT_APPLICABLE',
            'Continuous-flow hydraulic retention time is not substituted for batch cycle duration.')
    derived = {}
    if p.operating_mode == 'continuous' and working is not None:
        if p.daily_feed_volume_l is not None:
            derived['hydraulic_retention_days'] = working/p.daily_feed_volume_l
            add('SCENARIO_ASSUMPTION', 'daily_feed_volume_l', 'CONDITIONAL',
                'For the HRT calculation, daily_feed_volume_l must be total daily liquid inflow, including dilution and inoculum streams.')
            if p.hrt_days is not None:
                add('HARD_CONSTRAINT', 'hrt_days', 'SATISFIED' if math.isclose(p.hrt_days, derived['hydraulic_retention_days'], rel_tol=.01) else 'VIOLATED',
                    'Declared HRT must match working volume / total daily liquid inflow within 1%.')
        if p.daily_vs_mass_kg is not None:
            derived['olr_kg_vs_m3_day'] = p.daily_vs_mass_kg/(working/1000)
            if p.olr_kg_vs_m3_day is not None:
                add('HARD_CONSTRAINT', 'olr_kg_vs_m3_day', 'SATISFIED' if math.isclose(p.olr_kg_vs_m3_day, derived['olr_kg_vs_m3_day'], rel_tol=.01, abs_tol=1e-9) else 'VIOLATED',
                    'OLR must match daily VS loading / working volume within 1%.')
    for field in ['ts_percent', 'vs_percent', 'ph', 'temperature_c', 'hrt_days', 'olr_kg_vs_m3_day']:
        if getattr(p, field) is None:
            add('UNKNOWN', field, 'UNKNOWN', 'No universal literature value is substituted for the missing measurement.')
    if scientific:
        for claim in scientific.get('claims', []):
            if claim['values']:
                add('EVIDENCE_BASED_RANGE', claim['id'], 'REFERENCE_ONLY', claim['scope'],
                    values=claim['values'], unit=claim['unit'], source_id=claim['source_id'])
    for key, value in p.assumptions.items():
        add('SCENARIO_ASSUMPTION', key, 'CONDITIONAL', 'Explicit scenario assumption; not a measured fact.', value=value)
    checks = {'temperature_min_c': (p.temperature_c, 'min'), 'temperature_max_c': (p.temperature_c, 'max'),
              'energy_max_kwh': ((energy or {}).get('total_energy_kwh'), 'max')}
    for key, limit in p.user_limits.items():
        if key not in checks:
            continue
        actual, direction = checks[key]
        status = 'UNKNOWN' if actual is None else 'VIOLATED' if (actual < limit if direction == 'min' else actual > limit) else 'SATISFIED'
        add('USER_DEFINED_LIMIT', key, status, 'Explicit user limit; not a universal biological threshold.', limit=limit, actual=actual)
    critical = [r['parameter'] for r in rows if r['kind'] == 'UNKNOWN' and r['parameter'] in
                {'material', 'reactor_total_volume_l', 'reactor_working_volume_l', 'reactor_type', 'operating_mode', 'inoculum_description', 'gas_storage_conditions'}]
    critical += [r['parameter'] for r in rows if r['kind']=='USER_DEFINED_LIMIT' and r['status']=='UNKNOWN']
    violated = any(r['status'] == 'VIOLATED' for r in rows)
    return {'constraints': rows, 'critical_missing': critical, 'derived': derived,
            'feasibility_status': 'INFEASIBLE' if violated else 'INSUFFICIENT_DATA' if critical else 'CONDITIONAL',
            'status_scope': 'Consistency and information availability only; not engineering safety certification.'}


def plan_batches(p):
    required = ['feedstock_volume_l', 'reactor_working_volume_l', 'operating_mode', 'reactor_type',
                'inoculum_volume_l', 'dilution_water_l', 'resident_liquid_volume_l']
    missing = [k for k in required if getattr(p, k) is None]
    if p.operating_mode == 'continuous':
        return {'status': 'not_applicable', 'batch_count': None, 'total_duration_days': None,
                'missing': [], 'message': 'Continuous feed requires a flow/retention plan; no batch count is generated.'}
    if missing:
        return {'status': 'needs_input', 'batch_count': None, 'total_duration_days': None, 'missing': missing,
                'message': 'Need working volume, loading mode, reactor type and explicit occupancy before assigning batches.'}
    capacity = p.reactor_working_volume_l-p.inoculum_volume_l-p.dilution_water_l-p.resident_liquid_volume_l
    if capacity <= 0 or (p.reactor_total_volume_l is not None and p.reactor_working_volume_l > p.reactor_total_volume_l):
        return {'status': 'infeasible', 'batch_count': None, 'total_duration_days': None, 'missing': [],
                'message': 'Declared charge allocation exceeds vessel capacity.'}
    count = math.ceil(p.feedstock_volume_l/capacity)
    last = p.feedstock_volume_l-(count-1)*capacity
    duration = count*p.batch_duration_days+(count-1)*p.turnaround_days if p.batch_duration_days is not None and p.turnaround_days is not None else None
    missing = [k for k in ['batch_duration_days', 'turnaround_days'] if getattr(p, k) is None]
    return {'status': 'ok' if duration is not None else 'partial', 'batch_count': count,
            'feedstock_capacity_per_batch_l': capacity, 'last_feedstock_charge_l': last,
            'total_duration_days': duration, 'missing': missing,
            'formula': 'capacity = working - inoculum - dilution - resident liquid; count = ceil(feedstock/capacity)',
            'assumptions': ['Serial charges in one reactor with the entered occupancy for each charge.',
                            'Turnaround occurs only between charges; no initial setup/final cleanout time is included.',
                            'This is a volume/time worksheet, not proof of microbial stability, safe loading or achieved conversion.'],
            'message': 'Batch allocation uses explicit occupancy; no percentage of total reactor volume was assumed.'}
