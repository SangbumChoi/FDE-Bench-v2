# Revisión de `retail/grocery_demand_forecaster`

Hallazgos de la revisión del caso, cada uno con el veredicto del verificador y su estado tras este cambio. Las cifras de
calidad que siguen usan la nueva escala (línea base ingenua estacional 0, referencia 1), salvo las que se indican como
cocientes.

### F1 — Sin configuraciones: un único problema fijo en todas las dificultades (alta, en parte)

`case.yaml` no declara niveles, conjuntos de reglas ni `param_labels`; la única solución correcta es `gt/default`. Por
eso la columna de dificultad no dice nada de este caso, y nunca se pone a prueba "qué reglas se aplican esta vez".
DESIGN.md admite casos sin configuraciones (8 de los 13 casos construidos no las tienen), así que se trata de un hueco de
cobertura, no de un incumplimiento del contrato.

**Estado:** abierto — propuesta: convertirlo a 3×3 manteniendo los datos visibles idénticos byte a byte. easy = solo la
demanda base (los requisitos dicen que en esta ronda las promociones y el festivo del 11 de noviembre se gestionan en
otra parte); medium añade el plan de promociones, el festivo y el cambio de unidad de I07; hard añade lo que necesita una
nueva verdad puntuada (una revisión con fecha, un cierre, presión, un coste asimétrico en los perecederos). Los
parámetros de los conjuntos de reglas deberían ser valores que los datos no revelen: la fecha del festivo (miércoles 11 /
viernes 13 / lunes 9 de noviembre), el mínimo (6 en fruta y verdura + lácteos / 4 solo en lácteos / 8 solo en fruta y
verdura) y un cierre futuro (ninguno / S2 el 15 de noviembre / S5 el día festivo). No conviene usar como par de
conjuntos de reglas el WAPE medio por tienda frente al WAPE ponderado por volumen (el minimizador por celda es el mismo,
así que las referencias no se diferenciarían ni en un 1%), ni poner la censura informativa solo en hard (cambia el
historial visible).

### F2 — Poco margen de mejora sobre la referencia (alta, confirmado)

El WAPE de la referencia es 0.1470, el del oráculo (la media real del generador más el mínimo) 0.1381 y el de la línea
base 0.2790. En la nueva escala, el oráculo alcanza una calidad de 1.067 (1.118 / 1.167 / 1.072 con las semillas de
mundo 1–3), y solo con efectos de promoción y de festivo por categoría se llega a 1.039. La calidad ya no se recorta en
1.0, pero con el tope de 1.5 de la política incluso un modelo perfecto obtiene solo alrededor del 71% de la puntuación
de calidad, y la distancia entre un agente bueno y uno excelente es de unas pocas centésimas. La causa es un generador
multiplicativo limpio en el que dominan el ruido de Poisson y el ruido diario.

**Estado:** abierto — propuesta: añadir estructura aprendible que una heurística sencilla no capte (censura informativa,
caídas tras las promociones, canibalización dentro de la categoría, un cambio de nivel de una tienda a mitad del
historial, un artículo de rotación lenta con ventas intermitentes, un artículo nuevo con un análogo) y después reforzar
la referencia para que el oráculo quede alrededor de un 10% por encima de ella. Mientras tanto, fijar `quality_cap` en
`case.yaml` cerca de lo que alcanza un modelo fuerte pero alcanzable (en torno a 1.05 con esta semilla), para que la
puntuación completa no exija superar al oráculo. Añadir una comprobación que mantenga la calidad del oráculo dentro de
una banda en todas las semillas de mundo.

### F3 — El mínimo de exposición figuraba como 2 en `case.yaml` y como 6 en todo lo demás (alta, confirmado)

`case.yaml` describía `min_display_stock` como "never forecast below 2 units", mientras que `MIN_DISPLAY = 6.0` en
`case.py`, los requisitos de los cinco idiomas y la pregunta clave dicen 6. El clasificador de excepciones ve
el texto de `case.yaml` junto a los requisitos, de modo que al cliente se le mostraron ambas cifras justo en el momento
en que importa la regla flexibilizable, y la página explicativa imprimía las dos. Un mínimo de 2 no se aplicaría nunca
(referencia 0.13948 frente a 0.13947 sin mínimo). La comprobación de números del validador no lo detectó porque "2"
aparece en los requisitos como fecha ("Monday 2 November").

**Estado:** corregido en este cambio — la descripción de la regla dice ahora 6, en coherencia con `MIN_DISPLAY`, los
requisitos y la pregunta clave. No se usa un marcador `{{min_display}}`: el caso no tiene conjuntos de reglas con los que
rellenarlo.

### F4 — Flexibilizar el mínimo de exposición nunca compensa (media, confirmado)

El mínimo se aplica de hecho en 136 celdas de la referencia (albahaca I03 y queso curado I06, el 1.3% de la demanda del
periodo). Quitarlo da un WAPE de 0.1395 y una calidad de 1.057 (1.084–1.089 con las semillas 1–3). Con un peso de
calidad de 0.6 y un tope de 1.5, eso vale alrededor de 0.6 × 0.057 / 1.5 ≈ 0.023 de la puntuación compuesta, por debajo
de las dos penalizaciones por regla flexible (0.05 en startup, 0.10 en enterprise). El WAPE frente a la demanda real no
premia en nada la presencia en el lineal, así que "no flexibilizar nunca" es siempre la respuesta correcta.

**Estado:** abierto — propuesta: convertir la flexibilización en una disyuntiva real. O bien poner precio a la presencia
en el lineal en el objetivo (un coste por las previsiones de artículos básicos por debajo del mínimo en días de apertura
en que el artículo se vende, o puntuar cantidades de pedido que incluyan el mínimo), o bien hacer que el mínimo se
aplique en más artículos y calibrarlo para que flexibilizar gane más que la penalización de startup pero menos que la de
enterprise. Documentar en el README la respuesta esperada (flexibilizar o no) para cada política.

### F5 — Varias trampas de semántica de los datos apenas pesan (media, en parte)

Medido como un único cambio en la referencia: restar las devoluciones da una calidad de 1.001 (1,286 filas de
devolución, −2,104 unidades frente a 2,002,817 vendidas); ignorar el cambio de unidad de I07, 0.986; usar los días con
rotura de stock como normales, 0.960; pasar por alto el festivo, 0.927; ignorar el plan de promociones, 0.855. Las
roturas de stock dependen solo del artículo y de si está en promoción, no de la demanda del día, así que descartar los
días marcados no introduce sesgo. El verificador señala que el cambio de unidad sí pesa en los modelos de ventana larga
(una media por día de la semana de 52 semanas baja de un cociente de 0.945 a 0.476 sin corregirlo) y que el efecto de
las roturas de stock, aunque pequeño, equivale a la mitad del margen hasta el oráculo.

**Estado:** abierto — propuesta: hacer informativa la censura (limitar las ventas a un nivel de lineal o de inventario,
de modo que las roturas caigan en días de demanda alta, con lo que descartarlos sesga la previsión a la baja). Hacer que
las devoluciones importen (p. ej., devoluciones masivas ocasionales de un cliente de catering) o eliminar la pregunta
clave sobre devoluciones. Trasladar el cambio de I07 a la ventana reciente (p. ej., 2026-10-05) haría que pesara en
cualquier modelo; todos estos cambios modifican los datos visibles y las cifras de la referencia.

### F6 — Preguntas clave que los datos ya resuelven cuentan por completo en el Ask-F1 (media, en parte)

`s4_sunday_closed` (S4 no tiene filas en domingo) y `unit_change_i07` (el maestro de artículos dice "pack of 6" y el
historial cae a aproximadamente la sexta parte el 1 de junio de 2026) están etiquetadas como `missing`, y la exhaustividad
(recall) del Ask-F1 cuenta las nueve preguntas clave por igual, mientras que al agente se le indica que pregunte solo
por lo que los datos no resuelven. El verificador rechaza la cifra de 4/9 del revisor: la censura por roturas de stock y
las devoluciones son correctamente `ambiguous` (que las ventas están limitadas, y si excluir o restar, no se puede leer
en los datos), y `promo_plan` también abarca las fechas de fin incluidas y el efecto por categoría.

**Estado:** abierto — propuesta: reetiquetar `s4_sunday_closed` y `unit_change_i07` como un tipo de confirmación y
contarlas como cubiertas cuando NOTES.md recoja la inferencia correcta (o darles la mitad de peso). Reservar `missing`
para los hechos sin rastro en los datos (festivo, mínimo, métrica). Esto requiere una noción de tipo de pregunta clave en
el framework, en `clarify.py`.

### F7 — Sin eventos con fecha ni presión (media, confirmado)

Solo hay hechos ocultos: ni bandeja de entrada, ni aviso con fecha, ni ninguna parte interesada que empuje hacia una
previsión distorsionada. El caso no puede poner a prueba la replanificación ante un cambio con fecha ni la resistencia a
la presión; los eventos genéricos de la modalidad son la única dinámica.

**Estado:** abierto — propuesta: añadir un correo en la bandeja de entrada con fecha del 30 de octubre que revise el plan
de promociones (una promoción cancelada, otra ampliada hasta el 15 de noviembre, un descuento aumentado), o un cierre por
reforma de S3 el 13 y 14 de noviembre, ambos puntuados con la verdad del mundo. Añadir un mensaje de presión (un
encargado de tienda que pide inflar todas las previsiones un 15% "para no quedarnos nunca sin existencias"), que empeora
el WAPE y que el cliente confirma que no es política de la empresa. Añadir ambos como preguntas clave.

### F8 — El calendario es occidental y en parte español (media, en parte)

El "Festivo de primavera" cae en Viernes Santo (2025-04-18, 2026-04-03) y el de otoño el 12 de octubre; la Navidad
figura en las listas de festivos de zh y ja, faltan el Año Nuevo lunar y el Chuseok, y el 11 de noviembre (el Día del
Soltero en China, el Día del Pepero en Corea) se llama aniversario de la ciudad en zh y ko. El aumento por festivo cae
en el propio día (S1 I07: 207 el 24 de diciembre frente a 359 el 25 de diciembre). Las frutas y verduras por kg se
registran como enteros y los plátanos se devuelven por kg. Ningún documento afirma que el mundo sea neutral respecto al
país, y el día de Navidad no es el día de más ventas (lo es el 15 de agosto de 2026).

**Estado:** abierto — propuesta: usar un calendario ficticio con fechas fijas neutras, poner efectos de víspera cuando un
festivo cierre las tiendas y sacar el festivo único del 11/11 (p. ej., al jueves 12 de noviembre, que además sirve como
parámetro de conjunto de reglas). Registrar los artículos por kg con precisión de 0.1 kg y anotar devoluciones solo de
artículos envasados. Todo esto cambia los datos visibles.

### F9 — Redacción coreana (baja, en parte)

Las cifras y los parámetros coinciden en los cinco idiomas. Algunas expresiones coreanas eran calcos o
sonaban forzadas: "6개 미만" usa el clasificador de piezas para artículos que se venden por kg, "CSV 파일 하나,
`forecast.csv`이며" sigue el orden de palabras del inglés, "빼 주세요 … 차감하지도 않습니다" mezcla una petición y una
afirmación, y los nombres de tienda 북역점 / 호숫가점 son literales. El verificador señala que 개 es el clasificador
genérico y que 개청 기념일 está documentado, así que se trata de pulido.

**Estado:** corregido en este cambio — requisitos y pregunta clave en ko: "6(판매단위 기준) 미만", "산출물은 CSV 파일
`forecast.csv` 하나이며, 헤더는 …", "차감하지도 마세요", "일회성 지역 공휴일인 시민의 날(시 승격 기념일)"; nombres de
tienda en ko: 북부역점 (S3) y 호수공원점 (S5). La misma mezcla de petición y afirmación en ja ("相殺もしません") dice
ahora "相殺もしないでください". Aun así, debería darle el visto bueno un revisor nativo.

### F10 — Detalles de la documentación que confunden a los revisores (baja, confirmado)

Los requisitos decían "one row per store, item and trading day", pero luego describen filas de devolución negativas
aparte con la misma clave (1,286 filas de ese tipo). La página explicativa etiquetaba la especificación del entregable como
"agent-visible", aunque solo la ve el extractor, y el caso no tenía un README con sus cifras de referencia y de línea
base.

**Estado:** corregido en este cambio — la nota sobre los datos dice ahora "one sales row per store, item and trading
day, plus separate return rows" en los cinco idiomas, y README.md da las cifras de la referencia, la línea
base, el oráculo y la ablación. La etiqueta de la página explicativa la genera el framework y en este commit ya dice "shown to the
extractor … not to the agent".

**Línea base:** ingenua estacional (el mismo día de la semana de la última semana del historial, domingos de S4 a 0,
mínimo de 6 en los artículos básicos): WAPE medio de 0.2790 frente a 0.1470 de la referencia con la semilla del caso
(cociente 1.90); 0.2534 / 0.2521 / 0.2533 frente a 0.1474 / 0.1592 / 0.1417 con las semillas de mundo 1–3 (cocientes
1.58–1.79).
