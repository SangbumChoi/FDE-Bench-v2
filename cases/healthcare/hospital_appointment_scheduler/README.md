# Hospital Appointment Scheduler — `healthcare/hospital_appointment_scheduler`

A mid-size outpatient hospital asks the agent to book a backlog of 320 appointment requests into 14
doctors' free 20-minute slots over two weeks (16–27 November 2026, 10 working days). The deliverable is
`bookings.csv` (`request_id,doctor_id,date,start,test_date`). The setting is country-neutral: no national
insurance or payer rules, only rules every outpatient clinic has (referral letters, triage windows,
interpreters, lab capacity, no-shows).

The case has **settings**: one dataset and one request, nine ground truths (3 tiers × 3 rule sets). The
agent always gets the same files and the same request; the tier and rule set change only what the client
answers and how the bookings are scored. Results for a difficulty are the mean over rule sets A, B and C.
How the work is handed over (full spec / standard / messy) is a separate engagement axis (see
[cases/README.md](../../README.md)).

## Data (the same in every setting)

`doctors`, `free_slots`, `appointment_requests` (with `referral_valid_until` and `pre_visit_test`),
`clinic_notices` (City Day on 23 November; Dr D11 on leave in week 1) and `attendance_history.csv` (past and
missed appointments of returning patients). Deliverable: `bookings.csv`
(`request_id,doctor_id,date,start,test_date`).

## Tiers: which rules apply

| | easy | medium | hard |
|---|---|---|---|
| **Rules in force** | Day/month/year dates; new patient = 2 consecutive slots, follow-up = 1; urgent within the window; one clinic closed on the holiday although its slots are listed; follow-ups with the previous doctor (bendable habit); in-person interpreters capped per day for new patients, paid video interpreting for follow-ups | + a new patient's referral letter expires (booking after it voids the visit); a fasting blood test at least one working day before the visit, not before the earliest date, written in `test_date`; a daily lab cap | + no-shows: each patient's hidden rate, about 1 in 5 overall, rising one point per working day of lead time (attendance history given); follow-ups may be overbooked two to a slot, a capped number per doctor session |
| **Out of scope this round** (the client says so) | referral dates, tests, attendance history; `test_date` stays empty | attendance history; no overbooking | – |
| **Rules** | `no_double_booking`, `slot_length`, `department_match`, `holiday_closure`, `not_before_earliest`, `interpreter_capacity` (physical); `urgent_within_2_days` (contractual); `follow_up_same_doctor` (business policy, bendable) | + `test_before_visit`, `lab_capacity` (physical); `referral_validity` (contractual) | `no_double_booking` → `slot_capacity` (physical: ≤ 2 follow-ups, new visits never shared) + `overbooking_limit` (contractual) |
| **Quality (lower is better)** | Σ waiting working days × weight (U 3, S 2, R 1) + 20 per S request later than the "soon" window + 60 per unbooked request + 3 per video-interpreted visit | same | + 10 × P(slot stands empty) per slot + 25 × P(both come) per overbooked slot, with the true no-show rates |
| **What it tests** | Messy data, slot packing, priorities, when to bend a habit | Two resources (doctor slot + lab day); deadlines that make leaving a request out correct | Rates from small samples, lead-time effects, when the collision risk is worth it |

## Rule sets: the client's parameters

| Parameter | A | B | C |
|---|---|---|---|
| Clinic closed on 23 November (`closed_dept`) | Dermatology | Orthopedics | Pediatrics |
| Urgent window, working days (`urgent_days`) | 2 | 1 | 3 |
| In-person interpreters per day (`interpreters_per_day`) | 3 | 4 | 2 |
| "Soon" requests late after, working days (`soon_days`) | 5 | 3 | 8 |
| Lab tests per day (`lab_cap`, medium+) | 7 | 6 | 8 |
| Overbooked slots per doctor session (`overbooked_per_session`, hard) | 2 | 1 | 2 |

The closed clinic is what makes the rule sets non-nested: a plan built for one rule set books the clinic
another rule set closes, so it is invalid there. The validator checks every pair within each tier.

## Reference numbers (seed 20261116)

The reference is a priority greedy (urgent, soon, routine; each by reference date) into the cheapest feasible
slot, with one repair pass that moves a single blocking booking; in hard it then overbooks left-over
follow-ups with its own shrunk no-show estimates. It keeps the follow-up habit.

| Setting | Reference objective | Booked / unbooked | Bending the follow-up habit for D11's patients |
|---|---|---|---|
| easy / A | 1,434 | 312 / 8 | −9.5% |
| easy / B | 1,179 | 316 / 4 | −14.0% |
| easy / C | 1,128 | 315 / 5 | −4.3% |
| medium / A | 2,030 | 303 / 17 | −5.3% |
| medium / B | 2,271 | 298 / 22 | −7.3% |
| medium / C | 1,337 | 313 / 7 | −3.7% |
| hard / A | 2,988 | 303 / 17 | −4.6% |
| hard / B | 3,236 | 298 / 22 | −5.0% |
| hard / C | 2,360 | 313 / 7 | −2.4% |
| **mean easy / medium / hard** | **1,247 / 1,879 / 2,861** | | **−9.2% / −5.4% / −4.0%** |

Bending the habit pays in every setting, so a policy that allows exceptions rewards an agent that asks for
one. In hard an agent can also beat the reference by overbooking deliberately (moving follow-ups into shared
slots frees slot pairs for new patients who would otherwise go unbooked).

## Notes

- Rates and capacities are synthetic. A review of no-show models found that predictive overbooking can
  make some patient groups wait longer (see `docs/specs/healthcare.md`). The data carries no protected
  attributes; the hard tier only rewards overbooking through expected idle and collision costs.
- `validate-case` checks all nine settings: deterministic data in five locales, the reference at quality 1.0,
  one deliverable per rule that breaks only that rule, different solutions per rule set, and the same agent
  view everywhere.
