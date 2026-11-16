import type { AdvisorDecision } from './advisorApi'
import { tr } from './i18n'

export default function ScenarioControls({ value, onChange, region }: { value: AdvisorDecision; onChange: (value: AdvisorDecision) => void; region: string }) {
  const reactor = value.reactor ?? {}
  const edit = (key: string, v: unknown) => onChange({ ...value, [key]: v })
  const editReactor = (key: string, v: unknown) => edit('reactor', { ...reactor, [key]: v })
  const costs = (value.costs ?? {}) as Record<string, { low: number; high: number }>
  const point = (v: number) => ({ low: v, high: v, provenance: 'USER_REPORTED', evidence: 'Explicit Dashboard scenario input; not independently measured' })
  const quotes = (value.quotes ?? {}) as Record<string, Record<string, unknown>>
  const quote = quotes.electricity ?? {}
  const quoteEdit = (key: string, v: unknown) => edit('quotes', { ...quotes, electricity: { commodity: 'electricity', unit: 'KZT/kWh', currency: 'KZT', source: tr('scenarioControls.1'), ...quote, region, [key]: v } })
  return <details className="advisor-reactor"><summary>{tr('scenarioControls.2')}</summary>
    <p>{tr('scenarioControls.3')}</p>
    <div className="advisor-input-grid">
      {Object.entries({ dilution_water_l: tr('scenarioControls.4'), headspace_l: tr('scenarioControls.5'), resident_liquid_volume_l: tr('scenarioControls.6'), temperature_c: tr('scenarioControls.7'), initial_temperature_c: tr('scenarioControls.8'), ambient_temperature_c: tr('scenarioControls.9'), heated_mass_kg: tr('scenarioControls.10'), heat_capacity_kj_kg_k: tr('scenarioControls.11'), heat_loss_coefficient_w_k: tr('scenarioControls.12'), duration_days: tr('scenarioControls.13'), heater_efficiency: tr('scenarioControls.14'), auxiliary_energy_kwh: tr('scenarioControls.15') }).map(([key, label]) =>
        <label key={key}>{label}<input type="number" step="any" value={reactor[key] == null ? '' : String(reactor[key])} onChange={e => editReactor(key, e.target.value === '' ? undefined : Number(e.target.value))} /></label>)}
      <label>{tr('scenarioControls.16')}<select value={String(reactor.heating_carrier ?? '')} onChange={e => editReactor('heating_carrier', e.target.value || undefined)}><option value="">{tr('scenarioControls.17')}</option><option value="electricity">{tr('scenarioControls.18')}</option><option value="process_heat">{tr('scenarioControls.19')}</option><option value="external_heat">{tr('scenarioControls.20')}</option></select></label>
      <label>{tr('scenarioControls.21')}<select value={String(value.gas_use ?? 'unknown')} onChange={e => edit('gas_use', e.target.value)}><option value="unknown">{tr('scenarioControls.22')}</option><option value="heat">{tr('scenarioControls.23')}</option><option value="electricity">{tr('scenarioControls.18')}</option><option value="chp">{tr('scenarioControls.24')}</option><option value="sell_gas">{tr('scenarioControls.25')}</option></select></label>
      {Object.entries({ recovery_fraction: tr('scenarioControls.26'), thermal_efficiency: tr('scenarioControls.27'), electrical_efficiency: tr('scenarioControls.28'), methane_fraction: tr('scenarioControls.29') }).map(([key, label]) => <label key={key}>{label}<input type="number" min="0" max="1" step="any" value={(value[key] as { low?: number } | undefined)?.low ?? ''} onChange={e => edit(key, e.target.value === '' ? undefined : point(Number(e.target.value)))} /></label>)}
      {Object.entries({ preparation: tr('scenarioControls.30'), maintenance: tr('scenarioControls.31'), storage: tr('scenarioControls.32'), transport: tr('scenarioControls.33'), gas_cleaning: tr('scenarioControls.34'), digestate_handling: tr('scenarioControls.35'), packaging: tr('scenarioControls.36') }).map(([key, label]) => <label key={key}>{label}{tr('scenarioControls.37')}<input type="number" min="0" step="any" value={costs[key]?.low ?? ''} onChange={e => edit('costs', { ...costs, [key]: e.target.value === '' ? undefined : point(Number(e.target.value)) })} /></label>)}
    </div>
    <label className="advisor-checkbox"><input type="checkbox" checked={reactor.energy_scope === 'entire_batch'} onChange={e => editReactor('energy_scope', e.target.checked ? 'entire_batch' : undefined)} />{tr('scenarioControls.38')}</label>
    <label className="advisor-checkbox"><input type="checkbox" checked={value.all_operating_costs_included === true} onChange={e => edit('all_operating_costs_included', e.target.checked)} />{tr('scenarioControls.39')}</label>
    <label className="advisor-checkbox"><input type="checkbox" checked={value.assume_full_self_consumption === true} onChange={e => edit('assume_full_self_consumption', e.target.checked)} />{tr('scenarioControls.40')}</label>
    <label className="advisor-checkbox"><input type="checkbox" checked={value.replacement_heat_source === 'electric_resistance'} onChange={e => edit('replacement_heat_source', e.target.checked ? 'electric_resistance' : 'unknown')} />{tr('scenarioControls.41')}</label>
    <details><summary>{tr('scenarioControls.42')}</summary><p>{tr('scenarioControls.43')} {region}.</p><div className="advisor-input-grid">
      <label>{tr('scenarioControls.44')}<input type="number" min="0" step="any" value={quote.value == null ? '' : String(quote.value)} onChange={e => { if (e.target.value === '') { const rest = { ...quotes }; delete rest.electricity; edit('quotes', rest) } else quoteEdit('value', Number(e.target.value)) }} /></label>
      <label>{tr('scenarioControls.45')}<input type="date" disabled={quote.value == null} value={String(quote.published_at ?? '')} onChange={e => quoteEdit('published_at', e.target.value || undefined)} /></label>
      <label>{tr('scenarioControls.46')}<input disabled={quote.value == null} value={String(quote.source ?? '')} onChange={e => quoteEdit('source', e.target.value)} /></label>
      <label>{tr('scenarioControls.47')}<input disabled={quote.value == null} placeholder={tr('scenarioControls.48')} value={String(value.consumer_class ?? '')} onChange={e => onChange({ ...value, consumer_class: e.target.value || undefined, quotes: { ...quotes, electricity: { ...quote, consumer_class: e.target.value || undefined } } })} /></label>
    </div><label className="advisor-checkbox"><input type="checkbox" disabled={quote.value == null} checked={quote.confirmed === true} onChange={e => quoteEdit('confirmed', e.target.checked)} />{tr('scenarioControls.49')}</label></details>
    <p>{tr('scenarioControls.50')}</p>
  </details>
}
