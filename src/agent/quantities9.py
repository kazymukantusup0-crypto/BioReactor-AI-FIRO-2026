"""Ground prose quantities against selected typed outputs and literal input units."""
import math
import re

NUMBER=r'[-+]?[0-9]+(?:[.,][0-9]+)?'
UNIT=re.compile(r'\s*(?:[-–—]\s*'+NUMBER+r')?\s*[- ]?\s*'
    r'(мл\s*(?:CH[4₄])?\s*/\s*г\s*VS|ml\s*(?:CH4)?\s*/\s*g\s*VS|'
    r'кВт[·⋅* .]?ч|kWh|KZT\s*/\s*(?:кг|kg|kWh|кВт[·⋅* .]?ч|м[³3]|m[³3])|KZT|тенге|тг\b|°\s*C|°\s*С|градус\w*|'
    r'м³|м3|m³|m3|кубометр\w*|кг\s*VS|kg\s*VS|кг\b|kg\b|килограмм\w*|'
    r'литр\w*|lit[er]\w*|L\b|л\b|мл\b|ml\b|день\b|дня\b|дней\b|дн\.?|сутки\b|суток\b|days?\b|күн\b|тәулік\b|%|процент\w*)',re.I)

def unit(value):
    value=value.casefold().replace(' ','')
    if re.match(r'день|дня|дней|дн\.?|сутки|суток|days?$|күн|тәулік',value):return 'day'
    if 'vs' in value and ('мл' in value or 'ml' in value):return 'bmp'
    if value.startswith(('квт','kwh')):return 'energy'
    if value.startswith('kzt/'):return 'money_rate'
    if value in {'kzt','тенге','тг'}:return 'money'
    if value.startswith(('°','градус')):return 'temperature'
    if value.startswith(('м³','м3','m³','m3','кубометр')):
        if any(s in value for s in ['ch4','ch₄','метан','methane']):return 'methane_m3'
        if any(s in value for s in ['биогаз','biogas']):return 'biogas_m3'
        return 'm3'
    if 'vs' in value:return 'kg_vs'
    if value in {'кг','kg'} or value.startswith('килограмм'):return 'kg'
    if value=='%' or value.startswith('процент'):return 'percent'
    if value in {'l','л'} or value.startswith(('литр','lit','lch','лch','lметан','лметан','lбиогаз','лбиогаз','lmethane','лmethane','lbiogas','лbiogas')):
        if any(s in value for s in ['ch4','ch₄','метан','methane']):return 'methane_L'
        if any(s in value for s in ['биогаз','biogas']):return 'biogas_L'
        return 'L'
    if value in {'мл','ml'} or value.startswith(('млch','mlch')):
        return 'methane_ml' if any(s in value for s in ['ch4','ch₄','метан','methane']) else 'ml'
    return value


def user_time_horizons(query):
    """Read only literal durations from this turn, never inherit stale horizons."""
    rows=[]
    for match in re.finditer(r'(?<![\w])('+NUMBER+r')\s*(день\b|дня\b|дней\b|дн\.?|сутки\b|суток\b|days?\b|күн\b|тәулік\b)',query,re.I):
        if re.search(r'\b(?:не|not|вместо)\s*$',query[max(0,match.start()-20):match.start()],re.I):continue
        value=float(match[1].replace(',','.'))
        if math.isfinite(value) and value>0:
            rows.append({'value':value,'unit':'day','origin':'USER_INPUT','role':'question_time_horizon','reference':match.group()})
    return rows


def _horizon_scope_allowed(clause):
    # Mentioning a horizon does not establish a measurement, assay duration,
    # optimal residence time or operating instruction.
    if not re.search(r'(?:\bза|\bчерез|\bк|в\s+течение|\bover|\bwithin|\bafter|\bby)\s+'+NUMBER+r'\s*(?:день|дня|дней|дн|сут|days?)',clause,re.I):return False
    if re.search(r'измерили.{0,45}(?:выход|выработ)|измеренн\w*\s+(?:выход|выработ)|\bmeasured\s+(?:yield|output)',clause,re.I):return False
    if re.search(r'выдержива\w*|держите|установите|оптимальн|\b(?:hold|set|optimal|must)\b',clause,re.I):return False
    if re.search(r'(?:bmp|бмп).{0,35}(?:измеряют|длится|продолжается)|длительност\w*.{0,20}(?:bmp|бмп)',clause,re.I):return False
    for claim in re.finditer(r'гарантир\w*|\bguarantee\w*',clause,re.I):
        if not re.search(r'\b(?:не|not|no|never)\s*$',clause[max(0,claim.start()-12):claim.start()],re.I):return False
    return True


def check(texts,evidence,ids,state=None,diagnostics=None,*,query='',audit=None):
    known=[]
    def add(value,label,origin,role='quantity',reference=None):
        if isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value):
            known.append({'value':value,'unit':unit(label),'origin':origin,'role':role,'reference':reference})
    for key in ids:
        ref=evidence.get(key)
        if not ref:continue
        value=ref['value']
        origin='DERIVED' if ref.get('formula') or (ref.get('result_provenance') or {}).get('method')=='CALCULATED' else 'SCIENTIFIC_SOURCE' if ref.get('level')=='LITERATURE' else 'USER_INPUT' if ref.get('level')=='USER_REPORTED' else 'TOOL_RESULT'
        role='reactor_volume' if key.endswith('.vessel') else 'quantity'
        if isinstance(value,(int,float)):add(value,ref['unit'],origin,role=role,reference=key)
        for bound in ['low','high']:
            if isinstance(value,dict) and isinstance(value.get(bound),(int,float)):
                add(value[bound],ref['unit'],origin,role=role,reference=key)
    if state:
        # Keep every provenance layer. A same-named hypothetical assumption
        # must not be overwritten by the confirmed measurement during mapping.
        for layer in (state.derived,state.assumptions,state.facts):
            for name,fact in layer.items():
                value=fact.value
                if not isinstance(value,(int,float)) or isinstance(value,bool):continue
                label=fact.unit
                if name=='quantity':label=state.value('unit') or label
                if name in {'reactor_total_volume_l','reactor_working_volume_l','material_volume_l','dilution_water_l'}:label='L'
                if name in {'mass_kg','heated_mass_kg'}:label='kg'
                if name=='vs_mass_kg':label='kg VS'
                if name in {'ts_percent','vs_percent'}:label='%'
                if name=='temperature_c':label='°C'
                if name=='reported_methane_volume_m3':label='m3 CH4'
                if name=='reported_biogas_volume_m3':label='m3 biogas'
                if fact.provenance=='UNKNOWN':continue
                origin='DERIVED' if fact.provenance=='CALCULATED_FROM_CONFIRMED' else 'SCIENTIFIC_SOURCE' if fact.provenance=='SOURCE_VERIFIED' else 'USER_INPUT' if fact.provenance=='USER_CONFIRMED' else 'TOOL_RESULT'
                role='reactor_volume' if name in {'reactor_total_volume_l','reactor_working_volume_l'} else 'feedstock_volume' if name in {'material_volume_l','quantity'} and label in {'L','m3'} else 'quantity'
                if label:add(value,label,origin,role=role,reference=name)
                if name in {'methane_fraction','recovery_fraction','electricity_efficiency'}:add(value*100,'percent',origin,reference=name)
        # Component masses/volumes are individually typed user inputs. They
        # are not necessarily projected into the top-level quantity fact.
        for layer_name in ('mixture_components','mixture_scenario_components'):
            for component in getattr(state,layer_name,[]) or []:
                if not isinstance(component,dict):continue
                value=component.get('quantity');label=component.get('unit')
                if isinstance(value,(int,float)) and not isinstance(value,bool) and label:
                    add(value,str(label),'USER_INPUT',role='feedstock_volume' if label in {'L','m3'} else 'quantity',reference=component.get('id'))
    known.extend(user_time_horizons(query))
    volume_scales={'methane_m3':('methane',1000),'methane_L':('methane',1),'methane_ml':('methane',.001),
                   'biogas_m3':('biogas',1000),'biogas_L':('biogas',1),'m3':('volume',1000),'L':('volume',1),'ml':('volume',.001)}
    def supported(value,label,decimals,clause='',role=None):
        for row in known:
            expected=row['value'];kind=row['unit'];factor=1
            if role in {'reactor_volume','feedstock_volume'} and row['role']!=role:continue
            if label!=kind:
                if label=='m3' and kind in {'methane_m3','biogas_m3'}:pass
                elif label in volume_scales and kind in volume_scales and volume_scales[label][0]==volume_scales[kind][0]:
                    factor=volume_scales[kind][1]/volume_scales[label][1];expected*=factor
                else:continue
            if row['role']=='question_time_horizon' and not _horizon_scope_allowed(clause):continue
            if row['origin']=='SCIENTIFIC_SOURCE' and re.search(r'установите|выдержива\w*|\b(?:set|hold)\b|оптимальн|\boptimal\b',clause,re.I) and not re.search(r'не\s+(?:явля\w*|установ\w*|определ\w*)|\bnot\b',clause,re.I):continue
            if row['origin']!='USER_INPUT' and re.search(r'измеренн\w*\s+(?:выход|выработ)|measured\s+(?:yield|output)',clause,re.I) and re.search(r'ваш\w*|\byour\b',clause,re.I):continue
            if abs(value-expected)<=max(1e-8,min(.5*10**-decimals,max(1e-8,abs(expected)*.01))):
                return {**row,'converted_value':expected,'conversion_factor':factor}
        return None
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
            physical_role=None
            left=max([text.rfind(mark,0,token.start()) for mark in '.!?;\n']+[0])
            ends=[p for mark in '.!?;\n' if (p:=text.find(mark,token.end()))>=0]
            clause=text[left:min(ends) if ends else len(text)]
            if label in {'m3','L','ml'}:
                suffix=re.match(r'\s*(CH[4₄]|метан\w*|methane|биогаз\w*|biogas)',text[token.end()+tail.end():],re.I)
                if suffix:label=unit(tail[1]+' '+suffix[1])
                else:
                    feed_suffix=re.match(r'\s*(?:(?:коров\w*|жидк\w*|свин\w*|пищев\w*|cattle|cow|liquid|food)\s+){0,2}(?:навоз\w*|сырь\w*|отход\w*|manure|feedstock|substrate)',text[token.end()+tail.end():],re.I)
                    if feed_suffix:physical_role='feedstock_volume'
                    context=text[left:token.start()]
                    roles=list(re.finditer(r'метан\w*|methane|биогаз\w*|biogas|реактор\w*|ёмкост\w*|емкост\w*|сосуд\w*|сырь\w*|навоз\w*|парт\w*|загрузк\w*|feedstock|substrate|loading|reactor|vessel',context,re.I))
                    if roles and not physical_role:
                        last=roles[-1][0]
                        if re.match(r'метан|methane|биогаз|biogas',last,re.I):label=unit(tail[1]+' '+last)
                        elif re.match(r'реактор|ёмкост|емкост|сосуд|reactor|vessel',last,re.I):
                            gas_mentions=list(re.finditer(r'метан\w*|methane|биогаз\w*|biogas',context,re.I))
                            direct_capacity=re.search(r'(?:объ[её]м|ёмкост\w*|емкост\w*|вместимост\w*|capacity|volume)\s+(?:\w+\s+){0,2}(?:реактор\w*|сосуд\w*|reactor|vessel)|(?:реактор\w*|сосуд\w*|reactor|vessel)\s+(?:объ[её]м\w*|вместимост\w*|capacity|volume)',context,re.I)
                            if gas_mentions and not direct_capacity:label=unit(tail[1]+' '+gas_mentions[-1][0])
                            else:physical_role='reactor_volume'
                        else:physical_role='feedstock_volume'
            if tail and label in {'m3','L','ml','methane_m3','methane_L','methane_ml','biogas_m3','biogas_L'}:
                remainder=text[token.end()+tail.end():]
                remainder=re.sub(r'^\s*(?:CH[₄4]|метан\w*|methane|биогаз\w*|biogas)\b','',remainder,flags=re.I)
                denominator=re.match(r'\s*(?:/|per\b)\s*(л\b|литр\w*|L\b|kg\b|кг\b|g\b|г\b|day\w*|дн\w*|сут\w*|м³|m3)',remainder,re.I)
                if denominator:label=label+'_per_'+unit(denominator[1])
            support=supported(value,label,decimals,clause,physical_role) if tail else None
            if audit is not None:
                audit.append({'value':value,'unit':label,'origin':('DERIVED' if support['conversion_factor']!=1 else support['origin']) if support else 'UNSUPPORTED',
                              'input_origin':support['origin'] if support else None,
                              'role':support['role'] if support else physical_role,'reference':support.get('reference') if support else None,
                              'conversion_factor':support.get('conversion_factor') if support else None,'accepted':support is not None})
            if support is None:
                issues.append('ungrounded_quantity_or_wrong_unit')
                if diagnostics is not None:diagnostics.append({'rejected_value':value,'unit':label,'origin':'UNSUPPORTED','allowed_typed_values':known})
        for amount in amounts(text):
            support=supported(amount['value'],unit(amount['unit']),0,text)
            if audit is not None:
                audit.append({'value':amount['value'],'unit':unit(amount['unit']),'origin':('DERIVED' if support['conversion_factor']!=1 else support['origin']) if support else 'UNSUPPORTED',
                              'input_origin':support['origin'] if support else None,
                              'role':support['role'] if support else None,'reference':support.get('reference') if support else None,
                              'conversion_factor':support.get('conversion_factor') if support else None,'accepted':support is not None})
            if support is None:issues.append('ungrounded_quantity_or_wrong_unit')
    return list(dict.fromkeys(issues))
