from pathlib import Path
p=Path('frontend/src/AdvisorResults.tsx');s=p.read_text(encoding='utf-8')
needle=' <section className="decision-card" data-testid="process-recommendations">'
insert=''' <section className="decision-card"><h3>Подготовка и применимость сырья</h3><p>Для переноса результатов важно совпадение физического состояния и подготовки исследованного образца.</p>{m.components.some(c=>c.material==='food_waste')&&<p>Пищевой профиль относится к измельчённой столовой пульпе. Он не подтверждает характеристики отходов с упаковкой или неизвестным составом; отдельно проверяются загрязнения и склонность к закислению.</p>}{m.components.some(c=>c.material==='cattle_manure')&&<p>Жижа и навоз с подстилкой имеют разные профили. Нельзя переносить плотность жижи на сухой, компостированный или подстилочный навоз.</p>}{m.components.some(c=>['grass','straw','plant_residue'].includes(c.material))&&<p>Для растительных остатков важны вид, зрелость, влажность и подготовка. Подходящий выход для вашей партии пока не установлен; затраты подготовки неизвестны.</p>}</section>
'''
s=s.replace(needle,insert+needle)
s=s.replace('<th>Прибыль / срок / стабильность</th>','<th>Энергозатраты реактора</th><th>Чистый результат</th><th>Срок / стабильность</th>')
s=s.replace('<td>Требуют данных о расходах, кинетике и взаимодействии</td>',"<td>{c.result.decision_analysis.reactor_balance?.total_energy_kwh == null ? 'Нужны данные' : `${number(c.result.decision_analysis.reactor_balance.total_energy_kwh,2)} кВт·ч`}</td><td>{c.result.decision_analysis.scenarios?.filter(x=>x.net_result_kzt).map(x=>span(x.net_result_kzt,'₸')).join(' / ')||'Нужны цены и все расходы'}</td><td>Нужна проверка кинетики и взаимодействия</td>")
p.write_text(s,encoding='utf-8')
