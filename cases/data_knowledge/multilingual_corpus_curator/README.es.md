# Curador de corpus multilingüe — `data_knowledge/multilingual_corpus_curator`

Una pequeña editorial guarda el material de unos cien libros (en chino, inglés, coreano, japonés y español) en una unidad compartida desordenada: el título, los autores, los años de publicación y la sinopsis de cada libro están repartidos en uno a tres archivos de formatos distintos, junto a escaneos, archivos comprimidos, exportaciones de catálogo y archivos basura. El agente entrega un **programa**, `program/organize.py` con `organize(task)`, `task = {"corpus_dir": "$INPUT_DIR", "out_dir": "$OUTPUT_DIR"}`, que construye una biblioteca normalizada:

```
out_dir/library/<estructura sorteada>.txt   un archivo UTF-8 por libro: solo su sinopsis
out_dir/_review/...                         archivos de origen de los libros que no se pueden colocar
out_dir/manifest.csv                        source,status,path,reason (placed | review | skipped)
```

El agente ve una muestra visible (`data/corpus/`, 100 libros, ~120 archivos) y el programa se puntúa sobre un **corpus oculto** construido con la misma receta y otra semilla (mismo tamaño y misma mezcla), idéntico en todas las configuraciones. Todo es sintético: los títulos, los nombres y las sinopsis se generan a partir de vocabularios inventados, escritos de forma nativa en cada idioma. Para leer todos los formatos basta con la biblioteca estándar.

## Configuraciones: un corpus, niveles × semillas de reglas

Una configuración es un nivel y una semilla de reglas. El mundo, el corpus visible, el corpus oculto y la solicitud son los mismos en todas las configuraciones (el validador comprueba que lo que ve el agente es idéntico byte a byte). El nivel decide qué libros puntúan, qué reglas se aplican y entre qué candidatos sortea la semilla de reglas; la semilla de reglas sortea las reglas de biblioteca del cliente, cada parámetro por separado, de modo que la biblioteca correcta cambia de una semilla a otra. El panel público son las semillas de reglas **11, 18 y 21** (nueve configuraciones, guardadas en `dataset/gt/` y comprobadas por el validador); cualquier otra semilla es un sorteo privado cuyas respuestas no se publican en ningún sitio.

### Niveles (mismo corpus; cambian el alcance, la exigencia y los candidatos)

| | easy | medium | hard |
|---|---|---|---|
| **Libros que puntúan** (corpus oculto) | 30 libros bien formados: un archivo, UTF-8, metadatos completos, años normales de cuatro cifras | 66: + todos los libros legibles | 100: + las excepciones |
| **Qué se añade** | Formatos, la estructura de rutas, las reglas de nombre, la extracción de la sinopsis, la base del año, las parejas romanizadas | Codificaciones antiguas (GB18030, CP949, Shift_JIS, CP1252); `令和元年`, `民國98年`, `단기 4342년`, `二〇〇九年`, `MMIX`; títulos en ancho completo y con acentos descompuestos; caracteres prohibidos en las rutas; un autor con varias romanizaciones (la pareja oficial solo aparece en los demás libros del autor); copias en varios formatos y carpetas que hay que fundir; precedencia de las fuentes (metadatos incrustados > portadilla > nombre de archivo) | Autor/título/sinopsis que faltan y se recuperan de otro archivo; título a partir de un nombre de archivo con sentido; año a partir de una línea `©`; revisión con código de motivo: `NO_TITLE` / `NO_YEAR` / `NO_DESCRIPTION` / `CONFLICT` (desacuerdo de año entre fuentes del mismo rango) / `UNREADABLE` (escaneo de solo imagen); la política del cliente para los libros sin autor (revisión `NO_AUTHOR`, o colocarlos con un nombre de autor de reserva); escaneos que duplican un archivo legible; basura (`.DS_Store`, `Thumbs.db`, `desktop.ini`, archivos de bloqueo `~$`, `__MACOSX/._*`, archivos vacíos); libros dentro de archivos zip; CSV de catálogo con varios libros (cabeceras en inglés y en japonés) |
| **Candidatos de longitud de nombre** (`max_len`) | 60, 48, 40: solo se cortan los títulos largos con subtítulo | 50, 40, 32: + algunos títulos más largos y, con 32, listas de coautores | 40, 32, 24: + títulos de longitud media y listas de coautores |
| **Política para libros sin autor** (`no_author`) | no se sortea (esos libros quedan fuera del alcance) | no se sortea | revisión, o colocarlos con el nombre de autor "Unknown" o "Anonymous" |
| **Reglas** | `utf8_output`, `safe_names` (física); `one_file_per_book`, `review_reason` (contractual) | igual | + `no_fabrication` (contractual); `missing_author_review` (costumbre del negocio, flexibilizable) solo con la política de revisión |
| **Extras de puntuación** | los libros fuera del alcance se ignoran | −0.5 por cada archivo de la biblioteca que no es un libro | política de revisión: un libro sin autor que espera en revisión suma 0.7 (colocarlo con el autor de reserva suma 1, pero exige una excepción aprobada); política de colocación: ese libro se puntúa como cualquier otro libro colocado y en revisión no suma nada; un archivo de la biblioteca cuyo texto no está en ninguna fuente incumple `no_fabrication` |
| **Lo que los requisitos dejan fuera del alcance** | "Los demás archivos de la unidad (codificaciones antiguas, copias en varios formatos, material dañado o incompleto, archivos comprimidos, catálogos, escaneos) todavía no se revisan, pero el programa no debe detenerse por ellos" | "Las excepciones (datos que faltan, escaneos, archivos comprimidos, catálogos, archivos basura) todavía no puntúan, pero nada que no sea un libro debe acabar en la biblioteca" | nada |

Una semilla de reglas sortea la misma posición de la lista de candidatos en todos los niveles (el sorteo no depende del nivel), pero `max_len` tiene candidatos distintos en cada nivel y `no_author` solo tiene candidatos en hard. Así, la misma semilla da un límite de nombre más estricto en cada nivel más difícil y, en hard, puede cambiar la política para libros sin autor: las referencias de los tres niveles difieren en todas las semillas públicas, y cada una, puntuada bajo otro nivel, queda por debajo de la referencia propia de ese nivel (tabla de abajo).

### Parámetros

Una semilla de reglas s sortea la posición `Random("data_knowledge/multilingual_corpus_curator|<name>|s").randrange(n)` de cada lista de n candidatos, de forma independiente de los demás parámetros. Las cinco primeras listas son iguales en todos los niveles.

| Parámetro | Candidatos | Qué cambia (corpus oculto, mundo público, libros colocados dentro del alcance easy / medium / hard) | Pregunta clave |
|---|---|---|---|
| `layout` | `library/<año>/<título>/<autor>.txt`, `library/<año>/<autor>/<título>.txt`, `library/<autor>/<año>_<título>.txt` | la ruta de cada libro colocado (30 / 66 / 88) | `layout` |
| `year_basis` | primera publicación, esta edición (un libro con un solo año lo usa para ambas) | libros cuyos dos años difieren (14 / 30 / 38) | `year_basis` |
| `script` | original, latina (la romanización emparejada en los metadatos) | libros en chino, coreano y japonés (18 / 40 / 55) | `script` |
| `multi_author` | solo el primer autor, todos unidos con `" & "` | libros con dos autores (6 / 13 / 14) | `co_authors` |
| `sep` | `_`, `-`, un espacio normal | nombres con espacios (18 / 40 / 52 en la escritura original, todos los libros en la latina) | `name_rules` |
| `max_len` | easy 60, 48, 40; medium 50, 40, 32; hard 40, 32, 24 | nombres más largos que el límite: easy 3 con cualquier valor; medium 7, 7, 8–11; hard 9, 10–13, 13–21 (rangos según la escritura y la regla de coautores) | `name_rules` |
| `no_author` | easy y medium `review`; hard `review`, `Unknown`, `Anonymous` | los 2 libros sin autor (hard): `review` los envía a revisión como `NO_AUTHOR` (0.7 cada uno) según la regla flexibilizable `missing_author_review`; un nombre los coloca con ese nombre de autor como cualquier otro libro (1 cada uno, 0 en revisión) | `missing_author` |

`derive_params` añade `fallback_author`, el nombre que citan los textos: el nombre sorteado con una política de colocación, y "Unknown" (el nombre que usaría una excepción aprobada) con la política de revisión. Ninguna combinación es inviable: en el mundo público y con las semillas de mundo 1–20 (corpus visible y oculto), ningún par de libros colocados de ningún nivel comparte ruta bajo ninguna de las 216 combinaciones de easy y medium ni de las 648 de hard, así que el caso no define `admissible`.

Reglas de nombre en todas las configuraciones: NFKC; cada `\ / : * ? " < > |` o carácter de control pasa a ser un espacio; cada tramo de espacios en blanco pasa a ser el separador; se corta a `max_len` caracteres; se quitan espacios, puntos y separadores en ambos extremos. Un límite más estricto alcanza más nombres, así que equivocarse en el orden de estos pasos cuesta más a menudo: cortar un título español con acentos descompuestos antes de NFKC conserva menos letras, y un corte que cae en un separador deja uno por quitar.

### Panel público

El panel muestra todos los candidatos de todos los parámetros: entre las semillas 11, 18 y 21, cada lista de tres candidatos da sus tres valores (en todos los niveles) y cada lista de dos, sus dos valores. La semilla 11 va primero porque validate-case comprueba la influencia de los parámetros a partir de ella, y su sorteo de hard coloca los libros sin autor, así que la comprobación de la política compara una referencia válida con política de colocación con la política de revisión que esa referencia incumple.

| Configuración | `layout` | `year_basis` | `script` | `multi_author` | `sep` | `max_len` | `no_author` (→ `fallback_author`) | Referencia | Línea base | Máximo posible |
|---|---|---|---|---|---|---|---|---|---|---|
| easy/s11 | author/year_title | first | latin | all | `" "` | 40 | review (Unknown) | 100.00 | 10.00 | 100.00 |
| easy/s18 | year/title/author | first | latin | first | `-` | 48 | review (Unknown) | 100.00 | 10.00 | 100.00 |
| easy/s21 | year/author/title | edition | original | first | `_` | 60 | review (Unknown) | 100.00 | 10.00 | 100.00 |
| medium/s11 | author/year_title | first | latin | all | `" "` | 32 | review (Unknown) | 92.73 | 13.33 | 100.00 |
| medium/s18 | year/title/author | first | latin | first | `-` | 40 | review (Unknown) | 92.73 | 13.33 | 100.00 |
| medium/s21 | year/author/title | edition | original | first | `_` | 50 | review (Unknown) | 92.73 | 13.33 | 100.00 |
| hard/s11 | author/year_title | first | latin | all | `" "` | 24 | Unknown | 86.20 | 10.80 | 100.00 |
| hard/s18 | year/title/author | first | latin | first | `-` | 32 | review (Unknown) | 85.60 | 10.80 | 99.40 (100 con la excepción) |
| hard/s21 | year/author/title | edition | original | first | `_` | 40 | Anonymous | 86.20 | 10.80 | 100.00 |

Objetivos sobre el corpus oculto con la semilla de mundo pública (20261027); el "máximo posible" es `expected_output` puntuado por el evaluador. Las semillas privadas sortean cualquier otra combinación; p. ej., la semilla 101: `author/year_title`, first, original, first, `-`, 60 / 50 / 40, review en todos los niveles; la semilla 102: `year/author/title`, first, original, first, `_`, 40 / 32 / 24, `Unknown` en hard.

**Influencia de los parámetros** (validate-case, desde hard/s11): cada parámetro cambia la puntuación de la referencia con el primer valor distinto que prueba. En el mundo público, la referencia de hard/s11 obtiene 86.20, y con un solo parámetro cambiado: `layout` 39.60, `year_basis` → edition 79.60, `script` → original 67.80, `multi_author` → first 83.60, `sep` → `_` 55.80, `max_len` → 40 81.60, `no_author` → review inválida (`missing_author_review`). Entre los dos nombres de reserva, la referencia solo pierde 0.4 (85.80: los dos libros sin autor conservan año y título), por debajo del margen del 1 %; `no_author` influye a través de la política, no del nombre. En easy y medium los candidatos de longitud también influyen: la referencia de easy/s11 obtiene 98.00 con un límite de 60 caracteres, y la de medium/s11, 89.09 con 50. Las mismas comprobaciones se superan con las semillas de mundo 1, 2 y 3.

**Referencias entre configuraciones** (mundo público; cada fila es una configuración y cada celda, la referencia de otra configuración puntuada bajo ella; `*` = inválida):

| Puntuada bajo | easy s11 / s18 / s21 | medium s11 / s18 / s21 | hard s11 / s18 / s21 |
|---|---|---|---|
| easy/s11 | **100.00** / 40.00 / 40.00 | 96.00 / 40.00 / 40.00 | 94.67 / 40.00 / 40.00 |
| easy/s18 | 40.00 / **100.00** / 50.67 | 40.00 / 98.00 / 50.67 | 40.00 / 97.33 / 50.67 |
| easy/s21 | 40.00 / 50.67 / **100.00** | 40.00 / 50.67 / 98.00 | 40.00 / 50.67 / 98.00 |
| medium/s11 | 89.09 / 37.58 / 37.58 | **92.73** / 37.58 / 37.58 | 86.67 / 37.58 / 37.58 |
| medium/s18 | 37.58 / 90.91 / 48.18 | 37.58 / **92.73** / 48.18 | 37.58 / 90.61 / 48.18 |
| medium/s21 | 37.58 / 48.18 / 90.91 | 37.58 / 48.18 / **92.73** | 37.58 / 48.18 / 90.91 |
| hard/s11 | 79.60 / 38.80 / 38.80 | 79.60 / 38.80 / 38.80 | **86.20** / 38.80 / 39.60 |
| hard/s18 | 40.20 / 83.80 / 49.20 | 40.20 / 83.80 / 49.20 | 39.60* / **85.60** / 48.80* |
| hard/s21 | 38.80 / 47.80 / 82.60 | 38.80 / 47.80 / 82.60 | 39.60 / 47.80 / **86.20** |

La referencia de otra semilla conserva su estructura de rutas, así que sus archivos solo se encuentran por la sinopsis (0.4 más los componentes correctos). La referencia de la misma semilla en otro nivel difiere en el límite de longitud y, en hard/s11 y hard/s21, en la política para libros sin autor: pierde 1.8–6.6 puntos, y las dos referencias con política de colocación son inválidas bajo la política de revisión de hard/s18.

### Lo que un agente debe preguntar

Seis preguntas clave llevan el sorteo de la semilla de reglas y no se pueden leer en los datos ni trasladar de otra ejecución: `layout`, `year_basis`, `script`, `co_authors`, `name_rules` (separador y límite de longitud) y, en hard, `missing_author` (la política para libros sin autor y el nombre de reserva). Las demás (`content`, `manifest_review`, `precedence`, `scoring` y, según el nivel, `encodings`, `year_notations`, `author_variants`, `duplicates`, `exceptions`, `containers`) son iguales con cualquier sorteo.

## Formatos de archivo y catálogo de excepciones

| Tipo | Dónde están los datos |
|---|---|
| JSON | `title`, `title_latin`, `authors[{name, name_latin}]`, `first_published`, `edition_year`, `description` (en medium los años pueden ser cadenas con eras) |
| XML de tipo ONIX (espacio de nombres `ns.editeur.org/onix/3.0`) | `TitleText` (+ `textscript="Latn"`), `Contributor/PersonName` + `AlternativeName` o `PersonNameInverted`, `PublishingDateRole` 01 = esta edición, 11 = primera publicación, `TextContent/Text` |
| EPUB (zip + OPF) | `dc:title`, `dc:creator` con refinamientos `alternate-script` / `file-as`, `dc:date` (esta edición), meta `first-published`, `dc:description`; `dcterms:modified` es una trampa |
| DOCX (zip + XML) | title y creator de `docProps/core.xml` (`dcterms:created` es una trampa); párrafos del cuerpo partidos en varios runs = portadilla + sinopsis |
| PDF (flujos de texto sin comprimir) | `/Title` y `/Author` de Info (cadenas hexadecimales UTF-16; `/CreationDate` es una trampa); texto de página como cadenas `Tj` en UTF-16, con líneas cortadas |
| PDF escaneado | página de solo imagen, sin texto ni título: ilegible |
| HTML | `<title>`, `<meta name="author">`; en el cuerpo, `h1`, `p.latin`, `p.byline`, `p.edition`, `h2` y párrafos de sinopsis; `<meta charset>` (Shift_JIS / CP949 en medium) |
| Markdown | bloque inicial (`title`, `title_latin`, `author`, `author_latin`, `first_published`, `edition`) + portadilla en el cuerpo |
| Texto plano | portadilla (título, `(título romanizado)`, `Nombre（Romanizado） 著` / `지음` / `by` / `por`, línea de edición, línea `©` opcional), encabezado (`内容简介`, `内容紹介`, `책 소개`, `About this book`, `Sinopsis`), sinopsis (a veces con cortes de línea fijos, CRLF o en una codificación antigua) |
| CSV de catálogo | un libro por fila; cabeceras en inglés o en japonés; `source` = `file.csv#row` |
| Archivo zip | 2 libros cada uno más una entrada AppleDouble `__MACOSX/._*`; `source` = `archive.zip!inner/path` |

Composición de cada corpus (cantidades fijas, idiomas en parte aleatorios): 30 easy; medium: 7 codificaciones, 6 notaciones de año, 4 títulos en ancho completo o descompuestos, 5 caracteres prohibidos, 5 variantes de romanización, 6 copias en varios archivos, 3 conflictos de precedencia; hard: 3 autores recuperados, 2 sin autor, 2 títulos a partir del nombre de archivo, 2 sin título, 2 sinopsis recuperadas, 2 sin sinopsis, 3 años de línea de copyright, 2 sin año, 2 conflictos del mismo rango, 2 solo con escaneo, 2 escaneos con copia legible, 4 libros en zips, 6 filas de catálogo; más 8 archivos basura.

## Puntuación

Por libro puntuado: **1** por la ruta exacta en la biblioteca con la sinopsis correcta; si no, un archivo de la biblioteca encontrado por su sinopsis suma 0.4 + 0.2 por cada componente correcto (año, título, autor), y la ruta correcta con cualquier otro texto suma 0.2. Un libro que debe ir a revisión suma 1 cuando todas las filas del manifiesto que nombran alguno de sus archivos dicen `review` con el código de motivo correcto (0.4 si coinciden en otro código; con la política de revisión, un libro `NO_AUTHOR` suma 0.7 en revisión); si las filas se contradicen, o si el libro tiene además un archivo en la biblioteca, no suma nada. Un libro que debe ir a la biblioteca no suma nada en revisión; con una política de colocación eso incluye los libros sin autor, cuyo autor esperado es el nombre de reserva sorteado. También se revisa la fila de cada libro en el manifiesto (la única fila que nombra los archivos del libro, todos ellos y nada más; `placed` con la ruta del libro en la biblioteca, o `review` con sus archivos copiados byte a byte bajo `_review/`; un escaneo que copia un archivo legible puede ir en la fila, figurar como skipped u omitirse): una fila que falta o está mal cuesta una quinta parte del crédito del libro. Medium y hard restan 0.5 por cada archivo de la biblioteca que no es un libro. Objetivo = 100 × crédito / libros puntuados (maximizar); la calidad se normaliza entre la línea base (0) y la referencia (1). Las sinopsis se comparan tras NFKC y sin espacios en blanco, así que los cortes de línea no importan. En hard, `no_fabrication` también salta con un archivo no vacío de la biblioteca que no contiene ningún párrafo completo de sinopsis de ningún libro ni es un fragmento (20+ caracteres) de uno: textos de relleno y sinopsis inventadas; un encabezado suelto o un párrafo omitido solo cuestan crédito.

Dos sondas cuya respuesta da la puntuación (corpus oculto, mundo público): `expected_output` con sus filas de revisión sustituidas por seis filas `review` (una por código de motivo) por cada archivo del corpus puntúa 72.40 en hard/s18 y 74.00 en hard/s11 y hard/s21 (80.00 en easy y medium), frente a 99.40 / 100.00 del propio árbol; el mismo árbol esperado con todas las sinopsis sustituidas por `x` puntúa 20.00 en easy y medium e incumple `no_fabrication` en hard.

La salida del programa sobre el corpus oculto se guarda en caché según el resumen (digest) del programa, de modo que las configuraciones, los ejemplos de incumplimiento y las comprobaciones de influencia y entre niveles ejecutan cada programa distinto una sola vez (`validate-case` tarda unos dos minutos con las semillas de mundo por defecto 1–3).

## Referencia y cifras verificadas (semilla 20261027, corpus oculto)

La línea base (`reference/baseline.py` + el mismo `config.json`) es lo que el cliente podría programar sin un ingeniero: coloca solo los libros que tienen una exportación JSON completa en UTF-8 (título, autor, un año normal de cuatro cifras y una sinopsis) según las reglas del catálogo, y deja todos los demás archivos para el equipo (ningún otro formato, ni codificaciones antiguas ni años de era, sin fundir copias, sin área de revisión). Es válida en todas las configuraciones.

La referencia (`reference/organize.py` + `config.json` de la configuración) es un organizador sólido basado en reglas: todos los formatos, codificaciones antiguas detectadas mediante las estadísticas de caracteres UTF-8 del propio corpus, años de era, slugs NFKC, agrupación por título normalizado, precedencia por campo, emparejamiento de nombres en los archivos del propio libro, escaneos, basura y catálogos, y la política para libros sin autor sorteada. Huecos deliberados (margen de mejora): sin archivos zip, sin años en números romanos ni en numerales chinos, sin años de línea de copyright, sin detección de conflictos del mismo rango y sin un mapa de nombres de autor para todo el corpus.

| Nivel | Libros puntuados | Objetivo de la línea base | Objetivo de la referencia | Máximo posible (sin flexibilizar) | Su calidad normalizada |
|---|---|---|---|---|---|
| easy (s11, s18, s21) | 30 | 10.00 | 100.00 | 100.00 | 1.00 |
| medium (s11, s18, s21) | 66 | 13.33 | 92.73 | 100.00 | 1.09 |
| hard, política de revisión (s18) | 100 | 10.80 | 85.60 | 99.40 (100 con la excepción) | 1.18 (1.19) |
| hard, política de colocación (s11, s21) | 100 | 10.80 | 86.20 | 100.00 | 1.18 |

Dentro de un nivel, las reglas de biblioteca sorteadas no cambian estas cifras en este mundo (las rutas de cada configuración se puntúan con sus propias reglas); solo las cambia la política para libros sin autor, en 0.6. Medias por nivel de la referencia sobre el panel: **easy 100.00, medium 92.73, hard 86.00**; de la línea base: easy 10.00, medium 13.33, hard 10.80 (línea base/referencia 0.10 / 0.14 / 0.13). La línea base logra 3 / 10 / 12 colocaciones exactas; en medium y hard, 6 de ellas (copias y parejas de precedencia) pierden una quinta parte porque el libro tiene otros archivos y su fila del manifiesto solo enumera el JSON, y en hard coloca los 2 libros `CONFLICT`, lo que no suma nada. Con las semillas de mundo 1, 2 y 3, la línea base obtiene 6.67–20.00 (easy), 8.18–13.33 (medium) y 5.40–8.80 (hard), frente a referencias de 100.00, 94.24–95.76 y 86.60–87.60 (política de revisión) o 87.20–88.20 (política de colocación). Con la política de revisión, flexibilizar `missing_author_review` (colocar los dos libros sin autor con "Unknown") es válido cuando la regla se relaja y da 86.20 en hard/s18 (calidad normalizada 1.008).

Lo que pierde la referencia en el corpus oculto: medium — 4 libros con años en números romanos o en numerales chinos van a revisión como `NO_YEAR` y 4 libros con variantes de autor reciben un nombre no oficial (0.8 cada uno); hard — además, 4 libros en zips, 3 años de línea de copyright, 2 conflictos del mismo rango colocados en lugar de enviados a revisión y, con la política de revisión, 2 × 0.3 por mantener la política de `NO_AUTHOR`.

## Notas

- El corpus visible es idéntico byte a byte en todas las configuraciones e idiomas (`content_dirs: [corpus]`); solo las notas del archivo, fuera del corpus, están localizadas.
- `write only inside out_dir` y `never modify the corpus` los hace cumplir el ejecutor (el programa recibe una copia del corpus, de solo lectura bajo docker); no se puntúan.

## Conjunto de datos guardado (`dataset/`)

Lo escribe `python -m fdebench2.cli export-dataset cases/data_knowledge/multilingual_corpus_curator`; `validate-case` lo regenera y falla si se aparta del generador (~2 MB, ~2,300 archivos pequeños).

```
dataset/
  agent_view/<lang>/corpus/...       la unidad de muestra del agente (idéntica byte a byte en todos los idiomas) + las notas del archivo
  hidden/corpus/...                  la unidad oculta tal como la recibe organize() (igual en todas las configuraciones)
  gt/<tier>_s<seed>/                 easy_s11 ... hard_s21, el panel público
    setting.json, score.json         los parámetros sorteados (+ el fallback_author derivado) y la puntuación de la
                                       referencia sobre el corpus oculto (con el objetivo de la línea base y ambas
                                       calidades normalizadas)
    reference/program/               el entregable de referencia (organize.py + config.json de la configuración)
    reference_output/                lo que escribe la referencia sobre el corpus oculto (library/, _review/, manifest.csv)
    expected_output/                 el out_dir correcto para los libros que puntúan en esta configuración, corpus oculto:
                                       library/... un archivo de sinopsis por libro colocado, en la ruta de la configuración
                                       _review/<REASON>/<ruta con / como __>  los archivos de origen de los libros en revisión
                                       manifest.csv  filas placed / review (con motivo) y, en hard, filas skipped de JUNK
    books.csv                        clave de respuestas (corpus oculto): cada libro con tipo, nivel, si puntúa, estado
                                       esperado, ruta y motivo, título/autores/años canónicos y sus archivos de origen
    expected_score.json              expected_output puntuado por el evaluador: 100 en easy y medium; en hard, 99.4
                                       con la política de revisión (los dos libros NO_AUTHOR suman 0.7 en revisión; no
                                       se flexibiliza ninguna regla) y 100 con una política de colocación
```

Solo el corpus oculto tiene clave de respuestas: la muestra visible es el material del que aprende el agente, y no se calcula ninguna puntuación sobre ella. Los árboles esperados contienen solo los libros que puntúa el nivel (30 / 66 / 100); los libros fuera del nivel no forman parte de la respuesta de esa configuración. No se añadieron correos del cliente ni exportaciones SQL: la unidad ya contiene las exportaciones de catálogo del propio cliente, y añadir material nuevo cambiaría lo que el caso pone a prueba.
