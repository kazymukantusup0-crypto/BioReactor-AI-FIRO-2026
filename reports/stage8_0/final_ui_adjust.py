from pathlib import Path
p=Path(__file__).resolve().parents[2]/'frontend/src/pages/SubstrateAdvisor.tsx';s=p.read_text(encoding='utf-8')
s=s.replace("['kg','L'].includes(c.unit)","['g','kg','t','mL','L','m3'].includes(c.unit)")
s=s.replace("slurry:'Жидкий'","slurry:'Жидкий',semiliquid:'Полужидкий'")
old="['unknown',...(catalog.data?.materials.find(m=>m.id===r.material)?.physical_states??[]).filter(x=>x!=='unknown')]"
new="(r.material==='manure'||r.material.endsWith('_manure')?['unknown','slurry','semiliquid','fresh_solid','dry','bedded']:['unknown',...(catalog.data?.materials.find(m=>m.id===r.material)?.physical_states??[]).filter(x=>x!=='unknown')])"
assert old in s;s=s.replace(old,new)
p.write_text(s,encoding='utf-8')
