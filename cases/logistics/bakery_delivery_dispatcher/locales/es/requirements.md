# Rutas de reparto matutino de la panadería

## Contexto

Mañana (lunes) por la mañana nuestra cocina central tiene que repartir el pan a todas nuestras cafeterías con nuestras cuatro furgonetas. ¿Puede planificar qué furgoneta va a cada sitio, para que las cafeterías reciban sus bandejas a tiempo y los conductores no estén fuera más de lo necesario? Le adjunto la lista de cafeterías y la de furgonetas.

## Entregable

Un archivo JSON, `routes.json`: `{"routes": [{"van": "V1", "depart": "05:40", "stops": ["C03", "C07", ...]}, ...]}`. Una entrada por furgoneta utilizada, con las paradas en orden de visita y los códigos exactamente como en los datos. `depart` es la hora de salida de la cocina; si se omite, se considera 05:00.

## Notas sobre los datos

- `x_km` / `y_km` son posiciones en kilómetros respecto a la cocina central, en (0, 0). La distancia por carretera es 1,3 veces la distancia en línea recta.
- La velocidad depende de la hora a la que empieza cada tramo: 30 km/h para tramos que empiezan antes de las 07:00 y 20 km/h para tramos que empiezan a las 07:00 o después (hora punta de la mañana).
- La descarga en cada cafetería dura 4 minutos más 0,2 minutos por bandeja.
- Una furgoneta que llega antes de la `apertura` espera a que abra la cafetería. `entregar_antes` es la hora de llegada más tardía que la cafetería acepta.
- Las furgonetas pueden salir desde las 05:00 y deben estar de vuelta en la cocina a las 09:30 (fin del turno de los conductores). Cada furgoneta lleva como máximo `max_bandejas` bandejas.
- La Cafetería Torre del Reloj (C11) está cerrada esta semana por reformas. No se le entrega.
- Las cafeterías con `marca_asociada = sí` venden productos refrigerados de nuestro socio. Solo la furgoneta refrigerada (V4) puede atenderlas.
- Cada cafetería recibe todas sus bandejas en una sola visita de una sola furgoneta.
- Nuestra costumbre: en cada ruta, las cafeterías premium se atienden antes que las estándar, para que las premium estén listas primero.

## Cómo se evalúa el plan

**Restricciones obligatorias** (si se incumple alguna, el plan no cuenta):

- Ninguna furgoneta lleva más de sus `max_bandejas`.
- Las furgonetas salen a las 05:00 o después y vuelven a las 09:30 como muy tarde.
- Cada cafetería abierta se atiende exactamente una vez; C11 no se atiende.
- Las cafeterías de marca asociada solo las atiende V4.
- En cada ruta, las cafeterías premium van antes que las estándar.

**Calidad**: el tiempo total que están fuera todas las furgonetas (de la salida a la vuelta), más tres veces cada minuto que una cafetería recibe el pedido después de su hora `entregar_antes`. Cuanto menor, mejor.
