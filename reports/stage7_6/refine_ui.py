from pathlib import Path
p=Path('frontend/src/AdvisorResults.tsx');s=p.read_text(encoding='utf-8').replace('names[c.material]??c.material','names[c.material]??c.display_name??c.material');p.write_text(s,encoding='utf-8')
p=Path('frontend/src/pages/SubstrateAdvisor.tsx');s=p.read_text(encoding='utf-8').replace("{material:e.target.value,material_state:'unknown'}","{material:e.target.value,material_state:'unknown',properties:{}}")
s=s.replace('placeholder="\u041d\u0435 \u0438\u0437\u043c\u0435\u0440\u0435\u043d\u043e" onChange=', 'placeholder="\u041d\u0435 \u0438\u0437\u043c\u0435\u0440\u0435\u043d\u043e" value={typeof r.properties?.[p.key]===\'number\'?r.properties[p.key] as number:\'\'} onChange=')
p.write_text(s,encoding='utf-8')
