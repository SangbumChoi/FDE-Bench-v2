# Multilingual Corpus Curator — `data_knowledge/multilingual_corpus_curator`

A small publisher keeps the material of about a hundred books (Chinese, English, Korean, Japanese, Spanish) on
one messy shared drive: each book's title, authors, publication years and description are spread over one to
three files of mixed formats, next to scans, archives, catalog exports and junk. The agent delivers a
**program**, `program/organize.py` with `organize(task)`, `task = {"corpus_dir": "$INPUT_DIR", "out_dir":
"$OUTPUT_DIR"}`, that builds a normalized library:

```
out_dir/library/<layout of the rule set>.txt   one UTF-8 file per book: the book's description only
out_dir/_review/...                            source files of books that cannot be placed
out_dir/manifest.csv                           source,status,path,reason (placed | review | skipped)
```

The agent sees a visible sample (`data/corpus/`, 100 books, ~120 files) and the program is scored on a
**hidden corpus** built by the same recipe with another seed (same size and mix), identical in all nine
settings. Everything is synthetic: titles, names and blurbs are generated from invented vocabularies written
natively in each language. Only the standard library is needed to read every format.

## Settings: one corpus, nine ground truths

The world, the visible corpus, the hidden corpus and the request are the same in every setting (the
validator checks the agent's view is byte-identical). The tier decides which books are scored and which
rules apply; the rule set decides how the correct library looks.

### Tiers (same corpus; scope and strictness differ)

| | easy | medium | hard |
|---|---|---|---|
| **Books scored** (hidden corpus) | 30 well-formed books: one file, UTF-8, complete metadata, plain 4-digit years | 66: + every readable book | 100: + the exceptions |
| **What is added** | Formats, the layout, name rules, description extraction, the year basis, romanized pairs | Legacy encodings (GB18030, CP949, Shift_JIS, CP1252); `令和元年`, `民國98年`, `단기 4342년`, `二〇〇九年`, `MMIX`; full-width and decomposed titles; forbidden path characters; one author under several romanizations (official pair only in the author's other books); copies across formats and folders to merge; source precedence (embedded metadata > title page > file name) | Missing author/title/description recovered from another file; title from a meaningful file name; year from a `©` line; `NO_AUTHOR` / `NO_TITLE` / `NO_YEAR` / `NO_DESCRIPTION` / `CONFLICT` (same-rank year disagreement) / `UNREADABLE` (image-only scan) review with reason code; scans that duplicate a readable file; junk (`.DS_Store`, `Thumbs.db`, `desktop.ini`, `~$` lock files, `__MACOSX/._*`, empty files); books inside zip archives; multi-book catalog CSVs (English and Japanese headers) |
| **Rules** | `utf8_output`, `safe_names` (physical); `one_file_per_book`, `review_reason` (contractual) | same | + `no_fabrication` (contractual); `missing_author_review` (business policy, bendable) |
| **Scoring extras** | out-of-scope books are ignored | −0.5 per library file that is no book | + a book without an author waiting in review earns 0.7 (shelving it under the fallback name earns 1 but needs an approved exception) |

### Rule sets (hyperparameters of the client's library rules)

| Parameter | A | B | C |
|---|---|---|---|
| Layout | `library/<year>/<title>/<author>.txt` | `library/<year>/<author>/<title>.txt` | `library/<author>/<year>_<title>.txt` |
| Year basis | first publication | this edition | first publication |
| Script of titles and names | original | original | Latin (the romanization paired in the metadata) |
| Co-authors | first author only | all, joined with `" & "` | first author only |
| Separator for spaces | `_` | `-` | a plain space |
| Max length of a title/author part | 60 | 40 | 80 |
| Fallback author (only with an approved exception) | `Unknown` | `Anonymous` | `Unknown Author` |

Name rules in every rule set: NFKC; each `\ / : * ? " < > |` or control character becomes a space; whitespace
runs become the separator; cut to the max length; strip spaces, dots and separators at both ends.

Within each tier every rule set's reference is clearly wrong under the other rule sets (quality of the row's
reference evaluated under the column's rule set; all valid, so the difference is in the paths):

| reference → scored under | easy | medium | hard |
|---|---|---|---|
| A under B / B under A | 0.507 | 0.520 | 0.575 |
| A or B under C / C under A or B | 0.400 | 0.405 | 0.470 |

## File formats and the exception catalog

| Kind | Where the facts are |
|---|---|
| JSON | `title`, `title_latin`, `authors[{name, name_latin}]`, `first_published`, `edition_year`, `description` (years may be era strings in medium) |
| ONIX-like XML (namespace `ns.editeur.org/onix/3.0`) | `TitleText` (+ `textscript="Latn"`), `Contributor/PersonName` + `AlternativeName` or `PersonNameInverted`, `PublishingDateRole` 01 = this edition, 11 = first publication, `TextContent/Text` |
| EPUB (zip + OPF) | `dc:title`, `dc:creator` with `alternate-script` / `file-as` refinements, `dc:date` (this edition), `first-published` meta, `dc:description`; `dcterms:modified` is a trap |
| DOCX (zip + XML) | `docProps/core.xml` title and creator (`dcterms:created` is a trap); body paragraphs split into several runs = title page + description |
| PDF (uncompressed text streams) | Info `/Title`, `/Author` (UTF-16 hex strings; `/CreationDate` is a trap); page text as UTF-16 `Tj` strings, wrapped lines |
| Scan PDF | image-only page, no text and no title: unreadable |
| HTML | `<title>`, `<meta name="author">`; body `h1`, `p.latin`, `p.byline`, `p.edition`, `h2`, description paragraphs; `<meta charset>` (Shift_JIS / CP949 in medium) |
| Markdown | front matter (`title`, `title_latin`, `author`, `author_latin`, `first_published`, `edition`) + body title page |
| Plain text | title page (title, `(romanized title)`, `Name（Romanized） 著` / `지음` / `by` / `por`, edition line, optional `©` line), heading (`内容简介`, `内容紹介`, `책 소개`, `About this book`, `Sinopsis`), description (sometimes hard-wrapped, CRLF, or in a legacy encoding) |
| Catalog CSV | one book per row; English or Japanese headers; `source` = `file.csv#row` |
| Zip archive | 2 books each plus an AppleDouble `__MACOSX/._*` entry; `source` = `archive.zip!inner/path` |

Composition of each corpus (fixed counts, languages partly random): 30 easy; medium 7 encodings, 6 year
notations, 4 full-width/decomposed titles, 5 forbidden characters, 5 romanization variants, 6 multi-file copies,
3 precedence conflicts; hard 3 author recoveries, 2 no author, 2 titles from file names, 2 no title, 2
description recoveries, 2 no description, 3 copyright-line years, 2 no year, 2 same-rank conflicts, 2 scan-only,
2 scans with a readable copy, 4 books in zips, 6 catalog rows; plus 8 junk files.

## Scoring

Per scored book: **1** for the exact library path with the right description; otherwise a library file found
by its description earns 0.4 + 0.2 for each right component (year, title, author), and the right path with a
wrong description earns 0.6. A book that belongs in review earns 1 for a manifest `review` row naming one of its
files with the right reason code (0.4 with another code); a `NO_AUTHOR` book earns 0.7 in review. Medium and
hard subtract 0.5 per library file that is no book. Quality = 100 × credit / books scored, relative to the
reference (maximize). Descriptions are compared after NFKC with whitespace removed, so wrapping does not matter.
The program's output on the hidden corpus is cached by the program's digest, so the nine settings, the
violating examples and the cross-rule-set checks run each distinct program once (`validate-case` takes ~10 s).

## Reference and verified numbers (seed 20261027, hidden corpus)

The reference (`reference/organize.py` + `config.json` of the rule set) is a solid rule-based organizer:
every format, legacy encodings via the corpus's own UTF-8 character statistics, era years, NFKC slugs,
grouping by normalized title, per-field precedence, own-file name pairing, scans, junk and catalogs.
Deliberate gaps (headroom): no zip archives, no Roman-numeral or Chinese-numeral years, no copyright-line
years, no same-rank conflict detection, no corpus-wide author-name map, and it keeps the `NO_AUTHOR` policy.

| Setting | Books scored | Reference quality | Best possible (no bending) | Headroom | Naive organizer |
|---|---|---|---|---|---|
| easy/A | 30 | 100.00 | 100.00 | 0% | 81.33 |
| easy/B | 30 | 100.00 | 100.00 | 0% | 81.33 |
| easy/C | 30 | 100.00 | 100.00 | 0% | 83.33 |
| medium/A | 66 | 92.73 | 100.00 | +7.8% | 61.21 |
| medium/B | 66 | 92.73 | 100.00 | +7.8% | invalid (`one_file_per_book`); 61.21 if it merges identical titles |
| medium/C | 66 | 92.73 | 100.00 | +7.8% | 62.12 |
| hard/A | 100 | 85.60 | 99.40 (100 with the exception) | +16.1% (+16.8%) | invalid (`one_file_per_book`); 63.80 if it merges |
| hard/B | 100 | 85.60 | 99.40 (100) | +16.1% (+16.8%) | invalid; 63.80 if it merges |
| hard/C | 100 | 85.60 | 99.40 (100) | +16.1% (+16.8%) | invalid; 64.60 if it merges |

Per-tier means of the reference (A/B/C averaged): **easy 100.00, medium 92.73, hard 85.60**. On the visible
sample the reference scores 100.00 / 94.24 / 86.60. The naive organizer is the reference with UTF-8-only
decoding, digit-only years, no NFKC or length limit in names, and no merging of copies. Bending
`missing_author_review` (shelving the two author-less books under the fallback name) is valid when relaxed and
raises the hard quality to 1.007.

How often each rule-set parameter changes the answer (placed books in scope, hidden corpus):

| | easy | medium | hard |
|---|---|---|---|
| Year basis (first publication ≠ this edition) | 14 | 30 | 38 |
| Script (non-Latin titles and names) | 18 | 40 | 55 |
| Co-authors (books with 2 authors) | 6 | 13 | 14 |
| Separator (titles with spaces) | 18 | 40 | 52 |
| Length cut (A 60 / B 40 / C 80) | 3 / 3 / 0 | 7 / 7 / 2 | 9 / 9 / 3 |

What the reference loses on the hidden corpus: medium — 4 books with Roman or Chinese-numeral years go to review
as `NO_YEAR` and 4 author-variant books get an unofficial name (0.8 each); hard — additionally 4 books in zips,
3 copyright-line years, 2 same-rank conflicts placed instead of reviewed, and 2 × 0.3 for keeping the
`NO_AUTHOR` policy.

## Notes

- The visible corpus is byte-identical in every setting and locale (`content_dirs: [corpus]`); only the
  archivist's note outside the corpus is localized.
- `write only inside out_dir` and `never modify the corpus` are enforced by the runner (the program gets a copy
  of the corpus, read-only under docker), not scored.

## Stored dataset (`dataset/`)

Written by `python -m fdebench2.cli export-dataset cases/data_knowledge/multilingual_corpus_curator`;
`validate-case` regenerates it and fails if it drifts from the generator (~2 MB, ~2,900 small files).

```
dataset/
  visible/<lang>/corpus/...          the agent's sample drive (byte-identical in every locale) + the archivist's note
  hidden/corpus/...                  the hidden drive exactly as organize() receives it (same in all nine settings)
  gt/<tier>_<A|B|C>/
    setting.json, score.json         the setting and the reference's score on the hidden corpus
    reference/program/               the reference deliverable (organize.py + config.json of the rule set)
    reference_output/                what the reference writes on the hidden corpus (library/, _review/, manifest.csv)
    expected_hidden/                 the correct out_dir for the books scored in this setting, hidden corpus:
                                       library/... one description file per placed book, at the rule set's path
                                       _review/<REASON>/<path with / as __>  the source files of review books
                                       manifest.csv  placed / review rows (with reason) and, in hard, JUNK skips
    expected_visible/                the same for the visible sample
    books_hidden.csv, books_visible.csv   answer key: every book with kind, tier, scored, expected status,
                                       path and reason, canonical title/authors/years and its source files
    expected_score.json              expected_* scored by the evaluator: 100 in easy and medium, 99.4 in hard
                                       (the two NO_AUTHOR books earn 0.7 in review; no rule is bent)
```

The expected trees hold only the books the tier scores (30 / 66 / 100); books outside the tier are not part of
that setting's answer. No client e-mails or SQL exports were added: the drive already contains the client's
own catalog exports, and new side material would change what the case tests.
