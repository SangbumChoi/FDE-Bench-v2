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
patients who often stay away), without breaking a rule. Quality = 0.8 x operations value / the reference
program's operations value + 0.2 x status-table accuracy. The operations value counts 10 per expected
patient-slot seen on the period's clinic days, minus waiting, unbooked requests, moves of patients'
appointments and (hard) overbooking collisions and extra trips.

One world and one hidden period for every setting: the same doctors, requests, cancellations intents,
notices and notes. The tier decides which rules are in force:

  easy    the daily booking core: new patient = 2 consecutive slots, follow-up = 1; department; the urgent
          window; the urgent reserve (first two morning slots held for urgent requests until the day before);
          a clinic closed on the City Day holiday; in-person interpreters per day for new patients; the
          notice period for moving an appointment; the waitlist priority order; follow-ups with the same
          doctor (bendable); the status table. Absence and interpreter notices, referral dates, blood tests,
          no-shows and duplicates are out of scope.
  medium  + referral letters that expire, a fasting blood test >= 1 working day before the visit with a daily
          lab cap, doctor absences (the absent doctor's appointments must be moved, with the notice period)
          and an interpreter's absence (one fewer interpreter that day)
  hard    + no-shows (hidden per-patient rates rising with lead time; expected-value scoring), overbooking of
          follow-ups (two to a slot, a cap per doctor session), duplicate requests (one appointment per
          patient and department) and extra trips of patients with several departments

The rule set (A / B / C) sets the parameters: which clinic closes on the holiday, the urgent window, the
interpreters per day, the lab cap, the overbooking cap, the notice period for moves and the waitlist order.
"""

from __future__ import annotations

import copy
import datetime as dt
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
HOLIDAY = 10                            # Monday 23 November 2026, City Day: one clinic closes (rule set)
SCORED = range(1, N_DAYS + 1)           # clinic days whose appointments are final at the end (1..20)
SLOT = 20
AM = tuple(540 + SLOT * k for k in range(9))      # 09:00 .. 11:40
PM = tuple(780 + SLOT * k for k in range(9))      # 13:00 .. 15:40
RESERVE = (540, 560)                    # urgent reserve: the first two slots of every morning session
DEPTS = ("IM", "CARD", "DERM", "ORTH", "PED")
CLOSABLE = ("DERM", "ORTH", "PED")
LANGS = ("L0", "F1", "F2", "F3", "F4")  # L0 = the local language
URGENCY = ("U", "S", "R")
WEIGHT = {"U": 3, "S": 2, "R": 1}
SEEN_VALUE = 10.0                       # per patient-slot seen on a clinic day of the period
WAIT_COST = 0.4                         # per working day of waiting x urgency weight
UNBOOKED_COST = 10.0                    # per request (need) never booked
MOVE_COST = 4.0                         # per change the hospital makes to a patient's appointment
COLLISION_COST = 12.0                   # hard: both patients of an overbooked slot turn up
TRIP_COST = 3.0                         # hard: an extra hospital trip of a patient with several departments
OPS_WEIGHT, TABLE_WEIGHT = 0.8, 0.2
LEAD_SLOPE = 0.01                       # hard: no-show rate + 1 point per working day of lead time
HIST_LEAD = 5                           # the patients' attendance counts were measured at ~5 days of lead
CALL_TIMEOUT = 10.0
TOTAL_TIMEOUT = 600.0

# Notices (data: the same in every setting; which apply is the tier's business).
ABSENCES = (("D13", 4, tuple(range(5, 15)), "illness"),      # notice day, absent days, reason
            ("D05", 9, (15, 16, 17, 18), "conference"))
INTERP_NOTICE, INTERP_DAY = 11, 13
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
TEST_SHARE = {"IM": 0.2, "CARD": 0.2, "PED": 0.08}
PREV_WEIGHT = {"D11": 2.5, "D13": 2.5, "D05": 2.0}
N_WAIT0 = 45
N_DUPLICATES = 10
N_MULTI = 10
CANCEL_SHARE = 0.09


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


def no_show(r: Req, lead: int) -> float:
    """True probability that the patient stays away from an appointment booked `lead` working days ahead."""
    return min(0.9, r.base_p + LEAD_SLOPE * max(lead, 0))


class _View:
    """The world as one setting's rules see it."""

    def __init__(self, world: World, setting):
        self._w, self.setting = world, setting
        self.medium, self.hard = setting.at_least("medium"), setting.at_least("hard")
        self.closed = str(setting["closed_dept"])
        self.urgent_days = int(setting["urgent_days"])
        self.interpreters = int(setting["interpreters_per_day"])
        self.lab_cap = int(setting["lab_cap"])
        self.ob_cap = int(setting["overbooked_per_session"])
        self.notice = int(setting["move_notice_days"])
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
        if self.order == "received":
            return (0 if r.urgency == "U" else 1, r.recv, r.id)
        if self.order == "urgency_earliest":
            return (URGENCY.index(r.urgency), r.earliest, r.id)
        return (URGENCY.index(r.urgency), r.recv, r.id)

    def dup(self, r: Req) -> bool:
        return self.hard and bool(r.dup_of)


# ── generation ───────────────────────────────────────────────────────────────

def _base_p(rng: random.Random) -> float:
    return round(rng.betavariate(4, 8) if rng.random() < 0.15 else rng.betavariate(2, 14), 4)


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
                    held = half == "AM" and s in RESERVE and t >= 1
                    if held or rng.random() >= occ:
                        i += 1
                        continue
                    new = i + 1 < len(starts) and rng.random() < NEW_SHARE and not (
                        half == "AM" and starts[i + 1] in RESERVE and t >= 1)
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
            for half, starts in w.sessions(doc.id, t):
                i = 0
                while i < len(starts):
                    if rng.random() >= 0.92:
                        i += 1
                        continue
                    new = i + 1 < len(starts) and rng.random() < NEW_SHARE
                    urg = rng.choices(URGENCY, weights=(4, 28, 68))[0]
                    recv = t - (1 if urg == "U" else rng.randint(1, 12))
                    r = Req("", "", doc.dept, None if new else doc.id, urg, _lang(rng), recv, recv + 1,
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

    def __init__(self, view: _View):
        self.v, self.w = view, view._w
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

    def flag(self, rule: str, msg: str) -> None:
        self.found.setdefault(rule, []).append(msg)

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
        actions, table = [], None
        if err is not None:
            problems.append(f"call failed: {err}"[:200])
            self.m["calls_failed"] += 1
        elif not isinstance(out, dict) or not isinstance(out.get("actions"), list):
            problems.append("output is not {'actions': [...], 'status_table': {...}}")
        else:
            actions, table = out["actions"], out.get("status_table")
        for act in actions:
            n = len(problems)
            self._apply(d, act, problems)
            self.m["actions_rejected"] += len(problems) - n
        for p in problems:
            self.flag("well_formed", f"{iso(d)}: {p}")
        self._check(d)
        self.acc.append(self._table_accuracy(d, table))

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
                        s in RESERVE and w.slot_half(a.doctor, a.day).get(s) == "AM" for s in a.slots()):
                    self.flag("urgent_reserve", f"{day}: {r.urgency} request {rid} in the reserve slot "
                                                f"{a.doctor} {iso(a.day)} {hhmm(a.start)}")
                # Notice is for a changed date or time; the same slot with another doctor needs none.
                if was is not None and (a.day, a.start) != was[1:3] and a.day < d + v.notice:
                    self.flag("move_notice", f"{day}: {rid} moved to {iso(a.day)} with less than {v.notice} "
                                             f"working days' notice")
                elif was is None and rid in self.released_on:
                    # A request the hospital released and books again later: notice from the day of the release
                    # (the same date and time as the released appointment needs none).
                    rd, t0, s0 = self.released_on[rid]
                    if a.day < rd + v.notice and (a.day, a.start) != (t0, s0):
                        self.flag("move_notice", f"{day}: {rid} released on {iso(rd)} and booked again for "
                                                 f"{iso(a.day)}, less than {v.notice} working days after the release")
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
                self.flag("interpreter_capacity", f"{day}: {n} interpreted new-patient visits on {iso(t)}")
        for t, n in lab.items():
            if n > v.lab_cap:
                self.flag("lab_capacity", f"{day}: {n} blood tests on {iso(t)}")
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
                self.flag("waitlist_priority", f"{iso(d)}: {rid} booked on {iso(a.day)} while {y.id} (higher "
                                               f"priority) still waits")
                break

    # ── the status table ─────────────────────────────────────────────────────
    def table_truth(self, d: int) -> dict:
        w, v = self.w, self.v
        out = {}
        upcoming = {(w.req[rid].patient, w.req[rid].dept) for rid in self.appt}
        for dept in DEPTS:
            free = held = 0
            for doc in w.doctors:
                if doc.dept != dept:
                    continue
                for t in range(d + 1, d + HORIZON + 1):
                    if v.closed_on(dept, t) or v.absent(doc.id, t, d):
                        continue
                    for h, starts in w.sessions(doc.id, t):
                        for s in starts:
                            if self.occ.get((doc.id, t, s)):
                                continue
                            if h == "AM" and s in RESERVE and t >= d + 2:
                                held += 1
                            else:
                                free += 1
            waiting = [w.req[rid] for rid in self.open if w.req[rid].dept == dept]
            if v.medium:
                waiting = [r for r in waiting if not (r.new and r.referral < d + 1)]
            if v.hard:
                n = len({r.patient for r in waiting if (r.patient, dept) not in self.held
                         and (r.patient, dept) not in upcoming})
            else:
                n = len(waiting)
            out[dept] = {"free_slots": free, "held_back": held, "waitlist": n}
        return out

    def _table_accuracy(self, d: int, table) -> float:
        if not isinstance(table, dict):
            return 0.0
        truth = self.table_truth(d)
        ok = total = 0
        for dept, row in truth.items():
            got = table.get(dept)
            for k, val in row.items():
                total += 1
                x = got.get(k) if isinstance(got, dict) else None
                ok += isinstance(x, (int, float)) and not isinstance(x, bool) and x == val
        return ok / total

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
                    slots.setdefault((a.doctor, a.day, s), []).append(p)
        for ps in slots.values():
            if len(ps) == 2:
                collisions += COLLISION_COST * ps[0] * ps[1]
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
        value = (SEEN_VALUE * seen - wait - UNBOOKED_COST * unbooked - MOVE_COST * self.moves - collisions
                 - TRIP_COST * trips)
        acc = sum(self.acc) / len(self.acc) if self.acc else 0.0
        viol = [(rule, f"{len(items)} cases, e.g. {items[0]}") for rule, items in self.found.items()]
        m = dict(self.m)
        m.update(ops_value=round(value, 3), seen_slots=round(seen, 3), capacity_slots=cap,
                 utilization=round(seen / cap, 6) if cap else 0.0, waiting_cost=round(wait, 3),
                 unbooked=unbooked, moves=self.moves, collision_cost=round(collisions, 3), extra_trips=trips,
                 overbooked_slots=sum(1 for ps in slots.values() if len(ps) == 2), table_accuracy=round(acc, 6))
        return {"violations": viol, "value": value, "accuracy": acc, "metrics": m}


def replay(view: _View, decide, engine: Engine | None = None, first: int = 0) -> dict:
    """Run the hidden period in one setting. `decide(day_input)` returns (output, error) for one call."""
    e = engine or Engine(view)
    for d in range(first, N_DAYS):
        x = e.begin(d)
        out, err = decide(x)
        e.end(d, out, err)
    return e.finish()


def _objective(res: dict, ref_value: float) -> float:
    return OPS_WEIGHT * res["value"] / ref_value + TABLE_WEIGHT * res["accuracy"]


def score(world: World, submission_dir: Path, setting) -> dict:
    view = _View(world, setting)
    ref_value = _reference_run(view)["value"]
    try:
        with program_session(Path(submission_dir), ENTRYPOINT, per_call_timeout=CALL_TIMEOUT,
                             total_timeout=TOTAL_TIMEOUT) as prog:
            res = replay(view, prog.call)
    except Fatal as e:
        return {"fatal": str(e)}
    res["metrics"].update(reference_ops_value=round(ref_value, 3),
                          ops_component=round(res["value"] / ref_value, 6))
    return {"violations": res["violations"], "objective": round(_objective(res, ref_value), 8),
            "metrics": res["metrics"]}


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
           "interpreters_per_day": view.interpreters, "lab_cap": view.lab_cap,
           "overbooked_per_session": view.ob_cap, "move_notice_days": view.notice,
           "waitlist_order": view.order, "horizon": HORIZON, "noshow": _noshow_prior(view._w),
           "seen_value": SEEN_VALUE, "collision_cost": COLLISION_COST}
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
        return any(x in RESERVE and self.w.slot_half(doc, t).get(x) == "AM" for x in (s, s + SLOT * (n - 1)))

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
        elif rule == "lab_capacity":
            for t in range(d + 1, d + HORIZON + 1):
                load = sum(1 for a in st.e.appt.values() if a.test == t)
                movers = [(rid, r, a) for rid, r, a in st.appts(no_test=False, urgent=True)
                          if r.test and a.day > t + 0 and a.test != t and r.earliest <= t and a.day - 1 >= t
                          and (a.test is None or a.test >= d + 1)]
                need = v.lab_cap + 1 - load
                if 0 < need <= len(movers):
                    yield d, [st.act("move", rid, a.doctor, a.day, a.start, t) for rid, r, a in movers[:need]]
        elif rule == "test_before_visit":
            for rid, r, a in st.appts(no_test=False):
                if r.test and a.day >= d + 1 and sum(1 for b in st.e.appt.values() if b.test == a.day) < v.lab_cap:
                    yield d, [st.act("move", rid, a.doctor, a.day, a.start, a.day)]
        elif rule == "referral_validity":
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


# ── the pilot day shown in the data ──────────────────────────────────────────

PILOT_RULES = {"tier": "easy", "closed_dept": "", "holiday": "", "urgent_days": 2, "interpreters_per_day": 3,
               "lab_cap": 10, "overbooked_per_session": 0, "move_notice_days": 1, "waitlist_order": "received",
               "horizon": HORIZON, "noshow": {"base0": 0.15, "slope": 0.01, "shrink": 6.0, "hist_lead": HIST_LEAD},
               "seen_value": SEEN_VALUE, "collision_cost": COLLISION_COST, "pilot_reserve": False}


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
    for r in reqs:
        a = appt.get(id(r))
        if a and r.new and r.dept == "ORTH" and r.urgency == "R" and r.recv == -7 and a.day > r.recv + 1:
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
    cancellation notices) are left out: gt/<setting>/ has them for the reference program.
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
