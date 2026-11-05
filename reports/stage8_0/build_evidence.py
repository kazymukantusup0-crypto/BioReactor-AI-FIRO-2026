"""Reviewed additions only; older evidence files are immutable."""
import main
import json
from src.data.prepare import ROOT
out=ROOT/'data/research/advanced_profiles.json'
assert not out.exists()
sources=[
 {'id':'alberta2005','title':'Manure Composting Manual','authors':['Alberta Agriculture, Food and Rural Development'],'year':2005,'url':'https://www1.agric.gov.ab.ca/$department/deptdocs.nsf/all/agdex8875/$file/400_27-1.pdf?OpenElement=','verification_stage':'NUMERIC_DATA_VERIFIED','reviewed_sections':['Table 3, printed page 10'],'conditions':{'method':'Engineering reference table, not BMP experiment'},'limitations':'Density depends on moisture, bedding and packing; no uncertainty coverage supplied.'},
 {'id':'alberta_nmp','title':'Nutrient Management Planning Guide, Chapter 6.1','authors':['Alberta Agriculture'],'year':None,'url':'https://www1.agriculture.alberta.ca/$department/deptdocs.nsf/all/epw11920/$FILE/6-1.pdf','verification_stage':'NUMERIC_DATA_VERIFIED','reviewed_sections':['Table 6.1.2, printed page 222'],'conditions':{'method':'Estimated density of selected solid manure sources'},'limitations':'Class averages, not universal densities or intervals; bedding/moisture unspecified.'},
 {'id':'monch2013','title':'Investigation of the methane potential of horse manure','authors':['Matthias Mönch-Tegeder','Andreas Lemmer','Hans Oechsner','Thomas Jungbluth'],'year':2013,'url':'https://cigrjournal.org/index.php/Ejounral/article/view/2445','review_url':'https://cigrjournal.org/index.php/Ejounral/article/download/2445/1736/8047','verification_stage':'NUMERIC_DATA_VERIFIED','reviewed_sections':['Methods 2.1-2.3; Tables 2, 3, 7, 8'],'conditions':{'temperature_c':37,'temperature_tolerance_c':.5,'duration_days':35,'duration_kind':'BMP_INCUBATION','reactor_type':'HBT 100 mL glass syringes; 30 g inoculum + 600 mg dried milled sample','gas_basis':{'temperature_k':273.15,'pressure_pa':101300,'moisture':'unknown'},'preparation':'Dried at 60 C for 48 h, milled to 1 mm; Stuttgart barns'},'limitations':'Preparation affects hydrolysis; barn A paired measurements only, not universal raw feedstock BMP.'}
]
densities=[]
def density(material,states,lo,hi,locator,source='alberta2005',beddings=None,limits=None):
 densities.append({'material':material,'physical_states':states,'value':{'low':lo,'high':hi},'source_id':source,'locator':locator,'beddings':beddings,'limitations':limits or ['Reference sample; measure local moisture and packing','Cross-study transfer to a BMP sample is an illustrative scenario, not a coherent measurement']})
density('cattle_manure',['bedded'],.710,.710,'Table 3: beef feedlot with bedding, moisture 68%; 710 kg/m3')
density('cattle_manure',['solid'],.710,.710,'Table 3: dairy solid manure handling, moisture 79%; 710 kg/m3',beddings=['none','unknown'])
density('swine_manure',['liquid'],1,1,'Table 3: pig slurry, moisture 93-99%; 1000 kg/m3')
density('swine_manure',['solid'],.772,.796,'Table 6.1.2: solid grow/finish 772, farrow-to-finish 796 kg/m3','alberta_nmp')
density('poultry_manure',['bedded'],.330,.330,'Table 3: broiler litter, moisture 25%; 330 kg/m3')
density('poultry_manure',['solid'],.470,.470,'Table 3: broiler/breeder/layer, moisture 46%; 470 kg/m3')
density('horse_manure',['bedded'],.725,.960,'Table 3: horse manure with bedding, moisture 59-79%; 725-960 kg/m3')
density('sheep_goat_manure',['solid'],.497,.497,'Table 6.1.2: sheep ewes/rams and goats general, 497 kg/m3','alberta_nmp')
density('straw',['dry'],.130,.192,'Table 3: oat straw, moisture 14%; 130-192 kg/m3',limits=['Oat straw only; wheat straw density is not reported. Use solely as an explicitly chosen oat-straw scenario.'])
profiles=[]
def profile(id,material,state,ts,vs,bmp,locator,decay=None):
 def value(x,label):return {'low':x,'high':x,'locator':label}
 profiles.append({'id':id,'material':material,'material_state':state,'source_id':'monch2013','verification_stage':'APPROVED_FOR_ESTIMATION','approved_scope':locator,'density_kg_l':None,'ts_fraction':value(ts,locator),'vs_fraction_wet':value(vs,locator),'bmp_ml_g_vs':value(bmp,locator),'cn_ratio':None,'ph':None,'preparation':'Barn A; dried 60 C, milled 1 mm before HBT. No population interval.','decay_states':decay or ['unknown','fresh'],'beddings':['none','unknown'] if material=='horse_manure' else ['unknown','none']})
profile('monch2013-horse-dung-A','horse_manure','fresh_solid',.2319,.2051,176,'Tables 3 and 8, barn A: TS 23.19% FM, VS 20.51% FM, observed 0.176 Nm3 CH4/kg VS')
profile('monch2013-straw-A','straw','dry',.8177,.7561,214,'Tables 2 and 7, barn A: TS 81.77% FM, VS 75.61% FM, observed 0.214 Nm3 CH4/kg VS')
partials=[{'material':m,'status':'PARTIAL_ONLY','density_profile_available':any(d['material']==m for d in densities),'bmp_available':False,'reason':reason} for m,reason in [('cattle_manure','No coherent measured dry or straw-bedded cattle BMP/TS/VS/density set; dry and straw scenarios require explicit cross-study assumptions.'),('swine_manure','Baek Table 1 TS/VS known; RSM pure-pig vertex is fitted, not measured mono BMP.'),('poultry_manure','Reference density only; ammonia-sensitive material, no approved matched BMP set.'),('sheep_goat_manure','Reference density only; no approved local matched BMP set.'),('plant_residue','No universal BMP for heterogeneous plant residues.'),('grass','Existing co-digestion experiment is not mono grass BMP.')]]
out.write_text(json.dumps({'version':'8.0','sources':sources,'density_profiles':densities,'profiles':profiles,'partial_characterizations':partials,'source_access':{'mdpi_horse2026':'429; excluded from numerical profiles','pmc_pham2013':'CAPTCHA; not bypassed; excluded until primary tables can be reviewed','alberta':'Official PDF text reviewed','cigr':'Primary full PDF reviewed'}},ensure_ascii=False,indent=2),encoding='utf-8')
print(out)
