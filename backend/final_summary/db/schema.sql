-- =============================================================================
-- AUDIT REPORT DATABASE SCHEMA
-- =============================================================================
-- Database  : PostgreSQL 15+
-- Purpose   : Store extracted audit report data for fast querying by
--             factory, buyer, style, PO number, and date.
--
-- Table Map
-- ---------
--   factories          → one row per unique factory name
--   buyers             → one row per unique buyer/brand (e.g. UNIQLO)
--   styles             → one row per unique style (links to buyer + country)
--   purchase_orders    → one row per PO number (links to style)
--   audit_reports      → core audit record (one per Excel file)
--   audit_times        → factory/audit in-out times (1:1 with audit_reports)
--   shipment_dates     → EXF, PO EDT, PO WH, PLAN EDT, PLAN WH dates
--   defect_items       → one row per defect line (major/minor/comment)
--   delivery_orders    → D.O. plan table rows
--   validation_errors  → any validation errors found during extraction
--
-- Key design decisions
-- --------------------
--   1. Normalised lookup tables (factories, buyers, styles, POs) enable
--      fast JOINs and avoid scanning audit_reports for text matches.
--   2. Composite and partial indexes cover every common query pattern.
--   3. All date columns are DATE type for range queries.
--   4. Percentages stored as NUMERIC(6,3) — e.g. 3.714 for 3.714%.
--   5. Quantities stored as INTEGER; raw extracted string kept in po_qty_raw.
-- =============================================================================


-- ---------------------------------------------------------------------------
-- Extensions
-- ---------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS pg_trgm;   -- trigram index for LIKE searches


-- ---------------------------------------------------------------------------
-- LOOKUP TABLES
-- ---------------------------------------------------------------------------

CREATE TABLE factories (
    id          SERIAL      PRIMARY KEY,
    name        TEXT        NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_factory_name UNIQUE (name)
);
COMMENT ON TABLE factories IS 'One row per unique factory name.';

-- --

CREATE TABLE buyers (
    id          SERIAL      PRIMARY KEY,
    name        TEXT        NOT NULL,    -- e.g. "UNIQLO", "H&M"
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_buyer_name UNIQUE (name)
);
COMMENT ON TABLE buyers IS 'One row per unique buyer / brand.';

-- --

CREATE TABLE styles (
    id              SERIAL      PRIMARY KEY,
    buyer_id        INTEGER     NOT NULL REFERENCES buyers (id) ON DELETE RESTRICT,
    style_no        TEXT        NOT NULL,   -- e.g. "04336N068B"
    item_name       TEXT,                   -- e.g. "Premium linen shirt/L/YD"
    country         TEXT,                   -- destination country derived from style prefix
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_style_no UNIQUE (style_no)
);
COMMENT ON TABLE styles IS
    'One row per style number. Linked to buyer. country is derived from '
    'the first 2 characters of style_no (STYLE_COUNTRY_MAP).';

-- --

CREATE TABLE purchase_orders (
    id          SERIAL      PRIMARY KEY,
    style_id    INTEGER     NOT NULL REFERENCES styles (id) ON DELETE RESTRICT,
    po_no       TEXT        NOT NULL,   -- e.g. "P0426-485655-006"
    po_qty_raw  TEXT,                   -- raw extracted string e.g. "1200 PCS"
    po_qty_pcs  INTEGER     DEFAULT 0,
    po_qty_pack INTEGER     DEFAULT 0,
    po_qty_set  INTEGER     DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_po_no UNIQUE (po_no)
);
COMMENT ON TABLE purchase_orders IS
    'One row per PO number. Quantities are split by unit type.';


-- ---------------------------------------------------------------------------
-- CORE AUDIT REPORT TABLE
-- ---------------------------------------------------------------------------

CREATE TABLE audit_reports (
    id                  SERIAL          PRIMARY KEY,
    factory_id          INTEGER         NOT NULL REFERENCES factories (id) ON DELETE RESTRICT,
    style_id            INTEGER         NOT NULL REFERENCES styles (id)    ON DELETE RESTRICT,
    po_id               INTEGER         REFERENCES purchase_orders (id)    ON DELETE SET NULL,

    -- File source
    file_name           TEXT            NOT NULL,

    -- Report identity
    report_no           TEXT,           -- PO-format: P0426-485655-006-1-1
    audit_report_no     TEXT,           -- Report-format: EU26-02CIPL-001
    inspection_type     TEXT,           -- FINAL / RE-FINAL / INLINE / CMF / SAMPLE
    audit_result        TEXT,           -- PASS / FAIL / "-"
    date_of_issue       DATE,

    -- Quantities
    do_qty              INTEGER,
    ship_qty            INTEGER,
    audit_qty           INTEGER,
    defect_qty          INTEGER,
    acceptable_defect_qty INTEGER,
    defect_percentage   NUMERIC(6, 3),  -- e.g. 3.714 (stored without % sign)

    -- Personnel
    inspector           TEXT,
    person              TEXT,

    -- Additional checks
    carton              TEXT,
    needle_detector     TEXT,
    remarks             TEXT,
    do_set_col_size     TEXT,
    do_note             TEXT,

    -- Validation
    has_validation_errors BOOLEAN       NOT NULL DEFAULT FALSE,

    -- Audit trail
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT now(),

    CONSTRAINT uq_file_name UNIQUE (file_name)
);
COMMENT ON TABLE audit_reports IS
    'One row per extracted Excel audit file. Central fact table.';


-- ---------------------------------------------------------------------------
-- 1-to-1 EXTENSION TABLES
-- ---------------------------------------------------------------------------

CREATE TABLE audit_times (
    audit_report_id     INTEGER     PRIMARY KEY REFERENCES audit_reports (id) ON DELETE CASCADE,
    factory_in          TIME,
    factory_out         TIME,
    factory_total_hours NUMERIC(5, 2),
    audit_start         TIME,
    audit_end           TIME,
    audit_total_hours   NUMERIC(5, 2)
);
COMMENT ON TABLE audit_times IS
    'Factory in/out and audit start/end times. 1-to-1 with audit_reports.';

-- --

CREATE TABLE shipment_dates (
    audit_report_id     INTEGER     PRIMARY KEY REFERENCES audit_reports (id) ON DELETE CASCADE,
    exf                 DATE,       -- Ex-Factory date
    po_edt              DATE,       -- PO Estimated Delivery
    po_wh               DATE,       -- PO Warehouse / ship date
    plan_edt            DATE,       -- Plan Estimated Delivery
    plan_wh             DATE        -- Plan Warehouse
);
COMMENT ON TABLE shipment_dates IS
    'All 5 shipment-related dates. 1-to-1 with audit_reports.';


-- ---------------------------------------------------------------------------
-- 1-to-MANY CHILD TABLES
-- ---------------------------------------------------------------------------

CREATE TABLE defect_items (
    id              SERIAL      PRIMARY KEY,
    audit_report_id INTEGER     NOT NULL REFERENCES audit_reports (id) ON DELETE CASCADE,
    category        TEXT        NOT NULL,   -- e.g. "B : Sewing"
    item            TEXT        NOT NULL,   -- e.g. "3.Pieces not symmetrical"
    major_count     INTEGER     NOT NULL DEFAULT 0,
    minor_count     INTEGER     NOT NULL DEFAULT 0,
    comment         TEXT
);
COMMENT ON TABLE defect_items IS
    'One row per defect line item with a non-zero count. '
    'Auto-extracted from the Defects table in the Excel sheet.';

-- --

CREATE TABLE delivery_orders (
    id                      SERIAL      PRIMARY KEY,
    audit_report_id         INTEGER     NOT NULL REFERENCES audit_reports (id) ON DELETE CASCADE,
    do_date                 DATE,
    po_qty                  INTEGER,
    do_no                   TEXT,
    do_qty                  INTEGER,
    ship_qty                INTEGER,
    audit_qty               INTEGER,
    do_balance_and_extra    INTEGER,
    po_balance              INTEGER,
    remarks                 TEXT,
    special_note            TEXT,
    row_order               SMALLINT    NOT NULL DEFAULT 0   -- preserves table order
);
COMMENT ON TABLE delivery_orders IS
    'D.O. plan table rows. One row per delivery order line in the Excel sheet.';

-- --

CREATE TABLE validation_errors (
    id              SERIAL      PRIMARY KEY,
    audit_report_id INTEGER     NOT NULL REFERENCES audit_reports (id) ON DELETE CASCADE,
    error_message   TEXT        NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE validation_errors IS
    'One row per validation error message found for an audit report.';


-- =============================================================================
-- INDEXES
-- =============================================================================

-- factories
CREATE INDEX idx_factories_name_trgm
    ON factories USING gin (name gin_trgm_ops);

-- buyers
CREATE INDEX idx_buyers_name_trgm
    ON buyers USING gin (name gin_trgm_ops);

-- styles
CREATE INDEX idx_styles_buyer_id         ON styles (buyer_id);
CREATE INDEX idx_styles_country          ON styles (country);
CREATE INDEX idx_styles_style_no_trgm
    ON styles USING gin (style_no gin_trgm_ops);

-- purchase_orders
CREATE INDEX idx_po_style_id             ON purchase_orders (style_id);
CREATE INDEX idx_po_no_trgm
    ON purchase_orders USING gin (po_no gin_trgm_ops);

-- audit_reports — the most-queried table
CREATE INDEX idx_ar_factory_id           ON audit_reports (factory_id);
CREATE INDEX idx_ar_style_id             ON audit_reports (style_id);
CREATE INDEX idx_ar_po_id                ON audit_reports (po_id);
CREATE INDEX idx_ar_inspection_type      ON audit_reports (inspection_type);
CREATE INDEX idx_ar_audit_result         ON audit_reports (audit_result);
CREATE INDEX idx_ar_date_of_issue        ON audit_reports (date_of_issue);
CREATE INDEX idx_ar_date_of_issue_desc   ON audit_reports (date_of_issue DESC);
CREATE INDEX idx_ar_has_errors           ON audit_reports (has_validation_errors)
    WHERE has_validation_errors = TRUE;

-- Composite: factory + date (most common dashboard query)
CREATE INDEX idx_ar_factory_date
    ON audit_reports (factory_id, date_of_issue DESC);

-- Composite: style + date
CREATE INDEX idx_ar_style_date
    ON audit_reports (style_id, date_of_issue DESC);

-- Composite: PO + inspection type
CREATE INDEX idx_ar_po_type
    ON audit_reports (po_id, inspection_type);

-- shipment_dates
CREATE INDEX idx_sd_exf       ON shipment_dates (exf);
CREATE INDEX idx_sd_po_edt    ON shipment_dates (po_edt);
CREATE INDEX idx_sd_po_wh     ON shipment_dates (po_wh);
CREATE INDEX idx_sd_plan_edt  ON shipment_dates (plan_edt);
CREATE INDEX idx_sd_plan_wh   ON shipment_dates (plan_wh);

-- defect_items
CREATE INDEX idx_di_audit_report_id  ON defect_items (audit_report_id);
CREATE INDEX idx_di_category         ON defect_items (category);

-- delivery_orders
CREATE INDEX idx_do_audit_report_id  ON delivery_orders (audit_report_id);
CREATE INDEX idx_do_do_date          ON delivery_orders (do_date);

-- validation_errors
CREATE INDEX idx_ve_audit_report_id  ON validation_errors (audit_report_id);


-- =============================================================================
-- TRIGGER: auto-update updated_at on audit_reports
-- =============================================================================

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_audit_reports_updated_at
    BEFORE UPDATE ON audit_reports
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- =============================================================================
-- VIEWS  (pre-built for common queries)
-- =============================================================================

-- Full flat view: one row per audit report with all lookup names expanded
CREATE OR REPLACE VIEW v_audit_full AS
SELECT
    ar.id                       AS report_id,
    ar.file_name,
    f.name                      AS factory,
    b.name                      AS buyer,
    s.style_no,
    s.item_name,
    s.country,
    po.po_no,
    ar.inspection_type,
    ar.date_of_issue,
    ar.audit_result,
    ar.ship_qty,
    ar.audit_qty,
    ar.defect_qty,
    ar.defect_percentage,
    ar.inspector,
    ar.person,
    sd.exf,
    sd.po_edt,
    sd.po_wh,
    sd.plan_edt,
    sd.plan_wh,
    at_.factory_in,
    at_.factory_out,
    at_.factory_total_hours,
    at_.audit_start,
    at_.audit_end,
    at_.audit_total_hours,
    ar.has_validation_errors,
    ar.created_at
FROM       audit_reports     ar
JOIN       factories         f   ON f.id  = ar.factory_id
JOIN       styles            s   ON s.id  = ar.style_id
JOIN       buyers            b   ON b.id  = s.buyer_id
LEFT JOIN  purchase_orders   po  ON po.id = ar.po_id
LEFT JOIN  shipment_dates    sd  ON sd.audit_report_id = ar.id
LEFT JOIN  audit_times       at_ ON at_.audit_report_id = ar.id;

COMMENT ON VIEW v_audit_full IS
    'Flat denormalized view of every audit report. Use for reports and exports.';

-- --

-- Defect summary per report
CREATE OR REPLACE VIEW v_defect_summary AS
SELECT
    ar.id               AS report_id,
    ar.file_name,
    f.name              AS factory,
    s.style_no,
    ar.date_of_issue,
    ar.inspection_type,
    SUM(di.major_count) AS total_major,
    SUM(di.minor_count) AS total_minor,
    COUNT(di.id)        AS defect_line_count
FROM       audit_reports ar
JOIN       factories     f  ON f.id = ar.factory_id
JOIN       styles        s  ON s.id = ar.style_id
LEFT JOIN  defect_items  di ON di.audit_report_id = ar.id
GROUP BY ar.id, ar.file_name, f.name, s.style_no, ar.date_of_issue, ar.inspection_type;

COMMENT ON VIEW v_defect_summary IS
    'Aggregated major/minor defect counts per audit report.';
