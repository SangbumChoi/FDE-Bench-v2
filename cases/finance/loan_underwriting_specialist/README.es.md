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
[Datos](#datos)). El caso tiene nueve configuraciones (3 niveles × 3 conjuntos de reglas) sobre **un solo** mundo: el
historial, el período oculto y cada solicitud, nota de sucursal y aviso son los mismos en las nueve, y lo que ve el agente
(solicitud, datos, especificación del entregable) es idéntico byte a byte (lo comprueba el validador). Solo cambian los
requisitos ocultos y el evaluador. Los ajustes de la modalidad (especificación completa o aclarar primero, perfil, ruido en los
datos, eventos) se aplican por encima, como en todos los casos (véase [cases/README.md](../../README.md)).

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
- `gt/<tier>_<ruleset>/` (9 configuraciones): `setting.json`, `reference/program/` (la referencia con su configuración),
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
| ① hecho oculto | Tope diario de desembolso, presupuesto del período | — | Preguntar: tope por conjunto de reglas; presupuesto desde medium. Priorizar las aprobaciones más rentables; dosificar el presupuesto |
| ① | Fórmulas del límite | — | Preguntar: importe máximo del producto, % del tope por ingresos, DSR con préstamos a plazos (easy) / líneas de crédito y tipo de estrés (medium y hard), contando lo que ya prestamos antes |
| ① | La cuota near-prime es **acumulada** sobre el período | — | Preguntar; gobernar la proporción acumulada, que se comprueba una vez al final |
| ① | Buró de la política y corte, costumbre de antigüedad, orden de los códigos de motivo, tabla al cierre (no de la mañana) | — | Preguntar |
| ② evento con fecha | El regulador baja el tope de DSR 5 puntos para las decisiones desde el 16 de noviembre (aviso el 10 de noviembre) | 1 `regulation_change` | medium y hard: nuevo tope para las decisiones y la tabla desde la fecha de efecto (ese día cambian los límites de ≈ 170–185 clientes) |
| ② | Tesorería recorta el presupuesto del período en 400,000 desde el 19 de noviembre | 1 `budget_change` | medium y hard: el presupuesto y su valor en la tabla bajan ese mismo día; la dosificación se adapta. Las aprobaciones anteriores al recorte se mantienen; si el total ya supera el nuevo presupuesto, no se aprueba nada más |
| ② | Un acreedor confirma una deuda pagada (7 el día en que el cliente presenta la solicitud, 8 más tarde) | 15 `repayment` | hard: quitar la deuda desde ese día (la lista del buró de la mañana todavía la muestra): más margen, otra tabla |
| ② | Un empleador reemite un documento que infravaloraba el salario | 8 `document_correction` (todos para solicitudes con una diferencia del 27–45%, derivadas en todos los conjuntos de reglas de hard) | hard: decidir de nuevo la solicitud derivada el mismo día (la referencia decide de nuevo las 8) |
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

## Conjuntos de reglas (los parámetros del cliente)

| Parámetro | A | B | C |
|---|---|---|---|
| Buró de la política y corte (`policy_bureau`, `min_score`) | Buró A ≥ 650 | **Buró B** ≥ 740 | Buró A ≥ 680 |
| Near-prime por debajo de (`near_prime_below`) | 820 | 870 (buró B) | 850 |
| Tope de DSR (`max_dsr_pct`; −5 puntos desde el 16 de noviembre en medium y hard) | 40% | 35% | 45% |
| Tope por ingresos (`income_cap_pct`) | 100% | 80% | 120% |
| Tope diario (`daily_cap`) | 250,000 | 200,000 | 300,000 |
| Presupuesto del período, medium y hard (`period_budget`; −400,000 desde el 19 de noviembre) | 4,400,000 | 3,800,000 | 3,400,000 |
| Cuota near-prime, medium y hard (`quota_pct`) | 30% | 25% | 35% |
| Discrepancia de ingresos para derivar, hard (`discrepancy_pct`) | 20% | 15% | 25% |
| Costumbre de antigüedad: derivar por debajo de (`min_tenure`, meses) | 6 | 3 | 12 |

Los parámetros no anidados: el buró (el buró B da unos 55 puntos más, con ruido, así que su corte selecciona a otros
clientes), el tope por ingresos frente al tope de DSR (B es estricto en ambos, C holgado en ambos, A está en medio) y el tope
diario frente al presupuesto (B: tope diario estricto, presupuesto más holgado; C: tope diario holgado, presupuesto estricto).
Dentro de cada nivel, la referencia de cada conjunto de reglas **no es válida bajo los otros dos** (típicamente por
`customer_limit`, `daily_cap`, `score_cutoff`, `tenure_review`, `near_prime_quota`, `period_budget`,
`reason_code_required`).

## Cifras de referencia (semilla 20261026)

La referencia (`reference/underwriter.py` + un `config.json` por configuración) aplica las reglas de admisión de la
configuración, ofrece a cada candidato mín(solicitado, límite del cliente), predice la PD con un scorecard logístico de 5
variables ajustado sobre el historial (buró A, DSR económico con todas las deudas y el salario documentado más bajo,
consultas, antigüedad del historial crediticio; los coeficientes van en la configuración), aprueba las unidades con beneficio
esperado positivo (las parejas como una sola unidad), de la más rentable a la menos, dentro de lo que permite el día (el tope
diario; desde medium también el presupuesto restante / días restantes × 1.25), completa aprobaciones near-prime hasta que la
proporción acumulada queda 1.5 puntos por encima de la cuota (sustituyendo las aprobaciones prime menos rentables cuando falta
capacidad), asigna a cada rechazo su código y comunica la tabla al cierre. Mantiene la costumbre de antigüedad y aprueba el
importe máximo. Su objetivo es 1.0 en todas las configuraciones (componente de beneficio 1.0, precisión de la tabla 1.000).

| Configuración | Beneficio esperado de la referencia | Aprobar / rechazar / derivar | Importe aprobado | Proporción near-prime | Días al ≥95% del tope diario | Flexibilizar `tenure_review` (objetivo) | Margen de mejora: oráculo (objetivo) |
|---|---|---|---|---|---|---|---|
| easy/A | 352,508 | 203 / 280 / 79 | 4,680,060 | 11.6% | 14 | +3.0% | +9.5% |
| easy/B | 322,117 | 156 / 367 / 39 | 3,953,984 | 12.1% | 19 | +0.5% | +5.4% |
| easy/C | 347,016 | 217 / 213 / 132 | 4,843,842 | 24.5% | 9 | +12.4% | +14.5% |
| medium/A | 225,186 | 197 / 286 / 79 | 3,950,000 (presupuesto 4,000,000) | 31.5% (cuota 30%) | 4 | +7.6% | +21.0% |
| medium/B | 260,426 | 144 / 379 / 39 | 3,400,000 (presupuesto 3,400,000) | 27.7% (25%) | 5 | +0.6% | +3.7% |
| medium/C | 207,738 | 139 / 291 / 132 | 3,000,000 (presupuesto 3,000,000) | 37.0% (35%) | 0 | +5.3% | +9.3% |
| hard/A | 227,201 | 195 / 250 / 125 | 3,950,000 | 31.6% | 6 | +9.2% | +18.5% |
| hard/B | 260,042 | 158 / 307 / 105 | 3,400,000 | 27.6% | 5 | +0.5% | +1.8% |
| hard/C | 199,877 | 137 / 282 / 151 | 2,905,728 | 36.7% | 0 | +7.1% | +11.8% |

Los recuentos incluyen las nuevas decisiones de hard (8 por configuración de hard). Flexibilizar: el mismo programa aprobando a
solicitantes con poca antigüedad (solo se incumple `tenure_review`; de +0.7% a +17.7% de beneficio). Oráculo: la PD real en
lugar del scorecard, ordenando por beneficio por unidad de capacidad, el importe más rentable (rejilla de 250), el mejor de
cuatro factores de dosificación, las mismas reglas (válido en todas partes); una cota inferior de lo posible. La mayor parte del
margen de mejora está en el dimensionamiento del préstamo: la referencia presta el máximo, y la PD real sube con fuerza por
encima de un DSR económico del 32%. B tiene el menor margen porque su tope de 200,000 aprieta en 19 de los 20 días de easy y
sus límites son pequeños.

| Media por nivel (A, B, C) | easy | medium | hard |
|---|---|---|---|
| Beneficio esperado de la referencia | 340,547 | 231,117 | 229,040 |
| Objetivo de la línea base | 0.470 | 0.611 | 0.670 |
| Flexibilizar `tenure_review` (objetivo) | +5.3% | +4.5% | +5.6% |
| Margen de mejora del oráculo (objetivo) | +9.8% | +11.3% | +10.7% |

**Línea base** (`baseline_solution`: lo que hace la mesa sin un ingeniero): el programa de referencia con dos interruptores,
`first_come` (sin scorecard: a cada solicitud que pasa las reglas se le ofrece lo máximo que permite el límite del cliente, por
orden de llegada, hasta que se agota la línea de financiación del día) y `pace: null` (desde medium el presupuesto del período
se gasta según llega, sin dosificar). Mantiene todas las reglas, los códigos de motivo, el complemento near-prime (por orden de
llegada, en lugar de las aprobaciones prime más pequeñas) y la tabla exacta al cierre, así que es válida en todas las
configuraciones; solo pierde en beneficio, al aprobar préstamos cuya pérdida esperada supera el margen. En medium/C y hard/C
ya ha aprobado 3,400,000 antes del recorte de tesorería a 3,000,000 y no aprueba nada después. La calidad normalizada es
(objetivo − línea base) / (1 − línea base).

| Configuración | Objetivo de la línea base | Beneficio esperado de la línea base (proporción del de la referencia) | Aprobar / rechazar / derivar | Importe aprobado |
|---|---|---|---|---|
| easy/A | 0.460 | 80,447 (23%) | 243 / 240 / 79 | 4,999,394 |
| easy/B | 0.571 | 124,532 (39%) | 202 / 321 / 39 | 3,999,248 |
| easy/C | 0.380 | 39,443 (11%) | 275 / 155 / 132 | 5,909,000 |
| medium/A | 0.596 | 95,369 (42%) | 196 / 287 / 79 | 4,000,000 |
| medium/B | 0.725 | 158,240 (61%) | 181 / 342 / 39 | 3,400,000 |
| medium/C | 0.511 | 62,687 (30%) | 161 / 269 / 132 | 3,400,000 |
| hard/A | 0.641 | 110,588 (49%) | 204 / 241 / 125 | 3,999,609 |
| hard/B | 0.749 | 166,683 (64%) | 187 / 278 / 105 | 3,400,000 |
| hard/C | 0.620 | 91,376 (46%) | 164 / 255 / 151 | 3,400,000 |

Con las semillas de mundo 1–3 la línea base sigue siendo válida en todas partes, con un 0.43–0.89 del objetivo de la
referencia.

Cuánto aprietan las reglas y las situaciones (misma semilla):

| Regla o situación | A | B | C |
|---|---|---|---|
| Primeras solicitudes de clientes admisibles que piden más que su límite (easy / medium / hard) | 150 / 188 / 206 de 495 | 190 / 239 / 255 de 485 | 112 / 145 / 165 de 492 |
| Tope diario al ≥95% (días de easy / medium / hard) | 14 / 4 / 6 | 19 / 5 / 5 | 9 / 0 / 0 |
| Presupuesto del período restante al final (medium / hard) | 50,000 / 50,000 | 0 / 0 | 0 / 94,272 |
| Proporción near-prime sin el complemento (medium / hard) y su ganancia de beneficio si se permitiera | 9.4% / 12.7%, +42% / +39% | 10.3% / 13.0%, +9% / +8% | 18.5% / 18.8%, +12% / +17% |
| Clientes cuyo límite baja en la fecha de efecto del regulador (medium / hard) | 184 / 185 | 181 / 180 | 170 / 169 |
| Grupos fraccionados por encima del límite del cliente en total | 6–7 de 12 | 7 de 12 | 6 de 12 |
| Notas de presión cuyo seguimiento incumple una regla | 10 de 10 | 10 de 10 | 10 de 10 |
| Amortizaciones (hard) / correcciones decididas de nuevo (hard) | 15 / 8 | 15 / 8 | 15 / 8 |

Sensibilidad de la tabla (decisiones de la referencia, tabla errónea): olvidar nuestros préstamos anteriores en los límites de
los clientes da una precisión de 0.81–0.86; comunicar los límites de la mañana en lugar de los del cierre, 0.97–0.98. La
referencia de cada conjunto de reglas ejecutada bajo otro conjunto de reglas también se equivoca en la tabla (otro corte, otros
topes y otras fórmulas).

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
  presupuesto (nunca aprueba más de lo que queda) no incumple `period_budget`: en las configuraciones C de la semilla pública
  tiene 3.1M aprobados antes del recorte a 3.0M, y la regla no debe contárselo en contra. `validate-case` (9 configuraciones,
  ~200 reproducciones) tarda unos **40 segundos** por mundo.
- **Otras semillas de mundo** (`validate-case --world-seeds`, campañas con semillas privadas): los ejemplos no dependen del
  margen que un período deje por casualidad. Una modificación que aprueba más en un día que ya está en el tope diario (o en el
  presupuesto) recorta otra aprobación de ese día en la misma cantidad; cuando la referencia no aprueba por sí misma ninguna
  segunda solicitud fraccionada (ningún miembro de una pareja), el ejemplo pasa 1,000 a una segunda (aprueba a uno de la
  pareja); cuando la demanda se queda por debajo del tope o del presupuesto, o por encima de la cuota, el ejemplo aprueba
  rechazos por riesgo crediticio, completa aprobaciones near-prime sin fin o rechaza aprobaciones near-prime. El generador
  mantiene todos los avisos dentro del período y da a cada conjunto de reglas al menos un solicitante por debajo de su corte de
  puntuación que, por lo demás, sería aprobable en todos sus niveles (un mundo sin ninguno recibe nuevas puntuaciones de buró
  para un solicitante aleatorio que no interviene en ninguna otra situación). Las unidades de pareja de la referencia solo unen
  a dos clientes: una necesidad fraccionada en partes iguales (p. ej. 24,000 + 24,000) son dos unidades, cada una dentro de lo
  que queda del límite del cliente. La semilla pública tiene los solicitantes por debajo del corte y ningún fraccionamiento en
  partes iguales, así que su mundo, sus datos, sus decisiones y sus tablas de límites no cambian.
- Las puntuaciones, los salarios, las deudas y las probabilidades de impago son sintéticos; la PD real no usa ningún atributo
  protegido. El historial y los clientes salen del mismo generador que la versión por lotes de este caso; el período oculto
  tiene sus propios flujos aleatorios para clientes, líneas de crédito, documentos y situaciones.
- La suplantación de identidad y el fraude de identidad sintética quedan fuera del caso a propósito: las discrepancias de
  ingresos son documentos que infravaloran el salario, no personas falsas.
