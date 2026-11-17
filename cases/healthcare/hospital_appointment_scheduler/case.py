"""Daily outpatient appointment scheduling through a program (original FDE-Bench v2 case).

A mid-size outpatient hospital wants its booking office to run on a program. Every working day the program
gets the day's new appointment requests, the notices of the day (patient cancellations, a doctor falling ill
or going to a conference, an interpreter away, notes from staff), today's attendance and the current booking
book and waitlist (the effect of its own earlier decisions). It books new requests into the doctors' free
20-minute slots of the next ten working days, re-books appointments a notice affects, fills freed slots from
the waitlist, and returns the day's status table (per department: free slots, slots held back, waitlist).
The agent delivers `scheduler.py:on_day(day)`; the evaluator calls it once per working day of a HIDDEN period
of 20 working days (9 November - 4 December 2026), in order, in one isolated process
(casekit.program_session).

The key of the case is slot utilization: as many patients seen as possible in the doctors' time, by
re-filling cancelled and released slots from the waitlist (and, in hard, by overbooking follow-ups of
patients who often stay away), without breaking a rule. Objective = the operations value / the reference
program's operations value. The operations value counts 10 per expected patient-slot seen on the period's clinic
days, minus waiting, unbooked requests, moves of patients' appointments, follow-ups seen by a colleague (only
under the bendable habit's exception), every entry of the daily status table that is not exact (20, as much as
two empty slots: the departments staff their clinics from the table, which is also mandatory, rule status_table)
and (hard) overbooking collisions (30 x the chance both come) and extra trips.

What the agent sees carries the office's old practice and only that: the history keeps the first two morning
slots for urgent patients (empty when none comes), never double-books and shows some follow-ups seen by a
colleague (exceptions); the pilot holds the reserve too and reports held_back 0. The client's facts (the
reserve released for tomorrow, its size, the table's definition, the collision cost, the round's scope, ...)
are what the score rewards; the ground truth audit's hooks (ablations, shortcuts, diagnose, robust_solution,
best_known_solution, objective_bound) are below the violating examples.

One world and one hidden period for every setting: the same doctors, requests, cancellations intents,
notices and notes. The tier decides which rules are in force:

  easy    the daily booking core: new patient = 2 consecutive slots, follow-up = 1; department; the urgent
          window; the urgent reserve (first two or three morning slots held for urgent requests until the day
          before, then released); a clinic closed on the City Day holiday; in-person interpreters per day for
          new patients; the notice period for moving an appointment; the waitlist priority order; follow-ups
          with the same doctor (bendable); staff notes carry no weight; the status table. Absence and
          interpreter notices, referral dates, blood tests, no-shows and duplicates are out of scope.
  medium  + referral letters that expire, a fasting blood test >= 1 working day before the visit with a daily
          lab cap, doctor absences (the absent doctor's appointments must be moved, with the notice period)
          and an interpreter's absence (one fewer interpreter that day)
  hard    + no-shows (hidden per-patient rates rising with lead time; expected-value scoring), overbooking of
          follow-ups (two to a slot, a cap per doctor session), duplicate requests (one appointment per
          patient and department) and extra trips of patients with several departments

A rule seed draws the client's rule values from the pools in case.yaml, each on its own: which clinic closes
on the holiday, how many morning slots the urgent reserve holds, the in-person interpreters per day, the
waitlist order, the lab cap (drawn in medium and hard only) and the overbooking cap (drawn in hard only; a single
candidate where the tier does not use them). The urgent window (2 working days) and
the notice period for a changed appointment (3 working days) are fixed: the reference never books an urgent
request later than tomorrow, and it moves appointments too rarely at short notice for another value to change
its answer (see README.md, "Parameters and rule seeds").
"""

from __future__ import annotations

import copy
import datetime as dt
import functools
import hashlib
import importlib.util
import json
import random
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

from fdebench2.casekit import LOCALES, Fatal, labels, program_session, write_csv, write_eml, write_sql

ENTRYPOINT = "scheduler.py:on_day"
REFERENCE = Path(__file__).resolve().parent / "reference" / "scheduler.py"

# ── calendar and the hospital's constants ────────────────────────────────────

BASE = dt.date(2026, 1, 5)              # a Monday: working-day arithmetic counts Monday-Friday from here
FIRST_DAY = dt.date(2026, 11, 9)        # day 0 of the hidden period (a Monday)
N_DAYS = 20                             # calls: days 0..19 (9 Nov - 4 Dec)
HORIZON = 10                            # bookings on days d+1 .. d+10
N_CAL = N_DAYS + HORIZON                # calendar days 0..29
HOLIDAY = 10                            # Monday 23 November 2026, City Day: one clinic closes (drawn)
SCORED = range(1, N_DAYS + 1)           # clinic days whose appointments are final at the end (1..20)
SLOT = 20
AM = tuple(540 + SLOT * k for k in range(9))      # 09:00 .. 11:40
PM = tuple(780 + SLOT * k for k in range(9))      # 13:00 .. 15:40
RESERVE = (540, 560)                    # the office's urgent reserve before the period (the initial book)
URGENT_DAYS = 2                         # an urgent request is seen within 2 working days of its first possible day
MOVE_NOTICE = 3                         # working days' notice for a changed date or time
DEPTS = ("IM", "CARD", "DERM", "ORTH", "PED")
CLOSABLE = ("DERM", "ORTH", "PED")
LANGS = ("L0", "F1", "F2", "F3", "F4")  # L0 = the local language
URGENCY = ("U", "S", "R")
WEIGHT = {"U": 3, "S": 2, "R": 1}
SEEN_VALUE = 10.0                       # per patient-slot seen on a clinic day of the period
WAIT_COST = 0.4                         # per working day of waiting x urgency weight
UNBOOKED_COST = 10.0                    # per request (need) never booked
MOVE_COST = 4.0                         # per change the hospital makes to a patient's appointment
COLLISION_COST = 30.0                   # hard: both patients of an overbooked slot turn up (three empty slots)
TRIP_COST = 3.0                         # hard: an extra hospital trip of a patient with several departments
COLLEAGUE_COST = 1.0                    # a follow-up seen by another doctor than the patient's own (only possible
                                        # under the head of the outpatient office's exception)
TABLE_COST = 20.0                       # per entry of the daily status table that is not exact (15 a day): the
                                        # department staffs for a wrong number, as much as two empty slots
LEAD_SLOPE = 0.01                       # hard: no-show rate + 1 point per working day of lead time
HIST_LEAD = 5                           # the patients' attendance counts were measured at ~5 days of lead
CALL_TIMEOUT = 10.0
TOTAL_TIMEOUT = 600.0

# Notices (data: the same in every setting; which apply is the tier's business).
ABSENCES = (("D13", 4, tuple(range(5, 15)), "illness"),      # notice day, absent days, reason
            ("D05", 9, (15, 16, 17, 18), "conference"))
INTERP_NOTICE, INTERP_DAY = 6, 9            # Tuesday 17 November: an interpreter away on Friday 20
HEAD_NOTE_DAY, HEAD_DOCTOR = 2, "D10"
NOTES_PLAN = ((7, "ORTH"), (14, "ORTH"), (17, "DERM"), (18, "ORTH"))   # the director's-acquaintance notes


def wd_index(date: dt.date) -> int | None:
    n = (date - BASE).days
    w, r = divmod(n, 7)
    return None if r >= 5 else w * 5 + r


def wd_date(i: int) -> dt.date:
    w, r = divmod(i, 5)
    return BASE + dt.timedelta(days=7 * w + r)


DAY0 = wd_index(FIRST_DAY)


def day_date(t: int) -> dt.date:
    return wd_date(DAY0 + t)


_ISO: dict = {}


def iso(t: int) -> str:
    if t not in _ISO:
        _ISO[t] = day_date(t).isoformat()
    return _ISO[t]


def parse_day(s) -> int | None:
    """A working-day index (relative to day 0) from 'YYYY-MM-DD'; None for anything else or a weekend."""
    if not isinstance(s, str):
        return None
    try:
        i = wd_index(dt.date.fromisoformat(s.strip()))
    except ValueError:
        return None
    return None if i is None else i - DAY0


def hhmm(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"


def parse_start(s) -> int | None:
    if not isinstance(s, str) or len(s.strip()) != 5 or s.strip()[2] != ":":
        return None
    try:
        h, m = int(s.strip()[:2]), int(s.strip()[3:])
    except ValueError:
        return None
    return h * 60 + m if 0 <= h < 24 and 0 <= m < 60 else None


# ── the world ────────────────────────────────────────────────────────────────

DOCTOR_PLAN = [  # (department, languages besides L0, weekly sessions (weekday, half))
    ("IM", ["F1"], [(0, "AM"), (1, "PM"), (3, "AM")]),
    ("IM", [], [(0, "PM"), (2, "AM"), (4, "AM")]),
    ("IM", ["F2"], [(1, "AM"), (3, "PM"), (4, "PM")]),
    ("IM", [], [(2, "PM"), (4, "PM")]),
    ("CARD", ["F1"], [(0, "AM"), (2, "PM"), (3, "AM")]),
    ("CARD", [], [(1, "AM"), (4, "AM")]),
    ("CARD", ["F3"], [(2, "AM"), (3, "PM"), (4, "PM")]),
    ("DERM", ["F1"], [(0, "AM"), (1, "PM"), (2, "AM"), (4, "AM")]),
    ("DERM", [], [(1, "AM"), (3, "AM"), (3, "PM")]),
    ("ORTH", ["F4"], [(0, "AM"), (1, "PM"), (2, "AM"), (3, "PM")]),
    ("ORTH", [], [(1, "AM"), (3, "AM"), (4, "PM")]),
    ("ORTH", ["F1", "F2"], [(0, "PM"), (2, "PM"), (4, "AM")]),
    ("PED", ["F1"], [(0, "PM"), (1, "AM"), (2, "PM"), (3, "AM")]),
    ("PED", [], [(0, "AM"), (2, "AM"), (3, "PM"), (4, "AM")]),
]
DEMAND = {"IM": 14.5, "CARD": 9.0, "DERM": 10.0, "ORTH": 15.0, "PED": 9.0}   # requests per day
NEW_SHARE = 0.45
TEST_SHARE = {"IM": 0.3, "CARD": 0.3, "PED": 0.12}   # requests that need a fasting blood test first
PREV_WEIGHT = {"D11": 2.5, "D13": 2.5, "D05": 2.0}
N_WAIT0 = 45
N_DUPLICATES = 10
N_MULTI = 10
CANCEL_SHARE = 0.09
CHRONIC_SHARE = 0.18                    # patients who miss most of their appointments
HIST_URGENT = 0.10                      # history: chance that a reserve slot holds an urgent patient
HIST_COLLEAGUE = 0.12                   # history: follow-ups seen by a colleague (exceptions the head granted)


@dataclass
class Doctor:
    id: str
    dept: str
    langs: tuple
    sessions: frozenset          # {(weekday, half)}


@dataclass
class Req:
    id: str
    patient: str
    dept: str
    prev: str | None             # previous doctor of a follow-up; None for a new patient
    urgency: str
    lang: str
    recv: int                    # working day received (relative to day 0; negative before the period)
    earliest: int
    referral: int | None = None  # new patients: last working day the referral letter is valid
    test: bool = False           # needs a fasting blood test before the visit
    note: int = 0                # triage note index
    notes: list = field(default_factory=list)
    base_p: float = 0.0          # hidden no-show rate at zero lead time
    past: int = 0
    missed: int = 0
    cancel_k: int = 0            # the patient cancels k working days before the appointment (0 = never)
    dup_of: str = ""             # a planted duplicate of this request (same patient and department)

    @property
    def new(self) -> bool:
        return self.prev is None

    @property
    def ref(self) -> int:
        """The first day the request can be seen: its earliest date, or the day after it was received."""
        return max(self.earliest, self.recv + 1)


@dataclass
class Appt:
    doctor: str
    day: int
    start: int
    n: int                       # slots: 2 for a new patient, 1 for a follow-up
    test: int | None = None      # blood-test day
    booked_on: int = 0           # the call day of the latest booking or change (lead time for no-shows)

    def slots(self) -> list[int]:
        return [self.start + SLOT * k for k in range(self.n)]


@dataclass
class World:
    doctors: list
    reqs: list = field(default_factory=list)
    initial_book: dict = field(default_factory=dict)     # request id -> Appt (days 0..9)
    initial_wait: list = field(default_factory=list)     # request ids waiting at day 0
    by_day: dict = field(default_factory=dict)           # call day -> new request ids
    notices: dict = field(default_factory=dict)          # call day -> static notices
    past_appts: list = field(default_factory=list)       # history: (Req, Appt, outcome)
    past_reqs: list = field(default_factory=list)
    sample: dict = field(default_factory=dict)
    repeat_keys: set = field(default_factory=set)        # (patient, department) with more than one request
    _cache: dict = field(default_factory=dict, repr=False)

    def __post_init__(self):
        self.doc = {d.id: d for d in self.doctors}
        self.req: dict = {}

    def sessions(self, doc: str, t: int) -> list:
        """[(half, starts)] of the doctor's sessions on calendar day t, as the calendar lists them."""
        key = ("sess", doc, t)
        if key not in self._cache:
            wd = day_date(t).weekday()
            out = [(h, AM if h == "AM" else PM) for h in ("AM", "PM") if (wd, h) in self.doc[doc].sessions]
            self._cache[key] = out
        return self._cache[key]

    def slot_half(self, doc: str, t: int) -> dict:
        key = ("half", doc, t)
        if key not in self._cache:
            self._cache[key] = {s: h for h, starts in self.sessions(doc, t) for s in starts}
        return self._cache[key]


# ── the rule seed's parameters ───────────────────────────────────────────────

RESERVE_SIZES = (2, 3)                  # the candidates of reserve_slots
RESERVE_TIMES = {   # the reserve's slots as each locale lists them, by the number of slots
    2: {"zh": "09:00 和 09:20", "en": "09:00 and 09:20", "ko": "09:00, 09:20", "ja": "09:00と09:20",
        "es": "09:00 y 09:20"},
    3: {"zh": "09:00、09:20 和 09:40", "en": "09:00, 09:20 and 09:40", "ko": "09:00, 09:20, 09:40",
        "ja": "09:00、09:20と09:40", "es": "09:00, 09:20 y 09:40"},
}


def derive_params(params: dict, tier: str) -> dict:
    """The urgent reserve's slot times, worded per locale, from the drawn number of reserve slots."""
    return {"reserve_times": dict(RESERVE_TIMES[int(params["reserve_slots"])])}


def no_show(r: Req, lead: int) -> float:
    """True probability that the patient stays away from an appointment booked `lead` working days ahead."""
    return min(0.9, r.base_p + LEAD_SLOPE * max(lead, 0))


ORDERS = ("urgency_received", "received", "urgency_earliest")     # the candidates of waitlist_order


def priority(order: str, r: Req) -> tuple:
    """A request's waitlist priority under an order (smaller first)."""
    if order == "received":
        return (0 if r.urgency == "U" else 1, r.recv, r.id)
    if order == "urgency_earliest":
        return (URGENCY.index(r.urgency), r.earliest, r.id)
    return (URGENCY.index(r.urgency), r.recv, r.id)


class _View:
    """The world as one setting's rules see it."""

    def __init__(self, world: World, setting):
        self._w, self.setting = world, setting
        self.medium, self.hard = setting.at_least("medium"), setting.at_least("hard")
        self.closed = str(setting["closed_dept"])
        self.urgent_days = URGENT_DAYS
        self.reserve = AM[:int(setting["reserve_slots"])]     # the first N slots of every morning session
        self.interpreters = int(setting["interpreters_per_day"])
        self.lab_cap = int(setting["lab_cap"])
        self.ob_cap = int(setting["overbooked_per_session"])
        self.notice = MOVE_NOTICE
        self.order = str(setting["waitlist_order"])
        self._cache = world._cache.setdefault(("setting", setting.label), {})

    def __getattr__(self, name):
        return getattr(self._w, name)

    def absent(self, doc: str, t: int, d: int) -> bool:
        """Medium+: the doctor is known (by call day d) to be away on day t."""
        if not self.medium:
            return False
        return any(doc == a and t in days and d >= nd for a, nd, days, _ in ABSENCES)

    def closed_on(self, dept: str, t: int) -> bool:
        return t == HOLIDAY and dept == self.closed

    def interp_cap(self, t: int, d: int) -> int:
        return self.interpreters - (1 if self.medium and t == INTERP_DAY and d >= INTERP_NOTICE else 0)

    def deadline(self, r: Req) -> int:
        return r.ref + self.urgent_days

    def prio(self, r: Req) -> tuple:
        """Waitlist priority (smaller first)."""
        return priority(self.order, r)

    def dup(self, r: Req) -> bool:
        return self.hard and bool(r.dup_of)


# ── generation ───────────────────────────────────────────────────────────────

def _base_p(rng: random.Random) -> float:
    """A patient's no-show rate at zero lead time: most patients nearly always come, a minority (CHRONIC_SHARE)
    miss more appointments than they keep. Which kind a patient is shows in their record, not in the request."""
    return round(rng.betavariate(6, 4) if rng.random() < CHRONIC_SHARE else rng.betavariate(2, 30), 4)


def _history_counts(rng: random.Random, r: Req) -> None:
    if not r.new or rng.random() < 0.3:
        r.past = rng.randint(2, 14)
        r.missed = sum(rng.random() < r.base_p + LEAD_SLOPE * HIST_LEAD for _ in range(r.past))


def _cancel(rng: random.Random, r: Req) -> None:
    if rng.random() < CANCEL_SHARE:
        r.cancel_k = rng.choices((1, 2, 3, 4), weights=(35, 30, 20, 15))[0]


def _lang(rng: random.Random) -> str:
    return "L0" if rng.random() < 0.8 else rng.choice(LANGS[1:])


def _am_doctors(w: World, dept: str, t: int) -> list[str]:
    """Doctors of the department with a morning session on day t that no absence or closure can touch."""
    if t >= N_CAL or (t == HOLIDAY and dept in CLOSABLE):
        return []
    return [d.id for d in w.doctors if d.dept == dept and any(h == "AM" for h, _ in w.sessions(d.id, t))
            and not any(d.id == a and t in days for a, _, days, _ in ABSENCES)]


def _initial(w: World, rng: random.Random, rp: random.Random) -> list[Req]:
    """The booking book at day 0 (appointments on days 0..9 booked before the period) and its requests."""
    reqs, interp, lab = [], {}, {}
    for t in range(HORIZON):
        occ = 0.97 - 0.06 * t
        for doc in w.doctors:
            for half, starts in w.sessions(doc.id, t):
                i = 0
                while i < len(starts):
                    s = starts[i]
                    # the office's practice: the first two morning slots stay with urgent patients, also on the
                    # day itself (it never gave them to anyone else)
                    held = half == "AM" and s in RESERVE
                    if held or rng.random() >= occ:
                        i += 1
                        continue
                    new = i + 1 < len(starts) and rng.random() < NEW_SHARE and not (
                        half == "AM" and starts[i + 1] in RESERVE)
                    urg = rng.choices(("S", "R"), weights=(30, 70))[0]
                    recv = -rng.randint(1, 10)
                    earliest = recv + 1 if rng.random() < 0.8 else rng.randint(recv + 1, t)
                    lang = _lang(rng)
                    if new and lang not in doc.langs:
                        if interp.get(t, 0) >= 1:
                            lang = "L0"
                        else:
                            interp[t] = interp.get(t, 0) + 1
                    r = Req("", "", doc.dept, None if new else doc.id, urg, lang, recv, earliest,
                            referral=(t + rng.randint(30, 60)) if new else None, note=rng.randrange(3))
                    booked = rng.randint(max(recv, -10), -1)
                    test = None
                    if rng.random() < TEST_SHARE.get(doc.dept, 0.0):
                        lo = max(earliest, booked + 1)
                        if lo <= t - 1:
                            test = rng.randint(lo, t - 1)
                            if test >= 1 and lab.get(test, 0) >= 3:
                                test = None
                            elif test >= 1:
                                lab[test] = lab.get(test, 0) + 1
                    r.test = test is not None
                    r.base_p = _base_p(rp)
                    _history_counts(rp, r)
                    _cancel(rp, r)
                    reqs.append(r)
                    w.initial_book[id(r)] = Appt(doc.id, t, s, 2 if new else 1, test, booked)
                    i += 2 if new else 1
    return reqs


def _waiting(w: World, rng: random.Random, rp: random.Random) -> list[Req]:
    out = []
    for _ in range(N_WAIT0):
        dept = rng.choices(DEPTS, weights=(20, 8, 30, 35, 7))[0]
        new = rng.random() < NEW_SHARE
        docs = [d.id for d in w.doctors if d.dept == dept]
        recv = -rng.randint(1, 8)
        r = Req("", "", dept, None if new else rng.choices(docs, [PREV_WEIGHT.get(x, 1) for x in docs])[0],
                rng.choices(("S", "R"), weights=(35, 65))[0], _lang(rng), recv, recv + 1, note=rng.randrange(3))
        if new:
            r.referral = recv + 1 + rng.randint(5, 14) if rng.random() < 0.3 else recv + 60
        r.test = rng.random() < TEST_SHARE.get(dept, 0.0)
        r.base_p = _base_p(rp)
        _history_counts(rp, r)
        _cancel(rp, r)
        out.append(r)
    return out


def _new_request(w: World, rng: random.Random, rp: random.Random, d: int, dept: str, urgent: bool) -> Req:
    docs = [x.id for x in w.doctors if x.dept == dept]
    if urgent:
        new = rng.random() < 0.5
        prev = None if new else rng.choice(_am_doctors(w, dept, d + 1))
        r = Req("", "", dept, prev, "U", "L0", d, d + 1, note=rng.randrange(3))
        if new:
            r.referral = d + 60
    else:
        new = rng.random() < NEW_SHARE
        prev = None if new else rng.choices(docs, [PREV_WEIGHT.get(x, 1) for x in docs])[0]
        earliest = d + 1 if rng.random() < 0.7 else d + rng.randint(2, 12)
        r = Req("", "", dept, prev, rng.choices(("S", "R"), weights=(28, 72))[0], _lang(rng), d, earliest,
                note=rng.randrange(3))
        if new:
            r.referral = earliest + rng.randint(2, 12) if rng.random() < 0.3 else d + 60
        r.test = rng.random() < TEST_SHARE.get(dept, 0.0)
    r.base_p = _base_p(rp)
    _history_counts(rp, r)
    _cancel(rp, r)
    return r


ACQUAINTANCE = (
    "The hospital director's acquaintance - please book tomorrow morning.",
    "A personal friend of our director. Tomorrow morning, please, whatever it takes.",
    "Director's office: please fit this patient in tomorrow morning.",
    "Acquaintance of the director - tomorrow morning if at all possible, thank you.",
)
HEAD_NOTE = ("Please keep my afternoon clinics free for my own patients from now on - do not fill them from the "
             "waitlist. I will tell the office whom to book there.")


def _period(w: World, rng: random.Random, rp: random.Random) -> list[Req]:
    out = []
    for d in range(N_DAYS):
        for dept in DEPTS:
            mean = DEMAND[dept] * (1.15 if day_date(d).weekday() == 0 else 1.0)
            n = max(0, round(rng.gauss(mean, 2.0)))
            urgent = rng.random() < 0.16 and bool(_am_doctors(w, dept, d + 1)) and n > 0
            for k in range(n):
                out.append(_new_request(w, rng, rp, d, dept, urgent and k == 0))
    return out


def _plant(w: World, rng: random.Random, rp: random.Random, period: list[Req]) -> list[Req]:
    extra = []
    plain = [r for r in period if r.urgency != "U" and r.recv <= 16]
    picked = rng.sample(plain, N_DUPLICATES + N_MULTI)
    for r in picked[:N_DUPLICATES]:                  # duplicates: the same need requested again
        recv = min(N_DAYS - 1, r.recv + rng.randint(0, 3))
        x = Req("", "", r.dept, r.prev, r.urgency, r.lang, recv, max(r.earliest, recv + 1), r.referral, r.test,
                rng.randrange(3), base_p=r.base_p, past=r.past, missed=r.missed)
        x.dup_of = "pending"
        x._orig = r
        extra.append(x)
    for r in picked[N_DUPLICATES:]:                  # one patient, a second department the same day
        dept = rng.choice([x for x in DEPTS if x != r.dept])
        x = Req("", "", dept, None, rng.choice(("S", "R")), r.lang, r.recv, r.earliest, r.recv + 60, False,
                rng.randrange(3), base_p=r.base_p, past=r.past, missed=r.missed)
        x._same = r
        extra.append(x)
    for k, (d, dept) in enumerate(NOTES_PLAN):       # the director's acquaintances
        x = Req("", "", dept, None, "R", "L0", d, d + 1, d + 60, False, rng.randrange(3))
        x.base_p = _base_p(rp)
        x.notes = [{"author_role": "director_office", "request": "book_tomorrow_morning",
                    "text": ACQUAINTANCE[k]}]
        extra.append(x)
    return extra


def build_world(seed: int) -> World:
    """Everything every setting needs (the data and the hidden period are the same in all of them)."""
    w = World([Doctor(f"D{i + 1:02d}", dept, tuple(["L0"] + fl), frozenset(sess))
               for i, (dept, fl, sess) in enumerate(DOCTOR_PLAN)])
    rp = random.Random(seed * 10 + 9)
    booked = _initial(w, random.Random(seed * 10 + 1), rp)
    waiting = _waiting(w, random.Random(seed * 10 + 2), rp)
    period = _period(w, random.Random(seed * 10 + 3), rp)
    extra = _plant(w, random.Random(seed * 10 + 4), rp, period)
    past = _history(w, random.Random(seed * 10 + 5))
    allr = booked + waiting + period + extra
    ro = random.Random(seed * 10 + 6)
    order = sorted(allr, key=lambda r: (r.recv, ro.random()))
    patients = ro.sample(range(100000, 999999), len(allr) + len(past))
    for k, r in enumerate(order, start=1):
        r.id = f"Q{k:05d}"
    for r, num in zip(order, patients):
        r.patient = f"P{num}"
    for r in allr:
        if getattr(r, "_orig", None) is not None:
            o = r._orig
            del r._orig
            r.patient = o.patient
            first, second = sorted((o, r), key=lambda x: x.id)    # the later request is the duplicate
            first.dup_of, second.dup_of = "", first.id
        if getattr(r, "_same", None) is not None:
            r.patient = r._same.patient
            del r._same
    for (r, a, o), num in zip(past, patients[len(allr):]):
        r.patient = f"P{num}"
    w.past_appts = past
    w.reqs = order
    w.req = {r.id: r for r in order}
    w.initial_book = {r.id: w.initial_book[id(r)] for r in booked}
    w.initial_wait = sorted(r.id for r in waiting)
    for d in range(N_DAYS):
        w.by_day[d] = [r.id for r in order if r.recv == d]
    w.past_reqs = [r for r in order if r.recv < 0]
    seen: dict = {}
    for r in order:
        seen[(r.patient, r.dept)] = seen.get((r.patient, r.dept), 0) + 1
    w.repeat_keys = {k for k, n in seen.items() if n > 1}
    w.notices = _notices()
    w.sample = _pilot(w, seed)
    return w


def _notices() -> dict:
    out: dict = {}
    for k, (doc, nd, days, why) in enumerate(ABSENCES, start=1):
        out.setdefault(nd, []).append({
            "notice_id": f"NT-A{k}", "type": "doctor_absence", "doctor_id": doc, "from": iso(days[0]),
            "to": iso(days[-1]), "reason": why,
            "text": ("Dr {doc} is off sick" if why == "illness" else "Dr {doc} is at a conference").format(doc=doc)
            + f" from {iso(days[0])} to {iso(days[-1])} and holds no clinics then."})
    out.setdefault(INTERP_NOTICE, []).append({
        "notice_id": "NT-I1", "type": "interpreter_absence", "date": iso(INTERP_DAY),
        "in_person_interpreters_change": -1,
        "text": f"One of our in-person interpreters is away on {iso(INTERP_DAY)}."})
    out.setdefault(HEAD_NOTE_DAY, []).append({
        "notice_id": "NT-H1", "type": "staff_note", "author_role": "department_head", "doctor_id": HEAD_DOCTOR,
        "text": HEAD_NOTE})
    return out


def _history(w: World, rng: random.Random) -> list:
    """Four weeks of past appointments (12 Oct - 6 Nov) with their outcome, for the visible data."""
    out = []
    for t in range(-20, 0):
        for doc in w.doctors:
            colleagues = [x.id for x in w.doctors if x.dept == doc.dept and x.id != doc.id]
            for half, starts in w.sessions(doc.id, t):
                i = 0
                while i < len(starts):
                    # The office's practice before the program: the first two morning slots (09:00, 09:20) are
                    # kept for urgent patients and stay empty when none comes; everything else fills up.
                    reserve = half == "AM" and starts[i] in RESERVE
                    if rng.random() >= (HIST_URGENT if reserve else 0.92):
                        i += 1
                        continue
                    if reserve:
                        new, urg = starts[i] == RESERVE[0] and rng.random() < 0.5, "U"
                    else:
                        new = i + 1 < len(starts) and rng.random() < NEW_SHARE
                        urg = rng.choices(("S", "R"), weights=(30, 70))[0]
                    recv = t - (1 if urg == "U" else rng.randint(1, 12))
                    prev = None if new else doc.id
                    if prev and urg != "U" and colleagues and rng.random() < HIST_COLLEAGUE:
                        prev = rng.choice(colleagues)        # seen by a colleague of the patient's own doctor
                    r = Req("", "", doc.dept, prev, urg, _lang(rng), recv, recv + 1,
                            note=rng.randrange(3))
                    if new:
                        r.referral = recv + rng.randint(15, 60)
                    r.test = urg != "U" and rng.random() < TEST_SHARE.get(doc.dept, 0.0)
                    r.base_p = _base_p(rng)
                    booked = rng.randint(max(recv, t - 12), t - 1)
                    a = Appt(doc.id, t, starts[i], 2 if new else 1, t - 1 if r.test else None, booked)
                    if rng.random() < 0.07:
                        outcome = "cancelled"
                    else:
                        outcome = "missed" if rng.random() < no_show(r, t - booked) else "attended"
                    out.append((r, a, outcome))
                    i += 2 if new else 1
    return out


# ── what the program is sent each day ────────────────────────────────────────

TRIAGE = {
    "U": ("symptoms getting worse quickly, referring GP asks for a prompt review",
          "abnormal test result flagged by the referring doctor", "severe pain not controlled by current medication"),
    "S": ("symptoms ongoing for several weeks", "medication needs adjusting soon", "GP referral, should not wait long"),
    "R": ("routine check", "annual review", "mild long-standing complaint"),
}


def req_json(w: World, r: Req) -> dict:
    key = ("rj", r.id)
    if key not in w._cache:
        w._cache[key] = {
            "request_id": r.id, "patient_id": r.patient, "received": iso(r.recv), "department": r.dept,
            "visit_type": "new" if r.new else "follow_up", "previous_doctor": r.prev, "urgency": r.urgency,
            "triage_note": TRIAGE[r.urgency][r.note], "preferred_language": r.lang,
            "earliest_date": iso(r.earliest), "referral_valid_until": iso(r.referral) if r.referral is not None
            else None, "pre_visit_test": r.test, "past_appointments": r.past, "missed_appointments": r.missed,
            "notes": [dict(n) for n in r.notes]}
    return w._cache[key]


def doctors_json(w: World) -> list:
    return [{"doctor_id": d.id, "department": d.dept, "languages": list(d.langs)} for d in w.doctors]


def sessions_json(w: World, d: int) -> list:
    key = ("sj", d)
    if key not in w._cache:
        w._cache[key] = [{"doctor_id": doc.id, "date": iso(t), "session": h, "starts": [hhmm(s) for s in starts]}
                         for t in range(d + 1, d + HORIZON + 1) for doc in w.doctors
                         for h, starts in w.sessions(doc.id, t)]
    return w._cache[key]


def _uniform(*parts) -> float:
    h = hashlib.sha256("|".join(map(str, parts)).encode()).digest()
    return int.from_bytes(h[:8], "big") / 2 ** 64


# ── the engine and the evaluator ─────────────────────────────────────────────

class Engine:
    """One replay of the hidden period in one setting. begin(d) builds the day's input; end(d, out, err)
    applies the program's actions, checks the rules and scores the status table."""

    def __init__(self, view: _View, trace: bool = False):
        self.v, self.w = view, view._w
        self.trace = [] if trace else None      # per call, what diagnose() reads (score() keeps it private)
        self.rec: dict | None = None
        self.appt = {rid: copy.copy(a) for rid, a in self.w.initial_book.items()}
        self.occ: dict = {}
        for rid, a in self.appt.items():
            self._occupy(rid, a)
        self.open = set(self.w.initial_wait)
        self.closed: set = set()
        self.past: dict = {}
        self.moves = 0
        self.freed: list = []            # slots freed by patients' cancellations (for the README's numbers)
        self.held: dict = {}             # (patient, department) -> appointments that took place in the period
        self.released_on: dict = {}      # request id -> (call day, day, start) of the hospital's latest release
        self.found: dict = {}
        self.acc: list = []
        self.wrong = 0                   # entries of the daily status tables that were not exact
        self.m = {"booked": 0, "moved": 0, "released": 0, "cancellations": 0, "calls_failed": 0,
                  "actions_rejected": 0}

    def __deepcopy__(self, memo):
        new = Engine.__new__(Engine)
        memo[id(self)] = new
        for k, val in self.__dict__.items():
            new.__dict__[k] = val if k in ("v", "w") else copy.deepcopy(val, memo)
        return new

    # ── state ────────────────────────────────────────────────────────────────
    def _occupy(self, rid: str, a: Appt) -> None:
        for s in a.slots():
            self.occ.setdefault((a.doctor, a.day, s), []).append(rid)

    def _vacate(self, rid: str, a: Appt) -> None:
        for s in a.slots():
            lst = self.occ.get((a.doctor, a.day, s))
            if lst and rid in lst:
                lst.remove(rid)
                if not lst:
                    del self.occ[(a.doctor, a.day, s)]

    def flag(self, rule: str, msg: str, **info) -> None:
        self.found.setdefault(rule, []).append(msg)
        if self.rec is not None:
            self.rec["viol"].append({"rule": rule, **info})

    # ── one day ──────────────────────────────────────────────────────────────
    def begin(self, d: int) -> dict:
        w = self.w
        attendance = []
        for rid in sorted(r for r, a in self.appt.items() if a.day == d):
            a = self.appt.pop(rid)
            self._vacate(rid, a)
            self.past[rid] = a
            r = w.req[rid]
            self.held[(r.patient, r.dept)] = self.held.get((r.patient, r.dept), 0) + 1
            came = _uniform("att", rid, d) >= no_show(r, d - a.booked_on)
            attendance.append({"request_id": rid, "patient_id": r.patient, "doctor_id": a.doctor,
                               "start": hhmm(a.start), "attended": came})
        notices = [dict(n) for n in w.notices.get(d, [])]
        for rid in sorted(self.appt):
            a, r = self.appt[rid], w.req[rid]
            if r.cancel_k and max(a.booked_on + 1, a.day - r.cancel_k, 0) == d and d < a.day:
                self._vacate(rid, a)
                del self.appt[rid]
                self.closed.add(rid)
                self.m["cancellations"] += 1
                self.freed.extend((a.doctor, a.day, s) for s in a.slots())
                notices.append({"notice_id": f"CX-{rid}", "type": "cancellation", "request_id": rid,
                                "patient_id": r.patient, "doctor_id": a.doctor, "date": iso(a.day),
                                "start": hhmm(a.start), "text": "The patient cancelled this appointment."})
        new = w.by_day.get(d, [])
        waitlist = sorted(self.open)
        self.open.update(new)
        self.start = {rid: (a.doctor, a.day, a.start, a.test) for rid, a in self.appt.items()}
        self.start_open = set(self.open)
        if self.trace is not None:
            self.rec = {"day": d, "viol": [], "placed": [], "changed": 0, "released": [], "double": 0,
                        "interp_at_start": sum(1 for rid, a in self.appt.items() if a.day == INTERP_DAY
                                               and w.req[rid].new and w.req[rid].lang not in w.doc[a.doctor].langs)}
        book = [{"request_id": rid, "doctor_id": a.doctor, "date": iso(a.day), "start": hhmm(a.start),
                 "slots": a.n, "test_date": iso(a.test) if a.test is not None else None,
                 "booked_on": iso(a.booked_on), "request": req_json(w, w.req[rid])}
                for rid, a in sorted(self.appt.items(), key=lambda x: (x[1].day, x[1].doctor, x[1].start, x[0]))]
        return {"date": iso(d), "day_index": d, "days_in_period": N_DAYS, "period_end": iso(N_DAYS - 1),
                "booking_window": {"first": iso(d + 1), "last": iso(d + HORIZON)},
                "doctors": doctors_json(w), "sessions": sessions_json(w, d),
                "new_requests": [req_json(w, w.req[rid]) for rid in new], "notices": notices,
                "attendance": attendance, "book": book,
                "waitlist": [req_json(w, w.req[rid]) for rid in waitlist]}

    def _apply(self, d: int, act, problems: list) -> None:
        w = self.w
        if not isinstance(act, dict):
            problems.append(f"action is not an object: {str(act)[:60]}")
            return
        kind, rid = str(act.get("type", "")).strip().lower(), act.get("request_id")
        if kind not in ("book", "move", "release"):
            problems.append(f"unknown action type {kind!r}")
            return
        if not isinstance(rid, str) or rid not in w.req:
            problems.append(f"{kind}: unknown request {rid!r}")
            return
        if kind == "book" and rid not in self.open:
            problems.append(f"book {rid}: not on the waitlist")
            return
        if kind in ("move", "release") and rid not in self.appt:
            problems.append(f"{kind} {rid}: no upcoming appointment")
            return
        if kind == "release":
            a = self.appt.pop(rid)
            self._vacate(rid, a)
            self.open.add(rid)
            self.released_on[rid] = (d, a.day, a.start)
            return
        doc, t, s = act.get("doctor_id"), parse_day(act.get("date")), parse_start(act.get("start"))
        if doc not in w.doc or t is None or s is None:
            problems.append(f"{kind} {rid}: bad doctor, date or start {doc!r} {act.get('date')!r} "
                            f"{act.get('start')!r}")
            return
        if not d + 1 <= t <= d + HORIZON:
            problems.append(f"{kind} {rid}: {act.get('date')} is outside the booking window")
            return
        raw = act.get("test_date")
        test = parse_day(raw) if raw not in (None, "") else None
        if raw not in (None, "") and test is None:
            test = -10 ** 6                        # unreadable: never a valid test day
        r = w.req[rid]
        if not (self.v.medium and r.test):
            test = None
        if kind == "move":
            old = self.appt.pop(rid)
            self._vacate(rid, old)
            booked_on = d if (old.doctor, old.day, old.start) != (doc, t, s) else old.booked_on
        else:
            self.open.discard(rid)
            booked_on = d
        a = Appt(doc, t, s, 1 if r.prev else 2, test, booked_on)
        self.appt[rid] = a
        self._occupy(rid, a)

    def end(self, d: int, out, err) -> None:
        problems: list = []
        actions, table, answered = [], None, False
        if err is not None:
            problems.append(f"call failed: {err}"[:200])
            self.m["calls_failed"] += 1
        elif not isinstance(out, dict) or not isinstance(out.get("actions"), list):
            problems.append("output is not {'actions': [...], 'status_table': {...}}")
        else:
            actions, table, answered = out["actions"], out.get("status_table"), True
        for act in actions:
            n = len(problems)
            self._apply(d, act, problems)
            self.m["actions_rejected"] += len(problems) - n
        for p in problems:
            self.flag("well_formed", f"{iso(d)}: {p}")
        self._check(d)
        formed = table_formed(table)
        if answered and not formed:      # a call that failed breaks well_formed, not this
            self.flag("status_table", f"{iso(d)}: the status table lacks a department or one of its three whole "
                                      f"numbers")
        ok = self._table_right(d, table)
        self.acc.append(ok / 15)
        self.wrong += 15 - ok
        if self.rec is not None:
            self.rec.update(table=table if formed else None, truth=self.table_truth(d),
                            readings=self.table_readings(d))
            self.trace.append(self.rec)
            self.rec = None

    # ── the rules ────────────────────────────────────────────────────────────
    def _check(self, d: int) -> None:
        w, v = self.w, self.v
        day = iso(d)
        for rid, a in self.appt.items():
            was = self.start.get(rid)
            if was == (a.doctor, a.day, a.start, a.test):
                continue
            r = w.req[rid]
            placed = was is None or was[:3] != (a.doctor, a.day, a.start)
            if was is None:
                self.m["booked"] += 1
            elif placed:
                self.m["moved"] += 1
                self.moves += 1
            if placed and self.rec is not None:
                self.rec["placed"].append({"rid": rid, "doc": a.doctor, "day": a.day, "start": a.start,
                                           "from": None if was is None else [was[0], was[1]],
                                           "shared": len(self.occ.get((a.doctor, a.day, a.start), ())) > 1})
                self.rec["changed"] += was is not None and (a.day, a.start) != was[1:3]
            if placed:
                half = w.slot_half(a.doctor, a.day)
                if any(s not in half for s in a.slots()) or len({half.get(s) for s in a.slots()}) != 1:
                    self.flag("slot_length", f"{day}: {rid} at {a.doctor} {iso(a.day)} {hhmm(a.start)} "
                                             f"({a.n} slot(s)) is not within one session of the calendar")
                if w.doc[a.doctor].dept != r.dept:
                    self.flag("department_match", f"{day}: {rid} ({r.dept}) with {a.doctor}")
                if a.day < r.earliest:
                    self.flag("not_before_earliest", f"{day}: {rid} on {iso(a.day)} before {iso(r.earliest)}")
                if r.urgency != "U" and a.day >= d + 2 and any(
                        s in v.reserve and w.slot_half(a.doctor, a.day).get(s) == "AM" for s in a.slots()):
                    self.flag("urgent_reserve", f"{day}: {r.urgency} request {rid} in the reserve slot "
                                                f"{a.doctor} {iso(a.day)} {hhmm(a.start)}", rid=rid,
                              start=a.start)
                # Notice is for a changed date or time; the same slot with another doctor needs none.
                if was is not None and (a.day, a.start) != was[1:3] and a.day < d + v.notice:
                    self.flag("move_notice", f"{day}: {rid} moved to {iso(a.day)} with less than {v.notice} "
                                             f"working days' notice", rid=rid)
                elif was is None and rid in self.released_on:
                    # A request the hospital released and books again later: notice from the day of the release
                    # (the same date and time as the released appointment needs none).
                    rd, t0, s0 = self.released_on[rid]
                    if a.day < rd + v.notice and (a.day, a.start) != (t0, s0):
                        self.flag("move_notice", f"{day}: {rid} released on {iso(rd)} and booked again for "
                                                 f"{iso(a.day)}, less than {v.notice} working days after the release",
                                  rid=rid)
                if r.prev and a.doctor != r.prev:
                    self.flag("follow_up_same_doctor", f"{day}: follow-up {rid} with {a.doctor}, not {r.prev}")
            if v.medium and r.new and a.day > r.referral:
                self.flag("referral_validity", f"{day}: {rid} on {iso(a.day)}, referral valid until "
                                               f"{iso(r.referral)}")
            if v.medium and r.test:
                t, old = a.test, (was[3] if was else None)
                if t is None or t > a.day - 1 or t < r.earliest or (t != old and t < d + 1):
                    self.flag("test_before_visit", f"{day}: {rid} visit {iso(a.day)} test "
                                                   f"{iso(t) if t is not None and t > -1000 else t}")
        for rid, was in self.start.items():
            if rid not in self.appt:
                self.m["released"] += 1
                self.moves += 1
                if self.rec is not None:
                    self.rec["released"].append((rid, was[0], was[1]))

        # End state of the upcoming book.
        sessions_ob: dict = {}
        for (doc, t, s), lst in self.occ.items():
            if t < d + 1 or not lst:
                continue
            if not v.hard:
                if len(lst) > 1:
                    self.flag("no_double_booking", f"{day}: {doc} {iso(t)} {hhmm(s)} holds {sorted(lst)}")
            else:
                if len(lst) > 2 or (len(lst) == 2 and any(w.req[x].new for x in lst)):
                    self.flag("slot_capacity", f"{day}: {doc} {iso(t)} {hhmm(s)} holds {sorted(lst)}")
                if len(lst) >= 2:
                    key = (doc, t, w.slot_half(doc, t).get(s, "?"))
                    sessions_ob[key] = sessions_ob.get(key, 0) + 1
                    if self.rec is not None:
                        self.rec["double"] += 1
        for (doc, t, h), n in sessions_ob.items():
            if n > v.ob_cap:
                self.flag("overbooking_limit", f"{day}: {doc} {iso(t)} {h} has {n} overbooked slots")
        interp, lab, per = {}, {}, {}
        for rid, a in self.appt.items():
            r = w.req[rid]
            dept = w.doc[a.doctor].dept
            if r.new and r.lang not in w.doc[a.doctor].langs:
                interp[a.day] = interp.get(a.day, 0) + 1
            if v.medium and r.test and a.test is not None and a.test >= d + 1:
                lab[a.test] = lab.get(a.test, 0) + 1
            if v.closed_on(dept, a.day):
                self.flag("holiday_closure", f"{day}: {rid} with {a.doctor} on {iso(a.day)}")
            if v.absent(a.doctor, a.day, d):
                self.flag("doctor_available", f"{day}: {rid} with {a.doctor} on {iso(a.day)}, a day of absence")
            if r.urgency == "U" and a.day > v.deadline(r):
                self.flag("urgent_window", f"{day}: urgent {rid} on {iso(a.day)}, due by {iso(v.deadline(r))}")
            per[(r.patient, r.dept)] = per.get((r.patient, r.dept), 0) + 1
        for t, n in interp.items():
            if n > v.interp_cap(t, d):
                self.flag("interpreter_capacity", f"{day}: {n} interpreted new-patient visits on {iso(t)}",
                          on=t, n=n)
        for t, n in lab.items():
            if n > v.lab_cap:
                self.flag("lab_capacity", f"{day}: {n} blood tests on {iso(t)}", on=t, n=n)
        if v.hard:
            for (p, dept), n in per.items():
                if n + self.held.get((p, dept), 0) > 1:
                    self.flag("one_per_department", f"{day}: patient {p} has {n + self.held.get((p, dept), 0)} "
                                                    f"{dept} appointments in the period")
        for rid in self.open:
            r = w.req[rid]
            if r.urgency == "U":
                self.flag("urgent_window", f"{day}: urgent {rid} is not booked")
        self._check_priority(d, interp, lab)

    def _check_priority(self, d: int, interp: dict, lab: dict) -> None:
        """A booking breaks the priority order when a higher-priority request of its group still waits at the
        end of the day and could have taken that slot instead (`interp` / `lab`: the day's end-state loads)."""
        w, v = self.w, self.v

        def lab_room(y: Req, x: Req, a: Appt) -> bool:
            """A working day for y's blood test before the slot, had x's own test not taken it."""
            own = a.test if x.test and a.test is not None and a.test >= d + 1 else None
            return any(lab.get(t, 0) - (t == own) < v.lab_cap for t in range(max(d + 1, y.earliest), a.day))
        groups: dict = {}
        for rid in self.open:
            r = w.req[rid]
            if not v.dup(r):
                groups.setdefault((r.dept, r.prev), []).append(r)
        for rid, a in self.appt.items():
            if rid in self.start or rid not in self.start_open:
                continue
            x = w.req[rid]
            if v.dup(x):
                continue
            px = v.prio(x)
            langs = w.doc[a.doctor].langs
            passed = []
            for y in groups.get((x.dept, x.prev), ()):
                if v.prio(y) >= px or y.earliest > a.day:
                    continue
                if v.medium and ((y.new and y.referral < a.day) or (y.test and not lab_room(y, x, a))):
                    continue
                if y.new and y.lang not in langs and not (x.new and x.lang not in langs) and \
                        interp.get(a.day, 0) >= v.interp_cap(a.day, d):
                    continue
                if y.id in self.released_on and a.day < self.released_on[y.id][0] + v.notice:
                    continue
                passed.append(y)
                if self.rec is None:
                    break
            if passed:
                y = passed[0]
                self.flag("waitlist_priority", f"{iso(d)}: {rid} booked on {iso(a.day)} while {y.id} (higher "
                                               f"priority) still waits", x=rid,
                          **(self._passed_over(x, passed, a) if self.rec is not None else {}))

    def _passed_over(self, x: Req, passed: list, a: Appt) -> dict:
        """For the diagnostic: why a program may have passed over each higher-priority request in `passed` when
        it booked x into slot a, as the readings that explain it: an interpreter it needs there ("interp"), a blood
        test ("lab", or easy "test_scope"), a referral run out by then (easy "referral_scope"), a second request
        of the patient for the department (easy/medium "dup_scope"), a release ("released"), a note on x
        ("note"), or another candidate order that puts x first ("order")."""
        v, w = self.v, self.w
        langs = w.doc[a.doctor].langs
        out = []
        for y in passed:
            why = []
            if y.new and y.lang not in langs and not (x.new and x.lang not in langs):
                why.append("interp")
            if y.test:
                why.append("lab" if v.medium else "test_scope")
            if not v.medium and y.new and y.referral is not None and y.referral < a.day:
                why.append("referral_scope")
            if not v.hard and (y.patient, y.dept) in w.repeat_keys:
                why.append("dup_scope")
            if y.id in self.released_on:
                why.append("released")
            if x.notes:
                why.append("note")
            if any(priority(o, y) > priority(o, x) for o in ORDERS if o != v.order):
                why.append("order")
            out.append(why)
        return {"reasons": out}

    # ── the status table ─────────────────────────────────────────────────────
    def table_truth(self, d: int, reserve=None, closed=None, absences: bool = True, count_expired: bool = False,
                    count_requests: bool = False, tomorrow: bool = False) -> dict:
        """The day's true table, or (for the diagnostic) the table a program reports that reads one fact another
        way: `reserve` the reserve's slot starts (() for none held back), `tomorrow` tomorrow's empty reserve slots
        counted as held back too, `closed` the clinics closed on City Day,
        `absences` False for the calendar's sessions of notified absences counted, `count_expired` new patients
        whose referral has run out counted (medium+), `count_requests` requests counted instead of patients (hard)."""
        w, v = self.w, self.v
        reserve = v.reserve if reserve is None else reserve
        closed = {v.closed} if closed is None else closed
        out = {}
        upcoming = {(w.req[rid].patient, w.req[rid].dept) for rid in self.appt}
        for dept in DEPTS:
            free = held = 0
            for doc in w.doctors:
                if doc.dept != dept:
                    continue
                for t in range(d + 1, d + HORIZON + 1):
                    if (t == HOLIDAY and dept in closed) or (absences and v.absent(doc.id, t, d)):
                        continue
                    for h, starts in w.sessions(doc.id, t):
                        for s in starts:
                            if self.occ.get((doc.id, t, s)):
                                continue
                            if h == "AM" and s in reserve and (t >= d + 2 or tomorrow):
                                held += 1
                            else:
                                free += 1
            waiting = [w.req[rid] for rid in self.open if w.req[rid].dept == dept]
            if v.medium and not count_expired:
                waiting = [r for r in waiting if not (r.new and r.referral < d + 1)]
            if v.hard and not count_requests:
                n = len({r.patient for r in waiting if (r.patient, dept) not in self.held
                         and (r.patient, dept) not in upcoming})
            else:
                n = len(waiting)
            out[dept] = {"free_slots": free, "held_back": held, "waitlist": n}
        return out

    def table_readings(self, d: int) -> dict:
        """{reading: the table a program that reads one client fact another way reports today}, for the readings
        the diagnostic tells apart (only those that differ from the truth on some day are worth keeping)."""
        v = self.v
        out = {"no_reserve": self.table_truth(d, reserve=()), "hold_tomorrow": self.table_truth(d, tomorrow=True)}
        for k in RESERVE_SIZES:
            if AM[:k] != v.reserve:
                out[f"reserve_{k}"] = self.table_truth(d, reserve=AM[:k])
        if d + 1 <= HOLIDAY <= d + HORIZON:
            for dept in CLOSABLE:
                if dept != v.closed:
                    out[f"closed_{dept}"] = self.table_truth(d, closed={dept})
            out["calendar"] = self.table_truth(d, closed=set())
        if v.medium:
            out["absences_ignored"] = self.table_truth(d, absences=False)
            out["expired"] = self.table_truth(d, count_expired=True)
        if v.hard:
            out["requests"] = self.table_truth(d, count_requests=True)
        return out

    def _table_right(self, d: int, table) -> int:
        """How many of the day's 15 table entries (5 departments x 3 numbers) are exact (0 without a table)."""
        if not isinstance(table, dict):
            return 0
        ok = 0
        for dept, row in self.table_truth(d).items():
            got = table.get(dept)
            for k, val in row.items():
                x = got.get(k) if isinstance(got, dict) else None
                ok += isinstance(x, (int, float)) and not isinstance(x, bool) and x == val
        return ok

    # ── the end of the period ───────────────────────────────────────────────
    def finish(self) -> dict:
        w, v = self.w, self.v
        for rid in sorted(r for r, a in self.appt.items() if a.day == N_DAYS):
            a = self.appt.pop(rid)
            self._vacate(rid, a)
            self.past[rid] = a
        seen = collisions = 0.0
        slots: dict = {}
        for rid, a in self.past.items():
            if a.day not in SCORED:
                continue
            r = w.req[rid]
            p = 1.0 - no_show(r, a.day - a.booked_on) if v.hard else 1.0
            seen += a.n * p
            if v.hard:
                for s in a.slots():
                    slots.setdefault((a.doctor, a.day, s), []).append((a.booked_on, rid, p))
        pairs = []                       # overbooked slots: (chance the first-booked comes, chance the second comes)
        for ps in slots.values():
            if len(ps) == 2:
                (_, _, p1), (_, _, p2) = sorted(ps)
                collisions += COLLISION_COST * p1 * p2
                pairs.append((round(p1, 6), round(p2, 6)))
        cap = 0
        for doc in w.doctors:
            for t in SCORED:
                if v.closed_on(doc.dept, t) or v.absent(doc.id, t, N_DAYS):
                    continue
                cap += sum(len(st) for _, st in w.sessions(doc.id, t))
        # Waiting and unbooked needs (hard: a patient's requests to one department are one need).
        needs: dict = {}
        for r in w.reqs:
            if r.id in self.closed:
                continue
            key = (r.patient, r.dept) if v.hard else r.id
            needs.setdefault(key, []).append(r)
        wait = 0.0
        unbooked = 0
        for key, rs in needs.items():
            days = [x.day for x in (self.past.get(r.id) or self.appt.get(r.id) for r in rs) if x is not None]
            start = max(min(r.ref for r in rs), 1)
            wt = max(WEIGHT[r.urgency] for r in rs)
            if days:
                wait += WAIT_COST * wt * max(0, min(days) - start)
            elif min(r.earliest for r in rs) <= N_CAL - 1:
                wait += WAIT_COST * wt * max(0, N_DAYS + 1 - start)
                unbooked += 1
        trips = 0
        if v.hard:
            pdays: dict = {}
            for rid, a in list(self.past.items()) + list(self.appt.items()):
                if a.day >= 1:
                    pdays.setdefault(w.req[rid].patient, set()).add(a.day)
            depts: dict = {}
            for rid, a in list(self.past.items()) + list(self.appt.items()):
                if a.day >= 1:
                    depts.setdefault(w.req[rid].patient, set()).add(w.req[rid].dept)
            trips = sum(len(pdays[p]) - 1 for p in pdays if len(depts[p]) > 1)
        # Follow-ups with another doctor than the patient's own: none in a valid run; under the head of the
        # outpatient office's exception each counts for less (the colleague has to read into the case).
        colleague = sum(1 for rid, a in list(self.past.items()) + list(self.appt.items())
                        if a.day >= 1 and w.req[rid].prev and a.doctor != w.req[rid].prev)
        table_cost = TABLE_COST * self.wrong
        value = (SEEN_VALUE * seen - wait - UNBOOKED_COST * unbooked - MOVE_COST * self.moves - collisions
                 - TRIP_COST * trips - COLLEAGUE_COST * colleague - table_cost)
        acc = sum(self.acc) / len(self.acc) if self.acc else 0.0
        viol = [(rule, f"{len(items)} cases, e.g. {items[0]}") for rule, items in self.found.items()]
        m = dict(self.m)
        m.update(ops_value=round(value, 3), seen_slots=round(seen, 3), capacity_slots=cap,
                 utilization=round(seen / cap, 6) if cap else 0.0, waiting_cost=round(wait, 3),
                 unbooked=unbooked, moves=self.moves, collision_cost=round(collisions, 3), extra_trips=trips,
                 overbooked_slots=len(pairs), colleague_follow_ups=colleague, table_accuracy=round(acc, 6),
                 table_entries_wrong=self.wrong, table_cost=round(table_cost, 3))
        out = {"violations": viol, "value": value, "accuracy": acc, "metrics": m}
        if self.trace is not None:
            out["trace"] = {"days": self.trace, "pairs": pairs}
        return out


TABLE_KEYS = ("free_slots", "held_back", "waitlist")


def table_formed(table) -> bool:
    """The status table has a row for every department with its three whole numbers."""
    if not isinstance(table, dict):
        return False
    for dept in DEPTS:
        row = table.get(dept)
        if not isinstance(row, dict):
            return False
        for k in TABLE_KEYS:
            x = row.get(k)
            if isinstance(x, bool) or not isinstance(x, (int, float)) or x != int(x) or x < 0:
                return False
    return True


def replay(view: _View, decide, engine: Engine | None = None, first: int = 0, trace: bool = False) -> dict:
    """Run the hidden period in one setting. `decide(day_input)` returns (output, error) for one call."""
    e = engine or Engine(view, trace)
    for d in range(first, N_DAYS):
        x = e.begin(d)
        out, err = decide(x)
        e.end(d, out, err)
    return e.finish()


def _objective(res: dict, ref_value: float) -> float:
    """The operations value relative to the reference program's. The status table is in the operations value:
    every entry that is not exact costs as much as two empty slots (TABLE_COST), the reference's table is exact."""
    return res["value"] / ref_value


def score(world: World, submission_dir: Path, setting) -> dict:
    view = _View(world, setting)
    ref_value = _reference_run(view)["value"]
    try:
        with program_session(Path(submission_dir), ENTRYPOINT, per_call_timeout=CALL_TIMEOUT,
                             total_timeout=TOTAL_TIMEOUT) as prog:
            res = replay(view, prog.call, trace=True)
    except Fatal as e:
        return {"fatal": str(e)}
    res["metrics"].update(reference_ops_value=round(ref_value, 3),
                          ops_component=round(res["value"] / ref_value, 6))
    # "trace": what the run did each day, for diagnose() (evaluate() never copies it to its result)
    return {"violations": res["violations"], "objective": round(_objective(res, ref_value), 8),
            "metrics": res["metrics"], "trace": res["trace"]}


# ── reference solution ───────────────────────────────────────────────────────

def _noshow_prior(world: World) -> dict:
    """The population's missed share in the visible history and the lead-time slope, as the reference
    estimates them (a least-squares line of missed vs lead over the past appointments)."""
    if "prior" not in world._cache:
        pts = [(a.day - a.booked_on, 1.0 if o == "missed" else 0.0) for _, a, o in world.past_appts
               if o != "cancelled"]
        n = len(pts)
        mx = sum(x for x, _ in pts) / n
        my = sum(y for _, y in pts) / n
        sxx = sum((x - mx) ** 2 for x, _ in pts)
        slope = sum((x - mx) * (y - my) for x, y in pts) / sxx
        world._cache["prior"] = {"base0": round(my - slope * mx, 5), "slope": round(slope, 5), "shrink": 6.0,
                                 "hist_lead": HIST_LEAD}
    return world._cache["prior"]


def ref_config(view: _View, **extra) -> dict:
    s = view.setting
    cfg = {"tier": s.tier, "closed_dept": view.closed, "holiday": iso(HOLIDAY), "urgent_days": view.urgent_days,
           "reserve_slots": len(view.reserve),
           "interpreters_per_day": view.interpreters, "lab_cap": view.lab_cap,
           "overbooked_per_session": view.ob_cap, "move_notice_days": view.notice,
           "waitlist_order": view.order, "horizon": HORIZON, "noshow": _noshow_prior(view._w),
           "seen_value": SEEN_VALUE, "collision_cost": COLLISION_COST, "unbooked_cost": UNBOOKED_COST}
    cfg.update(extra)
    return cfg


def _module():
    name = "fdeb2_hospital_reference_scheduler"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, REFERENCE)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
    return sys.modules[name]


def _rt(x):
    return json.loads(json.dumps(x))


def _decider(sched):
    def decide(x):
        try:
            return _rt(sched.on_day(_rt(x))), None
        except Exception as e:  # noqa: BLE001 - mirrors a failed call
            return None, repr(e)
    return decide


def run_inprocess(view: _View, cfg: dict) -> dict:
    """Replay the reference program with `cfg` in this process (inputs and outputs round-tripped as JSON)."""
    return replay(view, _decider(_module().Scheduler(_rt(cfg))))


def _reference_run(view: _View) -> dict:
    if "reference_run" not in view._cache:
        view._cache["reference_run"] = run_inprocess(view, ref_config(view))
    return view._cache["reference_run"]


def write_program(out_dir: Path, cfg: dict) -> None:
    prog = Path(out_dir) / "program"
    prog.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(REFERENCE, prog / "scheduler.py")
    (prog / "config.json").write_text(json.dumps(cfg, indent=1, sort_keys=True), encoding="utf-8")


def reference_solution(world: World, out_dir: Path, setting) -> None:
    write_program(out_dir, ref_config(_View(world, setting)))


def baseline_solution(world: World, out_dir: Path, setting) -> None:
    """The booking office's practice without an engineer: the same program (earliest feasible slot in the
    priority order, every rule kept, the same status table), but the urgent reserve stays with urgent patients
    and is never released for tomorrow's clinics, and no slot is ever double-booked. The client names the
    released reserve as one of the two places it loses most doctor time today."""
    write_program(out_dir, ref_config(_View(world, setting), hold_reserve=True, no_overbook=True))


# ── programs that break one rule (for the validator) ─────────────────────────

def _snapshots(view: _View) -> dict:
    """day -> (engine after begin(day), the scheduler after its call, the reference's output that day)."""
    if "snapshots" not in view._cache:
        sched = _module().Scheduler(_rt(ref_config(view)))
        e = Engine(view)
        snaps = {}
        for d in range(N_DAYS):
            x = e.begin(d)
            out = _rt(sched.on_day(_rt(x)))
            snaps[d] = (copy.deepcopy(e), copy.deepcopy(sched), out)
            e.end(d, out, None)
        view._cache["snapshots"] = snaps
    return view._cache["snapshots"]


def _try(view: _View, d: int, extra: list) -> set:
    """The rules the reference breaks when `extra` actions are appended to its output on day d."""
    e0, s0, out = _snapshots(view)[d]
    e, sched = copy.deepcopy(e0), copy.deepcopy(s0)
    e.end(d, {"actions": out["actions"] + extra, "status_table": out["status_table"]}, None)
    res = replay(view, _decider(sched), engine=e, first=d + 1) if d + 1 < N_DAYS else e.finish()
    return {r for r, _ in res["violations"]}


class _State:
    """The upcoming book after the reference's actions of day d (for building rule-breaking actions)."""

    def __init__(self, view: _View, d: int):
        e0, _, out = _snapshots(view)[d]
        self.e = copy.deepcopy(e0)
        for act in out["actions"]:
            self.e._apply(d, act, [])
        self.v, self.w, self.d = view, view._w, d

    def free(self, doc: str, t: int, s: int, n: int) -> bool:
        half = self.w.slot_half(doc, t)
        ss = [s + SLOT * k for k in range(n)]
        return all(x in half for x in ss) and len({half[x] for x in ss}) == 1 and \
            not any(self.e.occ.get((doc, t, x)) for x in ss)

    def reserve(self, doc: str, t: int, s: int, n: int) -> bool:
        return any(x in self.v.reserve and self.w.slot_half(doc, t).get(x) == "AM" for x in (s, s + SLOT * (n - 1)))

    def ok_day(self, doc: str, t: int) -> bool:
        return not self.v.closed_on(self.w.doc[doc].dept, t) and not self.v.absent(doc, t, self.d)

    def appts(self, **kw):
        """Upcoming appointments, filtered: new, urgent, test, followup."""
        out = []
        for rid, a in sorted(self.e.appt.items()):
            r = self.w.req[rid]
            if kw.get("new") is not None and r.new != kw["new"]:
                continue
            if not kw.get("urgent") and r.urgency == "U":
                continue
            if kw.get("no_test", True) and r.test and self.v.medium:
                continue
            if kw.get("interp") is False and r.new and r.lang not in self.w.doc[a.doctor].langs:
                continue
            out.append((rid, r, a))
        return out

    def interp_ok(self, r: Req, doc: str, t: int) -> bool:
        if not r.new or r.lang in self.w.doc[doc].langs:
            return True
        n = sum(1 for x, a in self.e.appt.items() if a.day == t and self.w.req[x].new
                and self.w.req[x].lang not in self.w.doc[a.doctor].langs)
        return n + 1 <= self.v.interp_cap(t, self.d)

    def act(self, kind: str, rid: str, doc: str, t: int, s: int, test: int | None = None) -> dict:
        a = {"type": kind, "request_id": rid, "doctor_id": doc, "date": iso(t), "start": hhmm(s)}
        if test is not None:
            a["test_date"] = iso(test)
        return a


def _cands(view: _View, rule: str):
    """Candidate (day, extra actions) that should break `rule` alone, best first."""
    v, w = view, view._w
    days = list(range(N_DAYS - 1, -1, -1))

    def moves(st: _State, rid: str, r: Req, a: Appt, docs, t_lo, t_hi, pred, reserve=False, n=None, check=True):
        for t in range(max(t_lo, st.d + 1), min(t_hi, st.d + HORIZON) + 1):
            for doc in docs:
                if check and not st.ok_day(doc, t):
                    continue
                for h, starts in w.sessions(doc, t):
                    for s in starts:
                        if (doc, t, s) == (a.doctor, a.day, a.start):
                            continue
                        if pred(doc, t, s) and (reserve or not st.reserve(doc, t, s, n or a.n)):
                            yield doc, t, s

    if rule == "well_formed":
        yield N_DAYS - 1, [{"type": "book", "request_id": "Q99999", "doctor_id": "D01",
                            "date": iso(N_DAYS), "start": "09:40"}]
        return
    if rule == "move_notice" and v.notice >= 3:
        # First choice: the hospital releases a follow-up today and the reference books it again tomorrow for the
        # day after, inside the notice period counted from the release (a move at short notice is the fallback).
        for d in range(1, 6):
            st = _State(v, d)
            rel = [rid for rid, r, a in st.appts(new=False) if a.day >= d + 3
                   and any(h == "AM" for h, _ in w.sessions(a.doctor, d + 2))]
            for rid in rel[:2]:
                yield d, [{"type": "release", "request_id": rid}]
    for d in days:
        if rule == "holiday_closure" and not d + 1 <= HOLIDAY <= d + HORIZON:
            continue
        if rule == "doctor_available" and not any(nd <= d and any(d + 1 <= t <= d + HORIZON for t in ds)
                                                  for _, nd, ds, _ in ABSENCES):
            continue
        st = _State(v, d)
        test_of = (lambda r, a: a.test)
        if rule in ("no_double_booking", "slot_capacity"):
            for rid, r, a in st.appts(new=False):
                lo = max(d + v.notice, a.day)
                for doc, t, s in moves(st, rid, r, a, [a.doctor], lo, d + HORIZON,
                                       lambda doc, t, s: (lambda o: o and (not v.hard or any(
                                           w.req[x].new for x in o)))(st.e.occ.get((doc, t, s)))):
                    yield d, [st.act("move", rid, doc, t, s, test_of(r, a))]
                    break
        elif rule == "overbooking_limit":
            for doc in sorted(w.doc):
                for t in range(max(d + v.notice, d + 1), d + HORIZON + 1):
                    if not st.ok_day(doc, t):
                        continue
                    for h, starts in w.sessions(doc, t):
                        singles = [s for s in starts if len(st.e.occ.get((doc, t, s), [])) == 1
                                   and not w.req[st.e.occ[(doc, t, s)][0]].new and not st.reserve(doc, t, s, 1)]
                        movers = [rid for rid, r, a in st.appts(new=False) if a.doctor == doc and a.day >= t]
                        k = v.ob_cap + 1 - sum(1 for s in starts if len(st.e.occ.get((doc, t, s), [])) == 2)
                        targets = [s for s in singles if st.e.occ[(doc, t, s)][0] not in movers[:k]]
                        mv = [x for x in movers if x not in [st.e.occ[(doc, t, s)][0] for s in targets[:k]]][:k]
                        if k > 0 and len(targets) >= k and len(mv) >= k:
                            yield d, [st.act("move", x, doc, t, s, st.e.appt[x].test) for x, s in zip(mv, targets)]
        elif rule == "slot_length":
            for rid, r, a in st.appts(new=False):
                if a.day >= d + v.notice:
                    yield d, [st.act("move", rid, a.doctor, a.day, 12 * 60 + 20, a.test)]
                    break
        elif rule == "department_match":
            for rid, r, a in st.appts(new=True, interp=False):
                others = [x.id for x in w.doctors if x.dept != r.dept and r.lang in x.langs]
                for doc in others:
                    if st.ok_day(doc, a.day) and st.free(doc, a.day, a.start, 2) and \
                            not st.reserve(doc, a.day, a.start, 2):
                        yield d, [st.act("move", rid, doc, a.day, a.start, a.test)]
        elif rule == "holiday_closure":
            for rid, r, a in st.appts(new=False):
                if r.dept != v.closed or r.earliest > HOLIDAY or HOLIDAY < d + v.notice:
                    continue
                for doc, t, s in moves(st, rid, r, a, [a.doctor], HOLIDAY, HOLIDAY,
                                       lambda doc, t, s: st.free(doc, t, s, 1), check=False):
                    yield d, [st.act("move", rid, doc, t, s, a.test)]
                    break
        elif rule == "not_before_earliest":
            for rid, r, a in st.appts(new=False):
                if r.earliest <= d + v.notice:
                    continue
                for doc, t, s in moves(st, rid, r, a, [a.doctor], d + v.notice, r.earliest - 1,
                                       lambda doc, t, s: st.free(doc, t, s, 1)):
                    yield d, [st.act("move", rid, doc, t, s, a.test)]
                    break
        elif rule == "interpreter_capacity":
            # Swap an interpreted new-patient visit on another day with a new-patient visit of the same doctor
            # on day t (both at least the notice period ahead), until day t has one interpreted visit too many.
            def interp_at(r, doc):
                return r.new and r.lang not in w.doc[doc].langs
            news = [(rid, r, a) for rid, r, a in st.appts(new=True) if a.day >= d + v.notice
                    and not st.reserve(a.doctor, a.day, a.start, 2)]
            for t in range(max(d + 1, d + v.notice), d + HORIZON + 1):
                n = sum(1 for x, a in st.e.appt.items() if a.day == t and interp_at(w.req[x], a.doctor))
                need = v.interp_cap(t, d) + 1 - n
                if need <= 0:
                    continue
                acts, used = [], set()
                for ra, xa, aa in news:
                    if len(acts) >= 2 * need:
                        break
                    if aa.day == t or not interp_at(xa, aa.doctor) or ra in used:
                        continue
                    for rb, xb, ab in news:
                        if ab.day != t or ab.doctor != aa.doctor or rb in used or interp_at(xb, ab.doctor):
                            continue
                        if xa.earliest > t or xb.earliest > aa.day or (v.medium and (xa.referral < t
                                                                                     or xb.referral < aa.day)):
                            continue
                        acts += [st.act("move", ra, ab.doctor, t, ab.start), st.act("move", rb, aa.doctor, aa.day,
                                                                                    aa.start)]
                        used |= {ra, rb}
                        break
                if len(acts) == 2 * need:
                    yield d, acts
        elif rule in ("lab_capacity", "test_before_visit") and v.medium:
            # Book the first waiting test-needing request of its group, which the reference left waiting, into a
            # free slot: without a test day (test_before_visit), or with its test on a day the lab is full
            # (lab_capacity). Moving booked test days instead frees lab places that excused the reference's
            # passed-over patients, which breaks waitlist_priority too when the lab is busy.
            yield from _book_test_examples(st, rule)
        if rule == "lab_capacity":
            for t in range(d + 1, d + HORIZON + 1):
                load = sum(1 for a in st.e.appt.values() if a.test == t)
                movers = [(rid, r, a) for rid, r, a in st.appts(no_test=False, urgent=True)
                          if r.test and a.day > t + 0 and a.test != t and r.earliest <= t and a.day - 1 >= t
                          and (a.test is None or a.test >= d + 1)]
                need = v.lab_cap + 1 - load
                if 0 < need <= len(movers):
                    yield d, [st.act("move", rid, a.doctor, a.day, a.start, t) for rid, r, a in movers[:need]]
        if rule == "test_before_visit":
            for rid, r, a in st.appts(no_test=False):
                if r.test and a.day >= d + 1 and sum(1 for b in st.e.appt.values() if b.test == a.day) < v.lab_cap:
                    yield d, [st.act("move", rid, a.doctor, a.day, a.start, a.day)]
        if rule == "referral_validity":
            for rid, r, a in st.appts(new=True, interp=False):
                if r.referral >= d + HORIZON:
                    continue
                for doc, t, s in moves(st, rid, r, a, [a.doctor], max(r.referral + 1, d + v.notice), d + HORIZON,
                                       lambda doc, t, s: st.free(doc, t, s, 2)):
                    yield d, [st.act("move", rid, doc, t, s, a.test)]
                    break
        elif rule == "doctor_available":
            for doc, nd, ds, _ in ABSENCES:
                if nd > d:
                    continue
                for rid, r, a in st.appts(new=False):
                    if a.doctor != doc:
                        continue
                    for doc2, t, s in moves(st, rid, r, a, [doc], max(d + v.notice, r.earliest), d + HORIZON,
                                            lambda doc2, t, s: t in ds and st.free(doc2, t, s, 1), check=False):
                        yield d, [st.act("move", rid, doc2, t, s, a.test)]
                        break
        elif rule == "urgent_window":
            for rid, r, a in st.appts(urgent=True, interp=False):
                if r.urgency != "U":
                    continue
                for doc, t, s in moves(st, rid, r, a, [a.doctor], max(v.deadline(r) + 1, d + v.notice),
                                       d + HORIZON, lambda doc, t, s: st.free(doc, t, s, a.n), reserve=True):
                    if r.new and r.referral < t:
                        continue
                    yield d, [st.act("move", rid, doc, t, s, a.test)]
                    break
        elif rule == "urgent_reserve":
            for rid, r, a in st.appts(new=False):
                for doc, t, s in moves(st, rid, r, a, [a.doctor], max(d + 2, d + v.notice, r.earliest),
                                       d + HORIZON, lambda doc, t, s: st.free(doc, t, s, 1)
                                       and st.reserve(doc, t, s, 1), reserve=True):
                    yield d, [st.act("move", rid, doc, t, s, a.test)]
                    break
        elif rule == "move_notice":
            for rid, r, a in st.appts(new=False):
                for doc, t, s in moves(st, rid, r, a, [a.doctor], max(d + 1, r.earliest), d + v.notice - 1,
                                       lambda doc, t, s: st.free(doc, t, s, 1)):
                    yield d, [st.act("move", rid, doc, t, s, a.test)]
                    break
        elif rule == "follow_up_same_doctor":
            for rid, r, a in st.appts(new=False):
                others = [x.id for x in w.doctors if x.dept == r.dept and x.id != a.doctor]
                for doc, t, s in moves(st, rid, r, a, others, max(d + v.notice, r.earliest), d + HORIZON,
                                       lambda doc, t, s: st.free(doc, t, s, 1)):
                    yield d, [st.act("move", rid, doc, t, s, a.test)]
                    break
                for doc in others:
                    if st.ok_day(doc, a.day) and st.free(doc, a.day, a.start, 1) and \
                            not st.reserve(doc, a.day, a.start, 1):
                        yield d, [st.act("move", rid, doc, a.day, a.start, a.test)]
                        break
        elif rule == "one_per_department" and v.hard:
            # Book a waiting duplicate whose patient already has an appointment in the department: into a free
            # slot, or (follow-ups) next to a single follow-up in a session below the overbooking cap.
            for rid in sorted(st.e.open):
                x = w.req[rid]
                if not v.dup(x) or x.recv > d or (x.patient, x.dept) not in {
                        (w.req[y].patient, w.req[y].dept) for y in list(st.e.appt) + list(st.e.past)}:
                    continue
                docs = [x.prev] if x.prev else [y.id for y in w.doctors if y.dept == x.dept and x.lang in y.langs]
                for t in range(max(d + 1, x.earliest), d + HORIZON + 1):
                    if (x.new and x.referral < t) or (x.test and v.medium):
                        break
                    for doc in docs:
                        if not st.ok_day(doc, t):
                            continue
                        for h, starts in w.sessions(doc, t):
                            nob = sum(1 for s in starts if len(st.e.occ.get((doc, t, s), [])) >= 2)
                            for s in starts:
                                if st.reserve(doc, t, s, 2 if x.new else 1) and t >= d + 2:
                                    continue
                                lst = st.e.occ.get((doc, t, s), [])
                                if st.free(doc, t, s, 2 if x.new else 1) or (
                                        not x.new and len(lst) == 1 and not w.req[lst[0]].new and nob < v.ob_cap):
                                    yield d, [st.act("book", rid, doc, t, s)]
        if rule in ("waitlist_priority", "one_per_department"):
            waiting = sorted((w.req[x] for x in st.e.open if w.req[x].recv <= d and w.req[x].urgency != "U"),
                             key=v.prio)
            for rid, r, a in st.appts(interp=False):
                # free this appointment's slot(s) and book a waiting request there
                for x in reversed(waiting):
                    if (x.dept, x.prev) != (r.dept, r.prev) or x.earliest > a.day or (v.medium and x.test):
                        continue
                    if v.medium and x.new and x.referral < a.day:
                        continue
                    if x.new and x.lang not in w.doc[a.doctor].langs:
                        continue
                    dup = v.dup(x)
                    if (rule == "one_per_department") != dup:
                        continue
                    if rule == "waitlist_priority" and not any(
                            v.prio(y) < v.prio(x) and (y.dept, y.prev) == (x.dept, x.prev) and y.earliest <= a.day
                            and not (v.medium and (y.test or (y.new and y.referral < a.day)))
                            and not (y.new and y.lang not in w.doc[a.doctor].langs) and not v.dup(y)
                            for y in waiting):
                        continue
                    if rule == "one_per_department":
                        orig = w.req[x.dup_of]
                        if orig.id not in st.e.appt:
                            continue
                    yield d, [{"type": "release", "request_id": rid}, st.act("book", x.id, a.doctor, a.day,
                                                                              a.start)]
                    break


def _book_test_examples(st: _State, rule: str):
    """(day, actions) booking a waiting test-needing request that heads its priority group into a free slot of
    its doctor (follow-ups) or of a doctor who speaks its language (new patients), with no test day
    (test_before_visit) or with its test on a working day the lab is already full (lab_capacity)."""
    v, w, d = st.v, st.w, st.d
    groups: dict = {}
    for rid in st.e.open:
        r = w.req[rid]
        if r.recv <= d and not v.dup(r):
            groups.setdefault((r.dept, r.prev), []).append(r)
    upcoming = {(w.req[x].patient, w.req[x].dept) for x in list(st.e.appt) + list(st.e.past)}
    lab: dict = {}
    for a in st.e.appt.values():
        if a.test is not None and a.test >= d + 1:
            lab[a.test] = lab.get(a.test, 0) + 1
    for _, members in sorted(groups.items(), key=lambda g: str(g[0])):
        x = min(members, key=v.prio)
        if not x.test or x.urgency == "U" or (v.hard and (x.patient, x.dept) in upcoming):
            continue
        docs = [x.prev] if x.prev else [y.id for y in w.doctors if y.dept == x.dept and x.lang in y.langs]
        n = 1 if x.prev else 2
        for t in range(max(d + 2, x.earliest), d + HORIZON + 1):
            if x.new and x.referral < t:
                break
            full = [u for u in range(max(d + 1, x.earliest), t) if lab.get(u, 0) >= v.lab_cap]
            if rule == "lab_capacity" and not full:
                continue
            for doc in docs:
                if not st.ok_day(doc, t):
                    continue
                for h, starts in w.sessions(doc, t):
                    for s in starts:
                        if st.free(doc, t, s, n) and not st.reserve(doc, t, s, n):
                            yield d, [st.act("book", x.id, doc, t, s, full[0] if rule == "lab_capacity" else None)]
                            break
                    else:
                        continue
                    break


def violating_examples(world: World, setting) -> dict:
    """One program per rule of the setting that breaks exactly that rule (for the validator): the reference
    with a few actions appended on one day, found by replaying candidates in this process."""
    view = _View(world, setting)
    rules = ["well_formed", "slot_length", "department_match", "holiday_closure", "not_before_earliest",
             "interpreter_capacity", "urgent_window", "urgent_reserve", "move_notice", "waitlist_priority",
             "follow_up_same_doctor"]
    rules.append("slot_capacity" if view.hard else "no_double_booking")
    if view.medium:
        rules += ["lab_capacity", "test_before_visit", "referral_validity", "doctor_available"]
    if view.hard:
        rules += ["overbooking_limit", "one_per_department"]
    assert not _reference_run(view)["violations"], _reference_run(view)["violations"]
    out = {}
    # status_table: the reference's last call reports a table without the Pediatrics row.
    table = {dept: dict(row) for dept, row in _snapshots(view)[N_DAYS - 1][2]["status_table"].items() if dept != "PED"}
    cfg = ref_config(view, inject_table={str(N_DAYS - 1): table})
    broken = {r for r, _ in run_inprocess(view, cfg)["violations"]}
    assert broken == {"status_table"}, broken
    out["status_table"] = (lambda o, cfg=cfg: write_program(o, cfg))
    for rule in rules:
        for k, (d, extra) in enumerate(_cands(view, rule)):
            if k >= 40:
                break
            if _try(view, d, extra) == {rule}:
                cfg = ref_config(view, inject={str(d): extra})
                out[rule] = (lambda o, cfg=cfg: write_program(o, cfg))
                break
        else:
            raise AssertionError(f"no clean example for {rule} ({setting.label})")
    return out


# ── the ground truth audit's hooks (fdebench2.audit) ─────────────────────────

@functools.lru_cache(maxsize=1)
def target_tiers() -> dict:
    """{target id: the tiers it is in force in}, from locales/en/targets.yaml."""
    import yaml
    from fdebench2.cases import TIERS
    path = Path(__file__).resolve().parent / "locales" / "en" / "targets.yaml"
    return {t["id"]: tuple(t.get("tiers", TIERS)) for t in yaml.safe_load(path.read_text(encoding="utf-8"))}


def _in_force(setting) -> list[str]:
    return [t for t, tiers in target_tiers().items() if setting.tier in tiers]


def misreading(target: str, view: _View) -> dict:
    """The reference program's switches for the most natural wrong reading of one client fact, from the agent's
    view alone: the office's practice where the data shows it, the pilot's where the pilot shows it, and every
    field and notice of the data acted on where the tier puts it out of scope (and ignored where it is in)."""
    m, h = view.medium, view.hard
    return {
        "reserve_release": dict(hold_reserve=True),                  # the office never gave the reserve away
        "follow_up_doctor": dict(bend=True),                          # the export has follow-ups seen by colleagues
        "move_notice": dict(move_notice_days=1, pull_forward=True),   # a change is free: pull patients forward
        "status_table": dict(table_no_reserve=True),                  # the pilot's table: held_back 0
        "staff_notes": dict(follow_notes=True, head_note=True),       # the notes followed
        "duplicates": dict(dedupe=not h),                             # a second request read the other way
        "overbooking": dict(no_overbook=True) if h else dict(overbook=True),
        "referral_expiry": dict(referrals=not m),
        "blood_test": dict(tests=not m),
        "doctor_absence": dict(absences=not m),
        "interpreter_absence": dict(interpreter_absence=not m),
        "collision_cost": dict(collision_cost=0.0),                   # no cost stated: a collision costs nothing
    }[target]


def ablations(world: World, setting) -> dict:
    """{target: fn(out_dir)} for every target in force that is not a drawn parameter: the reference program
    misreading only that fact (misreading())."""
    view, out = _View(world, setting), {}
    for t in _in_force(setting):
        if t in PARAM_TARGETS:
            continue
        cfg = ref_config(view, **misreading(t, view))
        out[t] = (lambda o, cfg=cfg: write_program(o, cfg))
    return out


PARAM_TARGETS = {"urgent_reserve": "reserve_slots", "interpreters": "interpreters_per_day",
                 "holiday_clinic": "closed_dept", "waitlist_priority": "waitlist_order", "lab_cap": "lab_cap",
                 "overbooking_cap": "overbooked_per_session"}


def shortcuts(world: World, setting) -> dict:
    """Degenerate strategies the scoring must not reward (each closed: invalid, or quality at most 0.5)."""
    view = _View(world, setting)
    base = ref_config(view)
    lit = literal_config(world)

    def book_nobody(out_dir):
        """Book nobody: no action, an exact status table"""
        write_program(out_dir, dict(base, book_nothing=True))

    def urgent_only(out_dir):
        """Book only the urgent requests, an exact status table"""
        write_program(out_dir, dict(base, urgent_only=True))

    def arrival_order(out_dir):
        """First come, first served: every request in the order received into the earliest free slot of its doctor, no slot held back, the pilot's table"""
        write_program(out_dir, dict(base, waitlist_order="fcfs", pilot_reserve=False, table_no_reserve=True))

    def earliest_slots(out_dir):
        """Fill the earliest free slots: every request with whichever doctor of its department is free first, no slot held back"""
        write_program(out_dir, dict(base, bend=True, pilot_reserve=False))

    def copy_last_weeks(out_dir):
        """Keep doing what the export shows: the reserve held for urgent patients, one patient a slot, the pilot's table"""
        write_program(out_dir, dict(base, hold_reserve=True, no_overbook=True, table_no_reserve=True))

    def no_table(out_dir):
        """The reference's bookings without a status table"""
        write_program(out_dir, dict(base, table_none=True))

    def zero_table(out_dir):
        """The reference's bookings, every table entry 0"""
        write_program(out_dir, dict(base, table_zero=True))

    def morning_table(out_dir):
        """The reference's bookings, the table as the day began (before the day's bookings)"""
        write_program(out_dir, dict(base, table_morning=True))

    def copy_and_release(out_dir):
        """Keep doing what the export shows but give tomorrow's empty reserve slots to the waitlist, the pilot's table"""
        write_program(out_dir, dict(base, no_overbook=True, table_no_reserve=True))

    def pilot_numbers(out_dir):
        """The reference's bookings, the pilot day's table numbers reported every day"""
        write_program(out_dir, dict(base, table_const=world.sample["output"]["status_table"]))
    out = {f.__name__: f for f in (book_nobody, urgent_only, arrival_order, earliest_slots, copy_last_weeks,
                                   no_table, zero_table, morning_table, copy_and_release, pilot_numbers)}
    if view.hard:
        def office_overbooking(out_dir):
            """Keep the office's practice (the reserve held) but overbook the earliest follow-up slots the cap allows, whoever the patients are, an exact table"""
            write_program(out_dir, dict(base, hold_reserve=True, ob_blind=True))
        out["office_overbooking"] = office_overbooking

    # The literal solution's near misses: the literal program with one client rule it breaks kept (the setting's
    # value of that rule), and with all of them kept.
    fixes = {"holiday": {"closed_dept": view.closed, "holiday": iso(HOLIDAY)},
             "order": {"waitlist_order": view.order},
             "interpreters": {"interpreters_per_day": view.interpreters},
             "lab": {"lab_cap": view.lab_cap},
             "reserve": {"reserve_slots": len(view.reserve)},
             "scope": {"tier": view.setting.tier},
             "notice": {"move_notice_days": view.notice}}
    for name, fix in fixes.items():
        def literal_plus(out_dir, fix=fix):
            write_program(out_dir, dict(lit, **fix))
        literal_plus.__doc__ = f"The literal program with {SHORTCUT_FIX[name]} kept"
        out[f"literal_plus_{name}"] = literal_plus

    every = {k: v for fix in fixes.values() for k, v in fix.items()}

    def literal_all_rules(out_dir):
        """The literal program with every client rule kept (all the setting's rule values)"""
        write_program(out_dir, dict(lit, **every))

    def literal_all_rules_release(out_dir):
        """The literal program with every client rule kept and tomorrow's reserve released (the pilot's table)"""
        write_program(out_dir, dict(lit, **every, hold_reserve=False))

    def literal_all_rules_table(out_dir):
        """The literal program with every client rule kept and the client's status table (the reserve held)"""
        write_program(out_dir, dict(lit, **every, table_no_reserve=False))
    out.update(literal_all_rules=literal_all_rules, literal_all_rules_release=literal_all_rules_release,
               literal_all_rules_table=literal_all_rules_table)
    return out


SHORTCUT_FIX = {"holiday": "the City Day closure", "order": "the waitlist order", "interpreters": "the interpreters per day",
                "lab": "the lab cap", "reserve": "the reserve's size", "scope": "the round's scope",
                "notice": "the notice period"}


# ── the per-target diagnostic ────────────────────────────────────────────────

READING_TARGET = {"interp": "interpreters", "lab": "lab_cap", "test_scope": "blood_test",
                  "referral_scope": "referral_expiry", "dup_scope": "duplicates", "released": "move_notice",
                  "note": "staff_notes", "order": "waitlist_priority", "plain": "waitlist_priority"}
TABLE_TARGET = {"no_reserve": "status_table", "hold_tomorrow": "status_table", "reserve_2": "urgent_reserve", "reserve_3": "urgent_reserve",
                "closed_DERM": "holiday_clinic", "closed_ORTH": "holiday_clinic", "closed_PED": "holiday_clinic",
                "calendar": "holiday_clinic", "absences_ignored": "doctor_absence", "expired": "referral_expiry",
                "requests": "duplicates"}
RISKY_PAIR = 0.5                # an overbooked slot whose two patients both come with more than this chance: its
                                # expected collision (30 x 0.5) costs more than the second visit can be worth


def _priority_readings(viol: list) -> dict:
    """{reading: the priority breaches it explains}, each breach given to one reading: of the readings that
    explain every request it passed over (their reasons), the one that explains most breaches overall; a breach
    nothing explains is the order's ("plain")."""
    breaches = [set.intersection(*(set(r) for r in v["reasons"])) if v.get("reasons") else set()
                for v in viol if v["rule"] == "waitlist_priority"]
    count: dict = {}
    for b in breaches:
        for r in b:
            count[r] = count.get(r, 0) + 1
    out: dict = {}
    for b in breaches:
        pick = max(sorted(b), key=lambda r: count[r]) if b else "plain"
        out[pick] = out.get(pick, 0) + 1
    return out


def _same_table(a: dict, b: dict) -> bool:
    return all(a[dept][k] == b[dept][k] for dept in DEPTS for k in TABLE_KEYS)


def _table_readings(days: list) -> dict:
    """{reading: (days the table is the truth, days it is the reading's table)} over the days whose table the
    program reported and where the two differ (a whole table: a program that reads one fact another way reports
    exactly the reading's table, and a partial match is often a coincidence of two wrong counts)."""
    out: dict = {}
    for day in days:
        table, truth = day["table"], day["truth"]
        if table is None:
            continue
        same = _same_table(table, truth)
        for name, alt in day["readings"].items():
            if _same_table(alt, truth):
                continue
            r, x = same, _same_table(table, alt)
            a, b = out.get(name, (0, 0))
            out[name] = (a + r, b + x)
    return out


def _diagnose(view: _View, trace: dict) -> tuple[dict, dict]:
    """diagnose()'s per-target diagnostic: ({target: True | False | None}, {target: evidence}) for every target in
    force, read from the trace of the deliverable's own run (score() records it). True: the run follows the
    client's fact where it and its natural misreading differ; False: it follows the misreading; None: nothing in
    the run tells them apart."""
    w, setting = view._w, view.setting
    days, pairs = trace["days"], trace["pairs"]
    viol = [dict(v, call=day["day"]) for day in days for v in day["viol"]]
    rules: dict = {}
    for v in viol:
        rules[v["rule"]] = rules.get(v["rule"], 0) + 1
    prio = _priority_readings(viol)
    tables = _table_readings(days)
    placed = [dict(p, call=day["day"]) for day in days for p in day["placed"]]
    released = [(day["day"], rid, doc, t) for day in days for rid, doc, t in day["released"]]
    enforced: dict = {}
    evidence: dict = {}

    def table_follows(t: str) -> list:
        return [name for name, (r, x) in tables.items() if TABLE_TARGET.get(name) == t and x > r]

    def put(t: str, ok, text: str) -> None:
        enforced[t], evidence[t] = ok, text

    def by_rules(t: str, names: tuple, readings: tuple = (), table: bool = True, otherwise=True) -> None:
        n = sum(rules.get(r, 0) for r in names)
        k = sum(prio.get(r, 0) for r in readings)
        follows = table_follows(t) if table else []
        bad = [f"{n} breach(es) of {', '.join(names)}"] if n else []
        bad += [f"{k} priority breach(es) explained by {', '.join(readings)}"] if k else []
        bad += [f"the table follows the reading {', '.join(follows)}"] if follows else []
        put(t, False if bad else otherwise, "; ".join(bad) or f"no breach of {', '.join(names) or 'the order'}"
            + (", the table follows the truth" if table and any(TABLE_TARGET.get(x) == t for x in tables) else ""))

    sr_tomorrow = sum(1 for p in placed if p["day"] == p["call"] + 1 and w.req[p["rid"]].urgency != "U"
                      and not p["shared"]
                      and any(s in view.reserve and w.slot_half(p["doc"], p["day"]).get(s) == "AM"
                              for s in (p["start"], p["start"] + SLOT * (2 if w.req[p["rid"]].new else 1) - SLOT)))
    # S/R bookings two or more days ahead in the reserve: in 09:00/09:20, the reserve not kept (its release read too
    # early); after the first two, or in 09:20 while 09:00 is always kept, its size read wrong
    breach = [v for v in viol if v["rule"] == "urgent_reserve"]
    at_first = any(v.get("start") == RESERVE[0] for v in breach)
    early = [v for v in breach if v.get("start") == RESERVE[0] or (at_first and v.get("start") in RESERVE)]
    late = [v for v in breach if v not in early]
    for t in _in_force(setting):
        if t == "urgent_reserve":
            follows = table_follows(t)
            bad = ([f"{len(late)} S/R bookings in reserve slots after 09:00 while 09:00 is kept"] if late else []) + (
                [f"the table follows {', '.join(follows)}"] if follows else [])
            put(t, False if bad else True, "; ".join(bad) or "no S/R booking in the reserve two or more days ahead; "
                                                             "held_back as the reserve's size gives it")
        elif t == "reserve_release":
            bad = ([f"{len(early)} S/R bookings in 09:00/09:20 two or more days ahead"] if early else [])
            if not sr_tomorrow:
                bad.append("no S/R request booked into tomorrow's reserve slots in the whole period")
            put(t, False if bad else True, "; ".join(bad) or f"{sr_tomorrow} S/R bookings into tomorrow's reserve")
        elif t == "follow_up_doctor":
            n = rules.get("follow_up_same_doctor", 0)
            fu = sum(1 for p in placed if w.req[p["rid"]].prev)
            put(t, False if n else (True if fu else None),
                f"{n} follow-up(s) with another doctor" if n else f"{fu} follow-ups placed, all with their doctor")
        elif t == "interpreters":
            over = [v for v in viol if v["rule"] == "interpreter_capacity"
                    and not (view.medium and v.get("on") == INTERP_DAY and v.get("n", 0) <= view.interpreters)]
            k = prio.get("interp", 0)
            bad = ([f"{len(over)} day(s) over the interpreters"] if over else []) + (
                [f"{k} priority breach(es) passing over interpreted patients while interpreters were free"] if k else [])
            put(t, False if bad else True, "; ".join(bad) or "interpreters used up to the number and no further")
        elif t == "holiday_clinic":
            by_rules(t, ("holiday_closure",))
        elif t == "move_notice":
            changes = sum(day["changed"] for day in days) + len(released)
            by_rules(t, ("move_notice",), ("released",), table=False, otherwise=True if changes else None)
        elif t == "waitlist_priority":
            by_rules(t, (), ("order", "plain"), table=False)
        elif t == "status_table":
            by_rules(t, ("status_table",))
        elif t == "staff_notes":
            pm = sum(1 for p in placed if p["doc"] == HEAD_DOCTOR and p["call"] > HEAD_NOTE_DAY
                     and w.slot_half(p["doc"], p["day"]).get(p["start"]) == "PM")
            k = prio.get("note", 0)
            bad = ([f"{k} priority breach(es) booking a noted request ahead of its turn"] if k else []) + (
                [f"nothing booked into {HEAD_DOCTOR}'s afternoons after the head's note"] if not pm else [])
            put(t, False if bad else True, "; ".join(bad) or f"{pm} bookings into {HEAD_DOCTOR}'s afternoons, "
                                                             f"notes not followed")
        elif t == "duplicates":
            if view.hard:
                by_rules(t, ("one_per_department",))
            else:
                by_rules(t, (), ("dup_scope",), table=False)
        elif t == "overbooking":
            doubles = sum(day["double"] for day in days)
            if view.hard:
                put(t, bool(doubles), f"{doubles} overbooked slot-days in the book" if doubles else
                    "no slot ever holds two follow-ups")
            else:
                by_rules(t, ("no_double_booking",), table=False)
        elif t == "referral_expiry":
            if view.medium:
                by_rules(t, ("referral_validity",))
            else:
                by_rules(t, (), ("referral_scope",), table=False)
        elif t == "blood_test":
            if view.medium:
                by_rules(t, ("test_before_visit",), table=False)
            else:
                by_rules(t, (), ("test_scope",), table=False)
        elif t == "doctor_absence":
            if view.medium:
                by_rules(t, ("doctor_available",))
            else:
                moved = sum(1 for d, _, doc0, t0 in released for doc, nd, ds, _ in ABSENCES
                            if doc0 == doc and t0 in ds and d >= nd)
                kept = sum(1 for p in placed for doc, nd, ds, _ in ABSENCES if p["doc"] == doc and p["day"] in ds
                           and p["call"] >= nd)
                bad = ([f"{moved} appointment(s) of a doctor with a notice released"] if moved else []) + (
                    ["no booking with a doctor on the days of their notice"] if not kept else [])
                put(t, False if bad else True, "; ".join(bad) or f"{kept} bookings with the doctors on the days "
                                                                 f"of their notices, as a locum covers them")
        elif t == "interpreter_absence":
            # a run over the interpreters on other days too misreads their number, which explains the day as well
            other = [v for v in viol if v["rule"] == "interpreter_capacity" and v.get("on") != INTERP_DAY]
            over = [v for v in viol if v["rule"] == "interpreter_capacity" and v.get("on") == INTERP_DAY
                    and v.get("n", 0) <= view.interpreters] if not other else []
            put(t, False if over else True, f"{len(over)} call(s) left {iso(INTERP_DAY)} over the reduced number"
                if over else f"{iso(INTERP_DAY)} within the reduced number of interpreters")
        elif t == "lab_cap":
            by_rules(t, ("lab_capacity",), ("lab",), table=False)
        elif t == "overbooking_cap":
            by_rules(t, ("overbooking_limit",), table=False)
        elif t == "collision_cost":
            risky = sum(1 for p1, p2 in pairs if p1 * p2 > RISKY_PAIR)
            if not pairs:
                put(t, None, "no overbooked slot")
            else:
                put(t, risky * 2 <= len(pairs), f"{risky} of {len(pairs)} overbooked slots hold two patients who "
                                                f"both come with more than an even chance")
    return enforced, evidence


def diagnose(world: World, submission_dir: Path, setting, scored: dict) -> dict:
    """The per-target diagnostic (fdebench2: evaluate(..., diagnose=True), for a run's target funnel and the audit):
    read from the trace score() recorded of the deliverable's own run (_diagnose), so the program runs once per
    evaluation. The validator's many evaluations skip it."""
    if "trace" not in scored:
        return {}
    enforced, evidence = _diagnose(_View(world, setting), scored["trace"])
    return {"enforced": enforced, "evidence": evidence}


# ── the never-asks program, the best known program and the bound ─────────────

def robust_config(world: World, tier: str, candidates: dict, **choices) -> dict:
    """robust_solution()'s configuration; `choices` overrides one of its guesses (for the audit's notes)."""
    from fdebench2.cases import Setting
    middle = {k: sorted(v)[(len(v) - 1) // 2] for k, v in candidates.items() if k in ("interpreters_per_day", "lab_cap")}
    params = {"closed_dept": candidates["closed_dept"][0], "reserve_slots": max(candidates["reserve_slots"]),
              "interpreters_per_day": choices.get("interpreters_per_day", 3 if 3 in candidates["interpreters_per_day"]
                                                  else middle["interpreters_per_day"]),
              "waitlist_order": choices.get("waitlist_order", "received"),
              "lab_cap": choices.get("lab_cap", middle["lab_cap"]),
              "overbooked_per_session": min(candidates["overbooked_per_session"])}
    params.update(derive_params(params, tier))
    view = _View(world, Setting(tier, 0, params, variation="never asks"))
    extra = dict(closed_dept=sorted(set(candidates["closed_dept"])), table_closed=[], move_notice_days=5,
                 collision_cost=0.0, table_reserve_slots=min(candidates["reserve_slots"]))
    if choices.get("office_practice"):          # the export's practice and the pilot's table, nothing inferred
        extra.update(hold_reserve=True, table_no_reserve=True)
    extra.update({k: v for k, v in choices.items() if k in ("move_notice_days", "table_reserve_slots")})
    return ref_config(view, **extra)


def robust_solution(world: World, out_dir: Path, tier: str, candidates: dict) -> None:
    """What the agent can build without asking the client anything: the reference program with a strong reading
    of every fixed fact and, for each drawn parameter, a safe candidate of the tier's pool where one exists.

    Fixed facts, read from the agent's view at their strongest: the program runs once a day after the clinics,
    so tomorrow's urgent-reserve slots that today's urgent requests leave empty can serve nobody else and are
    given to the waitlist ("above all we want to stop losing doctor time to empty slots"; the export's office
    never did, and the client confirms it only when asked); held_back counts the reserve slots the program
    still holds two or more days ahead, as many as the export shows (09:00 and 09:20; it holds the largest
    candidate reserve but reports the office's), free_slots every other empty slot of the calendar as listed (the
    absent doctors' days left out); one patient a slot except where the tier allows overbooking, and then no cost
    for a collision (none is stated); follow-ups with their own doctor; notes not followed; a long notice (5
    working days) for the changes the absences force. Generous beyond the agent's view: it is given the tier's
    scope (what is in force this round), which can only help it.

    Drawn parameters: safe where a side is safe (no booking in any clinic that may close on City Day, the
    largest reserve, the smallest overbooking cap). The waitlist order, the interpreters and the lab cap have no
    safe side: the priority rule makes passing over a waiting patient for want of an interpreter or a lab place
    the client does have as invalid as booking one too many, and no booking order keeps every candidate order
    (dropping each booking some candidate order forbids leaves the program at about a quarter of the
    reference's operations value). It takes the pilot's waitlist order, the pilot's three interpreters and the
    middle lab cap. With the export's practice and the pilot's table instead (office_practice), it earns 0
    everywhere."""
    write_program(out_dir, robust_config(world, tier, candidates))


BEST_KNOWN_MOVES = (     # the reference's switches and weights, searched one move at a time
    {"pack": True},
    {"oracle": True},
    {"ob_slot_value": 6.0}, {"ob_slot_value": 10.0}, {"ob_slot_value": 12.0},
    {"ob_booked_value": 5.0}, {"ob_booked_value": 15.0},
)


def _best_known_config(view: _View) -> dict:
    """The reference program tuned on the hidden period itself (hindsight the agent does not have): coordinate
    search over BEST_KNOWN_MOVES from the reference's own configuration (in hard also the patients' true no-show
    rates), keeping a move while the replay stays valid and its objective grows. Deterministic; cached per
    setting."""
    key = "best_known_config"
    if key in view._cache:
        return view._cache[key]
    ref = _reference_run(view)
    best_cfg, best = ref_config(view), _objective(ref, ref["value"])
    moves = [m for m in BEST_KNOWN_MOVES if view.hard or "pack" in m]
    for _ in range(2):
        better = False
        for move in moves:
            cfg = dict(best_cfg, **move)
            if cfg.pop("oracle", None):
                cfg["oracle_p"] = {r.id: r.base_p for r in view._w.reqs}
            if cfg == best_cfg:
                continue
            res = run_inprocess(view, cfg)
            obj = _objective(res, ref["value"])
            if not res["violations"] and obj > best + 1e-9:
                best_cfg, best, better = cfg, obj, True
        if not better:
            break
    view._cache[key] = best_cfg
    return best_cfg


def best_known_solution(world: World, out_dir: Path, setting) -> None:
    write_program(out_dir, _best_known_config(_View(world, setting)))


def _bound_lp(world: World, view: _View) -> dict:
    """objective_bound()'s linear relaxation: {"value": its optimum (an upper bound on the operations value of
    every valid program), "seen", "pairs", "unbooked": what the optimum is made of}."""
    import numpy as np
    from scipy.optimize import linprog
    from scipy.sparse import coo_matrix
    w = world
    cap, sessions = {}, {}
    for doc in w.doctors:
        for t in range(1, N_CAL):
            if view.closed_on(doc.dept, t) or view.absent(doc.id, t, N_DAYS):
                continue
            n = sum(len(st) for _, st in w.sessions(doc.id, t))
            if n:
                cap[(doc.id, t)], sessions[(doc.id, t)] = n, len(w.sessions(doc.id, t))
    cap_index = {k: i for i, k in enumerate(sorted(cap))}
    n_cap = len(cap_index)
    fixed = {rid for rid, a in w.initial_book.items() if a.day == 0}
    groups: dict = {}
    for r in w.reqs:
        groups.setdefault((r.patient, r.dept) if view.hard else r.id, []).append(r)
    # a request (hard: a need) with an appointment on day 0 is settled: seen before the period, no waiting
    groups = {k: rs for k, rs in groups.items() if not any(r.id in fixed for r in rs)}
    docs_of = {dept: [d.id for d in w.doctors if d.dept == dept] for dept in DEPTS}
    a_rows, a_cols, a_vals, gain, kinds = [], [], [], [], []
    const = 0.0
    n_needs = len(groups)
    for i, (k, rs) in enumerate(sorted(groups.items(), key=lambda x: str(x[0]))):
        start = max(min(r.ref for r in rs), 1)
        wt = max(WEIGHT[r.urgency] for r in rs)
        never = (0.0 if any(r.cancel_k for r in rs) else
                 -(UNBOOKED_COST + WAIT_COST * wt * max(0, N_DAYS + 1 - start))
                 if min(r.earliest for r in rs) <= N_CAL - 1 else 0.0)
        const += never
        best = {}
        for r in rs:
            lo, hi = max(r.ref, 1), N_CAL - 1
            if view.medium and r.test:
                lo = max(lo, r.earliest + 1, r.recv + 2)
            if view.medium and r.new:
                hi = min(hi, r.referral)
            if r.urgency == "U":
                hi = min(hi, view.deadline(r))
            booked = w.initial_book.get(r.id)
            p = 1.0 - no_show(r, 1) if view.hard else 1.0
            p_lo = 1.0 - no_show(r, HORIZON) if view.hard else 1.0
            for doc in ([r.prev] if r.prev else docs_of[r.dept]):
                for t in range(lo, hi + 1):
                    if (doc, t) not in cap:
                        continue
                    stay = booked is not None and (booked.doctor, booked.day) == (doc, t)
                    if booked is not None and not stay and t < MOVE_NOTICE and t != booked.day:
                        continue        # a booked appointment moves at the earliest on day 0: to day 3 or later,
                                        # or to another doctor at the same date and time
                    if stay and view.hard:
                        p = 1.0 - no_show(r, booked.day - booked.booked_on)
                    elif view.hard:
                        p = 1.0 - no_show(r, 1)
                    v = (SEEN_VALUE * (1 if r.prev else 2) * p if t in SCORED else 0.0) \
                        - WAIT_COST * wt * max(0, t - start) - (MOVE_COST if booked is not None and not stay else 0)
                    key = (doc, t)
                    if key not in best or v > best[key][0]:
                        best[key] = (v, 1 if r.prev else 2, p, p_lo, r.prev is not None)
        for (doc, t), (v, n, p, p_lo, fu) in best.items():
            j = len(gain)
            gain.append(v - never)
            kinds.append(("x", doc, t, fu, p_lo))
            a_rows += [i, n_needs + cap_index[(doc, t)]]
            a_cols += [j, j]
            a_vals += [1.0, float(n)]
            if view.hard and fu and t in SCORED:
                # u: this follow-up is the first of an overbooked slot (at most when it is booked there)
                gain.append(0.0)
                kinds.append(("u", doc, t, j, p_lo))
                # y: the same patient as the second follow-up of an overbooked slot: its visit (at best at a
                # day's lead) and its waiting stopped there
                gain.append(SEEN_VALUE * p - WAIT_COST * wt * max(0, t - start) - never)
                kinds.append(("y", doc, t, i, p_lo))
                a_rows += [i]
                a_cols += [len(gain) - 1]
                a_vals += [1.0]
    rows = n_needs + n_cap
    b = [1.0] * n_needs + [float(cap[k]) for k in sorted(cap)]
    n_var = len(gain)
    if view.hard:
        # Per doctor-day ci: second follow-ups at most the overbooking cap per session (row A), at most the first
        # follow-ups marked u (row B), each u at most its booking (row U), and the expected collisions C_ci at
        # least 0 and at least 30 x the sum over its pairs of (p1 + p2 - 1) <= p1 p2, with each chance at its
        # lowest in the window (row C): sum 30 (p_lo - 1/2) over the u and the y, less C.
        c0 = len(gain)
        gain += [-1.0] * n_cap
        u_rows = []
        for j, kind in enumerate(kinds):
            if kind[0] not in "uy":
                continue
            ci = cap_index[(kind[1], kind[2])]
            if kind[0] == "y":
                a_rows += [rows + ci, rows + n_cap + ci]
                a_cols += [j, j]
                a_vals += [1.0, 1.0]
            else:
                a_rows += [rows + n_cap + ci]
                a_cols += [j]
                a_vals += [-1.0]
                u_rows.append((j, kind[3]))
            a_rows += [rows + 2 * n_cap + ci]
            a_cols += [j]
            a_vals += [COLLISION_COST * (kind[4] - 0.5)]
        for ci in range(n_cap):
            a_rows += [rows + 2 * n_cap + ci]
            a_cols += [c0 + ci]
            a_vals += [-1.0]
        b += [float(view.ob_cap * sessions[k]) for k in sorted(cap)] + [0.0] * (2 * n_cap)
        rows += 3 * n_cap
        for k, (j, jx) in enumerate(u_rows):
            a_rows += [rows + k, rows + k]
            a_cols += [j, jx]
            a_vals += [1.0, -1.0]
        b += [0.0] * len(u_rows)
        rows += len(u_rows)
    A = coo_matrix((a_vals, (a_rows, a_cols)), shape=(rows, len(gain))).tocsr()
    upper = np.array([1.0] * n_var + [np.inf] * (len(gain) - n_var))
    res = linprog(-np.array(gain), A_ub=A, b_ub=np.array(b), bounds=np.column_stack([np.zeros(len(gain)), upper]),
                  method="highs")
    if res.status != 0:
        raise RuntimeError(f"objective_bound: the LP did not solve ({res.message})")
    x = res.x
    return {"value": float(-res.fun + const),
            "seen": float(sum(x[j] * (1 if True else 0) for j, k in enumerate(kinds) if k[0] == "x" and k[2] in SCORED)),
            "pairs": float(sum(x[j] for j, k in enumerate(kinds) if k[0] == "y")),
            "unbooked": float(n_needs - sum(x[j] for j, k in enumerate(kinds) if k[0] in ("x", "y")))}


def objective_bound(world: World, setting) -> float:
    """A proven upper bound on the objective of every valid program (the follow-up habit kept), over the
    reference's operations value (the status table costs nothing at best): a linear relaxation of the period with
    perfect information (_bound_lp).

    Every request (hard: every patient's need in a department) either gets one appointment on a day t from its
    first possible day on (medium+ with a fasting test one day later and not before the day after it arrives, a new
    patient not after its referral, an urgent one within its window), with its own doctor (follow-ups) or any
    doctor of its department, or gets none. An appointment already in the book stays where it is or moves, for 4,
    to day 3 or later (or to another doctor at the same time). An appointment on a clinic day 1-20 earns 10 per slot (hard: times the patient's best
    chance of coming, at a day's lead or the lead it was booked with), less 0.4 x urgency weight per day waited; one on a later day only stops the
    waiting; none costs 10 and the waiting to 8 December, or nothing for a patient who would cancel (a cancellation
    closes the request). A doctor-day holds at most its calendar slots (none in the closed clinic on City Day or,
    medium+, on a notified absence day). In hard a doctor-day may also hold up to its overbooking cap per session of
    second follow-ups, each next to a first one, worth their visit less the expected collisions, which are at least
    0 and at least 30 x the sum over the pairs of (p1 + p2 - 1) (as p1 p2 >= p1 + p2 - 1), each chance at its lowest
    within ten days' lead. Everything else is relaxed: the order, the reserve, interpreters, the lab, notice beyond the
    book's first three days, slot positions, extra trips, and when requests arrive beyond their first possible day.
    So the LP's optimum is at least any valid program's operations value."""
    view = _View(world, setting)
    key = "objective_bound"
    if key not in view._cache:
        view._cache[key] = _bound_lp(world, view)["value"] / _reference_run(view)["value"]
    return view._cache[key]


# ── the pilot day shown in the data ──────────────────────────────────────────

PILOT_RULES = {"tier": "easy", "closed_dept": "", "holiday": "", "urgent_days": 2, "interpreters_per_day": 3,
               "lab_cap": 10, "overbooked_per_session": 0, "move_notice_days": 1, "waitlist_order": "received",
               "horizon": HORIZON, "noshow": {"base0": 0.15, "slope": 0.01, "shrink": 6.0, "hist_lead": HIST_LEAD},
               "seen_value": SEEN_VALUE, "collision_cost": COLLISION_COST, "unbooked_cost": UNBOOKED_COST,
               "hold_reserve": True, "table_no_reserve": True}


def _pilot(w: World, seed: int) -> dict:
    """One past day (Friday 6 November 2026, the pilot) exactly as the engine sends it, and the answer the
    pilot program gave under its interim rules (format only)."""
    rp = random.Random(seed * 10 + 11)
    d = -1
    reqs = []
    for k in range(6):
        dept = DEPTS[k % 5]
        r = _new_request(w, rp, rp, d, dept, False)
        r.id, r.patient = f"T{k + 1:04d}", f"P{rp.randrange(100000, 999999)}"
        reqs.append(r)
    reqs[3].notes = [{"author_role": "director_office", "request": "book_tomorrow_morning",
                      "text": ACQUAINTANCE[0]}]
    waiting = []
    for k in range(3):
        r = _new_request(w, rp, rp, d - 2, DEPTS[(k + 2) % 5], False)
        r.id, r.patient = f"T{k + 11:04d}", f"P{rp.randrange(100000, 999999)}"
        waiting.append(r)
    booked = []
    for k, (doc, t, s) in enumerate((("D02", 0, 780), ("D08", 0, 600), ("D10", 2, 900))):
        dept = w.doc[doc].dept
        r = Req(f"T{k + 21:04d}", f"P{rp.randrange(100000, 999999)}", dept, doc, "R", "L0", -4, -3, note=1)
        booked.append((r, Appt(doc, t, s, 1, None, -3)))
    gone = Req("T0031", f"P{rp.randrange(100000, 999999)}", "IM", "D01", "S", "L0", -5, -4, note=0)
    pw = World(w.doctors)
    for r in reqs + waiting + [b[0] for b in booked] + [gone]:
        pw.req[r.id] = r
    notices = [
        {"notice_id": "NT-P1", "type": "cancellation", "request_id": gone.id, "patient_id": gone.patient,
         "doctor_id": "D01", "date": iso(0), "start": "09:40", "text": "The patient cancelled this appointment."},
        {"notice_id": "NT-P2", "type": "doctor_absence", "doctor_id": "D05", "from": iso(3), "to": iso(3),
         "reason": "conference", "text": f"Dr D05 is at a conference from {iso(3)} to {iso(3)} and holds no "
                                          f"clinics then."},
        {"notice_id": "NT-P3", "type": "interpreter_absence", "date": iso(1), "in_person_interpreters_change": -1,
         "text": f"One of our in-person interpreters is away on {iso(1)}."},
        {"notice_id": "NT-P4", "type": "staff_note", "author_role": "department_head", "doctor_id": "D07",
         "text": "Please send me the list of next week's new patients by Monday."},
    ]
    day = {"date": iso(d), "day_index": 0, "days_in_period": 1, "period_end": iso(d),
           "booking_window": {"first": iso(d + 1), "last": iso(d + HORIZON)},
           "doctors": doctors_json(w), "sessions": [{"doctor_id": doc.id, "date": iso(t), "session": h,
                                                     "starts": [hhmm(s) for s in starts]}
                                                    for t in range(d + 1, d + HORIZON + 1) for doc in w.doctors
                                                    for h, starts in w.sessions(doc.id, t)],
           "new_requests": [req_json(pw, r) for r in reqs], "notices": notices,
           "attendance": [{"request_id": "T0041", "patient_id": f"P{rp.randrange(100000, 999999)}",
                           "doctor_id": "D04", "start": "13:20", "attended": True},
                          {"request_id": "T0042", "patient_id": f"P{rp.randrange(100000, 999999)}",
                           "doctor_id": "D04", "start": "13:40", "attended": False}],
           "book": [{"request_id": r.id, "doctor_id": a.doctor, "date": iso(a.day), "start": hhmm(a.start),
                     "slots": a.n, "test_date": None, "booked_on": iso(a.booked_on), "request": req_json(pw, r)}
                    for r, a in booked],
           "waitlist": [req_json(pw, r) for r in waiting]}
    answer = _module().Scheduler(_rt(PILOT_RULES)).on_day(_rt(day))
    return {"input": day, "output": answer}


# ── literal solution: the request as written ─────────────────────────────────

def literal_config(world: World) -> dict:
    """The literal program's configuration: the pilot's interim rules (PILOT_RULES) with every notice and request
    field of the data acted on (tier medium's switches)."""
    return dict(PILOT_RULES, tier="medium")


def literal_solution(world: World, out_dir: Path) -> None:
    """The request at face value, from the agent's view only: the reference program on the only rule values the
    view shows, the pilot's (PILOT_RULES, as its answer and the export reveal them: earliest free slot first,
    urgent requests and then everyone by the date received, 09:00 and 09:20 kept for urgent patients as the office
    always did (never given to anyone else, the day before included), the status table as the pilot reports it
    (held_back 0), three interpreters a day, a day's notice to move an appointment, no overbooking), every clinic
    open on City Day as the outpatient office's e-mail says, and every notice and request field acted on
    (absences, the interpreter's absence, referral dates, blood tests within the history's lab figure); notes
    asking for special treatment are not followed. The same program in every setting."""
    write_program(out_dir, literal_config(world))


# ── data rendering ───────────────────────────────────────────────────────────
#
# The agent sees what the hospital would hand over: an export of the booking system as a plain-text SQL dump
# (ASCII table and column names and IDs; department and language names, visit types, statuses and comments in
# the customer locale), the booking office's e-mails (mail/*.eml) and the pilot day as JSON, exactly as the
# engine sends a day. The dataset adds the hidden period (write_hidden) and per-setting answers
# (write_ground_truth).

FILES = {
    "export": {"zh": "预约系统导出.sql", "en": "booking_system_export.sql", "ko": "예약시스템_내보내기.sql",
               "ja": "予約システム_エクスポート.sql", "es": "exportacion_sistema_citas.sql"},
    "sample_in": {"zh": "试点日_输入示例.json", "en": "pilot_day_input.json", "ko": "시범일_입력예시.json",
                  "ja": "試行日_入力例.json", "es": "dia_piloto_entrada.json"},
    "sample_out": {"zh": "试点日_输出示例.json", "en": "pilot_day_output.json", "ko": "시범일_출력예시.json",
                   "ja": "試行日_出力例.json", "es": "dia_piloto_salida.json"},
}
MAIL_DIR = "mail"
EXPORT_DAY = -1                         # the export and the pilot: Friday 6 November 2026, end of the day
CAL_FROM, CAL_TO = -20, HORIZON - 1     # the calendar in the export: 12 October - 20 November
VALUES = {
    "new": {"zh": "初诊", "en": "new patient", "ko": "초진", "ja": "初診", "es": "primera visita"},
    "follow": {"zh": "复诊", "en": "follow-up", "ko": "재진", "ja": "再診", "es": "revisión"},
    "blood": {"zh": "空腹抽血", "en": "fasting blood test", "ko": "공복 채혈", "ja": "空腹時採血",
              "es": "análisis de sangre en ayunas"},
    "attended": {"zh": "已就诊", "en": "attended", "ko": "내원", "ja": "来院", "es": "acudió"},
    "missed": {"zh": "爽约", "en": "missed", "ko": "미내원", "ja": "無断欠席", "es": "no acudió"},
    "cancelled": {"zh": "患者取消", "en": "cancelled by patient", "ko": "환자 취소", "ja": "患者キャンセル",
                  "es": "anulada por el paciente"},
    "booked": {"zh": "已预约", "en": "booked", "ko": "예약됨", "ja": "予約済み", "es": "citada"},
    "patient": {"zh": "患者", "en": "patient", "ko": "환자", "ja": "患者", "es": "paciente"},
    "appointment_given": {"zh": "已约上", "en": "appointment given", "ko": "예약 완료", "ja": "予約確定",
                          "es": "cita asignada"},
    "director_office": {"zh": "院长办公室", "en": "director's office", "ko": "원장실", "ja": "院長室",
                        "es": "dirección"},
    "pilot": {"zh": "试点程序（临时规则）", "en": "pilot program (interim rules)", "ko": "시범 프로그램(임시 규칙)",
              "ja": "試行版プログラム（暫定ルール）", "es": "programa piloto (reglas provisionales)"},
    "IM": {"zh": "内科", "en": "Internal Medicine", "ko": "내과", "ja": "内科", "es": "Medicina Interna"},
    "CARD": {"zh": "心内科", "en": "Cardiology", "ko": "심장내과", "ja": "循環器内科", "es": "Cardiología"},
    "DERM": {"zh": "皮肤科", "en": "Dermatology", "ko": "피부과", "ja": "皮膚科", "es": "Dermatología"},
    "ORTH": {"zh": "骨科", "en": "Orthopedics", "ko": "정형외과", "ja": "整形外科", "es": "Traumatología"},
    "PED": {"zh": "儿科", "en": "Pediatrics", "ko": "소아청소년과", "ja": "小児科", "es": "Pediatría"},
}
LANG_NAMES = {
    "zh": {"L0": "中文", "F1": "英语", "F2": "韩语", "F3": "俄语", "F4": "越南语"},
    "en": {"L0": "English", "F1": "Spanish", "F2": "Chinese", "F3": "Vietnamese", "F4": "Arabic"},
    "ko": {"L0": "한국어", "F1": "영어", "F2": "중국어", "F3": "베트남어", "F4": "러시아어"},
    "ja": {"L0": "日本語", "F1": "英語", "F2": "中国語", "F3": "ベトナム語", "F4": "ポルトガル語"},
    "es": {"L0": "español", "F1": "inglés", "F2": "árabe", "F3": "rumano", "F4": "chino"},
}
NAMES = {
    "zh": ["王建华", "李敏", "张伟", "刘芳", "陈志强", "杨雪", "赵磊", "黄静", "周涛", "吴婷", "徐明", "孙丽", "马超",
           "胡琳"],
    "en": ["Alan Hughes", "Priya Shah", "Martin Cole", "Grace Okafor", "Simon Reid", "Laura Bennett", "Tom Fischer",
           "Hannah Moore", "Owen Price", "Chloe Walsh", "Ben Carter", "Ruth Ellis", "Sam Doyle", "Nina Patel"],
    "ko": ["김민준", "이서연", "박지훈", "최수진", "정우성", "강하은", "조현우", "윤지아", "장도윤", "임소영", "한재민",
           "오유나", "서준호", "신예린"],
    "ja": ["佐藤健一", "鈴木美咲", "高橋翔", "田中由美", "伊藤大輔", "渡辺真理", "山本拓也", "中村彩", "小林誠", "加藤恵",
           "吉田亮", "山田さくら", "松本悠", "井上奈々"],
    "es": ["Javier Morales", "Lucía Fernández", "Andrés Ruiz", "Carmen Navarro", "Pablo Herrera", "Elena Castro",
           "Miguel Ortega", "Sara Domínguez", "Raúl Vega", "Marta Iglesias", "Diego Ramos", "Ana Molina",
           "Jorge Serrano", "Paula Gil"],
}
WEEKDAYS = {
    "zh": ["周一", "周二", "周三", "周四", "周五", "周六", "周日"],
    "en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
    "ko": ["월", "화", "수", "목", "금", "토", "일"],
    "ja": ["月", "火", "水", "木", "金", "土", "日"],
    "es": ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"],
}
MONTHS = {
    "en": ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
           "November", "December"],
    "es": ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
           "noviembre", "diciembre"],
}
TZ = {"zh": 8, "en": 0, "ko": 9, "ja": 9, "es": 1}
TRIAGE_L = {
    "U": {
        "zh": ["症状迅速加重，转诊医生要求尽快复查", "转诊医生标注检查结果异常", "疼痛剧烈，现用药物无法控制"],
        "en": list(TRIAGE["U"]),
        "ko": ["증상이 빠르게 악화되어 의뢰 의사가 신속한 진료를 요청함", "의뢰 의사가 검사 결과 이상을 표시함",
               "현재 약으로 조절되지 않는 심한 통증"],
        "ja": ["症状が急速に悪化しており、紹介元の医師が早めの診察を希望", "紹介元の医師が検査結果の異常を指摘",
               "現在の薬で抑えられない強い痛み"],
        "es": ["los síntomas empeoran rápido; el médico de cabecera pide revisión pronto",
               "resultado de prueba anómalo señalado por el médico que deriva",
               "dolor intenso que no cede con la medicación actual"],
    },
    "S": {
        "zh": ["症状已持续数周", "需要尽快调整用药", "社区医生转诊，不宜久等"],
        "en": list(TRIAGE["S"]),
        "ko": ["몇 주째 증상이 지속됨", "곧 약 조정이 필요함", "동네 의원 의뢰, 오래 기다리면 안 됨"],
        "ja": ["数週間症状が続いている", "近いうちに薬の調整が必要", "かかりつけ医からの紹介、あまり待たせられない"],
        "es": ["síntomas desde hace varias semanas", "hay que ajustar la medicación pronto",
               "derivación del médico de cabecera; no conviene esperar mucho"],
    },
    "R": {
        "zh": ["常规检查", "年度复查", "轻微的老毛病"],
        "en": list(TRIAGE["R"]),
        "ko": ["정기 검진", "연례 점검", "오래된 가벼운 증상"],
        "ja": ["定期チェック", "年1回の経過観察", "以前からの軽い症状"],
        "es": ["control rutinario", "revisión anual", "molestia leve de larga evolución"],
    },
}
ACQUAINTANCE_L = {
    "zh": ["院长的熟人——请安排明天上午。", "院长的私人朋友。无论如何请明天上午约上。", "院长办公室：请把这位患者安排在明天上午。",
           "院长的熟人——如有可能请明天上午，谢谢。"],
    "en": list(ACQUAINTANCE),
    "ko": ["병원장님 지인입니다. 내일 오전으로 예약 부탁드립니다.", "원장님의 개인적인 친구분입니다. 어떻게든 내일 오전으로 부탁드립니다.",
           "원장실입니다. 이 환자분 내일 오전에 넣어 주세요.", "원장님 지인입니다. 가능하면 내일 오전으로 부탁드립니다. 감사합니다."],
    "ja": ["院長の知人です。明日の午前でお願いします。", "院長の個人的なご友人です。何とか明日の午前でお願いします。",
           "院長室より：この患者さんを明日の午前に入れてください。", "院長の知人です。できれば明日の午前でお願いします。"],
    "es": ["Conocido del director del hospital: por favor, cítelo mañana por la mañana.",
           "Un amigo personal de nuestro director. Mañana por la mañana, por favor, como sea.",
           "Dirección: por favor, encaje a este paciente mañana por la mañana.",
           "Conocido del director: mañana por la mañana si es posible, gracias."],
}
HEAD_NOTE_L = {
    "zh": "从现在起请把我下午的门诊留给我自己的病人——不要从候补名单里补约。约谁由我告诉预约处。",
    "en": HEAD_NOTE,
    "ko": "앞으로 제 오후 진료는 제 환자들을 위해 비워 두세요. 대기자 명단에서 채우지 마시고, 누구를 넣을지는 제가 예약실에 "
          "알려 드리겠습니다.",
    "ja": "今後、私の午後の外来は自分の患者のために空けておいてください。待機リストから埋めないでください。誰を入れるかは私から"
          "予約係に伝えます。",
    "es": "A partir de ahora, por favor, dejen libres mis consultas de tarde para mis propios pacientes; no las llenen "
          "desde la lista de espera. Yo diré a la oficina a quién citar.",
}
NOTICE = {   # the outpatient office's instructions: (subject, body) of its two e-mails
    "zh": (("11月23日市民日", "2026年11月23日（周一）为本市市民日，属于地方公共假日。当天门诊照常开放，各科室按平时的出诊安排接诊；"
            "如有调整，以各科室通知为准。预约系统里的出诊表没有因假日作任何修改。"),
           ("预约程序数据里的代码", "预约程序收到的数据里，科室、语言和日期都用代码和 YYYY-MM-DD 表示：科室代码 IM=内科、"
            "CARD=心内科、DERM=皮肤科、ORTH=骨科、PED=儿科；语言代码见系统导出里的 languages 表。")),
    "en": (("City Day, Monday 23 November", "Monday 23 November 2026 is City Day, a municipal public holiday. The "
            "outpatient building is open that day and clinics run on their usual schedule, unless a department "
            "announces otherwise. The session calendar in the booking system was not changed for the holiday."),
           ("Codes in the booking program's data", "In the data the booking program receives, departments, languages "
            "and dates are codes and YYYY-MM-DD: department codes IM = Internal Medicine, CARD = Cardiology, DERM = "
            "Dermatology, ORTH = Orthopedics, PED = Pediatrics; the language codes are in the languages table of the "
            "system export.")),
    "ko": (("11월 23일 시민의 날", "2026년 11월 23일(월)은 시민의 날로 지방 공휴일입니다. 당일 외래는 정상 운영하며 각 진료과는 "
            "평소 일정대로 진료합니다. 변경 사항은 진료과별로 따로 안내합니다. 예약 시스템의 진료 일정표는 공휴일이라고 바꾸지 "
            "않았습니다."),
           ("예약 프로그램 데이터의 코드", "예약 프로그램이 받는 데이터에서 진료과·언어·날짜는 코드와 YYYY-MM-DD로 표시합니다. "
            "진료과 코드는 IM=내과, CARD=심장내과, DERM=피부과, ORTH=정형외과, PED=소아청소년과이고, 언어 코드는 시스템 "
            "내보내기 파일의 languages 테이블에 있습니다.")),
    "ja": (("11月23日 市民の日について", "2026年11月23日（月）は市民の日（市の祝日）です。当日も外来は開いており、各診療科は通常"
            "どおりの担当表で診療します。変更がある場合は各診療科からお知らせします。予約システムの外来枠表は祝日用に変更していません。"),
           ("予約プログラムのデータのコード", "予約プログラムが受け取るデータでは、診療科・言語・日付はコードと YYYY-MM-DD で表します。"
            "診療科コードは IM=内科、CARD=循環器内科、DERM=皮膚科、ORTH=整形外科、PED=小児科、言語コードはシステムの"
            "エクスポートの languages テーブルにあります。")),
    "es": (("Día de la Ciudad, lunes 23 de noviembre", "El lunes 23 de noviembre de 2026 es el Día de la Ciudad, "
            "festivo local. Ese día el edificio de consultas externas abre y las consultas siguen su horario habitual, "
            "salvo que una especialidad avise de lo contrario. El calendario de consultas del sistema de citas no se "
            "modificó por el festivo."),
           ("Códigos en los datos del programa de citas", "En los datos que recibe el programa de citas, "
            "especialidades, idiomas y fechas van como códigos y AAAA-MM-DD: códigos de especialidad IM = Medicina "
            "Interna, CARD = Cardiología, DERM = Dermatología, ORTH = Traumatología, PED = Pediatría; los códigos de "
            "idioma están en la tabla languages de la exportación del sistema.")),
}
SENDERS = {   # (display name, address); {name}/{dept} filled in
    "office": ({"zh": "门诊预约处", "en": "Outpatient booking office", "ko": "외래 예약실", "ja": "外来予約係",
                "es": "Oficina de citas de consultas externas"}, "booking-office@hospital.example"),
    "outpatient": ({"zh": "门诊部办公室", "en": "Outpatient office", "ko": "외래 운영팀", "ja": "外来管理室",
                    "es": "Dirección de consultas externas"}, "outpatient-office@hospital.example"),
    "interpreters": ({"zh": "翻译服务组", "en": "Interpreter service", "ko": "통역 지원팀", "ja": "通訳サービス",
                      "es": "Servicio de intérpretes"}, "interpreters@hospital.example"),
    "director": ({"zh": "院长办公室", "en": "Director's office", "ko": "원장실", "ja": "院長室", "es": "Dirección"},
                 "director-office@hospital.example"),
    "secretariat": ({"zh": "{dept}科室秘书", "en": "{dept} secretariat", "ko": "{dept} 사무실", "ja": "{dept} 医局",
                     "es": "Secretaría de {dept}"}, "{code}-secretariat@hospital.example"),
    "doctor": ({"zh": "{name}", "en": "Dr {name}", "ko": "{name} 과장", "ja": "{name} 医師", "es": "Dr. {name}"},
               "{docl}@hospital.example"),
}
MAIL = {   # kind -> lang -> (subject, body); body greetings and sign-offs included
    "conference": {
        "zh": ("{frm_s}至{to_s}外出开会，停诊", "预约处：\n\n我{frm}至{to}外出参加学术会议，这几天不出诊。\n\n{name}（{doc}），{dept}"),
        "en": ("Conference {frm_s} - {to_s}: no clinics", "Dear booking office,\n\nI will be at a conference from {frm} "
               "to {to} and hold no clinics on those days.\n\nBest regards,\n{name} ({doc}), {dept}"),
        "ko": ("{frm_s}~{to_s} 학회 참석으로 휴진", "예약실 담당자님께\n\n{frm}부터 {to}까지 학회 참석으로 그 기간에는 진료가 "
               "없습니다.\n\n{name}({doc}), {dept}"),
        "ja": ("{frm_s}〜{to_s} 学会出張のため休診", "予約係 御中\n\n{frm}から{to}まで学会に出席するため、その間の外来は"
               "休診です。\n\n{dept} {name}（{doc}）"),
        "es": ("Congreso del {frm_s} al {to_s}: sin consultas", "Estimada oficina de citas:\n\nEstaré en un congreso "
               "del {frm} al {to} y no pasaré consulta esos días.\n\nUn saludo,\n{name} ({doc}), {dept}"),
    },
    "illness": {
        "zh": ("{name}医生（{doc}）病假 {frm_s}至{to_s}", "预约处：\n\n{dept}{name}医生（{doc}）因病请假，{frm}至{to}"
               "不出诊。\n\n{dept}科室秘书"),
        "en": ("Dr {name} ({doc}) off sick {frm_s} - {to_s}", "Dear booking office,\n\nDr {name} ({doc}, {dept}) is off "
               "sick from {frm} to {to} and holds no clinics then.\n\nKind regards,\n{dept} secretariat"),
        "ko": ("{name} 과장({doc}) 병가 {frm_s}~{to_s}", "예약실 담당자님께\n\n{dept} {name} 과장({doc})이 병가로 {frm}부터 "
               "{to}까지 진료하지 않습니다.\n\n{dept} 사무실"),
        "ja": ("{name}医師（{doc}）病欠 {frm_s}〜{to_s}", "予約係 御中\n\n{dept}の{name}医師（{doc}）が病気のため、{frm}から"
               "{to}まで外来を休みます。\n\n{dept} 医局"),
        "es": ("Dr. {name} ({doc}) de baja del {frm_s} al {to_s}", "Estimada oficina de citas:\n\nEl Dr. {name} ({doc}, "
               "{dept}) está de baja por enfermedad del {frm} al {to} y no pasa consulta esos días.\n\nUn saludo,\n"
               "Secretaría de {dept}"),
    },
    "interpreter": {
        "zh": ("{day_s}有一位现场翻译不在", "各位好：\n\n{day}我们有一位现场翻译请假，当天现场翻译少一人。\n\n翻译服务组"),
        "en": ("Interpreter away on {day_s}", "Hello,\n\nOne of our in-person interpreters is away on {day}; we have one "
               "in-person interpreter fewer that day.\n\nInterpreter service"),
        "ko": ("{day_s} 대면 통역사 1명 부재", "안녕하세요.\n\n{day}에 대면 통역사 한 명이 자리를 비웁니다. 그날은 대면 통역사가 "
               "한 명 적습니다.\n\n통역 지원팀"),
        "ja": ("{day_s} 対面通訳1名不在", "お疲れさまです。\n\n{day}は対面通訳が1名休みのため、当日の対面通訳は1名少なくなります。"
               "\n\n通訳サービス"),
        "es": ("Una intérprete ausente el {day_s}", "Hola:\n\nUna de nuestras intérpretes presenciales falta el {day}; ese "
               "día tenemos una intérprete presencial menos.\n\nServicio de intérpretes"),
    },
    "head_list": {
        "zh": ("下周初诊名单", "预约处：\n\n请在周一前把下周的初诊患者名单发给我。\n\n谢谢，\n{dept}主任 {name}（{doc}）"),
        "en": ("Next week's new patients", "Hello,\n\nPlease send me the list of next week's new patients by Monday.\n\n"
               "Thanks,\n{name} ({doc}), head of {dept}"),
        "ko": ("다음 주 초진 환자 명단", "안녕하세요.\n\n다음 주 초진 환자 명단을 월요일까지 보내 주세요.\n\n{dept} 과장 {name}({doc})"),
        "ja": ("来週の初診患者リスト", "お疲れさまです。\n\n来週の初診患者のリストを月曜までに送ってください。\n\n{dept} 部長 {name}（{doc}）"),
        "es": ("Primeras visitas de la semana que viene", "Hola:\n\nPor favor, envíenme antes del lunes la lista de "
               "primeras visitas de la semana que viene.\n\nGracias,\n{name} ({doc}), jefe de {dept}"),
    },
    "head_keepfree": {
        "zh": ("我下午的门诊", "预约处：\n\n{note}\n\n{dept}主任 {name}（{doc}）"),
        "en": ("My afternoon clinics", "Hello,\n\n{note}\n\n{name} ({doc}), head of {dept}"),
        "ko": ("제 오후 진료 건", "안녕하세요.\n\n{note}\n\n{dept} 과장 {name}({doc})"),
        "ja": ("私の午後の外来について", "お疲れさまです。\n\n{note}\n\n{dept} 部長 {name}（{doc}）"),
        "es": ("Mis consultas de tarde", "Hola:\n\n{note}\n\n{name} ({doc}), jefe de {dept}"),
    },
    "acquaintance": {
        "zh": ("申请 {rid}（患者 {pid}）", "预约处：\n\n申请 {rid}（患者 {pid}，{dept}，{visit}）：{note}\n\n院长办公室"),
        "en": ("Request {rid} (patient {pid})", "Dear booking office,\n\nRequest {rid} (patient {pid}, {dept}, {visit}): "
               "{note}\n\nDirector's office"),
        "ko": ("요청 {rid}(환자 {pid})", "예약실 담당자님께\n\n요청 {rid}(환자 {pid}, {dept}, {visit}): {note}\n\n원장실"),
        "ja": ("依頼 {rid}（患者 {pid}）", "予約係 御中\n\n依頼 {rid}（患者 {pid}、{dept}、{visit}）：{note}\n\n院長室"),
        "es": ("Solicitud {rid} (paciente {pid})", "Estimada oficina de citas:\n\nSolicitud {rid} (paciente {pid}, {dept}, "
               "{visit}): {note}\n\nDirección"),
    },
    "instructions": {
        "zh": ("{subject}", "预约处各位：\n\n{body}\n\n门诊部办公室"),
        "en": ("{subject}", "To the booking office,\n\n{body}\n\nOutpatient office"),
        "ko": ("{subject}", "예약실 여러분께\n\n{body}\n\n외래 운영팀"),
        "ja": ("{subject}", "予約係各位\n\n{body}\n\n外来管理室"),
        "es": ("{subject}", "A la oficina de citas:\n\n{body}\n\nDirección de consultas externas"),
    },
}
SQL_DOC = {   # the export's header comment: title, how to load, one line per table
    "zh": ("门诊预约系统导出（截至 2026-11-06 下班）。导入：sqlite3 booking.db < 本文件。日期为 YYYY-MM-DD，时间为 HH:MM。",
           {"departments": "科室代码与名称", "languages": "语言代码与名称",
            "doctors": "医生", "doctor_languages": "医生会说的语言",
            "weekly_sessions": "每周出诊安排（weekday 1=周一；session AM 上午 / PM 下午；每个号源20分钟）",
            "clinic_sessions": "出诊表 2026-10-12 至 2026-11-20（未因假日修改）",
            "requests": "预约申请（10月12日以来就诊的申请，以及11月6日前受理、尚在候补或已约到之后日期的申请）",
            "request_notes": "工作人员对申请的备注", "appointments": "预约：已就诊、爽约、患者取消，以及11月9日起已预约的",
            "cancellations": "患者取消的预约", "attendance": "到诊记录（attended 1=来了，0=没来）",
            "waitlist_history": "候补名单进出记录（removed_on 为空：仍在候补）",
            "status_reports": "各科室状况表（试点日由试点程序生成）"}),
    "en": ("Outpatient booking system export (as of 2026-11-06, end of day). Load: sqlite3 booking.db < this file. "
           "Dates are YYYY-MM-DD, times HH:MM.",
           {"departments": "department codes and names", "languages": "language codes and names",
            "doctors": "doctors", "doctor_languages": "the languages each doctor speaks",
            "weekly_sessions": "weekly clinic sessions (weekday 1 = Monday; session AM / PM; 20-minute slots)",
            "clinic_sessions": "the session calendar 2026-10-12 to 2026-11-20 (not changed for holidays)",
            "requests": "appointment requests (those seen since 12 October, and those received before 6 November "
                        "that are waiting or booked for a later date)",
            "request_notes": "staff notes on requests",
            "appointments": "appointments: attended, missed, cancelled by the patient, and booked from 9 November on",
            "cancellations": "appointments the patient cancelled", "attendance": "attendance (attended 1 = came, 0 = "
                                                                                 "did not come)",
            "waitlist_history": "entries and exits of the waitlist (removed_on empty: still waiting)",
            "status_reports": "the department status table (the pilot day's, from the pilot program)"}),
    "ko": ("외래 예약 시스템 내보내기(2026-11-06 업무 종료 기준). 불러오기: sqlite3 booking.db < 이 파일. 날짜는 YYYY-MM-DD, "
           "시각은 HH:MM.",
           {"departments": "진료과 코드와 이름", "languages": "언어 코드와 이름", "doctors": "의사",
            "doctor_languages": "의사별 구사 언어",
            "weekly_sessions": "주간 진료 일정(weekday 1=월요일, session AM 오전 / PM 오후, 슬롯 20분)",
            "clinic_sessions": "진료 일정표 2026-10-12 ~ 2026-11-20(공휴일 반영 안 됨)",
            "requests": "예약 요청(10월 12일 이후 진료받은 요청과, 11월 6일 전에 접수되어 대기 중이거나 이후 날짜로 예약된 요청)",
            "request_notes": "요청에 대한 직원 메모",
            "appointments": "예약: 내원, 미내원, 환자 취소, 그리고 11월 9일 이후로 잡힌 예약",
            "cancellations": "환자가 취소한 예약", "attendance": "내원 기록(attended 1=내원, 0=미내원)",
            "waitlist_history": "대기자 명단 등록·해제 이력(removed_on이 비어 있으면 아직 대기 중)",
            "status_reports": "진료과별 현황표(시범일의 것, 시범 프로그램이 작성)"}),
    "ja": ("外来予約システムのエクスポート（2026-11-06 業務終了時点）。読み込み: sqlite3 booking.db < このファイル。日付は "
           "YYYY-MM-DD、時刻は HH:MM。",
           {"departments": "診療科コードと名称", "languages": "言語コードと名称", "doctors": "医師",
            "doctor_languages": "医師ごとの対応言語",
            "weekly_sessions": "週間の外来担当（weekday 1=月曜、session AM 午前 / PM 午後、1枠20分）",
            "clinic_sessions": "外来枠表 2026-10-12〜2026-11-20（祝日の反映なし）",
            "requests": "予約依頼（10月12日以降に受診した依頼と、11月6日までに受け付けて待機中または以降の日付で予約済みの依頼）",
            "request_notes": "依頼への職員メモ",
            "appointments": "予約：来院、無断欠席、患者キャンセル、および11月9日以降の予約済み",
            "cancellations": "患者がキャンセルした予約", "attendance": "来院記録（attended 1=来院、0=来院せず）",
            "waitlist_history": "待機リストの登録・解除の履歴（removed_on が空なら待機中）",
            "status_reports": "診療科別の状況表（試行日のもの、試行版プログラムが作成）"}),
    "es": ("Exportación del sistema de citas de consultas externas (a 2026-11-06, fin de la jornada). Carga: "
           "sqlite3 booking.db < este fichero. Fechas AAAA-MM-DD, horas HH:MM.",
           {"departments": "códigos y nombres de especialidad", "languages": "códigos y nombres de idioma",
            "doctors": "médicos", "doctor_languages": "los idiomas que habla cada médico",
            "weekly_sessions": "consultas semanales (weekday 1 = lunes; session AM mañana / PM tarde; huecos de 20 "
                               "minutos)",
            "clinic_sessions": "el calendario de consultas del 2026-10-12 al 2026-11-20 (sin cambios por festivos)",
            "requests": "solicitudes de cita (las atendidas desde el 12 de octubre y las recibidas antes del 6 de "
                        "noviembre que esperan o están citadas para una fecha posterior)",
            "request_notes": "notas del personal sobre las solicitudes",
            "appointments": "citas: acudió, no acudió, anulada por el paciente, y citadas a partir del 9 de noviembre",
            "cancellations": "citas anuladas por el paciente", "attendance": "asistencia (attended 1 = acudió, 0 = no "
                                                                             "acudió)",
            "waitlist_history": "entradas y salidas de la lista de espera (removed_on vacío: sigue esperando)",
            "status_reports": "la tabla de estado por especialidad (la del día piloto, del programa piloto)"}),
}


def _cal(date: dt.date, lang: str, long: bool = True) -> str:
    """A date as a person writes it in an e-mail."""
    wd = WEEKDAYS[lang][date.weekday()]
    if lang == "en":
        return f"{wd} {date.day} {MONTHS['en'][date.month - 1]}" if long else f"{date.day} {MONTHS['en'][date.month - 1][:3]}"
    if lang == "es":
        return f"{wd} {date.day} de {MONTHS['es'][date.month - 1]}" if long else f"{date.day} de {MONTHS['es'][date.month - 1]}"
    if lang == "ko":
        return f"{date.month}월 {date.day}일({wd})" if long else f"{date.month}/{date.day}"
    return f"{date.month}月{date.day}日（{wd}）" if long else f"{date.month}月{date.day}日"


def _sender(key: str, lang: str, **kw) -> str:
    name, addr = SENDERS[key]
    from email.headerregistry import Address
    return str(Address(name[lang].format(**kw), addr_spec=addr.format(**kw)))


def _mail(path: Path, lang: str, when: dt.datetime, sender: str, kind: str, cc: str = "", **kw) -> None:
    import email.utils
    subject, body = MAIL[kind][lang]
    stamp = when.replace(tzinfo=dt.timezone(dt.timedelta(hours=TZ[lang])))
    write_eml(path, sender=sender, to=_sender("office", lang), cc=cc, date=email.utils.format_datetime(stamp),
              subject=subject.format(**kw), body=body.format(**kw),
              message_id=f"<{path.stem}.{lang}@hospital.example>")


def _at(date: dt.date, *parts) -> dt.datetime:
    """A deterministic office-hours time on that date."""
    minute = int(_uniform("mail", date.isoformat(), *parts) * 7 * 60)
    return dt.datetime(date.year, date.month, date.day, 9 + minute // 60, minute % 60)


def _doctor_kw(w: World, doc: str, lang: str) -> dict:
    i = [d.id for d in w.doctors].index(doc)
    code = w.doc[doc].dept
    return {"doc": doc, "docl": doc.lower(), "name": NAMES[lang][i], "dept": VALUES[code][lang], "code": code.lower()}


def _absence_mail(w: World, out: Path, lang: str, sent: dt.date, doc: str, frm: dt.date, to: dt.date,
                  why: str) -> None:
    kw = _doctor_kw(w, doc, lang)
    kw.update(frm=_cal(frm, lang), to=_cal(to, lang), frm_s=_cal(frm, lang, False), to_s=_cal(to, lang, False))
    who = _sender("doctor", lang, **kw) if why == "conference" else _sender("secretariat", lang, **kw)
    _mail(out / f"{sent.isoformat()}_{why}_{doc}.eml", lang, _at(sent, doc), who, why, **kw)


def _interpreter_mail(out: Path, lang: str, sent: dt.date, day: dt.date) -> None:
    _mail(out / f"{sent.isoformat()}_interpreter_absence.eml", lang, _at(sent, "interp"),
          _sender("interpreters", lang), "interpreter", day=_cal(day, lang), day_s=_cal(day, lang, False))


def _acquaintance_mail(w: World, out: Path, lang: str, sent: dt.date, r: Req, rid: str, k: int) -> None:
    v = labels(VALUES, lang)
    _mail(out / f"{sent.isoformat()}_director_office_{rid}.eml", lang, _at(sent, rid), _sender("director", lang),
          "acquaintance", rid=rid, pid=r.patient, dept=v[r.dept], visit=v["new" if r.new else "follow"],
          note=ACQUAINTANCE_L[lang][k])


# The e-mails of the history (all before the pilot day; the absences fall before the four weeks of the export).
HIST_ABSENCES = (("D09", dt.date(2026, 9, 28), dt.date(2026, 10, 5), dt.date(2026, 10, 9), "conference"),
                 ("D02", dt.date(2026, 10, 6), dt.date(2026, 10, 7), dt.date(2026, 10, 9), "illness"))
HIST_INTERP = (dt.date(2026, 10, 2), dt.date(2026, 10, 8))
HIST_HEAD = ("D07", dt.date(2026, 10, 21))
HIST_INSTRUCTIONS = (dt.date(2026, 11, 2), dt.date(2026, 11, 4))


def _history_requests(w: World) -> tuple[list, dict]:
    """The requests of the export in order, and their ids (history requests get H ids)."""
    if "hist_ids" not in w._cache:
        reqs = sorted([r for r, _, _ in w.past_appts] + w.past_reqs, key=lambda r: (r.recv, r.patient))
        ids = {id(r): r.id or f"H{k:05d}" for k, r in enumerate(reqs, start=1)}
        w._cache["hist_ids"] = (reqs, ids)
    return w._cache["hist_ids"]


def _history_acquaintance(w: World):
    """The history's director's-acquaintance request: a routine new Orthopedics patient received 28 October."""
    reqs, ids = _history_requests(w)
    appt = {id(r): a for r, a, _ in w.past_appts}
    for recv in (-7, -8, -6, -9, -5):           # received about a week and a half before the export
        for r in reqs:
            a = appt.get(id(r))
            if a and r.new and r.dept == "ORTH" and r.urgency == "R" and r.recv == recv and a.day > r.recv + 1:
                return r, ids[id(r)]
    raise AssertionError("no history request for the acquaintance e-mail")


def _history_cancelled_on(r_id: str, a: Appt) -> int:
    k = 1 + int(_uniform("cx", r_id) * 4)
    return max(a.booked_on, a.day - k)


def write_data(world: World, data_dir: Path, lang: str) -> None:
    w, v, ln = world, labels(VALUES, lang), LANG_NAMES[lang]
    reqs, ids = _history_requests(w)
    acq, acq_id = _history_acquaintance(w)
    t_lo, t_hi = CAL_FROM, CAL_TO
    weekly = [(d.id, wd + 1, WEEKDAYS[lang][wd], h, hhmm((AM if h == "AM" else PM)[0]),
               hhmm((AM if h == "AM" else PM)[-1] + SLOT), SLOT) for d in w.doctors for wd, h in sorted(d.sessions)]
    calendar = [(doc.id, iso(t), h, hhmm(starts[0]), hhmm(starts[-1] + SLOT), SLOT)
                for t in range(t_lo, t_hi + 1) for doc in w.doctors for h, starts in w.sessions(doc.id, t)]
    requests = [(ids[id(r)], r.patient, iso(r.recv), r.dept, v["new" if r.new else "follow"], r.prev, r.urgency,
                 TRIAGE_L[r.urgency][lang][r.note], r.lang, iso(r.earliest),
                 iso(r.referral) if r.referral is not None else None, v["blood"] if r.test else None) for r in reqs]
    appts, cancels, attend, wait = [], [], [], []
    for r, a, o in w.past_appts:
        rid = ids[id(r)]
        appts.append((rid, r.patient, a.doctor, iso(a.day), hhmm(a.start), a.n,
                      iso(a.test) if a.test is not None else None, iso(a.booked_on), v[o]))
        if o == "cancelled":
            cancels.append((rid, r.patient, a.doctor, iso(a.day), hhmm(a.start), iso(_history_cancelled_on(rid, a)),
                            v["patient"]))
        else:
            attend.append((iso(a.day), rid, r.patient, a.doctor, hhmm(a.start), 1 if o == "attended" else 0))
    for rid, a in w.initial_book.items():
        r = w.req[rid]
        appts.append((rid, r.patient, a.doctor, iso(a.day), hhmm(a.start), a.n,
                      iso(a.test) if a.test is not None else None, iso(a.booked_on), v["booked"]))
    booked_on = {ids[id(r)]: a.booked_on for r, a, _ in w.past_appts}
    booked_on.update({rid: a.booked_on for rid, a in w.initial_book.items()})
    for r in reqs:
        rid = ids[id(r)]
        b = booked_on.get(rid)
        wait.append((rid, r.dept, iso(r.recv), iso(b) if b is not None else None,
                     v["appointment_given"] if b is not None else None))
    appts.sort(key=lambda x: (x[3], x[2], x[4], x[0]))
    cancels.sort(key=lambda x: (x[5], x[0]))
    attend.sort(key=lambda x: (x[0], x[3], x[4]))
    wait.sort(key=lambda x: (x[2], x[0]))
    pilot = w.sample["output"]["status_table"]
    title, docs = SQL_DOC[lang]
    T, I = "TEXT", "INTEGER"
    tables = {
        "departments": ([("department_code", "TEXT PRIMARY KEY"), ("name", T)], [(c, v[c]) for c in DEPTS]),
        "languages": ([("language_code", "TEXT PRIMARY KEY"), ("name", T)], [(c, ln[c]) for c in LANGS]),
        "doctors": ([("doctor_id", "TEXT PRIMARY KEY"), ("name", T), ("department_code", T)],
                    [(d.id, NAMES[lang][i], d.dept) for i, d in enumerate(w.doctors)]),
        "doctor_languages": ([("doctor_id", T), ("language_code", T)],
                             [(d.id, x) for d in w.doctors for x in d.langs]),
        "weekly_sessions": ([("doctor_id", T), ("weekday", I), ("weekday_name", T), ("session", T),
                             ("start_time", T), ("end_time", T), ("slot_minutes", I)], weekly),
        "clinic_sessions": ([("doctor_id", T), ("date", T), ("session", T), ("start_time", T), ("end_time", T),
                             ("slot_minutes", I)], calendar),
        "requests": ([("request_id", "TEXT PRIMARY KEY"), ("patient_id", T), ("received", T), ("department_code", T),
                      ("visit_type", T), ("previous_doctor", T), ("urgency", T), ("triage_note", T),
                      ("preferred_language", T), ("earliest_date", T), ("referral_valid_until", T),
                      ("pre_visit_test", T)], requests),
        "request_notes": ([("request_id", T), ("author_role", T), ("text", T)],
                          [(acq_id, v["director_office"], ACQUAINTANCE_L[lang][0])]),
        "appointments": ([("request_id", T), ("patient_id", T), ("doctor_id", T), ("date", T), ("start", T),
                          ("slots", I), ("test_date", T), ("booked_on", T), ("status", T)], appts),
        "cancellations": ([("request_id", T), ("patient_id", T), ("doctor_id", T), ("date", T), ("start", T),
                           ("cancelled_on", T), ("cancelled_by", T)], cancels),
        "attendance": ([("date", T), ("request_id", T), ("patient_id", T), ("doctor_id", T), ("start", T),
                        ("attended", I)], attend),
        "waitlist_history": ([("request_id", T), ("department_code", T), ("added_on", T), ("removed_on", T),
                              ("removal_reason", T)], wait),
        "status_reports": ([("report_date", T), ("department_code", T), ("free_slots", I), ("held_back", I),
                            ("waitlist", I), ("produced_by", T)],
                           [(iso(EXPORT_DAY), c, pilot[c]["free_slots"], pilot[c]["held_back"], pilot[c]["waitlist"],
                             v["pilot"]) for c in DEPTS if c in pilot]),
    }
    comment = "\n".join([title, ""] + [f"{name}: {docs[name]}" for name in tables])
    write_sql(data_dir / FILES["export"][lang], tables, comment=comment)

    mail = data_dir / MAIL_DIR
    mail.mkdir(parents=True, exist_ok=True)
    for doc, sent, frm, to, why in HIST_ABSENCES:
        _absence_mail(w, mail, lang, sent, doc, frm, to, why)
    _interpreter_mail(mail, lang, *HIST_INTERP)
    doc, sent = HIST_HEAD
    kw = _doctor_kw(w, doc, lang)
    _mail(mail / f"{sent.isoformat()}_department_head_{doc}.eml", lang, _at(sent, doc), _sender("doctor", lang, **kw),
          "head_list", **kw)
    _acquaintance_mail(w, mail, lang, day_date(acq.recv), acq, acq_id, 0)
    for (subject, body), sent, slug in zip(NOTICE[lang], HIST_INSTRUCTIONS, ("city_day", "data_codes")):
        _mail(mail / f"{sent.isoformat()}_outpatient_office_{slug}.eml", lang, _at(sent, slug),
              _sender("outpatient", lang), "instructions", subject=subject, body=body)
    for key, part in (("sample_in", "input"), ("sample_out", "output")):
        (data_dir / FILES[key][lang]).write_text(json.dumps(w.sample[part], ensure_ascii=False, indent=1),
                                                 encoding="utf-8")


# ── the stored dataset: the hidden period and the answers per setting ───────

def write_hidden(world: World, out: Path) -> None:
    """The hidden period as the engine would send it, as far as it does not depend on the program.

    days/<date>.json: each call's input. Day 0 is complete (nothing has been decided yet); for days 1-19 the
    fields that depend on the program's earlier decisions (attendance, book, waitlist and the patients'
    cancellation notices) are left out: answer/<tier>/s<seed>/ has them for the reference program.
    mail/<lang>/*.eml: the period's e-mails behind the notices and notes. requests.csv: every request of the
    period and the start with its hidden facts (no-show rate, cancellation intent, duplicate)."""
    w = world
    days = out / "days"
    days.mkdir(parents=True, exist_ok=True)
    e = Engine(type("_Any", (), {"_w": w})())
    for d in range(N_DAYS):
        if d == 0:
            x = e.begin(0)
        else:
            x = {"date": iso(d), "day_index": d, "days_in_period": N_DAYS, "period_end": iso(N_DAYS - 1),
                 "booking_window": {"first": iso(d + 1), "last": iso(d + HORIZON)}, "doctors": doctors_json(w),
                 "sessions": sessions_json(w, d), "new_requests": [req_json(w, w.req[rid]) for rid in w.by_day[d]],
                 "notices": [dict(n) for n in w.notices.get(d, [])]}
        (days / f"{iso(d)}.json").write_text(json.dumps(x, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    acq = [(r.recv, r) for r in w.reqs if r.notes]
    for lang in LOCALES:
        mail = out / "mail" / lang
        mail.mkdir(parents=True, exist_ok=True)
        for doc, nd, ds, why in ABSENCES:
            _absence_mail(w, mail, lang, day_date(nd), doc, day_date(ds[0]), day_date(ds[-1]), why)
        _interpreter_mail(mail, lang, day_date(INTERP_NOTICE), day_date(INTERP_DAY))
        kw = _doctor_kw(w, HEAD_DOCTOR, lang)
        _mail(mail / f"{iso(HEAD_NOTE_DAY)}_department_head_{HEAD_DOCTOR}.eml", lang,
              _at(day_date(HEAD_NOTE_DAY), HEAD_DOCTOR), _sender("doctor", lang, **kw), "head_keepfree",
              note=HEAD_NOTE_L[lang], **kw)
        for t, r in sorted(acq, key=lambda x: (x[0], x[1].id)):
            k = ACQUAINTANCE.index(r.notes[0]["text"])
            _acquaintance_mail(w, mail, lang, day_date(t), r, r.id, k)
    write_csv(out / "requests.csv",
              ["request_id", "patient_id", "received", "department", "visit_type", "urgency", "status_at_start",
               "no_show_rate_at_zero_lead", "cancels_working_days_before", "duplicate_of"],
              [[r.id, r.patient, iso(r.recv), r.dept, "new" if r.new else "follow_up", r.urgency,
                "booked" if r.id in w.initial_book else "waiting" if r.recv < 0 else "",
                r.base_p, r.cancel_k or "", r.dup_of] for r in w.reqs])


def _reference_trace(view: _View) -> tuple:
    """The reference program's run with everything it did and saw per day (for the stored answers)."""
    sched = _module().Scheduler(_rt(ref_config(view)))
    decide = _decider(sched)
    e = Engine(view)
    log, attended = [], {}
    for d in range(N_DAYS):
        x = e.begin(d)
        out, err = decide(x)
        e.end(d, out, err)
        attended.update({a["request_id"]: a["attended"] for a in x["attendance"]})
        log.append((d, [n for n in x["notices"] if n["type"] == "cancellation"], out, e.table_truth(d)))
    return e, log, attended, e.finish()


def write_ground_truth(world: World, gt: Path, setting) -> None:
    """The reference program's run in this setting: its actions per day, the patients' cancellations it met,
    the expected status table of every day, and the book at the end (appointments held in the period and the
    upcoming ones) with the requests still waiting."""
    w = world
    e, log, attended, res = _reference_trace(_View(world, setting))
    write_csv(gt / "actions.csv", ["call_date", "seq", "type", "request_id", "doctor_id", "date", "start", "test_date"],
              [[iso(d), k, a.get("type"), a.get("request_id"), a.get("doctor_id", ""), a.get("date", ""),
                a.get("start", ""), a.get("test_date") or ""]
               for d, _, out, _ in log for k, a in enumerate(out["actions"], start=1)])
    write_csv(gt / "status_tables.csv", ["date", "department", "free_slots", "held_back", "waitlist"],
              [[iso(d), dept, row["free_slots"], row["held_back"], row["waitlist"]]
               for d, _, _, truth in log for dept, row in truth.items()])
    write_csv(gt / "cancellations.csv", ["notice_date", "request_id", "patient_id", "doctor_id", "date", "start"],
              [[iso(d), n["request_id"], n["patient_id"], n["doctor_id"], n["date"], n["start"]]
               for d, cx, _, _ in log for n in cx])
    book = [(rid, a, "held") for rid, a in e.past.items()] + [(rid, a, "upcoming") for rid, a in e.appt.items()]
    write_csv(gt / "final_book.csv",
              ["request_id", "patient_id", "department", "visit_type", "urgency", "doctor_id", "date", "start",
               "slots", "test_date", "booked_on", "state", "attended"],
              [[rid, w.req[rid].patient, w.req[rid].dept, "new" if w.req[rid].new else "follow_up",
                w.req[rid].urgency, a.doctor, iso(a.day), hhmm(a.start), a.n,
                iso(a.test) if a.test is not None else "", iso(a.booked_on), state,
                {True: "true", False: "false"}.get(attended.get(rid), "")]
               for rid, a, state in sorted(book, key=lambda x: (x[1].day, x[1].doctor, x[1].start, x[0]))])
    write_csv(gt / "final_waitlist.csv", ["request_id", "patient_id", "department", "visit_type", "urgency",
                                          "received", "earliest_date"],
              [[rid, w.req[rid].patient, w.req[rid].dept, "new" if w.req[rid].new else "follow_up",
                w.req[rid].urgency, iso(w.req[rid].recv), iso(w.req[rid].earliest)] for rid in sorted(e.open)])
