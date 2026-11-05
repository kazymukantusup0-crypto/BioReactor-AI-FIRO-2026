"""Explicit scenario inputs; quantities include provenance and compatible gas bases."""
from datetime import date
from typing import Literal
from pydantic import Field,model_validator
from src.optimizer.schemas import Strict

class Range(Strict):
    low:float=Field(ge=0)
    high:float=Field(ge=0)
    provenance:Literal['MEASURED','USER_REPORTED','LITERATURE_ESTIMATE','HYPOTHETICAL_SCENARIO','MARKET_REFERENCE','CONFIRMED_PRICE']='USER_REPORTED'
    evidence:str=Field(default='',max_length=1000)
    @model_validator(mode='after')
    def ordered(self):
        if self.low>self.high:raise ValueError('Range low exceeds high')
        return self

class GasBasis(Strict):
    temperature_k:float=Field(gt=0)
    pressure_pa:float=Field(gt=0)
    moisture:Literal['dry','wet','unknown']='unknown'
    description:str=Field(default='',max_length=300)

class Quote(Strict):
    value:float=Field(ge=0)
    currency:Literal['KZT']='KZT'
    unit:Literal['KZT/kg','KZT/kWh','KZT/m3']
    commodity:Literal['cattle_manure','swine_manure','poultry_manure','food_waste','mixture','sheep_goat_manure','horse_manure','vegetable_waste','fruit_waste','plant_residue','grass','straw','silage','dairy_waste','other_organic','electricity','useful_heat','raw_biogas','biomethane','digestate','natural_gas']
    region:str=Field(min_length=1,max_length=100)
    published_at:date|None=None
    confirmed:bool=False
    source:str=Field(min_length=1,max_length=1000)
    counterparty_confirmed:bool=False
    minimum_batch_kg:float|None=Field(default=None,ge=0)
    material_state:str|None=None
    gas_basis:GasBasis|None=None
    consumer_class:str|None=None
    tax_basis:str|None=None

class Load(Strict):
    name:str=Field(min_length=1,max_length=100)
    power_w:float=Field(ge=0)
    hours:float=Field(ge=0)
    duty_fraction:float=Field(default=1,ge=0,le=1)
    provenance:Literal['MEASURED','USER_REPORTED','HYPOTHETICAL_SCENARIO']='USER_REPORTED'

class ReactorInputs(Strict):
    reactor_working_volume_l:float|None=Field(default=None,gt=0)
    headspace_l:float|None=Field(default=None,ge=0)
    inoculum_volume_l:float|None=Field(default=None,ge=0)
    dilution_water_l:float|None=Field(default=None,ge=0)
    resident_liquid_volume_l:float|None=Field(default=None,ge=0)
    operating_mode:Literal['batch','continuous']|None=None
    reactor_type:str|None=Field(default=None,max_length=150)
    engineering_review_confirmed:bool=False
    safety_review_required:bool=False
    temperature_c:float|None=Field(default=None,gt=-273.15)
    initial_temperature_c:float|None=Field(default=None,gt=-273.15)
    ambient_temperature_c:float|None=Field(default=None,gt=-273.15)
    heated_mass_kg:float|None=Field(default=None,gt=0)
    heat_capacity_kj_kg_k:float|None=Field(default=None,gt=0)
    heat_loss_coefficient_w_k:float|None=Field(default=None,ge=0)
    u_w_m2_k:float|None=Field(default=None,ge=0)
    area_m2:float|None=Field(default=None,gt=0)
    duration_days:float|None=Field(default=None,gt=0)
    heater_efficiency:float|None=Field(default=None,gt=0,le=1)
    heating_carrier:Literal['electricity','process_heat','external_heat']|None=None
    auxiliary_energy_kwh:float|None=Field(default=None,ge=0)
    loads:list[Load]=Field(default_factory=list,max_length=20)
    loads_complete:bool=False
    energy_scope:str|None=Field(default=None,max_length=300)
    provenance:Literal['MEASURED','USER_REPORTED','HYPOTHETICAL_SCENARIO']='USER_REPORTED'
    @model_validator(mode='after')
    def matching_ua(self):
        if self.heat_loss_coefficient_w_k is not None and self.u_w_m2_k is not None and self.area_m2 is not None:
            import math
            if not math.isclose(self.heat_loss_coefficient_w_k,self.u_w_m2_k*self.area_m2,rel_tol=1e-6,abs_tol=1e-9):raise ValueError('UA disagrees with U times A')
        return self

class DecisionInputs(Strict):
    gas_use:Literal['unknown','heat','electricity','chp','sell_gas']='unknown'
    gas_basis:GasBasis|None=None
    methane_fraction:Range|None=None
    composition_basis:GasBasis|None=None
    assume_reference_compatibility:bool=False
    recovery_fraction:Range|None=None
    thermal_efficiency:Range|None=None
    electrical_efficiency:Range|None=None
    chp_thermal_efficiency:Range|None=None
    chp_electrical_efficiency:Range|None=None
    use_reference_scenarios:bool=True
    heating_value_kwh_m3:float|None=Field(default=None,gt=0)
    heating_value_type:Literal['LHV','HHV']='LHV'
    heating_value_basis:GasBasis|None=None
    equipment_evidence:str|None=Field(default=None,max_length=1000)
    reactor:ReactorInputs=Field(default_factory=ReactorInputs)
    quotes:dict[str,Quote]=Field(default_factory=dict)
    price_ids:dict[str,int]=Field(default_factory=dict)
    consumer_class:str|None=None
    tax_basis:str|None=None
    max_price_age_days:int=Field(default=30,ge=0,le=3650)
    costs:dict[str,Range]=Field(default_factory=dict)
    all_operating_costs_included:bool=False
    include_capital:bool=False
    capital_cost_per_batch:Range|None=None
    heat_demand_kwh:float|None=Field(default=None,ge=0)
    electricity_demand_kwh:float|None=Field(default=None,ge=0)
    assume_full_self_consumption:bool=False
    replacement_heat_source:Literal['unknown','electric_resistance','priced_useful_heat']='unknown'
    gas_sale_technical_confirmed:bool=False
    gas_sale_legal_confirmed:bool=False
    gas_quality_confirmed:bool=False
    gas_storage_transport_confirmed:bool=False
    digestate_mass_kg:float|None=Field(default=None,ge=0)
    digestate_quality_confirmed:bool=False
    digestate_market_allowed:bool=False
    @model_validator(mode='after')
    def physically_consistent(self):
        for name in ['methane_fraction','recovery_fraction','thermal_efficiency','electrical_efficiency','chp_thermal_efficiency','chp_electrical_efficiency']:
            v=getattr(self,name)
            if v is not None and (v.high>1 or name=='methane_fraction' and v.low<=0):raise ValueError(name+' must be a valid fraction')
        if self.chp_electrical_efficiency and self.chp_thermal_efficiency and self.chp_electrical_efficiency.high+self.chp_thermal_efficiency.high>1+1e-12:raise ValueError('CHP heat plus electric efficiency exceeds unity')
        if self.heating_value_type=='HHV' and self.heating_value_kwh_m3 is None:raise ValueError('An HHV coefficient must be explicitly supplied; FNR default is LHV')
        allowed={'preparation','maintenance','storage','transport','gas_cleaning','digestate_handling','packaging','sale_transport','sale_storage','sale_packaging','gas_sale_transport','digestate_transport'}
        if set(self.costs)-allowed:raise ValueError('Unknown cost component: '+','.join(set(self.costs)-allowed))
        if set(self.quotes)-{'feedstock','electricity','heat','gas_sale','digestate'}:raise ValueError('Unknown quote role')
        return self
