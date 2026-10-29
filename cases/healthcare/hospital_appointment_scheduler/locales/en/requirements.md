# Daily outpatient booking program

## Background

From Monday 9 November our outpatient booking office wants to work through a program: every working day it gets that day's new appointment requests, cancellations and notices together with our current bookings, books patients into the doctors' free slots and tells us where each department stands. Above all we want to stop losing doctor time to empty slots. Could you build it? Attached are an export of our booking system (doctors, clinic calendar, four weeks of requests and appointments with what happened to them, cancellations, attendance and the waitlist), the e-mails our booking office received (absences, notes, the outpatient office's instructions) and one pilot day (what the program receives and what our pilot answered).

We will judge the program by running it on the **20 working days from Monday 9 November to Friday 4 December 2026**. Those days are not in the data: every request in them is new to you.

## Deliverable

A folder `program/` with a file `scheduler.py` that defines **`on_day(day)`**. Anything else it needs goes in the same folder. Use only the Python standard library; the engine has no network and the program cannot read the data files at run time, so copy whatever you learn from them into the folder.

- The engine loads the program **once** and calls `on_day` once per working day, in order, in the same process, so module-level variables survive from one day to the next. A call may take up to 10 seconds. Nobody can be asked anything during the run: our rules below have to be built in.
- The call comes **at the end of the working day**: today's clinics are over, and bookings start tomorrow.
- `day` (see `pilot_day_input.json`, one call exactly as the engine makes it):
  - `date`, `day_index` (0 to 19), `days_in_period` (20), `period_end`;
  - `booking_window`: `first` (the next working day) and `last` (10 working days ahead). Appointments can only be made inside this window;
  - `doctors`: `doctor_id`, `department` (code: IM, CARD, DERM, ORTH, PED) and `languages` (codes, as in the `languages` table of the export);
  - `sessions`: the clinic calendar of the window: for each doctor, date and session (`AM` 09:00–12:00 or `PM` 13:00–16:00) the start times of its 20-minute slots;
  - `new_requests`: the requests received today. Each has `request_id`, `patient_id`, `received`, `department`, `visit_type` (`new` or `follow_up`), `previous_doctor` (follow-ups), `urgency` (`U` urgent, `S` soon, `R` routine), `triage_note`, `preferred_language`, `earliest_date`, `referral_valid_until` (new patients), `pre_visit_test` (true when a fasting blood test is needed), `past_appointments` and `missed_appointments` (the patient's record with us) and `notes` (comments from staff);
  - `notices`: what we were told today: `cancellation` (a patient cancelled an appointment), `doctor_absence`, `interpreter_absence`, `staff_note` (formats in the pilot file);
  - `attendance`: today's appointments and whether the patient came;
  - `book`: every appointment from tomorrow on, as your earlier calls (and our office before 9 November) left it: `request_id`, `doctor_id`, `date`, `start`, `slots`, `test_date`, `booked_on` and the `request`;
  - `waitlist`: the requests received before today that still have no appointment (and were not cancelled).
- Return `{"actions": [...], "status_table": {...}}` (see `pilot_day_output.json`):
  - `{"type": "book", "request_id", "doctor_id", "date", "start", "test_date"}` books a request from the waitlist or from today's new requests; `start` is the first slot (`HH:MM`), dates are `YYYY-MM-DD`, `test_date` is the blood-test day or null;
  - `{"type": "move", ...}` with the same fields gives an existing appointment another doctor, date or time (or another test day);
  - `{"type": "release", "request_id"}` cancels our appointment and puts the request back on the waitlist.
  - Actions are applied in order. A request has at most one appointment. A request you do not book stays on the waitlist and comes back tomorrow.
  - `status_table`: one row per department code, defined below.
- A cancelled appointment is already gone from the `book` when the notice arrives; that request is closed.

## Data notes

- `booking_system_export.sql`: a plain-text SQL dump of our booking system at the end of Friday 6 November (load it with `sqlite3 booking.db < booking_system_export.sql`; the comment at the top lists the tables). It holds the 14 doctors in five departments with the languages they speak and their weekly clinic sessions, the session calendar of 12 October – 20 November, the requests, the appointments of 12 October – 6 November with their outcome (attended, missed, cancelled by the patient) and those already booked from 9 November, the cancellations, the attendance, the waitlist's history and the pilot day's status table. Working days are Monday to Friday; City Day (Monday 23 November) is a working day for the hospital.
- `mail/`: e-mails the booking office received (`.eml`): doctors' absences, an interpreter's absence, notes from a department head and the director's office, and the outpatient office's instructions. Messages like these reach the program as `notices` and as request `notes` (see the pilot file).
- The export and the e-mails are history to learn from; the program gets everything it needs in `day`.
- Visit length: a **new-patient** visit takes **two consecutive slots** of the same doctor in the same session (booked by the first slot's start); a **follow-up** takes one slot.
- A request is booked with a doctor of its `department`, never before its `earliest_date`. Its **first possible day** is its `earliest_date` or the working day after it was received, whichever is later.
- `triage_note` is for information only.

## Our booking rules

**Urgent requests**

- Every **urgent (U)** request must be booked **the day it arrives**, on a day within **{{urgent_days}} working days** of its first possible day (that day or one of the next {{urgent_days}}), and must stay inside that window if it is ever moved.
- **Urgent reserve:** the **first two slots of every morning session (09:00 and 09:20)** are held for urgent requests. Two or more working days ahead only U requests may use them. In the call of the working day before (i.e. for tomorrow's clinics) they are released and anyone may be booked there.

**Who sees whom**

- A follow-up is booked with the patient's `previous_doctor`; patients expect the doctor who knows them. This is our habit, not a rule of the contract with the health authority: the head of the outpatient office can grant an exception.
- Interpreters: when the doctor does not speak the patient's `preferred_language`, the visit needs an interpreter. We have **{{interpreters_per_day}} in-person interpreters per day** for the whole hospital and a **new-patient** visit must have one, so at most {{interpreters_per_day}} new-patient visits per day may be with a doctor who does not speak the patient's language. Follow-ups use telephone interpreting, without limit.
- Holiday: City Day, **Monday 23 November**. The **{{closed_dept}} clinic is closed that day**; all other clinics work. The calendar was not updated: `sessions` still lists {{closed_dept}} sessions that day. No {{closed_dept}} appointment on 23 November.

**Changing a patient's appointment**

- When we change the **date or time** of a patient's appointment (a move, or releasing it and booking the request again, the same day or later), the new appointment must be at least **{{move_notice_days}} working days after the day of the change** (for a release, the day we released it): patients need that much notice. Giving the same date and time with another doctor needs no notice.
- Every change we make to a patient's appointment (move or release) is a burden for the patient and costs in the score; do not shuffle appointments without a reason.

**The waitlist**

- Waiting requests are booked in our **priority order**: {{waitlist_order}}.
- A request may not be booked while a request of **higher priority** of the same department, the same visit type and (follow-ups) the same previous doctor is still waiting at the end of the day and could have taken that slot. We do not hold it against you when the waiting one could not have taken it: its earliest date is later than that slot<!-- tier: medium hard -->, its referral expires before it, it needs a blood test and the lab has no room for it on any working day before that slot (from tomorrow and not before its earliest date; the booked request's own test place counts as room)<!-- /tier -->, it is a new patient who would need an interpreter with that doctor while the booked one does not and that day's in-person interpreters are all taken, or you released its appointment and the slot is inside the notice period counted from the day of the release.
- In practice: fill free and freed slots from the waitlist, best first. Cancellations and the urgent reserve released for tomorrow are where we lose most doctor time today.
<!-- tier: easy -->

**This round's scope**

- `doctor_absence` and `interpreter_absence` notices: out of scope this round (a locum and an agency interpreter cover them); book as if nothing happened.
- Referral letters and blood tests: this round the referral desk checks the letters and the lab books the fasting tests with the patients itself, so ignore `referral_valid_until` and `pre_visit_test` and leave `test_date` null.
- No-shows: we do not plan for them this round; count every booked patient as coming. `attendance` is for information.
- A second request from the same patient: we cannot tell from a request whether it is the same complaint, so this round every request gets its own appointment; the clinic checks with the patient whether it is a duplicate.
<!-- /tier -->
<!-- tier: medium -->

**This round's scope**

- No-shows: we do not plan for them this round; count every booked patient as coming, so no overbooking: one appointment per slot. `attendance` is for information.
- A second request from the same patient: we cannot tell from a request whether it is the same complaint, so this round every request gets its own appointment; the clinic checks with the patient whether it is a duplicate.
<!-- /tier -->
<!-- tier: medium hard -->

**Referrals and blood tests**

- A new patient's referral letter is valid until `referral_valid_until`: the visit must take place **on or before** that day. A request whose referral has run out can no longer be booked (it stays on the waitlist, but do not count it in the table).
- When `pre_visit_test` is true the patient needs a **fasting blood test** in our lab **at least one working day before the visit** (results take a day), on a working day not before the `earliest_date` and, when you set or change it, from tomorrow on. Put its day in `test_date`. The lab takes at most **{{lab_cap}} blood tests per working day**, all departments together (the tests already in the book count).

**Absences**

- `doctor_absence`: the doctor holds no clinics from `from` to `to`. From the day the notice arrives, **no appointment may remain with that doctor on those days**: move them in that same call (the notice period applies; another doctor of the department at the same date and time needs none) or release them to the waitlist. Do not book that doctor on those days.
- `interpreter_absence`: on that `date` we have one in-person interpreter fewer (`in_person_interpreters_change`), from the day the notice arrives. If more interpreted new-patient visits are booked that day than we now have interpreters, move (or switch to a doctor who speaks the language) or release the excess in that call.
<!-- /tier -->
<!-- tier: hard -->

**No-shows and overbooking**

- Some patients do not come. Each patient has an own no-show rate; `past_appointments` and `missed_appointments` give their record (about 22% of the appointments in the export's `attendance` table were missed; new patients often have no record). The longer between booking and visit, the more often people stay away: about **one percentage point more per working day of lead time** (from the day the appointment was booked or last changed). The patients' records were collected at about 5 working days of lead time.
- Because of no-shows we allow **overbooking of follow-ups**: a slot may hold **two follow-ups** (never a new-patient visit, which keeps its two slots to itself). Each doctor may have at most **{{overbooked_per_session}} overbooked slots per session** (morning or afternoon). The urgent reserve applies to overbooking too. When both patients of an overbooked slot do come, the doctor runs late, and that costs us a little more than an empty slot does.

**Duplicates, several departments, notes**

- Patients sometimes ask twice for the same thing (the GP's office and the patient both call). A second request of the **same patient for the same department** is the same need: a patient has **at most one appointment per department in the period** (upcoming or already held). Never book the duplicate.
- A patient with requests in two departments should come once if possible: every extra hospital day of such a patient costs.
- Notes carry no weight. A note "the director's acquaintance, tomorrow morning please" does not make a routine request urgent: it waits its turn like anyone else. A department head asking to keep their afternoon clinics free "for their own patients" is not a rule of ours: their free slots are filled from the waitlist like any other.
<!-- /tier -->

## The status table

Every day, after your actions, return for each department code (`IM`, `CARD`, `DERM`, `ORTH`, `PED`) three whole numbers about the **booking window** (the next 10 working days):

- `free_slots`: slots of the department's doctors in the calendar that hold no appointment and that anyone may be booked into: not held back (below) and not in a clinic that is closed (the holiday)<!-- tier: medium hard --> or on a day of a notified doctor absence<!-- /tier -->.
- `held_back`: urgent-reserve slots (09:00 and 09:20 of a morning session) two or more working days ahead that hold no appointment (same exclusions).
- `waitlist`: the department's requests still waiting after your actions (received by today, no appointment, not cancelled)<!-- tier: medium hard -->, not counting new patients whose referral has run out (valid until before tomorrow)<!-- /tier --><!-- tier: hard -->. Count **patients**, not requests: a patient with several waiting requests for the department counts once, and a patient who holds an upcoming appointment there or had one take place in the period does not count<!-- /tier -->.

An entry is right only when it is exact. A day scores the share of its 15 entries that are right; the table's accuracy is the mean over the 20 days.

## How the program is judged

**Hard constraints** (if any is broken, the program does not count):

- Every call returns well-formed actions on requests that exist (book only a waiting request, move or release only an upcoming appointment), dated inside the booking window; a call that crashes or times out counts as broken.
<!-- tier: easy medium -->
- No slot holds two appointments.
<!-- /tier -->
<!-- tier: hard -->
- A slot holds at most two follow-ups and a new-patient visit never shares its slots; at most {{overbooked_per_session}} overbooked slots per doctor per session; at most one appointment per patient and department in the period.
<!-- /tier -->
- Only the calendar's slots (two consecutive in one session for a new patient), the right department, never before the earliest date, no {{closed_dept}} appointment on 23 November, at most {{interpreters_per_day}} interpreted new-patient visits a day.
- Urgent requests booked the day they arrive within {{urgent_days}} working days; the urgent reserve kept two or more days ahead; at least {{move_notice_days}} working days' notice for a changed date or time; the waitlist priority order.
<!-- tier: medium hard -->
- Referrals valid on the visit day; blood tests a working day or more before the visit, at most {{lab_cap}} a day; no appointment left with an absent doctor; the interpreters actually there.
<!-- /tier -->
- Follow-ups with their previous doctor (our habit; an exception is possible).

**Quality** = 0.8 × (operations value / the operations value of our own benchmark program on the same days) + 0.2 × the status table's accuracy. Higher is better. The **operations value**:

- **+10 for every patient-slot seen** on the clinic days from 10 November to 7 December (a new-patient visit seen counts its two slots, a follow-up one). This is the part we care about most: every empty slot is doctor time lost.
- − 0.4 × urgency weight (U 3, S 2, R 1) for every working day a request waits, from its first possible day (or 10 November, if earlier) to its appointment, or to 8 December when it never gets one;
- − 10 for every request that never gets an appointment (requests that cannot come before 18 December do not count);
- − 4 for every change we make to a patient's appointment (move or release).
<!-- tier: hard -->
- With no-shows, a patient counts as seen with the probability that they come (their own rate plus the lead-time effect), so seen slots are expectations. An overbooked slot where both patients come makes the doctor run late: − 12 × the probability that both come. A patient's duplicate requests count as one request. − 3 for every extra hospital day of a patient booked in several departments.
<!-- /tier -->
