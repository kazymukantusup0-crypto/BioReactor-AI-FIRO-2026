import { request } from './api'
export type Bounds = { low: number; high: number }
export type Unit = 'kg' | 'g' | 't' | 'mL' | 'L' | 'm3'
export type AdvisorDecision = Record<string, unknown> & { reactor?: Record<string, unknown> & { reactor_working_volume_l?: number; inoculum_volume_l?: number; operating_mode?: string } }
export interface ComponentInput { id: string; material: string; material_state: string; quantity: number; unit: Unit; animal?: string; poultry_type?: string; physical_state?: string; decay_state?: string; bedding?: string; data_mode?: string; reference_profile_id?: string | null; provenance?: string; evidence?: string; properties?: Record<string, unknown> }
export interface AdvisorRequestInput {
 components: ComponentInput[]
 allow_literature_transfer?: boolean
 assume_common_dry_gas_basis?: boolean
 reactor_total_volume_l?: number
 objectives?: string[]
 decision?: AdvisorDecision
 [key: string]: unknown
}
export interface CatalogOption { value: string; label: string; material?: string; physical_state?: string }
export interface Material {
  scope_status?: string;
 id: string
 name: {ru:string;en:string;kk:string}
 physical_states: string[]
 form_states: {value:string;physical_state:string;label:string}[]
 available_reference_states: string[]
 has_numerical_profile: boolean
 support_level: string
 support_notice: string
 potential_inhibitors: string[]
 profiles: { id: string; material_state: string; matching_states?: string[]; animals?: string[]; poultry_types?: string[]; beddings?: string[]; state_transfer_note?: string; approved_scope?: string; preparation?: string; [key: string]: unknown }[]
 [key: string]: unknown
}
export interface AdvisorCatalog {
 recognized_categories: number
 approved_profile_count: number
 materials_with_approved_profiles: string[]
 complete_density_solids_bmp_profile_count: number
 materials: Material[]
 ui: { units: CatalogOption[]; animals: CatalogOption[]; decay_states: CatalogOption[]; beddings: CatalogOption[]; poultry_types: CatalogOption[]; data_modes: CatalogOption[] }
}
export interface SavedMixture {
 mixture_id: string
 revision: number
 name: string
 created_at: string
 request: AdvisorRequestInput
 display_units: Record<string, Unit>
}
export interface ComponentResult { id: string; material: string; display_name?: string; quantity: number; unit: string; volume_l?: Bounds | null; wet_mass_kg: Bounds | null; ts_mass_kg: Bounds | null; vs_mass_kg: Bounds | null; methane_reference_m3: Bounds | null; wet_mass_fraction: Bounds | null; assumptions: string[]; missing: string[]; [key: string]: unknown }
export interface AdvisorResult {
 advisor_run_id?: number; status: string; mixture: { components: ComponentResult[]; total_wet_mass_kg: Bounds | null; total_ts_kg: Bounds | null; total_vs_kg: Bounds | null; sum_separate_volumes_l: Bounds | null; additive_methane_reference_m3: Bounds | null; known_component_additive_subtotal_m3: Bounds | null; olr_kg_vs_m3_day: Bounds | null; [key: string]: unknown };
 temperature: { candidate: { temperature_c: number } | null; studies: { source_id: string; temperatures_c: number[]; kind: string; conditions: string }[]; missing: string[] };
 duration: { studies: { source_id: string; kind: string; days: number[]; conditions: string }[]; [key: string]: unknown };
 stability: { risks: string[]; [key: string]: unknown }; decision_analysis: { energy: { outputs: Record<string, Bounds> }; feasibility: { status: string; working_volume_l: number | null }; reactor_balance?: {total_energy_kwh:number|null}; decision?: {selected_scenario?:string|null}; scenarios?: {id:string;net_result_kzt:Bounds|null}[]; [key: string]: unknown };
 sources: { id: string; title: string; url: string }[]; conditional_reference_case?: AdvisorResult; [key: string]: unknown
}
export interface MixtureComparison { preferred_mixture: string | null; candidates: { label: string; result: AdvisorResult; feasibility: string }[]; [key: string]: unknown }
export const advisorApi = {
 catalog: (signal?: AbortSignal) => request<AdvisorCatalog>('/api/advisor/catalog', { signal }),
 analyze: (body: AdvisorRequestInput, signal?: AbortSignal) => request<AdvisorResult>('/api/advisor/analyze', { method: 'POST', body, timeout: 45000, signal }),
 compare: (body: {base: AdvisorRequestInput; candidates: {label:string;components:ComponentInput[]}[]}) => request<MixtureComparison>('/api/advisor/compare', { method: 'POST', body, timeout: 45000 }),
 mixtures: (signal?: AbortSignal) => request<{mixtures:SavedMixture[]}>('/api/advisor/mixtures', { signal }),
 saveMixture: (body: {name:string;request:AdvisorRequestInput;display_units:Record<string,Unit>;mixture_id?:string}) => request<SavedMixture>('/api/advisor/mixtures', { method: 'POST', body }),
 loadMixture: (id:string,revision?:number) => request<SavedMixture>(`/api/advisor/mixtures/${encodeURIComponent(id)}${revision ? `?revision=${revision}` : ''}`),
 convert: (body:{request:AdvisorRequestInput;target_unit:Unit}) => request<{conversions:{id:string;status:string;value:Bounds|null;message:string;target_unit:Unit}[]}>('/api/advisor/convert', { method:'POST', body }),
 handoff: (body:{request:AdvisorRequestInput;mode:'offline'|'no_llm'}) => request<{session_id:string;component_count:number;suggested_question:string}>('/api/advisor/handoff', {method:'POST',body}),
}
