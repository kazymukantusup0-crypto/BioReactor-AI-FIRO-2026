import { useState } from 'react'
import type { AdvisorResult, Bounds, MixtureComparison } from './advisorApi'
import CompactAdvisorResults from './CompactAdvisorResults'
import { locale, localized, tr } from './i18n'
const span = (v?: Bounds | null) => v == null ? tr('functionalResults.1') : v.low === v.high ? v.low.toLocaleString(locale(), { maximumSignificantDigits: 6 }) : `${v.low.toLocaleString(locale(), { maximumSignificantDigits: 6 })}–${v.high.toLocaleString(locale(), { maximumSignificantDigits: 6 })}`
const statuses: Record<string, string> = localized(() => ({ PHYSICALLY_INFEASIBLE: tr('functionalResults.2'), REQUIRES_REVIEW: tr('functionalResults.3'), GEOMETRY_ONLY_CONSISTENT: tr('functionalResults.4') }))
const labels: Record<string, string> = localized(() => ({ inoculum_volume_l: tr('functionalResults.5'), dilution_water_l: tr('functionalResults.6'), resident_liquid_volume_l: tr('functionalResults.7'), operating_mode: tr('functionalResults.8'), reactor_working_volume_l: tr('functionalResults.9'), headspace_l: tr('functionalResults.10'), reactor_total_volume_l: tr('functionalResults.11') }))
const missingLabel = (key: string) => key.startsWith('volume_or_density:') ? tr('functionalResults.12', { v0: key.split(':')[1] }) : labels[key] ?? key
const scenarioNames: Record<string, string> = localized(() => ({ A_sell_feedstock: tr('functionalResults.13'), B_heat: tr('functionalResults.14'), C_electricity: tr('functionalResults.15'), CHP: tr('functionalResults.16'), D_sell_gas: tr('functionalResults.17'), E_digestate: tr('functionalResults.18') }))
const levels: Record<string, string> = localized(() => ({ MEASURED: tr('functionalResults.19'), CALCULATED: tr('functionalResults.20'), PREDICTED: tr('functionalResults.21'), USER_REPORTED: tr('functionalResults.22'), LITERATURE_ESTIMATE: tr('functionalResults.23'), HYPOTHETICAL_SCENARIO: tr('functionalResults.24'), UNAVAILABLE: tr('functionalResults.25') }))
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
  return <section aria-label={tr('functionalResults.26')}>
    <p><strong>{levels[String(selected.result_level ?? selected.mixture.result_level)] ?? tr('functionalResults.27')}</strong>{tr('functionalResults.28')}</p>
    {cases.length > 1 && <label>{tr('functionalResults.29')}<select aria-label={tr('functionalResults.29')} value={Math.min(index, cases.length - 1)} onChange={e => setIndex(Number(e.target.value))}>{cases.map((c, i) => <option value={i} key={i}>{i + 1}: {c.mixture.components.map(row => String(row.profile_id ?? row.material)).join(' + ')}</option>)}</select></label>}
    {result.scenarios_truncated === true && <p>{tr('functionalResults.30')} {cases.length} {tr('functionalResults.31')} {String(result.candidate_count)} {tr('functionalResults.32')}</p>}
    <CompactAdvisorResults result={selected} comparison={comparison} names={names} />
    {g && <section className="decision-card"><h2>{tr('functionalResults.33')}</h2><p>{tr('functionalResults.34')} <strong>{statuses[g.status] ?? g.status}</strong>{tr('functionalResults.35')}</p><dl><dt>{tr('functionalResults.36')}</dt><dd data-testid="known-charge">{span(g.known_charge_present ? g.known_charge_volume_l : null)}</dd><dt>{tr('functionalResults.37')}</dt><dd>{span(g.complete_charge_volume_l)}</dd><dt>{tr('functionalResults.38')}</dt><dd>{span(g.remaining_total_volume_l)}</dd><dt>{tr('functionalResults.39')}</dt><dd>{span(g.feed_plus_water_ts_fraction)}</dd></dl><p>{tr('functionalResults.40')}</p>{g.violations.length > 0 && <p role="alert">{tr('functionalResults.41')} {g.violations.join(', ')}</p>}<p>{tr('functionalResults.42')} {g.missing.map(missingLabel).join(', ') || tr('functionalResults.43')}</p>{g.warnings.map(w => <p key={w}>{w}</p>)}</section>}
    <section className="decision-card"><h2>{tr('functionalResults.44')}</h2><p>{tr('functionalResults.45')}</p><div style={{ overflowX: 'auto' }}><table><thead><tr><th>{tr('functionalResults.46')}</th><th>{tr('functionalResults.47')}</th><th>{tr('functionalResults.48')}</th><th>{tr('functionalResults.49')}</th></tr></thead><tbody>{rows.map(row => <tr key={row.id}><td>{scenarioNames[row.id] ?? row.id}</td><td>{span(row.gross_benefit_reference_kzt)}</td><td>{span(row.total_cost_kzt)}</td><td>{span(row.net_result_kzt)}</td></tr>)}</tbody></table></div>
    <details><summary>{tr('functionalResults.50')}</summary><pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{JSON.stringify({ prices: a.prices, break_even: a.scenarios, partial: a.partial_economics, reactor_balance: a.reactor_balance }, null, 2)}</pre></details></section>
    <details><summary>{tr('functionalResults.51')}</summary><ul>{assumptions.map((note, i) => <li key={i}>{typeof note === 'string' ? note : JSON.stringify(note)}</li>)}</ul></details>
  </section>
}
