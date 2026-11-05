from typing import Literal
from pydantic import Field,model_validator,field_validator
from src.optimizer.schemas import Strict
from src.economics.decision_schemas import Range,GasBasis,DecisionInputs

class Properties(Strict):
    density_kg_l:Range|None=None
    ts_fraction:Range|None=None
    vs_fraction_wet:Range|None=None
    vs_fraction_of_ts:Range|None=None
    bmp_ml_g_vs:Range|None=None
    carbon_fraction_wet:Range|None=None
    nitrogen_fraction_wet:Range|None=None
    gas_basis:GasBasis|None=None
    @model_validator(mode='before')
    @classmethod
    def point_values(cls,values):
        if isinstance(values,dict):
            values=dict(values)
            for k,v in values.items():
                if k!='gas_basis' and isinstance(v,(int,float)) and not isinstance(v,bool):values[k]={'low':v,'high':v,'provenance':'USER_REPORTED','evidence':'Explicit component property'}
        return values
    @model_validator(mode='after')
    def valid(self):
        for k in ['ts_fraction','vs_fraction_wet','vs_fraction_of_ts','carbon_fraction_wet','nitrogen_fraction_wet']:
            v=getattr(self,k)
            if v and v.high>1:raise ValueError(k+' must be a mass fraction in 0..1')
        if self.density_kg_l and self.density_kg_l.low<=0:raise ValueError('Density must be positive')
        if self.vs_fraction_wet and self.ts_fraction and self.vs_fraction_wet.high>self.ts_fraction.high:raise ValueError('VS cannot exceed TS')
        return self

class Component(Strict):
    id:str=Field(min_length=1,max_length=80)
    material:str=Field(min_length=1,max_length=80)
    material_state:str=Field(default='unknown',max_length=80)
    quantity:float=Field(gt=0,le=1e9)
    unit:Literal['kg','g','t','mL','L','m3']='kg'
    animal:Literal['unknown','cattle','pig','poultry','horse','sheep','goat']='unknown'
    poultry_type:Literal['unknown','chicken','broiler','layer','turkey']='unknown'
    reference_profile_id:str|None=Field(default=None,max_length=100)
    physical_state:Literal['unknown','liquid','semiliquid','solid','dry','bedded']='unknown'
    decay_state:Literal['unknown','fresh','stored','rotted','composted']='unknown'
    bedding:Literal['unknown','none','straw','sawdust','shavings','other']='unknown'
    data_mode:Literal['MEASURED','LITERATURE_ESTIMATE','ILLUSTRATIVE_ASSUMPTION']='LITERATURE_ESTIMATE'
    properties:Properties=Field(default_factory=Properties)
    provenance:Literal['USER_CONFIRMED','ASSUMED_FOR_SCENARIO']='USER_CONFIRMED'
    evidence:str=Field(default='',max_length=1500)

    @model_validator(mode='after')
    def axes(self):
        from src.advisor.material_axes import normalize
        normalize(self)
        from src.advisor.catalog import normalized,choose
        self.material=normalized(self.material)
        if self.animal!='poultry' and self.poultry_type!='unknown':raise ValueError('Poultry subtype requires poultry manure')
        if self.reference_profile_id:choose(self,True)
        return self

class AdvisorRequest(Strict):
    components:list[Component]=Field(min_length=1,max_length=20)
    allow_literature_transfer:bool=True
    allow_conditional_profiles:bool=False
    target_ts_fraction:float|None=Field(default=None,gt=0,le=1)
    assume_common_dry_gas_basis:bool=False
    assume_unreported_gas_basis:bool=False
    reactor_total_volume_l:float|None=Field(default=None,gt=0)
    decision:DecisionInputs=Field(default_factory=DecisionInputs)
    feeding_period_days:float|None=Field(default=None,gt=0)
    total_daily_liquid_feed_l:float|None=Field(default=None,gt=0)
    daily_feed_includes_all_liquid:bool=False
    inoculum_description:str|None=Field(default=None,max_length=1000)
    inoculum_adapted_temperature_c:float|None=Field(default=None,gt=-273.15)
    temperature_control_confirmed:bool=False
    mixing_available:bool|None=None
    measured_ph:float|None=Field(default=None,ge=0,le=14)
    monitoring_confirmed:bool=False
    inhibition_warning:bool=False
    region:str=Field(default='KZ-Karaganda',max_length=100)
    region_confirmed:bool=False
    online:bool=False
    objectives:list[Literal['methane','energy','duration','profit','stability']]=Field(default_factory=lambda:['methane','stability'],max_length=5)
    @model_validator(mode='after')
    def unique(self):
        if len({c.id for c in self.components})!=len(self.components):raise ValueError('Component IDs must be unique')
        return self

class Candidate(Strict):
    label:str=Field(min_length=1,max_length=150)
    components:list[Component]=Field(min_length=1,max_length=20)

class MixtureSave(Strict):
    name:str=Field(min_length=1,max_length=160)
    request:AdvisorRequest
    mixture_id:str|None=Field(default=None,max_length=80)
    display_units:dict[str,Literal['kg','g','t','mL','L','m3']]=Field(default_factory=dict)
    @model_validator(mode='after')
    def valid(self):
        self.name=self.name.strip()
        if not self.name:raise ValueError('Mixture name is empty')
        if set(self.display_units)-{c.id for c in self.request.components}:raise ValueError('Display units refer to an absent component')
        return self

class MixtureHandoff(Strict):
    request:AdvisorRequest
    mode:Literal['offline','no_llm']='offline'

class ConversionRequest(Strict):
    request:AdvisorRequest
    target_unit:Literal['kg','g','t','mL','L','m3']='kg'

class ComparisonRequest(Strict):
    base:AdvisorRequest
    candidates:list[Candidate]=Field(min_length=1,max_length=8)
    @model_validator(mode='after')
    def no_overuse(self):
        # Availability is checked in normalized mass/volume within each unit family.
        from src.advisor.mixing import normalize_inventory
        available=normalize_inventory(self.base.components)
        originals={c.id:c for c in self.base.components}
        for candidate in self.candidates:
            used=normalize_inventory(candidate.components)
            if any(k not in available or v>available[k]+1e-9 for k,v in used.items()):raise ValueError('Candidate exceeds available component inventory or changes material state')
            if any(c.properties!=originals[c.id].properties for c in candidate.components):raise ValueError('Comparison must preserve component property evidence; define a separate explicit input scenario to change properties')
        return self
