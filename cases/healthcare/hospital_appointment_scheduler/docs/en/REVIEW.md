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
this change the most conservative value of every number (2 interpreters, lab 5, overbooking 1, notice 4,
urgent 1) was valid in 8 of 9 settings at 0.98–1.00, so only `waitlist_order` (and weakly `closed_dept`) separated the
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

## Ground truth audit

The case is now `audited: true`. `dataset/audit.json` holds the audit of the public world (`fdebench2 audit-case`:
per tier the public panel and 12 admissible combinations of the tier's candidates, 45 settings),
[GT.md](../../GT.md) the ground truth in five parts generated from it by `gt_report.py`, and
[CLIENT_REVIEW.md](../../CLIENT_REVIEW.md) the passages of requirements.md each locale answers each target from,
with a machine pre-check (awaiting human review). Before this change the audit found no hook at all: 24 targets
without an ablation or a diagnostic, no shortcut, no never-asks program, no best known solution or bound and no
quality cap. What changed, in the order it was done:

1. **What the agent sees now shows the office's old practice, and only that** (data changed, the same in every
   setting; resolves F5 for the reserve and the diagnosis of DIRECTION §10.1, "hidden requirements readable from
   the visible data"). The export's four weeks keep 09:00 and 09:20 for urgent patients (24 of the 200 reserve
   slots held one; the rest stayed empty; before, 106 of 151 held S/R patients booked days ahead), 74 of the 571
   follow-ups were seen by a colleague of the patient's doctor (exceptions the head granted), and the initial book
   leaves 09:00 and 09:20 empty on 9 November too. The pilot program keeps the reserve as well and reports
   `held_back` 0. So the natural reading of the data is the office's practice, and the client's facts differ
   from it: the reserve is released for tomorrow (`reserve_release`, new), the table holds the reserve back
   (`status_table`), follow-ups stay with their doctor (`follow_up_doctor`). The facts a careful agent can read
   off the data stopped being targets: `visit_length` (every appointment carries its slots), `no_show_rates`
   (every request carries the patient's record and the attendance table the lead effect), and `interface` and
   `evaluation_period` (the deliverable spec is shown in every condition).
2. **Shortcuts closed before the reference was touched** (`shortcuts()`, 16, each closed in all 45 settings):
   booking nobody (invalid: urgent window), booking only the urgent requests, first come first served with no
   slot held back, the earliest slot with any doctor, the office's practice with the pilot's table, the
   reference's bookings without a table, with a zero table or with the morning's table, and the literal program
   with each client rule it breaks kept, or all of them. Two changes closed what was open: the status table is a
   mandatory output (`status_table`, a new contractual rule with a violating example: a call without it, or a
   table without a department's three whole numbers) and the objective is the operations ratio **times** the
   table's accuracy (was 0.8 × the ratio + 0.2 × accuracy, under which the pilot's table, right on a third of
   the entries, kept 0.87 of the objective); the departments staff their clinics from the table, the client says
   in all five locales. `referral_validity`, enforced by the engine but missing from case.yaml since the rebuild,
   is declared.
3. **One fact per target.** The 24 targets became 18. Split: `urgent_reserve` (its size, `param: reserve_slots`,
   and `reserve_release`), `blood_test` (the test day, and `lab_cap`, `param:`), `overbooking` (two follow-ups to
   a slot, and `overbooking_cap`, `param:`), `scoring_hard` (`collision_cost`; the expected-value counting is how
   the objective works). `easy_scope` and `medium_scope` became one fact per subject, in force in every tier
   where the client must say how to treat it, with tier-specific text: `duplicates`, `overbooking`,
   `referral_expiry`, `blood_test`, `doctor_absence` (easy and medium say what is out of scope, medium and hard
   what is in). `staff_notes` is in force in every tier, as its paragraph moved out of hard (F7's proposal).
   Removed, kept in requirements.md as context: `interface`, `evaluation_period`, `visit_length`,
   `no_show_rates` (item 1), `urgent_window` (a window of 1, 2, 3 or 10 days gives the same program, F3),
   `scoring` (the request states it), `several_departments` (keeping two departments on one day moves at most
   0.01 of the scale). Every target has an ablation (the reference with one switch flipped: the most natural
   misreading of the agent's view; GT.md part 1) and bites in every tier where it is in force: fifteen in every
   measured setting, `overbooking` in 12 of 15 hard settings, `collision_cost` in 15 of 15 (0.18–0.42), and two
   below half, which the audit warns about: `interpreter_absence` (6 of 15 medium, 2 of 15 hard: ignoring the
   notice overfills the day only where it is full when the notice comes) and `overbooking_cap` (6 of 15: a cap
   one lower costs little, one higher is invalid).
4. **Facts that changed nothing were made to bite, in the client's terms.** The lab: more requests need a fasting
   test (internal medicine and cardiology 30%, pediatrics 12%, were 20% and 8%), so the lab is full on the days
   that matter and a cap guessed one lower passes over test-needing patients the lab could take (a priority
   breach): `lab_cap` bites in 15 of 15 settings of both tiers (was 5 and 6 of 15). Overbooking (F2): a
   collision costs three empty slots (30, was 12, "a little more than one"), and the patients are of two kinds,
   one in six missing most appointments (rates around 0.6) and the rest rarely (around 0.06), which only their
   record shows; the reference now doubles up a follow-up where that is worth more than its free slot or than
   waiting. Never overbooking loses 0.09–0.16 of the scale, pairing blind 0.18–0.41, and the true rates would add
   0.035–0.051 (GT.md part 3). The two parameters that varied where nothing used them now have a single candidate
   there: `lab_cap` 6 in easy, `overbooked_per_session` 2 in easy and medium (DIRECTION §10.2; validate-case no
   longer warns).
5. **Bending (F4).** A follow-up seen by a colleague now counts a tenth of a slot less (−1 a visit, the client
   says why in all five locales). Bending every follow-up gains 0.07–0.23 of quality with the rule relaxed (it
   gained 0.09–0.27 before), only the absent doctors' patients 0.00–0.08, only tomorrow's idle slots 0.02–0.10.
   Net of the soft-rule penalty the best bend pays in 3 of the 9 public settings under `enterprise_balanced` and
   7 under `startup_velocity`, and loses or breaks even in the others (GT.md part 2).
6. **Diagnostics.** `score()` keeps a private trace of the program's own run, and `diagnose()` reads it: rule
   breaches with what they concern, the placements and releases, the doubled-up slots, the reported table against
   the true one and the tables of each misreading, and the overbooked pairs' chances. A priority breach is given
   to the one reading that explains every request it passed over and the most breaches (an interpreter, a blood
   test, a referral date, a second request, a note, another order). The diagnostic separates every target from
   its ablation, never calls the best known solution not enforced, and no ablation flags another target.
7. **Reference and bounds (F1).** The reference is unchanged apart from overbooking (item 4) and the switches the
   misreadings and shortcuts use. `best_known_solution` tunes it on the hidden period (packing; in hard the true
   no-show rates and the overbooking rule's two values): 1.000–1.144 of quality, median 1.024, so
   `quality_cap` is 1.03 (the policy's 1.5 was out of reach). `objective_bound` is a proven LP relaxation with
   perfect information (scipy's HiGHS, under a second a setting); it drops the order, the reserve, interpreters,
   the lab and arrival times, and in hard counts every visit at a day's lead, so it is 15–20% above the reference
   in easy, 22–28% in medium and 58–67% in hard.
8. **Value of asking**: 1.00 in every tier. `robust_solution` (the export's practice, the pilot's table and order,
   no cost for a collision and the strictest candidate of every drawn rule, even given the tier's scope) is
   invalid wherever its order or interpreters are wrong and below the baseline wherever it is valid (its table is
   the pilot's). The references of the other settings, which know every fixed fact, earn 0.07 on average (the
   drawn values are worth 0.93).
9. **The literal solution** is invalid in all 9 public settings, as delivered and with the bendable habit relaxed
   (City Day closure and waitlist order everywhere, plus interpreters, reserve, lab or duplicates by setting); with
   every client rule kept it is valid and below the baseline.
10. **Round 2026-11** (rule seeds 108807, 519122, 904685): in all nine settings the reference and the baseline are
    valid, the scale is 24–56% wide and the literal solution is invalid as delivered and with the habit relaxed.

**Texts.** requirements.md (five locales): the release of the reserve as its own bullet with the office's old
practice; the colleague's tenth of a slot; the notes paragraph in every tier; "no overbooking" in easy's no-show
bullet; the hard no-show paragraph (one in five missed, mostly by a minority) and the collision cost of three empty
slots; the table as part of every day's job; the quality formula. targets.yaml rewritten in five locales;
summary.yaml and explainer.yaml (the two new rules and the shortcuts' wording) in five locales.

**Tests.** `tests/test_transforms.py` checked that `overbooking` is a hard-only target; it is in every tier now
(easy and medium say there is none), so the test checks `overbooking_cap` instead.

**Still open.** `interpreter_absence` and `overbooking_cap` bite in fewer than half of their settings (warnings).
The bound is loose, above all in hard. No person has reviewed CLIENT_REVIEW.md yet. The urgent window still binds
for no reasonable program (F3). The Japanese mails still sign as 医局 (F9).

## Ground truth audit: adversarial check

A second engineer checked the audit above by running code against it (in-process replays of the reference
program with one switch at a time, over each tier's 15 measured settings and the round-2026-11 seeds) and changed
what it confirmed. Every change is the same in every setting; the agent's data is unchanged, its program interface
changes by two words (item 1).

1. **A wrong table entry is a cost, not a factor** (the check's main finding). With the objective the operations
   ratio × the table's accuracy, a slip in one count was close to fatal wherever the baseline sits near the
   reference (0.74–0.77 of the objective in most easy and medium settings): on the public settings one entry
   wrong every day lost 0.12–0.29 of the quality scale, one department's row 0.36–0.86, one column 0.6–1.0, and a
   program that books exactly like the reference but counts the expired referrals in `waitlist` (medium) kept
   0.0004 of medium/s10. The table's definition is a real client fact (the departments staff their clinics from
   it, and the pilot's `held_back` 0 is internally inconsistent: the pilot holds the reserve), but a client does
   not throw away a month of bookings for one wrong number. Now every entry that is not exact costs 20 in the
   operations value (two empty slots: "the department staffs for a wrong number"), in requirements.md,
   targets.yaml (`status_table`) and summary.yaml in all five locales. One entry wrong every day costs 0.10–0.16,
   a row 0.30–0.50, a column 0.50–0.83, the expired referrals counted 0.28–0.64, the pilot's table everything
   (GT.md part 3); every degenerate table still scores 0. case.yaml's deliverable spec said the table is "as in
   the pilot-day output file", which reads as "with the pilot's numbers' meaning"; it now says "in the format of"
   (the zh, ko and ja reading translations already did; es changed with it).
2. **`interpreter_absence` bites in 29 of 30 settings (14 of 15 medium, 15 of 15 hard)** (was 8 of 30): the interpreter is away on Friday 20 November,
   announced on Tuesday 17 November (was Thursday 26, announced Tuesday 24, a day that rarely reached the
   interpreters' number, so ignoring the notice usually overfilled nothing). The hidden period's notice and mail
   only.
3. **`overbooking_cap` cannot bite more in the client's terms.** It bites in every setting where the cap is 1
   (any guess above it is invalid) and nowhere else: the second and third overbooked slot of a session carry
   little (a cap of 1 where the client allows 2 loses 0.02–0.04 of the scale, 2 where it allows 3 at most 0.01),
   because the whole of overbooking is worth 0.09–0.17. Making it bite would need overbooking to be worth three
   to five times more, which no collision cost or no-show mix the export supports gives. The warning stays.
4. **The never-asks program was not the strongest.** Its docstring called its guesses the strictest, but the
   waitlist priority rule makes too few interpreters or lab places as invalid as too many (a waiting patient who
   needs one, passed over while the client's interpreter was free, is a priority breach), so the old program was
   invalid wherever its interpreter guess was off, not only where it was too high. `robust_solution` now reads
   the two fixed facts that carry the literal solution's failure at their strongest: the program runs once a day
   after the clinics, so tomorrow's reserve slots that today's urgent requests leave empty can serve nobody else
   and are given to the waitlist, and `held_back` counts the reserve it still holds (the export's two slots); it
   takes the safe side of every drawn rule that has one and the pilot's order and three interpreters and the
   middle lab cap otherwise. Value of asking 0.964 in easy (it is valid in 1 of the 15 easy settings and earns 0.54 there), 1.00 in medium and hard (was 1.00 everywhere). Tried and rejected: keeping every
   candidate order at once (dropping each booking some candidate order forbids, repeatedly) is valid in all 15
   easy settings but keeps about a quarter of the reference's operations value (−0.05 with the interpreter and
   lab numbers hedged too); the best single combination of guesses, chosen on the measured settings themselves,
   reaches 0.07 (easy), 0.10 (medium) and 0.04 (hard) with the fixed facts granted; with the export's practice and
   the pilot's table a never-asking program earns 0 everywhere (keeping the reserve caps it at the baseline).
5. **Shortcuts** (20, and 21 in hard, each closed in all 45 settings): five new ones, all closed without a change: copying the office and releasing the
   reserve with the pilot's table (at most 0.022), the pilot day's table numbers every day (constants), the
   literal program with every rule kept and the reserve released (at most 0.022) or with the client's table
   (exactly the baseline: the literal program with every rule kept is the office's practice), and in hard the
   office's practice with blind overbooking and an exact table (at most 0.066). Overbooking blind with
   everything else right is not a shortcut but `collision_cost`'s misreading (0.59–0.82).
6. **The literal solution is an honest reading.** It and the next most natural literal readings (the round's
   scope read as easy's, nothing held back because the pilot reports `held_back` 0, the history's figures of 8
   interpreters and 14 tests a day, both of those, the reserve released with the pilot's table) are invalid in all
   9 public settings, as delivered and with the follow-up habit relaxed.
7. **Diagnostics.** Three correct programs that differ from the reference (packing, booking at most 8 days
   ahead, hard without same-day clustering and with an overbooking margin) are called enforced on every target in
   force in 45 of 45 cases (five settings a tier); six new misreadings were caught in 38 of 55 cases in easy and
   medium before, and in 85 of 85 in the three tiers after two fixes:
   a table that also holds tomorrow's empty reserve back is now a reading of `status_table` (it was called
   enforced), and S/R bookings from 09:20 on while 09:00 is kept read the reserve's size (`urgent_reserve`), not
   its release.
8. **Texts.** The two differences the pre-check flagged are gone: ko's waitlist bullet named `earliest_date`, es's
   lab bullet named `book`; both now say it in words, as en does. The ko and ja targets `reserve_release` and
   hard's `duplicates` were reworded to read naturally (the release as something the office does, "the same need"
   as a request for the same visit).
9. **Checked, no change.** The ablations are the natural misreadings and change only their fact (the
   `move_notice` misreading bites in easy only through pulling booked patients forward, which a program that
   thinks changes are free and need no notice does to fill tomorrow; in medium and hard a day's notice alone is
   invalid). `visit_length` and `no_show_rates` can be read off the data in every locale (every appointment
   carries its slots, 2 for every new patient and 1 for every follow-up; every request carries the patient's
   record, and the export's attendance gives a lead slope of 0.0098 against the true 0.01). The five locales'
   exports agree on every id, number and date; nothing visible differs between settings. The bound: making the
   LP's bookings integral (HiGHS MILP, 120 s on hard/s1) moves it from 1.621 to 1.608 of the reference, so its
   looseness is the relaxed rules, not fractions; a longer coordinate search (31 moves, four passes) beats the
   best known by 0.004–0.005 of quality in hard. Best known median on world seeds 1, 2, 3 (public panel): 1.031,
   1.022, 1.006; over the audit's 45 settings it is 1.019 (was 1.024), so `quality_cap` is 1.02. Round
   2026-11: every target in force bites in at least one round seed of each tier, the
   reference and baseline are valid, the scale is 23–54% wide, the literal solution is invalid in all nine.

**Still open.** F5's caps: the export's history still runs up to 8 interpreted new-patient visits and 14 fasting
tests a day, above every candidate of the client's caps (it misleads, it does not leak a drawn value). Several
facts are satisfied by a careful program that never thinks of the misreading (`follow_up_doctor`: book the
`previous_doctor`; `duplicates` and `overbooking` in easy and medium: book each request, one a slot;
`staff_notes`: ignore the notes; `move_notice` in easy: never move anyone); they bite because their misreading,
which an optimizing program makes, is invalid, not because the data hides them. `overbooking_cap` bites in 6 of
15 (item 3). The bound is loose in hard. No person has reviewed CLIENT_REVIEW.md.
