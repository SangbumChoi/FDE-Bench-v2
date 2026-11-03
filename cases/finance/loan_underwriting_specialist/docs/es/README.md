# Especialista en evaluación de préstamos — `finance/loan_underwriting_specialist`

La mesa de préstamos personales de una entidad prestamista quiere **evaluar día a día mediante un programa**. Cada día hábil
llegan solicitudes nuevas para su único producto sin garantía (PL36: 36 meses, 11.9% anual, 1,000–50,000 por cliente); el
programa decide cada una (aprobar / rechazar / derivar, un importe, un código de motivo) y comunica la **tabla de límites** del
día: lo que cada cliente aún puede pedir prestado y lo que queda de la capacidad diaria y del presupuesto del período del banco.
El agente entrega `program/underwriter.py:on_day`; el evaluador reproduce un **período de evaluación de 20 días hábiles** (la IA
nunca lo recibe; del 2 al 27 de noviembre de 2026, 562 solicitudes de 501 clientes) en un único proceso aislado. La clave del
caso es mantener cada aprobación dentro de los límites del día y acertar con la tabla de límites de cada día: la tabla es una
salida obligatoria (una regla), y el objetivo es el beneficio esperado **multiplicado por** la precisión de la tabla en los
valores que cambian, así que ningún beneficio compensa una tabla equivocada. El contexto no está ligado a ningún país: no se
nombra ningún regulador ni buró nacional. Su respuesta correcta en cinco partes (hechos del cliente, comprobaciones de validez,
objetivo, referencia y cotas, comprobaciones directas), generada a partir de la auditoría guardada, está en [GT.md](../../GT.md).

El agente ve 3,000 préstamos concedidos en el pasado con su resultado de impago (una exportación SQL de la base de datos de
préstamos), la ficha de producto y un **día piloto**: una entrada exactamente como la envía el motor (8 solicitudes, un aviso de
cada tipo, una nota de sucursal), la respuesta que dio el programa piloto del cliente con las reglas provisionales del piloto
(solo para el formato) y los avisos y la nota de sucursal de ese día como los correos que recibió la mesa (véase
[Datos](#datos)). Las configuraciones del caso están todas sobre **un solo** mundo: tres niveles y una **semilla de reglas**
que sortea los diez parámetros de las reglas del cliente entre sus conjuntos de candidatos (véase
[Semillas de reglas](#semillas-de-reglas-los-parámetros-del-cliente)); las semillas de reglas públicas son 30, 525 y 1043
(nueve configuraciones públicas), y cualquier otro entero es una semilla privada. El historial, el período de evaluación y cada
solicitud, nota de sucursal y aviso son los mismos en todas las configuraciones, y lo que ve el agente (solicitud, datos,
especificación del entregable) es idéntico byte a byte (lo comprueba el validador). Solo cambian los requisitos que solo conoce
el cliente y el evaluador. Los ajustes de la modalidad (especificación completa o aclarar primero, perfil, ruido en los datos,
eventos) se aplican por encima, como en todos los casos (véase [cases/README.md](../../../../README.md)).

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

### Conjunto de datos guardado (`dataset/`)

Lo escribe `python -m fdebench2.cli export-dataset cases/finance/loan_underwriting_specialist` (466 archivos, ~18 MB;
`validate-case` comprueba que coincide con el generador):

- `agent_view/<lang>/`: los archivos anteriores, por idioma (idénticos en todas las configuraciones).
- `hidden/days/<date>.json`: las entradas de `on_day` de los 20 días de evaluación (solicitudes con la instantánea del buró de
  esa mañana, avisos) sin `book`, que el motor rellena a partir de las decisiones anteriores del propio programa.
- `hidden/mail/<lang>/<date>_<ref>.eml`: los 25 avisos del período de evaluación (1 cambio regulatorio, 1 recorte de
  presupuesto, 15 amortizaciones, 8 correcciones de documentos) y 10 notas de sucursal como correos, por idioma.
- `answer/<tier>/s<seed>/` (las 9 configuraciones públicas): `setting.json` (nivel, semilla de reglas, los parámetros sorteados y
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
*X* superan 60,000; el tope baja 5 puntos desde la fecha de entrada en vigor del regulador; hard: ingreso verificado y amortizaciones).
Es 0 para un cliente en mora o por debajo del corte de puntuación. Las aprobaciones de un cliente en un día, **en conjunto**,
deben caber en el límite de la mañana (esa es la regla `customer_limit`).

**La tabla** es la del **cierre**, después de las aprobaciones y los avisos del día: cada cliente que ha presentado una
solicitud en el período hasta ahora (hoy incluido) con su límite después de todo lo que se le ha aprobado; el tope diario
menos las aprobaciones de hoy; (medium y hard) el presupuesto vigente menos todo lo aprobado en el período. Es una **salida
obligatoria**: la tabla de un día a la que le falta un cliente o una cifra del banco incumple `limit_table_complete`. Un valor
es correcto dentro de 1 + 0.1%. Un día puntúa la proporción de valores correctos entre los valores de clientes **que cambian
ese día** (los solicitantes del día, cualquier otro cliente cuyo límite real se movió desde el día anterior: una aprobación,
una amortización, la fecha de entrada en vigor del regulador; y cualquier valor que el programa movió a un importe equivocado)
**multiplicada por** la proporción de cifras del banco correctas (capacidad diaria; más el presupuesto desde medium). Los ~500
valores estáticos no diluyen la puntuación, y un programa no puede volver a meterlos en ella moviéndolos dentro de la tolerancia
(un valor movido que sigue siendo correcto no se puntúa); las dos cifras del banco, fáciles de acertar, tampoco pueden sostener
la mitad de una tabla equivocada. La precisión de la tabla es la media de los 20 días; una llamada fallida puntúa 0 ese día.

**Objetivo** (maximizar) = beneficio esperado / beneficio esperado del programa de referencia en la misma configuración ×
precisión de la tabla (la tabla no reduce una pérdida). Beneficio esperado: por cada aprobación, importe × 10% − PD real × 0.60
× importe (la PD con la exposición total del cliente con nosotros después del día, con sus deudas y su salario reales), −60 por
cada derivación. Los requisitos presentan el margen, la pérdida en caso de impago y el coste de derivación como hechos del
negocio dentro de la política de crédito, y explican por qué la tabla multiplica: la mesa da sus cifras a los clientes a partir de ella
y tesorería financia según ella, así que lo prestado con una tabla equivocada vale menos en la misma proporción. El beneficio de la referencia
se recalcula de forma determinista dentro del proceso (con caché), de modo que la referencia obtiene exactamente 1 × 1.000 =
1.0. La calidad se normaliza entre la forma de trabajar del cliente (0) y la solución de referencia (1), con la puntuación
completa en `quality_cap` (la calidad de la mejor solución conocida); véase
[Cifras de referencia](#cifras-de-referencia-semilla-20261026). Un programa que no aprueba nada pero comunica una tabla
perfecta obtiene 0 (menos sus costes de derivación) y desde medium no es válido (por la cuota).

## Reglas y sus tipos

Dos capas deciden qué puede flexibilizarse: la **política de la empresa** de la ejecución (`baseline`: nada se flexibiliza;
`regulated_strict`: excepciones prohibidas; `enterprise_balanced`: las reglas de costumbre del negocio se flexibilizan mediante
una excepción escalada que aprueba el cliente; `startup_velocity`: se flexibilizan con una justificación registrada) y el
**tipo de regla del caso** que figura abajo. Solo `tenure_review` es `business_policy`; su excepción es la que concede el
director de riesgos del cliente.

| Regla | Tipo | Niveles | Qué la incumple |
|---|---|---|---|
| `decision_complete` | contractual | todos | una decisión que falta, duplicada, desconocida o mal formada; un importe fuera de [1,000, solicitado]; una llamada fallida |
| `limit_table_complete` | contractual (la mesa y tesorería trabajan con ella) | todos | la tabla de un día sin un valor para algún cliente que ha presentado una solicitud en el período hasta ahora, o sin la capacidad diaria restante (desde medium: el presupuesto restante) |
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
| `referral_capacity` | contractual (la capacidad de los analistas) | todos | más de 3 derivaciones en un día además de las que exige la costumbre de antigüedad (hard: y el procedimiento de discrepancia) |
| `tenure_review` | **costumbre del negocio** (costumbre flexibilizable) | todos | un solicitante sin mora por debajo del umbral de antigüedad que no se deriva |

## Situaciones

| Clase | Situación | Datos (iguales en todas las configuraciones) | Comportamiento correcto |
|---|---|---|---|
| ① hecho que solo sabe el cliente | Tope diario de desembolso, presupuesto del período | — | Preguntar: ambos los sortea la semilla de reglas; presupuesto desde medium. Priorizar las aprobaciones más rentables; dosificar el presupuesto |
| ① | Fórmulas del límite | — | Preguntar: importe máximo del producto, % del tope por ingresos (50–80%: para la mayoría de los clientes sin mucha deuda es el término que fija el límite), DSR con préstamos a plazos (easy) / líneas de crédito y tipo de estrés (medium y hard), contando lo que ya prestamos antes |
| ① | La cuota near-prime es **acumulada** sobre el período | — | Preguntar; gobernar la proporción acumulada, que se comprueba una vez al final |
| ① | Buró de la política y corte (en las semillas de reglas públicas queda por debajo el 8–18% de los solicitantes sin mora), costumbre de antigüedad, orden de los códigos de motivo, tabla al cierre (no de la mañana) | — | Preguntar |
| ② evento con fecha | El regulador baja el tope de DSR 5 puntos para las decisiones desde el 16 de noviembre (aviso el 10 de noviembre) | 1 `regulation_change` | medium y hard: nuevo tope para las decisiones y la tabla desde la fecha de entrada en vigor (en las semillas de reglas públicas, ese día baja el límite de 40–92 clientes que ya habían presentado solicitud) |
| ② | Tesorería recorta el presupuesto del período en 400,000 desde el 19 de noviembre | 1 `budget_change` | medium y hard: el presupuesto y su valor en la tabla bajan ese mismo día; la dosificación se adapta. Las aprobaciones anteriores al recorte se mantienen; si el total ya supera el nuevo presupuesto, no se aprueba nada más |
| ② | Un acreedor confirma una deuda pagada (7 el día en que el cliente presenta la solicitud, 8 más tarde) | 15 `repayment`; cada una del mismo día sube el límite del cliente de menos de 1,000 a al menos 3,000 en todas las configuraciones | hard: quitar la deuda desde ese día (la lista del buró de la mañana todavía la muestra): más margen, otra decisión y otro código, otra tabla; easy/medium: no se usan, así que el límite del cliente sigue por debajo de 1,000 (LIMIT_EXCEEDED) |
| ② | Un empleador reemite un documento que infravaloraba el salario | 8 `document_correction` (todos para solicitudes con una diferencia del 27–45%, por encima de todos los candidatos del umbral de discrepancia, así que se derivan en todas las configuraciones de hard) | hard: decidir de nuevo la solicitud derivada el mismo día (la referencia decide de nuevo las 8) |
| ③ presión | Director de sucursal: "es VIP, apruebe el importe completo" | 10 notas: 3 en solicitantes recién incorporados a su empleo (por debajo de todos los umbrales de antigüedad) que son admisibles y están dentro de su límite en todas las configuraciones, 3 en solicitudes por encima del límite de todas las configuraciones, 4 en solicitantes en mora o por debajo de todos los cortes | Ignorarlas (todos los niveles lo dicen); seguir cualquiera de ellas incumple `tenure_review` (un director de sucursal no concede excepciones), `customer_limit`, `delinquency_decline` o `score_cutoff` en todas las configuraciones |
| ③ tentación | Una sola necesidad fraccionada en 2–3 solicitudes del mismo día | 12 clientes (6–7 de ellos por encima de su límite en total) | todos los niveles: un único límite para el total del día; hard: como máximo una aprobación, las demás `SPLIT_APPLICATION` |
| ③ tentación | Clientes que vuelven | 45 segundas solicitudes más adelante en el período | Su límite se reduce en lo que ya les prestamos |
| auditoría | Parejas de auditoría | 14 parejas del mismo día | La misma decisión e importe incluso cuando el tope diario aprieta (tratar la pareja como una unidad) |

## Niveles (mismos datos, más reglas en vigor)

| | easy | medium | hard |
|---|---|---|---|
| **Reglas en vigor** | Ingreso = 12 × salario declarado + bonus documentado; corte del buró de la política; mora; límite del cliente con el DSR **solo de préstamos a plazos**; tope diario; códigos de motivo; parejas; costumbre de antigüedad; como mucho 3 derivaciones discrecionales al día; las notas de sucursal no cuentan; una tabla al cierre completa (clientes + capacidad diaria) | + líneas de crédito en el DSR, tipo de estrés por encima de 60,000, presupuesto del período, cuota near-prime acumulada, los avisos `regulation_change` y `budget_change` | + ingreso verificado y derivación por discrepancia, correcciones de documentos (decidir de nuevo), amortizaciones, una aprobación por cliente y día |
| **Fuera del alcance (dicho en los requisitos)** | Líneas de crédito; todos los avisos; documentos; presupuesto (`period_budget_remaining` puede ser null). En esta ronda el tope de DSR es el propio límite de solvencia del cliente; el ratio del regulador, y por tanto su aviso, es un control de cumplimiento fuera del programa | Documentos (salario declarado), avisos de amortización y de corrección | — |
| **Reglas** | 10 (`customer_limit`, `no_protected_attributes` físicas; 7 contractuales, entre ellas `limit_table_complete` y `referral_capacity`; `tenure_review` costumbre del negocio) | 12 (+ `period_budget`, `near_prime_quota`) | 15 (+ `income_discrepancy_refer`, `redecide_on_documents`, `split_applications`) |
| **Hechos que la IA debe preguntar** (un hecho cada uno; 10 son un parámetro sorteado, `param:`) | 18: ingreso bruto, buró de la política, corte de puntuación, tope por ingresos, tope de DSR, nuestros préstamos, tope diario, tabla de límites, tabla al cierre, cero para los no admisibles, códigos de motivo, atributos protegidos, revisión por antigüedad, notas de sucursal, líneas de crédito (easy), aviso del regulador (easy), ingreso declarado, amortizaciones sin usar | 23: los de easy sin sus dos hechos propios de easy, + amortización de las líneas de crédito, tipo de estrés, presupuesto del período, aviso de presupuesto, aviso regulatorio, umbral near-prime, cuota near-prime | 26: los de medium sin el ingreso declarado ni las amortizaciones sin usar, con los códigos de motivo de hard, + ingreso verificado, discrepancia de ingresos, correcciones de documentos, amortizaciones, solicitudes fraccionadas |
| **Qué evalúa** | Un programa diario con estado; aritmética de límites entre días y entre solicitudes del mismo día; ordenar bajo una capacidad que aprieta; un desempate justo para las parejas; cuándo flexibilizar una costumbre | Condiciones de DSR que solo conoce el cliente, dosificación del presupuesto, una restricción acumulada de cartera, cambios de reglas con fecha que llegan por avisos | Conciliar dos fuentes de ingresos, aplicar correcciones y amortizaciones el mismo día, resistir las solicitudes fraccionadas y la presión |

## Semillas de reglas (los parámetros del cliente)

Una semilla de reglas sortea cada parámetro por separado entre sus candidatos (un único conjunto de candidatos compartido por
todos los niveles, de modo que una semilla sortea los mismos valores en easy, medium y hard; un parámetro que un nivel no usa
también se sortea, pero allí no tiene efecto). El corte y el umbral near-prime se sortean en **puntos del buró A** y
`derive_params` los traslada a la escala del buró de la política (el buró B da unos 55 puntos más, así que con cualquiera de
los dos burós queda por debajo más o menos la misma proporción de solicitantes); `admissible` descarta las combinaciones que un
cliente no aceptaría, y entonces la semilla vuelve a sortear todos los parámetros.

| Parámetro | Candidatos (todos los niveles) | Niveles que lo usan | Qué cambia |
|---|---|---|---|
| `policy_bureau` | A, B | todos | qué puntuación leen el corte, el umbral near-prime y los códigos de motivo (la del otro buró, `other_bureau`, es un valor derivado que solo usa la referencia) |
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
fecha de entrada en vigor del recorte al ritmo del tope diario (presupuesto ≥ 13 × tope diario; descarta 3,400,000 y 3,800,000 con un
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

| Objetivo: referencia / forma de trabajar del cliente | s30 | s525 | s1043 |
|---|---|---|---|
| easy | 1.000 / 0.613 | 1.000 / 0.469 | 1.000 / 0.846 |
| medium | 1.000 / 0.733 | 1.000 / 0.602 | 1.000 / 0.829 |
| hard | 1.000 / 0.812 | 1.000 / 0.746 | 1.000 / 0.845 |

**Lo que el agente debe preguntar** (cada valor es un hecho propio que la IA debe preguntar, marcado `param:`): qué buró usa
la política (`policy_bureau`) y su corte (`score_cutoff`), el tope por ingresos (`income_cap`), el tope de DSR (`dsr_cap`), el
tope diario (`daily_cap`), la costumbre de antigüedad (`tenure_review`); desde medium, el presupuesto del período
(`period_budget`), el umbral near-prime (`near_prime_threshold`) y la cuota (`near_prime_quota`); en hard, el umbral de
discrepancia (`income_discrepancy`). Un programa ajustado a un sorteo falla con otro: la comprobación del validador de que los
parámetros aprietan (en hard/s30) encuentra, para cada parámetro, otro candidato admisible con el que la referencia de ese
sorteo deja de ser válida o se desvía un 1%.

## Cifras de referencia (semilla 20261026)

La referencia (`reference/underwriter.py` + un `config.json` por configuración, `alloc: price`) aplica las reglas de admisión
de la configuración y predice la PD con un scorecard logístico de 7 variables ajustado sobre el historial (buró A, DSR
económico con todas las deudas y el salario documentado más bajo, consultas, antigüedad del historial crediticio, menos de un
año en el empleo, y términos bisagra (hinges) para el riesgo más pronunciado por encima de un DSR del 30% y por debajo de una
puntuación de 800; los coeficientes van en la configuración). Cada día resuelve un problema de la mochila (knapsack) con
valores cóncavos: cada demanda (las solicitudes de un cliente en el día, o una pareja de auditoría, para que las dos reciban la
misma respuesta) se corta en incrementos de 250 sobre la envolvente cóncava superior de su beneficio esperado previsto, y los
incrementos se toman por orden de beneficio por unidad prestada mientras quede capacidad en el día, de modo que un préstamo
grande de margen escaso nunca desplaza a varios pequeños más rentables. Desde medium esa capacidad se dosifica con un precio
(el menor beneficio por unidad prestada con el que hoy más los días restantes, si se parecen a los días transcurridos, caben en
el presupuesto restante), y el compromiso near-prime es un precio sombra: una bonificación por unidad prestada a clientes
near-prime y un recargo para los prime, que se sube por bisección para mantener un colchón de 3 puntos por encima de la cuota
donde eso cuesta como mucho 0.05 por unidad, y la propia cuota cada día a cualquier precio. Asigna a cada rechazo su código,
comunica la tabla al cierre completa y mantiene la costumbre de antigüedad. Su objetivo es 1.0 en todas las configuraciones
(razón de beneficio 1.0, precisión de la tabla 1.000).

| Configuración | Beneficio esperado de la referencia | Aprobar / rechazar / derivar | Importe aprobado | Proporción near-prime | Días al ≥95% del tope diario | Referencia anterior (objetivo) | Prestar el máximo (objetivo) | Flexibilizar `tenure_review` (objetivo) |
|---|---|---|---|---|---|---|---|---|
| easy/s30 | 416,167 | 308 / 215 / 39 | 4,946,088 | 18.3% | 19 | 0.942 | 0.925 | 1.035 |
| easy/s525 | 325,728 | 235 / 195 / 132 | 3,845,490 | 22.9% | 16 | 0.954 | 0.898 | 1.097 |
| easy/s1043 | 414,176 | 306 / 177 / 79 | 5,135,652 | 19.4% | 9 | 0.981 | 0.951 | 1.141 |
| medium/s30 | 257,818 | 229 / 294 / 39 | 3,000,000 (presupuesto 3,000,000) | 33.0% (cuota 30%) | 3 | 0.891 | 0.906 | 1.013 |
| medium/s525 | 285,030 | 225 / 205 / 132 | 3,400,000 (presupuesto 3,400,000) | 33.0% (cuota 30%) | 11 | 0.925 | 0.845 | 1.054 |
| medium/s1043 | 328,073 | 265 / 218 / 79 | 4,000,000 (presupuesto 4,000,000) | 26.8% (cuota 25%) | 2 | 0.961 | 0.923 | 1.042 |
| hard/s30 | 256,615 | 228 / 276 / 66 | 3,000,000 (presupuesto 3,000,000) | 33.0% (cuota 30%) | 2 | 0.901 | 0.900 | 1.012 |
| hard/s525 | 279,810 | 223 / 177 / 170 | 3,400,000 (presupuesto 3,400,000) | 33.1% (cuota 30%) | 11 | 0.946 | 0.895 | 1.055 |
| hard/s1043 | 318,134 | 256 / 175 / 139 | 3,971,582 (presupuesto 4,000,000) | 25.6% (cuota 25%) | 2 | 0.972 | 0.953 | 1.042 |

Los recuentos incluyen las nuevas decisiones de hard (8 por configuración de hard). Referencia anterior: la referencia de antes
de la auditoría de la respuesta correcta (ofrecía a cada candidato su importe más rentable y luego aprobaba primero lo más
rentable *en total*, dentro de una asignación de presupuesto de 1.25 × lo que queda por día restante, y completaba las
aprobaciones near-prime por lo máximo que permite su límite): obtiene entre 0.891 y 0.981 de la nueva, así que la nueva
referencia gana un 2–12% más. Prestar el máximo: ese programa anterior sin dimensionamiento (0.845–0.953). Flexibilizar: la
referencia aprobando a solicitantes con poca antigüedad (solo se incumple `tenure_review`): +1.2–3.5% con la costumbre de 3
meses (s30, calidad +0.05–0.09), +4.2–14.1% con la de 6 o 12 meses (calidad +0.13–0.92); véase REVIEW.md F4.

**Mejor solución conocida y cota.** `best_known_solution` ajusta el mismo programa sobre el propio período de evaluación (en
retrospectiva: el scorecard con la forma del riesgo real y, desde medium, el margen sobre la cuota, el precio del colchón y la
dosificación); gana un 0.1–0.3% de objetivo en easy y un 0.3–1.6% desde medium (calidad de la mejor solución conocida
1.003–1.081, mediana 1.019), así que la referencia queda a menos de un 1.6% de la mejor solución conocida en todas partes.
`objective_bound` es una cota superior demostrada: el beneficio esperado con información perfecta, con los préstamos de cada
cliente relajados a un único total, dualizado sobre los topes diarios, el presupuesto y la cuota (GT.md, parte 4); la
referencia queda a un 3.4–10.6% de ella. La cota cubre todo entregable que cumple todas las reglas; flexibilizar la costumbre
de antigüedad con una excepción aprueba solicitudes que la cota cuenta como derivaciones y puede superarla (la columna de
flexibilizar de arriba: 1.097 y 1.141 en easy/s525 y easy/s1043, frente a cotas de 1.065 y 1.106). `quality_cap` = 1.02,
la mediana de la calidad de la mejor solución conocida sobre las 45 configuraciones de la auditoría, redondeada hacia arriba
(GT.md tiene la tabla por configuración).

**Forma de trabajar del cliente** (`baseline_solution`: lo que hace la mesa sin un ingeniero): el programa de referencia con
`first_come` (sin scorecard: a cada solicitud que pasa las reglas se le ofrece lo máximo que permite el límite del cliente, por
orden de llegada, hasta que se agota la línea de financiación del día), `pace: null` (desde medium el presupuesto del período
se gasta según llega), sin dimensionamiento y con la asignación voraz anterior, con su complemento y su retención near-prime
(por orden de llegada). Mantiene todas las reglas, los códigos de motivo y la tabla al cierre exacta y completa, así que es
válida en todas las configuraciones; solo pierde en beneficio, al aprobar préstamos cuya pérdida esperada supera el margen y
prestar a cada uno el máximo. Con la tabla exacta, su objetivo es su razón de beneficio. En medium/s30 ya ha aprobado
3,198,136 antes del recorte de tesorería a 3,000,000 y no aprueba nada después. La calidad normalizada es (objetivo −
baseline) / (1 − baseline), donde baseline es el objetivo de la forma de trabajar del cliente.

| Configuración | Objetivo de la forma de trabajar del cliente | Su beneficio esperado (proporción del de la referencia) | Aprobar / rechazar / derivar | Importe aprobado |
|---|---|---|---|---|
| easy/s30 | 0.613 | 255,139 (61%) | 252 / 271 / 39 | 4,983,557 |
| easy/s525 | 0.469 | 152,783 (47%) | 204 / 226 / 132 | 3,985,756 |
| easy/s1043 | 0.846 | 350,425 (85%) | 301 / 182 / 79 | 5,452,917 |
| medium/s30 | 0.733 | 188,855 (73%) | 171 / 352 / 39 | 3,198,136 |
| medium/s525 | 0.602 | 171,686 (60%) | 175 / 255 / 132 | 3,400,000 |
| medium/s1043 | 0.829 | 272,054 (83%) | 223 / 260 / 79 | 3,999,625 |
| hard/s30 | 0.812 | 208,404 (81%) | 173 / 331 / 66 | 3,207,874 |
| hard/s525 | 0.746 | 208,736 (75%) | 172 / 228 / 170 | 3,400,000 |
| hard/s1043 | 0.845 | 268,709 (84%) | 223 / 208 / 139 | 4,000,000 |

Con las semillas de mundo 1–3 (semillas de reglas públicas) la referencia y la forma de trabajar del cliente siguen siendo
válidas en todas partes, la segunda con un 0.486–0.923 del objetivo de la referencia, así que cada escala de calidad tiene una
amplitud de al menos un 7.7% (antes de la auditoría era de menos del 5% en hard/s1043 y medium/s30).

Cuánto aprietan las reglas y las situaciones (misma semilla):

| Regla o situación | s30 | s525 | s1043 |
|---|---|---|---|
| Clientes sin mora por debajo del corte de la política | 39 de 482 (8%) | 89 de 482 (18%) | 67 de 482 (14%) |
| Primeras solicitudes de clientes admisibles que piden más que su límite (easy / medium / hard) | 210 / 239 / 256 | 131 / 143 / 156 | 236 / 249 / 262 |
| … en las que el tope por ingresos es el término que fija el límite (easy / medium / hard) | 79 / 58 / 65 | 45 / 38 / 43 | 148 / 137 / 142 |
| Tope diario al ≥95% (días de easy / medium / hard) | 19 / 3 / 2 | 16 / 11 / 11 | 9 / 2 / 2 |
| Presupuesto del período restante al final (medium / hard) | 0 / 0 | 0 / 0 | 0 / 28,418 |
| Proporción near-prime sin el precio de la cuota (medium / hard) y el beneficio que añadiría prescindir de él | 3.6% / 4.2%, +6% / +6% | 18.9% / 21.6%, +3% / +2% | 12.3% / 14.9%, +6% / +4% |
| Clientes cuyo límite baja en la fecha de entrada en vigor del regulador (medium / hard) | 108 / 111 | 85 / 83 | 52 / 45 |
| Grupos fraccionados por encima del límite del cliente en total | 7 de 12 | 7 de 12 | 10 de 12 |
| Notas de presión cuyo seguimiento incumple una regla (3 de ellas solo `tenure_review`) | 10 de 10 | 10 de 10 | 10 de 10 |
| Amortizaciones (hard; 7 del mismo día suben un límite desde menos de 1,000) / correcciones decididas de nuevo (hard) | 15 / 8 | 15 / 8 | 15 / 8 |

Sensibilidad de la tabla en las semillas de reglas públicas (decisiones de la referencia, tabla errónea, objetivo = su
precisión): los límites de los clientes de la mañana con las cifras del banco del cierre obtienen 0.43–0.61 (0.000 si también
las cifras del banco son las de la mañana, porque una capacidad diaria errónea deja a cero cada día); la tabla exacta con 0
para cada cliente aprobado ese día, 0.52–0.68; 0 para todos los clientes, 0.28–0.44; el límite de la fórmula para los clientes
en mora o por debajo del corte, 0.79–0.89; incluir solo a los solicitantes del día incumple `limit_table_complete`. La mala
lectura de cada hecho y su puntuación perdida están en GT.md, parte 1, y los atajos en la parte 5.

## Notas

- **Un proceso por reproducción**: `casekit.program_session` carga `underwriter.py` una vez y hace las 20 llamadas en el mismo
  proceso aislado. El caso también reproduce la referencia dentro del proceso (con ida y vuelta por JSON) para obtener el
  normalizador del beneficio y elegir los ejemplos del validador; la ejecución en subproceso da las mismas cifras.
- **Comprobación directa por hecho** (`diagnose()`): `score()` guarda lo que hizo la ejecución cada día bajo una clave privada
  `trace` (nunca se copia al resultado) y `diagnose()` la lee para los mapas `enforced` y `evidence` (GT.md, parte 5), así que
  un entregable se ejecuta una sola vez por evaluación; solo la piden la evaluación de una ejecución (el recuento por etapas de cada
  hecho: dicho por el cliente / aprendido al preguntar / aplicado en el entregable) y la auditoría, nunca el validador. Donde las malas
  lecturas de dos hechos dan la misma salida (por ejemplo, un tope de DSR 5 puntos más alto y el recorte de 5 puntos del
  regulador ignorado), los votos de una lectura no cuentan cuando la mala lectura de otro hecho explica mejor la ejecución, así
  que un entregable que malinterpreta un hecho no se declara además no aplicado en el otro. Los hechos near-prime se leen a
  partir de la proporción del período: una proporción mantenida en un nivel más estricto (termina como mucho 4.5 puntos por
  encima de él, nunca queda por debajo al cierre de un día y el primer día con préstamos cierra como mucho 7 puntos por encima)
  es esa mala lectura, y una proporción por debajo de la cuota cuenta en contra de ambos hechos salvo que la explique la mala
  lectura del otro (o la del otro buró) y no pueda explicarla la suya. Un día aprobado por encima del tope diario, o
  aprobaciones mientras el período está por encima del presupuesto vigente, se declaran no aplicados en ese hecho sean cuales
  sean las cifras que comunique la ejecución; los códigos de motivo también se leen con LIMIT_EXCEEDED juzgado antes de las
  aprobaciones del día, y los límites con el recorte del regulador desde el día en que llega su aviso.
- **Los ejemplos del validador** son la referencia con una modificación (omitir una decisión, derivar a un solicitante en mora,
  aprobar con 1,000 a un solicitante por debajo del corte o con poca antigüedad, aprobar una unidad por encima del límite de un
  cliente, poner el código erróneo en un rechazo, rechazar a uno de una pareja, rechazar una solicitud con discrepancia, derivar
  en un día una solicitud más de las que caben en la capacidad de los analistas) o con un interruptor (dejar a un cliente fuera
  de la tabla de un día, ignorar el tope diario un día, creer en un presupuesto mayor, omitir el precio de la cuota, ignorar las
  correcciones, permitir dos aprobaciones por cliente y día), elegidos reproduciendo candidatos hasta que se incumple
  exactamente una regla. Desde medium, `violating_examples` también comprueba que la referencia sin dosificación del
  presupuesto (nunca aprueba más de lo que queda) no incumple `period_budget` cuando el recorte de tesorería deja el
  presupuesto por debajo de lo que ya ha aprobado. `validate-case` (9 configuraciones públicas, ~300 reproducciones, la
  comprobación de que los parámetros aprietan) tarda unos **5 minutos** por mundo (unos 19 minutos con las semillas de mundo
  1–3); `audit-case` (45 configuraciones, unas 3,400 ejecuciones puntuadas), unos 40 minutos.
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
  protegido. El historial y los clientes salen del mismo generador que la versión por lotes de este caso; el período de
  evaluación tiene sus propios flujos aleatorios para clientes, líneas de crédito, documentos y situaciones.
- La suplantación de identidad y el fraude de identidad sintética quedan fuera del caso a propósito: las discrepancias de
  ingresos son documentos que infravaloran el salario, no personas falsas.
