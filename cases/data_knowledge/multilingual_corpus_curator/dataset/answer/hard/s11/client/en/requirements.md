# A clean library from our shared drive

## Background

Our shared drive holds the material of about a hundred of our books, in Chinese, English, Korean, Japanese and Spanish, and nobody has kept it in order: titles, authors, years and blurbs are scattered over all kinds of files from the regional offices, the scanning team and the rights desk. A sample of the drive is attached (`corpus/`). We need a program we can run on the full drive that builds a clean library from it, plus a manifest; anything it cannot file is set aside for our team, not guessed.

## Deliverable

A folder `program/` with `organize.py` defining `organize(task)`, where `task = {"corpus_dir": ..., "out_dir": ...}`. We run it once, offline, on the full drive (same structure and mix of files as the sample, about 100 books, Python standard library only, at most 5 minutes). It only reads `corpus_dir` and writes everything inside `out_dir`:

- **The library.** One file per book at `library/<author>/<year>_<title>.txt` (inside `out_dir`).
  - `<year>` is the year of first publication, four digits. When a book gives only one year, that year is both its first publication and this edition.
  - `<title>` and `<author>` are written in the Latin script (Chinese, Korean and Japanese books use the romanized form given in their metadata).
  - Co-authored books: `<author>` is all authors in their order, joined with `" & "`.
  - Name rules for `<title>` and `<author>`: apply Unicode NFKC normalization (full-width letters become ordinary ones, accents are composed); every `\ / : * ? " < > |` and every control character becomes a space; each run of whitespace becomes a single plain space (spaces are kept); keep the first **24 characters**; then remove spaces, dots and separators at both ends. The `<year>` folder or prefix is just the four digits.
  - The file holds the book's **description only** (the blurb: no title, author or year lines), UTF-8, paragraphs separated by one blank line, ending with a newline. Line wrapping and spacing inside a paragraph are not judged.
- **`manifest.csv`** with the header `source,status,path,reason`: one row per book, `source` = the corpus-relative path(s) of the files the book was read from, separated by `;`; `status` = `placed` (with `path` = its library path, e.g. `library/...`) or `review` (with a reason code, below). Files that are not books may be listed as `skipped`.
- **`_review/`**: for every book sent to review, copy its source files somewhere under `_review/` so our team can look at them. The reason codes are `UNREADABLE`, `NO_TITLE`, `NO_AUTHOR`, `NO_YEAR`, `NO_DESCRIPTION`, `CONFLICT`; if several apply, the first in this list.

## Data notes

- A book's facts can be spread over one to three files of different formats: JSON, ONIX XML exports from the rights desk, EPUB, DOCX, PDF, HTML, Markdown with a front-matter block, plain text.
- Where the facts come from, by rank: **embedded metadata** (JSON fields, ONIX, the EPUB package file, DOCX document properties, the PDF document info, HTML `<title>`/`<meta>`, Markdown front matter, catalog rows) beats the **title page text** (the first lines of a text, PDF, DOCX, HTML or Markdown body: title, romanized title in parentheses, author line, edition line), which beats the **file name**. A field missing at one rank is taken from the next.
- Years: JSON has `first_published` and `edition_year`; ONIX `PublishingDateRole` 01 is this edition and 11 the first publication (01 alone: the only year); EPUB `dc:date` is this edition and `first-published` the first publication; title pages say e.g. `First published 2009 · This edition 2019`, `Primera edición: 2009 · Esta edición: 2019`, or the same with `初版` / `本版` / `新版` / `초판` / `개정판`. Document creation and modification dates (DOCX, PDF, EPUB) are file dates, never publication years.
- Names: Chinese, Korean and Japanese books give the title and the authors in their own script and in a romanized form, paired in the metadata (`title_latin`, `name_latin`, `author_latin`, ONIX `textscript="Latn"`, EPUB `alternate-script`) and on title pages (romanized title in parentheses, `Name（Romanized）`). That paired romanization is the author's and the title's official Latin form. English and Spanish names are written given name first.
- Encodings: most files are UTF-8, but old office exports are in GB18030 (Chinese), CP949 (Korean), Shift_JIS (Japanese) or CP1252 (English, Spanish), without a marker; HTML files declare theirs in `<meta charset>`.
- Year notations: besides `2019` and `2019年` / `2019년` you will find Japanese eras (`令和元年` = 2019, `平成21年` = 2009, `昭和50年` = 1975), the Minguo calendar (`民國98年` = 2009), the Korean Dangi calendar (`단기 4342년` = 2009), Chinese numerals (`二〇〇九年` = 2009) and Roman numerals (`MMIX` = 2009). All mean ordinary four-digit years.
- Titles may come full-width or with decomposed accents and may contain characters a file name cannot hold (`:`, `?`, `？`); the name rules above take care of both.
- Authors: the same person appears under several romanizations (`Kim Min-jun`, `Min-jun Kim`, `KIM Minjun`; `Sato Haruka`, `Haruka Sato`) and English or Spanish names as `Family, Given`. Always write the author's official form (see Names). When a book's own files only have an unofficial romanization, the same author's other books in the drive give the official pair.
- Copies: the same book (same title once normalized) often sits in several files and folders. It gets one library file; its manifest row lists all its files.
- Conflicts between ranks are settled by the ranking (e.g. a title page whose edition year disagrees with the metadata loses).
- Exceptions, and how to handle them:
  - A field missing in one file of a book but present in another is taken from the other one (any rank). An empty description in one file is not a description.
  - No title anywhere: `NO_TITLE`. A meaningful file name counts as a title (underscores stand for spaces); generic names such as `doc_0042`, `scan_0007`, `book_0031` or an ISBN do not.
  - No author anywhere: see our policy for books without an author, below.
  - No year anywhere: a copyright line on the title page (`© 2014 ...`) gives the year (both first publication and this edition); otherwise `NO_YEAR`.
  - No description anywhere: `NO_DESCRIPTION`. Never write a made-up or placeholder description.
  - Two sources of the same rank that disagree on a year (e.g. a JSON record and an ONIX record of one book): `CONFLICT`.
  - Scans are image-only PDFs in `scans/` with no text. A scan named `<title> (scan).pdf` is a copy of a book that also has a readable file: ignore the scan. A scan that is the book's only material: `UNREADABLE`.
  - Zip archives hold more of our files: treat their contents like the rest of the drive (`source` = `archive.zip!path/inside`).
  - Catalog CSVs in `catalogs/` have one book per row (headers in English or Japanese; several authors separated by `;`); `source` = `file.csv#<row>`, rows counted from 1 after the header.
  - Junk is not a book and gets no library file: `.DS_Store`, `Thumbs.db`, `desktop.ini`, Office lock files `~$...`, `__MACOSX/._...` entries, empty files.
- Policy: **a book with no author is shelved under the author name "Unknown"**, spelled exactly like that whatever the script, and is otherwise filed like any other book. It does not go to review: our catalogue team agreed to this for the clean-up, so `NO_AUTHOR` is not used on this drive.

## How the result is judged

We run the program on the full drive and compare the library with our own catalogue.

- Every book is counted.
- A book filed at exactly the right path with its description earns 1. A library file with the right description at a wrong path is misfiled and earns 0.4 (our team has to find it and move it by hand); the right path with a wrong description earns 0.2.
- A book that belongs in review earns 1 when every manifest row naming its files says `review` with the right reason code, 0.4 when they agree on another code, and nothing when the rows disagree or the book also has a library file.
- Each book's manifest row is checked too: it must be the only row naming the book's files, list all of them, and say `placed` with the book's library path, or `review` with the files copied under `_review/`. A missing or wrong row costs a fifth of the book's credit.
- A book with no author is judged like any other book, with "Unknown" as its author; sent to review it earns nothing.
- Every library file that is not one of our books costs 0.5.
- Quality = 100 × total credit / number of books counted. Higher is better.

**Hard constraints** (if one is broken, the result does not count):

- Every library file and `manifest.csv` is valid UTF-8; no file or folder name contains `\ / : * ? " < > |` or a control character, is `.` or `..`, ends in a space or a dot, or is longer than 255 bytes.
- One library file per book.
- Every `review` row carries one of the six reason codes.
- `manifest.csv` is the index of the library: every library file is the `path` of exactly one `placed` row, every `placed` row's `path` is a library file and its `source` names the files of the drive the book was read from, and no source (a file, an archive member or a catalog row) is named in two rows.
- Every file of the drive named in a `review` row is copied under `_review/` (archive members and catalog rows need not be).
- No library file for a book without a description, and every library file holds a description taken from our files (nothing empty, made up or placeholder).
- No book is placed under a title or a year that its files do not settle: no title other than a generic file name, no year anywhere (file dates are not publication years), or two sources of the same rank that disagree on the year.
- Books without an author are shelved under "Unknown" (our policy for this clean-up).
