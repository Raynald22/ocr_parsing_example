"""
api.py
======
Flask API server untuk React UI.

Cara menjalankan:
    python api.py
    # Berjalan di http://localhost:5000

Endpoints:
    GET  /api/status           — cek apakah output/ sudah ada
    GET  /api/ground-truth     — data faktur asli (ground_truth.json)
    GET  /api/results          — skor akurasi (results.json)
    GET  /api/ocr              — teks OCR raw + preprocessed
    GET  /images/<filename>    — file gambar dari folder output/
    POST /api/run              — jalankan pipeline (body: {"seed": 42})
    POST /api/upload           — upload + proses dokumen gambar
    GET  /api/upload-result    — ambil hasil upload terakhir
"""

import dataclasses
import subprocess
import sys
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_file
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

OUTPUT = Path(__file__).parent / "output"


# ---------------------------------------------------------------------------
# Status: cek apakah output files sudah ada
# ---------------------------------------------------------------------------

@app.get("/api/status")
def status():
    ready = (
        (OUTPUT / "ground_truth.json").exists()
        and (OUTPUT / "results.json").exists()
    )
    files = [f.name for f in OUTPUT.glob("*")] if OUTPUT.exists() else []
    return jsonify({"ready": ready, "files": files})


# ---------------------------------------------------------------------------
# Data endpoints
# ---------------------------------------------------------------------------

@app.get("/api/ground-truth")
def ground_truth():
    path = OUTPUT / "ground_truth.json"
    if not path.exists():
        return jsonify({"error": "Belum ada data. Jalankan pipeline terlebih dahulu."}), 404
    return send_file(path, mimetype="application/json")


@app.get("/api/results")
def results():
    path = OUTPUT / "results.json"
    if not path.exists():
        return jsonify({"error": "Belum ada hasil. Jalankan pipeline terlebih dahulu."}), 404
    return send_file(path, mimetype="application/json")


@app.get("/api/ocr")
def ocr():
    raw_path  = OUTPUT / "ocr_raw.txt"
    prep_path = OUTPUT / "ocr_preprocessed.txt"

    raw  = raw_path.read_text(encoding="utf-8")  if raw_path.exists()  else ""
    prep = prep_path.read_text(encoding="utf-8") if prep_path.exists() else ""

    return jsonify({"raw": raw, "preprocessed": prep})


# ---------------------------------------------------------------------------
# Image serving
# ---------------------------------------------------------------------------

@app.get("/images/<filename>")
def image(filename):
    # Hanya izinkan file PNG dari folder output/ (keamanan dasar)
    path = OUTPUT / filename
    if not path.exists() or path.suffix.lower() != ".png":
        return jsonify({"error": "File tidak ditemukan"}), 404
    return send_file(path, mimetype="image/png")


# ---------------------------------------------------------------------------
# Jalankan pipeline
# ---------------------------------------------------------------------------

@app.post("/api/run")
def run():
    data  = request.get_json(silent=True) or {}
    seed  = int(data.get("seed", 42))

    result = subprocess.run(
        [sys.executable, "main.py", "--seed", str(seed)],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent,
    )

    return jsonify({
        "success": result.returncode == 0,
        "stdout":  result.stdout,
        "stderr":  result.stderr,
    })


# ---------------------------------------------------------------------------
# Upload dokumen
# ---------------------------------------------------------------------------

UPLOAD_RESULT = OUTPUT / "upload_result.json"
MAX_UPLOAD_MB = 20

@app.post("/api/upload")
def upload():
    if "file" not in request.files:
        return jsonify({"error": "Tidak ada file dalam request."}), 400

    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "Nama file kosong."}), 400

    # Cek ukuran (stream belum dibaca, cek lewat Content-Length header)
    content_length = request.content_length
    if content_length and content_length > MAX_UPLOAD_MB * 1024 * 1024:
        return jsonify({"error": f"File terlalu besar (maks {MAX_UPLOAD_MB} MB)."}), 413

    suffix = Path(file.filename).suffix.lower()
    temp_path = OUTPUT / f"upload_temp{suffix}"
    csv_temp  = None
    OUTPUT.mkdir(exist_ok=True)
    file.save(temp_path)

    # CSV ground truth opsional
    if "csv" in request.files and request.files["csv"].filename:
        csv_temp = OUTPUT / "upload_gt_temp.csv"
        request.files["csv"].save(csv_temp)

    try:
        # Import di sini agar tidak crash saat Tesseract belum terinstall
        # (endpoint lain tetap bisa diakses)
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).parent))
        from src.upload_processor import process_uploaded

        result = process_uploaded(
            str(temp_path),
            csv_path=str(csv_temp) if csv_temp else None,
        )
        return jsonify(dataclasses.asdict(result))

    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        msg = str(e)
        # Deteksi Tesseract tidak terinstall
        if "tesseract" in msg.lower() and ("not installed" in msg.lower() or "path" in msg.lower()):
            return jsonify({
                "error": (
                    "Tesseract OCR belum terinstall. "
                    "Download dari: https://github.com/UB-Mannheim/tesseract/wiki "
                    "dan install, lalu restart python api.py."
                )
            }), 503
        return jsonify({"error": f"Gagal memproses: {msg}"}), 500
    finally:
        if temp_path.exists():
            temp_path.unlink()
        if csv_temp and csv_temp.exists():
            csv_temp.unlink()


@app.get("/api/upload-result")
def upload_result():
    if not UPLOAD_RESULT.exists():
        return jsonify({"error": "Belum ada upload. Upload file terlebih dahulu."}), 404
    return send_file(UPLOAD_RESULT, mimetype="application/json")


@app.get("/api/csv-template")
def csv_template():
    """Download template CSV ground truth kosong untuk diisi user."""
    from src.upload_processor import CSV_TEMPLATE
    return Response(
        CSV_TEMPLATE,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=ground_truth_template.csv"},
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("  API server berjalan di http://localhost:5000")
    print("  Tekan Ctrl+C untuk berhenti\n")
    app.run(port=5000, debug=False)
