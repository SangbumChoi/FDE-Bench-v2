# Plan de compras para las próximas ocho semanas

## Contexto

Ensamblamos dos modelos de placa de control y compramos unos veinte componentes a varios proveedores. ¿Podría planificar qué debemos pedir y a qué proveedor durante los próximos dos meses, para que la producción no se detenga y no gastemos de más? Le adjunto el plan de producción, la lista de materiales, el inventario actual, los pedidos abiertos, las cotizaciones de los proveedores, la lista de proveedores homologados y el presupuesto.
Últimamente el suministro anda inestable, así que también le añado el historial de entregas de los proveedores de los últimos seis meses y el aviso de asignación que recibimos. La lista de materiales ya incluye el cambio que ingeniería tiene previsto en la memoria flash de las dos placas.
También le reenvío nuestro intercambio de correos con Nara Display sobre el nuevo precio de la pantalla; téngalo en cuenta al calcular los precios de los pedidos.

## Entregable

Un archivo CSV, `orders.csv`, con la cabecera `order_week,component_id,supplier_id,quantity`. Una fila por línea de pedido. `order_week` es la semana en que se emite el pedido, como número del 1 al 8 (1 = W1, la semana que empieza el lunes 23 de noviembre de 2026; 8 = W8, la semana del 11 de enero de 2027). `component_id` y `supplier_id` exactamente como en los datos. `quantity` en piezas (unidades enteras), también para las resistencias. Las filas con la misma semana, componente y proveedor se suman en una sola línea de pedido.

## Notas sobre los datos

- `plan_produccion.csv` indica cuántas placas fabricamos cada semana (`placas`) de cada modelo (`id_producto` B100 y B200), de W1 a W10. Solo emitimos pedidos de W1 a W8; W9 y W10 están en el plan para evaluar lo que cubren los últimos pedidos. El stock que quede después de W10 no tiene ningún valor en este plan.
- `lista_materiales.csv` es la lista de materiales: cada placa de ese modelo lleva `cantidad_por_placa` piezas del componente. La necesidad de un componente en una semana es el número de placas de cada modelo fabricadas esa semana por su `cantidad_por_placa`, sumado para los dos modelos. La B100 no lleva pantalla ni antena. Las piezas se necesitan en la semana en que se fabrican las placas, no antes: lo que llega en una semana sirve para toda la producción de esa semana (no hay desfase de montaje).
- El cambio de la flash que aparece en `lista_materiales.csv` (C04 hasta W5, la nueva C25 desde W6) todavía no está aprobado para esta ronda (ingeniería aún está homologando C25): planifique como si las dos placas siguieran usando C04 las diez semanas, e ignore las filas de C25 y las columnas `semana_desde` y `semana_hasta`. No hace falta C25.
- `inventario.csv`: `existencias` es el stock al inicio de W1. Está en piezas para todos los componentes salvo las resistencias SMD (C07, C08, C09), que el almacén cuenta en bobinas de 5.000 piezas: `existencias = 12` en una resistencia significa 60.000 piezas.
- `pedidos_abiertos.csv`: pedidos ya emitidos y pagados. Llegan en la `semana_llegada` indicada y no forman parte del gasto de este plan.
- `cotizaciones_proveedores.xlsx`, hoja `cotizaciones`: una fila por componente y proveedor, con el precio por pieza `precio_unitario` en la `moneda` indicada. Pacific Parts (S04) cotiza en dólares estadounidenses y todos los demás en KRW. Nuestro presupuesto está en KRW y convertimos con un tipo de cambio fijo de planificación de **1.450 KRW por USD**, no con el tipo de mercado.
- Cambio de precio de Nara Display (los correos de `mail/`): hemos aceptado su aumento del 12% en el módulo de pantalla C06 para los pedidos que reciban a partir del miércoles 9 de diciembre de 2026. Se aplica a todos sus precios unitarios de C06, el de lista y los de los dos tramos. Enviamos cada pedido el lunes de su semana de pedido, así que los pedidos de W3 (lunes 7 de diciembre) mantienen el precio anterior y el aumento se aplica a sus pedidos de C06 desde W4. El 8% adicional que propusieron desde enero no se ha aceptado: planifique sin él. Los pedidos abiertos no se ven afectados.
- En esta ronda planificamos a precio de lista (los tramos requieren un acuerdo marco que aún no está firmado): cada línea se paga a `precio_unitario` por pieza (con el aumento acordado de Nara Display indicado arriba), sea cual sea su tamaño; ignore las columnas de tramos.
- También tratamos los plazos como semanas completas en esta ronda: `plazo_entrega_dias` cuenta días hábiles, no naturales; divídalo entre 5 y redondee hacia arriba para obtener L semanas, sin tener en cuenta los festivos (todas las semanas cuentan como cinco días hábiles, también las de Navidad y Año Nuevo). El pedido se emite el lunes de su semana, y un pedido emitido en la semana w con un plazo de L semanas puede usarse a partir de la semana w+L (pedido en W1 con 12 días = 3 semanas → disponible en W4). Lo recibido está disponible para toda la necesidad de la semana de llegada.
- `pedido_minimo` es la cantidad mínima por línea de pedido, es decir, por proveedor, componente y semana de pedido. Por debajo, el proveedor no envía. Las cantidades pedidas en semanas distintas nunca se suman para el pedido mínimo.
- `proveedores_homologados.csv`: un componente solo puede comprarse a un proveedor cuyo `estado` para ese componente sea `homologado`. `en evaluación` (aún en calificación) y `suspendido` no valen, aunque el proveedor haya enviado cotización.
- Hanbit Electronics (S01) está en retención de calidad: sus lotes con llegada prevista de W1 a W4 se rechazan en la inspección de entrada y no llegan a la línea. Su mercancía solo puede llegar después de W4.
- `presupuesto.csv` es un tope mensual fijado por nuestra casa matriz, no un objetivo: ningún mes puede superarlo. Cada pedido cuenta en el mes del lunes de su semana de pedido: W1-W2 son noviembre de 2026 (W2 empieza el lunes 30 de noviembre, así que cuenta en noviembre aunque la mayoría de sus días sean de diciembre), W3-W6 diciembre de 2026, W7-W8 enero de 2027. Los pedidos en USD cuentan a 1.450 KRW por USD.
- Los componentes críticos son los que tienen `critico = sí` en `componentes.csv`. Para ellos queremos un stock de seguridad de **1,5 veces su necesidad semanal media**: su necesidad total en las semanas en que se usa, dividida entre el número de esas semanas, multiplicada por 1,5 y redondeada hacia arriba. Debe haber esa cantidad al final de cada semana en que se usa el componente.
- Nuestra política: cada componente crítico en uso se pide a al menos dos proveedores distintos durante las ocho semanas, y ningún proveedor recibe más del **80 %** de la cantidad total pedida de ese componente (contando solo los pedidos de este plan, en piezas), para mantener calificada una segunda fuente.
- En esta ronda no usamos `historial_entregas.csv` ni `asignaciones.csv` (la dirección quiere primero un plan con las fechas confirmadas por los proveedores): planifique como si todos los proveedores entregaran en la semana prometida y confirmaran todo lo que pedimos.

## Cómo se evalúa el plan

**Restricciones obligatorias** (si se incumple alguna, el plan no cuenta):

- Solo proveedores homologados para cada componente.
- Cada línea de pedido alcanza al menos el pedido mínimo del proveedor.
- Las compras de cada mes no superan el presupuesto de `presupuesto.csv`.
- Nada de Hanbit Electronics (S01) tiene llegada prevista de W1 a W4.
- Cada componente crítico en uso se pide a al menos dos proveedores, ninguno con más del 80 % de la cantidad (es una costumbre nuestra; podemos hacer una excepción si ahorra dinero de verdad).

**Calidad** (cuanto más bajo, mejor), simulada semana a semana de W1 a W10 para cada componente: el stock al inicio de la semana más lo que llega esa semana (pedidos abiertos y este plan) cubre la necesidad de la semana; las placas que no se pueden fabricar por falta de una pieza la esperan y se fabrican en cuanto llega. El total es
- el coste de compra de todas las líneas de pedido en KRW (USD a 1.450 KRW por USD), más
- coste de almacenamiento: 0,5 % del `costo_estandar_krw` por pieza en stock al final de cada semana, más
- coste de espera: cada placa que espera una semana por una pieza que falta nos cuesta 10.000 KRW (penalizaciones por entrega tardía y horas extra para recuperar). Se cuenta por componente: cada pieza de necesidad que sigue esperando al final de una semana cuesta 10.000 KRW divididos entre las piezas de ese componente por placa (su necesidad dividida entre las placas fabricadas de los modelos que lo usan), y una pieza que falta dos semanas cuenta dos veces, más
- déficit de stock de seguridad en componentes críticos: 1,5 veces el `costo_estandar_krw` por pieza por debajo del stock de seguridad al final de cada semana en que se usa el componente.
