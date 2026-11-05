import { useState } from 'react'
import type { AdvisorResult, Bounds, MixtureComparison } from './advisorApi'
import CompactAdvisorResults from './CompactAdvisorResults'
const span = (v?: Bounds | null) => v == null ? 'Не определено' : v.low === v.high ? v.low.toLocaleString('ru', { maximumSignificantDigits: 6 }) : `${v.low.toLocaleString('ru', { maximumSignificantDigits: 6 })}–${v.high.toLocaleString('ru', { maximumSignificantDigits: 6 })}`
const statuses: Record<string, string> = { PHYSICALLY_INFEASIBLE: 'Загрузка или размеры противоречат вместимости', REQUIRES_REVIEW: 'Нужны дополнительные параметры', GEOMETRY_ONLY_CONSISTENT: 'Заданные объёмы согласуются' }
const labels: Record<string, string> = { inoculum_volume_l: 'объём инокулюма', dilution_water_l: 'объём воды', resident_liquid_volume_l: 'остаток жидкости', operating_mode: 'режим загрузки', reactor_working_volume_l: 'рабочий объём', headspace_l: 'газовое пространство', reactor_total_volume_l: 'полный объём' }
const missingLabel = (key: string) => key.startsWith('volume_or_density:') ? `объём или плотность компонента ${key.split(':')[1]}` : labels[key] ?? key
const scenarioNames: Record<string, string> = { A_sell_feedstock: 'Продажа сырья', B_heat: 'Тепло / условное замещение нагрева', C_electricity: 'Электричество', CHP: 'Когенерация', D_sell_gas: 'Продажа газа', E_digestate: 'Дигестат' }
const levels: Record<string, string> = { MEASURED: 'Расчёт по введённым свойствам', USER_REPORTED: 'Расчёт по пользовательским данным', LITERATURE_ESTIMATE: 'Литературный ориентир', HYPOTHETICAL_SCENARIO: 'Условный сценарий', UNAVAILABLE: 'Показатель неизвестен' }
type Geometry = { status: string; known_charge_present: boolean; known_charge_volume_l: Bounds; complete_charge_volume_l: Bounds | null; remaining_total_volume_l: Bounds | null; feed_plus_water_ts_fraction: Bounds | null; missing: string[]; violations: string[]; warnings: string[] }
type EconomicRow = { id: string; gross_benefit_reference_kzt?: Bounds; net_result_kzt?: Bounds; total_cost_kzt?: Bounds; missing?: string[] }
export default function FunctionalResults({ result, comparison, names }: { result: AdvisorResult; comparison: MixtureComparison | null; names: Record<string, string> }) {
  const [index, setIndex] = useState(0)
  const cases = (result.scenario_results as AdvisorResult[] | undefined) ?? [result]
  const selected = cases[Math.min(index, cases.length - 1)]
  const g = selected.engineering as Geometry | undefined
  const a = selected.decision_analysis
  const rows = (a.scenarios ?? []) as EconomicRow[]
  const assumptions = (selected.scenario_assumptions ?? []) as string[]
  return <section aria-label="Проверяемые результаты">
    <p><strong>{levels[String(selected.result_level ?? selected.mixture.result_level)] ?? 'Расчёт с указанными ограничениями'}</strong>. Расчёт потенциала не является измерением выработки установки.</p>
    {cases.length > 1 && <label>Научный сценарий<select aria-label="Научный сценарий" value={Math.min(index, cases.length - 1)} onChange={e => setIndex(Number(e.target.value))}>{cases.map((c, i) => <option value={i} key={i}>{i + 1}: {c.mixture.components.map(row => String(row.profile_id ?? row.material)).join(' + ')}</option>)}</select></label>}
    {result.scenarios_truncated === true && <p>Показаны первые {cases.length} из {String(result.candidate_count)} сочетаний исследований. Это ограниченная выборка сценариев, не поиск оптимальной смеси.</p>}
    <CompactAdvisorResults result={selected} comparison={comparison} names={names} />
    {g && <section className="decision-card"><h2>Баланс загрузки</h2><p>Статус: <strong>{statuses[g.status] ?? g.status}</strong>. Это проверка геометрии, не разрешение эксплуатации.</p><dl><dt>Известная часть загрузки, л</dt><dd data-testid="known-charge">{span(g.known_charge_present ? g.known_charge_volume_l : null)}</dd><dt>Полная загрузка, л</dt><dd>{span(g.complete_charge_volume_l)}</dd><dt>Остаток полного объёма, л</dt><dd>{span(g.remaining_total_volume_l)}</dd><dt>Доля TS сырья с водой, кг/кг</dt><dd>{span(g.feed_plus_water_ts_fraction)}</dd></dl><p>Раздельные объёмы условно суммируются; фактическая укладка не измерена. Состав инокулюма не включён в долю TS. Для воды принято 1 кг/л.</p>{g.violations.length > 0 && <p role="alert">Нарушения: {g.violations.join(', ')}</p>}<p>Для полной проверки: {g.missing.map(missingLabel).join(', ') || 'геометрические параметры заданы'}</p>{g.warnings.map(w => <p key={w}>{w}</p>)}</section>}
    <section className="decision-card"><h2>Доступная экономика партии</h2><p>Варианты использования одного газа альтернативны. Валовая ценность — до затрат; неизвестные затраты не равны нулю.</p><div style={{ overflowX: 'auto' }}><table><thead><tr><th>Вариант</th><th>Валовая ценность, KZT</th><th>Затраты, KZT</th><th>Чистый результат, KZT</th></tr></thead><tbody>{rows.map(row => <tr key={row.id}><td>{scenarioNames[row.id] ?? row.id}</td><td>{span(row.gross_benefit_reference_kzt)}</td><td>{span(row.total_cost_kzt)}</td><td>{span(row.net_result_kzt)}</td></tr>)}</tbody></table></div>
    <details><summary>Цены, даты, ограничения и точка безубыточности</summary><pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{JSON.stringify({ prices: a.prices, break_even: a.scenarios, partial: a.partial_economics, reactor_balance: a.reactor_balance }, null, 2)}</pre></details></section>
    <details><summary>Допущения выбранного исследования</summary><ul>{assumptions.map((note, i) => <li key={i}>{typeof note === 'string' ? note : JSON.stringify(note)}</li>)}</ul></details>
  </section>
}
