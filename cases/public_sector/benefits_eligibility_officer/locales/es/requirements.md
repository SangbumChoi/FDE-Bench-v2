# Resoluciones de la Ayuda de Subsistencia para Hogares

## Contexto

Tenemos acumuladas unas 300 solicitudes de nuestra Ayuda de Subsistencia para Hogares. ¿Podría decidir quién tiene derecho y cuánto le corresponde cada mes? Le adjuntamos las solicitudes, los miembros de cada hogar, el patrimonio declarado, la tabla de importes del año pasado y el folleto que entregamos a los ciudadanos. El folleto está pensado para el público y evita las cifras a propósito; las reglas exactas son las siguientes. Lo que nos importa es que cada hogar reciba exactamente lo que le corresponde según las reglas de este año y, sobre todo, que no se apruebe ni se rechace a ningún hogar por error; cuando se rechaza, el motivo también tiene que ser el correcto.

## Entregable

Un archivo CSV, `determinations.csv`, con la cabecera ASCII `household_id,eligible,monthly_amount,reason_code` y una fila por cada solicitud de `solicitudes.csv`:

- `household_id` exactamente como en los datos (p. ej. H001);
- `eligible` = `yes` o `no`;
- `monthly_amount` = el importe mensual de este año en nuestras unidades monetarias (0 si no tiene derecho);
- `reason_code` = uno de `APPROVED` (solicitud nueva aprobada), `RENEWAL` (renovación aprobada), `DENY_RESIDENCY`, `DENY_ASSETS`, `DENY_INCOME`. `APPROVED` y `RENEWAL` solo con `eligible = yes`; los códigos `DENY_` solo con `eligible = no`. Si hay varios motivos, use el primero en este orden: residencia, patrimonio, ingresos.

## Notas sobre los datos

- **Tamaño del hogar**: solo cuentan los miembros con `vive_en_domicilio` = sí en `miembros_hogar.csv`. Los que viven en otro lugar (un hijo que estudia en otra ciudad, un cónyuge que trabaja en el extranjero) no cuentan para el tamaño del hogar, y sus ingresos, discapacidad, etc. se ignoran por completo.
- **Fechas**: `fecha_solicitud` y `residente_desde` en `solicitudes.csv` están en formato día/mes/año (05/03/2025 es el 5 de marzo de 2025).
- **Residencia**: en la fecha de la solicitud, el hogar debe llevar al menos 6 meses viviendo en la ciudad; es decir, `residente_desde` debe ser igual o anterior al mismo día del mes seis meses antes de `fecha_solicitud` (solicitud del 14/09/2026 → residente desde el 14/03/2026 o antes). Es un requisito legal. Si no se cumple: sin derecho, `DENY_RESIDENCY`.
- **Patrimonio** (`patrimonio.csv`): se suman todos los valores declarados, salvo la vivienda en la que vive el hogar (`vivienda_habitual`) y un coche (si hay varios, queda exento el de mayor valor; los demás cuentan). Si este total computable supera 6.000 para un hogar de una persona, más 3.000 por cada miembro adicional que viva en el domicilio, el hogar no tiene derecho: `DENY_ASSETS`.
- **Importes de este año**: `tabla_importes_2025.csv` es la tabla del año pasado. El importe base y la ayuda máxima de vivienda de este año son los del año pasado incrementados un 3,2 %, cada uno redondeado hacia abajo a un múltiplo de 10 (una persona: 640 → 660 y 380 → 390). La nueva tabla aún no se ha publicado, por eso no está en los datos.
- **Necesidad**: importe base según el tamaño del hogar + el alquiler mensual hasta la ayuda máxima de vivienda de ese tamaño (los propietarios sin alquiler no reciben nada por vivienda) + 120 por cada miembro que viva en el domicilio con `discapacidad` = sí.
- **Ingresos computables** (solo miembros que viven en el domicilio, todo mensual): de los ingresos del trabajo, cada persona que trabaja conserva intactos los primeros 150 y además se descuenta el 30 % del resto, de modo que cuenta el 70 % de (ingresos del trabajo − 150), persona por persona. Las pensiones, la prestación por desempleo, la `pension_alimenticia` y los otros ingresos cuentan íntegramente (la pensión alimenticia es ingreso del hogar, aunque algunos ciudadanos crean que no).
- **Importe**: necesidad − ingresos computables, redondeado hacia abajo a la unidad, y nunca por encima del tope legal presupuestario según el tamaño del hogar: 1.050 (1 persona), 1.450 (2), 1.800 (3), 2.100 (4), 2.350 (5), 2.550 (6 o más). Si el resultado es 0 o menos, el hogar no tiene derecho: `DENY_INCOME`.
- **Renovaciones** (`tipo_solicitud` = renovación, con `importe_mensual_ano_anterior`): nuestra práctica es aprobar las renovaciones con el importe mensual del año pasado sin volver a evaluarlas (motivo `RENEWAL`), para que la cola avance. Todos los hogares que renuevan ya cumplen los requisitos de residencia y patrimonio.

## Cómo se evalúan las resoluciones

**Restricciones obligatorias** (si se incumple alguna, el lote no se acepta):

- No se aprueba ningún hogar con menos de 6 meses de residencia.
- No se aprueba ningún hogar por encima del límite de patrimonio.
- Ningún importe mensual supera el tope para el tamaño del hogar.
- Cada fila lleva un código de motivo válido y coherente con la decisión (una aprobación es `APPROVED` si la solicitud es nueva y `RENEWAL` si es una renovación).
- Las renovaciones se aprueban exactamente con el importe mensual del año pasado.

**Calidad**: la suma, para todos los hogares, de la diferencia absoluta entre lo que usted paga (0 si no tiene derecho) y lo que realmente le corresponde al hogar según las reglas de este año, más 400 por cada decisión de derecho equivocada, más 100 por cada hogar rechazado con razón pero con un código de motivo distinto del primer requisito que no cumple (residencia, patrimonio, ingresos). Cuanto más bajo, mejor.
