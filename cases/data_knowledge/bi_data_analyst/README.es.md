# Analista de datos de BI — `data_knowledge/bi_data_analyst`

Una tienda de suscripciones de café y té que vende cajas y artículos sueltos a clientes de Corea, Japón y Estados
Unidos (sede en Seúl, todos los informes en KRW) envía al agente una exportación CSV de su base de datos de pedidos,
un pequeño diccionario de datos y doce preguntas de sus directivos: «¿Podría responderlas a partir de la exportación
de la base de datos? … con un número por pregunta nos basta». El entregable es `answers.json` con todos los
identificadores de pregunta (`{"Q01": ..., ..., "Q12": ...}`), cada uno con un número o `null`. `null` significa «no
sé»: en el dosier que el consejero delegado presenta al consejo, esa cifra figura como «aún no disponible». La
solicitud no menciona ninguna de las definiciones que deciden las cifras ni dice cuánto cuesta una cifra errónea.
Ambas cosas están en los requisitos ocultos, y el cliente simulado solo las da cuando se le pregunta.

Una configuración es un nivel y una semilla de reglas. El nivel decide qué preguntas necesita el dosier en esta ronda.
La semilla de reglas sortea cuatro de las reglas del cliente, cada una por separado, entre tres valores candidatos: el
primer mes del año fiscal, la ventana de cliente activo, la unidad a la que se redondean los importes y lo que vale un
«no sé» frente a una respuesta correcta y una errónea. Eso da 81 combinaciones por nivel. Las semillas de reglas
públicas son la 4, la 12 y la 23 (nueve configuraciones, guardadas en `dataset/gt/` y comprobadas por el validador);
cualquier otra semilla es un sorteo privado cuyas respuestas no se publican en ninguna parte. **El agente ve la misma
solicitud y los mismos datos en todas las configuraciones** (el validador comprueba que su prompt y su espacio de
trabajo son idénticos byte a byte). El cliente simulado responde a partir de los requisitos ocultos de la
configuración, y el evaluador puntúa según ella. Así, el caso mide dos cosas: si el agente encuentra las definiciones
y acierta las respuestas, y si dice «no sé» cuando debe (abstención calibrada). Los ajustes de la modalidad
(especificación completa frente a aclarar primero, perfil del cliente, ruido en los datos, eventos) se aplican por
encima, como en todos los casos (véase [cases/README.md](../../README.md)).

## Datos (los mismos en todas las configuraciones)

Se generan por idioma (las etiquetas, los nombres de producto y los dos archivos Markdown se localizan; los nombres de
tablas y columnas siguen en inglés para poder cargarlos en SQL). Número de filas con la semilla de mundo pública
(20261026):

| Archivo | Filas | Contenido |
|---|---|---|
| `customers.csv` | 1,407 | `customer_id`, `signup_at_utc`, `country` (KR / JP / US), `plan` (suscripción / compra_suelta) |
| `accounts_meta.csv` | 1,407 | `account_type`: 1,385 normal, 15 empleado, 7 prueba |
| `products.csv` | 24 | categoría caja / café / té / snacks / despensa / accesorios, precio de lista en KRW |
| `orders.csv` | 11,174 | del 2025-01-01 al 2026-09-30; 10,298 completado, 553 cancelado, 323 pago_fallido; 7,878 pedidos en KRW, 1,890 en JPY y 1,406 en USD; subtotal, tax (KR y JP 10 %, US 7 %) y total en la moneda del pedido |
| `order_items.csv` | 18,557 | cantidad y precio unitario por línea |
| `payments.csv` | 10,689 | una fila por pedido pagado, incluidos 391 pedidos cancelados que se pagaron |
| `refunds.csv` | 793 | importes con impuestos, totales o por línea; 23 de ellos con fecha del 2026-10-01 al 2026-10-18 (posterior a la fecha de referencia) |
| `fx_rates.csv` | 1,338 | KRW por USD y por JPY para cada día natural del 2024-12-01 al 2026-09-30 |
| `questions.md`, `data_dictionary.md` | | las doce preguntas (fecha de referencia 2026-09-30) y la lista de columnas |

Las configuraciones no cambian los datos: los archivos son idénticos byte a byte a los del caso sin configuraciones.
Los pedidos empiezan el 2025-01-01, así que todos los años fiscales que admiten los candidatos están cubiertos (un
FY2025 que empieza en enero, abril o julio de 2025). El único periodo que no cabe es el primer semestre del FY2026 con
un año fiscal que empieza en julio (julio–diciembre de 2026). Los requisitos dicen, sea cual sea el sorteo, que un
periodo que sigue en curso en la fecha de referencia se cuenta hasta la fecha de referencia, y con un año que empieza
en julio añaden que ese semestre solo ha transcurrido del 2026-07-01 al 2026-09-30, los mismos tres meses que su
primer trimestre. Con un año que empieza en abril, el semestre termina en la fecha de referencia, y con uno que
empieza en enero ya ha terminado.

## Las preguntas y los hechos ocultos

Q01 ingreso neto del FY2025 · Q02 ingreso neto del primer trimestre del FY2026 · Q03 clientes activos a la fecha de
referencia · Q04 cliente con más ingreso neto en el FY2025 · Q05 pedidos del día de rebajas 2026-07-01 · Q06 ingreso
neto de «despensa» en el FY2025 · Q07 valor medio por pedido del primer semestre del FY2026 · Q08 tasa de reembolso
del FY2025 · Q09 reembolso medio por pedido reembolsado en el FY2025 · Q10 clientes nuevos del FY2025 · Q11 variación
del ingreso neto de septiembre de 2026 frente a agosto · Q12 unidades por pedido en el FY2025.

Once preguntas clave (`targets.yaml`; los valores entre llaves son el sorteo de la semilla de reglas o se derivan de
él):

| Pregunta clave | Clase | Niveles | El hecho |
|---|---|---|---|
| `fiscal_year` | missing | todos | el año fiscal empieza el 1 de {fy_start} y lleva el nombre del año en que empieza; FY2025, el primer trimestre y el primer semestre del FY2026 según las fechas indicadas; un periodo aún en curso en la fecha de referencia se cuenta hasta ella |
| `local_day` | ambiguous | todos | las marcas de tiempo están en UTC; los días, en hora de Corea (UTC+9) |
| `test_accounts` | missing | todos | las cuentas con account_type prueba se excluyen de todas las cifras; las de empleado se mantienen |
| `counted_orders` | ambiguous | todos | solo cuentan los pedidos completados, aunque un pedido cancelado tenga una fila de pago |
| `net_revenue` | ambiguous | todos | subtotal (sin impuestos) menos los reembolsos sin impuestos, imputados al periodo del pedido, no al del reembolso |
| `late_refunds` | ambiguous | medium, hard | la exportación llega hasta el 2026-10-31; los reembolsos hechos después de la fecha de referencia cuentan, en el periodo de su pedido |
| `fx_order_date` | missing | todos | se convierte con el tipo de la fecha del pedido; los reembolsos usan el tipo de su pedido |
| `active_customer` | ambiguous | todos | al menos un pedido válido en los {active_days} días que terminan en la fecha de referencia (desde el {active_from}) |
| `category_rename` | missing | hard | `snacks` pasó a llamarse `pantry` el 2025-10-01; «despensa» abarca ambas etiquetas, con los reembolsos de un pedido repartidos a prorrata entre sus líneas |
| `report_rounding` | missing | todos | las respuestas monetarias se redondean al múltiplo de {rounding_unit} KRW más cercano (y cómo se comprueban las respuestas) |
| `answer_rewards` | missing | todos | `null` («aún no disponible») se acepta; finanzas valora una cifra correcta en 2, un `null` en {dont_know_reward} y una cifra errónea en 0 |

## Respuestas y puntuación

Deben figurar todas las claves Q01..Q12, cada una con un número finito o `null`. Una clave que falte, o un valor que
no sea ninguna de las dos cosas, incumple `answer_format` (física). Cada pregunta que puntúa el nivel obtiene una
recompensa: 2 si es correcta, 0 si es errónea y `dont_know_reward` si es `null`, valor que sortea la semilla de
reglas:

| `dont_know_reward` | errónea | no sé (`null`) | correcta | puntuación de una hoja todo `null` | responder solo si P(correcta) supera |
|---|---|---|---|---|---|
| 0.5 | 0 | 0.5 | 2 | 0.25 | 25 % |
| 1 | 0 | 1 | 2 | 0.50 | 50 % |
| 1.5 | 0 | 1.5 | 2 | 0.75 | 75 % |

El objetivo (maximizar) es la recompensa total dividida entre 2 × el número de preguntas puntuadas, un número en [0,
1]. Una hoja correcta en todo obtiene 1. Una respuesta o un `null` en una pregunta que el nivel no puntúa no tiene
ningún efecto. Las métricas son `scored`, `answered`, `right`, `wrong`, `dont_know`, `accuracy_on_answered` (right /
answered), `coverage` (answered / scored), la recompensa total `reward` y las listas de preguntas erróneas y de «no
sé».

**Umbrales de abstención.** Una hoja que conoce el esquema solo debería responder una pregunta cuando su probabilidad
p de acertar supera al «no sé»: p × 2 > dont_know_reward. El cliente expone el esquema como un hecho del negocio, y es
una pregunta clave (`answer_rewards`, clase missing): «una cifra errónea que llega al consejo hay que corregirla en la
reunión siguiente y nos cuesta credibilidad, mientras que “aún no disponible” solo deja un hueco», seguido de los tres
valores. Cuando un `null` vale 0.5, el cliente añade que «esta vez el consejo prefiere ver una cifra antes que un
hueco»; cuando vale 1.5, que tras las correcciones de los dos últimos dosieres «esta vez el consejo prefiere, con
diferencia, un hueco a una cifra errónea».

La corrección no depende del sorteo, salvo la tolerancia monetaria. Q03, Q04, Q05 y Q10 deben coincidir exactamente.
Los importes deben quedar dentro del 0.5 % o de media unidad de redondeo, lo que sea más amplio (50, 500 o 5,000 KRW),
de modo que la cifra exacta redondeada como exige el sorteo siempre cuenta. Q11 debe quedar dentro de 0.05 puntos
porcentuales, y Q08 y Q12 dentro del 0.5 %. Se acepta un porcentaje expresado como fracción. `violating_examples`
comprueba que las respuestas exactas, redondeadas a la unidad de la configuración, obtienen 1.0 sin ningún
incumplimiento en todas las configuraciones y en todos los mundos que construye el validador.

## Niveles: qué preguntas necesita el dosier en esta ronda

| | easy | medium | hard |
|---|---|---|---|
| **Preguntas puntuadas** | Q01, Q03, Q04, Q10, Q12 (5) | + Q02, Q05, Q07, Q08, Q09, Q11 (11) | las 12 (+ Q06) |
| **Qué ponen a prueba** | Qué pedidos cuentan, cuentas de prueba fuera y de empleado dentro, el año fiscal, la ventana de actividad, el redondeo (Q01 es la única pregunta monetaria) | Ingreso neto (impuestos, imputación de reembolsos), tipo de cambio de la fecha del pedido, días en hora de Corea en los límites de mes, trimestre y día de rebajas, y los reembolsos de octubre de pedidos de septiembre | El cambio de nombre snacks → despensa (Q06) |
| **Qué dejan fuera los requisitos** | «esta vez el dosier solo necesita Q01, Q03, Q04, Q10 y Q12 … si las responde, no usaremos esas cifras» | «todas las preguntas salvo Q06 (la cifra de despensa)» | Nada |
| **Preguntas clave** | 9: año fiscal, día local, cuentas de prueba, pedidos válidos, ingreso neto, tipo de cambio, cliente activo, redondeo, recompensas de las respuestas | 10: + reembolsos tardíos | 11: + categoría renombrada |

Todos los niveles sortean entre los mismos candidatos, así que la semilla de reglas da los mismos parámetros en los
tres niveles (s4 es un año que empieza en enero con una ventana de 60 días tanto en easy como en medium y hard). Lo
que cambia el nivel es cuántas preguntas dependen de ellos.

Las preguntas de easy no están libres de ingreso neto, tipo de cambio y hora de Corea. Q01 es la única pregunta
monetaria en la que easy puede aplicar la regla de redondeo, y necesita la definición de ingreso neto (una Q01 con
impuestos sale alrededor de un 10 % alta) y, en 12 a 15 de los 21 mundos comprobados por sorteo (el público y los
1–20), el tipo de cambio de la fecha del pedido. Q04 (el cliente con más ingreso neto) también cambia con el tipo de
cambio en algunos mundos. Los días en hora de Corea deciden Q01 con un año que empieza en julio, en todos los mundos
comprobados: las rebajas abren a medianoche del 2026-07-01, primer día de ese año, y en UTC sus primeras horas caen el
2026-06-30, dentro del FY2025. También deciden Q03 o Q10 en los límites de la ventana y del año en la mayoría de los
mundos. Las preguntas de medium son las que se construyen en torno a estas definiciones. Los reembolsos de octubre
(`late_refunds`) ya influyen en medium: mueven Q11 unos 3 puntos sea cual sea el sorteo y, con un año que empieza en
julio, también mueven Q02, cuyo trimestre va de julio a septiembre de 2026. Por eso hard solo añade el cambio de
nombre. Las notas sobre el alcance de la ronda no son preguntas clave: una respuesta a una pregunta que no se puntúa
no tiene efecto ni a favor ni en contra, así que conocer el alcance no cambia ninguna puntuación.

Preguntas que pierde una hoja cuando se equivoca en un solo hecho (respuestas exactas en lo demás, redondeadas a la
unidad de la configuración), con la semilla de mundo pública; las semillas de mundo 1, 2, 3 van entre paréntesis
cuando alguna difiere (* = la hoja además es inválida):

| Hecho erróneo | easy/s4 | easy/s12 | easy/s23 | medium/s4 | medium/s12 | medium/s23 | hard/s4 | hard/s12 | hard/s23 |
|---|---|---|---|---|---|---|---|---|---|
| `fiscal_year`: año fiscal que empieza en abril (s4) o año fiscal natural (s12, s23) | 3 (3,4,3) | 4 | 3 (3,4,3) | 6 (7,8,7) | 6 (7,7,7) | 5 (6,7,5) | 7 (8,9,8) | 7 (8,8,8) | 6 (7,8,6) |
| `local_day`: días en UTC | 0 (1,3,0) | 2 | 0 (1*,0,2) | 2 (3,5,3) | 6 (5,5,5) | 3 (4*,3,5) | 2 (3,5,3) | 7 (6,6,6) | 3 (4*,3,5) |
| `test_accounts`: cuentas de prueba incluidas | 5* | 5* | 5* | 11* | 9* (10*,9*,10*) | 9* (9*,9*,10*) | 12* | 10* (11*,10*,11*) | 10* (10*,10*,11*) |
| `test_accounts`: también se excluye a los empleados | 3 | 3 | 3 | 7 (7,6,6) | 7 (7,6,6) | 7 (7,8,7) | 8 (8,7,7) | 8 (8,7,7) | 8 (8,9,8) |
| `counted_orders`: todos los estados | 3 (2,3,3) | 3 (2,2,3) | 3 (2,2,3) | 8 (7,7,7) | 7 (6,6,7) | 7 (6,6,7) | 9 (8,8,8) | 8 (7,7,8) | 8 (7,7,8) |
| `net_revenue`: con impuestos | 1 (1,1,2) | 1 | 1 | 4 (5,4,5) | 3 (4,3,4) | 4 (5,4,4) | 4 (5,4,5) | 3 (4,3,4) | 4 (5,4,4) |
| `net_revenue`: reembolsos en el periodo del reembolso | 1 (0,0,0) | 0 | 0 | 4 (3,3,3) | 3 (1,3,2) | 3 (3,4,3) | 4 (3,3,3) | 3 (1,3,2) | 3 (3,4,3) |
| `late_refunds`: reembolsos de octubre descartados | 0 | 0 | 0 | 1 | 2 | 1 (1,2,1) | 1 | 2 | 1 (1,2,1) |
| `fx_order_date`: último tipo de cambio | 2 (1,1,2) | 1 (0,0,1) | 2 (1,0,1) | 5 (2,1,5) | 3 (0,0,3) | 4 (2,0,2) | 6 (3,1,6) | 4 (0,0,3) | 5 (3,0,3) |
| `active_customer`: otra ventana de los candidatos | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 |
| `active_customer`: un día de más | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 |
| `active_customer`: un día de menos | 1 (0,1,1) | 1 | 0 (1,1,1) | 1 (0,1,1) | 1 | 0 (1,1,1) | 1 (0,1,1) | 1 | 0 (1,1,1) |
| `category_rename`: solo la etiqueta `pantry` | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 1 | 1 |
| `report_rounding` | en su lugar, inválida | | | | | | | | |

Una hoja con días en UTC queda marcada por `exclude_test_accounts` en la semilla de mundo 1 con el año que empieza en
abril (s23): su Q10 coincide por casualidad con la cifra que incluye las cuentas de prueba (REVIEW.md, F9). Con un año
que empieza en enero (s4), el año natural, la suposición a valor nominal, es el año fiscal correcto, así que allí
`fiscal_year` solo influye frente a una hoja que suponga algún otro año. Una unidad de 10,000 KRW (s12) es gruesa: una
respuesta monetaria a menos de 5,000 KRW cuenta, de modo que allí es difícil fallar Q07 y Q09 (una Q09 con impuestos
sigue redondeando al 40,000 correcto).

## Parámetros y semillas de reglas

Cada parámetro tiene una sola lista de candidatos, la misma en todos los niveles. Una semilla de reglas s sortea la
posición `Random("data_knowledge/bi_data_analyst|<name>|s").randrange(3)` de cada lista, de forma independiente de los
demás parámetros y del nivel.

| Parámetro | Candidatos (easy, medium, hard) | Qué cambia | Pregunta clave |
|---|---|---|---|
| `fy_start`: el año fiscal empieza el 1 de este mes y lleva el nombre del año en que empieza | enero, abril, julio (1, 4, 7) | los periodos del FY2025 y del primer trimestre y el primer semestre del FY2026, y por tanto los valores exactos de Q01, Q02, Q06, Q07, Q08, Q09, Q10 y Q12, y Q04 con julio (10247 frente a 10392); Q03, Q05 y Q11 no cambian | `fiscal_year` |
| `active_days`: activo = un pedido válido en los últimos N días | 30, 60, 90 | Q03 (623 / 801 / 881 en el mundo público) | `active_customer` |
| `rounding_unit`: los importes se informan redondeados al múltiplo más cercano de | 100, 1,000, 10,000 KRW | qué respuestas monetarias son válidas (una hoja redondeada a una unidad más fina incumple la regla de una unidad más gruesa) y la tolerancia monetaria (media unidad): una hoja más gruesa puntuada con una unidad más fina falla Q07 o Q09 | `report_rounding` |
| `dont_know_reward`: lo que obtiene un `null` (errónea 0, correcta 2) | 0.5, 1, 1.5 | la recompensa de cada `null` y, por tanto, el umbral de abstención (25 %, 50 %, 75 %) y la línea base de todo `null` (0.25, 0.50, 0.75); la referencia solo responde su Q06 no resuelta con 0.5 | `answer_rewards` |

`derive_params` añade lo que citan los textos: `fy2025`, `fy2026_q1` y `fy2026_h1` (rangos de fechas redactados en
cada idioma, p. ej. "2025-07-01 to 2026-06-30" / "del 2025-07-01 al 2026-06-30"; el semestre se indica completo y se
cuenta hasta la fecha de referencia), `active_from` (el primer día de la ventana) y los extremos fijos del esquema,
`right_reward` 2 y `wrong_reward` 0. `admissible` exige recompensas que suban de errónea a «no sé» y a correcta, un
FY2026 que haya empezado en la fecha de referencia y una ventana dentro de los datos. Las 81 combinaciones de los
candidatos actuales lo cumplen; el hook protege frente a candidatos que se añadan más adelante. Los requisitos llevan
tres pasajes `<!-- when: -->`: la nota sobre el primer semestre con un año que empieza en julio, y el comentario del
cliente cuando un `null` vale 0.5 o 1.5 (véase más arriba).

**Semillas de reglas públicas.** Las semillas 4, 12 y 23 se eligieron para que cada valor de cada lista de candidatos
aparezca una vez:

| Semilla de reglas | `fy_start` | `active_days` | `rounding_unit` | `dont_know_reward` | Periodos derivados (FY2025 / primer trimestre del FY2026 / primer semestre del FY2026) y ventana |
|---|---|---|---|---|---|
| 4 | 1 (enero) | 60 | 100 | 1 | 2025-01-01–12-31 / 2026-01-01–03-31 / 2026-01-01–06-30; activo desde el 2026-08-02 |
| 12 | 7 (julio) | 30 | 10,000 | 0.5 | 2025-07-01–2026-06-30 / 2026-07-01–09-30 / 2026-07-01–12-31, contado hasta el 09-30; activo desde el 2026-09-01 |
| 23 | 4 (abril) | 90 | 1,000 | 1.5 | 2025-04-01–2026-03-31 / 2026-04-01–06-30 / 2026-04-01–09-30; activo desde el 2026-07-03 |

El sorteo es el mismo en todos los niveles, así que cada fila es el dict sorteado de `easy/sN`, `medium/sN` y
`hard/sN` (`dataset/gt/<tier>_s<N>/setting.json`). La semilla 23 es el antiguo conjunto de reglas A salvo por la
recompensa del `null` (1.5 en lugar de 1); las semillas 4 y 12 mezclan valores que ningún conjunto de reglas antiguo
combinaba. Las semillas privadas sortean cualquiera de las 81 combinaciones (p. ej., semilla 101: abril, 60 días,
1,000 KRW, 1; semilla 102: julio, 90 días, 100 KRW, 0.5).

**Efecto de cada parámetro** (validate-case, desde `hard/s4`): cada parámetro cambia la respuesta correcta o la
puntuación con el primer otro valor que prueba. `fy_start` 1 → 4: la referencia de s4 baja de 0.958 a 0.542.
`active_days` 60 → 30: a 0.875 (Q03). `rounding_unit` 100 → 1,000: la referencia queda inválida. `dont_know_reward` 1
→ 0.5: su objetivo pasa de 0.958 a 0.938, y la referencia sorteada con 0.5 responde Q06 y obtiene 0.917. En easy y
medium la referencia responde todas las preguntas puntuadas, así que allí `dont_know_reward` deja su objetivo en
1.000; aun así mueve la línea base de todo `null` (0.25 / 0.50 / 0.75) y la recompensa de cada `null` que dé un
agente, de modo que cambia la calidad normalizada de cualquier hoja que se abstenga. Del mismo modo, en easy, donde
Q01 es la única pregunta monetaria, una hoja de 10,000 KRW sigue siendo válida y correcta con 100 o 1,000 KRW; allí
solo incumple la regla la dirección contraria (una hoja más fina con una unidad más gruesa). Al puntuar la referencia
de cada semilla pública con las otras dos semillas de su nivel (18 pares), 9 son inválidos (redondeo: una hoja de 100
KRW con 1,000 o 10,000, una hoja de 1,000 KRW con 10,000) y los 9 válidos obtienen 0.00–0.38, frente a 0.92–1.00 de la
propia referencia de la configuración. En todos los pares, otro año fiscal mueve Q01, Q02, Q08 y Q10 (Q12 entre el año
que empieza en enero y los demás, Q04 entre el que empieza en julio y los demás), otra ventana mueve Q03, y una unidad
más gruesa puntuada con una más fina falla Q07 o Q09.

## Qué debe preguntar un agente

Las once preguntas clave en hard (nueve en easy, diez en medium), pero cuatro de ellas llevan el sorteo de la semilla
de reglas y no se pueden trasladar de otra ejecución ni adivinar a partir de los datos: el primer mes del año fiscal
(`fiscal_year`), la ventana de actividad (`active_customer`), la unidad de redondeo (`report_rounding`) y lo que vale
un «aún no disponible» (`answer_rewards`). Las otras siete son iguales con cualquier sorteo. Sin `answer_rewards`, un
agente no puede saber si debe dar una respuesta con un 60 % de probabilidad de acierto (sí con 0.5 y 1, no con 1.5);
sin `report_rounding`, no puede saber qué cifras monetarias son válidas.

## Reglas

| Regla | Tipo | Qué la incumple |
|---|---|---|
| `answer_format` | física | falta un identificador de pregunta, o un valor no es ni un número finito ni `null` (se comprueba en las doce, se puntúen o no) |
| `exclude_test_accounts` | contractual | una respuesta puntuada de recuento o de identificador de cliente (Q03, Q04, Q05, Q10) igual a la cifra que incluye las cuentas de prueba (días en hora de Corea, periodos de la configuración), cuando esta difiere de la cifra sin ellas |
| `report_rounding` | costumbre del negocio (flexibilizable) | una respuesta monetaria puntuada (Q01, Q02, Q06, Q07, Q09) que no es un múltiplo exacto de la unidad de la configuración (100 / 1,000 / 10,000 KRW) |

## Situaciones presentes

- **Hechos ocultos:** las once preguntas clave anteriores. Los datos están construidos para que cada una se
  manifieste. Una prueba de carga de QA en la cuenta de prueba 10027 (36 pedidos de diez molinillos manuales y cinco
  mezclas de 1 kg, de abril de 2025 a marzo de 2026) la convierte en el cliente principal con cualquier año fiscal
  cuando las cuentas de prueba se mantienen. Cinco pedidos de prueba caen en los primeros minutos de las rebajas del
  2026-07-01 (hora de Corea), que en UTC todavía es 2026-06-30. Las cancelaciones pagadas tienen filas de pago. Cuatro
  productos de despensa se lanzaron con la etiqueta nueva, mientras que los cuatro más antiguos siguen diciendo
  snacks. Los reembolsos de octubre de pedidos de septiembre mueven Q11 unos 3 puntos (2–4 en las semillas 1–3).
- **Abstención calibrada:** el esquema de recompensas también es un hecho oculto. Un agente que no ha encontrado una
  definición, o que no puede fijar una cifra, debería comparar su probabilidad de acertar con el umbral del sorteo.
  Decir «no sé» a todo da 0.25–0.75, que es la línea base (calidad 0); responder todo a valor nominal da 0–0.4 en las
  semillas de reglas públicas con el mundo público, menos que eso.
- **Eventos con fecha, presión:** ninguno en el propio caso (véase REVIEW.md F6). La modalidad messy añade los eventos
  genéricos del framework.

## Referencia y línea base (semilla de mundo pública 20261026)

La **referencia** es un analista cuidadoso que usa las convenciones de la configuración y acierta todas las
definiciones salvo el cambio de nombre de la categoría: responde la pregunta de «despensa» solo con la etiqueta
`pantry`. Deja en `null` las preguntas que el nivel no puntúa. Su política de abstención es razonada y determinista:
su cifra de despensa solo abarca los productos lanzados desde 2025-10, así que le da a esa respuesta una probabilidad
de acierto del 50 % y solo la mantiene cuando ½ × right_reward > dont_know_reward. Eso se cumple cuando un `null` vale
0.5 (1 > 0.5), así que responde y falla. Con 1 (1 = 1; en caso de empate se abstiene) y con 1.5 (1 < 1.5) dice «no
sé». En easy y medium no se puntúa Q06, así que allí la referencia acierta todas las preguntas puntuadas.

La **línea base** es lo que finanzas informa sin un analista: «aún no disponible» (`null`) en todas las preguntas.
Obtiene la recompensa de «no sé» del sorteo en todas las preguntas puntuadas (0.25 / 0.50 / 0.75 del máximo), de modo
que decir «no sé» a todo vale 0 en la escala normalizada. La **hoja a valor nominal** es la exportación sumada sin
ninguna de las definiciones del cliente: periodos de año natural sobre las fechas UTC guardadas, todos los pedidos sea
cual sea su estado, ingreso = `total` del pedido menos los reembolsos fechados en el periodo, todas las monedas al
tipo del 2026-09-30, activo = con un pedido en los últimos 30 días, «despensa» = la etiqueta `pantry`. Responde todas
las preguntas y respeta las dos políticas de finanzas que el cliente aplica de todos modos (cuentas de prueba fuera,
importes redondeados a la unidad de la configuración). En las semillas de reglas públicas con el mundo público puntúa
por debajo de la línea base en todas las configuraciones: sus cifras erróneas no suman nada.

| Configuración | Sorteo (fy_start, active_days, rounding_unit, dont_know_reward) | Objetivo de la referencia | Línea base (todo `null`) | Hoja a valor nominal | Hoja perfecta | Hoja perfecta, calidad normalizada |
|---|---|---|---|---|---|---|
| easy/s4 | 1, 60, 100, 1 | 1.000 (5 correctas) | 0.500 | 0.400 | 1.000 | 1.000 |
| easy/s12 | 7, 30, 10000, 0.5 | 1.000 | 0.250 | 0.000 | 1.000 | 1.000 |
| easy/s23 | 4, 90, 1000, 1.5 | 1.000 | 0.750 | 0.000 | 1.000 | 1.000 |
| medium/s4 | 1, 60, 100, 1 | 1.000 (11 correctas) | 0.500 | 0.182 | 1.000 | 1.000 |
| medium/s12 | 7, 30, 10000, 0.5 | 1.000 | 0.250 | 0.091 | 1.000 | 1.000 |
| medium/s23 | 4, 90, 1000, 1.5 | 1.000 | 0.750 | 0.000 | 1.000 | 1.000 |
| hard/s4 | 1, 60, 100, 1 | 0.958 (11 correctas, Q06 null) | 0.500 | 0.167 | 1.000 | 1.091 |
| hard/s12 | 7, 30, 10000, 0.5 | 0.917 (11 correctas, Q06 errónea) | 0.250 | 0.083 | 1.000 | 1.125 |
| hard/s23 | 4, 90, 1000, 1.5 | 0.979 (11 correctas, Q06 null) | 0.750 | 0.000 | 1.000 | 1.091 |

La calidad normalizada es (objetivo − línea base) / (referencia − línea base); la de la hoja a valor nominal es 0 en
todas las filas (por debajo de la línea base). La calidad normalizada de la hoja perfecta es 1.0 en easy y medium y
1.09–1.13 en hard, así que el caso no fija `quality_cap` (un solo número por caso no puede dar la puntuación completa
a la hoja perfecta en todas las configuraciones; REVIEW.md, F2). El objetivo de la referencia solo depende del nivel y
de la recompensa del `null`: 1.000 en easy y medium, y 0.917 / 0.958 / 0.979 en hard para un `null` que vale 0.5 / 1 /
1.5, en las 81 combinaciones con las semillas de mundo 1–10 y el mundo público, y en las nueve configuraciones
públicas con las semillas de mundo 1–20.

La hoja a valor nominal no siempre queda por debajo de la línea base. Con las semillas de mundo 1–20 obtiene 0.20–0.60
en easy/s4, frente a una línea base de 0.50: queda por encima con las semillas de mundo 4 y 7, donde acierta tres de
las cinco preguntas. En el resto de las configuraciones públicas se mantiene por debajo (0.00–0.20 en easy/s12,
0.00–0.40 en easy/s23, 0.09–0.36 en medium/s4, 0.00–0.18 en medium/s12 y medium/s23, 0.08–0.33 en hard/s4, 0.00–0.17
en hard/s12 y hard/s23). En las 81 combinaciones por nivel con las semillas de mundo 1–10, alcanza la línea base en
117 de 2,430 casos, todos salvo seis con un año que empieza en enero (el año natural que ella supone) y un `null` que
vale 0.5 o 1; su mejor resultado es 0.60 en easy, 0.46 en medium y 0.42 en hard, frente a una línea base de 0.25. Un
sorteo así da al enfoque a valor nominal una calidad normalizada positiva (hasta 0.47). Con las semillas 1–20 se
construyen, en las nueve configuraciones públicas, mundos, referencias, líneas base y ejemplos de incumplimiento
válidos.

Las respuestas del nivel hard (cifra exacta, referencia, hoja a valor nominal; ✓/✗ = la respuesta a valor nominal es
correcta o errónea; el ✗ de la referencia marca su única respuesta errónea):

| Pregunta | s4 exacta | s4 referencia | s4 valor nominal | s12 exacta | s12 referencia | s12 valor nominal | s23 exacta | s23 referencia | s23 valor nominal |
|---|---|---|---|---|---|---|---|---|---|
| Q01 | 190,723,915 | 190,723,900 | 231,048,900 ✗ | 258,620,880 | 258,620,000 | 231,050,000 ✗ | 223,734,559 | 223,735,000 | 231,049,000 ✗ |
| Q02 | 69,454,940 | 69,454,900 | 82,939,200 ✗ | 92,389,874 | 92,390,000 | 82,940,000 ✗ | 75,372,876 | 75,373,000 | 82,939,000 ✗ |
| Q03 | 801 | 801 | 668 ✗ | 623 | 623 | 668 ✗ | 881 | 881 | 668 ✗ |
| Q04 | 10392 | 10392 | 11182 ✗ | 10247 | 10247 | 11182 ✗ | 10392 | 10392 | 11182 ✗ |
| Q05 | 183 | 183 | 111 ✗ | 183 | 183 | 111 ✗ | 183 | 183 | 111 ✗ |
| Q06 | 28,990,095 | null | 5,611,900 ✗ | 45,050,055 | 20,050,000 ✗ | 5,610,000 ✗ | 37,194,179 | null | 5,612,000 ✗ |
| Q07 | 41,846 | 41,800 | 46,200 ✗ | 41,881 | 40,000 | 50,000 ✗ | 41,618 | 42,000 | 46,000 ✗ |
| Q08 | 5.903 | 5.903 | 4.991 ✗ | 6.178 | 6.178 | 4.991 ✗ | 6.097 | 6.097 | 4.991 ✗ |
| Q09 | 35,820 | 35,800 | 38,800 ✗ | 35,330 | 40,000 | 40,000 ✓ | 35,780 | 36,000 | 39,000 ✗ |
| Q10 | 640 | 640 | 640 ✓ | 690 | 690 | 640 ✗ | 655 | 655 | 640 ✗ |
| Q11 | −2.568 | −2.568 | −5.443 ✗ | −2.568 | −2.568 | −5.443 ✗ | −2.568 | −2.568 | −5.443 ✗ |
| Q12 | 2.128 | 2.128 | 2.124 ✓ | 2.100 | 2.100 | 2.124 ✗ | 2.105 | 2.105 | 2.124 ✗ |

Con s23 (un año que empieza en abril y una ventana de 90 días), las cifras exactas son las del caso sin
configuraciones. Q05 y Q11 no dependen del año fiscal; Q04 es el mismo cliente con el año que empieza en abril y con
el que empieza en enero.

## Notas

- Sintético. Los precios, los tipos impositivos, las trayectorias del tipo de cambio, los ritmos de pedido y las tasas
  de reembolso son inventados; la tienda, sus clientes y sus cuentas son ficticios. Las convenciones de año fiscal,
  día local, cuentas de prueba, ingreso neto y cambio de nombre son las trampas habituales del trabajo de BI sobre
  exportaciones en bruto, no hechos de una empresa real. Las tres recompensas del `null` son decisiones de diseño que
  fijan el umbral de abstención en el 25 %, el 50 % y el 75 %, no costes medidos.
- Simplificaciones conocidas (REVIEW.md F7): un impuesto fijo del 7 % en Estados Unidos para todos los pedidos, tipos
  de cambio también en fin de semana, cancelaciones pagadas sin fila de reversión y altas desde el 2024-07-01 mientras
  que el historial de pedidos empieza el 2025-01-01. La cuenta de prueba de QA 10027 tiene pedidos de prueba de carga
  desde abril de 2025, aunque se dio de alta en diciembre de 2025.
- `validate-case` comprueba todas las configuraciones públicas: datos deterministas en cinco idiomas, la misma vista
  del agente en las nueve, la referencia con calidad 1.0, una línea base válida peor que la referencia, un entregable
  por regla que incumple solo esa regla, las listas de candidatos y las semillas de reglas públicas, `derive_params`
  en todas las combinaciones, y que cada parámetro influye. Advierte de que las referencias de medium y hard son
  idénticas byte a byte con las semillas 4 y 23: ambas dejan Q06 en `null`, porque en medium no se necesita y en hard
  es «no sé» cuando un `null` vale 1 o 1.5. Puntúan distinto (1.0 frente a 0.958 y 0.979), así que el nivel sigue
  aportando información.
