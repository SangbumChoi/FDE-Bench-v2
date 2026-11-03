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
