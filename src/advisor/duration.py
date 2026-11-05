def recommend(request,mixture):
    materials={c.material for c in request.components};rows=[]
    if any(c.material=='cattle_manure' and c.material_state in {'slurry','unknown'} and c.decay_state in {'unknown','fresh'} for c in request.components):
        rows.extend([{'kind':'BMP_INCUBATION','days':[27],'source_id':'doi:10.1007/s43153-025-00592-x','conditions':'Untreated RM1, 37°C, AMPTS II; endpoint test, not prescribed operation'},
                     {'kind':'HRT','days':[16,20],'source_id':'moset2015','conditions':'Continuous CSTR, cattle slurry, 35/50°C; not a batch duration'}])
    if 'food_waste' in materials or any(c.material=='cattle_manure' and c.material_state=='bedded' for c in request.components):rows.append({'kind':'BMP_INCUBATION','days':[30],'source_id':'baek2020','conditions':'Diluted assay, specific substrates/inoculum, 35°C; not full-scale HRT'})
    from src.advisor.catalog import choose
    for c in request.components:
        p,_=choose(c,request.allow_literature_transfer)
        if p:
            conditions=p['conditions']
            days=conditions.get('duration_days')
            if days is not None and not any(row['source_id']==p['source_id'] for row in rows):
                rows.append({'kind':conditions.get('duration_kind','BMP_INCUBATION'),'days':[days],'source_id':p['source_id'],
                    'conditions':p['preparation']+'; laboratory study duration, not a full-scale retention time'})
    if {'grass','cattle_manure'}<=materials:rows.append({'kind':'BATCH_EXPERIMENT','days':[65],'source_id':'ulukardesler2023','conditions':'Specific shredded grass/cow manure/sludge batch, 35±1°C; not a universal cycle'})
    hrt=None
    if request.decision.reactor.operating_mode=='continuous' and request.total_daily_liquid_feed_l and request.daily_feed_includes_all_liquid and request.decision.reactor.reactor_working_volume_l:
        value=request.decision.reactor.reactor_working_volume_l/request.total_daily_liquid_feed_l
        hrt={'low':value,'high':value,'assumption':'User explicitly declares the full daily hydraulic feed including dilution and other liquid streams'}
    return {'status':'REFERENCE_ONLY','studies':rows,'recommended_batch_duration_days':None,'estimated_hrt_from_declared_feed_days':hrt,
            'srt_days':None,'startup_acclimation_days':None,'predicted_time_to_target_yield_days':None,
            'distinctions':{'BMP_INCUBATION':'Laboratory endpoint assay','HRT':'Working liquid volume / total daily liquid flow','SRT':'Retention of solids; not automatically equal to HRT','BATCH_EXPERIMENT':'Elapsed time of a specified batch experiment','STARTUP':'Inoculum establishment/adaptation, not included automatically'},
            'missing':['Matched validated kinetics, inoculum and loading information before predicting batch completion or start-up'],
            'notice':'27-day BMP incubation is not a required plant residence time. No time minimization without a suitable kinetic model.'}
