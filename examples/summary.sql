-- Сводка по городам для оплаченных заказов.
SELECT city, COUNT(*) AS orders, COUNT(amount) AS priced,
       SUM(amount) AS total, AVG(amount) AS average
FROM orders
WHERE status = 'paid'
GROUP BY city
ORDER BY total DESC, city ASC
LIMIT 3;
