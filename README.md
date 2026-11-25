# Olist Sales Pipeline and Payment Reconciliation

**Case:** 10 · Sales pipeline and payment reconciliation
**Time spent:** about 3h for the solution + 30 min for the video
**Video:** https://youtu.be/VIWVyTqDgIM

A Python pipeline that loads five Olist CSV files into PostgreSQL and answers three business questions with SQL:

1. Sales value and average ticket by month and customer state
2. Top 10 product categories by sales value in each month
3. Orders with no payment, or whose paid total differs from items + freight

The pipeline can run again on the same files without duplicating rows or changing totals. Every run is logged with row counts, rejected rows and data quality findings.

---

## Quick start

Requirements: Python 3.11+, Docker (or any local PostgreSQL 14+).

```bash
# 1. Start PostgreSQL
docker compose up -d

# 2. Install dependencies
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 3. Put the five Olist CSV files in data/   (see "Getting the data")

# 4. Run the pipeline and export the answers to results/
python -m pipeline.run --data-dir data --results-dir results

# 5. See the run history
python -m pipeline.report

# 6. Run the tests (uses a separate database, olist_test)
pytest
```

Connection settings come from `PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD` and `PGDATABASE`. The defaults match `docker-compose.yml` (`localhost:5432`, user `postgres`, password `postgres`, database `olist`). The database is created on the first run if it does not exist.

### Getting the data

Download the dataset from Kaggle: <https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce>. Unzip it and copy these five files into `data/`:

`olist_orders_dataset.csv`, `olist_order_items_dataset.csv`, `olist_order_payments_dataset.csv`, `olist_customers_dataset.csv`, `olist_products_dataset.csv`

The CSVs are in `.gitignore` and are not committed. All numbers in this README come from the Kaggle files; `data/README.md` lists their MD5 checksums. Another copy of the dataset (Olist's GitHub repository) differs in three files and gives different Q3 counts, so check the checksums if your numbers don't match.

### Querying the results

The answers are exported to `results/` as CSV. You can also run any query directly:

```bash
psql -h localhost -U postgres -d olist -f sql/q1_sales_by_month_state.sql
psql -h localhost -U postgres -d olist -f sql/q2_top10_categories_by_month.sql
psql -h localhost -U postgres -d olist -f sql/q3_payment_reconciliation.sql
```

Run log tables: `etl.pipeline_runs`, `etl.file_loads`, `etl.rejected_rows` and `etl.dq_findings`.

### Demo scenario

`examples/video_scenario/` is a small fictitious dataset (February 2018, RJ and MG) with expected results worked out by hand. It runs in its own database:

```bash
python -m pipeline.run --data-dir examples/video_scenario --dbname olist_demo --results-dir /tmp/demo
```

| Question | Expected |
|---|---|
| Q1 | RJ: sales 380.00, 2 orders, ticket 190.00 · MG: sales 160.00, 2 orders, ticket 80.00 (order G is `shipped`, so it is excluded) |
| Q2 | eletronicos 420.00 · esporte_lazer 80.00 · (unknown) 40.00 |
| Q3 | F paid 7.50 more (6 installments) · I has a payment but no items · E differs by exactly 0.01, so it is **not** flagged · D (2 items × 2 payments) reconciles |

---

## Project layout

```
pipeline/
  config.py     source file specs: column types, required columns, keys, renames
  extract.py    reads each CSV as text, checks columns, computes the file hash
  transform.py  trims, types and validates rows; drops exact duplicates; rejects bad rows
  load.py       staging table -> orphan check -> upsert (INSERT ... ON CONFLICT)
  quality.py    data quality checks stored after every run
  queries.py    runs Q1-Q3 and exports CSVs
  run.py        command line entry point; one transaction per run
  report.py     prints the run history
sql/
  schema.sql    tables, keys, indexes (idempotent)
  q1_..., q2_..., q3_...sql   the three business questions
tests/          pytest suite with fictitious data
scripts/crosscheck_q1_q2.py   recomputes Q1/Q2 with pandas to check the SQL
examples/video_scenario/      demo dataset with expected results
results/        exported answers and run logs from the real dataset
```

## How it works

```
CSV files ──► extract (all text) ──► transform (types, rules) ──► staging table ──► upsert ──► olist.* tables
                                         │                            │                         │
                                         └── rejected rows ───────────┴─► etl.rejected_rows      └─► data quality checks ─► etl.dq_findings
                                                                                                  etl.pipeline_runs / etl.file_loads
```

1. **Extract** reads every column as text, so pandas never guesses types (zip code `01310` stays `01310`). Missing files or columns stop the run before anything is written.
2. **Transform** trims values, turns empty cells into NULL, casts types and applies the rules in [Data quality](#data-quality-issues-and-handling).
3. **Load** copies clean rows into a temporary staging table, rejects rows that point to a parent that does not exist, then upserts by primary key.
4. **Quality checks** count known issues after the load and store them with the run.
5. The whole load is **one transaction**. If any step fails, nothing is committed and the run is marked `failed` with the error message.

---

## Results on the real dataset

All files loaded with **0 rejected rows** (448,369 rows in total). Full output: `results/first_run_output.txt`, `results/rerun_output.txt`, `results/run_history.txt`.

| | |
|---|---|
| Delivered orders | 96,478 |
| Delivered sales (items, no freight) | R$ 13,221,498.11 |
| Q1 rows (month × state) | 556 |
| Q2 rows | 212 (23 months; 21 months have 10 categories, 2016-09 and 2016-12 have only 1) |
| Q3 flagged orders | 1,076 |

Q3 by reason:

| Reason | Orders | Meaning |
|---|---:|---|
| `payment_without_items` | 772 | payment exists, but the order has no items (603 `unavailable`, 161 `canceled`, 8 other statuses) |
| `paid_more_than_items` | 264 | paid more than items + freight by more than R$ 0.01 |
| `paid_less_than_items` | 39 | paid less than items + freight by more than R$ 0.01 |
| `no_payment` | 1 | `bfbd0f9bdef84302105ad712db648a6c`, delivered, items R$ 143.46, no payment rows |

**Run history (real data):**

| Run | What | Result |
|---|---|---|
| 1 | first load | 448,369 inserted |
| 2 | same files again | 0 inserted, 0 updated, 448,369 unchanged; results identical (`cmp`) |
| 3 | payments file removed on purpose | `failed`, error logged, tables untouched |
| 4 | same files again | 0 inserted, 0 updated |

---

## Key decisions

**Aggregate before joining.** Items and payments are both "many per order". Joining them directly repeats every payment once per item (2 items × 2 payments = 4 rows) and inflates both totals. Each side is summed per order in its own CTE and only then joined. Q1 does the same for sales so the order count stays correct.

**Upsert on primary keys for reruns.** Every table has its natural key (`order_id`, `(order_id, order_item_id)`, `(order_id, payment_sequential)`, ...) and the load uses `INSERT ... ON CONFLICT DO UPDATE ... WHERE (columns) IS DISTINCT FROM (new columns)`. Same file → nothing changes. Changed row → updated, not duplicated. New row → inserted.
*Alternative considered:* truncate and reload in a transaction. It is simpler and also idempotent for static files, but it cannot tell what changed between runs, and it rewrites everything every time. Upsert also prepares the pipeline for daily incremental files.

**`NUMERIC(12,2)` and `Decimal`, never float.** The reconciliation rule is about one cent. With floats, `0.10 + 0.20 = 0.30000000000000004`, which can move an order across the line. Money is parsed with `Decimal` in Python and stored as `NUMERIC` in PostgreSQL.

**One transaction per run + separate log connection.** Business tables never hold a half-loaded state. The run log uses its own autocommit connection, so a failed run is still recorded. An advisory lock stops two runs from loading at the same time.

**Reject, don't guess.** A row with a bad value is saved to `etl.rejected_rows` with its reason and CSV row number, not fixed silently. Exact duplicate rows are dropped (no information lost). Rows with the same key but different content are **all** rejected, because there is no way to know which version is true.

**Q3 reasons are specific.** Instead of one "mismatch" flag, each flagged order says why: `no_payment`, `no_payment_and_no_items`, `payment_without_items`, `paid_more_than_items` or `paid_less_than_items`. The 772 orders with payments but no items are a different problem from a wrong amount, and someone acting on the list needs to know which is which.

## Assumptions

- **Delivered** means `order_status = 'delivered'`, as the case defines. 8 delivered orders have no delivery date; they still count as delivered.
- **Month** is `date_trunc('month', order_purchase_timestamp)`. Timestamps are treated as local Brazil time (the files have no time zone).
- **Missing category:** 610 products have no category. They are kept with NULL and grouped as `(unknown)` in Q2, competing in the ranking like any category, because their sales are real. In the real data `(unknown)` never reaches a monthly top 10.
- **Ties in Q2:** `RANK()` is used, so if two categories tie for 10th place both are shown and that month returns more than 10 rows. No ties occur in the real data; the behavior is covered by a test.
- **Average ticket** divides by distinct delivered orders that have at least one item. A delivered order with no items has no sales to count; the real data has 0 such orders (checked every run by `delivered_orders_without_items`).
- **Q3 threshold:** strictly greater than R$ 0.01 (`ABS(diff) > 0.01`), so a difference of exactly 0.01 is not flagged.
- **Orders with no items and a 0.00 payment** (3 canceled orders with a `not_defined` payment of 0.00) are not flagged: 0.00 paid vs 0.00 items is not a difference.
- **Q3 difference sign:** `difference = paid_total - items_total`; positive means the customer paid more.

## Data quality issues and handling

Counts from the real dataset. These are stored in `etl.dq_findings` on every run.

| Issue | Rows | Handling |
|---|---:|---|
| Products without category (and without name/description/photo counts) | 610 | Kept with NULL; `(unknown)` in Q2 |
| Products without weight/dimensions | 2 | Kept with NULL; not used |
| Orders without items | 775 | Kept; flagged in Q3 when they have payments (772) |
| Orders without payments | 1 | Kept; flagged in Q3 as `no_payment` |
| Payments of 0.00 (`voucher` ×6, `not_defined` ×3) | 9 | Kept; add 0 to the paid total |
| Payment type `not_defined` | 3 | Kept; not used by the questions |
| Payments with 0 installments | 2 | Kept; not used by the questions |
| Delivered orders without delivery date | 8 | Kept as delivered (status is the rule) |
| Items with freight 0.00 | 383 | Kept; free shipping is valid |
| Misspelled source columns `product_name_lenght`, `product_description_lenght` | — | Renamed to `..._length` on load |
| Months with very little data (2016-09, 2016-12 have a single delivered category; no delivered orders in 2016-11, 2018-09, 2018-10) | — | Reported as is; the dataset starts and ends with sparse months |

Checks that found **nothing** in the real data but are enforced (and tested): duplicate keys, exact duplicate rows, invalid numbers or dates, negative or >2-decimal amounts, invalid state codes, items/payments for unknown orders, orders for unknown customers.

---

## Tests

`pytest` runs 15 tests on fictitious data in a separate database. Three highlighted:

| # | Test | Expected result | What error it catches |
|---|---|---|---|
| 1 | `test_rerun_with_same_files_changes_nothing` | Second run: 0 inserted, 0 updated; table counts and all three answers identical | Plain INSERTs that duplicate rows (sales double on every run), or updates that rewrite unchanged rows |
| 2 | `test_many_items_and_many_payments_are_not_multiplied` | Order with 3 items + 2 payments: sales 300.00 (not 600.00), 1 order, no Q3 flag (330 = 330) | Joining items to payments before aggregating (fan-out) |
| 3 | `test_one_cent_boundary` | +0.01 and −0.01 not flagged; +0.02 flagged; 0.10 + 0.20 vs 0.30 not flagged | `>=` instead of `>`, and float rounding errors |

Other tests: the worked example from the case (A, B, C) including a rerun, status update applied without duplication, failed run logged and rolled back, missing column stops the run, rejected values, duplicate handling, orphan rows, `(unknown)` category and ties at 10th place.

**Checking that the tests can fail:** I broke the code on purpose three times and confirmed the suite caught each one: changing `> 0.01` to `>= 0.01` (1 test failed), joining items to payments before aggregating in Q1 (4 failed), and replacing the upsert with `DO NOTHING` (the update test failed).

**Independent check of Q1 and Q2:** `scripts/crosscheck_q1_q2.py` recomputes both answers from the raw CSVs with pandas (no database) and compares row by row. Result on the real data: 556/556 and 212/212 rows, 0 differences.

---

## Two decisions I investigated

**1. Are the 264 overpaid orders a bug in my reconciliation?**
I expected overpayments to be rare, so 264 looked suspicious. I first checked the obvious bug, fan-out from joining items and payments, using the multi-item/multi-payment test and the pandas cross-check; both were fine. Then I grouped the flagged orders by payment details: 249 of the 264 overpaid orders (94%) were paid in more than one installment, while only 51.5% of all orders use installments. That pattern fits installment interest being included in `payment_value`, which would be a business rule, not a data error. I kept them flagged (the rule in the case is clear) and documented the hypothesis instead of "fixing" the numbers.

**2. A load failure from nullable integer columns (a bug in AI-assisted code).**
During development, the first full run failed with `invalid input syntax for type integer: "40.0"` on `product_name_length`. The transform built integer columns with pandas, and because those columns have empty cells, pandas silently turned them into floats. The failure was caught because the run is one transaction (nothing was half-loaded) and the error was written to `etl.pipeline_runs`. The source file was fine (it has `40`); the bug was in the transform. The fix was to build plain Python `int`/`None` values in an object column, so pandas cannot convert them to float. That run is the reason I keep the run log even for failures.

---

## Scale, new sources, updates and recovery

**Implemented and validated**
- Reruns with the same files: no duplicates, no changed totals (test 1, real-data runs 2 and 4).
- Updated rows (e.g. status `shipped` → `delivered`) are updated in place (`test_changed_row_is_updated_not_duplicated`).
- Failure recovery: one transaction per run, so a failed run leaves the previous data intact; fix the cause and run again (`test_failed_run_is_logged_and_leaves_previous_data_untouched`, real-data run 3).
- Every run logs per-file counts (read, duplicates, rejected, inserted, updated, unchanged), the file SHA-256, rejected rows with reasons, and quality findings.
- Full real dataset (448k rows) loads in about 11 seconds locally.

**Proposed, not implemented**
- **Daily incremental files:** the upsert already supports it. I would add a check that skips a file whose SHA-256 was already loaded successfully, and recompute Q3 flags on every run, because an order with no payment today may be paid tomorrow.
- **Deletes:** a row that disappears from a later file stays in the database. With full snapshots, a soft-delete (`is_active = false`) for keys missing from the new file would fix this.
- **Larger volumes (100×):** read CSVs in chunks instead of all at once, validate in chunks, keep COPY into staging (already used), and partition the big tables by purchase month. Q1/Q2 could become materialized views refreshed after each load.
- **New sources:** a new file is a new `Source` entry in `config.py` (types, keys, references), so most new tables need no new code.
- **Scheduling and alerts:** a cron job or an orchestrator (Airflow, Dagster) calling `python -m pipeline.run`, alerting when a run fails or when rejected rows or Q3 flags jump compared with the previous run.

## Limitations and pending items

- No soft-delete for rows removed from source files (see above).
- Q3 reports the current state only; there is no history of flags per run.
- Rejected rows are logged but there is no tool to reprocess them after a fix (rerunning the corrected file works).
- Timestamps are assumed to be Brazil local time; the dataset does not say.

---

## How I used AI

I used Claude (Anthropic) as a coding assistant. It drafted the pipeline structure, the SQL queries, the tests and this README, and I reviewed the design decisions against the rules of the case (staging + upsert, aggregate before joining, NUMERIC for money, specific Q3 reasons).

How the output was verified:
- **Locally, on my machine:** I ran the full pipeline twice (second run: 0 inserted, 0 updated), forced a failed run by removing the payments file (logged as `failed`, tables untouched), ran the 15 tests, and ran the independent pandas cross-check of Q1 and Q2 (0 differences).
- **A real discrepancy:** my local Q3 result (1,076 flagged orders) did not match the AI's first run (1,139). I compared MD5 checksums and found that the AI had used a different copy of the Olist dataset (from Olist's GitHub repository), which differs from the Kaggle files in three files. The code was correct; I updated every number in this README to the Kaggle files and recorded their checksums in `data/README.md`.
- **During development:** the case's worked example became an automated test; the code was broken on purpose (threshold, fan-out join, upsert) to confirm the tests fail; and the expected results of the demo scenario were worked out by hand before running it.
- The first AI-generated version had a real bug (nullable integers became floats); see "Two decisions I investigated".
