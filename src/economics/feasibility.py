"""Reuse v6 constraints and expose single-charge geometry without an operating approval."""
from src.optimizer.schemas import ProcessParameters
from src.optimizer.constraints import analyze_constraints,plan_batches

def evaluate(request,reactor):
    data={k:v for k,v in reactor.model_dump().items() if k in ProcessParameters.model_fields and v is not None}
    data.update(material=request.material,feedstock_volume_l=request.volume_l,reactor_total_volume_l=request.reactor_total_volume_l)
    p=ProcessParameters.model_validate(data);existing=analyze_constraints(p)
    unknown=[k for k in ['reactor_working_volume_l','headspace_l','inoculum_volume_l','dilution_water_l','operating_mode','reactor_type'] if getattr(reactor,k) is None]
    violations=[r['message'] for r in existing['constraints'] if r['status']=='VIOLATED']
    components=[request.volume_l,reactor.inoculum_volume_l,reactor.dilution_water_l,reactor.resident_liquid_volume_l]
    known_charge=sum(x for x in components if x is not None)
    if reactor.operating_mode!='continuous' and reactor.reactor_working_volume_l is not None and known_charge>reactor.reactor_working_volume_l+1e-9:violations.append('Even the known simultaneous charge exceeds working liquid volume')
    if reactor.operating_mode!='continuous' and request.reactor_total_volume_l is not None and known_charge>request.reactor_total_volume_l+1e-9:violations.append('Known simultaneous liquid charge exceeds total vessel volume')
    if reactor.resident_liquid_volume_l is None:unknown.append('resident_liquid_volume_l')
    if reactor.operating_mode=='continuous':unknown.append('continuous_flow_and_production_time_plan')
    return {'status':'PHYSICALLY_INFEASIBLE' if violations else 'REQUIRES_SAFETY_REVIEW' if reactor.safety_review_required else 'UNKNOWN' if unknown else 'GEOMETRICALLY_CONSISTENT',
            'violations':violations,'unknown':unknown,'known_charge_min_l':known_charge if any(x is not None for x in components) else None,
            'headspace_l':reactor.headspace_l,'working_volume_l':reactor.reactor_working_volume_l,'total_volume_l':request.reactor_total_volume_l,
            'engineering_review_confirmed':reactor.engineering_review_confirmed,'operation_authorized':False,'existing_constraints':existing,
            'batch_plan':plan_batches(p),'scope':'One simultaneous charge only; serial processing can require a different plan. Geometric consistency is not a safety certification.'}
