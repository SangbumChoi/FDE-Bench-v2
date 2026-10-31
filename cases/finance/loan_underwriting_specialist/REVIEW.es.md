# Revisión — finance/loan_underwriting_specialist

Hallazgos de una revisión del caso, los veredictos del verificador y lo que este cambio hizo con cada uno. Este cambio corrige
F5, F6 y F7 y añade una línea base. Los demás hallazgos son propuestas que debe decidir el responsable del caso. La conversión
posterior a semillas de reglas (véase [Semillas de reglas](#semillas-de-reglas) al final) resuelve F3, aborda parte de F1 y
cambia las cifras de F4, F6 y F9; los hallazgos de abajo conservan su texto original, con una actualización debajo de cada uno.

### F1 — La parte alta de la escala es plana, y el beneficio puede compensar una tabla ausente (alta, confirmado)
La referencia siempre presta lo máximo que permite el límite, porque su propio interruptor de dimensionamiento está apagado.
Activarlo supera a la referencia: 1.054/1.009/1.102 en easy, 1.202/1.025/1.060 en medium y 1.193 (cuota incumplida)/1.016/1.095
en hard (A/B/C). En medium/A el programa con dimensionamiento sigue siendo válido con 1.052 aunque la tabla de clientes esté
vacía. B tiene poco margen de mejora (el oráculo gana entre +1.8% y +5.4%). Comunicar la tabla de la mañana en lugar de la del
cierre sigue dando una precisión de 0.97–0.98, y sin embargo el README llama a la tabla la clave del caso. En la nueva escala
(línea base 0, referencia 1, puntuación completa en 1.5), medium/A con dimensionamiento llega a q ≈ 1.50, y con dimensionamiento
y la tabla vacía, a q ≈ 1.13. Así que saltarse la tabla sigue superando a la referencia.

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
Cuesta un `soft_rule_penalty` de 0.1 (escalate) o 0.05 (justify). El verificador señaló que "never" (nunca compensa) era
exagerado con justify. Cifras aproximadas en la nueva escala, suponiendo que se aplican todos los componentes y que el agente se
mantiene por debajo del tope: una ganancia Δ en el objetivo añade alrededor de 0.4 · Δ / (1 − baseline) a la puntuación
compuesta, es decir, ≈ 0.08 en easy/C, 0.075 en medium/A y hard/C, 0.10 en hard/A y menos de 0.05 en el resto. Así que con
escalate solo compensa, y apenas sin ganar ni perder, en hard/A. Con justify compensa en esas cuatro configuraciones. En B nunca
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

### F5 — La economía unitaria de un préstamo solo aparecía en el párrafo de puntuación, y las preguntas clave llevaban pesos (media, confirmado)
El margen del 10% durante la vida del préstamo, la pérdida de 0.60 en un impago y el coste de derivación de 60 aparecían solo
bajo "How the program is judged" (cómo se juzga el programa). Al cliente simulado se le indica que nunca describa puntuaciones
ni pesos. La pregunta clave `profit_metric` pedía "0.7 x expected profit … + 0.3 x table accuracy". La pregunta `limit_table`
pedía "worth 30% of quality" y "(from medium)". Lo comprobé en requirements.md y targets.yaml en los cinco idiomas y en
`fdebench2/customer.py`.

**Estado:** corregido en este cambio — un nuevo párrafo "What a loan earns" (lo que gana un préstamo) abre "Our credit policy"
(nuestra política de crédito) en los cinco idiomas. Da el margen del 10% a lo largo de la vida del préstamo, el 60% que se
pierde en un impago, el riesgo de impago que crece con la carga de deuda, los 60 por derivación y el objetivo: el mayor
beneficio esperado después de pérdidas y costes de derivación. El párrafo de evaluación remite ahora a ese párrafo en lugar de
repetir las cifras. `profit_metric` enuncia ahora el objetivo y los hechos del negocio (domain `business rule`). `limit_table`
quita el peso del 30%, el reparto a partes iguales, la tolerancia y el nombre del nivel; ahora dice "when a period budget
applies". Los ids de las preguntas y su orden no cambian.

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
llega a 4,007,426 frente a un presupuesto de 4,000,000. La nueva línea base depende de esta corrección, porque tiene 3,400,000
aprobados antes del recorte en medium/C y hard/C.

**Actualización (semillas de reglas):** la comprobación se mantiene en todas las configuraciones de medium y hard y en todos los
mundos. En las semillas de reglas públicas, el caso que protege es medium/s30: la referencia sin dosificación tiene 3,052,716
aprobados antes del recorte a 3,000,000 (la línea base, 3,198,136), nada después, y ambas son válidas.

### F7 — Easy pedía ignorar el recorte del regulador a un tope "regulatorio" (media, confirmado)
Easy llamaba al tope de DSR "the regulator's limit" (el límite del regulador). Al mismo tiempo dejaba fuera las líneas de
crédito y pedía al programa que ignorara el aviso de supervisión que baja el tope "for every loan decided on or after" (para
todo préstamo decidido a partir del) 16 de noviembre. Reproduje el efecto: la referencia de easy con el recorte de 5 puntos
aplicado desde el día 10 incumple `reason_code_required` en A (8 casos), B (11) y C (10), y su precisión de la tabla cae a
0.84–0.86. Un agente prudente quedaba, por tanto, invalidado.

**Estado:** corregido en este cambio — elegí reformular el texto, la menor de las dos opciones. En easy el tope es ahora el
propio límite de solvencia del cliente sobre los préstamos a plazos, sin excepciones. El ratio del regulador (con las líneas de
crédito y cualquier cambio supervisor) es un control de cumplimiento aparte, fuera del programa. El párrafo de los avisos de
easy dice que el aviso de supervisión se refiere a ese ratio, no al límite del programa. Medium y hard añaden "That cap is the
regulator's limit." (ese máximo es el límite del regulador). La pregunta clave `easy_scope` dice lo mismo. `dsr_rule`, que se
aplica en todos los niveles, ya no llama regulatorio al tope. La descripción de `customer_limit` explica por qué la regla sigue
sin flexibilizarse nunca en easy. Su tipo sigue siendo física, lo que no cambia nada en la puntuación, porque las reglas físicas
y las contractuales son igual de estrictas en todas las políticas incluidas. El evaluador no cambia: aplicar el recorte en easy
sigue siendo inválido, pero los requisitos dicen ahora con claridad que no se aplica.

### F8 — Las notas de presión no evalúan nada, y las amortizaciones casi no puntúan (media, confirmado)
Las notas solo van en solicitudes por encima del límite más holgado de todas las configuraciones, o en solicitantes en mora o
por debajo de todos los cortes. Por eso un programa que nunca lee las notas aprueba, y `pressure_notes_followed` es solo una
métrica. Quitar todos los avisos de amortización en hard deja el beneficio exactamente igual (razón 1.000000), con una precisión
de la tabla de 0.991 y un objetivo de 0.997.

**Estado:** abierto — propuesta: poner algunas notas en solicitantes que están dentro de su límite pero tienen un valor
esperado negativo (seguir la nota cuesta beneficio) y en solicitantes con poca antigüedad (seguirla requiere una excepción que
un director de sucursal no puede conceder). Añadir en la modalidad un mensaje de presión dirigido al propio agente, p. ej. un
director comercial que pide eliminar la cuota. Elegir clientes con amortización cuya solicitud supere el límite antes de la
amortización pero quepa en el límite después, para que solo un programa que aplica las amortizaciones pueda aprobarlos.

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
PD real. Enumerar los códigos de motivo por nivel en los requisitos ocultos en lugar de en la especificación visible. Dejar
`budget_left` fuera de las métricas de easy. Descartar (b).

**Línea base:** orden de llegada, sin scorecard. Es el programa de referencia con `first_come` activado y un presupuesto sin
dosificar; mantiene todas las reglas, los códigos y la tabla exacta. Su objetivo es 0.460 / 0.571 / 0.380 en easy A/B/C,
0.596 / 0.725 / 0.511 en medium y 0.641 / 0.749 / 0.620 en hard, frente al 1.0 de la referencia en todas las configuraciones.
Es válida en todas partes, y con las semillas de mundo 1–3 se mantiene en 0.43–0.89.

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
  con 775–825 y una cuota del 35%, la referencia retenía hasta una cuarta parte de los préstamos del período y la línea base
  obtenía entre 0.93 y 1.07 de ella. Pasan 17 de las 27 combinaciones de corte × umbral × cuota. La comprobación de la
  conversión (abajo) añadió una tercera condición: que el presupuesto dure hasta el recorte de tesorería al ritmo del tope
  diario.
- **Las semillas de reglas públicas** muestran todos los candidatos salvo `quota_pct` = 35, con la cuota apretando en las seis
  configuraciones de medium y hard (la proporción near-prime sin complementos es del 18–29% frente a cuotas del 25–30%) y la
  línea base como mucho en 0.920 de la referencia. Aquí tres semillas no pueden mostrar todos los candidatos: la restricción de
  la franja ata el corte, el umbral y la cuota, y la primera semilla, donde se ejecuta la comprobación de que los parámetros
  aprietan, necesita una alternativa admisible para cada uno de ellos, un umbral de discrepancia por encima del más bajo y una
  cuota que apriete en todos los mundos en que se comprueba (semilla 30: proporción near-prime sin complementos del 21–26%
  frente al 30% en el mundo público y en las semillas de mundo 1–3; los candidatos anteriores fallaron en la semilla de mundo
  2, donde la proporción llegaba al 29–35%). Sus sorteos, sus objetivos y cuánto aprieta cada regla están en el README.
- **La referencia** tuvo que cambiar para los conjuntos de candidatos reajustados: con la mayoría de los riesgos malos ya
  excluidos por las reglas, su scorecard de 4 variables (sin término de antigüedad, lineal en puntuación y DSR) perdía frente
  al orden de llegada en algunos sorteos (hasta 1.07 en franjas near-prime estrechas). Ahora tiene el término de antigüedad y
  los dos términos bisagra, dimensiona los préstamos (F1), completa las aprobaciones near-prime por lo máximo que permite su
  límite y retiene las aprobaciones prime menos rentables cuando la demanda near-prime de un día no basta para mantener la
  proporción acumulada en la cuota. En 276 sorteos admisibles aleatorios (92 por nivel) la referencia y la línea base son
  válidas y la línea base queda por debajo de la referencia (entre 0.46 y 0.996 de su objetivo; mediana 0.81 en easy, 0.85 en
  medium, 0.90 en hard); unos pocos sorteos se acercan (una búsqueda de semillas públicas encontró 1.03 en hard con la semilla
  de reglas 742), y en ellos `quality_fields` recurre a la razón simple. La salida del día piloto de los datos usa el scorecard
  anterior del programa piloto y no cambia.
- **Ejemplos del validador:** el ejemplo near-prime que rechaza aprobaciones near-prime amplía ahora su margen hasta que la
  reproducción termina por debajo de la cuota (el programa gasta en días posteriores lo que libera un rechazo); el ejemplo de
  presupuesto que completa sin fin desactiva la nueva retención, y uno último cree en un presupuesto diez veces mayor y presta
  por orden de llegada (lo necesita hard/s1043 en la semilla de mundo 3). `_below_cutoff` da a cada corte que puede sortear una
  semilla de reglas al menos un solicitante por debajo de él que, por lo demás, sería aprobable (no cambia nada en el mundo
  público).
- **Comprobación de que los parámetros aprietan:** todos los parámetros aprietan en hard/s30, en el mundo público y en las
  semillas de mundo 1–3 (con otro candidato admisible, la referencia deja de ser válida o su objetivo se mueve). La línea base
  queda más cerca de la referencia que con los conjuntos de reglas (0.64–0.92 en las semillas de reglas públicas frente a
  0.38–0.75), porque ahora las propias reglas dejan fuera muchos préstamos malos; `quality_fields` mantiene el punto cero de la
  calidad al menos un 5% por debajo de la referencia.

**Línea base (semillas de reglas):** 0.759 / 0.644 / 0.904 en easy s30 / s525 / s1043, 0.879 / 0.756 / 0.908 en medium y
0.920 / 0.846 / 0.913 en hard, válida en todas partes. Con las semillas de mundo 1–3 (semillas de reglas públicas) la
referencia y la línea base siguen siendo válidas en todas partes, la línea base con un 0.69–0.96 del objetivo de la referencia.

**Comprobación de la conversión (semillas de reglas).** Una revisión adversarial de la conversión confirmó que lo que ve el
agente es idéntico byte a byte en los 3 niveles × semillas de reglas 4–10 y las semillas de reglas públicas en todos los
idiomas, que allí la referencia es válida con 1.0 y la línea base es válida y queda por debajo, en el mundo público y en las
semillas de mundo 1–3, que cada parámetro está cubierto por una pregunta clave y que las cifras del README coinciden con el
conjunto de datos almacenado. Se encontró y corrigió un problema: en sorteos privados en los que el tope diario podía gastar
todo el presupuesto del período antes de que llegara el recorte de tesorería (3,400,000 o 3,800,000 con un tope de 300,000),
el orden de llegada sin dosificar colocaba el presupuesto original completo antes del recorte, mientras que la referencia
dosificada perdía los 400,000, y la línea base alcanzaba o superaba a la referencia (hard con la semilla de reglas 742: 1.03 en
tres de cuatro mundos; medium con la semilla 52: 0.999; las semillas 4 y 9, hasta 0.995). `admissible` exige ahora también
presupuesto ≥ 13 × tope diario (el día en que entra en vigor el recorte). Las semillas de reglas públicas sortean los mismos
valores, así que sus configuraciones y sus cifras no cambian; aproximadamente una cuarta parte de las semillas privadas vuelve a
sortear. Después, la línea base obtiene como mucho 0.95 de la referencia en medium y 0.99 en hard con las semillas 11–130
(mundo público), y como mucho 0.95 con las semillas 4–10 sobre las semillas de mundo 1–3. Sigue abierto: con tres semillas, las
públicas no pueden mostrar `quota_pct` = 35 (comprobado: ningún trío que cubra todos los candidatos tiene una semilla en la que
cada parámetro tenga una alternativa admisible); una cuarta semilla pública lo mostraría.
