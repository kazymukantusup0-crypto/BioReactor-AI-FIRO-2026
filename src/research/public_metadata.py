"""Bounded public literature metadata; never an automatic numerical profile."""
import json
import os
from datetime import datetime,timezone
from urllib.parse import urlencode,quote
from urllib.request import Request,urlopen
from src.research.dossiers import CORE_MATERIALS


def search(materials):
    if os.getenv('BIOREACTOR_RESEARCH_ONLINE','1')=='0':
        return {'status':'unavailable','message':'Online research is disabled; use the reviewed local corpus.', 'live_search_performed':False,'sources':[]}
    allowed=[m for m in materials if m in CORE_MATERIALS]
    if not allowed:
        return {'status':'needs_input','message':'Identify a supported material before public retrieval; private user text is never sent.', 'missing':['identified_material'],'sources':[],'live_search_performed':False}
    query='('+ ' OR '.join(m.replace('_',' ') for m in allowed[:2])+') AND (anaerobic digestion OR methane potential)'
    url='https://www.ebi.ac.uk/europepmc/webservices/rest/search?'+urlencode({'query':query,'format':'json','pageSize':3})
    try:
        from src.market.tls import verified_context
        with urlopen(Request(url,headers={'Accept':'application/json','User-Agent':'BioReactor-AI/8.5 scientific-metadata'}),timeout=5,context=verified_context()) as response:
            raw=response.read(512*1024+1)
        if len(raw)>512*1024:raise ValueError('Publication metadata exceeded bounded response size')
        payload=json.loads(raw)
        records=[]
        for r in payload.get('resultList',{}).get('result',[])[:3]:
            doi=r.get('doi');pmcid=r.get('pmcid')
            link='https://doi.org/'+quote(doi,safe='/') if doi else 'https://europepmc.org/article/'+quote(str(r.get('source','MED')),safe='')+'/'+quote(str(r.get('id','')),safe='')
            records.append({'title':str(r.get('title',''))[:500],'url':link,'doi':doi,'pmcid':pmcid,
                'year':r.get('pubYear'),'review_status':'UNREVIEWED_METADATA_ONLY','approved_for_calculation':False})
        return {'status':'ok','message':'Live publication metadata only; full texts and quantitative applicability are not verified. No new estimation profile created.',
                'sources':records,'query':query,'retrieved_at':datetime.now(timezone.utc).isoformat(),
                'live_search_performed':True,'numerical_profile_created':False}
    except Exception as exc:
        return {'status':'error','message':'Public metadata retrieval failed: '+type(exc).__name__+'. Reviewed local evidence remains available.',
                'error_type':type(exc).__name__,'sources':[],'live_search_performed':True,'numerical_profile_created':False}
