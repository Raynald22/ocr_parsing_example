# OCR Service — Kontrak API

Kontrak antara **OCR Service** (Python) dan komponen lain (Data Service / API Gateway)
dalam arsitektur microservices LNSW.

## Prinsip

1. **Stateless** — OCR Service **tidak** menyimpan ke database. Input = referensi file di
   S3/MinIO (milik Data Service), output = JSON terstruktur + confidence. **Data Service**
   yang melakukan persist ke tabel & blob.
2. **Asinkron** — proses OCR makan waktu (menit). Submit dibalas `202`, hasil dikirim lewat
   **RabbitMQ** saat selesai. Endpoint poll disediakan sebagai fallback.
3. **Transient state** — status/hasil sementara disimpan di **Redis** dengan TTL (cache,
   bukan sumber kebenaran). Sumber durable tetap milik Data Service.
4. **Envelope seragam** — semua respons HTTP: `{ success, message, data, error, meta }`.
5. **Versioned** — base path `/api/v1`.

---

## Endpoint

| Method | Path | Fungsi |
|---|---|---|
| POST | `/api/v1/ocr/jobs` | Submit job (async) → `202` |
| GET | `/api/v1/ocr/jobs/{job_id}` | Status job |
| GET | `/api/v1/ocr/jobs/{job_id}/result` | Hasil bila `completed` |
| GET | `/api/v1/health` | Cek Redis/MinIO |

---

## 1. Submit job

**Request**
```json
POST /api/v1/ocr/jobs
{
  "job_id": "f3a1b2c3-...-uuid",
  "file": { "bucket": "documents", "key": "uploads/f3a1.../INVOICE.pdf" },
  "options": {
    "document_type": null,
    "force_ocr": false,
    "callback_url": "http://data-service/internal/ocr-callback"
  }
}
```
| Field | Wajib | Keterangan |
|---|---|---|
| `job_id` | ya | Correlation id dari Data Service |
| `file.bucket` / `file.key` | ya | Lokasi file di S3/MinIO |
| `options.document_type` | tidak | Hint tipe; `null` = auto-detect |
| `options.force_ocr` | tidak | Paksa OCR penuh (lewati pdfplumber) |
| `options.callback_url` | tidak | Webhook tambahan selain RabbitMQ |

**Response `202`**
```json
{ "success": true, "message": "job diterima",
  "data": { "job_id": "f3a1...", "status": "accepted" },
  "error": null, "meta": { "timestamp": "..." } }
```

---

## 2. Status

```
GET /api/v1/ocr/jobs/{job_id}
```
```json
{ "success": true, "data": { "job_id": "f3a1...", "status": "processing" }, ... }
```
`status`: `accepted` → `processing` → `completed` | `failed`.

## 3. Result

```
GET /api/v1/ocr/jobs/{job_id}/result
```
- Bila belum selesai → `202 { data: { status } }`.
- Bila selesai → `200` dengan **payload hasil** di `data` (lihat di bawah).

---

## 4. Payload Hasil (inti kontrak)

Inilah objek yang dipetakan Data Service ke tabel.

```json
{
  "document_type": "invoice",
  "confidence": 100.0,
  "needs_review": false,
  "data": [ /* per tipe — lihat 4.1 */ ],
  "review": {
    "errors": 0, "warnings": 0, "critical_errors": 0,
    "fields_scored": 68, "threshold": 95,
    "issues": [ { "field": "items[1].amount", "level": "error", "message": "amount != qty*unit_price" } ]
  },
  "meta": {
    "pages": 6,
    "ocr_engine": "pdfplumber",
    "ocr_forced": false,
    "model": "qwen2.5:latest",
    "elapsed_s": 552.2,
    "doc_confidence": 100.0
  }
}
```

| Field | Tipe | Keterangan |
|---|---|---|
| `document_type` | string | `invoice` \| `packing_list` \| `bill_of_lading` \| `generic` |
| `confidence` | number | 0–100, skor agregat |
| `needs_review` | bool | Sinyal human-in-the-loop |
| `data` | array \| object | Data terstruktur (lihat 4.1) |
| `review.issues[]` | array | `{ field, level: error\|warn, message }` |
| `meta.ocr_engine` | string | `pdfplumber` \| `docling-ocr` \| `docling` |

> `raw` (extracted_text, tables) **tidak** termasuk kontrak. (Bisa disediakan endpoint
> `/raw` terpisah bila perlu debug.)

### 4.1 Bentuk `data` per tipe

- **invoice / packing_list** → `array` record. Tiap record = header + `items[]`.
  - invoice item: `item_code, desc, hs_code, country_of_origin, net_weight, gross_weight, qty, unit_price, amount`
  - packing item: `item_code, desc, country_of_origin, net_weight, gross_weight, qty, measurement`
- **bill_of_lading** → `object` dengan `shipper/consignee/notify_party` (nested
  `{name, address, country, tax_id}`), `containers[]`, `packages`.
- **generic** → `object` flat key-value.

---

## 5. Event RabbitMQ (penyelesaian asinkron)

Saat job selesai/gagal, OCR Service **publish** ke RabbitMQ.

- **Exchange**: `ocr.results` (type `fanout`, durable)
- **Message** (JSON, persistent):

**Selesai**
```json
{
  "event": "ocr.completed",
  "job_id": "f3a1...",
  "timestamp": "2026-06-29T10:23:49+07:00",
  "result": { /* payload hasil bagian 4 */ }
}
```
**Gagal**
```json
{
  "event": "ocr.failed",
  "job_id": "f3a1...",
  "timestamp": "...",
  "error": { "code": "OCR_FAILED", "message": "Qwen timeout setelah 3 percobaan" }
}
```

Data Service consume exchange `ocr.results` → persist ke tabel (`invoices`/`invoice_items`/…)
+ blob → jika `needs_review` → masukkan antrian verifikasi petugas.

> Jika `options.callback_url` diisi, payload yang sama juga di-`POST` ke URL itu (webhook).

---

## 6. Kontrak Error

Envelope error seragam:
```json
{ "success": false, "data": null,
  "error": { "code": "FILE_NOT_FOUND", "message": "objek S3 tidak ditemukan" },
  "meta": { "timestamp": "..." } }
```
| Kode | Kapan |
|---|---|
| `BAD_REQUEST` | request tidak valid |
| `FILE_NOT_FOUND` | objek S3/MinIO tidak ada |
| `UNSUPPORTED_TYPE` | tipe file tidak didukung |
| `OCR_FAILED` | pipeline OCR gagal (mis. Qwen timeout) |
| `INTERNAL_ERROR` | error tak terduga |

---

## 7. Alur ringkas

```
Data Service simpan file -> S3
  -> POST /api/v1/ocr/jobs { job_id, file:{bucket,key} }      [202 accepted]
OCR Service: fetch S3 -> routing(pdfplumber/force-OCR) -> Qwen -> normalize -> validate
  -> publish "ocr.completed" { result } ke exchange ocr.results   [RabbitMQ]
Data Service: consume -> persist tabel + blob
  -> needs_review? -> antrian verifikasi petugas (HITL)
```

## 8. Konfigurasi (env)

| Variabel | Default | Fungsi |
|---|---|---|
| `RABBITMQ_URL` | `amqp://guest:guest@localhost:5672/` | Koneksi RabbitMQ |
| `OCR_EXCHANGE` | `ocr.results` | Nama exchange hasil |
| `OCR_JOB_TTL` | `3600` | TTL status job di Redis (detik) |
| `OCR_SERVICE_PORT` | `8092` | Port OCR Service |
