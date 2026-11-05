"""Reuse the existing explicit-price calculator, without promoting asks to bids."""
from src.economics.calculator import calculate_profitability,ECONOMIC_FIELDS

def compare_explicit(result,inputs):
    derived={'mass_kg','potential_methane_m3','gas_volume_basis'}
    missing=[k for k in ECONOMIC_FIELDS if k not in derived and (inputs or {}).get(k) is None]
    if missing or result.get('methane_potential_m3') is None or result.get('wet_mass_kg') is None:
        return {'status':'needs_input','missing':missing,'endpoints':[],'final_recommendation':None}
    endpoints=[]
    try:
        for side in ['low','high']:
            data={k:inputs[k] for k in ECONOMIC_FIELDS if k in inputs}
            data.update(mass_kg=result['wet_mass_kg'][side],potential_methane_m3=result['methane_potential_m3'][side],gas_volume_basis=result['gas_reference'])
            endpoints.append({'endpoint':side,**calculate_profitability(data)})
    except (ValueError,TypeError) as exc:return {'status':'invalid_input','message':str(exc),'endpoints':[],'final_recommendation':None}
    return {'status':'ok','endpoints':endpoints,'final_recommendation':None,
            'scope':'Conditional explicit user-price calculation at literature endpoints; no independent quote, gas-sale eligibility or full-cost verification. Storage, transport and digestate costs must be included explicitly in operating_cost. No validated probability coverage.'}
