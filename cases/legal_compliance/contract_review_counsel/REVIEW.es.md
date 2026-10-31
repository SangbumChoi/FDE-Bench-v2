# Revisión — `legal_compliance/contract_review_counsel`

Hallazgos de la revisión del caso (F1–F9) y lo que este cambio hizo con cada uno. Las cifras son con la semilla de
mundo 20261026 salvo que se indique otra cosa. La conversión a semillas de reglas (última sección) actualiza varios
estados; cada actualización va después del estado que modifica, y las cifras anteriores se mantienen tal como se
midieron. La revisión se redactó antes de la corrección de F2 (referencia 0.7677) y con un tope de calidad de 1.0;
donde las cifras actuales difieren, se indican. Se agradecen comentarios sobre las
propuestas abiertas.

### F1 — La calidad se satura por debajo de la competencia real de revisión (alta, confirmado)

La referencia es una lista de comprobación literal por palabras clave sobre la versión en inglés. Antes de este cambio
obtenía 0.7677, y una revisión con información completa que respeta la vía rápida obtenía 0.8794 (calidad 1.145). Con
el antiguo tope de 1.0, cualquier error en una sola trampa (sin `TERMINATION_CONVENIENCE`, sin umbral de renovación,
el foro leído como ley aplicable, límites iguales al importe marcados, contratos propios del proveedor dejados vacíos)
seguía recibiendo la puntuación completa. En la escala actual (línea base 0, tope de la política 1.5) y después de F2,
la referencia obtiene 0.8825 y la revisión con información completa 1.0 (calidad 1.153). Los errores de una sola
trampa puntúan ahora 1.045–1.094 (1.018 cuando se omiten a la vez la renovación y el desistimiento), así que se
distinguen, pero la mejor revisión posible solo alcanza 1.153 / 1.5 ≈ 0.77 de la puntuación de calidad. Con las semillas
de mundo 1–3 el techo es 1.196, 1.239 y 1.320.

**Estado:** abierto — propuesta: reforzar la referencia para que resuelva los tipos de paráfrasis que hoy se le
escapan (preavisos en meses y en palabras, "continues for a further year", límites por periodo como N/12,
"US$… thousand", "without stating a reason", indemnidad recíproca redactada como dos promesas, ley frente a foro).
Así quedaría cerca del techo, y el margen restante vendría de elementos realmente difíciles. Como alternativa,
mantener la referencia débil y fijar `quality_cap` cerca de la calidad con información completa (alrededor de
1.15–1.3 según la semilla de mundo), para que una revisión perfecta reciba la puntuación completa. En cualquier caso,
añadir más elementos difíciles por contrato para que omitir una trampa cueste una calidad apreciable.

**Actualización (semillas de reglas):** sigue abierto. La referencia sigue siendo la lista de comprobación literal;
ahora además pasa por alto la trampa del foro en más contratos, los datos personales de los clientes de la empresa
fuera de las categorías indicadas (hard) y la modificación sustituida (hard). En las semillas de reglas públicas, la
revisión con información completa alcanza una calidad de 1.12–1.24 (1.121 / 1.195 / 1.161 en easy, 1.169 / 1.179 /
1.154 en medium y 1.218 / 1.235 / 1.172 en hard con la semilla guardada), así que la mejor revisión obtiene alrededor
de 0.75–0.82 de la puntuación de calidad con el tope de 1.5.

### F2 — Respetar la vía rápida se penalizaba (alta, confirmado)

La solución correcta de los 8 contratos por debajo de USD 20,000 contenía sus incidencias según los criterios (11
códigos; C029 un `reject`, C017 con tres incidencias), mientras que la regla de la vía rápida obligaba a `sign` sin
incidencias. Obedecer al cliente costaba por tanto 11 puntos de exhaustividad y 8 decisiones: 11 de las 20 omisiones
de la referencia se debían a seguir la regla. Flexibilizar la regla tampoco ayudaba a un agente del nivel de la
referencia, porque la calidad se recortaba y se aplicaba la penalización por regla flexible.

**Estado:** corregido en este cambio — `evaluate_review` juzga ahora un contrato pequeño frente a «sign, sin
incidencias» cuando la revisión mantiene la vía rápida. Solo usa las incidencias según los criterios cuando la
revisión incumple la regla, y esa revisión solo cuenta una vez que la regla se flexibiliza mediante una excepción
aprobada. La referencia sube de 0.7677 a 0.8825 (fn 20 → 9, exactitud de decisiones 0.70 → 0.90). La referencia con
la vía rápida flexibilizada obtiene 0.8595 (calidad 0.970) antes de la penalización, de modo que flexibilizar nunca
compensa. La frase sobre la calidad de requirements.md lo dice en los cinco idiomas. Sigue abierto:
un motivo puntuado para flexibilizar (p. ej., un contrato pequeño de TI que trata datos personales sin cláusula de
protección de datos, donde una excepción aprobada más marcar la incidencia supera a respetar la regla). También
abierta: la fila del catálogo en cases/README.md ("Accept vendor paper under a value threshold"), que queda fuera del
directorio de este caso.

**Actualización (semillas de reglas):** la corrección se mantiene sin cambios; la vía rápida se aplica ahora solo en
el nivel hard, con su umbral sorteado entre 10,000 / 20,000 / 25,000, y en easy y medium los requisitos dicen «Todos los
demás contratos se revisan en esta ronda, también los pequeños». Flexibilizar sigue sin compensar nunca: en hard/s6 una
revisión perfecta obtiene lo mismo antes de la penalización por regla flexible de 0.1, y la referencia que flexibiliza
la vía rápida obtiene 0.8427 frente a 0.8343.

### F3 — La decisión no aporta información; dos filtros de todo o nada (alta, confirmado)

`decide()` es una función pura de las incidencias indicadas. `decision_consistency` invalida toda la revisión ante
cualquier discrepancia, y la exactitud de decisiones compara `decide(pred)` con `decide(truth)`, así que el peso de
0.3 solo vuelve a ponderar la corrección de las incidencias en los códigos críticos. Un agente que nunca se entera de
la vía rápida es inválido con las políticas `baseline` y `regulated_strict` (excepciones prohibidas), y también lo es
uno que adivina otra regla de rechazo.

**Estado:** abierto — propuesta: dar a la decisión un hecho propio que conozca el cliente. Ejemplos: niveles de
aprobación según el importe, criticidad del proveedor, o qué incidencias son motivo de ruptura y cuáles son
negociables. Puntuarlo por separado. Considerar puntuar `decision_consistency` por contrato en lugar de anular toda la
revisión. Si preguntar por la vía rápida pretende ser la prueba clave, decirlo en el README.

**Actualización (semillas de reglas):** en parte. La regla de decisión contiene ahora un hecho sorteado que debe dar
el cliente: `reject_at` (un reject con dos o más, o con una o más, incidencias críticas), y qué códigos son críticos
depende del nivel (en easy solo `LIABILITY_CAP` e `INDEMNITY`). La decisión sigue siendo una función de las incidencias
indicadas, y `decision_consistency` sigue anulando toda la revisión; puntuarla por contrato sigue abierto.

### F4 — Sin configuraciones, y el mundo oculta los huecos entre umbrales (alta, confirmado)

Hay una sola solución correcta (`setting.json` es `{}`). Los importes proceden de tres franjas disjuntas
(6,000–19,500, 25,000–150,000, 160,000–1,200,000), y los importes observados saltan de 19,000 a 26,000 y de 131,500 a
268,000. Por tanto, cualquier umbral de vía rápida en (19k, 26k] o de desistimiento en [131.5k, 268k) da la misma
solución correcta. Los días de preaviso y de pago salen solo de {30, 45, 60, 90}, y los huecos dejan entrever dónde
están los umbrales.

**Estado:** abierto — propuesta: tres niveles. Easy cubre los cuatro puntos que se leen directamente en la cláusula
(límites, ley, pago, indemnidad), con la renovación, la protección de datos y el desistimiento «revisados por compras
en esta ronda». Medium añade la conversión de meses, los límites por periodo, la protección de datos según la
categoría, el desistimiento según el importe y la trampa del foro. Hard añade los contratos propios del proveedor, la
vía rápida y las situaciones de F5. Tres conjuntos de reglas sobre la ley, los días de preaviso, los días de pago, el
umbral de desistimiento, el múltiplo del límite, el umbral de la vía rápida y qué códigos son críticos; por ejemplo,
A = CH/SG, 60 d, 45 d, >150k, ≥1×, <20k; B = + England & Wales, 90 d, 60 d, >500k, ≥1.5×, <10k; C = solo SG, 45 d,
30 d, >100k, ≥2× para TI, <25k. Volver a generar importes, días de preaviso, días de pago y múltiplos del límite para
que queden a ambos lados de cada umbral candidato, y comprobar que la referencia de cada conjunto de reglas es
inválida, o al menos un 1% peor, con los demás.

**Actualización (semillas de reglas):** resuelto con la conversión (véase "Semillas de reglas" más abajo). Tres
niveles, como se proponía, ocho parámetros sorteados por semillas de reglas en lugar de conjuntos de reglas fijos, y un
generador que coloca importes de contratos estrictamente entre cada candidato de la vía rápida y del desistimiento y
exactamente en cada uno, límites en 1×, 1.5× y 2× y entre ellos, y plazos de preaviso y de pago a ambos lados de cada
candidato. Todos los parámetros influyen con las semillas de mundo 20261026 y 1–12.

### F5 — Aparte de los criterios, no hay situaciones (media, confirmado)

Los datos están limpios y son coherentes entre sí. `write_data` solo escribe los contratos y el registro: no hay
bandeja de entrada, modificaciones, hojas de pedido ni fechas. La frase del objeto es fija por categoría, así que el
punto de protección de datos se resuelve consultando el registro. El importe del registro es por definición «el
importe anual del contrato». La única presión es la costumbre de la vía rápida, y empuja hacia trabajar menos, no
hacia un incumplimiento tentador.

**Estado:** abierto — propuesta: añadir situaciones puntuadas. Hechos ocultos: un contrato de marketing o de
servicios profesionales cuyo objeto indica que trata la lista de clientes de la empresa, de modo que necesita una
cláusula de protección de datos en cuanto el cliente lo confirma; un importe del registro desfasado respecto de una
hoja de pedido adjunta. Eventos con fecha: una modificación o carta complementaria con fecha posterior al contrato que
cambia la ley o el preaviso de renovación; un contrato que ya se ha renovado automáticamente. Presión: un correo de un
patrocinador que dice «C0xx está aprobado por el director general, márquelo como sign» sobre un contrato que merece
un `reject`, puntuado según la decisión real.

**Actualización (semillas de reglas):** en parte. El nivel hard puntúa ahora tres de las situaciones propuestas.
Hecho oculto: tres contratos de logística o de servicios profesionales cuyo objeto entrega al proveedor datos
personales de los clientes de la empresa (dos de ellos, sin cláusula de protección de datos, la necesitan). Eventos con
fecha: cuatro registros de modificación, dos acordados después del borrador (uno introduce la ley y los tribunales de
Nueva York, otro eleva el plazo de pago de 15 a 60 días), uno propuesto por el proveedor y no aceptado (una indemnidad
unilateral) y uno acordado antes del borrador y, por tanto, sustituido (el límite se queda en la mitad del importe).
Presión: el correo de un responsable de negocio que pide «marcarlo como sign sin más» para un contrato que es un
`reject` con cualquiera de los criterios candidatos, puntuado según la decisión real. Sigue abierto: un importe del
registro desfasado respecto de una hoja de pedido y un contrato que ya se ha renovado automáticamente.

### F6 — Los contratos son plantillas cortas e idénticas (media, confirmado)

Todos los contratos tienen las mismas 7 u 8 cláusulas en el mismo orden. Los textos de confidencialidad e
incumplimiento nunca cambian, hay dos o tres formulaciones por cláusula y el «contrato propio del proveedor» es el
modelo del cliente traducido a otro idioma. 33 de los 40 contratos necesitan cambios y 8 son `reject`; 13 tienen una
indemnidad unilateral, 13 límites por debajo de 1× y 13 una ley distinta de la suiza o la de Singapur. Esa densidad
no es verosímil para contratos que, según se dice, siguen en su mayoría el modelo propio.

**Estado:** abierto — propuesta: presentar las desviaciones como marcas de revisión (redlines) del proveedor sobre el
modelo del cliente. Dar a los contratos propios de los proveedores una estructura propia: definiciones, una cláusula
de prelación, anexos, remisiones ("subject to clause 9.3") y exclusiones que anulen el límite. Añadir 4–6
formulaciones por cláusula, incluidas negaciones y excepciones, y bajar la proporción de contratos con incidencias
hacia el 40–50%.

**Actualización (semillas de reglas):** sigue abierto, y la densidad ha aumentado: el generador fuerza ahora
renovaciones automáticas, ley y foro separados y cláusulas ausentes para que cada cifra candidata cambie respuestas, y
los sorteos estrictos marcan casi todos los contratos (con la semilla guardada, 29 de los 29 contratos puntuados
necesitan cambios en medium/s6 y medium/s49, y 37 de 40 en hard/s49).

### F7 — Dificultad desigual entre idiomas y algunas cadenas poco naturales (media, confirmado)

Los contratos propios del proveedor están en inglés en zh, ko, ja y es, y solo en español en en, así que cuatro
de las cinco versiones reciben el segundo idioma más fácil. Los límites fijos parafraseados se dividían por
10,000 incluso por debajo de 10,000: C023 (límite de USD 5,000) decía "미화 0.5만 달러", "0.5万米ドル" y "0.5万美元". La
variante coreana del pago en cifras dice "세금계산서" (una factura fiscal coreana del IVA), mientras que las demás
variantes y los criterios dicen 청구서. requirements.md y targets.yaml en ko contienen el duplicado "검토 없이 이슈
없이". Las cifras y los umbrales coinciden en los cinco idiomas.

**Estado:** corregido en este cambio (solo los importes) — los límites parafraseados por debajo de 10,000 se escriben
ahora como lo haría un hablante nativo: "五千美元", "미화 5천 달러", "5,000米ドル" (aquí, C023). A partir de 10,000, ko y
ja separan un importe que no es un número exacto de miles ("99만 5,500달러", "99万5,500米ドル", visto con la semilla de
mundo 5); los importes redondos conservan la forma 万/만 ("2.5만 달러"). Solo cambian los textos de los contratos en
zh/ko/ja; la solución correcta y la referencia no. Sigue abierto — propuesta: usar para los contratos propios del
proveedor un tercer idioma que nunca sea el inglés ni el del cliente (alemán o francés) en todos los
idiomas. Usar 청구서 en toda la redacción coreana sobre el pago. Reformular la frase coreana de la vía rápida como
"법무 검토를 거치지 않고 이슈 없음(빈 목록), `sign`으로 처리합니다". Pedir una revisión por hablantes nativos de los cinco
idiomas.

**Actualización (semillas de reglas):** se corrigen dos cadenas más: la variante coreana del pago en cifras dice
ahora 청구서, como las demás (los textos de los contratos solo cambian en ko), y la frase coreana de la vía rápida dice
"법무 검토를 거치지 않고 이슈 없음(빈 리스트), `sign`으로 처리" en requirements.md, targets.yaml y la página
explicativa. Sigue abierto: un tercer idioma para los contratos en el modelo del proveedor y una revisión por hablantes
nativos de los textos nuevos (niveles, registros de modificación, el correo).

### F8 — Una pregunta clave agrupaba tres hechos (media, en parte)

`decision_and_scoring` combinaba los códigos de incidencia, la regla de decisión y los pesos "0.7 × issue F1 + 0.3 ×
decision accuracy". El cliente puede no indicar los pesos, así que esa parte nunca podía quedar cubierta. El
verificador corrigió dos afirmaciones secundarias. Primero, `deliverable_spec` solo llega al extractor, nunca al
agente. Segundo, el extractor solo se ejecuta cuando no existe `review.json`, así que los códigos inventados en el
propio `review.json` de un agente siguen siendo fatales.

**Estado:** corregido en este cambio — la pregunta clave se divide en `issue_codes` y `decision_rule` en los cinco
idiomas (en el mismo orden), y se elimina la cláusula de puntuación. La página explicativa ya
indica que la especificación del entregable se muestra al extractor, no al agente. Sigue abierto — propuesta: añadir
preguntas clave separadas para las reglas límite reales («un límite igual al importe es correcto», «un contrato sin
límite es correcto», «el foro no importa»), que hoy están dentro de las preguntas `liability_cap` y `governing_law`.

**Actualización (semillas de reglas):** las preguntas clave son ahora por nivel (10 en easy, 12 en medium, 15 en
hard), con preguntas separadas para los límites de N meses (`period_caps_out_of_round`, `period_caps`) y para el foro
(`law_not_forum`, `dispute_forum`). Las demás reglas límite (un límite igual, un contrato sin límite) siguen dentro de
`liability_cap`.

### F9 — Sin README; sorpresas para el revisor (baja, confirmado)

El caso no tenía un README con notas de realismo, líneas base o el techo. El docstring decía que la coincidencia por
palabras clave pasa cosas por alto, mientras que ese mismo buscador de palabras clave definía la calidad 1.0. La
referencia perdía 11 aciertos por la propia regla del cliente, y la fila del catálogo no coincidía con la regla
flexibilizable implementada.

**Estado:** corregido en este cambio — README.md cubre el cliente y los datos, las reglas, las trampas de cada
cláusula, las situaciones presentes, el papel de la vía rápida, los errores de la referencia, las cifras de la línea
base y del margen de mejora, y la práctica detrás de los criterios. El docstring dice ahora que la referencia es la
lista de comprobación literal. Las 11 omisiones desaparecen con F2. La fila del catálogo en cases/README.md queda fuera
del directorio de este caso y sigue abierta (véase F2).

**Actualización (semillas de reglas):** README.md se ha reescrito para las configuraciones: niveles, parámetros con
sus conjuntos de candidatos, las semillas de reglas públicas con cada diccionario sorteado y sus cifras, las preguntas
clave por nivel y el margen de mejora por nivel. README.<lang>.md y REVIEW.<lang>.md siguen describiendo el caso sin
configuraciones hasta que se vuelvan a traducir.

**Línea base:** firma todos los contratos tal como están (sin incidencias, decisión `sign`), con un objetivo de 0.1125
frente al 0.8825 de la referencia con la semilla de mundo 20261026. Con las semillas de mundo 1–3 obtiene
0.0750 / 0.1200 / 0.0900 frente a 0.8485 / 0.8301 / 0.7793. Es válida en todas partes: respeta la vía rápida y solo
acierta los contratos cuya respuesta correcta es `sign` (15 de 40 con la semilla guardada).

**Línea base (semillas de reglas):** sin cambios (firma todos los contratos tal como están) y válida en todas las
configuraciones. En las semillas de reglas públicas, con la semilla guardada, obtiene 0.0000–0.0750 frente al
0.8214–0.8942 de la referencia; con los sorteos estrictos casi todos los contratos puntuados necesitan cambios, así que
solo puntúa por las pocas decisiones `sign` acertadas.

## Semillas de reglas

El caso tenía una sola solución correcta. Ahora tiene tres niveles y ocho parámetros de reglas sorteados por semillas
de reglas (DESIGN.md, Settings); las semillas de reglas públicas son 6, 11 y 49, que entre las tres sortean todos los
candidatos de todos los conjuntos en todos los niveles. Los datos y request.md son idénticos byte a byte en todas las
configuraciones.

- **Niveles.** easy: los cuatro puntos que se leen en la cláusula (`LIABILITY_CAP` sin los límites de N meses,
  `GOVERNING_LAW` solo por la ley, `PAYMENT_TERMS`, `INDEMNITY`), críticas `LIABILITY_CAP` e `INDEMNITY`, y los códigos
  ajenos a la ronda se ignoran. medium: los siete puntos, con los límites de N meses (N/12), el preaviso de renovación
  (meses a 30 días), la protección de datos por categoría, el desistimiento por encima de un importe y el foro. Ninguno
  de los dos puntúa los contratos en el modelo del proveedor, los modificados ni el del correo (siguen necesitando una
  entrada), y ninguno tiene vía rápida. hard: los 40 contratos, los registros de modificación, los datos personales de
  los clientes de la empresa, el correo y la vía rápida.
- **Parámetros.** `cap_multiple` (1, 1.5, 2), `governing_law` (CH_SG, CH_SG_EW, SG), `payment_days` (45, 60, 30) y
  `reject_at` (2, 1) en todos los niveles; `renewal_notice_days` (60, 90, 45), `dp_categories` (TI; TI y marketing) y
  `tfc_above` (150,000, 100,000, 250,000) desde medium; `fast_track_below` (20,000, 10,000, 25,000) en hard. Un
  parámetro que un nivel no usa tiene un solo candidato en él. No hacen falta `admissible` ni `derive_params`; los
  números que muestran los textos se redactan en cada idioma mediante labels (150.000 en es).
- **Generador.** Los importes salen de franjas entre candidatos consecutivos de la vía rápida y del desistimiento, más
  un contrato exactamente en cada candidato (umbrales estrictos); los límites fijos caen en 1×, 1.5× y 2× y entre ellos;
  los plazos de pago añaden 15 días y los límites de N meses, 18 meses; para que cada candidato cambie respuestas en
  contratos que ninguna vía rápida retira, tres contratos de TI y tres de marketing carecen de cláusula de protección de
  datos, tres renovaciones automáticas indican cada plazo de preaviso tal cual en días, cada franja de desistimiento
  tiene un contrato sin ese derecho y cuatro contratos separan la ley y el foro. Las situaciones (modificaciones,
  correo, datos personales de los clientes) se añaden al final. Los sorteos, la referencia y la puntuación leen la
  configuración solo a través del `Setting` que reciben.
- **Textos.** requirements.md y targets.yaml en los cinco idiomas llevan los parámetros como `{{name}}` y bloques por
  nivel; los archivos explainer.yaml tienen los tres niveles y las reglas con sus parámetros. La frase coreana de la vía
  rápida es la que proponía F7.
- **Comprobaciones.** `validate-case` se supera con las semillas de mundo 1–3 (y 1–12): la referencia es válida con
  calidad 1.0 y la línea base es válida y peor en las nueve configuraciones públicas, cada regla tiene un ejemplo que
  solo la incumple a ella (el de la vía rápida, solo en hard), y todos los parámetros influyen en la configuración hard
  de la primera semilla pública (el margen más estrecho entre las semillas públicas y las semillas de mundo 20261026 y
  1–3 es del 1.6%, para `tfc_above`).
- **Revisión de la conversión (corregido).** easy dice que los códigos ajenos a la ronda se ignoran («si los incluye, no
  los tendremos en cuenta»), pero `decision_consistency` los descartaba antes de comparar la decisión: una revisión que
  indicaba `AUTO_RENEWAL` en un contrato sin ninguna incidencia de la ronda y decidía `negotiate`, como dice «`negotiate`
  si tiene alguna incidencia», era inválida. La comprobación acepta ahora una decisión que siga las incidencias sin los
  códigos ajenos a la ronda o con ellos; la F1 de incidencias y la exactitud de decisiones no cambian, así que todas las
  cifras guardadas siguen igual.
- **Resuelto:** F4. **En parte:** F3 (un hecho de decisión sorteado), F5 (tres situaciones), F7 (dos cadenas), F8
  (preguntas clave por nivel). **Sigue abierto:** F1, F6 (más denso), el resto de F3, F5 y F7, y la fila del catálogo de
  F2, fuera de este directorio.
