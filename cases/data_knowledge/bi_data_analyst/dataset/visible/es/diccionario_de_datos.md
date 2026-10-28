# Diccionario de datos

Todos los archivos son CSV (UTF-8). Los nombres de tablas y columnas se mantienen en inglés para poder usarlos directamente en SQL.

- `customers.csv`: customer_id, signup_at_utc (marca de tiempo, UTC), country (KR / JP / US), plan (suscripción, compra_suelta)
- `accounts_meta.csv`: customer_id, account_type (normal, empleado, prueba)
- `products.csv`: product_id, product_name, category (caja, café, té, snacks, despensa, accesorios), list_price_krw
- `orders.csv`: order_id, customer_id, ordered_at_utc (marca de tiempo, UTC), status (completado, cancelado, pago_fallido), currency (KRW / JPY / USD), subtotal, tax, total (importes en la moneda del pedido)
- `order_items.csv`: order_id, product_id, quantity, unit_price (moneda del pedido)
- `payments.csv`: payment_id, order_id, paid_at_utc (marca de tiempo, UTC), amount (moneda del pedido), method (tarjeta, transferencia, monedero)
- `refunds.csv`: refund_id, order_id, refunded_at_utc (marca de tiempo, UTC), amount (moneda del pedido), reason (dañado, artículo_erróneo, cambio_de_opinión, retraso)
- `fx_rates.csv`: rate_date, currency, krw_per_unit (KRW por una unidad de la moneda)
