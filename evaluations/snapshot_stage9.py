"""Record reproducible source/model fingerprints without changing artifacts."""
import hashlib
import json
import sys
import urllib.request
import zipfile
from datetime import datetime,timezone
from pathlib import Path
from validate_stage9 import ROOT,source_hash

label=sys.argv[1] if len(sys.argv)>1 else 'rc2'
if not all(c.isalnum() or c in '_-' for c in label):raise ValueError('Invalid snapshot label')
out=ROOT/'reports/stage9';out.mkdir(exist_ok=True)
archive=out/(label+'_source.zip')
if archive.exists():raise FileExistsError('Snapshots are immutable')
paths=sorted((ROOT/'src').rglob('*.py'))+[ROOT/'main.py',ROOT/'evaluations/stage9_cases.json']
paths+=sorted((ROOT/'data/research').glob('*.json'))
with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED) as snapshot:
    for path in paths:snapshot.write(path,path.relative_to(ROOT))
models={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'models').rglob('*') if p.is_file() and p.suffix in {'.joblib','.json'}}
with urllib.request.urlopen('http://127.0.0.1:11434/api/tags',timeout=5) as response:tags=json.load(response)
meta={'created_at':datetime.now(timezone.utc).isoformat(),'source_sha256':source_hash(),'snapshot':archive.name,'model_artifact_sha256':models,
      'qwen':next((m for m in tags['models'] if m['name']=='qwen3:8b'),None),
      'validation_configuration':{'num_ctx':8192,'num_gpu':16,'think':False,'temperature':0,'agent_timeout_seconds':150,'job_timeout_seconds':180,'online_research':False},
      'note':'A source snapshot and configuration record, not evidence that generations succeeded.'}
(out/(label+'_snapshot.json')).write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'source_sha256':meta['source_sha256'],'model_artifacts':len(models),'snapshot':archive.name}))
