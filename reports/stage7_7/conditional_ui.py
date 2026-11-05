from pathlib import Path
p=Path('frontend/src/pages/SubstrateAdvisor.tsx');s=p.read_text(encoding='utf-8').replace('[commonBasis,setCommonBasis]=useState(false)','[commonBasis,setCommonBasis]=useState(true)').replace('Условно считать неизвестную влажность газа сопоставимой с сухим газом для суммирования разных исследований','Показать условный ориентир смеси, предполагая сопоставимые условия объёма газа');p.write_text(s,encoding='utf-8')
p=Path('frontend/src/CompactAdvisorResults.tsx');s=p.read_text(encoding='utf-8').replace('<dt>Температура</dt>', '<dt>Температура</dt>')
needle='<p>Литературная оценка не гарантирует реальную выработку; для смеси взаимодействие компонентов требует проверки.</p>'
s=s.replace(needle,needle+"{!biogas?.potential_biogas_m3&&<p>Для общего биогаза нужна подходящая доля метана; метан уже входит в общий газ.</p>}{Array.isArray(effective.mixture.normalization)&&effective.mixture.normalization.length>0&&effective.mixture.additive_methane_reference_m3&&<p>Сопоставимость влажности и условий объёма газа здесь принята условно; исходные сведения сохранены в подробностях.</p>}")
p.write_text(s,encoding='utf-8')
p=Path('frontend/tests/advisor.test.tsx');s=p.read_text(encoding='utf-8').replace('expect(input.assume_common_dry_gas_basis).toBe(false)','expect(input.assume_common_dry_gas_basis).toBe(true)');p.write_text(s,encoding='utf-8')
