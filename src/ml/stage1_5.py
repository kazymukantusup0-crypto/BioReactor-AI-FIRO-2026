"""Stage 1.5: nested training-only laboratory CV, immutable stage-1 artifacts."""
import hashlib
import json
from pathlib import Path
import platform
from importlib.metadata import version
import joblib
import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import ExtraTreesRegressor, HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from src.data.prepare import ROOT, FEATURES, NUMERIC, write_json
from src.ml.train import SEED, metrics, json_bytes
from src.ml.estimators import ScientificFeatures, SubstrateMedian, ENGINEERED
from src.ml.reliability import DomainDetector, group_radius

OUT = ROOT / 'reports/stage1_5'
MODEL = ROOT / 'models/stage1_5'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def preserved_paths():
    return [p for directory in ['models', 'reports', 'data'] for p in (ROOT / directory).rglob('*')
            if p.is_file() and 'stage1_5' not in p.parts and p.name != 'stage1_5.md']


def lab_mae(y, prediction, groups):
    f = pd.DataFrame({'error': np.abs(np.asarray(y)-prediction), 'lab': np.asarray(groups)})
    return float(f.groupby('lab').error.mean().mean())


def scored(frame, prediction):
    return {**metrics(frame.bmp_calc, prediction), 'macro_lab_MAE': lab_mae(frame.bmp_calc, prediction, frame.lab_id)}


def make(regressor, mode='raw'):
    if isinstance(regressor, SubstrateMedian):
        return regressor
    columns = NUMERIC + (ENGINEERED if mode == 'engineered' else [])
    if mode == 'drop_fixed':
        columns = [c for c in columns if c != 'c_vs_sub_f']
    processor = ColumnTransformer([
        ('numeric', Pipeline([('impute', SimpleImputer(strategy='median')), ('scale', StandardScaler())]), columns),
        ('category', OneHotEncoder(handle_unknown='ignore', sparse_output=False), ['substrate'])])
    return Pipeline([('scientific', ScientificFeatures(mode)), ('preprocess', processor), ('model', regressor)])


def candidate_grid():
    from catboost import CatBoostRegressor
    def cat(depth=3, iterations=350, rate=.04, l2=3):
        return CatBoostRegressor(depth=depth, iterations=iterations, learning_rate=rate, l2_leaf_reg=l2,
            loss_function='MAE', random_seed=SEED, thread_count=2, verbose=False, allow_writing_files=False)
    return {
        'Dummy': [make(DummyRegressor(strategy='median'))],
        'SubstrateMedian': [SubstrateMedian()],
        'Stage1CatBoost': [make(cat())],
        'Ridge': [make(Ridge(alpha=alpha), mode) for alpha, mode in [(10, 'raw'), (100, 'engineered'), (100, 'drop_fixed')]],
        'RandomForest': [make(RandomForestRegressor(n_estimators=180, min_samples_leaf=leaf, max_features=.8,
            criterion='absolute_error', random_state=SEED, n_jobs=2), mode) for leaf, mode in [(4, 'raw'), (10, 'engineered'), (10, 'drop_fixed')]],
        'ExtraTrees': [make(ExtraTreesRegressor(n_estimators=180, min_samples_leaf=leaf, max_features=.8,
            criterion='absolute_error', random_state=SEED, n_jobs=2), mode) for leaf, mode in [(4, 'raw'), (10, 'engineered'), (10, 'drop_fixed')]],
        'HistGradientBoosting': [make(HistGradientBoostingRegressor(loss='absolute_error', max_iter=180,
            max_leaf_nodes=leaves, l2_regularization=10, min_samples_leaf=15, early_stopping=False, random_state=SEED), mode)
            for leaves, mode in [(4, 'raw'), (7, 'engineered'), (4, 'drop_fixed')]],
        'CatBoost': [make(cat(depth, iters, rate, l2), mode) for depth, iters, rate, l2, mode in [
            (2, 300, .03, 10, 'raw'), (3, 500, .03, 10, 'raw'), (4, 300, .03, 20, 'raw'),
            (2, 300, .03, 10, 'engineered'), (3, 500, .03, 10, 'engineered'), (3, 500, .03, 10, 'drop_fixed')]],
    }


def choose(candidates, frame, family, outer, logs):
    rankings = []
    for index, candidate in enumerate(candidates):
        scores = []
        for fold, (a, b) in enumerate(GroupKFold(3).split(frame, groups=frame.lab_id)):
            model = clone(candidate).fit(frame.iloc[a][FEATURES], frame.iloc[a].bmp_calc)
            score = lab_mae(frame.iloc[b].bmp_calc, model.predict(frame.iloc[b][FEATURES]), frame.iloc[b].lab_id)
            logs.append({'family': family, 'outer': outer, 'candidate': index, 'inner_fold': fold, 'macro_lab_MAE': score})
            scores.append((score, frame.iloc[b].lab_id.nunique()))
        # Each laboratory gets equal total weight, including unequal fold sizes.
        rankings.append((float(np.average([s[0] for s in scores], weights=[s[1] for s in scores])), index))
    return min(rankings)[1]


def describe_model(model):
    return {k: ('NaN' if isinstance(v, float) and not np.isfinite(v) else v)
            for k, v in model.get_params(deep=True).items() if isinstance(v, (str, float, int, bool)) or v is None}


def error_tables(frame, predictions, name):
    f = frame[['lab_id', 'substrate', 'bottle_id', 'bmp_calc']].copy()
    f['prediction'] = predictions
    f['absolute_error'] = np.abs(f.prediction-f.bmp_calc)
    f.to_csv(OUT / f'{name}_predictions.csv', index=False)
    for grouping in ['substrate', 'lab_id']:
        rows = [{grouping: key, 'labs': part.lab_id.nunique(), **scored(part, part.prediction.to_numpy())} for key, part in f.groupby(grouping)]
        pd.DataFrame(rows).to_csv(OUT / f'{name}_errors_by_{grouping}.csv', index=False)
    return f


def run():
    OUT.mkdir(parents=True, exist_ok=True)
    MODEL.mkdir(parents=True, exist_ok=True)
    protected = {str(p.relative_to(ROOT)): digest(p) for p in preserved_paths()}
    write_json(OUT / 'stage1_hashes_before.json', protected)
    frame = pd.read_csv(ROOT / 'data/processed/bmp.csv')
    assignments = pd.read_csv(ROOT / 'data/processed/split_assignments.csv')
    frame = frame.merge(assignments, on=['lab_id', 'bottle_id'], validate='one_to_one')
    if frame.groupby('lab_id').partition.nunique().max() != 1 or len(frame) != 613:
        raise ValueError('Unexpected original partitions or data; review required')
    train = frame[frame.partition == 'train'].copy().reset_index(drop=True)
    # Target values of test are never passed to fitting, scoring or diagnostics.
    val = frame[frame.partition == 'validation'].copy()
    cal = frame[frame.partition == 'calibration'].copy()
    counts = frame.groupby(['partition', 'substrate']).agg(rows=('bottle_id','size'), labs=('lab_id','nunique')).reset_index()
    counts.to_csv(OUT / 'substrate_support.csv', index=False)
    train[NUMERIC + ['bmp_calc']].describe().to_csv(OUT / 'train_distributions.csv')
    train.groupby('substrate')[NUMERIC].nunique().to_csv(OUT / 'train_feature_cardinality.csv')
    raw_setup = pd.read_csv(ROOT / 'data/raw/hafner_2026_il_bmp/data/setup.csv')
    write_json(OUT / 'raw_columns.json', {'setup': list(raw_setup.columns),
        'bmp': list(pd.read_csv(ROOT / 'data/raw/hafner_2026_il_bmp/data/BMP_calc.csv', nrows=0).columns),
        'selected': FEATURES, 'missing_selected_train': train[FEATURES].isna().sum().to_dict()})
    grid = candidate_grid()
    write_json(OUT / 'search_space.json', {family: [describe_model(m) for m in models] for family, models in grid.items()})
    write_json(OUT / 'protocol.json', {'seed': SEED, 'outer_folds': 4, 'inner_folds': 3,
        'selection_metric': 'Equal-laboratory mean absolute error from training-only nested OOF predictions',
        'family_selection_bias': 'Choosing best family from outer CV makes its reported CV optimistic; no new untouched test exists.',
        'test': 'Viewed during stage 1; not evaluated again, not used by this search.',
        'validation': 'Previously viewed; used once after family/configuration freeze for descriptive comparison only.',
        'rare_rule': 'Train labs <12 OR train rows <40; declared before fitting.',
        'candidate_count': sum(map(len, grid.values()))})
    folds = list(GroupKFold(4).split(train, groups=train.lab_id))
    write_json(OUT / 'cv_labs.json', [{'fold': i, 'train_labs': sorted(train.iloc[a].lab_id.unique()), 'heldout_labs': sorted(train.iloc[b].lab_id.unique())} for i, (a,b) in enumerate(folds)])
    inner, outer, selected, oof, fold_models = [], [], [], {}, {}
    for family, candidates in grid.items():
        pred = np.full(len(train), np.nan)
        fold_models[family] = []
        for fold, (a, b) in enumerate(folds):
            best = choose(candidates, train.iloc[a], family, fold, inner) if len(candidates) > 1 else 0
            model = clone(candidates[best]).fit(train.iloc[a][FEATURES], train.iloc[a].bmp_calc)
            pred[b] = model.predict(train.iloc[b][FEATURES])
            fold_models[family].append(model)
            outer.append({'family': family, 'fold': fold, 'candidate': best, **scored(train.iloc[b], pred[b])})
        oof[family] = pred
        selected.append({'family': family, **scored(train, pred)})
        print('nested CV:', selected[-1], flush=True)
    comparison = pd.DataFrame(selected).sort_values(['macro_lab_MAE', 'family'])
    comparison.to_csv(OUT / 'nested_cv_comparison.csv', index=False)
    pd.DataFrame(outer).to_csv(OUT / 'outer_folds.csv', index=False)
    pd.DataFrame(inner).to_csv(OUT / 'inner_search.csv', index=False)
    pd.DataFrame(oof).to_csv(OUT / 'all_oof_predictions.csv', index=False)
    winner = str(comparison.iloc[0].family)
    best_index = choose(grid[winner], train, winner, 'full_train', inner) if len(grid[winner]) > 1 else 0
    pd.DataFrame(inner).to_csv(OUT / 'inner_search.csv', index=False)
    pipeline = clone(grid[winner][best_index]).fit(train[FEATURES], train.bmp_calc)
    # Choice frozen here, before examining calibration and validation outcomes.
    write_json(OUT / 'frozen_selection.json', {'family': winner, 'candidate': best_index, 'parameters': describe_model(pipeline)})
    validation_prediction = pipeline.predict(val[FEATURES])
    validation = scored(val, validation_prediction)
    baseline = joblib.load(ROOT / 'models/bmp.joblib')
    baseline_val = scored(val, baseline['pipeline'].predict(val[FEATURES]))
    error_tables(train, oof[winner], 'nested_oof')
    val_errors = error_tables(val, validation_prediction, 'validation')
    support = counts[counts.partition=='train'].set_index('substrate')
    rare = support.index[(support.labs < 12) | (support.rows < 40)].tolist()
    rare_results = []
    for label, f, pred in [('nested_oof', train, oof[winner]), ('validation', val, validation_prediction)]:
        for category in rare:
            mask = f.substrate.eq(category)
            rare_results.append({'evaluation': label, 'substrate': category, 'train_rows': int(support.loc[category,'rows']),
                'train_labs': int(support.loc[category,'labs']), **scored(f.loc[mask], pred[mask])})
    pd.DataFrame(rare_results).to_csv(OUT / 'rare_substrates.csv', index=False)
    cal_error = np.abs(cal.bmp_calc.to_numpy() - pipeline.predict(cal[FEATURES]))
    r90, r80 = group_radius(cal_error, cal.lab_id.to_numpy(), .1), group_radius(cal_error, cal.lab_id.to_numpy(), .2)
    covered = np.abs(val.bmp_calc.to_numpy()-validation_prediction) <= r80 if r80 is not None else np.zeros(len(val), dtype=bool)
    covered_groups = pd.DataFrame({'lab': val.lab_id.to_numpy(), 'covered': covered}).groupby('lab').covered.all()
    uncertainty = {'group_radius_90': r90, 'experimental_group_radius_80': r80,
        'calibration_labs': int(cal.lab_id.nunique()), 'validation_labs': int(val.lab_id.nunique()),
        'validation_row_coverage': float(covered.mean()), 'validation_all_bottles_group_coverage': float(covered_groups.mean()),
        'covered_validation_labs': int(covered_groups.sum()),
        'warning': 'Only four calibration labs and five previously viewed validation labs. 80% band is exploratory; observed coverage does not establish population coverage. 90% finite band unavailable. Group exchangeability, group sizes and substrate composition may differ.'}
    write_json(OUT / 'uncertainty.json', uncertainty)
    detector = DomainDetector().fit(train)
    domain_rows = [{'bottle_id': int(row.bottle_id), **detector.assess(row)} for _, row in val.iterrows()]
    write_json(OUT / 'validation_domain.json', domain_rows)
    importance, stability = [], []
    rng = np.random.default_rng(SEED)
    for fold, (a, b) in enumerate(folds):
        hold = train.iloc[b].copy()
        model = fold_models[winner][fold]
        original = model.predict(hold[FEATURES])
        base = lab_mae(hold.bmp_calc, original, hold.lab_id)
        for col in FEATURES:
            for repeat in range(5):
                changed = hold[FEATURES].copy()
                # Within-substrate numeric permutations reduce category mixing, but
                # can still create implausible numeric combinations; diagnostic only.
                if col == 'substrate':
                    changed[col] = rng.permutation(changed[col].to_numpy())
                else:
                    for _, indices in changed.groupby('substrate').groups.items():
                        changed.loc[indices, col] = rng.permutation(changed.loc[indices,col].to_numpy())
                delta = lab_mae(hold.bmp_calc, model.predict(changed), hold.lab_id)-base
                importance.append({'fold': fold, 'feature': col, 'repeat': repeat, 'macro_MAE_increase': delta})
        fold_domain = DomainDetector().fit(train.iloc[a])
        for col in NUMERIC:
            for factor in [.95, 1.05]:
                changed = hold[FEATURES].copy()
                changed[col] = changed[col]*factor
                if col != 'ISR':
                    changed[col] = changed[col].clip(0, 1)
                shift = np.abs(model.predict(changed)-original)
                ood = [fold_domain.assess(row)['out_of_distribution'] for _,row in changed.iterrows()]
                stability.append({'fold': fold, 'feature': col, 'factor': factor, 'mean_absolute_prediction_change': float(shift.mean()),
                    'max_absolute_prediction_change': float(shift.max()), 'n': len(hold), 'OOD_fraction': float(np.mean(ood))})
    pd.DataFrame(importance).to_csv(OUT / 'permutation_importance.csv', index=False)
    pd.DataFrame(stability).to_csv(OUT / 'sensitivity.csv', index=False)
    baseline_diagnostics(train, folds, grid['Stage1CatBoost'][0])
    # No global or category bounds are learned from validation/calibration/test.
    schema = {'features': FEATURES, 'numeric': NUMERIC, 'categories': sorted(train.substrate.unique()),
        'bounds': {c: [float(train[c].min()), float(train[c].max())] for c in NUMERIC}, 'unit': baseline['metadata']['schema']['unit']}
    schema['prediction_features'] = ['substrate'] if winner == 'SubstrateMedian' else FEATURES
    schema['diagnostic_features'] = NUMERIC
    metadata = {'selected_model': winner, 'schema': schema, 'seed': SEED, 'artifact_format': 2,
        'stage': '1.5', 'selection': 'Nested grouped CV only on original training labs; final inner CV selects configuration.',
        'nested_cv': comparison.iloc[0].to_dict(), 'validation': validation, 'stage1_validation': baseline_val,
        'test': None, 'test_status': 'Previously viewed in stage1; not rescored or used for selection in stage1.5',
        'parameters': describe_model(pipeline), 'rare_substrates': rare,
        'interval': {'alpha': .1, 'radius': r90, 'limitation': uncertainty['warning']}, 'experimental_uncertainty': uncertainty,
        'limitations': ['Research only: one study with six shared substrates.', 'Nested CV winner selection is optimistic; validation was previously viewed.',
            'Required composition and operating conditions are not represented; no reactor yield prediction.', 'Input domain detector is heuristic and cannot establish applicability.'],
        'python': platform.python_version(), 'versions': {p: version(p) for p in ['numpy','pandas','scikit-learn','catboost','joblib','matplotlib']},
        'data_sha256': digest(ROOT/'data/processed/bmp.csv'), 'split_sha256': digest(ROOT/'data/processed/split_assignments.csv')}
    metadata['model_version'] = 'stage1_5-' + hashlib.sha256(json_bytes(metadata)).hexdigest()[:12]
    joblib.dump({'pipeline': pipeline, 'metadata': metadata, 'domain_detector': detector}, MODEL/'bmp.joblib')
    write_json(MODEL/'metadata.json', metadata)
    write_json(MODEL/'features.json', schema)
    plots(train, comparison, pd.DataFrame(importance), pd.DataFrame(stability), oof[winner], counts)
    unchanged = all((ROOT / p).exists() and digest(ROOT / p) == value for p,value in protected.items())
    write_json(OUT / 'preservation_check.json', {'all_stage1_artifacts_unchanged': unchanged, 'files_checked': len(protected)})
    if not unchanged:
        raise RuntimeError('Stage-1 artifacts changed unexpectedly')
    write_report(metadata, comparison, counts, pd.DataFrame(importance), pd.DataFrame(outer), val_errors)
    print('Selected:', winner, 'validation:', validation, 'preserved:', unchanged, flush=True)
    return metadata


def plots(train, comparison, importance, sensitivity, pred, counts):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 3, figsize=(13, 7))
    for ax,col in zip(axes.flat, NUMERIC+['bmp_calc']):
        for name,part in train.groupby('substrate'):
            ax.hist(part[col], bins=15, alpha=.35, label=name)
        ax.set_title(col)
    axes.flat[-1].axis('off')
    axes.flat[0].legend(fontsize=6)
    fig.tight_layout(); fig.savefig(OUT/'distributions.png', dpi=150); plt.close(fig)
    fig,axes = plt.subplots(1,2,figsize=(12,4))
    axes[0].barh(comparison.family, comparison.macro_lab_MAE)
    axes[0].set_xlabel('Nested OOF macro laboratory MAE (mL CH4/g VS)')
    imp = importance.groupby('feature').macro_MAE_increase.agg(['mean','std'])
    axes[1].barh(imp.index, imp['mean'], xerr=imp['std'].fillna(0))
    axes[1].set_xlabel('Conditional permutation MAE increase (diagnostic)')
    fig.tight_layout(); fig.savefig(OUT/'comparison_importance.png', dpi=150); plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(11,4))
    for name,part in train.assign(prediction=pred).groupby('substrate'):
        axes[0].scatter(part.bmp_calc,part.prediction,s=12,label=name)
    axes[0].set(xlabel='Measured BMP',ylabel='Nested OOF predicted BMP')
    axes[0].legend(fontsize=6)
    categories=sorted(train.substrate.unique())
    axes[1].boxplot([pred[train.substrate.eq(c)]-train.loc[train.substrate.eq(c),'bmp_calc'].to_numpy() for c in categories],tick_labels=categories)
    axes[1].tick_params(axis='x',labelrotation=45)
    axes[1].set_ylabel('Nested OOF prediction minus measured BMP')
    fig.tight_layout();fig.savefig(OUT/'errors.png',dpi=150);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(11,4))
    stability=sensitivity.groupby('feature').mean_absolute_prediction_change.mean()
    axes[0].barh(stability.index,stability.values)
    axes[0].set_xlabel('Mean prediction change at +/-5% input (mL/g VS)')
    support=counts[counts.partition=='train']
    axes[1].barh(support.substrate,support.labs)
    axes[1].set_xlabel('Independent training laboratories')
    fig.tight_layout();fig.savefig(OUT/'stability_support.png',dpi=150);plt.close(fig)


def baseline_diagnostics(train, folds, candidate):
    """Inspect fixed stage-1 CatBoost on held-out training laboratories."""
    rng = np.random.default_rng(SEED)
    rows = []
    for fold, (a,b) in enumerate(folds):
        model = clone(candidate).fit(train.iloc[a][FEATURES], train.iloc[a].bmp_calc)
        hold = train.iloc[b]
        base = lab_mae(hold.bmp_calc, model.predict(hold[FEATURES]), hold.lab_id)
        for feature in FEATURES + ['substrate+fixed_reference']:
            for repeat in range(5):
                changed = hold[FEATURES].copy()
                if feature == 'substrate+fixed_reference':
                    order = rng.permutation(len(changed))
                    changed[['substrate','c_vs_sub_f']] = changed[['substrate','c_vs_sub_f']].iloc[order].to_numpy()
                elif feature == 'substrate':
                    changed[feature] = rng.permutation(changed[feature].to_numpy())
                else:
                    for _,indices in changed.groupby('substrate').groups.items():
                        changed.loc[indices,feature] = rng.permutation(changed.loc[indices,feature].to_numpy())
                rows.append({'fold':fold, 'feature':feature, 'repeat':repeat,
                    'macro_MAE_increase':lab_mae(hold.bmp_calc,model.predict(changed),hold.lab_id)-base})
    result=pd.DataFrame(rows)
    result.to_csv(OUT/'stage1_configuration_importance.csv',index=False)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    imp=result.groupby('feature').macro_MAE_increase.agg(['mean','std'])
    fig,ax=plt.subplots(figsize=(8,4))
    ax.barh(imp.index,imp['mean'],xerr=imp['std'].fillna(0))
    ax.set_xlabel('Stage1 CatBoost: held-out train-lab macro MAE increase')
    fig.tight_layout();fig.savefig(OUT/'stage1_importance.png',dpi=150);plt.close(fig)
    return result


def table(frame):
    columns = list(frame.columns)
    def fmt(v):
        return f'{v:.3f}' if isinstance(v, (float, np.floating)) else str(v)
    return '\n'.join(['| '+' | '.join(columns)+' |', '| '+' | '.join(['---']*len(columns))+' |'] +
        ['| '+' | '.join(fmt(v) for v in row)+' |' for row in frame.itertuples(index=False, name=None)])


def write_report(meta, comparison, counts, importance, folds, val_errors):
    imp = importance.groupby('feature').macro_MAE_increase.mean().sort_values(ascending=False)
    baseline_imp = pd.read_csv(OUT/'stage1_configuration_importance.csv').groupby('feature').macro_MAE_increase.mean().sort_values(ascending=False)
    deviations = folds.groupby('family').macro_lab_MAE.agg(['min','max','std']).reset_index()
    report = f'''# Этап 1.5 — научный аудит и улучшение BMP-модели

Дата: 28.10.2026. Данные и результаты этапа 1 сохранены побайтово; проверка:
[preservation_check.json](stage1_5/preservation_check.json).

## 1. Текущая модель и протокол

Этап 1: CatBoost; test MAE 80.38, RMSE 131.99 мл CH4/г VS, R² 0.173.
Test (109 бутылок / 5 лабораторий) уже просмотрен ранее. Поэтому новая независимая
финальная оценка здесь невозможна. Test повторно не прогнозируется, не используется
для выбора признаков, настройки или сравнения новых кандидатов. Старые метрики не
сравниваются напрямую с новой CV как доказательство улучшения.

Исходные train 304 бутылки / 17 лабораторий сохранены. Внешний GroupKFold(4),
внутренний GroupKFold(3) в каждом внешнем train выбирает конфигурацию по MAE с
равным весом лабораторий. Скейлинг, кодирование и импутация обучаются внутри fold.
HistGradientBoosting: early_stopping=False, чтобы не создавать случайный bottle-level
validation внутри обучения. Конфигурации и списки лабораторий сохранены в
[search_space.json](stage1_5/search_space.json) и [cv_labs.json](stage1_5/cv_labs.json).

Выбор семейства по внешней CV сам создаёт оптимизм оценки победителя. CV честно
проверяет настройку внутри каждого семейства, но не является независимой оценкой
процедуры выбора семейства. Малое число лабораторий и один набор fold добавляют
неопределённость; стандартное отклонение fold не является доверительным интервалом.
Validation уже использовался на этапе 1; здесь он только описательная проверка после
фиксации выбора, без замены победителя по результату validation.

## 2. Аудит признаков и исходников

Входы: substrate, c_vs_sub_m (измеренная VS субстрата), c_vs_sub_f (эталонная VS),
c_vs_inoc (VS инокулята), ISR (отношение масс VS). Концентрации — г/г, ISR — г/г VS.
619 исходных бутылок, 613 очищенных; 6 строк с VS >1 исключены на этапе 1, не добавляются
обратно ради метрик. Повторы бутылок одной лаборатории не разделяются между fold.

Инженерия полностью из входов: относительное/абсолютное расхождение измеренной и
эталонной VS, log ISR и log VS инокулята. Проверена абляция без c_vs_sub_f.
Никаких искусственных обучающих наблюдений. Возмущения входов и перестановки используются
только для диагностики, не для обучения и не выдаются за эксперименты.

У c_vs_sub_f в train одна величина на субстрат (Cellulose — две), то есть признак
в основном кодирует категорию. Он доступен только для эталонных общих субстратов
исследования; вне этой постановки его нельзя назначать произвольно. Измеренная VS
также входит в нормировку BMP: математическая связь не означает причинного эффекта.
ISR и свойства инокулята могут отражать лабораторную методику и общий сдвиг измерения.

Прямая утечка: bmp_calc, bmp_rep, smp, cvCH4/cvBg, fv_inoc и аналоги цели,
коэффициенты биоразлагаемости, рассчитанные через измеренный BMP. Исключены также
lab_id/file_id/bottle_id/test/set как предикторы. Они используются только для групп
и аудита. Близкие результаты повторов не считаются независимыми лабораториями.

Отсутствуют в текущей входной таблице: химический состав (липиды, белок, углеводы,
лигнин/целлюлоза, C/N), предобработка, возраст/адаптация инокулята, температура,
рабочий pH, длительность и критерий окончания BMP, стандартизация газа и blank,
качество/калибровка приборов. В полном локальном источнике есть inoc_prop.csv, включая
pH инокулята; это не рабочий pH реактора. Эти поля в данном этапе не добавлялись:
нужны проверка единиц, полноты и момента измерения. Массы setup не добавлены без
подтверждения единиц; газовые временные ряды доступны после начала опыта.

Различия лабораторий, нормировки, эталонная природа сырья и отсутствующие условия
правдоподобно объясняют слабый перенос; причинность этими данными не установлена.

## 3. Поддержка категорий

{table(counts[counts.partition=='train'][['substrate','rows','labs']])}

Заранее заданная относительная редкость: <12 лабораторий ИЛИ <40 train-строк.
Выделены {', '.join(meta['rare_substrates'])}. Это эвристика, а не научная граница
достаточности. Даже 17 лабораторий не дают разнообразия происхождения сырья: это
общие субстраты одного исследования. Навоз, почва, food_waste и смеси не представлены.
Ошибки редких категорий: [rare_substrates.csv](stage1_5/rare_substrates.csv).

## 4. Реальные результаты CV и выбор

{table(comparison[['family','macro_lab_MAE','MAE','RMSE','R2']])}

Все MAE/RMSE — мл CH4/г VS. macro_lab_MAE даёт каждой лаборатории равный вес;
обычный MAE даёт вес каждой бутылке. Разброс между внешними fold:

{table(deviations)}

Выбрано **{meta['selected_model']}**: минимальный nested OOF macro_lab_MAE.
Финальная конфигурация выбрана внутренней GroupKFold на всём исходном train.
Модель обучена только на train; validation/calibration не включены в fit.
Если выбран SubstrateMedian, это обучаемый статистический baseline: прогноз
использует только substrate. Числовые входы обязательны для совместимости контракта
и проверки области применимости; они не влияют на BMP этой модели. Нулевая
чувствительность такой модели к VS/ISR не доказывает физическую независимость BMP.
Сильный baseline — медиана по субстрату, рассчитанная строго на train каждого fold;
её необходимо учитывать прежде, чем приписывать выигрыш сложной ML-модели.

После фиксации выбора validation: новая модель MAE {meta['validation']['MAE']:.3f},
macro_lab_MAE {meta['validation']['macro_lab_MAE']:.3f}, RMSE {meta['validation']['RMSE']:.3f},
R² {meta['validation']['R2']:.3f}; исходная сохранённая модель: MAE
{meta['stage1_validation']['MAE']:.3f}, macro_lab_MAE {meta['stage1_validation']['macro_lab_MAE']:.3f}.
Это описательное сравнение на ранее просмотренном validation, не доказательство
улучшения на новом независимом исследовании. По его результату выбор не пересматривался.

## 5. Важность, ошибки, устойчивость и область применимости

Среднее увеличение macro MAE при перестановке raw-признаков на внешних holdout:

{table(imp.rename('MAE_increase').reset_index())}

Для числовых признаков перестановки внутри субстрата; для substrate — по всему fold.
Зависимость повторов и корреляции признаков остаются: это описательная диагностика,
не p-value и не причинная важность. Перестановка категории при неизменной эталонной
VS может создавать нереалистичные комбинации; признаки с малой условной вариацией
могут получить нулевую важность, даже если они информативны совместно.

Для фиксированной конфигурации исходного CatBoost отдельная диагностика на тех же
внешних обучающих holdout (переобучение конфигурации без подбора, не test):

{table(baseline_imp.rename('MAE_increase').reset_index())}

Совместная перестановка substrate+fixed_reference показывает их общую информацию;
она также не гарантирует физически правдоподобные сочетания с остальными признаками.

Ошибки сохранены по [сырью](stage1_5/nested_oof_errors_by_substrate.csv) и
[лабораториям](stage1_5/nested_oof_errors_by_lab_id.csv), отдельно для validation.
Общий R² необходимо сопоставлять с R² внутри каждой категории: он может отражать
в основном различия между категориями. Отрицательный R² внутри субстрата означает,
что модель не объясняет вариацию отдельных бутылок относительно среднего этого
субстрата в оценочной выборке. Более низкий MAE baseline не доказывает способность
прогнозировать новую партию сырья. Разброс fold у лидирующих моделей велик;
малые различия CV не доказывают статистически значимого превосходства.
Устойчивость: числовые входы внешнего holdout меняются на ±5%, с ограничением VS
диапазоном [0,1]. Фиксируются средний/максимальный сдвиг прогноза и доля OOD.
Это не измеренная погрешность приборов и не интервал неопределённости.

Новый детектор обучается только на train: ближайший сосед того же субстрата в
пространстве числовых признаков, масштабированном train IQR. Порог — 95-й процентиль
расстояний train при исключении всей лаборатории точки; дополнительно проверяются
категориальные диапазоны и ограниченная поддержка. Порог эвристический; нормальные
диапазоны не доказывают применимость. Значения за глобальными train-границами CLI
отклоняет; необычные комбинации внутри границ помечает предупреждением.

## 6. Групповая калибровка

Четыре calibration-лаборатории сохранены отдельно. Score — максимальная абсолютная
ошибка всех бутылок лаборатории. Rank = ceil((G+1)*(1-alpha)). При G=4 и alpha=.1
rank=5>4: конечный 90% диапазон недоступен (null); минимум 9 calibration-групп нужен
только для конечности, а не для надёжной эмпирической проверки.

Экспериментальная полоса при alpha=.2: радиус {meta['experimental_uncertainty']['experimental_group_radius_80']:.3f}.
На пяти ранее просмотренных validation-лабораториях покрыты целиком
{meta['experimental_uncertainty']['covered_validation_labs']}/5;
покрытие бутылок {meta['experimental_uncertainty']['validation_row_coverage']:.3f}.
Она называется экспериментальной полосой, не проверенным 80% или 90% предсказательным
интервалом. Пять групп не подтверждают покрытие популяции; обменность лабораторий,
размеры групп и состав субстратов могут нарушаться. Численный результат и метод:
[uncertainty.json](stage1_5/uncertainty.json).

## 7. Графики

![Распределения только train](stage1_5/distributions.png)
![Сравнение и важность](stage1_5/comparison_importance.png)
![Важность для исходной конфигурации CatBoost](stage1_5/stage1_importance.png)
![Ошибки внешних fold](stage1_5/errors.png)
![Чувствительность и поддержка](stage1_5/stability_support.png)

## 8. Дополнительные данные и научные ограничения

Нужны независимые публикации/лаборатории и разные партии одного вида сырья;
измеренный состав, предобработка, условия BMP, blank, нормировка газа и контроль
приборов. pH инокулята следует отделять от рабочего pH. Для практического реактора
нужны собственные измерения массы VS и газа, времени, температур, pH, OLR/HRT и событий.
Протокол следующего исследования следует зафиксировать до получения новых исходов.
Межлабораторные повторы одного исследования не заменяют независимые исследования.

Этап 1.5 улучшает проверяемость процедуры, но не гарантирует улучшение реальной
обобщающей способности. Шесть общих субстратов недостаточны для универсального BMP.
Подбор ограничен небольшой заранее записанной сеткой; это не исчерпывающая оптимизация.
Сложная модель и feature engineering не должны приниматься только за высокий R².
Новая модель хранится отдельно в models/stage1_5; исходная остаётся CLI по умолчанию.

## Источники

- [Исходный README и словарь Hafner](https://github.com/AU-BCE-EE/Hafner-2026-IL-BMP).
- [Group CV и nested CV, scikit-learn](https://scikit-learn.org/stable/modules/cross_validation.html).
- [Lee, Barber, Willett: Distribution-free inference with hierarchical data](https://arxiv.org/abs/2306.06342).

Проверки исполнения и совместимости записываются отдельно в stage1_5/verification.json.
'''
    (ROOT/'reports/stage1_5.md').write_text(report,encoding='utf-8')
