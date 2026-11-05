"""Bounded, evidence-grounded tool loop for the conversational agent."""
import json
import re
import os
import time
from src.agent.providers import ProviderError,TOOL_DESCRIPTIONS
from src.agent.tools import TOOL_NAMES
from src.agent import analytical

# The registry allowlist remains the authority. Tools that persist optimizer runs
# are excluded from autonomous chat; the agent can only read/compute here.
AUTONOMOUS_TOOLS=[name for name in TOOL_NAMES if name not in {
    'optimize_process','generate_process_scenarios','compare_process_scenarios',
}]
MAX_TOOL_CALLS=3


def _state_payload(state):
    def facts(rows):
        return {k:{'value':v.value,'unit':v.unit,'provenance':v.provenance,'evidence':v.evidence[:180]}
            for k,v in rows.items()}
    def components(rows):
        keep={'id','material','material_state','quantity','unit','animal','poultry_type','physical_state',
            'decay_state','bedding','data_mode','provenance','properties'}
        return [{k:v for k,v in row.items() if k in keep} for row in rows]
    return {
        'language':state.language,
        'intents':state.intents,
        'confirmed_facts':facts(state.facts),
        'derived_facts':facts(state.derived),
        'scenario_assumptions':facts(state.assumptions),
        'model_estimates':facts(state.estimates),
        'verified_sources':facts(state.source_verified),
        'pending_question':state.pending_question.model_dump(mode='json') if state.pending_question else None,
        'mixture_components':components(state.mixture_components),
        'mixture_scenario_components':components(state.mixture_scenario_components),
        'decision_settings':state.decision_settings,
        'input_conflicts':state.advanced.get('input_conflicts',[]),
    }


def _tool_context(agent,name,query,arguments):
    from src.agent.dialogue_memory import tool_context
    from src.agent import advisor_bridge,process_bridge,research_bridge
    context=tool_context(agent.state)
    if name=='calculate_vs_concentration' and 'dilution_water_l' in agent.state.assumptions:
        context['dilution_water_l']=agent.state.assumptions['dilution_water_l'].value
        context['scenario_input_provenance']={'dilution_water_l':'ASSUMED_FOR_SCENARIO'}
    from src.agent.scientific_tools import TOOLS as SCIENTIFIC_TOOLS
    if name in analytical.TOOLS or name in SCIENTIFIC_TOOLS:
        context['analytical_context']=analytical.context(agent.state)
    if name=='advise_substrate_conditions' and arguments.get('topics'):
        context['topics']=arguments['topics']
    advisor_tools={'get_substrate_catalog','analyze_substrate_mixture','compare_substrate_mixtures',
        'estimate_substrate_gas','advise_substrate_conditions','convert_substrate_units',
        'estimate_advanced_gas','estimate_advanced_energy','evaluate_advanced_economics',
        'get_matched_substrate_conditions'}
    if name in advisor_tools and name!='get_substrate_catalog':
        # Adapt explicit single-substrate dialogue facts to the same typed
        # schema used by the mixture builder. Never invent a batch quantity.
        try:
            request_state=agent.state.model_copy(deep=True)
            if not request_state.mixture_components and not request_state.mixture_scenario_components:
                material=request_state.value('material')
                quantity=request_state.value('quantity');unit=request_state.value('unit')
                if quantity is None and request_state.value('mass_kg') is not None:
                    quantity=request_state.value('mass_kg');unit='kg'
                elif quantity is None and request_state.value('material_volume_l') is not None:
                    quantity=request_state.value('material_volume_l');unit='L'
                if material and material!='mixture' and quantity is not None and unit:
                    from src.advisor.schemas import Component
                    properties={}
                    value=request_state.value('density_kg_l')
                    if value is not None:properties['density_kg_l']=value
                    value=request_state.value('ts_percent')
                    if value is not None:properties['ts_fraction']=value/100
                    value=request_state.value('vs_percent')
                    basis=request_state.value('vs_basis')
                    if value is not None and basis=='TS':properties['vs_fraction_of_ts']=value/100
                    elif value is not None and basis=='fresh_mass':properties['vs_fraction_wet']=value/100
                    value=request_state.value('bmp_ml_ch4_g_vs')
                    if value is not None:properties['bmp_ml_g_vs']=value
                    component=Component(id='dialogue-component',material=material,quantity=quantity,unit=unit,
                        material_state=request_state.value('material_state','unknown'),properties=properties,
                        evidence='Adapted from explicitly parsed dialogue facts')
                    request_state.mixture_components=[component.model_dump(mode='json')]
                    request_state.advisor_inventory_mode='single'
            context['advisor_request']=advisor_bridge.request_data(request_state).model_dump(mode='json')
        except (ValueError,TypeError,KeyError):
            pass
    if name in {'analyze_process_constraints','estimate_process_energy','explain_optimization'}:
        try:context['process_request']=process_bridge.request_data(agent.state)
        except (ValueError,TypeError,KeyError):pass
    if name in {'research_scientific_evidence','research_market_offers','estimate_from_literature','research_and_estimate'}:
        try:
            context['research_request']=research_bridge.request_data(agent.state)
            # Autonomous chat uses the local reviewed RAG store. Live web
            # retrieval remains an explicit research operation, not a hidden
            # side effect of ordinary conversation.
            context['research_request']['online']=False
        except (ValueError,TypeError,KeyError):pass
    return context


def _number_values(value):
    """Collect numeric evidence recursively for a conservative answer check."""
    values=set()
    def visit(item):
        if isinstance(item,bool) or item is None:return
        if isinstance(item,(int,float)):
            values.add(round(float(item),6));return
        if isinstance(item,dict):
            for key,val in item.items():visit(key);visit(val)
        elif isinstance(item,(list,tuple)):
            for val in item:visit(val)
        elif isinstance(item,str):
            for token in re.findall(r'(?<![A-Za-z])[-+]?\d+(?:[.,]\d+)?',item):
                try:values.add(round(float(token.replace(',','.')),6))
                except ValueError:pass
    visit(value)
    return values


def _numeric_units(results):
    units={'m3':set(),'m3_per_kg_vs':set(),'kg':set(),'kg_vs':set(),'bmp_ml_g_vs':set()}
    def add(target,value):
        if isinstance(value,bool):return
        if isinstance(value,(int,float)):units[target].add(round(float(value),6));return
        if isinstance(value,dict):
            for key in ('low','high','value'):
                if key in value:add(target,value[key])
    def visit(value):
        if isinstance(value,dict):
            for key,item in value.items():
                if key.endswith('_m3') or key in {'potential_biogas_m3','methane_reference_m3'}:add('m3',item)
                if key.endswith('_kg') or key in {'wet_mass_kg','total_wet_mass_kg'}:add('kg',item)
                if key=='vs_mass_kg':add('kg_vs',item)
                if key=='bmp_ml_g_vs':
                    add('bmp_ml_g_vs',item)
                    vals=item.values() if isinstance(item,dict) else [item]
                    for raw in vals:
                        if isinstance(raw,(int,float)) and not isinstance(raw,bool):units['m3_per_kg_vs'].add(round(raw/1000,6))
                visit(item)
        elif isinstance(value,list):
            for item in value:visit(item)
    visit(results)
    return units


def _unsupported_numbers(answer,state,results):
    evidence=_number_values({'state':_state_payload(state),'results':results})
    unsupported=[]
    for token in re.findall(r'(?<![A-Za-z])[-+]?\d+(?:[.,]\d+)?',answer):
        try:number=float(token.replace(',','.'))
        except ValueError:continue
        decimals=len(re.search(r'[.,](\d+)$',token).group(1)) if re.search(r'[.,](\d+)$',token) else 0
        display_rounding=0.5*(10**-decimals)
        if not any(abs(number-known)<=max(display_rounding,1e-5,abs(known)*1e-5) for known in evidence):
            unsupported.append(token)
    return list(dict.fromkeys(unsupported))


def _numbers_are_grounded(answer,state,results):return not _unsupported_numbers(answer,state,results)


def grounded_text(answer,state,results):
    return bool(answer) and not (_unsupported_numbers(answer,state,results)+_unsupported_units(answer,results))


def _mentions_calculated_quantity(answer,bounds,unit_pattern):
    values=[float(v[k]) for v in bounds if isinstance(v,dict) for k in ('low','high') if isinstance(v.get(k),(int,float))]
    for match in re.finditer(r'([-+]?\d+(?:[.,]\d+)?)\s*(?:'+unit_pattern+r')',answer,re.I):
        token=match[1];number=float(token.replace(',','.'))
        decimals=len(token.split('.')[-1]) if '.' in token else len(token.split(',')[-1]) if ',' in token else 0
        for value in values:
            tolerance=min(.5*10**-decimals,max(1e-6,abs(value)*.1))
            if abs(number-value)<=tolerance:return True
    return False


def _unsupported_conclusions(answer,results):
    issues=[]
    econ=results.get('evaluate_partial_economics',{})
    science=results.get('assess_substrate_potential',{})
    profiles=results.get('search_substrate_profiles',{}).get('dossiers',[])
    if (any(d.get('studies') for d in profiles) or science.get('available_profile_ids')) and re.search(r'BMP.{0,35}(?:отсутств|нет данных)|данные.{0,35}BMP.{0,25}отсутств',answer,re.I) and not re.search(r'ваш\w*\s+парти|your\s+batch',answer,re.I):
        issues.append('literature_absence_claim_despite_available_profiles')
    applicable=any(s.get('methane_m3') or s.get('known_component_subtotal_m3') for s in science.get('scenarios',[]))
    if science and not applicable and 'assess_process_evidence' not in results and re.search(r'\d+(?:[.,]\d+)?\s*(?:м³|м3|m3)\s*(?:CH[₄4]|метан|methane)',answer,re.I):
        issues.append('absolute_methane_without_applicable_batch_evidence')
    if econ and not econ.get('profit_established') and re.search(r'(?:заработаете|чистая прибыль составит|гарантированная прибыль|you will earn)\s*[:=]?\s*\d',answer,re.I):
        issues.append('profit_without_complete_confirmed_economics')
    net_known=any(r.get('net_result_kzt') is not None for s in econ.get('scenarios',[]) for r in s.get('analysis',{}).get('scenarios',[]))
    if econ and not net_known and re.search(r'\b(?:вероятно выгодно|переработка выгодна|производство выгодно|выгодно производить)\b',answer,re.I):
        issues.append('profitability_conclusion_without_net_cost_basis')
    if science.get('scenarios') and any(s['engineering']['status']!='GEOMETRY_ONLY_CONSISTENT' for s in science['scenarios']):
        if re.search(r'можно безопасно загрузить|загрузка безопасна|safe to load',answer,re.I):issues.append('safety_without_validated_loading')
    if any(s['engineering']['status']=='PHYSICALLY_INFEASIBLE' for s in science.get('scenarios',[])) and re.search(r'\b(?:можно загрузить|поместится|достаточно места|can load|fits into)\b',answer,re.I):
        issues.append('loading_conclusion_contradicts_calculated_capacity')
    if re.search(r'(?:гарантированно получите|точно получите|guaranteed yield)\s*[:=]?\s*\d',answer,re.I):
        issues.append('guaranteed_future_yield_not_established')
    return issues


def _bounded_action(agent,deadline,*args,**kwargs):
    remaining=deadline-time.perf_counter()
    if remaining<=0:raise ProviderError('resource_time_limit')
    provider=getattr(agent.llm,'active',None)
    previous=getattr(provider,'timeout',None)
    if previous is not None:provider.timeout=min(previous,remaining)
    try:return agent.llm.autonomous_action(*args,**kwargs)
    finally:
        if previous is not None:provider.timeout=previous


def _unsupported_units(answer,results):
    units=_numeric_units(results);bad=[]
    for match in re.finditer(r'(?<![A-Za-z])([-+]?\d+(?:[.,]\d+)?)(.{0,55})',answer):
        number=float(match.group(1).replace(',','.'));tail=match.group(2).casefold().replace('₄','4').replace('₃','3')
        if re.search(r'(?:m\s*(?:\^?3|3)|m³)\s*(?:ch4|methane|ch₄)?\s*(?:/|per)\s*kg\s*(?:vs|volatile solids)',tail):
            if not any(abs(number-known)<=max(1e-4,abs(known)*1e-3) for known in units['m3_per_kg_vs']):bad.append(match.group(1)+' m3/kg VS')
    for result in results.values():
        mixture=result.get('mixture') if isinstance(result,dict) else None
        if not isinstance(mixture,dict) or mixture.get('complete_methane_reference') is not False:continue
        partial=mixture.get('known_component_additive_subtotal_m3')
        if not partial:continue
        if any(abs(float(number.replace(',','.'))-float(partial['low']))<=max(1e-4,abs(float(partial['low']))*1e-3)
            for number in re.findall(r'(?<![A-Za-z])[-+]?\d+(?:[.,]\d+)?',answer)):
            if not re.search(r'known[- ]components?|known parts?|only\s+components?|partial|subtotal|partial reference|частичн|подытог|only components with|только для компонент\w*|компонент\w*.*(?:только|лишь|ғана|only)',answer,re.I):
                bad.append('incomplete_mixture_total_scope')
    return list(dict.fromkeys(bad))


def _sources(results):
    found={}
    def visit(value):
        if isinstance(value,dict):
            for row in value.get('sources',[]) if isinstance(value.get('sources'),list) else []:
                if isinstance(row,dict):
                    url=row.get('url') or row.get('source_url')
                    title=row.get('title') or row.get('id')
                    if isinstance(url,str) and url.startswith(('https://','http://')) and title:
                        found[url]={'title':str(title),'url':url}
            for val in value.values():visit(val)
        elif isinstance(value,list):
            for val in value:visit(val)
    visit(results)
    return list(found.values())[:20]


def _fallback_answer(results,state):
    if any(name in results for name in analytical.TOOLS):
        rendered=analytical.render(results,state)
        if rendered:return rendered
    dossiers=results.get('search_substrate_profiles',{}).get('dossiers',[])
    if dossiers:
        available=[d for d in dossiers if d.get('studies')]
        if available:
            names=', '.join(d['name'] for d in available)
            return (f'В локальном научном корпусе есть опубликованные профили: {names}. Это данные конкретных образцов с указанной подготовкой и условиями, а не измерения вашей партии. Без допущений о переносимости нельзя гарантировать её выход. Для оценки без литературного переноса нужны измеренные TS, VS и BMP вашей партии; фактическая выработка также зависит от инокулята и режима.'
                if state.language=='ru' else 'Published sample-specific profiles exist in the local corpus. They are not batch measurements or a guaranteed plant yield. An estimate without literature transfer needs measured batch TS, VS and BMP and documented operating conditions.')
    from src.advisor import catalog
    entered=state.mixture_scenario_components or state.mixture_components
    unknown_manure=[c for c in entered if c.get('material','').endswith('_manure') and c.get('physical_state','unknown')=='unknown']
    if unknown_manure:
        names=', '.join(dict.fromkeys(catalog.name(c['material'],state.language) for c in unknown_manure))
        return {
            'ru':f'?????????? ????? ????? {names} ?? ???????. ????????: ??? ????, ?????????? ????????, ??????? ??? ????? ????? ???? ????? ? ??????????. ?? ????? ?????? ???????? ??????? ? ????????? ????? ??????.',
            'en':f'The physical form of {names} is unspecified. Please say whether it is slurry, semi-liquid, solid, dry, or bedded manure. I cannot select a reference profile or estimate methane until this is known.',
            'kk':f'{names} ??????????? ????????? ???? ?????????????. ???? ?????, ???????? ?????, ?????, ?????? ?????? ??????? ?????? ??? ?????? ??????????. ???? ????? ??????? ????????, ????? ?????? ????????????.'
        }[state.language]
    for row in results.values():
        mixture=row.get('mixture') if isinstance(row,dict) else None
        if not isinstance(mixture,dict):continue
        lang=state.language;parts=[]
        mass=mixture.get('total_wet_mass_kg')
        if mass and mass.get('low')==mass.get('high'):
            value=f"{mass['low']:g}"
            parts.append({'ru':f'Введённая влажная масса компонентов суммарно равна {value} кг.',
                'en':f'The entered component wet masses sum to {value} kg.',
                'kk':f'Енгізілген компоненттердің ылғал массасы {value} кг.'}[lang])
        if mixture.get('complete_methane_reference'):
            value=mixture.get('additive_methane_reference_m3') or {}
            parts.append({'ru':f"Аддитивный лабораторный ориентир составляет {value.get('low')}–{value.get('high')} м³ CH₄; это не измеренный выход совместного сбраживания.",
                'en':f"The additive laboratory reference is {value.get('low')}–{value.get('high')} m³ CH₄; it is not a measured co-digestion yield.",
                'kk':f"Аддитивті зертханалық бағдар {value.get('low')}–{value.get('high')} м³ CH₄; бұл бірге қорыту кезінде өлшенген шығым емес."}[lang])
        else:
            value=mixture.get('known_component_additive_subtotal_m3')
            known=[catalog.name(c.get('material'),lang) for c in mixture.get('components',[]) if c.get('methane_reference_m3')]
            if value:
                quantity=value.get('low');names=', '.join(known)
                parts.append({'ru':f'Только для компонентов с сопоставимыми данными получен аддитивный ориентир {quantity:.4g} м³ CH₄ ({names}). Это не полный прогноз смеси и не нижняя граница её выхода.',
                    'en':f'Only components with comparable data have an additive reference of {quantity:.4g} m³ CH₄ ({names}). This is not a full mixture estimate or a lower bound on its yield.',
                    'kk':f'Салыстырмалы дерегі бар компоненттер үшін ғана {quantity:.4g} м³ CH₄ аддитивті бағдары алынды ({names}). Бұл қоспаның толық болжамы да, шығымының төменгі шегі де емес.'}[lang])
            missing=sorted({catalog.name(c.get('material'),lang) for c in mixture.get('components',[]) if c.get('missing')})
            if missing:
                names=', '.join(missing)
                parts.append({'ru':'Для оценки полного потенциала нужны измеренные TS, VS и BMP сопоставимых образцов: '+names+'.',
                    'en':'A full potential estimate needs measured TS, VS and BMP from comparable samples of: '+names+'.',
                    'kk':'Толық әлеуетті бағалау үшін салыстырмалы үлгілердің өлшенген TS, VS және BMP мәндері қажет: '+names+'.'}[lang])
        if parts:return ' '.join(parts)
    return '\n\n'.join(dict.fromkeys(r.get('message','') for r in results.values() if r.get('message'))) or 'The local language model could not complete a grounded response.'


def _append_dilution_caveat(answer,results,language):
    result=results.get('calculate_vs_concentration',{})
    if result.get('status')!='ok':return answer
    has_density=bool(re.search(r'1(?:[.,]0)?\s*(?:kg\s*/\s*l|кг\s*/\s*л)|density|плотност|тығыздық',answer,re.I))
    has_volume_caveat=bool(re.search(r'volumetric|volume-based|об[ъь]?[её]м|көлемдік',answer,re.I) and
        re.search(r'need|require|нуж|не\s+определ|қажет|анықтал',answer,re.I))
    has_no_loss=bool(re.search(r'no mass loss|mass loss is not|mass is conserved|потер\w*\s+мас|масса\s+не\s+тер|масса жоғал',answer,re.I))
    if has_density and has_volume_caveat and has_no_loss:return answer
    caveat={
        'ru':'Допущения: плотность добавленной воды приближённо принята равной 1,0 кг/л, потери массы не учитываются. Это массовая доля VS; для объёмной концентрации нужны объём или плотность сырья.',
        'en':'Assumptions: added-water density is approximated as 1.0 kg/L and no mass is lost. This is a wet-mass VS percentage; volumetric concentration needs feed volume or density.',
        'kk':'Болжам: қосылған судың тығыздығы шамамен 1,0 кг/л деп алынды, масса жоғалуы есептелмейді. Бұл ылғал массаға шаққандағы VS пайызы; көлемдік концентрация үшін шикізат көлемі не тығыздығы қажет.',
    }[language]
    return answer.rstrip()+'\n\n'+caveat


def _safe_observation(result):
    """Keep the model context compact while preserving reported values/evidence."""
    keep={'status','message','missing','material','model_applicable','category','bmp','model','model_version',
        'result_level','mixture','methane_potential_m3','potential_methane_m3','gas_potential_m3','energy',
        'biogas','conditions','studies','claims','sources','assumptions','limitations','domain','uncertainty',
        'estimate','estimates','price','prices','history','comparison','decision_analysis','supported_substrates',
        'accuracy','evaluation','items','conversions','gas_basis','total_wet_mass_kg','total_vs_kg',
        'additive_methane_reference_m3','known_component_additive_subtotal_m3','complete_methane_reference',
        'components','component','properties_used','profile_id','methane_comparable_m3','vs_mass_kg',
        'methane_reference_m3','source','title','url','authors','study','text','unit','evidence','values',
        'low','high','warnings','recommendation','kind','scope','temperature_c','duration_days','inoculum',
        'preparation','published_at','year','condition','status_reason','count'}
    def trim(value,depth=0):
        if isinstance(value,str):return value[:360]
        if isinstance(value,list):return [trim(v,depth+1) for v in value[:5]]
        if isinstance(value,dict):
            rows={k:trim(v,depth+1) for k,v in value.items() if k in keep}
            return dict(list(rows.items())[:24])
        return value
    return trim(result)


def _available_tools(state):
    material=state.value('material');intents=set(state.intents)
    has_batch=bool(state.mixture_components or state.mixture_scenario_components or
        state.value('quantity') is not None or state.value('mass_kg') is not None or state.value('material_volume_l') is not None)
    mixture=bool(state.mixture_components or state.mixture_scenario_components);names=[]
    pending_fields=set(state.pending_question.fields) if state.pending_question else set()
    components=state.mixture_scenario_components or state.mixture_components
    missing_form=any(c.get('material','').endswith('_manure') and c.get('physical_state','unknown')=='unknown' for c in components)
    missing_species=any(c.get('material')=='manure' and c.get('animal','unknown')=='unknown' for c in components)
    missing_material='material' in pending_fields and not material
    missing_quantity=bool(pending_fields & {'quantity','mass_kg','material_volume_l'}) and not has_batch
    clarification_block=missing_form or missing_species or missing_material or missing_quantity
    single_manure_form_missing=material in {'cattle_manure','swine_manure','poultry_manure','manure'} and (state.value('material_state') or 'unknown')=='unknown'
    if mixture:
        names+=['search_scientific_sources']
        if not clarification_block:
            names+=['analyze_substrate_mixture','estimate_advanced_gas']
            if intents & {'temperature_recommendation','process_guidance'}:names+=['advise_substrate_conditions']
            if intents & {'economic_comparison','market_prices'}:names+=['estimate_advanced_energy','evaluate_advanced_economics','get_market_prices','compare_market_scenarios']
            if not intents or intents=={'general'}:names+=['get_substrate_catalog','get_matched_substrate_conditions']
    else:
        if not mixture and 'process_guidance' in intents and all(state.value(key) is not None for key in ('vs_mass_kg','mass_kg','dilution_water_l')):
            names+=['calculate_vs_concentration']
        if material:names+=['analyze_substrate','search_scientific_sources','get_substrate_catalog']
        if intents & {'methane_yield','economic_comparison'}:
            names+=['predict_bmp','calculate_methane']
            if material and has_batch and not single_manure_form_missing:names+=['estimate_substrate_gas','estimate_from_literature']
        if intents & {'temperature_recommendation','process_guidance'}:
            names+=['recommend_conditions','search_scientific_sources']
            if material and has_batch and not single_manure_form_missing:names+=['advise_substrate_conditions','get_matched_substrate_conditions']
        if intents & {'economic_comparison','market_prices'}:names+=['get_market_prices','compare_market_scenarios','explain_market_recommendation','calculate_profitability','evaluate_advanced_economics']
        if 'price_history' in intents:names+=['get_price_history']
        if 'reactor_status' in intents:names+=['get_reactor_status']
        if 'model_info' in intents:names+=['get_model_info']
        if 'sources' in intents:
            names+=['search_scientific_sources']
            if material:names+=['research_scientific_evidence']
        if not intents or intents=={'general'}:names+=['search_scientific_sources','get_model_info','get_substrate_catalog']
        if material:names+=['research_scientific_evidence','research_market_offers','research_and_estimate']
    if not names:names=['search_scientific_sources','get_model_info','get_substrate_catalog','get_reactor_status']
    from src.agent.scientific_tools import TOOLS as SCIENTIFIC_TOOLS
    names += SCIENTIFIC_TOOLS
    if os.getenv('BIOREACTOR_RESEARCH_ONLINE','1')=='0' or 'sources' not in intents:
        names=[n for n in names if n!='search_public_scientific_metadata']
    if has_batch:names+=['assess_substrate_potential']
    return list(dict.fromkeys(name for name in names if name in AUTONOMOUS_TOOLS))


def _observations_for_model(observations):
    """Keep authoritative calculations resident; compress auxiliary retrieval."""
    out=[]
    for obs in observations:
        if obs.get('tool') in analytical.TOOLS or obs.get('tool') in {'recover_local_scientific_analysis','recover_partial_economics'}:
            out.append(obs);continue
        raw=obs.get('result')
        if raw is not None and len(json.dumps(raw,ensure_ascii=False))>2400:
            brief={k:raw[k] for k in ['status','message','missing','checked','all_checks_passed','pooled_bmp','live_search_performed'] if k in raw}
            if raw.get('dossiers'):
                brief['dossiers']=[{'material':d['material'],'scope_status':d.get('scope_status'),
                    'profiles':[s['profile_id'] for s in d.get('studies',[])],
                    'risks':d.get('inhibition_risks',[])} for d in raw['dossiers']]
            if raw.get('studies'):
                brief['studies']=[{k:s.get(k) for k in ['profile_id','physical_state','bmp_ml_ch4_g_vs','gas_basis']} for s in raw['studies']]
            if raw.get('comparability_checks'):brief['comparability_warning']='Distinct studies/preparation/gas bases must not be pooled.'
            out.append({'tool':obs.get('tool'),'result':brief,'full_evidence_retained_in_trace':True})
        else:out.append(obs)
    return out


def provider_failure(agent,text,extraction,started):
    """Explicit bounded local projection when understanding/generation failed.

    Never runs another model or a second hidden dialogue pipeline. This is
    deliberately labelled as a deterministic fallback, not Qwen autonomy.
    """
    from src.agent.research_memory import finish_turn
    from src.agent.scientific_tools import verify
    state=agent.state
    deadline=started+max(1,min(600,float(os.getenv('BIOREACTOR_AGENT_TIMEOUT','120'))))
    cap=max(1,min(12,int(os.getenv('BIOREACTOR_AGENT_MAX_TOOLS','4'))))
    results={};trace=[]
    required=analytical.obligations(state,text)
    if not required:
        reads={'market_prices':'get_market_prices','price_history':'get_price_history',
            'model_info':'get_model_info','reactor_status':'get_reactor_status','sources':'search_substrate_profiles'}
        required=list(dict.fromkeys(reads[i] for i in state.intents if i in reads))
    for name in required:
        if len(trace)>=cap or time.perf_counter()>=deadline:break
        try:result=agent.registry.execute(name,_tool_context(agent,name,text,{}),results,text)
        except Exception as exc:result={'status':'error','message':'Tool execution failed: '+type(exc).__name__,'error_type':type(exc).__name__}
        results[name]=result
        trace.append({'tool':name,'status':result.get('status'),'input_origin':'explicit_local_fallback_after_provider_failure','result':result})
    details=analytical.render(results,state)
    if not details and results:
        details=_fallback_answer(results,state) if 'search_substrate_profiles' in results else '\n\n'.join(r.get('message','') for r in results.values())
    note='Языковая модель недоступна или не вернула допустимую структуру. Ниже — явно обозначенный локальный анализ по сохранённым фактам и научным профилям.' if state.language=='ru' else 'The language model was unavailable or returned invalid structure. This is an explicit local analysis from saved facts and reviewed profiles.'
    if not trace:
        note='Языковая модель недоступна. Подтверждённые параметры сохранены; расчётные инструменты в этом ответе не выполнены.' if state.language=='ru' else 'The model was unavailable. Confirmed inputs are saved; no calculation tools ran in this reply.'
    body=note+('\n\n'+details if details else '')
    if time.perf_counter()>=deadline:
        body+='\n\n'+('Достигнут лимит времени; невыполненные проверки перечислены в диагностике.' if state.language=='ru' else 'Time budget exhausted; unchecked evidence is listed in diagnostics.')
    compact=analytical.user_facing(results,state)
    facing={'paragraphs':[note]+[s['body'] for s in compact['sections']],**compact}
    facing['modes']=list(dict.fromkeys(['explicit_local_fallback']+compact['modes']))
    facing,body,diagnostics=finish_turn(state,text,extraction,facing,body,results)
    diagnostics.insert(0,{'stage':'provider','reason':'no_valid_structured_understanding','provider_status':list(agent.llm.status)})
    agent.history=(agent.history+[text])[-8:]
    return {'conversation_version':'7','analysis_version':'8.5','mode':'deterministic_partial_provider_failure',
        'answer':body,'user_facing_answer':facing,'tools':trace,'provider_status':list(agent.llm.status),
        'memory':state.model_dump(mode='json'),'context':dict(agent.context),'context_updated':True,
        'pending_question':state.pending_question.model_dump(mode='json') if state.pending_question else None,
        'missing':list(dict.fromkeys(k for r in results.values() for k in r.get('missing',[]))),
        'technical_metadata':{'agent_version':'8.5','diagnostics':diagnostics,'tool_calls':trace,
            'resource_budget':{'max_tools':cap,'timeout_seconds':deadline-started},'verification':verify(results),
            'analytical_required_tools':required,'analytical_unchecked_tools':[n for n in required if n not in results],
            'numeric_claims_grounded':not (_unsupported_numbers(details,state,results)+_unsupported_units(details,results)) if details else True,
            'autonomous_termination':'provider_unavailable_local_fallback','latency_seconds':time.perf_counter()-started,
            'extracted_entities':extraction.model_dump(mode='json'),'actuator_access':False},
        'actuator_access':False,'policy_tool_plan':[t['tool'] for t in trace]}


def run(agent,text,extraction,proposal,started):
    """Bounded model-selected investigation; shared calculators verify evidence."""
    state=agent.state;state.version='7';results={};trace=[];observations=[];called=set()
    max_calls=max(1,min(12,int(os.getenv('BIOREACTOR_AGENT_MAX_TOOLS','4'))))
    deadline=started+max(1,min(600,float(os.getenv('BIOREACTOR_AGENT_TIMEOUT','120'))))
    required=analytical.obligations(state,text)
    final='';action_count=0;termination='model_final';allowed_tools=list(dict.fromkeys(required+_available_tools(state)))
    diagnostics=[];actions=[];enforce=False
    for step in range(max_calls+3):
        if action_count>=max_calls:
            termination='tool_call_limit';diagnostics.append({'stage':'budget','reason':'tool_call_limit'});break
        if time.perf_counter()>=deadline:
            termination='time_limit';diagnostics.append({'stage':'budget','reason':'time_limit'});break
        remaining_tools=[name for name in allowed_tools if name not in called]
        if results.get('assess_substrate_potential',{}).get('status')!='error':
            remaining_tools=[n for n in remaining_tools if n!='recover_local_scientific_analysis']
        if results.get('evaluate_partial_economics',{}).get('status')!='error':
            remaining_tools=[n for n in remaining_tools if n!='recover_partial_economics']
        if required:
            # The canonical tools already calculate profile-scoped methane and
            # economics. Avoid offering parallel legacy wrappers of that work.
            redundant={'estimate_substrate_gas','estimate_from_literature','research_and_estimate',
                'estimate_advanced_gas','estimate_advanced_energy','evaluate_advanced_economics',
                'analyze_substrate_mixture','calculate_profitability','compare_market_scenarios',
                'explain_market_recommendation'}
            remaining_tools=[n for n in remaining_tools if n not in redundant]
            from src.agent.scientific_tools import TOOLS as RESEARCH_TOOLS
            canonical=set(required)|set(RESEARCH_TOOLS)|{'get_reactor_status','get_model_info','get_market_prices'}
            remaining_tools=[n for n in remaining_tools if n in canonical]
        if results.get('assess_substrate_potential',{}).get('scenarios'):
            # These audits are already attached to each scenario; repeating them
            # cannot add evidence. Source comparison and risks remain optional.
            remaining_tools=[n for n in remaining_tools if n not in {'verify_scientific_calculations','check_reactor_loading'}]
        if results.get('evaluate_partial_economics',{}).get('scenarios'):
            remaining_tools=[n for n in remaining_tools if n!='get_market_prices']
        # Offer only executable tools; a missing measured BMP is not an excuse
        # to run a redundant exact calculator after a literature estimate.
        facts=analytical.context(state)['facts']
        if not all(facts.get(k) is not None for k in ['c_vs_sub_m','c_vs_sub_f','c_vs_inoc','ISR']):
            remaining_tools=[n for n in remaining_tools if n!='predict_bmp']
        if not all(facts.get(k) is not None for k in ['bmp_ml_ch4_g_vs','vs_mass_kg']):
            remaining_tools=[n for n in remaining_tools if n!='calculate_methane']
        if 'assess_substrate_potential' not in results:
            remaining_tools=[n for n in remaining_tools if n not in {'evaluate_partial_economics','check_reactor_loading','calculate_dilution_plan','verify_scientific_calculations'}]
        if results.get('assess_substrate_potential',{}).get('status')=='error':
            remaining_tools=[n for n in remaining_tools if n!='evaluate_partial_economics']
        unmet=[name for name in required if name not in called]
        if results.get('assess_substrate_potential',{}).get('status')=='error' and 'recover_local_scientific_analysis' not in called:
            unmet.insert(0,'recover_local_scientific_analysis')
        if results.get('evaluate_partial_economics',{}).get('status')=='error' and 'recover_partial_economics' not in called:
            unmet.append('recover_partial_economics')
        if unmet and enforce:
            eligible=[name for name in unmet if name!='evaluate_partial_economics' or 'assess_substrate_potential' in results and results['assess_substrate_potential'].get('status')!='error']
            # The model can inspect categories, sources and prices first. Reserve
            # enough calls to satisfy the calculation contract before answering.
            if max_calls-action_count>len(unmet):
                eligible += [n for n in remaining_tools if n in {'analyze_substrate','search_scientific_sources','get_market_prices'}]
            remaining_tools=list(dict.fromkeys(eligible))
        try:
            action=_bounded_action(agent,deadline,text,_state_payload(state),
                {'conversation_id':state.conversation_id,'active_intents':state.intents,
                 'mixture_revision':state.mixture_revision,'required_tool_checks':unmet,
                 'enforce_evidence_check':enforce,'remaining_tool_budget':max_calls-action_count,
                 'previous_questions':state.advanced.get('research_dialogue',{}).get('asked',[])},agent.history,_observations_for_model(observations),remaining_tools,
                final_only=not remaining_tools)
        except ProviderError as exc:
            diagnostics.append({'stage':'tool_selection','error':str(exc),'type':type(exc).__name__})
            termination='provider_action_failed';break
        if action is None:
            termination='provider_not_active';break
        actions.append({'step':step,'action':action['action'],'tool':action.get('tool'),
            'plan':action.get('plan',[]),'purpose':action.get('purpose',''),
            'protocol_normalization':action.get('protocol_normalization'),
            'elapsed_seconds':round(time.perf_counter()-started,3)})
        if action['action']=='final':
            if unmet:
                diagnostics.append({'stage':'answer_contract','reason':'calculation_evidence_not_checked','missing_tools':unmet})
                observations.append({'instruction':'Before answering, call the offered evidence/calculation tools. Missing measurements permit explicitly labelled literature scenarios, not invented facts.'})
                enforce=True
                continue
            final=action['final'].strip();break
        if action_count>=max_calls:
            termination='tool_call_limit';break
        name=action['tool'];arguments=action.get('arguments',{})
        # One call per tool keeps result provenance unambiguous and prevents loops.
        if name in called:
            diagnostics.append({'stage':'loop_detection','reason':'repeated_tool_blocked','tool':name})
            termination='repeated_tool_blocked';break
        called.add(name);action_count+=1
        query=arguments.get('query') or text
        context=_tool_context(agent,name,query,arguments)
        # Model-produced query text is retrieval-only. Numeric user inputs always
        # come from parsed, validated, and persisted session facts.
        try:result=agent.registry.execute(name,context,results,query)
        except Exception as exc:
            result={'status':'error','message':'Tool execution failed: '+type(exc).__name__, 'error_type':type(exc).__name__}
        try:
            json.dumps(result,ensure_ascii=False,allow_nan=False)
            if not isinstance(result,dict) or not isinstance(result.get('message'),str) or 'status' not in result:
                raise ValueError('Invalid tool protocol')
        except (ValueError,TypeError):
            result={'status':'error','message':'Tool result failed protocol validation.'}
        results[name]=result
        if name=='recover_local_scientific_analysis' and result.get('scenarios'):
            results['assess_substrate_potential']=dict(result,recovered_from_tool=name)
            diagnostics.append({'stage':'replanning','reason':'primary_science_recovered_locally','tool':name})
        if name=='recover_partial_economics' and result.get('scenarios'):
            results['evaluate_partial_economics']=dict(result,recovered_from_tool=name)
            diagnostics.append({'stage':'replanning','reason':'partial_economics_recovered_locally','tool':name})
        if result['status']=='error':
            diagnostics.append({'stage':'tool_execution','tool':name,'error':result.get('message'),'error_type':result.get('error_type')})
            observations.append({'instruction':'This tool failed; use an alternative applicable evidence path. Do not repeat the failed call or describe the error as missing scientific evidence.'})
        trace.append({'tool':name,'status':result['status'],'input_origin':'validated_dialogue_state_and_typed_tool_request','result':result})
        evidence_tool={'recover_local_scientific_analysis':'assess_substrate_potential','recover_partial_economics':'evaluate_partial_economics'}.get(name,name)
        observations.append({'tool':name,'result':analytical.observation(evidence_tool,result) if evidence_tool in analytical.TOOLS else _safe_observation(result)})
        if name=='assess_substrate_potential':
            from src.agent.scientific_tools import verify
            observations.append({'independent_calculation_check':verify(results)})
        if time.perf_counter()>=deadline:
            termination='time_limit';break
    stop_reason=termination
    if not final and time.perf_counter()<deadline:
        # Ask for a final synthesis after the call cap, with an explicit stop
        # condition. Tool results remain the only source of numeric claims.
        try:
            action=_bounded_action(agent,deadline,text,_state_payload(state),
                {'conversation_id':state.conversation_id,'active_intents':state.intents},agent.history,
            _observations_for_model(observations),allowed_tools,final_only=True)
        except ProviderError:
            action=None
        if action and action.get('action')=='final':final=action['final'].strip()
        else:termination=termination if termination!='model_final' else 'no_final_response'
    original_model_synthesis=final
    unsupported=_unsupported_numbers(final,state,results)+_unsupported_units(final,results)+_unsupported_conclusions(final,results) if final else ['no answer']
    if unsupported and results and time.perf_counter()<deadline:
        repair_observations=observations+[{'grounding_check':{'rejected_numeric_tokens':unsupported,
            'instruction':'Use only confirmed evidence. Do not relabel absolute m3 as m3/kg VS. If complete_methane_reference is false, any methane quantity is only a known-component subtotal, not a full mixture estimate.'}}]
        try:
            repaired=_bounded_action(agent,deadline,text,_state_payload(state),
                {'conversation_id':state.conversation_id,'active_intents':state.intents},agent.history,
                _observations_for_model(repair_observations),[],final_only=True)
            if repaired and repaired.get('action')=='final':
                candidate=repaired['final'].strip()
                if not (_unsupported_numbers(candidate,state,results)+_unsupported_units(candidate,results)+_unsupported_conclusions(candidate,results)):
                    final=candidate;unsupported=[]
        except ProviderError:pass
    draft_rejections=list(unsupported)
    if unsupported:
        final=_fallback_answer(results,state)
        termination='numeric_grounding_fallback' if results else 'empty_or_ungrounded_final'
    unsupported=_unsupported_numbers(final,state,results)+_unsupported_units(final,results) if final else ['no answer']
    if unsupported and results:
        final='I could not produce a numerical answer grounded in the available tool results.'
        termination='grounded_fallback_unavailable'
        unsupported=_unsupported_numbers(final,state,results)+_unsupported_units(final,results)
    llm_draft=final
    if required and any(name in results for name in analytical.TOOLS):
        # Result projection supplies the complete analytical contract, including
        # assumptions and unavailable quantities, even when the LLM omits them.
        projected=analytical.render(results,state)
        # Preserve a grounded model synthesis. Use evidence projection only for
        # refusal, absent numbers despite available potential, or invalid output.
        has_potential=any(s.get('methane_m3') for s in results.get('assess_substrate_potential',{}).get('scenarios',[]))
        science=results.get('assess_substrate_potential',{})
        wants_gas=('methane_yield' in state.intents and 'sources' not in state.intents) or bool(re.search(r'(?:сколько|оцени|потенциал|how much|estimate).{0,90}(?:метан|биогаз|газ|gas)|потенциал',text,re.I))
        gas_mentioned=_mentions_calculated_quantity(final,[s.get('methane_m3') for s in science.get('scenarios',[])],r'м³|м3|m3')
        energy_bounds=[];money_bounds=[]
        for row in results.get('evaluate_partial_economics',{}).get('scenarios',[]):
            analysis=row.get('analysis',{})
            energy_bounds.extend(analysis.get('energy',{}).get('outputs',{}).values())
            money_bounds.extend(a.get(k) for a in analysis.get('scenarios',[]) for k in ['gross_benefit_reference_kzt','net_result_kzt'])
        economic_mentioned=_mentions_calculated_quantity(final,energy_bounds,r'kwh|кВт\s*[·*-]?\s*ч') or _mentions_calculated_quantity(final,money_bounds,r'KZT|тенге|₸')
        omitted_calculation=(has_potential and wants_gas and not gas_mentioned) or ('economic_comparison' in state.intents and any(isinstance(b,dict) for b in energy_bounds+money_bounds) and not economic_mentioned)
        if 'temperature_recommendation' in state.intents and results.get('assess_process_evidence',{}).get('matched_temperature_experiments') and not re.search(r'°|градус|degrees',final,re.I):
            omitted_calculation=True
        if 'economic_comparison' in state.intents and re.search(r'продать|продаж|sell',text,re.I) and not re.search(r'порог|безубыточ|затрат|расход|break.even|cost',final,re.I):
            omitted_calculation=True
        refusal=bool(re.search(r'недостаточно данных|расч[её]т невозможен|cannot calculate|insufficient data',final,re.I))
        if projected and (not grounded_text(final,state,results) or omitted_calculation or has_potential and (refusal or not re.search(r'\d',final))):
            final=projected
            termination='computed_evidence_projection'
    elif required and any(name in analytical.TOOLS for name in required):
        final='Не удалось выполнить обязательную проверку научных данных и вычислительных инструментов. Это ошибка выполнения анализа, а не доказательство отсутствия применимых данных. Диагностика доступна в метаданных ответа.'
    final=_append_dilution_caveat(final,results,state.language)
    if state.language=='ru' and any(s.get('result_level')=='HYPOTHETICAL_SCENARIO' for s in results.get('assess_substrate_potential',{}).get('scenarios',[])) and not re.search(r'условн|литератур|допущен|опубликован',final,re.I):
        final='Предварительный условный сценарий по литературе: '+final
    engineering=[s.get('engineering',{}) for s in results.get('assess_substrate_potential',{}).get('scenarios',[])]
    if state.language=='ru' and any(e.get('status')=='PHYSICALLY_INFEASIBLE' for e in engineering):
        final+='\n\nКак минимум один рассчитанный сценарий нарушает ограничения объёма. Допустимость загрузки не подтверждена; массу партии и рабочую ёмкость необходимо пересмотреть.'
    elif state.language=='ru' and engineering and any(e.get('total_volume_l') and e.get('status')=='REQUIRES_REVIEW' for e in engineering) and 'не задаёт выход метана' not in final:
        final+='\n\nДопустимость загрузки не подтверждена. Номинальный объём ограничивает вместимость; для проверки нужны рабочий объём, объём сырья или плотность, вода, инокулят и газовое пространство.'
    unsupported=_unsupported_numbers(final,state,results)+_unsupported_units(final,results) if final else ['no answer']
    grounded=not unsupported
    if any(name in results for name in {'search_scientific_sources','research_scientific_evidence','research_and_estimate'}) and not _sources(results):
        notices={'ru':'Проверенный локальный каталог не вернул применимых источников; объяснение выше не подтверждено источниками в этом запросе.',
            'en':'The reviewed local catalogue returned no applicable sources; the explanation above is not source-verified in this run.',
            'kk':'Тексерілген жергілікті каталог сәйкес дереккөз таппады; жоғарыдағы түсіндірме осы сұрауда дереккөзбен расталмады.'}
        final=final.rstrip()+'\n\n'+notices[state.language]
    sources=_sources(results)
    agent.history=(agent.history+[text])[-8:];agent.last_pending=[name for name,r in results.items() if r.get('status')=='needs_input']
    pending=None
    missing=list(dict.fromkeys(k for r in results.values() for k in r.get('missing',[]) if isinstance(k,str)))
    from src.agent.research_memory import finish_turn
    body=final
    if required and any(name in results for name in analytical.TOOLS):
        compact=analytical.user_facing(results,state)
        facing={'paragraphs':[section['body'] for section in compact['sections']],
            'sections':compact['sections'],'question':compact['question'],'sources':compact['sources'] or sources,
            'modes':list(dict.fromkeys(['autonomous_scientific_tools']+compact['modes'])),
            'assumptions':compact['assumptions']}
    else:
        facing={'paragraphs':[body],'sections':[],'question':None,'sources':sources,'modes':['autonomous_scientific_tools'],'assumptions':list(state.assumptions)}
    if llm_draft and termination!='computed_evidence_projection' and grounded_text(llm_draft,state,results):
        synthesis=re.sub(r'[^.!?\n]*\?','',body).strip()
        if synthesis:
            facing['paragraphs'].insert(0,synthesis)
            if facing.get('sections'):
                facing['sections'][0]['body']=synthesis
    metrics=[]
    active=getattr(agent.llm,'active',None)
    if active is not None:metrics=list(active.metrics[-(action_count+2):])
    facing,body,dialogue_diagnostics=finish_turn(state,text,extraction,facing,body,results)
    diagnostics.extend(dialogue_diagnostics)
    if stop_reason in {'time_limit','tool_call_limit','provider_action_failed'}:
        limit_note=('Анализ остановлен по лимиту времени или вызовов; приведены доступные частичные результаты.'
            if state.language=='ru' else 'Investigation stopped at the resource limit or provider failure; available partial results are retained.')
        if stop_reason=='provider_action_failed':
            limit_note='Ошибка языковой модели прервала исследование; доступные вычисления сохранены.' if state.language=='ru' else 'A provider error interrupted the investigation; available computations are retained.'
        body+='\n\n'+limit_note
        facing['paragraphs'].append(limit_note)
        if facing.get('sections'):facing['sections'][-1]['body']+=' '+limit_note
    from src.agent.scientific_tools import verify
    verification=verify(results)
    if verification['status']=='error':diagnostics.append({'stage':'verification','reason':'arithmetic_mismatch','checks':verification['checks']})
    metadata={'agent_version':'8.5','tool_calls':trace,'autonomous_action_steps':action_count,
        'research_actions':actions,'verification':verification,
        'resource_termination':stop_reason,
        'resource_budget':{'max_tools':max_calls,'timeout_seconds':deadline-started},
        'analytical_required_tools':required,'analytical_unchecked_tools':[n for n in required if n not in called],
        'diagnostics':diagnostics,
        'llm_draft':llm_draft,'original_model_synthesis':original_model_synthesis,
        'answer_projection':termination=='computed_evidence_projection',
        'autonomous_termination':termination,'provider_generation_metrics':metrics,
        'confirmed_parameters':{k:v.model_dump(mode='json') for k,v in state.facts.items() if v.provenance=='USER_CONFIRMED'},
        'assumptions':{k:v.model_dump(mode='json') for k,v in state.assumptions.items()},
        'derived_parameters':{k:v.model_dump(mode='json') for k,v in state.derived.items()},
        'model_estimates':{k:v.model_dump(mode='json') for k,v in state.estimates.items()},
        'missing_parameters':missing,'numeric_claims_grounded':grounded,
        'numeric_grounding_rejections':draft_rejections,
        'uncertainty_status':'No calibrated prediction interval established.',
        'extracted_entities':extraction.model_dump(mode='json'),'llm_proposal':proposal.model_dump(mode='json'),
        'latency_seconds':__import__('time').perf_counter()-started,'actuator_access':False}
    return {'conversation_version':'7','analysis_version':'8.5','mode':'qwen_autonomous_tools',
        'answer':body,'user_facing_answer':facing,'technical_metadata':metadata,'tools':trace,
        'provider_status':list(agent.llm.status),'missing':missing,'context':dict(agent.context),
        'memory':state.model_dump(mode='json'),'pending_question':None,'context_updated':True,
        'actuator_access':False,'policy_tool_plan':[r['tool'] for r in trace]}
