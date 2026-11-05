"""Recognized names are counted separately from scoped numerical profiles."""
import json,re
from src.data.prepare import ROOT
from src.research.evidence_extractor import catalog as legacy_catalog

DEFINITIONS=[
 ('cattle_manure','Навоз КРС','Cattle manure','Сиыр көңі',[r'коров\w*(?:\s+навоз\w*)?',r'навоз\w*(?:\s+жиж\w*)?\s+крс',r'(?:cow|cattle)\s+(?:dung|manure|slurry)',r'сиыр\w*\s+көң\w*'],['slurry','bedded','fresh_solid','dry'],['bedding and slow hydrolysis','ammonia; verify composition']),
 ('swine_manure','Свиной навоз','Swine manure','Шошқа көңі',[r'свин\w*\s+навоз\w*',r'(?:pig|swine)\s+(?:manure|slurry)',r'шошқа\w*\s+көң\w*'],['slurry','fresh_solid'],['ammonia','volatile fatty acids']),
 ('poultry_manure','Птичий помёт','Poultry manure','Құс саңғырығы',[r'птич\w*\s+пом[её]т\w*',r'курин\w*\s+пом[её]т\w*',r'(?:poultry|chicken)\s+(?:manure|litter)',r'құс\s+(?:көң\w*|саңғыры\w*)'],['fresh_solid','bedded','dry'],['nitrogen/ammonia; measure before loading']),
 ('sheep_goat_manure','Овечий и козий навоз','Sheep/goat manure','Қой-ешкі көңі',[r'(?:овеч\w*|коз\w*)\s+навоз\w*',r'(?:sheep|goat)\s+manure',r'(?:қой|ешкі)\s+көң\w*'],['fresh_solid','dry'],['specific composition and bedding need review']),
 ('horse_manure','Конский навоз','Horse manure','Жылқы көңі',[r'конск\w*\s+навоз\w*',r'horse\s+manure',r'жылқы\s+көң\w*'],['bedded','fresh_solid'],['lignocellulosic bedding and slow hydrolysis']),
 ('food_waste','Пищевые отходы','Food waste','Тағам қалдықтары',[r'пищев\w*\s+отход\w*',r'food\s+waste',r'(?:тағам|тамақ)\s+қалдық\w*'],['prepared_pulp','fresh_solid'],['rapid acidification','lipids and loading']),
 ('vegetable_waste','Овощные отходы','Vegetable waste','Көкөніс қалдықтары',[r'овощн\w*\s+отход\w*',r'vegetable\s+waste',r'көкөніс\s+қалдық\w*'],['fresh_solid','prepared_pulp'],['acidification; sample-specific degradability']),
 ('fruit_waste','Фруктовые отходы','Fruit waste','Жеміс қалдықтары',[r'фруктов\w*\s+отход\w*',r'fruit\s+waste',r'жеміс\s+қалдық\w*'],['fresh_solid','prepared_pulp'],['acidification; fruit-specific inhibitors require review']),
 ('plant_residue','Растительные остатки','Plant residues','Өсімдік қалдықтары',[r'растительн\w*\s+остат\w*',r'растительн\w*\s+отход\w*',r'(?:crop|plant)\s+residu\w*',r'өсімдік\s+қалдық\w*'],['fresh_solid','dry','shredded'],['lignocellulose and preprocessing demand']),
 ('grass','Трава','Grass','Шөп',[r'трав\w*',r'\bgrass\b',r'шөп\w*'],['fresh_solid','shredded','silage','dry'],['lignocellulose','seasonality and preparation']),
 ('straw','Солома','Straw','Сабан',[r'(?:пшенич\w*\s+)?солом\w*',r'(?:wheat\s+)?straw',r'(?:бидай\s+)?сабан\w*'],['dry','shredded'],['slow hydrolysis','preparation energy']),
 ('silage','Силос','Silage','Сүрлем',[r'силос\w*',r'\bsilage\b',r'сүрлем\w*'],['silage'],['ensiling history and acids need verification']),
 ('dairy_waste','Отходы молочной промышленности','Dairy waste','Сүт өндірісінің қалдықтары',[r'отход\w*\s+молочн\w*',r'молочн\w*\s+отход\w*',r'сыворот\w*',r'\bwhey\b',r'dairy\s+waste',r'сарысу'],['slurry'],['rapid acidification','variable fats and cleaning chemicals']),
 ('other_organic','Другое органическое сырьё','Other organic material','Басқа органикалық шикізат',[r'друг\w*\s+органическ\w*',r'other\s+organic'],['unknown'],['identify material before quantitative advice']),
 ('manure','Навоз: вид не уточнён','Manure: species unknown','Көң: түрі белгісіз',[r'навозн\w*\s+жиж\w*',r'\bmanure\b',r'навоз\w*',r'сұйық\s+көң'],['slurry','fresh_solid','bedded'],['species and physical state unknown'])]

def document():
    from src.research.profile_cache import read_profile
    d=read_profile(ROOT/'data/research/substrate_advisor.json')
    extra=read_profile(ROOT/'data/research/advanced_profiles.json')
    for key in ['sources','profiles','partial_characterizations']:d[key]+=extra.get(key,[])
    path=ROOT/'data/research/complete_substrate_profiles.json'
    if path.exists():
        extra=read_profile(path)
        for key in ['sources','profiles','partial_characterizations']:d[key]+=extra.get(key,[])
    path=ROOT/'data/research/stage83_profiles.json'
    if path.exists():
        extra=read_profile(path)
        for key in ['sources','profiles','partial_characterizations']:d[key]+=extra.get(key,[])
    return d
def name(material,language='ru'):
    row=next((x for x in DEFINITIONS if x[0]==material),None)
    return row[{'ru':1,'en':2,'kk':3}.get(language,1)] if row else material
def matches(text):
    found=[]
    for material,ru,en,kk,patterns,states,risks in DEFINITIONS:
        for pattern in patterns:
            for m in re.finditer(pattern,text,re.I):found.append({'material':material,'start':m.start(),'end':m.end(),'text':m.group()})
    # Longest explicit material wins over generic manure inside its name.
    accepted=[]
    for item in sorted(found,key=lambda x:(x['material']=='manure',-(x['end']-x['start']))):
        if not any(item['start']<x['end'] and item['end']>x['start'] for x in accepted):accepted.append(item)
    return sorted(accepted,key=lambda x:x['start'])
def normalized(material):
    if material in {x[0] for x in DEFINITIONS}:return material
    if material=='Wheat straw':return 'straw'
    if material=='Whey':return 'dairy_waste'
    hits=matches(material)
    if len({x['material'] for x in hits})!=1:raise ValueError('Unknown or ambiguous substrate: '+material)
    return hits[0]['material']

def profiles():
    d=document();rows=[]
    for p in legacy_catalog()['profiles']:
        rows.append({'id':p['id'],'material':p['material'],'material_state':p['material_state'],'source_id':p['source']['id'],'source':p['source'],
            'verification_stage':'APPROVED_FOR_ESTIMATION','approved_scope':'Single untreated RM1 slurry; coarse graph BMP bracket',
            'density_kg_l':p['values']['density_kg_l'],'ts_fraction':p['values']['ts_fraction'],'vs_fraction_wet':p['values']['vs_fraction_wet'],
            'bmp_ml_g_vs':p['values']['bmp_ml_g_vs'],'conditions':p['conditions'],'cn_ratio':None,'ph':None,'preparation':'Untreated refrigerated cattle slurry; other forms excluded'})
    for p in d['profiles']:
        source=next(s for s in d['sources'] if s['id']==p['source_id']);rows.append({**p,'source':source,'conditions':source['conditions']})
    return rows

def get_catalog():
    p=profiles();d=document();materials=[]
    from src.advisor.registry import ui,describe
    for key,ru,en,kk,patterns,states,risks in DEFINITIONS:
        selected=[x for x in p if x['material']==key]
        from src.research.dossiers import CORE_MATERIALS
        materials.append({'id':key,'scope_status':'CORE' if key in CORE_MATERIALS else 'EXPERIMENTAL_RETAINED','name':{'ru':ru,'en':en,'kk':kk},'synonyms':patterns,'physical_states':states,'density':None,'ts':None,'vs':None,'bmp':None,'cn_ratio':None,'ph':None,**describe(key,selected),
            'profiles':selected,'partial_characterizations':[r for r in d['partial_characterizations'] if r['material']==key],
            'potential_inhibitors':risks,'preparation':'Requires material-specific verification; no pretreatment prescribed automatically',
            'evidence_status':'APPROVED_FOR_ESTIMATION' if selected else 'PARTIAL_OR_QUALITATIVE_ONLY'})
    return {'version':'8.1','materials':materials,'ui':ui(),'recognized_categories':len(materials),
            'materials_with_approved_profiles':sorted({x['material'] for x in p}),'approved_profile_count':len(p),
            'complete_density_solids_bmp_profile_count':sum(all(x.get(k) is not None for k in ['density_kg_l','ts_fraction','vs_fraction_wet','bmp_ml_g_vs']) for x in p),
            'sources':d['sources'],'notice':'Names, partial characterizations and numerical estimation profiles are separate counts.'}

def choose(component,allow_transfer):
    if not allow_transfer or component.data_mode=='MEASURED':return None,False
    if component.decay_state in {'rotted','composted','stored'}:return None,False
    matching=[p for p in profiles() if p['material']==component.material and p['verification_stage']=='APPROVED_FOR_ESTIMATION']
    matching=[p for p in matching if not p.get('animals') or component.animal in p['animals']]
    matching=[p for p in matching if not p.get('poultry_types') or component.poultry_type in p['poultry_types']]
    matching=[p for p in matching if not p.get('beddings') or component.bedding in p['beddings']]
    if component.bedding=='straw':matching=[p for p in matching if p['material_state']!='bedded' or 'straw' in p.get('beddings',[])]
    if component.bedding in {'sawdust','shavings','straw','other'}:matching=[p for p in matching if p['material_state'] not in {'slurry','fresh_solid'}]
    if component.reference_profile_id:
        matching=[p for p in matching if p['id']==component.reference_profile_id]
        if not matching:raise ValueError('Profile does not match this material, animal or subtype')
    exact=[p for p in matching if component.material_state in p.get('matching_states',[p['material_state']])]
    if exact:return exact[0],component.material_state in exact[0].get('conditional_states',[])
    if component.material_state=='unknown':
        if component.reference_profile_id:raise ValueError('Profile physical state does not match the component')
        return None,False
    if component.reference_profile_id:raise ValueError('Profile physical state does not match the component')
    return None,False
