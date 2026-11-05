"""Explicit SI inputs. Missing values are never replaced with engineering defaults."""
from typing import Any, Literal, get_args
from pydantic import BaseModel, ConfigDict, Field, model_validator


Status = Literal['VERIFIED', 'CONDITIONAL', 'INSUFFICIENT_DATA', 'INFEASIBLE']
Objective = Literal['methane', 'energy', 'cost', 'profit', 'duration', 'uncertainty']


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)

    @model_validator(mode='before')
    @classmethod
    def no_boolean_numbers(cls, values):
        if isinstance(values, dict):
            for key, value in values.items():
                field = cls.model_fields.get(key)
                if field and isinstance(value, bool) and (field.annotation in (float, int) or float in get_args(field.annotation)):
                    raise ValueError(f'{key}: a number, not a boolean, is required')
        return values


class ProcessParameters(Strict):
    material: str | None = Field(default=None, max_length=120)
    mass_kg: float | None = Field(default=None, gt=0)
    feedstock_volume_l: float | None = Field(default=None, gt=0)
    density_kg_l: float | None = Field(default=None, gt=0)
    reactor_total_volume_l: float | None = Field(default=None, gt=0)
    reactor_working_volume_l: float | None = Field(default=None, gt=0)
    headspace_l: float | None = Field(default=None, ge=0)
    inoculum_volume_l: float | None = Field(default=None, ge=0)
    dilution_water_l: float | None = Field(default=None, ge=0)
    resident_liquid_volume_l: float | None = Field(default=None, ge=0)
    liquid_charge_volume_l: float | None = Field(default=None, ge=0)
    gas_storage_volume_l: float | None = Field(default=None, ge=0)
    gas_storage_conditions: str | None = Field(default=None, max_length=1000)
    reactor_type: str | None = Field(default=None, max_length=150)
    process_type: str | None = Field(default=None, max_length=150)
    operating_mode: Literal['batch', 'continuous'] | None = None
    batch_duration_days: float | None = Field(default=None, gt=0)
    turnaround_days: float | None = Field(default=None, ge=0)
    duration_days: float | None = Field(default=None, gt=0)
    hrt_days: float | None = Field(default=None, gt=0)
    olr_kg_vs_m3_day: float | None = Field(default=None, ge=0)
    daily_feed_volume_l: float | None = Field(default=None, gt=0)
    daily_vs_mass_kg: float | None = Field(default=None, ge=0)
    inoculum_description: str | None = Field(default=None, max_length=1000)
    ts_percent: float | None = Field(default=None, ge=0, le=100)
    vs_percent: float | None = Field(default=None, ge=0, le=100)
    vs_basis: Literal['TS', 'fresh_mass'] | None = None
    vs_mass_kg: float | None = Field(default=None, gt=0)
    ph: float | None = Field(default=None, ge=0, le=14)
    temperature_c: float | None = Field(default=None, gt=-273.15)
    initial_temperature_c: float | None = Field(default=None, gt=-273.15)
    ambient_temperature_c: float | None = Field(default=None, gt=-273.15)
    heating_available: bool | None = None
    heated_mass_kg: float | None = Field(default=None, gt=0)
    heat_capacity_kj_kg_k: float | None = Field(default=None, gt=0)
    heat_loss_coefficient_w_k: float | None = Field(default=None, ge=0)
    heater_efficiency: float | None = Field(default=None, gt=0, le=1)
    auxiliary_power_w: float | None = Field(default=None, ge=0)
    auxiliary_duty_fraction: float | None = Field(default=None, ge=0, le=1)
    auxiliary_energy_kwh: float | None = Field(default=None, ge=0)
    energy_scope: str | None = Field(default=None, max_length=500)
    bmp_ml_ch4_g_vs: float | None = Field(default=None, ge=0)
    bmp_unit: Literal['mL CH4/g VS'] | None = None
    bmp_provenance: Literal['measured', 'scenario_assumption'] | None = None
    bmp_evidence: str | None = Field(default=None, max_length=1000)
    gas_volume_basis: str | None = Field(default=None, max_length=1000)
    recovery_fraction: float | None = Field(default=None, ge=0, le=1)
    methane_fraction: float | None = Field(default=None, gt=0, le=1)
    model: Literal['stage1', 'stage1_5'] = 'stage1_5'
    c_vs_sub_m: float | None = Field(default=None, ge=0, le=1)
    c_vs_sub_f: float | None = Field(default=None, ge=0, le=1)
    c_vs_inoc: float | None = Field(default=None, ge=0, le=1)
    ISR: float | None = Field(default=None, gt=0)
    pretreatment: str | None = Field(default=None, max_length=1000)
    mixture_components: list[dict[str, Any]] = Field(default_factory=list, max_length=10)
    # Explicitly selected cost/scenario data, validated again by Market Intelligence.
    market: dict[str, Any] = Field(default_factory=dict)
    assumptions: dict[str, Any] = Field(default_factory=dict)
    user_limits: dict[str, float] = Field(default_factory=dict)
    feedstock_purchase_cost: float | None = Field(default=None,ge=0)
    capital_cost: float | None = Field(default=None,gt=0)
    annual_batches: float | None = Field(default=None,gt=0)
    annual_fixed_cost: float | None = Field(default=None,ge=0)

    @model_validator(mode='before')
    @classmethod
    def literal_inputs(cls,values):
        if isinstance(values,dict):
            if any(isinstance(value,bool) for value in values.get('user_limits',{}).values()):
                raise ValueError('User limits require numbers, not booleans')
            for key,value in values.items():
                if key in cls.model_fields and isinstance(value,str) and not value.strip():
                    raise ValueError(key+': blank text is unknown; omit it instead')
        return values

    @model_validator(mode='after')
    def consistency(self):
        if self.vs_mass_kg is not None and self.mass_kg is not None and self.vs_mass_kg > self.mass_kg:
            raise ValueError('VS mass cannot exceed fresh mass')
        if self.mass_kg is not None and self.feedstock_volume_l is not None and self.density_kg_l is not None:
            import math
            if not math.isclose(self.mass_kg, self.feedstock_volume_l * self.density_kg_l, rel_tol=.01):
                raise ValueError('Mass, volume and density disagree by more than 1%')
        if self.bmp_ml_ch4_g_vs is not None and (not self.bmp_unit or not self.bmp_provenance or not self.bmp_evidence):
            raise ValueError('Explicit BMP requires unit, provenance and evidence or scenario explanation')
        allowed = {'temperature_min_c', 'temperature_max_c', 'energy_max_kwh', 'duration_max_days', 'cost_max'}
        if set(self.user_limits) - allowed:
            raise ValueError('Unknown user limit')
        if any(isinstance(value, bool) for value in self.user_limits.values()):
            raise ValueError('User limits must be numeric')
        if self.user_limits.get('temperature_min_c', -273.15) > self.user_limits.get('temperature_max_c', float('inf')):
            raise ValueError('Minimum temperature exceeds maximum')
        if any(v < 0 for k, v in self.user_limits.items() if k not in {'temperature_min_c', 'temperature_max_c'}):
            raise ValueError('Negative energy, time or cost limit')
        for component in self.mixture_components:
            if set(component) != {'material', 'mass_fraction'} or not isinstance(component['material'], str):
                raise ValueError('Mixture components require material and mass_fraction only')
            fraction = component['mass_fraction']
            if isinstance(fraction, bool) or not isinstance(fraction, (int, float)) or not 0 < fraction <= 1:
                raise ValueError('Mixture mass fractions must be in (0,1]')
        if self.mixture_components and abs(sum(c['mass_fraction'] for c in self.mixture_components)-1) > 1e-8:
            raise ValueError('Mixture mass fractions must sum to one')
        return self


class ScenarioCandidate(Strict):
    label: str = Field(min_length=1, max_length=150)
    # Changes are hypotheses unless supplied as the base measured input.
    overrides: dict[str, Any] = Field(default_factory=dict)
    rationale: str = Field(min_length=3, max_length=1500)

    @model_validator(mode='after')
    def known_overrides(self):
        if set(self.overrides) - set(ProcessParameters.model_fields):
            raise ValueError('Unknown scenario override')
        if set(self.overrides) & {'assumptions', 'user_limits', 'model'}:
            raise ValueError('Scenario overrides cannot replace provenance, limits or model')
        return self


class SensitivityRange(Strict):
    parameter: Literal['bmp_ml_ch4_g_vs', 'vs_mass_kg', 'temperature_c', 'heat_loss_coefficient_w_k',
                       'auxiliary_energy_kwh', 'electricity_price', 'feedstock_price', 'operating_cost']
    low: float
    high: float
    provenance: Literal['USER_DEFINED_RANGE', 'SOURCE_VERIFIED']
    evidence: str = Field(min_length=4, max_length=1000)
    source_url: str | None = Field(default=None, pattern=r'^https://', max_length=2000)

    @model_validator(mode='after')
    def ordered(self):
        if self.low > self.high:
            raise ValueError('Sensitivity range low exceeds high')
        if self.parameter != 'temperature_c' and self.low < 0:
            raise ValueError('Negative physical input or cost')
        if self.parameter == 'temperature_c' and self.low <= -273.15:
            raise ValueError('Temperature below absolute zero')
        if self.provenance == 'SOURCE_VERIFIED' and not self.source_url:
            raise ValueError('Scientific range requires source URL')
        return self


class ProcessRequest(ProcessParameters):
    label: str = Field(default='Process study', min_length=1, max_length=150)
    candidates: list[ScenarioCandidate] = Field(default_factory=list, max_length=12)
    objectives: list[Objective] = Field(default_factory=list, max_length=6)
    sensitivity: list[SensitivityRange] = Field(default_factory=list, max_length=12)

    @model_validator(mode='after')
    def unique(self):
        if len(set(self.objectives)) != len(self.objectives):
            raise ValueError('Objectives must be unique')
        if len({c.label for c in self.candidates}) != len(self.candidates):
            raise ValueError('Scenario labels must be unique')
        return self
