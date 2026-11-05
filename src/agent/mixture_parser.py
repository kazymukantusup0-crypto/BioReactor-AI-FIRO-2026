"""Independent RU/KK/EN quantity-to-material binding and reversible inventory edits."""
import copy,json,re
from src.advisor.catalog import matches,normalized
from src.advisor.schemas import Component
from src.advisor.mixing import FACTORS
from src.agent.nlu import NUMBER,numeric,language_of

UNIT=r'(?:килограмм\w*|кг\b|kg\b|грамм\w*|г\b|g\b|тонн\w*|т\b|t\b|миллилитр\w*|мл\b|ml\b|литр\w*|л\b|litres?\b|liters?\b|l\b|м[³3]|m[³3])'
AMOUNT=re.compile(r'(?P<number>'+NUMBER+r')\s*(?P<unit>'+UNIT+r')',re.I)
def unit(text):
    text=text.casefold()
    if re.match(r'мл|миллилитр|ml',text):return 'mL'
    if re.match(r'кг|килограмм|kg',text):return 'kg'
    if re.match(r'тонн|т$|t$',text):return 't'
    if re.match(r'м[³3]|m[³3]',text):return 'm3'
    if re.match(r'г$|грамм|g$',text):return 'g'
    return 'L'
def state_of(text):
    for value,pattern in [
        ('bedded',r'подстил|bedd|litter|төсеніш'),
        ('semiliquid',r'полужид|semi.?liquid'),
        ('slurry',r'жиж|жидк\w*|liquid|slurry|сұйық\s+көң'),
        ('prepared_pulp',r'пульп|измельч[её]н\w*\s+пищ|prepared\s+pulp|ground\s+food'),
        ('compost',r'перегно|компост|compost'),
        ('silage',r'силос|silage|сүрлем'),
        ('dry',r'сух\w*|dry|құрғақ'),
        ('fresh_solid',r'свеж\w*|тв[её]рд\w*|fresh|solid'),
        ('shredded',r'измельч|shredded|ұсақталған'),
    ]:
        if re.search(pattern,text,re.I):return value
    return 'unknown'
def poultry_type_of(text):
    for value,pattern in [('broiler',r'бройлер|broiler'),('layer',r'несуш|laying\s+hen|layer'),('turkey',r'индюш|turkey'),('chicken',r'курин|chicken|hen')]:
        if re.search(pattern,text,re.I):return value
    return 'unknown'
def amounts(text):
    from src.agent.quantity_words import amounts as word_amounts
    rows=[{'value':numeric(m['number'],language_of(text)),'unit':unit(m['unit']),'start':m.start(),'end':m.end(),'text':m.group()} for m in AMOUNT.finditer(text)]
    return sorted(rows+word_amounts(text),key=lambda row:row['start'])
def explicit_components(text):
    # In a quantity correction the rejected amount is evidence of the old
    # value, not an unbound additional component. Keep span offsets stable.
    correction=re.compile(r'\b(?:не|not)\s*'+NUMBER+r'\s*'+UNIT+r'\s*[,;]?\s*(?:а\b|but\b)\s*',re.I)
    text=correction.sub(lambda m:' '*len(m.group()),text)
    values=amounts(text);result=[];unbound=[]
    for index,a in enumerate(values):
        from src.agent.quantity_roles import reactor_field
        if reactor_field(text,a['start'],a['end']):continue
        next_start=values[index+1]['start'] if index+1<len(values) else len(text)
        after=text[a['end']:min(next_start,a['end']+110)]
        before=text[(values[index-1]['end'] if index else 0):a['start']]
        if re.match(r'\s*[-–]?\s*(?:reactor|digester|реактор)',after,re.I):continue
        if re.match(r'\s*/',after):continue  # density/concentration units are not inventory amounts
        if re.search(r'(?:рабоч\w*\s+объ[её]м|working\s+volume|газов\w*\s+пространств\w*|headspace|остаток\s+жидкости)\s*[:=]?\s*$',before,re.I):continue
        if re.match(r'\s*(?:вод[аыу]|water\b|инокул\w*|inoculum\b)',after,re.I) or re.search(r'(?:вод[аыу]|water|инокул\w*|inoculum)\s*[:=]?\s*$',before,re.I):continue
        if re.match(r'\s*(?:of\s+)?(?:measured\s+)?(?:VS\b|volatile\s+solids\b)',after,re.I) or re.search(r'(?:\bVS|volatile\s+solids)(?:\s+mass)?\s*(?:is|of|=|:)?\s*$',before,re.I):continue
        future=matches(after);past=matches(before)
        if re.search(r'(?:реактор|reactor|digester|жұмыс.*көлем).{0,35}$',before,re.I) and not future:continue
        preceding=past[-1] if past and re.fullmatch(r'\s*[:=]?\s*',before[past[-1]['end']:]) else None
        # A nearby but unrelated material must not absorb an unknown component.
        future=[hit for hit in future if re.fullmatch(r'\s*(?:(?:of|wet|dry|fresh|liquid|slurry|bedded|влажн\w*|жидк\w*|полужидк\w*|свеж\w*|сух\w*|тв[её]рд\w*|подстил\w*|измельч[её]н\w*)\s+)*',after[:hit['start']],re.I)]
        past_valid=past[-1] if past and re.fullmatch(r'\s*(?:(?:есть|имеется|массой|весом|weighs|is|бар)\s*)?[:=]?\s*',before[past[-1]['end']:],re.I) else None
        hit=preceding or (future[0] if future else past_valid)
        if hit:
            segment=before[max(0,hit['start']-12):] if preceding else after[:future[1]['start']] if future and len(future)>1 else after if future else before[max(0,hit['start']-12):]
            from src.advisor.material_axes import extract as extract_axes
            axes=extract_axes(segment)
            result.append(Component(id='c'+str(len(result)+1),material=hit['material'],material_state=state_of(segment),
                animal=axes.get('animal','unknown'),physical_state=axes.get('physical_state','unknown'),
                decay_state=axes.get('decay_state','unknown'),bedding=axes.get('bedding','unknown'),
                poultry_type=poultry_type_of(segment) if hit['material']=='poultry_manure' else 'unknown',
                quantity=a['value'],unit=a['unit'],evidence=text[max(0,a['start']-30):min(len(text),a['end']+110)]))
        else:unbound.append(a['text'])
    if result and unbound:raise ValueError('Unbound material quantities: '+', '.join(unbound)+'. Specify each component explicitly; unknown material is not assigned to another component.')
    return result

def parse_turn(text,state):
    current=[Component.model_validate(c) for c in state.mixture_components]
    if re.search(r'вод[аыу]|\bwater\b',text,re.I) and not matches(text):
        return None  # Dilution is a process input, not an inventory edit.
    if text.lstrip().startswith('{'):
        raw=json.loads(text)
        if 'mixture_components' in raw:
            components=[Component.model_validate(c) for c in raw['mixture_components']]
            if not components:raise ValueError('At least one component is required')
            return {'components':components,'scenario':False,'action':'set','changed':True}
        return None
    add=bool(re.search(r'добав|\badd\b|қос',text,re.I));remove=bool(re.search(r'убери|убрать|удали|исключи|remove|exclude|алып\s+таста',text,re.I))
    change_edit=r'\bchange\s+(?:(?:the|my|this|that)\s+)?(?:quantity|amount|mass|volume|dose|feed|substrate|material|manure|food\s+waste|\d+(?:[.,]\d+)?)\b.{0,70}\b(?:to|by|into)\b'
    replace=bool(re.search(r'замени|заменить|\breplace\b|'+change_edit+r'|ауыстыр',text,re.I))
    double=bool(re.search(r'вдвое|в\s+два\s+раза|double|екі\s+есе',text,re.I))
    hypothesis=bool(re.search(r'что\s+измен|если|допустим|предполож|what\s+if|\bassume|егер|болжам',text,re.I))
    if not current and (add or remove or replace or double) and state.value('material') and state.value('quantity') is not None and state.value('unit'):
        try:current=[Component(id='c1',material=normalized(state.value('material')),material_state=state.value('material_state','unknown'),quantity=state.value('quantity'),unit=state.value('unit'),evidence='Prior confirmed single-substrate inventory')]
        except ValueError:pass
    candidates=[] if replace or remove or double else explicit_components(text)
    if current and (add or remove or replace or double):
        hits=matches(text);targets={x['material'] for x in hits}
        if not targets:raise ValueError('Specify the material to edit')
        if 'manure' in targets:
            species={c.material for c in current if c.material.endswith('_manure')}
            if len(species)!=1:raise ValueError('Specify which manure component')
            targets.remove('manure');targets.update(species)
        selected=[c for c in current if c.material in targets]
        result=copy.deepcopy(current)
        if remove:
            if not selected:raise ValueError('Material is not in the mixture')
            result=[c for c in result if c.material not in targets]
        elif double:
            if len(selected)!=1:raise ValueError('Doubling needs one unambiguous component')
            result=[c.model_copy(update={'quantity':c.quantity*2,'provenance':'ASSUMED_FOR_SCENARIO' if hypothesis else 'USER_CONFIRMED'}) if c.id==selected[0].id else c for c in result]
        elif replace:
            qs=amounts(text)
            if len(selected)!=1 or not qs:raise ValueError('Replacement needs one material and a new quantity')
            replacement=qs[-1];Component(id='check',material=selected[0].material,quantity=replacement['value'],unit=replacement['unit'])
            result=[c.model_copy(update={'quantity':replacement['value'],'unit':replacement['unit'],'provenance':'ASSUMED_FOR_SCENARIO' if hypothesis else 'USER_CONFIRMED'}) if c.id==selected[0].id else c for c in result]
        elif add:
            if not candidates:raise ValueError('Provide a material quantity to add')
            for new in candidates:
                family,factor=FACTORS[new.unit];existing=[c for c in result if c.material==new.material and FACTORS[c.unit][0]==family and (new.material_state=='unknown' or new.material_state==c.material_state)]
                if len(existing)>1:raise ValueError('Ambiguous component; use its ID in structured input')
                if existing:
                    c=existing[0];new_amount=c.quantity+new.quantity*factor/FACTORS[c.unit][1]
                    result=[r.model_copy(update={'quantity':new_amount,'provenance':'ASSUMED_FOR_SCENARIO' if hypothesis else 'USER_CONFIRMED'}) if r.id==c.id else r for r in result]
                else:
                    ids={c.id for c in result};n=1
                    while 'c'+str(n) in ids:n+=1
                    result.append(new.model_copy(update={'id':'c'+str(n)}))
        if not result:raise ValueError('Removing all materials leaves no mixture to calculate')
        return {'components':[Component.model_validate(c.model_dump()) for c in result],'baseline_components':current,'scenario':hypothesis,'action':'double' if double else 'remove' if remove else 'replace' if replace else 'add','changed':True}
    if not current and (remove or replace or double):raise ValueError('There is no confirmed inventory to edit')
    # "I have ... what if I mix it" confirms inventory, not biological performance.
    owns=bool(re.search(r'у\s+меня|имеется|\bi\s+have\b|менде',text,re.I))
    if len(candidates)>1:return {'components':candidates,'scenario':hypothesis and not owns,'action':'set','changed':True}
    if candidates:
        c=candidates[0];new_types=c.material not in {'cattle_manure','swine_manure','poultry_manure','food_waste'}
        conditions=bool(re.search(r'температур|градус|врем|суток|дней|срок|hrt|srt|duration|temperature|how\s+long|қанша\s+уақыт|температура',text,re.I))
        if new_types or conditions or current:return {'components':candidates,'scenario':hypothesis and not owns,'action':'set','changed':True}
    if current:
        if state.pending_question and state.pending_question.id=='advisor-species':
            species=next((value for value,pattern in [('cattle_manure',r'коров|\bкрс\b|cattle|cow|сиыр'),('swine_manure',r'свин|pig|swine|шошқа'),('poultry_manure',r'птич|курин|poultry|құс')] if re.search(pattern,text,re.I)),None)
            target=next((c for c in current if c.id==state.advisor_pending_component),None)
            if species and target:return {'components':[c.model_copy(update={'material':species}) if c.id==target.id else c for c in current],'scenario':False,'action':'species','changed':True}
        # One-word form clarification updates the uniquely matching component.
        form=state_of(text)
        if form!='unknown' and len(text.split())<=8:
            target=next((c for c in current if c.id==state.advisor_pending_component),None)
            if target is None and len(current)==1:target=current[0]
            if target:
                return {'components':[c.model_copy(update={'material_state':form}) if c.id==target.id else c for c in current],'scenario':False,'action':'state','changed':True}
    return None
