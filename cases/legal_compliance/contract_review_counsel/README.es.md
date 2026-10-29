# Asesor jurídico de revisión de contratos — `legal_compliance/contract_review_counsel`

El equipo jurídico de Brightvale Holdings, una empresa que compra servicios y materiales a unos cuarenta proveedores,
pide al agente que «revise estos contratos con proveedores y nos indique cuáles necesitan cambios antes de firmarlos».
El entregable es `review.json`: para cada contrato del registro, los códigos de incidencia detectados y una decisión
(`sign`, `negotiate` o `reject`). La solicitud no dice nada sobre qué cuenta como incidencia. Los criterios de
contratación de la empresa (siete puntos con sus umbrales), los códigos de incidencia, la regla de decisión y la vía
rápida para contratos pequeños están en los requisitos ocultos, y el agente tiene que preguntárselos al cliente.

El caso no tiene configuraciones: un mundo, una solución correcta, el mismo problema en todas las dificultades. Los
parámetros de la interacción (especificación completa frente a aclarar primero, perfil del cliente, ruido en los datos,
eventos) se aplican por encima, como en todos los casos (véase [cases/README.md](../../README.md)).

## Datos

- `contract_register.csv` (nombre localizado, p. ej. `계약대장.csv`; en español, `registro_contratos.csv`):
  `contract_id`, `supplier`, `category` (seis categorías de compra; la mayor es TI y servicios de datos, con 12 de 40),
  `annual_value_usd` y `contract_file`. En la versión en español las columnas se llaman `id_contrato`, `proveedor`,
  `categoria`, `importe_anual_usd` y `archivo_contrato`. Los requisitos dicen que el importe del registro es «el importe
  anual del contrato» al que se refieren los contratos.
- `contracts/C001.txt` … `C040.txt` (en español, `contratos/`): un contrato de suministro por archivo, con 7 u 8
  cláusulas (objeto y duración, precio y forma de pago, confidencialidad, protección de datos cuando la hay,
  indemnidad, limitación de responsabilidad, resolución, ley aplicable y jurisdicción). Los contratos están redactados
  en el idioma del cliente. Seis de ellos (C012, C021, C024, C028, C032, C036) son contratos propios del proveedor en
  otro idioma: español para un cliente de habla inglesa e inglés para las otras cuatro configuraciones regionales.
- Importes con la semilla 20261026: 8 contratos por debajo de USD 20,000 (de 7,500 a 19,000), 14 entre 26,000 y
  131,500 y 18 entre 268,000 y 1,176,500.

## Reglas

| Regla | Tipo | Qué dice |
|---|---|---|
| `all_contracts_reviewed` | física | Todos los contratos del registro tienen una entrada. |
| `decision_consistency` | contractual | La decisión se deduce de las incidencias indicadas: `reject` con dos o más incidencias críticas (`LIABILITY_CAP`, `DATA_PROTECTION`, `INDEMNITY`), `negotiate` con alguna incidencia y `sign` en los demás casos. |
| `small_contract_fast_track` | costumbre del negocio (flexibilizable) | Los contratos por debajo de USD 20,000 se marcan como `sign` sin incidencias y sin revisión. |

La **calidad** (cuanto más alta, mejor) es 0.7 × la F1 micro de los códigos de incidencia sobre todos los pares
contrato × código más 0.3 × la proporción de contratos cuya decisión coincide con la que los criterios asignan a sus
incidencias reales. Se puntúa siempre frente al mundo, nunca frente al texto generado.

## Los criterios de contratación y las trampas de cada cláusula

| Código | Regla | Cómo lo formulan los contratos, y la trampa |
|---|---|---|
| `LIABILITY_CAP` | límite ≥ 1 × importe anual | Un múltiplo en cifras o en palabras ("one half of", "twice"); un importe fijo en cifras o parafraseado ("US$20 thousand in aggregate", 万/만 en zh/ko/ja, "mil dólares" en es); o "the fees paid in the six months preceding the claim", que equivale a N/12 × el importe. Un límite exactamente igual al importe pasa (con esta semilla, 8 contratos por encima de la vía rápida están exactamente en 1×), y también pasa un contrato sin límite. |
| `GOVERNING_LAW` | Derecho suizo o de Singapur | "Swiss law" o "the laws of Switzerland". En 14 de los 40 contratos de esta semilla, los tribunales o la sede del arbitraje están en una jurisdicción distinta de la ley aplicable; solo cuenta la ley, de modo que la ley de Hong Kong con sede en Singapur es una incidencia. |
| `AUTO_RENEWAL` | preaviso de no renovación ≥ 60 días | "Renews automatically … unless notice" o "continues for a further year … unless a party objects"; el preaviso se expresa en días o en meses (un mes son 30 días: "two months" pasa, "forty-five days" no). Un contrato que simplemente vence pasa. |
| `PAYMENT_TERMS` | ≥ 45 días desde la recepción de la factura | En cifras, en palabras ("forty-five days") o "net 30". |
| `DATA_PROTECTION` | los contratos de TI y datos necesitan una cláusula de datos personales | Titulada "Data Protection" o "Personal Information", con distinta redacción; solo la categoría del registro decide si hace falta. |
| `TERMINATION_CONVENIENCE` | por encima de USD 150,000, el cliente puede desistir sin causa | "For convenience" o "bring this Agreement to an end at any time and without stating a reason"; la resolución por incumplimiento no cuenta. Estrictamente por encima de 150,000. |
| `INDEMNITY` | recíproca | "Each party shall indemnify the other", o lo mismo como dos promesas ("the Supplier shall indemnify the Customer … and the Customer shall indemnify the Supplier on the same terms"); unilateral significa que solo el cliente indemniza al proveedor. |

Solución correcta con la semilla 20261026: 69 códigos de incidencia en 33 de los 40 contratos, 8 de ellos `reject`.
Por encima de la vía rápida (32 contratos) hay 58 códigos; las decisiones allí son 7 `reject`, 18 `negotiate` y 7
`sign`.

## Situaciones presentes

- **Hechos ocultos.** Todo lo que decide qué es correcto (los siete puntos y sus umbrales, los códigos, la regla de
  decisión, la vía rápida) está en los requisitos ocultos. Nada en los datos lo indica.
- **Una costumbre de la empresa (la vía rápida).** El cliente firma los contratos por debajo de USD 20,000 sin revisión
  jurídica. La regla es una costumbre del negocio flexibilizable. Mientras se mantiene, la respuesta correcta para un
  contrato pequeño es `sign` sin incidencias, y una revisión que la respeta acierta esos contratos. Si el agente la
  incumple, la revisión solo cuenta con una excepción aprobada. En ese caso, los contratos pequeños se juzgan según los
  criterios como los demás, y se aplica la penalización por regla flexible de la política. Con esta semilla, los 8
  contratos pequeños tienen incidencias según los criterios (11 códigos; C029 sería un `reject`), así que un revisor
  que nunca se entera de la vía rápida y los revisa queda invalidado si no tiene una excepción. Flexibilizar la regla
  no compensa en puntuación: la referencia que deja de lado la vía rápida obtiene 0.8595, frente a 0.8825 cuando la
  respeta, antes de la penalización.
- **Idioma.** Seis contratos están redactados en un segundo idioma, y cada cláusula tiene dos o tres formulaciones.
- No presentes: eventos con fecha (modificaciones, cartas complementarias, un contrato ya renovado), mensajes en la
  bandeja de entrada, fuentes contradictorias o presiones para firmar un contrato desfavorable. Véase REVIEW.md F5.

## Referencia y línea base

La **referencia** es una lista de comprobación literal por palabras clave que lee la versión en inglés de cada
contrato (sea cual sea la configuración regional) y respeta la vía rápida. Maneja las cifras, los números escritos en
palabras para los días de pago y "one half of", y pasa por alto las paráfrasis. **Línea base**: firma todos los
contratos tal como están, sin incidencias y con la decisión `sign` (lo que hace el cliente sin un revisor). Ambas son
válidas. La calidad normalizada es (objetivo − línea base) / (referencia − línea base).

| Semilla de mundo | Línea base | Referencia | Revisión con información completa (respeta la vía rápida) |
|---|---|---|---|
| 20261026 (conjunto de datos guardado) | 0.1125 | 0.8825 | 1.0 (calidad 1.153) |
| 1 | 0.0750 | 0.8485 | 1.0 (calidad 1.196) |
| 2 | 0.1200 | 0.8301 | 1.0 (calidad 1.239) |
| 3 | 0.0900 | 0.7793 | 1.0 (calidad 1.320) |

Con la semilla 20261026 la referencia obtiene una F1 de incidencias de 0.875 (precisión 0.907, exhaustividad 0.845:
tp 49, fp 5, fn 9) y una exactitud de decisiones de 0.90. Todos sus errores están por encima de la vía rápida:

- **Omisiones (9).** Tres `LIABILITY_CAP`: dos límites por periodo de seis meses (C010, C011) y un "US$20 thousand"
  parafraseado (C027). Cuatro `AUTO_RENEWAL`: "continues for a further year" (C021, C027, C039) y un preaviso escrito
  como "forty-five days" (C020). Dos `GOVERNING_LAW`: ley de Hong Kong con sede o tribunales en Singapur (C037, C039).
- **Falsos positivos (5).** Tres `INDEMNITY`, en los que la indemnidad recíproca se redacta como dos promesas (C001,
  C025, C039), y dos `TERMINATION_CONVENIENCE`, en los que el derecho se formula como "without stating a reason"
  (C014, C033).

La línea base no da ningún código (F1 0). Su exactitud de decisiones es 0.375, gracias a los 15 contratos cuya
respuesta correcta es `sign`: los 8 de la vía rápida y 7 más grandes sin incidencias.

Margen de mejora con la semilla 20261026 (cada revisión es la revisión con información completa con un único error,
respetando la vía rápida):

| Revisión | Objetivo | Calidad |
|---|---|---|
| Información completa | 1.0 | 1.153 |
| Nunca marca `AUTO_RENEWAL` | 0.9550 | 1.094 |
| Nunca marca `TERMINATION_CONVENIENCE` | 0.9481 | 1.085 |
| Lee el foro en lugar de la ley aplicable | 0.9321 | 1.064 |
| Deja vacíos los 6 contratos propios del proveedor en otro idioma | 0.9181 | 1.046 |
| Marca los límites exactamente iguales al importe | 0.9173 | 1.045 |
| Nunca marca `AUTO_RENEWAL` ni `TERMINATION_CONVENIENCE` | 0.8960 | 1.018 |
| Referencia | 0.8825 | 1.0 |
| Referencia con la vía rápida flexibilizada (antes de la penalización) | 0.8595 | 0.970 |

Con el tope de calidad por defecto de la política, 1.5, la mejor revisión posible alcanza 1.153 / 1.5 ≈ 0.77 del
componente de calidad con esta semilla (REVIEW.md F1).

## Notas

- La práctica detrás de los hechos. Los siete puntos son los habituales de unos criterios internos de compras. Las
  encuestas "Most Negotiated Terms" de World Commerce & Contracting sitúan desde hace tiempo la limitación de
  responsabilidad y la indemnidad en lo más alto de la lista. Un límite equivalente al importe de un año, una ley aplicable
  preferida, un plazo mínimo de preaviso de no renovación, plazos de pago netos y el desistimiento por conveniencia en
  los contratos grandes son posiciones habituales. La cláusula de protección de datos que usan los contratos sigue las
  condiciones del encargado del tratamiento del artículo 28, apartado 3, del RGPD: tratamiento solo según
  instrucciones documentadas, medidas de seguridad y supresión o devolución al final, más la notificación de brechas
  (artículo 33, apartado 2).
- Sintético. La empresa, los proveedores, los importes, los umbrales (60 días, 45 días, USD 150,000, USD 20,000) y la
  regla de decisión son decisiones de diseño, no proceden de unos criterios reales. El mundo se construye solo a partir
  de `random.Random(seed)`.
- El importe del registro equivale por definición a «el importe anual del contrato». El objeto del contrato siempre
  coincide con la categoría del registro, así que el punto de protección de datos consiste en consultar la categoría y
  comprobar la cláusula.
- `validate-case` comprueba datos deterministas en cinco configuraciones regionales, una referencia válida con
  calidad 1.0, una línea base válida por debajo de ella, un entregable por regla que incumple solo esa regla y las
  semillas de mundo 1–3.
