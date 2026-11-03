# A clean library from our shared drive

## Background

Our shared drive holds the material of about a hundred of our books, in Chinese, English, Korean, Japanese and Spanish, and nobody has kept it in order: titles, authors, years and blurbs are scattered over all kinds of files from the regional offices, the scanning team and the rights desk. A sample of the drive is attached (`corpus/`). We need a program we can run on the full drive that builds a clean library from it, plus a manifest; anything it cannot file is set aside for our team, not guessed.

## Deliverable

A folder `program/` with `organize.py` defining `organize(task)`, where `task = {"corpus_dir": ..., "out_dir": ...}`. We run it once, offline, on the full drive (same structure and mix of files as the sample, about 100 books, Python standard library only, at most 5 minutes). It only reads `corpus_dir` and writes everything inside `out_dir`:

- **The library.** One file per book at `library/<year>/<title>/<author>.txt` (inside `out_dir`).
  - `<year>` is the year of first publication, four digits. When a book gives only one year, that year is both its first publication and this edition.
  - `<title>` and `<author>` are written in the Latin script (Chinese, Korean and Japanese books use the romanized form given in their metadata).
  - Co-authored books: `<author>` is only the first author.
  - Name rules for `<title>` and `<author>`: apply Unicode NFKC normalization (full-width letters become ordinary ones, accents are composed); every `\ / : * ? " < > |` and every control character becomes a space; each run of whitespace becomes a hyphen `-`; keep the first **48 characters**; then remove spaces, dots and separators at both ends. The `<year>` folder or prefix is just the four digits.
  - The file holds the book's **description only** (the blurb: no title, author or year lines), UTF-8, paragraphs separated by one blank line, ending with a newline. Line wrapping and spacing inside a paragraph are not judged.
- **`manifest.csv`** with the header `source,status,path,reason`: one row per book, `source` = the corpus-relative path(s) of the files the book was read from, separated by `;`; `status` = `placed` (with `path` = its library path, e.g. `library/...`) or `review` (with a reason code, below). Files that are not books may be listed as `skipped`.
- **`_review/`**: for every book sent to review, copy its source files somewhere under `_review/` so our team can look at them. The reason codes are `UNREADABLE`, `NO_TITLE`, `NO_AUTHOR`, `NO_YEAR`, `NO_DESCRIPTION`, `CONFLICT`; if several apply, the first in this list.

## Data notes

- A book's facts can be spread over one to three files of different formats: JSON, ONIX XML exports from the rights desk, EPUB, DOCX, PDF, HTML, Markdown with a front-matter block, plain text.
- Where the facts come from, by rank: **embedded metadata** (JSON fields, ONIX, the EPUB package file, DOCX document properties, the PDF document info, HTML `<title>`/`<meta>`, Markdown front matter, catalog rows) beats the **title page text** (the first lines of a text, PDF, DOCX, HTML or Markdown body: title, romanized title in parentheses, author line, edition line), which beats the **file name**. A field missing at one rank is taken from the next.
- Years: JSON has `first_published` and `edition_year`; ONIX `PublishingDateRole` 01 is this edition and 11 the first publication (01 alone: the only year); EPUB `dc:date` is this edition and `first-published` the first publication; title pages say e.g. `First published 2009 · This edition 2019`, `Primera edición: 2009 · Esta edición: 2019`, or the same with `初版` / `本版` / `新版` / `초판` / `개정판`. Document creation and modification dates (DOCX, PDF, EPUB) are file dates, never publication years.
- Names: Chinese, Korean and Japanese books give the title and the authors in their own script and in a romanized form, paired in the metadata (`title_latin`, `name_latin`, `author_latin`, ONIX `textscript="Latn"`, EPUB `alternate-script`) and on title pages (romanized title in parentheses, `Name（Romanized）`). That paired romanization is the author's and the title's official Latin form. English and Spanish names are written given name first.
- This round we only check the well-formed books: one file each, UTF-8, complete metadata, plain four-digit years. Other files in the drive (old encodings, copies in several formats, damaged or incomplete material, archives, catalogs, scans) are not checked yet, but the program must not stop on them.

## How the result is judged

We run the program on the full drive and compare the library with our own catalogue.

- Only the well-formed books are counted.
- A book filed at exactly the right path with its description earns 1. A library file with the right description at a wrong path is misfiled and earns 0.4 (our team has to find it and move it by hand); the right path with a wrong description earns 0.2.
- A book that belongs in review earns 1 when every manifest row naming its files says `review` with the right reason code, 0.4 when they agree on another code, and nothing when the rows disagree or the book also has a library file.
- Each book's manifest row is checked too: it must be the only row naming the book's files, list all of them, and say `placed` with the book's library path, or `review` with the files copied under `_review/`. A missing or wrong row costs a fifth of the book's credit.
- Quality = 100 × total credit / number of books counted. Higher is better.

**Hard constraints** (if one is broken, the result does not count):

- Every library file and `manifest.csv` is valid UTF-8; no file or folder name contains `\ / : * ? " < > |` or a control character, is `.` or `..`, ends in a space or a dot, or is longer than 255 bytes.
- One library file per book.
- Every `review` row carries one of the six reason codes.
- `manifest.csv` is the index of the library: every library file is the `path` of exactly one `placed` row, every `placed` row's `path` is a library file and its `source` names the files of the drive the book was read from, and no source (a file, an archive member or a catalog row) is named in two rows.
- Every file of the drive named in a `review` row is copied under `_review/` (archive members and catalog rows need not be).
