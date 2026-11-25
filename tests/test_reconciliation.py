"""Reconciliation and fan-out tests (Q1 and Q3)."""
from decimal import Decimal


def test_many_items_and_many_payments_are_not_multiplied(dataset, run, query):
    """HIGHLIGHTED TEST 2: an order with 3 items and 2 payments.

    A naive join of items with payments returns 3 x 2 = 6 rows, which would
    report sales of 3 x 2 = 2x the real value and paid totals 3x too high.
    Expected: sales 300.00 (not 600.00), 1 order, and no reconciliation flag
    because 120 + 210 = 330 = (100+10) + (150+15) + (50+5).
    """
    (dataset
        .customer("c1", "RJ")
        .product("p1", "eletronicos")
        .order("O1", "c1", "delivered", "2018-02-05 10:00:00")
        .item("O1", 1, "p1", "100.00", "10.00")
        .item("O1", 2, "p1", "150.00", "15.00")
        .item("O1", 3, "p1", "50.00", "5.00")
        .payment("O1", 1, "120.00", "credit_card")
        .payment("O1", 2, "210.00", "voucher"))
    run(dataset.write())

    assert query("q1_sales_by_month_state") == [{
        "purchase_month": "2018-02", "customer_state": "RJ",
        "sales_value": Decimal("300.00"), "orders": 1, "avg_ticket": Decimal("300.00"),
    }]
    q2 = query("q2_top10_categories_by_month")
    assert [(r["product_category"], r["sales_value"]) for r in q2] == [("eletronicos", Decimal("300.00"))]
    assert query("q3_payment_reconciliation") == []


def test_one_cent_boundary(dataset, run, query):
    """HIGHLIGHTED TEST 3: only differences ABOVE R$ 0.01 are flagged.

    Expected: 0.01 over and 0.01 under are NOT flagged; 0.02 IS flagged.
    Catches: using >= instead of >, or float rounding (e.g. 0.1 + 0.2 != 0.3)
    flipping a case across the line.
    """
    dataset.customer("c1").product("p1", "cama_mesa_banho")
    cases = {
        "over_0_01": "100.01",
        "under_0_01": "99.99",
        "over_0_02": "100.02",
        "exact": "100.00",
    }
    for order_id, paid in cases.items():
        dataset.order(order_id, "c1").item(order_id, 1, "p1", "90.00", "10.00").payment(order_id, 1, paid)
    # float trap: 0.10 + 0.20 must equal exactly 0.30
    dataset.order("float_trap", "c1").item("float_trap", 1, "p1", "0.20", "0.10")
    dataset.payment("float_trap", 1, "0.10").payment("float_trap", 2, "0.20")
    run(dataset.write())

    flagged = {r["order_id"]: r for r in query("q3_payment_reconciliation")}
    assert set(flagged) == {"over_0_02"}
    assert flagged["over_0_02"]["difference"] == Decimal("0.02")
    assert flagged["over_0_02"]["flag_reason"] == "paid_more_than_items"


def test_orders_missing_items_or_payments_get_their_own_reason(dataset, run, query):
    (dataset
        .customer("c1")
        .product("p1", "brinquedos")
        .order("paid_no_items", "c1", "unavailable")
        .payment("paid_no_items", 1, "45.00")
        .order("nothing", "c1", "created")
        .order("zero_voucher_no_items", "c1", "canceled")
        .payment("zero_voucher_no_items", 1, "0.00", "not_defined"))
    run(dataset.write())

    flagged = {r["order_id"]: r["flag_reason"] for r in query("q3_payment_reconciliation")}
    assert flagged == {
        "paid_no_items": "payment_without_items",
        "nothing": "no_payment_and_no_items",
        # a 0.00 payment on an order with no items: 0 vs 0, nothing to flag
    }


def test_average_ticket_counts_distinct_orders_per_state_and_month(dataset, run, query):
    (dataset
        .customer("sp1", "SP").customer("sp2", "SP").customer("mg1", "MG")
        .product("p1", "esporte_lazer")
        .order("o1", "sp1", "delivered", "2018-03-01 08:00:00").item("o1", 1, "p1", "10.00", "1.00")
        .item("o1", 2, "p1", "20.00", "1.00")
        .order("o2", "sp2", "delivered", "2018-03-31 23:59:59").item("o2", 1, "p1", "60.00", "1.00")
        .order("o3", "mg1", "delivered", "2018-04-01 00:00:00").item("o3", 1, "p1", "15.50", "1.00")
        .order("o4", "sp1", "shipped", "2018-03-10 08:00:00").item("o4", 1, "p1", "999.00", "1.00"))
    run(dataset.write())

    rows = {(r["purchase_month"], r["customer_state"]): r for r in query("q1_sales_by_month_state")}
    assert set(rows) == {("2018-03", "SP"), ("2018-04", "MG")}
    assert rows[("2018-03", "SP")]["sales_value"] == Decimal("90.00")   # shipped o4 left out
    assert rows[("2018-03", "SP")]["orders"] == 2
    assert rows[("2018-03", "SP")]["avg_ticket"] == Decimal("45.00")
    assert rows[("2018-04", "MG")]["avg_ticket"] == Decimal("15.50")
