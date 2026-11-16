// AI Chat on agent v10: the agent's steps are shown live ("thinking feed").
// Farmer view: answer, number cards, one question. Jury view: every step with
// tool arguments, raw results, LLM token counts and timings.
import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { ArrowUp, Bot, BookOpen, Check, CircleStop, Cpu, Gavel, LoaderCircle, MessageSquarePlus, Pencil, ShieldAlert, ShieldCheck, User } from 'lucide-react'
import {
  agentApi, componentText, INSULATION_LABELS, MODE_LABELS, newConversationId, streamAgentChat, TOOL_LABELS,
  type AgentAnswer, type AgentEvent, type AgentStatus, type DemoReactor, type Facts, type NumberCard, type Verdict,
} from '../agentV10'
import { DEMO_SCENARIOS, type DemoScenario } from '../demoScenarios'
import '../agentChat.css'

const STORAGE_ID = 'bioreactor-agent-v10-conversation'
const STORAGE_JURY = 'bioreactor-agent-v10-jury'
const EXAMPLES = [
  'У меня 200 литров коровьего навоза, сколько будет газа?',
  'Какую температуру ставить зимой при −15 на улице? Бочка не утеплена.',
  'А если добавить 30 кг пищевых отходов?',
  'Что выгоднее: тепло или электричество? Сколько это в тенге?',
  'Сиыр көңі 200 литр, қанша газ болады?',
]

export interface Turn { id: string; user: string; events: AgentEvent[]; live: string; answer?: AgentAnswer; error?: string; running: boolean; restored?: boolean }

function read(key: string): string | null { try { return localStorage.getItem(key) } catch { return null } }
function write(key: string, value: string) { try { localStorage.setItem(key, value) } catch { /* optional */ } }
const seconds = (ms?: number | null) => ms == null ? '—' : `${(ms / 1000).toFixed(1)} с`

/** Apply one SSE event to a turn (pure: easy to test). */
export function applyEvent(turn: Turn, event: AgentEvent): Turn {
  const events = event.type === 'token' ? turn.events : [...turn.events, event]
  switch (event.type) {
    case 'token': return { ...turn, live: turn.live + String(event.text ?? '') }
    case 'token_reset': return { ...turn, events, live: '' }
    case 'answer': return { ...turn, events, answer: event as unknown as AgentAnswer, live: '' }
    case 'error': return { ...turn, events, error: String(event.message ?? 'Ошибка'), running: false }
    case 'done': return { ...turn, events, running: false }
    default: return { ...turn, events }
  }
}

// ---------- thinking feed ----------
interface FeedLine { icon: string; title: string; detail?: unknown; tone?: 'ok' | 'warn' | 'bad' }
function json(value: unknown) { return JSON.stringify(value, null, 1).replace(/\n\s*/g, ' ') }

export function feedLine(event: AgentEvent): FeedLine | null {
  switch (event.type) {
    case 'understood': return { icon: '🧠', title: `Понял вопрос · язык: ${({ ru: 'русский', kk: 'казахский', en: 'английский' } as Record<string, string>)[String(event.language)] ?? event.language}` }
    case 'facts': {
      const updates = (event.updates ?? {}) as Record<string, unknown>
      const keys = Object.keys(updates)
      return { icon: '📋', title: keys.length ? `Записал факты: ${keys.join(', ')}` : 'Новых фактов нет — беру из памяти диалога', detail: updates }
    }
    case 'llm_step': {
      const decision = event.decision === 'tool_calls' ? 'вызвать инструмент' : 'написать ответ'
      return { icon: '🤖', title: `Шаг ${event.step}: модель решила — ${decision}`, detail: { 'промпт, токенов': event.prompt_tokens, 'ответ, токенов': event.output_tokens, 'время': seconds(event.duration_ms as number), 'ток/с': event.tokens_per_s } }
    }
    case 'tool_call': return { icon: '🔧', title: `${TOOL_LABELS[String(event.name)] ?? event.name} · выбрал ${event.by === 'llm' ? 'ИИ' : 'Python'}`, detail: { tool: event.name, args: event.args } }
    case 'tool_result': return { icon: '📊', title: `Результат: ${TOOL_LABELS[String(event.name)] ?? event.name}${event.ok ? '' : ' — ошибка'} · ${event.duration_ms} мс`, detail: event.summary, tone: event.ok ? 'ok' : 'bad' }
    case 'verification': {
      const unknown = (event.unknown_numbers ?? []) as number[]
      const against = (event.contradicts ?? []) as string[]
      const next = event.attempt === 1 ? 'прошу модель переписать' : 'заменяю текст шаблоном'
      if (event.ok) return { icon: '✅', title: 'Проверка: числа взяты из расчётов, выводы не противоречат Python', tone: 'ok' }
      if (against.length) return { icon: '⚠️', title: `Текст противоречит выводу Python — ${next}`, detail: { 'вывод': against, 'чужие числа': unknown }, tone: 'warn' }
      return { icon: '⚠️', title: `Проверка чисел: ${unknown.join(', ')} нет в расчётах — ${next}`, tone: 'warn' }
    }
    case 'note': return { icon: 'ℹ️', title: String(event.message ?? event.code), tone: 'warn' }
    case 'token_reset': return event.reason === 'template' ? { icon: '📝', title: 'Текст собран по шаблону из расчётов', tone: 'warn' } : null
    case 'answer': return { icon: '💬', title: `Ответ готов · ${MODE_LABELS[String(event.mode)] ?? event.mode}` }
    case 'done': return { icon: '⏱️', title: `Готово за ${seconds(event.total_ms as number)}` }
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
    {turn.running && <li className="ac-feed-item"><LoaderCircle size={14} className="spin" /><div><span>Думаю…</span></div></li>}
  </ol>
  if (jury || turn.running) return <div className="ac-feed" aria-label="Ход рассуждений агента">{list}</div>
  return <details className="ac-feed ac-feed-collapsed"><summary>Как агент получил ответ · {lines.filter(l => l.event.type === 'tool_call').length} расчёт(а)</summary>{list}</details>
}

// ---------- answer ----------
function badgeTone(label: string) { return label === 'measured' ? 'green' : label === 'literature' ? 'cyan' : 'amber' }

/** Big central estimate (≈), small "from–to" range under it. */
export function CardValue({ card }: { card: NumberCard }) {
  if (!card.center) return <strong className="ac-card-value">{card.value}<small> {card.unit}</small></strong>
  return <>
    <strong className="ac-card-value" aria-label={`примерно ${card.center} ${card.unit}, от ${card.range}`}>≈{card.center}<small> {card.unit}</small></strong>
    <span className="ac-card-range">{card.range} {card.unit}</span>
  </>
}

function Verdicts({ items }: { items: Verdict[] }) {
  const advice = items.find(item => item.key === 'advice')
  const rest = items.filter(item => item.key !== 'advice')
  return <div className="ac-verdicts" aria-label="Выводы, рассчитанные программой">
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
      {answer.numbers.map(card => <div key={card.title} className="ac-card">
        <span className="ac-card-title">{card.title}</span>
        <CardValue card={card} />
        <span className={`badge badge-${badgeTone(card.label)}`}><span className="badge-dot" />{card.badge}</span>
      </div>)}
    </div>}
    {answer.explanation && <p className="ac-explanation">{answer.explanation}</p>}
    {answer.question && <p className="ac-question">❓ {answer.question}</p>}
    <div className="ac-answer-meta">
      {answer.verified
        ? <span className="badge badge-green"><ShieldCheck size={11} />Числа сверены с расчётами</span>
        : <span className="badge badge-amber"><ShieldAlert size={11} />Текст модели заменён шаблоном</span>}
      <span className="badge">{MODE_LABELS[answer.mode] ?? answer.mode}</span>
      {jury && answer.model && <span className="badge">{answer.model}</span>}
      {jury && answer.timings && <span className="badge">всего {seconds(answer.timings.total_ms)} · 1-й токен {seconds(answer.timings.first_answer_token_ms)} · промпт ≤ {answer.timings.prompt_tokens_max ?? '—'} ток.</span>}
    </div>
    {answer.assumptions.length > 0 && <details className="ac-details" open={jury}>
      <summary>Допущения ({answer.assumptions.length}) — замените своими данными, и расчёт уточнится</summary>
      <ul>{answer.assumptions.map(item => <li key={item}>{item}</li>)}</ul>
    </details>}
    {answer.sources.length > 0 && <details className="ac-details" open={jury}>
      <summary><BookOpen size={12} /> Источники ({answer.sources.length})</summary>
      <ul>{answer.sources.map((source, index) => <li key={source.id ?? index}>
        {source.url ? <a href={source.url} target="_blank" rel="noreferrer">{source.title ?? source.id}</a> : source.title ?? source.id}{source.year ? ` (${source.year})` : ''}
      </li>)}</ul>
    </details>}
    {jury && <details className="ac-details"><summary>Сырые данные инструментов (JSON)</summary><pre>{JSON.stringify(answer.data, null, 2)}</pre></details>}
  </div>
}

// ---------- "What the agent knows" ----------
type Editable = 'reactor_volume_l' | 'ambient_c' | 'target_c' | 'days'
const FIELDS: { key: Editable; label: string; unit: string; demo: (d: DemoReactor) => number }[] = [
  { key: 'reactor_volume_l', label: 'Объём реактора', unit: 'л', demo: d => d.reactor_volume_l },
  { key: 'ambient_c', label: 'На улице', unit: '°C', demo: d => d.ambient_c },
  { key: 'target_c', label: 'Температура в реакторе', unit: '°C', demo: d => d.target_c },
  { key: 'days', label: 'Срок сбраживания', unit: 'дней', demo: d => d.days },
]

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
      if (!Number.isFinite(value)) { setError(`${field.label}: нужно число`); return }
      update[field.key] = value
    }
    update.insulation = draft.insulation || null
    try {
      const result = await agentApi.editFacts(conversationId, update as Partial<Facts>)
      if (!result.ok || !result.facts) { setError(result.error ?? 'Не сохранилось'); return }
      onSaved(result.facts); setEditing(false)
    } catch (caught) { setError(caught instanceof Error ? caught.message : String(caught)) }
  }
  const value = (known: unknown, unit: string, fallback?: string) => known != null && known !== ''
    ? <strong>{String(known)} {unit}</strong>
    : <span className="ac-default">{fallback ? `не указано → ${fallback}` : 'не указано'}</span>
  return <aside className="ac-side panel" aria-label="Что агент знает">
    <div className="ac-side-head"><h2>Что агент знает</h2>
      {!editing && <button className="ac-link" onClick={start} disabled={disabled}><Pencil size={12} />Исправить</button>}
    </div>
    <p className="ac-side-hint">Агент запоминает факты из диалога. Пустые поля он заполняет значениями демо-реактора и пишет это в допущениях.</p>
    <dl className="ac-facts">
      <dt>Сырьё</dt>
      <dd>{facts?.components?.length ? facts.components.map(c => <div key={componentText(c)}>{componentText(c)}</div>) : <span className="ac-default">не указано → {demo ? `${demo.working_volume_l} л жидкого навоза КРС` : 'демо-партия'}</span>}</dd>
      {FIELDS.map(field => <div key={field.key} className="ac-fact-row"><dt>{field.label}</dt><dd>
        {editing
          ? <input aria-label={field.label} inputMode="decimal" value={draft[field.key] ?? ''} placeholder={demo ? String(field.demo(demo)) : ''} onChange={e => setDraft({ ...draft, [field.key]: e.target.value })} />
          : value(facts?.[field.key], field.unit, demo ? `${field.demo(demo)} ${field.unit}` : undefined)}
      </dd></div>)}
      <div className="ac-fact-row"><dt>Утепление</dt><dd>
        {editing
          ? <select aria-label="Утепление" value={draft.insulation ?? ''} onChange={e => setDraft({ ...draft, insulation: e.target.value })}>
              <option value="">не указано</option>{Object.entries(INSULATION_LABELS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
            </select>
          : value(facts?.insulation ? INSULATION_LABELS[facts.insulation] ?? facts.insulation : null, '', demo ? INSULATION_LABELS[demo.insulation] : undefined)}
      </dd></div>
    </dl>
    {editing && <div className="ac-edit-actions"><button className="ac-btn ac-btn-primary" onClick={save}>Сохранить</button><button className="ac-btn" onClick={() => setEditing(false)}>Отмена</button></div>}
    {error && <p className="ac-error" role="alert">{error}</p>}
    {demo && <p className="ac-demo">Демо-реактор: {demo.name}, рабочий объём {demo.working_volume_l} л, {demo.location ?? ''}. Файл <code>data/config/demo_reactor.json</code>.</p>}
  </aside>
}

// ---------- jury: how an answer is made ----------
const PIPELINE = [
  { title: 'Факты', text: 'Python разбирает текст: сырьё, «2 ведра» → 20 л, −15 °C, «не утеплена».' },
  { title: 'Выбор', text: 'Модель qwen3:8b (локально) выбирает инструмент из 7. Не больше 5 шагов.' },
  { title: 'Расчёт', text: 'Python: метан = VS × BMP; энергия = CH₄ × 9.97 кВт·ч/м³; подогрев = m·c·ΔT + UA·ΔT·t.' },
  { title: 'Объяснение', text: 'Модель пишет 2–4 предложения только по результатам расчёта.' },
  { title: 'Проверка', text: 'Каждое число в тексте сверяется с расчётом; чужое число → переписать, затем шаблон.' },
]
function JuryPipeline() {
  return <ol className="ac-pipeline" aria-label="Как агент получает ответ">
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
      update(turn => ({ ...turn, running: false, error: stopped ? 'Остановлено' : `Нет связи с сервером: ${caught instanceof Error ? caught.message : String(caught)}` }))
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
  return <div className="ac-page">
    <div className="ac-topline">
      <div><span className="eyebrow">АГЕНТ v10 · ЛОКАЛЬНО, БЕЗ ИНТЕРНЕТА</span><h1>AI Chat</h1>
        <p>Модель выбирает инструмент, Python считает, каждое число в ответе сверяется с расчётом.</p></div>
      <div className="ac-controls">
        <span className={`badge badge-${status?.llm_available ? 'green' : status ? 'amber' : 'muted'}`}><Cpu size={11} />
          {status ? status.llm_available ? `${status.model}${gpu?.loaded ? ` · GPU ${gpu.gpu_percent}%` : ''}` : 'Ollama недоступна — режим без ИИ' : 'проверяю модель…'}</span>
        <label className="ac-switch"><input type="checkbox" checked={!useLlm} onChange={e => setUseLlm(!e.target.checked)} />Без ИИ-модели</label>
        <button className={`ac-btn ${jury ? "ac-btn-primary" : ""}`} aria-pressed={jury} onClick={() => setJury(!jury)}><Gavel size={14} />Режим жюри</button>
        <button className="ac-btn" onClick={newDialog}><MessageSquarePlus size={14} />Новый диалог</button>
        <a className="ac-link" href="#/chat-v9" title="Предыдущая версия чата (v9)">старый чат</a>
      </div>
    </div>
    {jury && <JuryPipeline />}
    {jury && <div className="ac-scenarios" role="group" aria-label="Сценарии для показа">
      {DEMO_SCENARIOS.map(item => <button key={item.id} className={`ac-scenario ${item.main ? 'main' : ''}`} title={item.goal}
        disabled={running || scenario !== null} aria-busy={scenario === item.id} onClick={() => void runScenario(item)}>
        <strong>{item.title}</strong><span>{item.goal}</span>
      </button>)}
    </div>}
    <div className="ac-layout">
      <section className="ac-chat panel" aria-label="Диалог">
        <div className="ac-messages" aria-live="polite">
          {!turns.length && <div className="ac-empty">
            <Bot size={30} /><h2>Спросите про свою установку</h2>
            <p>Можно писать как удобно: «2 ведра», «бочка не утеплена», по-русски, по-казахски или по-английски.</p>
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
          <textarea aria-label="Сообщение агенту" rows={2} maxLength={2000} value={input} placeholder="Например: 150 л навоза КРС, на улице −10, бочка без утепления"
            onChange={e => setInput(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void send(input) } }} />
          {running
            ? <button type="button" className="ac-btn" onClick={() => abort.current?.abort()} aria-label="Остановить"><CircleStop size={16} /></button>
            : <button type="submit" className="ac-btn ac-btn-primary" disabled={!input.trim()} aria-label="Отправить"><ArrowUp size={16} /></button>}
        </form>
        <p className="ac-footnote"><Check size={11} />Все цифры считает Python по формулам и данным из литературы; ИИ только выбирает расчёт и объясняет его словами.</p>
      </section>
      <FactsPanel facts={facts} demo={demo} conversationId={conversationId} onSaved={setFacts} disabled={running} />
    </div>
  </div>
}
