// Metadata setiap langkah preprocessing (sesuai dengan nama file di output/)
const STEPS = [
  {
    filename: 'invoice_original.png',
    label:    'Original',
    step:     '0',
    desc:     'Gambar faktur asli sebelum preprocessing. Font 13px, RGB.',
    why:      null, // Tidak ada "why" untuk original
  },
  {
    filename: 'step_01_upscale.png',
    label:    'Upscale 2x',
    step:     '1',
    desc:     'Gambar diperbesar 2x dengan interpolasi Lanczos.',
    why:      'Tesseract butuh font minimal ~20px. Upscale mengubah 13px → 26px.',
  },
  {
    filename: 'step_02_grayscale.png',
    label:    'Grayscale',
    step:     '2',
    desc:     'Konversi dari RGB (3 channel) ke skala abu-abu (1 channel).',
    why:      'Warna tidak membawa informasi teks, mengurangi kompleksitas proses.',
  },
  {
    filename: 'step_03_contrast.png',
    label:    'Contrast',
    step:     '3',
    desc:     'Kontras ditingkatkan 1.6x dengan convertScaleAbs.',
    why:      'Memperkuat perbedaan antara tinta gelap dan kertas putih.',
  },
  {
    filename: 'step_04_denoise.png',
    label:    'Denoise',
    step:     '4',
    desc:     'Gaussian blur ringan (radius 0.8) untuk menghaluskan noise.',
    why:      'Noise kecil bisa membuat threshold Otsu salah hitung. Blur membersihkannya.',
  },
  {
    filename: 'step_05_binarize.png',
    label:    'Binarize (Otsu)',
    step:     '5',
    desc:     'Threshold Otsu: setiap piksel jadi hitam (0) atau putih (255).',
    why:      'Tesseract bekerja paling baik pada gambar hitam-putih murni.',
  },
  {
    filename: 'step_06_sharpen.png',
    label:    'Sharpen',
    step:     '6',
    desc:     'Kernel unsharp mask untuk mempertegas tepi karakter.',
    why:      'Gaussian blur di step 4 sedikit memperlunak tepi. Sharpen memulihkannya.',
  },
]

export default function PreprocessSteps() {
  return (
    <div>
      <div className="mb-4">
        <h2 className="text-lg font-bold text-slate-800">Pipeline Preprocessing (6 Langkah)</h2>
        <p className="text-sm text-slate-500 mt-1">
          Setiap langkah meningkatkan kualitas gambar sebelum diberikan ke Tesseract OCR.
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
        {STEPS.map(step => (
          <StepCard key={step.filename} step={step} />
        ))}
      </div>
    </div>
  )
}

function StepCard({ step }) {
  return (
    <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden flex flex-col">
      {/* Badge + judul */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-slate-100 bg-slate-50">
        <span className={`
          inline-flex items-center justify-center w-6 h-6 rounded-full text-xs font-bold
          ${step.step === '0'
            ? 'bg-slate-200 text-slate-600'
            : 'bg-blue-600 text-white'}
        `}>
          {step.step}
        </span>
        <span className="font-semibold text-slate-700 text-sm">{step.label}</span>
      </div>

      {/* Gambar */}
      <div className="bg-slate-100 flex items-center justify-center overflow-hidden">
        <img
          src={`/images/${step.filename}`}
          alt={step.label}
          className="w-full object-contain max-h-48"
          onError={e => { e.target.style.display = 'none' }}
        />
      </div>

      {/* Deskripsi */}
      <div className="px-3 py-3 flex flex-col gap-2 flex-1">
        <p className="text-xs text-slate-600">{step.desc}</p>
        {step.why && (
          <div className="bg-amber-50 border border-amber-100 rounded px-2 py-1.5">
            <p className="text-xs text-amber-700">
              <span className="font-semibold">Kenapa?</span> {step.why}
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
