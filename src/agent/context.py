"""Only explicit user facts enter tools. LLM-generated numeric arguments are forbidden."""
import json
import re
from src.economics.calculator import ECONOMIC_FIELDS, number
from src.data.prepare import NUMERIC
from src.recommendations.knowledge import detect_material, normalize_material

NUMBERS=set(ECONOMIC_FIELDS)-{'currency','price_date','gas_volume_basis','price_gas_volume_basis'} | set(NUMERIC) | {
    'bmp_ml_ch4_g_vs','vs_mass_kg','material_volume_l','dilution_water_l','reactor_volume_l','density_kg_l','temperature_c'}
TEXT={'material','substrate','currency','price_date','gas_volume_basis','price_gas_volume_basis','bmp_unit','model'}
TEXT.update({'market_region','market_commodity','market_start','market_end'})
EXPECTED_UNITS={'mass_kg':'kg','vs_mass_kg':'kg VS','material_volume_l':'L','reactor_volume_l':'L',
    'density_kg_l':'kg/L','bmp_ml_ch4_g_vs':'mL CH4/g VS','c_vs_sub_m':'g/g','c_vs_sub_f':'g/g',
    'c_vs_inoc':'g/g','ISR':'g VS/g VS','potential_methane_m3':'m3 CH4','temperature_c':'degC'}


def validate_context(data):
    if not isinstance(data,dict):
        raise ValueError('Контекст должен быть JSON-объектом')
    unknown=set(data)-NUMBERS-TEXT-{'units','market_scenario'}
    if unknown:
        raise ValueError('Неизвестные поля контекста: '+', '.join(sorted(unknown)))
    out=dict(data)
    if 'market_scenario' in out:
        from src.market.scenarios import ScenarioInput
        out['market_scenario']=ScenarioInput.model_validate(out['market_scenario']).model_dump(exclude_unset=True,mode='json')
    from datetime import date
    for field in ['market_start','market_end']:
        if field in out:date.fromisoformat(out[field])
    if out.get('market_start','')>out.get('market_end','9999-12-31'):raise ValueError('market_start must not exceed market_end')
    for key in set(out)&NUMBERS:
        if key=='temperature_c':
            number(out[key],key,minimum=-273.15,strict=True)
        else:
            number(out[key],key,strict=key in {'mass_kg','vs_mass_kg','material_volume_l','reactor_volume_l','density_kg_l','ISR'})
        if key in {'c_vs_sub_m','c_vs_sub_f','c_vs_inoc','recovery_fraction'} and out[key]>1:
            raise ValueError(f'{key}: требуется доля в [0,1], не проценты')
    for key in set(out)&TEXT:
        if not isinstance(out[key],str) or not out[key].strip():
            raise ValueError(f'{key}: требуется непустая строка')
    for key in ['material','substrate']:
        if key in out:
            out[key]=normalize_material(out[key])
    if 'material' in out and 'substrate' in out and out['material']!=out['substrate']:
        raise ValueError('material и substrate противоречат друг другу')
    if 'substrate' in out:
        out['material']=out.pop('substrate')
    units=out.get('units',{})
    if not isinstance(units,dict) or any(EXPECTED_UNITS.get(k)!=v for k,v in units.items()):
        raise ValueError('Некорректные единицы. Допустимые: '+json.dumps(EXPECTED_UNITS,ensure_ascii=False))
    if out.get('bmp_unit','mL CH4/g VS')!='mL CH4/g VS':
        raise ValueError('bmp_unit: поддерживается только mL CH4/g VS')
    if out.get('model','stage1_5') not in {'stage1','stage1_5'}:
        raise ValueError('model должен быть stage1 или stage1_5')
    if out.get('vs_mass_kg',0)>out.get('mass_kg',float('inf')):
        raise ValueError('Масса VS не может превышать влажную массу')
    return out


def extract_explicit(text):
    """Restricted fallback parser. Unsupported prose is asked for, never guessed."""
    if not isinstance(text,str) or len(text)>12000:
        raise ValueError('Введите текст длиной до 12000 символов')
    stripped=text.strip()
    if stripped.startswith('{'):
        return validate_context(json.loads(stripped))
    values={}
    from src.agent.geography import resolve_region
    material=detect_material(text)
    if material:
        values['material']=material
    region=resolve_region(text)
    if region:values['market_region']=region
    for pattern,commodity in [(r'электроэнерг','electricity'),(r'природн\w*\s+газ','natural_gas'),(r'биогаз','raw_biogas'),(r'карбамид','urea'),(r'аммофос','ammophos'),(r'дигестат','digestate')]:
        if re.search(pattern,text,re.I):values['market_commodity']=commodity;break
    for match in re.finditer(r'\b([A-Za-z_][A-Za-z_0-9]*)\s*=\s*("[^"\n]*"|\'[^\'\n]*\'|[^\s;]+)',text):
        key,raw=match.groups()
        if key not in NUMBERS|TEXT:
            continue
        raw=raw.strip('"\'').rstrip(';')
        if key in NUMBERS:
            try:
                value=float(raw.replace(',','.'))
            except ValueError:
                raise ValueError(f'{key}: укажите число без суффикса единиц; единицы заданы именем поля') from None
        else:
            value=raw
        if key in values and values[key]!=value:
            raise ValueError(f'Противоречивые значения поля {key}')
        values[key]=value
    for match in re.finditer(r'(?<![\w.])(-?\d+(?:[.,]\d+)?)\s*(?:литр\w*|л\b|[lL]\b)',text,re.I):
        before=text[max(0,match.start()-35):match.start()].casefold()
        after=text[match.end():match.end()+25].casefold()
        key='reactor_volume_l' if re.search(r'реактор|reactor',before) or re.search(r'^\s*(?:реактор|reactor)',after) else 'material_volume_l'
        val=float(match.group(1).replace(',','.'))
        if key in values and values[key]!=val:
            raise ValueError(f'Неоднозначный объём {key}: задайте поле явно')
        values[key]=val
    match=re.search(r'(?<![\w.])(-?\d+(?:[.,]\d+)?)\s*(?:кг|kg)\b',text,re.I)
    if match and 'mass_kg' not in values:
        # Explicit labelled kg fields are handled above; do not reinterpret VS mass.
        before=text[max(0,match.start()-20):match.start()]
        if not re.search(r'vs|летуч|VS',before):
            values['mass_kg']=float(match.group(1).replace(',','.'))
    return validate_context(values)


def merge_context(previous, additions):
    # New material means a new batch; no old composition or prices carry over.
    reset='material' in additions and previous.get('material') not in (None,additions['material'])
    merged=({'model':previous['model']} if 'model' in previous else {}) if reset else dict(previous)
    merged.update(additions)
    merged=validate_context(merged)
    return merged,reset
