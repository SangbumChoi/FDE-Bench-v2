"""Reference daily underwriter for finance/loan_underwriting_specialist (copied into program/ with a config.json).

Standard library only. The engine loads this file once and calls on_day(day) once per business day, in
order, in the same process, so the state (what we lent to whom, what is left of the budget, the notices
received) lives in one Underwriter object.

Each day:
  * apply the day's notices the round's rules use (DSR cap change and budget cut from medium; repayments and
    document corrections in hard);
  * decide every new application, and in hard every referred application whose corrected document arrived:
    delinquency -> decline; policy score under the cutoff -> decline; (hard) income discrepancy -> refer;
    short job tenure -> refer (the habit); otherwise a candidate for up to min(requested, customer limit);
  * (hard) one approval per customer per day: the largest of a customer's same-day applications;
  * (alloc "price", the reference) lend at a price: each demand (one customer's applications of the day, or a pair
    of planted twins, so twins get the same answer) is cut into increments of 250 on the upper concave hull of its
    predicted expected profit (a logistic scorecard fitted on the history: score, DSR, inquiries, history length,
    less than a year in the job, and the steeper risk above a 30% DSR and below a score of 800), and the increments
    are taken by profit per unit lent while the day's room lasts: the daily cap and, from medium, the period
    budget paced at a price (the lowest profit per unit lent at which today and the days ahead, if they look like
    the days so far, stay within the budget left);
  * (medium+) the near-prime commitment as a shadow price: a bonus per unit lent near-prime and a malus prime,
    raised by bisection to keep a buffer above the quota where it is cheap and the quota itself every day;
  * give each decline its reason code and report the closing limit table.

The earlier allocation (alloc "greedy": the most profitable amount per candidate, approved most profitable in
total first within a paced allowance, near-prime approvals topped up at the most their limit allows, prime ones
held back when near-prime demand runs short) stays for the baseline and the pilot.

config.json holds the client's rule parameters for the setting and the scorecard; the other switches exist only
so the case can build programs that break one rule each, that misread one client fact each (the ground truth
audit's ablations), that take a shortcut, or the baseline (`first_come`: no scorecard, every eligible application
offered the most its limit allows in order of arrival; `pace` null: no budget pacing; `sizing` off). Without
`features` the scorecard is the pilot program's older one (score, DSR, inquiries, history).
"""

import json
import math
import os

MIN_AMOUNT, MAX_AMOUNT = 1000, 50000
APR, STRESS_APR, TERM = 11.9, 13.4, 36
MARGIN, LGD = 0.10, 0.60
LINE_YEARS = 5
STRESS_THRESHOLD = 60000


def _installment(amount, apr):
    r = apr / 100 / 12
    return amount * r / (1 - (1 + r) ** -TERM)


PER_1000 = round(_installment(1000, APR), 2)               # 33.17, as on the product sheet
PER_1000_STRESSED = round(_installment(1000, STRESS_APR), 2)


PILOT_FEATURES = ("score", "dsr", "inquiries", "history")     # the pilot program's older scorecard


def scorecard_x(names, score_a, dsr, inquiries, history_months, months_in_job, attrs=("", "", "")):
    """The scorecard's inputs: an intercept and the named features (the case fits the same ones on the history).
    attrs = (age band, gender, nationality) feed only the protected features, which the client's rules forbid (the
    case builds a program with them to show what the planted twins catch)."""
    age, gender, nationality = attrs
    f = {"score": (score_a - 760) / 100, "dsr": dsr, "inquiries": float(inquiries),
         "history": math.log(max(history_months, 3) / 60),
         "short_tenure": 1.0 if months_in_job < 12 else 0.0,            # less than a year in the job
         "dsr_over_30": max(0.0, dsr - 0.30),                             # the burden's risk steepens above 30%
         "score_under_800": max(0.0, (800 - score_a) / 100),             # and the score's below 800
         "dsr_over_32": max(0.0, dsr - 0.32), "score_under_820": max(0.0, (820 - score_a) / 100),
         "score_under_690_sq": max(0.0, (690 - score_a) / 100) ** 2,
         "age_under_26": 1.0 if age == "18-25" else 0.0, "age_over_50": 1.0 if age in ("51-65", "66+") else 0.0,
         "female": 1.0 if gender == "female" else 0.0, "foreign": 1.0 if nationality == "foreign" else 0.0}
    return [1.0] + [f[n] for n in names]


def _service(debt):
    if debt["type"] == "installment":
        return 12.0 * debt["monthly_payment"]
    return debt["outstanding_balance"] / LINE_YEARS + debt["outstanding_balance"] * debt["annual_rate_pct"] / 100


class Underwriter:
    def __init__(self, cfg):
        self.cfg = cfg
        self.medium = cfg["tier"] in ("medium", "hard")
        self.hard = cfg["tier"] == "hard"
        # What the round's rules use. Each switch reads one client fact the other way (the case's ablations: the
        # reference misunderstanding only that fact): lines "in" (easy: credit lines in the DSR, as from medium) or
        # "interest" (credit lines at their interest only), stress False, count_bonus (an undocumented bonus counted),
        # verify_income / declared_income, apply_ / ignore_repayments, apply_ / ignore_reg_notice,
        # ignore_budget_notice, forget_lending (our earlier days' lending left out of the limit).
        self.lines = self.medium or cfg.get("lines") in ("in", "interest")
        self.stress = self.medium and cfg.get("stress", True)
        self.verified = (self.hard and not cfg.get("declared_income")) or bool(cfg.get("verify_income"))
        self.use_repayments = (self.hard and not cfg.get("ignore_repayments")) or bool(cfg.get("apply_repayments"))
        self.use_reg = (self.medium and not cfg.get("ignore_reg_notice")) or bool(cfg.get("apply_reg_notice"))
        self.use_budget_notice = self.medium and not cfg.get("ignore_budget_notice")
        self.reset()

    def reset(self):
        self.cust = {}          # customer id -> latest application (profile and bureau snapshot)
        self.repaid = set()     # (customer id, debt id) repaid per a notice (hard)
        self.fixes = {}         # customer id -> {replaced document id: new document} (hard)
        self.lent = {}          # customer id -> our approvals in the period
        self.status = {}        # application id -> latest decision
        self.apps = {}          # application id -> application
        self.spent = 0
        self.near = 0
        self.cap_changes = []   # (effective date, points)
        self.budget_changes = []
        self.curves = []        # each day's demand: (profit per unit lent, amount) of its increments (pace "price")

    # ── the policy's reading of a customer ─────────────────────────────────
    def score(self, c):
        return c["bureau"]["bureau_a_score" if self.cfg["policy_bureau"] == "A" else "bureau_b_score"]

    def eligible(self, c):
        return not c["bureau"]["active_delinquency"] and self.score(c) >= self.cfg["min_score"]

    def near_prime(self, c):
        return self.score(c) < self.cfg["near_prime_below"]

    def debts(self, c, policy=True):
        cid = c["customer_id"]
        debts = c["existing_debts"]
        if self.use_repayments or not policy:
            debts = [x for x in debts if (cid, x["debt_id"]) not in self.repaid]
        if policy and not self.lines:
            debts = [x for x in debts if x["type"] == "installment"]
        return debts

    def service(self, debt):
        """A debt's annual service in the policy's DSR."""
        if debt["type"] == "credit_line" and self.cfg.get("lines") == "interest":
            return debt["outstanding_balance"] * debt["annual_rate_pct"] / 100
        return _service(debt)

    def base(self, c, policy=True):
        if policy and not self.verified:
            return c["monthly_base_salary"]
        fix = self.fixes.get(c["customer_id"], {}) if not self.cfg.get("ignore_corrections") else {}
        shown = [fix.get(x["document_id"], x)["monthly_base_salary_shown"] for x in c["income_documents"]]
        return min([c["monthly_base_salary"]] + shown)

    def income(self, c, policy=True):
        bonus = c["bonus_documented"] or (policy and self.cfg.get("count_bonus"))
        return 12 * self.base(c, policy) + (c["annual_bonus"] if bonus else 0)

    def discrepant(self, c):
        """The fraud-prevention check reads the documents whatever salary the limits use (declared_income misreads
        only the latter)."""
        declared = c["monthly_base_salary"]
        return self.hard and declared - self.base(c, policy=False) > self.cfg["discrepancy_pct"] / 100 * declared + 1e-9

    def dsr_cap_pct(self):
        return self.cfg["max_dsr_pct"] + (sum(p for d, p in self.cap_changes if d <= self.date) if self.use_reg else 0)

    def budget(self):
        b = self.cfg["period_budget"] + sum(x for d, x in self.budget_changes if d <= self.date)
        return b * self.cfg.get("budget_scale", 1.0)

    def ours(self, cid, extra=0):
        """Our lending to the customer that the customer limit counts: everything approved in the period plus
        `extra` (today's approvals); forget_lending counts only `extra`."""
        return (0 if self.cfg.get("forget_lending") else self.lent.get(cid, 0)) + extra

    def dsr(self, c, ours, terms):
        income, service, balances = terms
        stressed = self.stress and balances + ours > STRESS_THRESHOLD
        return (service + 12.0 * (PER_1000_STRESSED if stressed else PER_1000) * ours / 1000) / income

    def limit(self, c, lent):
        """Largest whole amount the customer may still borrow after `lent` of our lending (negative if over)."""
        debts = self.debts(c)
        terms = (self.income(c), sum(self.service(x) for x in debts), sum(x["outstanding_balance"] for x in debts))
        top = min(MAX_AMOUNT, terms[0] * self.cfg["income_cap_pct"] // 100) - lent
        cap = self.dsr_cap_pct() / 100 + 1e-9
        if top < 0 or self.dsr(c, lent, terms) > cap:
            return min(top, -1)
        if self.dsr(c, lent + top, terms) <= cap:
            return top
        lo, hi = 0, top
        while hi - lo > 1:
            mid = (lo + hi) // 2
            lo, hi = (mid, hi) if self.dsr(c, lent + mid, terms) <= cap else (lo, mid)
        return lo

    # ── the scorecard ───────────────────────────────────────────────────────
    def pd(self, c, total):
        """Predicted lifetime default probability with `total` of our lending outstanding to the customer."""
        debts = self.debts(c, policy=False)
        dsr = (sum(_service(x) for x in debts) + 12.0 * _installment(total, APR)) / self.income(c, policy=False)
        b = c["bureau"]
        x = scorecard_x(self.cfg.get("features", PILOT_FEATURES), b["bureau_a_score"], dsr, b["inquiries_6m"],
                        b["credit_history_months"], c["months_in_job"], (c["age_band"], c["gender"], c["nationality"]))
        z = sum(w * v for w, v in zip(self.cfg["beta"], x))
        return 1 / (1 + math.exp(-z))

    @staticmethod
    def signature(a):
        """Everything but the ids and the protected attributes (planted twins share it)."""
        return json.dumps([a["requested_amount"], a["months_in_job"], a["monthly_base_salary"], a["annual_bonus"],
                           a["bonus_documented"], a["bureau"],
                           sorted((x["type"], x["outstanding_balance"], x.get("monthly_payment"),
                                   x.get("annual_rate_pct"), x.get("credit_limit")) for x in a["existing_debts"]),
                           sorted((x["type"], x["monthly_base_salary_shown"]) for x in a["income_documents"])],
                          sort_keys=True)

    # ── one day ─────────────────────────────────────────────────────────────
    def on_day(self, day):
        cfg = self.cfg
        d = day["day_index"]
        if d == 0:
            self.reset()
        self.date = day["date"]
        corrected = []
        for n in day.get("notices", []):
            if n["type"] == "regulation_change" and self.use_reg:
                self.cap_changes.append((n["effective_date"], n["dsr_cap_change_points"]))
            elif n["type"] == "budget_change" and self.use_budget_notice:
                self.budget_changes.append((n["effective_date"], n["period_budget_change"]))
            elif n["type"] == "repayment" and self.use_repayments:
                self.repaid.add((n["customer_id"], n["debt_id"]))
            elif (n["type"] == "document_correction" and (self.verified or self.hard)     # hard: the fraud check
                  and not cfg.get("ignore_corrections")):                                  # reads the documents too
                self.fixes.setdefault(n["customer_id"], {})[n["replaces_document_id"]] = n["document"]
                if self.hard and cfg.get("redecide", True):
                    corrected.append(n["application_id"])
        for a in day["applications"]:
            self.cust[a["customer_id"]] = a
            self.apps[a["application_id"]] = a
        todo = list(day["applications"]) + [self.apps[x] for x in corrected if self.status.get(x) == "refer"]

        decision = {}
        cands = []
        for a in todo:
            c = self.cust[a["customer_id"]]
            if a["bureau"]["active_delinquency"]:
                decision[a["application_id"]] = "decline"
            elif self.discrepant(c):
                decision[a["application_id"]] = "refer"
            elif cfg.get("tenure_review", True) and a["months_in_job"] < cfg["min_tenure"]:
                decision[a["application_id"]] = "refer"
            elif self.score(a) < cfg["min_score"]:
                decision[a["application_id"]] = "decline"
            else:
                cands.append(a)
        if cfg.get("approve_nothing") or cfg.get("refer_all"):     # shortcuts, see the case
            cands = []
            if cfg.get("refer_all"):
                decision.update({a["application_id"]: "refer" for a in todo if not a["bureau"]["active_delinquency"]})
        if self.hard and cfg.get("split_rule", True):       # one approval per customer per day
            best = {}
            for a in sorted(cands, key=lambda a: (-a["requested_amount"], a["application_id"])):
                best.setdefault(a["customer_id"], a)
            for a in cands:
                if best[a["customer_id"]] is not a:
                    decision[a["application_id"]] = "decline"
            cands = [a for a in cands if best[a["customer_id"]] is a]
        today, pre = {}, {}
        if cfg.get("honor_notes"):
            # Misread: a branch manager's note is honoured when the rules allow it, as the head of credit's exception
            # to the tenure habit: the full requested amount, within the customer limit (else decided as usual).
            for a in todo:
                aid, cid = a["application_id"], a["customer_id"]
                c = self.cust[cid]
                if (a.get("notes") and not a["bureau"]["active_delinquency"] and not self.discrepant(c)
                        and self.score(a) >= cfg["min_score"]
                        and a["requested_amount"] <= self.limit(c, self.ours(cid, today.get(cid, 0)))):
                    pre[aid] = a["requested_amount"]
                    today[cid] = today.get(cid, 0) + pre[aid]
                    decision.pop(aid, None)
            cands = [a for a in cands if a["application_id"] not in pre]

        groups, nth = {}, {}
        for a in sorted(cands, key=lambda a: a["application_id"]):
            # twins are two customers: one customer's equal same-day applications (a split need) are not one unit
            key = (self.signature(a), a["customer_id"])
            nth[key] = nth.get(key, -1) + 1
            # twins False (an ablation): every customer its own unit, as if no pair were planted
            groups.setdefault((key[0], nth[key]) if cfg.get("twins", True) else key + (nth[key],), []).append(a)
        units = list(groups.values())

        def offer(unit, sized=True):
            amt = min(min(a["requested_amount"], self.limit(self.cust[a["customer_id"]],
                                                            self.ours(a["customer_id"], today.get(a["customer_id"], 0))))
                      for a in unit)
            if sized and cfg.get("sizing") and amt >= MIN_AMOUNT:    # the most profitable amount (250 steps)
                amt = max(range(amt, MIN_AMOUNT - 1, -250), key=lambda x: (value(unit, x), x))
            return amt

        first_come = cfg.get("first_come")    # the baseline: no scorecard, in order of arrival

        def value(unit, amt):
            a = unit[0]
            c = self.cust[a["customer_id"]]
            total = self.lent.get(a["customer_id"], 0) + today.get(a["customer_id"], 0) + amt
            return len(unit) * amt * (MARGIN - (0.0 if first_come else LGD * self.pd(c, total)))

        est = {id(u): value(u, max(offer(u), 0)) for u in units}

        def rank(u):
            return (u[0]["application_id"],) if first_come else (-est[id(u)], u[0]["application_id"])
        room = cfg["daily_cap"]
        self.days_in_period, self.day_index = day["days_in_period"], d
        if self.medium:
            left = max(0.0, self.budget() - self.spent)
            days_left = day["days_in_period"] - d
            unpaced = days_left <= 1 or cfg["pace"] is None or cfg["pace"] == "price"     # "price": paced_room
            room = min(room, left if unpaced else left / days_left * cfg["pace"])
        flood = str(d) in cfg.get("flood_days", [])     # validator example only: ignore the daily cap
        room = int(room) - sum(pre.values()) if not flood else 10 ** 9
        approved = {}            # id(unit) -> (unit, amount each)

        def take(unit, amt):
            approved[id(unit)] = (unit, amt)
            for a in unit:
                today[a["customer_id"]] = today.get(a["customer_id"], 0) + amt
            return amt * len(unit)

        def drop(unit):
            _, amt = approved.pop(id(unit))
            for a in unit:
                today[a["customer_id"]] -= amt
            return amt * len(unit)

        if cfg.get("alloc") == "price" and not first_come:
            amounts = self.price_alloc(units, room, flood)
            for aid, amt in amounts.items():
                cid = self.apps[aid]["customer_id"]
                today[cid] = today.get(cid, 0) + amt
            units = []          # the greedy pass and its quota steps below have nothing left to do
        else:
            amounts = None
        for u in sorted(units, key=rank):
            amt = offer(u)
            if amt < MIN_AMOUNT or (value(u, amt) <= 0 and not flood):
                continue
            if amt * len(u) > room:
                amt = room // len(u)
                if amt < MIN_AMOUNT or value(u, amt) <= 0:
                    continue
            room -= take(u, amt)

        if self.medium and cfg.get("quota", True) and amounts is None:
            target = cfg["quota_pct"] / 100 + cfg["quota_margin"]

            def share():
                tot = self.spent + sum(amt * len(u) for u, amt in approved.values())
                near = self.near + sum(amt * len(u) for u, amt in approved.values()
                                       if self.near_prime(self.cust[u[0]["customer_id"]]))
                return near / tot if tot else 1.0
            pool = [u for u in sorted(units, key=rank)
                    if id(u) not in approved and self.near_prime(self.cust[u[0]["customer_id"]])]
            while share() < target and pool:
                u = pool[0]
                amt = offer(u, sized=False)        # a top-up is for the volume: the most the limit allows
                if amt < MIN_AMOUNT:
                    pool.pop(0)
                    continue
                if amt * len(u) > room:
                    victims = [v for v, _ in approved.values()
                               if not self.near_prime(self.cust[v[0]["customer_id"]])]
                    if victims:
                        room += drop(min(victims, key=lambda v: (value(v, approved[id(v)][1]),
                                                                v[0]["application_id"])))
                        continue
                    amt = room // len(u)
                    if amt < MIN_AMOUNT:
                        break
                room -= take(u, amt)
                pool.pop(0)
            # Too little near-prime demand today: hold back prime approvals (the least profitable first) rather
            # than end the day under the quota itself and count on later days' near-prime demand (or budget).
            floor = cfg["quota_pct"] / 100 + cfg.get("hold_margin", 0.002)
            while cfg.get("quota_hold", True) and share() < floor:
                victims = [v for v, _ in approved.values() if not self.near_prime(self.cust[v[0]["customer_id"]])]
                if not victims:
                    break
                room += drop(min(victims, key=lambda v: (value(v, approved[id(v)][1]), v[0]["application_id"])))

        if amounts is None:
            amounts = {a["application_id"]: amt for u, amt in approved.values() for a in u}
        amounts.update(pre)
        for a in todo:
            aid = a["application_id"]
            decision[aid] = "approve" if aid in amounts else decision.get(aid, "decline")
        codes = {}
        for aid, v in cfg.get("overrides", {}).get(str(d), {}).items():
            a = self.apps[aid]
            if decision.get(aid) == "approve":
                today[a["customer_id"]] -= amounts.pop(aid)
            if v[0] == "omit":
                decision.pop(aid, None)
                continue
            decision[aid] = v[0]
            if v[0] == "approve":
                amounts[aid] = int(v[1])
                today[a["customer_id"]] = today.get(a["customer_id"], 0) + int(v[1])
            elif len(v) > 1:
                codes[aid] = v[1]

        out = []
        for a in todo:
            aid, cid = a["application_id"], a["customer_id"]
            if aid not in decision:
                continue
            dd = decision[aid]
            row = {"application_id": aid, "decision": dd, "amount": amounts.get(aid, 0), "reason_code": ""}
            if dd == "decline":
                row["reason_code"] = codes.get(aid) or self.driver(a, today, amounts)
                if cfg.get("refer_declines") and row["reason_code"] != "DELINQUENCY":    # a shortcut, see the case
                    row.update(decision="refer", reason_code="")
            out.append(row)
        for row in out:
            self.status[row["application_id"]] = row["decision"]
        for aid, amt in amounts.items():
            cid = self.apps[aid]["customer_id"]
            self.lent[cid] = self.lent.get(cid, 0) + amt
            self.spent += amt
            if self.near_prime(self.cust[cid]):
                self.near += amt
        total = sum(amounts.values())
        return {"decisions": out, "limit_table": self.table(day, today, total)}

    def table(self, day, today, total):
        """The closing limit table. Misreadings (the case's ablations and shortcuts), cfg "table": "morning" (the
        limits before the day's approvals; with "table_bank": "closing" the bank figures still after them),
        "today" (only the day's applicants), "formula" (the formula limit also for a delinquent or below-cutoff
        customer), "zeros" (every customer 0), "approved_zero" (0 for every customer approved today), "empty";
        cfg "jitter" moves every customer entry by 1 on odd days (within the tolerance)."""
        mode = self.cfg.get("table", "closing")
        if mode == "empty":
            return {"customers": {}}
        morning = mode == "morning"
        who = {a["customer_id"] for a in day["applications"]} if mode == "today" else self.cust
        customers = {}
        for cid in sorted(who):
            c, mine = self.cust[cid], today.get(cid, 0)          # self.lent already holds today's approvals
            counted = mine if self.cfg.get("forget_lending") else self.lent.get(cid, 0)
            room = self.limit(c, counted - mine if morning else counted)
            customers[cid] = max(0, room) if self.eligible(c) or mode == "formula" else 0
            if mode == "zeros" or (mode == "approved_zero" and mine > 0):
                customers[cid] = 0
            customers[cid] += day["day_index"] % 2 if self.cfg.get("jitter") else 0
        drop = self.cfg.get("table_drop")          # validator example: one customer left out on one day
        if drop and str(day["day_index"]) == drop[0]:
            customers.pop(drop[1], None)
        morning_bank = morning and self.cfg.get("table_bank") != "closing"
        budget = self.budget() / self.cfg.get("budget_scale", 1.0) - self.spent + (total if morning_bank else 0)
        return {"customers": customers,
                "daily_capacity_remaining": (self.cfg["daily_cap"] if morning_bank
                                             else max(0, self.cfg["daily_cap"] - total)),
                "period_budget_remaining": max(0, int(budget)) if self.medium else None}

    # ── the day's allocation at a price (the reference) ─────────────────────
    def price_alloc(self, units, room, flood):
        """{application id: amount}: the day's lending as a knapsack with concave values. Each demand (one
        customer's applications of the day together, or a pair of planted twins) is cut into increments of `step`
        on the upper concave hull of its predicted expected profit; the increments are taken in order of profit per
        unit lent while the day's room lasts, so a large loan of thin margin never crowds out several richer small
        ones. From medium a near-prime bonus lam (a prime malus) per unit lent is raised, by bisection, until the
        period's running near-prime share stays at the quota plus a margin: it tops up near-prime lending where
        that costs least and holds back the thinnest prime lending (the quota's shadow price)."""
        cfg = self.cfg
        step = int(cfg.get("step", 250))
        margin, lgd = cfg.get("margin", MARGIN), cfg.get("lgd", LGD)
        q = cfg.get("quota_pct", 0) / 100
        demands, mine = [], {}
        for u in units:
            cids = sorted({a["customer_id"] for a in u})
            if len(cids) == 1 and cids[0] in mine:          # another application of the customer today
                mine[cids[0]]["apps"][cids[0]].extend(u)
                continue
            dmd = {"cids": cids, "apps": {cid: [a for a in u if a["customer_id"] == cid] for cid in cids}}
            demands.append(dmd)
            if len(cids) == 1:
                mine[cids[0]] = dmd
        plans = []
        for dmd in demands:
            top = min(min(sum(a["requested_amount"] for a in apps), self.limit(self.cust[cid], self.ours(cid)))
                      for cid, apps in dmd["apps"].items())
            if top < MIN_AMOUNT:
                continue
            k, cid = len(dmd["cids"]), dmd["cids"][0]
            c, lent = self.cust[cid], self.lent.get(cid, 0)
            pts = [(0, 0.0)] + [(x, k * x * (margin - lgd * self.pd(c, lent + x)))
                                for x in list(range(MIN_AMOUNT, top, step)) + [top]]
            hull = [pts[0]]
            for p in pts[1:]:                               # upper concave hull from (0, 0)
                while len(hull) >= 2 and ((hull[-1][1] - hull[-2][1]) * (p[0] - hull[-1][0])
                                          <= (p[1] - hull[-1][1]) * (hull[-1][0] - hull[-2][0])):
                    hull.pop()
                hull.append(p)
            incs = [(x0, x1, (v1 - v0) / (k * (x1 - x0))) for (x0, v0), (x1, v1) in zip(hull, hull[1:])]
            plans.append((dmd, k, self.near_prime(c), incs, dict(pts)))

        def alloc(lam):
            items = []
            for i, (_, k, near, incs, _) in enumerate(plans):
                bonus = lam * ((1 - q) if near else -q)
                for j, (_, _, dens) in enumerate(incs):
                    if dens + bonus <= 0 and not flood:
                        break
                    items.append((-(dens + bonus), i, j))
            items.sort()
            got, left, frozen = [0] * len(plans), room, set()
            for _, i, j in items:
                if i in frozen:
                    continue
                _, k, _, incs, pts = plans[i]
                x0, x1, _ = incs[j]
                if got[i] != x0:
                    continue
                if k * (x1 - x0) <= left:
                    got[i], left = x1, left - k * (x1 - x0)
                    continue
                frozen.add(i)                               # the room runs out inside this increment
                x = x0 + left // k
                if x >= MIN_AMOUNT and (x0 or flood or margin - lgd * self.pd(self.cust[plans[i][0]["cids"][0]],
                                                                               self.lent.get(plans[i][0]["cids"][0], 0)
                                                                               + x) > 0):
                    got[i], left = x, left - k * (x - x0)
            return got

        def share(got):
            tot = self.spent + sum(k * g for (_, k, _, _, _), g in zip(plans, got))
            near = self.near + sum(k * g for (_, k, n, _, _), g in zip(plans, got) if n)
            return near / tot if tot else 1.0

        if self.medium and cfg.get("pace") == "price" and not flood:
            room = self.paced_room(plans, room)

        def price_for(target, top):
            """The lowest near-prime bonus up to `top` that brings the running share to `target` (top if none)."""
            if share(alloc(0.0)) >= target:
                return 0.0
            lo, hi = 0.0, top
            if share(alloc(hi)) >= target:
                for _ in range(int(cfg.get("bisect", 14))):
                    mid = (lo + hi) / 2
                    lo, hi = (lo, mid) if share(alloc(mid)) >= target else (mid, hi)
            return hi

        lam = 0.0
        if self.medium and cfg.get("quota", True) and q > 0:
            # A buffer above the quota where it is cheap (the bonus capped)
            lam = min(price_for(q + cfg["quota_margin"], 1.0), cfg.get("buffer_price", 1.0))
            # and the quota itself kept every day at any price (later days may bring too little near-prime demand
            # to catch up).
            if cfg.get("quota_hold", True):
                lam = max(lam, price_for(q + cfg.get("hold_margin", 0.002), 1.0))
        got = alloc(lam)
        amounts = {}
        for (dmd, _, _, _, _), g in zip(plans, got):
            if g < MIN_AMOUNT:
                continue
            for cid in dmd["cids"]:                         # one customer's applications: the largest first
                rest = g
                for a in sorted(dmd["apps"][cid], key=lambda a: (-a["requested_amount"], a["application_id"])):
                    part = min(a["requested_amount"], rest)
                    if part < MIN_AMOUNT:
                        break
                    amounts[a["application_id"]] = part
                    rest -= part
        return amounts

    def paced_room(self, plans, room):
        """The day's room under the period budget, at a price: the lowest profit per unit lent nu at which today's
        lending plus that of each remaining day, if the days ahead look like the days so far (today included), stays
        within the budget left; today lends what is worth at least nu (within the daily cap)."""
        cap = self.cfg["daily_cap"]
        curve = sorted(((dens, k * (x1 - x0)) for _, k, _, incs, _ in plans for x0, x1, dens in incs if dens > 0),
                       reverse=True)
        self.curves.append(curve)
        days_left = self.days_in_period - self.day_index
        left = max(0.0, self.budget() - self.spent)
        if days_left <= 1:
            return room

        def take(c, nu):
            return min(cap, sum(s for dens, s in c if dens >= nu))

        def need(nu):
            return take(curve, nu) + (days_left - 1) * sum(take(c, nu) for c in self.curves) / len(self.curves)
        if need(0.0) <= left:
            return room
        lo, hi = 0.0, self.cfg.get("margin", MARGIN)
        for _ in range(20):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if need(mid) > left else (lo, mid)
        return min(room, int(take(curve, hi)))

    def driver(self, a, today, amounts):
        """The reason code of a decline, after the day's approvals."""
        cid = a["customer_id"]
        c = self.cust[cid]
        if a["bureau"]["active_delinquency"]:
            return "DELINQUENCY"
        if self.score(a) < self.cfg["min_score"]:
            return "LOW_SCORE"
        if self.hard and any(self.apps[x]["customer_id"] == cid for x in amounts if x != a["application_id"]):
            return "SPLIT_APPLICATION"
        left = self.limit(c, self.ours(cid, today.get(cid, 0)))
        if self.cfg.get("codes") == "requested":     # misread: the request above what is left
            return "LIMIT_EXCEEDED" if a["requested_amount"] > left else "CREDIT_RISK"
        if left < MIN_AMOUNT:
            return "LIMIT_EXCEEDED"
        return "CREDIT_RISK"


_INSTANCE = None


def on_day(day):
    global _INSTANCE
    if _INSTANCE is None:
        here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(here, "config.json"), encoding="utf-8") as f:
            _INSTANCE = Underwriter(json.load(f))
    return _INSTANCE.on_day(day)
