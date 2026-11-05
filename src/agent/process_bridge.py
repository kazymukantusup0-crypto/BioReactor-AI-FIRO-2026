"""v6 process tools and grounded conversational adaptation; no actuator access."""
import json
import re
from src.agent.dialogue_types import Entity, Question

PROCESS_TOOLS = ['analyze_process_constraints', 'generate_process_scenarios',
                 'estimate_process_energy', 'optimize_process', 'explain_optimization',
                 'compare_process_scenarios']


def augment(text, state, extraction):
    """Only literal parameters enter memory; LLM cannot supply engineering defaults."""
    from src.optimizer.schemas import ProcessParameters
    from src.agent.nlu import NUMBER, numeric
    supplied = {e.name: e.value for e in extraction.entities}
    enabled = bool(state.value('process_optimizer_active'))
    reactor = any(e.name in {'reactor_total_volume_l', 'reactor_working_volume_l'} for e in extraction.entities) or state.value('reactor_total_volume_l') is not None
    requested = bool(re.search(r'оптимиз|optim[iz]|оңтай|как\s+лучше|как.*организ|план.*парти|process\s+scenari|compare.*(?:degrees|temperature)|сравни.*(?:градус|температур)|салыстыр.*(?:градус|температур)', text, re.I))
    # A simple temperature question remains the existing three-tool guidance path.
    enabled = enabled or requested and bool(reactor or re.search(r'оптимиз|optim[iz]|оңтай|сравни|compare|салыстыр', text, re.I))
    additions = {}
    patterns = {
        'initial_temperature_c': r'(?:начальн\w*\s+температур\w*|initial\s+temperature|бастапқы\s+температура)\s*(?:[=:]|is)?\s*(' + NUMBER + ')',
        'ambient_temperature_c': r'(?:температур\w*\s+(?:воздуха|среды)|ambient\s+temperature|сыртқы\s+температура)\s*(?:[=:]|is)?\s*(' + NUMBER + ')',
        'heat_capacity_kj_kg_k': r'(?:тепло[её]мкост\w*|heat\s+capacity)\s*(?:[=:]|is)?\s*(' + NUMBER + r')\s*(?:кдж|kj)\s*/?\s*\(?\s*(?:кг|kg)',
        'batch_duration_days': r'(?:длительност\w*\s+парти\w*|batch\s+duration)\s*(?:[=:]|is)?\s*(' + NUMBER + r')\s*(?:дн|день|дней|days?)',
        'duration_days': r'(?:длительност\w*\s+процесс\w*|process\s+duration)\s*(?:[=:]|is)?\s*(' + NUMBER + r')\s*(?:дн|день|дней|days?)',
        'ph': r'\bpH\s*[=:]?\s*(' + NUMBER + ')',
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, text, re.I)
        if match: additions[key] = numeric(match.group(1), extraction.language)
    if set(additions) & {'initial_temperature_c','ambient_temperature_c'} and not re.search(r'целев|target|сравни|compare',text,re.I):
        extraction.entities=[e for e in extraction.entities if e.name!='temperature_c']
        supplied.pop('temperature_c',None)
    # Power/heat-loss/efficiency etc. may also be entered explicitly with named SI fields.
    for match in re.finditer(r'\b([a-zA-Z_][a-zA-Z_0-9]*)\s*=\s*("[^"\n]*"|\'[^\'\n]*\'|[^\s;]+)', text):
        key, raw = match.groups()
        if key not in ProcessParameters.model_fields or key in {'model', 'market', 'assumptions', 'user_limits', 'mixture_components'}: continue
        raw = raw.strip('"\'').rstrip(';,')
        if key=='operating_mode':raw=raw.rstrip('.!?')
        try: value = json.loads(raw)
        except ValueError:
            try: value = float(raw.replace(',', '.'))
            except ValueError: value = raw
        additions[key] = value
    if text.lstrip().startswith('{'):
        raw = json.loads(text)
        additions.update(raw.get('process_parameters', {}))
        if 'process_parameters' in raw: enabled = True
    new_fields=set(additions)-{e.name for e in extraction.entities}
    if additions:
        # Validate each independent field; cross-field checks run on the full request later.
        for key, value in additions.items():
            if key not in ProcessParameters.model_fields: raise ValueError('Unknown process parameter: ' + key)
            from pydantic import TypeAdapter
            field = ProcessParameters.model_fields[key]
            TypeAdapter(field.rebuild_annotation()).validate_python(value,strict=True)
            if isinstance(value,str) and not value.strip():raise ValueError(key+': omit an unknown blank parameter')
        if new_fields:enabled = True
    for key, value in additions.items():
        if key in supplied: continue
        hypothetical=any(e.provenance=='ASSUMED_FOR_SCENARIO' for e in extraction.entities) or bool(re.search(r'допустим|предположим|например|assume|hypothetical|мысалы|болжам',text,re.I))
        extraction.entities.append(Entity(name=key, value=value, evidence=text,provenance='ASSUMED_FOR_SCENARIO' if hypothetical else 'USER_CONFIRMED'))
    if enabled:
        extraction.entities.append(Entity(name='process_optimizer_active', value=True, evidence=text,provenance='CALCULATED_FROM_CONFIRMED'))
        if not extraction.intents and not state.intents: extraction.intents=['process_guidance']
        compare = re.search(r'(?:сравни\w*|compare|салыстыр\w*)\s+(' + NUMBER + r')\s*(?:и|and|мен|және|vs|,)\s*(' + NUMBER + r')\s*(?:градус\w*|degrees?|°\s*[cс]|температур\w*)', text, re.I)
        if compare:
            values = [numeric(v, extraction.language) for v in compare.groups()]
            if any(v <= -273.15 for v in values): raise ValueError('Temperature below absolute zero')
            # Comparing targets does not assert either as the measured/current temperature.
            extraction.entities = [e for e in extraction.entities if e.name not in {'temperature_c', 'process_candidates'}]
            extraction.entities.append(Entity(name='process_candidates', value={'temperatures_c': values}, evidence=compare.group(), provenance='ASSUMED_FOR_SCENARIO'))
        elif 'temperature_c' in supplied:
            # A new target supersedes previous comparison alternatives.
            extraction.entities.append(Entity(name='process_candidates', value={'temperatures_c': [supplied['temperature_c']]}, evidence=text, provenance='ASSUMED_FOR_SCENARIO'))
    return extraction


def request_data(state):
    from src.optimizer.schemas import ProcessParameters
    fields = set(ProcessParameters.model_fields)
    data = {k: f.value for k, f in {**state.derived, **state.facts}.items() if k in fields and f.value is not None}
    if state.value('material_volume_l') is not None: data['feedstock_volume_l'] = state.value('material_volume_l')
    assumptions = {k: f.value for k, f in state.assumptions.items() if k in fields and k != 'market_region'}
    for key, value in assumptions.items(): data.setdefault(key, value)
    if assumptions: data['assumptions'] = assumptions
    bmp = state.facts.get('bmp_ml_ch4_g_vs') or state.assumptions.get('bmp_ml_ch4_g_vs')
    if bmp:
        data.setdefault('bmp_provenance', 'scenario_assumption' if bmp.provenance == 'ASSUMED_FOR_SCENARIO' else 'measured')
        data.setdefault('bmp_evidence', bmp.evidence)
    selected = state.assumptions.get('process_candidates')
    if selected:
        data['candidates'] = [{'label': f'{v:g} °C', 'overrides': {'temperature_c': v}, 'rationale': selected.evidence}
                              for v in selected.value.get('temperatures_c', [])]
    market = dict(state.value('market_scenario', {}))
    if state.value('market_region'): market.setdefault('region', state.value('market_region'))
    # Profile default stays an explicit assumption and never establishes a contractual tariff.
    elif state.assumptions.get('market_region'):
        market.setdefault('region', state.assumptions['market_region'].value)
        data.setdefault('assumptions', {})['market_region'] = state.assumptions['market_region'].value
    if market: data['market'] = market
    return data


def plan(state, text):
    if not state.value('process_optimizer_active'): return []
    if not set(state.intents) & {'process_guidance','economic_comparison','temperature_recommendation','methane_yield'} and not re.search(r'оптимиз|optim|сравни|compare|ограничени|constraints|энерго|energy',text,re.I): return []
    if re.search(r'объясни.*оптим|explain.*optim', text, re.I): return ['explain_optimization']
    if re.search(r'энерго|нагрев|energy|heating|жылыту', text, re.I) and not re.search(r'оптим|выгод|compare|сравни', text, re.I): return ['estimate_process_energy']
    if re.search(r'сравни|compare|салыстыр', text, re.I): return ['compare_process_scenarios']
    if re.search(r'ограничени|constraints', text, re.I): return ['analyze_process_constraints']
    return ['optimize_process']


def execute_tool(name, context, store):
    from src.optimizer.schemas import ProcessRequest
    from src.optimizer.service import optimize
    from src.optimizer.energy_model import estimate_energy
    request = ProcessRequest.model_validate(context.get('process_request', context))
    if name == 'estimate_process_energy':
        result = {'energy': estimate_energy(request), 'scenarios': []}
    elif name == 'analyze_process_constraints':
        from src.optimizer.constraints import analyze_constraints
        result = analyze_constraints(request)
    else:
        result = optimize(store, request)
        if name in {'optimize_process','compare_process_scenarios','generate_process_scenarios'}:
            from src.optimizer.storage import save_run,initialize
            initialize(store)
            result=save_run(store,request,result)
    return {'status': 'ok', 'message': 'Process study calculated with explicit missing data; no equipment commands.',
            'optimizer_version': '6', 'actuator_access': False, **result}


def pending(state, results, previous):
    if not any(name in results for name in PROCESS_TOOLS): return previous
    lang = state.language
    def make(name, texts, fields, options=None):
        return Question(id=name, text=texts[['ru', 'en', 'kk'].index(lang)], fields=fields, options=options or [], reason='process_optimizer')
    if 'estimate_process_energy' in results and not any(name in results for name in PROCESS_TOOLS if name!='estimate_process_energy'):
        missing=results['estimate_process_energy'].get('energy',{}).get('missing',[])
        if not missing:return None
        return make('energy_parameters',('Какие параметры нагрева вам известны: масса нагреваемой загрузки и её начальная температура? Остальные неизвестные значения можно оставить пустыми.', 'Do you know the heated charge mass and initial temperature? Other unknown values may remain blank.', 'Қыздырылатын жүктеменің массасы мен бастапқы температурасы белгілі ме? Басқа белгісіз мәндерді бос қалдыруға болады.'),missing[:2])
    if state.value('reactor_working_volume_l') is None:
        return make('working_volume', ('Какой рабочий объём реактора? Полный объём не равен допустимой жидкой загрузке.', 'What is the working volume? Total vessel volume is not its permitted liquid charge.', 'Реактордың жұмыс көлемі қандай? Толық көлем рұқсат етілген сұйық жүктемеге тең емес.'), ['reactor_working_volume_l'])
    if state.value('operating_mode') is None:
        return make('operating_mode', ('Загрузка периодическая или непрерывная? От этого зависит план переработки.', 'Is loading batch or continuous? The processing plan depends on this.', 'Жүктеу мерзімді ме, әлде үздіксіз бе? Өңдеу жоспары осыған байланысты.'), ['operating_mode'], ['Периодический (batch)', 'Непрерывный'] if lang == 'ru' else ['Batch', 'Continuous'])
    if 'economic_comparison' in state.intents: return previous
    if state.value('inoculum_volume_l') is None or state.value('dilution_water_l') is None:
        return make('liquid_occupancy', ('Какой объём займут инокулят и вода для разбавления? Если их не добавляете, укажите это явно.', 'What volumes are occupied by inoculum and dilution water? State explicitly if neither is added.', 'Инокулят пен сұйылту суының көлемі қандай? Қоспасаңыз, оны нақты көрсетіңіз.'), ['inoculum_volume_l', 'dilution_water_l'])
    return previous


def response(state, results):
    """Human text uses only actually computed fields; never a surrogate performance curve."""
    from src.agent.dialogue_response import choose, fmt
    result = next((results[name] for name in reversed(PROCESS_TOOLS) if name in results), None)
    if not result: return [], []
    lang = state.language
    if result.get('status')=='error':
        return [choose(lang,'Не удалось принять параметры оптимизатора. Проверьте единицы и согласованность исходных данных; оптимальный режим не выбран.','The optimizer could not accept these inputs. Check units and consistency; no optimal regime was selected.','Оңтайландырғыш деректерді қабылдамады. Бірліктер мен сәйкестікті тексеріңіз; оңтайлы режим таңдалмады.')],[]
    lines = [choose(lang, 'Проверил варианты процесса. При неполных данных единственный лучший режим не назначается.', 'I checked the process alternatives. Incomplete data do not establish a unique best regime.', 'Процесс нұсқаларын тексердім. Деректер толық болмаса, жалғыз үздік режим тағайындалмайды.')]
    if state.value('reactor_working_volume_l') is not None:
        value = fmt(state.value('reactor_working_volume_l'), lang)
        lines.append(choose(lang, f'Рабочий объём сохранён: {value} л. Для плана партий нужны режим загрузки, доли инокулята/воды и длительность цикла.', f'Working volume retained: {value} L. Batch planning also needs loading mode, inoculum/water occupancy and cycle time.', f'Жұмыс көлемі сақталды: {value} л. Партия жоспарына жүктеу режимі, инокулят/су көлемі және цикл ұзақтығы қажет.'))
    scenarios = result.get('scenarios', [])
    if not scenarios and result.get('energy'):
        scenarios=[{'label':choose(lang,'Текущий расчёт','Current calculation','Ағымдағы есеп'),'predicted_outputs':{'energy':result['energy']}}]
    selected = state.assumptions.get('process_candidates')
    if selected and len(selected.value.get('temperatures_c', [])) > 1:
        temps = ' / '.join(fmt(v, lang) for v in selected.value['temperatures_c'])
        lines.append(choose(lang, f'{temps} °C — заданные вами варианты. Зависимость BMP от температуры не установлена; больший выход метана при нагреве не предполагается.', f'{temps} °C are your chosen alternatives. A BMP-temperature response is not established; more methane from heating is not assumed.', f'{temps} °C — сіз таңдаған нұсқалар. BMP-нің температураға тәуелділігі анықталмаған; қыздыру метанды көбейтеді деп есептелмейді.'))
    for scenario in scenarios[:4]:
        outputs = scenario.get('predicted_outputs', {})
        energy = outputs.get('energy', {})
        if energy.get('total_energy_kwh') is not None:
            lines.append(f"{scenario.get('label', '')}: " + choose(lang, 'энергия ', 'energy ', 'энергия ') + fmt(energy['total_energy_kwh'], lang) + ' kWh.')
        elif energy.get('initial_heating_kwh') is not None:
            lines.append(f"{scenario.get('label', '')}: " + choose(lang,'только первоначальный нагрев ','initial heating only ','тек бастапқы қыздыру ') + fmt(energy['initial_heating_kwh'],lang) + choose(lang,' kWh; поддержание температуры и полный баланс ещё не установлены.',' kWh; temperature maintenance and the complete balance remain unestablished.',' kWh; температураны сақтау мен толық теңгерім әлі анықталмаған.'))
        methane = outputs.get('methane', {})
        potential = methane.get('potential_methane_m3')
        if potential is not None:
            lines.append(f"{scenario.get('label', '')}: " + choose(lang, 'потенциал метана ', 'methane potential ', 'метан әлеуеті ') + fmt(potential, lang) + choose(lang, ' м³; фактический выход установки не измерен.', ' m³; actual plant output is not measured.', ' м³; қондырғының нақты шығымы өлшенбеген.'))
        economics=outputs.get('economics',{})
        labels={'A':choose(lang,'продажа сырья','feedstock sale','шикізатты сату'),'B':choose(lang,'собственная энергия','own energy','өз энергиясы'),'C':choose(lang,'продажа газа','gas sale','газды сату'),'D':choose(lang,'дигестат','digestate','дигестат')}
        for row in economics.get('scenarios',[]):
            if row.get('status')=='ok' and row.get('net_profit') is not None:
                lines.append(f"{scenario.get('label','')} · {labels.get(row.get('scenario'),row.get('scenario',''))}: " + choose(lang,'чистый расчётный результат ','calculated net result ','есептелген таза нәтиже ') + fmt(row['net_profit'],lang)+' '+economics.get('currency','')+'.')
    if not any(s.get('predicted_outputs', {}).get('energy', {}).get('total_energy_kwh') is not None for s in scenarios):
        lines.append(choose(lang, 'Полных энергозатрат пока нет: нужны масса нагреваемой загрузки, начальная температура, теплоёмкость, КПД, длительность, теплопотери и вспомогательное потребление.', 'Total energy is incomplete: heated charge mass, initial temperature, heat capacity, efficiency, duration, heat loss and auxiliary use are needed.', 'Толық энергия шығыны белгісіз: жүктеменің массасы, бастапқы температура, жылусыйымдылық, ПӘК, уақыт, жылу жоғалту және қосымша тұтыну қажет.'))
    sources = result.get('scientific_sources', []) or result.get('energy',{}).get('scientific_sources',[])
    return lines, sources
