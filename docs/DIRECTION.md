# FDE-Bench v2 — direction, positioning and critique

Status: October 2026. This document says what the benchmark is for, where it sits among current agent
evaluations, what it does that others do not, where it is still weak, and what to do next. It is written to
guide new cases (the catalog has 76 planned roles) and the first live campaigns. Facts about other work come
from the research notes summarized in §9; items marked *(unverified)* were not checked against a primary
source.

## 1. What FDE-Bench v2 measures

A forward-deployed engineer (FDE) turns an under-specified client request into a working deliverable inside
the client's rules. FDE-Bench v2 measures four abilities on the same trajectory, separately:

| Ability | Question | Measured by |
|---|---|---|
| **Elicit** | Did the agent find out this client's rules and parameters? | Ask-F1 against clarification targets (judges see the client's answers); the share of runs valid under every rule seed of a tier ("all valid across rule seeds") |
| **Operationalize** | Did the deliverable actually enforce what was learned, including on hidden and future inputs? | Validity against hard rules; program deliverables run on hidden, dated inputs |
| **Optimize** | Within the rules, how good is the result? | Quality normalized between a naive baseline (0) and a reference solution (1), uncapped; full credit at the quality cap |
| **Hold the line** | Under pressure, temptation or a profitable shortcut, did it follow the client's rules and the company policy for exceptions? | Rule violations on pressure items; bent rules only with an approved exception for that rule |

…and how these change with the **customer language**, the agent's **protocol language**, the **company
policy**, the **engagement** (full spec / must clarify / messy) and the **harness** (one reference loop and
four vendor CLIs on the same client channel).

**One-sentence positioning.** FDE-Bench v2 is a procedurally generated, multilingual benchmark of
deliverable-level FDE work. It holds the agent's view fixed while varying the hidden ground truth (difficulty
tier × rule seed), so it can isolate whether agents *elicit, operationalize and honour* a client's rules,
including in programs that run on hidden, dated inputs. It does this across customer and protocol languages,
company policies and vendor harnesses on one client channel.

## 2. Lineage and neighbours

- **Baidu FDE-Bench** (arXiv 2610.14539, Oct 2026) introduced the FDE framing: 49 real customer projects
  (optimization and ML), hidden information revealed by a simulated customer, quality relative to the
  customer-accepted FDE solution, DSR, pass^3, Ask-F1 with a judge panel, case-cluster bootstrap CIs. Best
  quality was 0.551 and best DSR 6.12%; 78.5% of zero scores were constraint violations, and agents sometimes
  asked about a rule and then failed to enforce it. Its stated limits: a static customer, fixed data, two task
  families, no human customers.
  - **v2 keeps the metric vocabulary** (quality vs reference, DSR, Ask-F1, pass^k, Interact-Req) so results
    are comparable in kind. It **shares no code or data**: every case is original and generated from a seed
    (the original cases could not be redistributed). v2 is a successor in design, not a fork.
  - What v2 adds to that framing: counterfactual ground truths over a fixed view, rule classes with company
    policies and exception processes, dated events and pressure items, program deliverables run day by day,
    five natively authored languages on two axes, and harness comparison through one client channel.
- **Name collision.** Another, unrelated "FDE-Bench" (arXiv 2609.27571, Sep 2026) evaluates deployment
  configuration (Docker, Compose, Kubernetes). Cite v2 with its full name and repository.
- **Closest neighbour: τ^τ-Bench** (arXiv 2609.04611, Sep 2026). A coding agent builds a customer-service
  agent from business records and a client with hidden requirements (fixed fact IDs), and the built agent is
  scored on held-out simulated users. It compares Claude Code, Codex, Kimi Code and OpenCode and keeps 53
  private tasks. Best result is 23.9% against an 82.2% oracle reference, from one trial per configuration
  with no CIs. v2 shares the "program on hidden inputs + hidden requirements + harness comparison" core and
  differs in counterfactual settings, policies, multilinguality and dated events.

## 3. Where agent evaluation is going, and how v2 responds

| Trend (2025–26) | Evidence | v2 response | Status |
|---|---|---|---|
| User-in-the-loop evaluation with simulated users, now under scrutiny | τ / τ² / τ³; UserBench; CRMArena-Pro; *Lost in Simulation* (up to 9 pp from the simulator alone); *Sim2Real* (simulators too cooperative) | LLM client answering only from the brief at temperature 0; persona by engagement; no spec dump; no invented rules; at most 6 questions per message; exceptions classified, not negotiated | Partly. Needs a simulator audit (leakage, fidelity, model sensitivity) and a human calibration subset |
| Knowing when to ask is scored | Ask-F1 (HiL-Bench, Baidu); *Lost in Conversation* (−39%); Baidu oracle ablation (0.06 → 0.87 quality with full answers) | Ask-F1 with answer-grounded judges; targets per setting; all valid across rule seeds | Done. Needs judge–human agreement per locale |
| Deliverable-level, economically grounded work | GDPval; RLI (2.5%); Baidu (0.55 quality); τ^τ (23.9%) | Batch and program deliverables with business objectives | Done. No human or expert baseline yet |
| Harness as an experimental variable | HAL; "Stop comparing agents without disclosing the harness"; scaffold effects up to 40× tokens | Reference loop + 4 vendor CLIs on one MCP client channel; same model in both isolates the harness effect | Built, untested live |
| Reliability and statistics beyond one run | pass^k (τ-bench); 2–6 pp single-run noise; clustered SEs, power analysis | pass^k over repeated trials (trials separate from noise seeds); all valid across rule seeds; bootstrap CIs over cases; world-seed robustness; run statuses so infrastructure errors are not averaged in | Partly. Needs pre-registered contrasts and case-clustered models (§7) |
| Contamination resistance | Private splits (SWE-bench Pro, HCAST, τ^τ); seeded generation; rebranding; agents searching for answers | Procedural worlds; `world_seed` for private evaluation worlds; private rule seeds draw rule parameters whose answers are published nowhere; validator checks other world seeds | Partly. Ground truth for the public world and the public rule seeds is in the repo by design; private seeds are the protocol (§7) |
| Validity audits and "Verified" releases | Agentic Benchmark Checklist (up to 100% relative mis-estimation); τ-Bench Verified; ImpossibleBench (reward hacking) | validate-case: reference and baseline valid, one clean example per rule, every parameter binding in every tier where it varies, identical agent view, stored data matches generator, locale parity and authoring lints, negative tests of the validator | Partly. Needs per-target ablations and shortcut probes (§8, §10) |
| Headroom-aware scoring | RE-Bench (0 = starting solution, 1 = reference, uncapped); DSBench Relative Performance Gap; the deployment FDE-Bench's release gate (do-nothing and stub baselines must score 0) | Quality normalized from a per-case baseline to the reference, uncapped; full credit at a cap above the reference | Done in the framework; per-case calibration open (§10) |
| Cost-aware evaluation | HAL cost columns; τ^τ build and serve cost | Tokens and dollars per run for solver, client, extractor and judges | Partly. CLI solver tokens not parsed yet |
| Benchmarks as RL environments | Environments Hub, OpenEnv, verifiers; gyms (UserBench, ColBench) | Daily program cases are already step-wise environments | Not built (a gym wrapper is cheap; §6) |
| Safety as propensity under pressure inside productive work | Agentic Misalignment; ODCV-Bench; PropensityBench; PACT (evaluation framing cuts violations ~29%) | Pressure and temptation items (VIP override notes, insider tip, "make it 10%") scored as rule violations | Done. Report propensity separately; keep cues naturalistic |
| Multilingual agentic evaluation | τ-Multilingual (Korean −14.7, Mandarin −8.4); MAPS; PolyWorkBench | Five natively authored locales; customer × protocol language | Done. Needs native-speaker review and difficulty parity across locales |
| Dynamic worlds and time | Gaia2; Vending-Bench 2; τ² dual control; Baidu names requirement drift as future work | Dated events, mid-task changes (messy), day-by-day programs | Done |

## 4. What is distinctive

1. **Counterfactual ground truths over a byte-identical view.** The same data and request carry a correct
   answer for every tier and rule seed, and a private rule seed draws one that is published nowhere. A good
   score across rule seeds requires eliciting the parameters; priors and memorized answers cannot get there.
   The validator enforces both halves (identical view; every parameter changes the answer in every tier where
   it varies).
2. **Programs on hidden, dated inputs.** The agent ships code that runs day by day on a period it never saw,
   with regulator changes, absences and cancellations arriving as notices. This tests whether elicited rules
   are *operationalized*, which is exactly where Baidu found agents failing.
3. **Rules with classes and company policies.** Physical rules never bend; contractual and business rules
   bend only through the policy's exception process, and an approval covers one named rule. The same run is
   re-scored under several policies without re-running.
4. **Two-axis multilinguality.** Customer language × protocol language, authored natively in zh, en, ko, ja
   and es, including the data labels and file names.
5. **Pressure inside productive work.** Integrity is measured on the same trajectory as capability.
6. **Auditability.** Every case stores its data, hidden inputs and ground truth per setting (`dataset/`) and
   an explainer page; the validator keeps both in sync with the generator.

## 5. Design commitments for every new case

These are the rules new cases follow (the `new-case` scaffold encodes them):

1. One seeded world; the agent's data and request are the same in every setting.
2. Three tiers that change which rules apply, and rule parameters that a rule seed draws from candidate
   pools (`params:`, with a public panel in `rule_seeds:`); every parameter binds in every tier where it has
   more than one candidate, so each draw has its own answer.
3. Every rule has a class; exactly one business rule is the bendable habit, and bending it must matter: its
   measured gain should be positive in some settings and negative in others, never fixed by the formula.
4. Situations of all three kinds: hidden facts, dated events, pressure or temptation. Pressure reaches the
   agent (not only a program at run time), and every hidden fact bites: ignoring it makes the deliverable
   invalid or measurably worse.
5. Deterministic outcome scoring against the world; no LLM judge for quality.
6. Two anchors: a baseline (the client's own way without an engineer, quality 0) and a solid reference
   (quality 1.0), with the headroom above the reference measured and reported; rules that bind; numbers for
   every public setting.
7. Client-native formats (CSV, xlsx, SQL dumps, e-mails, folders), five natively written locales; the
   scenario's country is stated, or localized, in every locale.
8. The client knows business facts (goals, costs, trade-offs), never the evaluation; a target that the data
   already settles is a confirmation, not a hidden fact.
9. The case works on other world seeds (`validate-case` checks seeds 1–3 by default), so evaluation can use
   private worlds.

**Forecasting and other ML cases.** A forecast has no single correct answer: many models are reasonable, and
one realized future mixes skill with luck. Such cases follow four rules instead of "match the reference":

- *Score the expected loss, not one draw.* The world knows the demand distribution it samples from, so the
  scorer computes the deliverable's expected loss under it (exactly, or over many sampled futures). The result
  is deterministic and its optimum is known: the Bayes forecast of the true process. That optimum, not a
  reference heuristic, sets `quality_cap`; seasonal naive is the baseline.
- *The client's decision picks the loss.* Absolute error is minimized by the median, squared error by the mean,
  a newsvendor cost with under- and over-stock prices by a quantile. Which one applies is a business fact to
  elicit (what a lost sale costs against an unsold unit), so a good model scored under the wrong loss is worse,
  for a reason the client can explain.
- *Rules constrain decisions, not forecasts.* A shelf minimum, case-pack sizes or a delivery capacity apply to
  an order plan derived from the forecast; a forecast itself should never be "invalid" for being low. Ask for
  both (forecast and order) or score the order only.
- *Elicitation is about the target.* The hidden facts are what is being forecast (demand or recorded sales
  when stockouts censor it, units or kilograms, returns netted or not), the calendar (holidays, promotions,
  closures) and the horizon. Each changes the expected loss measurably, which the validator can check with
  ablations; the model family is left entirely to the agent.

## 6. Critique

### 6.1 Fixed in this review
| Problem | Why it mattered | Fix |
|---|---|---|
| Any approved exception forgave any bendable violation | An agent could get approval for rule X and break rule Y | The client maps a request to one of the setting's rules; an approval only covers that rule |
| The client could be asked for its whole brief | "List all your requirements" turned the clarification test into one question | The client has no spec to send and answers specific questions only |
| Ask-F1 judges saw only the questions | Coverage was a guess about what an answer "would" reveal | Judges see each round's answer and score what the engineer learned |
| Every run used the public world, whose answers are in the repo | Memorization and search-time contamination | `world_seed` for private worlds; `validate-case --world-seeds` checks other seeds |
| Several cases broke on other seeds | Private-seed evaluation would crash or mis-score | Generators, references and examples fixed to work across seeds (see §6.3) |
| No uncertainty in reports | With 13 cases most differences are noise | 95% bootstrap intervals over cases; unclipped quality next to the capped component |
| Quality clipped at a modest reference, no null anchor | Competent agents saturated; hidden facts that only move quality, and bendable rules, were free or worthless; do-nothing deliverables scored 0.24–0.6 | Quality normalized from a per-case baseline (0) to the reference (1), not clipped at 1; full credit at `quality_cap` (1.5 or the case's known best); a perfect minimize answer no longer scores 0; NaN objectives are invalid |
| `request_exception` was a free-text side channel | Its prompt held the client's whole brief and its reply was free text | A classifier sees only the rule list; the decision is computed from the policy; the reply is a fixed template; the first decision binds; escalation costs a question round |
| Client prompt gaps | Business costs under "how judged" were unreachable; the client invented defaults; engineer text could steer it | The client states business facts but never the evaluation, says it has no rule instead of inventing one, treats engineer text as untrusted, answers at most 6 questions per message, runs at temperature 0 |
| Events leaked or varied by setting | The client knew future events from t = 0; the volunteered fact and inbox names depended on the setting or revealed the event type | Event knowledge arrives when the event fires; one volunteered target id across settings; neutral inbox names |
| Program interface unknowable without asking | In the hidden condition a program case could not be delivered | The entry point and interface spec are shown to the agent in every condition |
| Question budget counted rounds | 30 questions in one message cost one | Budgets and the per-message cap count questions |
| Isolation holes | Agent symlinks could make the host copy ground truth; the extractor had a host shell over data/; the mount path named the setting; the bridge had no auth; every API key reached every container | Workspace sanitized before any host read; extractor without shell, sees only the agent's files; opaque staging path; per-run bearer token; per-harness env |
| Campaign bookkeeping | One `seed` meant both trial and noise (no pass^k); duplicate runs raced; stale results reused after edits; errors averaged in as 0 | `noise_seed` and `trial` split, τ-bench pass^k; dedup and per-run locks; fingerprinted cache; run statuses with infra errors excluded; cost columns for solver, client, extractor, judges |
| Fixed rule sets A / B / C | Three published parameter sets per case: their answers were in the repo, and the validator compared whole sets, so a parameter that changed nothing went unnoticed | A rule seed draws each parameter from its candidate pool; private rule seeds give answers published nowhere; validate-case checks that every parameter binds in every tier where it varies |
| The validator only checked what authors remembered | Defects found by hand in review (wrong café name, a rule saying 2 where the data says 6, TODOs, locale drift) | Baseline, locale-parity, hash-seed determinism, TODO, number and name–ID lints, cross-tier warnings, a default world-seed panel, and negative tests of the validator itself |

### 6.2 Open (ordered by importance)
1. **No live run yet.** No API keys in the build environment; vendor CLI flags and docker isolation are
   unverified. Headroom, signal-to-noise and null-agent scores are therefore unknown.
2. **Simulated-client validity is unmeasured.** Over-cooperation, leakage per locale and sensitivity to the
   client model need an audit and a small human-client calibration.
3. **Statistical power.** 13 cases, all with settings. Settings and seeds are clustered within cases, so they
   do not replace more cases. The axis grid multiplies cells faster than evidence.
4. **Ten cases are not yet audited.** `fdebench2 audit-case` now measures, per case, whether each client fact
   bites, whether shortcuts are closed, what asking is worth and how far the reference is from the best known
   solution (§11). Procurement, loan and the multilingual corpus curator are audited (`audited: true`); the
   other ten are measured on request only, and the bendable rules' payoff is still a per-case property.
5. **No human baseline.** References are written with full knowledge of the ground truth.
6. **Synthetic realism and language quality.** Requirements reflect the authors' research, not elicited
   practice; locale texts were written by models and need native review.
7. **Open binding findings.** A parameter the client states changes no reference in some tiers: bi's reward
   for "don't know" in easy and medium, bakery's lateness cost in easy and its shift end in easy and medium on
   world seeds 2 and 3. They are validator warnings
   (`validate.OPEN_BINDING_FINDINGS`) until each owner decides. Loan and hospital also vary parameters in tiers
   where nothing uses them (warnings).
8. **Cost reporting** covers client, extractor and judges; a CLI solver's own tokens are not parsed yet.
9. **Open network in the agent container.** Model APIs need egress; an allowlist needs a proxy. Web search
   should be off or logged per harness.

### 6.3 Case-level critique
See §10 (from an independent review of every case with adversarial verification of each finding).

## 7. How to run and report an evaluation (protocol)

- **Primary metrics:** final score and its components; validity; normalized quality (baseline 0, reference
  1, uncapped) next to the plain ratio to the reference; DSR (normalized quality ≥ 1); all valid across rule
  seeds (valid under every rule seed of the tier); Ask-F1; propensity (violations on pressure items, reported
  separately).
- **Settings:** report per tier (difficulty), each case's score the mean over its rule seeds, then the mean
  over cases. Use private rule seeds (`rule_seeds: [...]` in the campaign; the same seeds for every system):
  the public panel's answers are in the repository and are for development and the explainers.
- **Worlds:** report on private world seeds; the public seed is for development and the explainers.
- **Repetition:** `trials: 3` or more per (case, setting) for pass^k (τ-bench estimator over trials); noise
  seeds vary the hand-over and are not trials. World robustness (valid across world seeds) is a separate
  quantity; do not call it pass^k. Report run statuses and keep harness or infrastructure errors out of means.
- **Uncertainty:** case-cluster bootstrap intervals; compare systems with paired, within-case differences.
  Pre-register the primary contrasts (e.g. harness effect at fixed model; Korean vs English customer) instead
  of reading the full grid.
- **Harness disclosure:** model, harness, version, flags, tool access (web search off or logged), budgets.
- **Cost:** tokens and dollars for the solver, the client, the extractor and the judges; wall-clock.
- **Simulator disclosure:** client model, persona, engagement; judge models (not from the solver's family).

## 8. Roadmap

| Priority | Item |
|---|---|
| P0 | Audit the other ten cases to the standard of §11 before adding cases: facts that bite, shortcuts closed, a genuine never-asks solver, best known and bound, `quality_cap` from the best known; anchors that hold on 10+ private seeds (stock first); bending that pays in some settings and not others (§10) |
| P0 | Human review of the client's answers: each audited case's `CLIENT_REVIEW.md` awaits a reviewer's verdict per fact and locale |
| P0 | First live campaign on a small grid with `trials: 3`; null and stub agents per case; signal-to-noise per case |
| P0 | Client audit: leakage and fidelity per locale, sensitivity to the client model; consider a fact-ID knowledge boundary |
| P0 | Private evaluation seeds (world and rule seeds) and a canary string; web tools off or logged in harness configs; an egress proxy for the agent container |
| P1 | Settle the open binding findings (`validate.OPEN_BINDING_FINDINGS`: bi, bakery) and give a parameter a single candidate in tiers where nothing uses it (loan, hospital); add a dated event and pressure to bi |
| P1 | Human-FDE baseline on a subset (time and quality); expert review of each case's requirements |
| P1 | Native-speaker review of the five locales; difficulty parity across locales; declare or localize each scenario's country |
| P1 | A `confirm` target kind for facts the data already settles; CLI solver token parsing; Pareto plots |
| P2 | Grow to 40–50 cases across the catalog with the scaffold; pre-registered contrasts and power analysis |
| P2 | Gym wrapper over daily program cases (observation = day input, action = program output, reward = daily score minus violations) |

## 9. Sources

Primary references for the claims above: Baidu FDE-Bench arXiv 2610.14539; deployment FDE-Bench arXiv
2609.27571; τ^τ-Bench arXiv 2609.04611; τ-bench 2406.12045; τ²-bench 2506.07982; τ-Multilingual 2609.35820;
SABER / τ-Bench Verified 2512.07850; UserBench 2507.22034; BIRD-Interact 2510.05318; CRMArena-Pro 2505.18878;
GDPval 2510.04374; Remote Labor Index 2510.26787; SWE-bench Pro 2509.16941; MLE-bench 2410.07095; RE-Bench
2411.15114; DSBench 2409.07703; HAL
2510.11977; ImpossibleBench 2510.20270; ODCV-Bench 2512.20798; PACT 2609.18605; Gaia2 / ARE 2509.17158;
Lost in Simulation 2601.17087; Mind the Sim2Real Gap 2603.11245; MAPS 2505.15935; PolyWorkBench 2607.06008.

## 10. Case-level critique (appendix)

An independent reviewer read each of the 13 cases (code, data, five locales, stored dataset) and a second agent
tried to refute every finding by re-running the reviewer's evidence. 121 findings: 82 confirmed, 39 confirmed in
part, none refuted (the verifiers were lenient: read "partly" as "the direction is right, a detail is overstated").
Each case's findings, with what was fixed and what is left as a proposal, are in its `REVIEW.md` and in the
"Review findings" section of its `explainer.html`.

### 10.1 Patterns across cases

| Pattern | Cases | Consequence | Response |
|---|---|---|---|
| The reference is a modest heuristic and quality was clipped at 1.0 | 12 of 13 | Every competent agent saturates; hidden facts that only move quality are free to ignore; the case cannot tell good from excellent | Framework: quality is normalized between a naive baseline (0) and the reference (1) and is not clipped at 1; the composite gives full credit at `quality_cap` (1.5, or the case's known best) |
| Degenerate valid deliverables score well | stock (do-nothing 0.24–0.32), callcenter (one shift 0.38), corpus (placeholders 0.60) | A null agent looks competent | Every case gets `baseline_solution`; the validator checks it is valid and worse than the reference; the baseline scores 0 |
| The bendable rule never pays, or dominates | never: 10 cases; dominates: stock (+28–90%); non-monotone: benefits | "When to bend a habit" has one answer, so the exception process measures nothing | Partly framework (headroom above the reference now counts); the rest is case calibration: bending should pay a bounded, visible amount in some settings and lose in others |
| Hidden requirements readable from the visible data | battery, stock, grocery, hospital, bi, resume, callcenter | Ask-F1 penalizes an agent that correctly infers instead of asking | Proposal: a `confirm` target kind (credited by a question or by a correct NOTES.md statement) |
| Business facts sit under "How the work is judged", which the client may not discuss | loan, bakery, hospital, contract, benefits | Whether the agent can learn a cost depends on the simulator disobeying its prompt | Framework: the client may state business goals, costs and trade-offs; cases move unit economics into business sections |
| Missing situation types (dated event, pressure) | 10 of 13; vacuous pressure in loan and stock | Two of the three situation types are untested in most cases | Case work, part of each conversion to tiers × rule seeds: the converted cases put a dated event or pressure in hard; bi still has neither |
| No settings | 8 single-problem cases (7 after the BI conversion) | Their easy/medium/hard columns are identical | Done: every case has three tiers and rule parameters drawn by rule seeds (each REVIEW.md, "Rule seeds") |
| Correctness bugs | bakery (wrong café name), grocery (rule says 2, data says 6), bi (rounding rule contradicts tolerance), loan (budget cut invalidates earlier approvals), contract (obeying the fast-track rule penalized), benefits (a perfect answer scored 0), corpus (review rows and placeholder text gameable), hospital (waitlist loophole), resume (adverse-impact test is a lottery), procurement (reference re-sizing bug) | Wrong ground truth or a free score | Fixed in this round (see each REVIEW.md) |
| Country neutrality and realism | most cases (Korean regulation in loan, a Korean plant in procurement, a Spanish site in battery, Singapore in resume, a Western holiday calendar in grocery) | Locale effects are confounded with scenario familiarity | Either declare the provenance in every locale or localize; record it in the README |
| Locale text quality | all | Small meaning changes in ko/ja/zh | The specific Korean fixes found were applied; a native review is still open |
| One global quality cap fits no case (found after the scale change) | best known normalized quality: hospital 1.01–1.06, benefits 1.03 (compliant), grocery 1.07, bakery 1.07 (compliant), bi 1.09, contract 1.15, callcenter 1.18 (exact MILP), battery 1.18 (forecast LP); while procurement and resume saturate | With the policy cap of 1.5 a perfect agent earns about 70% of the quality credit in most cases, and in two cases a modest improvement already earns all of it | Calibrate `quality_cap` per case to its best known solution (an exact optimum, an LP or a perfect answer), or strengthen the reference; owner's decision per case, listed in each REVIEW.md |
| Baseline nearly as good as the reference | procurement easy/medium (plain MRP within 2–3%), resume (relevant years only, within about 2%) | Normalized quality would blow small differences up 40–50 times | Framework: the baseline stays exactly the zero point (an earlier 5% floor moved it silently: with reference 100 and baseline 102 the baseline scored 0.6); a scale narrower than 5% is now a validator finding, open for procurement, loan and resume, and the fix is a stronger reference or a sharper objective |

### 10.2 Per case

Every case has three tiers and rule parameters that rule seeds draw from candidate pools. Six of them (bi,
multilingual curation, loan, stock, hospital, procurement) had fixed rule sets A / B / C before and now draw
their parameters; the other seven were single problems and got tiers and rule seeds in this round. Each
REVIEW.md has a "Rule seeds" section on its conversion.

Baseline/reference is the objective ratio on the public world, from the lowest to the highest over the case's
nine public settings (tier × public rule seed; above 1 for cases that minimize cost).

| Case | Fixed in this round | Main open item (proposal for the owner) | Baseline / reference |
|---|---|---|---|
| callcenter_workforce_planner | Under-staffing weight explained as a business cost; neutral holiday framing; Korean wording; fixed-rota baseline; README. Then converted to 3 tiers × rule seeds (under-staffing weight, contract week, holiday share, rest, sick days), with a dated sick call and a team lead's pressure note in hard | The bendable buddy rule still pays little; the greedy reference is 0.5–8.1% above the exact MILP optimum (normalized 1.03–1.17), so one quality cap fits no setting | 1.16–1.63 (min) |
| bi_data_analyst | A rule-compliant rounded answer now scores; refund cut-off stated; Korean wording. Then converted to 3 tiers × rule seeds: answers may be "don't know" (null), and the rule seed draws what a null earns (0.5, 1 or 1.5; wrong 0, right 2) along with the fiscal year, active window and rounding unit, so calibrated abstention is measured; the all-"don't know" sheet is the baseline | No dated event or pressure; one quality cap cannot fit both the tiers where the reference is perfect and hard; there (easy, medium) the reward for a null changes no reference (an open binding finding) | 0.25–0.77 |
| multilingual_corpus_curator | Review-row spamming, placeholder descriptions and a header-only manifest no longer score; Korean labels; medium scope wording. With rule seeds, a length limit per tier and a no-author policy in hard. Then deeply audited (§11): the manifest and review copies are mandatory outputs, a misfiled book earns a flat 0.4 so every naming rule bites, the reference is the full organizer and meets the proven bound (quality_cap 1.0), eleven shortcuts closed, a never-asks program leaves 0.65–0.69 to asking | No dated event or pressure, and the bend stays dominated; era notations in implausible places; fixed counts per kind; four hard facts bite only through a hard gate | 0.09–0.17 |
| battery_dispatch_operator | SOC tolerance no longer turns on rounding; no DST hint to the extractor; the site is in Spain in every locale. Then converted to 3 tiers × rule seeds, with three dated notices and trading-desk pressure in hard | The visible dispatch log reveals the hidden rules; a forecast LP reaches 1.18; a daily-bid program would be closer to practice | 0.00 |
| loan_underwriting_specialist | A treasury cut no longer invalidates earlier approvals; unit economics are business facts; easy scope consistent with the regulator. Then deeply audited (§11): referrals are scarce (3 discretionary a day), the limit table is mandatory and multiplies profit, so neither referring hard declines nor dropping the table pays; a price-based reference (+2–12%), a perfect-information bound (gap 3–11%), quality_cap 1.02 | Bending the tenure habit always adds objective; asking is all-or-nothing validity (every fact is a hard rule); Korean regulatory provenance; four parameters vary in easy (the discrepancy threshold also in medium) where nothing uses them | 0.47–0.85 |
| stock_trading_strategist | Easy scope names the large-order rule; Korean terms consistent; do-nothing baseline | On many private worlds the reference ends below cash (the do-nothing baseline beats it on seeds 0, 3, 7, 42, ...): measure excess over max(index, cash) and average several hidden paths; bound the large-order exception | 0.23–0.57 (public world; above 1 on some private world seeds) |
| hospital_appointment_scheduler | Waiting-list excuses only when capacity was really gone; notice after a release; a same-slot doctor swap needs no notice; client-voiced scope; Korean terms | Demand is about equal to capacity, so utilization barely varies (best known 1.01–1.06); overbooking economics do not reward risk selection; the lab cap varies in easy and the overbooking cap in easy and medium where nothing uses them | 0.56–0.81 |
| contract_review_counsel | Obeying the fast-track rule is no longer penalized; target split into issue codes and decision rule; natural amounts in ko/ja/zh; README. Then converted to 3 tiers × rule seeds, with supplier paper, amendments and a business owner's e-mail in hard | The decision field carries no information of its own; contracts are templated; a perfect review is 1.15 | 0.00–0.09 |
| bakery_delivery_dispatcher | The closed café is C11 = South Hill (the texts named C10); lateness cost is a business fact; Korean wording; README. Then converted to 3 tiers × rule seeds (the shift end and tray limit now bind in the headline settings), with V2 in the workshop and a premium manager's demand in hard | Where premium-first holds it costs about 28% of the reference's objective, so bending it pays clearly; whether a bend should pay that much is open; the one-visit rule never binds; the lateness cost changes no easy reference, nor the shift end an easy or medium one on world seeds 2 and 3 (open binding findings) | 2.19–3.83 (min) |
| procurement_specialist | Reference deferral re-size bug; garbled easy sentence; Korean lines. Then deeply audited (§11): the price e-mail is a supplier thread that raises the display maker by 12% from a mid-week date (the order week decides), backlog is priced per board, 19 bundled targets became 25 single facts, a local-search reference, an LP bound and quality_cap 1.11 | Five facts bite in under half their settings; the share and budget rules are decided by several facts together (cross-flag warnings); asking is worth only 0.34 in hard; the bound is loose in hard (18–20%) | 1.09–1.19 (min) |
| resume_screening_specialist | The adverse-impact check no longer fails protected-blind shortlists by chance; past-hire instruction; Korean. Converted to 3 tiers × rule seeds. Then the quality scale: fit counts above the 30 points every qualified candidate starts from, and the easy and medium reference learns from the past hires; spans 7.5–37% on every world checked, and the interview date now binds | Not audited yet: no ablations, shortcuts, never-asks solver or bound; in hard a face-value learner nearly matches the debiased reference; the requested ranking is not scored | 0.63–0.79 |
| benefits_eligibility_officer | Reason codes scored (RENEWAL vs APPROVED, precedence of refusals); business-goal target; Korean terms; README. Then converted to 3 tiers × rule seeds, with the heating circular, reported changes and two exception letters in hard | A fixed renewal error caps compliant answers at 1.03 and bending the renewal rule always pays | 1.46–3.00 (min) |
| grocery_demand_forecaster | The display-floor rule says 6, as everything else does (it said 2); row-cardinality text; Korean wording; README. Then converted to 3 tiers × rule seeds (the floor is drawn), with a dated promotion cancellation in hard | A forecast from the true generator mean reaches only 1.07; censoring is uninformative; no pressure item | 1.64–3.20 (min) |

### 10.3 What this changes in the direction

- **Headroom is part of validity.** A score that saturates at a modest reference cannot measure the thing the
  benchmark claims (optimization on top of elicitation). Precedents: RE-Bench scores 0 = starting solution and
  1 = reference with no cap; DSBench's Relative Performance Gap normalizes between a baseline and the best human;
  the deployment FDE-Bench's release gate rejects tasks that do-nothing or stub baselines solve.
- **Every hidden fact and every bendable rule must bite, measurably.** The review found many facts that change no
  answer and bendable rules whose payoff is fixed by the scoring formula. The next case-authoring contract adds
  an `ablations()` hook next to `violating_examples()`: for each quality-relevant target, a deliverable that
  ignores only that fact, which the validator requires to be invalid or to lose at least 3% normalized quality;
  and for the bendable rule, the measured gain of the best bent deliverable per setting, which should be positive
  in some settings and negative in others.
- **The client knows business facts, not the evaluation.** Costs, margins and trade-offs belong in the client's
  business knowledge; formulas and weights do not.
- **Calibrate each case against its best known solution.** A single quality cap is wrong for every case: the
  room between the reference and the best possible answer ranges from 1% to more than 20%. Each case should
  report its best known normalized quality (an exact optimum where one is cheap, an LP or perfect answer
  otherwise) and set `quality_cap` from it, so full credit means "as good as is known".
- **Robustness across worlds is part of the case, not the seed.** The stock case's reference loses to cash on
  many generated worlds; a case's anchors (baseline, reference) must hold on the private seeds it will be
  evaluated on, which the validator's seed panel now checks for three seeds and should check for more before a
  campaign.

## 11. Ground truth before breadth

The case owner's assessment after the first ten rounds:

- Strengthen ground truth (GT) and scoring before adding cases, and keep the counterfactual core: one world with
  identical data in every setting, where the client-only facts decide the right answer.
- GT should describe acceptable behaviour, with the reference as supporting evidence, in five parts:
  1. client facts;
  2. validity checks;
  3. the objective, including uncertainty;
  4. the reference and how close it is to the best achievable;
  5. diagnostic cases that tell a correct implementation from a shortcut.

The priorities were:
1. calibration;
2. facts that measurably matter;
3. shortcuts closed before the reference is improved;
4. a test of whether asking is necessary;
5. learning a fact kept apart from using it.

The milestone was three deeply audited cases rather than more cases. This section records what was done and what
it showed.

### 11.1 Calibration

The quality scale had a hidden inconsistency. A 5% floor moved the zero point whenever the baseline came within 5%
of the reference: with reference 100 and baseline 102 (minimizing), the baseline scored 0.6, against the documented
"baseline = 0".

- The baseline is now the zero point exactly.
- Every evaluation reports the scale's width, `quality_span` = |reference − baseline| / |reference|.
- A setting narrower than 5% is a validator finding. On a scale that narrow, a 1% objective difference moves
  quality by 0.2 or more.
- The check found narrow scales in procurement (6 settings on worlds 1–3), loan (4) and resume (13, down to 0.8%).
  All three are now at least 5% wide on the public world and world seeds 1–3, so the validator has no waivers
  left.
- Resume's fix changes what the objective counts: fit above the 30 points every qualified candidate starts from.
  That widens the span without changing quality per fit point. The case README states this.

### 11.2 The audit

`fdebench2 audit-case` measures a case on its public panel plus up to 12 parameter combinations per tier.
Combinations are used rather than rule seeds, so no private rule seed's draw is exposed. The results are stored in
`dataset/audit.json` with a fingerprint of the case sources. A case with `audited: true` fails validation when its
audit is missing or stale, or when any of the following holds.

| Part of the GT | What the audit measures | Gate |
|---|---|---|
| Client facts | Per target, the reference planned on a misreading of only that fact (`param:` targets: the reference of each wrong candidate value, judged on the least harmful one) | Invalid or ≥ 0.10 normalized quality lost in some setting of each tier where it is in force; a warning below half the settings |
| Validity checks | `shortcuts()`: strategies that skip what the case tests | Invalid or quality ≤ 0.5 in every setting |
| Objective, value of asking | `robust_solution()`: the best single deliverable built from the agent's view alone, against the reference; also the best reference of another setting | Asking worth ≥ 0.10 per tier (warning below 0.30) |
| Reference and bounds | `best_known_solution()`, `objective_bound()` | One of them exists; `quality_cap` at least the median best known quality |
| Diagnostic cases | Per-target `enforced` from score() or the lazy `diagnose()` hook | Separates the reference from every ablation that bites; no false "not enforced" on the best known; cross-fact flags are warnings |

Each run now records three stages per target:
1. **revealed** by the client: a verbatim quote, asked or volunteered;
2. **learned** through a specific question (Ask-F1, unchanged);
3. **enforced** in the deliverable (the diagnostic).

The report adds a funnel per case. It shows enforced-given-learned and enforced-given-not-learned, so inferring a
fact from the data is visible as such. No live campaign has run yet, so there are no funnel numbers.

### 11.3 Three audited cases

| | procurement | loan | multilingual corpus curator |
|---|---|---|---|
| Targets | 19 bundled → 25 single facts | 26 → 31 | 16 → 12 |
| Facts that bite | 25 of 25 (5 in under half their settings) | 31 of 31 | 12 of 12, in every setting |
| Facts dropped as targets (kept as context) | Resistor reels, holding weight, expected-cost wording, planning rate in easy and hard: under 0.10 damage | Interface, evaluation period, profit metric | Data facts the sample shows, author variants, precedence |
| Shortcuts | 10, closed everywhere | 10, closed everywhere | 11, closed everywhere |
| Shortcuts open before the audit | None of the obvious ones. One mild deviation (no safety stock, 0.58 in one setting) was redefined | Refer every hard decline (0.94–0.98 of the objective); empty table (q 1.13); morning limits (0.71); jittered table (0.67–0.93) | Header-only manifest (0.78); no review copies (1.0); manifest rows without sources (0.76) |
| How they were closed | (none needed) | A daily referral capacity; the limit table made mandatory, and the objective is profit × accuracy on the entries that change | Manifest and review copies made mandatory; no guessed titles or years |
| Value of asking, easy / medium / hard | 1.00 / 1.00 / 0.34 | 1.00 / 1.00 / 1.00 | 0.69 / 0.66 / 0.65 |
| Reference → best known → bound | Local search; best known median 1.11; LP bound gap 3.6–19.5% | Price allocation (+2–12%); best known median 1.02; perfect-information bound gap 3.4–10.6% | Full organizer = best known = proven bound |
| quality_cap | 1.11 | 1.02 | 1.0 |
| Diagnostics on other deliverables | False "not enforced": best known 125 → 0 and baseline 228 → 0 of 657; new misreadings caught 77% (was 53%) | 0 false calls on 84 correct-but-different programs; new misreadings 76% (was 53%) | 0 false calls on 72 correct programs; new misreadings 83% (was 65%) |

Scenario changes the audit asked for, all in the client's own terms and with the agent view unchanged unless
noted:
- **Procurement price e-mail.** It used to change no plan. It is now a localized three-message thread in which
  the display maker raises its main part by 12% for orders received from a mid-week date; the agent view gains
  the thread.
- **Procurement backlog** is priced per board waiting, not per piece.
- **Loan hidden period.** Some branch notes and same-day repayments moved to applicants where they decide the
  answer.
- **Corpus scoring.** A misfiled book earns a flat 0.4, so every naming rule bites.

### 11.4 What this showed

- **Facts that change nothing are common.**
  - Of 61 original targets in the three cases, several bundled three or four facts.
  - About a dozen were dropped as scored facts and kept as context: misreading them cost less than a tenth of
    the scale, or the agent's own data already settles them.
  - Some of those were headline facts, such as procurement's resistor reels; the old price e-mail changed no
    plan at all until its scenario was rewritten.
- **Mandatory outputs must be rules.** The objective did not reliably punish a missing or stale output: loan's
  table and corpus's manifest and review copies could be left out at 0.78 to 1.13 quality. Rules with violating
  examples closed them where objective tweaks alone did not.
- **Value of asking can be all-or-nothing.**
  - In loan, and in procurement's easy and medium tiers, the never-asks solution is invalid everywhere: some rule
    value is always wrong. That proves asking is necessary, but it does not grade how much.
  - The corpus case grades it: a never-asks program keeps 0.31–0.36, and asking is worth the rest.
  - Procurement's hard tier is the weak spot: asking is worth 0.34, because the natural reading of the data
    already matches that tier's scope.
- **A diagnostic that only separates the reference from its ablations is not enough.**
  - An agent's deliverable is neither of those.
  - Procurement's first diagnostic falsely called the client's own plan "not enforced" in a third of its fact
    checks.
  - The audit now requires no false calls on the best known solution, and the adversarial probes add
    correct-but-different deliverables and misreadings the ablations never tried.
  - Misreadings in a direction the natural one does not take remain undetected by design. Examples: one piece per
    board, a lead time a week longer.
- **Facts interact.** Procurement's budget and dual-sourcing rules are each decided by several facts together. A
  per-fact diagnostic then also flags the facts that share the rule (eight cross-flag warnings). Attributing a
  shared rule to one fact needs more than a per-target check.

### 11.5 Still open

- **Human review of the client's answers.**
  - Each audited case has a `CLIENT_REVIEW.md`. For each fact it gives the question an engineer would ask, the
    passage each locale's client answers from, and a machine pre-check: the same numbers, IDs and dates
    everywhere.
  - Every verdict line awaits a human reviewer; none has been given.
- **Ten cases are not audited.** Resume's scale is fixed, but it has no ablations, shortcuts, never-asks solver
  or bound.
- **Thresholds were set on one world.** The 0.10 bite, 0.5 shortcut and 0.10 / 0.30 value-of-asking thresholds,
  and the cases' diagnostic tolerances, are calibrated on the public world.
- **Audits are slow.** An audit takes 10–40 minutes per case, and every source change makes the stored audit
  stale.
- **No live runs yet.** No live run has measured how real agents move through revealed → learned → enforced.
