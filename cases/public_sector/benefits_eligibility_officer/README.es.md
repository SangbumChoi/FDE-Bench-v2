# Técnico de elegibilidad de prestaciones — `public_sector/benefits_eligibility_officer`

La oficina de servicios sociales de una ciudad tiene acumuladas unas 300 solicitudes de su Ayuda de Subsistencia para
Hogares, que se paga cada mes, y pide al agente que "decida quién tiene derecho y cuánto le corresponde cada mes". El
entregable es `determinations.csv` (`household_id,eligible,monthly_amount,reason_code`), una fila por solicitud, con un
código de motivo entre `APPROVED`, `RENEWAL`, `DENY_RESIDENCY`, `DENY_ASSETS` y `DENY_INCOME`. La solicitud solo nombra
los archivos adjuntos; todas las reglas que deciden la validez y la calidad están en los requisitos ocultos y hay que
preguntarlas. El escenario no corresponde a ningún país: los importes están en las unidades de pago propias de la ciudad
y el tope es una regla presupuestaria local, no una ley real.

El caso no tiene configuraciones: una sola solución correcta y el mismo problema en todas las dificultades. Los ajustes
de la modalidad (especificación completa o aclarar primero, perfil del cliente, ruido en los datos, eventos) se aplican
por encima, como en todos los casos (véase [cases/README.md](../../README.md)).

## Datos

- `applications` (300 filas: 185 solicitudes nuevas y 115 renovaciones): tipo de solicitud, `application_date` y
  `resident_since` (día/mes/año en en y es, 年月日 en zh y ja, `2026. 9. 14.` en ko; solicitudes fechadas entre el
  1 de septiembre y el 20 de octubre de 2026), alquiler mensual y, en las renovaciones, `last_year_monthly_amount`.
- `household_members` (776 filas): parentesco, edad, `lives_at_address` (53 miembros de 48 hogares viven en otro
  lugar), `disability` y cinco columnas de ingresos mensuales (ingresos del trabajo, pensión, prestación por desempleo,
  pensión alimenticia y otros ingresos).
- `assets` (541 filas): ahorros, la vivienda en la que vive el hogar, coches (23 hogares tienen dos), inversiones y
  otros inmuebles.
- `amount_table_2025`: el importe base y la ayuda máxima de vivienda **del año pasado** para hogares de 1 a 10 personas.
- Un folleto para los ciudadanos que describe la ayuda con palabras y no da ninguna cifra.

## Reglas (requisitos ocultos)

| Hecho | Lo que dice el cliente cuando se le pregunta |
|---|---|
| Tamaño del hogar | Solo cuentan los miembros con `lives_at_address = yes`; los que viven en otro lugar se ignoran por completo, incluidos sus ingresos y su discapacidad |
| Residencia | Al menos 6 meses naturales en la ciudad en la fecha de la solicitud (requisito legal) → si no, `DENY_RESIDENCY` |
| Patrimonio | Todos los valores declarados salvo la vivienda y el coche de mayor valor; por encima de 6,000 + 3,000 por cada miembro adicional → `DENY_ASSETS` |
| Actualización | Tabla de este año = la del año pasado × 1.032, cada valor redondeado hacia abajo a un múltiplo de 10; la nueva tabla no está en los datos |
| Necesidad | Importe base + alquiler hasta la ayuda máxima de vivienda + 120 por cada miembro con discapacidad que viva en el domicilio |
| Ingresos | El 70% de (ingresos del trabajo − 150) por cada persona que trabaja; pensiones, prestación por desempleo, pensión alimenticia y otros ingresos, íntegros |
| Importe | Necesidad − ingresos, redondeado hacia abajo, como máximo el tope de 1,050 / 1,450 / 1,800 / 2,100 / 2,350 / 2,550 para 1-6 o más personas; 0 o menos → `DENY_INCOME` |
| Renovaciones | La práctica de la oficina: se aprueban con el importe del año pasado sin volver a evaluarlas (`RENEWAL`) |
| Códigos de motivo | La primera prueba no superada, en el orden residencia, patrimonio, ingresos; las aprobaciones son `APPROVED` (nuevas) o `RENEWAL` (renovaciones) |
| Objetivo | Pagar a cada hogar exactamente lo que le corresponde según las reglas de este año y, sobre todo, acertar en cada decisión de sí o no |

Tipos de regla: `amount_cap`, física; `residency_requirement`, `asset_limit` y `reason_code_required`, contractuales;
`auto_approve_renewals`, costumbre del negocio (puede flexibilizarse mediante el procedimiento de excepción con las
políticas que hacen flexible la costumbre del negocio).

**Objetivo (minimizar):** Σ |importe pagado − importe que realmente corresponde| sobre todos los hogares (0 pagado si se
rechaza) + 400 por cada decisión de derecho equivocada + 100 por cada hogar rechazado con razón pero con un código de
motivo distinto de la primera prueba que no supera. La solución correcta es lo que le corresponde este año a cada hogar,
renovaciones incluidas, de modo que la regla de renovaciones cuesta una cantidad fija que ninguna entrega que cumpla las
reglas puede evitar (véase REVIEW.md, F2).

## Situaciones presentes

- Solo hechos ocultos: la composición del hogar, la deducción de ingresos del trabajo por cada persona que trabaja, las
  exenciones de patrimonio, el periodo de residencia y el formato de fecha, la actualización de una tabla que no está en
  los datos, el suplemento por discapacidad, la pensión alimenticia como ingreso, el tope presupuestario y el orden de
  los códigos de motivo.
- Una tentación: la práctica de renovaciones, una regla de costumbre del negocio que paga a 102 renovaciones con derecho
  el importe del año pasado (49 cobran de más, 46 de menos y 7 lo exacto) y aprueba 13 renovaciones que ya no tienen
  derecho.
- No hay eventos con fecha, ni bandeja de entrada, ni elemento de presión; lo que el catálogo anuncia, "applicants in
  five languages; deadlines" (solicitantes en cinco idiomas; plazos), no está construido (REVIEW.md, F4).

## Referencia y línea base (semilla 20261026)

**Referencia** (`reference_solution`): las renovaciones se prorrogan con el importe del año pasado; las solicitudes
nuevas se evalúan con todas las reglas salvo una simplificación deliberada: la cantidad fija de 150 de los ingresos del
trabajo se aplica una sola vez por hogar en lugar de por cada persona que trabaja (afecta a 17 hogares nuevos con dos o
más personas que trabajan).

**Línea base** (`baseline_solution`): lo que haría la ventanilla sin un ingeniero. Las renovaciones se prorrogan como de
costumbre; cada solicitud nueva se revisa en residencia y patrimonio y se le paga la tabla publicada el año pasado
(importe base + alquiler hasta la ayuda máxima de vivienda) menos todos los ingresos del domicilio contados
íntegramente, dentro del tope. Pasa por alto la actualización, la deducción de ingresos del trabajo y el suplemento por
discapacidad.

| Entrega | Objetivo | Error de importe / decisiones equivocadas / motivos de rechazo equivocados | Calidad normalizada |
|---|---|---|---|
| Línea base | 58,879 | 44,479 / 36 / 0 | 0 |
| Referencia | 17,928 | 12,728 / 13 / 0 | 1 |
| Respuesta exacta, renovaciones prorrogadas (la mejor que cumple las reglas) | 16,773 | 11,573 / 13 / 0 | 1.028 |
| Respuesta exacta, regla de renovaciones flexibilizada (`auto_approve_renewals` relajada) | 0 | 0 / 0 / 0 | 1.438 |
| Referencia con renovaciones reevaluadas (flexibilizada) | 1,815 | 1,415 / 1 / 0 | 1.393 |
| Cumple las reglas, sin actualización | 22,840 | | 0.880 |
| Cumple las reglas, pensión alimenticia ignorada | 22,133 | | 0.897 |
| Cumple las reglas, suplemento por discapacidad ignorado | 19,173 | | 0.970 |
| La mejor que cumple las reglas, con todos los rechazos codificados `DENY_INCOME` | 22,173 | 11,573 / 13 / 54 | 0.896 |
| Todas las solicitudes nuevas rechazadas | 177,049 | | 0 (acotada en el mínimo) |

De los 17,928 de la referencia, 16,773 proceden de las filas de renovación (11,573 de error de importe + 13 × 400) y los
comparten todas las entregas que cumplen las reglas. Con el `quality_cap` de la política en 1.5, la mejor respuesta que
cumple las reglas obtiene 1.028 / 1.5 de la puntuación de calidad; véase REVIEW.md, F2. Las semillas de mundo 1, 2 y 3
dan objetivos de referencia / línea base de 14,435 / 49,945, 12,598 / 42,468 y 15,145 / 54,996; la mejor respuesta que
cumple las reglas obtiene allí 1.025-1.047.
