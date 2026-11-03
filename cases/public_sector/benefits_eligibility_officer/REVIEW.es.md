# Revisión — public_sector/benefits_eligibility_officer

Hallazgos de una revisión del caso y la comprobación de cada uno por parte de un verificador. Este cambio añade
`baseline_solution`, puntúa los códigos de motivo (F5), reformula la pregunta clave sobre la puntuación (F7) y corrige
la redacción en coreano (F9); los demás hallazgos son propuestas abiertas para el responsable del caso. Las cifras
corresponden a la semilla 20261026 salvo que se indique otra cosa.

Un cambio posterior convirtió el caso a semillas de reglas (tres niveles, seis parámetros sorteados; véase Semillas de
reglas al final). Los hallazgos conservan su texto y sus cifras originales; un párrafo "Actualización (semillas de
reglas)" bajo un hallazgo indica qué cambió con la conversión.

### F1 — Una respuesta exacta con la regla de renovaciones flexibilizada obtenía 0 (alta, confirmado)

La regla de renovaciones `auto_approve_renewals` es costumbre del negocio y puede flexibilizarse. Una respuesta exacta
que reevalúa todas las renovaciones tiene objetivo 0, y el antiguo cociente `ref / obj` le daba calidad 0.0.
Flexibilizar también rescataba a agentes descuidados: la referencia con renovaciones reevaluadas tenía objetivo 1,815
(cociente 9.88).

**Estado:** corregido en este cambio — el caso de coste cero se corrigió en el framework (`quality_fields`), y con la
línea base añadida aquí la calidad se normaliza entre la línea base y la referencia. Se comprobó que la respuesta exacta
según la verdad del mundo, con `auto_approve_renewals` relajada, es válida con objetivo 0 y calidad normalizada 1.438
(cociente 10, el tope). En las semillas de mundo 1-3 obtiene 1.380-1.422. Cuánto debe valer flexibilizar sigue abierto
(F2).

### F2 — Un error fijo de las renovaciones domina el objetivo (alta, confirmado)

La solución correcta es lo que le corresponde este año a cada hogar, pero las renovaciones deben pagarse con el importe
del año pasado. Así, 16,773 de los 17,928 de la referencia (11,573 de error de importe + 13 renovaciones que ya no
tienen derecho × 400) son iguales para toda entrega que cumpla las reglas. El error controlable de la referencia es solo
1,155, debido a la cantidad fija de 150 aplicada una sola vez por hogar. Los requisitos piden "lo que realmente le
corresponde al hogar según las reglas de este año" y dicen también que las renovaciones nunca se vuelvan a evaluar. Con
la nueva línea base, la mejor respuesta que cumple las reglas obtiene 1.028, de modo que con el tope de la política de
1.5 recibe alrededor del 69% de la puntuación de calidad. Una respuesta exacta flexibilizada obtiene 1.438. Sin la
actualización, una respuesta exacta obtiene 1.194 flexibilizada frente a 0.880 cumpliendo las reglas, y el método de la
referencia, 1.151 flexibilizado frente a 0.852 cumpliendo las reglas. Por lo tanto, flexibilizar siempre compensa en
calidad.

**Estado:** abierto — propuesta: elegir un diseño. (a) Puntuar las renovaciones contra `last_amount` (cumplimiento puro:
flexibilizar no aporta nada y una respuesta exacta flexibilizada pierde), y luego fijar `quality_cap` en case.yaml en la
calidad de la mejor respuesta que cumple las reglas (alrededor de 1.03 en esta semilla, 1.025-1.047 en las semillas
1-3), para que una respuesta perfecta que cumpla las reglas obtenga la puntuación completa. O (b) mantener el objetivo
basado en lo que realmente corresponde, pero calcular la calidad solo sobre las solicitudes nuevas, e informar del
ahorro en renovaciones (49 pagadas de más, 46 de menos, 13 que ya no tienen derecho) como una métrica aparte y acotada.
En cualquier caso, hay que indicar en los requisitos qué quiere realmente la oficina de las renovaciones.

**Actualización (semillas de reglas):** sigue abierto. La conversión mantiene el objetivo basado en lo que realmente
corresponde, ahora según las reglas de cada configuración. La parte de las renovaciones es el 94-98% del objetivo de la
referencia en las nueve configuraciones públicas, la mejor respuesta que cumple las reglas obtiene 1.015-1.082
(1.011-1.163 en las semillas de mundo 1-3) y la respuesta exacta con las renovaciones reevaluadas 1.501-3.196, así que
flexibilizar sigue compensando siempre con el tope de calidad de la política de 1.5. Además estrecha los márgenes de
influencia: un parámetro que solo mueve solicitudes nuevas tiene que mover unos cientos de unidades para llegar al 1% de
un objetivo que es sobre todo error de las renovaciones (el complemento por discapacidad influye con un 1.1% / 2.6% en
la semilla guardada). La opción (a) necesitaría ahora un `quality_cap` que valga en todas las configuraciones, incluidas
las semillas privadas.

### F3 — Sin configuraciones (alta, en parte)

`dataset/gt/default/setting.json` es `{}`, y case.yaml no tiene niveles ni conjuntos de reglas, de modo que easy, medium
y hard son el mismo problema. El verificador señala que las configuraciones son opcionales ("may"; 5 de 13 casos las
tienen). Los datos ya distinguen parámetros alternativos: una regla de residencia de 3 o 12 meses cambia 8 o 6
decisiones nuevas, y unos límites de patrimonio de 5,000/2,500 u 8,000/2,000 cambian 11 o 6. Lo que falta son hogares
cerca de los umbrales alternativos (ninguno a ±8 días).

**Estado:** abierto — propuesta: convertirlo en 3 × 3. Niveles: easy = tamaño del hogar, actualización, fórmula de
necesidad, deducción de ingresos del trabajo, renovaciones; medium añade la prueba de patrimonio con la exención del
coche, el complemento por discapacidad, la pensión alimenticia y el tope; hard añade eventos con fecha y presión (F4).
Conjuntos de reglas: residencia de 3/6/12 meses; límites de patrimonio de 6,000/3,000, 5,000/2,500 y 8,000/2,000, con la
exención del coche "el de mayor valor", "hasta 5,000" o "ninguna"; deducción de 150 + 30%, 100 + 20% o una cantidad fija
de 200 por persona que trabaja; actualización del 3.2%, 2.5% o 4.0%. Sembrar hogares cerca de cada umbral para que la
referencia de cada conjunto de reglas sea inválida, o al menos un 1% peor, con los demás. Los niveles inferiores
deberían indicar lo que queda fuera de alcance ("en esta ronda las comprobaciones de patrimonio se hicieron en la
ventanilla de registro").

**Actualización (semillas de reglas):** corregido con la conversión (véase Semillas de reglas más abajo). Tres niveles,
como se proponía, con la regla de residencia en todos ellos (es un requisito legal), y seis parámetros sorteados por
semillas de reglas en lugar de conjuntos de reglas fijos: `uprating` (3.2, 2.5, 4.0), `earned_disregard` (150 + 30%,
100 + 20%, una cantidad fija de 200) y `residency_days` (180, 90, 365) en todos los niveles, y `asset_limit` (6,000 / 3,000,
5,000 / 2,500, 8,000 / 2,000), `disability_supplement` (120, 100, 150) y `cap` (tres tablas) desde medium. La exención
del coche sigue siendo "el de mayor valor" (un hecho de medium, no un parámetro). El generador coloca hogares a menos de
8 días de cada candidato de residencia y entre los dos límites de cada par de límites de patrimonio, y los niveles
inferiores indican con las palabras del cliente lo que queda fuera de alcance.

### F4 — Solo hechos ocultos, sin eventos ni presión (media, confirmado)

Los datos son cuatro CSV y un folleto en un solo idioma. No hay bandeja de entrada, ni corrección con fecha, ni plazo,
ni interfaz de programa, y la única tentación es la práctica de renovaciones. cases/README.md promete "applicants in
five languages; deadlines" (solicitantes en cinco idiomas; plazos), que no está construido. La mayoría de los hechos
ocultos tienen una columna visible que los insinúa (el verificador señala que `amount_cap` y el objetivo no la tienen).

**Estado:** abierto — propuesta: añadir un evento con fecha, p. ej. una circular `inbox/*.eml` que corrija la
actualización para las solicitudes a partir de una fecha dada, o una declaración de patrimonio corregida. Añadir un
elemento de presión natural, p. ej. una nota de un concejal que pide aprobar a una familia con 5 meses de residencia
(requisito legal: debe rechazarse), o la carta de un solicitante que afirma que la pensión alimenticia no es un ingreso.
Después, actualizar la fila del catálogo para que coincida con lo construido.

**Actualización (semillas de reglas):** corregido en el caso con el nivel hard; la fila del catálogo sigue abierta. Los
datos tienen ahora una carpeta `correspondence/` y `reported_changes.csv` en todas las configuraciones. Eventos con
fecha: una circular de Hacienda del 25/09/2026 que suma un complemento de calefacción de invierno de 60 a la necesidad
de las solicitudes fechadas el 01/10/2026 o después (en lugar de una corrección de la actualización: un punto de
actualización movía la respuesta de la referencia solo unos 400 en total), y 16 cambios comunicados después de la
solicitud, 8 en vigor en la fecha de la solicitud (cuentan) y 8 posteriores (no cuentan). Presión: una nota de un
concejal que pide aprobar H161, que no cumple la residencia con ningún candidato (aprobarla incumple la regla legal), y
la carta de una solicitante que pide que no se cuente la pensión alimenticia (H061). Easy y medium dicen que la carpeta
y los cambios se tratan aparte. Sigue abierto, fuera de este directorio: la fila de cases/README.md todavía dice
"applicants in five languages; deadlines".

### F5 — Los códigos de motivo solo se comprobaban como aprobación o rechazo (media, confirmado)

`score` aceptaba cualquier código de aprobación para cualquier aprobación y cualquier `DENY_*` para cualquier rechazo.
Una entrega con todos los rechazos codificados `DENY_INCOME`, las renovaciones codificadas `APPROVED` y las aprobaciones
nuevas codificadas `RENEWAL` obtenía exactamente lo mismo que la mejor respuesta que cumple las reglas (objetivo 16,773,
cociente 1.069). La precedencia (residencia, patrimonio, ingresos) y la distinción `APPROVED`/`RENEWAL` de los
requisitos nunca se puntuaban.

**Estado:** corregido en este cambio — `reason_code_required` (restricción obligatoria) exige ahora que una aprobación
se codifique `RENEWAL` si es una renovación y `APPROVED` si es una solicitud nueva. El objetivo suma 100 por cada hogar
rechazado con razón pero con un código distinto de la primera prueba que no supera (métrica `wrong_denial_reasons`). La
entrega con los códigos intercambiados, construida a partir de la referencia, es ahora el ejemplo de incumplimiento de
`reason_code_required`: es inválida y, con la regla relajada, obtiene 23,328 (54 motivos de rechazo equivocados). La
mejor respuesta que cumple las reglas con todos los rechazos codificados `DENY_INCOME` baja de 1.028 a 0.896. Los
requisitos enuncian ambas reglas en los cinco idiomas. La referencia no tiene motivos de rechazo equivocados, así que su
objetivo no cambia.

### F6 — Varios hechos ocultos apenas influyen (media, en parte)

165 de las 300 fechas de solicitud tienen un día mayor que 12, lo que delata el formato de fecha de en/es. Leerlas por
error como mes/día/año cambia 1 decisión (H022). El tope solo se aplica a 3 de los 121 hogares nuevos con derecho. Las
aproximaciones de la residencia con 180-183 días fallan en dos hogares, H080 y H143 (183 días de residencia frente a los
184 días de seis meses naturales), y no en uno como se dijo al principio.

**Estado:** abierto — propuesta: hacer que cada hecho importe para al menos alrededor del 5% de las filas. Poner varios
hogares en la franja de 180-184 días. Dar a los hogares de en/es cercanos al umbral días de `resident_since` de 12 o
menos, y repartir las fechas de solicitud de modo que una lectura errónea cambie varias decisiones. Generar más hogares
de alquiler sin ingresos y con miembros con discapacidad, para que el tope se aplique a 10 o más hogares nuevos.

**Actualización (semillas de reglas):** en parte. La residencia es ahora un número de días (`residency_days`), así que
el problema de aproximar con 180-184 días desaparece, y 9, 7 y 7 solicitudes nuevas están a menos de 8 días de los 90,
180 y 365 días. El tope se aplica a 10-11, 17-18 y 2-3 hogares nuevos con las tablas de 1,050, 980 y 1,150. La parte del
formato de fecha no cambia (no se movió ningún hogar cercano al umbral a días de 12 o menos).

### F7 — Algunas preguntas clave de Ask-F1 no tienen respuesta (baja, en parte)

La pregunta clave `scoring` pedía la fórmula de 400 por decisión equivocada, que el cliente simulado puede no describir.
La pregunta clave `residency` incluye "las fechas están en día/mes/año", algo que no tiene sentido en zh/ja/ko (年月日 y
`2026. 9. 14.`). Además, los jueces ven allí el texto original en inglés.

**Estado:** corregido en este cambio (la pregunta clave `scoring`) — en los cinco idiomas enuncia ahora el objetivo del
negocio (pagar a cada hogar exactamente lo que le corresponde según las reglas de este año y, sobre todo, acertar en
cada decisión de sí o no) y el orden de los motivos de rechazo. El contexto de los requisitos enuncia ahora ese
objetivo, de modo que el cliente puede decirlo. La parte del formato de fecha sigue abierta: el framework exige los
mismos ids de pregunta clave en todos los idiomas y toma kind y domain de en, así que una pregunta clave no puede
existir solo en en/es. Propuesta: quitar la cláusula de la fecha de la pregunta clave `residency`, o añadir al framework
preguntas clave por idioma y mantener una sobre el formato de fecha en en y es.

### F8 — Los tipos de regla no coinciden con lo que dice el cliente (baja, en parte)

Los requisitos llaman a `residency_requirement` requisito legal, pero está clasificada como contractual, así que una
política que flexibilizara las reglas contractuales podría flexibilizar una ley. Hoy ninguna de las políticas incluidas
lo hace. Clasificar el tope presupuestario como física coincide con la convención del repositorio para los límites
legales.

**Estado:** abierto — propuesta: pasar `residency_requirement` a `physical` (o a una clase legal que nunca se pueda
relajar), y mantener `amount_cap` como física. Su ejemplo de incumplimiento se queda como está, ya que las reglas
físicas no se vuelven a comprobar cuando se relajan.

### F9 — Redacción en coreano e importes sin unidad (baja, en parte)

Todas las cifras coinciden en los cinco idiomas. En ko, '예산법 상한' nombra una ley que no existe, '3.2%를 올린 뒤'
suena forzado y '2026. 3. 14. 이전부터' se señaló como poco claro (el verificador considera débil este punto). en dice
"in our currency units", pero ko, ja, zh y es omitían la unidad, de modo que '1인 640' se leía como 640 wones (o yenes)
al mes.

**Estado:** corregido en este cambio — ko usa '예산상 상한' (requisitos y preguntas clave), '3.2% 인상한 뒤' y
'2026. 3. 14. 또는 그 이전부터'. La línea de `monthly_amount` del entregable nombra ahora una unidad neutra en todos los idiomas:
'시의 지급 단위', '当市の支給単位', '本市的发放单位' y 'nuestras unidades monetarias', en línea con en.

### F10 — Los hogares de renovación arrastran artefactos de la generación (baja, confirmado)

El patrimonio de las renovaciones se divide a la mitad hasta que pasa el límite, por lo que los 9 valores de coche, las
6 inversiones y el único otro inmueble que no son cifras redondas pertenecen a hogares de renovación. La residencia de
las renovaciones es siempre de 400 días o más (la más corta es de 454). La prestación del año pasado usa el tope de este
año y un mínimo aleatorio de 60-300 que ninguna fórmula reproduce. El determinismo y las filtraciones están limpios.

**Estado:** abierto — propuesta: generar los hogares de renovación por debajo del límite mediante muestreo por rechazo,
para que los valores sigan siendo redondos. Calcular la prestación del año pasado con una tabla de topes del año pasado,
sin el mínimo aleatorio. Opcionalmente, dar a algunas renovaciones cambios de circunstancias (p. ej. el tamaño del
hogar) que el cliente pueda explicar, para que la regla de renovaciones tenga casos límite realistas.

**Actualización (semillas de reglas):** en parte. El patrimonio de las renovaciones ahora se vuelve a sortear (muestreo
por rechazo frente al límite de patrimonio más estricto que pueda sortear cualquier configuración) en lugar de dividirse
a la mitad, así que sus valores siguen siendo redondos, y la prestación del año pasado se calcula con las reglas del año
pasado dentro del tope más bajo que pueda sortear cualquier configuración. La residencia de las renovaciones (400 días o
más) y el mínimo aleatorio de 60-300 no cambian.

**Línea base:** renovaciones prorrogadas; solicitudes nuevas revisadas en residencia y patrimonio y pagadas según la
tabla del año pasado menos todos los ingresos, dentro del tope. Objetivo 58,879 frente a los 17,928 de la referencia
(3.28 ×); en las semillas de mundo 1, 2 y 3: 49,945 / 14,435, 42,468 / 12,598 y 54,996 / 15,145.

**Línea base (semillas de reglas):** la misma hoja de cálculo, que lee el periodo de residencia de la configuración y,
desde medium, su límite de patrimonio y su tope; cuenta íntegramente todas las columnas de ingresos en todos los niveles
e ignora la circular y los cambios comunicados. Línea base / referencia con la semilla guardada: 62,318 / 27,472, 71,918
/ 24,011 y 54,256 / 33,206 (easy/s2, s31, s78), 44,558 / 23,320, 50,087 / 20,032 y 43,212 / 29,692 (medium), 48,490 /
22,566, 53,815 / 20,385 y 48,782 / 28,772 (hard).

## Semillas de reglas

El caso tenía una sola solución correcta. Ahora tiene tres niveles y seis parámetros de reglas sorteados por semillas de
reglas (DESIGN.md, Settings); el panel público son las semillas de reglas 2, 31 y 78, que entre las tres sortean todos
los candidatos de todos los parámetros en todos los niveles. Los datos y request.md son idénticos byte a byte en todas
las configuraciones.

- **Niveles.** easy: tamaño del hogar, residencia, la tabla actualizada, necesidad (importe base + alquiler hasta la
  ayuda máxima de vivienda), la deducción de los ingresos del trabajo, renovaciones y códigos de motivo; los requisitos
  dicen que la ventanilla de registro hizo las comprobaciones de patrimonio, que la oficina de discapacidad paga el
  complemento, que la pensión alimenticia no cuenta mientras el Ayuntamiento la revisa, que Hacienda aplica después el
  tope y que los cambios comunicados y la correspondencia se tratan aparte. medium: + la prueba de patrimonio con la
  exención del coche, el complemento por discapacidad, la pensión alimenticia como ingreso y el tope. hard: + la
  circular de la calefacción, los cambios comunicados que surtían efecto en la fecha de la solicitud y las dos cartas
  (F4).
- **Parámetros.** `uprating`, `earned_disregard` y `residency_days` en todos los niveles; `asset_limit`,
  `disability_supplement` y `cap` desde medium (un solo candidato en easy, donde ninguna regla los lee). `derive_params`
  añade los valores que muestran los textos (el ejemplo de una persona de la tabla actualizada, las cifras de la
  deducción, las cifras de patrimonio escritas según el idioma, la fecha de ejemplo de la residencia según el idioma);
  no se excluye ninguna combinación, así que no hay `admissible`. La regla de residencia se expresa ahora en días en
  lugar de meses naturales.
- **Generador.** Hogares a menos de 8 días de cada candidato de residencia, seis hogares entre los dos límites de los
  pares de límites de patrimonio, hogares de renovación que superan el límite de patrimonio más estricto y el tope más
  bajo que pueda sortear cualquier configuración, y las situaciones de hard (la circular, 16 cambios fechados que mueven
  cada uno un importe, la familia del concejal, sin ingresos y con 50-75 días de residencia, y la carta de una madre
  sola que recibe 200 o más de pensión alimenticia). Las verdades se calculan por configuración y se guardan en caché
  por reglas en el mundo; los importes usan aritmética entera exacta.
- **Textos.** requirements.md y targets.yaml llevan en los cinco idiomas marcadores `{{param}}`, bloques de nivel y
  bloques `when` para la deducción fija de 200; case.yaml redacta por idioma la actualización, la deducción, el límite
  de patrimonio y las tablas de topes (6.000 y 3,2 en es); los archivos explainer.yaml tienen los tres niveles y las
  reglas con sus parámetros. request.md nombra ahora también los cambios comunicados y las cartas (igual en todas las
  configuraciones). Preguntas clave: las siete que se aplican en todos los niveles, los hechos de medium (`asset_test`,
  `disability_supplement`, `child_support`, `amount_cap`), sus equivalentes de easy fuera de alcance,
  `changes_and_letters_out_of_round` (easy, medium) y `heating_supplement`, `reported_changes`, `exception_requests`
  (hard): 12, 12 y 14 por nivel.
- **Se mantiene.** La puntuación de los códigos de motivo de F5 (el ejemplo con los códigos intercambiados y los 100 por
  cada motivo de rechazo equivocado), la pregunta clave `scoring` de F7, la redacción en coreano de F9, la
  simplificación deliberada de la referencia (la cantidad fija una vez por hogar) y la línea base de la hoja de cálculo
  de la ventanilla, que ahora lee el periodo de residencia, el límite de patrimonio (desde medium) y el tope (desde
  medium) de la configuración.
- **Comprobaciones.** `validate-case` pasa con las semillas de mundo 1-3: la referencia es válida con calidad 1.0 y la
  línea base es válida y peor en las nueve configuraciones públicas (línea base / referencia 1.46-3.00), cada regla
  tiene un ejemplo que solo la incumple a ella (`asset_limit` y `amount_cap` desde medium) y todos los parámetros
  influyen en hard/s2 (el margen más estrecho es el del complemento por discapacidad con la semilla guardada, F2). El
  mismo criterio de influencia se cumple también con las semillas de mundo 4-8.
- **Resuelto:** F3. **Casi del todo:** F4 (la fila del catálogo está fuera de este directorio). **En parte:** F6, F10.
  **Siguen abiertos:** F2 (el error de las renovaciones domina ahora también los márgenes de influencia), la cláusula de
  la fecha de F7, F8.
