import main,hashlib,json,sqlite3
from contextlib import closing
from src.data.prepare import ROOT
out=ROOT/'reports/stage8_0';original=json.loads((out/'preserved_hashes.json').read_text(encoding='utf-8'))
files={key:(ROOT/key).is_file() and hashlib.sha256((ROOT/key).read_bytes()).hexdigest()==value for key,value in original.items()}
old=json.loads((out/'legacy_sqlite.json').read_text(encoding='utf-8'));tables={};counts={}
with closing(sqlite3.connect(ROOT/'data/market/market.sqlite3')) as db:
 db.row_factory=sqlite3.Row
 for table,rows in old.items():
  current=[dict(r) for r in db.execute('SELECT * FROM '+table)];counts[table]=len(current)
  keys={json.dumps(r,sort_keys=True,ensure_ascii=False) for r in current}
  tables[table]={'baseline_rows':len(rows),'current_rows':len(current),'all_old_rows_unchanged':all(json.dumps(r,sort_keys=True,ensure_ascii=False) in keys for r in rows)}
 leases=[dict(row) for row in db.execute("SELECT * FROM leases WHERE julianday(expires_at)>julianday('now')")]
report={'protected_file_count':len(files),'all_protected_files_unchanged':all(files.values()),'changed_or_missing':[p for p,ok in files.items() if not ok],'tables':tables,'active_leases':leases}
(out/'preservation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2));assert report['all_protected_files_unchanged'];assert all(t['all_old_rows_unchanged'] for t in tables.values())
