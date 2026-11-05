"""v6 API/storage tests; every measurement/price fixture stays in a temporary DB."""
import csv
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from src.market.store import Store
from src.optimizer.api import create_router
from src.optimizer import storage, experiment_lab as lab


class ProcessApiTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.store = Store(Path(temporary.name) / 'TEST_ONLY.sqlite3')
        app = FastAPI()
        @app.exception_handler(ValueError)
        def bad_input(request: Request, exc: ValueError):
            return JSONResponse(status_code=422, content={'detail': str(exc)})
        app.include_router(create_router(self.store))
        self.client = TestClient(app)

    def experiment(self, **kwargs):
        response = self.client.post('/api/experiments', json={'name': 'TEST experiment, not real data', **kwargs})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_minimal_experiment_unknowns_and_frozen_model_snapshot(self):
        item = self.experiment()
        self.assertIsNone(item['mass_kg']); self.assertIsNone(item['gas_volume_m3'])
        self.assertFalse(item['auto_training_enabled'])
        self.assertTrue(item['model_snapshot']['version'])
        self.assertNotEqual(item['model_snapshot']['prediction']['status'], 'ok')
        self.assertEqual(item['measurements'], [])

    def test_manual_origin_separate_from_laboratory(self):
        user = self.experiment(origin='user')
        laboratory = self.experiment(origin='laboratory', source_reference='TEST laboratory record')
        listed = self.client.get('/api/experiments?origin=laboratory').json()['experiments']
        self.assertEqual([r['id'] for r in listed], [laboratory['id']])
        self.assertNotIn(user['id'], [r['id'] for r in listed])
        self.assertEqual(self.client.patch('/api/experiments/' + user['id'], json={'origin': 'laboratory'}).status_code, 422)

    def test_edited_metadata_has_append_only_revisions(self):
        initial = self.experiment(mass_kg=2)
        updated = self.client.patch('/api/experiments/' + initial['id'], json={'mass_kg': 3}).json()
        self.assertEqual(updated['mass_kg'], 3)
        revisions = self.client.get('/api/experiments/' + initial['id'] + '/revisions').json()['revisions']
        self.assertEqual(len(revisions), 2)
        self.assertEqual(revisions[0]['data']['mass_kg'], 2)
        self.assertEqual(revisions[0]['model_snapshot'], initial['model_snapshot'])
        with self.assertRaises(sqlite3.IntegrityError), self.store.connect() as con:
            con.execute('UPDATE experiment_revisions SET archived=1')

    def test_archive_keeps_measurements_and_hides_default_list(self):
        item = self.experiment(gas_volume_m3=.2)
        identifier = item['id']
        response = self.client.post(f'/api/experiments/{identifier}/archive')
        self.assertTrue(response.json()['archived'])
        self.assertEqual(len(response.json()['measurements']), 1)
        self.assertEqual(self.client.get('/api/experiments').json()['experiments'], [])
        self.assertEqual(len(self.client.get('/api/experiments?include_archived=true').json()['experiments']), 1)
        self.assertEqual(self.client.post(f'/api/experiments/{identifier}/measurements', json={'ph': 7}).status_code, 422)
        self.assertEqual(self.client.patch(f'/api/experiments/{identifier}', json={'mass_kg': 4}).status_code, 422)

    def test_measurement_preserved_and_ordered_by_actual_datetime(self):
        identifier = self.experiment()['id']
        path = f'/api/experiments/{identifier}/measurements'
        for time, volume in [('2026-10-28T12:30:00+05:00', .2), ('2026-10-28T08:00:00+00:00', .3)]:
            response = self.client.post(path, json={'observed_at': time, 'gas_volume_m3': volume})
            self.assertEqual(response.status_code, 201)
            self.assertEqual(response.json()['origin'], 'user')
        rows = self.client.get(path).json()['measurements']
        self.assertEqual([r['gas_volume_m3'] for r in rows], [.2, .3])
        with self.assertRaises(sqlite3.IntegrityError), self.store.connect() as con:
            con.execute('DELETE FROM experiment_measurements')

    def test_biogas_without_ch4_is_never_compared_to_bmp(self):
        item = self.experiment(gas_volume_m3=.2, vs_mass_kg=.5)
        result = self.client.get(f"/api/experiments/{item['id']}/comparison").json()
        self.assertEqual(result['status'], 'INSUFFICIENT_DATA')
        self.assertIsNone(result['measured_methane_m3'])
        self.assertIsNone(result['relative_difference_percent'])
        self.assertTrue(any('CH4' in reason for reason in result['reasons']))

    def test_quantitative_mq_fraction_rejected(self):
        response = self.client.post('/api/experiments', json={'name': 'TEST MQ', 'gas_volume_m3': 1,
            'methane_fraction': .6, 'measurement_method': 'MQ-4 sensor raw ADC', 'quantitative_method_confirmed': True})
        self.assertEqual(response.status_code, 422)
        identifier = self.experiment()['id']
        response = self.client.post(f'/api/experiments/{identifier}/measurements', json={
            'methane_fraction': .6, 'measurement_method': 'MQ sensor', 'quantitative_method_confirmed': True})
        self.assertEqual(response.status_code, 422)

    def test_instantaneous_fraction_not_total_batch_fraction(self):
        item = self.experiment(gas_volume_m3=.2, methane_fraction=.6,
            measurement_method='TEST calibrated gas meter and GC', quantitative_method_confirmed=True,
            methane_fraction_basis='instantaneous', gas_volume_basis='TEST dry 273.15 K 101.325 kPa')
        result = lab.comparison(self.store, item['id'])
        self.assertIsNone(result['measured_methane_m3'])
        self.assertTrue(any('instantaneous' in reason for reason in result['reasons']))

    def test_measured_ch4_units_but_no_model_validation_without_basis(self):
        item = self.experiment(gas_volume_m3=.2, methane_fraction=.6, vs_mass_kg=.5,
            measurement_method='TEST calibrated meter and GC', quantitative_method_confirmed=True,
            methane_fraction_basis='volume_weighted', gas_volume_basis='TEST dry reference')
        result = lab.comparison(self.store, item['id'])
        self.assertAlmostEqual(result['measured_methane_m3'], .12)
        self.assertAlmostEqual(result['measured_specific_yield_ml_ch4_g_vs'], 240)
        self.assertIsNone(result['relative_difference_percent'])

    def test_comparison_no_vs_no_specific_yield(self):
        item = self.experiment(gas_volume_m3=.2, methane_fraction=.6,
            measurement_method='TEST calibrated meter and GC', quantitative_method_confirmed=True,
            methane_fraction_basis='volume_weighted', gas_volume_basis='TEST dry reference')
        result = lab.comparison(self.store, item['id'])
        self.assertAlmostEqual(result['measured_methane_m3'], .12)
        self.assertIsNone(result['measured_specific_yield_ml_ch4_g_vs'])

    def test_interval_measurement_not_misrepresented_as_cumulative(self):
        item = self.experiment(gas_volume_m3=.2, methane_fraction=.6, vs_mass_kg=.5,
            measurement_method='TEST calibrated meter and GC', quantitative_method_confirmed=True,
            methane_fraction_basis='volume_weighted', gas_volume_basis='TEST dry reference', gas_volume_kind='interval')
        result = lab.comparison(self.store, item['id'])
        self.assertIsNone(result['measured_specific_yield_ml_ch4_g_vs'])
        self.assertIsNone(result['relative_difference_percent'])

    def test_full_comparison_conditional_with_actual_preserved_model(self):
        root = Path(__file__).resolve().parents[1]
        example = json.loads((root / 'examples/stage1_5_measured.json').read_text(encoding='utf-8'))
        context = {k: example[k] for k in ['c_vs_sub_m', 'c_vs_sub_f', 'c_vs_inoc', 'ISR']}
        item = self.experiment(material=example.get('material', example.get('substrate')), prediction_context=context,
            gas_volume_m3=.2, methane_fraction=.6, vs_mass_kg=.5, measurement_method='TEST calibrated meter and GC',
            quantitative_method_confirmed=True, methane_fraction_basis='volume_weighted',
            gas_volume_basis='TEST matching gas reference', prediction_gas_volume_basis='TEST matching gas reference',
            gas_basis_comparison_confirmed=True, gas_basis_evidence='TEST explicit operator assertion, not independent validation')
        result = lab.comparison(self.store, item['id'])
        self.assertEqual(result['model_snapshot']['prediction']['status'], 'ok')
        self.assertEqual(result['status'], 'CONDITIONAL')
        self.assertIsNotNone(result['relative_difference_percent'])
        self.assertFalse(result['model_snapshot']['auto_training_enabled'])

    def test_mismatched_reference_conditions_block_comparison(self):
        snapshot = {'artifact': 'stage1_5', 'version': 'TEST isolated stub', 'prediction': {'status': 'ok', 'bmp': 300}}
        with patch.object(lab, 'model_snapshot', return_value=snapshot):
            item = self.experiment(gas_volume_m3=.2, methane_fraction=.6, vs_mass_kg=.5,
                measurement_method='TEST calibrated meter', quantitative_method_confirmed=True,
                methane_fraction_basis='volume_weighted', gas_volume_basis='TEST wet gas',
                prediction_gas_volume_basis='TEST dry gas', gas_basis_comparison_confirmed=True,
                gas_basis_evidence='TEST external basis review')
        result = lab.comparison(self.store, item['id'])
        self.assertEqual(result['status'], 'INSUFFICIENT_DATA')
        self.assertIsNone(result['relative_difference_percent'])

    def test_csv_safe_formula_and_origin_and_reference_conditions(self):
        item = self.experiment(name='=TEST(1)', origin='laboratory', gas_volume_m3=.2,
                               gas_volume_basis='TEST dry gas', notes='@TEST()')
        response = self.client.get(f"/api/experiments/{item['id']}/export.csv")
        self.assertEqual(response.status_code, 200)
        rows = list(csv.DictReader(io.StringIO(response.content.decode('utf-8-sig'))))
        self.assertEqual(rows[0]['experiment_name'], "'=TEST(1)")
        self.assertEqual(rows[0]['notes'], "'@TEST()")
        self.assertEqual(rows[0]['origin'], 'laboratory')
        self.assertEqual(rows[0]['gas_volume_basis'], 'TEST dry gas')
        self.assertTrue(rows[0]['model_version'])

    def test_edited_vs_does_not_reinterpret_historical_gas_observation(self):
        item = self.experiment(gas_volume_m3=.2, methane_fraction=.6, vs_mass_kg=.5,
            measurement_method='TEST calibrated meter and GC', quantitative_method_confirmed=True,
            methane_fraction_basis='volume_weighted', gas_volume_basis='TEST dry reference')
        previous_revision = item['revision']
        self.client.patch('/api/experiments/' + item['id'], json={'vs_mass_kg': 1})
        result = lab.comparison(self.store, item['id'])
        self.assertEqual(result['comparison_revision'], previous_revision)
        self.assertTrue(result['uses_historical_revision'])
        self.assertEqual(result['measured_specific_yield_ml_ch4_g_vs'], 240)
        rows = list(csv.DictReader(io.StringIO(lab.csv_export(self.store, item['id']))))
        self.assertEqual(rows[0]['vs_mass_kg'], '0.5')
        self.assertEqual(rows[0]['experiment_revision'], str(previous_revision))

    def test_latest_n_measurements_are_explicitly_truncated(self):
        identifier = self.experiment()['id']
        path = f'/api/experiments/{identifier}/measurements'
        for minute in [1, 2, 3]:
            self.client.post(path, json={'observed_at': f'2026-10-28T12:0{minute}:00+05:00', 'gas_volume_m3': minute / 10})
        result = self.client.get(path + '?limit=2').json()
        self.assertTrue(result['truncated']); self.assertEqual(result['total'], 3)
        self.assertEqual([r['gas_volume_m3'] for r in result['measurements']], [.2, .3])

    def test_validation_ranges_empty_measurements_and_missing_ids(self):
        for body in [{'name': 'TEST', 'vs_mass_kg': 3, 'mass_kg': 2},
                     {'name': 'TEST', 'methane_fraction': 2}, {'name': 'TEST', 'ph': 15},
                     {'name': 'TEST', 'mass_kg': True}, {'name': '  '},
                     {'name': 'TEST', 'prediction_context': {'ISR': True}},
                     {'name': 'TEST', 'prediction_context': {'fake_feature': 1}}]:
            self.assertEqual(self.client.post('/api/experiments', json=body).status_code, 422, body)
        identifier = self.experiment()['id']
        path = f'/api/experiments/{identifier}/measurements'
        self.assertEqual(self.client.post(path, json={}).status_code, 422)
        self.assertEqual(self.client.post(path, json={'ph': 7, 'observed_at': '2026-10-28T12:00:00'}).status_code, 422)
        for route in ['/api/experiments/missing', '/api/experiments/missing/comparison',
                      '/api/experiments/missing/export.csv', '/api/process/scenarios/missing']:
            self.assertEqual(self.client.get(route).status_code, 404, route)

    def test_saved_scenarios_are_immutable_and_do_not_touch_market_prices(self):
        result = {'scenarios': [{'scenario_id': 'TEST candidate', 'feasibility_status': 'INSUFFICIENT_DATA'}]}
        saved = storage.save_run(self.store, {'material': 'TEST'}, result)
        retrieved = self.client.get('/api/process/scenarios/' + saved['id']).json()
        self.assertEqual(retrieved['result'], result)
        self.assertEqual(len(self.client.get('/api/process/scenarios').json()['scenarios']), 1)
        with self.assertRaises(sqlite3.IntegrityError), self.store.connect() as con:
            con.execute('UPDATE process_optimizer_runs SET engine_version=?', ('TEST modified',))
        with self.store.connect() as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM observations').fetchone()[0], 0)

    def test_compare_requires_distinct_existing_saved_runs(self):
        self.assertEqual(self.client.post('/api/process/compare', json={'scenario_ids': ['a', 'a']}).status_code, 422)
        self.assertEqual(self.client.post('/api/process/compare', json={'scenario_ids': ['missing1', 'missing2']}).status_code, 404)

    def test_optimizer_endpoint_real_core_and_compare(self):
        payload = {'material': 'cattle_manure', 'feedstock_volume_l': 800, 'reactor_total_volume_l': 90,
            'candidates': [{'label': 'TEST 35 C', 'overrides': {'temperature_c': 35}, 'rationale': 'TEST user hypothesis'},
                           {'label': 'TEST 38 C', 'overrides': {'temperature_c': 38}, 'rationale': 'TEST user hypothesis'}],
            'objectives': ['energy', 'methane']}
        first = self.client.post('/api/process/optimize', json=payload)
        self.assertEqual(first.status_code, 201, first.text)
        second = self.client.post('/api/process/optimize', json=payload)
        self.assertEqual(second.status_code, 201, second.text)
        result = self.client.post('/api/process/compare', json={'scenario_ids': [first.json()['id'], second.json()['id']],
                                                              'objectives': ['energy', 'methane']})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(len(first.json()['scenarios']), 2)


if __name__ == '__main__':
    unittest.main()
