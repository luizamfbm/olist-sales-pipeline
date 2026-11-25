"""Data quality checks that run after every load.

These are problems that do not stop a row from loading but that someone
reading the results should know about. Each finding is stored in
etl.dq_findings with the number of affected rows and how it was handled,
so every run leaves a record that can be compared with earlier runs.
"""
from __future__ import annotations

import psycopg

# (check name, SQL returning a single count, treatment)
CHECKS: list[tuple[str, str, str]] = [
    (
        "products_without_category",
        "SELECT COUNT(*) FROM olist.products WHERE product_category_name IS NULL",
        "Kept with NULL category. Grouped as '(unknown)' in Q2 so their sales still count.",
    ),
    (
        "orders_without_items",
        "SELECT COUNT(*) FROM olist.orders o WHERE NOT EXISTS "
        "(SELECT 1 FROM olist.order_items i WHERE i.order_id = o.order_id)",
        "Kept. They add no sales to Q1/Q2. Flagged in Q3 when they have payments.",
    ),
    (
        "delivered_orders_without_items",
        "SELECT COUNT(*) FROM olist.orders o WHERE o.order_status = 'delivered' AND NOT EXISTS "
        "(SELECT 1 FROM olist.order_items i WHERE i.order_id = o.order_id)",
        "Would be left out of the Q1 order count (no sales to divide). Expected to be 0.",
    ),
    (
        "orders_without_payments",
        "SELECT COUNT(*) FROM olist.orders o WHERE NOT EXISTS "
        "(SELECT 1 FROM olist.order_payments p WHERE p.order_id = o.order_id)",
        "Kept. Flagged in Q3 with reason no_payment.",
    ),
    (
        "zero_value_payments",
        "SELECT COUNT(*) FROM olist.order_payments WHERE payment_value = 0",
        "Kept. Real rows (vouchers and 'not_defined'); they add 0 to the paid total.",
    ),
    (
        "payment_type_not_defined",
        "SELECT COUNT(*) FROM olist.order_payments WHERE payment_type = 'not_defined'",
        "Kept as is. Payment type is not used by the three questions.",
    ),
    (
        "payments_with_zero_installments",
        "SELECT COUNT(*) FROM olist.order_payments WHERE payment_installments = 0",
        "Kept as is. Installments are not used by the three questions.",
    ),
    (
        "delivered_orders_without_delivery_date",
        "SELECT COUNT(*) FROM olist.orders WHERE order_status = 'delivered' "
        "AND order_delivered_customer_date IS NULL",
        "Kept. The case defines delivered by order_status, so they count as delivered.",
    ),
    (
        "items_with_zero_freight",
        "SELECT COUNT(*) FROM olist.order_items WHERE freight_value = 0",
        "Kept. Free shipping is a valid value.",
    ),
    (
        "products_missing_dimensions",
        "SELECT COUNT(*) FROM olist.products WHERE product_weight_g IS NULL",
        "Kept with NULL. Dimensions are not used by the three questions.",
    ),
]


def run_checks(cur: psycopg.Cursor, run_id: int) -> list[tuple[str, int, str]]:
    results = []
    for name, query, treatment in CHECKS:
        cur.execute(query)
        count = int(cur.fetchone()[0])
        cur.execute(
            "INSERT INTO etl.dq_findings (run_id, check_name, affected_rows, treatment) "
            "VALUES (%s, %s, %s, %s)",
            (run_id, name, count, treatment),
        )
        results.append((name, count, treatment))
    return results
