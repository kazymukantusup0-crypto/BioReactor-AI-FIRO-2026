"""Prepare original Hafner bottles, never using gas outcomes as predictors."""
from pathlib import Path
import hashlib
import json
import shutil
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
FEATURES = ['substrate', 'c_vs_sub_m', 'c_vs_sub_f', 'c_vs_inoc', 'ISR']
NUMERIC = FEATURES[1:]
KEYS = ['test', 'set', 'lab_id', 'file_id', 'substrate', 'bottle_id']
UNIT = 'mL CH4/g substrate VS'


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')


def prepare(source=None):
    source = Path(source) if source else ROOT.parent / 'biogas_ai_dataset/data/raw/hafner_2026_il_bmp'
    dest = ROOT / 'data/raw/hafner_2026_il_bmp'
    dest.mkdir(parents=True, exist_ok=True)
    hashes = {}
    for name in ['README.md', 'LICENSE', 'data/BMP_calc.csv', 'data/setup.csv']:
        original = source / name
        target = dest / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if original.resolve() != target.resolve():
            shutil.copy2(original, target)
        hashes[name] = hashlib.sha256(target.read_bytes()).hexdigest()
    bmp = pd.read_csv(dest / 'data/BMP_calc.csv')
    setup = pd.read_csv(dest / 'data/setup.csv')
    if bmp.duplicated(KEYS).any() or setup.duplicated(KEYS).any():
        raise ValueError('Duplicate bottle keys: manual review required')
    frame = bmp[KEYS + ['bmp_calc']].merge(setup[KEYS + NUMERIC], on=KEYS, how='left', validate='one_to_one', indicator=True)
    if not frame['_merge'].eq('both').all():
        raise ValueError('Unmatched bottle setup')
    frame = frame.drop(columns='_merge')
    for col in NUMERIC + ['bmp_calc']:
        frame[col] = pd.to_numeric(frame[col], errors='raise')
    invalid = pd.Series(False, index=frame.index)
    for col in NUMERIC[:3]:
        invalid |= frame[col].notna() & (~np.isfinite(frame[col]) | ~frame[col].between(0, 1))
    invalid |= frame.ISR.notna() & (~np.isfinite(frame.ISR) | (frame.ISR <= 0))
    invalid |= ~np.isfinite(frame.bmp_calc) | (frame.bmp_calc < 0)
    invalid |= frame.substrate.isna() | frame.lab_id.isna()
    report = {
        'raw_rows': len(frame), 'missing': frame.isna().sum().to_dict(),
        'duplicate_bottle_keys': int(frame.duplicated(KEYS).sum()),
        'identical_feature_target_rows': int(frame.duplicated(FEATURES + ['bmp_calc']).sum()),
        'invalid_rows_excluded': int(invalid.sum()),
        'extreme_bmp_above_1000_retained_for_review': int((frame.bmp_calc > 1000).sum()),
        'distributions': json.loads(frame[NUMERIC + ['bmp_calc']].describe().to_json()),
        'units': {**{c: 'g VS/g fresh material' for c in NUMERIC[:3]}, 'ISR': 'g inoculum VS/g substrate VS', 'bmp_calc': UNIT},
        'replicates': 'Bottle replicates retained; all records from each laboratory stay in one partition.',
        'leakage_control': 'Explicit input allowlist. Excludes fv_inoc, gas volumes, SMP, reported BMP, identifiers and all target aliases.',
    }
    clean = frame.loc[~invalid].copy().reset_index(drop=True)
    if clean.lab_id.nunique() < 12:
        raise ValueError('At least 12 independent laboratories required for four partitions')
    (ROOT / 'data/processed').mkdir(parents=True, exist_ok=True)
    (ROOT / 'reports').mkdir(exist_ok=True)
    frame.loc[invalid].to_csv(ROOT / 'reports/excluded_rows.csv', index=False)
    clean.to_csv(ROOT / 'data/processed/bmp.csv', index=False)
    write_json(ROOT / 'reports/data_audit.json', report)
    provenance = {
        'source': 'https://github.com/AU-BCE-EE/Hafner-2026-IL-BMP',
        'paper': 'https://doi.org/10.1016/j.biortech.2026.134136',
        'local_manifest_claimed_commit': 'a4e3dc1a6fdadc3339dc3b49271d7790e5c51c93',
        'commit_verification': 'Inherited local snapshot; not independently compared with remote in this run.',
        'license': 'CC BY 4.0; see preserved LICENSE', 'sha256': hashes,
        'data_kind': 'Experimental bottle BMP calculated by source authors from submitted measurements; not theoretical BMP.',
        'scope': 'One interlaboratory study. Laboratory holdout is NOT independent-study validation.',
        'mendeley': {'url': 'https://data.mendeley.com/datasets/g6z68g9ytb/1', 'status': '2026-10-28 public-api request returned HTTP 403; CSV not available locally; no rows fabricated'},
        'other_sources': {'BMP-data': 'Not merged: no verified license in local manifest', 'Zenodo 21079219': 'Embargoed until 2026-12-26; not downloaded or merged'},
    }
    write_json(ROOT / 'reports/provenance.json', provenance)
    return clean
