"""Read-only TLS comparison. Every backend validates certificates and hostnames."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
from importlib.metadata import version
import hashlib
import json
import os
from pathlib import Path
import platform
import ssl
import sys
import urllib.request
from urllib.parse import urlsplit
sys.path.insert(0,str(Path(__file__).resolve().parent))
import main

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'reports/stage3_5'


def context(backend):
    if backend=='windows_native':
        import truststore
        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    if backend=='certifi':
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    return ssl.create_default_context()


def probe(item):
    backend,url=item
    result={'backend':backend,'url':url}
    try:
        ctx=context(backend)
        result.update(certificate_required=ctx.verify_mode==ssl.CERT_REQUIRED,hostname_check=ctx.check_hostname)
        if not result['certificate_required'] or not result['hostname_check']:raise RuntimeError('Unsafe TLS configuration')
        with urllib.request.urlopen(url,context=ctx,timeout=15) as response:
            result.update(http_status=response.status,final_url=response.url)
            try:
                der=response.fp.raw._sock.getpeercert(binary_form=True)
                from cryptography import x509
                cert=x509.load_der_x509_certificate(der)
                result['leaf_certificate']={'issuer':cert.issuer.rfc4514_string(),'subject':cert.subject.rfc4514_string(),
                    'not_before_utc':cert.not_valid_before_utc.isoformat(),'not_after_utc':cert.not_valid_after_utc.isoformat(),
                    'sha256':hashlib.sha256(der).hexdigest()}
            except (AttributeError,ImportError,ValueError):pass
            response.read(1024)
        result['status']='verified_https_success'
    except Exception as exc:
        result.update(status='failed',error_type=type(exc).__name__,error=str(exc))
    return result


def run():
    OUT.mkdir(parents=True,exist_ok=True)
    urls=['https://www.esalmaty.kz/ru/business-tariffs','https://stat.gov.kz/ru/industries/economy/prices/spreadsheets/?name=19087',
        'https://www.k-zharyk.kz/ru/node/329','https://krec.kz/notices']
    items=[(backend,urls[0]) for backend in ['default','certifi','windows_native']]+[('windows_native',url) for url in urls[1:]]
    with ThreadPoolExecutor(max_workers=3) as pool:probes=list(pool.map(probe,items))
    env={}
    for key,value in os.environ.items():
        if key.lower() in {'http_proxy','https_proxy','all_proxy','no_proxy','ssl_cert_file','ssl_cert_dir','requests_ca_bundle','curl_ca_bundle'}:
            parsed=urlsplit(value)
            env[key]={'present':True,'hostname':parsed.hostname,'credentials_present':bool(parsed.username)} if 'proxy' in key.lower() and key.lower()!='no_proxy' else {'present':True}
    result={'python':sys.version,'openssl':ssl.OPENSSL_VERSION,'platform':platform.platform(),
        'utc_time':datetime.now(timezone.utc).isoformat(),'client_timezone':'Asia/Qyzylorda','environment':env,
        'urllib_proxy_setting_names':list(urllib.request.getproxies()),'certifi':version('certifi'),'truststore':version('truststore'),
        'windows_roots':len(ssl.enum_certificates('ROOT')) if sys.platform=='win32' else None,
        'windows_intermediates':len(ssl.enum_certificates('CA')) if sys.platform=='win32' else None,
        'default_verify_flags':int(ssl.create_default_context().verify_flags),'probes':probes,
        'verification_disabled':False,'global_ssl_injection':False}
    (OUT/'tls_diagnostics.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':run()
