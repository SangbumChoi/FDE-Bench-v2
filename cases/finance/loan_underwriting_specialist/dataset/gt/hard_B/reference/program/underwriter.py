"""Reference daily underwriter for finance/loan_underwriting_specialist (copied into program/ with a config.json).

Standard library only. The engine loads this file once and calls on_day(day) once per business day, in
order, in the same process, so the state (what we lent to whom, what is left of the budget, the notices
received) lives in one Underwriter object.

Each day:
  * apply the day's notices the round's rules use (DSR cap change and budget cut from medium; repayments and
    document corrections in hard);
  * decide every new application, and in hard every referred application whose corrected document arrived:
    delinquency -> decline; policy score under the cutoff -> decline; (hard) income discrepancy -> refer;
    short job tenure -> refer (the habit); otherwise a candidate for min(requested, customer limit);
  * (hard) one approval per customer per day: the largest of a customer's same-day applications;
  * approve candidates whose predicted expected profit (a logistic scorecard fitted on the history) is
    positive, most profitable first, within the day's allowance: the daily cap and, from medium, the period
    budget paced over the days left; planted twins (same application apart from protected attributes) are
    one unit, so they get the same answer;
  * (medium+) top up near-prime approvals until the cumulative near-prime share is above the quota;
  * give each decline its reason code and report the closing limit table.

config.json holds the client's rule parameters for the setting and the scorecard; a few switches exist only
so the case can build programs that break one rule each.
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


def _service(debt):
    if debt["type"] == "installment":
        return 12.0 * debt["monthly_payment"]
    return debt["outstanding_balance"] / LINE_YEARS + debt["outstanding_balance"] * debt["annual_rate_pct"] / 100


class Underwriter:
    def __init__(self, cfg):
        self.cfg = cfg
        self.medium = cfg["tier"] in ("medium", "hard")
        self.hard = cfg["tier"] == "hard"
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
        if self.hard or not policy:
            debts = [x for x in debts if (cid, x["debt_id"]) not in self.repaid]
        if policy and not self.medium:
            debts = [x for x in debts if x["type"] == "installment"]
        return debts

    def base(self, c, policy=True):
        if policy and not self.hard:
            return c["monthly_base_salary"]
        fix = self.fixes.get(c["customer_id"], {}) if not self.cfg.get("ignore_corrections") else {}
        shown = [fix.get(x["document_id"], x)["monthly_base_salary_shown"] for x in c["income_documents"]]
        return min([c["monthly_base_salary"]] + shown)

    def income(self, c, policy=True):
        return 12 * self.base(c, policy) + (c["annual_bonus"] if c["bonus_documented"] else 0)

    def discrepant(self, c):
        declared = c["monthly_base_salary"]
        return self.hard and declared - self.base(c) > self.cfg["discrepancy_pct"] / 100 * declared + 1e-9

    def dsr_cap_pct(self):
        return self.cfg["max_dsr_pct"] + (sum(p for d, p in self.cap_changes if d <= self.date) if self.medium else 0)

    def budget(self):
        b = self.cfg["period_budget"] + sum(x for d, x in self.budget_changes if d <= self.date)
        return b * self.cfg.get("budget_scale", 1.0)

    def dsr(self, c, ours, terms):
        income, service, balances = terms
        stressed = self.medium and balances + ours > STRESS_THRESHOLD
        return (service + 12.0 * (PER_1000_STRESSED if stressed else PER_1000) * ours / 1000) / income

    def limit(self, c, lent):
        """Largest whole amount the customer may still borrow after `lent` of our lending (negative if over)."""
        debts = self.debts(c)
        terms = (self.income(c), sum(_service(x) for x in debts), sum(x["outstanding_balance"] for x in debts))
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
        x = [1.0, (b["bureau_a_score"] - 760) / 100, dsr, float(b["inquiries_6m"]),
             math.log(max(b["credit_history_months"], 3) / 60)]
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
            if n["type"] == "regulation_change" and self.medium:
                self.cap_changes.append((n["effective_date"], n["dsr_cap_change_points"]))
            elif n["type"] == "budget_change" and self.medium:
                self.budget_changes.append((n["effective_date"], n["period_budget_change"]))
            elif n["type"] == "repayment" and self.hard:
                self.repaid.add((n["customer_id"], n["debt_id"]))
            elif n["type"] == "document_correction" and self.hard and not cfg.get("ignore_corrections"):
                self.fixes.setdefault(n["customer_id"], {})[n["replaces_document_id"]] = n["document"]
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
        if self.hard and cfg.get("split_rule", True):       # one approval per customer per day
            best = {}
            for a in sorted(cands, key=lambda a: (-a["requested_amount"], a["application_id"])):
                best.setdefault(a["customer_id"], a)
            for a in cands:
                if best[a["customer_id"]] is not a:
                    decision[a["application_id"]] = "decline"
            cands = [a for a in cands if best[a["customer_id"]] is a]

        groups = {}
        for a in sorted(cands, key=lambda a: a["application_id"]):
            groups.setdefault(self.signature(a), []).append(a)
        units = list(groups.values())
        today = {}

        def offer(unit):
            amt = min(min(a["requested_amount"], self.limit(self.cust[a["customer_id"]],
                                                            self.lent.get(a["customer_id"], 0)
                                                            + today.get(a["customer_id"], 0))) for a in unit)
            if cfg.get("sizing") and amt >= MIN_AMOUNT:    # off in the reference: the most profitable amount
                amt = max(range(amt, MIN_AMOUNT - 1, -250), key=lambda x: (value(unit, x), x))
            return amt

        def value(unit, amt):
            a = unit[0]
            c = self.cust[a["customer_id"]]
            total = self.lent.get(a["customer_id"], 0) + today.get(a["customer_id"], 0) + amt
            return len(unit) * amt * (MARGIN - LGD * self.pd(c, total))

        est = {id(u): value(u, max(offer(u), 0)) for u in units}
        room = cfg["daily_cap"]
        if self.medium:
            left = max(0.0, self.budget() - self.spent)
            days_left = day["days_in_period"] - d
            room = min(room, left if days_left <= 1 else left / days_left * cfg["pace"])
        flood = str(d) in cfg.get("flood_days", [])     # validator example only: ignore the daily cap
        room = int(room) if not flood else 10 ** 9
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

        for u in sorted(units, key=lambda u: (-est[id(u)], u[0]["application_id"])):
            amt = offer(u)
            if amt < MIN_AMOUNT or (value(u, amt) <= 0 and not flood):
                continue
            if amt * len(u) > room:
                amt = room // len(u)
                if amt < MIN_AMOUNT or value(u, amt) <= 0:
                    continue
            room -= take(u, amt)

        if self.medium and cfg.get("quota", True):
            target = cfg["quota_pct"] / 100 + cfg["quota_margin"]

            def share():
                tot = self.spent + sum(amt * len(u) for u, amt in approved.values())
                near = self.near + sum(amt * len(u) for u, amt in approved.values()
                                       if self.near_prime(self.cust[u[0]["customer_id"]]))
                return near / tot if tot else 1.0
            pool = [u for u in sorted(units, key=lambda u: (-est[id(u)], u[0]["application_id"]))
                    if id(u) not in approved and self.near_prime(self.cust[u[0]["customer_id"]])]
            while share() < target and pool:
                u = pool[0]
                amt = offer(u)
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

        amounts = {a["application_id"]: amt for u, amt in approved.values() for a in u}
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
        customers = {cid: (max(0, self.limit(c, self.lent.get(cid, 0))) if self.eligible(c) else 0)
                     for cid, c in sorted(self.cust.items())}
        table = {"customers": customers, "daily_capacity_remaining": max(0, cfg["daily_cap"] - total),
                 "period_budget_remaining": max(0, int(self.budget() / cfg.get("budget_scale", 1.0) - self.spent))
                 if self.medium else None}
        return {"decisions": out, "limit_table": table}

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
        if self.limit(c, self.lent.get(cid, 0) + today.get(cid, 0)) < MIN_AMOUNT:
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
