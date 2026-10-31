# Multilingual Corpus Curator — `data_knowledge/multilingual_corpus_curator`

A small publisher keeps the material of about a hundred books (Chinese, English, Korean, Japanese, Spanish) on
one messy shared drive: each book's title, authors, publication years and description are spread over one to
three files of mixed formats, next to scans, archives, catalog exports and junk. The agent delivers a
**program**, `program/organize.py` with `organize(task)`, `task = {"corpus_dir": "$INPUT_DIR", "out_dir":
"$OUTPUT_DIR"}`, that builds a normalized library:

```
out_dir/library/<the drawn layout>.txt   one UTF-8 file per book: the book's description only
out_dir/_review/...                      source files of books that cannot be placed
out_dir/manifest.csv                     source,status,path,reason (placed | review | skipped)
```

The agent sees a visible sample (`data/corpus/`, 100 books, ~120 files) and the program is scored on a
**hidden corpus** built by the same recipe with another seed (same size and mix), identical in every setting.
Everything is synthetic: titles, names and blurbs are generated from invented vocabularies written natively in
each language. Only the standard library is needed to read every format.

## Settings: one corpus, tiers × rule seeds

A setting is a tier and a rule seed. The world, the visible corpus, the hidden corpus and the request are the
same in every setting (the validator checks that the agent's view is byte-identical). The tier decides which
books are scored, which rules apply and which candidate pools the rule seed draws from; the rule seed draws the
client's library rules, each parameter on its own, so the correct library differs from seed to seed. The public
panel is rule seeds **11, 18 and 21** (nine settings, stored in `dataset/gt/` and checked by the validator); any
other seed is a private draw whose answers are published nowhere.

### Tiers (same corpus; scope, strictness and pools differ)

| | easy | medium | hard |
|---|---|---|---|
| **Books scored** (hidden corpus) | 30 well-formed books: one file, UTF-8, complete metadata, plain 4-digit years | 66: + every readable book | 100: + the exceptions |
| **What is added** | Formats, the layout, name rules, description extraction, the year basis, romanized pairs | Legacy encodings (GB18030, CP949, Shift_JIS, CP1252); `令和元年`, `民國98年`, `단기 4342년`, `二〇〇九年`, `MMIX`; full-width and decomposed titles; forbidden path characters; one author under several romanizations (official pair only in the author's other books); copies across formats and folders to merge; source precedence (embedded metadata > title page > file name) | Missing author/title/description recovered from another file; title from a meaningful file name; year from a `©` line; `NO_TITLE` / `NO_YEAR` / `NO_DESCRIPTION` / `CONFLICT` (same-rank year disagreement) / `UNREADABLE` (image-only scan) review with reason code; the client's policy for books with no author (`NO_AUTHOR` review, or shelved under a fallback name); scans that duplicate a readable file; junk (`.DS_Store`, `Thumbs.db`, `desktop.ini`, `~$` lock files, `__MACOSX/._*`, empty files); books inside zip archives; multi-book catalog CSVs (English and Japanese headers) |
| **Name-length pool** (`max_len`) | 60, 48, 40: only the long subtitled titles are cut | 50, 40, 32: + a few longer titles and co-author lists at 32 | 40, 32, 24: + mid-length titles and co-author lists |
| **No-author policy** (`no_author`) | not drawn (the books are out of scope) | not drawn | review, or shelved under "Unknown" or "Anonymous" |
| **Rules** | `utf8_output`, `safe_names` (physical); `one_file_per_book`, `review_reason` (contractual) | same | + `no_fabrication` (contractual); `missing_author_review` (business policy, bendable) only under the review policy |
| **Scoring extras** | out-of-scope books are ignored | −0.5 per library file that is no book | review policy: a book without an author waiting in review earns 0.7 (shelving it under the fallback name earns 1 but needs an approved exception); shelving policy: such a book is scored like any other placed book and earns nothing in review; a library file whose text is in none of the sources breaks `no_fabrication` |
| **What the requirements put out of scope** | "Other files in the drive (old encodings, copies in several formats, damaged or incomplete material, archives, catalogs, scans) are not checked yet, but the program must not stop on them" | "The exceptions (missing fields, scans, archives, catalogs, junk) are not scored yet, but anything that is not a book must not end up in the library" | nothing |

A rule seed draws the same position of a pool in every tier (the draw does not depend on the tier), but `max_len`
has a different pool per tier and `no_author` has candidates only in hard. So the same seed gives a tighter name
limit in each harder tier, and in hard it may change the no-author policy: the three tiers' references differ in
every public seed, and each one scores below the other tier's own reference under that tier (table below).

### Parameters

A rule seed s draws position `Random("data_knowledge/multilingual_corpus_curator|<name>|s").randrange(n)` of
each pool of n candidates, independently of the other parameters. The first five pools are the same in every
tier.

| Parameter | Pool | What it changes (hidden corpus, public world, placed books in scope easy / medium / hard) | Target |
|---|---|---|---|
| `layout` | `library/<year>/<title>/<author>.txt`, `library/<year>/<author>/<title>.txt`, `library/<author>/<year>_<title>.txt` | every placed book's path (30 / 66 / 88) | `layout` |
| `year_basis` | first publication, this edition (a book with one year uses it for both) | books whose two years differ (14 / 30 / 38) | `year_basis` |
| `script` | original, Latin (the romanization paired in the metadata) | Chinese, Korean and Japanese books (18 / 40 / 55) | `script` |
| `multi_author` | first author only, all joined with `" & "` | books with two authors (6 / 13 / 14) | `co_authors` |
| `sep` | `_`, `-`, a plain space | names with spaces (18 / 40 / 52 in the original script, every book in Latin) | `name_rules` |
| `max_len` | easy 60, 48, 40; medium 50, 40, 32; hard 40, 32, 24 | names longer than the limit: easy 3 at every value; medium 7, 7, 8–11; hard 9, 10–13, 13–21 (ranges over script and co-author rule) | `name_rules` |
| `no_author` | easy and medium `review`; hard `review`, `Unknown`, `Anonymous` | the 2 author-less books (hard): `review` sends them to `NO_AUTHOR` review (0.7 each) under the bendable `missing_author_review`; a name shelves them under that author name like any other book (1 each, 0 in review) | `missing_author` |

`derive_params` adds `fallback_author`, the name the texts quote: the drawn name under a shelving policy, and
"Unknown" (the name an approved exception would use) under the review policy. No combination is infeasible: on
the public world and world seeds 1–20 (visible and hidden corpora), no two placed books of any tier share a path
under any of the 216 combinations of easy and medium or the 648 of hard, so the case defines no `admissible`.

Name rules in every setting: NFKC; each `\ / : * ? " < > |` or control character becomes a space; whitespace
runs become the separator; cut to `max_len` characters; strip spaces, dots and separators at both ends. A
tighter limit reaches more names, so getting the order of these steps wrong costs more often: cutting a
decomposed Spanish title before NFKC keeps fewer letters, and a cut that lands on a separator leaves one to strip.

### Public panel

The panel shows every candidate of every pool: across seeds 11, 18 and 21 each three-candidate pool gives all
three of its values (in every tier) and each two-candidate pool both of its values. Seed 11 comes first because
validate-case checks binding from it, and its hard draw shelves the author-less books, so the policy check
compares a valid shelving reference with the review policy it breaks.

| Setting | `layout` | `year_basis` | `script` | `multi_author` | `sep` | `max_len` | `no_author` (→ `fallback_author`) | Reference | Baseline | Best possible |
|---|---|---|---|---|---|---|---|---|---|---|
| easy/s11 | author/year_title | first | latin | all | `" "` | 40 | review (Unknown) | 100.00 | 10.00 | 100.00 |
| easy/s18 | year/title/author | first | latin | first | `-` | 48 | review (Unknown) | 100.00 | 10.00 | 100.00 |
| easy/s21 | year/author/title | edition | original | first | `_` | 60 | review (Unknown) | 100.00 | 10.00 | 100.00 |
| medium/s11 | author/year_title | first | latin | all | `" "` | 32 | review (Unknown) | 92.73 | 13.33 | 100.00 |
| medium/s18 | year/title/author | first | latin | first | `-` | 40 | review (Unknown) | 92.73 | 13.33 | 100.00 |
| medium/s21 | year/author/title | edition | original | first | `_` | 50 | review (Unknown) | 92.73 | 13.33 | 100.00 |
| hard/s11 | author/year_title | first | latin | all | `" "` | 24 | Unknown | 86.20 | 10.80 | 100.00 |
| hard/s18 | year/title/author | first | latin | first | `-` | 32 | review (Unknown) | 85.60 | 10.80 | 99.40 (100 with the exception) |
| hard/s21 | year/author/title | edition | original | first | `_` | 40 | Anonymous | 86.20 | 10.80 | 100.00 |

Objectives on the hidden corpus at the public world seed (20261027); "best possible" is `expected_output` scored
by the evaluator. Private seeds draw any other combination, e.g. seed 101: `author/year_title`, first, original,
first, `-`, 60 / 50 / 40, review in every tier; seed 102: `year/author/title`, first, original, first, `_`,
40 / 32 / 24, `Unknown` in hard.

**Parameter binding** (validate-case, from hard/s11): every parameter changes the score of the reference with the
first other value it tries. At the public world the reference of hard/s11 scores 86.20, and with one parameter
changed: `layout` 39.60, `year_basis` → edition 79.60, `script` → original 67.80, `multi_author` → first 83.60,
`sep` → `_` 55.80, `max_len` → 40 81.60, `no_author` → review invalid (`missing_author_review`). Between the two
fallback names the reference loses only 0.4 (85.80: the two author-less books keep year and title), below the 1%
margin; `no_author` binds through the policy, not the name. In easy and medium the length pools bind too: the
reference of easy/s11 scores 98.00 under a 60-character limit, that of medium/s11 89.09 under 50. The same checks
pass on world seeds 1, 2 and 3.

**References across settings** (public world; each row is a setting, each cell another setting's reference scored
under it; `*` = invalid):

| Scored under | easy s11 / s18 / s21 | medium s11 / s18 / s21 | hard s11 / s18 / s21 |
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

Another seed's reference keeps its layout, so it is placed by description only (0.4 plus the right components).
The same seed's reference from another tier differs in the length limit and, in hard/s11 and hard/s21, in the
no-author policy: it loses 1.8–6.6 points, and the two shelving references are invalid under hard/s18's review
policy.

### What an agent must ask

Six targets carry the rule seed's draw and cannot be read from the data or carried over from another run:
`layout`, `year_basis`, `script`, `co_authors`, `name_rules` (separator and length limit) and, in hard,
`missing_author` (the no-author policy and the fallback name). The others (`content`, `manifest_review`,
`precedence`, `scoring`, and per tier `encodings`, `year_notations`, `author_variants`, `duplicates`,
`exceptions`, `containers`) are the same under every draw.

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
by its description earns 0.4 + 0.2 for each right component (year, title, author), and the right path holding
any other text earns 0.2. A book that belongs in review earns 1 when every manifest row naming one of its files
says `review` with the right reason code (0.4 when they agree on another code; under the review policy a
`NO_AUTHOR` book earns 0.7 in review); rows that disagree, or a library file for the book as well, earn nothing.
A book that belongs on the shelf earns nothing in review; under a shelving policy that includes the author-less
books, whose expected author is the drawn fallback name. Each book's manifest row is checked too (the only row
naming the book's files, all of them and nothing else; `placed` with the book's library path, or `review` with
its files copied byte for byte under `_review/`; a scan that copies a readable file may be in the row, listed as
skipped or left out): a missing or wrong row costs a fifth of the book's credit. Medium and hard subtract 0.5
per library file that is no book. Objective = 100 × credit / books scored (maximize); quality is normalized
between the baseline (0) and the reference (1). Descriptions are compared after NFKC with whitespace removed, so
wrapping does not matter. In hard, `no_fabrication` also fires on a non-empty library file that holds no whole
description paragraph of any book and is not a piece (20+ characters) of one: placeholders and invented blurbs;
a stray heading or a dropped paragraph only loses credit.

Two probes that the scoring answers (hidden corpus, public world): `expected_output` with its review rows
replaced by six `review` rows (one per reason code) for every corpus file scores 72.40 in hard/s18 and 74.00 in
hard/s11 and hard/s21 (80.00 in easy and medium), against 99.40 / 100.00 for the tree itself; the same expected
tree with every description replaced by `x` scores 20.00 in easy and medium and breaks `no_fabrication` in hard.

The program's output on the hidden corpus is cached by the program's digest, so the settings, the violating
examples and the binding and cross-tier checks run each distinct program once (`validate-case` takes about two
minutes with the default world seeds 1–3).

## Reference and verified numbers (seed 20261027, hidden corpus)

The baseline (`reference/baseline.py` + the same `config.json`) is what the client could script without an
engineer: it shelves only the books that have a complete UTF-8 JSON export (title, author, a plain four-digit
year and a description) under the catalogue rules, and leaves every other file for the team (no other format,
no legacy encodings or era years, no merging of copies, no review area). It is valid in every setting.

The reference (`reference/organize.py` + `config.json` of the setting) is a solid rule-based organizer:
every format, legacy encodings via the corpus's own UTF-8 character statistics, era years, NFKC slugs,
grouping by normalized title, per-field precedence, own-file name pairing, scans, junk and catalogs, and the
drawn no-author policy. Deliberate gaps (headroom): no zip archives, no Roman-numeral or Chinese-numeral years,
no copyright-line years, no same-rank conflict detection and no corpus-wide author-name map.

| Tier | Books scored | Baseline objective | Reference objective | Best possible (no bending) | Its normalized quality |
|---|---|---|---|---|---|
| easy (s11, s18, s21) | 30 | 10.00 | 100.00 | 100.00 | 1.00 |
| medium (s11, s18, s21) | 66 | 13.33 | 92.73 | 100.00 | 1.09 |
| hard, review policy (s18) | 100 | 10.80 | 85.60 | 99.40 (100 with the exception) | 1.18 (1.19) |
| hard, shelving policy (s11, s21) | 100 | 10.80 | 86.20 | 100.00 | 1.18 |

Within a tier the drawn library rules do not change these numbers at this world (each setting's paths are scored
under its own rules); only the no-author policy does, by 0.6. Per-tier means over the panel of the reference:
**easy 100.00, medium 92.73, hard 86.00**; of the baseline: easy 10.00, medium 13.33, hard 10.80
(baseline/reference 0.10 / 0.14 / 0.13). The baseline earns 3 / 10 / 12 exact placements; in medium and hard 6 of
them (copies and precedence pairs) lose a fifth because the book has other files and its manifest row lists only
the JSON, and in hard it shelves the 2 `CONFLICT` books, which earns nothing. On world seeds 1, 2 and 3 the
baseline scores 6.67–20.00 (easy), 8.18–13.33 (medium) and 5.40–8.80 (hard) against references of 100.00,
94.24–95.76 and 86.60–87.60 (review policy) or 87.20–88.20 (shelving policy). Under the review policy, bending
`missing_author_review` (shelving the two author-less books under "Unknown") is valid when relaxed and gives
86.20 in hard/s18 (normalized quality 1.008).

What the reference loses on the hidden corpus: medium — 4 books with Roman or Chinese-numeral years go to review
as `NO_YEAR` and 4 author-variant books get an unofficial name (0.8 each); hard — additionally 4 books in zips,
3 copyright-line years, 2 same-rank conflicts placed instead of reviewed, and under the review policy 2 × 0.3
for keeping the `NO_AUTHOR` policy.

## Notes

- The visible corpus is byte-identical in every setting and locale (`content_dirs: [corpus]`); only the
  archivist's note outside the corpus is localized.
- `write only inside out_dir` and `never modify the corpus` are enforced by the runner (the program gets a copy
  of the corpus, read-only under docker), not scored.

## Stored dataset (`dataset/`)

Written by `python -m fdebench2.cli export-dataset cases/data_knowledge/multilingual_corpus_curator`;
`validate-case` regenerates it and fails if it drifts from the generator (~2 MB, ~2,300 small files).

```
dataset/
  agent_view/<lang>/corpus/...       the agent's sample drive (byte-identical in every locale) + the archivist's note
  hidden/corpus/...                  the hidden drive exactly as organize() receives it (same in every setting)
  gt/<tier>_s<seed>/                 easy_s11 ... hard_s21, the public panel
    setting.json, score.json         the drawn parameters (+ derived fallback_author) and the reference's score on
                                       the hidden corpus (with the baseline's objective and both normalized qualities)
    reference/program/               the reference deliverable (organize.py + config.json of the setting)
    reference_output/                what the reference writes on the hidden corpus (library/, _review/, manifest.csv)
    expected_output/                 the correct out_dir for the books scored in this setting, hidden corpus:
                                       library/... one description file per placed book, at the setting's path
                                       _review/<REASON>/<path with / as __>  the source files of review books
                                       manifest.csv  placed / review rows (with reason) and, in hard, JUNK skips
    books.csv                        answer key (hidden corpus): every book with kind, tier, scored, expected status,
                                       path and reason, canonical title/authors/years and its source files
    expected_score.json              expected_output scored by the evaluator: 100 in easy and medium; in hard 99.4
                                       under the review policy (the two NO_AUTHOR books earn 0.7 in review; no rule
                                       is bent) and 100 under a shelving policy
```

Only the hidden corpus has an answer key: the visible sample is the agent's material to learn from, and no
score is computed on it. The expected trees hold only the books the tier scores (30 / 66 / 100); books outside
the tier are not part of that setting's answer. No client e-mails or SQL exports were added: the drive already
contains the client's own catalog exports, and new side material would change what the case tests.
