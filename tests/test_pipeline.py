import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main
import numpy as np
import pandas as pd
from src.data.prepare import ROOT, FEATURES
from src.data.prepare import prepare
from src.ml.train import partitions
from src.inference.predict import predict_bmp, positive


class PipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frame = pd.read_csv(ROOT / 'data/processed/bmp.csv')
        cls.meta = json.loads((ROOT / 'models/metadata.json').read_text(encoding='utf-8'))
        cls.payload = cls.frame.iloc[0][FEATURES].to_dict()

    def test_laboratory_partitions_disjoint_and_complete(self):
        splits = partitions(self.frame)
        seen = set()
        rows = []
        for indices in splits.values():
            labs = set(self.frame.iloc[indices].lab_id)
            self.assertFalse(seen & labs)
            seen |= labs
            rows.extend(indices)
        self.assertEqual(sorted(rows), list(range(len(self.frame))))

    def test_missing_measurements(self):
        with self.assertRaisesRegex(ValueError, 'Missing measured'):
            predict_bmp({'material': 'food_waste', 'mass_kg': 5})

    def test_unknown_material(self):
        with self.assertRaisesRegex(ValueError, 'Unsupported'):
            predict_bmp({**self.payload, 'substrate': 'chernozem'})

    def test_invalid_measurements(self):
        for val in [True, -1, float('nan'), float('inf'), '0.9', 90]:
            with self.subTest(val=val), self.assertRaises(ValueError):
                predict_bmp({**self.payload, 'c_vs_sub_m': val})

    def test_volume_units(self):
        a = predict_bmp({**self.payload, 'vs_mass_kg': 2})
        self.assertAlmostEqual(a['potential_methane_m3'], a['bmp'] * .002)
        self.assertNotIn('potential_methane_m3', predict_bmp(self.payload))

    def test_impossible_mass(self):
        with self.assertRaisesRegex(ValueError, 'VS mass'):
            predict_bmp({**self.payload, 'vs_mass_kg': 2, 'mass_kg': 1})

    def test_no_leakage_features(self):
        self.assertEqual(self.meta['schema']['features'], FEATURES)
        self.assertNotIn('fv_inoc', FEATURES)
        self.assertNotIn('bmp_calc', FEATURES)

    def test_metrics_recomputed_from_predictions(self):
        f = pd.read_csv(ROOT / 'reports/test_predictions.csv')
        self.assertAlmostEqual(float(np.abs(f.prediction-f.bmp_calc).mean()), self.meta['test']['MAE'])

    def test_preparation_preserves_raw_and_rejects_impossible_vs(self):
        import hashlib
        source = ROOT / 'data/raw/hafner_2026_il_bmp'
        original = source / 'data/setup.csv'
        checksum = hashlib.sha256(original.read_bytes()).hexdigest()
        with tempfile.TemporaryDirectory() as temp:
            with patch('src.data.prepare.ROOT', Path(temp)):
                clean = prepare(source)
            self.assertEqual(len(clean), 613)
            self.assertTrue(clean.c_vs_sub_m.between(0, 1).all())
            audit = json.loads((Path(temp) / 'reports/data_audit.json').read_text(encoding='utf-8'))
            self.assertEqual(audit['invalid_rows_excluded'], 6)
            self.assertEqual(audit['duplicate_bottle_keys'], 0)
        self.assertEqual(hashlib.sha256(original.read_bytes()).hexdigest(), checksum)

    def test_duplicate_bottle_keys_fail_preparation(self):
        import shutil
        source = ROOT / 'data/raw/hafner_2026_il_bmp'
        with tempfile.TemporaryDirectory() as temp:
            staging = Path(temp) / 'source'
            shutil.copytree(source, staging)
            path = staging / 'data/setup.csv'
            frame = pd.read_csv(path)
            pd.concat([frame, frame.iloc[:1]], ignore_index=True).to_csv(path, index=False)
            with patch('src.data.prepare.ROOT', Path(temp) / 'output'):
                with self.assertRaisesRegex(ValueError, 'Duplicate bottle keys'):
                    prepare(staging)


if __name__ == '__main__':
    unittest.main()
