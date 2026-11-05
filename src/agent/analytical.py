"""Evidence-scoped calculation tools and a result contract for partial analyses.

Unknown properties are considered in separate, named literature scenarios. They
are never written back into confirmed inventory or the existing profile store.
"""
import itertools
import re
from src.advisor import catalog,mixing
from src.advisor.schemas import AdvisorRequest,Component
from src.economics import complete_analysis,gas_composition
from src.economics.decision_schemas import DecisionInputs
from src.advisor.advanced_science import summary,proxy

TOOLS=['assess_substrate_potential','evaluate_partial_economics','assess_process_evidence']

def context(state):
    facts={k:v.value for k,v in {**state.derived,**state.facts}.items()}
    process_assumptions={k:v.value for k,v in state.assumptions.items() if k in {'dilution_water_l','temperature_c','reactor_total_volume_l','reactor_working_volume_l'}}
    facts.update(process_assumptions)
    import copy
    decision=copy.deepcopy(state.decision_settings)
    reactor=decision.setdefault('reactor',{})
    if process_assumptions:reactor['provenance']='HYPOTHETICAL_SCENARIO'
    for key in ['dilution_water_l','temperature_c','reactor_working_volume_l','inoculum_volume_l','headspace_l','operating_mode']:
        if facts.get(key) is not None:reactor[key]=facts[key]
    return {'facts':facts,'components':state.mixture_scenario_components or state.mixture_components,
            'decision':decision,'mode':state.analytical_mode,
            'language':state.language,'scenario_process_inputs':process_assumptions,
            'advisor_settings':dict(state.advanced.get('request_overrides') or {}) | dict(state.advisor_settings or {})}

def components(data):
    if data.get('components'):return [Component.model_validate(c) for c in data['components']]
    f=data['facts'];material=f.get('material');q=f.get('quantity');unit=f.get('unit')
    if q is None:q=f.get('mass_kg');unit='kg'
    if q is None:q=f.get('material_volume_l');unit='L'
    if not material or material=='mixture' or q is None:return []
    props={}
    for k,target,factor in [('ts_percent','ts_fraction',.01),('bmp_ml_ch4_g_vs','bmp_ml_g_vs',1),('density_kg_l','density_kg_l',1)]:
        if f.get(k) is not None:props[target]=f[k]*factor
    if f.get('vs_percent') is not None and f.get('vs_basis') in {'TS','fresh_mass'}:
        props['vs_fraction_of_ts' if f['vs_basis']=='TS' else 'vs_fraction_wet']=f['vs_percent']/100
    if f.get('vs_mass_kg') is not None and f.get('mass_kg'):
        props['vs_fraction_wet']=f['vs_mass_kg']/f['mass_kg']
    return [Component(id='c1',material=material,quantity=q,unit=unit or 'kg',
        material_state=f.get('material_state') or 'unknown',physical_state=f.get('physical_state') or 'unknown',
        decay_state=f.get('decay_state') or 'unknown',properties=props)]

from src.advisor.evidence_engine import variants, scientific_request

def scientific(data,store=None):
    cs=components(data)
    if not cs:
        facts=data['facts'];missing=[]
        if facts.get('material') in {None,'mixture'}:missing.append('material_identity_or_component_inventory')
        if not any(facts.get(k) is not None for k in ['quantity','mass_kg','material_volume_l']):missing.append('batch_quantity')
        available=[p['id'] for p in catalog.profiles() if p['material']==facts.get('material')]
        return {'status':'needs_input','message':'The local profile index was inspected; specific missing batch inputs are listed.',
                'missing':missing,'scenarios':[],'catalog_checked':True,'available_profile_ids':available,
                'known_quantity':facts.get('quantity',facts.get('mass_kg',facts.get('material_volume_l')))}
    settings=dict(data.get('advisor_settings') or {})
    settings.update(components=cs,decision=data['decision'],
        reactor_total_volume_l=data['facts'].get('reactor_total_volume_l',settings.get('reactor_total_volume_l')),
        region=data['facts'].get('market_region') or settings.get('region','KZ-Karaganda'),
        region_confirmed=bool(data['facts'].get('market_region')) or settings.get('region_confirmed',False))
    settings.setdefault('allow_conditional_profiles',True)
    settings.setdefault('assume_common_dry_gas_basis',any(c.data_mode!='MEASURED' for c in cs))
    result=scientific_request(AdvisorRequest.model_validate(settings),data['mode'],store=store)
    for s in result.get('scenarios',[]):
        for key,value in data.get('scenario_process_inputs',{}).items():
            s['assumptions'].append(f'User hypothetical process input {key}={value}; not a measured process change.')
    return result


def economics(data,results,store):
    science=results.get('assess_substrate_potential')
    if not science:return {'status':'needs_input','message':'Assess the substrate evidence before valuing gas.', 'missing':['assess_substrate_potential']}
    rows=[]
    from src.advisor.service import analyze_exact
    for s in science.get('scenarios',[]):
        r=AdvisorRequest.model_validate(s['request']);mix=s['mixture']
        analysis=analyze_exact(store,r,persist=False)['decision_analysis']
        rows.append({'id':s['id'],'label':s['label'],'analysis':analysis})
    leaders=[]
    if science.get('comparison_mode')=='alternatives':
        for s in science['scenarios']:
            if s['methane_m3'] and all(o['methane_m3'] and s['methane_m3']['low']>o['methane_m3']['high'] for o in science['scenarios'] if o['label']!=s['label']):
                leaders.append(s['label'])
    return {'status':'ok','message':'Available energy and price evidence valued; unknown costs are not zero.',
        'potential_dominates_other_material_scenarios':list(dict.fromkeys(leaders)),
        'scenarios':rows,'missing':['complete_operating_costs','capital_and_service_life_for_payback'],
        'profit_established':any(a.get('net_result_kzt') is not None and a.get('evidence_confirmed') for r in rows for a in r['analysis']['scenarios']),
        'region':data['facts'].get('market_region') or 'KZ-Karaganda','region_confirmed':bool(data['facts'].get('market_region'))}

def process(data):
    f=data['facts'];sources=[]
    from src.research.dossiers import search
    cs=components(data)
    materials=list(dict.fromkeys([c.material for c in cs] or ([f['material']] if f.get('material') else [])))
    dossiers=search(materials)['dossiers'] if materials else []
    studies=[];reference=None
    for dossier in dossiers:
        sources.extend(dossier['sources'])
        forms={c.material_state for c in cs if c.material==dossier['material']}
        for study in dossier['studies']:
            temperature=study.get('conditions',{}).get('temperature_c')
            if temperature is None:continue
            if temperature==35:reference=35
            if forms and 'unknown' not in forms and study['physical_state'] not in forms:continue
            studies.append({'profile_id':study['profile_id'],'source_id':study['source_id'],
                            'physical_state':study['physical_state'],'temperature_c':temperature,
                            'evidence_level':'PUBLISHED_EXPERIMENT_NOT_AN_OPERATING_SETPOINT'})
    heating_missing=[key for key in ['heated_mass_kg','initial_temperature_c','heat_capacity_kj_kg_k','heating_efficiency','heat_losses']
                     if f.get(key) is None and data.get('decision',{}).get('reactor',{}).get(key) is None]
    return {'status':'ok','message':'Process effects separated from unmeasured yield changes.',
        'temperature_c':f.get('temperature_c'),'dilution_water_l':f.get('dilution_water_l'),
        'added_water_vs_kg':0 if f.get('dilution_water_l') is not None else None,
        'added_water_methane_potential_m3':0 if f.get('dilution_water_l') is not None else None,
        'water_effect':'Clean water adds no organic VS; potential from the original feed remains unchanged. Actual conversion may change through dilution/inhibition; extra liquid requires capacity and heating checks.',
        'temperature_effect':'Temperature alone does not establish an optimum. Increasing it raises heat demand and may change kinetics and ammonia risk; gradual change requires acclimated inoculum and monitoring.',
        'matched_temperature_experiments':studies,
        'mesophilic_discussion_reference_c':reference,
        'reference_scope':'Around 35 C can be discussed as a mesophilic scenario where supported by the material corpus; the exact liquid/solid study conditions above take precedence. Neither is a validated optimum or automatic setpoint.',
        'heating_missing':heating_missing,
        'heating_formula':'Q = heated_mass_kg * heat_capacity_kj_kg_k * temperature_change_c / 3600 / efficiency',
        'missing':['substrate','current_gas_rate','pH_VFA_alkalinity','inoculum_adaptation','heat_losses_and_energy_cost'],
        'sources':sources,'actuator_access':False}

def execute(name,context,results,store):
    data=context['analytical_context']
    if name=='assess_substrate_potential':return scientific(data,store=store)
    if name=='evaluate_partial_economics':return economics(data,results,store)
    if name=='assess_process_evidence':return process(data)
    raise ValueError('Unknown analytical tool')

def span(value):
    if value is None:return 'не определено'
    return f"{value['low']:.5g}" if value['low']==value['high'] else f"{value['low']:.5g}–{value['high']:.5g}"

def observation(name,result):
    """Keep complete calculation values in a compact, bounded LLM observation."""
    if name=='assess_substrate_potential':
        return {k:v for k,v in result.items() if k not in {'scenarios','sources','local_experiments'}} | {'scenarios':[
            {k:s.get(k) for k in ['id','label','methane_m3','known_component_subtotal_m3','wet_mass_kg','ts_mass_kg','vs_mass_kg',
                'gas_basis','result_level','profile_ids','missing']} | {'assumptions':s.get('assumptions',[])[:3],
                'engineering':{k:s.get('engineering',{}).get(k) for k in ['status','violations','known_charge_volume_l','missing','necessary_mean_feed_density_kg_l']}}
                for s in result.get('scenarios',[])[:8]]}
    if name=='evaluate_partial_economics':
        return {'status':result['status'],'message':result['message'],'missing':result.get('missing',[]),
            'scenarios':[{'id':s['id'],'energy':s['analysis']['energy']['outputs'],
                'energy_assumptions':s['analysis']['energy']['parameters'],
                'prices':{k:{f:p.get(f) for f in ['status','value','region','age_days','source_url','published_at']} for k,p in s['analysis']['prices'].items() if p.get('value') is not None},
                'economic_scenarios':[{k:r.get(k) for k in ['id','status','gross_benefit_reference_kzt','net_result_kzt','break_even']} for r in s['analysis']['scenarios'] if r.get('gross_benefit_reference_kzt') or r.get('net_result_kzt')],
                'missing_costs':s['analysis']['operating_costs']['missing']} for s in result.get('scenarios',[])[:8]]}
    return result

def render(results,state):
    """Generic result projection, never a response matched to a test prompt."""
    if state.language!='ru':return render_international(results,state.language)
    parts=[];science=results.get('assess_substrate_potential',{});econ=results.get('evaluate_partial_economics',{})
    if science.get('comparison_mode')=='alternatives':parts.append('Сравниваю отдельные партии, без сложения их масс и доходов.')
    for s in science.get('scenarios',[]):
        p=f"{s['label']}, {span(s['wet_mass_kg'])} кг: "
        p+='условный сценарий по опубликованным образцам; ' if s['result_level']=='HYPOTHETICAL_SCENARIO' else 'расчёт по введённым данным; '
        if s['methane_m3'] is not None:p+=f"потенциал CH₄ {span(s['methane_m3'])} м³ при указанной базе газа. "
        elif s['known_component_subtotal_m3'] is not None:p+=f"только известная часть компонентов даёт {span(s['known_component_subtotal_m3'])} м³ CH₄; полный выход смеси неизвестен. "
        else:p+='численный потенциал не определён: нет совместимых TS, VS и BMP. '
        for c in s['components']:
            used=c['properties_used'];ts=used.get('ts_fraction',{}).get('range');vs=used.get('vs_fraction_wet',{}).get('range');bmp=used.get('bmp_ml_g_vs',{}).get('range')
            if bmp and c['vs_mass_kg']:
                p+=f"{catalog.name(c['material'])}: TS {span(ts)} кг/кг влажной массы; VS {span(vs)} кг/кг; масса VS {span(c['vs_mass_kg'])} кг; BMP {span(bmp)} мл CH₄/г VS. "
            if c.get('source'):p+=f"Источник: {c['source']['title']} ({c['source'].get('year','')}); профиль {c['profile_id']}, форма {c['material_state']}. "
            if c.get('source_stp_claimed') and c['gas_basis'] is None:
                p+='Источник обозначает STP без полного определения температуры и давления; общая база газа принята условно, коэффициент пересчёта не проверен. '
        if s['result_level']=='HYPOTHETICAL_SCENARIO':
            p+='Допущение: состав и подготовка вашей партии сопоставимы с данным образцом; это не измерение партии и не прогноз фактической выработки. Неизвестная влажность газа источника не измерена.'
        else:p+='Это вычисленный потенциал, а не измеренный выход установки.'
        if s['gas_basis']:
            b=s['gas_basis'];p+=f" Газовая база: {b['temperature_k']:g} K, {b['pressure_pa']:g} Па, {b['moisture']}."
        if not s['complete']:p+=' Недостающие параметры: '+', '.join(s['missing'])+'.'
        if len(s['components'])>1:p+=' Сумма аддитивная; синергия и ингибирование не рассчитаны.'
        gas=s['biogas']
        if gas['potential_biogas_m3'] is not None:
            p+=f" Общий биогаз {span(gas['potential_biogas_m3'])} м³ при доле CH₄ {span(gas['methane_fraction'])}; это отдельный сценарий состава газа, не измерение."
        elif s['methane_m3'] is not None:
            p+=' Общий биогаз = объём CH₄ / доля CH₄ при одинаковой газовой базе; без доли метана численный объём всего биогаза не определён.'
        e=s.get('engineering')
        if e:
            p+=f" Учтённый объём загрузки {span(e['known_charge_volume_l'] if e['known_charge_present'] else None)} л; статус геометрии {e['status']}. "
            if e['complete_charge_volume_l'] is None:p+='Это известная часть загрузки, не полный объём. '
            if e['remaining_total_volume_l'] is not None:p+=f"Остаток полного объёма {span(e['remaining_total_volume_l'])} л. "
            if e['violations']:p+='Нарушения: '+', '.join(e['violations'])+'. '
            if e['warnings']:p+='Ограничения: '+', '.join(e['warnings'])+'. '
            if e['missing']:p+='Для полной проверки загрузки нужны: '+', '.join(e['missing'])+'. '
            if e['feed_plus_water_ts_fraction']:p+=f"Доля TS сырья с добавленной водой {span(e['feed_plus_water_ts_fraction'])}; состав инокулюма не включён. "
        parts.append(p)
    if science.get('reactor_total_volume_l'):
        parts.append(f"Объём реактора {science['reactor_total_volume_l']:g} л ограничивает загрузку, но не задаёт выход метана. Нужны рабочий объём, объём инокулята и воды, запас газового пространства; вся ёмкость не считается массой нагреваемой жидкости.")
    for row in econ.get('scenarios',[]):
        a=row['analysis'];energy=a['energy'];out=energy['outputs'];p=f"Энергия и экономика ({row['id']}): "
        if out:
            p+=f"валовая энергия топлива {span(out['potential_fuel_kwh'])} кВт·ч; тепло {span(out['heat_only_kwh'])} кВт·ч ИЛИ электричество {span(out['electricity_only_kwh'])} кВт·ч. "
            ps=energy['parameters'];p+=f"Условные параметры: извлечение {span(ps['recovery_fraction'])}, КПД тепла {span(ps['thermal_efficiency'])}, электричества {span(ps['electrical_efficiency'])}; LHV {energy['heating_value']['value']:g} кВт·ч/м³ CH₄. "
        price=a['prices']['electricity'];v=price.get('value') if price['status'] not in {'missing','unusable'} else None;obs=price.get('observation',{})
        if v is not None:
            p+=f"Сохранённый ориентир электричества {v:g} KZT/кВт·ч; дата {price.get('published_at') or obs.get('published_at')}, регион {econ.get('region')}, источник {price.get('source')}. "
            if 'stale_reference' in price.get('reasons',[]) or obs.get('is_stale'):p+='Цена устарела и не является текущим тарифом. '
            if obs.get('age_days') is not None:p+=f"Возраст ценового наблюдения {obs['age_days']} дней. "
            if not econ.get('region_confirmed'):p+='Регион принят условно, пользователем не подтверждён. '
        for alt in a['scenarios']:
            if alt['id']=='A_sell_feedstock':
                sale=alt.get('confirmed_buyer_gross_offer_kzt') or alt.get('reference_asking_value_kzt')
                if sale:
                    p+=f"Продажа исходного сырья: {span(sale)} KZT как {'подтверждённое валовое предложение' if alt.get('confirmed_buyer_gross_offer_kzt') else 'условный ориентир цены предложения, а не подтверждённая закупка'}. Расходы продажи и наличие покупателя требуют проверки. "
            budget=(alt.get('break_even') or {}).get('maximum_total_processing_cost_to_match_sale_kzt')
            if budget is not None:
                p+=f"{alt['id']}: условный порог всех затрат переработки для сравнения с продажей {span(budget)} KZT; это валовая ценность минус принятый ориентир продажи, не прибыль. "
            if alt['id'] in {'B_heat','C_electricity'} and alt.get('gross_benefit_reference_kzt') is not None:
                label='Тепло' if a['prices']['heat']['status'] not in {'missing','unusable'} else 'Замещение электронагрева'
                p+=f"{label if alt['id']=='B_heat' else 'Электричество'}: валовая ценность {span(alt['gross_benefit_reference_kzt'])} KZT при принятом сценарии потребления. "
        if v is None and out:p+=f"При применимой цене P KZT/кВт·ч ценность электричества = ({span(out['electricity_only_kwh'])}) × P; цену не подставляю без источника. "
        net=[alt for alt in a['scenarios'] if alt.get('net_result_kzt') is not None]
        if net:
            p+='Чистый результат по введённым параметрам: '+', '.join(alt['id']+' '+span(alt['net_result_kzt'])+' KZT' for alt in net)+'. Это условный расчёт; окупаемость требует отдельной проверки инвестиций и эксплуатации.'
        else:
            p+='Прибыль и окупаемость не установлены: не подтверждён полный баланс подогрева и перемешивания, всех расходов и капитальных затрат. Неизвестные затраты не равны нулю.'
            if a['operating_costs'].get('known_subtotal'):
                p+=' Учтённая часть эксплуатационных расходов: '+span(a['operating_costs']['known_subtotal'])+' KZT; это не полные затраты.'
            if a['operating_costs']['missing']:p+=' Недостающие статьи: '+', '.join(a['operating_costs']['missing'])+'.'
        p+=' Цена природного газа не используется как цена продажи сырого биогаза.'
        parts.append(p)
    if econ.get('potential_dominates_other_material_scenarios'):
        parts.append('В рассмотренных литературных сценариях больший метановый потенциал имеет: '+', '.join(econ['potential_dominates_other_material_scenarios'])+'. При одинаковых КПД это даёт больше энергии. Самый прибыльный вариант не установлен: нужны сопоставимые цены продажи сырья и полные затраты каждой партии.')
    proc=results.get('assess_process_evidence',{})
    if proc.get('matched_temperature_experiments'):
        temperatures=sorted({s['temperature_c'] for s in proc['matched_temperature_experiments']})
        p='Совместимые по форме опубликованные опыты проводились при '+', '.join(f'{v:g}' for v in temperatures)+' °C. Это условия исследований, не установленный оптимум вашей установки.'
        if proc.get('mesophilic_discussion_reference_c') is not None:
            p+=f" Около {proc['mesophilic_discussion_reference_c']:g} °C можно рассмотреть как мезофильный сценарий; наличие такого опыта для другого состояния навоза не подтверждает переносимость его режима."
        p+=' Перед выбором уставки нужны адаптация инокулята, pH/VFA, стабильность газовыделения и тепловой баланс. Исполнительные устройства агент не включает.'
        if proc.get('heating_missing'):
            p+=' Нагрев: Q = m × c × (Tцель − Tнач) / (3600 × КПД) плюс теплопотери; численный расход пока не определён. Нужны фактическая нагреваемая загрузка с водой и инокулятом, начальная температура, теплоёмкость, КПД и теплопотери; номинальная ёмкость не заменяет массу загрузки.'
        parts.append(p)
    if proc.get('dilution_water_l') is not None:
        parts.append(f"Добавление {proc['dilution_water_l']:g} л чистой воды добавляет 0 кг VS и 0 м³ потенциала CH₄: потенциал исходного сырья не увеличивается. Разбавление меняет концентрацию и может влиять на реальное сбраживание; дополнительную воду нужно разместить и нагреть.")
    if proc.get('temperature_c') is not None:
        parts.append(f"Сообщённая температура {proc['temperature_c']:g} °C сама по себе не обосновывает её повышение. Подогрев повышает энергозатраты, влияет на скорость процесса и аммиачный риск; оптимум без данных о сырье, инокуляте, pH и динамике газа не определён. Следует оценить теплопотери и устойчивость процесса до изменения режима.")
    if not parts and science.get('catalog_checked'):parts.append('Каталог проверен; для расчёта партии отсутствуют: '+', '.join(science.get('missing',[]))+'. Без применимого профиля численные свойства не назначаются; возможен отдельный условный расчёт с явно заданными TS, VS и BMP.')
    for name,result in results.items():
        if name in TOOLS and result.get('status')=='error':
            parts.append('Ошибка инструмента '+name+': '+result.get('message','неизвестная ошибка')+'. Доступные результаты выше сохранены; ошибка не означает отсутствия научных данных.')
    question='Какой состав и влажность у сырья вашей партии?'
    if econ:
        # Ask only for an unresolved input. Region is a structured session fact;
        # once supplied, it must not keep reappearing after every recalculation.
        if not state.facts.get('market_region'):
            question='В каком регионе находится установка?'
        elif 'complete_operating_costs' in econ.get('missing',[]):
            question='Какие полные расходы на эту партию: подготовка, транспорт, нагрев и обслуживание?'
        else:question='Какой подтверждённый рабочий объём реактора, отдельно от номинального?'
    elif proc.get('temperature_c') is not None:question='Какое сырьё и инокулят сейчас находятся в реакторе?'
    elif science.get('scenarios') and any(c['material'].endswith('_manure') for s in science['scenarios'] for c in s['components']):question='Навоз жидкий, твёрдый или с подстилкой?'
    if parts:parts.append(question)
    return '\n\n'.join(parts)


def user_facing(results,state):
    """Create a short, sectioned answer; detailed provenance stays in tool data."""
    lang=state.language
    t={
        'ru':{'short':'Краткий результат','gas':'Потенциал метана','energy':'Энергетическая ценность','economics':'Экономика','risks':'Ограничения и риски',
              'unknown':'не определён по имеющимся данным','conditional':'условный литературный сценарий, не измерение вашей партии',
              'calculated':'расчёт из введённых свойств, не измерение выхода установки','partial':'только известная часть; полный выход смеси не установлен',
              'profit':'Прибыль не подтверждена: нужны полные расходы и капитальные затраты. Неизвестные расходы не считаются нулевыми.',
              'region':'В каком регионе находится установка?','costs':'Какие полные расходы на эту партию: подготовка, транспорт, нагрев и обслуживание?',
              'feed':'Каково физическое состояние и влажность сырья?','working':'Какой подтверждённый рабочий объём реактора, отдельно от номинального?',
              'gas_unknown':'Потенциал метана не рассчитан: нет совместимого профиля и свойств партии.'},
        'en':{'short':'Short result','gas':'Methane potential','energy':'Energy value','economics':'Economics','risks':'Limits and risks',
              'unknown':'unavailable from current evidence','conditional':'conditional literature scenario, not a measurement of your batch',
              'calculated':'calculated from supplied properties, not measured plant output','partial':'known components only; total mixture output is unavailable',
              'profit':'Profit is not established: full operating and capital costs are needed. Unknown costs are not zero.',
              'region':'Which region is the installation in?','costs':'What are the full batch costs for preparation, transport, heating and service?',
              'feed':'What are the feedstock physical form and moisture?','working':'What is the confirmed working volume, separately from nominal capacity?',
              'gas_unknown':'Methane potential is unavailable: no compatible profile and feed properties were found.'},
        'kk':{'short':'Қысқаша нәтиже','gas':'Метан әлеуеті','energy':'Энергетикалық құндылық','economics':'Экономика','risks':'Шектеулер мен тәуекелдер',
              'unknown':'қолдағы деректермен анықталмады','conditional':'шартты әдеби сценарий, сіздің партияңыздың өлшемі емес',
              'calculated':'енгізілген қасиеттер бойынша есеп, қондырғыдағы өлшем емес','partial':'тек белгілі бөлігі; қоспаның толық шығымы белгісіз',
              'profit':'Пайда расталмады: толық пайдалану және капитал шығындары қажет. Белгісіз шығын нөлге тең емес.',
              'region':'Қондырғы қай өңірде орналасқан?','costs':'Осы партияны дайындау, тасымалдау, жылыту және қызмет көрсету шығындары қандай?',
              'feed':'Шикізаттың физикалық күйі мен ылғалдылығы қандай?','working':'Номиналды көлемнен бөлек расталған жұмыс көлемі қандай?',
              'gas_unknown':'Метан әлеуеті анықталмады: сәйкес профиль мен партия қасиеттері табылмады.'}
    }[lang]
    science=results.get('assess_substrate_potential',{});econ=results.get('evaluate_partial_economics',{})
    scenarios=science.get('scenarios',[]);sources=[];modes=[]
    if scenarios:
        gas=[]
        for s in scenarios:
            if s.get('methane_m3') is not None:
                gas.append(f"{s.get('label','Сценарий')}: {span(s['methane_m3'])} м³ CH₄" if lang=='ru' else f"{s.get('label','Scenario')}: {span(s['methane_m3'])} m³ CH₄")
            elif s.get('known_component_subtotal_m3') is not None:
                gas.append(f"{s.get('label','Сценарий')}: {span(s['known_component_subtotal_m3'])} м³ CH₄ ({t['partial']})")
            else:gas.append(t['gas_unknown'])
            if s.get('result_level')=='HYPOTHETICAL_SCENARIO':modes.append('HYPOTHETICAL_SCENARIO')
            elif s.get('result_level')=='MEASURED':modes.append('MEASURED')
            else:modes.append('LITERATURE_ESTIMATE')
            for component in s.get('components',[]):
                source=component.get('source')
                if source and source.get('url'):sources.append({'title':source.get('title',source.get('id','Source')),'url':source['url']})
        gas_body='; '.join(gas)+'. '+(t['conditional'] if 'HYPOTHETICAL_SCENARIO' in modes else t['calculated'])
    else:
        gas_body=t['gas_unknown']
        if lang=='ru' and 'batch_quantity' in science.get('missing',[]) and science.get('available_profile_ids'):
            gas_body='Опубликованные профили найдены; объём метана для партии не рассчитан, поскольку её количество не указано.'
    sections=[{'title':t['short'],'body':gas[0] if scenarios and gas else gas_body},
              {'title':t['gas'],'body':gas_body}]
    energy=[]
    for row in econ.get('scenarios',[]):
        out=row.get('analysis',{}).get('energy',{}).get('outputs',{})
        value=out.get('potential_fuel_kwh')
        if value is not None:
            item=f"{span(value)} kWh fuel-equivalent"
            if lang=='ru':
                item+=f"; условное полезное тепло {span(out.get('heat_only_kwh'))} кВт·ч ИЛИ электричество {span(out.get('electricity_only_kwh'))} кВт·ч при принятых извлечении и КПД"
            energy.append(item)
    sections.append({'title':t['energy'],'body':'; '.join(energy) if energy else t['unknown']+'. '+('Нужна измеренная доля CH₄ и условия преобразования.' if lang=='ru' else 'A methane fraction and conversion efficiency are needed.' if lang=='en' else 'Метан үлесі мен түрлендіру ПӘК қажет.')})
    net=[alt.get('net_result_kzt') for row in econ.get('scenarios',[]) for alt in row.get('analysis',{}).get('scenarios',[]) if alt.get('net_result_kzt') is not None]
    if net:eco_body=('Расчётный чистый результат: ' if lang=='ru' else 'Calculated net result: ')+', '.join((span(x) if isinstance(x,dict) else f'{x:g}')+' KZT' for x in net)+'.'
    elif econ:eco_body=t['profit']
    else:eco_body=t['unknown']
    if net and not econ.get('profit_established'):
        eco_body=('Условный сценарий. ' if lang=='ru' else 'Conditional scenario. ')+eco_body
    gross=[]
    labels={'B_heat':'тепло / замещение электронагрева','C_electricity':'электричество','CHP':'когенерация'}
    for row in econ.get('scenarios',[])[:1]:
        for alt in row.get('analysis',{}).get('scenarios',[]):
            value=alt.get('gross_benefit_reference_kzt')
            if value is not None:
                gross.append(f"{labels.get(alt['id'],alt['id']) if lang=='ru' else alt['id']}: {span(value)} KZT")
    if gross:
        eco_body+=' '+('Условная валовая ценность до расходов: ' if lang=='ru' else 'Conditional gross value before costs: ')+'; '.join(gross)+'. '
        eco_body+=('Это альтернативы одного газового потока; доходы не складываются. Это также условный потолок суммарных затрат до учёта альтернативной продажи сырья. Дата, возраст и применимость сохранённых цен указаны в научных подробностях.' if lang=='ru' else 'These are alternative uses of one gas stream, not additive revenues. Values are also conditional total-cost ceilings before the feedstock-sale opportunity cost; verify price age and applicability in the details.')
        uncertain=any(p.get('value') is not None and p.get('status')!='confirmed' for row in econ.get('scenarios',[])[:1] for role,p in row['analysis'].get('prices',{}).items() if role in {'electricity','heat'})
        if uncertain:eco_body+=' '+('Использован сохранённый ценовой ориентир; текущий тариф не подтверждён.' if lang=='ru' else 'A stored price reference was used; a current applicable tariff is not established.')
    sections.append({'title':t['economics'],'body':eco_body})
    risks=[]
    for row in scenarios:
        eng=row.get('engineering') or {}
        risks.extend(eng.get('warnings',[]));risks.extend(eng.get('violations',[]))
    if science.get('reactor_total_volume_l'):
        risks.append(f"{science['reactor_total_volume_l']:g} л — номинальная ёмкость; она не задаёт рабочую загрузку или выход метана." if lang=='ru' else f"{science['reactor_total_volume_l']:g} L is vessel capacity, not feed capacity or methane yield.")
    sections.append({'title':t['risks'],'body':'; '.join(dict.fromkeys(risks)) if risks else (t['conditional'] if 'HYPOTHETICAL_SCENARIO' in modes else t['calculated'])})
    question=None
    if not scenarios and 'batch_quantity' in science.get('missing',[]):
        question={'id':'batch-quantity','text':'Какова масса партии в килограммах?','options':[],'fields':['quantity','unit'],'reason':'A batch quantity is needed to scale published sample evidence.'}
    elif econ and not state.facts.get('market_region'):
        question={'id':'market-region','text':t['region'],'options':[],'fields':['market_region'],'reason':'Region affects which stored market observations are applicable.'}
    elif econ and 'complete_operating_costs' in econ.get('missing',[]):
        question={'id':'operating-costs','text':t['costs'],'options':[],'fields':['operating_costs'],'reason':'Full costs are required to establish net profit.'}
    elif any('reactor_working_volume_l' in (s.get('engineering') or {}).get('missing',[]) for s in scenarios):
        question={'id':'working-volume','text':t['working'],'options':[],'fields':['reactor_working_volume_l'],'reason':'Nominal volume does not establish safe working capacity.'}
    elif scenarios and not any(s.get('complete') for s in scenarios):
        question={'id':'feed-state','text':t['feed'],'options':[],'fields':['material_state'],'reason':'Physical form and moisture determine profile transfer.'}
    return {'sections':sections,'question':question,'sources':list({x['url']:x for x in sources}.values()),
            'modes':list(dict.fromkeys(modes)),'assumptions':list(state.assumptions)}


def render_international(results,language):
    """The same evidence contract for the pre-existing English/Kazakh UI."""
    def t(en,kk):return kk if language=='kk' else en
    def value(v):return span(v) if v is not None else t('unavailable','анықталмаған')
    parts=[];science=results.get('assess_substrate_potential',{});econ=results.get('evaluate_partial_economics',{})
    if science.get('comparison_mode')=='alternatives':parts.append(t('These are separate feedstock alternatives, not a combined mixture.','Бұл — бөлек шикізат нұсқалары, біріктірілген қоспа емес.'))
    for s in science.get('scenarios',[]):
        names=' + '.join(catalog.name(c['material'],language) for c in s['components'])
        p=f"{names}: {value(s['wet_mass_kg'])} kg; CH₄ {value(s['methane_m3'])} m³. "
        p+=t('Calculated potential under stated inputs or literature-transfer assumptions; not measured plant output or a calibrated prediction interval. ','Берілген деректер не әдебиеттен көшіру болжамдары бойынша есептелген әлеует; қондырғының өлшенген шығымы немесе тексерілген болжам аралығы емес. ')
        for c in s['components']:
            bmp=c['properties_used'].get('bmp_ml_g_vs',{}).get('range')
            p+=f"VS {value(c['vs_mass_kg'])} kg; BMP {value(bmp)} mL CH₄/g VS. "
            if c.get('source'):p+=c['source']['title']+'; '+c['source']['url']+'. '
        if s['gas_basis']:
            b=s['gas_basis'];p+=f"{b['temperature_k']:g} K, {b['pressure_pa']:g} Pa, {b['moisture']}. "
        if s['result_level']=='HYPOTHETICAL_SCENARIO':p+=t('Assumes comparable composition/preparation and dry source gas where moisture is unreported. ','Құрамы мен дайындалуы салыстырмалы, ал ылғалы белгісіз бастапқы газ құрғақ деп шартты қабылданған. ')
        if s['methane_m3'] is None:p+=t('Known-component subtotal only: ','Тек белгілі компоненттер қосындысы: ')+value(s['known_component_subtotal_m3'])+' m³. '
        p+=t('Total biogas also needs a compatible methane fraction; mixture synergy and inhibition are not predicted.','Жалпы биогаз үшін сәйкес метан үлесі қажет; қоспаның синергиясы мен тежелуі болжанбайды.')
        parts.append(p)
    if science.get('reactor_total_volume_l'):
        parts.append(f"{science['reactor_total_volume_l']:g} L: "+t('total vessel capacity limits loading, not methane potential. Working volume, inoculum, dilution and headspace are still needed.','реактордың толық көлемі жүктемені шектейді, метан әлеуетін анықтамайды. Жұмыс көлемі, инокулят, сұйылту және газға бос орын қажет.'))
    for row in econ.get('scenarios',[]):
        a=row['analysis'];out=a['energy']['outputs'];p=row['id']+': '
        if out:
            p+=t('Fuel / useful heat / electricity: ','Отын / пайдалы жылу / электр: ')+' / '.join(value(out[k]) for k in ['potential_fuel_kwh','heat_only_kwh','electricity_only_kwh'])+' kWh. '
            ps=a['energy']['parameters'];p+=t('Scenario recovery / thermal efficiency / electric efficiency: ','Сценарийдегі қалпына келтіру / жылу ПӘК / электр ПӘК: ')+' / '.join(value(ps[k]) for k in ['recovery_fraction','thermal_efficiency','electrical_efficiency'])+'. '
        for alt in a['scenarios']:
            if alt.get('gross_benefit_reference_kzt') is not None:p+=alt['id']+' '+value(alt['gross_benefit_reference_kzt'])+' KZT '+t('gross value, before costs. ','шығынға дейінгі жалпы құн. ')
        price=a['prices']['electricity'];obs=price.get('observation',{})
        if price['status'] not in {'missing','unusable'}:
            p+=f"{price['value']:g} KZT/kWh; {econ['region']}; {price.get('published_at') or obs.get('published_at')}; {price.get('source')}. "
            if obs.get('is_stale') or 'stale_reference' in price.get('reasons',[]):p+=t('Stale reference, not a current tariff. ','Ескірген бағдар, ағымдағы тариф емес. ')
        elif out:p+=t('Unpriced electricity value = ','Бағасы белгісіз электр құны = ')+value(out['electricity_only_kwh'])+' × P KZT/kWh. '
        p+=t('Alternatives must not be added together. Profit/payback need complete energy costs, operating costs and capital inputs. Missing costs are not zero. Natural gas prices do not price raw biogas.','Баламалар қосылмайды. Пайда мен өтелімділік үшін толық энергия, пайдалану және капитал шығындары қажет. Белгісіз шығын нөл емес. Табиғи газ бағасы шикі биогаз бағасы емес.')
        parts.append(p)
    proc=results.get('assess_process_evidence',{})
    if proc.get('dilution_water_l') is not None:parts.append(f"{proc['dilution_water_l']:g} L "+t('clean water adds 0 kg VS and 0 m³ methane potential; actual conversion, loading and heat demand can change.','таза су 0 kg VS және 0 m³ метан әлеуетін қосады; нақты ыдырау, жүктеме және жылу қажеттілігі өзгеруі мүмкін.'))
    if proc.get('temperature_c') is not None:parts.append(f"{proc['temperature_c']:g} °C: "+t('temperature alone cannot establish an optimum. Check heat losses, inoculum adaptation, pH and gas production before changing the regime.','тек температура оңтайлы режимді анықтамайды. Өзгертпес бұрын жылу шығынын, инокуляттың бейімделуін, pH пен газ өндірісін тексеру қажет.'))
    for name,r in results.items():
        if r.get('status')=='error':parts.append(name+': '+r.get('message','error'))
    if not parts:parts.append(t('Evidence was checked; batch identity/quantity or compatible TS, VS, BMP and gas reference are missing. No values were invented.','Деректер тексерілді; шикізат түрі/мөлшері не сәйкес TS, VS, BMP және газ базасы жетіспейді. Мәндер ойдан алынған жоқ.'))
    parts.append(t('Which region is the installation in?','Қондырғы қай өңірде орналасқан?') if econ else t('What is the physical form and moisture of the feedstock?','Шикізаттың физикалық түрі мен ылғалдылығы қандай?'))
    return '\n\n'.join(parts)

def obligations(state,text):
    intents=set(state.intents);f=context(state)['facts'];has_batch=bool(state.mixture_components or state.mixture_scenario_components or f.get('quantity') or f.get('mass_kg'))
    wanted=[]
    if has_batch and re.search(r'гарантир|без\s+допущен|guarantee|without\s+assumption',text,re.I):
        # An explicit demand for certainty does not authorize silently adopting
        # a literature sample. Inspect evidence and explain its actual scope.
        return ['search_substrate_profiles']
    calculation_question=bool(re.search(r'сколько|рассчита|расчет|расчёт|how much|calculate',text,re.I))
    if (has_batch or calculation_question) and (intents & {'methane_yield','economic_comparison','temperature_recommendation'} or re.search(r'пересчита|recalculat',text,re.I)):wanted.append('assess_substrate_potential')
    if intents & {'economic_comparison','temperature_recommendation'} and has_batch:wanted.append('evaluate_partial_economics')
    colloquial_calculation=calculation_question or bool(re.search(r'оцени|потенциал|estimate|potential',text,re.I))
    concentration_request=bool(re.search(r'concentration|концентраци',text,re.I)) and not re.search(r'methane|метан|биогаз|biogas',text,re.I)
    if has_batch and colloquial_calculation and not concentration_request and 'assess_substrate_potential' not in wanted:
        wanted.insert(0,'assess_substrate_potential')
    engineering_question=bool(re.search(r'загруз|вместим|осуществим|разбав|нагруз|риски|loading|capacity|feasib|dilut|risk',text,re.I)) or bool(set(state.assumptions)&{'reactor_total_volume_l','reactor_working_volume_l'})
    energy_question=bool(re.search(r'энерги|тепла|электрич|energy|electricity|useful heat',text,re.I))
    if has_batch and calculation_question and not re.search(r'concentration|концентраци',text,re.I) and re.search(r'\bTS\b|\bVS\b|сух\w* веществ|летуч\w* веществ',text,re.I) and 'assess_substrate_potential' not in wanted:
        wanted.insert(0,'assess_substrate_potential')
    if has_batch and engineering_question and 'assess_substrate_potential' not in wanted:
        wanted.insert(0,'assess_substrate_potential')
    if has_batch and energy_question:
        if 'assess_substrate_potential' not in wanted:wanted.insert(0,'assess_substrate_potential')
        if 'evaluate_partial_economics' not in wanted:wanted.append('evaluate_partial_economics')
    concentration_only=bool(re.search(r'concentration|концентраци',text,re.I)) and not re.search(r'methane|метан|биогаз|biogas',text,re.I)
    if (f.get('dilution_water_l') is not None and not concentration_only) or 'temperature_recommendation' in intents:wanted.append('assess_process_evidence')
    return wanted
