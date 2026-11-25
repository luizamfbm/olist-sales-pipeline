"""Independent check of Q1 and Q2: recompute them straight from the CSV files
with pandas (no database involved) and compare with the exported results.

    python scripts/crosscheck_q1_q2.py --data-dir data --results-dir results

If the SQL and this script disagree on any row, one of them has a bug.
Money is summed as Decimal, so there is no float rounding in the comparison.
"""
import argparse
import sys
from decimal import Decimal
from pathlib import Path

import pandas as pd


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--results-dir", type=Path, default=Path("results"))
    args = parser.parse_args()
    d, r = args.data_dir, args.results_dir

    orders = pd.read_csv(d / "olist_orders_dataset.csv", dtype=str)
    items = pd.read_csv(d / "olist_order_items_dataset.csv", dtype=str)
    customers = pd.read_csv(d / "olist_customers_dataset.csv", dtype=str)
    products = pd.read_csv(d / "olist_products_dataset.csv", dtype=str)
    items["price_d"] = items["price"].map(Decimal)

    delivered = orders[orders["order_status"] == "delivered"].merge(customers, on="customer_id")
    delivered["month"] = delivered["order_purchase_timestamp"].str[:7]

    # Q1
    x = items.merge(delivered[["order_id", "month", "customer_state"]], on="order_id")
    q1_expected = (x.groupby(["month", "customer_state"])
                     .agg(sales=("price_d", "sum"), orders=("order_id", "nunique")).reset_index())
    q1 = pd.read_csv(r / "q1_sales_by_month_state.csv", dtype=str)
    m1 = q1_expected.merge(q1, left_on=["month", "customer_state"],
                           right_on=["purchase_month", "customer_state"], how="outer", indicator=True)
    q1_problems = int((m1["_merge"] != "both").sum()
                      + (m1["sales"] != m1["sales_value"].map(Decimal)).sum()
                      + (m1["orders_x"] != m1["orders_y"].astype(int)).sum())
    print(f"Q1: {len(q1_expected)} expected rows, {len(q1)} SQL rows, {q1_problems} differences")

    # Q2
    x2 = (items.merge(delivered[["order_id", "month"]], on="order_id")
               .merge(products[["product_id", "product_category_name"]], on="product_id"))
    x2["category"] = x2["product_category_name"].fillna("(unknown)")
    sales = x2.groupby(["month", "category"])["price_d"].sum().reset_index()
    sales["rank"] = sales.groupby("month")["price_d"].transform(
        lambda s: s.astype(float).rank(method="min", ascending=False))
    q2_expected = sales[sales["rank"] <= 10]
    q2 = pd.read_csv(r / "q2_top10_categories_by_month.csv", dtype=str)
    m2 = q2_expected.merge(q2, left_on=["month", "category"],
                           right_on=["purchase_month", "product_category"], how="outer", indicator=True)
    q2_problems = int((m2["_merge"] != "both").sum()
                      + (m2["price_d"] != m2["sales_value"].map(Decimal)).sum())
    print(f"Q2: {len(q2_expected)} expected rows, {len(q2)} SQL rows, {q2_problems} differences")

    return 1 if (q1_problems or q2_problems) else 0


if __name__ == "__main__":
    sys.exit(main())
