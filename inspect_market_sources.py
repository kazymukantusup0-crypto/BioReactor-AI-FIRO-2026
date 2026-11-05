"""Fetch permitted primary documents and inspect workbook structure before mapping."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import io
import json
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import main
from src.market.adapters import public_get,TextParser

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'reports/stage3_5/inspection'
URLS={
    'bns_retail_index':'https://stat.gov.kz/ru/industries/economy/prices/spreadsheets/?name=19087',
    'bns_retail_september':'https://stat.gov.kz/api/iblock/element/353619/file/ru/',
    'karaganda_supply':'https://www.k-zharyk.kz/ru/node/329',
    'krec_notices':'https://krec.kz/notices',
    'esalmaty':'https://www.esalmaty.kz/ru/business-tariffs',
    'open_data_catalogue':'https://data.egov.kz/',
    'kosagro_pricelist':'https://kosagro.kz/f/price-list.pdf',
}


def fetch(item):
    name,url=item
    try:
        data=public_get(url)
        (OUT/(name+'.bin')).write_bytes(data)
        result={'name':name,'url':url,'bytes':len(data),'status':'downloaded_with_verified_https'}
        if data.startswith(b'PK'):
            import openpyxl
            book=openpyxl.load_workbook(io.BytesIO(data),read_only=True,data_only=True)
            sheets={}
            for sheet in book:
                rows=[]
                for i,row in enumerate(sheet.iter_rows(values_only=True),1):
                    vals=[str(v) if v is not None else None for v in row]
                    if i<16 or any(v and any(term in v.casefold() for term in ['газ','электр','караганд','удобрен','солом','навоз']) for v in vals):
                        rows.append({'row':i,'values':vals})
                sheets[sheet.title]={'rows':sheet.max_row,'columns':sheet.max_column,'selected_rows':rows}
            result['sheets']=sheets
            (OUT/(name+'_structure.json')).write_text(json.dumps(sheets,ensure_ascii=False,indent=2),encoding='utf-8')
            book.close()
        elif data[:100].lower().find(b'<')>=0:
            p=TextParser();p.feed(data.decode('utf-8',errors='replace'))
            (OUT/(name+'.txt')).write_text('\n'.join(p.parts),encoding='utf-8')
        return result
    except Exception as exc:return {'name':name,'url':url,'status':'unavailable','reason':str(exc)}


def run():
    OUT.mkdir(parents=True,exist_ok=True)
    with ThreadPoolExecutor(max_workers=3) as pool:results=list(pool.map(fetch,URLS.items()))
    (OUT/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps([{k:v for k,v in r.items() if k!='sheets'} for r in results],ensure_ascii=False,indent=2))


if __name__=='__main__':run()
