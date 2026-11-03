# Previsión diaria de demanda en supermercados

## Contexto

¿Podría prevernos cuánto va a vender cada una de nuestras cinco tiendas de cada producto, día a día, durante las próximas dos semanas a partir del lunes 2 de noviembre? Con esas cifras hacemos los pedidos. Le adjunto el historial de ventas, los datos maestros y algún archivo más.
<!-- tier: easy -->

**En esta ronda** solo necesitamos la previsión base: lo que vende cada tienda en un día normal. El efecto de las promociones y del festivo regional único del periodo lo añade nuestro equipo de categorías encima de sus cifras, así que deje fuera las dos cosas. Los panecillos (I07) no se evalúan en esta ronda (mientras se asienta el cambio a paquetes, los pide la propia panadería); aun así, mantenga sus filas en el archivo.
<!-- /tier -->
<!-- tier: medium -->

**En esta ronda** necesitamos la previsión completa, con las promociones y el festivo regional único. Los panecillos (I07) no se evalúan en esta ronda (mientras se asienta el cambio a paquetes, los pide la propia panadería); aun así, mantenga sus filas en el archivo.
<!-- /tier -->

## Entregable

Un archivo CSV, `forecast.csv`, con la cabecera `store_id,item_id,date,forecast`. Una fila por cada tienda (S1–S5) × artículo (I01–I12) × día del 2026-11-02 al 2026-11-15, es decir, 840 filas. Los códigos, exactamente como en los datos; las fechas, en formato YYYY-MM-DD; `forecast` es un número (se admiten decimales) en la `unidad_venta` actual del artículo.

## Notas sobre los datos

- `historial_ventas.csv` abarca del 2024-11-04 al 2026-11-01, con una fila de ventas por tienda, artículo y día de apertura, más filas aparte para las devoluciones (véase más abajo). `tiendas.csv` y `articulos.csv` son los maestros de tiendas y artículos; `festivos.csv` recoge los festivos de ese periodo y `plan_promociones.csv` es el plan de promociones para el periodo de la previsión.
<!-- tier: easy medium -->
- En esta ronda evaluamos la previsión con lo que registran las cajas, tal como lo muestra nuestro informe semanal de ventas: `unidades_vendidas` tal como se registraron, las devoluciones de clientes (filas aparte con `unidades_vendidas` negativas, en la fecha de la devolución) restadas de las ventas de ese día, y los días con `rotura_stock = sí` tal como quedaron registrados. Corregir lo que no se vendió por tener el lineal vacío queda para una ronda posterior.
<!-- /tier -->
<!-- tier: hard -->
- Lo que necesitamos es una previsión de la demanda de los clientes, no de lo que registró la caja. Los días con `rotura_stock = sí` el lineal se quedó vacío, así que `unidades_vendidas` es solo lo que había en stock y la demanda real fue mayor. No trate esos días como ventas normales.
- Las devoluciones de clientes se registran en `historial_ventas.csv` como filas aparte con `unidades_vendidas` negativas, en la fecha de la devolución. Las devoluciones no son demanda: deje fuera esas filas y no las reste de las ventas del día.
<!-- /tier -->
- La tienda Casco Antiguo (S4) cierra los domingos, por eso no tiene filas en domingo. Su previsión para los domingos debe ser 0.
<!-- tier: easy -->
- `descuento_promo_pct` en el historial indica el descuento de los días en que un artículo estaba en promoción en una tienda (0 = sin promoción); esos días se vendió más que un día normal. Las promociones de `plan_promociones.csv` las añade el equipo de categorías en esta ronda: prevea esos días como días normales, sin ningún aumento por promoción.
- En el periodo de la previsión hay un festivo regional único que no figura en `festivos.csv`. Su efecto también lo añade el equipo de categorías, así que prevea ese día como un día normal de su día de la semana.
<!-- /tier -->
<!-- tier: medium hard -->
- `descuento_promo_pct` en el historial indica el descuento de los días en que un artículo estaba en promoción en una tienda (0 = sin promoción). Las promociones del periodo de la previsión están en `plan_promociones.csv`; `fecha_inicio` y `fecha_fin` están incluidas las dos, y hay que tenerlas en cuenta. El aumento de ventas crece con el descuento y es distinto según la categoría; estímelo a partir de las promociones pasadas.
<!-- when: promo_uplift=1 -->
- Las promociones de noviembre funcionan como las anteriores (solo con la etiqueta en el lineal, sin folleto), así que el aumento que estime del historial vale tal cual.
<!-- /when -->
<!-- when: promo_uplift=1.5,2 -->
- Las promociones de noviembre salen además en nuestro folleto impreso, cosa que nunca pasó con las del historial. El equipo de categorías calcula que cada una traerá unas {{promo_uplift}} veces las ventas adicionales de una promoción pasada con el mismo descuento en la misma categoría.
<!-- /when -->
<!-- /tier -->
<!-- tier: hard -->
- El viernes 30 de octubre, después de exportar `plan_promociones.csv`, el proveedor retiró su financiación y se cancelaron todas las promociones de {{promo_cancelled}} del plan: no se harán. El resto del plan se mantiene.
<!-- /tier -->
<!-- tier: medium hard -->
- El {{holiday_date}} es un festivo regional único (el aniversario de la ciudad) y no figura en `festivos.csv`. Ese día todas las tiendas abren con normalidad. En los festivos anteriores la demanda subió, más en panadería y bebidas que en fruta y verdura y lácteos; cuente con el mismo patrón.
<!-- /tier -->
<!-- tier: hard -->
- Los panecillos (I07) se vendían y registraban por unidad hasta el 31 de mayo de 2026. Desde el 1 de junio de 2026 se venden en paquetes de 6, que es la `unidad_venta` actual. Divida por 6 el historial anterior al 1 de junio de 2026 y prevea I07 en paquetes.
<!-- /tier -->
- Nuestra costumbre: nunca prevemos menos de {{min_display}} unidades de un artículo básico, es decir, de fruta y verdura y lácteos (I01–I06), en un día en que la tienda abre, para que los lineales no parezcan vacíos.

## Cómo se evalúa la previsión

**Restricciones obligatorias** (si se incumple alguna, la previsión no cuenta):

- Exactamente una fila por cada tienda × artículo × fecha del periodo; que no falte ninguna ni haya repetidas.
- Ninguna previsión negativa.
- S4 tiene previsión 0 los domingos.
- Los artículos de fruta y verdura y de lácteos tienen previsión de {{min_display}} o más en todos los días que la tienda abre.

<!-- when: short_weight=1 -->
**Calidad**: para cada tienda, el WAPE (error porcentual absoluto ponderado) = suma de |previsión − real| de todos sus artículos y días ÷ suma de lo real; después, la media de las cinco tiendas. Una unidad de más y una unidad de menos cuentan lo mismo.
<!-- /when -->
<!-- when: short_weight=2,3 -->
**Calidad**: un lineal vacío nos cuesta más que una unidad sobrante, así que cada unidad prevista de menos cuenta {{short_weight}} veces lo que una unidad prevista de más. Para cada tienda: la suma, sobre todos sus artículos y días, de {{short_weight}} × (real − previsión) donde la previsión queda por debajo de lo real y de (previsión − real) donde queda por encima, ÷ la suma de lo real; después, la media de las cinco tiendas.
<!-- /when -->
<!-- tier: easy -->

"Lo real" son las ventas base: lo que registran las cajas esos días, con las devoluciones restadas y sin el efecto de las promociones ni del festivo, que retira el equipo de categorías. Los panecillos (I07) quedan fuera de las sumas en esta ronda. Cuanto más bajo, mejor.
<!-- /tier -->
<!-- tier: medium -->

"Lo real" es lo que registran las cajas esos días, con las devoluciones restadas. Los panecillos (I07) quedan fuera de las sumas en esta ronda. Cuanto más bajo, mejor.
<!-- /tier -->
<!-- tier: hard -->

"Lo real" es la demanda de los clientes: lo que querían comprar, incluido lo que no pudieron comprar por una rotura de stock, en la unidad de venta actual. Cuanto más bajo, mejor.
<!-- /tier -->
