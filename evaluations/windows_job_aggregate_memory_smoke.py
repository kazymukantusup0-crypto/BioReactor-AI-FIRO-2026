"""Check job-wide commit limit with two individually smaller disposable workers."""
import ctypes,json,queue,subprocess,sys,threading,time
from datetime import datetime
from pathlib import Path
import psutil
from windows_job_object_smoke import kernel,ExtendedLimits,check

WORKER="""import json,sys,time
try:
 x=bytearray(80*1024*1024);print(json.dumps({'status':'allocated'}),flush=True);time.sleep(120)
except MemoryError:
 print(json.dumps({'status':'rejected'}),flush=True)
"""
BOOT="""import json,subprocess,sys,time
if sys.stdin.readline().strip()!='go':raise SystemExit(2)
for i in range(2):
 p=subprocess.Popen([sys.executable,'-u','-c',sys.argv[1]],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,creationflags=0x08000000)
 print(json.dumps({'pid':p.pid,'result':json.loads(p.stdout.readline())}),flush=True)
time.sleep(120)
"""

def main():
    out={'start':datetime.now().astimezone().isoformat(),'process_commit_limit_mib':112,'job_commit_limit_mib':144,'worker_allocation_mib':80,'steps':{},'status':'FAILED'}
    job=kernel.CreateJobObjectW(None,None);check(job);parent=None;workers=[]
    try:
        lim=ExtendedLimits();lim.BasicLimitInformation.LimitFlags=0x100|0x200|0x2000
        lim.ProcessMemoryLimit=112*1048576;lim.JobMemoryLimit=144*1048576
        check(kernel.SetInformationJobObject(job,9,ctypes.byref(lim),ctypes.sizeof(lim)))
        parent=subprocess.Popen([sys.executable,'-u','-c',BOOT,WORKER],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,creationflags=subprocess.CREATE_NO_WINDOW)
        check(kernel.AssignProcessToJobObject(job,int(parent._handle)))
        q=queue.Queue();threading.Thread(target=lambda:[q.put(s) for s in parent.stdout],daemon=True).start()
        parent.stdin.write('go\n');parent.stdin.flush()
        first=json.loads(q.get(timeout=10));workers.append(first['pid'])
        second=json.loads(q.get(timeout=10));workers.append(second['pid'])
        out['workers']=[first,second]
        assert first['result']['status']=='allocated' and second['result']['status']=='rejected'
        out['steps']['aggregate_limit_rejects_second_worker']='PASS'
        check(kernel.TerminateJobObject(job,1));parent.wait(timeout=5)
        deadline=time.monotonic()+5
        while any(psutil.pid_exists(pid) for pid in workers) and time.monotonic()<deadline:time.sleep(.05)
        assert not any(psutil.pid_exists(pid) for pid in workers)
        out['steps']['all_owned_workers_stopped']='PASS';out['status']='PASSED'
    except Exception as exc:out['error']=f'{type(exc).__name__}: {exc}'
    finally:
        if parent and parent.poll() is None:
            kernel.TerminateJobObject(job,2)
            try:parent.wait(timeout=2)
            except subprocess.TimeoutExpired:
                parent.terminate()
                try:parent.wait(timeout=3)
                except subprocess.TimeoutExpired:out['cleanup']='BLOCKED'
        kernel.CloseHandle(job)
        if parent:
            for pipe in (parent.stdin,parent.stdout,parent.stderr):
                if pipe:pipe.close()
    out['end']=datetime.now().astimezone().isoformat()
    (Path(__file__).resolve().parents[1]/'reports'/'windows_job_aggregate_memory_smoke_20261111.json').write_text(json.dumps(out,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(out,indent=2));return 0 if out['status']=='PASSED' else 1

if __name__=='__main__':raise SystemExit(main())
