"""Fixed public adapters: never fetch an arbitrary user URL or authenticated resource."""
from urllib.parse import urlsplit
from src.market.adapters import public_get,SourceError

ALLOWED={'api.crossref.org','stroitaxi.kz','media.springernature.com','biogas.fnr.de'}
def validate_url(url):
    p=urlsplit(url)
    if p.scheme!='https' or p.hostname not in ALLOWED or p.username or p.password or p.port not in {None,443} or p.fragment:
        raise SourceError('Source outside configured public HTTPS allowlist')
    return url

def download(url,evidence,fetcher=None):
    validate_url(url)
    try:
        raw=(fetcher or public_get)(url)
        evidence.log(url,'success',f'{len(raw)} bytes; robots/TLS checked by public adapter')
        return raw
    except (SourceError,OSError,ValueError) as exc:
        evidence.log(url,'unavailable',str(exc));raise
