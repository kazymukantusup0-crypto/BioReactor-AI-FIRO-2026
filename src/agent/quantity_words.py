"""Small literal word-number grammar; evidence spans remain the user's words."""
import re

VALUES={'один':1,'одна':1,'одну':1,'одно':1,'два':2,'две':2,'три':3,'четыре':4,'пять':5,
 'шесть':6,'семь':7,'восемь':8,'девять':9,'десять':10,'одиннадцать':11,'двенадцать':12,
 'тринадцать':13,'четырнадцать':14,'пятнадцать':15,'шестнадцать':16,'семнадцать':17,
 'восемнадцать':18,'девятнадцать':19,'двадцать':20,'тридцать':30,'сорок':40,
 'пятьдесят':50,'шестьдесят':60,'семьдесят':70,'восемьдесят':80,'девяносто':90,'сто':100,
 'полтора':1.5,'полторы':1.5,
 'one':1,'two':2,'three':3,'four':4,'five':5,'six':6,'seven':7,'eight':8,'nine':9,'ten':10,
 'eleven':11,'twelve':12,'thirteen':13,'fourteen':14,'fifteen':15,'sixteen':16,
 'seventeen':17,'eighteen':18,'nineteen':19,'twenty':20,'thirty':30,'forty':40,'fifty':50}
WORDS='|'.join(sorted(VALUES,key=len,reverse=True))
PATTERN=re.compile(r'\b('+WORDS+r')(?:[ -]+('+WORDS+r'))?\s*(кг\b|килограмм\w*|kg\b|kilograms?\b|литр\w*|л\b|litres?\b|liters?\b|L\b|тонн\w*|t\b|tonnes?\b|грамм\w*|g\b|grams?\b)',re.I)


def amounts(text):
    rows=[]
    for m in PATTERN.finditer(text):
        first=VALUES[m[1].casefold()];second=VALUES[m[2].casefold()] if m[2] else 0
        if m[2] and not(first>=20 and 0<second<10):continue
        label=m[3].casefold()
        unit='kg' if re.match(r'кг|килограмм|kg|kilogram',label) else 'L' if re.match(r'литр|л$|lit|l$',label) else 't' if re.match(r'тонн|t$|tonne',label) else 'g'
        rows.append({'value':first+second,'unit':unit,'start':m.start(),'end':m.end(),'text':m.group()})
    return rows
