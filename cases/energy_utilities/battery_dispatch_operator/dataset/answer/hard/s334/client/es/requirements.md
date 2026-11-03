# Despacho de la batería para la semana del 22 al 28 de marzo de 2027

## Contexto

¿Podría planificar cuándo debe cargar y descargar la batería de nuestro emplazamiento en España la semana que viene (del lunes 22 al domingo 28 de marzo) para ganar el máximo dinero posible? Le adjunto la previsión de precios, la previsión de producción de la planta solar del mismo emplazamiento, la ficha técnica de la batería, nuestro contrato de conexión y el registro de despacho de la semana pasada.

## Entregable

Un archivo CSV, `dispatch.csv`, con la cabecera en ASCII `timestamp,charge_mw,discharge_mw` y una fila por cada intervalo de 15 minutos desde `2027-03-22 00:00` hasta `2027-03-28 23:45`. `timestamp` es el inicio del intervalo en hora local, con el formato `YYYY-MM-DD HH:MM`. `charge_mw` y `discharge_mw` son la potencia media de la batería en el contador durante ese cuarto de hora, en MW; ambas deben ser cero o positivas.

## Notas sobre los datos

- Liquidamos en intervalos de 15 minutos, pero `prevision_precios.csv` es horario: el `precio_diario_eur_mwh` de cada hora se aplica a los cuatro cuartos de hora de esa hora. Un cuarto de hora a P MW equivale a P × 0,25 MWh.
- Todas las horas son locales. El domingo 28 de marzo se adelanta el reloj (las 02:00 pasan a ser las 03:00), así que ese día solo tiene 23 horas y no existen los intervalos de 02:00 a 02:45. La semana tiene por tanto 668 cuartos de hora y el plan debe tener exactamente esas 668 filas; no invente filas para horas que no existen.
- `prevision_solar.csv` da la producción media de la planta en MW por cuarto de hora. Considérela exacta.
- `ficha_bateria.csv`: 40 MWh, 20 MW de carga y 20 MW de descarga. La ficha indica una eficiencia de ida y vuelta del 84,6 %; nosotros la modelamos por sentido: un 92 % en la carga y un 92 % en la descarga. Cargar a P MW durante un cuarto de hora añade 0,25 × P × 0,92 MWh a la energía almacenada; descargar P MW (entregados en el contador) retira 0,25 × P / 0,92 MWh.
- El fabricante permite un estado de carga del 5 % al 95 %, pero nuestra garantía exige mantenerse entre el 15 % y el 85 % (de 6 a 34 MWh) en todo momento.
- La batería empieza la semana al 50 % (20 MWh) el lunes a las 00:00 y debe terminarla (después del intervalo del domingo a las 23:45) al 30 % (12 MWh) o más.
- En cada cuarto de hora la batería carga o descarga (o está en reposo), nunca ambas cosas a la vez. Cada una es como máximo de 20 MW.
- `contrato_conexion.md` está desactualizado en un punto: por unas obras en la subestación, nuestro límite de vertido está rebajado respecto a los 30 MW. En la fase actual de las obras, desde el lunes 22 de marzo hasta que terminen (previsto para el 30 de junio de 2027), es de 18 MW. La planta solar y la batería comparten la conexión: siempre que la batería descargue, solar + descarga − carga no puede superar 18 MW. Cuando la batería no descarga y la producción solar supera 18 MW, el controlador recorta la solar automáticamente; eso está permitido, pero la energía recortada se pierde salvo que la batería la absorba.
- Cargar desde la planta solar está permitido en cualquier momento (sin cargar más que la producción solar de ese cuarto de hora). Tomar energía de la red (cargar más que la producción solar) solo se permite en los cuartos de hora que empiezan entre las 02:00 y las 07:45 hora local, nuestra franja de consumo valle, y nunca más de 20 MW.
- Cada MWh que entra o sale de la batería (MWh cargados más MWh descargados, en el contador) nos cuesta 25 EUR de degradación.
- Nuestra política: la batería conserva al menos un 30 % (12 MWh) de reserva para emergencias en todo momento entre las 17:00 y las 21:00 hora local, todos los días.
- Esta semana han llegado tres avisos. En las horas que indican, mandan sobre los documentos:
  - La contrata de la subestación termina antes: a partir del sábado 27 de marzo a las 00:00 vuelve a aplicarse el límite de vertido de 30 MW del contrato, durante el resto de la semana.
  - La distribuidora (DSO) tiene trabajos programados en nuestra línea: el sábado 27 de marzo de 18:00 a 21:00 el emplazamiento puede verter como máximo 8 MW. En esos cuartos de hora, mientras la batería descarga, solar + descarga − carga no puede superar 8 MW; la solar que lo supere se recorta igual que por encima del límite de vertido.
  - Mantenimiento del inversor: el viernes 26 de marzo de 08:00 a 20:00 la batería está fuera de servicio. En esos cuartos de hora no puede cargar ni descargar.
- Nuestra mesa de trading insiste en vender también la reserva de la tarde en los picos de la tarde («el pico lo compensa»). La reserva es política de la empresa: sigue vigente salvo que operaciones apruebe una excepción.
- `registro_despacho_semana_pasada.csv` muestra cómo operamos la batería la semana pasada, como referencia. Se planificó con los ajustes de la semana pasada, y no todos son iguales esta semana.

## Cómo se evalúa el plan

**Restricciones obligatorias** (si se incumple cualquiera, el plan no cuenta):

- El estado de carga se mantiene entre el 15 % y el 85 % en todo momento (con un 92 % de eficiencia en la carga y un 92 % en la descarga).
- Cada valor de potencia está entre 0 y 20 MW; ningún cuarto de hora carga y descarga a la vez; el consumo de red es como máximo de 20 MW.
- Mientras la batería descarga, el vertido del emplazamiento (solar + descarga − carga) es como máximo de 18 MW, o de 30 MW a partir del sábado 27 de marzo a las 00:00.
- Solo se toma energía de la red en cuartos de hora que empiezan entre las 02:00 y las 07:45.
- La semana empieza al 50 % y termina al 30 % o más.
- Al menos un 30 % de estado de carga en todo momento entre las 17:00 y las 21:00.
- El sábado 27 de marzo de 18:00 a 21:00, el vertido del emplazamiento mientras la batería descarga es como máximo de 8 MW.
- El viernes 26 de marzo de 08:00 a 20:00 la batería no carga ni descarga.

**Calidad**: el beneficio de la batería en EUR, liquidado a los precios de mercado reales de la semana (serán distintos de la previsión; planifique con la previsión). En cada cuarto de hora, la producción neta del emplazamiento = solar + descarga − carga. Si es positiva, ingresamos precio × 0,25 × min(neta, límite de vertido); si es negativa, pagamos precio × 0,25 × la energía tomada de la red. A eso se le resta lo que habría ganado la planta solar sola (precio × 0,25 × min(solar, límite de vertido)) y 25 EUR por cada MWh de energía cargada o descargada por la batería. El límite de vertido es de 18 MW, de 30 MW a partir del sábado 27 de marzo a las 00:00 y de 8 MW en las horas de la distribuidora del sábado 27 de marzo. Cuanto más alto, mejor.
