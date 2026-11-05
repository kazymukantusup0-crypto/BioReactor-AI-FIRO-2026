"""Typed display references: the model selects IDs but never rewrites their numbers."""
from src.agent.analytical import span


def collect(results):
    evidence={};notes=[]
    def add(key,label,value,unit,level,scenario=None):
        if value is not None:evidence[key]={'id':key,'label':label,'value':value,'unit':unit,'level':level,'scenario':scenario}
    science=results.get('assess_substrate_potential',{})
    for s in science.get('scenarios',[])[:8]:
        sid=s['id'];label=s['label']+(f" (отдельный сценарий {sid})" if len(science.get('scenarios',[]))>1 else '')
        # A potential computed from measured properties is not measured gas.
        level='LITERATURE' if s['result_level']=='LITERATURE_ESTIMATE' else 'SCENARIO_ASSUMPTION'
        add(sid+'.methane',label+': потенциал метана',s.get('methane_m3'),'м³ CH₄',level,sid)
        add(sid+'.vs',label+': масса VS',s.get('vs_mass_kg'),'кг VS',level,sid)
        add(sid+'.biogas',label+': потенциал общего биогаза',s.get('biogas',{}).get('potential_biogas_m3'),'м³ биогаза',level,sid)
        vessel=s['engineering'].get('total_volume_l')
        if vessel is not None:add(sid+'.vessel',label+': номинальная ёмкость (ограничивает загрузку, не задаёт метан)',{'low':vessel,'high':vessel},'л','MEASURED',sid)
        if s.get('missing'):notes.append({'scenario':sid,'missing':s['missing']})
        notes.append({'scenario':sid,'profiles':s['profile_ids'],'assumptions':s['assumptions'][:3],
                      'capacity_status':s['engineering']['status'],'capacity_missing':s['engineering']['missing'],
                      'capacity_violations':s['engineering']['violations'],'biogas':s.get('biogas'),
                      'biogas_requires_methane_fraction_on_same_gas_basis':s.get('biogas',{}).get('methane_fraction') is None})
    for row in results.get('evaluate_partial_economics',{}).get('scenarios',[])[:4]:
        sid=row['id'];analysis=row['analysis'];energy=analysis['energy'];scope=row['label']+': '
        for name,label in [('heat_only_kwh','Полезное тепло'),('electricity_only_kwh','Электричество')]:
            add(sid+'.'+name,scope+label+' (альтернативное использование газа)',energy['outputs'].get(name),'кВт·ч','SCENARIO_ASSUMPTION',sid)
        for alt in analysis['scenarios']:
            if alt['id'] not in {'B_heat','C_electricity','A_sell_feedstock'}:continue
            name={'B_heat':'Тепло' if analysis['prices']['heat']['status'] not in {'missing','unusable'} else 'Замещение электронагрева','C_electricity':'Электричество','A_sell_feedstock':'Продажа сырья'}[alt['id']]
            value=alt.get('gross_benefit_reference_kzt')
            if value is None:value=alt.get('reference_asking_value_kzt')
            add(sid+'.'+alt['id']+'.gross',scope+name+': валовая ценность до расходов',value,'KZT','SCENARIO_ASSUMPTION',sid)
            ref=evidence.get(sid+'.'+alt['id']+'.gross')
            if ref:
                role='feedstock' if alt['id']=='A_sell_feedstock' else 'heat' if alt['id']=='B_heat' and analysis['prices']['heat']['status'] not in {'missing','unusable'} else 'electricity'
                price=analysis['prices'].get(role,{});observation=price.get('observation') or {}
                ref['price_context']={k:observation.get(k) for k in ['published_at','age_days','region','is_stale','usable_as_current']}
                ref['alternative_use']=True
            threshold=(alt.get('break_even') or {}).get('maximum_total_processing_cost_to_match_sale_kzt')
            add(sid+'.'+alt['id']+'.threshold',name+': порог всех затрат относительно продажи',threshold,'KZT','SCENARIO_ASSUMPTION',sid)
        notes.append({'scenario':sid,'unknown_costs':analysis['operating_costs']['missing'],
                      'price_statuses':{role:{k:p.get(k) for k in ['status','published_at','age_days','region']} for role,p in analysis['prices'].items()},
                      'energy_assumptions':energy.get('assumed_parameters',[]),'alternatives_not_additive':True})
    process=results.get('assess_process_evidence',{})
    for index,study in enumerate(process.get('matched_temperature_experiments',[])[:3]):
        add('temperature.'+str(index),'Температура опубликованного опыта, не уставка',{'low':study['temperature_c'],'high':study['temperature_c']},'°C','LITERATURE',study['profile_id'])
    if process:notes.append({'heating_missing':process.get('heating_missing',[]),'temperature_not_optimum':True})
    prediction=results.get('predict_bmp',{})
    if prediction.get('status')=='ok':add('model.bmp','Прогноз сохранённой модели',{'low':prediction['bmp'],'high':prediction['bmp']},'мл CH₄/г VS','MODEL_PREDICTION')
    info=results.get('get_model_info',{})
    for name,value in info.get('accuracy',{}).items():
        if isinstance(value,(int,float)) and not isinstance(value,bool) and any(metric in name for metric in ['MAE','RMSE','R2']):
            add('model.'+name,'Оценка сохранённой модели '+name,{'low':value,'high':value},'безразмерно' if 'R2' in name else 'мл CH₄/г VS','MODEL_PREDICTION')
    for name,result in results.items():
        if result.get('status') in {'error','needs_input','unsupported','unavailable'}:notes.append({'tool':name,'status':result['status'],'message':result.get('message'),'missing':result.get('missing',[])})
    return evidence,notes


def render_reference(reference):
    qualifier={'SCENARIO_ASSUMPTION':'условный сценарий','LITERATURE':'литературные данные','MODEL_PREDICTION':'прогноз модели','MEASURED':'по сообщённым данным','UNKNOWN':'неизвестно'}
    text=f"{reference['label']}: {span(reference['value'])} {reference['unit']} ({qualifier.get(reference['level'],'неизвестно')})."
    if reference.get('alternative_use'):text+=' Альтернативы одного газового потока; суммы не складываются.'
    price=reference.get('price_context')
    if price and price.get('published_at'):
        text+=f" Сохранённый ориентир: {price['region']}, публикация {price['published_at']}, возраст ценового периода {price['age_days']} дн.; "
        text+='устарел, текущий тариф не подтверждён.' if price.get('is_stale') else 'применимость индивидуального тарифа требует подтверждения.'
    return text


def partial_references(evidence,results):
    """Keep compared materials and available valuation visible after LLM failure."""
    scenarios=results.get('assess_substrate_potential',{}).get('scenarios',[])
    representatives={}
    for scenario in scenarios:
        if scenario['id']+'.methane' in evidence:representatives.setdefault(scenario['label'],scenario['id'])
    selected=[sid+'.methane' for sid in representatives.values()][:4]
    selected+=[key for key in evidence if key.endswith('.methane') and key not in selected][:max(0,4-len(selected))]
    money=[]
    for sid in list(representatives.values())[:2]:
        money += [key for key in evidence if key.startswith(sid+'.') and key.endswith('.gross')][:1 if len(representatives)>1 else 2]
    selected+=money
    if not selected:selected=list(evidence)[:3]
    return [evidence[key] for key in selected[:6]]
