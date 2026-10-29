# Revisión — `healthcare/hospital_appointment_scheduler`

Hallazgos de la revisión del caso (F1–F9), con los veredictos del verificador y lo que este cambio hizo con cada uno. Las cifras
son de la semilla 20261116 salvo que se diga otra cosa; «q» es la calidad normalizada (línea base 0, referencia 1).

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

**Estado:** abierto — propuesta: hacer que los números restantes actúen en los dos sentidos, de modo que el valor más prudente
también sea erróneo (por ejemplo, un retraso máximo de nueva citación junto al preaviso, o un plazo de urgentes con una fecha más
temprana fijada por el triaje, para que «mañana» no sea siempre lo correcto). Generar algunas solicitudes urgentes que necesiten
intérprete o análisis, o que lleguen cuando la reserva de mañana ya está usada, para que `urgent_days` actúe. Añadir el programa de
la envolvente a la comprobación de distinción de validate-case y exigir que sea inválido o más de un 3% peor.

### F4 — Flexibilizar la costumbre de las revisiones premia la flexibilización general, no la selectiva (alta, confirmado)

Citar cada revisión con el colega que esté libre antes (287–332 excepciones) sube el objetivo un 2.0–5.8%; flexibilizar solo para
los pacientes de un médico ausente (43–51 excepciones), un 0.0–1.3%. Con la nueva escala, la flexibilización general vale q
1.11–1.29, es decir, de +0.04 a +0.115 en la puntuación final antes de la penalización, así que ahora compensa con
startup_velocity (penalización 0.05) en 5 de 9 configuraciones, mientras que la flexibilización selectiva, la clínicamente
sensata (+0.000 a +0.024), nunca compensa. Una sola aprobación cubre todas las excepciones.

**Estado:** abierto — propuesta: dar a algunas revisiones del pediatra de baja un plazo clínico dentro de la ausencia, de modo que
mantener la costumbre las deje sin atender y solo una excepción selectiva y aprobada recupere el valor. Añadir un pequeño coste
operativo por cada revisión atendida por un médico distinto del anterior, para que la flexibilización general puntúe por debajo de
la selectiva. Informar de la flexibilización en términos de puntuación final en el README.

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
coincide con B).

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
medium/hard (0.998–1.006), y una revisión anulada un día y vuelta a citar al día siguiente para el día después no rompía ninguna
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
revise también un revisor nativo.

**Línea base:** la práctica de la oficina de citas sin un ingeniero: el programa de referencia, pero la reserva de urgencias nunca
se libera para las consultas de mañana y (hard) nunca se sobrecita nada. Objetivo 0.806–0.812 en easy, 0.787–0.799 en medium y
0.689–0.701 en hard, frente al 1.0 de la referencia en todas las configuraciones (válida en las nueve configuraciones y en las
semillas de mundo 1–3).
