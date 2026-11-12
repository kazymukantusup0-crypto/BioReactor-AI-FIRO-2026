"""Web-only launch and multi-turn thermal scope; no LLM inference."""
import ast
import runpy,sys,types
from unittest.mock import Mock,patch
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from src.market.api import create_app
from src.market.store import Store
from test_scientific_question_routing import _wait_job

QUESTIONS=[
 'У меня 78 литров жидкого свиного навоза и реактор на 200 литров. Сколько метана получится, какую температуру выбрать и выгодно ли перерабатывать?',
 'А если температура будет только 25 °C?',
 'Сравни 25 °C и 35 °C и посоветуй, какой режим лучше для моей установки.'
]

def test_parent_entry_delegates_before_gui_imports_and_preserves_legacy_functions():
    p=Path(__file__).resolve().parents[2]/'main.py'
    tree=ast.parse(p.read_text(encoding='utf-8-sig'))
    first_guard=next(i for i,n in enumerate(tree.body) if isinstance(n,ast.If))
    tk_import=next(i for i,n in enumerate(tree.body) if isinstance(n,ast.Import) and any(a.name=='tkinter' for a in n.names))
    assert first_guard<tk_import
    main=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main')
    assert 'tk.Tk' not in ast.unparse(main) and 'launch_web()' in ast.unparse(main)

def test_running_parent_script_never_imports_tk_or_ml():
    helper=types.ModuleType('launch_bioreactor_web');helper.main=Mock()
    import builtins
    original=builtins.__import__
    def guarded(name,*a,**k):
        if name in {'tkinter','joblib','pandas'}:raise AssertionError('Desktop dependency imported')
        return original(name,*a,**k)
    with patch.dict(sys.modules,{'launch_bioreactor_web':helper}),patch('builtins.__import__',side_effect=guarded),pytest.raises(SystemExit):
        runpy.run_path(str(Path(__file__).resolve().parents[2]/'main.py'),run_name='__main__')
    helper.main.assert_called_once()

def test_three_messages_share_batch_and_compare_without_overwriting_temperature(tmp_path):
    with TestClient(create_app(Store(tmp_path/'web.sqlite3'),scheduler_enabled=False,firo_demo=True)) as client:
        sid=client.post('/api/dashboard/chat/sessions',json={'mode':'no_llm','conversation_version':'7'}).json()['id']
        for i,q in enumerate(QUESTIONS):
            job=client.post(f'/api/dashboard/chat/sessions/{sid}/jobs',json={'message':q,'request_id':f'TEST_WEB_THERMAL_{i}','expected_state_version':i}).json()
            assert _wait_job(client,job['id'])['status']=='COMPLETED'
            reply=client.get(job['result_reference']).json()['reply']
            assert reply['memory']['facts']['quantity']['value']==78
            assert reply['memory']['facts']['reactor_total_volume_l']['value']==200
            assert reply['tools']
            if i:
                assert reply['memory']['assumptions']['temperature_c']['value']==25
            if i==2:
                assert reply['memory']['advanced']['temperature_comparison_c']==[25,35]
                assert 'Сравнение температур' in [s['title'] for s in reply['user_facing_answer']['sections']]
                assert '416' in reply['answer'] and '512.69' in reply['answer']
                assert '4.147' in reply['answer'] and '5.111' in reply['answer']
        saved=client.get('/api/dashboard/chat/sessions/'+sid).json()
        assert len(saved['turns'])==3 and saved['turns'][-1]['reply']['answer']==reply['answer']
