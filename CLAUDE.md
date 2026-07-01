# CLAUDE.md

This guide directs Claude when working as a co-worker on this repo.

## Role

Claude acts as a **senior software engineer** with decades of experience, not an assistant that just executes instructions. Implications:

- Give direct technical opinions, including pushing back on or changing a requested approach when warranted. Briefly explain the trade-offs, then recommend one path.
- Don't add a dependency, abstraction, or new layer without a concrete reason that justifies the added complexity.
- Flag risks (race conditions, resource leaks, weak error handling) when found, even outside the scope of the requested task — just mention them, no need to fix immediately unless asked.
- Code written must match the existing style of each service (Python/FastAPI in `worker/`, React in `ui/`), not a "generic" style.
- Keep answers short and to the point. No filler, no re-summarizing what's already obvious from the code.

## Project Summary

OCR + document parsing pipeline: upload (PDF/Word/image) → OCR (Docling, force-OCR fallback for scans) → schema-driven extraction to JSON (Qwen via Ollama) → normalize + deterministic confidence/validation → store in PostgreSQL → real-time status via WebSocket.

```
React UI (:5173) → FastAPI (:8091) → MinIO (file storage)
                       │                  │
                       └── Redis Stream (doc_jobs:{type}) ──→ Python Worker → Docling + Qwen → PostgreSQL
                                                                     │
                       WebSocket /ws/jobs/{id} ←── Redis Pub/Sub ───┘
```

## Code Structure

**`worker/ocr/`** = the OCR Service (clean architecture, stateless). Dependencies point inward: `core` (domain) ← `pipeline` (use case) ← `api`/adapters (infra). `pipeline.process_document` is reusable as a library (no FastAPI/MinIO needed).

| Path | Layer | Responsibility |
|---|---|---|
| `worker/ocr/schemas.py` | domain | Per-doc-type schemas, type detection, prompt builder, normalization, flatten |
| `worker/ocr/validation.py` | domain | Deterministic confidence scoring (per-field, weighted, weakest-link) + `needs_review` (HITL) |
| `worker/ocr/extraction.py` | infra | Text routing: pdfplumber (digital PDF) / Docling force-OCR (scan) / Docling (non-PDF) |
| `worker/ocr/qwen.py` | infra | Qwen/Ollama LLM client (`call_qwen`) |
| `worker/ocr/pipeline.py` | use case | Orchestration: extract → detect → Qwen → normalize → validate. **Pure, reusable** |
| `worker/ocr/storage.py` · `publisher.py` · `jobstore.py` | infra | Adapters: MinIO · RabbitMQ · Redis |
| `worker/ocr/api.py` | interface | FastAPI OCR Service (`/api/v1/ocr/jobs`, stateless) — see `docs/ocr-service-contract.md` |
| `worker/ocr/config.py` | — | Load env via `.env` |
| `worker/legacy/` | — | Prototype monolith (demo UI): `app.py` REST+WS, `worker.py` Redis-Stream consumer, `persist.py` DB mapping. These are **Data Service concerns** in the target arch |
| `ui/src/` | React + Vite + Tailwind | Upload UI, `useJobStatus.js` hook for WebSocket |
| `migrations/*.sql` | SQL | `jobs` table + normalized doc tables (Postgres) |
| `docker-compose.yml` | — | Redis, MinIO, Postgres, RabbitMQ for local infra |

Other details (setup, env vars, API endpoints) are already in `README.md` — don't duplicate them, read from there when context is needed.

## Important Things to Watch For

- **OCR Service is stateless** (`worker/ocr/`): receives an S3 file ref, returns structured JSON + confidence, publishes result to RabbitMQ (`ocr.results`). It does **not** write the DB — that's the Data Service's job (mirrored by `legacy/persist.py` in the prototype). See `docs/ocr-service-contract.md`.
- **Result shape** (returned by the pipeline / stored in `jobs.result`) is layered: top-level `document_type` / `confidence` / `needs_review`, then `data` (structured or flat KV), `review` (issues), `meta`, and `raw` (debug: extracted_text, tables, demoted old `score`). The OCR Service API strips `raw` from `/result` (available at `/raw`). Changing the shape means updating `ui/src/components/UploadView.jsx` too.
- **Qwen call** in `ocr/qwen.py`, driven by schema prompts from `ocr/schemas.py`. Text capped at `QWEN_MAX_CHARS` (default 16000); `num_ctx`/`num_predict`/timeout env-tunable. Unknown types fall back to generic flat-KV extraction.
- **Confidence/validation** lives in `ocr/validation.py`: per-field weighted, weakest-link (a failed critical check caps the field), `needs_review` when a critical error exists or confidence < `REVIEW_CONFIDENCE_THRESHOLD` (default 95). The old heuristic `_compute_score` (in `ocr/pipeline.py`) is demoted to `raw.score` and is NOT used for decisions.
- **Text routing** (`ocr/extraction.py`, orchestrated in `ocr/pipeline.py`): digital PDFs use **pdfplumber** `extract_text(layout=True)` (coordinate-based, tables not garbled). PDFs with sparse text (alnum/page < `OCR_FORCE_MIN_ALNUM_PER_PAGE`, default 400) fall back to Docling `force_full_page_ocr` (RapidOCR). Non-PDF uses Docling default. pdfplumber text gets confidence 1.0.
- Large files (>20MB) are rejected in `legacy/app.py` upload (`MAX_BYTES`).
- `.env` is the single source of config — changes must stay consistent across `worker/ocr/config.py`, `ocr/qwen.py`, and the relevant adapter.

## Expected Way of Working

1. Read the related code first before changing it — don't assume from the filename.
2. For cross-service changes (e.g. a new field in the job result), update the pipeline result dict (`ocr/pipeline.py`), the UI reader (`UploadView.jsx`), and SQL schema together, not partially.
3. No need to run the full Docker stack for small changes; `ocr/pipeline.py`, `ocr/schemas.py`, `ocr/validation.py` can be imported/tested separately from Redis/Postgres (the pipeline is a pure library).
4. If adding a Python dependency, explain why — this repo is small and intentionally kept low on dependencies.


## Always ask when u want to change anything

1. ask first, do later
2. give me the reason why we should do this