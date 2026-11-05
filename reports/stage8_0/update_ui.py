from pathlib import Path
root=Path(__file__).resolve().parents[2]
p=root/'frontend/src/pages/SubstrateAdvisor.tsx';s=p.read_text(encoding='utf-8')
s=s.replace("import '../advisor.css'","import '../advisor.css'\nimport MaterialPropertiesFields from '../MaterialPropertiesFields'")
s=s.replace("slurry:'Навозная жижа'","slurry:'Жидкий'").replace("fresh_solid:'Свежий твёрдый'","fresh_solid:'Твёрдый'")
s=s.replace("material:e.target.value,material_state:'unknown',properties:{}","material:e.target.value,material_state:'unknown',animal:undefined,physical_state:'unknown',decay_state:'unknown',bedding:'unknown',properties:{}")
s=s.replace("change(r.id,{material_state:e.target.value})","change(r.id,{material_state:e.target.value,physical_state:({slurry:'liquid',semiliquid:'semiliquid',fresh_solid:'solid',dry:'dry',bedded:'bedded'} as Record<string,string>)[e.target.value]??'unknown'})")
s=s.replace("{['kg','L'].map(u=><option","{['g','kg','t','mL','L','m3'].map(u=><option").replace("L:'л',m3:'м³'","L:'л',mL:'мл',m3:'м³'")
s=s.replace('</select></label></div><details className="advisor-measurements">','</select></label></div><MaterialPropertiesFields row={r} index={i+1} onChange={patch=>change(r.id,patch)}/><details className="advisor-measurements">')
assert 'MaterialPropertiesFields row=' in s
p.write_text(s,encoding='utf-8')
p=root/'frontend/src/CompactAdvisorResults.tsx';s=p.read_text(encoding='utf-8')
s=s.replace('<h2>Оценка состава</h2>','<h2>Оценка состава</h2><div className="conversion-summary" data-testid="conversion-summary">{effective.mixture.components.map(c=><p key={c.id}>{names[c.material]??c.display_name??c.material}: {c.quantity} {c.unit} → {span(c.wet_mass_kg,\'кг\')}; объём {span(c.volume_l??null,\'л\')}</p>)}</div>')
s=s.replace('Срок вашей партии пока неизвестен; длительность лабораторного испытания его не заменяет','{effective.duration.studies.length?`В опубликованных опытах: ${Array.from(new Set(effective.duration.studies.flatMap(s=>s.days))).join(\' / \')} дней; это длительность испытаний, а не срок вашей партии`:\'Срок вашей партии пока неизвестен; длительность лабораторного испытания его не заменяет\'}')
p.write_text(s,encoding='utf-8')
