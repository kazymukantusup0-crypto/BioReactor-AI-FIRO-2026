import { useEffect, useRef, useState } from 'react'
import { api, ApiError, CHAT_SESSION_KEY } from './api'
import type { AgentJob, JobResult, Session, Turn } from './types'

interface Delivery { requestId: string; message: string; expectedVersion?: number }
const pendingKey = (id: string) => `bioreactor-pending-delivery:${id}`
function readDelivery(raw: string | null): Delivery | undefined {
  if (!raw) return
  try {
    const value = JSON.parse(raw)
    if (value && typeof value.requestId === 'string' && /^[A-Za-z0-9_-]{8,80}$/.test(value.requestId)
      && typeof value.message === 'string' && value.message.trim().length > 0 && value.message.length <= 12000
      && (value.expectedVersion === undefined || Number.isInteger(value.expectedVersion) && value.expectedVersion >= 0)) return value
  } catch { /* Invalid input is quarantined by the caller, never submitted. */ }
}
export function useChatSession() {
  const [id, setId] = useState(() => localStorage.getItem(CHAT_SESSION_KEY) ?? '')
  const [session, setSession] = useState<Session>()
  const [turns, setTurns] = useState<Turn[]>([])
  const [jobs, setJobs] = useState<AgentJob[]>([])
  const [loading, setLoading] = useState(Boolean(id))
  const [submitting, setSubmitting] = useState(() => Boolean(id && localStorage.getItem(pendingKey(id))))
  const [error, setError] = useState('')
  const [rejectedMessage, setRejectedMessage] = useState('')
  const [deliveryError, setDeliveryError] = useState('')
  const kick = useRef(() => {})
  const sendLock = useRef(false)
  const currentId = useRef(id)
  const mounted = useRef(false)
  const action = useRef<AbortController | undefined>(undefined)
  const active = jobs.find(j => !j.terminal)
  const busy = submitting || Boolean(active)

  useEffect(() => {
    mounted.current = true
    const changed = (event: StorageEvent) => {
      if (event.key === CHAT_SESSION_KEY) {
        action.current?.abort()
        currentId.current = event.newValue ?? ''
        setId(currentId.current)
      }
    }
    window.addEventListener('storage', changed)
    return () => { mounted.current = false; action.current?.abort(); window.removeEventListener('storage', changed) }
  }, [])

  useEffect(() => {
    setSession(old => old?.id === id ? old : undefined); setTurns([]); setJobs([])
    setError(''); setDeliveryError(''); setRejectedMessage('')
    setSubmitting(Boolean(id && localStorage.getItem(pendingKey(id))))
    if (!id) { setLoading(false); return }
    setLoading(true)
    const controller = new AbortController()
    const results = new Map<string, JobResult>()
    const acknowledged = new Set<string>()
    const retryAfter = new Map<string, number>()
    let timer: ReturnType<typeof setTimeout> | undefined
    let polling = false
    let failures = 0
    let latestVersion = -1
    let deliveryAttempts = 0
    let deliveryRaw: string | null = null
    let nextDeliveryAt = 0
    const valid = () => !controller.signal.aborted && currentId.current === id
    const schedule = (delay: number) => { if (valid()) timer = setTimeout(poll, delay) }
    const clearPending = (raw: string) => {
      if (valid() && localStorage.getItem(pendingKey(id)) === raw) {
        localStorage.removeItem(pendingKey(id)); setSubmitting(false)
      }
    }
    const quarantine = (raw: string) => {
      // Preserve even malformed input for recovery; do not silently discard it.
      localStorage.setItem(`${pendingKey(id)}:rejected:${Date.now()}`, raw)
      clearPending(raw)
    }
    const renderSnapshot = (value: Session, executions: AgentJob[]) => {
      if (!valid() || (value.state_version ?? 0) < latestVersion) return
      latestVersion = value.state_version ?? 0
      const byRequest = new Map(executions.map(job => [job.request_id, job]))
      setSession(value); setJobs(executions)
      const received = value.turns.map(turn => {
        const job = byRequest.get(turn.request_id)
        const result = job ? results.get(job.id) : undefined
        return { ...turn, job, execution_result: result, reply: turn.reply ?? result?.reply ?? null }
      })
      const delivery = readDelivery(localStorage.getItem(pendingKey(id)))
      const optimistic: Turn[] = delivery && !received.some(t => t.request_id === delivery.requestId)
        ? [{ id: -1, request_id: delivery.requestId, question: delivery.message, created_at: new Date().toISOString(), status: 'submitting', reply: null }] : []
      setTurns([...received, ...optimistic]); setLoading(false)
    }
    const poll = async () => {
      if (!valid() || polling) return
      polling = true
      let executions: AgentJob[] = []
      try {
        let saved = localStorage.getItem(pendingKey(id))
        const delivery = readDelivery(saved)
        if (saved && !delivery) {
          try { const value = JSON.parse(saved); if (typeof value?.message === 'string') setRejectedMessage(value.message) } catch { /* Raw value is preserved below. */ }
          quarantine(saved); setDeliveryError('Сохранённая отправка повреждена. Доступный текст восстановлен; история загружается.'); saved = null
        }
        // Render durable history before fetching optional results or acknowledgements.
        let value = await api.session(id, controller.signal)
        if (!valid()) return
        if (value.conversation_version !== '7') {
          value = await api.upgradeSession(id, true, controller.signal)
          if (!valid()) return
        }
        // Older servers remain readable. Current servers provide one SQLite snapshot.
        executions = value.jobs ?? (await api.sessionJobs(id, controller.signal)).jobs
        if (!valid()) return
        renderSnapshot(value, executions); failures = 0; setError('')
        if (saved && delivery) {
          if (executions.some(j => j.request_id === delivery.requestId)) {
            clearPending(saved); setDeliveryError('')
          } else {
            if (saved !== deliveryRaw) { deliveryRaw = saved; deliveryAttempts = 0; nextDeliveryAt = 0 }
            if (deliveryAttempts < 5 && Date.now() >= nextDeliveryAt) {
              deliveryAttempts++
              try {
                const submitted = await api.submitJob(id, delivery.message, delivery.requestId, delivery.expectedVersion, controller.signal)
                if (!valid()) return
                executions = [...executions, submitted]
                if (!value.turns.some(t => t.request_id === delivery.requestId)) value = { ...value, turns: [...value.turns,
                  { id: -1, request_id: delivery.requestId, question: delivery.message, created_at: new Date().toISOString(), status: 'queued', reply: null }] }
                clearPending(saved); setDeliveryError('')
                renderSnapshot(value, executions)
              } catch (reason) {
                if (!valid()) return
                const status = reason instanceof ApiError ? reason.status : undefined
                if (status && status < 500 && ![408,425,429].includes(status)) {
                  quarantine(saved); setRejectedMessage(delivery.message)
                  setDeliveryError(`Сообщение не принято: ${(reason as Error).message}. Текст восстановлен для исправления.`)
                } else {
                  nextDeliveryAt = Date.now() + Math.min(10000, 1000 * 2 ** deliveryAttempts)
                  setDeliveryError(deliveryAttempts < 5
                    ? 'Доставка пока не подтверждена. Текст сохранён; повторная проверка выполняется автоматически.'
                    : 'Доставка не подтверждена после 5 попыток. Текст сохранён. Нажмите «Повторить», чтобы проверить отправку с тем же идентификатором.')
                }
              }
            }
          }
        }
        const warnings: string[] = []
        // Limit optional I/O per poll so old delivery failures cannot starve new work.
        for (const job of executions.filter(j => j.terminal && !j.acknowledged_at && !acknowledged.has(j.id)
          && (retryAfter.get(j.id) ?? 0) <= Date.now()).slice(-3)) {
          if ((retryAfter.get(job.id) ?? 0) > Date.now()) continue
          try {
            if (!results.has(job.id) && !value.turns.some(t => t.request_id === job.request_id && t.reply)) {
              const result = await api.jobResult(job.id, controller.signal)
              if (!valid()) return
              results.set(job.id, result); renderSnapshot(value, executions)
            }
            if (!job.acknowledged_at && !acknowledged.has(job.id)) {
              await api.acknowledgeJob(job.id, controller.signal)
              if (!valid()) return
              acknowledged.add(job.id)
            }
            retryAfter.delete(job.id)
          } catch (reason) {
            if (!valid()) return
            retryAfter.set(job.id, Date.now() + 30000)
            warnings.push(`Не удалось подтвердить получение одного из результатов: ${(reason as Error).message}`)
          }
        }
        if (valid() && warnings.length) setError(warnings.join(' '))
      } catch (reason) {
        if (!valid()) return
        failures++
        setError(`Связь с сервером прервана. Проверка и получение результата продолжатся автоматически. ${(reason as Error).message}`)
        setLoading(false)
      } finally {
        polling = false
        schedule(failures ? Math.min(10000, 1000 * 2 ** Math.min(failures, 3))
          : executions.some(j => !j.terminal) || Boolean(localStorage.getItem(pendingKey(id))) ? 1000 : 3000)
      }
    }
    kick.current = () => { deliveryAttempts = 0; nextDeliveryAt = 0; retryAfter.clear(); if (timer) clearTimeout(timer); if (!polling) void poll() }
    void poll()
    return () => { controller.abort(); if (timer) clearTimeout(timer) }
  }, [id])

  const newSession = async (mode: string) => {
    if (busy || sendLock.current) return
    const origin = currentId.current; const controller = new AbortController(); action.current = controller
    const valid = () => mounted.current && !controller.signal.aborted && currentId.current === origin
    sendLock.current = true; setLoading(true)
    try {
      const value = await api.newSession(mode, '7', controller.signal)
      if (!valid()) return
      localStorage.setItem(CHAT_SESSION_KEY, value.id); currentId.current = value.id
      setSession(value); setTurns([]); setJobs([]); setError(''); setDeliveryError(''); setRejectedMessage(''); setId(value.id)
    } catch (reason) { if (valid()) { setError((reason as Error).message); setLoading(false) } }
    finally { sendLock.current = false }
  }

  const send = async (message: string, mode: string) => {
    if (!message.trim() || busy || loading || sendLock.current) return false
    const origin = currentId.current; const controller = new AbortController(); action.current = controller
    const valid = () => mounted.current && !controller.signal.aborted && currentId.current === origin
    sendLock.current = true; setSubmitting(true); setError(''); setDeliveryError(''); setRejectedMessage('')
    try {
      const current = session ?? await api.newSession(mode, '7', controller.signal)
      if (!valid()) return false
      const delivery: Delivery = { requestId: crypto.randomUUID(), message: message.trim(), expectedVersion: current.state_version }
      localStorage.setItem(pendingKey(current.id), JSON.stringify(delivery))
      setTurns(old => [...old, { id: Date.now(), request_id: delivery.requestId, question: delivery.message,
        created_at: new Date().toISOString(), status: 'submitting', reply: null }])
      if (!session) {
        localStorage.setItem(CHAT_SESSION_KEY, current.id); currentId.current = current.id; setSession(current); setId(current.id)
      } else kick.current()
      return true
    } catch (reason) { if (valid()) { setError((reason as Error).message); setSubmitting(false) } return false }
    finally { sendLock.current = false }
  }

  return { session, turns, active, busy, loading, error:error || deliveryError, rejectedMessage, send, newSession, reload: () => kick.current(),
    cancel: async () => {
      if (!active) return
      const origin = currentId.current; const controller = new AbortController(); action.current = controller
      try { await api.cancelJob(active.id, controller.signal); if (mounted.current && currentId.current === origin && !controller.signal.aborted) kick.current() }
      catch (reason) { if (mounted.current && currentId.current === origin && !controller.signal.aborted) setError((reason as Error).message) }
    } }
}
