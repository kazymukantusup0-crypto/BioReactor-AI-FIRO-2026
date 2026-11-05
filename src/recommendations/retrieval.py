"""Offline, source-bound scientific claims; operator-reviewed extensions are append-only."""
from datetime import date
import hashlib
import json
import re
import math
from typing import Literal
from pydantic import Field,model_validator
from src.agent.dialogue_types import Strict
from src.data.prepare import ROOT
from src.market.domain import market_today
from src.recommendations.knowledge import load_knowledge


class Publication(Strict):
    id:str=Field(pattern=r'^[a-z0-9_-]{1,80}$')
    title:str=Field(min_length=4,max_length=500)
    url:str=Field(pattern=r'^https://',max_length=2000)
    year:int=Field(ge=1800,le=2100)
    doi:str|None=None
    locator:str=Field(min_length=4,max_length=1000)
    reviewed_by:str=Field(min_length=4,max_length=200)
    verified_on:date
    provenance:Literal['SOURCE_VERIFIED']='SOURCE_VERIFIED'

    @model_validator(mode='after')
    def check(self):
        if self.verified_on>market_today() or self.year>market_today().year:raise ValueError('Verification/publication date in the future')
        if self.doi is not None and not re.fullmatch(r'10\.\d{4,9}/\S+',self.doi):raise ValueError('Invalid DOI syntax')
        return self


class Claim(Strict):
    id:str=Field(pattern=r'^[a-z0-9_-]{1,80}$')
    source_id:str
    topics:list[str]=Field(min_length=1,max_length=10)
    materials:list[str]=Field(min_length=1,max_length=30)
    category:str
    process_type:str
    values:list[float]=Field(default_factory=list,max_length=20)
    unit:str|None=None
    scope:str=Field(min_length=10,max_length=1500)
    text:dict[str,str]

    @model_validator(mode='after')
    def localized(self):
        if not {'ru','en','kk'}<=set(self.text):raise ValueError('Reviewed ru/en/kk statements required')
        if any(not 1<=len(value)<=2000 for value in self.text.values()):raise ValueError('Invalid claim text size')
        for statement in self.text.values():
            literals=[float(n.replace(',','.')) for n in re.findall(r'(?<![\w])\d+(?:[.,]\d+)?',statement)]
            if any(not any(math.isclose(n,value,rel_tol=1e-9,abs_tol=1e-9) for value in self.values) for n in literals):
                raise ValueError('Every numerical claim must be declared in values with units and source scope')
        return self


class Document(Strict):
    version:str
    sources:list[Publication]=Field(min_length=1,max_length=30)
    claims:list[Claim]=Field(min_length=1,max_length=200)

    @model_validator(mode='after')
    def references(self):
        ids={s.id for s in self.sources}
        if len(ids)!=len(self.sources) or len({c.id for c in self.claims})!=len(self.claims):raise ValueError('Duplicate source/claim ID')
        if any(c.source_id not in ids for c in self.claims):raise ValueError('Claim source missing')
        return self


def documents():
    paths=[ROOT/'data/knowledge/claims_v5_6.json',*sorted((ROOT/'data/knowledge/imported').glob('*.json'))]
    return [Document.model_validate_json(path.read_text(encoding='utf-8')) for path in paths]


def import_document(path):
    raw=path.read_bytes()
    if len(raw)>1024*1024:raise ValueError('Scientific document exceeds 1 MiB')
    doc=Document.model_validate_json(raw)
    existing=documents();source_ids={s.id for d in existing for s in d.sources};claim_ids={c.id for d in existing for c in d.claims}
    digest=hashlib.sha256(raw).hexdigest();dest=ROOT/'data/knowledge/imported'/f'{digest}.json'
    if dest.exists():return {'status':'duplicate','sha256':digest}
    if any(s.id in source_ids for s in doc.sources) or any(c.id in claim_ids for c in doc.claims):raise ValueError('IDs already exist; preserve published source versions')
    dest.parent.mkdir(exist_ok=True)
    with dest.open('x',encoding='utf-8') as file:file.write(doc.model_dump_json(indent=2))
    return {'status':'imported','sha256':digest,'sources':len(doc.sources),'claims':len(doc.claims),'verification':'Operator review assertion, not automatic verification of scientific truth'}


def topics_for(text):
    patterns={'temperature':r'температур|temperature|градус|degree','ph':r'\bph\b|кислот|қышқыл',
        'retention':r'удерж|hrt|retention|ұстау','loading':r'нагруз|загруз|loading|жүктеме','bmp':r'\bbmp\b|бмп|метан|methane',
        'low_gas':r'сниз|мало\s+газ|low\s+gas|decreas|газ.*аз','process':r'процесс|режим|process|digest|сбраж|ашыту'}
    return [topic for topic,pattern in patterns.items() if re.search(pattern,text,re.I)]


def retrieve(query,material=None,topics=None,category=None,process_type=None):
    from src.agent.nlu import material_of
    from src.agent.dialogue_types import DialogueState
    material=material or material_of(query,DialogueState())[0]
    topics=topics or topics_for(query)
    source_map={s.id:s.model_dump(mode='json') for doc in documents() for s in doc.sources}
    claims=[]
    for doc in documents():
        for claim in doc.claims:
            if material and material not in claim.materials:continue
            if not material and not topics:continue
            if topics and not set(topics)&set(claim.topics):continue
            if category and claim.category!=category:continue
            if process_type and process_type.casefold() not in claim.process_type.casefold():continue
            claims.append(claim.model_dump(mode='json'))
    ids=list(dict.fromkeys(c['source_id'] for c in claims))
    # Dataset/soil references remain available even where no operational claim exists.
    legacy=load_knowledge();key='manure_unspecified' if material=='manure' else material
    for source_id in legacy['materials'].get(key,{}).get('sources',[]):
        if source_id not in ids:ids.append(source_id)
    if 'bmp' in topics and material in legacy['materials'] and 'hafner' in legacy['materials'][material].get('sources',[]):ids.append('hafner')
    sources=[]
    for source_id in dict.fromkeys(ids):
        record=source_map.get(source_id) or dict(id=source_id,**legacy['sources'][source_id])
        year=re.search(r'\b(?:19|20)\d{2}\b',record['title'])
        record.setdefault('year',int(year.group()) if year else None)
        record.setdefault('doi',None);record.setdefault('provenance','SOURCE_VERIFIED')
        sources.append(record)
    return {'status':'ok','search_mode':'structured_verified_local_catalogue','live_web_search':False,
        'query':query,'material':material,'topics':topics,'claims':claims,'sources':sources,
        'message':'Найдены проверенные локальные публикации и утверждения с областью применимости.' if sources else 'В проверенной локальной базе применимых публикаций не найдено.'}
