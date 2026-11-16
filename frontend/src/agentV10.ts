// Client of the agent v10 API (src/agent_v10/api.py).
// POST /api/agent/chat answers with Server-Sent Events: "event: <type>\ndata: <json>\n\n".
// EventSource only supports GET, so the stream is read with fetch + ReadableStream.

export interface NumberCard { key: string; title: string; value: string; unit: string; label: string; badge: string; low?: number; high?: number; center?: string | null; range?: string | null; details?: string[] }
/** A conclusion decided by Python (src/agent_v10/verdicts.py); the LLM only retells it. */
export interface Verdict { key: string; code: string; title: string; value: string; text: string; tone: 'good' | 'bad' | 'warn' | 'info' | string; before?: number[]; after?: number[] }
export interface Source { id?: string; title?: string; year?: number | null; url?: string | null; doi?: string | null }
export interface LlmStats { duration_ms?: number; first_token_ms?: number | null; prompt_tokens?: number | null; output_tokens?: number | null; tokens_per_s?: number | null }
export interface AgentAnswer {
  text: string; explanation: string; numbers: NumberCard[]; question: string | null; assumptions: string[]; sources: Source[]
  verdicts?: Verdict[]; tools: string[]; data: Record<string, unknown>; mode: 'llm' | 'no_llm' | 'llm_fallback' | string; verified: boolean; language: string
  model?: string; timings?: { total_ms?: number; first_answer_token_ms?: number | null; prompt_tokens_max?: number; llm_steps?: LlmStats[] }
}
export interface Component { substrate?: string; amount?: number | null; unit?: string; base_unit?: string; value?: number | null; state?: string | null }
export interface Facts {
  components: Component[]; reactor_volume_l: number | null; insulation: string | null; ambient_c: number | null
  target_c: number | null; days: number | null; operating_mode?: string | null; price_class?: string | null
}
export type AgentEvent = { type: string; t_ms?: number; [key: string]: unknown }
export interface AgentStatus { model: string; llm_available: boolean; offline: boolean; mode: string; gpu: { loaded: boolean; gpu_percent?: number; vram_gb?: number; context?: number; others?: string[] } }
export interface DemoReactor { name: string; reactor_volume_l: number; working_volume_l: number; insulation: string; ambient_c: number; target_c: number; days: number; location?: string; feedstock: { substrate: string; state: string } }
export interface StoredMessage { role: string; content: string; numbers?: NumberCard[]; verdicts?: Verdict[]; question?: string | null; verified?: boolean; mode?: string }
export interface Conversation { id: string; exists: boolean; facts: Facts; messages: StoredMessage[]; last_answer: AgentAnswer | null; language?: string }

/** Split an SSE text into complete events; returns the events and the unfinished tail. */
export function parseSSE(buffer: string): { events: AgentEvent[]; rest: string } {
  const normalized = buffer.replace(/\r\n/g, '\n')
  const blocks = normalized.split('\n\n')
  const rest = blocks.pop() ?? ''
  const events: AgentEvent[] = []
  for (const block of blocks) {
    const data = block.split('\n').filter(line => line.startsWith('data:')).map(line => line.slice(5).trimStart()).join('\n')
    if (!data) continue
    try { events.push(JSON.parse(data) as AgentEvent) } catch { /* a broken event is skipped, the stream goes on */ }
  }
  return { events, rest }
}

export async function streamAgentChat(
  body: { message: string; conversation_id: string; use_llm: boolean },
  onEvent: (event: AgentEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch('/api/agent/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), signal })
  if (!response.ok || !response.body) {
    let detail = `HTTP ${response.status}`
    try { const data = await response.json(); detail = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail ?? data) } catch { /* keep the status */ }
    throw new Error(detail)
  }
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const parsed = parseSSE(buffer)
    buffer = parsed.rest
    parsed.events.forEach(onEvent)
  }
  parseSSE(buffer + '\n\n').events.forEach(onEvent)
}

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...init })
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
  return response.json() as Promise<T>
}

export const agentApi = {
  status: () => json<AgentStatus>('/api/agent/status'),
  demoReactor: () => json<DemoReactor>('/api/agent/demo-reactor'),
  conversation: (id: string) => json<Conversation>(`/api/agent/conversations/${encodeURIComponent(id)}`),
  editFacts: (id: string, facts: Partial<Facts>) => json<{ ok: boolean; error?: string; facts?: Facts }>(`/api/agent/conversations/${encodeURIComponent(id)}/facts`, { method: 'POST', body: JSON.stringify({ facts }) }),
  reset: (id: string) => json<{ ok: boolean }>('/api/agent/reset', { method: 'POST', body: JSON.stringify({ conversation_id: id }) }),
}

export function newConversationId(): string {
  try { if (typeof crypto !== 'undefined' && crypto.randomUUID) return crypto.randomUUID() } catch { /* insecure context */ }
  return 'c' + Math.random().toString(36).slice(2) + Date.now().toString(36)
}

// ---------- labels for people (Russian UI) ----------
export const TOOL_LABELS: Record<string, string> = {
  estimate_methane: 'Расчёт метана и биогаза',
  estimate_heating_energy: 'Расчёт подогрева',
  recommend_temperature_regime: 'Выбор температурного режима',
  compare_scenarios: 'Сравнение сценариев',
  energy_balance_and_economics: 'Энергобаланс и деньги',
  search_knowledge: 'Поиск в источниках',
  extract_batch_facts: 'Разбор сырья и единиц',
  verdicts: 'Выводы и совет (считает Python)',
}
export const SUBSTRATE_LABELS: Record<string, string> = {
  cattle_manure: 'навоз КРС', swine_manure: 'свиной навоз', poultry_manure: 'птичий помёт', sheep_goat_manure: 'навоз МРС',
  horse_manure: 'конский навоз', food_waste: 'пищевые отходы', vegetable_waste: 'овощные отходы', grass: 'трава',
  silage: 'силос', straw: 'солома', manure: 'навоз',
}
export const STATE_LABELS: Record<string, string> = {
  slurry: 'жидкий', fresh_solid: 'твёрдый', dry: 'сухой', silage: 'силос', bedded: 'с подстилкой', prepared_pulp: 'пульпа',
}
export const INSULATION_LABELS: Record<string, string> = { none: 'нет', basic: 'базовое (3–5 см)', good: 'хорошее (10–15 см)' }
export const MODE_LABELS: Record<string, string> = {
  llm: 'ИИ-модель + инструменты', no_llm: 'без ИИ-модели: только расчёты', llm_fallback: 'запасной путь: шаблон вместо модели',
}

export function componentText(component: Component): string {
  const name = SUBSTRATE_LABELS[component.substrate ?? ''] ?? component.substrate ?? '?'
  // base_unit/value are normalized by Python ("2 ведра" -> 20 L); the user's own word is shown only as a fallback.
  const unit = (component.base_unit ?? component.unit ?? '').toLowerCase()
  const amount = component.value ?? component.amount
  const unitText = unit === 'l' ? 'л' : unit === 'kg' ? 'кг' : unit === 'm3' ? 'м³' : unit === 't' ? 'т' : unit
  const amountText = amount != null ? `${amount} ${unitText}`.trim() : 'количество ?'
  const state = component.state ? `, ${STATE_LABELS[component.state] ?? component.state}` : ''
  return `${name}: ${amountText}${state}`
}

/** Why the next answer may be slow (shown next to the model badge), or null when the model is ready. */
export function speedWarning(status: AgentStatus | null): string | null {
  if (!status?.llm_available) return null
  const gpu = status.gpu
  if (gpu.others?.length) return `в видеопамяти ещё ${gpu.others.join(', ')} — следующий ответ может ждать перезагрузку модели`
  if (!gpu.loaded) return 'модель ещё не загружена — первый ответ на 5–10 с дольше'
  if ((gpu.gpu_percent ?? 100) < 100) return `только ${gpu.gpu_percent}% модели на видеокарте — ответы будут медленнее`
  return null
}
