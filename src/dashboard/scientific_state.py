"""Versioned scientific layers, separate from history, saved scenarios and drafts."""
import json
from src.market.domain import utcnow


def initialize(store):
    with store.connect() as con:
        columns={r['name'] for r in con.execute('PRAGMA table_info(dashboard_sessions)')}
        if 'state_version' not in columns:con.execute('ALTER TABLE dashboard_sessions ADD COLUMN state_version INTEGER NOT NULL DEFAULT 0')
        con.executescript('''
        CREATE TABLE IF NOT EXISTS scientific_tasks(id TEXT PRIMARY KEY,conversation_id TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,revision INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS scientific_task_versions(task_id TEXT NOT NULL,revision INTEGER NOT NULL,state_json TEXT NOT NULL,created_at TEXT NOT NULL,PRIMARY KEY(task_id,revision));
        CREATE TABLE IF NOT EXISTS scientific_fields(task_id TEXT NOT NULL,revision INTEGER NOT NULL,layer TEXT NOT NULL,field TEXT NOT NULL,value_json TEXT NOT NULL,provenance TEXT NOT NULL,updated_at TEXT NOT NULL,source_json TEXT NOT NULL,PRIMARY KEY(task_id,revision,layer,field));
        CREATE TABLE IF NOT EXISTS dashboard_drafts(conversation_id TEXT PRIMARY KEY,revision INTEGER NOT NULL,base_state_version INTEGER NOT NULL,draft_json TEXT NOT NULL,updated_at TEXT NOT NULL);
        ''')


def persist(con,identifier,state,version):
    task_id=state.get('task_id') or 'legacy-'+identifier
    now=utcnow().isoformat()
    con.execute('INSERT INTO scientific_tasks VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET updated_at=excluded.updated_at,revision=excluded.revision',
                (task_id,identifier,now,now,version))
    con.execute('INSERT OR IGNORE INTO scientific_task_versions VALUES(?,?,?,?)',(task_id,version,json.dumps(state,ensure_ascii=False),now))
    for layer,key in [('confirmed','facts'),('literature','source_verified'),('assumptions','assumptions'),('derived','derived'),('predictions','estimates')]:
        for name,fact in state.get(key,{}).items():
            con.execute('INSERT OR IGNORE INTO scientific_fields VALUES(?,?,?,?,?,?,?,?)',
                        (task_id,version,layer,name,json.dumps(fact.get('value'),ensure_ascii=False),fact.get('provenance','UNKNOWN'),
                         fact.get('recorded_at') or now,json.dumps({'evidence':fact.get('evidence'),'dependencies':fact.get('dependencies',[])},ensure_ascii=False)))


def persist_results(con,identifier,state,version,reply):
    """Keep conditional profile evidence out of confirmed batch measurements."""
    task_id=state.get('task_id') or 'legacy-'+identifier;now=utcnow().isoformat()
    def field(layer,name,value,provenance,source):
        con.execute('INSERT OR IGNORE INTO scientific_fields VALUES(?,?,?,?,?,?,?,?)',
                    (task_id,version,layer,name,json.dumps(value,ensure_ascii=False),provenance,now,json.dumps(source,ensure_ascii=False)))
    results=reply.get('technical_metadata',{}).get('scientific_details',{})
    for scenario in results.get('assess_substrate_potential',{}).get('scenarios',[]):
        sid=scenario['id'];scope={'tool':'assess_substrate_potential','scenario_id':sid,'profile_ids':scenario.get('profile_ids'),
                                 'gas_basis':scenario.get('gas_basis'),'result_level':scenario['result_level']}
        for component in scenario['components']:
            source=component.get('source')
            if source:
                for name,value in component.get('properties_used',{}).items():
                    if value.get('provenance') not in {'LITERATURE_ESTIMATE','SOURCE_VERIFIED'} and not value.get('source_id'):continue
                    field('literature',sid+'.'+component['id']+'.'+name,value,'SOURCE_PROFILE_REFERENCE',
                          {**scope,'source':source,'material':component['material'],'material_state':component['material_state']})
        field('assumptions',sid+'.transfer',scenario.get('assumptions',[]),'EXPLICIT_TRANSFER_ASSUMPTIONS',scope)
        if scenario.get('methane_m3') is not None:
            field('derived',sid+'.methane_m3',scenario['methane_m3'],'CALCULATED_POTENTIAL_NOT_MEASURED_YIELD',scope)
    for scenario in results.get('evaluate_partial_economics',{}).get('scenarios',[]):
        for alternative in scenario['analysis']['scenarios']:
            value=alternative.get('gross_benefit_reference_kzt')
            if value is not None:field('derived',scenario['id']+'.'+alternative['id']+'.gross_kzt',value,'CONDITIONAL_GROSS_NOT_PROFIT',
                                      {'tool':'evaluate_partial_economics','scenario_id':scenario['id'],'alternative':alternative['id'],
                                       'prices':scenario['analysis']['prices'],'assumptions':alternative.get('assumptions',[])})


def read(store,identifier):
    with store.connect() as con:
        con.execute('BEGIN')
        row=con.execute('SELECT * FROM dashboard_sessions WHERE id=?',(identifier,)).fetchone()
        if row is None:return None
        memory=json.loads(row['conversation_state_json'] or '{}')
        task_id=memory.get('task_id') or 'legacy-'+identifier
        fields=[{k:r[k] for k in ['layer','field','provenance','updated_at']} | {'value':json.loads(r['value_json']),'source':json.loads(r['source_json'])}
                for r in con.execute('SELECT * FROM scientific_fields WHERE task_id=? AND revision=? ORDER BY layer,field',(task_id,row['state_version']))]
        draft=con.execute('SELECT * FROM dashboard_drafts WHERE conversation_id=?',(identifier,)).fetchone()
        archived=[dict(r) for r in con.execute('SELECT id,revision,created_at,updated_at FROM scientific_tasks WHERE conversation_id=? ORDER BY created_at',(identifier,))]
    return {'conversation_id':identifier,'state_version':row['state_version'],'active_task_id':memory.get('task_id'),
            'confirmed_measurements':memory.get('facts',{}),'literature':memory.get('source_verified',{}),
            'assumptions':memory.get('assumptions',{}),'derived':memory.get('derived',{}),'predictions':memory.get('estimates',{}),
            'components':memory.get('mixture_components',[]),'scenario_components':memory.get('mixture_scenario_components',[]),
            'scoped_result_fields':fields,'archived_tasks':archived,'dashboard_draft':dict(draft) if draft else None}
