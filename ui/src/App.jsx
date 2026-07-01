import { useState } from 'react'
import UploadView from './components/UploadView.jsx'
import DocumentsView from './components/DocumentsView.jsx'

export default function App() {
  const [view, setView] = useState('upload')   // 'upload' | 'documents'

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="bg-white border-b border-slate-200 shadow-sm">
        <div className="max-w-5xl mx-auto px-6 py-4 flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-slate-800">OCR + Parsing Dokumen</h1>
            <p className="text-sm text-slate-500 mt-0.5">Upload dokumen → Docling OCR → Qwen AI → JSON</p>
          </div>
          <nav className="flex rounded-lg border border-slate-200 overflow-hidden text-sm">
            <button onClick={() => setView('upload')}
              className={`px-4 py-2 ${view === 'upload' ? 'bg-slate-800 text-white' : 'bg-white text-slate-600 hover:bg-slate-50'}`}>
              Upload
            </button>
            <button onClick={() => setView('documents')}
              className={`px-4 py-2 border-l border-slate-200 ${view === 'documents' ? 'bg-slate-800 text-white' : 'bg-white text-slate-600 hover:bg-slate-50'}`}>
              Dokumen
            </button>
          </nav>
        </div>
      </header>
      <main className="max-w-5xl mx-auto px-6 py-6">
        {view === 'upload' ? <UploadView /> : <DocumentsView />}
      </main>
    </div>
  )
}
