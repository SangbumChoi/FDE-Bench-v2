# Revisión de `logistics/bakery_delivery_dispatcher`

Hallazgos de la revisión del caso (F1–F9), con el veredicto del verificador y lo que este cambio hizo con cada uno.
Las cifras corresponden a la semilla del caso 20261025 salvo que se indique otra cosa; "q" es la calidad normalizada
(línea base 0, referencia 1). Las cifras de margen de mejora proceden de una búsqueda de recocido simulado desde la
referencia (movimientos de reubicación, intercambio y 2-opt, salidas al minuto), que reprodujo los 601.51 y 521.98 de
la revisión.

### F1 — La cafetería cerrada se llamaba con el nombre de otra cafetería (alta, confirmado)

Los textos de los cinco idiomas decían que "Clock Tower café (C11)" (en la versión española, "Cafetería Torre del Reloj
(C11)") estaba cerrada. En los datos, Torre del Reloj es C10, una cafetería asociada premium, y C11 es Colina Sur
(남산점, 南山店, South Hill café). Un agente que se guiaba por el nombre, atendía C11 y se saltaba C10 entregaba un
plan inválido: la referencia modificada de esa forma incumple `closed_cafe`, `serve_each_once` (C10 sin atender) y
`shift_window` (V4 vuelve a las 10:08). La validez dependía de fiarse más de los códigos que de los nombres, no de
hacer la pregunta correcta.

**Estado:** corregido en este cambio — requirements.md y targets.yaml de los cinco idiomas nombran ahora
la cafetería como lo hacen los datos: South Hill café (C11), 남산점(C11), 南山店（C11） (ja, zh), Cafetería Colina Sur
(C11). C10 sigue abierta. La comprobación `name (ID)` del validador, que señalaba la discrepancia en los cinco
idiomas, ya no da ningún aviso.

**Semillas de reglas:** la cafetería cerrada es ahora un parámetro (C11, C03 o C14). La forma de nombrar cada
candidato en cada idioma sale de `params.closed_cafe.labels` en case.yaml y es el nombre que los datos dan a ese
código (en todos los mundos, el nombre de una cafetería va con su código), así que la corrección se mantiene sea cual
sea la cafetería sorteada; la cafetería que presiona en el nivel hard, C07, también se nombra como en los datos. La
comprobación `name (ID)` no da ningún aviso en ninguna configuración pública.

### F2 — Poco margen de mejora sobre la referencia (alta, confirmado)

La búsqueda llega a 601.51 cumpliendo todas las reglas, un 3.8% por debajo de los 625.55 de la referencia. La calidad
ya no se recorta en 1.0: frente a la nueva línea base (963.09), ese plan obtiene q = 1.07 y 0.71 de la puntuación
de calidad con el tope de la política en 1.5, frente a 0.67 de la referencia. El plan ingenuo de barrido angular de la
revisión con salidas ajustadas (686.39) obtiene q = 0.82. Así, los planes ingenuos y los expertos ya se distinguen
(0, 0.82, 1.0, 1.07), pero ningún plan conocido que cumpla las reglas se acerca al tope.

**Estado:** abierto — propuesta: o reforzar la referencia (movimientos de intercambio y 2-opt, salidas al minuto:
unos 601.5 en este mundo) o mantenerla y fijar `quality_cap: 1.1` en case.yaml, para que un plan al nivel del mejor
conocido obtenga la puntuación completa. Ajustar más la instancia (F3, F4) separaría más los planes.

**Semillas de reglas:** la referencia parte ahora también del plan de respaldo del nivel y añade 300 rondas de
destrucción y reconstrucción (ruin and recreate) tras la reubicación. Las cifras de arriba corresponden al antiguo
problema único; el margen de mejora con las nuevas reglas no se ha medido. Sigue abierto.

### F3 — Saltarse premium primero solo compensa por poco, y no donde la costumbre perjudica (alta, en parte)

Con `premium_first` flexibilizada, la búsqueda llega a 521.98 sin minutos de retraso (q = 1.31), un 13.2% por debajo
del mejor plan que cumple las reglas. Todo plan que cumple las reglas llega a C05 unos 10 minutos tarde, porque V4
tiene que atender antes C16 y C10 (V4 de la referencia: C16 06:19, C10 07:00, C05 07:40). Con la nueva escala
desaparece el antiguo argumento de "recortada en 1.0". Contando los cuatro componentes de la puntuación (peso de la
calidad 0.6), saltarse la costumbre gana 0.094 de la puntuación final antes de la penalización frente al mejor plan
que cumple las reglas. Eso deja −0.006 netos con `enterprise_balanced` (penalización 0.1) y +0.044 con
`startup_velocity` (0.05). Frente a la referencia, deja +0.023 netos con `enterprise_balanced`. El mejor plan que se
salta la costumbre lo hace en tres de las cuatro rutas, no solo en V4.

**Estado:** abierto — propuesta: decidir si una excepción bien argumentada debe compensar aquí. Si es así, hacer que
el coste de la costumbre sea concreto y local: por ejemplo, un SLA con el socio ("las cafeterías asociadas nos cobran
cada minuto de retraso"), de modo que la ruta de V4 que cumple las reglas cueste claramente más que una que se la
salta y que la razón de negocio sea la que el agente debe dar. Mantener al día las cifras con y sin la costumbre del
README (601.51 frente a 521.98). Si no, eliminar el conflicto (por ejemplo, un `deliver_by` más tardío para C05) o
hacer contractual la costumbre, para que saltársela nunca deje una ganancia neta.

**Semillas de reglas:** la costumbre es ahora un parámetro: medium y hard sortean si se aplica o no, y en easy no se
aplica. Donde se aplica cuesta mucho más que antes, el 27.5% (hard/s5) y el 28.4% (medium/s5) del objetivo de la
referencia con la semilla del caso, porque las ventanas de entrega son ahora más estrechas; flexibilizarla con una
excepción aprobada compensa claramente donde la costumbre del negocio es flexible. `build_world` exige al menos un 1%
en la combinación principal de hard para que el parámetro influya. Sigue abierto si flexibilizarla debe compensar
tanto.

### F4 — La capacidad, el turno y la pregunta de una sola visita no deciden el mejor plan (media, en parte)

En el mejor plan que cumple las reglas, las cargas son de 89/85/115/67 bandejas frente a 120, y la vuelta más tardía
es a las 09:21 frente a las 09:30. La demanda abierta es de 356 bandejas frente a 480 de capacidad de la flota. El
entregable no tiene cantidad por parada, así que la pregunta `one_visit` no puede cambiar un plan (una cafetería que
aparece dos veces ya incumple `serve_each_once`). Ambas reglas sí limitan en planes más flojos: el barrido de la línea
base pasa a la siguiente furgoneta justo cuando la capacidad o el turno lo cortan. `van_capacity` no tiene pregunta
clave (`max_trays` está en los datos).

**Estado:** abierto — propuesta: si las reglas físicas deben importar en los planes buenos, hacer que una limite en
el óptimo: un fin de turno a las 09:00, o una demanda cercana al 90% de la flota. Una V4 más pequeña no lo conseguiría,
porque la ruta de V4 que cumple las reglas lleva 67 bandejas. O bien eliminar la pregunta `one_visit`, o bien permitir
entregas divididas con bandejas por parada, para que ese hecho cambie el entregable.

**Semillas de reglas:** resuelto en parte. El fin del turno (09:00, 09:30, 10:00) y el límite de bandejas de esta
semana (100, 110, 120; un hecho oculto por debajo de los 120 visibles de `max_trays`, planteado como cajas nuevas más
hondas) son parámetros, y `build_world` solo conserva los mundos en los que pueden cambiar la respuesta: la referencia
de la combinación principal de hard tiene una furgoneta que vuelve después de las 09:00 y la de medium una que lleva
más de 100 bandejas (semilla del caso: 09:03 y 103 bandejas), así que ambos influyen ahí. `van_capacity` tiene ahora
una pregunta clave (`tray_limit`) siempre que está por debajo de 120. La pregunta `one_visit` no cambia (abierto).

### F5 — El coste del retraso solo aparecía como regla de puntuación (media, confirmado)

El peso de 3× sobre los minutos de retraso solo figuraba en "Cómo se evalúa el plan". El prompt del cliente prohíbe
describir pesos, y las notas sobre los datos solo decían que `deliver_by` es "la hora de llegada más tardía que la
cafetería acepta". Que el agente conociera el compromiso, y que la pregunta `lateness` pudiera cubrirse, dependía de
que el cliente simulado se saltara sus propias instrucciones.

**Estado:** corregido en este cambio — las notas sobre los datos de los cinco idiomas presentan ahora el
coste como un hecho del negocio, justo después de la línea de `deliver_by` (versión española): "Una entrega tardía se
acepta, pero nos cuesta: cada minuto que una cafetería recibe el pedido después de su `entregar_antes` nos cuesta lo
mismo que tres minutos de furgoneta (quejas y abonos a la cafetería)." La sección "Cómo se evalúa el plan" no cambia;
reducirla a la voz del gerente queda en manos del responsable del caso.

**Semillas de reglas:** el peso es el parámetro `late_cost` (2, 3 o 5), expresado del mismo modo en las notas sobre
los datos, en la sección de evaluación y en la pregunta `lateness`.

### F6 — Algunas semillas de mundo hacían fallar el generador (media, confirmado)

En el momento de la revisión, el solucionador de referencia lanzaba una excepción en 5 de las semillas de mundo 1–30,
y 3 de esos mundos no tenían ningún plan válido, porque los papeles de asociada y de categoría están fijados por
índice.

**Estado:** no reproducido — el commit anterior "Bakery dispatcher: work on any world seed" (adb576f) hace que
`build_world` siga extrayendo del flujo aleatorio de la semilla hasta que la referencia encuentra un plan válido y
cada regla tiene un plan que solo la incumple a ella, y la construcción reintenta ahora con cada orden viable de las
cafeterías asociadas y con órdenes barajados. Las semillas de mundo 1–50 se construyen todas, y
`validate-case --world-seeds 1,...,50` pasa: referencia, ejemplos de incumplimiento y la nueva línea base. Los papeles
siguen fijados por índice; la nueva extracción resuelve el problema.

**Semillas de reglas:** `build_world` exige ahora además un plan válido con la combinación más estricta de cada nivel
(el plan de respaldo del nivel) y mundos en los que todos los parámetros puedan influir (véase "Semillas de reglas"
más abajo). Pasa alrededor del 9% de las extracciones, con 0.8 s por mundo de media. La semilla del caso y las
semillas de mundo 1–30 se construyen; `validate-case --world-seeds 1,...,20` pasa. Los datos de la semilla del caso
cambiaron con ello.

### F7 — Entrega en horario de apertura, el escalón de velocidad y los nombres de barrio (media, en parte)

Las furgonetas esperan a que abra la cafetería, y `deliver_by` cae entre 45 y 90 minutos después de la apertura,
mientras que en la realidad las entregas de panadería suelen llegar antes de abrir. La velocidad depende solo de
cuándo empieza el tramo: un tramo que empieza a las 06:59 va entero a 30 km/h y uno que empieza a las 07:00 tarda
un 50% más. Los nombres de barrio no casan con las coordenadas (Cafetería Estación Norte está en y = −10.27 y
Cafetería Colina Sur en y = +6.05), aunque los datos nunca dicen que +y sea el norte. El verificador considera que son
juicios de realismo y no defectos: las reglas están enunciadas y se aplican por igual a todos los agentes.

**Estado:** abierto — propuesta: si se rehace el caso (F8), convertir `opens` en una ventana de recepción ("personal
en el local desde") con `deliver_by` a la hora de apertura o antes, usar una velocidad que cambie a mitad de tramo (o
que varíe gradualmente entre las 06:45 y las 07:15) y asignar los nombres de barrio a partir de las coordenadas. Cada
uno de estos cambios modifica los datos y la referencia, así que corresponden al rediseño de F8 y no a un parche.

**Semillas de reglas:** hecho en parte. En hard, la velocidad cambia ahora a las `rush_start` también en un tramo ya
empezado (un tramo que empieza más tarde nunca tarda menos); easy y medium usan 25 km/h constantes. `deliver_by` cae
ahora 30, 45 o 60 minutos después de la apertura (antes 45, 60 o 90), así que el retraso es un compromiso real. No se
han hecho ni `opens` como ventana de recepción ni los nombres de barrio a partir de las coordenadas (abierto).

### F8 — Sin configuraciones y solo con hechos ocultos (media, confirmado)

El caso no tiene niveles ni conjuntos de reglas, así que todas las columnas de dificultad puntúan el mismo problema.
De los tres tipos de situación solo tiene hechos ocultos (C11 cerrada, el significado de la cadena de frío, la
costumbre de premium primero): no hay evento fechado ni presión de partes interesadas. Además es el fixture de pruebas
del framework (`tests/conftest.py`), lo que encarece cualquier cambio.

**Estado:** abierto — propuesta: primero trasladar las pruebas del fixture a un caso pequeño dedicado. Después,
convertirlo a 3 niveles × 3 conjuntos de reglas con datos idénticos byte a byte. Easy: el modelo de desplazamiento,
el turno, la cafetería cerrada y el coste del retraso, con la cadena de frío y premium primero declarados fuera de
alcance esta semana. Medium: añade la cadena de frío, las velocidades de hora punta y premium primero (flexibilizable).
Hard: añade un evento fechado (V2 en el taller hasta las 06:40, o un pedido duplicado que haga que la capacidad
limite) y un mensaje de presión (el encargado de una cafetería premium que exige ser el primero). Los conjuntos de
reglas podrían variar qué cafetería está cerrada, el fin del turno, el peso del retraso y el inicio de la hora punta.
Una capacidad oculta de V4 contradiría el `max_trays` visible, así que debería plantearse como un hecho oculto ("el
estante refrigerado de V4 está averiado esta semana").

**Estado (semillas de reglas):** resuelto — convertido a 3 niveles y 6 parámetros sorteados por semillas de reglas,
con V2 en el taller hasta las 06:40 como evento con fecha y la exigencia de la encargada de la Cafetería Lago Este
(C07) como presión, ambos en hard; véase "Semillas de reglas" más abajo. El límite de bandejas se plantea como un
hecho oculto para todas las furgonetas (cajas nuevas), no solo para V4. Las pruebas del fixture siguen en este caso,
con los cambios mínimos.

### F9 — La redacción coreana del límite de las 07:00 y una etiqueta de columna (baja, confirmado)

`07:00 이전` / `07:00 이후` incluyen ambas las 07:00 en el uso estándar del coreano, así que un tramo que empezaba
exactamente a las 07:00 caía en las dos franjas de velocidad; con salidas al minuto, ese caso es alcanzable. La
etiqueta de columna `최종도착` se lee como "llegada final" y no como un plazo. Las cifras coinciden en los cinco
idiomas.

**Estado:** corregido en este cambio — ko/requirements.md y ko/targets.yaml dicen ahora "07:00 전에 출발하는 구간은
시속 30km, 07:00부터 출발하는 구간은 시속 20km". La columna coreana pasa a llamarse `납품마감` en los datos (case.py)
y en todos los textos coreanos que la nombran.

**Semillas de reglas:** las frases de la velocidad se reescribieron para el nuevo modelo (easy y medium: 25 km/h
constantes; hard: `{{rush_start}} 전까지는 시속 30km, {{rush_start}}부터는 시속 20km`), manteniendo un límite sin
ambigüedad. `납품마감` no cambia.

**Línea base:** el plan del propio coordinador de reparto (V4 se encarga de las cafeterías asociadas; el resto se
reparte por acimut alrededor de la cocina y se carga en V1, V2, V3 y luego V4; premium primero y después por orden de
apertura; todas las furgonetas salen a las 05:00): 963.09 frente a los 625.55 de la referencia con la semilla 20261025
(×1.54). Con las semillas de mundo 1, 2 y 3: 1,292.28 frente a 568.06, 1,192.03 frente a 779.02 y 1,402.46 frente a
560.91. En las semillas 1–50 es válida en todos los mundos, entre ×1.37 y ×4.16 de la referencia (mediana ×2.19).

## Semillas de reglas

El caso ha pasado de un único problema fijo al contrato de semillas de reglas (DESIGN.md, Settings): tres niveles en
case.yaml y seis parámetros que una semilla de reglas sortea, cada uno por separado, entre los candidatos de cada
nivel. Los datos y `request.md` son los mismos en todas las configuraciones; los requisitos, las preguntas clave, las
reglas y la puntuación siguen los valores sorteados.

- **Niveles.** Easy: el límite de bandejas de esta semana, el turno, una sola visita, la cafetería cerrada, 25 km/h
  constantes y el coste del retraso; los requisitos dicen con las palabras del cliente que esta semana el socio lleva
  sus refrigerados él mismo, que la costumbre de atender primero las premium queda en suspenso, que el lunes no hay
  hora punta (no hay colegio) y que la revisión de frenos de V2 es el martes. Medium añade la cadena de frío y la
  costumbre donde se sortea. Hard añade la hora punta (30 km/h antes de `rush_start` y 20 km/h desde esa hora, también
  a mitad de tramo), V2 en el taller hasta las 06:40 (nueva regla `van_ready`) y la presión de la encargada de C07 (no
  es una regla; pregunta clave `manager_pressure`).
- **Parámetros.** `closed_cafe` (C11, C03, C14, nombrados en cada idioma mediante labels), `late_cost` (3, 2, 5),
  `shift_end` (09:30, 09:00, 10:00), `van_capacity` (100, 110, 120 en easy y medium; 110 en hard, así que se compara
  en medium), `rush_start` (none en easy y medium; 07:00, 06:30, 07:30 en hard) y `premium_first` (false en easy; true
  o false en medium y hard). Sin valores derivados; toda combinación es admisible.
- **Panel público.** Semillas de reglas 5, 13 y 58: aparecen todos los candidatos, y la semilla 5 sortea la
  combinación principal de medium y de hard (el fin de turno más tardío, el límite de bandejas más alto y el primer
  candidato del resto).
- **Toda configuración tiene un plan válido.** `build_world` resuelve la combinación más estricta de cada nivel con
  las 18 cafeterías abiertas y guarda el plan como plan de respaldo del nivel; sin la cafetería cerrada sigue siendo
  válido con cualquier sorteo del nivel, semillas privadas incluidas. La referencia parte de él además de la
  construcción voraz.
- **Todos los parámetros influyen**, en cualquier mundo que `build_world` acepte: la cafetería cerrada y el inicio de
  la hora punta, siempre; el fin del turno, el límite de bandejas, el peso del retraso y la costumbre, porque
  `build_world` solo conserva los mundos en los que cambian la referencia de la combinación principal (una furgoneta
  que vuelve después de las 09:00 en hard, una por encima de 100 bandejas en medium, un retraso de al menos el 1% del
  objetivo y una costumbre que cuesta al menos un 1% en hard). El filtro de mundos está calibrado solo sobre los
  candidatos.
- **Cambio en los datos.** `deliver_by` cae 30, 45 o 60 minutos después de la apertura (antes 45, 60 o 90) y el mundo
  aceptado con cada semilla cambió con el nuevo filtro, así que los datos de la semilla del caso y todas las cifras
  difieren de los hallazgos de arriba.
- **Línea base.** Sigue siendo el barrido del coordinador de reparto (V4 se encarga de las cafeterías asociadas cuando
  se aplica la cadena de frío; todas las furgonetas salen a las 05:00, V2 a las 06:40 en hard), válida en todas las
  configuraciones comprobadas (semilla del caso y semillas de mundo 1–30, semillas de reglas 5, 13, 58 y 101–105)
  entre 1.17 y 9.76 veces la referencia.
- **Pruebas.** `tests/test_validator.py` mantiene este caso como su fixture rápido: sus líneas base plantadas y la
  sustitución del ejemplo reciben el argumento de configuración, y dos aserciones se ajustan a los mensajes por
  configuración. `tests/test_end_to_end.py` y `tests/test_isolation.py` escriben la referencia mediante
  `NativeCase.write_reference` y resuelven la semilla de reglas de la especificación antes de buscar una carpeta de
  ejecución. `tests/test_rule_seeds.py` usaba este caso como "un caso sin configuraciones"; ahora escribe para ello un
  case.yaml mínimo sin configuraciones.
- **Abierto:** el margen de mejora sobre la nueva referencia (F2), si flexibilizar la costumbre debe compensar tanto
  (F3), la pregunta `one_visit` (F4), las ventanas de recepción y los nombres de barrio (F7).
