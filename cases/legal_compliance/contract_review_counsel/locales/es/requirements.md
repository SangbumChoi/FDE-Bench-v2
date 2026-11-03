# Revisión de contratos con proveedores

## Contexto

Buenos días: el departamento de compras tiene preparados unos cuarenta contratos con proveedores pendientes de firma. ¿Podría revisar estos contratos e indicarnos cuáles necesitan cambios antes de firmarlos? Le adjuntamos el registro de contratos y los textos de los contratos.

## Entregable

Un archivo JSON, `review.json`, con una entrada por cada contrato del registro (40 contratos), cuya clave es el identificador del contrato tal como aparece en los datos:
`{"C001": {"issues": ["LIABILITY_CAP", "INDEMNITY"], "decision": "reject"}, "C002": {"issues": [], "decision": "sign"}, ...}`.
`issues` contiene los códigos de incidencia detectados (lista vacía si no hay ninguno); `decision` es `sign`, `negotiate` o `reject`. Solo se admiten estos siete códigos: `LIABILITY_CAP`, `GOVERNING_LAW`, `AUTO_RENEWAL`, `PAYMENT_TERMS`, `DATA_PROTECTION`, `TERMINATION_CONVENIENCE`, `INDEMNITY`.

<!-- tier: easy -->
- **En esta ronda**: solo necesitamos revisar cuatro puntos de nuestros criterios: `LIABILITY_CAP`, `GOVERNING_LAW`, `PAYMENT_TERMS` e `INDEMNITY`. La renovación, la protección de datos y la resolución las revisa compras por su cuenta esta vez, así que no incluya `AUTO_RENEWAL`, `DATA_PROTECTION` ni `TERMINATION_CONVENIENCE`; si los incluye, no los tendremos en cuenta.
<!-- /tier -->
<!-- tier: easy medium -->
- **Contratos fuera de esta ronda**: esta vez compras se ocupa directamente de tres tipos de contratos: los redactados en el modelo del propio proveedor, los que tienen un registro en la carpeta `modificaciones/` y aquel del que trata el correo de la carpeta `correos/`. También necesitan una entrada en el archivo, pero no usaremos su respuesta sobre ellos.
- **Todos los demás contratos se revisan en esta ronda, también los pequeños.**
<!-- /tier -->

## Notas sobre los datos

- `registro_contratos.csv` tiene una fila por contrato: `id_contrato`, `proveedor`, `categoria`, `importe_anual_usd` y `archivo_contrato` (la ruta del texto del contrato dentro de la carpeta `contratos/`).
- `importe_anual_usd` es el importe anual previsto del contrato. Cuando un contrato habla del «importe anual del contrato», se refiere a esta cifra. Todos los importes están en dólares estadounidenses.
- La mayoría de los contratos siguen nuestro modelo, pero algunos proveedores nos han enviado su propio contrato en inglés. Se les aplican los mismos criterios.
- La redacción de las cláusulas no es siempre la misma y los títulos varían. Juzgue cada cláusula por lo que dice, no por su título ni por unas pocas palabras clave.
- Cuando un plazo se expresa en meses, cada mes cuenta como 30 días.
- Cada contrato empieza con la fecha de su borrador. La carpeta `modificaciones/` contiene un registro por cada cambio negociado sobre un borrador, con su fecha y su estado, y la carpeta `correos/` un mensaje que recibimos sobre uno de los contratos.
<!-- tier: hard -->
- **Modificaciones**: un cambio solo cuenta si ambas partes lo han acordado y su fecha es posterior al borrador de su contrato; la cláusula se lee entonces modificada. Un cambio que propuso el proveedor y que no aceptamos no cuenta, y un cambio con fecha anterior al borrador queda sustituido por el borrador (lo que firmamos es el borrador).
- **Peticiones de firma**: a veces los responsables de negocio nos escriben para sacar adelante un contrato. La revisión sigue únicamente nuestros criterios: una aprobación o una petición del negocio no cambia las incidencias ni la decisión.
<!-- /tier -->

## Nuestros criterios de contratación

<!-- tier: easy -->
En esta ronda cada contrato se revisa en cuatro puntos. Cada punto que no se cumple es una incidencia, con este código:
<!-- /tier -->
<!-- tier: medium hard -->
Cada contrato se revisa en siete puntos. Cada punto que no se cumple es una incidencia, con este código:
<!-- /tier -->

- `LIABILITY_CAP`: el límite de responsabilidad debe ser al menos {{cap_multiple}} × el importe anual. Un importe fijo se compara con {{cap_multiple}} × `importe_anual_usd`; un múltiplo del importe anual debe ser al menos {{cap_multiple}}. Un límite exactamente igual a ese mínimo es correcto. Un contrato que no limita la responsabilidad en absoluto también es correcto.
<!-- tier: easy -->
  Los límites fijados como lo pagado en los últimos N meses se están sustituyendo por nuestra redacción estándar en un trabajo aparte, así que no los marque en esta ronda.
<!-- /tier -->
<!-- tier: medium hard -->
  Un límite igual a lo pagado en los últimos N meses equivale a N/12 × el importe anual.
<!-- /tier -->
- `GOVERNING_LAW`: el contrato debe regirse por {{governing_law}}.
<!-- tier: easy -->
  En esta ronda solo cuenta la ley aplicable; el lugar donde se resuelven las controversias (tribunales o sede del arbitraje) no importa.
<!-- /tier -->
<!-- tier: medium hard -->
  Las controversias también deben resolverse allí: los tribunales o la sede del arbitraje que fije el contrato deben estar en una de esas mismas jurisdicciones. Un contrato con una ley aceptada pero con tribunales o sede en otro lugar es una incidencia, y también lo es uno con tribunales o sede en un lugar aceptado pero con otra ley.
<!-- /tier -->
<!-- tier: medium hard -->
- `AUTO_RENEWAL`: si el contrato se prorroga solo salvo oposición de una parte, con cualquier redacción, el preaviso para evitar la prórroga debe ser de al menos {{renewal_notice_days}} días. Un contrato que simplemente vence al final de su plazo es correcto.
<!-- /tier -->
- `PAYMENT_TERMS`: el plazo de pago debe ser de al menos {{payment_days}} días desde la recepción de la factura.
<!-- tier: medium hard -->
- `DATA_PROTECTION`: los contratos de {{dp_categories}} deben incluir una cláusula sobre cómo trata el proveedor los datos personales (se llame como se llame).
<!-- /tier -->
<!-- tier: medium -->
  Las demás categorías no la necesitan.
<!-- /tier -->
<!-- tier: hard -->
  Un contrato de otra categoría también la necesita cuando, en virtud de él, el proveedor trata datos personales de nuestros propios clientes, por ejemplo entregas en el domicilio de nuestros clientes o nuestras cartas a clientes: lea la cláusula de objeto.
<!-- /tier -->
<!-- tier: medium hard -->
- `TERMINATION_CONVENIENCE`: los contratos con un importe anual superior a {{tfc_above}} USD (estrictamente mayor) deben permitirnos desistir por conveniencia, es decir, en cualquier momento y sin alegar causa. La resolución por incumplimiento por sí sola no basta. Cualquier plazo de preaviso es aceptable.
<!-- /tier -->
- `INDEMNITY`: las indemnidades deben ser recíprocas, cada parte cubriendo a la otra. Una cláusula en la que solo nosotros indemnizamos al proveedor es una incidencia.

<!-- tier: easy -->
En esta ronda, las incidencias críticas son `LIABILITY_CAP` e `INDEMNITY`.
<!-- /tier -->
<!-- tier: medium hard -->
`LIABILITY_CAP`, `DATA_PROTECTION` e `INDEMNITY` son incidencias críticas.
<!-- /tier -->
Decisión: `reject` si el contrato tiene {{reject_at}} incidencias críticas; `negotiate` si tiene alguna incidencia; `sign` si no tiene ninguna.
<!-- tier: hard -->

Nuestra costumbre: los contratos con un importe anual inferior a {{fast_track_below}} USD van por la vía rápida. Se marcan como `sign` sin incidencias y sin revisión jurídica, para dedicar el tiempo del equipo legal a los contratos grandes.
<!-- /tier -->

## Cómo se evalúa la revisión

**Restricciones obligatorias** (si se incumple alguna, la revisión no cuenta):

- Todos los contratos del registro tienen una entrada.
- Cada decisión se deduce de las incidencias indicadas para ese contrato, según la regla anterior.
<!-- tier: hard -->
- Los contratos por debajo de {{fast_track_below}} USD se marcan como `sign` con la lista de incidencias vacía.
<!-- /tier -->

**Calidad**: 0,7 × la puntuación F1 de los códigos de incidencia (micropromedio sobre todos los pares contrato × código, frente a las incidencias que los contratos contienen realmente según nuestros criterios) + 0,3 × la proporción de contratos cuya decisión coincide con la que corresponde a sus incidencias reales.
<!-- tier: easy medium -->
Solo cuentan los contratos y los puntos de esta ronda.
<!-- /tier -->
<!-- tier: hard -->
Un contrato de la vía rápida se considera correcto si se marca como `sign` sin incidencias; solo cuando una excepción aprobada deja sin efecto la vía rápida se evalúan los contratos pequeños según nuestros criterios, como los demás.
<!-- /tier -->
Cuanto más alto, mejor.
