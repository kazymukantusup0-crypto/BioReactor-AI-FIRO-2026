from src.estimation.scenario_ranges import point,multiply

def resolve(request,profile):
    inputs={};assumptions=[]
    def value(name,measured,profile_key):
        if measured is not None:inputs[name]={'range':point(measured),'basis':'USER_MEASURED_INPUT'}
        elif profile:
            raw=profile['values'][profile_key]
            inputs[name]={'range':{'low':raw['low'],'high':raw['high']},'basis':'REVIEWED_LITERATURE','source_id':profile['source']['id'],'locator':raw['locator'],'original_value':raw['original_value'],'original_unit':raw['original_unit'],'method':raw['method']}
            assumptions.append(name+' transferred from '+profile['id'])
        return inputs.get(name,{}).get('range')
    mass=point(request.mass_kg) if request.mass_kg is not None else None
    if mass is None and request.volume_l is not None:
        density=value('density_kg_l',request.density_kg_l,'density_kg_l')
        if density:mass=multiply(point(request.volume_l),density)
    vs=point(request.vs_mass_kg) if request.vs_mass_kg is not None else None
    if vs is None and mass:
        if request.vs_fraction_wet is not None:fraction=value('vs_fraction_wet',request.vs_fraction_wet,'vs_fraction_wet')
        elif request.ts_fraction is not None and request.vs_fraction_of_ts is not None:
            fraction=point(request.ts_fraction*request.vs_fraction_of_ts)
            inputs['TS_and_VS_of_TS']={'range':fraction,'basis':'USER_MEASURED_INPUT','formula':'TS_fraction * VS_fraction_of_TS'}
        elif request.ts_fraction is not None or request.vs_fraction_of_ts is not None:
            # Partial measured solids data must not be silently overridden by an unrelated profile.
            fraction=None
        else:fraction=value('vs_fraction_wet',None,'vs_fraction_wet')
        if fraction:vs=multiply(mass,fraction)
    bmp=value('bmp_ml_g_vs',request.bmp_ml_g_vs,'bmp_ml_g_vs')
    return mass,vs,bmp,inputs,assumptions
