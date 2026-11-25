"""Source file specs and database settings.

Each source describes how one CSV maps to one table: column types, which
columns are required, the primary key, and any column renames.
Sources are listed in load order: parents before children, so foreign keys
can be checked against rows that are already loaded.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Source:
    name: str                      # short name, also used in logs
    file_name: str                 # CSV file expected in the data directory
    table: str                     # target table in the "olist" schema
    columns: dict[str, str]        # target column -> type (text, int, money, timestamp, state)
    primary_key: list[str]
    required: list[str]            # columns that cannot be empty
    renames: dict[str, str] = field(default_factory=dict)  # source column -> target column
    # (child columns, parent table, parent columns): rows whose parent does not
    # exist are rejected instead of breaking the load
    references: list[tuple[list[str], str, list[str]]] = field(default_factory=list)


SOURCES: list[Source] = [
    Source(
        name="customers",
        file_name="olist_customers_dataset.csv",
        table="customers",
        columns={
            "customer_id": "text",
            "customer_unique_id": "text",
            "customer_zip_code_prefix": "text",
            "customer_city": "text",
            "customer_state": "state",
        },
        primary_key=["customer_id"],
        required=["customer_id", "customer_unique_id", "customer_state"],
    ),
    Source(
        name="products",
        file_name="olist_products_dataset.csv",
        table="products",
        columns={
            "product_id": "text",
            "product_category_name": "text",
            "product_name_length": "int",
            "product_description_length": "int",
            "product_photos_qty": "int",
            "product_weight_g": "int",
            "product_length_cm": "int",
            "product_height_cm": "int",
            "product_width_cm": "int",
        },
        primary_key=["product_id"],
        required=["product_id"],
        renames={
            "product_name_lenght": "product_name_length",
            "product_description_lenght": "product_description_length",
        },
    ),
    Source(
        name="orders",
        file_name="olist_orders_dataset.csv",
        table="orders",
        columns={
            "order_id": "text",
            "customer_id": "text",
            "order_status": "status",
            "order_purchase_timestamp": "timestamp",
            "order_approved_at": "timestamp",
            "order_delivered_carrier_date": "timestamp",
            "order_delivered_customer_date": "timestamp",
            "order_estimated_delivery_date": "timestamp",
        },
        primary_key=["order_id"],
        required=["order_id", "customer_id", "order_status", "order_purchase_timestamp"],
        references=[(["customer_id"], "customers", ["customer_id"])],
    ),
    Source(
        name="order_items",
        file_name="olist_order_items_dataset.csv",
        table="order_items",
        columns={
            "order_id": "text",
            "order_item_id": "int",
            "product_id": "text",
            "seller_id": "text",
            "shipping_limit_date": "timestamp",
            "price": "money",
            "freight_value": "money",
        },
        primary_key=["order_id", "order_item_id"],
        required=["order_id", "order_item_id", "product_id", "seller_id", "price", "freight_value"],
        references=[
            (["order_id"], "orders", ["order_id"]),
            (["product_id"], "products", ["product_id"]),
        ],
    ),
    Source(
        name="order_payments",
        file_name="olist_order_payments_dataset.csv",
        table="order_payments",
        columns={
            "order_id": "text",
            "payment_sequential": "int",
            "payment_type": "text",
            "payment_installments": "int",
            "payment_value": "money",
        },
        primary_key=["order_id", "payment_sequential"],
        required=["order_id", "payment_sequential", "payment_type", "payment_installments", "payment_value"],
        references=[(["order_id"], "orders", ["order_id"])],
    ),
]


def db_settings(dbname: str | None = None) -> dict[str, str]:
    """Connection settings from environment variables, with local defaults
    that match docker-compose.yml."""
    return {
        "host": os.getenv("PGHOST", "localhost"),
        "port": os.getenv("PGPORT", "5432"),
        "user": os.getenv("PGUSER", "postgres"),
        "password": os.getenv("PGPASSWORD", "postgres"),
        "dbname": dbname or os.getenv("PGDATABASE", "olist"),
    }
