# OCR + Parsing Dokumen

Upload dokumen (PDF, DOCX, gambar) → **Docling** baca isinya → **Qwen AI** parse ke JSON → tampil di UI.

Target: dokumen terbaca ≥ 95% akurat.

---

## Cara Install

### 1. Python packages

```bash
pip install -r requirements.txt
```

Package yang diinstall:
- `docling` — baca PDF, DOCX, gambar (download model AI ~500 MB saat pertama kali dijalankan)
- `requests` — HTTP client untuk komunikasi ke Ollama (terinstall otomatis via docling)

### 2. Ollama + Qwen

Ollama menjalankan model Qwen secara lokal — dipakai untuk parsing dokumen ke JSON.

1. Download dan install Ollama dari **ollama.com**
2. Buka terminal baru, lalu download model Qwen (~4–5 GB):
   ```bash
   ollama pull qwen2.5
   ```
3. Ollama otomatis berjalan di background di `http://localhost:11434`

> Jika Ollama tidak berjalan saat upload, sistem otomatis fallback ke parsing regex biasa.

---

## Cara Jalankan

**Terminal 1 — Python API (FastAPI + Uvicorn):**
```bash
python api.py
# Berjalan di http://localhost:5000
# Swagger UI  → http://localhost:5000/docs
```

**Terminal 2 — React dev server:**
```bash
cd ui
npm install
npm run dev
# Buka http://localhost:5173
```

---

## Cara Pakai

1. Buka `http://localhost:5173`
2. Drag & drop atau klik untuk upload file
3. Tunggu Docling membaca dokumen
4. Hasil muncul: konten dokumen + JSON dari Qwen + skor confidence

**Format yang didukung:** PDF, DOCX, PNG, JPG, JPEG, BMP, TIFF, WEBP — maks 20 MB

**Badge di UI:**
- **Qwen AI** (ungu) — Qwen berhasil parse dokumen ke JSON
- **regex** (abu) — Ollama tidak aktif, fallback ke regex biasa

---

## Opsional: CSV Ground Truth

Untuk mengukur akurasi secara tepat (CER per field):

1. Download template CSV dari tombol di UI
2. Isi nilai field yang diketahui
3. Upload bersama dokumen → sistem hitung Character Error Rate per field

---

## Arsitektur

```
Upload file (PDF / DOCX / gambar)
           ↓
        Docling              ← layout analysis, tabel, OCR internal (jika gambar)
           ↓
      teks markdown
           ↓
    Qwen via Ollama          ← parse teks → JSON dengan rules ketat
           ↓                   (fallback ke regex jika Ollama tidak aktif)
       Hasil UI              ← konten dinamis + tabel + skor confidence Docling
```

**Kenapa Docling?**
Menangani PDF, DOCX, dan gambar dalam satu pipeline — termasuk layout analysis
dan OCR internal. Tidak perlu install Tesseract atau preprocessing manual.

**Kenapa Qwen?**
Regex tidak bisa menangani dokumen yang formatnya bervariasi, nilai multi-baris,
atau field yang tidak mengikuti pola tertentu. Qwen memahami konteks dokumen
dan mengekstrak informasi secara natural.

---

## Struktur Kode

```
ocr_parse_example/
├── api.py                       # Flask API server
├── requirements.txt
└── src/
    └── upload_processor.py      # Docling + Qwen AI parsing
ui/
└── src/
    ├── App.jsx                  # Layout utama
    └── components/
        └── UploadView.jsx       # UI upload + tampilan hasil
```

---

## Konfigurasi

### Ganti model Qwen

Default: `qwen2.5`. Model lain yang tersedia di Ollama:

| Model | RAM | Kecepatan | Akurasi |
|-------|-----|-----------|---------|
| `qwen2.5:3b` | ~3 GB | Cepat | Cukup |
| `qwen2.5:latest` (7b) | ~5 GB | Sedang | Baik ✓ default |
| `qwen2.5:14b` | ~10 GB | Lambat | Lebih baik |

```bash
# Windows PowerShell
$env:QWEN_MODEL = "qwen2.5:14b"
python api.py
```

```bash
# macOS / Linux
QWEN_MODEL=qwen2.5:14b python api.py
```

### Ganti URL Ollama

Jika Ollama berjalan di port berbeda:
```bash
QWEN_BASE_URL=http://localhost:11434 python api.py
```
