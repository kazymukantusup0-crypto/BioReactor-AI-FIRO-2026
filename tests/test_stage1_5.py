"""Scientific invariants checked using actual source observations."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main
import joblib
import numpy as np
import pandas as pd
from src.data.prepare import ROOT, FEATURES, NUMERIC
from src.inference.predict import predict_bmp
from src.ml.estimators import ScientificFeatures, SubstrateMedian
from src.ml.reliability import DomainDetector, group_radius


class ResearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        frame = pd.read_csv(ROOT/'data/processed/bmp.csv').merge(
            pd.read_csv(ROOT/'data/processed/split_assignments.csv'), on=['lab_id','bottle_id'], validate='one_to_one')
        cls.train = frame[frame.partition=='train'].copy()
        cls.cal = frame[frame.partition=='calibration'].copy()
        cls.frame = frame
        cls.bundle = joblib.load(ROOT/'models/stage1_5/bmp.joblib')

    def test_old_artifacts_byte_identical(self):
        original = json.loads((ROOT/'reports/stage1_5/stage1_hashes_before.json').read_text())
        for path, checksum in original.items():
            self.assertEqual(hashlib.sha256((ROOT/path).read_bytes()).hexdigest(), checksum, path)

    def test_outer_labs_only_original_train_and_no_overlap(self):
        folds = json.loads((ROOT/'reports/stage1_5/cv_labs.json').read_text())
        heldout = []
        training_labs = set(self.train.lab_id)
        for fold in folds:
            a,b = set(fold['train_labs']),set(fold['heldout_labs'])
            self.assertFalse(a & b)
            self.assertEqual(a|b, training_labs)
            heldout.extend(b)
        self.assertEqual(len(heldout),len(set(heldout)))
        self.assertEqual(set(heldout),training_labs)
        self.assertIsNone(self.bundle['metadata']['test'])

    def test_feature_engineering_ignores_target_and_id(self):
        transformer = ScientificFeatures('engineered').fit(self.train[FEATURES])
        before = transformer.transform(self.train)
        changed = self.train.copy()
        changed['bmp_calc'] = -999
        changed['lab_id'] = 'untrusted'
        pd.testing.assert_frame_equal(before,transformer.transform(changed))
        self.assertTrue(np.isfinite(before.select_dtypes('number')).all().all())

    def test_category_baseline_only_uses_fit_data(self):
        train = self.train[self.train.lab_id != self.train.lab_id.iloc[0]]
        model = SubstrateMedian().fit(train[FEATURES],train.bmp_calc)
        for category, rows in self.train.groupby('substrate'):
            expected = train.loc[train.substrate.eq(category),'bmp_calc'].median()
            np.testing.assert_allclose(model.predict(rows[FEATURES]),expected)

    def test_detector_independent_of_target(self):
        a = DomainDetector().fit(self.train)
        changed = self.train.copy()
        changed.bmp_calc = -1000
        b = DomainDetector().fit(changed)
        self.assertEqual(a.thresholds_,b.thresholds_)
        pd.testing.assert_frame_equal(a.reference_,b.reference_)

    def test_conditional_ood_inside_global_bounds(self):
        row = self.train[self.train.substrate.eq('Wheat straw')].iloc[0][FEATURES].to_dict()
        # Real reference VS value from another substrate, within global bounds.
        row['c_vs_sub_f'] = float(self.train.c_vs_sub_f.max())
        out = predict_bmp(row,ROOT/'models/stage1_5/bmp.joblib')
        self.assertTrue(out['domain']['out_of_distribution'])
        self.assertIn('c_vs_sub_f',out['domain']['conditional_range_violations'])
        self.assertTrue(any('extrapolation' in warning for warning in out['warnings']))

    def test_training_observation_has_zero_neighbor_distance(self):
        row = self.train.iloc[0][FEATURES].to_dict()
        result = self.bundle['domain_detector'].assess(row)
        self.assertEqual(result['distance'],0)
        self.assertFalse(result['out_of_distribution'])

    def test_rare_substrate_has_warning(self):
        row = self.train[self.train.substrate.eq('Bird feed')].iloc[0][FEATURES].to_dict()
        out = predict_bmp(row,ROOT/'models/stage1_5/bmp.joblib')
        self.assertTrue(out['domain']['limited_support'])
        self.assertTrue(any('limited independent' in s for s in out['warnings']))

    def test_group_calibration_insufficient_for_finite_90(self):
        pred = self.bundle['pipeline'].predict(self.cal[FEATURES])
        errors = np.abs(pred-self.cal.bmp_calc.to_numpy())
        self.assertIsNone(group_radius(errors,self.cal.lab_id.to_numpy(),.1))
        expected = float(pd.Series(errors).max())
        self.assertAlmostEqual(group_radius(errors,self.cal.lab_id.to_numpy(),.2),expected)
        self.assertIsNone(self.bundle['metadata']['interval']['radius'])

    def test_roundtrip_old_and_new_model(self):
        payload = self.train.iloc[0][FEATURES].to_dict()
        for path in [ROOT/'models/bmp.joblib',ROOT/'models/stage1_5/bmp.joblib']:
            before = predict_bmp(payload,path)
            with tempfile.TemporaryDirectory() as temp:
                copy = Path(temp)/'model.joblib'
                joblib.dump(joblib.load(path),copy)
                after = predict_bmp(payload,copy)
            self.assertEqual(before['bmp'],after['bmp'])
            self.assertEqual(before['model_version'],after['model_version'])

    def test_legacy_applicability_explicitly_unknown(self):
        out = predict_bmp(self.train.iloc[0][FEATURES].to_dict())
        self.assertEqual(out['domain']['status'],'unavailable')
        self.assertIsNone(out['domain']['out_of_distribution'])

    def test_reported_cv_metrics_match_oof(self):
        from src.ml.stage1_5 import lab_mae
        oof = pd.read_csv(ROOT/'reports/stage1_5/all_oof_predictions.csv')
        comparison = pd.read_csv(ROOT/'reports/stage1_5/nested_cv_comparison.csv')
        for _, row in comparison.iterrows():
            score = lab_mae(self.train.bmp_calc,oof[row.family].to_numpy(),self.train.lab_id)
            self.assertAlmostEqual(score,row.macro_lab_MAE)

    def test_inference_reflects_actually_used_features(self):
        out = predict_bmp(self.train.iloc[0][FEATURES].to_dict(), ROOT/'models/stage1_5/bmp.joblib')
        if self.bundle['metadata']['selected_model']=='SubstrateMedian':
            self.assertEqual(list(out['used_features']),['substrate'])
            self.assertEqual(set(out['domain_assessed_features']),set(FEATURES))


if __name__ == '__main__':
    unittest.main()
