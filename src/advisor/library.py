"""Append-only named mixture versions and lossless, typed chat handoff."""
import json,uuid
from fastapi import HTTPException
from src.market.domain import utcnow

def initialize(store):
    with store.connect() as con:con.executescript('''
      CREATE TABLE IF NOT EXISTS advisor_saved_mixtures(
        mixture_id TEXT NOT NULL,revision INTEGER NOT NULL,name TEXT NOT NULL,
        created_at TEXT NOT NULL,request_json TEXT NOT NULL,display_units_json TEXT NOT NULL,
        PRIMARY KEY(mixture_id,revision));
    ''')

def decoded(row):
    return {'mixture_id':row['mixture_id'],'revision':row['revision'],'name':row['name'],'created_at':row['created_at'],'request':json.loads(row['request_json']),'display_units':json.loads(row['display_units_json'])}

def save(store,body):
    identifier=body.mixture_id or uuid.uuid4().hex;payload=body.request.model_dump_json();units=json.dumps(body.display_units,sort_keys=True)
    with store.connect() as con:
        con.execute('BEGIN IMMEDIATE')
        prior=con.execute('SELECT * FROM advisor_saved_mixtures WHERE mixture_id=? ORDER BY revision DESC LIMIT 1',(identifier,)).fetchone()
        if body.mixture_id and prior is None:raise HTTPException(404,'Saved mixture not found')
        if prior and prior['request_json']==payload and prior['display_units_json']==units and prior['name']==body.name:return {**decoded(prior),'deduplicated':True}
        revision=prior['revision']+1 if prior else 1
        con.execute('INSERT INTO advisor_saved_mixtures VALUES(?,?,?,?,?,?)',(identifier,revision,body.name,utcnow().isoformat(),payload,units))
        row=con.execute('SELECT * FROM advisor_saved_mixtures WHERE mixture_id=? AND revision=?',(identifier,revision)).fetchone()
    return {**decoded(row),'deduplicated':False}

def listing(store):
    with store.connect() as con:rows=con.execute('SELECT m.* FROM advisor_saved_mixtures m WHERE revision=(SELECT MAX(revision) FROM advisor_saved_mixtures WHERE mixture_id=m.mixture_id) ORDER BY created_at DESC').fetchall()
    return {'mixtures':[decoded(row) for row in rows]}

def load(store,identifier,revision=None):
    with store.connect() as con:
        row=con.execute('SELECT * FROM advisor_saved_mixtures WHERE mixture_id=? '+('AND revision=?' if revision else 'ORDER BY revision DESC LIMIT 1'),(identifier,revision) if revision else (identifier,)).fetchone()
    if row is None:raise HTTPException(404,'Saved mixture/version not found')
    return decoded(row)

def handoff(store,body):
    from src.dashboard.service import initialize as dashboard_initialize
    from src.agent.dialogue_memory import from_context
    dashboard_initialize(store)
    identifier=uuid.uuid4().hex;now=utcnow().isoformat();r=body.request
    state=from_context({},identifier);state.version='7';state.decision_settings=r.decision.model_dump(mode='json')
    from src.agent.dialogue_memory import fact
    if r.region_confirmed:
        state.facts['market_region']=fact(r.region,evidence='Confirmed region transferred from the substrate calculator')
    else:
        state.assumptions['market_region']=fact(r.region,provenance='ASSUMED_FOR_SCENARIO',evidence='Region transferred from the substrate calculator without user confirmation')
    if r.reactor_total_volume_l is not None:
        state.facts['reactor_total_volume_l']=fact(r.reactor_total_volume_l,'L',evidence='Nominal reactor volume transferred from the substrate calculator')
    inventory=[c.model_dump(mode='json') for c in r.components];state.mixture_components=inventory
    overrides=r.model_dump(mode='json',exclude={'components','decision','online'})
    state.advanced={'inventory':inventory,'origin':'mixture_builder','preferences':{},'request_overrides':overrides,'reactor':{'total_volume_l':r.reactor_total_volume_l} if r.reactor_total_volume_l else {},'task':{'id':uuid.uuid4().hex,'original_text':'Состав передан из конструктора с измерениями и допущениями','goals':['gas','heat','electricity','economics'],'status':{g:'pending' for g in ['gas','heat','electricity','economics']}}}
    with store.connect() as con:con.execute('INSERT INTO dashboard_sessions(id,created_at,mode,context_json,history_json,pending_json,conversation_version,conversation_state_json) VALUES(?,?,?,?,?,?,?,?)',(identifier,now,body.mode,'{}','[]','[]','7',state.model_dump_json()))
    return {'session_id':identifier,'component_count':len(inventory),'message':'Состав и свойства переданы без округления или замены профилей','suggested_question':'Оцени экономику этой смеси: продажа сырья или переработка?'}
