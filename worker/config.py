import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

REDIS_ADDR      = os.getenv("REDIS_ADDR",      "localhost:6379")
REDIS_HOST      = REDIS_ADDR.split(":")[0]
REDIS_PORT      = int(REDIS_ADDR.split(":")[1])

MINIO_ENDPOINT  = os.getenv("MINIO_ENDPOINT",  "localhost:9000")
MINIO_ACCESS    = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET    = os.getenv("MINIO_SECRET_KEY", "minioadmin")
MINIO_BUCKET    = os.getenv("MINIO_BUCKET",     "documents")

DATABASE_URL    = os.getenv("DATABASE_URL",     "postgres://postgres:postgres@localhost:5432/ocr_parse")

QWEN_BASE_URL   = os.getenv("QWEN_BASE_URL",   "http://localhost:11434")
QWEN_MODEL      = os.getenv("QWEN_MODEL",      "qwen2.5:latest")
QWEN_TIMEOUT    = int(os.getenv("QWEN_TIMEOUT", "300"))

STREAM_NAME     = "doc_jobs"
GROUP_NAME      = "workers"
CONSUMER_NAME   = os.getenv("WORKER_ID", "worker-1")
