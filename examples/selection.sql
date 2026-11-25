SELECT id, customer AS "Покупатель", amount
FROM orders
WHERE paid = TRUE AND (amount >= 100 OR amount IS NULL)
ORDER BY amount DESC, id ASC
LIMIT 4;
