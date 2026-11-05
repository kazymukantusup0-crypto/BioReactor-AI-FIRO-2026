"""Independent animal, physical form, decomposition and bedding; legacy adapter."""
import re

ANIMALS={'cattle':'cattle_manure','pig':'swine_manure','poultry':'poultry_manure','horse':'horse_manure','sheep':'sheep_goat_manure','goat':'sheep_goat_manure'}
PATTERNS={'cattle':r'коров|крс|cattle|cow|сиыр','pig':r'свин|pig|swine|шошқа','poultry':r'курин|птич|пом[её]т|chicken|poultry','horse':r'конск|лошад|horse','sheep':r'овеч|баран|sheep','goat':r'коз|goat'}

def extract(text):
    result={}
    for animal,pattern in PATTERNS.items():
        if re.search(pattern,text,re.I):result['animal']=animal;break
    for value,pattern in [('dry',r'сух|dry'),('bedded',r'подстил|bedded|litter'),('semiliquid',r'полужид|semiliquid'),('liquid',r'жидк|жиж|slurry|liquid'),('solid',r'тв[её]рд|solid')]:
        if re.search(pattern,text,re.I):result['physical_state']=value;break
    for value,pattern in [('composted',r'компост|compost'),('rotted',r'перепрев|rotted'),('stored',r'хранив|хранени|stored'),('fresh',r'свеж|fresh')]:
        if re.search(pattern,text,re.I):result['decay_state']=value;break
    for value,pattern in [('none',r'без подстил|without bedding'),('sawdust',r'опил|sawdust'),('shavings',r'струж|shavings'),('straw',r'соломен|straw.based|straw bedding')]:
        if re.search(pattern,text,re.I):result['bedding']=value;break
    return result

def normalize(c):
    legacy_form=c.physical_state=='unknown'
    expected=ANIMALS.get(c.animal)
    inferred=next((a for a,m in ANIMALS.items() if m==c.material),None)
    if expected and c.material not in {'manure',expected}:raise ValueError('Animal contradicts the substrate material')
    if expected:c.material=expected
    elif inferred and c.material!='sheep_goat_manure':c.animal=inferred
    legacy={'slurry':'liquid','fresh_solid':'solid','dry':'dry','bedded':'bedded'}
    if c.physical_state=='unknown':c.physical_state=legacy.get(c.material_state,'unknown')
    if c.material_state=='compost' and c.decay_state=='unknown':c.decay_state='composted'
    if legacy_form and c.material_state=='fresh_solid' and c.decay_state=='unknown':c.decay_state='fresh'
    if c.physical_state!='unknown':c.material_state={'liquid':'slurry','semiliquid':'semiliquid','solid':'fresh_solid','dry':'dry','bedded':'bedded'}[c.physical_state]
    if c.decay_state in {'rotted','composted'}:c.material_state='compost'
    return c
