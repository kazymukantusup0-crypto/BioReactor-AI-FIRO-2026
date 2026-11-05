"""Export the runtime dossiers without modifying any reviewed numerical profiles."""
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.research.dossiers import search

out=ROOT/'reports/stage8_5';out.mkdir(exist_ok=True)
data=search()
(out/'scientific_dossiers.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
lines=['# Научные досье восьми материалов', '',
       'Параметры ниже принадлежат отдельным опубликованным образцам. Между исследованиями они не объединяются в универсальные диапазоны. '
       'TS и VS указаны долями влажной массы, BMP — мл CH₄/г VS. Литературные значения не являются измерениями пользовательской партии.', '']
def fmt(value):
    if value is None:return 'не установлено'
    if isinstance(value,dict) and 'low' in value:return str(value['low']) if value['low']==value['high'] else f"{value['low']}–{value['high']}"
    return json.dumps(value,ensure_ascii=False)
for d in data['dossiers']:
    lines+=['## '+d['name'], '', d['selection_rationale'], '',
            'Формы: '+', '.join(d['physical_states'])+'.', '',
            '| Профиль | Форма | TS | VS | BMP |', '|---|---|---|---|---|']
    for s in d['studies']:
        lines.append('| '+' | '.join([s['profile_id'],s['physical_state'],fmt(s['ts_fraction']),fmt(s['vs_fraction_wet']),fmt(s['bmp_ml_ch4_g_vs'])])+' |')
    lines+=['', '### Условия и переносимость', '']
    for s in d['studies']:
        lines += ['- **'+s['profile_id']+'**. Подготовка: '+str(s['preparation'])+'. Условия: '+fmt(s['conditions'])+'.']
    lines+=['', 'Риски: '+', '.join(d['inhibition_risks'])+'.', '',
            'Безопасный предел органической нагрузки: не установлен. Опытная загрузка, ISR и длительность сохраняются в условиях отдельного источника; универсальный OLR из них не выводится.', '',
            'Совместимость: '+d['co_digestion'], '',
            'Перенос на установку требует измерений состава партии, инокулята, нагрузки и фактического извлечения газа. '
            'Продолжительность BMP-теста не считается временем достижения полного выхода на реальной установке.', '',
            '### Источники', '']
    for s in d['sources']:
        lines+=['- ['+s['title']+']('+s['url']+'). DOI: '+str(s.get('doi','не указан'))+'. '
                'Качество: локальная проверенная выписка из опубликованной работы; независимое повторение не выполнено.']
    lines+=['']
(out/'scientific_dossiers.md').write_text('\n'.join(lines),encoding='utf-8')
print('Exported',len(data['dossiers']),'dossiers')
