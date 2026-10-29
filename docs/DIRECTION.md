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
| **Elicit** | Did the agent find out this client's rules and parameters? | Ask-F1 against clarification targets (judges see the client's answers); the all-3 rate (valid under every rule set) |
| **Operationalize** | Did the deliverable actually enforce what was learned, including on hidden and future inputs? | Validity against hard rules; program deliverables run on hidden, dated inputs |
| **Optimize** | Within the rules, how good is the result? | Quality normalized between a naive baseline (0) and a reference solution (1), uncapped; full credit at the quality cap |
| **Hold the line** | Under pressure, temptation or a profitable shortcut, did it follow the client's rules and the company policy for exceptions? | Rule violations on pressure items; bent rules only with an approved exception for that rule |

…and how these change with the **customer language**, the agent's **protocol language**, the **company
policy**, the **engagement** (full spec / must clarify / messy) and the **harness** (one reference loop and
four vendor CLIs on the same client channel).

**One-sentence positioning.** FDE-Bench v2 is a procedurally generated, multilingual benchmark of
deliverable-level FDE work. It holds the agent's view fixed while varying the hidden ground truth (difficulty
tier × rule set), so it can isolate whether agents *elicit, operationalize and honour* a client's rules,
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
| Knowing when to ask is scored | Ask-F1 (HiL-Bench, Baidu); *Lost in Conversation* (−39%); Baidu oracle ablation (0.06 → 0.87 quality with full answers) | Ask-F1 with answer-grounded judges; targets per setting; the all-3 rate | Done. Needs judge–human agreement per locale |
| Deliverable-level, economically grounded work | GDPval; RLI (2.5%); Baidu (0.55 quality); τ^τ (23.9%) | Batch and program deliverables with business objectives | Done. No human or expert baseline yet |
| Harness as an experimental variable | HAL; "Stop comparing agents without disclosing the harness"; scaffold effects up to 40× tokens | Reference loop + 4 vendor CLIs on one MCP client channel; same model in both isolates the harness effect | Built, untested live |
| Reliability and statistics beyond one run | pass^k (τ-bench); 2–6 pp single-run noise; clustered SEs, power analysis | pass^k over repeated trials (trials separate from noise seeds); all-3 over rule sets; bootstrap CIs over cases; world-seed robustness; run statuses so infrastructure errors are not averaged in | Partly. Needs pre-registered contrasts and case-clustered models (§7) |
| Contamination resistance | Private splits (SWE-bench Pro, HCAST, τ^τ); seeded generation; rebranding; agents searching for answers | Procedural worlds; `world_seed` for private evaluation worlds; validator checks other seeds | Partly. Ground truth for the public seed is in the repo by design; private seeds are the protocol (§7) |
| Validity audits and "Verified" releases | Agentic Benchmark Checklist (up to 100% relative mis-estimation); τ-Bench Verified; ImpossibleBench (reward hacking) | validate-case: reference and baseline valid, one clean example per rule, distinct rule sets, identical agent view, stored data matches generator, locale parity and authoring lints, negative tests of the validator | Partly. Needs per-target ablations and shortcut probes (§8, §10) |
| Headroom-aware scoring | RE-Bench (0 = starting solution, 1 = reference, uncapped); DSBench Relative Performance Gap; the deployment FDE-Bench's release gate (do-nothing and stub baselines must score 0) | Quality normalized from a per-case baseline to the reference, uncapped; full credit at a cap above the reference | Done in the framework; per-case calibration open (§10) |
| Cost-aware evaluation | HAL cost columns; τ^τ build and serve cost | Tokens and dollars per run for solver, client, extractor and judges | Partly. CLI solver tokens not parsed yet |
| Benchmarks as RL environments | Environments Hub, OpenEnv, verifiers; gyms (UserBench, ColBench) | Daily program cases are already step-wise environments | Not built (a gym wrapper is cheap; §6) |
| Safety as propensity under pressure inside productive work | Agentic Misalignment; ODCV-Bench; PropensityBench; PACT (evaluation framing cuts violations ~29%) | Pressure and temptation items (VIP override notes, insider tip, "make it 10%") scored as rule violations | Done. Report propensity separately; keep cues naturalistic |
| Multilingual agentic evaluation | τ-Multilingual (Korean −14.7, Mandarin −8.4); MAPS; PolyWorkBench | Five natively authored locales; customer × protocol language | Done. Needs native-speaker review and difficulty parity across locales |
| Dynamic worlds and time | Gaia2; Vending-Bench 2; τ² dual control; Baidu names requirement drift as future work | Dated events, mid-task changes (messy), day-by-day programs | Done |

## 4. What is distinctive

1. **Counterfactual ground truths over a byte-identical view.** The same data and request carry nine correct
   answers. A good score on all three rule sets requires eliciting the parameters; priors and memorized
   answers cannot get there. The validator enforces both halves (identical view, different answers).
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
2. Three tiers that change which rules apply, three rule sets that change their parameters; at least one
   parameter is non-nested so each rule set has its own answer.
3. Every rule has a class; exactly one business rule is the bendable habit, and bending it must matter: its
   measured gain should be positive in some settings and negative in others, never fixed by the formula.
4. Situations of all three kinds: hidden facts, dated events, pressure or temptation. Pressure reaches the
   agent (not only a program at run time), and every hidden fact bites: ignoring it makes the deliverable
   invalid or measurably worse.
5. Deterministic outcome scoring against the world; no LLM judge for quality.
6. Two anchors: a baseline (the client's own way without an engineer, quality 0) and a solid reference
   (quality 1.0), with the headroom above the reference measured and reported; rules that bind; numbers for
   all nine settings.
7. Client-native formats (CSV, xlsx, SQL dumps, e-mails, folders), five natively written locales; the
   scenario's country is stated, or localized, in every locale.
8. The client knows business facts (goals, costs, trade-offs), never the evaluation; a target that the data
   already settles is a confirmation, not a hidden fact.
9. The case works on other world seeds (`validate-case` checks seeds 1–3 by default), so evaluation can use
   private worlds.

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
| The validator only checked what authors remembered | Defects found by hand in review (wrong café name, a rule saying 2 where the data says 6, TODOs, locale drift) | Baseline, locale-parity, hash-seed determinism, TODO, number and name–ID lints, cross-tier warnings, a default world-seed panel, and negative tests of the validator itself |

### 6.2 Open (ordered by importance)
1. **No live run yet.** No API keys in the build environment; vendor CLI flags and docker isolation are
   unverified. Headroom, signal-to-noise and null-agent scores are therefore unknown.
2. **Simulated-client validity is unmeasured.** Over-cooperation, leakage per locale and sensitivity to the
   client model need an audit and a small human-client calibration.
3. **Statistical power.** 13 cases (5 with settings). Settings and seeds are clustered within cases, so they
   do not replace more cases. The axis grid multiplies cells faster than evidence.
4. **Headroom and bite are not yet measured per case.** The scale now credits beating the reference, but
   whether each hidden fact and the bendable rule move the score by a meaningful amount is still a per-case
   property (§10). Proposed: an `ablations()` hook checked by the validator.
5. **No human baseline.** References are written with full knowledge of the ground truth.
6. **Synthetic realism and language quality.** Requirements reflect the authors' research, not elicited
   practice; locale texts were written by models and need native review.
7. **Eight cases are single fixed problems** (no tiers × rule sets yet).
8. **Cost reporting** covers client, extractor and judges; a CLI solver's own tokens are not parsed yet.
9. **Open network in the agent container.** Model APIs need egress; an allowlist needs a proxy. Web search
   should be off or logged per harness.

### 6.3 Case-level critique
See §10 (from an independent review of every case with adversarial verification of each finding).

## 7. How to run and report an evaluation (protocol)

- **Primary metrics:** final score and its components; validity; normalized quality (baseline 0, reference
  1, uncapped) next to the plain ratio to the reference; DSR (normalized quality ≥ 1); all-3 (valid under
  every rule set); Ask-F1; propensity (violations on pressure items, reported separately).
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
| P0 | Calibrate every case before the first campaign: `quality_cap` from its best known solution, anchors that hold on 10+ private seeds (stock first), bending that pays in some settings and not others (§10) |
| P0 | `ablations()` per case: every quality-relevant hidden fact must bite, checked by the validator |
| P0 | First live campaign on a small grid with `trials: 3`; null and stub agents per case; signal-to-noise per case |
| P0 | Client audit: leakage and fidelity per locale, sensitivity to the client model; consider a fact-ID knowledge boundary |
| P0 | Private evaluation seeds and a canary string; web tools off or logged in harness configs; an egress proxy for the agent container |
| P1 | Convert the eight single-problem cases to settings with all three situation types (each REVIEW.md has a concrete proposal) |
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
| Missing situation types (dated event, pressure) | 10 of 13; vacuous pressure in loan and stock | Two of the three situation types are untested in most cases | Case work, part of each 3×3 conversion |
| No settings | 8 single-problem cases | Their easy/medium/hard columns are identical | Case work; each REVIEW.md proposes concrete tiers and rule-set parameters |
| Correctness bugs | bakery (wrong café name), grocery (rule says 2, data says 6), bi (rounding rule contradicts tolerance), loan (budget cut invalidates earlier approvals), contract (obeying the fast-track rule penalized), benefits (a perfect answer scored 0), corpus (review rows and placeholder text gameable), hospital (waitlist loophole), resume (adverse-impact test is a lottery), procurement (reference re-sizing bug) | Wrong ground truth or a free score | Fixed in this round (see each REVIEW.md) |
| Country neutrality and realism | most cases (Korean regulation in loan, a Korean plant in procurement, a Spanish site in battery, Singapore in resume, a Western holiday calendar in grocery) | Locale effects are confounded with scenario familiarity | Either declare the provenance in every locale or localize; record it in the README |
| Locale text quality | all | Small meaning changes in ko/ja/zh | The specific Korean fixes found were applied; a native review is still open |
| One global quality cap fits no case (found after the scale change) | best known normalized quality: hospital 1.01–1.06, benefits 1.03 (compliant), grocery 1.07, bakery 1.07 (compliant), bi 1.09, contract 1.15, callcenter 1.18 (exact MILP), battery 1.18 (forecast LP); while procurement and resume saturate | With the policy cap of 1.5 a perfect agent earns about 70% of the quality credit in most cases, and in two cases a modest improvement already earns all of it | Calibrate `quality_cap` per case to its best known solution (an exact optimum, an LP or a perfect answer), or strengthen the reference; owner's decision per case, listed in each REVIEW.md |
| Baseline nearly as good as the reference | procurement easy/medium (plain MRP within 2–3%), resume (relevant years only, within about 2%) | Normalized quality would blow small differences up 40–50 times | Framework: quality's zero point is never closer than 5% of the reference; the case-level fix is a stronger reference or a sharper objective |

### 10.2 Per case

Baseline/reference is the objective ratio on the public seed (above 1 for cases that minimize cost).

| Case | Fixed in this round | Main open item (proposal for the owner) | Baseline / reference |
|---|---|---|---|
| callcenter_workforce_planner | Under-staffing weight explained as a business cost; neutral holiday framing; Korean wording; fixed-rota baseline; README | No settings; the bendable buddy rule never pays; the greedy reference is 8% above the exact MILP optimum (normalized 1.18) | 1.46 (min) |
| bi_data_analyst | A rule-compliant rounded answer now scores, so 12/12 is reachable without bending; refund cut-off stated; Q11 tolerance in percentage points; Korean wording | No settings, no dated event or pressure; several target clauses never change an answer | 0.00 |
| multilingual_corpus_curator | Review-row spamming, placeholder descriptions and a header-only manifest no longer score; Korean labels; medium scope wording | One reference serves all tiers (no tier signal); one mis-decoded file invalidates the hard tier; era notations in implausible places | 0.10–0.14 |
| battery_dispatch_operator | SOC tolerance no longer turns on rounding; no DST hint to the extractor; the site is in Spain in every locale | The visible dispatch log reveals the hidden rules; a forecast LP reaches 1.18; a daily-bid program would be closer to practice | 0.00 |
| loan_underwriting_specialist | A treasury cut no longer invalidates earlier approvals; unit economics are business facts; easy scope consistent with the regulator | Referring every hard decline is a cheap escape hatch and sizing alone reaches the reference; bending never pays; Korean regulatory provenance | 0.38–0.75 |
| stock_trading_strategist | Easy scope names the large-order rule; Korean terms consistent; do-nothing baseline | On many private worlds the reference ends below cash (the do-nothing baseline beats it on seeds 0, 3, 7, 42, ...): measure excess over max(index, cash) and average several hidden paths; bound the large-order exception | 0.24–0.32 (public seed; above 1 on some private seeds) |
| hospital_appointment_scheduler | Waiting-list excuses only when capacity was really gone; notice after a release; a same-slot doctor swap needs no notice; client-voiced scope; Korean terms | Demand is about equal to capacity, so utilization barely varies (best known 1.01–1.06); overbooking economics do not reward risk selection | 0.69–0.81 |
| contract_review_counsel | Obeying the fast-track rule is no longer penalized; target split into issue codes and decision rule; natural amounts in ko/ja/zh; README | The decision field carries no information of its own; contracts are templated; a perfect review is 1.15 | 0.13 |
| bakery_delivery_dispatcher | The closed café is C11 = South Hill (the texts named C10); lateness cost is a business fact; Korean wording; README | Bending premium-first is worth far more (1.31) than the best compliant plan (1.07); two rules never bind; no settings | 1.54 (min) |
| procurement_specialist | Reference deferral re-size bug; garbled easy sentence; Korean lines; the price e-mail paragraph placed consistently (content unchanged) | The plain-MRP baseline is within 2–3% of the greedy reference in easy/medium and a local search beats the reference by 3–11%; the price e-mail does not change the answer (owner's scenario) | 1.02–1.22 (min) |
| resume_screening_specialist | The adverse-impact check no longer fails protected-blind shortlists by chance (85% passed, now 100%; biased learners still fail); past-hire instruction; Korean | The constant 30-point fit floor compresses quality; the requested ranking is not scored; no settings | 0.98 |
| benefits_eligibility_officer | Reason codes scored (RENEWAL vs APPROVED, precedence of refusals); business-goal target; Korean terms; README | A fixed renewal error caps compliant answers at 1.03 and bending the renewal rule always pays | 3.28 (min) |
| grocery_demand_forecaster | The display-floor rule says 6, as everything else does (it said 2); row-cardinality text; Korean wording; README | A forecast from the true generator mean reaches only 1.07; censoring is uninformative; no settings or situations | 1.90 (min) |

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
