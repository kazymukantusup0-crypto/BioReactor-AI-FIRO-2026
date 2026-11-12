"""Multilingual proposition/negation/scope regressions, no inference."""
import pytest
from src.agent.verification9 import validate_synthesis,verify_scientific_answer
from src.recommendations.knowledge import search_scientific_sources


def draft(text):
    return {'conclusion':text,'explanation':'','limitations':[],'next_question':None,'evidence_ids':[],'decision':'not_applicable'}


BAD=[
    ('BMP не измеряется экспериментально.','bmp_experimental_measurement_denied'),
    ('BMP невозможно измерить в лаборатории.','bmp_experimental_measurement_denied'),
    ('BMP is not measured experimentally.','bmp_experimental_measurement_denied'),
    ('BMP cannot be measured in a laboratory.','bmp_experimental_measurement_denied'),
    ('BMP тәжірибеде өлшенбейді.','bmp_experimental_measurement_denied'),
    ('BMP зертханада өлшенетін шама емес.','bmp_experimental_measurement_denied'),
    ('Лабораторное определение BMP невозможно.','bmp_experimental_measurement_denied'),
    ('Определить BMP экспериментальным способом нельзя.','bmp_experimental_measurement_denied'),
    ('Experimental measurement of BMP is impossible.','bmp_experimental_measurement_denied'),
    ('BMP is a mathematical upper bound with no experimental basis.','bmp_experimental_measurement_denied'),
    ('Зертханалық жолмен BMP-ді өлшеу мүмкін емес.','bmp_experimental_measurement_denied'),
    ('BMP — это исключительно теоретический максимум.','bmp_equated_to_theoretical_maximum'),
    ('BMP is purely the theoretical maximum.','bmp_equated_to_theoretical_maximum'),
    ('BMP тек теориялық максимум.','bmp_equated_to_theoretical_maximum'),
    ('Кинетика не влияет на batch BMP-тест.','batch_kinetics_or_conditions_denied'),
    ('Кинетика и условия реактора не отражены в batch-тесте.','batch_kinetics_or_conditions_denied'),
    ('Kinetics does not affect the batch BMP test.','batch_kinetics_or_conditions_denied'),
    ('Batch BMP results are independent of kinetics.','batch_kinetics_or_conditions_denied'),
    ('A BMP assay final yield is unaffected by digestion kinetics.','batch_kinetics_or_conditions_denied'),
    ('Кинетика batch BMP сынағына әсер етпейді.','batch_kinetics_or_conditions_denied'),
    ('Batch BMP нәтижелері кинетикаға тәуелді емес.','batch_kinetics_or_conditions_denied'),
    ('BMP гарантирует такой же выход в промышленном реакторе.','bmp_guarantees_reactor_yield'),
    ('BMP guarantees the same yield in an industrial reactor.','bmp_guarantees_reactor_yield'),
    ('BMP өнеркәсіптік реакторда дәл сондай шығымға кепілдік береді.','bmp_guarantees_reactor_yield'),
    ('Фактический выход за 30 дней всегда равен BMP.','fixed_time_yield_equated_to_bmp'),
    ('Actual yield after 30 days always equals BMP.','fixed_time_yield_equated_to_bmp'),
    ('30 күндегі нақты шығым әрқашан BMP-ге тең.','fixed_time_yield_equated_to_bmp'),
    ('BMP — лабораторный потенциал, а не измеренная выработка.','bmp_measurement_scope_ambiguous'),
    ('Кинетика лабораторного испытания не переносима в промышленный реактор.','absolute_lab_transfer_denial'),
    ('Laboratory kinetics cannot be transferred to an industrial reactor.','absolute_lab_transfer_denial'),
    ('Биогаз — это чистый метан.','methane_biogas_equated'),
    ('Объём метана равен объёму биогаза.','methane_biogas_equated'),
    ('Biogas is pure methane.','methane_biogas_equated'),
    ('BMP 250 мл CH4/г VS больше выхода 150 л CH4.','bmp_yield_incompatible_basis'),
]


@pytest.mark.parametrize('text,code',BAD)
def test_rejects_false_scientific_proposition(text,code):
    assert code in validate_synthesis(draft(text),{}, {})


GOOD=[
    'BMP измеряют экспериментально; это не измеренная выработка конкретного реактора.',
    'BMP — не измеренная выработка конкретного реактора.',
    'BMP is experimentally measured, not the measured output of a specific reactor.',
    'BMP is not the measured output of a specific reactor.',
    'BMP зертханада өлшенеді; бұл нақты реактордың өлшенген өнімі емес.',
    'BMP не является исключительно теоретическим максимумом.',
    'BMP нельзя считать теоретическим максимумом.',
    'BMP is not the theoretical maximum.',
    'BMP тек теориялық максимум емес.',
    'Кинетика влияет на batch BMP-тест; её параметры нельзя автоматически переносить на реактор.',
    'Batch BMP kinetics cannot be transferred directly to an industrial reactor.',
    'Кинетика batch BMP сынағына әсер етеді; нәтижені реакторға тікелей көшіруге болмайды.',
    'BMP не гарантирует такой же выход в промышленном реакторе.',
    'BMP does not guarantee the same yield in a full-scale reactor.',
    'BMP нақты реактордың шығымына кепілдік бермейді.',
    'Фактический выход за 30 дней не всегда равен BMP.',
    'Actual yield after 30 days does not always equal BMP.',
    '30 күндегі нақты шығым әрқашан BMP-ге тең емес.',
    'Неверно, что BMP не измеряется экспериментально.',
    'It is false that BMP cannot be measured experimentally.',
    'Нельзя утверждать, что BMP не измеряют экспериментально.',
    'It would be wrong to claim BMP is purely theoretical.',
    'BMP экспериментте өлшенбейді деу дұрыс емес.',
    'Лабораторные данные нельзя автоматически переносить на промышленный реактор без учёта условий.',
    'Лабораторная кинетика может служить ориентиром для промышленного реактора с учётом условий.',
    'Биогаз содержит метан и другие газы.',
    'Объём метана не равен объёму биогаза.',
    'Нельзя напрямую сравнивать BMP 250 мл CH4/г VS и 150 л CH4 без сопоставимой массы VS.',
]


@pytest.mark.parametrize('text',GOOD)
def test_does_not_reject_correct_negation_or_reactor_scope(text):
    codes={code for _,code in BAD}
    assert not codes.intersection(validate_synthesis(draft(text),{}, {},query='Выход за 30 дней / 30 days / 30 күн'))


def test_keywords_cannot_mask_an_explicit_contradiction():
    query='Что такое BMP?'
    answer='BMP измеряют экспериментально в лаборатории. BMP не измеряется экспериментально.'
    check=verify_scientific_answer(answer,{'search_scientific_sources':search_scientific_sources(query)},query)
    assert check['status']=='failed' and 'bmp_experimental_measurement_denied' in check['contradictions']


@pytest.mark.parametrize('query,text',[
    ('Что такое BMP и теоретический выход? Почему выход за 30 дней ниже? Нужен ли кислород?',
     'BMP измеряют экспериментально в лабораторном batch-тесте. Теоретический выход рассчитывают по составу. Условия batch-теста влияют на наблюдаемый BMP; кинетика влияет на скорость накопления метана. Выход за 30 дней зависит от кинетики и условий реактора, BMP не гарантирует его. Метаногенез идёт без кислорода.'),
    ('What is BMP versus theoretical yield and actual yield after 30 days? Is oxygen needed?',
     'BMP is experimentally measured in a laboratory batch assay. Theoretical yield is calculated from composition and assumptions. Batch conditions affect observed BMP, and kinetics affects methane accumulation. Yield after 30 days depends on kinetics and reactor conditions; BMP does not guarantee it. Methanogenesis proceeds without oxygen.'),
    ('BMP және теориялық шығым деген не? 30 күндегі шығым неге төмен? Оттегі қажет пе?',
     'BMP зертханалық batch сынағында эксперименттік жолмен өлшенеді. Теориялық шығым құрам бойынша жорамалдармен есептеледі. Batch сынағының жағдайлары BMP-ге, кинетика метан жиналу жылдамдығына әсер етеді. Нақты шығым кинетика мен реактор жағдайына тәуелді. Метаногенезге оттегі қажет емес.'),
])
def test_complete_scientific_explanations_pass_in_three_languages(query,text):
    report=verify_scientific_answer(text,{'search_scientific_sources':search_scientific_sources(query)},query)
    assert report['checked'] is True and report['status']=='passed',report
    assert any(a['subject']=='BMP' and a['passed'] for a in report['assertions'])
