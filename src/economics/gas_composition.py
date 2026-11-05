"""Gas composition arithmetic requires comparable dry/wet and volume references."""
import math
from src.economics.decision_schemas import GasBasis

def compatible(a,b,assume_unknown=False):
    if a is None or b is None:return False,'missing_gas_basis'
    a=a.model_dump() if hasattr(a,'model_dump') else a;b=b.model_dump() if hasattr(b,'model_dump') else b
    if not math.isclose(a['temperature_k'],b['temperature_k'],rel_tol=1e-6) or not math.isclose(a['pressure_pa'],b['pressure_pa'],rel_tol=1e-6):return False,'incompatible_temperature_or_pressure'
    if 'unknown' in {a['moisture'],b['moisture']}:
        return (True,'assumed_moisture_compatibility') if assume_unknown else (False,'unknown_gas_moisture_basis')
    return (True,'matched') if a['moisture']==b['moisture'] else (False,'wet_dry_mismatch')

def source_basis(result,settings):
    if result.get('structured_gas_basis'):
        original=GasBasis.model_validate(result['structured_gas_basis'])
        if settings.gas_basis:
            ok,reason=compatible(original,settings.gas_basis,settings.assume_reference_compatibility)
            if not ok:return None,reason
        return original,'Structured gas reference supplied with component calculation'
    if result.get('gas_reference')=='273.2 K; 1.01325 bar':
        original=GasBasis(temperature_k=273.2,pressure_pa=101325,moisture='unknown',description=result['gas_reference'])
        if settings.gas_basis:
            ok,reason=compatible(original,settings.gas_basis,settings.assume_reference_compatibility)
            if not ok:return None,reason
        return original,'RM1 gas moisture unspecified'
    if result.get('gas_reference') and settings.gas_basis:return settings.gas_basis,'User-declared measured BMP gas basis'
    return None,'missing_documented_BMP_gas_basis'

def biogas_volume(methane,fraction):
    if not 0<fraction['low']<=fraction['high']<=1:raise ValueError('Invalid methane fraction')
    return {'low':methane['low']/fraction['high'],'high':methane['high']/fraction['low']}

def resolve(result,request,settings):
    basis,reason=source_basis(result,settings)
    fraction=settings.methane_fraction
    preset=fraction is None and settings.use_reference_scenarios and request.material=='cattle_manure' and request.material_state in {'slurry','unknown'}
    if preset:
        fraction={'low':.55,'high':.60,'provenance':'HYPOTHETICAL_SCENARIO','evidence':'FNR cattle-slurry references 55% (2024) and 60% (2006); cross-reference sensitivity, not same sample'}
    elif fraction is not None:fraction=fraction.model_dump()
    scenario_fraction=bool(fraction and fraction.get('provenance')=='HYPOTHETICAL_SCENARIO' and settings.use_reference_scenarios)
    assume=settings.assume_reference_compatibility or preset or scenario_fraction
    cb=settings.composition_basis or (basis if preset or scenario_fraction else None)
    ok,why=compatible(basis,cb,assume)
    volume=biogas_volume(result['methane_potential_m3'],fraction) if result.get('methane_potential_m3') and fraction and ok else None
    levels={result.get('result_level'),fraction.get('provenance') if fraction else None}
    level='HYPOTHETICAL_SCENARIO' if preset or 'assumed' in why or 'HYPOTHETICAL_SCENARIO' in levels or 'USER_REPORTED' in levels else 'LITERATURE_ESTIMATE' if 'LITERATURE_ESTIMATE' in levels else 'MEASURED'
    return {'potential_biogas_m3':volume,'methane_fraction':fraction,'gas_basis':basis.model_dump() if basis else None,
            'status':'conditional' if volume and (preset or 'assumed' in why) else 'ok' if volume else 'needs_input',
            'result_level':level if volume else None,
            'compatibility':why if basis else reason,'assumptions':['CH4 and total biogas at identical temperature, pressure and moisture basis assumed'] if volume and (preset or 'assumed' in why) else [],
            'scope':'Potential gas corresponding to laboratory methane potential, not collected plant gas. CH4 is part of biogas and must not be added again.',
            'uncertainty':'Independent extrema envelope; unknown correlation and no validated probability coverage.'}
