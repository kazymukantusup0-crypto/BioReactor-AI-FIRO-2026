"""One public schema manifest over the existing read-only ToolRegistry."""
from src.agent.scientific_tools import DESCRIPTIONS

CAPABILITIES={
 'search_substrate_profiles':'scientific_profiles','analyze_substrate':'substrate_classification',
 'assess_substrate_potential':'ts_vs_bmp_methane_mixture_geometry',
 'assess_process_evidence':'temperature_process','estimate_process_energy':'heat_balance',
 'evaluate_partial_economics':'energy_economic_alternatives','analyze_economic_sensitivity':'sensitivity',
 'get_market_prices':'current_market','get_price_history':'historical_market',
 'assess_scientific_risks':'inhibition_risks','compare_scientific_studies':'study_comparison',
 'verify_scientific_calculations':'evidence_verification','verify_scientific_sources':'source_audit',
 'search_public_scientific_metadata':'literature_search','check_reactor_loading':'capacity',
 'calculate_dilution_plan':'target_dilution','calculate_vs_concentration':'vs_concentration',
 'predict_bmp':'preserved_ml_model','get_model_info':'model_limits','get_reactor_status':'sensor_status',
 'recover_local_scientific_analysis':'scientific_recovery','recover_partial_economics':'economic_recovery',
}
REQUIRES={name:['assess_substrate_potential'] for name in ['evaluate_partial_economics','check_reactor_loading','calculate_dilution_plan','verify_scientific_calculations']}
REQUIRES['analyze_economic_sensitivity']=['evaluate_partial_economics']
ARGUMENTS={'type':'object','properties':{'query':{'type':'string','maxLength':400},'topics':{'type':'array','maxItems':2,'items':{'type':'string','enum':['temperature','duration']}}},'additionalProperties':False}


def manifest(names=None):
    from src.agent.tools import TOOL_NAMES
    from src.agent.providers import TOOL_DESCRIPTIONS
    allowed=set(names or TOOL_NAMES)
    return [{'name':name,'description':DESCRIPTIONS.get(name,TOOL_DESCRIPTIONS.get(name,capability.replace('_',' '))),
             'capability':capability,'parameters':ARGUMENTS,'requires':REQUIRES.get(name,[]),'read_only':True}
            for name,capability in CAPABILITIES.items() if name in allowed and name in TOOL_NAMES]


def validate_arguments(arguments):
    from src.agent.providers import ProviderError
    if not isinstance(arguments,dict) or set(arguments)-{'query','topics'}:raise ProviderError('Tool argument schema rejected')
    if 'query' in arguments and (not isinstance(arguments['query'],str) or len(arguments['query'])>400):raise ProviderError('Retrieval query schema rejected')
    if 'topics' in arguments and (not isinstance(arguments['topics'],list) or len(arguments['topics'])>2 or any(t not in {'temperature','duration'} for t in arguments['topics'])):raise ProviderError('Topic schema rejected')
    return arguments
