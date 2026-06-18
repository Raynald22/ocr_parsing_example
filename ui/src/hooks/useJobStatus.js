import { useState, useEffect, useCallback, useRef } from 'react'

/**
 * Hook untuk track job status via WebSocket.
 *
 * Flow:
 *   1. Upload file → POST /api/upload → dapat {job_id}
 *   2. Buka WebSocket ke /ws/jobs/{job_id}
 *   3. Terima real-time pipeline updates
 *   4. Saat completed → GET /api/jobs/{id}/result
 */
export function useJobStatus() {
  const [jobId,     setJobId]     = useState(null)
  const [status,    setStatus]    = useState('idle')     // idle | uploading | queued | processing | completed | failed
  const [step,      setStep]      = useState(null)       // current pipeline step
  const [steps,     setSteps]     = useState([])         // all step updates received
  const [result,    setResult]    = useState(null)        // final result (from DB)
  const [error,     setError]     = useState(null)
  const wsRef = useRef(null)

  const reset = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }
    setJobId(null)
    setStatus('idle')
    setStep(null)
    setSteps([])
    setResult(null)
    setError(null)
  }, [])

  // Fetch final result from DB
  const fetchResult = useCallback(async (id) => {
    try {
      const res = await fetch(`/api/jobs/${id}/result`)
      if (!res.ok) throw new Error('Gagal ambil hasil')
      const data = await res.json()
      setResult(data)
    } catch (e) {
      setError(e.message)
    }
  }, [])

  // Connect WebSocket and listen for updates
  const connectWS = useCallback((id) => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const ws = new WebSocket(`${protocol}//${window.location.host}/ws/jobs/${id}`)
    wsRef.current = ws

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data)

        setStatus(msg.status)
        if (msg.step) setStep(msg.step)

        if (msg.step_status) {
          setSteps(prev => {
            const existing = prev.findIndex(s => s.step === msg.step)
            const entry = {
              step:      msg.step,
              status:    msg.step_status,
              detail:    msg.detail || '',
              elapsed_s: msg.elapsed_s,
            }
            if (existing >= 0) {
              const next = [...prev]
              next[existing] = entry
              return next
            }
            return [...prev, entry]
          })
        }

        if (msg.status === 'completed') {
          fetchResult(id)
        }
        if (msg.status === 'failed') {
          setError(msg.error || 'Job gagal diproses')
        }
      } catch { /* ignore parse errors */ }
    }

    ws.onerror = () => {
      setError('WebSocket error — cek koneksi ke server')
    }

    ws.onclose = () => {
      wsRef.current = null
    }
  }, [fetchResult])

  // Upload file → create job → connect WebSocket
  const upload = useCallback(async (file) => {
    reset()
    setStatus('uploading')

    const form = new FormData()
    form.append('file', file)

    try {
      const res = await fetch('/api/upload', { method: 'POST', body: form })
      const data = await res.json()

      if (!res.ok) {
        setError(data.error || 'Upload gagal')
        setStatus('failed')
        return
      }

      setJobId(data.job_id)
      setStatus('queued')
      connectWS(data.job_id)
    } catch {
      setError('Tidak bisa terhubung ke server')
      setStatus('failed')
    }
  }, [reset, connectWS])

  // Cleanup WebSocket on unmount
  useEffect(() => {
    return () => {
      if (wsRef.current) wsRef.current.close()
    }
  }, [])

  return { jobId, status, step, steps, result, error, upload, reset }
}
