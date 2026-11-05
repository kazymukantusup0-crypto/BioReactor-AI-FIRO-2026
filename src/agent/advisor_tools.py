"""Read-only advisor tools with a typed boundary independent of the legacy context."""
ADVISOR_TOOLS=['get_substrate_catalog','analyze_substrate_mixture','compare_substrate_mixtures']

def execute_tool(name,context,store):
    if name=='get_substrate_catalog':
        from src.advisor.catalog import get_catalog
        return {**get_catalog(),'status':'ok','message':'Recognized names and approved numerical profiles are counted separately.'}
    if name=='analyze_substrate_mixture':
        from src.advisor.service import analyze
        return {**analyze(store,context.get('advisor_request',context)),'message':'Component mass balance and conditional literature references; no measured mixture yield or operating approval.'}
    from src.advisor.optimization import compare
    return {**compare(store,context.get('comparison_request',context)),'message':'Availability-constrained scenarios; no validated optimum.'}
