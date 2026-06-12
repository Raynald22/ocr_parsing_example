"""
ocr.py
======
Wrapper tipis di atas pytesseract untuk membaca teks dari gambar faktur.

Konfigurasi Tesseract yang digunakan:
  --oem 3  : Mode engine LSTM (deep learning) + Legacy (pilih otomatis)
  --psm 6  : Anggap input sebagai satu blok teks seragam (cocok untuk dokumen)
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PIL import Image

# Path default Tesseract di Windows
_TESSERACT_PATHS = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    os.path.expanduser(r"~\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"),
]

TESSERACT_CONFIG = "--oem 3 --psm 6"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class OcrResult:
    text:       str
    confidence: float   # rata-rata confidence per kata (0–100)
    word_count: int
    char_count: int
    lang:       str


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

def configure_tesseract(path: Optional[str] = None) -> None:
    """
    Deteksi instalasi Tesseract dan set ke pytesseract.

    Args:
        path: Path manual ke tesseract.exe (opsional).
              Jika None, dicari otomatis dari lokasi standar.

    Raises:
        RuntimeError: Jika Tesseract tidak ditemukan.
    """
    try:
        import pytesseract
    except ImportError:
        raise ImportError("Jalankan: pip install pytesseract")

    if path:
        pytesseract.pytesseract.tesseract_cmd = path
        return

    for candidate in _TESSERACT_PATHS:
        if Path(candidate).exists():
            pytesseract.pytesseract.tesseract_cmd = candidate
            return

    raise RuntimeError(
        "\n"
        "  Tesseract tidak ditemukan!\n"
        "  Langkah instalasi:\n"
        "  1. Download installer dari:\n"
        "     https://digi.bib.uni-mannheim.de/tesseract/\n"
        "     (pilih file: tesseract-ocr-w64-setup-*.exe)\n"
        "  2. Saat install, centang 'Additional language data' → Indonesian\n"
        "  3. Jalankan ulang script ini\n"
        "\n"
        "  Atau set path manual: configure_tesseract(path=r'C:\\...\\tesseract.exe')\n"
    )


def get_tesseract_version() -> str:
    """Kembalikan versi Tesseract yang terinstall."""
    import pytesseract
    try:
        return pytesseract.get_tesseract_version().vstring
    except Exception:
        return pytesseract.get_tesseract_version()


# ---------------------------------------------------------------------------
# Fungsi OCR
# ---------------------------------------------------------------------------

def run_ocr(
    image: Image.Image,
    lang: str = "ind+eng",
    config: str = TESSERACT_CONFIG,
) -> OcrResult:
    """
    Jalankan OCR pada gambar, kembalikan teks yang diekstrak.

    Args:
        image:  Gambar PIL (idealnya sudah dipreprocess)
        lang:   Bahasa OCR. "ind+eng" = Indonesia + Inggris
        config: Konfigurasi Tesseract

    Returns:
        OcrResult dengan teks dan statistik dasar
    """
    import pytesseract

    # Fallback ke bahasa Inggris saja jika tessdata Indonesia tidak ada
    lang = _check_lang(lang)

    text = pytesseract.image_to_string(image, lang=lang, config=config)
    text = text.strip()

    return OcrResult(
        text=text,
        confidence=0.0,     # gunakan run_ocr_with_confidence() untuk confidence
        word_count=len(text.split()),
        char_count=len(text),
        lang=lang,
    )


def run_ocr_with_confidence(
    image: Image.Image,
    lang: str = "ind+eng",
    config: str = TESSERACT_CONFIG,
) -> OcrResult:
    """
    Jalankan OCR dan hitung confidence rata-rata per kata.

    Tesseract mengembalikan confidence 0–100 untuk setiap kata yang dikenali.
    Confidence -1 menandakan elemen layout (bukan kata), dilewati.

    Returns:
        OcrResult dengan confidence terisi (0.0–100.0)
    """
    import pytesseract

    lang = _check_lang(lang)

    # image_to_data mengembalikan DataFrame-like string dengan kolom:
    # level, page_num, block_num, par_num, line_num, word_num, left, top,
    # width, height, conf, text
    data = pytesseract.image_to_data(
        image, lang=lang, config=config,
        output_type=pytesseract.Output.DICT,
    )

    text = pytesseract.image_to_string(image, lang=lang, config=config).strip()

    # Ambil hanya confidence kata yang valid (conf >= 0)
    confs = [int(c) for c in data["conf"] if int(c) >= 0]
    avg_conf = sum(confs) / len(confs) if confs else 0.0

    return OcrResult(
        text=text,
        confidence=avg_conf,
        word_count=len(text.split()),
        char_count=len(text),
        lang=lang,
    )


# ---------------------------------------------------------------------------
# Perbandingan hasil
# ---------------------------------------------------------------------------

def compare_ocr_results(raw: OcrResult, preprocessed: OcrResult) -> None:
    """
    Tampilkan tabel perbandingan OCR sebelum dan sesudah preprocessing.

    Ini membuktikan bahwa preprocessing memang meningkatkan akurasi.
    """
    print("\n  Perbandingan OCR:")
    print(f"  {'Metrik':<22} {'Tanpa Preprocess':>18} {'Dengan Preprocess':>18}")
    print("  " + "-" * 60)

    rows = [
        ("Confidence Tesseract", f"{raw.confidence:.1f}%",      f"{preprocessed.confidence:.1f}%"),
        ("Jumlah kata",          str(raw.word_count),           str(preprocessed.word_count)),
        ("Jumlah karakter",      str(raw.char_count),           str(preprocessed.char_count)),
        ("Bahasa",               raw.lang,                      preprocessed.lang),
    ]
    for label, r, p in rows:
        print(f"  {label:<22} {r:>18} {p:>18}")
    print()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _check_lang(lang: str) -> str:
    """Cek apakah tessdata untuk bahasa yang diminta tersedia."""
    import pytesseract

    try:
        available = pytesseract.get_languages()
    except Exception:
        return "eng"

    # Jika "ind" tidak ada, fallback ke "eng" saja
    requested = [l.strip() for l in lang.split("+")]
    valid      = [l for l in requested if l in available]

    if not valid:
        return "eng"

    if "ind" in requested and "ind" not in available:
        print(
            "  [!] Tessdata bahasa Indonesia (ind) tidak ditemukan.\n"
            "      Fallback ke bahasa Inggris. Akurasi bisa menurun.\n"
            "      Download ind.traineddata dari:\n"
            "      https://github.com/tesseract-ocr/tessdata/blob/main/ind.traineddata\n"
        )

    return "+".join(valid) if valid else "eng"
