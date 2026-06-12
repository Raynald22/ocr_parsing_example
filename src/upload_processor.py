"""
upload_processor.py
====================
Proses file gambar yang diupload user: preprocessing → OCR → parsing → skor kualitas.

Berbeda dengan pipeline utama yang punya ground truth (data referensi yang diketahui),
modul ini menghitung skor TANPA ground truth menggunakan tiga komponen:

  1. OCR Confidence  (50%) — seberapa yakin Tesseract terhadap setiap karakter
  2. Field Completeness (35%) — berapa banyak field yang berhasil diparse
  3. Math Consistency (15%) — apakah subtotal + ppn = total?

Format yang didukung (via Pillow, tanpa dependency tambahan):
  PNG, JPG, JPEG, BMP, TIFF, TIF, WEBP
"""

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List, Optional

from PIL import Image

from src.ocr import configure_tesseract, run_ocr_with_confidence, OcrResult
from src.parser import parse_invoice, ParsedInvoice
from src.preprocessor import preprocess_for_ocr

OUTPUT_DIR    = Path("output")
RESULT_FILE   = OUTPUT_DIR / "upload_result.json"
TOTAL_FIELDS  = 11   # nomor_faktur, tanggal, jatuh_tempo, nama_penjual, npwp_penjual,
                     # nama_pembeli, npwp_pembeli, alamat_pembeli, subtotal, ppn, total

SUPPORTED = {'.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.tif', '.webp'}


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class UploadQualityScore:
    ocr_confidence:     float          # Tesseract confidence rata-rata per kata (0–100)
    ocr_confidence_norm: float         # dinormalisasi ke 0–1
    field_completeness: float          # fields_found / TOTAL_FIELDS
    fields_found:       int
    fields_total:       int
    math_consistent:    Optional[bool] # None = tidak bisa dicek, True/False = konsistensi angka
    math_score:         float
    overall:            float          # skor gabungan (0.0–1.0)
    passes:             bool           # overall >= 0.95


@dataclass
class UploadResult:
    filename:       str
    image_url:      str          # "/images/uploaded_original.png"
    prep_images:    List[str]    # nama file di output/ untuk setiap langkah
    ocr_raw_text:   str
    ocr_prep_text:  str
    ocr_confidence: float
    parsed_fields:  dict         # ParsedInvoice sebagai dict (semua Optional)
    parsed_items:   list         # List[ParsedLineItem] sebagai list of dict
    score:          UploadQualityScore
    elapsed_s:      float


# ---------------------------------------------------------------------------
# Fungsi utama
# ---------------------------------------------------------------------------

def process_uploaded(file_path: str, lang: str = "ind+eng") -> UploadResult:
    """
    Jalankan pipeline lengkap pada file yang diupload.

    Args:
        file_path: Path ke file gambar (string atau Path)
        lang:      Bahasa Tesseract (default "ind+eng")

    Returns:
        UploadResult dengan semua hasil, juga disimpan ke output/upload_result.json

    Raises:
        ValueError: Format file tidak didukung
        OSError:    File tidak bisa dibuka
    """
    start = time.time()
    path  = Path(file_path)

    # Pastikan Tesseract ditemukan sebelum proses dimulai
    configure_tesseract()

    if path.suffix.lower() not in SUPPORTED:
        raise ValueError(
            f"Format '{path.suffix}' tidak didukung. "
            f"Gunakan: {', '.join(sorted(SUPPORTED))}"
        )

    OUTPUT_DIR.mkdir(exist_ok=True)

    # 1. Load gambar
    image = Image.open(path).convert("RGB")

    # 2. Simpan sebagai PNG ke output/ agar bisa diakses UI
    original_out = OUTPUT_DIR / "uploaded_original.png"
    image.save(original_out)

    # 3. Preprocessing — 6 langkah
    prep = preprocess_for_ocr(
        image,
        scale_factor=2.0,
        save_steps=False,   # kita copy manual agar nama file tidak bentrok
        output_dir=None,
    )

    # Simpan setiap langkah dengan prefix "upload_" agar tidak menimpa step pipeline utama
    prep_images = []
    for i, step in enumerate(prep.steps):
        name = f"upload_step_{i+1:02d}_{step.name}.png"
        step.image.save(OUTPUT_DIR / name)
        prep_images.append(name)

    # 4. OCR — dua kali: tanpa dan dengan preprocessing
    ocr_raw  = run_ocr_with_confidence(image,      lang=lang)
    ocr_prep = run_ocr_with_confidence(prep.final, lang=lang)

    # 5. Parse teks hasil OCR
    parsed = parse_invoice(ocr_prep.text)

    # 6. Hitung skor kualitas
    score = _compute_score(ocr_prep, parsed)

    elapsed = round(time.time() - start, 2)

    # Serialize ParsedInvoice ke dict (semua Optional, bisa None)
    parsed_fields = {
        "nomor_faktur":   parsed.nomor_faktur,
        "tanggal":        parsed.tanggal,
        "jatuh_tempo":    parsed.jatuh_tempo,
        "nama_penjual":   parsed.nama_penjual,
        "npwp_penjual":   parsed.npwp_penjual,
        "nama_pembeli":   parsed.nama_pembeli,
        "npwp_pembeli":   parsed.npwp_pembeli,
        "alamat_pembeli": parsed.alamat_pembeli,
        "subtotal":       parsed.subtotal,
        "ppn":            parsed.ppn,
        "total":          parsed.total,
    }
    parsed_items = [
        {
            "nomor":        it.nomor,
            "deskripsi":    it.deskripsi,
            "kuantitas":    it.kuantitas,
            "satuan":       it.satuan,
            "harga_satuan": it.harga_satuan,
            "total_harga":  it.total_harga,
        }
        for it in parsed.items
    ]

    result = UploadResult(
        filename=path.name,
        image_url="uploaded_original.png",
        prep_images=prep_images,
        ocr_raw_text=ocr_raw.text,
        ocr_prep_text=ocr_prep.text,
        ocr_confidence=ocr_prep.confidence,
        parsed_fields=parsed_fields,
        parsed_items=parsed_items,
        score=score,
        elapsed_s=elapsed,
    )

    # Persist ke JSON agar bisa di-load kembali saat app restart
    RESULT_FILE.write_text(
        json.dumps(asdict(result), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return result


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def _compute_score(ocr: OcrResult, parsed: ParsedInvoice) -> UploadQualityScore:
    """
    Hitung skor kualitas dokumen TANPA ground truth.

    Komponen:
        OCR Confidence  50% — normalize: 85% conf → skor 1.0
        Field Completeness 35% — berapa field berhasil diparse dari 11
        Math Consistency 15% — apakah subtotal + ppn ≈ total?

    Kalibrasi target >= 95% pada dokumen cetak bersih:
        Conf 86%+ → norm 1.00 → 0.50
        10/11 field → 0.91  → 0.32
        Math OK      → 1.00 → 0.15
        Total = 0.97 → LULUS

    Threshold 85% dipilih karena OCR bahasa Inggris pada teks Indonesia
    secara konsisten menghasilkan confidence ~82-84% (systematic errors
    pada karakter khas Indonesia). Dokumen dengan tessdata 'ind' terpasang
    akan menghasilkan 90%+ confidence.
    """
    # --- OCR confidence ---
    conf_raw  = ocr.confidence                      # 0–100
    conf_norm = min(1.0, conf_raw / 85.0)           # 85% = full score

    # --- Field completeness ---
    scalar_vals = [
        parsed.nomor_faktur, parsed.tanggal, parsed.jatuh_tempo,
        parsed.nama_penjual, parsed.npwp_penjual,
        parsed.nama_pembeli, parsed.npwp_pembeli, parsed.alamat_pembeli,
        parsed.subtotal, parsed.ppn, parsed.total,
    ]
    found        = sum(1 for v in scalar_vals if v is not None)
    completeness = found / TOTAL_FIELDS

    # --- Math consistency ---
    math_ok = None
    if parsed.subtotal is not None and parsed.ppn is not None and parsed.total is not None:
        expected = parsed.subtotal + parsed.ppn
        # Toleransi ±1% untuk rounding
        math_ok  = abs(parsed.total - expected) <= max(1, expected * 0.01)
    math_score = 1.0 if math_ok is True else (0.75 if math_ok is None else 0.0)

    # --- Gabungkan ---
    overall = min(1.0, 0.50 * conf_norm + 0.35 * completeness + 0.15 * math_score)

    return UploadQualityScore(
        ocr_confidence=round(conf_raw, 1),
        ocr_confidence_norm=round(conf_norm, 4),
        field_completeness=round(completeness, 4),
        fields_found=found,
        fields_total=TOTAL_FIELDS,
        math_consistent=math_ok,
        math_score=math_score,
        overall=round(overall, 4),
        passes=overall >= 0.95,
    )
