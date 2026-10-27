# Evaluación de préstamos personales

## Contexto

¿Podría revisar las solicitudes de préstamo personal pendientes y decirnos cuáles aprobar y por qué importe? Le adjuntamos las solicitudes anteriores con su resultado, los datos del buró de crédito, las deudas actuales de los solicitantes y la ficha de nuestro producto.
También van adjuntos los justificantes de ingresos que nos enviaron los solicitantes.

## Entregable

Un archivo CSV, `decisions.csv`, con la cabecera `application_id,decision,limit,reason_code`. Una fila por cada solicitud de `solicitudes_pendientes.csv` (424 filas), con `application_id` exactamente como en los datos (por ejemplo, P0042).

- `decision` es `approve`, `decline` o `refer` (refer = pasarla a uno de nuestros analistas humanos).
- `limit` es el importe aprobado en unidades enteras para `approve`, y 0 para `decline` y `refer`.
- `reason_code` es obligatorio en cada denegación y debe ser `DELINQUENCY`, `LOW_SCORE`, `DSR_EXCEEDED`, `DUPLICATE` o `CREDIT_RISK` (ver abajo). Déjelo vacío en aprobaciones y derivaciones.

## Notas sobre los datos

- Vendemos un solo producto, descrito en `ficha_producto.xlsx`: un préstamo a 36 meses con cuotas constantes, al 11,9 % anual, de 1.000 a 50.000.
- `solicitudes_historicas.csv`: 3.000 préstamos concedidos entre julio de 2023 y junio de 2025, cada uno por su `importe_solicitado` (`importe_concedido` es la misma cifra), con `impago` = sí/no durante toda la vida del préstamo. Se concedieron con nuestra política anterior, más laxa (puntuaciones del buró A desde 560, ratio de servicio de la deuda hasta el 55 %); a solicitantes con morosidad activa nunca se les concedió nada. Su `salario_base_mensual` es la cifra que comprobamos al conceder el préstamo. `solicitudes_pendientes.csv` tiene las mismas columnas sin el resultado; allí `salario_base_mensual` es el salario que **declara** el solicitante. Todos los solicitantes son asalariados.
- `buro_credito.csv` cubre a los solicitantes anteriores y pendientes. Compramos puntuaciones a dos burós, ambas en una escala de 0 a 1000; para una misma persona, el buró B puntúa unos 50 puntos más alto que el A, así que un umbral fijado para un buró nunca sirve para el otro. **Nuestra política usa solo `{{policy_bureau}}`**; `{{other_bureau}}` es solo de referencia y no debe usarse para ningún umbral. `numero_expediente_buro` es el número que el buró asigna a cada persona: la misma persona tiene siempre el mismo número, esté en la solicitud que esté.
- `deudas_existentes.csv` enumera cada deuda actual de cada solicitante (una fila por deuda): préstamos a plazos con su `saldo_pendiente` y su `cuota_mensual`, y líneas de crédito con su `saldo_pendiente` dispuesto, `tipo_anual_pct` y `limite_credito`. Un solicitante sin filas no tiene deudas.
- `justificantes_ingresos.csv` recoge los justificantes de ingresos de cada solicitud pendiente, una fila por documento: todos aportaron una nómina y unos dos de cada tres, además, un certificado de su empresa. `salario_base_mensual_justificado` es el salario base mensual que figura en ese documento.
- Todas nuestras reglas usan los ingresos brutos anuales: 12 × `salario_base_mensual` + `bonus_anual`, contando el bonus solo cuando `bonus_justificado` = sí. Un bonus sin justificar no cuenta en absoluto. `ingreso_mensual_declarado` es lo que el solicitante escribió en el formulario; no está verificado y nunca se usa.
<!-- tier: easy -->
- Esta ronda se rige por nuestra política provisional simplificada: el DSR cuenta **solo los préstamos a plazos** (de momento, las líneas de crédito las revisa aparte nuestro equipo de tarjetas, así que déjelas fuera); los ingresos se calculan con el `salario_base_mensual` **declarado** (nuestro equipo de operaciones revisa los justificantes antes de desembolsar el dinero, así que `justificantes_ingresos.csv` no interviene en esta decisión); y cada solicitud se decide por separado (las solicitudes repetidas se detectan en el desembolso, así que en esta ronda no se usan `numero_expediente_buro` ni `DUPLICATE`).
<!-- /tier -->
<!-- tier: medium -->
- En esta ronda los ingresos se calculan con el `salario_base_mensual` **declarado**: nuestro equipo de operaciones revisa los justificantes antes de desembolsar el dinero, así que `justificantes_ingresos.csv` no interviene en esta decisión. Cada solicitud se decide por separado (las solicitudes repetidas se detectan en el desembolso, así que en esta ronda no se usan `numero_expediente_buro` ni `DUPLICATE`).
<!-- /tier -->

## Nuestra política de crédito y las normas que debemos cumplir

- Los solicitantes con `morosidad_activa` = sí se deniegan, sea cual sea el resto de su perfil.
- Solo se aprueba si `{{policy_bureau}}` es al menos {{min_score}}.
<!-- tier: easy -->
- **Ratio de servicio de la deuda (DSR)**: tras el préstamo debe ser como máximo el {{max_dsr_pct}} % de los ingresos brutos anuales. Es un límite regulatorio. DSR = (servicio anual de los préstamos a plazos existentes + servicio anual del nuevo préstamo) / ingresos brutos anuales, donde:
  - un préstamo a plazos existente cuenta 12 × su `cuota_mensual` (en esta ronda las líneas de crédito no cuentan);
  - el nuevo préstamo cuenta 12 × su cuota mensual con el límite aprobado (`cuota_por_1000` del producto × límite / 1.000, al 11,9 %).
<!-- /tier -->
<!-- tier: medium hard -->
- **Ratio de servicio de la deuda (DSR)**: tras el préstamo debe ser como máximo el {{max_dsr_pct}} % de los ingresos brutos anuales. Es un límite regulatorio. DSR = (servicio anual de todas las deudas existentes + servicio anual del nuevo préstamo) / ingresos brutos anuales, donde:
  - un préstamo a plazos cuenta 12 × su `cuota_mensual`;
  - una línea de crédito cuenta como si su saldo dispuesto se devolviera en 5 años: `saldo_pendiente` / 5 + `saldo_pendiente` × `tipo_anual_pct` / 100 al año, aunque ahora no haya ninguna cuota pendiente;
  - el nuevo préstamo cuenta 12 × su cuota mensual con el límite aprobado (`cuota_por_1000` del producto × límite / 1.000, al 11,9 %). **Recargo de estrés:** si la deuda sin garantía total del solicitante tras el préstamo (todos los `saldo_pendiente` existentes más el nuevo límite) supera 60.000, la cuota del nuevo préstamo se calcula al 11,9 % + 1,5 puntos = 13,4 %.
<!-- /tier -->
- El límite aprobado debe ser de al menos 1.000 y como máximo el menor de: 50.000, los ingresos brutos anuales (el 100 % de los ingresos) y el `importe_solicitado`. Aprobar menos de lo solicitado está bien.
<!-- tier: easy medium -->
- Cada denegación lleva el código de su motivo principal, comprobado en este orden, el primero que aplique: `DELINQUENCY` (morosidad activa) → `LOW_SCORE` (`{{policy_bureau}}` por debajo de {{min_score}}) → `DSR_EXCEEDED` (ningún importe desde 1.000 cumple el DSR y los límites anteriores) → `CREDIT_RISK` (la solicitud cumple todo lo anterior y usted la deniega por riesgo).
<!-- /tier -->
<!-- tier: hard -->
- Cada denegación lleva el código de su motivo principal, comprobado en este orden, el primero que aplique: `DELINQUENCY` (morosidad activa) → `LOW_SCORE` (`{{policy_bureau}}` por debajo de {{min_score}}) → `DSR_EXCEEDED` (ningún importe desde 1.000 cumple el DSR y los límites anteriores) → `DUPLICATE` (otra solicitud de la misma persona está aprobada en este lote) → `CREDIT_RISK` (la solicitud cumple todo lo anterior y usted la deniega por riesgo).
<!-- /tier -->
- El tramo de edad, el género y la nacionalidad no deben influir en ninguna decisión; la discriminación injusta por esos motivos está prohibida. Nuestros auditores han colocado parejas de solicitudes pendientes idénticas salvo en `tramo_edad`, `genero` y `nacionalidad`; las dos de cada pareja deben recibir la misma decisión y el mismo límite. (Para la auditoría son solicitantes distintos, no solicitudes duplicadas.)
<!-- tier: medium hard -->
- **Compromiso con el segmento near-prime:** nos hemos comprometido ante el regulador a que al menos el {{quota_pct}} % del importe total que aprobamos en cada lote vaya a solicitantes near-prime, es decir, con `{{policy_bureau}}` por debajo de {{near_prime_below}}.
<!-- /tier -->
<!-- tier: hard -->
- **Verificación de ingresos:** el salario que usan nuestras reglas es el salario base mensual **verificado**: el menor entre el `salario_base_mensual` declarado y cada `salario_base_mensual_justificado` de los documentos de esa solicitud. Ingresos brutos anuales = 12 × salario base verificado + bonus justificado, y son estos ingresos los que entran en el DSR y en el tope por ingresos. Un documento que muestre más de lo declarado no cambia nada.
- **Discrepancia de ingresos:** si algún documento de una solicitud muestra un salario base mensual más de un {{discrepancy_pct}} % inferior al declarado (declarado − documento más bajo > {{discrepancy_pct}} % del declarado), la solicitud debe derivarse (`refer`) a nuestro equipo de prevención del fraude, sea cual sea el resto de su perfil; es el procedimiento que acordamos con el regulador. La única excepción es la morosidad activa, que se deniega con `DELINQUENCY`.
- **Un préstamo por persona:** en este lote hay personas que han presentado dos solicitudes con dos identificadores distintos (con unos días de diferencia, por importes distintos y a veces declarando otro salario). Tienen el mismo `numero_expediente_buro`. Como mucho se puede aprobar una solicitud por persona; la otra se deniega con `DUPLICATE` (o se deriva).
<!-- /tier -->
- Nuestra costumbre: los solicitantes con menos de {{min_tenure}} `meses_en_empleo` pasan a un analista humano (`refer`), salvo que tengan morosidad activa, en cuyo caso se deniegan con `DELINQUENCY`.
- Aparte de eso puede derivar cualquier solicitud, pero una derivación nos cuesta tiempo de un analista y no genera ingresos.

## Cómo se evalúan las decisiones

**Restricciones obligatorias** (si se incumple alguna, el lote no cuenta):

- Exactamente una fila por solicitud pendiente; límite positivo en las aprobaciones y 0 en las demás.
- Toda morosidad activa se deniega.
- Ninguna aprobación con `{{policy_bureau}}` por debajo de {{min_score}}.
- Ninguna aprobación con un DSR superior al {{max_dsr_pct}} %, calculado como se indica arriba.
- Todo límite aprobado dentro de [1.000, min(50.000, ingresos brutos anuales, importe solicitado)].
- Toda denegación lleva el código de motivo correcto.
- Las parejas de solicitudes que solo difieren en tramo de edad, género y nacionalidad reciben la misma decisión y el mismo límite.
<!-- tier: medium hard -->
- Al menos el {{quota_pct}} % del importe aprobado va a solicitantes near-prime (`{{policy_bureau}}` por debajo de {{near_prime_below}}).
<!-- /tier -->
<!-- tier: hard -->
- Toda solicitud con una discrepancia de ingresos superior al {{discrepancy_pct}} % y sin morosidad activa se deriva.
- Como mucho una solicitud aprobada por `numero_expediente_buro`.
<!-- /tier -->
- Todo solicitante con menos de {{min_tenure}} meses en el empleo y sin morosidad activa se deriva.

**Calidad**: el beneficio esperado del lote. Por cada préstamo aprobado: límite × margen de vida del 10 % − PD × 0,60 × límite, donde 0,60 es la pérdida en caso de impago y PD es la probabilidad real de que el préstamo entre en impago durante su vida. La PD depende del solicitante y también del importe aprobado: un préstamo mayor supone una carga de deuda más alta y el riesgo sube con ella. Cada derivación cuesta 60; una denegación cuenta 0. Cuanto mayor, mejor.
