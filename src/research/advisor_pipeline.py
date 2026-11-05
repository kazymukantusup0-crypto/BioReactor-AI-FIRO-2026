"""Scoped review stages and topic discovery; LLM cannot approve numerical data."""
from urllib.parse import urlencode
import json,re
from src.research.research_cache import ResearchCache
from src.research.source_validator import download
STAGES=['DISCOVERED','METADATA_VERIFIED','FULL_TEXT_REVIEWED','NUMERIC_DATA_VERIFIED','APPROVED_FOR_ESTIMATION']
TOPICS={'co_digestion','temperature','retention','OLR','BMP','stability','inhibition','CN'}
def advance(record,target,review):
    old=record.get('verification_stage','DISCOVERED')
    if target not in STAGES or STAGES.index(target)!=STAGES.index(old)+1:raise ValueError('Review stages must advance one step at a time')
    if not review.get('reviewer') or not review.get('evidence'):raise ValueError('Review evidence and reviewer required')
    if target=='METADATA_VERIFIED' and not (record.get('title') and record.get('authors') and record.get('year') and re.fullmatch(r'10\.\d{4,9}/\S+',record.get('doi',''))):raise ValueError('Verified bibliographic metadata required')
    if target=='NUMERIC_DATA_VERIFIED' and not all(review.get(k) for k in ['units_checked','material_checked','conditions_checked','locator']):raise ValueError('Numerical units/material/conditions/locator must be checked')
    if target=='APPROVED_FOR_ESTIMATION' and not (review.get('approved_scope') and review.get('manual_review')):raise ValueError('A scoped explicit review, not an LLM proposal, is required')
    return {**record,'verification_stage':target,'reviews':record.get('reviews',[])+[review]}

def discover(evidence,materials,topics,online=False,fetcher=None):
    from src.advisor.catalog import name,document
    if not set(topics)<=TOPICS:raise ValueError('Unsupported scientific search topic')
    curated=[s for s in document()['sources'] if not s.get('conditions',{}).get('materials') or set(materials)&set(s['conditions']['materials'])]
    result={'curated':curated,'discovered':[],'topics':topics,'network_status':'not_requested'}
    key='advisor-search:'+','.join(sorted(materials))+':'+','.join(sorted(topics));cache=ResearchCache(evidence);prior=cache.get(key,168)
    if prior and not prior['stale']:return {**result,'discovered':prior['data'],'network_status':'cached_metadata','cache_age_hours':prior['age_hours']}
    if not online:return {**result,'discovered':prior['data'] if prior else [],'network_status':'offline_cache' if prior else 'not_requested'}
    failure=cache.get(key+':failure',1)
    if failure and not failure['stale']:return {**result,'network_status':'backoff_after_source_error'}
    query=' '.join(name(m,'en') for m in materials)+' anaerobic digestion '+' '.join(topics)
    url='https://api.crossref.org/works?'+urlencode({'query.bibliographic':query,'rows':5,'select':'DOI,title,author,published,URL'})
    try:
        items=json.loads(download(url,evidence,fetcher))['message']['items'];rows=[]
        for x in items:
            rows.append({'doi':x.get('DOI'),'title':(x.get('title') or [''])[0],'authors':x.get('author',[]),'published':x.get('published'),'url':x.get('URL'),
                         'verification_stage':'DISCOVERED','numeric_use_allowed':False,'metadata_note':'Crossref discovery is not independent identity/material/full-text verification'})
        cache.put(key,rows);return {**result,'discovered':rows,'network_status':'success'}
    except Exception as exc:
        cache.put(key+':failure',{'error':type(exc).__name__});return {**result,'network_status':'unavailable','discovered':prior['data'] if prior else []}
