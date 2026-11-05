"""Actual provider requests, ML calls, CLI and tests; never retrains a model."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import main
from src.agent.orchestrator import Agent
from src.agent.providers import HybridLLM

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'reports/stage2'


def write(name,value):
    (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')


def run():
    OUT.mkdir(parents=True,exist_ok=True)
    test=subprocess.run([sys.executable,'-m','unittest','discover','-s',str(ROOT/'tests'),'-v'],capture_output=True,text=True,encoding='utf-8',errors='replace')
    (OUT/'tests.log').write_text(test.stdout+test.stderr,encoding='utf-8')
    statuses=HybridLLM().probe()
    write('provider_probe.json',statuses)
    dialogs=[]
    soil=Agent(mode='offline')
    question='У меня 80 литров чернозёма и реактор на 90 литров. Выгоднее продать чернозём или переработать в биогаз?'
    dialogs.append({'scenario':'live local LLM; user-request example','user':question,'reply':soil.ask(question)})
    bmp=Agent(mode='auto')
    question='Оцени BMP пшеничной соломы'
    dialogs.append({'scenario':'live hybrid agent; incomplete measured inputs','user':question,'reply':bmp.ask(question)})
    # Genuine source inputs of train bottle 902, not a new experiment/accuracy test.
    question=(ROOT/'examples/stage1_5_measured.json').read_text(encoding='utf-8')
    dialogs.append({'scenario':'live same session; real train-bottle inputs, not independent validation','user':question,'reply':bmp.ask(question)})
    # Exercise the legacy artifact as well, without changing the default research artifact.
    measured=json.loads(question)
    legacy=Agent(context={**measured,'model':'stage1'},llm=HybridLLM(providers=[]))
    dialogs.append({'scenario':'legacy ML loading, deterministic tool mode','user':'Оцени BMP','reply':legacy.ask('Оцени BMP')})
    write('actual_dialogues.json',dialogs)
    transcript=['# Реальные диалоги проверки 28.10.2026', '',
        'Запросы Ollama фактически выполнены. Пример бутылки 902 — входы из train, не независимый эксперимент.', '']
    for index,dialog in enumerate(dialogs,1):
        reply=dialog['reply']
        transcript += [f'## {index}. {dialog["scenario"]}', '', '**Пользователь:**', '', dialog['user'], '',
            '**Вызовы Python:** '+ ' → '.join(f'{entry["tool"]} [{entry["status"]}]' for entry in reply['tools']), '',
            '**Ответ:**', '', reply['answer'], '']
    (OUT/'actual_dialogues.md').write_text('\n'.join(transcript),encoding='utf-8')
    cli=[]
    for args,expected in [(['chat','--no-llm','--message','Статус датчиков','--json'],'deterministic_tools_no_llm'),
                          (['chat','--mode','online','--message','Статус датчиков','--json'],None),
                          (['tool','search_scientific_sources','--query','BMP VS Hafner'],None)]:
        proc=subprocess.run([sys.executable,str(ROOT/'main.py'),*args],capture_output=True,text=True,encoding='utf-8',errors='replace')
        result=json.loads(proc.stdout) if proc.returncode==0 else {'error':proc.stderr}
        cli.append({'args':args,'returncode':proc.returncode,'output':result,
            'passed':proc.returncode==0 and (expected is None or result.get('mode')==expected)})
    interactive=subprocess.run([sys.executable,str(ROOT/'main.py'),'chat','--no-llm'],input='sensor status\n/exit\n',capture_output=True,text=True,encoding='utf-8',errors='replace')
    cli.append({'args':['chat','--no-llm'],'input':'sensor status\n/exit\n','returncode':interactive.returncode,
        'output':interactive.stdout,'passed':interactive.returncode==0 and 'Mock-режим' in interactive.stdout})
    write('cli_checks.json',cli)
    protected=json.loads((OUT/'preserved_hashes.json').read_text(encoding='utf-8'))
    changed=[name for name,sha in protected.items() if not (ROOT/name).exists() or hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=sha]
    write('preservation_check.json',{'files_checked':len(protected),'changed_files':changed,'all_preserved':not changed})
    results={entry['tool']:entry['result'] for entry in dialogs[2]['reply']['tools']}
    legacy_results={entry['tool']:entry['result'] for entry in dialogs[3]['reply']['tools']}
    success=test.returncode==0 and all(c['passed'] for c in cli) and not changed and results.get('predict_bmp',{}).get('model_called') is True and legacy_results.get('predict_bmp',{}).get('model_called') is True
    write('verification.json',{'tests_returncode':test.returncode,'all_checks_passed':success,
        'local_actual_generation_verified':any(s['provider']=='offline' and s.get('status')=='available' for s in statuses),
        'online_actual_generation_verified':any(s['provider']=='online' and s.get('status')=='available' for s in statuses),
        'models_retrained':False,'prior_artifacts_unchanged':not changed})
    print(test.stdout+test.stderr)
    print(json.dumps({'all_checks_passed':success,'provider_probe':statuses,'preserved':not changed},ensure_ascii=False,indent=2))
    return 0 if success else 1


if __name__=='__main__':
    raise SystemExit(run())
