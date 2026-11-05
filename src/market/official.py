"""Audited primary-source mappings; statistics remain reference prices."""
import calendar
from datetime import date
from decimal import Decimal,InvalidOperation
import hashlib
from html.parser import HTMLParser
import io
import json
import re
from urllib.parse import urljoin
import zipfile
import openpyxl
from src.market.adapters import public_get,TextParser,MONTHS,SourceError
from src.market.domain import PriceInput,market_today


class Links(HTMLParser):
    def __init__(self):super().__init__();self.href=None;self.text=[];self.links=[]
    def handle_starttag(self,tag,attrs):
        if tag=='a':self.href=dict(attrs).get('href');self.text=[]
    def handle_data(self,data):
        if self.href:self.text.append(data)
    def handle_endtag(self,tag):
        if tag=='a' and self.href:self.links.append((self.href,' '.join(self.text)));self.href=None


class RussianText(HTMLParser):
    def __init__(self):super().__init__();self.stack=[];self.parts=[]
    def handle_starttag(self,tag,attrs):
        if tag in {'br','img','input','meta','link','hr','source','wbr'}:return
        self.stack.append((tag,(self.stack[-1][1] if self.stack else False) or dict(attrs).get('lang')=='kk' or tag in {'script','style'}))
    def handle_endtag(self,tag):
        for i in range(len(self.stack)-1,-1,-1):
            if self.stack[i][0]==tag:del self.stack[i:];break
    def handle_data(self,data):
        if not self.stack or not self.stack[-1][1]:self.parts.append(data)


def text(data):
    p=RussianText();p.feed(data.decode('utf-8'));return re.sub(r'\s+',' ',' '.join(p.parts)).strip()


def archive(documents):
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as out:
        manifest=[]
        for i,(url,payload) in enumerate(documents):
            name=f'document_{i}.bin';out.writestr(name,payload)
            manifest.append({'url':url,'file':name,'sha256':hashlib.sha256(payload).hexdigest()})
        out.writestr('manifest.json',json.dumps(manifest,ensure_ascii=False))
    return buffer.getvalue()


def label_test(source,records):
    if source.get('config',{}).get('test_mode') is True:
        return [p.model_copy(update={'is_test':True,'reliability':'test','evidence':'TEST fictitious parser document. '+p.evidence}) for p in records]
    return records


def _month(title):
    stems=['январ','феврал','март','апрел','ма','июн','июл','август','сентябр','октябр','ноябр','декабр']
    found=re.search(r'\b([а-яё]+)\s+(20\d{2})\s+года',title,re.I)
    if not found:raise SourceError('Monthly statistical period not stated')
    word,year=found.groups()
    months=[i+1 for i,stem in enumerate(stems) if word.casefold().startswith(stem)]
    if word.casefold().startswith('март'):months=[3]
    if len(months)!=1:raise SourceError('Ambiguous statistical month')
    return int(year),months[0]


def parse_bns_workbook(payload,source,file_url):
    # Bound ZIP expansion before passing externally supplied XLSX to openpyxl.
    with zipfile.ZipFile(io.BytesIO(payload)) as zipped:
        if len(zipped.infolist())>2000 or sum(i.file_size for i in zipped.infolist())>40*1024*1024:raise SourceError('Workbook exceeds safe size limits')
    book=openpyxl.load_workbook(io.BytesIO(payload),read_only=True,data_only=True)
    try:
        if 'Обложка' not in book.sheetnames or '3' not in book.sheetnames:raise SourceError('BNS workbook sheet schema changed')
        if any(book[n].max_row>5000 or book[n].max_column>300 for n in ['Обложка','3']):raise SourceError('Unexpected workbook dimensions')
        cover=' '.join(str(v) for row in book['Обложка'].iter_rows(values_only=True) for v in row if v is not None)
        published=re.search(r'Дата опубликования:\s*(\d{2})\.(\d{2})\.(\d{4})',cover)
        if not published:raise SourceError('Actual publication date missing from workbook cover')
        dd,mm,yyyy=map(int,published.groups());publication=date(yyyy,mm,dd)
        if publication>market_today():raise SourceError('Workbook publication is in the future')
        rows=list(book['3'].iter_rows(values_only=True))
        title=next((str(v) for row in rows[:5] for v in row if v and 'Цены и тарифы на отдельные виды платных услуг' in str(v)),None)
        if not title:raise SourceError('BNS table identity not confirmed')
        year,month=_month(title)
        first=date(year,month,1);last=date(year,month,calendar.monthrange(year,month)[1])
        header=next((r for r in rows[:10] if 'Республика Казахстан' in r and 'Караганда' in r),None)
        if header is None:raise SourceError('Karaganda/national columns not identified')
        wanted='natural_gas' if source['category']=='natural_gas' else 'electricity'
        matched=[]
        for index,row in enumerate(rows,1):
            label=str(row[0] or '').casefold()
            is_gas=label.startswith('газ,') and 'природный' in label and '1 куб.метр' in label
            is_power=label.startswith('электроэнергия,') and 'первого уровня' in label and 'населения, использующего электрические плиты' in label and '100 квт' in label
            if (wanted=='natural_gas' and is_gas) or (wanted=='electricity' and is_power):matched.append((index,row))
        if len(matched)!=1:raise SourceError('Commodity row absent/ambiguous; no LPG or other electricity tier substitution')
        index,row=matched[0];output=[]
        for label,region in [('Республика Казахстан','KZ-national'),('Караганда','KZ-Karaganda')]:
            column=header.index(label);raw=row[column]
            try:value=Decimal(str(raw).strip())
            except InvalidOperation:raise SourceError(f'Missing/confidential/footnoted value for {label}; no numeric guessing') from None
            if not value.is_finite():raise SourceError('Nonfinite statistic')
            output.append(PriceInput(source_id=source['id'],commodity=wanted,region=region,country='KZ',value=value,currency='KZT',
                unit='m3' if wanted=='natural_gas' else '100_kWh',published_at=publication,effective_from=last,period_start=first,period_end=last,
                price_type='reference',reliability='verified_official',consumer_class='household_statistics' if wanted=='natural_gas' else 'household_tier1_electric_stove_statistics',
                tax_basis='statistics_as_published',gas_volume_basis='BNS natural gas m3 as published; temperature/pressure basis not specified' if wanted=='natural_gas' else None,
                source_url=file_url,acquisition_method='https_xlsx',
                evidence=f'Official BNS monthly statistic, NOT a purchase/sale quote. Period {first}..{last}; {label}; sheet 3 row {index} column {column+1}; original label: {row[0]}; SHA256 {hashlib.sha256(payload).hexdigest()}. Geography must not be substituted.'))
        return label_test(source,output)
    finally:book.close()


def fetch_bns(source):
    index=public_get(source['url']);links=Links();links.feed(index.decode('utf-8'))
    files=[]
    for href,label in links.links:
        if 'Розничные цены на отдельные товары и услуги в Республике Казахстан' in label and re.fullmatch(r'/api/iblock/element/\d+/file/ru/',href):
            url=urljoin(source['url'],href)
            if url not in files:files.append(url)
    count=int(source.get('config',{}).get('history_files',3))
    if not 1<=count<=4:raise SourceError('history_files must be 1..4')
    if not files:raise SourceError('Official BNS file catalogue changed or access is restricted')
    documents=[(source['url'],index)];prices=[]
    for url in files[:count]:
        data=public_get(url);prices+=parse_bns_workbook(data,source,url);documents.append((url,data))
    return prices,archive(documents)


def parse_karaganda(payload,source):
    body=text(payload)
    heading=re.search(r'Цены на услуги розничной реализации электрической энергии с (\d{1,2}) ([а-я]+) (20\d{2}) года\s*\(г[.\s]*Караганда\)',body,re.I)
    if not heading:raise SourceError('Karaganda city tariff heading/date not found')
    day,month,year=heading.groups();effective=date(int(year),MONTHS[month.lower()],int(day))
    block=body[heading.end():];block=block.split('Цены на услуги',1)[0]
    values=re.search(r'потребители, использующие электрическую энергию не для бытовых нужд\s+(\d+[,.]\d{2})\s+(\d+[,.]\d{2})',block,re.I)
    if not values:raise SourceError('Non-household city tariff row changed')
    return label_test(source,[PriceInput(source_id=source['id'],commodity='electricity',region='KZ-Karaganda',value=value.replace(',','.'),currency='KZT',unit='kWh',
        published_at=None,effective_from=effective,price_type='tariff',reliability='verified_official',consumer_class='non_household',tax_basis=tax,
        source_url=source['url'],acquisition_method='https_html',evidence=f'Exact city table, original heading effective {effective}; publication date unknown; do not declare current. SHA256 {hashlib.sha256(payload).hexdigest()}')
        for value,tax in zip(values.groups(),['VAT_excluded','VAT_included'])])


def parse_krec(payload,notice,source):
    body=text(payload)
    scope='Абайского, Бухар-Жырауского, Нуринского, Осакаровского и Каркаралинского районов'
    if scope.casefold() not in body.casefold():raise SourceError('KREC district geography changed; review source mapping')
    date_match=re.search(r'ЦЕНЫ НА ЭЛЕКТРОСНАБЖЕНИЕ С\s+(\d{2})\.(\d{2})\.(\d{4})',body,re.I)
    if not date_match:raise SourceError('Current KREC effective date not found')
    day,month,year=map(int,date_match.groups());effective=date(year,month,day)
    # Avoid accidentally matching the old archived district prices further down.
    block=body[date_match.end():].split('Цены по районам до',1)[0]
    values=re.search(r'Не для бытовых нужд.{0,230}?(\d+[,.]\d{2})\s*₸\s*/\s*кВт.{0,50}?С НДС\s*\(16%\):\s*(\d+[,.]\d{2})',block,re.I)
    if not values:raise SourceError('KREC current non-household price block changed')
    publication=[]
    for match in re.finditer(r'<time[^>]+datetime=["\'](\d{4}-\d{2}-\d{2})["\'][^>]*>(.*?)</time>(.*?)(?=<time|$)',notice.decode('utf-8'),re.S):
        if f'price_{effective.isoformat()}_notice.docx' in match.group(3):publication.append(match.group(1))
    if len(set(publication))!=1:raise SourceError('Publication time not corroborated by dated announcement')
    districts=['Abay','Bukhar-Zhyrau','Nura','Osakarov','Karkaraly']
    records=[]
    for district in districts:
        for value,tax in zip(values.groups(),['VAT_excluded','VAT_included']):
            records.append(PriceInput(source_id=source['id'],commodity='electricity',region=f'KZ-Karaganda-{district}-district',value=value.replace(',','.'),currency='KZT',unit='kWh',
                published_at=publication[0],effective_from=effective,price_type='tariff',reliability='verified_official',consumer_class='non_household',tax_basis=tax,
                source_url=source['url'],acquisition_method='https_html',evidence=f'KREC retail SUPPLY price for five explicitly listed districts, NOT Karaganda city or transmission tariff. Publication corroborated at https://krec.kz/notices . SHA256 {hashlib.sha256(payload).hexdigest()}; notice SHA256 {hashlib.sha256(notice).hexdigest()}'))
    return label_test(source,records)


def fetch_official(source):
    if source['adapter']=='bns_retail_xlsx':return fetch_bns(source)
    payload=public_get(source['url'])
    if source['adapter']=='karaganda_supply':return parse_karaganda(payload,source),payload
    if source['adapter']=='krec_supply':
        notice=public_get('https://krec.kz/notices')
        return parse_krec(payload,notice,source),archive([(source['url'],payload),('https://krec.kz/notices',notice)])
    raise SourceError('Unsupported official adapter')


SOURCES=[
    {'id':'bns_retail_gas','name':'БНС РК: месячная статистика розничных цен природного газа','url':'https://stat.gov.kz/ru/industries/economy/prices/spreadsheets/?name=19087','category':'natural_gas','adapter':'bns_retail_xlsx','config':{'history_files':3,'geography':['KZ-Karaganda','KZ-national'],'price_kind':'reference_statistics'}},
    {'id':'bns_retail_electricity','name':'БНС РК: месячная статистика электроэнергии, население, первый уровень, электроплиты','url':'https://stat.gov.kz/ru/industries/economy/prices/spreadsheets/?name=19087','category':'electricity','adapter':'bns_retail_xlsx','config':{'history_files':3,'geography':['KZ-Karaganda','KZ-national'],'price_kind':'reference_statistics'}},
    {'id':'karaganda_zharyk_supply','name':'Қарағанды Жарық: тариф небытовых потребителей г. Караганда','url':'https://www.k-zharyk.kz/ru/node/329','category':'electricity','adapter':'karaganda_supply'},
    {'id':'krec_district_supply','name':'КРЭК: небытовое электроснабжение пяти районов Карагандинской области','url':'https://krec.kz/price','category':'electricity','adapter':'krec_supply'},
    {'id':'kosagro_verified_manual','name':'КОСАГРО: датированный публичный PDF прайс, требуется проверка табличной привязки','url':'https://kosagro.kz/f/price-list.pdf','category':'mineral_fertilizer','adapter':'manual'},
]
