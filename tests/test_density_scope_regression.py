"""Volume-to-mass conversion must use a density supplied for the batch."""
import pytest
from src.advisor.schemas import AdvisorRequest, Component
from src.advisor.mixing import evaluate
from src.advisor.conversion import convert
from src.estimation.schemas import EstimateRequest
from src.estimation.substrate_properties import resolve


def batch(properties=None):
    return Component(id='c1', material='cattle_manure', material_state='slurry',
                     physical_state='liquid', quantity=470, unit='L', properties=properties or {})


def test_literature_density_does_not_convert_user_litres_to_mass():
    c = batch()
    row = evaluate(AdvisorRequest(components=[c]))['components'][0]
    assert row['volume_l']['low'] == 470
    assert row['wet_mass_kg'] is None
    assert row['methane_reference_m3'] is None
    assert 'density_kg_l' in row['missing']
    assert convert(c, 'kg')['status'] == 'needs_input'


def test_explicit_batch_density_preserves_conversion():
    c = batch({'density_kg_l': 1.02})
    row = evaluate(AdvisorRequest(components=[c]))['components'][0]
    assert row['wet_mass_kg']['low'] == pytest.approx(479.4)
    converted=convert(c, 'kg')
    assert converted['value']['low'] == pytest.approx(479.4)
    assert converted['density']['mode'] == 'USER_REPORTED'


def test_hypothetical_density_is_not_promoted_to_batch_mass():
    c = batch({'density_kg_l': {'low': 1.0, 'high': 1.0,
                                'provenance': 'HYPOTHETICAL_SCENARIO', 'evidence': 'TEST assumption'}})
    assert evaluate(AdvisorRequest(components=[c]))['components'][0]['wet_mass_kg'] is None
    assert convert(c, 'kg')['status'] == 'needs_input'


def test_legacy_estimator_also_requires_explicit_density():
    # A profile with density is sufficient to reproduce the legacy issue.
    profile = {'id': 'TEST', 'source': {'id': 'TEST'}, 'values': {
        key: {'low': val, 'high': val, 'locator': 'TEST', 'original_value': str(val),
              'original_unit': 'TEST', 'method': 'TEST'}
        for key, val in [('density_kg_l', 1.013), ('vs_fraction_wet', .1), ('bmp_ml_g_vs', 250)]}}
    mass, vs, _, _, _ = resolve(EstimateRequest(volume_l=470), profile)
    assert mass is None and vs is None
    mass, _, _, _, _ = resolve(EstimateRequest(volume_l=470, density_kg_l=1.02), profile)
    assert mass['low'] == pytest.approx(479.4)
