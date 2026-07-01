import json
import multiprocessing
import signal
import sys
import tempfile
import time
from pathlib import Path

import psycopg2
import redis
from minio import Minio

from ocr.config import (
    DATABASE_URL, GROUP_NAME, MINIO_ACCESS, MINIO_BUCKET,
    MINIO_ENDPOINT, MINIO_SECRET, REDIS_HOST, REDIS_PORT, STREAM_NAME,
    WORKER_COUNT, WORKER_TYPE,
)
from ocr.pipeline import process_document
from legacy.persist import persist


def run_worker(consumer_name: str):
    rds = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True, socket_timeout=30, socket_connect_timeout=10)
    minio_client = Minio(MINIO_ENDPOINT, access_key=MINIO_ACCESS, secret_key=MINIO_SECRET, secure=False)
    db = psycopg2.connect(DATABASE_URL.replace("postgres://", "postgresql://"))
    db.autocommit = True

    tag = f"[{consumer_name}]"
    running = True

    def shutdown(sig, frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    try:
        rds.xgroup_create(STREAM_NAME, GROUP_NAME, id="0", mkstream=True)
    except redis.ResponseError as e:
        if "BUSYGROUP" not in str(e):
            raise

    if not minio_client.bucket_exists(MINIO_BUCKET):
        minio_client.make_bucket(MINIO_BUCKET)

    def update_status(job_id, status, step=None):
        with db.cursor() as cur:
            cur.execute(
                "UPDATE jobs SET status = %s, current_step = %s, updated_at = NOW() WHERE id = %s",
                (status, step, job_id),
            )
        rds.publish(f"job:{job_id}:status", json.dumps({
            "job_id": job_id, "status": status, "step": step, "timestamp": time.time(),
        }))

    def save_result(job_id, result, elapsed_ms):
        with db.cursor() as cur:
            cur.execute(
                """UPDATE jobs SET status = 'completed', result = %s, elapsed_ms = %s,
                   completed_at = NOW(), updated_at = NOW() WHERE id = %s""",
                (json.dumps(result, ensure_ascii=False), elapsed_ms, job_id),
            )
        rds.publish(f"job:{job_id}:status", json.dumps({
            "job_id": job_id, "status": "completed", "elapsed_ms": elapsed_ms, "timestamp": time.time(),
        }))

    def save_error(job_id, error):
        with db.cursor() as cur:
            cur.execute(
                "UPDATE jobs SET status = 'failed', error = %s, updated_at = NOW() WHERE id = %s",
                (error, job_id),
            )
        rds.publish(f"job:{job_id}:status", json.dumps({
            "job_id": job_id, "status": "failed", "error": error, "timestamp": time.time(),
        }))

    def process_job(msg_id, data):
        job_id = data["job_id"]
        file_key = data["file_key"]
        filename = data.get("filename", "unknown")

        print(f"{tag} Processing {job_id}: {filename}")
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
            # Turunkan ke tabel ternormalisasi (best-effort; jangan gagalkan job)
            try:
                with db.cursor() as cur:
                    persist(cur, job_id, result.get("document_type"), result.get("data"),
                            result.get("confidence"), result.get("needs_review"))
            except Exception as pe:
                print(f"{tag} persist failed for {job_id}: {type(pe).__name__}: {pe}")
            print(f"{tag} {job_id} done in {elapsed_ms}ms")
        except Exception as e:
            save_error(job_id, f"{type(e).__name__}: {e}")
            print(f"{tag} {job_id} failed: {e}")
        finally:
            Path(tmp.name).unlink(missing_ok=True)
            rds.xack(STREAM_NAME, GROUP_NAME, msg_id)

    print(f"{tag} Listening on '{STREAM_NAME}' (group '{GROUP_NAME}')")

    while running:
        try:
            messages = rds.xreadgroup(GROUP_NAME, consumer_name, {STREAM_NAME: ">"}, count=1, block=5000)
        except (redis.ConnectionError, redis.TimeoutError):
            print(f"{tag} Redis lost, retrying...")
            time.sleep(3)
            continue

        if not messages:
            continue

        for _, entries in messages:
            for msg_id, data in entries:
                process_job(msg_id, data)

    db.close()
    print(f"{tag} Stopped.")


def main():
    if WORKER_COUNT <= 1:
        run_worker(f"{WORKER_TYPE}-1")
        return

    print(f"[Launcher] Starting {WORKER_COUNT} {WORKER_TYPE} workers...")
    procs = []
    for i in range(1, WORKER_COUNT + 1):
        name = f"{WORKER_TYPE}-{i}"
        p = multiprocessing.Process(target=run_worker, args=(name,), name=name)
        p.start()
        procs.append(p)

    def shutdown_all(sig, frame):
        print(f"\n[Launcher] Shutting down {len(procs)} workers...")
        for p in procs:
            if p.is_alive():
                p.terminate()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown_all)
    signal.signal(signal.SIGTERM, shutdown_all)

    for p in procs:
        p.join()


if __name__ == "__main__":
    main()
