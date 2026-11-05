import math
def validate(result):
    for key in ['wet_mass_kg','vs_mass_kg','methane_potential_l','methane_potential_m3','fuel_energy_kwh','raw_biogas_m3','catalog_reference_value_kzt']:
        item=result.get(key)
        if item is not None and (not all(math.isfinite(item[k]) and item[k]>=0 for k in ['low','high']) or item['low']>item['high']):raise ValueError('Invalid calculated range: '+key)
    if result.get('net_profit') is not None:raise ValueError('Research reference engine must not invent profit')
    return result
