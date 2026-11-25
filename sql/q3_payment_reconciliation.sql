-- Q3. Orders with no payment, or whose paid total differs from items + freight.
--
-- Rules (from the case):
--   * all order statuses
--   * compare SUM(payment_value) with SUM(price + freight_value) per order
--   * flag absolute differences greater than R$ 0.01
--
-- Items and payments are aggregated to one row per order in SEPARATE CTEs and
-- only then joined. Joining the raw tables would repeat every payment once per
-- item (2 items x 2 payments = 4 rows) and inflate both totals.
--
-- difference = paid_total - items_total  (positive = customer paid more)

WITH item_totals AS (
    SELECT order_id,
           COUNT(*)                    AS item_count,
           SUM(price + freight_value)  AS items_total
    FROM olist.order_items
    GROUP BY order_id
),
payment_totals AS (
    SELECT order_id,
           COUNT(*)            AS payment_count,
           SUM(payment_value)  AS paid_total
    FROM olist.order_payments
    GROUP BY order_id
),
reconciliation AS (
    SELECT
        o.order_id,
        o.order_status,
        COALESCE(i.item_count, 0)       AS item_count,
        COALESCE(i.items_total, 0.00)   AS items_total,
        COALESCE(p.payment_count, 0)    AS payment_count,
        COALESCE(p.paid_total, 0.00)    AS paid_total,
        (p.order_id IS NULL)            AS has_no_payment,
        (i.order_id IS NULL)            AS has_no_items
    FROM olist.orders o
    LEFT JOIN item_totals    i ON i.order_id = o.order_id
    LEFT JOIN payment_totals p ON p.order_id = o.order_id
)
SELECT
    order_id,
    order_status,
    item_count,
    items_total,
    payment_count,
    paid_total,
    paid_total - items_total AS difference,
    CASE
        WHEN has_no_payment AND has_no_items THEN 'no_payment_and_no_items'
        WHEN has_no_payment                  THEN 'no_payment'
        WHEN has_no_items                    THEN 'payment_without_items'
        WHEN paid_total > items_total        THEN 'paid_more_than_items'
        ELSE                                      'paid_less_than_items'
    END AS flag_reason
FROM reconciliation
WHERE has_no_payment
   OR ABS(paid_total - items_total) > 0.01
ORDER BY flag_reason, ABS(paid_total - items_total) DESC, order_id;
