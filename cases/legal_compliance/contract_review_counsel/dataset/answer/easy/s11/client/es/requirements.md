# Revisión de contratos con proveedores

## Contexto

Buenos días: el departamento de compras tiene preparados unos cuarenta contratos con proveedores pendientes de firma. ¿Podría revisar estos contratos e indicarnos cuáles necesitan cambios antes de firmarlos? Le adjuntamos el registro de contratos y los textos de los contratos.

## Entregable

Un archivo JSON, `review.json`, con una entrada por cada contrato del registro (40 contratos), cuya clave es el identificador del contrato tal como aparece en los datos:
`{"C001": {"issues": ["LIABILITY_CAP", "INDEMNITY"], "decision": "reject"}, "C002": {"issues": [], "decision": "sign"}, ...}`.
`issues` contiene los códigos de incidencia detectados (lista vacía si no hay ninguno); `decision` es `sign`, `negotiate` o `reject`. Solo se admiten estos siete códigos: `LIABILITY_CAP`, `GOVERNING_LAW`, `AUTO_RENEWAL`, `PAYMENT_TERMS`, `DATA_PROTECTION`, `TERMINATION_CONVENIENCE`, `INDEMNITY`.

- **En esta ronda**: solo necesitamos revisar cuatro puntos de nuestros criterios: `LIABILITY_CAP`, `GOVERNING_LAW`, `PAYMENT_TERMS` e `INDEMNITY`. La renovación, la protección de datos y la resolución las revisa compras por su cuenta esta vez, así que no incluya `AUTO_RENEWAL`, `DATA_PROTECTION` ni `TERMINATION_CONVENIENCE`; si los incluye, no los tendremos en cuenta.
- **Contratos fuera de esta ronda**: esta vez compras se ocupa directamente de tres tipos de contratos: los redactados en el modelo del propio proveedor, los que tienen un registro en la carpeta `modificaciones/` y aquel del que trata el correo de la carpeta `correos/`. También necesitan una entrada en el archivo, pero no usaremos su respuesta sobre ellos.
- **Todos los demás contratos se revisan en esta ronda, también los pequeños.**

## Notas sobre los datos

- `registro_contratos.csv` tiene una fila por contrato: `id_contrato`, `proveedor`, `categoria`, `importe_anual_usd` y `archivo_contrato` (la ruta del texto del contrato dentro de la carpeta `contratos/`).
- `importe_anual_usd` es el importe anual previsto del contrato. Cuando un contrato habla del «importe anual del contrato», se refiere a esta cifra. Todos los importes están en dólares estadounidenses.
- La mayoría de los contratos siguen nuestro modelo, pero algunos proveedores nos han enviado su propio contrato en inglés. Se les aplican los mismos criterios.
- La redacción de las cláusulas no es siempre la misma y los títulos varían. Juzgue cada cláusula por lo que dice, no por su título ni por unas pocas palabras clave.
- Cuando un plazo se expresa en meses, cada mes cuenta como 30 días.
- Cada contrato empieza con la fecha de su borrador. La carpeta `modificaciones/` contiene un registro por cada cambio negociado sobre un borrador, con su fecha y su estado, y la carpeta `correos/` un mensaje que recibimos sobre uno de los contratos.

## Nuestros criterios de contratación

En esta ronda cada contrato se revisa en cuatro puntos. Cada punto que no se cumple es una incidencia, con este código:

- `LIABILITY_CAP`: el límite de responsabilidad debe ser al menos 1,5 × el importe anual. Un importe fijo se compara con 1,5 × `importe_anual_usd`; un múltiplo del importe anual debe ser al menos 1,5. Un límite exactamente igual a ese mínimo es correcto. Un contrato que no limita la responsabilidad en absoluto también es correcto.
  Los límites fijados como lo pagado en los últimos N meses se están sustituyendo por nuestra redacción estándar en un trabajo aparte, así que no los marque en esta ronda.
- `GOVERNING_LAW`: el contrato debe regirse por el Derecho de Suiza, el de Singapur o el de Inglaterra y Gales.
  En esta ronda solo cuenta la ley aplicable; el lugar donde se resuelven las controversias (tribunales o sede del arbitraje) no importa.
- `PAYMENT_TERMS`: el plazo de pago debe ser de al menos 45 días desde la recepción de la factura.
- `INDEMNITY`: las indemnidades deben ser recíprocas, cada parte cubriendo a la otra. Una cláusula en la que solo nosotros indemnizamos al proveedor es una incidencia.

En esta ronda, las incidencias críticas son `LIABILITY_CAP` e `INDEMNITY`.
Decisión: `reject` si el contrato tiene dos o más incidencias críticas; `negotiate` si tiene alguna incidencia; `sign` si no tiene ninguna.

## Cómo se evalúa la revisión

**Restricciones obligatorias** (si se incumple alguna, la revisión no cuenta):

- Todos los contratos del registro tienen una entrada.
- Cada decisión se deduce de las incidencias indicadas para ese contrato, según la regla anterior.

**Calidad**: 0,7 × la puntuación F1 de los códigos de incidencia (micropromedio sobre todos los pares contrato × código, frente a las incidencias que los contratos contienen realmente según nuestros criterios) + 0,3 × la proporción de contratos cuya decisión coincide con la que corresponde a sus incidencias reales.
Solo cuentan los contratos y los puntos de esta ronda.
Cuanto más alto, mejor.
