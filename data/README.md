# Data

Put the five Olist CSV files here (they are not committed to the repository):

- `olist_orders_dataset.csv`
- `olist_order_items_dataset.csv`
- `olist_order_payments_dataset.csv`
- `olist_customers_dataset.csv`
- `olist_products_dataset.csv`

Download them from Kaggle: https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce
(the zip has more files; only these five are used).

Expected sizes (rows, without header): orders 99,441 · items 112,650 ·
payments 103,886 · customers 99,441 · products 32,951.

MD5 checksums of the Kaggle files used for the results in this repository:

| File | MD5 |
|---|---|
| olist_customers_dataset.csv | 8a2c4244856aab4bde3b8ed81f8ca251 |
| olist_order_items_dataset.csv | f4fa76976662e9cba0633f9e49ed2645 |
| olist_order_payments_dataset.csv | 75ce0c041d18e5f250c5cea9a8042944 |
| olist_orders_dataset.csv | 8bd60e55c1ca229d9f70b62f3e72f22c |
| olist_products_dataset.csv | e935401104a3669223b83c9a01fdf5ca |

Check with `md5 data/*.csv` (macOS) or `md5sum data/*.csv` (Linux).
Other copies of the Olist dataset exist with the same row counts but different
values in items, payments and customers, which changes the Q3 results.
