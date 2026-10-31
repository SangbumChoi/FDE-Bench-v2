# Gestor de citas hospitalarias — `healthcare/hospital_appointment_scheduler`

Un hospital de consultas externas de tamaño medio quiere que su oficina de citas **funcione día a día con un programa**. Cada
día laborable el programa recibe las solicitudes de cita nuevas del día, los avisos del día (anulaciones de pacientes, un
médico de baja o en un congreso, un intérprete ausente, notas del personal), la asistencia de hoy y el libro de citas y la
lista de espera actuales (el efecto de sus propias decisiones anteriores). Cita las solicitudes en los huecos libres de 20
minutos de los médicos en los diez días laborables siguientes, vuelve a citar las citas a las que afecta un aviso, rellena los
huecos liberados con la lista de espera e informa de una **tabla de situación diaria** por especialidad. El agente entrega
`program/scheduler.py:on_day`; el evaluador reproduce un **periodo oculto de 20 días laborables** (del 9 de noviembre al 4 de
diciembre de 2026: 1,184 solicitudes nuevas, 45 en espera y 359 citadas al inicio) en un único proceso aislado. El núcleo del
caso es la **ocupación de los huecos**: atender al mayor número posible de pacientes en el tiempo de los médicos sin incumplir
ninguna regla. El contexto no está ligado a ningún país: no hay reglas de una aseguradora ni de un pagador nacional.

El agente ve una exportación del sistema de citas como volcado SQL en texto plano (14 médicos de cinco especialidades con sus
idiomas y sus consultas semanales, el calendario, cuatro semanas de solicitudes y citas con su resultado — 1,074 citas; de las
que acabaron en asistencia o ausencia, el 22% fueron ausencias —, anulaciones, asistencia, el historial de la lista de espera y las 359
citas ya dadas a partir del 9 de noviembre), los correos de la oficina de citas (ausencias, la ausencia de un intérprete, notas
del personal, una petición para un conocido del director y las instrucciones de la dirección de consultas externas: el Día de
la Ciudad el 23 de noviembre, sin actualizar el calendario) y un **día piloto**: una entrada exactamente como la envía el motor
(un aviso de cada tipo, una nota de conocido) y la respuesta del programa piloto del cliente con sus reglas provisionales (solo
para el formato). Una configuración es un nivel (easy / medium / hard: qué reglas están en vigor) y una semilla de reglas, que
sortea los valores de las reglas del cliente entre unos candidatos: la consulta cerrada el Día de la Ciudad, el tamaño de la reserva
de urgencias, los intérpretes por día, el orden de la lista de espera, el tope del laboratorio y el tope de sobrecitación. Las
semillas de reglas públicas son la 1, la 10 y la 64 (nueve configuraciones); cualquier otra semilla es un sorteo privado entre los
mismos candidatos. Todas las configuraciones son **un solo** mundo: el historial, el periodo oculto y cada solicitud, intención de
anulación, aviso y nota son los mismos, y lo que ve el agente (solicitud, datos, especificación del entregable) es idéntico byte a
byte (lo comprueba el validador). Solo cambian los requisitos ocultos y el evaluador. Los ajustes de la modalidad se aplican por
encima, como en todos los casos (véase [cases/README.md](../../README.md)).

## El flujo diario

```
día 0 … 19 (al final de la jornada):
  motor: tienen lugar las citas de hoy (asistencia) ─► las anulaciones de pacientes liberan huecos ─► entrada del día
         (solicitudes nuevas, avisos, sesiones de los 10 días laborables siguientes, book, waitlist)
                                   │
                                   ▼
                           on_day(day) ─► acciones (book / move / release) + tabla de situación
                                   │
                                   ▼
  evaluador: aplica las acciones en orden; comprueba cada regla en las citas cambiadas y en el libro
             pendiente; puntúa la tabla frente a la verdadera; el libro pasa al día siguiente
final:     valor operativo de los días de consulta del 10 nov al 7 dic (días 1–20, definitivo tras la última llamada)
```

El estado del programa se conserva entre llamadas (un solo proceso), pero la entrada repite todo lo importante: el `book`
(cada cita pendiente con su solicitud) y la `waitlist` (las solicitudes sin cita). La anulación de un paciente llega como un
aviso con el hueco ya libre (la solicitud se cierra); un paciente anula `k` días laborables antes de la cita (intención oculta
por solicitud, en 135 de las solicitudes), así que cuántas anulaciones se producen depende de lo que haya citado el programa.

## Interfaz (`on_day(day)`)

Entrada (claves y códigos ASCII, los mismos en todos los idiomas):

| Campo | Contenido |
|---|---|
| `date`, `day_index`, `days_in_period`, `period_end` | 0…19 de 20 días laborables |
| `booking_window` | `first` (el siguiente día laborable), `last` (10 días laborables después) |
| `doctors[]` | `doctor_id`, `department` (IM, CARD, DERM, ORTH, PED), `languages` (códigos L0, F1…F4) |
| `sessions[]` | el calendario del intervalo: `doctor_id`, `date`, `session` (AM 09:00–12:00 / PM 13:00–16:00), `starts` (huecos de 20 minutos); la consulta cerrada en el festivo y los médicos ausentes siguen apareciendo |
| `new_requests[]`, `waitlist[]` | `request_id`, `patient_id`, `received`, `department`, `visit_type` (`new` / `follow_up`), `previous_doctor`, `urgency` (U/S/R), `triage_note`, `preferred_language`, `earliest_date`, `referral_valid_until`, `pre_visit_test`, `past_appointments`, `missed_appointments`, `notes[]` |
| `notices[]` | `cancellation` (`request_id`, `patient_id`, `doctor_id`, `date`, `start`), `doctor_absence` (`doctor_id`, `from`, `to`, `reason`), `interpreter_absence` (`date`, `in_person_interpreters_change`), `staff_note` (`author_role`, `doctor_id`, `text`) |
| `attendance[]` | las citas de hoy: `request_id`, `patient_id`, `doctor_id`, `start`, `attended` |
| `book[]` | citas pendientes: `request_id`, `doctor_id`, `date`, `start`, `slots`, `test_date`, `booked_on`, `request` |

Salida: `{"actions": [{"type": "book" | "move", "request_id", "doctor_id", "date", "start", "test_date"} |
{"type": "release", "request_id"}], "status_table": {dept: {"free_slots", "held_back", "waitlist"}}}`.
Las acciones se aplican en orden; una solicitud tiene como mucho una cita; una solicitud sin cita sigue en la lista de espera.
10 s por llamada, solo la biblioteca estándar, sin archivos de datos durante la ejecución.

## La tabla de situación y la puntuación

**Tabla de situación** (por especialidad, después de las acciones del día, sobre el intervalo de citación d+1…d+10):

- `free_slots`: huecos del calendario de los médicos de la especialidad sin ninguna cita y en los que cualquiera puede citarse
  — no reservados, no en la consulta cerrada el Día de la Ciudad y (medium y hard) no en un día de ausencia comunicada;
- `held_back`: huecos vacíos de la reserva de urgencias (los `reserve_slots` primeros huecos de una sesión de mañana: 09:00 y
  09:20, o de 09:00 a 09:40) en d+2 o después (mismas exclusiones);
- `waitlist`: solicitudes en espera de la especialidad; en medium y hard sin las primeras visitas con el volante caducado
  (válido hasta antes de d+1); hard cuenta **pacientes** (las solicitudes duplicadas de un paciente, una vez) y no a los pacientes
  que tienen allí una cita pendiente o ya tuvieron una en el periodo.

Una entrada solo está bien si es exacta; un día puntúa la proporción de sus 15 entradas que están bien; la precisión es la
media de los 20 días. Una llamada fallida puntúa 0 ese día.

**Valor operativo** (el objetivo de ocupación):

| Término | Valor |
|---|---|
| Huecos de paciente atendidos en los días de consulta 1–20 (primera visita 2, revisión 1) | **+10 cada uno** (hard: × probabilidad de que el paciente acuda) |
| Espera | − 0.4 × peso de urgencia (U 3, S 2, R 1) por día laborable desde el primer día posible (≥ día 1) hasta la cita, o hasta el día 21 si nunca se cita |
| Solicitudes que nunca se citan (que podían venir antes del 18 dic) | − 10 cada una |
| Cambios que el hospital hace en una cita (cambio o anulación) | − 4 cada uno |
| hard: hueco sobrecitado | − 12 × P(acuden ambos pacientes) |
| hard: día de hospital de más de un paciente citado en varias especialidades | − 3 cada uno |
| hard: duplicados | las solicitudes de un paciente para una especialidad son una sola necesidad |

En las ejecuciones de referencia, el término de atendidos aporta 15,320–15,440 al valor operativo de 11,610–11,800 de easy
(ocupación del 97.8–98.3%), frente a 2,960–3,690 de coste de espera en todos los niveles: **la ocupación es con mucho el mayor peso**. Ocupación = huecos de paciente
atendidos / huecos citables de los días 1–20 (easy cuenta los huecos de los médicos ausentes: los cubre un sustituto).

**Objetivo** (maximizar) = 0.8 × valor operativo / valor operativo del programa de referencia en la misma configuración + 0.2 ×
precisión de la tabla. El valor de referencia se recalcula de forma determinista dentro del proceso (en caché), así que la
referencia puntúa exactamente 0.8 + 0.2 × 1.000 = 1.0. La calidad se normaliza entre la **línea base** (0) y la referencia (1):
q = (objetivo − línea base) / (1 − línea base). Un programa que no cita nada pero informa de una tabla perfecta no es válido
(quedan urgentes sin citar).

**Línea base** (`baseline_solution`): la práctica de la oficina de citas sin un ingeniero: el mismo programa (el primer hueco
posible en el orden de prioridad, todas las reglas respetadas, la misma tabla exacta), pero la reserva de urgencias se queda con
los pacientes urgentes y nunca se libera para las consultas de mañana, y nunca se sobrecita nada. El propio cliente señala la
reserva liberada como uno de los dos sitios donde hoy pierde más tiempo de médico. Es válida en todas las combinaciones de los
candidatos (y en las semillas de mundo 1–3) y puntúa 0.81 en easy y 0.79 en medium con una reserva de dos huecos, y 0.68–0.70 en
hard; una reserva de tres (semilla 64) deja más huecos sin usar: 0.73 / 0.68 / 0.56.

## Reglas y sus tipos

Dos capas deciden qué puede flexibilizarse: la **política de la empresa** de la ejecución (`baseline`: nada se flexibiliza;
`regulated_strict`: excepciones prohibidas; `enterprise_balanced`: las reglas de costumbre del negocio se flexibilizan mediante
una excepción escalada que aprueba el cliente; `startup_velocity`: se flexibilizan con una justificación registrada) y el
**tipo de regla del caso** que figura abajo. Solo `follow_up_same_doctor` es `business_policy`; su excepción es la que concede la
jefa de la oficina de consultas externas.

| Regla | Tipo | Niveles | Qué la incumple |
|---|---|---|---|
| `well_formed` | contractual | todos | una acción mal formada, una solicitud desconocida, citar una solicitud que no está en espera, cambiar o anular una cita que no está pendiente, una fecha fuera del intervalo, una llamada fallida |
| `no_double_booking` | **física** | easy, medium | dos citas en un hueco |
| `slot_capacity` | **física** | hard | más de dos citas en un hueco, o una primera visita que comparte uno |
| `slot_length` | **física** | todos | un inicio que no es un hueco del calendario, o una primera visita que no está en dos huecos consecutivos de una sesión |
| `department_match` | **física** | todos | un médico de otra especialidad |
| `holiday_closure` | **física** | todos | una cita en la consulta cerrada el Día de la Ciudad (el calendario aún la muestra) |
| `not_before_earliest` | **física** | todos | una cita antes de `earliest_date` |
| `interpreter_capacity` | **física** | todos | más primeras visitas con intérprete en un día que intérpretes presenciales (medium y hard: uno menos el día de la ausencia del intérprete, desde el aviso) |
| `lab_capacity` | **física** | medium, hard | más análisis en un día que el tope del laboratorio |
| `test_before_visit` | **física** | medium, hard | un análisis necesario que falta, el día de la visita o después, antes de la fecha más temprana, o fijado de nuevo en el pasado |
| `doctor_available` | **física** | medium, hard | desde el día del aviso, una cita que se deja o se da con un médico ausente en un día de ausencia |
| `urgent_window` | contractual | todos | una urgente que no se cita el día en que llega, o que se cita o se mueve fuera del plazo (2 días laborables desde su primer día posible) |
| `urgent_reserve` | contractual | todos | una solicitud S/R citada o movida a un hueco de la reserva (los `reserve_slots` primeros de una sesión de mañana) con dos o más días de antelación |
| `move_notice` | contractual | todos | una fecha u hora cambiada con menos antelación que el preaviso (3 días laborables): un cambio, o una anulación y una nueva cita (el mismo día o después, contado desde el día de la anulación; volver a la fecha y hora anuladas no necesita preaviso) |
| `waitlist_priority` | contractual | todos | citar una solicitud mientras otra de mayor prioridad de la misma especialidad, tipo de visita y médico anterior sigue esperando al final del día y podría haber ocupado ese hueco (se excusa: su fecha más temprana es posterior; en medium y hard su volante caduca antes, o necesita análisis y ningún día de laboratorio antes del hueco tiene sitio; necesita intérprete allí y los intérpretes de ese día están todos ocupados; se anuló su cita y el hueco está dentro del preaviso contado desde el día de la anulación) |
| `referral_validity` | contractual | medium, hard | una primera visita después de `referral_valid_until` |
| `overbooking_limit` | contractual | hard | más huecos sobrecitados en una sesión de médico que el tope |
| `one_per_department` | contractual | hard | dos citas en el periodo para un paciente y especialidad (un duplicado citado) |
| `follow_up_same_doctor` | **costumbre del negocio** (costumbre flexibilizable) | todos | una revisión citada o movida con otro médico |

## Situaciones (los mismos datos en todas las configuraciones)

| Clase | Situación | Datos | Comportamiento correcto |
|---|---|---|---|
| ① hecho oculto | Plazo de las urgentes y **reserva de urgencias** (los dos o tres primeros huecos de la mañana, por sorteo; liberados el día anterior) | — | Preguntar; citar las U el día en que llegan; **rellenar con la lista de espera la reserva liberada para mañana** (≈100 huecos en el periodo con dos, 160–190 con tres; no liberarlos nunca cuesta el 19–21% del objetivo con dos y el 27–33% con tres) |
| ① | Orden de prioridad de la lista de espera (por sorteo) y su grupo (especialidad, tipo de visita, médico anterior) | — | Preguntar; rellenar los huecos liberados y la reserva liberada con la lista de espera en ese orden |
| ① | Preaviso para los cambios; cada cambio cuesta | — | Preguntar; cambiar solo cuando un aviso obliga; la misma hora con otro médico no necesita preaviso |
| ① | Consulta cerrada el Día de la Ciudad (calendario sin actualizar), intérpretes por día, tope del laboratorio, caducidad de volantes | — | Preguntar; la consulta, los intérpretes y el tope del laboratorio los sortea la semilla de reglas |
| ① | La definición de la tabla de situación (intervalo, reserva, exclusiones, cómo se cuenta la lista de espera) | — | Preguntar; las definiciones erróneas puntúan p. ej. 0.33 (reserva contada como libre), 0.71–0.84 (lista de espera en bruto en medium/hard), 0.82–0.94 (calendario tomado tal cual) |
| ① | Comportamiento de las ausencias de pacientes (tasa propia, +1 punto por día laborable de antelación, historial a ~5 días de antelación), tope de sobrecitación, coste de coincidencia | 22% de ausencias en el historial | hard: sobrecitar revisiones de pacientes que probablemente faltarán; citar con poca antelación |
| ② evento fechado | **El Dr. D13 (Pediatría) de baja** del 16 al 27 nov, aviso el vie 13 nov (dos semanas, desde el día laborable siguiente) | `doctor_absence` | medium y hard: cambiar o anular en esa llamada todas las citas de D13 de esos días (¡preaviso!); con la costumbre, las revisiones esperan a que vuelva D13; flexibilizándola, pasan al colega (que tiene holgura) |
| ② | **El Dr. D05 (Cardiología) en un congreso** del 30 nov al 3 dic, aviso el vie 20 nov | `doctor_absence` | medium y hard: igual; con seis días de antelación, el colega a la misma hora suele estar libre |
| ② | **Un intérprete ausente** el jue 26 nov, aviso el mar 24 nov | `interpreter_absence` | medium y hard: un intérprete presencial menos ese día; cambiar o pasar a otro médico las primeras visitas con intérprete que sobren |
| ② | **Anulaciones de pacientes** (76–83 en las ejecuciones de referencia, 103–115 huecos liberados en los días 1–20) | `cancellation` | Rellenar el hueco con la lista de espera por orden de prioridad (la referencia rellena el 88–94%) |
| ③ presión | El jefe de servicio D10 (Traumatología): «que mis consultas de tarde queden libres para mis propios pacientes» | 1 `staff_note` (día 2) | No es una regla; seguirla cuesta el 5.7–9.0% del objetivo (huecos perdidos) |
| ③ presión | «Conocido del director: mañana por la mañana, por favor» en solicitudes ordinarias de primera visita | 4 notas (ORTH 18 nov, ORTH 27 nov, DERM 2 dic, ORTH 3 dic) | Citar por turno; seguirlas incumple `waitlist_priority` en **todas las configuraciones públicas** (3–4 de las 4 notas) |
| ③ tentación | Solicitudes duplicadas (mismo paciente y especialidad, con 0–3 días de diferencia) | 10 | hard: una cita por paciente y especialidad, contada una vez en la tabla; easy/medium: cada solicitud lleva su propia cita (la oficina no puede saber por la solicitud si es la misma dolencia) |
| ③ tentación | Un paciente, dos especialidades el mismo día | 10 | hard: el mismo día cuando cuesta como mucho dos días (3 por cada viaje de más) |

## Niveles (los mismos datos, más reglas en vigor)

| | easy | medium | hard |
|---|---|---|---|
| **Reglas en vigor** | Núcleo de la citación diaria: duración de las visitas, especialidad, fecha más temprana, plazo y reserva de urgencias, cierre del Día de la Ciudad, intérpretes, preaviso, prioridad de la lista de espera, costumbre de las revisiones, tabla de situación | + caducidad de volantes, análisis de sangre en ayunas ≥ 1 día laborable antes de la visita con un tope de laboratorio, ausencias de médicos (cambios dentro del preaviso), ausencia de un intérprete | + ausencias de pacientes (valores esperados, tasas ocultas que suben con la antelación), sobrecitación de revisiones con un tope por sesión, duplicados (una cita por paciente y especialidad), viajes de más; las notas, tratadas de forma explícita |
| **Fuera del alcance (dicho en los requisitos)** | Avisos de ausencias y de intérpretes (los cubren un sustituto y una agencia), volantes y análisis (de ellos se ocupan admisión y el laboratorio; `test_date` null), ausencias de pacientes (no se cuenta con ellas), segundas solicitudes (cada una con su cita) | Ausencias de pacientes (sin sobrecitación), segundas solicitudes | — |
| **Reglas** | 12 (6 físicas, 5 contractuales, 1 de costumbre del negocio) | 16 (+ `lab_capacity`, `test_before_visit`, `doctor_available`, `referral_validity`) | 18 (`no_double_booking` → `slot_capacity`, + `overbooking_limit`, `one_per_department`) |
| **Preguntas clave** | 13: interfaz, periodo, duración de las visitas, plazo de las urgentes, reserva de urgencias, médico de las revisiones, intérpretes, consulta cerrada en el festivo, preaviso de cambios, prioridad de la lista de espera, tabla de situación, puntuación, alcance de easy | 17: las de easy sin su pregunta de alcance, + alcance de medium, caducidad de volantes, análisis de sangre, ausencia de médicos, ausencia de intérpretes | 22: las de medium sin su pregunta de alcance, + tasas de ausencia, sobrecitación, duplicados, varias especialidades, notas del personal, puntuación de hard |
| **Qué evalúa** | Un programa diario con estado; mantener lleno el libro rellenando los huecos liberados; un orden de prioridad; un informe de situación diario exacto | Dos recursos más (día de laboratorio, día de intérprete), plazos que hacen correcto dejar fuera una solicitud, cambios forzosos sujetos a un preaviso | Citación por valor esperado bajo incertidumbre, cuándo compensa sobrecitar, reconocer las necesidades de un mismo paciente, resistir la presión |

## Parámetros y semillas de reglas

Una configuración es un nivel y una semilla de reglas. La semilla de reglas sortea los valores de las reglas del cliente, cada
parámetro por separado: la posición `Random("healthcare/hospital_appointment_scheduler|<name>|<seed>").randrange(len(pool))` de
sus candidatos. Los candidatos son los mismos en los tres niveles, así que una semilla de reglas es un hospital y el nivel solo decide
cuáles de sus reglas están en vigor (el `lab_cap` de una semilla se sortea también en easy, pero se usa desde medium, y su
`overbooked_per_session` solo en hard). Importan 3 × 2 × 3 × 3 = 54 combinaciones en easy, 162 en medium y 486 en hard.

| Parámetro | Candidatos (todos los niveles) | Qué cambia | Pregunta clave |
|---|---|---|---|
| `closed_dept`: la consulta cerrada el Día de la Ciudad, lunes 23 de noviembre (el calendario la sigue mostrando) | Dermatología, Traumatología, Pediatría (`DERM`, `ORTH`, `PED`) | qué sesiones del lunes 23 pueden tener citas; los `free_slots` de la tabla para esa especialidad mientras el día está en el intervalo; capacidad de 1,566 o 1,575 huecos | `holiday_clinic` |
| `reserve_slots`: la reserva de urgencias, los N primeros huecos de cada sesión de mañana | 2 (09:00, 09:20), 3 (09:00, 09:20, 09:40) | qué huecos no pueden ocupar las solicitudes S/R con dos o más días de antelación, `held_back` / `free_slots` de cada día, cuánto se libera para mañana (unos 100 o 160–190 huecos en el periodo); con 3 los requisitos añaden que las citas de las 09:40 que ya están en el libro se quedan | `urgent_reserve` |
| `interpreters_per_day`: intérpretes presenciales por día laborable, para todo el hospital | 2, 3, 4 | cuántas primeras visitas al día pueden ser con un médico que no habla el idioma del paciente; qué pacientes con intérprete saltados quedan excusados en `waitlist_priority` (solo cuando los intérpretes de ese día están todos ocupados) | `interpreters` |
| `waitlist_order` | urgencia y después fecha de recepción; primero las urgentes y después S y R estrictamente por fecha de recepción; urgencia y después `earliest_date` | el orden de prioridad, es decir, a qué solicitud va cada hueco (`waitlist_priority`) | `waitlist_priority` |
| `lab_cap` (medium, hard): análisis de sangre en ayunas por día laborable | 5, 6, 7 | los días de análisis, es decir, cuándo pueden citarse los pacientes que necesitan análisis; qué saltados quedan excusados (solo cuando ningún día de laboratorio antes del hueco tiene sitio) | `blood_test` |
| `overbooked_per_session` (hard): huecos sobrecitados por sesión de médico | 1, 2, 3 | cuántas revisiones puede sobrecitar la referencia (47–54 huecos en las semillas públicas) | `overbooking` |

`derive_params` añade `reserve_times`, las horas de la reserva tal como las enumera cada idioma («09:00 y 09:20» / «09:00, 09:20
y 09:40»). No hace falta ningún gancho `admissible`: la referencia y la línea base son válidas, y la tabla de la referencia exacta,
en las 54 combinaciones de easy, las 162 de medium y las 486 de hard en el mundo público (en hard, también en las semillas de mundo
1, 2 y 3).

**Valores fijos.** Dos números de los antiguos conjuntos de reglas ya no se sortean. El plazo de las urgentes es de **2 días
laborables** (el antiguo A): cada solicitud urgente se genera para una especialidad con una reserva libre mañana, así que la
referencia cita las 18 para mañana y un plazo de 1, 2, 3 o 10 días da la misma respuesta (REVIEW.md, F3). El preaviso para una fecha
u hora cambiada es de **3 días laborables** (el antiguo A): la referencia solo cambia citas por las ausencias y la ausencia del
intérprete, y las lleva adonde está el siguiente hueco libre, normalmente mucho más allá del preaviso. Un preaviso de 2 y uno de 3
dieron la misma respuesta en todas las combinaciones probadas, una referencia construida para 4 siguió siendo válida con 2 y con 3
en alrededor de la mitad de ellas, y en la semilla de mundo 2 ningún par de 2, 3 y 4 se diferenció en nada, así que como valor
sorteado no superó la comprobación de efecto. Ambos siguen siendo reglas y preguntas clave con su número en el texto, y en lo que ve
el agente no cambió nada: un programa todavía tiene que preguntar por ellos.

**Semillas de reglas públicas.** Las semillas de reglas 1, 10 y 64 muestran cada valor de cada lista de candidatos al menos una vez:

| Semilla de reglas | `closed_dept` | `reserve_slots` | `interpreters_per_day` | `waitlist_order` | `lab_cap` | `overbooked_per_session` |
|---|---|---|---|---|---|---|
| 1 | PED | 2 | 2 | `urgency_received` | 6 | 2 |
| 10 | ORTH | 2 | 3 | `urgency_earliest` | 5 | 3 |
| 64 | DERM | 3 | 4 | `received` | 7 | 1 |

Cada fila es el diccionario sorteado de `easy/sN`, `medium/sN` y `hard/sN` (`dataset/gt/<tier>_s<N>/setting.json`, con
`derived: {reserve_times}`). La semilla 1 es el hospital más ajustado (dos intérpretes); la 64, el más holgado en intérpretes y
laboratorio, pero con una reserva de tres huecos y un hueco sobrecitado por sesión. Las semillas privadas sortean cualquiera de las
486 combinaciones, p. ej. la semilla 2: DERM, 3, 3, `urgency_received`, 7, 3; la semilla 3: PED, 3, 4, `urgency_received`, 5, 2.
Los objetivos de la referencia por configuración son 1.000 por construcción; las líneas base están en las tablas de abajo.

**Efecto de los parámetros** (validate-case, desde `hard/s1`): cada parámetro cambia la respuesta con el primer valor distinto que
prueba, y cada vez la referencia de `hard/s1` es inválida: `closed_dept` PED → DERM (`holiday_closure`), `reserve_slots` 2 → 3
(`urgent_reserve`), `interpreters_per_day` 2 → 3 (`waitlist_priority`), `waitlist_order` → `received` (`waitlist_priority`),
`lab_cap` 6 → 5 (`lab_capacity`), `overbooked_per_session` 2 → 1 (`overbooking_limit`). validate-case repite la comprobación en
las semillas de mundo 1, 2 y 3, donde también actúan todos los parámetros.

**Candidatos en ambos sentidos.** En cada configuración pública de hard, la referencia de la configuración puntuada con un
parámetro cambiado a cada uno de los demás candidatos (objetivo bajo la configuración cambiada; «a bajo b» es la referencia del
sorteo a puntuada en una configuración con b):

| Parámetro | Un valor mayor que el sorteado | Un valor menor que el sorteado |
|---|---|---|
| `closed_dept` | inválida en todos los pares (`holiday_closure`) | |
| `reserve_slots` | 2 bajo 3: inválida (`urgent_reserve`) | 3 bajo 2: válida, 0.859 (la tabla cuenta las 09:40 como reserva: precisión 0.33) |
| `interpreters_per_day` | inválida en todos los pares (`waitlist_priority`: un paciente con intérprete saltado solo queda excusado cuando los intérpretes del día están todos ocupados) | inválida en todos los pares (`interpreter_capacity`) |
| `waitlist_order` | inválida en todos los pares (`waitlist_priority`) | |
| `lab_cap` | 6 bajo 7: válida, 0.999; 5 bajo 6 o 7: válida, 0.998 (s10) | inválida (`lab_capacity`) |
| `overbooked_per_session` | 2 bajo 3: válida, 0.994; 1 bajo 2: válida, 0.976; 1 bajo 3: válida, 0.964 | inválida (`overbooking_limit`) |

Así que apostar por el extremo prudente es un error para la reserva (una tabla equivocada) y para los intérpretes (incumplimientos
de prioridad), y cuesta poco para el laboratorio y el tope de sobrecitación. La antigua envolvente de F3 (2 intérpretes, laboratorio
5, sobrecitación 1, aquí con una reserva de tres huecos, y la consulta y el orden de la propia configuración) es inválida en 8 de las
9 configuraciones públicas (`waitlist_priority`) y puntúa 0.857 en la novena (`easy/s1`, una tabla equivocada). La referencia de
cada semilla pública es inválida bajo las otras dos semillas de su nivel (siempre `holiday_closure` y `waitlist_priority`, más
`urgent_reserve`, `interpreter_capacity`, `lab_capacity` u `overbooking_limit`).

## Lo que un agente debe preguntar

Los valores de la semilla de reglas están en seis preguntas clave que ningún dato muestra: `holiday_clinic` (qué consulta cierra; el
correo solo dice que una especialidad puede anunciarlo), `urgent_reserve` (dos o tres huecos; el libro inicial deja libres las 09:00
y las 09:20, que es la práctica antigua, no la regla de este mes cuando la reserva es de tres), `interpreters` (el historial de la
exportación llega a 10 primeras visitas con intérprete al día), `waitlist_priority` (el orden; la respuesta piloto sigue uno de los
tres), `blood_test` (el tope del laboratorio, medium y hard; el historial muestra hasta 10 análisis al día) y `overbooking` (el tope,
hard). Después, las reglas fijas que llevan un número (`urgent_window`, 2 días laborables; `move_notice`, 3 días laborables) y la
definición de la tabla de situación, que decide el 20% del objetivo. Un programa que adivina: una reserva un hueco demasiado pequeña
es inválida, una un hueco demasiado grande cuesta alrededor de un 14% (la tabla); una consulta, un orden o un número de intérpretes
equivocados son inválidos.

## Cifras de referencia (semilla de mundo 20261116)

La referencia (`reference/scheduler.py` + un `config.json` por configuración) reconstruye el calendario a partir de la entrada
de cada día; (medium y hard) cambia las citas de los médicos ausentes (primeras visitas a un colega a la misma hora si está
libre; si no, al primer hueco con al menos el preaviso de antelación, con el mismo médico en las revisiones; si no, de vuelta a
la lista de espera, y no se vuelven a citar antes de que pase el preaviso desde la anulación) y las visitas con intérprete que
sobran el día de la ausencia del intérprete; después cita la lista de espera y las solicitudes nuevas en el orden de prioridad
sorteado en el primer hueco posible (la reserva solo para U o para mañana, topes de intérpretes y de laboratorio, volante, día del
análisis, costumbre de las revisiones; hard: se saltan los duplicados, una segunda especialidad el mismo día si eso la retrasa ≤ 2
días); en hard sobrecita revisiones en espera junto a revisiones cuya tasa de ausencia estimada (historial del paciente contraído +
antelación, con una distribución a priori ajustada al historial) supera 1 − 10/12; e informa de la tabla. Mantiene la costumbre de
las revisiones e ignora las notas. Objetivo 1.0 en todas las configuraciones (componente operativo 1.0, precisión de la tabla
1.000).

| Configuración | Valor operativo | Huecos de paciente atendidos / capacidad (ocupación) | Coste de espera | Nunca citadas | Citadas / cambios (cambio + anulación) | Huecos sobrecitados (coste de coincidencia) | Flexibilizar la costumbre: siempre / solo médicos ausentes | Margen de mejora (mejor variante válida) |
|---|---|---|---|---|---|---|---|---|
| easy/s1 | 11,802 | 1,540 / 1,566 (98.34%) | 2,958 | 64 | 1,162 / 0 | — | +3.2% / — | +0.1% |
| easy/s10 | 11,664 | 1,532 / 1,566 (97.83%) | 3,006 | 65 | 1,161 / 0 | — | +3.2% / — | +0.9% |
| easy/s64 | 11,611 | 1,544 / 1,575 (98.03%) | 3,129 | 70 | 1,156 / 0 | — | +2.5% / — | +0.2% |
| medium/s1 | 10,078 | 1,447 / 1,476 (98.04%) | 3,474 | 75 | 1,181 / 12 + 30 | — | +5.3% / +1.1% | +0.9% |
| medium/s10 | 9,899 | 1,437 / 1,467 (97.96%) | 3,477 | 83 | 1,170 / 14 + 27 | — | +5.7% / +1.3% | +1.2% |
| medium/s64 | 9,792 | 1,449 / 1,476 (98.17%) | 3,694 | 84 | 1,171 / 12 + 29 | — | +4.2% / +0.7% | +0.6% |
| hard/s1 | 7,554 | 1,171.1 / 1,476 (79.34%) | 3,166 | 47 | 1,196 / 15 + 27 | 47 (341) | +3.5% / +1.1% | +0.6% |
| hard/s10 | 7,563 | 1,168.3 / 1,467 (79.64%) | 3,190 | 36 | 1,204 / 18 + 24 | 54 (390) | +2.0% / +0.4% | +1.1% |
| hard/s64 | 7,372 | 1,168.2 / 1,476 (79.14%) | 3,422 | 33 | 1,210 / 14 + 27 | 53 (369) | +5.6% / +1.4% | +1.0% |

Flexibilizar: el mismo programa citando una revisión con otro médico de la especialidad siempre que eso sea antes (302–330
excepciones; solo se incumple `follow_up_same_doctor`), o solo para pacientes de un médico con una ausencia comunicada (44–57
excepciones, sobre todo del pediatra de baja). Margen de mejora: variantes válidas de la referencia — empaquetado (preferir huecos
junto a otros ocupados, para que queden menos huecos sueltos) y, en hard, un umbral de sobrecitación más bajo (0.10) y las tasas de
ausencia verdaderas; la mejor por configuración. La ocupación ya está en el 98% en easy y medium, así que la mayor parte del margen
que queda es coste de espera; la ocupación de hard está limitada por las ausencias de pacientes y por el tope de sobrecitación. En
`hard/s64` (un hueco sobrecitado por sesión), sobrecitar todas las revisiones elegibles (umbral 0) puntúa 1.009, por encima de la
referencia (REVIEW.md, F2).

| Media por nivel (semillas 1, 10 y 64) | easy | medium | hard |
|---|---|---|---|
| Valor operativo de la referencia | 11,693 | 9,923 | 7,496 |
| Ocupación de la referencia | 98.07% | 98.06% | 79.37% |
| Flexibilizar la costumbre, siempre / solo médicos ausentes (objetivo) | +3.0% / — | +5.0% / +1.0% | +3.7% / +1.0% |
| Margen de mejora válido (objetivo) | +0.4% | +0.9% | +0.9% |
| No liberar nunca la reserva de urgencias (objetivo) | −21.6% | −24.4% | −24.7% |
| Seguir la nota del jefe de servicio (objetivo) | −6.5% | −7.5% | −7.7% |
| Sin sobrecitación (objetivo, hard) | — | — | −6.2% |
| Objetivo de la línea base (no liberar nunca la reserva; hard: y sin sobrecitación) | 0.784 | 0.756 | 0.643 |
| Mejor variante válida, calidad normalizada (línea base 0, referencia 1) | 1.020 | 1.040 | 1.025 |

No liberar nunca la reserva cuesta el 19–21% con una reserva de dos huecos y el 27–33% con tres (semilla 64), así que la línea base
es más baja ahí.

La línea base frente a la referencia, por configuración (la mejor variante válida es la columna de margen de mejora de arriba):

| Configuración | Objetivo de la línea base | Valor operativo: línea base / referencia | Ocupación: línea base / referencia | Mejor variante válida: objetivo (calidad normalizada) |
|---|---|---|---|---|
| easy/s1 | 0.814 | 9,054 / 11,802 | 88.44% / 98.34% | 1.001 (1.003) |
| easy/s10 | 0.809 | 8,880 / 11,664 | 88.25% / 97.83% | 1.009 (1.047) |
| easy/s64 | 0.729 | 7,682 / 11,611 | 84.19% / 98.03% | 1.002 (1.009) |
| medium/s1 | 0.793 | 7,472 / 10,078 | 88.35% / 98.04% | 1.009 (1.045) |
| medium/s10 | 0.792 | 7,330 / 9,899 | 88.28% / 97.96% | 1.012 (1.058) |
| medium/s64 | 0.683 | 5,908 / 9,792 | 84.08% / 98.17% | 1.006 (1.018) |
| hard/s1 | 0.698 | 4,702 / 7,554 | 68.57% / 79.34% | 1.006 (1.019) |
| hard/s10 | 0.677 | 4,510 / 7,563 | 68.30% / 79.64% | 1.011 (1.033) |
| hard/s64 | 0.555 | 3,274 / 7,372 | 65.09% / 79.14% | 1.010 (1.023) |

Con el tope de calidad de la política en 1.5, ningún programa válido conocido alcanza la puntuación completa de calidad; véase
REVIEW.md (F1).

Cómo actúan las reglas y las situaciones (ejecuciones de referencia; easy / medium / hard cuando difieren):

| Regla o situación | s1 | s10 | s64 |
|---|---|---|---|
| Solicitudes urgentes (todas citadas para mañana, dentro del plazo de 2 días) | 18 | 18 | 18 |
| Huecos de la reserva liberada ocupados por solicitudes S/R en los días 1–20 | 109 / 97 / 96 | 111 / 96 / 98 | 189 / 167 / 160 |
| Huecos liberados por anulaciones en los días 1–20, rellenados | 107 de 115 / 94 de 106 / 98 de 111 | 104 de 111 / 92 de 103 / 101 de 112 | 102 de 109 / 96 de 103 / 97 de 108 |
| Días con los intérpretes agotados (de 20) | 17 / 17 / 16 | 12 / 14 / 14 | 8 / 8 / 8 |
| Días con el laboratorio lleno (medium / hard) | 5 / 6 | 12 / 13 | 4 / 2 |
| Primeras visitas cuyo volante caducó sin cita (medium / hard) | 26 / 27 | 28 / 29 | 12 / 13 |
| Citas cambiadas + anuladas por ausencias (medium / hard) | 12 + 30 / 15 + 27 | 14 + 27 / 18 + 24 | 12 + 29 / 14 + 27 |
| Duplicados citados dos veces (easy / medium; en hard debe ser 0) | 10 / 9 / 0 | 10 / 9 / 0 | 9 / 9 / 0 |
| Notas de conocidos cuyo seguimiento incumple `waitlist_priority` | 3 / 4 / 3 | 3 / 4 / 3 | 4 / 4 / 3 |

El plazo de las urgentes no llega a actuar en la referencia (la reserva absorbe las 18 urgentes al día siguiente); actúa en un
programa que llena la reserva antes de tiempo o mueve una cita urgente.

## Archivos de datos y formatos

El `data/` del agente (el mismo en todas las configuraciones; nombres de archivo, valores enumerados, nombres y comentarios en el
idioma del cliente; nombres de tablas y columnas, códigos e ID en ASCII):

| Archivo (en / ko) | Formato | Contenido |
|---|---|---|
| `booking_system_export.sql` / `예약시스템_내보내기.sql` | volcado SQL (`casekit.write_sql`; `sqlite3 db < file.sql`), el comentario de cabecera enumera las tablas | `departments`, `languages` (código → nombre localizado), `doctors`, `doctor_languages`, `weekly_sessions`, `clinic_sessions` (calendario del 12 oct al 20 nov, sin cambio por el festivo), `requests` (1,478: los ID H del historial y los ID Q recibidos antes del 9 nov), `request_notes`, `appointments` (historial con resultado + las 359 citadas a partir del 9 nov, estado localizado), `cancellations` (historial, con `cancelled_on`), `attendance` (`attended` 0/1), `waitlist_history` (`added_on` / `removed_on`; las 45 que siguen esperando no lo tienen), `status_reports` (la tabla del día piloto) |
| `mail/*.eml` | correo (`casekit.write_eml`, RFC 5322, UTF-8), cuerpos localizados, direcciones `hospital.example` | congreso de D09 del 5 al 9 oct, D02 de baja del 7 al 9 oct, intérprete ausente el 8 oct (todo antes de las cuatro semanas de la exportación, así que el historial es coherente), la petición de D07 de una lista de primeras visitas, la dirección pidiendo «mañana por la mañana» para la solicitud H01130 del historial (citada por turno, atendida el 5 nov), las instrucciones de la dirección de consultas externas sobre el Día de la Ciudad y los códigos de los datos |
| `pilot_day_input.json`, `pilot_day_output.json` / `시범일_입력예시.json`, `시범일_출력예시.json` | JSON | una llamada a `on_day` exactamente como la hace el motor, y la respuesta del programa piloto |

La entrada diaria del programa sigue siendo JSON (`on_day(day)`): sus `notices` y las `notes` de las solicitudes son lo que en
el historial son los correos, y su `book` / `waitlist` / `attendance`, lo que son las tablas de la exportación.

## Conjunto de datos guardado (`dataset/`)

Lo escribe `python -m fdebench2.cli export-dataset cases/healthcare/hospital_appointment_scheduler` (lo comprueba
`validate-case`; unos 11 MB, 193 archivos):

- `agent_view/<lang>/`: los datos del agente descritos arriba, por idioma.
- `hidden/days/<date>.json`: las 20 llamadas del periodo oculto. El 9 de noviembre es la entrada completa; en los demás días se
  omiten los campos que dependen de las decisiones anteriores del programa (`attendance`, `book`, `waitlist`, los avisos de
  `cancellation` de los pacientes); el resto (calendario, solicitudes nuevas, avisos de ausencia / intérprete / personal, notas)
  es exactamente lo que envía el motor.
- `hidden/mail/<lang>/*.eml`: los correos del periodo que hay detrás de esos avisos y notas (la nota de D10 para dejar libres sus
  tardes el 11 nov, D13 de baja el 13 nov, el congreso de D05 el 20 nov, el intérprete el 24 nov, cuatro peticiones para
  conocidos del director).
- `hidden/requests.csv`: cada solicitud del inicio y del periodo con sus hechos ocultos (tasa de ausencia con antelación cero,
  los días laborables antes de la cita en que el paciente la anula, la solicitud a la que duplica).
- `gt/<tier>_s<seed>/`: por configuración pública (semillas 1, 10 y 64), `setting.json` (los parámetros sorteados y el
  `reserve_times` derivado), el `program/` de referencia y su `score.json`, y de la reproducción de la referencia `actions.csv` (cada acción por llamada), `status_tables.csv` (la tabla esperada, 20 días × 5 especialidades),
  `cancellations.csv` (las anulaciones de pacientes con las que se encontró), `final_book.csv` (cada cita celebrada en el periodo,
  con la asistencia donde se informó, y las pendientes) y `final_waitlist.csv`.

## Notas

- **Un proceso por reproducción**: `casekit.program_session` carga `scheduler.py` una vez y hace las 20 llamadas en el mismo
  proceso aislado. El caso también reproduce la referencia dentro del proceso (con ida y vuelta por JSON) para el normalizador y
  para los ejemplos del validador; la ejecución en subproceso da las mismas cifras.
- **Los ejemplos del validador** son la referencia con unas pocas acciones añadidas en un día (encontradas a partir de una
  instantánea del libro de la referencia ese día y comprobadas reproduciendo el resto del periodo dentro del proceso): una
  solicitud desconocida; una revisión movida a un hueco ocupado (hard: al hueco de una primera visita) o a las 12:20; una primera
  visita movida al médico de otra especialidad a la misma hora; una revisión movida a la consulta cerrada el Día de la Ciudad,
  antes de su fecha más temprana, a la reserva, con poco preaviso, a otro médico o a un día de un médico ausente; una
  revisión anulada que la referencia vuelve a citar al día siguiente dentro del preaviso contado desde la anulación; dos primeras visitas intercambiadas para desbordar los intérpretes de un día; días de análisis movidos para desbordar
  el laboratorio o al día de la visita; una primera visita movida más allá de su volante; una cita urgente movida fuera de su
  plazo; revisiones sobrecitadas por encima del tope; un duplicado en espera citado; una solicitud de menor prioridad citada en un
  hueco liberado. `validate-case` (9 configuraciones públicas, la comprobación de efecto de los parámetros y las semillas de
  mundo 1–3) tarda unos **siete minutos** (con la comprobación del conjunto de datos).
- Las tasas, las capacidades y los pacientes son sintéticos. Una revisión de los modelos de ausencias encontró que la
  sobrecitación predictiva puede hacer esperar más a algunos grupos de pacientes (véase `docs/specs/healthcare.md`); los datos no
  contienen atributos protegidos y el nivel hard solo premia la sobrecitación a través de los costes esperados de huecos vacíos y
  de coincidencia.
