import { useCallback, useEffect, useRef, useState } from 'react'

export function useQuery<T>(key: string, fetcher: (signal: AbortSignal) => Promise<T>) {
  const [entry, setEntry] = useState<{ key: string; value: T }>()
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [revision, setRevision] = useState(0)
  const fetchRef = useRef(fetcher); fetchRef.current = fetcher
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError('')
    fetchRef.current(controller.signal).then(value => { if (!controller.signal.aborted) setEntry({ key, value }) }).catch(error => { if (!controller.signal.aborted) setError(String(error.message ?? error)) }).finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [key, revision])
  return { data: entry?.key === key ? entry.value : undefined, error, loading, refresh: useCallback(() => setRevision(value => value + 1), []) }
}
