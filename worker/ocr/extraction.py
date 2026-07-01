"""Ekstraksi teks dari file (lapisan infra).

Menyediakan blok bangunan untuk mengubah file menjadi teks mentah + tabel:
  - pdfplumber untuk PDF digital (layout-aware, kolom tabel rapi)
  - Docling default untuk non-PDF (docx/gambar)
  - Docling force full-page OCR (RapidOCR) untuk PDF gambar/scan

Orkestrasi pemilihan jalur ada di pipeline.py (agar status per-langkah tetap
tercatat di sana).
"""

import os

# PDF gambar/scan sering punya text-layer tipis (mis. cuma disclaimer); Docling
# default melihat ada teks lalu MELEWATI OCR -> isi form hilang. Jika alnum per
# halaman di bawah ambang ini, ulangi dengan force full-page OCR.
OCR_FORCE_MIN_ALNUM_PER_PAGE = int(os.getenv("OCR_FORCE_MIN_ALNUM_PER_PAGE", "400"))

_converter = None
_ocr_converter = None


def get_converter():
    global _converter
    if _converter is None:
        from docling.document_converter import DocumentConverter
        _converter = DocumentConverter()
    return _converter


def get_ocr_converter():
    """Converter yang memaksa OCR seluruh halaman, mengabaikan text-layer tipis."""
    global _ocr_converter
    if _ocr_converter is None:
        from docling.document_converter import DocumentConverter, PdfFormatOption
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.datamodel.base_models import InputFormat
        opts = PdfPipelineOptions()
        opts.do_ocr = True
        opts.ocr_options.force_full_page_ocr = True
        _ocr_converter = DocumentConverter(
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)}
        )
    return _ocr_converter


def page_count(document) -> int:
    try:
        return max(1, len(document.pages))
    except Exception:
        return 1


def is_text_sparse(raw_text: str, num_pages: int) -> bool:
    """True bila teks terlalu sedikit per halaman (indikasi PDF gambar/scan)."""
    stripped = raw_text.replace("<!-- image -->", "")
    alnum = sum(1 for c in stripped if c.isalnum())
    return alnum / max(num_pages, 1) < OCR_FORCE_MIN_ALNUM_PER_PAGE


def doc_confidence(document) -> float:
    try:
        return float(document.confidence_scores.mean_grade)
    except Exception:
        return 1.0


def pdfplumber_text(path) -> tuple:
    """Teks PDF digital dengan layout dipertahankan (kolom tabel tidak geser).
    Return (text, num_pages). Jauh lebih akurat untuk tabel dibanding markdown Docling."""
    import pdfplumber
    parts = []
    with pdfplumber.open(str(path)) as pdf:
        for page in pdf.pages:
            parts.append(page.extract_text(layout=True) or "")
        n = len(pdf.pages)
    return "\n\n".join(parts), n


def extract_tables(document) -> list:
    tables = []
    try:
        for table in document.tables:
            grid = [[cell.text for cell in row] for row in table.data.grid]
            if grid:
                tables.append(grid)
    except Exception:
        pass
    return tables
