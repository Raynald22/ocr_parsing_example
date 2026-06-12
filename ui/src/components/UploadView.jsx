import { useState, useRef } from 'react'

const ACCEPTED = '.png,.jpg,.jpeg,.bmp,.tiff,.tif,.webp'
const MAX_MB   = 20

const rp = (v) => v != null ? 'Rp ' + Number(v).toLocaleString('id-ID') : null

export default function UploadView() {
  const [dragOver,    setDragOver]    = useState(false)
  const [processing,  setProcessing]  = useState(false)
  const [result,      setResult]      = useState(null)
  const [error,       setError]       = useState(null)
  const [step,        setStep]        = useState('')   // label langkah saat processing
  const inputRef = useRef(null)

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
    setStep('Mengunggah file…')

    const form = new FormData()
    form.append('file', file)

    try {
      setStep('Preprocessing gambar (6 langkah)…')
      const res  = await fetch('/api/upload', { method: 'POST', body: form })
      const data = await res.json()

      if (!res.ok) {
        setError(data.error || 'Terjadi kesalahan.')
        return
      }
      setStep('Selesai!')
      setResult(data)
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
          Upload gambar invoice atau faktur. Pipeline akan otomatis preprocessing,
          OCR, parsing, dan menghitung skor kualitas.
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
            <p className="text-xs text-slate-400">Mohon tunggu, OCR membutuhkan beberapa detik…</p>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-2 text-slate-400">
            <span className="text-4xl">📄</span>
            <p className="font-medium text-slate-600">
              Drag &amp; drop file di sini, atau klik untuk pilih
            </p>
            <p className="text-xs">PNG, JPG, JPEG, BMP, TIFF, WEBP — maks {MAX_MB} MB</p>
          </div>
        )}
      </div>

      {/* ── Error ──────────────────────────────────────────────────────── */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-xl px-4 py-3 text-sm text-red-700">
          <strong>Error:</strong> {error}
        </div>
      )}

      {/* ── Hasil ──────────────────────────────────────────────────────── */}
      {result && <UploadResult result={result} />}
    </div>
  )
}

// ── Komponen hasil ─────────────────────────────────────────────────────────

function UploadResult({ result }) {
  const { score, parsed_fields: pf, parsed_items, ocr_confidence,
          filename, elapsed_s, ocr_prep_text } = result

  return (
    <div className="flex flex-col gap-4">

      {/* Header file info */}
      <div className="flex items-center gap-3 text-sm text-slate-500">
        <span className="font-medium text-slate-700">{filename}</span>
        <span>•</span>
        <span>Diproses dalam {elapsed_s}s</span>
        <span>•</span>
        <span>OCR confidence: {ocr_confidence.toFixed(1)}%</span>
      </div>

      {/* Grid utama: gambar | parsed | skor */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">

        {/* Gambar yang diupload */}
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
          <div className="px-4 py-2.5 bg-slate-50 border-b border-slate-100">
            <p className="text-sm font-semibold text-slate-700">Gambar Upload</p>
          </div>
          <div className="p-3">
            <img
              src={`/images/${result.image_url}`}
              alt="Uploaded document"
              className="w-full rounded border border-slate-200 object-contain max-h-72"
            />
          </div>
        </div>

        {/* Data yang diparsing */}
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm">
          <div className="px-4 py-2.5 bg-slate-50 border-b border-slate-100 flex items-center justify-between">
            <p className="text-sm font-semibold text-slate-700">Data Terparsing</p>
            <span className="text-xs text-slate-400">
              {score.fields_found}/{score.fields_total} field
            </span>
          </div>
          <div className="px-4 py-3 space-y-1.5 text-sm">
            <ParsedRow label="No. Faktur"  value={pf.nomor_faktur}   mono />
            <ParsedRow label="Tanggal"     value={pf.tanggal} />
            <ParsedRow label="Jatuh Tempo" value={pf.jatuh_tempo} />
            <ParsedRow label="Penjual"     value={pf.nama_penjual} />
            <ParsedRow label="NPWP Penjual" value={pf.npwp_penjual} mono />
            <ParsedRow label="Pembeli"     value={pf.nama_pembeli} />
            <ParsedRow label="NPWP Pembeli" value={pf.npwp_pembeli} mono />
            <ParsedRow label="Alamat"      value={pf.alamat_pembeli} />
            <div className="pt-1.5 border-t border-slate-100 mt-1.5" />
            <ParsedRow label="Subtotal"    value={rp(pf.subtotal)} mono />
            <ParsedRow label="PPN"         value={rp(pf.ppn)}      mono />
            <ParsedRow label="Total"       value={rp(pf.total)}    mono bold />
            {parsed_items.length > 0 && (
              <p className="text-xs text-slate-400 pt-1">
                + {parsed_items.length} baris item ditemukan
              </p>
            )}
          </div>
        </div>

        {/* Skor kualitas */}
        <ScoreCard score={score} />
      </div>

      {/* Preprocessing steps */}
      {result.prep_images?.length > 0 && (
        <PrepStepsRow images={result.prep_images} />
      )}

      {/* OCR teks mentah */}
      <details className="bg-white rounded-xl border border-slate-200 shadow-sm">
        <summary className="px-4 py-3 cursor-pointer text-sm font-semibold text-slate-700 select-none">
          Teks OCR Mentah (klik untuk lihat)
        </summary>
        <pre className="px-4 pb-4 text-xs font-mono text-slate-600 whitespace-pre-wrap leading-relaxed max-h-48 overflow-auto">
          {ocr_prep_text || '(kosong)'}
        </pre>
      </details>
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
