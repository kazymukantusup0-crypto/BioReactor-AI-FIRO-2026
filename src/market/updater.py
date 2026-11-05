import asyncio
import hashlib
import json
import logging
import threading
import os
from src.market.domain import utcnow
from src.market.adapters import bootstrap,fetch_source
from src.market.domain import CATEGORIES

log=logging.getLogger('bioreactor.market')


class Updater:
    def __init__(self,store,fetcher=fetch_source,interval=None):
        self.store=store;self.fetcher=fetcher
        self.interval=float(interval if interval is not None else os.getenv('BIOREACTOR_MARKET_INTERVAL_SECONDS','86400'))
        if self.interval<5:raise ValueError('Source interval must be at least 5 seconds')

    def update_category(self,category):
        if category not in CATEGORIES:raise ValueError('Unknown category')
        owner=self.store.acquire(category)
        if owner is None:return {'category':category,'status':'already_running','inserted':0}
        stop=threading.Event()
        def heartbeat():
            while not stop.wait(30):
                if not self.store.renew(category,owner):return
        keeper=threading.Thread(target=heartbeat,daemon=True)
        keeper.start()
        output=[]
        try:
            for source in self.store.sources():
                if source['category']!=category or not source['enabled']:continue
                state=self.store.source_state(source['id'])
                if state and state.get('next_attempt_at') and state['next_attempt_at']>utcnow().isoformat():
                    output.append({'source':source['id'],'status':'rate_limited','inserted':0,'next_attempt_at':state['next_attempt_at']});continue
                identifier=self.store.log_start(source['id'],category)
                if source['adapter']=='manual':
                    self.store.log_finish(identifier,'needs_configuration',error='Manual import required; no automatic numeric price extraction')
                    self.store.defer_manual(source['id'],self.interval)
                    output.append({'source':source['id'],'status':'needs_configuration','inserted':0});continue
                try:
                    prices,payload=self.fetcher(source)
                    if not prices:raise ValueError('Source returned no validated prices')
                    raw=self.store.path.parent/'raw';raw.mkdir(exist_ok=True)
                    (raw/(hashlib.sha256(payload).hexdigest()+'.bin')).write_bytes(payload)
                    result=self.store.import_prices(prices)
                    self.store.finish_source(source['id'],True,self.interval)
                    self.store.log_finish(identifier,'success',result['inserted'])
                    output.append({'source':source['id'],'status':'success',**result})
                except Exception as exc:
                    message=f'{type(exc).__name__}: {exc}'
                    self.store.log_finish(identifier,'error',error=message)
                    self.store.finish_source(source['id'],False,self.interval,error=message)
                    log.warning('Source %s: %s',source['id'],message)
                    output.append({'source':source['id'],'status':'error','error':message,'inserted':0})
        finally:
            stop.set();keeper.join(timeout=3)
            self.store.release(category,owner)
        return {'category':category,'sources':output,'inserted':sum(r['inserted'] for r in output)}

    def update_all(self):return [self.update_category(c) for c in CATEGORIES]


async def scheduler(updater,stop,interval=86400):
    if interval<5:raise ValueError('Update interval must be at least 5 seconds')
    while not stop.is_set():
        await asyncio.to_thread(updater.update_all)
        # Lightweight minute ticks allow bounded backoff retries; successful
        # sources still perform network I/O only once per configured interval.
        try:await asyncio.wait_for(stop.wait(),timeout=min(interval,60))
        except asyncio.TimeoutError:pass
