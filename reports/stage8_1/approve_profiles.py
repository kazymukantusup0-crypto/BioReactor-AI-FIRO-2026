import main,json
from src.data.prepare import ROOT
p=ROOT/'reports/stage8_1/research_candidates.json';d=json.loads(p.read_text(encoding='utf-8'));target=ROOT/'data/research/complete_substrate_profiles.json'
assert not target.exists(),'Approved evidence is versioned, not overwritten'
rows=[]
for candidate in d['paired_candidates']:
    solid=candidate['physical_state_stated']!='slurry';layer=candidate['source_id']=='ramos2019'
    row={'id':candidate['id'],'material':candidate['material'],'animals':[candidate['animal']],'source_id':candidate['source_id'],'material_state':'fresh_solid' if solid else 'slurry','verification_stage':'APPROVED_FOR_ESTIMATION','approved_scope':'Paired sample means; no population or predictive interval; see source conditions and limits','density_kg_l':None,'cn_ratio':7.18 if layer else None,'ph':7.19 if layer else None,'preparation':'Crushed, wet diluted assay on fresh conveyor-belt laying-hen Sample1; frozen after characterization' if layer else 'Specific Greek farm sample, refrigerated at4 C; paired TS/VS/BMP, subtype/bedding unspecified','matching_states':['fresh_solid'] if solid else ['slurry']}
    for key in ['ts_fraction','vs_fraction_wet','bmp_ml_g_vs']:
        value=candidate.get(key)
        if value:row[key]={'low':value['value'],'high':value['value'],'locator':value['locator'],'reported_spread':value.get('reported_plus_minus'),'spread_type':'standard error' if layer and key=='bmp_ml_g_vs' else 'unspecified reported +/-; not interval'}
    if layer:row['vs_fraction_wet']={'low':candidate['vs_fraction_wet_derived'],'high':candidate['vs_fraction_wet_derived'],'locator':'Derived from paired SupplementTableS1 TS*VS/TS Sample1'};row['poultry_types']=['layer'];row['beddings']=['unknown','none']
    elif candidate['material']=='poultry_manure':
        row['poultry_types']=['unknown','chicken'];row['matching_states']+=['dry'];row['conditional_states']=['dry'];row['beddings']=['unknown','none'];row['state_transfer_note']='Высокосухой образец с TS69.25% сопоставлен с сухим помётом; это не образец после специальной сушки и не профиль бройлерной подстилки.'
    elif candidate['animal']=='goat':row['matching_states']+=['dry'];row['conditional_states']=['dry'];row['state_transfer_note']='TS71.7% в конкретном твёрдом козьем образце; перенос на сухой материал условный.'
    row['source_stp_claimed']=candidate['source_id']=='eftaxias2024'
    rows.append(row)
partials=[{'material':m,'status':'PARTIAL_SCOPE_REQUIRES_MEASUREMENTS','reason':reason} for m,reason in [('poultry_manure','Broiler/turkey/bedded/moist slurry are not interchangeable with the two paired samples; specific conditions required.'),('swine_manure','Liquid pig profiles available; solid/bedded/dry pig BMP not transferred from cattle.'),('vegetable_waste','No approved paired profile for arbitrary vegetable mixture; measured TS/VS/BMP can be entered.'),('fruit_waste','Fruit identity, preparation and inhibitors vary; no universal BMP assigned.'),('grass','Existing mixed grass/cattle experiment not treated as mono grass BMP.'),('plant_residue','Specific plant material and preparation required before transferring BMP.'),('silage','Crop and ensiling conditions required; no general energy-crop BMP assigned.')]]
target.write_text(json.dumps({'version':'8.1','sources':d['sources'],'profiles':rows,'partial_characterizations':partials,'process_references':d['process_references'],'approval':'Parent reviewed primary table images and paired-sample limitations; dry observed yield is NOT BMP'},ensure_ascii=False,indent=2),encoding='utf-8');print('Approved',len(rows),'paired profiles; kept dry process reference separate')
