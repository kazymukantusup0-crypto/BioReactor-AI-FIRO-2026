// Client of the agent v10 API (src/agent_v10/api.py).
// POST /api/agent/chat answers with Server-Sent Events: "event: <type>\ndata: <json>\n\n".
// EventSource only supports GET, so the stream is read with fetch + ReadableStream.
import { getLang, localized, tr } from './i18n'

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
export interface ServerVersion { commit: string; branch: string; fingerprint: string; started_at: string; disk_commit: string; disk_fingerprint: string; stale: boolean }
export interface AgentStatus { model: string; version?: ServerVersion; llm_available: boolean; offline: boolean; mode: string; gpu: { loaded: boolean; gpu_percent?: number; vram_gb?: number; context?: number; others?: string[] } }
export interface DemoReactor { name: string; name_i18n?: { en?: string; kk?: string }; location_i18n?: { en?: string; kk?: string }; reactor_volume_l: number; working_volume_l: number; insulation: string; ambient_c: number; target_c: number; days: number; location?: string; feedstock: { substrate: string; state: string } }
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
  const response = await fetch('/api/agent/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...body, ui_language: getLang() }), signal })
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
export const TOOL_LABELS: Record<string, string> = localized(() => ({
  estimate_methane: tr('agentV10.1'),
  estimate_heating_energy: tr('agentV10.2'),
  recommend_temperature_regime: tr('agentV10.3'),
  compare_scenarios: tr('agentV10.4'),
  energy_balance_and_economics: tr('agentV10.5'),
  search_knowledge: tr('agentV10.6'),
  extract_batch_facts: tr('agentV10.7'),
  estimate_daily_production: tr('agentV10.8'),
  gas_stove_hours: tr('agentV10.9'),
  verdicts: tr('agentV10.10'), explain_confidence: tr('agentV10.toolTrust'), list_sources: tr('agentV10.toolSources'),
}))
/** Russian plural by number: pluralRu(1, ['расчёт', 'расчёта', 'расчётов']) -> 'расчёт' (2 расчёта, 5 расчётов, 11 расчётов, 21 расчёт). */
export function pluralRu(n: number, forms: [string, string, string]): string {
  const tens = Math.abs(n) % 100
  const ones = tens % 10
  if (tens >= 11 && tens <= 14) return forms[2]
  if (ones === 1) return forms[0]
  if (ones >= 2 && ones <= 4) return forms[1]
  return forms[2]
}

export const SUBSTRATE_LABELS: Record<string, string> = localized(() => ({
  cattle_manure: tr('agentV10.11'), swine_manure: tr('agentV10.12'), poultry_manure: tr('agentV10.13'), sheep_goat_manure: tr('agentV10.14'),
  horse_manure: tr('agentV10.15'), food_waste: tr('agentV10.16'), vegetable_waste: tr('agentV10.17'), grass: tr('agentV10.18'),
  silage: tr('agentV10.19'), straw: tr('agentV10.20'), manure: tr('agentV10.21'),
}))
export const STATE_LABELS: Record<string, string> = localized(() => ({
  slurry: tr('agentV10.22'), fresh_solid: tr('agentV10.23'), dry: tr('agentV10.24'), silage: tr('agentV10.19'), bedded: tr('agentV10.25'), prepared_pulp: tr('agentV10.26'),
}))
export const INSULATION_LABELS: Record<string, string> = localized(() => ({ none: tr('agentV10.27'), basic: tr('agentV10.28'), good: tr('agentV10.29') }))
export const MODE_LABELS: Record<string, string> = localized(() => ({
  llm: tr('agentV10.30'), no_llm: tr('agentV10.31'), llm_fallback: tr('agentV10.32'),
  history: tr('agentV10.33'), refused: tr('agentV10.34'),
  trust: tr('agentV10.35'), sources: tr('agentV10.36'),
}))

export function componentText(component: Component): string {
  const name = SUBSTRATE_LABELS[component.substrate ?? ''] ?? component.substrate ?? '?'
  // base_unit/value are normalized by Python ("2 ведра" -> 20 L); the user's own word is shown only as a fallback.
  const unit = (component.base_unit ?? component.unit ?? '').toLowerCase()
  const amount = component.value ?? component.amount
  const unitText = unit === 'l' ? tr('agentV10.37') : unit === 'kg' ? tr('agentV10.38') : unit === 'm3' ? tr('agentV10.39') : unit === 't' ? tr('agentV10.40') : unit
  const amountText = amount != null ? `${amount} ${unitText}`.trim() : tr('agentV10.41')
  const state = component.state ? `, ${STATE_LABELS[component.state] ?? component.state}` : ''
  return `${name}: ${amountText}${state}`
}

/** Why the next answer may be slow (shown next to the model badge), or null when the model is ready. */
export function speedWarning(status: AgentStatus | null): string | null {
  if (!status?.llm_available) return null
  const gpu = status.gpu
  if (gpu.others?.length) return tr('agentV10.42', { v0: gpu.others.join(', ') })
  if (!gpu.loaded) return tr('agentV10.43')
  if ((gpu.gpu_percent ?? 100) < 100) return tr('agentV10.44', { v0: gpu.gpu_percent })
  return null
}
