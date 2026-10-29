# Revisión de `customer_service/callcenter_workforce_planner`

Hallazgos de la revisión del caso, con el veredicto del verificador y lo que este cambio hizo con cada uno. Las cifras
corresponden a la semilla pública 20261109 salvo que se indique otra cosa; la calidad se normaliza con la nueva línea base
(rotación fija = 0, referencia voraz = 1).

### F1 — La referencia voraz queda muy por debajo del óptimo (alta, confirmado)

Un MILP exacto del mismo modelo (HiGHS de scipy, unas 2,000 variables binarias, optimalidad demostrada en unos 8 s) llega a
23,464 frente a los 25,584 de la referencia (ratio 1.090; 75 frente a 183 agentes-franja sin cubrir). En el momento de la
revisión la calidad se recortaba en 1.0, así que este margen no daba ningún punto, e ignorar el festivo, el recargo por horas
extra o el peso no costaba nada. Con el nuevo marco (sin recorte por arriba, puntuación completa en el tope de la política de
1.5) y esta línea base, el óptimo obtiene 1.180, un óptimo que ignora el festivo 1.145 y uno que ignora las horas extra o el
peso 1.172. Estas diferencias ahora cuentan, pero son pequeñas.

**Estado:** abierto — propuesta: mantener el algoritmo voraz como referencia y fijar `quality_cap: 1.18` en `case.yaml`, la
calidad normalizada del óptimo MILP con esta semilla (1.1798). El objetivo óptimo es único, así que el valor es determinista.
El óptimo obtendría entonces la puntuación completa y la referencia 0.85, en lugar de 0.67 con el tope por defecto. Las
semillas de mundo 1–3 alcanzan 1.135–1.177, de modo que en las semillas privadas el tope queda un poco por encima de lo
alcanzable. Una comprobación del validador de que ignorar cada pregunta clave que solo afecta a la calidad cuesta al menos un
3% obligaría además a reajustar F3 y F5.

### F2 — Sin configuraciones (alta, confirmado)

`setting.json` es `{}` y hay una sola solución correcta, así que las columnas easy, medium y hard son el mismo problema y el
caso no aporta nada a la curva de dificultad. El peso de la falta de personal bastaría por sí solo para formar conjuntos de
reglas útiles: los óptimos con W = 15, 25 y 40 usan 109, 116 y 126 turnos, y puntuados de forma cruzada dan 0.908–0.991.

**Estado:** abierto — propuesta: pasar a 3 niveles × 3 conjuntos de reglas sobre el mismo mundo. Parámetros de los conjuntos
de reglas: el peso (p. ej. 12/25/40, de modo que la referencia de cada conjunto sea al menos un 1% peor con los demás), el día
y el factor del festivo, el umbral de horas extra, el tope de media jornada y las horas de descanso (13 h prohíbe
S1400 → S1000). Niveles: easy es la planificación básica del cuadrante, medium añade el descanso, el festivo, las horas extra
y la regla de acompañamiento, y hard añade las partes inciertas. Según el verificador, para un nivel con Erlang C las llamadas
y el tiempo de gestión tendrían que estar en los datos que ve el agente en todos los niveles, y una replanificación a mitad de
semana convertiría todo el caso en un entregable de programa.

### F3 — Ratio de calidad comprimido; el peso aplasta el coste de personal (media, en parte)

Un solo turno (A01, lunes, S0800, en) era un cuadrante válido con ratio 0.378, y el ratio del cuadrante vacío sería 0.376. El
peso de 40 por media hora (80 por agente-hora, frente a tarifas de 22 y 18) hace que casi cualquier turno compense su coste, así
que el óptimo usa 126 de los 130 turnos posibles. El peso no tenía un significado declarado.

**Estado:** corregido en este cambio — los requisitos en los cinco idiomas indican ahora qué significa el 40: está en las mismas
unidades que las tarifas por hora y es la estimación del cliente de lo que cuesta que falte un agente durante media hora en
llamadas abandonadas, rellamadas y niveles de servicio incumplidos (el número no cambia). El suelo alto desaparece con la
normalización por la línea base: el cuadrante de un solo turno obtiene −2.57, que se trunca a 0. Sigue abierto — propuesta:
bajar el peso al rango 15–30 o variarlo por conjunto de reglas (F2), donde las horas extra y la elección entre jornada completa
y media jornada sí pesan. La restricción obligatoria de cobertura mínima que se sugirió no tiene solución en este mundo (el
verificador: solo hay 4 agentes zh veteranos).

### F4 — La regla flexibilizable nunca compensa; no hay presión ni eventos con fecha (media, confirmado)

`buddy_rule` es la única regla flexibilizable. Flexibilizarla mejora el óptimo un 0.58% (23,328 frente a 23,464), y un
0–2.3% en otras semillas. Eso equivale a unas 0.01 de calidad normalizada, y menos en la puntuación compuesta, muy por debajo
de la penalización de 0.05–0.1 por incumplir una regla flexible. El caso no tiene nota de ninguna parte interesada, aviso de
baja por enfermedad, revisión de la previsión ni aprobación tardía de ausencias; solo existen los eventos genéricos de la
modalidad `messy`.

**Estado:** abierto — propuesta: dar forma a los datos para que flexibilizar compense en una cantidad visible pero acotada,
p. ej. una tarde o un domingo de zh en que el único agente con zh que queda es A12, de nuevo ingreso, con un valor de un 3–8%
frente a la referencia. Añadir una nota del jefe de equipo ("A12 puede encargarse del chino sin apoyo el domingo por la noche, póngalo sin
más") como la tentación que tiene que pasar por el procedimiento de excepción. Añadir un evento con fecha, p. ej. un aviso de
baja por enfermedad o una aprobación tardía de ausencia el jueves, entregado como corrección en la bandeja de entrada.

### F5 — Hechos ocultos que no tienen efecto (media, en parte)

El redondeo hacia arriba sobre enteros pequeños amortigua el festivo: 106 de las 140 celdas del miércoles no cambian, así que
la demanda del miércoles baja de 265 a 229 agentes-franja (−13.6%, no −40%), e ignorar el festivo solo le cuesta al óptimo
1.180 → 1.145. Tratar la solicitud rechazada (A03) como ausencia deja el óptimo igual. La fila rechazada decía
`12/11/2026–13/11/2026`, y un día mayor que 12 delata el formato día/mes/año. Algunas preguntas clave (`slot_coverage`, la
parte de contrato de `contract_limits`) se pueden deducir de los nombres de las columnas.

**Estado:** corregido en este cambio (solo la fecha) — la solicitud rechazada queda ahora dentro del lunes 9 al jueves 12 (A03
dice `12/11/2026–12/11/2026`), de modo que los datos públicos no tienen ningún día mayor que 12. Una solicitud rechazada nunca
afecta a la puntuación, así que no cambia el óptimo de ningún mundo. Leídas como mes/día, las fechas siguen cayendo entre
septiembre y diciembre, por lo que un agente atento todavía puede deducir el formato. En las semillas de mundo 1 y 3, las
ausencias aprobadas de viernes a domingo siguen mostrando los días 13–15. No reproducido: la parte del descanso. Un optimizador
que no conoce la regla produce 13 infracciones de `min_rest`, así que el descanso es una trampa obligatoria que sí tiene efecto. Sigue
abierto — propuesta: expresar la demanda en unidades más grandes (p. ej. 2–12 por franja) o redondear al más cercano, de modo
que ignorar el festivo cueste al menos un 3%. Asignar la solicitud rechazada a un agente escaso en un día de pico. Marcar las
preguntas clave que se pueden deducir de los datos, o eliminarlas, para que el Ask-F1 no premie preguntarlas.

### F6 — Realismo y tipos de regla (media, en parte)

La semana normal de jornada completa es de 4 turnos (32 h), y el 5.º es hora extra. Los turnos cuentan en las 16 franjas sin
pausas, y la previsión ya está en agentes, lo que se salta el paso de Erlang C de la planificación de personal. `min_rest` se
clasifica como física aunque es una norma laboral, y 11 h queda por debajo de las 12 h legales de España (Estatuto de los
Trabajadores, art. 34.3). Las tarifas no tienen moneda. El verificador señala que una semana contractual de 32 h es poco
habitual pero legal, y que reclasificar `min_rest` no cambia ninguna puntuación (ambos tipos son obligatorios en todas las
políticas).

**Estado:** abierto — propuesta: hacer que la semana normal sea de 5 turnos (40 h), con horas extra por encima de eso bajo un
tope de 6 turnos, o decir explícitamente que el contrato es de 32 h. Reclasificar `min_rest` como contractual y dejar "un solo
turno a la vez" como la regla física. Usar 12 h de descanso en todos los idiomas: con estos horarios de turno prohíbe
exactamente los mismos pares de turnos que 11 h (ningún par está separado por 11 h), así que solo cambian el texto y
`MIN_REST`. Nombrar la unidad de coste (p. ej. "unidades de coste", o una moneda local con los números escalados). Dejar las
pausas y Erlang C para un nivel hard (F2).

### F7 — Redacción por idioma y neutralidad de país (baja, confirmado)

Los números coinciden en los cinco idiomas, pero el 11 de noviembre como festivo de bajo volumen choca con el Día de los
Solteros (Singles' Day) para un cliente chino. El texto coreano repetía 근무 ("근무하는 근무 하나당"), usaba la expresión
calcada "신입이 아닌 상담원", enterraba la fórmula en un paréntesis largo con un 40 sin unidad y etiquetaba la jornada completa
como 정규직 (empleo fijo). Los nombres están en alfabeto latino en todos los idiomas y se asignan sin relación con los idiomas
que habla cada agente (p. ej. "Haruto Kim" solo habla ja).

**Estado:** corregido en este cambio — el festivo es ahora "festivo regional en nuestro mercado principal" en los requisitos
y en la pregunta clave de los cinco idiomas (fecha y 60% sin cambios). Coreano: "상담원 1명의 근무 1회당 항목 1개입니다",
"기존(신입이 아닌) 상담원/동료" en los requisitos y en la pregunta clave, y el párrafo de calidad nombra ahora sus dos partes y da
unidad al 40 ("부족한 상담원 1명·30분당 40(인건비와 같은 단위)"). La jornada completa es 풀타임 en la etiqueta de los datos
(`고용형태`), en los requisitos y en las preguntas clave. Sigue abierto — propuesta: escribir los nombres según el idioma (hangul,
kanji/kana, hanzi) o vincularlos al idioma principal del agente.

### F8 — El formato del cuadrante no se muestra al agente (baja, en parte)

Al agente se le dice que no se especificó ningún formato de archivo. La forma exacta del JSON solo está en los requisitos
ocultos, así que un cuadrante de unas 120 filas puede pasar por el extractor, y una sola fila mal transcrita lo invalida. El
verificador señala que basta una pregunta al cliente para obtener el formato, que un `roster.json` escrito por el agente se
copia directamente y que el extractor puede convertir un CSV con un script. La etiqueta "agent-visible" de la página
explicativa se corrigió después en el marco.

**Estado:** abierto — propuesta: añadir, antes del extractor LLM, un analizador previo determinista para las formas habituales
de cuadrante (CSV/xlsx con columnas de agente, día, turno e idioma, nombres de idioma localizados) y registrar las infracciones
que introdujo el extractor por separado de las del agente. Otra opción es dejar una plantilla de cuadrante en el espacio de
trabajo. Cualquiera de las dos es una decisión del marco o del diseño, no una corrección del caso.

**Línea base:** rotación fija (el mismo turno toda la semana en el idioma principal, 4 días normales para jornada completa y 3
para media jornada, las personas de nuevo ingreso acompañando a un veterano), objetivo 37,376 frente a los 25,584 de la
referencia (ratio 0.685) con la semilla 20261109; 36,776–37,848 frente a 25,232–25,440 en las semillas de mundo 1–3. El caso
no tiene configuraciones.
