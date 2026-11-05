import json
import re
from src.data.prepare import ROOT


def load_knowledge():
    return json.loads((ROOT/'data/knowledge/biogas.json').read_text(encoding='utf-8'))


ALIASES = {
    'chernozem': [r'черноз[её]м\w*',r'почв\w*',r'chernozem',r'soil'],
    'Wheat straw': [r'пшенич\w*\s+солом\w*',r'wheat\s+straw'],
    'Whey': [r'сыворот\w*',r'whey'],
    'Cellulose': [r'целлюлоз\w*',r'cellulose'],
    'Bird feed': [r'корм\w*\s+для\s+птиц\w*',r'bird\s+feed'],
    'Rabbit feed': [r'корм\w*\s+для\s+кролик\w*',r'rabbit\s+feed'],
    'Sunflower seeds': [r'сем\w*\s+подсолнечник\w*',r'sunflower\s+seeds'],
    'cattle_manure': [r'(?:коров\w*\s+навоз\w*|навоз\w*\s+(?:крс|коров\w*))',r'cattle_manure',r'cattle\s+manure'],
    'food_waste': [r'пищев\w*\s+отход\w*',r'food[_\s]+waste'],
}


def detect_material(text):
    hits = [name for name, patterns in ALIASES.items() if any(re.search(r'\b'+p+r'\b',text,re.I) for p in patterns)]
    if re.search(r'\b(?:смесь|смеси|mixture|mix)\b',text,re.I) or len(hits)>1:
        return 'mixture'
    if not hits and re.search(r'\bнавоз\w*\b',text,re.I):
        return 'manure_unspecified'
    return hits[0] if hits else None


def normalize_material(value):
    if not isinstance(value,str) or not value.strip():
        raise ValueError('material must be a nonempty string')
    kb=load_knowledge()
    return value if value in kb['materials'] else detect_material(value) or value.strip()


def source_records(ids):
    kb=load_knowledge()
    return [dict(id=i,**kb['sources'][i]) for i in dict.fromkeys(ids)]


def search_scientific_sources(query,material=None,topics=None,category=None,process_type=None):
    if not isinstance(query,str) or not query.strip():
        raise ValueError('Nonempty scientific query required')
    from src.recommendations.retrieval import retrieve
    structured=retrieve(query,material=material,topics=topics,category=category,process_type=process_type)
    kb=load_knowledge()
    material=material or detect_material(query)
    ids=kb['materials'].get(material,{}).get('sources',[])
    text=query.casefold()
    ids+= [key for key,record in kb['sources'].items() if any(word in text for word in record['keywords'])]
    records={s['id']:s for s in source_records(ids)}
    records.update({s['id']:s for s in structured['sources']})
    return {'status':'ok','search_mode':'curated_local_catalogue_with_structured_claims','query':query,
        'sources':list(records.values()),'claims':structured['claims'],'filters':{'material':material,'topics':structured['topics'],'category':category,'process_type':process_type}, 'live_web_search':False,
        'message':'Поиск по локально проверенному каталогу; свежий поиск публикаций в интернете не выполнялся.'}
