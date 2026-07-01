import { useState, useEffect, useCallback } from 'react'
import { DocResult } from './UploadView.jsx'

const TYPE = {
  invoice:        { label: 'Invoice',     cls: 'bg-violet-100 text-violet-700 border-violet-200' },
  packing_list:   { label: 'Packing List', cls: 'bg-blue-100   text-blue-700   border-blue-200' },
  bill_of_lading: { label: 'B/L',          cls: 'bg-green-100  text-green-700  border-green-200' },
  generic:        { label: 'Lainnya',      cls: 'bg-slate-100  text-slate-500  border-slate-200' },
}

const fmtDate = (iso) => {
  if (!iso) return '-'
  try {
    return new Date(iso).toLocaleString('id-ID', {
      day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
    })
  } catch { return iso }
}

const confColor = (c) =>
  c == null ? 'text-slate-300'
  : c >= 95 ? 'text-green-600'
  : c >= 80 ? 'text-amber-600'
  : 'text-red-600'


export default function DocumentsView() {
  const [jobs, setJobs] = useState([])
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState('all')        // 'all' | 'review'
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState(null)
  const [detailLoading, setDetailLoading] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const r = await fetch('/api/jobs')
      const env = await r.json()
      setJobs(env.data || [])
    } catch {
      setJobs([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const openDoc = async (job) => {
    if (job.status !== 'completed') return
    setDetailLoading(true)
    try {
      const r = await fetch(`/api/jobs/${job.id}/result`)
      if (r.ok) {
        const env = await r.json()
        setSelected(env.data)
      }
    } finally {
      setDetailLoading(false)
    }
  }

  if (selected) {
    return (
      <div className="flex flex-col gap-4">
        <button onClick={() => setSelected(null)}
          className="self-start text-sm text-blue-600 hover:underline">
          ← Kembali ke daftar
        </button>
        <DocResult result={selected} onReset={() => setSelected(null)} />
      </div>
    )
  }

  const reviewCount = jobs.filter(j => j.needs_review).length
  const filtered = jobs.filter(j => {
    if (tab === 'review' && !j.needs_review) return false
    if (query) {
      const hay = `${j.filename} ${j.ref ?? ''}`.toLowerCase()
      if (!hay.includes(query.toLowerCase())) return false
    }
    return true
  })

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2 flex-wrap">
        <div className="flex rounded-lg border border-slate-200 overflow-hidden text-sm">
          <button onClick={() => setTab('all')}
            className={`px-3 py-1.5 ${tab === 'all' ? 'bg-slate-800 text-white' : 'bg-white text-slate-600 hover:bg-slate-50'}`}>
            Semua ({jobs.length})
          </button>
          <button onClick={() => setTab('review')}
            className={`px-3 py-1.5 border-l border-slate-200 ${tab === 'review' ? 'bg-amber-500 text-white' : 'bg-white text-amber-700 hover:bg-amber-50'}`}>
            ⚠ Perlu Review ({reviewCount})
          </button>
        </div>
        <input
          value={query} onChange={e => setQuery(e.target.value)}
          placeholder="🔍 cari file / no. ref"
          className="flex-1 min-w-[160px] px-3 py-1.5 text-sm border border-slate-200 rounded-lg focus:outline-none focus:border-blue-300"
        />
        <button onClick={load}
          className="px-3 py-1.5 text-sm border border-slate-200 rounded-lg text-slate-600 hover:bg-slate-50">
          ↻ Refresh
        </button>
      </div>

      <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-slate-500">
              <tr className="text-left">
                <th className="px-4 py-2.5 font-semibold">File</th>
                <th className="px-4 py-2.5 font-semibold">Tipe</th>
                <th className="px-4 py-2.5 font-semibold">No. Ref</th>
                <th className="px-4 py-2.5 font-semibold text-right">Conf.</th>
                <th className="px-4 py-2.5 font-semibold">Status</th>
                <th className="px-4 py-2.5 font-semibold whitespace-nowrap">Tanggal</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loading ? (
                <tr><td colSpan={6} className="px-4 py-10 text-center text-slate-400">Memuat…</td></tr>
              ) : filtered.length === 0 ? (
                <tr><td colSpan={6} className="px-4 py-10 text-center text-slate-400">Tidak ada dokumen.</td></tr>
              ) : filtered.map(j => {
                const t = TYPE[j.document_type] ?? TYPE.generic
                const clickable = j.status === 'completed'
                return (
                  <tr key={j.id}
                    onClick={() => openDoc(j)}
                    className={`${j.needs_review ? 'bg-amber-50/40' : 'bg-white'} ${clickable ? 'cursor-pointer hover:bg-slate-50' : 'cursor-default opacity-70'}`}>
                    <td className="px-4 py-2.5 font-medium text-slate-700 max-w-[200px] truncate">{j.filename}</td>
                    <td className="px-4 py-2.5">
                      <span className={`text-xs font-semibold px-2 py-0.5 rounded-full border ${t.cls}`}>{t.label}</span>
                    </td>
                    <td className="px-4 py-2.5 font-mono text-xs text-slate-600 whitespace-nowrap">
                      {j.ref || '—'}{j.doc_count > 1 && <span className="text-slate-400"> (+{j.doc_count - 1})</span>}
                    </td>
                    <td className={`px-4 py-2.5 text-right font-semibold ${confColor(j.confidence)}`}>
                      {j.confidence != null ? `${j.confidence.toFixed(1)}%` : '—'}
                    </td>
                    <td className="px-4 py-2.5 whitespace-nowrap">
                      <StatusCell job={j} />
                    </td>
                    <td className="px-4 py-2.5 text-slate-400 text-xs whitespace-nowrap">{fmtDate(j.created_at)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>

      {detailLoading && (
        <p className="text-center text-sm text-slate-400">Memuat detail…</p>
      )}
    </div>
  )
}


function StatusCell({ job }) {
  if (job.status !== 'completed') {
    const color = job.status === 'failed' ? 'text-red-600'
      : job.status === 'processing' ? 'text-blue-600 animate-pulse'
      : 'text-slate-400'
    return <span className={`text-xs font-medium ${color}`}>{job.status}</span>
  }
  if (job.needs_review == null) return <span className="text-xs text-slate-400">selesai</span>
  return job.needs_review
    ? <span className="text-xs font-semibold text-amber-600">⚠ Perlu review</span>
    : <span className="text-xs font-semibold text-green-600">✓ Auto-pass</span>
}
