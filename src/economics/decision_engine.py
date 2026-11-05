"""Statuses derive from structured bounds, geometry and evidence, never LLM prose."""
def decide(feasibility,rows,gas_use,has_methane,sale_reference=None):
    if feasibility['status']=='PHYSICALLY_INFEASIBLE':return {'status':'PHYSICALLY_INFEASIBLE','selected_scenario':None,'reason':'Declared simultaneous charge violates geometry; a different staged plan is not assessed here.'}
    if feasibility['status']=='REQUIRES_SAFETY_REVIEW':return {'status':'REQUIRES_SAFETY_REVIEW','selected_scenario':None,'reason':'Declared engineering safety review is outstanding.'}
    eligible={'heat':{'B_heat'},'electricity':{'C_electricity'},'chp':{'CHP'},'sell_gas':{'D_sell_gas'},'unknown':{'B_heat','C_electricity','CHP','D_sell_gas','E_digestate'}}[gas_use]
    sale=next(r for r in rows if r['id']=='A_sell_feedstock');sale_net=sale.get('net_result_kzt') or sale_reference or sale.get('reference_asking_value_kzt')
    candidates=[r for r in rows if r['id'] in eligible and r.get('net_result_kzt') is not None]
    complete=all(any(r['id']==name and (r.get('net_result_kzt') is not None or r.get('status')=='ineligible') for r in rows) for name in eligible)
    if candidates and sale_net is not None:
        best=max(candidates,key=lambda r:sum(r['net_result_kzt'].values()))
        n=best['net_result_kzt'];verified=best['evidence_confirmed'] and sale['evidence_confirmed'] and sale.get('net_result_kzt') is not None and feasibility['status']=='GEOMETRICALLY_CONSISTENT' and feasibility['engineering_review_confirmed']
        if n['low']>sale_net['high']:status='PROCESSING_PREFERRED' if verified else 'CONDITIONALLY_PROCESSING_PREFERRED'
        elif sale_net['low']>max(r['net_result_kzt']['high'] for r in candidates):status='SELLING_PREFERRED' if verified and complete else 'CONDITIONALLY_SELLING_PREFERRED'
        else:status='CONDITIONALLY_PROCESSING_PREFERRED' if sum(n.values())>sum(sale_net.values()) else 'CONDITIONALLY_SELLING_PREFERRED'
        return {'status':status,'selected_scenario':best['id'],'reason':'Compared explicit net-result sensitivity bounds; overlapping ranges remain conditional. Missing candidate scenarios are excluded, not assumed unprofitable.','comparison_complete':complete,'operating_approval':False}
    budgets=[r for r in rows if r['id'] in eligible and r.get('break_even',{}).get('maximum_total_processing_cost_to_match_sale_kzt') is not None]
    if has_methane and budgets:
        best=max(budgets,key=lambda r:r['break_even']['maximum_total_processing_cost_to_match_sale_kzt']['low'])
        budget=best['break_even']['maximum_total_processing_cost_to_match_sale_kzt']
        return {'status':'CONDITIONALLY_PROCESSING_PREFERRED' if budget['low']>0 else 'CONDITIONALLY_SELLING_PREFERRED' if budget['high']<0 else 'INSUFFICIENT_EVIDENCE',
                'selected_scenario':best['id'],'reason':'Only a conditional cost-budget comparison is available; actual net profit, buyer and technical feasibility remain unconfirmed.',
                'required_total_cost_below_kzt':budget,'comparison_complete':False,'operating_approval':False}
    return {'status':'INSUFFICIENT_EVIDENCE','selected_scenario':None,'reason':'No eligible comparable price/energy result; break-even formulas and missing inputs are retained.','operating_approval':False}
