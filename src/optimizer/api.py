"""Local optimizer and scientific notebook endpoints, additive to the legacy API."""
from typing import Literal
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import Field, model_validator
from src.optimizer.schemas import ProcessRequest, Objective, Strict
from src.optimizer import storage
from src.optimizer import experiment_lab as lab


class CompareInput(Strict):
    scenario_ids: list[str] = Field(min_length=2, max_length=20)
    objectives: list[Objective] | None = Field(default=None, max_length=6)

    @model_validator(mode='after')
    def distinct(self):
        if len(set(self.scenario_ids)) != len(self.scenario_ids):
            raise ValueError('Select at least two distinct saved optimization runs')
        if self.objectives is not None and len(set(self.objectives)) != len(self.objectives):
            raise ValueError('Objectives must be distinct')
        return self


def create_router(store):
    storage.initialize(store)
    router = APIRouter(tags=['Process Optimizer and Experiment Lab'])

    def found(function, *args, **kwargs):
        try:
            return function(*args, **kwargs)
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from None

    @router.post('/api/process/optimize', status_code=201)
    def optimize(body: ProcessRequest):
        from src.optimizer.service import optimize as calculate
        result = calculate(store, body)
        return storage.save_run(store, body, result)

    @router.get('/api/process/scenarios')
    def scenarios(limit: int = Query(100, ge=1, le=500)):
        return {'scenarios': storage.list_runs(store, limit), 'record_type': 'optimization_run'}

    @router.get('/api/process/scenarios/{identifier}')
    def scenario(identifier: str):
        return found(storage.get_run, store, identifier)

    @router.post('/api/process/compare')
    def compare(body: CompareInput):
        from src.optimizer.ranking import compare_results
        candidates = []
        for identifier in body.scenario_ids:
            run = found(storage.get_run, store, identifier)
            for item in run['result'].get('scenarios', []):
                candidates.append({**item, 'scenario_id': identifier + ':' + str(item['scenario_id']),
                                   'saved_run_id': identifier})
        comparison=compare_results(candidates, body.objectives)
        return {**comparison,'scenarios':candidates,'comparison':comparison,'scientific_sources':list({s['url']:s for c in candidates for s in c.get('scientific_sources',[]) if s.get('url')}.values()),'actuator_access':False}

    @router.get('/api/experiments/schema')
    def experiment_schema():
        return {'experiment': lab.ExperimentInput.model_json_schema(),
                'measurement': lab.MeasurementInput.model_json_schema(), 'auto_training_enabled': False}

    @router.post('/api/experiments', status_code=201)
    def create_experiment(body: lab.ExperimentInput):
        return lab.create_experiment(store, body)

    @router.get('/api/experiments')
    def experiments(origin: Literal['user', 'laboratory'] | None = None, include_archived: bool = False,
                    limit: int = Query(100, ge=1, le=500)):
        return {'experiments': lab.list_experiments(store, origin, include_archived, limit),
                'auto_training_enabled': False}

    @router.get('/api/experiments/{identifier}')
    def experiment(identifier: str):
        return found(lab.get_experiment, store, identifier)

    @router.patch('/api/experiments/{identifier}')
    def update_experiment(identifier: str, body: lab.ExperimentPatch):
        return found(lab.update_experiment, store, identifier, body)

    @router.post('/api/experiments/{identifier}/archive')
    def archive(identifier: str):
        return found(lab.archive_experiment, store, identifier)

    @router.get('/api/experiments/{identifier}/revisions')
    def revisions(identifier: str):
        return {'revisions': found(lab.revisions, store, identifier)}

    @router.post('/api/experiments/{identifier}/measurements', status_code=201)
    def measurement(identifier: str, body: lab.MeasurementInput):
        return found(lab.add_measurement, store, identifier, body)

    @router.get('/api/experiments/{identifier}/measurements')
    def measurements(identifier: str, limit: int = Query(5000, ge=1, le=5000)):
        rows = found(lab.measurements, store, identifier, limit)
        with store.connect() as con:
            total = con.execute('SELECT COUNT(*) FROM experiment_measurements WHERE experiment_id=?', (identifier,)).fetchone()[0]
        return {'measurements': rows, 'total': total, 'truncated': len(rows) < total}

    @router.get('/api/experiments/{identifier}/comparison')
    def comparison(identifier: str):
        return found(lab.comparison, store, identifier)

    @router.get('/api/experiments/{identifier}/export.csv')
    def export(identifier: str):
        content = found(lab.csv_export, store, identifier)
        return Response(content='\ufeff' + content, media_type='text/csv; charset=utf-8',
                        headers={'Content-Disposition': 'attachment; filename="experiment.csv"'})

    return router
