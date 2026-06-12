import { useState, useEffect, useCallback } from 'react'
import InvoiceView      from './components/InvoiceView.jsx'
import PreprocessSteps  from './components/PreprocessSteps.jsx'
import OcrComparison    from './components/OcrComparison.jsx'
import AccuracyScore    from './components/AccuracyScore.jsx'
import UploadView       from './components/UploadView.jsx'

const TABS = [
  { id: 'invoice',       label: 'Invoice'          },
  { id: 'preprocessing', label: 'Preprocessing'    },
  { id: 'ocr',          label: 'OCR'               },
  { id: 'accuracy',     label: 'Akurasi'           },
  { id: 'upload',       label: 'Upload Dokumen'    },
]

export default function App() {
  const [tab,         setTab]         = useState('invoice')
  const [groundTruth, setGroundTruth] = useState(null)
  const [results,     setResults]     = useState(null)
  const [ocrData,     setOcrData]     = useState(null)
  const [hasOutput,   setHasOutput]   = useState(false)
  const [loading,     setLoading]     = useState(true)
  const [running,     setRunning]     = useState(false)
  const [runLog,      setRunLog]      = useState('')
  const [seed,        setSeed]        = useState(42)

  const loadData = useCallback(async () => {
    try {
      const status = await fetch('/api/status').then(r => r.json())
      if (!status.ready) { setHasOutput(false); return }

      const [gt, res, ocr] = await Promise.all([
        fetch('/api/ground-truth').then(r => r.json()),
        fetch('/api/results').then(r => r.json()),
        fetch('/api/ocr').then(r => r.json()),
      ])
      setGroundTruth(gt)
      setResults(res)
      setOcrData(ocr)
      setHasOutput(true)
    } catch {
      setHasOutput(false)
    }
  }, [])

  useEffect(() => {
    loadData().finally(() => setLoading(false))
  }, [loadData])

  const runPipeline = async () => {
    setRunning(true)
    setRunLog('')
    try {
      const res = await fetch('/api/run', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ seed }),
      }).then(r => r.json())

      setRunLog(res.stdout || res.stderr || '')
      await loadData()
    } catch (e) {
      setRunLog('Error: ' + e.message)
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="min-h-screen bg-slate-50">

      {/* ── Top bar ─────────────────────────────────────────────── */}
      <header className="bg-white border-b border-slate-200 shadow-sm">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between gap-4">
          <div>
            <h1 className="text-xl font-bold text-slate-800">OCR + Parsing Pipeline</h1>
            <p className="text-sm text-slate-500">Faktur Pajak Indonesia — Contoh Pembelajaran</p>
          </div>

          {/* Run panel */}
          <div className="flex items-center gap-3">
            <label className="text-sm text-slate-600">Seed</label>
            <input
              type="number"
              value={seed}
              onChange={e => setSeed(Number(e.target.value))}
              className="w-20 px-2 py-1.5 border border-slate-300 rounded text-sm text-center"
              min={1}
            />
            <button
              onClick={runPipeline}
              disabled={running}
              className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400
                         text-white text-sm font-medium px-4 py-1.5 rounded transition-colors"
            >
              {running && (
                <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z"/>
                </svg>
              )}
              {running ? 'Menjalankan…' : 'Jalankan Pipeline'}
            </button>
          </div>
        </div>

        {/* Log output (muncul saat selesai run) */}
        {runLog && (
          <div className="max-w-7xl mx-auto px-6 pb-3">
            <pre className="bg-slate-800 text-green-400 text-xs rounded p-3 max-h-32 overflow-auto">
              {runLog}
            </pre>
          </div>
        )}

        {/* Tabs */}
        <div className="max-w-7xl mx-auto px-6 flex gap-1">
          {TABS.map(t => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
                tab === t.id
                  ? 'border-blue-600 text-blue-600'
                  : 'border-transparent text-slate-500 hover:text-slate-700'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
      </header>

      {/* ── Content ─────────────────────────────────────────────── */}
      <main className="max-w-7xl mx-auto px-6 py-6">
        {/* Tab Upload selalu tampil, tidak perlu pipeline terlebih dahulu */}
        {tab === 'upload' ? (
          <UploadView />
        ) : loading ? (
          <EmptyState icon="⏳" title="Memuat data…" />
        ) : !hasOutput ? (
          <EmptyState
            icon="📄"
            title="Belum ada output"
            desc='Klik "Jalankan Pipeline" di atas untuk memulai, atau buka tab "Upload Dokumen".'
          />
        ) : (
          <>
            {tab === 'invoice'       && <InvoiceView     groundTruth={groundTruth} />}
            {tab === 'preprocessing' && <PreprocessSteps />}
            {tab === 'ocr'           && <OcrComparison   ocrData={ocrData} />}
            {tab === 'accuracy'      && <AccuracyScore   results={results} />}
          </>
        )}
      </main>
    </div>
  )
}

function EmptyState({ icon, title, desc }) {
  return (
    <div className="flex flex-col items-center justify-center py-24 text-slate-400">
      <span className="text-5xl mb-4">{icon}</span>
      <p className="text-lg font-medium text-slate-600">{title}</p>
      {desc && <p className="text-sm mt-1">{desc}</p>}
    </div>
  )
}
