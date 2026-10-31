# Revisión — `healthcare/hospital_appointment_scheduler`

Hallazgos de la revisión del caso (F1–F9), con los veredictos del verificador y lo que este cambio hizo con cada uno. Las cifras
son de la semilla 20261116 salvo que se diga otra cosa; «q» es la calidad normalizada (línea base 0, referencia 1). Un cambio
posterior sustituyó los tres conjuntos de reglas fijos A/B/C por semillas de reglas que sortean cada valor de regla entre unos
candidatos (sección «Semillas de reglas», al final). Resuelve F3 y mueve las cifras de F1, F2, F4 y F5; los hallazgos de abajo
conservan las cifras de los conjuntos de reglas con las que se escribieron.

### F1 — La ocupación está en el techo, así que el empaquetado gana poco (alta, en parte)

La capacidad es de unos 79 huecos al día y la demanda de unos 83–86, así que la referencia ya llena el 98% de los huecos en easy y
medium. Las mejores variantes válidas que conocemos (empaquetado; en hard además un umbral de sobrecitación más bajo y las tasas de
ausencia verdaderas) solo añaden entre +0.1% y +1.5% al objetivo, lo que supone q = 1.005–1.056 frente a la nueva línea base. Los
programas válidos siguen repartidos entre aproximadamente 0.79 y 1.0, pero a través de unas pocas palancas gruesas (liberar la
reserva, la nota de D10, sobrecitar o no) y no del empaquetado. El problema original de «recortado en 1.0» desaparece con la nueva
escala, pero ahora el tope de la política, 1.5, queda fuera de alcance: ningún programa válido conocido obtiene más de alrededor
del 70% de la puntuación de calidad.

**Estado:** abierto — propuesta: decidir primero si aquí debe poder medirse una optimización mejor. Si es así, hacer más difícil
la colocación en lugar de bajar la demanda (más revisiones ligadas a un médico, días cargados de intérpretes y análisis,
duraciones de visita mezcladas) y añadir una referencia más fuerte o una cota superior, de modo que el empaquetado y la
anticipación muevan la puntuación varios puntos porcentuales. Si no, fijar `quality_cap` en case.yaml en torno a 1.1, para que un
programa al mejor nivel conocido obtenga la puntuación completa.

### F2 — La sobrecitación no necesita la estimación de ausencias por paciente (alta, confirmado)

Sobrecitar todos los huecos de revisión elegibles hasta el tope (umbral 0) puntúa 0.999 / 1.005 / 1.000 en hard A/B/C (q 0.997 /
1.015 / 1.000), todos válidos; un umbral de 0.10 puntúa algo por encima de la referencia y no sobrecitar, 0.943–0.952. Así que
importa si se sobrecita (alrededor de un 5%), pero no la selección de riesgo que el nivel hard pretende evaluar. Hasta este cambio,
el equilibrio de 10 frente a 12 solo figuraba como un peso de la puntuación, que el cliente simulado puede no revelar.

**Estado:** abierto — propuesta: hacer que la selección de riesgo decida la puntuación: subir el coste de coincidencia (o añadir un
coste por horas extra del médico) para que la sobrecitación indiscriminada sea claramente negativa en neto, y ampliar la
dispersión de las tasas de ausencia para que la sobrecitación selectiva la supere con claridad. Añadir a validate-case una
comprobación de que el programa con umbral 0 puntúa al menos un 3% por debajo de la referencia. (Este cambio, en F6, ya enuncia el
equilibrio como un hecho del negocio en los requisitos de hard: cuando acuden los dos pacientes el médico se retrasa, lo que cuesta
algo más que un hueco vacío.)

### F3 — Los números de los conjuntos de reglas son inertes o de un solo sentido (alta, confirmado)

`urgent_days` = 1, 3 o 10 da un objetivo de 1.0000 sin ningún incumplimiento en las nueve configuraciones: las solicitudes urgentes
son siempre en el idioma local, sin análisis, para mañana y solo se generan cuando la reserva de mañana está intacta. Antes de este
cambio, el valor más conservador de cada número (2 intérpretes, laboratorio 5, sobrecitación 1, preaviso 4, urgentes 1) era válido
en 8 de 9 configuraciones con 0.98–1.00, así que solo `waitlist_order` (y débilmente `closed_dept`) distinguía los conjuntos de
reglas. Tras la corrección de F8, esa envolvente es inválida en 8 de 9 (`waitlist_priority`: los intérpretes y plazas de
laboratorio sin usar ya no excusan a un paciente saltado), pero preaviso 4 + sobrecitación 1 + urgentes 1 por sí solos siguen
siendo válidos en 6 de 9 con 0.988–1.000.

**Estado:** corregido en el cambio a semillas de reglas (sección «Semillas de reglas»). Hasta entonces estaba abierto con esta
propuesta: hacer que los números restantes actúen en los dos sentidos, de modo que el valor más prudente también sea erróneo (por
ejemplo, un retraso máximo de nueva citación junto al preaviso, o un plazo de urgentes con una fecha más temprana fijada por el
triaje, para que «mañana» no sea siempre lo correcto). Generar algunas solicitudes urgentes que necesiten intérprete o análisis, o
que lleguen cuando la reserva de mañana ya está usada, para que `urgent_days` actúe. Añadir el programa de la envolvente a la
comprobación de distinción de validate-case y exigir que sea inválido o más de un 3% peor. Lo que hizo el cambio en su lugar: los
dos números que no actúan ya no se sortean (el plazo de las urgentes queda fijo en 2 días laborables y el preaviso en 3), el tamaño
de la reserva pasa a ser un valor sorteado que actúa en los dos sentidos, y la envolvente es inválida en 8 de las 9 configuraciones
públicas y un 14% peor en la novena. La comprobación de efecto de validate-case (todo parámetro sorteado debe cambiar la respuesta)
sustituye a la comprobación de distinción; la envolvente en sí no es una comprobación del validador.

### F4 — Flexibilizar la costumbre de las revisiones premia la flexibilización general, no la selectiva (alta, confirmado)

Citar cada revisión con el colega que esté libre antes (287–332 excepciones) sube el objetivo un 2.0–5.8%; flexibilizar solo para
los pacientes de un médico ausente (43–51 excepciones), un 0.0–1.3%. Con la nueva escala, la flexibilización general vale q
1.11–1.29, es decir, de +0.04 a +0.115 en la puntuación final antes de la penalización, así que ahora compensa con
startup_velocity (penalización 0.05) en 5 de 9 configuraciones, mientras que la flexibilización selectiva, la clínicamente
sensata (+0.000 a +0.024), nunca compensa. Una sola aprobación cubre todas las excepciones.

**Estado:** abierto — propuesta: dar a algunas revisiones del pediatra de baja un plazo clínico dentro de la ausencia, de modo que
mantener la costumbre las deje sin atender y solo una excepción selectiva y aprobada recupere el valor. Añadir un pequeño coste
operativo por cada revisión atendida por un médico distinto del anterior, para que la flexibilización general puntúe por debajo de
la selectiva. Informar de la flexibilización en términos de puntuación final en el README. Semillas de reglas: sin cambios de
fondo. En las semillas públicas, la flexibilización general (302–330 excepciones) añade un 2.0–5.7% y la selectiva (44–57), un
0.0–1.4%.

### F5 — El historial visible contradice las reglas del hospital (media, confirmado)

En la exportación, 106 de las 151 citas del historial a las 09:00/09:20 son solicitudes S/R citadas con dos o más días laborables
de antelación, lo que prohíbe la regla de la reserva; las primeras visitas con intérprete llegan a 10 al día (tope 2–4) y los
análisis en ayunas a 10 al día (tope 5–7). `_history` llena los huecos al 92% sin ninguna lógica de reserva, intérpretes ni
laboratorio, mientras que el libro inicial respeta las reglas. La respuesta piloto usa el orden de lista de espera `received` (el
del conjunto de reglas B) y ninguna reserva.

**Estado:** abierto — propuesta: generar el historial con las reglas que comparten los tres conjuntos de reglas (reserva
respetada, como mucho 2 primeras visitas con intérprete y 5 análisis al día), o que un correo de la dirección de consultas
externas diga que la reserva, el turno de intérpretes y el tope del laboratorio empiezan el 9 de noviembre. Reformular el tope
del laboratorio como «plazas de extracción en ayunas en la sala de extracciones de consultas externas» para que el número pequeño
resulte verosímil, y dar al piloto un orden provisional que no coincida con ningún conjunto de reglas (o decir en el README que
coincide con B). Semillas de reglas: sigue abierto. El orden `received` del piloto es ahora uno de los tres candidatos de
`waitlist_order` (lo sortea la semilla 64). El libro inicial deja libres las 09:00 y las 09:20, es decir, una reserva de dos huecos;
cuando una semilla sortea tres huecos, los requisitos dicen ahora, en los cinco idiomas, que la oficina solo guardaba dos hasta el 9
de noviembre y que las citas de las 09:40 ya dadas se quedan donde están.

### F6 — Preguntas clave sobre la puntuación que al cliente se le indica no revelar nunca (media, en parte)

`scoring` y `scoring_hard` eran fórmulas y pesos de la puntuación, y `status_table` («20% de la calidad») y `several_departments`
(«cuesta 3») también llevaban pesos, mientras que el prompt del cliente prohíbe describir puntuaciones o pesos; el recall de
Ask-F1 no podía llegar a 1. La parte de «ya visible» no se sostenía: en la condición por defecto `interact_req` el agente solo ve
request.md y los datos, así que `interface`, `visit_length` y el final del periodo hay que preguntarlos de todos modos.

**Estado:** corregido en este cambio — las cuatro preguntas clave se han reescrito en los cinco idiomas como hechos del negocio
(el tiempo de médico vacío es la mayor pérdida; la espera, las solicitudes sin cita y los cambios cuestan; con ausencias, lo que
cuenta son los pacientes que acuden; un hueco sobrecitado en el que acuden los dos cuesta algo más que uno vacío; los viajes de más
son un coste), sin pesos. Los requisitos de hard ganan la frase que necesita el último hecho; la puntuación no cambia. Se mantienen
`interface`, `visit_length` y `evaluation_period`.

### F7 — El alcance de los niveles inferiores, escrito como instrucciones de examen (media, en parte)

Easy y medium decían «cada solicitud es su propia visita, aunque el mismo paciente pida dos veces» y «los análisis quedan fuera
del alcance», lo que se lee como una instrucción al programa más que como un hecho del hospital; de hecho, deduplicar ahí es
inválido (`waitlist_priority`, 187–342 casos). La pauta sobre las notas (el conocido del director, las tardes de D10) solo figura
en hard, aunque seguir la nota de D10 cuesta un 6.7–7.5% en easy y medium.

**Estado:** corregido en este cambio — los puntos de alcance de easy y medium ahora dicen el porqué, como lo diría el cliente, en
los cinco idiomas: esta ronda admisión y el laboratorio se ocupan ellos mismos de los volantes y de los análisis en ayunas; no se
cuenta con ausencias de pacientes; una segunda solicitud lleva su propia cita porque la oficina no puede saber por la solicitud si
es la misma dolencia. La puntuación no cambia y las preguntas clave correspondientes se han reformulado. Queda como propuesta:
llevar el párrafo de las notas y la pregunta clave `staff_notes` a todos los niveles, ya que las notas están en los datos de
todos los niveles.

### F8 — Excusas laxas en la prioridad de la lista de espera y un resquicio en el preaviso (baja, confirmado)

Reproducido con el comprobador antiguo: un programa que nunca cita una primera visita con intérprete era válido en 9 de 9
configuraciones (0.950–0.988), uno que cita al final las solicitudes que necesitan análisis era válido en 6 de 6 configuraciones
medium/hard (0.998–1.006), y una revisión anulada un día y vuelta a citar al día siguiente para el día después no incumplía ninguna
regla en los conjuntos de reglas A y C (preaviso 3 y 4; con preaviso 2 no puede ocurrir).

**Estado:** corregido en este cambio — una primera visita en espera que necesita intérprete solo queda excusada cuando los
intérpretes presenciales de ese día están todos ocupados al final de la llamada; una que necesita análisis, solo cuando ningún día
laborable antes del hueco (desde mañana, no antes de su fecha más temprana) tiene sitio en el laboratorio, contando como sitio la
plaza de análisis de la propia solicitud citada; `move_notice` cubre ahora también una solicitud anulada que se vuelve a citar más
tarde (preaviso desde el día de la anulación; volver a la fecha y hora anuladas no lo necesita), y la excusa correspondiente por
anulación se cuenta desde el día de la anulación. Así lo dicen los requisitos (cinco idiomas), la pregunta clave sobre el preaviso
de los cambios, case.yaml y el README. La referencia ahora recuerda sus propias anulaciones; sus resultados no cambian en ninguna
de las nueve configuraciones. En A y C el ejemplo de `move_notice` del validador es ahora la vía de la anulación. Un cambio a la
misma fecha y hora con otro médico ya no exige preaviso, como dice el texto (solo podía darse en IM los viernes por la tarde, cuando
D03 y D04 se solapan). Sin cambiar (decisión del responsable): una revisión citada con otro médico sigue comparándose solo con la
cola de su médico anterior.

### F9 — Elección de términos en coreano (baja, confirmado)

`earliest_date` se traducía como «희망시작일» (fecha de inicio deseada) aunque la regla es un «nunca antes» estricto; S era «조기»;
los médicos firmaban como «교수» y la secretaría como «의국», lo que apunta a un hospital universitario.

**Estado:** corregido en este cambio — «진료 가능 시작일(earliest_date)» en los requisitos coreanos, las preguntas clave y la
etiqueta del orden del conjunto de reglas C; S = «준응급»; los médicos «{name} 과장» y la secretaría «{dept} 사무실» en los correos
coreanos (con la partícula tras «과장» ajustada). Los correos japoneses siguen firmando como «医局», algo que quizá convenga que
revise también un hablante nativo.

**Línea base:** la práctica de la oficina de citas sin un ingeniero: el programa de referencia, pero la reserva de urgencias nunca
se libera para las consultas de mañana y (hard) nunca se sobrecita nada. Objetivo 0.806–0.812 en easy, 0.787–0.799 en medium y
0.689–0.701 en hard, frente al 1.0 de la referencia en todas las configuraciones (válida en las nueve configuraciones y en las
semillas de mundo 1–3).

## Semillas de reglas

Los conjuntos de reglas A/B/C (siete valores fijos cada uno) pasaron a ser seis parámetros que una semilla de reglas sortea entre
unos candidatos, los mismos en todos los niveles, así que una semilla es un hospital y el nivel solo añade reglas:

| Parámetro | Candidatos | Antes (A / B / C) |
|---|---|---|
| `closed_dept` | DERM, ORTH, PED | DERM / ORTH / PED |
| `reserve_slots` (nuevo) | 2, 3 | 2 (fijo: «los dos primeros huecos») |
| `interpreters_per_day` | 2, 3, 4 | 3 / 4 / 2 |
| `waitlist_order` | `urgency_received`, `received`, `urgency_earliest` | los mismos tres |
| `lab_cap` (medium y hard) | 5, 6, 7 | 6 / 5 / 7 |
| `overbooked_per_session` (hard) | 1, 2, 3 | 2 / 1 / 2 |
| `urgent_days` | eliminado: fijo en 2 | 2 / 1 / 3 |
| `move_notice_days` | eliminado: fijo en 3 | 3 / 2 / 4 |

Las semillas de reglas públicas son la 1, la 10 y la 64, que muestran cada candidato de cada lista al menos una vez (README.md,
«Parámetros y semillas de reglas», tiene los diccionarios sorteados y las cifras). `derive_params` redacta en cada idioma las horas
de la reserva (`reserve_times`); no hace falta ningún gancho `admissible`, porque la referencia y la línea base son válidas, y la
tabla de la referencia exacta, en las 54 combinaciones de easy, las 162 de medium y las 486 de hard en el mundo público. Los datos,
el periodo oculto y `request.md` no cambian; solo cambiaron la forma en que el evaluador ve la reserva y los textos.

**Por qué dos números son fijos.** `urgent_days` no puede actuar: cada solicitud urgente se genera para una especialidad con un
hueco de reserva libre mañana, así que la referencia cita las 18 para mañana con cualquier plazo (F3). Mover en su lugar el extremo
inferior del plazo (un día de triaje) rompe los datos: el médico de una revisión urgente se elige para que tenga una sesión de
mañana al día siguiente, no más tarde. `move_notice_days` solo actúa por casualidad. La referencia cambia citas solo por las dos
ausencias y la ausencia del intérprete, y las pone en el siguiente hueco libre, normalmente mucho más allá del preaviso. En las
combinaciones probadas (los tres antiguos conjuntos de reglas y doce aleatorias, en las semillas de mundo 1–3 y en el mundo público)
un preaviso de 2 y uno de 3 dieron siempre la misma respuesta; una referencia construida para 2 o 3 incumplía un preaviso de 4 en la
mayoría de ellas, mientras que una construida para 4 era válida con 2 y con 3 en alrededor de la mitad; en la semilla de mundo 2
ningún par se diferenció en nada. Adelantar un día los avisos de ausencia (probado: el aviso de D13 el jueves, el de D05 el jueves)
hizo que los pares se diferenciaran en algunas combinaciones y no en otras. Ambas reglas se mantienen, con su número en el texto y
sus preguntas clave.

**Por qué `reserve_slots` es nuevo.** Es un valor que el cliente tiene que decir («los dos primeros huecos» era un número oculto en
todos los conjuntos de reglas) y actúa en los dos sentidos: un programa que guarda dos huecos cuando la regla es tres cita
solicitudes S/R a las 09:40 con dos días de antelación (`urgent_reserve`); uno que guarda tres cuando la regla es dos informa mal de
`held_back` y `free_slots` todos los días (precisión de la tabla 0.33, objetivo 0.85–0.86). Con tres huecos la referencia libera
para mañana 160–190 huecos de reserva en lugar de unos 100, y la línea base, que nunca los libera, baja a 0.73 / 0.68 / 0.56.

**Efecto y doble sentido.** La comprobación de efecto de validate-case parte de `hard/s1`; cada parámetro actúa ya con su primera
alternativa, siempre porque la referencia pasa a ser inválida (README.md). Puntuando la referencia de cada configuración pública con
un valor cambiado (todos los niveles): `closed_dept` y `waitlist_order` son inválidos en todos los pares; `interpreters_per_day` es
inválido en todos los pares en ambos sentidos (menos: `interpreter_capacity`; más: `waitlist_priority`, ya que los intérpretes sin
usar ya no excusan a un paciente saltado, la corrección de F8); `lab_cap` es inválido al bajarlo y, en las combinaciones de s1 y
s64, al subirlo desde 5, pero un laboratorio de 5 bajo 6 o 7 en la combinación de s10 y uno de 6 bajo 7 siguen siendo válidos con
−0.1 a −0.2%; `overbooked_per_session` es inválido al bajarlo y válido pero entre −0.6% (2 bajo 3) y −3.6% (1 bajo 3) peor al
subirlo. Así que el tope de sobrecitación y, en parte, el del laboratorio siguen siendo de un solo sentido: una suposición prudente
es válida y algo peor. La referencia de cada semilla pública es inválida bajo las otras dos semillas de su nivel.

**La envolvente de F3.** 2 intérpretes, laboratorio 5, sobrecitación 1 y una reserva de tres (el extremo prudente de cada número
sorteado), con la consulta y el orden de la propia configuración: inválida en 8 de las 9 configuraciones públicas
(`waitlist_priority`) y 0.857 en `easy/s1` (cuyos intérpretes son 2; el hueco de reserva de más estropea la tabla).

**Cifras que se movieron.** F1: las mejores variantes válidas (empaquetado; en hard, un umbral de 0.10) llegan a 1.001–1.012,
q 1.003–1.058; el tope de calidad de la política, 1.5, sigue fuera de alcance. F2 es más marcado con un tope de un hueco sobrecitado
por sesión: en `hard/s64`, sobrecitar todas las revisiones elegibles (umbral 0) puntúa 1.009, por encima de la referencia (1.002 en
`hard/s10`, 0.999 en `hard/s1`). F4: arriba. La línea base es válida en todas las combinaciones y puntúa 0.81 / 0.79 / 0.68–0.70
(easy / medium / hard) con una reserva de dos huecos y 0.73 / 0.68 / 0.56 con tres.

**Pruebas.** `tests/test_transforms.py` fijaba las antiguas semillas públicas (1, 2, 3) y el cierre de Dermatología del conjunto
de reglas A en easy; ahora comprueba las semillas públicas (1, 10, 64) y usa `easy/s64` (Dermatología) junto a `hard/s3`, una
semilla privada que sigue sorteando Pediatría y dos huecos sobrecitados.

**Comprobación de la conversión.** Una revisión adversarial encontró lo que ve el agente idéntico byte a byte en todos los idiomas
en los tres niveles, las semillas públicas y las semillas de reglas privadas 4–10; la referencia válida con 1.0 y la línea base
válida y por debajo de ella (como mucho 0.823 de ella) allí, en el mundo público y en las semillas de mundo 1–3; cada parámetro
sorteado cubierto por una pregunta clave; y las cifras de las semillas públicas del README iguales al conjunto de datos guardado.
Se corrigió una cifra del README: la referencia de hard con un hueco sobrecitado por sesión puntúa 0.976 con un tope de 2 y 0.964
con un tope de 3 (no 0.98 en ambos casos).
