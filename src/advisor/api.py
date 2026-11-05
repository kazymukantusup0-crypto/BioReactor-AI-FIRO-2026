from fastapi import APIRouter,Query
from src.advisor.schemas import AdvisorRequest,ComparisonRequest,ConversionRequest,MixtureSave,MixtureHandoff
from src.advisor.catalog import get_catalog
from src.advisor.service import analyze
from src.advisor.optimization import compare
from src.research.evidence_store import EvidenceStore
def create_router(store):
    router=APIRouter(prefix='/api/advisor',tags=['Substrate Advisor v8.1']);evidence=EvidenceStore(store)
    from src.advisor import library
    library.initialize(store)
    @router.get('/mixtures')
    def mixtures():return library.listing(store)
    @router.post('/mixtures',status_code=201)
    def save(body:MixtureSave):return library.save(store,body)
    @router.get('/mixtures/{identifier}')
    def load(identifier:str,revision:int|None=Query(default=None,ge=1)):return library.load(store,identifier,revision)
    @router.post('/handoff',status_code=201)
    def handoff(body:MixtureHandoff):return library.handoff(store,body)
    @router.get('/catalog')
    def catalog():return get_catalog()
    @router.get('/research/dossiers')
    def dossiers(material:str|None=None):
        from src.research.dossiers import search
        return search([material] if material else None)
    @router.get('/research/compare')
    def compare_studies(material:str):
        from src.research.dossiers import compare
        return compare([material])
    @router.post('/analyze')
    def run(body:AdvisorRequest):return analyze(store,body)
    @router.post('/compare')
    def comparison(body:ComparisonRequest):return compare(store,body)
    @router.post('/convert')
    def conversion(body:ConversionRequest):
        from src.advisor.advanced_science import run
        return run('convert_substrate_units',{'advisor_request':body.request.model_dump(mode='json'),'target_unit':body.target_unit})
    @router.get('/runs')
    def history():return {'runs':evidence.records('advisor_run')}
    return router
