"""
invoice_generator.py
====================
Membuat gambar faktur pajak Indonesia secara programatik beserta ground truth-nya.

Kenapa synthetic? Karena:
- Reproducible (seed = hasil selalu sama)
- Kita tahu pasti nilai yang benar (ground truth)
- Tidak butuh scan fisik / data pribadi
"""

import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from PIL import Image, ImageDraw, ImageFont

FONT_DIR = "C:/Windows/Fonts"

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class LineItem:
    nomor:       int
    deskripsi:   str
    kuantitas:   int
    satuan:      str   # unit / pcs / buah / set
    harga_satuan: int  # dalam Rupiah
    total_harga:  int  # = kuantitas * harga_satuan


@dataclass
class InvoiceData:
    nomor_faktur:   str
    tanggal:        str   # "15 Desember 2024"
    jatuh_tempo:    str   # "15 Januari 2025"
    nama_penjual:   str
    npwp_penjual:   str   # "01.234.567.8-091.000"
    alamat_penjual: str
    nama_pembeli:   str
    npwp_pembeli:   str
    alamat_pembeli: str
    items:          List[LineItem]
    subtotal:       int
    ppn:            int   # 11% dari subtotal
    total:          int   # subtotal + ppn
    terbilang:      str   # total dalam kata-kata bahasa Indonesia


# ---------------------------------------------------------------------------
# Data contoh
# ---------------------------------------------------------------------------

_PENJUAL = [
    (
        "PT. Teknologi Maju Indonesia",
        "01.234.567.8-091.000",
        "Jl. Gatot Subroto No. 123, Jakarta Selatan",
    ),
    (
        "CV. Solusi Digital Nusantara",
        "02.345.678.9-092.000",
        "Jl. HR. Rasuna Said Kav. 5, Jakarta Selatan",
    ),
]

_PEMBELI = [
    (
        "PT. Berkah Sentosa",
        "98.765.432.1-012.000",
        "Jl. Sudirman No. 45 Blok B-12, Jakarta Pusat",
    ),
    (
        "CV. Maju Bersama",
        "87.654.321.0-011.000",
        "Jl. Thamrin No. 20, Jakarta Pusat",
    ),
]

_BULAN = [
    "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember",
]

_PRODUK = [
    ("Laptop Asus VivoBook 15",        "unit", 8_500_000),
    ("Mouse Wireless Logitech M170",   "unit",   150_000),
    ("Keyboard Mechanical USB",        "unit",   450_000),
    ("Monitor LED 24 inch Full HD",    "unit", 2_200_000),
    ("Headset Bluetooth Sony WH-1000", "unit", 1_800_000),
    ("Webcam HD 1080p Logitech C920",  "unit",   900_000),
    ("SSD External 1TB Samsung T7",    "unit", 1_350_000),
    ("Hub USB-C 7-in-1",               "unit",   280_000),
    ("Printer Laser Canon LBP6030",    "unit", 2_750_000),
    ("Tinta Printer Set Epson L3150",  "set",    380_000),
]


# ---------------------------------------------------------------------------
# Fungsi utama
# ---------------------------------------------------------------------------

def create_sample_invoice(seed: int = 42) -> InvoiceData:
    """Buat data faktur contoh yang deterministik berdasarkan seed."""
    rng = random.Random(seed)

    penjual = _PENJUAL[rng.randint(0, len(_PENJUAL) - 1)]
    pembeli = _PEMBELI[rng.randint(0, len(_PEMBELI) - 1)]

    hari       = rng.randint(1, 28)
    bulan_idx  = rng.randint(0, 11)
    tahun      = 2024
    tanggal    = f"{hari} {_BULAN[bulan_idx]} {tahun}"
    jatuh_idx  = (bulan_idx + 1) % 12
    jatuh_thn  = tahun if bulan_idx < 11 else tahun + 1
    jatuh_tempo = f"{hari} {_BULAN[jatuh_idx]} {jatuh_thn}"

    no = rng.randint(1, 999)
    nomor_faktur = f"INV-{tahun}/{no:03d}/{_BULAN[bulan_idx][:3].upper()}"

    picked = rng.sample(_PRODUK, 5)
    items = []
    for i, (deskripsi, satuan, harga) in enumerate(picked, 1):
        qty   = rng.randint(1, 4)
        total = qty * harga
        items.append(LineItem(
            nomor=i, deskripsi=deskripsi, kuantitas=qty,
            satuan=satuan, harga_satuan=harga, total_harga=total,
        ))

    subtotal = sum(it.total_harga for it in items)
    ppn      = int(subtotal * 0.11)
    total    = subtotal + ppn

    return InvoiceData(
        nomor_faktur=nomor_faktur,
        tanggal=tanggal,
        jatuh_tempo=jatuh_tempo,
        nama_penjual=penjual[0],
        npwp_penjual=penjual[1],
        alamat_penjual=penjual[2],
        nama_pembeli=pembeli[0],
        npwp_pembeli=pembeli[1],
        alamat_pembeli=pembeli[2],
        items=items,
        subtotal=subtotal,
        ppn=ppn,
        total=total,
        terbilang=terbilang(total),
    )


def generate_invoice_image(
    invoice: InvoiceData,
    output_path: Optional[str] = None,
    width: int = 820,
    font_dir: str = FONT_DIR,
) -> Image.Image:
    """Render InvoiceData menjadi gambar PIL 820x~750px."""
    img  = Image.new("RGB", (width, 820), "white")
    draw = ImageDraw.Draw(img)
    f    = _load_fonts(font_dir)
    M    = 35  # margin kiri/kanan

    y = _draw_header(draw, invoice, f, M, width, y=20)
    y = _draw_title_bar(draw, f, y + 6, M, width)
    y = _draw_meta(draw, invoice, f, y + 10, M, width)
    draw.line([(M, y), (width - M, y)], fill="#aaa", width=1)
    y = _draw_buyer(draw, invoice, f, y + 8, M)
    draw.line([(M, y), (width - M, y)], fill="#aaa", width=1)
    y = _draw_table(draw, invoice, f, y + 8, M, width)
    y = _draw_totals(draw, invoice, f, y + 6, M, width)
    draw.line([(M, y), (width - M, y)], fill="#aaa", width=1)
    y = _draw_terbilang(draw, invoice, f, y + 8, M)
    _draw_signature(draw, f, y + 14, M, width)

    # Crop gambar agar tidak ada whitespace terlalu banyak di bawah
    img = img.crop((0, 0, width, y + 120))

    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        img.save(output_path)

    return img


# ---------------------------------------------------------------------------
# Konversi angka ke kata (Bahasa Indonesia)
# ---------------------------------------------------------------------------

def terbilang(n: int) -> str:
    """Konversi angka bulat ke kata-kata Bahasa Indonesia."""
    _satuan = [
        "", "Satu", "Dua", "Tiga", "Empat", "Lima",
        "Enam", "Tujuh", "Delapan", "Sembilan", "Sepuluh", "Sebelas",
    ]

    if n == 0:
        return "Nol"

    parts = []

    if n >= 1_000_000_000:
        parts.append(f"{terbilang(n // 1_000_000_000)} Miliar")
        n %= 1_000_000_000

    if n >= 1_000_000:
        m = n // 1_000_000
        parts.append(f"{'Satu' if m == 1 else terbilang(m)} Juta")
        n %= 1_000_000

    if n >= 1_000:
        m = n // 1_000
        parts.append("Seribu" if m == 1 else f"{terbilang(m)} Ribu")
        n %= 1_000

    if n >= 100:
        m = n // 100
        parts.append("Seratus" if m == 1 else f"{_satuan[m]} Ratus")
        n %= 100

    if n > 0:
        if n <= 11:
            parts.append(_satuan[n])
        elif n < 20:
            parts.append(f"{_satuan[n - 10]} Belas")
        else:
            p, s = divmod(n, 10)
            parts.append(f"{_satuan[p]} Puluh" + (f" {_satuan[s]}" if s else ""))

    return " ".join(parts)


# ---------------------------------------------------------------------------
# Helper: font loading
# ---------------------------------------------------------------------------

def _load_fonts(font_dir: str) -> dict:
    def ttf(name, size):
        try:
            return ImageFont.truetype(str(Path(font_dir) / name), size)
        except (OSError, IOError):
            return ImageFont.load_default()

    return {
        "company": ttf("arialbd.ttf", 17),
        "title":   ttf("arialbd.ttf", 14),
        "label":   ttf("arialbd.ttf", 12),
        "body":    ttf("arial.ttf",   13),
        "small":   ttf("arial.ttf",   11),
        "mono":    ttf("consola.ttf", 12),
    }


# ---------------------------------------------------------------------------
# Helper: format mata uang Indonesia
# ---------------------------------------------------------------------------

def _rp(amount: int) -> str:
    """Format angka ke "Rp 8.500.000" (titik sebagai pemisah ribuan)."""
    return "Rp " + f"{amount:,}".replace(",", ".")


def _tw(draw, text, font) -> int:
    """Lebar teks dalam pixel."""
    bb = draw.textbbox((0, 0), text, font=font)
    return bb[2] - bb[0]


# ---------------------------------------------------------------------------
# Section drawing helpers
# ---------------------------------------------------------------------------

def _draw_header(draw, inv, f, M, W, y) -> int:
    draw.text((M, y), inv.nama_penjual, font=f["company"], fill="black")
    y += 22
    draw.text((M, y), "Solusi Teknologi Terpercaya untuk Bisnis Anda", font=f["small"], fill="#555")
    y += 15
    draw.text((M, y), inv.alamat_penjual, font=f["small"], fill="#333")
    y += 14
    return y


def _draw_title_bar(draw, f, y, M, W) -> int:
    draw.rectangle([(M, y), (W - M, y + 30)], fill="#2c3e50")
    label = "FAKTUR PAJAK"
    cx = (W - _tw(draw, label, f["title"])) // 2
    draw.text((cx, y + 7), label, font=f["title"], fill="white")
    return y + 30


def _draw_meta(draw, inv, f, y, M, W) -> int:
    """Dua kolom: No. Faktur dll (kiri) | NPWP Penjual dll (kanan)."""
    LW = 105  # lebar kolom label
    mid = W // 2 + 5

    left = [
        ("No. Faktur",  inv.nomor_faktur),
        ("Tanggal",     inv.tanggal),
        ("Jatuh Tempo", inv.jatuh_tempo),
    ]
    right = [
        ("NPWP Penjual",   inv.npwp_penjual),
        ("Alamat Penjual", inv.alamat_penjual),
    ]

    start_y = y
    for label, val in left:
        draw.text((M,      y), label, font=f["label"], fill="black")
        draw.text((M + LW, y), f": {val}", font=f["body"], fill="black")
        y += 18

    y = start_y
    for label, val in right:
        draw.text((mid,       y), label, font=f["label"], fill="black")
        draw.text((mid + LW,  y), f": {val}", font=f["body"], fill="black")
        y += 18

    return start_y + 18 * max(len(left), len(right)) + 6


def _draw_buyer(draw, inv, f, y, M) -> int:
    LW = 105
    rows = [
        ("Kepada Yth.",  inv.nama_pembeli),
        ("NPWP Pembeli", inv.npwp_pembeli),
        ("Alamat",       inv.alamat_pembeli),
    ]
    for label, val in rows:
        draw.text((M,      y), label, font=f["label"], fill="black")
        draw.text((M + LW, y), f": {val}", font=f["body"], fill="black")
        y += 18
    return y + 6


def _draw_table(draw, inv, f, y, M, W) -> int:
    """Tabel item dengan header gelap dan baris bergantian warna."""
    TW = W - 2 * M   # lebar total tabel = 750px

    # Kolom: (label, offset_x, lebar, align)
    cols = [
        ("No",               0,   30, "center"),
        ("Nama Barang/Jasa", 30, 270, "left"),
        ("Qty",             300,  40, "center"),
        ("Sat",             340,  48, "center"),
        ("Harga Satuan",    388, 165, "right"),
        ("Jumlah",          553, TW - 553, "right"),
    ]

    HDR_H = 24
    ROW_H = 20
    table_top = y

    # --- Header row ---
    draw.rectangle([(M, y), (W - M, y + HDR_H)], fill="#2c3e50")
    for label, ox, cw, align in cols:
        tx = _align_x(draw, label, f["label"], M + ox, cw, align)
        draw.text((tx, y + 5), label, font=f["label"], fill="white")
    y += HDR_H
    hdr_bottom = y

    # --- Data rows ---
    for idx, item in enumerate(inv.items):
        bg = "#f0f4f8" if idx % 2 == 0 else "white"
        draw.rectangle([(M, y), (W - M, y + ROW_H)], fill=bg)

        row_vals = [
            (str(item.nomor),                  cols[0]),
            (item.deskripsi[:36],              cols[1]),
            (str(item.kuantitas),              cols[2]),
            (item.satuan,                      cols[3]),
            (_rp(item.harga_satuan),           cols[4]),
            (_rp(item.total_harga),            cols[5]),
        ]
        for val, (_, ox, cw, align) in row_vals:
            tx = _align_x(draw, val, f["body"], M + ox, cw, align)
            draw.text((tx, y + 3), val, font=f["body"], fill="black")
        y += ROW_H

    table_bottom = y

    # --- Garis pembatas ---
    draw.rectangle([(M, table_top), (W - M, table_bottom)], outline="#888", width=1)
    draw.line([(M, hdr_bottom), (W - M, hdr_bottom)], fill="#888", width=1)
    for _, ox, _, _ in cols[1:]:   # garis vertikal pemisah kolom
        x = M + ox
        draw.line([(x, table_top), (x, table_bottom)], fill="#ccc", width=1)

    return y


def _draw_totals(draw, inv, f, y, M, W) -> int:
    """Blok total di sisi kanan dokumen."""
    COL_L = W - M - 310
    COL_V = W - M

    rows = [
        ("Subtotal",      inv.subtotal, False),
        ("Diskon (0%)",   0,            False),
        ("DPP",           inv.subtotal, False),
        ("PPN (11%)",     inv.ppn,      False),
        ("PPnBM (0%)",    0,            False),
        ("TOTAL TAGIHAN", inv.total,    True),
    ]

    for label, amount, bold in rows:
        fn = f["label"] if bold else f["body"]
        if bold:
            draw.line([(COL_L - 5, y), (W - M, y)], fill="black", width=1)
            y += 3
        val = _rp(amount)
        draw.text((COL_L, y), label, font=fn, fill="black")
        tw = _tw(draw, val, fn)
        draw.text((COL_V - tw - 2, y), val, font=fn, fill="black")
        y += 20

    return y + 4


def _draw_terbilang(draw, inv, f, y, M) -> int:
    draw.text((M,       y), "Terbilang", font=f["label"], fill="black")
    draw.text((M + 80,  y), f": {inv.terbilang} Rupiah", font=f["body"], fill="black")
    return y + 20


def _draw_signature(draw, f, y, M, W):
    BOX_W, BOX_H = 170, 70
    for x, label in [(M + 30, "Pembuat Faktur"), (W - M - BOX_W - 30, "Penerima")]:
        draw.rectangle([(x, y), (x + BOX_W, y + BOX_H)], outline="#999", width=1)
        tw = _tw(draw, label, f["label"])
        draw.text((x + (BOX_W - tw) // 2, y + BOX_H + 4), label, font=f["label"], fill="black")


def _align_x(draw, text, font, col_x, col_w, align) -> int:
    tw = _tw(draw, text, font)
    if align == "center":
        return col_x + (col_w - tw) // 2
    if align == "right":
        return col_x + col_w - tw - 4
    return col_x + 4   # left
