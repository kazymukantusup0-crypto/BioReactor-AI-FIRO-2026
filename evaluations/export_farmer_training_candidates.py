"""Export trace-backed review candidates. Never train or certify a dataset."""
import argparse
import hashlib
import json
from pathlib import Path

def candidates(path):
    trace=json.loads(path.read_text(encoding='utf-8'))
    calls=trace.get('provider_calls',[])
    real=any(m.get('generation_received') is True for c in calls for m in c.get('metrics',[]))
    if not real:return []
    rows=[]
    for turn in trace.get('turns',[]):
        reply=turn.get('result',{}).get('reply',{})
        if not reply:continue
        meta=reply.get('technical_metadata',{});question=turn['request'];answer=reply['answer']
        rows.append({'id':hashlib.sha256((question+'\n'+answer).encode()).hexdigest(),
            'origin':'REAL_MODEL_EXECUTION','question_origin':'USER_PROVIDED_ACCEPTANCE' if trace.get('farmer_case')=='pig' else 'AGENT_AUTHORED_VALIDATION_NOT_REAL_FARMER_TRAFFIC',
            'split':'development','model':next((c['model'] for c in calls if c.get('model')),None),
            'question':question,'answer':answer,'trace_path':str(path),'trace_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'tools':reply.get('tools',[]),'model_synthesis':meta.get('model_synthesis'),
            'automatic_verification':{k:meta.get(k) for k in ['verification','scientific_answer_verification','quantity_verification']},
            'final_author':meta.get('final_author'),'manual_review':'PENDING_INDEPENDENT_REVIEW',
            'eligible_for_training':False,'restrictions':['No blind holdout records','Need independent scientific/source review','Do not promote fallback to model-authored target','No training performed']})
    return rows

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('traces',nargs='+',type=Path);parser.add_argument('--output',type=Path,default=Path('datasets/farmer_consultant/candidates.jsonl'));args=parser.parse_args()
    rows={row['id']:row for path in args.traces for row in candidates(path)}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows.values()),encoding='utf-8')
    print(json.dumps({'candidates':len(rows),'trainable':0,'output':str(args.output)}))

if __name__=='__main__':main()
