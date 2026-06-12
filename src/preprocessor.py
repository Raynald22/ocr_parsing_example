"""
preprocessor.py
===============
Pipeline 6-langkah untuk meningkatkan kualitas gambar sebelum OCR.

Mengapa preprocessing penting?
Tesseract bekerja terbaik dengan gambar:
  - Resolusi tinggi (300+ DPI equivalent)
  - Hitam-putih bersih (tidak ada noise)
  - Kontras tinggi

Setiap langkah di modul ini berkontribusi terhadap akurasi akhir OCR.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

try:
    import cv2
    _CV2 = True
except ImportError:
    _CV2 = False


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class PreprocessStep:
    name:        str
    description: str          # apa yang dilakukan langkah ini
    why:         str          # kenapa langkah ini meningkatkan akurasi
    image:       Image.Image  # gambar setelah langkah ini diterapkan


@dataclass
class PreprocessResult:
    original:        Image.Image
    final:           Image.Image
    steps:           List[PreprocessStep]
    scale_factor:    float
    otsu_threshold:  int      # threshold yang ditemukan algoritma Otsu


# ---------------------------------------------------------------------------
# Fungsi utama
# ---------------------------------------------------------------------------

def preprocess_for_ocr(
    image: Image.Image,
    scale_factor: float = 2.0,
    save_steps: bool = False,
    output_dir: Optional[str] = None,
) -> PreprocessResult:
    """
    Jalankan 6-langkah preprocessing pada gambar.

    Args:
        image:        Gambar input (PIL Image)
        scale_factor: Faktor perbesaran (default 2.0 = 2x lipat)
        save_steps:   Simpan setiap langkah ke file PNG jika True
        output_dir:   Direktori output untuk gambar langkah-langkah

    Returns:
        PreprocessResult berisi gambar final dan detail setiap langkah
    """
    steps: List[PreprocessStep] = []
    threshold = 128  # default jika fallback

    # Langkah 1: Upscale
    img = _step_upscale(image, scale_factor)
    steps.append(PreprocessStep(
        name="upscale",
        description=f"Perbesar gambar {scale_factor}x dengan interpolasi Lanczos",
        why="Tesseract akurat pada font ≥20px. Upscale mengubah font 13px → 26px.",
        image=img.copy(),
    ))

    # Langkah 2: Grayscale
    img = _step_grayscale(img)
    steps.append(PreprocessStep(
        name="grayscale",
        description="Konversi RGB → skala abu-abu (1 channel)",
        why="Warna tidak membawa info teks; mengurangi kompleksitas proses.",
        image=img.copy(),
    ))

    # Langkah 3: Tingkatkan kontras
    img = _step_enhance_contrast(img, factor=1.6)
    steps.append(PreprocessStep(
        name="contrast",
        description="Tingkatkan kontras 1.6x",
        why="Perkuat perbedaan tinta gelap vs kertas putih agar binarize lebih bersih.",
        image=img.copy(),
    ))

    # Langkah 4: Denoise (blur ringan)
    img = _step_denoise(img)
    steps.append(PreprocessStep(
        name="denoise",
        description="Gaussian blur ringan (radius 0.8)",
        why="Hilangkan noise kecil (piksel acak) sebelum binarisasi agar threshold lebih stabil.",
        image=img.copy(),
    ))

    # Langkah 5: Binarisasi Otsu
    img, threshold = _step_binarize(img)
    steps.append(PreprocessStep(
        name="binarize",
        description=f"Binarisasi Otsu (threshold otomatis = {threshold})",
        why="Tesseract bekerja optimal pada gambar hitam-putih murni, bukan grayscale.",
        image=img.copy(),
    ))

    # Langkah 6: Pertajam tepi
    img = _step_sharpen(img)
    steps.append(PreprocessStep(
        name="sharpen",
        description="Pertajam tepi karakter dengan kernel unsharp mask",
        why="Pulihkan ketajaman tepi yang sedikit melunak akibat blur di langkah 4.",
        image=img.copy(),
    ))

    if save_steps and output_dir:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        for i, step in enumerate(steps):
            step.image.save(out / f"step_{i+1:02d}_{step.name}.png")

    return PreprocessResult(
        original=image,
        final=img,
        steps=steps,
        scale_factor=scale_factor,
        otsu_threshold=threshold,
    )


def explain_preprocessing() -> None:
    """Tampilkan tabel penjelasan setiap langkah preprocessing."""
    rows = [
        ("1", "Upscale",   "Perbesar 2x",        "Font jadi cukup besar untuk dibaca Tesseract"),
        ("2", "Grayscale", "RGB -> abu-abu",      "Reduksi data yang tidak perlu"),
        ("3", "Contrast",  "Tingkatkan 1.6x",     "Tinta vs kertas makin kontras"),
        ("4", "Denoise",   "Gaussian blur 0.8",   "Bersihkan noise sebelum threshold"),
        ("5", "Binarize",  "Otsu threshold",       "Hitam-putih murni = input ideal"),
        ("6", "Sharpen",   "Unsharp mask",         "Pertegas tepi karakter"),
    ]
    print("\n  Preprocessing Pipeline:")
    print(f"  {'No':<4} {'Langkah':<12} {'Operasi':<22} {'Tujuan'}")
    print("  " + "-" * 72)
    for r in rows:
        print(f"  {r[0]:<4} {r[1]:<12} {r[2]:<22} {r[3]}")
    print()


# ---------------------------------------------------------------------------
# Implementasi setiap langkah
# ---------------------------------------------------------------------------

def _step_upscale(img: Image.Image, factor: float) -> Image.Image:
    new_w = int(img.width  * factor)
    new_h = int(img.height * factor)
    if _CV2:
        arr = np.array(img)
        arr = cv2.resize(arr, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)
        return Image.fromarray(arr)
    return img.resize((new_w, new_h), Image.LANCZOS)


def _step_grayscale(img: Image.Image) -> Image.Image:
    if _CV2:
        arr = np.array(img)
        if arr.ndim == 3:
            arr = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
        return Image.fromarray(arr)
    return img.convert("L")


def _step_enhance_contrast(img: Image.Image, factor: float = 1.6) -> Image.Image:
    if _CV2:
        arr = np.array(img)
        # convertScaleAbs: dst = alpha * src + beta, clip ke [0,255]
        arr = cv2.convertScaleAbs(arr, alpha=factor, beta=0)
        return Image.fromarray(arr)
    return ImageEnhance.Contrast(img).enhance(factor)


def _step_denoise(img: Image.Image) -> Image.Image:
    if _CV2:
        arr = np.array(img)
        arr = cv2.GaussianBlur(arr, (3, 3), sigmaX=0.8)
        return Image.fromarray(arr)
    return img.filter(ImageFilter.GaussianBlur(radius=0.8))


def _step_binarize(img: Image.Image) -> Tuple[Image.Image, int]:
    """Otsu's thresholding: otomatis cari nilai threshold terbaik."""
    arr = np.array(img)
    if arr.ndim == 3:
        arr = np.mean(arr, axis=2).astype(np.uint8)

    if _CV2:
        thresh_val, arr_bin = cv2.threshold(
            arr, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )
        return Image.fromarray(arr_bin), int(thresh_val)

    # Fallback: implementasi Otsu murni NumPy
    thresh_val = _otsu_threshold(arr)
    arr_bin = np.where(arr >= thresh_val, 255, 0).astype(np.uint8)
    return Image.fromarray(arr_bin), thresh_val


def _step_sharpen(img: Image.Image) -> Image.Image:
    if _CV2:
        arr = np.array(img)
        kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]], dtype=np.float32)
        arr = cv2.filter2D(arr, -1, kernel)
        return Image.fromarray(arr)
    return img.filter(ImageFilter.SHARPEN)


def _otsu_threshold(arr: np.ndarray) -> int:
    """
    Algoritma Otsu: cari threshold yang memaksimalkan variansi antar-kelas.
    O(256) - sangat cepat.
    """
    hist, _ = np.histogram(arr.flatten(), bins=256, range=(0, 256))
    total   = arr.size
    prob    = hist / total

    best_thresh = 0
    best_var    = 0.0
    w0 = mu0 = 0.0

    for t in range(256):
        w0  += prob[t]
        w1   = 1.0 - w0
        if w0 == 0 or w1 == 0:
            continue
        mu0 += t * prob[t]
        mu1  = (np.dot(np.arange(256), prob) - mu0) / w1
        m0   = mu0 / w0
        var  = w0 * w1 * (m0 - mu1) ** 2
        if var > best_var:
            best_var    = var
            best_thresh = t

    return best_thresh
