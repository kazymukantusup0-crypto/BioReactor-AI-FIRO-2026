"""Opt-in preloaded-model QA client. No model load or unload requests are made.

Ollama has no atomic 'execute only if already loaded' API: a model may be
unloaded between /api/ps and /api/chat. See the accompanying instructions.
"""
import argparse
import ctypes
import json
import math
import os
import subprocess
import sys
import threading
import time
import urllib.request
import uuid
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'evaluations'))
import qwen_offload_ab_harness as telemetry
from qwen3_4b_resource_policy import load_policy, reasons
from src.agent.providers import HybridLLM, JSONProvider, ProviderError
from src.agent.providers import request_json
from src.agent.cancellation import CancellationSignal
import psutil
from src.market.api import create_app
from src.market.store import Store
from fastapi.testclient import TestClient

MODEL = 'qwen3:4b-q4_K_M'
API = 'http://127.0.0.1:11434'
LOCK = threading.BoundedSemaphore(1)
CONTEXT = ('You are the BioReactor AI assistant for anaerobic digestion and biogas. '
           'In this domain an unqualified BMP means biochemical methane potential; '
           'respect an explicit question about the bitmap image format.')
KEEP_ALIVE = '5m'
MAX_MODEL_CALLS = 6

# Calibration-only engineering margins for this 16 GiB laptop, not proven
# Windows minima or production thresholds. The 2.5 GiB admission headroom is
# above twice the ~0.9 GiB observed drop in the earlier short 4B experiment.
CAL_RAM_FLOOR_MIB = 4096
CAL_ADMISSION_RAM_MIB = CAL_RAM_FLOOR_MIB + 2560
CAL_COMMIT_FLOOR_MIB = 4096
CAL_VRAM_FLOOR_MIB = 512
CAL_ADMISSION_VRAM_MIB = 4096
CAL_TIMEOUT_S = 60


class WindowsLowMemory:
    """Use the OS low-memory notification in addition to engineering margins."""
    def __init__(self):
        if os.name != 'nt': raise RuntimeError('Windows low-memory notification unavailable')
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.kernel.CreateMemoryResourceNotification.argtypes = [ctypes.c_int]
        self.kernel.CreateMemoryResourceNotification.restype = ctypes.c_void_p
        self.kernel.QueryMemoryResourceNotification.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int)]
        self.kernel.QueryMemoryResourceNotification.restype = ctypes.c_int
        self.kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        self.handle = self.kernel.CreateMemoryResourceNotification(0)
        if not self.handle: raise ctypes.WinError(ctypes.get_last_error())

    def low(self):
        value = ctypes.c_int()
        if not self.kernel.QueryMemoryResourceNotification(self.handle, ctypes.byref(value)):
            raise ctypes.WinError(ctypes.get_last_error())
        return bool(value.value)

    def close(self):
        self.kernel.CloseHandle(self.handle)


def calibration_issues(row, low_memory, admission=False):
    issues = []
    if any(k in row for k in ('gpu_error','free_ram_error','commit_error','api_error','process_error')):
        issues.append('telemetry_error')
    gpu = row.get('gpu') or {}; commit = row.get('commit') or {}
    required = (row.get('free_ram_mib'), commit.get('commit_headroom_mib'),
                gpu.get('temperature_c'), gpu.get('vram_total_mib'), gpu.get('vram_used_mib'))
    if not all(isinstance(v, (int,float)) and not isinstance(v, bool) and math.isfinite(v) and v >= 0 for v in required):
        issues.append('telemetry_incomplete')
        return issues
    if not isinstance(row.get('api_version'),dict) or not isinstance(row.get('running_models'),list):
        issues.append('ollama_telemetry_incomplete')
    if low_memory is not False: issues.append('windows_low_memory_or_unknown')
    if row['free_ram_mib'] < (CAL_ADMISSION_RAM_MIB if admission else CAL_RAM_FLOOR_MIB): issues.append('ram_limit')
    if commit['commit_headroom_mib'] < CAL_COMMIT_FLOOR_MIB: issues.append('commit_limit')
    free_vram = gpu['vram_total_mib'] - gpu['vram_used_mib']
    if free_vram < (CAL_ADMISSION_VRAM_MIB if admission else CAL_VRAM_FLOOR_MIB): issues.append('vram_limit')
    if gpu['temperature_c'] >= telemetry.GPU_STOP_C: issues.append('gpu_temperature_limit')
    if gpu.get('hw_thermal_slowdown') != 'Not Active' or gpu.get('sw_thermal_slowdown') != 'Not Active':
        issues.append('thermal_slowdown_or_unknown')
    if admission and row.get('running_models'): issues.append('model_already_loaded')
    if not admission and any(m.get('name') != MODEL and m.get('model') != MODEL for m in row.get('running_models',[]) if isinstance(m,dict)):
        issues.append('unexpected_model_loaded')
    return issues


def active_ollama_connections():
    rows = psutil.net_connections(kind='tcp')
    return [{'pid': c.pid, 'local':str(c.laddr), 'remote':str(c.raddr)} for c in rows
            if c.status == 'ESTABLISHED' and ((c.laddr and c.laddr.port == 11434) or (c.raddr and c.raddr.port == 11434))]


def unload_target_if_uncontended(timeout=15):
    """Stop only the selected model when no other visible local client is active."""
    started=time.monotonic()
    try:
        connections=psutil.net_connections(kind='tcp')
        external=[c for c in connections if c.status=='ESTABLISHED' and c.raddr and c.raddr.port==11434
                  and c.laddr and c.laddr.port!=11434 and c.pid!=os.getpid()]
        if external:
            return {'status':'BLOCKED_EXTERNAL_CLIENT','client_pids':[c.pid for c in external]}
        models=telemetry.get_json('/api/ps').get('models',[])
        if not models: return {'status':'ALREADY_EMPTY','elapsed_seconds':round(time.monotonic()-started,3)}
        check_loaded({'models':models})
        process=subprocess.run(['ollama','stop',MODEL],capture_output=True,text=True,timeout=timeout)
        if process.returncode != 0:
            return {'status':'STOP_ERROR','returncode':process.returncode,'stderr':process.stderr}
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            models=telemetry.get_json('/api/ps').get('models',[])
            if not models:
                return {'status':'UNLOADED','elapsed_seconds':round(time.monotonic()-started,3)}
            time.sleep(.25)
        return {'status':'UNLOAD_UNCONFIRMED','models':models}
    except Exception as exc:
        return {'status':'UNLOAD_ERROR','error':f'{type(exc).__name__}: {exc}'}


def calibrate(cancel_on_token=False):
    """One standalone request only; no policy promotion or Chat execution."""
    directory = ROOT / 'reports' / 'qwen4b_manual_qa'
    directory.mkdir(parents=True, exist_ok=True)
    output = directory / f'{"cancel_active" if cancel_on_token else "calibration"}_{time.time_ns()}.json'
    record = {'status':'PREPARING','samples':[],'events':[], 'started':telemetry.now(),
              'one_request_only':True, 'other_clients_concurrency':'not globally controlled',
              'limits':{'ram_floor_mib':CAL_RAM_FLOOR_MIB,'admission_ram_mib':CAL_ADMISSION_RAM_MIB,
                        'commit_floor_mib':CAL_COMMIT_FLOOR_MIB,'vram_floor_mib':CAL_VRAM_FLOOR_MIB,
                        'admission_vram_mib':CAL_ADMISSION_VRAM_MIB,'timeout_s':CAL_TIMEOUT_S,
                        'local_gpu_stop_c':telemetry.GPU_STOP_C}}
    def save(): output.write_text(json.dumps(record,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    try: notification = WindowsLowMemory()
    except Exception as exc:
        record.update(status='BLOCKED', reason='OS low-memory notification unavailable: '+str(exc)); save(); print(json.dumps(record,ensure_ascii=False)); return 2
    try:
        initial = telemetry.sample(0); record['initial'] = initial
        try:
            low = notification.low(); connections = active_ollama_connections()
            issues = calibration_issues(initial, low, admission=True)
            if connections: issues.append('active_ollama_connections')
            if cancel_on_token and any(p.get('name','').casefold() in {'llama-server','llama-server.exe'} for p in initial.get('ollama_processes',[])):
                issues.append('existing_runner_process')
            record['connections_before'] = connections
        except Exception as exc:
            issues = ['preflight_error: '+type(exc).__name__]
        if issues:
            record.update(status='BLOCKED', reasons=issues); save(); print(json.dumps({'status':'BLOCKED','reasons':issues,'report':str(output)})); return 2
        signal = CancellationSignal()
        cancel_started=threading.Event()
        def observer(event):
            record['events'].append(event)
            if (cancel_on_token and event.get('type')=='stream_content' and event.get('done') is False
                    and event.get('content_characters',0)>0 and not cancel_started.is_set()):
                cancel_started.set()
                record['cancel_started_monotonic']=time.monotonic()
                record['cancel_started_local']=telemetry.now()
                threading.Thread(target=signal.cancel,daemon=True).start()
        signal.set_stream_observer(observer)
        body = {'model':MODEL,'stream':True,'think':False,'keep_alive':'5m' if cancel_on_token else 0,
                'messages':[{'role':'system','content':CONTEXT},{'role':'user','content':'Объясни различие BMP и фактической выработки метана в реакторе.'}],
                'options':{'num_ctx':4096,'num_batch':32,'num_gpu':-1,'num_predict':512 if cancel_on_token else 256}}
        def call():
            try: record['response'] = request_json(API+'/api/chat',body,CAL_TIMEOUT_S,cancellation=signal)
            except Exception as exc: record['request_error'] = f'{type(exc).__name__}: {exc}'
        record['request'] = body; record['status'] = 'RUNNING'; save()
        start=time.monotonic(); worker=threading.Thread(target=call,daemon=True); worker.start()
        while worker.is_alive():
            row=telemetry.sample(len(record['samples'])+1); record['samples'].append(row)
            try: failures=calibration_issues(row,notification.low())
            except Exception as exc: failures=['low_memory_telemetry_error: '+type(exc).__name__]
            if time.monotonic()-start >= CAL_TIMEOUT_S: failures.append('timeout')
            if failures:
                record['stop_reason']=failures; record['cancel_requested']=telemetry.now(); signal.cancel(); break
            worker.join(.25)
        worker.join(10); record['worker_stopped']=not worker.is_alive()
        record['response_elapsed_seconds']=round(time.monotonic()-start,3)
        unload_start=time.monotonic()
        if cancel_on_token:
            record['unload'] = unload_target_if_uncontended()
            record['unload_finished_monotonic'] = time.monotonic()
            if record.get('cancel_started_monotonic') is not None:
                record['cancel_to_unload_check_seconds'] = round(record['unload_finished_monotonic']-record['cancel_started_monotonic'],3)
            runner_pids = {p['pid'] for row in record['samples'] for p in row.get('ollama_processes',[])
                           if p.get('pid') and p.get('name','').casefold() in {'llama-server','llama-server.exe'}}
            record['observed_runner_pids'] = sorted(runner_pids)
            deadline=time.monotonic()+10
            while any(psutil.pid_exists(pid) for pid in runner_pids) and time.monotonic()<deadline: time.sleep(.1)
            record['runner_pids_remaining']=[pid for pid in sorted(runner_pids) if psutil.pid_exists(pid)]
            record['final']=telemetry.sample(999)
            try: record['api_after']=telemetry.get_json('/api/version')
            except Exception as exc: record['api_after_error']=f'{type(exc).__name__}: {exc}'
            events=record['events']
            transport_cancelled=any(e.get('type')=='request_closed' and e.get('reason')=='cancelled' for e in events)
            normal_done=any(e.get('type')=='stream_done' for e in events)
            record['status']='VERIFIED' if (cancel_started.is_set() and not record.get('stop_reason') and record['worker_stopped'] and transport_cancelled
                and not normal_done and record.get('request_error','').startswith('ExecutionStopped')
                and record['unload'].get('status') in {'UNLOADED','ALREADY_EMPTY'}
                and bool(runner_pids) and not record['runner_pids_remaining'] and not record['final'].get('running_models')
                and bool(record.get('api_after',{}).get('version'))) else 'INCONCLUSIVE'
            record['finished']=telemetry.now(); save()
            print(json.dumps({'status':record['status'],'reason':record.get('stop_reason'),'report':str(output)},ensure_ascii=False))
            return 0 if record['status']=='VERIFIED' else 1
        try:
            models=telemetry.get_json('/api/ps').get('models',[])
            if any(m.get('name')==MODEL or m.get('model')==MODEL for m in models):
                if any(m.get('name')!=MODEL and m.get('model')!=MODEL for m in models):
                    record['unload_error']='another model appeared; no stop issued'
                else:
                    stopped=subprocess.run(['ollama','stop',MODEL],capture_output=True,text=True,timeout=15)
                    record['ollama_stop']={'returncode':stopped.returncode,'stderr':stopped.stderr}
            deadline=time.monotonic()+15
            while time.monotonic()<deadline:
                models=telemetry.get_json('/api/ps').get('models',[])
                if not models: break
                time.sleep(.25)
            record['models_after']=models
            record['unload_seconds']=round(time.monotonic()-unload_start,3)
        except Exception as exc: record['unload_error']=f'{type(exc).__name__}: {exc}'
        record['final']=telemetry.sample(999)
        record['status']='COMPLETED' if record.get('response') and not record.get('stop_reason') and record['worker_stopped'] and not record.get('models_after') and not record.get('unload_error') else 'INCOMPLETE'
        record['finished']=telemetry.now(); save()
        print(json.dumps({'status':record['status'],'reason':record.get('stop_reason'), 'report':str(output)},ensure_ascii=False))
        return 0 if record['status']=='COMPLETED' else 1
    finally: notification.close()


def check_loaded(ps):
    models = ps.get('models') if isinstance(ps, dict) else None
    if not isinstance(models, list) or len(models) != 1:
        raise ProviderError('QA requires exactly one loaded model')
    item = models[0]
    if not isinstance(item, dict) or (item.get('name') != MODEL and item.get('model') != MODEL):
        raise ProviderError('QA model is not loaded or another model is active')
    if item.get('context_length') != 4096:
        raise ProviderError('QA loaded model must report context_length=4096')
    return item


def loaded_model():
    try:
        with urllib.request.urlopen(API + '/api/ps', timeout=2) as response:
            return check_loaded(json.loads(response.read(128 * 1024)))
    except (OSError, ValueError, TypeError) as exc:
        raise ProviderError('QA cannot verify loaded model: ' + type(exc).__name__) from None


def safety_reasons(row, policy, admission):
    # The policy normally rejects all resident models at cold admission. This
    # manual route requires exactly the intended resident model instead.
    model_errors = []
    try:
        check_loaded({'models': row.get('running_models')})
    except ProviderError as exc:
        model_errors.append(str(exc))
    adjusted = dict(row)
    if admission:
        adjusted['running_models'] = []
    failures = reasons(adjusted, policy, admission=admission)
    # A policy for keep_alive=0 cold starts is not approval for this mode.
    if policy.get('manual_preloaded_approved') is not True:
        failures.append('manual_preloaded_mode_not_admitted')
    return model_errors + failures


class ManualProvider(JSONProvider):
    def __init__(self, events):
        super().__init__('offline', model=MODEL, url=API + '/api/chat', timeout=45)
        self.num_ctx = 4096
        self.events = events

    def payload(self, messages, schema=None):
        result = super().payload([{'role':'system','content':CONTEXT}, *messages], schema)
        # Avoid implicit placement changes due to unrelated environment settings.
        for field in ('num_gpu', 'num_batch', 'num_thread'):
            result['options'].pop(field, None)
        result['keep_alive'] = KEEP_ALIVE
        return result

    def generate(self, messages, schema=None):
        if not LOCK.acquire(blocking=False):
            raise ProviderError('QA already has an active request')
        if len(self.events) >= MAX_MODEL_CALLS:
            LOCK.release()
            raise ProviderError('QA model call limit reached')
        event = {'started': telemetry.now(), 'model': MODEL}
        self.events.append(event)
        try:
            before = loaded_model()
            result = super().generate(messages, schema)
            after = loaded_model()
            if before.get('digest') and after.get('digest') != before['digest']:
                raise ProviderError('QA loaded model identity changed during request')
            event.update(status='ok', finished=telemetry.now())
            return result
        except Exception as exc:
            event.update(status='error', error=f'{type(exc).__name__}: {exc}', finished=telemetry.now())
            raise
        finally:
            LOCK.release()


class LimitedProvider(ManualProvider):
    """Bounded QA stages: NLU, tool selection, synthesis and one repair."""
    def __init__(self,events,*,call_offset=0):
        super().__init__(events)
        self.capture_public_output=True
        self.call_offset=call_offset

    def payload(self,messages,schema=None):
        result=super().payload(messages,schema)
        result['options'].update(num_batch=32,num_gpu=-1)
        return result

    def generate(self, messages, schema=None):
        if not LOCK.acquire(blocking=False): raise ProviderError('QA already has an active request')
        try:
            current_events=self.events[self.call_offset:]
            if len(current_events) >= 4: raise ProviderError('QA four-call limit reached')
            models=telemetry.get_json('/api/ps').get('models',[])
            if models: check_loaded({'models':models})
            elif self.events: raise ProviderError('QA model disappeared after first call; refusing reload')
            limit=self.payload(messages,schema)['options']['num_predict']
            used=sum(e.get('token_limit',0) for e in current_events)
            properties=(schema or {}).get('properties',{})
            phase='compact_nlu' if 'material_span' in properties else 'scientific_synthesis' if 'conclusion' in properties else 'tool_selection'
            if phase=='tool_selection' and (len(current_events)>=3 or used+limit+540>1358):
                raise ProviderError('QA synthesis budget reserved')
            if used+limit>1358:
                raise ProviderError('QA total output token budget reached')
            event={'started':telemetry.now(),'model':MODEL,'phase':phase,'messages':messages,'schema':schema,'token_limit':limit}
            self.events.append(event)
            try:
                result=JSONProvider.generate(self,messages,schema)
                loaded_model()
                event.update(status='ok',finished=telemetry.now(),response=result,metrics=self.metrics[-1:])
                return result
            except Exception as exc:
                event.update(status='error',finished=telemetry.now(),error=f'{type(exc).__name__}: {exc}',metrics=self.metrics[-1:])
                raise
        finally:
            LOCK.release()


def foreign_ollama_clients():
    return [c.pid for c in psutil.net_connections(kind='tcp') if c.status=='ESTABLISHED'
            and c.raddr and c.raddr.port==11434 and c.laddr and c.laddr.port!=11434 and c.pid!=os.getpid()]


SCIENTIFIC_CASES = {
    'A': ['Объясни экспериментальный BMP и лабораторную кинетику. Как использовать их при оценке реального реактора?'],
    'B': ['Для 0,6 кг VS при BMP 250 мл CH₄/г VS рассчитай потенциал метана. Гарантирован ли этот выход за 30 дней?'],
    'C': ['У меня 142 л коровьего навоза и реактор номинальной вместимостью 200 л. Сколько метана получится за 30 дней?'],
    'D': ['У меня новая партия: 800 л жидкого коровьего навоза. Запомни объём партии.', 'Исправление: не 800, а 500 л. Какой объём моей текущей партии?'],
    'E': ['Нужен ли кислород для метаногенеза при анаэробном сбраживании? Объясни.'],
}

FARMER_CASES={
    'pig':['Привет! У меня 78 литров жидкого свиного навоза и реактор объёмом 200 литров. Сколько получится метана, выгодно ли его перерабатывать и какую температуру выставить?'],
    'cow':['Есть 41 л жидкого коровьего навоза, реактор 260 л. Какой ориентир метана за 30 дней, какую температуру выбрать и выгодна ли переработка?'],
    'food':['У меня 3,2 кг пищевых отходов, реактор 85 л. Сколько метана можно получить, какую температуру выбрать и выгодно ли использовать газ для обогрева?'],
    'straw':['Есть 4,2 кг сухой соломы и реактор 250 л. Как оценить метан, какую температуру выбрать и выгодна ли переработка?'],
    'compare':['Что выгоднее: 7 кг коровьего навоза или 7 кг пищевых отходов? Сравни метан и экономию.'],
    'no_numbers':['Какую температуру выбрать для жидкого свиного навоза и почему более горячий режим не всегда лучше?'],
    'dialogue':['У меня 63 л жидкого свиного навоза, реактор 210 л. Сколько метана, выгодно ли перерабатывать и какую температуру выбрать?', 'А если температура будет 25 °C?'],
}


def read_message_file(path):
    raw=Path(path).read_bytes();message=raw.decode('utf-8',errors='strict')
    if message.encode('utf-8')!=raw or not message.strip() or len(message)>12000 or '\ufffd' in message or '\x00' in message:
        raise ValueError('INVALID_INPUT: expected intact UTF-8 text,1..12000 characters')
    if message.count('?')>max(3,len(message)//5):raise ValueError('INVALID_INPUT: likely lossy question-mark substitution')
    return message

def limited_chat(case=None,farmer_case=None,message_file=None,followup_file=None):
    """One explicit engineering experiment; does not approve the full policy."""
    directory=ROOT/'reports'/'qwen4b_manual_qa'; directory.mkdir(parents=True,exist_ok=True)
    name=f'limited_chat_{time.time_ns()}'; output=directory/(name+'.json')
    record={'status':'PREPARING','started':telemetry.now(),'samples':[],'provider_calls':[],
            'request':'Чем экспериментальный BMP отличается от теоретического выхода метана? Почему фактический выход за 30 дней может быть ниже BMP?',
            'limits':{'admission_ram_mib':CAL_ADMISSION_RAM_MIB,'runtime_ram_mib':CAL_RAM_FLOOR_MIB,
                      'commit_mib':CAL_COMMIT_FLOOR_MIB,'admission_vram_mib':CAL_ADMISSION_VRAM_MIB,
                      'runtime_vram_mib':CAL_VRAM_FLOOR_MIB,'gpu_stop_c':telemetry.GPU_STOP_C,
                      'timeout_seconds':120,'max_model_calls':4,'max_requested_output_tokens':1358,'keep_alive':'5m'},
            'policy_scope':'single experimental job; not production/full Chat approval'}
    questions=([read_message_file(message_file)]+([read_message_file(followup_file)] if followup_file else [])) if message_file else FARMER_CASES[farmer_case] if farmer_case else SCIENTIFIC_CASES[case] if case else [record['request']]
    bounded_jobs=bool(farmer_case or message_file)
    record['farmer_case']=farmer_case
    if bounded_jobs:
        record['limits'].update(max_model_calls=4*len(questions),max_model_calls_per_job=4,max_model_calls_total=4*len(questions),max_turns=len(questions),max_experiment_seconds=120*len(questions))
    record['case']=case; record['requests']=questions; record['request']=questions[0]; record['turns']=[]
    def save(): output.write_text(json.dumps(record,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    request_started=False
    unload_done=False
    try: notification=WindowsLowMemory()
    except Exception as exc:
        record.update(status='BLOCKED',reason=f'low-memory notification: {exc}'); save(); print(json.dumps({'status':record['status'],'reason':record['reason'],'report':str(output)})); return 2
    try:
        before=telemetry.sample(0); record['before']=before
        try:
            issues=calibration_issues(before,notification.low(),admission=True)
            if active_ollama_connections(): issues.append('active_ollama_connections')
            if any(p.get('name','').casefold() in {'llama-server','llama-server.exe'} for p in before.get('ollama_processes',[])): issues.append('existing_runner_process')
        except Exception as exc: issues=['preflight_error:'+type(exc).__name__]
        if issues:
            record.update(status='BLOCKED',reasons=issues); save(); print(json.dumps({'status':'BLOCKED','reasons':issues,'report':str(output)})); return 2
        def factory(*a,**k):
            if bounded_jobs and len(record['provider_calls'])>=4*len(questions):raise ProviderError('QA experiment total call limit reached')
            return HybridLLM('offline',providers=[LimitedProvider(record['provider_calls'],call_offset=record.get('job_call_offset',0) if bounded_jobs else 0)],strict_model=True)
        app=create_app(Store(directory/(name+'.sqlite3')),scheduler_enabled=False)
        with patch('src.dashboard.api.HybridLLM',side_effect=factory), TestClient(app) as client:
            session=client.post('/api/dashboard/chat/sessions',json={'mode':'offline','context':{},'conversation_version':'7'}).json()
            accepted=client.post(f"/api/dashboard/chat/sessions/{session['id']}/jobs",json={'message':questions[0],'request_id':uuid.uuid4().hex,'expected_state_version':0})
            record['session_id']=session['id']; record['submission_http']=accepted.status_code
            if accepted.status_code!=202:
                record.update(status='FAILED',reason='job submission: '+accepted.text); save(); return 1
            job=accepted.json(); request_started=True; record['job_id']=job['id']; record['status']='RUNNING'; save(); started=time.monotonic(); reason=None
            while True:
                job=client.get(f"/api/dashboard/jobs/{job['id']}").json()
                if job.get('terminal'): break
                try:
                    row=telemetry.sample(len(record['samples'])+1);record['samples'].append(row)
                    failures=calibration_issues(row,notification.low())
                    if foreign_ollama_clients(): failures.append('external_ollama_client')
                except Exception as exc: failures=['telemetry_error:'+type(exc).__name__]
                if time.monotonic()-started>=120: failures.append('job_timeout')
                if failures:
                    reason=failures;record['cancel_response']=client.post(f"/api/dashboard/jobs/{job['id']}/cancel").json();break
                save();time.sleep(.25)
            record['elapsed_seconds']=round(time.monotonic()-started,3);record['job']=job;record['stop_reason']=reason
            if reason:
                deadline=time.monotonic()+10
                while time.monotonic()<deadline:
                    terminal=client.get(f"/api/dashboard/jobs/{job['id']}").json()
                    if terminal.get('terminal'): break
                    time.sleep(.1)
                record['job_after_cancel']=terminal
            else:
                record['result']=client.get(job['result_reference']).json()
                record['events']=client.get(f"/api/dashboard/jobs/{job['id']}/events").json()
                record['turns'].append({'request':questions[0],'job':job,'result':record['result'],'events':record['events'],'elapsed_seconds':record['elapsed_seconds']})
                if len(questions)>1 and job.get('status')=='COMPLETED':
                    snapshot=client.get(f"/api/dashboard/chat/sessions/{session['id']}").json()
                    record['session_before_correction']=snapshot
                    version=snapshot.get('state_version', snapshot.get('session',{}).get('state_version'))
                    if version is None:
                        reason=['session_state_version_unavailable']
                    else:
                        if bounded_jobs:record['job_call_offset']=len(record['provider_calls'])
                        accepted=client.post(f"/api/dashboard/chat/sessions/{session['id']}/jobs",json={'message':questions[1],'request_id':uuid.uuid4().hex,'expected_state_version':version})
                        if accepted.status_code!=202:
                            reason=['correction_submission_http_'+str(accepted.status_code)];record['correction_submission']=accepted.text
                        else:
                            job=accepted.json(); started=time.monotonic()
                            while True:
                                job=client.get(f"/api/dashboard/jobs/{job['id']}").json()
                                if job.get('terminal'): break
                                try:
                                    row=telemetry.sample(len(record['samples'])+1);record['samples'].append(row)
                                    failures=calibration_issues(row,notification.low())
                                    if foreign_ollama_clients(): failures.append('external_ollama_client')
                                except Exception as exc: failures=['telemetry_error:'+type(exc).__name__]
                                if time.monotonic()-started>=120: failures.append('job_timeout')
                                if failures:
                                    reason=failures;record['correction_cancel_response']=client.post(f"/api/dashboard/jobs/{job['id']}/cancel").json();break
                                save();time.sleep(.25)
                            if reason:
                                deadline=time.monotonic()+10
                                while time.monotonic()<deadline:
                                    terminal=client.get(f"/api/dashboard/jobs/{job['id']}").json()
                                    if terminal.get('terminal'): break
                                    time.sleep(.1)
                                record['correction_job_after_cancel']=terminal
                            turn={'request':questions[1],'job':job,'elapsed_seconds':round(time.monotonic()-started,3)}
                            if not reason:
                                turn['result']=client.get(job['result_reference']).json()
                                turn['events']=client.get(f"/api/dashboard/jobs/{job['id']}/events").json()
                            record['turns'].append(turn)
                record['stop_reason']=reason
            record['unload']=unload_target_if_uncontended(); unload_done=True; record['after']=telemetry.sample(999)
            record['status']='COMPLETED' if not reason and job.get('status')=='COMPLETED' and record['unload'].get('status') in {'UNLOADED','ALREADY_EMPTY'} else 'INCOMPLETE'
            record['finished']=telemetry.now();save()
        print(json.dumps({'status':record['status'],'reason':reason,'report':str(output)},ensure_ascii=False))
        return 0 if record['status']=='COMPLETED' else 1
    finally:
        if request_started and not unload_done:
            record['emergency_unload']=unload_target_if_uncontended()
            record['status']='ERROR_CLEANUP_ATTEMPTED'
            save()
        notification.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--message-file', help='UTF-8 text file containing the user question')
    parser.add_argument('--followup-file',help='Optional second UTF-8 question for the same limited Chat session (at most2 jobs)')
    parser.add_argument('--calibrate', action='store_true', help='One monitored standalone 4B calibration; never approves integration')
    parser.add_argument('--cancel-active-test', action='store_true', help='One active-generation cancellation experiment')
    parser.add_argument('--limited-chat', action='store_true', help='One isolated monitored Chat experiment, maximum four model calls')
    parser.add_argument('--firo-demo-case', choices=('methane','incomplete','oxygen'), help='One real explanation through the existing deterministic-first FIRO endpoint')
    parser.add_argument('--case', choices=tuple(SCIENTIFIC_CASES), help='Select a limited scientific scenario (D shares the total model-call budget across two turns)')
    parser.add_argument('--farmer-case',choices=tuple(FARMER_CASES),help='Existing limited Chat:4 calls per job, at most2 turns, same safety limits')
    parser.add_argument('--confirm-experimental', required=True, action='store_true',
                        help='Explicitly opt in to one experimental Chat job; does not override resource policy')
    parser.add_argument('--session', help='Reuse the QA session ID printed by an earlier run')
    parser.add_argument('--timeout', type=int, default=120, choices=range(10, 301), metavar='10..300')
    parser.add_argument('--unload-after', action='store_true', help='Unload only target model after job, if no external clients are visible')
    args = parser.parse_args()
    if args.firo_demo_case:
        if args.limited_chat or args.calibrate or args.cancel_active_test or args.message_file or args.session or args.case or args.farmer_case:
            parser.error('--firo-demo-case cannot be combined with other modes')
        directory=ROOT/'reports'/'qwen4b_manual_qa';directory.mkdir(parents=True,exist_ok=True)
        name='firo_demo_'+str(time.time_ns())
        with TestClient(create_app(Store(directory/(name+'.sqlite3')),scheduler_enabled=False,firo_demo=True)) as client:
            response=client.post('/api/dashboard/firo-demo/runs',json={'case':args.firo_demo_case})
            response.raise_for_status();record=response.json()
            response=client.post('/api/dashboard/firo-demo/runs/'+record['id']+'/explain')
            response.raise_for_status();record=response.json()
        path=directory/(name+'.json');path.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'status':record['explanation']['status'],'report':str(path)},ensure_ascii=False))
        return 0 if record['explanation']['status']=='accepted' else 2
    if args.limited_chat:
        if args.session or args.calibrate or args.cancel_active_test: parser.error('--limited-chat cannot be combined with other modes')
        if sum(bool(v) for v in (args.case,args.farmer_case,args.message_file))>1:parser.error('Choose --case, --farmer-case or --message-file')
        if args.followup_file and not args.message_file:parser.error('--followup-file requires --message-file')
        return limited_chat(args.case,args.farmer_case,args.message_file,args.followup_file)
    if args.case: parser.error('--case requires --limited-chat')
    if args.farmer_case:parser.error('--farmer-case requires --limited-chat')
    if args.followup_file:parser.error('--followup-file requires --limited-chat')
    if args.calibrate or args.cancel_active_test:
        if args.message_file or args.session or (args.calibrate and args.cancel_active_test): parser.error('experiment flags cannot be combined with Chat input or each other')
        return calibrate(cancel_on_token=args.cancel_active_test)
    if not args.message_file: parser.error('--message-file is required for Chat')
    raw = Path(args.message_file).read_bytes()
    message = raw.decode('utf-8', errors='strict')
    if message.encode('utf-8') != raw or not message.strip(): raise ValueError('INVALID_INPUT: UTF-8 or empty input')
    policy = load_policy()
    before = telemetry.sample(0)
    errors = safety_reasons(before, policy, admission=True)
    if errors:
        print(json.dumps({'status':'BLOCKED','reasons':errors}, ensure_ascii=False))
        return 2
    directory = ROOT / 'reports' / 'qwen4b_manual_qa'
    directory.mkdir(parents=True, exist_ok=True)
    record = {'status':'RUNNING', 'message':message, 'started':telemetry.now(), 'provider_calls':[],
              'samples':[before], 'model':MODEL, 'api_endpoint':'FastAPI TestClient dashboard chat jobs',
              'other_clients_concurrency':'uncontrolled', 'model_loading_race':'not preventable by /api/ps check'}
    output = directory / f'{time.time_ns()}_{uuid.uuid4().hex[:8]}.json'
    def save(): output.write_text(json.dumps(record, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    def factory(*args, **kwargs):
        return HybridLLM('offline', providers=[ManualProvider(record['provider_calls'])], strict_model=True)
    save()
    app = create_app(Store(directory / 'qa.sqlite3'), scheduler_enabled=False)
    with patch('src.dashboard.api.HybridLLM', side_effect=factory), TestClient(app) as client:
        if args.session:
            response = client.get(f'/api/dashboard/chat/sessions/{args.session}')
            response.raise_for_status()
            session = response.json()
        else:
            response = client.post('/api/dashboard/chat/sessions', json={'mode':'offline','context':{},'conversation_version':'7'})
            response.raise_for_status(); session = response.json()
        record['session_id'] = session['id']
        accepted = client.post(f"/api/dashboard/chat/sessions/{session['id']}/jobs", json={
            'message':message, 'request_id':uuid.uuid4().hex, 'expected_state_version':session['state_version']})
        accepted.raise_for_status(); job = accepted.json(); record['job_id'] = job['id']; save()
        started = time.monotonic(); reason = None
        while True:
            job = client.get(f"/api/dashboard/jobs/{job['id']}").json()
            if job.get('terminal'): break
            row = telemetry.sample(len(record['samples']))
            record['samples'].append(row)
            failures = safety_reasons(row, policy, admission=False)
            if failures: reason = ', '.join(failures)
            elif time.monotonic() - started >= args.timeout: reason = 'job timeout'
            if reason:
                record['cancel_requested'] = client.post(f"/api/dashboard/jobs/{job['id']}/cancel").json()
                break
            save(); time.sleep(1)
        record.update(status='CANCEL_REQUESTED' if reason else job['status'], stop_reason=reason,
                      elapsed_seconds=round(time.monotonic()-started,2), last_job=job)
        if not reason:
            record['result'] = client.get(job['result_reference']).json()
            record['events'] = client.get(f"/api/dashboard/jobs/{job['id']}/events").json()
        else:
            deadline=time.monotonic()+10
            while time.monotonic()<deadline:
                terminal=client.get(f"/api/dashboard/jobs/{job['id']}").json()
                if terminal.get('terminal'): break
                time.sleep(.1)
            record['job_after_cancel']=terminal
        if reason or args.unload_after:
            record['unload'] = unload_target_if_uncontended()
        save()
    record['finished'] = telemetry.now(); save()
    print(json.dumps({'status':record['status'],'session_id':record['session_id'],'report':str(output),
                      'answer':record.get('result',{}).get('reply',{}).get('answer'),
                      'stop_reason':record.get('stop_reason')},ensure_ascii=False))
    return 0 if record['status']=='COMPLETED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
