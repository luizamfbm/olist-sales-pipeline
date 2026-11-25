-- Schema for the Olist sales pipeline.
-- Safe to run many times: every object uses IF NOT EXISTS.
--
--   olist.* : cleaned, typed business tables (one row per business key)
--   etl.*   : run log, per-file load stats, rejected rows and data quality findings

CREATE SCHEMA IF NOT EXISTS olist;
CREATE SCHEMA IF NOT EXISTS etl;

-- ---------------------------------------------------------------------------
-- Run log
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS etl.pipeline_runs (
    run_id       BIGSERIAL PRIMARY KEY,
    started_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at  TIMESTAMPTZ,
    status       TEXT NOT NULL CHECK (status IN ('running', 'success', 'failed')),
    data_dir     TEXT NOT NULL,
    error        TEXT
);

CREATE TABLE IF NOT EXISTS etl.file_loads (
    run_id                    BIGINT NOT NULL REFERENCES etl.pipeline_runs (run_id),
    source_file               TEXT   NOT NULL,
    file_sha256               TEXT   NOT NULL,
    rows_read                 INTEGER NOT NULL,
    exact_duplicates_dropped  INTEGER NOT NULL,
    rows_rejected             INTEGER NOT NULL,
    rows_inserted             INTEGER NOT NULL,
    rows_updated              INTEGER NOT NULL,
    rows_unchanged            INTEGER NOT NULL,
    PRIMARY KEY (run_id, source_file)
);

CREATE TABLE IF NOT EXISTS etl.rejected_rows (
    run_id       BIGINT NOT NULL REFERENCES etl.pipeline_runs (run_id),
    source_file  TEXT   NOT NULL,
    row_number   INTEGER,          -- data row number in the CSV (1 = first row after the header)
    reason       TEXT   NOT NULL,
    raw_record   JSONB  NOT NULL
);

CREATE TABLE IF NOT EXISTS etl.dq_findings (
    run_id          BIGINT NOT NULL REFERENCES etl.pipeline_runs (run_id),
    check_name      TEXT   NOT NULL,
    affected_rows   INTEGER NOT NULL,
    treatment       TEXT   NOT NULL,
    PRIMARY KEY (run_id, check_name)
);

-- ---------------------------------------------------------------------------
-- Business tables
-- Money is NUMERIC(12,2): exact decimal math, so the R$ 0.01 rule in the
-- reconciliation is never broken by floating point error.
-- Timestamps are local Brazil time as delivered in the files (no time zone).
-- last_run_id records the run that last inserted or changed the row.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS olist.customers (
    customer_id               TEXT PRIMARY KEY,
    customer_unique_id        TEXT NOT NULL,
    customer_zip_code_prefix  TEXT,          -- text, so leading zeros are kept
    customer_city             TEXT,
    customer_state            CHAR(2) NOT NULL,
    last_run_id               BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS olist.products (
    product_id                   TEXT PRIMARY KEY,
    product_category_name        TEXT,       -- NULL when the source has no category
    product_name_length          INTEGER,    -- source column is misspelled "lenght"
    product_description_length   INTEGER,
    product_photos_qty           INTEGER,
    product_weight_g             INTEGER,
    product_length_cm            INTEGER,
    product_height_cm            INTEGER,
    product_width_cm             INTEGER,
    last_run_id                  BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS olist.orders (
    order_id                        TEXT PRIMARY KEY,
    customer_id                     TEXT NOT NULL REFERENCES olist.customers (customer_id),
    order_status                    TEXT NOT NULL,
    order_purchase_timestamp        TIMESTAMP NOT NULL,
    order_approved_at               TIMESTAMP,
    order_delivered_carrier_date    TIMESTAMP,
    order_delivered_customer_date   TIMESTAMP,
    order_estimated_delivery_date   TIMESTAMP,
    last_run_id                     BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS olist.order_items (
    order_id             TEXT     NOT NULL REFERENCES olist.orders (order_id),
    order_item_id        INTEGER  NOT NULL,
    product_id           TEXT     NOT NULL REFERENCES olist.products (product_id),
    seller_id            TEXT     NOT NULL,
    shipping_limit_date  TIMESTAMP,
    price                NUMERIC(12, 2) NOT NULL CHECK (price >= 0),
    freight_value        NUMERIC(12, 2) NOT NULL CHECK (freight_value >= 0),
    last_run_id          BIGINT NOT NULL,
    PRIMARY KEY (order_id, order_item_id)
);

CREATE TABLE IF NOT EXISTS olist.order_payments (
    order_id              TEXT     NOT NULL REFERENCES olist.orders (order_id),
    payment_sequential    INTEGER  NOT NULL,
    payment_type          TEXT     NOT NULL,
    payment_installments  INTEGER  NOT NULL,
    payment_value         NUMERIC(12, 2) NOT NULL CHECK (payment_value >= 0),
    last_run_id           BIGINT NOT NULL,
    PRIMARY KEY (order_id, payment_sequential)
);

-- Indexes for the joins used by the business questions
CREATE INDEX IF NOT EXISTS ix_orders_customer   ON olist.orders (customer_id);
CREATE INDEX IF NOT EXISTS ix_orders_status_date ON olist.orders (order_status, order_purchase_timestamp);
CREATE INDEX IF NOT EXISTS ix_items_product     ON olist.order_items (product_id);
