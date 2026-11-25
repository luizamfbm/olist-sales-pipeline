-- Q1. Sales value and average ticket by purchase month and customer state.
--
-- Rules (from the case):
--   * delivered orders only (order_status = 'delivered')
--   * month comes from order_purchase_timestamp
--   * sales value = SUM(price); freight is excluded
--   * average ticket = sales value / number of distinct orders
--
-- Items are aggregated to one row per order BEFORE joining, so an order with
-- many items is still counted once in the order count.

WITH delivered_orders AS (
    SELECT
        o.order_id,
        date_trunc('month', o.order_purchase_timestamp)::date AS purchase_month,
        c.customer_state
    FROM olist.orders o
    JOIN olist.customers c ON c.customer_id = o.customer_id
    WHERE o.order_status = 'delivered'
),
order_sales AS (
    SELECT order_id, SUM(price) AS sales_value
    FROM olist.order_items
    GROUP BY order_id
)
SELECT
    to_char(d.purchase_month, 'YYYY-MM')                          AS purchase_month,
    d.customer_state,
    SUM(s.sales_value)                                            AS sales_value,
    COUNT(DISTINCT d.order_id)                                    AS orders,
    ROUND(SUM(s.sales_value) / COUNT(DISTINCT d.order_id), 2)     AS avg_ticket
FROM delivered_orders d
JOIN order_sales s ON s.order_id = d.order_id
GROUP BY d.purchase_month, d.customer_state
ORDER BY d.purchase_month, d.customer_state;
