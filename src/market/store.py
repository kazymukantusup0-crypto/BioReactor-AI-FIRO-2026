"""SQLite WAL, append-only prices/scenarios, atomic imports and cross-process leases."""
from contextlib import contextmanager
from datetime import datetime,timezone,timedelta
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import uuid
from src.data.prepare import ROOT
from src.market.domain import COMMODITIES, PriceInput, SourceInput, normalize_price,utcnow,market_today


def default_db():
    return Path(os.getenv('BIOREACTOR_MARKET_DB',str(ROOT/'data/market/market.sqlite3')))


class Store:
    def __init__(self,path=None):
        self.path=Path(path or default_db())
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as con:
            con.executescript('''
            CREATE TABLE IF NOT EXISTS sources(id TEXT PRIMARY KEY,name TEXT NOT NULL,url TEXT NOT NULL,category TEXT NOT NULL,adapter TEXT NOT NULL,enabled INTEGER NOT NULL,config TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS categories(id TEXT PRIMARY KEY);
            CREATE TABLE IF NOT EXISTS commodities(id TEXT PRIMARY KEY,category TEXT NOT NULL REFERENCES categories(id),unit TEXT NOT NULL,name TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS regions(id TEXT PRIMARY KEY,country TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS observations(id INTEGER PRIMARY KEY AUTOINCREMENT,source_id TEXT NOT NULL REFERENCES sources(id),commodity TEXT NOT NULL REFERENCES commodities(id),region TEXT NOT NULL REFERENCES regions(id),country TEXT NOT NULL,value TEXT NOT NULL,currency TEXT NOT NULL,unit TEXT NOT NULL,normalized_value TEXT NOT NULL,normalized_unit TEXT NOT NULL,published_at TEXT,effective_from TEXT NOT NULL,valid_to TEXT,received_at TEXT NOT NULL,price_type TEXT NOT NULL,reliability TEXT NOT NULL,consumer_class TEXT NOT NULL,tax_basis TEXT NOT NULL,gas_volume_basis TEXT,source_url TEXT NOT NULL,evidence TEXT NOT NULL,is_test INTEGER NOT NULL,fingerprint TEXT NOT NULL UNIQUE);
            CREATE INDEX IF NOT EXISTS ix_prices ON observations(commodity,region,effective_from);
            CREATE TABLE IF NOT EXISTS updates(id INTEGER PRIMARY KEY AUTOINCREMENT,source_id TEXT,category TEXT NOT NULL,started_at TEXT NOT NULL,finished_at TEXT,status TEXT NOT NULL,inserted INTEGER NOT NULL DEFAULT 0,error TEXT);
            CREATE TABLE IF NOT EXISTS leases(category TEXT PRIMARY KEY,owner TEXT NOT NULL,expires_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS source_state(source_id TEXT PRIMARY KEY REFERENCES sources(id),last_attempt_at TEXT,last_success_at TEXT,last_status TEXT,consecutive_failures INTEGER NOT NULL DEFAULT 0,next_attempt_at TEXT,last_error TEXT);
            CREATE TABLE IF NOT EXISTS scenarios(id INTEGER PRIMARY KEY AUTOINCREMENT,created_at TEXT NOT NULL,input_json TEXT NOT NULL,result_json TEXT NOT NULL,is_test INTEGER NOT NULL);
            CREATE TRIGGER IF NOT EXISTS immutable_prices_update BEFORE UPDATE ON observations BEGIN SELECT RAISE(ABORT,'Observations are append-only'); END;
            CREATE TRIGGER IF NOT EXISTS immutable_prices_delete BEFORE DELETE ON observations BEGIN SELECT RAISE(ABORT,'Observations are append-only'); END;
            CREATE TRIGGER IF NOT EXISTS immutable_scenarios_update BEFORE UPDATE ON scenarios BEGIN SELECT RAISE(ABORT,'Scenarios are append-only'); END;
            CREATE TRIGGER IF NOT EXISTS immutable_scenarios_delete BEFORE DELETE ON scenarios BEGIN SELECT RAISE(ABORT,'Scenarios are append-only'); END;
            ''')
            columns={row['name'] for row in con.execute('PRAGMA table_info(observations)')}
            for name,kind in [('acquisition_method',"TEXT NOT NULL DEFAULT 'legacy_unspecified'"),('period_start','TEXT'),('period_end','TEXT')]:
                if name not in columns:con.execute(f'ALTER TABLE observations ADD COLUMN {name} {kind}')
            for key,(category,unit,name) in COMMODITIES.items():
                con.execute('INSERT OR IGNORE INTO categories VALUES(?)',(category,))
                con.execute('INSERT OR IGNORE INTO commodities VALUES(?,?,?,?)',(key,category,unit,name))

    @contextmanager
    def connect(self):
        con=sqlite3.connect(self.path,timeout=15)
        con.row_factory=sqlite3.Row
        con.execute('PRAGMA foreign_keys=ON')
        con.execute('PRAGMA journal_mode=WAL')
        try:
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally: con.close()

    def add_source(self,source):
        s=source if isinstance(source,SourceInput) else SourceInput.model_validate(source)
        with self.connect() as con:
            con.execute('INSERT INTO sources VALUES(?,?,?,?,?,?,?)',(s.id,s.name,s.url,s.category,s.adapter,int(s.enabled),json.dumps(s.config)))
        return s.model_dump()

    def sources(self):
        with self.connect() as con: rows=[dict(r) for r in con.execute('SELECT * FROM sources ORDER BY id')]
        for row in rows: row['config']=json.loads(row['config'])
        return rows

    def import_prices(self,prices):
        # Validate entire batch before inserting anything; no partial bad CSV imports.
        parsed=[p if isinstance(p,PriceInput) else PriceInput.model_validate(p) for p in prices]
        ids=[]
        inserted=0
        with self.connect() as con:
            for p in parsed:
                source=con.execute('SELECT category FROM sources WHERE id=?',(p.source_id,)).fetchone()
                if source is None or source['category']!=COMMODITIES[p.commodity][0]: raise ValueError('Missing source or wrong source category')
                con.execute('INSERT OR IGNORE INTO regions VALUES(?,?)',(p.region,p.country))
                if con.execute('SELECT country FROM regions WHERE id=?',(p.region,)).fetchone()['country']!=p.country: raise ValueError('Region country mismatch')
                d=p.model_dump(mode='json')
                d['normalized_value'],d['normalized_unit']=normalize_price(p.value,p.unit,p.commodity)
                d['value']=format(p.value.normalize(),'f')
                # Evidence text/receipt changes alone must not create fake price changes.
                fingerprint={k:v for k,v in d.items() if k not in {'evidence','source_url','value','unit','acquisition_method'} and not (k in {'period_start','period_end'} and v is None)}
                d['fingerprint']=hashlib.sha256(json.dumps(fingerprint,sort_keys=True).encode()).hexdigest()
                d['received_at']=utcnow().isoformat()
                columns=list(d)
                cur=con.execute(f"INSERT OR IGNORE INTO observations({','.join(columns)}) VALUES({','.join('?' for _ in columns)})",[d[k] for k in columns])
                inserted+=cur.rowcount
                ids.append(con.execute('SELECT id FROM observations WHERE fingerprint=?',(d['fingerprint'],)).fetchone()['id'])
        return {'inserted':inserted,'duplicates':len(parsed)-inserted,'ids':ids}

    def prices(self,commodity=None,region=None,start=None,end=None,include_test=False,max_age_days=30,now=None,latest=False):
        now=now or utcnow()
        if now.tzinfo is None: raise ValueError('Timezone-aware now required')
        today=market_today(now)
        if max_age_days<0: raise ValueError('max_age_days must be nonnegative')
        conditions=['1=1']; args=[]
        for key,value,operator in [('commodity',commodity,'='),('region',region,'='),('effective_from',start,'>='),('effective_from',end,'<=')]:
            if value is not None: conditions.append(f'o.{key}{operator}?');args.append(value)
        if not include_test: conditions.append('o.is_test=0')
        if latest: conditions.append('o.effective_from<=?');args.append(today.isoformat())
        sql='SELECT o.*,c.category,s.name AS source_name,ss.last_status AS source_last_status,ss.last_success_at AS source_last_success_at,ss.last_attempt_at AS source_last_attempt_at,ss.last_error AS source_last_error FROM observations o JOIN commodities c ON c.id=o.commodity JOIN sources s ON s.id=o.source_id LEFT JOIN source_state ss ON ss.source_id=o.source_id WHERE '+' AND '.join(conditions)+' ORDER BY o.effective_from DESC,o.id DESC'
        series_keys=['source_id','commodity','region','currency','normalized_unit','consumer_class','tax_basis','price_type','gas_volume_basis','is_test']
        with self.connect() as con:
            rows=[dict(r) for r in con.execute(sql,args)]
            active=con.execute('SELECT * FROM observations WHERE effective_from<=? ORDER BY effective_from DESC,id DESC',(today.isoformat(),)).fetchall()
        latest_ids={}
        for row in active:latest_ids.setdefault(tuple(row[k] for k in series_keys),row['id'])
        seen=set();result=[]
        for row in rows:
            group=tuple(row[k] for k in series_keys)
            if latest and group in seen: continue
            seen.add(group)
            # An old tariff fetched today is still an old tariff; unknown publication
            # is explicitly disclosed. Use effective_from as conservative age basis.
            anchor=min(filter(None,[row['published_at'],row['effective_from']]))
            age=(today-datetime.fromisoformat(anchor).date()).days
            superseded=group in latest_ids and latest_ids[group]!=row['id'] and row['effective_from']<=today.isoformat()
            row.update(age_days=age,publication_date_unknown=row['published_at'] is None,is_superseded=superseded,
                receipt_age_seconds=max(0,(now-datetime.fromisoformat(row['received_at'])).total_seconds()),
                is_stale=superseded or age>max_age_days or (row['valid_to'] is not None and row['valid_to']<today.isoformat()),
                is_future=row['effective_from']>today.isoformat())
            from src.market.validation import classify,VERIFIED_CURRENT
            row['validation_status'],row['validation_reason']=classify(row)
            if row['source_last_status']=='error':row['is_stale']=True
            row['usable_as_current']=row['validation_status']==VERIFIED_CURRENT
            result.append(row)
        return result

    def observation(self,identifier,max_age_days=30):
        # The same age/reliability computation is used for explicit price selection.
        return next((p for p in self.prices(include_test=True,max_age_days=max_age_days) if p['id']==identifier),None)

    def acquire(self,category,ttl=300):
        owner=uuid.uuid4().hex;now=utcnow()
        with self.connect() as con:
            cur=con.execute('INSERT INTO leases VALUES(?,?,?) ON CONFLICT(category) DO UPDATE SET owner=excluded.owner,expires_at=excluded.expires_at WHERE leases.expires_at<=?',
                (category,owner,(now+timedelta(seconds=ttl)).isoformat(),now.isoformat()))
        return owner if cur.rowcount else None

    def release(self,category,owner):
        with self.connect() as con: con.execute('DELETE FROM leases WHERE category=? AND owner=?',(category,owner))

    def renew(self,category,owner,ttl=300):
        with self.connect() as con:
            return con.execute('UPDATE leases SET expires_at=? WHERE category=? AND owner=?',((utcnow()+timedelta(seconds=ttl)).isoformat(),category,owner)).rowcount==1

    def log_start(self,source,category):
        with self.connect() as con: return con.execute('INSERT INTO updates(source_id,category,started_at,status) VALUES(?,?,?,?)',(source,category,utcnow().isoformat(),'running')).lastrowid

    def log_finish(self,identifier,status,inserted=0,error=None):
        with self.connect() as con: con.execute('UPDATE updates SET status=?,inserted=?,error=?,finished_at=? WHERE id=?',(status,inserted,error,utcnow().isoformat(),identifier))

    def updates(self):
        with self.connect() as con: return [dict(r) for r in con.execute('SELECT * FROM updates ORDER BY id DESC LIMIT 200')]

    def source_state(self,source_id):
        with self.connect() as con:
            row=con.execute('SELECT * FROM source_state WHERE source_id=?',(source_id,)).fetchone()
        return dict(row) if row else None

    def finish_source(self,source_id,success,interval=86400,error=None):
        now=utcnow();old=self.source_state(source_id) or {}
        failures=0 if success else old.get('consecutive_failures',0)+1
        # Three bounded retries (5,10,20 min), then at most once per day.
        delay=interval if success else min(interval,300*2**(failures-1)) if failures<=3 else max(interval,86400)
        last_success=now.isoformat() if success else old.get('last_success_at')
        with self.connect() as con:
            con.execute('INSERT INTO source_state VALUES(?,?,?,?,?,?,?) ON CONFLICT(source_id) DO UPDATE SET last_attempt_at=excluded.last_attempt_at,last_success_at=excluded.last_success_at,last_status=excluded.last_status,consecutive_failures=excluded.consecutive_failures,next_attempt_at=excluded.next_attempt_at,last_error=excluded.last_error',
                (source_id,now.isoformat(),last_success,'success' if success else 'error',failures,(now+timedelta(seconds=delay)).isoformat(),error))

    def source_states(self):
        with self.connect() as con:return [dict(r) for r in con.execute('SELECT * FROM source_state ORDER BY source_id')]

    def defer_manual(self,source_id,interval):
        now=utcnow()
        with self.connect() as con:
            con.execute("INSERT INTO source_state(source_id,last_attempt_at,last_status,next_attempt_at) VALUES(?,?,?,?) ON CONFLICT(source_id) DO UPDATE SET last_attempt_at=excluded.last_attempt_at,last_status=excluded.last_status,next_attempt_at=excluded.next_attempt_at",
                (source_id,now.isoformat(),'needs_configuration',(now+timedelta(seconds=interval)).isoformat()))

    def save_scenario(self,data,result):
        with self.connect() as con:
            return con.execute('INSERT INTO scenarios(created_at,input_json,result_json,is_test) VALUES(?,?,?,?)',
                (utcnow().isoformat(),json.dumps(data,ensure_ascii=False,allow_nan=False),json.dumps(result,ensure_ascii=False,allow_nan=False),int(data.get('allow_test_prices',False)))).lastrowid

    def scenarios(self,identifier=None):
        with self.connect() as con:
            rows=con.execute('SELECT * FROM scenarios WHERE id=?',(identifier,)).fetchall() if identifier else con.execute('SELECT * FROM scenarios ORDER BY id DESC LIMIT 100').fetchall()
        return [{**dict(r),'input_json':json.loads(r['input_json']),'result_json':json.loads(r['result_json'])} for r in rows]
