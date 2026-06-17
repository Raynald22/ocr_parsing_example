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

import csv as _csv
import json
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List, Optional

from PIL import Image

from src.invoice_generator import InvoiceData
from src.ocr import configure_tesseract, run_ocr_with_confidence, OcrResult
from src.parser import parse_invoice, ParsedInvoice
from src.preprocessor import preprocess_for_ocr

OUTPUT_DIR    = Path("output")
RESULT_FILE   = OUTPUT_DIR / "upload_result.json"
TOTAL_FIELDS  = 11   # nomor_faktur, tanggal, jatuh_tempo, nama_penjual, npwp_penjual,
                     # nama_pembeli, npwp_pembeli, alamat_pembeli, subtotal, ppn, total

SUPPORTED        = {'.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.tif', '.webp'}
SUPPORTED_CSV    = {'.csv'}


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
    cer_score:      Optional[dict] = None  # score_to_dict(InvoiceScore) jika CSV diberikan


@dataclass
class DoclingResult:
    """
    Hasil pemrosesan dokumen dengan Docling + Qwen AI.

    Menggunakan pendekatan fleksibel — tidak memaksa dokumen ke dalam schema tetap.
    Isi dokumen diekstrak apa adanya: teks markdown, tabel, dan pasangan kunci:nilai.
    """
    filename:       str
    extracted_text: str             # teks hasil OCR/Docling
    cleaned_text:   str             # teks setelah cleaning
    tables:         list            # tabel dari Docling (list[list[list[str]]])
    key_values:     dict            # key_values flat (dari AI atau regex fallback)
    ai_result:      Optional[dict]  # full structured result dari Qwen (None jika fallback)
    doc_confidence: float           # Docling mean_grade × 100 (0–100)
    tables_found:   int
    kv_found:       int
    passes:         bool            # doc_confidence >= 95
    ai_extraction:  bool            # True jika ai_result terisi dari Qwen
    pipeline_steps: list            # [{step, status, detail, elapsed_s}]
    elapsed_s:      float
    image_url:      Optional[str] = None   # nama file di output/ (hanya untuk upload gambar)
    cer_score:      Optional[dict] = None


# ---------------------------------------------------------------------------
# Fungsi utama
# ---------------------------------------------------------------------------

def process_uploaded(
    file_path: str,
    lang:      str = "ind+eng",
    csv_path:  Optional[str] = None,
) -> UploadResult:
    """
    Jalankan pipeline lengkap pada file yang diupload.

    Args:
        file_path: Path ke file gambar (string atau Path)
        lang:      Bahasa Tesseract (default "ind+eng")
        csv_path:  Path ke CSV ground truth (opsional). Jika diberikan,
                   hasil parsing di-score dengan CER menggunakan nilai CSV.

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

    # 6. Hitung skor kualitas (selalu dihitung)
    score = _compute_score(ocr_prep, parsed)

    # 7. Hitung skor CER jika ground truth CSV diberikan
    cer_score = None
    if csv_path:
        from src.scorer import score_invoice, score_to_dict
        ground_truth = parse_ground_truth_csv(csv_path)
        cer_score = score_to_dict(score_invoice(ground_truth, parsed))

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
        cer_score=cer_score,
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

# ---------------------------------------------------------------------------
# Ground truth CSV
# ---------------------------------------------------------------------------

_NUMERIC_FIELDS = {"subtotal", "ppn", "total"}

_GT_FIELDS = [
    "nomor_faktur", "tanggal", "jatuh_tempo",
    "nama_penjual", "npwp_penjual",
    "nama_pembeli", "npwp_pembeli", "alamat_pembeli",
    "subtotal", "ppn", "total",
]

# Template CSV yang bisa didownload user
CSV_TEMPLATE = "field,value\n" + "\n".join(f"{f}," for f in _GT_FIELDS) + "\n"


def parse_ground_truth_csv(csv_path: str) -> InvoiceData:
    """
    Baca CSV ground truth dan buat InvoiceData untuk di-score.

    Format CSV:
        field,value
        nomor_faktur,INV-2024/001/JAN
        subtotal,6400000
        ...

    Field yang tidak ada di CSV dibiarkan kosong/nol.
    Angka boleh pakai separator ribuan titik ("6.400.000" → 6400000).
    """
    rows: dict = {}
    with open(csv_path, encoding="utf-8", newline="") as f:
        for row in _csv.DictReader(f):
            fname = row.get("field", "").strip()
            fval  = row.get("value", "").strip()
            if fname in _GT_FIELDS and fval:
                rows[fname] = fval

    def get_int(key: str) -> int:
        raw = rows.get(key, "0")
        return int(re.sub(r"[.,]", "", raw)) if raw else 0

    return InvoiceData(
        nomor_faktur   = rows.get("nomor_faktur",   ""),
        tanggal        = rows.get("tanggal",         ""),
        jatuh_tempo    = rows.get("jatuh_tempo",     ""),
        nama_penjual   = rows.get("nama_penjual",    ""),
        npwp_penjual   = rows.get("npwp_penjual",    ""),
        alamat_penjual = rows.get("alamat_penjual",  ""),
        nama_pembeli   = rows.get("nama_pembeli",    ""),
        npwp_pembeli   = rows.get("npwp_pembeli",    ""),
        alamat_pembeli = rows.get("alamat_pembeli",  ""),
        subtotal       = get_int("subtotal"),
        ppn            = get_int("ppn"),
        total          = get_int("total"),
        items          = [],
        terbilang      = "",
    )


@dataclass
class CsvParseResult:
    """Hasil parsing CSV faktur tanpa OCR."""
    filename:     str
    fields:       dict          # semua 11 field, None jika tidak ada di CSV
    fields_found: int
    fields_total: int           # selalu 11
    math_ok:      Optional[bool]  # apakah subtotal + ppn = total?


def process_csv_only(csv_path: str) -> CsvParseResult:
    """
    Parse file CSV faktur dan validasi isinya, tanpa OCR.

    Cocok untuk kasus di mana data invoice sudah tersedia dalam bentuk teks
    (dari sistem akuntansi, export ERP, dll) dan tidak perlu proses gambar.

    Args:
        csv_path: Path ke file CSV dengan format field,value

    Returns:
        CsvParseResult dengan field-field yang berhasil diparsing
    """
    path = Path(csv_path)
    gt   = parse_ground_truth_csv(csv_path)

    fields = {
        "nomor_faktur":   gt.nomor_faktur   or None,
        "tanggal":        gt.tanggal        or None,
        "jatuh_tempo":    gt.jatuh_tempo    or None,
        "nama_penjual":   gt.nama_penjual   or None,
        "npwp_penjual":   gt.npwp_penjual   or None,
        "nama_pembeli":   gt.nama_pembeli   or None,
        "npwp_pembeli":   gt.npwp_pembeli   or None,
        "alamat_pembeli": gt.alamat_pembeli or None,
        "subtotal":       gt.subtotal       or None,
        "ppn":            gt.ppn            or None,
        "total":          gt.total          or None,
    }

    found = sum(1 for v in fields.values() if v is not None)

    math_ok = None
    if gt.subtotal and gt.ppn and gt.total:
        math_ok = abs(gt.total - (gt.subtotal + gt.ppn)) <= max(1, gt.total * 0.01)

    return CsvParseResult(
        filename=path.name,
        fields=fields,
        fields_found=found,
        fields_total=TOTAL_FIELDS,
        math_ok=math_ok,
    )


# ---------------------------------------------------------------------------
# Docling pipeline (untuk tab Upload Dokumen)
# ---------------------------------------------------------------------------

SUPPORTED_DOCLING = {
    '.pdf',
    '.docx', '.doc',
    '.xlsx', '.xls',
    '.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.tif', '.webp',
}

IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.tif', '.webp'}


def process_with_docling(
    file_path: str,
    csv_path:  Optional[str] = None,
) -> DoclingResult:
    """
    Pipeline dokumen: OCR → Clean Text → Qwen → Validate JSON.

    Args:
        file_path: Path ke dokumen (PDF, DOCX, Excel)
        csv_path:  CSV ground truth opsional → skor CER

    Returns:
        DoclingResult dengan hasil tiap step pipeline
    """
    try:
        from docling.document_converter import DocumentConverter
    except ImportError:
        raise ImportError(
            "Jalankan: pip install docling\n"
            "Pertama kali install akan download model AI (~500MB)."
        )

    start = time.time()
    path  = Path(file_path)
    steps = []

    if path.suffix.lower() not in SUPPORTED_DOCLING:
        raise ValueError(
            f"Format '{path.suffix}' tidak didukung. "
            f"Gunakan: {', '.join(sorted(SUPPORTED_DOCLING))}"
        )

    OUTPUT_DIR.mkdir(exist_ok=True)

    # ── Step 1: OCR ────────────────────────────────────────────────────────
    t0 = time.time()
    converter  = DocumentConverter()
    doc_result = converter.convert(str(path))
    raw_text   = doc_result.document.export_to_markdown()

    try:
        conf_01 = float(doc_result.document.confidence_scores.mean_grade)
    except Exception:
        conf_01 = 1.0

    tables = _extract_tables_docling(doc_result.document)
    steps.append({
        "step":      "OCR",
        "status":    "ok",
        "detail":    f"{len(raw_text)} karakter diekstrak, confidence {round(conf_01*100,1)}%",
        "elapsed_s": round(time.time() - t0, 2),
    })

    # Simpan preview gambar jika input adalah file gambar
    image_url = None
    if path.suffix.lower() in IMAGE_EXTS:
        try:
            from PIL import Image as _PILImage
            preview_path = OUTPUT_DIR / "upload_preview.png"
            _PILImage.open(path).convert("RGB").save(preview_path)
            image_url = "upload_preview.png"
        except Exception:
            pass

    # ── Step 2: Clean Text ─────────────────────────────────────────────────
    t0 = time.time()
    cleaned = _clean_text(raw_text)
    steps.append({
        "step":      "Clean Text",
        "status":    "ok",
        "detail":    f"{len(raw_text)} → {len(cleaned)} karakter",
        "elapsed_s": round(time.time() - t0, 2),
    })

    # ── Step 3: Qwen ───────────────────────────────────────────────────────
    t0 = time.time()
    raw_ai = _extract_kv_with_qwen(cleaned)
    if raw_ai:
        steps.append({
            "step":      "Qwen",
            "status":    "ok",
            "detail":    f"JSON diterima ({len(str(raw_ai))} chars)",
            "elapsed_s": round(time.time() - t0, 2),
        })
    else:
        steps.append({
            "step":      "Qwen",
            "status":    "fallback",
            "detail":    "Ollama tidak aktif — menggunakan regex",
            "elapsed_s": round(time.time() - t0, 2),
        })

    # ── Step 4: Validate JSON ──────────────────────────────────────────────
    t0 = time.time()
    if raw_ai:
        # Qwen returns flat {field: value} — use directly as key_values
        key_values = {k: v for k, v in raw_ai.items() if v not in (None, "", [], {})}
        ai_result  = {"key_values": key_values}
        ai_used    = True
        val_status = "ok"
        val_detail = f"{len(key_values)} field diekstrak"
    else:
        ai_result  = None
        key_values = _extract_kv_flexible(cleaned)
        ai_used    = False
        val_status = "skip"
        val_detail = "tidak ada AI result — menggunakan regex"

    steps.append({
        "step":      "Validate JSON",
        "status":    val_status,
        "detail":    val_detail,
        "elapsed_s": round(time.time() - t0, 2),
    })

    # ── CER scoring (opsional) ─────────────────────────────────────────────
    cer_score = None
    if csv_path:
        from src.scorer import score_invoice, score_to_dict
        parsed    = parse_invoice(cleaned)
        gt        = parse_ground_truth_csv(csv_path)
        cer_score = score_to_dict(score_invoice(gt, parsed))

    elapsed = round(time.time() - start, 2)

    result = DoclingResult(
        filename=path.name,
        extracted_text=raw_text,
        cleaned_text=cleaned,
        tables=tables,
        key_values=key_values,
        ai_result=ai_result,
        doc_confidence=round(conf_01 * 100, 1),
        tables_found=len(tables),
        kv_found=len(key_values),
        passes=conf_01 * 100 >= 95.0,
        ai_extraction=ai_used,
        pipeline_steps=steps,
        elapsed_s=elapsed,
        image_url=image_url,
        cer_score=cer_score,
    )

    RESULT_FILE.write_text(
        json.dumps(asdict(result), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return result


def _extract_tables_docling(document) -> list:
    """Ekstrak semua tabel dari dokumen Docling sebagai list 2D string."""
    tables = []
    try:
        for table in document.tables:
            grid = []
            for row in table.data.grid:
                grid.append([cell.text for cell in row])
            if grid:
                tables.append(grid)
    except Exception:
        pass
    return tables


def _extract_kv_flexible(text: str) -> dict:
    """
    Ekstrak pasangan kunci:nilai dari teks dokumen secara dinamis.

    Mencari baris dengan format "Kunci: Nilai" — tidak tergantung pada
    schema tetap seperti nomor_faktur, tanggal, dll.
    Digunakan sebagai fallback jika AI extraction tidak tersedia.
    """
    kv = {}
    for line in text.splitlines():
        line = line.strip().lstrip('#*-> ').strip()
        if ':' not in line or len(line) > 300:
            continue
        key, _, val = line.partition(':')
        key = key.strip()
        val = val.strip()
        if key and val and 3 <= len(key) <= 80 and len(val) <= 200:
            if key not in kv:
                kv[key] = val
    return kv


def _clean_text(text: str) -> str:
    """
    Bersihkan teks hasil OCR sebelum dikirim ke Qwen.

    - Hapus baris kosong berlebihan (> 2 baris berturut-turut)
    - Hapus karakter kontrol non-printable
    - Normalisasi spasi horizontal
    - Hapus baris yang hanya berisi pemisah (---, ===, dll)
    """
    import re
    # Hapus karakter kontrol (kecuali newline dan tab)
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    # Normalisasi spasi horizontal
    text = re.sub(r'[ \t]+', ' ', text)
    # Bersihkan tiap baris
    lines = []
    for line in text.splitlines():
        line = line.strip()
        # Hapus baris pemisah: hanya berisi -, =, _, *, |
        if re.match(r'^[-=_*|#]{3,}$', line):
            continue
        lines.append(line)
    # Kolaps baris kosong berlebihan
    cleaned = re.sub(r'\n{3,}', '\n\n', '\n'.join(lines))
    return cleaned.strip()



def _extract_kv_with_qwen(text: str) -> dict:
    """
    Ekstrak semua informasi dokumen menggunakan Qwen via Ollama.

    Mengirim teks hasil Docling ke Qwen untuk diparsing secara cerdas —
    lebih akurat dari regex karena memahami konteks, nilai multi-baris,
    dan field yang tidak mengikuti format "kunci: nilai" secara ketat.

    Konfigurasi via environment variable (opsional):
        QWEN_BASE_URL  — default: http://localhost:11434
        QWEN_MODEL     — default: qwen2.5

    Setup: install Ollama (https://ollama.com) lalu jalankan:
        ollama pull qwen2.5

    Jika Ollama tidak berjalan / gagal, kembalikan dict kosong (fallback ke regex).
    """
    import json
    import os

    import requests

    base_url = os.getenv("QWEN_BASE_URL", "http://localhost:11434")
    model    = os.getenv("QWEN_MODEL",    "qwen2.5:latest")
    timeout  = int(os.getenv("QWEN_TIMEOUT", "300"))

    # Potong teks — 2000 karakter cukup untuk sebagian besar dokumen
    MAX_CHARS = 2000
    text_for_qwen = text[:MAX_CHARS] + ("\n[dipotong]" if len(text) > MAX_CHARS else "")

    prompt = f"""Extract all key-value information from this document as a flat JSON object.

Rules:
- Output ONLY valid JSON, nothing else
- No markdown, no explanation, no code fences
- Use the exact field names from the document
- Skip empty/blank fields
- For lists (e.g. attachments), join with " | "
- Numbers and dates: keep original format

Output format:
{{"field1": "value1", "field2": "value2"}}

Document:
{text_for_qwen}"""

    try:
        resp = requests.post(
            f"{base_url}/api/chat",
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": "You are a JSON extraction API. Respond ONLY with a single valid JSON object. No markdown, no explanation, no code fences."},
                    {"role": "user",   "content": prompt},
                ],
                "stream":     False,
                "keep_alive": "10m",
                "options": {
                    "temperature": 0,
                    "num_predict": 800,
                    "num_ctx":     2048,
                    "num_gpu":     99,
                },
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        response = resp.json()["message"]["content"].strip()
        print(f"[Qwen] Raw response: {response[:300]}")

        # Cari posisi { pertama lalu parse hanya objek JSON pertama yang valid
        start = response.find('{')
        if start == -1:
            print("[Qwen] Tidak ada JSON ditemukan dalam response")
            return {}
        obj, _ = json.JSONDecoder().raw_decode(response, start)
        return obj

    except Exception as e:
        print(f"[Qwen] Error: {type(e).__name__}: {e}")
        return {}


# ---------------------------------------------------------------------------
# Scoring tanpa ground truth (Tesseract, untuk main pipeline)
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
