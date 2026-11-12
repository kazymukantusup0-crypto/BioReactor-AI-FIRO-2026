"""Offline validation only. This script never starts a server or model."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PATH=ROOT/'evaluations/qwen3_4b_compact_profile_20261111.json'
QUESTION='Чем BMP отличается от фактической выработки метана?'
PROBE='Русский; қазақша: ә ғ қ ң ө ұ ү һ і; 0,6 кг VS × 250 мл CH₄/г VS.'

def inspect():
    p=json.loads(PATH.read_text(encoding='utf-8'))
    assert p['model']=='qwen3:4b-q4_K_M'
    assert p['options']['num_ctx']==2048 and p['options']['num_batch']==16
    assert p['options']['num_gpu']==-1 and p['keep_alive']==0 and p['max_client_requests']==1
    assert p['qa_server_environment']['OLLAMA_NUM_PARALLEL']=='1'
    body={'model':p['model'],'messages':[{'role':'user','content':QUESTION}],'stream':True,
          'keep_alive':p['keep_alive'],'options':p['options'],'think':False}
    for value in (QUESTION,PROBE):
        raw=json.dumps({'message':value},ensure_ascii=False).encode('utf-8')
        assert json.loads(raw.decode('utf-8'))['message'].encode('utf-8')==value.encode('utf-8')
    a=p['admission'];missing=[k for k in ('model_peak_commit_bound_mib','model_peak_uncapped_ram_bound_mib',
        'driver_vram_reserve_bound_mib','os_reserve_mib','abort_latency_bound_seconds') if a.get(k) is None]
    if not a.get('runner_job_containment_verified'):missing.append('runner_job_containment_verified')
    # Deliberately no run/admit command: no real execution until these bounds are established.
    return {'status':'BLOCKED' if missing else 'REVIEW_REQUIRED','missing_evidence':missing,
        'unicode':'PASS','prompt_sha256':hashlib.sha256(QUESTION.encode('utf-8')).hexdigest(),
        'request_preview':body,'inference':'NOT RUN','telemetry':'NOT RUN'}

if __name__=='__main__':print(json.dumps(inspect(),ensure_ascii=False,indent=2))
