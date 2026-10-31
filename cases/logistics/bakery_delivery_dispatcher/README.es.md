# Coordinador de reparto de panadería — `logistics/bakery_delivery_dispatcher`

La cocina central de una panadería reparte cada mañana bandejas de pan a sus cafeterías con cuatro furgonetas. El
cliente pide al agente que planifique las rutas de mañana (lunes) "para que las cafeterías reciban sus bandejas a
tiempo y los conductores no estén fuera más de lo necesario". El entregable es `routes.json`: para cada furgoneta
utilizada, una hora de salida (`HH:MM`, 05:00 si se omite) y las cafeterías en orden de visita. El evaluador recorre
el plan con el modelo de desplazamiento de la configuración y lo puntúa frente a la referencia.

El caso tiene **configuraciones**: tres niveles × semillas de reglas (DESIGN.md, Settings). Los datos y la solicitud
son los mismos en todas las configuraciones; solo cambian las reglas ocultas del cliente y, con ellas, el plan
correcto. Los ajustes de la modalidad (especificación completa frente a aclarar primero, perfil del cliente, ruido en
los datos, eventos) se aplican por encima, como en todos los casos (véase [cases/README.md](../../README.md)). Además
es el fixture de pruebas del framework (`tests/conftest.py`, `tests/test_validator.py`), por lo que su validación
tiene que seguir siendo rápida.

## Niveles

| Nivel | Reglas que se aplican | Fuera de alcance (dicho con las palabras del cliente) |
|---|---|---|
| **easy** | El núcleo del reparto: el límite de bandejas por furgoneta de esta semana, el turno de los conductores (salida desde las 05:00, vuelta como muy tarde al fin del turno), una sola visita por cafetería, la cafetería cerrada esta semana, 25 km/h constantes, el coste del retraso | La cadena de frío del socio ("esta semana el socio lleva sus refrigerados él mismo … cualquier furgoneta puede atenderlas"), la costumbre de atender primero las premium ("esta semana dejamos de lado la costumbre"), la hora punta ("el lunes no hay colegio"), la revisión de frenos de V2 ("es el martes") |
| **medium** | Lo de easy + la cadena de frío del socio (las cafeterías de marca asociada, solo con la furgoneta refrigerada V4) + la costumbre de atender primero las premium cuando la semilla de reglas la saca | La hora punta y la revisión de frenos de V2, como en easy |
| **hard** | Lo de medium + la hora punta de la mañana (30 km/h antes de `rush_start` y 20 km/h desde esa hora, también en un tramo ya empezado), un evento con fecha (el lunes V2 está en el taller hasta las 06:40) y la presión de la encargada de la Cafetería Lago Este (C07), que insiste en ser la primera parada antes de las 06:30 (no es una regla) | — |

## Parámetros (lo que sortea una semilla de reglas)

Cada parámetro se sortea por separado entre los candidatos de su nivel en la configuración (`case.yaml` `params:`).

| Parámetro | easy | medium | hard | Qué cambia |
|---|---|---|---|---|
| `closed_cafe` | C11, C03, C14 | igual | igual | Qué cafetería no debe atenderse (Cafetería Colina Sur / Estación Norte / Paseo de los Arces, con el nombre de los datos en todos los idiomas); todas las demás deben atenderse |
| `late_cost` | 3, 2, 5 | igual | igual | Cuántos minutos de furgoneta cuesta un minuto de retraso: el peso del retraso en el objetivo |
| `shift_end` | 09:30, 09:00, 10:00 | igual | igual | Hora a la que todas las furgonetas deben estar de vuelta en la cocina |
| `van_capacity` | 100, 110, 120 | igual | 110 | Bandejas por furgoneta esta semana (`max_trays` en los datos es 120; las cajas nuevas ocupan más). Fijo en hard, así que sus candidatos se comparan en medium |
| `rush_start` | none | none | 07:00, 06:30, 07:30 | Hora a la que las furgonetas pasan de 30 a 20 km/h (easy y medium: 25 km/h toda la mañana) |
| `premium_first` | false | true, false | true, false | Si esta semana se aplica la costumbre de atender primero las premium |

Las furgonetas, el inicio a las 05:00, la distancia por carretera (1.3 × la línea recta), la descarga (4 + 0.2 min por
bandeja), el taller de V2 hasta las 06:40 (hard) y la cafetería que presiona (C07) son fijos. `case.py` no deriva
ningún valor y no necesita `admissible()`: toda combinación es factible en cualquier mundo que `build_world` acepte
(véase más abajo).

## Panel público (semillas de reglas 5, 13 y 58) con la semilla del caso 20261025

La semilla 5 sortea la **combinación principal** (headline) de cada nivel: el fin de turno más tardío y el límite de
bandejas más alto, con el primer candidato de cada uno de los demás parámetros (`case.py` `_headline`); la
comprobación de influencia de los parámetros del validador parte de ella.

| Configuración | Parámetros sorteados | Referencia | Línea base | Línea base / referencia |
|---|---|---|---|---|
| easy/s5 | C11, retraso 3, 10:00, 120 bandejas, sin hora punta, costumbre desactivada | 435.73 | 1,669.60 | 3.83 |
| easy/s13 | C14, retraso 5, 09:00, 100 bandejas, sin hora punta, costumbre desactivada | 449.79 | 1,285.12 | 2.86 |
| easy/s58 | C03, retraso 2, 09:30, 110 bandejas, sin hora punta, costumbre desactivada | 420.30 | 1,189.64 | 2.83 |
| medium/s5 | C11, retraso 3, 10:00, 120 bandejas, sin hora punta, **costumbre activada** | 626.50 | 1,977.71 | 3.16 |
| medium/s13 | C14, retraso 5, 09:00, 100 bandejas, sin hora punta, costumbre desactivada | 463.34 | 1,273.22 | 2.75 |
| medium/s58 | C03, retraso 2, 09:30, 110 bandejas, sin hora punta, costumbre desactivada | 440.61 | 1,141.36 | 2.59 |
| hard/s5 | C11, retraso 3, 10:00, 110 bandejas, hora punta 07:00, **costumbre activada** | 709.27 | 1,870.28 | 2.64 |
| hard/s13 | C14, retraso 5, 09:00, 110 bandejas, hora punta 07:30, costumbre desactivada | 472.58 | 1,269.31 | 2.69 |
| hard/s58 | C03, retraso 2, 09:30, 110 bandejas, hora punta 06:30, costumbre desactivada | 537.35 | 1,177.53 | 2.19 |

Los diccionarios tal como se guardan en `dataset/gt/<tier>_s<seed>/setting.json` (`rush_start` y `premium_first` tal
como se sortearon):

```
easy/s5    {closed_cafe: C11, late_cost: 3, shift_end: "10:00", van_capacity: 120, rush_start: none, premium_first: false}
easy/s13   {closed_cafe: C14, late_cost: 5, shift_end: "09:00", van_capacity: 100, rush_start: none, premium_first: false}
easy/s58   {closed_cafe: C03, late_cost: 2, shift_end: "09:30", van_capacity: 110, rush_start: none, premium_first: false}
medium/s5  {closed_cafe: C11, late_cost: 3, shift_end: "10:00", van_capacity: 120, rush_start: none, premium_first: true}
medium/s13 {closed_cafe: C14, late_cost: 5, shift_end: "09:00", van_capacity: 100, rush_start: none, premium_first: false}
medium/s58 {closed_cafe: C03, late_cost: 2, shift_end: "09:30", van_capacity: 110, rush_start: none, premium_first: false}
hard/s5    {closed_cafe: C11, late_cost: 3, shift_end: "10:00", van_capacity: 110, rush_start: "07:00", premium_first: true}
hard/s13   {closed_cafe: C14, late_cost: 5, shift_end: "09:00", van_capacity: 110, rush_start: "07:30", premium_first: false}
hard/s58   {closed_cafe: C03, late_cost: 2, shift_end: "09:30", van_capacity: 110, rush_start: "06:30", premium_first: false}
```

Todos los candidatos de todos los parámetros aparecen en el panel. Todos los parámetros influyen (validador; también
con las semillas de mundo 1–20):
- `closed_cafe`: la referencia de hard/s5 atiende C03 y C14, así que es inválida con cualquiera de las dos cerrada.
- `late_cost`: la referencia de hard/s5 acumula 56 minutos de retraso; su objetivo varía un 7.9% (peso 2) y un 15.8%
  (peso 5).
- `shift_end`: una furgoneta de hard/s5 vuelve a las 09:03, así que la referencia es inválida con las 09:00.
- `van_capacity` (comparado en medium): una furgoneta de medium/s5 lleva 103 bandejas, inválida con 100.
- `rush_start`: el objetivo de la referencia de hard/s5 varía un +14.0% con las 06:30 y un −10.6% con las 07:30.
- `premium_first`: sin la costumbre, la referencia es un 27.5% más barata en hard/s5 (514.28 frente a 709.27) y un
  28.4% en medium/s5 (448.70 frente a 626.50).

## Lo que un agente debe preguntar

Las preguntas clave, por nivel (`locales/<lang>/targets.yaml`):

- **Todos los niveles:** la distancia por carretera (1.3 ×), el tiempo de descarga, el fin del turno, la cafetería
  cerrada (cuál), una sola visita por cafetería, la costumbre de atender primero las premium (si se aplica o si queda
  en suspenso esta semana), el coste del retraso (su peso) y el límite de bandejas cuando está por debajo de las 120 de
  las estanterías (`tray_limit`, sorteado entre 100 y 110; en hard siempre 110).
- **easy y medium:** los 25 km/h constantes (`speed`).
- **easy:** que esta semana cualquier furgoneta puede atender las cafeterías asociadas (`partner_this_week`).
- **medium y hard:** la cadena de frío (las cafeterías asociadas, solo con V4).
- **hard:** la hora punta y su inicio (`rush_hour`), V2 en el taller hasta las 06:40 (`workshop`) y que la exigencia
  de la encargada de C07 no es una regla (`manager_pressure`).

Así, hay 9 o 10 preguntas clave en easy y medium, y 12 en hard.

## Datos

`cafes` (18 cafeterías C01–C18: `x_km` / `y_km` respecto a la cocina en (0, 0), `trays` 8–30, `tier`
premium/standard, `opens`, `deliver_by` 30, 45 o 60 minutos después de la apertura, `partner_brand`) y `vans`
(V1–V4, `max_trays` 120, solo V4 refrigerada). Los nombres de archivo, los encabezados y las etiquetas están
localizados (`매장목록.csv` con `매장등급 = 프리미엄`, `cafeterias.csv` con `categoria = premium`); los códigos y los
números, no, y el nombre de una cafetería va con su código (C11 es siempre la Cafetería Colina Sur). La cafetería
cerrada es una fila más: solo el cliente sabe que está cerrada.

Con la semilla del caso, las 18 cafeterías piden 332 bandejas (de 309 a 318 sin la cafetería cerrada, frente a una
capacidad de la flota de 400 a 480 bandejas). Las cafeterías asociadas son Cafetería Puerto (C05, estándar),
Cafetería Torre del Reloj (C10, premium) y Cafetería Estadio (C16, premium); las demás cafeterías premium son C01,
C04, C07 y C13. C07 abre a las 07:00 (entrega antes de las 08:00), así que el "antes de las 06:30" de la encargada
supondría una furgoneta esperando media hora a su puerta.

**Qué mundos se usan.** `build_world` sigue extrayendo del flujo aleatorio de la semilla hasta obtener un mundo que
sirva para todas las configuraciones que una semilla de reglas pueda sortear (públicas o privadas):
1. Para cada nivel, el solucionador de referencia atiende las 18 cafeterías con la combinación más estricta del nivel
   (100 bandejas, vuelta a las 09:00, en hard la hora punta desde las 06:30 y V2 desde las 06:40, y la costumbre y la
   cadena de frío donde el nivel las tiene). Ese plan es el plan de respaldo del nivel: sin la cafetería cerrada cumple
   las reglas de todas las configuraciones (un fin de turno más tardío, más bandejas, una hora punta más tardía, la
   ausencia de la costumbre y una parada menos nunca hacen volver más tarde a una furgoneta), así que toda
   configuración tiene un plan válido.
2. Los parámetros pueden cambiar la respuesta: con la combinación principal de cada nivel, la referencia hace volver
   una furgoneta después del fin de turno más temprano (hard), carga una por encima del límite de bandejas más bajo
   (medium), tiene un retraso de al menos el 1% de su objetivo y cuesta al menos un 1% más que sin la costumbre de
   atender primero las premium (hard).
3. Cada regla tiene un plan que solo la incumple a ella en hard con 110 bandejas y el fin de turno a las 09:00.

Pasa alrededor del 9% de las extracciones; construir un mundo lleva 0.8 s de media (como máximo 3.3 s con las
semillas de mundo 1–30).

## Reglas

| Regla | Tipo | Niveles | Significado |
|---|---|---|---|
| `van_capacity` | física | todos | Una furgoneta lleva como máximo `van_capacity` bandejas esta semana. |
| `shift_window` | física | todos | Las furgonetas salen a las 05:00 o más tarde y están de vuelta en la cocina a las `shift_end` como muy tarde. |
| `van_ready` | física | hard | V2 no sale antes de las 06:40 (el lunes está en el taller). |
| `closed_cafe` | física | todos | No se entrega a `closed_cafe`. |
| `serve_each_once` | contractual | todos | Cada cafetería abierta se atiende exactamente una vez. |
| `cold_chain` | contractual | medium, hard | Las cafeterías de marca asociada solo las atiende la furgoneta refrigerada. |
| `premium_first` | costumbre del negocio | medium, hard, solo si `premium_first` | En cada ruta, las cafeterías premium van antes que las estándar (puede flexibilizarse mediante el procedimiento de excepción con las políticas que hacen flexible la costumbre del negocio). |

**Calidad (cuanto menor, mejor):** el tiempo total que están fuera todas las furgonetas, de la salida a la vuelta
(incluida la espera en cafeterías que aún no han abierto), más `late_cost` × cada minuto que una cafetería recibe el
pedido después de su `deliver_by`.

## Situaciones presentes

- **Hechos ocultos:** qué cafetería está cerrada; el límite de bandejas de esta semana, por debajo de `max_trays`; el
  fin del turno; el peso del retraso; si se aplica la costumbre de atender primero las premium; en hard, cuándo empieza
  la hora punta.
- **Semántica de los datos:** `partner_brand = yes` significa productos refrigerados y, por tanto, solo la furgoneta
  refrigerada (medium, hard), pero no esta semana en easy.
- **Costumbre que puede flexibilizarse:** premium primero, donde se sortea. En las configuraciones de la combinación
  principal cuesta un 27–28% del objetivo, así que flexibilizarla mediante el procedimiento de excepción compensa
  donde la costumbre del negocio es flexible (REVIEW.md, F3).
- **Evento con fecha (hard):** V2 en el taller hasta las 06:40 el lunes.
- **Presión (hard):** la exigencia de la encargada de C07 de ser la primera parada antes de las 06:30. El cliente dice
  que no es una regla; atenderla supone esperar en una cafetería que abre a las 07:00 (semilla del caso) y rehacer una
  ruta.
- **Compromiso:** salir más tarde evita esperar en cafeterías que aún no han abierto, pero en hard los tramos
  posteriores al inicio de la hora punta son más lentos, y las llegadas tardías cuestan `late_cost` veces lo que el
  tiempo de furgoneta.

## Referencia y línea base

La **referencia** (`_plan`) construye las rutas por inserción factible más barata (primero las cafeterías asociadas
cuando se aplica la cadena de frío, luego por categoría, de mayor a menor) y, cuando la construcción voraz se queda
sin salida, reintenta con V4 iniciada con cada orden viable de las cafeterías asociadas y después con órdenes de
inserción barajados; además parte del plan de respaldo del nivel sin la cafetería cerrada. Cada punto de partida se
mejora reubicando paradas sueltas; el más barato de los dos, además, con 300 rondas de destrucción y reconstrucción
(ruin and recreate: se sacan 2–4 cafeterías vecinas o al azar y se vuelven a insertar por inserción más barata), y
cada ruta recibe su mejor hora de salida en una cuadrícula de 5 minutos. Se calcula una vez por mundo y valores de
las reglas.

La **línea base** (`baseline_solution`) es el plan del propio coordinador de reparto sin un ingeniero: cuando se
aplica la cadena de frío, V4 se encarga de las cafeterías asociadas (premium primero, en el orden que la hace volver
antes); las demás cafeterías se toman por acimut alrededor de la cocina, empezando por el oeste, y se cargan en V1,
V2, V3 y luego V4 hasta que la siguiente ya no cabe (el límite de bandejas de esta semana, la vuelta como muy tarde al fin
del turno); cada furgoneta atiende primero sus cafeterías premium y después el resto por orden de apertura; todas salen a
las 05:00 (en hard, V2 a las 06:40), cuando empieza el turno, y se ignora `deliver_by`. Si sobra alguna cafetería, el
barrido vuelve a empezar desde la siguiente cafetería de la vuelta; si ningún punto de partida funciona, se recorren
las rutas del plan de respaldo del nivel con cada furgoneta saliendo lo antes posible (siempre válido; no ha hecho
falta hasta ahora).

Las rutas de las configuraciones de la combinación principal con la semilla del caso:

| Configuración | Plan | Objetivo |
|---|---|---|
| referencia de medium/s5 | V1 05:50 C01 C07 C09 · V2 06:05 C08 C12 C15 C02 · V3 06:05 C13 C14 C17 C03 C18 C06 · V4 06:00 C10 C04 C16 C05 | 626.50 (557.97 min de ruta, 22.84 de retraso) |
| línea base de medium/s5 | V1 C01 C03 C09 C17 C06 C18 · V2 C13 C04 C07 C14 C12 C15 C02 · V3 C08 · V4 C10 C16 C05, todas a las 05:00 | 1,977.71 (859.59, 372.71 de retraso) |
| referencia de hard/s5 | V1 06:10 C04 C12 C15 C02 · V2 06:40 C08 C03 C18 C06 · V3 06:10 C13 C14 C09 C17 · V4 05:50 C10 C01 C07 C16 C05 | 709.27 (541.10, 56.06 de retraso) |
| línea base de hard/s5 | V1 C01 C03 C09 C17 C06 C18 · V2 06:40 C13 C07 C14 C15 C02 · V3 C04 C08 C12 · V4 C10 C16 C05, las demás a las 05:00 | 1,870.28 (841.89, 342.80 de retraso) |

La mayor parte del coste adicional de la línea base es espera (furgonetas en cafeterías antes de que abran) y retraso
en las cafeterías a las que llega en último lugar.

Objetivos de la referencia con las demás semillas de mundo del validador:

| Semilla de mundo | easy s5 / s13 / s58 | medium s5 / s13 / s58 | hard s5 / s13 / s58 |
|---|---|---|---|
| 1 | 469.31 / 510.62 / 468.93 | 632.60 / 557.98 / 470.66 | 671.59 / 537.13 / 540.77 |
| 2 | 448.89 / 418.55 / 452.80 | 805.19 / 452.96 / 473.96 | 1,104.65 / 431.50 / 544.96 |
| 3 | 492.71 / 496.33 / 499.92 | 634.03 / 607.11 / 601.92 | 751.63 / 597.80 / 708.56 |

Con la semilla del caso y las semillas de mundo 1–30, en todos los niveles y con las semillas de reglas 5, 13, 58 y
las privadas 101–105 (744 configuraciones), la referencia es válida, la línea base es válida y cuesta entre 1.17 y
9.76 veces lo que la referencia (mediana 3.04), y cada regla que se aplica tiene un plan que solo la incumple a ella.
`validate-case --world-seeds 1,...,20` pasa.

## Notas

- Sintético. Las posiciones, el número de bandejas, las horas de apertura, las velocidades, el tiempo de descarga y
  los pesos del retraso son inventados. En hard, la velocidad cambia a las `rush_start` también en un tramo ya
  empezado (un tramo nunca tarda menos por empezar más tarde).
- El margen de mejora sobre la referencia no se ha vuelto a medir desde las semillas de reglas (REVIEW.md, F2).
- `validate-case` comprueba todas las configuraciones públicas: la referencia con calidad 1.0, la línea base válida y
  peor, un entregable por cada regla que se aplica que solo incumple esa regla, datos deterministas en los cinco
  idiomas, que todos los parámetros influyen, la misma vista del agente en todas las configuraciones y las semillas de
  mundo 1, 2 y 3.
