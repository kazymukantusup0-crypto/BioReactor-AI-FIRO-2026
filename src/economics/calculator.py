"""All quantities are explicit batch scenarios, never market estimates."""
from datetime import date
import math


def number(value,name,minimum=0,strict=False,maximum=None):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
        raise ValueError(f'{name}: требуется конечное число')
    if value < minimum or (strict and value==minimum) or (maximum is not None and value>maximum):
        raise ValueError(f'{name}: значение вне допустимого диапазона')
    return float(value)


def calculate_methane(data):
    required=['bmp_ml_ch4_g_vs','vs_mass_kg','bmp_unit','gas_volume_basis']
    missing=[k for k in required if data.get(k) is None or data.get(k)=='']
    if missing:
        return {'status':'needs_input','missing':missing,'message':'Для потенциального метана нужны BMP с единицами, измеренная масса VS и условия приведения газа.'}
    if data['bmp_unit']!='mL CH4/g VS':
        raise ValueError('bmp_unit: поддерживается только mL CH4/g VS; нельзя подменять VS влажной массой или TS')
    if not isinstance(data['gas_volume_basis'],str) or not data['gas_volume_basis'].strip():
        raise ValueError('gas_volume_basis: укажите условия приведения газа строкой')
    bmp=number(data['bmp_ml_ch4_g_vs'],'bmp_ml_ch4_g_vs')
    vs=number(data['vs_mass_kg'],'vs_mass_kg',strict=True)
    if 'mass_kg' in data and vs>number(data['mass_kg'],'mass_kg',strict=True):
        raise ValueError('Масса VS не может превышать влажную массу партии')
    potential=bmp*vs/1000
    if not math.isfinite(potential):
        raise ValueError('Переполнение расчёта метана; проверьте масштаб входов')
    return {'status':'ok','potential_methane_m3':potential,'gas_volume_basis':data['gas_volume_basis'],
        'bmp_ml_ch4_g_vs':bmp,'vs_mass_kg':vs,'formula':'BMP [mL/g VS] * VS [kg] / 1000',
        'message':f"Потенциальный метан: {potential:.6g} м³. Условия объёма: {data['gas_volume_basis']}. Это BMP-потенциал, не фактическая выработка реактора."}


ECONOMIC_FIELDS=['mass_kg','sale_price_per_kg','potential_methane_m3','recovery_fraction','methane_price_per_m3',
    'preparation_cost','heating_cost','operating_cost','currency','price_date','gas_volume_basis','price_gas_volume_basis']


def calculate_profitability(data):
    missing=[k for k in ECONOMIC_FIELDS if data.get(k) is None or data.get(k)=='']
    if missing:
        return {'status':'needs_input','missing':missing,'message':'Сравнение пока невозможно. Задайте количество, цены, дату, валюту, долю извлечения и все затраты партии (включая явные нули).'}
    for key in ['currency','gas_volume_basis','price_gas_volume_basis']:
        if not isinstance(data[key],str) or not data[key].strip():
            raise ValueError(f'{key}: требуется непустая строка')
    if data['gas_volume_basis'].strip().casefold()!=data['price_gas_volume_basis'].strip().casefold():
        raise ValueError('Условия приведения объёма и тарифа метана различаются. Сначала подтвердите или выполните приведение; автоматической конверсии нет.')
    try:
        date.fromisoformat(data['price_date'])
    except (ValueError,TypeError):
        raise ValueError('price_date: требуется дата YYYY-MM-DD') from None
    vals={k:number(data[k],k,strict=k=='mass_kg') for k in ECONOMIC_FIELDS if k not in ['currency','price_date','gas_volume_basis','price_gas_volume_basis']}
    number(vals['recovery_fraction'],'recovery_fraction',maximum=1)
    sale=vals['mass_kg']*vals['sale_price_per_kg']
    recovered=vals['potential_methane_m3']*vals['recovery_fraction']
    revenue=recovered*vals['methane_price_per_m3']
    costs=sum(vals[k] for k in ['preparation_cost','heating_cost','operating_cost'])
    net=revenue-costs
    delta=net-sale
    if not all(math.isfinite(v) for v in [sale,recovered,revenue,costs,net,delta]):
        raise ValueError('Переполнение расчёта; проверьте единицы и масштаб входов')
    currency=data['currency']
    return {'status':'ok','sale_revenue':sale,'recoverable_methane_m3':recovered,'methane_revenue':revenue,
        'preparation_cost':vals['preparation_cost'],'heating_cost':vals['heating_cost'],'operating_cost':vals['operating_cost'],
        'total_processing_cost':costs,'processing_net_profit':net,'difference_processing_minus_sale':delta,
        'currency':currency,'price_date':data['price_date'],'price_source':'explicit_user_inputs',
        'gas_volume_basis':data['gas_volume_basis'],'preferred_scenario':'processing' if delta>0 else 'sale' if delta<0 else 'equal',
        'limitations':['Сценарий по введённым ценам и доле извлечения, не прогноз рыночных цен или реального выхода.',
            'Цена относится к метану, не к сырому биогазу; объём и тариф должны иметь одинаковые условия приведения.',
            'Капитальные, налоговые, транспортные и прочие затраты учтены только если включены пользователем в operating_cost.'],
        'message':f'Сценарий ({currency}): продажа {sale:.6g}; выручка от метана {revenue:.6g}; затраты {costs:.6g}; чистый результат переработки {net:.6g}; разница с продажей {delta:+.6g}. Это условный расчёт по вашим входам.'}
