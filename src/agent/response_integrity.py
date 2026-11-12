"""Conservative checks for clearly incomplete or duplicated model output."""
import re
from difflib import SequenceMatcher


def check_response(payload, *, finish_reason=None, limits=None):
    """Return actionable issues; absence of a final period alone is allowed."""
    limits=limits or {'conclusion':350,'explanation':350,'next_question':100}
    issues=[]
    if finish_reason in {'length','max_tokens','max_output_tokens'}:
        issues.append('generation_truncated')
    fields=['conclusion','explanation','next_question']
    fields += [f'limitations[{i}]' for i in range(len(payload.get('limitations',[])))]
    values={key:payload.get(key) for key in ('conclusion','explanation','next_question')}
    values.update({f'limitations[{i}]':v for i,v in enumerate(payload.get('limitations',[]))})
    for key in fields:
        value=values.get(key)
        if not isinstance(value,str) or not value.strip():continue
        s=value.strip();limit=limits.get(key,120 if key.startswith('limitations[') else None)
        if re.search(r'(?:[,;:]|[-–—]|\b(?:и|или|но|для|при|поскольку|потому что|and|or|because|for|with|және|немесе))\s*$',s,re.I):
            issues.append('incomplete_enumeration_or_clause')
        if limit and len(value)>=limit-2 and not re.search(r'[.!?…:;»”\])}]$',s):
            issues.append('text_at_limit_incomplete')
        if re.search(r'(?:^|\n)\s*(?:[-*•]|\d+[.)])\s*$',s):
            issues.append('incomplete_enumeration_or_clause')
    a=values.get('conclusion') or '';b=values.get('explanation') or ''
    def norm(text):return ' '.join(re.findall(r'\w+',text.casefold()))
    x,y=norm(a),norm(b)
    xwords,ywords=set(x.split()),set(y.split())
    token_overlap=(len(xwords & ywords)/min(len(xwords),len(ywords)) if xwords and ywords else 0)
    token_jaccard=(len(xwords & ywords)/len(xwords | ywords) if xwords or ywords else 0)
    if min(len(x),len(y))>=65 and (SequenceMatcher(None,x,y).ratio()>=.83 or min(len(x),len(y))>=100 and (x in y or y in x)
                                  or min(len(xwords),len(ywords))>=15 and token_overlap>=.84 and token_jaccard>=.60):
        issues.append('repeated_model_text')
    return list(dict.fromkeys(issues))
