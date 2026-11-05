from datetime import datetime
from typing import Literal
from pydantic import Field,field_validator,model_validator
from src.market.domain import StrictModel
from src.agent.context import validate_context


class SessionInput(StrictModel):
    mode:Literal['offline','no_llm','online','auto']='offline'
    context:dict=Field(default_factory=dict)
    conversation_version:Literal['4','5.6','7']='4'

    @field_validator('context')
    @classmethod
    def context_valid(cls,value):return validate_context(value)


class ChatInput(StrictModel):
    message:str=Field(min_length=1,max_length=12000)
    request_id:str=Field(pattern=r'^[a-zA-Z0-9_-]{8,80}$')

    @field_validator('message')
    @classmethod
    def nonblank(cls,value):
        if not value.strip():raise ValueError('Введите вопрос')
        return value.strip()


class PredictionInput(StrictModel):
    model:Literal['stage1','stage1_5']='stage1_5'
    context:dict

    @field_validator('context')
    @classmethod
    def context_valid(cls,value):return validate_context(value)


class MeasurementContract(StrictModel):
    """Future observation contract ONLY. No ingestion or actuator command route."""
    device_id:str=Field(min_length=1,max_length=100)
    measured_at:datetime
    temperature_c:float|None=Field(default=None,gt=-273.15)
    ph:float|None=Field(default=None,ge=0,le=14)
    moisture_fraction:float|None=Field(default=None,ge=0,le=1)
    dry_solids_fraction:float|None=Field(default=None,ge=0,le=1)
    gas_volume_m3:float|None=Field(default=None,ge=0)
    gas_flow_m3_h:float|None=Field(default=None,ge=0)
    methane_fraction:float|None=Field(default=None,ge=0,le=1)
    gas_instrument:Literal['unknown','MQ_raw','calibrated_meter','calibrated_analyzer']='unknown'
    calibration_reference:str|None=None
    gas_volume_basis:str|None=None
    mq_raw_adc:int|None=Field(default=None,ge=0)
    heating_state:Literal['unknown','on','off']='unknown'
    cooling_state:Literal['unknown','on','off']='unknown'
    pump_state:Literal['unknown','on','off']='unknown'

    @model_validator(mode='after')
    def physically_documented(self):
        if self.measured_at.tzinfo is None:raise ValueError('measured_at requires a timezone')
        if any(v is not None for v in [self.gas_volume_m3,self.gas_flow_m3_h,self.methane_fraction]):
            if self.gas_instrument not in {'calibrated_meter','calibrated_analyzer'} or not self.calibration_reference:
                raise ValueError('Quantitative gas measurement requires calibrated instrument and calibration reference; MQ raw is not quantitative CH4')
            if not self.gas_volume_basis:raise ValueError('Gas reference conditions must be documented')
        if self.methane_fraction is not None and self.gas_instrument!='calibrated_analyzer':
            raise ValueError('Methane fraction requires a calibrated composition analyzer')
        return self
