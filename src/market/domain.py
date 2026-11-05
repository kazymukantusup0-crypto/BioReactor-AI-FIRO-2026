from datetime import date, datetime, timezone,timedelta
from decimal import Decimal, InvalidOperation
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CATEGORIES=['natural_gas','electricity','organic_fertilizer','mineral_fertilizer','organic_feedstock','heat_energy']
COMMODITIES={
    'natural_gas':('natural_gas','m3','Природный газ'),
    'raw_biogas':('natural_gas','m3','Сырой биогаз; отдельный товар'),
    'biomethane':('natural_gas','m3','Очищенный биометан; отдельный товар'),
    'electricity':('electricity','kWh','Электроэнергия'),
    'digestate':('organic_fertilizer','kg','Дигестат подтверждённого качества'),
    'compost':('organic_fertilizer','kg','Компост'),
    'urea':('mineral_fertilizer','kg','Карбамид'),
    'ammophos':('mineral_fertilizer','kg','Аммофос'),
    'food_waste':('organic_feedstock','kg','Пищевые отходы'),
    'Wheat straw':('organic_feedstock','kg','Пшеничная солома'),
    'Whey':('organic_feedstock','kg','Молочная сыворотка'),
    'cattle_manure':('organic_feedstock','kg','Навоз КРС'),
    'swine_manure':('organic_feedstock','kg','Свиной навоз'),
    'poultry_manure':('organic_feedstock','kg','Птичий помёт'),
    'organic_waste':('organic_feedstock','kg','Органические отходы'),
    'heat':('heat_energy','kWh','Тепловая энергия; отдельный товар и тариф'),
    'chernozem':('organic_feedstock','kg','Чернозём; не подтверждённый BMP-субстрат'),
}
UNITS={'kg':('kg',Decimal(1)),'t':('kg',Decimal(1000)),'g':('kg',Decimal('.001')),
    'kWh':('kWh',Decimal(1)),'MWh':('kWh',Decimal(1000)),
    '100_kWh':('kWh',Decimal(100)),
    'm3':('m3',Decimal(1)),'1000_m3':('m3',Decimal(1000)),'L':('m3',Decimal('.001'))}
PRICE_TYPES=['retail','wholesale','tariff','purchase','reference']
RELIABILITY=['verified_official','verified_manual','unverified','test']


def utcnow():
    return datetime.now(timezone.utc)


def market_today(now=None):
    # The primary market uses the client's Asia/Qyzylorda calendar. Windows may
    # lack IANA tzdata; UTC+05 is the current offset for this project context.
    from zoneinfo import ZoneInfo,ZoneInfoNotFoundError
    try:zone=ZoneInfo('Asia/Qyzylorda')
    except ZoneInfoNotFoundError:zone=timezone(timedelta(hours=5))
    return (now or utcnow()).astimezone(zone).date()


def normalize_price(value,unit,commodity):
    if unit not in UNITS or commodity not in COMMODITIES:
        raise ValueError('Unknown unit or commodity')
    base,factor=UNITS[unit]
    if base!=COMMODITIES[commodity][1]:
        raise ValueError('Incompatible unit and commodity; no density, energy or gas-composition conversions are implied')
    price=Decimal(str(value))
    if not price.is_finite() or price<0:
        raise ValueError('Price must be finite and nonnegative')
    return format((price/factor).normalize(),'f'),base


class StrictModel(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)


class SourceInput(StrictModel):
    id:str=Field(pattern=r'^[a-z0-9_-]{1,64}$')
    name:str=Field(min_length=1,max_length=300)
    url:str=Field(min_length=1,max_length=2000)
    category:str
    adapter:str='manual'
    enabled:bool=True
    config:dict=Field(default_factory=dict)

    @field_validator('category')
    @classmethod
    def category_valid(cls,v):
        if v not in CATEGORIES: raise ValueError('Unknown category')
        return v

    @field_validator('adapter')
    @classmethod
    def adapter_valid(cls,v):
        if v not in {'manual','esalmaty','csv','bns_retail_xlsx','karaganda_supply','krec_supply'}: raise ValueError('Unknown adapter')
        return v

    @model_validator(mode='after')
    def origin_valid(self):
        if self.adapter=='esalmaty' and self.url!='https://www.esalmaty.kz/ru/business-tariffs':raise ValueError('Official adapter is pinned to the verified origin and page')
        official={'bns_retail_xlsx':'https://stat.gov.kz/ru/industries/economy/prices/spreadsheets/?name=19087',
            'karaganda_supply':'https://www.k-zharyk.kz/ru/node/329','krec_supply':'https://krec.kz/price'}
        if self.adapter in official and self.url!=official[self.adapter]:raise ValueError('Official adapter origin/page mismatch')
        return self


class PriceInput(StrictModel):
    source_id:str
    commodity:str
    region:str=Field(min_length=1,max_length=100)
    country:str=Field(default='KZ',pattern=r'^[A-Z]{2}$')
    value:Decimal=Field(ge=0,max_digits=22,decimal_places=8)
    currency:str=Field(pattern=r'^[A-Z]{3}$')
    unit:str
    published_at:date|None=None
    effective_from:date
    valid_to:date|None=None
    price_type:str
    reliability:str='unverified'
    consumer_class:str=Field(min_length=1,max_length=100)
    tax_basis:str=Field(min_length=1,max_length=100)
    gas_volume_basis:str|None=None
    source_url:str=Field(min_length=1,max_length=2000)
    evidence:str=Field(min_length=1,max_length=3000)
    is_test:bool=False
    acquisition_method:str='manual'
    period_start:date|None=None
    period_end:date|None=None

    @model_validator(mode='after')
    def check(self):
        if self.commodity not in COMMODITIES: raise ValueError('Unknown commodity')
        if self.price_type not in PRICE_TYPES or self.reliability not in RELIABILITY: raise ValueError('Invalid price type/reliability')
        normalize_price(self.value,self.unit,self.commodity)
        if self.valid_to and self.valid_to<self.effective_from: raise ValueError('Invalid validity dates')
        if self.published_at and self.published_at>market_today(): raise ValueError('Publication cannot be in the future')
        if self.is_test != (self.reliability=='test'): raise ValueError('Test prices must carry both is_test=true and reliability=test')
        if self.currency not in {'KZT','USD','EUR','RUB','UZS','KGS','CNY','GBP'}:raise ValueError('Unsupported currency; add an explicit validated currency mapping')
        if not self.region.startswith(self.country+'-'):raise ValueError('Region must be explicitly namespaced by country, e.g. KZ-Karaganda or KZ-national')
        if self.acquisition_method not in {'manual','legacy_unspecified','https_html','https_csv','https_xlsx','manual_pdf'}:raise ValueError('Unknown acquisition method')
        if bool(self.period_start)!=bool(self.period_end):raise ValueError('Both period dates required')
        if self.period_start and (self.period_start>self.period_end or self.period_end!=self.effective_from):raise ValueError('Monthly observation must use its actual period end as as-of date')
        if COMMODITIES[self.commodity][1]=='m3' and not self.gas_volume_basis: raise ValueError('Gas reference conditions required')
        return self
