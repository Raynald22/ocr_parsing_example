"""FastAPI API — pengganti gateway Go (Fiber).

Semua endpoint HTTP membungkus respons dalam envelope seragam:
    {success, message, data, error, meta}
Error juga seragam lewat exception handler (error.code + error.message).

  - POST /api/upload            -> upload ke MinIO, INSERT job, XADD Redis Stream
  - GET  /api/jobs?page&per_page-> daftar job (paginated, meta.page/per_page/total)
  - GET  /api/jobs/{id}         -> status job
  - GET  /api/jobs/{id}/result  -> hasil bersih (tanpa blok debug `raw`)
  - GET  /api/jobs/{id}/raw     -> data mentah/debug (extracted_text, tables, score lama)
  - GET  /api/health            -> cek redis/minio/postgres
  - WS   /ws/jobs/{id}          -> relay status dari Redis Pub/Sub (stream, tanpa envelope)

Redis = antrian + pub/sub, MinIO = file, Postgres = job & hasil.
"""

import io
import json
import os
import uuid
from datetime import datetime

import psycopg2
import redis.asyncio as aioredis
from psycopg2.pool import SimpleConnectionPool
from minio import Minio

from fastapi import FastAPI, File, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from ocr.config import (
    DATABASE_URL, MINIO_ACCESS, MINIO_BUCKET, MINIO_ENDPOINT, MINIO_SECRET,
    REDIS_HOST, REDIS_PORT,
)

MAX_BYTES = 20 * 1024 * 1024
STREAM_PREFIX = "doc_jobs"

pg_pool: SimpleConnectionPool = None
rds: aioredis.Redis = None
minio_client: Minio = None

app = FastAPI(title="OCR Parse API")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


# --- Response envelope: semua endpoint balas {success, message, data, error, meta} ---

_ERR_CODES = {400: "BAD_REQUEST", 404: "NOT_FOUND", 413: "PAYLOAD_TOO_LARGE",
              422: "VALIDATION_ERROR", 503: "SERVICE_UNAVAILABLE"}


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


# --- Postgres helpers (sync, dijalankan di threadpool) ---------------------

def _db_exec(query, params):
    conn = pg_pool.getconn()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(query, params)
    finally:
        pg_pool.putconn(conn)


def _db_fetchone(query, params):
    conn = pg_pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchone()
    finally:
        pg_pool.putconn(conn)


def _db_fetchall(query, params):
    conn = pg_pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchall()
    finally:
        pg_pool.putconn(conn)


def _minio_put(key, data: bytes, content_type: str):
    minio_client.put_object(MINIO_BUCKET, key, io.BytesIO(data), len(data),
                            content_type=content_type or "application/octet-stream")


def _iso(v):
    return v.isoformat() if v is not None else None


# --- Lifecycle -------------------------------------------------------------

@app.on_event("startup")
async def _startup():
    global pg_pool, rds, minio_client
    pg_pool = SimpleConnectionPool(1, 10, dsn=DATABASE_URL.replace("postgres://", "postgresql://"))
    rds = aioredis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    minio_client = Minio(MINIO_ENDPOINT, access_key=MINIO_ACCESS, secret_key=MINIO_SECRET, secure=False)
    if not minio_client.bucket_exists(MINIO_BUCKET):
        minio_client.make_bucket(MINIO_BUCKET)
    print(f"[API] up | redis={REDIS_HOST}:{REDIS_PORT} bucket={MINIO_BUCKET}")


@app.on_event("shutdown")
async def _shutdown():
    if rds:
        await rds.aclose()
    if pg_pool:
        pg_pool.closeall()


# --- Endpoints -------------------------------------------------------------

@app.get("/api/health")
async def health():
    services, healthy = {}, True
    try:
        await rds.ping()
        services["redis"] = {"status": "ok"}
    except Exception as e:
        services["redis"] = {"status": "down", "error": str(e)}
        healthy = False
    try:
        exists = await run_in_threadpool(minio_client.bucket_exists, MINIO_BUCKET)
        services["minio"] = {"status": "ok"} if exists else {"status": "down", "error": "bucket not found"}
        healthy = healthy and exists
    except Exception as e:
        services["minio"] = {"status": "down", "error": str(e)}
        healthy = False
    try:
        await run_in_threadpool(_db_fetchone, "SELECT 1", None)
        services["postgres"] = {"status": "ok"}
    except Exception as e:
        services["postgres"] = {"status": "down", "error": str(e)}
        healthy = False
    return ok({"services": services}, "healthy" if healthy else "degraded",
              status_code=200 if healthy else 503)


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    data = await file.read()
    if not data:
        raise HTTPException(400, "file required")
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "max 20 MB")

    job_id = str(uuid.uuid4())
    file_key = f"uploads/{job_id}/{file.filename}"
    file_type = "document"

    await run_in_threadpool(_minio_put, file_key, data, file.content_type)
    await run_in_threadpool(
        _db_exec,
        "INSERT INTO jobs (id, filename, file_key, file_size, file_type, status) "
        "VALUES (%s, %s, %s, %s, %s, 'queued')",
        (job_id, file.filename, file_key, len(data), file_type),
    )
    await rds.xadd(f"{STREAM_PREFIX}:{file_type}", {
        "job_id": job_id, "file_key": file_key, "filename": file.filename, "file_type": file_type,
    })

    print(f"[API] Job {job_id} [{file_type}]: {file.filename} ({len(data)} bytes)")
    return ok({"job_id": job_id, "filename": file.filename, "status": "queued",
               "ws_url": f"/ws/jobs/{job_id}"}, "job antri", status_code=201)


@app.get("/api/jobs/{job_id}")
async def job_status(job_id: str):
    row = await run_in_threadpool(
        _db_fetchone,
        "SELECT id, filename, file_size, status, current_step, error, elapsed_ms, "
        "created_at, updated_at, completed_at FROM jobs WHERE id = %s", (job_id,))
    if not row:
        raise HTTPException(404, "job tidak ditemukan")
    keys = ["id", "filename", "file_size", "status", "current_step", "error",
            "elapsed_ms", "created_at", "updated_at", "completed_at"]
    d = dict(zip(keys, row))
    d["id"] = str(d["id"])
    for k in ("created_at", "updated_at", "completed_at"):
        d[k] = _iso(d[k])
    return ok(d)


@app.get("/api/jobs/{job_id}/result")
async def job_result(job_id: str):
    row = await run_in_threadpool(
        _db_fetchone, "SELECT status, result FROM jobs WHERE id = %s", (job_id,))
    if not row:
        raise HTTPException(404, "job tidak ditemukan")
    status, result = row
    if status != "completed" or not result:
        return ok({"status": status}, "belum selesai", status_code=202)
    # buang blok debug `raw` dari kontrak utama (tersedia di /raw)
    clean = {k: v for k, v in result.items() if k != "raw"}
    return ok(clean)


@app.get("/api/jobs/{job_id}/raw")
async def job_raw(job_id: str):
    """Data mentah/debug (extracted_text, tables, skor lama) — terpisah dari result utama."""
    row = await run_in_threadpool(
        _db_fetchone, "SELECT status, result FROM jobs WHERE id = %s", (job_id,))
    if not row:
        raise HTTPException(404, "job tidak ditemukan")
    status, result = row
    if status != "completed" or not result:
        return ok({"status": status}, "belum ada hasil", status_code=202)
    return ok(result.get("raw"))


@app.get("/api/jobs")
async def list_jobs(page: int = 1, per_page: int = 50):
    # Ringkasan untuk tabel riwayat — field penting diekstrak dari result (JSONB)
    # tanpa menarik blob besar. 'ref' = nomor dokumen kunci; 'doc_count' = jumlah dok/file.
    page = max(page, 1)
    per_page = min(max(per_page, 1), 100)
    offset = (page - 1) * per_page

    total_row = await run_in_threadpool(_db_fetchone, "SELECT count(*) FROM jobs", None)
    total = total_row[0] if total_row else 0

    rows = await run_in_threadpool(
        _db_fetchall,
        """
        SELECT id, filename, file_size, status, elapsed_ms, created_at,
               result->>'document_type'                         AS document_type,
               (result->>'confidence')::float                   AS confidence,
               (result->>'needs_review')::bool                  AS needs_review,
               COALESCE(
                   result->'data'->0->>'invoice_no',
                   result->'data'->0->>'order_no',
                   result->'data'->>'bill_no',
                   result->'data'->0->>'bill_no'
               )                                                 AS ref,
               CASE WHEN jsonb_typeof(result->'data') = 'array'
                    THEN jsonb_array_length(result->'data') ELSE 1 END AS doc_count
        FROM jobs ORDER BY created_at DESC LIMIT %s OFFSET %s
        """, (per_page, offset))
    keys = ["id", "filename", "file_size", "status", "elapsed_ms", "created_at",
            "document_type", "confidence", "needs_review", "ref", "doc_count"]
    jobs = []
    for r in rows:
        d = dict(zip(keys, r))
        d["id"] = str(d["id"])
        d["created_at"] = _iso(d["created_at"])
        jobs.append(d)
    return ok(jobs, meta={"page": page, "per_page": per_page, "total": total})


@app.websocket("/ws/jobs/{job_id}")
async def job_ws(ws: WebSocket, job_id: str):
    await ws.accept()
    channel = f"job:{job_id}:status"
    pubsub = rds.pubsub()
    await pubsub.subscribe(channel)
    try:
        # status awal dari DB
        row = await run_in_threadpool(
            _db_fetchone,
            "SELECT status, COALESCE(current_step, ''), error FROM jobs WHERE id = %s", (job_id,))
        if row:
            await ws.send_json({"job_id": job_id, "status": row[0], "step": row[1]})
            if row[0] in ("completed", "failed"):
                return  # sudah selesai sebelum WS dibuka -> jangan menggantung

        async for msg in pubsub.listen():
            if msg.get("type") != "message":
                continue
            payload = msg["data"]
            await ws.send_text(payload)
            try:
                if json.loads(payload).get("status") in ("completed", "failed"):
                    break
            except Exception:
                pass
    except WebSocketDisconnect:
        pass
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.aclose()
        try:
            await ws.close()
        except Exception:
            pass


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("API_PORT", os.getenv("GO_PORT", "8091")))
    uvicorn.run("legacy.app:app", host="0.0.0.0", port=port)
