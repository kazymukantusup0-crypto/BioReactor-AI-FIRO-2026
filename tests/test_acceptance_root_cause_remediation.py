"""Regression coverage for the shared causes in the final acceptance audit.

These tests exercise deterministic parsing, routing, verification and rendering;
they are not substitutes for real-Qwen or browser acceptance tests.
"""
import json
import pytest
from src.agent.analytical import obligations
from src.agent.dialogue_memory import apply, fact, tool_context
from src.agent.dialogue_types import DialogueState, NLUProposal, Question
from src.agent.evidence9 import collect, partial_references, render_reference
from src.agent.nlu import extract
from src.agent.runtime9 import requirements
from src.agent.runtime9 import fallback_explanations
from src.agent.analytical import explicit_calculations
from src.agent.conversation import ConversationAgent
from src.agent.providers import HybridLLM, JSONProvider, ProviderError
from src.agent.tools import ToolRegistry


def parsed(text, prior=None):
    return apply(prior or DialogueState(), extract(text, prior))


def prepared(text, prior=None):
    from src.agent.task_state import prepare as prepare_task
    prior=prior or DialogueState();extraction=extract(text,prior)
    state,events,issues=prepare_task(text,prior,extraction)
    assert not issues
    return apply(state,extraction,tolerate_engineering_conflicts=True),events


def any_input(state, name):
    return next((layer[name] for layer in (state.facts, state.assumptions, state.derived) if name in layer), None)


def test_whey_sale_offer_value_currency_scope_and_provenance_reach_tools():
    text = ('Молокозавод забирает 25 кг сыворотки по 40 тенге за кг; '
            'сколько это даёт при продаже?')
    state = parsed(text)

    assert state.value('sale_offer_amount') == 40
    assert state.value('sale_offer_currency') == 'KZT'
    assert state.value('sale_offer_scope') == 'kg'
    assert state.facts['sale_offer_amount'].unit == 'KZT/kg'
    assert state.facts['sale_offer_amount'].provenance == 'USER_CONFIRMED'
    context = tool_context(state)
    assert context['sale_offer_amount'] == 40
    assert context['sale_offer_scope'] == 'kg'


def test_scenario_word_does_not_trigger_market_price_route():
    from src.agent.smart_intent import identify

    prior = parsed('Начинаем новую партию: 4,5 кг измельчённой пшеничной соломы. Оцени потенциальный метан.')
    prompt = ('А если гипотетически было бы 8 кг? Ответь как сценарий, '
              'не заменяя записанную массу 4,5 кг.')
    extraction = extract(prompt, prior)
    state = apply(prior, extraction)

    assert 'market_prices' not in extraction.intents
    assert 'economics' not in identify(prompt, prior)['goals']
    assert state.value('quantity') == 4.5
    assert state.assumptions['quantity'].value == 8
    assert 'get_market_prices' not in requirements(state, prompt)
    assert 'assess_substrate_potential' in requirements(state, prompt)

    price_query = 'Какая сейчас цена природного газа в Караганде?'
    assert 'market_prices' in extract(price_query, prior).intents
    assert 'economics' in identify(price_query, prior)['goals']


def test_negated_profit_clause_does_not_route_economic_tools_but_keeps_literature_lookup():
    from src.agent.smart_intent import identify

    text = ('\u0421\u0440\u0430\u0432\u043d\u0438 \u0442\u043e\u043b\u044c\u043a\u043e \u043b\u0438\u0442\u0435\u0440\u0430\u0442\u0443\u0440\u043d\u044b\u0439 '
            '\u043f\u043e\u0442\u0435\u043d\u0446\u0438\u0430\u043b \u043c\u0435\u0442\u0430\u043d\u0430 \u0434\u043b\u044f 3 \u043a\u0433 \u0441\u0432\u0435\u043a\u043b\u043e\u0432\u0438\u0447\u043d\u043e\u0433\u043e \u0436\u043e\u043c\u0430 '
            '\u0438 3 \u043a\u0433 \u043f\u0448\u0435\u043d\u0438\u0447\u043d\u043e\u0439 \u0441\u043e\u043b\u043e\u043c\u044b. \u041d\u0435 \u0434\u0435\u043b\u0430\u0439 \u0432\u044b\u0432\u043e\u0434 '
            '\u043e \u043f\u0440\u0438\u0431\u044b\u043b\u0438 \u0431\u0435\u0437 \u0446\u0435\u043d \u0438 \u0437\u0430\u0442\u0440\u0430\u0442.')
    extraction = extract(text)
    state = apply(DialogueState(), extraction)

    assert 'economic_comparison' not in extraction.intents
    assert 'market_prices' not in extraction.intents
    assert 'economics' not in identify(text, DialogueState())['goals']
    assert 'search_substrate_profiles' in requirements(state, text)
    assert 'get_market_prices' not in requirements(state, text)
    assert 'evaluate_partial_economics' not in requirements(state, text)

    paraphrase = ('\u041d\u0430\u0439\u0434\u0438 \u0432 \u043b\u0438\u0442\u0435\u0440\u0430\u0442\u0443\u0440\u0435 BMP-\u0434\u0438\u0430\u043f\u0430\u0437\u043e\u043d\u044b \u0434\u043b\u044f \u0441\u0432\u0435\u043a\u043b\u043e\u0432\u0438\u0447\u043d\u043e\u0433\u043e \u0436\u043e\u043c\u0430 '
                  '\u0438 \u043f\u0448\u0435\u043d\u0438\u0447\u043d\u043e\u0439 \u0441\u043e\u043b\u043e\u043c\u044b, \u0441\u0440\u0430\u0432\u043d\u0438 \u043e\u0442\u0434\u0435\u043b\u044c\u043d\u043e \u0434\u043b\u044f \u043f\u0430\u0440\u0442\u0438\u0439 \u043f\u043e 3 \u043a\u0433. '
                  '\u041d\u0435 \u0440\u0430\u0441\u0441\u0447\u0438\u0442\u044b\u0432\u0430\u0439 \u043f\u0440\u0438\u0431\u044b\u043b\u044c \u0438 \u043d\u0435 \u0437\u0430\u043f\u0440\u0430\u0448\u0438\u0432\u0430\u0439 \u0446\u0435\u043d\u044b: TS \u0438 VS \u044d\u0442\u0438\u0445 \u043f\u0430\u0440\u0442\u0438\u0439 \u043d\u0435 \u0438\u0437\u043c\u0435\u0440\u0435\u043d\u044b.')
    second_extraction = extract(paraphrase)
    second_state = apply(DialogueState(), second_extraction)
    assert 'economic_comparison' not in second_extraction.intents
    assert 'market_prices' not in second_extraction.intents
    assert 'search_substrate_profiles' in requirements(second_state, paraphrase)
    assert 'get_market_prices' not in requirements(second_state, paraphrase)


def test_quantity_verifier_recognizes_each_explicit_mixture_component_amount():
    from src.agent.mixture_parser import explicit_components
    from src.agent.quantities9 import check

    text = ('\u0421\u0440\u0430\u0432\u043d\u0438 3 \u043a\u0433 \u0441\u0432\u0435\u043a\u043b\u043e\u0432\u0438\u0447\u043d\u043e\u0433\u043e \u0436\u043e\u043c\u0430 '
            '\u0438 3 \u043a\u0433 \u043f\u0448\u0435\u043d\u0438\u0447\u043d\u043e\u0439 \u0441\u043e\u043b\u043e\u043c\u044b.')
    components = [component.model_dump(mode='json') for component in explicit_components(text)]
    state = DialogueState(mixture_components=components)

    assert check(['For 3 kg beet pulp and 3 kg straw.'], {}, [], state) == []
    assert 'ungrounded_quantity_or_wrong_unit' in check(['For 4 kg beet pulp.'], {}, [], state)


def test_unrequested_economic_analysis_is_rejected_for_non_economic_turns():
    from src.agent.verification9 import validate_synthesis

    state = DialogueState(intents=['profile_lookup'])
    draft = {'conclusion': 'A literature profile is available.',
             'explanation': 'Selling this batch is profitable.',
             'limitations': [], 'next_question': None,
             'evidence_ids': [], 'decision': 'not_applicable'}

    assert 'unrequested_economic_analysis' in validate_synthesis(draft, {}, {}, state)


def test_synthesis_cannot_omit_available_sample_specific_literature_bmp():
    from src.agent.verification9 import validate_synthesis

    state = DialogueState(intents=['profile_lookup'])
    evidence = {'profile.straw-observation.bmp': {
        'id': 'profile.straw-observation.bmp', 'label': 'Wheat straw: published sample BMP',
        'value': {'low': 214, 'high': 214}, 'unit': 'mL CH4/g VS',
        'level': 'LITERATURE', 'scenario': 'straw-observation'}}
    results = {'search_substrate_profiles': {'status': 'ok', 'dossiers': []}}
    draft = {'conclusion': 'A sample-specific literature result is available.',
             'explanation': 'It cannot be transferred directly to a different batch.',
             'limitations': [], 'next_question': None,
             'evidence_ids': [], 'decision': 'not_applicable'}

    assert 'available_literature_value_omitted' in validate_synthesis(draft, evidence, results, state)
    draft['evidence_ids'] = ['profile.straw-observation.bmp']
    assert validate_synthesis(draft, evidence, results, state) == []


def test_local_profile_search_cannot_be_synthesized_as_global_literature_absence():
    from src.agent.verification9 import validate_synthesis

    state = DialogueState(intents=['profile_lookup'])
    evidence = {'profile.straw-A.bmp': {
        'id': 'profile.straw-A.bmp', 'label': 'Wheat straw sample BMP',
        'value': {'low': 214, 'high': 214}, 'unit': 'mL CH4/g VS',
        'level': 'LITERATURE', 'scenario': 'straw-A'}}
    # Match the actual tool schema: scope metadata is attached to each dossier,
    # and the response has no top-level live_search_performed field.
    results = {'search_substrate_profiles': {'status': 'ok',
        'dossiers': [{'material': 'beet_pulp', 'name': 'Beet pulp', 'studies': [],
                      'search_scope': 'LOCAL_REVIEWED_CORPUS', 'live_search_performed': False},
                     {'material': 'straw', 'name': 'Wheat straw', 'studies': [{}],
                      'search_scope': 'LOCAL_REVIEWED_CORPUS', 'live_search_performed': False}]}}
    draft = {'conclusion': 'No scientific publications exist for beet pulp.',
             'explanation': 'The local catalogue has no result.', 'limitations': [],
             'next_question': None, 'evidence_ids': ['profile.straw-A.bmp'],
             'decision': 'not_applicable'}

    assert 'local_search_scope_overstated' in validate_synthesis(draft, evidence, results, state)
    draft['conclusion'] = 'No quantitative beet-pulp profile was found in the reviewed local catalogue; this does not establish that no publications exist.'
    assert validate_synthesis(draft, evidence, results, state) == []


def test_agent_budget_preserves_synthesis_time_after_required_tool_selection():
    from src.agent.runtime9 import _synthesis_reserve_seconds

    # At a 150 s request budget, reserve 90 s for the grounded response and
    # preflight any required tools that did not fit in the model planning window.
    assert _synthesis_reserve_seconds(150) == 90
    assert _synthesis_reserve_seconds(120) == 72
    assert _synthesis_reserve_seconds(20) == 15
    assert _synthesis_reserve_seconds(600) == 90


def test_missing_cost_requirements_are_not_misclassified_as_a_profitability_verdict():
    from src.agent.autonomous import _unsupported_conclusions, unconfirmed_profitability_claim

    answer = ('Прибыльность не определена. Для оценки прибыльности необходимо знать цены '
              'и затраты на обработку и транспортировку.')
    results = {'evaluate_partial_economics': {'profit_established': False}}

    assert not unconfirmed_profitability_claim(answer)
    assert _unsupported_conclusions(answer, results) == []


def test_conditional_literature_calculation_cannot_be_described_as_a_batch_measurement():
    from src.agent.verification9 import validate_synthesis

    state = DialogueState(intents=['methane_yield'])
    evidence = {'s1.methane': {'id': 's1.methane', 'label': 'Methane potential',
        'value': {'low': 0.31814, 'high': 0.31814}, 'unit': 'm3 CH4',
        'level': 'SCENARIO_ASSUMPTION', 'scenario': 's1'}}
    results = {'assess_substrate_potential': {'status': 'ok', 'scenarios': [{
        'id': 's1', 'result_level': 'HYPOTHETICAL_SCENARIO',
        'methane_m3': {'low': 0.31814, 'high': 0.31814},
        'engineering': {'status': 'GEOMETRY_ONLY_CONSISTENT'}}]}}
    draft = {'conclusion': 'Измерения показывают, что из 5 кг сырья получается 0,31814 м³ CH₄.',
        'explanation': 'Это предварительный расчёт.', 'limitations': [], 'next_question': None,
        'evidence_ids': ['s1.methane'], 'decision': 'not_applicable'}

    assert 'scenario_misrepresented_as_measurement' in validate_synthesis(draft, evidence, results, state)
    draft['conclusion'] = 'Условный расчёт по литературному профилю даёт 0,31814 м³ CH₄; это не измерение партии.'
    assert 'scenario_misrepresented_as_measurement' not in validate_synthesis(draft, evidence, results, state)


def test_fallback_names_recognized_mixture_materials_when_component_binding_is_ambiguous():
    query = ('\u041d\u0430\u0439\u0434\u0438 \u0432 \u043b\u0438\u0442\u0435\u0440\u0430\u0442\u0443\u0440\u0435 BMP-\u0434\u0438\u0430\u043f\u0430\u0437\u043e\u043d\u044b \u0434\u043b\u044f '
             '\u0441\u0432\u0435\u043a\u043b\u043e\u0432\u0438\u0447\u043d\u043e\u0433\u043e \u0436\u043e\u043c\u0430 \u0438 \u043f\u0448\u0435\u043d\u0438\u0447\u043d\u043e\u0439 \u0441\u043e\u043b\u043e\u043c\u044b, \u0441\u0440\u0430\u0432\u043d\u0438 \u043e\u0442\u0434\u0435\u043b\u044c\u043d\u043e \u0434\u043b\u044f \u043f\u0430\u0440\u0442\u0438\u0439 \u043f\u043e 3 \u043a\u0433.')
    state = parsed(query)
    results = {
        'assess_substrate_potential': {'status': 'needs_input', 'scenarios': [],
            'missing': ['material_identity_or_component_inventory']},
        'search_substrate_profiles': {'status': 'ok', 'dossiers': [
            {'material': 'beet_pulp', 'name': '\u0421\u0432\u0435\u043a\u043b\u043e\u0432\u0438\u0447\u043d\u044b\u0439 \u0436\u043e\u043c', 'studies': []},
            {'material': 'straw', 'name': '\u041f\u0448\u0435\u043d\u0438\u0447\u043d\u0430\u044f \u0441\u043e\u043b\u043e\u043c\u0430', 'studies': []}]}}

    explanation = ' '.join(fallback_explanations(results, state, query))

    assert '\u0421\u0432\u0435\u043a\u043b\u043e\u0432\u0438\u0447\u043d\u044b\u0439 \u0436\u043e\u043c' in explanation
    assert '\u041f\u0448\u0435\u043d\u0438\u0447\u043d\u0430\u044f \u0441\u043e\u043b\u043e\u043c\u0430' in explanation
    assert '\u043c\u0430\u0441\u0441\u0443 \u043a\u0430\u0436\u0434\u043e\u0433\u043e \u043a\u043e\u043c\u043f\u043e\u043d\u0435\u043d\u0442\u0430' in explanation
    assert '\u0412\u0438\u0434 \u0441\u044b\u0440\u044c\u044f \u0438\u043b\u0438 \u0441\u043e\u0441\u0442\u0430\u0432 \u0441\u043c\u0435\u0441\u0438 \u043d\u0435 \u043e\u043f\u0440\u0435\u0434\u0435\u043b\u0451\u043d' not in explanation


def test_incomplete_verification_keeps_profile_source_but_hides_derived_scenario_totals():
    evidence = {
        'profile.straw-A.bmp': {'id': 'profile.straw-A.bmp', 'level': 'LITERATURE',
            'label': 'Straw sample BMP', 'value': {'low': 214, 'high': 214}, 'unit': 'mL CH4/g VS'},
        's1.methane': {'id': 's1.methane', 'level': 'LITERATURE',
            'label': 'Calculated batch methane', 'value': {'low': 0.5, 'high': 0.7}, 'unit': 'm3 CH4'},
        'market.price.official.4': {'id': 'market.price.official.4', 'level': 'SOURCE_VERIFIED',
            'label': 'Official saved tariff', 'value': {'low': 20, 'high': 20}, 'unit': 'KZT/kWh'},
    }

    selected = partial_references(evidence, {}, safe_only=True)

    assert [row['id'] for row in selected] == ['profile.straw-A.bmp', 'market.price.official.4']


def test_quantity_verifier_keeps_hypothetical_values_separate_from_confirmed_facts():
    from src.agent.quantities9 import check

    prior = parsed('Новая партия: 4,5 кг соломы. Оцени потенциальный метан.')
    prompt = 'Гипотетически рассмотри 8 кг, не меняя подтверждённые 4,5 кг.'
    state = parsed(prompt, prior)

    assert state.value('quantity') == 4.5
    assert state.assumptions['quantity'].value == 8
    assert check(['Для сценария масса равна 8 кг.'], {}, [], state) == []
    assert 'ungrounded_quantity_or_wrong_unit' in check(
        ['Подтверждённая масса равна 9 кг.'], {}, [], state)


def test_missing_input_notes_are_human_readable_for_synthesis():
    result = {'status': 'needs_input', 'scenarios': [{
        'id': 's1', 'label': 'Солома', 'result_level': 'UNAVAILABLE',
        'profile_ids': [None], 'assumptions': [],
        'missing': ['bmp_ml_g_vs', 'ts_fraction', 'vs_fraction_wet'],
        'engineering': {'status': 'REQUIRES_REVIEW', 'total_volume_l': 60,
                        'missing': ['inoculum_volume_l', 'headspace_l'],
                        'violations': []},
        'biogas': {'potential_biogas_m3': None, 'methane_fraction': None,
                   'gas_basis': None, 'status': 'needs_input',
                   'compatibility': 'missing_documented_BMP_gas_basis',
                   'assumptions': [], 'scope': 'potential only',
                   'uncertainty': 'not calibrated'},
    }]}
    _, notes = collect({'assess_substrate_potential': result})
    rendered = json.dumps(notes, ensure_ascii=False)

    assert 'bmp_ml_g_vs' not in rendered
    assert 'ts_fraction' not in rendered
    assert 'inoculum_volume_l' not in rendered
    assert 'BMP' in rendered and 'сухого вещества' in rendered
    assert 'газового пространства' in rendered


def test_new_batch_synthesis_rejects_unrequested_profitability_topic():
    from src.agent.verification9 import validate_synthesis

    state = parsed('Начинаем новую партию: 7 кг молочной сыворотки, сосуд 80 л. Не смешивай с прошлой партией.')
    state.intents = ['process_guidance']
    draft = {'conclusion': 'Не хватает данных для оценки прибыльности.',
             'explanation': 'Для оценки прибыльности нужны расходы и доходы.',
             'limitations': ['Затраты не установлены.'],
             'next_question': 'Какие затраты и доходы учитывать?',
             'evidence_ids': [], 'decision': 'not_applicable'}

    issues = validate_synthesis(draft, {}, {}, state, new_batch=True)
    assert 'unrequested_economic_analysis' in issues

    state.intents = ['economic_comparison']
    assert 'unrequested_economic_analysis' not in validate_synthesis(
        draft, {}, {}, state, new_batch=True)


def test_new_batch_summary_confirms_current_typed_inputs_and_separation():
    from src.agent.batch_intent import confirmation, covers_confirmation

    state = parsed('Начинаем новую партию: 7 кг молочной сыворотки, сосуд 80 л. Не смешивай с прошлой партией.')
    state.task_history = [{'task_id': 'previous-batch'}]
    summary = confirmation(state)

    assert '7 кг' in summary
    assert '80 л' in summary
    assert 'сыворот' in summary
    assert 'отдельно' in summary
    assert not covers_confirmation('Не хватает данных для оценки прибыльности.', state)
    assert covers_confirmation(summary, state)


def test_batch_start_verb_without_adjective_triggers_clean_task_transition():
    from src.agent.batch_intent import starts_new_batch

    assert starts_new_batch('Начинаем партию: 6 кг свиного навоза.')
    assert not starts_new_batch('Для этой же партии уточняю состав.')
    first, _ = prepared('Новая партия: 3 кг соломы, реактор 60 л.')
    second, events = prepared('Начинаем партию: 6 кг свиного навоза, сосуд 100 л.', first)

    assert any(event['type'] == 'NewBatch' for event in events)
    assert second.value('material') == 'swine_manure'
    assert second.value('quantity') == 6
    assert second.value('reactor_total_volume_l') == 100
    assert second.value('quantity') != first.value('quantity')


def test_bak_volume_is_linked_to_reactor_not_feedstock_quantity():
    state, events = prepared('Начинаем другую партию: 6 кг свиного навоза, бак 100 л.')

    assert any(event['type'] == 'NewBatch' for event in events)
    assert state.value('material') == 'swine_manure'
    assert state.value('quantity') == 6 and state.value('unit') == 'kg'
    assert state.value('reactor_total_volume_l') == 100
    assert state.value('material_volume_l') is None


def test_non_analytical_new_batch_fallback_does_not_claim_numbers_failed():
    from src.agent.runtime9 import allow_optional_tools, fallback_heading

    extraction = extract('Начинаем партию: 6 кг свиного навоза, бак 100 л. Только сохрани параметры.')

    assert extraction.new_batch
    assert fallback_heading({}, {'status': 'not_applicable'}, [], new_batch=True) is None
    assert fallback_heading({'search_substrate_profiles': {'status': 'ok'}},
                            {'status': 'not_applicable'}, [], new_batch=True) is None
    assert fallback_heading({}, {'status': 'error'}, [], new_batch=True) == (
        'Численные результаты не прошли проверку; подробности доступны в диагностике.')
    assert not allow_optional_tools(extraction, [])
    assert allow_optional_tools(extraction, ['assess_substrate_potential'])


def test_sludge_scientific_fields_keep_their_roles_units_and_bases():
    text = ('30 кг осадка сточных вод, реактор 90 л; TS равен 18%, '
            'VS составляет 70% от TS, BMP равен 250 мл CH₄/г VS, температура 37 °C.')
    state = parsed(text)

    assert state.value('material') == 'wastewater_sludge'
    assert state.value('quantity') == 30 and state.value('unit') == 'kg'
    assert state.value('reactor_total_volume_l') == 90
    assert state.value('ts_percent') == 18
    assert state.value('vs_percent') == 70 and state.value('vs_basis') == 'TS'
    assert state.value('bmp_ml_ch4_g_vs') == 250
    assert state.value('temperature_c') == 37
    context = tool_context(state)
    for key in ('ts_percent', 'vs_percent', 'vs_basis', 'bmp_ml_ch4_g_vs', 'temperature_c'):
        assert context[key] == state.value(key)


def test_measured_gas_volume_and_methane_fraction_are_not_feedstock_amounts():
    state = parsed('Измерено 0,42 м³ сырого биогаза; доля CH₄ равна 58%.')

    assert state.value('reported_biogas_volume_m3') == 0.42
    assert state.value('methane_fraction') == 0.58
    assert state.value('quantity') is None
    assert tool_context(state)['reported_biogas_volume_m3'] == 0.42
    assert tool_context(state)['methane_fraction'] == 0.58


def test_instrument_wording_keeps_measured_gas_balance_out_of_bmp_route():
    text = ('Мои приборы измерили 0.42 м³ сырого биогаза и 58% CH₄ на той же сухой базе. '
            'Рассчитай измеренный объём CH₄, укажи, что это баланс измерений, а не BMP.')
    state = parsed(text)

    assert state.value('reported_biogas_volume_m3') == 0.42
    assert state.value('methane_fraction') == 0.58
    assert 'assess_substrate_potential' not in requirements(state, text)
    rows = explicit_calculations(state)['calculations']
    assert rows[0]['kind'] == 'measured_methane_balance_m3'
    assert rows[0]['value'] == pytest.approx(0.2436)


def test_explicit_energy_inputs_are_typed_and_hypothetical():
    state = parsed('Условный расчёт: 0,10 м³ CH₄, LHV 9,97 kWh/m³, электрический КПД 30%.')

    assert any_input(state, 'reported_methane_volume_m3').value == 0.10
    assert any_input(state, 'heating_value_kwh_m3').value == 9.97
    assert any_input(state, 'electricity_efficiency').value == 0.30
    assert all(state.assumptions[key].provenance == 'ASSUMED_FOR_SCENARIO'
               for key in ('reported_methane_volume_m3', 'heating_value_kwh_m3', 'electricity_efficiency'))
    assert 'electricity_efficiency' not in tool_context(state)


def test_measured_input_and_explicit_assumption_keep_separate_provenance():
    text = 'Измеренная масса VS 0,6 кг; в условном расчёте принимаю BMP 250 мл CH₄/г VS.'
    state = parsed(text)

    assert state.facts['vs_mass_kg'].provenance == 'USER_CONFIRMED'
    assert state.assumptions['bmp_ml_ch4_g_vs'].provenance == 'ASSUMED_FOR_SCENARIO'


def test_complete_explicit_formulas_return_partial_arithmetic_without_feedstock_profiles():
    cases = [
        ('Молокозавод предлагает 25 кг сыворотки по 40 тенге за кг.', 'sale_gross_value_kzt', 1000),
        ('Измеренная масса VS 0,6 кг; условно принимаю BMP 250 мл CH₄/г VS.', 'methane_potential_m3', 0.15),
        ('Измерено 0,42 м³ сырого биогаза; доля CH₄ равна 58%.', 'measured_methane_balance_m3', 0.2436),
        ('Условный расчёт: 0,10 м³ CH₄, LHV 9,97 kWh/m³, электрический КПД 30%.', 'electricity_kwh', 0.2991),
    ]
    for prompt, kind, expected in cases:
        state = parsed(prompt)
        result = explicit_calculations(state)
        row = next(item for item in result['calculations'] if item['kind'] == kind)
        assert row['value'] == pytest.approx(expected)
        assert row['provenance'] in {'CALCULATED_FROM_CONFIRMED', 'ASSUMED_FOR_SCENARIO'}
        from src.agent.verification9 import verify_results
        verification = verify_results({'explicit_calculations': result})
        assert verification['status'] == 'ok' and verification['all_checks_passed']


def test_named_components_are_bound_to_their_own_quantities_and_forms():
    from src.agent.mixture_parser import explicit_components

    components = explicit_components(
        'Сравни 3 кг жидкого свекловичного жома и 3 кг сухой пшеничной соломы.')

    assert [(c.material, c.quantity, c.unit) for c in components] == [
        ('beet_pulp', 3, 'kg'), ('straw', 3, 'kg')]
    assert components[0].material_state == 'slurry'
    assert components[1].material_state == 'dry'


def test_corrections_and_new_batches_do_not_reuse_old_material_data():
    first,_ = prepared('У меня 5 кг пищевых отходов, TS 20%.')
    corrected,_ = prepared('Исправление: не 5 кг, а 7 кг пищевых отходов.', first)
    assert corrected.value('quantity') == 7
    assert corrected.value('material') == 'food_waste'

    from src.agent.dialogue_memory import fact
    corrected.facts['bmp_ml_ch4_g_vs'] = fact(300, 'mL CH4/g VS', evidence='test prior batch')
    newer,events = prepared('Начинаем новую партию: 4 кг измельчённой пшеничной соломы, реактор 60 л.', corrected)
    assert newer.value('material') == 'straw'
    assert newer.value('quantity') == 4 and newer.value('reactor_total_volume_l') == 60
    assert newer.value('ts_percent') is None and newer.value('bmp_ml_ch4_g_vs') is None
    assert any(event['type']=='NewBatch' for event in events)


def test_new_batch_binds_feedstock_around_vessel_capacity_and_excludes_prior_material():
    text = ('\u041d\u0430\u0447\u0438\u043d\u0430\u0435\u043c \u0434\u0440\u0443\u0433\u0443\u044e \u043f\u0430\u0440\u0442\u0438\u044e: 7 \u043a\u0433 \u043c\u043e\u043b\u043e\u0447\u043d\u043e\u0439 \u0441\u044b\u0432\u043e\u0440\u043e\u0442\u043a\u0438, \u0441\u043e\u0441\u0443\u0434 80 \u043b. '
            '\u041d\u0435 \u0441\u043c\u0435\u0448\u0438\u0432\u0430\u0439 \u0435\u0451 \u0441 \u043f\u0440\u0435\u0434\u044b\u0434\u0443\u0449\u0435\u0439 \u0441\u043e\u043b\u043e\u043c\u043e\u0439.')
    state, events = prepared(text)

    assert state.value('material') == 'dairy_waste'
    assert state.value('quantity') == 7 and state.value('unit') == 'kg'
    assert state.value('reactor_total_volume_l') == 80
    assert state.value('material_volume_l') is None
    assert any(event['type'] == 'NewBatch' for event in events)

    from src.agent.mixture_parser import explicit_components
    components = explicit_components(text)
    assert [(c.material, c.quantity, c.unit) for c in components] == [('dairy_waste', 7, 'kg')]


def test_reference_to_same_new_batch_preserves_state_and_detects_conflicting_quantities():
    first_text = ('\u041d\u043e\u0432\u0430\u044f \u043f\u0430\u0440\u0442\u0438\u044f: 7 \u043a\u0433 \u043c\u043e\u043b\u043e\u0447\u043d\u043e\u0439 \u0441\u044b\u0432\u043e\u0440\u043e\u0442\u043a\u0438, \u0441\u043e\u0441\u0443\u0434 80 \u043b.')
    current, _ = prepared(first_text)
    task_id = current.task_id
    conflict_text = ('\u0414\u043b\u044f \u044d\u0442\u043e\u0439 \u0436\u0435 \u043d\u043e\u0432\u043e\u0439 \u043f\u0430\u0440\u0442\u0438\u0438 \u044f \u043d\u0430\u0437\u0432\u0430\u043b \u0438 7 \u043a\u0433, \u0438 9 \u043a\u0433 \u0441\u044b\u0432\u043e\u0440\u043e\u0442\u043a\u0438. '
                    '\u041d\u0435 \u0432\u044b\u0431\u0438\u0440\u0430\u0439 \u0447\u0438\u0441\u043b\u043e \u0437\u0430 \u043c\u0435\u043d\u044f: \u0437\u0430\u0444\u0438\u043a\u0441\u0438\u0440\u0443\u0439 \u043a\u043e\u043d\u0444\u043b\u0438\u043a\u0442 \u0438 \u0443\u0442\u043e\u0447\u043d\u0438 \u043c\u0430\u0441\u0441\u0443.')
    extraction = extract(conflict_text, current)

    assert extraction.new_batch is False
    unchanged, events, issues = __import__('src.agent.task_state', fromlist=['prepare']).prepare(conflict_text, current, extraction)
    assert issues and issues[0]['type'] == 'ConflictingValuesInSameRequest'
    assert unchanged.task_id == task_id
    assert unchanged.value('material') == 'dairy_waste'
    assert unchanged.value('quantity') == 7 and unchanged.value('reactor_total_volume_l') == 80


def test_omitted_material_correction_and_hypothetical_mass_keep_inventory_scoped():
    from src.agent.advanced_conversation import parse
    from src.agent.dialogue_types import DialogueState

    start = ('\u041d\u043e\u0432\u0430\u044f \u043f\u0430\u0440\u0442\u0438\u044f: 2,2 \u043a\u0433 \u0432\u043b\u0430\u0436\u043d\u043e\u0439 \u043f\u0448\u0435\u043d\u0438\u0447\u043d\u043e\u0439 \u0441\u043e\u043b\u043e\u043c\u044b, \u0440\u0435\u0430\u043a\u0442\u043e\u0440 75 \u043b.')
    correction = ('\u041f\u043e\u043f\u0440\u0430\u0432\u043a\u0430 \u043a \u044d\u0442\u043e\u0439 \u043f\u0430\u0440\u0442\u0438\u0438: \u0444\u0430\u043a\u0442\u0438\u0447\u0435\u0441\u043a\u0430\u044f \u043c\u0430\u0441\u0441\u0430 2,6 \u043a\u0433, \u0430 \u043d\u0435 2,2. \u041f\u0435\u0440\u0435\u0441\u0447\u0438\u0442\u0430\u0439, \u043f\u0440\u0435\u0436\u043d\u044e\u044e \u043c\u0430\u0441\u0441\u0443 \u0437\u0430\u043c\u0435\u043d\u0438.')
    hypothetical = ('\u0414\u043b\u044f \u0441\u0440\u0430\u0432\u043d\u0435\u043d\u0438\u044f \u0433\u0438\u043f\u043e\u0442\u0435\u0442\u0438\u0447\u0435\u0441\u043a\u0438 \u0432\u043e\u0437\u044c\u043c\u0438 5 \u043a\u0433, \u043d\u0435 \u0437\u0430\u043f\u0438\u0441\u044b\u0432\u0430\u044f \u044d\u0442\u043e \u043a\u0430\u043a \u043d\u043e\u0432\u0443\u044e \u043f\u043e\u0434\u0442\u0432\u0435\u0440\u0436\u0434\u0451\u043d\u043d\u0443\u044e \u043c\u0430\u0441\u0441\u0443.')
    state = DialogueState()
    data = {}
    assert parse(start, state, data) == (True, True)
    assert data['inventory'][0]['quantity'] == 2.2

    assert parse(correction, state, data)[0]
    assert data['inventory'][0]['quantity'] == 2.6

    assert parse(hypothetical, state, data)[0]
    assert data['inventory'][0]['quantity'] == 2.6
    assert data['scenario'][0]['quantity'] == 5
    assert data['active_scenario'] is True


def test_hypothetical_wording_sets_assumed_provenance_without_changing_confirmed_mass():
    confirmed = parsed('\u0423 \u043c\u0435\u043d\u044f 2,6 \u043a\u0433 \u043f\u0448\u0435\u043d\u0438\u0447\u043d\u043e\u0439 \u0441\u043e\u043b\u043e\u043c\u044b.')
    state, _ = prepared('\u0414\u043b\u044f \u0441\u0440\u0430\u0432\u043d\u0435\u043d\u0438\u044f \u0433\u0438\u043f\u043e\u0442\u0435\u0442\u0438\u0447\u0435\u0441\u043a\u0438 \u0432\u043e\u0437\u044c\u043c\u0438 5 \u043a\u0433.', confirmed)

    assert state.facts['quantity'].value == 2.6
    assert state.assumptions['quantity'].value == 5
    assert state.assumptions['quantity'].provenance == 'ASSUMED_FOR_SCENARIO'


def test_referenced_confirmed_mass_is_not_reparsed_as_a_second_hypothesis():
    confirmed = parsed('\u041d\u043e\u0432\u0430\u044f \u043f\u0430\u0440\u0442\u0438\u044f: 4,5 \u043a\u0433 \u043f\u0448\u0435\u043d\u0438\u0447\u043d\u043e\u0439 \u0441\u043e\u043b\u043e\u043c\u044b.')
    text = ('\u0410 \u0435\u0441\u043b\u0438 \u0433\u0438\u043f\u043e\u0442\u0435\u0442\u0438\u0447\u0435\u0441\u043a\u0438 \u0431\u044b\u043b\u043e \u0431\u044b 8 \u043a\u0433? '
            '\u041e\u0442\u0432\u0435\u0442\u044c \u043a\u0430\u043a \u0441\u0446\u0435\u043d\u0430\u0440\u0438\u0439, \u043d\u0435 \u0437\u0430\u043c\u0435\u043d\u044f\u044f \u0437\u0430\u043f\u0438\u0441\u0430\u043d\u043d\u0443\u044e \u043c\u0430\u0441\u0441\u0443 4,5 \u043a\u0433.')
    extraction = extract(text, confirmed)
    quantity_entities = [e for e in extraction.entities if e.name == 'quantity']

    assert [(e.value, e.provenance) for e in quantity_entities] == [(8, 'ASSUMED_FOR_SCENARIO')]
    state, _ = prepared(text, confirmed)
    assert state.facts['quantity'].value == 4.5
    assert state.assumptions['quantity'].value == 8
    assert state.assumptions['quantity'].provenance == 'ASSUMED_FOR_SCENARIO'


def test_volume_density_reactor_volume_and_physical_form_keep_distinct_roles():
    state,_ = prepared('5 м³ жидкого коровьего навоза, плотность 1,013 кг/л, реактор 6 м³, рабочий объём 5 м³.')
    assert state.value('quantity') == 5 and state.value('unit') == 'm3'
    assert state.value('material_volume_l') == 5000
    assert state.value('reactor_total_volume_l') == 6000
    assert state.value('reactor_working_volume_l') == 5000
    assert state.value('density_kg_l') == pytest.approx(1.013)
    assert state.value('mass_kg') == pytest.approx(5065)
    assert state.value('material_state') == 'slurry'


def test_hypothetical_scenario_does_not_overwrite_confirmed_temperature():
    confirmed,_ = prepared('Измеренная температура содержимого 37 °C.')
    scenario,_ = prepared('Условный сценарий: температура 40 °C.',confirmed)
    assert scenario.facts['temperature_c'].value == 37
    assert scenario.assumptions['temperature_c'].value == 40
    assert scenario.assumptions['temperature_c'].provenance == 'ASSUMED_FOR_SCENARIO'


def test_profile_questions_require_catalog_evidence_without_forcing_economics():
    text = 'Для 10 кг сухого яблочного жмыха проверь точное покрытие научным каталогом.'
    state = parsed(text)
    required = requirements(state, text)
    optional = obligations(state, text)

    assert 'search_substrate_profiles' in required
    assert 'assess_substrate_potential' not in required
    assert 'evaluate_partial_economics' not in required
    assert 'search_substrate_profiles' in optional


def test_unrecognized_material_search_does_not_return_unrelated_core_profiles():
    from src.research.dossiers import search
    result = search([], '12 kg onion peel scientific methane profile')
    assert result['status'] == 'needs_input'
    assert result['dossiers'] == []
    assert result['missing'] == ['recognized_material_or_explicit_analogue_request']


def test_reviewed_profile_measurements_remain_citable_after_synthesis_fallback():
    from src.agent.evidence9 import collect, partial_references, render_reference
    from src.agent.quantities9 import check

    results = {'search_substrate_profiles': {'status': 'ok', 'dossiers': [{
        'material': 'straw', 'name': 'Straw', 'studies': [{
            'profile_id': 'straw-study-A', 'source_id': 'reviewed-straw-study',
            'physical_state': 'dry', 'preparation': 'Dried and milled sample',
            'bmp_ml_g_vs': {'low': 214, 'high': 214,
                            'locator': 'Tables 2 and 7; paired BMP observation'},
            'quality': 'Reviewed extraction of a published experiment',
            'transfer_limitations': 'Sample-specific; not a measurement of the user batch.'
        }]}]}}

    evidence, notes = collect(results)
    key = 'profile.straw-study-A.bmp'
    assert evidence[key]['value'] == {'low': 214, 'high': 214}
    assert evidence[key]['unit'] == 'mL CH4/g VS'
    assert evidence[key]['level'] == 'LITERATURE'
    assert evidence[key]['source_locator'] == 'Tables 2 and 7; paired BMP observation'
    assert key in {row['id'] for row in partial_references(evidence, results)}
    rendered = render_reference(evidence[key])
    assert '214' in rendered and '\u043b\u0438\u0442\u0435\u0440\u0430\u0442\u0443\u0440\u043d\u044b\u0435 \u0434\u0430\u043d\u043d\u044b\u0435' in rendered
    assert 'Dried and milled sample' in rendered
    assert check([rendered], evidence, [key]) == []
    assert 'ungrounded_quantity_or_wrong_unit' in check(
        ['0.214 m3 CH4/kg VS'], evidence, [key])


def test_profile_search_canonical_bmp_field_is_projected_to_literature_evidence():
    results = {'search_substrate_profiles': {'status': 'ok', 'dossiers': [{
        'material': 'straw', 'name': 'Wheat straw', 'studies': [{
            'profile_id': 'catalog-shape-A', 'source_id': 'reviewed-source',
            'bmp_ml_ch4_g_vs': {'low': 214, 'high': 214, 'locator': 'Table 2'},
            'physical_state': 'dry', 'preparation': 'Dried and milled sample',
        }]}]}}

    evidence, _ = collect(results)

    assert evidence['profile.catalog-shape-A.bmp']['value'] == {'low': 214, 'high': 214}
    assert evidence['profile.catalog-shape-A.bmp']['unit'] == 'mL CH4/g VS'


def test_required_market_tool_is_the_only_model_choice_and_survives_synthesis_failure():
    class PriceRegistry(ToolRegistry):
        def _execute(self, name, *args):
            if name == 'get_market_prices':
                return {'status': 'ok', 'prices': [{
                    'id': 16, 'source_id': 'official', 'source_name': 'official reference',
                    'commodity': 'electricity', 'normalized_value': '20.39', 'normalized_unit': 'kWh',
                    'currency': 'KZT', 'published_at': '2026-10-09', 'effective_from': '2026-09-30',
                    'age_days': 38, 'region': 'KZ-Karaganda', 'is_stale': True,
                    'usable_as_current': False, 'reliability': 'verified_official', 'is_test': 0,
                }]}
            return super()._execute(name, *args)

    provider = JSONProvider('offline', model='qwen3:8b')
    provider.extract_dialogue = lambda *args: NLUProposal(
        language='ru', intents=['market_prices'], material=None, material_evidence=None, entities=[])
    available = []
    def timeout_after_planning(messages, schema):
        if 'action' in schema.get('properties', {}):
            payload = json.loads(messages[-1]['content'])
            available.extend(item['name'] for item in payload['tools'])
        raise ProviderError('TEST controlled synthesis timeout')
    provider.generate = timeout_after_planning
    agent = ConversationAgent(research_enabled=True, llm=HybridLLM('offline', providers=[provider]), registry=PriceRegistry())
    agent.runtime_version = '9'

    reply = agent.ask('Проверь сохранённую цену электроэнергии для Караганды и сообщи, можно ли считать её текущей.')

    assert available == ['get_market_prices']
    assert any(item['tool'] == 'get_market_prices' for item in reply['tools'])
    assert '20.39 KZT/kWh' in reply['answer']
    assert '2026-10-09' in reply['answer'] and '38' in reply['answer']
    assert 'устарел' in reply['answer']
    assert reply['technical_metadata']['verification']['status'] == 'not_applicable'


def test_unsupported_model_claim_does_not_erase_verified_market_evidence():
    class PriceRegistry(ToolRegistry):
        def _execute(self, name, *args):
            if name == 'get_market_prices':
                return {'status': 'ok', 'prices': [{
                    'id': 16, 'source_id': 'official', 'source_name': 'official reference',
                    'commodity': 'electricity', 'normalized_value': '20.39', 'normalized_unit': 'kWh',
                    'currency': 'KZT', 'published_at': '2026-10-09', 'effective_from': '2026-09-30',
                    'age_days': 38, 'region': 'KZ-Karaganda', 'is_stale': True,
                    'usable_as_current': False, 'reliability': 'verified_official', 'is_test': 0,
                }]}
            return super()._execute(name, *args)

    provider = JSONProvider('offline', model='qwen3:8b')
    provider.extract_dialogue = lambda *args: NLUProposal(
        language='ru', intents=['market_prices'], material=None, material_evidence=None, entities=[])
    calls = {'actions': 0, 'synthesis': 0}
    def inaccurate_then_timeout(messages, schema):
        if 'action' in schema.get('properties', {}):
            calls['actions'] += 1
            if calls['actions'] == 1:
                return {'action': 'tool', 'tool': 'get_market_prices', 'arguments': {},
                    'purpose': 'Inspect the saved tariff', 'ready_after_tool': True}
            return {'action': 'answer', 'tool': '', 'arguments': {},
                'purpose': 'Evidence is available', 'ready_after_tool': False}
        calls['synthesis'] += 1
        if calls['synthesis'] > 1:raise ProviderError('TEST repair timeout')
        evidence_ids=schema['properties']['evidence_ids'].get('items',{}).get('enum',[])
        return {'conclusion':'The current tariff is 999 KZT/kWh.', 'explanation':'This value is unsupported.',
            'limitations':[], 'next_question':None, 'evidence_ids':evidence_ids[:1], 'decision':'not_applicable'}
    provider.generate = inaccurate_then_timeout
    agent = ConversationAgent(research_enabled=True, llm=HybridLLM('offline', providers=[provider]), registry=PriceRegistry())
    agent.runtime_version = '9'

    reply = agent.ask('Проверь сохранённую цену электроэнергии для Караганды и сообщи, можно ли считать её текущей.')

    assert '20.39 KZT/kWh' in reply['answer']
    assert '999 KZT/kWh' not in reply['answer']
    assert 'устарел' in reply['answer']
    assert reply['technical_metadata']['diagnostics']


def test_raw_biogas_tariff_question_does_not_require_a_feedstock_bmp():
    text = ('Можно ли оценивать сырое биогазовое топливо по тарифу природного газа, '
            'или нужны состав и отдельная цена продажи?')
    state = parsed(text)

    assert 'assess_substrate_potential' not in requirements(state, text)
    assert 'evaluate_partial_economics' not in requirements(state, text)


def test_unknown_optional_fact_is_not_sent_as_a_numeric_tool_input():
    state = DialogueState(pending_question=Question(id='sale_offer', text='Sale quote?', fields=['sale_offer_amount']))
    state.facts['sale_offer_amount'] = fact(None, provenance='UNKNOWN', evidence='User said the quote is unknown')
    assert 'sale_offer_amount' not in tool_context(state)


def test_unquantified_methane_question_still_checks_missing_scientific_inputs():
    text = 'Сколько метана получится из неизвестного сырья?'
    state = parsed(text)
    assert 'assess_substrate_potential' in requirements(state, text)


def test_partial_references_keep_source_verified_market_rows_after_model_rejection():
    results = {'get_market_prices': {'status': 'ok', 'prices': [{
        'id': 16, 'commodity': 'electricity', 'normalized_value': 20.39,
        'normalized_unit': 'kWh', 'currency': 'KZT', 'published_at': '2026-10-09',
        'age_days': 38, 'region': 'KZ-Karaganda', 'is_stale': True,
        'usable_as_current': False, 'reliability': 'verified_official', 'is_test': 0,
        'source_name': 'official reference',
    }]}}
    evidence, _ = collect(results)
    refs = partial_references(evidence, results)

    assert any(ref['value']['low'] == 20.39 and ref['level'] == 'SOURCE_VERIFIED' for ref in refs)
    assert any(ref.get('price_context', {}).get('is_stale') is True for ref in refs)


def test_price_reference_shows_effective_date_and_age_when_publication_date_is_missing():
    rendered = render_reference({
        'label': 'Official electricity tariff', 'value': {'low': 20.39, 'high': 20.39},
        'unit': 'KZT/kWh', 'level': 'SOURCE_VERIFIED',
        'price_context': {'published_at': None, 'effective_from': '2026-09-30',
            'age_days': 38, 'region': 'KZ-Karaganda', 'is_stale': True},
    })

    assert 'дата публикации не установлена' in rendered
    assert '2026-09-30' in rendered and '38 дн.' in rendered
    assert 'устарел, текущий тариф не подтверждён' in rendered


def test_partial_science_fallback_names_missing_properties_without_internal_keys():
    state = DialogueState(language='ru')
    results = {'assess_substrate_potential': {'status': 'needs_input', 'scenarios': [{
        'missing': ['bmp_ml_g_vs', 'ts_fraction', 'vs_fraction_wet'],
        'components': [{'wet_mass_kg': {'low': 25, 'high': 25},
            'missing': ['density_kg_l', 'ts_fraction', 'vs_fraction_wet', 'bmp_ml_g_vs']}],
    }]}}

    explanation = ' '.join(fallback_explanations(results, state))

    assert 'содержание сухого вещества (TS)' in explanation
    assert 'доля VS во влажной массе' in explanation
    assert 'BMP в мл CH₄/г VS' in explanation
    assert 'density_kg_l' not in explanation and 'bmp_ml_g_vs' not in explanation
    assert 'плотность' not in explanation


def test_digestate_fertilizer_question_uses_product_valuation_route_not_bmp_route():
    text='После переработки останется 80 л дигестата. Можно ли считать его удобрением и приписать ему цену минерального NPK без анализа состава?'
    state=parsed(text)
    state.assumptions['market_region']=fact('KZ-Karaganda',provenance='ASSUMED_FOR_SCENARIO',evidence='Default dashboard region')

    assert 'digestate_management' in state.intents
    assert state.value('market_commodity')=='digestate'
    assert state.value('quantity')==80 and state.value('unit')=='L'
    required=requirements(state,text)
    assert required==['get_market_prices','search_scientific_sources','assess_scientific_risks']
    assert 'assess_substrate_potential' not in required
    assert 'evaluate_partial_economics' not in required
    assert obligations(state,text)==[]


def test_digestate_fallback_preserves_volume_and_rejects_mineral_price_substitution():
    from src.agent.market_response import digestate_valuation_explanation
    text='После переработки останется 80 л дигестата. Можно ли считать его удобрением и приписать ему цену минерального NPK без анализа состава?'
    state=parsed(text)
    state.assumptions['market_region']=fact('KZ-Karaganda',provenance='ASSUMED_FOR_SCENARIO',evidence='Default dashboard region')
    results={
        'get_market_prices':{'status':'needs_input','prices':[],'missing':['verified_market_observations']},
        'search_scientific_sources':{'status':'ok','sources':[],'claims':[],'live_web_search':False},
        'assess_scientific_risks':{'status':'ok','materials':[],'sources':[]},
    }
    answer=digestate_valuation_explanation(results,state)

    assert '80 л' in answer
    assert 'цену минерального NPK' in answer
    assert 'не вернула подходящей цены' in answer
    assert 'не установлены' in answer
    assert 'анализ' in answer
    assert 'выбранного системой по умолчанию' in answer
    assert 'Какие значения сухого вещества и N/P/K показал анализ' in answer
    assert not any(token in answer for token in ('KZT','тенге','₸'))


def test_digestate_answer_coverage_detects_omitted_volume_and_market_result():
    from src.agent.market_response import digestate_answer_covers
    state=parsed('После переработки останется 80 л дигестата. Можно ли приписать ему цену минерального NPK?')
    results={'get_market_prices':{'status':'needs_input','prices':[]}}
    assert not digestate_answer_covers('Без анализа нельзя приравнять дигестат к NPK.',results,state)
    assert digestate_answer_covers('Объём 80 л. Нельзя приравнять его к цене NPK; рыночная цена не найдена.',results,state)


def test_unverified_regulatory_claim_is_rejected_without_source_evidence():
    from src.agent.autonomous import _unsupported_conclusions
    assert 'unverified_regulatory_claim_without_source' in _unsupported_conclusions(
        'Дигестат требует специального разрешения и соответствия стандартам.',
        {'search_scientific_sources':{'status':'ok','sources':[{'title':'Anaerobic plant design and control','url':'https://example.test'}]}})
    assert 'unverified_regulatory_claim_without_source' not in _unsupported_conclusions(
        'Дигестат требует специального разрешения.',
        {'search_scientific_sources':{'status':'ok','sources':[{'title':'KZ digestate fertilizer regulation','url':'https://example.test/organic-fertilizer-regulation'}]}})


def test_legacy_reply_exposes_and_persists_structured_clarification():
    class DigestateRegistry(ToolRegistry):
        def _execute(self,name,*args):
            if name=='get_market_prices':return {'status':'needs_input','message':'No applicable quote','prices':[]}
            if name=='search_scientific_sources':return {'status':'ok','message':'No matching local sources','sources':[],'claims':[]}
            if name=='assess_scientific_risks':return {'status':'ok','message':'No measurements','materials':[],'sources':[]}
            return super()._execute(name,*args)

    provider=JSONProvider('offline',model='qwen3:8b')
    provider.extract_dialogue=lambda *args:NLUProposal(language='ru',intents=['digestate_management','market_prices'],
        material=None,material_evidence=None,entities=[])
    def choose_tool(question,facts,memory,history,observations,allowed_tools,final_only=False):
        if final_only:return {'action':'final','tool':None,'arguments':{},'final':'The regional digestate price is not established.'}
        return {'action':'call_tool','tool':allowed_tools[0],'arguments':{},'final':''}
    provider.autonomous_action=choose_tool
    agent=ConversationAgent(research_enabled=True,llm=HybridLLM('offline',providers=[provider]),registry=DigestateRegistry())

    reply=agent.ask('Осталось 80 л дигестата. Можно ли приписать ему цену NPK без анализа?')

    question=reply['user_facing_answer']['question']
    assert question and 'Какие значения сухого вещества' in question['text']
    assert reply['pending_question']==question
    assert reply['memory']['pending_question']==question


def test_legacy_agent_offers_mandatory_tools_before_optional_retrieval():
    from src.agent.autonomous import _required_tool_choices
    unmet=['assess_substrate_potential','evaluate_partial_economics','get_market_prices']
    offered=unmet+['search_scientific_sources','verify_scientific_sources','get_reactor_status']

    first=_required_tool_choices(unmet,offered,{})
    assert first==['assess_substrate_potential','get_market_prices']
    after_science=_required_tool_choices(unmet,offered,{
        'assess_substrate_potential':{'status':'partial','scenarios':[]}})
    assert after_science==unmet
    assert _required_tool_choices([],offered,{})==offered
