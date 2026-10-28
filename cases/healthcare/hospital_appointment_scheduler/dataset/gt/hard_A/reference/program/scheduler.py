"""Reference daily scheduler for healthcare/hospital_appointment_scheduler (copied into program/ with a
config.json).

Standard library only. The engine loads this file once and calls on_day(day) once per working day, in order,
in the same process. The book and the waitlist come with every call, so the program rebuilds its view of the
calendar each day; it only remembers the notices (absences, interpreter changes) and which patients have had
an appointment in which department.

Each day:
  * (medium+) apply the day's absence and interpreter notices; move every appointment of an absent doctor on
    an absent day (another doctor of the department at the same time for new patients, else the earliest free
    slot at least the notice period ahead, else back to the waitlist), and move interpreted new-patient visits
    off a day that has lost an interpreter;
  * take the waitlist and the new requests in priority order (urgent first; the rule set's order after that)
    and book each into its earliest feasible slot in the next ten working days: department, follow-ups with
    their previous doctor, two consecutive slots for a new patient, never before the earliest date, the
    urgent reserve (first two morning slots) only for urgent requests until the day before, the holiday
    closure, in-person interpreters per day, (medium+) referral expiry and a blood test at least a working
    day before the visit within the lab cap; (hard) one appointment per patient and department, and a second
    department's visit on the same day when that costs at most two days;
  * (hard) overbook waiting follow-ups into slots of follow-ups whose patients' estimated no-show rate makes
    the expected gain positive (rate > 1 - seen value / collision cost), within the cap per session;
  * report the status table.

config.json holds the client's rule parameters for the setting and the no-show prior from the history; a few
switches exist only so the case can build variants (bending the follow-up habit, following notes) and
programs that break one rule each (`inject`).
"""

import datetime as dt
import json
import os

BASE = dt.date(2026, 1, 5)
RESERVE = (540, 560)
URG = {"U": 0, "S": 1, "R": 2}
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
        self.reset()

    def reset(self):
        self.absent = {}        # doctor -> set of absent days
        self.interp_cut = {}    # day -> change in in-person interpreters
        self.ever = set()       # (patient, department) with an appointment that took place in the period
        self.head_blocked = set()
        self.head_doc = None

    # ── calendar helpers ───────────────────────────────────────────────────
    def bookable(self, doc, D):
        cfg = self.cfg
        if cfg.get("holiday") and D == wd(cfg["holiday"]) and self.docs[doc]["department"] == cfg["closed_dept"]:
            return False
        if self.medium and D in self.absent.get(doc, ()):
            return False
        return True

    def reserve(self, doc, D, s):
        if not self.cfg.get("pilot_reserve", True):
            return False
        return s in RESERVE and self.half.get((doc, D, s)) == "AM"

    def cap(self, D):
        return self.cfg["interpreters_per_day"] + (self.interp_cut.get(D, 0) if self.medium else 0)

    def needs_interp(self, r, doc):
        return r["visit_type"] == "new" and r["preferred_language"] not in self.docs[doc]["languages"]

    def prio(self, r):
        order = self.cfg["waitlist_order"]
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
        hi = min(d + cfg["horizon"], self.deadline(r))
        if self.medium and r["visit_type"] == "new" and r.get("referral_valid_until"):
            hi = min(hi, wd(r["referral_valid_until"]))
        lo = max(lo, d + 1, wd(r["earliest_date"]))
        days = [only] if only is not None else range(lo, hi + 1)
        for D in days:
            if D < lo or D > hi:
                continue
            test = None
            if self.medium and r["pre_visit_test"]:
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
            if n["type"] == "doctor_absence" and self.medium:
                self.absent.setdefault(n["doctor_id"], set()).update(range(wd(n["from"]), wd(n["to"]) + 1))
            elif n["type"] == "interpreter_absence" and self.medium:
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

        notice = cfg["move_notice_days"]
        if self.medium:
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

        # The waitlist in priority order.
        todo = sorted(waiting.values(), key=self.prio)
        if cfg.get("follow_notes"):
            todo.sort(key=lambda r: 0 if r.get("notes") else 1)
        skipped = set()
        if self.hard:
            seen = set()
            upcoming = {(self.req[x]["patient_id"], self.req[x]["department"]) for x in self.appt}
            for r in sorted(waiting.values(), key=lambda r: (r["received"], r["request_id"])):
                key = (r["patient_id"], r["department"])
                if key in seen or key in self.ever or key in upcoming:
                    skipped.add(r["request_id"])
                seen.add(key)
        booked_today = []
        for r in todo:
            rid = r["request_id"]
            if rid in skipped:
                continue
            lo = d + notice if rid in released else d + 1
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
            if f and self.hard:
                other = sorted({a["D"] for x, a in self.appt.items() if self.req[x]["patient_id"] == r["patient_id"]})
                for X in other:
                    if f[1] < X <= f[1] + 2:
                        g = self.find(r, lo, docs, only=X)
                        if g:
                            f = g
                            break
            if f:
                self.place(rid, f[0], f[1], f[2], f[3], d)
                del waiting[rid]
                booked_today.append(rid)

        if self.hard and cfg["overbooked_per_session"] > 0 and not cfg.get("no_overbook"):
            ns = cfg["noshow"]
            thr = cfg.get("ob_threshold", 1.0 - cfg["seen_value"] / cfg["collision_cost"])
            hist = ns["base0"] + ns["slope"] * ns["hist_lead"]
            oracle = cfg.get("oracle_p")

            def p_occ(x, D):
                q = self.req[x]
                if oracle is not None:
                    base = oracle[x]
                else:
                    base = (q["missed_appointments"] + ns["shrink"] * hist) / (q["past_appointments"] + ns["shrink"]) \
                        - ns["slope"] * ns["hist_lead"]
                return base + ns["slope"] * (D - self.appt[x]["booked_on"])

            # Slots holding one follow-up whose patient will probably stay away, per doctor session.
            good, n_ob = {}, {}
            for (doc, D), sessions in self.sess.items():
                if D <= d:
                    continue
                for half, starts in sessions:
                    n_ob[(doc, D, half)] = sum(1 for s in starts if len(self.occ.get((doc, D, s), ())) >= 2)
                    good[(doc, D, half)] = [s for s in starts if len(self.occ.get((doc, D, s), ())) == 1
                                            and self.req[self.occ[(doc, D, s)][0]]["visit_type"] == "follow_up"
                                            and p_occ(self.occ[(doc, D, s)][0], D) > thr]
            for r in todo:
                rid = r["request_id"]
                if rid not in waiting or rid in skipped or r["visit_type"] != "follow_up":
                    continue
                lo = max(d + notice if rid in released else d + 1, wd(r["earliest_date"]))
                doc = r["previous_doctor"]
                hit = None
                for D in range(lo, d + cfg["horizon"] + 1):
                    halves = [(h, good.get((doc, D, h))) for h, _ in self.sess.get((doc, D), ())]
                    if not any(g for _, g in halves) or not self.bookable(doc, D):
                        continue
                    test = None
                    if self.medium and r["pre_visit_test"]:
                        test = self.test_day(r, D)
                        if test is None:
                            continue
                    for half, g in halves:
                        if not g or n_ob[(doc, D, half)] >= cfg["overbooked_per_session"]:
                            continue
                        for s in g:
                            if r["urgency"] != "U" and D >= d + 2 and self.reserve(doc, D, s):
                                continue
                            hit = (doc, D, s, test)
                            g.remove(s)
                            n_ob[(doc, D, half)] += 1
                            break
                        if hit:
                            break
                    if hit:
                        break
                if hit:
                    self.place(rid, hit[0], hit[1], hit[2], hit[3], d)
                    del waiting[rid]

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

        table = self.table(waiting)
        actions += cfg.get("inject", {}).get(str(day["day_index"]), [])
        return {"actions": actions, "status_table": table}

    def table(self, waiting):
        d, cfg = self.d, self.cfg
        out = {}
        for dept in DEPTS:
            free = held = 0
            for doc in self.dept_docs.get(dept, ()):
                for D in range(d + 1, d + cfg["horizon"] + 1):
                    if not self.bookable(doc, D) and not cfg.get("table_calendar_as_is"):
                        continue
                    for half, starts in self.sess.get((doc, D), ()):
                        for s in starts:
                            if self.occ.get((doc, D, s)):
                                continue
                            if D >= d + 2 and self.reserve(doc, D, s) and not cfg.get("table_no_reserve"):
                                held += 1
                            else:
                                free += 1
            rs = [r for r in waiting.values() if r["department"] == dept]
            if self.medium and not cfg.get("table_raw_waitlist"):
                rs = [r for r in rs if not (r["visit_type"] == "new" and r.get("referral_valid_until")
                                            and wd(r["referral_valid_until"]) < d + 1)]
            if self.hard and not cfg.get("table_raw_waitlist"):
                upcoming = {(self.req[x]["patient_id"], self.req[x]["department"]) for x in self.appt}
                n = len({r["patient_id"] for r in rs if (r["patient_id"], dept) not in self.ever
                         and (r["patient_id"], dept) not in upcoming})
            else:
                n = len(rs)
            out[dept] = {"free_slots": free, "held_back": held, "waitlist": n}
        return out


_INSTANCE = None


def on_day(day):
    global _INSTANCE
    if _INSTANCE is None:
        here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(here, "config.json"), encoding="utf-8") as f:
            _INSTANCE = Scheduler(json.load(f))
    return _INSTANCE.on_day(day)
