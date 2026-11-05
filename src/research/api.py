from fastapi import APIRouter
from src.research.evidence_store import EvidenceStore
from src.research.evidence_extractor import catalog
from src.research.orchestrator import research_and_estimate
from src.estimation.schemas import EstimateRequest

def create_router(store):
    evidence=EvidenceStore(store);router=APIRouter(prefix='/api/research',tags=['Research v7'])
    @router.get('/evidence')
    def reviewed():return catalog()
    @router.post('/estimate')
    def run(body:EstimateRequest):return research_and_estimate(store,body)
    @router.post('/decision')
    def decision(body:EstimateRequest):return research_and_estimate(store,body)
    @router.get('/runs')
    def runs():return {'runs':evidence.records('research_run')}
    @router.get('/offers')
    def offers():return {'offers':evidence.records('market_offer')}
    @router.get('/logs')
    def logs():return {'logs':evidence.logs()}
    return router
