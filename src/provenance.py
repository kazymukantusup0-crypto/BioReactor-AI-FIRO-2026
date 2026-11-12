"""Explicit method and input origins for numerical results.

Verification reports the checks actually performed, not scientific validity.
"""
def calculated(inputs, unit, sources=None, assumptions=None, limitations=None):
    return {'method': 'CALCULATED', 'inputs': inputs, 'unit': unit,
            'sources': sources or [], 'assumptions': assumptions or [],
            'limitations': limitations or [],
            'verification': {'status': 'NOT_PERFORMED', 'scope': None}}


def predicted(inputs, unit, sources=None, limitations=None):
    result=calculated(inputs, unit, sources=sources, limitations=limitations)
    result['method']='PREDICTED'
    return result
