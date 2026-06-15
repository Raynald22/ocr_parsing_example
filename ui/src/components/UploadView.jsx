import { useState, useRef } from 'react'

const ACCEPTED_IMAGE = '.png,.jpg,.jpeg,.bmp,.tiff,.tif,.webp'
const ACCEPTED_DOC   = '.pdf,.docx'
const ACCEPTED_CSV   = '.csv'
const ACCEPTED       = ACCEPTED_IMAGE + ',' + ACCEPTED_DOC + ',' + ACCEPTED_CSV
const MAX_MB         = 20

const isCsv = (file) => file?.name?.toLowerCase().endsWith('.csv')

const rp = (v) => v != null ? 'Rp ' + Number(v).toLocaleString('id-ID') : null

export default function UploadView() {
  const [dragOver,    setDragOver]    = useState(false)
  const [processing,  setProcessing]  = useState(false)
  const [result,      setResult]      = useState(null)   // {type:'image'|'csv', data:{...}}
  const [error,       setError]       = useState(null)
  const [step,        setStep]        = useState('')
  const [csvFile,     setCsvFile]     = useState(null)   // ground truth CSV opsional (untuk gambar)
  const inputRef    = useRef(null)
  const csvInputRef = useRef(null)

  // ── Upload handler ─────────────────────────────────────────────────────

  const handleFile = async (file) => {
    if (!file) return

    if (file.size > MAX_MB * 1024 * 1024) {
      setError(`File terlalu besar. Maksimum ${MAX_MB} MB.`)
      return
    }

    setError(null)
    setResult(null)
    setProcessing(true)

    const form = new FormData()
    form.append('file', file)

    try {
      if (isCsv(file)) {
        // ── Alur CSV-only: parse langsung tanpa OCR ──────────────────
        setStep('Membaca dan parsing CSV…')
        const res  = await fetch('/api/parse-csv', { method: 'POST', body: form })
        const data = await res.json()
        if (!res.ok) { setError(data.error || 'Gagal memproses CSV.'); return }
        setResult({ type: 'csv', data })
      } else {
        // ── Alur gambar: OCR + parse + score ─────────────────────────
        if (csvFile) form.append('csv', csvFile)
        setStep('Memproses dengan Docling…')
        const res  = await fetch('/api/upload', { method: 'POST', body: form })
        const data = await res.json()
        if (!res.ok) { setError(data.error || 'Terjadi kesalahan.'); return }
        setResult({ type: 'image', data })
      }
      setStep('Selesai!')
    } catch (e) {
      setError('Tidak bisa terhubung ke server. Pastikan python api.py sedang berjalan.')
    } finally {
      setProcessing(false)
      setStep('')
    }
  }

  // ── Drag & drop events ─────────────────────────────────────────────────

  const onDrop = (e) => {
    e.preventDefault()
    setDragOver(false)
    const file = e.dataTransfer.files[0]
    if (file) handleFile(file)
  }

  const onDragOver = (e) => { e.preventDefault(); setDragOver(true) }
  const onDragLeave = ()  => setDragOver(false)

  // ── Render ─────────────────────────────────────────────────────────────

  return (
    <div className="flex flex-col gap-5">

      <div>
        <h2 className="text-lg font-bold text-slate-800">Upload Dokumen</h2>
        <p className="text-sm text-slate-500 mt-1">
          Upload dokumen atau gambar. Docling akan membaca isi dokumen secara akurat
          dan mengekstrak konten yang ditemukan — teks, tabel, dan pasangan kunci:nilai.
        </p>
      </div>

      {/* ── Drop Zone ──────────────────────────────────────────────────── */}
      <div
        onDrop={onDrop}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onClick={() => !processing && inputRef.current?.click()}
        className={`
          border-2 border-dashed rounded-xl p-10 text-center cursor-pointer
          transition-colors select-none
          ${dragOver
            ? 'border-blue-400 bg-blue-50'
            : 'border-slate-300 bg-white hover:border-blue-300 hover:bg-slate-50'
          }
          ${processing ? 'cursor-not-allowed opacity-60' : ''}
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
          <div className="flex flex-col items-center gap-3">
            <svg className="animate-spin h-10 w-10 text-blue-500" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z"/>
            </svg>
            <p className="text-blue-600 font-medium">{step}</p>
            <p className="text-xs text-slate-400">Mohon tunggu, Docling membutuhkan beberapa detik…</p>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-2 text-slate-400">
            <span className="text-4xl">📄</span>
            <p className="font-medium text-slate-600">
              Drag &amp; drop file di sini, atau klik untuk pilih
            </p>
            <p className="text-xs">Dokumen: <strong>PDF, DOCX</strong></p>
            <p className="text-xs">Gambar: PNG, JPG, JPEG, BMP, TIFF, WEBP</p>
            <p className="text-xs text-slate-400">CSV (format field,value) untuk parse langsung</p>
            <p className="text-xs text-slate-300">maks {MAX_MB} MB</p>
          </div>
        )}
      </div>

      {/* ── Ground Truth CSV (opsional) ────────────────────────────────── */}
      <div className="bg-white border border-slate-200 rounded-xl px-4 py-3">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-sm font-semibold text-slate-700">Ground Truth CSV <span className="font-normal text-slate-400">(opsional)</span></p>
            <p className="text-xs text-slate-500 mt-0.5">
              Upload CSV berisi nilai field yang diketahui → skor CER yang akurat (bukan quality score)
            </p>
          </div>
          <a
            href="/api/csv-template"
            download
            className="shrink-0 text-xs text-blue-600 hover:underline whitespace-nowrap mt-0.5"
          >
            Download Template ↓
          </a>
        </div>

        <div className="flex items-center gap-3 mt-2.5">
          <input
            ref={csvInputRef}
            type="file"
            accept=".csv"
            className="hidden"
            onChange={e => setCsvFile(e.target.files[0] || null)}
          />
          <button
            onClick={() => csvInputRef.current?.click()}
            disabled={processing}
            className="text-xs px-3 py-1.5 border border-slate-300 rounded hover:bg-slate-50 text-slate-600 disabled:opacity-50"
          >
            Pilih CSV
          </button>
          {csvFile ? (
            <div className="flex items-center gap-1.5 text-xs text-slate-600">
              <span className="font-medium">{csvFile.name}</span>
              <button
                onClick={() => { setCsvFile(null); if (csvInputRef.current) csvInputRef.current.value = '' }}
                className="text-slate-400 hover:text-red-500 leading-none"
                title="Hapus"
              >✕</button>
            </div>
          ) : (
            <span className="text-xs text-slate-400">Belum ada file dipilih</span>
          )}
        </div>
      </div>

      {/* ── Error ──────────────────────────────────────────────────────── */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-xl px-4 py-3 text-sm text-red-700">
          <strong>Error:</strong> {error}
        </div>
      )}

      {/* ── Hasil ──────────────────────────────────────────────────────── */}
      {result?.type === 'image' && <UploadResult result={result.data} />}
      {result?.type === 'csv'   && <CsvResult   result={result.data} />}
    </div>
  )
}

// ── Komponen hasil ─────────────────────────────────────────────────────────

function UploadResult({ result }) {
  const { cer_score, filename, elapsed_s,
          // DoclingResult fields (baru — fleksibel)
          doc_confidence, extracted_text, file_url,
          tables, key_values, tables_found, kv_found, passes, ai_extraction,
          // UploadResult fields (Tesseract legacy, compat)
          ocr_confidence, ocr_prep_text, prep_images } = result

  const confidence = doc_confidence ?? ocr_confidence
  const text       = extracted_text ?? ocr_prep_text

  return (
    <div className="flex flex-col gap-4">

      {/* Header file info */}
      <div className="flex items-center gap-3 text-sm text-slate-500 flex-wrap">
        <span className="font-medium text-slate-700">{filename}</span>
        <span>•</span>
        <span className="text-blue-600 font-medium">Docling</span>
        {ai_extraction && (
          <>
            <span>•</span>
            <span className="bg-violet-100 text-violet-700 font-semibold text-xs px-2 py-0.5 rounded-full">
              Qwen AI
            </span>
          </>
        )}
        <span>•</span>
        <span>{elapsed_s}s</span>
        {confidence != null && (
          <>
            <span>•</span>
            <span>Confidence: {typeof confidence === 'number' ? confidence.toFixed(1) : confidence}%</span>
          </>
        )}
        {cer_score && (
          <>
            <span>•</span>
            <span className="text-green-700 font-medium">CER scoring aktif</span>
          </>
        )}
      </div>

      {/* Grid utama: dokumen | konten | skor */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">

        {/* Gambar (hanya untuk file gambar) atau icon dokumen (PDF/DOCX) */}
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
          <div className="px-4 py-2.5 bg-slate-50 border-b border-slate-100">
            <p className="text-sm font-semibold text-slate-700">Dokumen</p>
          </div>
          <div className="p-3 flex items-center justify-center min-h-32">
            {file_url ? (
              <img
                src={`/images/${file_url}`}
                alt="Uploaded document"
                className="w-full rounded border border-slate-200 object-contain max-h-72"
              />
            ) : (
              <div className="text-center text-slate-400">
                <div className="text-5xl mb-2">📄</div>
                <p className="text-xs">{filename}</p>
                <p className="text-xs text-slate-300 mt-1">PDF / DOCX</p>
              </div>
            )}
          </div>
        </div>

        {/* Konten yang ditemukan Docling (dinamis, tidak fixed schema) */}
        <DocContentPanel keyValues={key_values ?? {}} tables={tables ?? []} aiExtraction={ai_extraction} />

        {/* Skor */}
        {cer_score
          ? <CerScoreCard cerScore={cer_score} />
          : <DocScoreCard
              confidence={confidence}
              passes={passes}
              kvFound={kv_found}
              tablesFound={tables_found}
            />
        }
      </div>

      {/* Preprocessing steps — hanya tampil jika ada (Tesseract legacy) */}
      {prep_images?.length > 0 && <PrepStepsRow images={prep_images} />}

      {/* Teks terekstrak */}
      {text && (
        <details className="bg-white rounded-xl border border-slate-200 shadow-sm">
          <summary className="px-4 py-3 cursor-pointer text-sm font-semibold text-slate-700 select-none">
            Teks Terekstrak (klik untuk lihat)
          </summary>
          <pre className="px-4 pb-4 text-xs font-mono text-slate-600 whitespace-pre-wrap leading-relaxed max-h-64 overflow-auto">
            {text}
          </pre>
        </details>
      )}
    </div>
  )
}

// ── Panel konten dinamis dari Docling ─────────────────────────────────────────

function DocContentPanel({ keyValues, tables, aiExtraction }) {
  const kvEntries = Object.entries(keyValues)
  const hasKv     = kvEntries.length > 0
  const hasTables = tables.length > 0

  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
      <div className="px-4 py-2.5 bg-slate-50 border-b border-slate-100 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <p className="text-sm font-semibold text-slate-700">Konten Ditemukan</p>
          {aiExtraction
            ? <span className="text-xs bg-violet-100 text-violet-700 px-1.5 py-0.5 rounded font-medium">Qwen AI</span>
            : <span className="text-xs bg-slate-100 text-slate-500 px-1.5 py-0.5 rounded">regex</span>
          }
        </div>
        <span className="text-xs text-slate-400">
          {kvEntries.length} kunci · {tables.length} tabel
        </span>
      </div>
      <div className="px-4 py-3 overflow-auto max-h-80">
        {hasKv && (
          <div className="space-y-1.5 mb-3">
            {kvEntries.slice(0, 20).map(([k, v]) => (
              <div key={k} className="flex justify-between gap-3">
                <span className="text-slate-500 shrink-0 text-xs">{k}</span>
                <span className="text-slate-700 text-xs text-right truncate max-w-[60%]">{v}</span>
              </div>
            ))}
            {kvEntries.length > 20 && (
              <p className="text-xs text-slate-400">+{kvEntries.length - 20} lainnya…</p>
            )}
          </div>
        )}
        {hasTables && (
          <div className={hasKv ? 'border-t border-slate-100 pt-3' : ''}>
            {tables.map((tbl, ti) => (
              <div key={ti} className="mb-3">
                <p className="text-xs font-medium text-slate-500 mb-1">Tabel {ti + 1}</p>
                <div className="overflow-auto">
                  <table className="text-xs border-collapse w-full">
                    <tbody>
                      {tbl.slice(0, 8).map((row, ri) => (
                        <tr key={ri} className={ri === 0 ? 'bg-slate-50 font-medium' : ''}>
                          {row.map((cell, ci) => (
                            <td key={ci} className="border border-slate-200 px-1.5 py-0.5 truncate max-w-[120px]">
                              {cell}
                            </td>
                          ))}
                        </tr>
                      ))}
                      {tbl.length > 8 && (
                        <tr>
                          <td colSpan={tbl[0]?.length || 1} className="text-center text-slate-400 py-1">
                            +{tbl.length - 8} baris…
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            ))}
          </div>
        )}
        {!hasKv && !hasTables && (
          <p className="text-sm text-slate-400 text-center py-6">
            Tidak ada konten terstruktur yang ditemukan.
            Lihat teks terekstrak di bawah.
          </p>
        )}
      </div>
    </div>
  )
}

// ── Skor kualitas Docling (berbasis confidence, bukan field count) ─────────────

function DocScoreCard({ confidence, passes, kvFound, tablesFound }) {
  const confStr = confidence != null ? confidence.toFixed(1) + '%' : '—'

  return (
    <div className={`rounded-xl border shadow-sm flex flex-col ${
      passes ? 'border-green-200 bg-green-50' : 'border-amber-200 bg-amber-50'
    }`}>
      <div className={`px-4 py-2.5 border-b font-semibold text-sm ${
        passes ? 'border-green-200 text-green-800' : 'border-amber-200 text-amber-800'
      }`}>
        Skor Kualitas
      </div>

      <div className="px-4 py-4 flex flex-col gap-4 flex-1">
        {/* Angka besar */}
        <div className="text-center">
          <p className={`text-4xl font-extrabold ${passes ? 'text-green-700' : 'text-amber-700'}`}>
            {confStr}
          </p>
          <p className="text-xs text-slate-500 mt-1">Docling Confidence</p>
          <span className={`text-xs font-bold px-3 py-1 rounded-full mt-2 inline-block ${
            passes ? 'bg-green-200 text-green-800' : 'bg-amber-200 text-amber-800'
          }`}>
            {passes ? 'LULUS (≥95%)' : 'PERLU PERBAIKAN (<95%)'}
          </span>
        </div>

        {/* Progress bar */}
        {confidence != null && (
          <div className="bg-white rounded-full h-2.5 overflow-hidden">
            <div
              className={`h-2.5 rounded-full ${passes ? 'bg-green-500' : 'bg-amber-500'}`}
              style={{ width: Math.min(confidence, 100) + '%' }}
            />
          </div>
        )}

        {/* Info konten yang diekstrak */}
        <div className="bg-white rounded-lg px-3 py-2 text-xs text-slate-600 border border-slate-100 space-y-1">
          <div className="flex justify-between">
            <span>Pasangan kunci:nilai</span>
            <span className="font-semibold">{kvFound ?? 0}</span>
          </div>
          <div className="flex justify-between">
            <span>Tabel ditemukan</span>
            <span className="font-semibold">{tablesFound ?? 0}</span>
          </div>
        </div>

        {!passes && (
          <div className="bg-white rounded-lg px-3 py-2 text-xs text-amber-700 border border-amber-200">
            <strong>Tips:</strong> Pastikan dokumen berkualitas baik.
            Untuk PDF: gunakan PDF teks (bukan scan). Untuk gambar: resolusi ≥ 300 DPI.
          </div>
        )}
      </div>
    </div>
  )
}

function ScoreCard({ score }) {
  const pct     = (v) => (v * 100).toFixed(1) + '%'
  const passes  = score.passes
  const overall = score.overall

  return (
    <div className={`rounded-xl border shadow-sm flex flex-col ${
      passes ? 'border-green-200 bg-green-50' : 'border-amber-200 bg-amber-50'
    }`}>
      {/* Header */}
      <div className={`px-4 py-2.5 border-b font-semibold text-sm ${
        passes ? 'border-green-200 text-green-800' : 'border-amber-200 text-amber-800'
      }`}>
        Skor Kualitas
      </div>

      <div className="px-4 py-4 flex flex-col gap-4 flex-1">
        {/* Angka besar */}
        <div className="text-center">
          <p className={`text-4xl font-extrabold ${passes ? 'text-green-700' : 'text-amber-700'}`}>
            {pct(overall)}
          </p>
          <span className={`text-xs font-bold px-3 py-1 rounded-full mt-2 inline-block ${
            passes ? 'bg-green-200 text-green-800' : 'bg-amber-200 text-amber-800'
          }`}>
            {passes ? 'LULUS (≥95%)' : 'PERLU PERBAIKAN (<95%)'}
          </span>
        </div>

        {/* Progress bar */}
        <div className="bg-white rounded-full h-2.5 overflow-hidden">
          <div
            className={`h-2.5 rounded-full ${passes ? 'bg-green-500' : 'bg-amber-500'}`}
            style={{ width: pct(Math.min(overall, 1)) }}
          />
        </div>

        {/* Breakdown komponen */}
        <div className="space-y-2 text-sm">
          <ScoreRow
            label="OCR Confidence"
            raw={score.ocr_confidence.toFixed(1) + '%'}
            norm={pct(score.ocr_confidence_norm)}
            weight="50%"
          />
          <ScoreRow
            label="Field Completeness"
            raw={`${score.fields_found}/${score.fields_total}`}
            norm={pct(score.field_completeness)}
            weight="35%"
          />
          <ScoreRow
            label="Math Consistency"
            raw={score.math_consistent === true ? 'OK' : score.math_consistent === false ? 'SALAH' : 'N/A'}
            norm={pct(score.math_score)}
            weight="15%"
          />
        </div>

        {/* Tips jika gagal */}
        {!passes && (
          <div className="bg-white rounded-lg px-3 py-2 text-xs text-amber-700 border border-amber-200 space-y-1.5">
            <p><strong>Tips kualitas gambar:</strong> Pastikan gambar cukup terang,
            tidak buram, dan teks terbaca jelas. Foto tegak lurus tanpa bayangan.</p>
            <p><strong>Tips bahasa Indonesia:</strong> Jika banyak field tidak ditemukan,
            install tessdata bahasa Indonesia:
            download <code className="bg-amber-100 px-1 rounded">ind.traineddata</code> dari{' '}
            <span className="underline">github.com/tesseract-ocr/tessdata</span>{' '}
            dan copy ke <code className="bg-amber-100 px-1 rounded">C:\Program Files\Tesseract-OCR\tessdata\</code>
            </p>
          </div>
        )}
      </div>
    </div>
  )
}

function ScoreRow({ label, raw, norm, weight }) {
  return (
    <div className="flex items-center justify-between gap-2 text-xs">
      <span className="text-slate-600 shrink-0">{label} <span className="text-slate-400">({weight})</span></span>
      <span className="text-slate-500">{raw}</span>
      <span className="font-mono font-semibold text-slate-700">{norm}</span>
    </div>
  )
}

function PrepStepsRow({ images }) {
  const LABELS = {
    upscale:   'Upscale 2x',
    grayscale: 'Grayscale',
    contrast:  'Contrast',
    denoise:   'Denoise',
    binarize:  'Binarize',
    sharpen:   'Sharpen',
  }
  return (
    <div>
      <p className="text-sm font-semibold text-slate-700 mb-2">Langkah Preprocessing</p>
      <div className="grid grid-cols-3 sm:grid-cols-6 gap-2">
        {images.map((name, i) => {
          const key   = name.replace(/^upload_step_\d+_/, '').replace('.png', '')
          const label = LABELS[key] || key
          return (
            <div key={name} className="bg-white border border-slate-200 rounded-lg overflow-hidden text-center">
              <img
                src={`/images/${name}`}
                alt={label}
                className="w-full object-contain max-h-24 bg-slate-100"
                onError={e => { e.target.style.display = 'none' }}
              />
              <p className="text-xs text-slate-500 py-1 px-1 truncate">
                <span className="font-medium text-blue-600">{i+1}.</span> {label}
              </p>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ── Hasil parse CSV-only (tanpa OCR) ──────────────────────────────────────

function CsvResult({ result }) {
  const { filename, fields, fields_found, fields_total, math_ok } = result

  const LABELS = {
    nomor_faktur:   'No. Faktur',
    tanggal:        'Tanggal',
    jatuh_tempo:    'Jatuh Tempo',
    nama_penjual:   'Penjual',
    npwp_penjual:   'NPWP Penjual',
    nama_pembeli:   'Pembeli',
    npwp_pembeli:   'NPWP Pembeli',
    alamat_pembeli: 'Alamat',
    subtotal:       'Subtotal',
    ppn:            'PPN',
    total:          'Total',
  }
  const MONO = new Set(['nomor_faktur','npwp_penjual','npwp_pembeli','subtotal','ppn','total'])

  const completeness = fields_found / fields_total
  const mathLabel    = math_ok === true ? 'Konsisten' : math_ok === false ? 'Tidak konsisten' : 'Tidak dapat dicek'
  const mathColor    = math_ok === true ? 'text-green-700' : math_ok === false ? 'text-red-600' : 'text-slate-400'

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2 text-sm text-slate-500">
        <span className="font-medium text-slate-700">{filename}</span>
        <span>•</span>
        <span className="text-blue-600 font-medium">Mode: Parse CSV (tanpa OCR)</span>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">

        {/* Tabel field */}
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm">
          <div className="px-4 py-2.5 bg-slate-50 border-b border-slate-100 flex items-center justify-between">
            <p className="text-sm font-semibold text-slate-700">Field Terparsing dari CSV</p>
            <span className="text-xs text-slate-400">{fields_found}/{fields_total} field</span>
          </div>
          <div className="px-4 py-3 space-y-1.5 text-sm">
            {Object.entries(LABELS).map(([key, label]) => {
              const val = fields[key]
              const formatted = (key === 'subtotal' || key === 'ppn' || key === 'total') && val != null
                ? rp(val)
                : val != null ? String(val) : null
              return (
                <ParsedRow
                  key={key}
                  label={label}
                  value={formatted}
                  mono={MONO.has(key)}
                  bold={key === 'total'}
                />
              )
            })}
          </div>
        </div>

        {/* Validasi */}
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm">
          <div className="px-4 py-2.5 bg-slate-50 border-b border-slate-100">
            <p className="text-sm font-semibold text-slate-700">Validasi</p>
          </div>
          <div className="px-4 py-4 flex flex-col gap-4">
            {/* Field completeness */}
            <div>
              <div className="flex justify-between text-sm mb-1">
                <span className="text-slate-600">Field terisi</span>
                <span className="font-semibold">{fields_found}/{fields_total}</span>
              </div>
              <div className="bg-slate-100 rounded-full h-2 overflow-hidden">
                <div
                  className="h-2 rounded-full bg-blue-500"
                  style={{ width: `${completeness * 100}%` }}
                />
              </div>
              <p className="text-xs text-slate-400 mt-1">{(completeness * 100).toFixed(0)}% field ada di CSV</p>
            </div>

            {/* Math check */}
            <div className="border-t border-slate-100 pt-3">
              <p className="text-sm text-slate-600 mb-1">Konsistensi angka</p>
              <p className="text-sm font-medium">
                Subtotal + PPN = Total:
                <span className={`ml-2 ${mathColor}`}>{mathLabel}</span>
              </p>
              {fields.subtotal != null && fields.ppn != null && (
                <p className="text-xs text-slate-400 mt-1 font-mono">
                  {rp(fields.subtotal)} + {rp(fields.ppn)} = {rp(fields.subtotal + fields.ppn)}
                  {fields.total != null && ` (tercatat: ${rp(fields.total)})`}
                </p>
              )}
            </div>

            {/* Catatan */}
            <div className="bg-blue-50 rounded-lg px-3 py-2 text-xs text-blue-700 border border-blue-100">
              <strong>Catatan:</strong> Ini adalah parsing data CSV langsung — tidak ada gambar atau OCR.
              Untuk skor akurasi OCR, upload gambar invoice di drop zone di atas.
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}


// ── CER Score Card (digunakan saat CSV ground truth diberikan) ─────────────

function CerScoreCard({ cerScore }) {
  const passes  = cerScore.passes_threshold
  const pct     = (v) => (v * 100).toFixed(1) + '%'

  const rowColor = (f) => {
    if (f.exact_match)   return 'bg-green-50 text-green-800'
    if (f.cer < 0.3)     return 'bg-amber-50 text-amber-800'
    return 'bg-red-50 text-red-700'
  }
  const rowStatus = (f) => {
    if (f.exact_match)  return 'EXACT'
    if (f.cer < 1.0)    return `~${((1 - f.cer) * 100).toFixed(0)}%`
    return 'MISS'
  }

  return (
    <div className={`rounded-xl border shadow-sm flex flex-col ${
      passes ? 'border-green-200 bg-green-50' : 'border-red-200 bg-red-50'
    }`}>
      <div className={`px-4 py-2.5 border-b font-semibold text-sm ${
        passes ? 'border-green-200 text-green-800' : 'border-red-200 text-red-800'
      }`}>
        Skor CER (dengan ground truth)
      </div>

      <div className="px-4 py-4 flex flex-col gap-3 flex-1">
        {/* Angka besar */}
        <div className="text-center">
          <p className={`text-4xl font-extrabold ${passes ? 'text-green-700' : 'text-red-700'}`}>
            {pct(cerScore.char_accuracy)}
          </p>
          <span className={`text-xs font-bold px-3 py-1 rounded-full mt-2 inline-block ${
            passes ? 'bg-green-200 text-green-800' : 'bg-red-200 text-red-800'
          }`}>
            {passes ? 'LULUS (>=95%)' : 'TIDAK LULUS (<95%)'}
          </span>
        </div>

        {/* Progress bar */}
        <div className="bg-white rounded-full h-2.5 overflow-hidden">
          <div
            className={`h-2.5 rounded-full ${passes ? 'bg-green-500' : 'bg-red-500'}`}
            style={{ width: pct(Math.min(cerScore.char_accuracy, 1)) }}
          />
        </div>

        {/* Per-field tabel */}
        <div className="bg-white rounded-lg overflow-hidden text-xs border border-slate-100">
          <div className="grid grid-cols-3 px-2 py-1 text-slate-400 font-medium border-b border-slate-100">
            <span>Field</span>
            <span className="truncate">Hasil OCR</span>
            <span className="text-right">Status</span>
          </div>
          {cerScore.fields.map(f => (
            <div key={f.field} className={`grid grid-cols-3 px-2 py-1 ${rowColor(f)}`}>
              <span className="font-medium truncate">{f.field}</span>
              <span className="truncate opacity-80">{f.got || '—'}</span>
              <span className="text-right font-bold">{rowStatus(f)}</span>
            </div>
          ))}
        </div>

        {/* Stats baris bawah */}
        <div className="flex justify-between text-xs text-slate-500">
          <span>Exact match: {pct(cerScore.exact_match_rate)}</span>
          <span>CER: {cerScore.overall_cer.toFixed(3)}</span>
        </div>
      </div>
    </div>
  )
}


function ParsedRow({ label, value, mono = false, bold = false }) {
  const missing = value == null
  return (
    <div className="flex justify-between gap-3">
      <span className="text-slate-500 shrink-0">{label}</span>
      <span className={`text-right ${mono ? 'font-mono text-xs' : ''} ${bold ? 'font-bold text-blue-700' : 'text-slate-700'} ${missing ? 'text-slate-300 italic' : ''}`}>
        {missing ? 'tidak ditemukan' : String(value)}
      </span>
    </div>
  )
}
