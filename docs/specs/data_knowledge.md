# Data & Knowledge Work — case specs

Research points the same way across this field. AI is already deployed where text has to become structured
records (invoice capture, open-ended survey coding, abstract screening, entity resolution) and where readers
want answers grounded in a fixed corpus (Kindle's "Ask this Book", publisher and policy assistants). The
failures people report are rarely about the model itself. They come from definitions nobody wrote down: which
edition counts, which system wins a conflict, what "churn" means, which date format a supplier uses. They also
come from legal limits that differ by market: Japan's Copyright Act Art. 47-5 allows only "minor" use by
search services, Korea's 2025 AI copyright guide says a RAG corpus needs a licence, and cross-border transfer
rules differ under China's PIPL Art. 38, Korea's PIPA Art. 28-8 and Japan's APPI Art. 28. Multilingual work
adds its own problems: answers come back in the wrong language, there are no word boundaries in CJK, names are
romanized several ways, and invoices use era dates or decimal commas. Every hidden requirement below is built
on one of these gaps, and every case can be scored deterministically against a world generated from a seed.

| Role | Task type | Deliverable | Hook |
|---|---|---|---|
| BI Data Analyst ✅ | Text-to-SQL | Batch `answers.json` | (built) |
| Book QA Assistant Builder ⭐ | Cross-lingual retrieval QA | Program `answer(question)` | Korean reader asks about a book that only exists in Spanish and Japanese; reader is at chapter 5 |
| Data Migration Engineer | Entity resolution | Batch `merged_customers.csv` | Two CRMs after an acquisition; legacy encodings, pre-2014 Korean lot addresses, erased customers |
| Document Extraction Specialist | Extraction | Batch `invoices.jsonl` | Invoices from KR/JP/CN/ES/MX/US: era dates, red-letter fapiao, IRPF withholding |
| Report Automation Analyst | Data engineering | Program `build_report(data_dir, period)` | Monthly KPI pack run on hidden future months; restatements and a reorg |
| Survey Insights Analyst | Multi-label text classification | Batch `coded_responses.csv` + `topline.csv` | Five-market verbatims, net codes, raking weights |
| Research Literature Curator | Screening + record linkage | Batch `screening.csv` | Abstracts in five languages, trial-registry IDs link companion reports |

No catalog role was replaced. The six unbuilt roles each match a documented AI deployment and have a clean
deterministic ground truth.

---

### Book QA Assistant Builder — `data_knowledge/book_qa_assistant_builder`

> **Not built.** Replaced by the program case `data_knowledge/multilingual_corpus_curator` (organize a
> multilingual book folder); the research below is kept as background.

- **Why it matters** — In late 2025 Amazon shipped "Ask this Book" in the Kindle iOS app (US only). It answers
  only from text before the reader's current position, gives publishers no opt-out, and blocks copying of
  answers. Publishers now want the same thing on their own terms. The research gives two warnings. Multilingual
  RAG often answers in the wrong language or switches language mid-answer unless the prompt is engineered for
  it (Chirkova et al. 2024). Book-length QA is weak on multi-hop and late-evidence questions, and models score
  well "closed-book" on famous novels because they memorized them (NovelQA, ICLR 2025). Hence a synthetic corpus.
- **Client & request** — The digital director of a mid-size publisher with imprints in all five markets and a
  reading app: *"We want readers to be able to ask questions about our books inside the app. Here's the catalog
  export and the book files — can you build the Q&A part?"*
- **Deliverable** — Program. `solution/answer.py` with `answer(q: dict) -> dict`. The input is
  `{"qid": str, "text": str, "reader": {"book_id": str|null, "edition_id": str|null, "chapter": int|null}}`.
  The output is `{"qid", "refused": bool, "reason": "out_of_corpus"|"spoiler"|null, "answer": str,
  "citations": [{"book_id", "edition_id", "chapter": int, "page": int}]}`. Runs offline with no network calls.
  The agent may bundle indexes it built at authoring time (≤ 200 MB). Limits are ≤ 2 s per question and
  ≤ 30 min in total.
- **World & data** — The world has 24 synthetic books from 6 genres (mystery, family saga, travel memoir,
  cookbook, popular science, business handbook), 3 of which form a series. Original languages are spread evenly
  over zh/en/ko/ja/es. Each book has 1–3 translations, so about 40% of (book, language) pairs have no edition.
  Six books also have a superseded first edition. The agent receives:
  - `catalog.csv`, about 70 editions, with columns book_id, edition_id, language, title, author, series,
    volume, edition_no, status, pub_date and isbn13.
  - `books/<edition_id>.txt`, with localized chapter headings (`제3장`, `第三章`, `Capítulo 3`, `Chapter 3`),
    page markers `=== p.17 ===`, and front matter numbered i–x.
  - `glossary.csv`, the translators' term base: term_id plus names of people, places and key objects in each
    language where an edition exists.
  - `questions_sample.jsonl`, 40 questions with gold answers.

  The world keeps hidden: about 300 test questions (60 per question language, independent of the customer
  locale), each linked to a gold entity id and to evidence sentence ids.

  **Generating the corpus deterministically.** Everything comes from `rng = Random(seed)`, used in a fixed
  order. (1) For each book, build a fact graph: 6–10 characters, 4–6 places, objects drawn from a 300-item
  lexicon hand-written in all five languages ("brass compass" / "놋쇠 나침반" / "真鍮のコンパス" / "黄铜罗盘" /
  "brújula de latón"), dated events tied to a chapter index, and numeric attributes (ages, years, quantities).
  Names are generated per script from fixed syllable inventories: Hangul syllables, katakana for Japanese
  renderings of foreign names, a 200-character Han list for Chinese, and Latin syllables for en/es. Every
  Japanese alias of a foreign name contains kana and no Chinese alias does, so a script check can tell the two
  apart. (2) Each event is written with 8–12 sentence templates per language and interleaved with filler from
  a seeded bank to about 900 English-word equivalents per chapter. Near-miss distractors are planted (another
  character with a similar object) so that keyword overlap alone picks the wrong sentence. (3) Translations
  are rendered from the same fact graph with that language's templates, so facts line up across editions while
  sentences do not. (4) Superseded editions change 2–3 facts (a corrected year, a revised statistic, a renamed
  translated character). (5) Pagination is deterministic: a page break every 280 words (en/es), 600 characters
  (zh/ja) or 450 syllables (ko), plus a front-matter offset of 4–12 pages per edition, so page numbers differ
  between editions. (6) ISBNs are synthetic with valid check digits under the national prefixes
  (979-11, 978-4, 978-7, 978-84, 978-1). **Generating the questions.** Question families: single-fact 40%,
  cross-lingual (no edition in the question's language) 20%, multi-hop within a book 10%, edition-sensitive 8%,
  spoiler-position 10%, and out-of-corpus 12% (invented titles, real-world trivia, facts absent from the book).
  Each family has 4–6 paraphrase templates per language. Hidden questions draw 30% from paraphrase templates
  held out of the sample. Before a question is accepted, the generator checks that exactly one entity
  satisfies it in the current editions.
- **Hidden requirements**
  1. `answer_language` (ambiguous; scoring): answer in the question's language, not the book's or the client's.
     Names take the glossary form for that language, or the original-language form when the glossary has none.
     This is modeled on the mRAG language-drift finding.
  2. `citation_edition` (missing; scoring): cite chapter and body page of the current edition in the question's
     language when one exists, otherwise of the current original-language edition. This follows publisher
     practice of citing the reader's edition.
  3. `superseded_edition` (missing; data semantics): editions whose status is superseded (localized label) are
     never used to answer or cite. Publishers withdraw corrected editions.
  4. `reading_position` (ambiguous; business rule): `reader.chapter` is the last chapter the reader has
     finished. Content up to and including it may be used; null means no limit. This mirrors Ask this Book's
     position limit.
  5. `series_spoilers` (missing; business rule): for a series, the volumes after the one being read are beyond
     the reading position as a whole.
  6. `out_of_corpus` (missing; business rule): refuse anything not answerable from the catalog, including true
     world knowledge, with reason `out_of_corpus`.
  7. `quote_limit` (missing; business rule): the author licence allows at most 40 consecutive words (60 CJK
     characters) of book text in an answer. Paraphrase instead. This mirrors the "minor and necessary" use under
     JP Art. 47-5 and the quotation limits in JP Art. 32 and KR Art. 28.
  8. `page_numbering` (ambiguous; data semantics): a prologue is chapter 0, roman-numeral front matter is never
     cited, and a page is the one where the evidence sentence starts.
- **Rules**

| id | class | check | why |
|---|---|---|---|
| answer_contract | physical | importable; schema-valid output for every qid within the time limits; no network | the app cannot call a broken function |
| citation_exists | physical | every citation names an existing edition, and the page falls inside the cited chapter | a fabricated page reference cannot exist |
| quote_limit | contractual | longest normalized verbatim overlap with any edition < 40 words / 60 CJK chars | author licence; KR guide says RAG use needs a licence |
| no_spoilers | business_policy | for positioned questions: no citation past the position, and no gold alias of a later-revealed fact in the answer | product promise, but readers asking "who did it?" want the answer |

  Keeping `no_spoilers` costs quality: spoiler-position questions (about 10%) earn credit only for the true
  answer, so a compliant refusal scores 0 on them.
- **Objective** — Maximize the mean credit per question. Credit is 1 for an answer that contains a gold alias
  in the question's language (NFKC, casefold, punctuation stripped; numbers in Arabic or CJK numerals) and
  cites the correct edition/chapter/page. It is 0.5 for a correct answer with a wrong citation. For
  out-of-corpus questions, credit is 1 for `refused` and 0 for any answer. Refusing an answerable question
  earns 0. Reference: character-3-gram BM25 over current-edition pages within the reading position; queries
  expanded with glossary aliases in every language; the answer taken from the top sentence by the expected
  entity type and rendered through the glossary; refusal when the top score falls below a threshold tuned on
  the sample. Expected about 0.72, with headroom in multi-hop and held-out paraphrases.
- **Hard tier** — Duplicate catalog rows. A stale `catalog_backup.csv` that still marks a superseded edition
  current. One Japanese edition in Shift_JIS. An errata file in the middle of the task re-flows one
  translation (second printing, pages +2). Marketing asks for "always answer, spoilers are fine", which
  conflicts with the editor's position. Twist: one translator's glossary uses a different name for a
  character than the translated text does, and the text wins.
- **Policy & language angles** — Under `regulated_strict` the spoiler rule cannot bend and NOTES must list the
  licence checks. Under `enterprise_balanced` the agent may escalate spoiler relaxation. Under
  `startup_velocity` it may justify-and-relax. `baseline` only measures quality. Localized: chapter headings,
  status labels, page markers, titles, and name order (family name first in zh/ja/ko). Pitfalls: Korean
  particles glued to names (`리오나는`), no spaces in zh/ja, full-width digits, Spanish accents.
- **Authoring risks** — Real text would bring copyright and memorization issues, so everything is synthetic.
  Gold answers must be unique. Answers whose en/es aliases are identical accept either. Templates could be
  overfitted, which the held-out paraphrases and distractor sentences counter. Spoiler gold must be checked
  against first-reveal chapters per edition.
- **Sources**
  - https://arxiv.org/abs/2407.01463
  - https://arxiv.org/abs/2410.13716
  - https://arxiv.org/pdf/2007.15207v1
  - https://arxiv.org/html/2403.12766v1
  - https://en.eloutput.com/news/applications/Kindle%27s-new-feature-that-answers-questions-without-spoiling-the-book/
  - https://www.tomsguide.com/computing/e-readers/amazon-adds-ai-chatbot-to-the-kindle-app-which-offers-spoiler-free-answers-about-your-ebooks
  - https://www.cric.or.jp/english/clj/cl2.html
  - https://www.copyright.or.kr/eng/doc/etc_pdf/Guide_to_Preventing_Copyright_Disputes_Related_to_Generative_AI_Outputs.pdf
  - https://monolith.law/en/it/ai-governance-copyright-protection
  - https://www.law.cornell.edu/uscode/text/17/107
  - https://www.reedsmith.com/articles/entertainment-media-guide-to-ai-three-years-on/text-data-mining-in-the-eu/

---

### Data Migration Engineer — `data_knowledge/data_migration_engineer`

- **Why it matters** — Customer-data consolidation after an acquisition is a textbook MDM project. Matching
  errors cut both ways: a false merge mixes two people's personal data, and a missed merge splits one customer.
  Vendors recommend field-level survivorship over "one system wins" rules. GDPR Art. 5(1)(d) and PIPA make
  accuracy and honoring erasure legal duties, not good manners.
- **Client & request** — The COO of a fitness-and-wellness retailer that bought an online competitor: *"We need
  one customer database before the new CRM goes live next month. Can you merge the two exports?"*
- **Deliverable** — Batch. `merged_customers.csv` with columns golden_id, source_keys (`A:10023@2017-03-02;B:88812`),
  region, full_name, email, phone_e164, postal_code, address, birth_date (ISO), marketing_opt_in (0/1) and
  updated_at.
- **World & data** — 9,000 true persons in two regions per locale (ko: KR+JP; ja: JP+KR; zh: CN mainland+HK;
  es: ES+MX; en: US+CA). The agent receives `system_a_customers.csv` (6,500 rows, in-store POS since 2012, legacy
  code page), `system_b_customers.csv` (5,800 rows, web shop, UTF-8, names partly romanized),
  `address_crosswalk.csv` (KR lot-number to road-name; JP chōme variants) and `data_dictionary.md`. About 2,400
  people appear in both systems, and 4% are duplicated within one system. The world keeps the true person_id
  for every row hidden.
- **Hidden requirements**
  1. `field_survivorship` (missing; business rule): B wins email and opt-in (self-service, newer); A wins
     address and birth date (checked against ID in store). This is field-level survivorship.
  2. `consent_restrictive` (missing; business rule): if any merged record has opt-out, the result is opt-out.
     Withdrawal of consent must be honored.
  3. `legacy_encoding` (missing; data semantics): A is CP949/Shift_JIS/GB18030/CP1252, and JP rows contain
     half-width katakana.
  4. `erased_status` (missing; data semantics): A status `D9` = erased on request. Such rows must not appear
     and must not be revived through B. This is GDPR Art. 17 / PIPA erasure.
  5. `id_reuse` (ambiguous; data semantics): A reused customer ids after a 2019 purge, so the key is (id,
     created_at).
  6. `shared_email` (ambiguous; business rule): household emails are shared in A. Email alone never merges;
     name or birth date must also agree.
  7. `address_normalization` (ambiguous; calculation): pre-2014 KR addresses are lot-number (road-name addresses
     have been legal since 1 Jan 2014). JP addresses mix kanji and Arabic chōme numbers. ES/MX addresses mix
     `C/`, `Calle`, `Av.`. Matching must normalize them.
  8. `phone_e164` (missing; calculation): drop the trunk 0 and add the region's country code (KR 010… →
     +8210…).
  9. `romanized_names` (ambiguous; data semantics): B stores KR/CN names in passport romanization in
     family-given order. Match them through name readings (A has a `name_kana` column for JP).
- **Rules**

| id | class | check | why |
|---|---|---|---|
| row_coverage | physical | every non-erased source row appears in exactly one golden record | a lost customer cannot be recovered after cut-over |
| erasure_honored | physical | no D9 row or its B counterpart is present | legal erasure duty; no exception process can authorize it |
| consent_restrictive | contractual | opt_in = 0 whenever any member record is opted out | consent law and the DPA |
| no_cross_region_merge | business_policy | no golden record spans two regions | the company's residency policy is stricter than law (PIPL standard contract or APPI consent would permit it); about 3% of true persons span regions, so pairwise F1 drops |

- **Objective** — Maximize 0.7 × pairwise F1 of the clustering against the true person ids plus 0.3 × the
  accuracy of surviving field values on correctly matched clusters. Reference: blocking on normalized
  phone/email/postal+birth date, Jaro-Winkler ≥ 0.92 on normalized names, union-find, survivorship as
  specified. Headroom (about 10%) comes from typos, people who moved, and romanization.
- **Hard tier** — Duplicate rows, a stale B backup from the previous quarter, a legacy encoding (natural here),
  a corrected crosswalk arriving mid-task, and a client unavailable before the deadline. Twist: the id-reuse
  collision.
- **Policy & language angles** — `regulated_strict`: the residency rule is fixed and NOTES must document the
  erasure checks. `startup_velocity`: the agent may justify merging cross-region pairs. Localized: status
  labels, column headers, address formats, name order, and phone formats.
- **Authoring risks** — Make sure truth clusters can be separated with the data given (no identical twins
  without any distinguishing field). Keep D9 rows recognizable from the dictionary.
- **Sources**
  - https://geosurge.ai/corpus/gen-3659/customer-data-management/customer-identity-resolution-and-golden-record-strategies-for-enterprise-cdps.html
  - https://docs.redpointglobal.com/bpd/profile-unification-using-out-of-the-box-cdp-jobs
  - https://gdpr-info.eu/art-5-gdpr/
  - https://github.com/geolonia/normalize-japanese-addresses
  - https://koreascience.kr/article/CFKO201335553772233.pdf
  - https://law.asia/doing-business-in-korea-data-privacy-compliance
  - https://www.haynesboone.com/news/alerts/china-releases-new-rules-to-ease-burden-on-cross-border-transfer-of-data

---

### Document Extraction Specialist — `data_knowledge/document_extraction_specialist`

- **Why it matters** — Accounts-payable capture is one of the most widely deployed document-AI uses. Benchmarks
  such as DocILE (6.7k annotated business documents, 55 field classes, line items) show that the hard parts are
  layout and line items rather than OCR. Tax regimes differ sharply. Japan's Qualified Invoice System (since 1
  Oct 2023) requires the issuer's registration number and tax per rate (10% / 8%). Spain's VeriFactu (RD
  1007/2023) regulates billing software. China's red-letter fapiao and Korea's amended tax invoices express
  credits as negatives.
- **Client & request** — The AP lead of a trading company buying from six countries: *"Can you pull the key
  fields out of this quarter's supplier invoices so we can load them into the ERP?"*
- **Deliverable** — Batch. `invoices.jsonl`, one object per document: `{"doc_id","doc_type":"invoice|credit_note|duplicate|other",
  "status":"post|review","supplier_tax_id","invoice_number","issue_date":"YYYY-MM-DD","currency",
  "net_total","tax_total","gross_total","withholding","tax_lines":[{"rate","base","tax"}]}`.
- **World & data** — 600 documents from KR/JP/CN/ES/MX/US suppliers in all five languages regardless of the
  client locale. The agent receives `docs/<id>.txt` (OCR text in reading order), `docs/<id>.layout.json` (tokens
  with boxes and confidence) and `suppliers.csv` (master data: tax id, country, currency). The world keeps the
  true field values and document types hidden.
- **Hidden requirements**
  1. `date_formats` (ambiguous; data semantics): ES dd/mm/yyyy, US mm/dd/yyyy, JP Reiwa era (令和8年 = R8 =
     2026), CJK `2026年3月5日`.
  2. `credit_negative` (missing; business rule): credit notes (red-letter 红字, factura rectificativa,
     수정세금계산서 마이너스, 適格返還請求書) get negative amounts.
  3. `jp_rate_rounding` (missing; calculation): JP tax is rounded once per rate per invoice, not per line.
  4. `es_irpf` (missing; calculation): Spanish professional invoices withhold 15% IRPF. It goes in
     `withholding`; it is not part of tax_total and does not reduce gross_total.
  5. `decimal_conventions` (ambiguous; data semantics): `1.234,56` in ES/MX; JPY and KRW have no minor units.
  6. `duplicate_copies` (missing; business rule): re-sent copies marked COPIA/副本/사본 are `duplicate`,
     not posted twice.
  7. `tax_id_check` (missing; business rule): KR business registration numbers (10 digits, check digit), JP
     `T`+13 digits, MX RFC, ES NIF. If the checksum fails, set status review.
  8. `multi_page` (ambiguous; data semantics): continuation pages carry the same invoice number. Totals are
     taken only from the last page.
- **Rules**

| id | class | check | why |
|---|---|---|---|
| schema | physical | one valid object per doc_id | the ERP loader rejects anything else |
| arithmetic | physical | net + tax = gross within 1 minor unit; tax lines sum to tax_total | an invoice that does not add up cannot post |
| no_invalid_tax_id_posted | contractual | status=post only with a valid-checksum tax id | AP control and input-VAT deduction rules |
| reject_handwritten | business_policy | documents with handwriting (mean OCR confidence < 0.6) get status review and no fields | the AP SOP; about 5% are legitimate and lose field credit |

- **Objective** — Maximize weighted field accuracy (amounts ×2, dates and ids ×1, doc_type ×1). Review docs
  score 0 on fields. Reference: per-locale label dictionaries plus regexes, with arithmetic reconciliation.
- **Hard tier** — Duplicates, a stale supplier master, CP1252/GB18030 text, and a late requirement (MX CFDI
  UUID wanted). Twist: one supplier switches from 8% to 10% mid-quarter on mixed food/non-food lines.
- **Policy & language angles** — Under `regulated_strict` the handwriting rule is fixed. Localized: labels such
  as 合計/소계/Base imponible and the numeral conventions above.
- **Authoring risks** — The OCR noise model must leave every true value recoverable from the text. Avoid
  ambiguous dd/mm dates unless supplier country resolves them.
- **Sources**
  - https://www.nta.go.jp/taxes/shiraberu/zeimokubetsu/shohi/keigenzeiritsu/invoice_about.htm
  - https://sede.agenciatributaria.gob.es/Sede/iva/sistemas-informaticos-facturacion-verifactu.html
  - https://arxiv.org/abs/2302.05658
  - https://en.wikipedia.org/wiki/Japanese_era_name

---

### Report Automation Analyst — `data_knowledge/report_automation_analyst`

- **Why it matters** — Monthly KPI packs are rebuilt by hand in many finance teams, and automating them is a
  common analytics project. The SEC's 2020 MD&A guidance asks for a clear definition and calculation of each
  KPI, and for prior figures to be recast or the differences explained when a calculation changes. IAS 8
  requires restating comparatives for material prior-period errors. That leaves a choice between "as
  restated" and "as originally reported".
- **Client & request** — The FP&A manager of a subscription-software company in three countries: *"Automate our
  monthly KPI report. Last month's version and the raw extracts are attached."*
- **Deliverable** — Program. `build_report(data_dir: str, period: str) -> list[dict]` returns rows
  `{"metric_id","period","segment","value","prior_year_value"}` for 12 metrics × 4 segments. It is run on the
  hidden months 2026-10, 2026-11 and 2026-12.
- **World & data** — 5,000 accounts, 18 months of history. The agent receives `subscriptions.csv`,
  `invoices.csv`, `credit_notes.csv`, `accounts.csv` (with SCD2 segment history), `fx_monthly.csv`,
  `load_log.csv` (load timestamps), `kpi_report_2026-09.xlsx` and `published_snapshots/` (previous reports as
  issued). The world keeps the hidden months' extracts and the corrections.
- **Hidden requirements**
  1. `mrr_definition` (missing; calculation): MRR excludes one-time and usage fees; annual contracts count as
     ÷12.
  2. `logo_churn_base` (ambiguous; calculation): churn = logos lost in the month / logos at the start of the month.
  3. `cutoff_bd3` (missing; business rule): rows loaded after business day 3 of the next month (local holiday
     calendar: KR/JP/CN/ES/US) belong to the next report.
  4. `restatement_source` (missing; data semantics): `credit_notes` with `corrects_period` restate earlier months.
  5. `reorg_asis` (ambiguous; business rule): segments follow the current org (SCD2, as-is) for all periods
     after the July 2026 reorg.
  6. `fx_monthly_avg` (missing; calculation): convert at the monthly average rate of the period, not the
     spot rate.
  7. `internal_accounts` (missing; business rule): exclude accounts with type internal or partner_demo.
  8. `units` (missing; scoring): money in thousands, rounded half-up; ratios in percent with one decimal.
- **Rules**

| id | class | check | why |
|---|---|---|---|
| contract | physical | runs on each hidden month and returns all 48 rows | report must exist |
| definitions_documented | contractual | NOTES or docstring defines each metric | SEC KPI guidance / audit trail |
| as_originally_reported | business_policy | prior_year_value equals the published snapshot | consistent with board packs; the objective scores against restated truth, so compliance costs about 8% of PY cells |

- **Objective** — Maximize the share of cells within 0.1% of truth (restated, as-is segments). Reference: a
  pandas implementation of the definitions. Headroom comes from holiday-aware cutoffs and corrections.
- **Hard tier** — Duplicate invoice rows, a stale FX file, an encoding issue, and finance changing the churn
  definition mid-task (late requirement). Twist: a back-dated cancellation that lands after the cutoff.
- **Policy & language angles** — `regulated_strict`: no bending of as-reported. Localized: holiday calendars,
  the JP fiscal year starting in April, and number formats in the xlsx.
- **Authoring risks** — Hidden months must use exactly the same schema. Each cutoff case must be unambiguous.
- **Sources**
  - https://www.sec.gov/rules/interp/2020/33-10751.pdf
  - https://www.ifrs.org/issued-standards/list-of-standards/ias-8-accounting-policies-changes-in-accounting-estimates-and-errors/
  - https://en.wikipedia.org/wiki/Slowly_changing_dimension

---

### Survey Insights Analyst — `data_knowledge/survey_insights_analyst`

- **Why it matters** — Coding open-ended answers is costly manual work that LLMs now often do first. Ziems et
  al. find that zero-shot LLMs reach fair agreement with humans but do not beat fine-tuned coders. AAPOR's
  disclosure standards require reporting whether software or humans coded the answers, and how weights were
  built. Pew showed that the choice of weighting variables matters more than the method, and raking comes
  within 0.1–0.3 points of complex methods.
- **Client & request** — The consumer-insights manager of an appliance brand: *"Please code the open-ended
  answers from our Q3 post-purchase survey and tell us the top reasons by market."*
- **Deliverable** — Batch. `coded_responses.csv` (resp_id, codes as `;`-joined code ids) and `topline.csv`
  (market, code_id, weighted_pct).
- **World & data** — 4,000 respondents across 5 markets. The agent receives `responses.csv` (verbatims in the
  market language with some code-switching, plus age band, gender, market), `codebook.xlsx` (28 codes in 6
  nets, English examples only) and `population_targets.csv`. The world keeps the latent true codes hidden.
- **Hidden requirements**
  1. `multi_label_max3` (missing; business rule): at most 3 codes per response.
  2. `net_once` (ambiguous; calculation): a net counts once per respondent even when several of its subcodes
     apply.
  3. `other_last` (missing; business rule): 96 "other" applies only if no other code fits.
  4. `negation` (ambiguous; data semantics): "not noisy at all" is the positive quietness code.
  5. `base_definition` (missing; calculation): the base is respondents who answered. Blanks are excluded, and
     97 "nothing" stays in the base.
  6. `raking` (missing; calculation): rake to the market's age×gender margins, with weights trimmed to
     [0.3, 3].
  7. `low_base_flag` (missing; scoring): markets with an unweighted base < 50 get pct null.
  8. `pii_redaction` (missing; data semantics): verbatims containing phone numbers or emails are coded
     normally; see the rule below.
- **Rules**

| id | class | check | why |
|---|---|---|---|
| schema | physical | every resp_id is coded with valid ids | needed to tabulate |
| no_pii_in_outputs | contractual | no phone numbers or emails copied into any output file | respondent anonymity (MRS/ESOMAR, PIPA) |
| merge_small_codes | business_policy | codes < 3% in a market are reported as 96 in topline | the client's chart style; scoring compares per-code shares, so merging loses accuracy |

- **Objective** — 0.6 × micro-F1 of the codes + 0.4 × (1 − mean absolute error of weighted pct / 10). Reference:
  multilingual keyword lexicon with negation windows, plus IPF raking.
- **Hard tier** — Duplicate respondents (panel speeders), a stale codebook version, and a stakeholder adding a
  code mid-task. Twist: a Korean verbatim written in English.
- **Policy & language angles** — Localized: verbatims, code labels, and markets. Pitfalls: Japanese indirect
  negatives and Spanish double negation.
- **Authoring risks** — Phrase banks must make the latent codes recoverable. Avoid codes that overlap by
  definition.
- **Sources**
  - https://arxiv.org/abs/2305.03514
  - https://aapor.org/standards-and-ethics/disclosure-standards/
  - https://www.pewresearch.org/methods/2018/01/26/for-weighting-online-opt-in-samples-what-matters-most/
  - https://en.wikipedia.org/wiki/Iterative_proportional_fitting

---

### Research Literature Curator — `data_knowledge/research_literature_curator`

- **Why it matters** — Systematic reviews screen thousands of records. Cochrane reports that automation (the RCT
  Classifier, Screen4Me, active learning) can cut manual screening by 30% to over 90%, at a sensitivity cost of
  up to 5%, and still does not recommend automated elimination. ASReview claims savings of up to 95%. Cochrane
  says not to restrict searches by language and to link multiple reports of one study.
- **Client & request** — A hospital evidence team: *"Screen these 3,000 abstracts for our review on exercise for
  knee osteoarthritis. The protocol is attached."*
- **Deliverable** — Batch. `screening.csv` (record_id, decision include|exclude, reason_code, study_id).
- **World & data** — 3,000 records (about 120 true includes, about 40 companion reports) in five languages. The
  agent receives `records.csv` (title, abstract, journal, year, language, registry_ids text) and
  `protocol.md` (a short PICO). The world keeps true study ids and eligibility hidden.
- **Hidden requirements**
  1. `age_rule` (ambiguous; business rule): adults ≥ 50, or a mean age ≥ 50 when only the mean is reported.
  2. `design` (missing; business rule): parallel and cluster RCTs are included; crossover and "randomly
     selected" non-randomized studies are excluded.
  3. `registry_linking` (missing; data semantics): NCT, KCT (CRIS), jRCT/UMIN, ChiCTR, ISRCTN and CTIS IDs link
     reports into one study_id.
  4. `conference_abstracts` (missing; business rule): included if they report results.
  5. `retractions` (missing; data semantics): retracted records are excluded with reason R.
  6. `search_cutoff` (missing; business rule): records after 2026-06-30 are excluded.
  7. `comparator` (ambiguous; business rule): usual care or no exercise only. Exercise-vs-exercise is excluded.
  8. `multilingual_terms` (ambiguous; data semantics): 무작위, ランダム化/無作為化, 随机对照 and aleatorizado
     all mean randomized.
- **Rules**

| id | class | check | why |
|---|---|---|---|
| schema | physical | every record decided, with a valid reason code | needed for the PRISMA diagram |
| recall_floor | contractual | study-level recall ≥ 0.95 | protocol SOP; missed studies bias the review |
| nonenglish_rct_forward | business_policy | every non-English randomized record is included for full-text translation | lead reviewer's rule; costs precision on off-topic RCTs |

- **Objective** — Maximize study-level F2 × linking accuracy. Reference: multilingual keyword rules plus
  registry-ID union.
- **Hard tier** — Duplicate exports from two databases, a stale protocol v1, and the late addition of the
  comparator rule. Twist: a trial whose registry id is mistyped in one report.
- **Policy & language angles** — Localized: abstracts and reason labels. Pitfall: CJK journal names.
- **Authoring risks** — Borderline abstracts must still be decidable from the text.
- **Sources**
  - https://www.cochrane.org/authors/handbooks-and-manuals/handbook/current/chapter-04
  - https://www.prisma-statement.org/prisma-2020
  - https://asreview.nl/
  - https://www.who.int/tools/clinical-trials-registry-platform/network/primary-registries
