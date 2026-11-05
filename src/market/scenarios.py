"""Mutually exclusive batch scenarios; quoted commodities are never interchangeable."""
from datetime import date
import math
from pydantic import Field,model_validator
from src.market.domain import StrictModel,COMMODITIES
from src.economics.calculator import calculate_methane,calculate_profitability


class ScenarioInput(StrictModel):
    region:str|None=None
    currency:str='KZT'
    consumer_class:str|None=None
    tax_basis:str|None=None
    feedstock_commodity:str|None=None
    mass_kg:float|None=Field(default=None,gt=0)
    bmp_ml_ch4_g_vs:float|None=Field(default=None,ge=0)
    bmp_unit:str|None=None
    vs_mass_kg:float|None=Field(default=None,gt=0)
    potential_methane_m3:float|None=Field(default=None,ge=0)
    gas_volume_basis:str|None=None
    recovery_fraction:float|None=Field(default=None,ge=0,le=1)
    methane_fraction:float|None=Field(default=None,gt=0,le=1)
    methane_energy_kwh_per_m3:float|None=Field(default=None,gt=0)
    electricity_efficiency:float|None=Field(default=None,gt=0,le=1)
    electricity_demand_kwh:float|None=Field(default=None,ge=0)
    energy_use_kwh:float|None=Field(default=None,ge=0)
    preparation_cost:float|None=Field(default=None,ge=0)
    heating_cost:float|None=Field(default=None,ge=0)
    operating_cost:float|None=Field(default=None,ge=0)
    storage_cost:float|None=Field(default=None,ge=0)
    transport_cost:float|None=Field(default=None,ge=0)
    gas_cleaning_cost:float|None=Field(default=None,ge=0)
    digestate_handling_cost:float|None=Field(default=None,ge=0)
    sale_storage_cost:float|None=Field(default=None,ge=0)
    sale_transport_cost:float|None=Field(default=None,ge=0)
    upgrading_cost:float|None=Field(default=None,ge=0)
    upgrading_recovery_fraction:float|None=Field(default=None,gt=0,le=1)
    biomethane_purity:float|None=Field(default=None,gt=0,le=1)
    gas_sale_product:str='raw_biogas'
    gas_sale_technical_confirmed:bool|None=None
    gas_sale_legal_confirmed:bool|None=None
    gas_sale_evidence:str|None=None
    digestate_mass_kg:float|None=Field(default=None,ge=0)
    digestate_mode:str='sale'
    digestate_quality_confirmed:bool|None=None
    digestate_market_allowed:bool|None=None
    digestate_equivalence_confirmed:bool|None=None
    digestate_quality_evidence:str|None=None
    price_ids:dict[str,int]=Field(default_factory=dict)
    max_price_age_days:int=Field(default=30,ge=0,le=3650)
    allow_stale_prices:bool=False
    allow_test_prices:bool=False

    @model_validator(mode='before')
    @classmethod
    def reject_boolean_numbers(cls,values):
        if isinstance(values,dict):
            from typing import get_args
            for key,value in values.items():
                field=cls.model_fields.get(key)
                if field and isinstance(value,bool) and (field.annotation is float or float in get_args(field.annotation)):
                    raise ValueError(f'{key} must be numeric, not boolean')
        return values

    @model_validator(mode='after')
    def valid(self):
        if self.gas_sale_product not in {'raw_biogas','biomethane'}:raise ValueError('Natural-gas price cannot value biogas sales')
        if self.digestate_mode not in {'sale','use'}:raise ValueError('digestate_mode must be sale or use')
        if self.vs_mass_kg is not None and self.mass_kg is not None and self.vs_mass_kg>self.mass_kg:raise ValueError('VS mass exceeds fresh mass')
        if self.bmp_unit is not None and self.bmp_unit!='mL CH4/g VS':raise ValueError('BMP must be in mL CH4/g VS')
        if self.feedstock_commodity and (self.feedstock_commodity not in COMMODITIES or COMMODITIES[self.feedstock_commodity][0]!='organic_feedstock'):raise ValueError('Unknown feedstock commodity')
        if set(self.price_ids)-{'feedstock','electricity','gas_sale','digestate'}:raise ValueError('Unknown price role')
        if any(isinstance(v,bool) for v in self.price_ids.values()):raise ValueError('Price id cannot be boolean')
        return self


class PriceUnavailable(ValueError):pass


def select_price(store,request,role):
    commodities={'feedstock':request.feedstock_commodity,'electricity':'electricity','gas_sale':request.gas_sale_product,'digestate':'digestate'}
    commodity=commodities[role]
    if not request.region:raise PriceUnavailable('region: укажите конкретный регион; общенациональная цена не подменяет местную')
    if not commodity:raise PriceUnavailable('feedstock_commodity: укажите товар исходного сырья')
    if not request.tax_basis:raise PriceUnavailable('tax_basis: укажите основание НДС для сопоставления')
    if role=='electricity' and not request.consumer_class:raise PriceUnavailable('consumer_class: укажите категорию потребителя электричества')
    if role in request.price_ids:
        selected=store.observation(request.price_ids[role],request.max_price_age_days);prices=[selected] if selected else []
    else:
        prices=store.prices(commodity,request.region,include_test=request.allow_test_prices,max_age_days=request.max_price_age_days,latest=True)
    types={'electricity':{'tariff','retail'},'feedstock':{'purchase','wholesale'},'gas_sale':{'purchase','wholesale'},
        'digestate':{'purchase','wholesale'} if request.digestate_mode=='sale' else {'retail','wholesale'}}[role]
    matching=[]
    for p in prices:
        if p['commodity']!=commodity or p['region']!=request.region or p['currency']!=request.currency or p['tax_basis']!=request.tax_basis or p['price_type'] not in types:continue
        if role=='electricity' and p['consumer_class']!=request.consumer_class:continue
        if p['is_future'] or p['reliability']=='unverified':continue
        if p['is_test'] and not request.allow_test_prices:continue
        if not p['is_test'] and not request.allow_stale_prices and p.get('validation_status')!='VERIFIED_CURRENT':continue
        # Test records only for explicit test scenarios; never implicit production fallbacks.
        if not p['is_test'] and (p['published_at'] is None or (p['is_stale'] and not request.allow_stale_prices)):continue
        if role=='gas_sale' and p['gas_volume_basis']!=request.gas_volume_basis:continue
        matching.append(p)
    if len(matching)!=1:
        raise PriceUnavailable(f'{role}: '+('нет пригодной цены нужного товара, региона, даты, типа, единиц и достоверности' if not matching else 'несколько сопоставимых цен; выберите price_ids явно'))
    p=matching[0]
    if role in request.price_ids:
        # Explicit IDs still obey caller freshness policy, independently of store default.
        if p['age_days']>request.max_price_age_days and not (request.allow_stale_prices or p['is_test']):raise PriceUnavailable(f'{role}: выбранная цена устарела')
    return p


BASE_COSTS=['preparation_cost','heating_cost','operating_cost','storage_cost','transport_cost','digestate_handling_cost']


def compare(store,data,persist=True):
    request=data if isinstance(data,ScenarioInput) else ScenarioInput.model_validate(data)
    values=request.model_dump()
    potential=request.potential_methane_m3
    provenance='explicit_user_potential' if potential is not None else 'unavailable'
    if potential is None and request.bmp_ml_ch4_g_vs is not None and request.vs_mass_kg is not None and request.bmp_unit and request.gas_volume_basis:
        converted=calculate_methane(values)
        if converted['status']=='ok':potential=converted['potential_methane_m3'];provenance='explicit_BMP_times_measured_VS'
    rows=[];used={};sensitivity=[]

    def price(role):
        if role not in used:used[role]=select_price(store,request,role)
        return float(used[role]['normalized_value'])

    def require(fields):
        missing=[key for key in fields if values.get(key) is None or values.get(key)=='']
        if missing:raise PriceUnavailable('Не заданы: '+', '.join(missing))

    def scenario(label):
        if label=='C':
            if request.gas_sale_technical_confirmed is False or request.gas_sale_legal_confirmed is False:
                return {'scenario':label,'status':'ineligible','reason':'Продажа газа не подтверждена технически или юридически','net_profit':None}
            require(['gas_sale_technical_confirmed','gas_sale_legal_confirmed','gas_sale_evidence'])
        if label=='D':
            if request.digestate_quality_confirmed is False or request.digestate_market_allowed is False:
                return {'scenario':label,'status':'ineligible','reason':'Качество или доступ дигестата на рынок не подтверждены','net_profit':None}
            require(['digestate_quality_confirmed','digestate_market_allowed','digestate_quality_evidence'])
            if request.digestate_mode=='use':
                if request.digestate_equivalence_confirmed is False:return {'scenario':label,'status':'ineligible','reason':'Замещение удобрения не подтверждено','net_profit':None}
                require(['digestate_equivalence_confirmed'])
        if label=='A':
            require(['mass_kg','sale_storage_cost','sale_transport_cost'])
            p=price('feedstock');volume=request.mass_kg
            revenue=volume*p;cost=request.sale_storage_cost+request.sale_transport_cost
            return {'scenario':label,'status':'ok','revenue':revenue,'total_cost':cost,'net_profit':revenue-cost,
                'valuation_role':'feedstock','priced_quantity':volume,'price':p,'price_slope':volume,
                'break_even_price':cost/volume,'break_even_unit':f'{request.currency}/kg'}
        require(BASE_COSTS+['energy_use_kwh','recovery_fraction','gas_volume_basis'])
        if potential is None:raise PriceUnavailable('Нужен обоснованный potential_methane_m3 или измеренные BMP + масса VS с условиями газа; данных ML для этого сырья может не быть')
        recovered=potential*request.recovery_fraction
        if not math.isfinite(recovered):raise ValueError('Nonfinite methane quantity')
        base=sum(values[k] for k in BASE_COSTS)
        electric=price('electricity') if request.energy_use_kwh else None
        electric_cost=request.energy_use_kwh*(electric or 0)
        cost=base+electric_cost
        if label=='B':
            require(['methane_energy_kwh_per_m3','electricity_efficiency','electricity_demand_kwh','gas_cleaning_cost'])
            p=price('electricity')
            generated=recovered*request.methane_energy_kwh_per_m3*request.electricity_efficiency
            volume=min(generated,request.electricity_demand_kwh)
            cost=base+request.gas_cleaning_cost+request.energy_use_kwh*p
            revenue=volume*p
            details={'gross_generated_kwh':generated,'valued_self_consumption_kwh':volume,'unvalued_surplus_kwh':generated-volume,
                'priced_quantity':volume,'price_slope':volume-request.energy_use_kwh,'valuation_role':'electricity','price':p,
                'non_price_cost':base+request.gas_cleaning_cost}
        elif label=='C':
            require(['gas_cleaning_cost'])
            if request.gas_sale_product=='raw_biogas':
                require(['methane_fraction']);volume=recovered/request.methane_fraction
            else:
                require(['upgrading_cost','upgrading_recovery_fraction','biomethane_purity'])
                volume=recovered*request.upgrading_recovery_fraction/request.biomethane_purity
                cost+=request.upgrading_cost
            p=price('gas_sale');revenue=volume*p;cost+=request.gas_cleaning_cost
            details={'priced_quantity':volume,'valuation_role':'gas_sale','price':p,'price_slope':volume,'product':request.gas_sale_product}
        else:
            require(['digestate_mass_kg']);volume=request.digestate_mass_kg;p=price('digestate')
            revenue=volume*p
            details={'priced_quantity':volume,'valuation_role':'digestate','price':p,'price_slope':volume,'mode':request.digestate_mode,
                'benefit_kind':'sale_revenue' if request.digestate_mode=='sale' else 'avoided_purchase_cost'}
        result={'scenario':label,'status':'ok','revenue':revenue,'total_cost':cost,'net_profit':revenue-cost,
            'recovered_methane_m3':recovered,**details}
        if label=='C' and recovered>0 and request.mass_kg is not None:
            # Reconcile the monetary ledger with existing calculate_profitability.
            # This is a derived CH4-equivalent valuation, NOT a natural-gas quote.
            sale=next((r for r in rows if r['scenario']=='A' and r['status']=='ok'),None)
            if sale:
                existing=calculate_profitability({'mass_kg':request.mass_kg,'sale_price_per_kg':float(used['feedstock']['normalized_value']),
                    'potential_methane_m3':potential,'recovery_fraction':request.recovery_fraction,'methane_price_per_m3':revenue/recovered,
                    'preparation_cost':request.preparation_cost,'heating_cost':request.heating_cost,
                    'operating_cost':max(0,cost-request.preparation_cost-request.heating_cost),
                    'currency':request.currency,'price_date':used['gas_sale']['published_at'] or used['gas_sale']['effective_from'],'gas_volume_basis':request.gas_volume_basis,'price_gas_volume_basis':request.gas_volume_basis})
                result['legacy_profitability_reconciliation']={'processing_net_profit':existing['processing_net_profit'],
                    'derived_ch4_valuation_not_market_quote':revenue/recovered}
        if not all(math.isfinite(v) for v in [revenue,cost,result['net_profit']]):raise ValueError('Nonfinite scenario result')
        return result

    for label in ['A','B','C','D']:
        try:rows.append(scenario(label))
        except PriceUnavailable as exc:rows.append({'scenario':label,'status':'needs_input','reason':str(exc),'net_profit':None})
    sale=next((r for r in rows if r['scenario']=='A' and r['status']=='ok'),None)
    for row in rows:
        if row['status']!='ok':continue
        if sale:
            row['difference_vs_sale']=row['net_profit']-sale['net_profit']
            if row['scenario']!='A':
                denominator=row['price_slope']
                numerator=(row.get('non_price_cost',row['total_cost'])+sale['net_profit'])
                row['break_even_price_to_match_sale']=numerator/denominator if denominator>0 else None
                row['break_even_unit']=f"{request.currency}/"+('kWh' if row['scenario']=='B' else 'kg' if row['scenario']=='D' else 'm3')
        roles=[(row['valuation_role'],row['price_slope'],row['price'])]
        if row['scenario'] in {'C','D'} and request.energy_use_kwh:
            roles.append(('electricity',-request.energy_use_kwh,float(used['electricity']['normalized_value'])))
        for role,slope,p in roles:
            sensitivity.append({'scenario':row['scenario'],'price_role':role,'price':p,'net_profit_minus_20pct':row['net_profit']-.2*p*slope,
                'net_profit_plus_20pct':row['net_profit']+.2*p*slope,'method':'One price at a time, other explicit inputs fixed; not a future-price forecast'})
    complete=all(r['status'] in {'ok','ineligible'} for r in rows)
    available=[r for r in rows if r['status']=='ok']
    winner=max(available,key=lambda r:r['net_profit'])['scenario'] if complete and available else None
    hypothetical=request.allow_test_prices or any(p['is_stale'] for p in used.values())
    message='; '.join(f"{r['scenario']}: {r['net_profit']:.6g} {request.currency}" if r['status']=='ok' else f"{r['scenario']}: {r.get('reason',r['status'])}" for r in rows)
    result={'status':'ok' if complete else 'needs_input','scenarios':rows,'recommended_scenario':winner,
        'final_recommendation':winner if not hypothetical else None,'is_final_recommendation':winner is not None and not hypothetical,
        'recommendation_scope':'test_or_stale_price_scenario_only' if hypothetical else 'explicit_assumptions_and_selected_quotes',
        'currency':request.currency,'region':request.region,'potential_methane_m3':potential,'potential_provenance':provenance,
        'selected_prices':used,'sensitivity':sensitivity,'double_counting_policy':'A/B/C/D are alternatives. B values only self-consumed electricity; C only gas sales; D only digestate benefit. No summed gas/electricity/digestate revenue.',
        'limitations':['Нет гарантии фактической эффективности или юридической оценки: подтверждения задаёт пользователь.',
            'Тариф покупки электроэнергии означает только экономию собственного потребления, не доход от продажи в сеть.',
            'Минеральное удобрение не оценивает дигестат без подтверждённой эквивалентности; здесь такой пересчёт не выполняется.'],
        'message':('Условные сценарии (тестовые/устаревшие цены). ' if hypothetical else 'Рыночные сценарии. ')+message+
            (f'. При заданных предположениях лучший вариант: {winner}.' if winner else '. Итоговая рекомендация не выдана: сравнение неполное.')}
    if persist:result['scenario_id']=store.save_scenario(request.model_dump(mode='json'),result)
    return result
