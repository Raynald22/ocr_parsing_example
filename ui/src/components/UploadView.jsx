import { useState, useRef, useCallback } from 'react'

// ── Konstanta ──────────────────────────────────────────────────────────────────

const ACCEPTED_IMG = '.png,.jpg,.jpeg,.bmp,.tiff,.tif,.webp'
const ACCEPTED_DOC = '.pdf,.docx,.doc,.xlsx,.xls'
const ACCEPTED_CSV = '.csv'
const ACCEPTED     = ACCEPTED_IMG + ',' + ACCEPTED_DOC + ',' + ACCEPTED_CSV
const MAX_MB       = 20

const IMAGE_EXTS = new Set(['.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.tif', '.webp'])

const isImage = (file) => {
  if (!file?.name) return false
  const ext = '.' + file.name.split('.').pop().toLowerCase()
  return IMAGE_EXTS.has(ext)
}
const isCsv = (file) => file?.name?.toLowerCase().endsWith('.csv')

const fileExt  = (name = '') => name.split('.').pop().toLowerCase()
const fileIcon = (name = '') => {
  const ext = fileExt(name)
  if (ext === 'pdf')                                          return '📕'
  if (['xlsx', 'xls'].includes(ext))                        return '📗'
  if (['docx', 'doc'].includes(ext))                        return '📘'
  if (['png','jpg','jpeg','bmp','tiff','tif','webp'].includes(ext)) return '🖼️'
  return '📄'
}

// ── Komponen utama ─────────────────────────────────────────────────────────────

export default function UploadView() {
  const [dragOver,   setDragOver]   = useState(false)
  const [processing, setProcessing] = useState(false)
  const [result,     setResult]     = useState(null)
  const [error,      setError]      = useState(null)
  const [step,       setStep]       = useState('')
  const [csvFile,    setCsvFile]    = useState(null)
  const [preview,    setPreview]    = useState(null)   // object URL untuk gambar lokal

  const inputRef    = useRef(null)
  const csvInputRef = useRef(null)

  const handleFile = useCallback(async (file) => {
    if (!file) return

    if (file.size > MAX_MB * 1024 * 1024) {
      setError(`File terlalu besar. Maksimum ${MAX_MB} MB.`)
      return
    }

    setError(null)
    setResult(null)
    setProcessing(true)

    // Preview lokal untuk gambar
    if (preview) URL.revokeObjectURL(preview)
    setPreview(isImage(file) ? URL.createObjectURL(file) : null)

    const form = new FormData()
    form.append('file', file)

    try {
      if (isCsv(file)) {
        setStep('Membaca dan parsing CSV…')
        const res  = await fetch('/api/parse-csv', { method: 'POST', body: form })
        const data = await res.json()
        if (!res.ok) { setError(data.error || 'Gagal memproses CSV.'); return }
        setResult({ type: 'csv', data })
      } else {
        if (csvFile) form.append('csv', csvFile)
        setStep('Memproses dokumen…')
        const res  = await fetch('/api/upload', { method: 'POST', body: form })
        const data = await res.json()
        if (!res.ok) { setError(data.error || 'Terjadi kesalahan.'); return }
        setResult({ type: 'doc', data })
      }
      setStep('Selesai!')
    } catch {
      setError('Tidak bisa terhubung ke server. Pastikan python api.py sedang berjalan.')
    } finally {
      setProcessing(false)
      setStep('')
    }
  }, [csvFile, preview])

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
              <img
                src={preview}
                alt="Preview"
                className="max-h-36 max-w-xs object-contain rounded-lg shadow border border-slate-200"
              />
            )}
            <div className="flex items-center gap-3">
              <svg className="animate-spin h-6 w-6 text-blue-500 shrink-0" viewBox="0 0 24 24" fill="none">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z"/>
              </svg>
              <div>
                <p className="text-sm font-semibold text-blue-700">{step}</p>
                <p className="text-xs text-slate-400 mt-0.5">Mohon tunggu…</p>
              </div>
            </div>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-3 py-10 px-6">
            <div className="flex gap-2 text-3xl">
              <span>📕</span><span>📗</span><span>📘</span><span>🖼️</span>
            </div>
            <div className="text-center">
              <p className="font-semibold text-slate-700">Drag &amp; drop atau klik untuk pilih file</p>
              <p className="text-xs text-slate-500 mt-1">
                <span className="font-medium">PDF</span> · <span className="font-medium">Word</span> (.docx, .doc) ·{' '}
                <span className="font-medium">Excel</span> (.xlsx, .xls) ·{' '}
                <span className="font-medium">Gambar</span> (PNG, JPG, BMP, TIFF, WEBP)
              </p>
              <p className="text-xs text-slate-400 mt-1">Maks {MAX_MB} MB</p>
            </div>
          </div>
        )}
      </div>

      {/* ── Ground Truth CSV ───────────────────────────────────────────────── */}
      <div className="bg-white border border-slate-200 rounded-xl px-4 py-3">
        <div className="flex items-center justify-between gap-4">
          <div>
            <p className="text-sm font-semibold text-slate-700">
              Ground Truth CSV{' '}
              <span className="font-normal text-slate-400">(opsional)</span>
            </p>
            <p className="text-xs text-slate-500 mt-0.5">
              Upload CSV berisi nilai yang diketahui → skor CER per field
            </p>
          </div>
          <a
            href="/api/csv-template"
            download
            className="shrink-0 text-xs text-blue-600 hover:underline whitespace-nowrap"
            onClick={e => e.stopPropagation()}
          >
            Download Template ↓
          </a>
        </div>
        <div className="flex items-center gap-3 mt-3">
          <input
            ref={csvInputRef}
            type="file"
            accept=".csv"
            className="hidden"
            onChange={e => setCsvFile(e.target.files[0] || null)}
          />
          <button
            onClick={e => { e.stopPropagation(); csvInputRef.current?.click() }}
            disabled={processing}
            className="text-xs px-3 py-1.5 border border-slate-300 rounded-lg hover:bg-slate-50 text-slate-600 disabled:opacity-50 transition-colors"
          >
            Pilih CSV
          </button>
          {csvFile ? (
            <div className="flex items-center gap-1.5 text-xs text-slate-600">
              <span className="font-medium">{csvFile.name}</span>
              <button
                onClick={() => { setCsvFile(null); if (csvInputRef.current) csvInputRef.current.value = '' }}
                className="text-slate-400 hover:text-red-500"
              >✕</button>
            </div>
          ) : (
            <span className="text-xs text-slate-400">Belum ada file dipilih</span>
          )}
        </div>
      </div>

      {/* ── Error ──────────────────────────────────────────────────────────── */}
      {error && (
        <div className="flex items-start gap-2 bg-red-50 border border-red-200 rounded-xl px-4 py-3 text-sm text-red-700">
          <span className="shrink-0 mt-0.5">⚠</span>
          <span>{error}</span>
        </div>
      )}

      {/* ── Hasil ──────────────────────────────────────────────────────────── */}
      {result?.type === 'doc' && (
        <DocResult result={result.data} localPreview={preview} />
      )}
      {result?.type === 'csv' && <CsvResult result={result.data} />}
    </div>
  )
}

// ── Hasil dokumen ──────────────────────────────────────────────────────────────

function DocResult({ result, localPreview }) {
  const {
    filename, elapsed_s, doc_confidence,
    extracted_text, tables, key_values,
    ai_result, tables_found, kv_found,
    passes, ai_extraction, pipeline_steps,
    image_url, cer_score,
  } = result

  const imgSrc = image_url
    ? `/images/${image_url}`
    : localPreview || null

  return (
    <div className="flex flex-col gap-4">

      {/* ── Header ───────────────────────────────────────────────────────── */}
      <div className="bg-white border border-slate-200 rounded-2xl p-4 flex items-center gap-4 shadow-sm">
        {imgSrc ? (
          <img
            src={imgSrc}
            alt={filename}
            className="h-16 w-16 object-cover rounded-lg border border-slate-200 shrink-0"
          />
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
            {cer_score      && <Badge color="green">CER aktif</Badge>}
            <span className="text-xs text-slate-400">{elapsed_s}s</span>
            {doc_confidence != null && (
              <span className="text-xs text-slate-400">
                confidence {doc_confidence.toFixed(1)}%
              </span>
            )}
          </div>
        </div>
      </div>

      {/* ── Pipeline steps ───────────────────────────────────────────────── */}
      {pipeline_steps?.length > 0 && <PipelineSteps steps={pipeline_steps} />}

      {/* ── Grid konten + skor ───────────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
        <div className="lg:col-span-3">
          <DocContentPanel
            keyValues={key_values ?? {}}
            tables={tables ?? []}
            aiResult={ai_result}
            aiExtraction={ai_extraction}
          />
        </div>
        <div className="lg:col-span-2">
          {cer_score
            ? <CerScoreCard cerScore={cer_score} />
            : <DocScoreCard
                confidence={doc_confidence}
                passes={passes}
                kvFound={kv_found}
                tablesFound={tables_found}
                aiExtraction={ai_extraction}
              />
          }
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
    return found ?? { step: label, status: 'skip', detail: label === 'Database' ? 'segera hadir' : 'dilewati', elapsed_s: null }
  })

  return (
    <div className="bg-white border border-slate-200 rounded-xl shadow-sm px-5 py-4">
      <div className="flex items-center">
        {allSteps.map((s, i) => {
          const st = STATUS_STYLE[s.status] ?? STATUS_STYLE.skip
          return (
            <div key={s.step} className="flex items-center flex-1 min-w-0">
              {/* Step node */}
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
                {s.step === 'Database' && (
                  <p className="text-[10px] text-slate-300 text-center">soon</p>
                )}

                {/* Tooltip */}
                <div className="pointer-events-none absolute bottom-full mb-2 left-1/2 -translate-x-1/2 hidden group-hover:flex z-20 w-52">
                  <div className="bg-slate-800 text-white text-xs rounded-lg px-3 py-2 text-center shadow-lg leading-relaxed w-full">
                    {s.detail}
                  </div>
                </div>
              </div>

              {/* Connector */}
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

function DocContentPanel({ keyValues, tables, aiResult, aiExtraction }) {
  const kvEntries = Object.entries(keyValues)

  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden flex flex-col h-full">
      {/* Header */}
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

        {/* Key-Values sebagai tabel */}
        {kvEntries.length > 0 && (
          <table className="w-full text-xs">
            <thead className="bg-slate-50 sticky top-0">
              <tr>
                <th className="text-left px-4 py-2 font-semibold text-slate-500 uppercase tracking-wide w-2/5">
                  Field
                </th>
                <th className="text-left px-4 py-2 font-semibold text-slate-500 uppercase tracking-wide">
                  Nilai
                </th>
              </tr>
            </thead>
            <tbody>
              {kvEntries.map(([k, v], i) => (
                <tr key={k} className={i % 2 === 0 ? 'bg-white' : 'bg-slate-50/60'}>
                  <td className="px-4 py-2 text-slate-500 font-medium align-top break-words">
                    {k}
                  </td>
                  <td className="px-4 py-2 text-slate-800 font-mono align-top break-words">
                    {String(v)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {/* Tabel dari Docling */}
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
                          <td key={ci} className="border border-slate-200 px-2 py-1 whitespace-nowrap">
                            {cell}
                          </td>
                        ))}
                      </tr>
                    ))}
                    {tbl.length > 10 && (
                      <tr>
                        <td colSpan={tbl[0]?.length || 1} className="text-center text-slate-400 py-1.5">
                          +{tbl.length - 10} baris…
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            ))}
          </div>
        )}

        {/* Empty state */}
        {kvEntries.length === 0 && tables.length === 0 && (
          <div className="flex flex-col items-center justify-center py-12 text-slate-400">
            <span className="text-3xl mb-2">🔍</span>
            <p className="text-sm">Tidak ada konten terstruktur ditemukan.</p>
            <p className="text-xs mt-1">Lihat teks terekstrak di bawah.</p>
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
        {/* Confidence besar */}
        <div className="text-center">
          <p className={`text-5xl font-black tracking-tight ${passes ? 'text-green-700' : 'text-amber-700'}`}>
            {confStr}
          </p>
          <p className="text-xs text-slate-500 mt-1">Docling Confidence</p>

          {/* Progress bar */}
          {confidence != null && (
            <div className="mt-3 bg-white/70 rounded-full h-2 overflow-hidden">
              <div
                className={`h-2 rounded-full transition-all duration-700 ${passes ? 'bg-green-500' : 'bg-amber-500'}`}
                style={{ width: pct + '%' }}
              />
            </div>
          )}

          <span className={`mt-3 inline-block text-xs font-bold px-3 py-1 rounded-full ${
            passes ? 'bg-green-200 text-green-800' : 'bg-amber-200 text-amber-800'
          }`}>
            {passes ? '✓ LULUS (≥95%)' : '✗ PERLU PERBAIKAN (<95%)'}
          </span>
        </div>

        {/* Stats */}
        <div className="bg-white/70 rounded-lg divide-y divide-slate-100 border border-slate-100 text-sm">
          <StatRow label="Sumber ekstraksi" value={aiExtraction ? 'Qwen AI' : 'Regex'} accent={aiExtraction} />
          <StatRow label="Pasangan kunci:nilai" value={kvFound ?? 0} />
          <StatRow label="Tabel ditemukan" value={tablesFound ?? 0} />
        </div>

        {!passes && (
          <div className="bg-amber-100/60 rounded-lg px-3 py-2 text-xs text-amber-800 border border-amber-200">
            <strong>Tips:</strong> Gunakan PDF teks (bukan scan) atau gambar resolusi ≥ 300 DPI untuk hasil lebih baik.
          </div>
        )}
      </div>
    </div>
  )
}

function StatRow({ label, value, accent = false }) {
  return (
    <div className="flex justify-between items-center px-3 py-2 text-xs">
      <span className="text-slate-500">{label}</span>
      <span className={`font-semibold ${accent ? 'text-violet-700' : 'text-slate-700'}`}>
        {String(value)}
      </span>
    </div>
  )
}

// ── CER Score Card ─────────────────────────────────────────────────────────────

function CerScoreCard({ cerScore }) {
  const passes = cerScore.passes_threshold
  const pct    = (v) => (v * 100).toFixed(1) + '%'

  const rowStyle = (f) => {
    if (f.exact_match) return 'bg-green-50 text-green-800'
    if (f.cer < 0.3)   return 'bg-amber-50 text-amber-800'
    return 'bg-red-50 text-red-700'
  }
  const rowLabel = (f) => {
    if (f.exact_match)  return <span className="font-bold text-green-700">EXACT</span>
    if (f.cer < 1.0)    return <span className="font-semibold">{((1-f.cer)*100).toFixed(0)}%</span>
    return <span className="font-bold text-red-600">MISS</span>
  }

  return (
    <div className={`rounded-xl border shadow-sm flex flex-col h-full ${
      passes ? 'border-green-200 bg-green-50' : 'border-red-200 bg-red-50'
    }`}>
      <div className={`px-4 py-2.5 border-b font-semibold text-sm ${
        passes ? 'border-green-200 text-green-800' : 'border-red-200 text-red-800'
      }`}>
        Skor CER
      </div>

      <div className="px-4 py-5 flex flex-col gap-4 flex-1">
        <div className="text-center">
          <p className={`text-5xl font-black tracking-tight ${passes ? 'text-green-700' : 'text-red-700'}`}>
            {pct(cerScore.char_accuracy)}
          </p>
          <p className="text-xs text-slate-500 mt-1">Character Accuracy</p>
          <div className="mt-3 bg-white/70 rounded-full h-2 overflow-hidden">
            <div
              className={`h-2 rounded-full transition-all duration-700 ${passes ? 'bg-green-500' : 'bg-red-500'}`}
              style={{ width: pct(Math.min(cerScore.char_accuracy, 1)) }}
            />
          </div>
          <span className={`mt-3 inline-block text-xs font-bold px-3 py-1 rounded-full ${
            passes ? 'bg-green-200 text-green-800' : 'bg-red-200 text-red-800'
          }`}>
            {passes ? '✓ LULUS (≥95%)' : '✗ TIDAK LULUS (<95%)'}
          </span>
        </div>

        <div className="bg-white/70 rounded-lg overflow-hidden border border-slate-100 text-xs">
          <div className="grid grid-cols-3 px-3 py-1.5 bg-slate-100/70 font-semibold text-slate-500 border-b border-slate-200">
            <span>Field</span>
            <span>Hasil</span>
            <span className="text-right">Status</span>
          </div>
          {cerScore.fields.map(f => (
            <div key={f.field} className={`grid grid-cols-3 px-3 py-1.5 ${rowStyle(f)}`}>
              <span className="font-medium truncate">{f.field}</span>
              <span className="truncate opacity-75">{f.got || '—'}</span>
              <span className="text-right">{rowLabel(f)}</span>
            </div>
          ))}
        </div>

        <div className="flex justify-between text-xs text-slate-500">
          <span>Exact: {pct(cerScore.exact_match_rate)}</span>
          <span>CER: {cerScore.overall_cer.toFixed(3)}</span>
        </div>
      </div>
    </div>
  )
}

// ── CSV Result ─────────────────────────────────────────────────────────────────

function CsvResult({ result }) {
  const { filename, fields, fields_found, fields_total, math_ok } = result

  const LABELS = {
    nomor_faktur:   'No. Faktur',    tanggal:        'Tanggal',
    jatuh_tempo:    'Jatuh Tempo',   nama_penjual:   'Penjual',
    npwp_penjual:   'NPWP Penjual',  nama_pembeli:   'Pembeli',
    npwp_pembeli:   'NPWP Pembeli',  alamat_pembeli: 'Alamat',
    subtotal:       'Subtotal',      ppn:            'PPN',
    total:          'Total',
  }
  const NUM_FIELDS = new Set(['subtotal', 'ppn', 'total'])

  const rp = (v) => v != null ? 'Rp ' + Number(v).toLocaleString('id-ID') : null
  const completeness = fields_found / fields_total

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2 text-sm">
        <span className="text-2xl">📄</span>
        <span className="font-bold text-slate-800">{filename}</span>
        <Badge color="blue">CSV · Tanpa OCR</Badge>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
        <div className="lg:col-span-3 bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
          <div className="px-4 py-2.5 bg-slate-50 border-b border-slate-100 flex items-center justify-between">
            <p className="text-sm font-semibold text-slate-700">Field dari CSV</p>
            <span className="text-xs text-slate-400">{fields_found}/{fields_total} field</span>
          </div>
          <table className="w-full text-xs">
            <tbody>
              {Object.entries(LABELS).map(([key, label], i) => {
                const val = fields[key]
                const fmt = NUM_FIELDS.has(key) && val != null ? rp(val) : val != null ? String(val) : null
                return (
                  <tr key={key} className={i % 2 === 0 ? 'bg-white' : 'bg-slate-50/60'}>
                    <td className="px-4 py-2 text-slate-500 font-medium w-1/3">{label}</td>
                    <td className={`px-4 py-2 font-mono ${fmt ? 'text-slate-800' : 'text-slate-300 italic'} ${key === 'total' ? 'font-bold text-blue-700' : ''}`}>
                      {fmt ?? 'tidak ditemukan'}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>

        <div className="lg:col-span-2 bg-white rounded-xl border border-slate-200 shadow-sm flex flex-col">
          <div className="px-4 py-2.5 bg-slate-50 border-b border-slate-100">
            <p className="text-sm font-semibold text-slate-700">Validasi</p>
          </div>
          <div className="px-4 py-4 flex flex-col gap-4 flex-1">
            <div>
              <div className="flex justify-between text-xs mb-1.5 text-slate-600">
                <span>Field terisi</span>
                <span className="font-bold">{fields_found}/{fields_total}</span>
              </div>
              <div className="bg-slate-100 rounded-full h-2 overflow-hidden">
                <div className="h-2 rounded-full bg-blue-500 transition-all duration-700"
                     style={{ width: `${completeness * 100}%` }} />
              </div>
              <p className="text-xs text-slate-400 mt-1">{(completeness * 100).toFixed(0)}% field ditemukan</p>
            </div>

            <div className="border-t border-slate-100 pt-3">
              <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">Konsistensi Angka</p>
              <p className={`text-sm font-semibold ${
                math_ok === true ? 'text-green-700' : math_ok === false ? 'text-red-600' : 'text-slate-400'
              }`}>
                {math_ok === true ? '✓ Subtotal + PPN = Total' :
                 math_ok === false ? '✗ Angka tidak konsisten' : '— Tidak dapat dicek'}
              </p>
              {fields.subtotal != null && fields.ppn != null && (
                <p className="text-xs text-slate-400 mt-1 font-mono">
                  {rp(fields.subtotal)} + {rp(fields.ppn)} = {rp(fields.subtotal + fields.ppn)}
                </p>
              )}
            </div>

            <div className="bg-blue-50 rounded-lg px-3 py-2 text-xs text-blue-700 border border-blue-100 mt-auto">
              Ini adalah parsing CSV langsung — tidak ada OCR. Upload gambar invoice untuk skor akurasi OCR.
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Utilitas kecil ─────────────────────────────────────────────────────────────

const BADGE = {
  blue:   'bg-blue-100  text-blue-700  border-blue-200',
  violet: 'bg-violet-100 text-violet-700 border-violet-200',
  green:  'bg-green-100 text-green-700 border-green-200',
  gray:   'bg-slate-100 text-slate-500 border-slate-200',
}

function Badge({ color = 'gray', children }) {
  return (
    <span className={`inline-flex items-center text-xs font-semibold px-2 py-0.5 rounded-full border ${BADGE[color] ?? BADGE.gray}`}>
      {children}
    </span>
  )
}
