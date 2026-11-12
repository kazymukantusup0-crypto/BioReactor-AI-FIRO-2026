"""Numerical grounding must preserve the role and unit of an input quantity."""
import pytest
from src.agent.quantities9 import check
from src.agent.dialogue_memory import from_context

QUESTION='Почему фактический выход метана за 30 дней может быть ниже BMP?'


def test_literal_time_horizon_is_allowed_in_its_original_scope():
    audit=[]
    assert check(['За 30 дней выход может быть ниже измеренного BMP из-за кинетики.'],{},[],query=QUESTION,audit=audit)==[]
    assert audit[0]['origin']=='USER_INPUT' and audit[0]['unit']=='day'


@pytest.mark.parametrize('text',[
    'За 30 дней реактор гарантированно произведёт 150 л CH4.',
    'Оптимальная температура составляет 30 °C.',
    'Концентрация составляет 30 %. ',
    'За 20 дней выход будет ниже BMP.',
    'Выдерживайте загрузку ровно 30 дней.',
    'Мы измерили выход метана за 30 дней.',
    'Установите температуру 37 °C.',
    'Оптимальное HRT составляет 30 дней.',
    'Длительность BMP составляет 30 дней.',
])
def test_input_horizon_does_not_authorize_a_prediction_measurement_or_recommendation(text):
    assert check([text],{},[],query=QUESTION)


def test_typed_tool_result_may_be_repeated_with_correct_species_and_units():
    evidence={'gas':{'value':{'low':.15,'high':.15},'unit':'m3 CH4','level':'CALCULATED','formula':'VS * BMP'}}
    audit=[]
    assert check(['Рассчитанный потенциал метана 0.15 м³ CH4.'],evidence,['gas'],audit=audit)==[]
    assert audit[0]['origin']=='DERIVED'
    assert check(['Общий биогаз составит 0.15 м³.'],evidence,['gas'])


def test_unit_conversion_is_arithmetic_and_keeps_methane_identity():
    evidence={'gas':{'value':{'low':.15,'high':.15},'unit':'m3 CH4','level':'CALCULATED','formula':'VS * BMP'}}
    assert check(['Рассчитанный потенциал 150 л CH4.'],evidence,['gas'])==[]
    assert check(['Рассчитанный потенциал 1500 л CH4.'],evidence,['gas'])


def test_user_volume_conversion_is_derived_not_a_new_measurement():
    state=from_context({'reported_methane_volume_m3':.15})
    audit=[]
    assert check(['Объём метана соответствует 150 л CH4.'],{},[],state,audit=audit)==[]
    assert audit[0]['origin']=='DERIVED' and audit[0]['input_origin']=='USER_INPUT'
    assert audit[0]['conversion_factor']==1000


def test_inputs_do_not_authorize_incorrect_multiplication():
    state=from_context({'vs_mass_kg':.6,'bmp_ml_ch4_g_vs':250})
    assert check(['Потенциал равен 250 л CH4.'],{},[],state)


def test_current_turn_horizon_replaces_previous_horizon_without_stale_allowlist():
    assert check(['За 30 дней выход может измениться.'],{},[],query=QUESTION)==[]
    current='Исправление: рассматриваем не 30, а 20 дней.'
    assert check(['За 20 дней выход может измениться.'],{},[],query=current)==[]
    assert check(['За 30 дней выход может измениться.'],{},[],query=current)


def test_scientific_reference_origin_is_preserved():
    evidence={'temperature':{'value':{'low':35,'high':35},'unit':'°C','level':'LITERATURE'}}
    audit=[]
    assert check(['Температура опубликованного опыта 35 °C.'],evidence,['temperature'],audit=audit)==[]
    assert audit[0]['origin']=='SCIENTIFIC_SOURCE'
    assert check(['Установите температуру 35 °C.'],evidence,['temperature'])


def test_actual_parameter_correction_does_not_leave_old_mass_allowed():
    from src.agent.nlu import extract
    from src.agent.dialogue_memory import apply
    from src.agent.dialogue_types import DialogueState
    state=apply(DialogueState(),extract('У меня 5 кг пищевых отходов.',DialogueState()))
    updated=apply(state,extract('Исправление: не 5, а 6 кг.',state))
    assert check(['Для 6 кг пищевых отходов.'],{},[],updated)==[]
    assert check(['Для 5 кг пищевых отходов.'],{},[],updated)


def test_unconfirmed_tool_output_does_not_become_user_measurement():
    evidence={'gas':{'value':{'low':.15,'high':.15},'unit':'m3 CH4','level':'MODEL_PREDICTION'}}
    audit=[]
    assert check(['Прогноз модели 0.15 м³ CH4.'],evidence,['gas'],audit=audit)==[]
    assert audit[0]['origin']=='TOOL_RESULT'
    assert check(['Измеренная выработка вашего реактора 0.15 м³ CH4.'],evidence,['gas'])


def test_manure_volume_with_adjective_and_reactor_volume_after_noun_keep_roles():
    from src.agent.nlu import extract
    from src.agent.dialogue_memory import apply
    from src.agent.dialogue_types import DialogueState
    query='У меня 142 л коровьего навоза и реактор номинальной вместимостью 200 л.'
    state=apply(DialogueState(),extract(query,DialogueState()));audit=[]
    text='Для прогноза метана из 142 л коровьего навоза в реакторе объемом 200 л недостаточно данных: масса, VS, BMP, кинетика и условия.'
    assert check([text],{},[],state,audit=audit)==[]
    assert [(r['value'],r['role']) for r in audit]==[(142,'feedstock_volume'),(200,'reactor_volume')]
    assert check(['Получится 142 л метана.'],{},[],state)
    assert check(['Для прогноза из 200 л коровьего навоза.'],{},[],state)
    assert check(['Реакторе объёмом 142 л.'],{},[],state)
