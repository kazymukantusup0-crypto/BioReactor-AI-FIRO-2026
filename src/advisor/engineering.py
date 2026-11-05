"""Conservative, auditable batch geometry. No invented density or safe fill ratio."""
from src.advisor.mixing import pair, add, ratio


def evaluate(request, mixture):
    r=request.decision.reactor
    unknown=[]; known=pair(0);present=False
    for row in mixture['components']:
        if row['volume_l'] is None:unknown.append('volume_or_density:'+row['id'])
        else:known=add(known,row['volume_l']);present=True
    feed_known=dict(known)
    for key in ['inoculum_volume_l','dilution_water_l','resident_liquid_volume_l']:
        value=getattr(r,key)
        if value is None:unknown.append(key)
        else:known=add(known,pair(value));present=True
    total=request.reactor_total_volume_l;working=r.reactor_working_volume_l
    headspace=r.headspace_l
    violations=[];warnings=[]
    if total and working and working>total:violations.append('working_volume_exceeds_total')
    if total and working and headspace is not None and working+headspace>total:
        violations.append('working_volume_plus_headspace_exceeds_total')
    if r.operating_mode=='batch':
        for label,limit in [('total_volume',total),('working_volume',working),('headspace_limit',total-headspace if total and headspace is not None else None)]:
            if limit is None:continue
            if known['low']>limit:violations.append('known_charge_exceeds_'+label)
            elif known['high']>limit:warnings.append('possible_charge_exceeds_'+label)
    elif r.operating_mode=='continuous':warnings.append('feed_per_period_is_not_resident_charge; verify withdrawal and hydraulic flow')
    else:
        unknown.append('operating_mode')
        if total and known['low']>total:warnings.append('batch_loading_would_exceed_total_volume')
    if working is None:unknown.append('reactor_working_volume_l')
    if headspace is None:unknown.append('headspace_l')
    if total is None:unknown.append('reactor_total_volume_l')
    volume_missing=any(x.startswith('volume_or_density:') or x in {'inoculum_volume_l','dilution_water_l','resident_liquid_volume_l'} for x in unknown)
    charge=None if volume_missing else known
    remaining=None if total is None or charge is None else {'low':total-charge['high'],'high':total-charge['low']}
    mass=mixture['total_wet_mass_kg'];ts=mixture['total_ts_kg'];vs=mixture['total_vs_kg'];water=r.dilution_water_l
    diluted=add(mass,pair(water)) if mass and water is not None else None
    target=request.target_ts_fraction
    water_needed=None
    if target and mass and ts:
        water_needed={'low':max(0,ts['low']/target-mass['high']), 'high':max(0,ts['high']/target-mass['low'])}
    # Algebraic necessary condition, not an invented physical density. It makes
    # a mass-only batch useful while retaining all unresolved geometry inputs.
    unknown_feed_mass=None
    for row in mixture['components']:
        if row['volume_l'] is None and row['wet_mass_kg'] is not None:
            unknown_feed_mass=add(unknown_feed_mass,row['wet_mass_kg']) if unknown_feed_mass else dict(row['wet_mass_kg'])
    limits=[v for v in [total,working,total-headspace if total and headspace is not None else None] if v is not None]
    available=min(limits)-known['high'] if limits else None
    required_density=ratio(unknown_feed_mass,pair(available)) if unknown_feed_mass and available is not None and available>0 else None
    return {'status':'PHYSICALLY_INFEASIBLE' if violations else 'REQUIRES_REVIEW' if unknown or warnings else 'GEOMETRY_ONLY_CONSISTENT',
        'total_volume_l':total,'working_volume_l':working,'headspace_required_l':headspace,
        'known_feed_volume_l':feed_known,'known_charge_present':present,'known_charge_volume_l':known,'complete_charge_volume_l':charge,
        'remaining_total_volume_l':remaining,'fill_fraction':ratio(charge,pair(total)) if charge and total else None,
        'missing':unknown,'violations':violations,'warnings':warnings,
        'feed_plus_water_mass_kg':diluted,'feed_plus_water_ts_fraction':ratio(ts,diluted) if ts and diluted else None,
        'feed_plus_water_vs_fraction':ratio(vs,diluted) if vs and diluted else None,
        'additional_water_to_target_ts_kg':({'low':max(0,water_needed['low']-(water or 0)), 'high':max(0,water_needed['high']-(water or 0))} if water_needed else None),
        'target_ts_fraction':target,'water_density_assumption_kg_l':1 if water is not None else None,
        'necessary_mean_feed_density_kg_l':required_density,
        'density_constraint_scope':'Necessary mean density for the unvolumed feed to fit after known volumes only. Unmeasured inoculum/water still reduce capacity; this is not measured density or authorization to load.',
        'scope':'Separate volumes are additive bookkeeping, not a packing measurement. Dilution solids exclude inoculum/resident material: their TS/VS are unknown. Water density 1 kg/L is an explicit approximation. Target TS is user-selected, not an operating recommendation.',
        'operation_authorized':False}
