"""Short RU/KK/EN answers; full formulas and evidence stay in expandable cards."""
def interval(r,unit='',digits=2):
    if r is None:return None
    return (f"{r['low']:.{digits}f}" if abs(r['high']-r['low'])<1e-9 else f"{r['low']:.{digits}f}–{r['high']:.{digits}f}")+(' '+unit if unit else '')

def render(state,data,r):
    a=r.get('decision_analysis',{});language=state.language
    def t(ru,en,kk):return {'ru':ru,'en':en,'kk':kk}[language]
    previous=state.last_research_summary;now={'quantity':state.value('quantity'),'material_state':data['material_state'],'gas_use':state.decision_settings.get('gas_use','unknown'),'level':r.get('result_level')}
    form_changed=bool(previous and previous.get('material_state')!=now['material_state'])
    use_changed=bool(previous and previous.get('gas_use')!=now['gas_use'])
    p=[];methane=interval(r.get('methane_potential_m3'),'м³ CH₄' if language!='en' else 'm³ CH4')
    if form_changed:p.append(t('Уточнение сохранено: это навозная жижа. Литературный профиль стал более подходящим; характеристики партии всё ещё не измерены.' if data['material_state']=='slurry' else 'Состояние сырья обновлено; применимость прежнего профиля проверена заново.',
                              'Material form updated. The literature profile is more comparable for slurry, but this batch is still unmeasured.',
                              'Шикізат күйі жаңартылды. Сұйық көңге әдеби профиль жақынырақ, бірақ осы партияның қасиеттері өлшенген жоқ.'))
    elif use_changed:p.append(t('Назначение газа изменено; экономическое сравнение пересчитано.','Gas use changed; the comparison has been recalculated.','Газды пайдалану мақсаты өзгерді; салыстыру қайта есептелді.'))
    if methane:
        if not previous and r.get('result_level')=='HYPOTHETICAL_SCENARIO':p.append(t('Расчёт условный: предполагается сопоставимость с исследованной навозной жижей; состояние вашей партии ещё нужно уточнить.','This assumes comparability with the studied cattle slurry; your batch form is not yet confirmed.','Есеп зерттелген сұйық көңмен салыстырмалылықты болжайды; сіздің партияңыздың күйі әлі расталмаған.'))
        bg=interval(a.get('biogas',{}).get('potential_biogas_m3'),'м³' if language!='en' else 'm³')
        p.append(t(f'Потенциал метана: {methane}.'+('' if form_changed else f' Условный общий биогаз по BMP, до потерь: {bg} при 55–60% CH₄.' if bg and a['biogas']['methane_fraction'].get('provenance')=='HYPOTHETICAL_SCENARIO' and a['biogas']['methane_fraction']['low']==.55 else f' Общий биогаз: {bg}.' if bg else ' Для общего биогаза не хватает сопоставимого газового базиса/доли CH₄.'),
                   f'Methane potential: {methane}.'+(f' Conditional total biogas: {bg}; composition and reference assumptions are in the cards.' if bg else ' Total biogas needs a compatible composition and gas basis.'),
                   f'Метан әлеуеті: {methane}.'+(f' Шартты жалпы биогаз: {bg}; құрам мен газ базисінің болжамдары карточкада.' if bg else ' Жалпы биогазға сәйкес құрам мен газ базисі қажет.')))
        outputs=a.get('energy',{}).get('outputs',{});heat=interval(outputs.get('heat_only_kwh'));electric=interval(outputs.get('electricity_only_kwh'))
        params=a.get('energy',{}).get('parameters',{})
        def pct(name):
            v=params.get(name)
            return interval({'low':v['low']*100,'high':v['high']*100},'%',0) if v else 'неизвестно'
        if heat and electric and not form_changed and not use_changed:p.append(t(f"Варианты при заданных условиях: тепло {heat} кВт·ч или электричество {electric} кВт·ч. Извлечение {pct('recovery_fraction')}, тепловой КПД {pct('thermal_efficiency')}, электрический {pct('electrical_efficiency')}; происхождение этих параметров указано в карточках.",
            f'Illustrative alternatives: heat {heat} kWh or electricity {electric} kWh. Selected recovery and efficiencies are scenarios, not device measurements.',
            f'Шартты баламалар: жылу {heat} кВт·сағ немесе электр {electric} кВт·сағ. Алу үлесі мен ПӘК — құрылғы өлшемдері емес, сценарийлер.'))
    else:p.append(t('Для этого состояния сырья пока нет применимого численного BMP-профиля; ранее рассчитанный потенциал не переносится.','No applicable numerical BMP profile is available for this material state.','Бұл шикізат күйіне сәйкес сандық BMP профилі жоқ.'))
    d=a.get('decision',{});selected=next((x for x in a.get('scenarios',[]) if x['id']==d.get('selected_scenario')),None)
    if d.get('status')=='PHYSICALLY_INFEASIBLE':p.append(t('Указанная одновременная загрузка не помещается в подтверждённый объём. Нужен другой план загрузок; это не запрет последовательной переработки.','The declared single charge violates vessel geometry; a different staged plan is needed.','Көрсетілген бір реттік жүктеме расталған көлемге сыймайды; бөлек жүктеу жоспары қажет.'))
    elif d.get('status')=='REQUIRES_SAFETY_REVIEW':p.append(t('До эксплуатационного решения требуется инженерная проверка безопасности.','Engineering safety review is required before an operating decision.','Пайдалану шешіміне дейін инженерлік қауіпсіздік тексеруі қажет.'))
    elif selected and selected.get('net_result_kzt') is not None:
        p.append(t(f"Условный чистый результат выбранного варианта: {interval(selected['net_result_kzt'],'₸')}. Статус: {d['status']}; это сравнение заданных условий, не гарантия прибыли.",
            f"Conditional net result: {interval(selected['net_result_kzt'],'KZT')}. Decision: {d['status']}; no profit guarantee.",
            f"Таңдалған нұсқаның шартты таза нәтижесі: {interval(selected['net_result_kzt'],'₸')}. Мәртебе: {d['status']}; пайдаға кепілдік жоқ."))
    elif selected and selected.get('break_even',{}).get('maximum_total_processing_cost_to_match_sale_kzt') is not None:
        budget=selected['break_even']['maximum_total_processing_cost_to_match_sale_kzt'];value=r.get('catalog_reference_value_kzt')
        reference=interval(value,'₸')
        p.append(t((f'Каталожный ориентир навоза: {reference}, не подтверждённый доход. ' if reference else '')+f"При сценарии {selected['id']} переработка превосходит этот ориентир, если ВСЕ затраты ниже соответствующего порога {interval(budget,'₸')}. "+(f"Для консервативного края сценария нужен бюджет ниже {budget['low']:.2f} ₸. " if budget['low']>0 else 'Победитель зависит от выхода и расходов. ')+ 'В оценке тепла по электрическому ориентиру предполагается замещение электроотопления, а не продажа газа.',
                   f"Processing can beat the sale comparator only below the total-cost threshold {interval(budget,'KZT')}, with the stated price/use assumptions. An asking value is not a confirmed sale; heat valuation assumes displaced resistance heating when no heat quote exists.",
                   f"Өңдеу барлық шығын {interval(budget,'₸')} шегінен төмен болса ғана сату бағдарынан тиімді болуы мүмкін. Каталог бағасы нақты табыс емес; жылу үшін электрмен жылытуды алмастыру болжанған."))
    else:p.append(t('Победитель пока не установлен: применимой цены или полного энергобаланса недостаточно. Карточки показывают, какие условия дают безубыточность.','No winner is established; eligible prices or energy inputs are missing. Break-even conditions remain in the cards.','Тиімді нұсқа анықталмады: сәйкес баға немесе энергия балансы жеткіліксіз. Өтелу шарттары карточкаларда.'))
    critical=[]
    if a.get('feasibility',{}).get('working_volume_l') is None:critical.append(t('рабочий объём и совместная загрузка','working volume and total charge','жұмыс көлемі мен толық жүктеме'))
    if a.get('reactor_balance',{}).get('status')!='ok':critical.append(t('реальные расходы на нагрев и оборудование','actual heating and auxiliary demand','нақты жылыту және жабдық шығыны'))
    if critical and not form_changed and not use_changed:p.append(t('Не установлены: ','Still unknown: ','Әлі белгісіз: ')+', '.join(critical)+t('. Полные 200 л не означают разрешённую загрузку; сценарии не записаны как измерения.' if state.value('reactor_total_volume_l')==200 else '. Сценарии не записаны как измерения.', '. Scenarios are separate from measured facts.', '. Сценарийлер өлшенген деректерден бөлек.'))
    state.last_research_summary=now
    return p
