"""Offline regressions: no model download, inference or server restart."""
from pathlib import Path
import hashlib
import tempfile
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from evaluations.qwen3_4b_agent_qa import Qwen4BQAProvider, create_qa_llm
from src.agent.verification9 import validate_synthesis
from src.agent.dialogue_types import DialogueState
from src.agent.nlu import extract
from src.recommendations.retrieval import retrieve
from src.market.api import create_app
from src.market.store import Store
from test_scientific_question_routing import _fake_runtime_llm, _run_job


def test_qa_profile_is_explicit_and_does_not_change_production_config():
    config = Path('data/config/llm_selection.json')
    before = hashlib.sha256(config.read_bytes()).digest()
    llm = create_qa_llm()
    provider = llm.providers[0]
    payload = provider.payload([{'role': 'user', 'content': 'Тест'}])
    assert isinstance(provider, Qwen4BQAProvider)
    assert provider.url == 'http://127.0.0.1:11479/api/chat'
    assert payload['model'] == 'qwen3:4b-q4_K_M'
    assert payload['options']['num_ctx'] == 4096
    assert payload['options']['num_batch'] == 32
    assert payload['options']['num_gpu'] == -1
    assert payload['keep_alive'] == 0
    assert hashlib.sha256(config.read_bytes()).digest() == before


def candidate(text):
    return {'conclusion':text, 'explanation':'', 'limitations':[],
            'next_question':None, 'evidence_ids':[], 'decision':'not_applicable'}


@pytest.mark.parametrize('answer,issue', [
    ('Для метаногенеза нужен кислород.', 'oxygen_required_for_anaerobic_process'),
    ('Кислород не нужен; метаногенез требует кислород.', 'oxygen_required_for_anaerobic_process'),
    ('BMP является теоретическим максимумом.', 'bmp_equated_to_theoretical_maximum'),
])
def test_scientific_contradictions_are_rejected(answer, issue):
    assert issue in validate_synthesis(candidate(answer), {}, {})


@pytest.mark.parametrize('answer', [
    'Для метаногенеза не нужен кислород.',
    'BMP не является теоретическим максимумом.',
])
def test_correct_scientific_statements_are_not_rejected(answer):
    issues = validate_synthesis(candidate(answer), {}, {})
    assert 'oxygen_required_for_anaerobic_process' not in issues
    assert 'bmp_equated_to_theoretical_maximum' not in issues


def test_oxygen_question_uses_scientific_catalogue():
    query = 'Почему метаногенез проходит без кислорода?'
    assert 'scientific_explanation' in extract(query, DialogueState()).request_kinds
    found = retrieve(query)
    assert 'q4b_anaerobic_no_oxygen' in {c['id'] for c in found['claims']}


def test_bmp_theory_is_source_bound():
    found = retrieve('Чем BMP отличается от теоретического максимума?')
    assert 'q4b_bmp_not_theoretical_maximum' in {c['id'] for c in found['claims']}


def test_oxygen_question_through_dashboard_chat_endpoint():
    with tempfile.TemporaryDirectory(dir=Path.cwd(), prefix='.tmp-q4b-oxygen-') as temporary:
        app = create_app(Store(Path(temporary) / 'qa.sqlite3'), scheduler_enabled=False)
        with patch('src.dashboard.api.HybridLLM', side_effect=_fake_runtime_llm), TestClient(app) as client:
            _, _, reply = _run_job(client, 'Почему метаногенез проходит без кислорода?', 'TEST_OXYGEN_ROUTE')
            assert 'q4b_anaerobic_no_oxygen' in {claim['id'] for tool in reply['tools']
                for claim in tool.get('result', {}).get('claims', [])} or 'без свободного кислорода' in reply['answer'].lower()
            assert not any(t['tool'] == 'assess_substrate_potential' for t in reply['tools'])


def test_fixed_time_limit_through_dashboard_chat_endpoint():
    prompt = 'У меня 142 л коровьего навоза и реактор 200 л. Сколько метана получится за 30 дней?'
    with tempfile.TemporaryDirectory(dir=Path.cwd(), prefix='.tmp-q4b-science-') as temporary:
        app = create_app(Store(Path(temporary) / 'qa.sqlite3'), scheduler_enabled=False)
        with patch('src.dashboard.api.HybridLLM', side_effect=_fake_runtime_llm), TestClient(app) as client:
            _, _, reply = _run_job(client, prompt, 'TEST_FIXED_TIME_LIMIT')
            answer = reply['answer'].lower()
            assert 'кинетик' in answer and 'плотност' in answer and 'bmp' in answer
            # The literature-estimate route can now publish a scoped BMP
            # potential. It must still withhold an unsupported thirty-day yield.
            assert 'выход за 30 дней: численно не установлен' in answer
            estimate=next(t['result'] for t in reply['tools'] if t['tool']=='estimate_methane_yield')
            assert estimate['target_days']==30
            assert all(s['time_yield']['methane_l'] is None for s in estimate['scenarios'])
