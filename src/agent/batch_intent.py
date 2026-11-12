"""Distinguish starting a batch from referring to an already active batch."""
import re


MARKER = re.compile(r'нов\w*\s+парт\w*|друг\w*\s+парт\w*|\bначина\w*\s+(?:(?:нов\w*|друг\w*|следующ\w*)\s+)?парт\w*|new\s+batch|start\s+over|жаңа\s+парт\w*', re.I)
ANAPHORA = re.compile(r'\b(?:этой|этого|этом|этот|эту|this|that)\s+(?:(?:же|same)\s+)?$', re.I)


def starts_new_batch(text):
    """Return true for a batch transition, not a reference like “this same new batch”."""
    for marker in MARKER.finditer(text):
        prefix = text[max(0, marker.start() - 48):marker.start()]
        if ANAPHORA.search(prefix):
            continue
        return True
    return False


def _format_number(value,language):
    text=f'{float(value):.6g}'
    return text.replace('.',',') if language in {'ru','kk'} else text


def confirmation(state):
    """Render a short factual confirmation for a typed new-batch transition."""
    from src.agent.dialogue_response import NAMES

    language=state.language
    material=state.value('material')
    material_name=NAMES.get(material,(str(material or ''),)*3)[['ru','en','kk'].index(language)] if material else None
    quantity_fact=state.facts.get('quantity') or state.assumptions.get('quantity')
    unit_fact=state.facts.get('unit') or state.assumptions.get('unit')
    quantity=quantity_fact.value if quantity_fact else None
    unit=unit_fact.value if unit_fact else None
    vessel=state.value('reactor_total_volume_l') or state.value('reactor_working_volume_l')

    ru=[];en=[];kk=[]
    if material_name:
        ru.append(material_name);en.append(material_name);kk.append(material_name)
    if quantity is not None and unit:
        units={'kg':'кг','g':'г','t':'т','L':'л','m3':'м³'}
        en_units={'kg':'kg','g':'g','t':'t','L':'L','m3':'m³'}
        qualifier=quantity_fact.provenance=='ASSUMED_FOR_SCENARIO'
        is_volume=unit in {'L','m3'}
        ru_label=('условный объём сырья ' if qualifier else 'объём сырья ') if is_volume else ('условная масса ' if qualifier else 'масса ')
        en_label=('hypothetical feedstock volume ' if qualifier else 'feedstock volume ') if is_volume else ('hypothetical mass ' if qualifier else 'mass ')
        kk_label=('шартты шикізат көлемі ' if qualifier else 'шикізат көлемі ') if is_volume else ('шартты масса ' if qualifier else 'массасы ')
        ru.append(ru_label+_format_number(quantity,language)+' '+units.get(unit,unit))
        en.append(en_label+_format_number(quantity,language)+' '+en_units.get(unit,unit))
        kk.append(kk_label+_format_number(quantity,language)+' '+units.get(unit,unit))
    if vessel is not None:
        ru.append('ёмкость сосуда '+_format_number(vessel,language)+' л')
        en.append('vessel capacity '+_format_number(vessel,language)+' L')
        kk.append('ыдыс сыйымдылығы '+_format_number(vessel,language)+' л')
    if not any([material_name,quantity is not None,vessel is not None]):return None

    separated=bool(state.task_history)
    if language=='en':
        prefix='New batch saved separately from the previous batch: ' if separated else 'New batch recorded: '
        return prefix+'; '.join(en)+'.'
    if language=='kk':
        prefix='Жаңа партия алдыңғы партиядан бөлек сақталды: ' if separated else 'Жаңа партия тіркелді: '
        return prefix+'; '.join(kk)+'.'
    prefix='Новая партия сохранена отдельно от предыдущей: ' if separated else 'Новая партия зафиксирована: '
    return prefix+'; '.join(ru)+'.'


def covers_confirmation(answer,state):
    """Check whether the reply visibly confirms the new batch's typed identity."""
    from src.agent.dialogue_response import NAMES

    language=state.language
    material=state.value('material')
    if material:
        name=NAMES.get(material,(str(material),)*3)[['ru','en','kk'].index(language)]
        noun=name.casefold().split()[-1]
        if noun not in answer.casefold():return False
    quantity=state.facts.get('quantity') or state.assumptions.get('quantity')
    unit=state.facts.get('unit') or state.assumptions.get('unit')
    if quantity and unit:
        units={'ru':{'kg':'кг','g':'г','t':'т','L':'л','m3':'м³'},
               'kk':{'kg':'кг','g':'г','t':'т','L':'л','m3':'м³'},
               'en':{'kg':'kg','g':'g','t':'t','L':'L','m3':'m³'}}
        token=_format_number(quantity.value,language)+' '+units[language].get(unit.value,unit.value)
        if token.casefold() not in answer.casefold():return False
    vessel=state.value('reactor_total_volume_l') or state.value('reactor_working_volume_l')
    if vessel is not None:
        unit_label='L' if language=='en' else 'л'
        if (_format_number(vessel,language)+' '+unit_label).casefold() not in answer.casefold():return False
    if state.task_history:
        separated={'ru':'отдельно','en':'separately','kk':'бөлек'}[language]
        if separated not in answer.casefold():return False
    return True
