import { request } from './api'

export type ProcessStatus = 'VERIFIED' | 'CONDITIONAL' | 'INSUFFICIENT_DATA' | 'INFEASIBLE'
export interface ScientificSource { title?: string; url?: string; year?: number; doi?: string | null; [key: string]: unknown }
export interface ProcessCandidate {
  scenario_id: string; name?: string; feasibility_status: ProcessStatus;
  input_parameters: Record<string, unknown>; assumptions: Record<string, unknown> | unknown[]; scientific_sources: ScientificSource[];
  constraints: unknown[]; predicted_outputs: Record<string, unknown>; uncertainty_status: unknown; warnings: string[];
  [key: string]: unknown
}
export interface ProcessResult {
  id?: string; scenarios: ProcessCandidate[]; ranking?: Record<string, unknown>; sensitivity?: unknown;
  warnings?: string[]; missing_parameters?: string[]; [key: string]: unknown
}
export interface SavedProcess { id: string; created_at: string; input: Record<string, unknown>; result: ProcessResult }
export interface Experiment {
  id: string; name: string; experiment_date?: string | null; material?: string | null; origin: 'user' | 'laboratory';
  mass_kg?: number | null; volume_l?: number | null; temperature_c?: number | null; ph?: number | null;
  ts_percent?: number | null; vs_percent?: number | null; vs_mass_kg?: number | null; duration_days?: number | null;
  gas_volume_m3?: number | null; methane_fraction?: number | null; measurement_method?: string | null;
  gas_volume_basis?: string | null; quantitative_method_confirmed?: boolean; model_version?: string | null;
  archived?: boolean; [key: string]: unknown
}
export interface ExperimentMeasurement {
  id: string; observed_at?: string; temperature_c?: number | null; ph?: number | null;
  gas_volume_m3?: number | null; methane_fraction?: number | null; [key: string]: unknown
}
export const processApi = {
  optimize: (body: Record<string, unknown>) => request<ProcessResult>('/api/process/optimize', { method: 'POST', body, timeout: 45000 }),
  scenarios: (signal?: AbortSignal) => request<{ scenarios: SavedProcess[] }>('/api/process/scenarios', { signal }),
  scenario: (id: string) => request<SavedProcess>(`/api/process/scenarios/${id}`),
  compare: (ids: string[], objectives: string[] = []) => request<ProcessResult>('/api/process/compare', { method: 'POST', body: { scenario_ids: ids, objectives } }),
  experiments: (signal?: AbortSignal) => request<{ experiments: Experiment[] }>('/api/experiments', { signal }),
  createExperiment: (body: Record<string, unknown>) => request<Experiment>('/api/experiments', { method: 'POST', body }),
  experiment: (id: string) => request<Experiment>(`/api/experiments/${id}`),
  updateExperiment: (id: string, body: Record<string, unknown>) => request<Experiment>(`/api/experiments/${id}`, { method: 'PATCH', body }),
  archiveExperiment: (id: string) => request<Experiment>(`/api/experiments/${id}/archive`, { method: 'POST' }),
  measurements: (id: string, signal?: AbortSignal) => request<{ measurements: ExperimentMeasurement[] }>(`/api/experiments/${id}/measurements`, { signal }),
  addMeasurement: (id: string, body: Record<string, unknown>) => request<ExperimentMeasurement>(`/api/experiments/${id}/measurements`, { method: 'POST', body }),
  experimentComparison: (id: string, signal?: AbortSignal) => request<Record<string, unknown>>(`/api/experiments/${id}/comparison`, { signal }),
  exportUrl: (id: string) => `/api/experiments/${id}/export.csv`,
}

export function finiteValue(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined
}
export function compactValues(values: Record<string, string>, textual: string[] = []) {
  return Object.fromEntries(Object.entries(values).filter(([, value]) => value.trim() !== '').map(([name, value]) => [name, textual.includes(name) ? value.trim() : Number(value)]))
}
