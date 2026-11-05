from src.advisor.catalog import document
def recommend(request,mixture,geometry):
    materials={c.material for c in request.components};states={c.material_state for c in request.components};refs=[]
    if any(c.material=='cattle_manure' and c.material_state in {'slurry','unknown'} and c.decay_state in {'unknown','fresh'} for c in request.components):
        refs.append({'source_id':'moset2015','temperatures_c':[35,50],'kind':'CONTINUOUS_STUDY','reactor_type':'CSTR','conditions':'Specific cattle slurry at HRT 16/20 d; acclimated cultures and controlled operation','applies_to_full_composition':materials=={'cattle_manure'} and states=={'slurry'}})
    if any(c.material=='cattle_manure' and c.material_state=='bedded' or c.material=='food_waste' for c in request.components):refs.append({'source_id':'baek2020','temperatures_c':[35],'kind':'BMP_INCUBATION_ONLY','conditions':'Specific bedded cattle/ground cafeteria food; diluted 30 d laboratory assay','applies_to_full_composition':False})
    from src.advisor.catalog import choose
    for c in request.components:
        p,_=choose(c,request.allow_literature_transfer)
        if p:
            conditions=p['conditions']
            temperatures=conditions.get('temperatures_c') or ([conditions['temperature_c']] if conditions.get('temperature_c') is not None else [])
            if temperatures and not any(ref['source_id']==p['source_id'] for ref in refs):
                refs.append({'source_id':p['source_id'],'temperatures_c':temperatures,'kind':'BMP_INCUBATION_ONLY',
                    'conditions':p['preparation']+'; reported study conditions only, not an operating setpoint','applies_to_full_composition':False})
    if {'grass','cattle_manure'}<=materials:refs.append({'source_id':'ulukardesler2023','temperatures_c':[35],'kind':'BATCH_STUDY','conditions':'Shredded grass, cow manure and particular sludge; 7 L working volume, 65 d','applies_to_full_composition':materials=={'grass','cattle_manure'}})
    candidate=None
    reactor=request.decision.reactor
    complete=(materials=={'cattle_manure'} and states=={'slurry'} and reactor.operating_mode=='continuous' and (reactor.reactor_type or '').casefold() in {'cstr','continuous stirred reactor'}
              and request.inoculum_description and request.inoculum_adapted_temperature_c==35 and request.temperature_control_confirmed and request.monitoring_confirmed and request.measured_ph is not None and 7.6<=request.measured_ph<=8.0 and request.mixing_available is True
              and mixture.get('olr_kg_vs_m3_day') is not None and not request.inhibition_warning and reactor.engineering_review_confirmed and geometry.get('status') not in {'PHYSICALLY_INFEASIBLE','REQUIRES_SAFETY_REVIEW'})
    if complete:candidate={'temperature_c':35,'status':'ADVISORY_CANDIDATE','reason':'Matches declared 35°C-adapted inoculum and a studied mesophilic CSTR mode. Not a demonstrated optimum or an actuator setpoint.'}
    return {'status':'ADVISORY_CANDIDATE' if candidate else 'STUDIED_CONDITIONS_ONLY','candidate':candidate,'studies':refs,
            'volume_determines_temperature':False,'default_setpoint_c':None,
            'tradeoffs':['Higher temperature may improve conversion in some studies but increases heat demand and can change ammonia/process stability.',
                         'Quantity affects heat capacity and vessel/loading feasibility, not a biological optimum by itself.'],
            'missing':[k for k,present in [('operating_mode',reactor.operating_mode),('reactor_type',reactor.reactor_type),('inoculum',request.inoculum_description),('stable_temperature_control',request.temperature_control_confirmed),('process_monitoring',request.monitoring_confirmed)] if not present],
            'operation_authorized':False}
