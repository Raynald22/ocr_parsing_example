"""Adapter object storage (MinIO/S3). Lazy singleton."""

from minio import Minio

from .config import MINIO_ACCESS, MINIO_BUCKET, MINIO_ENDPOINT, MINIO_SECRET

_client = None


def client() -> Minio:
    global _client
    if _client is None:
        _client = Minio(MINIO_ENDPOINT, access_key=MINIO_ACCESS,
                        secret_key=MINIO_SECRET, secure=False)
    return _client


def fetch(bucket: str, key: str, dest: str):
    client().fget_object(bucket, key, dest)


def bucket_exists(bucket: str = MINIO_BUCKET) -> bool:
    return client().bucket_exists(bucket)
