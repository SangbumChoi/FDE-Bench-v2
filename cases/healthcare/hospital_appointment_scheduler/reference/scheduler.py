"""Reference daily scheduler for healthcare/hospital_appointment_scheduler (copied into program/ with a
config.json).

Standard library only. The engine loads this file once and calls on_day(day) once per working day, in order,
in the same process. The book and the waitlist come with every call, so the program rebuilds its view of the
calendar each day; it only remembers the notices (absences, interpreter changes), which patients have had
an appointment in which department, and the day it released each request it released (a released request
is booked again no sooner than the notice period after that day).

Each day:
  * (medium+) apply the day's absence and interpreter notices; move every appointment of an absent doctor on
    an absent day (another doctor of the department at the same time for new patients, else the earliest free
    slot at least the notice period ahead, else back to the waitlist), and move interpreted new-patient visits
    off a day that has lost an interpreter;
  * take the waitlist and the new requests in priority order (urgent first; the setting's order after that)
    and book each into its earliest feasible slot in the next ten working days: department, follow-ups with
    their previous doctor, two consecutive slots for a new patient, never before the earliest date, the
    urgent reserve (the first `reserve_slots` morning slots) only for urgent requests until the day before,
    the holiday closure, in-person interpreters per day, (medium+) referral expiry and a blood test at least
    a working day before the visit within the lab cap; (hard) one appointment per patient and department,
    and a second department's visit on the same day when that costs at most two days;
  * (hard) overbook a waiting follow-up next to the booked follow-up of the same doctor with which the pair is
    least likely to turn up together, when the expected value is positive: the second patient's expected visit
    and the request no longer left without an appointment, against the collision cost times the chance that
    both come (rates estimated from the patients' records and the lead time), within the cap per session;
  * report the status table.

config.json holds the client's rule parameters for the setting and the no-show prior from the history. The
tier decides which parts of the data are in scope (absence and interpreter notices, referral dates, blood
tests, duplicates, overbooking); each can also be set on its own (`absences`, `interpreter_absence`,
`referrals`, `tests`, `dedupe`, `same_day`), which is how the case builds the misreadings of one client fact
at a time. Other switches exist only for variants (bending the follow-up habit, following notes, pulling
booked patients forward, table definitions), the baseline (`hold_reserve`, `no_overbook`) and programs that
break one rule each (`inject`, `inject_table`).
"""

import datetime as dt
import json
import os

BASE = dt.date(2026, 1, 5)
RESERVE_FIRST = 540                     # 09:00, the first slot of a morning session
URG = {"U": 0, "S": 1, "R": 2}
WAIT_WEIGHT = {"U": 3, "S": 2, "R": 1}  # how much a day of waiting weighs, by urgency
DEPTS = ("IM", "CARD", "DERM", "ORTH", "PED")


_WD = {}


def wd(s):
    """Working-day index of a date (Monday-Friday counted from a fixed Monday)."""
    i = _WD.get(s)
    if i is None:
        n = (dt.date.fromisoformat(s) - BASE).days
        w, r = divmod(n, 7)
        i = _WD[s] = w * 5 + min(r, 4)
    return i


def ds(i):
    w, r = divmod(i, 5)
    return (BASE + dt.timedelta(days=7 * w + r)).isoformat()


def mins(s):
    return int(s[:2]) * 60 + int(s[3:5])


def hhmm(m):
    return "%02d:%02d" % (m // 60, m % 60)


class Scheduler:
    def __init__(self, cfg):
        self.cfg = cfg
        self.medium = cfg["tier"] in ("medium", "hard")
        self.hard = cfg["tier"] == "hard"
        # the urgent reserve: the first N slots of every morning session
        self.res_starts = tuple(RESERVE_FIRST + 20 * k for k in range(cfg.get("reserve_slots", 2)))
        # what is in scope: the tier's answer unless the config says otherwise
        self.f_absence = cfg.get("absences", self.medium)                # doctor_absence notices
        self.f_interp_abs = cfg.get("interpreter_absence", self.medium)  # interpreter_absence notices
        self.f_referral = cfg.get("referrals", self.medium)              # referral_valid_until
        self.f_tests = cfg.get("tests", self.medium)                     # pre_visit_test
        self.f_dedupe = cfg.get("dedupe", self.hard)                     # one appointment per patient and department
        self.f_same_day = cfg.get("same_day", self.hard)                 # a second department on the same day
        self.f_overbook = cfg.get("overbook", self.hard) and cfg.get("overbooked_per_session", 0) > 0 \
            and not cfg.get("no_overbook")
        closed = cfg.get("closed_dept") or ()
        self.closed = set([closed] if isinstance(closed, str) else closed)
        self.reset()

    def reset(self):
        self.absent = {}        # doctor -> set of absent days
        self.interp_cut = {}    # day -> change in in-person interpreters
        self.ever = set()       # (patient, department) with an appointment that took place in the period
        self.rel_day = {}       # request -> the day this program released its appointment (notice counts from it)
        self.head_blocked = set()
        self.head_doc = None

    # ── calendar helpers ───────────────────────────────────────────────────
    def bookable(self, doc, D):
        cfg = self.cfg
        if cfg.get("holiday") and D == wd(cfg["holiday"]) and self.docs[doc]["department"] in self.closed:
            return False
        if self.f_absence and D in self.absent.get(doc, ()):
            return False
        return True

    def reserve(self, doc, D, s):
        if not self.cfg.get("pilot_reserve", True):
            return False
        return s in self.res_starts and self.half.get((doc, D, s)) == "AM"

    def cap(self, D):
        return self.cfg["interpreters_per_day"] + (self.interp_cut.get(D, 0) if self.f_interp_abs else 0)

    def needs_interp(self, r, doc):
        return r["visit_type"] == "new" and r["preferred_language"] not in self.docs[doc]["languages"]

    def prio(self, r):
        order = self.cfg["waitlist_order"]
        if order == "fcfs":                 # a variant: strictly the date received, urgent or not
            return (r["received"], r["request_id"])
        if order == "received":
            return (0 if r["urgency"] == "U" else 1, r["received"], r["request_id"])
        if order == "urgency_earliest":
            return (URG[r["urgency"]], r["earliest_date"], r["request_id"])
        return (URG[r["urgency"]], r["received"], r["request_id"])

    def deadline(self, r):
        if r["urgency"] != "U":
            return 10 ** 9
        return max(wd(r["earliest_date"]), wd(r["received"]) + 1) + self.cfg["urgent_days"]

    # ── occupancy ──────────────────────────────────────────────────────────
    def place(self, rid, doc, D, s, test, booked_on):
        r = self.req[rid]
        n = 2 if r["visit_type"] == "new" else 1
        a = {"doctor_id": doc, "D": D, "s": s, "n": n, "test": test, "booked_on": booked_on}
        self.appt[rid] = a
        self._fs.pop((doc, D), None)
        for k in range(n):
            lst = self.occ.setdefault((doc, D, s + 20 * k), [])
            if not lst and (doc, D, s + 20 * k) in self.half:
                self.nfree[(doc, D)] -= 1
            lst.append(rid)
        if self.needs_interp(r, doc):
            self.interp[D] = self.interp.get(D, 0) + 1
        if test is not None and test >= self.d + 1:
            self.lab[test] = self.lab.get(test, 0) + 1

    def unplace(self, rid):
        a = self.appt.pop(rid)
        self._fs.pop((a["doctor_id"], a["D"]), None)
        r = self.req[rid]
        for k in range(a["n"]):
            key = (a["doctor_id"], a["D"], a["s"] + 20 * k)
            self.occ[key].remove(rid)
            if not self.occ[key] and key in self.half:
                self.nfree[key[:2]] += 1
        if self.needs_interp(r, a["doctor_id"]):
            self.interp[a["D"]] -= 1
        if a["test"] is not None and a["test"] >= self.d + 1:
            self.lab[a["test"]] -= 1
        return a

    def free(self, doc, D, s, n):
        starts = [s + 20 * k for k in range(n)]
        if any((doc, D, x) not in self.half for x in starts):
            return False
        if len({self.half[(doc, D, x)] for x in starts}) != 1:
            return False
        return not any(self.occ.get((doc, D, x)) for x in starts)

    def test_day(self, r, D):
        lo = max(self.d + 1, wd(r["earliest_date"]))
        for t in range(lo, D):
            if self.lab.get(t, 0) < self.cfg["lab_cap"]:
                return t
        return None

    def find(self, r, lo, docs, keep_test=None, only=None):
        """Earliest feasible (doctor, day, start, test day) for request r from day `lo` on."""
        d, cfg = self.d, self.cfg
        n = 2 if r["visit_type"] == "new" else 1
        hi = min(d + cfg.get("book_ahead", cfg["horizon"]), self.deadline(r))
        if self.f_referral and r["visit_type"] == "new" and r.get("referral_valid_until"):
            hi = min(hi, wd(r["referral_valid_until"]))
        lo = max(lo, d + 1, wd(r["earliest_date"]))
        days = [only] if only is not None else range(lo, hi + 1)
        for D in days:
            if D < lo or D > hi:
                continue
            test = None
            if self.f_tests and r["pre_visit_test"]:
                if keep_test is not None and keep_test < D:
                    test = keep_test
                else:
                    test = self.test_day(r, D)
                    if test is None:
                        continue
            best = None
            occ = self.occ
            for doc in docs:
                if self.nfree.get((doc, D), 0) < n:
                    continue
                if not self.bookable(doc, D) or (doc, D) in self.head_blocked:
                    continue
                if self.needs_interp(r, doc) and self.interp.get(D, 0) >= self.cap(D):
                    continue
                use_reserve = r["urgency"] == "U" or (D < d + 2 and not cfg.get("hold_reserve"))
                if not cfg.get("pack"):
                    s = self.first_slot(doc, D, n, use_reserve)
                    if s is not None:
                        return doc, D, s, test
                    continue
                for half, starts in self.sess.get((doc, D), ()):
                    for i in range(len(starts) - n + 1):
                        s = starts[i]
                        if occ.get((doc, D, s)) or (n == 2 and (starts[i + 1] != s + 20
                                                                or occ.get((doc, D, s + 20)))):
                            continue
                        if not use_reserve and any(self.reserve(doc, D, s + 20 * k) for k in range(n)):
                            continue
                        # variant: prefer the slot that leaves the fewest isolated free slots
                        snug = sum(1 for x in (s - 20, s + 20 * n) if not self.free(doc, D, x, 1))
                        if best is None or snug > best[0]:
                            best = (snug, (doc, D, s, test))
                if best is not None and cfg.get("pack"):
                    return best[1]
        return None

    def first_slot(self, doc, D, n, use_reserve):
        """The first free start for an n-slot visit with the doctor on day D (cached until the day changes)."""
        cache = self._fs.setdefault((doc, D), {})
        key = (n, use_reserve)
        if key not in cache:
            cache[key] = None
            occ = self.occ
            for half, starts in self.sess.get((doc, D), ()):
                for i in range(len(starts) - n + 1):
                    s = starts[i]
                    if occ.get((doc, D, s)) or (n == 2 and (starts[i + 1] != s + 20 or occ.get((doc, D, s + 20)))):
                        continue
                    if not use_reserve and any(self.reserve(doc, D, s + 20 * k) for k in range(n)):
                        continue
                    cache[key] = s
                    break
                if cache[key] is not None:
                    break
        return cache[key]

    def doctors_for(self, r, bend=None):
        bend = self.cfg.get("bend") if bend is None else bend
        if self.cfg.get("bend_absence") and r["visit_type"] == "follow_up" and any(
                D > self.d for D in self.absent.get(r["previous_doctor"], ())):
            bend = True
        dept = [x for x in self.dept_docs[r["department"]]]
        if r["visit_type"] == "follow_up":
            prev = r["previous_doctor"]
            return [prev] + ([x for x in dept if x != prev] if bend else [])
        return sorted(dept, key=lambda x: (r["preferred_language"] not in self.docs[x]["languages"], x))

    # ── one day ────────────────────────────────────────────────────────────
    def on_day(self, day):
        cfg = self.cfg
        if day["day_index"] == 0:
            self.reset()
        d = self.d = wd(day["date"])
        self.docs = {x["doctor_id"]: x for x in day["doctors"]}
        self.dept_docs = {}
        for x in day["doctors"]:
            self.dept_docs.setdefault(x["department"], []).append(x["doctor_id"])
        self.sess, self.half, self.nfree, self._fs = {}, {}, {}, {}
        for s in day["sessions"]:
            D = wd(s["date"])
            starts = [mins(x) for x in s["starts"]]
            self.sess.setdefault((s["doctor_id"], D), []).append((s["session"], starts))
            self.nfree[(s["doctor_id"], D)] = self.nfree.get((s["doctor_id"], D), 0) + len(starts)
            for m in starts:
                self.half[(s["doctor_id"], D, m)] = s["session"]
        for n in day["notices"]:
            if n["type"] == "doctor_absence" and self.f_absence:
                self.absent.setdefault(n["doctor_id"], set()).update(range(wd(n["from"]), wd(n["to"]) + 1))
            elif n["type"] == "interpreter_absence" and self.f_interp_abs:
                D = wd(n["date"])
                self.interp_cut[D] = self.interp_cut.get(D, 0) + n["in_person_interpreters_change"]
            elif n["type"] == "staff_note" and cfg.get("head_note"):       # variant only: following the note
                self.head_doc = n["doctor_id"]
        if self.head_doc:
            self.head_blocked = {(x, D) for (x, D), lst in self.sess.items() if x == self.head_doc
                                 and any(h == "PM" for h, _ in lst)}
        for a in day["attendance"]:
            self.ever.add((a["patient_id"], self.docs[a["doctor_id"]]["department"]))

        self.req, self.appt, self.occ, self.interp, self.lab = {}, {}, {}, {}, {}
        start = {}
        for b in day["book"]:
            r = b["request"]
            self.req[r["request_id"]] = r
            test = wd(b["test_date"]) if b.get("test_date") else None
            self.place(r["request_id"], b["doctor_id"], wd(b["date"]), mins(b["start"]), test, wd(b["booked_on"]))
            start[r["request_id"]] = (b["doctor_id"], wd(b["date"]), mins(b["start"]), test)
        waiting = {}
        for r in day["waitlist"] + day["new_requests"]:
            self.req[r["request_id"]] = r
            waiting[r["request_id"]] = r
        released = set()
        actions = []

        def move(rid, doc, D, s, test):
            a = self.unplace(rid)
            same = (a["doctor_id"], a["D"], a["s"]) == (doc, D, s)
            self.place(rid, doc, D, s, test, a["booked_on"] if same else d)

        def release(rid):
            self.unplace(rid)
            waiting[rid] = self.req[rid]
            released.add(rid)
            self.rel_day[rid] = d

        notice = cfg["move_notice_days"]
        if cfg.get("book_nothing"):         # a variant: no action at all, the table as the day ends
            return {"actions": [], "status_table": self.table(waiting)}
        if self.f_absence:
            # Appointments of absent doctors.
            for rid in sorted(self.appt, key=lambda x: (self.appt[x]["D"], self.appt[x]["s"], x)):
                a = self.appt[rid]
                if a["D"] not in self.absent.get(a["doctor_id"], ()):
                    continue
                r = self.req[rid]
                done = False
                if r["visit_type"] == "new" or cfg.get("bend") or cfg.get("bend_absence"):
                    for doc in self.doctors_for(r, bend=True):
                        if doc == a["doctor_id"] or not self.bookable(doc, a["D"]):
                            continue
                        if not self.free(doc, a["D"], a["s"], a["n"]):
                            continue
                        if self.needs_interp(r, doc) and self.interp.get(a["D"], 0) >= self.cap(a["D"]):
                            continue
                        move(rid, doc, a["D"], a["s"], a["test"])
                        done = True
                        break
                if done:
                    continue
                docs = [x for x in self.doctors_for(r, bend=cfg.get("bend") or cfg.get("bend_absence"))
                        if x != a["doctor_id"] or r["visit_type"] == "follow_up"]
                f = self.find(r, d + notice, docs, keep_test=a["test"])
                if f:
                    move(rid, *f)
                else:
                    release(rid)
        if self.f_interp_abs:
            # Days that lost an interpreter.
            for D in sorted(self.interp_cut):
                while D > d and self.interp.get(D, 0) > self.cap(D):
                    cands = sorted((x for x, a in self.appt.items() if a["D"] == D
                                    and self.needs_interp(self.req[x], a["doctor_id"])
                                    and self.req[x]["urgency"] != "U"),
                                   key=lambda x: (-self.appt[x]["booked_on"], x))
                    if not cands:
                        break
                    rid = cands[0]
                    a, r = self.appt[rid], self.req[rid]
                    alt = [x for x in self.dept_docs[r["department"]] if r["preferred_language"]
                           in self.docs[x]["languages"] and self.bookable(x, D) and self.free(x, D, a["s"], a["n"])]
                    if alt:
                        move(rid, alt[0], D, a["s"], a["test"])
                        continue
                    f = self.find(r, d + notice, self.doctors_for(r), keep_test=a["test"])
                    if f and f[1] != D:
                        move(rid, *f)
                    else:
                        release(rid)

        morning = self.table(waiting) if cfg.get("table_morning") else None
        # The waitlist in priority order.
        todo = sorted(waiting.values(), key=self.prio)
        if cfg.get("urgent_only"):          # a variant: only the urgent requests are booked
            todo = [r for r in todo if r["urgency"] == "U"]
        if cfg.get("follow_notes"):
            todo.sort(key=lambda r: 0 if r.get("notes") else 1)
        skipped = set()
        if self.f_dedupe:
            seen = set()
            upcoming = {(self.req[x]["patient_id"], self.req[x]["department"]) for x in self.appt}
            for r in sorted(waiting.values(), key=lambda r: (r["received"], r["request_id"])):
                key = (r["patient_id"], r["department"])
                if key in seen or key in self.ever or key in upcoming:
                    skipped.add(r["request_id"])
                seen.add(key)
        n_ob = None
        if self.f_overbook:              # overbooked slots per doctor session so far
            n_ob = {}
            for (doc, D), sessions in self.sess.items():
                for half, starts in sessions:
                    n_ob[(doc, D, half)] = sum(1 for s in starts if len(self.occ.get((doc, D, s), ())) >= 2)
        stuck = set()                    # (department, previous doctor) with a follow-up left waiting today
        for r in todo:
            rid = r["request_id"]
            if rid in skipped:
                continue
            # a request this program released (today or earlier): the notice counts from the release
            lo = max(d + 1, self.rel_day.get(rid, -10 ** 6) + notice)
            docs = self.doctors_for(r)
            if cfg.get("follow_notes") and r.get("notes"):
                f = None
                for doc in docs:
                    for half, starts in self.sess.get((doc, d + 1), ()):
                        if half != "AM" or not self.bookable(doc, d + 1):
                            continue
                        for s in starts:
                            if self.free(doc, d + 1, s, 2):
                                f = (doc, d + 1, s, None)
                                break
                        if f:
                            break
                    if f:
                        break
                if f is None:
                    f = self.find(r, lo, docs)
            else:
                f = self.find(r, lo, docs)
            if f and self.f_same_day:
                other = sorted({a["D"] for x, a in self.appt.items() if self.req[x]["patient_id"] == r["patient_id"]})
                for X in other:
                    if f[1] < X <= f[1] + 2:
                        g = self.find(r, lo, docs, only=X)
                        if g:
                            f = g
                            break
            group = (r["department"], r["previous_doctor"])
            if n_ob is not None and r["visit_type"] == "follow_up" and group not in stuck and not (
                    f and r["urgency"] == "U"):
                # a place next to another follow-up, when that is worth more than the free slot (or than waiting)
                g = self.double_up(r, lo, f, n_ob)
                if g:
                    f = g[:4]
                    n_ob[(g[0], g[1], g[4])] += 1
            if f:
                self.place(rid, f[0], f[1], f[2], f[3], d)
                del waiting[rid]
            elif r["visit_type"] == "follow_up":
                # nobody behind this request in its doctor's queue may be doubled up into a slot it could have had
                stuck.add(group)

        if cfg.get("bend_idle"):
            self.fill_idle(todo, waiting, skipped, notice)
        if cfg.get("pull_forward"):
            self.pull_forward(move)

        # Actions: what changed against the morning book.
        for rid in sorted(set(start) | set(self.appt)):
            a = self.appt.get(rid)
            if a is None:
                if rid in start:
                    actions.append({"type": "release", "request_id": rid})
                continue
            now = (a["doctor_id"], a["D"], a["s"], a["test"])
            if start.get(rid) == now:
                continue
            act = {"type": "move" if rid in start else "book", "request_id": rid, "doctor_id": a["doctor_id"],
                   "date": ds(a["D"]), "start": hhmm(a["s"]),
                   "test_date": ds(a["test"]) if a["test"] is not None else None}
            if rid in start and rid in released:
                actions.append({"type": "release", "request_id": rid})
                act["type"] = "book"
            actions.append(act)
        actions.sort(key=lambda x: (x["type"] != "release", x["type"] != "move", x["request_id"]))

        table = morning if morning is not None else self.table(waiting)
        if cfg.get("table_none"):
            table = None
        actions += cfg.get("inject", {}).get(str(day["day_index"]), [])
        out = {"actions": actions, "status_table": table}
        if str(day["day_index"]) in cfg.get("inject_table", {}):        # the validator's malformed-table example
            out["status_table"] = cfg["inject_table"][str(day["day_index"])]
        return out

    # ── overbooking (hard) ─────────────────────────────────────────────────
    def p_show(self, rid, D, booked_on):
        """Estimated chance that the patient of request `rid` comes on day D to an appointment booked on
        `booked_on`: the patient's record shrunk towards the history's missed share, plus the lead-time effect."""
        ns = self.cfg["noshow"]
        oracle = self.cfg.get("oracle_p")
        q = self.req[rid]
        if oracle is not None:
            base = oracle[rid]
        else:
            hist = ns["base0"] + ns["slope"] * ns["hist_lead"]
            base = (q["missed_appointments"] + ns["shrink"] * hist) / (q["past_appointments"] + ns["shrink"]) \
                - ns["slope"] * ns["hist_lead"]
        return 1.0 - min(0.9, max(0.0, base + ns["slope"] * max(D - booked_on, 0)))

    def double_up(self, r, lo, f, n_ob):
        """The best slot for follow-up r next to a booked follow-up of its doctor: (doctor, day, start, test day,
        session), or None when no such slot is worth it.

        With a free slot f in reach, doubling up on an earlier day is worth the free slot it leaves for someone
        else (`ob_slot_value`) and the days of waiting saved, less the collision cost times the chance that both
        patients come. Without one it is worth the patient's expected visit and the request no longer left
        without an appointment (`ob_booked_value`), less the same expected collision. `ob_blind` (a variant: a
        program that takes a double-booked slot to cost nothing) takes the earliest such slot."""
        cfg, d = self.cfg, self.d
        rid, doc = r["request_id"], r["previous_doctor"]
        cap, blind = cfg["overbooked_per_session"], cfg.get("ob_blind")
        seen, coll = cfg["seen_value"], cfg["collision_cost"]
        slot_value = cfg.get("ob_slot_value", 0.8 * seen)
        booked = cfg.get("ob_booked_value", cfg.get("unbooked_cost", 10.0))
        wait = cfg.get("wait_cost", 0.4) * WAIT_WEIGHT[r["urgency"]]
        lo = max(lo, wd(r["earliest_date"]))
        hi = f[1] - 1 if f else d + cfg["horizon"]
        best = None
        for D in range(lo, hi + 1):
            if not self.bookable(doc, D) or (doc, D) in self.head_blocked:
                continue
            test = None
            if self.f_tests and r["pre_visit_test"]:
                test = self.test_day(r, D)
                if test is None:
                    continue
            pb = self.p_show(rid, D, d)
            for half, starts in self.sess.get((doc, D), ()):
                if n_ob[(doc, D, half)] >= cap:
                    continue
                for s in starts:
                    lst = self.occ.get((doc, D, s), ())
                    if len(lst) != 1 or self.req[lst[0]]["visit_type"] != "follow_up":
                        continue
                    if r["urgency"] != "U" and (D >= d + 2 or cfg.get("hold_reserve")) and self.reserve(doc, D, s):
                        continue
                    if blind:
                        gain = 1.0
                    else:
                        pa = self.p_show(lst[0], D, self.appt[lst[0]]["booked_on"])
                        gain = (slot_value + wait * (f[1] - D) if f else pb * seen + booked) - coll * pa * pb
                    if best is None or gain > best[0] + 1e-9:
                        best = (gain, doc, D, s, test, half)
            if blind and best:
                break
        return best[1:] if best and best[0] > cfg.get("ob_margin", 0.0) else None

    # ── variants: what a program does that misreads one fact, or bends the habit ──
    def fill_idle(self, todo, waiting, skipped, notice):
        """Bending the habit where it fills doctor time: a slot still empty tomorrow goes to a waiting follow-up
        of a colleague's patient (the head of the outpatient office's exception)."""
        d, D = self.d, self.d + 1
        for r in todo:
            rid = r["request_id"]
            if rid not in waiting or rid in skipped or r["visit_type"] != "follow_up":
                continue
            if wd(r["earliest_date"]) > D or self.rel_day.get(rid, -10 ** 6) + notice > D:
                continue
            if self.f_tests and r["pre_visit_test"]:
                continue
            for doc in self.dept_docs[r["department"]]:
                if doc == r["previous_doctor"] or not self.bookable(doc, D) or (doc, D) in self.head_blocked:
                    continue
                s = self.first_slot(doc, D, 1, True)
                if s is not None:
                    self.place(rid, doc, D, s, None, d)
                    del waiting[rid]
                    break

    def pull_forward(self, move):
        """A slot still empty tomorrow goes to a patient of the same doctor who is booked for a later day (a
        program that takes changing an appointment to be free and to need no notice)."""
        d, D = self.d, self.d + 1
        later = sorted((x for x, a in self.appt.items() if a["D"] > D and self.req[x]["urgency"] != "U"
                        and wd(self.req[x]["earliest_date"]) <= D and a["test"] is None
                        and not (self.f_tests and self.req[x]["pre_visit_test"])),
                       key=lambda x: self.prio(self.req[x]))
        for rid in later:
            a = self.appt[rid]
            doc = a["doctor_id"]
            if not self.bookable(doc, D) or (doc, D) in self.head_blocked:
                continue
            if self.needs_interp(self.req[rid], doc) and self.interp.get(D, 0) >= self.cap(D):
                continue
            if len(self.occ.get((doc, a["D"], a["s"]), ())) > 1:
                continue
            s = self.first_slot(doc, D, a["n"], True)
            if s is not None:
                move(rid, doc, D, s, None)

    # ── the status table ───────────────────────────────────────────────────
    def table(self, waiting):
        d, cfg = self.d, self.cfg
        # variants (the never-asks program): the table's own reserve size and City Day closures
        res = self.res_starts if cfg.get("table_reserve_slots") is None else tuple(
            RESERVE_FIRST + 20 * k for k in range(cfg["table_reserve_slots"]))
        closed = self.closed if cfg.get("table_closed") is None else set(cfg["table_closed"])
        holiday = wd(cfg["holiday"]) if cfg.get("holiday") else None
        out = {}
        for dept in DEPTS:
            free = held = 0
            for doc in self.dept_docs.get(dept, ()):
                for D in range(d + 1, d + cfg["horizon"] + 1):
                    if not cfg.get("table_calendar_as_is") and (
                            (D == holiday and dept in closed) or (self.f_absence and D in self.absent.get(doc, ()))):
                        continue
                    for half, starts in self.sess.get((doc, D), ()):
                        for s in starts:
                            if self.occ.get((doc, D, s)):
                                continue
                            if cfg.get("pilot_reserve", True) and s in res and half == "AM" and not cfg.get(
                                    "table_no_reserve") and (D >= d + 2 or cfg.get("table_hold_tomorrow")):
                                held += 1
                            else:
                                free += 1
            rs = [r for r in waiting.values() if r["department"] == dept]
            if self.f_referral and not cfg.get("table_count_expired"):
                rs = [r for r in rs if not (r["visit_type"] == "new" and r.get("referral_valid_until")
                                            and wd(r["referral_valid_until"]) < d + 1)]
            if self.f_dedupe and not cfg.get("table_count_requests"):
                upcoming = {(self.req[x]["patient_id"], self.req[x]["department"]) for x in self.appt}
                n = len({r["patient_id"] for r in rs if (r["patient_id"], dept) not in self.ever
                         and (r["patient_id"], dept) not in upcoming})
            else:
                n = len(rs)
            out[dept] = {"free_slots": free, "held_back": held, "waitlist": n}
        if cfg.get("table_zero"):
            out = {dept: {"free_slots": 0, "held_back": 0, "waitlist": 0} for dept in DEPTS}
        if cfg.get("table_const"):          # a variant: the same numbers every day
            out = {dept: dict(row) for dept, row in cfg["table_const"].items()}
        return out


_INSTANCE = None


def on_day(day):
    global _INSTANCE
    if _INSTANCE is None:
        here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(here, "config.json"), encoding="utf-8") as f:
            _INSTANCE = Scheduler(json.load(f))
    return _INSTANCE.on_day(day)
