# Rutas de reparto matutino de la panadería

## Contexto

Mañana (lunes) por la mañana nuestra cocina central tiene que repartir el pan a todas nuestras cafeterías con nuestras cuatro furgonetas. ¿Puede planificar qué furgoneta va a cada sitio, para que las cafeterías reciban sus bandejas a tiempo y los conductores no estén fuera más de lo necesario? Le adjunto la lista de cafeterías y la de furgonetas.

## Entregable

Un archivo JSON, `routes.json`: `{"routes": [{"van": "V1", "depart": "05:40", "stops": ["C03", "C07", ...]}, ...]}`. Una entrada por furgoneta utilizada, con las paradas en orden de visita y los códigos exactamente como en los datos. `depart` es la hora de salida de la cocina; si se omite, se considera 05:00.

## Notas sobre los datos

- `x_km` / `y_km` son posiciones en kilómetros respecto a la cocina central, en (0, 0). La distancia por carretera es 1,3 veces la distancia en línea recta.
- Velocidad: cuente con una media de 25 km/h durante toda la mañana. El lunes no hay colegio, así que esta semana no hay hora punta que tener en cuenta.
- La descarga en cada cafetería dura 4 minutos más 0,2 minutos por bandeja.
- Una furgoneta que llega antes de la `apertura` espera a que abra la cafetería. `entregar_antes` es la hora de llegada más tardía que la cafetería acepta.
- Una entrega tardía se acepta, pero nos cuesta: cada minuto que una cafetería recibe el pedido después de su `entregar_antes` nos cuesta lo mismo que 2 minutos de furgoneta (quejas y abonos a la cafetería).
- Las furgonetas pueden salir desde las 05:00 y deben estar de vuelta en la cocina a las 09:30 (fin del turno de los conductores).
- `max_bandejas` (120) es lo que caben en las estanterías de una furgoneta, pero esta semana repartimos en las cajas nuevas, más hondas, así que una furgoneta lleva como máximo 110 bandejas.
- La Cafetería Estación Norte (C03) está cerrada esta semana por reformas. No se le entrega.
- Cada cafetería recibe todas sus bandejas en una sola visita de una sola furgoneta.
- Las cafeterías con `marca_asociada = sí` venden productos refrigerados de nuestro socio. Solo la furgoneta refrigerada (V4) puede atenderlas.
- Esta semana dejamos de lado la costumbre de atender primero las cafeterías premium (sus encargados están de acuerdo en que llegar a tiempo importa más), así que en una ruta las cafeterías pueden ir en el orden que mejor convenga.
- El lunes las cuatro furgonetas están disponibles desde las 05:00 (la revisión de frenos de V2 es el martes).

## Cómo se evalúa el plan

**Restricciones obligatorias** (si se incumple alguna, el plan no cuenta):

- Ninguna furgoneta lleva más de 110 bandejas.
- Las furgonetas salen a las 05:00 o después y vuelven a las 09:30 como muy tarde.
- Cada cafetería abierta se atiende exactamente una vez; la Cafetería Estación Norte (C03) no se atiende.
- Las cafeterías de marca asociada solo las atiende V4.

**Calidad**: el tiempo total que están fuera todas las furgonetas (de la salida a la vuelta), más 2 veces cada minuto que una cafetería recibe el pedido después de su hora `entregar_antes`. Cuanto menor, mejor.
