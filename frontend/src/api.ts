import type { AgentReply, Catalog, ChangeSeries, Demo, EconomicResult, EconomicSchema, ModelSchema, Overview, Prediction, Price, Reactor, Science, Session, SourceState, SystemStatus } from './types'
import type { AgentJob, JobResult } from './types'

export class ApiError extends Error {
  constructor(message: string, public status?: number) { super(message); this.name = 'ApiError' }
}
interface Options { method?: string; body?: unknown; signal?: AbortSignal; timeout?: number }
export async function request<T>(path: string, options: Options = {}): Promise<T> {
  const method = options.method ?? 'GET'
  for (let attempt = 0; attempt < (method === 'GET' ? 2 : 1); attempt++) {
    const controller = new AbortController()
    const abort = () => controller.abort()
    options.signal?.addEventListener('abort', abort, { once: true })
    if (options.signal?.aborted) controller.abort()
    const timer = setTimeout(abort, options.timeout ?? 15000)
    try {
      const response = await fetch(path, { method, signal: controller.signal, headers: { 'Content-Type': 'application/json' }, body: options.body === undefined ? undefined : JSON.stringify(options.body) })
      const data = await response.json()
      if (!response.ok) {
        const detail = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail ?? data)
        throw new ApiError(detail, response.status)
      }
      return data as T
    } catch (error) {
      if (options.signal?.aborted) throw error
      if (method === 'GET' && attempt === 0 && (!(error instanceof ApiError) || (error.status ?? 0) >= 500)) continue
      if (error instanceof ApiError) throw error
      throw new ApiError(controller.signal.aborted ? 'Время ожидания истекло. Проверьте историю перед повторной отправкой.' : 'Нет соединения с локальным сервером. Проверьте запуск FastAPI.')
    } finally { clearTimeout(timer); options.signal?.removeEventListener('abort', abort) }
  }
  throw new ApiError('Запрос не завершён')
}
const query = (values: Record<string, string | undefined>) => new URLSearchParams(Object.entries(values).filter((entry): entry is [string, string] => entry[1] !== undefined)).toString()
const root = '/api/dashboard'
export const CHAT_SESSION_KEY = 'bioreactor_chat_session_v4'
export const CHAT_ADVISOR_KEY = 'bioreactor-chat-to-advisor-v1'
export const api = {
  health: (signal?: AbortSignal) => request<{status:string}>('/health', {signal}),
  overview: (signal?: AbortSignal) => request<Overview>(`${root}/overview`, { signal }),
  status: (signal?: AbortSignal) => request<SystemStatus>(`${root}/status`, { signal }),
  schema: (model: string, signal?: AbortSignal) => request<ModelSchema>(`${root}/models/${model}/schema`, { signal }),
  predict: (model: string, context: Record<string, unknown>) => request<Prediction>(`${root}/predict`, { method: 'POST', body: { model, context }, timeout: 30000 }),
  science: (signal?: AbortSignal) => request<Science>(`${root}/scientific`, { signal }),
  economicsSchema: (signal?: AbortSignal) => request<EconomicSchema>(`${root}/economics/schema`, { signal }),
  reactor: (signal?: AbortSignal) => request<Reactor>(`${root}/reactor`, { signal }),
  catalog: (signal?: AbortSignal) => request<Catalog>('/catalog', { signal }),
  prices: (region: string, signal?: AbortSignal) => request<{ prices: Price[] }>(`/prices/current?${query({ region })}`, { signal }),
  history: (commodity: string, region: string, signal?: AbortSignal) => request<{ prices: Price[]; total: number; truncated: boolean }>(`/prices/history?${query({ commodity, region })}`, { signal }),
  changes: (commodity: string, region: string, signal?: AbortSignal) => request<{ series: ChangeSeries[] }>(`/analytics/price-change?${query({ commodity, region })}`, { signal }),
  sources: (signal?: AbortSignal) => request<{ states: SourceState[] }>('/sources/status', { signal }),
  update: (category: string) => request<{ inserted: number; sources: { source: string; status: string; error?: string }[] }>(`/updates?${query({ category })}`, { method: 'POST', timeout: 180000 }),
  compare: (data: Record<string, unknown>) => request<EconomicResult>('/scenarios/compare', { method: 'POST', body: data, timeout: 30000 }),
  impact: (id: number) => request<{ message: string; current_recommendation: string | null; profit_changes: { scenario: string; difference: number | null }[] }>(`/scenarios/${id}/price-impact`),
  newSession: (mode: string, version = '5.6') => request<Session>(`${root}/chat/sessions`, { method: 'POST', body: { mode, context: {}, conversation_version: version } }),
  upgradeSession: (id: string, research = false) => request<Session>(`${root}/chat/sessions/${id}/${research ? 'research-upgrade' : 'upgrade'}`, { method: 'POST' }),
  session: (id: string, signal?: AbortSignal) => request<Session>(`${root}/chat/sessions/${id}`, { signal }),
  message: (id: string, message: string, requestId: string) => request<AgentReply>(`${root}/chat/sessions/${id}/messages`, { method: 'POST', body: { message, request_id: requestId }, timeout: 125000 }),
  submitJob: (id: string, message: string, requestId: string, expectedVersion?: number) => request<AgentJob>(`${root}/chat/sessions/${id}/jobs`, { method: 'POST', body: { message, request_id: requestId, expected_state_version: expectedVersion } }),
  sessionJobs: (id: string, signal?: AbortSignal) => request<{jobs: AgentJob[]}>(`${root}/chat/sessions/${id}/jobs`, {signal}),
  jobResult: (id: string, signal?: AbortSignal) => request<JobResult>(`${root}/jobs/${id}/result`, {signal}),
  acknowledgeJob: (id: string) => request<AgentJob>(`${root}/jobs/${id}/ack`, {method:'POST'}),
  cancelJob: (id: string) => request<AgentJob>(`${root}/jobs/${id}/cancel`, {method:'POST'}),
  scientificState: (id: string, signal?: AbortSignal) => request<{state_version:number; dashboard_draft:{revision:number}|null}>(`${root}/chat/sessions/${id}/scientific-state`,{signal}),
  saveDraft: (id: string, base: number, revision: number, draft: unknown, signal?: AbortSignal) => request<{revision:number}>(`${root}/chat/sessions/${id}/draft`,{method:'PUT',body:{base_state_version:base,expected_revision:revision,draft},signal}),
  contract: (signal?: AbortSignal) => request<{ schema: Record<string, unknown>; units: Record<string, string>; notice: string; ingestion_enabled: boolean; commands_enabled: boolean }>(`${root}/reactor/contract`, { signal }),
  demo: (signal?: AbortSignal) => request<Demo>(`${root}/demo`, { signal }),
}
