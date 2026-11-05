import math
import joblib
import pandas as pd
from src.data.prepare import ROOT, FEATURES, NUMERIC


def positive(value, name, zero=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or (value < 0 if zero else value <= 0):
        raise ValueError(f'{name} must be a finite {"nonnegative" if zero else "positive"} number')
    return float(value)


def predict_bmp(payload, model_path=None):
    if not isinstance(payload, dict):
        raise ValueError('Input must be a JSON object')
    # Load only the trusted artifact created locally by train; joblib is executable.
    bundle = joblib.load(model_path or ROOT / 'models/bmp.joblib')
    meta = bundle['metadata']
    schema = meta['schema']
    missing = [f for f in FEATURES if f not in payload or payload[f] is None]
    if missing:
        raise ValueError('Missing measured input features: ' + ', '.join(missing))
    if payload['substrate'] not in schema['categories']:
        raise ValueError('Unsupported substrate; supported: ' + ', '.join(schema['categories']))
    warnings = list(meta['limitations'])
    values = {'substrate': payload['substrate']}
    for col in NUMERIC:
        val = positive(payload[col], col, zero=col != 'ISR')
        if col != 'ISR' and val > 1:
            raise ValueError(f'{col} must be g/g in [0,1], not percent')
        low, high = schema['bounds'][col]
        if not low <= val <= high:
            raise ValueError(f'{col} outside training domain [{low}, {high}]; prediction refused')
        values[col] = val
    for name in ['mass_kg', 'reactor_volume_l', 'vs_mass_kg']:
        if name in payload:
            positive(payload[name], name)
    if 'temperature_c' in payload:
        temp = payload['temperature_c']
        if isinstance(temp, bool) or not isinstance(temp, (int, float)) or not math.isfinite(temp) or temp <= -273.15:
            raise ValueError('temperature_c must be finite and above absolute zero')
    if 'mass_kg' in payload and 'vs_mass_kg' in payload and payload['vs_mass_kg'] > payload['mass_kg']:
        raise ValueError('VS mass cannot exceed fresh mass')
    result = float(bundle['pipeline'].predict(pd.DataFrame([values]))[0])
    if not math.isfinite(result) or result < 0:
        raise ValueError('Model produced invalid BMP; manual review required')
    radius = meta['interval']['radius']
    out = {'bmp': result, 'unit': schema['unit'], 'model_version': meta['model_version'], 'model': meta['selected_model'],
        'used_features': {c: values[c] for c in schema.get('prediction_features', FEATURES)}, 'uncertainty': {'interval_90': [max(0, result-radius), result+radius] if radius is not None else None, 'explanation': meta['interval']['limitation']},
        'warnings': warnings, 'ignored_context_fields': sorted(set(payload) - set(FEATURES) - {'vs_mass_kg'})}
    detector = bundle.get('domain_detector')
    if detector is not None:
        out['domain_assessed_features'] = values
        out['domain'] = detector.assess(values)
        if out['domain']['out_of_distribution']:
            warnings.append('Input combination outside empirical same-substrate training support; BMP is an unreliable extrapolation.')
        if out['domain'].get('limited_support'):
            warnings.append('Substrate has limited independent training support; more measured laboratories/parties are required.')
    else:
        out['domain'] = {'status': 'unavailable', 'out_of_distribution': None}
        warnings.append('Legacy artifact: only global numeric bounds are checked; multivariate applicability is unknown.')
    if meta.get('experimental_uncertainty'):
        out['experimental_uncertainty'] = meta['experimental_uncertainty']
    if 'vs_mass_kg' in payload:
        out['potential_methane_m3'] = result * payload['vs_mass_kg'] / 1000
        warnings.append('Potential BMP-based volume only, at source gas reference conditions; not actual reactor production.')
    return out
