"""Generate only entered alternatives or a narrowly scoped literature reference."""
from src.optimizer.schemas import ProcessParameters, ProcessRequest
from src.optimizer.scientific_conditions import scientific_conditions


def generate_scenarios(request):
    request = request if isinstance(request, ProcessRequest) else ProcessRequest.model_validate(request)
    base = {k: getattr(request, k) for k in ProcessParameters.model_fields}
    # Optional assumptions may supply missing inputs, but remain visibly hypothetical.
    for key, entry in request.assumptions.items():
        if key in ProcessParameters.model_fields and key not in {'assumptions', 'market', 'user_limits', 'model'}:
            value = entry.get('value') if isinstance(entry, dict) and 'value' in entry else entry
            if base.get(key) is None:
                base[key] = value
    parameters = ProcessParameters.model_validate(base)
    candidates = request.candidates
    rows = []
    if not candidates:
        guidance = scientific_conditions(parameters)
        reference = guidance['reference_temperature_c']
        if parameters.temperature_c is None and reference is not None:
            modified = dict(base, temperature_c=reference)
            assumptions = dict(parameters.assumptions)
            assumptions['temperature_c'] = {'value': reference, 'provenance': 'SCENARIO_ASSUMPTION',
                'evidence': guidance['reference_scope'], 'source': 'fao_environment',
                'warning': 'Literature illustration only; not a validated operating setpoint.'}
            modified['assumptions'] = assumptions
            rows.append({'parameters': ProcessParameters.model_validate(modified), 'label': 'Literature reference study',
                         'assumptions': assumptions, 'rationale': guidance['reference_scope']})
        else:
            rows.append({'parameters': parameters, 'label': request.label, 'assumptions': parameters.assumptions,
                         'rationale': 'Calculation from entered parameters; unknown inputs remain unknown.'})
        return rows
    for candidate in candidates:
        merged = {**base, **candidate.overrides}
        material_changed=candidate.overrides.get('material',base['material'])!=base['material']
        composition_changed='mixture_components' in candidate.overrides and candidate.overrides['mixture_components']!=base['mixture_components']
        pretreatment_changed='pretreatment' in candidate.overrides and candidate.overrides['pretreatment']!=base['pretreatment']
        if material_changed or composition_changed or pretreatment_changed:
            # Base laboratory composition/BMP cannot silently transfer to another material or treatment.
            for field in ['bmp_ml_ch4_g_vs','bmp_unit','bmp_evidence','bmp_provenance','c_vs_sub_m','c_vs_sub_f','c_vs_inoc','ISR']:
                if field not in candidate.overrides: merged[field]=None
            if material_changed or composition_changed:
                for field in ['vs_mass_kg','vs_percent','ts_percent','vs_basis','density_kg_l']:
                    if field not in candidate.overrides:merged[field]=None
        assumptions = dict(parameters.assumptions)
        for field, value in candidate.overrides.items():
            assumptions[field] = {'value': value, 'provenance': 'SCENARIO_ASSUMPTION', 'evidence': candidate.rationale}
        merged['assumptions'] = assumptions
        rows.append({'parameters': ProcessParameters.model_validate(merged), 'label': candidate.label,
                     'assumptions': assumptions, 'rationale': candidate.rationale})
    return rows
