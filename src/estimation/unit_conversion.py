def methane_l(vs_mass_kg,bmp_ml_g_vs):
    """kg*(1000 g/kg)*(mL/g)*(L/1000 mL) = L."""
    return vs_mass_kg*bmp_ml_g_vs

def wet_mass(volume_l,density_kg_l):return volume_l*density_kg_l

def volatile_mass(wet_mass_kg,ts_fraction,vs_fraction_of_ts):return wet_mass_kg*ts_fraction*vs_fraction_of_ts
