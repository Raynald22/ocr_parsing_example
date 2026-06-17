"""
api.py
======
FastAPI server untuk React UI.

Cara menjalankan:
    python api.py
    # atau:
    uvicorn api:app --port 5000 --reload

Endpoints:
    GET  /api/status           — cek apakah output/ sudah ada
    GET  /api/ground-truth     — data faktur asli (ground_truth.json)
    GET  /api/results          — skor akurasi (results.json)
    GET  /api/ocr              — teks OCR raw + preprocessed
    GET  /images/{filename}    — file gambar dari folder output/
    POST /api/run              — jalankan pipeline (body: {"seed": 42})
    POST /api/upload           — upload + proses dokumen/gambar
    GET  /api/upload-result    — ambil hasil upload terakhir
    POST /api/parse-csv        — parse CSV faktur tanpa OCR
    GET  /api/csv-template     — download template CSV kosong
    GET  /docs                 — Swagger UI (auto-generated)
"""

import dataclasses
import subprocess
import sys
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response

app = FastAPI(title="OCR Parse API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

OUTPUT = Path(__file__).parent / "output"

_IMG_MIME = {
    ".png":  "image/png",
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".bmp":  "image/bmp",
    ".webp": "image/webp",
    ".tiff": "image/tiff",
    ".tif":  "image/tiff",
}


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

@app.get("/api/status")
def status():
    ready = (
        (OUTPUT / "ground_truth.json").exists()
        and (OUTPUT / "results.json").exists()
    )
    files = [f.name for f in OUTPUT.glob("*")] if OUTPUT.exists() else []
    return {"ready": ready, "files": files}


# ---------------------------------------------------------------------------
# Data endpoints
# ---------------------------------------------------------------------------

@app.get("/api/ground-truth")
def ground_truth():
    path = OUTPUT / "ground_truth.json"
    if not path.exists():
        raise HTTPException(404, detail="Belum ada data. Jalankan pipeline terlebih dahulu.")
    return FileResponse(path, media_type="application/json")


@app.get("/api/results")
def results():
    path = OUTPUT / "results.json"
    if not path.exists():
        raise HTTPException(404, detail="Belum ada hasil. Jalankan pipeline terlebih dahulu.")
    return FileResponse(path, media_type="application/json")


@app.get("/api/ocr")
def ocr():
    raw_path  = OUTPUT / "ocr_raw.txt"
    prep_path = OUTPUT / "ocr_preprocessed.txt"
    raw  = raw_path.read_text(encoding="utf-8")  if raw_path.exists()  else ""
    prep = prep_path.read_text(encoding="utf-8") if prep_path.exists() else ""
    return {"raw": raw, "preprocessed": prep}


# ---------------------------------------------------------------------------
# Image serving
# ---------------------------------------------------------------------------

@app.get("/images/{filename}")
def image(filename: str):
    path = OUTPUT / filename
    mime = _IMG_MIME.get(path.suffix.lower())
    if not path.exists() or not mime:
        raise HTTPException(404, detail="File tidak ditemukan")
    return FileResponse(path, media_type=mime)


# ---------------------------------------------------------------------------
# Jalankan pipeline
# ---------------------------------------------------------------------------

@app.post("/api/run")
async def run(data: dict = {}):
    seed = int(data.get("seed", 42))
    result = await run_in_threadpool(
        subprocess.run,
        [sys.executable, "main.py", "--seed", str(seed)],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent,
    )
    return {
        "success": result.returncode == 0,
        "stdout":  result.stdout,
        "stderr":  result.stderr,
    }


# ---------------------------------------------------------------------------
# Upload dokumen
# ---------------------------------------------------------------------------

UPLOAD_RESULT = OUTPUT / "upload_result.json"
MAX_UPLOAD_MB = 20


@app.post("/api/upload")
async def upload(
    file: UploadFile = File(...),
    csv:  Optional[UploadFile] = File(None),
):
    if not file.filename:
        raise HTTPException(400, detail="Nama file kosong.")

    contents = await file.read()
    if len(contents) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, detail=f"File terlalu besar (maks {MAX_UPLOAD_MB} MB).")

    suffix    = Path(file.filename).suffix.lower()
    temp_path = OUTPUT / f"upload_temp{suffix}"
    csv_temp  = None
    OUTPUT.mkdir(exist_ok=True)
    temp_path.write_bytes(contents)

    if csv and csv.filename:
        csv_temp = OUTPUT / "upload_gt_temp.csv"
        csv_temp.write_bytes(await csv.read())

    try:
        from src.upload_processor import SUPPORTED_DOCLING, process_with_docling

        if suffix not in SUPPORTED_DOCLING:
            raise HTTPException(400, detail=f"Format '{suffix}' tidak didukung.")

        # run_in_threadpool: Docling + Qwen jalan di thread pool
        # → server tetap bisa terima request lain selama proses berjalan
        result = await run_in_threadpool(
            process_with_docling,
            str(temp_path),
            str(csv_temp) if csv_temp else None,
        )
        return dataclasses.asdict(result)

    except HTTPException:
        raise
    except ImportError as e:
        raise HTTPException(503, detail=str(e))
    except ValueError as e:
        raise HTTPException(400, detail=str(e))
    except Exception as e:
        raise HTTPException(500, detail=f"Gagal memproses: {e}")
    finally:
        if temp_path.exists():
            temp_path.unlink()
        if csv_temp and csv_temp.exists():
            csv_temp.unlink()


@app.get("/api/upload-result")
def upload_result():
    if not UPLOAD_RESULT.exists():
        raise HTTPException(404, detail="Belum ada upload. Upload file terlebih dahulu.")
    return FileResponse(UPLOAD_RESULT, media_type="application/json")


# ---------------------------------------------------------------------------
# Parse CSV
# ---------------------------------------------------------------------------

@app.post("/api/parse-csv")
async def parse_csv(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(400, detail="Nama file kosong.")
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(400, detail="Hanya file .csv yang didukung di endpoint ini.")

    csv_temp = OUTPUT / "parse_csv_temp.csv"
    OUTPUT.mkdir(exist_ok=True)
    csv_temp.write_bytes(await file.read())

    try:
        from src.upload_processor import process_csv_only
        result = await run_in_threadpool(process_csv_only, str(csv_temp))
        return dataclasses.asdict(result)
    except Exception as e:
        raise HTTPException(500, detail=f"Gagal memproses CSV: {e}")
    finally:
        if csv_temp.exists():
            csv_temp.unlink()


@app.get("/api/csv-template")
def csv_template():
    from src.upload_processor import CSV_TEMPLATE
    return Response(
        content=CSV_TEMPLATE,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=ground_truth_template.csv"},
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    print("  API server berjalan di http://localhost:5000")
    print("  Swagger docs  →  http://localhost:5000/docs")
    print("  Tekan Ctrl+C untuk berhenti\n")
    uvicorn.run("api:app", host="0.0.0.0", port=5000, reload=True)
