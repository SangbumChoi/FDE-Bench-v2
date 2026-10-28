# Data dictionary

All files are CSV (UTF-8). Table and column names are kept in English so they can be used directly in SQL.

- `customers.csv`: customer_id, signup_at_utc (timestamp, UTC), country (KR / JP / US), plan (subscription, one_off)
- `accounts_meta.csv`: customer_id, account_type (regular, staff, test)
- `products.csv`: product_id, product_name, category (box, coffee, tea, snacks, pantry, accessories), list_price_krw
- `orders.csv`: order_id, customer_id, ordered_at_utc (timestamp, UTC), status (completed, cancelled, payment_failed), currency (KRW / JPY / USD), subtotal, tax, total (amounts in the order currency)
- `order_items.csv`: order_id, product_id, quantity, unit_price (order currency)
- `payments.csv`: payment_id, order_id, paid_at_utc (timestamp, UTC), amount (order currency), method (card, bank_transfer, wallet)
- `refunds.csv`: refund_id, order_id, refunded_at_utc (timestamp, UTC), amount (order currency), reason (damaged, wrong_item, changed_mind, late_delivery)
- `fx_rates.csv`: rate_date, currency, krw_per_unit (KRW for one unit of the currency)
