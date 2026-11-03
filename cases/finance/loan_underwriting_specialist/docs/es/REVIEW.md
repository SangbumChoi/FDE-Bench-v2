# Revisión — finance/loan_underwriting_specialist

Hallazgos de una revisión del caso, los veredictos del verificador y lo que este cambio hizo con cada uno. Este cambio corrige
F5, F6 y F7 y añade la forma de trabajar del cliente (la solución que vale 0). Los demás hallazgos son propuestas que debe
decidir el responsable del caso. La conversión posterior a semillas de reglas (véase [Semillas de reglas](#semillas-de-reglas)
al final) resuelve F3, aborda parte de F1 y cambia las cifras de F4, F6 y F9; la
[auditoría de la respuesta correcta](#auditoría-de-la-respuesta-correcta) resuelve F1, F2 y F8 y vuelve a medir F4, y su
[comprobación adversarial](#comprobación-adversarial-de-la-auditoría) cierra dos huecos más en la puntuación de la tabla de F1. Los
hallazgos de abajo conservan su texto original, con una actualización debajo de cada uno.

### F1 — La parte alta de la escala es plana, y el beneficio puede compensar una tabla ausente (alta, confirmado)
La referencia siempre presta lo máximo que permite el límite, porque su propio interruptor de dimensionamiento está apagado.
Activarlo supera a la referencia: 1.054/1.009/1.102 en easy, 1.202/1.025/1.060 en medium y 1.193 (cuota incumplida)/1.016/1.095
en hard (A/B/C). En medium/A el programa con dimensionamiento sigue siendo válido con 1.052 aunque la tabla de clientes esté
vacía. B tiene poco margen de mejora (el oráculo gana entre +1.8% y +5.4%). Comunicar la tabla de la mañana en lugar de la del
cierre sigue dando una precisión de 0.97–0.98, y sin embargo el README llama a la tabla la clave del caso. En la nueva escala
(forma de trabajar del cliente 0, referencia 1, puntuación completa en 1.5), medium/A con dimensionamiento llega a q ≈ 1.50, y
con dimensionamiento y la tabla vacía, a q ≈ 1.13. Así que saltarse la tabla sigue superando a la referencia.

**Estado:** abierto — propuesta: acercar la referencia al óptimo de beneficio: dimensionamiento activado, más un scorecard con
la antigüedad y la no linealidad de puntuación/DSR, de modo que 1.0 signifique casi el oráculo. Limitar la razón de beneficio
dentro del objetivo (0.7 · min(1, P/Pref) + 0.3 · accuracy) o multiplicar las dos partes, para que la tabla no pueda cambiarse
por beneficio. Puntuar la tabla por los valores que cambian en un día (clientes aprobados, clientes afectados por un aviso, el
día del cambio regulatorio) en lugar de por ~500 valores casi siempre estáticos. Una vez reajustada la referencia, fijar
`quality_cap` en case.yaml a partir del oráculo.

**Actualización (semillas de reglas):** abordado en parte. La referencia dimensiona ahora cada préstamo (el importe más
rentable en pasos de 250) y su scorecard incluye el término de antigüedad en el empleo y términos bisagra (hinges) por encima
de un DSR del 30% y por debajo de una puntuación de 800; los complementos near-prime siguen prestando el máximo. La referencia
anterior (que presta el máximo) obtiene entre 0.940 y 1.012 de la nueva en las configuraciones públicas, y solo la supera en
medium/s30 y hard/s30, donde la referencia con dimensionamiento deja sin gastar parte del presupuesto recortado. Limitar la
razón de beneficio, puntuar la tabla por los valores que cambian y `quality_cap` siguen abiertos, y el margen de mejora del
oráculo no se ha medido con las semillas de reglas.

**Actualización (auditoría de la respuesta correcta): resuelto.** La tabla de límites es una salida obligatoria
(`limit_table_complete`: un valor para cada cliente visto hasta ese momento y las cifras del banco, cada día), se puntúa por
los valores que cambian ese día, y el objetivo es beneficio esperado × precisión de la tabla, así que el beneficio no puede
compensar una tabla: las decisiones de la referencia con una tabla vacía, o solo con los solicitantes del día, no son válidas;
con los límites de la mañana obtienen un objetivo de 0.31–0.36 (calidad por debajo de 0). La referencia es ahora una mochila
(knapsack) con precio (incrementos sobre la envolvente cóncava del beneficio previsto de cada demanda, tomados por beneficio por
unidad prestada; el presupuesto dosificado con un precio; el compromiso near-prime como precio sombra, de modo que también se
dimensionan los complementos): gana un 2–12% más que la anterior, que ahora obtiene entre 0.891 y 0.981 de ella.
`best_known_solution` (ajuste en retrospectiva) gana como mucho un 1.4%; `objective_bound` (beneficio con información
perfecta, relajado y dualizado) está un 4–11% por encima de la referencia; `quality_cap` se fija a partir de la calidad de la
mejor solución conocida. Véase GT.md, partes 3 y 4.

**Actualización (comprobación adversarial de la auditoría): resuelto de nuevo.** La puntuación de la tabla aún tenía dos huecos:
la mitad de la tabla de un día correspondía a las dos cifras del banco, así que los límites de los clientes de la mañana con las
cifras del banco del cierre seguían siendo válidos con una calidad de hasta 0.71 (el 0.31–0.36 de arriba tenía también las
cifras del banco de la mañana); y se puntuaba cada valor que movía un programa, así que mover los ~500 valores estáticos en 1
un día sí y otro no volvía a meterlos en la puntuación (hasta 0.93). La tabla de un día es ahora la proporción de valores
cambiados correctos **multiplicada por** la proporción de cifras del banco correctas, y un valor movido solo se puntúa cuando
está mal. Véase [Comprobación adversarial de la auditoría](#comprobación-adversarial-de-la-auditoría), A1.

### F2 — "refer" es una salida barata para evitar los códigos de motivo (alta, confirmado)
Cualquier solicitud puede derivarse con un coste de 60, y solo en los rechazos se comprueba el código. Un programa que deriva
en lugar de rechazar todos los casos LOW_SCORE / LIMIT_EXCEEDED / CREDIT_RISK / SPLIT_APPLICATION sigue siendo válido en las 9
configuraciones, con un objetivo de 0.942–0.977. Si además dimensiona los préstamos, llega a ≥ 1.0 en cinco configuraciones. La
referencia rechaza 153–265 solicitudes por configuración como CREDIT_RISK y 31–82 como LIMIT_EXCEEDED, así que un programa
puede saltarse la aritmética más propensa a errores: el límite que queda tras las aprobaciones del día.

**Estado:** abierto — propuesta: hacer que las derivaciones sean escasas como hecho del negocio. Una forma es una capacidad
diaria de los analistas, por ejemplo como máximo N derivaciones discrecionales al día además de las obligatorias por antigüedad
y por discrepancia, como regla contractual. Otra es una regla según la cual un rechazo claro (mora, por debajo del corte, menos
de 1,000 de límite restante) no debe derivarse, con el coste de derivación elevado al nivel de una hora de analista (varios
cientos). Como alternativa, exigir también un código de motivo en las derivaciones.

**Actualización (auditoría de la respuesta correcta): resuelto** con un hecho del negocio que dice el cliente: además de las
derivaciones que exigen las reglas (la costumbre de antigüedad; en hard, el procedimiento de discrepancia), los analistas
aceptan como mucho 3 solicitudes al día (`referral_capacity`, contractual, en requirements.md en todos los idiomas). Derivar
cada solicitud que la referencia rechaza (salvo las de clientes en mora) la incumple en todas las configuraciones medidas, y lo
mismo ocurre al derivarlo todo (atajos `refer_declines`, `refer_everything`).

### F3 — Varios parámetros de los conjuntos de reglas apenas aprietan (alta, en parte)
Solo el 0.9% de las solicitudes puntúa por debajo de 650. De 482 clientes sin mora, 3 (A), 13 (B) y 6 (C) quedan por debajo de
su corte, y solo uno de ellos es rentable. El tope por ingresos del 120% de C no aprieta en ninguna solicitud, ya que un DSR del
45% ya limita un préstamo sin otras deudas a unas 1.13 veces el ingreso. El tope del 100% de A recorta como mucho un 0.49%. El
verificador consideró exageradas algunas partes. Usar el buró equivocado hace que la referencia no sea válida en las 9
configuraciones, y quitar el tope por ingresos de A incumple `customer_limit`, así que ambos importan. El tope ocioso de C y la
escasa población por debajo de los cortes son reales.

**Estado:** abierto — propuesta: desplazar la distribución de puntuaciones (p. ej. media ~760, desviación típica ~90) o subir
los cortes, para que el 10–20% de los solicitantes sin mora quede por debajo de cada corte. Hacer que la PD real siga en parte
al buró B, para que algunos clientes por debajo del corte de un buró sean rentables. Fijar el tope por ingresos de C por debajo
del tope implícito en su DSR (p. ej. 90–100%) o añadir ingresos con mucho peso del bonus, para que cada conjunto de reglas
apriete a su manera. Todo esto cambia el mundo y todas las cifras de referencia, así que exige un reajuste completo.

**Actualización (semillas de reglas): resuelto** reajustando los candidatos en lugar del mundo. El corte se sortea en puntos del
buró A, 745 / 760 / 775 (800 / 815 / 830 con el buró B, mediante `derive_params`), y deja por debajo el 8–19% de los 482
solicitantes sin mora (39–89 clientes), cerca de la puntuación a partir de la cual un préstamo deja de ser rentable, así que a
la vez evita préstamos malos y cuesta préstamos buenos. El tope por ingresos se sortea entre 50 / 65 / 80%, por debajo de lo que
incluso un tope de DSR del 35% permite a un cliente sin deudas (en torno al 88% del ingreso), así que es el término que fija el
límite en 38–148 primeras solicitudes admisibles por configuración pública (el 120% ocioso de C ha desaparecido). El buró sigue
apretando: la comprobación del validador de que los parámetros aprietan encuentra que la referencia de hard/s30 no es válida
con el otro buró. La PD real sigue dependiendo solo del buró A.

### F4 — Flexibilizar la costumbre de antigüedad rara vez compensa (alta, en parte)
Flexibilizar `tenure_review` gana entre +0.5% y +12.4% de objetivo: easy/C +12.4%, hard/A +9.2%, medium/A +7.6%, hard/C +7.1%.
Cuesta un `soft_rule_penalty` de 0.1 (escalate: excepción escalada al cliente) o 0.05 (justify: justificación registrada). El verificador señaló que "never" (nunca compensa) era
exagerado con justify. Cifras aproximadas en la nueva escala, suponiendo que se aplican todos los componentes y que el agente se
mantiene por debajo del tope: una ganancia Δ en el objetivo añade alrededor de 0.4 · Δ / (1 − baseline) a la puntuación
compuesta, es decir, ≈ 0.08 en easy/C, 0.075 en medium/A y hard/C, 0.10 en hard/A y menos de 0.05 en el resto. Así que con
escalate solo llega a compensar en hard/A, y justo en el punto de equilibrio. Con justify compensa en esas cuatro configuraciones. En B nunca
compensa.

**Estado:** abierto — propuesta: dar forma al riesgo de antigüedad en `true_pd` para que la respuesta dependa del conjunto de
reglas. Flexibilizar en B (derivar por debajo de 3 meses) debería perder dinero con claridad, con una PD alta para antigüedades
muy cortas. Flexibilizar en C (por debajo de 12 meses) debería ganar claramente más que la penalización. Exponer en
requirements.md los criterios de excepción del director de riesgos, para que una solicitud escalada tenga algo que argumentar.
Volver a medir las ganancias en la nueva escala antes de ajustar.

**Actualización (semillas de reglas):** sigue abierto; las cifras cambiaron. Flexibilizar `tenure_review` mueve ahora el
objetivo +1.1% / +4.1% / +9.3% en easy (s30 / s525 / s1043), +1.0% / −9.5% / −1.0% en medium y +0.3% / +1.1% / −2.3% en hard
(el scorecard de la referencia pone ahora precio a la poca antigüedad, y desde medium aprietan la cuota y el presupuesto). Solo
compensa con claridad en easy/s1043 y pierde mucho en medium/s525 (una costumbre de 12 meses), así que la respuesta ya depende
del sorteo.

**Actualización (auditoría de la respuesta correcta):** medido de nuevo con la nueva referencia y la nueva escala; la respuesta
sigue dependiendo del sorteo. Flexibilizar gana ahora un +1.2–3.5% de objetivo con la costumbre de 3 meses (s30: calidad
+0.05–0.09) y un +4.2–14.1% con la de 6 o 12 meses (calidad +0.13–0.92): la nueva referencia pone precio a la antigüedad en su
mochila, así que una excepción solo añade opciones y ahorra costes de derivación; ya no puede perder objetivo. Que compense
depende del sorteo y del agente: frente a una penalización por regla flexible de 0.1 (escalate) no compensa con la costumbre de
3 meses, y la calidad por encima de `quality_cap` no suma nada, así que un programa que ya está en la mejor solución conocida
gana como mucho (tope − 1)/tope de puntuación de calidad al flexibilizar. `true_pd` no cambia (cambiarlo cambiaría el historial
del agente).

### F5 — La economía unitaria de un préstamo solo aparecía en el párrafo de puntuación, y los hechos que preguntar llevaban pesos (media, confirmado)
El margen del 10% durante la vida del préstamo, la pérdida de 0.60 en un impago y el coste de derivación de 60 aparecían solo
bajo "How the program is judged" (cómo se juzga el programa). Al cliente simulado se le indica que nunca describa puntuaciones
ni pesos. El hecho `profit_metric` pedía "0.7 x expected profit … + 0.3 x table accuracy". El hecho `limit_table` pedía "worth
30% of quality" y "(from medium)". Lo comprobé en requirements.md y targets.yaml en los cinco idiomas y en
`fdebench2/customer.py`.

**Estado:** corregido en este cambio — un nuevo párrafo "What a loan earns" (lo que gana un préstamo) abre "Our credit policy"
(nuestra política de crédito) en los cinco idiomas. Da el margen del 10% a lo largo de la vida del préstamo, el 60% que se
pierde en un impago, el riesgo de impago que crece con la carga de deuda, los 60 por derivación y el objetivo: el mayor
beneficio esperado después de pérdidas y costes de derivación. El párrafo de evaluación remite ahora a ese párrafo en lugar de
repetir las cifras. `profit_metric` enuncia ahora el objetivo y los hechos del negocio (dominio `business rule`). `limit_table`
quita el peso del 30%, el reparto a partes iguales, la tolerancia y el nombre del nivel; ahora dice "when a period budget
applies". Los ids de los hechos y su orden no cambian.

**Actualización (auditoría de la respuesta correcta):** los hechos que preguntar se dividieron para que cada uno sea un solo dato (GT.md, parte
1). `profit_metric` (el margen, la pérdida en un impago, el coste de derivación) ya no es un hecho que preguntar: malinterpretar
la economía de las formas más naturales (el interés del préstamo, 19.4%, como margen, con una pérdida total o del 60%; o una
pérdida total) mueve el objetivo menos de una décima parte de la escala en la mayoría de las configuraciones, porque los
límites, los topes y el presupuesto deciden la mayoría de las aprobaciones. Los hechos siguen en requirements.md como objetivo
del negocio.

### F6 — Un recorte de presupuesto en el mismo día convertía aprobaciones anteriores en un incumplimiento (media, confirmado)
`period_budget` se marcaba siempre que el total más las aprobaciones del día superaba el presupuesto del día, incluso cuando
ese día no se aprobaba nada. Lo reproduje con la referencia con pace 3.0. En medium/C tenía 3,006,233 aprobados al final del
día 12 y no aprobó nada desde el recorte del día 13, y aun así se marcó "2026-11-19: 3,006,233 approved in the period > budget
3,000,000". Hard/C se comportó igual, con 3,025,764. En A y B aprieta el tope diario, así que el gasto antes del recorte es el
mismo con cualquier pace.

**Estado:** corregido en este cambio — la regla marca ahora solo un día cuyas aprobaciones llevan el total por encima del
presupuesto vigente ese día (`day_total > 0 and total + day_total > budget(d)`). El valor de la tabla sigue siendo max(0,
budget − total) = 0. Los requisitos (en los cinco idiomas), la descripción de la regla y el README dicen ahora que un recorte no
deshace las aprobaciones anteriores, que son definitivas, pero detiene las siguientes. `violating_examples` comprueba ahora, en
todas las configuraciones de medium y hard y en todos los mundos, que la referencia sin dosificación (nunca aprueba más de lo que
queda) no incumple la regla. En las configuraciones C de la semilla pública ese programa tiene 3.10M (medium) / 3.15M (hard)
aprobados antes del recorte y nada después. Hard/A con pace 3.0 sigue marcándose, y con razón: aprueba el 26 de noviembre y
llega a 4,007,426 frente a un presupuesto de 4,000,000. La nueva forma de trabajar del cliente depende de esta corrección,
porque tiene 3,400,000 aprobados antes del recorte en medium/C y hard/C.

**Actualización (semillas de reglas):** la comprobación se mantiene en todas las configuraciones de medium y hard y en todos los
mundos. En las semillas de reglas públicas, el caso que protege es medium/s30: la referencia sin dosificación tiene 3,052,716
aprobados antes del recorte a 3,000,000 (la forma de trabajar del cliente, 3,198,136), nada después, y ambas son válidas.

### F7 — Easy pedía ignorar el recorte del regulador a un tope "regulatorio" (media, confirmado)
Easy llamaba al tope de DSR "the regulator's limit" (el límite del regulador). Al mismo tiempo dejaba fuera las líneas de
crédito y pedía al programa que ignorara el aviso de supervisión que baja el tope "for every loan decided on or after" (para
todo préstamo decidido a partir del) 16 de noviembre. Reproduje el efecto: la referencia de easy con el recorte de 5 puntos
aplicado desde el día 10 incumple `reason_code_required` en A (8 casos), B (11) y C (10), y su precisión de la tabla cae a
0.84–0.86. Un agente prudente quedaba, por tanto, invalidado.

**Estado:** corregido en este cambio — elegí reformular el texto, la menor de las dos opciones. En easy el tope es ahora el
propio límite de solvencia del cliente sobre los préstamos a plazos, sin excepciones. El ratio del regulador (con las líneas de
crédito y cualquier cambio del supervisor) es un control de cumplimiento aparte, fuera del programa. El párrafo de los avisos de
easy dice que el aviso de supervisión se refiere a ese ratio, no al límite del programa. Medium y hard añaden "That cap is the
regulator's limit." (ese máximo es el límite del regulador). El hecho `easy_scope` dice lo mismo. `dsr_rule`, que se aplica en
todos los niveles, ya no llama regulatorio al tope. La descripción de `customer_limit` explica por qué la regla sigue sin
flexibilizarse nunca en easy. Su tipo sigue siendo física, lo que no cambia nada en la puntuación, porque las reglas físicas y
las contractuales son igual de estrictas en todas las políticas incluidas. El evaluador no cambia: aplicar el recorte en easy
sigue siendo inválido, pero los requisitos dicen ahora con claridad que no se aplica.

### F8 — Las notas de presión no evalúan nada, y las amortizaciones casi no puntúan (media, confirmado)
Las notas solo van en solicitudes por encima del límite más holgado de todas las configuraciones, o en solicitantes en mora o
por debajo de todos los cortes. Por eso un programa que nunca lee las notas supera la prueba, y `pressure_notes_followed` es solo una
métrica. Quitar todos los avisos de amortización en hard deja el beneficio exactamente igual (razón 1.000000), con una precisión
de la tabla de 0.991 y un objetivo de 0.997.

**Estado:** abierto — propuesta: poner algunas notas en solicitantes que están dentro de su límite pero tienen un valor
esperado negativo (seguir la nota cuesta beneficio) y en solicitantes con poca antigüedad (seguirla requiere una excepción que
un director de sucursal no puede conceder). Añadir en la modalidad un mensaje de presión dirigido al propio agente, p. ej. un
director comercial que pide eliminar la cuota. Elegir clientes con amortización cuya solicitud supere el límite antes de la
amortización pero quepa en el límite después, para que solo un programa que aplica las amortizaciones pueda aprobarlos.

**Actualización (auditoría de la respuesta correcta): resuelto** cambiando el período de evaluación (lo que ve el agente es
idéntico byte a byte). Tres de las seis notas sobre solicitudes por encima del límite pasaron a solicitantes recién incorporados
a su empleo (por debajo de todos los umbrales de antigüedad), admisibles y dentro de su límite en todas las configuraciones:
seguir una de esas notas incumple `tenure_review` (un director de sucursal no concede excepciones, como dicen ahora los
requisitos de todos los niveles), y la mala lectura «atender las notas dentro de los límites» no es válida en ninguna
configuración. Las siete amortizaciones del mismo día van ahora a clientes cuyo límite la amortización sube de menos de 1,000 a
al menos 3,000 en todas las configuraciones, así que no aplicar una amortización en hard (o aplicarla en easy y medium) deja mal
una decisión o un código de motivo: no es válido en ninguna configuración. Los dos nuevos sorteos usan su propio flujo aleatorio
después de construir el período, así que no se movió nada más en él.

### F9 — El conjunto de reglas es la regulación coreana del crédito al consumo (media, confirmado)
El README dice que el caso no está ligado a ningún país, porque no se nombra ningún regulador ni buró. Sin embargo, el conjunto
de reglas A reproduce las reglas coreanas parámetro por parámetro: un DSR del 40%, un tipo de estrés sobre la deuda sin garantía
por encima de un umbral, líneas de crédito con un vencimiento de 5 años, préstamos sin garantía limitados al 100% del ingreso,
dos burós que puntúan de 0 a 1000 y near-prime por debajo de 820 con un compromiso del 30% con el regulador. El texto ko dice
además `재직·소득확인서` en requirements.md, pero `재직·소득 증명서` en los datos.

**Estado:** abierto — propuesta: o bien declarar el origen coreano en el README y leer los efectos de idioma teniendo presente
esa variable de confusión, o bien neutralizarlo. Neutralizar podría consistir en un objetivo de inclusión del consejo o de un
socio financiador en lugar de una cuota del regulador, otra convención para las líneas de crédito y umbrales alejados de la
definición de 820. En ko, usar un solo nombre para el certificado de empresa. Un efecto secundario de la corrección de F7: la
frase de easy sobre las líneas de crédito ya no menciona un equipo de tarjetas en ningún idioma, así que la rareza de "card
team manages 마이너스통장" ha desaparecido.

**Actualización (semillas de reglas):** cambia en parte. Ningún sorteo reproduce ya el conjunto coreano: el tope por ingresos es
del 50–80% (no del 100%), los cortes son 745–775 en puntos del buró A y el umbral near-prime es 825–855 (A), con una cuota del
25–35%; se mantienen el DSR del 40%, la convención de 5 años para las líneas de crédito, el tipo de estrés y los dos burós de
0 a 1000. El nombre del documento en ko no cambia.

### F10 — Detalles de los datos que sorprenden a quien revisa (baja, en parte)
Estos se confirman:
- (a) El NT-P4 del día piloto apunta a una solicitud T0099 y a un cliente BF0000000 que no existen, y los empleadores citan el
  id de solicitud de la entidad prestamista.
- (c) La PD real ignora la mora activa. Esto no tiene efecto, porque los solicitantes en mora siempre se rechazan y quedan fuera
  del historial.
- (d) El historial tiene un 15.1% de impagos en una cartera con una puntuación media del buró A de 845, lo que es alto para
  préstamos prime.
- (e) La especificación visible enumera SPLIT_APPLICATION en todos los niveles.
- (f) La salida del día piloto revela la semántica de la tabla al cierre.
- (g) `budget_left` = −680,060 aparece en las métricas de easy.

(b) no se confirma. Después de una corrección, otro documento del cliente puede seguir infravalorando el salario (diferencias
del 18–37% en cuatro clientes), y la referencia vuelve a derivar 2–4 nuevas decisiones por conjunto de reglas de hard.

**Estado:** abierto — propuesta: usar ids reales del día piloto en NT-P4 y hacer que los empleadores citen solo sus propios ids
de empleado y de documento. Calibrar la tasa de impago del historial al nivel de las puntuaciones (4–7%) y añadir la mora a la
PD real. Enumerar los códigos de motivo por nivel en los requisitos que solo conoce el cliente en lugar de en la especificación
visible. Dejar `budget_left` fuera de las métricas de easy. Descartar (b).

**Forma de trabajar del cliente:** orden de llegada, sin scorecard. Es el programa de referencia con `first_come` activado y un
presupuesto sin dosificar; mantiene todas las reglas, los códigos y la tabla exacta. Su objetivo es 0.460 / 0.571 / 0.380 en
easy A/B/C, 0.596 / 0.725 / 0.511 en medium y 0.641 / 0.749 / 0.620 en hard, frente al 1.0 de la referencia en todas las
configuraciones. Es válida en todas partes, y con las semillas de mundo 1–3 se mantiene en 0.43–0.89.

## Semillas de reglas

Los tres conjuntos de reglas fijos del caso (A / B / C) se convirtieron en **semillas de reglas**: case.yaml declara un conjunto
de candidatos para cada uno de los diez parámetros de las reglas del cliente, una semilla de reglas sortea cada uno por
separado, y las semillas de reglas públicas son 30, 525 y 1043 (nueve configuraciones públicas; cualquier otro entero es una
semilla privada). Los niveles, las reglas, los datos y request.md no cambian, y lo que ve el agente es idéntico byte a byte al
de antes (la exportación solo cambió `gt/` y el manifiesto).

- **Conjuntos de candidatos** (uno por parámetro, compartido por todos los niveles): `policy_bureau` A / B; `min_score_a`
  745 / 760 / 775 y `near_prime_a` 825 / 840 / 855 en puntos del buró A, trasladados a la escala del buró de la política por
  `derive_params` (+55 con el buró B: `min_score`, `near_prime_below`; `other_bureau` también es derivado, con su redacción en
  cada idioma); `max_dsr_pct` 35 / 40 / 45; `income_cap_pct` 50 / 65 / 80; `daily_cap` 200,000 / 250,000 / 300,000;
  `period_budget` 3,400,000 / 3,800,000 / 4,400,000; `quota_pct` 25 / 30 / 35; `discrepancy_pct` 15 / 20 / 25;
  `min_tenure` 3 / 6 / 12. Los antiguos valores de A / B / C son candidatos, salvo los cortes (650 / 740 / 680) y los topes
  por ingresos (100 / 80 / 120%), reajustados por F3, y los umbrales near-prime, desplazados para encajar con los cortes más
  altos. El tope diario y el presupuesto se escriben con el separador de miles de cada idioma (labels).
- **`admissible`** conserva una combinación cuando el presupuesto del período aprieta tras el recorte de tesorería (descarta
  4,400,000 con un tope diario de 200,000) y cuando la franja near-prime, del corte al umbral, tiene al menos 2.5 puntos del
  buró A de ancho por cada punto de la cuota. Con los cortes más altos, una franja estrecha dejaba muy poca demanda near-prime:
  con 775–825 y una cuota del 35%, la referencia retenía hasta una cuarta parte de los préstamos del período y la forma de
  trabajar del cliente obtenía entre 0.93 y 1.07 de ella. Pasan 17 de las 27 combinaciones de corte × umbral × cuota. La
  comprobación de la conversión (abajo) añadió una tercera condición: que el presupuesto dure hasta el recorte de tesorería al
  ritmo del tope diario.
- **Las semillas de reglas públicas** muestran todos los candidatos salvo `quota_pct` = 35, con la cuota apretando en las seis
  configuraciones de medium y hard (la proporción near-prime sin complementos es del 18–29% frente a cuotas del 25–30%) y la
  forma de trabajar del cliente como mucho en 0.920 de la referencia. Aquí tres semillas no pueden mostrar todos los
  candidatos: la restricción de la franja ata el corte, el umbral y la cuota, y la primera semilla, donde se ejecuta la
  comprobación de que los parámetros aprietan, necesita una alternativa admisible para cada uno de ellos, un umbral de
  discrepancia por encima del más bajo y una cuota que apriete en todos los mundos en que se comprueba (semilla 30: proporción
  near-prime sin complementos del 21–26% frente al 30% en el mundo público y en las semillas de mundo 1–3; los candidatos
  anteriores fallaron en la semilla de mundo 2, donde la proporción llegaba al 29–35%). Sus sorteos, sus objetivos y cuánto
  aprieta cada regla están en el README.
- **La referencia** tuvo que cambiar para los conjuntos de candidatos reajustados: con la mayoría de los riesgos malos ya
  excluidos por las reglas, su scorecard de 4 variables (sin término de antigüedad, lineal en puntuación y DSR) perdía frente
  al orden de llegada en algunos sorteos (hasta 1.07 en franjas near-prime estrechas). Ahora tiene el término de antigüedad y
  los dos términos bisagra, dimensiona los préstamos (F1), completa las aprobaciones near-prime por lo máximo que permite su
  límite y retiene las aprobaciones prime menos rentables cuando la demanda near-prime de un día no basta para mantener la
  proporción acumulada en la cuota. En 276 sorteos admisibles aleatorios (92 por nivel) la referencia y la forma de trabajar
  del cliente son válidas y la segunda queda por debajo de la referencia (entre 0.46 y 0.996 de su objetivo; mediana 0.81 en
  easy, 0.85 en medium, 0.90 en hard); unos pocos sorteos se acercan (una búsqueda de semillas públicas encontró 1.03 en hard
  con la semilla de reglas 742), y en ellos `quality_fields` recurre a la razón simple. La salida del día piloto de los datos
  usa el scorecard anterior del programa piloto y no cambia.
- **Ejemplos del validador:** el ejemplo near-prime que rechaza aprobaciones near-prime amplía ahora su margen hasta que la
  reproducción termina por debajo de la cuota (el programa gasta en días posteriores lo que libera un rechazo); el ejemplo de
  presupuesto que completa sin fin desactiva la nueva retención, y uno último cree en un presupuesto diez veces mayor y presta
  por orden de llegada (lo necesita hard/s1043 en la semilla de mundo 3). `_below_cutoff` da a cada corte que puede sortear una
  semilla de reglas al menos un solicitante por debajo de él que, por lo demás, sería aprobable (no cambia nada en el mundo
  público).
- **Comprobación de que los parámetros aprietan:** todos los parámetros aprietan en hard/s30, en el mundo público y en las
  semillas de mundo 1–3 (con otro candidato admisible, la referencia deja de ser válida o su objetivo se mueve). La forma de
  trabajar del cliente queda más cerca de la referencia que con los conjuntos de reglas (0.64–0.92 en las semillas de reglas
  públicas frente a 0.38–0.75), porque ahora las propias reglas dejan fuera muchos préstamos malos; `quality_fields` mantiene
  el punto cero de la calidad al menos un 5% por debajo de la referencia.

**Forma de trabajar del cliente (semillas de reglas):** 0.759 / 0.644 / 0.904 en easy s30 / s525 / s1043, 0.879 / 0.756 /
0.908 en medium y 0.920 / 0.846 / 0.913 en hard, válida en todas partes. Con las semillas de mundo 1–3 (semillas de reglas
públicas) la referencia y la forma de trabajar del cliente siguen siendo válidas en todas partes, la segunda con un 0.69–0.96
del objetivo de la referencia.

**Comprobación de la conversión (semillas de reglas).** Una comprobación adversarial de la conversión confirmó que lo que ve el
agente es idéntico byte a byte en los 3 niveles × semillas de reglas 4–10 y las semillas de reglas públicas en todos los
idiomas, que allí la referencia es válida con 1.0 y la forma de trabajar del cliente es válida y queda por debajo, en el mundo
público y en las semillas de mundo 1–3, que cada parámetro está cubierto por un hecho que preguntar y que las cifras del README
coinciden con el conjunto de datos guardado. Se encontró y corrigió un problema: en sorteos privados en los que el tope diario
podía gastar todo el presupuesto del período antes de que llegara el recorte de tesorería (3,400,000 o 3,800,000 con un tope
de 300,000), el orden de llegada sin dosificar gastaba el presupuesto original completo antes del recorte, mientras que la
referencia dosificada perdía los 400,000, y la forma de trabajar del cliente alcanzaba o superaba a la referencia (hard con la
semilla de reglas 742: 1.03 en tres de cuatro mundos; medium con la semilla 52: 0.999; las semillas 4 y 9, hasta 0.995).
`admissible` exige ahora también presupuesto ≥ 13 × tope diario (el día en que entra en vigor el recorte). Las semillas de
reglas públicas sortean los mismos valores, así que sus configuraciones y sus cifras no cambian; aproximadamente una cuarta
parte de las semillas privadas vuelve a sortear. Después, la forma de trabajar del cliente obtiene como mucho 0.95 de la
referencia en medium y 0.99 en hard con las semillas 11–130 (mundo público), y como mucho 0.95 con las semillas 4–10 sobre las
semillas de mundo 1–3. Sigue abierto: con tres semillas, las públicas no pueden mostrar `quota_pct` = 35 (comprobado: ningún
trío que cubra todos los candidatos tiene una semilla en la que cada parámetro tenga una alternativa admisible); una cuarta
semilla pública lo mostraría.

## Auditoría de la respuesta correcta

El caso es ahora `audited: true`. `dataset/audit.json` guarda la auditoría del mundo público (`fdebench2 audit-case`: por
nivel, las semillas de reglas públicas y 12 combinaciones admisibles de los candidatos del nivel, 45 configuraciones),
[GT.md](../../GT.md), la respuesta correcta en cinco partes generada a partir de ella por `make_gt.py`, y
[CLIENT_REVIEW.md](../../CLIENT_REVIEW.md), el pasaje de requirements.md con el que cada idioma responde a cada hecho, con una
comprobación previa automática (generado por `make_client_review.py`; pendiente de revisión humana). Lo que cambió, en el orden
en que se hizo:

1. **Atajos cerrados antes de tocar la referencia** (`shortcuts()`, cada uno cerrado en las 45 configuraciones): derivar cada
   solicitud que rechazaría, o todas las solicitudes (`referral_capacity`, una nueva regla contractual: como mucho 3
   derivaciones al día además de las que exigen las reglas, F2); una tabla de límites vacía o solo con los solicitantes del día
   (`limit_table_complete`, una nueva regla contractual: un valor para cada cliente visto hasta ese momento y las cifras del
   banco, cada día, F1); los límites de la mañana en lugar de los del cierre (válido, calidad por debajo de 0); no aprobar nada
   (calidad por debajo de 0, no válido desde medium por la cuota). Las salidas obligatorias son reglas con ejemplos de
   incumplimiento: `decision_complete`, como antes, y `limit_table_complete`.
2. **Puntuación (F1)**: objetivo = razón de beneficio × precisión de la tabla (antes 0.7 × razón de beneficio + 0.3 ×
   precisión), y la parte de clientes de la tabla de un día solo puntúa los valores que cambian ese día (los solicitantes del
   día y cualquier cliente cuyo límite real o comunicado se movió), así que el beneficio no puede compensar una tabla y los ~500
   valores estáticos ya no esconden una fórmula equivocada. Los requisitos (cinco idiomas), los textos de la página explicativa
   y los resúmenes lo dicen, con la razón del cliente: la mesa da sus cifras a los clientes a partir de la tabla y tesorería
   financia según ella.
3. **Un hecho por pregunta.** Los 26 hechos que preguntar pasaron a ser 31. Divididos: `policy_bureau` (en el buró y
   `score_cutoff`), `customer_limit` (`income_cap`, `our_lending`), `dsr_rule` (`dsr_cap`), `limit_table` (`limit_table`,
   `closing_table`, `ineligible_zero`), `easy_scope` y `medium_scope` (`credit_lines_easy`, `regulator_notice_easy`,
   `declared_income`, `repayments_unused`), `period_budget` (y `budget_notice`), `near_prime_quota` (`near_prime_threshold`,
   `near_prime_quota`). Diez hechos son exactamente un parámetro sorteado (`param:` en en/targets.yaml); cada uno de los demás
   tiene en `ablations()` una respuesta que malinterpreta solo ese hecho: el programa de referencia con un interruptor cambiado,
   la mala lectura más natural de lo que ve el agente. `branch_notes` está ahora en vigor en todos los niveles, porque su
   párrafo salió de hard. Quitados de los hechos que preguntar y conservados en requirements.md como contexto: `interface` y
   `evaluation_period` (lo que ve el agente ya dice ambos) y `profit_metric` (actualización de F5: malinterpretar la economía
   mueve menos de una décima parte de la escala en la mayoría de las configuraciones). Cada hecho restante cambia la puntuación
   en todos los niveles en que está en vigor: 26 de ellos en todas las configuraciones medidas (la mayoría de las malas lecturas
   invalidan el programa: un límite, un código o un valor de la tabla equivocados), `ineligible_zero` en 44 de 45 (puntuación
   perdida 0.09–0.57), y los parámetros de la cuota y del umbral de discrepancia en aproximadamente la mitad (su candidato
   equivocado menos dañino cuesta poco donde la cuota o la diferencia no aprietan). `stress_rate` cambia la puntuación en 9 de
   30 configuraciones (pocos clientes pasan de 60,000 de deuda): una advertencia, y se mantiene porque decide los límites de
   esos clientes allí donde cambia la puntuación.
4. **El período de evaluación (F8)**: tres notas de sucursal pasaron a solicitantes recién incorporados a su empleo que son
   admisibles y están dentro de su límite en todas las configuraciones, y las amortizaciones del mismo día, a clientes cuyo
   límite la amortización sube de menos de 1,000 a al menos 3,000 en todas las configuraciones; ambos cambios con sus propios
   flujos aleatorios después de construir el período. Lo que ve el agente es idéntico byte a byte (la exportación solo cambió
   `hidden/`, `gt/` y el manifiesto).
5. **Comprobaciones directas**: `score()` devuelve `enforced` y `evidence` para cada hecho en vigor, leídos de la propia
   ejecución del entregable en la misma invocación del programa: los valores puntuados de la tabla donde la mala lectura (u
   otro candidato del parámetro) da otro límite, votados por alternativa, y para los demás hechos las decisiones que solo ellos
   deciden (derivaciones, códigos de motivo, parejas, solicitudes con nota, nuevas decisiones, grupos fraccionados, la
   proporción near-prime). La referencia se declara aplicada en el entregable en todos los hechos y en todas las
   configuraciones medidas, y toda respuesta que malinterpreta un solo hecho y cambia la puntuación se declara no aplicada (las
   comprobaciones directas de la auditoría separan los 31 hechos).
6. **La solución que nunca pregunta** (`robust_solution`): el programa de referencia con la lectura más natural de cada hecho
   fijo y el candidato más estricto de cada parámetro. No es válida en ninguna configuración medida (sin preguntar, un corte,
   un tope o un código siempre está mal en algún sitio), así que `voi` = 1.000 en todos los niveles; la referencia de la mejor
   configuración individual, que sabe todos los hechos fijos, gana 0.133 en easy y 0.067 desde medium (`voi_params` 0.867 /
   0.933 / 0.933): solo es válida donde todos los parámetros que usa su nivel son los suyos.
7. **Referencia, mejor solución conocida, cota (F1)**: la referencia es una mochila con precio (README, Cifras de referencia):
   un 2–12% más de beneficio que la anterior. `best_known_solution` la ajusta sobre el período de evaluación (en
   retrospectiva); `objective_bound` es el beneficio con información perfecta, relajado y dualizado. Sobre las 45
   configuraciones la mejor solución conocida está entre un 0.06% y un 1.6% por encima de la referencia (calidad 1.003–1.081,
   mediana 1.019) y la cota, entre un 3.4% y un 10.6% por encima; `quality_cap` = 1.02 (la mediana de la calidad de la mejor
   solución conocida, redondeada hacia arriba).
8. **Escalas estrechas**: la forma de trabajar del cliente está ahora en 0.469–0.846 de la referencia en el mundo público y en
   0.486–0.923 en las semillas de mundo 1–3 (cada escala tiene una amplitud de al menos un 7.7%), así que el caso salió de
   `validate.OPEN_NARROW_SCALES`.

Hallazgos resueltos: F1, F2 y F8 (arriba y debajo de cada uno), las escalas estrechas; F4, medido de nuevo (depende del
sorteo: véase su actualización); los hechos de F5, divididos. Siguen abiertos: F9 y F10 como antes, y `quota_pct` = 35 no está
en las semillas de reglas públicas. `OPEN_AUDIT_FINDINGS` no exime de nada a este caso.

### Comprobación adversarial de la auditoría

Un segundo ingeniero intentó romper la auditoría en su propia rama (atajos nuevos, cada respuesta que malinterpreta un solo
hecho y la solución que nunca pregunta leídas de nuevo, las comprobaciones directas ejecutadas sobre la forma de trabajar del
cliente y los atajos, la demostración de la cota, los textos en cinco idiomas). Confirmado y corregido:

- **A1 — La puntuación de la tabla se podía manipular (alta).** Dos huecos, ambos medidos sobre las decisiones de la
  referencia:
  - la mitad de la tabla de un día eran las dos cifras del banco, que cualquier programa acierta: los límites de los clientes
    de la mañana con las cifras del banco del cierre seguían siendo válidos con una calidad de hasta 0.71 (easy/s525; 0.64 en
    medium/s525, 0.52 en easy/s30). El atajo `morning_table` de la lista también comunicaba las cifras del banco de la mañana,
    lo que ocultaba el hueco;
  - «o cuyo valor ustedes movieron» permitía a un programa volver a meter en la puntuación los ~500 valores estáticos: mover
    cada valor en 1 (dentro de la tolerancia) un día sí y otro no subía los límites de la mañana a 0.67–0.93 en las semillas
    de reglas públicas, y una tabla exacta con los solicitantes del día a 0, a 0.64–0.88.

  Corregido en la puntuación, con la redacción del cliente en los cinco idiomas: la tabla de un día es la proporción de valores
  correctos entre los que cambian ese día **multiplicada por** la proporción de cifras del banco correctas, y un valor que el
  programa movió solo se puntúa cuando lo movió a un importe equivocado. Se añadieron cuatro atajos (`morning_limits`,
  `jitter_table`, `zero_table`, `approved_zero`), todos cerrados en las 45 configuraciones: mejor calidad 0.32 para los límites
  de la mañana (mover los valores ya no añade nada), 0.35 con 0 para los clientes aprobados del día, 0.000 para una tabla toda a
  cero; `morning_table` baja de 0.008 a 0.000. Todo entregable con una tabla exacta (la referencia, la forma de trabajar del
  cliente, la mejor solución conocida) puntúa como antes, así que la escala, la cota y `quality_cap` se mantienen. Las tablas
  mal leídas cuestan más, así que más hechos cambian la puntuación: `ineligible_zero` en 45 de 45 configuraciones (antes 44;
  puntuación perdida 0.17–1.00), `stress_rate` en 25 de 30 (antes 9, así que desaparece su advertencia por cambiar la
  puntuación en pocas configuraciones), `daily_cap` y `period_budget` con una puntuación perdida de 1.000 en todas partes; la
  auditoría no informa de ningún hallazgo.
- **A2 — La respuesta que malinterpreta solo la tabla al cierre inflaba su puntuación perdida (media).** También comunicaba las
  cifras del banco de la mañana, con las que el producto puntuaría 0 cada día fueran cuales fueran los valores de los clientes.
  Ahora mantiene las cifras del banco del cierre (lo que un programa malinterpreta son los límites de los clientes; las cifras
  del banco son la aritmética del propio día): puntuación perdida 0.68–1.00 (antes 0.992–1.000), y cambia la puntuación en
  todas las configuraciones.
- **A3 — Las comprobaciones directas near-prime declaraban no aplicada la forma de trabajar del cliente, que es válida
  (media).** El orden de llegada termina a menudo 4.5 puntos o menos por encima de una cuota candidata más estricta (o mantiene
  ahí la proporción calculada con un umbral más estricto), y la comprobación directa lo leía como gobernar la proporción:
  `near_prime_quota` False para la forma de trabajar del cliente en 17 y `near_prime_threshold` en 15 de las 30 configuraciones
  de medium y hard. Gobernar la proporción hacia un nivel más estricto exige ahora además que la proporción acumulada nunca
  cierre un día por debajo de él y que termine como mucho 3.5 puntos por encima: la forma de trabajar del cliente se declara no
  aplicada en 3 configuraciones para cada hecho (medium/c8, hard/s30 y hard/c10 para la cuota; medium/c1, hard/s30 y hard/c10
  para el umbral), donde su proporción sí se mantuvo cada día en el nivel más estricto y nada en la ejecución lo distingue de
  gobernarla; toda respuesta que malinterpreta un solo hecho y cambia la puntuación se sigue declarando no aplicada.
- **A4 — Las comprobaciones directas de antigüedad y de discrepancia malinterpretaban otras derivaciones (baja).**
  `refer_declines` (deriva lo que rechazaría) se leía como una costumbre de antigüedad más larga en 27 configuraciones. Una
  derivación que la regla no pide cuenta ahora en contra del hecho solo por encima de la tasa propia del programa de derivar
  solicitantes que ningún candidato envía.
- **A5 — La solución que nunca pregunta malinterpretaba dos hechos en contra de lo que el propio agente puede ver (baja).**
  Leía LIMIT_EXCEEDED como una solicitud por encima de lo que queda, aunque la respuesta del piloto pone CREDIT_RISK a una
  solicitud de 46,500 con 30,840 restantes y LIMIT_EXCEEDED a un cliente con 0 restante; y daba a los clientes no admisibles su
  límite de la fórmula, cuando «lo que aún puede pedir» se lee como 0. Ambas cosas corregidas. Sigue sin ser válida en ninguna
  configuración medida (en cada una está mal un corte, un tope o un aviso), así que `voi` sigue en 1.000. Intentos de
  superarla: la validez exige acertar todos los parámetros que aprietan, y ninguna configuración medida tiene la combinación
  más estricta; la combinación de easy más frecuente aparece en dos configuraciones, de ahí sale `never_asks_params` (0.133), y
  un programa que además no sabe ningún hecho fijo no puede hacerlo mejor que esa referencia.
- **A6 — El alcance de la cota (baja).** `objective_bound` vale para todo entregable que cumple todas las reglas; un programa
  que flexibiliza la costumbre de antigüedad con una excepción (una regla relajada en una ejecución) puede superarla
  (easy/s525: flexibilizar 1.097 frente a una cota de 1.065; easy/s1043: 1.141 frente a 1.106). El docstring y GT.md indican
  ahora ese alcance.
- **A7 — Un hecho hablaba de "the client's own affordability limit" (el propio límite de solvencia del cliente) (baja).** zh
  (客户) y ja (顧客) lo traducían como el límite propio del prestatario. `regulator_notice_easy` dice ahora "our own
  affordability limit" (nuestro propio límite de solvencia), con la voz del cliente, en los cinco idiomas.

Comprobado sin hallazgos: cada una de las demás respuestas que malinterpretan un solo hecho es la referencia con un interruptor
y una mala lectura natural; lo que ve el agente y la solicitud son idénticos byte a byte (validate-case); las citas de
CLIENT_REVIEW.md son las líneas citadas del requirements.md de cada idioma y los cinco idiomas coinciden en cada número,
identificador y fecha (vuelto a comprobar con un script independiente); nada afirma una revisión humana; la demostración de la
cota (sumas de Riemann por la izquierda de una probabilidad que crece con el importe, lineal entre los puntos de la malla,
dualidad débil, los dos casos del recorte de tesorería) se sostiene y ningún entregable válido la supera; `quality_cap` = 1.02
es al menos la mediana de la calidad de la mejor solución conocida; las cifras de referencia del README coinciden con el
conjunto de datos guardado; `referral_capacity` no es, con razón, un hecho que preguntar (un programa que maximiza el
beneficio nunca deriva por elección, ya que una derivación cuesta 60 y no genera nada, así que malinterpretar la capacidad no
le cambia nada; la regla cierra el atajo de F2).

### Comprobaciones directas

La etapa «aplicado en el entregable» de una ejecución sale de la comprobación directa por hecho aplicada al entregable del
agente, que no es ni la referencia ni una respuesta que malinterpreta un solo hecho, así que el framework comprueba ahora
también la comprobación directa sobre otros entregables (DESIGN.md, sección Ground truth audit; AUDIT_VERSION 3): un False en
la mejor solución conocida, que es válida, es un problema (`diagnostic_false_negative`), una respuesta que malinterpreta un
solo hecho y declara no aplicados otros hechos en más de la mitad de las configuraciones en que cambia la puntuación es una
advertencia `cross_flags`, y `diagnostic_profile` cuenta, por hecho, los False de la forma de trabajar del cliente y de
`robust_solution`. Auditado de nuevo con ese criterio, con la comprobación directa tal como estaba (la parte near-prime medida
con una réplica de la auditoría dentro del proceso): ningún falso «no aplicado», la mejor solución conocida aplicada en todos
los hechos en vigor en las 45 configuraciones; la forma de trabajar del cliente, que es válida, declarada no aplicada en un
hecho near-prime en 4 de las 30 configuraciones de medium y hard; y ocho advertencias de marcas cruzadas, `policy_bureau` (37
de las 45 configuraciones en que cambia la puntuación), `dsr_cap` (36/45), `ineligible_zero` (31/45), `regulator_notice_easy`
(11/15), `regulatory_notice` (19/30), `verified_income` (8/15) y los dos hechos near-prime (cada uno sobre el otro, en 15 de 24
y 16 de 29). Lo que cambió:

1. **La comprobación directa pasó a `diagnose()`.** `score()` guarda lo que hizo la ejecución cada día bajo una clave privada
   `trace` (que `evaluate()` nunca copia) y `diagnose(world, submission_dir, setting, scored)` la lee, así que un entregable
   sigue ejecutándose una sola vez por evaluación; el validador y la matriz del valor de preguntar se la saltan.
2. **Hechos near-prime en la forma de trabajar del cliente: de 4 configuraciones de 30 a 0.** «Mantenida en un nivel» (la
   proporción del período termina unos pocos puntos por encima de un nivel más estricto y nunca cierra un día por debajo de él)
   también leía el orden de llegada como gobernar la proporción allí donde su proporción acabó asentándose en ese nivel
   (`near_prime_quota` en medium/c8, hard/s30, hard/c10; `near_prime_threshold` en medium/c1, hard/s30, hard/c10). Ahora exige
   además que el primer día con préstamos cierre como mucho 7 puntos por encima del nivel: un programa que mantiene un
   compromiso lo mantiene desde su primer día, cuya proporción es la mezcla propia de ese día (y un programa que busca
   beneficio no presta a near-prime más de lo que se le pide, porque los préstamos near-prime son los más arriesgados); el
   primer día de la forma de trabajar del cliente cerró 11–35 puntos por encima del nivel en esas configuraciones, el de las
   malas lecturas más estrictas, 0.2–4.6. Con el primer día en la prueba, la franja final volvió de 3.5 a 4.5 puntos (la
   lectura de una cuota cumplida que hace la propia comprobación directa de la cuota): en la semilla de mundo 1, tres respuestas
   que malinterpretan un solo hecho y cambian la puntuación terminan 4.0–4.2 puntos por encima de su nivel y con 3.5 se
   perdían. La forma de trabajar del cliente ya no se declara no aplicada en ningún hecho near-prime en las configuraciones de
   medium y hard del mundo público ni de las semillas de mundo 1 y 2, y toda respuesta near-prime que malinterpreta un solo
   hecho y cambia la puntuación se sigue declarando no aplicada.
3. **Lecturas en competencia.** Las malas lecturas de dos hechos pueden dar la misma salida, y la respuesta que malinterpreta
   uno se declaraba no aplicada en el otro: un tope de DSR 5 puntos más alto da, desde la fecha de entrada en vigor del regulador, los
   límites de su recorte de 5 puntos ignorado (`dsr_cap` con `regulatory_notice` y `regulator_notice_easy` en ambos sentidos,
   y a través de los mismos límites los hechos de líneas de crédito y de estrés y los códigos de motivo); el límite de la
   fórmula de un cliente no admisible es el límite con un corte más bajo (`ineligible_zero` → `score_cutoff`,
   `policy_bureau`); el otro buró mueve el corte y la definición de near-prime; un presupuesto 400,000 mayor da las cifras del
   recorte ignorado (`period_budget` → `budget_notice`); una ejecución por debajo de la cuota contaba en contra de ambos hechos
   near-prime. Cada comprobación directa lee ahora cada lectura en vigor de su salida (los valores de clientes bajo la mala
   lectura de cada hecho de la tabla y cada otro candidato de un parámetro de la tabla, los códigos que da cada lectura de los
   límites, el presupuesto restante con y sin el recorte y con los otros presupuestos). Un lugar donde el valor de una mala
   lectura es también el de la mala lectura de otro hecho que la ejecución sigue (más de los lugares donde las dos difieren son
   de la otra) ya no cuenta en contra del hecho, salvo que, en los valores de clientes, la ejecución siga la mala lectura además
   de la lectura que mejor sigue. Por debajo de la cuota, no se cuenta en contra de la cuota (o del umbral) cuando se cumple la
   mala lectura del otro y la suya propia no es posible (su proporción cerró algún día por debajo de su nivel), o cuando la
   proporción del otro buró se mantiene en la cuota. Una respuesta que malinterpreta un solo hecho comunica los valores de su
   propio hecho allí donde difieren de cualquier otra lectura, así que no sigue ninguna otra lectura y conserva su separación;
   donde la ejecución no puede descartar una lectura, sus votos se mantienen (una separación perdida es un problema; una marca
   cruzada, solo una advertencia).
4. **La respuesta que malinterpreta solo el ingreso verificado malinterpretaba tres hechos.** Leer el salario declarado para
   los límites también desactivaba el control de fraude (la derivación por discrepancia leía el mismo salario) y las
   correcciones de documentos. El control de fraude y las correcciones del programa de referencia leen ahora los justificantes
   sea cual sea el salario que usan sus límites, así que esa respuesta solo malinterpreta el salario de los límites; la
   referencia lee los justificantes en todas partes en hard, así que sus decisiones, la escala, la cota y `quality_cap` no
   cambian.

La auditoría ya no informa de ningún hallazgo: ningún falso «no aplicado» en la mejor solución conocida, la forma de trabajar
del cliente no se declara no aplicada en ningún hecho en ninguna de las 45 configuraciones, toda respuesta que malinterpreta un
solo hecho y cambia la puntuación se sigue declarando no aplicada (los 31 hechos se separan), y las únicas marcas cruzadas que
quedan son las de los dos hechos near-prime (2 de 23 y 3 de 21 configuraciones, donde las dos malas lecturas o ninguna explican
una ejecución que termina por debajo de la cuota). `robust_solution`, que malinterpreta muchos hechos a la vez, se sigue
declarando no aplicada donde se ven sus malas lecturas (GT.md, parte 5). La contrapartida: un entregable que malinterpreta a la
vez los dos hechos de uno de esos pares puede declararse ahora aplicado (o no determinable) en uno de ellos donde la tabla no
distingue los dos. De 33 programas sobre las semillas de reglas públicas que malinterpretan dos hechos a la vez (cada par de
arriba y tres sin relación), en 20 se declaran no aplicados los dos hechos (25 antes; 8 de los 13 fallos ya fallaban antes): los
fallos son pares en los que la segunda mala lectura repite o anula en la salida los valores de la primera (otro corte bajo el
límite de la fórmula para los clientes no admisibles, un tope de DSR 5 puntos más alto con el recorte del regulador aplicado en
easy, un presupuesto mayor con su recorte ignorado). Las comprobaciones de validez no dependen de la comprobación directa (las
aprobaciones de un corte más laxo siguen incumpliendo `score_cutoff`). `audit-case` sigue tardando unos 40 minutos (la
comprobación directa es barata al lado de las ejecuciones del programa); `OPEN_AUDIT_FINDINGS` no exime de nada a este caso.

### Comprobación adversarial de las comprobaciones directas (programas que no son ni la referencia ni una respuesta que malinterpreta un solo hecho)

Programas construidos para las 9 configuraciones públicas y evaluados con `evaluate(..., diagnose=True)`:

- **Correctos pero distintos** (cada hecho bien leído): la referencia con incrementos de 500 o 1,000 en lugar de 250, una
  pérdida en caso de impago de 0.70 o un margen del 8% en su precio, rechazando (con el código correcto) a solicitantes hasta
  10 o 25 puntos de la política por encima del corte, la asignación voraz anterior con dimensionamiento, una dosificación
  lineal del presupuesto, un colchón near-prime de 2 o 1 puntos y, en hard, la primera de las solicitudes del mismo día de un
  cliente aprobada en lugar de la mayor (84 programas, calidad 0.00–1.03, todos válidos). Ninguno se declaró no aplicado en
  ningún hecho, ni antes ni después.
- **Malas lecturas nuevas** (cambios de código o de configuración que no hace ninguna respuesta que malinterpreta un solo
  hecho: el ingreso mensual declarado como ingreso; una derivación también con la antigüedad exactamente igual al umbral; las
  deudas existentes fuera del DSR; olvidar nuestros préstamos del mismo día; LIMIT_EXCEEDED leído sobre el límite antes de las
  aprobaciones del día; el scorecard con atributos protegidos, con las parejas aún decididas como una unidad; el corte o el
  umbral near-prime en puntos del buró A aplicados sobre la escala del B; un tope diario un 10% mayor; el recorte del regulador
  desde el día en que llega su aviso; el recorte del presupuesto desde su aviso; la cuota contada en número de préstamos o
  ignorada; near-prime con el umbral incluido; un presupuesto un 10% mayor). De las 76 que cambian la puntuación, 40 se
  declararon no aplicadas en su hecho (53%). Cuatro tipos que cambian la puntuación se declararon aplicados o no determinables,
  tres de ellos aunque incumplen la regla que enuncia su hecho: días por encima del tope diario (2 de 9: las capacidades
  comunicadas no coincidían con ninguna lectura más a menudo que con la verdad), aprobaciones por encima del presupuesto del
  período (6 de 6: el presupuesto restante comunicado es el del propio programa, no el de ningún candidato), los códigos de
  motivo leídos antes de las aprobaciones del día (4 de 4: solo se comparaba la lectura «pidió más de lo que queda») y el
  recorte del regulador desde el día de su aviso (6 de 6: solo se comparaba el recorte ignorado).

Lo que cambió (case.py `_diagnose`, `_View.dsr_cap_pct`):

1. **`daily_cap`**: cualquier día aprobado por encima del tope se declara no aplicado.
2. **`period_budget` / `budget_notice`**: las aprobaciones hechas mientras el período está por encima del presupuesto vigente
   se declaran no aplicadas: en `budget_notice` cuando la ejecución se mantiene dentro del presupuesto sin recortar y comunica
   las cifras del presupuesto sin recortar en lugar de las de otro candidato (el recorte ignorado), y si no, en
   `period_budget`.
3. **Códigos de motivo**: una segunda mala lectura de LIMIT_EXCEEDED, el límite antes de las aprobaciones del día, con las
   lecturas en competencia como para la primera; una lectura de los límites que la ejecución sigue en la tabla (más de los
   valores donde difiere de la verdad son suyos) también explica los códigos que comparte con una mala lectura donde los
   códigos por sí solos no pueden distinguir las dos (el único rechazo de la respuesta que malinterpreta solo el ingreso bruto
   en medium/s30).
4. **`regulatory_notice`**: los valores también se leen con el recorte desde el día en que llega su aviso (mala lectura
   `reg_on_notice`, `TABLE_MISREAD_MORE`), dentro de las lecturas en competencia (un tope de DSR 5 puntos más bajo da esos
   valores desde el día del aviso hasta la fecha de entrada en vigor).

Después (mismos programas): los 84 programas correctos siguen aplicados en todos los hechos; de las 76 malas lecturas que
cambian la puntuación, 58 se declaran no aplicadas en su hecho (76%, antes 53%). Siguen declarándose aplicadas: olvidar
nuestros préstamos del mismo día (9: su tabla es la tabla de la mañana, así que en su lugar se declara no aplicada en
`closing_table` y, donde cambian los códigos, en los códigos de motivo: los dos hechos dan los mismos valores), una derivación
con la antigüedad exactamente igual al umbral (4: esas derivaciones son la tasa propia del programa de derivar solicitantes que
ningún candidato envía), las deudas existentes fuera del DSR en las configuraciones del 45% (3: donde otro candidato difiere de
la verdad, los límites son los del tope por ingresos, que la ejecución comunica bien; incumple `customer_limit`) y el umbral
near-prime en puntos A sobre la escala B donde su proporción aún termina en la franja de la cuota (2: no hay un candidato más
bajo con el que comparar). La nueva auditoría (2,236 s) no encuentra ningún falso «no aplicado» (mejor solución conocida 0 de
1,003, forma de trabajar del cliente 0 de 953), todos los hechos se separan, quedan las mismas dos marcas cruzadas near-prime
por debajo de la línea de advertencia y no hay ningún hallazgo; `robust_solution`, que aplica el recorte del regulador desde su
aviso, se declara ahora también no aplicada en `regulatory_notice` (15 configuraciones: 410 de 914, antes 395).
