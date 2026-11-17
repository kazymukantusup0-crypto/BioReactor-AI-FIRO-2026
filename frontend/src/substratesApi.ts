// «Сырьё и смеси»: the page asks the server for the SAME calculation the AI agent makes in the chat
// (src/dashboard/substrates_api.py -> agent tool estimate_methane).
import { request } from './api'
import templates from './askAgentTemplates.json'
import type { Lang } from './i18n'

export type FarmUnit = 'kg' | 't' | 'L' | 'm3' | 'g' | 'mL'
export interface Range { low: number; high: number }
export interface EstimateComponent {
  substrate: string; name: string; state: string; amount: number; unit: string
  wet_mass_kg: Range; methane_m3: Range; biogas_m3: Range; methane_potential_m3: Range; share_of_methane: number
}
export interface EstimateData {
  status: string; components?: EstimateComponent[]; regime_name?: string; temperature_c?: number; days?: Range
  wet_mass_kg?: Range; methane_potential_m3?: Range; methane_m3?: Range; biogas_m3?: Range; energy_kwh?: Range; methane_share?: Range
}
export interface EstimateResult {
  ok: boolean; status: string; data: EstimateData; assumptions: string[]
  sources: { id?: string; title?: string; url?: string; year?: number }[]; question: string | null
}
export interface EstimateRow { material: string; quantity: number; unit: FarmUnit; state?: string }

export const substratesApi = {
  materials: (signal?: AbortSignal) => request<{ with_data: string[] }>('/api/substrates/materials', { signal }),
  estimate: (components: EstimateRow[], language: Lang, signal?: AbortSignal) =>
    request<EstimateResult>('/api/substrates/estimate', { method: 'POST', body: { components, language }, signal, timeout: 30000 }),
}

// Grams and millilitres: the chat parser knows kg and L, so the question uses those (the server does the same).
const TO_CHAT_UNIT: Record<FarmUnit, ['kg' | 't' | 'L' | 'm3', number]> = { kg: ['kg', 1], g: ['kg', .001], t: ['t', 1], L: ['L', 1], mL: ['L', .001], m3: ['m3', 1] }

/**
 * Text for the «Спросить ИИ об этой смеси» button. tests/test_substrates_page_same_as_agent.py builds the same text
 * from askAgentTemplates.json and checks the agent answers it with the page's numbers.
 */
export function askAgentQuestion(rows: EstimateRow[], language: Lang, nameOf: (id: string) => string): string {
  const words = (templates as unknown as Record<Lang, { intro: string; and: string; ask: string; units: Record<string, string>; states: Record<string, string> }>)[language]
  const items = rows.map(row => {
    const [unit, factor] = TO_CHAT_UNIT[row.unit]
    const quantity = Number((row.quantity * factor).toPrecision(12))
    return [String(quantity), words.units[unit], words.states[row.state ?? ''], nameOf(row.material).toLowerCase()].filter(Boolean).join(' ')
  })
  const joined = items.length === 1 ? items[0] : `${items.slice(0, -1).join(', ')} ${words.and} ${items[items.length - 1]}`
  return `${words.intro} ${joined}. ${words.ask}`
}

export const CHAT_PREFILL_KEY = 'bioreactor-agent-prefill'
