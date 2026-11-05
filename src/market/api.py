"""Loopback FastAPI service; SQLite remains usable when the internet is absent."""
import asyncio
from contextlib import asynccontextmanager
import os
import sqlite3
from datetime import date
from fastapi import FastAPI,HTTPException,Query,Request
from fastapi.responses import JSONResponse
from pydantic import Field,ValidationError
from src.market.domain import PriceInput,SourceInput,StrictModel,CATEGORIES
from src.market.store import Store
from src.market.adapters import bootstrap,parse_csv
from src.market.scenarios import ScenarioInput,compare
from src.market.service import price_changes,recommendation_change
from src.market.updater import Updater,scheduler


class CSVInput(StrictModel):
    csv_text:str=Field(min_length=1,max_length=2*1024*1024)


def manual_observation(price):
    updates={'acquisition_method':'manual_pdf' if price.acquisition_method=='manual_pdf' else 'manual'}
    if price.reliability=='verified_official':updates['reliability']='verified_manual'
    return price.model_copy(update=updates)


def create_app(store=None,scheduler_enabled=None,interval=None):
    db=store or Store();bootstrap(db)
    interval=float(interval if interval is not None else os.getenv('BIOREACTOR_MARKET_INTERVAL_SECONDS','86400'))
    enabled=scheduler_enabled if scheduler_enabled is not None else os.getenv('BIOREACTOR_MARKET_SCHEDULER','1')=='1'
    if interval<5:raise ValueError('Interval must be at least 5 seconds')
    updater=Updater(db,interval=interval)

    @asynccontextmanager
    async def lifespan(app):
        stop=asyncio.Event()
        task=asyncio.create_task(scheduler(updater,stop,interval)) if enabled else None
        runtime=getattr(app.state,'agent_runtime',None)
        if runtime:runtime.start()
        try:yield
        finally:
            if runtime:runtime.stop()
            stop.set()
            if task is not None:await task

    app=FastAPI(title='BioReactor AI Market Intelligence',version='3.5',lifespan=lifespan)
    app.state.store=db;app.state.updater=updater

    @app.middleware('http')
    async def loopback_origin(request,call_next):
        # No CORS opt-in; reject browser requests originating from unrelated sites.
        origin=request.headers.get('origin')
        from urllib.parse import urlsplit
        if origin and urlsplit(origin).hostname not in {'127.0.0.1','localhost','::1'}:
            return JSONResponse(status_code=403,content={'detail':'Local origins only'})
        return await call_next(request)

    @app.exception_handler(ValueError)
    async def bad_input(request,exc):return JSONResponse(status_code=422,content={'detail':str(exc)})
    @app.exception_handler(sqlite3.IntegrityError)
    async def conflict(request,exc):return JSONResponse(status_code=409,content={'detail':str(exc)})

    @app.get('/health')
    def health():return {'status':'ok','database':str(db.path),'scheduler_enabled':enabled,'interval_seconds':interval,'market':'KZ','price_forecasting':False}

    @app.get('/catalog')
    def catalog():
        with db.connect() as con:
            return {'categories':CATEGORIES,'commodities':[dict(r) for r in con.execute('SELECT * FROM commodities')],
                'regions':[dict(r) for r in con.execute('SELECT * FROM regions')]}

    @app.get('/sources')
    def sources():return db.sources()

    @app.get('/sources/status')
    def source_status():return {'states':db.source_states()}

    @app.post('/sources',status_code=201)
    def add_source(source:SourceInput):return db.add_source(source)

    @app.get('/prices/current')
    def current(region:str|None=None,commodity:str|None=None,max_age_days:int=Query(30,ge=0,le=3650)):
        return {'label':'latest_known_not_necessarily_current','prices':db.prices(commodity,region,max_age_days=max_age_days,latest=True)}

    @app.get('/prices/history')
    def history(commodity:str,region:str,start:date|None=None,end:date|None=None,limit:int=Query(1000,ge=1,le=5000)):
        if start and end and start>end:raise ValueError('start must not exceed end')
        rows=db.prices(commodity,region,start=start.isoformat() if start else None,end=end.isoformat() if end else None)
        return {'prices':rows[:limit],'total':len(rows),'truncated':len(rows)>limit}

    @app.get('/analytics/price-change')
    def change(commodity:str,region:str,start:date|None=None,end:date|None=None,as_of:date|None=None):
        if start and end and start>end:raise ValueError('start must not exceed end')
        return {'series':price_changes(db.prices(commodity,region,start=start.isoformat() if start else None,end=end.isoformat() if end else None),as_of=as_of)}

    @app.post('/prices',status_code=201)
    def price(observation:PriceInput):return db.import_prices([manual_observation(observation)])

    @app.post('/prices/import-csv')
    def import_csv(body:CSVInput):return db.import_prices([manual_observation(p) for p in parse_csv(body.csv_text)])

    @app.get('/updates')
    def logs():return db.updates()

    @app.post('/updates')
    def update(category:str|None=None):
        if category and category not in CATEGORIES:raise ValueError('Unknown category')
        return updater.update_category(category) if category else updater.update_all()

    @app.post('/scenarios/compare')
    def scenarios(body:ScenarioInput):return compare(db,body)

    @app.get('/scenarios')
    def scenario_history():return db.scenarios()

    @app.get('/scenarios/{identifier}')
    def scenario(identifier:int):
        rows=db.scenarios(identifier)
        if not rows:raise HTTPException(404,'Scenario not found')
        return rows[0]

    @app.get('/scenarios/{identifier}/price-impact')
    def price_impact(identifier:int):
        try:return recommendation_change(db,identifier)
        except LookupError as exc:raise HTTPException(404,str(exc)) from None

    from src.dashboard.api import create_router
    from src.data.prepare import ROOT
    from fastapi.staticfiles import StaticFiles
    dashboard_router=create_router(db)
    app.state.agent_runtime=dashboard_router.agent_runtime
    app.include_router(dashboard_router)
    from src.optimizer.api import create_router as process_router
    app.include_router(process_router(db))
    from src.research.api import create_router as research_router
    app.include_router(research_router(db))
    from src.advisor.api import create_router as advisor_router
    app.include_router(advisor_router(db))
    if (ROOT/'frontend/dist/index.html').is_file():
        app.mount('/dashboard',StaticFiles(directory=ROOT/'frontend/dist',html=True),name='dashboard')
    return app
