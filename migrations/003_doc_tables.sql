-- Tabel ternormalisasi per tipe dokumen (turunan dari jobs.result JSONB).
-- Blob `jobs.result` tetap disimpan untuk audit; tabel ini untuk query & rekonsiliasi.

-- ---------- Invoice ----------
CREATE TABLE IF NOT EXISTS invoices (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    job_id          UUID REFERENCES jobs(id) ON DELETE CASCADE,
    invoice_no      TEXT,
    invoice_date    DATE,
    issuer_name     TEXT,
    issuer_country  TEXT,
    order_no        TEXT,
    consignee       TEXT,
    currency        TEXT,
    incoterm        TEXT,
    confidence      NUMERIC,
    needs_review    BOOLEAN,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS invoice_items (
    id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    invoice_id        UUID REFERENCES invoices(id) ON DELETE CASCADE,
    item_code         TEXT,
    description       TEXT,
    hs_code           TEXT,
    country_of_origin TEXT,
    net_weight        NUMERIC,
    gross_weight      NUMERIC,
    qty               NUMERIC,
    unit_price        NUMERIC,
    amount            NUMERIC
);

-- ---------- Packing List ----------
CREATE TABLE IF NOT EXISTS packing_lists (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    job_id        UUID REFERENCES jobs(id) ON DELETE CASCADE,
    invoice_no    TEXT,
    invoice_date  DATE,
    order_no      TEXT,
    consignee     TEXT,
    vessel        TEXT,
    container_no  TEXT,
    seal_no       TEXT,
    confidence    NUMERIC,
    needs_review  BOOLEAN,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS packing_items (
    id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    packing_list_id   UUID REFERENCES packing_lists(id) ON DELETE CASCADE,
    item_code         TEXT,
    description       TEXT,
    country_of_origin TEXT,
    net_weight        NUMERIC,
    gross_weight      NUMERIC,
    qty               NUMERIC,
    measurement       NUMERIC
);

-- ---------- Bill of Lading ----------
CREATE TABLE IF NOT EXISTS bills_of_lading (
    id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    job_id            UUID REFERENCES jobs(id) ON DELETE CASCADE,
    bill_no           TEXT,
    bill_no_date      DATE,
    document_type     TEXT,
    shipper_name      TEXT,
    shipper_country   TEXT,
    shipper_tax_id    TEXT,
    consignee_name    TEXT,
    consignee_tax_id  TEXT,
    notify_name       TEXT,
    port_of_loading   TEXT,
    port_of_discharge TEXT,
    place_of_delivery TEXT,
    place_of_receipt  TEXT,
    vessel            TEXT,
    voy_no            TEXT,
    hs_code           TEXT,
    gross_weight      NUMERIC,
    measurement       NUMERIC,
    total_packages    NUMERIC,
    package_type      TEXT,
    confidence        NUMERIC,
    needs_review      BOOLEAN,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS bl_containers (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    bl_id        UUID REFERENCES bills_of_lading(id) ON DELETE CASCADE,
    container_no TEXT,
    size         TEXT,
    type         TEXT,
    seal_no      TEXT
);

-- ---------- Index (lookup + rekonsiliasi lintas dokumen) ----------
CREATE INDEX IF NOT EXISTS idx_invoices_job       ON invoices (job_id);
CREATE INDEX IF NOT EXISTS idx_invoices_order_no  ON invoices (order_no);
CREATE INDEX IF NOT EXISTS idx_invoice_items_inv  ON invoice_items (invoice_id);
CREATE INDEX IF NOT EXISTS idx_packing_job        ON packing_lists (job_id);
CREATE INDEX IF NOT EXISTS idx_packing_order_no   ON packing_lists (order_no);
CREATE INDEX IF NOT EXISTS idx_packing_items_pl   ON packing_items (packing_list_id);
CREATE INDEX IF NOT EXISTS idx_bl_job             ON bills_of_lading (job_id);
CREATE INDEX IF NOT EXISTS idx_bl_bill_no         ON bills_of_lading (bill_no);
CREATE INDEX IF NOT EXISTS idx_bl_containers_no   ON bl_containers (container_no);
