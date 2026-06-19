import { useState, useEffect, useCallback, useRef } from 'react'

export function useJobStatus() {
  const [jobId,  setJobId]  = useState(null)
  const [status, setStatus] = useState('idle')
  const [step,   setStep]   = useState(null)
  const [steps,  setSteps]  = useState([])
  const [result, setResult] = useState(null)
  const [error,  setError]  = useState(null)
  const wsRef = useRef(null)

  const reset = useCallback(() => {
    if (wsRef.current) { wsRef.current.close(); wsRef.current = null }
    setJobId(null); setStatus('idle'); setStep(null)
    setSteps([]); setResult(null); setError(null)
  }, [])

  const fetchResult = useCallback(async (id) => {
    try {
      const res = await fetch(`/api/jobs/${id}/result`)
      if (!res.ok) throw new Error('Failed to fetch result')
      setResult(await res.json())
    } catch (e) {
      setError(e.message)
    }
  }, [])

  const connectWS = useCallback((id) => {
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const ws = new WebSocket(`${proto}//${window.location.host}/ws/jobs/${id}`)
    wsRef.current = ws

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data)
        setStatus(msg.status)
        if (msg.step) setStep(msg.step)

        if (msg.step_status) {
          setSteps(prev => {
            const entry = { step: msg.step, status: msg.step_status, detail: msg.detail || '', elapsed_s: msg.elapsed_s }
            const idx = prev.findIndex(s => s.step === msg.step)
            if (idx >= 0) { const next = [...prev]; next[idx] = entry; return next }
            return [...prev, entry]
          })
        }

        if (msg.status === 'completed') fetchResult(id)
        if (msg.status === 'failed') setError(msg.error || 'Job failed')
      } catch {}
    }

    ws.onerror = () => setError('WebSocket error')
    ws.onclose = () => { wsRef.current = null }
  }, [fetchResult])

  const upload = useCallback(async (file) => {
    reset()
    setStatus('uploading')
    const form = new FormData()
    form.append('file', file)

    try {
      const res = await fetch('/api/upload', { method: 'POST', body: form })
      const data = await res.json()
      if (!res.ok) { setError(data.error || 'Upload failed'); setStatus('failed'); return }
      setJobId(data.job_id)
      setStatus('queued')
      connectWS(data.job_id)
    } catch {
      setError('Cannot connect to server')
      setStatus('failed')
    }
  }, [reset, connectWS])

  useEffect(() => () => { if (wsRef.current) wsRef.current.close() }, [])

  return { jobId, status, step, steps, result, error, upload, reset }
}
