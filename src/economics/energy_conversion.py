"""One fuel stream: heat/electric alternatives and a constrained CHP balance."""
from src.economics.gas_composition import source_basis,compatible
from src.economics.decision_schemas import GasBasis

def pair(value):return {'low':value,'high':value}
def bounds(value):return {'low':value.low,'high':value.high} if hasattr(value,'low') else {k:value[k] for k in ['low','high']}
def multiply(a,b):return {'low':a['low']*b['low'],'high':a['high']*b['high']}
def scale(a,n):return {'low':a['low']*n,'high':a['high']*n}
def subtract(a,b):return {'low':a['low']-b['high'],'high':a['high']-b['low']}
def add(a,b):return {'low':a['low']+b['low'],'high':a['high']+b['high']}

def convert(methane,heating_value,recovery,thermal,electric,chp_thermal,chp_electric):
    for v in [recovery,thermal,electric,chp_thermal,chp_electric]:
        if not 0<=v['low']<=v['high']<=1:raise ValueError('Efficiency/recovery outside 0..1')
    if chp_thermal['high']+chp_electric['high']>1+1e-12:raise ValueError('CHP combined efficiency exceeds one')
    if heating_value<=0:raise ValueError('Heating value must be positive')
    fuel=scale(methane,heating_value);recovered=multiply(fuel,recovery)
    return {'potential_fuel_kwh':fuel,'recovered_fuel_kwh':recovered,
            'heat_only_kwh':multiply(recovered,thermal),'electricity_only_kwh':multiply(recovered,electric),
            'chp_heat_kwh':multiply(recovered,chp_thermal),'chp_electricity_kwh':multiply(recovered,chp_electric),
            'chp_unconverted_fuel_kwh':multiply(recovered,{'low':max(0,1-chp_thermal['high']-chp_electric['high']),'high':1-chp_thermal['low']-chp_electric['low']})}

def resolve(result,settings):
    names=['recovery_fraction','thermal_efficiency','electrical_efficiency','chp_thermal_efficiency','chp_electrical_efficiency']
    defaults={'recovery_fraction':{'low':.6,'high':.8},'thermal_efficiency':pair(.8),'electrical_efficiency':pair(.25),'chp_thermal_efficiency':pair(.45),'chp_electrical_efficiency':pair(.25)}
    parameters={};assumptions=[]
    for name in names:
        v=getattr(settings,name)
        if v is not None:parameters[name]=v.model_dump()
        elif settings.use_reference_scenarios:
            parameters[name]={**defaults[name],'provenance':'HYPOTHETICAL_SCENARIO','evidence':'Selected illustrative equipment/recovery scenario, not a device measurement'};assumptions.append(name)
    basis,why=source_basis(result,settings)
    default_hv=settings.heating_value_kwh_m3 is None
    heating_value=settings.heating_value_kwh_m3 if not default_hv else 9.97
    hvbasis=settings.heating_value_basis or (GasBasis(temperature_k=273.2,pressure_pa=101325,moisture='dry',description='FNR indicative LHV; compatible dry reference assumed') if default_hv and settings.use_reference_scenarios else None)
    assume=settings.assume_reference_compatibility or default_hv and settings.use_reference_scenarios
    compatible_basis,reason=compatible(basis,hvbasis,assume)
    outputs=convert(result['methane_potential_m3'],heating_value,*[bounds(parameters[k]) for k in names]) if result.get('methane_potential_m3') and len(parameters)==len(names) and compatible_basis else {}
    conditional=bool(assumptions or 'assumed' in reason or result.get('result_level')!='MEASURED' or any(p['provenance']!='MEASURED' for p in parameters.values()))
    return {'status':'conditional' if outputs and conditional else 'ok' if outputs else 'needs_input','outputs':outputs,'parameters':parameters,
            'heating_value':{'value':heating_value,'unit':'kWh/m3 CH4','type':settings.heating_value_type,'source':'FNR' if default_hv else settings.equipment_evidence or 'user input'},
            'gas_compatibility':reason if basis else why,'gas_basis':basis.model_dump() if basis else None,'assumed_parameters':assumptions,
            'result_level':'HYPOTHETICAL_SCENARIO' if conditional else 'MEASURED',
            'allocation_policy':'Heat-only, electricity-only and CHP are alternative allocations of one fuel stream. Only CHP heat and electricity may be valued together.',
            'uncertainty':'Sensitivity bounds, no independent probability or validated interval coverage.'}
