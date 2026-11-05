"""Task boundaries and typed input diagnostics, separate from physical modelling."""
import re
import uuid
from enum import Enum
from src.agent.dialogue_types import DialogueState, Entity, Question


class EventType(str, Enum):
    AmbiguousIntent = 'AmbiguousIntent'
    ConflictingValuesInSameRequest = 'ConflictingValuesInSameRequest'
    UpdatedPreviousValue = 'UpdatedPreviousValue'
    NewBatch = 'NewBatch'
    MissingScientificParameters = 'MissingScientificParameters'
    InvalidPhysicalParameters = 'InvalidPhysicalParameters'


def event(kind, phase, **details):
    return {'type': kind.value if isinstance(kind, EventType) else kind, 'phase': phase, **details}


def prepare(text, state, extraction):
    """Return a tentative task state; the caller commits only validated updates."""
    from src.agent.mixture_parser import amounts
    from src.agent.nlu import NUMBER
    entries = extraction.entities
    events = []
    issues = []
    hypothetical = bool(re.search(r'\bесли\b|what\s+if|\bif\b|егер', text, re.I))
    values = amounts(text)
    # Two unlabelled corrections follow the two previously established roles.
    # Without that unique context, ask about intent rather than alleging conflict.
    unlabelled = extraction.correction and len(values) == 2 and not re.search(r'реактор|reactor|навоз|manure|отход|waste', text, re.I)
    if unlabelled:
        single = state.advisor_inventory_mode != 'mixture' and len(state.mixture_components) <= 1
        if single and state.value('unit') in {'L', 'm3'} and state.value('reactor_total_volume_l') is not None and all(v['unit'] in {'L', 'm3'} for v in values):
            entries[:] = [e for e in entries if e.name not in {'quantity', 'unit', 'material_volume_l', 'reactor_total_volume_l'}]
            feed, tank = values
            entries.extend([Entity(name='quantity', value=feed['value'], unit=feed['unit'], evidence=feed['text']),
                            Entity(name='unit', value=feed['unit'], evidence=feed['text']),
                            Entity(name='reactor_total_volume_l', value=tank['value']*(1000 if tank['unit']=='m3' else 1), unit='L', evidence=tank['text'])])
            events.append(event(EventType.UpdatedPreviousValue, 'intent_resolution', binding='previous_single_feed_then_reactor_order'))
        else:
            issues.append(event(EventType.AmbiguousIntent, 'intent_resolution', fields=['quantity', 'reactor_total_volume_l'],
                                reason='Two unlabelled quantities have no unique previous role assignment.'))
    # Shared-unit reports such as "47 and 478 litres of the same batch" cannot
    # be represented by last-write-wins. Alternatives and mixtures are exempt.
    shared = re.search(r'('+NUMBER+r')\s*(?:и|and)\s*('+NUMBER+r')\s*(?:литр\w*|л\b|litres?|liters?|L\b|кг\b|kg\b)', text, re.I)
    same_batch = bool(re.search(r'одновремен|одн\w*\s+и\s+т\w*\s+же\s+парти|same\s+batch|simultaneously', text, re.I))
    if shared and same_batch and not extraction.correction:
        candidates = [float(shared[i].replace(',', '.')) for i in (1, 2)]
        if candidates[0] != candidates[1]:
            issues.append(event(EventType.ConflictingValuesInSameRequest, 'parameter_extraction', field='quantity', values=candidates,
                                unit=values[-1]['unit'] if values else None, evidence=shared.group(), scope='current_request_same_batch'))
    if same_batch and not extraction.correction and not issues:
        reported=[e for e in entries if e.name=='quantity']
        converted=[e.value*({'m3':1000,'L':1,'kg':1,'t':1000,'g':.001}.get(e.unit,1)) for e in reported]
        if len(set(converted))>1:
            issues.append(event(EventType.ConflictingValuesInSameRequest,'parameter_extraction',field='quantity',values=converted,scope='current_request_same_batch'))
    for key in ('reactor_total_volume_l', 'reactor_working_volume_l', 'density_kg_l', 'ts_percent', 'vs_percent', 'vs_mass_kg'):
        supplied = [e for e in entries if e.name == key and e.provenance == 'USER_CONFIRMED']
        distinct = list(dict.fromkeys(e.value for e in supplied))
        if len(distinct) > 1 and not extraction.correction and not hypothetical:
            issues.append(event(EventType.ConflictingValuesInSameRequest, 'parameter_extraction', field=key, values=distinct, scope='current_request'))
    if issues:
        return state, events, issues
    owns = bool(re.search(r'у\s+меня|имеется|\bi\s+have\b|менде', text, re.I))
    batch_description = owns and any(e.name == 'material' for e in entries) and any(e.name == 'quantity' for e in entries)
    edit = bool(re.search(r'добав|убери|удали|замени|\badd\b|\bremove\b|\breplace\b', text, re.I))
    fresh = extraction.new_batch or batch_description and not (extraction.correction or hypothetical or edit)
    if fresh:
        condition_cache=state.smart_cache.get('conditions')
        prior = state.model_dump(mode='json')
        archive = list(state.task_history)
        if state.facts or state.mixture_components:
            archive.append({k: prior[k] for k in ('facts', 'assumptions', 'mixture_components', 'decision_settings', 'intents')})
        state = DialogueState(version=state.version, conversation_id=state.conversation_id, language=extraction.language,
                              mixture_history=state.mixture_history, mixture_revision=state.mixture_revision,
                              task_history=archive[-30:],task_id=uuid.uuid4().hex)
        if not any(e.name=='quantity' for e in entries) and 'inventory' in prior['advanced']:
            state.advanced={'inventory':[]}
        # This cache is keyed by material/form/source revision, not batch size;
        # the existing conditions service rebuilds request and geometry on hits.
        if condition_cache:state.smart_cache['conditions']=condition_cache
        if 'model' in prior['facts']:
            from src.agent.dialogue_types import Fact
            state.facts['model'] = Fact.model_validate(prior['facts']['model'])
        extraction.new_batch = True
        events.append(event(EventType.NewBatch, 'task_transition', task_id=state.task_id, previous_task_archived=bool(archive)))
    else:
        state = state.model_copy(deep=True)
        if state.task_id is None:state.task_id=uuid.uuid4().hex
    if hypothetical and state.version=='7':
        for e in entries:
            if e.name in {'reactor_total_volume_l', 'reactor_working_volume_l', 'dilution_water_l', 'temperature_c'}:
                e.provenance = 'ASSUMED_FOR_SCENARIO'
        events.append(event('ConditionalScenario', 'task_transition', confirmed_values_replaced=False))
    for e in entries:
        previous = state.value(e.name)
        if e.provenance == 'USER_CONFIRMED' and previous is not None and previous != e.value:
            events.append(event(EventType.UpdatedPreviousValue, 'task_transition', field=e.name, previous=previous, value=e.value, evidence=e.evidence))
    if not events:
        events.append(event('Clarification', 'task_transition', task_id=state.task_id))
    return state, events, []


def rejected(agent, issues, extraction=None):
    issue = issues[0]
    genuine = issue['type'] == EventType.ConflictingValuesInSameRequest.value
    field = issue.get('field', 'quantity')
    if genuine:
        label = {'quantity': 'объём или масса одной партии', 'reactor_total_volume_l': 'полный объём реактора',
                 'reactor_working_volume_l': 'рабочий объём реактора'}.get(field, field)
        body = f"В одном запросе для параметра «{label}» указаны разные значения: {', '.join(str(v) for v in issue['values'])} {issue.get('unit') or ''}. Одновременно использовать их как одно измерение нельзя. Предыдущие данные не заменены."
        question = 'Какое значение относится к этой партии или установке?'
    elif issue['type'] == EventType.AmbiguousIntent.value:
        body = 'Неясно, к каким параметрам относятся новые значения. Это неоднозначность назначения чисел, а не противоречие измерений.'
        question = 'Какое значение относится к сырью, а какое — к реактору?'
    else:
        body = 'Параметр не прошёл проверку допустимых значений: ' + str(issue.get('reason', ''))
        question = 'Каково исправленное значение и его единица измерения?'
    trace = []
    # The model has already inspected this request. Check available evidence
    # without ever scaling yield using contradictory batch quantities.
    if extraction and genuine:
        from src.agent import analytical
        data = analytical.context(agent.state)
        material = next((e.value for e in extraction.entities if e.name == 'material'), None)
        if material:
            data['facts']['material'] = material
        result = agent.registry.execute('search_substrate_profiles', {'analytical_context': data}, {}, '')
        trace.append({'tool': 'search_substrate_profiles', 'status': result['status'], 'result': result, 'input_origin': 'identity_only_no_conflicting_quantity'})
    pending = Question(id='resolve-'+field, text=question, fields=[field])
    return {'conversation_version': agent.state.version, 'mode': 'input_rejected' if issue['type']==EventType.InvalidPhysicalParameters.value else 'input_needs_clarification', 'answer': body+'\n\n'+question,
            'user_facing_answer': {'paragraphs': [body], 'question': pending.model_dump(), 'sources': [], 'assumptions': [], 'modes': ['validation']},
            'error_type': issue['type'], 'tools': trace, 'provider_status': list(agent.llm.status), 'actuator_access': False,
            'context_updated': False, 'context': dict(agent.context), 'memory': agent.state.model_dump(mode='json'),
            'missing': [field], 'pending_question': pending.model_dump(), 'technical_metadata': {'input_issues': issues}}
