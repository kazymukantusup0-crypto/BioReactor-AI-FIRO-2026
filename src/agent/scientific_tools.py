"""Read-only research tools using the same typed calculations as the dashboard."""
from src.research import dossiers

DESCRIPTIONS = {
    'analyze_economic_sensitivity':'Inspect existing deterministic price sensitivity and break-even thresholds; do not train or predict future prices.',
    'search_public_scientific_metadata': 'Search Europe PMC publication metadata using only canonical material names. New records are unreviewed and cannot supply numerical estimation profiles; disabled when online research is disabled.',
    'recover_local_scientific_analysis': 'Alternative offline calculation path when the primary scientific tool failed. Reuse the shared local profile engine, preserving the failed call in diagnostics.',
    'recover_partial_economics': 'Alternative local energy and valuation calculation after the primary economics tool failed; requires existing scientific scenarios and retains unknown costs.',
    'search_substrate_profiles': 'Find study-specific dossiers for known materials in the reviewed local corpus; returns TS/VS, BMP, preparation, source and limitations.',
    'compare_scientific_studies': 'Compare study conditions, physical form and gas basis; identify incompatible evidence without pooling BMP values.',
    'verify_scientific_sources': 'Audit local citation metadata and scope; explicitly distinguishes metadata completeness from live source verification.',
    'check_reactor_loading': 'Inspect calculated feed, water, inoculum, headspace and working capacity; never authorizes safe operation.',
    'calculate_dilution_plan': 'Calculate user-selected target TS dilution and resulting loading from existing science scenarios; never invent a target concentration.',
    'assess_scientific_risks': 'Assess material-specific inhibition risks, missing measurements and physical feasibility; no actuator control.',
    'verify_scientific_calculations': 'Independently recompute methane from VS and BMP, audit gas normalization, nonnegative quantities and economic completeness.',
}
TOOLS = list(DESCRIPTIONS)


def _materials(data):
    rows = data.get('components', [])
    return list(dict.fromkeys(c['material'] for c in rows)) or ([data['facts']['material']] if data['facts'].get('material') not in {None, 'mixture'} else [])


def verify(results):
    checks = []
    for s in results.get('assess_substrate_potential', {}).get('scenarios', []):
        for c in s.get('components', []):
            vs = c.get('vs_mass_kg'); bmp = c.get('properties_used', {}).get('bmp_ml_g_vs', {}).get('range')
            methane = c.get('methane_reference_m3')
            if vs and bmp and methane:
                # Check at source basis; a later mixture normalization is separate.
                expected = {'low': vs['low']*bmp['low']*.001, 'high': vs['high']*bmp['high']*.001}
                ok = all(abs(expected[k]-methane[k]) <= max(1e-8, abs(expected[k])*1e-6) for k in expected)
                checks.append({'scenario': s['id'], 'component': c['id'], 'check': 'VS_kg_times_BMP_ml_per_g_times_0.001',
                               'expected_m3': expected, 'observed_m3': methane, 'passed': ok})
    return {'status': 'ok' if all(c['passed'] for c in checks) else 'error',
            'message': 'Independent source-basis arithmetic check; mixture gas-basis assumptions remain explicit.',
            'checks': checks, 'verification_scope': 'Component methane arithmetic only; no certification of biological recovery or safe operation.',
            'checked': bool(checks), 'all_checks_passed': bool(checks) and all(c['passed'] for c in checks)}


def execute(name, context, results, query, store=None):
    data = context['analytical_context']; materials = _materials(data)
    if name=='analyze_economic_sensitivity':
        economy=results.get('evaluate_partial_economics',{})
        if not economy.get('scenarios'):return {'status':'needs_input','message':'Calculate the available economics first.','missing':['evaluate_partial_economics']}
        return {'status':'ok','message':'Existing economic-engine sensitivities; no future-price prediction.',
                'scenarios':[{'id':s['id'],'alternatives':[{'id':a['id'],'price_sensitivity':a.get('price_sensitivity'),'break_even':a.get('break_even')}
                    for a in s['analysis']['scenarios']]} for s in economy['scenarios']],
                'scope':'One-at-a-time price perturbations and deterministic thresholds; not a causal ranking of unmeasured process factors.'}
    if name == 'search_public_scientific_metadata':
        from src.research.public_metadata import search
        return search(materials)
    if name == 'recover_local_scientific_analysis':
        from src.agent.analytical import scientific
        return scientific(data)
    if name == 'recover_partial_economics':
        from src.agent.analytical import economics
        from src.market.service import get_store
        return economics(data,results,store or get_store())
    if name == 'search_substrate_profiles': return dossiers.search(materials, query)
    if name == 'compare_scientific_studies': return dossiers.compare(materials, query)
    if name == 'verify_scientific_sources':
        ds = dossiers.search(materials, query)['dossiers']
        sources = list({s['id']: s for d in ds for s in d['sources']}.values())
        return {'status': 'ok', 'message': 'Local citation audit only. No live fetch or full-text verification performed in this call.',
                'sources': sources, 'checks': [{'source_id': s['id'], 'has_title_and_url': bool(s.get('title') and s.get('url')),
                    'doi': s.get('doi'), 'live_verification': 'NOT_PERFORMED'} for s in sources]}
    if name == 'verify_scientific_calculations': return verify(results)
    science = results.get('assess_substrate_potential')
    if name in {'check_reactor_loading', 'calculate_dilution_plan'}:
        if not science:
            return {'status': 'needs_input', 'message': 'First obtain scoped component mass and profile evidence.', 'missing': ['assess_substrate_potential']}
        return {'status': 'ok', 'message': 'Scenario loading audit; admissibility of operation is not established.',
                'scenarios': [{'id': s['id'], 'engineering': s['engineering'], 'assumptions': s['assumptions']} for s in science['scenarios']],
                'target_ts_fraction': data.get('advisor_settings', {}).get('target_ts_fraction'),
                'missing': ['user_selected_target_ts_fraction'] if name == 'calculate_dilution_plan' and not data.get('advisor_settings', {}).get('target_ts_fraction') else [],
                'operation_authorized': False}
    if name == 'assess_scientific_risks':
        ds = dossiers.search(materials, query)['dossiers']
        return {'status': 'ok', 'message': 'Qualitative risk screen; inhibition cannot be quantified without measurements.',
                'materials': [{'material': d['material'], 'risks': d['inhibition_risks'], 'unknowns': d['unknowns']} for d in ds],
                'engineering': [{'id': s['id'], 'status': s['engineering']['status'], 'violations': s['engineering']['violations'], 'missing': s['engineering']['missing']} for s in (science or {}).get('scenarios', [])],
                'sources': list({s['id']: s for d in ds for s in d['sources']}.values()), 'actuator_access': False}
    raise ValueError('Unknown scientific tool')
