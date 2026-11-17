# Previsión diaria de demanda en supermercados

## Contexto

¿Podría prevernos cuánto va a vender cada una de nuestras cinco tiendas de cada producto, día a día, durante las próximas dos semanas a partir del lunes 2 de noviembre? Con esas cifras hacemos los pedidos. Le adjunto el historial de ventas, los datos maestros y algún archivo más.

**Para qué sirven las cifras.** Cada tienda pide exactamente la cifra de su archivo para cada producto y cada día; la mercancía llega esa misma mañana y nadie le añade un margen de seguridad. Así que lo que necesitamos es la cantidad a pedir, no las ventas esperadas.

**Lo que nos cuesta una cifra equivocada.** Una unidad que sigue en el lineal al cierre nos cuesta más o menos lo que vale una unidad: se da de baja o se liquida con pérdida. Una unidad que un cliente quería y no encontró nos cuesta unas {{lost_sale_cost}} veces más: el margen, y los clientes que la próxima vez compran en otro sitio. Vale para todos los productos y todas las tiendas.

**Cómo piden hoy las tiendas.** Cada gerente pide por costumbre: para cada producto, la media de lo que la tienda vendió ese día de la semana en las últimas ocho semanas, sin contar los días en que se quedó sin género, más un {{habit_cushion}}% aproximadamente por seguridad; alrededor de un 2% más por cada punto de descuento cuando el producto está en promoción; un festivo, como un sábado. Queremos algo mejor que eso.
<!-- tier: easy -->

**En esta ronda** necesitamos el pedido sin las promociones: el efecto de las promociones lo añade después nuestro equipo de categorías encima de sus cifras, así que déjelas fuera. Los panecillos (I07) no se evalúan en esta ronda (mientras se asienta el cambio a paquetes, los pide la propia panadería); aun así, mantenga sus filas en el archivo.
<!-- /tier -->
<!-- tier: medium -->

**En esta ronda** necesitamos el pedido completo, con las promociones incluidas: nadie las añade después. Los panecillos (I07) no se evalúan en esta ronda (mientras se asienta el cambio a paquetes, los pide la propia panadería); aun así, mantenga sus filas en el archivo.
<!-- /tier -->
<!-- tier: hard -->

**En esta ronda** necesitamos el pedido completo, con las promociones incluidas: nadie las añade después. Los panecillos (I07) forman parte de él.
<!-- /tier -->

## Entregable

Un archivo CSV, `forecast.csv`, con la cabecera `store_id,item_id,date,order_qty`. Una fila por cada tienda (S1–S5) × artículo (I01–I12) × día del 2026-11-02 al 2026-11-15, es decir, 840 filas, incluidos los domingos de la tienda Casco Antiguo y los panecillos. Nuestro sistema de pedidos carga el archivo tal cual, así que tienen que estar todas esas filas. Los códigos, exactamente como en los datos; las fechas, en formato YYYY-MM-DD; `order_qty` es la cantidad que la tienda pide para ese día, un número (se admiten decimales) en la `unidad_venta` actual del artículo.

## Notas sobre los datos

- `historial_ventas.csv` abarca del 2024-11-04 al 2026-11-01, con una fila de ventas por tienda, artículo y día de apertura, más filas aparte para las devoluciones (véase más abajo). `tiendas.csv` y `articulos.csv` son los maestros de tiendas y artículos; `festivos.csv` recoge los festivos de ese periodo; `plan_promociones.csv` es el plan de promociones para el periodo de la previsión; en `mail/` hay un correo de uno de nuestros gerentes de tienda (véase más abajo).
- El pedido tiene que cubrir la demanda de los clientes, no lo que registró la caja. Los días con `rotura_stock = sí` el lineal se quedó vacío, así que `unidades_vendidas` es solo lo que había en stock y la demanda real fue mayor. No trate esos días como ventas normales.
- Las devoluciones de clientes se registran en `historial_ventas.csv` como filas aparte con `unidades_vendidas` negativas, en la fecha de la devolución. Las devoluciones no son demanda: deje fuera esas filas y no las reste de las ventas del día.
- La tienda Casco Antiguo (S4) cierra los domingos, por eso no tiene filas en domingo. Su pedido para los domingos debe ser 0.
<!-- tier: easy -->
- `descuento_promo_pct` en el historial indica el descuento de los días en que un artículo estaba en promoción en una tienda (0 = sin promoción); esos días se vendió más que un día normal. Las promociones de `plan_promociones.csv` las añade el equipo de categorías en esta ronda: pida para esos días como para días normales, sin ningún aumento por promoción.
<!-- /tier -->
<!-- tier: medium hard -->
- `descuento_promo_pct` en el historial indica el descuento de los días en que un artículo estaba en promoción en una tienda (0 = sin promoción). Las promociones del periodo de la previsión están en `plan_promociones.csv`; `fecha_inicio` y `fecha_fin` están incluidas las dos, y tienen que estar en el pedido. El aumento de ventas crece con el descuento y es distinto según la categoría; estímelo a partir de las promociones pasadas.
<!-- when: promo_uplift=1 -->
- Las promociones de noviembre funcionan como las anteriores (solo con la etiqueta en el lineal, sin folleto), así que el aumento que estime del historial vale tal cual.
<!-- /when -->
<!-- when: promo_uplift=2,3 -->
- Las promociones de noviembre salen además en nuestro folleto impreso, cosa que nunca pasó con las del historial. El equipo de categorías calcula que cada una traerá unas {{promo_uplift}} veces las ventas adicionales de una promoción pasada con el mismo descuento en la misma categoría, y los gerentes cuentan con lo mismo.
<!-- /when -->
<!-- /tier -->
<!-- tier: hard -->
- El viernes 30 de octubre, después de exportar `plan_promociones.csv`, el proveedor retiró su financiación y se cancelaron todas las promociones de {{promo_cancelled}} del plan: no se harán. El resto del plan se mantiene.
<!-- /tier -->
- El {{holiday_date}} es un festivo regional único (el aniversario de la ciudad) y no figura en `festivos.csv`. Ese día todas las tiendas abren con normalidad. En los festivos anteriores la demanda subió, más en panadería y bebidas que en fruta y verdura y lácteos; cuente con el mismo patrón.
<!-- tier: hard -->
- Los panecillos (I07) se vendían y registraban por unidad hasta el 31 de mayo de 2026. Desde el 1 de junio de 2026 se venden en paquetes de 6, que es la `unidad_venta` actual. Divida por 6 el historial anterior al 1 de junio de 2026 y pida I07 en paquetes.
<!-- /tier -->
- El correo de `mail/` es del gerente de nuestra tienda Plaza Central (S1), que pide un 20% más sobre las cifras de su tienda. Es un deseo suyo, no la política de la empresa: Plaza Central se pide como todas las demás tiendas. No añada ese 20%.
- Nuestra costumbre: nunca pedimos menos de {{min_display}} unidades de un artículo básico, es decir, de fruta y verdura y lácteos (I01–I06), para un día en que la tienda abre, para que los lineales no parezcan vacíos.

## Cómo se evalúa el pedido

**Restricciones obligatorias** (si se incumple alguna, el archivo no cuenta):

- Exactamente una fila por cada tienda × artículo × fecha del periodo; que no falte ninguna ni haya repetidas.
- Ninguna cantidad de pedido negativa.
- S4 tiene pedido 0 los domingos.
- Los artículos de fruta y verdura y de lácteos tienen un pedido de {{min_display}} o más en todos los días que la tienda abre.

**Calidad**: no esperamos a noviembre para ver cómo salieron las cifras; valoramos el plan por lo que nos cuesta de media, sabiendo cuánto varía la demanda de un día a otro. Para cada tienda: sobre todos sus artículos y días, las unidades que esperamos que sobren más {{lost_sale_cost}} veces las unidades que esperamos que falten, dividido por la demanda esperada de la tienda; después, la media de las cinco tiendas. Cuanto más bajo, mejor.
<!-- tier: easy -->

Aquí "demanda" es la demanda sin el efecto de las promociones, que añade el equipo de categorías. Los panecillos (I07) quedan fuera de las sumas en esta ronda.
<!-- /tier -->
<!-- tier: medium -->

Los panecillos (I07) quedan fuera de las sumas en esta ronda.
<!-- /tier -->
<!-- tier: hard -->

Los panecillos (I07) cuentan, en paquetes.
<!-- /tier -->
