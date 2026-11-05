"""A seller ask is retained separately from comparable purchase bids and tariffs."""
import hashlib,re,math
from src.market.adapters import TextParser,SourceError
from src.market.domain import utcnow
from src.research.source_validator import download
from src.research.research_cache import ResearchCache

URL='https://stroitaxi.kz/karaganda/catalog/stroitelnye-materialy/koroviy-navoz/'
def parse_manure(raw):
    parser=TextParser();parser.feed(raw.decode('utf-8'));text=re.sub(r'\s+',' ',' '.join(parser.parts))
    if 'Караганда' not in text or not re.search(r'Коровий\s+навоз',text,re.I):raise SourceError('Material/region changed; review required')
    values=re.findall(r'≈\s*([\d\s]+(?:[,.]\d+)?)\s*₸\s*/\s*тонна',text)
    if len(set(values))!=1:raise SourceError('Price/unit schema changed or ambiguous')
    value=float(values[0].replace(' ','').replace(',','.'))
    if not math.isfinite(value) or value<=0:raise SourceError('Nonfinite or nonpositive offer')
    return {'source_id':'stroitaxi-karaganda-cattle-manure','source_url':URL,'title':'Коровий навоз — Караганда',
            'commodity':'cattle_manure','region':'KZ-Karaganda','country':'KZ','value':value,'currency':'KZT','unit':'t',
            'normalized_value':value/1000,'normalized_unit':'KZT/kg','published_at':None,'received_at':utcnow().isoformat(),
            'price_type':'seller_ask','reliability':'UNDATED_APPROXIMATE_REFERENCE','is_current':False,'material_state':'unknown',
            'evidence':'Approximate catalog asking price; publication date, moisture, delivery, minimum lot and tax basis unspecified',
            'sha256':hashlib.sha256(raw).hexdigest()}

def search(evidence,material,region='KZ-Karaganda',online=False,fetcher=None):
    result={'offers':[],'status':'no_configured_comparable_offer','region':region,'missing':['confirmed_feedstock_purchase_bid','raw_biogas_purchase_quote'],
            'coverage':['cattle_manure','swine_manure','poultry_manure','organic_waste','digestate','electricity','natural_gas','biogas','heat'],
            'coverage_notice':'Only configured cattle manure catalog adapter; other categories use existing market store/manual import. Coverage does not imply live sources.'}
    if material!='cattle_manure' or region!='KZ-Karaganda':return result
    cache=ResearchCache(evidence);key='offer:'+material+':'+region;prior=cache.get(key)
    if prior and not prior['stale']:
        return {**result,'offers':[prior['data']],'status':'cached_undated_reference','cache_age_hours':prior['age_hours']}
    if online:
        cooldown=cache.get(key+':failure',1)
        if cooldown and not cooldown['stale']:
            return {**result,'offers':[prior['data']] if prior else [],'status':'backoff_after_source_error','cache_age_hours':prior['age_hours'] if prior else None,'stale':prior['stale'] if prior else True}
        owner=evidence.store.acquire('research-market:'+region)
        if owner:
            try:
                offer=parse_manure(download(URL,evidence,fetcher));evidence.append('market_offer',offer);cache.put(key,offer)
                return {**result,'offers':[offer],'status':'retrieved_undated_reference','cache_age_hours':0}
            except (SourceError,OSError,ValueError) as exc:
                result.update(status='source_unavailable',error=type(exc).__name__);cache.put(key+':failure',{'error':type(exc).__name__})
            finally:evidence.store.release('research-market:'+region,owner)
        else:result['status']='update_already_running'
    if prior:return {**result,'offers':[prior['data']],'status':'offline_stale_reference','cache_age_hours':prior['age_hours'],'stale':True}
    return result
