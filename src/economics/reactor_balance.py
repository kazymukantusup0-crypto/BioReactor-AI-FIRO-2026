"""Adapt the preserved v6 SI energy worksheet, adding separately named loads."""
import math
from src.optimizer.energy_model import estimate_energy

def calculate(inputs):
    p=inputs.model_dump();loads=[]
    for load in inputs.loads:
        kwh=load.power_w*load.hours*load.duty_fraction/1000
        loads.append({**load.model_dump(),'energy_kwh':kwh})
    subtotal=sum(v['energy_kwh'] for v in loads)
    if inputs.auxiliary_energy_kwh is not None and loads and inputs.loads_complete and not math.isclose(subtotal,inputs.auxiliary_energy_kwh,rel_tol=.01,abs_tol=1e-9):raise ValueError('Named loads and total auxiliary energy disagree')
    if inputs.auxiliary_energy_kwh is None and inputs.loads_complete:p['auxiliary_energy_kwh']=subtotal
    if p['heat_loss_coefficient_w_k'] is None and p['u_w_m2_k'] is not None and p['area_m2'] is not None:p['heat_loss_coefficient_w_k']=p['u_w_m2_k']*p['area_m2']
    result=estimate_energy(p)
    heating=(result['initial_heating_kwh']+result['maintenance_heating_kwh']) if result['initial_heating_kwh'] is not None and result['maintenance_heating_kwh'] is not None else None
    electricity=heating+result['auxiliary_kwh'] if inputs.heating_carrier=='electricity' and heating is not None and result['auxiliary_kwh'] is not None else result['auxiliary_kwh'] if inputs.heating_carrier in {'process_heat','external_heat'} else None
    return {**result,'heating_input_kwh':heating,'electricity_input_kwh':electricity,'heating_carrier':inputs.heating_carrier,
            'process_heat_draw_kwh':heating if inputs.heating_carrier=='process_heat' else 0 if inputs.heating_carrier in {'electricity','external_heat'} else None,
            'loads':loads,'known_load_subtotal_kwh':subtotal if loads else None,'input_provenance':inputs.provenance,
            'scope_valid_for_batch':inputs.energy_scope=='entire_batch',
            'warnings':result['warnings']+(['Continuous operation needs a matching production/time horizon; no automatic batch scaling.'] if inputs.operating_mode=='continuous' else [])}

def illustrative_cases(mass):
    if mass is None:return []
    from src.economics.decision_schemas import ReactorInputs
    rows=[]
    for ua in [.2,1.0]:
        p=ReactorInputs(temperature_c=35,initial_temperature_c=15,ambient_temperature_c=15,heated_mass_kg=mass,
            heat_capacity_kj_kg_k=4,heat_loss_coefficient_w_k=ua,duration_days=20,heater_efficiency=1,heating_carrier='electricity',
            loads_complete=True,loads=[{'name':'ILLUSTRATIVE mixing/pump/electronics total','power_w':1,'hours':480}],
            energy_scope='entire_batch',provenance='HYPOTHETICAL_SCENARIO')
        rows.append({'inputs':p.model_dump(),'result':calculate(p),'notice':'Illustration only: chosen 35/15°C, cp=4, 20 days, UA and 1 W are not measured reactor properties or prescribed operation. Heated mass excludes unreported inoculum/vessel mass. No 37°C laboratory setting was copied.'})
    return rows
