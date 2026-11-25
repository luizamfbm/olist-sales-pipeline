"""The worked example from the case description (orders A, B and C).

January 2018, customers in SP:
  A  delivered  Livros     items 60.00 + 40.00, freight 6.00 + 4.00, payments 70.00 + 40.00
  B  delivered  Papelaria  item 50.00, freight 5.00, payment 54.98
  C  canceled   Livros     item 30.00, freight 3.00, no payment

Expected: sales R$ 150.00, average ticket R$ 75.00, Livros R$ 100.00,
Papelaria R$ 50.00. A reconciles, B differs by R$ 0.02, C has no payment.
Running again must give the same results.
"""
from decimal import Decimal


def build_example(dataset):
    (dataset
        .customer("cust-a").customer("cust-b").customer("cust-c")
        .product("prod-livro", "Livros").product("prod-papel", "Papelaria")
        .order("A", "cust-a", "delivered", "2018-01-10 09:00:00")
        .order("B", "cust-b", "delivered", "2018-01-12 14:30:00")
        .order("C", "cust-c", "canceled", "2018-01-20 18:00:00")
        .item("A", 1, "prod-livro", "60.00", "6.00")
        .item("A", 2, "prod-livro", "40.00", "4.00")
        .item("B", 1, "prod-papel", "50.00", "5.00")
        .item("C", 1, "prod-livro", "30.00", "3.00")
        .payment("A", 1, "70.00")
        .payment("A", 2, "40.00")
        .payment("B", 1, "54.98"))
    return dataset.write()


def check_expected_results(query):
    q1 = query("q1_sales_by_month_state")
    assert q1 == [{
        "purchase_month": "2018-01", "customer_state": "SP",
        "sales_value": Decimal("150.00"), "orders": 2, "avg_ticket": Decimal("75.00"),
    }]

    q2 = {(r["product_category"], r["sales_value"], r["sales_rank"]) for r in query("q2_top10_categories_by_month")}
    assert q2 == {("Livros", Decimal("100.00"), 1), ("Papelaria", Decimal("50.00"), 2)}

    q3 = {r["order_id"]: r for r in query("q3_payment_reconciliation")}
    assert set(q3) == {"B", "C"}                       # A reconciles, so it is not flagged
    assert q3["B"]["difference"] == Decimal("-0.02")
    assert q3["B"]["flag_reason"] == "paid_less_than_items"
    assert q3["C"]["flag_reason"] == "no_payment"
    assert q3["C"]["items_total"] == Decimal("33.00")


def test_worked_example_matches_case_description(dataset, run, query):
    folder = build_example(dataset)
    run(folder)
    check_expected_results(query)


def test_worked_example_survives_a_rerun(dataset, run, query):
    folder = build_example(dataset)
    run(folder)
    run(folder)
    check_expected_results(query)
