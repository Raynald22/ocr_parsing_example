export default function OcrComparison({ ocrData }) {
  if (!ocrData) return null

  const rawWords  = ocrData.raw?.split(/\s+/).filter(Boolean).length  ?? 0
  const prepWords = ocrData.preprocessed?.split(/\s+/).filter(Boolean).length ?? 0

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h2 className="text-lg font-bold text-slate-800">Hasil OCR: Sebelum vs Sesudah Preprocessing</h2>
        <p className="text-sm text-slate-500 mt-1">
          Preprocessing meningkatkan akurasi OCR secara signifikan. Bandingkan kedua teks di bawah.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <TextPanel
          title="Tanpa Preprocessing"
          badge={`${rawWords} kata`}
          badgeColor="bg-red-100 text-red-700"
          text={ocrData.raw}
          note="Langsung dari gambar asli. Banyak error, kata terpotong."
        />
        <TextPanel
          title="Dengan Preprocessing"
          badge={`${prepWords} kata`}
          badgeColor="bg-green-100 text-green-700"
          text={ocrData.preprocessed}
          note="Dari gambar setelah 6 langkah preprocessing. Akurasi jauh lebih tinggi."
        />
      </div>

      {/* Insight */}
      <div className="bg-blue-50 border border-blue-100 rounded-xl px-5 py-4">
        <p className="text-sm font-semibold text-blue-800 mb-1">Insight Pembelajaran</p>
        <p className="text-sm text-blue-700">
          Perhatikan perbedaan jumlah kata: teks kiri cenderung memiliki kata yang lebih sedikit atau
          berantakan karena Tesseract kesulitan membaca gambar resolusi rendah. Teks kanan,
          setelah preprocessing, lebih lengkap dan terstruktur — hasilnya kemudian di-parse
          oleh modul <code className="bg-blue-100 px-1 rounded">parser.py</code>.
        </p>
      </div>
    </div>
  )
}

function TextPanel({ title, badge, badgeColor, text, note }) {
  return (
    <div className="bg-white rounded-xl shadow-sm border border-slate-200 flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-100 bg-slate-50">
        <h3 className="font-semibold text-slate-700 text-sm">{title}</h3>
        <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${badgeColor}`}>
          {badge}
        </span>
      </div>

      {/* Teks */}
      <pre className="flex-1 p-4 text-xs font-mono text-slate-700 overflow-auto max-h-96
                      whitespace-pre-wrap leading-relaxed bg-slate-50">
        {text || '(kosong)'}
      </pre>

      {/* Note */}
      <div className="px-4 py-2 border-t border-slate-100">
        <p className="text-xs text-slate-400 italic">{note}</p>
      </div>
    </div>
  )
}
