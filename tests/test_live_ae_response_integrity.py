"""Regressions for real A/C/D/E traces without any live model call."""
import pytest

from src.agent.dialogue_memory import apply
from src.agent.dialogue_types import DialogueState
from src.agent.nlu import extract
from src.agent.quantities9 import check
from src.agent.response_integrity import check_response
from src.agent.verification9 import scientific_assertions,validate_synthesis
from evaluations.qwen4b_manual_chat import SCIENTIFIC_CASES
from test_scientific_assertion_scope import draft


def test_saved_real_a_draft_is_rejected_for_incomplete_and_repeated_text():
    text=('Экспериментальный BMP — это лабораторно измеренный потенциал метана при определенных условиях. '
          'Лабораторная кинетика показывает скорость его накопления, но не гарантирует реальный выход в реакторе. '
          'Для оценки реального реактора нужно учитывать условия, доступность органики и кинетику, а не просто BMP. '
          'BMP не равен теоретическому выходу и не гаранти')
    payload=draft(text);payload['explanation']=text.replace('не гаранти','не гарантирует конкретный')[:349]
    issues=check_response(payload)
    assert 'text_at_limit_incomplete' in issues
    assert 'repeated_model_text' in issues
    assert 'text_at_limit_incomplete' in validate_synthesis(payload,{}, {},query=SCIENTIFIC_CASES['A'][0])


@pytest.mark.parametrize('text',['Ответ закончен без точки','Какой результат?','Список:\n- вода\n- инокулят','Қорытынды дайын'])
def test_valid_endings_need_no_forced_final_period(text):
    assert not check_response({'conclusion':text,'explanation':'','limitations':[]})


@pytest.mark.parametrize('text',['Не хватает массы,','Нужно знать массу и','Список:\n- вода\n-','Параметры:'])
def test_incomplete_enumeration_or_clause_is_rejected(text):
    assert 'incomplete_enumeration_or_clause' in check_response({'conclusion':text,'explanation':'','limitations':[]})


def test_finish_reason_reports_truncation_and_plain_complete_text_passes():
    payload={'conclusion':'Данные доступны','explanation':'','limitations':[]}
    assert 'generation_truncated' in check_response(payload,finish_reason='length')
    assert check_response(payload,finish_reason='stop')==[]


def test_saved_real_c_numeric_roles_are_preserved_and_swaps_rejected():
    text=SCIENTIFIC_CASES['C'][0];state=apply(DialogueState(),extract(text,DialogueState()))
    payload={'conclusion':'Не хватает плотности сырья для оценки метанового потенциала. Вместимость реактора 200 л, но объём навоза 142 л. Метан не может быть рассчитан без плотности и других параметров.'}
    audit=[]
    assert check([payload['conclusion']],{},[],state,query=text,audit=audit)==[]
    assert {(a['value'],a['role']) for a in audit} >= {(142.0,'feedstock_volume'),(200.0,'reactor_volume')}
    assert check(['Объём навоза 200 л.'],{},[],state,query=text)
    assert check(['Объём реактора 142 л.'],{},[],state,query=text)
    assert check(['Выход метана 142 л CH₄.'],{},[],state,query=text)
    assert check(['Выход метана 200 л.'],{},[],state,query=text)
    assert check(['Выход метана в реакторе составит 200 л.'],{},[],state,query=text)
    assert check(['Из 142 л навоза получится 142 л метана.'],{},[],state,query=text)
    assert check(['Метана из 142 л навоза получится неизвестное количество.'],{},[],state,query=text)==[]
    assert check(['Вместимость реактора 200 л не влияет на метановый выход, так как объем загрузки 142 л меньше номинальной вместимости.'],{},[],state,query=text)==[]
    assert check(['За 30 дней выход может измениться.'],{},[],state,query=text)==[]


def test_nominal_capacity_does_not_prove_charge_or_reactor_yield():
    text='Вместимость реактора 200 л не влияет на метановый выход, так как объем загрузки 142 л меньше номинальной вместимости.'
    assert 'capacity_conclusion_from_nominal_only' in validate_synthesis(draft(text),{}, {},query=SCIENTIFIC_CASES['C'][0])


def test_unqualified_kinetics_transfer_and_paraphrased_repetition_are_rejected():
    content=draft('Экспериментальный BMP — лабораторно измеренный потенциал метана, не гарантирующий реального реактора. Лабораторная кинетика показывает скорость накопления, но не переносится на реактор. Реальный реактор оценивается по стабильности, нагрузке и HRT, а не по однократному тесту.')
    content['explanation']='BMP — потенциал образца в batch-тесте, не гарантирующий реального реактора. Кинетика — скорость метана, но не переносится на реактор. Реактор оценивается по стабильности, нагрузке и HRT, а не по однократному тесту.'
    issues=validate_synthesis(content,{}, {},query=SCIENTIFIC_CASES['A'][0])
    assert 'absolute_lab_transfer_denial' in issues
    assert 'repeated_model_text' in issues


@pytest.mark.parametrize('text',[
    'BMP не равен теоретическому выходу.',
    'BMP не совпадает с теоретическим максимумом.',
    'BMP — экспериментально измеренный потенциал, не равный теоретическому выходу.',
    'BMP is not equal to theoretical yield.',
])
def test_unqualified_numerical_inequality_is_flagged(text):
    assert 'bmp_theoretical_values_unconditionally_unequal' in {x['rule'] for x in scientific_assertions(text)}


@pytest.mark.parametrize('text',[
    'BMP и теоретический выход — разные понятия, а их значения могут совпасть.',
    'BMP не обязательно равен теоретическому выходу.',
    'BMP — не измеренная выработка конкретного реактора.',
    'Лабораторные результаты могут служить ориентиром после проверки применимости.',
])
def test_cautious_scientific_statements_are_not_rejected(text):
    assert 'bmp_theoretical_values_unconditionally_unequal' not in {x['rule'] for x in scientific_assertions(text)}


def test_incomplete_model_draft_is_retried_and_only_repaired_answer_delivered():
    import json
    import tempfile
    from pathlib import Path
    from unittest.mock import patch
    from fastapi.testclient import TestClient
    from src.agent.providers import HybridLLM,JSONProvider
    from src.market.api import create_app
    from src.market.store import Store
    from test_scientific_question_routing import _run_job
    attempts=[]
    def http(url,payload,*args,**kwargs):
        if not attempts:
            content={'language':'ru','material_span':None}
        elif len(attempts)==1:
            content=draft('BMP измеряют экспериментально в лаборатории. '+('Подробные условия теста и реактора. '*10)[:300])
            content['conclusion']=(content['conclusion']+'незаверш').ljust(350,'н')[:350]
        else:
            content=draft('BMP экспериментально измеряют в лабораторном испытании при определённых условиях.')
            content['explanation']='Лабораторная кинетика служит ориентиром для реактора после проверки применимости.'
        attempts.append(content)
        return {'message':{'content':json.dumps(content,ensure_ascii=False)},'done_reason':'stop','eval_count':30}
    def factory(*a,**k):return HybridLLM('offline',providers=[JSONProvider('offline',model='qwen3:4b-q4_K_M')],strict_model=True)
    with tempfile.TemporaryDirectory(dir=Path.cwd(),prefix='.tmp-repair-') as tmp:
        app=create_app(Store(Path(tmp)/'qa.sqlite3'),scheduler_enabled=False)
        with patch('src.dashboard.api.HybridLLM',side_effect=factory),patch('src.agent.providers.request_json',side_effect=http),TestClient(app) as client:
            _,_,reply=_run_job(client,SCIENTIFIC_CASES['A'][0],'TEST_REPAIR_A')
            assert len(attempts)==3
            assert 'незаверш' not in reply['answer']
            assert 'после проверки применимости' in reply['answer']
            assert reply['technical_metadata']['final_author']=='qwen_grounded_information'
            assert any('text_at_limit_incomplete' in row.get('issues',[]) for row in reply['technical_metadata']['diagnostics'])
