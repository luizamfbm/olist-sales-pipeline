"""Run the three business questions and export their results to CSV."""
from __future__ import annotations

import csv
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"

QUERIES = {
    "q1_sales_by_month_state": SQL_DIR / "q1_sales_by_month_state.sql",
    "q2_top10_categories_by_month": SQL_DIR / "q2_top10_categories_by_month.sql",
    "q3_payment_reconciliation": SQL_DIR / "q3_payment_reconciliation.sql",
}


def run_query(conn: psycopg.Connection, name: str) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(QUERIES[name].read_text())
        return cur.fetchall()


def export_results(conn: psycopg.Connection, out_dir: Path) -> dict[str, int]:
    out_dir.mkdir(parents=True, exist_ok=True)
    counts = {}
    for name in QUERIES:
        rows = run_query(conn, name)
        path = out_dir / f"{name}.csv"
        with path.open("w", newline="", encoding="utf-8") as fh:
            if rows:
                writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
        counts[name] = len(rows)
    return counts
