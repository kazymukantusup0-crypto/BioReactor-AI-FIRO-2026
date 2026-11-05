import { useEffect, useMemo, useState, useRef } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import { advisorApi, type AdvisorRequestInput, type AdvisorResult, type ComponentInput, type Material, type MixtureComparison, type SavedMixture, type Unit } from '../advisorApi'
import { api, CHAT_ADVISOR_KEY, CHAT_SESSION_KEY } from '../api'
import FunctionalResults from '../FunctionalResults'
import ScenarioControls from '../ScenarioControls'
import type { AdvisorDecision } from '../advisorApi'
import type { ConversationMemory } from '../types'
import { useQuery } from '../hooks'
import { Notice } from '../ui'
import '../advisor.css'
import MaterialPropertiesFields from '../MaterialPropertiesFields'

const STORAGE_KEY = 'bioreactor-inventory-v8.1'
const DRAFT_KEY = 'bioreactor-calculator-draft-v9'
const UNIT_FACTORS: Record<Unit, { family: 'mass' | 'volume'; factor: number }> = {
  kg: { family: 'mass', factor: 1 }, g: { family: 'mass', factor: .001 }, t: { family: 'mass', factor: 1000 },
  mL: { family: 'volume', factor: .001 }, L: { family: 'volume', factor: 1 }, m3: { family: 'volume', factor: 1000 },
}
const defaultRows = (): ComponentInput[] => [{ id: 'c1', material: 'cattle_manure', material_state: 'unknown', quantity: 50, unit: 'kg' }]
const labelForState = (material: Material, state: string) => material.form_states.find(option => option.value === state)?.label ?? state
const profileMatches = (profile: Material['profiles'][number], row: ComponentInput, animal: string) => {
  if (row.data_mode === 'MEASURED' || ['stored', 'rotted', 'composted'].includes(row.decay_state ?? 'unknown')) return false
  const states = profile.matching_states ?? [profile.material_state]
  return states.includes(row.material_state)
    && (!profile.animals || profile.animals.includes(row.animal ?? animal))
    && (!profile.poultry_types || profile.poultry_types.includes(row.poultry_type ?? 'unknown'))
    && (!profile.beddings || profile.beddings.includes(row.bedding ?? 'unknown'))
}
const factorLabels: Record<string, string> = {
  density_kg_l: 'плотность', ts_fraction: 'сухое вещество', vs_fraction_wet: 'органическое вещество',
  vs_fraction_on_explicit_TS_or_wet_basis: 'доля органики на заданной основе TS/влажной массы',
  bmp_ml_g_vs: 'BMP', gas_basis: 'условия измерения газа',
}

export default function SubstrateAdvisorV81({ mixture = true }: { mixture?: boolean }) {
  const catalog = useQuery('advisor-catalog', advisorApi.catalog)
  const [rows, setRows] = useState<ComponentInput[]>(() => {
    try {
      const value: unknown = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? localStorage.getItem('bioreactor-inventory-v7.7') ?? 'null')
      if (Array.isArray(value) && value.length > 0 && value.length <= 20
        && value.every(row => typeof row.id === 'string' && typeof row.material === 'string'
          && typeof row.material_state === 'string' && Number.isFinite(row.quantity) && row.quantity > 0
          && Object.hasOwn(UNIT_FACTORS, row.unit))) return value
    } catch (error) {
      console.error('Could not restore the substrate mixture from local storage.', error)
    }
    return defaultRows()
  })
  const [saved, setSaved] = useState<SavedMixture[]>([])
  const [selectedSaved, setSelectedSaved] = useState('')
  const [mixtureName, setMixtureName] = useState('')
  const [result, setResult] = useState<AdvisorResult | null>(null)
  const [comparison, setComparison] = useState<MixtureComparison | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [dirty, setDirty] = useState(false)
  const [total, setTotal] = useState('')
  const [working, setWorking] = useState('')
  const [inoculum, setInoculum] = useState('')
  const [operation, setOperation] = useState('')
  const [commonBasis, setCommonBasis] = useState(true)
  const [decision, setDecision] = useState<AdvisorDecision>({})
  const [region, setRegion] = useState('KZ-Karaganda')
  const [regionConfirmed, setRegionConfirmed] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const sequence = useRef(0)
  const [transfer, setTransfer] = useState(true)
  const [objectives, setObjectives] = useState<string[]>(['methane'])
  const [displayMode, setDisplayMode] = useState<'simple' | 'scientific'>('simple')
  const [draftReady,setDraftReady]=useState(false)
  const [draftScope,setDraftScope]=useState<{conversation?:string;base?:number;task?:string}>({})

  useEffect(() => {
    try {
      if(!sessionStorage.getItem(CHAT_ADVISOR_KEY)) {
        const saved=JSON.parse(localStorage.getItem(DRAFT_KEY) ?? 'null') as {request:AdvisorRequestInput;scope:typeof draftScope}|null
        const request=saved?.request
        if(request && Array.isArray(request.components) && request.components.length>0 && request.components.length<=20
          && request.components.every(c=>c.quantity>0 && Number.isFinite(c.quantity) && Object.hasOwn(UNIT_FACTORS,c.unit))) {
          setRows(request.components);setTotal(request.reactor_total_volume_l==null?'':String(request.reactor_total_volume_l))
          setDecision(request.decision ?? {});setRegion(String(request.region ?? 'KZ-Karaganda'));setRegionConfirmed(request.region_confirmed===true)
          setTransfer(request.allow_literature_transfer ?? true);setCommonBasis(request.assume_common_dry_gas_basis ?? true)
          setObjectives(request.objectives ?? ['methane']);setDraftScope(saved?.scope ?? {})
          const reactor=request.decision?.reactor
          setWorking(reactor?.reactor_working_volume_l==null?'':String(reactor.reactor_working_volume_l))
          setInoculum(reactor?.inoculum_volume_l==null?'':String(reactor.inoculum_volume_l));setOperation(reactor?.operating_mode ?? '')
        }
      }
    } catch(cause) {setError(`Не удалось восстановить черновик: ${String(cause)}`)}
    setDraftReady(true)
  },[])

  useEffect(() => {
    const raw = sessionStorage.getItem(CHAT_ADVISOR_KEY)
    if (!raw) return
    sessionStorage.removeItem(CHAT_ADVISOR_KEY)
    try {
      const memory = JSON.parse(raw) as ConversationMemory & {state_version?:number;task_id?:string}
      setDraftScope({conversation:memory.conversation_id ?? undefined,base:memory.state_version,task:memory.task_id})
      const active = memory.active_mixture_scenario ? memory.mixture_scenario_components : memory.mixture_components
      const valid = (items: unknown): items is ComponentInput[] => Array.isArray(items) && items.length > 0 && items.length <= 20
        && items.every(item => item && typeof item === 'object' && typeof (item as ComponentInput).material === 'string'
          && typeof (item as ComponentInput).material_state === 'string' && Number.isFinite((item as ComponentInput).quantity)
          && (item as ComponentInput).quantity > 0 && Object.hasOwn(UNIT_FACTORS, (item as ComponentInput).unit))
      const quantity = memory.facts.quantity?.value ?? memory.derived.mass_kg?.value ?? memory.facts.mass_kg?.value
      const unit = memory.facts.unit?.value ?? (memory.facts.quantity ? undefined : 'kg')
      const material = memory.facts.material?.value
      const imported: ComponentInput[] = valid(active) ? active : typeof material === 'string' && typeof quantity === 'number'
        && typeof unit === 'string' && Object.hasOwn(UNIT_FACTORS, unit)
        ? [{ id: 'chat-batch', material, material_state: String(memory.facts.material_state?.value ?? 'unknown'), quantity, unit: unit as Unit,
            properties: Object.fromEntries(Object.entries({density_kg_l: memory.facts.density_kg_l?.value,
              ts_fraction: typeof memory.facts.ts_percent?.value === 'number' ? Number(memory.facts.ts_percent.value) / 100 : undefined,
              vs_fraction_of_ts: memory.facts.vs_basis?.value === 'TS' && typeof memory.facts.vs_percent?.value === 'number' ? Number(memory.facts.vs_percent.value) / 100 : undefined,
              vs_fraction_wet: memory.facts.vs_basis?.value === 'fresh_mass' && typeof memory.facts.vs_percent?.value === 'number' ? Number(memory.facts.vs_percent.value) / 100 : undefined,
              bmp_ml_g_vs: memory.facts.bmp_ml_ch4_g_vs?.value}).filter(([, value]) => typeof value === 'number')) }]
        : []
      if (!imported.length) throw new Error('Диалог не содержит полного набора сырья и количества для передачи.')
      setRows(imported)
      const overrides = memory.advanced?.request_overrides ?? {}
      const reactor = (memory.decision_settings?.reactor ?? {}) as Record<string, unknown>
      setTransfer(typeof overrides.allow_literature_transfer === 'boolean' ? overrides.allow_literature_transfer : true)
      setCommonBasis(typeof overrides.assume_common_dry_gas_basis === 'boolean' ? overrides.assume_common_dry_gas_basis : true)
      const volume = memory.facts.reactor_total_volume_l?.value ?? memory.advanced?.reactor?.total_volume_l
      setTotal(typeof volume === 'number' ? String(volume) : '')
      setWorking(typeof reactor.reactor_working_volume_l === 'number' ? String(reactor.reactor_working_volume_l) : '')
      setInoculum(typeof reactor.inoculum_volume_l === 'number' ? String(reactor.inoculum_volume_l) : '')
      setOperation(typeof reactor.operating_mode === 'string' ? reactor.operating_mode : '')
      setRegion(String(memory.facts.market_region?.value ?? memory.assumptions.market_region?.value ?? overrides.region ?? 'KZ-Karaganda'))
      setRegionConfirmed(memory.facts.market_region?.provenance === 'USER_CONFIRMED' || overrides.region_confirmed === true)
      if (memory.decision_settings && typeof memory.decision_settings === 'object') {
        const hypothetical = Object.fromEntries(['dilution_water_l', 'temperature_c'].flatMap(key => {
          const entry = memory.assumptions[key]
          return entry?.provenance === 'ASSUMED_FOR_SCENARIO' && typeof entry.value === 'number' ? [[key, entry.value]] : []
        }))
        setDecision({ ...memory.decision_settings, reactor: { ...reactor, ...hypothetical,
          ...(Object.keys(hypothetical).length ? { provenance: 'HYPOTHETICAL_SCENARIO' } : {}) } } as AdvisorDecision)
      }
      setDisplayMode('scientific');setResult(null);setComparison(null);setDirty(true)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause))
    }
  }, [])

  useEffect(() => {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(rows)) }
    catch (cause) { setError(`Не удалось сохранить текущую смесь в браузере: ${String(cause)}`) }
  }, [rows])
  useEffect(() => {
    const controller = new AbortController()
    advisorApi.mixtures(controller.signal).then(data => setSaved(data.mixtures))
      .catch(cause => { if (!controller.signal.aborted) setError(`Не удалось загрузить список сохранённых смесей: ${String(cause)}`) })
    return () => controller.abort()
  }, [])

  const names = useMemo(() => Object.fromEntries((catalog.data?.materials ?? []).map(material => [material.id, material.name.ru])), [catalog.data])
  const payload = (): AdvisorRequestInput => ({
    components: rows,
    region, region_confirmed: regionConfirmed,
    online: false,
    allow_literature_transfer: transfer,
    allow_conditional_profiles: true,
    assume_common_dry_gas_basis: commonBasis,
    ...(total ? { reactor_total_volume_l: Number(total) } : {}),
    objectives,
    decision: { ...decision, reactor: {
      ...decision.reactor,
      ...(working ? { reactor_working_volume_l: Number(working) } : {}),
      ...(inoculum ? { inoculum_volume_l: Number(inoculum) } : {}),
      ...(operation ? { operating_mode: operation } : {}),
    } },
  })
  const bodyKey = JSON.stringify(payload())
  useEffect(() => {
    if(!draftReady)return
    const request=JSON.parse(bodyKey) as AdvisorRequestInput
    try {localStorage.setItem(DRAFT_KEY,JSON.stringify({request,scope:draftScope}))}
    catch(cause){setError(`Не удалось сохранить черновик: ${String(cause)}`)}
    if(!draftScope.conversation || draftScope.base==null)return
    const controller=new AbortController()
    const timer=setTimeout(async()=>{
      try {
        const current=await api.scientificState(draftScope.conversation!,controller.signal)
        await api.saveDraft(draftScope.conversation!,draftScope.base!,current.dashboard_draft?.revision ?? 0,{request,task_id:draftScope.task},controller.signal)
      } catch(cause){if(!controller.signal.aborted)setError(`Черновик сохранён в браузере; синхронизация с диалогом не выполнена: ${String(cause)}`)}
    },700)
    return ()=>{clearTimeout(timer);controller.abort()}
  },[bodyKey,draftReady,draftScope])
  const ready = Boolean(catalog.data)
  useEffect(() => {
    const epoch = ++sequence.current
    const controller = new AbortController()
    const body = JSON.parse(bodyKey) as AdvisorRequestInput
    setDirty(true)
    setComparison(null)
    if (!ready || body.components.some(c => !Number.isFinite(c.quantity) || c.quantity <= 0)) return
    const timer = window.setTimeout(() => {
      if (epoch !== sequence.current) return
      setRefreshing(true)
      advisorApi.analyze(body, controller.signal).then(value => {
        if (epoch !== sequence.current || controller.signal.aborted) return
        setResult(value); setDirty(false); setError('')
      }).catch(cause => {
        if (!controller.signal.aborted && epoch === sequence.current) setError(String(cause))
      }).finally(() => { if (epoch === sequence.current) setRefreshing(false) })
    }, 700)
    return () => { window.clearTimeout(timer); controller.abort() }
  }, [bodyKey, ready])
  const change = (id: string, patch: Partial<ComponentInput>) => {
    setRows(old => old.map(row => row.id === id ? { ...row, ...patch } : row))
    setDirty(true)
  }
  const add = () => {
    setRows(old => [...old, { id: crypto.randomUUID(), material: 'food_waste', material_state: 'unknown', quantity: 20, unit: 'kg' }])
    setDirty(true)
  }
  const remove = (id: string) => {
    setRows(old => old.filter(row => row.id !== id))
    setDirty(true)
  }

  async function changeUnit(id: string, target: Unit) {
    const row = rows.find(item => item.id === id)
    if (!row || row.unit === target) return
    setBusy(true)
    setError('')
    try {
      const source = UNIT_FACTORS[row.unit]
      const destination = UNIT_FACTORS[target]
      if (source.family === destination.family) {
        change(id, { quantity: row.quantity * source.factor / destination.factor, unit: target })
        return
      }
      const response = await advisorApi.convert({ request: { components: [row], allow_literature_transfer: transfer }, target_unit: target })
      const converted = response.conversions.find(item => item.id === id)
      if (!converted || converted.status !== 'ok' || !converted.value) {
        throw new Error(converted?.message ?? 'Для выбранного сырья и состояния нет подходящей плотности.')
      }
      if (Math.abs(converted.value.high - converted.value.low) > 1e-9) {
        throw new Error(`Плотность даёт диапазон ${converted.value.low}–${converted.value.high} ${target}; точное количество не подменено средней точкой. Укажите измеренную плотность, чтобы сохранить эквивалентность.`)
      }
      change(id, { quantity: converted.value.low, unit: target })
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause))
    } finally { setBusy(false) }
  }

  function makeCandidates() {
    const candidates: { label: string; components: ComponentInput[] }[] = [{ label: 'Текущий состав', components: rows }]
    for (const row of rows) {
      const name = names[row.material] ?? row.material
      candidates.push({ label: `Половина: ${name}`, components: rows.map(item => item.id === row.id ? { ...item, quantity: item.quantity / 2 } : item) })
      if (rows.length > 1) candidates.push({ label: `Без компонента: ${name}`, components: rows.filter(item => item.id !== row.id) })
    }
    return candidates.slice(0, 8)
  }

  async function calculate(compare = false) {
    const epoch = ++sequence.current
    setBusy(true)
    setError('')
    try {
      const body = payload()
      const value = await advisorApi.analyze(body)
      if (epoch !== sequence.current) return
      setResult(value)
      setDirty(false)
      setComparison(null)
      if (compare) setComparison(await advisorApi.compare({ base: body, candidates: makeCandidates() }))
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause))
    } finally { setBusy(false) }
  }

  async function refreshSaved() {
    const value = await advisorApi.mixtures()
    setSaved(value.mixtures)
  }
  async function saveMixture() {
    setBusy(true)
    setError('')
    try {
      const body = payload()
      const value = await advisorApi.saveMixture({
        name: mixtureName.trim(),
        request: body,
        display_units: Object.fromEntries(rows.map(row => [row.id, row.unit])),
        ...(selectedSaved ? { mixture_id: selectedSaved } : {}),
      })
      setSelectedSaved(value.mixture_id)
      setMixtureName(value.name)
      await refreshSaved()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause))
    } finally { setBusy(false) }
  }
  async function loadMixture() {
    if (!selectedSaved) return
    setBusy(true)
    setError('')
    try {
      const value = await advisorApi.loadMixture(selectedSaved)
      const request = value.request
      setRows(request.components)
      setTransfer(request.allow_literature_transfer ?? true)
      setCommonBasis(request.assume_common_dry_gas_basis ?? false)
      setTotal(request.reactor_total_volume_l == null ? '' : String(request.reactor_total_volume_l))
      setObjectives(request.objectives ?? ['methane', 'stability'])
      setDecision(request.decision ?? {})
      setRegion(String(request.region ?? 'KZ-Karaganda'))
      setRegionConfirmed(request.region_confirmed === true)
      const reactor = request.decision?.reactor
      setWorking(reactor?.reactor_working_volume_l == null ? '' : String(reactor.reactor_working_volume_l))
      setInoculum(reactor?.inoculum_volume_l == null ? '' : String(reactor.inoculum_volume_l))
      setOperation(reactor?.operating_mode ?? '')
      setResult(null)
      setComparison(null)
      setDirty(true)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause))
    } finally { setBusy(false) }
  }
  async function sendToChat() {
    setBusy(true)
    setError('')
    try {
      const value = await advisorApi.handoff({ request: payload(), mode: 'offline' })
      localStorage.setItem(CHAT_SESSION_KEY, value.session_id)
      sessionStorage.setItem('bioreactor_demo_question', value.suggested_question)
      window.location.hash = '/chat'
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause))
    } finally { setBusy(false) }
  }

  return <div className="advisor-page">
    <div className="page-heading"><div><h1>Сырьё и смеси</h1><p>Укажите состав — получите источниковый ориентир газа, условия и оценку экономики.</p></div><div className="display-mode" role="group" aria-label="Режим калькулятора"><button type="button" aria-pressed={displayMode === 'simple'} onClick={() => setDisplayMode('simple')}>Простой</button><button type="button" aria-pressed={displayMode === 'scientific'} onClick={() => setDisplayMode('scientific')}>Научный</button></div></div>
    {catalog.error && <Notice tone="red">{catalog.error}</Notice>}
    {catalog.data && <details className="catalog-detail"><summary>О научном охвате реестра</summary><div className="advisor-catalog-strip">
      <span><strong>{catalog.data.recognized_categories}</strong> распознаваемых категорий</span>
      <span><strong>{catalog.data.materials_with_approved_profiles.length}</strong> категорий с профилями для ограниченных состояний</span>
      <span><strong>{catalog.data.approved_profile_count}</strong> источниковых профилей</span>
      <span><strong>{catalog.data.complete_density_solids_bmp_profile_count}</strong> полных профиля, включая плотность</span>
    </div><p>Распознавание материала не означает наличие расчётного профиля. Выход — лабораторный ориентир, а не гарантированная выработка.</p></details>}
    <form onSubmit={event => { event.preventDefault(); void calculate() }}>
      <fieldset disabled={busy}>
        <legend>Сырьё и количество</legend>
        {rows.map((row, index) => {
          const material = catalog.data?.materials.find(item => item.id === row.material)
          const animal = catalog.data?.ui.animals.find(option => option.material === row.material)?.value ?? 'unknown'
          const matchingProfiles = material?.profiles.filter(profile => profileMatches(profile, row, animal)) ?? []
          const states = material?.form_states ?? []
          return <section className="advisor-component" key={row.id}>
            <div className="advisor-component-label">Компонент {index + 1}{mixture && rows.length > 1 && <button type="button" className="icon-button" aria-label={`Удалить компонент ${index + 1}`} onClick={() => remove(row.id)}><Trash2 size={16} /></button>}</div>
            <div className="advisor-input-grid">
              <label>Сырьё {index + 1}<select aria-label={`Сырьё ${index + 1}`} data-testid={`material-${index}`} value={row.material} onChange={event => change(row.id, { material: event.target.value, material_state: 'unknown', animal: undefined, poultry_type: 'unknown', physical_state: 'unknown', decay_state: 'unknown', bedding: 'unknown', reference_profile_id: null, properties: {} })}>
                {catalog.data?.materials.filter(item => displayMode === 'scientific' || item.id === row.material || item.scope_status !== 'EXPERIMENTAL_RETAINED').map(item => <option key={item.id} value={item.id}>{item.name.ru}</option>)}
              </select></label>
              <label>Состояние {index + 1}<select aria-label={`Состояние ${index + 1}`} data-testid={`state-${index}`} value={row.material_state} onChange={event => {
                const state = states.find(item => item.value === event.target.value)
                change(row.id, { material_state: event.target.value, physical_state: state?.physical_state ?? 'unknown', reference_profile_id: null })
              }}>
                {states.map(state => <option key={state.value} value={state.value}>{state.label}</option>)}
              </select></label>
              <label>Количество {index + 1}<input type="number" min="0.000001" max="1000000000" step="any" required data-testid={`quantity-${index}`} value={row.quantity} onChange={event => change(row.id, { quantity: event.target.value === '' ? 0 : Number(event.target.value) })} /></label>
              <label>Единицы {index + 1}<select aria-label={`Единицы ${index + 1}`} value={row.unit} onChange={event => { void changeUnit(row.id, event.target.value as Unit) }}>
                {catalog.data?.ui.units.map(unit => <option key={unit.value} value={unit.value}>{unit.label}</option>)}
              </select></label>
            </div>
            {material && <details className="advisor-scientific-component" open={displayMode === 'scientific'}><summary>Научные свойства и выбор профиля</summary><div className="advisor-profile-notice" role="status">
              <p>{material.support_notice}</p>
              {matchingProfiles.length > 0 ? <>
                <label>Научный профиль {index + 1}<select aria-label={`Научный профиль ${index + 1}`} data-testid={`profile-${index}`} value={row.reference_profile_id ?? ''} onChange={event => change(row.id, { reference_profile_id: event.target.value || null })}>
                  <option value="">Автоматически: первый совместимый профиль</option>
                  {matchingProfiles.map(profile => <option key={profile.id} value={profile.id}>{profile.id} · {String(profile.source_id ?? '')}</option>)}
                </select></label>
                {(row.reference_profile_id ? matchingProfiles.filter(profile => profile.id === row.reference_profile_id) : matchingProfiles.slice(0, 1)).map(profile => <p key={profile.id}><strong>{profile.id}</strong>: {String(profile.approved_scope ?? profile.preparation ?? '')}{profile.state_transfer_note ? ` ${profile.state_transfer_note}` : ''}</p>)}
              </> : <p>Для состояния «{labelForState(material, row.material_state)}» и выбранного типа нет точного профиля. Доступны состояния с литературными данными: {material.available_reference_states.length ? material.available_reference_states.map(state => labelForState(material, state)).join(', ') : 'пока отсутствуют'}. При разрешённом переносе проверяются отдельные условные сценарии того же материала. Несовместимые состояния не подменяются.</p>}
            </div>
            {catalog.data && <MaterialPropertiesFields row={row} index={index + 1} onChange={patch => change(row.id, patch)} catalog={catalog.data} />}
            <details className="advisor-measurements"><summary>Измеренные свойства компонента · необязательно</summary><div className="advisor-input-grid">
              {[{ key: 'density_kg_l', label: 'Плотность, кг/л', max: 10 }, { key: 'ts_fraction', label: 'Доля сухого вещества, 0–1', max: 1 }, { key: 'vs_fraction_wet', label: 'Доля органического вещества во влажной массе, 0–1', max: 1 }].map(field => <label key={field.key}>{field.label} {index + 1}<input type="number" min="0" max={field.max} step="any" placeholder="Не измерено" value={typeof row.properties?.[field.key] === 'number' ? row.properties[field.key] as number : ''} onChange={event => change(row.id, { properties: { ...row.properties, [field.key]: event.target.value === '' ? undefined : Number(event.target.value) } })} /></label>)}
            </div></details></details>}
          </section>
        })}
        {mixture && displayMode === 'scientific' && <button type="button" className="secondary-button" disabled={rows.length >= 20} onClick={add}><Plus size={16} />Добавить материал</button>}
        <label>Номинальный объём реактора, л<input aria-label="Номинальный объём реактора" type="number" min="0.001" step="any" data-testid="reactor-total" value={total} onChange={event => { setTotal(event.target.value); setDirty(true) }} placeholder="Не указан" /></label>
        <label>Регион расчёта<input data-testid="market-region" value={region} onChange={e => { setRegion(e.target.value); setRegionConfirmed(false); setDirty(true) }} /></label>
        {displayMode === 'simple' && <p className="muted">Простой режим использует совместимые литературные профили как отдельно обозначенные условные сценарии. Номинальный объём не подтверждает безопасную загрузку.</p>}
        <details className="advisor-reactor" open={displayMode === 'scientific'}><summary>Научные настройки реактора, профилей и сценариев</summary><div className="advisor-input-grid">
          <label>Подтверждённый рабочий объём, л<input type="number" min="0.001" step="any" value={working} onChange={event => { setWorking(event.target.value); setDirty(true) }} placeholder="Не подтверждён" /></label>
          <label>Инокулюм, л<input type="number" min="0" step="any" value={inoculum} onChange={event => { setInoculum(event.target.value); setDirty(true) }} placeholder="Не измерен" /></label>
          <label>Режим загрузки<select aria-label="Режим загрузки" value={operation} onChange={event => { setOperation(event.target.value); setDirty(true) }}><option value="">Не указан</option><option value="batch">Периодическая партия</option><option value="continuous">Непрерывный</option></select></label>
        </div>
          <label className="advisor-checkbox"><input type="checkbox" checked={transfer} onChange={event => { setTransfer(event.target.checked); setDirty(true) }} />Разрешить явно обозначенный перенос литературных характеристик</label>
          <label className="advisor-checkbox"><input type="checkbox" checked={commonBasis} onChange={event => { setCommonBasis(event.target.checked); setDirty(true) }} />Показать условный ориентир смеси, предполагая сопоставимые условия объёма газа</label>
          <p>Это сценарное допущение, а не измеренное свойство. Заведомо влажный газ автоматически не переводится в сухой.</p>
        </details>
        <label className="advisor-checkbox"><input type="checkbox" data-testid="region-confirmed" checked={regionConfirmed} onChange={e => { setRegionConfirmed(e.target.checked); setDirty(true) }} />Регион установки подтверждён</label>
        <ScenarioControls region={region} value={decision} onChange={value => { setDecision(value); setDirty(true) }} />
        {mixture && <div className="advisor-objectives" role="group" aria-label="Цели сравнения">{Object.entries({ methane: 'Метан', energy: 'Энергозатраты', duration: 'Продолжительность', profit: 'Экономика', stability: 'Стабильность' }).map(([id, label]) => <label key={id}><input type="checkbox" disabled={['duration', 'stability'].includes(id)} checked={objectives.includes(id)} onChange={event => { setObjectives(old => event.target.checked ? [...old, id] : old.filter(value => value !== id)); setDirty(true) }} />{label}</label>)}</div>}
        <div className="advisor-actions"><button type="submit" className="primary-button" disabled={!catalog.data}>{busy ? 'Считаю…' : 'Получить оценку'}</button>{mixture && <button type="button" className="secondary-button" disabled={!catalog.data || rows.length === 0} onClick={() => { void calculate(true) }}>Сравнить варианты</button>}</div>
      </fieldset>
    </form>
    <section className="advisor-saved-mixtures" aria-label="Сохранение и передача смеси">
      <label>Название смеси<input aria-label="Название смеси для сохранения" value={mixtureName} onChange={event => setMixtureName(event.target.value)} placeholder="Например, свиной навоз + пищевые отходы" /></label>
      <button type="button" className="secondary-button" disabled={busy || !mixtureName.trim()} onClick={() => { void saveMixture() }}>Сохранить смесь</button>
      <label>Сохранённые смеси<select aria-label="Сохранённые смеси" value={selectedSaved} onChange={event => setSelectedSaved(event.target.value)}><option value="">Выберите смесь</option>{saved.map(item => <option key={item.mixture_id} value={item.mixture_id}>{item.name} · версия {item.revision}</option>)}</select></label>
      <button type="button" className="secondary-button" disabled={busy || !selectedSaved} onClick={() => { void loadMixture() }}>Загрузить смесь</button>
      <button type="button" className="secondary-button" disabled={busy || rows.length === 0} data-testid="send-to-chat" onClick={() => { void sendToChat() }}>Передать смесь в чат</button>
    </section>
    {refreshing && <p role="status">Пересчитываю параметры…</p>}
    {error && <Notice tone="red">{error}</Notice>}
    {result && <>{dirty && <Notice tone="amber">Параметры изменились. Ниже предыдущий расчёт; автоматический пересчёт выполняется после ввода.</Notice>}<FunctionalResults key={String(result.calculated_at)} result={result} comparison={comparison} names={names} /></>}
  </div>
}
