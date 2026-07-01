import { useState, useRef, useCallback } from 'react'
import { useJobStatus } from '../hooks/useJobStatus'


const ACCEPT_DOCUMENT = '.pdf,.docx,.doc,.png,.jpg,.jpeg,.bmp,.tiff,.tif,.webp'
const MAX_MB          = 20

const IMAGE_EXTS = new Set(['.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.tif', '.webp'])

const isImage = (file) => {
  if (!file?.name) return false
  return IMAGE_EXTS.has('.' + file.name.split('.').pop().toLowerCase())
}

const fileIcon = (name = '') => {
  const ext = name.split('.').pop().toLowerCase()
  if (ext === 'pdf')                                                    return '📕'
  if (['docx', 'doc'].includes(ext))                                  return '📘'
  if (['png','jpg','jpeg','bmp','tiff','tif','webp'].includes(ext))  return '🖼️'
  return '📄'
}


export default function UploadView() {
  const [dragOver, setDragOver] = useState(false)
  const [preview,  setPreview]  = useState(null)
  const [fileName, setFileName] = useState(null)
  const docInputRef   = useRef(null)

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
    if (docInputRef.current) docInputRef.current.value = ''
  }

  const onDrop     = (e) => { e.preventDefault(); setDragOver(false); handleFile(e.dataTransfer.files[0]) }
  const onDragOver = (e) => { e.preventDefault(); setDragOver(true) }
  const onDragLeave = ()  => setDragOver(false)

  return (
    <div className="flex flex-col gap-5">

      <input ref={docInputRef} type="file" accept={ACCEPT_DOCUMENT} className="hidden" onChange={e => handleFile(e.target.files[0])} />

      <div
        onDrop={onDrop}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        className={`
          relative border-2 border-dashed rounded-2xl select-none
          transition-all duration-200
          ${dragOver
            ? 'border-blue-400 bg-blue-50 scale-[1.01]'
            : 'border-slate-300 bg-white'
          }
          ${processing ? 'cursor-not-allowed' : ''}
        `}
      >
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
          <div className="flex flex-col items-center gap-4 py-10 px-6">
            <p className="text-sm text-slate-500">Drag &amp; drop file ke sini, atau pilih file:</p>
            <button
              onClick={() => docInputRef.current?.click()}
              className="flex items-center gap-2 px-5 py-3 rounded-xl border-2 border-blue-200 bg-blue-50 hover:bg-blue-100 hover:border-blue-300 transition-colors"
            >
              <span className="text-2xl">📕</span>
              <div className="text-left">
                <p className="text-sm font-semibold text-blue-800">PDF / Word / Gambar</p>
                <p className="text-xs text-blue-500">.pdf .docx .doc .png .jpg .tiff</p>
              </div>
            </button>
            <p className="text-xs text-slate-400">Maks {MAX_MB} MB</p>
          </div>
        )}
      </div>


      {error && (
        <div className="flex items-start gap-2 bg-red-50 border border-red-200 rounded-xl px-4 py-3 text-sm text-red-700">
          <span className="shrink-0 mt-0.5">⚠</span>
          <span className="flex-1">{error}</span>
          <button onClick={handleReset} className="text-red-400 hover:text-red-600 text-xs font-medium shrink-0">
            Coba lagi
          </button>
        </div>
      )}


      {status === 'completed' && result && (
        <DocResult result={result} localPreview={preview} onReset={handleReset} />
      )}
    </div>
  )
}


export function DocResult({ result, localPreview, onReset }) {
  const {
    document_type, confidence, needs_review,
    data, review, meta = {}, raw = {},
  } = result
  const { filename, elapsed_s, doc_confidence, ai_extraction, pipeline_steps = [] } = meta
  const { extracted_text, tables = [], key_values = {} } = raw

  const isStructured = document_type && document_type !== 'generic'
  const validation = review
    ? { confidence, needs_review, threshold: review.threshold, summary: review, issues: review.issues }
    : null

  const imgSrc = localPreview

  return (
    <div className="flex flex-col gap-4">


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


      {validation && <ValidationCard validation={validation} />}


      {pipeline_steps?.length > 0 && <PipelineSteps steps={pipeline_steps} />}


      {isStructured
        ? <StructuredPanel docType={document_type} data={data} tables={tables} />
        : <DocContentPanel keyValues={data ?? {}} tables={tables} aiExtraction={ai_extraction} />
      }


      {isStructured && Object.keys(key_values).length > 0 && (
        <details className="bg-white rounded-xl border border-slate-200 shadow-sm group">
          <summary className="px-4 py-3 cursor-pointer text-sm font-semibold text-slate-700 select-none flex items-center gap-2">
            <span className="text-slate-400 group-open:rotate-90 transition-transform inline-block">▶</span>
            Field Mentah (flat)
            <span className="font-normal text-slate-400 text-xs">({Object.keys(key_values).length} field)</span>
          </summary>
          <div className="border-t border-slate-100 overflow-auto max-h-72">
            <table className="w-full text-xs">
              <tbody>
                {Object.entries(key_values).map(([k, v], i) => (
                  <tr key={k} className={i % 2 === 0 ? 'bg-white' : 'bg-slate-50/60'}>
                    <td className="px-4 py-1.5 text-slate-500 font-medium align-top break-words w-2/5">{k}</td>
                    <td className="px-4 py-1.5 text-slate-800 font-mono align-top break-words">{String(v)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}


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


function ValidationCard({ validation }) {
  const { confidence, needs_review, threshold, summary, issues } = validation
  const ok = !needs_review
  const t = ok
    ? { border: 'border-green-200', bg: 'bg-green-50', text: 'text-green-700', bar: 'bg-green-500', badge: 'bg-green-200 text-green-800' }
    : { border: 'border-amber-300', bg: 'bg-amber-50', text: 'text-amber-700', bar: 'bg-amber-500', badge: 'bg-amber-200 text-amber-800' }

  const ordered = [...issues].sort((a, b) => (a.level === 'error' ? 0 : 1) - (b.level === 'error' ? 0 : 1))

  return (
    <div className={`rounded-2xl border shadow-sm p-4 ${t.border} ${t.bg}`}>
      <div className="flex items-center gap-4">
        <div className="shrink-0 text-center w-20">
          <p className={`text-4xl font-black tracking-tight ${t.text}`}>{confidence.toFixed(1)}%</p>
          <p className="text-[11px] text-slate-500">confidence</p>
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className={`text-xs font-bold px-3 py-1 rounded-full ${t.badge}`}>
              {ok ? `✓ AUTO-PASS (≥${threshold}%)` : `⚠ PERLU VERIFIKASI (<${threshold}%)`}
            </span>
            {summary.critical_errors > 0 && (
              <span className="text-xs font-bold text-red-600">{summary.critical_errors} critical</span>
            )}
          </div>
          <p className="text-xs text-slate-500 mt-1">
            {summary.errors} error · {summary.warnings} warning · {summary.fields_scored} field dinilai
          </p>
          <div className="mt-2 bg-white/70 rounded-full h-2 overflow-hidden">
            <div className={`h-2 rounded-full ${t.bar}`} style={{ width: Math.min(confidence, 100) + '%' }} />
          </div>
        </div>
      </div>

      {ordered.length > 0 && (
        <div className="mt-3 border-t border-slate-200/70 pt-3 flex flex-col gap-1 max-h-48 overflow-auto">
          {ordered.map((it, i) => (
            <div key={i} className="flex items-start gap-2 text-xs">
              <span className={it.level === 'error' ? 'text-red-500' : 'text-amber-500'}>
                {it.level === 'error' ? '✕' : '⚠'}
              </span>
              <span className="font-mono text-slate-500 shrink-0 break-all">{it.field}</span>
              <span className="text-slate-600 min-w-0">{it.message}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}


const DOC_TYPE_LABEL = {
  invoice:        'Invoice',
  packing_list:   'Packing List',
  bill_of_lading: 'Bill of Lading',
  generic:        'Dokumen',
}

const prettyKey = (k) => k.replace(/_/g, ' ')
const fmtValue  = (v) =>
  typeof v === 'number' ? v.toLocaleString('en-US') : String(v)

const isEmpty = (v) =>
  v == null || v === '' || v === '-' ||
  (Array.isArray(v) && v.length === 0) ||
  (typeof v === 'object' && !Array.isArray(v) && Object.values(v).every(isEmpty))


function StructuredPanel({ docType, data, tables }) {
  const records = Array.isArray(data) ? data : [data]

  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden flex flex-col h-full">
      <div className="px-4 py-2.5 bg-slate-50 border-b border-slate-100 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2">
          <p className="text-sm font-semibold text-slate-700">Data Terstruktur</p>
          <Badge color="violet">{DOC_TYPE_LABEL[docType] ?? docType}</Badge>
        </div>
        {records.length > 1 && (
          <span className="text-xs text-slate-400">{records.length} dokumen</span>
        )}
      </div>

      <div className="overflow-auto flex-1 flex flex-col gap-3 p-3">
        {records.map((rec, i) => (
          <RecordCard key={i} record={rec} index={records.length > 1 ? i + 1 : null} />
        ))}

        {tables.length > 0 && (
          <details className="rounded-lg border border-slate-200 group">
            <summary className="px-3 py-2 cursor-pointer text-xs font-semibold text-slate-500 uppercase tracking-wide select-none">
              Tabel mentah ({tables.length})
            </summary>
            <div className="px-3 pb-3">
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
          </details>
        )}
      </div>
    </div>
  )
}


function RecordCard({ record, index }) {
  const entries = Object.entries(record || {})
  const scalars = entries.filter(([, v]) => v == null || typeof v !== 'object')
  const objects = entries.filter(([, v]) => v && typeof v === 'object' && !Array.isArray(v))
  const arrays  = entries.filter(([, v]) => Array.isArray(v))

  return (
    <div className="rounded-lg border border-slate-200 overflow-hidden">
      {index != null && (
        <div className="px-3 py-1.5 bg-violet-50 border-b border-violet-100 text-xs font-semibold text-violet-700">
          Dokumen #{index}
        </div>
      )}

      <FieldGrid fields={scalars} />

      {objects.map(([name, obj]) => (
        isEmpty(obj) ? null : (
          <div key={name} className="border-t border-slate-100">
            <p className="px-3 pt-2 text-[11px] font-semibold text-slate-400 uppercase tracking-wide">{prettyKey(name)}</p>
            <FieldGrid fields={Object.entries(obj)} />
          </div>
        )
      ))}

      {arrays.map(([name, rows]) => (
        rows.length === 0 ? null : (
          <div key={name} className="border-t border-slate-100">
            <p className="px-3 pt-2 pb-1 text-[11px] font-semibold text-slate-400 uppercase tracking-wide">
              {prettyKey(name)} <span className="text-slate-300">({rows.length})</span>
            </p>
            <ItemsTable rows={rows} />
          </div>
        )
      ))}
    </div>
  )
}


function FieldGrid({ fields }) {
  const shown = fields.filter(([, v]) => !isEmpty(v))
  if (shown.length === 0) return null

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-4">
      {shown.map(([k, v]) => (
        <div key={k} className="flex gap-2 px-3 py-1.5 text-xs border-b border-slate-50 last:border-0 min-w-0">
          <span className="text-slate-400 shrink-0 w-32 truncate">{prettyKey(k)}</span>
          <span className="text-slate-800 font-medium break-words min-w-0">{fmtValue(v)}</span>
        </div>
      ))}
    </div>
  )
}


function ItemsTable({ rows }) {
  const cols = [...rows.reduce((set, r) => {
    Object.keys(r || {}).forEach(k => set.add(k))
    return set
  }, new Set())]

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs border-collapse">
        <thead>
          <tr className="bg-slate-50 text-slate-500">
            {cols.map(c => (
              <th key={c} className="text-left px-2 py-1.5 font-semibold uppercase tracking-wide whitespace-nowrap border-b border-slate-200">
                {prettyKey(c)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, ri) => (
            <tr key={ri} className={ri % 2 === 0 ? 'bg-white' : 'bg-slate-50/60'}>
              {cols.map(c => (
                <td key={c} className="px-2 py-1.5 text-slate-700 align-top whitespace-nowrap border-b border-slate-50">
                  {isEmpty(row[c]) ? <span className="text-slate-300">—</span> : fmtValue(row[c])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}


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
