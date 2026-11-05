"""Persist clarification intent and prevent asking the same unresolved question in a loop."""
import re
import hashlib
from src.agent.dialogue_types import Question

CATEGORIES = {'heating': r'нагрев|подогрев|heating',
              'maintenance': r'обслуживан|maintenance',
              'preparation': r'подготовк|preparation',
              'transport': r'транспорт|доставк|transport',
              'storage': r'хранени|storage'}


def finish_turn(state, text, extraction, facing, body, results):
    memory = state.advanced.setdefault('research_dialogue', {})
    asked = memory.setdefault('asked', [])
    categories = [k for k, p in CATEGORIES.items() if re.search(p, text, re.I)]
    no_amounts = bool(categories) and not re.search(r'\d', text)
    relation = ('correction' if extraction.correction else
                'incomplete_answer' if no_amounts else
                'comparison' if state.analytical_mode == 'alternatives' else
                'explanation' if re.search(r'почему|объясни|источник|why|explain', text, re.I) else
                'agreement' if re.fullmatch(r'\s*(?:да|согласен|yes)[.!]?\s*', text, re.I) else
                'negation' if re.fullmatch(r'\s*(?:нет|no)[.!]?\s*', text, re.I) else
                'clarification' if not extraction.intents and extraction.entities else 'new_question')
    memory['last_turn_type'] = relation
    memory['known_cost_categories'] = list(dict.fromkeys(memory.get('known_cost_categories', []) + categories))
    memory['unpriced_categories'] = [k for k in memory['known_cost_categories']
                                    if k not in state.decision_settings.get('costs', {})]
    diagnostics = []
    q = facing.get('question')
    has_batch=bool(state.mixture_components or state.mixture_scenario_components or state.value('quantity') or state.value('mass_kg'))
    if not q and not has_batch and state.value('material') and set(state.intents)&{'methane_yield','economic_comparison'}:
        q={'id':'batch-quantity','text':'Какова масса партии в килограммах?','fields':['quantity','unit'],'options':[],
           'reason':'Quantity is the missing input needed to scale the available scientific evidence.'}
    if not q:
        candidates=[s.strip() for s in re.findall(r'[^.!?\n]+\?',body) if re.search(r'како|сколько|где|уточн|what|which|how|where|қандай|қай',s,re.I) and len(s)<400]
        if candidates:
            text_question=candidates[-1]
            has_batch=bool(state.mixture_components or state.mixture_scenario_components or state.value('quantity') or state.value('mass_kg'))
            if not has_batch:
                identifier='batch-quantity';fields=['quantity','unit']
            elif re.search(r'регион|region|өңір',text_question,re.I):
                identifier='market-region';fields=['market_region']
            elif re.search(r'расход|затрат|cost',text_question,re.I):
                identifier='operating-costs';fields=['operating_costs']
            elif re.search(r'плотност|density',text_question,re.I):
                identifier='feed-density';fields=['density_kg_l']
            else:
                identifier='model-question-'+hashlib.sha256(text_question.casefold().encode()).hexdigest()[:12];fields=[]
            if not(identifier=='market-region' and state.value('market_region')):
                q={'id':identifier,'text':text_question,'fields':fields,'options':[], 'reason':'Model-selected clarification retained after available analysis.'}
    if no_amounts:
        note = ('Вы назвали категории затрат, но не суммы. Эти расходы остаются неизвестными. '
                'Можно заполнить отдельный редактируемый сценарий; результат будет условным. '
                'Верхняя граница допустимых суммарных затрат равна применимой валовой ценности энергии до расходов.'
                if state.language == 'ru' else
                'Cost categories were named without amounts. They remain unknown; an editable cost scenario must be labelled hypothetical.')
        facing.setdefault('paragraphs', []).insert(0, note)
        if facing.get('sections'): facing['sections'][-2]['body'] += ' ' + note
        body = note + '\n\n' + body
    if q and q['id'] in asked:
        diagnostics.append({'stage': 'clarification', 'reason': 'repeated_question_suppressed', 'question_id': q['id']})
        q = None
        # A concrete measurement has higher value than repeating broad costs.
        if no_amounts and 'heating-kwh' not in asked:
            q = {'id': 'heating-kwh', 'text': 'Сколько кВт·ч уходит на нагрев одной партии?',
                 'fields': ['auxiliary_energy_kwh'], 'options': [],
                 'reason': 'A numerical heat demand can change the economic conclusion.'}
    if q:
        asked.append(q['id']); memory['asked'] = asked[-32:]
    facing['question'] = q
    facing['paragraphs']=[re.sub(r'[^.!?\n]*\?','',p).strip() for p in facing.get('paragraphs',[]) if re.sub(r'[^.!?\n]*\?','',p).strip()]
    state.pending_question = Question.model_validate(q) if q else None
    # The complete tool evidence is retained separately. Exactly one explicit
    # clarification appears in the answer, matching the structured UI question.
    body = re.sub(r'[^.!?\n]*\?','',body).strip()
    if q: body += '\n\n' + q['text']
    memory['last_question_id'] = q['id'] if q else None
    return facing, body, diagnostics
