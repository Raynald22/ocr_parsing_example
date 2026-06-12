// Warna baris berdasarkan status field
function rowColor(field) {
  if (field.exact_match) return 'bg-green-50'
  if (field.cer < 0.2)   return 'bg-yellow-50'
  return 'bg-red-50'
}

function statusBadge(field) {
  if (field.exact_match) return <Badge color="green">EXACT</Badge>
  if (field.cer < 0.2)   return <Badge color="yellow">~{((1 - field.cer) * 100).toFixed(0)}%</Badge>
  return <Badge color="red">MISS</Badge>
}

export default function AccuracyScore({ results }) {
  if (!results) return null

  const accuracy      = results.char_accuracy ?? 0
  const exactRate     = results.exact_match_rate ?? 0
  const itemAccuracy  = results.item_accuracy ?? 0
  const passes        = results.passes_threshold
  const target        = results.target ?? 0.95

  const pct = (v) => (v * 100).toFixed(1) + '%'

  return (
    <div className="flex flex-col gap-5">

      {/* ── Hero: angka besar ─────────────────────────────────── */}
      <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6 flex flex-col items-center gap-3">
        <div className={`text-6xl font-extrabold ${passes ? 'text-green-600' : 'text-red-600'}`}>
          {pct(accuracy)}
        </div>
        <div className={`text-sm font-bold px-4 py-1.5 rounded-full ${
          passes ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
        }`}>
          {passes ? 'LULUS' : 'TIDAK LULUS'} — target {pct(target)}
        </div>

        {/* Progress bar */}
        <div className="w-full max-w-md bg-slate-100 rounded-full h-3 overflow-hidden">
          <div
            className={`h-3 rounded-full transition-all ${passes ? 'bg-green-500' : 'bg-red-500'}`}
            style={{ width: pct(Math.min(accuracy, 1)) }}
          />
        </div>
        <p className="text-xs text-slate-400">Karakter Accuracy (1 - CER)</p>
      </div>

      {/* ── Stat cards ──────────────────────────────────────────── */}
      <div className="grid grid-cols-3 gap-4">
        <StatCard
          label="Char Accuracy"
          value={pct(accuracy)}
          sub="1 - rata-rata CER"
          color="blue"
        />
        <StatCard
          label="Exact Match Rate"
          value={pct(exactRate)}
          sub={`${results.fields?.filter(f => f.exact_match).length ?? 0} / ${results.fields?.length ?? 0} field tepat`}
          color="indigo"
        />
        <StatCard
          label="Item Accuracy"
          value={pct(itemAccuracy)}
          sub="baris tabel terparsing"
          color="violet"
        />
      </div>

      {/* ── Tabel per-field ─────────────────────────────────────── */}
      <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
        <div className="px-5 py-3 border-b border-slate-100 bg-slate-50">
          <h3 className="font-semibold text-slate-700 text-sm">Detail per Field</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-slate-500 uppercase border-b border-slate-100 bg-slate-50">
                <th className="text-left px-4 py-2 font-medium">Field</th>
                <th className="text-left px-4 py-2 font-medium">Expected</th>
                <th className="text-left px-4 py-2 font-medium">Got (OCR)</th>
                <th className="text-right px-4 py-2 font-medium">CER</th>
                <th className="text-center px-4 py-2 font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {results.fields?.map(field => (
                <tr key={field.field} className={`border-b border-slate-100 ${rowColor(field)}`}>
                  <td className="px-4 py-2 font-mono text-xs text-slate-600">{field.field}</td>
                  <td className="px-4 py-2 text-slate-700 max-w-[200px] truncate" title={field.expected}>
                    {field.expected}
                  </td>
                  <td className="px-4 py-2 text-slate-700 max-w-[200px] truncate" title={field.got}>
                    {field.got || <span className="text-slate-400 italic">tidak ditemukan</span>}
                  </td>
                  <td className="px-4 py-2 text-right font-mono text-slate-600">
                    {field.cer.toFixed(3)}
                  </td>
                  <td className="px-4 py-2 text-center">
                    {statusBadge(field)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Penjelasan CER */}
        <div className="px-5 py-3 bg-slate-50 border-t border-slate-100">
          <p className="text-xs text-slate-500">
            <strong>CER (Character Error Rate)</strong> = jarak Levenshtein / panjang referensi.
            0.000 = sempurna, 1.000 = semua karakter salah.
            &nbsp;<span className="inline-block w-3 h-3 bg-green-200 rounded-sm align-middle" /> Exact &nbsp;
            <span className="inline-block w-3 h-3 bg-yellow-200 rounded-sm align-middle" /> Dekat &nbsp;
            <span className="inline-block w-3 h-3 bg-red-200 rounded-sm align-middle" /> Miss
          </p>
        </div>
      </div>

    </div>
  )
}

// ── Helpers ─────────────────────────────────────────────────────────────────

function StatCard({ label, value, sub, color }) {
  const colors = {
    blue:   'border-blue-200   bg-blue-50   text-blue-700',
    indigo: 'border-indigo-200 bg-indigo-50 text-indigo-700',
    violet: 'border-violet-200 bg-violet-50 text-violet-700',
  }
  return (
    <div className={`rounded-xl border p-4 ${colors[color]}`}>
      <p className="text-xs font-medium opacity-70 mb-1">{label}</p>
      <p className="text-2xl font-bold">{value}</p>
      <p className="text-xs opacity-60 mt-1">{sub}</p>
    </div>
  )
}

function Badge({ color, children }) {
  const colors = {
    green:  'bg-green-100 text-green-700',
    yellow: 'bg-yellow-100 text-yellow-700',
    red:    'bg-red-100 text-red-700',
  }
  return (
    <span className={`inline-block text-xs font-semibold px-2 py-0.5 rounded-full ${colors[color]}`}>
      {children}
    </span>
  )
}
