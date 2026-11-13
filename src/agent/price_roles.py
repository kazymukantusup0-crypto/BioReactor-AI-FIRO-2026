"""Bind monetary amounts to their local commodity and denominator, never globally."""
import re

NUMBER=r'-?\d+(?:[ \u00a0\u202f]\d{3})*(?:[.,]\d+)?'
MONEY=re.compile(r'('+NUMBER+r')\s*(тенге|теңге|₸|KZT|USD|dollars?|руб\w*|RUB)\b',re.I)
ENERGY=r'(?:квт\s*[·⋅*. -]?\s*ч|kwh|квтсағ)'
BATCH=r'(?:вс[юе][йх]?\s+парти\w*|весь\s+объ[её]м|целую\s+парти\w*|(?:цен\w*\s+)?(?:новой\s+)?парти\w*|whole\s+batch|entire\s+(?:batch|volume)|бүкіл\s+көлем|барлық\s+көлем)'


def extract_prices(text):
    """Return independently grounded price entities; ambiguous same-role quotes fail closed."""
    result=[]
    for clause in re.split(r'[;!?\n]|\.(?!\d)|,(?!\d)',text):
        matches=list(MONEY.finditer(clause))
        for i,m in enumerate(matches):
            # A denominator belongs to this amount, not another amount in the clause.
            left=clause[matches[i-1].end() if i else 0:m.start()]
            right=clause[m.end():matches[i+1].start() if i+1<len(matches) else len(clause)]
            currency='KZT' if re.fullmatch(r'тенге|теңге|₸|kzt',m[2],re.I) else 'USD' if re.fullmatch(r'usd|dollars?',m[2],re.I) else 'RUB'
            value=float(re.sub(r'[ \u00a0\u202f]','',m[1]).replace(',','.'))
            evidence=(left+m.group()+right).strip()
            energy=bool(re.match(r'\s*(?:/|за\s+|per\s+)'+ENERGY,right,re.I) or re.search(r'(?:тариф\w*|electricity|электроэнерг\w*).{0,30}$',left,re.I) and re.search(ENERGY,left+right,re.I))
            if energy:
                if currency=='KZT':result.append(('electricity_tariff_kzt_per_kwh',value,evidence,'KZT/kWh'))
                continue
            scopes=[('batch',BATCH),('kg',r'(?:за|per|/)\s*(?:1\s*)?(?:кг|kg|килограмм)\b'),('L',r'(?:за|per|/)\s*(?:1\s*)?(?:литр\w*|litres?|liters?|л)\b'),('t',r'(?:за|per|/)\s*(?:1\s*)?(?:тонн\w*|tonnes?|tons?)\b')]
            scope=next((name for name,p in scopes if re.search(p,left+right,re.I)),None)
            sale=bool(scope or re.search(r'прода\w*|предлага\w*|цен\w*|стоим\w*|offer|sell|sale|price|бағасы',left,re.I) or re.search(r'(?:по|за|for)\s*$',left,re.I))
            if not sale:continue
            result.extend([('sale_offer_amount',value,evidence,f'{currency}/{scope}' if scope else None),('sale_offer_currency',currency,evidence,None)])
            if scope:result.append(('sale_offer_scope',scope,evidence,None))
            if scope=='batch' and currency=='KZT':result.append(('batch_sale_price_kzt',value,evidence,'KZT/batch'))
    for name in {r[0] for r in result}:
        if len({r[1] for r in result if r[0]==name})>1:
            raise ValueError('Ambiguous multiple prices for '+name+'; clarify which offer applies')
    return list(dict.fromkeys(result))
