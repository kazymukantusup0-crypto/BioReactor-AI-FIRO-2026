"""Start a test-owned Ollama server in a job with an empty model store; no inference."""
import ctypes,json,os,queue,socket,subprocess,sys,tempfile,threading,time,urllib.request
from ctypes import wintypes
from datetime import datetime
from pathlib import Path
import psutil
from windows_job_object_smoke import kernel,ExtendedLimits,check

PORT=11479
BOOT=r'''import json,os,subprocess,sys
if sys.stdin.readline().strip()!='go':raise SystemExit(2)
p=subprocess.Popen([sys.argv[1],'serve'],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=0x08000000)
print(json.dumps({'pid':p.pid}),flush=True)
p.wait()
'''
def get(port,path):
    with urllib.request.urlopen(f'http://127.0.0.1:{port}{path}',timeout=2) as r:return json.loads(r.read().decode('utf-8'))

def main():
    out={'start':datetime.now().astimezone().isoformat(),'port':PORT,'model_inference':'NOT RUN','status':'FAILED','steps':{}}
    job=kernel.CreateJobObjectW(None,None);check(job)
    boot=None;server_pid=None
    try:
        with socket.socket() as s:
            s.bind(('127.0.0.1',PORT))
        production_before={'version':get(11434,'/api/version'),'ps':get(11434,'/api/ps')}
        out['production_before']=production_before
        server_path=Path(os.environ['LOCALAPPDATA'])/'Programs'/'Ollama'/'ollama.exe'
        if not server_path.is_file():raise FileNotFoundError(server_path)
        limits=ExtendedLimits();limits.BasicLimitInformation.LimitFlags=0x100|0x200|0x2000
        limits.ProcessMemoryLimit=256*1024*1024;limits.JobMemoryLimit=384*1024*1024
        check(kernel.SetInformationJobObject(job,9,ctypes.byref(limits),ctypes.sizeof(limits)))
        with tempfile.TemporaryDirectory(prefix='bioreactor-ollama-empty-') as store:
            env=os.environ.copy();env.update(OLLAMA_HOST=f'127.0.0.1:{PORT}',OLLAMA_MODELS=store,
                                              OLLAMA_NUM_PARALLEL='1',OLLAMA_NO_CLOUD='1')
            boot=subprocess.Popen([sys.executable,'-u','-c',BOOT,str(server_path)],stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,creationflags=subprocess.CREATE_NO_WINDOW,env=env)
            check(kernel.AssignProcessToJobObject(job,int(boot._handle)))
            boot.stdin.write('go\n');boot.stdin.flush()
            lines=queue.Queue();threading.Thread(target=lambda:[lines.put(s) for s in boot.stdout],daemon=True).start()
            server_pid=json.loads(lines.get(timeout=8))['pid']
            handle=kernel.OpenProcess(0x1000,False,server_pid);check(handle)
            try:
                inside=wintypes.BOOL();check(kernel.IsProcessInJob(handle,job,ctypes.byref(inside)))
                if not inside.value:raise RuntimeError('server did not inherit job')
            finally:kernel.CloseHandle(handle)
            out['steps']['server_in_job']='PASS';out['server_pid']=server_pid
            deadline=time.monotonic()+12
            while True:
                try:
                    out['qa_version']=get(PORT,'/api/version');out['qa_ps']=get(PORT,'/api/ps');break
                except (OSError,ValueError):
                    if boot.poll() is not None or time.monotonic()>deadline:raise RuntimeError('QA server failed to start within timeout')
                    time.sleep(.2)
            out['steps']['qa_api']='PASS'
            out['qa_models']=get(PORT,'/api/tags')
            if out['qa_models'].get('models'):raise RuntimeError('isolated store unexpectedly nonempty')
            out['steps']['empty_model_store']='PASS'
            out['production_during']={'version':get(11434,'/api/version'),'ps':get(11434,'/api/ps')}
            start=time.monotonic();check(kernel.TerminateJobObject(job,1));boot.wait(timeout=8)
            deadline=time.monotonic()+8
            while psutil.pid_exists(server_pid) and time.monotonic()<deadline:time.sleep(.05)
            if psutil.pid_exists(server_pid):raise RuntimeError('QA server still exists after job termination')
            out['termination_seconds']=round(time.monotonic()-start,3);out['steps']['qa_tree_stopped']='PASS'
            try:get(PORT,'/api/version');raise RuntimeError('QA port still responds')
            except (OSError,ValueError):out['steps']['qa_port_closed']='PASS'
            out['production_after']={'version':get(11434,'/api/version'),'ps':get(11434,'/api/ps')}
            out['steps']['production_api_survived']='PASS';out['status']='PASSED'
    except Exception as exc:out['error']=f'{type(exc).__name__}: {exc}'
    finally:
        kernel.TerminateJobObject(job,2)
        if boot and boot.poll() is None:
            try:boot.wait(timeout=2)
            except subprocess.TimeoutExpired:
                boot.terminate()
                try:boot.wait(timeout=3)
                except subprocess.TimeoutExpired:out['cleanup']='BLOCKED: owned bootstrap still running'
        kernel.CloseHandle(job)
        if boot:
            for pipe in (boot.stdin,boot.stdout,boot.stderr):
                if pipe:pipe.close()
    out['end']=datetime.now().astimezone().isoformat();out['server_pid']=server_pid
    (Path(__file__).resolve().parents[1]/'reports'/f'isolated_ollama_job_smoke_{time.time_ns()}.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(out,ensure_ascii=False,indent=2));return 0 if out['status']=='PASSED' else 1

if __name__=='__main__':raise SystemExit(main())
