import UploadView from './components/UploadView.jsx'

export default function App() {
  return (
    <div className="min-h-screen bg-slate-50">

      {/* ── Header ───────────────────────────────────────────────── */}
      <header className="bg-white border-b border-slate-200 shadow-sm">
        <div className="max-w-4xl mx-auto px-6 py-4">
          <h1 className="text-xl font-bold text-slate-800">OCR + Parsing Dokumen</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Upload PDF, DOCX, atau gambar — Docling baca, Qwen AI parse ke JSON
          </p>
        </div>
      </header>

      {/* ── Main ─────────────────────────────────────────────────── */}
      <main className="max-w-4xl mx-auto px-6 py-6">
        <UploadView />
      </main>
    </div>
  )
}
