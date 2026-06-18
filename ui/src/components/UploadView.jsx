import { useState, useRef, useCallback } from 'react'
import { useJobStatus } from '../hooks/useJobStatus'

// ── Konstanta ──────────────────────────────────────────────────────────────────

const ACCEPTED_IMG = '.png,.jpg,.jpeg,.bmp,.tiff,.tif,.webp'
const ACCEPTED_DOC = '.pdf,.docx,.doc,.xlsx,.xls'
const ACCEPTED     = ACCEPTED_IMG + ',' + ACCEPTED_DOC
const MAX_MB       = 20

const IMAGE_EXTS = new Set(['.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.tif', '.webp'])
const isImage = (file) => {
  if (!file?.name) return false
  return IMAGE_EXTS.has('.' + file.name.split('.').pop().toLowerCase())
}

const fileIcon = (name = '') => {
  const ext = name.split('.').pop().toLowerCase()
  if (ext === 'pdf')                                                    return '📕'
  if (['xlsx', 'xls'].includes(ext))                                  return '📗'
  if (['docx', 'doc'].includes(ext))                                  return '📘'
  if (['png','jpg','jpeg','bmp','tiff','tif','webp'].includes(ext))  return '🖼️'
  return '📄'
}

// ── Komponen utama ─────────────────────────────────────────────────────────────

export default function UploadView() {
  const [dragOver, setDragOver] = useState(false)
  const [preview,  setPreview]  = useState(null)
  const [fileName, setFileName] = useState(null)
  const inputRef = useRef(null)

  const { status, step, steps, result, error, upload, reset, jobId } = useJobStatus()

  const processing = ['uploading', 'queued', 'processing'].includes(status)

  const handleFile = useCallback((file) => {
    if (!file || processing) return

    if (file.size > MAX_MB * 1024 * 1024) {
      return
    }

    if (preview) URL.revokeObjectURL(preview)
    setPreview(isImage(file) ? URL.createObjectURL(file) : null)
    setFileName(file.name)
    upload(file)
  }, [processing, preview, upload])

  const handleReset = () => {
    reset()
    setPreview(null)
    setFileName(null)
    if (inputRef.current) inputRef.current.value = ''
  }

  const onDrop     = (e) => { e.preventDefault(); setDragOver(false); handleFile(e.dataTransfer.files[0]) }
  const onDragOver = (e) => { e.preventDefault(); setDragOver(true) }
  const onDragLeave = ()  => setDragOver(false)

  return (
    <div className="flex flex-col gap-5">

      {/* ── Drop Zone ──────────────────────────────────────────────────────── */}
      <div
        onDrop={onDrop}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onClick={() => !processing && inputRef.current?.click()}
        className={`
          relative border-2 border-dashed rounded-2xl cursor-pointer select-none
          transition-all duration-200
          ${dragOver
            ? 'border-blue-400 bg-blue-50 scale-[1.01]'
            : 'border-slate-300 bg-white hover:border-blue-300 hover:bg-slate-50'
          }
          ${processing ? 'cursor-not-allowed' : ''}
        `}
      >
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPTED}
          className="hidden"
          onChange={e => handleFile(e.target.files[0])}
        />

        {processing ? (
          <div className="flex flex-col items-center gap-4 py-12 px-6">
            {preview && (
              <img src={preview} alt="Preview"
                className="max-h-36 max-w-xs object-contain rounded-lg shadow border border-slate-200" />
            )}
            <div className="flex items-center gap-3">
              <svg className="animate-spin h-6 w-6 text-blue-500 shrink-0" viewBox="0 0 24 24" fill="none">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z"/>
              </svg>
              <div>
                <p className="text-sm font-semibold text-blue-700">
                  {status === 'uploading' ? 'Mengupload...' :
                   status === 'queued'    ? 'Menunggu worker...' :
                   step ? `${step}...` : 'Memproses...'}
                </p>
                <p className="text-xs text-slate-400 mt-0.5">
                  {fileName && <span className="font-medium text-slate-500">{fileName}</span>}
                  {jobId && <span className="ml-2 text-slate-300">#{jobId.slice(0, 8)}</span>}
                </p>
              </div>
            </div>

            {/* Live pipeline steps */}
            {steps.length > 0 && (
              <div className="flex items-center gap-2 flex-wrap justify-center">
                {steps.map((s) => (
                  <span key={s.step} className={`text-xs px-2 py-0.5 rounded-full font-medium border ${
                    s.status === 'ok'       ? 'bg-green-50  text-green-700  border-green-200' :
                    s.status === 'running'  ? 'bg-blue-50   text-blue-700   border-blue-200 animate-pulse' :
                    s.status === 'fallback' ? 'bg-amber-50  text-amber-700  border-amber-200' :
                    'bg-slate-50 text-slate-500 border-slate-200'
                  }`}>
                    {s.status === 'ok' ? '✓' : s.status === 'running' ? '⟳' : '↩'} {s.step}
                    {s.elapsed_s != null && s.status !== 'running' && (
                      <span className="ml-1 text-slate-400">{s.elapsed_s}s</span>
                    )}
                  </span>
                ))}
              </div>
            )}
          </div>
        ) : (
          <div className="flex flex-col items-center gap-3 py-10 px-6">
            <div className="flex gap-2 text-3xl">
              <span>📕</span><span>📗</span><span>📘</span><span>🖼️</span>
            </div>
            <div className="text-center">
              <p className="font-semibold text-slate-700">Drag &amp; drop atau klik untuk pilih file</p>
              <p className="text-xs text-slate-500 mt-1">
                <span className="font-medium">PDF</span> · <span className="font-medium">Word</span> ·{' '}
                <span className="font-medium">Excel</span> · <span className="font-medium">Gambar</span>
              </p>
              <p className="text-xs text-slate-400 mt-1">Maks {MAX_MB} MB</p>
            </div>
          </div>
        )}
      </div>

      {/* ── Error ──────────────────────────────────────────────────────────── */}
      {error && (
        <div className="flex items-start gap-2 bg-red-50 border border-red-200 rounded-xl px-4 py-3 text-sm text-red-700">
          <span className="shrink-0 mt-0.5">⚠</span>
          <span className="flex-1">{error}</span>
          <button onClick={handleReset} className="text-red-400 hover:text-red-600 text-xs font-medium shrink-0">
            Coba lagi
          </button>
        </div>
      )}

      {/* ── Hasil ──────────────────────────────────────────────────────────── */}
      {status === 'completed' && result && (
        <DocResult result={result} localPreview={preview} onReset={handleReset} />
      )}
    </div>
  )
}

// ── Hasil dokumen ──────────────────────────────────────────────────────────────

function DocResult({ result, localPreview, onReset }) {
  const {
    filename, elapsed_s, doc_confidence,
    extracted_text, tables, key_values,
    ai_result, tables_found, kv_found,
    passes, ai_extraction, pipeline_steps,
    image_url,
  } = result

  const imgSrc = image_url ? `/images/${image_url}` : localPreview

  return (
    <div className="flex flex-col gap-4">

      {/* ── Header ───────────────────────────────────────────────────────── */}
      <div className="bg-white border border-slate-200 rounded-2xl p-4 flex items-center gap-4 shadow-sm">
        {imgSrc ? (
          <img src={imgSrc} alt={filename}
            className="h-16 w-16 object-cover rounded-lg border border-slate-200 shrink-0" />
        ) : (
          <div className="h-16 w-16 flex items-center justify-center text-4xl shrink-0">
            {fileIcon(filename)}
          </div>
        )}
        <div className="flex-1 min-w-0">
          <p className="font-bold text-slate-800 truncate">{filename}</p>
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 mt-1">
            <Badge color="blue">Docling</Badge>
            {ai_extraction && <Badge color="violet">Qwen AI</Badge>}
            <span className="text-xs text-slate-400">{elapsed_s}s</span>
            {doc_confidence != null && (
              <span className="text-xs text-slate-400">confidence {doc_confidence.toFixed(1)}%</span>
            )}
          </div>
        </div>
        <button onClick={onReset}
          className="text-xs px-3 py-1.5 border border-slate-300 rounded-lg hover:bg-slate-50 text-slate-600 shrink-0">
          Upload lagi
        </button>
      </div>

      {/* ── Pipeline steps ───────────────────────────────────────────────── */}
      {pipeline_steps?.length > 0 && <PipelineSteps steps={pipeline_steps} />}

      {/* ── Grid konten + skor ───────────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
        <div className="lg:col-span-3">
          <DocContentPanel
            keyValues={key_values ?? {}}
            tables={tables ?? []}
            aiExtraction={ai_extraction}
          />
        </div>
        <div className="lg:col-span-2">
          <DocScoreCard
            confidence={doc_confidence}
            passes={passes}
            kvFound={kv_found}
            tablesFound={tables_found}
            aiExtraction={ai_extraction}
          />
        </div>
      </div>

      {/* ── Teks terekstrak ──────────────────────────────────────────────── */}
      {extracted_text && (
        <details className="bg-white rounded-xl border border-slate-200 shadow-sm group">
          <summary className="px-4 py-3 cursor-pointer text-sm font-semibold text-slate-700 select-none flex items-center gap-2">
            <span className="text-slate-400 group-open:rotate-90 transition-transform inline-block">▶</span>
            Teks Terekstrak
            <span className="font-normal text-slate-400 text-xs">({extracted_text.length} karakter)</span>
          </summary>
          <pre className="px-4 pb-4 text-xs font-mono text-slate-600 whitespace-pre-wrap leading-relaxed max-h-72 overflow-auto border-t border-slate-100">
            {extracted_text}
          </pre>
        </details>
      )}
    </div>
  )
}

// ── Pipeline Steps ─────────────────────────────────────────────────────────────

const STATUS_STYLE = {
  ok:       { ring: 'ring-green-400  bg-green-50',  text: 'text-green-600',  icon: '✓' },
  warn:     { ring: 'ring-amber-400  bg-amber-50',  text: 'text-amber-600',  icon: '⚠' },
  fallback: { ring: 'ring-amber-400  bg-amber-50',  text: 'text-amber-600',  icon: '↩' },
  error:    { ring: 'ring-red-400    bg-red-50',    text: 'text-red-600',    icon: '✕' },
  skip:     { ring: 'ring-slate-200  bg-slate-50',  text: 'text-slate-400',  icon: '–' },
}

const STEP_LABELS = ['OCR', 'Clean Text', 'Qwen', 'Validate JSON', 'Database']

function PipelineSteps({ steps }) {
  const allSteps = STEP_LABELS.map(label => {
    const found = steps.find(s => s.step === label)
    return found ?? { step: label, status: label === 'Database' ? 'ok' : 'skip', detail: label === 'Database' ? 'tersimpan' : 'dilewati', elapsed_s: null }
  })

  return (
    <div className="bg-white border border-slate-200 rounded-xl shadow-sm px-5 py-4">
      <div className="flex items-center">
        {allSteps.map((s, i) => {
          const st = STATUS_STYLE[s.status] ?? STATUS_STYLE.skip
          return (
            <div key={s.step} className="flex items-center flex-1 min-w-0">
              <div className="relative group flex flex-col items-center shrink-0">
                <div className={`w-8 h-8 rounded-full ring-2 flex items-center justify-center text-sm font-bold ${st.ring} ${st.text}`}>
                  {st.icon}
                </div>
                <p className="text-[11px] font-medium text-slate-600 text-center mt-1 leading-tight whitespace-nowrap">
                  {s.step === 'Database' ? 'DB' : s.step}
                </p>
                {s.elapsed_s != null && (
                  <p className="text-[10px] text-slate-400 text-center">{s.elapsed_s}s</p>
                )}
                <div className="pointer-events-none absolute bottom-full mb-2 left-1/2 -translate-x-1/2 hidden group-hover:flex z-20 w-52">
                  <div className="bg-slate-800 text-white text-xs rounded-lg px-3 py-2 text-center shadow-lg leading-relaxed w-full">
                    {s.detail}
                  </div>
                </div>
              </div>
              {i < allSteps.length - 1 && (
                <div className={`h-0.5 flex-1 mx-2 rounded-full ${
                  allSteps[i + 1].status !== 'skip' ? 'bg-green-300' : 'bg-slate-200'
                }`} />
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ── Panel konten ───────────────────────────────────────────────────────────────

function DocContentPanel({ keyValues, tables, aiExtraction }) {
  const kvEntries = Object.entries(keyValues)

  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden flex flex-col h-full">
      <div className="px-4 py-2.5 bg-slate-50 border-b border-slate-100 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2">
          <p className="text-sm font-semibold text-slate-700">Konten Ditemukan</p>
          {aiExtraction
            ? <Badge color="violet">Qwen AI</Badge>
            : <Badge color="gray">regex</Badge>
          }
        </div>
        {kvEntries.length > 0 && (
          <span className="text-xs text-slate-400">{kvEntries.length} field</span>
        )}
      </div>

      <div className="overflow-auto flex-1 divide-y divide-slate-100">
        {kvEntries.length > 0 && (
          <table className="w-full text-xs">
            <thead className="bg-slate-50 sticky top-0">
              <tr>
                <th className="text-left px-4 py-2 font-semibold text-slate-500 uppercase tracking-wide w-2/5">Field</th>
                <th className="text-left px-4 py-2 font-semibold text-slate-500 uppercase tracking-wide">Nilai</th>
              </tr>
            </thead>
            <tbody>
              {kvEntries.map(([k, v], i) => (
                <tr key={k} className={i % 2 === 0 ? 'bg-white' : 'bg-slate-50/60'}>
                  <td className="px-4 py-2 text-slate-500 font-medium align-top break-words">{k}</td>
                  <td className="px-4 py-2 text-slate-800 font-mono align-top break-words">{String(v)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {tables.length > 0 && (
          <div className="px-4 py-3">
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">
              Tabel <span className="font-normal text-slate-400">({tables.length})</span>
            </p>
            {tables.map((tbl, ti) => (
              <div key={ti} className="mb-3 overflow-x-auto rounded border border-slate-200">
                <table className="text-xs border-collapse w-full">
                  <tbody>
                    {tbl.slice(0, 10).map((row, ri) => (
                      <tr key={ri} className={ri === 0 ? 'bg-slate-100 font-semibold' : ri % 2 === 0 ? 'bg-white' : 'bg-slate-50'}>
                        {row.map((cell, ci) => (
                          <td key={ci} className="border border-slate-200 px-2 py-1 whitespace-nowrap">{cell}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))}
          </div>
        )}

        {kvEntries.length === 0 && tables.length === 0 && (
          <div className="flex flex-col items-center justify-center py-12 text-slate-400">
            <span className="text-3xl mb-2">🔍</span>
            <p className="text-sm">Tidak ada konten terstruktur ditemukan.</p>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Score Card ─────────────────────────────────────────────────────────────────

function DocScoreCard({ confidence, passes, kvFound, tablesFound, aiExtraction }) {
  const confStr = confidence != null ? confidence.toFixed(1) + '%' : '—'
  const pct = confidence != null ? Math.min(confidence, 100) : 0

  return (
    <div className={`rounded-xl border shadow-sm flex flex-col h-full ${
      passes ? 'border-green-200 bg-green-50' : 'border-amber-200 bg-amber-50'
    }`}>
      <div className={`px-4 py-2.5 border-b font-semibold text-sm ${
        passes ? 'border-green-200 text-green-800' : 'border-amber-200 text-amber-800'
      }`}>
        Skor Kualitas
      </div>
      <div className="px-4 py-5 flex flex-col gap-4 flex-1">
        <div className="text-center">
          <p className={`text-5xl font-black tracking-tight ${passes ? 'text-green-700' : 'text-amber-700'}`}>
            {confStr}
          </p>
          <p className="text-xs text-slate-500 mt-1">Docling Confidence</p>
          {confidence != null && (
            <div className="mt-3 bg-white/70 rounded-full h-2 overflow-hidden">
              <div className={`h-2 rounded-full transition-all duration-700 ${passes ? 'bg-green-500' : 'bg-amber-500'}`}
                style={{ width: pct + '%' }} />
            </div>
          )}
          <span className={`mt-3 inline-block text-xs font-bold px-3 py-1 rounded-full ${
            passes ? 'bg-green-200 text-green-800' : 'bg-amber-200 text-amber-800'
          }`}>
            {passes ? '✓ LULUS (≥95%)' : '✗ PERLU PERBAIKAN (<95%)'}
          </span>
        </div>

        <div className="bg-white/70 rounded-lg divide-y divide-slate-100 border border-slate-100 text-sm">
          <StatRow label="Sumber" value={aiExtraction ? 'Qwen AI' : 'Regex'} accent={aiExtraction} />
          <StatRow label="Key-values" value={kvFound ?? 0} />
          <StatRow label="Tabel" value={tablesFound ?? 0} />
        </div>
      </div>
    </div>
  )
}

function StatRow({ label, value, accent = false }) {
  return (
    <div className="flex justify-between items-center px-3 py-2 text-xs">
      <span className="text-slate-500">{label}</span>
      <span className={`font-semibold ${accent ? 'text-violet-700' : 'text-slate-700'}`}>{String(value)}</span>
    </div>
  )
}

// ── Badge ──────────────────────────────────────────────────────────────────────

const BADGE_COLORS = {
  blue:   'bg-blue-100   text-blue-700   border-blue-200',
  violet: 'bg-violet-100 text-violet-700 border-violet-200',
  green:  'bg-green-100  text-green-700  border-green-200',
  gray:   'bg-slate-100  text-slate-500  border-slate-200',
}

function Badge({ color = 'gray', children }) {
  return (
    <span className={`inline-flex items-center text-xs font-semibold px-2 py-0.5 rounded-full border ${BADGE_COLORS[color] ?? BADGE_COLORS.gray}`}>
      {children}
    </span>
  )
}
