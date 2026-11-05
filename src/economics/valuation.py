"""Reuse strict market selection; keep reference asks/statistics distinct from contracts."""
from datetime import date
from src.market.domain import market_today
from src.market.domain import COMMODITIES
from src.market.scenarios import ScenarioInput,select_price,PriceUnavailable
from src.economics.gas_composition import compatible

def resolve(store,request,settings,role,gas_basis=None):
    expected={'feedstock':(request.material,'KZT/kg'),'electricity':('electricity','KZT/kWh'),'heat':('useful_heat','KZT/kWh'),'gas_sale':('raw_biogas','KZT/m3'),'digestate':('digestate','KZT/kg')}
    commodity,unit=expected[role]
    q=settings.quotes.get(role)
    if q:
        reasons=[]
        if q.commodity!=commodity or q.unit!=unit:reasons.append('incomparable_commodity_or_unit')
        if q.region!=request.region:reasons.append('region_mismatch')
        if q.published_at is None:reasons.append('publication_date_missing')
        age=(market_today()-q.published_at).days if q.published_at else None
        if age is not None and (age<0 or age>settings.max_price_age_days):reasons.append('future_or_stale_price')
        if role=='feedstock':
            if q.material_state!=request.material_state:reasons.append('material_state_mismatch_or_unconfirmed')
            if q.minimum_batch_kg is not None and (request.mass_kg is None or request.mass_kg<q.minimum_batch_kg):reasons.append('minimum_order_not_met_or_unverified')
        if role=='gas_sale':
            ok,why=compatible(gas_basis,q.gas_basis,settings.assume_reference_compatibility)
            if not ok:reasons.append(why)
        if role=='electricity' and (not settings.consumer_class or q.consumer_class!=settings.consumer_class):reasons.append('consumer_class_unconfirmed_or_mismatch')
        if settings.tax_basis is not None and q.tax_basis!=settings.tax_basis:reasons.append('tax_basis_mismatch_or_unconfirmed')
        return {'status':'unusable' if reasons else 'confirmed' if q.confirmed and request.region_confirmed and (role not in {'feedstock','gas_sale','digestate'} or q.counterparty_confirmed) else 'reference',
                'value':q.value,'unit':q.unit,'commodity':q.commodity,'region':q.region,'published_at':q.published_at.isoformat() if q.published_at else None,
                'source':q.source,'age_days':age,'reasons':reasons,'provenance':'CONFIRMED_PRICE' if not reasons and q.confirmed and request.region_confirmed and (role not in {'feedstock','gas_sale','digestate'} or q.counterparty_confirmed) else 'MARKET_REFERENCE'}
    if role in {'electricity','feedstock','gas_sale','digestate'}:
        try:
            selected=select_price(store,ScenarioInput(region=request.region,feedstock_commodity=request.material if request.material in COMMODITIES else None,consumer_class=settings.consumer_class,tax_basis=settings.tax_basis,
                gas_volume_basis=None,price_ids=settings.price_ids,max_price_age_days=settings.max_price_age_days),role)
            # A wholesale observation is not proof of an available buyer for this batch.
            confirmed=role=='electricity' and request.region_confirmed
            return {'status':'confirmed' if confirmed else 'reference','value':float(selected['normalized_value']),'unit':unit,
                    'source':selected['source_url'],'provenance':'CONFIRMED_PRICE' if confirmed else 'MARKET_REFERENCE','observation':selected,'reasons':[]}
        except PriceUnavailable:pass
    if role=='electricity' and not settings.quotes.get(role) and role not in settings.price_ids:
        rows=[p for p in store.prices('electricity',request.region,latest=True,max_age_days=settings.max_price_age_days) if p['price_type']=='reference' and not p['is_test'] and not p['is_future'] and (not settings.consumer_class or p['consumer_class']==settings.consumer_class) and (not settings.tax_basis or p['tax_basis']==settings.tax_basis)]
        if rows:
            p=max(rows,key=lambda x:x['effective_from'])
            return {'status':'reference','value':float(p['normalized_value']),'unit':unit,'source':p['source_url'],'provenance':'MARKET_REFERENCE','observation':p,
                    'reasons':['Statistical category price, not an individual billing tariff']+(['stale_reference'] if p['is_stale'] else [])}
    return {'status':'missing','value':None,'unit':unit,'provenance':None,'reasons':['no_eligible_quote']}
