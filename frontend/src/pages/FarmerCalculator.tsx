// «Сырьё и смеси» for a farmer: choose the feedstock -> type the amount -> the cards appear at once.
// The numbers come from the AI agent's own Python tool (estimate_methane), so the page and the chat agree.
import { useEffect, useMemo, useRef, useState } from 'react'
import { BookOpen, Clock, Flame, MessageSquare, Plus, Trash2, Wind, Zap } from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import { advisorApi } from '../advisorApi'
import { useQuery } from '../hooks'
import { locale, materialName, tr, useI18n } from '../i18n'
// design-v3: result cards alternate light «paper» and dark
const FARM_TONE = ['paper', 'dark', 'dark', 'paper'] as const
import { askAgentQuestion, CHAT_PREFILL_KEY, substratesApi, type EstimateResult, type EstimateRow, type FarmUnit, type Range } from '../substratesApi'

const STORAGE = 'bioreactor-farm-calculator-v10'
const SIMPLE_UNITS: FarmUnit[] = ['kg', 't', 'L', 'm3']
const ALL_UNITS: FarmUnit[] = ['kg', 't', 'g', 'L', 'm3', 'mL']
// The states the agent's chat parser understands in ru / kk / en (askAgentTemplates.json); «unknown» = the agent assumes.
const STATES = ['unknown', 'slurry', 'fresh_solid', 'dry']
interface Row { id: string; material: string; state: string; quantity: string; unit: FarmUnit }
const newId = () => Math.random().toString(36).slice(2, 10)
const DEFAULT_ROWS: Row[] = [{ id: 'r1', material: 'cattle_manure', state: 'unknown', quantity: '200', unit: 'L' }]

function load(): Row[] {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(STORAGE) ?? 'null')
    if (Array.isArray(value) && value.length > 0 && value.length <= 8 && value.every(row => row && typeof row.material === 'string'
      && typeof row.quantity === 'string' && ALL_UNITS.includes(row.unit) && STATES.includes(row.state))) return value as Row[]
  } catch { /* no saved rows */ }
  return DEFAULT_ROWS
}

/** Problem with the typed amount, or null when it is a usable number. */
export function amountError(raw: string): string | null {
  const text = raw.trim().replace(',', '.')
  if (!text) return tr('farm.err.empty')
  const value = Number(text)
  if (!Number.isFinite(value)) return tr('farm.err.number')
  if (value <= 0) return tr('farm.err.positive')
  if (value > 1e9) return tr('farm.err.big')
  return null
}

/** 2 significant digits, like the agent's numbers in the chat. */
export const num = (value: number) => value.toLocaleString(locale(), { maximumSignificantDigits: 2 })
export const range = (r?: Range | null) => !r ? '—' : num(r.low) === num(r.high) ? num(r.low) : `${num(r.low)}–${num(r.high)}`
const mid = (r: Range) => (r.low + r.high) / 2

export default function FarmerCalculator({ scientific }: { scientific: boolean }) {
  const { lang } = useI18n()
  const catalog = useQuery('advisor-catalog', advisorApi.catalog)
  const withData = useQuery('substrates-with-data', substratesApi.materials)
  const [rows, setRows] = useState<Row[]>(load)
  const [result, setResult] = useState<EstimateResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const sequence = useRef(0)

  useEffect(() => { try { localStorage.setItem(STORAGE, JSON.stringify(rows)) } catch { /* optional */ } }, [rows])
  const known = useMemo(() => new Set(withData.data?.with_data ?? []), [withData.data])
  const materials = catalog.data?.materials ?? []
  const nameOf = (id: string) => materialName(materials.find(m => m.id === id)?.name) || id
  const options = materials.filter(m => scientific || known.has(m.id) || rows.some(r => r.material === m.id))
  const units = scientific ? ALL_UNITS : SIMPLE_UNITS

  const errors = rows.map(row => amountError(row.quantity))
  const valid = rows.length > 0 && errors.every(e => e === null)
  const request: EstimateRow[] = rows.map(row => ({ material: row.material, quantity: Number(row.quantity.trim().replace(',', '.')), unit: row.unit,
    ...(row.state !== 'unknown' ? { state: row.state } : {}) }))
  const key = JSON.stringify([request, lang])

  useEffect(() => {
    if (!valid) return
    const epoch = ++sequence.current
    const controller = new AbortController()
    const timer = window.setTimeout(() => {
      setBusy(true)
      substratesApi.estimate(JSON.parse(key)[0] as EstimateRow[], lang, controller.signal)
        .then(value => { if (epoch === sequence.current) { setResult(value); setError('') } })
        .catch(cause => { if (!controller.signal.aborted && epoch === sequence.current) setError(tr('farm.err.server', { v0: cause instanceof Error ? cause.message : String(cause) })) })
        .finally(() => { if (epoch === sequence.current) setBusy(false) })
    }, 350)
    return () => { window.clearTimeout(timer); controller.abort() }
  }, [key, valid, lang])

  const change = (id: string, patch: Partial<Row>) => setRows(old => old.map(row => row.id === id ? { ...row, ...patch } : row))
  const add = () => setRows(old => [...old, { id: newId(), material: old.some(r => r.material === 'food_waste') ? 'straw' : 'food_waste', state: 'unknown', quantity: '20', unit: 'kg' }])
  const ask = () => {
    try { sessionStorage.setItem(CHAT_PREFILL_KEY, askAgentQuestion(request, lang, nameOf)) } catch { /* the chat opens empty */ }
    window.location.hash = '/chat'
  }

  const data = result?.data
  const ok = result?.ok && data?.status === 'ok'  // with a bad amount the last valid result stays, dimmed
  const parts = data?.components ?? []
  return <div className="farm">
    <section className="farm-input v3-card v3-card-dark" aria-label={tr('farm.input')}>
      <div className="farm-rows">
        <AnimatePresence initial={false}>
          {rows.map((row, index) => {
            const material = materials.find(m => m.id === row.material)
            const states = STATES.filter(s => s === 'unknown' || material?.form_states.some(f => f.value === s))
            const showState = row.material.endsWith('_manure') && states.length > 1
            return <motion.div key={row.id} className="farm-row" layout initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, height: 0 }} transition={{ duration: .18 }}>
              <label className="farm-field farm-material"><span>{tr('farm.material')}{rows.length > 1 ? ` ${index + 1}` : ''}</span>
                <select data-testid={`farm-material-${index}`} value={row.material} onChange={e => change(row.id, { material: e.target.value, state: 'unknown' })}>
                  {options.map(m => <option key={m.id} value={m.id}>{materialName(m.name)}{known.has(m.id) ? '' : ` — ${tr('farm.noData')}`}</option>)}
                </select></label>
              {showState && <label className="farm-field farm-state"><span>{tr('farm.state')}</span>
                <select data-testid={`farm-state-${index}`} value={row.state} onChange={e => change(row.id, { state: e.target.value })}>
                  {states.map(s => <option key={s} value={s}>{tr(`farm.state.${s}`)}</option>)}
                </select></label>}
              <label className="farm-field farm-amount"><span>{tr('farm.amount')}</span>
                <input data-testid={`farm-amount-${index}`} inputMode="decimal" value={row.quantity} aria-invalid={errors[index] !== null}
                  aria-describedby={errors[index] ? `farm-error-${row.id}` : undefined} onChange={e => change(row.id, { quantity: e.target.value })} /></label>
              <label className="farm-field farm-unit"><span>{tr('farm.unit')}</span>
                <select data-testid={`farm-unit-${index}`} value={row.unit} onChange={e => change(row.id, { unit: e.target.value as FarmUnit })}>
                  {(units.includes(row.unit) ? units : [...units, row.unit]).map(u => <option key={u} value={u}>{tr(`farm.unit.${u}`)}</option>)}
                </select></label>
              {rows.length > 1 && <button type="button" className="ds-icon-button farm-remove" aria-label={tr('farm.remove', { v0: index + 1 })} onClick={() => setRows(old => old.filter(r => r.id !== row.id))}><Trash2 size={17} /></button>}
              {errors[index] && <p className="farm-error" id={`farm-error-${row.id}`} role="alert">{errors[index]}</p>}
            </motion.div>
          })}
        </AnimatePresence>
      </div>
      <div className="farm-actions">
        <button type="button" className="v3-pill" disabled={rows.length >= 8} onClick={add} data-testid="farm-add"><Plus size={17} />{tr('farm.add')}</button>
        <button type="button" className="v3-pill v3-pill-lime" disabled={!valid} onClick={ask} data-testid="farm-ask"><MessageSquare size={17} />{tr('farm.ask')}</button>
        <span className="farm-status" role="status">{busy ? tr('farm.calculating') : ''}</span>
      </div>
    </section>

    {error && <p className="ds-notice ds-notice-danger" role="alert">{error}</p>}
    {!valid && result && <p className="ds-notice">{tr('farm.fixInput')}</p>}
    {result && !result.ok && valid && <div className="ds-notice ds-notice-warn" data-testid="farm-no-data"><strong>{tr('farm.noDataTitle')}</strong><p>{result.question ?? tr('farm.noDataText')}</p></div>}

    {ok && data && <section aria-label={tr('farm.results')} className={`farm-results ${busy || !valid ? 'is-busy' : ''}`} data-testid="farm-results">
      <div className="farm-cards">
        {[
          { id: 'methane', icon: Flame, title: tr('farm.card.methane'), value: data.methane_m3!, unit: tr('farm.unit.m3'), note: tr('farm.card.lab', { v0: num(data.methane_potential_m3!.high), v1: tr('farm.unit.m3') }) },
          { id: 'biogas', icon: Wind, title: tr('farm.card.biogas'), value: data.biogas_m3!, unit: tr('farm.unit.m3'), note: tr('farm.card.share', { v0: Math.round(data.methane_share!.low * 100), v1: Math.round(data.methane_share!.high * 100) }) },
          { id: 'energy', icon: Zap, title: tr('farm.card.energy'), value: data.energy_kwh!, unit: tr('farm.kwh'), note: tr('farm.card.energyNote') },
          { id: 'days', icon: Clock, title: tr('farm.card.days'), value: data.days!, unit: tr('farm.days'), note: tr('farm.card.regime', { v0: data.regime_name ?? '', v1: data.temperature_c ?? 37 }) },
        ].map((card, index) => <motion.article key={card.id} className={`farm-card v3-card v3-card-${FARM_TONE[index % 4]}`} data-testid={`farm-card-${card.id}`}
          initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .22, delay: index * .05 }}>
          <span className="farm-card-title"><card.icon size={18} />{card.title}</span>
          <strong className="farm-card-value">≈ {card.id === 'days' ? range(card.value) : num(mid(card.value))} <small>{card.unit}</small></strong>
          {card.id !== 'days' && <span className="farm-card-range">{tr('farm.range', { v0: range(card.value), v1: card.unit })}</span>}
          <span className="farm-card-note">{card.note}</span>
        </motion.article>)}
      </div>

      {parts.length > 1 && <motion.section className="farm-chart v3-card v3-card-dark" aria-label={tr('farm.chart')} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: .25, delay: .15 }}>
        <h2>{tr('farm.chart')}</h2>
        <p className="ds-muted">{tr('farm.chartNote')}</p>
        <ul className="farm-bars" data-testid="farm-chart">
          {parts.map(part => <li key={part.substrate + part.amount} title={`${part.name}: ${range(part.methane_m3)} ${tr('farm.unit.m3')}`}>
            <span className="farm-bar-label">{part.name} · {num(part.amount)} {tr(`farm.unit.${part.unit}`)}</span>
            <span className="farm-bar-track"><motion.span className="farm-bar-fill" initial={{ width: 0 }} animate={{ width: `${Math.max(part.share_of_methane * 100, 1.5)}%` }} transition={{ duration: .4 }} /></span>
            <span className="farm-bar-value">{Math.round(part.share_of_methane * 100)} % · ≈ {num(mid(part.methane_m3))} {tr('farm.unit.m3')}</span>
          </li>)}
        </ul>
      </motion.section>}

      <p className="farm-same ds-muted"><BookOpen size={15} />{tr('farm.same')}</p>
      <details className="ds-collapse">
        <summary>{tr('farm.assumptions', { v0: result!.assumptions.length, v1: result!.sources.length })}</summary>
        <ul>{result!.assumptions.map(item => <li key={item}>{item}</li>)}</ul>
        <h3>{tr('farm.sources')}</h3>
        <ul>{result!.sources.map((s, i) => <li key={s.id ?? i}>{s.url ? <a href={s.url} target="_blank" rel="noreferrer">{s.title ?? s.id}</a> : s.title ?? s.id}{s.year ? ` (${s.year})` : ''}</li>)}</ul>
      </details>
    </section>}
  </div>
}
