"""Serializable, target-free transformations and a strong category baseline."""
import numpy as np
from sklearn.base import BaseEstimator, RegressorMixin, TransformerMixin
from src.data.prepare import FEATURES, NUMERIC

ENGINEERED = ['vs_relative_error', 'vs_absolute_error', 'log_ISR', 'log_inoc_vs']


class ScientificFeatures(TransformerMixin, BaseEstimator):
    def __init__(self, mode='raw'):
        self.mode = mode

    def fit(self, X, y=None):
        self.feature_names_in_ = np.asarray(FEATURES, dtype=object)
        self.n_features_in_ = len(FEATURES)
        return self

    def transform(self, X):
        f = X[FEATURES].copy()
        if self.mode == 'engineered':
            f['vs_relative_error'] = (f.c_vs_sub_m - f.c_vs_sub_f) / f.c_vs_sub_f.clip(lower=1e-6)
            f['vs_absolute_error'] = f.c_vs_sub_m - f.c_vs_sub_f
            f['log_ISR'] = np.log(f.ISR.clip(lower=1e-6))
            f['log_inoc_vs'] = np.log(f.c_vs_inoc.clip(lower=1e-6))
        elif self.mode == 'drop_fixed':
            f = f.drop(columns='c_vs_sub_f')
        return f


class SubstrateMedian(RegressorMixin, BaseEstimator):
    """Training-only medians; unknown categories fall back to train median."""
    def fit(self, X, y):
        f = X[['substrate']].copy()
        f['target'] = np.asarray(y)
        self.medians_ = f.groupby('substrate').target.median().to_dict()
        self.fallback_ = float(np.median(y))
        self.n_features_in_ = X.shape[1]
        return self

    def predict(self, X):
        return X.substrate.map(self.medians_).fillna(self.fallback_).to_numpy(dtype=float)
