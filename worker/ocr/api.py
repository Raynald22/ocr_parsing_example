"""OCR Service — HTTP API (lapisan interface). Lihat docs/ocr-service-contract.md.

Stateless: terima referensi file (S3/MinIO) -> proses (pipeline) -> publish hasil
ke RabbitMQ. TIDAK menyimpan ke DB (Data Service yang persist). Redis hanya cache
status (TTL) untuk endpoint poll.

Jalankan:  python -m ocr        (atau: uvicorn ocr.api:app --port 8092)
"""

import asyncio
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from minio.error import S3Error
from pydantic import BaseModel

from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import jobstore, storage
from .config import MINIO_BUCKET
from .pipeline import process_document
from .publisher import publish_event

app = FastAPI(title="OCR Service", version="1.0")


# --- Envelope ---------------------------------------------------------------

def _now():
    return datetime.now().astimezone().isoformat()


def ok(data, message="OK", status_code=200, meta=None):
    m = {"timestamp": _now()}
    if meta:
        m.update(meta)
    return JSONResponse(status_code=status_code,
                        content={"success": True, "message": message, "data": data,
                                 "error": None, "meta": m})


def _err_body(code, message):
    return {"success": False, "message": message, "data": None,
            "error": {"code": code, "message": message}, "meta": {"timestamp": _now()}}


_ERR_CODES = {400: "BAD_REQUEST", 404: "NOT_FOUND", 415: "UNSUPPORTED_TYPE",
              422: "VALIDATION_ERROR"}


@app.exception_handler(StarletteHTTPException)
async def _on_http_exc(request: Request, exc: StarletteHTTPException):
    return JSONResponse(status_code=exc.status_code,
                        content=_err_body(_ERR_CODES.get(exc.status_code, "ERROR"), str(exc.detail)))


@app.exception_handler(RequestValidationError)
async def _on_validation(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content=_err_body("VALIDATION_ERROR", "request tidak valid"))


@app.exception_handler(Exception)
async def _on_unhandled(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content=_err_body("INTERNAL_ERROR", str(exc)))


@app.on_event("shutdown")
async def _shutdown():
    await jobstore.close()


# --- Schema request ---------------------------------------------------------

class FileRef(BaseModel):
    bucket: str
    key: str


class Options(BaseModel):
    document_type: Optional[str] = None
    force_ocr: bool = False
    callback_url: Optional[str] = None


class JobRequest(BaseModel):
    job_id: str
    file: FileRef
    options: Options = Options()


def _to_contract(result: dict) -> dict:
    """Bentuk hasil sesuai kontrak: buang blok debug `raw`."""
    return {k: v for k, v in result.items() if k != "raw"}


async def _webhook(url: str, message: dict):
    def _post():
        import requests
        requests.post(url, json=message, timeout=15)
    try:
        await run_in_threadpool(_post)
    except Exception as e:
        print(f"[OCR Service] webhook gagal: {type(e).__name__}: {e}")


# --- Pemrosesan (background) -------------------------------------------------

async def _process(req: JobRequest):
    job_id = req.job_id
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=Path(req.file.key).suffix)
    tmp.close()
    try:
        await jobstore.set_state(job_id, {"job_id": job_id, "status": "processing"})
        try:
            await run_in_threadpool(storage.fetch, req.file.bucket, req.file.key, tmp.name)
        except S3Error as e:
            raise FileNotFoundError(f"objek S3 tidak ditemukan: {req.file.bucket}/{req.file.key} ({e.code})")

        result = await run_in_threadpool(process_document, tmp.name)
        payload = _to_contract(result)

        await jobstore.set_state(job_id, {"job_id": job_id, "status": "completed", "result": payload})
        await publish_event("ocr.completed", job_id, {"result": payload})
        if req.options.callback_url:
            await _webhook(req.options.callback_url,
                           {"event": "ocr.completed", "job_id": job_id,
                            "timestamp": _now(), "result": payload})
    except Exception as e:
        code = "FILE_NOT_FOUND" if isinstance(e, FileNotFoundError) else "OCR_FAILED"
        err = {"code": code, "message": f"{type(e).__name__}: {e}"}
        await jobstore.set_state(job_id, {"job_id": job_id, "status": "failed", "error": err})
        await publish_event("ocr.failed", job_id, {"error": err})
        if req.options.callback_url:
            await _webhook(req.options.callback_url,
                           {"event": "ocr.failed", "job_id": job_id, "timestamp": _now(), "error": err})
        print(f"[OCR Service] job {job_id} failed: {err['message']}")
    finally:
        Path(tmp.name).unlink(missing_ok=True)


# --- Endpoint ---------------------------------------------------------------

@app.get("/api/v1/health")
async def health():
    services, healthy = {}, True
    try:
        await jobstore.ping()
        services["redis"] = {"status": "ok"}
    except Exception as e:
        services["redis"] = {"status": "down", "error": str(e)}
        healthy = False
    try:
        await run_in_threadpool(storage.bucket_exists, MINIO_BUCKET)
        services["minio"] = {"status": "ok"}
    except Exception as e:
        services["minio"] = {"status": "down", "error": str(e)}
        healthy = False
    return ok({"services": services}, "healthy" if healthy else "degraded",
              status_code=200 if healthy else 503)


@app.post("/api/v1/ocr/jobs")
async def submit(req: JobRequest):
    await jobstore.set_state(req.job_id, {"job_id": req.job_id, "status": "accepted"})
    asyncio.create_task(_process(req))
    return ok({"job_id": req.job_id, "status": "accepted"}, "job diterima", status_code=202)


@app.get("/api/v1/ocr/jobs/{job_id}")
async def job_status(job_id: str):
    state = await jobstore.get_state(job_id)
    if not state:
        raise HTTPException(404, "job tidak ditemukan / kedaluwarsa")
    return ok({"job_id": job_id, "status": state["status"],
               **({"error": state["error"]} if state.get("error") else {})})


@app.get("/api/v1/ocr/jobs/{job_id}/result")
async def job_result(job_id: str):
    state = await jobstore.get_state(job_id)
    if not state:
        raise HTTPException(404, "job tidak ditemukan / kedaluwarsa")
    if state["status"] != "completed":
        return ok({"job_id": job_id, "status": state["status"]}, "belum selesai", status_code=202)
    return ok(state["result"])
