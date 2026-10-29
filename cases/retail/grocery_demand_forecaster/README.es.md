# Analista de previsión de demanda en supermercados — `retail/grocery_demand_forecaster`

Una cadena regional de supermercados con cinco tiendas pide al agente que prevea "cuánto va a vender cada una de
nuestras cinco tiendas de cada producto, día a día, durante las próximas dos semanas a partir del lunes 2 de
noviembre", porque hace sus pedidos con esas cifras. El entregable es `forecast.csv` (`store_id,item_id,date,forecast`):
una fila por cada tienda (S1–S5) × artículo (I01–I12) × día del 2026-11-02 al 2026-11-15, 840 filas, en la unidad de
venta actual de cada artículo. La previsión se puntúa frente a la demanda real de los clientes en el periodo de la
previsión, que solo existe en el mundo.

El caso no tiene configuraciones: la petición, los datos, los requisitos ocultos y el evaluador son los mismos en todas
las dificultades. Los ajustes de modalidad (especificación completa frente a aclarar primero, perfil del cliente, ruido
en los datos, eventos) se aplican por encima, como en todos los casos (véase [cases/README.md](../../README.md)).

## Datos

- `sales_history` (43,718 filas, del 2024-11-04 al 2026-11-01, 104 semanas): una fila de ventas por tienda, artículo y
  día de apertura con `units_sold`, `promo_discount_pct` (0 = sin promoción) y un indicador `stockout` (4,390 filas con
  rotura de stock, en las que las ventas registradas son el 30–85% de la demanda), más 1,286 filas aparte de
  devoluciones de clientes con unidades negativas (−2,104 unidades frente a 2,002,817 vendidas). S4 no tiene filas en
  domingo.
- `promo_plan`: 14 promociones de tienda × artículo en el periodo de la previsión (10/20/30% de descuento, con las
  fechas de inicio y fin incluidas).
- `holidays`: 12 festivos pasados (Navidad, Año Nuevo, un festivo de primavera, uno de verano y uno de otoño, y el Día
  del Trabajo, cada uno dos veces). Ninguno cae en el periodo de la previsión, y el festivo único del miércoles 11 de
  noviembre no figura en la lista.
- `stores` (cuatro supermercados y la tienda exprés Casco Antiguo, S4) e `items` (12 artículos en cuatro categorías:
  fruta y verdura I01–I03, lácteos I04–I06, panadería I07–I09, bebidas I10–I12, con su unidad de venta). Los panecillos
  (I07) figuran en paquetes de 6; el historial los registra por unidad hasta el 31 de mayo de 2026.

El mundo es un modelo multiplicativo por tienda × artículo × día (escala y tendencia de la tienda, perfil semanal y
estacionalidad anual por categoría, efecto de las promociones según la categoría y el descuento, efecto de los festivos
por categoría) con ruido diario lognormal (σ = 0.07) y ventas de Poisson. Las roturas de stock se producen con la
probabilidad base del artículo, más 0.20 los días de promoción, con independencia de la demanda del día.

## Reglas

| Regla | Tipo | Qué exige |
|---|---|---|
| `complete_grid` | contractual | exactamente una fila por tienda × artículo × fecha del periodo |
| `non_negative` | física | ninguna previsión negativa |
| `closed_day_zero` | física | S4 cierra los domingos: su previsión para los domingos es 0 |
| `min_display_stock` | costumbre del negocio (flexible) | los artículos básicos (fruta y verdura y lácteos, I01–I06) se prevén en 6 o más todos los días de apertura |

La calidad es el WAPE por tienda (Σ |previsión − demanda| ÷ Σ demanda sobre sus artículos y días), promediado sobre las
cinco tiendas; cuanto más bajo, mejor. La demanda incluye lo que los clientes no pudieron comprar por una rotura de
stock.

## Situaciones presentes

Solo hechos ocultos. La petición dice únicamente "prevea lo que venderá cada tienda"; las nueve preguntas clave son la
censura por roturas de stock (prever la demanda, no las ventas registradas), las devoluciones (dejarlas fuera, no
restarlas), el cierre dominical de S4, el plan de promociones (fechas incluidas, efecto según la categoría y el
descuento), el festivo del 11 de noviembre, el cambio de unidad de I07, el mínimo de exposición de 6, la métrica WAPE y
el formato del archivo. No hay eventos con fecha ni mensajes de presión propios del caso; los únicos eventos los aporta
el eje de modalidad.

## Cifras de la referencia y la línea base (semilla 20261102)

La **referencia** es un modelo de nivel y perfil semanal por tienda × artículo, que tiene en cuenta la censura y se
construye solo con el historial: un perfil por día de la semana a partir de las últimas 52 semanas de días limpios (sin
rotura de stock, promoción ni festivo), un nivel a partir de las últimas 8 semanas de días limpios, un factor estacional
por categoría a partir del nivel del año pasado en torno al periodo de la previsión, un efecto de promoción por nivel de
descuento y un único efecto de festivo, ambos agregados sobre todas las categorías, el historial de I07 anterior al 1 de
junio de 2026 dividido por 6, las devoluciones fuera, los domingos de S4 a 0 y el mínimo de 6 en los artículos básicos.

La **línea base** es la previsión ingenua estacional que usaría un encargado de tienda sin un ingeniero: lo que registró
la caja el mismo día de la semana en la última semana del historial (del 26 de octubre al 1 de noviembre), con los
domingos de S4 a 0 y el mínimo de 6 en los artículos básicos. No hace ningún ajuste por roturas de stock, promociones ni
festivos.

| Previsión | WAPE medio | S1 | S2 | S3 | S4 | S5 | Calidad (línea base 0, referencia 1) |
|---|---|---|---|---|---|---|---|
| Línea base (mismo día de la semana anterior + mínimo) | 0.2790 | 0.3106 | 0.2026 | 0.3084 | 0.3325 | 0.2409 | 0 |
| Referencia | 0.1470 | 0.1346 | 0.1196 | 0.1604 | 0.1763 | 0.1442 | 1 |
| Oráculo (media real del generador, mínimo de 6) | 0.1381 | | | | | | 1.067 |

Lo que aporta cada parte de la referencia (la referencia con un solo cambio; calidad en la misma escala):

| Cambio en la referencia | WAPE medio | Calidad |
|---|---|---|
| Efectos de promoción y de festivo por categoría en lugar de agregados | 0.1418 | 1.039 |
| Sin mínimo de exposición (se incumple la regla flexible) | 0.1395 | 1.057 |
| Devoluciones restadas de las ventas del día | 0.1469 | 1.001 |
| Historial de I07 anterior a junio sin dividir por 6 | 0.1489 | 0.986 |
| Días con rotura de stock usados como ventas normales | 0.1523 | 0.960 |
| Festivo del 11 de noviembre desconocido (9.1% de la demanda del periodo) | 0.1566 | 0.927 |
| Plan de promociones ignorado | 0.1662 | 0.855 |

Con las semillas de mundo 1, 2 y 3, la referencia obtiene 0.1474 / 0.1592 / 0.1417 y la línea base 0.2534 / 0.2521 /
0.2533 (línea base ÷ referencia 1.72 / 1.58 / 1.79), y el oráculo alcanza una calidad de 1.118 / 1.167 / 1.072. El
mínimo se aplica de hecho en 136 celdas de la referencia, todas de albahaca (I03) y queso curado (I06), que juntas
suponen el 1.3% de la demanda del periodo.

## Notas

- Sintético. Todos los volúmenes, perfiles, elasticidades, efectos de festivos y tasas de rotura de stock son
  inventados; nada está calibrado con una cadena real. El calendario de festivos es genérico (véase REVIEW.md, F8).
- `validate-case` comprueba que los datos sean deterministas en las cinco versiones de idioma, que la referencia tenga
  calidad 1.0, que haya una línea base válida peor que la referencia y un entregable por regla que incumpla solo esa
  regla, y las semillas de mundo 1–3.
