# Especialista en cribado de currículos — `people_hr/resume_screening_specialist`

Una empresa de pagos en crecimiento con sede en Singapur ha recibido 250 solicitudes para tres puestos vacantes (R1 Ingeniero/a
de backend, R2 Analista de datos, R3 Analista de seguridad) y pide al agente que "preseleccione a los mejores candidatos para
entrevistarlos". La solicitud adjunta las descripciones de los puestos, la exportación de candidatos del sistema de selección y
datos de 360 personas contratadas antes para los mismos puestos. Todo lo que decide la validez y la calidad (ocho por puesto,
los requisitos imprescindibles, qué experiencia cuenta, los certificados vencidos, el permiso de trabajo, un puesto por
candidato, el control de impacto adverso, el sesgo de los responsables en las puntuaciones pasadas y la costumbre de los
referidos) está en los requisitos ocultos y hay que preguntarlo. El entregable es `shortlist.csv`
(`role_id,candidate_id,rank`, 8 filas por puesto).

El caso no tiene configuraciones: el mismo problema se puntúa en todas las dificultades. Los ajustes de la modalidad
(especificación completa o preguntar primero, perfil del cliente, ruido en los datos, eventos) se aplican encima, como en
todos los casos (véase [cases/README.md](../../README.md)).

## Datos

| Archivo (en) | Contenido |
|---|---|
| `candidates.csv` | 250 candidatos: `applied_roles` (1 o 2 de R1–R3), `application_date`, `location`, `work_authorization` (ciudadano, residente permanente, permiso de trabajo vigente, requiere patrocinio de visado), `highest_education`, `graduation_year`, `total_years_experience` (toda la carrera; una trampa), `skills` (etiquetas), `languages`, `referral` y los atributos protegidos `gender`, `age_band`, `nationality` |
| `work_history.csv` | Una fila por empleo: `job_family` y mes de inicio y de fin (`present` = sigue en el empleo) |
| `certifications.csv` | Una fila por certificado, con `issued_on` y `expires_on` |
| `past_hires.csv` | 360 contrataciones de 2021–2025 con los años relevantes y los certificados al ingresar, habilidades, estudios, atributos protegidos, referido y `performance_score_1y` (la fórmula de ajuste sin ruido, más ruido con desviación típica 4.5, más el sesgo de los antiguos responsables: +6 hombres, −5 mujeres, +5 menores de 30, +3 de 30 a 39, −6 de 40 a 49, −10 de 50 o más, +6 singapurenses, −2 el resto) |
| `job_descriptions.md` | Los tres puestos, con las habilidades imprescindibles y las deseables en una sola lista |

Las etiquetas de los datos están traducidas en los cinco idiomas; los identificadores y los números no. 113 candidatos están
cualificados para al menos un puesto al que se presentaron (R1 39, R2 57, R3 26; 9 para dos puestos). 15 candidatos son
referidos, y 6 de ellos están cualificados.

## Reglas

| Regla | Tipo | Qué exige |
|---|---|---|
| `must_have_skills` | contractual | Las dos habilidades imprescindibles, la experiencia relevante mínima (R1 36 meses de desarrollo de software, R2 24 de análisis de datos, R3 24 de seguridad de la información; con el mes de inicio y el de fin incluidos y `present` hasta octubre de 2026) y, para R3, un CISSP o Security+ vigente el 1 de noviembre de 2026 |
| `work_authorization` | física | Nadie que requiera patrocinio de visado en R1 ni en R3; R2 es remoto a través de un socio de empleo (EOR) y queda exento |
| `one_role_per_candidate` | contractual | Un candidato figura como máximo en una preselección |
| `adverse_impact` | física | Entre los candidatos cualificados, un grupo de género, de edad (menores de 40 / 40 o más) o de nacionalidad (Singapur / otras) con 15 o más personas solo suspende si su tasa de selección es inferior a 0.8× la del grupo más alto **y** una prueba exacta de Fisher bilateral frente a ese grupo da p < 0.05 |
| `referral_boost` | costumbre del negocio (puede flexibilizarse) | Todo referido cualificado está preseleccionado (la costumbre de la empresa) |

La calidad es la suma del ajuste real de los 24 preseleccionados al puesto en el que figuran. El ajuste real es 30 + un peso
por cada año de experiencia relevante por encima del mínimo (con tope) + habilidades deseables ponderadas + un certificado
adicional vigente + estudios (R2) + ruido gaussiano (desviación típica 3), en la escala 0–100 de las puntuaciones pasadas sin
el sesgo de los responsables. Las 9 preguntas clave son: tamaño de la preselección, requisitos imprescindibles, experiencia
relevante, vencimiento de los certificados, permiso de trabajo, un solo puesto, el sesgo de las contrataciones previas,
impacto adverso y la costumbre de los referidos.

## Situaciones presentes

- Hechos ocultos: todas las reglas anteriores, y además cómo se cuentan la experiencia relevante y la vigencia de los
  certificados. El generador del mundo mantiene a los candidatos a más de un mes de cualquier mínimo y los certificados
  lejos de la fecha de corte, de modo que las convenciones de conteo nunca deciden una cualificación (revisión F5).
- Una señal de aprendizaje sesgada: las puntuaciones de las contrataciones previas llevan el sesgo de los responsables y, en
  esas contrataciones, la edad se construye a partir de la experiencia, así que una regresión solo con las columnas del
  puesto está confundida. Los requisitos prohíben usar las columnas demográficas como entradas de la puntuación de cribado,
  pero permiten usarlas para medir y eliminar ese sesgo.
- Personas que se presentan a dos puestos y son fuertes en ambos (3 de ellas en la preselección de referencia).
- Una costumbre de la empresa que puede flexibilizarse: los seis referidos cualificados quedan abajo en el orden de ajuste
  de sus puestos, así que respetarlos cuesta alrededor del 5% del objetivo.
- No hay eventos con fecha, ni presión de ninguna parte interesada, ni conjuntos de reglas (revisión F3).

## Control de impacto adverso: calibración

Con 24 plazas para 113 candidatos cualificados en grupos de unas 56 personas, la regla de los cuatro quintos por sí sola
marca diferencias de dos o tres personas. El caso añadía antes una tolerancia de una persona, y aun así las preselecciones que
no miran los atributos protegidos suspendían por azar. Ahora el control añade una prueba de significación (la combinación
habitual de significación práctica y estadística): un grupo por debajo de la línea de los cuatro quintos solo se marca si una
prueba exacta de Fisher bilateral sobre la tabla 2 × 2 (este grupo y el grupo con la tasa más alta, seleccionados frente a no
seleccionados) da p < 0.05. Se elimina la tolerancia de una persona: en 800 preselecciones de prueba nunca cambió un
resultado una vez aplicada la prueba.

Panel: por mundo, 400 preselecciones casi óptimas que no miran los atributos protegidos, construidas con la asignación voraz
de la referencia a partir de puntuaciones con ruido: 200 a partir de la puntuación de cribado de la referencia y 200 a partir
de la fórmula de ajuste sin ruido, cada una con ruido gaussiano por candidato y puesto (desviación típica 0.5, 1 o 2) o con
cada peso multiplicado por un factor aleatorio (desviación típica del 30%). Aprendices sesgados: 200 preselecciones puntuadas
con la fórmula sin ruido más 0.5–1.5× el sesgo de los responsables más ruido. El mundo y la referencia no cambian: el
generador sigue eligiendo mundos cuya referencia supera el control antiguo, más estricto.

| Semilla de mundo | Superan el control antiguo (basadas en la referencia / en la fórmula) | Superan el control nuevo | Preselecciones sesgadas marcadas (antiguo / nuevo) |
|---|---|---|---|
| 20261103 (pública) | 340 de 400, 85.0% (183 / 157) | 400 de 400, 100% | 100% / 100% |
| 1 | 341 de 400, 85.3% (149 / 192) | 399 de 400, 99.8% | 100% / 99.5% |
| 2 | 330 de 400, 82.5% (180 / 150) | 399 de 400, 99.8% | 100% / 99.5% |
| 3 | 298 de 400, 74.5% (139 / 159) | 398 de 400, 99.5% | 100% / 100% |

En la semilla pública la referencia pasa con una razón mínima de 0.727 (otras nacionalidades 10/56 frente a singapurenses
14/57, p = 0.49). Una regresión sobre las contrataciones previas que mantiene los efectos protegidos en la puntuación suspende
con una razón mínima de 0.26 (p = 0.001); el ejemplo del validador que deja fuera a las mujeres suspende con 0.15. La prueba
tiene menos potencia que la regla antigua ante diferencias leves: ordenar por el número de habilidades deseables (razón
mínima 0.46, p = 0.060) ahora pasa, y una cuarta parte del sesgo de los responsables no se marca en ninguno de los cuatro
mundos.

## Referencia y línea base (semilla 20261103)

La **referencia** coloca a cada referido cualificado en el puesto donde mejor puntúa y después asigna de forma voraz pares
(candidato, puesto) según una puntuación de cribado sencilla: años relevantes + 1.5 por habilidad deseable + 2 por un
certificado adicional vigente. La **línea base** es lo que el cliente hace hoy sin un ingeniero: el mismo filtro de
requisitos imprescindibles, la costumbre de los referidos y la regla de un puesto por candidato, y después primero quienes
tienen más años de experiencia relevante, sin mirar nada más.

Calidad normalizada q = (objetivo − 1226.29) / (1254.49 − 1226.29); el tope por defecto de las políticas, 1.5, se alcanza con
un objetivo de 1268.59 (1.011 de la referencia).

| Preselección | Objetivo | Razón respecto a la referencia | q | Válida |
|---|---|---|---|---|
| Línea base: solo años relevantes | 1226.29 | 0.978 | 0 | sí |
| Referencia | 1254.49 | 1.000 | 1 | sí |
| Puntuaciones aleatorias, misma asignación voraz (200 válidas de 211 extraídas) | — | 0.851–0.995, media 0.934 | por debajo de 0 | sí |
| Orden por años de experiencia total (manteniendo los imprescindibles) | 1203.18 | 0.959 | por debajo de 0 | sí |
| Orden por número de habilidades deseables | 1285.52 | 1.025 | 2.10 | sí |
| Regresión sobre las contrataciones previas, años con tope, solo columnas del puesto | 1314.84 | 1.048 | 3.14 | sí |
| Igual, con los atributos protegidos como controles (descartados al puntuar) | 1328.65 | 1.059 | 3.63 | sí |
| Regresión, años lineales, solo columnas del puesto | 1279.46 | 1.020 | — | no: impacto adverso (p = 0.037) |
| Regresión que mantiene los términos protegidos en la puntuación | 1260.09 | 1.004 | — | no: impacto adverso (p = 0.001) |
| Fórmula de ajuste sin ruido | 1315.86 | 1.049 | 3.18 | sí |
| Oráculo de ajuste (ajuste real con el ruido incluido) | 1343.64 | 1.071 | 4.16 | sí |
| Referencia sin la costumbre de los referidos | 1316.22 | 1.049 | 3.19 | solo con `referral_boost` flexibilizada |

Con las semillas de mundo 1, 2 y 3 la línea base obtiene 0.951, 0.949 y 0.957 de la referencia (objetivos 1170.98 frente a
1231.73, 1116.54 frente a 1176.82 y 1140.42 frente a 1192.18). Nada en la línea base atiende al control de impacto adverso,
así que el generador exige además que la línea base sea válida; sin esa exigencia, suspendía el control con la semilla de
mundo 23 (p = 0.037). Con las semillas de mundo 1–40 la línea base obtiene 0.913–0.996 de la referencia (mediana 0.961);
donde la diferencia es menor del 1%, la escala normalizada es muy empinada. Todo aprendiz competente queda por encima del
tope, de modo que el componente de calidad distingue la línea base de un agente al nivel de la referencia, pero no a un buen
aprendiz del oráculo (revisión F1).

## Notas

- Datos sintéticos. Los candidatos, las carreras, las habilidades, los certificados, las puntuaciones y el tamaño de los
  sesgos son generados; los pesos del ajuste son decisiones de diseño. La regla de los cuatro quintos sigue la práctica
  estadounidense (las Uniform Guidelines on Employee Selection Procedures, 29 CFR 1607.4D, que también señalan que las
  diferencias basadas en números pequeños que no son estadísticamente significativas pueden no constituir impacto adverso),
  y lo mismo ocurre con el corte de edad en 40 años o más (la Age Discrimination in Employment Act de Estados Unidos). Los
  requisitos califican el control de requisito legal, aunque el caso transcurre en Singapur, donde no se conoce ninguna ley
  que imponga una prueba estadística de este tipo (revisión F8).
- Todos los números de esta página salen de `case.py` (`_solve`, `check`, `_fit_value`); los paneles y las regresiones son
  un script de análisis, no forman parte del caso.
- `validate-case` comprueba el determinismo en los cinco idiomas, la referencia con calidad 1, una línea base válida y peor,
  un ejemplo que incumple cada regla y las semillas de mundo 1–3.
