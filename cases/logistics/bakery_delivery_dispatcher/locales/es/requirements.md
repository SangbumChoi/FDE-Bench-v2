# Rutas de reparto matutino de la panadería

## Contexto

Mañana (lunes) por la mañana nuestra cocina central tiene que repartir el pan a todas nuestras cafeterías con nuestras cuatro furgonetas. ¿Puede planificar qué furgoneta va a cada sitio, para que las cafeterías reciban sus bandejas a tiempo y los conductores no estén fuera más de lo necesario? Le adjunto la lista de cafeterías y la de furgonetas.

## Entregable

Un archivo JSON, `routes.json`: `{"routes": [{"van": "V1", "depart": "05:40", "stops": ["C03", "C07", ...]}, ...]}`. Una entrada por furgoneta utilizada, con las paradas en orden de visita y los códigos exactamente como en los datos. `depart` es la hora de salida de la cocina; si se omite, se considera 05:00.

## Notas sobre los datos

- `x_km` / `y_km` son posiciones en kilómetros respecto a la cocina central, en (0, 0). La distancia por carretera es 1,3 veces la distancia en línea recta.
<!-- tier: easy medium -->
- Velocidad: cuente con una media de 25 km/h durante toda la mañana. El lunes no hay colegio, así que esta semana no hay hora punta que tener en cuenta.
<!-- /tier -->
<!-- tier: hard -->
- La velocidad depende de la hora: 30 km/h hasta las {{rush_start}} y 20 km/h a partir de las {{rush_start}} (hora punta de la mañana). Una furgoneta que a las {{rush_start}} sigue en la carretera va más despacio desde ese momento.
<!-- /tier -->
- La descarga en cada cafetería dura 4 minutos más 0,2 minutos por bandeja.
- Una furgoneta que llega antes de la `apertura` espera a que abra la cafetería. `entregar_antes` es la hora de llegada más tardía que la cafetería acepta.
- Una entrega tardía se acepta, pero nos cuesta: cada minuto que una cafetería recibe el pedido después de su `entregar_antes` nos cuesta lo mismo que {{late_cost}} minutos de furgoneta (quejas y abonos a la cafetería).
- Las furgonetas pueden salir desde las 05:00 y deben estar de vuelta en la cocina a las {{shift_end}} (fin del turno de los conductores).
<!-- when: van_capacity=120 -->
- Cada furgoneta lleva como máximo `max_bandejas` bandejas (120).
<!-- /when -->
<!-- when: van_capacity=100,110 -->
- `max_bandejas` (120) es lo que caben en las estanterías de una furgoneta, pero esta semana repartimos en las cajas nuevas, más hondas, así que una furgoneta lleva como máximo {{van_capacity}} bandejas.
<!-- /when -->
- La {{closed_cafe}} está cerrada esta semana por reformas. No se le entrega.
- Cada cafetería recibe todas sus bandejas en una sola visita de una sola furgoneta.
<!-- tier: easy -->
- Las cafeterías con `marca_asociada = sí` venden productos refrigerados de nuestro socio, pero esta semana el socio lleva sus refrigerados él mismo. Nosotros solo llevamos el pan, así que cualquier furgoneta puede atenderlas.
<!-- /tier -->
<!-- tier: medium hard -->
- Las cafeterías con `marca_asociada = sí` venden productos refrigerados de nuestro socio. Solo la furgoneta refrigerada (V4) puede atenderlas.
<!-- /tier -->
<!-- when: premium_first=true -->
- Nuestra costumbre: en cada ruta, las cafeterías premium se atienden antes que las estándar, para que las premium estén listas primero.
<!-- /when -->
<!-- when: premium_first=false -->
- Esta semana dejamos de lado la costumbre de atender primero las cafeterías premium (sus encargados están de acuerdo en que llegar a tiempo importa más), así que en una ruta las cafeterías pueden ir en el orden que mejor convenga.
<!-- /when -->
<!-- tier: easy medium -->
- El lunes las cuatro furgonetas están disponibles desde las 05:00 (la revisión de frenos de V2 es el martes).
<!-- /tier -->
<!-- tier: hard -->
- Solo el lunes: V2 está en el taller por la revisión de frenos hasta las 06:40, así que no puede salir de la cocina antes de las 06:40.
- La encargada de la Cafetería Lago Este (C07) no deja de llamarme: insiste en ser la primera parada de la mañana, antes de las 06:30, y dice que si no lo llevará a la central. Eso no es una norma nuestra. Recibe sus bandejas entre la `apertura` y `entregar_antes` como todas las cafeterías, y no quiero que el plan gire en torno a sus llamadas.
<!-- /tier -->

## Cómo se evalúa el plan

**Restricciones obligatorias** (si se incumple alguna, el plan no cuenta):

- Ninguna furgoneta lleva más de {{van_capacity}} bandejas.
- Las furgonetas salen a las 05:00 o después y vuelven a las {{shift_end}} como muy tarde.
<!-- tier: hard -->
- V2 no sale antes de las 06:40.
<!-- /tier -->
- Cada cafetería abierta se atiende exactamente una vez; la {{closed_cafe}} no se atiende.
<!-- tier: medium hard -->
- Las cafeterías de marca asociada solo las atiende V4.
<!-- when: premium_first=true -->
- En cada ruta, las cafeterías premium van antes que las estándar.
<!-- /when -->
<!-- /tier -->

**Calidad**: el tiempo total que están fuera todas las furgonetas (de la salida a la vuelta), más {{late_cost}} veces cada minuto que una cafetería recibe el pedido después de su hora `entregar_antes`. Cuanto menor, mejor.
