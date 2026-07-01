"""Pipeline OCR (use case / orkestrasi).

Menggabungkan: extraction (baca teks) -> deteksi tipe -> Qwen (schemas) ->
normalisasi -> validation/confidence. Murni Python; tidak tahu soal HTTP,
MinIO, Redis, atau RabbitMQ. Bisa dipakai ulang sebagai library:

    from ocr.pipeline import process_document
    result = process_document("invoice.pdf")
"""

import json
import os
import re
import time
from pathlib import Path
from typing import Callable, Optional

from .extraction import (
    doc_confidence, extract_tables, get_converter, get_ocr_converter,
    is_text_sparse, page_count, pdfplumber_text,
)
from .qwen import call_qwen, cap, generic_prompt
from .schemas import (
    build_extraction_prompt, coerce_and_normalize,
    detect_document_type, flatten_for_display,
)
from .validation import validate


def process_document(file_path: str, on_status: Optional[Callable] = None) -> dict:
    start = time.time()
    path = Path(file_path)
    steps = []

    def publish(step, status, detail):
        entry = {"step": step, "status": status, "detail": detail}
        steps.append(entry)
        if on_status:
            on_status(step, status, detail, round(time.time() - start, 2))

    # OCR — routing input bersih:
    #   PDF digital -> pdfplumber (layout, kolom tabel rapi)
    #   PDF gambar/scan -> Docling force full-page OCR (RapidOCR)
    #   non-PDF (docx/gambar) -> Docling default
    publish("OCR", "running", "Reading document...")
    t0 = time.time()
    is_pdf = path.suffix.lower() == ".pdf"
    ocr_forced = False
    tables = []

    if is_pdf:
        raw_text, num_pages = None, 1
        try:
            raw_text, num_pages = pdfplumber_text(path)
        except Exception as e:
            print(f"[OCR] pdfplumber gagal: {type(e).__name__}: {e}")

        if raw_text is not None and not is_text_sparse(raw_text, num_pages):
            confidence, source = 1.0, "pdfplumber"      # teks digital, bukan OCR
        else:
            publish("OCR", "running", "Teks tipis, OCR penuh (gambar/scan)...")
            doc_result = get_ocr_converter().convert(str(path))
            raw_text = doc_result.document.export_to_markdown()
            num_pages = page_count(doc_result.document)
            tables = extract_tables(doc_result.document)
            confidence = doc_confidence(doc_result.document)
            ocr_forced, source = True, "docling-ocr"
    else:
        doc_result = get_converter().convert(str(path))
        raw_text = doc_result.document.export_to_markdown()
        num_pages = page_count(doc_result.document)
        tables = extract_tables(doc_result.document)
        confidence = doc_confidence(doc_result.document)
        source = "docling"

    steps[-1]["elapsed_s"] = round(time.time() - t0, 2)
    publish("OCR", "ok", f"{len(raw_text)} chars · {source} · {round(confidence*100,1)}%")

    # Clean
    publish("Clean Text", "running", "Cleaning...")
    t0 = time.time()
    cleaned = _clean_text(raw_text)
    steps[-1]["elapsed_s"] = round(time.time() - t0, 2)
    publish("Clean Text", "ok", f"{len(raw_text)} → {len(cleaned)} chars")

    # Qwen — schema-driven bila tipe dokumen dikenali, generic KV bila tidak
    doc_type = detect_document_type(cleaned)
    publish("Qwen", "running", f"Extracting ({doc_type})...")
    t0 = time.time()
    if doc_type == "generic":
        raw_ai = call_qwen(generic_prompt(cap(cleaned)))
        structured = None
    else:
        prompt = build_extraction_prompt(doc_type, cap(cleaned), tables)
        raw_ai = call_qwen(prompt)
        structured = coerce_and_normalize(doc_type, raw_ai)
    steps[-1]["elapsed_s"] = round(time.time() - t0, 2)
    publish("Qwen", "ok", f"{doc_type}, {len(raw_ai)} keys")

    # Validate
    publish("Validate JSON", "running", "Validating...")
    t0 = time.time()

    if structured is not None:
        key_values = flatten_for_display(doc_type, structured)
    else:
        key_values = _normalize_kv(raw_ai)

    # Validation/confidence layer (deterministik) — sinyal HITL & audit
    validation = validate(doc_type, structured, confidence)
    if validation is not None:
        publish("Validate JSON", "ok",
                f"confidence {validation['confidence']}%, "
                f"{validation['summary']['errors']}E/{validation['summary']['warnings']}W"
                + (" — perlu review" if validation['needs_review'] else ""))
    else:
        publish("Validate JSON", "ok", f"{len(key_values)} fields extracted")

    steps[-1]["elapsed_s"] = round(time.time() - t0, 2)

    score = _compute_score(raw_text, cleaned, key_values, tables, confidence)

    review = None
    if validation is not None:
        s = validation["summary"]
        review = {
            "errors": s["errors"],
            "warnings": s["warnings"],
            "critical_errors": s["critical_errors"],
            "fields_scored": s["fields_scored"],
            "threshold": validation["threshold"],
            "issues": validation["issues"],
        }

    # Output berlapis & terbaca: kesimpulan di atas, data, review, lalu debug di `raw`.
    return {
        "document_type": doc_type,
        "confidence": validation["confidence"] if validation else None,
        "needs_review": validation["needs_review"] if validation else False,

        # data utama: terstruktur (invoice/packing/BL) atau flat key-value (generic)
        "data": structured if structured is not None else key_values,

        "review": review,

        "meta": {
            "filename": path.name,
            "pages": num_pages,
            "elapsed_s": round(time.time() - start, 2),
            "doc_confidence": round(confidence * 100, 1),
            "tables_found": len(tables),
            "ocr_engine": source,
            "ocr_forced": ocr_forced,
            "model": os.getenv("QWEN_MODEL", "qwen2.5:latest"),
            "ai_extraction": True,
            "pipeline_steps": steps,
        },

        # debug/mentah — dipisah supaya output utama enak dibaca
        "raw": {
            "extracted_text": raw_text,
            "tables": tables,
            "key_values": key_values,
            "score": score,
        },
    }


def _clean_text(text: str) -> str:
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    text = re.sub(r'[ \t]+', ' ', text)
    lines = [l.strip() for l in text.splitlines() if not re.match(r'^[-=_*|#]{3,}$', l.strip())]
    return re.sub(r'\n{3,}', '\n\n', '\n'.join(lines)).strip()


def _normalize_kv(raw: dict) -> dict:
    """Ratakan ekstraksi generic Qwen jadi dict key-value datar (untuk tipe 'generic')."""
    normalized = {}
    seen_keys = set()
    for k, v in raw.items():
        key = str(k).strip()
        if not key:
            continue
        dedup_key = key.lower()
        if dedup_key in seen_keys:
            continue
        if v in (None, "", [], {}):
            continue
        if isinstance(v, (dict, list)):
            value = json.dumps(v, ensure_ascii=False)
        elif isinstance(v, str):
            value = v.strip()
            if not value:
                continue
        else:
            value = v
        normalized[key] = value
        seen_keys.add(dedup_key)
    return normalized


def _compute_score(raw_text, cleaned, key_values, tables, ocr_confidence) -> dict:
    """Skor heuristik lama (didemote ke raw.score; TIDAK dipakai untuk keputusan).
    Gunakan validation.py untuk confidence/HITL."""
    text_len = len(cleaned)
    text_length_score = min(1.0, text_len / 200)
    clean_ratio = len(cleaned) / max(len(raw_text), 1)
    alpha_count = sum(1 for c in cleaned if c.isalnum())
    alpha_ratio = alpha_count / max(text_len, 1)
    text_quality = round((text_length_score * 0.3 + clean_ratio * 0.3 + alpha_ratio * 0.4) * 100, 1)

    method_score = 1.0
    field_count = len(key_values)
    field_score = min(1.0, field_count / 5)

    value_scores = []
    for v in key_values.values():
        s = str(v).strip()
        if not s:
            value_scores.append(0.0)
        elif len(s) < 2:
            value_scores.append(0.3)
        elif len(s) > 500:
            value_scores.append(0.5)
        else:
            value_scores.append(1.0)
    value_quality = sum(value_scores) / max(len(value_scores), 1)

    extraction = round((method_score * 0.4 + field_score * 0.35 + value_quality * 0.25) * 100, 1)
    ocr_score = round(ocr_confidence * 100, 1)
    has_tables = 1.0 if tables else 0.0
    has_fields = 1.0 if field_count >= 3 else field_count / 3
    completeness = round((has_fields * 0.7 + has_tables * 0.3) * 100, 1)

    overall = round(text_quality * 0.25 + extraction * 0.35 + ocr_score * 0.20 + completeness * 0.20, 1)

    return {
        "overall": overall,
        "text_quality": text_quality,
        "extraction": extraction,
        "ocr_confidence": ocr_score,
        "completeness": completeness,
        "breakdown": {
            "text_length": text_len,
            "fields_extracted": field_count,
            "tables_found": len(tables),
            "method": "Qwen AI",
        },
    }
