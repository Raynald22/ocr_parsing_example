# OCR + Parsing Dokumen

Upload dokumen (PDF, Word, Excel, gambar) → **Docling** OCR → **Qwen AI** parse ke JSON → simpan ke **PostgreSQL** → real-time status via **WebSocket**.

---

## Arsitektur

```
React UI (Vite :5173)
     │
     ├── POST /api/upload ──→ Go API (:8080) ──→ MinIO (file storage)
     │                            │
     │                            └── Redis Stream (job queue)
     │                                     │
     │   WebSocket /ws/jobs/{id} ←── Redis Pub/Sub ←── Python Worker
     │                                                     │
     │                                              Docling + Qwen AI
     │                                                     │
     └── GET /api/jobs/{id}/result ──→ Go API ──→ PostgreSQL
```

---

## Tech Stack

| Layer | Tech | Port |
|---|---|---|
| Frontend | React 18 + Vite + Tailwind | :5173 |
| Gateway | Go (Fiber) | :8080 |
| Queue | Redis Streams | :6379 |
| File Storage | MinIO (S3-compatible) | :9000 |
| Database | PostgreSQL 16 | :5432 |
| Worker | Python (Docling + Qwen) | - |
| AI | Qwen 2.5 via Ollama | :11434 |

---

## Setup

### 1. Infrastruktur (Docker)

```bash
docker compose up -d
```

Ini menjalankan Redis, MinIO, dan PostgreSQL. Schema database otomatis dibuat dari `migrations/001_init.sql`.

### 2. Ollama + Qwen

```bash
# Install Ollama dari https://ollama.com
ollama pull qwen2.5
```

### 3. Go Gateway

```bash
cd gateway
go build -o gateway.exe .
./gateway.exe
# Berjalan di http://localhost:8080
```

### 4. Python Worker

```bash
pip install -r worker/requirements.txt
python worker/worker.py
```

### 5. React UI

```bash
cd ui
npm install
npm run dev
# Buka http://localhost:5173
```

---

## Cara Pakai

1. Buka `http://localhost:5173`
2. Drag & drop file (PDF, Word, Excel, gambar)
3. Upload langsung ke Go API → file disimpan di MinIO
4. Worker memproses di background: OCR → Clean → Qwen → DB
5. UI menampilkan progress real-time via WebSocket
6. Hasil muncul: key-values, tabel, confidence score

---

## API Endpoints

| Method | Path | Deskripsi |
|---|---|---|
| POST | `/api/upload` | Upload file, return `{job_id}` |
| GET | `/api/jobs/:id` | Status job (queued/processing/completed/failed) |
| GET | `/api/jobs/:id/result` | Hasil lengkap (JSONB dari PostgreSQL) |
| GET | `/api/jobs` | List 50 job terbaru |
| WS | `/ws/jobs/:id` | Real-time pipeline status |

---

## Konfigurasi

Semua config via `.env`:

```env
REDIS_ADDR=localhost:6379
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=documents
DATABASE_URL=postgres://postgres:postgres@localhost:5432/ocr_parse?sslmode=disable
QWEN_BASE_URL=http://localhost:11434
QWEN_MODEL=qwen2.5:latest
GO_PORT=8080
```

---

## Struktur Kode

```
ocr_parse_example/
├── docker-compose.yml        # Redis + MinIO + PostgreSQL
├── .env                      # Environment variables
├── gateway/                  # Go API (Fiber)
│   ├── main.go
│   └── go.mod
├── worker/                   # Python worker
│   ├── worker.py             # Redis Stream consumer
│   ├── processor.py          # Docling + Qwen pipeline
│   ├── config.py
│   └── requirements.txt
├── migrations/
│   └── 001_init.sql          # PostgreSQL schema
└── ui/                       # React frontend
    └── src/
        ├── App.jsx
        ├── components/
        │   └── UploadView.jsx
        └── hooks/
            └── useJobStatus.js  # WebSocket hook
```

---

## Mode Simpel (tanpa Docker)

Untuk development cepat tanpa Go + Redis + MinIO, bisa langsung pakai FastAPI:

```bash
python api.py
# http://localhost:5000 (FastAPI + Swagger di /docs)
```

Mode ini menjalankan Docling + Qwen secara synchronous dalam satu proses Python.
