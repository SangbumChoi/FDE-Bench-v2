# Coordinador de reparto de panadería — `logistics/bakery_delivery_dispatcher`

La cocina central de una panadería reparte cada mañana bandejas de pan a sus cafeterías con cuatro furgonetas. El
cliente pide al agente que planifique las rutas de mañana (lunes) "para que las cafeterías reciban sus bandejas a
tiempo y los conductores no estén fuera más de lo necesario". El entregable es `routes.json`: para cada furgoneta
utilizada, una hora de salida (`HH:MM`, 05:00 si se omite) y las cafeterías en orden de visita. El evaluador recorre
el plan con el modelo de desplazamiento del mundo y lo puntúa frente a la referencia.

El caso no tiene configuraciones: es un único problema fijo en todas las dificultades (sin niveles ni conjuntos de
reglas). Los ajustes de modalidad (especificación completa frente a aclarar primero, perfil del cliente, ruido en los
datos, eventos) se aplican por encima, como en todos los casos (véase [cases/README.md](../../README.md)). Además es
el fixture de pruebas del framework (`tests/conftest.py`), por lo que su validación tiene que seguir siendo rápida.

## Datos

`cafes` (18 cafeterías C01–C18: `x_km` / `y_km` respecto a la cocina en (0, 0), `trays` 8–30, `tier`
premium/standard, `opens`, `deliver_by`, `partner_brand`) y `vans` (V1–V4, `max_trays` 120, solo V4 refrigerada).
Los nombres de archivo, los encabezados y las etiquetas están localizados (`매장목록.csv` con `매장등급 = 프리미엄`,
`cafeterias.csv` con `categoria = premium`); los códigos y los números, no. La cafetería cerrada es una fila más:
solo el cliente sabe que está cerrada.

Con la semilla del caso (20261025) hay 17 cafeterías abiertas con 356 bandejas, frente a 480 bandejas de capacidad de
la flota. Las cafeterías asociadas son Cafetería Puerto (C05, estándar), Cafetería Torre del Reloj (C10, premium) y
Cafetería Estadio (C16, premium); las demás cafeterías premium son C01, C04, C07 y C13.

## Lo que sabe el cliente (requisitos ocultos)

- La distancia por carretera es 1.3 veces la distancia en línea recta. La velocidad depende de cuándo empieza el
  tramo: 30 km/h antes de las 07:00 y 20 km/h a partir de las 07:00 (hora punta). La descarga dura 4 minutos más
  0.2 minutos por bandeja.
- Una furgoneta que llega antes de `opens` espera. Llegar después de `deliver_by` se acepta, pero cada minuto de
  retraso le cuesta a la panadería lo mismo que tres minutos de furgoneta (quejas, abonos).
- Las furgonetas salen desde las 05:00 y están de vuelta a las 09:30 como muy tarde (fin del turno de los
  conductores); cada una lleva como máximo `max_trays` bandejas.
- La Cafetería Colina Sur (C11) está cerrada esta semana por reformas.
- Las cafeterías con `partner_brand` venden productos refrigerados del socio, así que solo la furgoneta refrigerada
  V4 puede atenderlas.
- Cada cafetería recibe todas sus bandejas en una sola visita de una sola furgoneta.
- La costumbre de la empresa: en cada ruta, las cafeterías premium van antes que las estándar.

Hay 9 preguntas clave: distancia por carretera, velocidades, tiempo de descarga, turno, cafetería cerrada, cadena de
frío, una sola visita, premium primero y el coste del retraso.

## Reglas

| Regla | Tipo | Significado |
|---|---|---|
| `van_capacity` | física | Una furgoneta lleva como máximo 120 bandejas. |
| `shift_window` | física | Las furgonetas salen a las 05:00 o más tarde y están de vuelta en la cocina a las 09:30 como muy tarde. |
| `closed_cafe` | física | No se entrega a la cafetería cerrada (C11). |
| `serve_each_once` | contractual | Cada cafetería abierta se atiende exactamente una vez. |
| `cold_chain` | contractual | Las cafeterías de marca asociada solo las atiende la furgoneta refrigerada. |
| `premium_first` | costumbre del negocio | En cada ruta, las cafeterías premium van antes que las estándar (puede flexibilizarse mediante el procedimiento de excepción con las políticas que hacen flexible la costumbre del negocio). |

**Calidad (cuanto menor, mejor):** el tiempo total que están fuera todas las furgonetas, de la salida a la vuelta
(incluida la espera en cafeterías que aún no han abierto), más 3 × cada minuto que una cafetería recibe el pedido
después de su `deliver_by`.

## Situaciones presentes

- **Hecho oculto:** C11 está cerrada esta semana; nada en los datos lo indica.
- **Semántica de los datos:** `partner_brand = yes` significa productos refrigerados y, por tanto, solo la furgoneta
  refrigerada.
- **Costumbre que puede flexibilizarse:** premium primero. Con esta semilla obliga a V4 a atender C16 y C10 antes que
  C05, de modo que en todo plan que cumple las reglas C05 recibe el pedido unos 10 minutos después de su
  `deliver_by` de las 07:30.
- **Compromiso:** salir más tarde evita esperar en cafeterías que aún no han abierto, pero los tramos que empiezan a
  partir de las 07:00 son más lentos y las llegadas tardías cuestan el triple.
- No hay evento fechado ni presión de partes interesadas (véase REVIEW.md, F8).

## Referencia y línea base

La **referencia** (`_solve`) construye las rutas por inserción factible más barata (primero las cafeterías asociadas,
luego por categoría, de mayor a menor) y, cuando la construcción voraz se queda sin salida, reintenta con V4 iniciada
con cada orden viable de las cafeterías asociadas y después con órdenes de inserción barajados. A continuación
reubica paradas sueltas mientras el objetivo siga bajando y asigna a cada ruta su mejor hora de salida en una
cuadrícula de 5 minutos.

La **línea base** (`baseline_solution`) es el plan del propio coordinador de reparto sin un ingeniero: V4 se encarga
de las cafeterías asociadas (premium primero, en el orden que la hace volver antes); las demás cafeterías se ordenan
por acimut alrededor de la cocina, empezando por el oeste, y se cargan en V1, V2, V3 y luego V4 hasta que la siguiente
ya no cabe (capacidad, vuelta a las 09:30); cada furgoneta atiende primero sus cafeterías premium y después el resto
por orden de apertura; todas salen a las 05:00, cuando empieza el turno, y se ignora `deliver_by`. Si sobra alguna
cafetería, el barrido vuelve a empezar desde la siguiente cafetería de la vuelta (si ningún punto de partida
funciona, se recorren las rutas de la referencia con todas las furgonetas saliendo a las 05:00, lo que siempre es
válido; ningún mundo construido hasta ahora lo ha necesitado).

| Semilla 20261025 | Objetivo | Minutos de ruta | Minutos de retraso | Rutas |
|---|---|---|---|---|
| Referencia | 625.55 | 592.74 | 10.94 | V1 06:20 C01 C04 C15 C08 · V2 06:00 C13 C07 C18 C06 · V3 05:45 C09 C03 C14 C02 C17 · V4 06:10 C16 C10 C05 C12 |
| Línea base | 963.09 | 897.53 | 21.85 | V1 C03 C14 C02 C17 · V2 C07 C13 C09 C18 C06 C12 · V3 C01 C04 C08 C15 · V4 C16 C10 C05, todas a las 05:00 |

La mayor parte del coste adicional de la línea base es espera: al salir a las 05:00, las furgonetas llegan a
cafeterías que abren de las 06:00 en adelante.

Otras semillas de mundo (el panel de `validate-case` y dos más):

| Semilla de mundo | Referencia | Línea base | Línea base / referencia |
|---|---|---|---|
| 1 | 568.06 | 1,292.28 | 2.27 |
| 2 | 779.02 | 1,192.03 | 1.53 |
| 3 | 560.91 | 1,402.46 | 2.50 |
| 7 | 543.02 | 939.29 | 1.73 |
| 42 | 532.93 | 1,415.56 | 2.66 |

Con la semilla del caso y las semillas de mundo 1–50, la línea base es válida en los 51 mundos (el recurso de respaldo
nunca se usa) y cuesta entre 1.37 y 4.16 veces lo que la referencia (mediana 2.19). `validate-case --world-seeds
1,...,50` pasa.

**Margen de mejora** (semilla 20261025; "q" es la calidad normalizada, con la línea base en 0 y la referencia en 1).
Una búsqueda de recocido simulado desde la referencia (movimientos de reubicación, intercambio y 2-opt, salidas al
minuto; un script de análisis, no forma parte del caso) llega a 601.51 cumpliendo todas las reglas, q = 1.07, con lo
que obtiene 0.71 de la puntuación de calidad con el tope de la política en 1.5 (la referencia obtiene 0.67). Sus cargas
son de 89/85/115/67 bandejas y su vuelta más tardía es a las 09:21, así que ahí no limitan ni la capacidad ni el turno.
Con `premium_first` flexibilizada, la misma búsqueda llega a 521.98 sin minutos de retraso (q = 1.31) y se salta la
costumbre en tres de las cuatro rutas.

## Notas

- Sintético. Las posiciones, el número de bandejas, las horas de apertura, las velocidades, el tiempo de descarga y el
  peso del retraso son inventados; la velocidad es un escalón a las 07:00 según la hora de inicio del tramo, no un
  modelo de desplazamiento dependiente del tiempo.
- `build_world` sigue extrayendo del flujo aleatorio de la semilla hasta que el solucionador de referencia encuentra un
  plan que cumple todas las reglas y cada regla tiene un plan que solo la incumple a ella, de modo que cualquier semilla
  de mundo da un mundo utilizable.
- `validate-case` comprueba que la referencia tiene calidad 1.0, que la línea base es válida y peor, que hay un
  entregable por regla que incumple solo esa regla y que los datos son deterministas en los cinco idiomas; además comprueba las semillas de mundo 1, 2 y 3.
