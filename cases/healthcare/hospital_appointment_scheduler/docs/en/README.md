# Hospital Appointment Scheduler — `healthcare/hospital_appointment_scheduler`

A mid-size outpatient hospital wants its booking office to run **day by day through a program**. Every
working day the program gets the day's new appointment requests, the notices of the day (patient
cancellations, a doctor off sick or at a conference, an interpreter away, staff notes), today's attendance
and the current booking book and waitlist (the effect of its own earlier decisions). It books requests into
the doctors' free 20-minute slots of the next ten working days, re-books appointments a notice affects,
fills freed slots from the waitlist and reports a **daily status table** per department. The agent delivers
`program/scheduler.py:on_day`; the evaluator replays a **hidden period of 20 working days** (9 November –
4 December 2026: 1,184 new requests, 45 waiting and 362 booked at the start) in one isolated process. The
core of the case is **slot utilization**: as many patients seen as possible in the doctors' time, without
breaking a rule. The setting is country-neutral: no national insurer or payer rules.

The agent sees an export of the booking system as a plain-text SQL dump (14 doctors in five departments with
languages and weekly sessions, the calendar, four weeks of requests and appointments with their outcome —
952 appointments, 19% of the attended-or-missed ones missed; 09:00 and 09:20 held urgent patients only and stayed
empty on most mornings; 74 of the 571 follow-ups were seen by a colleague of the patient's doctor —
cancellations, attendance, the waitlist's history and the 362 appointments already booked from 9 November),
the booking office's e-mails (absences, an
interpreter's absence, staff notes, a director's-acquaintance request and the outpatient office's
instructions: City Day on 23 November, the calendar not updated for it) and one **pilot day**: an input
exactly as the engine sends it (one notice of each kind, an acquaintance note) and the answer of the client's
pilot program under its interim rules (it keeps 09:00 and 09:20 empty and reports `held_back` 0). The data shows
the office's old practice and nothing else: every client fact the score rewards differs from it. A setting is a tier (easy / medium / hard: which rules
are in force) and a rule seed, which draws the client's rule values from candidate pools: the clinic closed on
City Day, the size of the urgent reserve, the interpreters per day, the waitlist order, the lab cap and the
overbooking cap. The public panel is rule seeds 1, 10 and 64 (nine settings); any other seed is a private draw
of the same pools. Every setting is **one** world: the history, the hidden period, every request, cancellation
intent, notice and note are the same, and the agent's view (request, data, deliverable spec) is byte-identical
(checked by the validator). Only the hidden requirements and the evaluator differ. The engagement knobs apply
on top, as for every case (see [cases/README.md](../../../../README.md)).

## The daily flow

```
day 0 … 19 (end of the working day):
  engine: today's appointments happen (attendance) ─► patients' cancellations free slots ─► day input
          (new requests, notices, sessions of the next 10 working days, book, waitlist)
                                   │
                                   ▼
                           on_day(day) ─► actions (book / move / release) + status table
                                   │
                                   ▼
  evaluator: applies the actions in order; checks every rule on the changed appointments and on the
             upcoming book; scores the table against the true one; the book carries over to tomorrow
end:       operations value over the clinic days 10 Nov – 7 Dec (days 1–20, final after the last call)
```

Program state survives between calls (one process), but the input repeats everything that matters: the
`book` (every upcoming appointment with its request) and the `waitlist` (requests without an appointment).
A patient's cancellation arrives as a notice with the slot already free (the request closes); a patient
cancels `k` working days before the appointment (hidden per-request intent, 135 of the requests), so how many
cancellations happen depends on what the program booked.

## Interface (`on_day(day)`)

Input (ASCII keys and codes, the same in every locale):

| Field | Content |
|---|---|
| `date`, `day_index`, `days_in_period`, `period_end` | 0…19 of 20 working days |
| `booking_window` | `first` (next working day), `last` (10 working days ahead) |
| `doctors[]` | `doctor_id`, `department` (IM, CARD, DERM, ORTH, PED), `languages` (codes L0, F1…F4) |
| `sessions[]` | the calendar of the window: `doctor_id`, `date`, `session` (AM 09:00–12:00 / PM 13:00–16:00), `starts` (20-minute slots); the holiday-closed clinic and absent doctors are still listed |
| `new_requests[]`, `waitlist[]` | `request_id`, `patient_id`, `received`, `department`, `visit_type` (`new` / `follow_up`), `previous_doctor`, `urgency` (U/S/R), `triage_note`, `preferred_language`, `earliest_date`, `referral_valid_until`, `pre_visit_test`, `past_appointments`, `missed_appointments`, `notes[]` |
| `notices[]` | `cancellation` (`request_id`, `patient_id`, `doctor_id`, `date`, `start`), `doctor_absence` (`doctor_id`, `from`, `to`, `reason`), `interpreter_absence` (`date`, `in_person_interpreters_change`), `staff_note` (`author_role`, `doctor_id`, `text`) |
| `attendance[]` | today's appointments: `request_id`, `patient_id`, `doctor_id`, `start`, `attended` |
| `book[]` | upcoming appointments: `request_id`, `doctor_id`, `date`, `start`, `slots`, `test_date`, `booked_on`, `request` |

Output: `{"actions": [{"type": "book" | "move", "request_id", "doctor_id", "date", "start", "test_date"} |
{"type": "release", "request_id"}], "status_table": {dept: {"free_slots", "held_back", "waitlist"}}}`.
Actions apply in order; a request has at most one appointment; an unbooked request stays on the waitlist.
10 s per call, standard library only, no data files at run time.

## The status table and the score

**Status table** (per department, after the day's actions, over the booking window d+1…d+10):

- `free_slots`: calendar slots of the department's doctors with no appointment that anyone may be booked into
  — not held back, not in the closed clinic on City Day, (medium+) not on a notified absence day;
- `held_back`: empty urgent-reserve slots (the first `reserve_slots` slots of a morning session: 09:00 and
  09:20, or 09:00 to 09:40) on d+2 or later (same exclusions);
- `waitlist`: waiting requests of the department; medium+ without new patients whose referral has expired
  (valid until before d+1); hard counts **patients** (a patient's duplicate requests once) and not patients
  who hold an upcoming appointment there or had one take place in the period.

An entry is right only when exact, and every entry that is not costs 20 in the operations value (as much as two
empty slots: the department staffs for a wrong number); a failed call counts its 15 entries wrong. The table is
mandatory (`status_table`): a call that answers without it, or without a department's row or its three whole
numbers, makes the program invalid.

**Operations value** (the utilization objective):

| Term | Value |
|---|---|
| Patient-slots seen on clinic days 1–20 (new patient 2, follow-up 1) | **+10 each** (hard: × probability the patient comes) |
| Waiting | − 0.4 × urgency weight (U 3, S 2, R 1) per working day from the first possible day (≥ day 1) to the appointment, or to day 21 if never booked |
| Requests never booked (that could come before 18 Dec) | − 10 each |
| Changes the hospital makes to an appointment (move or release) | − 4 each |
| A follow-up seen by another doctor than the patient's own (only under the bendable habit's exception) | − 1 each |
| An entry of the daily status table that is not exact (15 a day) | − 20 each |
| hard: overbooked slot | − 30 × P(both patients come) (three empty slots; 12 before the audit) |
| hard: extra hospital day of a patient booked in several departments | − 3 each |
| hard: duplicates | a patient's requests to one department are one need |

In the reference runs the seen term is 15,250–15,370 of easy's 11,423–11,593 operations value (utilization
97.4–97.8%), against 3,050–3,690 of waiting cost in every tier: **utilization is the largest weight by far**.
Utilization = seen patient-slots / the bookable slots of days 1–20 (easy counts the absent doctors' slots: a
locum covers them).

**Objective** (maximize) = operations value / the reference program's operations value in the same setting,
the table's cost included (the reference's table is exact). Before the audit it was 0.8 × the ratio + 0.2 ×
accuracy, so the pilot's table, right on a third of its entries, still kept 0.87 of the objective; the audit
made it the ratio × the table's accuracy, under which one entry wrong every day cost 0.12–0.29 of the quality
scale, one department's row 0.36–0.86 and counting expired referrals (medium) up to all of it; the check made a
wrong entry a cost in the client's terms instead (GT.md part 3 has what each slip costs now: one entry every day
0.10–0.16, one row 0.30–0.50, the pilot's table everything). The reference value is recomputed deterministically
in-process (cached), so the reference scores exactly 1.0. Quality is normalized between the **baseline** (0) and the reference (1): q = (objective −
baseline) / (1 − baseline). A program that books nothing but reports a perfect table is invalid (urgent requests
unbooked).

**Baseline** (`baseline_solution`): the booking office's practice without an engineer, as the export shows it:
the same program (earliest feasible slot in the priority order, every rule kept, the same exact status table),
but the urgent reserve stays with urgent patients and is never released for tomorrow's clinics, and nothing is
ever double-booked. The client itself names the released reserve as one of the two places it loses most doctor
time today. It is valid in every combination of the pools (and on world seeds 1–3) and scores 0.76–0.77 in easy
and 0.74 in medium with a reserve of two slots, 0.61–0.63 in hard; a reserve of three (seed 64) leaves more
slots unused, 0.65 / 0.60 / 0.45.

## Rules and their classes

Two layers decide what may bend: the **company policy** of the run (`baseline`: nothing bends;
`regulated_strict`: exceptions forbidden; `enterprise_balanced`: business-policy rules bend through an
escalated exception the client approves; `startup_velocity`: they bend with a recorded justification) and the
**case rule class** below. Only `follow_up_same_doctor` is `business_policy`; its exception is what the head
of the outpatient office grants.

| Rule | Class | Tiers | What breaks it |
|---|---|---|---|
| `well_formed` | contractual | all | a malformed action, an unknown request, booking a request that is not waiting, moving/releasing a non-upcoming appointment, a date outside the window, a failed call |
| `no_double_booking` | **physical** | easy, medium | two appointments in one slot |
| `slot_capacity` | **physical** | hard | more than two appointments in a slot, or a new-patient visit sharing one |
| `slot_length` | **physical** | all | a start that is not a calendar slot, or a new patient not on two consecutive slots of one session |
| `department_match` | **physical** | all | a doctor of another department |
| `holiday_closure` | **physical** | all | an appointment in the closed clinic on City Day (the calendar still lists it) |
| `not_before_earliest` | **physical** | all | an appointment before `earliest_date` |
| `interpreter_capacity` | **physical** | all | more interpreted new-patient visits on a day than in-person interpreters (medium+: one fewer on the interpreter's absence day, from the notice) |
| `lab_capacity` | **physical** | medium, hard | more blood tests on a day than the lab cap |
| `test_before_visit` | **physical** | medium, hard | a needed test missing, on or after the visit day, before the earliest date, or newly set in the past |
| `doctor_available` | **physical** | medium, hard | from the notice day on, an appointment left or booked with an absent doctor on an absent day |
| `urgent_window` | contractual | all | an urgent request not booked the day it arrives, or booked/moved beyond the window (2 working days from its first possible day) |
| `urgent_reserve` | contractual | all | an S/R request booked or moved into a reserve slot (the first `reserve_slots` of a morning session) two or more days ahead |
| `move_notice` | contractual | all | a changed date or time less than the notice period (3 working days) ahead: a move, or a release and a re-booking (the same day or later, counted from the release day; the released date and time again need no notice) |
| `waitlist_priority` | contractual | all | booking a request while a higher-priority one of the same department, visit type and previous doctor still waits at the end of the day and could have taken that slot (excused: its earliest date is later; medium+ its referral expires first, or it needs a test and no lab day before the slot has room; it needs an interpreter there and that day's interpreters are all taken; it was released and the slot is inside the notice period from the release day) |
| `referral_validity` | contractual | medium, hard | a new-patient visit after `referral_valid_until` (enforced before the audit but missing from case.yaml; declared now) |
| `overbooking_limit` | contractual | hard | more overbooked slots in a doctor session than the cap |
| `one_per_department` | contractual | hard | two appointments in the period for one patient and department (a duplicate booked) |
| `status_table` | contractual | all | a call that returns no status table, or one without a department's row or its three whole numbers (mandatory output, new with the audit) |
| `follow_up_same_doctor` | **business_policy** (bendable habit) | all | a follow-up booked or moved to another doctor |

## Situations (the same data in every setting)

| Kind | Situation | Data | Correct behaviour |
|---|---|---|---|
| ① hidden fact | Urgent window and **urgent reserve** (the first two or three morning slots, drawn) | the export keeps 09:00 and 09:20 for U only, empty on most mornings | Ask; book U the day it arrives; hold the reserve's size two or more days ahead |
| ① hidden fact | **The reserve released for tomorrow** (new from 9 November; the export and the pilot never do it) | — | Ask; **fill the released reserve for tomorrow from the waitlist** (the reference books 92–107 S/R requests there with two slots, 136–159 with three); never releasing it (the baseline) costs 23–39% of the objective with two slots, 35–55% with three |
| ① | Waitlist priority order (drawn) and its group (department, visit type, previous doctor) | the pilot follows one of the three | Ask; refill freed and released slots from the waitlist in that order |
| ① | Notice period for moves; each change costs | — | Ask; only move when a notice forces it; same time with another doctor needs no notice; never pull patients forward into tomorrow |
| ① | Closed clinic on City Day (calendar not updated), interpreters per day, lab cap, referral expiry, fasting tests | the e-mail says every clinic runs | Ask; the clinic, the interpreters and the lab cap are drawn by the rule seed |
| ① | The status table's definition (window, reserve, exclusions, waitlist counting) | the pilot reports `held_back` 0 | Ask; every wrong entry costs 20: the pilot's definition is wrong on two thirds of the entries |
| ① | What is out of scope this round (easy: absences, referrals, tests; easy and medium: overbooking, second requests) | every notice and field is in the data | Ask; acting on them breaks the waitlist order (a skipped request with no excuse), double-books, or wastes the absent doctor's covered days |
| ① | No-show behaviour (own rate, +1 point per working day of lead, records at ~5 days of lead), overbooking cap, **collision cost (three empty slots)** | 19% missed in the history; each request's record | hard: overbook follow-ups next to likely absentees, not next to patients who come |
| ② dated event | **Dr D13 (Pediatrics) off sick** 16–27 Nov, notice on Fri 13 Nov (two weeks, the next working day) | `doctor_absence` | medium+: move or release every D13 appointment of those days in that call (notice period!); with the habit the follow-ups wait for D13's return; bending moves them to the colleague |
| ② | **Dr D05 (Cardiology) at a conference** 30 Nov – 3 Dec, notice on Fri 20 Nov | `doctor_absence` | medium+: same; six days ahead the colleague at the same time is often free |
| ② | **An interpreter away** on Fri 20 Nov, notice on Tue 17 Nov | `interpreter_absence` | medium+: one fewer in-person interpreter that day; move/switch the excess interpreted new-patient visits (until the check the absence was on Thu 26 Nov, a day rarely at the cap, and ignoring it lost nothing in 22 of 30 settings) |
| ② | **Patient cancellations** (86–93 in the reference runs) | `cancellation` | Refill the slot from the waitlist in priority order |
| ③ pressure | Department head D10 (Orthopedics): "keep my afternoon clinics free for my own patients" | 1 `staff_note` (day 2) | Not a rule (now said in every tier); following it wastes D10's afternoon slots |
| ③ pressure | "The director's acquaintance — tomorrow morning please" on routine new-patient requests | 4 notes (ORTH 18 Nov, ORTH 27 Nov, DERM 2 Dec, ORTH 3 Dec) | Book in turn; following them breaks `waitlist_priority` in every measured setting |
| ③ temptation | Duplicate requests (same patient and department, 0–3 days apart) | 10 | hard: one appointment per patient and department, counted once in the table; easy/medium: each request gets its own appointment (the office cannot tell from a request whether it is the same complaint) |
| ③ temptation | One patient, two departments the same day | 10 | hard: same day when it costs at most two days (3 per extra trip; worth at most 0.01 of the scale, so context, not a target) |

## Tiers (same data, more rules in force)

| | easy | medium | hard |
|---|---|---|---|
| **Rules in force** | Daily booking core: slot lengths, department, earliest date, urgent window and reserve, City Day closure, interpreters, notice period, waitlist priority, follow-up habit, status table (mandatory), staff notes carry no weight | + referral expiry, fasting blood test ≥ 1 working day before the visit with a lab cap, doctor absences (moves within the notice period), interpreter absence | + no-shows (expected values, hidden rates rising with lead time), overbooking of follow-ups with a cap per session, duplicates (one appointment per patient and department), extra trips |
| **Out of scope (said in the requirements)** | Absence and interpreter notices (a locum and an agency cover), referrals and tests (the referral desk and the lab handle them; `test_date` null), no-shows (not planned for), second requests (each its own appointment) | No-shows (no overbooking), second requests | — |
| **Rules** | 13 (6 physical, 6 contractual, 1 business policy) | 17 (+ `lab_capacity`, `test_before_visit`, `doctor_available`, `referral_validity`) | 19 (`no_double_booking` → `slot_capacity`, + `overbooking_limit`, `one_per_department`) |
| **Clarification targets** | 14: urgent reserve (size), reserve release, follow-up doctor, interpreters, holiday clinic, move notice, waitlist priority, status table, staff notes, and what is out of scope this round: duplicates, overbooking, referral expiry, blood test, doctor absence | 16: + lab cap, interpreter absence (the five scope facts now say what is in force) | 18: + overbooking cap, collision cost |
| **What it tests** | A stateful daily program; keeping the book full by refilling freed and released slots; a priority order; an exact daily status report | Two more resources (lab day, interpreter day), deadlines that make leaving a request out correct, forced moves under a notice period | Expected-value booking under uncertainty, when an overbooking pays, recognising the same patient's needs, resisting pressure |

## Parameters and rule seeds

A setting is a tier and a rule seed. The rule seed draws the client's rule values, each parameter on its own:
position `Random("healthcare/hospital_appointment_scheduler|<name>|<seed>").randrange(len(pool))` of its
pool. A parameter is drawn only in the tiers that use it: `lab_cap` has the single candidate 6 in easy (the lab
is out of scope there) and `overbooked_per_session` the single candidate 2 in easy and medium (no
overbooking there); before the audit both varied in those tiers although nothing used them (validate-case
warned). The other pools are the same in every tier, so a rule seed is one hospital and the tier only decides
which of its rules are in force. 3 × 2 × 3 × 3 = 54 combinations in easy, 162 in medium and 486 in hard.

| Parameter | Pool | What it changes | Target |
|---|---|---|---|
| `closed_dept`: the clinic closed on City Day, Monday 23 November (the calendar still lists it) | Dermatology, Orthopedics, Pediatrics (`DERM`, `ORTH`, `PED`) | which Monday-23 sessions may hold appointments; the table's `free_slots` of that department while the day is in the window; capacity 1,566 or 1,575 slots | `holiday_clinic` |
| `reserve_slots`: the urgent reserve, the first N slots of every morning session | 2 (09:00, 09:20), 3 (09:00, 09:20, 09:40) | which slots S/R requests may not take two or more days ahead, `held_back` / `free_slots` of every day, how much is released for tomorrow; with 3 the requirements add that the 09:40 appointments already in the book stay | `urgent_reserve` |
| `interpreters_per_day`: in-person interpreters per working day, hospital-wide | 2, 3, 4 | how many new-patient visits a day may be with a doctor who does not speak the patient's language; which skipped interpreted patients are excused under `waitlist_priority` (only when that day's interpreters are all taken) | `interpreters` |
| `waitlist_order` | urgency then date received; urgent first, then S and R strictly by date received; urgency then `earliest_date` | the priority order, so which request each slot goes to (`waitlist_priority`) | `waitlist_priority` |
| `lab_cap`: fasting blood tests per working day | easy 6 (not drawn); medium, hard 5, 6, 7 | test days, so which test-needing patients can be booked when; which skipped ones are excused (only when no lab day before the slot has room) | `lab_cap` |
| `overbooked_per_session`: overbooked slots per doctor session | easy, medium 2 (not drawn); hard 1, 2, 3 | how many follow-ups may be doubled up in a session | `overbooking_cap` |

`derive_params` adds `reserve_times`, the reserve's slot times as each locale lists them ("09:00 and 09:20" /
"09:00, 09:20 and 09:40"). No `admissible` hook is needed: the reference and the baseline are valid in every
combination the audit measured (45 on the public world) and on world seeds 1–3 in the public settings.

**Fixed values.** Two numbers of the old rule sets are no longer drawn. The urgent window is **2 working days**
(old A): every urgent request is generated for a department with a free reserve tomorrow, so the reference
books all 18 of them for tomorrow and a window of 1, 2, 3 or 10 days gives the same answer (REVIEW.md, F3; it
is no longer a target either). The notice for a changed date or time is **3 working days** (old A): the
reference changes appointments only for the absences and the interpreter's absence, usually far beyond the
notice, so as a drawn value it failed the binding check. It stays a rule and a target with its number in the
text: a program that takes a change to be free and pulls patients forward into tomorrow's empty slots breaks it.

**Public panel.** Rule seeds 1, 10 and 64 show every value of every pool at least once (`lab_cap` and
`overbooked_per_session` as drawn in medium and hard, and hard; easy has 6 and 2, medium 2):

| Rule seed | `closed_dept` | `reserve_slots` | `interpreters_per_day` | `waitlist_order` | `lab_cap` | `overbooked_per_session` |
|---|---|---|---|---|---|---|
| 1 | PED | 2 | 2 | `urgency_received` | 6 | 2 |
| 10 | ORTH | 2 | 3 | `urgency_earliest` | 5 | 3 |
| 64 | DERM | 3 | 4 | `received` | 7 | 1 |

Seed 1 is the tightest hospital (two interpreters), seed 64 the loosest in interpreters and lab but with a
three-slot reserve and one overbooked slot per session. Private seeds draw any of the combinations. The
reference objectives per setting are 1.000 by construction; the baselines are in the tables below.

**Parameter binding** (validate-case): every parameter binds in every tier where it varies, on the public world
and on world seeds 1–3, and validate-case reports no parameter that varies where nothing uses it. What a wrong
value of each costs is the audit's ablation of its target (GT.md, part 1): another clinic, order or interpreter
count is invalid everywhere; a reserve one slot too small is invalid and one too large reports a wrong table
every day; a lab cap one lower passes over test-needing patients the lab could take (a priority breach) and one
higher overfills the lab, except where the cap is 7 and the lab is not full on the days that matter; an
overbooking cap one higher is invalid, one lower costs little (GT.md: `overbooking_cap` bites in about two
settings of five).

## What an agent must ask

The rule seed's values sit in six targets that no data shows: `holiday_clinic` (which clinic closes; the e-mail
says every clinic runs unless a department announces otherwise), `urgent_reserve` (two or three slots; the
export holds 09:00 and 09:20 free, which is the old practice), `interpreters` (the export's history runs up to 8
interpreted new-patient visits a day), `waitlist_priority` (the order; the pilot answer follows one of the
three), `lab_cap` (medium+; the history shows up to 14 tests a day) and `overbooking_cap` (hard). Then twelve
fixed facts: `reserve_release` (the data shows the reserve never released), `status_table` (the pilot reports
`held_back` 0), `move_notice`, `follow_up_doctor` (the export has follow-ups seen by a colleague), `staff_notes`,
the five facts of what is in or out of scope (`duplicates`, `overbooking`, `referral_expiry`, `blood_test`,
`doctor_absence`), and from medium `interpreter_absence`, in hard `collision_cost`. GT.md part 1 has each
one's natural misreading and what it costs; CLIENT_REVIEW.md the passage the client answers from.

## Reference numbers (world seed 20261116)

The reference (`reference/scheduler.py` + a per-setting `config.json`) rebuilds the calendar from each day's
input; (medium+) moves the absent doctors' appointments (new patients to a colleague at the same time if free,
else the earliest slot at least the notice period ahead with the same doctor for follow-ups, else back to the
waitlist, booked again no sooner than the notice period after the release) and the excess interpreted visits
of the interpreter's absence day; then books the waitlist and the new requests in the drawn priority order
into the earliest feasible slot (reserve only for U or for tomorrow, interpreter and lab caps, referral, test
day, follow-up habit; hard: duplicates skipped, a second department on the same day if ≤ 2 days later). In
hard, a waiting follow-up is doubled up next to a booked follow-up of its doctor where that is worth more than
its free slot (or than waiting, when it has none), counting the expected collision 30 × p1 × p2 with each
patient's chance of coming estimated from their record (shrunk to the history's rate) and the lead; within the
cap per session. It reports the exact table, keeps the follow-up habit and ignores notes. Objective 1.0 in every
setting. Which parts of the data it acts on follows the tier, and
each can be switched on its own: the audit's misreadings are the same program with one switch flipped.

| Setting | Operations value | Seen patient-slots / capacity (utilization) | Waiting cost | Never booked | Booked / changes (move + release) | Overbooked slots (collision cost) | Best known: objective (quality) | Bound: objective (quality) |
|---|---|---|---|---|---|---|---|---|
| easy/s1 | 11,593 | 1,531 / 1,566 (97.77%) | 3,057 | 66 | 1,160 / 0 + 0 | — | 1.002 (1.009) | 1.163 (1.68) |
| easy/s10 | 11,528 | 1,525 / 1,566 (97.38%) | 3,052 | 67 | 1,159 / 0 + 0 | — | 1.004 (1.019) | 1.162 (1.69) |
| easy/s64 | 11,423 | 1,537 / 1,575 (97.59%) | 3,197 | 75 | 1,151 / 0 + 0 | — | 1.005 (1.013) | 1.189 (1.54) |
| medium/s1 | 9,864 | 1,437 / 1,476 (97.36%) | 3,476 | 87 | 1,170 / 9 + 31 | — | 1.004 (1.015) | 1.226 (1.88) |
| medium/s10 | 9,504 | 1,422 / 1,467 (96.93%) | 3,518 | 103 | 1,150 / 15 + 27 | — | 1.005 (1.018) | 1.254 (1.99) |
| medium/s64 | 9,682 | 1,447 / 1,476 (98.04%) | 3,694 | 93 | 1,163 / 11 + 30 | — | 1.000 (1.000) | 1.250 (1.62) |
| hard/s1 | 7,144 | 1,150.9 / 1,476 (77.97%) | 3,247 | 60 | 1,186 / 11 + 30 | 39 (336) | 1.036 (1.097) | 1.621 (2.69) |
| hard/s10 | 6,873 | 1,143.3 / 1,467 (77.94%) | 3,287 | 68 | 1,175 / 13 + 27 | 45 (412) | 1.039 (1.101) | 1.665 (2.71) |
| hard/s64 | 6,933 | 1,148.1 / 1,476 (77.78%) | 3,494 | 51 | 1,193 / 12 + 28 | 40 (353) | 1.033 (1.060) | 1.652 (2.18) |

Best known: the reference tuned on the hidden period (hindsight: packing, in hard the true no-show rates and the
overbooking rule's two values). Bound: the LP relaxation of `objective_bound` (GT.md part 4), loose because it
drops the order, the reserve, the arrival times and, in hard, counts every visit at a day's lead. Utilization is
already at 97–98% in easy and medium, so most of the headroom is waiting; hard's is capped by no-shows and the
overbooking cap. Over the audit's 45 settings the best known quality is 1.000–1.138 (median 1.019): the case's
`quality_cap` is 1.02 (a longer search, 31 moves and four passes, adds only 0.004–0.005 in hard).

Baseline against the reference, per setting:

| Setting | Baseline objective | Operations value: baseline / reference | Utilization: baseline / reference |
|---|---|---|---|
| easy/s1 | 0.760 | 8,812 / 11,593 | 87.99% / 97.77% |
| easy/s10 | 0.766 | 8,834 / 11,528 | 88.19% / 97.38% |
| easy/s64 | 0.650 | 7,426 / 11,423 | 83.62% / 97.59% |
| medium/s1 | 0.742 | 7,314 / 9,864 | 87.94% / 97.36% |
| medium/s10 | 0.745 | 7,080 / 9,504 | 87.66% / 96.93% |
| medium/s64 | 0.599 | 5,802 / 9,682 | 83.74% / 98.04% |
| hard/s1 | 0.633 | 4,524 / 7,144 | 68.15% / 77.97% |
| hard/s10 | 0.611 | 4,197 / 6,873 | 67.51% / 77.94% |
| hard/s64 | 0.449 | 3,113 / 6,933 | 64.66% / 77.78% |

How the rules and situations bind in the reference runs: all 18 urgent requests booked for tomorrow inside the
2-day window (the window binds only for a program that fills the reserve early or moves an urgent appointment);
92–107 S/R requests booked into tomorrow's released reserve with two slots, 136–159 with three; 86–93 patient
cancellations met; 9–15 moves and 27–31 releases for the absences in medium and hard.

**Bending the follow-up habit** (GT.md part 2): every follow-up with whichever doctor is free first (284–320
exceptions) gains 0.07–0.23 of quality with the rule relaxed, after the new tenth of a slot a colleague's visit
costs; only the absent doctors' patients 0.00–0.08 (none in easy, where a locum covers); only tomorrow's idle
slots 0.02–0.10. Net of the soft-rule penalty the best bend pays in 3 of the 9 public settings under
`enterprise_balanced` and 7 under `startup_velocity`, and loses or breaks even in the others.

**Literal solution** (`literal_solution`: the request done as written, the same in every setting): the reference
program on the only rule values the agent's view shows: the pilot's (`PILOT_RULES`: earliest free slot first, U
and then everyone by the date received, 09:00 and 09:20 kept for urgent patients as the office always did, the
day before included, the pilot's table with `held_back` 0, three interpreters a day, a day's notice for a move,
no overbooking, a lab figure of 10), every clinic open on City Day as the outpatient office's e-mail says, and
every notice and request field acted on (absences, the interpreter's absence, referral dates, blood tests);
notes are not followed. It books the closed clinic on City Day and breaks the waitlist order in every setting,
the interpreter cap where it is 2, the reserve where it is three slots, the lab cap from medium and books
duplicates in hard, so it is invalid in all 9 public settings, with the bendable habit relaxed too. Even with
every client rule kept (the audit's `literal_all_rules`) it is valid but below the baseline (quality 0): keeping
the reserve for the day before and the pilot's table are the two client facts that carry the score.

## Ground truth audit

The case is `audited: true`. `dataset/audit.json` holds the audit of the public world (`fdebench2 audit-case`: per
tier the public panel and 12 admissible combinations, 45 settings), [GT.md](../../GT.md) the ground truth in five
parts generated from it by `gt_report.py`, and [CLIENT_REVIEW.md](../../CLIENT_REVIEW.md) the passages of
requirements.md each locale answers each target from, with a machine pre-check (awaiting human review). In short:

- **Targets** (18, one fact each): every one bites in every tier where it is in force. Fifteen bite in every
  measured setting (most misreadings make the program invalid), `overbooking` in 12 of 15 hard settings (never
  overbooking loses 0.09–0.16), `collision_cost` in all 15 (0.18–0.42), `interpreter_absence` in 14 of 15 medium
  and 15 of 15 hard settings (the interpreter is away on a day that reaches the interpreters' number; it was 8 of
  30 before the check) and `overbooking_cap` in 6 of 15, every setting where the cap is 1 (a cap one lower costs
  0.00–0.04, one higher is invalid): the one warning. The diagnostic (from the trace of the program's own run)
  separates every target, calls the best known solution enforced on every target in force, and no ablation flags
  another target.
- **Status table**: every entry that is not exact costs 20 in the operations value (as much as two empty slots);
  it multiplied the objective after the first audit, which made a one-column slip cost up to the whole scale.
- **Shortcuts** (20, and 21 in hard; GT.md part 2): booking nobody, only the urgent requests, first come first
  served, the earliest slot with any doctor, the office's practice as the export shows it, the same with
  tomorrow's reserve released, no table, a zero table, the morning's table, the pilot day's numbers every day, the
  literal program with one client rule kept or all of them (and then also the reserve released, or the client's
  table), and in hard the office's practice with blind overbooking: closed in all 45 settings (best 0.066).
- **Value of asking**: 0.96 in easy, 1.00 in medium and hard. The program that never asks (`robust_solution`)
  reads the fixed facts at their strongest (tomorrow's empty reserve slots given to the waitlist, `held_back` as
  the reserve it still holds) and takes the safe side of every drawn rule that has one, the pilot's order and
  three interpreters and the middle lab cap otherwise; the waitlist order, the interpreters and the lab cap have
  no safe side (the priority rule makes too few as invalid as too many), so it is valid in 1 of the 45 settings.
  Knowing every fixed fact but not the drawn values earns 0.07 (value of the parameters 0.93).
- **Bounds**: best known 1.000–1.138 (median 1.019), LP bound 15–67% above the reference (made integral, 120 s
  on hard/s1, it goes only from 1.621 to 1.608: the looseness is the relaxed rules), `quality_cap` 1.02.
- **Overbooking** (hard) pays 0.09–0.16 of the scale over never overbooking, and pairing blind loses 0.18–0.41:
  the tier measures whom to pair.

## Data files and formats

The agent's `data/` (the same in every setting; file names, enum values, names and comments in the customer
locale, table and column names, codes and IDs ASCII):

| File (en / ko) | Format | Content |
|---|---|---|
| `booking_system_export.sql` / `예약시스템_내보내기.sql` | SQL dump (`casekit.write_sql`; `sqlite3 db < file.sql`), header comment lists the tables | `departments`, `languages` (code → localized name), `doctors`, `doctor_languages`, `weekly_sessions`, `clinic_sessions` (calendar 12 Oct – 20 Nov, no holiday change), `requests` (1,478: the history's H ids and the Q ids received before 9 Nov), `request_notes`, `appointments` (history with outcome + the 359 booked from 9 Nov, status localized), `cancellations` (history, with `cancelled_on`), `attendance` (`attended` 0/1), `waitlist_history` (`added_on` / `removed_on`; the 45 still waiting have none), `status_reports` (the pilot day's table) |
| `mail/*.eml` | e-mail (`casekit.write_eml`, RFC 5322, UTF-8), localized bodies, `hospital.example` addresses | D09 conference 5–9 Oct, D02 off sick 7–9 Oct, interpreter away 8 Oct (all before the export's four weeks, so the history is consistent), D07's request for a new-patient list, the director's office asking "tomorrow morning" for history request H00868 (booked in turn, seen 2 Nov), the outpatient office's City Day and data-codes instructions |
| `pilot_day_input.json`, `pilot_day_output.json` / `시범일_입력예시.json`, `시범일_출력예시.json` | JSON | one `on_day` call exactly as the engine makes it, and the pilot program's answer |

The program's daily input stays JSON (`on_day(day)`): its `notices` and request `notes` are what the e-mails
are in the history, its `book` / `waitlist` / `attendance` what the export's tables are.

## Stored dataset (`dataset/`)

Written by `python -m fdebench2.cli export-dataset cases/healthcare/hospital_appointment_scheduler` (checked by
`validate-case`; about 11 MB, 123 files):

- `agent_view/<lang>/`: the agent's data above, per locale.
- `hidden/days/<date>.json`: the 20 calls of the hidden period. 9 November is the complete input; for the other
  days the fields that depend on the program's earlier decisions (`attendance`, `book`, `waitlist`, patients'
  `cancellation` notices) are left out — the rest (calendar, new requests, the absence / interpreter / staff
  notices, notes) is exactly what the engine sends.
- `hidden/mail/<lang>/*.eml`: the period's e-mails behind those notices and notes (D10's keep-free note 11 Nov,
  D13 off sick 13 Nov, the interpreter 17 Nov, D05's conference 20 Nov, four director's-acquaintance requests).
- `hidden/requests.csv`: every request of the start and the period with its hidden facts (no-show rate at zero
  lead, the working days before an appointment the patient cancels, the request it duplicates).
- `answer/`: the public settings (seeds 1, 10, 64), each file keyed by difficulty and seed: `answers.csv` (one row
  per setting: the drawn parameters, the reference's and the baseline's objective and the reference's metrics; the
  derived `reserve_times` is not stored), the reference and baseline `files/<reference|baseline>/program/scheduler.py`
  (the same in every setting) with each setting's config in `reference_program.jsonl` and `baseline_program.jsonl`,
  and from the reference's replay, the settings stacked, `actions.csv` (every action per call), `status_tables.csv`
  (the expected table, 20 days × 5 departments), `cancellations.csv` (the patients' cancellations it met),
  `final_book.csv` (every appointment held in the period, with attendance where reported, and the upcoming ones) and
  `final_waitlist.csv`.

## Notes

- **One process per replay**: `casekit.program_session` loads `scheduler.py` once and makes the 20 calls in the
  same isolated process. The case also replays the reference in-process (JSON round-tripped) for the
  normalizer and for the validator's examples; the subprocess run gives the same numbers.
- **Validator examples** are the reference with a few actions appended on one day (found from a snapshot of
  the reference's book that day and checked by replaying the rest of the period in-process): an unknown
  request; a follow-up moved onto an occupied slot (hard: onto a new patient's slot) or to 12:20; a new patient
  moved to another department's doctor at the same time; a follow-up moved into the closed clinic on City Day,
  before its earliest date, into the reserve, at short notice, to another doctor, or into an absent doctor's
  day; a follow-up released, which the reference books again the next day inside the notice period counted
  from the release; two new-patient visits swapped to overfill a day's interpreters; a waiting test-needing request
  (the first of its group) booked with its test on a day the lab is full, or with no test day (test days moved
  are the fallback); a new patient moved past its referral; an urgent appointment moved past its window;
  overbooked follow-ups beyond the cap; a waiting duplicate booked; a lower-priority request booked into a
  released slot; the last call's status table without the Pediatrics row. `validate-case` (9 public settings,
  the binding check and world seeds 1–3) takes about **ten minutes** (with the dataset check); `audit-case`
  about twenty.
- Rates, capacities and patients are synthetic. A review of no-show models found that predictive overbooking
  can make some patient groups wait longer (see `docs/specs/healthcare.md`); the data carries no protected
  attributes and the hard tier rewards overbooking only through expected idle and collision costs.
- **Trace and diagnostic**: `score()` keeps a private trace of the run (breaches with what they concern,
  placements, releases, doubled-up slots, the reported and true tables and the tables of each misreading, the
  overbooked pairs' chances); `diagnose()` reads it for the target funnel and the audit, and `evaluate()` never
  copies it to a result.
