"""Ground prose quantities against selected typed outputs and literal input units."""
import math
import re

NUMBER=r'[-+]?[0-9]+(?:[.,][0-9]+)?'
UNIT=re.compile(r'\s*(?:[-–—]\s*'+NUMBER+r')?\s*[- ]?\s*'
    r'(мл\s*(?:CH[4₄])?\s*/\s*г\s*VS|ml\s*(?:CH4)?\s*/\s*g\s*VS|'
    r'кВт[·⋅* .]?ч|kWh|KZT|тенге|тг\b|°\s*C|°\s*С|градус\w*|'
    r'м³|м3|m³|m3|кубометр\w*|кг\s*VS|kg\s*VS|кг\b|kg\b|килограмм\w*|'
    r'литр\w*|lit[er]\w*|L\b|л\b|%|процент\w*)',re.I)

def unit(value):
    value=value.casefold().replace(' ','')
    if 'vs' in value and ('мл' in value or 'ml' in value):return 'bmp'
    if value.startswith(('квт','kwh')):return 'energy'
    if value in {'kzt','тенге','тг'}:return 'money'
    if value.startswith(('°','градус')):return 'temperature'
    if value.startswith(('м³','м3','m³','m3','кубометр')):
        if any(s in value for s in ['ch4','ch₄','метан','methane']):return 'methane_m3'
        if any(s in value for s in ['биогаз','biogas']):return 'biogas_m3'
        return 'm3'
    if 'vs' in value:return 'kg_vs'
    if value in {'кг','kg'} or value.startswith('килограмм'):return 'kg'
    if value=='%' or value.startswith('процент'):return 'percent'
    if value in {'l','л'} or value.startswith(('литр','lit')):return 'L'
    return value

def check(texts,evidence,ids,state=None,diagnostics=None):
    known=[]
    for key in ids:
        ref=evidence.get(key)
        if not ref:continue
        value=ref['value']
        for bound in ['low','high']:
            if isinstance(value,dict) and isinstance(value.get(bound),(int,float)):
                known.append((value[bound],unit(ref['unit'])))
    if state:
        for name,fact in {**state.derived,**state.assumptions,**state.facts}.items():
            value=fact.value
            if not isinstance(value,(int,float)) or isinstance(value,bool):continue
            label=fact.unit
            if name=='quantity':label=state.value('unit') or label
            if name in {'reactor_total_volume_l','reactor_working_volume_l','material_volume_l','dilution_water_l'}:label='L'
            if name in {'mass_kg','heated_mass_kg'}:label='kg'
            if name=='vs_mass_kg':label='kg VS'
            if name in {'ts_percent','vs_percent'}:label='%'
            if name=='temperature_c':label='°C'
            if label:known.append((value,unit(label)))
            if name in {'methane_fraction','recovery_fraction','electricity_efficiency'}:known.append((value*100,'percent'))
    def supported(value,label,decimals):
        return any((label==kind or label=='m3' and kind in {'methane_m3','biogas_m3'}) and math.isfinite(expected) and abs(value-expected)<=max(1e-8,min(.5*10**-decimals,max(1e-8,abs(expected)*.01))) for expected,kind in known)
    issues=[]
    from src.agent.quantity_words import amounts
    for text in texts:
        text=text.replace('−','-')
        if re.search(r'https?://',text):issues.append('source_links_must_use_verified_sources')
        if re.search(r'\bs[0-9]+\.[a-z_]',text,re.I):issues.append('evidence_id_outside_reference_list')
        for token in re.finditer(r'(?<![\w])('+NUMBER+r')',text):
            tail=UNIT.match(text[token.end():]);value=float(token[1].replace(',','.'))
            decimals=len(token[1].split('.')[-1]) if '.' in token[1] else len(token[1].split(',')[-1]) if ',' in token[1] else 0
            label=unit(tail[1]) if tail else None
            if label=='m3':
                suffix=re.match(r'\s*(CH[4₄]|метан\w*|methane|биогаз\w*|biogas)',text[token.end()+tail.end():],re.I)
                if suffix:label=unit(tail[1]+' '+suffix[1])
                else:
                    mentions=list(re.finditer(r'метан\w*|methane|биогаз\w*|biogas',text[max(0,token.start()-120):token.start()],re.I))
                    if mentions:label=unit(tail[1]+' '+mentions[-1][0])
            if not tail or not supported(value,label,decimals):
                issues.append('ungrounded_quantity_or_wrong_unit')
                if diagnostics is not None:diagnostics.append({'rejected_value':value,'unit':label,'allowed_typed_values':[{'value':v,'unit':u} for v,u in known]})
        for amount in amounts(text):
            if not supported(amount['value'],unit(amount['unit']),0):issues.append('ungrounded_quantity_or_wrong_unit')
    return list(dict.fromkeys(issues))
