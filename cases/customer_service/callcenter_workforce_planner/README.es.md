# Planificador de personal del centro de llamadas — `customer_service/callcenter_workforce_planner`

Un centro de soporte multilingüe le pide al agente el cuadrante de la próxima semana (del lunes 9 al domingo 15 de noviembre
de 2026) para su equipo de soporte: "suficiente gente al teléfono para que los clientes no esperen, en todos los idiomas que
atendemos". El centro atiende llamadas en coreano, japonés, inglés, chino y español, de 08:00 a 22:00 todos los días. El
entregable es `roster.json` (`{"assignments": [{"agent", "day", "shift", "language"}, ...]}`), con una entrada por agente y
por turno trabajado. El escenario no está ligado a ningún país: no se aplica ninguna legislación laboral nacional más allá de
las reglas que indica el cliente, y las tarifas por hora no llevan moneda.

El caso **no tiene configuraciones**: el mismo problema, las mismas reglas y la misma solución correcta en todas las
dificultades. Los ajustes de la modalidad (especificación completa o aclarar primero, perfil del cliente, ruido en los
datos, eventos) se aplican encima, como en todos los casos (véase [cases/README.md](../../README.md)).

## Datos

| Archivo (en) | Contenido |
|---|---|
| `agents.xlsx` | Hoja `staff`: 30 agentes con `contract` (20 de jornada completa, 10 de media jornada) y `new_hire` (4, todos de jornada completa). Hoja `skills`: una fila por agente e idioma (la primera fila es el idioma principal del agente) |
| `call_forecast.csv` | `agents_needed` por día, franja de media hora (08:00–21:30) e idioma: 980 filas, de 1 a 5 agentes cada una, ya convertidas de llamadas a personas |
| `leave.csv` | 5 solicitudes de ausencia, `from` / `to` escritos como día/mes/año, `status` approved o rejected |
| `shifts.csv` | Cuatro turnos de jornada completa de 8 horas (S0800, S1000, S1200, S1400) y cuatro turnos de media jornada de 4 horas (P0800, P1200, P1600, P1800) |
| `labor_cost.csv` | Tarifa por hora según el contrato: 22.0 jornada completa, 18.0 media jornada |

Los nombres de archivos, hojas y columnas y las etiquetas de categorías están localizados (un cliente coreano envía
`고객센터_상담원명단.xlsx` con `고용형태 = 풀타임`); los ids, los códigos y los números no.

## Reglas

| Regla | Tipo | Qué dice |
|---|---|---|
| `skill_valid` | física | Un agente solo atiende llamadas en un idioma que figure entre sus idiomas (un único idioma durante todo el turno) |
| `min_rest` | física | Al menos 11 horas entre dos turnos del mismo agente (por tanto, como mucho uno al día) |
| `shift_type` | contractual | Jornada completa solo en turnos de 8 horas; media jornada solo en turnos de 4 horas |
| `max_shifts` | contractual | Como máximo 5 turnos a la semana para jornada completa y 3 para media jornada |
| `leave_respected` | contractual | Nadie programado en un día de ausencia aprobada |
| `buddy_rule` | costumbre del negocio (flexibilizable) | Mientras una persona de nuevo ingreso está al teléfono, en cada franja hay al menos un agente que no es de nuevo ingreso en el mismo idioma |

**Objetivo (minimizar):** 40 por cada agente que falte en cada franja de media hora y en cada idioma (la previsión, con el
miércoles al 60% redondeado hacia arriba, menos los agentes asignados) más el coste de personal de todos los turnos
(horas × tarifa, el 5.º turno semanal de jornada completa a 1.5×). El cliente explica el 40 como su estimación, en las mismas
unidades que las tarifas, de lo que cuesta que falte un agente durante media hora en llamadas abandonadas, rellamadas y
niveles de servicio incumplidos.

## Hechos ocultos (9 preguntas clave)

`one_language` (un agente bilingüe cuenta solo para un idioma), `slot_coverage` (la previsión ya está en personas y se
comprueba por franja de media hora), `holiday_wednesday` (el 11 de noviembre es festivo regional en el mercado principal del
cliente: el 60% de la previsión, redondeado hacia arriba; el archivo no se actualizó), `contract_limits`, `min_rest`,
`leave_dates` (día/mes/año, ambos extremos incluidos; las solicitudes rechazadas no son ausencias), `overtime` (4 turnos
normales, el 5.º a 1.5×), `buddy_rule`, `understaffing_penalty` (el 40 y el modelo de costes).

## Situaciones presentes

- **Hechos ocultos que deciden la validez:** la regla de descanso (un optimizador que no la conoce produce 13 incumplimientos de
  `min_rest` con esta semilla), los tipos de turno y los topes según el contrato, un solo idioma por turno y el archivo de
  ausencias (si se lee como mes/día, el día libre de A20 el lunes 9 de noviembre pasa a ser el 11 de septiembre, y los demás
  intervalos se extienden a lo largo de varios meses).
- **Hechos ocultos que solo mueven la calidad:** el festivo (demanda del miércoles 265 → 229 agentes-franja), el recargo por
  horas extra y el peso de la falta de personal.
- **Trampas en los datos:** fechas en día/mes/año (con esta semilla ningún día es mayor que 12), una solicitud de ausencia
  rechazada (A03) y una previsión no actualizada para el festivo.
- **Regla flexibilizable:** `buddy_rule`. En el óptimo, flexibilizarla mejora el objetivo un 0.58%.
- **Ninguna nota de presión ni evento con fecha** en el propio caso; solo los eventos genéricos de la modalidad `messy`.

## Referencia, línea base y óptimo (semilla 20261109)

La **solución de referencia** es un algoritmo voraz: añade una y otra vez el (agente, día, turno, idioma) con mayor ganancia,
40 por cada franja aún sin cubrir menos el pago del turno (con el recargo por horas extra), respetando todas las reglas y
dando preferencia a los agentes veteranos (los que no son de nuevo ingreso) para que más adelante las personas de nuevo
ingreso encuentren compañero. La **línea base** es el cuadrante rotativo fijo que el supervisor elabora sin mirar la
previsión: cada veterano trabaja el mismo turno toda la semana en su idioma principal, la jornada completa sus 4 días
normales y la media jornada 3, en días consecutivos a partir de un inicio escalonado dentro de su idioma y su contrato; los
días de ausencia se dejan vacíos, y cada persona de nuevo ingreso acompaña a un veterano de jornada completa de su idioma
(mismos días, mismo turno). La calidad se normaliza: línea base 0, referencia 1.

| Cuadrante | Objetivo | Agentes-franja sin cubrir | Coste de personal | Turnos | Ratio respecto a la referencia | Calidad normalizada |
|---|---|---|---|---|---|---|
| Línea base (rotación fija) | 37,376 | 554 | 15,216 | 103 | 0.685 | 0 |
| Referencia (voraz) | 25,584 | 183 | 18,264 | 116 | 1 | 1 |
| Óptimo (MILP) | 23,464 | 75 | 20,464 | 126 | 1.090 | 1.180 |
| Óptimo que ignora el festivo | 23,872 | | | | 1.072 | 1.145 |
| Óptimo que ignora las horas extra, o sin conocer el peso | 23,560 | | | | 1.086 | 1.172 |
| Óptimo sin la regla de acompañamiento (válido solo si se flexibiliza) | 23,328 | | | | 1.097 | 1.191 |
| Un solo turno (A01, lunes, S0800, en) | 67,656 | | | 1 | 0.378 | 0 (acotado en el mínimo) |

El óptimo es el techo conocido: un MILP exacto del mismo modelo (unas 2,000 variables binarias) resuelto con HiGHS de scipy
en unos 8 segundos, con optimalidad demostrada, y comprobado con el propio evaluador de `case.py`. Es un script de análisis,
no forma parte del caso (scipy no es una dependencia). Con el tope de la política por defecto de 1.5, la referencia obtiene
0.67 del componente de calidad y el óptimo 0.79; `case.yaml` no fija ningún `quality_cap` (véase REVIEW.md, F1).

Semillas de mundo 1–3 (se validan por defecto):

| Semilla de mundo | Línea base | Referencia | Óptimo | Calidad normalizada del óptimo |
|---|---|---|---|---|
| 1 | 36,776 | 25,232 | 23,672 | 1.135 |
| 2 | 36,936 | 25,336 | 23,544 | 1.155 |
| 3 | 37,848 | 25,440 | 23,248 | 1.177 |

## Notas

- Sintético: los nombres, los idiomas, la previsión, las ausencias y las tarifas se generan a partir de la semilla; el patrón
  de turnos y las reglas son decisiones de diseño, no la práctica de un centro concreto.
- Simplificaciones: la previsión ya está en agentes (sin llamadas, tiempo de gestión ni paso de Erlang C), los turnos cuentan
  en todas las franjas sin pausas, la semana normal de jornada completa es de 4 turnos (32 horas), y 11 horas de descanso es
  el mínimo de la UE pero queda por debajo de las 12 de España. Los nombres están en alfabeto latino en todos los idiomas y no
  guardan relación con los idiomas del agente.
- Las fechas de las ausencias están en día/mes/año en todos los idiomas. Con esta semilla ninguna fecha tiene un día mayor que
  12, pero en otras semillas de mundo las ausencias aprobadas de viernes a domingo muestran 13–15 (semillas 1 y 3).
- `validate-case` comprueba el caso con su semilla y con las semillas de mundo 1–3: datos deterministas en los cinco idiomas,
  la referencia válida con calidad 1, la línea base válida y peor, y un cuadrante por regla que incumple solo esa regla.
