# Asignación de citas de consultas externas

## Contexto

Tenemos acumuladas muchas solicitudes de cita de consultas externas. ¿Podría usted citarlas en las agendas de los médicos para las próximas dos semanas (del lunes 16 al viernes 27 de noviembre)? Nos gustaría que los pacientes no esperen más de lo necesario. Le adjuntamos la lista de médicos, los huecos libres, las solicitudes y nuestros avisos de consultas.
También le adjuntamos el historial de asistencia de los pacientes.

## Entregable

Un archivo CSV, `bookings.csv`, con la cabecera `request_id,doctor_id,date,start,test_date` (estos nombres de columna en inglés, sea cual sea el idioma). Una fila por cada solicitud citada: `request_id` y `doctor_id` tal como vienen en los datos, `date` como AAAA-MM-DD y `start` como HH:MM, la hora de inicio del primer hueco de la visita (por ejemplo `R017,D04,2026-11-18,09:40,`). 
<!-- tier: easy -->
Deje `test_date` vacía.
<!-- /tier -->
<!-- tier: medium hard -->
`test_date` es la fecha (AAAA-MM-DD) del análisis de sangre cuando la solicitud lo necesita, y se deja vacía en caso contrario.
<!-- /tier -->
Las solicitudes que no quepan simplemente no se incluyen; ninguna solicitud puede aparecer dos veces.

## Notas sobre los datos

- El periodo de citación son los diez días laborables del lunes 16 al viernes 27 de noviembre de 2026 (de lunes a viernes; los fines de semana no hay consulta). El lunes 23 de noviembre cuenta como día laborable.
- `huecos_libres.csv` solo recoge los huecos que siguen libres; todo lo demás ya está ocupado. Cada fila es un hueco de 20 minutos de un médico, indicado por su hora de inicio. Las consultas de mañana son de 09:00 a 12:00 y las de tarde de 13:00 a 17:00.
- La duración de la visita depende de `tipo_visita`: una `primera visita` ocupa **dos huecos libres consecutivos** del mismo médico el mismo día (por ejemplo 09:00 y 09:20, con `start` 09:00); una `revisión` ocupa un hueco. Una visita no puede pasar por encima de la pausa del mediodía.
- Cada solicitud se cita con un médico de su `especialidad` (véase `medicos.csv`).
- `fecha_desde` viene de nuestro antiguo sistema de citas y está escrita como **día/mes/año** (10/11/2026 es el 10 de noviembre). Es el primer día en que el paciente puede venir; nunca se cita antes. Si es anterior al 16 de noviembre, el paciente ya lleva tiempo esperando y puede venir cualquier día desde el 16.
- La fecha de referencia de una solicitud es su `fecha_desde`, o el 16 de noviembre si es anterior. La espera se cuenta en días laborables desde la fecha de referencia hasta el día de la cita (mismo día = 0).
- Códigos de `urgencia`: `U` = urgente, `S` = pronto, `R` = ordinaria. `nota_triaje` es texto libre, solo informativo. Nuestro acuerdo de servicio clínico exige que toda solicitud **urgente** se atienda en un plazo de **{{urgent_days}} días laborables** desde su fecha de referencia (ese mismo día o uno de los {{urgent_days}} días laborables siguientes). Todas las solicitudes U deben quedar citadas.
- Una `revisión` (con `medico_anterior` relleno) se cita con ese mismo médico: los pacientes esperan ver al médico que ya los conoce. Es una costumbre de nuestra admisión, no una obligación contractual. Tenga en cuenta que el médico D11 (Traumatología) está de vacaciones la primera semana (véase `avisos_consultas.txt`), así que esa semana no hay huecos de D11 en la lista.
- Idiomas: si el médico no habla el `idioma_preferido` del paciente (véase `idiomas` en `medicos.csv`), la visita necesita intérprete. Tenemos **{{interpreters_per_day}} intérpretes presenciales al día** para todo el hospital, y una **primera visita** tiene que contar con intérprete presencial, así que como máximo hay {{interpreters_per_day}} primeras visitas con intérprete al día. Las revisiones con intérprete usan un intérprete presencial si alguno de los {{interpreters_per_day}} sigue libre ese día y, si no, nuestro servicio de interpretación por vídeo, que pagamos (**3 por visita**). Las visitas con un médico que habla el idioma del paciente no necesitan intérprete.
- Festivo: el 23 de noviembre es el Día de la Ciudad (véase `avisos_consultas.txt`). Las demás especialidades trabajan con normalidad, pero **{{closed_dept}} cierra ese día**. La agenda no se actualizó y `huecos_libres.csv` todavía muestra huecos de {{closed_dept}} el 23; no deben usarse.
<!-- tier: easy -->
- En esta ronda solo se aplican las reglas anteriores: no tenga en cuenta `volante_valido_hasta`, `prueba_previa` ni `historial_asistencia.csv`, y deje `test_date` vacía.
<!-- /tier -->
<!-- tier: medium -->
- En esta ronda no se sobrecita y no se usa `historial_asistencia.csv`.
<!-- /tier -->
<!-- tier: medium hard -->
- Volantes: cada paciente de primera visita viene con un volante de derivación, y `volante_valido_hasta` (también **día/mes/año**) es el último día en que es válido. La visita debe hacerse ese día o antes; después el volante caduca y el paciente necesitaría uno nuevo, así que es mejor dejar esa solicitud sin citar.
- Análisis de sangre: cuando `prueba_previa` indica `análisis de sangre en ayunas`, el paciente debe hacerse el análisis en nuestro laboratorio **al menos un día laborable antes de la visita** (los resultados tardan un día) y no antes de su `fecha_desde`. El análisis es otra visita, por la mañana, y su fecha va en `test_date`. El laboratorio admite como máximo **{{lab_cap}} análisis de sangre en ayunas por día laborable**, para todas las especialidades juntas.
<!-- /tier -->
<!-- tier: hard -->
- Ausencias: algunos pacientes no se presentan. Cada paciente tiene su propia tasa de ausencias; `historial_asistencia.csv` da las citas previas y las citas perdidas de los pacientes que ya han venido antes (los de primera visita no tienen historial; en todo el hospital se pierde más o menos una cita de cada cinco). Cuanto más tiempo pasa entre la citación y la visita, más ausencias: aproximadamente **un punto porcentual más por cada día laborable** de antelación. Las cifras pasadas se midieron con unos 5 días laborables de antelación, y estas solicitudes se recibieron 2 días laborables antes del 16 de noviembre.
- Sobrecitación: por las ausencias permitimos **sobrecitar revisiones**: un hueco puede tener **dos revisiones** (nunca una primera visita, que necesita sus dos huecos para ella sola), y cada médico puede tener como máximo **{{overbooked_per_session}} huecos sobrecitados por consulta** (de mañana o de tarde).
<!-- /tier -->

## Cómo se evalúa el plan

**Restricciones obligatorias** (si se incumple alguna, el plan no vale):

- Solo huecos libres de `huecos_libres.csv`; una primera visita usa dos huecos libres consecutivos del mismo médico y una revisión uno.
<!-- tier: easy medium -->
- Ningún hueco se usa dos veces.
<!-- /tier -->
<!-- tier: hard -->
- Un hueco tiene como máximo dos revisiones y una primera visita nunca comparte sus huecos; como máximo {{overbooked_per_session}} huecos sobrecitados por médico y consulta.
<!-- /tier -->
- El médico pertenece a la especialidad solicitada.
- Ninguna cita antes de `fecha_desde`; ninguna cita de {{closed_dept}} el 23 de noviembre.
- Como máximo {{interpreters_per_day}} primeras visitas con intérprete al día.
- Todas las solicitudes urgentes se citan dentro de los {{urgent_days}} días laborables siguientes a su fecha de referencia.
- Las revisiones se citan con su médico anterior (es costumbre nuestra; podemos hacer una excepción si beneficia a los pacientes).
<!-- tier: medium hard -->
- Las primeras visitas se hacen mientras el volante sigue vigente.
- Cada análisis de sangre se hace entre la fecha desde y el día laborable anterior a la visita, con un máximo de {{lab_cap}} al día.
<!-- /tier -->

**Calidad**: para cada solicitud citada, sus días laborables de espera multiplicados por un peso (U 3, S 2, R 1), más 20 por cada solicitud S citada más de {{soon_days}} días laborables después de su fecha de referencia, más 60 por cada solicitud sin citar, más 3 por cada revisión con interpretación por vídeo. Cuanto más bajo, mejor.
<!-- tier: hard -->
Además contamos el coste esperado de las ausencias y de la sobrecitación: 10 por cada hueco cuyos pacientes no se presentan (una primera visita arriesga sus dos huecos), y 25 por cada hueco sobrecitado en el que se presentan los dos pacientes y el médico se retrasa. Ambos son valores esperados según las tasas reales de ausencia de los pacientes.
<!-- /tier -->
