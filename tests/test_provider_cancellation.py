import json
import errno
import io
import ssl
import threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer

import pytest

from src.agent.cancellation import CancellationSignal,ExecutionStopped
from src.agent.providers import HybridLLM,JSONProvider,ProviderError,request_json


def test_cancel_during_tcp_connect_closes_socket_without_sending(monkeypatch):
    from src.agent import providers
    connect_waiting=threading.Event();socket_closed=threading.Event();outcome=[]

    class PendingSocket:
        def setblocking(self,value):pass
        def connect_ex(self,address):return errno.EINPROGRESS
        def shutdown(self,how):socket_closed.set()
        def close(self):socket_closed.set()
        def sendall(self,data):raise AssertionError('HTTP request must not be sent')

    sock=PendingSocket()
    monkeypatch.setattr(providers.socket,'getaddrinfo',lambda *args:[
        (providers.socket.AF_INET,providers.socket.SOCK_STREAM,0,'',('127.0.0.1',11434))])
    monkeypatch.setattr(providers.socket,'socket',lambda *args:sock)

    def pending_select(_read,_write,_exceptional,timeout):
        connect_waiting.set();socket_closed.wait(2)
        return [],[],[]

    monkeypatch.setattr(providers.select,'select',pending_select)
    signal=CancellationSignal()

    def call():
        try:invoke('http://127.0.0.1:11434/connect-cancel',signal)
        except Exception as exc:outcome.append(exc)

    request_thread=threading.Thread(target=call,daemon=True);request_thread.start()
    assert connect_waiting.wait(1)
    signal.cancel();request_thread.join(2)
    assert not request_thread.is_alive() and socket_closed.is_set()
    assert len(outcome)==1 and isinstance(outcome[0],ExecutionStopped)


def test_cancel_during_blocking_http_send_closes_socket_without_reconnect(monkeypatch):
    from src.agent import providers
    send_entered=threading.Event();socket_closed=threading.Event();outcome=[]

    class BlockingSendSocket:
        connect_attempts=0
        def setblocking(self,value):pass
        def settimeout(self,value):pass
        def connect_ex(self,address):
            self.connect_attempts+=1
            return 0
        def sendall(self,data):
            send_entered.set()
            if not socket_closed.wait(2):raise AssertionError('Cancel did not close the sending socket')
            raise OSError('socket closed during send')
        def shutdown(self,how):socket_closed.set()
        def close(self):socket_closed.set()

    sock=BlockingSendSocket()
    monkeypatch.setattr(providers.socket,'getaddrinfo',lambda *args:[
        (providers.socket.AF_INET,providers.socket.SOCK_STREAM,0,'',('127.0.0.1',11434))])
    monkeypatch.setattr(providers.socket,'socket',lambda *args:sock)
    signal=CancellationSignal()

    def call():
        try:invoke('http://127.0.0.1:11434/send-cancel',signal)
        except Exception as exc:outcome.append(exc)

    request_thread=threading.Thread(target=call,daemon=True);request_thread.start()
    assert send_entered.wait(1)
    assert signal.cancel() is True
    assert signal.cancel() is False
    request_thread.join(2)
    assert not request_thread.is_alive() and socket_closed.is_set()
    assert sock.connect_attempts==1
    assert len(outcome)==1 and isinstance(outcome[0],ExecutionStopped)


def test_https_connection_keeps_certificate_context_and_parses_response(monkeypatch):
    from src.agent import providers
    raw=type('RawSocket',(),{
        'setblocking':lambda self,value:None,
        'settimeout':lambda self,value:None,
        'connect_ex':lambda self,address:0,
        'shutdown':lambda self,how:None,
        'close':lambda self:None,
    })()
    class TLSContext:
        def wrap_socket(self,sock,server_hostname,do_handshake_on_connect):
            assert sock is raw and server_hostname=='example.test' and not do_handshake_on_connect
            return tls
    class TLSSocket:
        def setblocking(self,value):pass
        def settimeout(self,value):pass
        def do_handshake(self):pass
        def sendall(self,data):pass
        def makefile(self,mode):return io.BytesIO(b'HTTP/1.1 200 OK\r\nContent-Length: 11\r\n\r\n{"ok":true}')
        def shutdown(self,how):pass
        def close(self):pass
    tls=TLSSocket();context=TLSContext()
    monkeypatch.setattr(providers.socket,'getaddrinfo',lambda *args:[
        (providers.socket.AF_INET,providers.socket.SOCK_STREAM,0,'',('127.0.0.1',443))])
    monkeypatch.setattr(providers.socket,'socket',lambda *args:raw)
    monkeypatch.setattr(providers.ssl,'create_default_context',lambda:context)
    assert request_json('https://example.test/ok',{},timeout=2)=={'ok':True}


def test_cancel_during_https_tls_handshake_closes_socket(monkeypatch):
    from src.agent import providers
    handshake_waiting=threading.Event();socket_closed=threading.Event();outcome=[]
    raw=type('RawSocket',(),{
        'setblocking':lambda self,value:None,
        'settimeout':lambda self,value:None,
        'connect_ex':lambda self,address:0,
        'shutdown':lambda self,how:socket_closed.set(),
        'close':lambda self:socket_closed.set(),
    })()
    class TLSSocket:
        def setblocking(self,value):pass
        def settimeout(self,value):pass
        def do_handshake(self):raise ssl.SSLWantReadError()
        def shutdown(self,how):socket_closed.set()
        def close(self):socket_closed.set()
        def sendall(self,data):raise AssertionError('HTTP request must not be sent')
    tls=TLSSocket()
    class TLSContext:
        def wrap_socket(self,sock,server_hostname,do_handshake_on_connect):return tls
    monkeypatch.setattr(providers.socket,'getaddrinfo',lambda *args:[
        (providers.socket.AF_INET,providers.socket.SOCK_STREAM,0,'',('127.0.0.1',443))])
    monkeypatch.setattr(providers.socket,'socket',lambda *args:raw)
    monkeypatch.setattr(providers.ssl,'create_default_context',lambda:TLSContext())
    def pending_select(_read,_write,_exceptional,timeout):
        handshake_waiting.set();socket_closed.wait(2)
        return [],[],[]
    monkeypatch.setattr(providers.select,'select',pending_select)
    signal=CancellationSignal()
    def call():
        try:request_json('https://example.test/cancel',{},timeout=5,cancellation=signal)
        except Exception as exc:outcome.append(exc)
    request_thread=threading.Thread(target=call,daemon=True);request_thread.start()
    assert handshake_waiting.wait(1)
    signal.cancel();request_thread.join(2)
    assert not request_thread.is_alive() and socket_closed.is_set()
    assert len(outcome)==1 and isinstance(outcome[0],ExecutionStopped)


def start_server(handler):
    server=ThreadingHTTPServer(('127.0.0.1',0),handler)
    server.daemon_threads=True
    thread=threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    return server,thread


def stop_server(server,thread):
    server.shutdown();server.server_close();thread.join(1)


def invoke(url,signal=None,payload=None,timeout=5):
    return request_json(url,payload or {'test':True},timeout,cancellation=signal)


def test_cancel_before_http_request_never_connects():
    requests=[]
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):requests.append(self.path)
        def log_message(self,*args):pass
    server,thread=start_server(Handler)
    signal=CancellationSignal();signal.cancel()
    try:
        with pytest.raises(ExecutionStopped):
            invoke(f'http://127.0.0.1:{server.server_port}/cancel-before',signal)
        assert requests==[]
    finally:stop_server(server,thread)


def test_cancel_during_response_wait_closes_socket_and_discards_late_response():
    entered=threading.Event();client_closed=threading.Event();late_response_attempted=threading.Event()
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers.get('Content-Length','0')))
            self.send_response(200);self.send_header('Content-Length','128');self.end_headers();self.wfile.flush()
            entered.set()
            try:
                self.connection.recv(1)
                client_closed.set()
                late_response_attempted.set()
                self.wfile.write(b'{"message":{"content":"{\\"late\\":true}"}}')
                self.wfile.flush()
            except OSError:
                client_closed.set();late_response_attempted.set()
        def log_message(self,*args):pass
    server,thread=start_server(Handler)
    signal=CancellationSignal();outcome=[]
    def call():
        try:outcome.append(('result',invoke(f'http://127.0.0.1:{server.server_port}/wait',signal)))
        except Exception as exc:outcome.append(('error',exc))
    request_thread=threading.Thread(target=call,daemon=True);request_thread.start()
    try:
        assert entered.wait(2)
        signal.cancel()
        request_thread.join(2)
        assert not request_thread.is_alive()
        assert client_closed.wait(1) and late_response_attempted.is_set()
        assert len(outcome)==1 and outcome[0][0]=='error' and isinstance(outcome[0][1],ExecutionStopped)
    finally:stop_server(server,thread)


def test_cancel_during_ollama_style_stream_closes_stream_and_discards_chunks():
    first_chunk=threading.Event();client_closed=threading.Event()
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers.get('Content-Length','0')))
            self.send_response(200);self.send_header('Content-Type','application/x-ndjson');self.end_headers()
            self.wfile.write(b'{"message":{"role":"assistant","content":"{\\"partial\\":"},"done":false}\n');self.wfile.flush()
            first_chunk.set()
            try:self.connection.recv(1)
            except OSError:pass
            client_closed.set()
        def log_message(self,*args):pass
    server,thread=start_server(Handler)
    signal=CancellationSignal();outcome=[]
    def call():
        try:outcome.append(('result',invoke(f'http://127.0.0.1:{server.server_port}/stream',signal,{'stream':True})))
        except Exception as exc:outcome.append(('error',exc))
    request_thread=threading.Thread(target=call,daemon=True);request_thread.start()
    try:
        assert first_chunk.wait(2)
        signal.cancel();request_thread.join(2)
        assert not request_thread.is_alive() and client_closed.wait(1)
        assert len(outcome)==1 and outcome[0][0]=='error' and isinstance(outcome[0][1],ExecutionStopped)
    finally:stop_server(server,thread)


def test_stream_response_is_aggregated_for_json_provider_and_cancellable_job():
    received=[]
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            received.append(json.loads(self.rfile.read(int(self.headers.get('Content-Length','0')))))
            chunks=[
                {'message':{'role':'assistant','content':'{"ok":'},'done':False},
                {'message':{'role':'assistant','content':'true}'},'done':True,'prompt_eval_count':3,'eval_count':2,'eval_duration':1000000000},
            ]
            self.send_response(200);self.send_header('Content-Type','application/x-ndjson');self.end_headers()
            for chunk in chunks:self.wfile.write(json.dumps(chunk).encode()+b'\n');self.wfile.flush()
        def log_message(self,*args):pass
    server,thread=start_server(Handler)
    provider=JSONProvider('offline',model='qwen3:8b',url=f'http://127.0.0.1:{server.server_port}/api/chat')
    signal=CancellationSignal();llm=HybridLLM('offline',providers=[provider]);llm.bind_cancellation(signal)
    try:
        result=provider.generate([{'role':'user','content':'test'}])
        assert result=={'ok':True}
        assert received[0]['stream'] is True
        assert provider.metrics[-1]['status']=='ok' and provider.metrics[-1]['output_tokens']==2
    finally:stop_server(server,thread)


def test_json_provider_checks_bound_signal_before_starting_model_request():
    from unittest.mock import patch
    provider=JSONProvider('offline',model='qwen3:8b')
    signal=CancellationSignal();signal.cancel()
    llm=HybridLLM('offline',providers=[provider]);llm.bind_cancellation(signal)
    with patch('src.agent.providers.request_json') as request:
        with pytest.raises(ExecutionStopped):provider.generate([{'role':'user','content':'must not send'}])
        request.assert_not_called()


def test_http_timeout_remains_a_provider_error_and_releases_connection():
    entered=threading.Event();release=threading.Event();client_closed=threading.Event()
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers.get('Content-Length','0')));entered.set()
            release.wait(2)
            try:self.wfile.write(b'{"late":true}');self.wfile.flush()
            except OSError:client_closed.set()
        def log_message(self,*args):pass
    server,thread=start_server(Handler)
    try:
        with pytest.raises(ProviderError,match='Provider unreachable'):
            request_json(f'http://127.0.0.1:{server.server_port}/timeout',{},timeout=.15)
        assert entered.wait(1)
    finally:release.set();stop_server(server,thread)


def test_http_error_response_closes_connection(monkeypatch):
    from src.agent import providers
    closed=[]
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers.get('Content-Length','0')))
            body=b'upstream failure'
            self.send_response(503);self.send_header('Content-Length',str(len(body)));self.end_headers()
            self.wfile.write(body)
        def log_message(self,*args):pass
    server,thread=start_server(Handler)
    original_close=providers.http.client.HTTPConnection.close
    def observed_close(connection):
        closed.append(True)
        return original_close(connection)
    monkeypatch.setattr(providers.http.client.HTTPConnection,'close',observed_close)
    try:
        with pytest.raises(ProviderError,match='HTTP 503'):
            request_json(f'http://127.0.0.1:{server.server_port}/error',{},timeout=2)
        assert closed
    finally:stop_server(server,thread)


def test_parallel_independent_requests_cancel_only_the_selected_signal():
    cancel_entered=threading.Event();cancel_closed=threading.Event();normal_entered=threading.Event();normal_release=threading.Event()
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers.get('Content-Length','0')))
            if self.path=='/cancel':
                cancel_entered.set()
                try:self.connection.recv(1)
                except OSError:pass
                cancel_closed.set()
                return
            normal_entered.set();normal_release.wait(2)
            try:
                body=json.dumps({'message':{'content':'{"independent":true}'}}).encode()
                self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
            except OSError:pass
        def log_message(self,*args):pass
    server,thread=start_server(Handler)
    cancelled=CancellationSignal();independent=CancellationSignal();outcomes=[]
    def call(path,signal):
        try:outcomes.append((path,'result',invoke(f'http://127.0.0.1:{server.server_port}/{path}',signal)))
        except Exception as exc:outcomes.append((path,'error',exc))
    first=threading.Thread(target=call,args=('cancel',cancelled),daemon=True)
    second=threading.Thread(target=call,args=('normal',independent),daemon=True)
    first.start();second.start()
    try:
        assert cancel_entered.wait(2) and normal_entered.wait(2)
        cancelled.cancel();first.join(2)
        assert not first.is_alive() and cancel_closed.wait(1)
        normal_release.set();second.join(2)
        assert not second.is_alive()
        assert any(path=='cancel' and kind=='error' and isinstance(value,ExecutionStopped) for path,kind,value in outcomes)
        assert any(path=='normal' and kind=='result' and value['message']['content']=='{"independent":true}' for path,kind,value in outcomes)
        assert not independent.cancelled
    finally:normal_release.set();stop_server(server,thread)
