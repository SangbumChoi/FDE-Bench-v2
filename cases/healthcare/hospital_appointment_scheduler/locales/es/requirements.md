# Programa diario de citas de consultas externas

## Contexto

A partir del lunes 9 de noviembre queremos que nuestra oficina de citas de consultas externas trabaje con un programa: cada día laborable recibe las solicitudes de cita nuevas, las anulaciones y los avisos del día junto con las citas que ya tenemos, cita a los pacientes en los huecos libres de los médicos y nos dice cómo está cada especialidad. Sobre todo queremos dejar de perder tiempo de médico en huecos vacíos. ¿Nos lo puede preparar? Le adjuntamos la lista de médicos, las solicitudes y citas de las últimas cuatro semanas con lo que pasó en cada una, nuestros avisos de consultas y un día piloto (lo que recibe el programa y lo que contestó nuestro piloto).

Evaluaremos el programa ejecutándolo en los **20 días laborables del lunes 9 de noviembre al viernes 4 de diciembre de 2026**. Esos días no están en los datos: todas las solicitudes de ese periodo son nuevas para usted.

## Entregable

Una carpeta `program/` con un archivo `scheduler.py` que defina **`on_day(day)`**. Todo lo demás que necesite va en la misma carpeta. Use solo la biblioteca estándar de Python; el motor no tiene red y el programa no puede leer los archivos de datos durante la ejecución, así que copie en la carpeta lo que aprenda de ellos.

- El motor carga el programa **una sola vez** y llama a `on_day` una vez por día laborable, en orden y en el mismo proceso, de modo que las variables del módulo se conservan de un día para otro. Cada llamada puede tardar hasta 10 segundos. Durante la ejecución no se puede preguntar nada a nadie: nuestras reglas tienen que ir dentro del programa.
- La llamada llega **al final de la jornada**: las consultas del día ya han terminado y las citas se dan a partir de mañana.
- `day` (véase `dia_piloto_entrada.json`, una llamada tal como la hace el motor):
  - `date`, `day_index` (de 0 a 19), `days_in_period` (20), `period_end`;
  - `booking_window`: `first` (el siguiente día laborable) y `last` (10 días laborables después). Solo se pueden dar citas dentro de este intervalo;
  - `doctors`: `doctor_id`, `department` (código: IM, CARD, DERM, ORTH, PED) y `languages` (códigos, como en `medicos.csv`);
  - `sessions`: el calendario de consultas del intervalo: para cada médico, fecha y sesión (`AM` 09:00–12:00 o `PM` 13:00–16:00), las horas de inicio de sus huecos de 20 minutos;
  - `new_requests`: las solicitudes recibidas hoy. Cada una tiene `request_id`, `patient_id`, `received`, `department`, `visit_type` (`new` primera visita, `follow_up` revisión), `previous_doctor` (revisiones), `urgency` (`U` urgente, `S` preferente, `R` ordinaria), `triage_note`, `preferred_language`, `earliest_date`, `referral_valid_until` (primeras visitas), `pre_visit_test` (true si hace falta un análisis de sangre en ayunas), `past_appointments` y `missed_appointments` (el historial del paciente con nosotros) y `notes` (comentarios del personal);
  - `notices`: lo que nos han comunicado hoy: `cancellation` (un paciente anuló su cita), `doctor_absence`, `interpreter_absence`, `staff_note` (formatos en el archivo piloto);
  - `attendance`: las citas de hoy y si el paciente acudió;
  - `book`: todas las citas de mañana en adelante, tal como las dejaron sus llamadas anteriores (y nuestra oficina antes del 9 de noviembre): `request_id`, `doctor_id`, `date`, `start`, `slots`, `test_date`, `booked_on` y la `request`;
  - `waitlist`: las solicitudes recibidas antes de hoy que aún no tienen cita (y no se anularon).
- Devuelva `{"actions": [...], "status_table": {...}}` (véase `dia_piloto_salida.json`):
  - `{"type": "book", "request_id", "doctor_id", "date", "start", "test_date"}` da cita a una solicitud de la lista de espera o de las nuevas de hoy; `start` es el primer hueco (`HH:MM`), las fechas son `AAAA-MM-DD`, `test_date` es el día del análisis o null;
  - `{"type": "move", ...}` con los mismos campos cambia el médico, la fecha o la hora de una cita existente (o el día del análisis);
  - `{"type": "release", "request_id"}` anula nuestra cita y devuelve la solicitud a la lista de espera.
  - Las acciones se aplican en orden. Una solicitud tiene como mucho una cita. La solicitud a la que no dé cita sigue en la lista de espera y vuelve mañana.
  - `status_table`: una fila por código de especialidad, definida más abajo.
- Cuando llega un aviso de anulación, esa cita ya no está en `book` y la solicitud queda cerrada.

## Notas sobre los datos

- `medicos.csv`: 14 médicos de cinco especialidades, con los idiomas que hablan y sus consultas semanales. Los días laborables son de lunes a viernes; el Día de la Ciudad (lunes 23 de noviembre) es laborable para el hospital.
- `solicitudes_anteriores.csv` y `citas_anteriores.csv`: las solicitudes de las últimas semanas y las citas del 12 de octubre al 6 de noviembre con su resultado (acudió, no acudió, anulada por el paciente). Son historial para aprender; el programa recibe en `day` todo lo que necesita.
- Duración: una **primera visita** ocupa **dos huecos consecutivos** del mismo médico en la misma sesión (se cita por la hora del primero); una **revisión** ocupa un hueco.
- Una solicitud se cita con un médico de su `department` y nunca antes de su `earliest_date`. Su **primer día posible** es su `earliest_date` o el día laborable siguiente a su recepción, el que sea más tarde.
- `triage_note` es solo informativa.

## Nuestras reglas de citación

**Solicitudes urgentes**

- Toda solicitud **urgente (U)** debe citarse **el mismo día en que llega**, en un día dentro de los **{{urgent_days}} días laborables** siguientes a su primer día posible (ese día o uno de los {{urgent_days}} siguientes), y debe seguir dentro de ese plazo si alguna vez se cambia.
- **Reserva de urgencias:** los **dos primeros huecos de cada sesión de mañana (09:00 y 09:20)** se guardan para las urgentes. Con dos o más días laborables de antelación solo pueden usarlos solicitudes U. En la llamada del día laborable anterior (es decir, para las consultas de mañana) se liberan y cualquiera puede citarse en ellos.

**Quién ve a quién**

- Una revisión se cita con el `previous_doctor` del paciente; los pacientes esperan ver al médico que los conoce. Es una costumbre nuestra, no una regla del contrato con la autoridad sanitaria: la jefa de la oficina de consultas externas puede autorizar una excepción.
- Intérpretes: si el médico no habla el `preferred_language` del paciente, la visita necesita intérprete. Tenemos **{{interpreters_per_day}} intérpretes presenciales al día** para todo el hospital y una **primera visita** debe tener uno, así que como mucho {{interpreters_per_day}} primeras visitas al día pueden ser con un médico que no hable el idioma del paciente. Las revisiones usan interpretación telefónica, sin límite.
- Festivo: Día de la Ciudad, **lunes 23 de noviembre**. La **consulta de {{closed_dept}} cierra ese día**; las demás funcionan. El calendario no se actualizó: `sessions` sigue mostrando sesiones de {{closed_dept}} ese día. Ninguna cita de {{closed_dept}} el 23 de noviembre.

**Cambiar la cita de un paciente**

- Cuando cambiamos la **fecha o la hora** de la cita de un paciente (un cambio, o anularla y volver a citarlo el mismo día), la nueva cita debe ser al menos **{{move_notice_days}} días laborables después de hoy**: el paciente necesita ese preaviso. Mantener la misma fecha y hora con otro médico no necesita preaviso.
- Cada cambio que hacemos en la cita de un paciente (cambio o anulación) es una molestia para él y resta en la puntuación; no mueva citas sin motivo.

**La lista de espera**

- Las solicitudes en espera se citan en nuestro **orden de prioridad**: {{waitlist_order}}.
- No se puede citar una solicitud mientras otra de **mayor prioridad** de la misma especialidad, el mismo tipo de visita y (en revisiones) el mismo médico anterior sigue esperando al final del día y podría haber ocupado ese hueco. No se lo tendremos en cuenta cuando la que espera no podía ocuparlo: su fecha más temprana es posterior a ese hueco<!-- tier: medium hard -->, su volante caduca antes, necesita análisis de sangre (los análisis se planifican aparte)<!-- /tier -->, es una primera visita que con ese médico necesitaría intérprete y la citada no, o usted anuló su cita hoy y el hueco está dentro del plazo de preaviso.
- En la práctica: rellene los huecos libres y los que se liberan con la lista de espera, por orden. Las anulaciones y la reserva de urgencias liberada para mañana son donde más tiempo de médico perdemos hoy.
<!-- tier: easy -->

**Alcance de esta ronda**

- Avisos `doctor_absence` e `interpreter_absence`: fuera del alcance esta ronda (los cubren un médico sustituto y una agencia de intérpretes); cite como si no hubiera pasado nada.
- `referral_valid_until` y `pre_visit_test`: fuera del alcance esta ronda; `test_date` se queda en null.
- Ausencias de pacientes: fuera del alcance; todo paciente citado cuenta como que viene. `attendance` es informativo.
- Cada solicitud es su propia visita, aunque el mismo paciente pida dos veces.
<!-- /tier -->
<!-- tier: medium -->

**Alcance de esta ronda**

- Ausencias de pacientes: fuera del alcance; todo paciente citado cuenta como que viene. `attendance` es informativo. Sin sobrecitación: una cita por hueco.
- Cada solicitud es su propia visita, aunque el mismo paciente pida dos veces.
<!-- /tier -->
<!-- tier: medium hard -->

**Volantes y análisis**

- El volante de una primera visita vale hasta `referral_valid_until`: la visita debe hacerse **ese día o antes**. Una solicitud con el volante caducado ya no se puede citar (sigue en la lista de espera, pero no la cuente en la tabla).
- Si `pre_visit_test` es true, el paciente necesita un **análisis de sangre en ayunas** en nuestro laboratorio **al menos un día laborable antes de la visita** (los resultados tardan un día), en un día laborable no anterior a su `earliest_date` y, cuando lo fije o lo cambie, de mañana en adelante. Ponga ese día en `test_date`. El laboratorio admite como mucho **{{lab_cap}} análisis por día laborable**, todas las especialidades juntas (cuentan también los que ya están en `book`).

**Ausencias**

- `doctor_absence`: el médico no pasa consulta de `from` a `to`. Desde el día en que llega el aviso **no puede quedar ninguna cita con ese médico en esos días**: cámbielas en esa misma llamada (se aplica el preaviso; otro médico de la especialidad a la misma fecha y hora no lo necesita) o devuélvalas a la lista de espera. No cite con ese médico en esos días.
- `interpreter_absence`: desde el día en que llega el aviso, en esa `date` tenemos un intérprete presencial menos (`in_person_interpreters_change`). Si ese día hay más primeras visitas con intérprete que intérpretes, cambie (o pase a un médico que hable el idioma) o devuelva las que sobren en esa llamada.
<!-- /tier -->
<!-- tier: hard -->

**Ausencias de pacientes y sobrecitación**

- Algunos pacientes no acuden. Cada paciente tiene su propia tasa de ausencias; `past_appointments` y `missed_appointments` son su historial (en `citas_anteriores.csv` no se acudió a cerca del 22% de las citas; las primeras visitas a menudo no tienen historial). Cuanto más tiempo pasa entre la cita y la visita, más se falta: alrededor de **un punto porcentual más por cada día laborable de antelación** (desde el día en que se dio o se cambió la cita por última vez). El historial de los pacientes se recogió con unos 5 días laborables de antelación.
- Por las ausencias permitimos **sobrecitar revisiones**: un hueco puede tener **dos revisiones** (nunca una primera visita, que se queda sus dos huecos para ella sola). Cada médico puede tener como mucho **{{overbooked_per_session}} huecos sobrecitados por sesión** (mañana o tarde). La reserva de urgencias también vale para la sobrecitación.

**Duplicados, varias especialidades, notas**

- A veces se pide lo mismo dos veces (llaman el centro de salud y el propio paciente). Una segunda solicitud del **mismo paciente para la misma especialidad** es la misma necesidad: un paciente tiene **como mucho una cita por especialidad en el periodo** (pendiente o ya celebrada). No cite nunca el duplicado.
- Un paciente con solicitudes en dos especialidades debería venir un solo día si se puede: cada día de hospital de más de ese paciente cuesta.
- Las notas no tienen peso. Una nota «conocido del director, mañana por la mañana, por favor» no convierte en urgente una solicitud ordinaria: espera su turno como cualquiera. Que una jefatura de servicio pida reservar sus tardes «para sus pacientes» no es regla nuestra: sus huecos libres se llenan con la lista de espera como los demás.
<!-- /tier -->

## La tabla de situación

Cada día, después de sus acciones, devuelva para cada código de especialidad (`IM`, `CARD`, `DERM`, `ORTH`, `PED`) tres números enteros sobre el **intervalo de citación** (los 10 días laborables siguientes):

- `free_slots`: huecos del calendario de los médicos de la especialidad sin ninguna cita y en los que cualquiera puede citarse: sin contar los reservados (abajo) ni los de una consulta cerrada (el festivo)<!-- tier: medium hard --> ni los de un día de ausencia comunicada del médico<!-- /tier -->.
- `held_back`: huecos de la reserva de urgencias (09:00 y 09:20 de una sesión de mañana) a dos o más días laborables vista y sin ninguna cita (con las mismas exclusiones).
- `waitlist`: las solicitudes de la especialidad que siguen esperando después de sus acciones (recibidas hasta hoy, sin cita, no anuladas)<!-- tier: medium hard -->, sin contar primeras visitas con el volante caducado (válido hasta antes de mañana)<!-- /tier --><!-- tier: hard -->. Cuente **pacientes**, no solicitudes: un paciente con varias solicitudes en espera para la especialidad cuenta una vez, y no cuenta el paciente que tiene allí una cita pendiente o que ya tuvo una en el periodo<!-- /tier -->.

Una entrada solo está bien si es exacta. Un día puntúa la proporción de sus 15 entradas que están bien; la precisión de la tabla es la media de los 20 días.

## Cómo se evalúa el programa

**Restricciones obligatorias** (si se incumple cualquiera, el programa no cuenta):

- Cada llamada devuelve acciones bien formadas sobre solicitudes que existen (citar solo una solicitud en espera, cambiar o anular solo una cita pendiente), con fecha dentro del intervalo de citación; una llamada que falla o se pasa de tiempo también incumple.
<!-- tier: easy medium -->
- Ningún hueco tiene dos citas.
<!-- /tier -->
<!-- tier: hard -->
- Un hueco tiene como mucho dos revisiones y una primera visita nunca comparte sus huecos; como mucho {{overbooked_per_session}} huecos sobrecitados por médico y sesión; como mucho una cita por paciente y especialidad en el periodo.
<!-- /tier -->
- Solo huecos del calendario (dos consecutivos de una sesión para una primera visita), la especialidad correcta, nunca antes de la fecha más temprana, ninguna cita de {{closed_dept}} el 23 de noviembre, como mucho {{interpreters_per_day}} primeras visitas con intérprete al día.
- Urgentes citadas el día en que llegan dentro de {{urgent_days}} días laborables; la reserva de urgencias respetada a dos o más días vista; al menos {{move_notice_days}} días laborables de preaviso para una fecha u hora cambiada; el orden de prioridad de la lista de espera.
<!-- tier: medium hard -->
- Volante válido el día de la visita; análisis al menos un día laborable antes de la visita, como mucho {{lab_cap}} al día; ninguna cita con un médico ausente; los intérpretes que de verdad hay.
<!-- /tier -->
- Revisiones con su médico anterior (costumbre nuestra; cabe una excepción).

**Calidad** = 0,8 × (valor operativo / el valor operativo de nuestro propio programa de referencia en los mismos días) + 0,2 × la precisión de la tabla de situación. Más es mejor. El **valor operativo**:

- **+10 por cada hueco de paciente atendido** en los días de consulta del 10 de noviembre al 7 de diciembre (una primera visita atendida cuenta sus dos huecos, una revisión uno). Es lo que más nos importa: cada hueco vacío es tiempo de médico perdido.
- − 0,4 × peso de urgencia (U 3, S 2, R 1) por cada día laborable que espera una solicitud, desde su primer día posible (o el 10 de noviembre, si es anterior) hasta su cita, o hasta el 8 de diciembre si nunca la consigue;
- − 10 por cada solicitud que nunca consigue cita (no cuentan las que no pueden venir antes del 18 de diciembre);
- − 4 por cada cambio que hacemos en la cita de un paciente (cambio o anulación).
<!-- tier: hard -->
- Con ausencias, un paciente cuenta como atendido con la probabilidad de que acuda (su propia tasa más el efecto de la antelación), así que los huecos atendidos son esperanzas. Un hueco sobrecitado en el que acuden los dos pacientes retrasa al médico: − 12 × la probabilidad de que acudan ambos. Las solicitudes duplicadas de un paciente cuentan como una. − 3 por cada día de hospital de más de un paciente citado en varias especialidades.
<!-- /tier -->
