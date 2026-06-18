"""
worker.py
=========
Redis Stream consumer — ambil job, proses dengan Docling + Qwen, simpan ke PostgreSQL.

Jalankan:
    python worker/worker.py
"""

import json
import signal
import sys
import tempfile
import time
from pathlib import Path

import psycopg2
import psycopg2.extras
import redis
from minio import Minio

from config import (
    CONSUMER_NAME, DATABASE_URL, GROUP_NAME, MINIO_ACCESS, MINIO_BUCKET,
    MINIO_ENDPOINT, MINIO_SECRET, REDIS_HOST, REDIS_PORT, STREAM_NAME,
)
from processor import process_document

# ── Koneksi ─────────────────────────────────────────────────────────────────

rds = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

minio_client = Minio(
    MINIO_ENDPOINT,
    access_key=MINIO_ACCESS,
    secret_key=MINIO_SECRET,
    secure=False,
)

# Parse postgres URL → psycopg2 connect
_db_url = DATABASE_URL.replace("postgres://", "postgresql://")
db = psycopg2.connect(_db_url)
db.autocommit = True

running = True


def shutdown(sig, frame):
    global running
    print("\n[Worker] Shutting down...")
    running = False


signal.signal(signal.SIGINT, shutdown)
signal.signal(signal.SIGTERM, shutdown)


# ── Setup ───────────────────────────────────────────────────────────────────

def setup():
    # Buat consumer group (abaikan jika sudah ada)
    try:
        rds.xgroup_create(STREAM_NAME, GROUP_NAME, id="0", mkstream=True)
        print(f"[Worker] Created consumer group '{GROUP_NAME}' on stream '{STREAM_NAME}'")
    except redis.ResponseError as e:
        if "BUSYGROUP" not in str(e):
            raise

    # Pastikan bucket MinIO ada
    if not minio_client.bucket_exists(MINIO_BUCKET):
        minio_client.make_bucket(MINIO_BUCKET)
        print(f"[Worker] Created MinIO bucket '{MINIO_BUCKET}'")


def update_job_status(job_id: str, status: str, step: str = None):
    """Update status di PostgreSQL dan publish ke Redis Pub/Sub."""
    with db.cursor() as cur:
        cur.execute(
            "UPDATE jobs SET status = %s, current_step = %s, updated_at = NOW() WHERE id = %s",
            (status, step, job_id),
        )
    rds.publish(f"job:{job_id}:status", json.dumps({
        "job_id": job_id,
        "status": status,
        "step": step,
        "timestamp": time.time(),
    }))


def save_result(job_id: str, result: dict, elapsed_ms: int):
    """Simpan hasil ke PostgreSQL."""
    with db.cursor() as cur:
        cur.execute(
            """UPDATE jobs
               SET status = 'completed', result = %s, elapsed_ms = %s,
                   completed_at = NOW(), updated_at = NOW()
               WHERE id = %s""",
            (json.dumps(result, ensure_ascii=False), elapsed_ms, job_id),
        )
    rds.publish(f"job:{job_id}:status", json.dumps({
        "job_id": job_id,
        "status": "completed",
        "step": None,
        "elapsed_ms": elapsed_ms,
        "timestamp": time.time(),
    }))


def save_error(job_id: str, error: str):
    """Simpan error ke PostgreSQL."""
    with db.cursor() as cur:
        cur.execute(
            "UPDATE jobs SET status = 'failed', error = %s, updated_at = NOW() WHERE id = %s",
            (error, job_id),
        )
    rds.publish(f"job:{job_id}:status", json.dumps({
        "job_id": job_id,
        "status": "failed",
        "error": error,
        "timestamp": time.time(),
    }))


# ── Main loop ───────────────────────────────────────────────────────────────

def process_job(msg_id: str, data: dict):
    job_id = data["job_id"]
    file_key = data["file_key"]
    filename = data.get("filename", "unknown")

    print(f"[Worker] Processing job {job_id}: {filename}")

    update_job_status(job_id, "processing", "OCR")

    # Download file dari MinIO ke temp
    tmp = tempfile.NamedTemporaryFile(
        delete=False,
        suffix=Path(filename).suffix,
    )
    tmp.close()  # Windows: tutup handle agar MinIO bisa tulis
    try:
        minio_client.fget_object(MINIO_BUCKET, file_key, tmp.name)
    except Exception as e:
        save_error(job_id, f"Download dari MinIO gagal: {e}")
        rds.xack(STREAM_NAME, GROUP_NAME, msg_id)
        return

    start_ms = int(time.time() * 1000)

    def on_status(step, status, detail, elapsed):
        update_job_status(job_id, "processing", step)
        rds.publish(f"job:{job_id}:status", json.dumps({
            "job_id": job_id,
            "status": "processing",
            "step": step,
            "step_status": status,
            "detail": detail,
            "elapsed_s": elapsed,
            "timestamp": time.time(),
        }))

    try:
        result = process_document(tmp.name, on_status=on_status)
        elapsed_ms = int(time.time() * 1000) - start_ms
        save_result(job_id, result, elapsed_ms)
        print(f"[Worker] Job {job_id} completed in {elapsed_ms}ms")
    except Exception as e:
        save_error(job_id, f"{type(e).__name__}: {e}")
        print(f"[Worker] Job {job_id} failed: {e}")
    finally:
        Path(tmp.name).unlink(missing_ok=True)
        rds.xack(STREAM_NAME, GROUP_NAME, msg_id)


def main():
    setup()
    print(f"[Worker] Listening on stream '{STREAM_NAME}' as '{CONSUMER_NAME}'...")
    print("[Worker] Ctrl+C to stop\n")

    while running:
        try:
            messages = rds.xreadgroup(
                GROUP_NAME, CONSUMER_NAME,
                {STREAM_NAME: ">"},
                count=1,
                block=5000,
            )
        except redis.ConnectionError:
            print("[Worker] Redis connection lost, retrying in 3s...")
            time.sleep(3)
            continue

        if not messages:
            continue

        for stream_name, entries in messages:
            for msg_id, data in entries:
                process_job(msg_id, data)

    db.close()
    print("[Worker] Stopped.")


if __name__ == "__main__":
    main()
