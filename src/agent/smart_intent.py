"""Current-turn goals take precedence over inherited dialogue intents."""
import re
PATTERNS={
 'gas':r'газ|метан|\bbmp\b|\bgas\b|biogas|methane',
 'temperature':r'температур|градус|temperature|degrees',
 'duration':r'сколько\s+дн|суток|сколько.*врем|продолжитель|срок|how long|duration|\bhrt\b|\bsrt\b|қанша.*(?:күн|уақыт)',
 'economics':r'выгод|прибыл|стоим|стоит|цен[ауы]|продать|продаж|отоплен|электрич|profit|sell|cost|heat\b|electricity|тиімді|пайда',
 'compare':r'сравни.*(?:смес|состав|материал)|какая\s+смесь|какой\s+состав|compare.*(?:mixture|material)|which mixture',
 'reactor':r'состояни.*реактор|статус.*реактор|датчик|reactor status|sensor|датчик.*күй',
 'loading':r'загруз.*сразу|всё\s+сразу|все\s+сразу|can.*load|all.*once',
}
def identify(text,state):
    if re.search(r'источник|откуда.*(?:числ|данн)|\bsources?\b|дереккөз',text,re.I):return {'goals':list(state.smart_goals),'delegate_legacy':False,'detail':False,'one_sentence':False,'edit':False,'explicit':True,'source_only':True}
    if re.search(r'что\s+такое.*биогаз|what is biogas|биогаз деген',text,re.I):return {'goals':[],'delegate_legacy':False,'detail':False,'one_sentence':False,'edit':False,'explicit':True,'definition':True}
    detail=bool(re.search(r'подроб|объясни|почему|формул|detail|explain|why|толық|түсіндір',text,re.I))
    meta_detail=bool(re.fullmatch(r'\s*(?:объясни(?:\s+подробнее|\s+расч[её]т)?|подробнее|почему|explain(?:\s+more|\s+the calculation)?|more details|why|толығырақ|түсіндір)[.!?]?\s*',text,re.I))
    one=bool(re.search(r'одним\s+предлож|одно\s+предлож|one\s+sentence|бір\s+сөйлем',text,re.I))
    edit=bool(re.search(r'добав|убери|удали|замени|вдвое|\badd\b|remove|replace|double|қос|алып\s+таста',text,re.I))
    goals=[k for k,p in PATTERNS.items() if re.search(p,text,re.I)]
    # Mentioning an ingredient during an edit is not a request for every output.
    if edit and not re.search(r'сколько|какая|какой|выгод|сравни|how|what.*(?:yield|temperature)|қанша|қандай',text,re.I):goals=[]
    if re.search(r'точност|модел.*огранич|model.*limit|accuracy|mae|rmse|истори.*цен|price history',text,re.I):return {'goals':[],'delegate_legacy':True,'detail':detail,'one_sentence':one,'edit':edit,'explicit':False}
    explicit=bool(goals)
    needs_interpretation=detail and not meta_detail and not goals and not one
    if not goals and (meta_detail or one or edit or text.lstrip().startswith('{')):goals=list(state.smart_goals)
    if not goals and state.pending_question and state.pending_question.id in {'research-material-form','advisor-state','advisor-species','decision-gas-use'}:goals=list(state.smart_goals)
    # A form clarification preserves the last task, not an unrelated old intent.
    if not goals and state.smart_goals and re.fullmatch(r'\s*(?:навозная жижа|коровий|с подстилкой|cattle slurry|сұйық көң)[.!]?\s*',text,re.I):goals=list(state.smart_goals)
    return {'goals':goals,'detail':detail and not one,'one_sentence':one,'edit':edit,'explicit':explicit,'delegate_legacy':False,'needs_interpretation':needs_interpretation}

def fast_followup(text,state,plan):
    if plan.get('needs_interpretation'):return False
    # Initial, mixed or ambiguous messages still receive local Qwen interpretation.
    if re.search(r'\d',text) and not plan['edit']:return False
    return bool((state.smart_goals or state.value('material') or state.mixture_components) and (plan['explicit'] or plan['detail'] or plan['one_sentence'])) and len(text.split())<=12 and not plan['delegate_legacy']
