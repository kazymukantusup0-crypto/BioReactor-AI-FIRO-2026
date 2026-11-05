"""One foreground process: bundled React + existing FastAPI, Ctrl+C shuts it down."""
import threading
import socket
import time
import urllib.request
import webbrowser
from src.data.prepare import ROOT


def run(args):
    dist=ROOT/'frontend/dist/index.html'
    if not dist.is_file():raise ValueError('Frontend not built. Run: cd BioReactor_AI/frontend; npm.cmd ci; npm.cmd run build')
    if not 1<=args.port<=65535:raise ValueError('Port must be between 1 and 65535')
    try:
        with socket.socket() as probe:probe.bind(('127.0.0.1',args.port))
    except OSError:raise ValueError(f'Port {args.port} is already in use. Open the existing dashboard or use --port with another port.') from None
    import uvicorn
    from src.market.api import create_app
    app=create_app(scheduler_enabled=False if args.no_scheduler else None)
    address=f'http://127.0.0.1:{args.port}'
    if not args.no_browser:
        def open_when_ready():
            for _ in range(60):
                try:
                    with urllib.request.urlopen(address+'/health',timeout=1) as response:
                        if response.status==200:webbrowser.open(address+'/dashboard/');return
                except OSError:pass
                time.sleep(.25)
        threading.Thread(target=open_when_ready,daemon=True).start()
    print('BioReactor AI Control Center: '+address+'/dashboard/  |  Ctrl+C to stop')
    uvicorn.run(app,host='127.0.0.1',port=args.port,log_level='info')
