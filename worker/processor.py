"""
processor.py
============
Pipeline Docling + Qwen untuk worker.
Reuse logic dari src/upload_processor.py, disesuaikan untuk async worker.
"""

import json
import os
import re
import time
from pathlib import Path
from typing import Callable, Optional

import requests


def process_document(
    file_path: str,
    on_status: Optional[Callable] = None,
) -> dict:
    """
    Jalankan pipeline dokumen: OCR -> Clean -> Qwen -> Validate.

    Args:
        file_path: path ke file lokal (sudah didownload dari MinIO)
        on_status: callback(step, status, detail) untuk publish progress

    Returns:
        dict hasil lengkap (disimpan ke PostgreSQL sebagai JSONB)
    """
    start = time.time()
    path = Path(file_path)
    steps = []

    def publish(step, status, detail):
        entry = {"step": step, "status": status, "detail": detail}
        steps.append(entry)
        if on_status:
            elapsed = round(time.time() - start, 2)
            on_status(step, status, detail, elapsed)

    # ── Step 1: OCR via Docling ────────────────────────────────────────────
    publish("OCR", "running", "Membaca dokumen dengan Docling...")

    from docling.document_converter import DocumentConverter

    t0 = time.time()
    converter = DocumentConverter()
    doc_result = converter.convert(str(path))
    raw_text = doc_result.document.export_to_markdown()

    try:
        confidence = float(doc_result.document.confidence_scores.mean_grade)
    except Exception:
        confidence = 1.0

    tables = _extract_tables(doc_result.document)

    steps[-1]["elapsed_s"] = round(time.time() - t0, 2)
    publish("OCR", "ok", f"{len(raw_text)} karakter, confidence {round(confidence*100,1)}%")

    # ── Step 2: Clean Text ─────────────────────────────────────────────────
    publish("Clean Text", "running", "Membersihkan teks...")
    t0 = time.time()
    cleaned = _clean_text(raw_text)
    steps[-1]["elapsed_s"] = round(time.time() - t0, 2)
    publish("Clean Text", "ok", f"{len(raw_text)} -> {len(cleaned)} karakter")

    # ── Step 3: Qwen AI ────────────────────────────────────────────────────
    publish("Qwen", "running", "Mengirim ke Qwen AI...")
    t0 = time.time()
    raw_ai = _extract_with_qwen(cleaned)

    if raw_ai:
        steps[-1]["elapsed_s"] = round(time.time() - t0, 2)
        publish("Qwen", "ok", f"JSON diterima ({len(raw_ai)} fields)")
    else:
        steps[-1]["elapsed_s"] = round(time.time() - t0, 2)
        publish("Qwen", "fallback", "Qwen tidak tersedia, pakai regex")

    # ── Step 4: Validate ───────────────────────────────────────────────────
    publish("Validate JSON", "running", "Memvalidasi hasil...")
    t0 = time.time()

    if raw_ai:
        key_values = {k: v for k, v in raw_ai.items() if v not in (None, "", [], {})}
        ai_result = {"key_values": key_values}
        ai_used = True
        publish("Validate JSON", "ok", f"{len(key_values)} field diekstrak")
    else:
        key_values = _extract_kv_regex(cleaned)
        ai_result = None
        ai_used = False
        publish("Validate JSON", "skip", "Tidak ada AI result")

    steps[-1]["elapsed_s"] = round(time.time() - t0, 2)

    elapsed = round(time.time() - start, 2)

    return {
        "filename":       path.name,
        "extracted_text":  raw_text,
        "cleaned_text":    cleaned,
        "tables":          tables,
        "key_values":      key_values,
        "ai_result":       ai_result,
        "doc_confidence":  round(confidence * 100, 1),
        "tables_found":    len(tables),
        "kv_found":        len(key_values),
        "passes":          confidence * 100 >= 95.0,
        "ai_extraction":   ai_used,
        "pipeline_steps":  steps,
        "elapsed_s":       elapsed,
    }


# ── Helpers ─────────────────────────────────────────────────────────────────

def _extract_tables(document) -> list:
    tables = []
    try:
        for table in document.tables:
            grid = []
            for row in table.data.grid:
                grid.append([cell.text for cell in row])
            if grid:
                tables.append(grid)
    except Exception:
        pass
    return tables


def _clean_text(text: str) -> str:
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    text = re.sub(r'[ \t]+', ' ', text)
    lines = []
    for line in text.splitlines():
        line = line.strip()
        if re.match(r'^[-=_*|#]{3,}$', line):
            continue
        lines.append(line)
    return re.sub(r'\n{3,}', '\n\n', '\n'.join(lines)).strip()


def _extract_kv_regex(text: str) -> dict:
    kv = {}
    for line in text.splitlines():
        line = line.strip().lstrip('#*-> ').strip()
        if ':' not in line or len(line) > 300:
            continue
        key, _, val = line.partition(':')
        key, val = key.strip(), val.strip()
        if key and val and 3 <= len(key) <= 80 and len(val) <= 200:
            if key not in kv:
                kv[key] = val
    return kv


def _extract_with_qwen(text: str) -> dict:
    base_url = os.getenv("QWEN_BASE_URL", "http://localhost:11434")
    model = os.getenv("QWEN_MODEL", "qwen2.5:latest")
    timeout = int(os.getenv("QWEN_TIMEOUT", "300"))

    MAX_CHARS = 2000
    text_for_qwen = text[:MAX_CHARS] + ("\n[dipotong]" if len(text) > MAX_CHARS else "")

    prompt = f"""Extract all key-value information from this document as a flat JSON object.

Rules:
- Output ONLY valid JSON, nothing else
- No markdown, no explanation, no code fences
- Use the exact field names from the document
- Skip empty/blank fields
- For lists (e.g. attachments), join with " | "
- Numbers and dates: keep original format

Output format:
{{"field1": "value1", "field2": "value2"}}

Document:
{text_for_qwen}"""

    try:
        resp = requests.post(
            f"{base_url}/api/chat",
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": "You are a JSON extraction API. Respond ONLY with a single valid JSON object. No markdown, no explanation, no code fences."},
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
                "keep_alive": "10m",
                "options": {
                    "temperature": 0,
                    "num_predict": 800,
                    "num_ctx": 2048,
                    "num_gpu": 99,
                },
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        response = resp.json()["message"]["content"].strip()
        print(f"[Qwen] Raw: {response[:200]}")

        start = response.find('{')
        if start == -1:
            return {}
        obj, _ = json.JSONDecoder().raw_decode(response, start)
        return obj

    except Exception as e:
        print(f"[Qwen] Error: {type(e).__name__}: {e}")
        return {}
