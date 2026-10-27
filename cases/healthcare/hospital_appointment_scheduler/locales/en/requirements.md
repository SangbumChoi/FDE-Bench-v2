# Outpatient appointment booking

## Background

We have a backlog of outpatient appointment requests. Can you book them into the doctors' calendars for the next two weeks (Monday 16 to Friday 27 November)? We'd like patients not to wait longer than they have to. The doctor list, the free slots, the request list and our clinic notices are attached.
The patients' attendance history is attached too.

## Deliverable

One CSV file, `bookings.csv`, with the header `request_id,doctor_id,date,start,test_date` (these English column names in any case). One row per booked request: `request_id` and `doctor_id` exactly as in the data, `date` as YYYY-MM-DD, `start` as HH:MM, the start time of the visit's first slot (e.g. `R017,D04,2026-11-18,09:40,`). 
<!-- tier: easy -->
Leave `test_date` empty.
<!-- /tier -->
<!-- tier: medium hard -->
`test_date` is the date (YYYY-MM-DD) of the request's blood test when it needs one, and empty otherwise.
<!-- /tier -->
A request we cannot fit in is simply left out of the file; no request may appear twice.

## Data notes

- The booking period is the ten working days Monday 16 November to Friday 27 November 2026 (Monday to Friday; weekends are closed). Monday 23 November counts as a working day.
- `free_slots.csv` lists only the slots that are still free; everything else is already taken. Each row is one 20-minute slot of one doctor, by its start time. Morning clinics run 09:00-12:00, afternoon clinics 13:00-17:00.
- Visit length depends on `visit_type`: a `new patient` visit takes **two consecutive free slots** of the same doctor on the same day (e.g. 09:00 and 09:20, booked as `start` 09:00); a `follow-up` takes one slot. A visit cannot run over the lunch break.
- A request is booked with a doctor of its `department` (see `doctors.csv`).
- `earliest_date` comes from our old booking system and is written **day/month/year** (10/11/2026 is 10 November). It is the first day the patient can come; never book before it. If it is before 16 November, the patient has been waiting already and can come any day from 16 November.
- The reference date of a request is its `earliest_date`, or 16 November if that is earlier. Waiting time is counted in working days from the reference date to the appointment date (same day = 0).
- `urgency` codes: `U` = urgent, `S` = soon, `R` = routine. `triage_note` is free text for information only. Our clinical service agreement says every **urgent** request must be seen within **{{urgent_days}} working days** of its reference date (on that day or one of the next {{urgent_days}} working days). Every U request must be booked.
- A `follow-up` request (`previous_doctor` filled in) is booked with that same doctor; patients expect to see the doctor who knows them. This is our own front-desk habit, not a contract. Note that Dr D11 (Orthopedics) is on leave in the first week (see `clinic_notices.txt`), so the free-slot list has no D11 slots then.
- Languages: if the doctor does not speak the patient's `preferred_language` (see `languages` in `doctors.csv`), the visit needs an interpreter. We have **{{interpreters_per_day}} in-person interpreters per day** across the whole hospital, and a **new-patient** visit must have an in-person interpreter, so at most {{interpreters_per_day}} interpreted new-patient visits per day. Interpreted follow-ups use an in-person interpreter if one of the {{interpreters_per_day}} is still free that day, and otherwise our video interpreting service, which we pay for (**3 per visit**). Visits with a doctor who speaks the patient's language need no interpreter.
- Holiday: 23 November is City Day (see `clinic_notices.txt`). The other clinics work normally, but the **{{closed_dept}} clinic is closed that day**. The calendar was not updated, so `free_slots.csv` still shows {{closed_dept}} slots on 23 November; do not use them.
<!-- tier: easy -->
- This round uses only the rules above: ignore `referral_valid_until`, `pre_visit_test` and `attendance_history.csv`, and leave `test_date` empty.
<!-- /tier -->
<!-- tier: medium -->
- This round has no overbooking and does not use `attendance_history.csv`.
<!-- /tier -->
<!-- tier: medium hard -->
- Referral letters: a new patient comes with a referral letter, and `referral_valid_until` (also **day/month/year**) is the last day it is valid. The visit must take place on or before that day; after it the visit is not covered and the patient would need a new letter, so such a request is better left unbooked.
- Blood tests: when `pre_visit_test` says `fasting blood test`, the patient must have the test in our lab **at least one working day before the visit** (results take a day) and not before their `earliest_date`. The test is a separate morning visit, written in `test_date`. The lab can take at most **{{lab_cap}} fasting blood tests per working day**, for all departments together.
<!-- /tier -->
<!-- tier: hard -->
- No-shows: some patients do not turn up. Each patient has their own no-show rate; `attendance_history.csv` gives past appointments and missed appointments for patients who have been here before (new patients have no history; across the hospital about 1 in 5 appointments is missed). The longer the wait between booking and visit, the more often people miss it: about **one percentage point more per working day** of lead time. The past figures were measured with about 5 working days of lead time, and the requests were taken 2 working days before 16 November.
- Overbooking: because of no-shows we allow **overbooking of follow-ups**: a slot may hold **two follow-ups** (never a new-patient visit, which needs both its slots to itself), and each doctor may have at most **{{overbooked_per_session}} overbooked slots per session** (morning or afternoon).
<!-- /tier -->

## How the plan is judged

**Hard constraints** (if any is broken, the plan does not count):

- Only free slots from `free_slots.csv`; a new-patient visit uses two consecutive free slots of the same doctor, a follow-up one.
<!-- tier: easy medium -->
- No slot is used twice.
<!-- /tier -->
<!-- tier: hard -->
- A slot holds at most two follow-ups and a new-patient visit never shares its slots; at most {{overbooked_per_session}} overbooked slots per doctor per session.
<!-- /tier -->
- The doctor belongs to the requested department.
- No booking before `earliest_date`; no {{closed_dept}} booking on 23 November.
- At most {{interpreters_per_day}} interpreted new-patient visits per day.
- Every urgent request is booked within {{urgent_days}} working days of its reference date.
- Follow-ups are booked with their previous doctor (our habit; we can make an exception if it helps patients).
<!-- tier: medium hard -->
- New-patient visits take place while the referral letter is valid.
- Every blood test is done from the earliest date up to the working day before the visit, at most {{lab_cap}} per day.
<!-- /tier -->

**Quality**: for every booked request, its waiting working days times a weight (U 3, S 2, R 1), plus 20 for every S request booked more than {{soon_days}} working days after its reference date, plus 60 for every request that is not booked, plus 3 for every follow-up interpreted by video. Lower is better.
<!-- tier: hard -->
On top of that we count the expected cost of no-shows and overbooking: 10 for every slot whose patients all stay away (a new-patient visit risks both its slots), and 25 for every overbooked slot where both patients turn up and the doctor runs late. Both are expectations over the patients' real no-show rates.
<!-- /tier -->
