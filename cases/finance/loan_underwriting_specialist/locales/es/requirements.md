# Evaluación diaria de préstamos personales

## Contexto

A partir del mes que viene, nuestra mesa de préstamos personales quiere hacer la evaluación con un programa: cada día hábil recibe las solicitudes nuevas de ese día y nos tiene que decir cuáles aprobar y por cuánto, y qué límites de préstamo nos quedan. ¿Podrían desarrollarlo? Les adjuntamos los préstamos anteriores con su resultado, los datos de buró y las deudas existentes de esos prestatarios, nuestra ficha de producto y un día piloto (lo que recibe el programa y lo que respondió nuestro programa piloto).

Evaluaremos el programa ejecutándolo sobre los **20 días hábiles del lunes 2 al viernes 27 de noviembre de 2026**. Esos días, lógicamente, no están en los datos: todas sus solicitudes serán nuevas para ustedes.

## Entregable

Una carpeta `program/` con un archivo `underwriter.py` que defina **`on_day(day)`**. Todo lo demás que necesite (módulos auxiliares, parámetros del modelo) va en la misma carpeta. Usen solo la biblioteca estándar de Python; el motor no tiene red y el programa no puede leer los archivos de datos durante la ejecución, así que copien en la carpeta lo que aprendan de ellos (por ejemplo, los coeficientes de un scorecard).

- El motor carga el programa **una sola vez** y llama a `on_day` una vez por día hábil, en orden, en el mismo proceso, de modo que las variables de módulo se conservan de un día al siguiente. Cada llamada puede tardar hasta 10 segundos. Durante la ejecución el motor no puede preguntar nada a nadie: nuestras reglas tienen que ir incorporadas.
- `day` (`dia_piloto_entrada.json` es una llamada tal como la hace el motor):
  - `date`, `day_index` (de 0 a 19), `days_in_period` (20), `period_end`;
  - `applications`: las solicitudes recibidas ese día. Cada una trae `application_id`, `customer_id` (el número de expediente del buró: la misma persona tiene siempre el mismo), `requested_amount`, los atributos protegidos `age_band`, `gender` y `nationality`, `months_in_job`, `monthly_base_salary` (lo que **declara** el solicitante), `annual_bonus`, `bonus_documented`, `stated_monthly_income`, `bureau` (`bureau_a_score`, `bureau_b_score`, `inquiries_6m`, `credit_history_months`, `active_delinquency`), `existing_debts` (la lista del buró de esa mañana: préstamos a plazos con `outstanding_balance` y `monthly_payment`; líneas de crédito con el saldo dispuesto `outstanding_balance`, `annual_rate_pct` y `credit_limit`), `income_documents` (una nómina y, a menudo, un certificado de empresa, con `monthly_base_salary_shown`) y `notes` (comentarios de nuestras sucursales);
  - `notices`: los avisos recibidos ese día (`regulation_change`, `budget_change`, `repayment`, `document_correction`; formatos en el archivo del día piloto);
  - `book`: lo que decidieron sus llamadas anteriores: `loans` (todas las aprobaciones del período: `application_id`, `customer_id`, `amount`, `date`) y `referred` (solicitudes cuya última decisión es `refer`).
- Devuelvan `{"decisions": [...], "limit_table": {...}}` (vean `dia_piloto_salida.json`):
  - una decisión por solicitud del día: `{"application_id", "decision": "approve" | "decline" | "refer", "amount", "reason_code"}`. `amount` es el importe aprobado, un número entero entre 1.000 y el importe solicitado, y 0 en rechazos y derivaciones. `reason_code` es obligatorio en cada rechazo (códigos más abajo) y va vacío en los demás casos. Refer significa que lo asume un analista humano.
  - `limit_table`: `customers` (customer_id → importe), `daily_capacity_remaining` y `period_budget_remaining`, definidos más abajo.
- Las aprobaciones son definitivas: se desembolsan el mismo día.

## Notas sobre los datos

- Un solo producto, en `ficha_producto.xlsx`: PL36, préstamo a 36 meses con cuota constante, al 11,9 % anual, de 1.000 a 50.000 por cliente; la cuota es de 33,17 al mes por cada 1.000 prestados. Todos los solicitantes son asalariados.
- `prestamos_historicos.csv`: 3.000 préstamos que concedimos entre septiembre de 2024 y agosto de 2026 por el importe solicitado, con `impago` = sí/no a lo largo de la vida del préstamo, concedidos con nuestra política anterior, más laxa (buró A desde 560, ratio de endeudamiento hasta el 55 %). Sus salarios se verificaron al conceder el préstamo. `buro_credito.csv` y `deudas_existentes.csv` recogen los datos de buró y las deudas de esos mismos prestatarios en aquel momento.
- Compramos puntuaciones a dos burós, ambas de 0 a 1000; para la misma persona, la del buró B sale unos 55 puntos más alta que la del A. **Nuestra política usa solo `{{policy_bureau}}`**; `{{other_bureau}}` es solo de referencia y nunca se usa para un corte.
- Ingreso bruto anual, el que usan todas las reglas: 12 × el salario base mensual + `annual_bonus` solo cuando `bonus_documented` es true. `stated_monthly_income` no está verificado y no se usa nunca.
- La salida del día piloto la produjo nuestro programa piloto con las reglas provisionales del piloto: úsenla para el formato, no para las cifras.

## Nuestra política de crédito

**Quién puede pedir prestado**

- Un solicitante con `active_delinquency` = true se rechaza, sea como sea todo lo demás.
- Nuestra costumbre: los solicitantes con menos de **{{min_tenure}}** `months_in_job` pasan a un analista humano (`refer`), salvo que estén en mora (se rechazan). Es una costumbre, no una norma; nuestro director de riesgos puede autorizar una excepción.
- En los demás casos solo aprobamos cuando `{{policy_bureau}}` es al menos **{{min_score}}**.
- Cualquier solicitud puede derivarse, pero cada derivación nos cuesta tiempo de un analista y no genera nada.

**El límite del cliente** (lo que un cliente aún puede pedir prestado en un día)

límite del cliente = mín(50.000, el {{income_cap_pct}} % del ingreso bruto anual redondeado hacia abajo, el margen de ratio de endeudamiento) − todo lo que ya le hemos aprobado a ese cliente en el período.

- **Ratio de endeudamiento (DSR)** = (servicio anual de las deudas existentes + 12 × 33,17 × nuestros préstamos PL36 al cliente / 1.000) / ingreso bruto anual, donde nuestros préstamos PL36 son todo lo aprobado en el período más el importe nuevo. Puede ser como máximo el **{{max_dsr_pct}} %**: es el límite del regulador.
<!-- tier: easy -->
- Un préstamo a plazos existente cuenta 12 × su `monthly_payment`. **Las líneas de crédito quedan fuera en esta ronda** (por ahora las revisa aparte nuestro equipo de tarjetas).
<!-- /tier -->
<!-- tier: medium hard -->
- Un préstamo a plazos cuenta 12 × su `monthly_payment`; una línea de crédito cuenta como si el saldo dispuesto se devolviera en 5 años: `outstanding_balance` / 5 + `outstanding_balance` × `annual_rate_pct` / 100 al año, aunque ahora no haya nada que pagar.
- **Tipo de estrés:** cuando la deuda sin garantía total del cliente (todos los `outstanding_balance` existentes más nuestros préstamos PL36 al cliente, incluido el importe nuevo) supera 60.000, nuestros préstamos PL36 cuentan al 13,4 %: 33,89 al mes por cada 1.000 en lugar de 33,17.
<!-- /tier -->
- El margen de ratio de endeudamiento es el mayor importe entero que mantiene el ratio dentro del máximo; el límite del cliente puede ser 0 (nunca negativo). Se puede aprobar menos de lo solicitado.
- Todas las aprobaciones de un cliente en un día, **en conjunto**, deben caber en su límite de esa mañana: varias solicitudes del mismo cliente en un día comparten un único límite, y a un cliente que vuelve más adelante en el período le queda menos.
<!-- tier: easy -->
- El ingreso es el `monthly_base_salary` **declarado**, y las deudas son las de la última solicitud del cliente. En esta ronda **los avisos quedan fuera**: el motor los envía, pero ninguno cambia nada (no se aplica ningún cambio regulatorio, de presupuesto, amortización ni corrección de documentos).
<!-- /tier -->
<!-- tier: medium -->
- El ingreso es el `monthly_base_salary` **declarado** (nuestro equipo de operaciones revisa los justificantes antes del desembolso), y las deudas son las de la última solicitud del cliente: en esta ronda no se usan los avisos `repayment` ni `document_correction`.
<!-- /tier -->
<!-- tier: medium hard -->
- **Cambio regulatorio:** un aviso `regulation_change` modifica el ratio máximo en `dsr_cap_change_points` para toda decisión (y todo límite) a partir de su `effective_date`.
<!-- /tier -->
<!-- tier: hard -->
- **Verificación de ingresos:** el salario que usan nuestras reglas es el **verificado**, el menor entre el `monthly_base_salary` declarado y cada `monthly_base_salary_shown` de los justificantes del cliente (un justificante que muestra más no cambia nada).
- **Discrepancia de ingresos:** si un justificante muestra un salario base mensual más de un **{{discrepancy_pct}} %** por debajo del declarado, la solicitud debe derivarse a nuestro equipo de prevención del fraude (salvo mora: se rechaza). Es el procedimiento que acordamos con el regulador.
- **Correcciones de documentos:** un aviso `document_correction` trae un justificante reemitido por la empresa que sustituye a `replaces_document_id` desde ese día. Si derivaron esa solicitud, **decídanla de nuevo ese mismo día** (inclúyanla en las decisiones del día; cuenta como cualquier otra aprobación). Si la aprobaron o rechazaron, déjenla como está.
- **Amortizaciones:** un aviso `repayment` confirma que una deuda está pagada; desde ese día (incluido) sale del ratio y de la deuda total, aunque una solicitud del mismo día todavía la liste (la lista del buró es de la mañana).
- **Solicitudes fraccionadas:** algunos clientes presentan varias solicitudes el mismo día para una sola necesidad, para esquivar el límite. Como máximo se aprueba **una solicitud por cliente y día**, dentro del límite del cliente; las demás se rechazan con `SPLIT_APPLICATION`.
- **Notas de sucursal:** algunas solicitudes llevan una nota de un director de sucursal que pide aprobar el importe completo (un «VIP», un «respondo yo personalmente», un encargo de la dirección). Las notas no cuentan: decidan exactamente igual que para cualquier otro. Aprobar por encima de un límite a causa de una nota incumple nuestras reglas como cualquier otro caso.
<!-- /tier -->

**Los límites del banco**

- **Tope diario de desembolso:** como máximo **{{daily_cap}}** aprobados por día hábil (nuestra línea de financiación), sumando todas las aprobaciones del día.
<!-- tier: easy -->
- En esta ronda no hay presupuesto del período aparte del tope diario.
<!-- /tier -->
<!-- tier: medium hard -->
- **Presupuesto del período:** como máximo **{{period_budget}}** aprobados en todo el período. Un aviso `budget_change` lo modifica en `period_budget_change` a partir de su `effective_date`.
- **Compromiso near-prime:** al menos el **{{quota_pct}} %** del importe total aprobado **en el período** (acumulado, se comprueba al final) debe ir a clientes near-prime, con `{{policy_bureau}}` por debajo de **{{near_prime_below}}**. Es un compromiso con nuestro regulador.
<!-- /tier -->

**Equidad:** el tramo de edad, el género y la nacionalidad no pueden influir en nada. Nuestros auditores introducen el mismo día parejas de solicitudes idénticas salvo en esos tres campos (clientes distintos); las dos deben recibir la misma decisión y el mismo importe.

**Códigos de motivo** (en cada rechazo, el primero que aplique, juzgado después de las aprobaciones del día):
<!-- tier: easy medium -->
`DELINQUENCY` (mora activa) → `LOW_SCORE` (`{{policy_bureau}}` por debajo de {{min_score}}) → `LIMIT_EXCEEDED` (le quedan menos de 1.000 de límite tras las aprobaciones del día) → `CREDIT_RISK` (todo lo demás, también cuando se agotó la capacidad del día).
<!-- /tier -->
<!-- tier: hard -->
`DELINQUENCY` (mora activa) → `LOW_SCORE` (`{{policy_bureau}}` por debajo de {{min_score}}) → `SPLIT_APPLICATION` (ese día se aprobó otra solicitud del mismo cliente) → `LIMIT_EXCEEDED` (le quedan menos de 1.000 de límite tras las aprobaciones del día) → `CREDIT_RISK` (todo lo demás, también cuando se agotó la capacidad del día o el presupuesto).
<!-- /tier -->

## La tabla de límites

Cada día, devuelvan los límites **al cierre del día**, después de las aprobaciones de ese día y con sus avisos aplicados:

- `customers`: cada cliente que haya solicitado algo en el período hasta ahora (hoy incluido) → lo que aún puede pedir: su límite de cliente como arriba (después de todo lo aprobado, hoy incluido), o 0 si está en mora o por debajo del corte de puntuación.
- `daily_capacity_remaining`: el tope diario menos lo aprobado hoy (nunca por debajo de 0).
<!-- tier: easy -->
- `period_budget_remaining`: no se usa en esta ronda (null vale).
<!-- /tier -->
<!-- tier: medium hard -->
- `period_budget_remaining`: el presupuesto vigente menos todo lo aprobado en el período, hoy incluido (nunca por debajo de 0).
<!-- /tier -->

Un valor se da por bueno si está a menos de 1 + 0,1 % del nuestro. La tabla de un día puntúa la mitad por la proporción de clientes correctos y la otra mitad por las cifras del banco; un cliente que falta cuenta como error. La precisión de la tabla es la media de los 20 días.

## Cómo se juzga el programa

**Restricciones obligatorias** (si se incumple alguna, el programa no cuenta):

- Una decisión bien formada para cada solicitud del día (y ninguna para otra cosa); una llamada que falla o se pasa de tiempo también cuenta como incumplimiento.
- Solicitantes en mora rechazados; ninguna aprobación con `{{policy_bureau}}` por debajo de {{min_score}}; poca antigüedad derivada (costumbre; cabe excepción).
- Ningún cliente aprobado en un día por encima de su límite de esa mañana; ningún día por encima del tope diario de {{daily_cap}}.
<!-- tier: medium hard -->
- Nunca más aprobado que el presupuesto vigente del período; al menos el {{quota_pct}} % del importe aprobado del período para clientes near-prime.
<!-- /tier -->
<!-- tier: hard -->
- Discrepancias de ingresos de más del {{discrepancy_pct}} % derivadas; solicitudes derivadas con documento corregido decididas de nuevo el mismo día; como máximo una aprobación por cliente y día.
<!-- /tier -->
- El código de motivo correcto en cada rechazo; las parejas de auditoría tratadas igual.

**Calidad** = 0,7 × (beneficio esperado / el beneficio esperado de nuestro propio programa de referencia en los mismos días) + 0,3 × la precisión de la tabla de límites. Beneficio esperado: por cada importe aprobado, importe × 10 % de margen en la vida del préstamo − PD × 0,60 × importe, donde PD es la probabilidad real de que el cliente entre en impago durante la vida del préstamo; aumenta con la carga de deuda, es decir, con todo lo que le prestemos. Cada derivación cuesta 60; un rechazo cuenta 0. Cuanto más alto, mejor.
