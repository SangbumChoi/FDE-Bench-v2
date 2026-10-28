# Plan de compras para las próximas ocho semanas

## Contexto

Ensamblamos dos modelos de placa de control y compramos unos veinte componentes a varios proveedores. ¿Podría planificar qué debemos pedir y a qué proveedor durante los próximos dos meses, para que la producción no se detenga y no gastemos de más? Le adjunto el plan de producción, la lista de materiales, el inventario actual, los pedidos abiertos, las cotizaciones de los proveedores, la lista de proveedores homologados y el presupuesto.
Últimamente el suministro anda inestable, así que también le añado el historial de entregas de los proveedores de los últimos seis meses y el aviso de asignación que recibimos. La lista de materiales ya incluye el cambio que ingeniería tiene previsto en la memoria flash de las dos placas.

## Entregable

Un archivo CSV, `orders.csv`, con la cabecera `order_week,component_id,supplier_id,quantity`. Una fila por línea de pedido. `order_week` es la semana en que se emite el pedido, como número del 1 al 8 (1 = W1, la semana que empieza el lunes 23 de noviembre de 2026; 8 = W8, la semana del 11 de enero de 2027). `component_id` y `supplier_id` exactamente como en los datos. `quantity` en piezas (unidades enteras), también para las resistencias. Las filas con la misma semana, componente y proveedor se suman en una sola línea de pedido.

## Notas sobre los datos

- `plan_produccion.csv` indica cuántas placas fabricamos cada semana (`placas`) de cada modelo (`id_producto` B100 y B200), de W1 a W10. Solo emitimos pedidos de W1 a W8; W9 y W10 están en el plan para evaluar lo que cubren los últimos pedidos. El stock que quede después de W10 no tiene ningún valor en este plan.
- `lista_materiales.csv` es la lista de materiales: cada placa de ese modelo lleva `cantidad_por_placa` piezas del componente. La necesidad de un componente en una semana es el número de placas de cada modelo fabricadas esa semana por su `cantidad_por_placa`, sumado para los dos modelos. La B100 no lleva pantalla ni antena.
<!-- tier: easy medium -->
- El cambio de la flash que aparece en `lista_materiales.csv` (C04 hasta W5, la nueva C25 desde W6) todavía no está aprobado para esta ronda: planifique como si las dos placas siguieran usando C04 las diez semanas, e ignore las filas de C25 y las columnas `semana_desde` y `semana_hasta`. No hace falta C25.
<!-- /tier -->
<!-- tier: hard -->
- `semana_desde` y `semana_hasta` en `lista_materiales.csv` indican en qué semanas se aplica cada fila (vea el cambio de ingeniería más abajo).
<!-- /tier -->
- `inventario.csv`: `existencias` es el stock al inicio de W1. Está en piezas para todos los componentes salvo las resistencias SMD (C07, C08, C09), que el almacén cuenta en bobinas de 5.000 piezas: `existencias = 12` en una resistencia significa 60.000 piezas.
- `pedidos_abiertos.csv`: pedidos ya emitidos y pagados. Llegan en la `semana_llegada` indicada y no forman parte del gasto de este plan.
<!-- tier: hard -->
  Ya están en camino, así que llegan a tiempo.
<!-- /tier -->
- `cotizaciones_proveedores.xlsx`, hoja `cotizaciones`: una fila por componente y proveedor, con el precio por pieza `precio_unitario` en la `moneda` indicada. Pacific Parts (S04) cotiza en dólares estadounidenses y todos los demás en KRW. Nuestro presupuesto está en KRW y convertimos con un tipo de cambio fijo de planificación de **{{usd_krw}} KRW por USD**, no con el tipo de mercado.
<!-- tier: easy -->
- En esta ronda planificamos a precio de lista: cada línea se paga a `precio_unitario` por pieza, sea cual sea su tamaño; ignore las columnas de tramos.
- También tratamos los plazos como semanas completas en esta ronda: divida `plazo_entrega_dias` entre 5 y redondee hacia arriba para obtener L semanas, sin tener en cuenta los festivos. El pedido se emite el lunes de su semana, y un pedido emitido en la semana w con un plazo de L semanas puede usarse a partir de la semana w+L (pedido en W1 con 12 días = 3 semanas → disponible en W4). Lo recibido está disponible para toda la necesidad de la semana de llegada.
- `pedido_minimo` es la cantidad mínima por línea de pedido, es decir, por proveedor, componente y semana de pedido. Por debajo, el proveedor no envía. Las cantidades pedidas en semanas distintas nunca se suman para el pedido mínimo.
<!-- /tier -->
<!-- tier: medium hard -->
- `plazo_entrega_dias` está en **días hábiles** (de lunes a viernes), no en días naturales. Hay dos semanas cortas: W5 (del 21 al 25 de diciembre, Navidad) y W6 (del 28 de diciembre al 1 de enero, Año Nuevo) tienen solo 4 días hábiles cada una; las demás semanas tienen 5.
- Plazos: el pedido se emite el lunes de su semana. El plazo se cuenta en días hábiles desde ese lunes, y la mercancía puede usarse a partir de la primera semana que empieza después de su llegada. Es decir, la semana de llegada es la primera semana k en la que los días hábiles desde el inicio de la semana del pedido hasta el final de la semana k-1 suman al menos el plazo. Ejemplos: 5 días pedido en W1 → disponible en W2; 12 días pedido en W1 → W4; 10 días pedido en W4 → W7 (W4 tiene 5 días, W5 y W6 solo 4 cada una). Lo recibido está disponible para toda la necesidad de la semana de llegada.
- `pedido_minimo` es la cantidad mínima por línea de pedido, es decir, por proveedor, componente y semana de pedido. Por debajo, el proveedor no envía. Los tramos de precio también se aplican por línea de pedido: si una línea alcanza `tramo1_cantidad`, toda la línea se paga a `tramo1_precio`; desde `tramo2_cantidad`, a `tramo2_precio`. Las cantidades pedidas en semanas distintas nunca se suman para el pedido mínimo ni para los tramos.
<!-- /tier -->
- `proveedores_homologados.csv`: un componente solo puede comprarse a un proveedor cuyo `estado` para ese componente sea `homologado`. `en evaluación` (aún en calificación) y `suspendido` no valen, aunque el proveedor haya enviado cotización.
- {{hold_supplier}} está en retención de calidad: sus lotes con llegada prevista de W1 a W{{hold_until}} se rechazan en la inspección de entrada y no llegan a la línea. Su mercancía solo puede llegar después de W{{hold_until}}.
- `presupuesto.csv` es un tope mensual fijado por nuestra casa matriz, no un objetivo. Cada pedido cuenta en el mes del lunes de su semana de pedido: W1-W2 son noviembre de 2026, W3-W6 diciembre de 2026, W7-W8 enero de 2027. Los pedidos en USD cuentan a {{usd_krw}} KRW por USD.
- Los componentes críticos son los que tienen `critico = sí` en `componentes.csv`. Para ellos queremos un stock de seguridad de **{{safety_weeks}} veces su necesidad semanal media**: su necesidad total en las semanas en que se usa, dividida entre el número de esas semanas, multiplicada por {{safety_weeks}} y redondeada hacia arriba. Debe haber esa cantidad al final de cada semana en que se usa el componente.
- Nuestra política: cada componente crítico en uso se pide a al menos dos proveedores distintos durante las ocho semanas, y ningún proveedor recibe más del **{{max_share}} %** de la cantidad total pedida de ese componente (contando solo los pedidos de este plan, en piezas), para mantener calificada una segunda fuente.
<!-- tier: easy medium -->
- En esta ronda no usamos `historial_entregas.csv` ni `asignaciones.csv`: planifique como si todos los proveedores entregaran en la semana prometida y confirmaran todo lo que pedimos.
<!-- /tier -->
<!-- tier: hard -->
- Cambio de ingeniería: a partir de W6, todas las placas (los dos modelos) se fabrican con la nueva flash **C25** (una nueva revisión del chip) en lugar de **C04**; `lista_materiales.csv` muestra C04 vigente en W1-W5 y C25 en W6-W10. C04 solo se usa en W1-W5. La C04 que quede en stock al final de W5 se desecha a su costo estándar (el proveedor no la recompra), y la C04 que llegue después de W5 no sirve. C25 es un componente nuevo: no hay stock ni pedidos abiertos; la cotizan Mirae Semicon (S03), Hanbit Electronics (S01) y Express Parts (S09), todos homologados. C25 es crítico: su stock de seguridad se calcula sobre su necesidad de W6 a W10 y cuenta a partir del final de W6. C04, que se está retirando, no necesita stock de seguridad ni tiene que pedirse ya a dos proveedores; C25 sí.
- Retrasos: los proveedores no siempre entregan en la semana prometida. `historial_entregas.csv` recoge nuestras entregas de los últimos seis meses con la fecha prometida (un lunes) y la fecha en que recibimos la mercancía. Recibida en la fecha prometida o antes, cuenta como puntual; de 1 a 7 días después, como una semana de retraso; de 8 a 14 días después, como dos semanas. Nunca hubo retrasos mayores. Esperamos que cada proveedor se comporte en las próximas semanas como en su historial. Una entrega retrasada puede usarse una o dos semanas más tarde de lo previsto (lo que llegue después de W10 sigue sin valer). Una entrega es todo lo que un proveedor envía de un componente para la misma semana de llegada; cada entrega llega a tiempo o con retraso independientemente de las demás.
- Asignación: Mirae Semicon (S03) tiene en asignación el microcontrolador (C01) y la DRAM (C03), y Nara Display (S08) la pantalla (C06). `asignaciones.csv` indica lo máximo que cada uno confirmará por mes natural, contando todos nuestros pedidos de ese componente emitidos en ese mes (por el lunes de la semana de pedido, como en el presupuesto). Lo que pase de ahí no se confirma.
<!-- /tier -->

## Cómo se evalúa el plan

**Restricciones obligatorias** (si se incumple alguna, el plan no cuenta):

- Solo proveedores homologados para cada componente.
- Cada línea de pedido alcanza al menos el pedido mínimo del proveedor.
- Las compras de cada mes no superan el presupuesto de `presupuesto.csv`.
- Nada de {{hold_supplier}} tiene llegada prevista de W1 a W{{hold_until}}.
<!-- tier: hard -->
- Los pedidos mensuales a S03 de C01 y C03, y a S08 de C06, no superan `asignaciones.csv`.
<!-- /tier -->
- Cada componente crítico en uso se pide a al menos dos proveedores, ninguno con más del {{max_share}} % de la cantidad (es una costumbre nuestra; podemos hacer una excepción si ahorra dinero de verdad).

**Calidad** (cuanto más bajo, mejor), simulada semana a semana de W1 a W10 para cada componente: el stock al inicio de la semana más lo que llega esa semana (pedidos abiertos y este plan) cubre la necesidad de la semana; las placas que no se pueden fabricar por falta de una pieza la esperan y se fabrican en cuanto llega. El total es
- el coste de compra de todas las líneas de pedido en KRW (USD a {{usd_krw}} KRW por USD), más
- coste de almacenamiento: 0,5 % del `costo_estandar_krw` por pieza en stock al final de cada semana, más
- coste de espera: 5 veces el `costo_estandar_krw` por pieza de necesidad que sigue esperando al final de cada semana (una pieza que falta dos semanas cuenta dos veces), más
- déficit de stock de seguridad en componentes críticos: 1,5 veces el `costo_estandar_krw` por pieza por debajo del stock de seguridad al final de cada semana en que se usa el componente.
<!-- tier: medium hard -->

El coste de compra usa el tramo de precio que alcanza cada línea.
<!-- /tier -->
<!-- tier: hard -->

Además, la C04 que quede en stock al final de W5 cuesta su `costo_estandar_krw` por pieza (desecho), y la C04 no se simula después de W5. Como las entregas pueden retrasarse, el almacenamiento, la espera, el déficit y el desecho se cuentan como valores esperados según las probabilidades reales de cada proveedor de llegar una o dos semanas tarde (el historial es solo una muestra de ellas). Las compras se pagan completas, llegue la entrega a tiempo o no.
<!-- /tier -->
