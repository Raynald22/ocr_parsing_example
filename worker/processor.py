import json
import os
import re
import time
from pathlib import Path
from typing import Callable, Optional

import requests


def process_document(file_path: str, on_status: Optional[Callable] = None) -> dict:
    start = time.time()
    path = Path(file_path)
    steps = []

    def publish(step, status, detail):
        entry = {"step": step, "status": status, "detail": detail}
        steps.append(entry)
        if on_status:
            on_status(step, status, detail, round(time.time() - start, 2))

    # OCR
    publish("OCR", "running", "Reading document...")
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
    publish("OCR", "ok", f"{len(raw_text)} chars, {round(confidence*100,1)}%")

    # Clean
    publish("Clean Text", "running", "Cleaning...")
    t0 = time.time()
    cleaned = _clean_text(raw_text)
    steps[-1]["elapsed_s"] = round(time.time() - t0, 2)
    publish("Clean Text", "ok", f"{len(raw_text)} → {len(cleaned)} chars")

    # Qwen
    publish("Qwen", "running", "Extracting with AI...")
    t0 = time.time()
    raw_ai = _extract_with_qwen(cleaned)
    steps[-1]["elapsed_s"] = round(time.time() - t0, 2)

    if raw_ai:
        publish("Qwen", "ok", f"{len(raw_ai)} fields")
    else:
        publish("Qwen", "fallback", "Using regex fallback")

    # Validate
    publish("Validate JSON", "running", "Validating...")
    t0 = time.time()

    if raw_ai:
        key_values = {k: v for k, v in raw_ai.items() if v not in (None, "", [], {})}
        ai_result = {"key_values": key_values}
        ai_used = True
        publish("Validate JSON", "ok", f"{len(key_values)} fields extracted")
    else:
        key_values = _extract_kv_regex(cleaned)
        ai_result = None
        ai_used = False
        publish("Validate JSON", "skip", "No AI result")

    steps[-1]["elapsed_s"] = round(time.time() - t0, 2)

    return {
        "filename": path.name,
        "extracted_text": raw_text,
        "cleaned_text": cleaned,
        "tables": tables,
        "key_values": key_values,
        "ai_result": ai_result,
        "doc_confidence": round(confidence * 100, 1),
        "tables_found": len(tables),
        "kv_found": len(key_values),
        "passes": confidence * 100 >= 95.0,
        "ai_extraction": ai_used,
        "pipeline_steps": steps,
        "elapsed_s": round(time.time() - start, 2),
    }


def _extract_tables(document) -> list:
    tables = []
    try:
        for table in document.tables:
            grid = [[cell.text for cell in row] for row in table.data.grid]
            if grid:
                tables.append(grid)
    except Exception:
        pass
    return tables


def _clean_text(text: str) -> str:
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    text = re.sub(r'[ \t]+', ' ', text)
    lines = [l.strip() for l in text.splitlines() if not re.match(r'^[-=_*|#]{3,}$', l.strip())]
    return re.sub(r'\n{3,}', '\n\n', '\n'.join(lines)).strip()


def _extract_kv_regex(text: str) -> dict:
    kv = {}
    for line in text.splitlines():
        line = line.strip().lstrip('#*-> ').strip()
        if ':' not in line or len(line) > 300:
            continue
        key, _, val = line.partition(':')
        key, val = key.strip(), val.strip()
        if key and val and 3 <= len(key) <= 80 and len(val) <= 200 and key not in kv:
            kv[key] = val
    return kv


def _extract_with_qwen(text: str) -> dict:
    base_url = os.getenv("QWEN_BASE_URL", "http://localhost:11434")
    model = os.getenv("QWEN_MODEL", "qwen2.5:latest")
    timeout = int(os.getenv("QWEN_TIMEOUT", "300"))

    MAX_CHARS = 2000
    truncated = text[:MAX_CHARS] + ("\n[truncated]" if len(text) > MAX_CHARS else "")

    prompt = f"""Extract all key-value information from this document as a flat JSON object.

Rules:
- Output ONLY valid JSON, nothing else
- No markdown, no explanation, no code fences
- Use the exact field names from the document
- Skip empty/blank fields
- Numbers and dates: keep original format

Document:
{truncated}"""

    try:
        resp = requests.post(
            f"{base_url}/api/chat",
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": "You are a JSON extraction API. Respond ONLY with valid JSON."},
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
                "keep_alive": "10m",
                "options": {"temperature": 0, "num_predict": 800, "num_ctx": 2048, "num_gpu": 99},
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        response = resp.json()["message"]["content"].strip()

        start = response.find('{')
        if start == -1:
            return {}
        obj, _ = json.JSONDecoder().raw_decode(response, start)
        return obj

    except Exception as e:
        print(f"[Qwen] {type(e).__name__}: {e}")
        return {}
