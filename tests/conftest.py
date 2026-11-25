"""Test setup.

Tests need a running PostgreSQL (the same one from docker-compose works).
They use a separate database, olist_test, created on first use. The olist and
etl schemas are dropped before every test, so each test starts empty.

All test data is fictitious and written as small CSV files with the same
headers as the real Olist files.
"""
from __future__ import annotations

import csv
from pathlib import Path

import psycopg
import pytest

from pipeline.config import db_settings
from pipeline.queries import run_query
from pipeline.run import run_pipeline

TEST_DB = "olist_test"

HEADERS = {
    "olist_customers_dataset.csv": [
        "customer_id", "customer_unique_id", "customer_zip_code_prefix", "customer_city", "customer_state",
    ],
    "olist_products_dataset.csv": [
        "product_id", "product_category_name", "product_name_lenght", "product_description_lenght",
        "product_photos_qty", "product_weight_g", "product_length_cm", "product_height_cm", "product_width_cm",
    ],
    "olist_orders_dataset.csv": [
        "order_id", "customer_id", "order_status", "order_purchase_timestamp", "order_approved_at",
        "order_delivered_carrier_date", "order_delivered_customer_date", "order_estimated_delivery_date",
    ],
    "olist_order_items_dataset.csv": [
        "order_id", "order_item_id", "product_id", "seller_id", "shipping_limit_date", "price", "freight_value",
    ],
    "olist_order_payments_dataset.csv": [
        "order_id", "payment_sequential", "payment_type", "payment_installments", "payment_value",
    ],
}


@pytest.fixture(scope="session", autouse=True)
def test_database():
    with psycopg.connect(**db_settings("postgres"), autocommit=True) as conn:
        exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (TEST_DB,)).fetchone()
        if not exists:
            conn.execute(f"CREATE DATABASE {TEST_DB}")
    yield


@pytest.fixture(autouse=True)
def clean_schemas():
    with psycopg.connect(**db_settings(TEST_DB), autocommit=True) as conn:
        conn.execute("DROP SCHEMA IF EXISTS olist CASCADE")
        conn.execute("DROP SCHEMA IF EXISTS etl CASCADE")
    yield


class Dataset:
    """Builds a tiny fictitious Olist dataset in a temp folder."""

    def __init__(self, folder: Path):
        self.folder = folder
        self.rows: dict[str, list[dict]] = {name: [] for name in HEADERS}

    def customer(self, customer_id, state="SP"):
        self.rows["olist_customers_dataset.csv"].append({
            "customer_id": customer_id, "customer_unique_id": f"u-{customer_id}",
            "customer_zip_code_prefix": "01310", "customer_city": "sao paulo", "customer_state": state,
        })
        return self

    def product(self, product_id, category):
        self.rows["olist_products_dataset.csv"].append({
            "product_id": product_id, "product_category_name": category or "",
            "product_name_lenght": "40", "product_description_lenght": "300", "product_photos_qty": "1",
            "product_weight_g": "500", "product_length_cm": "20", "product_height_cm": "10", "product_width_cm": "15",
        })
        return self

    def order(self, order_id, customer_id, status="delivered", purchased="2018-01-15 10:00:00"):
        self.rows["olist_orders_dataset.csv"].append({
            "order_id": order_id, "customer_id": customer_id, "order_status": status,
            "order_purchase_timestamp": purchased, "order_approved_at": purchased,
            "order_delivered_carrier_date": purchased if status == "delivered" else "",
            "order_delivered_customer_date": "2018-01-31 12:00:00" if status == "delivered" else "",
            "order_estimated_delivery_date": "2018-02-01 00:00:00",
        })
        return self

    def item(self, order_id, item_no, product_id, price, freight):
        self.rows["olist_order_items_dataset.csv"].append({
            "order_id": order_id, "order_item_id": str(item_no), "product_id": product_id,
            "seller_id": "seller-1", "shipping_limit_date": "2018-01-20 10:00:00",
            "price": price, "freight_value": freight,
        })
        return self

    def payment(self, order_id, seq, value, ptype="credit_card", installments="1"):
        self.rows["olist_order_payments_dataset.csv"].append({
            "order_id": order_id, "payment_sequential": str(seq), "payment_type": ptype,
            "payment_installments": installments, "payment_value": value,
        })
        return self

    def write(self) -> Path:
        self.folder.mkdir(parents=True, exist_ok=True)
        for name, header in HEADERS.items():
            with (self.folder / name).open("w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=header)
                writer.writeheader()
                writer.writerows(self.rows[name])
        return self.folder


@pytest.fixture
def dataset(tmp_path) -> Dataset:
    return Dataset(tmp_path / "data")


@pytest.fixture
def run():
    """Run the pipeline against the test database."""
    def _run(folder: Path):
        return run_pipeline(folder, TEST_DB)
    return _run


@pytest.fixture
def query():
    """Run one of the business questions against the test database."""
    def _query(name: str):
        with psycopg.connect(**db_settings(TEST_DB)) as conn:
            return run_query(conn, name)
    return _query


@pytest.fixture
def db():
    """Plain SQL access to the test database."""
    def _db(sql: str, params=None):
        with psycopg.connect(**db_settings(TEST_DB)) as conn:
            return conn.execute(sql, params).fetchall()
    return _db
