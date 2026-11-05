"""Backend-owned UI vocabulary and explicit scope/capability metadata."""
from src.advisor.material_axes import ANIMALS
STATES=[('unknown','unknown','Не уточнено'),('slurry','liquid','Жидкий'),('semiliquid','semiliquid','Полужидкий'),('fresh_solid','solid','Твёрдый'),('dry','dry','Сухой'),('bedded','bedded','С подстилкой'),('prepared_pulp','unknown','Подготовленная пульпа'),('shredded','unknown','Измельчённый'),('silage','unknown','Силос'),('compost','unknown','Компост')]
ANIMAL_NAMES={'unknown':'Не уточнён','cattle':'КРС','pig':'Свиньи','poultry':'Птица','horse':'Лошади','sheep':'Овцы','goat':'Козы'}
def ui():
    return {'units':[{'value':v,'label':label} for v,label in [('g','г'),('kg','кг'),('t','т'),('mL','мл'),('L','л'),('m3','м³')]],
      'animals':[{'value':a,'label':label,'material':'manure' if a=='unknown' else ANIMALS[a]} for a,label in ANIMAL_NAMES.items()],
      'decay_states':[{'value':v,'label':s} for v,s in [('unknown','Не уточнена'),('fresh','Свежий'),('stored','Хранившийся'),('rotted','Перепревший'),('composted','Компостированный')]],
      'beddings':[{'value':v,'label':s} for v,s in [('unknown','Не уточнена'),('none','Без подстилки'),('straw','Солома'),('sawdust','Опилки'),('shavings','Стружка'),('other','Другая')]],
      'poultry_types':[{'value':v,'label':s} for v,s in [('unknown','Тип не уточнён'),('chicken','Куриный · тип не уточнён'),('broiler','Бройлеры'),('layer','Несушки'),('turkey','Индейки')]],
      'data_modes':[{'value':v,'label':s} for v,s in [('LITERATURE_ESTIMATE','Приблизительные · по источникам'),('MEASURED','Только измеренные'),('ILLUSTRATIVE_ASSUMPTION','Явно условный сценарий')]]}

def describe(material,profiles):
    manure=material=='manure' or material.endswith('_manure')
    from src.advisor.catalog import DEFINITIONS
    states=next(d[-2] for d in DEFINITIONS if d[0]==material)
    allowed=['unknown','slurry','semiliquid','fresh_solid','dry','bedded'] if manure else list(dict.fromkeys(['unknown',*states]))
    return {'form_states':[{'value':v,'physical_state':phys,'label':label} for v,phys,label in STATES if v in allowed],
      'is_manure':manure,'has_numerical_profile':bool(profiles),'support_level':'NUMERICAL_REFERENCE_SCOPED' if profiles else 'PARTIAL',
      'support_notice':'Численные профили относятся к конкретным состояниям и образцам; проверьте область переноса.' if profiles else 'Частичная поддержка: материал распознаётся; для полного выхода нужны измеренные свойства или подходящий профиль.',
      'available_reference_states':list(dict.fromkeys(s for p in profiles for s in p.get('matching_states',[p['material_state']])))}
