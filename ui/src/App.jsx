import UploadView from './components/UploadView.jsx'

export default function App() {
  return (
    <div className="min-h-screen bg-slate-50">
      <header className="bg-white border-b border-slate-200 shadow-sm">
        <div className="max-w-4xl mx-auto px-6 py-4">
          <h1 className="text-xl font-bold text-slate-800">OCR + Parsing Dokumen</h1>
          <p className="text-sm text-slate-500 mt-0.5">Upload dokumen → Docling OCR → Qwen AI → JSON</p>
        </div>
      </header>
      <main className="max-w-4xl mx-auto px-6 py-6">
        <UploadView />
      </main>
    </div>
  )
}
