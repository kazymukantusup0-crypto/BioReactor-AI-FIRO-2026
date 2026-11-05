"""Reuse A-D ledgers and explicit process energy without duplicate heating charges."""
import math
from src.market.scenarios import ScenarioInput, compare


def evaluate_economics(store, parameters, methane, energy):
    data = dict(parameters.market)
    route = data.pop('comparison_route', None)
    if route is not None and route not in {'A', 'B', 'C', 'D'}:
        raise ValueError('comparison_route must be A, B, C or D')
    extras = {}
    for name, alias in [('feedstock_purchase_cost','feedstock_acquisition_cost'), ('capital_cost','equipment_cost'),
                        ('annual_batches','annual_batches'), ('annual_fixed_cost','annual_fixed_cost')]:
        value, alternate = getattr(parameters,name), data.pop(alias,None)
        if value is not None and alternate is not None and value != alternate:
            raise ValueError('Conflicting process/market '+name)
        value = value if value is not None else alternate
        if value is not None and (isinstance(value,bool) or not isinstance(value,(float,int)) or not math.isfinite(value) or value<0):
            raise ValueError(name+' requires a finite nonnegative number')
        extras[name]=value
    warnings=[]
    if data.get('mass_kg') is None and parameters.mass_kg is not None:data['mass_kg']=parameters.mass_kg
    if data.get('mass_kg') is None and parameters.feedstock_volume_l is not None and parameters.density_kg_l is not None:
        data['mass_kg']=parameters.feedstock_volume_l*parameters.density_kg_l
    if data.get('feedstock_commodity') is None:
        from src.market.domain import COMMODITIES
        if parameters.material in COMMODITIES and COMMODITIES[parameters.material][0]=='organic_feedstock':
            data['feedstock_commodity']=parameters.material
    def unavailable(message):
        return {'status':'needs_input','scenarios':[],'final_recommendation':None,'warnings':[message],'sensitivity':[]}
    if methane.get('potential_methane_m3') is not None:
        if data.get('potential_methane_m3') is not None and not math.isclose(data['potential_methane_m3'],methane['potential_methane_m3'],abs_tol=1e-8):
            return unavailable('Market potential conflicts with process methane potential.')
        data['potential_methane_m3']=methane['potential_methane_m3']
        data.setdefault('gas_volume_basis',methane['gas_volume_basis'])
    for key in ['gas_volume_basis','recovery_fraction','methane_fraction']:
        if data.get(key) is None and getattr(parameters,key) is not None:data[key]=getattr(parameters,key)
    computed=energy.get('total_energy_kwh')
    if computed is not None and parameters.energy_scope=='entire_feedstock':
        if data.get('heating_cost') not in (None,0):
            return unavailable('Modeled electricity includes heating. Set heating_cost=0 explicitly or reconcile the ledger before comparison.')
        if data.get('energy_use_kwh') is not None and not math.isclose(data['energy_use_kwh'],computed,abs_tol=1e-8):
            return unavailable('Explicit market energy and modeled total energy disagree; no silent replacement is allowed.')
        data['energy_use_kwh']=computed
    elif computed is not None:
        warnings.append('Energy scope is not entire_feedstock; single-charge energy is not applied to the whole-lot ledger.')
    if not data.get('region'):warnings.append('Market region is not supplied; no regional price is substituted.')
    try:result=compare(store,ScenarioInput.model_validate(data),persist=False)
    except (ValueError,TypeError) as exc:return unavailable(str(exc))
    result['sensitivity']=[]
    result['sensitivity_policy']='Only explicit v6 ranges; legacy automatic +/-20% is not used.'
    result['comparison_route']=route
    result['warnings']=warnings
    purchase=extras['feedstock_purchase_cost']
    if purchase is None:
        warnings.append('Input acquisition cost is unknown: margins exclude feedstock purchase. Sale A separately represents the owned-feedstock opportunity value.')
    else:
        for row in result['scenarios']:
            if row.get('status')=='ok':
                row['net_before_feedstock_acquisition']=row['net_profit']
                row['feedstock_purchase_cost']=purchase
                row['total_cost']+=purchase
                row['net_profit']-=purchase
    result['payback']={'status':'INSUFFICIENT_DATA','simple_payback_years':None,
        'scope':'Simple incremental payback relative to sale A; excludes discounting, financing, taxes and unprovided replacement costs.'}
    sale=next((r for r in result['scenarios'] if r.get('scenario')=='A' and r.get('status')=='ok'),None)
    processing=next((r for r in result['scenarios'] if r.get('scenario')==route and route in {'B','C','D'} and r.get('status')=='ok'),None)
    if sale and processing and all(extras[k] is not None for k in ['capital_cost','annual_batches','annual_fixed_cost']):
        annual=(processing['net_profit']-sale['net_profit'])*extras['annual_batches']-extras['annual_fixed_cost']
        result['payback'].update(status='CONDITIONAL',annual_incremental_net_cashflow=annual,
            simple_payback_years=extras['capital_cost']/annual if annual>0 else None,
            reason='Annual cycle count is a user scenario, not established reactor capacity.' if annual>0 else 'No positive incremental cash flow; finite payback is not established.')
    if parameters.assumptions or parameters.bmp_provenance=='scenario_assumption':
        result['final_recommendation']=None
        result['is_final_recommendation']=False
        result['recommendation_scope']='explicit_hypothetical_process_inputs_only'
    return result
