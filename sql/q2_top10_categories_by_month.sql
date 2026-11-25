-- Q2. Top 10 product categories by sales value in each purchase month.
--
-- Rules (from the case):
--   * delivered orders only, month from order_purchase_timestamp
--   * sales value = SUM(price); freight is excluded
--
-- Assumptions (see README):
--   * Products with no category are grouped as '(unknown)' and compete in the
--     ranking like any other category. Their sales are real, so hiding them
--     would make the monthly totals look smaller than they are.
--   * Ties use RANK(): if two categories tie for 10th place, both are shown,
--     so a month can return more than 10 rows. Nothing is dropped arbitrarily.
--
-- Joining items to products is safe here: each item has exactly one product,
-- so the join does not multiply rows.

WITH category_sales AS (
    SELECT
        date_trunc('month', o.order_purchase_timestamp)::date      AS purchase_month,
        COALESCE(p.product_category_name, '(unknown)')              AS product_category,
        SUM(i.price)                                                AS sales_value,
        COUNT(DISTINCT o.order_id)                                  AS orders
    FROM olist.orders o
    JOIN olist.order_items i ON i.order_id = o.order_id
    JOIN olist.products p    ON p.product_id = i.product_id
    WHERE o.order_status = 'delivered'
    GROUP BY 1, 2
),
ranked AS (
    SELECT
        *,
        RANK() OVER (PARTITION BY purchase_month ORDER BY sales_value DESC) AS sales_rank
    FROM category_sales
)
SELECT
    to_char(purchase_month, 'YYYY-MM') AS purchase_month,
    sales_rank,
    product_category,
    sales_value,
    orders
FROM ranked
WHERE sales_rank <= 10
ORDER BY purchase_month, sales_rank, product_category;
