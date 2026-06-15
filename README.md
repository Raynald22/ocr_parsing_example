# OCR + Parsing — Dokumen Invoice

Contoh pembelajaran OCR dan parsing dokumen dengan Python.
Ada dua pipeline yang berjalan terpisah:

| Pipeline | Tab | Teknologi | Tujuan |
|----------|-----|-----------|--------|
| **Utama** | 1–4 | Tesseract + Pillow | Belajar OCR step-by-step |
| **Upload** | 5 | Docling + Qwen AI | Baca dokumen nyata secara akurat |

Target akurasi: ≥ 95% character accuracy.

---

## Cara Install

### 1. Python packages

```bash
pip install -r requirements.txt
```

Package utama:
- `Pillow`, `pytesseract`, `opencv-python`, `numpy` — pipeline utama (Tesseract)
- `docling` — baca PDF, DOCX, gambar (download model AI ~500 MB saat pertama kali dijalankan)

### 2. Tesseract OCR

Wajib untuk pipeline utama (tab 1–4). Install sesuai OS:

#### Windows

1. Download dari **github.com/UB-Mannheim/tesseract/wiki** — pilih `tesseract-ocr-w64-setup-*.exe`
2. Saat install, centang **Additional language data → Indonesian**
3. Tesseract akan ada di `C:\Program Files\Tesseract-OCR\tesseract.exe`

> Jika lupa install bahasa Indonesia: download `ind.traineddata` dari
> github.com/tesseract-ocr/tessdata lalu copy ke `C:\Program Files\Tesseract-OCR\tessdata\`

#### macOS

```bash
brew install tesseract tesseract-lang
```

#### Linux (Debian / Ubuntu)

```bash
sudo apt install tesseract-ocr tesseract-ocr-ind
```

### 3. Ollama + Qwen (untuk tab Upload)

Ollama menjalankan model AI secara lokal — dipakai untuk parsing dokumen ke JSON.

1. Download dan install Ollama dari **ollama.com**
2. Buka terminal baru, lalu download model Qwen (~4–5 GB):
   ```bash
   ollama pull qwen2.5
   ```
3. Ollama otomatis berjalan di background di `http://localhost:11434`

> Jika Ollama tidak berjalan saat upload, sistem otomatis fallback ke parsing regex biasa.

---

## Cara Jalankan

### Pipeline utama (terminal)

```bash
python main.py
```

Atau dengan seed berbeda (data faktur berbeda):

```bash
python main.py --seed 7
```

### UI (React + Flask)

**Terminal 1 — Python API:**
```bash
python api.py
# Berjalan di http://localhost:5000
```

**Terminal 2 — React dev server:**
```bash
cd ui
npm install
npm run dev
# Buka http://localhost:5173
```

---

## Yang Terjadi Saat Dijalankan (Pipeline Utama)

```
Langkah 1: GENERATE FAKTUR SINTETIK
  → Buat gambar faktur Indonesia beserta nilai ground truth-nya

Langkah 2: PREPROCESSING GAMBAR
  → 6 langkah untuk meningkatkan kualitas gambar sebelum OCR:
     1. Upscale 2x     — font dari 13px jadi 26px
     2. Grayscale      — hapus info warna
     3. Contrast +1.6x — perkuat tinta vs kertas
     4. Denoise        — bersihkan noise
     5. Binarize Otsu  — hitam-putih murni
     6. Sharpen        — pertegas tepi karakter

Langkah 3: OCR
  → Baca teks dari gambar, bandingkan sebelum vs sesudah preprocessing

Langkah 4: PARSING
  → Ekstrak field terstruktur dari teks OCR menggunakan regex

Langkah 5: SCORING
  → Hitung akurasi dengan CER (Character Error Rate)
  → Target: >= 95%
```

---

## Tab UI

| Tab | Isi |
|-----|-----|
| **Invoice** | Gambar faktur + data ground truth terstruktur |
| **Preprocessing** | 6 langkah preprocessing dengan gambar + penjelasan |
| **OCR** | Teks OCR sebelum vs sesudah preprocessing |
| **Akurasi** | Skor CER, progress bar, tabel per-field (EXACT / ~X% / MISS) |
| **Upload Dokumen** | Upload file nyata → Docling + Qwen → konten terstruktur |

---

## Tab Upload Dokumen

Upload file invoice atau dokumen apapun. Pipeline:

```
File (PDF / DOCX / gambar)
         ↓
      Docling          ← baca layout, tabel, teks (OCR internal jika gambar)
         ↓
   teks markdown
         ↓
    Qwen (Ollama)      ← parse teks → JSON key-value secara cerdas
         ↓               (fallback ke regex jika Ollama tidak jalan)
   Hasil di UI         ← konten dinamis + tabel + skor confidence
```

**Format yang didukung:** PDF, DOCX, PNG, JPG, JPEG, BMP, TIFF, WEBP — maks 20 MB

**Skor kualitas** ditampilkan berdasarkan Docling confidence (target ≥ 95%).
Badge **Qwen AI** muncul di UI jika Ollama berhasil digunakan.

**Opsional — CSV ground truth:**
Upload CSV berisi nilai field yang diketahui → sistem hitung CER aktual per-field
seperti di tab Akurasi. Download template CSV dari tombol di UI.

---

## Output Files

Setelah menjalankan pipeline utama, folder `output/` berisi:

| File | Isi |
|------|-----|
| `invoice_original.png` | Gambar faktur yang dibuat |
| `step_01_upscale.png` — `step_06_sharpen.png` | Gambar setiap langkah preprocessing |
| `ocr_raw.txt` | Teks OCR tanpa preprocessing |
| `ocr_preprocessed.txt` | Teks OCR dengan preprocessing |
| `ground_truth.json` | Nilai field yang sebenarnya |
| `results.json` | Skor akurasi detail per field |

---

## Struktur Kode

```
ocr_parse_example/
├── main.py                      # Entry point pipeline utama
├── api.py                       # Flask API server untuk UI
├── requirements.txt
└── src/
    ├── invoice_generator.py     # Buat gambar faktur sintetik + ground truth
    ├── preprocessor.py          # Pipeline 6-langkah preprocessing gambar
    ├── ocr.py                   # Wrapper pytesseract (Windows/macOS/Linux)
    ├── parser.py                # Regex parser: teks OCR → data terstruktur
    ├── scorer.py                # Hitung CER dan field accuracy
    └── upload_processor.py      # Pipeline upload: Docling + Qwen AI parsing
```

### Perbedaan dua pipeline

**Pipeline utama** (tab 1–4) — untuk belajar cara kerja OCR:
- Gambar sintetik → Pillow preprocessing → Tesseract OCR → regex parser → CER score
- Setiap langkah bisa dilihat hasilnya di UI
- Ada ground truth → skor akurasi bisa dihitung dengan tepat

**Pipeline upload** (tab 5) — untuk dokumen nyata:
- Docling menangani layout analysis, tabel, dan OCR secara internal
- Qwen AI (via Ollama) parsing teks → JSON secara cerdas, tanpa schema tetap
- Konten apapun dalam dokumen diekstrak secara dinamis (bukan hanya field invoice)

---

## Penjelasan Konsep

**Kenapa preprocessing?**
Tesseract bekerja optimal pada gambar resolusi tinggi (300+ DPI) dengan teks hitam-putih bersih.
Gambar tanpa preprocessing biasanya 10–20% lebih rendah akurasinya.

**Kenapa regex untuk parsing (pipeline utama)?**
Dokumen terstruktur seperti faktur punya format yang konsisten.
Regex lebih mudah dipahami dan di-debug dibanding ML untuk kasus pembelajaran ini.

**Kenapa Qwen untuk parsing (pipeline upload)?**
Regex tidak bisa menangani dokumen yang formatnya bervariasi, nilai multi-baris,
atau field yang tidak mengikuti pola tertentu. Qwen memahami konteks dokumen
dan mengekstrak informasi secara natural, seperti manusia membaca dokumen.

**Apa itu CER?**
Character Error Rate = jumlah karakter salah / total karakter referensi.
CER 0.03 = 3% karakter salah → akurasi 97%.

**Kenapa Docling?**
Docling (IBM Research) menangani PDF, DOCX, dan gambar dalam satu pipeline —
termasuk layout analysis dan OCR internal menggunakan EasyOCR.
Tidak perlu install Tesseract untuk pipeline upload.

---

## Konfigurasi Opsional

### Ganti model Qwen

Default menggunakan `qwen2.5`. Bisa diganti via environment variable:

```bash
# Windows PowerShell
$env:QWEN_MODEL = "qwen2.5:14b"
python api.py
```

```bash
# macOS / Linux
QWEN_MODEL=qwen2.5:14b python api.py
```

Model yang tersedia di Ollama: `qwen2.5:3b` (ringan), `qwen2.5:7b` (default), `qwen2.5:14b` (lebih akurat).

### Ganti URL Ollama

Jika Ollama berjalan di port atau host berbeda:

```bash
QWEN_BASE_URL=http://localhost:11434 python api.py
```
