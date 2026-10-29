# Preguntas de la dirección sobre la base de datos de pedidos

## Contexto

Nuestros directivos nos han enviado estas preguntas. ¿Podría responderlas a partir de la exportación de la base de datos? Le adjuntamos las tablas, un pequeño diccionario de datos y la lista de preguntas; con un número por pregunta nos basta.

Vendemos cajas de suscripción de café y té, además de artículos sueltos, a clientes de Corea, Japón y Estados Unidos. Nuestra sede está en Seúl y todos los informes se hacen en wones (KRW).

## Entregable

Un archivo JSON, `answers.json`: `{"Q01": 123456000, "Q02": ..., ..., "Q12": 1.5}`. Un número por cada identificador de pregunta del archivo de preguntas (Q01 a Q12). Los importes en KRW, los porcentajes en tanto por ciento (4.25 significa 4,25 %) y, en la pregunta sobre un cliente, el `customer_id` numérico.

## Notas sobre los datos

- La exportación es un conjunto de tablas CSV (`customers.csv`, `accounts_meta.csv`, `products.csv`, `orders.csv`, `order_items.csv`, `payments.csv`, `refunds.csv`, `fx_rates.csv`). Los nombres de tablas y columnas están en inglés para poder cargarlos tal cual en SQL; las etiquetas de estado, categoría, etc. están en nuestro idioma de trabajo.
- **Año fiscal**: nuestro año fiscal empieza el 1 de abril y lleva el nombre del año natural en que empieza. FY2025 = del 2025-04-01 al 2026-03-31; FY2026 = del 2026-04-01 al 2027-03-31. El primer trimestre es abril–junio y el primer semestre, abril–septiembre.
- **Los días son en hora de Corea**: todas las marcas de tiempo (`ordered_at_utc`, `signup_at_utc`, ...) se guardan en UTC, pero para nosotros un «día» es un día natural en hora de Corea (UTC+9). Sume 9 horas antes de tomar la fecha; días, meses, trimestres y años fiscales se deciden así. Por ejemplo, un pedido del 2026-06-30 a las 16:30 UTC se hizo el 2026-07-01. La fecha de referencia de las preguntas es el 2026-09-30 (hora de Corea).
- **Qué pedidos cuentan**: solo los pedidos con status `completado`. Los pedidos `cancelado` y `pago_fallido` no cuentan nunca, aunque `payments.csv` tenga una fila de pago para ellos. Un pedido pertenece al periodo de su fecha de pedido.
- **Cuentas de prueba**: los clientes cuyo `account_type` en `accounts_meta.csv` es `prueba` son cuentas de QA. Por política de finanzas se excluyen de todas las cifras (pedidos, ingresos, recuentos de clientes, altas). Las cuentas `empleado` son clientes reales y se mantienen.
- **El ingreso neto** no incluye impuestos y descuenta los reembolsos: tome el `subtotal` del pedido (antes de impuestos) y reste los reembolsos de ese pedido sin su impuesto. Los importes de `refunds.csv` incluyen impuestos; la parte sin impuesto es `amount × subtotal / total` del pedido. Un reembolso reduce el ingreso del periodo en que se hizo el pedido, no del periodo del reembolso. La exportación se hizo el 2026-10-31: contiene los pedidos hechos hasta la fecha de referencia con todos los reembolsos registrados hasta la exportación, así que `refunds.csv` también tiene reembolsos de octubre de 2026; también cuentan, en el periodo de su pedido. Para una categoría, los reembolsos de un pedido se reparten entre sus líneas en proporción al importe de cada línea (`quantity × unit_price`).
- **Monedas**: los importes están en la moneda del pedido (`currency`). Conviértalos a KRW con el `krw_per_unit` de `fx_rates.csv` de la fecha del pedido (hora de Corea); los reembolsos de un pedido usan el mismo tipo. Los pedidos en KRW no necesitan conversión.
- **Cliente activo**: cliente con al menos un pedido válido cuya fecha cae en los 90 días que terminan en la fecha de referencia, es decir, del 2026-07-03 al 2026-09-30, ambos incluidos.
- **Categoría renombrada**: el 2025-10-01 la categoría `snacks` pasó a llamarse `despensa`. Los productos lanzados desde entonces llevan `despensa`, pero los anteriores siguen con `snacks` en `products.csv` (el catálogo nunca se migró). Es una sola categoría: una pregunta sobre `despensa` incluye ambas etiquetas durante todo el periodo.
- **Definiciones por pregunta**: valor medio por pedido = ingreso neto / número de pedidos válidos. Tasa de reembolso = reembolsos sin impuesto / ingreso antes de reembolsos (suma de subtotales), para los pedidos del periodo, en porcentaje. Reembolso medio por pedido reembolsado = reembolsos sin impuesto (KRW) / número de pedidos válidos del periodo con al menos un reembolso. Clientes nuevos = clientes cuya fecha de alta cae en el periodo. Variación mensual = (septiembre / agosto − 1) × 100. Unidades por pedido = suma de `quantity` / número de pedidos válidos.
- **Redondeo (política de finanzas)**: toda cifra monetaria que reportamos (Q01, Q02, Q06, Q07, Q09) se redondea al millar de KRW más cercano; por ejemplo, 38.412 pasa a 38.000. Los recuentos, identificadores, porcentajes y unidades no se redondean.

## Cómo se evalúan las respuestas

**Restricciones obligatorias** (si se incumple alguna, la hoja de respuestas no cuenta):

- Cada pregunta Q01–Q12 se responde con un único número.
- Se excluyen las cuentas de prueba; una respuesta de recuento o de cliente que coincida con la cifra que incluye las cuentas de prueba incumple la política de finanzas.
- Toda cifra monetaria (Q01, Q02, Q06, Q07, Q09) es un múltiplo exacto de 1.000 KRW.

**Calidad**: el número de preguntas respondidas correctamente. Cada respuesta se compara con la cifra exacta (sin redondear) según las definiciones anteriores: el identificador de cliente y los recuentos (Q03, Q04, Q05, Q10) deben coincidir exactamente; una cifra monetaria debe quedar dentro del 0,5 % o de 500 KRW de la cifra exacta, lo que sea más amplio (así, la cifra exacta redondeada al millar más cercano siempre cuenta); la variación mensual (Q11), dentro de 0,05 puntos porcentuales; las demás respuestas, dentro del 0,5 % de la cifra exacta. Cuantas más, mejor.
