-- Investigation: are overpaid orders concentrated in installment payments?
WITH r AS (
  SELECT o.order_id,
         (SELECT SUM(payment_value) FROM olist.order_payments p WHERE p.order_id = o.order_id) AS paid,
         (SELECT SUM(price + freight_value) FROM olist.order_items i WHERE i.order_id = o.order_id) AS items,
         (SELECT MAX(payment_installments) > 1 FROM olist.order_payments p WHERE p.order_id = o.order_id) AS installments
  FROM olist.orders o
)
SELECT installments, COUNT(*) AS overpaid_orders
FROM r
WHERE paid - items > 0.01
GROUP BY installments;
