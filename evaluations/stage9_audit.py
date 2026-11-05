"""Reproduce pre-v9 lifecycle failure in a temporary DB; no production edits."""
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from src.market.store import Store
from src.market.api import create_app
from src.agent.dialogue_memory import from_context
from src.agent.nlu import extract
from src.agent.task_state import prepare

root=Path(__file__).resolve().parents[1]
out=root/'reports/stage9';out.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory() as temp:
    store=Store(Path(temp)/'audit.sqlite3')
    with TestClient(create_app(store,scheduler_enabled=False),raise_server_exceptions=False) as client:
        sid=client.post('/api/dashboard/chat/sessions',json={'mode':'offline','context':{},'conversation_version':'7'}).json()['id']
        body={'message':'Проверь профиль навоза','request_id':'FAULT-INJECTION-construction'}
        with patch('src.dashboard.api.HybridLLM',side_effect=RuntimeError('TEST FAULT: provider construction interrupted')):
            failed=client.post(f'/api/dashboard/chat/sessions/{sid}/messages',json=body)
        repeated=client.post(f'/api/dashboard/chat/sessions/{sid}/messages',json=body)
        snapshot=client.get(f'/api/dashboard/chat/sessions/{sid}').json()
        result={'fault_injection':'Constructor failure after durable turn insert, before result handler',
                'initial_http':failed.status_code,'repeat_http':repeated.status_code,'repeat_body':repeated.json(),
                'persisted_turns':snapshot['turns']}
state=from_context({'material':'cattle_manure','material_volume_l':47,'reactor_volume_l':114});state.version='7'
query='У меня 470 л свежей травы и реактор 840 л. Стоит ли производить биогаз?'
extraction=extract(query,state);prepared,events,issues=prepare(query,state,extraction)
result['grass']={'query':query,'extraction':extraction.model_dump(mode='json'),'events':events,
                 'active_material_before_scientific_bridge':prepared.value('material')}
(out/'audit_before.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'initial_http':result['initial_http'],'repeat_http':result['repeat_http'],
                  'persisted_status':result['persisted_turns'][0]['status'],'grass_material':prepared.value('material')},ensure_ascii=False))
