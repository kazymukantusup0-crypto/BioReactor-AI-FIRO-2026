"""Twenty additional HTTP experiments. Explicit fixture values are TEST ONLY.

Uses an isolated server/database. Never imports fixture prices into market history.
"""
import sys,json,copy,urllib.request,urllib.error
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import main
from src.market.domain import market_today
URL='http://127.0.0.1:8767'
OUT=Path('reports/stage8_3/http_additional.json')
records=[]
def http(path,data):
    req=urllib.request.Request(URL+path,json.dumps(data).encode(),{'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(req,timeout=120) as r:return r.status,json.load(r)
    except urllib.error.HTTPError as e:return e.code,json.load(e)
def run(name,data,check,status=200):
    code,result=http('/api/advisor/analyze',data)
    row={'id':name,'input':data,'status_code':code,'result':result,'fixture_notice':'TEST ONLY values, not experimental or market observations'}
    try:
        assert code==status,(code,result)
        check(result);row['passed']=True
    except Exception as e:row['passed']=False;row['failure']=str(e)
    records.append(row);OUT.write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
    print(name,row['passed'],row.get('failure','')[:180],flush=True)
    return result
def require(condition):assert condition
def close(a,b):return abs(a-b)<1e-8
def point(v):return {'low':v,'high':v,'provenance':'HYPOTHETICAL_SCENARIO','evidence':'TEST ONLY validation fixture'}
def component(material='food_waste',quantity=6.5,**kw):
    return {'id':'x','material':material,'quantity':quantity,'unit':'kg','data_mode':'MEASURED',
        'properties':{'density_kg_l':1,'ts_fraction':.178,'vs_fraction_wet':.161,'bmp_ml_g_vs':480,
            'gas_basis':{'temperature_k':273.2,'pressure_pa':101325,'moisture':'dry','description':'TEST ONLY'}},**kw}
def body(**kw):return {'components':[component()],**kw}
def methane(r):return r['mixture']['additive_methane_reference_m3']
def electric(r):return next(x for x in r['decision_analysis']['scenarios'] if x['id']=='C_electricity')
def full():
    costs={k:point(2) for k in ['preparation','maintenance','storage','transport','gas_cleaning','digestate_handling','packaging']}
    return body(region='KZ-Karaganda',region_confirmed=True,reactor_total_volume_l=40,decision={
        'consumer_class':'TEST_ONLY','quotes':{'electricity':{'value':25,'unit':'KZT/kWh','commodity':'electricity','region':'KZ-Karaganda','published_at':str(market_today()),'source':'TEST ONLY tariff, not a real price','consumer_class':'TEST_ONLY','confirmed':False}},
        'recovery_fraction':point(.7),'electrical_efficiency':point(.3),'thermal_efficiency':point(.8),
        'assume_full_self_consumption':True,'replacement_heat_source':'electric_resistance','costs':costs,'all_operating_costs_included':True,
        'reactor':{'reactor_working_volume_l':30,'headspace_l':10,'inoculum_volume_l':0,'dilution_water_l':0,'resident_liquid_volume_l':0,'operating_mode':'batch',
            'temperature_c':35,'initial_temperature_c':20,'ambient_temperature_c':20,'heated_mass_kg':6.5,'heat_capacity_kj_kg_k':4,'heat_loss_coefficient_w_k':.05,'duration_days':10,'heater_efficiency':.9,'heating_carrier':'electricity','auxiliary_energy_kwh':.1,'energy_scope':'entire_batch','provenance':'HYPOTHETICAL_SCENARIO'}})
if __name__=='__main__':
    r=run('01_measured_paired_food',body(),lambda r:require(close(methane(r)['low'],6.5*.161*.480)))
    run('02_grams_equivalence',body(components=[component(quantity=6500,unit='g')]),lambda r:require(close(methane(r)['low'],6.5*.161*.480)))
    c=component('swine_manure',17,unit='L');c['properties']['density_kg_l']=point(.7)|{'high':.9}
    run('03_litres_density_bounds',body(components=[c]),lambda r:require(close(methane(r)['low'],17*.7*.161*.480) and close(methane(r)['high'],17*.9*.161*.480)))
    d=body(components=[component(quantity=13,unit='L')],reactor_total_volume_l=38,decision={'reactor':{'operating_mode':'batch','reactor_working_volume_l':28,'inoculum_volume_l':8,'dilution_water_l':10,'resident_liquid_volume_l':0,'headspace_l':10}})
    run('04_working_overflow_not_total',d,lambda r:require(r['engineering']['known_charge_volume_l']['low']==31 and 'known_charge_exceeds_working_volume' in r['engineering']['violations']))
    c=component(quantity=40);c['properties']['density_kg_l']=point(.5)|{'high':1}
    run('05_possible_overflow_range',body(components=[c],reactor_total_volume_l=65,decision={'reactor':{'operating_mode':'batch'}}),lambda r:require(not r['engineering']['violations'] and bool(r['engineering']['warnings'])))
    d=body(components=[component(quantity=120,unit='L')],reactor_total_volume_l=80,feeding_period_days=10,total_daily_liquid_feed_l=12,daily_feed_includes_all_liquid=True,decision={'reactor':{'operating_mode':'continuous','reactor_working_volume_l':60}})
    run('06_continuous_HRT_OLR',d,lambda r:require(close(r['duration']['estimated_hrt_from_declared_feed_days']['low'],5) and close(r['mixture']['olr_kg_vs_m3_day']['low'],120*.161/10/.06)))
    d['decision']['reactor']['operating_mode']='batch'
    run('07_batch_not_daily_OLR',d,lambda r:require(r['mixture']['olr_kg_vs_m3_day'] is None and r['engineering']['status']=='PHYSICALLY_INFEASIBLE'))
    d=body(components=[component(quantity=30)],target_ts_fraction=.08,decision={'reactor':{'dilution_water_l':10}})
    run('08_target_TS_water_mass',d,lambda r:require(close(r['engineering']['additional_water_to_target_ts_kg']['low'],30*.178/.08-40)))
    d=full();d['decision']['reactor']['heated_mass_kg']=2
    run('09_inconsistent_heated_mass',d,lambda r:require(electric(r)['net_result_kzt'] is None))
    baseline=run('10_complete_economic_scenario',full(),lambda r:require(electric(r)['net_result_kzt'] is not None and electric(r)['evidence_confirmed'] is False))
    d=full();d['decision']['costs']['preparation']=point(12)
    run('11_cost_sensitivity_delta',d,lambda r:require(close(electric(r)['net_result_kzt']['low'],electric(baseline)['net_result_kzt']['low']-10)))
    d=full();d['decision']['quotes']['electricity']['value']=30
    run('12_tariff_sensitivity_delta',d,lambda r:require(close(electric(r)['net_result_kzt']['low']+14,(electric(baseline)['net_result_kzt']['low']+14)*1.2)))
    d=full();d['decision']['reactor']['temperature_c']=40
    run('13_temperature_heat_demand',d,lambda r:require(r['decision_analysis']['reactor_balance']['heating_input_kwh']>baseline['decision_analysis']['reactor_balance']['heating_input_kwh'] and methane(r)==methane(baseline)))
    d=full();d['decision']['reactor']['auxiliary_energy_kwh']=10
    run('14_negative_net_energy',d,lambda r:require(electric(r)['net_electricity_balance_kwh']['high']<0 and electric(r)['net_result_kzt']['high']<0))
    c=component();c['properties']['gas_basis']['moisture']='wet'
    run('15_wet_gas_blocks_energy',body(components=[c]),lambda r:require(methane(r) is not None and not r['decision_analysis']['energy']['outputs']))
    run('16_explicit_TS_without_VS',body(allow_conditional_profiles=True,components=[{'id':'c','material':'food_waste','quantity':4,'properties':{'ts_fraction':.4}}]),lambda r:require(methane(r) is None))
    run('17_compost_no_fresh_transfer',body(allow_conditional_profiles=True,components=[{'id':'c','material':'cattle_manure','quantity':18,'decay_state':'composted'}]),lambda r:require(methane(r) is None))
    c=component();c['properties']['vs_fraction_wet']=.8
    run('18_VS_exceeds_TS_rejected',body(components=[c]),lambda r:require('detail' in r),status=422)
    run('19_unknown_material_measured_only',body(components=[component('other_organic',2.25)]),lambda r:require(close(methane(r)['low'],2.25*.161*.480)))
    data=full();code,handoff=http('/api/advisor/handoff',{'request':data,'mode':'offline'})
    req=urllib.request.Request(URL+'/api/dashboard/chat/sessions/'+handoff['session_id'])
    with urllib.request.urlopen(req) as resp:session=json.load(resp)
    from src.advisor.schemas import AdvisorRequest
    canonical=AdvisorRequest.model_validate(data).model_dump(mode='json')
    memory=session['memory']
    preserved=(memory['decision_settings']==canonical['decision'] and memory['mixture_components']==canonical['components']
        and memory['advanced']['request_overrides']['reactor_total_volume_l']==40)
    records.append({'id':'20_handoff_exact_decision_context','status_code':code,'input':data,'response':session,'handoff':handoff,'passed':code==201 and preserved,'fixture_notice':'TEST ONLY isolated session; complete canonical decisions/components and reactor volume compared, not only HTTP status'})
    OUT.write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
    print('PASSED',sum(r['passed'] for r in records),'OF',len(records),flush=True)
    raise SystemExit(0 if all(r['passed'] for r in records) else 1)
