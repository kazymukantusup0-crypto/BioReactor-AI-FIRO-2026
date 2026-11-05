"""Stage 8.4 live HTTP checks against local Qwen3 8B and isolated SQLite.

Run only while the isolated v8.4 dashboard server is listening on :8768.
The payloads are user scenarios, not market quotes or experimental data.
"""
import json
import urllib.error
import urllib.request
import uuid
from pathlib import Path

BASE = 'http://127.0.0.1:8768'
OUT = Path('reports/stage8_4/live_qwen_cases.json')
records = []


def request(method, path, payload=None, timeout=180):
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(BASE + path, data=data,
        headers={'Content-Type': 'application/json'}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as exc:
        return exc.code, json.load(exc)


def session():
    code, value = request('POST', '/api/dashboard/chat/sessions',
        {'mode': 'offline', 'context': {}, 'conversation_version': '7'})
    assert code == 201, value
    return value['id']


def turn(identifier, message):
    code, value = request('POST', f'/api/dashboard/chat/sessions/{identifier}/messages',
        {'message': message, 'request_id': str(uuid.uuid4())})
    assert code == 200, value
    return value


def record(name, message, result, checks, require_qwen=True):
    provider = result.get('provider_status', [])
    generated = any(p.get('model') == 'qwen3:8b' and p.get('actual_generation') is True for p in provider)
    if require_qwen:
        checks = dict(checks, live_qwen3_8b=generated, qwen_mode=result.get('mode') == 'qwen_autonomous_tools')
    passed = all(checks.values())
    records.append({'id': name, 'prompt': message, 'passed': passed, 'checks': checks,
        'answer': result.get('answer'), 'sections': result.get('user_facing_answer', {}).get('sections'),
        'clarification': result.get('user_facing_answer', {}).get('question'),
        'tools': [{'tool': item.get('tool'), 'status': item.get('status')} for item in result.get('tools', [])],
        'memory': result.get('memory'), 'provider_status': provider})
    OUT.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')
    print(name, 'PASS' if passed else 'FAIL', checks, flush=True)
    assert passed, name
    return result


def live_tool(result, name):
    return next((x.get('result') for x in result.get('tools', []) if x.get('tool') == name), None)


if __name__ == '__main__':
    OUT.parent.mkdir(parents=True, exist_ok=True)
    # 1: First-turn science/economics, then a short inflected oblast reply.
    sid = session()
    first_text = 'У меня 5 кг пищевых отходов и реактор объёмом 90 литров. Сколько метана можно получить и выгодно ли его производить?'
    first = turn(sid, first_text)
    science = live_tool(first, 'assess_substrate_potential')
    assert science and science.get('scenarios')
    methane = science['scenarios'][0].get('methane_m3')
    assert methane and abs(methane['low'] - 0.318140715815) < 1e-8
    record('01_first_science_economics', first_text, first, {
        'science_tool_called': science is not None,
        'methane_potential_0_31814': methane is not None and abs(methane['low'] - 0.318140715815) < 1e-8,
        'nominal_reactor_explained': any('90' in s['body'] for s in first.get('user_facing_answer', {}).get('sections', [])),
        'has_compact_answer': len(first.get('user_facing_answer', {}).get('sections', [])) >= 4,
        'asks_region_when_not_yet_known': first.get('user_facing_answer', {}).get('question', {}).get('id') == 'market-region'})
    region_text = 'В Карагандинской'
    second = turn(sid, region_text)
    confirmed = second.get('memory', {}).get('facts', {}).get('market_region', {})
    record('02_oblast_reply_saved_and_used', region_text, second, {
        'region_saved': confirmed.get('value') == 'KZ-Karaganda-oblast',
        'region_confirmed': confirmed.get('provenance') == 'USER_CONFIRMED',
        'no_region_question': second.get('user_facing_answer', {}).get('question', {}).get('id') != 'market-region',
        'market_economics_rechecked': any(x.get('tool') in {'evaluate_partial_economics', 'get_market_prices', 'compare_market_scenarios'} for x in second.get('tools', []))})
    changed = turn(sid, 'Теперь регион Алматы.')
    value = changed.get('memory', {}).get('facts', {}).get('market_region', {}).get('value')
    record('03_region_correction', 'Теперь регион Алматы.', changed, {'region_updated': value == 'KZ-Almaty'})

    # 2: Quantity correction invalidates dependent methane estimate.
    sid2 = session()
    turn(sid2, 'У меня 50 кг пищевых отходов. Сколько метана?')
    corrected = turn(sid2, 'Исправление: 5 кг.')
    facts = corrected.get('memory', {}).get('facts', {})
    science2 = live_tool(corrected, 'assess_substrate_potential')
    methane2 = science2['scenarios'][0]['methane_m3'] if science2 and science2.get('scenarios') else None
    record('04_mass_correction_50_to_5', 'Исправление: 5 кг.', corrected, {
        'quantity_is_5': facts.get('quantity', {}).get('value') == 5,
        'unit_is_kg': facts.get('unit', {}).get('value') == 'kg',
        'recalculated_5kg': methane2 is not None and abs(methane2['low'] - 0.318140715815) < 1e-8})

    # 3: Reactor volume changes without overwriting feed quantity.
    sid3 = session()
    turn(sid3, 'У меня 5 кг пищевых отходов и реактор 90 литров. Сколько метана?')
    capacity = turn(sid3, 'Нет, реактор 120 литров.')
    facts3 = capacity.get('memory', {}).get('facts', {})
    record('05_reactor_volume_correction', 'Нет, реактор 120 литров.', capacity, {
        'reactor_volume_120': facts3.get('reactor_total_volume_l', {}).get('value') == 120,
        'quantity_preserved_5': capacity.get('memory', {}).get('derived', {}).get('mass_kg', {}).get('value') == 5})

    # 4: The exact same explicit batch through Dashboard's public analysis API
    # and the chat's shared scientific tool contract.
    payload = {'components': [{'id': 'c1', 'material': 'food_waste', 'quantity': 5, 'unit': 'kg', 'material_state': 'unknown'}],
        'reactor_total_volume_l': 90, 'region': 'KZ-Karaganda-oblast', 'region_confirmed': True,
        'allow_conditional_profiles': True, 'allow_literature_transfer': True, 'assume_common_dry_gas_basis': True}
    code, dashboard = request('POST', '/api/advisor/analyze', payload)
    assert code == 200, dashboard
    sid4 = session()
    chat = turn(sid4, 'У меня 5 кг пищевых отходов, реактор 90 литров, регион Карагандинская область. Сколько метана?')
    chat_science = live_tool(chat, 'assess_substrate_potential')
    dashboard_first = (dashboard.get('scenario_results') or [dashboard])[0]
    dashboard_mix = dashboard_first.get('mixture')
    chat_mix = (chat_science or {}).get('scenarios', [{}])[0].get('mixture')
    record('06_chat_api_dashboard_contract_equal', '5 kg food waste / 90 L / Karaganda oblast', chat, {
        'dashboard_api_ok': code == 200,
        'chat_scientific_tool_called': chat_science is not None,
        'same_mixture_result': chat_mix == dashboard_mix})

    # 5: A selected but unsupported physical state must not reuse pulp data.
    sid5 = session()
    dry = turn(sid5, 'У меня 5 кг сухих пищевых отходов. Сколько метана?')
    dry_science = live_tool(dry, 'assess_substrate_potential')
    record('07_incompatible_physical_state', 'У меня 5 кг сухих пищевых отходов. Сколько метана?', dry, {
        'science_checked': dry_science is not None,
        'no_pulp_profile_transfer': bool(dry_science and dry_science.get('scenarios')
            and all(s.get('methane_m3') is None and 'baek2020-food-pulp' not in s.get('profile_ids', []) for s in dry_science['scenarios']))})

    # 6: A new request should retain confirmed batch context and can answer
    # energy without asking for the feedstock again.
    followup = turn(sid, 'А сколько полезной энергии в этом метане?')
    record('08_new_question_keeps_batch_context', 'А сколько полезной энергии в этом метане?', followup, {
        'feed_material_retained': followup.get('memory', {}).get('facts', {}).get('material', {}).get('value') == 'food_waste',
        'quantity_retained': followup.get('memory', {}).get('facts', {}).get('quantity', {}).get('value') == 5,
        'science_or_economics_checked': any(x.get('tool') in {'assess_substrate_potential', 'evaluate_partial_economics'} for x in followup.get('tools', []))})

    # 7: Scientific detail request stays in the same session, which preserves
    # confirmed profile, batch and region facts.
    details = turn(sid, 'Покажи научные подробности расчёта и источник.')
    record('09_scientific_detail_followup', 'Покажи научные подробности расчёта и источник.', details, {
        'batch_retained': details.get('memory', {}).get('facts', {}).get('quantity', {}).get('value') == 5,
        'source_or_science_tool': any(x.get('tool') in {'assess_substrate_potential', 'research_scientific_evidence', 'search_scientific_sources'} for x in details.get('tools', []))})

    # 8: Dashboard-to-chat handoff is checked over the actual HTTP routes.
    handoff_payload = dict(payload, components=[dict(payload['components'][0], material_state='prepared_pulp',
        reference_profile_id='baek2020-food-pulp')])
    code, handoff = request('POST', '/api/advisor/handoff', {'request': handoff_payload, 'mode': 'offline'})
    code2, restored = request('GET', f"/api/dashboard/chat/sessions/{handoff['session_id']}")
    mem = restored.get('memory', {})
    record('10_dashboard_to_chat_handoff', 'dashboard mixture handoff', {
        'mode': 'dashboard_http_handoff', 'provider_status': [],
        'answer': 'dashboard handoff persisted; no assistant generation in this check', 'user_facing_answer': {}, 'tools': [], 'memory': mem}, {
        'handoff_created': code == 201 and code2 == 200,
        'material_and_mass_preserved': mem.get('advanced', {}).get('inventory', [{}])[0].get('quantity') == 5,
        'profile_preserved': mem.get('advanced', {}).get('inventory', [{}])[0].get('reference_profile_id') == 'baek2020-food-pulp',
        'region_preserved': mem.get('facts', {}).get('market_region', {}).get('value') == 'KZ-Karaganda-oblast'}, require_qwen=False)

    print('TOTAL', sum(x['passed'] for x in records), '/', len(records), flush=True)
