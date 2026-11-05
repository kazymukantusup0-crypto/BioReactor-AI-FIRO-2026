import { useEffect, useRef, useState } from 'react'
import { api, ApiError, CHAT_SESSION_KEY } from './api'
import type { AgentJob, JobResult, Session, Turn } from './types'

interface Delivery { requestId: string; message: string; expectedVersion?: number }
const pendingKey = (id: string) => `bioreactor-pending-delivery:${id}`

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
  const currentId = useRef(id); currentId.current = id
  const active = jobs.find(j => !j.terminal)
  const busy = submitting || Boolean(active)

  useEffect(() => {
    const changed = (event: StorageEvent) => { if (event.key === CHAT_SESSION_KEY) setId(event.newValue ?? '') }
    window.addEventListener('storage', changed)
    return () => window.removeEventListener('storage', changed)
  }, [])

  useEffect(() => {
    if (!id) { setLoading(false); return }
    setSession(old => old?.id===id ? old : undefined); setTurns([]); setJobs([])
    setLoading(true); setSubmitting(Boolean(localStorage.getItem(pendingKey(id))))
    const controller = new AbortController()
    const results = new Map<string, JobResult>()
    let timer: ReturnType<typeof setTimeout> | undefined
    let polling = false
    let failures = 0
    let latestVersion = -1
    const valid = () => !controller.signal.aborted && currentId.current === id
    const schedule = (delay: number) => { if (valid()) timer = setTimeout(poll, delay) }
    const poll = async () => {
      if (!valid() || polling) return
      polling = true
      try {
        const saved = localStorage.getItem(pendingKey(id))
        if (saved) {
          const delivery = JSON.parse(saved) as Delivery
          try {
            await api.submitJob(id, delivery.message, delivery.requestId, delivery.expectedVersion)
            localStorage.removeItem(pendingKey(id))
            if (valid()) setSubmitting(false)
          } catch (reason) {
            if (reason instanceof ApiError && reason.status && reason.status < 500) {
              localStorage.removeItem(pendingKey(id)); if (valid()) setSubmitting(false)
              if (valid()) { setRejectedMessage(delivery.message); setDeliveryError(`Сообщение не принято: ${reason.message}. Текст восстановлен для исправления.`) }
            } else {
              throw reason
            }
          }
        }
        let [value, executions] = await Promise.all([api.session(id, controller.signal), api.sessionJobs(id, controller.signal)])
        if (value.conversation_version !== '7') value = await api.upgradeSession(id, true)
        if (!valid()) return
        for (const job of executions.jobs.filter(j => j.terminal)) {
          if (!results.has(job.id)) results.set(job.id, await api.jobResult(job.id, controller.signal))
          if (!valid()) return
          if (!job.acknowledged_at) await api.acknowledgeJob(job.id)
        }
        if (!valid()) return
        const version = value.state_version ?? 0
        if (version >= latestVersion) {
          latestVersion = version
          const byRequest = new Map(executions.jobs.map(job => [job.request_id, job]))
          setSession(value); setJobs(executions.jobs)
          const received=value.turns.map(turn => {
            const job = byRequest.get(turn.request_id)
            const result = job ? results.get(job.id) : undefined
            return { ...turn, job, execution_result: result, reply: turn.reply ?? result?.reply ?? null }
          })
          const pending=localStorage.getItem(pendingKey(id))
          const delivery=pending ? JSON.parse(pending) as Delivery : undefined
          setTurns(old => [...received,...old.filter(turn => delivery?.requestId===turn.request_id && !received.some(t => t.request_id===turn.request_id))])
        }
        failures = 0; setError(''); setLoading(false)
        schedule(executions.jobs.some(j => !j.terminal) ? 1000 : 3000)
      } catch (reason) {
        if (!valid()) return
        failures++
        setError(`Связь с сервером прервана. Проверка и получение результата продолжатся автоматически. ${(reason as Error).message}`)
        setLoading(false)
        schedule(Math.min(10000, 1000 * 2 ** Math.min(failures, 3)))
      } finally { polling = false }
    }
    kick.current = () => { if (timer) clearTimeout(timer); if (!polling) void poll() }
    void poll()
    return () => { controller.abort(); if (timer) clearTimeout(timer) }
  }, [id])

  const newSession = async (mode: string) => {
    if (busy || sendLock.current) return
    sendLock.current = true; setLoading(true)
    try {
      const value = await api.newSession(mode, '7')
      setSession(value); setTurns([]); setJobs([]); setError(''); setDeliveryError(''); setRejectedMessage('')
      localStorage.setItem(CHAT_SESSION_KEY, value.id); setId(value.id)
    } catch (reason) { setError((reason as Error).message); setLoading(false) }
    finally { sendLock.current = false }
  }

  const send = async (message: string, mode: string) => {
    if (!message.trim() || busy || loading || sendLock.current) return false
    sendLock.current = true; setSubmitting(true); setError(''); setDeliveryError(''); setRejectedMessage('')
    try {
      const current = session ?? await api.newSession(mode, '7')
      const delivery: Delivery = { requestId: crypto.randomUUID(), message: message.trim(), expectedVersion: current.state_version }
      localStorage.setItem(pendingKey(current.id), JSON.stringify(delivery))
      setTurns(old => [...old, { id: Date.now(), request_id: delivery.requestId, question: delivery.message,
        created_at: new Date().toISOString(), status: 'submitting', reply: null }])
      if (!session) {
        setSession(current); localStorage.setItem(CHAT_SESSION_KEY, current.id); setId(current.id)
      } else kick.current()
      return true
    } catch (reason) { setError((reason as Error).message); setSubmitting(false); return false }
    finally { sendLock.current = false }
  }

  return { session, turns, active, busy, loading, error:error || deliveryError, rejectedMessage, send, newSession, reload: () => kick.current(),
    cancel: async () => { if (active) { try { await api.cancelJob(active.id); kick.current() } catch (reason) { setError((reason as Error).message) } } } }
}
