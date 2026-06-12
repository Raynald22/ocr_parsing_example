"""
parser.py
=========
Ekstrak data terstruktur dari teks OCR faktur pajak.

Strategi parsing:
  1. Normalisasi teks (perbaiki error OCR umum, kolaps spasi)
  2. Untuk setiap field, coba beberapa regex pattern (primary → fallback)
  3. Parsing item tabel baris per baris dengan satuan sebagai anchor
  4. Konversi angka ke int (hilangkan separator ribuan Indonesia ".")

Kenapa regex, bukan ML?
  - Lebih mudah dipahami dan di-debug
  - Deterministik: jelas kenapa match atau tidak
  - Cukup untuk struktur dokumen yang konsisten
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from src.invoice_generator import InvoiceData, LineItem


# ---------------------------------------------------------------------------
# Data model hasil parsing
# ---------------------------------------------------------------------------

@dataclass
class ParsedLineItem:
    nomor:        int
    deskripsi:    str
    kuantitas:    int
    satuan:       str
    harga_satuan: int
    total_harga:  int


@dataclass
class ParsedInvoice:
    nomor_faktur:   Optional[str] = None
    tanggal:        Optional[str] = None
    jatuh_tempo:    Optional[str] = None
    nama_penjual:   Optional[str] = None
    npwp_penjual:   Optional[str] = None
    nama_pembeli:   Optional[str] = None
    npwp_pembeli:   Optional[str] = None
    alamat_pembeli: Optional[str] = None
    items:          List[ParsedLineItem] = field(default_factory=list)
    subtotal:       Optional[int] = None
    ppn:            Optional[int] = None
    total:          Optional[int] = None


# ---------------------------------------------------------------------------
# Regex patterns
# Setiap field punya beberapa pattern: primary dulu, lalu fallback.
# Ini meningkatkan ketahanan terhadap variasi output OCR.
# ---------------------------------------------------------------------------

# No. Faktur: "INV-2024/001/DES"
# Fallback: OCR English-only sering menghilangkan ':' separator,
# dan '/' dalam nilai bisa terbaca sebagai "'" atau ' ' (spasi).
_P_FAKTUR = [
    r'No\.?\s*[Ff]aktur\s*[:\|]\s*([A-Z0-9][A-Z0-9\-/\.]+)',
    r'No\.?\s*[Ff]aktur\s+([A-Z]{2,}[A-Z0-9\-/\.\'\s:]{4,}?)(?=\s+NPWP|\s{2,}|\n|$)',
    r'Nomor\s*[:\|]?\s*([A-Z0-9][A-Z0-9\-/\.]+)',
]

# Tanggal dan Jatuh Tempo: "15 Desember 2024"
# ':' dibuat opsional — OCR English-only sering menghilangkannya.
_P_TANGGAL = [
    r'[Tt]anggal\s*[:\|]?\s*(\d{1,2}\s+\w+\s+\d{4})',
    r'[Tt]gl\.?\s*[:\|]?\s*(\d{1,2}[\s\-/]\w+[\s\-/]\d{4})',
]
_P_JATUH = [
    r'[Jj]atuh\s+[Tt]empo\s*[:\|]?\s*(\d{1,2}\s+\w+\s+\d{4})',
    r'[Jj]atuh\s*[:\|]?\s*(\d{1,2}\s+\w+\s+\d{4})',
]

# Nama Penjual (baris setelah "Faktur Pajak", atau label spesifik)
_P_NAMA_PENJUAL = [
    r'(?:^|\n)(PT\.\s+[A-Za-z ]+|CV\.\s+[A-Za-z ]+)',
]

# NPWP: "01.234.567.8-091.000"
# ':' opsional; spasi dalam nilai (OCR: "98.765.432. 1-012.000") dibersihkan oleh _clean_npwp().
_P_NPWP_PENJUAL = [
    r'NPWP\s+Penjual\s*[:\|]?\s*([\d]{2}\.[\d\.\s]+\-[\d]{3}\.[\d]{3})',
    r'NPWP\s+Penjual\s*[:\|]?\s*([\d][\d\.\s]+-[\d\.]+)',
]
_P_NPWP_PEMBELI = [
    r'NPWP\s+Pembeli\s*[:\|]?\s*([\d]{2}\.[\d\.\s]+\-[\d]{3}\.[\d]{3})',
    r'NPWP\s+Pembeli\s*[:\|]?\s*([\d][\d\.\s]+-[\d\.]+)',
]

# Nama Pembeli: "PT. Berkah Sentosa"
_P_NAMA_PEMBELI = [
    r'[Kk]epada\s+[Yy]th\.?\s*[:\|]?\s*((?:PT\.|CV\.)\s*[A-Za-z ]+)',
    r'[Kk]epada\s+[Yy]th\.?\s*[:\|]?\s*([A-Za-z][A-Za-z .]+)',
]

# Alamat Pembeli
# J[lI] — Tesseract English sering membaca "Jl." sebagai "JI." (kapital-I, bukan l)
_P_ALAMAT_PEMBELI = [
    r'[Aa]lamat\s*[:\|]?\s*(J[lI]\.\s*.+)',
    r'[Aa]lamat\s*[:\|]?\s*(.{10,})',
]

# Angka mata uang: "Rp 30.900.000" → "30900000"
_P_SUBTOTAL = [
    r'[Ss]ubtotal\s*[:\|]?\s*(?:Rp\.?\s*)?([\d\.,]{4,})',
    r'DPP\s*[:\|]?\s*(?:Rp\.?\s*)?([\d\.,]{4,})',
]
_P_PPN = [
    r'PPN\s*(?:\(1[01]%\))?\s*[:\|]?\s*(?:Rp\.?\s*)?([\d\.,]{4,})',
]
_P_TOTAL = [
    r'TOTAL\s+TAGIHAN\s*[:\|]?\s*(?:Rp\.?\s*)?([\d\.,]{4,})',
    r'TOTAL\s*[:\|]?\s*(?:Rp\.?\s*)?([\d\.,]{4,})',
]

# Satu baris item tabel:
# "1  Laptop Asus VivoBook 15   1  unit  Rp 8.500.000  Rp 8.500.000"
_P_ITEM = re.compile(
    r'^\s*(\d{1,2})\s+'                          # nomor
    r'(.+?)\s+'                                   # deskripsi (lazy)
    r'(\d{1,3})\s+'                               # qty
    r'(unit|pcs|buah|set|lembar|kg)\s+'           # satuan (anchor penting)
    r'(?:Rp\.?\s*)?([\d\.,]{3,})\s+'             # harga satuan
    r'(?:Rp\.?\s*)?([\d\.,]{3,})',               # total harga
    re.IGNORECASE | re.MULTILINE,
)


# ---------------------------------------------------------------------------
# Fungsi utama
# ---------------------------------------------------------------------------

def parse_invoice(ocr_text: str) -> ParsedInvoice:
    """
    Parse teks OCR faktur menjadi ParsedInvoice terstruktur.

    Args:
        ocr_text: Teks mentah dari Tesseract OCR

    Returns:
        ParsedInvoice dengan field yang berhasil diekstrak
    """
    text = _normalize(ocr_text)
    result = ParsedInvoice()

    result.nomor_faktur   = _extract(text, _P_FAKTUR)
    result.tanggal        = _extract(text, _P_TANGGAL)
    result.jatuh_tempo    = _extract(text, _P_JATUH)
    result.npwp_penjual   = _clean_npwp(_extract(text, _P_NPWP_PENJUAL))
    result.npwp_pembeli   = _clean_npwp(_extract(text, _P_NPWP_PEMBELI))
    result.nama_pembeli   = _clean_name(_extract(text, _P_NAMA_PEMBELI))
    result.alamat_pembeli = _extract(text, _P_ALAMAT_PEMBELI)

    # Nama penjual: ambil dari baris pertama yang berisi "PT." atau "CV."
    m = re.search(_P_NAMA_PENJUAL[0], text, re.MULTILINE)
    if m:
        result.nama_penjual = m.group(1).strip()

    # Parse angka
    result.subtotal = _extract_int(text, _P_SUBTOTAL)
    result.ppn      = _extract_int(text, _P_PPN)
    result.total    = _extract_int(text, _P_TOTAL)

    # Parse baris-baris item tabel
    result.items = _parse_items(text)

    return result


def display_parsed_invoice(parsed: ParsedInvoice) -> None:
    """Tampilkan hasil parsing dalam format tabel yang mudah dibaca."""
    print("\n  Hasil Parsing:")
    print(f"  {'Field':<20} {'Nilai'}")
    print("  " + "-" * 65)

    scalar_fields = [
        ("nomor_faktur",   parsed.nomor_faktur),
        ("tanggal",        parsed.tanggal),
        ("jatuh_tempo",    parsed.jatuh_tempo),
        ("nama_penjual",   parsed.nama_penjual),
        ("npwp_penjual",   parsed.npwp_penjual),
        ("nama_pembeli",   parsed.nama_pembeli),
        ("npwp_pembeli",   parsed.npwp_pembeli),
        ("alamat_pembeli", parsed.alamat_pembeli),
        ("subtotal",       f"Rp {parsed.subtotal:,}".replace(",", ".") if parsed.subtotal else None),
        ("ppn",            f"Rp {parsed.ppn:,}".replace(",", ".")       if parsed.ppn      else None),
        ("total",          f"Rp {parsed.total:,}".replace(",", ".")     if parsed.total    else None),
    ]

    for name, val in scalar_fields:
        status = str(val)[:55] if val else "[TIDAK DITEMUKAN]"
        print(f"  {name:<20} {status}")

    n = len(parsed.items)
    print(f"  {'items':<20} {n} item{'s' if n != 1 else ''} ditemukan")
    for it in parsed.items:
        print(f"  {'':4} {it.nomor}. {it.deskripsi[:30]:<32} "
              f"qty={it.kuantitas} {it.satuan}  "
              f"@ Rp {it.harga_satuan:,}".replace(",", "."))
    print()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _normalize(text: str) -> str:
    """
    Perbaiki error OCR umum dan normalisasi whitespace.
    Kolom tabel yang dipisah spasi banyak dipertahankan untuk regex item.
    """
    # "JI." → "Jl." — Tesseract English sering baca 'l' kecil sebagai 'I' kapital
    text = re.sub(r'\bJI\.', 'Jl.', text)
    lines = text.splitlines()
    return "\n".join(lines)


def _extract(text: str, patterns: List[str]) -> Optional[str]:
    """Coba setiap pattern secara berurutan, kembalikan hasil pertama yang cocok."""
    for pat in patterns:
        m = re.search(pat, text, re.MULTILINE | re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return None


def _extract_int(text: str, patterns: List[str]) -> Optional[int]:
    """Ekstrak nilai currency sebagai integer."""
    raw = _extract(text, patterns)
    if raw is None:
        return None
    return _normalize_currency(raw)


def _normalize_currency(raw: str) -> int:
    """
    Konversi string angka Indonesia ke integer.

    Contoh:
        "30.900.000" → 30900000
        "30,900,000" → 30900000
        "30900000"   → 30900000
    """
    # Hapus semua titik dan koma (keduanya bisa jadi ribuan separator)
    cleaned = re.sub(r'[.,]', '', raw.strip())
    try:
        return int(cleaned)
    except ValueError:
        return 0


def _parse_items(text: str) -> List[ParsedLineItem]:
    """
    Parse semua baris item dari teks OCR.

    Mencari baris dengan format: No  Deskripsi  Qty  Satuan  Harga  Total
    Satuan (unit/pcs/buah/set) digunakan sebagai anchor yang paling reliable.
    """
    items = []
    for m in _P_ITEM.finditer(text):
        nomor        = int(m.group(1))
        deskripsi    = m.group(2).strip()
        kuantitas    = int(m.group(3))
        satuan       = m.group(4).lower()
        harga_satuan = _normalize_currency(m.group(5))
        total_harga  = _normalize_currency(m.group(6))
        items.append(ParsedLineItem(
            nomor=nomor, deskripsi=deskripsi, kuantitas=kuantitas,
            satuan=satuan, harga_satuan=harga_satuan, total_harga=total_harga,
        ))
    # Hapus duplikat berdasarkan nomor
    seen = set()
    unique = []
    for it in items:
        if it.nomor not in seen:
            seen.add(it.nomor)
            unique.append(it)
    return sorted(unique, key=lambda x: x.nomor)


def _clean_name(s: Optional[str]) -> Optional[str]:
    """Hapus teks yang tidak relevan setelah nama perusahaan."""
    if not s:
        return None
    # Potong di karakter yang tidak mungkin ada dalam nama perusahaan
    s = re.sub(r'\s*[,;]\s*.*$', '', s).strip()
    return s


def _clean_npwp(s: Optional[str]) -> Optional[str]:
    """
    Bersihkan NPWP dari spasi ekstra akibat OCR error.
    Contoh: "98.765.432. 1-012.000" → "98.765.432.1-012.000"
    """
    if not s:
        return None
    return re.sub(r'\s+', '', s).strip()
