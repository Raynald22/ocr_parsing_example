"""Adapter status job sementara di Redis (cache, TTL). Bukan sumber durable —
sumber kebenaran ada di Data Service. Dipakai untuk endpoint poll OCR Service.
"""

import json
import os

import redis.asyncio as aioredis

from .config import REDIS_HOST, REDIS_PORT

JOB_TTL = int(os.getenv("OCR_JOB_TTL", "3600"))

_rds = None


def _redis() -> aioredis.Redis:
    global _rds
    if _rds is None:
        _rds = aioredis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    return _rds


def _key(job_id: str) -> str:
    return f"ocr:job:{job_id}"


async def set_state(job_id: str, payload: dict):
    await _redis().set(_key(job_id), json.dumps(payload, ensure_ascii=False), ex=JOB_TTL)


async def get_state(job_id: str):
    v = await _redis().get(_key(job_id))
    return json.loads(v) if v else None


async def ping():
    await _redis().ping()


async def close():
    if _rds is not None:
        await _rds.aclose()
