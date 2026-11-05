import json
from datetime import datetime
from src.market.domain import utcnow

class ResearchCache:
    def __init__(self,evidence):self.evidence=evidence
    def get(self,key,ttl_hours=24):
        with self.evidence.store.connect() as con:row=con.execute('SELECT * FROM research_cache WHERE key=?',(key,)).fetchone()
        if row is None:return None
        age=max(0,(utcnow()-datetime.fromisoformat(row['stored_at'])).total_seconds())
        return {'data':json.loads(row['payload']),'age_hours':age/3600,'stale':age>ttl_hours*3600,'stored_at':row['stored_at']}
    def put(self,key,payload):
        with self.evidence.store.connect() as con:con.execute('INSERT INTO research_cache VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET stored_at=excluded.stored_at,payload=excluded.payload',(key,utcnow().isoformat(),json.dumps(payload,ensure_ascii=False,allow_nan=False)))
