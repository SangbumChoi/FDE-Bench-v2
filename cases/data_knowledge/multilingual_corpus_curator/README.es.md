# Curador de corpus multilingüe — `data_knowledge/multilingual_corpus_curator`

Una pequeña editorial guarda el material de unos cien libros (en chino, inglés, coreano, japonés y español) en una unidad compartida desordenada: el título, los autores, los años de publicación y la sinopsis de cada libro están repartidos en uno a tres archivos de formatos distintos, junto a escaneos, archivos comprimidos, exportaciones de catálogo y archivos basura. El agente entrega un **programa**, `program/organize.py` con `organize(task)`, `task = {"corpus_dir": "$INPUT_DIR", "out_dir": "$OUTPUT_DIR"}`, que construye una biblioteca normalizada:

```
out_dir/library/<estructura del conjunto de reglas>.txt   un archivo UTF-8 por libro: solo su sinopsis
out_dir/_review/...                                       archivos de origen de los libros que no se pueden colocar
out_dir/manifest.csv                                      source,status,path,reason (placed | review | skipped)
```

El agente ve una muestra visible (`data/corpus/`, 100 libros, ~120 archivos) y el programa se puntúa sobre un **corpus oculto** construido con la misma receta y otra semilla (mismo tamaño y misma mezcla), idéntico en las nueve configuraciones. Todo es sintético: los títulos, los nombres y las sinopsis se generan a partir de vocabularios inventados, escritos de forma nativa en cada idioma. Para leer todos los formatos basta con la biblioteca estándar.

## Configuraciones: un corpus, nueve soluciones correctas

El mundo, el corpus visible, el corpus oculto y la solicitud son los mismos en todas las configuraciones (el validador comprueba que lo que ve el agente es idéntico byte a byte). El nivel decide qué libros puntúan y qué reglas se aplican; el conjunto de reglas decide cómo es la biblioteca correcta.

### Niveles (mismo corpus; cambian el alcance y la exigencia)

| | easy | medium | hard |
|---|---|---|---|
| **Libros que puntúan** (corpus oculto) | 30 libros bien formados: un archivo, UTF-8, metadatos completos, años normales de cuatro cifras | 66: + todos los libros legibles | 100: + las excepciones |
| **Qué se añade** | Formatos, la estructura de rutas, las reglas de nombre, la extracción de la sinopsis, la base del año, las parejas romanizadas | Codificaciones antiguas (GB18030, CP949, Shift_JIS, CP1252); `令和元年`, `民國98年`, `단기 4342년`, `二〇〇九年`, `MMIX`; títulos en ancho completo y con acentos descompuestos; caracteres prohibidos en las rutas; un autor con varias romanizaciones (la pareja oficial solo aparece en los demás libros del autor); copias en varios formatos y carpetas que hay que fundir; precedencia de las fuentes (metadatos incrustados > portadilla > nombre de archivo) | Autor/título/sinopsis que faltan y se recuperan de otro archivo; título a partir de un nombre de archivo con sentido; año a partir de una línea `©`; revisión con código de motivo: `NO_AUTHOR` / `NO_TITLE` / `NO_YEAR` / `NO_DESCRIPTION` / `CONFLICT` (desacuerdo de año entre fuentes del mismo rango) / `UNREADABLE` (escaneo de solo imagen); escaneos que duplican un archivo legible; basura (`.DS_Store`, `Thumbs.db`, `desktop.ini`, archivos de bloqueo `~$`, `__MACOSX/._*`, archivos vacíos); libros dentro de archivos zip; CSV de catálogo con varios libros (cabeceras en inglés y en japonés) |
| **Reglas** | `utf8_output`, `safe_names` (física); `one_file_per_book`, `review_reason` (contractual) | igual | + `no_fabrication` (contractual); `missing_author_review` (costumbre del negocio, flexibilizable) |
| **Extras de puntuación** | los libros fuera del alcance se ignoran | −0.5 por cada archivo de la biblioteca que no es un libro | + un libro sin autor que espera en revisión suma 0.7 (colocarlo con el autor de reserva suma 1, pero exige una excepción aprobada); un archivo de la biblioteca cuyo texto no está en ninguna fuente incumple `no_fabrication` |

### Conjuntos de reglas (hiperparámetros de las reglas de biblioteca del cliente)

| Parámetro | A | B | C |
|---|---|---|---|
| Estructura de rutas | `library/<año>/<título>/<autor>.txt` | `library/<año>/<autor>/<título>.txt` | `library/<autor>/<año>_<título>.txt` |
| Base del año | primera publicación | esta edición | primera publicación |
| Escritura de títulos y nombres | original | original | latina (la romanización emparejada en los metadatos) |
| Coautores | solo el primer autor | todos, unidos con `" & "` | solo el primer autor |
| Separador que sustituye a los espacios | `_` | `-` | un espacio normal |
| Longitud máxima de una parte de título o autor | 60 | 40 | 80 |
| Autor de reserva (solo con una excepción aprobada) | `Unknown` | `Anonymous` | `Unknown Author` |

Reglas de nombre comunes a todos los conjuntos: NFKC; cada `\ / : * ? " < > |` o carácter de control pasa a ser un espacio; cada tramo de espacios en blanco pasa a ser el separador; se corta a la longitud máxima; se quitan espacios, puntos y separadores en ambos extremos.

Dentro de cada nivel, la referencia de cada conjunto de reglas es claramente errónea bajo los otros conjuntos (objetivo de la referencia de la fila bajo el conjunto de la columna, dividido por el objetivo de la referencia de ese conjunto; todas son válidas, así que la diferencia está en las rutas):

| referencia → puntuada bajo | easy | medium | hard |
|---|---|---|---|
| A bajo B / B bajo A | 0.507 | 0.520 | 0.575 |
| A o B bajo C / C bajo A o B | 0.400 | 0.405 | 0.470 |

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

Por libro puntuado: **1** por la ruta exacta en la biblioteca con la sinopsis correcta; si no, un archivo de la biblioteca encontrado por su sinopsis suma 0.4 + 0.2 por cada componente correcto (año, título, autor), y la ruta correcta con cualquier otro texto suma 0.2. Un libro que debe ir a revisión suma 1 cuando todas las filas del manifiesto que nombran alguno de sus archivos dicen `review` con el código de motivo correcto (0.4 si coinciden en otro código; un libro `NO_AUTHOR` suma 0.7 en revisión); si las filas se contradicen, o si el libro tiene además un archivo en la biblioteca, no suma nada. También se revisa la fila de cada libro en el manifiesto (la única fila que nombra los archivos del libro, todos ellos y nada más; `placed` con la ruta del libro en la biblioteca, o `review` con sus archivos copiados byte a byte bajo `_review/`; un escaneo que copia un archivo legible puede ir en la fila, figurar como skipped u omitirse): una fila que falta o está mal cuesta una quinta parte del crédito del libro. Medium y hard restan 0.5 por cada archivo de la biblioteca que no es un libro. Objetivo = 100 × crédito / libros puntuados (maximizar); la calidad se normaliza entre la línea base (0) y la referencia (1). Las sinopsis se comparan tras NFKC y sin espacios en blanco, así que los cortes de línea no importan. En hard, `no_fabrication` también salta con un archivo no vacío de la biblioteca que no contiene ningún párrafo completo de sinopsis de ningún libro ni es un fragmento (20+ caracteres) de uno: textos de relleno y sinopsis inventadas; un encabezado suelto o un párrafo omitido solo cuestan crédito.

Dos sondas cuya respuesta da la puntuación (hard, corpus oculto): `expected_output` con sus filas de revisión sustituidas por una fila por cada combinación de archivo del corpus y código de motivo puntúa 71.6 (antes obtenía el máximo posible, 99.4), y el mismo árbol esperado con todas las sinopsis sustituidas por `x` incumple `no_fabrication` (antes puntuaba 64.2 y era válido).

La salida del programa sobre el corpus oculto se guarda en caché según el resumen (digest) del programa, de modo que las nueve configuraciones, los ejemplos de infracción y las comprobaciones cruzadas entre conjuntos de reglas ejecutan cada programa distinto una sola vez (`validate-case` tarda ~40 s con las semillas de mundo por defecto 1–3).

## Referencia y cifras verificadas (semilla 20261027, corpus oculto)

La línea base (`reference/baseline.py` + el mismo `config.json`) es lo que el cliente podría programar sin un ingeniero: coloca solo los libros que tienen una exportación JSON completa en UTF-8 (título, autor, un año normal de cuatro cifras y una sinopsis) según las reglas del catálogo, y deja todos los demás archivos para el equipo (ningún otro formato, ni codificaciones antiguas ni años de era, sin fundir copias, sin área de revisión). Es válida en todas las configuraciones.

La referencia (`reference/organize.py` + `config.json` del conjunto de reglas) es un organizador sólido basado en reglas: todos los formatos, codificaciones antiguas detectadas mediante las estadísticas de caracteres UTF-8 del propio corpus, años de era, slugs NFKC, agrupación por título normalizado, precedencia por campo, emparejamiento de nombres en los archivos del propio libro, escaneos, basura y catálogos. Huecos deliberados (margen de mejora): sin archivos zip, sin años en números romanos ni en numerales chinos, sin años de línea de copyright, sin detección de conflictos del mismo rango, sin un mapa de nombres de autor para todo el corpus, y mantiene la política de `NO_AUTHOR`.

| Configuración | Libros puntuados | Objetivo de la línea base | Objetivo de la referencia | Máximo posible (sin flexibilizar) | Su calidad normalizada |
|---|---|---|---|---|---|
| easy/A, B, C | 30 | 10.00 | 100.00 | 100.00 | 1.00 |
| medium/A, B, C | 66 | 13.33 | 92.73 | 100.00 | 1.09 |
| hard/A, B, C | 100 | 10.80 | 85.60 | 99.40 (100 con la excepción) | 1.18 (1.19) |

Los tres conjuntos de reglas dan las mismas cifras con esta semilla (las rutas de cada conjunto se puntúan con sus propias reglas). Medias por nivel de la referencia: **easy 100.00, medium 92.73, hard 85.60**; de la línea base: easy 10.00, medium 13.33, hard 10.80 (línea base/referencia 0.10 / 0.14 / 0.13). La línea base logra 3 / 10 / 12 colocaciones exactas; en medium y hard, 6 de ellas (copias y parejas de precedencia) pierden una quinta parte porque el libro tiene otros archivos y su fila del manifiesto solo enumera el JSON, y en hard coloca los 2 libros `CONFLICT`, lo que no suma nada. Con las semillas de mundo 1, 2 y 3, la línea base obtiene 6.7–20.0 (easy), 8.2–13.3 (medium) y 5.4–8.8 (hard), frente a referencias de 100.00, 94.24–95.76 y 86.60–87.60. Sobre la muestra visible, la referencia obtiene 100.00 / 94.24 / 86.60. Flexibilizar `missing_author_review` (colocar los dos libros sin autor con el autor de reserva) es válido cuando la regla se relaja y da 86.20 en hard (calidad normalizada 1.008).

Con qué frecuencia cada parámetro del conjunto de reglas cambia la respuesta (libros colocados dentro del alcance, corpus oculto):

| | easy | medium | hard |
|---|---|---|---|
| Base del año (primera publicación ≠ esta edición) | 14 | 30 | 38 |
| Escritura (títulos y nombres no latinos) | 18 | 40 | 55 |
| Coautores (libros con 2 autores) | 6 | 13 | 14 |
| Separador (títulos con espacios) | 18 | 40 | 52 |
| Corte de longitud (A 60 / B 40 / C 80) | 3 / 3 / 0 | 7 / 7 / 2 | 9 / 9 / 3 |

Lo que pierde la referencia en el corpus oculto: medium — 4 libros con años en números romanos o en numerales chinos van a revisión como `NO_YEAR` y 4 libros con variantes de autor reciben un nombre no oficial (0.8 cada uno); hard — además, 4 libros en zips, 3 años de línea de copyright, 2 conflictos del mismo rango colocados en lugar de enviados a revisión, y 2 × 0.3 por mantener la política de `NO_AUTHOR`.

## Notas

- El corpus visible es idéntico byte a byte en todas las configuraciones e idiomas (`content_dirs: [corpus]`); solo las notas del archivo, fuera del corpus, están localizadas.
- `write only inside out_dir` y `never modify the corpus` los hace cumplir el ejecutor (el programa recibe una copia del corpus, de solo lectura bajo docker); no se puntúan.

## Conjunto de datos guardado (`dataset/`)

Lo escribe `python -m fdebench2.cli export-dataset cases/data_knowledge/multilingual_corpus_curator`; `validate-case` lo regenera y falla si se aparta del generador (~2 MB, ~2,300 archivos pequeños).

```
dataset/
  visible/<lang>/corpus/...          la unidad de muestra del agente (idéntica byte a byte en todos los idiomas) + las notas del archivo
  hidden/corpus/...                  la unidad oculta tal como la recibe organize() (igual en las nueve configuraciones)
  gt/<tier>_<A|B|C>/
    setting.json, score.json         la configuración y la puntuación de la referencia sobre el corpus oculto (con el
                                       objetivo de la línea base y ambas calidades normalizadas)
    reference/program/               el entregable de referencia (organize.py + config.json del conjunto de reglas)
    reference_output/                lo que escribe la referencia sobre el corpus oculto (library/, _review/, manifest.csv)
    expected_output/                 el out_dir correcto para los libros que puntúan en esta configuración, corpus oculto:
                                       library/... un archivo de sinopsis por libro colocado, en la ruta del conjunto de reglas
                                       _review/<REASON>/<ruta con / como __>  los archivos de origen de los libros en revisión
                                       manifest.csv  filas placed / review (con motivo) y, en hard, filas skipped de JUNK
    books.csv                        clave de respuestas (corpus oculto): cada libro con tipo, nivel, si puntúa, estado
                                       esperado, ruta y motivo, título/autores/años canónicos y sus archivos de origen
    expected_score.json              expected_output puntuado por el evaluador: 100 en easy y medium, 99.4 en hard
                                       (los dos libros NO_AUTHOR suman 0.7 en revisión; no se flexibiliza ninguna regla)
```

Solo el corpus oculto tiene clave de respuestas: la muestra visible es el material del que aprende el agente, y no se calcula ninguna puntuación sobre ella. Los árboles esperados contienen solo los libros que puntúa el nivel (30 / 66 / 100); los libros fuera del nivel no forman parte de la respuesta de esa configuración. No se añadieron correos del cliente ni exportaciones SQL: la unidad ya contiene las exportaciones de catálogo del propio cliente, y añadir material nuevo cambiaría lo que el caso pone a prueba.
