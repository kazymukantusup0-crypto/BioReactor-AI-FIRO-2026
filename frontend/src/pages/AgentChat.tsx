// AI Chat on agent v10: the agent's steps are shown live ("thinking feed").
// Farmer view: answer, number cards, one question. Jury view: every step with
// tool arguments, raw results, LLM token counts and timings.
import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { ArrowUp, Bot, BookOpen, Check, CircleStop, Cpu, Gavel, LoaderCircle, MessageSquarePlus, Pencil, ShieldAlert, ShieldCheck, User } from 'lucide-react'
import {
  agentApi, componentText, INSULATION_LABELS, MODE_LABELS, newConversationId, pluralRu, speedWarning, streamAgentChat, TOOL_LABELS,
  type AgentAnswer, type AgentEvent, type AgentStatus, type DemoReactor, type Facts, type NumberCard, type Verdict,
} from '../agentV10'
import { DEMO_SCENARIOS, type DemoScenario } from '../demoScenarios'
import '../agentChat.css'
import { localized, materialName, tr } from '../i18n'

const STORAGE_ID = 'bioreactor-agent-v10-conversation'
const STORAGE_JURY = 'bioreactor-agent-v10-jury'
const EXAMPLES = localized(() => ([
  tr('agentChat.1'),
  tr('agentChat.2'),
  tr('agentChat.3'),
  tr('agentChat.4'),
  tr('agentChat.5'),
]))

export interface Turn { id: string; user: string; events: AgentEvent[]; live: string; answer?: AgentAnswer; error?: string; running: boolean; restored?: boolean }

function read(key: string): string | null { try { return localStorage.getItem(key) } catch { return null } }
function write(key: string, value: string) { try { localStorage.setItem(key, value) } catch { /* optional */ } }
const seconds = (ms?: number | null) => ms == null ? '—' : tr('agentChat.6', { v0: (ms / 1000).toFixed(1) })

/** Apply one SSE event to a turn (pure: easy to test). */
export function applyEvent(turn: Turn, event: AgentEvent): Turn {
  const events = event.type === 'token' ? turn.events : [...turn.events, event]
  switch (event.type) {
    case 'token': return { ...turn, live: turn.live + String(event.text ?? '') }
    case 'token_reset': return { ...turn, events, live: '' }
    case 'answer': return { ...turn, events, answer: event as unknown as AgentAnswer, live: '' }
    case 'error': return { ...turn, events, error: String(event.message ?? tr('agentChat.7')), running: false }
    case 'done': return { ...turn, events, running: false }
    default: return { ...turn, events }
  }
}

// ---------- thinking feed ----------
interface FeedLine { icon: string; title: string; detail?: unknown; tone?: 'ok' | 'warn' | 'bad' }
function json(value: unknown) { return JSON.stringify(value, null, 1).replace(/\n\s*/g, ' ') }

export function feedLine(event: AgentEvent): FeedLine | null {
  switch (event.type) {
    case 'understood': return { icon: '🧠', title: tr('agentChat.8', { v0: ({ ru: tr('agentChat.97'), kk: tr('agentChat.98'), en: tr('agentChat.99') } as Record<string, string>)[String(event.language)] ?? event.language }) }
    case 'facts': {
      const updates = (event.updates ?? {}) as Record<string, unknown>
      const keys = Object.keys(updates)
      return { icon: '📋', title: keys.length ? tr('agentChat.9', { v0: keys.join(', ') }) : tr('agentChat.10'), detail: updates }
    }
    case 'llm_step': {
      const decision = event.decision === 'tool_calls' ? tr('agentChat.11') : tr('agentChat.12')
      return { icon: '🤖', title: tr('agentChat.13', { v0: event.step, v1: decision }), detail: { [tr('agentChat.102')]: event.prompt_tokens, [tr('agentChat.103')]: event.output_tokens, [tr('agentChat.104')]: seconds(event.duration_ms as number), [tr('agentChat.105')]: event.tokens_per_s } }
    }
    case 'tool_call': return { icon: '🔧', title: tr('agentChat.14', { v0: TOOL_LABELS[String(event.name)] ?? event.name, v1: event.by === 'llm' ? tr('agentChat.100') : 'Python' }), detail: { tool: event.name, args: event.args } }
    case 'tool_result': return { icon: '📊', title: tr('agentChat.15', { v0: TOOL_LABELS[String(event.name)] ?? event.name, v1: event.ok ? '' : tr('agentChat.101'), v2: event.duration_ms }), detail: event.summary, tone: event.ok ? 'ok' : 'bad' }
    case 'verification': {
      const unknown = (event.unknown_numbers ?? []) as number[]
      const against = (event.contradicts ?? []) as string[]
      const next = event.attempt === 1 ? tr('agentChat.16') : tr('agentChat.17')
      if (event.ok) return { icon: '✅', title: tr('agentChat.18'), tone: 'ok' }
      if (against.length) return { icon: '⚠️', title: tr('agentChat.19', { v0: next }), detail: { [tr('agentChat.106')]: against, [tr('agentChat.107')]: unknown }, tone: 'warn' }
      return { icon: '⚠️', title: tr('agentChat.20', { v0: unknown.join(', '), v1: next }), tone: 'warn' }
    }
    // Notes come from Python in Russian; the text in the interface language is taken by the note code.
    case 'note': return { icon: 'ℹ️', title: tr(`note.${String(event.code)}`) === `note.${String(event.code)}` ? String(event.message ?? event.code) : tr(`note.${String(event.code)}`), tone: 'warn' }
    case 'token_reset': return event.reason === 'template' ? { icon: '📝', title: tr('agentChat.21'), tone: 'warn' } : null
    case 'answer': return { icon: '💬', title: tr('agentChat.22', { v0: MODE_LABELS[String(event.mode)] ?? event.mode }) }
    case 'done': return { icon: '⏱️', title: tr('agentChat.23', { v0: seconds(event.total_ms as number) }) }
    case 'error': return { icon: '❌', title: String(event.message), tone: 'bad' }
    default: return null
  }
}

function ThinkingFeed({ turn, jury }: { turn: Turn; jury: boolean }) {
  const lines = turn.events.map(event => ({ event, line: feedLine(event) })).filter(item => item.line)
  if (!lines.length && !turn.running) return null
  const list = <ol className="ac-feed-list">
    {lines.map(({ event, line }, index) => <li key={index} className={`ac-feed-item ${line!.tone ?? ''}`}>
      <span className="ac-feed-icon" aria-hidden>{line!.icon}</span>
      <div><span>{line!.title}</span>{jury && <span className="ac-feed-time">{seconds(event.t_ms)}</span>}
        {jury && line!.detail != null && Object.keys(line!.detail as object).length > 0 && <code className="ac-feed-detail">{json(line!.detail)}</code>}
      </div>
    </li>)}
    {turn.running && <li className="ac-feed-item"><LoaderCircle size={14} className="spin" /><div><span>{tr('agentChat.24')}</span></div></li>}
  </ol>
  if (jury || turn.running) return <div className="ac-feed" aria-label={tr('agentChat.25')}>{list}</div>
  const calls = lines.filter(l => l.event.type === 'tool_call').length
  return <details className="ac-feed ac-feed-collapsed"><summary>{tr('agentChat.26')} {calls} {pluralRu(calls, [tr('agentChat.27'), tr('agentChat.28'), tr('agentChat.29')])}</summary>{list}</details>
}

// ---------- answer ----------
function badgeTone(label: string) { return label === 'measured' ? 'green' : label === 'literature' ? 'cyan' : 'amber' }

/** Big central estimate (≈), small "from–to" range under it. */
export function CardValue({ card }: { card: NumberCard }) {
  if (!card.center) return <strong className="ac-card-value">{card.value}<small> {card.unit}</small></strong>
  return <>
    <strong className="ac-card-value" aria-label={tr('agentChat.30', { v0: card.center, v1: card.unit, v2: card.range })}>≈{card.center}<small> {card.unit}</small></strong>
    <span className="ac-card-range">{card.range} {card.unit}</span>
  </>
}

function Verdicts({ items }: { items: Verdict[] }) {
  const advice = items.find(item => item.key === 'advice')
  const rest = items.filter(item => item.key !== 'advice')
  return <div className="ac-verdicts" aria-label={tr('agentChat.31')}>
    {rest.map(item => <div key={item.key} className={`ac-verdict ${item.tone}`}>
      <span className="ac-verdict-title">{item.title}</span><strong>{item.value}</strong>
    </div>)}
    {advice && <div className={`ac-advice ${advice.tone}`}>
      <span className="ac-verdict-title">{advice.title}</span>
      <strong className="ac-advice-value">{advice.value}</strong>
      <p>{advice.text}</p>
    </div>}
  </div>
}

export function AnswerView({ answer, jury }: { answer: AgentAnswer; jury: boolean }) {
  return <div className="ac-answer">
    {answer.verdicts && answer.verdicts.length > 0 && <Verdicts items={answer.verdicts} />}
    {answer.numbers.length > 0 && <div className="ac-cards">
      {answer.numbers.map(card => <div key={card.title} className={`ac-card ${card.details?.length ? 'ac-card-wide' : ''}`}>
        <span className="ac-card-title">{card.title}</span>
        <CardValue card={card} />
        <span className={`badge badge-${badgeTone(card.label)}`}><span className="badge-dot" />{card.badge}</span>
        {card.details && card.details.length > 0 && <ul className="ac-card-details">
          {card.details.map(line => <li key={line}>{line}</li>)}
        </ul>}
      </div>)}
    </div>}
    {answer.explanation && <p className="ac-explanation">{answer.explanation}</p>}
    {answer.question && <p className="ac-question">❓ {answer.question}</p>}
    <div className="ac-answer-meta">
      {answer.verified
        ? <span className="badge badge-green"><ShieldCheck size={11} />{tr('agentChat.32')}</span>
        : <span className="badge badge-amber"><ShieldAlert size={11} />{tr('agentChat.33')}</span>}
      <span className="badge">{MODE_LABELS[answer.mode] ?? answer.mode}</span>
      {jury && answer.model && <span className="badge">{answer.model}</span>}
      {jury && answer.timings && <span className="badge">{tr('agentChat.34')} {seconds(answer.timings.total_ms)} {tr('agentChat.35')} {seconds(answer.timings.first_answer_token_ms)} {tr('agentChat.36')} {answer.timings.prompt_tokens_max ?? '—'} {tr('agentChat.37')}</span>}
    </div>
    {answer.assumptions.length > 0 && <details className="ac-details" open={jury}>
      <summary>{tr('agentChat.38')}{answer.assumptions.length}{tr('agentChat.39')}</summary>
      <ul>{answer.assumptions.map(item => <li key={item}>{item}</li>)}</ul>
    </details>}
    {answer.sources.length > 0 && <details className="ac-details" open={jury}>
      <summary><BookOpen size={12} /> {tr('agentChat.40')}{answer.sources.length})</summary>
      <ul>{answer.sources.map((source, index) => <li key={source.id ?? index}>
        {source.url ? <a href={source.url} target="_blank" rel="noreferrer">{source.title ?? source.id}</a> : source.title ?? source.id}{source.year ? ` (${source.year})` : ''}
      </li>)}</ul>
    </details>}
    {jury && <details className="ac-details"><summary>{tr('agentChat.41')}</summary><pre>{JSON.stringify(answer.data, null, 2)}</pre></details>}
  </div>
}

// ---------- "What the agent knows" ----------
type Editable = 'reactor_volume_l' | 'ambient_c' | 'target_c' | 'days'
const FIELDS: { key: Editable; label: string; unit: string; demo: (d: DemoReactor) => number }[] = localized(() => ([
  { key: 'reactor_volume_l', label: tr('agentChat.42'), unit: tr('agentChat.43'), demo: d => d.reactor_volume_l },
  { key: 'ambient_c', label: tr('agentChat.44'), unit: '°C', demo: d => d.ambient_c },
  { key: 'target_c', label: tr('agentChat.45'), unit: '°C', demo: d => d.target_c },
  { key: 'days', label: tr('agentChat.46'), unit: tr('agentChat.47'), demo: d => d.days },
]))

function FactsPanel({ facts, demo, conversationId, onSaved, disabled }: { facts: Facts | null; demo: DemoReactor | null; conversationId: string; onSaved: (facts: Facts) => void; disabled: boolean }) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState<Record<string, string>>({})
  const [error, setError] = useState<string | null>(null)
  const start = () => {
    setDraft(Object.fromEntries([...FIELDS.map(f => [f.key, facts?.[f.key] != null ? String(facts[f.key]) : '']), ['insulation', facts?.insulation ?? '']]))
    setError(null); setEditing(true)
  }
  const save = async () => {
    const update: Record<string, number | string | null> = {}
    for (const field of FIELDS) {
      const raw = (draft[field.key] ?? '').trim().replace(',', '.').replace('−', '-')
      if (raw === '') { update[field.key] = null; continue }
      const value = Number(raw)
      if (!Number.isFinite(value)) { setError(tr('agentChat.48', { v0: field.label })); return }
      update[field.key] = value
    }
    update.insulation = draft.insulation || null
    try {
      const result = await agentApi.editFacts(conversationId, update as Partial<Facts>)
      if (!result.ok || !result.facts) { setError(result.error ?? tr('agentChat.49')); return }
      onSaved(result.facts); setEditing(false)
    } catch (caught) { setError(caught instanceof Error ? caught.message : String(caught)) }
  }
  const value = (known: unknown, unit: string, fallback?: string) => known != null && known !== ''
    ? <strong>{String(known)} {unit}</strong>
    : <span className="ac-default">{fallback ? tr('agentChat.50', { v0: fallback }) : tr('agentChat.51')}</span>
  return <aside className="ac-side panel" aria-label={tr('agentChat.52')}>
    <div className="ac-side-head"><h2>{tr('agentChat.52')}</h2>
      {!editing && <button className="ac-link" onClick={start} disabled={disabled}><Pencil size={12} />{tr('agentChat.53')}</button>}
    </div>
    <p className="ac-side-hint">{tr('agentChat.54')}</p>
    <dl className="ac-facts">
      <dt>{tr('agentChat.55')}</dt>
      <dd>{facts?.components?.length ? facts.components.map(c => <div key={componentText(c)}>{componentText(c)}</div>) : <span className="ac-default">{tr('agentChat.56')} {demo ? tr('agentChat.57', { v0: demo.working_volume_l }) : tr('agentChat.58')}</span>}</dd>
      {FIELDS.map(field => <div key={field.key} className="ac-fact-row"><dt>{field.label}</dt><dd>
        {editing
          ? <input aria-label={field.label} inputMode="decimal" value={draft[field.key] ?? ''} placeholder={demo ? String(field.demo(demo)) : ''} onChange={e => setDraft({ ...draft, [field.key]: e.target.value })} />
          : value(facts?.[field.key], field.unit, demo ? `${field.demo(demo)} ${field.unit}` : undefined)}
      </dd></div>)}
      <div className="ac-fact-row"><dt>{tr('agentChat.59')}</dt><dd>
        {editing
          ? <select aria-label={tr('agentChat.59')} value={draft.insulation ?? ''} onChange={e => setDraft({ ...draft, insulation: e.target.value })}>
              <option value="">{tr('agentChat.51')}</option>{Object.entries(INSULATION_LABELS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
            </select>
          : value(facts?.insulation ? INSULATION_LABELS[facts.insulation] ?? facts.insulation : null, '', demo ? INSULATION_LABELS[demo.insulation] : undefined)}
      </dd></div>
    </dl>
    {editing && <div className="ac-edit-actions"><button className="ac-btn ac-btn-primary" onClick={save}>{tr('agentChat.60')}</button><button className="ac-btn" onClick={() => setEditing(false)}>{tr('agentChat.61')}</button></div>}
    {error && <p className="ac-error" role="alert">{error}</p>}
    {demo && <p className="ac-demo">{tr('agentChat.62')} {materialName({ ru: demo.name, ...demo.name_i18n })}{tr('agentChat.63')} {demo.working_volume_l} {tr('agentChat.64')} {materialName({ ru: demo.location ?? '', ...demo.location_i18n })}{tr('agentChat.65')} <code>data/config/demo_reactor.json</code>.</p>}
  </aside>
}

// ---------- jury: how an answer is made ----------
const PIPELINE = localized(() => ([
  { title: tr('agentChat.66'), text: tr('agentChat.67') },
  { title: tr('agentChat.68'), text: tr('agentChat.69') },
  { title: tr('agentChat.70'), text: tr('agentChat.71') },
  { title: tr('agentChat.72'), text: tr('agentChat.73') },
  { title: tr('agentChat.74'), text: tr('agentChat.75') },
]))
function JuryPipeline() {
  return <ol className="ac-pipeline" aria-label={tr('agentChat.76')}>
    {PIPELINE.map((step, index) => <li key={step.title}><span className="ac-pipeline-n">{index + 1}</span><div><strong>{step.title}</strong><p>{step.text}</p></div></li>)}
  </ol>
}

// ---------- page ----------
export default function AgentChat() {
  const [conversationId, setConversationId] = useState(() => read(STORAGE_ID) ?? newConversationId())
  const [turns, setTurns] = useState<Turn[]>([])
  const [facts, setFacts] = useState<Facts | null>(null)
  const [input, setInput] = useState('')
  const [jury, setJury] = useState(() => read(STORAGE_JURY) === '1')
  const [useLlm, setUseLlm] = useState(true)
  const [status, setStatus] = useState<AgentStatus | null>(null)
  const [demo, setDemo] = useState<DemoReactor | null>(null)
  const abort = useRef<AbortController | null>(null)
  const bottom = useRef<HTMLDivElement | null>(null)
  const running = turns.some(turn => turn.running)

  useEffect(() => { write(STORAGE_ID, conversationId) }, [conversationId])
  useEffect(() => { write(STORAGE_JURY, jury ? '1' : '0') }, [jury])
  const refreshStatus = useCallback(() => { agentApi.status().then(setStatus).catch(() => setStatus(null)) }, [])
  useEffect(() => {
    refreshStatus(); agentApi.demoReactor().then(setDemo).catch(() => setDemo(null))
    const timer = setInterval(refreshStatus, 30000)
    return () => clearInterval(timer)
  }, [refreshStatus])
  // Restore the previous dialog after a page reload (texts + last full answer).
  useEffect(() => {
    let cancelled = false
    agentApi.conversation(conversationId).then(state => {
      if (cancelled || !state.exists) return
      setFacts(state.facts)
      const restored: Turn[] = []
      for (let i = 0; i < state.messages.length; i += 2) {
        if (state.messages[i]?.role !== 'user') continue
        const reply = state.messages[i + 1]
        restored.push({ id: `r${i}`, user: state.messages[i].content, events: [], live: '', running: false, restored: true,
          answer: { text: reply?.content ?? '', explanation: reply?.content ?? '', numbers: reply?.numbers ?? [], verdicts: reply?.verdicts ?? [], question: reply?.question ?? null,
            assumptions: [], sources: [], tools: [], data: {}, mode: reply?.mode ?? 'llm', verified: reply?.verified ?? true, language: 'ru' } })
      }
      if (restored.length && state.last_answer) restored[restored.length - 1] = { ...restored[restored.length - 1], answer: state.last_answer }
      setTurns(current => current.length ? current : restored)
    }).catch(() => { /* server offline: start empty */ })
    return () => { cancelled = true }
  }, [conversationId])
  useEffect(() => { bottom.current?.scrollIntoView?.({ behavior: 'smooth', block: 'end' }) }, [turns])

  const send = async (text: string, options: { conversation?: string; llm?: boolean; force?: boolean } = {}) => {
    const message = text.trim()
    if (!message || (running && !options.force)) return
    const id = `t${Date.now()}`
    setTurns(current => [...current, { id, user: message, events: [], live: '', running: true }])
    setInput('')
    const update = (change: (turn: Turn) => Turn) => setTurns(current => current.map(turn => turn.id === id ? change(turn) : turn))
    const controller = new AbortController(); abort.current = controller
    try {
      await streamAgentChat({ message, conversation_id: options.conversation ?? conversationId, use_llm: options.llm ?? useLlm }, event => {
        if (event.type === 'facts' && event.facts) setFacts(event.facts as Facts)
        update(turn => applyEvent(turn, event))
      }, controller.signal)
      update(turn => ({ ...turn, running: false }))
    } catch (caught) {
      const stopped = controller.signal.aborted
      update(turn => ({ ...turn, running: false, error: stopped ? tr('agentChat.77') : tr('agentChat.78', { v0: caught instanceof Error ? caught.message : String(caught) }) }))
    } finally { abort.current = null }
  }
  const submit = (event: FormEvent) => { event.preventDefault(); void send(input) }
  const newDialog = async () => {
    abort.current?.abort()
    try { await agentApi.reset(conversationId) } catch { /* the new id is enough */ }
    const id = newConversationId()
    setTurns([]); setFacts(null); setConversationId(id)
    return id
  }
  // Jury scenario: a new dialog, then the messages one after another (each waits for the answer).
  const [scenario, setScenario] = useState<string | null>(null)
  const runScenario = async (item: DemoScenario) => {
    setScenario(item.id)
    const id = await newDialog()
    try {
      for (const message of item.messages) await send(message, { conversation: id, llm: item.noLlm ? false : useLlm, force: true })
    } finally { setScenario(null) }
  }

  const gpu = status?.gpu
  const slow = speedWarning(status)
  return <div className="ac-page">
    <div className="ac-topline">
      <div><span className="eyebrow">{tr('agentChat.79')}</span><h1>{tr('app.chat')}</h1>
        <p>{tr('agentChat.80')}</p></div>
      <div className="ac-controls">
        <span className={`badge badge-${status?.llm_available ? slow ? 'amber' : 'green' : status ? 'amber' : 'muted'}`} title={slow ?? undefined}><Cpu size={11} />
          {status ? status.llm_available ? `${status.model}${gpu?.loaded ? ` · GPU ${gpu.gpu_percent}%` : ''}` : tr('agentChat.81') : tr('agentChat.82')}{slow ? ' · ⚠' : ''}</span>
        <label className="ac-switch"><input type="checkbox" checked={!useLlm} onChange={e => setUseLlm(!e.target.checked)} />{tr('agentChat.83')}</label>
        <button className={`ac-btn ${jury ? "ac-btn-primary" : ""}`} aria-pressed={jury} onClick={() => setJury(!jury)}><Gavel size={14} />{tr('agentChat.84')}</button>
        <button className="ac-btn" onClick={newDialog}><MessageSquarePlus size={14} />{tr('agentChat.85')}</button>
        <a className="ac-link" href="#/chat-v9" title={tr('agentChat.86')}>{tr('agentChat.87')}</a>
      </div>
    </div>
    {jury && <JuryPipeline />}
    {jury && <div className="ac-scenarios" role="group" aria-label={tr('agentChat.88')}>
      {DEMO_SCENARIOS.map(item => <button key={item.id} className={`ac-scenario ${item.main ? 'main' : ''}`} title={item.goal}
        disabled={running || scenario !== null} aria-busy={scenario === item.id} onClick={() => void runScenario(item)}>
        <strong>{item.title}</strong><span>{item.goal}</span>
      </button>)}
    </div>}
    <div className="ac-layout">
      <section className="ac-chat panel" aria-label={tr('agentChat.89')}>
        <div className="ac-messages" aria-live="polite">
          {!turns.length && <div className="ac-empty">
            <Bot size={30} /><h2>{tr('agentChat.90')}</h2>
            <p>{tr('agentChat.91')}</p>
            <div className="ac-examples">{EXAMPLES.map(example => <button key={example} className="ac-chip" onClick={() => void send(example)}>{example}</button>)}</div>
          </div>}
          {turns.map(turn => <article key={turn.id} className="ac-turn">
            <div className="ac-msg ac-user"><User size={15} /><p>{turn.user}</p></div>
            <div className="ac-msg ac-bot"><Bot size={15} /><div className="ac-bot-body">
              {!turn.restored && <ThinkingFeed turn={turn} jury={jury} />}
              {turn.live && !turn.answer && <p className="ac-explanation ac-live">{turn.live}<span className="ac-caret" /></p>}
              {turn.answer && <AnswerView answer={turn.answer} jury={jury} />}
              {turn.error && <p className="ac-error" role="alert">{turn.error}</p>}
            </div></div>
          </article>)}
          <div ref={bottom} />
        </div>
        <form className="ac-composer" onSubmit={submit}>
          <textarea aria-label={tr('agentChat.92')} rows={2} maxLength={2000} value={input} placeholder={tr('agentChat.93')}
            onChange={e => setInput(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void send(input) } }} />
          {running
            ? <button type="button" className="ac-btn" onClick={() => abort.current?.abort()} aria-label={tr('agentChat.94')}><CircleStop size={16} /></button>
            : <button type="submit" className="ac-btn ac-btn-primary" disabled={!input.trim()} aria-label={tr('agentChat.95')}><ArrowUp size={16} /></button>}
        </form>
        <p className="ac-footnote"><Check size={11} />{tr('agentChat.96')}</p>
      </section>
      <FactsPanel facts={facts} demo={demo} conversationId={conversationId} onSaved={setFacts} disabled={running} />
    </div>
  </div>
}
