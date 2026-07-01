"""Klien LLM Qwen (via Ollama). Lapisan infra untuk ekstraksi schema-driven.

Hanya soal "panggil model + kembalikan JSON". Penyusunan prompt schema ada di
core/schemas.py; orkestrasi di pipeline.py.
"""

import json
import os
import time

import requests

QWEN_MAX_RETRIES = int(os.getenv("QWEN_MAX_RETRIES", "3"))
QWEN_RETRY_BACKOFF_S = float(os.getenv("QWEN_RETRY_BACKOFF_S", "2"))

# Dokumen shipping sering multi-halaman. Batas teks ke model besar & configurable;
# num_ctx/num_predict dinaikkan agar muat input + output.
QWEN_MAX_CHARS = int(os.getenv("QWEN_MAX_CHARS", "16000"))
QWEN_NUM_CTX = int(os.getenv("QWEN_NUM_CTX", "8192"))
QWEN_NUM_PREDICT = int(os.getenv("QWEN_NUM_PREDICT", "2048"))


def cap(text: str) -> str:
    if len(text) <= QWEN_MAX_CHARS:
        return text
    return text[:QWEN_MAX_CHARS] + "\n[truncated]"


def generic_prompt(text: str) -> str:
    return f"""Extract all key-value information from this document as a flat JSON object.

Rules:
- Output ONLY valid JSON, nothing else
- No markdown, no explanation, no code fences
- Use the exact field names from the document
- Skip empty/blank fields
- Numbers and dates: keep original format

Document:
{text}"""


def call_qwen(prompt: str) -> dict:
    """Panggil Qwen dengan prompt siap-pakai, kembalikan JSON terparse.
    Raise RuntimeError bila semua percobaan gagal (caller menandai job gagal)."""
    base_url = os.getenv("QWEN_BASE_URL", "http://localhost:11434")
    model = os.getenv("QWEN_MODEL", "qwen2.5:latest")
    timeout = int(os.getenv("QWEN_TIMEOUT", "300"))

    last_err = None
    for attempt in range(1, QWEN_MAX_RETRIES + 1):
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
                    "format": "json",
                    "options": {
                        "temperature": 0,
                        "num_predict": QWEN_NUM_PREDICT,
                        "num_ctx": QWEN_NUM_CTX,
                        "num_gpu": 99,
                    },
                },
                timeout=timeout,
            )
            resp.raise_for_status()
            response = resp.json()["message"]["content"].strip()

            start = response.find('{')
            if start == -1:
                raise ValueError("no JSON object in Qwen response")
            obj, _ = json.JSONDecoder().raw_decode(response, start)
            return obj

        except Exception as e:
            last_err = e
            print(f"[Qwen] attempt {attempt}/{QWEN_MAX_RETRIES} failed: {type(e).__name__}: {e}")
            if attempt < QWEN_MAX_RETRIES:
                time.sleep(QWEN_RETRY_BACKOFF_S * attempt)

    raise RuntimeError(f"Qwen extraction failed after {QWEN_MAX_RETRIES} attempts: {last_err}")
