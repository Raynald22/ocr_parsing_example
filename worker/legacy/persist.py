"""Map hasil ekstraksi (structured) -> tabel ternormalisasi per tipe dokumen.

Dipanggil dari worker.py setelah process_document; processor.py tetap murni
(tanpa DB). Idempotent: baris lama untuk job_id dihapus dulu (re-run aman, FK
ON DELETE CASCADE membersihkan items/containers).

Catatan: dijalankan dengan koneksi autocommit, jadi clear+insert tidak atomik —
tapi idempotent: kalau gagal di tengah, pemrosesan ulang job akan clear & ulang.
"""


def _txt(v):
    v = (v or "").strip() if isinstance(v, str) else v
    return None if v in (None, "", "-") else v


def _num(v):
    if v in (None, "", "-"):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _date(v):
    v = (v or "").strip()
    return v or None  # 'YYYY-MM-DD' atau None (psycopg2 cast ke DATE)


def persist(cur, job_id, doc_type, structured, confidence, needs_review):
    """structured: list (invoice/packing) atau dict (BL). None/generic -> no-op."""
    if structured is None:
        return
    _clear(cur, job_id)

    if doc_type == "invoice":
        for rec in structured:
            _insert_invoice(cur, job_id, rec, confidence, needs_review)
    elif doc_type == "packing_list":
        for rec in structured:
            _insert_packing(cur, job_id, rec, confidence, needs_review)
    elif doc_type == "bill_of_lading":
        _insert_bl(cur, job_id, structured, confidence, needs_review)


def _clear(cur, job_id):
    cur.execute("DELETE FROM invoices WHERE job_id = %s", (job_id,))
    cur.execute("DELETE FROM packing_lists WHERE job_id = %s", (job_id,))
    cur.execute("DELETE FROM bills_of_lading WHERE job_id = %s", (job_id,))


def _insert_invoice(cur, job_id, rec, conf, review):
    cur.execute(
        """INSERT INTO invoices
           (job_id, invoice_no, invoice_date, issuer_name, issuer_country,
            order_no, consignee, currency, incoterm, confidence, needs_review)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (job_id, _txt(rec.get("invoice_no")), _date(rec.get("invoice_date")),
         _txt(rec.get("invoice_issuer_name")), _txt(rec.get("invoice_issuer_country")),
         _txt(rec.get("order_no")), _txt(rec.get("consignee")),
         _txt(rec.get("currency")), _txt(rec.get("incoterm")), conf, review))
    inv_id = cur.fetchone()[0]
    for it in rec.get("items") or []:
        cur.execute(
            """INSERT INTO invoice_items
               (invoice_id, item_code, description, hs_code, country_of_origin,
                net_weight, gross_weight, qty, unit_price, amount)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (inv_id, _txt(it.get("item_code")), _txt(it.get("desc")),
             _txt(it.get("hs_code")), _txt(it.get("country_of_origin")),
             _num(it.get("net_weight")), _num(it.get("gross_weight")),
             _num(it.get("qty")), _num(it.get("unit_price")), _num(it.get("amount"))))


def _insert_packing(cur, job_id, rec, conf, review):
    cur.execute(
        """INSERT INTO packing_lists
           (job_id, invoice_no, invoice_date, order_no, consignee,
            vessel, container_no, seal_no, confidence, needs_review)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (job_id, _txt(rec.get("invoice_no")), _date(rec.get("invoice_date")),
         _txt(rec.get("order_no")), _txt(rec.get("consignee")),
         _txt(rec.get("vessel")), _txt(rec.get("container_no")),
         _txt(rec.get("seal_no")), conf, review))
    pl_id = cur.fetchone()[0]
    for it in rec.get("items") or []:
        cur.execute(
            """INSERT INTO packing_items
               (packing_list_id, item_code, description, country_of_origin,
                net_weight, gross_weight, qty, measurement)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
            (pl_id, _txt(it.get("item_code")), _txt(it.get("desc")),
             _txt(it.get("country_of_origin")), _num(it.get("net_weight")),
             _num(it.get("gross_weight")), _num(it.get("qty")), _num(it.get("measurement"))))


def _insert_bl(cur, job_id, rec, conf, review):
    sh = rec.get("shipper") or {}
    co = rec.get("consignee") or {}
    no = rec.get("notify_party") or {}
    pk = rec.get("packages") or {}
    cur.execute(
        """INSERT INTO bills_of_lading
           (job_id, bill_no, bill_no_date, document_type,
            shipper_name, shipper_country, shipper_tax_id,
            consignee_name, consignee_tax_id, notify_name,
            port_of_loading, port_of_discharge, place_of_delivery, place_of_receipt,
            vessel, voy_no, hs_code, gross_weight, measurement,
            total_packages, package_type, confidence, needs_review)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
           RETURNING id""",
        (job_id, _txt(rec.get("bill_no")), _date(rec.get("bill_no_date")), _txt(rec.get("document_type")),
         _txt(sh.get("name")), _txt(sh.get("country")), _txt(sh.get("tax_id")),
         _txt(co.get("name")), _txt(co.get("tax_id")), _txt(no.get("name")),
         _txt(rec.get("port_of_loading")), _txt(rec.get("port_of_discharge")),
         _txt(rec.get("place_of_delivery")), _txt(rec.get("place_of_receipt")),
         _txt(rec.get("vessel")), _txt(rec.get("voy_no")), _txt(rec.get("hs_code")),
         _num(rec.get("gross_weight")), _num(rec.get("measurement")),
         _num(pk.get("total_packages")), _txt(pk.get("package_type")), conf, review))
    bl_id = cur.fetchone()[0]
    for c in rec.get("containers") or []:
        cur.execute(
            """INSERT INTO bl_containers (bl_id, container_no, size, type, seal_no)
               VALUES (%s,%s,%s,%s,%s)""",
            (bl_id, _txt(c.get("container_no")), _txt(c.get("size")),
             _txt(c.get("type")), _txt(c.get("seal_no"))))
