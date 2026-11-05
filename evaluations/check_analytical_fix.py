"""Acceptance checks on saved, unmocked Qwen/HTTP responses."""
import json,sys,math
from pathlib import Path


def check(path):
    artifact=json.loads(Path(path).read_text(encoding='utf-8'))
    assert artifact['status']=='complete'
    assert len(artifact['cases'])==7
    checks=[]
    for case in artifact['cases']:
        for i,turn in enumerate(case['turns']):
            r=turn['response'];meta=r['technical_metadata'];tools={t['tool']:t['result'] for t in r['tools']}
            assert r['mode']=='qwen_autonomous_tools',(case['id'],r['mode'])
            assert any(p.get('actual_generation') and p['model']=='qwen3:8b' for p in r['provider_status'])
            assert meta['numeric_claims_grounded'],case['id']
            assert not meta['analytical_unchecked_tools'],case['id']
            assert all(v['status']!='error' for v in tools.values()),case['id']
            assert r['answer'].count('?')<=1
            science=tools.get('assess_substrate_potential',{})
            scenarios=science.get('scenarios',[])
            for s in scenarios:
                assert s['result_level']=='HYPOTHETICAL_SCENARIO'
                assert s['assumptions']
                assert s['methane_m3'] is not None
                independently_summed=0
                for c in s['components']:
                    assert c['source']['url']
                    vs=c['properties_used']['vs_fraction_wet']['range']['low']*c['wet_mass_kg']['low']
                    bmp=c['properties_used']['bmp_ml_g_vs']['range']['low']
                    basis=c['gas_basis']
                    if basis:
                        independently_summed+=vs*bmp*.001*basis['pressure_pa']/101325*273.2/basis['temperature_k']
                    else:
                        assert c['source_stp_claimed'] and s['request']['assume_common_dry_gas_basis']
                        independently_summed+=vs*bmp*.001  # Explicit STP-transfer scenario; no invented conversion factor.
                assert math.isclose(s['methane_m3']['low'],independently_summed,rel_tol=1e-9)
            econ=tools.get('evaluate_partial_economics')
            if econ:
                assert not econ['profit_established']
                for row in econ['scenarios']:
                    a=row['analysis']
                    assert a['partial_economics']['unknown_costs_are_zero'] is False
                    assert all(s['net_result_kzt'] is None for s in a['scenarios'])
                    assert a['energy']['outputs']['potential_fuel_kwh']['low']>0
                    for price in a['prices'].values():
                        assert not price.get('observation',{}).get('is_test',False)
                    assert next(s for s in a['scenarios'] if s['id']=='D_sell_gas')['revenue_kzt'] is None
            name=case['id']
            if name in {'food_economics','income','water_context'}:
                assert econ
                assert math.isclose(scenarios[0]['methane_m3']['low'],.3181407248764415)
                assert scenarios[0]['wet_mass_kg']['low']==5
                assert 'Прибыль и окупаемость не установлены' in r['answer']
            if name=='food_economics':
                assert science['reactor_total_volume_l']==90
                assert '90 л' in r['answer']
            if name=='pig_biogas':
                assert len(scenarios)>=2
                assert all(s['wet_mass_kg']['low']==8 and s['biogas']['potential_biogas_m3'] is None for s in scenarios)
                assert 'без доли метана' in r['answer']
            if name=='alternatives':
                assert science['comparison_mode']=='alternatives'
                assert all(len(s['components'])==1 and s['wet_mass_kg']['low']==10 for s in scenarios)
                assert econ['potential_dominates_other_material_scenarios']==['Пищевые отходы']
            if name=='temperature':
                assert tools['assess_process_evidence']['temperature_c']==30
                assert tools['assess_process_evidence']['sources']
                assert not r['actuator_access']
            if name=='addition':
                assert all(s['wet_mass_kg']['low']==7 and len(s['components'])==2 for s in scenarios)
                assert [(c['quantity'],c['material']) for c in r['memory']['mixture_components']]==[(5,'food_waste'),(2,'poultry_manure')]
            if name=='water_context' and i==1:
                assert science['reactor_total_volume_l']==90
                process=tools['assess_process_evidence']
                assert process['dilution_water_l']==10 and process['added_water_methane_potential_m3']==0
                assert r['memory']['facts']['quantity']['value']==5
                assert r['memory']['facts']['unit']['value']=='kg'
            checks.append({'case':name,'turn':i,'status':'passed','tools':list(tools),'seconds':round(turn['latency_seconds'],3)})
    report={'artifact':str(path),'checks':checks,'passed':len(checks),'failed':0}
    Path(path).with_suffix('.checks.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report


if __name__=='__main__':
    print(json.dumps(check(sys.argv[1]),ensure_ascii=False,indent=2))
