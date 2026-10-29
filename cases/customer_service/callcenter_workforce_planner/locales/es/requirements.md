# Cuadrante semanal del centro de soporte multilingüe

## Contexto

¿Podría preparar el cuadrante de la próxima semana (del lunes 9 al domingo 15 de noviembre) para nuestro equipo de soporte? Necesitamos suficiente gente al teléfono para que los clientes no esperen, en todos los idiomas que atendemos. Le adjunto la lista de personal y el volumen de llamadas previsto.

## Entregable

Un archivo JSON, `roster.json`: `{"assignments": [{"agent": "A01", "day": "2026-11-09", "shift": "S0800", "language": "ko"}, ...]}`. Una entrada por agente y por turno trabajado. `agent` y `shift` exactamente como en los datos, `day` en formato YYYY-MM-DD y `language` con el código `ko` (coreano), `ja` (japonés), `en` (inglés), `zh` (chino) o `es` (español).

## Notas sobre los datos

- `agentes.xlsx`, hoja `personal`: cada agente con su `contrato` (jornada completa / media jornada) y `nuevo_ingreso`. La hoja `idiomas` tiene una fila por agente y por idioma en el que puede atender llamadas. Solo contamos con estos 30 agentes.
- `prevision_llamadas.csv` ya da personas, no llamadas: `agentes_necesarios` es el número de agentes que hace falta en cada idioma durante la franja de media hora que empieza en `inicio_franja` (de 08:00 a 21:30; el servicio está abierto de 08:00 a 22:00). La cobertura se comprueba por franja de media hora: un agente cuenta en todas las franjas que caen dentro de su turno (S0800 cubre las franjas de 08:00 a 15:30).
- Durante todo el turno un agente atiende en un solo idioma, el que se indica en `language`, y debe ser uno de sus idiomas. Un agente bilingüe cuenta para un solo idioma, nunca para dos a la vez.
- El miércoles 11 de noviembre es festivo regional en nuestro mercado principal. Abrimos igual, pero esperamos menos llamadas: para ese día use el 60 % de la previsión, redondeado hacia arriba a agentes enteros. El archivo de previsión no se actualizó.
- Según `turnos.csv`, el personal de jornada completa solo hace los turnos de 8 horas (S...) y el de media jornada solo los de 4 horas (P...).
- Una persona de jornada completa trabaja como máximo 5 turnos a la semana; una de media jornada, como máximo 3.
- Entre el final de un turno y el inicio del siguiente turno del mismo agente debe haber al menos 11 horas de descanso (por tanto, como mucho un turno al día; por ejemplo, el S1400 termina a las 22:00 y no puede ir seguido de un turno de las 08:00 a la mañana siguiente).
- `ausencias.csv` escribe las fechas como día/mes/año (10/11/2026 es el 10 de noviembre); `desde` y `hasta` están incluidos. Solo cuenta como ausencia lo que tiene `estado = aprobada`; una solicitud `rechazada` significa que el agente trabaja con normalidad.
- `costes.csv` da la tarifa por hora de cada tipo de contrato. La semana normal de jornada completa es de 4 turnos: el 5.º turno de la semana es hora extra y se paga a 1,5 veces.
- Nuestra costumbre: una persona de nuevo ingreso nunca está sola en un idioma. En cada franja de media hora en la que está al teléfono, debe haber al menos un agente que no sea de nuevo ingreso asignado al mismo idioma.

## Cómo se evalúa el cuadrante

**Restricciones obligatorias** (si se incumple alguna, el cuadrante no cuenta):

- Cada agente solo atiende en uno de sus idiomas.
- Jornada completa solo en turnos de 8 horas; media jornada solo en turnos de 4 horas.
- Como máximo 5 turnos a la semana para jornada completa y 3 para media jornada.
- Al menos 11 horas de descanso entre dos turnos del mismo agente.
- Nadie está programado durante una ausencia aprobada.
- Las personas de nuevo ingreso siempre tienen a un compañero que no es nuevo en el mismo idioma y a la misma hora.

**Calidad**: 40 por cada agente que falte en cada franja de media hora y en cada idioma (`agentes_necesarios`, con el ajuste del festivo del miércoles, menos los agentes asignados a ese idioma en esa franja, cuando es positivo), más el coste de personal de todos los turnos (horas por tarifa por hora, el 5.º turno de jornada completa a 1,5 veces). El 40 está en las mismas unidades que las tarifas por hora: es nuestra estimación de lo que nos cuesta que falte un agente durante media hora en llamadas abandonadas, rellamadas y niveles de servicio incumplidos. Los agentes que sobran por encima de la necesidad no se penalizan salvo por su coste. Cuanto menor, mejor.
