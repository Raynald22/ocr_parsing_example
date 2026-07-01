"""Entrypoint OCR Service:  python -m ocr"""

import os

import uvicorn

if __name__ == "__main__":
    uvicorn.run("ocr.api:app", host="0.0.0.0", port=int(os.getenv("OCR_SERVICE_PORT", "8092")))
