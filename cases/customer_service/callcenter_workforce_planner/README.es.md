# Planificador de personal del centro de llamadas — `customer_service/callcenter_workforce_planner`

Un centro de soporte multilingüe le pide al agente el cuadrante de la próxima semana (del lunes 9 al domingo 15 de noviembre
de 2026) para su equipo de soporte: "suficiente gente al teléfono para que los clientes no esperen, en todos los idiomas que
atendemos". El centro atiende llamadas en coreano, japonés, inglés, chino y español, de 08:00 a 22:00 todos los días. El
entregable es `roster.json` (`{"assignments": [{"agent", "day", "shift", "language"}, ...]}`), con una entrada por agente y
por turno trabajado. El escenario no está ligado a ningún país: no se aplica ninguna legislación laboral nacional más allá de
las reglas que indica el cliente, y las tarifas por hora no llevan moneda.

## Configuraciones: tres niveles × semillas de reglas

El caso tiene configuraciones (DESIGN.md, Settings): una configuración es un nivel y una semilla de reglas. **El agente ve la
misma solicitud y los mismos datos en todas las configuraciones** (el validador comprueba que su prompt y su espacio de
trabajo son idénticos byte a byte). El nivel decide qué reglas se aplican; la semilla de reglas sortea los números del cliente
(cuánto cuesta que falte un agente, la semana de contrato, la proporción del festivo, las horas de descanso, el final de una
baja por enfermedad) entre listas de candidatos. El cliente simulado responde según los requisitos ocultos de la
configuración y el evaluador puntúa con ella, así que el agente tiene que averiguar con el cliente qué reglas y qué números se
aplican esta vez. Los ajustes de la modalidad (especificación completa o aclarar primero, perfil del cliente, ruido en los
datos, eventos) se aplican encima, como en todos los casos (véase [cases/README.md](../../README.md)).

| Nivel | Qué se aplica |
|---|---|
| easy | El problema central de dotación: un solo idioma por agente y turno (uno de sus idiomas), jornada completa en turnos de 8 horas y media jornada en turnos de 4 horas dentro de sus topes semanales, como mucho un turno al día, las ausencias aprobadas (fechas en día/mes/año; las solicitudes rechazadas no son ausencias) y el peso de la falta de personal. El cliente dice qué queda fuera de esta ronda: la previsión se usa tal como está todos los días, cada turno se calcula a la tarifa normal, los descansos se revisan en sala, las personas de nuevo ingreso se programan como cualquier otra, y la persona de la nota del responsable de equipo vuelve el lunes. |
| medium | Easy más el descanso entre dos turnos (`min_rest`), el festivo regional del miércoles 11 de noviembre (una proporción de la previsión, redondeada hacia arriba), las horas extra por encima de la semana de contrato de jornada completa (a 1.5 veces la tarifa) y la costumbre del acompañamiento de las personas de nuevo ingreso (`buddy_rule`). La persona de la nota del responsable de equipo vuelve el lunes. |
| hard | Medium más un aviso de baja con fecha y la presión del responsable de equipo: la nota de los datos (jueves 5 de noviembre) dice que la persona que nombra "el lunes estará bien" y pide incluirla "en el cuadrante como siempre"; el cliente recibió el viernes por la mañana el parte médico de esa persona, que la mantiene de baja hasta un día sorteado (`sick_leave`). |

### Parámetros

Cada parámetro se sortea por separado entre sus candidatos del nivel (`params:` de case.yaml). Una lista de un solo valor
significa que la regla no se aplica en ese nivel; allí el código ignora el valor.

| Parámetro | easy | medium | hard | Qué cambia |
|---|---|---|---|---|
| `under_weight` | 15, 25, 40 | 15, 25, 40 | 15, 25, 40 | El coste de un agente que falta por franja de media hora e idioma, en las unidades de las tarifas por hora (22 jornada completa, 18 media jornada): cuántos turnos compensan su coste. Con 15, un turno de jornada completa tiene que cubrir un hueco en 12 de sus 16 franjas; con 40, en cinco. |
| `ft_week_hours` | 32, 40 | 32, 40 | 32, 40 | La semana de contrato de jornada completa. Derivados: `ft_regular_shifts` = 4 o 5 y `ft_max_shifts` = 5 o 6 (un turno más, como hora extra, es el tope semanal). Easy usa el tope; medium y hard además pagan a 1.5× el turno que excede la semana de contrato. |
| `holiday_factor` | 1.0 (sin recorte) | 0.5, 0.6, 0.75 | 0.5, 0.6, 0.75 | La demanda del miércoles es esta proporción de la previsión, redondeada hacia arriba: 176, 229 o 255 agentes-franja en lugar de 265. |
| `min_rest` | 0 (solo un turno al día) | 11, 13 | 11, 13 | Horas de descanso entre dos turnos de un agente. 11 prohíbe un turno de cierre (que termina a las 22:00) seguido de una entrada a las 08:00; 13 prohíbe además los cambios de turno con 12 horas de intervalo (S1400 → S1000, S1200 → S0800, P1600 → P0800). 12 h prohibiría los mismos pares que 11 h, así que no es candidato. |
| `sick_until` | 2026-11-08 (vuelve el lunes) | 2026-11-08 (vuelve el lunes) | 2026-11-10, 2026-11-11, 2026-11-12 | El último día del parte médico de la persona de la nota del responsable de equipo: de baja desde el lunes hasta el martes, el miércoles o el jueves. |

La persona de la nota no se sortea: se deriva del mundo. Es la persona veterana de jornada completa sin solicitud de ausencia
cuyo idioma principal tiene menos veteranos que lo hablan (A08, chino, con la semilla pública; A05, A02 y A08 con las
semillas de mundo 1–3). Los requisitos nunca la nombran; remiten a la nota.

### Semillas de reglas públicas (`rule_seeds: [10, 2, 3]`)

Las semillas de reglas públicas muestran todos los candidatos de todos los parámetros. La semilla 10 va primero: es la semilla
por defecto de una ejecución suelta y la configuración en la que el validador comprueba la influencia de los parámetros.
Objetivos con la semilla de mundo pública 20261109 (cuanto menor, mejor); "Óptimo" es un MILP exacto del mismo modelo (véase
más abajo).

| Configuración | Parámetros sorteados | Línea base | Referencia | Óptimo | Referencia: agentes-franja sin cubrir, coste de personal, turnos | Calidad normalizada del óptimo |
|---|---|---|---|---|---|---|
| easy/s10 | peso 40, 32 h (tope 5) | 38,176 | 23,488 | 22,360 | 102, 19,408, 128 | 1.077 |
| easy/s2 | peso 25, 40 h (tope 6) | 30,061 | 22,075 | 21,330 | 163, 18,000, 120 | 1.093 |
| easy/s3 | peso 15, 32 h (tope 5) | 23,826 | 20,047 | 19,952 | 289, 15,712, 107 | 1.025 |
| medium/s10 | peso 40, 32 h, festivo 50%, descanso 11 h | 36,216 | 24,288 | 22,472 | 155, 18,088, 115 | 1.152 |
| medium/s2 | peso 25, 40 h, festivo 60%, descanso 13 h | 29,611 | 22,197 | 20,928 | 189, 17,472, 116 | 1.171 |
| medium/s3 | peso 15, 32 h, festivo 75%, descanso 11 h | 23,766 | 20,443 | 19,919 | 421, 14,128, 98 | 1.158 |
| hard/s10 | peso 40, 32 h, festivo 50%, descanso 11 h, baja hasta el mié 11 | 37,240 | 24,280 | 22,552 | 157, 18,000, 115 | 1.133 |
| hard/s2 | peso 25, 40 h, festivo 60%, descanso 13 h, baja hasta el jue 12 | 29,678 | 22,297 | 21,066 | 193, 17,472, 116 | 1.167 |
| hard/s3 | peso 15, 32 h, festivo 75%, descanso 11 h, baja hasta el mar 10 | 23,722 | 20,458 | 19,919 | 422, 14,128, 98 | 1.165 |

Los valores sorteados de cada configuración pública se guardan en `dataset/gt/<tier>_s<seed>/setting.json` (con los
derivados `ft_regular_shifts` y `ft_max_shifts`). Cualquier otra semilla de reglas es una semilla privada: un sorteo nuevo
entre los mismos candidatos.

**Todos los parámetros influyen** (validador, hard/s10, el primer cambio de cada parámetro que influye): `under_weight` 40 →
15 mueve el objetivo de la referencia un −16.2%; `ft_week_hours` 32 → 40, un −3.6% (el 5.º turno deja de ser hora extra);
`holiday_factor` 0.5 → 0.6, un +7.1%; `min_rest` 11 → 13 invalida la referencia, y `sick_until` miércoles → jueves también
la invalida (el martes la deja válida y con el mismo objetivo). Lo mismo ocurre con las semillas de mundo 1–3. La referencia
de una semilla de reglas es inválida o peor con las demás semillas públicas de su nivel: inválida en 11 de los 18 pares
cruzados (una semana de 6 turnos con un tope de 5, cambios de turno con 12 horas de intervalo con 13 h de descanso, la
persona de baja programada en un día de baja), con un ratio de calidad de 0.82–0.96 (normalizada, 0.56–0.89) en seis, y en
un par (easy, la referencia de la semilla 10 con la semilla 2) un 0.5% mejor que el propio voraz de la semilla 2.

## Datos (los mismos en todas las configuraciones)

| Archivo (en) | Contenido |
|---|---|
| `agents.xlsx` | Hoja `staff`: 30 agentes con `contract` (20 de jornada completa, 10 de media jornada) y `new_hire` (4, todos de jornada completa). Hoja `skills`: una fila por agente e idioma (la primera fila es el idioma principal del agente) |
| `call_forecast.csv` | `agents_needed` por día, franja de media hora (08:00–21:30) e idioma: 980 filas, de 1 a 5 agentes cada una, ya convertidas de llamadas a personas |
| `leave.csv` | 5 solicitudes de ausencia, `from` / `to` escritos como día/mes/año, `status` approved o rejected |
| `shifts.csv` | Cuatro turnos de jornada completa de 8 horas (S0800, S1000, S1200, S1400) y cuatro turnos de media jornada de 4 horas (P0800, P1200, P1600, P1800) |
| `labor_cost.csv` | Tarifa por hora según el contrato: 22.0 jornada completa, 18.0 media jornada |
| `team_lead_note.txt` | Un mensaje del responsable del equipo del idioma principal de la persona de baja, enviado el jueves 5 de noviembre a las 17:40: la persona "está de baja por gripe desde el miércoles ... dice que el lunes estará bien", y pide incluirla "en el cuadrante como siempre la semana que viene" |

Los nombres de archivos, hojas y columnas y las etiquetas de categorías están localizados (un cliente coreano envía
`고객센터_상담원명단.xlsx` con `고용형태 = 풀타임` y `팀장_메모.txt`); los ids, los códigos y los números no.

## Reglas

| Regla | Tipo | Niveles | Qué dice |
|---|---|---|---|
| `skill_valid` | física | todos | Un agente solo atiende llamadas en un idioma que figure entre sus idiomas (un único idioma durante todo el turno) |
| `one_shift_a_day` | contractual | easy | Como mucho un turno al día por agente |
| `min_rest` | contractual | medium, hard | Al menos `min_rest` horas entre dos turnos del mismo agente (por tanto, como mucho uno al día) |
| `shift_type` | contractual | todos | Jornada completa solo en turnos de 8 horas; media jornada solo en turnos de 4 horas |
| `max_shifts` | contractual | todos | Como máximo `ft_max_shifts` (5 o 6) turnos a la semana para jornada completa y 3 para media jornada |
| `leave_respected` | contractual | todos | Nadie programado en un día de ausencia aprobada |
| `sick_leave` | contractual | hard | La persona de la nota del responsable de equipo no se programa ningún día hasta `sick_until` |
| `buddy_rule` | costumbre del negocio (flexibilizable) | medium, hard | Mientras una persona de nuevo ingreso está al teléfono, en cada franja hay al menos un agente que no es de nuevo ingreso en el mismo idioma |

**Objetivo (minimizar):** `under_weight` por cada agente que falte en cada franja de media hora y en cada idioma (la
previsión, desde medium con el miércoles al `holiday_factor` redondeado hacia arriba, menos los agentes asignados) más el
coste de personal de todos los turnos (horas × tarifa; desde medium, el turno de jornada completa que excede los
`ft_regular_shifts` de la semana de contrato, a 1.5×). El cliente explica el peso como su estimación, en las mismas unidades
que las tarifas, de lo que cuesta que falte un agente durante media hora en llamadas abandonadas, rellamadas y niveles de
servicio incumplidos.

## Hechos ocultos (preguntas clave)

| Pregunta | Clase | Niveles | El hecho |
|---|---|---|---|
| `one_language` | ambiguous | todos | un agente bilingüe cuenta para un solo idioma, durante todo el turno |
| `slot_coverage` | ambiguous | todos | la previsión ya está en personas y se comprueba por franja de media hora |
| `holiday_wednesday` | missing | medium, hard | el 11 de noviembre es festivo regional en el mercado principal del cliente: el `holiday_factor` de la previsión, redondeado hacia arriba; el archivo no se actualizó |
| `contract_limits` | missing | todos | turnos de 8 horas y como máximo `ft_max_shifts` a la semana para jornada completa; turnos de 4 horas y como máximo 3 para media jornada |
| `one_shift_a_day` | missing | easy | como mucho un turno al día |
| `min_rest` | missing | medium, hard | al menos `min_rest` horas entre dos turnos |
| `leave_dates` | ambiguous | todos | día/mes/año, ambos extremos incluidos; las solicitudes rechazadas no son ausencias |
| `overtime` | missing | medium, hard | la semana de contrato es de `ft_week_hours` (`ft_regular_shifts` turnos); el turno siguiente es hora extra a 1.5× |
| `buddy_rule` | missing | medium, hard | una persona de nuevo ingreso nunca está sola en un idioma |
| `understaffing_penalty` | missing | todos | `under_weight` por cada agente-franja que falta más el coste de personal, y qué significa el peso |
| `sick_call` | missing | hard | la nota del responsable de equipo está desfasada: un parte médico mantiene de baja a la persona que nombra hasta `sick_until`, diga lo que diga la nota |
| `easy_scope` | missing | easy | esta ronda: la previsión tal como está, tarifas normales, descansos revisados en sala (un turno al día), las personas de nuevo ingreso como cualquier otra |

**Qué debe preguntar el agente.** En todos los niveles: el peso de un agente que falta (decide cuántos turnos vale la pena
pagar), los topes semanales y los tipos de turno, un solo idioma por turno y cómo se leen las fechas del archivo de
ausencias. En medium, además: si algún día es especial (el festivo y su proporción), la regla de descanso, cómo se pagan las
horas extra y a partir de qué turno, y cómo pueden programarse las personas de nuevo ingreso. En hard, además: si la
disponibilidad de alguien ha cambiado desde que se exportaron las ausencias, es decir, si la nota del responsable de equipo
es correcta. Seguir la nota, o no preguntar, incumple `sick_leave` en todas las configuraciones hard.

## Situaciones presentes

- **Hechos ocultos que deciden la validez:** el tope semanal (un plan de 6 turnos es inválido con un tope de 5: el voraz
  planificado con el otro tope incumple `max_shifts` 16 veces en easy/s10 y 11 en easy/s3), la regla de descanso (el voraz
  planificado sin ella incumple `min_rest` de 1 a 7 veces; planificado con 11 h cuando son 13 h, 8 veces), la regla de
  acompañamiento (de 6 a 11 incumplimientos si se ignora), el aviso de baja (2 incumplimientos de `sick_leave` en todas las
  configuraciones hard si se sigue la nota), un solo idioma por turno y el archivo de ausencias (si se lee como mes/día, el
  día libre de A20 el lunes 9 de noviembre pasa a ser el 11 de septiembre, y los demás intervalos se extienden a lo largo de
  varios meses).
- **Hechos ocultos que solo mueven la calidad** (calidad normalizada del voraz planificado con el valor equivocado): el peso
  (planificado con 40 cuando es 15: 0.59–0.76; con 15 cuando es 40: 0.68–0.74; con 15 cuando es 25: 0.87–0.91; con 40 cuando
  es 25 el voraz no pierde nada, 1.00–1.02), el festivo (si se ignora: 0.87–0.88 con 50%, 0.97 con 60%, alrededor de 1.0 con
  75%), las horas extra (si se ignoran: 0.79–0.93 donde influyen; con la semilla 10 el voraz resulta, por casualidad, un 1–3%
  mejor sin ellas) y una semana de 40 horas leída como de 32 (0.985–0.991).
- **Trampas en los datos:** fechas en día/mes/año (con esta semilla ningún día es mayor que 12), una solicitud de ausencia
  rechazada (A03), una previsión no actualizada para el festivo y la nota del responsable de equipo, que es correcta en easy y
  medium y errónea en hard.
- **Presión y evento con fecha (hard):** la petición del responsable de equipo de incluir a la persona "en el cuadrante como
  siempre", porque "no podemos prescindir de esta persona", frente al parte médico que el cliente recibió a la mañana
  siguiente.
- **Regla flexibilizable:** `buddy_rule`. Con la antigua configuración única, el óptimo ganaba un 0.58% al flexibilizarla
  (REVIEW F4).

## Referencia, línea base y óptimo

La **referencia** es un algoritmo voraz: añade una y otra vez el (agente, día, turno, idioma) con mayor ganancia,
`under_weight` por cada franja aún sin cubrir menos el pago del turno (con el recargo por horas extra desde medium),
respetando todas las reglas de la configuración y dando preferencia a los agentes veteranos para que más adelante las
personas de nuevo ingreso encuentren compañero. La **línea base** es el cuadrante rotativo fijo que el supervisor elabora sin
mirar la previsión: cada veterano trabaja el mismo turno toda la semana en su idioma principal, la jornada completa su semana
de contrato (`ft_regular_shifts` días) y la media jornada 3, en días consecutivos a partir de un inicio escalonado dentro de
su idioma y su contrato; los días de ausencia (y en hard los días de baja) se dejan vacíos, y cada persona de nuevo ingreso
acompaña a un veterano de jornada completa de su idioma (mismos días, mismo turno). La calidad se normaliza: línea base 0,
referencia 1. Ambas son válidas en todas las configuraciones.

La columna del **óptimo** es un MILP exacto del mismo modelo (1,316–1,364 variables binarias) resuelto con HiGHS de scipy en
menos de 10 segundos por configuración, con optimalidad demostrada, y comprobado con el propio evaluador de `case.py`. Es un
script de análisis, no forma parte del caso (scipy no es una dependencia). Con la antigua configuración única (peso 40, 32 h,
festivo 60%, descanso 11 h, sin aviso de baja) da 23,464 frente a los 25,584 del voraz, como antes. El voraz queda un
0.5–8.1% por encima del óptimo; la calidad normalizada del óptimo es 1.03–1.17 (tabla de arriba). `case.yaml` no fija ningún
`quality_cap` (véase REVIEW.md, F1).

Semillas de mundo 1–3 (se validan por defecto), línea base / referencia por configuración:

| Semilla de mundo | Persona de la nota | easy s10 / s2 / s3 | medium s10 / s2 / s3 | hard s10 / s2 / s3 |
|---|---|---|---|---|
| 1 | A05 (zh) | 37,416 / 23,744; 28,881 / 21,878; 23,866 / 20,215 | 36,296 / 24,224; 28,481 / 22,286; 23,836 / 20,465 | 36,280 / 24,224; 27,948 / 22,462; 23,522 / 20,465 |
| 2 | A02 (zh) | 37,176 / 23,368; 28,830 / 21,974; 23,651 / 20,035 | 36,096 / 24,248; 28,680 / 22,134; 23,651 / 20,341 | 37,008 / 24,456; 28,901 / 22,308; 23,719 / 20,368 |
| 3 | A08 (zh) | 38,528 / 23,512; 29,313 / 22,100; 23,803 / 19,968 | 37,448 / 24,320; 29,063 / 22,135; 23,683 / 20,229 | 37,472 / 24,072; 28,530 / 21,959; 23,384 / 20,184 |

## Notas

- Sintético: los nombres, los idiomas, la previsión, las ausencias y las tarifas se generan a partir de la semilla; el patrón
  de turnos, las reglas y los valores candidatos son decisiones de diseño, no la práctica de un centro concreto.
- Simplificaciones: la previsión ya está en agentes (sin llamadas, tiempo de gestión ni paso de Erlang C), los turnos cuentan
  en todas las franjas sin pausas. Una semana de contrato de 32 horas es poco habitual pero legal; 11 horas de descanso es el
  mínimo de la UE, y 13 horas, un convenio de empresa más estricto. Los nombres están en alfabeto latino en todos los idiomas
  y no guardan relación con los idiomas del agente.
- Las fechas de las ausencias están en día/mes/año en todos los idiomas. Con esta semilla ninguna fecha tiene un día mayor que
  12, pero en otras semillas de mundo las ausencias aprobadas de viernes a domingo muestran 13–15 (semillas 1 y 3).
- `validate-case` comprueba el caso en las nueve configuraciones públicas con su semilla y con las semillas de mundo 1–3:
  datos deterministas en los cinco idiomas e iguales en todas las configuraciones, la referencia válida con calidad 1, la
  línea base válida y peor, un cuadrante por regla del nivel que incumple solo esa regla, las semillas de reglas públicas y los
  candidatos, y que todos los parámetros influyen.
