# Previsión diaria de demanda en supermercados

## Contexto

¿Podría prevernos cuánto va a vender cada una de nuestras cinco tiendas de cada producto, día a día, durante las próximas dos semanas a partir del lunes 2 de noviembre? Con esas cifras hacemos los pedidos. Le adjunto el historial de ventas, los datos maestros y algún archivo más.

## Entregable

Un archivo CSV, `forecast.csv`, con la cabecera `store_id,item_id,date,forecast`. Una fila por cada tienda (S1–S5) × artículo (I01–I12) × día del 2026-11-02 al 2026-11-15, es decir, 840 filas. Los códigos, exactamente como en los datos; las fechas, en formato YYYY-MM-DD; `forecast` es un número (se admiten decimales) en la `unidad_venta` actual del artículo.

## Notas sobre los datos

- `historial_ventas.csv` abarca del 2024-11-04 al 2026-11-01, con una fila de ventas por tienda, artículo y día de apertura, más filas aparte para las devoluciones (véase más abajo). `tiendas.csv` y `articulos.csv` son los maestros de tiendas y artículos; `festivos.csv` recoge los festivos de ese periodo y `plan_promociones.csv` es el plan de promociones para el periodo de la previsión.
- Lo que necesitamos es una previsión de la demanda de los clientes, no de lo que registró la caja. Los días con `rotura_stock = sí` el lineal se quedó vacío, así que `unidades_vendidas` es solo lo que había en stock y la demanda real fue mayor. No trate esos días como ventas normales.
- Las devoluciones de clientes se registran en `historial_ventas.csv` como filas aparte con `unidades_vendidas` negativas, en la fecha de la devolución. Las devoluciones no son demanda: deje fuera esas filas y no las reste de las ventas del día.
- La tienda Casco Antiguo (S4) cierra los domingos, por eso no tiene filas en domingo. Su previsión para los domingos debe ser 0.
- `descuento_promo_pct` en el historial indica el descuento de los días en que un artículo estaba en promoción en una tienda (0 = sin promoción). Las promociones del periodo de la previsión están en `plan_promociones.csv`; `fecha_inicio` y `fecha_fin` están incluidas las dos, y hay que tenerlas en cuenta. El aumento de ventas crece con el descuento y es distinto según la categoría; estímelo a partir de las promociones pasadas.
- Las promociones de noviembre salen además en nuestro folleto impreso, cosa que nunca pasó con las del historial. El equipo de categorías calcula que cada una traerá unas 1,5 veces las ventas adicionales de una promoción pasada con el mismo descuento en la misma categoría.
- El viernes 30 de octubre, después de exportar `plan_promociones.csv`, el proveedor retiró su financiación y se cancelaron todas las promociones de bebidas del plan: no se harán. El resto del plan se mantiene.
- El miércoles 11 de noviembre de 2026 es un festivo regional único (el aniversario de la ciudad) y no figura en `festivos.csv`. Ese día todas las tiendas abren con normalidad. En los festivos anteriores la demanda subió, más en panadería y bebidas que en fruta y verdura y lácteos; cuente con el mismo patrón.
- Los panecillos (I07) se vendían y registraban por unidad hasta el 31 de mayo de 2026. Desde el 1 de junio de 2026 se venden en paquetes de 6, que es la `unidad_venta` actual. Divida por 6 el historial anterior al 1 de junio de 2026 y prevea I07 en paquetes.
- Nuestra costumbre: nunca prevemos menos de 8 unidades de un artículo básico, es decir, de fruta y verdura y lácteos (I01–I06), en un día en que la tienda abre, para que los lineales no parezcan vacíos.

## Cómo se evalúa la previsión

**Restricciones obligatorias** (si se incumple alguna, la previsión no cuenta):

- Exactamente una fila por cada tienda × artículo × fecha del periodo; que no falte ninguna ni haya repetidas.
- Ninguna previsión negativa.
- S4 tiene previsión 0 los domingos.
- Los artículos de fruta y verdura y de lácteos tienen previsión de 8 o más en todos los días que la tienda abre.

**Calidad**: un lineal vacío nos cuesta más que una unidad sobrante, así que cada unidad prevista de menos cuenta 2 veces lo que una unidad prevista de más. Para cada tienda: la suma, sobre todos sus artículos y días, de 2 × (real − previsión) donde la previsión queda por debajo de lo real y de (previsión − real) donde queda por encima, ÷ la suma de lo real; después, la media de las cinco tiendas.

"Lo real" es la demanda de los clientes: lo que querían comprar, incluido lo que no pudieron comprar por una rotura de stock, en la unidad de venta actual. Cuanto más bajo, mejor.
