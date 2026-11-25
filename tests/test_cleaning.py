"""Cleaning rules, rejected rows and ranking assumptions."""
from decimal import Decimal


def rejected(db):
    return {(f, r) for f, r in db("SELECT source_file, reason FROM etl.rejected_rows")}


def test_bad_values_are_rejected_and_logged(dataset, run, db):
    (dataset
        .customer("c1").customer("c_bad_state", "Sao Paulo")
        .product("p1", "livros")
        .order("O1", "c1")
        .order("O_bad_date", "c1", "delivered", "15/01/2018")
        .item("O1", 1, "p1", "10.00", "1.00")
        .item("O1", 2, "p1", "abc", "1.00")          # not a number
        .item("O1", 3, "p1", "-5.00", "1.00")        # negative
        .item("O1", 4, "p1", "10.555", "1.00")       # 3 decimal places
        .payment("O1", 1, "11.00"))
    result = run(dataset.write())

    assert db("SELECT COUNT(*) FROM olist.order_items")[0][0] == 1
    assert rejected(db) == {
        ("olist_customers_dataset.csv", "invalid_state:customer_state"),
        ("olist_orders_dataset.csv", "invalid_timestamp:order_purchase_timestamp"),
        ("olist_order_items_dataset.csv", "invalid_amount:price"),
    }
    items = next(s for s in result.file_stats if s.source_file == "olist_order_items_dataset.csv")
    assert (items.rows_read, items.rows_rejected, items.rows_inserted) == (4, 3, 1)


def test_exact_duplicates_dropped_conflicting_duplicates_rejected(dataset, run, db):
    (dataset
        .customer("c1").product("p1", "livros")
        .order("O1", "c1")
        .item("O1", 1, "p1", "10.00", "1.00")
        .item("O1", 1, "p1", "10.00", "1.00")        # exact copy -> drop one
        .item("O1", 2, "p1", "20.00", "1.00")
        .item("O1", 2, "p1", "25.00", "1.00")        # same key, different price -> reject both
        .payment("O1", 1, "11.00"))
    result = run(dataset.write())

    items = next(s for s in result.file_stats if s.source_file == "olist_order_items_dataset.csv")
    assert items.exact_duplicates_dropped == 1
    assert items.rows_rejected == 2
    assert db("SELECT order_item_id, price FROM olist.order_items") == [(1, Decimal("10.00"))]


def test_rows_pointing_to_unknown_parents_are_rejected(dataset, run, db):
    (dataset
        .customer("c1").product("p1", "livros")
        .order("O1", "c1")
        .order("O_ghost_customer", "nobody")
        .item("O1", 1, "p1", "10.00", "1.00")
        .item("O_missing", 1, "p1", "10.00", "1.00")
        .payment("O_missing", 1, "11.00"))
    run(dataset.write())

    assert rejected(db) == {
        ("olist_orders_dataset.csv", "unknown_customers_reference:customer_id"),
        ("olist_order_items_dataset.csv", "unknown_orders_reference:order_id"),
        ("olist_order_payments_dataset.csv", "unknown_orders_reference:order_id"),
    }


def test_missing_category_shows_as_unknown_and_ties_keep_both(dataset, run, query):
    dataset.customer("c1")
    # 11 categories: cat01 > cat02 > ... ; (unknown) and cat10 tie for 10th place
    for n in range(1, 10):
        pid = f"p{n}"
        dataset.product(pid, f"cat{n:02d}").order(f"o{n}", "c1").item(f"o{n}", 1, pid, f"{200 - n}.00", "1.00")
    dataset.product("p10", "cat10").order("o10", "c1").item("o10", 1, "p10", "50.00", "1.00")
    dataset.product("p_none", None).order("o11", "c1").item("o11", 1, "p_none", "50.00", "1.00")
    dataset.product("p12", "cat12").order("o12", "c1").item("o12", 1, "p12", "5.00", "1.00")
    run(dataset.write())

    q2 = query("q2_top10_categories_by_month")
    assert len(q2) == 11                                   # 9 + two tied at rank 10
    tenth = {r["product_category"] for r in q2 if r["sales_rank"] == 10}
    assert tenth == {"(unknown)", "cat10"}
    assert "cat12" not in {r["product_category"] for r in q2}
