"""Validation + confidence scoring (deterministik, explainable) untuk LNSW.

Metode scoring (disepakati):
  1. Per-field confidence (0..1), bukan satu angka gelondongan — supaya HITL tahu
     field MANA yang ragu.
  2. Weakest-link: tiap cek gagal MENG-CAP confidence field (error->0, warn->0.5),
     bukan mengurangi rata-rata. Field bagus tidak boleh menutupi field buruk.
  3. Bobot kekritisan: field fiskal (amount, qty, unit_price, hs_code, PO, NPWP)
     berbobot CRITICAL; deskripsi remeh MINOR.
  4. Confidence dokumen = rata-rata berbobot * OCR confidence.
  5. Gate HITL: ada critical-error ATAU confidence < ambang -> needs_review.
  6. Selalu sertakan daftar issue per-field -> auditable.

Cek kunci: amount == qty * unit_price -> menangkap error kolom tabel geser
('IDR 1' kebaca jadi unit_price=1). Error salah-tapi-konsisten butuh layer
reconciliation antar-dokumen (belum dibuat).

Tidak menyentuh _compute_score di processor.py — ini layer terpisah.
"""

import os
import re

REVIEW_CONFIDENCE_THRESHOLD = float(os.getenv("REVIEW_CONFIDENCE_THRESHOLD", "95"))
AMOUNT_TOLERANCE = float(os.getenv("AMOUNT_TOLERANCE", "0.01"))  # 1%

# bobot kekritisan field
CRITICAL, NORMAL, MINOR = 3, 2, 1

# cap confidence field saat sebuah cek gagal (weakest-link)
_CAP = {"error": 0.0, "warn": 0.5}

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_NPWP_RE = re.compile(r"^\d{15}$")


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _assess(name, weight, checks):
    """Nilai satu field. checks = list of (ok: bool, level, message).
    confidence mulai 1.0, di-cap setiap cek gagal."""
    conf = 1.0
    issues = []
    for ok, level, msg in checks:
        if not ok:
            issues.append({"field": name, "level": level, "message": msg})
            conf = min(conf, _CAP[level])
    return {"field": name, "weight": weight, "confidence": conf, "issues": issues}


# ---------------------------------------------------------------------------
# Penilai per tipe dokumen -> list of field-assessment
# ---------------------------------------------------------------------------

def _invoice_fields(rec, prefix=""):
    a = [
        _assess(prefix + "invoice_no", CRITICAL,
                [(bool(rec.get("invoice_no")), "error", "invoice_no kosong")]),
        _assess(prefix + "invoice_date", NORMAL,
                [(bool(_DATE_RE.match(rec.get("invoice_date") or "")), "warn", "tanggal bukan YYYY-MM-DD")]),
        _assess(prefix + "order_no", CRITICAL,
                [(bool(rec.get("order_no")), "warn", "order_no (PO) kosong")]),
    ]
    items = rec.get("items") or []
    if not items:
        a.append(_assess(prefix + "items", CRITICAL, [(False, "error", "tidak ada item")]))
    for i, it in enumerate(items, 1):
        f = f"{prefix}items[{i}]"
        qty, up, amt = _num(it.get("qty")), _num(it.get("unit_price")), _num(it.get("amount"))
        consistent = (not (qty > 0 and up > 0 and amt > 0)) or \
                     abs(qty * up - amt) / max(amt, 1) <= AMOUNT_TOLERANCE
        a += [
            _assess(f + ".item_code", CRITICAL, [(bool(it.get("item_code")), "warn", "kode barang kosong")]),
            _assess(f + ".qty", CRITICAL, [(qty > 0, "warn", "qty <= 0")]),
            _assess(f + ".unit_price", CRITICAL, [(up > 0, "warn", "unit_price <= 0")]),
            _assess(f + ".amount", CRITICAL, [
                (amt > 0, "warn", "amount <= 0"),
                (consistent, "error", f"amount {amt:.0f} != qty*unit_price ({qty * up:.0f})"),
            ]),
            _assess(f + ".desc", MINOR, [(bool(it.get("desc")), "warn", "deskripsi kosong")]),
        ]
    return a


def _packing_fields(rec, prefix=""):
    a = [
        _assess(prefix + "invoice_no", NORMAL,
                [(bool(rec.get("invoice_no")), "warn", "Com.Invoice# kosong")]),
        _assess(prefix + "order_no", CRITICAL,
                [(bool(rec.get("order_no")), "warn", "Consignee P/O kosong")]),
    ]
    items = rec.get("items") or []
    if not items:
        a.append(_assess(prefix + "items", CRITICAL, [(False, "error", "tidak ada item")]))
    for i, it in enumerate(items, 1):
        f = f"{prefix}items[{i}]"
        a += [
            _assess(f + ".item_code", CRITICAL, [(bool(it.get("item_code")), "warn", "kode barang kosong")]),
            _assess(f + ".qty", CRITICAL, [(_num(it.get("qty")) > 0, "warn", "qty <= 0")]),
            _assess(f + ".weight", NORMAL,
                    [(_num(it.get("net_weight")) > 0 or _num(it.get("gross_weight")) > 0,
                      "warn", "net & gross weight kosong")]),
        ]
    return a


def _bl_fields(rec):
    a = [
        _assess("bill_no", CRITICAL, [(bool(rec.get("bill_no")), "error", "bill_no kosong")]),
        _assess("bill_no_date", NORMAL,
                [(bool(_DATE_RE.match(rec.get("bill_no_date") or "")), "warn", "tanggal B/L bukan YYYY-MM-DD")]),
        _assess("port_of_loading", NORMAL, [(bool(rec.get("port_of_loading")), "warn", "port of loading kosong")]),
        _assess("port_of_discharge", NORMAL, [(bool(rec.get("port_of_discharge")), "warn", "port of discharge kosong")]),
        _assess("containers", CRITICAL, [(bool(rec.get("containers")), "warn", "tidak ada container")]),
    ]
    for party in ("shipper", "consignee"):
        p = rec.get(party) or {}
        tax = p.get("tax_id") or ""
        a.append(_assess(f"{party}.name", NORMAL, [(bool(p.get("name")), "warn", f"{party} kosong")]))
        a.append(_assess(f"{party}.tax_id", NORMAL,
                         [(not tax or bool(_NPWP_RE.match(tax)), "warn", "tax_id bukan 15 digit")]))
    return a


# ---------------------------------------------------------------------------
# Agregasi -> confidence dokumen
# ---------------------------------------------------------------------------

def _multi(records, fn):
    records = records or []
    multi = len(records) > 1
    out = []
    for i, rec in enumerate(records, 1):
        out += fn(rec or {}, f"doc{i}." if multi else "")
    return out


def _summarize(assessments, ocr_confidence):
    issues = [iss for a in assessments for iss in a["issues"]]
    errors = sum(1 for i in issues if i["level"] == "error")
    warnings = sum(1 for i in issues if i["level"] == "warn")
    critical_errors = sum(
        1 for a in assessments
        if a["weight"] == CRITICAL and any(i["level"] == "error" for i in a["issues"])
    )

    total_w = sum(a["weight"] for a in assessments) or 1
    weighted = sum(a["weight"] * a["confidence"] for a in assessments) / total_w
    confidence = round(weighted * ocr_confidence * 100, 1)

    needs_review = critical_errors > 0 or confidence < REVIEW_CONFIDENCE_THRESHOLD

    return {
        "confidence": confidence,
        "needs_review": needs_review,
        "threshold": REVIEW_CONFIDENCE_THRESHOLD,
        "summary": {
            "errors": errors,
            "warnings": warnings,
            "critical_errors": critical_errors,
            "fields_scored": len(assessments),
        },
        "issues": issues,
    }


def validate(doc_type, structured, ocr_confidence=1.0):
    """Skor confidence sesuai tipe dokumen. None untuk tipe generic."""
    if doc_type == "invoice":
        assessments = _multi(structured, _invoice_fields)
    elif doc_type == "packing_list":
        assessments = _multi(structured, _packing_fields)
    elif doc_type == "bill_of_lading":
        assessments = _bl_fields(structured or {})
    else:
        return None
    return _summarize(assessments, ocr_confidence)
