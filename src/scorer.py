"""
scorer.py
=========
Hitung akurasi OCR + parsing dengan dua metrik:

1. CER (Character Error Rate)
   = levenshtein_distance(referensi, hipotesis) / len(referensi)
   Metrik standar industri untuk evaluasi OCR.
   CER 0.0 = sempurna, CER 1.0 = semua karakter salah.
   → Character Accuracy = 1.0 - CER

2. Field Exact Match Rate
   = jumlah field yang tepat sama persis / total field
   Lebih ketat dari CER: salah satu karakter pun = tidak match.

Target: Character Accuracy ≥ 95%
"""

from dataclasses import dataclass, field
from typing import List, Optional

from src.invoice_generator import InvoiceData
from src.parser import ParsedInvoice

TARGET_ACCURACY = 0.95


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class FieldScore:
    field_name:  str
    expected:    str
    got:         str    # kosong jika field tidak ditemukan
    cer:         float  # 0.0 = sempurna, > 0.0 = ada error
    exact_match: bool


@dataclass
class InvoiceScore:
    field_scores:      List[FieldScore]
    overall_cer:       float   # rata-rata CER semua field
    char_accuracy:     float   # 1.0 - overall_cer (clipped ke [0, 1])
    exact_match_rate:  float   # proporsi field yang exact match
    items_expected:    int
    items_found:       int
    item_accuracy:     float   # items_found / items_expected
    passes_threshold:  bool    # char_accuracy >= TARGET_ACCURACY


# ---------------------------------------------------------------------------
# Fungsi utama
# ---------------------------------------------------------------------------

def score_invoice(ground_truth: InvoiceData, parsed: ParsedInvoice) -> InvoiceScore:
    """
    Bandingkan ground truth dengan hasil parsing dan hitung skor akurasi.

    Field yang dibandingkan:
      - nomor_faktur, tanggal, jatuh_tempo
      - nama_penjual, npwp_penjual
      - nama_pembeli, npwp_pembeli, alamat_pembeli
      - subtotal, ppn, total (dibandingkan sebagai string angka)

    Args:
        ground_truth: Data faktur asli (dibuat oleh invoice_generator)
        parsed:       Hasil parsing dari OCR

    Returns:
        InvoiceScore dengan detail per field dan skor keseluruhan
    """
    pairs = [
        ("nomor_faktur",   ground_truth.nomor_faktur,    parsed.nomor_faktur),
        ("tanggal",        ground_truth.tanggal,          parsed.tanggal),
        ("jatuh_tempo",    ground_truth.jatuh_tempo,      parsed.jatuh_tempo),
        ("nama_penjual",   ground_truth.nama_penjual,     parsed.nama_penjual),
        ("npwp_penjual",   ground_truth.npwp_penjual,     parsed.npwp_penjual),
        ("nama_pembeli",   ground_truth.nama_pembeli,     parsed.nama_pembeli),
        ("npwp_pembeli",   ground_truth.npwp_pembeli,     parsed.npwp_pembeli),
        ("alamat_pembeli", ground_truth.alamat_pembeli,   parsed.alamat_pembeli),
        ("subtotal",       str(ground_truth.subtotal),    _int_str(parsed.subtotal)),
        ("ppn",            str(ground_truth.ppn),         _int_str(parsed.ppn)),
        ("total",          str(ground_truth.total),       _int_str(parsed.total)),
    ]

    scores = [_score_field(name, exp, got) for name, exp, got in pairs]

    cers          = [s.cer for s in scores]
    overall_cer   = sum(cers) / len(cers) if cers else 1.0
    char_accuracy = max(0.0, 1.0 - overall_cer)
    exact_rate    = sum(1 for s in scores if s.exact_match) / len(scores)

    items_found   = len(parsed.items)
    items_expected = len(ground_truth.items)
    item_accuracy = items_found / items_expected if items_expected else 0.0

    return InvoiceScore(
        field_scores=scores,
        overall_cer=overall_cer,
        char_accuracy=char_accuracy,
        exact_match_rate=exact_rate,
        items_expected=items_expected,
        items_found=items_found,
        item_accuracy=item_accuracy,
        passes_threshold=char_accuracy >= TARGET_ACCURACY,
    )


def print_score_report(score: InvoiceScore) -> None:
    """Tampilkan laporan akurasi detail per field."""
    print("\n  Laporan Akurasi:")
    print(f"  {'Field':<20} {'Expected':<28} {'Got':<28} {'CER':>6}  {'Status'}")
    print("  " + "-" * 92)

    for s in score.field_scores:
        exp_preview = s.expected[:26] + ".." if len(s.expected) > 26 else s.expected
        got_preview = s.got[:26]     + ".." if len(s.got)      > 26 else s.got
        status = "EXACT" if s.exact_match else (f"~{(1-s.cer)*100:.0f}%" if s.cer < 1.0 else "MISS")
        got_display = got_preview if s.got else "[tidak ditemukan]"
        print(f"  {s.field_name:<20} {exp_preview:<28} {got_display:<28} {s.cer:>6.3f}  {status}")

    print("  " + "-" * 92)
    print(f"  {'OVERALL':<20} {'':28} {'':28} {score.overall_cer:>6.3f}  "
          f"{score.char_accuracy:.1%}")
    print()
    print(f"  Item tabel  : {score.items_found}/{score.items_expected} "
          f"ditemukan ({score.item_accuracy:.0%})")
    print(f"  Exact match : {score.exact_match_rate:.0%} "
          f"({sum(1 for s in score.field_scores if s.exact_match)}/{len(score.field_scores)} field)")
    print()

    bar = _progress_bar(score.char_accuracy)
    status = "LULUS" if score.passes_threshold else "TIDAK LULUS"
    print(f"  Akurasi Karakter: {bar} {score.char_accuracy:.1%}  ->  {status} "
          f"(target >={TARGET_ACCURACY:.0%})")
    print()


def score_to_dict(score: InvoiceScore) -> dict:
    """Konversi InvoiceScore ke dict untuk disimpan sebagai JSON."""
    return {
        "char_accuracy":     round(score.char_accuracy, 4),
        "overall_cer":       round(score.overall_cer, 4),
        "exact_match_rate":  round(score.exact_match_rate, 4),
        "item_accuracy":     round(score.item_accuracy, 4),
        "passes_threshold":  score.passes_threshold,
        "target":            TARGET_ACCURACY,
        "fields": [
            {
                "field":       s.field_name,
                "expected":    s.expected,
                "got":         s.got,
                "cer":         round(s.cer, 4),
                "exact_match": s.exact_match,
            }
            for s in score.field_scores
        ],
    }


# ---------------------------------------------------------------------------
# Internal: Levenshtein + scoring
# ---------------------------------------------------------------------------

def _score_field(name: str, expected: str, got: Optional[str]) -> FieldScore:
    exp = _normalize(expected)
    hyp = _normalize(got or "")
    cer = _cer(exp, hyp)
    return FieldScore(
        field_name=name,
        expected=expected,
        got=got or "",
        cer=cer,
        exact_match=(exp == hyp),
    )


def _cer(reference: str, hypothesis: str) -> float:
    """
    Character Error Rate = edit_distance / len(reference)
    Menggunakan algoritma Wagner-Fischer (dynamic programming).
    """
    if not reference:
        return 0.0 if not hypothesis else 1.0
    dist = _levenshtein(reference, hypothesis)
    return dist / len(reference)


def _levenshtein(s1: str, s2: str) -> int:
    """
    Hitung Levenshtein distance antara dua string.
    Kompleksitas: O(n * m) waktu, O(n) memori.

    Ini adalah algoritma Wagner-Fischer yang dioptimalkan dengan rolling array.
    """
    if s1 == s2:
        return 0
    if not s1:
        return len(s2)
    if not s2:
        return len(s1)

    # Gunakan array 1D untuk menghemat memori
    prev = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1, 1):
        curr = [i] + [0] * len(s2)
        for j, c2 in enumerate(s2, 1):
            if c1 == c2:
                curr[j] = prev[j - 1]
            else:
                curr[j] = 1 + min(prev[j], curr[j - 1], prev[j - 1])
        prev = curr

    return prev[-1]


def _normalize(s: str) -> str:
    """Lowercase + strip whitespace untuk perbandingan yang adil."""
    return s.lower().strip()


def _int_str(val: Optional[int]) -> Optional[str]:
    """Konversi int ke string, None tetap None."""
    return str(val) if val is not None else None


def _progress_bar(ratio: float, width: int = 20) -> str:
    filled = int(ratio * width)
    bar    = "#" * filled + "." * (width - filled)
    return f"[{bar}]"
