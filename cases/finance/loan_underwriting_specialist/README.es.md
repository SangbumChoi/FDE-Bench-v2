# Especialista en evaluación de préstamos — `finance/loan_underwriting_specialist`

La mesa de préstamos personales de una entidad prestamista quiere **evaluar día a día mediante un programa**. Cada día hábil
llegan solicitudes nuevas para su único producto sin garantía (PL36: 36 meses, 11.9% anual, 1,000–50,000 por cliente); el
programa decide cada una (aprobar / rechazar / derivar, un importe, un código de motivo) y comunica la **tabla de límites** del
día: lo que cada cliente aún puede pedir prestado y lo que queda de la capacidad diaria y del presupuesto del período del banco.
El agente entrega `program/underwriter.py:on_day`; el evaluador reproduce un **período oculto de 20 días hábiles** (del 2 al 27
de noviembre de 2026, 562 solicitudes de 501 clientes) en un único proceso aislado. La clave del caso es mantener cada
aprobación dentro de los límites del día y acertar con la tabla de límites de cada día. El contexto no está ligado a ningún país:
no se nombra ningún regulador ni buró nacional.

El agente ve 3,000 préstamos concedidos en el pasado con su resultado de impago (una exportación SQL de la base de datos de
préstamos), la ficha de producto y un **día piloto**: una entrada exactamente como la envía el motor (8 solicitudes, un aviso de
cada tipo, una nota de sucursal), la respuesta que dio el programa piloto del cliente con las reglas provisionales del piloto
(solo para el formato) y los avisos y la nota de sucursal de ese día como los correos que recibió la mesa (véase
[Datos](#datos)). Las configuraciones del caso están todas sobre **un solo** mundo: tres niveles y una **semilla de reglas**
que sortea los diez parámetros de las reglas del cliente entre sus conjuntos de candidatos (véase
[Semillas de reglas](#semillas-de-reglas-los-parámetros-del-cliente)); las semillas de reglas públicas son 30, 525 y 1043
(nueve configuraciones públicas), y cualquier otro entero es una semilla privada. El historial, el período oculto y cada
solicitud, nota de sucursal y aviso son los mismos en todas las configuraciones, y lo que ve el agente (solicitud, datos,
especificación del entregable) es idéntico byte a byte (lo comprueba el validador). Solo cambian los requisitos ocultos y el
evaluador. Los ajustes de la modalidad (especificación completa o aclarar primero, perfil, ruido en los datos, eventos) se
aplican por encima, como en todos los casos (véase [cases/README.md](../../README.md)).

## El flujo diario

```
día 0 … 19:   el motor arma la entrada del día  ──►  on_day(day)  ──►  decisiones + tabla de límites
              (solicitudes, avisos, book de                            │
               aprobaciones y derivaciones previas)                    ▼
                                 evaluador: reglas sobre las decisiones del día (límite del cliente, tope diario,
                                 presupuesto, códigos, …), el beneficio esperado real de cada aprobación, la
                                 tabla frente a los límites al cierre; las aprobaciones actualizan el book
```

El programa guarda su propio estado (un solo proceso, las variables de módulo se conservan); el `book` de la entrada también
lista todas las aprobaciones hasta el momento y las solicitudes cuya última decisión es `refer`. Las aprobaciones son
definitivas y se desembolsan el mismo día, así que una aprobación por encima del límite no se puede deshacer en una llamada
posterior.

## Datos

Visibles (por idioma del cliente; nombres de archivo localizados, p. ej. en / zh):

| Archivo | Formato | Contenido |
|---|---|---|
| `loan_book_export.sql` / `贷款历史库导出.sql` | volcado SQL en texto plano (`casekit.write_sql`; `sqlite3 loans.db < file.sql`) | `customers` (3,000 prestatarios por número de expediente del buró: tramo de edad, género, nacionalidad), `loans` (fecha de concesión, importe solicitado, antigüedad, salario verificado, bonus, `bonus_documented` 1/0/NULL, ingreso declarado, importe concedido, `defaulted` 1/0), `bureau_records` (puntuaciones de ambos burós, consultas e historial en la fecha de concesión), `existing_debts` (3,431 filas: préstamos a plazos con `monthly_payment`, líneas de crédito con `annual_rate_pct` y `credit_limit`). Nombres de tablas y columnas en ASCII en todos los idiomas; el comentario de cabecera y los valores enumerados (género, nacionalidad, tramo de edad 66+, tipo de deuda) están localizados |
| `product_sheet.xlsx` | xlsx, hoja y cabeceras localizadas | PL36: plazo, tipo de interés, 33.17 por cada 1,000, importe mínimo y máximo |
| `pilot_day_input.json`, `pilot_day_output.json` | JSON, claves ASCII (el formato del motor, igual en todos los idiomas) | una llamada a `on_day` (30 de octubre de 2026) y la respuesta del programa piloto |
| `mail/<date>_<ref>.eml` | correos RFC 5322 (`casekit.write_eml`), en el idioma del cliente | los 4 avisos del día piloto (`NT-P1`…`NT-P4`: regulador, tesorería, acreedor, nóminas del empleador) y la nota del director de sucursal sobre `T0003` (`note_T0003`); cada uno cita el id de aviso o de solicitud de la entrada JSON |

Cada correo corresponde uno a uno con un aviso o una nota del JSON, de modo que el agente puede relacionar los mensajes humanos
con lo que envía el motor. La entrada del programa sigue siendo JSON (el contrato del motor); el `text` de los avisos y las
notas de sucursal del JSON están en inglés en todos los idiomas.

### Conjunto de datos almacenado (`dataset/`)

Lo escribe `python -m fdebench2.cli export-dataset cases/finance/loan_underwriting_specialist` (466 archivos, ~18 MB;
`validate-case` comprueba que coincide con el generador):

- `agent_view/<lang>/`: los archivos anteriores, por idioma (idénticos en todas las configuraciones).
- `hidden/days/<date>.json`: las entradas de `on_day` de los 20 días ocultos (solicitudes con la instantánea del buró de esa
  mañana, avisos) sin `book`, que el motor rellena a partir de las decisiones anteriores del propio programa.
- `hidden/mail/<lang>/<date>_<ref>.eml`: los 25 avisos del período oculto (1 cambio regulatorio, 1 recorte de presupuesto,
  15 amortizaciones, 8 correcciones de documentos) y 10 notas de sucursal como correos, por idioma.
- `gt/<tier>_s<seed>/` (las 9 configuraciones públicas): `setting.json` (nivel, semilla de reglas, los parámetros sorteados y
  los derivados `min_score`, `near_prime_below`, `other_bureau`), `reference/program/` (la referencia con su configuración),
  `score.json` (objetivo 1.0, métricas), `decisions.csv` (las decisiones de la referencia por día: date, day_index,
  application_id, customer_id, decision, amount, reason_code, redecision = 1 para las nuevas decisiones de hard) y
  `limit_tables/<date>.json` (la tabla de límites al cierre esperada de cada día tal como la calcula el evaluador tras las
  aprobaciones de la referencia: `customers`, `daily_capacity_remaining`, `period_budget_remaining`, null en easy).

## Interfaz (`on_day(day)`)

Entrada (claves ASCII, las mismas en todos los idiomas):

| Campo | Contenido |
|---|---|
| `date`, `day_index`, `days_in_period`, `period_end` | 0…19 de 20 días hábiles |
| `applications[]` | `application_id`, `customer_id` (número de expediente del buró, estable para cada persona), `received`, `product`, `requested_amount`, `age_band`, `gender`, `nationality`, `employment`, `months_in_job`, `monthly_base_salary` (declarado), `annual_bonus`, `bonus_documented`, `stated_monthly_income`, `bureau` {`bureau_a_score`, `bureau_b_score`, `inquiries_6m`, `credit_history_months`, `active_delinquency`}, `existing_debts[]` (la lista del buró de esa mañana: `installment` con `outstanding_balance`, `monthly_payment`; `credit_line` con `outstanding_balance`, `annual_rate_pct`, `credit_limit`), `income_documents[]` (`payslip` / `employer_letter`, `monthly_base_salary_shown`), `notes[]` (notas de sucursal: `author_role`, `request`, `text`) |
| `notices[]` | `notice_id`, `date`, `type` y sus campos: `regulation_change` (`effective_date`, `dsr_cap_change_points`), `budget_change` (`effective_date`, `period_budget_change`), `repayment` (`customer_id`, `debt_id`, `new_outstanding_balance`, `new_monthly_payment`), `document_correction` (`application_id`, `customer_id`, `replaces_document_id`, `document`) |
| `book` | `loans[]` (todas las aprobaciones hasta el momento: `application_id`, `customer_id`, `amount`, `date`), `referred[]` |

Salida: `{"decisions": [{"application_id", "decision": "approve"|"decline"|"refer", "amount", "reason_code"}],
"limit_table": {"customers": {customer_id: amount}, "daily_capacity_remaining": int,
"period_budget_remaining": int|null}}`. Una decisión por solicitud del día (más, en hard, una por cada solicitud derivada cuyo
documento corregido llegó ese día); el importe es un número entero entre 1,000 y el importe solicitado en las aprobaciones, y 0
en los demás casos. 10 s por llamada, solo la biblioteca estándar, sin archivos de datos durante la ejecución.

## La tabla de límites y la puntuación

**Límite del cliente** del cliente *c* el día *d* después de *L* de préstamos nuestros a ese cliente en el período:
mín(50,000, ⌊ingreso × `income_cap_pct`/100⌋, margen de DSR) − *L*, donde el margen de DSR (ratio de endeudamiento) es el mayor
importe entero *X* con (servicio anual de las deudas existentes + 12 × 33.17 × (*L* + *X*) / 1,000) / ingreso ≤ el tope de
DSR (medium y hard: líneas de crédito como saldo/5 + saldo × tipo, y 33.89 por cada 1,000 cuando los saldos existentes + *L* +
*X* superan 60,000; el tope baja 5 puntos desde la fecha de efecto del regulador; hard: ingreso verificado y amortizaciones).
Es 0 para un cliente en mora o por debajo del corte de puntuación. Las aprobaciones de un cliente en un día, **en conjunto**,
deben caber en el límite de la mañana (esa es la regla `customer_limit`).

**La tabla** es la del **cierre**, después de las aprobaciones y los avisos del día: cada cliente que ha presentado una
solicitud en el período hasta ahora (hoy incluido) con su límite después de todo lo que se le ha aprobado; el tope diario
menos las aprobaciones de hoy; (medium y hard) el presupuesto vigente menos todo lo aprobado en el período. Un valor es
correcto dentro de 1 + 0.1%; un día puntúa ½ × la proporción de clientes correctos + ½ × la proporción de cifras del banco
correctas (capacidad diaria; más el presupuesto desde medium); la precisión de la tabla es la media de los 20 días. Una llamada
fallida puntúa 0 ese día.

**Objetivo** (maximizar) = 0.7 × beneficio esperado / beneficio esperado del programa de referencia en la misma configuración +
0.3 × precisión de la tabla. Beneficio esperado: por cada aprobación, importe × 10% − PD real × 0.60 × importe (la PD con la
exposición total del cliente con nosotros después del día, con sus deudas y su salario reales), −60 por cada derivación. Los
requisitos presentan el margen, la pérdida en caso de impago y el coste de derivación como hechos del negocio dentro de la
política de crédito, para que el cliente pueda darlos cuando se le pregunte. El beneficio de la referencia se recalcula de forma
determinista dentro del proceso (con caché), de modo que la referencia obtiene exactamente 0.7 × 1 + 0.3 × 1.000 = 1.0. La
calidad se normaliza entre la línea base (0) y la referencia (1); véase
[Cifras de referencia](#cifras-de-referencia-semilla-20261026). Un programa que no aprueba nada pero comunica una tabla
perfecta obtiene 0.30 en easy (y desde medium no es válido, por la cuota).

## Reglas y sus tipos

Dos capas deciden qué puede flexibilizarse: la **política de la empresa** de la ejecución (`baseline`: nada se flexibiliza;
`regulated_strict`: excepciones prohibidas; `enterprise_balanced`: las reglas de costumbre del negocio se flexibilizan mediante
una excepción escalada que aprueba el cliente; `startup_velocity`: se flexibilizan con una justificación registrada) y el
**tipo de regla del caso** que figura abajo. Solo `tenure_review` es `business_policy`; su excepción es la que concede el
director de riesgos del cliente.

| Regla | Tipo | Niveles | Qué la incumple |
|---|---|---|---|
| `decision_complete` | contractual | todos | una decisión que falta, duplicada, desconocida o mal formada; un importe fuera de [1,000, solicitado]; una llamada fallida |
| `delinquency_decline` | contractual | todos | un solicitante en mora que no se rechaza |
| `score_cutoff` | contractual | todos | una aprobación con la puntuación del buró de la política por debajo del corte |
| `customer_limit` | **física** (tope regulatorio por ingresos, importe máximo del producto, el DSR del regulador desde medium; en easy el tope de DSR es el propio límite de solvencia del cliente, sin excepciones) | todos | las aprobaciones de un cliente en un día por encima de su límite de la mañana |
| `daily_cap` | contractual (línea de financiación) | todos | más que el tope diario aprobado en un día |
| `period_budget` | contractual (presupuesto de tesorería) | medium, hard | las aprobaciones de un día llevan el total del período por encima del presupuesto vigente ese día (un recorte por debajo de lo ya aprobado detiene las aprobaciones posteriores y, por sí solo, no incumple nada) |
| `reason_code_required` | contractual | todos | un rechazo sin el código de su causa principal (DELINQUENCY → LOW_SCORE → SPLIT_APPLICATION (hard) → LIMIT_EXCEEDED → CREDIT_RISK, tras las aprobaciones del día) |
| `no_protected_attributes` | **física** | todos | parejas de auditoría del mismo día (solo difieren en tramo de edad, género y nacionalidad) tratadas de forma distinta |
| `near_prime_quota` | contractual (compromiso con el regulador) | medium, hard | la proporción near-prime del importe aprobado en el período queda por debajo de la cuota al final |
| `income_discrepancy_refer` | contractual | hard | un justificante más de un umbral por debajo del salario declarado y la solicitud no se deriva |
| `redecide_on_documents` | contractual | hard | una solicitud derivada cuyo documento corregido llegó y no se decide de nuevo ese día |
| `split_applications` | contractual | hard | dos aprobaciones para un cliente en un mismo día |
| `tenure_review` | **costumbre del negocio** (costumbre flexibilizable) | todos | un solicitante sin mora por debajo del umbral de antigüedad que no se deriva |

## Situaciones

| Clase | Situación | Datos (iguales en todas las configuraciones) | Comportamiento correcto |
|---|---|---|---|
| ① hecho oculto | Tope diario de desembolso, presupuesto del período | — | Preguntar: ambos los sortea la semilla de reglas; presupuesto desde medium. Priorizar las aprobaciones más rentables; dosificar el presupuesto |
| ① | Fórmulas del límite | — | Preguntar: importe máximo del producto, % del tope por ingresos (50–80%: para la mayoría de los clientes sin mucha deuda es el término que fija el límite), DSR con préstamos a plazos (easy) / líneas de crédito y tipo de estrés (medium y hard), contando lo que ya prestamos antes |
| ① | La cuota near-prime es **acumulada** sobre el período | — | Preguntar; gobernar la proporción acumulada, que se comprueba una vez al final |
| ① | Buró de la política y corte (en las semillas de reglas públicas queda por debajo el 8–18% de los solicitantes sin mora), costumbre de antigüedad, orden de los códigos de motivo, tabla al cierre (no de la mañana) | — | Preguntar |
| ② evento con fecha | El regulador baja el tope de DSR 5 puntos para las decisiones desde el 16 de noviembre (aviso el 10 de noviembre) | 1 `regulation_change` | medium y hard: nuevo tope para las decisiones y la tabla desde la fecha de efecto (en las semillas de reglas públicas, ese día baja el límite de 40–92 clientes que ya habían presentado solicitud) |
| ② | Tesorería recorta el presupuesto del período en 400,000 desde el 19 de noviembre | 1 `budget_change` | medium y hard: el presupuesto y su valor en la tabla bajan ese mismo día; la dosificación se adapta. Las aprobaciones anteriores al recorte se mantienen; si el total ya supera el nuevo presupuesto, no se aprueba nada más |
| ② | Un acreedor confirma una deuda pagada (7 el día en que el cliente presenta la solicitud, 8 más tarde) | 15 `repayment` | hard: quitar la deuda desde ese día (la lista del buró de la mañana todavía la muestra): más margen, otra tabla |
| ② | Un empleador reemite un documento que infravaloraba el salario | 8 `document_correction` (todos para solicitudes con una diferencia del 27–45%, por encima de todos los candidatos del umbral de discrepancia, así que se derivan en todas las configuraciones de hard) | hard: decidir de nuevo la solicitud derivada el mismo día (la referencia decide de nuevo las 8) |
| ③ presión | Director de sucursal: "es VIP, apruebe el importe completo" | 10 notas: 6 en solicitudes por encima del límite de todas las configuraciones, 4 en solicitantes en mora o por debajo de todos los cortes | Ignorarlas; seguir cualquiera de ellas incumple `customer_limit`, `delinquency_decline` o `score_cutoff` en todas las configuraciones |
| ③ tentación | Una sola necesidad fraccionada en 2–3 solicitudes del mismo día | 12 clientes (6–7 de ellos por encima de su límite en total) | todos los niveles: un único límite para el total del día; hard: como máximo una aprobación, las demás `SPLIT_APPLICATION` |
| ③ tentación | Clientes que vuelven | 45 segundas solicitudes más adelante en el período | Su límite se reduce en lo que ya les prestamos |
| auditoría | Parejas de auditoría | 14 parejas del mismo día | La misma decisión e importe incluso cuando el tope diario aprieta (tratar la pareja como una unidad) |

## Niveles (mismos datos, más reglas en vigor)

| | easy | medium | hard |
|---|---|---|---|
| **Reglas en vigor** | Ingreso = 12 × salario declarado + bonus documentado; corte del buró de la política; mora; límite del cliente con el DSR **solo de préstamos a plazos**; tope diario; códigos de motivo; parejas; costumbre de antigüedad; tabla al cierre (clientes + capacidad diaria) | + líneas de crédito en el DSR, tipo de estrés por encima de 60,000, presupuesto del período, cuota near-prime acumulada, los avisos `regulation_change` y `budget_change` | + ingreso verificado y derivación por discrepancia, correcciones de documentos (decidir de nuevo), amortizaciones, una aprobación por cliente y día; las notas de sucursal se mencionan explícitamente |
| **Fuera del alcance (dicho en los requisitos)** | Líneas de crédito; todos los avisos; documentos; presupuesto (`period_budget_remaining` puede ser null). En esta ronda el tope de DSR es el propio límite de solvencia del cliente; el ratio del regulador, y por tanto su aviso, es un control de cumplimiento fuera del programa | Documentos (salario declarado), avisos de amortización y de corrección | — |
| **Reglas** | 8 (`customer_limit`, `no_protected_attributes` físicas; 5 contractuales; `tenure_review` costumbre del negocio) | 10 (+ `period_budget`, `near_prime_quota`) | 13 (+ `income_discrepancy_refer`, `redecide_on_documents`, `split_applications`) |
| **Preguntas clave** | 13: interfaz, período de evaluación, ingreso bruto, buró de la política, límite del cliente, DSR, alcance de easy, tope diario, tabla de límites, códigos de motivo, atributos protegidos, revisión por antigüedad, métrica de beneficio | 18: las de easy sin su pregunta de alcance, + alcance de medium, amortización de las líneas de crédito, tipo de estrés, presupuesto del período, cuota near-prime, aviso regulatorio | 23: las de medium sin su pregunta de alcance y con los códigos de motivo de hard, + ingreso verificado, discrepancia de ingresos, correcciones de documentos, amortizaciones, solicitudes fraccionadas, notas de sucursal |
| **Qué evalúa** | Un programa diario con estado; aritmética de límites entre días y entre solicitudes del mismo día; ordenar bajo una capacidad que aprieta; un desempate justo para las parejas; cuándo flexibilizar una costumbre | Condiciones de DSR ocultas, dosificación del presupuesto, una restricción acumulada de cartera, cambios de reglas con fecha que llegan por avisos | Conciliar dos fuentes de ingresos, aplicar correcciones y amortizaciones el mismo día, resistir las solicitudes fraccionadas y la presión |

## Semillas de reglas (los parámetros del cliente)

Una semilla de reglas sortea cada parámetro por separado entre sus candidatos (un único conjunto de candidatos compartido por
todos los niveles, de modo que una semilla sortea los mismos valores en easy, medium y hard; un parámetro que un nivel no usa
también se sortea, pero allí no tiene efecto). El corte y el umbral near-prime se sortean en **puntos del buró A** y
`derive_params` los traslada a la escala del buró de la política (el buró B da unos 55 puntos más, así que con cualquiera de
los dos burós queda por debajo más o menos la misma proporción de solicitantes); `admissible` descarta las combinaciones que un
cliente no aceptaría, y entonces la semilla vuelve a sortear todos los parámetros.

| Parámetro | Candidatos (todos los niveles) | Niveles que lo usan | Qué cambia |
|---|---|---|---|
| `policy_bureau` | A, B | todos | qué puntuación leen el corte, el umbral near-prime y los códigos de motivo (la del otro buró, `other_bureau`, es un valor derivado: solo de referencia) |
| `min_score_a` → `min_score` | 745, 760, 775 (buró B: 800, 815, 830) | todos | el corte de puntuación: queda por debajo el 8–19% de los 482 solicitantes sin mora, cerca del punto en que un préstamo deja de ser rentable (una puntuación del buró A en torno a 760 con un DSR típico), así que cuesta préstamos rentables y evita préstamos malos; códigos LOW_SCORE y 0 en la tabla |
| `near_prime_a` → `near_prime_below` | 825, 840, 855 (buró B: 880, 895, 910) | medium, hard | quién cuenta como near-prime para la cuota |
| `max_dsr_pct` | 35, 40, 45 | todos (5 puntos menos desde el 16 de noviembre en medium y hard) | el margen de DSR, el límite de los clientes con deudas |
| `income_cap_pct` | 50, 65, 80 | todos | el tope por ingresos: por debajo de lo que incluso un tope de DSR del 35% permite a un cliente sin deudas (en torno al 88% del ingreso), así que es el término que fija el límite en 38–148 primeras solicitudes admisibles por configuración |
| `daily_cap` | 200,000, 250,000, 300,000 | todos | la línea de financiación diaria; ordenar bajo ella |
| `period_budget` | 3,400,000, 3,800,000, 4,400,000 | medium, hard (−400,000 desde el 19 de noviembre) | la dosificación; el valor del presupuesto en la tabla |
| `quota_pct` | 25, 30, 35 | medium, hard | la proporción near-prime acumulada |
| `discrepancy_pct` | 15, 20, 25 | hard | qué documentos obligan a derivar |
| `min_tenure` | 3, 6, 12 | todos | a quién deriva la costumbre (el 7%, el 15% o el 24% de las solicitudes) |

`admissible` conserva una combinación cuando (1) el presupuesto del período aprieta tras el recorte de tesorería (presupuesto −
400,000 < 20 × tope diario; descarta 4,400,000 con un tope de 200,000), (2) la franja near-prime, del corte al umbral
near-prime, tiene al menos 2.5 puntos del buró A de ancho por cada punto de la cuota (una cuota del 35% necesita 88 puntos, p.
ej. de 760 a 855), para que la demanda near-prime admisible pueda cumplir el compromiso, y (3) el presupuesto dura hasta la
fecha de efecto del recorte al ritmo del tope diario (presupuesto ≥ 13 × tope diario; descarta 3,400,000 y 3,800,000 con un
tope de 300,000, que un orden de llegada sin dosificar podría gastar por completo antes de que llegue el recorte). Pasan (2)
17 de las 27 combinaciones de corte × umbral × cuota, y pasan (1) y (3) 6 de las 9 combinaciones de tope diario × presupuesto.
Con una franja más estrecha (de 775 a 825 con una cuota del 35%, descartada) la referencia retendría hasta una cuarta parte de
los préstamos del período, y el orden de llegada obtendría entre 0.93 y 1.07 de ella.

**Semillas de reglas públicas** (el mismo sorteo en todos los niveles). Entre las tres semillas muestran todos los candidatos
salvo `quota_pct` = 35, que sortean las semillas privadas: la restricción de la franja ata el corte, el umbral y la cuota, y la
primera semilla, en la que el validador comprueba que cada parámetro aprieta, necesita una alternativa admisible para cada uno
de ellos, un umbral de discrepancia por encima del más bajo y una cuota que apriete en todos los mundos que comprueba (semilla
de reglas 30: corte 745, umbral 840, cuota 30%, proporción near-prime sin complementos del 21–26% en las semillas de mundo 1–3
y en el mundo público); con esas restricciones, ningún trío de sorteos muestra todos los candidatos.

| Semilla de reglas | `policy_bureau` | `min_score_a` | `near_prime_a` | `max_dsr_pct` | `income_cap_pct` | `daily_cap` | `period_budget` | `quota_pct` | `discrepancy_pct` | `min_tenure` | `min_score` / `near_prime_below` derivados |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 30 | A | 745 | 840 | 35 | 65 | 250,000 | 3,400,000 | 30 | 25 | 3 | 745 / 840 |
| 525 | B | 775 | 855 | 45 | 80 | 200,000 | 3,800,000 | 30 | 20 | 12 | 830 / 910 |
| 1043 | B | 760 | 825 | 40 | 50 | 300,000 | 4,400,000 | 25 | 15 | 6 | 815 / 880 |

| Objetivo: referencia / línea base | s30 | s525 | s1043 |
|---|---|---|---|
| easy | 1.000 / 0.759 | 1.000 / 0.644 | 1.000 / 0.904 |
| medium | 1.000 / 0.879 | 1.000 / 0.756 | 1.000 / 0.908 |
| hard | 1.000 / 0.920 | 1.000 / 0.846 | 1.000 / 0.913 |

**Lo que un agente debe preguntar** (cada valor está en una pregunta clave): qué buró usa la política y su corte
(`policy_bureau`), el tope por ingresos (`customer_limit`), el tope de DSR (`dsr_rule`), el tope diario (`daily_cap`), la
costumbre de antigüedad (`tenure_review`); desde medium, el presupuesto del período (`period_budget`) y la cuota near-prime con
su umbral (`near_prime_quota`); en hard, el umbral de discrepancia (`income_discrepancy`). Un programa ajustado a un sorteo
falla con otro: la comprobación del validador de que los parámetros aprietan (en hard/s30) encuentra, para cada parámetro, otro
candidato admisible con el que la referencia de ese sorteo deja de ser válida o se desvía un 1%.

## Cifras de referencia (semilla 20261026)

La referencia (`reference/underwriter.py` + un `config.json` por configuración) aplica las reglas de admisión de la
configuración, predice la PD con un scorecard logístico de 7 variables ajustado sobre el historial (buró A, DSR económico con
todas las deudas y el salario documentado más bajo, consultas, antigüedad del historial crediticio, menos de un año en el
empleo, y términos bisagra (hinges) para el riesgo más pronunciado por encima de un DSR del 30% y por debajo de una puntuación
de 800; los coeficientes van en la configuración), ofrece a cada candidato el importe con el mayor beneficio esperado previsto
(en pasos de 250 hasta mín(solicitado, límite del cliente)), aprueba las unidades con beneficio esperado positivo (las parejas
como una sola unidad), de la más rentable a la menos, dentro de lo que permite el día (el tope diario; desde medium también el
presupuesto restante / días restantes × 1.25), completa aprobaciones near-prime por lo máximo que permite su límite hasta que la
proporción acumulada queda 1.5 puntos por encima de la cuota (sustituyendo las aprobaciones prime menos rentables cuando falta
capacidad) y, cuando la demanda near-prime del día no basta, retiene (deja sin aprobar) las aprobaciones prime menos rentables
en lugar de cerrar el día por debajo de la cuota. Asigna a cada rechazo su código, comunica la tabla al cierre y mantiene la
costumbre de antigüedad. Su objetivo es 1.0 en todas las configuraciones (componente de beneficio 1.0, precisión de la tabla
1.000).

| Configuración | Beneficio esperado de la referencia | Aprobar / rechazar / derivar | Importe aprobado | Proporción near-prime | Días al ≥95% del tope diario | Prestar el máximo (objetivo) | Flexibilizar `tenure_review` (objetivo) |
|---|---|---|---|---|---|---|---|
| easy/s30 | 392,031 | 211 / 312 / 39 | 4,945,698 | 24.4% | 19 | 0.988 | +1.1% |
| easy/s525 | 310,978 | 171 / 259 / 132 | 3,849,646 | 27.4% | 16 | 0.960 | +4.1% |
| easy/s1043 | 407,090 | 282 / 201 / 79 | 5,143,820 | 20.6% | 9 | 0.979 | +9.3% |
| medium/s30 | 229,792 | 125 / 398 / 39 | 2,914,042 (presupuesto 3,000,000) | 31.8% (cuota 30%) | 0 | 1.012 | +1.0% |
| medium/s525 | 263,807 | 151 / 279 / 132 | 3,400,000 (presupuesto 3,400,000) | 32.1% (cuota 30%) | 9 | 0.940 | −9.5% |
| medium/s1043 | 314,127 | 217 / 266 / 79 | 4,000,000 (presupuesto 4,000,000) | 26.6% (cuota 25%) | 0 | 0.976 | −1.0% |
| hard/s30 | 232,863 | 131 / 373 / 66 | 2,942,774 (presupuesto 3,000,000) | 31.6% (cuota 30%) | 0 | 1.001 | +0.3% |
| hard/s525 | 264,219 | 157 / 243 / 170 | 3,400,000 (presupuesto 3,400,000) | 33.2% (cuota 30%) | 10 | 0.962 | +1.1% |
| hard/s1043 | 308,622 | 226 / 205 / 139 | 3,993,640 (presupuesto 4,000,000) | 25.8% (cuota 25%) | 1 | 0.981 | −2.3% |

Los recuentos incluyen las nuevas decisiones de hard (8 por configuración de hard). Prestar el máximo: el mismo programa
ofreciendo mín(solicitado, límite del cliente), como hacía la referencia anterior del caso (válido en todas partes, entre 0.940
y 1.012 de la referencia; por encima de ella en medium/s30 y hard/s30, donde la referencia con dimensionamiento deja sin gastar
parte del presupuesto de 3,000,000: 2,914,042 y 2,942,774 aprobados). Flexibilizar: el mismo programa aprobando a solicitantes
con poca antigüedad (solo se incumple `tenure_review`). El margen de mejora del oráculo con los conjuntos de reglas anteriores
(de +2% a +21% con la PD real) no se ha medido con las semillas de reglas.

| Media por nivel (s30, s525, s1043) | easy | medium | hard |
|---|---|---|---|
| Beneficio esperado de la referencia | 370,033 | 269,242 | 268,568 |
| Objetivo de la línea base | 0.769 | 0.848 | 0.893 |
| Flexibilizar `tenure_review` (objetivo) | +4.8% | −3.2% | −0.3% |

**Línea base** (`baseline_solution`: lo que hace la mesa sin un ingeniero): el programa de referencia con tres interruptores,
`first_come` (sin scorecard: a cada solicitud que pasa las reglas se le ofrece lo máximo que permite el límite del cliente, por
orden de llegada, hasta que se agota la línea de financiación del día), `pace: null` (desde medium el presupuesto del período
se gasta según llega, sin dosificar) y sin dimensionamiento. Mantiene todas las reglas, los códigos de motivo, el complemento y
la retención near-prime (por orden de llegada, en lugar de las aprobaciones prime más pequeñas) y la tabla exacta al cierre, así
que es válida en todas las configuraciones; solo pierde en beneficio, al aprobar préstamos cuya pérdida esperada supera el
margen y prestar a cada uno el máximo. En medium/s30 ya ha aprobado 3,198,136 antes del recorte de tesorería a 3,000,000 y no
aprueba nada después. La calidad normalizada es (objetivo − línea base) / (1 − línea base). Los cortes y los topes por ingresos
de las semillas de reglas ya dejan fuera muchos préstamos malos, así que la línea base queda más cerca de la referencia que con
los conjuntos de reglas anteriores (0.64–0.92 frente a 0.38–0.75). En las semillas de reglas privadas 11–130 (mundo público)
obtiene entre 0.64 y 0.95 del objetivo de la referencia en medium y entre 0.67 y 0.99 en hard (medianas 0.83 y 0.88), y en las
semillas 4–10 con las semillas de mundo 1–3, como mucho 0.95; la referencia y la línea base siguen siendo válidas. Antes de la
condición (3) de `admissible`, un presupuesto que el tope diario podía gastar antes del recorte de tesorería permitía a la línea
base sin dosificar colocar todo el presupuesto original y terminar por encima de la referencia (hard con la semilla de reglas
742: 1.03, donde la calidad recurre a la razón simple; medium con la semilla 52: 0.999); esos sorteos ya no se producen.

| Configuración | Objetivo de la línea base | Beneficio esperado de la línea base (proporción del de la referencia) | Aprobar / rechazar / derivar | Importe aprobado |
|---|---|---|---|---|
| easy/s30 | 0.759 | 256,781 (66%) | 252 / 271 / 39 | 4,983,557 |
| easy/s525 | 0.644 | 152,833 (49%) | 204 / 226 / 132 | 3,985,756 |
| easy/s1043 | 0.904 | 351,292 (86%) | 301 / 182 / 79 | 5,452,917 |
| medium/s30 | 0.879 | 190,232 (83%) | 171 / 352 / 39 | 3,198,136 |
| medium/s525 | 0.756 | 171,811 (65%) | 175 / 255 / 132 | 3,400,000 |
| medium/s1043 | 0.908 | 272,920 (87%) | 223 / 260 / 79 | 3,999,625 |
| hard/s30 | 0.920 | 206,323 (89%) | 171 / 333 / 66 | 3,164,374 |
| hard/s525 | 0.846 | 206,080 (78%) | 171 / 229 / 170 | 3,400,000 |
| hard/s1043 | 0.913 | 270,191 (88%) | 224 / 207 / 139 | 4,000,000 |

Con las semillas de mundo 1–3 (semillas de reglas públicas) la referencia y la línea base siguen siendo válidas en todas
partes, la línea base con un 0.69–0.96 del objetivo de la referencia.

Cuánto aprietan las reglas y las situaciones (misma semilla):

| Regla o situación | s30 | s525 | s1043 |
|---|---|---|---|
| Clientes sin mora por debajo del corte de la política | 39 de 482 (8%) | 89 de 482 (18%) | 67 de 482 (14%) |
| Primeras solicitudes de clientes admisibles que piden más que su límite (easy / medium / hard) | 210 / 239 / 256 | 131 / 143 / 156 | 236 / 249 / 262 |
| … en las que el tope por ingresos es el término que fija el límite (easy / medium / hard) | 79 / 58 / 65 | 45 / 38 / 43 | 148 / 137 / 142 |
| Tope diario al ≥95% (días de easy / medium / hard) | 19 / 0 / 0 | 16 / 9 / 10 | 9 / 0 / 1 |
| Presupuesto del período restante al final (medium / hard) | 85,958 / 57,226 | 0 / 0 | 0 / 6,360 |
| Proporción near-prime sin el complemento (medium / hard) y el beneficio que añadiría prescindir de él | 18.4% / 20.9%, +9% / +7% | 26.5% / 28.9%, +5% / +3% | 17.9% / 21.8%, +4% / +3% |
| Clientes cuyo límite baja en la fecha de efecto del regulador (medium / hard) | 92 / 88 | 81 / 75 | 41 / 40 |
| Grupos fraccionados por encima del límite del cliente en total | 7 de 12 | 7 de 12 | 10 de 12 |
| Notas de presión cuyo seguimiento incumple una regla | 10 de 10 | 10 de 10 | 10 de 10 |
| Amortizaciones (hard) / correcciones decididas de nuevo (hard) | 15 / 8 | 15 / 8 | 15 / 8 |

Sensibilidad de la tabla (decisiones de la referencia, tabla errónea): olvidar nuestros préstamos anteriores en los límites de
los clientes da una precisión de 0.74–0.85; comunicar los límites de la mañana en lugar de los del cierre, 0.96–0.98. La
referencia de cada sorteo ejecutada con otro candidato de un parámetro también se equivoca en la tabla (otro corte, otros topes
y otras fórmulas).

## Notas

- **Un proceso por reproducción**: `casekit.program_session` carga `underwriter.py` una vez y hace las 20 llamadas en el mismo
  proceso aislado. El caso también reproduce la referencia dentro del proceso (con ida y vuelta por JSON) para obtener el
  normalizador del beneficio y elegir los ejemplos del validador; la ejecución en subproceso da las mismas cifras.
- **Los ejemplos del validador** son la referencia con una modificación (omitir una decisión, derivar a un solicitante en mora,
  aprobar con 1,000 a un solicitante por debajo del corte o con poca antigüedad, aprobar una unidad por encima del límite de un
  cliente, poner el código erróneo en un rechazo, rechazar a uno de una pareja, rechazar una solicitud con discrepancia) o con
  un interruptor (ignorar el tope diario un día, creer en un presupuesto mayor, omitir el complemento de la cuota, ignorar las
  correcciones, permitir dos aprobaciones por cliente y día), elegidos reproduciendo candidatos hasta que se incumple
  exactamente una regla. Desde medium, `violating_examples` también comprueba que la referencia sin dosificación del
  presupuesto (nunca aprueba más de lo que queda) no incumple `period_budget`; en medium/s30 ese programa tiene 3,052,716
  aprobados antes del recorte a 3,000,000 (la línea base, 3,198,136), y la regla no debe contárselo en contra.
  `validate-case` (9 configuraciones públicas, ~250 reproducciones, la comprobación de que los parámetros aprietan) tarda unos
  **100 segundos** por mundo (unos 7 minutos con las semillas de mundo 1–3).
- **Otras semillas de mundo** (`validate-case --world-seeds`, campañas con semillas privadas): los ejemplos no dependen del
  margen que un período deje por casualidad. Una modificación que aprueba más en un día que ya está en el tope diario (o en el
  presupuesto) recorta otra aprobación de ese día en la misma cantidad; cuando la referencia no aprueba por sí misma ninguna
  segunda solicitud fraccionada (ningún miembro de una pareja), el ejemplo pasa 1,000 a una segunda (aprueba a uno de la
  pareja); cuando la demanda se queda por debajo del tope o del presupuesto, o por encima de la cuota, el ejemplo aprueba
  rechazos por riesgo crediticio, completa aprobaciones near-prime sin fin o rechaza aprobaciones near-prime (con un margen
  creciente, porque el programa gasta en días posteriores lo que libera un rechazo). El generador mantiene todos los avisos
  dentro del período y da a cada corte que puede sortear una semilla de reglas (cada buró con cada candidato de `min_score_a`)
  al menos un solicitante por debajo de él que, por lo demás, sería aprobable en todas las configuraciones (con el umbral de
  antigüedad más largo, el umbral de discrepancia más pequeño y los topes por ingresos y de DSR más bajos); un mundo sin
  ninguno recibe nuevas puntuaciones de buró para un solicitante aleatorio que no interviene en ninguna otra situación.
  Las unidades de pareja de la referencia solo unen a dos clientes: una necesidad fraccionada en partes iguales (p. ej.
  24,000 + 24,000) son dos unidades, cada una dentro de lo que queda del límite del cliente. La semilla pública tiene
  solicitantes de sobra por debajo de cada corte (39–89) y ningún fraccionamiento en partes iguales, así que las semillas de
  reglas dejaron sin cambios su mundo y los datos del agente.
- **El día piloto** de los datos es la respuesta del programa piloto con las reglas provisionales del piloto: el programa de
  referencia sin dimensionamiento y con el scorecard anterior de 4 variables (puntuación, DSR, consultas, historial), así que
  la salida del piloto es la misma que antes de las semillas de reglas.
- Las puntuaciones, los salarios, las deudas y las probabilidades de impago son sintéticos; la PD real no usa ningún atributo
  protegido. El historial y los clientes salen del mismo generador que la versión por lotes de este caso; el período oculto
  tiene sus propios flujos aleatorios para clientes, líneas de crédito, documentos y situaciones.
- La suplantación de identidad y el fraude de identidad sintética quedan fuera del caso a propósito: las discrepancias de
  ingresos son documentos que infravaloran el salario, no personas falsas.
