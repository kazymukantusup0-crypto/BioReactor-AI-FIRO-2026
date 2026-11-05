"""Bounded public downloads, robots checks, explicit parser failures, no access bypass."""
import csv
from html.parser import HTMLParser
import hashlib
import io
import json
import re
from urllib.parse import urlsplit,urljoin,quote,urlunsplit
import urllib.error
import urllib.request
import urllib.robotparser
from src.market.domain import PriceInput,SourceInput
from src.market.tls import verified_context

USER_AGENT='BioReactorMarket/3.0'


class SourceError(RuntimeError): pass


def public_get(url,check_robots=True):
    parts=urlsplit(url)
    if parts.scheme!='https' or not parts.hostname or parts.username or parts.password:
        raise SourceError('Only public HTTPS sources without URL credentials are supported')
    url=urlunsplit((parts.scheme,parts.netloc,quote(parts.path,safe='/%'),quote(parts.query,safe='=&%'),''))
    class SameOrigin(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,req,fp,code,msg,headers,newurl):
            target=urlsplit(newurl)
            if target.scheme!='https' or target.hostname!=parts.hostname:
                raise SourceError('Cross-origin redirect requires a separately configured source')
            return super().redirect_request(req,fp,code,msg,headers,newurl)
    opener=urllib.request.build_opener(SameOrigin(),urllib.request.HTTPSHandler(context=verified_context()))
    def read(target):
        req=urllib.request.Request(target,headers={'User-Agent':USER_AGENT})
        with opener.open(req,timeout=15) as response:
            data=response.read(4*1024*1024+1)
        if len(data)>4*1024*1024: raise SourceError('Source document too large')
        return data
    try:
        if check_robots:
            robots_url=urljoin(url,'/robots.txt')
            try: robots_data=read(robots_url).decode('utf-8',errors='replace')
            except urllib.error.HTTPError as exc:
                if exc.code==404: robots_data=''
                else: raise
            robots=urllib.robotparser.RobotFileParser()
            robots.parse(robots_data.splitlines())
            if not robots.can_fetch(USER_AGENT,url): raise SourceError('robots.txt does not allow this download')
        data=read(url)
        if len(data)<10000 and re.search(rb'captcha|access denied|cloudflare challenge',data,re.I):
            raise SourceError('Access challenge; use manual import, no bypass attempted')
        return data
    except (urllib.error.URLError,OSError) as exc:
        raise SourceError(f'Download failed: {exc}') from None


class TextParser(HTMLParser):
    def __init__(self): super().__init__();self.parts=[];self.skip=0
    def handle_starttag(self,tag,attrs):
        if tag in {'script','style'}: self.skip+=1
    def handle_endtag(self,tag):
        if tag in {'script','style'} and self.skip: self.skip-=1
    def handle_data(self,data):
        if not self.skip:self.parts.append(data)


MONTHS={'января':1,'февраля':2,'марта':3,'апреля':4,'мая':5,'июня':6,'июля':7,'августа':8,'сентября':9,'октября':10,'ноября':11,'декабря':12}


def parse_esalmaty(data,source):
    html=data.decode('utf-8')
    parser=TextParser();parser.feed(html)
    text=re.sub(r'\s+',' ',' '.join(parser.parts))
    pattern=r'С\s+(\d{1,2})\s+([а-я]+)\s+(20\d{2})\s+года.{0,400}?небытовых нужд.{0,100}?тарифы:\s*([\d]+[,.]\d{2})\s+тенге\s+с НДС\s+([\d]+[,.]\d{2})\s+тенге\s+без НДС.{0,250}?\(2 группа\)'
    matches=re.findall(pattern,text,re.I)
    if not matches or len(set(matches))!=1: raise SourceError('Electricity page schema/date/group changed; review required')
    day,month,year,vat,net=matches[0]
    if month.lower() not in MONTHS:raise SourceError('Unknown month')
    effective=f'{year}-{MONTHS[month.lower()]:02d}-{int(day):02d}'
    publication=re.search(r'(?:datePublished["\s:]+|property=["\']article:published_time["\']\s+content=["\'])(\d{4}-\d{2}-\d{2})',html)
    published=publication.group(1) if publication else None
    evidence=f'Небытовые потребители, группа 2; с НДС. Действует с {effective}. Publication date '+('found' if published else 'not stated')+'. Document SHA256 '+hashlib.sha256(data).hexdigest()
    is_test=source.get('config',{}).get('test_mode') is True
    return [PriceInput(source_id=source['id'],commodity='electricity',region=region,country='KZ',value=vat.replace(',','.'),currency='KZT',unit='kWh',published_at=published,
        effective_from=effective,price_type='tariff',reliability='test' if is_test else 'verified_official',is_test=is_test,consumer_class='non_household_group2',tax_basis='VAT_included',source_url=source['url'],acquisition_method='https_html',evidence=('TEST parser fixture. ' if is_test else '')+evidence)
        for region in ['KZ-Almaty','KZ-Almaty-oblast']]


def parse_csv(text,source_id=None):
    reader=csv.DictReader(io.StringIO(text.lstrip('\ufeff')))
    rows=[]
    for row in reader:
        d={k:v for k,v in row.items() if v!=''}
        if source_id: d['source_id']=source_id
        rows.append(PriceInput.model_validate(d))
        if len(rows)>10000: raise ValueError('CSV row limit exceeded')
    if not rows:raise ValueError('Nonempty price CSV required')
    return rows


def fetch_source(source):
    if source['adapter']=='manual':raise SourceError('Manual source; provide a verified CSV or API observation')
    if source['adapter'] in {'bns_retail_xlsx','karaganda_supply','krec_supply'}:
        from src.market.official import fetch_official
        return fetch_official(source)
    payload=public_get(source['url'])
    if source['adapter']=='esalmaty':return parse_esalmaty(payload,source),payload
    if source['adapter']=='csv':
        rows=parse_csv(payload.decode('utf-8-sig'),source['id'])
        status='verified_manual' if source.get('config',{}).get('reviewed_schema') is True else 'unverified'
        rows=[p.model_copy(update={'acquisition_method':'https_csv'}) if p.is_test else p.model_copy(update={'reliability':status,'acquisition_method':'https_csv'}) for p in rows]
        return rows,payload
    raise SourceError('Adapter not configured')


DEFAULT_SOURCES=[
    {'id':'esalmaty_business','name':'АО Алатау Жарық Компаниясы — Энергосбыт, небытовая группа 2','url':'https://www.esalmaty.kz/ru/business-tariffs','category':'electricity','adapter':'esalmaty'},
    {'id':'qazaqgaz_aimaq','name':'QazaqGaz Aimaq: regional natural-gas schedules (Word attachment; manual review)','url':'https://www.aimaq.kz/ru/тарифы-и-цены/tarify-i-czeny-2026/','category':'natural_gas','adapter':'manual'},
    {'id':'organic_verified_manual','name':'Органические удобрения: проверенные предложения или договоры пользователя','url':'manual://organic_fertilizer','category':'organic_fertilizer','adapter':'manual'},
    {'id':'mineral_verified_manual','name':'Минеральные удобрения: проверенные предложения или договоры пользователя','url':'manual://mineral_fertilizer','category':'mineral_fertilizer','adapter':'manual'},
    {'id':'feedstock_verified_manual','name':'Органическое сырьё: проверенные предложения или договоры пользователя','url':'manual://organic_feedstock','category':'organic_feedstock','adapter':'manual'},
]


def bootstrap(store):
    from src.market.official import SOURCES
    known={s['id'] for s in store.sources()}
    for source in DEFAULT_SOURCES+SOURCES:
        if source['id'] not in known:store.add_source(source)
