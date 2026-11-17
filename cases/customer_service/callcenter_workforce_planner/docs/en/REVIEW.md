# Review of `customer_service/callcenter_workforce_planner`

Findings of the case review, with the verifier's verdict and what this change did about each. The numbers
are for the public seed 20261109 unless stated otherwise; quality is normalized with the new baseline
(fixed rota = 0, greedy reference = 1).

## Rule seeds

The case was converted from one fixed problem to the rule-seed contract (DESIGN.md, Settings): three tiers on
the same data and request, and five parameters that a rule seed draws from candidate pools. This resolves F2
and parts of F3, F4, F5 and F6 (statuses below).

- **Tiers.** easy is the core staffing problem (languages, shift types, weekly caps, one shift a day, leave,
  the under-staffing weight); its requirements say in the client's words that the holiday, overtime pay, rest
  times and new-hire pairing are out of scope this round. medium adds the rest rule, the Wednesday holiday,
  overtime beyond the contract week and the buddy rule. hard adds a dated sick call against a team lead's
  pressure note.
- **New data file.** `team_lead_note.txt` (localized name in every locale), the same in every setting: the team
  lead of the sick agent's main language writes on Thursday 5 November that the agent "will be fine by Monday,
  just roster them as usual". In easy and medium that is true; in hard the client received a doctor's
  certificate on Friday morning that keeps the agent off sick up to the drawn `sick_until`. The agent is derived
  from the world (an experienced full-timer with no leave request in the scarcest language), so the
  requirements point to the note instead of naming them. No existing data file changed.
- **Parameters.** `under_weight` 15 / 25 / 40 (every tier); `ft_week_hours` 32 / 40 with derived
  `ft_regular_shifts` 4 / 5 and `ft_max_shifts` 5 / 6 (every tier: the cap; from medium: overtime beyond the
  contract week); `holiday_factor` 0.5 / 0.6 / 0.75 (medium, hard; 1.0 in easy); `min_rest` 11 / 13 hours
  (medium, hard; 0 in easy, where the rule is one shift a day); `sick_until` Tuesday 10 / Wednesday 11 /
  Thursday 12 November (hard; Sunday 8 November, i.e. back on Monday, in easy and medium). 12 hours of rest
  forbids the same shift pairs as 11 (F6), so it is not a candidate. No combination is infeasible, so the case
  has no `admissible()`.
- **Rules.** New: `one_shift_a_day` (easy) and `sick_leave` (hard). `min_rest` is now contractual (F6) and
  applies from medium; `buddy_rule` applies from medium. `max_shifts` reads the drawn cap.
- **Public panel** `rule_seeds: [10, 2, 3]`: every candidate of every pool appears. Seed 10 (weight 40, 32 h,
  holiday 50%, rest 11 h, sick until Wednesday) comes first because the binding check runs there and every
  parameter binds in it, on the public world and on world seeds 1–3 (weight −16.2%, contract week −3.6%,
  holiday +7.1%, rest and sick leave: the reference becomes invalid). A panel led by a seed that draws rest 13
  h or sick until Thursday would fail the binding check for those parameters at the public world seed: the more
  lenient value leaves the reference valid and its objective, and the lenient setting's own reference, within
  1%.
- **Code.** `score`, `reference_solution`, `baseline_solution` and `violating_examples` read the setting through
  `rules_for(world, setting)`; the greedy reference and the fixed-rota baseline are unchanged in method. At the
  old single setting (weight 40, 32 h, holiday 60%, rest 11 h, no sick call) the reference is 25,584 and the
  baseline 37,376, as before, and the exact MILP optimum is 23,464, as before.
- **Validator:** OK on the public seed and world seeds 1–3, with no warnings.

### F1 — The greedy reference is far below the optimum (high, confirmed)

An exact MILP of the same model (scipy HiGHS, about 2,000 binaries, proven optimal in about 8 s) reaches
23,464 against the reference's 25,584 (ratio 1.090; 75 against 183 under-covered agent-slots). At review time
quality was clipped at 1.0, so this headroom earned nothing and ignoring the holiday, the overtime premium or
the weight cost nothing. With the new framework (not clipped above, full credit at the policy cap of 1.5) and
this baseline, the optimum scores 1.180, an optimum that ignores the holiday 1.145, and one that ignores
overtime or the weight 1.172. These gaps now count, but they are small.

**Status:** open — proposal: keep the greedy as the reference and set `quality_cap: 1.18` in `case.yaml`, the
MILP optimum's normalized quality at this seed (1.1798). The optimal objective is unique, so the value is
deterministic. The optimum would then earn full credit and the reference 0.85, not 0.67 against the default
cap. World seeds 1–3 reach 1.135–1.177, so on private seeds the cap is a little above what can be reached.
A validator check that ignoring each quality-only target costs at least 3% would also need F3 and F5 retuned.

**Status (rule seeds):** still open, numbers updated. Across the nine public settings the greedy is 0.5–8.1%
above the exact optimum, whose normalized quality is 1.03 (easy/s3, weight 15) to 1.17 (medium/s2). One
`quality_cap` for the case cannot fit every setting: 1.17 would leave easy/s3's optimum at 88% of the credit.
The greedy is also beaten by itself in places (planned with weight 40 when it is 25, or without overtime at
seed 10, it scores 1.01–1.03). Options: leave the cap unset (as now), set it to the lowest optimum (about
1.03), or replace the greedy with a stronger reference (the MILP needs scipy, which is not a dependency).

### F2 — No settings (high, confirmed)

`setting.json` is `{}` and there is one ground truth, so the easy, medium and hard columns are the same
problem and the case adds nothing to the difficulty curve. The under-staffing weight alone would make usable
rule sets: the optima at W = 15, 25 and 40 use 109, 116 and 126 shifts, and cross-score 0.908–0.991.

**Status:** open — proposal: convert to 3 tiers × 3 rule sets on the same world. Rule-set parameters: the
weight (e.g. 12/25/40, so that each rule set's reference is at least 1% worse under the others), the holiday
day and factor, the overtime threshold, the part-time cap and the rest hours (13 h forbids S1400 → S1000).
Tiers: easy is the core rostering, medium adds rest, holiday, overtime and the buddy rule, hard adds the
uncertain parts. Per the verifier, calls + handling time for an Erlang C tier would have to be in the visible
data in every tier, and a mid-week re-plan would make the whole case a program deliverable.

**Status (rule seeds):** fixed — three tiers and five drawn parameters (section "Rule seeds" above). The weight
pool is 15 / 25 / 40, the holiday day stays Wednesday with a drawn share, the overtime threshold follows the
drawn contract week, rest is 11 or 13 hours; the part-time cap stays 3. Within a tier, a rule seed's reference
is invalid under the other public seeds in 11 of 18 pairs and scores a quality ratio of 0.82–0.96 in six; in
one pair (easy, seed 10's reference under seed 2) it is 0.5% better than seed 2's own greedy, a weakness of the
greedy (F1). Hard took the dated sick call and the team lead's note, not the Erlang C step, for the verifier's
reason.

### F3 — Compressed quality ratio; the weight swamps labor cost (medium, partly)

One shift (A01, Monday, S0800, en) was a valid roster with ratio 0.378, and the empty roster's ratio would be
0.376. The weight of 40 per half-hour (80 per agent-hour, against rates of 22 and 18) makes almost any shift
pay for itself, so the optimum uses 126 of 130 possible shifts. The weight had no stated meaning.

**Status:** fixed in this change — the requirements in all five locales now state what the 40 means: it is in
the same units as the hourly rates and is the client's estimate of what one agent missing for half an hour
costs in abandoned calls, callbacks and missed service levels (the number is unchanged). The high floor is gone
with the baseline normalization: the one-shift roster scores −2.57, floored to 0. Still open — proposal: lower
the weight into the 15–30 range or vary it by rule set (F2), where overtime and the choice between full-time
and part-time actually bind. The suggested minimum-coverage hard gate is infeasible in this world (the
verifier: only 4 senior zh agents).

**Status (rule seeds):** fixed — the weight is drawn from 15 / 25 / 40 and the requirements state it as a
business cost in every locale. At 15 a full-time shift needs 12 of its 16 slots to fill a gap and the reference
uses 98–107 shifts; at 40 it uses 115–128. Planned with the wrong weight, the greedy scores 0.59–0.91 (40 when it
is 15, 15 when it is 25 or 40); planned at 40 when it is 25 it loses nothing (1.00–1.02).

### F4 — The bendable rule never pays, no pressure or dated events (medium, confirmed)

`buddy_rule` is the only bendable rule. Bending it improves the optimum by 0.58% (23,328 against 23,464), and
by 0–2.3% on other seeds. That is about 0.01 of normalized quality, and less on the composite, well below
the soft-rule penalty of 0.05–0.1. The case has no stakeholder note, sick call, forecast revision or late leave approval; only the
generic `messy` engagement events exist.

**Status:** open — proposal: shape the data so that bending pays a visible but bounded amount, e.g. a zh
evening or Sunday where the only zh-capable agent left is new hire A12, worth about 3–8% against the
reference. Add a team-lead note ("A12 can handle Chinese alone on Sunday night, just put them on") as the
temptation that has to go through the exception process. Add a dated event, e.g. a sick call or a late leave
approval on Thursday delivered as an inbox correction.

**Status (rule seeds):** partly fixed — the hard tier has a dated sick call and a team lead's pressure note. The
note (`team_lead_note.txt`, in the data of every setting, sent Thursday 5 November) asks to roster the sick
agent "as usual, we can't spare them"; in hard the client received a doctor's certificate on Friday morning
that keeps the agent off sick from Monday to the drawn `sick_until`. Following the note breaks `sick_leave`
(2 violations for the greedy in every hard setting). In easy and medium the note is right, so the same data
reads differently by tier. Still open: the bendable buddy rule still pays little, and the buddy temptation
(a note to put a new hire alone on a language) would bite from medium on, where the buddy rule applies, so it
was not added; that needs the data shaping proposed above.

### F5 — Hidden facts that do not bite (medium, partly)

Ceiling rounding on small integers blunts the holiday: 106 of the 140 Wednesday cells stay unchanged, so
Wednesday demand drops from 265 to 229 agent-slots (−13.6%, not −40%), and ignoring the holiday costs the
optimum only 1.180 → 1.145. Treating the rejected request (A03) as leave leaves the optimum unchanged. The
rejected row read `12/11/2026–13/11/2026`, and a day above 12 gives day/month/year away. Some targets
(`slot_coverage`, the contract part of `contract_limits`) can be read off the column names.

**Status:** fixed in this change (the date only) — the rejected request now stays within Monday 9 to Thursday
12 (A03 reads `12/11/2026–12/11/2026`), so the public data has no day above 12. A rejected request never
affects scoring, so no world's optimum changes. Read as month/day, the dates still land in September to
December, so an attentive agent can still infer the format. In world seeds 1 and 3, approved Friday–Sunday
leave still shows days 13–15. Not reproduced: the rest part. An optimizer that does not know the rule produces
13 `min_rest` violations, so rest is a hard trap that bites. Still open — proposal: put the demand in larger
units (e.g. 2–12 per slot) or round to nearest, so that ignoring the holiday costs at least 3%. Give the
rejected request to a scarce agent on a peak day. Mark targets that can be inferred from the data, or drop
them, so that Ask-F1 does not reward asking for them.

**Status (rule seeds):** partly fixed — the holiday's share is drawn from 50% / 60% / 75% (medium, hard), so
Wednesday's demand is 176, 229 or 255 agent-slots instead of 265. Ignoring it costs the greedy 0.12–0.13 of
normalized quality at 50%, 0.03 at 60% and nothing at 75%; the rounding is unchanged (round up, as a planner
would). Rest bites in every medium and hard setting (the greedy planned without it breaks `min_rest` 1–7 times;
planned with 11 h under 13 h, 8 times). The rejected-request and inferable-target parts are unchanged.

### F6 — Realism and rule classes (medium, partly)

A full-timer's normal week is 4 shifts (32 h), with the 5th as overtime. Shifts count in all 16 slots with no
breaks, and the forecast is already in agents, which skips the Erlang C step of workforce planning. `min_rest`
is classed physical although it is a labor rule, and 11 h is below Spain's statutory 12 h (Estatuto de los
Trabajadores, art. 34.3). The rates have no currency. The verifier notes that a 32 h contractual week is unusual
but lawful, and that reclassifying `min_rest` changes no score (both classes are hard in every policy).

**Status:** open — proposal: make the normal week 5 shifts (40 h) with overtime beyond it under a 6-shift cap,
or say explicitly that the contract is 32 h. Reclassify `min_rest` as contractual and keep "one shift at a
time" as the physical rule. Use 12 h of rest in every locale: with these shift times it forbids exactly the
same shift pairs as 11 h (no pair is 11 h apart), so only the text and `MIN_REST` change. Name the cost unit (e.g. "cost units", or a localized currency with scaled numbers). Leave breaks
and Erlang C for a hard tier (F2).

**Status (rule seeds):** partly fixed — the full-time contract week is drawn: 32 h (4 shifts, cap 5) or 40 h
(5 shifts, cap 6, the 6th shift overtime); the client states it in the requirements. `min_rest` is now
contractual and drawn from 11 h (EU minimum) and 13 h (a stricter company agreement, which also forbids the
12-hour turnarounds); 12 h is not a candidate because it forbids the same pairs as 11 h. In easy the only rule
on consecutive shifts is `one_shift_a_day` (contractual: two part-time shifts on one day do not overlap, so it
is not physical). Still open: the cost unit is unnamed, breaks and Erlang C are not modeled (hard took the sick
call instead, F2).

### F7 — Locale wording and country neutrality (low, confirmed)

Numbers agree across the five locales, but 11 November as a low-volume public holiday clashes with Singles'
Day for a Chinese client. The Korean text repeated 근무 ("근무하는 근무 하나당"), used the translationese
"신입이 아닌 상담원", buried the formula in a long parenthesis with a unitless 40, and labeled full-time as
정규직 (permanent employment). Names are Latin-script in every locale and drawn regardless of skills (e.g.
"Haruto Kim" speaks only ja).

**Status:** fixed in this change — the holiday is now "a regional public holiday in our main market" in the
requirements and the target of all five locales (date and 60% unchanged). Korean: "상담원 1명의 근무 1회당 항목
1개입니다", "기존(신입이 아닌) 상담원/동료" in the requirements and the target, and the quality paragraph now
names its two parts and gives the 40 its unit ("부족한 상담원 1명·30분당 40(인건비와 같은 단위)"). Full-time is 풀타임
in the data label (`고용형태`), the requirements and the targets. Still open — proposal: render names per
locale (Hangul, kanji/kana, hanzi) or tie them to the agent's main language.

### F8 — The roster format is not shown to the agent (low, partly)

The agent is told that no file format was specified. The exact JSON shape is only in the hidden requirements,
so a roster of about 120 rows may pass through the extractor, and one mistranscribed row makes it invalid. The
verifier notes that one question to the client gets the format, that a `roster.json` written by the agent is
copied directly, and that the extractor can convert a CSV with a script. The "agent-visible" label in the
explainer has since been fixed in the framework.

**Status:** open — proposal: add a deterministic pre-parser for common roster shapes (CSV/xlsx with agent, day,
shift and language columns, localized language names) before the LLM extractor, and log violations the
extractor introduced apart from the agent's. Alternatively, put a roster template in the workspace. Either is a
framework or design decision, not a case fix.

**Baseline:** fixed rota (one shift all week in the main language, 4 regular days for full-timers and 3 for
part-timers, new hires shadowing a senior), objective 37,376 against the reference's 25,584 (ratio 0.685) at
seed 20261109; 36,776–37,848 against 25,232–25,440 on world seeds 1–3. The case has no settings.

**Baseline (rule seeds):** the same fixed rota, with the drawn contract week (4 or 5 days for full-timers) and,
in hard, the sick days left empty. In the nine public settings it is 16–63% above the reference (objective
ratio 0.62–0.86): 23,722–38,176 against 20,047–24,288 at seed 20261109.

## Ground truth audit

The case is now `audited: true`. `dataset/audit.json` holds the audit of the public world (`fdebench2 audit-case`:
per tier the public panel and 12 admissible combinations of the tier's candidates, 45 settings), [GT.md](../../GT.md) the
ground truth in five parts generated from it by `make_gt.py`, and [CLIENT_REVIEW.md](../../CLIENT_REVIEW.md) the passage
of requirements.md each locale answers each target from, with a machine pre-check (generated by
`make_client_review.py`; awaiting human review). The agent's view (request and data) is unchanged and byte-identical
in every setting. What changed, in the order it was done:

1. **The literal solution's failure carried by the client's facts (DIRECTION §11.6).** Before, the literal roster
   (unchanged, byte for byte) was invalid in easy only through the part-time cap of 3; with that one rule kept it
   scored 0.68–0.98. The client's rules now differ from what the view suggests in several places, in every tier:
   - **the rest time applies in every tier** (11 or 13 hours, drawn; easy's "one shift a day, rest checked on the
     floor" scope is gone): the literal plan's 22:00 → 08:00 turnarounds break it in every setting;
   - **both contract weeks are drawn** (`ft_week_hours` 32/40 as before, `pt_week_hours` 12/16, new): the
     literal's usual five-day week breaks the full-time week at 32 hours and the part-time week always;
   - **the holiday applies in every tier, on a drawn day** (`holiday_day` Tuesday 10, Wednesday 11 or Thursday 12
     November, new) at a drawn share of 25% or 50% (was Wednesday at 50/60/75%, from medium);
   - **in easy nobody works beyond the contract week** (no overtime this round), from medium an extra full-time
     shift needs the operations manager's approval (`overtime_approval`, see Bending).
   As delivered and with the bendable rule relaxed, the literal roster is invalid in all 9 public settings and in
   all 45 audited ones; with any one rule it breaks kept (`literal_plus_max_shifts`, `literal_plus_min_rest`,
   `literal_plus_overtime_approval`, `literal_plus_buddy_rule`, `literal_plus_sick_leave`) it is still invalid
   everywhere, on the public world and on world seeds 1–3.
2. **Economics.** The price of a missing agent is drawn from 17 / 50 (was 15 / 25 / 40): a cost-driven center
   against one that cannot afford to miss calls. Under the new rules a price of 15 would put the fixed rota below an
   empty roster in the 40-hour settings (the rota's shifts would not pay for themselves, and the scale's zero point
   must be the client's own way); at 17 they do, and the reference planned at the other price loses up to 0.26 of the
   scale.
3. **Shortcuts closed** (`shortcuts()`, each closed in all 45 settings): a single shift (the F3 roster that once
   scored 0.38; quality ≤ 0 now), the fixed rota (0), the rota without new hires (at most 0.29), the rota on the
   peak shifts (0), constants (every experienced agent on the first shift from Monday, 0), part-timers only (at
   most 0.20), Monday alone (at most 0.07), and the literal solution plus each rule it breaks (invalid).
4. **One fact per target; inferable facts out.** The 12 targets became 9. Split or new: `understaffing_price` (was
   `understaffing_penalty`), `ft_contract_week` and `pt_contract_week` (from `contract_limits` and `overtime`),
   `holiday` (was `holiday_wednesday`), `overtime_approval` (new). Removed from the targets, kept in requirements.md
   as context, because a careful agent reads them off its own data in every setting: `slot_coverage` (the forecast's
   column is `agents_needed` per `slot_start`), the shift-type half of `contract_limits` (`shifts.csv` has a
   `contract` column) and `leave_dates` (read as month/day every date falls outside the November week asked for; a
   rejected request says `rejected`). `one_shift_a_day` and `easy_scope` went with the rules they described. Four
   targets are exactly a drawn parameter (`param:`); the other five have an ablation in `ablations()` (the reference
   planner with the most natural misreading: a bilingual agent counted on two languages, the forecast uncut, overtime
   planned at the plain rate, new hires like anyone else, the team lead's note followed). Every target bites in
   every tier where it is in force (GT.md, part 1).
5. **Reference (F1).** The greedy is replaced by `_Planner`: each agent's week re-planned exactly (a dynamic program
   over the seven days) given everyone else's, agents in turn, then pairs of agents who share a language re-planned
   together. It is 0.3–7.0% above the exact optimum (the greedy was 0.5–8.1% above it under the old rules and 1–14%
   under the new ones). `best_known_solution` is that optimum, a MILP solved by HiGHS (scipy) to proven optimality,
   and `objective_bound` its dual bound (best known = bound in every setting). Best known quality 1.009–1.098, median
   1.034: `quality_cap` = 1.04. The greedy stays only as the literal solution's planner.
6. **Diagnostics.** `diagnose()` reads each rule off the roster (contract weeks, rest, overtime, buddy, sick days)
   and measures every other fact against the planner's roster under each other reading (GT.md, part 5). It separates
   the reference from every ablation that bites, and calls the optimum enforced on every target in every setting.
7. **Never asks** (`robust_solution`): the planner on the forecast as it is with the strictest candidate of every
   rule and the price hedged at the geometric mean. It is valid everywhere and earns 0.84 / 0.70 / 0.71 of the credit
   (`voi` 0.16 / 0.30 / 0.29 by tier). Other never-asks rosters (another price hedge, a guessed day cut to 75%) do
   no better than 0.01 above it.
8. **Rule class.** `buddy_rule` is now contractual (the client's training agreement), not a bendable habit: as a
   business policy it paid nothing to bend (F4), and the case's bendable rule is now `overtime_approval`.
9. **The sick call bites.** The last day of the doctor's certificate is drawn from Wednesday 11, Thursday 12 or
   Friday 13 November (was Tuesday 10 to Thursday 12). Following the team lead's note cost nothing when the
   certificate ended on Tuesday (0 of 8 sampled hard settings: the planner gives that agent their four or five shifts
   from Wednesday on anyway), about half the time on Wednesday, and nearly always on Thursday or Friday. On the old
   pool the hard reference of rule seed 10 was byte-identical to medium's.
10. **Public panel** `rule_seeds: [10, 2, 11]` (was [10, 2, 3]): seed 11 draws the Thursday holiday and the price 17,
   so every candidate of every pool appears.

### Bending

`overtime_approval` (business policy) is the bendable rule: with an approved exception a full-timer may work one
shift beyond the contract week, paid 1.5 times. Measured with the exact optimum, rule relaxed against rule kept, in
medium and hard: at price 50 and a 32-hour week it pays 3–8% of the objective (normalized quality up to +0.11, e.g.
1.08 → 1.19); at price 50 and 40 hours 0–1.5%; at price 17 nothing (the optimum takes no overtime shift), so an
exception there only costs the policy's soft-rule penalty. The bound's scope is rosters that keep the rule.

### Findings resolved

- **Literal solution (DIRECTION §11.6, "callcenter, easy")**: resolved, section 1.
- **F1**: resolved: the stronger reference, a proven bound and `quality_cap` 1.04 (section 5).
- **F3**: the one-shift roster is a closed shortcut (quality ≤ 0 in every setting).
- **F4**: resolved for bending (the bendable rule now pays in some settings and not in others); the dated sick call
  and the team lead's note stay in hard.
- **F5**: the holiday bites (a drawn day and a deep cut: 0.05–0.23 of the scale when planned uncut), the inferable
  targets are out.

### Still open

- The value of asking is 0.16 in easy (a warning below 0.30): a never-asks roster on the strict side of every rule is
  valid and loses only what the longer contracts, the holiday and the price would have bought.
- Cross flags (warnings): in medium and hard at 32 hours a fifth full-time shift is both "the contract week read as
  40 hours" and "overtime without approval"; a roster cannot tell the two apart, so each ablation also flags the
  other target.
- `min_rest` bites in 17 of its 45 settings (a warning): the stricter rest is valid and cheap where 11 hours is
  allowed; the looser one breaks the rule only where the plan uses a 12-hour turnaround.
- F6 (cost unit, breaks, Erlang C), F7 (names per locale) and F8 (the roster format) are unchanged.

## Ground truth audit: adversarial check

A second pass over the audit above, which re-ran every claim on its branch and changed what it could not confirm.
The agent's view (request and data) is unchanged and byte-identical in every setting. In order:

1. **The never-asks solver was beaten, so the value of asking was overstated.** The audit's `robust_solution` (the
   planner on the strict side of every rule, the forecast uncut, the price at the geometric mean of the candidates)
   earned 0.842 / 0.704 / 0.710 of the credit. On the same 45 settings, the exact optimum of the *expected*
   objective over every price, holiday day and holiday share of the tier's pools, on the same strict side, earns
   0.873 / 0.832 / 0.798: asking was worth 0.127 / 0.168 / 0.202, not 0.158 / 0.296 / 0.290. That stochastic
   program is now `robust_solution` (`_milp` with scenarios: one shortfall variable per cell and need level, priced
   at the probability-weighted price). It reads the pay as the view suggests, by the hour. On the final case it
   earns 0.767 / 0.778 / 0.749, and other never-asks rosters do no better: weighting the scenarios by 1/price
   (closer to credit) gains at most 0.003, reading the guaranteed weeks and the training salary right (which the
   view does not say) at most 0.005, leaving the holiday unhedged loses 0.004–0.017, and the 40-hour, 16-hour or
   11-hour gambles are invalid in about half the settings (0.29–0.64). Only an in-sample oracle weighted by the
   measured settings' own scales gets 0.001–0.022 more.
2. **The facts made to matter more, the same way in every setting.** On the case as it was, knowing one fact was
   worth, to the stochastic never-asker of easy / medium: the price 0.013 / 0.008, the holiday 0.080 / 0.092, the full-time week 0.001 /
   0.072, the part-time week 0.032 / 0.027, the rest time 0 / 0. Changes:
   - **Guaranteed weeks.** A part-timer's contract hours are guaranteed (paid in full even with fewer shifts), and
     new hires are on a training salary (their contract week paid whether or not they are on the phones);
     experienced full-timers are paid by the shift as before. Planning a 12-hour week under a 16-hour contract now
     wastes paid hours: `pt_contract_week` bites in 41 of 45 settings (was 24). The training salary is a new
     target, `training_salary` (the most natural reading of `labor_cost.csv` is that a new hire is paid by the shift
     like everyone else): planning new hires that way loses up to 0.33 of the scale, in 15 of 45 settings, all at
     the price 17 (1 / 5 / 9 by tier; at 50 a new hire's shift pays for itself anyway).
   - **The holiday on any weekday:** `holiday_day` is drawn from Monday 9 to Friday 13 November (was Tuesday to
     Thursday), so a never-asks roster has to hedge five days instead of three.
   - The value of asking is now 0.233 / 0.222 / 0.251 (the warning below 0.30 stays): a roster on the strict side of
     every rule is still valid everywhere and loses only what the longer contracts, the holiday, the price and the
     training salary would have bought.
   - Tried and dropped: salaried full-timers (the price no longer decides anything: it bites in 0 of 45 settings);
     a cost for a language left with nobody (the fixed rota leaves 230–290 language-slots empty, so the scale
     widened and the value of asking fell to 0.14 / 0.15 / 0.20); the low price raised to 25 (the price bites in 0
     of 45).
3. **One target for the full-time week.** `overtime_approval` is folded into `ft_contract_week`: from medium its text
   says that a shift beyond the contract week (one at most, at 1.5×) needs the operations manager's approval. The
   client states the cap and the approval in one breath (requirements.md says "without that approval a full-timer
   works at most N shifts"), an agent that knows the contract week plans no overtime without being told, and at 32
   hours the two ablations were the same planning problem (cap 5 at the plain rate), hence the 26-of-26 and 22-of-31
   cross flags. The rule `overtime_approval` (business policy) stays, and so does the literal plus that rule.
4. **New shortcuts.** `weekdays_only` (the planner's roster for Monday to Friday, the weekend empty),
   `no_new_hires` (the buddy rule kept vacuously: the planner's roster without the new hires) and `one_shift_each`
   (the planner with one shift a week each). The engineer's set missed the first two: on their branch they scored
   up to 0.60 and 0.97. With the training salary `no_new_hires` keeps at most 0.515 (open in 1 of 45 settings);
   `weekdays_only` keeps up to 0.59 at the price 17 (open in 13 of 45; at 50 at most 0.29). Both are listed in
   `validate.OPEN_AUDIT_FINDINGS` with the reason: at 17 the client's own objective values the whole weekend at
   under half the scale, and the closures tried (above, and a rule that every line is staffed every day, or that
   every new hire works) either take the price's role away or make the client's own rota invalid on other worlds.
   Also tried and not listed: every agent in their first language only (0.96–1.03: a correct roster), every shift
   the planner can fill (the price read as infinite: 0.66–1.00, an ablation of the price), a roster with one agent
   per language at the weekend (0.48–0.71: a thin weekend, not an empty one).
5. **Diagnostics.** The holiday is now also checked against a cut on each other candidate day (at the true share):
   a roster that cuts the wrong weekday was called enforced before and is caught now. On rosters that are neither
   the reference nor an ablation (the 9 public settings): correct but different (the exact optimum, the optimum with
   two experienced agents' weeks swapped, the optimum under a 16-hour rest pattern, the reference with two weeks
   swapped) 36 of 36 called enforced on every fact; new misreadings caught: the holiday on another weekday 9 of 9, a
   20-hour part-time week 9 of 9, overtime planned without approval 6 of 6 (medium, hard), the sick leave read a day
   short 3 of 3, the holiday share misread 3 of 9 (the other six lose under 5% of the scale, below FOLLOWS_GAP by
   design), a price hedged at 29 0 of 9 (it loses 1–6%). The two holiday misreadings also flag
   `understaffing_price` in the three s10 settings (price 50, Monday at 25%), where a misplaced cut looks like the
   cheaper price's roster.
6. **GT.md** said the leave dates read as month/day all fall outside the week asked for. They do not: 11/11 reads
   the same either way, and 10/11–11/11 and 10/11–12/11 read as month/day overlap it. What makes day/month the
   reading a careful agent takes is that every request then lies inside 9–12 November. Corrected in GT.md and
   README.md.
7. **The literal solution** (code unchanged) is an honest reading. The next most natural readings, one change each,
   are invalid in all 9 public settings as delivered and with the bendable rule relaxed: part-timers on three days
   instead of five (still the 22:00 → 08:00 turnarounds), or a stable shift per agent that respects any rest (still
   five part-time shifts). A reading that changes both (a stable rota and part-timers on three days) is valid in
   easy at 40 hours and scores 0.67–0.94: the literal's failure in easy rests on the rest time and the part-time
   week.
8. **Bending** (re-measured with the exact optimum, rule relaxed against kept, 30 medium and hard settings): at
   price 50 and 32 hours an approved overtime shift makes the optimum 2.9–8.2% cheaper (+0.03 to +0.13 of quality),
   at 50 and 40 hours 0–1.5%, at 17 nothing (the optimum takes no overtime shift): `overtime_approval` pays to bend
   in some settings and only costs the policy's penalty in others.
9. **Reference and bounds.** The MILP is proven optimal (HiGHS status 0, gap 0, dual bound = objective) in all 45
   audited settings and in the same 45 combinations on world seeds 1, 2 and 3, in at most 90 seconds each (the time
   limit is 300 s); the reference takes at most 6 s per setting. With the new hires' paid weeks the planner is
   0.3–8.1% above the optimum (it was 0.3–7.0%), the optimum's quality is 1.008–1.114 with median 1.052 (1.037,
   1.046 and 1.055 on world seeds 1–3), so `quality_cap` is 1.06 (was 1.04).
10. **Round 2026-11 seeds** (108807, 519122, 904685; every one draws the price 50): the holidays are now Wednesday
    50%, Thursday 25% and Thursday 50%. In all nine settings the reference and the baseline are valid, the scale is
    57–91% wide and the literal solution is invalid, as delivered and with the bendable rule relaxed. Every target
    bites in at least one round seed of each tier where it is in force except `training_salary`, which bites only
    at the price 17 and so in none of them.
11. **Texts.** requirements.md, targets.yaml, summary.yaml and explainer.yaml in all five locales: the guaranteed
    part-time week, the training salary (a new target), the holiday on any weekday, the full-time week with its
    overtime approval, the new shortcuts. CLIENT_REVIEW.md's machine pre-check finds the same numbers and
    identifiers in every locale.

### Still open (adversarial check)

- `weekdays_only` and `no_new_hires` are open shortcuts, listed in `validate.OPEN_AUDIT_FINDINGS` (section 4).
- The value of asking stays below the 0.30 warning (0.23 / 0.22 / 0.25): a roster on the strict side of every rule
  is valid everywhere.
- `training_salary` bites in 15 of 45 settings (all at the price 17) and in no round seed; `min_rest` in 18 of 45.
- The ablation of `one_language` also breaks the buddy rule in 24 of 45 settings (a bilingual experienced agent
  counted on the new hire's language is not there): the facts interact.
- The literal solution's failure in easy rests on the rest time and the part-time week (section 7).
