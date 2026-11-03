# FDE-Bench v2 — design

FDE-Bench v2 measures how well agent systems (model × harness) do forward-deployed engineering when the
**customer's language**, the **deploying company's policy** and the **realism of the engagement** change.

An FDE task here is: an under-specified customer request plus business data; hidden requirements that a
simulated client reveals only when asked; a deliverable scored by a deterministic evaluator with hard
constraints and a quality score against a reference. The repository is self-contained: harness, case
format, cases, scoring and pipelines. It has no dependency on any other benchmark's code or data.

## 1. Design goals

| Goal | How |
|---|---|
| Languages | Cases authored natively in **zh / en / ko / ja / es**, data rendered in each locale; the agent's own instruction language is a separate variable. |
| Company policies | **Policy profiles** (gates, weights, budgets, question caps, exception process) and rule classes that say which rules may bend. |
| Realistic difficulty | **easy / medium / hard** content tiers, each scored under several **rule seeds** that draw the rules' parameters from candidate pools (a ground truth per tier and rule seed, all on the same data; private seeds give answers published nowhere), plus an engagement axis with recoverable data noise and mid-task events. |
| Fair comparison | The agent's prompt and files are byte-identical in every setting, and runs are isolated so nothing that differs between settings is reachable. |
| Any model, any harness | One **OpenAI-compatible** model protocol plus vendor CLIs over a shared **MCP** client channel. |

## 2. Cases

Cases live in `cases/<field>/<role>/`: grouped by field at the top level (`cases/fields.yaml`, names in all
five locales) and titled by the role the agent plays (e.g. `finance/loan_underwriting_specialist`). The
catalog of planned cases, at most 10 per field, is `cases/README.md`. Cases are written from scratch by the
benchmark owners; one built case per field serves as an example of the format. A case that lacks a locale can still be run in it: its texts are machine-translated at run
time (cached in `.cache/`).

## 3. Native case format

```
cases/<field>/<role>/
  case.yaml                 id (= role dir), role (title), field (= parent dir), task_type, seed,
                            objective (minimize|maximize), quality_cap (optional), audited (optional),
                            deliverables, deliverable_spec, rules [{id, class, description}]
  case.py                   build_world(seed) · write_data(world, dir, lang) · reference_solution(world, dir)
                            · baseline_solution(world, dir) · score(world, submission_dir)
                            · violating_examples(world); for the ground truth audit (optional):
                            ablations · shortcuts · robust_solution · best_known_solution · objective_bound
                            · diagnose (the per-target diagnostic, computed only when asked)
                            (cases with settings: all but build_world, write_data and robust_solution
                            also take the setting)
  locales/<zh|en|ko|ja|es>/
    request.md              the client's short, under-specified request (what the agent sees)
    requirements.md         complete requirements (hidden; the simulated client answers from it)
    targets.yaml            clarification targets: the facts a good FDE must ask for
  README.md                 generated index (explain-case): the role and id, one row per language linking to
                            its docs/<lang>/ files, then dataset/answer/ with each tier's and each setting's
                            folder, and GT.md and CLIENT_REVIEW.md when the case has them
  docs/<en|zh|ko|ja|es>/    each language's documents in its own folder (en: the originals, the others their
                            translations, which validate-case requires for every English one)
    README.md               the client, data, rules and situations; reference and baseline numbers
    REVIEW.md               findings of a case review and their status (rendered in the explainer)
    explainer.html          the case's page in this language, generated (fdebench2 explain-case)
  GT.md, CLIENT_REVIEW.md   audited cases: the ground truth in five parts and what the client answers from,
                            generated from dataset/audit.json, in English (docs: outside the audit's and a
                            run's hashes, like the index README.md, everything under docs/ and the page
                            texts locales/*/summary.yaml and explainer.yaml)
  dataset/                  the generated data and answers as files (fdebench2 export-dataset):
    agent_view/<lang>/      what the agent receives, per customer locale
    hidden/                 inputs the agent never sees (a program case's hidden period or corpus)
    answer/<tier>/s<seed>/  per public setting, grouped by tier (easy/, medium/, hard/, each with the public
                            rule seeds; answer/default/ without settings): setting.json (the drawn
                            parameters, the rules and targets in force), client/<lang>/ (requirements.md
                            and targets.yaml as rendered for the setting), reference/, baseline/,
                            score.json (both objectives and qualities) and case extras
    MANIFEST.json           sha256 of every file; validate-case checks it against the generator
    audit.json              the ground truth audit (fdebench2 audit-case), outside the manifest
```

Design rules that keep scoring language-independent:

- **The world is built from the seed, never from files.** Ground truth (including any hidden future for
  forecasting cases) lives in the world. The evaluator scores against the world, so noisy or localized data
  copies can never corrupt scoring.
- **Data comes in the client's own formats.** Tables arrive the way a client exports them (CSV and xlsx,
  or a plain-text SQL dump via `casekit.write_sql`), messages as e-mails (`casekit.write_eml`, `.eml`),
  documents as folders of mixed files.
- **Data is rendered per locale.** File names, sheet names, column headers and categorical labels are
  localized; IDs and numbers are not. A Korean client sends `매장목록.csv` with `매장등급 = 프리미엄`; a Spanish
  one sends `cafeterias.csv` with `categoria = premium`.
- **Deliverables use ASCII keys and data IDs**, so one evaluator scores submissions made in any locale.
- **Quality is normalized between a baseline and the reference.** `baseline_solution` is the simplest
  sensible valid deliverable (what the client gets without an engineer: do nothing, first fit, its own
  habit); `reference_solution` is a solid deterministic heuristic. With baseline objective b and reference
  objective r, quality q = (obj − b) / (r − b): the baseline scores 0, the reference 1, and a better
  deliverable more than 1 (floored at 0, capped at 10). The baseline is exactly the zero point in every setting;
  every evaluation also reports the scale's width, `quality_span` = |r − b| / |r|. A setting where the baseline
  comes within 5% of the reference (span < 5%, `cases.MIN_QUALITY_SPAN`) is a case defect the validator reports,
  because there a 1% objective difference moves quality by 0.2 or more: the fix is a stronger reference or a
  baseline that is really the client's way, never a moved zero point. Without a
  usable baseline (none, or one that fails on a generated world) q is the plain ratio obj / r (r / obj when
  minimizing); `quality_anchor` says which, and `quality_ratio` is always reported. A non-finite objective is
  invalid. The reference is not the ceiling: the composite gives full credit at
  `quality_cap` (the policy's, 1.5 by default, or the case's when it knows its best solution), so headroom
  above the reference counts and a degenerate valid deliverable earns nothing.
- **Rules carry a class** (`physical`, `contractual`, `business_policy`). The evaluator reports violations by
  rule id; relaxing a rule is a scoring parameter (`evaluate(..., relaxed={...})`), so no per-case hooks.

`fdebench2 validate-case <dir>` enforces the contract before a case is used:

- all 5 locales present with the same target ids (in the same order), the same `{{param}}` placeholders
  and the same sequence of setting markers, in the right script;
- data renders deterministically in every locale with no untranslated labels, and byte-identically in two
  processes with different `PYTHONHASHSEED`s;
- the stored `dataset/`, the explainer pages `docs/<lang>/explainer.html` and the index `README.md` match what
  the generator produces now; no TODO is left; no document is left at the case root from the layout before
  `docs/<lang>/` (`README.<lang>.md`, `REVIEW*.md`, `explainer*.html`: the validator names each one's new path),
  and no `dataset/gt/` from the layout before `dataset/answer/<tier>/s<seed>/`;
  `docs/en/README.md` and `REVIEW.md` have their translations in every other `docs/<lang>/`;
- the reference scores validity 1 / quality 1.0 and an empty submission is invalid;
- every case has a baseline, valid and strictly worse than the reference in every setting;
- every case has a plain-words summary in every locale (`locales/<lang>/summary.yaml`: what the AI has to do,
  what it is given, what it must ask, what makes it score 0, how quality is measured, what each difficulty asks
  for), shown at the top of its page, with the same number of items in every locale;
- every rule has an example that breaks exactly that rule, and that becomes valid when a non-physical rule
  is relaxed;
- the case still works on world seeds 1, 2 and 3 (`--world-seeds` chooses others, `--no-world-seeds` skips);
- a case with `audited: true` has a fresh ground truth audit that passes (Ground truth audit, below).

Warnings, which do not fail validation: two tiers whose references are byte-identical or score as each
other's reference; a parameter that varies in a tier where nothing in force uses it; a lower-tier binding
finding listed in `validate.OPEN_BINDING_FINDINGS` (Settings, below); a number in a rule
description that neither the requirements nor the data state; a `name (ID)` in a locale's texts whose ID's data
rows never mention that name; a setting whose quality scale is narrower than 5% that `validate.OPEN_NARROW_SCALES`
lists as known and open (otherwise it fails). Notes give each setting's baseline/reference objective ratio.

### Settings: one world, tiers × rule seeds

A case may declare **settings**: three content tiers (`tiers:` easy / medium / hard) and rule parameters that a
**rule seed** draws from candidate pools (`params:`), the way a world seed draws the data. A setting is
(tier, rule seed), and every setting is a ground truth for **one** world:

- **The agent's view never changes.** `build_world(seed)` and `write_data(world, dir, lang)` never see the
  setting, and `request.md` has no setting-specific text, so the data, the request and the prompt are
  byte-identical in every setting. Only the hidden requirements (which the simulated client answers from)
  and the evaluator differ: the agent has to find out from the client which rules apply this time.
- **A tier** decides which rules apply and how strictly the deliverable is scored: easy is the core problem,
  medium adds domain rules, hard adds the uncertain or adversarial parts. The data is the same, so a lower
  tier's requirements say which parts of it are out of scope this round.
- **A rule seed** draws the rules' hyperparameters (caps, thresholds, which item a rule targets, scoring
  weights), e.g. which clinic is closed on a holiday or how many interpreters there are, each parameter
  independently from its candidates. A tier may have its own, harder candidates. Different parameters lead to
  different correct solutions, so a solution tuned to one draw fails or scores worse under another. The
  case's **public panel** (`rule_seeds:`) is stored in `dataset/answer/<tier>/s<seed>/`, shown in the explainer
  and validated; any other int is a **private seed**, a fresh draw of the same candidates whose answers are
  published nowhere.

**case.yaml**

```yaml
tiers: {easy: text, medium: text, hard: text}
params:                                   # the rule parameters a rule seed draws
  <name>:
    values: [v1, v2, v3]                  # one pool for every tier, or
    values: {easy: [..], medium: [..], hard: [..]}   # a pool per tier (harder candidates in harder tiers)
    labels: {<value>: {zh: .., en: .., ko: .., ja: .., es: ..}}   # optional wording of a code value per locale
rule_seeds: [1, 2, 3]                     # the public panel; any other int is a private seed
```

Candidates are strings, numbers or booleans (quote a date). With `labels`, every candidate needs a wording in
all five locales.

**The draw.** For parameter `name`, rule seed `s` and tier `t`, with `pool` the parameter's candidates in `t`:
`value = pool[random.Random(f"{case id}|{name}|{s}").randrange(len(pool))]`, where the case id is
`<field>/<role>`. The position does not depend on the tier, so a shared pool gives the same value in every
tier (and pools of the same size the same position), unless `admissible` rejects the draw in one tier only.
Each parameter is drawn on its own: adding a parameter or changing one pool leaves the others' draws as they
were. Two optional hooks in case.py shape it:

- `derive_params(params, tier) -> dict`: extra keys computed from the drawn values (e.g. the period dates of
  a fiscal year from its first month). They may not replace a drawn key. A derived value may be a dict keyed
  by the five locales; `{{name}}` then words it per locale.
- `admissible(params, tier) -> bool`: given the drawn and derived values, False rejects the combination.
  Every parameter is then drawn again with the salt k = 1, 2, … (`Random(f"{case id}|{name}|{s}|{k}")`),
  deterministically, at most 100 times before the rule seed is an error.

**The setting in code.** `reference_solution`, `baseline_solution`, `score` and `violating_examples` take a
`Setting` as their last argument: `setting.tier`, `setting.rule_seed`, `setting.at_least(tier)`,
`setting["name"]`, and `setting.params`, the full dict (drawn and derived values). `setting.label` is
`easy/s1`, `setting.folder` its folder in `dataset/answer/` (`easy/s1`) and `setting.slug` the flat
`easy_s1`; the validator's one-parameter variations carry the change in the
label (`easy/s1[cap=5]`), so a case may cache per label. case.py reads its setting only from the `Setting`
it is given, never from a fixed list of settings: anything calibrated across settings (a budget that must be
feasible in every setting) is computed over the candidate pools, since a private seed may draw any admissible
combination. `NativeCase.at(tier, rule_seed)` is the case in one setting, `settings()` the tiers × public rule
seeds, `rule_seeds` the panel, `rule_seed` the current seed (None for a case without settings),
`drawn_params` the drawn values and `param_candidates` the pools; `with_world_seed(seed)` keeps the setting.

**Texts.** Requirements and targets insert parameters (drawn or derived) as `{{name}}` (worded by `labels`
when the parameter has them), and mark passages with `<!-- tier: medium hard -->` … `<!-- /tier -->` and
`<!-- when: name=v1,v2 -->` … `<!-- /when -->`, kept when the parameter's value, as a string (YAML's `true`,
`false`, `null` for those), is listed; when-blocks may nest. Rule descriptions may use both too. Rules in
case.yaml and targets in `en/targets.yaml` carry `tiers: [...]` and `when: {name: [values]}` (every named
parameter must have one of its values; other locales' targets.yaml give only `id` and `text`). Every locale has
the same `{{…}}` placeholders and the same sequence of tier and when markers.

**Evaluation.** The difficulty picks the tier; a campaign runs each case's public panel (`rule_seeds:
public`, the default) or the rule seeds it lists (`rule_seeds: [101, 102, 103]`, private seeds), at the
defaults level or per experiment. Run keys carry `r-<seed>`; result.json stores `tier`, `rule_seed` and
`params` (the drawn values). The report's difficulty table is per tier: a case's cell is the mean over its
rule seeds of the mean over each seed's runs, columns are case-macro means, and "all valid" is the share of
runs (the same variant apart from its rule seed) that are valid under every rule seed of the tier; the other
tables weigh a case's rule seeds the same way. A settings table lists each (case, tier, rule seed) with its
drawn parameters, mean final score and valid runs. A single run (`fdebench2 run`, `Bench.run`) without a rule
seed runs the case's first public one, and its key says so; re-scoring a run whose stored parameters are no
longer what its rule seed draws (the candidates changed) is refused.

**Dataset.** `dataset/answer/<tier>/s<seed>/` for every public setting, grouped by tier (the tier's folder
holds one folder per public rule seed, as in the label `easy/s42`; a case without settings has
`dataset/answer/default/`). Each folder bundles everything that defines the setting's answer:

- `setting.json` = `{tier, rule_seed, params: {drawn values}}` (plus `derived` when the case derives values),
  `rules` (the rules in force: `id`, `class` and the English `description` as rendered for the setting) and
  `targets` (the ids of the targets in force);
- `client/<lang>/requirements.md` and `client/<lang>/targets.yaml` in all five locales: what the client knows
  in this version (`case.at(tier, seed).requirements(lang)`, and the targets in force with `id`, `kind`,
  `domain` and their rendered `text`);
- `reference/`, the reference deliverable (quality 1), and `baseline/`, what the client's own way produces
  (`baseline_solution`, quality 0);
- `score.json` (both objectives and qualities) and whatever case.py `write_ground_truth(world, dir, setting)`
  adds (expected tables or outputs).

`MANIFEST.json` covers every file; `validate-case` regenerates the dataset and compares, and reports a
`dataset/gt/` left from the layout before `dataset/answer/` (export-dataset removes it).

**Validation.** `validate-case` checks every public setting (tier × public rule seed), computing each
setting's reference once and reusing it in every check: the reference is valid at quality 1.0 and scores the
same twice, the baseline is valid and worse, an empty submission is invalid, every rule of the setting has an
example that breaks exactly it, request.md has no setting markers, and the agent's prompt and workspace are
byte-identical in every setting. It checks `params:` (a non-empty pool per tier, scalar candidates, labels for
every candidate in every locale), `rule_seeds:` (distinct ints), that every public setting draws, that
`derive_params` works on every combination of a tier's candidates (a private seed may draw any of them), that
every candidate is admissible with some combination of the others, and that `when` conditions and markers (in
requirements, target texts and rule descriptions, balanced) name parameters and candidates. **Parameter
binding**, in every tier where a parameter has 2+ candidates: take the first public seed's setting s in that
tier and, for each other admissible candidate v in turn, s' = s with only that parameter set to v (derived
values recomputed), until one binds. The parameter binds in that tier if the reference of s is invalid under
s', or its objective under s' differs from its objective under s by at least 1% (relative), or the reference
of s' scores at least 1% better than the reference of s under s'. The references of the public settings are
the ones the other checks wrote and scored, so a tier costs only the variations it tries. A parameter that
binds in no tier, or not in the highest tier where it varies, is an error ("parameter X changes nothing").
One that does not bind in a lower tier whose hidden texts state it (the requirements, targets or rules of s
and s' differ there) is an error too: the client tells the agent a value that changes nothing. One that varies
in a lower tier where nothing in force uses it (the texts read the same under every candidate) is a warning:
a single candidate in that tier would say so.
A reference of s' that is not valid under s' is an error when the check gets that far (a private seed can
draw that combination). Lower-tier findings the built cases had when the check became per tier are listed in
`validate.OPEN_BINDING_FINDINGS` (case, parameter, tier, and the world seeds where one was found only on some
worlds) and reported as warnings until their owners decide; any other one, in another tier or on another
world, fails. The
validator also warns when the public panel shows only one value of a parameter whose pool has 2+ values, when
no parameter has two candidates at all, and when two tiers lead to the same answer. The world-seed check
(`--world-seeds`) repeats the reference, rule-example and binding checks on other worlds with the public rule
seeds. Cases without settings are the same problem at every difficulty.

**Rule sets are gone.** The fixed rule sets A / B / C that rule seeds replaced are no longer read: a
case.yaml with `rulesets:` does not load (the error says to declare `params:` and `rule_seeds:`), and
`validate-case` names any `param_labels:`, `rulesets:` on a rule or target, or `<!-- ruleset: ... -->` block
with the rule-seed form to use instead (`params.<name>.labels`, `when: {name: [values]}`,
`<!-- when: name=v1,v2 -->`). A run set up with a rule set cannot be re-scored; run it again.

### Program deliverables

A case with `deliverable_type: program` and `entrypoint: solution.py:decide` asks for code, not a file of
answers: the agent delivers a `program/` directory (entry file plus any helpers or model files), and the
case's `score()` calls `casekit.run_program(submission_dir, ENTRYPOINT, hidden_inputs)`. The function is
called once per hidden input, in order, in one process (so a program may keep state), and returns per-input
outputs or errors. Two variants:

- `casekit.program_session(...)`: one input at a time, each built after seeing the previous output, in the
  same process (a trading strategy whose next day depends on its own orders and fills).
- `run_program(..., input_dir=..., output_to=...)`: the program gets a copy of a hidden folder and an empty
  output folder (`"$INPUT_DIR"` / `"$OUTPUT_DIR"` in the inputs), e.g. `organize(corpus_dir, out_dir)`.

The program never runs inside the scorer. `fdebench2/program.py` starts `program_host.py` in a separate
process that speaks JSON lines over a pipe; whatever the program prints cannot reach the protocol stream.
Each call has a timeout, the whole run has a wall-clock limit and a memory cap, and a crash, a timeout or a
non-JSON output costs only that input (a program that cannot load is fatal). Two runners:

- `local` (development): a private copy of the program directory, minimal environment, `RLIMIT_AS`, and no
  network via `unshare -n` where available. The program can still read the filesystem.
- `docker` (campaigns; chosen automatically under a docker sandbox): `--network none`, memory and CPU limits,
  and only the program directory (read-only) and the host script mounted.

The agent is shown the entry point and `deliverable_spec` as a "Program interface" block in every condition:
an interface is a contract, not a hidden requirement. (A batch case's `deliverable_spec` is shown only to the
extractor; the agent chooses its own format.) Docker program containers are named and removed with
`docker rm -f` on a timeout. Program deliverables are collected from the workspace as the directory holding
the entry file (without `data/` and `inbox/`) and are never reshaped by the extractor model, since rewriting
code would mean re-solving the task. The validator requires the reference to write `program/`, checks that `ENTRYPOINT`
matches `case.yaml`, and checks that scoring is deterministic.

### Ground truth audit

The ground truth (GT) of a setting describes acceptable behaviour, with the reference as supporting evidence, in
five parts, and `fdebench2 audit-case` (`fdebench2/audit.py`) measures each:

1. **Client facts** (the targets): each must matter. For every target in force, a deliverable that misreads only
   that fact and is otherwise as good as the reference (an *ablation*) must lose credit.
2. **Validity checks**: the rules and mandatory outputs (hard gates), checked as before.
3. **Objective**: costs and benefits, including uncertainty.
4. **Reference and bounds**: a reproducible solution plus evidence of how close it is to the best achievable.
5. **Diagnostic cases**: inputs or checks that tell a correct implementation from a shortcut.

**Hooks** (case.py, all optional; a case with settings gets the `Setting` as the last argument, except
`robust_solution`, which gets the tier and its candidates instead and never the setting):

- `ablations(world) -> {target_id: fn(out_dir)}`: for each target that is not a single drawn parameter, the
  reference with one switch flipped: the most natural wrong reading of the agent-visible data, not sabotage. Only
  targets in force in the setting.
- `shortcuts(world) -> {name: fn(out_dir)}`: degenerate strategies that skip what the case tests (refer every
  borderline application, leave a mandatory table empty, ignore the uncertainty, copy the data through); the
  function's first docstring line describes it (in English; `shortcuts: {name: text}` in
  `locales/<lang>/explainer.yaml` words it for that language's explainer page).
- `robust_solution(world, out_dir, tier, candidates)`: the solver that never asks. It sees only what the agent
  sees and the most natural reading of every fixed hidden fact, and writes the one deliverable that does best on
  average over the tier's possible settings (`candidates` = the tier's pools), e.g. by planning for the strictest
  candidate of each rule. A genuine, strong attempt.
- `best_known_solution(world, out_dir)`: a stronger, possibly slow solver (local search, a MIP with a time limit,
  oracle sizing); `objective_bound(world) -> float`: a proven bound (a lower bound on cost when minimizing, an
  upper bound when maximizing), e.g. an LP relaxation or perfect-information sizing.
- `score()` may add `"enforced": {target_id: True | False | None}` (and `"evidence": {target_id: str}`): does the
  deliverable implement this fact (None: not applicable or not determinable)? It is computed for valid and invalid
  deliverables alike whenever the deliverable can be read; a program case computes it from hidden diagnostic
  inputs where only that fact decides the output, in the same program run as scoring. `evaluate()` passes it
  through (not on a fatal deliverable).
- `diagnose(world, submission_dir, scored) -> {"enforced": {...}, "evidence": {...}}` (with settings
  `diagnose(world, submission_dir, setting, scored)`): the same maps, computed lazily, for a diagnostic too slow
  to run on every evaluation (e.g. the regret of the deliverable's plan against the reference planner's plan for
  each misreading). `scored` is `score()`'s raw result, so a program case can read what its run recorded: it may
  put a private trace under a key such as `"trace"`, which `evaluate()` never copies to its output (only the
  keys it names are copied). `evaluate(..., diagnose=True)` calls the hook on every readable deliverable, valid
  or not (never on a fatal one), and merges its maps over `score()`'s (the hook's value wins for a target both
  give); a hook that raises never stops scoring, the result's `diagnose_error` says why. Only a run's scoring
  (`runner.Bench.score`, for the target funnel) and the audit ask for it. The validator never does, and the
  audit diagnoses the reference, baseline, ablations, shortcuts and best known solution in their setting and
  `robust_solution` in every setting of its tier, but none of the other cells of its value-of-information
  matrix, which needs only credit.

A target whose fact is exactly a drawn parameter's value carries `param: <name>` in `en/targets.yaml` (read from en
only, like `kind` and `domain`; it must name a declared parameter): the generic parameter ablation then covers it.

**What is measured.** Per tier: the public panel (a combination two seeds draw counted once) plus up to
`AUDIT_COMBOS` (12) admissible combinations of the tier's candidates, built with `with_params` and taken in the
order of sha256(case id | tier | values), so no private seed's draw is exposed. The public world is used unless a
world seed is given. Credit = 0 if invalid, else the quality score clipped to [0, 1]; damage = 1 − credit.
A combination whose reference or baseline raises or is not valid is skipped and reported (`invalid_reference`,
`invalid_baseline`: a rule seed can draw it), and drawing goes on until `AUDIT_COMBOS` combinations are measured
or as many have been skipped; another value of a `param:` target whose reference raises is reported the same way.

- **Ablations.** A `param:` target's ablation in setting s is the reference of `s.with_params(p=v)` for each other
  admissible candidate v, scored under s (worst, best guess = the least harmful v, mean); another target's is the
  `ablations()` deliverable (also used for a `param:` target whose parameter has no other candidate in that tier).
  A target **bites** in s when its ablation loses at least `ABLATION_MIN_DAMAGE` (0.10: a tenth of the way from
  the client's own way to the reference), on the best guess for a `param:` target: an agent that guesses wrong but
  sensibly. The diagnostic agrees when the reference's `enforced[t]` is True (or None) and every ablation
  deliverable that bites (invalid, or losing at least `ABLATION_MIN_DAMAGE`) has it False (or None when the case
  has no diagnostic for t). A setting where no ablation deliverable bites does not count: a harmless wrong value
  may give the reference's own deliverable, which a correct diagnostic calls enforced.
- **Shortcuts** are **closed** in s when invalid or at quality at most `SHORTCUT_MAX_QUALITY` (0.5).
- **Value of information** per tier: every candidate deliverable (each measured setting's reference, "right for one
  possible client"; the baseline of the tier's first setting; `robust_solution`) is scored in every setting of the
  tier. `never_asks_params` is the best mean credit of the references and the baseline, which know every fixed
  fact, so `voi_params` = 1 − it is the value of the drawn parameters; `never_asks` is `robust_solution`'s, so
  `voi` = 1 − it is the value of everything the client knows (the reference, the oracle, has credit 1).
- **Reference and bounds** per setting: the reference and baseline objectives and `quality_span`, the best known
  objective, its quality and its enforced map, the bound and its normalized value (bound − base) / (ref − base),
  and `gap_to_bound` = |bound − ref| / |ref|.
- **Diagnostic reliability.** A run's "enforced" stage comes from the diagnostic applied to the agent's
  deliverable, which is neither the reference nor an ablation, so separating those two is not enough: a
  diagnostic that compares against the reference within a tight tolerance calls most other good deliverables
  wrong. Three checks look at other deliverables. The best known solution is built with full knowledge of the
  setting, so a correct diagnostic calls it enforced (True or None) on every target in force: any False on a
  valid best known solution is a false negative (`diagnostic_false_negative`, per target). Specificity: an
  ablation misreads only its own target u, so for each deliverable of it that bites, the other targets in force
  whose enforced is False on it are listed in the row's `cross_flags`; an ablation that flags other targets in
  more than half of the settings where some deliverable of it bites is a `cross_flags` warning (only a warning,
  since facts can interact). `diagnostic_profile` counts, per target, the settings where the baseline (each
  setting's own) and `robust_solution` (its tier's) are called not enforced, of those where the target is in
  force and diagnosed: informational, as neither is built with full knowledge. A `diagnose()` that raises is
  recorded in `diagnose_errors`.

**Stored audit.** `audit-case cases/<field>/<role> [--world-seed N] [--combos N] [--no-write]` prints a report and
writes `dataset/audit.json` (public world only; with `--world-seed` it prints only) and the explainer pages, which
then show the section "Evidence the facts matter". Its `fingerprint` is a sha256 over `AUDIT_VERSION`, `audit.py`
and every file of the case except its docs (`cases.is_case_doc`: the index `README.md`, everything under `docs/`
(READMEs, REVIEWs and explainer pages in every language), `GT.md` and `CLIENT_REVIEW.md`, which are generated from
`audit.json` and would otherwise make every
audit stale the moment they are written, `locales/*/summary.yaml` and `explainer.yaml`) and `dataset/`: case.py,
case.yaml, every locale's `request.md`, `requirements.md` and `targets.yaml`, and the reference programs case.py
copies or imports. case.yaml counts without `audited` and `quality_cap`, which change what validate-case
enforces, not what the audit measures, so they can be set after the final audit run without running it again.
`export-dataset` never runs the audit (too slow) and keeps a stored one; the dataset manifest leaves it out, and so
does a run's fingerprint (with the docs), so `audit-case` never makes stored runs stale.

**Audited cases.** A case opts into enforcement with `audited: true` in case.yaml; validate-case then fails it when
`dataset/audit.json` is missing or stale, the reference or baseline fails in a measured combination, a target in
force has no ablation, a target bites in no measured setting of a tier where it is in force, a diagnostic exists
but does not separate the reference from an ablation that bites, a diagnostic calls a valid best known solution
not enforced (`diagnostic_false_negative`, keyed by target), `diagnose()` raised in some evaluation, a shortcut is
open in some setting, `voi` < `VOI_MIN` (0.10) in a tier or `robust_solution` is missing, neither
`best_known_solution` nor `objective_bound` exists, or `quality_cap` is unset or below the median best known
quality. It warns when a target bites in fewer than half of the settings where it is in force (but at least once:
never is a problem), when an ablation flags other targets in more than half of the settings where it bites
(`cross_flags`), when `voi` < 0.30 in a tier, and when a target has no diagnostic. `validate.OPEN_AUDIT_FINDINGS`
(case, kind, key) turns a known problem into a warning, like `OPEN_BINDING_FINDINGS`; waiving a stale audit waives
only that, as the stored audit's own findings still count. Every other case is measured on request only: the
validator neither runs nor requires the audit, and reports a stored audit that has gone stale as a warning. Three
cases are audited: procurement (`manufacturing/procurement_specialist`), loan underwriting
(`finance/loan_underwriting_specialist`) and the multilingual corpus curator
(`data_knowledge/multilingual_corpus_curator`).

**Three stages per target in a run.** With the client's answers, each clarification judge answers one question per
target: was it **revealed** (a quote from the client's replies that states it, volunteered or asked for) and was it
asked for (which specific questions)? A target is revealed when a majority quote a passage found verbatim
(whitespace-normalized) in some reply, and **learned** (covered, as Ask-F1 counts it) when a majority also cite a
specific question from a round whose answer holds the quote. result.json records `targets: {id: {revealed,
learned, enforced}}` (enforced from the evaluator, which scores a run with `diagnose=True`, so `diagnose()` runs
too; None where a stage was not measured), and the report has a target funnel per case: the share of runs where
each target was revealed, learned and enforced, and enforced given learned or not. The enforced column is only as
good as the diagnostic is on arbitrary deliverables, which is what the audit's diagnostic reliability checks
measure.

## 4. Architecture

```
                         cases/<id>  (5 locales)
                                         │
          ┌──────────────── transforms (fdebench2/transforms) ────────────────┐
          │ language: pick the customer locale; agent instructions in agent   │
          │           locale; all generated messages from a 5-locale catalog  │
          │ policy:   profile + agent-visible brief                           │
          │ setting:  difficulty (tier) × rule seed → hidden reqs + evaluator │
          │ engagement: condition · persona · data noise · scheduled events   │
          └──────────────────────────────┬────────────────────────────────────┘
                                         ▼
                 run_dir/  variant/variant.json   workspace/ (agent sees only this)
                                         │
       ┌─────────────────────────────────┼──────────────────────────────────┐
       ▼                                 ▼                                  ▼
 reference harness              Session (client, events,           CLI harnesses
 OpenAI Chat Completions        exceptions, transcript.jsonl)       Claude Code · Codex ·
 tool loop, any model  ───────▶  in-process  ◀── MCP bridge ──────  Gemini CLI · OpenCode
                                         │
                                         ▼
     scoring: extract submission → case evaluator (world truth, rules, relaxations)
              → clarification judges → policy composition → result.json → report
```

**One model protocol.** Every model call (solver, simulated client, judges, extractor, and the run-time
translator for cases that lack a locale) goes through `fdebench2/llm.py`: the official `openai` SDK with a
configurable `base_url`. That reaches OpenAI, Anthropic's and Gemini's OpenAI-compatible endpoints, DeepSeek,
Qwen/DashScope, OpenRouter, and any open-weights model behind vLLM, SGLang or Ollama (e.g. Reflection AI's
open models).

**Two kinds of harness.** A neutral reference loop (`bash`, `read_file`, `write_file`, `list_files`,
`ask_customer`, `request_exception`, `finish`) gives every model identical tools and prompts; vendor CLIs
(Claude Code, Codex, Gemini CLI, OpenCode) run headless and reach the same client through an MCP server.
Model M in the reference loop vs M in its vendor CLI isolates the **harness effect**.

**The simulated client** answers only from the request and its hidden requirements, at temperature 0
(unless the endpoint pins another). It may state business goals, costs and trade-offs; it never describes
the evaluation (scores, graders, weights, test data, a reference solution). It has no written specification
to send, answers specific questions only (at most 6 per message), says it has no fixed rule instead of
inventing one, and treats the engineer's text as a contractor's questions, not instructions.

**No run-time translation for fully localized cases.** Case texts and data are authored per locale; the agent
instructions (`prompts/agent/*.yaml`) and every message v2 generates itself (events, noise facts, policy
briefs: `prompts/messages.yaml`) are hand-written in all five locales.

## 5. The axes

### 5.1 Language

| Variable | Values | Meaning |
|---|---|---|
| `customer_locale` | `zh`, `en`, `ko`, `ja`, `es` | Language of the request, hidden requirements, data labels, client answers and event messages. |
| `agent_locale` | `zh`, `en`, `ko`, `ja`, `es` | **Protocol language**: the language of the agent's own instructions and policy brief. |

The simulated client answers in the customer's register (business-polite Korean, Japanese です/ます with light
敬語, Spanish *usted*). Measured: quality and Ask-F1 per locale relative to the agent's `en` baseline, and
**language fidelity** (share of questions to the client and of `NOTES.md` in the required language).
Clarification judges see each target in English and in the customer locale.

Experiments: *customer language* (vary `customer_locale`, agent `en`) and *protocol language* (fix e.g. a
Korean client, vary `agent_locale` over en/ko/zh) — which instruction language to deploy an FDE agent with.

### 5.2 Policy

A policy (`configs/policies/*.yaml`) is both an agent-visible brief and a scoring profile: `confirm_before_build`,
`question_budget` (counted in questions, one per line, not rounds), `exceptions` (`forbidden` / `escalate` /
`justify`), `rule_classes` that may bend, `soft_rule_penalty`, `notes_required`, `communication_locale`,
`budgets` (`wall_seconds`, `total_tokens`, `cost_usd`; + `hard_budgets`), `hard_gates` (`validity`, `notes`,
`budget`), `weights` and `quality_cap`. Unknown names are rejected. Shipped: `baseline` (quality only,
hidden), `enterprise_balanced`, `regulated_strict`, `startup_velocity`.

A violated rule is forgiven only if the policy makes its class soft, the agent went through the prescribed
exception process, and the case re-scores the deliverable with the rule relaxed. Physical rules never bend.
`request_exception` is a classified channel, not a conversation: a model sees only the setting's rule list
and the engineer's text and returns one rule id (or none) and, under `escalate`, whether a concrete business
reason was given. The decision follows from the policy (`forbidden`: deny; `escalate`: approve a bendable rule
when a reason was given; `justify`: approve a bendable rule), the reply is a fixed localized template naming
the rule id, an approval covers only that rule, and the first decision on a rule is final. Under `escalate` a
request costs a question round and needs a reachable client; under `justify` it is a record and works in
every condition.

### 5.3 Difficulty and rule seeds

`difficulty` (easy / medium / hard) picks a case's content tier and `rule_seed` draws its rule parameters
from their candidates (§3, Settings). Neither changes what the agent sees. Campaigns run several rule seeds
per difficulty, each case's public panel (`rule_seeds: public`) or private seeds (`rule_seeds: [101, 102,
103]`), and report their mean, so a difficulty column is the average over several ground truths of the same
data. Cases without settings run the same problem at every difficulty.

### 5.4 Engagement

How the work is handed over, kept separate from difficulty so that a difficulty comparison holds the
agent's prompt fixed (`configs/engagement.yaml`):

| Knob | `full_spec` | `standard` (default) | `messy` |
|---|---|---|---|
| Condition | `full`: complete requirements given | `interact_req`: must clarify first | `interact_req` |
| Client persona | cooperative | default | busy: terse; vague questions get vague answers |
| Question rounds | 30 | 30 | 15 |
| Data noise | none | none | duplicate rows, stale backup file, legacy code-page encoding (GB18030 / CP949 / Shift_JIS / CP1252 by locale) |
| Events | none | none | stakeholder conflict, client unavailable, data correction, late-remembered requirement, deadline pulled in |

Everything in `messy` is **recoverable**: noise touches only the agent's copy (scoring uses the world),
the client knows the fact that undoes each noise op (it becomes an extra clarification target), a non-owner
stakeholder's conflicting message is resolvable by asking the client, and a corrected file arrives mid-task.
Noise and events are seeded by the engagement (`noise_seed`), never by the difficulty or rule seed: the
volunteered requirement is the same target in every setting. What the client knows about an event reaches it
only when the event fires, and inbox messages have neutral names (`inbox/NN_message.md`).

### 5.5 Isolation

Comparisons are fair only if the agent cannot see what differs between settings. Campaigns default to
`isolation: strict`: every run uses the docker sandbox, which mounts a copy of the run's workspace staged in a
randomly named folder at `/workspace` (the request and data, identical in every setting), so nothing inside
the container, `/proc/self/mountinfo` included, names the case or setting. Containers run as the host user. A
vendor CLI runs inside the container (`docker/Dockerfile.agent`) with only its own API key and base URL, and
reaches the client over HTTP on the host with a per-run bearer token. After the run the host removes every
symlink and special file from the workspace before anything reads it, collection never follows links, and
the extractor has no shell and sees only the agent's own files. Network egress stays on (model APIs); an
egress allowlist would need a proxy. `isolation: off` allows the local sandbox for development.

## 6. Scoring

```
final = 0                                          if a hard gate fails (validity always; notes, budget if set)
      = clip( Σ wᵢ·cᵢ / Σ wᵢ − penalties, 0, 1 )   over the components that apply
```

| Component | Definition |
|---|---|
| quality | min(max(q, 0), cap) / cap with q the normalized quality (baseline 0, reference 1) and cap the case's or the policy's `quality_cap`; 0 if invalid |
| clarification | Ask-F1 over case + noise targets (majority vote of a judge panel; a covered vote must quote the client's answer and cite the question that asked for it); only if the client was reachable |
| communication | mean of language fidelity (questions, NOTES.md) and NOTES.md presence |
| efficiency | per budget: 1 − ½·used/budget, 0 once over budget |

Reported per cell: final, quality (normalized, and the plain ratio to the reference), validity rate, DSR
(quality ≥ reference), "all valid" (every seed and trial of a case valid), Ask-F1, with 95% case-bootstrap
intervals. Case-macro averages; deltas within one agent against its baseline cell. The difficulty table has
one column per difficulty, each the mean over the rule seeds run, with "all valid across rule seeds": the share
of runs (the same variant apart from its rule seed) valid under every rule seed of the tier. With `trials` > 1,
pass^k is the τ-bench estimator C(c, k) / C(n, k) over
repeated trials. Every run has a status (ok, invalid, agent_error, timeout, extract_failed, harness_error,
infra_error); harness and infrastructure errors are listed apart and never averaged in as zeros. Cost
columns give tokens and dollars per run for the solver, client, extractor and judges (a CLI solver's own
tokens are not parsed yet). A target funnel per case follows each client fact through the runs: revealed,
learned, enforced (§3, Ground truth audit); a target no run measured any stage of is left out. A stored result
is reused only under the same fingerprint (case files except the docs and the stored audit, policy, engagement,
model configs, agent, sandbox, framework version). The case files include the stored `dataset/`: a run never
reads it, but it changes whenever the data or answers the case generates do, framework changes included, so a
re-export that changes it (a new layout of `dataset/answer/`, for instance) runs the case's stored results again.

## 7. Status

- Harness, transforms, scoring, MCP bridge, campaign runner and report: implemented and tested.
- Case format, settings (tiers × rule seeds drawn from candidate pools, public and private), `casekit`,
  validator (parameter binding in every tier) and 5-locale message catalog: implemented. The fixed rule sets
  A / B / C are gone; every case draws its parameters.
- Built cases: one or more per field (see `cases/README.md`), all passing `validate-case` in all five
  locales and on world seeds 1–3, each with a baseline, a README and a REVIEW.md of open findings, and an
  explainer in every language (all three per language in the case's `docs/<lang>/`). Every case has settings: three tiers and a public panel of rule seeds, among
  them stock trading, loan underwriting, hospital scheduling and multilingual corpus curation as programs, and
  BI analysis, where answers may be "don't know" and the rule seed draws what a don't-know answer earns.
  Open binding findings (a parameter stated in a tier where it changes nothing) are listed in
  `validate.OPEN_BINDING_FINDINGS`.
- Program deliverables: implemented and tested (state across calls, step-by-step sessions, input/output
  folders, per-call and total timeouts, crashes, non-JSON outputs, environment and network isolation,
  collection, an end-to-end run).
- Ground truth audit (`audit-case`, `audited: true`, the target funnel, the lazy `diagnose()` hook and the
  diagnostic reliability checks): implemented and tested on a toy case. Three cases are audited (procurement,
  loan underwriting, multilingual corpus curator); their stored audits predate `AUDIT_VERSION` 3 and are stale
  until audit-case runs on them again.

Not yet verified: a live model run (no API keys in the build environment), the vendor CLI command lines
against installed versions, `DockerSandbox` and `docker/Dockerfile.agent` (no Docker daemon in the build
environment).
