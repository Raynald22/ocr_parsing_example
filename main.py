"""
main.py — OCR + Parsing Learning Example
=========================================

Demo end-to-end pipeline OCR dan parsing faktur pajak Indonesia.

Cara menjalankan:
  python main.py            # seed default (42)
  python main.py --seed 7   # seed lain untuk data berbeda

Langkah-langkah yang ditampilkan:
  1. Generate invoice sintetik (gambar + ground truth)
  2. Preprocessing gambar (6 langkah untuk meningkatkan kualitas)
  3. OCR: bandingkan tanpa vs dengan preprocessing
  4. Parse teks OCR ke data terstruktur
  5. Hitung skor akurasi (target ≥ 95%)
"""

import argparse
import dataclasses
import json
import sys
from pathlib import Path

# Pastikan src/ bisa diimport dari direktori ini
sys.path.insert(0, str(Path(__file__).parent))

from src.invoice_generator import create_sample_invoice, generate_invoice_image
from src.ocr               import configure_tesseract, run_ocr_with_confidence, compare_ocr_results
from src.parser            import parse_invoice, display_parsed_invoice
from src.preprocessor      import preprocess_for_ocr, explain_preprocessing
from src.scorer            import score_invoice, print_score_report, score_to_dict, TARGET_ACCURACY

OUTPUT_DIR = Path(__file__).parent / "output"


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main(seed: int = 42) -> int:
    """
    Jalankan pipeline lengkap.
    Return 0 jika akurasi ≥ 95%, 1 jika tidak.
    """
    OUTPUT_DIR.mkdir(exist_ok=True)

    _banner()

    # ------------------------------------------------------------------
    # Langkah 0: Setup Tesseract
    # ------------------------------------------------------------------
    print("  Menyiapkan Tesseract OCR...")
    try:
        configure_tesseract()
    except (RuntimeError, ImportError) as e:
        print(f"\n{e}")
        return 1

    from src.ocr import get_tesseract_version
    print(f"  Tesseract versi: {get_tesseract_version()}\n")

    # ------------------------------------------------------------------
    # Langkah 1: Generate faktur sintetik
    # ------------------------------------------------------------------
    _step(1, "GENERATE FAKTUR SINTETIK")
    print(f"  Seed: {seed}  (ubah dengan --seed untuk data berbeda)")

    invoice = create_sample_invoice(seed=seed)
    img_path = str(OUTPUT_DIR / "invoice_original.png")
    image = generate_invoice_image(invoice, output_path=img_path)

    print(f"  Gambar     : {img_path}")
    print(f"  Ukuran     : {image.width} x {image.height} px")
    print(f"  No. Faktur : {invoice.nomor_faktur}")
    print(f"  Tanggal    : {invoice.tanggal}")
    print(f"  Penjual    : {invoice.nama_penjual}")
    print(f"  Pembeli    : {invoice.nama_pembeli}")
    print(f"  Jumlah item: {len(invoice.items)}")
    print(f"  Total      : Rp {invoice.total:,}".replace(",", "."))
    print(f"  Terbilang  : {invoice.terbilang} Rupiah\n")

    # Simpan ground truth
    gt_path = OUTPUT_DIR / "ground_truth.json"
    gt_path.write_text(
        json.dumps(dataclasses.asdict(invoice), indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    print(f"  Ground truth disimpan ke: {gt_path}\n")

    # ------------------------------------------------------------------
    # Langkah 2: Preprocessing
    # ------------------------------------------------------------------
    _step(2, "PREPROCESSING GAMBAR")
    explain_preprocessing()

    prep = preprocess_for_ocr(
        image,
        scale_factor=2.0,
        save_steps=True,
        output_dir=str(OUTPUT_DIR),
    )
    print(f"  Gambar asli  : {image.width} x {image.height} px (RGB)")
    print(f"  Gambar final : {prep.final.width} x {prep.final.height} px ({prep.final.mode})")
    print(f"  Threshold Otsu: {prep.otsu_threshold}")
    print(f"  Gambar setiap langkah disimpan ke: output/step_0N_*.png\n")

    # ------------------------------------------------------------------
    # Langkah 3: OCR
    # ------------------------------------------------------------------
    _step(3, "OPTICAL CHARACTER RECOGNITION")
    print("  Menjalankan OCR... (ini mungkin butuh beberapa detik)")

    ocr_raw  = run_ocr_with_confidence(image)          # tanpa preprocessing
    ocr_prep = run_ocr_with_confidence(prep.final)     # dengan preprocessing

    compare_ocr_results(ocr_raw, ocr_prep)

    # Simpan teks OCR untuk inspeksi
    (OUTPUT_DIR / "ocr_raw.txt").write_text(ocr_raw.text, encoding="utf-8")
    (OUTPUT_DIR / "ocr_preprocessed.txt").write_text(ocr_prep.text, encoding="utf-8")
    print(f"  Teks OCR disimpan ke output/ocr_raw.txt dan ocr_preprocessed.txt\n")

    # ------------------------------------------------------------------
    # Langkah 4: Parsing
    # ------------------------------------------------------------------
    _step(4, "PARSE TEKS KE DATA TERSTRUKTUR")
    parsed = parse_invoice(ocr_prep.text)
    display_parsed_invoice(parsed)

    # ------------------------------------------------------------------
    # Langkah 5: Scoring
    # ------------------------------------------------------------------
    _step(5, "HITUNG SKOR AKURASI")
    score = score_invoice(invoice, parsed)
    print_score_report(score)

    # Simpan hasil
    results_path = OUTPUT_DIR / "results.json"
    results_path.write_text(
        json.dumps(score_to_dict(score), indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    print(f"  Hasil lengkap disimpan ke: {results_path}")

    # ------------------------------------------------------------------
    # Ringkasan akhir
    # ------------------------------------------------------------------
    print()
    print("  " + "=" * 60)
    status = "LULUS" if score.passes_threshold else "TIDAK LULUS"
    print(f"  HASIL AKHIR: {score.char_accuracy:.1%} akurasi karakter  ->  {status}")
    print(f"               (target minimum: {TARGET_ACCURACY:.0%})")
    print("  " + "=" * 60)
    print()
    print("  Output files:")
    print(f"    output/invoice_original.png  → gambar faktur asli")
    print(f"    output/step_0N_*.png         → setiap langkah preprocessing")
    print(f"    output/ocr_raw.txt           → teks OCR tanpa preprocessing")
    print(f"    output/ocr_preprocessed.txt  → teks OCR dengan preprocessing")
    print(f"    output/ground_truth.json     → data faktur sesungguhnya")
    print(f"    output/results.json          → skor akurasi detail")
    print()

    return 0 if score.passes_threshold else 1


# ---------------------------------------------------------------------------
# UI helpers
# ---------------------------------------------------------------------------

def _banner():
    print()
    print("  =" * 30)
    print("  OCR + Parsing - Faktur Pajak Indonesia")
    print("  Contoh Pembelajaran Python")
    print("  =" * 30)
    print()


def _step(n: int, title: str):
    print(f"  --- Langkah {n}: {title} ---")
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Demo OCR dan parsing faktur pajak Indonesia."
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="Seed untuk data faktur (default: 42)"
    )
    args = parser.parse_args()
    sys.exit(main(seed=args.seed))
