"""Bounded Windows Job Object smoke test. Starts only disposable Python processes."""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
from datetime import datetime

import psutil

if os.name != 'nt':
    raise SystemExit('Windows is required')

kernel=ctypes.WinDLL('kernel32',use_last_error=True)
SIZE=ctypes.c_size_t

class BasicLimits(ctypes.Structure):
    _fields_=[('PerProcessUserTimeLimit',ctypes.c_longlong),('PerJobUserTimeLimit',ctypes.c_longlong),
              ('LimitFlags',wintypes.DWORD),('MinimumWorkingSetSize',SIZE),('MaximumWorkingSetSize',SIZE),
              ('ActiveProcessLimit',wintypes.DWORD),('Affinity',SIZE),('PriorityClass',wintypes.DWORD),('SchedulingClass',wintypes.DWORD)]

class IoCounters(ctypes.Structure):
    _fields_=[(name,ctypes.c_ulonglong) for name in ('ReadOperationCount','WriteOperationCount','OtherOperationCount','ReadTransferCount','WriteTransferCount','OtherTransferCount')]

class ExtendedLimits(ctypes.Structure):
    _fields_=[('BasicLimitInformation',BasicLimits),('IoInfo',IoCounters),('ProcessMemoryLimit',SIZE),('JobMemoryLimit',SIZE),('PeakProcessMemoryUsed',SIZE),('PeakJobMemoryUsed',SIZE)]

for name,args,result in [
    ('CreateJobObjectW',[ctypes.c_void_p,wintypes.LPCWSTR],wintypes.HANDLE),
    ('SetInformationJobObject',[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD],wintypes.BOOL),
    ('QueryInformationJobObject',[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD,ctypes.c_void_p],wintypes.BOOL),
    ('AssignProcessToJobObject',[wintypes.HANDLE,wintypes.HANDLE],wintypes.BOOL),
    ('TerminateJobObject',[wintypes.HANDLE,wintypes.UINT],wintypes.BOOL),
    ('IsProcessInJob',[wintypes.HANDLE,wintypes.HANDLE,ctypes.POINTER(wintypes.BOOL)],wintypes.BOOL),
    ('OpenProcess',[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD],wintypes.HANDLE),
    ('CloseHandle',[wintypes.HANDLE],wintypes.BOOL),
]:
    fn=getattr(kernel,name);fn.argtypes=args;fn.restype=result

def check(ok):
    if not ok: raise ctypes.WinError(ctypes.get_last_error())

CHILD=r'''import json,subprocess,sys,time
print(json.dumps({'event':'waiting'}),flush=True)
if sys.stdin.readline().strip() != 'go': raise SystemExit(2)
try:
    x=bytearray(256*1024*1024)
    print(json.dumps({'event':'allocation_unexpectedly_succeeded'}),flush=True)
except MemoryError:
    print(json.dumps({'event':'allocation_rejected','exception':'MemoryError'}),flush=True)
p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(120)'],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=0x08000000)
print(json.dumps({'event':'descendant','pid':p.pid}),flush=True)
time.sleep(120)
'''

def main():
    result={'started_at':datetime.now().astimezone().isoformat(),'memory_limit_mib':128,
            'type':'synthetic Python children, no Ollama','steps':{},'status':'FAILED'}
    before=psutil.virtual_memory().available
    job=kernel.CreateJobObjectW(None,None); check(job)
    process=None; descendant_pid=None
    try:
        limits=ExtendedLimits();limits.BasicLimitInformation.LimitFlags=0x100 | 0x200 | 0x2000
        limits.ProcessMemoryLimit=128*1024*1024;limits.JobMemoryLimit=128*1024*1024
        check(kernel.SetInformationJobObject(job,9,ctypes.byref(limits),ctypes.sizeof(limits)))
        result['steps']['limits_set']='PASS'
        # This child waits for stdin before allocations or spawning descendants.
        # Production launch would need CREATE_SUSPENDED and assignment before ResumeThread.
        process=subprocess.Popen([sys.executable,'-u','-c',CHILD],stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE,text=True,creationflags=subprocess.CREATE_NO_WINDOW)
        lines=queue.Queue()
        threading.Thread(target=lambda:[lines.put(s) for s in process.stdout],daemon=True).start()
        assert json.loads(lines.get(timeout=10))['event']=='waiting'
        check(kernel.AssignProcessToJobObject(job,int(process._handle)))
        in_job=wintypes.BOOL();check(kernel.IsProcessInJob(int(process._handle),job,ctypes.byref(in_job)))
        assert in_job.value;result['steps']['parent_assigned']='PASS'
        process.stdin.write('go\n');process.stdin.flush()
        allocation=json.loads(lines.get(timeout=10));result['allocation']=allocation
        assert allocation['event']=='allocation_rejected';result['steps']['over_limit_commit_rejected']='PASS'
        spawned=json.loads(lines.get(timeout=10));assert spawned['event']=='descendant';descendant_pid=spawned['pid']
        handle=kernel.OpenProcess(0x1000,False,descendant_pid);check(handle)
        try:
            inherited=wintypes.BOOL();check(kernel.IsProcessInJob(handle,job,ctypes.byref(inherited)))
            assert inherited.value;result['steps']['descendant_in_job']='PASS'
        finally:kernel.CloseHandle(handle)
        assert process.poll() is None;result['steps']['hang_detected']='PASS'
        observed=ExtendedLimits();check(kernel.QueryInformationJobObject(job,9,ctypes.byref(observed),ctypes.sizeof(observed),None))
        result['peak_job_commit_mib']=round(observed.PeakJobMemoryUsed/1048576,2)
        start=time.monotonic();check(kernel.TerminateJobObject(job,1));process.wait(timeout=10)
        deadline=time.monotonic()+10
        while psutil.pid_exists(descendant_pid) and time.monotonic()<deadline:time.sleep(.05)
        result['termination_elapsed_seconds']=round(time.monotonic()-start,3)
        assert not psutil.pid_exists(descendant_pid);result['steps']['terminate_tree']='PASS'
        result['steps']['recovery_sample']='PASS';result['status']='PASSED'
    except Exception as exc:
        result['error']=f'{type(exc).__name__}: {exc}'
    finally:
        if process and process.poll() is None:
            kernel.TerminateJobObject(job,2)
            try:process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                # The disposable parent can still be unassigned if admission failed.
                process.terminate()
                try:process.wait(timeout=3)
                except subprocess.TimeoutExpired:result['cleanup']='BLOCKED: owned parent did not exit'
        kernel.CloseHandle(job)
        if process:
            for pipe in (process.stdin,process.stdout,process.stderr):
                if pipe:pipe.close()
    result.update(parent_pid=process.pid if process else None,descendant_pid=descendant_pid,
                  ram_available_before_mib=round(before/1048576,1),
                  ram_available_after_mib=round(psutil.virtual_memory().available/1048576,1),
                  ended_at=datetime.now().astimezone().isoformat())
    path=Path(__file__).resolve().parents[1]/'reports'/'windows_job_object_smoke_20261111.json'
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result['status']=='PASSED' else 1

if __name__=='__main__':raise SystemExit(main())
