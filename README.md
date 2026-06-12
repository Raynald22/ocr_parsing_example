# OCR + Parsing — Faktur Pajak Indonesia

Contoh pembelajaran OCR dan parsing dokumen dengan Python.
Pipeline: **buat gambar faktur** → **preprocessing** → **OCR** → **parse ke JSON** → **hitung akurasi**.

Target akurasi: ≥ 95% character accuracy.

---

## Cara Install

### 1. Install Python packages

```bash
pip install -r requirements.txt
```

Package yang diinstall: `Pillow`, `pytesseract`, `opencv-python`, `numpy`

### 2. Install Tesseract OCR (wajib, terpisah dari pip)

Tesseract adalah engine OCR-nya. Harus diinstall manual:

1. Download installer untuk Windows:
   **https://github.com/UB-Mannheim/tesseract/wiki**
   Scroll ke bagian "The latest installers can be downloaded here" lalu klik
   `tesseract-ocr-w64-setup-*.exe` (versi 64-bit)

2. Jalankan installer. Saat muncul halaman "Choose Components", centang:
   - `Additional language data` → cari dan centang **Indonesian**

3. Selesai install, Tesseract akan ada di:
   `C:\Program Files\Tesseract-OCR\tesseract.exe`

> Jika lupa install bahasa Indonesia saat pertama kali, download manual:
> `ind.traineddata` dari https://github.com/tesseract-ocr/tessdata/blob/main/ind.traineddata
> lalu copy ke `C:\Program Files\Tesseract-OCR\tessdata\`

---

## Cara Jalankan

```bash
python main.py
```

Atau dengan seed berbeda (untuk data faktur yang berbeda):

```bash
python main.py --seed 7
```

---

## Yang Terjadi Saat Dijalankan

Program menjalankan 5 langkah secara berurutan dan menampilkan hasilnya:

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

## Output Files

Setelah dijalankan, folder `output/` berisi:

| File | Isi |
|------|-----|
| `invoice_original.png` | Gambar faktur yang dibuat |
| `step_01_upscale.png` — `step_06_sharpen.png` | Gambar setiap langkah preprocessing |
| `ocr_raw.txt` | Teks OCR tanpa preprocessing |
| `ocr_preprocessed.txt` | Teks OCR dengan preprocessing (lebih akurat) |
| `ground_truth.json` | Nilai field yang sebenarnya (untuk scoring) |
| `results.json` | Skor akurasi detail per field |

---

## Cara Menjalankan UI (React)

Selain output terminal, ada web UI untuk melihat hasil secara visual.

**Terminal 1 — Python API server:**
```bash
pip install flask flask-cors
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

UI memiliki 5 tab:
| Tab | Isi |
|-----|-----|
| **Invoice** | Gambar faktur + data terstruktur ground truth |
| **Preprocessing** | 6 langkah preprocessing dengan gambar + penjelasan |
| **OCR** | Teks OCR sebelum vs sesudah preprocessing |
| **Akurasi** | Skor akurasi, progress bar, tabel per-field (EXACT/CLOSE/MISS) |
| **Upload Dokumen** | Upload gambar invoice sendiri → OCR + parse + skor kualitas |

### Upload Dokumen (tab ke-5)

Drag & drop atau pilih file gambar invoice kamu sendiri (PNG, JPG, JPEG, BMP, TIFF, WEBP, maks 20 MB).
Pipeline akan:
1. Preprocessing gambar (6 langkah)
2. OCR dengan Tesseract
3. Parse field-field invoice
4. Hitung **skor kualitas** (target ≥ 95%):
   - OCR Confidence (50%) — seberapa yakin Tesseract
   - Field Completeness (35%) — berapa field yang berhasil diparse
   - Math Consistency (15%) — apakah subtotal + PPN = Total?

Dari UI bisa juga langsung klik **"Jalankan Pipeline"** untuk membuat data baru dengan seed berbeda.

---

## Struktur Kode

```
ocr_parse_example/
├── main.py                    # Entry point — jalankan ini
├── requirements.txt
└── src/
    ├── invoice_generator.py   # Buat gambar faktur sintetik + data ground truth
    ├── preprocessor.py        # Pipeline 6-langkah preprocessing gambar
    ├── ocr.py                 # Wrapper pytesseract
    ├── parser.py              # Regex parser: teks OCR -> data terstruktur
    └── scorer.py              # Hitung CER dan field accuracy
```

---

## Penjelasan Konsep

**Kenapa preprocessing?**
Tesseract bekerja optimal pada gambar resolusi tinggi (300+ DPI) dengan teks hitam-putih bersih. Gambar yang langsung di-OCR tanpa preprocessing biasanya 10–20% lebih rendah akurasinya.

**Kenapa regex untuk parsing, bukan ML?**
Dokumen terstruktur seperti faktur punya format yang konsisten. Regex lebih mudah dipahami, di-debug, dan dimodifikasi dibanding model ML untuk kasus ini.

**Apa itu CER?**
Character Error Rate = jumlah karakter yang salah / total karakter referensi.
CER 0.03 berarti 3% karakter salah → akurasi 97%.
