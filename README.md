# OCR + Parsing Dokumen

Upload dokumen (PDF, Word, gambar) → **Docling** OCR (force-OCR untuk scan/gambar) → ekstraksi **schema-driven** via **Qwen AI** ke JSON → normalisasi + **confidence/validation** (HITL) → simpan ke **PostgreSQL** → real-time status via **WebSocket**.

---

## Arsitektur

```
React UI (Vite :5173)
     │
     ├── POST /api/upload ──→ FastAPI (:8091) ──→ MinIO (file storage)
     │                            │
     │                            └── doc_jobs:document ──→ Python Worker
     │                                                         │
     │   WebSocket /ws/jobs/{id} ←── Redis Pub/Sub ←──── Docling + Qwen AI
     │                                                         │
     └── GET /api/jobs/{id}/result ──→ FastAPI ──→ PostgreSQL ──┘
```

---

## Tech Stack

| Layer | Tech | Port |
|---|---|---|
| Frontend | React 18 + Vite + Tailwind | :5173 |
| API | Python (FastAPI + Uvicorn) | :8091 |
| Queue | Redis Streams (`doc_jobs:document`) | :6379 |
| File Storage | MinIO (S3-compatible) | :9000 |
| Database | PostgreSQL 16 | :5432 |
| Worker | Python (Docling + RapidOCR + Qwen) | - |
| AI | Qwen 2.5 via Ollama | :11434 |

---

## Setup

### 1. Infrastruktur (Docker)

```bash
docker compose up -d
```

Ini menjalankan Redis, MinIO, dan PostgreSQL. Schema database otomatis dibuat dari `migrations/001_init.sql`. Setelah pertama kali jalan, apply migration tambahan:

```bash
psql -h localhost -U postgres -d ocr_parse -f migrations/002_add_file_type.sql
```

### 2. Ollama + Qwen

```bash
# Install Ollama dari https://ollama.com
ollama pull qwen2.5
```

```bash
pip install -r worker/requirements.txt
```

### 3. OCR Service (microservice, clean architecture)

Package `worker/ocr/` — stateless, dijalankan dari folder `worker/`:

```bash
cd worker && python -m ocr        # OCR Service di http://localhost:8092
```

### 4. Prototype monolit (demo UI) — `worker/legacy/`

Untuk demo lokal dengan React UI (API + worker Redis-Stream):

```bash
cd worker
python -m legacy.app              # API :8091 (dipakai React UI)
python -m legacy.worker           # consumer Redis Stream (OCR + persist DB)
# WORKER_COUNT=3 python -m legacy.worker   # beberapa worker parallel
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
2. Drag & drop file (PDF, Word, gambar)
3. Upload langsung ke FastAPI → file disimpan di MinIO
4. API push job ke Redis Stream `doc_jobs:document`
5. Worker memproses di background: OCR → Clean → deteksi tipe → Qwen (schema) → normalisasi + validasi → DB
6. UI menampilkan progress real-time via WebSocket
7. Hasil muncul: data terstruktur + **confidence & needs_review** (per-field issues)

---

## API Endpoints

| Method | Path | Deskripsi |
|---|---|---|
| GET | `/api/health` | Health check (Redis, MinIO, PostgreSQL) |
| POST | `/api/upload` | Upload file, return `{job_id, file_type}` |
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
API_PORT=8091                      # port FastAPI (GO_PORT lama masih dibaca utk back-compat)

# Tuning Qwen / OCR (opsional — default sudah masuk akal)
QWEN_TIMEOUT=900                   # detik; model besar di GPU lambat butuh ruang
QWEN_MAX_CHARS=16000               # batas teks ke Qwen (multi-halaman)
QWEN_NUM_CTX=12288                 # context window Ollama
QWEN_NUM_PREDICT=4096              # batas token output
OCR_FORCE_MIN_ALNUM_PER_PAGE=400  # di bawah ini -> paksa OCR penuh (PDF gambar/scan)
REVIEW_CONFIDENCE_THRESHOLD=95     # confidence < ini -> needs_review (HITL)
```

---

## Tips Resource & Performa

**Model Qwen** — default `qwen2.5:latest` (7B) butuh ~4-5GB VRAM dan lebih akurat untuk dokumen kompleks (multi-invoice, banyak kolom). Untuk hemat resource / lebih cepat:

```bash
ollama pull qwen2.5:3b   # ~2GB, jauh lebih cepat
```

Lalu set di `.env`: `QWEN_MODEL=qwen2.5:3b`. Catatan: 3B kerap salah pada layout rumit (invoice multi-halaman, kolom ketukar) — untuk akurasi pakai 7B + naikkan `QWEN_TIMEOUT`.

**Worker count** — Ollama hanya serve 1 request at a time. Lebih dari 2 worker akan antri di Qwen. Rekomendasi: `WORKER_COUNT=1` (single GPU) atau `WORKER_COUNT=2` (overlap OCR + Qwen).

**Docling converter** — di-cache otomatis per worker process. Dokumen pertama lambat (load model), selanjutnya cepat.

---

## Struktur Kode

```
ocr_parse_example/
├── docker-compose.yml        # Redis + MinIO + PostgreSQL
├── .env                      # Environment variables
├── worker/
│   ├── ocr/                  # OCR Service (clean architecture, stateless)
│   │   ├── schemas.py        #   domain: schema tipe dokumen + normalisasi
│   │   ├── validation.py     #   domain: confidence scoring + needs_review (HITL)
│   │   ├── extraction.py     #   infra: pdfplumber / Docling / force-OCR
│   │   ├── qwen.py           #   infra: klien LLM (Ollama)
│   │   ├── pipeline.py       #   use case: orkestrasi (reusable sbg library)
│   │   ├── storage.py        #   adapter: MinIO
│   │   ├── publisher.py      #   adapter: RabbitMQ
│   │   ├── jobstore.py       #   adapter: Redis (status job)
│   │   ├── api.py            #   interface: FastAPI (kontrak microservice)
│   │   ├── config.py
│   │   └── __main__.py       #   `python -m ocr`
│   ├── legacy/               # prototype monolit (demo UI; concern Data Service)
│   │   ├── app.py            #   FastAPI UI-facing (REST + WebSocket)
│   │   ├── worker.py         #   Redis Stream consumer
│   │   └── persist.py        #   map hasil -> tabel ternormalisasi
│   └── requirements.txt
├── migrations/
│   ├── 001_init.sql          # PostgreSQL schema
│   ├── 002_add_file_type.sql # Kolom file_type
│   └── 003_doc_tables.sql    # Tabel ternormalisasi per tipe dokumen
└── ui/                       # React frontend
    └── src/
        ├── App.jsx
        ├── components/
        │   └── UploadView.jsx
        └── hooks/
            └── useJobStatus.js  # WebSocket hook
```

