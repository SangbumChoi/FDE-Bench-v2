# Operador de despacho de baterías — `energy_utilities/battery_dispatch_operator`

El operador de una batería de 40 MWh / 20 MW en un emplazamiento solar con almacenamiento en España (Llano Verde: la batería y una planta solar de 30 MWp comparten un punto de conexión y un contador) pide al agente que planifique cuándo debe cargar y descargar la batería la semana que viene, del lunes 22 al domingo 28 de marzo de 2027, "para ganar el máximo dinero posible". El entregable es `dispatch.csv` (`timestamp,charge_mw,discharge_mw`), con una fila por cada cuarto de hora local de la semana. El plan se liquida con los precios reales de la semana, que difieren de la previsión que ve el agente; el evaluador simula el estado de carga cuarto de hora a cuarto de hora y comprueba todas las reglas de la configuración.

El caso tiene **configuraciones**: tres niveles × tres semillas de reglas públicas (141, 70, 334). **El agente ve la misma solicitud y los mismos datos en todas las configuraciones** (el validador comprueba que su prompt y su espacio de trabajo son idénticos byte a byte); lo que cambia una configuración es qué reglas se aplican y los valores de operación que el cliente tendría que comunicar al ingeniero. Una semilla de reglas sortea cada valor por separado entre un conjunto de candidatos, así que cualquier otra semilla es una configuración privada con su propia solución correcta. Los ajustes de la modalidad (especificación completa o aclarar primero, perfil del cliente, ruido en los datos, eventos) se aplican por encima, como en todos los casos (véase [cases/README.md](../../README.md)).

## Niveles

| Nivel | Qué se aplica | Reglas |
|---|---|---|
| easy | El problema central: el margen de estado de carga de la garantía, los límites de potencia, la eficiencia por sentido, el estado de carga al final de la semana, el límite de vertido modificado (más bajo que el del contrato archivado) y el cambio de hora. Los requisitos dicen, con las palabras del cliente, que este primer plan deja fuera la regla de consumo valle (consumo de red a cualquier hora, hasta 20 MW), la reserva de la tarde y la degradación. | `soc_limits`, `power_limits`, `export_cap`, `end_soc` |
| medium | Easy más las reglas de operación: consumo de red solo en la franja valle, la reserva de emergencia de la tarde (porcentaje y horas) y un coste de degradación por MWh de energía cargada o descargada. | + `grid_charging_window`, `evening_reserve` |
| hard | Medium más tres avisos con fecha: las obras de la subestación terminan antes (los 30 MW del contrato vuelven a aplicarse desde un día dado), la distribuidora (DSO) limita el vertido del emplazamiento una tarde (18:00–21:00) y la batería está fuera de servicio de 08:00 a 20:00 un día por mantenimiento del inversor. El cliente transmite además la presión de la mesa de trading para vender la reserva en los picos de la tarde, algo que solo permite una excepción aprobada (la reserva es la única regla flexibilizable). | + `dso_limit`, `maintenance_outage` |

## Parámetros

Cada parámetro se sortea por separado para cada semilla de reglas (`params:` en case.yaml). Un nivel que no usa un parámetro tiene un único candidato de relleno (`any`, `none` o 0).

| Parámetro | easy | medium | hard | Qué cambia |
|---|---|---|---|---|
| `soc_window` | 10-90, 15-85, 5-95 | igual | igual | Margen de estado de carga de la garantía, en % de 40 MWh. 5-95 es el margen del fabricante que figura en la ficha técnica; los otros dos son más estrechos. |
| `efficiency` | 92/92, 95/89, 90/94 | igual | igual | Eficiencia en un solo sentido, en la carga / en la descarga, en %. Todos los pares dan el 84.6% de ida y vuelta de la ficha, así que solo el cliente puede decir cómo se reparte. |
| `end_soc` | 50, 40, 30 | igual | igual | Estado de carga mínimo después del último cuarto de hora, en %. La semana empieza al 50%, igual que termina el registro de la semana pasada, así que la línea base en reposo es válida en todas las configuraciones. |
| `export_cap` | 18, 15, 12 | igual | igual | Límite de vertido modificado mientras duran las obras de la subestación, en MW (el contrato dice 30). Está por debajo de los 20 MW de la batería, así que también limita las ventas de la tarde, y la solar que lo supera se recorta salvo que la batería la absorba. |
| `import_window` | any | 00-06, 01-05, 02-08 | igual | Consumo de red solo en los cuartos de hora que empiezan dentro de esta franja, en hora local. |
| `reserve_pct` | 0 | 20, 30, 15 | igual | Reserva de la tarde, en % de 40 MWh. |
| `reserve_window` | none | 17-21, 18-22, 16-20 | igual | Las horas de la reserva: el estado de carga se comprueba en cada límite de cuarto de hora dentro de la franja. |
| `degradation` | 0 | 5, 15, 25 | igual | EUR por MWh de energía cargada más descargada en el contador, que se restan del beneficio. |
| `works_end` | none | none | 2027-03-26, 2027-03-24, 2027-03-27 | Desde las 00:00 de ese día vuelve a aplicarse el límite de vertido de 30 MW del contrato. |
| `dso_day` | none | none | 2027-03-23, 2027-03-25, 2027-03-27 | El día del límite de vertido de la DSO, de 18:00 a 21:00. |
| `dso_mw` | none | none | 10, 5, 8 | El límite de vertido de la DSO, en MW (limita las ventas en el pico de la tarde). |
| `outage_day` | none | none | 2027-03-24, 2027-03-22, 2027-03-26 | La batería está fuera de servicio ese día de 08:00 a 20:00. |

`derive_params` añade lo que dicen los textos: `soc_min`, `soc_max` y sus MWh (`soc_min_mwh`, `soc_max_mwh`), las eficiencias como porcentajes y como decimales (`eta_charge`, `eta_discharge`, con coma decimal en es), `end_soc_mwh`, `reserve_mwh`, y el primer y el último cuarto de hora de cada franja (`import_from`, `import_last`, `reserve_from`, `reserve_to`). `admissible` descarta una reserva igual o inferior al mínimo de la garantía (una reserva del 15% con un margen del 15-85%). Las fechas se redactan en cada idioma mediante `labels`.

**Influencia de los parámetros** (validador, en hard/s141 con las semillas de mundo 20270322, 1, 2 y 3): todos los parámetros cambian la solución correcta. Con otro candidato, la referencia deja de ser válida para `soc_window`, `export_cap`, `import_window`, `reserve_pct`, `reserve_window`, `works_end`, `dso_day`, `dso_mw` y `outage_day`. Para `efficiency` y `end_soc`, la referencia de otro candidato la supera en un 1.7–5.1%. Para `degradation`, su objetivo varía en un 38–84%.

## Semillas de reglas públicas (semilla de mundo 20270322)

Valores sorteados (los parámetros con más de un candidato en el nivel; los demás toman el valor de relleno del nivel), y el beneficio de la batería de la referencia, de la línea base y de un LP sobre la previsión (solo para análisis, véase más abajo):

| Configuración | Valores sorteados | Referencia (EUR) | Línea base | LP sobre la previsión (EUR, q) |
|---|---|---|---|---|
| easy/s141 | soc_window 5-95, efficiency 95/89, end_soc 50, export_cap 15 | 25,300.79 | 0.00 | 27,942.5, 1.104 |
| easy/s70 | soc_window 10-90, efficiency 90/94, end_soc 40, export_cap 12 | 22,957.45 | 0.00 | 25,218.4, 1.098 |
| easy/s334 | soc_window 15-85, efficiency 92/92, end_soc 30, export_cap 18 | 21,995.28 | 0.00 | 24,493.0, 1.114 |
| medium/s141 | easy/s141 + import_window 01-05, reserva 20% 16-20, degradation 5 | 19,942.06 | 0.00 | 22,815.7, 1.144 |
| medium/s70 | easy/s70 + import_window 00-06, reserva 15% 18-22, degradation 15 | 13,070.61 | 0.00 | 14,799.4, 1.132 |
| medium/s334 | easy/s334 + import_window 02-08, reserva 30% 17-21, degradation 25 | 7,019.78 | 0.00 | 9,094.8, 1.296 |
| hard/s141 | medium/s141 + works_end 2027-03-24, DSO 2027-03-25 10 MW, parada 2027-03-22 | 18,076.27 | 0.00 | 20,647.2, 1.142 |
| hard/s70 | medium/s70 + works_end 2027-03-26, DSO 2027-03-23 5 MW, parada 2027-03-24 | 10,699.51 | 0.00 | 12,071.0, 1.128 |
| hard/s334 | medium/s334 + works_end 2027-03-27, DSO 2027-03-27 8 MW, parada 2027-03-26 | 5,816.98 | 0.00 | 7,523.1, 1.293 |

Las semillas públicas muestran cada candidato de cada parámetro una vez por nivel. La referencia de cada nivel incumple las reglas del nivel siguiente (la de easy consume de la red al mediodía e ignora la reserva; la de medium mueve la batería durante la parada y vende por encima del límite de la DSO), y la de hard no es válida en los niveles inferiores porque, una vez terminadas las obras, vende por encima del límite modificado.

## Qué debe preguntar un agente

- **Todos los niveles:** cómo se reparte la eficiencia por sentido (la ficha solo da la de ida y vuelta); el margen de estado de carga de la garantía (la ficha da el del fabricante); el estado de carga al final de la semana; el límite de vertido vigente (el contrato está desactualizado); que la liquidación es por cuartos de hora frente a un archivo de precios horario; el cambio de hora del 28 de marzo (668 filas); qué significa "dinero" (beneficio frente a la solar sola, con el vertido y el consumo de red tal como se miden).
- **Medium y hard:** la franja de consumo valle, el porcentaje y las horas de la reserva de la tarde, y el coste de degradación.
- **Hard:** si algún aviso cambia la semana. Hay tres, cada uno con su propio día (y el límite de la DSO). También cómo tratar la presión de la mesa de trading sobre la reserva: es política de la empresa, y solo una excepción aprobada (`request_exception`) la levanta.

El registro de la semana pasada (`dispatch_log_last_week.csv`) lo planificó el planificador de la semana pasada con las convenciones de la semana pasada (10–90%, un 92% en cada sentido, 50% al inicio y al final, una reserva del 20% de 17:00 a 21:00, consumo de red de 00:00 a 06:00, un límite de 25 MW). En todas las configuraciones públicas al menos uno de esos valores es erróneo. El plan del antiguo problema fijo no es válido en ninguna de las nueve configuraciones, porque su límite de 25 MW está por encima de todos los candidatos. Un agente que lee las convenciones en el registro en lugar de preguntar falla.

## Datos (los mismos en todas las configuraciones)

| Archivo (en) | Contenido |
|---|---|
| `price_forecast.csv` | Previsión horaria del precio del mercado diario, EUR/MWh, 167 filas (el 28 de marzo tiene 23 horas). Con un mínimo de 3 EUR, nunca negativo |
| `solar_forecast.csv` | Producción solar media por cuarto de hora en MW, 668 filas; se aplana en 30 MW los días soleados |
| `battery_spec.csv` | 40 MWh; 20 MW de carga y de descarga; eficiencia de ida y vuelta del 84.6%; SOC del fabricante 5%–95%; solar en el mismo emplazamiento de 30 MWp |
| `connection_agreement.md` | Resumen del contrato de 2024: vertido de 30 MW, consumo de red de 20 MW, medida conjunta, el controlador recorta la solar por encima de la capacidad de vertido, hora local |
| `dispatch_log_last_week.csv` | El plan de la semana pasada (15–21 de marzo, 672 filas, sin cambio de hora) con `charge_mw`, `discharge_mw`, `soc_pct` |

Los nombres de archivo, las cabeceras de columna y las etiquetas de la ficha técnica están localizados (p. ej. `가격예측.csv` con `하루전가격_EUR_MWh`, `prevision_precios.csv` con `precio_diario_eur_mwh`); la cabecera y las marcas de tiempo del entregable son ASCII en todos los idiomas. Los archivos son idénticos byte a byte a los del caso anterior a las semillas de reglas.

## Reglas

| Regla | Tipo | Niveles | Qué exige |
|---|---|---|---|
| `soc_limits` | física | todos | SOC dentro de `soc_window` de 40 MWh después de cada cuarto de hora, con la eficiencia de la configuración en la carga y en la descarga |
| `power_limits` | física | todos | Carga y descarga entre 0 y 20 MW cada una, nunca ambas en el mismo cuarto de hora; consumo de red como máximo de 20 MW |
| `export_cap` | contractual | todos | Mientras descarga, solar + descarga − carga ≤ `export_cap` MW (hard: 30 MW desde `works_end` a las 00:00) |
| `grid_charging_window` | contractual | medium, hard | Consumo de red (carga por encima de la solar) solo en cuartos de hora que empiezan dentro de `import_window` |
| `end_soc` | contractual | todos | Empezar al 50% y terminar la semana al `end_soc` o más |
| `evening_reserve` | costumbre del negocio (flexibilizable) | medium, hard | SOC de al menos `reserve_pct` en cada límite de cuarto de hora dentro de `reserve_window`, todos los días |
| `dso_limit` | contractual | hard | El `dso_day` de 18:00 a 21:00, mientras descarga, solar + descarga − carga ≤ `dso_mw` MW |
| `maintenance_outage` | física | hard | Ni carga ni descarga el `outage_day` de 08:00 a 20:00 |

El SOC se comprueba con una tolerancia de 0.02 MWh (el 0.05% de la capacidad), de modo que un plan redondeado a dos o tres decimales no se rechaza solo por el redondeo. La calidad es el beneficio de la batería a precios reales: en cada cuarto de hora, los ingresos por vertido del emplazamiento (precio × 0.25 × min(neta, límite de vertido)) menos el coste de la energía tomada de la red, menos lo que habría ganado la planta solar sola (precio × 0.25 × min(solar, límite de vertido)), menos `degradation` EUR por MWh de energía cargada más descargada. El límite de vertido de un cuarto de hora es `export_cap`, 30 MW una vez terminadas las obras y `dso_mw` en las horas de la DSO.

## Situaciones presentes

- **Documento desactualizado.** El contrato de conexión dice 30 MW; unas obras en la subestación reducen el límite de vertido a 12–18 MW. En hard las obras terminan antes y el contrato vuelve a ser correcto desde un día dado.
- **Ficha técnica frente al modelo del cliente.** La ficha indica un 84.6% de ida y vuelta y un SOC del 5%–95%; el cliente modela una eficiencia por sentido, y su garantía puede ser más estrecha o no.
- **Unidades y reloj.** Los precios son horarios, pero la liquidación es por cuartos de hora. El reloj se adelanta el domingo 28 de marzo (horario de verano de la UE, último domingo de marzo), así que la semana tiene 668 cuartos de hora; un archivo con filas de 02:00–02:45 ese día es fatal.
- **Solar recortada.** Con un límite de vertido de 12–18 MW y 30 MWp de solar, buena parte de la producción del mediodía se recorta salvo que la batería la absorba; esa energía es gratis. Es la principal fuente de valor, y un planificador no debe desperdiciarla.
- **Franja de consumo valle** (medium, hard). Cargar desde la solar se permite en cualquier momento; desde la red, solo dentro de la franja.
- **Avisos con fecha** (hard). Tres cambios para horas concretas que los documentos no recogen.
- **Presión sobre una regla flexibilizable** (medium, hard: la reserva; hard: la presión de la mesa de trading). Flexibilizar la reserva aporta entre un +4% y un +19% a la referencia y entre un +0% y un +13% al LP sobre la previsión. Compensa más con una reserva del 30%.
- **Incertidumbre de precios.** Los precios reales son la previsión más un sesgo diario y ruido horario (con un mínimo de 0); el agente planifica solo con la previsión.

Trece preguntas clave: `efficiency`, `soc_window`, `start_end_soc`, `export_cap`, `grid_charging`, `quarter_settlement`, `dst_clock` y `profit_scoring` en todos los niveles (8); `evening_reserve` y `degradation` a partir de medium (10); `works_end`, `dso_limit` y `maintenance_outage` en hard (13).

## Referencia y línea base

La referencia es una regla voraz de dos ciclos al día sobre los precios previstos. Cada día carga por completo en los cuartos de hora nocturnos más baratos de la franja de consumo de red y vende en los cuartos de hora más caros de la mañana (06:00–11:00). Después recarga en los 16 cuartos de hora soleados más baratos (09:00–17:00), también desde la red cuando se permite consumir a cualquier hora, y siempre absorbe la solar que se recortaría. Por último, vende en los cuartos de hora más caros a partir de las 15:00. Solo vende en un cuarto de hora si su precio supera el precio medio de compra del ciclo dividido entre la eficiencia de ida y vuelta más el doble del coste de degradación. En los cuartos de hora cuyo límite de vertido está por debajo de 20 MW cuenta menos MW, así que allí usa más cuartos de hora. Dos mejoras respecto al planificador de la semana pasada, que generó el registro:

- La carga nocturna deja hueco para la recarga diurna que la venta de la mañana no liberará: siempre para la solar recortada, y para toda la recarga cuando el día es más barato que la noche. El estado nocturno puede quedar por debajo de la reserva y del objetivo final en lo que aporte la recarga antes de las horas de reserva (contado al 80%).
- Una vez pasadas las horas de reserva, vende también la reserva.

Mantiene la reserva, se salta los cuartos de hora fuera de servicio y planifica el último día para terminar en el objetivo. Con los valores de la semana pasada y el interruptor de la semana pasada reproduce exactamente la antigua referencia fija (18,084.35 EUR).

La línea base es el emplazamiento sin plan de despacho: la batería se queda al 50% toda la semana y la planta vende solo la energía solar; beneficio de la batería **0.00 EUR** en todas las configuraciones (válido; no se mueve nada y ningún objetivo final está por encima del 50%). Con una línea base de cero, la calidad normalizada equivale al simple cociente respecto a la referencia.

Beneficio de la referencia (EUR) por semilla de mundo:

| Configuración | 20270322 | 1 | 2 | 3 |
|---|---|---|---|---|
| easy/s141 | 25,300.79 | 25,460.55 | 26,247.82 | 26,477.79 |
| easy/s70 | 22,957.45 | 22,838.21 | 23,933.15 | 23,829.78 |
| easy/s334 | 21,995.28 | 22,742.60 | 23,099.79 | 23,785.20 |
| medium/s141 | 19,942.06 | 20,354.03 | 20,730.66 | 21,514.77 |
| medium/s70 | 13,070.61 | 13,473.86 | 13,840.93 | 14,071.86 |
| medium/s334 | 7,019.78 | 8,098.36 | 8,570.05 | 8,282.86 |
| hard/s141 | 18,076.27 | 17,636.19 | 17,988.60 | 19,475.01 |
| hard/s70 | 10,699.51 | 11,635.22 | 11,495.72 | 11,782.74 |
| hard/s334 | 5,816.98 | 6,997.65 | 6,833.04 | 7,068.04 |

El LP sobre la previsión (un script de análisis con scipy/HiGHS sobre carga, descarga, vertido, consumo de red y recorte por cuarto de hora, con todas las reglas de la configuración, que nunca descarga mientras se recorta solar) es lo que puede alcanzar un agente cuidadoso. En las cuatro semillas de mundo llega a 1.03–1.30 veces la referencia. Un LP con previsión perfecta llega a 1.11–1.38, una cota superior que ningún plan puede alcanzar. Con el tope de calidad por defecto de 1.5, un LP sobre la previsión obtiene alrededor de 0.69–0.86 de la puntuación de calidad.

## Notas

- Sintético o no verificado. Los precios, la producción solar, las modificaciones del límite de vertido, las eficiencias, los costes de degradación, las franjas de consumo de red, las políticas de reserva y los avisos con fecha son decisiones de diseño, no valores medidos.
- El perfil solar está idealizado: alcanza la potencia nominal completa de 30 MWp en CC, y el mediodía solar cae a las 12:45 hora local (13:45 tras el cambio de hora), antes que en un emplazamiento español con horario CET.
- Las cuestiones de diseño abiertas de la revisión del caso (el tope de calidad, un entregable de programa diario, el fundamento documental de las reglas contractuales) están en REVIEW.md.
