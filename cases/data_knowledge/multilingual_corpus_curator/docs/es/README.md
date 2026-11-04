# Curador de corpus multilingüe — `data_knowledge/multilingual_corpus_curator`

Una pequeña editorial guarda el material de unos cien libros (en chino, inglés, coreano, japonés y español) en una unidad compartida desordenada: el título, los autores, los años de publicación y la sinopsis de cada libro están repartidos en uno a tres archivos de formatos distintos, junto a escaneos, archivos comprimidos, exportaciones de catálogo y archivos basura. El agente entrega un **programa**, `program/organize.py` con `organize(task)`, `task = {"corpus_dir": "$INPUT_DIR", "out_dir": "$OUTPUT_DIR"}`, que construye una biblioteca normalizada:

```
out_dir/library/<estructura sorteada>.txt   un archivo UTF-8 por libro: solo su sinopsis
out_dir/_review/...                         archivos de origen de los libros que no se pueden colocar
out_dir/manifest.csv                        source,status,path,reason (placed | review | skipped)
```

El agente ve una muestra visible (`data/corpus/`, 100 libros, ~120 archivos) y el programa se puntúa sobre un **corpus de evaluación** (la IA nunca lo recibe) construido con la misma receta y otra semilla (mismo tamaño y misma mezcla de tipos, otros libros y otros nombres de archivos comprimidos, de catálogos y de archivos numerados), idéntico en todas las configuraciones. Todo es sintético: los títulos, los nombres y las sinopsis se generan a partir de vocabularios inventados, escritos de forma nativa en cada idioma. Para leer todos los formatos basta con la biblioteca estándar.

El caso está **auditado** (`audited: true`): `dataset/audit.json` contiene su auditoría de la respuesta correcta; `GT.md`, la respuesta correcta en cinco partes generadas a partir de ella (hechos del cliente, comprobaciones de validez, objetivo, referencia y cotas, casos de la comprobación directa), y `CLIENT_REVIEW.md`, los pasajes a partir de los cuales el cliente simulado responde a cada hecho, en los cinco idiomas, para un revisor humano. Ambos los escribe `gt_report.py`.

## Configuraciones: un corpus, niveles × semillas de reglas

Una configuración es un nivel y una semilla de reglas. El mundo, el corpus visible, el corpus de evaluación y la solicitud son los mismos en todas las configuraciones (el validador comprueba que lo que ve el agente es idéntico byte a byte). El nivel decide qué libros puntúan, qué reglas se aplican y entre qué candidatos sortea la semilla de reglas; la semilla de reglas sortea las reglas de biblioteca del cliente, cada parámetro por separado, de modo que la biblioteca correcta cambia de una semilla a otra. Las semillas de reglas públicas son la **11, la 18 y la 21** (nueve configuraciones, guardadas en `dataset/answer/` y comprobadas por el validador); cualquier otra semilla es un sorteo privado cuyas respuestas no se publican en ningún sitio.

### Niveles (mismo corpus; cambian el alcance, la exigencia y los candidatos)

| | easy | medium | hard |
|---|---|---|---|
| **Libros que puntúan** (corpus de evaluación) | 30 libros bien formados: un archivo, UTF-8, metadatos completos, años normales de cuatro cifras | 66: + todos los libros legibles | 100: + las excepciones |
| **Qué se añade** | Formatos, la estructura de rutas, las reglas de nombre, la extracción de la sinopsis, la base del año, las parejas romanizadas | Codificaciones antiguas (GB18030, CP949, Shift_JIS, CP1252); `令和元年`, `昭和50年`, `民國98年`, `단기 4342년`, `二〇〇九年`, `MMIX`; títulos en ancho completo y con acentos descompuestos; caracteres prohibidos en las rutas; un autor con varias romanizaciones (la pareja oficial solo aparece en los demás libros del autor); copias en varios formatos y carpetas que hay que fundir; precedencia de las fuentes (metadatos incrustados > portadilla > nombre de archivo) | Autor/título/sinopsis que faltan y se recuperan de otro archivo; título a partir de un nombre de archivo con sentido; año a partir de una línea `©`; revisión con código de motivo: `NO_TITLE` / `NO_YEAR` / `NO_DESCRIPTION` / `CONFLICT` (desacuerdo de año entre fuentes del mismo rango) / `UNREADABLE` (escaneo de solo imagen); la política del cliente para los libros sin autor (revisión `NO_AUTHOR`, o colocarlos con un nombre de autor de reserva); escaneos que duplican un archivo legible; basura (`.DS_Store`, `Thumbs.db`, `desktop.ini`, archivos de bloqueo `~$`, `__MACOSX/._*`, archivos vacíos); libros dentro de archivos zip; CSV de catálogo con varios libros (cabeceras en inglés y en japonés) |
| **Candidatos de longitud de nombre** (`max_len`) | 60, 48, 40: cada uno corta los títulos con subtítulo en un punto distinto | 50, 40, 32: + listas de coautores y títulos largos con nombres de lugar, con 32 | 40, 32, 24: + títulos de longitud media y listas de coautores |
| **Política para libros sin autor** (`no_author`) | no se sortea (esos libros quedan fuera del alcance) | no se sortea | revisión, o colocarlos con el nombre de autor "Unknown" o "Anonymous" |
| **Reglas** | `utf8_output`, `safe_names` (física); `one_file_per_book`, `review_reason`, `manifest_rows`, `review_copies` (contractual) | igual | + `no_fabrication`, `no_guessing` (contractual); con la política de revisión, `missing_author_review`, y con una política de colocación, `missing_author_shelved` (costumbre del negocio) |
| **Extras de puntuación** | los libros fuera del alcance se ignoran | −0.5 por cada archivo de la biblioteca que no es un libro | política de revisión: un libro sin autor que espera en revisión suma 0.7 (colocarlo con "Unknown" suma 1, pero exige una excepción aprobada); política de colocación: ese libro se puntúa como cualquier otro libro colocado; un archivo de la biblioteca cuyo texto no está en ninguna fuente incumple `no_fabrication` |
| **Lo que los requisitos dejan fuera del alcance** | "Los demás archivos de la unidad (codificaciones antiguas, copias en varios formatos, material dañado o incompleto, archivos comprimidos, catálogos, escaneos) todavía no se revisan, pero el programa no debe detenerse por ellos" | "Las excepciones (datos que faltan, escaneos, archivos comprimidos, catálogos, archivos basura) todavía no puntúan, pero nada que no sea un libro debe acabar en la biblioteca" | nada |

Una semilla de reglas sortea la misma posición de la lista de candidatos en todos los niveles (el sorteo no depende del nivel), pero `max_len` tiene candidatos distintos en cada nivel y `no_author` solo tiene candidatos en hard. Así, la misma semilla da un límite de nombre más estricto en cada nivel más difícil y, en hard, puede cambiar la política para libros sin autor: las referencias de los tres niveles difieren en todas las semillas públicas, y cada una, puntuada bajo otro nivel, queda por debajo de la referencia propia de ese nivel (tabla de abajo).

### Parámetros

Una semilla de reglas s sortea la posición `Random("data_knowledge/multilingual_corpus_curator|<name>|s").randrange(n)` de cada lista de n candidatos, de forma independiente de los demás parámetros. Las cinco primeras listas son iguales en todos los niveles. Cada parámetro es el dato de un hecho que la IA debe preguntar (`param:` en `locales/en/targets.yaml`).

| Parámetro | Candidatos | Qué cambia (corpus de evaluación, mundo público, libros colocados dentro del alcance easy / medium / hard) | Hecho |
|---|---|---|---|
| `layout` | `library/<año>/<título>/<autor>.txt`, `library/<año>/<autor>/<título>.txt`, `library/<autor>/<año>_<título>.txt` | la ruta de cada libro colocado (30 / 66 / 88–90) | `layout` |
| `year_basis` | primera publicación, esta edición (un libro con un solo año lo usa para ambas) | libros cuyos dos años difieren (15 / 37 / 44) | `year_basis` |
| `script` | original, latina (la romanización emparejada en los metadatos) | libros en chino, coreano y japonés (18 / 40 / 58) | `script` |
| `multi_author` | solo el primer autor, todos unidos con `" & "` | libros con dos autores (10 / 23 / 30) | `co_authors` |
| `sep` | `_`, `-`, un espacio normal | nombres con espacios (18 / 40 / 53 en la escritura original, todos los libros en la latina) | `separator` |
| `max_len` | easy 60, 48, 40; medium 50, 40, 32; hard 40, 32, 24 | nombres más largos que el límite: easy 5–6; medium 13, 13, 15–17; hard 15, 17–19, 21–38 (rangos según la escritura y la regla de coautores) | `max_len` |
| `no_author` | easy y medium `review`; hard `review`, `Unknown`, `Anonymous` | los 2 libros sin autor (hard): `review` los envía a revisión como `NO_AUTHOR` (0.7 cada uno) según la regla flexibilizable `missing_author_review`; un nombre los coloca con ese nombre de autor como cualquier otro libro (1 cada uno), y `missing_author_shelved` invalida enviarlos a revisión o usar otro nombre | `missing_author` |

`derive_params` añade `fallback_author`, el nombre que citan los textos: el nombre sorteado con una política de colocación, y "Unknown" (el nombre que usaría una excepción aprobada) con la política de revisión. Ninguna combinación es inviable: el generador mantiene todos los títulos distintos en sus primeros 24 caracteres (el límite más estricto) en las dos escrituras, así que ningún par de libros colocados comparte ruta con ninguna combinación, y el caso no define `admissible`.

Reglas de nombre en todas las configuraciones: NFKC; cada `\ / : * ? " < > |` o carácter de control pasa a ser un espacio; cada tramo de espacios en blanco pasa a ser el separador; se corta a `max_len` caracteres; se quitan espacios, puntos y separadores en ambos extremos. Un límite más estricto alcanza más nombres, así que equivocarse en el orden de estos pasos cuesta más a menudo: cortar un título español con acentos descompuestos antes de NFKC conserva menos letras, y un corte que cae en un separador deja uno por quitar.

### Semillas de reglas públicas

Estas semillas muestran todos los candidatos de todos los parámetros: entre las semillas 11, 18 y 21, cada lista de tres candidatos da sus tres valores (en todos los niveles) y cada lista de dos, sus dos valores. La semilla 11 va primero porque validate-case comprueba a partir de ella que los parámetros aprietan, y su sorteo de hard coloca los libros sin autor, así que la comprobación de la política compara una referencia válida con política de colocación con las políticas que esa referencia incumple.

| Configuración | `layout` | `year_basis` | `script` | `multi_author` | `sep` | `max_len` | `no_author` (→ `fallback_author`) | Solución de referencia | Forma de trabajar del cliente | Cota |
|---|---|---|---|---|---|---|---|---|---|---|
| easy/s11 | author/year_title | first | latin | all | `" "` | 40 | review (Unknown) | 100.00 | 16.67 | 100.00 |
| easy/s18 | year/title/author | first | latin | first | `-` | 48 | review (Unknown) | 100.00 | 16.67 | 100.00 |
| easy/s21 | year/author/title | edition | original | first | `_` | 60 | review (Unknown) | 100.00 | 16.67 | 100.00 |
| medium/s11 | author/year_title | first | latin | all | `" "` | 32 | review (Unknown) | 100.00 | 13.03 | 100.00 |
| medium/s18 | year/title/author | first | latin | first | `-` | 40 | review (Unknown) | 100.00 | 13.03 | 100.00 |
| medium/s21 | year/author/title | edition | original | first | `_` | 50 | review (Unknown) | 100.00 | 13.03 | 100.00 |
| hard/s11 | author/year_title | first | latin | all | `" "` | 24 | Unknown | 100.00 | 8.60 | 100.00 |
| hard/s18 | year/title/author | first | latin | first | `-` | 32 | review (Unknown) | 99.40 | 8.60 | 99.40 (100 con la excepción) |
| hard/s21 | year/author/title | edition | original | first | `_` | 40 | Anonymous | 100.00 | 8.60 | 100.00 |

Objetivos sobre el corpus de evaluación con la semilla de mundo pública (20261027); la "cota" es `objective_bound`, lo máximo que puede obtener un programa válido (`expected_output` la alcanza). Las semillas privadas sortean cualquier otra combinación; p. ej., la semilla 101: `author/year_title`, first, original, first, `-`, 60 / 50 / 40, review en todos los niveles; la semilla 102: `year/author/title`, first, original, first, `_`, 40 / 32 / 24, `Unknown` en hard.

**Parámetros que aprietan** (validate-case, desde la configuración s11 de cada nivel): cada parámetro cambia la puntuación de la referencia con cualquier otro valor. En el mundo público, la referencia de hard/s11 obtiene 100.00, y con un solo parámetro cambiado: `layout` 46.00 (un libro mal archivado suma 0.4; los 10 libros de revisión conservan su crédito), `year_basis` → edition 73.60, `script` → original 65.20, `multi_author` → first 82.00, `sep` → `_` o `-` 46.00, `max_len` → 40 o 32 77.20, `no_author` → review inválida (`missing_author_review`), → Anonymous inválida (`missing_author_shelved`). En easy (desde 100.00): `layout` 40.00, `year_basis` 70.00, `script` 64.00, `multi_author` 80.00, `sep` 40.00, `max_len` 88.00; en medium: 40.00, 66.36, 63.64, 79.09, 40.00, 84.55. Las mismas comprobaciones se superan con las semillas de mundo 1, 2 y 3.

**Referencias entre configuraciones** (mundo público; cada fila es una configuración y cada celda, la referencia de otra configuración puntuada bajo ella; `*` = inválida):

| Puntuada bajo | easy s11 / s18 / s21 | medium s11 / s18 / s21 | hard s11 / s18 / s21 |
|---|---|---|---|
| easy/s11 | **100.00** / 40.00 / 40.00 | 88.00 / 40.00 / 40.00 | 76.00 / 40.00 / 40.00 |
| easy/s18 | 40.00 / **100.00** / 40.00 | 40.00 / 88.00 / 40.00 | 40.00 / 88.00 / 40.00 |
| easy/s21 | 40.00 / 40.00 / **100.00** | 40.00 / 40.00 / 88.00 | 40.00 / 40.00 / 88.00 |
| medium/s11 | 84.55 / 40.00 / 40.00 | **100.00** / 40.00 / 40.00 | 70.91 / 40.00 / 40.00 |
| medium/s18 | 40.00 / 88.18 / 40.00 | 40.00 / **100.00** / 40.00 | 40.00 / 86.36 / 40.00 |
| medium/s21 | 40.00 / 40.00 / 88.18 | 40.00 / 40.00 / **100.00** | 40.00 / 40.00 / 88.18 |
| hard/s11 | 75.20* / 45.20* / 45.20* | 75.20* / 45.20* / 45.20* | **100.00** / 45.20* / 46.00* |
| hard/s18 | 46.60 / 89.20 / 46.60 | 46.60 / 89.20 / 46.60 | 46.00* / **99.40** / 46.00* |
| hard/s21 | 45.20* / 45.20* / 89.00* | 45.20* / 45.20* / 89.00* | 46.00* / 45.20* / **100.00** |

La referencia de otra semilla conserva su estructura de rutas, así que todos los libros que coloca quedan mal archivados (0.4). La referencia de la misma semilla en otro nivel difiere en el límite de longitud y, en hard, en la política para libros sin autor: pierde 10–29 puntos, y con cada política de hard las referencias escritas para otra política son inválidas (`missing_author_review` o `missing_author_shelved`).

### Lo que el agente debe preguntar

Doce hechos que la IA debe preguntar, cada uno un solo dato (la parte 1 de GT.md muestra que malinterpretar uno solo de ellos pierde al menos una décima parte del crédito en todas las configuraciones medidas en las que se aplica):

- sorteados por la semilla de reglas (`param:`): `layout`, `year_basis`, `script`, `co_authors`, `separator`, `max_len` y, en hard, `missing_author` (la política para libros sin autor y su nombre de reserva);
- iguales con cualquier sorteo: `content` (el archivo contiene solo la sinopsis), `review_codes` (los seis códigos) y, en hard, `no_description` (sin sinopsis: `NO_DESCRIPTION`, nunca un texto de relleno), `conflict` (años del mismo rango que no coinciden: `CONFLICT`) y `generic_titles` (un nombre de archivo genérico no es un título: `NO_TITLE`).

Los antiguos hechos `precedence`, `encodings`, `year_notations`, `author_variants`, `duplicates`, `containers`, `scoring` y las partes de `exceptions` que no figuran arriba ya no son hechos que preguntar: son datos que se ven en la muestra o afectan a demasiado pocos libros para importar (GT.md da la cota de cada uno; REVIEW.md, "Auditoría de la respuesta correcta"). Siguen en requirements.md, y el cliente los responde si se le pregunta.

**Valor de preguntar** (auditoría, mundo público): un programa que nunca pregunta (`robust_solution`: la lectura de la referencia de cada hecho fijo, el primer candidato de cada regla sorteada, el límite de nombre más largo y ninguna fila de revisión, ya que no puede conocer los códigos) obtiene un crédito medio de 0.31 / 0.34 / 0.36 en easy / medium / hard, así que preguntar vale 0.69 / 0.66 / 0.64 del crédito.

## Formatos de archivo y catálogo de excepciones

| Tipo | Dónde están los datos |
|---|---|
| JSON | `title`, `title_latin`, `authors[{name, name_latin}]`, `first_published`, `edition_year`, `description` (en medium los años pueden ser cadenas con eras) |
| XML de tipo ONIX (espacio de nombres `ns.editeur.org/onix/3.0`) | `TitleText` (+ `textscript="Latn"`), `Contributor/PersonName` + `AlternativeName` o `PersonNameInverted`, `PublishingDateRole` 01 = esta edición, 11 = primera publicación, `TextContent/Text` |
| EPUB (zip + OPF) | `dc:title`, `dc:creator` con refinamientos `alternate-script` / `file-as`, `dc:date` (esta edición), meta `first-published`, `dc:description`; `dcterms:modified` es una trampa |
| DOCX (zip + XML) | title y creator de `docProps/core.xml` (`dcterms:created` es una trampa); párrafos del cuerpo partidos en varios runs = portadilla + sinopsis |
| PDF (flujos de texto sin comprimir) | `/Title` y `/Author` de Info (cadenas hexadecimales UTF-16; `/CreationDate` es una trampa); texto de página como cadenas `Tj` en UTF-16, con las líneas de la portadilla enteras y las de la sinopsis cortadas |
| PDF escaneado | página de solo imagen, sin texto ni título: ilegible |
| HTML | `<title>`, `<meta name="author">`; en el cuerpo, `h1`, `p.latin`, `p.byline`, `p.edition`, `h2` y párrafos de sinopsis; `<meta charset>` (Shift_JIS / CP949 en medium) |
| Markdown | bloque inicial (`title`, `title_latin`, `author`, `author_latin`, `first_published`, `edition`) + portadilla en el cuerpo |
| Texto plano | portadilla (título, `(título romanizado)`, `Nombre（Romanizado） 著` / `지음` / `by` / `por`, línea de edición, línea `©` opcional), encabezado (`内容简介`, `内容紹介`, `책 소개`, `About this book`, `Sinopsis`), sinopsis (a veces con cortes de línea fijos, CRLF o en una codificación antigua) |
| CSV de catálogo | un libro por fila; cabeceras en inglés o en japonés; `source` = `file.csv#row` |
| Archivo zip | 2 libros cada uno más una entrada AppleDouble `__MACOSX/._*`; `source` = `archive.zip!inner/path` (una carpeta más abajo en el corpus de evaluación) |

Composición de cada corpus (cantidades fijas, idiomas en parte aleatorios): 30 easy; medium: 7 codificaciones, 6 notaciones de año, 4 títulos en ancho completo o descompuestos, 5 caracteres prohibidos, 5 variantes de romanización, 6 copias en varios archivos, 3 conflictos de precedencia; hard: 3 autores recuperados, 2 sin autor, 2 títulos a partir del nombre de archivo, 2 sin título, 2 sinopsis recuperadas, 2 sin sinopsis, 3 años de línea de copyright, 2 sin año, 2 conflictos del mismo rango, 2 solo con escaneo, 2 escaneos con copia legible, 4 libros en zips, 6 filas de catálogo; más 8 archivos basura. Uno de cada dos libros easy en inglés y en español, y el 60 % de los demás, llevan un subtítulo largo (`The Silent Lighthouse — Stories from the Northern Coast and the Keepers Who Stayed Behind`); el 30 % de los libros tienen dos autores. Los nombres de los archivos comprimidos y de los catálogos salen de listas pequeñas, y los nombres de archivo numerados (`doc_0391`, `scan_0414`) empiezan en un desplazamiento aleatorio por corpus: en el mundo público, la unidad de evaluación solo comparte con la muestra 4 rutas de archivos basura (antes, 12), y con las semillas de mundo 1-3, como mucho un nombre de archivo comprimido además de esas (con otro contenido). La unidad de evaluación siempre contiene además un año de la era Shōwa (el libro con era japonesa) y entradas de zip una carpeta más abajo.

## Puntuación

Por libro puntuado: **1** por la ruta exacta en la biblioteca con la sinopsis correcta; **0.4** por la sinopsis correcta en cualquier otra ruta (mal archivado: el equipo tiene que encontrarlo y moverlo); **0.2** por la ruta correcta con cualquier otro texto. Un libro que debe ir a revisión suma 1 cuando todas las filas del manifiesto que nombran alguno de sus archivos dicen `review` con el código de motivo correcto (0.4 si coinciden en otro código; con la política de revisión, un libro `NO_AUTHOR` suma 0.7 en revisión); si las filas se contradicen, o si el libro tiene además un archivo en la biblioteca, no suma nada. Un libro que debe ir a la biblioteca no suma nada en revisión; con una política de colocación eso incluye los libros sin autor, cuyo autor esperado es el nombre de reserva sorteado. También se revisa la fila de cada libro en el manifiesto (la única fila que nombra los archivos del libro, todos ellos y nada más; `placed` con la ruta del libro en la biblioteca, o `review` con sus archivos copiados byte a byte bajo `_review/`; un escaneo que copia un archivo legible puede ir en la fila, figurar como skipped u omitirse): una fila que falta o está mal cuesta una quinta parte del crédito del libro. Medium y hard restan 0.5 por cada archivo de la biblioteca que no es un libro. Objetivo = 100 × crédito / libros puntuados (maximizar); la calidad se normaliza entre la forma de trabajar del cliente (0) y la referencia (1), y `quality_cap` es 1.0 (la referencia es lo mejor posible). Las sinopsis se comparan tras NFKC y sin espacios en blanco, así que los cortes de línea no importan. En hard, `no_fabrication` también salta con un archivo no vacío de la biblioteca que no contiene ningún párrafo completo de sinopsis de ningún libro ni es un fragmento (20+ caracteres) de uno: textos de relleno y sinopsis inventadas; un encabezado suelto o un párrafo omitido solo cuestan crédito.

Las reglas que hacen obligatorias las salidas: `manifest_rows` (cada archivo de la biblioteca es la ruta de exactamente una fila placed, la ruta de cada fila placed es un archivo de la biblioteca y su fuente nombra al menos un archivo de la unidad, una entrada de un archivo comprimido o una fila de catálogo, escritas con `!`, `/`, `:`, `#` o `|` tras la ruta del archivo comprimido o del catálogo; ninguna fuente aparece en dos filas) y `review_copies` (cada archivo de la unidad nombrado en una fila de revisión se copia bajo `_review/`). `no_guessing` (hard) convierte el "sin inventar nada" de la solicitud en una condición obligatoria: un libro cuyo título o año no dejan claro las fuentes (`NO_TITLE`, `NO_YEAR`, `CONFLICT`) no se coloca.

`score()` también da `enforced` y `evidence` por cada hecho que se aplica: la comprobación directa, calculada a partir de la misma ejecución del programa sobre la unidad de evaluación (parte 5 de GT.md). Los programas degenerados (los atajos de `shortcuts()` en case.py, parte 2 de GT.md) son inválidos o puntúan como mucho 0.42: mandar todo a revisión, inundar el manifiesto de filas de revisión, textos de relleno o archivos enteros en las rutas correctas, un manifiesto con solo la cabecera, un manifiesto cuyas filas placed tienen la fuente vacía o su propia ruta de biblioteca como fuente, revisión sin copias, cada libro en las tres estructuras, copiar la unidad tal cual y un `library/<title>.txt` plano. La comprobación directa también los distingue de un programa correcto: una ruta plana cuenta en contra de `layout`, un texto de relleno en la ruta correcta, en contra de `content`, y un libro sin autor que ni se coloca ni va a revisión, en contra de `missing_author`; en hard, un programa que no escribe ninguna fila de revisión sale como no aplicado en `review_codes` (en easy y medium ningún libro puntuado debe ir a revisión, y se queda en None). Un archivo suelto de la biblioteca que contiene la sinopsis completa de un libro con más texto alrededor (una ficha en una ruta que no da ninguna regla) sigue sin ser el archivo de ningún libro para la puntuación, pero la comprobación directa lo lee como el de ese libro, así que un programa que malinterpreta dos hechos queda marcado en los dos. La auditoría prueba además la comprobación directa en entregables que no son ni la referencia ni una respuesta que malinterpreta un solo hecho (la clave de respuestas, la forma de trabajar del cliente, `robust_solution`; parte 5 de GT.md; REVIEW.md, "Comprobaciones directas en otros entregables"). El caso no tiene una función `diagnose()` aparte, calculada bajo demanda: la comprobación directa es barata y se calcula en `score()`.

La salida del programa sobre el corpus de evaluación se guarda en caché según el resumen (digest) del programa, de modo que las configuraciones, los ejemplos de incumplimiento y las comprobaciones de que los parámetros aprietan y entre niveles ejecutan cada programa distinto una sola vez (`validate-case` tarda unos tres minutos con las semillas de mundo por defecto 1–3; `audit-case`, unos 8 a 10 minutos).

## Solución de referencia y cifras verificadas (semilla 20261027, corpus de evaluación)

La forma de trabajar del cliente (`reference/baseline.py` + el mismo `config.json`) es lo que el cliente podría programar sin un ingeniero: coloca solo los libros que tienen una exportación JSON completa en UTF-8 (título, autor, un año normal de cuatro cifras y una sinopsis) según las reglas del catálogo, deja para el equipo un registro JSON cuyo ISBN también tiene una exportación ONIX (no puede saber cuál de las dos es la correcta) y deja todos los demás archivos para el equipo (ningún otro formato, ni codificaciones antiguas ni años de era, sin fundir copias, sin zona de revisión). Es válida en todas las configuraciones.

La solución de referencia (`reference/organize.py` + `config.json` de la configuración) es el organizador completo: todos los formatos y las entradas de zip, codificaciones antiguas detectadas mediante las estadísticas de caracteres UTF-8 del propio corpus, todas las notaciones de año (eras, Minguo, Dangi, numerales chinos, números romanos, líneas `©`), nombres de ruta normalizados con NFKC, agrupación por título normalizado, precedencia por campo sobre todos los archivos de un libro, la pareja oficial de nombres de cada autor tomada de cualquier lugar de la unidad, conflictos de año del mismo rango, escaneos, basura y catálogos, y la política para libros sin autor sorteada. Archiva cada libro del corpus de evaluación exactamente como `expected_output`: alcanza `objective_bound` en todas las configuraciones, y `quality_cap` es 1.0. La mejor solución conocida (`best_known_solution`, para la auditoría) es la propia clave de respuestas escrita por un programa, un oráculo que también alcanza la cota: un segundo entregable que lo sabe todo, además de la referencia, que la comprobación directa nunca debe marcar como no aplicado.

| Nivel | Libros puntuados | Objetivo de la forma de trabajar del cliente | Objetivo de la solución de referencia = cota |
|---|---|---|---|
| easy (s11, s18, s21) | 30 | 16.67 | 100.00 |
| medium (s11, s18, s21) | 66 | 13.03 | 100.00 |
| hard, política de revisión (s18) | 100 | 8.60 | 99.40 (100 con la excepción) |
| hard, política de colocación (s11, s21) | 100 | 8.60 | 100.00 |

La forma de trabajar del cliente logra 5 / 9 / 9 colocaciones exactas; en medium y hard, 2 de ellas (copias) pierden una quinta parte porque el libro tiene otros archivos y su fila del manifiesto solo enumera el JSON. Con las semillas de mundo 1, 2 y 3, la forma de trabajar del cliente obtiene 3.33–20.00 (easy), 2.73–19.70 (medium) y 3.80–14.00 (hard), frente a referencias de 100.00 (99.40 con la política de revisión). Con la política de revisión, flexibilizar `missing_author_review` (colocar los dos libros sin autor con "Unknown") es válido cuando la regla se relaja y da 100.00 en hard/s18 (calidad normalizada 1.007).

## Notas

- El corpus visible es idéntico byte a byte en todas las configuraciones e idiomas (`content_dirs: [corpus]`); solo las notas del archivo, fuera del corpus, están localizadas.
- `write only inside out_dir` y `never modify the corpus` los hace cumplir el ejecutor (el programa recibe una copia del corpus, de solo lectura bajo docker); no se puntúan.

## Conjunto de datos guardado (`dataset/`)

Lo escribe `python -m fdebench2.cli export-dataset cases/data_knowledge/multilingual_corpus_curator`; `validate-case` lo regenera y falla si se aparta del generador (~2 MB, ~2,100 archivos pequeños). `audit-case` escribe `dataset/audit.json` (export-dataset lo conserva).

```
dataset/
  agent_view/<lang>/corpus/...       la unidad de muestra del agente (idéntica byte a byte en todos los idiomas) + las notas del archivo
  hidden/corpus/...                  la unidad de evaluación tal como la recibe organize() (igual en todas las configuraciones)
  audit.json                         la auditoría de la respuesta correcta (mundo público): respuestas que malinterpretan un hecho, atajos, valor de
                                       preguntar, cotas, comprobaciones directas; GT.md se genera a partir de ella
  answer/                            las semillas de reglas públicas (easy/s11 ... hard/s21), cada archivo con difficulty y seed
    answers.csv                      una fila por configuración: los parámetros sorteados (el fallback_author derivado no se
                                       guarda), el objetivo de la referencia y el de la forma de trabajar del cliente sobre el
                                       corpus de evaluación, el ancho de la escala de calidad, las reglas y los hechos por
                                       preguntar vigentes y las métricas de la referencia
    files/reference/program/         el organize.py del entregable de referencia (igual en todas las configuraciones; el
                                       config.json de cada una está en reference_program.jsonl)
    files/baseline/program/          el organize.py de la forma de trabajar del cliente (sus config.json en baseline_program.jsonl)
    reference_output_*               lo que escribe la referencia sobre el corpus de evaluación: reference_output_manifest.csv,
                                       reference_output__review_<REASON>.jsonl (los JSON de _review/), los demás archivos de
                                       _review/ en files/reference_output/ (iguales en todas las configuraciones) y library/
                                       en files/<difficulty>_s<seed>/reference_output/
    files/<difficulty>_s<seed>/expected_output/
                                     el out_dir correcto para los libros que puntúan en esta configuración, corpus de evaluación:
                                       library/... un archivo de sinopsis por libro colocado, en la ruta de la configuración
                                       _review/<REASON>/<ruta con / como __>  los archivos de origen de los libros en revisión
                                       (los JSON, en expected_output__review_<REASON>.jsonl)
    expected_output_manifest.csv     su manifest.csv: filas placed / review (con motivo) y, en hard, filas skipped de JUNK
    books.csv                        clave de respuestas (corpus de evaluación): cada libro con tipo, nivel, si puntúa,
                                       estado esperado, ruta y motivo, título/autores/años canónicos y sus archivos de origen
    expected_score.jsonl             expected_output puntuado por el evaluador: 100 en easy y medium; en hard, 99.4
                                       con la política de revisión (los dos libros NO_AUTHOR suman 0.7 en revisión; no
                                       se flexibiliza ninguna regla) y 100 con una política de colocación
```

Solo el corpus de evaluación tiene clave de respuestas: la muestra visible es el material del que aprende el agente, y no se calcula ninguna puntuación sobre ella. Los árboles esperados contienen solo los libros que puntúa el nivel (30 / 66 / 100); los libros fuera del nivel no forman parte de la respuesta de esa configuración. No se añadieron correos del cliente ni exportaciones SQL: la unidad ya contiene las exportaciones de catálogo del propio cliente, y añadir material nuevo cambiaría lo que el caso pone a prueba.
