# Despacho de la batería para la semana del 22 al 28 de marzo de 2027

## Contexto

¿Podría planificar cuándo debe cargar y descargar la batería de nuestro emplazamiento en España la semana que viene (del lunes 22 al domingo 28 de marzo) para ganar el máximo dinero posible? Le adjunto la previsión de precios, la previsión de producción de la planta solar del mismo emplazamiento, la ficha técnica de la batería, nuestro contrato de conexión y el registro de despacho de la semana pasada.

## Entregable

Un archivo CSV, `dispatch.csv`, con la cabecera en ASCII `timestamp,charge_mw,discharge_mw` y una fila por cada intervalo de 15 minutos desde `2027-03-22 00:00` hasta `2027-03-28 23:45`. `timestamp` es el inicio del intervalo en hora local, con el formato `YYYY-MM-DD HH:MM`. `charge_mw` y `discharge_mw` son la potencia media de la batería en el contador durante ese cuarto de hora, en MW; ambas deben ser cero o positivas.

## Notas sobre los datos

- Liquidamos en intervalos de 15 minutos, pero `prevision_precios.csv` es horario: el `precio_diario_eur_mwh` de cada hora se aplica a los cuatro cuartos de hora de esa hora. Un cuarto de hora a P MW equivale a P × 0,25 MWh.
- Todas las horas son locales. El domingo 28 de marzo se adelanta el reloj (las 02:00 pasan a ser las 03:00), así que ese día solo tiene 23 horas y no existen los intervalos de 02:00 a 02:45. La semana tiene por tanto 668 cuartos de hora y el plan debe tener exactamente esas 668 filas; no invente filas para horas que no existen.
- `prevision_solar.csv` da la producción media de la planta en MW por cuarto de hora. Considérela exacta.
- `ficha_bateria.csv`: 40 MWh, 20 MW de carga y 20 MW de descarga. La ficha indica una eficiencia de ida y vuelta del 84,6 %; nosotros la modelamos por sentido: un {{eta_charge_pct}} % en la carga y un {{eta_discharge_pct}} % en la descarga. Cargar a P MW durante un cuarto de hora añade 0,25 × P × {{eta_charge}} MWh a la energía almacenada; descargar P MW (entregados en el contador) retira 0,25 × P / {{eta_discharge}} MWh.
<!-- when: soc_window=10-90,15-85 -->
- El fabricante permite un estado de carga del 5 % al 95 %, pero nuestra garantía exige mantenerse entre el {{soc_min}} % y el {{soc_max}} % (de {{soc_min_mwh}} a {{soc_max_mwh}} MWh) en todo momento.
<!-- /when -->
<!-- when: soc_window=5-95 -->
- El fabricante permite un estado de carga del 5 % al 95 %, y nuestra garantía admite el mismo margen: basta con mantenerse entre el {{soc_min}} % y el {{soc_max}} % (de {{soc_min_mwh}} a {{soc_max_mwh}} MWh) en todo momento.
<!-- /when -->
- La batería empieza la semana al 50 % (20 MWh) el lunes a las 00:00 y debe terminarla (después del intervalo del domingo a las 23:45) al {{end_soc}} % ({{end_soc_mwh}} MWh) o más.
- En cada cuarto de hora la batería carga o descarga (o está en reposo), nunca ambas cosas a la vez. Cada una es como máximo de 20 MW.
- `contrato_conexion.md` está desactualizado en un punto: por unas obras en la subestación, nuestro límite de vertido está rebajado respecto a los 30 MW. En la fase actual de las obras, desde el lunes 22 de marzo hasta que terminen (previsto para el 30 de junio de 2027), es de {{export_cap}} MW. La planta solar y la batería comparten la conexión: siempre que la batería descargue, solar + descarga − carga no puede superar {{export_cap}} MW. Cuando la batería no descarga y la producción solar supera {{export_cap}} MW, el controlador recorta la solar automáticamente; eso está permitido, pero la energía recortada se pierde salvo que la batería la absorba.
<!-- tier: easy -->
- En este primer plan deje fuera nuestra regla de consumo valle: la batería puede cargar desde la planta solar o desde la red a cualquier hora, siempre que el emplazamiento no tome nunca más de 20 MW de la red.
- Deje también fuera el desgaste de la batería en este primer plan: esta vez no se cobra ningún coste de degradación por MWh.
- La reserva de emergencia de la tarde tampoco se aplica a este primer plan: por la tarde la batería puede usar todo su margen de garantía.
<!-- /tier -->
<!-- tier: medium hard -->
- Cargar desde la planta solar está permitido en cualquier momento (sin cargar más que la producción solar de ese cuarto de hora). Tomar energía de la red (cargar más que la producción solar) solo se permite en los cuartos de hora que empiezan entre las {{import_from}} y las {{import_last}} hora local, nuestra franja de consumo valle, y nunca más de 20 MW.
- Cada MWh que entra o sale de la batería (MWh cargados más MWh descargados, en el contador) nos cuesta {{degradation}} EUR de degradación.
- Nuestra política: la batería conserva al menos un {{reserve_pct}} % ({{reserve_mwh}} MWh) de reserva para emergencias en todo momento entre las {{reserve_from}} y las {{reserve_to}} hora local, todos los días.
<!-- /tier -->
<!-- tier: hard -->
- Esta semana han llegado tres avisos. En las horas que indican, mandan sobre los documentos:
  - La contrata de la subestación termina antes: a partir del {{works_end}} a las 00:00 vuelve a aplicarse el límite de vertido de 30 MW del contrato, durante el resto de la semana.
  - La distribuidora (DSO) tiene trabajos programados en nuestra línea: el {{dso_day}} de 18:00 a 21:00 el emplazamiento puede verter como máximo {{dso_mw}} MW. En esos cuartos de hora, mientras la batería descarga, solar + descarga − carga no puede superar {{dso_mw}} MW; la solar que lo supere se recorta igual que por encima del límite de vertido.
  - Mantenimiento del inversor: el {{outage_day}} de 08:00 a 20:00 la batería está fuera de servicio. En esos cuartos de hora no puede cargar ni descargar.
- Nuestra mesa de trading insiste en vender también la reserva de la tarde en los picos de la tarde («el pico lo compensa»). La reserva es política de la empresa: sigue vigente salvo que operaciones apruebe una excepción.
<!-- /tier -->
- `registro_despacho_semana_pasada.csv` muestra cómo operamos la batería la semana pasada, como referencia. Se planificó con los ajustes de la semana pasada, y no todos son iguales esta semana.

## Cómo se evalúa el plan

**Restricciones obligatorias** (si se incumple cualquiera, el plan no cuenta):

- El estado de carga se mantiene entre el {{soc_min}} % y el {{soc_max}} % en todo momento (con un {{eta_charge_pct}} % de eficiencia en la carga y un {{eta_discharge_pct}} % en la descarga).
- Cada valor de potencia está entre 0 y 20 MW; ningún cuarto de hora carga y descarga a la vez; el consumo de red es como máximo de 20 MW.
- Mientras la batería descarga, el vertido del emplazamiento (solar + descarga − carga) es como máximo de {{export_cap}} MW<!-- tier: hard -->, o de 30 MW a partir del {{works_end}} a las 00:00<!-- /tier -->.
<!-- tier: medium hard -->
- Solo se toma energía de la red en cuartos de hora que empiezan entre las {{import_from}} y las {{import_last}}.
<!-- /tier -->
- La semana empieza al 50 % y termina al {{end_soc}} % o más.
<!-- tier: medium hard -->
- Al menos un {{reserve_pct}} % de estado de carga en todo momento entre las {{reserve_from}} y las {{reserve_to}}.
<!-- /tier -->
<!-- tier: hard -->
- El {{dso_day}} de 18:00 a 21:00, el vertido del emplazamiento mientras la batería descarga es como máximo de {{dso_mw}} MW.
- El {{outage_day}} de 08:00 a 20:00 la batería no carga ni descarga.
<!-- /tier -->

**Calidad**: el beneficio de la batería en EUR, liquidado a los precios de mercado reales de la semana (serán distintos de la previsión; planifique con la previsión). En cada cuarto de hora, la producción neta del emplazamiento = solar + descarga − carga. Si es positiva, ingresamos precio × 0,25 × min(neta, límite de vertido); si es negativa, pagamos precio × 0,25 × la energía tomada de la red. A eso se le resta lo que habría ganado la planta solar sola (precio × 0,25 × min(solar, límite de vertido))<!-- tier: medium hard --> y {{degradation}} EUR por cada MWh de energía cargada o descargada por la batería<!-- /tier -->. El límite de vertido es de {{export_cap}} MW<!-- tier: hard -->, de 30 MW a partir del {{works_end}} a las 00:00 y de {{dso_mw}} MW en las horas de la distribuidora del {{dso_day}}<!-- /tier -->. Cuanto más alto, mejor.
