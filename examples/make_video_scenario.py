"""Rebuild the fictitious demo scenario used in the video (February 2018).

    python examples/make_video_scenario.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "tests"), str(ROOT)]

from conftest import Dataset  # noqa: E402 # type: ignore

d = Dataset(ROOT / "examples" / "video_scenario")
(d.customer("cust-rj-1", "RJ").customer("cust-rj-2", "RJ").customer("cust-mg-1", "MG").customer("cust-mg-2", "MG")
 .product("prod-tv", "eletronicos").product("prod-bola", "esporte_lazer").product("prod-sem-cat", None)
 # D: 2 items x 2 payments, reconciles exactly (330.00)
 .order("D", "cust-rj-1", "delivered", "2018-02-03 10:15:00")
 .item("D", 1, "prod-tv", "200.00", "20.00").item("D", 2, "prod-tv", "100.00", "10.00")
 .payment("D", 1, "150.00", "credit_card", "3").payment("D", 2, "180.00", "voucher", "1")
 # E: paid 0.01 more -> on the limit, NOT flagged
 .order("E", "cust-rj-2", "delivered", "2018-02-11 16:40:00")
 .item("E", 1, "prod-bola", "80.00", "8.00").payment("E", 1, "88.01", "boleto", "1")
 # F: 6 installments, paid 7.50 more -> flagged (installment interest pattern)
 .order("F", "cust-mg-1", "delivered", "2018-02-14 09:05:00")
 .item("F", 1, "prod-tv", "120.00", "15.00").payment("F", 1, "142.50", "credit_card", "6")
 # G: shipped, not delivered -> out of sales
 .order("G", "cust-rj-1", "shipped", "2018-02-20 12:00:00")
 .item("G", 1, "prod-tv", "500.00", "30.00").payment("G", 1, "530.00", "credit_card", "1")
 # H: product with no category -> '(unknown)'
 .order("H", "cust-mg-2", "delivered", "2018-02-25 19:30:00")
 .item("H", 1, "prod-sem-cat", "40.00", "5.00").payment("H", 1, "45.00", "debit_card", "1")
 # I: unavailable, payment but no items -> flagged
 .order("I", "cust-rj-2", "unavailable", "2018-02-27 08:00:00")
 .payment("I", 1, "60.00", "credit_card", "1"))
d.write()
print(f"Scenario written to {d.folder}")
