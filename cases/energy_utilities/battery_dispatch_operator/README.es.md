# Operador de despacho de baterías — `energy_utilities/battery_dispatch_operator`

El operador de una batería de 40 MWh / 20 MW en un emplazamiento solar con almacenamiento en España (Llano Verde: la batería y una planta solar de 30 MWp comparten un punto de conexión y un contador) pide al agente que planifique cuándo debe cargar y descargar la batería la semana que viene, del lunes 22 al domingo 28 de marzo de 2027, "para ganar el máximo dinero posible". El entregable es `dispatch.csv` (`timestamp,charge_mw,discharge_mw`), con una fila por cada cuarto de hora local de la semana. El plan se liquida con los precios reales de la semana, que difieren de la previsión que ve el agente; el evaluador simula el estado de carga cuarto de hora a cuarto de hora y comprueba todas las reglas.

El caso **no tiene configuraciones**: una sola solución correcta, el mismo problema en todas las dificultades. Los ajustes de la modalidad (especificación completa o aclarar primero, perfil del cliente, ruido en los datos, eventos) se aplican por encima, como en todos los casos (véase [cases/README.md](../../README.md)).

## Datos

| Archivo (en) | Contenido |
|---|---|
| `price_forecast.csv` | Previsión horaria del precio del mercado diario, EUR/MWh, 167 filas (el 28 de marzo tiene 23 horas). Con un mínimo de 3 EUR, nunca negativo |
| `solar_forecast.csv` | Producción solar media por cuarto de hora en MW, 668 filas; se aplana en 30 MW los días soleados, con 67 cuartos de hora por encima de 25 MW |
| `battery_spec.csv` | 40 MWh; 20 MW de carga y de descarga; eficiencia de ida y vuelta del 84.6%; SOC del fabricante 5%–95%; solar en el mismo emplazamiento de 30 MWp |
| `connection_agreement.md` | Resumen del contrato de 2024: vertido de 30 MW, consumo de red de 20 MW, medida conjunta, el controlador recorta la solar por encima de la capacidad de vertido, hora local |
| `dispatch_log_last_week.csv` | El plan de la semana pasada (15–21 de marzo, 672 filas, sin cambio de hora) con `charge_mw`, `discharge_mw`, `soc_pct` |

Los nombres de archivo, las cabeceras de columna y las etiquetas de la ficha técnica están localizados (p. ej. `가격예측.csv` con `하루전가격_EUR_MWh`, `prevision_precios.csv` con `precio_diario_eur_mwh`); la cabecera y las marcas de tiempo del entregable son ASCII en todos los idiomas.

## Reglas

| Regla | Tipo | Qué exige |
|---|---|---|
| `soc_limits` | física | SOC entre el 10% y el 90% de 40 MWh después de cada cuarto de hora, con un 92% de eficiencia en la carga y en la descarga |
| `power_limits` | física | Carga y descarga entre 0 y 20 MW cada una, nunca ambas en el mismo cuarto de hora; consumo de red como máximo de 20 MW |
| `export_cap` | contractual | Mientras descarga, solar + descarga − carga ≤ 25 MW (límite modificado; el contrato archivado dice 30) |
| `grid_charging_window` | contractual | Consumo de red (carga por encima de la solar) solo en cuartos de hora que empiezan entre las 00:00 y las 05:45 hora local |
| `end_soc` | contractual | Empezar al 50% y terminar la semana al 50% o más |
| `reserve_20pct` | costumbre del negocio (flexibilizable) | SOC de al menos el 20% en cada límite de cuarto de hora de 17:00 a 21:00, todos los días |

El SOC se comprueba con una tolerancia de 0.02 MWh (el 0.05% de la capacidad), de modo que un plan redondeado a dos o tres decimales no se rechaza solo por el redondeo. La calidad es el beneficio de la batería a precios reales: en cada cuarto de hora, los ingresos por vertido del emplazamiento (precio × 0.25 × min(neta, 25)) menos el coste de la energía tomada de la red, menos lo que habría ganado la planta solar sola (precio × 0.25 × min(solar, 25)), menos 5 EUR por MWh de energía cargada más descargada.

## Situaciones presentes

- **Documento desactualizado.** El contrato de conexión dice 30 MW; unas obras en la subestación reducen el límite de vertido a 25 MW del 1 de marzo al 30 de junio de 2027. Un plan hecho con 30 MW no es válido (`export_cap`).
- **Ficha técnica frente al modelo del cliente.** La ficha indica un 84.6% de ida y vuelta y un SOC del 5%–95%; el cliente modela un 92% en cada sentido y su garantía permite el 10%–90%.
- **Unidades y reloj.** Los precios son horarios, pero la liquidación es por cuartos de hora. El reloj se adelanta el domingo 28 de marzo (horario de verano de la UE, último domingo de marzo), así que la semana tiene 668 cuartos de hora; un archivo con filas de 02:00–02:45 ese día es fatal.
- **Franja de consumo valle.** Cargar desde la solar se permite en cualquier momento; desde la red, solo de 00:00 a 05:45.
- **Solar recortada.** Cuando la batería no descarga, la solar por encima de 25 MW se recorta salvo que la batería la absorba.
- **Regla flexibilizable.** La reserva de la tarde es una política de la empresa. Relajarla aporta un +9.1% a la heurística de referencia (19,733.9 frente a 18,084.35 EUR) y un +3.8% a un LP sobre la previsión (22,156.6 frente a 21,343.2 EUR).
- **Incertidumbre de precios.** Los precios reales son la previsión más un sesgo diario y ruido horario (con un mínimo de 0); el agente planifica solo con la previsión.

Nueve preguntas clave: eficiencia, rango de SOC, SOC inicial y final, límite de vertido, franja de carga desde la red, liquidación por cuartos de hora, cambio de hora, reserva de la tarde y definición del beneficio.

## Cifras de la referencia y de la línea base (semilla 20270322)

La referencia es una regla voraz de dos ciclos al día sobre los precios previstos: cada día carga por completo en los cuartos de hora nocturnos más baratos de la franja de consumo de red y vende en los cuartos de hora más caros de la mañana (06:00–11:00); después recarga desde la solar en los 16 cuartos de hora soleados más baratos (09:00–17:00), absorbiendo siempre la solar que se recortaría, y vende en los cuartos de hora más caros a partir de las 15:00; solo vende en un cuarto de hora si su precio supera el precio medio de compra dividido entre 0.92² más el doble del coste de degradación. Mantiene la reserva del 20% hasta las 21:00 y planifica el último día para terminar al 50%. Obtiene **18,084.35 EUR** a precios reales (19,225.3 a precios previstos): ingresos por vertido 58,211.90, coste del consumo de red 7,227.53, ingresos de la solar sola 29,237.22, degradación 3,662.80 (732.56 MWh de energía cargada y descargada), 36.49 MWh recortados, SOC entre el 20% y el 90%, y termina al 50%.

La línea base es el emplazamiento sin plan de despacho: la batería se queda al 50% toda la semana y la planta vende solo la energía solar; beneficio de la batería **0.00 EUR** (válido; no se mueve nada, así que ninguna regla puede incumplirse). Con una línea base de cero, la calidad normalizada equivale al simple cociente respecto a la referencia.

| Semilla de mundo | Referencia (EUR) | Línea base (EUR) | LP sobre la previsión (EUR, q) | LP con previsión perfecta (EUR, q) | Referencia sin la reserva (EUR) |
|---|---|---|---|---|---|
| 20270322 | 18,084.35 | 0.00 | 21,343.2, 1.180 | 23,099.9, 1.277 | 19,733.9 |
| 1 | 18,742.76 | 0.00 | 21,733.8, 1.160 | 23,388.3, 1.248 | 20,269.6 |
| 2 | 19,265.16 | 0.00 | 21,638.5, 1.123 | 23,351.8, 1.212 | 20,545.2 |
| 3 | 20,542.92 | 0.00 | 22,873.4, 1.113 | 23,932.5, 1.165 | 22,332.2 |

Los LP son un script de análisis (scipy/HiGHS sobre carga, descarga y vertido por cuarto de hora, con todas las reglas) y no forman parte del caso. El LP sobre la previsión es lo que puede alcanzar un agente cuidadoso; el LP con previsión perfecta usa los precios reales y es una cota superior que ningún plan puede alcanzar. Con el tope de calidad por defecto de 1.5, un LP sobre la previsión obtiene alrededor de 0.74–0.79 de la puntuación de calidad.

## Notas

- Sintético o no verificado. Los precios, la producción solar, la modificación a 25 MW, la eficiencia del 92% en cada sentido, la degradación de 5 EUR/MWh, la franja de consumo de red de 00:00–06:00 y la política de reserva son decisiones de diseño, no valores medidos.
- El perfil solar está idealizado: alcanza la potencia nominal completa de 30 MWp en CC, y el mediodía solar cae a las 12:45 hora local (13:45 tras el cambio de hora), antes que en un emplazamiento español con horario CET.
- Las cuestiones de diseño abiertas de la revisión del caso (fuerza de la referencia, el registro que revela demasiado, configuraciones, eventos de presión, un entregable de programa diario, fundamento de las reglas contractuales) están en REVIEW.md.
