import { Bot, Cable, Check, Cpu, Database, Globe2, LoaderCircle, RefreshCw, Server, ShieldCheck, WifiOff } from 'lucide-react'
import { api } from '../api'
import { useQuery } from '../hooks'
import { Badge, JsonDetails, LoadState, Notice, PageTitle, Panel, timestamp } from '../ui'
import { serverText, tr } from '../i18n'

// While the first check runs (it asks Ollama, up to ~2 s): the outline of the six cards instead of a spinner.
function SystemSkeleton() {
  return <div className="diagnostic-grid" aria-busy="true" aria-label={tr('system.loading')} data-testid="system-skeleton">
    {Array.from({ length: 6 }, (_, index) => <div key={index} className="ds-skeleton system-skeleton-card" />)}
  </div>
}

export default function System() {
  const status = useQuery('system-status', api.status); const data = status.data
  return <><PageTitle eyebrow={tr('system.eyebrow')} title={tr('system.1')} description={tr('system.2')} action={<button className="btn btn-secondary" disabled={status.loading} onClick={status.refresh}>{status.loading ? <LoaderCircle size={15} className="spin" /> : <RefreshCw size={15} />}{tr('system.3')}</button>} />{status.loading && !data && <SystemSkeleton />}<LoadState loading={false} error={status.error} retry={status.refresh} />{data &&<><div className="diagnostic-grid">{[
    { name: 'FastAPI', icon: <Server size={22} />, ok: data.fastapi.status === 'ok', status: tr('system.4'), detail: tr('system.5') },
    { name: 'SQLite', icon: <Database size={22} />, ok: data.sqlite.status === 'ok', status: data.sqlite.status === 'ok' ? tr('system.6') : tr('system.7'), detail: tr('system.8', { v0: data.sqlite.observations ?? '—', v1: data.sqlite.test_observations ?? '—' }) },
    { name: 'Ollama', icon: <Bot size={22} />, ok: data.ollama.available, status: data.ollama.available ? tr('system.9') : tr('system.10'), detail: tr('system.11', { v0: data.ollama.model }) },
    { name: 'Market Intelligence', icon: <Globe2 size={22} />, ok: data.market.status === 'available', status: tr('system.12'), detail: tr('system.13', { v0: timestamp(data.market.last_success_at) }) },
    { name: tr('system.14'), icon: <Cable size={22} />, ok: data.sensors.connected, status: data.sensors.connected ? tr('system.15') : tr('system.noSensorData'), // the old v9 tool always sends one fixed mock notice (connected: false); its current wording (relays 1–4) lives in the dictionaries
      detail: data.sensors.connected ? serverText(data.sensors.message, 'server.sensors') : tr('server.sensors') },
    { name: tr('system.16'), icon: <WifiOff size={22} />, ok: true, status: tr('system.17'), detail: tr('system.18') },
  ].map(item => <Panel className="diagnostic-card" key={item.name}><div className="diagnostic-icon">{item.icon}</div><Badge tone={item.ok ? 'green' : 'amber'}>{item.ok ? tr('system.19') : tr('system.20')}</Badge><h2>{item.name}</h2><strong>{item.status}</strong><p>{item.detail}</p></Panel>)}</div><div className="two-columns"><Panel title={tr('system.21')} subtitle={tr('system.22')}>{data.models.map(model => <div className="model-status" key={model.id}><Cpu size={20} /><div><strong>{model.id}</strong><code>{model.version ?? tr('system.23')}</code></div><Badge tone={model.available ? 'green' : 'red'}>{model.status}</Badge></div>)}</Panel><Panel title={tr('system.24')} subtitle={tr('system.25')}><div className="data-check"><ShieldCheck size={20} /><div><strong>{tr('system.26')}</strong><p>actuator_access: {String(data.actuator_access)}</p></div></div><div className="data-check"><Globe2 size={20} /><div><strong>{tr('system.27')} {data.online_provider_configured ? tr('system.28') : tr('system.29')}</strong><p>{tr('system.30')}</p></div></div><Notice tone="muted">{tr('system.31')}</Notice></Panel></div><Panel title={tr('system.32')} subtitle={tr('system.33')}><div className="table-scroll"><table><thead><tr><th>{tr('system.34')}</th><th>{tr('system.35')}</th><th>{tr('system.36')}</th><th>{tr('system.37')}</th><th>{tr('system.38')}</th></tr></thead><tbody>{data.market.source_states.map(source => <tr key={source.source_id}><td><code>{source.source_id}</code></td><td><Badge tone={source.last_status === 'success' ? 'green' : source.last_status === 'error' ? 'red' : 'amber'}>{source.last_status}</Badge></td><td>{timestamp(source.last_success_at)}</td><td>{timestamp(source.next_attempt_at)}</td><td className="table-error">{source.last_error ?? '—'}</td></tr>)}</tbody></table></div></Panel><div className="status-footer"><Check size={14} />{tr('system.39')} {timestamp(data.checked_at)}<span>{tr('system.40')} {Object.entries(data.market.validation_counts).map(([label, count]) => `${label}: ${count}`).join(' · ')}</span></div><JsonDetails value={data} title={tr('system.41')} /></>}</>
}
