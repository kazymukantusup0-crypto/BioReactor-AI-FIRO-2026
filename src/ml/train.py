from importlib.metadata import version
import hashlib
import math
import platform
import joblib
import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GroupKFold, GroupShuffleSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from src.data.prepare import ROOT, FEATURES, NUMERIC, UNIT, prepare, write_json

SEED = 2026


def metrics(y, pred):
    return {'MAE': float(mean_absolute_error(y, pred)), 'RMSE': float(np.sqrt(mean_squared_error(y, pred))), 'R2': float(r2_score(y, pred)) if len(y) > 1 else None, 'n': len(y)}


def partitions(frame):
    remaining = np.arange(len(frame))
    result = {}
    for name, fraction in [('test', .16), ('calibration', .12 / .84), ('validation', .16 / .72)]:
        keep, hold = next(GroupShuffleSplit(n_splits=1, test_size=fraction, random_state=SEED).split(remaining, groups=frame.iloc[remaining].lab_id))
        result[name] = remaining[hold]
        remaining = remaining[keep]
    result['train'] = remaining
    return result


def make_pipeline(regressor):
    preprocessing = ColumnTransformer([
        ('numeric', SimpleImputer(strategy='median', keep_empty_features=True), NUMERIC),
        ('category', OneHotEncoder(handle_unknown='ignore', sparse_output=False), ['substrate']),
    ])
    return Pipeline([('features', preprocessing), ('model', regressor)])


def train(source=None):
    from catboost import CatBoostRegressor
    frame = prepare(source)
    splits = partitions(frame)
    x, y = frame[FEATURES], frame.bmp_calc
    ti, vi, ci, si = [splits[k] for k in ['train', 'validation', 'calibration', 'test']]
    candidates = {'Dummy': [DummyRegressor(strategy='median')],
        'RandomForest': [RandomForestRegressor(n_estimators=200, min_samples_leaf=leaf, random_state=SEED, n_jobs=2) for leaf in [2, 8]],
        'CatBoost': [CatBoostRegressor(iterations=350, depth=depth, learning_rate=.04, loss_function='MAE', random_seed=SEED, thread_count=2, verbose=False, allow_writing_files=False) for depth in [3, 5]]}
    cv = GroupKFold(n_splits=4)
    cv_rows, val_rows, fitted = [], [], {}
    for name, models in candidates.items():
        ranked = []
        for index, reg in enumerate(models):
            scores = []
            for fold, (a, b) in enumerate(cv.split(x.iloc[ti], y.iloc[ti], groups=frame.iloc[ti].lab_id)):
                pipe = make_pipeline(clone(reg)).fit(x.iloc[ti[a]], y.iloc[ti[a]])
                score = metrics(y.iloc[ti[b]], pipe.predict(x.iloc[ti[b]]))
                cv_rows.append({'model': name, 'candidate': index, 'fold': fold, **score})
                scores.append(score['MAE'])
            ranked.append((float(np.mean(scores)), index))
        _, best = min(ranked)
        pipe = make_pipeline(clone(models[best])).fit(x.iloc[ti], y.iloc[ti])
        fitted[name] = pipe
        val_rows.append({'model': name, 'candidate': best, **metrics(y.iloc[vi], pipe.predict(x.iloc[vi]))})
        print(name, val_rows[-1], flush=True)
    winner = min(val_rows, key=lambda r: r['MAE'])['model']
    pipe = fitted[winner]  # Frozen before calibration and test. No refit.
    cal_errors = np.abs(y.iloc[ci].to_numpy() - pipe.predict(x.iloc[ci]))
    lab_errors = pd.DataFrame({'lab': frame.iloc[ci].lab_id.to_numpy(), 'error': cal_errors}).groupby('lab').error.max().to_numpy()
    alpha = .1
    rank = math.ceil((len(lab_errors) + 1) * (1 - alpha))
    radius = float(np.sort(lab_errors)[rank - 1]) if rank <= len(lab_errors) else None
    # Few calibration labs cannot yield a finite 90% group conformal bound.
    test_pred = pipe.predict(x.iloc[si])
    test_scores = []
    for name, model in fitted.items():
        test_scores.append({'model': name, **metrics(y.iloc[si], model.predict(x.iloc[si]))})
    residuals = frame.iloc[si][['lab_id', 'substrate', 'bottle_id', 'bmp_calc']].copy()
    residuals['prediction'] = test_pred
    residuals['error'] = test_pred - residuals.bmp_calc
    residuals.to_csv(ROOT / 'reports/test_predictions.csv', index=False)
    category_rows = []
    for category, subset in residuals.groupby('substrate'):
        category_rows.append({'substrate': category, **metrics(subset.bmp_calc, subset.prediction)})
    pd.DataFrame(category_rows).to_csv(ROOT / 'reports/error_by_substrate.csv', index=False)
    pd.DataFrame(cv_rows).to_csv(ROOT / 'reports/train_cv.csv', index=False)
    pd.DataFrame(val_rows).to_csv(ROOT / 'reports/validation_metrics.csv', index=False)
    pd.DataFrame(test_scores).to_csv(ROOT / 'reports/test_metrics.csv', index=False)
    assignments = frame[['lab_id', 'bottle_id']].copy()
    for name, indices in splits.items():
        assignments.loc[indices, 'partition'] = name
    assignments.to_csv(ROOT / 'data/processed/split_assignments.csv', index=False)
    schema = {'features': FEATURES, 'numeric': NUMERIC, 'categories': sorted(frame.iloc[ti].substrate.unique().tolist()),
        'bounds': {c: [float(frame.iloc[ti][c].min()), float(frame.iloc[ti][c].max())] for c in NUMERIC}, 'unit': UNIT}
    metadata = {'selected_model': winner, 'seed': SEED, 'selection': 'Four-fold laboratory CV on train chooses hyperparameters; validation MAE chooses algorithm; calibration/test untouched until frozen.',
        'partitions': {name: {'rows': len(indices), 'labs': sorted(frame.iloc[indices].lab_id.unique().tolist())} for name, indices in splits.items()},
        'test': next(r for r in test_scores if r['model'] == winner),
        'interval': {'alpha': alpha, 'radius': radius, 'calibration_labs': len(lab_errors), 'method': 'Split conformal on per-lab maximum absolute residual; exchangeability of labs required.',
            'limitation': 'Too few calibration laboratories for finite 90% group interval.' if radius is None else 'Exploratory guarantee requires exchangeable laboratories; not guaranteed for new substrates or reactors.'},
        'schema': schema, 'python': platform.python_version(),
        'versions': {p: version(p) for p in ['numpy', 'pandas', 'scikit-learn', 'catboost', 'joblib', 'matplotlib']},
        'processed_sha256': hashlib.sha256((ROOT / 'data/processed/bmp.csv').read_bytes()).hexdigest(),
        'limitations': ['One study only; no independent-study test.', 'Only represented shared substrates, laboratory batch BMP.', 'No temperature, pH, HRT or reactor production prediction.', 'Test results are not used to revise selection.']}
    metadata['model_version'] = 'hafner-' + hashlib.sha256(json_bytes(metadata)).hexdigest()[:12]
    (ROOT / 'models').mkdir(exist_ok=True)
    joblib.dump({'pipeline': pipe, 'metadata': metadata}, ROOT / 'models/bmp.joblib')
    write_json(ROOT / 'models/metadata.json', metadata)
    write_json(ROOT / 'models/features.json', schema)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(1, 2, figsize=(10, 4))
    ax[0].scatter(residuals.bmp_calc, residuals.prediction, s=12)
    ax[0].set(xlabel='Measured BMP (mL CH4/g VS)', ylabel='Predicted BMP')
    ax[1].hist(residuals.error, bins=20)
    ax[1].set(xlabel='Prediction minus measured BMP', ylabel='Bottles')
    fig.tight_layout()
    fig.savefig(ROOT / 'reports/test_errors.png', dpi=160)
    plt.close(fig)
    lines = ['# Stage 1: actual run', '', f'Selected by validation MAE: **{winner}**.', '', pd.DataFrame(test_scores).to_string(index=False), '',
        'Metrics: BMP in mL CH4/g substrate VS; RMSE in same units; R2 dimensionless.',
        'All algorithms evaluated on final holdout once for comparison; selection frozen beforehand.',
        'One interlaboratory study, not independent-study validation. No synthetic training data.',
        'Finite 90% group interval unavailable with this calibration laboratory count.' if radius is None else 'See metadata for group interval assumptions.',
        'See data_audit.json, provenance.json, train_cv.csv, validation_metrics.csv and test_predictions.csv.']
    (ROOT / 'reports/stage1.md').write_text('\n'.join(lines), encoding='utf-8')
    print('Selected:', winner, metadata['test'])
    return metadata


def json_bytes(value):
    import json
    return json.dumps(value, sort_keys=True).encode()
