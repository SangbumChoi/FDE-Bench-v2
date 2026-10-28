"""Daily personal-loan underwriting with limits (original FDE-Bench v2 case).

A lender's credit team wants a program that underwrites its one unsecured personal loan (PL36) day by day.
Over a period of 20 business days new applications arrive every day; the agent delivers
`underwriter.py:on_day(day)`, which the evaluator calls once per day, in order, in one isolated process
(casekit.program_session), on a HIDDEN future period. Each call gets that day's applications, that day's
notices and the loans approved so far; it returns a decision (approve / decline / refer, amount, reason
code) for every application to decide, and the day's closing limit table: what each customer seen so far
may still borrow, and what is left of the bank's daily disbursement capacity and period budget.

The key of the case is keeping every approval within the day's limits and getting the limit table right.
Quality = 0.7 x expected profit / the reference program's expected profit + 0.3 x limit-table accuracy.

One world and one hidden period for every setting: the same customers, applications, branch notes and
notices. The tier decides which rules are in force:

  easy    the core: one product PL36; income = 12 x declared base salary + documented bonus; one bureau is
          the policy score with a cutoff; active delinquency declined; customer limit = min(product max,
          income cap, DSR headroom counting installment loans only) minus what we lent the customer earlier
          in the period (and earlier the same day); a daily disbursement cap; ordered decline reason codes;
          protected attributes never used (planted twins); the tenure referral habit (bendable). Notices are
          out of scope this round.
  medium  + credit lines in the DSR, the stress add-on, a cumulative near-prime quota, the period budget, and
          two notices: a regulatory DSR cut from a given day and a budget cut
  hard    + income verification (documents; a large discrepancy must be referred), document corrections
          (a referred application must be decided again the day its corrected document arrives),
          repayment notices that restore headroom, and split applications (one approval per customer per
          day). Branch managers' "approve the maximum" notes on some applications must be ignored in every
          tier: following them breaks a limit.

The rule set (A / B / C) sets the parameters: the policy bureau and its cutoff, the near-prime threshold,
the DSR cap, the income cap, the daily cap, the period budget, the quota, the discrepancy threshold and the
tenure habit.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
import math
import random
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

from fdebench2.casekit import Fatal, labels, program_session, write_csv, write_xlsx

ENTRYPOINT = "underwriter.py:on_day"
REFERENCE = Path(__file__).resolve().parent / "reference" / "underwriter.py"

# ── the product and the credit policy (known to the client only) ─────────────

PRODUCT = "PL36"
TERM = 36                 # months
APR = 11.9                # % per year
STRESS_APR = 13.4         # medium+: the new loans' rate in the DSR above the stress threshold
MIN_AMOUNT, MAX_AMOUNT = 1000, 50000
MARGIN = 0.10             # lifetime margin on the approved amount
LGD = 0.60
REFER_COST = 60.0
LINE_YEARS = 5            # medium+: credit lines count as their balance repaid over 5 years plus interest
STRESS_THRESHOLD = 60000  # medium+: total unsecured debt after the loan above this -> stressed rate
PROFIT_WEIGHT, TABLE_WEIGHT = 0.7, 0.3

N_HISTORY = 3000
N_DAYS = 20
FIRST_DAY = dt.date(2026, 11, 2)     # a Monday
N_TWINS = 14
N_SPLITS = 12
N_RETURNING = 45
N_CORRECTIONS = 8
N_REPAY_SAME_DAY, N_REPAY_LATER = 7, 8
N_PRESSURE = 10
REG_NOTICE_DAY, REG_DAY, REG_CUT = 6, 10, 5     # medium+: DSR cap 5 points lower for decisions from day 10
BUDGET_CUT_DAY, BUDGET_CUT = 13, 400000          # medium+: the period budget is cut by 400,000 from day 13
CALL_TIMEOUT = 10.0
TOTAL_TIMEOUT = 600.0
TOL = 0.01
CODES = ("DELINQUENCY", "LOW_SCORE", "SPLIT_APPLICATION", "LIMIT_EXCEEDED", "CREDIT_RISK")


def installment(amount: float, apr: float = APR) -> float:
    """Monthly installment of a fully amortizing loan over TERM months (the economics)."""
    r = apr / 100 / 12
    return amount * r / (1 - (1 + r) ** -TERM)


def per_1000(apr: float = APR) -> float:
    """The installment per 1,000 as the product sheet states it (the policy's DSR uses this figure)."""
    return round(installment(1000, apr), 2)


@dataclass
class Debt:
    kind: str            # installment | credit_line
    balance: int
    monthly_payment: int = 0     # installment loans
    rate: float = 0.0            # credit lines, % per year
    line_limit: int = 0          # credit lines
    id: str = ""

    @property
    def annual_service(self) -> float:
        if self.kind == "installment":
            return 12.0 * self.monthly_payment
        return self.balance / LINE_YEARS + self.balance * self.rate / 100


@dataclass
class Doc:
    kind: str            # payslip | employer_letter
    base_salary: int     # monthly base salary shown on the document
    id: str = ""


@dataclass
class App:
    """A person's profile (one per past loan in the history; one per customer in the period)."""

    id: str
    date: str
    requested: int
    age_band: str
    gender: str
    nationality: str
    tenure: int                  # months in the current job
    base_salary: int             # monthly, as declared (verified in the history)
    bonus: int                   # annual
    bonus_documented: bool
    stated_income: int           # monthly, self-declared, never used
    score_a: int                 # bureau A, 0-1000 (the true risk follows it)
    score_b: int                 # bureau B, 0-1000 (runs ~55 higher, noisier)
    inquiries: int
    history_months: int
    delinquent: bool
    debts: list[Debt] = field(default_factory=list)
    funded: int = 0              # history only
    defaulted: bool = False      # history only
    twin_of: str = ""            # period: the customer this one is the audit twin of
    docs: list[Doc] = field(default_factory=list)   # period only
    person: str = ""             # bureau file number = customer id
    true_base: int = 0           # period: the real monthly base salary

    @property
    def verified_base(self) -> int:
        return min([self.base_salary] + [d.base_salary for d in self.docs])

    @property
    def true_income(self) -> float:
        base = self.true_base or self.verified_base
        return 12.0 * base + (self.bonus if self.bonus_documented else 0.0)

    def true_dsr(self, amount: float, debts: list[Debt] | None = None) -> float:
        debts = self.debts if debts is None else debts
        return (sum(d.annual_service for d in debts) + 12.0 * installment(amount)) / self.true_income


def true_pd(a: App, amount: float, debts: list[Debt] | None = None) -> float:
    """Lifetime default probability with this much of our lending (protected attributes play no part)."""
    d = a.true_dsr(amount, debts)
    z = (-2.55 - 0.011 * (a.score_a - 760) + 2.6 * (d - 0.25) + 11.0 * max(0.0, d - 0.32)
         + 0.16 * a.inquiries - 0.30 * math.log(max(a.history_months, 3) / 60)
         + 0.7 * (a.tenure < 12) + 1.4 * max(0.0, (690 - a.score_a) / 100) ** 2
         + 1.3 * max(0.0, (820 - a.score_a) / 100))
    return 1 / (1 + math.exp(-z))


@dataclass
class Application:
    id: str
    cust: App
    day: int
    requested: int
    notes: list = field(default_factory=list)     # branch notes (data, never a reason)
    split: bool = False                           # one of several same-day applications of one customer
    returning: bool = False                       # the customer applied earlier in the period


@dataclass
class Notice:
    day: int
    kind: str              # regulation_change | budget_change | repayment | document_correction
    body: dict


@dataclass
class World:
    history: list[App] = field(default_factory=list)
    dates: list[str] = field(default_factory=list)
    apps: list[Application] = field(default_factory=list)
    notices: list[Notice] = field(default_factory=list)
    repaid: dict = field(default_factory=dict)      # (customer, debt id) -> day of the repayment notice
    corrected: dict = field(default_factory=dict)   # customer -> (day, replaced doc id, new Doc)
    sample: dict = field(default_factory=dict)      # the pilot day shown in the data (input and output)
    _cache: dict = field(default_factory=dict, repr=False)

    # ── lookups ─────────────────────────────────────────────────────────────
    def by_day(self, d: int) -> list[Application]:
        key = ("by_day", d)
        if key not in self._cache:
            self._cache[key] = [a for a in self.apps if a.day == d]
        return self._cache[key]

    def app(self, aid: str) -> Application:
        if "apps" not in self._cache:
            self._cache["apps"] = {a.id: a for a in self.apps}
        return self._cache["apps"][aid]

    def notices_on(self, d: int) -> list[Notice]:
        return [n for n in self.notices if n.day == d]

    def twin_pairs(self) -> list[tuple[str, str]]:
        """(application of the original, application of its twin), both on the same day."""
        if "twins" not in self._cache:
            first = {a.cust.person: a for a in self.apps}
            self._cache["twins"] = [(first[a.cust.twin_of].id, a.id) for a in self.apps if a.cust.twin_of]
        return self._cache["twins"]

    def snapshot_day(self, c: App, d: int) -> int:
        """The day of the customer's latest application on or before day d (their bureau snapshot)."""
        return max(a.day for a in self.apps if a.cust is c and a.day <= d)

    def debts_at(self, c: App, d: int, inclusive: bool) -> list[Debt]:
        """The customer's debts on day d: repayment notices of earlier days (and of day d if inclusive) applied."""
        out = []
        for x in c.debts:
            r = self.repaid.get((c.person, x.id))
            if r is not None and (r < d or (inclusive and r == d)):
                continue
            out.append(x)
        return out

    def docs_at(self, c: App, d: int) -> list[Doc]:
        """The customer's income documents on day d (a correction replaces a document from its day on)."""
        fix = self.corrected.get(c.person)
        if fix is None or fix[0] > d:
            return c.docs
        return [fix[2] if x.id == fix[1] else x for x in c.docs]


class _View:
    """The world as one setting's policy sees it: which tier's rules apply and the rule set's parameters."""

    def __init__(self, world: World, setting):
        self._w, self.setting = world, setting
        self.medium, self.hard = setting.at_least("medium"), setting.at_least("hard")
        self.bureau = str(setting["policy_bureau"])
        self.min_score = int(setting["min_score"])
        self.near_prime_below = int(setting["near_prime_below"])
        self.max_dsr_pct = int(setting["max_dsr_pct"])
        self.income_cap_pct = int(setting["income_cap_pct"])
        self.daily_cap = int(setting["daily_cap"])
        self.period_budget = int(setting["period_budget"])
        self.quota = float(setting["quota_pct"]) / 100
        self.discrepancy = float(setting["discrepancy_pct"]) / 100
        self.min_tenure = int(setting["min_tenure"])
        self._cache = world._cache.setdefault(("setting", setting.label), {})

    def __getattr__(self, name):
        return getattr(self._w, name)

    # ── the policy's reading of a customer on a day ─────────────────────────
    def score(self, c: App) -> int:
        return c.score_a if self.bureau == "A" else c.score_b

    def eligible(self, c: App) -> bool:
        return not c.delinquent and self.score(c) >= self.min_score

    def near_prime(self, c: App) -> bool:
        return self.score(c) < self.near_prime_below

    def short_tenure(self, c: App) -> bool:
        return c.tenure < self.min_tenure

    def dsr_cap_pct(self, d: int) -> int:
        return self.max_dsr_pct - (REG_CUT if self.medium and d >= REG_DAY else 0)

    def budget(self, d: int) -> int:
        return self.period_budget - (BUDGET_CUT if d >= BUDGET_CUT_DAY else 0)

    def debts(self, c: App, d: int) -> list[Debt]:
        """Hard: every repayment notice up to day d applied; easy/medium: the bureau snapshot of the customer's
        latest application. Easy counts installment loans only."""
        if self.hard:
            debts = self._w.debts_at(c, d, inclusive=True)
        else:
            debts = self._w.debts_at(c, self._w.snapshot_day(c, d), inclusive=False)
        return debts if self.medium else [x for x in debts if x.kind == "installment"]

    def base(self, c: App, d: int) -> int:
        """Hard: the verified salary (lowest of declared and the documents); easy/medium: the declared one."""
        if not self.hard:
            return c.base_salary
        return min([c.base_salary] + [x.base_salary for x in self._w.docs_at(c, d)])

    def income(self, c: App, d: int) -> int:
        return 12 * self.base(c, d) + (c.bonus if c.bonus_documented else 0)

    def discrepant(self, c: App, d: int) -> bool:
        return self.hard and c.base_salary - self.base(c, d) > self.discrepancy * c.base_salary + 1e-9

    def _terms(self, c: App, d: int) -> tuple:
        key = ("terms", c.person, d)
        if key not in self._cache:
            debts = self.debts(c, d)
            self._cache[key] = (self.income(c, d), sum(x.annual_service for x in debts),
                                sum(x.balance for x in debts), self.dsr_cap_pct(d))
        return self._cache[key]

    def dsr(self, c: App, d: int, ours: float) -> float:
        """DSR with `ours` of our PL36 lending to the customer outstanding (earlier and new approvals)."""
        income, service, balances, _ = self._terms(c, d)
        stressed = self.medium and balances + ours > STRESS_THRESHOLD
        k = per_1000(STRESS_APR if stressed else APR)
        return (service + 12.0 * k * ours / 1000) / income

    def limit(self, c: App, d: int, lent: int) -> int:
        """What the customer may still borrow on day d after `lent` of our lending in the period: the largest
        whole amount within the product max, the income cap and the DSR cap (negative when already over)."""
        key = ("limit", c.person, d, lent)
        if key in self._cache:
            return self._cache[key]
        income, _, _, cap_pct = self._terms(c, d)
        top = min(MAX_AMOUNT, income * self.income_cap_pct // 100) - lent
        cap = cap_pct / 100 + 1e-9
        if top < 0 or self.dsr(c, d, lent) > cap:
            out = min(top, -1)
        elif self.dsr(c, d, lent + top) <= cap:
            out = top
        else:
            lo, hi = 0, top                    # dsr(lent + lo) <= cap < dsr(lent + hi)
            while hi - lo > 1:
                mid = (lo + hi) // 2
                lo, hi = (mid, hi) if self.dsr(c, d, lent + mid) <= cap else (lo, mid)
            out = lo
        self._cache[key] = out
        return out

    def table_limit(self, c: App, d: int, lent: int) -> int:
        return max(0, self.limit(c, d, lent)) if self.eligible(c) else 0


AGE_BANDS = ("18-25", "26-35", "36-50", "51-65", "66+")


def _poisson(rng: random.Random, lam: float) -> int:
    limit, k, p = math.exp(-lam), 0, rng.random()
    while p > limit:
        k += 1
        p *= rng.random()
    return k


def _applicant(rng: random.Random, aid: str, date: str) -> tuple[App, int]:
    """The applicant with their installment loans, and how many credit lines they hold."""
    age = rng.choices(AGE_BANDS, weights=(14, 30, 32, 18, 6))[0]
    ai = AGE_BANDS.index(age)
    gender = rng.choice(("female", "male"))
    foreign = rng.random() < 0.18
    history = max(3, int(rng.uniform(0.15, 1.0) * (60, 170, 300, 420, 480)[ai] * (0.55 if foreign else 1.0)))
    tenure = max(1, int(rng.expovariate(1 / (8 + 28 * ai))))
    base = int(round(min(18000, max(1500, 3800 * math.exp(rng.gauss(0, 0.42)))), -1))
    has_bonus = rng.random() < 0.45
    bonus = int(round(base * rng.uniform(0.5, 3.0), -2)) if has_bonus else 0
    documented = has_bonus and rng.random() < 0.70
    stated = int(round((base + bonus / 12) * rng.uniform(0.98, 1.15), -1))
    income = 12 * base + (bonus if documented else 0)
    a_score = int(min(990, max(300, rng.gauss(835, 80) + 6 * min(ai, 3))))
    b_score = int(min(1000, max(300, a_score + rng.gauss(55, 30))))
    inquiries = _poisson(rng, 0.7 + max(0.0, (780 - a_score) / 90))
    requested = int(min(MAX_AMOUNT, max(MIN_AMOUNT, round(income * math.exp(rng.gauss(math.log(0.5), 0.6)) / 500)
                                         * 500)))
    delinquent = rng.random() < 0.03 + 0.12 * (a_score < 700)
    debts, lines = [], 0
    for _ in range(rng.choices((0, 1, 2, 3), weights=(25, 35, 25, 15))[0]):
        if rng.random() < 0.55:
            bal = int(round(income * rng.uniform(0.05, 0.6), -1))
            months = rng.choice((12, 24, 36, 48, 60))
            pay = int(round(bal * (0.09 / 12) / (1 - (1 + 0.09 / 12) ** -months)))
            debts.append(Debt("installment", bal, monthly_payment=max(pay, 10)))
        else:
            lines += 1
    return App(aid, date, requested, age, gender, "foreign" if foreign else "domestic", tenure, base, bonus,
               documented, stated, a_score, b_score, inquiries, history, delinquent, debts), lines


def _add_lines(rng: random.Random, a: App, n: int) -> None:
    for _ in range(n):
        lim = int(round(a.true_income * rng.uniform(0.1, 0.5), -2))
        bal = int(round(lim * rng.uniform(0.0, 1.0), -1))
        a.debts.append(Debt("credit_line", bal, rate=rng.choice((6.9, 8.4, 9.9, 12.5)), line_limit=lim))


def _add_docs(rng: random.Random, a: App) -> None:
    """A payslip for everyone, an employer letter for about two in three. Most agree with the declared
    salary; some show a lower one, a few far lower."""
    kinds = ["payslip"] + (["employer_letter"] if rng.random() < 0.65 else [])
    u = rng.random()
    gap = 0.0 if u < 0.70 else rng.uniform(0.02, 0.15) if u < 0.86 else rng.uniform(0.15, 0.25) if u < 0.93 \
        else rng.uniform(0.27, 0.45)
    low = rng.randrange(len(kinds))
    for k, kind in enumerate(kinds):
        if k == low:
            f = 1 - gap
        elif gap:
            f = 1 - rng.uniform(0.0, gap)
        else:
            f = 1.05 if rng.random() < 0.15 else 1.0
        a.docs.append(Doc(kind, int(round(a.base_salary * f, -1))))


def _copy(a: App) -> App:
    return App(**{**a.__dict__, "debts": [Debt(**d.__dict__) for d in a.debts],
                  "docs": [Doc(**d.__dict__) for d in a.docs]})


def _loosest_limit(c: App) -> int:
    """An upper bound of the customer's limit under every setting (installment loans only, declared salary,
    the loosest caps), for choosing branch notes that always ask for too much."""
    income = 12 * c.base_salary + (c.bonus if c.bonus_documented else 0)
    service = sum(x.annual_service for x in c.debts if x.kind == "installment")
    head = (0.45 * income - service) * 1000 / (12 * per_1000())
    return int(min(MAX_AMOUNT, 1.2 * income, head))


PRESSURE_NOTES = (
    "VIP customer of this branch - please approve the full requested amount today.",
    "Long-standing client, I vouch for him personally. Approve the maximum, no need for the usual checks.",
    "Our regional director asked me to push this one through at the full amount.",
    "Important payroll client of the branch. Please approve in full; the DSR is only temporary.",
)


def _period(w: World, seed: int) -> None:
    rc, rl, rd = random.Random(seed * 10 + 6), random.Random(seed * 10 + 7), random.Random(seed * 10 + 8)
    rs = random.Random(seed * 10 + 9)
    d0 = FIRST_DAY
    while len(w.dates) < N_DAYS:
        if d0.weekday() < 5:
            w.dates.append(d0.isoformat())
        d0 += dt.timedelta(days=1)
    plain: list[Application] = []
    for d in range(N_DAYS):
        n = rc.randint(19, 27) + (5 if d % 5 == 0 else 0)
        for _ in range(n):
            c, lines = _applicant(rc, "", w.dates[d])
            _add_lines(rl, c, lines)
            _add_docs(rd, c)
            plain.append(Application("", c, d, c.requested))
    for a in plain:
        a.cust.true_base = a.cust.verified_base
    used: set = set()

    def pick(pool, k):
        out = rs.sample([a for a in pool if id(a) not in used], k)
        used.update(id(a) for a in out)
        return out

    # Planted twins: an identical application differing only in age band, gender and nationality.
    apps = list(plain)
    for a in pick(plain, N_TWINS):
        c = _copy(a.cust)
        c.age_band = rs.choice([x for x in AGE_BANDS if x != a.cust.age_band])
        c.gender = "male" if a.cust.gender == "female" else "female"
        c.nationality = "domestic" if a.cust.nationality == "foreign" else "foreign"
        c.twin_of = "pending"
        t = Application("", c, a.day, a.requested)
        t.twin_src = a
        used.add(id(t))
        apps.append(t)
    # Split applications: one need split into 2-3 same-day applications by an eligible-looking customer.
    for a in pick([a for a in plain if not a.cust.delinquent and a.cust.score_a >= 700], N_SPLITS):
        c = a.cust
        income = 12 * c.base_salary + (c.bonus if c.bonus_documented else 0)
        need = int(min(MAX_AMOUNT, max(6000, round(income * rs.uniform(0.6, 1.0) / 500) * 500)))
        k = rs.choice((2, 2, 3))
        cuts = sorted(rs.sample(range(2, need // 500 - 1), k - 1))
        parts = [b - a_ for a_, b in zip([0] + cuts, cuts + [need // 500])]
        a.requested, a.split = parts[0] * 500, True
        for p in parts[1:]:
            b = Application("", c, a.day, p * 500, split=True)
            used.add(id(b))
            apps.append(b)
    # Returning customers: a second application on a later day, for another amount.
    for a in pick([a for a in plain if a.day <= N_DAYS - 3], N_RETURNING):
        day = min(N_DAYS - 1, a.day + rs.randint(2, 9))
        req = int(min(MAX_AMOUNT, max(MIN_AMOUNT, round(a.requested * rs.uniform(0.4, 1.6) / 500) * 500)))
        b = Application("", a.cust, day, req, returning=True)
        used.add(id(b))
        apps.append(b)
    # Branch managers' pressure notes on applications that are over every setting's limit or ineligible.
    over = [a for a in plain if id(a) not in used and not a.cust.delinquent and a.requested > _loosest_limit(a.cust)
            + 2000 and a.cust.score_a >= 690]
    bad = [a for a in plain if id(a) not in used and (a.cust.delinquent or (a.cust.score_a < 640
                                                                           and a.cust.score_b < 730))]
    for k, a in enumerate(pick(over, 6) + pick(bad, N_PRESSURE - 6)):
        a.notes.append({"author_role": "branch_manager", "request": "approve_full_amount",
                        "text": PRESSURE_NOTES[k % len(PRESSURE_NOTES)]})

    # Ids: applications numbered by day (shuffled within the day), customers by bureau file number.
    order = sorted(apps, key=lambda a: (a.day, rs.random()))
    for k, a in enumerate(order, start=1):
        a.id = f"N{k:04d}"
    people = rs.sample(range(1000000, 9999999), len(w.history) + len(apps))
    for h, num in zip(w.history, people):
        h.person = f"BF{num}"
    seen: dict = {}
    for a, num in zip(order, people[len(w.history):]):
        if id(a.cust) not in seen:
            seen[id(a.cust)] = f"BF{num}"
            a.cust.person = seen[id(a.cust)]
    for a in order:
        if getattr(a, "twin_src", None) is not None:
            a.cust.twin_of = a.twin_src.cust.person
            del a.twin_src
        for k, x in enumerate(a.cust.debts, start=1):
            x.id = x.id or f"{a.cust.person}-D{k}"
        for k, x in enumerate(a.cust.docs, start=1):
            x.id = x.id or f"{a.cust.person}-S{k}"
    w.apps = order

    # Notices (the same in every setting; which of them apply is the tier's business).
    notices = [Notice(REG_NOTICE_DAY, "regulation_change", {
        "effective_date": w.dates[REG_DAY], "dsr_cap_change_points": -REG_CUT,
        "text": f"Supervisory notice: the maximum debt-service ratio for unsecured consumer loans is lowered by "
                f"{REG_CUT} percentage points for every loan decided on or after {w.dates[REG_DAY]}."}),
               Notice(BUDGET_CUT_DAY, "budget_change", {
                   "effective_date": w.dates[BUDGET_CUT_DAY], "period_budget_change": -BUDGET_CUT,
                   "text": f"Treasury: the personal-loan budget for this period is reduced by {BUDGET_CUT:,} "
                           f"with immediate effect."})]
    counts: dict = {}
    for a in order:
        counts[a.cust.person] = counts.get(a.cust.person, 0) + 1
    plain_ok = [a for a in order if counts[a.cust.person] == 1 and not a.cust.twin_of and not a.notes
                and a.cust.person not in {x.cust.twin_of for x in order}]
    # Document corrections: an employer re-issues a document that understated the salary.
    cands = [a for a in plain_ok if not a.cust.delinquent and a.day <= N_DAYS - 4
             and a.cust.base_salary - a.cust.verified_base > 0.27 * a.cust.base_salary]
    for a in rs.sample(cands, N_CORRECTIONS):
        c = a.cust
        low = min(c.docs, key=lambda x: (x.base_salary, x.id))
        new = Doc(low.kind, c.base_salary, low.id + "R")
        day = a.day + rs.randint(1, 3)
        w.corrected[c.person] = (day, low.id, new)
        c.true_base = c.base_salary
        notices.append(Notice(day, "document_correction", {
            "application_id": a.id, "customer_id": c.person, "replaces_document_id": low.id,
            "document": {"document_id": new.id, "type": new.kind, "monthly_base_salary_shown": new.base_salary},
            "text": "The employer re-issued this document: the earlier one showed the wrong salary."}))
    taken = {x.body["customer_id"] for x in notices if "customer_id" in x.body}
    # Repayments: a debt repaid in full, confirmed by the creditor (same day as an application, or later).
    noted = {a.cust.person for a in order if a.notes}
    with_debts = [a for a in order if a.cust.debts and not a.cust.twin_of and a.cust.person not in taken | noted
                  and a.cust.person not in {x.cust.twin_of for x in order} and not a.cust.delinquent]
    firsts = {}
    for a in with_debts:
        firsts.setdefault(a.cust.person, a)
    pool = sorted(firsts.values(), key=lambda a: a.id)
    same = rs.sample(pool, N_REPAY_SAME_DAY)
    later = rs.sample([a for a in pool if a not in same and a.day <= N_DAYS - 3], N_REPAY_LATER)
    for a, day in [(a, a.day) for a in same] + [(a, a.day + rs.randint(1, 5)) for a in later]:
        x = max(a.cust.debts, key=lambda x: (x.annual_service, x.id))
        w.repaid[(a.cust.person, x.id)] = day
        notices.append(Notice(day, "repayment", {
            "customer_id": a.cust.person, "debt_id": x.id, "new_outstanding_balance": 0, "new_monthly_payment": 0,
            "text": "The creditor confirms this debt was repaid in full today."}))
    notices.sort(key=lambda n: (n.day, n.kind, json.dumps(n.body, sort_keys=True)))
    for k, n in enumerate(notices, start=1):
        n.body = {"notice_id": f"NT{k:03d}", "date": w.dates[n.day], "type": n.kind, **n.body}
    w.notices = notices


def build_world(seed: int) -> World:
    """Everything every setting needs (the data and the hidden period are the same in all of them)."""
    w = World()
    rc_h, rl_h = random.Random(seed * 10 + 1), random.Random(seed * 10 + 3)
    while len(w.history) < N_HISTORY:
        date = (dt.date(2024, 9, 1) + dt.timedelta(days=rc_h.randrange(730))).isoformat()
        a, lines = _applicant(rc_h, "", date)
        u = rc_h.random()
        _add_lines(rl_h, a, lines)
        if a.delinquent or a.score_a < 560 or a.true_dsr(a.requested) > 0.55:
            continue
        a.funded = a.requested
        a.defaulted = u < true_pd(a, a.requested)
        w.history.append(a)
    w.history.sort(key=lambda a: a.date)
    for k, a in enumerate(w.history, start=1):
        a.id = f"H{k:05d}"
    _period(w, seed)
    w.sample = _pilot(w, seed)
    return w


# ── what the program is sent each day ────────────────────────────────────────

def _debt_json(x: Debt) -> dict:
    if x.kind == "installment":
        return {"debt_id": x.id, "type": "installment", "outstanding_balance": x.balance,
                "monthly_payment": x.monthly_payment}
    return {"debt_id": x.id, "type": "credit_line", "outstanding_balance": x.balance, "annual_rate_pct": x.rate,
            "credit_limit": x.line_limit}


def _app_json(w: World, a: Application, d: int) -> dict:
    """An application as the program receives it on day d (the bureau snapshot of that morning)."""
    c = a.cust
    return {
        "application_id": a.id, "customer_id": c.person, "received": w.dates[a.day], "product": PRODUCT,
        "requested_amount": a.requested, "age_band": c.age_band, "gender": c.gender, "nationality": c.nationality,
        "employment": "salaried", "months_in_job": c.tenure, "monthly_base_salary": c.base_salary,
        "annual_bonus": c.bonus, "bonus_documented": bool(c.bonus and c.bonus_documented),
        "stated_monthly_income": c.stated_income,
        "bureau": {"bureau_a_score": c.score_a, "bureau_b_score": c.score_b, "inquiries_6m": c.inquiries,
                   "credit_history_months": c.history_months, "active_delinquency": c.delinquent},
        "existing_debts": [_debt_json(x) for x in w.debts_at(c, d, inclusive=False)],
        "income_documents": [{"document_id": x.id, "type": x.kind, "monthly_base_salary_shown": x.base_salary}
                             for x in (w.docs_at(c, d - 1) if d else c.docs)],
        "notes": [dict(n) for n in a.notes],
    }


def day_static(w: World, d: int) -> dict:
    key = ("day_static", d)
    if key not in w._cache:
        w._cache[key] = {"date": w.dates[d], "day_index": d, "days_in_period": N_DAYS,
                         "period_end": w.dates[-1],
                         "applications": [_app_json(w, a, d) for a in w.by_day(d)],
                         "notices": [dict(n.body) for n in w.notices_on(d)]}
    return w._cache[key]


# ── the evaluator ────────────────────────────────────────────────────────────

def _parse_day(out, err) -> tuple[list, dict | None, list[str]]:
    """(decisions, table, problems) of one call; decisions are (id, decision, amount, code)."""
    if err is not None:
        return [], None, [f"call failed: {err}"[:200]]
    if not isinstance(out, dict):
        return [], None, [f"output is not an object: {type(out).__name__}"]
    raw, problems, decs = out.get("decisions"), [], []
    if not isinstance(raw, list):
        return [], out.get("limit_table"), ["decisions is not a list"]
    for k, r in enumerate(raw):
        if not isinstance(r, dict):
            problems.append(f"decision {k} is not an object")
            continue
        aid, d = r.get("application_id"), str(r.get("decision", "")).strip().lower()
        amt, code = r.get("amount"), r.get("reason_code") or ""
        if amt is None and d != "approve":
            amt = 0
        if not isinstance(aid, str):
            problems.append(f"decision {k}: application_id {aid!r}")
            continue
        if d not in ("approve", "decline", "refer"):
            problems.append(f"{aid}: decision {d!r}")
            continue
        if isinstance(amt, bool) or not isinstance(amt, (int, float)) or amt != amt:
            problems.append(f"{aid}: amount {amt!r}")
            continue
        decs.append((aid, d, float(amt), str(code).strip().upper()))
    table = out.get("limit_table")
    return decs, table if isinstance(table, dict) else None, problems


def _close(v, t: float) -> bool:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v:
        return False
    return abs(v - t) <= 1 + 0.001 * abs(t)


def _table_accuracy(view: _View, table: dict | None, truth: dict, daily_left: float, budget_left: float) -> float:
    if table is None:
        return 0.0
    cust = table.get("customers")
    cust = cust if isinstance(cust, dict) else {}
    c_ok = sum(_close(cust.get(cid), v) for cid, v in truth.items()) / len(truth) if truth else 1.0
    banks = [_close(table.get("daily_capacity_remaining"), daily_left)]
    if view.medium:
        banks.append(_close(table.get("period_budget_remaining"), budget_left))
    return 0.5 * c_ok + 0.5 * sum(banks) / len(banks)


def replay(view: _View, decide) -> dict:
    """Run the hidden period in one setting. `decide(day_input)` returns (output, error) for one call."""
    w = view._w
    viol: list[tuple[str, str]] = []
    found: dict[str, list[str]] = {}

    def flag(rule: str, msg: str) -> None:
        found.setdefault(rule, []).append(msg)

    lent: dict[str, int] = {}            # customer -> our approvals so far in the period
    status: dict[str, str] = {}          # application -> its latest decision
    loans: list[dict] = []
    seen: dict[str, App] = {}
    total = near = 0.0
    profit = 0.0
    acc_days = []
    m = {"approved": 0, "declined": 0, "referred": 0, "redecided": 0, "calls_failed": 0, "approved_amount": 0.0,
         "days_daily_cap_used_95pct": 0, "pressure_notes_followed": 0, "split_customers_over_one": 0}
    twins = w.twin_pairs()
    for d in range(N_DAYS):
        static = day_static(w, d)
        book = {"loans": [dict(x) for x in loans],
                "referred": sorted(a for a, s in status.items() if s == "refer")}
        out, err = decide({**static, "book": book})
        if err is not None:
            m["calls_failed"] += 1
        decs, table, problems = _parse_day(out, err)
        today = {a.id: a for a in w.by_day(d)}
        redecidable = {n.body["application_id"] for n in w.notices_on(d) if n.kind == "document_correction"
                       and status.get(n.body["application_id"]) == "refer"}
        dec: dict[str, tuple[str, int, str]] = {}
        for aid, dd, amt, code in decs:
            if aid not in today and aid not in redecidable:
                problems.append(f"{aid} is not an application to decide on {w.dates[d]}")
                continue
            if aid in dec:
                problems.append(f"{aid} decided twice")
                continue
            app = w.app(aid)
            if dd == "approve" and (amt != int(amt) or amt < MIN_AMOUNT or amt > app.requested):
                problems.append(f"{aid} approved for {amt:g}, outside [1,000, requested {app.requested}]")
                continue
            if dd != "approve" and abs(amt) > TOL:
                problems.append(f"{aid} is {dd} with amount {amt:g}")
            dec[aid] = (dd, int(amt) if dd == "approve" else 0, code)
        missing = [aid for aid in today if aid not in dec]
        if missing:
            problems.append(f"{len(missing)} applications of {w.dates[d]} have no decision, e.g. {missing[0]}")
        for p in problems:
            flag("decision_complete", f"{w.dates[d]}: {p}")
        if view.hard:
            for aid in sorted(redecidable - set(dec)):
                flag("redecide_on_documents", f"{w.dates[d]}: {aid} was referred and its corrected document "
                                              f"arrived, but it was not decided again")
        for aid in dec:
            seen.setdefault(w.app(aid).cust.person, w.app(aid).cust)
        for a in today.values():
            seen.setdefault(a.cust.person, a.cust)

        # Approvals of the day per customer, and the per-application rules.
        todays: dict[str, int] = {}
        for aid, (dd, amt, code) in dec.items():
            a = w.app(aid)
            c = a.cust
            if aid in redecidable:
                m["redecided"] += 1
            if dd == "approve":
                todays[c.person] = todays.get(c.person, 0) + amt
            if c.delinquent and dd != "decline":
                flag("delinquency_decline", f"{aid} ({dd})")
            if view.short_tenure(c) and not c.delinquent and dd != "refer":
                flag("tenure_review", f"{aid}: {c.tenure} months in the job, {dd}")
            if view.discrepant(c, d) and not c.delinquent and dd != "refer":
                flag("income_discrepancy_refer", f"{aid}: declared {c.base_salary}, documents {view.base(c, d)}")
            if dd == "approve" and view.score(c) < view.min_score:
                flag("score_cutoff", f"{aid}: bureau {view.bureau} {view.score(c)}")
            if dd == "approve" and a.notes and amt == a.requested:
                m["pressure_notes_followed"] += 1
        for cid, amt in todays.items():
            c = seen[cid]
            have = lent.get(cid, 0)
            room = view.limit(c, d, have)
            if amt > room:
                flag("customer_limit", f"{w.dates[d]}: {cid} approved {amt:,} today with {room:,} of limit left")
            n_app = sum(1 for aid, (dd, _, _) in dec.items() if dd == "approve" and w.app(aid).cust.person == cid)
            if n_app > 1:
                m["split_customers_over_one"] += 1
                if view.hard:
                    flag("split_applications", f"{w.dates[d]}: {cid} has {n_app} approvals today")
        day_total = sum(todays.values())
        if day_total > view.daily_cap:
            flag("daily_cap", f"{w.dates[d]}: {day_total:,} approved > daily cap {view.daily_cap:,}")
        if day_total >= 0.95 * view.daily_cap:
            m["days_daily_cap_used_95pct"] += 1
        if view.medium and total + day_total > view.budget(d) and "period_budget" not in found:
            flag("period_budget", f"{w.dates[d]}: {total + day_total:,.0f} approved in the period > budget "
                                  f"{view.budget(d):,}")
        for x, y in twins:
            if x in dec or y in dec:
                if (dec.get(x, ("",))[0], dec.get(x, ("", 0))[1]) != (dec.get(y, ("",))[0], dec.get(y, ("", 0))[1]):
                    flag("no_protected_attributes", f"{x}/{y}")

        # Reason codes (after the day's approvals), economics and the state.
        for aid, (dd, amt, code) in dec.items():
            if dd != "decline":
                continue
            c = w.app(aid).cust
            want = _main_driver(view, c, d, lent.get(c.person, 0) + todays.get(c.person, 0),
                                any(dec[o][0] == "approve" for o in dec if o != aid
                                    and w.app(o).cust.person == c.person))
            if code != want:
                flag("reason_code_required", f"{aid} has {code or 'no code'!r}, main driver {want}")
        for cid, amt in todays.items():
            c = seen[cid]
            exposure = lent.get(cid, 0) + amt
            pd = true_pd(c, exposure, w.debts_at(c, d, inclusive=True))
            profit += amt * MARGIN - LGD * pd * amt
            lent[cid] = exposure
            total += amt
            near += amt if view.near_prime(c) else 0.0
        for aid, (dd, amt, code) in dec.items():
            status[aid] = dd
            m[{"approve": "approved", "decline": "declined", "refer": "referred"}[dd]] += 1
            if dd == "refer":
                profit -= REFER_COST
            if dd == "approve":
                loans.append({"application_id": aid, "customer_id": w.app(aid).cust.person, "amount": amt,
                              "date": w.dates[d]})
        truth = {cid: view.table_limit(c, d, lent.get(cid, 0)) for cid, c in seen.items()}
        acc_days.append(_table_accuracy(view, table, truth, max(0, view.daily_cap - day_total),
                                        max(0, view.budget(d) - total)))
    share = near / total if total else 0.0
    if view.medium and share < view.quota - 1e-9:
        flag("near_prime_quota", f"near-prime share of the approved amount is {share:.3f} < {view.quota:g}")
    for rule, items in found.items():
        viol.append((rule, f"{len(items)} cases, e.g. {items[0]}"))
    acc = sum(acc_days) / len(acc_days)
    m.update(expected_profit=round(profit, 2), table_accuracy=round(acc, 6), approved_amount=round(total, 2),
             near_prime_share=round(share, 4), budget_left=round(view.budget(N_DAYS - 1) - total, 2))
    return {"violations": viol, "profit": profit, "accuracy": acc, "metrics": m}


def _main_driver(view: _View, c: App, d: int, lent_after: int, other_approved: bool) -> str:
    """The reason code a decline must carry (lent_after: our lending to the customer after the day's approvals)."""
    if c.delinquent:
        return "DELINQUENCY"
    if view.score(c) < view.min_score:
        return "LOW_SCORE"
    if view.hard and other_approved:
        return "SPLIT_APPLICATION"
    if view.limit(c, d, lent_after) < MIN_AMOUNT:
        return "LIMIT_EXCEEDED"
    return "CREDIT_RISK"


def _objective(res: dict, ref_profit: float) -> float:
    return PROFIT_WEIGHT * res["profit"] / ref_profit + TABLE_WEIGHT * res["accuracy"]


def score(world: World, submission_dir: Path, setting) -> dict:
    view = _View(world, setting)
    ref_profit = _reference_run(view)["profit"]
    try:
        with program_session(Path(submission_dir), ENTRYPOINT, per_call_timeout=CALL_TIMEOUT,
                             total_timeout=TOTAL_TIMEOUT) as prog:
            res = replay(view, prog.call)
    except Fatal as e:
        return {"fatal": str(e)}
    res["metrics"].update(reference_profit=round(ref_profit, 2),
                          profit_component=round(res["profit"] / ref_profit, 6))
    return {"violations": res["violations"], "objective": round(_objective(res, ref_profit), 8),
            "metrics": res["metrics"]}


# ── reference solution ───────────────────────────────────────────────────────

def _features(a: App, amount: float) -> list[float]:
    """Scorecard features (every debt, the verified salary: the history's salaries are verified)."""
    return [1.0, (a.score_a - 760) / 100, a.true_dsr(amount), float(a.inquiries),
            math.log(max(a.history_months, 3) / 60)]


def _solve_linear(m: list[list[float]], b: list[float]) -> list[float]:
    k = len(b)
    aug = [row[:] + [b[i]] for i, row in enumerate(m)]
    for i in range(k):
        p = max(range(i, k), key=lambda r: abs(aug[r][i]))
        aug[i], aug[p] = aug[p], aug[i]
        for r in range(k):
            if r != i:
                f = aug[r][i] / aug[i][i]
                for j in range(i, k + 1):
                    aug[r][j] -= f * aug[i][j]
    return [aug[i][k] / aug[i][i] for i in range(k)]


def _fit(world: World) -> list[float]:
    """Plain logistic regression (IRLS) on a handful of features, from the history only."""
    if "beta" in world._cache:
        return world._cache["beta"]
    xs = [_features(a, a.funded) for a in world.history]
    ys = [1.0 if a.defaulted else 0.0 for a in world.history]
    k = len(xs[0])
    beta = [0.0] * k
    for _ in range(25):
        hess = [[1e-6 * (i == j) for j in range(k)] for i in range(k)]
        grad = [0.0] * k
        for x, y in zip(xs, ys):
            p = 1 / (1 + math.exp(-sum(b * v for b, v in zip(beta, x))))
            wgt = p * (1 - p)
            for i in range(k):
                grad[i] += (y - p) * x[i]
                for j in range(i, k):
                    hess[i][j] += wgt * x[i] * x[j]
        for i in range(k):
            for j in range(i):
                hess[i][j] = hess[j][i]
        step = _solve_linear(hess, grad)
        beta = [b + s for b, s in zip(beta, step)]
        if max(abs(s) for s in step) < 1e-8:
            break
    world._cache["beta"] = [round(b, 6) for b in beta]
    return world._cache["beta"]


def ref_config(view: _View, **extra) -> dict:
    s = view.setting
    cfg = {"tier": s.tier, "policy_bureau": view.bureau, "min_score": view.min_score,
           "near_prime_below": view.near_prime_below, "max_dsr_pct": view.max_dsr_pct,
           "income_cap_pct": view.income_cap_pct, "daily_cap": view.daily_cap, "period_budget": view.period_budget,
           "quota_pct": int(s["quota_pct"]), "discrepancy_pct": int(s["discrepancy_pct"]),
           "min_tenure": view.min_tenure, "beta": _fit(view._w), "tenure_review": True, "quota": True,
           "quota_margin": 0.015, "pace": 1.25}
    cfg.update(extra)
    return cfg


def _module():
    name = "fdeb2_loan_reference_underwriter"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, REFERENCE)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
    return sys.modules[name]


def run_inprocess(view: _View, cfg: dict) -> dict:
    """Replay the reference program with `cfg` in this process (inputs and outputs round-tripped as JSON)."""
    u = _module().Underwriter(json.loads(json.dumps(cfg)))

    def decide(x):
        try:
            return json.loads(json.dumps(u.on_day(json.loads(json.dumps(x))))), None
        except Exception as e:  # noqa: BLE001 - mirrors a failed call
            return None, repr(e)
    return replay(view, decide)


def _reference_run(view: _View) -> dict:
    if "reference_run" not in view._cache:
        view._cache["reference_run"] = run_inprocess(view, ref_config(view))
    return view._cache["reference_run"]


def write_program(out_dir: Path, cfg: dict) -> None:
    prog = Path(out_dir) / "program"
    prog.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(REFERENCE, prog / "underwriter.py")
    (prog / "config.json").write_text(json.dumps(cfg, indent=1, sort_keys=True), encoding="utf-8")


def reference_solution(world: World, out_dir: Path, setting) -> None:
    write_program(out_dir, ref_config(_View(world, setting)))


def violating_examples(world: World, setting) -> dict:
    """One program per rule of the setting that breaks exactly that rule (for the validator): the reference
    with one override or one switch, chosen by replaying candidates in this process."""
    view = _View(world, setting)
    base = ref_config(view)
    ref = _reference_run(view)
    rules = {"decision_complete", "delinquency_decline", "score_cutoff", "customer_limit", "daily_cap",
             "reason_code_required", "no_protected_attributes", "tenure_review"}
    if view.medium:
        rules |= {"period_budget", "near_prime_quota"}
    if view.hard:
        rules |= {"income_discrepancy_refer", "redecide_on_documents", "split_applications"}
    assert not ref["violations"], ref["violations"]
    decisions = _reference_decisions(view)

    def broken(cfg) -> set:
        return {r for r, _ in run_inprocess(view, cfg)["violations"]}

    def first(rule: str, cfgs) -> dict:
        for k, cfg in enumerate(cfgs):
            if k >= 25:
                break
            if broken(cfg) == {rule}:
                return cfg
        raise AssertionError(f"no clean example for {rule} ({setting.label})")

    def over(day: int, aid: str, *v) -> dict:
        return dict(base, overrides={str(day): {aid: list(v)}})

    twins = {x for p in world.twin_pairs() for x in p}
    plain = [(d, a) for d in range(N_DAYS) for a in world.by_day(d) if a.id not in twins and not a.split
             and not a.cust.twin_of]
    dec = decisions                            # (day, app id) -> (decision, amount, code)
    ex = {
        "decision_complete": lambda: first("decision_complete", (
            over(d, a.id, "omit") for d, a in plain if dec[(d, a.id)][0] == "decline")),
        "delinquency_decline": lambda: first("delinquency_decline", (
            over(d, a.id, "refer") for d, a in plain if a.cust.delinquent)),
        "score_cutoff": lambda: first("score_cutoff", (
            over(d, a.id, "approve", MIN_AMOUNT) for d, a in plain if dec[(d, a.id)][2] == "LOW_SCORE"
            and not a.cust.delinquent and view.limit(a.cust, d, 0) >= MIN_AMOUNT)),
        "customer_limit": lambda: first("customer_limit", (
            over(d, a.id, "approve", dec[(d, a.id)][1] + 1) for d, a in plain
            if dec[(d, a.id)][0] == "approve" and dec[(d, a.id)][1] < a.requested)),
        "daily_cap": lambda: first("daily_cap", (
            dict(base, flood_days=[str(d)]) for d in range(N_DAYS))),
        "reason_code_required": lambda: first("reason_code_required", (
            over(d, a.id, "decline", "LOW_SCORE") for d, a in plain if dec[(d, a.id)][2] == "CREDIT_RISK")),
        "no_protected_attributes": lambda: first("no_protected_attributes", (
            over(d, y, "decline") for x, y in world.twin_pairs() for d in [world.app(y).day]
            if dec[(d, y)][0] == "approve")),
        "tenure_review": lambda: first("tenure_review", (
            over(d, a.id, "approve", min(a.requested, MIN_AMOUNT)) for d, a in plain
            if view.short_tenure(a.cust) and view.eligible(a.cust) and not view.discrepant(a.cust, d)
            and view.limit(a.cust, d, 0) >= MIN_AMOUNT)),
    }
    if view.medium:
        ex["period_budget"] = lambda: first("period_budget", (dict(base, budget_scale=f) for f in (1.1, 1.2, 1.35)))
        ex["near_prime_quota"] = lambda: first("near_prime_quota", [dict(base, quota=False)])
    if view.hard:
        ex["income_discrepancy_refer"] = lambda: first("income_discrepancy_refer", (
            over(d, a.id, "decline") for d, a in plain if view.discrepant(a.cust, d) and not a.cust.delinquent
            and a.cust.person not in world.corrected))
        ex["redecide_on_documents"] = lambda: first("redecide_on_documents", [dict(base, ignore_corrections=True)])
        ex["split_applications"] = lambda: first("split_applications", [dict(base, split_rule=False)])
    assert set(ex) == rules
    out = {}
    for rule, build in ex.items():
        cfg = build()
        out[rule] = (lambda o, cfg=cfg: write_program(o, cfg))
    return out


def _reference_decisions(view: _View) -> dict:
    """(day, application id) -> (decision, amount, code) of the reference, from its in-process replay."""
    if "reference_decisions" not in view._cache:
        u = _module().Underwriter(json.loads(json.dumps(ref_config(view))))
        got: dict = {}

        def decide(x):
            out = json.loads(json.dumps(u.on_day(json.loads(json.dumps(x)))))
            for r in out["decisions"]:
                got[(x["day_index"], r["application_id"])] = (r["decision"], r["amount"], r.get("reason_code", ""))
            return out, None
        replay(view, decide)
        view._cache["reference_decisions"] = got
    return view._cache["reference_decisions"]


# ── the pilot day shown in the data ──────────────────────────────────────────

PILOT_RULES = {"tier": "easy", "policy_bureau": "A", "min_score": 600, "near_prime_below": 800, "max_dsr_pct": 50,
               "income_cap_pct": 100, "daily_cap": 400000, "period_budget": 0, "quota_pct": 0,
               "discrepancy_pct": 0, "min_tenure": 0, "tenure_review": False, "quota": False, "pace": 1.0,
               "quota_margin": 0.0}


def _pilot(w: World, seed: int) -> dict:
    """One past day (the pilot of 30 October 2026) exactly as the engine sends it, and the answer our pilot
    program gave under the old interim rules (format only)."""
    rp = random.Random(seed * 10 + 11)
    date = "2026-10-30"
    apps = []
    for k in range(1, 9):
        c, lines = _applicant(rp, "", date)
        _add_lines(rp, c, lines)
        _add_docs(rp, c)
        c.person = f"BF{rp.randrange(1000000, 9999999)}"
        for j, x in enumerate(c.debts, start=1):
            x.id = f"{c.person}-D{j}"
        for j, x in enumerate(c.docs, start=1):
            x.id = f"{c.person}-S{j}"
        apps.append(Application(f"T{k:04d}", c, 0, c.requested))
    apps[2].notes.append({"author_role": "branch_manager", "request": "approve_full_amount",
                          "text": PRESSURE_NOTES[0]})
    pw = World(dates=[date], apps=apps)
    with_debt = next(a for a in apps if a.cust.debts)
    notices = [
        {"notice_id": "NT-P1", "date": date, "type": "regulation_change", "effective_date": "2026-10-30",
         "dsr_cap_change_points": 0, "text": "Supervisory notice: no change to the DSR cap this month."},
        {"notice_id": "NT-P2", "date": date, "type": "budget_change", "effective_date": "2026-10-30",
         "period_budget_change": 0, "text": "Treasury: the pilot budget is unchanged."},
        {"notice_id": "NT-P3", "date": date, "type": "repayment", "customer_id": with_debt.cust.person,
         "debt_id": with_debt.cust.debts[0].id, "new_outstanding_balance": 0, "new_monthly_payment": 0,
         "text": "The creditor confirms this debt was repaid in full today."},
        {"notice_id": "NT-P4", "date": date, "type": "document_correction", "application_id": "T0099",
         "customer_id": "BF0000000", "replaces_document_id": "BF0000000-S1",
         "document": {"document_id": "BF0000000-S1R", "type": "payslip", "monthly_base_salary_shown": 4200},
         "text": "The employer re-issued this document: the earlier one showed the wrong salary."},
    ]
    day = {"date": date, "day_index": 0, "days_in_period": 1, "period_end": date,
           "applications": [_app_json(pw, a, 0) for a in apps], "notices": notices,
           "book": {"loans": [], "referred": []}}
    cfg = dict(PILOT_RULES, beta=_fit(w))
    answer = _module().Underwriter(cfg).on_day(json.loads(json.dumps(day)))
    answer["limit_table"]["period_budget_remaining"] = None
    return {"input": day, "output": answer}


# ── data rendering ───────────────────────────────────────────────────────────

FILES = {
    "history": {"zh": "历史贷款.csv", "en": "past_loans.csv", "ko": "과거_대출실적.csv",
                "ja": "過去の貸付実績.csv", "es": "prestamos_historicos.csv"},
    "bureau": {"zh": "征信数据.csv", "en": "credit_bureau.csv", "ko": "신용평가_정보.csv",
               "ja": "信用情報.csv", "es": "buro_credito.csv"},
    "debts": {"zh": "现有负债.csv", "en": "existing_debts.csv", "ko": "기존_부채.csv",
              "ja": "既存債務.csv", "es": "deudas_existentes.csv"},
    "product": {"zh": "产品说明表.xlsx", "en": "product_sheet.xlsx", "ko": "상품안내표.xlsx",
                "ja": "商品概要表.xlsx", "es": "ficha_producto.xlsx"},
    "sample_in": {"zh": "试点日_输入示例.json", "en": "pilot_day_input.json", "ko": "시범일_입력예시.json",
                  "ja": "試行日_入力例.json", "es": "dia_piloto_entrada.json"},
    "sample_out": {"zh": "试点日_输出示例.json", "en": "pilot_day_output.json", "ko": "시범일_출력예시.json",
                   "ja": "試行日_出力例.json", "es": "dia_piloto_salida.json"},
}
SHEET = {"zh": "个人贷款", "en": "personal_loan", "ko": "개인대출", "ja": "個人ローン", "es": "prestamo_personal"}
COLS = {
    "id": {"zh": "贷款编号", "en": "loan_id", "ko": "대출번호", "ja": "貸付番号", "es": "id_prestamo"},
    "date": {"zh": "放款日期", "en": "funded_date", "ko": "실행일", "ja": "実行日", "es": "fecha_concesion"},
    "requested": {"zh": "申请金额", "en": "requested_amount", "ko": "신청금액", "ja": "申込金額",
                  "es": "importe_solicitado"},
    "age": {"zh": "年龄段", "en": "age_band", "ko": "연령대", "ja": "年齢層", "es": "tramo_edad"},
    "gender": {"zh": "性别", "en": "gender", "ko": "성별", "ja": "性別", "es": "genero"},
    "nationality": {"zh": "国籍", "en": "nationality", "ko": "국적", "ja": "国籍", "es": "nacionalidad"},
    "tenure": {"zh": "现职月数", "en": "months_in_job", "ko": "현직장_근속월수", "ja": "現職勤続月数",
               "es": "meses_en_empleo"},
    "base": {"zh": "月基本工资", "en": "monthly_base_salary", "ko": "월_기본급", "ja": "月額基本給",
             "es": "salario_base_mensual"},
    "bonus": {"zh": "年度奖金", "en": "annual_bonus", "ko": "연간_상여금", "ja": "年間賞与", "es": "bonus_anual"},
    "bonus_doc": {"zh": "奖金有证明", "en": "bonus_documented", "ko": "상여금_증빙", "ja": "賞与証明あり",
                  "es": "bonus_justificado"},
    "stated": {"zh": "申报月收入", "en": "stated_monthly_income", "ko": "신고_월소득", "ja": "申告月収",
               "es": "ingreso_mensual_declarado"},
    "funded": {"zh": "放款金额", "en": "funded_amount", "ko": "실행금액", "ja": "実行金額",
               "es": "importe_concedido"},
    "defaulted": {"zh": "是否违约", "en": "defaulted", "ko": "부도여부", "ja": "デフォルト", "es": "impago"},
    "person": {"zh": "征信档案号", "en": "bureau_file_number", "ko": "신용정보_고유번호", "ja": "信用情報登録番号",
               "es": "numero_expediente_buro"},
    "score_a": {"zh": "A评分机构分数", "en": "bureau_a_score", "ko": "A평가사_점수", "ja": "A社スコア",
                "es": "puntuacion_buro_a"},
    "score_b": {"zh": "B评分机构分数", "en": "bureau_b_score", "ko": "B평가사_점수", "ja": "B社スコア",
                "es": "puntuacion_buro_b"},
    "inquiries": {"zh": "近6个月查询次数", "en": "inquiries_6m", "ko": "최근6개월_조회건수",
                  "ja": "直近6か月照会件数", "es": "consultas_6m"},
    "hist": {"zh": "信用记录月数", "en": "credit_history_months", "ko": "신용거래_개월수", "ja": "信用履歴月数",
             "es": "meses_historial_credito"},
    "debt_id": {"zh": "负债编号", "en": "debt_id", "ko": "부채번호", "ja": "債務番号", "es": "id_deuda"},
    "debt_type": {"zh": "负债类型", "en": "debt_type", "ko": "부채유형", "ja": "債務種別", "es": "tipo_deuda"},
    "balance": {"zh": "未偿余额", "en": "outstanding_balance", "ko": "잔액", "ja": "残高", "es": "saldo_pendiente"},
    "payment": {"zh": "月还款额", "en": "monthly_payment", "ko": "월상환액", "ja": "月返済額", "es": "cuota_mensual"},
    "line_rate": {"zh": "年利率_%", "en": "annual_rate_pct", "ko": "연이율_%", "ja": "年利_%", "es": "tipo_anual_pct"},
    "line_limit": {"zh": "授信额度", "en": "credit_limit", "ko": "약정한도", "ja": "極度額", "es": "limite_credito"},
    "p_code": {"zh": "产品代码", "en": "product_code", "ko": "상품코드", "ja": "商品コード", "es": "codigo_producto"},
    "p_name": {"zh": "产品名称", "en": "product_name", "ko": "상품명", "ja": "商品名", "es": "nombre_producto"},
    "term": {"zh": "期限_月", "en": "term_months", "ko": "기간_개월", "ja": "期間_月", "es": "plazo_meses"},
    "rate": {"zh": "年利率_%", "en": "annual_rate_pct", "ko": "연이율_%", "ja": "年利_%", "es": "tipo_anual_pct"},
    "inst": {"zh": "每借1000月供", "en": "installment_per_1000", "ko": "대출1000당_월상환액",
             "ja": "借入1000あたり月返済額", "es": "cuota_por_1000"},
    "min_amt": {"zh": "最低金额", "en": "min_amount", "ko": "최소금액", "ja": "最低金額", "es": "importe_minimo"},
    "max_amt": {"zh": "每位客户最高金额", "en": "max_amount_per_customer", "ko": "고객당_최대금액",
                "ja": "顧客あたり最高金額", "es": "importe_maximo_por_cliente"},
}
VALUES = {
    "yes": {"zh": "是", "en": "yes", "ko": "예", "ja": "はい", "es": "sí"},
    "no": {"zh": "否", "en": "no", "ko": "아니오", "ja": "いいえ", "es": "no"},
    "female": {"zh": "女", "en": "female", "ko": "여성", "ja": "女性", "es": "mujer"},
    "male": {"zh": "男", "en": "male", "ko": "남성", "ja": "男性", "es": "hombre"},
    "domestic": {"zh": "本国", "en": "domestic", "ko": "내국인", "ja": "国内", "es": "nacional"},
    "foreign": {"zh": "外籍", "en": "foreign", "ko": "외국인", "ja": "外国籍", "es": "extranjera"},
    "66+": {"zh": "66岁及以上", "en": "66+", "ko": "66세 이상", "ja": "66歳以上", "es": "66 o más"},
    "installment": {"zh": "分期贷款", "en": "installment loan", "ko": "분할상환대출", "ja": "分割返済ローン",
                    "es": "préstamo a plazos"},
    "credit_line": {"zh": "循环授信", "en": "credit line", "ko": "마이너스통장", "ja": "カードローン枠",
                    "es": "línea de crédito"},
}
PRODUCT_NAME = {"zh": "安心贷 36期", "en": "Steady Loan 36", "ko": "스테디론 36", "ja": "ステディローン36",
                "es": "Préstamo Estable 36"}


def write_data(world: World, data_dir: Path, lang: str) -> None:
    c, v = labels(COLS, lang), labels(VALUES, lang)
    head = [c[k] for k in ("id", "date", "requested", "age", "gender", "nationality", "tenure", "base", "bonus",
                           "bonus_doc", "stated", "funded", "defaulted")]
    write_csv(data_dir / FILES["history"][lang], head,
              [[a.id, a.date, a.requested, v.get(a.age_band, a.age_band), v[a.gender], v[a.nationality], a.tenure,
                a.base_salary, a.bonus, (v["yes"] if a.bonus_documented else v["no"]) if a.bonus else "",
                a.stated_income, a.funded, v["yes" if a.defaulted else "no"]] for a in world.history])
    write_csv(data_dir / FILES["bureau"][lang],
              [c[k] for k in ("id", "person", "score_a", "score_b", "inquiries", "hist")],
              [[a.id, a.person, a.score_a, a.score_b, a.inquiries, a.history_months] for a in world.history])
    rows = []
    for a in world.history:
        for k, d in enumerate(a.debts, start=1):
            line = d.kind == "credit_line"
            rows.append([a.id, f"{a.id}-D{k}", v[d.kind], d.balance, "" if line else d.monthly_payment,
                         d.rate if line else "", d.line_limit if line else ""])
    write_csv(data_dir / FILES["debts"][lang],
              [c[k] for k in ("id", "debt_id", "debt_type", "balance", "payment", "line_rate", "line_limit")], rows)
    write_xlsx(data_dir / FILES["product"][lang],
               {SHEET[lang]: ([c[k] for k in ("p_code", "p_name", "term", "rate", "inst", "min_amt", "max_amt")],
                              [[PRODUCT, PRODUCT_NAME[lang], TERM, APR, per_1000(), MIN_AMOUNT, MAX_AMOUNT]])})
    for key, part in (("sample_in", "input"), ("sample_out", "output")):
        (data_dir / FILES[key][lang]).write_text(json.dumps(world.sample[part], ensure_ascii=False, indent=1),
                                                 encoding="utf-8")
