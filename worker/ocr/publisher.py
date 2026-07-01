"""Publish hasil OCR ke RabbitMQ (message bus).

Dipakai OCR Service untuk mengabarkan job selesai/gagal ke Data Service.
Best-effort: bila RabbitMQ tidak tersedia, error di-log, tidak menggagalkan job
(status tetap tersimpan di Redis & bisa di-poll).

`pika` bersifat blocking, jadi publish dijalankan di threadpool dari kode async.
"""

import json
import os
from datetime import datetime

from fastapi.concurrency import run_in_threadpool

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
OCR_EXCHANGE = os.getenv("OCR_EXCHANGE", "ocr.results")


def _now():
    return datetime.now().astimezone().isoformat()


def _publish_sync(message: dict):
    import pika
    conn = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
    try:
        ch = conn.channel()
        ch.exchange_declare(exchange=OCR_EXCHANGE, exchange_type="fanout", durable=True)
        ch.basic_publish(
            exchange=OCR_EXCHANGE,
            routing_key="",
            body=json.dumps(message, ensure_ascii=False).encode("utf-8"),
            properties=pika.BasicProperties(content_type="application/json", delivery_mode=2),
        )
    finally:
        conn.close()


async def publish_event(event: str, job_id: str, extra: dict):
    """Publish {event, job_id, timestamp, **extra} ke exchange ocr.results.
    Best-effort — kegagalan hanya di-log."""
    message = {"event": event, "job_id": job_id, "timestamp": _now(), **extra}
    try:
        await run_in_threadpool(_publish_sync, message)
        print(f"[bus] published {event} job={job_id}")
    except Exception as e:
        print(f"[bus] publish gagal (best-effort) {event} job={job_id}: {type(e).__name__}: {e}")
