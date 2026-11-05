"""v7.5 energy allocation, transaction economics and deterministic decisions."""
import json
from src.data.prepare import ROOT
from src.economics.decision_schemas import DecisionInputs
from src.economics import gas_composition,energy_conversion,reactor_balance,feasibility,valuation,break_even,decision_engine
from src.economics.energy_conversion import pair,scale,add,subtract,bounds

BASE_COSTS=['preparation','maintenance','storage','transport','gas_cleaning','digestate_handling','packaging']
SALE_COSTS=['sale_transport','sale_storage','sale_packaging']

def cost_sum(settings,keys,allocate_capital=False):
    missing=[k for k in keys if k not in settings.costs];total=pair(0)
    for key in keys:
        if key in settings.costs:total=add(total,bounds(settings.costs[key]))
    if settings.include_capital and allocate_capital:
        if settings.capital_cost_per_batch is None:missing.append('capital_cost_per_batch')
        else:total=add(total,bounds(settings.capital_cost_per_batch))
    return {'complete_total':None if missing else total,'known_subtotal':total,'missing':missing}

def cap(r,demand):return {'low':min(max(0,r['low']),demand),'high':min(max(0,r['high']),demand)} if demand is not None else {'low':max(0,r['low']),'high':max(0,r['high'])}

def analyze(store,request,result):
    s=request.decision or DecisionInputs()
    # For min-order comparability only, use a conservative mass endpoint; never rewrite user inputs.
    quote_request=request.model_copy(update={'mass_kg':result['wet_mass_kg']['low']}) if result.get('wet_mass_kg') else request
    gas=gas_composition.resolve(result,request,s);energy=energy_conversion.resolve(result,s)
    reactor=reactor_balance.calculate(s.reactor);geometry=feasibility.evaluate(request,s.reactor)
    if result.get('engineering'):
        e=result['engineering']
        geometry.update(status=e['status'],violations=e['violations'],unknown=e['missing'],
            known_charge_min_l=e['known_charge_volume_l']['low'],engineering=e)
    mass_scope_consistent=True
    if s.reactor.energy_scope=='entire_batch' and s.reactor.heated_mass_kg is not None and result.get('wet_mass_kg'):
        mass_scope_consistent=s.reactor.heated_mass_kg+1e-9>=result['wet_mass_kg']['high']
        if not mass_scope_consistent:reactor['warnings'].append('Declared heated mass is below the entire feedstock mass; this energy balance cannot price the entire batch.')
    reactor['mass_scope_consistent']=mass_scope_consistent
    prices={role:valuation.resolve(store,quote_request,s,role,gas.get('gas_basis')) for role in ['electricity','heat','feedstock','gas_sale','digestate']}
    def price(role):return prices[role]['value'] if prices[role]['status'] not in {'missing','unusable'} else None
    def gross(quantity,role):return scale(quantity,price(role)) if quantity is not None and price(role) is not None else None
    sale_cost=cost_sum(s,SALE_COSTS);base_cost=cost_sum(s,BASE_COSTS,True)
    sale_revenue=gross(result.get('wet_mass_kg'),'feedstock')
    sale_net=subtract(sale_revenue,sale_cost['complete_total']) if sale_revenue and sale_cost['complete_total'] is not None and prices['feedstock']['status']=='confirmed' else None
    reference=result.get('catalog_reference_value_kzt')
    comparator=sale_net or reference or sale_revenue
    comparator_basis='CONFIRMED_BUYER_NET' if sale_net else 'REFERENCE_ASKING_VALUE_WITH_UNKNOWN_TRANSACTION_COSTS' if comparator else 'UNAVAILABLE'
    rows=[{'id':'A_sell_feedstock','status':'ok' if sale_net else 'reference_only' if comparator else 'needs_input',
           'reference_asking_value_kzt':reference,'confirmed_buyer_gross_offer_kzt':sale_revenue if prices['feedstock']['status']=='confirmed' else None,
           'transaction_costs':sale_cost,'net_result_kzt':sale_net,'evidence_confirmed':sale_net is not None,
           'missing':sale_cost['missing']+([] if prices['feedstock']['status']=='confirmed' else ['confirmed_comparable_buyer_offer'])}]
    outputs=energy['outputs'];balanced=reactor['status']=='ok' and reactor['scope_valid_for_batch'] and mass_scope_consistent and s.reactor.operating_mode!='continuous' and reactor['electricity_input_kwh'] is not None
    electricity_draw=reactor['electricity_input_kwh'] if balanced else None
    heat_draw=reactor['process_heat_draw_kwh'] if balanced else None
    if not balanced:reactor['allocation_notice']='No complete matching entire-batch balance; energy costs are unknown, not zero. Gross energy and total-cost break-even remain scenario bounds.'
    heat_price=price('heat');electric_price=price('electricity')
    heat_reference=s.replacement_heat_source=='electric_resistance' or s.replacement_heat_source=='unknown' and s.use_reference_scenarios
    if heat_price is None and heat_reference:heat_price=electric_price
    full_use=s.assume_full_self_consumption or s.use_reference_scenarios
    for kind,heat_key,electric_key in [('B_heat','heat_only_kwh',None),('C_electricity',None,'electricity_only_kwh'),('CHP','chp_heat_kwh','chp_electricity_kwh')]:
        h=outputs.get(heat_key) if heat_key else None;e=outputs.get(electric_key) if electric_key else None
        conditional=[]
        if full_use and (h and s.heat_demand_kwh is None or e and s.electricity_demand_kwh is None):conditional.append('Full external self-consumption assumed; not a confirmed demand')
        h_used=cap(h,s.heat_demand_kwh) if h and (s.heat_demand_kwh is not None or full_use) else None
        e_used=cap(e,s.electricity_demand_kwh) if e and (s.electricity_demand_kwh is not None or full_use) else None
        gross_h=scale(h_used,heat_price) if h_used is not None and heat_price is not None else pair(0) if h is None else None
        gross_e=scale(e_used,electric_price) if e_used is not None and electric_price is not None else pair(0) if e is None else None
        benefit=add(gross_h,gross_e) if gross_h is not None and gross_e is not None and (h is not None or e is not None) else None
        if h and price('heat') is None and heat_reference:conditional.append('Heat valuation assumes displaced electric resistance heating at the electricity reference price (100% resistance efficiency)')
        total_cost=None;net=None;energy_cost=None;useful_heat=h_used;useful_electricity=e_used
        if balanced and outputs:
            # Subtract process heat from heat output once; electrical internal demand from generation once.
            net_h=subtract(h,pair(heat_draw)) if h is not None and heat_draw is not None else None
            net_e=subtract(e,pair(electricity_draw)) if e is not None else None
            useful_heat=cap(net_h,s.heat_demand_kwh) if net_h is not None and (s.heat_demand_kwh is not None or full_use) else None
            useful_electricity=cap(net_e,s.electricity_demand_kwh) if net_e is not None and (s.electricity_demand_kwh is not None or full_use) else None
            adjusted_h=scale(useful_heat,heat_price) if useful_heat is not None and heat_price is not None else pair(0) if h is None and not heat_draw else None
            adjusted_e=scale(useful_electricity,electric_price) if useful_electricity is not None and electric_price is not None else pair(0) if e is None else None
            if e is None:electrical_import=pair(electricity_draw)
            else:electrical_import={'low':max(0,electricity_draw-e['high']),'high':max(0,electricity_draw-e['low'])}
            thermal_import={'low':max(0,(heat_draw or 0)-(h['high'] if h else 0)),'high':max(0,(heat_draw or 0)-(h['low'] if h else 0))}
            if s.reactor.heating_carrier=='external_heat' and reactor['heating_input_kwh'] is not None:thermal_import=pair(reactor['heating_input_kwh'])
            ec=scale(electrical_import,electric_price) if electric_price is not None else pair(0) if electrical_import['high']==0 else None
            hc=scale(thermal_import,heat_price) if heat_price is not None else pair(0) if thermal_import['high']==0 else None
            energy_cost=add(ec,hc) if ec is not None and hc is not None else None
            if base_cost['complete_total'] is not None and energy_cost is not None and adjusted_h is not None and adjusted_e is not None and s.all_operating_costs_included:
                total_cost=add(base_cost['complete_total'],energy_cost);net=subtract(add(adjusted_h,adjusted_e),total_cost)
        quantity=h_used if kind=='B_heat' else e_used if kind=='C_electricity' else None
        unit_price=heat_price if kind=='B_heat' else electric_price if kind=='C_electricity' else None
        threshold=break_even.calculate(benefit,comparator,quantity,unit_price,total_cost)
        # A changing electricity tariff also prices internal imports. Solve with a
        # signed energy slope instead of treating that price-dependent cost as fixed.
        if balanced and comparator is not None and base_cost['complete_total'] is not None and kind!='CHP':
            def signed_consumption(generated,draw,demand):
                def f(x):return min(x-draw,demand) if demand is not None and x>=draw else x-draw
                return {side:f(generated[side]) for side in ['low','high']}
            fixed=base_cost['complete_total'];slope=None
            if kind=='C_electricity' and e is not None:
                slope=signed_consumption(e,electricity_draw,s.electricity_demand_kwh)
                if heat_price==electric_price and heat_reference:slope=subtract(slope,thermal_import)
                elif heat_price is not None:fixed=add(fixed,scale(thermal_import,heat_price))
                elif thermal_import['high']>0:slope=None
            elif kind=='B_heat' and h is not None:
                slope=subtract(cap(subtract(h,pair(heat_draw)),s.heat_demand_kwh),thermal_import)
                if price('heat') is None and heat_reference:slope=subtract(slope,electrical_import)
                elif electric_price is not None:fixed=add(fixed,scale(electrical_import,electric_price))
                elif electrical_import['high']>0:slope=None
            threshold['minimum_product_price']=({'low':max(0,(fixed['low']+comparator['low'])/slope['high']),
                'high':max(0,(fixed['high']+comparator['high'])/slope['low'])} if slope is not None and slope['low']>0 else None)
            threshold['signed_energy_price_slope_kwh']=slope
            threshold['minimum_price_formula']='(non-price costs + sale comparator) / signed useful-energy price slope; internal consumption is counted once'
        if balanced and comparator and base_cost['complete_total'] is not None and outputs and electric_price is not None:
            fuel=outputs['potential_fuel_kwh'];parameters=energy['parameters']
            eta_h=parameters['thermal_efficiency' if kind=='B_heat' else 'chp_thermal_efficiency'] if h is not None else pair(0)
            eta_e=parameters['electrical_efficiency' if kind=='C_electricity' else 'chp_electrical_efficiency'] if e is not None else pair(0)
            unit_h=energy_conversion.multiply(fuel,bounds(eta_h));unit_e=energy_conversion.multiply(fuel,bounds(eta_e))
            not_capped=(h is None or s.heat_demand_kwh is None and full_use or s.heat_demand_kwh is not None and s.heat_demand_kwh>=unit_h['high']) and (e is None or s.electricity_demand_kwh is None and full_use or s.electricity_demand_kwh is not None and s.electricity_demand_kwh>=unit_e['high'])
            if not_capped and (h is None or heat_price is not None):
                per_recovery=add(scale(unit_h,heat_price or 0),scale(unit_e,electric_price))
                thermal_cost=(heat_draw or 0)+(reactor['heating_input_kwh'] if s.reactor.heating_carrier=='external_heat' else 0)
                fixed=add(base_cost['complete_total'],pair(electricity_draw*electric_price+thermal_cost*(heat_price or 0)))
                if per_recovery['low']>0 and (thermal_cost==0 or heat_price is not None):threshold['minimum_recovery_fraction_sensitivity']={'low':(comparator['low']+fixed['low'])/per_recovery['high'],'high':(comparator['high']+fixed['high'])/per_recovery['low']}
        rows.append({'id':kind,'status':'conditional' if net is not None else 'gross_reference_only' if benefit is not None else 'needs_input',
            'gross_heat_kwh':h,'gross_electricity_kwh':e,'useful_heat_after_internal_use_kwh':useful_heat if balanced else None,'useful_electricity_after_internal_use_kwh':useful_electricity if balanced else None,
            'net_heat_balance_kwh':net_h if balanced and outputs else None,'net_electricity_balance_kwh':net_e if balanced and outputs else None,
            'gross_benefit_reference_kzt':benefit,'reactor_energy_cost_kzt':energy_cost,'total_cost_kzt':total_cost,'net_result_kzt':net,
            'break_even':threshold,'comparison_basis':comparator_basis,'evidence_confirmed':bool(net is not None and sale_net is not None and energy['result_level']=='MEASURED' and s.reactor.provenance=='MEASURED' and all(prices[k]['status']=='confirmed' for k in ['electricity']+(['heat'] if h else [])) and not conditional),
            'assumptions':conditional,'missing':base_cost['missing']+([] if balanced else ['complete_entire_batch_reactor_energy_balance'])+([] if s.all_operating_costs_included else ['confirm_all_operating_costs_included']),
            'price_sensitivity':{'minus_20_percent_gross_kzt':scale(benefit,.8),'plus_20_percent_gross_kzt':scale(benefit,1.2)} if benefit is not None else None})
    gas_eligible=all([s.gas_sale_technical_confirmed,s.gas_sale_legal_confirmed,s.gas_quality_confirmed,s.gas_storage_transport_confirmed]) and prices['gas_sale']['status']=='confirmed'
    gas_revenue=None;gas_net=None;gas_cost=None;recovered=None
    if gas_eligible and gas.get('potential_biogas_m3') and energy['parameters'].get('recovery_fraction'):
        recovered=energy_conversion.multiply(gas['potential_biogas_m3'],bounds(energy['parameters']['recovery_fraction']))
        gas_revenue=gross(recovered,'gas_sale')
        gc=cost_sum(s,BASE_COSTS+['gas_sale_transport'],True)
        if gc['complete_total'] is not None and balanced and price('electricity') is not None and s.all_operating_costs_included and s.reactor.heating_carrier=='electricity':
            gas_cost=add(gc['complete_total'],pair(reactor['electricity_input_kwh']*price('electricity')));gas_net=subtract(gas_revenue,gas_cost)
    rows.append({'id':'D_sell_gas','status':'conditional' if gas_revenue is not None else 'needs_input','revenue_kzt':gas_revenue,'net_result_kzt':gas_net,'total_cost_kzt':gas_cost,'evidence_confirmed':False,
                 'break_even':break_even.calculate(gas_revenue,comparator,recovered,price('gas_sale'),gas_cost,'KZT/m3 raw biogas'),
                 'missing':[] if gas_eligible else ['confirmed_raw_biogas_buyer_quote_composition_quality_storage_transport_and_technical_legal_conditions'],
                 'notice':'Natural gas tariffs never value raw biogas sales; no implied storage/pressure operation.'})
    digestate_eligible=s.digestate_quality_confirmed and s.digestate_market_allowed and s.digestate_mass_kg is not None and prices['digestate']['status']=='confirmed'
    digestate_revenue=gross(pair(s.digestate_mass_kg),'digestate') if digestate_eligible else None
    dc=cost_sum(s,BASE_COSTS+['digestate_transport'],True);digestate_net=None;digestate_cost=None
    if digestate_revenue is not None and dc['complete_total'] is not None and balanced and electric_price is not None and s.reactor.heating_carrier=='electricity' and s.all_operating_costs_included:
        digestate_cost=add(dc['complete_total'],pair(electricity_draw*electric_price));digestate_net=subtract(digestate_revenue,digestate_cost)
    rows.append({'id':'E_digestate','status':'conditional' if digestate_revenue else 'needs_input','revenue_kzt':digestate_revenue,'net_result_kzt':digestate_net,'total_cost_kzt':digestate_cost,'evidence_confirmed':False,'missing':[] if digestate_eligible else ['digestate_mass_quality_market_eligibility_and_buyer_offer'],
                 'break_even':break_even.calculate(digestate_revenue,comparator,pair(s.digestate_mass_kg) if digestate_eligible else None,price('digestate'),digestate_cost,'KZT/kg digestate'),
                 'notice':'Standalone product alternative. Digestate income is not added to the gas/energy alternatives.'})
    decision=decision_engine.decide(geometry,rows,s.gas_use,result.get('methane_potential_m3') is not None,comparator)
    references=json.loads((ROOT/'data/research/decision_references.json').read_text(encoding='utf-8'))
    if gas.get('potential_biogas_m3') and energy['parameters'].get('recovery_fraction'):
        gas['recoverable_biogas_scenario_m3']=energy_conversion.multiply(gas['potential_biogas_m3'],bounds(energy['parameters']['recovery_fraction']))
        gas['recovery_notice']='Conditional collected volume under selected recovery; distinct from laboratory potential and not a measured reactor output.'
    partial={'energy_available':bool(energy['outputs']),
             'gross_valuations_available':[r['id'] for r in rows if r.get('gross_benefit_reference_kzt') is not None],
             'net_results_available':[r['id'] for r in rows if r.get('net_result_kzt') is not None],
             'missing_costs':base_cost['missing'],
             'unknown_costs_are_zero':False,
             'unpriced_energy_formula':'value_KZT = eligible_energy_kWh * applicable_price_KZT_per_kWh; gross value before costs'}
    return {'version':'7.5','partial_economics':partial,'biogas':gas,'energy':energy,'reactor_balance':reactor,'feasibility':geometry,'prices':prices,'scenarios':rows,'decision':decision,
            'sale_comparator':{'value_kzt':comparator,'basis':comparator_basis},'operating_costs':base_cost,
            'illustrative_reactor_energy_cases':reactor_balance.illustrative_cases(result['wet_mass_kg']['low'] if result.get('wet_mass_kg') else None) if s.use_reference_scenarios else [],
            'assumptions':energy['assumed_parameters']+gas['assumptions'],'references':references['sources'],
            'capital_cost_included':s.include_capital,'capital_scope':'Explicit allocated capital cost included' if s.include_capital else 'Operating comparison only; capital cost excluded, not silently assumed paid off',
            'double_counting_policy':'A/B/C/CHP/D/E are alternatives. Only CHP heat and electricity share a split fuel stream. Reactor internal heat/electric consumption is subtracted once; gas and digestate income not added to energy.'}
