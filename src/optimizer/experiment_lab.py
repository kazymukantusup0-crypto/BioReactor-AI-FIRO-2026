"""Manual scientific records; observations never train or alter the BMP estimators."""
import csv
from datetime import date, datetime
import io
import json
import re
import uuid
from typing import Annotated, Literal
from pydantic import Field, model_validator
from src.optimizer.schemas import Strict
from src.optimizer.storage import encode
from src.market.domain import utcnow


def validate_quantitative_method(method):
    if not method or not method.strip():
        raise ValueError('Quantitative measurements require an explicit method')
    if re.search(r'\bmq[-_\s]*\d+\b|\bmq\b', method, re.I):
        raise ValueError('Raw MQ sensor readings are qualitative, not quantitative methane measurements')


class MeasurementInput(Strict):
    observed_at: datetime | None = None
    elapsed_days: float | None = Field(default=None, ge=0)
    temperature_c: float | None = Field(default=None, gt=-273.15)
    ph: float | None = Field(default=None, ge=0, le=14)
    gas_volume_m3: float | None = Field(default=None, ge=0)
    methane_fraction: float | None = Field(default=None, ge=0, le=1)
    measurement_method: str | None = Field(default=None, max_length=1000)
    gas_volume_basis: str | None = Field(default=None, max_length=1000)
    quantitative_method_confirmed: bool = False
    gas_volume_kind: Literal['cumulative', 'interval'] = 'cumulative'
    methane_fraction_basis: Literal['volume_weighted', 'instantaneous', 'unknown'] = 'unknown'
    notes: str | None = Field(default=None, max_length=5000)

    @model_validator(mode='after')
    def actual_measurement(self):
        if all(getattr(self, field) is None for field in ['temperature_c', 'ph', 'gas_volume_m3', 'methane_fraction']):
            raise ValueError('At least one measured temperature, pH, gas volume or methane fraction is required')
        if self.observed_at is not None and self.observed_at.tzinfo is None:
            raise ValueError('observed_at must include its UTC offset')
        if self.quantitative_method_confirmed:
            validate_quantitative_method(self.measurement_method)
        return self


class ExperimentInput(Strict):
    name: str = Field(min_length=1, max_length=200)
    experiment_date: date | None = None
    material: str | None = Field(default=None, max_length=200)
    origin: Literal['user', 'laboratory'] = 'user'
    source_reference: str | None = Field(default=None, max_length=2000)
    mass_kg: float | None = Field(default=None, gt=0)
    volume_l: float | None = Field(default=None, gt=0)
    temperature_c: float | None = Field(default=None, gt=-273.15)
    ph: float | None = Field(default=None, ge=0, le=14)
    ts_percent: float | None = Field(default=None, ge=0, le=100)
    vs_percent: float | None = Field(default=None, ge=0, le=100)
    vs_basis: Literal['TS', 'fresh_mass'] | None = None
    vs_mass_kg: float | None = Field(default=None, gt=0)
    duration_days: float | None = Field(default=None, ge=0)
    gas_volume_m3: float | None = Field(default=None, ge=0)
    methane_fraction: float | None = Field(default=None, ge=0, le=1)
    measurement_method: str | None = Field(default=None, max_length=1000)
    gas_volume_basis: str | None = Field(default=None, max_length=1000)
    quantitative_method_confirmed: bool = False
    gas_volume_kind: Literal['cumulative', 'interval'] = 'cumulative'
    methane_fraction_basis: Literal['volume_weighted', 'instantaneous', 'unknown'] = 'unknown'
    model: Literal['stage1', 'stage1_5'] = 'stage1_5'
    prediction_context: dict[str, Annotated[float, Field(strict=True)]] = Field(default_factory=dict)
    prediction_gas_volume_basis: str | None = Field(default=None, max_length=1000)
    gas_basis_comparison_confirmed: bool = False
    gas_basis_evidence: str | None = Field(default=None, max_length=2000)
    notes: str | None = Field(default=None, max_length=5000)

    @model_validator(mode='after')
    def scientific_consistency(self):
        if not self.name.strip():
            raise ValueError('Experiment name must not be blank')
        if self.vs_mass_kg is not None and self.mass_kg is not None and self.vs_mass_kg > self.mass_kg:
            raise ValueError('VS mass cannot exceed wet mass')
        if self.vs_basis == 'fresh_mass' and self.ts_percent is not None and self.vs_percent is not None and self.vs_percent > self.ts_percent:
            raise ValueError('VS percentage of wet mass cannot exceed TS percentage')
        allowed = {'c_vs_sub_m', 'c_vs_sub_f', 'c_vs_inoc', 'ISR'}
        if set(self.prediction_context) - allowed:
            raise ValueError('Only preserved BMP model features are accepted in prediction_context')
        for key, value in self.prediction_context.items():
            if key == 'ISR' and value <= 0 or key != 'ISR' and not 0 <= value <= 1:
                raise ValueError('Invalid BMP diagnostic feature range')
        if self.quantitative_method_confirmed:
            validate_quantitative_method(self.measurement_method)
        return self


class ExperimentPatch(Strict):
    # A patch is validated as a full ExperimentInput after merging. Origin is immutable.
    name: str | None = Field(default=None, min_length=1, max_length=200)
    experiment_date: date | None = None
    material: str | None = Field(default=None, max_length=200)
    source_reference: str | None = Field(default=None, max_length=2000)
    mass_kg: float | None = Field(default=None, gt=0)
    volume_l: float | None = Field(default=None, gt=0)
    temperature_c: float | None = Field(default=None, gt=-273.15)
    ph: float | None = Field(default=None, ge=0, le=14)
    ts_percent: float | None = Field(default=None, ge=0, le=100)
    vs_percent: float | None = Field(default=None, ge=0, le=100)
    vs_basis: Literal['TS', 'fresh_mass'] | None = None
    vs_mass_kg: float | None = Field(default=None, gt=0)
    duration_days: float | None = Field(default=None, ge=0)
    gas_volume_m3: float | None = Field(default=None, ge=0)
    methane_fraction: float | None = Field(default=None, ge=0, le=1)
    measurement_method: str | None = Field(default=None, max_length=1000)
    gas_volume_basis: str | None = Field(default=None, max_length=1000)
    quantitative_method_confirmed: bool | None = None
    gas_volume_kind: Literal['cumulative', 'interval'] | None = None
    methane_fraction_basis: Literal['volume_weighted', 'instantaneous', 'unknown'] | None = None
    model: Literal['stage1', 'stage1_5'] | None = None
    prediction_context: dict[str, Annotated[float, Field(strict=True)]] | None = None
    prediction_gas_volume_basis: str | None = Field(default=None, max_length=1000)
    gas_basis_comparison_confirmed: bool | None = None
    gas_basis_evidence: str | None = Field(default=None, max_length=2000)
    notes: str | None = Field(default=None, max_length=5000)


def model_snapshot(data):
    from src.agent.tools import get_model_info, predict_tool
    info = get_model_info(data.model)
    prediction = predict_tool({'model': data.model, 'material': data.material, **data.prediction_context})
    return {'artifact': data.model, 'version': info['version'], 'algorithm': info['algorithm'],
            'recorded_at': utcnow().isoformat(), 'prediction': prediction,
            'reference_gas_volume_basis': data.prediction_gas_volume_basis,
            'reference_basis_provenance': 'operator_assertion_not_independently_verified',
            'limitations': info['limitations'], 'auto_training_enabled': False}


def _measurement_values(data):
    fields = set(MeasurementInput.model_fields) - {'observed_at', 'elapsed_days'}
    return {key: getattr(data, key) for key in fields if hasattr(data, key)}


def create_experiment(store, data):
    identifier = uuid.uuid4().hex
    created = utcnow().isoformat()
    snapshot = model_snapshot(data)
    with store.connect() as con:
        con.execute('INSERT INTO experiment_records VALUES(?,?,?)', (identifier, created, data.origin))
        revision = con.execute('INSERT INTO experiment_revisions(experiment_id,recorded_at,data_json,model_snapshot_json) VALUES(?,?,?,?)',
                    (identifier, created, encode(data.model_dump(mode='json')), encode(snapshot))).lastrowid
        # Initial gas measurements are explicit records, not fabricated chart points.
        if data.gas_volume_m3 is not None or data.methane_fraction is not None:
            values = MeasurementInput(**_measurement_values(data)).model_dump(mode='json')
            values['observed_at'] = created
            con.execute('INSERT INTO experiment_measurements VALUES(?,?,?,?,?,?)',
                (uuid.uuid4().hex, identifier, created, created, encode(values), revision))
    return get_experiment(store, identifier)


def get_experiment(store, identifier, include_measurements=True):
    with store.connect() as con:
        row = con.execute('''SELECT h.id,h.created_at,h.origin,r.id AS revision,r.recorded_at,r.data_json,r.model_snapshot_json,r.archived
            FROM experiment_records h JOIN experiment_revisions r ON r.experiment_id=h.id
            WHERE h.id=? ORDER BY r.id DESC LIMIT 1''', (identifier,)).fetchone()
    if row is None:
        raise LookupError('Experiment not found')
    result = {**json.loads(row['data_json']), 'id': row['id'], 'created_at': row['created_at'],
        'origin': row['origin'], 'updated_at': row['recorded_at'], 'revision': row['revision'],
        'archived': bool(row['archived']), 'model_snapshot': json.loads(row['model_snapshot_json']),
        'auto_training_enabled': False}
    if include_measurements:
        result['measurements'] = measurements(store, identifier)
        with store.connect() as con:
            result['measurement_count'] = con.execute('SELECT COUNT(*) FROM experiment_measurements WHERE experiment_id=?', (identifier,)).fetchone()[0]
        result['measurements_truncated'] = result['measurement_count'] > len(result['measurements'])
    return result


def list_experiments(store, origin=None, include_archived=False, limit=100):
    query = '''SELECT h.id FROM experiment_records h JOIN experiment_revisions r ON r.id=(
        SELECT MAX(x.id) FROM experiment_revisions x WHERE x.experiment_id=h.id)'''
    clauses = []
    args = []
    if origin is not None:
        clauses.append('h.origin=?'); args.append(origin)
    if not include_archived:
        clauses.append('r.archived=0')
    if clauses:
        query += ' WHERE ' + ' AND '.join(clauses)
    query += ' ORDER BY h.created_at DESC,h.id LIMIT ?'; args.append(limit)
    with store.connect() as con:
        ids = [row['id'] for row in con.execute(query, args)]
    return [get_experiment(store, identifier, include_measurements=False) for identifier in ids]


def update_experiment(store, identifier, patch):
    current = get_experiment(store, identifier, include_measurements=False)
    if current['archived']:
        raise ValueError('Archived experiments cannot be changed')
    data = {key: current[key] for key in ExperimentInput.model_fields}
    changes = patch.model_dump(mode='json', exclude_unset=True)
    if not changes:
        raise ValueError('Patch must contain at least one field')
    data.update(changes)
    parsed = ExperimentInput.model_validate(data)
    snapshot = model_snapshot(parsed)
    now = utcnow().isoformat()
    with store.connect() as con:
        revision = con.execute('INSERT INTO experiment_revisions(experiment_id,recorded_at,data_json,model_snapshot_json) VALUES(?,?,?,?)',
                    (identifier, now, encode(parsed.model_dump(mode='json')), encode(snapshot))).lastrowid
        if set(changes) & {'gas_volume_m3', 'methane_fraction'} and (parsed.gas_volume_m3 is not None or parsed.methane_fraction is not None):
            values = MeasurementInput(**_measurement_values(parsed)).model_dump(mode='json')
            values['observed_at'] = now
            con.execute('INSERT INTO experiment_measurements VALUES(?,?,?,?,?,?)',
                (uuid.uuid4().hex, identifier, now, now, encode(values), revision))
    return get_experiment(store, identifier)


def archive_experiment(store, identifier):
    current = get_experiment(store, identifier, include_measurements=False)
    if not current['archived']:
        data = {key: current[key] for key in ExperimentInput.model_fields}
        with store.connect() as con:
            con.execute('INSERT INTO experiment_revisions(experiment_id,recorded_at,data_json,model_snapshot_json,archived) VALUES(?,?,?,?,1)',
                (identifier, utcnow().isoformat(), encode(data), encode(current['model_snapshot'])))
    return get_experiment(store, identifier)


def revisions(store, identifier):
    get_experiment(store, identifier, include_measurements=False)
    with store.connect() as con:
        rows = con.execute('SELECT * FROM experiment_revisions WHERE experiment_id=? ORDER BY id', (identifier,)).fetchall()
    return [{'revision': row['id'], 'recorded_at': row['recorded_at'], 'archived': bool(row['archived']),
             'data': json.loads(row['data_json']), 'model_snapshot': json.loads(row['model_snapshot_json'])} for row in rows]


def add_measurement(store, identifier, data):
    experiment = get_experiment(store, identifier, include_measurements=False)
    if experiment['archived']:
        raise ValueError('Archived experiments cannot receive measurements')
    now = utcnow().isoformat(); measurement_id = uuid.uuid4().hex
    values = data.model_dump(mode='json')
    observed = data.observed_at.isoformat() if data.observed_at else now
    values['observed_at'] = observed
    with store.connect() as con:
        con.execute('INSERT INTO experiment_measurements VALUES(?,?,?,?,?,?)',
                    (measurement_id, identifier, now, observed, encode(values), experiment['revision']))
    return {**values, 'id': measurement_id, 'experiment_id': identifier, 'recorded_at': now,
            'origin': experiment['origin'], 'experiment_revision': experiment['revision']}


def measurements(store, identifier, limit=5000):
    with store.connect() as con:
        header = con.execute('SELECT origin FROM experiment_records WHERE id=?', (identifier,)).fetchone()
        if header is None:
            raise LookupError('Experiment not found')
        query = 'SELECT * FROM experiment_measurements WHERE experiment_id=? ORDER BY julianday(observed_at) DESC,recorded_at DESC,id DESC'
        if limit is None:
            rows = con.execute(query, (identifier,)).fetchall()
        else:
            rows = con.execute(query + ' LIMIT ?', (identifier, limit)).fetchall()
        rows = list(reversed(rows))
    return [{**json.loads(row['data_json']), 'id': row['id'], 'experiment_id': identifier,
             'recorded_at': row['recorded_at'], 'origin': header['origin'],
             'experiment_revision': row['experiment_revision']} for row in rows]


def comparison(store, identifier):
    experiment = get_experiment(store, identifier)
    snapshot = experiment['model_snapshot']; prediction = snapshot['prediction']
    result = {'status': 'INSUFFICIENT_DATA', 'reasons': [], 'model_snapshot': snapshot,
        'measured_methane_m3': None, 'measured_specific_yield_ml_ch4_g_vs': None,
        'predicted_bmp_ml_ch4_g_vs': prediction.get('bmp') if prediction.get('status') == 'ok' else None,
        'relative_difference_percent': None, 'uncertainty_status': 'not_quantified',
        'notice': 'Observed yield is not automatically a completed laboratory BMP. No automatic retraining.'}
    points = experiment['measurements']
    gas_points = [point for point in points if point.get('gas_volume_m3') is not None]
    if not gas_points:
        result['reasons'].append('No measured gas volume'); return result
    latest = gas_points[-1]
    if latest.get('experiment_revision') is None:
        result['reasons'].append('Historical measurement has no associated input/model revision'); return result
    revision = next(row for row in revisions(store, identifier) if row['revision'] == latest['experiment_revision'])
    experiment = {**revision['data'], 'model_snapshot': revision['model_snapshot']}
    snapshot = revision['model_snapshot']; prediction = snapshot['prediction']
    result['model_snapshot'] = snapshot
    result['predicted_bmp_ml_ch4_g_vs'] = prediction.get('bmp') if prediction.get('status') == 'ok' else None
    result['comparison_revision'] = revision['revision']
    result['current_revision'] = get_experiment(store, identifier, include_measurements=False)['revision']
    result['uses_historical_revision'] = result['comparison_revision'] != result['current_revision']
    if latest.get('methane_fraction') is None:
        result['reasons'].append('Biogas volume is not methane volume; a measured CH4 fraction is missing')
    if not latest.get('quantitative_method_confirmed') or not latest.get('measurement_method'):
        result['reasons'].append('Quantitative calibrated measurement method is not confirmed')
    if latest.get('methane_fraction_basis') != 'volume_weighted':
        result['reasons'].append('An instantaneous methane fraction cannot normalize an entire accumulated gas volume')
    if not latest.get('gas_volume_basis'):
        result['reasons'].append('Measured gas reference conditions are unknown')
    if result['reasons']:
        return result
    methane = latest['gas_volume_m3'] * latest['methane_fraction']
    result['measured_methane_m3'] = methane
    result['measurement_scope'] = latest.get('gas_volume_kind')
    if latest.get('gas_volume_kind') != 'cumulative':
        result['reasons'].append('An interval measurement cannot be treated as cumulative batch yield'); return result
    vs_mass = experiment['vs_mass_kg']
    if vs_mass is None:
        result['reasons'].append('Measured VS mass is missing'); return result
    result['measured_specific_yield_ml_ch4_g_vs'] = methane * 1000 / vs_mass
    if prediction.get('status') != 'ok':
        result['reasons'].append('Preserved BMP model has no applicable prediction for these inputs'); return result
    if not experiment['gas_basis_comparison_confirmed'] or not experiment.get('gas_basis_evidence'):
        result['reasons'].append('Equivalence of measured and model gas reference conditions is not documented'); return result
    if not experiment['prediction_gas_volume_basis'] or latest['gas_volume_basis'].strip().casefold() != experiment['prediction_gas_volume_basis'].strip().casefold():
        result['reasons'].append('Measured and prediction gas volume bases differ or are unknown'); return result
    expected = result['predicted_bmp_ml_ch4_g_vs']
    if expected and expected > 0:
        result['relative_difference_percent'] = 100 * (result['measured_specific_yield_ml_ch4_g_vs'] - expected) / expected
    result['status'] = 'CONDITIONAL'
    result['reasons'].append('Comparison uses operator-confirmed gas conditions; this is not independent model validation')
    return result


def csv_export(store, identifier):
    experiment = get_experiment(store, identifier)
    fields = ['experiment_id', 'experiment_name', 'experiment_date', 'material', 'origin', 'experiment_revision', 'model_artifact', 'model_version', 'measurement_id',
              'observed_at', 'recorded_at', 'elapsed_days', 'temperature_c', 'ph', 'gas_volume_m3',
              'methane_fraction', 'gas_volume_kind', 'methane_fraction_basis', 'measurement_method',
              'quantitative_method_confirmed', 'gas_volume_basis', 'mass_kg', 'volume_l', 'vs_mass_kg',
              'ts_percent', 'vs_percent', 'vs_basis', 'duration_days', 'experiment_temperature_c', 'experiment_ph',
              'prediction_gas_volume_basis', 'gas_basis_evidence', 'notes']
    stream = io.StringIO(newline=''); writer = csv.DictWriter(stream, fieldnames=fields)
    writer.writeheader()
    def safe(value):
        # Protect spreadsheet consumers without changing values stored in SQLite.
        if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@', '\t', '\r', '\n')):
            return "'" + value
        return value
    revision_map = {r['revision']: r for r in revisions(store, identifier)}
    for point in measurements(store, identifier, limit=None) or [{}]:
        linked = revision_map.get(point.get('experiment_revision'))
        data = linked['data'] if linked else experiment
        snapshot = linked['model_snapshot'] if linked else experiment['model_snapshot']
        row = {**point, 'experiment_id': identifier, 'experiment_name': experiment['name'],
            'experiment_date': data['experiment_date'], 'material': data['material'],
            'origin': experiment['origin'], 'model_artifact': snapshot['artifact'],
            'model_version': snapshot['version'], 'measurement_id': point.get('id'),
            **{key: data[key] for key in ['mass_kg', 'volume_l', 'vs_mass_kg', 'ts_percent', 'vs_percent', 'vs_basis',
                                         'duration_days', 'prediction_gas_volume_basis', 'gas_basis_evidence']},
            'experiment_temperature_c': data['temperature_c'], 'experiment_ph': data['ph']}
        writer.writerow({key: safe(row.get(key)) for key in fields})
    return stream.getvalue()
