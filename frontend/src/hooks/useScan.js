import { useCallback, useEffect, useState } from 'react'
import api, { API_BASE } from '../api/client.js'

const terminal = status => ['completed', 'failed', 'cancelled'].includes(status)
const errorMessage = e => e.response?.data?.error || e.message

export default function useScan() {
  const [job, setJob] = useState(null)
  const [error, setError] = useState('')
  const [starting, setStarting] = useState(false)
  const [recovering, setRecovering] = useState(true)
  const [reconnecting, setReconnecting] = useState(false)
  useEffect(() => {
    const controller = new AbortController()
    async function restore() {
      try {
        let lastId
        try { lastId = sessionStorage.getItem('gta.session-run') } catch { /* Storage can be disabled. */ }
        if (lastId) {
          try { setJob((await api.get(`/runs/${encodeURIComponent(lastId)}`, { signal: controller.signal })).data) }
          catch (e) { if (e.response?.status !== 404) throw e }
        }
      } catch (e) { if (!controller.signal.aborted) setError(errorMessage(e)) }
      finally { if (!controller.signal.aborted) setRecovering(false) }
    }
    restore()
    return () => controller.abort()
  }, [])

  const jobId = job?.id
  const running = Boolean(job && !terminal(job.status))
  useEffect(() => {
    if (!jobId) return
    try { sessionStorage.setItem('gta.session-run', jobId) } catch { /* Storage can be disabled. */ }
    if (!running) return
    const controller = new AbortController()
    let stream
    let timer
    let lastSeq = 0
    let stopped = false
    function accept(snapshot) {
      if (stopped) return
      lastSeq = Math.max(lastSeq, ...(snapshot.events || []).map(event => event.seq), 0)
      setJob(snapshot)
      if (terminal(snapshot.status)) {
        stopped = true; stream?.close(); clearTimeout(timer); setReconnecting(false)
        if (snapshot.error) setError(snapshot.error)
      }
    }
    async function poll() {
      try {
        const { data } = await api.get(`/runs/${jobId}`, { signal: controller.signal })
        accept(data)
      } catch (e) {
        if (!controller.signal.aborted) { setReconnecting(true); if (e.response?.status === 404) { stopped = true; setError(errorMessage(e)) } }
      }
      if (!stopped && !controller.signal.aborted) timer = setTimeout(poll, 5000)
    }
    poll()
    if (typeof EventSource !== 'undefined') {
      stream = new EventSource(`${API_BASE}/runs/${jobId}/events?after=${lastSeq}`, { withCredentials: true })
      stream.onopen = () => setReconnecting(false)
      stream.addEventListener('progress', event => {
        try {
          const next = JSON.parse(event.data)
          if (next.seq <= lastSeq) return
          lastSeq = next.seq
          setJob(previous => previous?.id === jobId ? { ...previous, ...next, events: [...(previous.events || []), next] } : previous)
        } catch { setReconnecting(true) }
      })
      stream.addEventListener('done', event => { try { accept(JSON.parse(event.data)) } catch { poll() } })
      stream.onerror = () => { if (!stopped) setReconnecting(true) }
    }
    return () => { stopped = true; controller.abort(); clearTimeout(timer); stream?.close() }
  }, [jobId, running])

  const start = useCallback(async payload => {
    setStarting(true); setError(''); setJob(null)
    try { setJob((await api.post('/runs', payload)).data) }
    catch (e) { if (e.response?.data?.job) setJob(e.response.data.job); setError(errorMessage(e)) }
    finally { setStarting(false) }
  }, [])
  const cancel = useCallback(async () => {
    if (!jobId) return
    try { setJob((await api.post(`/runs/${jobId}/cancel`)).data) }
    catch (e) { setError(errorMessage(e)) }
  }, [jobId])
  return { job, logs: job?.events || [], running, starting, recovering, reconnecting, start, cancel, error, setError }
}
