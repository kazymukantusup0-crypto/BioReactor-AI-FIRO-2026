"""Source-bound guidance does not assert a validated control setpoint."""
from src.recommendations.retrieval import retrieve


def scientific_conditions(parameters):
    material = parameters.material
    found = retrieve('temperature process loading retention pH BMP', material=material,
                     topics=['temperature', 'process', 'loading', 'retention', 'ph', 'bmp'])
    claims = found.get('claims', [])
    references = [c for c in claims if c['id'] == 'mesophilic_reference']
    return {'claims': claims, 'scientific_sources': found.get('sources', []),
            'reference_temperature_c': references[0]['values'][0] if references else None,
            'reference_scope': references[0]['scope'] if references else None,
            'temperature_yield_response_available': False,
            'message': 'Local reviewed catalogue; no universal optimum, residence time or temperature-to-BMP response is inferred.'}
