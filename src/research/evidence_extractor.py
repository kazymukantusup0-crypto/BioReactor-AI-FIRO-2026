"""Only reviewed coherent profiles can feed arithmetic; discovery is quarantined."""
import json,math
from src.data.prepare import ROOT

def catalog():
    from src.research.profile_cache import read_profile
    data=read_profile(ROOT/'data/research/reviewed_evidence.json')
    for p in data['profiles']:validate_profile(p)
    return data

def validate_profile(p):
    if p['source']['verification_status']!='REVIEWED_PRIMARY':raise ValueError('Unreviewed evidence cannot feed estimates')
    if not p['source'].get('doi') and not p['source'].get('url'):raise ValueError('Missing citation')
    units={'density_kg_l':'kg/L','vs_fraction_wet':'kg VS/kg wet','ts_fraction':'kg TS/kg wet','bmp_ml_g_vs':'mL CH4/g VS at stated reference'}
    for name,unit in units.items():
        v=p['values'][name]
        if v['normalized_unit']!=unit or not v.get('locator') or not v.get('original_unit'):raise ValueError('Missing or inconsistent unit/locator')
        if not all(isinstance(v[k],(int,float)) and math.isfinite(v[k]) for k in ['low','high']) or not 0<v['low']<=v['high']:raise ValueError('Invalid evidence range')
        if 'fraction' in name and v['high']>1:raise ValueError('Fraction exceeds unity')
    if p['values']['vs_fraction_wet']['high']>p['values']['ts_fraction']['high']:raise ValueError('VS exceeds TS')
    if not p['conditions'].get('gas_reference') or not p['conditions'].get('bmp_method'):raise ValueError('BMP method/reference missing')
    return p

def extract_pdf_text(path):
    """Explicit local/manual PDF import only; text is DRAFT until reviewed."""
    from pypdf import PdfReader
    from pathlib import Path
    if Path(path).stat().st_size>4*1024*1024:raise ValueError('PDF too large')
    reader=PdfReader(path)
    if len(reader.pages)>100:raise ValueError('Too many pages')
    return {'verification_status':'DRAFT_NOT_FOR_CALCULATION','pages':[{'page':i+1,'text':page.extract_text()[:30000]} for i,page in enumerate(reader.pages)]}
