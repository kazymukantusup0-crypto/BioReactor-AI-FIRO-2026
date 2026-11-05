"""Explicit verified TLS contexts; never patches SSL globally or installs a CA."""
import os
import ssl
import sys


def verified_context():
    bundle=os.getenv('BIOREACTOR_MARKET_CA_BUNDLE')
    if bundle:
        ctx=ssl.create_default_context(cafile=bundle)
    elif sys.platform=='win32':
        try:import truststore
        except ImportError as exc:
            raise RuntimeError('Install truststore from requirements-market.txt or configure a trusted BIOREACTOR_MARKET_CA_BUNDLE') from exc
        # truststore 0.10.x exposes SSLContext; some managed environments ship
        # an older compatibility shim without it. Keep certificate and hostname
        # verification on through Python's standard context in that case.
        factory=getattr(truststore,'SSLContext',None)
        ctx=factory(ssl.PROTOCOL_TLS_CLIENT) if callable(factory) else ssl.create_default_context()
    else:ctx=ssl.create_default_context()
    if ctx.verify_mode!=ssl.CERT_REQUIRED or not ctx.check_hostname:
        raise RuntimeError('Certificate and hostname validation are mandatory')
    return ctx
