"""Additive append-only evidence, offers, runs and fetch logs in the existing SQLite."""
import hashlib
import json
from src.market.domain import utcnow

class EvidenceStore:
    def __init__(self,store):
        self.store=store
        with store.connect() as con:
            con.executescript('''
            CREATE TABLE IF NOT EXISTS research_records(id INTEGER PRIMARY KEY,kind TEXT NOT NULL,created_at TEXT NOT NULL,fingerprint TEXT NOT NULL UNIQUE,payload TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS ix_research_kind ON research_records(kind,id);
            CREATE TABLE IF NOT EXISTS research_fetches(id INTEGER PRIMARY KEY,url TEXT NOT NULL,attempted_at TEXT NOT NULL,status TEXT NOT NULL,detail TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS research_cache(key TEXT PRIMARY KEY,stored_at TEXT NOT NULL,payload TEXT NOT NULL);
            CREATE TRIGGER IF NOT EXISTS research_no_update BEFORE UPDATE ON research_records BEGIN SELECT RAISE(ABORT,'Research records are append-only'); END;
            CREATE TRIGGER IF NOT EXISTS research_no_delete BEFORE DELETE ON research_records BEGIN SELECT RAISE(ABORT,'Research records are append-only'); END;
            ''')

    def append(self,kind,payload):
        raw=json.dumps(payload,sort_keys=True,ensure_ascii=False,allow_nan=False)
        digest=hashlib.sha256((kind+raw).encode()).hexdigest()
        with self.store.connect() as con:
            con.execute('INSERT OR IGNORE INTO research_records(kind,created_at,fingerprint,payload) VALUES(?,?,?,?)',(kind,utcnow().isoformat(),digest,raw))
            return con.execute('SELECT id FROM research_records WHERE fingerprint=?',(digest,)).fetchone()[0]

    def records(self,kind,limit=100):
        with self.store.connect() as con:
            return [{'id':r['id'],'created_at':r['created_at'],**json.loads(r['payload'])} for r in con.execute('SELECT * FROM research_records WHERE kind=? ORDER BY id DESC LIMIT ?',(kind,limit))]

    def log(self,url,status,detail):
        with self.store.connect() as con:con.execute('INSERT INTO research_fetches(url,attempted_at,status,detail) VALUES(?,?,?,?)',(url,utcnow().isoformat(),status,str(detail)[:1000]))

    def logs(self):
        with self.store.connect() as con:return [dict(r) for r in con.execute('SELECT * FROM research_fetches ORDER BY id DESC LIMIT 100')]
