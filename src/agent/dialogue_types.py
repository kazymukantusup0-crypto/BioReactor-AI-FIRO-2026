"""Typed dialogue facts; suggested/assumed values never become confirmed inputs."""
from typing import Literal
import math
from pydantic import BaseModel,ConfigDict,Field,model_validator

Provenance=Literal['USER_CONFIRMED','SOURCE_VERIFIED','MODEL_ESTIMATED','ASSUMED_FOR_SCENARIO','UNKNOWN','CALCULATED_FROM_CONFIRMED']
Intent=Literal['economic_comparison','temperature_recommendation','methane_yield','process_guidance','model_info','market_prices','price_history','reactor_status','sources','general','greeting']
Language=Literal['ru','kk','en']


class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)


class Entity(Strict):
    name:str
    value:float|str|bool|dict
    unit:str|None=None
    evidence:str=Field(max_length=12000)
    provenance:Provenance='USER_CONFIRMED'

    @model_validator(mode='after')
    def measured_ranges(self):
        choices={'unit':{'L','m3','kg','t','g'},'vs_basis':{'TS','fresh_mass'},'sale_offer_scope':{'batch','kg','L','t'},'operating_mode':{'batch','continuous'}}
        if self.name in choices and self.value not in choices[self.name]:raise ValueError(f'Invalid {self.name}')
        positive={'quantity','mass_kg','material_volume_l','density_kg_l','vs_mass_kg','reactor_total_volume_l','reactor_working_volume_l','reactor_volume_l','ISR'}
        nonnegative={'dilution_water_l','auxiliary_energy_kwh'}
        fractions={'recovery_fraction','methane_fraction','electricity_efficiency','c_vs_sub_m','c_vs_sub_f','c_vs_inoc'}
        if self.name in positive|fractions|nonnegative|{'temperature_c','ts_percent','vs_percent','sale_offer_amount'}:
            if isinstance(self.value,bool) or not isinstance(self.value,(int,float)) or not math.isfinite(self.value):raise ValueError(f'{self.name}: finite numeric value required')
            if self.name in positive and self.value<=0:raise ValueError(f'{self.name}: positive value required')
            if self.name in nonnegative and self.value<0:raise ValueError(f'{self.name}: nonnegative value required')
            if self.name in fractions and not 0<=self.value<=1:raise ValueError(f'{self.name}: fraction must be in [0,1]')
            if self.name in {'ts_percent','vs_percent'} and not 0<=self.value<=100:raise ValueError('TS/VS percentage must be in [0,100]')
            if self.name=='temperature_c' and self.value<=-273.15:raise ValueError('Temperature below absolute zero')
            if self.name=='sale_offer_amount' and self.value<0:raise ValueError('Negative sale offer')
        return self


class Extraction(Strict):
    language:Language='ru'
    intents:list[Intent]=Field(default_factory=list)
    entities:list[Entity]=Field(default_factory=list)
    correction:bool=False
    new_batch:bool=False
    validation_errors:list[str]=Field(default_factory=list)


class Fact(Strict):
    value:float|str|bool|dict|None
    unit:str|None=None
    provenance:Provenance
    evidence:str=''
    recorded_at:str
    dependencies:list[str]=Field(default_factory=list)


class Question(Strict):
    id:str
    text:str
    options:list[str]=Field(default_factory=list)
    fields:list[str]=Field(default_factory=list)
    reason:str=''


class DialogueState(Strict):
    version:str='5.6'
    task_id:str|None=None
    task_history:list[dict]=Field(default_factory=list)
    conversation_id:str|None=None
    language:Language='ru'
    facts:dict[str,Fact]=Field(default_factory=dict)
    assumptions:dict[str,Fact]=Field(default_factory=dict)
    derived:dict[str,Fact]=Field(default_factory=dict)
    estimates:dict[str,Fact]=Field(default_factory=dict)
    source_verified:dict[str,Fact]=Field(default_factory=dict)
    intents:list[Intent]=Field(default_factory=list)
    pending_question:Question|None=None
    invalidated:list[str]=Field(default_factory=list)
    decision_settings:dict=Field(default_factory=dict)
    decision_unavailable:list[str]=Field(default_factory=list)
    last_research_summary:dict=Field(default_factory=dict)
    mixture_components:list[dict]=Field(default_factory=list)
    mixture_scenario_components:list[dict]=Field(default_factory=list)
    mixture_revision:int=0
    mixture_history:list[dict]=Field(default_factory=list)
    advisor_inventory_mode:str='none'
    advisor_pending_component:str|None=None
    advisor_settings:dict=Field(default_factory=dict)
    smart_goals:list[str]=Field(default_factory=list)
    smart_cache:dict=Field(default_factory=dict)
    active_mixture_scenario:bool=False
    advanced:dict=Field(default_factory=dict)
    analytical_mode:Literal['mixture','alternatives']='mixture'

    def value(self,name,default=None):
        entry=self.facts.get(name) or self.derived.get(name)
        return entry.value if entry else default

    def brief(self):
        relevant={'material','quantity','unit','material_state','physical_state','decay_state','reactor_total_volume_l','reactor_working_volume_l','operating_mode','market_region'}
        return {'language':self.language,'facts':{k:str(f.value)[:60] for k,f in self.facts.items() if k in relevant},'active_goals':self.smart_goals,
            'pending_question':self.pending_question.id if self.pending_question else None,'intents':self.intents,
            'mixture_inventory':[{'id':c['id'],'material':c['material'],'quantity':c['quantity'],'unit':c['unit']} for c in self.mixture_components[:8]]}


class ProposedEntity(Strict):
    name:str=Field(max_length=60)
    text:str=Field(min_length=1,max_length=200)


class NLUProposal(Strict):
    language:Language
    intents:list[Intent]=Field(max_length=4)
    material:str|None
    material_evidence:str|None
    entities:list[ProposedEntity]=Field(max_length=8)
