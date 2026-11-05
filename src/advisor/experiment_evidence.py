"""Read local experiments without promoting an unmatched observation to BMP."""
import json
from src.advisor.catalog import normalized

def review(store,request):
    if store is None:return {'status':'not_connected','candidates':[],'automatic_transfer':False}
    with store.connect() as con:
        exists=con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='experiment_revisions'").fetchone()
        if not exists:return {'status':'no_local_experiment_registry','candidates':[],'automatic_transfer':False}
        rows=con.execute('''SELECT r.experiment_id,r.id,r.data_json FROM experiment_revisions r
            WHERE r.archived=0 AND r.id=(SELECT MAX(x.id) FROM experiment_revisions x WHERE x.experiment_id=r.experiment_id)''').fetchall()
    materials={c.material for c in request.components};candidates=[]
    for row in rows:
        data=json.loads(row['data_json'])
        try:material=normalized(data.get('material') or '')
        except ValueError:continue
        if material not in materials:continue
        missing=['structured_physical_state_and_preparation','verified_BMP_endpoint_and_blank_correction','structured_gas_temperature_pressure_moisture']
        if not data.get('quantitative_method_confirmed'):missing.append('confirmed_quantitative_method')
        if data.get('vs_mass_kg') is None and (data.get('vs_percent') is None or data.get('vs_basis') is None):missing.append('VS_mass_or_explicit_basis')
        candidates.append({'experiment_id':row['experiment_id'],'revision':row['id'],'material':material,
            'eligible_for_automatic_BMP_transfer':False,'missing_compatibility_evidence':missing})
    return {'status':'checked','records_checked':len(rows),'candidates':candidates,'automatic_transfer':False,
        'reason':'Existing experiment schema records gas observations, not a reviewed substrate BMP profile with preparation, blank correction and structured gas basis. Matching names alone cannot establish transferability.'}
