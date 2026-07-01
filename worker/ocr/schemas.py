"""Schema-driven extraction untuk dokumen shipping (invoice / packing list / BL).

Pipeline lama mengekstrak "flat key-value" generik tanpa tahu jenis dokumen.
Modul ini menambahkan:
  - deteksi tipe dokumen dari teks OCR
  - definisi schema per tipe (field + tipe + instruksi)
  - prompt builder yang menuntun Qwen mengikuti schema
  - normalisasi/coercion hasil Qwen (tanggal, angka, country, incoterm, tax_id)
  - flatten ke dict datar untuk panel "Konten Ditemukan" di UI (kontrak lama)

Sengaja tanpa dependency baru (schema hand-rolled) sesuai filosofi repo low-dep.
"""

import re

# ---------------------------------------------------------------------------
# Deteksi tipe dokumen
# ---------------------------------------------------------------------------

# (keyword, bobot) per tipe. Bobot lebih besar untuk frasa yang sangat khas.
_TYPE_SIGNALS = {
    "bill_of_lading": [
        ("BILL OF LADING", 3), ("SEA WAYBILL", 3), ("WAYBILL", 2),
        ("PORT OF LOADING", 2), ("PORT OF DISCHARGE", 2), ("B/L NO", 2),
        ("PLACE OF DELIVERY", 1), ("SHIPPER", 1), ("VESSEL", 1),
    ],
    "packing_list": [
        ("PACKING LIST", 3), ("SHIPPING ADVICE", 2), ("CASE MARK", 2),
        ("PACKED IN", 2), ("NET WEIGHT", 1), ("CARTONS", 1), ("PALLET", 1),
        ("N/W", 1), ("G/W", 1),
    ],
    "invoice": [
        ("PLEASE PAY THIS AMOUNT", 3), ("SOLD-TO-PARTY", 2), ("UNIT PRICE", 2),
        ("TERMS OF PAYMENT", 1), ("INVOICE", 2), ("SHIP-TO-PARTY", 1),
    ],
}


def detect_document_type(text: str) -> str:
    """Klasifikasi teks OCR ke salah satu tipe yang dikenal, atau 'generic'."""
    upper = text.upper()
    scores = {}
    for doc_type, signals in _TYPE_SIGNALS.items():
        scores[doc_type] = sum(weight for kw, weight in signals if kw in upper)

    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "generic"


# ---------------------------------------------------------------------------
# Normalisasi nilai
# ---------------------------------------------------------------------------

_MONTHS = {
    "JAN": 1, "FEB": 2, "MAR": 3, "MAC": 3, "APR": 4, "MAY": 5, "MEI": 5,
    "JUN": 6, "JUL": 7, "AUG": 8, "AGU": 8, "SEP": 9, "OCT": 10, "OKT": 10,
    "NOV": 11, "DEC": 12, "DES": 12,
}

_INCOTERMS = {
    "EXW", "FCA", "FAS", "FOB", "CFR", "CIF", "CPT", "CIP",
    "DAP", "DPU", "DDP", "DAT", "DDU",
}

# Dokumen sering menulis frasa, bukan kode (mis. "Free on board SHENZHEN").
_INCOTERM_PHRASES = [
    ("FREE ON BOARD", "FOB"),
    ("COST INSURANCE AND FREIGHT", "CIF"),
    ("COST AND FREIGHT", "CFR"),
    ("CARRIAGE AND INSURANCE PAID", "CIP"),
    ("CARRIAGE PAID", "CPT"),
    ("EX WORKS", "EXW"),
    ("FREE CARRIER", "FCA"),
    ("FREE ALONGSIDE", "FAS"),
    ("DELIVERED DUTY PAID", "DDP"),
    ("DELIVERED AT PLACE", "DAP"),
]

_COUNTRY = {
    "CHINA": "CN", "INDONESIA": "ID", "SINGAPORE": "SG", "JAPAN": "JP",
    "MALAYSIA": "MY", "THAILAND": "TH", "VIETNAM": "VN", "PHILIPPINES": "PH",
    "HONG KONG": "HK", "TAIWAN": "TW", "SOUTH KOREA": "KR", "KOREA": "KR",
    "INDIA": "IN", "GERMANY": "DE", "UNITED STATES": "US", "USA": "US",
}


def normalize_date(value) -> str:
    """Format tanggal apa pun ke YYYY-MM-DD; kembalikan apa adanya jika gagal."""
    if not value:
        return ""
    s = str(value).strip()

    # YYYY-MM-DD / YYYY/MM/DD / YYYY.MM.DD
    m = re.match(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", s)
    if m:
        y, mo, d = m.groups()
        return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"

    # DD-MM-YYYY / DD/MM/YYYY / DD.MM.YYYY
    m = re.match(r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})", s)
    if m:
        d, mo, y = m.groups()
        return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"

    # DD MON YYYY  (mis. 23/MAC/2026)
    m = re.search(r"(\d{1,2})[\s/.\-]+([A-Za-z]{3,})[\s/.\-]+(\d{4})", s)
    if m:
        d, mon, y = m.groups()
        mo = _MONTHS.get(mon[:3].upper())
        if mo:
            return f"{int(y):04d}-{mo:02d}-{int(d):02d}"

    # MON DD, YYYY  (mis. MAR.23,2026)
    m = re.search(r"([A-Za-z]{3,})[\s.]*(\d{1,2})[,\s]+(\d{4})", s)
    if m:
        mon, d, y = m.groups()
        mo = _MONTHS.get(mon[:3].upper())
        if mo:
            return f"{int(y):04d}-{mo:02d}-{int(d):02d}"

    return s


def normalize_incoterm(value) -> str:
    if not value:
        return ""
    up = str(value).upper()
    # cek kode 3-huruf yang berdiri sendiri dulu (mis. "FOB SHEKOU")
    for code in _INCOTERMS:
        if re.search(rf"\b{code}\b", up):
            return code
    for phrase, code in _INCOTERM_PHRASES:
        if phrase in up:
            return code
    return str(value).strip()


def normalize_country(value) -> str:
    if not value:
        return ""
    s = str(value).strip()
    if len(s) == 2 and s.isalpha():
        return s.upper()
    up = s.upper()
    for name, code in _COUNTRY.items():
        if name in up:
            return code
    return s


def to_number(value):
    """Parse angka dari string ber-format ('1,080,666.00' -> 1080666). 0 jika gagal."""
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return value
    s = str(value).strip()
    if not s:
        return 0
    neg = s.lstrip().startswith("-")
    s = re.sub(r"[^0-9.]", "", s)            # buang mata uang, koma ribuan, spasi
    if s.count(".") > 1:                      # '1.080.666' -> titik dianggap pemisah ribuan
        parts = s.split(".")
        s = "".join(parts[:-1]) + "." + parts[-1]
    if not s or s == ".":
        return 0
    try:
        num = float(s)
    except ValueError:
        return 0
    if neg:
        num = -num
    return int(num) if num.is_integer() else num


def digits_only(value) -> str:
    return re.sub(r"\D", "", str(value or ""))


def normalize_hs(value) -> str:
    """Rapikan HS/Tariff code: buang titik & spasi pemisah, pertahankan digit penuh.
    Multi-HS (mis. '852990, 844332') dipertahankan, dipisah koma. Jangan dipotong."""
    s = str(value or "").strip()
    if not s or s == "-":
        return s
    # buang titik & spasi (pemisah dalam satu kode), pertahankan digit + koma (multi-HS)
    s = re.sub(r"[.\s]+", "", s)
    s = re.sub(r",+", ", ", s)  # rapikan pemisah antar-HS
    return s.strip(", ")


_NORMALIZERS = {
    "string": lambda v: str(v).strip(),
    "number": to_number,
    "date": normalize_date,
    "incoterm": normalize_incoterm,
    "country": normalize_country,
    "taxid": digits_only,
    "hs": normalize_hs,
}


# ---------------------------------------------------------------------------
# Definisi schema
# ---------------------------------------------------------------------------
# Tiap field: {name, type, default, instruction}
#   type "array"  -> punya "item_fields"
#   type "object" -> punya "fields"
# "multi": True  -> satu file bisa berisi banyak dokumen (dibungkus "documents")

def _f(name, type, instruction, default=None):
    if default is None:
        default = 0 if type == "number" else ("-" if name in ("hs_code", "country_of_origin") else "")
    return {"name": name, "type": type, "instruction": instruction, "default": default}


_INVOICE_ITEM_FIELDS = [
    _f("item_code", "string",
       "Kode material/SKU = alfanumerik huruf+angka (mis. C13S210051, C31CL28432, "
       "V13H134A32). JANGAN ambil nomor baris 6-digit seperti 000010/000020 (itu "
       "kolom Item/C/O, bukan kode material)."),
    _f("desc", "string",
       "Deskripsi/nama barang lengkap (mis. 'TM-U220IID- E04, ANK+SC+SA FONT'). "
       "Jangan masukkan qty, harga, atau angka."),
    _f("hs_code", "hs",
       "Kode HS/Tariff barang = NUMERIK 6–10 digit (mis. 85299000), tanpa titik. "
       "BUKAN kode material/SKU (mis. C13S210051). Banyak invoice tidak "
       "mencantumkannya → '-'."),
    _f("country_of_origin", "country", "Negara asal (ISO-2). Jika tidak ada, '-'."),
    _f("net_weight", "number", "Net weight, angka saja. Jika tidak ada, 0."),
    _f("gross_weight", "number", "Gross weight, angka saja. Jika tidak ada, 0."),
    _f("qty", "number", "Quantity / Shipped Qty, angka saja."),
    _f("unit_price", "number",
       "Harga satuan = angka BESAR sebelum kode mata uang (mis. '1,590,396.00000 IDR' "
       "-> 1590396). JANGAN ambil angka '1' setelah mata uang (itu Price Unit), dan "
       "JANGAN pakai Amount. Jangan menghitung/membagi sendiri."),
    _f("amount", "number", "Total amount per item (kolom paling kanan) tanpa simbol mata uang."),
]

_PACKING_ITEM_FIELDS = [
    _f("item_code", "string",
       "Kode SAP/material barang. Jika satu baris memuat dua kode "
       "(mis. 'T6190000730 C13T619000'), pilih yang berawalan huruf seperti "
       "C13.../V13... (kode yang cocok dengan invoice)."),
    _f("desc", "string", "Deskripsi/nama barang."),
    _f("country_of_origin", "country", "Negara asal (ISO-2). Jika tidak ada, '-'."),
    _f("net_weight", "number", "Net weight (N/W), angka saja."),
    _f("gross_weight", "number", "Gross weight (G/W), angka saja."),
    _f("qty", "number", "Quantity (PC), angka saja."),
    _f("measurement", "number", "Measurement/CBM, angka saja."),
]

_PARTY_FIELDS = lambda role: [
    _f("name", "string", f"Nama {role}."),
    _f("address", "string", f"Alamat lengkap {role} satu baris."),
    _f("country", "country", f"Negara {role} (ISO-2)."),
    _f("tax_id", "taxid", f"Tax ID / NPWP {role}, digit saja."),
]


SCHEMAS = {
    "invoice": {
        "title": "Commercial Invoice",
        "multi": True,
        "fields": [
            _f("invoice_no", "string", "Nomor invoice dari label 'Number/Date' (mis. '295730125 / 21.03.2026' -> 295730125)."),
            _f("invoice_date", "date", "Tanggal dari label 'Number/Date' -> YYYY-MM-DD."),
            _f("invoice_issuer_name", "string",
               "Nama penjual/seller di kop atas dokumen (mis. EPSON SINGAPORE PTE. LTD.). "
               "JANGAN pakai Sold-To/Ship-To/consignee. Jika tidak ada di teks, kosongkan ''."),
            _f("invoice_issuer_country", "country", "Negara penjual (ISO-2). Jika tidak ada, kosongkan."),
            _f("order_no", "string",
               "Purchase Order No (mis. 4501643539, biasa diawali 45). JANGAN ambil "
               "'Order number/Date' (mis. 1003267003) atau 'Customer number'."),
            _f("consignee", "string", "Nama consignee / Sold-To / Ship-To party."),
            _f("currency", "string", "Mata uang (ISO 4217: USD/IDR/EUR)."),
            _f("incoterm", "incoterm", "Incoterm/Trade Terms, kode 3 huruf (FOB/CIF/...)."),
            {"name": "items", "type": "array", "instruction": "Semua baris item invoice.",
             "default": [], "item_fields": _INVOICE_ITEM_FIELDS},
        ],
    },
    "packing_list": {
        "title": "Packing List",
        "multi": True,
        "fields": [
            _f("invoice_no", "string", "Com. Invoice# (mis. ESL-0176089)."),
            _f("invoice_date", "date", "Issue Date -> YYYY-MM-DD."),
            _f("order_no", "string",
               "Consignee P/O (BUKAN Cust P/O). Jika ada 'Consignee P/O:4501648463' "
               "dan 'Cust P/O:B0...', ambil yang Consignee P/O."),
            _f("consignee", "string", "Nama consignee (Consigned to)."),
            _f("vessel", "string", "Nama vessel / Shipped per."),
            _f("container_no", "string", "Nomor container."),
            _f("seal_no", "string", "Nomor seal."),
            {"name": "items", "type": "array",
             "instruction": "Satu object per baris produk fisik; jangan pecah satu baris jadi banyak item.",
             "default": [], "item_fields": _PACKING_ITEM_FIELDS},
        ],
    },
    "bill_of_lading": {
        "title": "Bill of Lading / Sea Waybill",
        "multi": False,
        "fields": [
            _f("bill_no", "string", "B/L No / Document No."),
            _f("bill_no_date", "date", "Tanggal B/L -> YYYY-MM-DD."),
            _f("document_type", "string", "OCEAN atau AIR."),
            {"name": "shipper", "type": "object", "instruction": "", "default": {},
             "fields": _PARTY_FIELDS("shipper")},
            {"name": "consignee", "type": "object", "instruction": "", "default": {},
             "fields": _PARTY_FIELDS("consignee")},
            {"name": "notify_party", "type": "object", "instruction": "", "default": {},
             "fields": _PARTY_FIELDS("notify party")},
            _f("port_of_loading", "string", "Port of Loading."),
            _f("port_of_discharge", "string", "Port of Discharge."),
            _f("place_of_delivery", "string", "Place of Delivery."),
            _f("place_of_receipt", "string", "Place of Receipt."),
            _f("vessel", "string", "Nama vessel."),
            _f("voy_no", "string", "Voyage No."),
            _f("description_of_goods", "string", "Deskripsi barang (boleh multi-baris jadi satu string)."),
            _f("hs_code", "hs",
               "Semua HS code yang tercantum (mis. dari 'H.S.CODE: 852990, 844332, "
               "844399'). Pertahankan LENGKAP & numerik, JANGAN dipotong; pisah koma "
               "bila lebih dari satu."),
            _f("gross_weight", "number", "Gross weight total (KGS), angka saja."),
            _f("measurement", "number", "Measurement total (CBM/M3), angka saja."),
            {"name": "containers", "type": "array", "instruction": "Daftar container.",
             "default": [], "item_fields": [
                 _f("container_no", "string", "Nomor container."),
                 _f("size", "string", "Ukuran (mis. 20/40)."),
                 _f("type", "string", "Tipe container."),
                 _f("seal_no", "string", "Nomor seal."),
             ]},
            {"name": "packages", "type": "object", "instruction": "", "default": {},
             "fields": [
                 _f("total_packages", "number", "Jumlah package/pallet."),
                 _f("package_type", "string", "Tipe package (PALLETS/CARTONS/...)."),
             ]},
        ],
    },
}


# ---------------------------------------------------------------------------
# Coercion / normalisasi hasil Qwen sesuai schema
# ---------------------------------------------------------------------------

def _coerce_value(field, value):
    ftype = field["type"]
    if ftype == "object":
        return _coerce_record(field["fields"], value if isinstance(value, dict) else {})
    if ftype == "array":
        if not isinstance(value, list):
            return list(field["default"])
        out = []
        for item in value:
            if isinstance(item, dict):
                out.append(_coerce_record(field["item_fields"], item))
        return out

    if value in (None, ""):
        return field["default"]
    norm = _NORMALIZERS.get(ftype, _NORMALIZERS["string"])
    try:
        result = norm(value)
    except Exception:
        return field["default"]
    if result == "" and ftype != "string":
        return field["default"]
    return result if result != "" else field["default"]


def _coerce_record(fields, raw: dict) -> dict:
    record = {}
    for field in fields:
        record[field["name"]] = _coerce_value(field, raw.get(field["name"]))
    return record


def coerce_and_normalize(doc_type: str, raw):
    """Ubah JSON mentah dari Qwen menjadi struktur ternormalisasi sesuai schema."""
    schema = SCHEMAS[doc_type]

    if schema["multi"]:
        if isinstance(raw, list):
            records = raw
        elif isinstance(raw, dict) and isinstance(raw.get("documents"), list):
            records = raw["documents"]
        elif isinstance(raw, dict):
            records = [raw]                  # model balas satu record langsung
        else:
            records = []
        return [_coerce_record(schema["fields"], r) for r in records if isinstance(r, dict)]

    # single-doc (BL)
    rec = raw
    if isinstance(raw, dict) and isinstance(raw.get("documents"), list) and raw["documents"]:
        rec = raw["documents"][0]
    return _coerce_record(schema["fields"], rec if isinstance(rec, dict) else {})


# ---------------------------------------------------------------------------
# Flatten untuk panel "Konten Ditemukan" (UI lama membaca key_values datar)
# ---------------------------------------------------------------------------

def flatten_for_display(doc_type: str, structured) -> dict:
    out = {}

    def walk(prefix, value):
        if isinstance(value, dict):
            for k, v in value.items():
                walk(f"{prefix}.{k}" if prefix else k, v)
        elif isinstance(value, list):
            if value:
                out[f"{prefix} (count)" if prefix else "count"] = len(value)
            for i, item in enumerate(value, 1):
                walk(f"{prefix}[{i}]", item)
        else:
            if value not in (None, "", "-", 0):
                out[prefix] = value

    if isinstance(structured, list):
        if len(structured) == 1:
            walk("", structured[0])
        else:
            for i, rec in enumerate(structured, 1):
                walk(f"doc{i}", rec)
    else:
        walk("", structured)
    return out


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def _describe_fields(fields, indent=0) -> list:
    pad = "  " * indent
    lines = []
    for f in fields:
        if f["type"] == "array":
            lines.append(f'{pad}- "{f["name"]}": array of objects — {f["instruction"]} Each object:')
            lines.extend(_describe_fields(f["item_fields"], indent + 1))
        elif f["type"] == "object":
            lines.append(f'{pad}- "{f["name"]}": object with:')
            lines.extend(_describe_fields(f["fields"], indent + 1))
        else:
            lines.append(f'{pad}- "{f["name"]}": {f["instruction"]}')
    return lines


def _render_tables(tables, max_rows=40) -> str:
    out = []
    for ti, tbl in enumerate(tables, 1):
        out.append(f"[table {ti}]")
        for row in tbl[:max_rows]:
            out.append(" | ".join(str(c) for c in row))
    return "\n".join(out)


def build_extraction_prompt(doc_type: str, text: str, tables=None) -> str:
    schema = SCHEMAS[doc_type]
    field_desc = "\n".join(_describe_fields(schema["fields"]))

    if schema["multi"]:
        shape = '{"documents": [ { ...one object per document... } ]}'
        multi_note = (
            f"This file may contain MULTIPLE {schema['title']} documents. "
            'Return one object per document inside "documents".\n'
            "IMPORTANT: one document can span several pages, and its number/header may "
            'repeat on a continuation page (e.g. page "1/2" then "2/2"). Treat the SAME '
            "document number as ONE document — merge its items, do NOT create a duplicate "
            "record. Never copy items from one document into another."
        )
    else:
        shape = "{ ...single JSON object... }"
        multi_note = f"Return a single JSON object for this {schema['title']}."

    tables_block = ""
    if tables:
        tables_block = f"\n\nDetected tables (use these for line items):\n{_render_tables(tables)}"

    return f"""You extract structured data from a {schema['title']}.

{multi_note}

Output ONLY valid JSON in this shape:
{shape}

Fields to extract:
{field_desc}

General rules:
- Output ONLY JSON. No markdown, no explanation, no code fences.
- Read every value EXACTLY as printed. Do NOT calculate, sum, derive, or guess numbers
  (e.g. never compute unit_price from amount/qty, or amount from qty*price).
- Each printed line/row is ONE item object; keep items only under the document they belong to.
- Use only what is in the text; if unsure, use the default rather than inventing a value.
- Missing field -> use its default ("" for text, 0 for numbers, "-" where noted).
- Numbers: digits only, no thousand separators or currency symbols.
- Dates: format as YYYY-MM-DD.

Document text:
{text}{tables_block}"""
