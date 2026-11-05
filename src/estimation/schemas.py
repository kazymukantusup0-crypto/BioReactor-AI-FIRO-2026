from typing import Literal
from pydantic import BaseModel,ConfigDict,Field,model_validator
from src.economics.decision_schemas import DecisionInputs

class EstimateRequest(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
    material:str=Field(default='cattle_manure',min_length=1,max_length=60)
    material_state:Literal['unknown','slurry','fresh_solid','bedded','dry','compost']='unknown'
    volume_l:float|None=Field(default=None,gt=0,le=1e9)
    mass_kg:float|None=Field(default=None,gt=0,le=1e12)
    density_kg_l:float|None=Field(default=None,gt=0,le=10)
    ts_fraction:float|None=Field(default=None,gt=0,le=1)
    vs_fraction_of_ts:float|None=Field(default=None,gt=0,le=1)
    vs_fraction_wet:float|None=Field(default=None,gt=0,le=1)
    vs_mass_kg:float|None=Field(default=None,gt=0)
    bmp_ml_g_vs:float|None=Field(default=None,gt=0)
    gas_reference:str|None=Field(default=None,max_length=300)
    methane_fraction:float|None=Field(default=None,gt=0,le=1)
    reactor_total_volume_l:float|None=Field(default=None,gt=0)
    region:str=Field(default='KZ-Karaganda',max_length=100)
    region_confirmed:bool=False
    online:bool=False
    economic_inputs:dict|None=None
    decision:DecisionInputs|None=None

    @model_validator(mode='before')
    @classmethod
    def no_boolean_quantities(cls,values):
        if isinstance(values,dict):
            from typing import get_args
            for key,value in values.items():
                field=cls.model_fields.get(key)
                if field and isinstance(value,bool) and float in get_args(field.annotation):raise ValueError(key+': numeric value required, not boolean')
        return values

    @model_validator(mode='after')
    def consistent(self):
        if self.mass_kg and self.vs_mass_kg and self.vs_mass_kg>self.mass_kg:raise ValueError('VS exceeds wet mass')
        if self.ts_fraction and self.vs_fraction_wet and self.vs_fraction_wet>self.ts_fraction:raise ValueError('VS exceeds TS')
        if self.mass_kg and self.volume_l and self.density_kg_l and abs(self.mass_kg-self.volume_l*self.density_kg_l)>max(1e-6,self.mass_kg*1e-6):raise ValueError('Mass, volume and density conflict')
        if self.vs_fraction_wet and self.ts_fraction and self.vs_fraction_of_ts and abs(self.vs_fraction_wet-self.ts_fraction*self.vs_fraction_of_ts)>1e-6:raise ValueError('VS mass bases conflict')
        return self
