# Una biblioteca limpia a partir de nuestra unidad compartida

## Contexto

En nuestra unidad compartida está el material de unos cien libros nuestros, en chino, inglés, coreano, japonés y español, y nadie lo ha mantenido en orden: títulos, autores, años y sinopsis andan repartidos en todo tipo de archivos de las oficinas regionales, el equipo de escaneo y el departamento de derechos. Adjuntamos una muestra de la unidad (`corpus/`). Necesitamos un programa que, ejecutado sobre la unidad completa, construya una biblioteca limpia y un manifiesto; lo que no pueda archivar queda para nuestro equipo, sin adivinar.

## Entregable

Una carpeta `program/` con `organize.py`, que define `organize(task)`, donde `task = {"corpus_dir": ..., "out_dir": ...}`. Lo ejecutamos una vez, sin conexión, sobre la unidad completa (misma estructura y misma mezcla de archivos que la muestra, unos 100 libros; solo la biblioteca estándar de Python; 5 minutos como máximo). Solo lee `corpus_dir` y escribe todo dentro de `out_dir`:

- **La biblioteca.** Un archivo por libro en {{layout}} (dentro de `out_dir`).
  - `<año>` es {{year_basis}}, con cuatro cifras. Si un libro da un solo año, ese año es a la vez el de la primera publicación y el de esta edición.
  - `<título>` y `<autor>` se escriben en {{script}}.
  - Libros con varios autores: `<autor>` es {{multi_author}}.
  - Reglas de nombre para `<título>` y `<autor>`: aplicar la normalización Unicode NFKC (las letras de ancho completo pasan a ser normales y los acentos se componen); cada `\ / : * ? " < > |` y cada carácter de control se convierte en un espacio; cada tramo de espacios en blanco se convierte en {{sep}}; se conservan los primeros **{{max_len}} caracteres**; y se quitan espacios, puntos y separadores en ambos extremos. La carpeta o el prefijo `<año>` son solo las cuatro cifras.
  - El archivo contiene **solo la sinopsis** del libro (sin líneas de título, autor ni año), en UTF-8, con los párrafos separados por una línea en blanco y terminado en salto de línea. No se juzgan los cortes de línea ni los espacios dentro de un párrafo.
- **`manifest.csv`** con la cabecera `source,status,path,reason`: una fila por libro; `source` = las rutas relativas al corpus de los archivos de los que se leyó el libro, separadas por `;`; `status` = `placed` (con `path` = su ruta en la biblioteca, p. ej. `library/...`) o `review` (con un código de motivo, abajo). Los archivos que no son libros pueden figurar como `skipped`.
- **`_review/`**: para cada libro enviado a revisión, copiar sus archivos de origen en algún lugar bajo `_review/` para que nuestro equipo los vea. Los códigos de motivo son `UNREADABLE`, `NO_TITLE`, `NO_AUTHOR`, `NO_YEAR`, `NO_DESCRIPTION`, `CONFLICT`; si se aplican varios, el primero de esta lista.

## Notas sobre los datos

- Los datos de un libro pueden estar repartidos en uno a tres archivos de formatos distintos: JSON, exportaciones ONIX XML del departamento de derechos, EPUB, DOCX, PDF, HTML, Markdown con un bloque de metadatos inicial (front matter) y texto plano.
- De dónde sale cada dato, por rango: los **metadatos incrustados** (campos JSON, ONIX, el archivo de paquete del EPUB, las propiedades del documento DOCX, la información del documento PDF, `<title>`/`<meta>` del HTML, el bloque inicial del Markdown, las filas de catálogo) mandan sobre el **texto de la portadilla** (las primeras líneas del cuerpo de un texto, PDF, DOCX, HTML o Markdown: título, título romanizado entre paréntesis, línea de autor, línea de edición), que manda sobre el **nombre del archivo**. Un dato que falta en un rango se toma del siguiente.
- Años: el JSON tiene `first_published` y `edition_year`; en ONIX, `PublishingDateRole` 01 es esta edición y 11 la primera publicación (01 solo: el único año); en EPUB, `dc:date` es esta edición y `first-published` la primera publicación; las portadillas dicen, por ejemplo, `Primera edición: 2009 · Esta edición: 2019`, `First published 2009 · This edition 2019`, o lo mismo con `初版` / `本版` / `新版` / `초판` / `개정판`. Las fechas de creación y modificación de los documentos (DOCX, PDF, EPUB) son fechas de archivo, nunca años de publicación.
- Nombres: los libros en chino, coreano y japonés dan el título y los autores en su escritura y en forma romanizada, emparejados en los metadatos (`title_latin`, `name_latin`, `author_latin`, `textscript="Latn"` de ONIX, `alternate-script` de EPUB) y en las portadillas (título romanizado entre paréntesis, `Nombre（Romanizado）`). Esa romanización emparejada es la forma latina oficial del autor y del título. Los nombres en inglés y en español se escriben con el nombre de pila primero.
<!-- tier: easy -->
- En esta ronda solo revisamos los libros bien formados: un archivo cada uno, UTF-8, metadatos completos, años normales de cuatro cifras. Los demás archivos de la unidad (codificaciones antiguas, copias en varios formatos, material dañado o incompleto, archivos comprimidos, catálogos, escaneos) todavía no se revisan, pero el programa no debe detenerse por ellos.
<!-- /tier -->
<!-- tier: medium hard -->
- Codificaciones: casi todo está en UTF-8, pero las exportaciones de los sistemas antiguos están en GB18030 (chino), CP949 (coreano), Shift_JIS (japonés) o CP1252 (inglés, español), sin ninguna marca; los HTML declaran la suya en `<meta charset>`.
- Notaciones de año: además de `2019` y `2019年` / `2019년` aparecen eras japonesas (`令和元年` = 2019, `平成21年` = 2009, `昭和50年` = 1975), el calendario Minguo (`民國98年` = 2009), el calendario Dangi coreano (`단기 4342년` = 2009), numerales chinos (`二〇〇九年` = 2009) y números romanos (`MMIX` = 2009). Todas significan años normales de cuatro cifras.
- Los títulos pueden venir en ancho completo o con los acentos descompuestos, y pueden contener caracteres que un nombre de archivo no admite (`:`, `?`, `？`); las reglas de nombre de arriba resuelven ambas cosas.
- Autores: la misma persona aparece con varias romanizaciones (`Kim Min-jun`, `Min-jun Kim`, `KIM Minjun`; `Sato Haruka`, `Haruka Sato`) y los nombres en inglés o español como `Apellido, Nombre`. Escriba siempre la forma oficial del autor (ver Nombres). Si los archivos de un libro solo tienen una romanización no oficial, los demás libros del mismo autor en la unidad dan la pareja oficial.
- Copias: el mismo libro (mismo título una vez normalizado) suele estar en varios archivos y carpetas. Le corresponde un solo archivo en la biblioteca; su fila del manifiesto enumera todos sus archivos.
- Los desacuerdos entre rangos se resuelven por el rango (p. ej., una portadilla cuyo año de edición no coincide con los metadatos pierde).
<!-- /tier -->
<!-- tier: medium -->
- En esta ronda revisamos todos los libros legibles. Las excepciones (datos que faltan, escaneos, archivos comprimidos, catálogos, archivos basura) todavía no puntúan, pero nada que no sea un libro debe acabar en la biblioteca, y el programa no debe detenerse por ellas.
<!-- /tier -->
<!-- tier: hard -->
- Excepciones y cómo tratarlas:
  - Un dato que falta en un archivo de un libro pero está en otro se toma del otro (de cualquier rango). Una sinopsis vacía en un archivo no es una sinopsis.
  - Sin título en ninguna parte: `NO_TITLE`. Un nombre de archivo con sentido cuenta como título (los guiones bajos son espacios); los nombres genéricos como `doc_0042`, `scan_0007`, `book_0031` o un ISBN no.
  - Sin autor en ninguna parte: ver más abajo nuestra política para los libros sin autor.
  - Sin año en ninguna parte: una línea de copyright en la portadilla (`© 2014 ...`) da el año (de la primera publicación y de esta edición); si no, `NO_YEAR`.
  - Sin sinopsis en ninguna parte: `NO_DESCRIPTION`. Nunca escriba una sinopsis inventada ni un texto de relleno.
  - Dos fuentes del mismo rango que no coinciden en un año (p. ej., un registro JSON y uno ONIX del mismo libro): `CONFLICT`.
  - Los escaneos son PDF de solo imagen en `scans/`, sin texto. Un escaneo llamado `<título> (scan).pdf` es copia de un libro que también tiene un archivo legible: ignórelo. Un escaneo que es el único material del libro: `UNREADABLE`.
  - Los archivos zip contienen más archivos nuestros: trate su contenido como el resto de la unidad (`source` = `archive.zip!ruta/interior`).
  - Los CSV de catálogo de `catalogs/` tienen un libro por fila (cabeceras en inglés o en japonés; varios autores separados por `;`); `source` = `archivo.csv#<fila>`, contando las filas desde 1 después de la cabecera.
  - La basura no es un libro y no genera archivo en la biblioteca: `.DS_Store`, `Thumbs.db`, `desktop.ini`, archivos de bloqueo de Office `~$...`, entradas `__MACOSX/._...`, archivos vacíos.
<!-- when: no_author=review -->
- Política: **un libro sin autor va a revisión** (`NO_AUTHOR`); nuestro catálogo no coloca libros anónimos. Es nuestra política de catalogación, no un contrato; se puede aprobar una excepción, y entonces esos libros se colocan con el nombre de autor "{{fallback_author}}".
<!-- /when -->
<!-- when: no_author=Unknown,Anonymous -->
- Política: **un libro sin autor se coloca con el nombre de autor "{{fallback_author}}"**, escrito así en cualquier escritura, y en lo demás se archiva como cualquier otro libro. No va a revisión: nuestro equipo de catálogo lo acordó para esta limpieza, así que en esta unidad no se usa `NO_AUTHOR`.
<!-- /when -->
<!-- /tier -->

## Cómo se juzga el resultado

Ejecutamos el programa sobre la unidad completa y comparamos la biblioteca con nuestro propio catálogo.

<!-- tier: easy -->
- Solo cuentan los libros bien formados.
<!-- /tier -->
<!-- tier: medium -->
- Cuentan todos los libros legibles; las excepciones no.
<!-- /tier -->
<!-- tier: hard -->
- Cuentan todos los libros.
<!-- /tier -->
- Un libro archivado exactamente en la ruta correcta con su sinopsis suma 1. Un archivo de la biblioteca con la sinopsis correcta en una ruta equivocada suma 0,4 más 0,2 por cada acierto entre año, título y autor; la ruta correcta con una sinopsis equivocada suma 0,2.
- Un libro que debe ir a revisión suma 1 cuando todas las filas del manifiesto que nombran sus archivos dicen `review` con el código de motivo correcto, 0,4 cuando coinciden en otro código, y nada cuando las filas se contradicen o el libro tiene además un archivo en la biblioteca.
- También se revisa la fila de cada libro en el manifiesto: debe ser la única fila que nombra los archivos del libro, listarlos todos y decir `placed` con la ruta del libro en la biblioteca, o `review` con los archivos copiados bajo `_review/`. Una fila que falta o está mal cuesta una quinta parte del crédito del libro.
<!-- tier: hard -->
<!-- when: no_author=review -->
- Un libro sin autor que espera en revisión suma 0,7 (no está en la estantería); colocado como "{{fallback_author}}" con la sinopsis correcta sumaría 1, pero solo con una excepción aprobada.
<!-- /when -->
<!-- when: no_author=Unknown,Anonymous -->
- Un libro sin autor se juzga como cualquier otro, con "{{fallback_author}}" como autor; enviado a revisión no suma nada.
<!-- /when -->
<!-- /tier -->
<!-- tier: medium hard -->
- Cada archivo de la biblioteca que no sea uno de nuestros libros resta 0,5.
<!-- /tier -->
- Calidad = 100 × crédito total / número de libros que cuentan. Cuanto más alta, mejor.

**Restricciones obligatorias** (si se incumple una, el resultado no vale):

- Todos los archivos de la biblioteca y `manifest.csv` son UTF-8 válido; ningún nombre de archivo o carpeta contiene `\ / : * ? " < > |` ni caracteres de control, es `.` o `..`, termina en espacio o punto, ni supera los 255 bytes.
- Un solo archivo de biblioteca por libro.
- Cada fila `review` lleva uno de los seis códigos de motivo.
<!-- tier: hard -->
- Ningún archivo de biblioteca para un libro sin sinopsis, y cada archivo de biblioteca contiene una sinopsis tomada de nuestros archivos (nada vacío, inventado ni de relleno).
<!-- when: no_author=review -->
- Los libros sin autor van a revisión (nuestra política; cabe una excepción).
<!-- /when -->
<!-- /tier -->
