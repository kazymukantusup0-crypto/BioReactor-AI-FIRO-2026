"""Algebraic cost budgets are useful even when actual operating costs are unknown."""
from src.economics.energy_conversion import subtract

def calculate(benefit,sale_target,priced_quantity,price,total_cost=None,unit='KZT/kWh'):
    budget=subtract(benefit,sale_target) if benefit is not None and sale_target is not None else None
    minimum_price=None;minimum_energy=None
    if total_cost is not None and sale_target is not None and priced_quantity is not None and priced_quantity['low']>0:
        minimum_price={'low':max(0,(total_cost['low']+sale_target['low'])/priced_quantity['high']),
                       'high':max(0,(total_cost['high']+sale_target['high'])/priced_quantity['low'])}
    if total_cost is not None and sale_target is not None and price is not None and price>0:
        minimum_energy={'low':max(0,(total_cost['low']+sale_target['low'])/price),'high':max(0,(total_cost['high']+sale_target['high'])/price)}
    return {'maximum_total_processing_cost_to_match_sale_kzt':budget,'minimum_product_price':minimum_price,'minimum_product_price_unit':unit,
            'minimum_useful_product_quantity':minimum_energy,
            'condition':'Processing beats the stated sale comparator only if total allocated processing costs are below the corresponding gross-benefit-minus-sale threshold.',
            'formulas':{'cost_budget':'gross benefit - sale net proceeds (or explicitly hypothetical reference asking comparator)',
                        'minimum_price':'(total processing cost + sale comparator) / useful consumed product quantity'},
            'scope':'Deterministic sensitivity thresholds, not guaranteed profit, coverage or evidence that a buyer exists.'}
