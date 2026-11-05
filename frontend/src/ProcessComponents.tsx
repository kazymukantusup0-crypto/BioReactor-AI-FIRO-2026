import { Badge, number } from './ui'
import type { ProcessStatus } from './processApi'

export function ProcessBadge({ status }: { status: ProcessStatus | string }) {
  return <Badge tone={status === 'VERIFIED' ? 'green' : status === 'INFEASIBLE' ? 'red' : 'amber'}>{status}</Badge>
}
export interface InputField { name: string; label: string; unit?: string; type?: string; options?: [string, string][]; hint?: string }
export function ScientificFields({ fields, values, setValue, prefix = '' }: { fields: InputField[]; values: Record<string, string>; setValue: (name: string, value: string) => void; prefix?: string }) {
  return <div className="form-grid">{fields.map(field => <div className="field" key={field.name}><label htmlFor={prefix + field.name}>{field.label}</label>{field.options ? <select id={prefix + field.name} value={values[field.name] ?? ''} onChange={e => setValue(field.name, e.target.value)}><option value="">Неизвестно / не указано</option>{field.options.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select> : <input id={prefix + field.name} type={field.type ?? 'number'} step={field.type === undefined ? 'any' : undefined} value={values[field.name] ?? ''} placeholder={field.type === 'text' ? undefined : 'Неизвестно'} onChange={e => setValue(field.name, e.target.value)} />}<small>{field.unit}{field.hint && <span className="field-hint">{field.hint}</span>}</small></div>)}</div>
}
export function ResultValue({ value, unit = '', digits = 3 }: { value: unknown; unit?: string; digits?: number }) { return typeof value === 'number' && Number.isFinite(value) ? <>{number(value, digits)} {unit}</> : <span className="muted">Недостаточно данных</span> }
