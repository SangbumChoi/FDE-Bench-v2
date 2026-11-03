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
**hidden corpus** built by the same recipe with another seed (same size and mix of kinds, other books, other
archive, catalog and numbered file names), identical in every setting. Everything is synthetic: titles, names
and blurbs are generated from invented vocabularies written natively in each language. Only the standard library
is needed to read every format.

The case is **audited** (`audited: true`): `dataset/audit.json` holds its ground truth audit, `GT.md` the ground
truth in five parts generated from it (client facts, validity checks, objective, reference and bounds,
diagnostic cases), and `CLIENT_REVIEW.md` the passages the simulated client answers each target from, in all five
locales, for a human reviewer. Both are written by `gt_report.py`.

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
| **What is added** | Formats, the layout, name rules, description extraction, the year basis, romanized pairs | Legacy encodings (GB18030, CP949, Shift_JIS, CP1252); `令和元年`, `昭和50年`, `民國98年`, `단기 4342년`, `二〇〇九年`, `MMIX`; full-width and decomposed titles; forbidden path characters; one author under several romanizations (official pair only in the author's other books); copies across formats and folders to merge; source precedence (embedded metadata > title page > file name) | Missing author/title/description recovered from another file; title from a meaningful file name; year from a `©` line; `NO_TITLE` / `NO_YEAR` / `NO_DESCRIPTION` / `CONFLICT` (same-rank year disagreement) / `UNREADABLE` (image-only scan) review with reason code; the client's policy for books with no author (`NO_AUTHOR` review, or shelved under a fallback name); scans that duplicate a readable file; junk (`.DS_Store`, `Thumbs.db`, `desktop.ini`, `~$` lock files, `__MACOSX/._*`, empty files); books inside zip archives; multi-book catalog CSVs (English and Japanese headers) |
| **Name-length pool** (`max_len`) | 60, 48, 40: the subtitled titles are cut at a different point by each | 50, 40, 32: + co-author lists and long place-name titles at 32 | 40, 32, 24: + mid-length titles and co-author lists |
| **No-author policy** (`no_author`) | not drawn (the books are out of scope) | not drawn | review, or shelved under "Unknown" or "Anonymous" |
| **Rules** | `utf8_output`, `safe_names` (physical); `one_file_per_book`, `review_reason`, `manifest_rows`, `review_copies` (contractual) | same | + `no_fabrication`, `no_guessing` (contractual); under the review policy `missing_author_review`, under a shelving policy `missing_author_shelved` (business policy) |
| **Scoring extras** | out-of-scope books are ignored | −0.5 per library file that is no book | review policy: a book without an author waiting in review earns 0.7 (shelving it under "Unknown" earns 1 but needs an approved exception); shelving policy: such a book is scored like any other placed book; a library file whose text is in none of the sources breaks `no_fabrication` |
| **What the requirements put out of scope** | "Other files in the drive (old encodings, copies in several formats, damaged or incomplete material, archives, catalogs, scans) are not checked yet, but the program must not stop on them" | "The exceptions (missing fields, scans, archives, catalogs, junk) are not scored yet, but anything that is not a book must not end up in the library" | nothing |

A rule seed draws the same position of a pool in every tier (the draw does not depend on the tier), but `max_len`
has a different pool per tier and `no_author` has candidates only in hard. So the same seed gives a tighter name
limit in each harder tier, and in hard it may change the no-author policy: the three tiers' references differ in
every public seed, and each one scores below the other tier's own reference under that tier (table below).

### Parameters

A rule seed s draws position `Random("data_knowledge/multilingual_corpus_curator|<name>|s").randrange(n)` of
each pool of n candidates, independently of the other parameters. The first five pools are the same in every
tier. Every parameter is the fact of one target (`param:` in `locales/en/targets.yaml`).

| Parameter | Pool | What it changes (hidden corpus, public world, placed books in scope easy / medium / hard) | Target |
|---|---|---|---|
| `layout` | `library/<year>/<title>/<author>.txt`, `library/<year>/<author>/<title>.txt`, `library/<author>/<year>_<title>.txt` | every placed book's path (30 / 66 / 88–90) | `layout` |
| `year_basis` | first publication, this edition (a book with one year uses it for both) | books whose two years differ (15 / 37 / 44) | `year_basis` |
| `script` | original, Latin (the romanization paired in the metadata) | Chinese, Korean and Japanese books (18 / 40 / 58) | `script` |
| `multi_author` | first author only, all joined with `" & "` | books with two authors (10 / 23 / 30) | `co_authors` |
| `sep` | `_`, `-`, a plain space | names with spaces (18 / 40 / 53 in the original script, every book in Latin) | `separator` |
| `max_len` | easy 60, 48, 40; medium 50, 40, 32; hard 40, 32, 24 | names longer than the limit: easy 5–6; medium 13, 13, 15–17; hard 15, 17–19, 21–38 (ranges over script and co-author rule) | `max_len` |
| `no_author` | easy and medium `review`; hard `review`, `Unknown`, `Anonymous` | the 2 author-less books (hard): `review` sends them to `NO_AUTHOR` review (0.7 each) under the bendable `missing_author_review`; a name shelves them under that author name like any other book (1 each), and `missing_author_shelved` makes review or another name invalid | `missing_author` |

`derive_params` adds `fallback_author`, the name the texts quote: the drawn name under a shelving policy, and
"Unknown" (the name an approved exception would use) under the review policy. No combination is infeasible: the
generator keeps every title distinct within its first 24 characters (the tightest limit) in both scripts, so no
two placed books share a path under any combination, and the case defines no `admissible`.

Name rules in every setting: NFKC; each `\ / : * ? " < > |` or control character becomes a space; whitespace
runs become the separator; cut to `max_len` characters; strip spaces, dots and separators at both ends. A
tighter limit reaches more names, so getting the order of these steps wrong costs more often: cutting a
decomposed Spanish title before NFKC keeps fewer letters, and a cut that lands on a separator leaves one to strip.

### Public panel

The panel shows every candidate of every pool: across seeds 11, 18 and 21 each three-candidate pool gives all
three of its values (in every tier) and each two-candidate pool both of its values. Seed 11 comes first because
validate-case checks binding from it, and its hard draw shelves the author-less books, so the policy check
compares a valid shelving reference with the policies it breaks.

| Setting | `layout` | `year_basis` | `script` | `multi_author` | `sep` | `max_len` | `no_author` (→ `fallback_author`) | Reference | Baseline | Bound |
|---|---|---|---|---|---|---|---|---|---|---|
| easy/s11 | author/year_title | first | latin | all | `" "` | 40 | review (Unknown) | 100.00 | 16.67 | 100.00 |
| easy/s18 | year/title/author | first | latin | first | `-` | 48 | review (Unknown) | 100.00 | 16.67 | 100.00 |
| easy/s21 | year/author/title | edition | original | first | `_` | 60 | review (Unknown) | 100.00 | 16.67 | 100.00 |
| medium/s11 | author/year_title | first | latin | all | `" "` | 32 | review (Unknown) | 100.00 | 13.03 | 100.00 |
| medium/s18 | year/title/author | first | latin | first | `-` | 40 | review (Unknown) | 100.00 | 13.03 | 100.00 |
| medium/s21 | year/author/title | edition | original | first | `_` | 50 | review (Unknown) | 100.00 | 13.03 | 100.00 |
| hard/s11 | author/year_title | first | latin | all | `" "` | 24 | Unknown | 100.00 | 8.60 | 100.00 |
| hard/s18 | year/title/author | first | latin | first | `-` | 32 | review (Unknown) | 99.40 | 8.60 | 99.40 (100 with the exception) |
| hard/s21 | year/author/title | edition | original | first | `_` | 40 | Anonymous | 100.00 | 8.60 | 100.00 |

Objectives on the hidden corpus at the public world seed (20261027); "bound" is `objective_bound`, the most a
valid program can score (`expected_output` scores it). Private seeds draw any other combination, e.g. seed 101:
`author/year_title`, first, original, first, `-`, 60 / 50 / 40, review in every tier; seed 102:
`year/author/title`, first, original, first, `_`, 40 / 32 / 24, `Unknown` in hard.

**Parameter binding** (validate-case, from the s11 setting of each tier): every parameter changes the score of the
reference with every other value. At the public world the reference of hard/s11 scores 100.00, and with one
parameter changed: `layout` 46.00 (a misfiled book earns 0.4; the 10 review books keep their credit),
`year_basis` → edition 73.60, `script` → original 65.20, `multi_author` → first 82.00, `sep` → `_` or `-` 46.00,
`max_len` → 40 or 32 77.20, `no_author` → review invalid (`missing_author_review`), → Anonymous invalid
(`missing_author_shelved`). In easy (from 100.00): `layout` 40.00, `year_basis` 70.00, `script` 64.00,
`multi_author` 80.00, `sep` 40.00, `max_len` 88.00; in medium: 40.00, 66.36, 63.64, 79.09, 40.00, 84.55. The same
checks pass on world seeds 1, 2 and 3.

**References across settings** (public world; each row is a setting, each cell another setting's reference scored
under it; `*` = invalid):

| Scored under | easy s11 / s18 / s21 | medium s11 / s18 / s21 | hard s11 / s18 / s21 |
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

Another seed's reference keeps its layout, so every book it places is misfiled (0.4). The same seed's reference
from another tier differs in the length limit and, in hard, in the no-author policy: it loses 10–29 points, and
under each hard policy the references written for another policy are invalid (`missing_author_review` or
`missing_author_shelved`).

### What an agent must ask

Twelve targets, one fact each (GT.md part 1 shows that misreading any one of them alone loses at least a tenth of
the credit in every measured setting where it is in force):

- drawn per rule seed (`param:`): `layout`, `year_basis`, `script`, `co_authors`, `separator`, `max_len` and, in
  hard, `missing_author` (the no-author policy and its fallback name);
- the same under every draw: `content` (the file holds the description only), `review_codes` (the six codes) and,
  in hard, `no_description` (no description: `NO_DESCRIPTION`, never a placeholder), `conflict` (same-rank years
  that disagree: `CONFLICT`) and `generic_titles` (a generic file name is not a title: `NO_TITLE`).

The earlier targets `precedence`, `encodings`, `year_notations`, `author_variants`, `duplicates`, `containers`,
`scoring` and the parts of `exceptions` not listed above are no longer targets: they are data facts the sample
shows, or concern too few books to matter (GT.md lists the bound for each; REVIEW.md, Ground truth audit). They
stay in requirements.md, and the client answers them when asked.

**Value of asking** (audit, public world): a program that never asks (`robust_solution`: the reference's reading
of every fixed fact, the first candidate of each drawn rule, the longest name limit, and no review rows since it
cannot know the codes) earns a mean credit of 0.31 / 0.34 / 0.36 in easy / medium / hard, so asking
is worth 0.69 / 0.66 / 0.64 of the credit.

## File formats and the exception catalog

| Kind | Where the facts are |
|---|---|
| JSON | `title`, `title_latin`, `authors[{name, name_latin}]`, `first_published`, `edition_year`, `description` (years may be era strings in medium) |
| ONIX-like XML (namespace `ns.editeur.org/onix/3.0`) | `TitleText` (+ `textscript="Latn"`), `Contributor/PersonName` + `AlternativeName` or `PersonNameInverted`, `PublishingDateRole` 01 = this edition, 11 = first publication, `TextContent/Text` |
| EPUB (zip + OPF) | `dc:title`, `dc:creator` with `alternate-script` / `file-as` refinements, `dc:date` (this edition), `first-published` meta, `dc:description`; `dcterms:modified` is a trap |
| DOCX (zip + XML) | `docProps/core.xml` title and creator (`dcterms:created` is a trap); body paragraphs split into several runs = title page + description |
| PDF (uncompressed text streams) | Info `/Title`, `/Author` (UTF-16 hex strings; `/CreationDate` is a trap); page text as UTF-16 `Tj` strings, title-page lines whole, description lines wrapped |
| Scan PDF | image-only page, no text and no title: unreadable |
| HTML | `<title>`, `<meta name="author">`; body `h1`, `p.latin`, `p.byline`, `p.edition`, `h2`, description paragraphs; `<meta charset>` (Shift_JIS / CP949 in medium) |
| Markdown | front matter (`title`, `title_latin`, `author`, `author_latin`, `first_published`, `edition`) + body title page |
| Plain text | title page (title, `(romanized title)`, `Name（Romanized） 著` / `지음` / `by` / `por`, edition line, optional `©` line), heading (`内容简介`, `内容紹介`, `책 소개`, `About this book`, `Sinopsis`), description (sometimes hard-wrapped, CRLF, or in a legacy encoding) |
| Catalog CSV | one book per row; English or Japanese headers; `source` = `file.csv#row` |
| Zip archive | 2 books each plus an AppleDouble `__MACOSX/._*` entry; `source` = `archive.zip!inner/path` (one folder deeper in the hidden corpus) |

Composition of each corpus (fixed counts, languages partly random): 30 easy; medium 7 encodings, 6 year
notations, 4 full-width/decomposed titles, 5 forbidden characters, 5 romanization variants, 6 multi-file copies,
3 precedence conflicts; hard 3 author recoveries, 2 no author, 2 titles from file names, 2 no title, 2
description recoveries, 2 no description, 3 copyright-line years, 2 no year, 2 same-rank conflicts, 2 scan-only,
2 scans with a readable copy, 4 books in zips, 6 catalog rows; plus 8 junk files. Every second English and
Spanish easy book, and 60% of the others, carry a long subtitle (`The Silent Lighthouse — Stories from the
Northern Coast and the Keepers Who Stayed Behind`); 30% of the books have two authors. The archive and catalog
names come from small pools and the numbered file names (`doc_0391`, `scan_0414`) start at a random offset per
corpus: on the public world the hidden drive shares only 4 junk paths with the sample (12 before), and on world
seeds 1-3 at most one archive name besides them (with other contents). The hidden drive also always holds a
Shōwa-era year (the Japanese era book) and zip members one folder deeper.

## Scoring

Per scored book: **1** for the exact library path with the right description; **0.4** for the right
description at any other path (misfiled: the team has to find and move it); **0.2** for the right path holding
any other text. A book that belongs in review earns 1 when every manifest row naming one of its files says
`review` with the right reason code (0.4 when they agree on another code; under the review policy a
`NO_AUTHOR` book earns 0.7 in review); rows that disagree, or a library file for the book as well, earn nothing.
A book that belongs on the shelf earns nothing in review; under a shelving policy that includes the author-less
books, whose expected author is the drawn fallback name. Each book's manifest row is checked too (the only row
naming the book's files, all of them and nothing else; `placed` with the book's library path, or `review` with
its files copied byte for byte under `_review/`; a scan that copies a readable file may be in the row, listed as
skipped or left out): a missing or wrong row costs a fifth of the book's credit. Medium and hard subtract 0.5
per library file that is no book. Objective = 100 × credit / books scored (maximize); quality is normalized
between the baseline (0) and the reference (1), and `quality_cap` is 1.0 (the reference is the best possible).
Descriptions are compared after NFKC with whitespace removed, so wrapping does not matter. In hard,
`no_fabrication` also fires on a non-empty library file that holds no whole description paragraph of any book
and is not a piece (20+ characters) of one: placeholders and invented blurbs; a stray heading or a dropped
paragraph only loses credit.

The rules that make the outputs mandatory: `manifest_rows` (every library file is the path of exactly one placed
row, every placed row's path is a library file and its source names at least one file of the drive, an archive
member or a catalog row, written `!`, `/`, `:`, `#` or `|` after the archive or catalog path; no source is named in
two rows) and `review_copies` (every file of the drive named in a review row is copied under `_review/`). `no_guessing` (hard) makes the request's "not
guessed" a hard gate: a book whose title or year the sources do not settle (`NO_TITLE`, `NO_YEAR`, `CONFLICT`) is
not placed.

`score()` also reports `enforced` and `evidence` per target in force: the diagnostic, computed from the same run of
the program on the hidden drive (GT.md part 5). Degenerate programs (`shortcuts()` in case.py, GT.md part 2) are
invalid or score at most 0.42: reviewing everything, spamming review rows, placeholders or whole files at the
right paths, a header-only manifest, a manifest whose placed rows have an empty source or their own library path
as the source, review without copies, every book under all three layouts, copying the drive through, and a flat
`library/<title>.txt`. The diagnostic also tells these from a correct program: a flat path counts against
`layout`, a placeholder at the right path against `content`, and an author-less book that is neither shelved nor
in review against `missing_author`; in hard, a program that writes no review row at all is not enforced on
`review_codes` (in easy and medium no scored book belongs in review, and it stays None). A stray library file that
holds one book's whole description with more around it (a card at a path no rule gives) is still no book's file
for the score, but the diagnostic reads it as that book's, so a program misreading two facts is flagged on both.
The audit also tries the diagnostic on deliverables that are neither the reference nor an ablation (the answer
key, the baseline, `robust_solution`; GT.md part 5, REVIEW.md "Diagnostics on other deliverables"). The case has
no lazy `diagnose()` hook: the diagnostic is cheap and computed in `score()`.

The program's output on the hidden corpus is cached by the program's digest, so the settings, the violating
examples and the binding and cross-tier checks run each distinct program once (`validate-case` takes about three
minutes with the default world seeds 1–3; `audit-case` about 8 to 10 minutes).

## Reference and verified numbers (seed 20261027, hidden corpus)

The baseline (`reference/baseline.py` + the same `config.json`) is what the client could script without an
engineer: it shelves only the books that have a complete UTF-8 JSON export (title, author, a plain four-digit
year and a description) under the catalogue rules, leaves a JSON record whose ISBN also has an ONIX export for the
team (it cannot tell which of the two is right), and leaves every other file for the team (no other format, no
legacy encodings or era years, no merging of copies, no review area). It is valid in every setting.

The reference (`reference/organize.py` + `config.json` of the setting) is the full organizer: every format and
zip member, legacy encodings via the corpus's own UTF-8 character statistics, every year notation (eras, Minguo,
Dangi, Chinese numerals, Roman numerals, `©` lines), NFKC slugs, grouping by normalized title, per-field
precedence over all files of a book, the official name pair of every author from anywhere on the drive,
same-rank year conflicts, scans, junk and catalogs, and the drawn no-author policy. It files every hidden book
exactly as `expected_output` does: it reaches `objective_bound` in every setting, and `quality_cap` is 1.0. The
best known solution (`best_known_solution`, for the audit) is the answer key itself written by a program, an
oracle that reaches the bound too: a second full-knowledge deliverable, besides the reference, that the
diagnostic must never call not enforced.

| Tier | Books scored | Baseline objective | Reference objective = bound |
|---|---|---|---|
| easy (s11, s18, s21) | 30 | 16.67 | 100.00 |
| medium (s11, s18, s21) | 66 | 13.03 | 100.00 |
| hard, review policy (s18) | 100 | 8.60 | 99.40 (100 with the exception) |
| hard, shelving policy (s11, s21) | 100 | 8.60 | 100.00 |

The baseline earns 5 / 9 / 9 exact placements; in medium and hard 2 of them (copies) lose a fifth because the
book has other files and its manifest row lists only the JSON. On world seeds 1, 2 and 3 the baseline scores
3.33–20.00 (easy), 2.73–19.70 (medium) and 3.80–14.00 (hard) against references of 100.00 (99.40 under the review
policy). Under the review policy, bending `missing_author_review` (shelving the two author-less books under
"Unknown") is valid when relaxed and gives 100.00 in hard/s18 (normalized quality 1.007).

## Notes

- The visible corpus is byte-identical in every setting and locale (`content_dirs: [corpus]`); only the
  archivist's note outside the corpus is localized.
- `write only inside out_dir` and `never modify the corpus` are enforced by the runner (the program gets a copy
  of the corpus, read-only under docker), not scored.

## Stored dataset (`dataset/`)

Written by `python -m fdebench2.cli export-dataset cases/data_knowledge/multilingual_corpus_curator`;
`validate-case` regenerates it and fails if it drifts from the generator (~2 MB, ~2,300 small files).
`audit-case` writes `dataset/audit.json` (export-dataset keeps it).

```
dataset/
  agent_view/<lang>/corpus/...       the agent's sample drive (byte-identical in every locale) + the archivist's note
  hidden/corpus/...                  the hidden drive exactly as organize() receives it (same in every setting)
  audit.json                         the ground truth audit (public world): ablations, shortcuts, value of asking,
                                       bounds, diagnostics; GT.md is generated from it
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
