"""Protocol and endpoint regressions; HTTP model responses are deterministic fixtures."""
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from src.agent.providers import JSONProvider, HybridLLM, ProviderError
from src.agent.verification9 import verify_scientific_answer
from src.recommendations.knowledge import search_scientific_sources
from src.market.api import create_app
from src.market.store import Store
from test_scientific_question_routing import _run_job

QUERY='Чем BMP отличается от теоретического выхода метана и фактического выхода за 30 дней? Нужен ли кислород для метаногенеза?'
ANSWER={'conclusion':'BMP — экспериментально измеренный потенциал образования метана в условиях лабораторного испытания.',
        'explanation':'Теоретический выход рассчитывают по составу субстрата или ХПК с допущениями. Фактическая выработка за 30 дней зависит от кинетики и условий реактора, поэтому BMP не гарантирует её за заданный срок. Метаногенез идёт без свободного кислорода.',
        'limitations':[], 'next_question':None,'evidence_ids':[],'decision':'not_applicable'}


def test_compact_nlu_schema_rejects_invented_material_without_retry():
    provider=JSONProvider('offline',model='qwen3:4b-q4_K_M')
    with patch.object(provider,'generate',return_value={'language':'ru','material_span':'expirimental_bmp'}) as call:
        with pytest.raises(ProviderError,match='Ungrounded'):
            provider.extract_dialogue(QUERY,{})
    assert call.call_count==1
    schema=call.call_args.args[1]
    assert set(schema['properties'])=={'language','material_span','requested_tasks'}
    assert schema['properties']['requested_tasks']['maxItems']==3
    assert schema['properties']['material_span']['enum']==[None]


def test_legacy_nlu_rejects_expirimental_bmp_even_with_valid_schema():
    provider=JSONProvider('offline',model='qwen3:8b')
    result={'language':'ru','intents':['general'],'material':'expirimental_bmp','material_evidence':'expirimental_bmp','entities':[]}
    with patch.object(provider,'generate',return_value=result):
        with pytest.raises(ProviderError,match='Ungrounded material'):
            provider.extract_dialogue(QUERY,{})


def test_truncated_json_is_never_a_successful_extraction():
    provider=JSONProvider('offline',model='qwen3:4b-q4_K_M')
    response={'message':{'content':'{"language":"ru","material_span":null}'},'done_reason':'length'}
    with patch('src.agent.providers.request_json',return_value=response):
        with pytest.raises(ProviderError,match='truncated'): provider.extract_dialogue(QUERY,{})
    assert provider.metrics[-1]['status']=='invalid_output'
    assert provider.metrics[-1]['nlu_validation']=='rejected'


def test_compact_nlu_anchors_real_material_to_literal_span():
    provider=JSONProvider('offline',model='qwen3:4b-q4_K_M')
    with patch.object(provider,'generate',return_value={'language':'ru','material_span':'пищевых отходов'}):
        result=provider.extract_dialogue('У меня 5 кг пищевых отходов.',{})
    assert result.material=='food_waste' and result.material_evidence=='пищевых отходов'


def test_reasoning_field_is_not_parsed_as_public_json():
    provider=JSONProvider('offline',model='qwen3:4b-q4_K_M')
    response={'message':{'thinking':'separate internal field','content':'{"language":"ru","material_span":null}'},'done_reason':'stop'}
    with patch('src.agent.providers.request_json',return_value=response):
        proposal=provider.extract_dialogue(QUERY,{})
    assert proposal.material is None and provider.metrics[-1]['nlu_validation']=='valid_compact_grounded'


@pytest.mark.parametrize('bad',[
    'BMP является теоретическим максимумом.',
    'Для метаногенеза нужен кислород.',
    'BMP — экспериментальная оценка. Теоретический выход зависит от состава.',
])
def test_scientific_checker_rejects_contradictions_or_missing_requested_concepts(bad):
    checked=verify_scientific_answer(bad,{'search_scientific_sources':search_scientific_sources(QUERY)},QUERY)
    assert checked['checked'] is True and checked['status']=='failed'


def test_scientific_checker_requires_sources_and_does_not_claim_general_truth():
    text=ANSWER['conclusion']+' '+ANSWER['explanation']
    assert verify_scientific_answer(text,{},QUERY)['status']=='failed'
    checked=verify_scientific_answer(text,{'search_scientific_sources':search_scientific_sources(QUERY)},QUERY)
    assert checked['status']=='passed' and checked['all_checks_passed'] is True
    assert 'limited' in checked['scope']


def test_endpoint_uses_nlu_then_source_grounded_model_synthesis_and_checks_history():
    calls=[]
    def http(url,payload,*args,**kwargs):
        calls.append(payload)
        if len(calls)==1:
            assert set(payload['format']['properties'])=={'language','material_span','requested_tasks'}
            assert payload['options']['num_predict']==128 and payload['think'] is False
            content={'language':'ru','material_span':None,'requested_tasks':[]}
        else:
            assert len(calls)==2, 'No call budget may be wasted on tool selection/retry'
            source_payload=json.loads(payload['messages'][-1]['content'])
            assert source_payload['reviewed_claims']
            content=ANSWER
        return {'message':{'content':json.dumps(content,ensure_ascii=False)},'done_reason':'stop','eval_count':30}
    def factory(*a,**k):
        provider=JSONProvider('offline',model='qwen3:4b-q4_K_M');provider.num_ctx=4096;provider.capture_public_output=True
        return HybridLLM('offline',providers=[provider],strict_model=True)
    with tempfile.TemporaryDirectory(dir=Path.cwd(),prefix='.tmp-grounded-synthesis-') as tmp:
        app=create_app(Store(Path(tmp)/'qa.sqlite3'),scheduler_enabled=False)
        with patch('src.dashboard.api.HybridLLM',side_effect=factory),patch('src.agent.providers.request_json',side_effect=http),TestClient(app) as client:
            _,sid,reply=_run_job(client,QUERY,'TEST_GROUNDED_SYNTHESIS')
            assert len(calls)==2
            assert reply['technical_metadata']['final_author']=='qwen_grounded_information'
            assert reply['technical_metadata']['scientific_answer_verification']['all_checks_passed'] is True
            assert reply['technical_metadata']['verification']['checked'] is False
            assert reply['technical_metadata']['model_synthesis']==ANSWER
            numbers=reply['technical_metadata']['quantity_verification']
            assert numbers['checked'] is True and numbers['status']=='passed'
            assert any(c['value']==30 and c['origin']=='USER_INPUT' and c['unit']=='day' for c in numbers['claims'])
            assert 'масса сырья' not in reply['answer']
            assert reply['tools'][0]['input_origin']=='deterministic_scientific_intent'
            restored=client.get(f'/api/dashboard/chat/sessions/{sid}').json()
            assert restored['turns'][0]['reply']['answer']==reply['answer']


def test_bmp_limits_bibliography_matches_primary_author_and_doi():
    doc=json.loads(Path('data/knowledge/imported/scientific_concepts_20261109.json').read_text(encoding='utf-8'))
    source=next(s for s in doc['sources'] if s['id']=='bmp_limits_2020')
    assert source['title'].startswith('Koch et al.')
    assert source['doi']=='10.3389/fenrg.2020.00063'


def test_fallback_answer_also_receives_scoped_scientific_checks():
    from test_scientific_question_routing import _fake_runtime_llm
    with tempfile.TemporaryDirectory(dir=Path.cwd(),prefix='.tmp-scientific-fallback-') as tmp:
        app=create_app(Store(Path(tmp)/'qa.sqlite3'),scheduler_enabled=False)
        with patch('src.dashboard.api.HybridLLM',side_effect=_fake_runtime_llm),TestClient(app) as client:
            _,_,reply=_run_job(client,QUERY,'TEST_SCIENTIFIC_FALLBACK_CHECK')
            meta=reply['technical_metadata']
            assert meta['final_author']=='curated_scientific_catalogue'
            assert meta['scientific_answer_verification']['checked'] is True
            assert meta['scientific_answer_verification']['status']=='passed'
            assert meta['model_synthesis'] is None
