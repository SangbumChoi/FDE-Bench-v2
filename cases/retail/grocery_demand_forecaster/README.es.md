# Analista de previsión de demanda en supermercados — `retail/grocery_demand_forecaster`

Una cadena regional de supermercados con cinco tiendas pide al agente que prevea "cuánto va a vender cada una de
nuestras cinco tiendas de cada producto, día a día, durante las próximas dos semanas a partir del lunes 2 de
noviembre", porque hace sus pedidos con esas cifras. El entregable es `forecast.csv`
(`store_id,item_id,date,forecast`): una fila por cada tienda (S1–S5) × artículo (I01–I12) × día del 2026-11-02 al
2026-11-15, 840 filas, en la unidad de venta actual de cada artículo. La previsión se puntúa frente a los valores
reales del periodo de la previsión, que solo existen en el mundo.

El caso tiene **configuraciones**: tres niveles × semillas de reglas (DESIGN.md, Settings). Los datos y la solicitud
son los mismos en todas las configuraciones; solo cambian las reglas ocultas del cliente, aquello con lo que se evalúa
la previsión y, por tanto, la previsión correcta. Los ajustes de la modalidad (especificación completa frente a
aclarar primero, perfil del cliente, ruido en los datos, eventos) se aplican por encima, como en todos los casos
(véase [cases/README.md](../../README.md)).

## Niveles

| Nivel | Qué debe hacer la previsión | Fuera de alcance (lo dice el propio cliente) |
|---|---|---|
| **easy** | La previsión base: un día normal por tienda × artículo, evaluada con las **ventas base de caja** (devoluciones restadas, días con rotura de stock tal como se registraron, sin efecto de promociones ni de festivos). Se aplican el cierre dominical de S4, el mínimo de exposición y el peso del error | Las promociones y el festivo único ("lo añade nuestro equipo de categorías … así que deje fuera las dos cosas"); la corrección de las roturas de stock ("queda para una ronda posterior"); los panecillos I07 ("no se evalúan en esta ronda … aun así, mantenga sus filas en el archivo") |
| **medium** | Easy + el plan de promociones (fechas incluidas, el aumento por categoría y descuento aprendido de las promociones pasadas, multiplicado por el factor del folleto cuando se sortea uno) y el festivo regional único en su fecha sorteada; se sigue evaluando con las **ventas de caja** con las devoluciones restadas | La corrección de las roturas de stock e I07, como en easy |
| **hard** | Medium evaluado con la **demanda de los clientes**: los días con rotura de stock están censurados, las devoluciones no son demanda, I07 se evalúa (su cambio de unidad: por unidad hasta el 31 de mayo de 2026, en paquetes de 6 desde entonces) y hay una revisión fechada: el viernes 30 de octubre, después de exportar `promo_plan.csv`, se cancelaron las promociones de la categoría sorteada | — |

Los niveles cambian la verdad, no solo las reglas: el mundo sortea una realización por celda (ruido diario, un cuantil
de Poisson, los sorteos de rotura de stock y de devolución) y cada configuración la evalúa con su propia media (con o
sin las promociones, el folleto, la cancelación y el festivo) y como ventas de caja o como demanda, de modo que todas
las configuraciones comparten la misma suerte.

## Parámetros (lo que sortea una semilla de reglas)

Cada parámetro se sortea por separado de su conjunto de candidatos en el nivel de la configuración (`case.yaml`
`params:`).

| Parámetro | easy | medium | hard | Qué cambia |
|---|---|---|---|---|
| `min_display` | 6, 4, 8 | igual | igual | El mínimo de exposición de los artículos básicos (fruta y verdura y lácteos, I01–I06) en los días de apertura: la regla flexibilizable `min_display_stock`. Se aplica de hecho en la albahaca (I03) y el queso curado (I06), 136 celdas con 6 u 8 |
| `holiday_date` | none (ninguno) | 2026-11-11, 2026-11-13, 2026-11-09 | igual | El día del festivo regional único (miércoles 11 / viernes 13 / lunes 9 de noviembre), que no está en `holidays.csv`; ese día la demanda sube según el efecto festivo de la categoría |
| `promo_uplift` | 1 | 1, 1.5, 2 | igual | El folleto impreso: una promoción de noviembre trae este múltiplo de las ventas adicionales de una promoción pasada (1 = sin folleto, solo etiquetas en el lineal como antes) |
| `promo_cancelled` | none (ninguna) | none (ninguna) | beverages (bebidas), dairy (lácteos), bakery (panadería) | La categoría cuyas promociones canceló el proveedor el 30 de octubre, después de exportar el plan |
| `short_weight` | 1, 2, 3 | igual | igual | En el WAPE de la tienda, una unidad prevista de menos cuenta este número de veces una unidad prevista de más (1 = WAPE simple). Desplaza la mejor previsión de la mediana al cuantil 2/3 o 3/4 |

El resto es fijo: el periodo de 14 días, el cierre dominical de S4, las categorías básicas, el cambio de unidad de I07
el 1 de junio de 2026 y que I07 se evalúe solo en hard. `case.py` no deriva nada y no necesita `admissible()`:
cualquier combinación es una semana razonable.

## Semillas de reglas públicas (3, 25, 58) con la semilla del caso 20261102

Todos los candidatos de todos los conjuntos aparecen en las semillas públicas. La semilla 3 va primero: sortea la
configuración de la comprobación de influencia de los parámetros (hard/s3: sin folleto, WAPE simple, mínimo 6), en la
que el primer candidato alternativo de cada parámetro ya invalida la referencia, mueve su objetivo o hace que la
propia referencia de esa configuración la supere en al menos un 3%.

| Configuración | Parámetros sorteados | Referencia | Línea base | Línea base / referencia |
|---|---|---|---|---|
| easy/s3 | mínimo 6, peso 1 | 0.1750 | 0.2873 | 1.64 |
| easy/s25 | mínimo 8, peso 2 | 0.2374 | 0.4090 | 1.72 |
| easy/s58 | mínimo 4, peso 3 | 0.2548 | 0.5040 | 1.98 |
| medium/s3 | mínimo 6, festivo lun. 9 nov., sin folleto, peso 1 | 0.1778 | 0.2939 | 1.65 |
| medium/s25 | mínimo 8, festivo mié. 11 nov., folleto 1.5, peso 2 | 0.2442 | 0.4701 | 1.93 |
| medium/s58 | mínimo 4, festivo vie. 13 nov., folleto 2, peso 3 | 0.2678 | 0.6609 | 2.47 |
| hard/s3 | mínimo 6, festivo lun. 9 nov., sin folleto, panadería cancelada, peso 1 | 0.1407 | 0.2747 | 1.95 |
| hard/s25 | mínimo 8, festivo mié. 11 nov., folleto 1.5, bebidas canceladas, peso 2 | 0.1962 | 0.4329 | 2.21 |
| hard/s58 | mínimo 4, festivo vie. 13 nov., folleto 2, lácteos cancelados, peso 3 | 0.2108 | 0.6753 | 3.20 |

El objetivo es la media sobre las cinco tiendas del WAPE ponderado (cuanto más bajo, mejor). Los diccionarios tal como
se guardan en `dataset/gt/<tier>_s<seed>/setting.json`:

```
easy/s3    {min_display: 6, holiday_date: none,         promo_uplift: 1,   promo_cancelled: none,      short_weight: 1}
easy/s25   {min_display: 8, holiday_date: none,         promo_uplift: 1,   promo_cancelled: none,      short_weight: 2}
easy/s58   {min_display: 4, holiday_date: none,         promo_uplift: 1,   promo_cancelled: none,      short_weight: 3}
medium/s3  {min_display: 6, holiday_date: "2026-11-09", promo_uplift: 1,   promo_cancelled: none,      short_weight: 1}
medium/s25 {min_display: 8, holiday_date: "2026-11-11", promo_uplift: 1.5, promo_cancelled: none,      short_weight: 2}
medium/s58 {min_display: 4, holiday_date: "2026-11-13", promo_uplift: 2,   promo_cancelled: none,      short_weight: 3}
hard/s3    {min_display: 6, holiday_date: "2026-11-09", promo_uplift: 1,   promo_cancelled: bakery,    short_weight: 1}
hard/s25   {min_display: 8, holiday_date: "2026-11-11", promo_uplift: 1.5, promo_cancelled: beverages, short_weight: 2}
hard/s58   {min_display: 4, holiday_date: "2026-11-13", promo_uplift: 2,   promo_cancelled: dairy,     short_weight: 3}
```

Todos los parámetros influyen (validador, desde hard/s3, con la semilla del caso y las semillas de mundo 1–3; sondeado
con las semillas de mundo 1–20, donde la alternativa más fuerte de cada parámetro invalida la referencia, o la mueve o
la supera en al menos un 5%):
- `min_display`: la referencia de hard/s3 (mínimo 6) es inválida con 8; con 4, la referencia de esa configuración es
  un 4.9% mejor.
- `holiday_date`: el objetivo de la referencia de hard/s3 se mueve un +28.4% con el miércoles 11 de noviembre y un
  +32.9% con el viernes 13 de noviembre.
- `promo_uplift`: +3.4% con un folleto de 1.5, +11.0% con 2.
- `promo_cancelled`: +17.0% cuando se cancelan las bebidas en lugar de la panadería, +5.7% con los lácteos.
- `short_weight`: +45.3% con peso 2, +90.6% con 3 (y allí la propia referencia de la configuración ponderada es un
  8.4% y un 18.4% mejor).

Con las semillas de mundo 1, 2 y 3, el cociente línea base ÷ referencia es 1.34–1.76 (easy), 1.45–2.25 (medium) y
1.68–2.96 (hard).

## Qué debe preguntar el agente

Las preguntas clave, por nivel (`locales/<lang>/targets.yaml`):

- **Todos los niveles:** el cierre dominical de S4 (`s4_sunday_closed`), el mínimo de exposición y su valor
  (`min_display`), la métrica con su peso del error y qué es lo real (`wape_metric`: ventas de caja con las
  devoluciones restadas en easy y medium, demanda en hard), el formato del archivo (`submission_format`).
- **easy:** que solo se quiere la previsión base, sin las promociones ni el festivo (`base_forecast`).
- **medium y hard:** el plan de promociones (`promo_plan`), el factor del folleto o que no hay folleto
  (`promo_flyer`), el festivo único y su fecha (`one_off_holiday`).
- **hard:** la censura por roturas de stock (`stockout_censoring`), las devoluciones fuera (`returns`), la cancelación
  del 30 de octubre y su categoría (`promo_revision`), el cambio de unidad de I07 (`unit_change_i07`).

Es decir, 5 preguntas clave en easy, 7 en medium y 11 en hard.

## Datos

- `sales_history` (43,718 filas, del 2024-11-04 al 2026-11-01, 104 semanas): una fila de ventas por tienda, artículo y
  día de apertura con `units_sold`, `promo_discount_pct` (0 = sin promoción) y un indicador `stockout` (4,390 filas
  con rotura de stock, en las que las ventas registradas son el 30–85% de la demanda), más 1,286 filas aparte de
  devoluciones de clientes con unidades negativas (−2,104 unidades frente a 2,002,817 vendidas). S4 no tiene filas en
  domingo.
- `promo_plan`: 14 promociones de tienda × artículo en el periodo de la previsión (10/20/30% de descuento, con las
  fechas de inicio y fin incluidas); con la semilla del caso, 7 promociones de bebidas, 3 de panadería, 2 de lácteos y
  2 de fruta y verdura. Con cualquier semilla de mundo, el plan tiene al menos una promoción en cada categoría que
  puede sortear la cancelación del 30 de octubre (bebidas, lácteos, panadería).
- `holidays`: 12 festivos pasados (Navidad, Año Nuevo, un festivo de primavera, uno de verano y uno de otoño, y el Día
  del Trabajo, cada uno dos veces). Ninguno cae en el periodo de la previsión, y el festivo único (en la fecha
  sorteada) no figura en la lista.
- `stores` (cuatro supermercados y la tienda exprés Casco Antiguo, S4) e `items` (12 artículos en cuatro categorías:
  fruta y verdura I01–I03, lácteos I04–I06, panadería I07–I09, bebidas I10–I12, con su unidad de venta). Los
  panecillos (I07) figuran en paquetes de 6; el historial los registra por unidad hasta el 31 de mayo de 2026.

La conversión no cambia los datos (idénticos byte a byte a los del caso sin configuraciones). El mundo es un modelo
multiplicativo por tienda × artículo × día (escala y tendencia de la tienda, perfil semanal y estacionalidad anual por
categoría, efecto de las promociones según la categoría y el descuento, efecto de los festivos por categoría) con
ruido diario lognormal (σ = 0.07) y ventas de Poisson. Las roturas de stock se producen con la probabilidad base del
artículo, más 0.20 los días de promoción, con independencia de la demanda del día. En el periodo de la previsión, el
folleto multiplica la demanda adicional de una promoción; las ventas de caja son la demanda recortada al 30–85% en un
día con rotura de stock (con las mismas probabilidades), menos una devolución de 1–2 unidades en el 3% de las celdas.

## Reglas

| Regla | Tipo | Niveles | Qué exige |
|---|---|---|---|
| `complete_grid` | contractual | todos | exactamente una fila por tienda × artículo × fecha del periodo (también I07, incluso donde no se evalúa) |
| `non_negative` | física | todos | ninguna previsión negativa |
| `closed_day_zero` | física | todos | S4 cierra los domingos: su previsión para los domingos es 0 |
| `min_display_stock` | costumbre del negocio (flexibilizable) | todos | los artículos básicos (fruta y verdura y lácteos, I01–I06) se prevén en `min_display` o más todos los días de apertura |

**Calidad (cuanto más baja, mejor):** por tienda, Σ (`short_weight` × (real − previsión) donde la previsión queda por
debajo, previsión − real donde queda por encima) ÷ Σ real sobre sus artículos y días evaluados, promediado sobre las
cinco tiendas. Lo real son las ventas base de caja (easy), las ventas de caja con las devoluciones restadas (medium) o
la demanda de los clientes (hard); I07 solo se evalúa en hard.

## Situaciones presentes

- **Hechos ocultos:** el alcance limitado a la previsión base (easy), qué es lo real (ventas de caja o demanda), las
  devoluciones, el cierre dominical de S4, el plan de promociones y el folleto, el festivo único y su fecha, el cambio
  de unidad de I07, el mínimo de exposición y el peso del error.
- **Un evento con fecha (hard):** la cancelación del 30 de octubre, posterior a la exportación de `promo_plan.csv`,
  así que el archivo que tiene el agente está desactualizado para una categoría.
- No hay mensaje de presión; los únicos eventos adicionales los aporta el eje de modalidad (REVIEW.md, F7).

## Referencia y línea base

La **referencia** es un modelo de nivel y perfil semanal por tienda × artículo construido solo con el historial: un
perfil por día de la semana a partir de las últimas 52 semanas de días utilizables sin promoción ni festivo, un nivel
a partir de las últimas 8 semanas de esos días, un factor estacional por categoría a partir del nivel del año pasado
en torno al periodo de la previsión, un efecto de promoción por categoría y descuento y un efecto de festivo por
categoría, ambos frente al nivel local, y el historial de I07 anterior al 1 de junio de 2026 dividido por 6. Después,
la configuración: las promociones que este nivel prevé (efecto × factor del folleto sobre la parte adicional, ninguna
para la categoría cancelada), el efecto festivo en el día sorteado y el cuantil `short_weight / (1 + short_weight)`
del cociente entre el valor real y el ajustado de la tienda × artículo en las últimas 26 semanas (la mediana con peso
1); los domingos de S4 a 0 y el mínimo en los artículos básicos. En easy y medium ajusta las ventas de caja tal como
se registraron (con los días de rotura de stock, con las devoluciones restadas, como describe el cliente lo real); en
hard ajusta la demanda (sin los días de rotura de stock ni las filas de devolución).

La **línea base** es la previsión ingenua estacional que usaría un encargado de tienda sin un ingeniero, la misma en
todas las configuraciones: lo que registró la caja el mismo día de la semana en la última semana del historial (del 26
de octubre al 1 de noviembre), con los domingos de S4 a 0 y el mínimo sorteado en los artículos básicos. No hace
ningún ajuste por roturas de stock, promociones, festivos ni peso.

Lo que aporta cada parte con la semilla del caso (la referencia con un solo cambio; calidad en la escala línea base 0
/ referencia 1):

| Cambio en la referencia | easy/s25 | medium/s25 | hard/s3 | hard/s25 | hard/s58 |
|---|---|---|---|---|---|
| Oráculo: el cuantil de la distribución real del resultado en cada celda, con el mínimo | 1.053 | 1.062 | 1.030 | 1.019 | 1.014 |
| Ajustada al otro objetivo (demanda en easy/medium, ventas de caja en hard) | 1.040 | 1.046 | 0.932 | 0.933 | 0.942 |
| Peso del error ignorado (la mediana) | 0.861 | 0.888 | — | 0.926 | 0.894 |
| Promociones y festivo del 11 de noviembre añadidos (easy) / promociones ignoradas | 0.714 | 0.767 | 0.846 | 0.847 | 0.688 |
| Festivo ignorado | — | 0.874 | 0.854 | 0.854 | 0.845 |
| Folleto ignorado | — | 0.948 | — | 0.965 | 0.905 |
| Cancelación ignorada | — | — | 0.975 | 0.856 | 0.976 |
| Historial de I07 sin dividir por 6 | — | — | 0.999 | 0.996 | 0.997 |
| Devoluciones restadas de las ventas del día | — | — | 0.999 | 0.999 | 1.000 |
| Sin mínimo de exposición (se incumple la regla flexibilizable) | 1.114 | 1.077 | 1.067 | 1.065 | 1.001 |

Así que la censura por roturas de stock solo pesa en hard: en easy y medium, como lo real del cliente son ventas de
caja, no hace falta ajustar la demanda, aunque ajustarla sigue superando al ajuste de las ventas de caja en un 3–5%
(los días censurados solo añaden ruido a un nivel de ventas de caja, y la mediana de una venta de caja está cerca de
la de la demanda). Flexibilizar el mínimo aporta un 7–11% con un mínimo de 6 u 8 y nada con 4 bajo peso 3, donde la
previsión por cuantil ya lo supera.

## Notas

- Sintético. Todos los volúmenes, perfiles, elasticidades, efectos de festivos y tasas de rotura de stock son
  inventados; nada está calibrado con una cadena real. El calendario de festivos es genérico (véase REVIEW.md, F8).
- `validate-case` comprueba que los datos sean deterministas en los cinco idiomas, que la referencia tenga calidad 1.0
  en todas las configuraciones públicas, que haya una línea base válida peor que la referencia y un entregable por
  regla que incumpla solo esa regla, que todos los parámetros influyan, y las semillas de mundo 1–3.
