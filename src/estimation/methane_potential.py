from src.estimation.evidence_selector import select
from src.estimation.substrate_properties import resolve
from src.estimation.scenario_ranges import multiply,scale,sensitivity
from src.estimation.uncertainty import NOTICE
from src.estimation.result_validator import validate
from src.research.citation_manager import citations

def estimate(request,profiles,energy_reference):
    profile=select(profiles,request)
    mass,vs,bmp,inputs,assumptions=resolve(request,profile)
    literature=bool(assumptions)
    level='HYPOTHETICAL_SCENARIO' if literature and request.material_state=='unknown' else 'LITERATURE_ESTIMATE' if literature else 'MEASURED'
    warnings=[NOTICE,'Laboratory methane potential is not actual plant gas production.']
    if literature and request.material_state=='unknown':assumptions.append('Material is comparable to untreated cattle slurry RM1; actual form/moisture unknown')
    if request.reactor_total_volume_l:warnings.append('Total vessel volume does not establish working volume, headspace, inoculum or dilution capacity.')
    if request.bmp_ml_g_vs is not None and not request.gas_reference:warnings.append('User BMP gas reference is missing; reference-conditioned energy is unavailable.')
    result={'status':'ok','result_level':level,'material':request.material,'material_state':request.material_state,'profile_id':profile['id'] if literature and profile else None,
            'wet_mass_kg':mass,'vs_mass_kg':vs,'inputs':inputs,'assumptions':assumptions,'warnings':warnings,
            'methane_potential_l':None,'methane_potential_m3':None,'raw_biogas_m3':None,'fuel_energy_kwh':None,
            'gas_sale_revenue':None,'net_profit':None,'final_recommendation':None,'missing':[],
            'sources':citations(profile,energy_reference) if literature and profile else [],'uncertainty_status':NOTICE,
            'gas_reference':request.gas_reference if request.bmp_ml_g_vs is not None else profile['conditions']['gas_reference'] if profile else None,
            'gas_moisture_basis':profile['conditions']['gas_moisture_basis'] if profile and request.bmp_ml_g_vs is None else 'user reference; verify moisture basis'}
    if mass is None and vs is None:result['missing'].append('wet_mass_or_volume_and_compatible_density')
    if vs is None:result['missing'].append('VS_mass_or_compatible_TS_VS')
    if bmp is None:result['missing'].append('measured_BMP_or_compatible_reviewed_profile')
    if not vs or not bmp:result.update(status='needs_input',result_level=None);return validate(result)
    litres=multiply(vs,bmp);result.update(methane_potential_l=litres,methane_potential_m3=scale(litres,.001),sensitivity=sensitivity(vs,bmp))
    if request.methane_fraction is not None:result['raw_biogas_m3']=scale(litres,.001/request.methane_fraction)
    else:result['missing'].append('methane_fraction_for_total_biogas_volume')
    if result['gas_reference']:
        result['fuel_energy_kwh']=scale(litres,.001*energy_reference['kwh_m3'])
        result['assumptions'].append('Indicative pure-methane fuel energy: FNR 9.97 kWh/m3; compatible dry/reference basis assumed, not verified')
        if not any(s['id']==energy_reference['id'] for s in result['sources']):result['sources'].append(energy_reference)
    return validate(result)
