"""Run tests and real CLI subprocesses, retaining machine-readable evidence."""
from pathlib import Path
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
OUT = ROOT/'reports/stage1_5'


def run():
    OUT.mkdir(parents=True,exist_ok=True)
    test = subprocess.run([sys.executable,'-m','unittest','discover','-s',str(ROOT/'tests'),'-v'],
        cwd=ROOT.parent, capture_output=True,text=True,encoding='utf-8',errors='replace')
    (OUT/'tests.log').write_text(test.stdout+test.stderr,encoding='utf-8')
    checks=[]
    for model in ['stage1','stage1_5']:
        for example,success in [('wheat_straw.json',True),('stage1_5_measured.json',True),('incomplete.json',False)]:
            proc=subprocess.run([sys.executable,str(ROOT/'main.py'),'predict','--model',model,
                '--input',str(ROOT/'examples'/example)],capture_output=True,text=True,encoding='utf-8',errors='replace')
            result=json.loads(proc.stdout if success else proc.stderr)
            passed=proc.returncode==0 and 'bmp' in result if success else proc.returncode!=0 and 'Missing measured input features' in result.get('error','')
            checks.append({'model':model,'example':example,'returncode':proc.returncode,'passed':passed,'output':result})
    summary={'tests_returncode':test.returncode,'test_log':'tests.log','cli_checks':checks,
        'all_passed':test.returncode==0 and all(c['passed'] for c in checks)}
    (OUT/'verification.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(test.stdout+test.stderr)
    print('All verification passed:',summary['all_passed'])
    return 0 if summary['all_passed'] else 1


if __name__=='__main__':
    raise SystemExit(run())
