"""Additive v6 tables in the existing SQLite database, with immutable snapshots."""
import json
import uuid
from src.market.domain import utcnow


def initialize(store):
    with store.connect() as con:
        con.executescript('''
        CREATE TABLE IF NOT EXISTS process_optimizer_runs(
            id TEXT PRIMARY KEY, created_at TEXT NOT NULL,
            input_json TEXT NOT NULL, result_json TEXT NOT NULL, engine_version TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS experiment_records(
            id TEXT PRIMARY KEY, created_at TEXT NOT NULL, origin TEXT NOT NULL
            CHECK(origin IN ('user','laboratory')));
        CREATE TABLE IF NOT EXISTS experiment_revisions(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            experiment_id TEXT NOT NULL REFERENCES experiment_records(id),
            recorded_at TEXT NOT NULL, data_json TEXT NOT NULL, model_snapshot_json TEXT NOT NULL,
            archived INTEGER NOT NULL DEFAULT 0);
        CREATE INDEX IF NOT EXISTS ix_experiment_revision ON experiment_revisions(experiment_id,id);
        CREATE INDEX IF NOT EXISTS ix_experiment_origin ON experiment_records(origin,created_at);
        CREATE TABLE IF NOT EXISTS experiment_measurements(
            id TEXT PRIMARY KEY, experiment_id TEXT NOT NULL REFERENCES experiment_records(id),
            recorded_at TEXT NOT NULL, observed_at TEXT NOT NULL, data_json TEXT NOT NULL,
            experiment_revision INTEGER REFERENCES experiment_revisions(id));
        CREATE INDEX IF NOT EXISTS ix_experiment_measurements ON experiment_measurements(experiment_id,observed_at);
        CREATE TRIGGER IF NOT EXISTS immutable_optimizer_update BEFORE UPDATE ON process_optimizer_runs
            BEGIN SELECT RAISE(ABORT,'Optimizer runs are immutable'); END;
        CREATE TRIGGER IF NOT EXISTS immutable_optimizer_delete BEFORE DELETE ON process_optimizer_runs
            BEGIN SELECT RAISE(ABORT,'Optimizer runs are immutable'); END;
        CREATE TRIGGER IF NOT EXISTS immutable_experiment_header_update BEFORE UPDATE ON experiment_records
            BEGIN SELECT RAISE(ABORT,'Experiment origin is immutable'); END;
        CREATE TRIGGER IF NOT EXISTS immutable_experiment_header_delete BEFORE DELETE ON experiment_records
            BEGIN SELECT RAISE(ABORT,'Experiments are archived, not deleted'); END;
        CREATE TRIGGER IF NOT EXISTS immutable_revision_update BEFORE UPDATE ON experiment_revisions
            BEGIN SELECT RAISE(ABORT,'Experiment revisions are immutable'); END;
        CREATE TRIGGER IF NOT EXISTS immutable_revision_delete BEFORE DELETE ON experiment_revisions
            BEGIN SELECT RAISE(ABORT,'Experiment revisions are immutable'); END;
        CREATE TRIGGER IF NOT EXISTS immutable_measurement_update BEFORE UPDATE ON experiment_measurements
            BEGIN SELECT RAISE(ABORT,'Measurements are immutable'); END;
        CREATE TRIGGER IF NOT EXISTS immutable_measurement_delete BEFORE DELETE ON experiment_measurements
            BEGIN SELECT RAISE(ABORT,'Measurements are immutable'); END;
        ''')
        columns = {row['name'] for row in con.execute('PRAGMA table_info(experiment_measurements)')}
        if 'experiment_revision' not in columns:
            con.execute('ALTER TABLE experiment_measurements ADD COLUMN experiment_revision INTEGER REFERENCES experiment_revisions(id)')


def encode(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def save_run(store, request, result):
    initialize(store)
    identifier = uuid.uuid4().hex
    created = utcnow().isoformat()
    payload = request.model_dump(mode='json') if hasattr(request, 'model_dump') else request
    with store.connect() as con:
        con.execute('INSERT INTO process_optimizer_runs VALUES(?,?,?,?,?)',
                    (identifier, created, encode(payload), encode(result), '6'))
    return {**result, 'id': identifier, 'created_at': created, 'engine_version': '6'}


def get_run(store, identifier):
    with store.connect() as con:
        row = con.execute('SELECT * FROM process_optimizer_runs WHERE id=?', (identifier,)).fetchone()
    if row is None:
        raise LookupError('Saved optimization run not found')
    return {'id': row['id'], 'created_at': row['created_at'], 'engine_version': row['engine_version'],
            'input': json.loads(row['input_json']), 'result': json.loads(row['result_json'])}


def list_runs(store, limit=100):
    with store.connect() as con:
        rows = con.execute('SELECT id,created_at,input_json,result_json,engine_version FROM process_optimizer_runs ORDER BY created_at DESC,id LIMIT ?', (limit,)).fetchall()
    return [{'id': row['id'], 'created_at': row['created_at'], 'engine_version': row['engine_version'],
             'input': json.loads(row['input_json']), 'result': json.loads(row['result_json'])} for row in rows]
