"""Shared service used by HTTP server and local agent; no server required for reads."""
from collections import defaultdict
from datetime import date,timedelta
from src.market.domain import market_today
from src.market.store import Store
from src.market.adapters import bootstrap
from src.market.scenarios import compare


def get_store():
    store=Store();bootstrap(store);return store


def get_market_prices(context,store=None):
    store=store or get_store()
    region=context.get('market_region') or context.get('market_scenario',{}).get('region')
    if not region:
        return {'status':'needs_input','missing':['market_region'],'prices':[],
            'message':'Укажите market_region (например, KZ-Almaty). Цены разных регионов не подменяются друг другом.'}
    prices=store.prices(context.get('market_commodity'),region,latest=True)
    geographic_warning=None
    if not prices and region!='KZ-national':
        prices=[p for p in store.prices(context.get('market_commodity'),'KZ-national',latest=True) if p['price_type']=='reference']
        if prices:geographic_warning='Региональных наблюдений нет. Показаны только общенациональные статистические ориентиры; они не подставляются вместо местной торговой цены.'
    message='; '.join(f"{p['commodity']}: {p['normalized_value']} {p['currency']}/{p['normalized_unit']}, {p['region']}, {p['validation_status']}, возраст {p['age_days']} дн., публикация {p['published_at'] or 'не установлена'}, профиль {p['consumer_class']}, {p['tax_basis']}, источник {p['source_name']}, "+('статистическая/справочная величина, не предложение сделки' if p['price_type']=='reference' else 'тариф/котировка с указанным профилем') for p in prices)
    return {'status':'ok' if prices else 'needs_input','missing':[] if prices else ['verified_market_observations'],
        'region':region,'prices':prices,'geographic_scope_warning':geographic_warning,'sources':[{'title':p['source_name'],'url':p['source_url']} for p in prices],
        'message':('Последние сохранённые цены: '+message+(' '+geographic_warning if geographic_warning else '')) if prices else 'В регионе нет подходящих сохранённых цен; нужен проверенный импорт или успешное обновление источника.'}


def get_price_history(context,store=None):
    store=store or get_store()
    region=context.get('market_region');commodity=context.get('market_commodity')
    if not region or not commodity:
        return {'status':'needs_input','missing':[k for k in ['market_region','market_commodity'] if not context.get(k)],'message':'Для истории укажите регион и конкретный товар.'}
    rows=store.prices(commodity,region,start=context.get('market_start'),end=context.get('market_end'))
    changes=price_changes(rows)
    return {'status':'ok','prices':rows,'changes':changes,'message':f'Сохранено наблюдений: {len(rows)}. Процентные изменения посчитаны отдельно по сопоставимым источникам, типам цен и единицам; прогноз будущих цен не строится.'}


def price_changes(rows,as_of=None):
    as_of=as_of or market_today()
    if isinstance(as_of,str):as_of=date.fromisoformat(as_of)
    groups=defaultdict(list)
    for p in rows:
        key=tuple(p[k] for k in ['source_id','commodity','region','currency','normalized_unit','consumer_class','tax_basis','price_type','gas_volume_basis'])
        groups[key].append(p)
    results=[]
    for key,series in groups.items():
        series.sort(key=lambda p:(p['effective_from'],p['id']))
        a,b=series[0],series[-1];start,end=float(a['normalized_value']),float(b['normalized_value'])
        windows={}
        by_day=defaultdict(list)
        for p in series:by_day[p['effective_from']].append(p)
        for days in [7,30,90]:
            target=(as_of-timedelta(days=days)).isoformat()
            current=by_day.get(as_of.isoformat(),[]);previous=by_day.get(target,[])
            # Never carry a monthly statistic forward to manufacture daily history.
            valid=len(current)==1 and len(previous)==1 and float(previous[0]['normalized_value'])>0
            windows[str(days)]={'status':'ok' if valid else 'insufficient_history',
                'from':target,'to':as_of.isoformat(),
                'percent_change':(float(current[0]['normalized_value'])/float(previous[0]['normalized_value'])-1)*100 if valid else None,
                'method':'Exact dated observations at both endpoints; no interpolation or forward fill'}
        results.append({'source_id':key[0],'commodity':key[1],'region':key[2],'currency':key[3],'unit':key[4],
            'consumer_class':key[5],'tax_basis':key[6],'price_type':key[7],'gas_volume_basis':key[8],
            'observations':len(series),'from':a['effective_from'],'to':b['effective_from'],
            'absolute_change':end-start if len(series)>1 else None,'percent_change':(end-start)/start*100 if start>0 and len(series)>1 else None,
            'windows_days':windows})
    return results


def compare_market_scenarios(context,results=None,store=None):
    store=store or get_store();results=results or {}
    data=dict(context.get('market_scenario',{}))
    if context.get('market_region'):data.setdefault('region',context['market_region'])
    mapping={'material':'feedstock_commodity','mass_kg':'mass_kg','potential_methane_m3':'potential_methane_m3',
        'bmp_ml_ch4_g_vs':'bmp_ml_ch4_g_vs','bmp_unit':'bmp_unit','vs_mass_kg':'vs_mass_kg',
        'gas_volume_basis':'gas_volume_basis','recovery_fraction':'recovery_fraction','preparation_cost':'preparation_cost',
        'heating_cost':'heating_cost','operating_cost':'operating_cost','currency':'currency'}
    for key,dest in mapping.items():
        if key in context:data.setdefault(dest,context[key])
    # Unknown feedstocks are reported as missing, never mapped to a known price.
    from src.market.domain import COMMODITIES
    if data.get('feedstock_commodity') not in COMMODITIES:data.pop('feedstock_commodity',None)
    prediction=results.get('predict_bmp',{})
    if prediction.get('status')=='ok' and 'bmp_ml_ch4_g_vs' not in data and 'potential_methane_m3' not in data:
        data.update(bmp_ml_ch4_g_vs=prediction['bmp'],bmp_unit='mL CH4/g VS',
            gas_volume_basis='source BMP reference conditions; normalization not independently verified')
    result=compare(store,data)
    if prediction.get('status')=='ok':result['bmp_model_version']=prediction['model_version']
    return result


def explain_market_recommendation(context,results=None,store=None):
    result=(results or {}).get('compare_market_scenarios')
    if result is None:result=compare_market_scenarios(context,results,store)
    return {'status':result['status'],'scenario_id':result.get('scenario_id'),'recommended_scenario':result['recommended_scenario'],
        'final_recommendation':result.get('final_recommendation'),
        'sources':[{'role':role,'title':p['source_name'],'url':p['source_url'],'region':p['region'],
            'published_at':p['published_at'],'effective_from':p['effective_from'],'validation_status':p['validation_status']} for role,p in result['selected_prices'].items()],
        'selected_price_ids':{role:p['id'] for role,p in result['selected_prices'].items()},
        'limitations':result['limitations'],'message':result['message']+' Доходы газа, электричества и дигестата не суммировались; B, C и D — альтернативы.'}


def recommendation_change(store,identifier):
    """Revalue a saved scenario using the same source/profile, leaving history intact."""
    records=store.scenarios(identifier)
    if not records:raise LookupError('Scenario not found')
    old=records[0]['result_json'];data=dict(records[0]['input_json']);ids=dict(data.get('price_ids',{}));changes=[]
    keys=['source_id','commodity','region','currency','normalized_unit','consumer_class','tax_basis','price_type','gas_volume_basis']
    for role,previous in old['selected_prices'].items():
        candidates=[p for p in store.prices(previous['commodity'],previous['region'],latest=True,
            include_test=data.get('allow_test_prices',False),max_age_days=data.get('max_price_age_days',30)) if all(p[k]==previous[k] for k in keys)]
        current=candidates[0] if len(candidates)==1 else None
        ids[role]=current['id'] if current else previous['id']
        changes.append({'role':role,'previous_id':previous['id'],'current_id':current['id'] if current else None,
            'previous_value':previous['normalized_value'],'current_value':current['normalized_value'] if current else None,
            'validation_status':current['validation_status'] if current else 'UNAVAILABLE'})
    data['price_ids']=ids
    new=compare(store,data,persist=False)
    before={r['scenario']:r for r in old['scenarios']};deltas=[]
    for row in new['scenarios']:
        prior=before[row['scenario']]
        deltas.append({'scenario':row['scenario'],'previous_net_profit':prior['net_profit'],'current_net_profit':row['net_profit'],
            'difference':row['net_profit']-prior['net_profit'] if row['net_profit'] is not None and prior['net_profit'] is not None else None})
    return {'scenario_id':identifier,'previous_recommendation':old.get('final_recommendation',old.get('recommended_scenario')),
        'current_recommendation':new['final_recommendation'],'prices':changes,'profit_changes':deltas,'current':new,
        'message':'Повторный расчёт с прежними физическими параметрами и затратами. Обновлены только цены тех же источников и профилей; сохранённый результат не изменён. '+new['message']}
