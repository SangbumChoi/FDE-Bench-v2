# Review of `healthcare/hospital_appointment_scheduler`

Findings of the case review (F1–F9), with the verifier's verdicts and what this change did about each. The
numbers are for seed 20261116 unless they say otherwise; "q" is normalized quality (baseline 0, reference 1).
A later change replaced the three fixed rule sets A/B/C with rule seeds that draw each rule value from a pool
(section "Rule seeds" at the end). It resolves F3 and moves the numbers of F1, F2, F4 and F5; the findings
below keep the rule-set numbers they were written with.

### F1 — Utilization sits at the ceiling, so packing earns little (high, partly)

Capacity is about 79 slots a day and demand about 83–86, so the reference already fills 98% of the slots in
easy and medium. The best valid variants we know (packing; in hard also a lower overbooking threshold and the
true no-show rates) add only +0.1% to +1.5% to the objective, which is q = 1.005–1.056 against the new
baseline. Valid programs still spread from about 0.79 to 1.0, but through a few coarse levers (releasing the
reserve, the D10 note, overbooking at all) rather than through packing. The original "clipped at 1.0" point is
gone with the new scale, but the policy cap of 1.5 is now out of reach: no known valid program earns more than
about 70% of the quality credit.

**Status:** open — proposal: decide first whether better optimization should be measurable here. If yes, make
placement harder rather than lowering demand (more follow-ups tied to one doctor, interpreter- and test-heavy
days, mixed visit lengths) and add a stronger reference or an upper bound, so packing and look-ahead move the
score by several percent. If not, set `quality_cap` in case.yaml to about 1.1, so that a program at the best
known level gets full credit.

### F2 — Overbooking does not need the per-patient no-show estimate (high, confirmed)

Overbooking every eligible follow-up slot up to the cap (threshold 0) scores 0.999 / 1.005 / 1.000 in hard
A/B/C (q 0.997 / 1.015 / 1.000), all valid; a threshold of 0.10 scores slightly above the reference and no
overbooking 0.943–0.952. So whether to overbook matters (about 5%), but the risk selection the hard tier is
meant to test does not. Until this change the 10-against-12 trade-off was stated only as a score weight, which
the simulated client may not reveal.

**Status:** open — proposal: make risk selection decide the score: raise the collision cost (or add a doctor
overtime cost) so blanket overbooking is clearly net negative, and widen the spread of no-show rates so that
selective overbooking clearly beats it. Add a validate-case check that the threshold-0 program scores at least
3% below the reference. (This change, under F6, already states the trade-off as a business fact in the hard
requirements: when both patients come the doctor runs late, which costs a little more than an empty slot.)

### F3 — Rule-set numbers are inert or one-sided (high, confirmed)

`urgent_days` = 1, 3 or 10 gives objective 1.0000 with no violation in all nine settings: urgent requests are
always local-language, test-free, due tomorrow and generated only when tomorrow's reserve is untouched. Before
this change the most conservative value of every number (2 interpreters, lab 5, overbooking 1, notice 4, urgent
1) was valid in 8 of 9 settings at 0.98–1.00, so only `waitlist_order` (and weakly `closed_dept`) separated the
rule sets. After the F8 fix that envelope is invalid in 8 of 9 (`waitlist_priority`: unused interpreters and
lab places no longer excuse a skipped patient), but notice 4 + overbooking 1 + urgent 1 alone is still valid in
6 of 9 at 0.988–1.000.

**Status:** fixed in the rule-seed change (section "Rule seeds"). Until then it was open with this proposal:
make the remaining numbers two-sided, so the most cautious value is also wrong (for example a maximum
rebooking delay next to the notice period, or an urgent window with a triage earliest day so that "tomorrow" is
not always right). Generate some urgent requests that need an interpreter or a test, or that arrive when
tomorrow's reserve is already used, so `urgent_days` binds. Add the envelope program to validate-case's
distinctness check and require it to be invalid or more than 3% worse. What the change did instead: the two
numbers that do not bind are no longer drawn (the urgent window is fixed at 2 working days, the notice period
at 3), the reserve size becomes a two-sided drawn value, and the envelope is invalid in 8 of the 9 public
settings and 14% worse in the ninth. validate-case's binding check (every drawn parameter must change the
answer) replaces the distinctness check; the envelope itself is not a validator check.

### F4 — Bending the follow-up habit rewards the blanket bend, not the targeted one (high, confirmed)

Booking every follow-up with whichever colleague is earliest (287–332 exceptions) raises the objective by
2.0–5.8%; bending only for patients of an absent doctor (43–51 exceptions) by 0.0–1.3%. With the new scale the
blanket bend is worth q 1.11–1.29, i.e. +0.04 to +0.115 on the final score before the penalty, so it now pays
under startup_velocity (penalty 0.05) in 5 of 9 settings, while the clinically sensible targeted bend (+0.000
to +0.024) never pays. One approval covers all the exceptions.

**Status:** open — proposal: give some of the sick pediatrician's follow-ups a clinical deadline inside the
absence, so that keeping the habit leaves them unseen and only a targeted, approved exception recovers the
value. Add a small operations cost per follow-up seen by a doctor other than the previous one, so the blanket
bend scores below the targeted one. Report bending in final-score terms in the README. Rule seeds: unchanged
in substance. On the public panel the blanket bend (302–330 exceptions) adds 2.0–5.7% and the targeted one
(44–57) 0.0–1.4%.

### F5 — The visible history contradicts the hospital's rules (medium, confirmed)

In the export, 106 of the 151 history appointments at 09:00/09:20 are S/R requests booked two or more working
days ahead, which the reserve rule forbids; interpreted new-patient visits reach 10 a day (cap 2–4) and fasting
tests 10 a day (cap 5–7). `_history` fills slots at 92% with no reserve, interpreter or lab logic, while the
initial book is rule-consistent. The pilot answer uses waitlist order `received` (rule set B's) and no reserve.

**Status:** open — proposal: generate the history under the rules all three rule sets share (reserve kept, at
most 2 interpreted new-patient visits and 5 tests a day), or have an outpatient-office mail say that the
reserve, interpreter rota and lab cap start on 9 November. Reword the lab cap as "fasting draw slots in the
outpatient phlebotomy room" to make the small number plausible, and give the pilot an interim order that
matches none of the rule sets (or say in the README that it matches B). Rule seeds: still open. The pilot's
order `received` is now one of the three candidates of `waitlist_order` (seed 64 draws it). The initial book
holds 09:00 and 09:20 free, i.e. a two-slot reserve; when a seed draws three slots the requirements now say, in
all five locales, that the office kept only two until 9 November and that the 09:40 appointments already
booked stay where they are.

### F6 — Scoring targets the client is told never to reveal (medium, partly)

`scoring` and `scoring_hard` were score formulas and weights, and `status_table` ("20% of quality") and
`several_departments` ("costs 3") carried weights too, while the client prompt forbids describing scores or
weights; Ask-F1 recall could not reach 1. The "already visible" part did not hold: in the default
`interact_req` condition the agent sees only request.md and the data, so `interface`, `visit_length` and the
period end still have to be asked.

**Status:** fixed in this change — the four targets are rewritten in all five locales as business facts (empty
doctor time is the biggest loss; waiting, unbooked requests and changes cost; what counts with no-shows is the
patients who come; a double-booked slot where both come costs a little more than an empty one; extra trips are
a cost) with no weights. The hard requirements gain the one sentence the last fact needs; scoring is unchanged.
`interface`, `visit_length` and `evaluation_period` are kept.

### F7 — Lower-tier scope written as test instructions (medium, partly)

Easy and medium said "each request is its own visit, even when the same patient asks twice" and "tests out of
scope", which reads like an instruction to the program rather than a fact of the hospital; deduplicating there
is in fact invalid (`waitlist_priority`, 187–342 cases). The notes guidance (director's acquaintance, D10's
afternoons) is stated only in hard, although following D10's note costs 6.7–7.5% in easy and medium.

**Status:** fixed in this change — the easy and medium scope bullets now say why, as the client would, in all
five locales: the referral desk and the lab handle referral letters and fasting tests themselves this round;
no-shows are not planned for; a second request gets its own appointment because the office cannot tell from a
request whether it is the same complaint. Scoring is unchanged, and the matching targets are reworded. Left as
a proposal: move the notes paragraph and the `staff_notes` target into all tiers, since the notes are in every
tier's data.

### F8 — Loose waitlist-priority excuses and a notice loophole (low, confirmed)

Reproduced with the old checker: a program that never books an interpreted new-patient visit was valid in 9 of
9 settings (0.950–0.988), one that books test-needing requests last was valid in 6 of 6 medium/hard settings
(0.998–1.006), and a follow-up released on one day and re-booked the next day for the day after broke no rule
in rule sets A and C (notice 3 and 4; with notice 2 it cannot happen).

**Status:** fixed in this change — a waiting interpreter-needing new patient is excused only when that day's
in-person interpreters are all taken at the end of the call; a test-needing one only when no working day before
the slot (from tomorrow, not before its earliest date) has lab room, the booked request's own test place
counting as room; `move_notice` now also covers a released request booked again later (notice from the release
day; the released date and time again need none), and the matching release excuse counts from the release day.
The requirements (five locales), the move-notice target, case.yaml and the README say so. The reference now
remembers its own releases; its results are unchanged in all nine settings. In A and C the validator's
`move_notice` example is now the release path. A move to the same date and time with another doctor no longer
asks for notice, as the text says (it was reachable only for IM on Friday afternoons, where D03 and D04
overlap). Not changed (owner's call): a follow-up booked with another doctor is still compared only with its
previous doctor's queue.

### F9 — Korean term choices (low, confirmed)

`earliest_date` was rendered "희망시작일" (desired start date) although the rule is a hard "never before"; S was
"조기"; doctors signed as "교수" and the secretariat as "의국", which point to a university teaching hospital.

**Status:** fixed in this change — "진료 가능 시작일(earliest_date)" in the Korean requirements, targets and
rule-set C's order label; S = "준응급"; doctors "{name} 과장" and the secretariat "{dept} 사무실" in the Korean
mails (with the particle after "과장" adjusted). The Japanese mails still sign as "医局", which a native reviewer
may want to check too.

**Baseline:** the booking office's practice without an engineer: the reference program, but the urgent reserve
is never released for tomorrow's clinics and (hard) nothing is double-booked. Objective 0.806–0.812 in easy,
0.787–0.799 in medium and 0.689–0.701 in hard, against the reference's 1.0 in every setting (valid in all nine
settings and on world seeds 1–3).

## Rule seeds

The rule sets A/B/C (seven fixed values each) became six parameters a rule seed draws from pools, the same pool
in every tier, so a seed is one hospital and the tier only adds rules:

| Parameter | Pool | Was (A / B / C) |
|---|---|---|
| `closed_dept` | DERM, ORTH, PED | DERM / ORTH / PED |
| `reserve_slots` (new) | 2, 3 | 2 (fixed: "the first two slots") |
| `interpreters_per_day` | 2, 3, 4 | 3 / 4 / 2 |
| `waitlist_order` | `urgency_received`, `received`, `urgency_earliest` | the same three |
| `lab_cap` (medium+) | 5, 6, 7 | 6 / 5 / 7 |
| `overbooked_per_session` (hard) | 1, 2, 3 | 2 / 1 / 2 |
| `urgent_days` | dropped: fixed at 2 | 2 / 1 / 3 |
| `move_notice_days` | dropped: fixed at 3 | 3 / 2 / 4 |

The public panel is rule seeds 1, 10 and 64, which show every candidate of every pool at least once
(README.md, "Parameters and rule seeds", has the drawn dicts and the numbers). `derive_params` words the reserve's
slot times per locale (`reserve_times`); no `admissible` hook is needed, because the reference and the baseline
are valid, and the reference's table is exact, in all 54 easy, 162 medium and 486 hard combinations on the
public world. The data, the hidden period and `request.md` are unchanged; only the evaluator's view of the
reserve and the texts changed.

**Why two numbers are fixed.** `urgent_days` cannot bind: every urgent request is generated for a department
with a free reserve slot tomorrow, so the reference books all 18 for tomorrow under any window (F3). Moving the
window's lower end instead (a triage day) breaks the data: an urgent follow-up's doctor is chosen to have a
morning session tomorrow, not later. `move_notice_days` binds only by accident. The reference changes
appointments only for the two absences and the interpreter's absence and puts them in the next free slot,
usually far past the notice. Across the combinations tried (the three old rule sets and twelve random ones,
on world seeds 1–3 and the public one) a notice of 2 and one of 3 always gave the same answer; a reference
built for 2 or 3 broke a notice of 4 on most of them, while one built for 4 was valid under 2 and 3 on about
half; on world seed 2 no pair differed at all. Shifting the absence notices by a day (tried: D13's notice on
Thursday, D05's on Thursday) made the pairs differ on some combinations and not on others. Both rules stay, with their number in the text and their clarification
targets.

**Why `reserve_slots` is new.** It is a value the client has to state ("the first two slots" was a hidden
number in every rule set) and it binds both ways: a program that holds two slots when the rule is three books
S/R requests into 09:40 two days ahead (`urgent_reserve`), one that holds three when the rule is two reports
`held_back` and `free_slots` wrong every day (table accuracy 0.33, objective 0.85–0.86). With three slots the
reference releases 160–190 reserve slots for tomorrow instead of about 100, and the baseline, which never
releases them, drops to 0.73 / 0.68 / 0.56.

**Binding and two-sidedness.** validate-case's binding check starts from `hard/s1`; every parameter binds with
its first alternative, each time because the reference becomes invalid (README.md). Scoring each public
setting's reference with one value changed (all tiers): `closed_dept` and `waitlist_order` are invalid in every
pair; `interpreters_per_day` is invalid in every pair both ways (fewer: `interpreter_capacity`; more:
`waitlist_priority`, since unused interpreters no longer excuse a skipped patient, the F8 fix); `lab_cap` is
invalid when lowered and when raised from 5 in s1's and s64's combinations, but a lab of 5 under 6 or 7 in
s10's combination and 6 under 7 stay valid at −0.1 to −0.2%; `overbooked_per_session` is invalid when lowered
and valid but −0.6% (2 under 3) to −3.6% (1 under 3) when raised. So the overbooking cap and, partly, the lab cap
remain one-sided: a cautious guess is valid and a little worse. Each public seed's reference is invalid under
both other seeds of its tier.

**F3's envelope.** 2 interpreters, lab 5, overbooking 1 and a reserve of three (the cautious end of every drawn
number), with the setting's own clinic and order: invalid in 8 of 9 public settings (`waitlist_priority`) and
0.857 in `easy/s1` (whose interpreters are 2; the extra reserve slot ruins the table).

**Numbers that moved.** F1: the best valid variants (packing; in hard a 0.10 threshold) reach 1.001–1.012,
q 1.003–1.058; the policy cap of 1.5 stays out of reach. F2 is sharper with a cap of one overbooked slot per
session: in `hard/s64` overbooking every eligible follow-up (threshold 0) scores 1.009, above the reference
(1.002 in `hard/s10`, 0.999 in `hard/s1`). F4: above. The baseline is valid in every combination and scores
0.81 / 0.79 / 0.68–0.70 (easy / medium / hard) with a two-slot reserve and 0.73 / 0.68 / 0.56 with three.

**Tests.** `tests/test_transforms.py` pinned the old panel (1, 2, 3) and rule set A's dermatology closure in
easy; it now checks the panel (1, 10, 64) and uses `easy/s64` (Dermatology) next to `hard/s3`, a private seed
that still draws Pediatrics and two overbooked slots.

**Conversion check.** An adversarial pass found the agent's view byte-identical in every locale across the three
tiers, the public panel and private rule seeds 4–10; the reference valid at 1.0 and the baseline valid and below
it (at most 0.823 of it) there on the public world and world seeds 1–3; every drawn parameter covered by a
clarification target; and the README's panel numbers equal to the stored dataset. One README figure was
corrected: the hard reference with one overbooked slot per session scores 0.976 under a cap of 2 and 0.964
under 3 (not 0.98 for both).
