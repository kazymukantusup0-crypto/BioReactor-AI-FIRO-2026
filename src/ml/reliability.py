"""Input-only domain diagnostics; no claims of calibrated OOD probabilities."""
import math
import numpy as np
import pandas as pd
from src.data.prepare import NUMERIC


def group_radius(errors, groups, alpha):
    """Finite-sample group-max rank, with infinity represented by None."""
    if not 0 < alpha < 1:
        raise ValueError('alpha must be in (0,1)')
    scores = pd.DataFrame({'error': errors, 'group': groups}).groupby('group').error.max().to_numpy()
    if not len(scores) or not np.isfinite(scores).all() or (scores < 0).any():
        raise ValueError('Finite nonnegative group errors required')
    rank = math.ceil((len(scores) + 1) * (1 - alpha) - 1e-12)
    return float(np.sort(scores)[rank - 1]) if rank <= len(scores) else None


class DomainDetector:
    """Category-specific distance with leave-laboratory-out training threshold."""
    def fit(self, frame):
        self.reference_ = frame[['substrate', 'lab_id', *NUMERIC]].copy().reset_index(drop=True)
        numeric = self.reference_[NUMERIC]
        self.center_ = numeric.median().to_numpy()
        self.scale_ = np.maximum((numeric.quantile(.75)-numeric.quantile(.25)).to_numpy(), .001)
        self.thresholds_ = {}
        for category, rows in self.reference_.groupby('substrate'):
            distances = []
            for _, row in rows.iterrows():
                other = rows[rows.lab_id != row.lab_id]
                if len(other):
                    distances.append(self.distance(row, other))
            self.thresholds_[category] = float(np.quantile(distances, .95)) if distances else None
        return self

    def distance(self, row, reference):
        diffs = (reference[NUMERIC].to_numpy(dtype=float) - row[NUMERIC].to_numpy(dtype=float)) / self.scale_
        return float(np.sqrt((diffs**2).sum(axis=1)).min())

    def assess(self, payload):
        row = pd.Series(payload)
        reference = self.reference_[self.reference_.substrate == payload['substrate']]
        if reference.empty:
            return {'out_of_distribution': True, 'reason': 'Unknown substrate', 'training_labs': 0}
        score = self.distance(row, reference)
        threshold = self.thresholds_[payload['substrate']]
        violations = [c for c in NUMERIC if not reference[c].min() <= payload[c] <= reference[c].max()]
        labs = reference.lab_id.nunique()
        return {'out_of_distribution': bool(violations or threshold is None or score > threshold),
                'distance': score, 'threshold': threshold, 'conditional_range_violations': violations,
                'training_labs': int(labs), 'training_rows': len(reference),
                'limited_support': bool(labs < 12 or len(reference) < 40),
                'method': 'IQR-scaled nearest same-substrate training observation; threshold=95th percentile of training leave-lab-out distances. Heuristic, not a probability.'}
