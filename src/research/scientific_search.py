"""Crossref discovery supplies metadata, not automatically verified BMP values."""
import json
from urllib.parse import urlencode
from src.research.evidence_extractor import catalog
from src.research.source_validator import download
from src.research.research_cache import ResearchCache

SYNONYMS={'cattle_manure':['коровий навоз','навоз КРС','cattle manure','cow manure','cow dung','cattle slurry'],
          'swine_manure':['свиной навоз','swine manure','pig slurry'], 'poultry_manure':['птичий помёт','poultry manure'],
          'food_waste':['пищевые отходы','food waste']}
def search(evidence,material,online=False,fetcher=None):
    reviewed=[p for p in catalog()['profiles'] if p['material']==material]
    for p in reviewed:evidence.append('scientific_profile',p)
    result={'reviewed_profiles':reviewed,'synonyms':SYNONYMS.get(material,[]),'discovered':[],'network_status':'not_requested'}
    cache=ResearchCache(evidence);key='crossref:'+material;prior=cache.get(key,168)
    if prior and not prior['stale']:
        result.update(discovered=prior['data'],network_status='cached_metadata',cache_age_hours=prior['age_hours']);return result
    if not online:
        if prior:result.update(discovered=prior['data'],network_status='offline_stale_metadata',cache_age_hours=prior['age_hours'])
        return result
    cooldown=cache.get(key+':failure',1)
    if cooldown and not cooldown['stale']:
        return {**result,'network_status':'backoff_after_source_error','retry_after_hours':max(0,1-cooldown['age_hours']),'error':cooldown['data']['error']}
    if material not in SYNONYMS:return result
    url='https://api.crossref.org/works?'+urlencode({'query.bibliographic':SYNONYMS[material][-1]+' biochemical methane potential total volatile solids density','rows':5,'select':'DOI,title,author,published,URL'})
    try:
        payload=json.loads(download(url,evidence,fetcher));rows=[]
        for item in payload['message']['items']:
            rows.append({'doi':item.get('DOI'),'title':(item.get('title') or [''])[0],'authors':item.get('author',[]),'published':item.get('published'),'url':item.get('URL'),'verification_status':'DRAFT_METADATA_ONLY_NOT_FOR_CALCULATION'})
        cache.put(key,rows);result.update(discovered=rows,network_status='success')
    except Exception as exc:
        cache.put(key+':failure',{'error':type(exc).__name__})
        result.update(network_status='unavailable',error=type(exc).__name__)
        if prior:result.update(discovered=prior['data'],cache_age_hours=prior['age_hours'],network_status='offline_stale_metadata')
    return result
