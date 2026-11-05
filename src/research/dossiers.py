"""Study-specific dossiers; no pooling across incompatible samples or gas bases."""
from src.advisor import catalog

CORE_MATERIALS = ('cattle_manure', 'swine_manure', 'poultry_manure',
                  'sheep_goat_manure', 'horse_manure', 'food_waste', 'straw', 'grass')

RATIONALE = {
    'cattle_manure': 'Livestock manure; several distinct slurry and bedded studies.',
    'swine_manure': 'Livestock manure; independent slurry experiments and method comparison.',
    'poultry_manure': 'Poultry farming; fresh droppings and dry-batch evidence must remain separate.',
    'sheep_goat_manure': 'Sheep/goat husbandry relevant to Kazakhstan; species-specific samples retained.',
    'horse_manure': 'Horse husbandry; dung, bedding and storage have distinct evidence.',
    'food_waste': 'Catering and household organic waste; only prepared pulp currently quantified.',
    'straw': 'Cereal residues; wheat straw preparation and slow hydrolysis are central constraints.',
    'grass': 'Seasonal green residues; several separately characterized samples available.',
}


def dossier(material):
    doc = catalog.document()
    profiles = [p for p in catalog.profiles() if p['material'] == material]
    definition = next((r for r in catalog.DEFINITIONS if r[0] == material), None)
    partial = [r for r in doc['partial_characterizations'] if r['material'] == material]
    sources = {p['source']['id']: p['source'] for p in profiles}
    for row in partial:
        source = next((s for s in doc['sources'] if s['id'] == row.get('source_id')), None)
        if source: sources[source['id']] = source
    return {
        'material': material, 'name': catalog.name(material),
        'scope_status': 'CORE' if material in CORE_MATERIALS else 'EXPERIMENTAL_RETAINED',
        'selection_rationale': RATIONALE.get(material, 'Historical category retained; evidence is not a core dossier.'),
        'physical_states': definition[5] if definition else [],
        'studies': [{
            'profile_id': p['id'], 'source_id': p['source_id'], 'physical_state': p['material_state'],
            'animal_scope': p.get('animals'), 'preparation': p.get('preparation'),
            'ts_fraction': p.get('ts_fraction'), 'vs_fraction_wet': p.get('vs_fraction_wet'),
            'vs_fraction_of_ts': p.get('vs_fraction_of_ts'), 'bmp_ml_ch4_g_vs': p.get('bmp_ml_g_vs'),
            'density_kg_l': p.get('density_kg_l'), 'conditions': p.get('conditions'),
            'quality': 'Reviewed local extraction of published experiment; not independent replication',
            'gas_basis': (p.get('conditions') or {}).get('gas_basis'),
            'provenance': 'PUBLISHED_EXPERIMENT', 'transfer_limitations': p['source'].get('limitations', []),
        } for p in profiles],
        'partial_characterizations': partial, 'sources': list(sources.values()),
        'inhibition_risks': definition[6] if definition else ['Material identity unverified'],
        'organic_loading_limit': None,
        'loading_limit_note': 'No universal safe OLR established. Study-specific loading, ISR and duration belong to their original reactor and feeding regime.',
        'co_digestion': 'No universal synergy or compatible mixing ratio inferred; compare specific mixed-substrate studies before transfer.',
        'unknowns': ['batch composition', 'inoculum activity', 'plant recovery', 'safe loading limit'],
        'search_scope': 'LOCAL_REVIEWED_CORPUS', 'live_search_performed': False,
    }


def search(materials=None, query=''):
    selected = materials or [m['material'] for m in catalog.matches(query)] or list(CORE_MATERIALS)
    return {'status': 'ok', 'message': 'Study-specific local evidence; no live internet search performed.',
            'dossiers': [dossier(m) for m in dict.fromkeys(selected)],
            'core_materials': list(CORE_MATERIALS), 'universal_profile_created': False}


def compare(materials=None, query=''):
    found = search(materials, query)
    studies = [s for d in found['dossiers'] for s in d['studies']]
    issues = []
    for i, left in enumerate(studies):
        for right in studies[i+1:]:
            mismatch = [k for k in ('physical_state', 'preparation', 'gas_basis', 'animal_scope')
                        if left.get(k) != right.get(k)]
            if left['source_id'] != right['source_id']:
                mismatch.append('study_conditions_and_sample')
            if not left.get('gas_basis') or not right.get('gas_basis'):
                mismatch.append('gas_basis_unresolved')
            if mismatch:
                issues.append({'left': left['profile_id'], 'right': right['profile_id'],
                               'differences': mismatch, 'pooling_allowed': False})
    return {'status': 'ok', 'message': 'Published samples compared separately; discrepancies are not a calibrated uncertainty interval.',
            'studies': studies, 'comparability_checks': issues,
            'sources': list({s['id']: s for d in found['dossiers'] for s in d['sources']}.values()),
            'pooled_bmp': None, 'live_search_performed': False}
