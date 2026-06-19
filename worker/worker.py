import json
import signal
import tempfile
import time
from pathlib import Path

import psycopg2
import redis
from minio import Minio

from config import (
    CONSUMER_NAME, DATABASE_URL, GROUP_NAME, MINIO_ACCESS, MINIO_BUCKET,
    MINIO_ENDPOINT, MINIO_SECRET, REDIS_HOST, REDIS_PORT, STREAM_NAME,
)
from processor import process_document

rds = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

minio_client = Minio(
    MINIO_ENDPOINT,
    access_key=MINIO_ACCESS,
    secret_key=MINIO_SECRET,
    secure=False,
)

db = psycopg2.connect(DATABASE_URL.replace("postgres://", "postgresql://"))
db.autocommit = True

running = True


def shutdown(sig, frame):
    global running
    print("\n[Worker] Shutting down...")
    running = False


signal.signal(signal.SIGINT, shutdown)
signal.signal(signal.SIGTERM, shutdown)


def setup():
    try:
        rds.xgroup_create(STREAM_NAME, GROUP_NAME, id="0", mkstream=True)
        print(f"[Worker] Created group '{GROUP_NAME}' on '{STREAM_NAME}'")
    except redis.ResponseError as e:
        if "BUSYGROUP" not in str(e):
            raise

    if not minio_client.bucket_exists(MINIO_BUCKET):
        minio_client.make_bucket(MINIO_BUCKET)


def update_status(job_id: str, status: str, step: str = None):
    with db.cursor() as cur:
        cur.execute(
            "UPDATE jobs SET status = %s, current_step = %s, updated_at = NOW() WHERE id = %s",
            (status, step, job_id),
        )
    rds.publish(f"job:{job_id}:status", json.dumps({
        "job_id": job_id, "status": status, "step": step, "timestamp": time.time(),
    }))


def save_result(job_id: str, result: dict, elapsed_ms: int):
    with db.cursor() as cur:
        cur.execute(
            """UPDATE jobs SET status = 'completed', result = %s, elapsed_ms = %s,
               completed_at = NOW(), updated_at = NOW() WHERE id = %s""",
            (json.dumps(result, ensure_ascii=False), elapsed_ms, job_id),
        )
    rds.publish(f"job:{job_id}:status", json.dumps({
        "job_id": job_id, "status": "completed", "elapsed_ms": elapsed_ms, "timestamp": time.time(),
    }))


def save_error(job_id: str, error: str):
    with db.cursor() as cur:
        cur.execute(
            "UPDATE jobs SET status = 'failed', error = %s, updated_at = NOW() WHERE id = %s",
            (error, job_id),
        )
    rds.publish(f"job:{job_id}:status", json.dumps({
        "job_id": job_id, "status": "failed", "error": error, "timestamp": time.time(),
    }))


def process_job(msg_id: str, data: dict):
    job_id = data["job_id"]
    file_key = data["file_key"]
    filename = data.get("filename", "unknown")

    print(f"[Worker] Processing {job_id}: {filename}")
    update_status(job_id, "processing", "OCR")

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=Path(filename).suffix)
    tmp.close()
    try:
        minio_client.fget_object(MINIO_BUCKET, file_key, tmp.name)
    except Exception as e:
        save_error(job_id, f"Storage download failed: {e}")
        rds.xack(STREAM_NAME, GROUP_NAME, msg_id)
        return

    start_ms = int(time.time() * 1000)

    def on_status(step, status, detail, elapsed):
        update_status(job_id, "processing", step)
        rds.publish(f"job:{job_id}:status", json.dumps({
            "job_id": job_id, "status": "processing", "step": step,
            "step_status": status, "detail": detail, "elapsed_s": elapsed,
            "timestamp": time.time(),
        }))

    try:
        result = process_document(tmp.name, on_status=on_status)
        elapsed_ms = int(time.time() * 1000) - start_ms
        save_result(job_id, result, elapsed_ms)
        print(f"[Worker] {job_id} done in {elapsed_ms}ms")
    except Exception as e:
        save_error(job_id, f"{type(e).__name__}: {e}")
        print(f"[Worker] {job_id} failed: {e}")
    finally:
        Path(tmp.name).unlink(missing_ok=True)
        rds.xack(STREAM_NAME, GROUP_NAME, msg_id)


def main():
    setup()
    print(f"[Worker] Listening as '{CONSUMER_NAME}' on '{STREAM_NAME}'")

    while running:
        try:
            messages = rds.xreadgroup(GROUP_NAME, CONSUMER_NAME, {STREAM_NAME: ">"}, count=1, block=5000)
        except redis.ConnectionError:
            print("[Worker] Redis lost, retrying...")
            time.sleep(3)
            continue

        if not messages:
            continue

        for _, entries in messages:
            for msg_id, data in entries:
                process_job(msg_id, data)

    db.close()
    print("[Worker] Stopped.")


if __name__ == "__main__":
    main()
