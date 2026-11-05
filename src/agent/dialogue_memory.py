"""Structured facts with provenance and dependency invalidation."""
from src.agent.dialogue_types import DialogueState,Entity,Extraction,Fact
from src.agent.context import validate_context,NUMBERS,TEXT
from src.market.domain import utcnow

MATERIAL_DEPENDENT={'mass_kg','material_volume_l','density_kg_l','ts_percent','vs_percent','vs_basis','vs_mass_kg','bmp_ml_ch4_g_vs','bmp_unit','gas_volume_basis','potential_methane_m3',
    'c_vs_sub_m','c_vs_sub_f','c_vs_inoc','ISR','sale_offer_amount','sale_offer_scope','sale_offer_currency','market_scenario',
    'heated_mass_kg','heat_capacity_kj_kg_k','dilution_water_l','bmp_evidence','bmp_provenance','liquid_charge_volume_l','inoculum_description',
    'pretreatment','mixture_components','market','inoculum_volume_l','dilution_water_l','resident_liquid_volume_l','material_state','physical_state','decay_state'}


def fact(value,unit=None,provenance='USER_CONFIRMED',evidence='',dependencies=None):
    return Fact(value=value,unit=unit,provenance=provenance,evidence=evidence,recorded_at=utcnow().isoformat(),dependencies=dependencies or [])


def from_context(context=None,conversation_id=None):
    state=DialogueState(conversation_id=conversation_id)
    for key,value in validate_context(context or {}).items():
        if key=='units':continue
        name='reactor_total_volume_l' if key=='reactor_volume_l' else key
        state.facts[name]=fact('manure' if value=='manure_unspecified' else value,evidence='Explicit validated context from the existing session/API')
    if state.value('mass_kg') is not None:
        state.facts['quantity']=fact(state.value('mass_kg'),'kg',evidence='Explicit mass_kg');state.facts['unit']=fact('kg',evidence='Explicit mass_kg unit')
    elif state.value('material_volume_l') is not None:
        state.facts['quantity']=fact(state.value('material_volume_l'),'L',evidence='Explicit material_volume_l');state.facts['unit']=fact('L',evidence='Explicit volume unit')
    return state


def apply(state,extraction,tolerate_engineering_conflicts=False):
    state=state.model_copy(deep=True);state.invalidated=[];state.language=extraction.language
    supplied={e.name for e in extraction.entities if e.provenance=='USER_CONFIRMED'}
    material=next((e.value for e in extraction.entities if e.name=='material'),None)
    old=state.value('material')
    change=material is not None and old is not None and old!=material
    refinement=old=='manure' and material in {'cattle_manure','swine_manure','poultry_manure'}
    if extraction.new_batch or change:
        # Refining generic manure keeps quantity; species correction cannot keep
        # the previous species' density, laboratory data, offer or output.
        for name in list(state.facts):
            if (extraction.new_batch or not refinement) and name in MATERIAL_DEPENDENT and name not in supplied:
                state.invalidated.append(name);del state.facts[name]
        if extraction.new_batch or 'quantity' in supplied:
            for key in ['quantity','unit','mass_kg','material_volume_l']:
                if key not in supplied:state.facts.pop(key,None)
        state.invalidated+=list(state.estimates);state.estimates={};state.assumptions={}
    if supplied & {'quantity','unit','mass_kg','density_kg_l','ts_percent','vs_percent','vs_basis','vs_mass_kg','bmp_ml_ch4_g_vs'}:
        state.invalidated+=list(state.estimates);state.estimates={}
    if supplied & {'material_state','physical_state','decay_state'}:
        state.invalidated+=list(state.estimates);state.estimates={}
        form_changed=any(e.name in {'material_state','physical_state','decay_state'} and state.value(e.name) is not None and state.value(e.name)!=e.value for e in extraction.entities)
        if form_changed:
            for key in ['density_kg_l','ts_percent','vs_percent','vs_basis','vs_mass_kg','bmp_ml_ch4_g_vs','c_vs_sub_m','c_vs_sub_f']:
                if key not in supplied and key in state.facts:state.invalidated.append(key);state.facts.pop(key)
    previous_quantity=(state.value('quantity'),state.value('unit'))
    previous_temperature=state.value('temperature_c')
    for entity in extraction.entities:
        target=state.assumptions if entity.provenance=='ASSUMED_FOR_SCENARIO' else state.facts
        target[entity.name]=fact(entity.value,entity.unit,entity.provenance,entity.evidence)
        if entity.provenance=='USER_CONFIRMED':state.assumptions.pop(entity.name,None)
    if previous_temperature is not None and state.value('temperature_c')!=previous_temperature:
        for name in ['heating_cost','energy_use_kwh','market_scenario']:
            if name not in supplied and name in state.facts:state.invalidated.append(name);del state.facts[name]
    if (state.value('quantity'),state.value('unit'))!=previous_quantity:
        # A new quantity invalidates an offer for the previous entire batch.
        for key in ['mass_kg','material_volume_l','sale_offer_amount','sale_offer_scope','sale_offer_currency']:
            if key not in supplied and key in state.facts:
                state.invalidated.append(key);del state.facts[key]
    state.derived={}
    def derived(name,value,unit,dependencies):
        state.derived[name]=fact(value,unit,'CALCULATED_FROM_CONFIRMED','Unit arithmetic from explicit confirmed inputs',dependencies)
    quantity=state.value('quantity');unit=state.value('unit')
    if quantity is not None:
        if unit in {'kg','t','g'}:
            converted=quantity*{'kg':1,'t':1000,'g':.001}[unit]
            if 'mass_kg' in state.facts and state.facts['mass_kg'].value!=converted:raise ValueError('Conflicting wet mass and batch quantity')
            derived('mass_kg',converted,'kg',['quantity','unit'])
        elif unit in {'L','m3'}:derived('material_volume_l',quantity*(1000 if unit=='m3' else 1),'L',['quantity','unit'])
        else:raise ValueError('Quantity unit must be L, m3, kg, t or g')
    volume=state.value('material_volume_l');density=state.value('density_kg_l')
    if state.value('mass_kg') is None and volume is not None and density is not None:
        derived('mass_kg',volume*density,'kg',['material_volume_l','density_kg_l'])
    mass=state.value('mass_kg');ts=state.value('ts_percent');vs=state.value('vs_percent');basis=state.value('vs_basis')
    if state.value('vs_mass_kg') is None and mass is not None and vs is not None:
        if basis=='fresh_mass':derived('vs_mass_kg',mass*vs/100,'kg VS',['mass_kg','vs_percent','vs_basis'])
        elif basis=='TS' and ts is not None:derived('vs_mass_kg',mass*ts/100*vs/100,'kg VS',['mass_kg','ts_percent','vs_percent','vs_basis'])
    if state.value('vs_mass_kg') is not None and mass is not None and state.value('vs_mass_kg')>mass:raise ValueError('VS mass cannot exceed wet mass')
    if state.value('reactor_working_volume_l') is not None and state.value('reactor_total_volume_l') is not None and state.value('reactor_working_volume_l')>state.value('reactor_total_volume_l'):
        if not tolerate_engineering_conflicts:raise ValueError('Working volume cannot exceed total reactor volume')
        state.advanced['input_conflicts']=[{'reason':'working_volume_exceeds_total',
            'reported_working_volume_l':state.value('reactor_working_volume_l'),'reported_total_volume_l':state.value('reactor_total_volume_l'),
            'scope':'Retained as contradictory user reports for engineering review; not validated capacity.'}]
    else:state.advanced.pop('input_conflicts',None)
    if extraction.intents:state.intents=extraction.intents
    # A one-word subtype or price-scope reply continues the active user goal.
    return state


def tool_context(state):
    allowed=NUMBERS|TEXT|{'market_scenario'}
    output={key:entry.value for key,entry in {**state.derived,**state.facts}.items() if key in allowed}
    if state.value('material')=='manure':output['material']='manure_unspecified'
    if state.value('reactor_total_volume_l') is not None:output['reactor_volume_l']=state.value('reactor_total_volume_l')
    if state.value('market_region') is None:
        preferred=state.assumptions.get('market_region')
        output['market_region']=preferred.value if preferred else 'KZ-Karaganda'
        if preferred is None:state.assumptions['market_region']=fact('KZ-Karaganda',provenance='ASSUMED_FOR_SCENARIO',evidence='Default dashboard region; not user-confirmed')
    return validate_context(output)
