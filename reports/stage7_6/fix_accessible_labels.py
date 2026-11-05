from pathlib import Path
p=Path('frontend/src/pages/SubstrateAdvisor.tsx');s=p.read_text(encoding='utf-8')
for key,label in [('material','\u0421\u044b\u0440\u044c\u0451'),('material_state','\u0421\u043e\u0441\u0442\u043e\u044f\u043d\u0438\u0435'),('unit','\u0415\u0434\u0438\u043d\u0438\u0446\u044b')]:
    s=s.replace('<select value={r.'+key+'}', '<select aria-label={`'+label+' ${i+1}`} value={r.'+key+'}')
p.write_text(s,encoding='utf-8')
