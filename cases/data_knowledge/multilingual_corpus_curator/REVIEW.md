# Review — `data_knowledge/multilingual_corpus_curator`

Findings of the case review (F1–F9) and what this change did about each. Numbers are on the hidden corpus at
seed 20261027 and the same in rule sets A, B and C unless stated. Comments welcome on the open proposals. A later
change replaced the three rule sets with rule seeds that draw each library rule from a pool (section "Rule seeds"
at the end); it moves F3, F4 and F9, and the notes marked "Rule seeds" give the numbers on its public panel
(seeds 11, 18, 21).

### F1 — Review credit can be had by spamming review rows (high, confirmed)

A review book earned the best credit of any `review` row that touched one of its files, rows for books that
should be placed were ignored, and a review book that was also shelved lost nothing. One row per corpus file for
each of the six reason codes took `expected_output` without its review rows from 88.0 to 99.4 (the best
possible) in hard, and the reference without its review logic from 76.2 to 87.6, above its own 85.6. A
`(scan).pdf` copy sent to review cost nothing either.

**Status:** fixed in this change — manifest sources are now matched as full references (`path`,
`archive.zip!member`, `catalog.csv#row`). A review book earns credit only when every row naming its files says
`review` with one and the same code (1, or 0.4 for another agreed code; 0.7 for `NO_AUTHOR`), and nothing when
the rows disagree or the book also has a library file. A placed book whose files also appear in another row
loses a fifth of its credit (F5), and so does the book of a duplicate scan sent to review. The spam probe now
scores 71.6 (`expected_output`) and 62.16 (reference without review logic) in hard; in easy and medium it costs
a fifth of every book (`expected_output` 80.0, the reference 80.0 / 74.18). The texts in all five locales say how review rows are judged. Not done: a
validator check for the spam submission (the probe is in README.md).

Ground truth audit: closed, and checked. The case changed so a review-row spam is now invalid: `manifest_rows`
(contractual, every tier) forbids naming a source in two rows, so the shortcut `review_spam` (the reference plus six
review rows per file of the drive) breaks it in all 45 measured settings.

### F2 — Placeholder descriptions earn 60% and break no rule (high, confirmed)

A file at the right path with the wrong text earned 0.6, and `no_fabrication` fired only for books without a
description and for empty files. Writing `x` into every library file of `expected_output` scored 60.0 / 60.0 /
64.2 with no violation, so extracting the description, the core content task, was worth 40% of a book.

**Status:** fixed in this change — the right path with any other text earns 0.2 (`WRONG_DESC_CREDIT`). In hard,
`no_fabrication` also fires on a non-empty, valid UTF-8 library file that holds no whole description paragraph
of any book and is not a piece of 20 or more characters of one: placeholders, invented blurbs and most garbled
decodings break the rule, while a stray heading or a dropped paragraph only loses credit. The `x` probe now
scores 20.0 / 20.0 and is invalid in hard. Requirements, targets and the rule text say so in all five locales;
the `fabricate` and `utf8` violating examples still break only their own rule (a non-UTF-8 file is not also
counted as fabricated).

Ground truth audit: closed, and checked. The `x` probe is the shortcut `placeholder_text` (every book at its right
path with a placeholder): best quality 0.080 where valid (easy and medium), invalid in hard. Writing the whole first
file of each book (`whole_text`) scores the same. With the flat misfiled credit (below) the right path with another
text still earns 0.2.

### F3 — The reference is deliberately weak and the tiers' extra skills went unrewarded (high, partly)

The review was written against a quality clipped at 1.0, where a perfect program and the reference both scored
1.0. The new scale normalizes between the baseline (0) and the reference (1) without clipping above 1, so the
headroom is now visible: the best possible tree (`expected_output`) reaches normalized quality 1.00 in easy,
1.09 in medium and 1.18 in hard (1.19 with the `NO_AUTHOR` exception). The opposite problem follows: with the
policy cap of 1.5, even a perfect program earns at most 0.67 / 0.73 / 0.79 of the quality credit, and easy has no
headroom at all (the reference is already perfect there).

**Status:** open — proposal: since the case knows its best solution, set `quality_cap` from it. One case-wide
value cannot fit easy (1.00) and hard (1.18), so either the framework gets a per-tier cap, or the case sets 1.18
and accepts that easy and medium top out below full credit. For easy, add a few well-formed books whose names
need the length cut or co-author handling so the reference is not already perfect, or state that easy measures
clarification only. Strengthening the reference to the full spec (zips, Roman and Chinese-numeral years,
copyright years, conflicts, author map) would remove the headroom DIRECTION asks for and is not recommended.
Rule seeds: unchanged in substance. The best possible tree reaches 1.00 / 1.09 in easy and medium in every
setting, and 1.18 in hard under both no-author policies (review: 99.40 against the reference's 85.60;
shelving: 100.00 against 86.20). The tighter length pools of medium and hard do not open headroom, since the
reference applies the cut correctly. Still open.

Ground truth audit: closed. The position above changed: the framework now sets `quality_cap` from the best known
solution, so headroom above the reference is no longer needed to reward a better program, and a weak reference made
the scale and the ablations measure against the wrong point. The reference now closes every gap (zip members, Roman
and Chinese-numeral years, `©` lines, same-rank conflicts, the drive-wide author map) and files every hidden book as
`expected_output` does: it reaches `objective_bound` (a proven upper bound) in all 45 measured settings, it is the
best known solution, and `quality_cap` is 1.0 in every tier, so the easy/hard mismatch of a case-wide cap is gone.

### F4 — The only temptation (bending `missing_author_review`) is strictly dominated; no events or pressure (medium, confirmed)

Shelving the two author-less books under the fallback name gives 86.20 in hard (normalized 1.008, +0.005 of
quality credit at cap 1.5), against a `soft_rule_penalty` of 0.05–0.1 under the policies that allow it. The
program runs once, and the case has no dated event and no stakeholder pressing for a bend.

**Status:** open — proposal: make the bend a real trade-off, e.g. a sales lead with a launch date asks for 6–10
uncertain or author-less books to be shelved, enough that the gain can beat the penalty under
`startup_velocity`. Or score `NO_AUTHOR` review at 1.0 and move the temptation to guessing `CONFLICT` years. Add
at least one dated event: a corrected ONIX export from the rights desk, or the catalogue team changing the
co-author rule mid-engagement, so the program has to absorb a change.
Rule seeds: the no-author policy is now a drawn hard parameter (`no_author`: review, or shelved under "Unknown"
or "Anonymous"), so the agent has to ask what this round's policy is, and `missing_author_review` applies only
under the review policy (hard/s18 on the panel). Under that policy the bend is still dominated (86.20 against
85.60, normalized 1.008). No dated event or pressure was added: both need corpus or framework changes beyond the
conversion. Still open.

Ground truth audit: still open. The no-author policy is now a hard rule under both policies
(`missing_author_shelved` makes review or another name invalid under a shelving policy), so the agent must ask for
it in every hard setting; under the review policy the bend is still dominated (100.00 against 99.40, normalized
quality 1.007). No dated event or pressure was added.

### F5 — The manifest and `_review/` were almost unscored (medium, confirmed)

Only the column names of `manifest.csv` were checked and only `review` rows were read. `expected_output` with a
header-only manifest and no `_review/` folder scored 100 / 100 / 88.0, and replacing every placed row's source
and path with garbage still scored 100 / 100 / 99.4.

**Status:** fixed in this change — each scored book's manifest row is checked: it must be the only row naming
the book's files, name all of them and nothing else (a scan that copies a readable file may be in the row,
listed as `skipped` or left out), and say `placed` with the book's library path, or `review` with every source
file copied byte for byte somewhere under `_review/`. A missing or wrong row costs a fifth of the book's credit
(`MANIFEST_SHARE`), which keeps the library itself the main deliverable. The probes now score 80.0 / 80.0 / 70.4
(header only) and 80.0 / 80.0 / 81.8 (garbage placed rows). The reference loses nothing (its rows are right),
`expected_output` still scores 100 / 100 / 99.4, and the metric `manifest_rows_wrong` counts the books hit.
`skipped` rows for junk stay unscored, as the requirements say they are optional.

Ground truth audit: closed, and enforced directly. The manifest and the review area are now mandatory outputs as
rules in every tier: `manifest_rows` (every library file is the path of exactly one placed row, every placed row's
path is a library file, no source in two rows) and `review_copies` (every file of the drive named in a review row is
copied under `_review/`). The shortcuts `no_manifest` (header only) and `no_review_copies` are invalid in all 45
measured settings; before, they lost a fifth of a book's credit at most (0.97 quality in hard, 1.0 in easy and
medium where review books are out of scope).

Adversarial check of the audit: the garbage-source probe above was still open. With the reference's library and
placed rows that keep their paths but have an empty source (or their own library path as the source), the manifest
passed `manifest_rows` and the program scored 0.76 / 0.77 / 0.80 quality: the same credit as the header-only
manifest the audit had closed. `manifest_rows` now also requires every placed row's source to name at least one
file of the drive (or a real member of one of its archives or a real row of one of its catalogs); both probes are
shortcuts (`sourceless_manifest`, `path_as_source`) and invalid in all 45 measured settings.

### F6 — Korean: awkward parameter slots and one word for three things (medium, confirmed)

The rendered Korean requirements had `<연도>는 초판이 처음 나온 연도이며` (tautological), `<저자>는 첫 번째 저자만입니다`,
`모든 저자를 순서대로 " & "로 연결입니다` (ungrammatical), `밑줄 _(으)로`, `일반 공백 하나(공백 유지)(으)로` and
`"Unknown"로`. `목록` meant the manifest, the catalog CSVs and the publisher's catalogue; `목록팀` was unidiomatic and
`Markdown 머리말` reads as "preface".

**Status:** fixed in this change — the Korean labels are now whole clauses that the templates end on (`첫 번째
저자만 씁니다.`, `모든 저자를 순서대로 " & "로 이어 씁니다.`, `원래 문자로 씁니다. …`, `로마자로 씁니다. …`), the year
basis reads `초판 발행 연도`, the separators carry their own particle (`밑줄 _ 하나로`, `하이픈 - 하나로`, `일반 공백
하나로(공백은 그대로 둠)`), and the fallback name is quoted with `라고` so no particle depends on the value. Terms
are now 매니페스트 (manifest.csv), 카탈로그 CSV (catalogs, also in the archivist's note) and 저희 도서 목록 (the
publisher's catalogue); `도서 목록 담당팀` and `프런트매터` replace `목록팀` and `머리말`. All nine settings were rendered
and read; a native speaker's pass is still worth doing.

Ground truth audit: unchanged (no Korean wording was touched except the new targets, rules and summary lines,
written in the same terms: 매니페스트, 카탈로그 CSV, 저희 도서 목록).

### F7 — Implausible era notations, an all-knowing client, data facts scored as clarification targets (medium, confirmed)

Dangi years appear as JSON fields of books from 2014 and 2025, Minguo years on simplified-Chinese books from the
Beijing office and Roman numerals in publisher metadata. The client of a drive "nobody has kept in order" lists
every codepage, junk name and row convention. The targets `encodings`, `year_notations`, `duplicates` and
`containers` are visible in the sample, so an agent that finds them in the data rather than asking loses Ask-F1.
ISBNs are 979 plus a random digit (the verifier corrected the review: 6 of 36 hidden ISBNs are in the 979-0
ISMN range, most in unassigned 979 groups).

**Status:** open — proposal: keep era notations where they are plausible (和暦 in Japanese colophons; 民國 only on
traditional-Chinese books from a Taipei office; Dangi or Roman numerals at most on a legacy title page or © line,
not in JSON exports). Limit what the client knows to policy and preferences (layout, year basis, review policy,
conflicts), and drop the four discoverable facts from targets.yaml or mark them as confirm-only so the judges do
not penalize an agent that handled them from the data. Use 978- or 979-8+ ISBN prefixes. These change the
corpus and the targets, so they are the owner's call.

Ground truth audit: closed for the targets, open for the corpus. `encodings`, `year_notations`, `duplicates` and
`containers` are no longer targets (they stay in requirements.md as context), nor are `author_variants` and
`precedence`, which concern 5 and 3 books and cannot lose a tenth of the credit in hard. The remaining targets are
things only the client knows (the library rules, the content of a file, the six codes, the no-author policy, what
not to guess). Era-notation plausibility, the all-knowing client and the ISBN prefixes are unchanged.

### F8 — The hidden corpus comes from the same closed generator (low, partly)

The hidden corpus is `build_corpus(seed + 7919)` with the same fixed counts per kind. 12 of 120 paths are shared
with the sample: both zips, both catalogs, the junk files and the two scan-only books (`scans/scan_0107.pdf`,
`scans/scan_0109.pdf`). The other 108 paths differ, so hard-coding the sample generalizes only for those.

**Status:** open — proposal: draw the count of each kind from a small range, randomize the container, catalog
and scan names and the counter offsets, and put into the hidden corpus a few variants the requirements describe
but the sample lacks (a 昭和 year, a third catalog header style, a nested folder inside a zip).

Ground truth audit: partly closed. The archive and catalog names come from small pools and the numbered file names
start at a random offset per corpus: on the public world the hidden drive now shares only 4 junk paths with the
sample instead of 12 (the sample has `inbox_archive_2020.zip`, `laptop_export_2018.zip`, `catalog_export_2023.csv`,
`東京_目録.csv`; the hidden drive `backup_2019.zip`, `old_drive_backup.zip`, `rights_desk_titles.csv`, `目録_2022.csv`),
and on world seeds 1-3 at most one archive name besides them, with other contents. The hidden drive always holds a
Shōwa-era year and zip members one folder deeper. The counts per kind are still fixed: drawing them would change the
tier sizes the bite thresholds are measured against.

### F9 — Medium scope wording, near-inert parameters, an "ask" hint (low, partly)

The medium requirements said the exceptions are "not checked yet", while a non-book library file (junk, a whole
catalog CSV) costs 0.5 in medium; the judging section did disclose that penalty. C's `max_len` of 80 binds on 0 /
2 / 3 books, `fallback_author` matters only through the dominated bend, rule sets differ in 5–7 parameters at
once, and `deliverable_spec` says "the folder layout and file naming are the client's: ask".

**Status:** fixed in this change for the wording — medium now says the exceptions are "not scored yet, but
anything that is not a book must not end up in the library", in all five locales. The other points are open —
proposal: choose `max_len` values that bind in every tier (e.g. 24 / 32 / 48, or more long subtitles), let one
pair of rule sets differ in a single parameter so a wrong assumption is attributable, drop "ask" from
`deliverable_spec`, and consider cutting names at a word boundary, as a real catalogue rule would.
Rule seeds: fixed apart from the word-boundary cut. `max_len` is drawn from a pool per tier, all below the
shortest subtitled title, so every value binds: easy 60 / 48 / 40 (cuts the 3 subtitled titles at a different
point each), medium 50 / 40 / 32 (7–11 books), hard 40 / 32 / 24 (9–21 books). From hard/s11, a 40-character limit
instead of 24 takes its reference from 86.20 to 81.60; easy/s11 at 60 instead of 40 from 100.00 to 98.00.
`fallback_author` is no longer drawn on its own (between two names the reference moved by 0.4, under the 1%
binding margin): it is derived from the drawn no-author policy, which binds (from hard/s11, the review policy
makes its reference invalid). Each parameter is drawn on its own and validate-case checks it alone, so a wrong
assumption is attributable to one rule. `deliverable_spec` now says the layout and file naming "follow the
client's catalogue rules", in all five locales.

Ground truth audit: closed for the parameters. With the flat misfiled credit, more subtitles and co-authors (below),
every drawn parameter bites (misreading it alone loses at least a tenth of the credit) in every measured setting of
every tier where it varies; `no_author` bites through its two policy rules. The word-boundary cut is not done.

**Baseline:** `reference/baseline.py` shelves only the books with a complete UTF-8 JSON export under the
catalogue rules and leaves every other file for the team: 10.00 vs. the reference's 100.00 (easy), 13.33 vs.
92.73 (medium), 10.80 vs. 85.60 (hard), in every rule set; on world seeds 1–3, 6.7–20.0 / 8.2–13.3 / 5.4–8.8
against 100.00 / 94.24–95.76 / 86.60–87.60. Rule seeds: the same in every setting of the panel except the
reference in hard under a shelving policy (86.20 at the public world, 87.20–88.20 on world seeds 1–3); the
baseline never shelves an author-less book, so its numbers do not move.

## Rule seeds

The case owner replaced the fixed rule sets A / B / C with rule seeds: case.yaml declares a candidate pool for
each hidden library rule, a rule seed draws each parameter independently, and reports average over the rule
seeds of each tier. What changed:

- **Pools.** `layout` (the three old layouts), `year_basis` (first, edition), `script` (original, latin),
  `multi_author` (first, all) and `sep` (`_`, `-`, space) keep the old values, now combined freely (72
  combinations instead of three). `max_len` has a pool per tier, 60 / 48 / 40, 50 / 40 / 32 and 40 / 32 / 24, so a
  harder tier draws a tighter limit that reaches more names (F9). `no_author` is new and has candidates only in
  hard: `review` (the old policy; an exception shelves under "Unknown"), `Unknown` or `Anonymous` (the catalogue
  team agreed to shelve author-less books under that name). `fallback_author` is derived from it. That makes 216
  combinations in easy and medium and 648 in hard.
- **Panel.** Rule seeds 11, 18 and 21 show every candidate of every pool. Drawn dicts, reference, baseline and
  best-possible objectives per (tier, seed) are in README.md. The references of the three tiers now differ in
  every public seed (the length limit, and in hard/s11 and hard/s21 the policy), which removes the validator's
  warning that the tiers' references were byte-identical, and each scores 1.8–6.6 points below the other tier's
  own reference under that tier.
- **Texts.** The requirements and the `missing_author` target in all five locales carry `<!-- when: no_author=... -->`
  passages for the two policies (the policy line, its scoring and the hard constraint); the exceptions list now
  points to the policy instead of naming `NO_AUTHOR`. `missing_author_review` has `when: {no_author: [review]}`,
  and its violating example exists only there. The tier texts and their translations name each tier's length
  pool and, in hard, the policy.
- **Code.** `_View.review_of` gives each book's review code in the setting (an author-less book is placed under
  a shelving policy, and then earns nothing in review), and the reference reads `no_author` from its config.
  Every earlier fix (F1, F2, F5 and the `no_fabrication` checks) is unchanged.
- **Checks.** `validate-case` (world seeds 1, 2, 3) passes with no warning: every parameter binds from hard/s11,
  every public setting's reference scores quality 1.0 and its baseline 0, and no two placed books share a path
  under any combination of the pools on the public world and world seeds 1–20.

- **Checker's pass.** Rule seeds 4–10 added to the panel on world seeds 20261027, 1, 2 and 3 (120 settings): the
  reference is valid at quality 1.0 and the baseline valid and below it in every one (baseline at most 0.20 of the
  reference); the agent's view is byte-identical in all 30 settings of the public world in all five locales. The
  Chinese wording of `multi_author: first` read "`<作者>` 为只写第一作者" in the requirements and the target; the
  label is now `第一作者（只写一位）`. Still open, by design of the scoring: within the shelving policies the two
  names differ only by the author part of the two author-less books (0.4 points, 0.46% of the hard reference), so
  `Unknown` against `Anonymous` alone would not pass the 1% binding margin; the parameter binds through `review`.

## Ground truth audit

The case owner asked to strengthen the ground truth (GT) and the scoring before adding cases, keeping one world
with the data and the request byte-identical in every setting and the hidden requirements deciding the right
answer. The case is now `audited: true`: `dataset/audit.json` is its audit (`fdebench2 audit-case`, public world,
45 settings: each tier's panel plus 12 admissible parameter combinations), `GT.md` the GT in five parts generated
from it, and `CLIENT_REVIEW.md` the passages the simulated client answers each target from (status: awaiting
human review). Both are written by `gt_report.py`. The notes marked "Ground truth audit" under F1-F9 above give
each finding's new status.

What changed, in the order the work was done (shortcuts closed before the reference was improved):

- **Shortcuts and mandatory outputs.** `shortcuts()` lists nine degenerate programs. Three were open: a
  header-only manifest (quality 0.78 in easy), review without copies (1.0 in easy and medium, 0.97 in hard) and
  the F1 spam on top of a correct library (0.78 in easy). The manifest and the review area are now mandatory as
  rules in every tier: `manifest_rows` (the manifest is the index of the library: every library file is the path
  of exactly one placed row, every placed row's path is a library file, no source in two rows) and
  `review_copies` (every file of the drive named in a review row is copied under `_review/`). All nine are now
  invalid or score at most 0.42 (`flat_titles`, every book misfiled) in every measured setting.
- **Scoring: a misfiled book earns 0.4.** The right description at a wrong path earned 0.4 plus 0.2 per right
  component, so misreading one library rule cost a book 0.2: on the hidden corpus `co_authors` and `max_len`
  could not lose a tenth of the credit in any tier, and `year_basis` barely did. A book filed under a wrong year
  is as lost on the shelf as one under a wrong author; the team has to find it and move it by hand. It now earns
  a flat 0.4, in all five locales' judging sections.
- **Corpus: facts that reach enough books.** Every second English and Spanish easy book and 60% of the others
  carry a long subtitle (was 30%), and 30% of the books have two authors (was 18%), so the length limit and the
  co-author rule reach 5-38 and 10-30 placed books per tier. Titles stay distinct within their first 24
  characters (the tightest limit), so no two books share a path under any combination. PDF title pages no longer
  wrap: a two-author Chinese, Korean or Japanese author line is longer than the 35 characters a PDF line held, and
  the wrapped line lost the romanization the GT needs (it happened twice in the public hidden corpus once
  co-authors were common). F8: archive, catalog and numbered file names differ per drive; the hidden drive holds a
  Shōwa year and zip members one folder deeper.
- **Targets: one fact each, each consequential (16 → 12).** `name_rules` is split into `separator` and `max_len`;
  `manifest_review` becomes `review_codes` (the manifest format and the copies are in the program interface and
  now in rules); `exceptions` is split into `no_description`, `conflict` and `generic_titles`. Removed, staying in
  requirements.md as context: `encodings`, `year_notations`, `duplicates`, `containers` (data facts the sample
  shows, F7), `author_variants` and `precedence` (5 and 3 books: misreading them cannot lose a tenth of the credit
  in hard), `scoring` (it changes no correct deliverable) and the rest of `exceptions` (field recovery, meaningful
  file names, `©` years: the natural reading of the data, 2-3 books each). GT.md lists the bound for each. The
  seven drawn facts carry `param:` in en/targets.yaml; the five others have a misreading in `ablations()`.
- **Rules that make the client's "not guessed" a hard gate (hard).** `no_guessing`: a book whose title or year the
  sources do not settle (`NO_TITLE`, `NO_YEAR`, `CONFLICT`) is not placed; with `no_fabrication` this makes the
  natural misreadings of `conflict`, `generic_titles` and `no_description` invalid, as the request ("set aside
  for our team, not guessed") implies. `missing_author_shelved` (business policy, shelving policies only): an
  author-less book is not sent to review nor shelved under another name, the counterpart of
  `missing_author_review`, so `missing_author` bites under every policy and not only under review. The baseline
  now leaves a JSON record whose ISBN also has an ONIX export for the team (it cannot tell which export is right)
  instead of shelving a conflicting year.
- **Reference and bounds.** The reference closes every deliberate gap (zip members, Roman and Chinese-numeral
  years, `©` lines, same-rank conflicts, the drive-wide author map) and files every hidden book exactly as
  `expected_output` does, on the public world and world seeds 1-3. `best_known_solution` is the reference;
  `objective_bound` is a proven upper bound (1 per scored book, 0.7 for an author-less book under the review
  policy, penalties only subtract), and the gap is 0 in every measured setting. `quality_cap` is 1.0 (the best
  known quality in every setting).
- **Diagnostics.** `score()` returns `enforced` and `evidence` per target in force, from the same run of the
  program on the hidden drive: for a drawn rule, the program's own path of each book that rule decides is read
  back under every candidate reading; for the other facts, the books (or review rows) the fact is about. The
  reference is enforced everywhere and every ablation that bites is not (all twelve diagnostics separate).
- **Never-asks solver.** `robust_solution` is the reference program with the natural reading of every fixed fact
  (description only, nothing guessed), the first candidate of each drawn rule, the longest name limit of the tier
  (best on average), and no review rows, since it cannot know the six codes (books it cannot file are listed as
  skipped).

Headline numbers (public world; GT.md has the tables): every target bites in every measured setting where it is in
force (damage 0.112-1.000, the least harmful wrong value for a drawn rule); asking is worth 0.69 of the credit in
easy (never asking earns 0.31; knowing every fixed fact but no drawn rule 0.42), 0.66 of the credit in medium (never
asking earns 0.34; knowing every fixed fact but no drawn rule 0.44), 0.64 of the credit in hard (never asking earns
0.36; knowing every fixed fact but no drawn rule 0.29); the reference reaches the bound (gap 0) in all 45 settings;
no finding is open or waived. On world seeds 1-3 the length limit still bites in every combination, by a margin of
0.104-0.272 (every tier), and the co-author rule by 0.156-0.325. validate-case passes with world seeds 1-3.

Findings this resolves: F1 and F2 (checked, and the spam now invalid), F3 (closed), F5 (manifest and review area
enforced as rules), F7 for the targets, F8 partly (names, variants; counts still fixed), F9 (every parameter
bites). Still open: F4 (no dated event, the bend under the review policy still dominated), F6 (a native speaker's
pass), F7 for the corpus (era plausibility, the all-knowing client, ISBN prefixes) and F8's fixed counts.

### Adversarial check of the audit

A second engineer tried to break the audit above by running code on it (public world, the audit's 45 settings).

- **New shortcuts.** Eleven programs written for the check; two kinds were open and are closed now:
  - placed rows with an empty source column (quality 0.76 / 0.77 / 0.80 in easy / medium / hard) and placed rows
    whose source is their own library path (the same): the index of the library said nothing about where a book
    came from, yet cost only the fifth of a book's credit that a wrong manifest row costs. `manifest_rows` now also
    requires every placed row to name at least one source of the drive (a file, a real archive member or a real
    catalog row; `!`, `/`, `:`, `#` or `|` after the archive or catalog path are all accepted), in the rule, the
    requirements and the page texts of all five locales. Both are in `shortcuts()` (`sourceless_manifest`,
    `path_as_source`) and invalid in 45/45 settings. The `dup` example of `one_file_per_book` now names a junk
    file in the second row, so it still breaks only its own rule.
  - Closed already, not added: a program that writes the sample's own correct output whatever drive it gets (quality
    −0.20 / −0.15, invalid in hard by `no_fabrication`: the hidden drive is another corpus), the baseline plus every
    other file sent to review as `UNREADABLE` (0.00 / 0.00 / 0.06, invalid under the shelving policies), an empty
    output (below 0), only the JSON, text and Markdown books filed (0.32 / 0.41 / 0.49). Partial programs that
    are not degenerate stay open on purpose: no review at all (books that cannot be filed listed as skipped; 1.0 /
    1.0 / 0.89, the `robust_solution` strategy), one code for every review book (1.0 / 1.0 / 0.95), only the
    first file of a book in its row (1.0 / 0.97 / 0.97).
- **Ablations.** Each is the reference with one switch and touches only its fact (checked: the other targets'
  diagnostics stay True). `card`, `free_reasons`, `placeholder`, `first_source` and `filename_titles` are
  plausible readings of what the agent sees, not sabotage. `free_reasons`, `placeholder`, `first_source` and
  `filename_titles` bite only through a rule (`review_reason`, `no_fabrication`, `no_guessing`): without it they
  would keep 0.92-1.00 of the credit, since they concern two books each or only the reason column. That is the
  design (the six codes route the review queue; the request's "not guessed" is a hard gate), not a misreading
  chosen to be extreme. The milder misreading of `generic_titles` (no file name is ever a title) would lose the two
  meaningful-file-name books only and not bite; the audit keeps the more common one (a file name is the fallback
  title, generic or not).
- **Never-asks solver.** Every fixed choice of the drawn rules (72 per tier with the longest limit, and the other
  limits for the first choice) was scored on the audit's settings: the means are 0.28-0.40 in easy (average 0.31;
  `robust_solution` 0.31) and 0.29-0.38 in hard (average 0.32; `robust_solution` 0.36). The best of them only fits
  the 15 sampled settings; over the uniform draw every layout, year basis, script, co-author rule and separator
  is equally good, the longest limit is tied with the middle one and ahead of the shortest (docstring), and
  since never asking stays above the baseline the credit is linear, so mixing guesses book by book gains nothing.
  Review rows need the six codes, which a guess cannot hit without risking invalidity. The reported value of
  asking (0.69 / 0.66 / 0.64) stands.
- **Diagnostics on other deliverables.** The reference is True everywhere and the baseline True wherever it files
  a book. Three gaps, now closed: a flat `library/<title>.txt` path gave `layout` None (now False: not even the
  client's folder shape), a placeholder at the right path gave `content` None (now False: no description at
  all), and an author-less book left out or listed as skipped gave `missing_author` None (now False under every
  policy). The two new shortcuts keep every library fact True, as they should (only the manifest is wrong).
- **Bound and cap.** `objective_bound` is proven (docstring, GT.md part 4): no valid deliverable can earn more than
  1 per book or 0.7 for an author-less book under the review policy, and penalties only subtract; none of the
  deliverables above exceeds it. `quality_cap` 1.0 = the median best-known quality.
- **Agent view, request, client answers.** The request is unchanged since the base commit and validate-case
  checks the agent view across settings. `CLIENT_REVIEW.md`: every quoted passage is verbatim in its locale's
  requirements.md (checked by script); numbers, codes and parameters agree across the five requirements.md
  except wording (the year examples, "nothing" written as 0, counters such as 1冊); it claims no human review.
- **Numbers.** GT.md is regenerated from the new audit; README's numbers match `dataset/audit.json` and the stored
  dataset; the commit message carries no attribution.

Findings this resolves: F5 fully (the garbage-source probe of the first review is invalid now). Everything else
in the list above keeps its status.

