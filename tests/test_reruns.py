"""Reruns, updates and failures."""
import pytest

from pipeline.extract import MissingFileError, SchemaError

TABLES = ["customers", "products", "orders", "order_items", "order_payments"]


def small_dataset(dataset, status="shipped"):
    return (dataset
        .customer("c1", "BA")
        .product("p1", "perfumaria")
        .order("O1", "c1", status, "2018-05-02 11:00:00")
        .item("O1", 1, "p1", "80.00", "12.00")
        .item("O1", 2, "p1", "20.00", "3.00")
        .payment("O1", 1, "115.00"))


def table_counts(db):
    return {t: db(f"SELECT COUNT(*) FROM olist.{t}")[0][0] for t in TABLES}


def test_rerun_with_same_files_changes_nothing(dataset, run, query, db):
    """HIGHLIGHTED TEST 1: running twice on the same files.

    Expected: second run inserts 0 rows and updates 0 rows; table counts and
    all three query results are identical to the first run.
    Catches: plain INSERTs that duplicate rows (sales would double on every
    run), or updates that rewrite rows that did not change.
    """
    folder = small_dataset(dataset).write()
    run(folder)
    counts_1 = table_counts(db)
    results_1 = [query(q) for q in ("q1_sales_by_month_state", "q2_top10_categories_by_month",
                                    "q3_payment_reconciliation")]

    second = run(folder)

    assert table_counts(db) == counts_1 == {
        "customers": 1, "products": 1, "orders": 1, "order_items": 2, "order_payments": 1,
    }
    assert all(s.rows_inserted == 0 and s.rows_updated == 0 for s in second.file_stats)
    assert all(s.rows_unchanged == s.rows_read for s in second.file_stats)
    assert [query(q) for q in ("q1_sales_by_month_state", "q2_top10_categories_by_month",
                               "q3_payment_reconciliation")] == results_1


def test_changed_row_is_updated_not_duplicated(dataset, tmp_path, run, query, db):
    run(small_dataset(dataset, status="shipped").write())
    assert query("q1_sales_by_month_state") == []          # not delivered yet

    from conftest import Dataset
    second = run(small_dataset(Dataset(tmp_path / "day2"), status="delivered").write())

    orders_stats = next(s for s in second.file_stats if s.source_file == "olist_orders_dataset.csv")
    assert (orders_stats.rows_inserted, orders_stats.rows_updated) == (0, 1)
    assert table_counts(db)["orders"] == 1
    assert [r["sales_value"] for r in query("q1_sales_by_month_state")] == [100]


def test_failed_run_is_logged_and_leaves_previous_data_untouched(dataset, tmp_path, run, db):
    run(small_dataset(dataset).write())
    before = table_counts(db)

    broken = tmp_path / "broken"
    broken.mkdir()
    for f in (dataset.folder).iterdir():
        (broken / f.name).write_bytes(f.read_bytes())
    (broken / "olist_order_payments_dataset.csv").unlink()

    with pytest.raises(MissingFileError):
        run(broken)

    assert table_counts(db) == before
    last = db("SELECT status, error FROM etl.pipeline_runs ORDER BY run_id DESC LIMIT 1")[0]
    assert last[0] == "failed"
    assert "olist_order_payments_dataset.csv" in last[1]


def test_missing_column_fails_before_loading(dataset, run, db):
    folder = small_dataset(dataset).write()
    path = folder / "olist_order_items_dataset.csv"
    lines = path.read_text().splitlines()
    path.write_text("\n".join(line.rsplit(",", 1)[0] for line in lines) + "\n")  # drop freight_value

    with pytest.raises(SchemaError, match="freight_value"):
        run(folder)
    assert db("SELECT COUNT(*) FROM olist.orders")[0][0] == 0
    assert db("SELECT status FROM etl.pipeline_runs")[0][0] == "failed"


def test_every_run_is_logged_with_counts(dataset, run, db):
    folder = small_dataset(dataset).write()
    run(folder)
    run(folder)
    rows = db("""
        SELECT r.run_id, r.status, f.source_file, f.rows_read, f.rows_inserted, f.rows_unchanged
        FROM etl.pipeline_runs r JOIN etl.file_loads f USING (run_id)
        WHERE f.source_file = 'olist_order_items_dataset.csv' ORDER BY r.run_id
    """)
    assert [(status, read, ins, unch) for _, status, _, read, ins, unch in rows] == [
        ("success", 2, 2, 0),
        ("success", 2, 0, 2),
    ]
