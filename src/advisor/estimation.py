"""Projections of the shared mass/VS/BMP engine; no independent yield calculator.

Literature sensitivity envelopes describe named samples, not confidence intervals.
A timed yield requires a separately supplied applicable kinetic fit. A BMP assay
duration is recorded but is never silently treated as reactor residence time.
"""
import math
import re
from src.economics.energy_conversion import scale

LABELS={'MEASURED':'Расчёт по измеренным данным','LITERATURE_ESTIMATE':'Литературная оценка',
        'INSUFFICIENT_EVIDENCE':'Недостаточно научных данных'}

def model_context(result,question,evidence):
    """Bounded stage projection; full provenance remains in the immutable trace."""
    return {'question':question,'estimation_mode':result['estimation_mode'],'target_days':result.get('target_days'),
            'verified_scenarios':[{'name':s['label'],'potential_methane_l':s['potential_methane_l'],
               'time_yield':s['time_yield']['methane_l'],'basis':'Conditional comparable source sample; not measured plant output',
               'missing_for_time_yield':s['time_yield']['missing'],
               'loading':s['loading']['status']} for s in result['scenarios'] if s.get('potential_methane_l')],
            'evidence':{k:{f:v[f] for f in ('label','value','unit','level') if f in v} for k,v in evidence.items() if k.endswith('.methane')},
            'clarification':'Confirm physical form/dilution, measured solids and applicable kinetics. Nominal capacity is not working capacity.',
            'output_instruction':'Explain why this is only a conditional potential; do not turn it into yield by the requested day.'}

def time_claim_issues(text,result):
    """A supported potential cannot be relabeled as a timed production forecast."""
    issues=[]
    for clause in re.split(r'(?<=[!?;])\s+|\n+|(?<!\d)\.(?!\d)\s+',text):
        if not re.search(r'\d+[.,]?\d*\s*(?:дн\w*|сут\w*|days?|күн\w*)',clause,re.I):continue
        from src.agent.quantities9 import check
        typed=[]
        check([clause],{},[],audit=typed)
        if not any(q['unit'] in {'methane_m3','methane_L','methane_ml'} for q in typed):continue
        # Negation must target the timed-production assertion, not another fact.
        if re.search(r'не\s+(?:является|равен|означает|гарантирует|гарантированн\w*)\s+(?:так\w*\s+)?(?:выход|выработ|прогноз)|не\s+(?:выход|выработ|прогноз)|not\s+(?:a\s+)?(?:yield|production|forecast)',clause,re.I):continue
        if re.search(r'не\s+(?:может|можно)\s+(?:быть\s+)?(?:привязан\w*|приравн\w*|счит\w*|трактова\w*)|cannot\s+be\s+(?:tied|equated|interpreted)',clause,re.I):continue
        timed={s['id']+'.time':{'value':s['time_yield']['methane_l'],'unit':'L CH4','level':'CALCULATED'}
               for s in result.get('scenarios',[]) if s.get('time_yield',{}).get('methane_l') is not None}
        if not timed:issues.append('unsupported_time_resolved_methane_claim');continue
        horizon=f"за {result.get('target_days')} дней"
        if check([clause],timed,list(timed),query=horizon):issues.append('timed_claim_not_supported_by_kinetic_result')
    return list(dict.fromkeys(issues))

def annotate(result,request):
    from src.advisor.catalog import profiles
    catalogue={p['id']:p for p in profiles()}
    for s in result['scenarios']:
        from src.optimizer.capacity import assess_reactor_capacity
        volumes=[c['volume_l'] for c in s['components']]
        feed=sum(v['low'] for v in volumes) if volumes and all(v and v['low']==v['high'] for v in volumes) else None
        reactor=request.decision.reactor
        s['loading']=assess_reactor_capacity(feedstock_volume_l=feed,reactor_total_volume_l=request.reactor_total_volume_l,
            reactor_working_volume_l=reactor.reactor_working_volume_l,dilution_water_l=reactor.dilution_water_l,
            inoculum_volume_l=reactor.inoculum_volume_l,resident_liquid_volume_l=reactor.resident_liquid_volume_l)
        for c in s['components']:
            c['source_conditions']=catalogue.get(c.get('profile_id'),{}).get('conditions',{})
        origins=[p.get('provenance') for c in s['components'] for p in c['properties_used'].values()]
        measured=(bool(origins) and all(o=='MEASURED' for o in origins)
                  and all(c.data_mode=='MEASURED' for c in request.components))
        mode=('INSUFFICIENT_EVIDENCE' if s['methane_m3'] is None else 'MEASURED' if measured else
              'LITERATURE_ESTIMATE' if any(c.get('source') for c in s['components']) else 'INSUFFICIENT_EVIDENCE')
        # User-reported numbers with no measurement claim remain calculations.
        s['estimation_mode']=mode
        s['potential_methane_l']=scale(s['methane_m3'],1000) if s['methane_m3'] else None
        time={'days':request.target_days,'methane_l':None,'mode':'INSUFFICIENT_EVIDENCE',
              'method':None,'missing':[],'source_assay_conditions':[c['source_conditions'] for c in s['components'] if c.get('source')]}
        k=request.kinetic_evidence
        if request.target_days is not None:
            if not s['methane_m3']:time['missing'].append('mass_VS_and_compatible_BMP')
            if k is None:time['missing'].append('applicable_measured_accumulation_or_validated_kinetics')
            if request.process_temperature_c is None:time['missing'].append('process_temperature_c')
            if k and request.process_temperature_c is not None and not math.isclose(k.temperature_c,request.process_temperature_c,abs_tol=.01):
                time['missing'].append('kinetic_fit_at_applicable_temperature')
            # Never transfer a fitted curve to another source sample automatically.
            if k and not measured:time['missing'].append('kinetic_fit_with_measured_batch_properties')
            if not time['missing']:
                fraction={'low':-math.expm1(-k.rate_per_day.low*max(0,request.target_days-k.lag_days.high)),
                          'high':-math.expm1(-k.rate_per_day.high*max(0,request.target_days-k.lag_days.low))}
                from src.economics.energy_conversion import multiply
                time.update(methane_l=multiply(s['potential_methane_l'],fraction),mode='MEASURED',
                            method='first_order',fraction=fraction,reference=k.reference,kinetic_inputs=k.model_dump(),
                            formula='V(t) = VS * BMP * (1 - exp(-k * max(0, t-lag)))',
                            result_method='CALCULATED',limitations=['Applicable user-supplied fit; not measured reactor gas production.'])
        s['time_yield']=time
    modes=[s['estimation_mode'] for s in result['scenarios'] if s['potential_methane_l'] is not None]
    result['estimation_mode']=('LITERATURE_ESTIMATE' if 'LITERATURE_ESTIMATE' in modes else 'MEASURED' if modes else 'INSUFFICIENT_EVIDENCE')
    result['target_days']=request.target_days
    result['answer']=render(result)

def span(v):
    if v is None:return 'не определено'
    return f"{v['low']:.6g}" if v['low']==v['high'] else f"{v['low']:.6g}–{v['high']:.6g}"

def render(result):
    lines=[]
    from src.optimizer.capacity import render_capacity_notice
    if result['scenarios']:
        notice=render_capacity_notice(result['scenarios'][0]['loading'],'ru')
        if notice:lines.append(notice)
    for s in result['scenarios']:
        if not s.get('potential_methane_l'):continue
        timed=s['time_yield'];days=timed.get('days')
        if days is not None:
            lines.append(f"Выход за {days:g} дней: "+(span(timed['methane_l'])+' л CH₄ (расчёт по применимой кинетической модели).' if timed['methane_l'] else 'численно не установлен; применимая кинетика и условия реактора не подтверждены.'))
        lines.append(f"Основа оценки: {LABELS[s['estimation_mode']]}. Расчётный BMP-ориентир всей партии: {span(s['potential_methane_l'])} л CH₄; это не измеренная выработка и не гарантия выхода за срок.")
        for c in s['components']:
            props=c['properties_used'];density=props.get('density_kg_l',{}).get('range');ts=props.get('ts_fraction',{}).get('range')
            vs=props.get('vs_fraction_wet',{}).get('range');bmp=props.get('bmp_ml_g_vs',{}).get('range')
            form={'slurry':'навозная жижа','fresh_solid':'свежий плотный навоз','bedded':'навоз с подстилкой'}.get(c['material_state'],c['material_state'])
            lines.append(f"{c['display_name']}: {form} — "+('условное соответствие опубликованному образцу, а не установленный состав вашей партии.' if c.get('source') else 'введённые параметры.'))
            if density:lines.append(f"Принятая плотность {span(density)} кг/л; расчётная масса {span(c['wet_mass_kg'])} кг.")
            if props.get('vs_kg_l'):
                lines.append(f"В опубликованном образце: органическое сухое вещество (VS) {span(scale(props['vs_kg_l']['range'],1000))} г/л. Из объёма партии рассчитано {span(c['vs_mass_kg'])} кг VS. Масса влажного навоза и плотность не назначены: здесь используется концентрация на литр, а не перевод литров в килограммы.")
            if props.get('ts_kg_l'):lines.append(f"Общее сухое вещество (TS) источника {span(scale(props['ts_kg_l']['range'],1000))} г/л; в партии условно {span(c['ts_mass_kg'])} кг TS.")
            if ts:lines.append(f"TS {span(scale(ts,100))}% влажной массы; TS партии {span(c['ts_mass_kg'])} кг.")
            if vs:lines.append(f"VS {span(scale(vs,100))}% влажной массы, а не TS; VS партии {span(c['vs_mass_kg'])} кг.")
            if bmp:lines.append(f"BMP {span(bmp)} мл CH₄/г VS. V(CH₄), л = VS, кг × BMP, мл/г.")
            if c.get('source'):
                src=c['source'];cond=c.get('source_conditions',{})
                lines.append('Источник: '+src['title']+' — '+src.get('url',''))
                details=[]
                if cond.get('temperature_c') is not None:details.append(f"температура {cond['temperature_c']:g} °C")
                if cond.get('duration_days') is not None:details.append(f"длительность испытания {cond['duration_days']:g} дней")
                if cond.get('gas_reference'):details.append('база объёма газа '+cond['gas_reference'])
                lines.append('Условия источника: '+', '.join(details)+'. Они не заданы как условия вашего реактора; влажность газа может быть не определена.')
                if c.get('profile_id')=='oliveira-rm1-2025-v1':
                    lines.append('Образец RM1: необработанная коровья жижа, охлаждённое хранение перед опытом. BMP — грубая графическая граница по рис. 1a; TS и VS — среднее ± опубликованное стандартное отклонение. Это не гарантированный окончательный потенциал и не прогноз за 30 дней.')
        lines.append('Диапазон — чувствительность к выбранным границам опубликованного образца, не доверительный интервал. Плотность — точечное значение; вариация другой партии и зависимость параметров не охвачены.')
    if not any(s.get('potential_methane_l') for s in result['scenarios']):
        from src.agent.evidence9 import _human_names
        lines.append('Численный диапазон не обоснован доступными совместимыми данными. Не хватает: '+', '.join(_human_names(sorted({x for s in result['scenarios'] for x in s['missing']})))+'.')
    lines.append('Номинальная вместимость не равна рабочему объёму. Возможность загрузки сырья вместе с водой и инокулятом проверяется отдельно; расчёт всей партии не является выходом одного цикла.')
    lines.append('Что измерить: физическую форму и разбавление, массу или плотность, TS и VS на указанной основе, BMP, температуру и кривую накопления метана; уточнить рабочий объём, воду и инокулят.')
    return '\n\n'.join(lines)
