# Previsión diaria de demanda en supermercados

## Contexto

¿Podría prevernos cuánto va a vender cada una de nuestras cinco tiendas de cada producto, día a día, durante las próximas dos semanas a partir del lunes 2 de noviembre? Con esas cifras hacemos los pedidos. Le adjunto el historial de ventas, los datos maestros y algún archivo más.

**En esta ronda** solo necesitamos la previsión base: lo que vende cada tienda en un día normal. El efecto de las promociones y del festivo regional único del periodo lo añade nuestro equipo de categorías encima de sus cifras, así que deje fuera las dos cosas. Los panecillos (I07) no se evalúan en esta ronda (mientras se asienta el cambio a paquetes, los pide la propia panadería); aun así, mantenga sus filas en el archivo.

## Entregable

Un archivo CSV, `forecast.csv`, con la cabecera `store_id,item_id,date,forecast`. Una fila por cada tienda (S1–S5) × artículo (I01–I12) × día del 2026-11-02 al 2026-11-15, es decir, 840 filas. Los códigos, exactamente como en los datos; las fechas, en formato YYYY-MM-DD; `forecast` es un número (se admiten decimales) en la `unidad_venta` actual del artículo.

## Notas sobre los datos

- `historial_ventas.csv` abarca del 2024-11-04 al 2026-11-01, con una fila de ventas por tienda, artículo y día de apertura, más filas aparte para las devoluciones (véase más abajo). `tiendas.csv` y `articulos.csv` son los maestros de tiendas y artículos; `festivos.csv` recoge los festivos de ese periodo y `plan_promociones.csv` es el plan de promociones para el periodo de la previsión.
- En esta ronda evaluamos la previsión con lo que registran las cajas, tal como lo muestra nuestro informe semanal de ventas: `unidades_vendidas` tal como se registraron, las devoluciones de clientes (filas aparte con `unidades_vendidas` negativas, en la fecha de la devolución) restadas de las ventas de ese día, y los días con `rotura_stock = sí` tal como quedaron registrados. Corregir lo que no se vendió por tener el lineal vacío queda para una ronda posterior.
- La tienda Casco Antiguo (S4) cierra los domingos, por eso no tiene filas en domingo. Su previsión para los domingos debe ser 0.
- `descuento_promo_pct` en el historial indica el descuento de los días en que un artículo estaba en promoción en una tienda (0 = sin promoción); esos días se vendió más que un día normal. Las promociones de `plan_promociones.csv` las añade el equipo de categorías en esta ronda: prevea esos días como días normales, sin ningún aumento por promoción.
- En el periodo de la previsión hay un festivo regional único que no figura en `festivos.csv`. Su efecto también lo añade el equipo de categorías, así que prevea ese día como un día normal de su día de la semana.
- Nuestra costumbre: nunca prevemos menos de 4 unidades de un artículo básico, es decir, de fruta y verdura y lácteos (I01–I06), en un día en que la tienda abre, para que los lineales no parezcan vacíos.

## Cómo se evalúa la previsión

**Restricciones obligatorias** (si se incumple alguna, la previsión no cuenta):

- Exactamente una fila por cada tienda × artículo × fecha del periodo; que no falte ninguna ni haya repetidas.
- Ninguna previsión negativa.
- S4 tiene previsión 0 los domingos.
- Los artículos de fruta y verdura y de lácteos tienen previsión de 4 o más en todos los días que la tienda abre.

**Calidad**: un lineal vacío nos cuesta más que una unidad sobrante, así que cada unidad prevista de menos cuenta 3 veces lo que una unidad prevista de más. Para cada tienda: la suma, sobre todos sus artículos y días, de 3 × (real − previsión) donde la previsión queda por debajo de lo real y de (previsión − real) donde queda por encima, ÷ la suma de lo real; después, la media de las cinco tiendas.

"Lo real" son las ventas base: lo que registran las cajas esos días, con las devoluciones restadas y sin el efecto de las promociones ni del festivo, que retira el equipo de categorías. Los panecillos (I07) quedan fuera de las sumas en esta ronda. Cuanto más bajo, mejor.
