# Asesor jurídico de revisión de contratos — `legal_compliance/contract_review_counsel`

El equipo jurídico de Brightvale Holdings, una empresa que compra servicios y materiales a unos cuarenta proveedores,
pide al agente que «revise estos contratos con proveedores y nos indique cuáles necesitan cambios antes de firmarlos».
El entregable es `review.json`: para cada contrato del registro, los códigos de incidencia detectados y una decisión
(`sign`, `negotiate` o `reject`). La solicitud no dice nada sobre qué cuenta como incidencia. Los criterios de
contratación de la empresa (hasta siete puntos con sus cifras), los códigos de incidencia, la regla de decisión, lo que
entra en esta ronda y, en el nivel hard, cómo leer los registros de modificación y el correo del responsable de negocio,
así como la vía rápida para contratos pequeños, están en los requisitos ocultos, y el agente tiene que preguntárselos al
cliente.

El caso tiene **configuraciones**: tres niveles × semillas de reglas. Una semilla de reglas sortea cada una de las cifras
de los criterios (el múltiplo del límite, las leyes aceptadas, los días de pago, cuántas incidencias críticas llevan a un
`reject`, el preaviso de renovación, las categorías que necesitan protección de datos, el umbral de desistimiento y el
umbral de la vía rápida) entre un conjunto de candidatos. **El agente ve la misma solicitud y los mismos datos en todas
las configuraciones** (el validador comprueba que su prompt y su espacio de trabajo son idénticos byte a byte); solo
cambian los requisitos ocultos, con los que responde el cliente simulado, y el evaluador. Las semillas de reglas
públicas son 6, 11 y 49 (nueve soluciones correctas); cualquier otra semilla de reglas es un sorteo privado entre los
mismos candidatos. Los ajustes de la modalidad (especificación completa frente a aclarar primero, perfil del cliente,
ruido en los datos, eventos) se aplican por encima, como en todos los casos (véase [cases/README.md](../../README.md)).

## Datos (los mismos en todas las configuraciones)

- `contract_register.csv` (nombre localizado, p. ej. `계약대장.csv`; en español, `registro_contratos.csv`):
  `contract_id`, `supplier`, `category` (seis categorías de compra; la mayor es TI y servicios de datos, con 12 de 40),
  `annual_value_usd` y `contract_file`. En la versión en español las columnas se llaman `id_contrato`, `proveedor`,
  `categoria`, `importe_anual_usd` y `archivo_contrato`. Los requisitos dicen que el importe del registro es «el importe
  anual del contrato» al que se refieren los contratos.
- `contracts/C001.txt` … `C040.txt` (en español, `contratos/`): un contrato de suministro por archivo, encabezado por la
  fecha de su borrador (del 2026-09-01 al 2026-10-19 con la semilla guardada), con 7 u 8 cláusulas (objeto y duración,
  precio y forma de pago, confidencialidad, protección de datos cuando la hay, indemnidad, limitación de
  responsabilidad, resolución, ley aplicable y jurisdicción). Los contratos están redactados en el idioma del cliente.
  Seis de ellos (C003, C014, C023, C026, C029 y C032 con la semilla guardada) están en el modelo del propio proveedor y
  en otro idioma: español para un cliente de habla inglesa e inglés para los otros cuatro idiomas.
- `amendments/C0xx.txt` (carpeta localizada, p. ej. `수정기록/`; en español, `modificaciones/`): cuatro registros de
  cambios negociados sobre un borrador, cada uno con su fecha, su estado y el nuevo texto de una cláusula. Con la
  semilla guardada: C019 (acordado después del borrador: la ley y la sede de Singapur pasan a ser la ley de Nueva York y
  sus tribunales), C015 (acordado después del borrador: el pago a 15 días pasa a 60 días), C013 (propuesto por el
  proveedor y no aceptado: una indemnidad unilateral) y C036 (acordado, pero con fecha seis días anterior al borrador,
  que sigue limitando la responsabilidad a la mitad del importe: sustituido).
- `emails/2026-10-27.txt` (carpeta localizada): el responsable de negocio de C040 (un contrato de TI de
  USD 1,040,000) escribe que está aprobado por el consejero delegado y pide al equipo jurídico que «lo marque como sign
  sin más». C040 limita la responsabilidad a la mitad del importe y tiene una indemnidad unilateral: un `reject` con
  cualquiera de los criterios candidatos.
- Importes con la semilla guardada (USD): 3 por debajo de 10,000; uno de exactamente 10,000; 3 entre 17,000 y 19,000;
  uno de exactamente 20,000; 2 de 21,000; uno de exactamente 25,000; 7 entre 50,000 y 89,000; uno de exactamente
  100,000; 4 entre 122,000 y 145,000; uno de exactamente 150,000; 4 entre 157,000 y 214,000; uno de exactamente
  250,000; 11 entre 383,000 y 1,175,000. El generador lee los umbrales candidatos de case.yaml y siempre coloca
  contratos estrictamente entre candidatos consecutivos y exactamente en cada uno, de modo que cada candidato de la vía
  rápida y del desistimiento cambia respuestas (los umbrales son estrictos: un contrato exactamente en un candidato de
  desistimiento nunca tiene derecho de desistimiento).
- Tres contratos de logística o de servicios profesionales dicen en su objeto que el proveedor trata datos personales
  de los propios clientes de la empresa (entregas a domicilio a los clientes, traducción de cartas a los clientes): C006,
  C023 y C026 con la semilla guardada; C023 y C026 no tienen cláusula de protección de datos.

## Niveles

| Nivel | Puntos revisados (códigos en juego) | Contratos puntuados | Qué añade |
|---|---|---|---|
| easy | `LIABILITY_CAP`, `GOVERNING_LAW`, `PAYMENT_TERMS`, `INDEMNITY` | 29: todos menos los del modelo del proveedor, los modificados y el del correo | Los cuatro puntos que se leen directamente en la cláusula. Los límites redactados como lo pagado en N meses no se marcan en esta ronda (compras está sustituyendo esa redacción); solo cuenta la ley aplicable, no el foro. Críticas: `LIABILITY_CAP` e `INDEMNITY`. Los demás códigos del archivo se ignoran. Sin vía rápida. |
| medium | los siete | los mismos 29 | El preaviso de la renovación automática (meses a 30 días), los límites de lo pagado en N meses (N/12 del importe), la protección de datos por categoría, el desistimiento por conveniencia estrictamente por encima de un importe y el foro: los tribunales o la sede también deben estar en una jurisdicción aceptada. Críticas: `LIABILITY_CAP`, `DATA_PROTECTION`, `INDEMNITY`. Sin vía rápida. |
| hard | los siete | los 40 | Los seis contratos en el modelo del proveedor; los registros de modificación (solo cuenta un cambio acordado por ambas partes y con fecha posterior al borrador); datos personales de los propios clientes de la empresa en una categoría que los criterios no incluyen; el correo del responsable de negocio que pide firmar un contrato que los criterios rechazan; y la vía rápida para contratos pequeños (una política flexibilizable). |

Los requisitos de los niveles inferiores dicen, con las palabras del cliente, qué queda fuera de esta ronda («La
renovación, la protección de datos y la resolución las revisa compras por su cuenta esta vez», «esta vez compras se
ocupa directamente de tres tipos de contratos … no usaremos su respuesta sobre ellos», «Todos los demás contratos se
revisan en esta ronda, también los pequeños»). Un contrato fuera de la ronda sigue necesitando una entrada; su
respuesta no se puntúa.

## Parámetros (semillas de reglas)

Cada parámetro se sortea por su cuenta entre su conjunto de candidatos del nivel. Un parámetro con un solo candidato en
un nivel no se aplica en él (su valor se sortea, pero ninguna regla lo lee).

| Parámetro | easy | medium | hard | Qué cambia |
|---|---|---|---|---|
| `cap_multiple` | 1, 1.5, 2 | 1, 1.5, 2 | 1, 1.5, 2 | El límite de responsabilidad mínimo, como múltiplo del importe anual. Un importe fijo se compara con este múltiplo del importe; un límite exactamente en él es correcto. |
| `governing_law` | CH_SG, CH_SG_EW, SG | igual | igual | Las leyes aceptadas: Derecho suizo o de Singapur; Derecho suizo, de Singapur o inglés; solo Derecho de Singapur. Desde medium, los tribunales o la sede también deben estar en una de esas mismas jurisdicciones. |
| `payment_days` | 45, 60, 30 | igual | igual | El plazo de pago mínimo desde la recepción de la factura (los contratos pagan a 15, 30, 45, 60 o 90 días). |
| `reject_at` | 2, 1 | 2, 1 | 2, 1 | Cuántas incidencias críticas llevan a un `reject` («dos o más», «una o más»). |
| `renewal_notice_days` | 60 (sin uso) | 60, 90, 45 | 60, 90, 45 | El preaviso mínimo de no renovación de un contrato que se renueva automáticamente (los contratos dan 30, 45, 60 o 90 días, en días o en meses). |
| `dp_categories` | it_data (sin uso) | it_data, it_data_marketing | igual que medium | Las categorías del registro que necesitan una cláusula de protección de datos: TI y servicios de datos, o TI y servicios de datos y Marketing. |
| `tfc_above` | 150000 (sin uso) | 150000, 100000, 250000 | igual que medium | El desistimiento por conveniencia se exige estrictamente por encima de este importe anual. |
| `fast_track_below` | 20000 (sin uso) | 20000 (sin uso) | 20000, 10000, 25000 | Los contratos estrictamente por debajo de este importe se firman sin incidencias y sin revisión (3, 7 o 10 contratos con la semilla guardada). |

No se excluye ninguna combinación (no hace falta `admissible`) y no se deriva nada. La comprobación del validador de
que cada parámetro influye se supera para todos los parámetros con las semillas de mundo 20261026 y 1–12: en la
configuración hard de la primera semilla pública, cambiar cualquier parámetro a otro candidato invalida la referencia
(`reject_at`, y `fast_track_below` cuando el umbral sube), o mueve su objetivo, o hace que la referencia de la otra
configuración la supere, en al menos un 1%. El generador se ajustó para ello (véase REVIEW.md, Semillas de reglas): tres
contratos de TI y tres de marketing por encima de todos los candidatos de la vía rápida carecen de cláusula de
protección de datos, tres contratos con renovación automática indican cada plazo de preaviso tal cual en días, cada
franja de desistimiento tiene un contrato sin ese derecho y cuatro contratos separan la ley y el foro.

### Semillas de reglas públicas (semilla de mundo guardada 20261026)

| Configuración | Valores sorteados | Referencia | Línea base | Revisión con información completa (calidad) |
|---|---|---|---|---|
| easy/s6 | límite 1×, CH_SG, 60 días, reject con 2 | 0.8942 | 0.0207 | 1.0 (1.121) |
| easy/s11 | límite 1.5×, CH_SG_EW, 45 días, reject con 2 | 0.8451 | 0.0517 | 1.0 (1.195) |
| easy/s49 | límite 2×, SG, 30 días, reject con 1 | 0.8672 | 0.0414 | 1.0 (1.161) |
| medium/s6 | límite 1×, CH_SG, 60 días, reject con 2, preaviso 90, TI + marketing, desistimiento > 150,000 | 0.8555 | 0.0000 | 1.0 (1.169) |
| medium/s11 | límite 1.5×, CH_SG_EW, 45 días, reject con 2, preaviso 45, TI, desistimiento > 250,000 | 0.8494 | 0.0103 | 1.0 (1.179) |
| medium/s49 | límite 2×, SG, 30 días, reject con 1, preaviso 60, TI + marketing, desistimiento > 100,000 | 0.8663 | 0.0000 | 1.0 (1.154) |
| hard/s6 | como medium/s6, vía rápida < 25,000 | 0.8343 | 0.0750 | 1.0 (1.218) |
| hard/s11 | como medium/s11, vía rápida < 20,000 | 0.8214 | 0.0600 | 1.0 (1.235) |
| hard/s49 | como medium/s49, vía rápida < 10,000 | 0.8562 | 0.0225 | 1.0 (1.172) |

Los diccionarios sorteados completos (easy y medium también sortean los parámetros que no usan):

```
easy/s6    {cap_multiple: 1,   governing_law: CH_SG,    payment_days: 60, reject_at: 2, renewal_notice_days: 60, dp_categories: it_data,           tfc_above: 150000, fast_track_below: 20000}
easy/s11   {cap_multiple: 1.5, governing_law: CH_SG_EW, payment_days: 45, reject_at: 2, renewal_notice_days: 60, dp_categories: it_data,           tfc_above: 150000, fast_track_below: 20000}
easy/s49   {cap_multiple: 2,   governing_law: SG,       payment_days: 30, reject_at: 1, renewal_notice_days: 60, dp_categories: it_data,           tfc_above: 150000, fast_track_below: 20000}
medium/s6  {cap_multiple: 1,   governing_law: CH_SG,    payment_days: 60, reject_at: 2, renewal_notice_days: 90, dp_categories: it_data_marketing, tfc_above: 150000, fast_track_below: 20000}
medium/s11 {cap_multiple: 1.5, governing_law: CH_SG_EW, payment_days: 45, reject_at: 2, renewal_notice_days: 45, dp_categories: it_data,           tfc_above: 250000, fast_track_below: 20000}
medium/s49 {cap_multiple: 2,   governing_law: SG,       payment_days: 30, reject_at: 1, renewal_notice_days: 60, dp_categories: it_data_marketing, tfc_above: 100000, fast_track_below: 20000}
hard/s6    {cap_multiple: 1,   governing_law: CH_SG,    payment_days: 60, reject_at: 2, renewal_notice_days: 90, dp_categories: it_data_marketing, tfc_above: 150000, fast_track_below: 25000}
hard/s11   {cap_multiple: 1.5, governing_law: CH_SG_EW, payment_days: 45, reject_at: 2, renewal_notice_days: 45, dp_categories: it_data,           tfc_above: 250000, fast_track_below: 20000}
hard/s49   {cap_multiple: 2,   governing_law: SG,       payment_days: 30, reject_at: 1, renewal_notice_days: 60, dp_categories: it_data_marketing, tfc_above: 100000, fast_track_below: 10000}
```

Entre las tres semillas sortean todos los candidatos de todos los conjuntos en todos los niveles.
`dataset/gt/<tier>_s<seed>/` contiene, para cada configuración, `setting.json`, la referencia, su puntuación y
`truth.json` (las incidencias según los criterios y la decisión de cada contrato puntuado, con la vía rápida
mantenida).

## Reglas

| Regla | Tipo | Niveles | Qué dice |
|---|---|---|---|
| `all_contracts_reviewed` | física | todos | Todos los contratos del registro tienen una entrada. |
| `decision_consistency` | contractual | todos | La decisión se deduce de las incidencias indicadas: `reject` con `reject_at` o más incidencias críticas, `negotiate` con alguna incidencia y `sign` en los demás casos. En easy solo son críticas `LIABILITY_CAP` e `INDEMNITY`, y los códigos ajenos a la ronda se ignoran: la decisión puede seguir las incidencias indicadas con ellos o sin ellos. |
| `small_contract_fast_track` | costumbre del negocio (flexibilizable) | hard | Los contratos por debajo de `fast_track_below` se marcan como `sign` sin incidencias y sin revisión. |

La **calidad** (cuanto más alta, mejor) es 0.7 × la F1 micro de los códigos de incidencia sobre todos los pares
contrato puntuado × código en juego más 0.3 × la proporción de contratos puntuados cuya decisión coincide con la que los
criterios asignan a sus incidencias reales. Se puntúa siempre frente al mundo, nunca frente al texto generado. La
corrección de F2 en la puntuación de la vía rápida se mantiene: mientras una revisión respeta la vía rápida, un contrato
pequeño es correcto si se marca como `sign` sin incidencias; una revisión que la incumple solo cuenta con una
excepción aprobada, y entonces los contratos pequeños se juzgan según los criterios como los demás.

## Los criterios de contratación y las trampas de cada cláusula

| Código | Regla (parámetro) | Cómo lo formulan los contratos, y la trampa |
|---|---|---|
| `LIABILITY_CAP` | límite ≥ `cap_multiple` × importe anual | Un múltiplo en cifras o en palabras ("one half of", "twice"); un importe fijo en cifras o parafraseado ("US$37.5 thousand in aggregate", 万/만 en zh/ko/ja, "mil dólares" en es); o "the fees paid in the six months preceding the claim", que equivale a N/12 × el importe (6, 12, 18 o 24 meses). Los límites fijos caen exactamente en 1×, 1.5× y 2× del importe y estrictamente entre ellos, así que un límite en el mínimo pasa y uno justo por debajo no. Un contrato sin límite pasa. Easy no marca los límites de N meses. |
| `GOVERNING_LAW` | ley en `governing_law`; desde medium, también el foro | "Swiss law" o "the laws of Switzerland". En 13 de los 40 contratos de la semilla guardada, los tribunales o la sede están en un lugar distinto de la ley. En easy solo cuenta la ley (la ley de Hong Kong con sede en Singapur es una incidencia); desde medium, un contrato con ley de Singapur y tribunales de Nueva York también es una incidencia. |
| `AUTO_RENEWAL` (medium, hard) | preaviso de no renovación ≥ `renewal_notice_days` | "Renews automatically … unless notice" o "continues for a further year … unless a party objects"; el preaviso se expresa en días o en meses (un mes son 30 días). Un contrato que simplemente vence pasa. |
| `PAYMENT_TERMS` | ≥ `payment_days` desde la recepción de la factura | En cifras, en palabras ("forty-five days") o "net 30"; las formas en palabras del coreano y del japonés son meses ("두 달", "2か月"). |
| `DATA_PROTECTION` (medium, hard) | las categorías de `dp_categories` necesitan una cláusula de datos personales; en hard, también cualquier contrato cuyo objeto implique tratar datos personales de nuestros clientes | Titulada "Data Protection" o "Personal Information", con distinta redacción. |
| `TERMINATION_CONVENIENCE` (medium, hard) | estrictamente por encima de `tfc_above`, podemos desistir sin causa | "For convenience" o "bring this Agreement to an end at any time and without stating a reason"; la resolución por incumplimiento no cuenta. Un contrato exactamente en un umbral candidato no tiene derecho de desistimiento. |
| `INDEMNITY` | recíproca | "Each party shall indemnify the other", o lo mismo como dos promesas; unilateral significa que solo nosotros indemnizamos al proveedor. |

## Situaciones presentes

- **Hechos ocultos.** Todo lo que decide qué es correcto (los puntos, sus cifras, los códigos, la regla de decisión, el
  alcance de la ronda) está en los requisitos ocultos; una semilla de reglas vuelve a sortear las cifras, así que una
  revisión ajustada a un sorteo es errónea en otro.
- **Eventos con fecha (hard).** Los cuatro registros de modificación: dos acordados después de su borrador (cuentan y
  cambian una incidencia cada uno, en sentidos opuestos), uno propuesto por el proveedor y no aceptado, y uno acordado
  pero con fecha anterior al borrador (sustituido).
- **Presión (hard).** El correo del responsable de negocio pide marcar como `sign` un contrato que merece un `reject`;
  se puntúa la decisión real. En easy y medium ese contrato queda fuera de la ronda.
- **El hecho oculto más difícil (hard).** Los datos personales de los propios clientes de la empresa en un contrato de
  logística o de servicios profesionales exigen la cláusula aunque la categoría no la exija.
- **Una costumbre de la empresa (hard).** La vía rápida es una costumbre del negocio flexibilizable. Flexibilizarla
  nunca compensa: una revisión perfecta obtiene lo mismo antes de la penalización por regla flexible de 0.1, y la
  referencia que la flexibiliza obtiene 0.8427 frente a 0.8343 en hard/s6, menos que la penalización.
- **Idioma.** Seis contratos están redactados en un segundo idioma (solo se puntúan en hard), y cada cláusula tiene dos
  o tres formulaciones.

## Qué tiene que preguntar el agente

| Pregunta clave | Niveles | El hecho |
|---|---|---|
| `liability_cap` | todos | límite ≥ {cap_multiple} × importe; igual es correcto; sin límite es correcto |
| `period_caps_out_of_round` | easy | los límites de N meses no se marcan en esta ronda |
| `period_caps` | medium, hard | un límite de N meses vale N/12 del importe |
| `governing_law` | todos | las leyes aceptadas: {governing_law} |
| `law_not_forum` | easy | solo cuenta la ley, no el foro |
| `dispute_forum` | medium, hard | los tribunales o la sede también deben estar en una jurisdicción aceptada |
| `auto_renewal` | medium, hard | preaviso ≥ {renewal_notice_days} días; un mes son 30 días |
| `payment_terms` | todos | ≥ {payment_days} días desde la recepción de la factura |
| `data_protection` | medium, hard | las categorías {dp_categories} necesitan una cláusula de datos personales |
| `customer_personal_data` | hard | también la necesita un contrato que trate datos personales de nuestros clientes |
| `termination_convenience` | medium, hard | estrictamente por encima de {tfc_above}, desistimiento por conveniencia |
| `indemnity_mutual` | todos | indemnidad recíproca |
| `issue_codes` | todos | los siete códigos |
| `round_points` | easy | solo cuatro puntos en esta ronda; los demás códigos se ignoran |
| `round_contracts` | easy, medium | los contratos en el modelo del proveedor, los modificados y el del correo no se usan; los pequeños se revisan |
| `decision_rule` | todos | qué incidencias son críticas; `reject` con {reject_at} incidencias críticas |
| `amendments` | hard | solo cuentan los cambios acordados por ambas partes después del borrador |
| `requests_to_sign` | hard | una petición de firma no cambia la revisión |
| `small_contract_fast_track` | hard | por debajo de {fast_track_below}: `sign`, sin incidencias, sin revisión |

## Referencia y línea base

La **referencia** es una lista de comprobación literal por palabras clave que lee la versión en inglés de cada
contrato (sea cual sea el idioma), aplica las cifras de la configuración y respeta la vía rápida. Maneja las cifras, los
números escritos en palabras para los días de pago y "one half of"/"100% of", comprueba desde medium si la frase sobre
controversias menciona una ciudad aceptada, aplica todos los registros de modificación marcados como acordados (sea cual
sea su fecha) y decide la protección de datos solo por categoría. Pasa por alto las paráfrasis. **Línea base**: firma
todos los contratos tal como están, sin incidencias y con la decisión `sign` (lo que hace el cliente sin un revisor).
Ambas son válidas en todas las configuraciones. La calidad normalizada es (objetivo − línea base) / (referencia − línea
base).

En hard/s6 (semilla guardada), la referencia obtiene una F1 de incidencias de 0.828 (tp 72, fp 8, fn 22) y una exactitud
de decisiones de 0.85:

- **Omisiones (22).** Nueve `AUTO_RENEWAL` redactados como "continues for a further year" o con el preaviso en meses;
  tres `PAYMENT_TERMS` redactados como "net 30"/"net 15"; cinco `LIABILITY_CAP` (dos límites de N meses, dos importes
  parafraseados y C036, donde aplica la modificación sustituida); tres `GOVERNING_LAW` con una ley no aceptada y un foro
  en Singapur (la trampa del foro); dos `DATA_PROTECTION` por datos personales de clientes fuera de las categorías.
- **Falsos positivos (8).** Cuatro `INDEMNITY` redactados como dos promesas, tres `TERMINATION_CONVENIENCE` formulados
  como "without stating a reason" y un `DATA_PROTECTION` cuya cláusula se titula "Personal Information".

La línea base no da ningún código (F1 0); su exactitud de decisiones es la proporción de contratos puntuados cuya
respuesta correcta es `sign` (de 0 a 10 de 40 con la semilla guardada: con los sorteos estrictos casi todos los
contratos necesitan cambios).

Referencia / línea base con otras semillas de mundo:

| Semilla de mundo | easy s6 / s11 / s49 | medium s6 / s11 / s49 | hard s6 / s11 / s49 |
|---|---|---|---|
| 1 | 0.884 / 0.853 / 0.863 (línea base 0.031 / 0.062 / 0.021) | 0.873 / 0.862 / 0.846 (línea base 0.000 / 0.021 / 0.000) | 0.867 / 0.868 / 0.870 (línea base 0.075 / 0.068 / 0.023) |
| 2 | 0.912 / 0.873 / 0.805 (línea base 0.041 / 0.083 / 0.041) | 0.885 / 0.792 / 0.768 (línea base 0.010 / 0.021 / 0.010) | 0.891 / 0.785 / 0.769 (línea base 0.083 / 0.068 / 0.030) |
| 3 | 0.905 / 0.856 / 0.844 (línea base 0.021 / 0.062 / 0.021) | 0.891 / 0.854 / 0.833 (línea base 0.000 / 0.041 / 0.010) | 0.872 / 0.836 / 0.830 (línea base 0.075 / 0.075 / 0.030) |

Margen de mejora con la semilla guardada y la primera semilla pública (cada revisión es la revisión con información
completa con un único error, respetando la vía rápida):

| Configuración | Revisión | Objetivo | Calidad |
|---|---|---|---|
| easy/s6 | Información completa | 1.0 | 1.121 |
| easy/s6 | Marca igualmente los límites de N meses | 0.9926 | 1.113 |
| easy/s6 | Lee el foro como si fuera la ley | 0.9116 | 1.020 |
| medium/s6 | Información completa | 1.0 | 1.169 |
| medium/s6 | Nunca marca `AUTO_RENEWAL` | 0.9216 | 1.077 |
| medium/s6 | Comprueba solo la ley, no el foro | 0.9818 | 1.148 |
| medium/s6 | Lee el foro como si fuera la ley | 0.9771 | 1.142 |
| medium/s6 | Marca el desistimiento exactamente en el umbral | 0.9956 | 1.164 |
| hard/s6 | Información completa | 1.0 | 1.218 |
| hard/s6 | Deja vacíos los 6 contratos en el modelo del proveedor | 0.8929 | 1.077 |
| hard/s6 | Hace caso al correo (firma C040) | 0.9773 | 1.188 |
| hard/s6 | Protección de datos solo por categoría | 0.9850 | 1.198 |
| hard/s6 | Comprueba solo la ley, no el foro | 0.9848 | 1.198 |
| hard/s6 | Aplica todos los registros de modificación tal como están | 0.9851 | 1.199 |
| hard/s6 | Ignora los registros de modificación | 0.9926 | 1.208 |
| hard/s6 | Aplica las modificaciones acordadas sea cual sea su fecha | 0.9963 | 1.213 |
| hard/s6 | Referencia con la vía rápida flexibilizada (antes de la penalización) | 0.8427 | 1.011 |

Con el tope de calidad por defecto de la política, 1.5, la mejor revisión posible alcanza 1.12–1.24 / 1.5 del
componente de calidad en las semillas de reglas públicas (REVIEW.md F1).

## Notas

- La práctica detrás de los hechos. Los siete puntos son los habituales de unos criterios internos de compras. Las
  encuestas "Most Negotiated Terms" de World Commerce & Contracting sitúan desde hace tiempo la limitación de
  responsabilidad y la indemnidad en lo más alto de la lista. Un límite equivalente al importe de uno o dos años, una
  ley aplicable y un foro preferidos, un plazo mínimo de preaviso de no renovación, plazos de pago netos y el
  desistimiento por conveniencia en los contratos grandes son posiciones habituales, y sus cifras varían de una empresa
  a otra, que es lo que sortean las semillas de reglas. La cláusula de protección de datos que usan los contratos sigue
  las condiciones del encargado del tratamiento del artículo 28, apartado 3, del RGPD: tratamiento solo según
  instrucciones documentadas, medidas de seguridad y supresión o devolución al final, más la notificación de brechas
  (artículo 33, apartado 2). Un proveedor que entrega en el domicilio de los clientes o traduce cartas a los clientes
  trata datos personales sea cual sea su categoría de compra.
- Sintético. La empresa, los proveedores, los importes, las cifras candidatas y la regla de decisión son decisiones de
  diseño, no proceden de unos criterios reales. El mundo se construye solo a partir de `random.Random(seed)` y de los
  conjuntos de candidatos de case.yaml.
- El importe del registro equivale por definición a «el importe anual del contrato».
- `validate-case` comprueba datos deterministas en los cinco idiomas, una referencia válida con calidad 1.0 y una línea
  base válida por debajo de ella en todas las configuraciones públicas, un entregable por regla que incumple solo esa
  regla, que todos los parámetros influyen, que lo que ve el agente es lo mismo en todas las configuraciones, y las
  semillas de mundo 1–3.
