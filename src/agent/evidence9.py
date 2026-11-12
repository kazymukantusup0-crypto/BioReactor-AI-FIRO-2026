"""Typed display references: the model selects IDs but never rewrites their numbers."""
from src.agent.analytical import span

_MISSING_LABELS={
    'bmp_ml_g_vs':'BMP в мл CH₄/г VS',
    'ts_fraction':'содержание сухого вещества (TS)',
    'vs_fraction_wet':'доля летучих веществ во влажной массе (VS)',
    'vs_fraction_of_ts':'доля VS от TS',
    'inoculum_volume_l':'объём инокулята',
    'dilution_water_l':'объём воды разбавления',
    'resident_liquid_volume_l':'объём остаточной жидкости',
    'operating_mode':'режим работы',
    'reactor_working_volume_l':'рабочий объём реактора',
    'headspace_l':'объём газового пространства',
    'density_kg_l':'плотность сырья',
    'feedstock_cost_kzt':'стоимость сырья',
    'transport_cost_kzt':'стоимость транспортировки',
    'storage_cost_kzt':'стоимость хранения',
    'preparation_cost_kzt':'стоимость подготовки',
    'operating_cost_kzt':'эксплуатационные затраты',
    'maintenance_cost_kzt':'затраты на обслуживание',
    'gas_cleaning_cost_kzt':'затраты на очистку газа',
    'capital_cost_kzt':'капитальные затраты',
}


def _human_names(values):
    names=[]
    for value in values or []:
        text=str(value)
        if text.startswith('volume_or_density:'):
            text='объём или плотность компонента '+text.split(':',1)[1]
        else:
            text=_MISSING_LABELS.get(text,text.replace('_',' ').replace(':',' '))
        if text not in names:names.append(text)
    return names


def collect(results):
    evidence={};notes=[]
    def add(key,label,value,unit,level,scenario=None):
        if value is not None:evidence[key]={'id':key,'label':label,'value':value,'unit':unit,'level':level,'scenario':scenario}
    # A profile search may return reviewed, sample-specific measurements even
    # when batch characterization is incomplete and no methane scenario can
    # be calculated. Keep those source observations citable in their original
    # units so synthesis failure does not erase useful literature evidence.
    profile_search=results.get('search_substrate_profiles',{})
    for dossier in profile_search.get('dossiers',[])[:12]:
        material=dossier.get('name') or dossier.get('material') or 'Substrate profile'
        for index,study in enumerate(dossier.get('studies',[])[:12]):
            # The reviewed dossier API uses the explicit CH4-qualified field;
            # retain the older alias for existing stored result fixtures.
            value=study.get('bmp_ml_ch4_g_vs')
            if not isinstance(value,dict):value=study.get('bmp_ml_g_vs')
            if not isinstance(value,dict):continue
            low=value.get('low');high=value.get('high')
            if (not isinstance(low,(int,float)) or isinstance(low,bool) or
                    not isinstance(high,(int,float)) or isinstance(high,bool) or low>high):continue
            profile_id=str(study.get('profile_id') or f"{dossier.get('material','profile')}-{index}")
            key='profile.'+profile_id+'.bmp'
            state=study.get('physical_state')
            label=f"{material}"+(f" ({state})" if state else '')+f": опубликованный BMP образца {profile_id}"
            details=[]
            if study.get('preparation'):details.append('Preparation: '+str(study['preparation']))
            if study.get('quality'):details.append('Evidence review: '+str(study['quality']))
            if study.get('transfer_limitations'):details.append(str(study['transfer_limitations']))
            source=study.get('source_id')
            if source:details.append('Source ID: '+str(source))
            add(key,label,{'low':low,'high':high},'mL CH4/g VS','LITERATURE',profile_id)
            evidence[key]['description']=' '.join(details)
            if value.get('locator'):evidence[key]['source_locator']=str(value['locator'])
            notes.append(f"Значение BMP профиля {profile_id} относится к исследованному образцу; перенос на пользовательскую партию автоматически не подтверждён.")
    science=results.get('assess_substrate_potential',{})
    for s in science.get('scenarios',[])[:8]:
        sid=s['id'];label=s['label']+(f" (отдельный сценарий {sid})" if len(science.get('scenarios',[]))>1 else '')
        # A potential computed from measured properties is not measured gas.
        level='LITERATURE' if s['result_level']=='LITERATURE_ESTIMATE' else 'SCENARIO_ASSUMPTION'
        add(sid+'.methane',label+': потенциал метана',s.get('methane_m3'),'м³ CH₄',level,sid)
        if sid+'.methane' in evidence and s.get('result_provenance'):
            evidence[sid+'.methane']['result_provenance']=s['result_provenance']
        add(sid+'.vs',label+': масса VS',s.get('vs_mass_kg'),'кг VS',level,sid)
        add(sid+'.biogas',label+': потенциал общего биогаза',s.get('biogas',{}).get('potential_biogas_m3'),'м³ биогаза',level,sid)
        if sid+'.biogas' in evidence and s.get('biogas',{}).get('result_provenance'):
            evidence[sid+'.biogas']['result_provenance']=s['biogas']['result_provenance']
        vessel=s['engineering'].get('total_volume_l')
        if vessel is not None:
            vessel_level='SCENARIO_ASSUMPTION' if 'reactor_total_volume_l' in science.get('scenario_process_inputs',{}) else 'USER_REPORTED'
            add(sid+'.vessel',label+': номинальная ёмкость (ограничивает загрузку, не задаёт метан)',{'low':vessel,'high':vessel},'л',vessel_level,sid)
        if s.get('missing'):
            notes.append(f"{label}: для численной оценки не хватает {', '.join(_human_names(s['missing']))}.")
        if not any(s.get('profile_ids',[])):
            notes.append(f"Для сырья «{label}» не найден подтверждённый применимый литературный профиль.")
        engineering=s.get('engineering',{})
        if engineering.get('status')!='OK' or engineering.get('missing'):
            missing=_human_names(engineering.get('missing'))
            details=', '.join(missing) if missing else 'данных о загрузке реактора'
            notes.append(f"Проверка вместимости требует уточнить: {details}.")
        if engineering.get('violations'):
            notes.append('Проверка загрузки выявила ограничения, которые требуют инженерной оценки.')
        biogas=s.get('biogas') or {}
        if biogas.get('methane_fraction') is None:
            notes.append('Для оценки общего объёма биогаза нужна доля метана на той же газовой базе; метан входит в биогаз.')
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
        missing=_human_names(analysis['operating_costs'].get('missing'))
        if missing:notes.append('Для оценки чистой прибыли не заданы: '+', '.join(missing)+'.')
        notes.append('Продажа сырья, использование тепла и выработка электричества являются альтернативами; их доходы нельзя складывать для одного потока газа.')
        if energy.get('assumed_parameters'):
            notes.append('Энергетическая оценка зависит от явно перечисленных расчётных допущений.')
    process=results.get('assess_process_evidence',{})
    discussion=process.get('temperature_consultation',{}).get('discussion_temperature_c')
    if discussion is not None:
        add('temperature.discussion','Литературный мезофильный вариант для обсуждения, не уставка',{'low':discussion,'high':discussion},'°C','LITERATURE',None)
    for index,study in enumerate(process.get('matched_temperature_experiments',[])[:3]):
        add('temperature.'+str(index),'Температура опубликованного опыта, не уставка',{'low':study['temperature_c'],'high':study['temperature_c']},'°C','LITERATURE',study['profile_id'])
    if process:
        missing=_human_names(process.get('heating_missing'))
        if missing:notes.append('Для оценки теплового баланса не хватает: '+', '.join(missing)+'.')
        notes.append('Температура опубликованного опыта не является автоматически оптимальной уставкой реактора.')
    prediction=results.get('predict_bmp',{})
    if prediction.get('status')=='ok':add('model.bmp','Прогноз сохранённой модели',{'low':prediction['bmp'],'high':prediction['bmp']},'мл CH₄/г VS','MODEL_PREDICTION')
    info=results.get('get_model_info',{})
    for name,value in info.get('accuracy',{}).items():
        if isinstance(value,(int,float)) and not isinstance(value,bool) and any(metric in name for metric in ['MAE','RMSE','R2']):
            add('model.'+name,'Оценка сохранённой модели '+name,{'low':value,'high':value},'безразмерно' if 'R2' in name else 'мл CH₄/г VS','MODEL_PREDICTION')
    for row in results.get('explicit_calculations',{}).get('calculations',[])[:8]:
        key=row['id'];value=row['value']
        evidence[key]={'id':key,'label':row['label'],'value':{'low':value,'high':value},'unit':row['unit'],
            'level':row['level'],'scenario':None,'formula':row['formula'],'description':row['description'],
            'inputs':row['inputs'],'result_provenance':row.get('result_provenance')}
    prices=results.get('get_market_prices',{}).get('prices',[])
    for price in prices[:8]:
        value=price.get('normalized_value')
        try:value=float(value)
        except (TypeError,ValueError):continue
        currency=price.get('currency','');unit=price.get('normalized_unit') or price.get('unit','')
        key=f"market.price.{price.get('source_id','source')}.{price.get('id',len(evidence))}"
        evidence[key]={'id':key,'label':f"{price.get('source_name','Сохранённая цена')}: {price.get('commodity','цена')}",
            'value':{'low':value,'high':value},'unit':f'{currency}/{unit}','level':'SOURCE_VERIFIED' if str(price.get('reliability','')).startswith('verified') else 'SOURCE_REPORTED',
            'scenario':None,'price_context':{k:price.get(k) for k in ['published_at','effective_from','age_days','region','is_stale','usable_as_current','price_type','consumer_class','tax_basis','source_name']}}
    tool_labels={'assess_substrate_potential':'оценка метанового потенциала',
                 'evaluate_partial_economics':'частичная экономическая оценка',
                 'get_market_prices':'проверка рыночных цен',
                 'search_substrate_profiles':'поиск научных профилей',
                 'assess_process_evidence':'оценка технологических данных'}
    status_labels={'error':'завершилась ошибкой','needs_input':'требует входных данных',
                   'unsupported':'не поддерживается доступными данными','unavailable':'недоступна'}
    for name,result in results.items():
        status=result.get('status')
        if status in status_labels:
            description=tool_labels.get(name,name.replace('_',' '))
            missing=_human_names(result.get('missing'))
            sentence=f"{description}: {status_labels[status]}"
            if missing:sentence+='; не хватает '+', '.join(missing)
            notes.append(sentence+'.')
    return evidence,notes


def render_reference(reference):
    qualifier={'SCENARIO_ASSUMPTION':'условный сценарий','LITERATURE':'литературные данные','MODEL_PREDICTION':'прогноз модели',
        'MEASURED':'по сообщённым данным','USER_REPORTED':'по сообщённым данным','SOURCE_VERIFIED':'по сохранённому подтверждённому источнику',
        'SOURCE_REPORTED':'по сохранённому источнику','CALCULATED_FROM_CONFIRMED':'расчёт из введённых данных','UNKNOWN':'неизвестно'}
    text=f"{reference['label']}: {span(reference['value'])} {reference['unit']} ({qualifier.get(reference['level'],'неизвестно')})."
    if reference.get('alternative_use'):text+=' Альтернативы одного газового потока; суммы не складываются.'
    if reference.get('description'):text+=' '+reference['description']
    price=reference.get('price_context')
    if price and any(price.get(k) is not None for k in ('published_at','effective_from','age_days')):
        publication=price.get('published_at') or 'дата публикации не установлена'
        basis=f", дата действия {price['effective_from']}" if price.get('effective_from') and price['effective_from']!=price.get('published_at') else ''
        region=f"Регион {price['region']}, " if price.get('region') else ''
        age=f", консервативный возраст ценового периода {price['age_days']} дн." if price.get('age_days') is not None else ''
        text+=f" {region}публикация {publication}{basis}{age}; "
        text+='устарел, текущий тариф не подтверждён.' if price.get('is_stale') else 'применимость индивидуального тарифа требует подтверждения.'
    return text


def partial_references(evidence,results,safe_only=False):
    """Keep compared materials and available valuation visible after LLM failure."""
    if safe_only:
        # A failed or incomplete arithmetic verification must not suppress
        # independently reviewed profile observations or source price records,
        # but derived scenario totals remain hidden until their checks pass.
        allowed=[]
        for key,reference in evidence.items():
            if key.startswith('profile.') and key.endswith('.bmp') and reference.get('level')=='LITERATURE':
                allowed.append(reference)
            elif key.startswith('market.price.') and reference.get('level') in {'SOURCE_VERIFIED','SOURCE_REPORTED'}:
                allowed.append(reference)
        return allowed[:6]
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
    selected += [key for key in evidence if key.startswith('explicit.') and key not in selected][:4]
    if not selected:selected=[key for key in evidence if key.startswith('market.price.')][:4]
    if not selected:selected=list(evidence)[:3]
    return [evidence[key] for key in selected[:6]]
