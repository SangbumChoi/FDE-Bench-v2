# Programa diario de citas de consultas externas

## Contexto

A partir del lunes 9 de noviembre queremos que nuestra oficina de citas de consultas externas trabaje con un programa: cada día laborable recibe las solicitudes de cita nuevas, las anulaciones y los avisos del día junto con las citas que ya tenemos, cita a los pacientes en los huecos libres de los médicos y nos dice cómo está cada especialidad. Sobre todo queremos dejar de perder tiempo de médico en huecos vacíos. ¿Nos lo puede preparar? Le adjuntamos una exportación de nuestro sistema de citas (médicos, calendario de consultas, las solicitudes y citas de las últimas cuatro semanas con lo que pasó en cada una, anulaciones, asistencia y lista de espera), los correos que recibió nuestra oficina de citas (ausencias, notas, instrucciones de la dirección de consultas externas) y un día piloto (lo que recibe el programa y lo que contestó nuestro piloto).

Evaluaremos el programa ejecutándolo en los **20 días laborables del lunes 9 de noviembre al viernes 4 de diciembre de 2026**. Esos días no están en los datos: todas las solicitudes de ese periodo son nuevas para usted.

## Entregable

Una carpeta `program/` con un archivo `scheduler.py` que defina **`on_day(day)`**. Todo lo demás que necesite va en la misma carpeta. Use solo la biblioteca estándar de Python; el motor no tiene red y el programa no puede leer los archivos de datos durante la ejecución, así que copie en la carpeta lo que aprenda de ellos.

- El motor carga el programa **una sola vez** y llama a `on_day` una vez por día laborable, en orden y en el mismo proceso, de modo que las variables del módulo se conservan de un día para otro. Cada llamada puede tardar hasta 10 segundos. Durante la ejecución no se puede preguntar nada a nadie: nuestras reglas tienen que ir dentro del programa.
- La llamada llega **al final de la jornada**: las consultas del día ya han terminado y las citas se dan a partir de mañana.
- `day` (véase `dia_piloto_entrada.json`, una llamada tal como la hace el motor):
  - `date`, `day_index` (de 0 a 19), `days_in_period` (20), `period_end`;
  - `booking_window`: `first` (el siguiente día laborable) y `last` (10 días laborables después). Solo se pueden dar citas dentro de este intervalo;
  - `doctors`: `doctor_id`, `department` (código: IM, CARD, DERM, ORTH, PED) y `languages` (códigos, como en la tabla `languages` de la exportación);
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

- `exportacion_sistema_citas.sql`: un volcado SQL en texto plano de nuestro sistema de citas al cierre del viernes 6 de noviembre (se carga con `sqlite3 booking.db < exportacion_sistema_citas.sql`; el comentario del principio enumera las tablas). Contiene los 14 médicos de cinco especialidades con los idiomas que hablan y sus consultas semanales, el calendario de consultas del 12 de octubre al 20 de noviembre, las solicitudes, las citas del 12 de octubre al 6 de noviembre con su resultado (acudió, no acudió, anulada por el paciente) y las ya dadas a partir del 9 de noviembre, las anulaciones, la asistencia, el historial de la lista de espera y la tabla de estado del día piloto. Los días laborables son de lunes a viernes; el Día de la Ciudad (lunes 23 de noviembre) es laborable para el hospital.
- `mail/`: correos que recibió la oficina de citas (`.eml`): ausencias de médicos, la ausencia de una intérprete, notas de un jefe de servicio y de la dirección, e instrucciones de la dirección de consultas externas. Mensajes así llegan al programa como `notices` y como `notes` de las solicitudes (véase el fichero piloto).
- La exportación y los correos son historial para aprender; el programa recibe en `day` todo lo que necesita.
- Duración: una **primera visita** ocupa **dos huecos consecutivos** del mismo médico en la misma sesión (se cita por la hora del primero); una **revisión** ocupa un hueco.
- Una solicitud se cita con un médico de su `department` y nunca antes de su `earliest_date`. Su **primer día posible** es su `earliest_date` o el día laborable siguiente a su recepción, el que sea más tarde.
- `triage_note` es solo informativa.

## Nuestras reglas de citación

**Solicitudes urgentes**

- Toda solicitud **urgente (U)** debe citarse **el mismo día en que llega**, en un día dentro de los **2 días laborables** siguientes a su primer día posible (ese día o uno de los dos siguientes), y debe seguir dentro de ese plazo si alguna vez se cambia.
- **Reserva de urgencias:** los **dos primeros huecos de cada sesión de mañana (09:00 y 09:20)** se guardan para las urgentes. Con dos o más días laborables de antelación solo pueden usarlos solicitudes U. En la llamada del día laborable anterior (es decir, para las consultas de mañana) se liberan y cualquiera puede citarse en ellos.

**Quién ve a quién**

- Una revisión se cita con el `previous_doctor` del paciente; los pacientes esperan ver al médico que los conoce. Es una costumbre nuestra, no una regla del contrato con la autoridad sanitaria: la jefa de la oficina de consultas externas puede autorizar una excepción.
- Intérpretes: si el médico no habla el `preferred_language` del paciente, la visita necesita intérprete. Tenemos **3 intérpretes presenciales al día** para todo el hospital y una **primera visita** debe tener uno, así que como mucho 3 primeras visitas al día pueden ser con un médico que no hable el idioma del paciente. Las revisiones usan interpretación telefónica, sin límite.
- Festivo: Día de la Ciudad, **lunes 23 de noviembre**. La **consulta de Traumatología cierra ese día**; las demás funcionan. El calendario no se actualizó: `sessions` sigue mostrando sesiones de Traumatología ese día. Ninguna cita de Traumatología el 23 de noviembre.

**Cambiar la cita de un paciente**

- Cuando cambiamos la **fecha o la hora** de la cita de un paciente (un cambio, o anularla y volver a citarlo ese mismo día o más adelante), la nueva cita debe ser al menos **3 días laborables después del día del cambio** (si se anuló, del día de la anulación): el paciente necesita ese preaviso. Mantener la misma fecha y hora con otro médico no necesita preaviso.
- Cada cambio que hacemos en la cita de un paciente (cambio o anulación) es una molestia para él y resta en la puntuación; no mueva citas sin motivo.

**La lista de espera**

- Las solicitudes en espera se citan en nuestro **orden de prioridad**: primero por urgencia (U, luego S, luego R) y, dentro de la misma urgencia, por earliest_date (primero quien puede venir antes).
- No se puede citar una solicitud mientras otra de **mayor prioridad** de la misma especialidad, el mismo tipo de visita y (en revisiones) el mismo médico anterior sigue esperando al final del día y podría haber ocupado ese hueco. No se lo tendremos en cuenta cuando la que espera no podía ocuparlo: su fecha más temprana es posterior a ese hueco, es una primera visita que con ese médico necesitaría intérprete y la citada no, y ese día ya están ocupados todos los intérpretes presenciales, o usted anuló su cita y el hueco está dentro del plazo de preaviso contado desde el día de la anulación.
- En la práctica: rellene los huecos libres y los que se liberan con la lista de espera, por orden. Las anulaciones y la reserva de urgencias liberada para mañana son donde más tiempo de médico perdemos hoy.

**Alcance de esta ronda**

- Avisos `doctor_absence` e `interpreter_absence`: fuera del alcance esta ronda (los cubren un médico sustituto y una agencia de intérpretes); cite como si no hubiera pasado nada.
- Volantes y análisis: esta ronda los volantes los revisa admisión y el laboratorio cita él mismo los análisis en ayunas con los pacientes, así que no tenga en cuenta `referral_valid_until` ni `pre_visit_test` y deje `test_date` en null.
- Ausencias de pacientes: esta ronda no contamos con que falten; todo paciente citado cuenta como que viene. `attendance` es informativo.
- Una segunda solicitud del mismo paciente: por la solicitud no sabemos si es la misma dolencia, así que esta ronda cada solicitud lleva su propia cita; la consulta comprueba con el paciente si es un duplicado.

## La tabla de situación

Cada día, después de sus acciones, devuelva para cada código de especialidad (`IM`, `CARD`, `DERM`, `ORTH`, `PED`) tres números enteros sobre el **intervalo de citación** (los 10 días laborables siguientes):

- `free_slots`: huecos del calendario de los médicos de la especialidad sin ninguna cita y en los que cualquiera puede citarse: sin contar los reservados (abajo) ni los de una consulta cerrada (el festivo).
- `held_back`: huecos de la reserva de urgencias (09:00 y 09:20 de una sesión de mañana) a dos o más días laborables vista y sin ninguna cita (con las mismas exclusiones).
- `waitlist`: las solicitudes de la especialidad que siguen esperando después de sus acciones (recibidas hasta hoy, sin cita, no anuladas).

Una entrada solo está bien si es exacta. Un día puntúa la proporción de sus 15 entradas que están bien; la precisión de la tabla es la media de los 20 días.

## Cómo se evalúa el programa

**Restricciones obligatorias** (si se incumple cualquiera, el programa no cuenta):

- Cada llamada devuelve acciones bien formadas sobre solicitudes que existen (citar solo una solicitud en espera, cambiar o anular solo una cita pendiente), con fecha dentro del intervalo de citación; una llamada que falla o se pasa de tiempo también incumple.
- Ningún hueco tiene dos citas.
- Solo huecos del calendario (dos consecutivos de una sesión para una primera visita), la especialidad correcta, nunca antes de la fecha más temprana, ninguna cita de Traumatología el 23 de noviembre, como mucho 3 primeras visitas con intérprete al día.
- Urgentes citadas el día en que llegan dentro de 2 días laborables; la reserva de urgencias respetada a dos o más días vista; al menos 3 días laborables de preaviso para una fecha u hora cambiada; el orden de prioridad de la lista de espera.
- Revisiones con su médico anterior (costumbre nuestra; cabe una excepción).

**Calidad** = 0,8 × (valor operativo / el valor operativo de nuestro propio programa de referencia en los mismos días) + 0,2 × la precisión de la tabla de situación. Más es mejor. El **valor operativo**:

- **+10 por cada hueco de paciente atendido** en los días de consulta del 10 de noviembre al 7 de diciembre (una primera visita atendida cuenta sus dos huecos, una revisión uno). Es lo que más nos importa: cada hueco vacío es tiempo de médico perdido.
- − 0,4 × peso de urgencia (U 3, S 2, R 1) por cada día laborable que espera una solicitud, desde su primer día posible (o el 10 de noviembre, si es anterior) hasta su cita, o hasta el 8 de diciembre si nunca la consigue;
- − 10 por cada solicitud que nunca consigue cita (no cuentan las que no pueden venir antes del 18 de diciembre);
- − 4 por cada cambio que hacemos en la cita de un paciente (cambio o anulación).
