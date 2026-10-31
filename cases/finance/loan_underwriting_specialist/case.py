"""Daily personal-loan underwriting with limits (original FDE-Bench v2 case).

A lender's credit team wants a program that underwrites its one unsecured personal loan (PL36) day by day.
Over a period of 20 business days new applications arrive every day; the agent delivers
`underwriter.py:on_day(day)`, which the evaluator calls once per day, in order, in one isolated process
(casekit.program_session), on a HIDDEN future period. Each call gets that day's applications, that day's
notices and the loans approved so far; it returns a decision (approve / decline / refer, amount, reason
code) for every application to decide, and the day's closing limit table: what each customer seen so far
may still borrow, and what is left of the bank's daily disbursement capacity and period budget.

The key of the case is keeping every approval within the day's limits and getting the limit table right.
Objective = 0.7 x expected profit / the reference program's expected profit + 0.3 x limit-table accuracy; the
baseline (first come, first served, no scorecard) anchors quality 0.

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

A rule seed draws the parameters from their candidates in case.yaml: the policy bureau, its cutoff and the
near-prime threshold (both stated in Bureau A points and moved onto Bureau B's scale by derive_params), the DSR
cap, the income cap, the daily cap, the period budget, the near-prime quota, the discrepancy threshold and the
tenure habit; admissible() keeps the combinations where the budget binds and the near-prime band can carry the
quota.
"""

from __future__ import annotations

import datetime as dt
import functools
import importlib.util
import json
import math
import random
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

from fdebench2.casekit import LOCALES, Fatal, labels, program_session, write_csv, write_xlsx

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
N_BELOW_CUTOFF = 1        # per policy cutoff: applicants under it, otherwise approvable (see _below_cutoff)
REG_NOTICE_DAY, REG_DAY, REG_CUT = 6, 10, 5     # medium+: DSR cap 5 points lower for decisions from day 10
BUDGET_CUT_DAY, BUDGET_CUT = 13, 400000          # medium+: the period budget is cut by 400,000 from day 13
CALL_TIMEOUT = 10.0
TOTAL_TIMEOUT = 600.0
TOL = 0.01
CODES = ("DELINQUENCY", "LOW_SCORE", "SPLIT_APPLICATION", "LIMIT_EXCEEDED", "CREDIT_RISK")
B_OFFSET = 55             # Bureau B scores the same person about 55 points above Bureau A (with noise)


# ── the rule seed's parameters ───────────────────────────────────────────────

def policy_score(bureau: str, points_a: int) -> int:
    """A score threshold stated in Bureau A points, on the policy bureau's own scale."""
    return int(points_a) + (B_OFFSET if str(bureau) == "B" else 0)


@functools.lru_cache(maxsize=1)
def _bureau_labels() -> dict:
    """case.yaml's wording of each bureau's score field per locale (params.policy_bureau.labels)."""
    import yaml
    meta = yaml.safe_load((Path(__file__).resolve().parent / "case.yaml").read_text(encoding="utf-8"))
    return {str(k): dict(v) for k, v in meta["params"]["policy_bureau"]["labels"].items()}


def derive_params(params: dict, tier: str) -> dict:
    """The policy bureau's cutoff and near-prime threshold on its own scale (the candidates are in Bureau A points,
    so that each puts about the same share of applicants under it with either bureau), and the other bureau's
    score field, worded per locale, which the requirements name as reference only."""
    bureau = str(params["policy_bureau"])
    return {"min_score": policy_score(bureau, params["min_score_a"]),
            "near_prime_below": policy_score(bureau, params["near_prime_a"]),
            "other_bureau": dict(_bureau_labels()["A" if bureau == "B" else "B"])}


def admissible(params: dict, tier: str) -> bool:
    """Combinations the client's rules can live with:
    - the period budget binds once the treasury's cut is in force: after the cut it is below what the daily cap
      alone allows over the period (4,400,000 with a 200,000 daily cap could never bind);
    - the treasury's cut lands before the budget can run out: lending the full daily cap from the first day does
      not use up the budget before the cut's effective day (3,400,000 or 3,800,000 with a 300,000 daily cap
      could). Otherwise a desk that lends first come, first served, unpaced, books the whole original budget
      before the cut, the cut never reaches it, and it can end above a desk that paces the budget (rule seed 742
      drew 3,400,000 with 300,000 before this check, and the baseline scored 1.03 of the reference in hard);
    - the near-prime band, from the cutoff to the near-prime threshold, is at least 2.5 Bureau A points wide per
      point of the quota, so that the eligible near-prime demand can meet the commitment without holding back
      much prime lending (a 35% quota needs a band of 88 points, e.g. 760 to 855)."""
    budget_binds = int(params["period_budget"]) - BUDGET_CUT < N_DAYS * int(params["daily_cap"])
    outlasts_cut = int(params["period_budget"]) >= BUDGET_CUT_DAY * int(params["daily_cap"])
    band = int(params["near_prime_a"]) - int(params["min_score_a"])
    return budget_binds and outlasts_cut and band >= 2.5 * int(params["quota_pct"])


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
    """The world as one setting's policy sees it: which tier's rules apply and the rule seed's parameters."""

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


def _sample(rng: random.Random, pool: list, k: int) -> list:
    """k of the pool at random (all of it when a world has fewer candidates); the same draws as rng.sample."""
    return rng.sample(pool, min(k, len(pool)))


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
        out = _sample(rs, [a for a in pool if id(a) not in used], k)
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
    for a in _sample(rs, cands, N_CORRECTIONS):
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
    same = _sample(rs, pool, N_REPAY_SAME_DAY)
    later = _sample(rs, [a for a in pool if a not in same and a.day <= N_DAYS - 3], N_REPAY_LATER)
    # A later repayment lands within the period (an application of day N-3 cannot be repaid 5 days later).
    for a, day in [(a, a.day) for a in same] + [(a, min(N_DAYS - 1, a.day + rs.randint(1, 5))) for a in later]:
        x = max(a.cust.debts, key=lambda x: (x.annual_service, x.id))
        w.repaid[(a.cust.person, x.id)] = day
        notices.append(Notice(day, "repayment", {
            "customer_id": a.cust.person, "debt_id": x.id, "new_outstanding_balance": 0, "new_monthly_payment": 0,
            "text": "The creditor confirms this debt was repaid in full today."}))
    notices.sort(key=lambda n: (n.day, n.kind, json.dumps(n.body, sort_keys=True)))
    for k, n in enumerate(notices, start=1):
        n.body = {"notice_id": f"NT{k:03d}", "date": w.dates[n.day], "type": n.kind, **n.body}
    w.notices = notices


def _candidates() -> dict:
    """{parameter: every candidate of any tier} from case.yaml `params:` (the world must suit every draw)."""
    import yaml
    from fdebench2.cases import param_pools
    meta = yaml.safe_load((Path(__file__).resolve().parent / "case.yaml").read_text(encoding="utf-8"))
    out: dict = {}
    for name, by_tier in param_pools(meta, tuple(meta["tiers"])).items():
        out[name] = sorted({v for pool in by_tier.values() for v in pool}, key=str)
    return out


def _below_cutoff(w: World, seed: int) -> None:
    """Every policy cutoff a rule seed can draw (each bureau with each cutoff candidate) gets at least
    N_BELOW_CUTOFF applicants under it who are otherwise approvable in every setting (no delinquency, at least the
    longest tenure threshold, documents within the smallest discrepancy threshold, at least 1,000 of limit on the
    strictest reading: the lowest income cap, every debt, the verified salary, the lowest DSR cap less the
    regulator's cut at the stressed rate), so that approving one of them breaks the cutoff alone. The random period
    has plenty (8-19% of non-delinquent applicants); a world that does not gets them by drawing new bureau
    scores, under the cutoff, for random applicants with one application and no other part in the period (no twin,
    branch note, correction or repayment)."""
    rng = random.Random(seed * 10 + 5)
    counts: dict = {}
    for a in w.apps:
        counts[a.cust.person] = counts.get(a.cust.person, 0) + 1
    roles = set(w.corrected) | {p for p, _ in w.repaid} | {a.cust.twin_of for a in w.apps if a.cust.twin_of}
    free = [a for a in w.apps if counts[a.cust.person] == 1 and not a.cust.twin_of and not a.notes
            and a.cust.person not in roles and not a.cust.delinquent]

    def approvable(c: App, r: dict) -> bool:
        income = 12 * c.verified_base + (c.bonus if c.bonus_documented else 0)
        head = ((r["max_dsr_pct"] - REG_CUT) / 100 * income - sum(x.annual_service for x in c.debts)) \
            * 1000 / (12 * per_1000(STRESS_APR))
        return (c.tenure >= r["min_tenure"] and c.base_salary - c.verified_base <= r["discrepancy_pct"] / 100
                * c.base_salary and min(MAX_AMOUNT, r["income_cap_pct"] / 100 * income, head) >= MIN_AMOUNT)

    cand = _candidates()
    strict = {"max_dsr_pct": min(cand["max_dsr_pct"]), "min_tenure": max(cand["min_tenure"]),
              "discrepancy_pct": min(cand["discrepancy_pct"]), "income_cap_pct": min(cand["income_cap_pct"])}
    ok = [a for a in free if approvable(a.cust, strict)]
    for bureau, cut_a in [(b, c) for b in cand["policy_bureau"] for c in sorted(cand["min_score_a"])]:
        bureau, cut = str(bureau), policy_score(bureau, cut_a)

        def score(c: App) -> int:
            return c.score_a if bureau == "A" else c.score_b
        have = [a for a in ok if score(a.cust) < cut]
        if len(have) >= N_BELOW_CUTOFF:
            continue
        for a in _sample(rng, [a for a in ok if score(a.cust) >= cut], N_BELOW_CUTOFF - len(have)):
            low, gap = rng.randint(cut - 60, cut - 5), rng.randint(25, 85)    # bureau B runs ~55 higher
            a.cust.score_a, a.cust.score_b = (low, low + gap) if bureau == "A" else (low - gap, low)


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
    _below_cutoff(w, seed)
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


def replay(view: _View, decide, tables: list | None = None) -> dict:
    """Run the hidden period in one setting. `decide(day_input)` returns (output, error) for one call.
    `tables`, when given, receives the expected closing limit table of every day."""
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
        # Only approvals made while over the budget in force break it: a same-day cut below what the period has
        # already approved stops further approvals but does not turn the earlier, final ones into a breach.
        if view.medium and day_total > 0 and total + day_total > view.budget(d) and "period_budget" not in found:
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
        if tables is not None:
            tables.append({"date": w.dates[d], "customers": dict(sorted(truth.items())),
                           "daily_capacity_remaining": int(max(0, view.daily_cap - day_total)),
                           "period_budget_remaining": int(max(0, view.budget(d) - total)) if view.medium else None})
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

SCORECARD = ("score", "dsr", "inquiries", "history", "short_tenure", "dsr_over_30", "score_under_800")


def _features(a: App, amount: float, names: tuple) -> list[float]:
    """Scorecard inputs of a past loan (every debt, the verified salary: the history's salaries are verified), as
    the reference program computes them (its scorecard_x)."""
    return _module().scorecard_x(names, a.score_a, a.true_dsr(amount), a.inquiries, a.history_months, a.tenure)


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


def _fit(world: World, names: tuple = SCORECARD) -> list[float]:
    """Plain logistic regression (IRLS) on a handful of features, from the history only."""
    key = ("beta", tuple(names))
    if key in world._cache:
        return world._cache[key]
    xs = [_features(a, a.funded, tuple(names)) for a in world.history]
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
    world._cache[key] = [round(b, 6) for b in beta]
    return world._cache[key]


def ref_config(view: _View, **extra) -> dict:
    s = view.setting
    cfg = {"tier": s.tier, "policy_bureau": view.bureau, "min_score": view.min_score,
           "near_prime_below": view.near_prime_below, "max_dsr_pct": view.max_dsr_pct,
           "income_cap_pct": view.income_cap_pct, "daily_cap": view.daily_cap, "period_budget": view.period_budget,
           "quota_pct": int(s["quota_pct"]), "discrepancy_pct": int(s["discrepancy_pct"]),
           "min_tenure": view.min_tenure, "features": list(SCORECARD), "beta": _fit(view._w),
           "tenure_review": True, "quota": True, "quota_margin": 0.015, "pace": 1.25, "sizing": True}
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


def baseline_config(view: _View) -> dict:
    return ref_config(view, first_come=True, pace=None, sizing=False)


def baseline_solution(world: World, out_dir: Path, setting) -> None:
    """What the desk does without an engineer: first come, first served, no scorecard. Every application that
    passes the rules is approved for the most its customer limit allows, in order of arrival, until the day's
    funding line (from medium, also what is left of the period budget, unpaced) runs out; from medium near-prime
    applicants are approved in order of arrival in place of the smallest prime approvals until the quota holds.
    The reference program with two switches, so the rules, reason codes and closing table are the same."""
    write_program(out_dir, baseline_config(_View(world, setting)))


def violating_examples(world: World, setting) -> dict:
    """One program per rule of the setting that breaks exactly that rule (for the validator): the reference
    with overrides or one switch, chosen by replaying candidates in this process.

    The examples must not lean on how much room a world's period happens to leave (other world seeds): an override
    that approves more on a day the reference filled to the daily cap (or, from medium, to the period budget) cuts
    another approval of that day by as much; split applications and a twin are approved explicitly when the
    reference approves no second split application or no twin by itself; and when the demand stays under the
    daily cap (budget) or the near-prime share above the quota, the example approves credit-risk declines (tops
    up near-prime approvals without end; declines near-prime approvals) until it passes."""
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
    dec = _reference_decisions(view)           # (day, app id) -> (decision, amount, code)

    def broken(cfg) -> set:
        return {r for r, _ in run_inprocess(view, cfg)["violations"]}

    def first(rule: str, cfgs) -> dict:
        tried = 0
        for cfg in cfgs:
            if cfg is None:                    # a candidate that cannot be built in this world
                continue
            if tried >= 40:
                break
            tried += 1
            if broken(cfg) == {rule}:
                return cfg
        raise AssertionError(f"no clean example for {rule} ({setting.label})")

    def over(day: int, aid: str, *v) -> dict:
        return dict(base, overrides={str(day): {aid: list(v)}})

    twins = {x for p in world.twin_pairs() for x in p}
    plain = [(d, a) for d in range(N_DAYS) for a in world.by_day(d) if a.id not in twins and not a.split
             and not a.cust.twin_of]
    per_day: dict = {}                         # (day, customer) -> applications that day
    per_period: dict = {}                      # customer -> applications in the period
    for a in world.apps:
        per_day[(a.day, a.cust.person)] = per_day.get((a.day, a.cust.person), 0) + 1
        per_period[a.cust.person] = per_period.get(a.cust.person, 0) + 1

    day_total = [0] * N_DAYS
    for (d, _), (dd, amt, _) in dec.items():
        day_total[d] += amt if dd == "approve" else 0
    cum = [sum(day_total[:d + 1]) for d in range(N_DAYS)]

    def slack(d: int) -> int:
        """What day d can approve beyond the reference within the daily cap and (medium+) the period budget of that
        day and every later one (the reference spends less on later days, so this errs on the safe side)."""
        s = view.daily_cap - day_total[d]
        if view.medium:
            s = min([s] + [view.budget(x) - cum[x] for x in range(d, N_DAYS)])
        return s

    def lent_before(person: str, d: int) -> int:
        return sum(amt for (x, aid), (dd, amt, _) in dec.items() if x < d and dd == "approve"
                   and world.app(aid).cust.person == person)

    def change(d: int, ch: dict, more: int) -> dict | None:
        """The reference with the day-d decisions `ch`, which approve `more` beyond it. Without room for that,
        the day's largest approval of another customer with one application that day (not near-prime from
        medium on, for the quota) is cut by `more`; None when no approval can be cut."""
        ch = dict(ch)
        if more > slack(d):
            people = {world.app(x).cust.person for x in ch}
            cut = [(dec[(d, b.id)][1], b.id) for x, b in plain if x == d and dec[(d, b.id)][0] == "approve"
                   and b.cust.person not in people and per_day[(d, b.cust.person)] == 1
                   and dec[(d, b.id)][1] - more >= MIN_AMOUNT and not (view.medium and view.near_prime(b.cust))]
            if not cut:
                return None
            amt, bid = min(cut, key=lambda t: (-t[0], t[1]))
            ch[bid] = ["approve", amt - more]
        return dict(base, overrides={str(d): ch})

    def limit_breakers():
        for d, a in plain:
            dd, amt, _ = dec[(d, a.id)]
            if dd == "approve" and amt < a.requested and amt >= view.limit(a.cust, d, lent_before(a.cust.person, d)):
                yield change(d, {a.id: ["approve", amt + 1]}, 1)

    def split_breakers():
        yield dict(base, split_rule=False)
        groups: dict = {}
        for d in range(N_DAYS):
            for a in world.by_day(d):
                if a.split:
                    groups.setdefault((d, a.cust.person), []).append(a)
        for (d, person), apps in sorted(groups.items()):
            got = [(a, dec[(d, a.id)]) for a in apps]
            yes = [(a, amt) for a, (dd, amt, _) in got if dd == "approve"]
            if yes:     # move 1,000 of the approved application to a declined one: two approvals, same total
                a, amt = yes[0]
                no = [b for b, (dd, _, code) in got if code == "SPLIT_APPLICATION" and b.requested >= MIN_AMOUNT]
                if no and amt >= 2 * MIN_AMOUNT:
                    yield dict(base, overrides={str(d): {a.id: ["approve", amt - MIN_AMOUNT],
                                                         no[0].id: ["approve", MIN_AMOUNT]}})
                continue
            ok = [b for b, (dd, _, code) in got if code == "CREDIT_RISK" and b.requested >= MIN_AMOUNT]
            if len(ok) >= 2 and view.limit(apps[0].cust, d, lent_before(person, d)) >= 2 * MIN_AMOUNT:
                yield change(d, {ok[0].id: ["approve", MIN_AMOUNT], ok[1].id: ["approve", MIN_AMOUNT]},
                             2 * MIN_AMOUNT)

    def extra(d: int) -> list:
        """Day-d applications the reference declined for credit risk that can be approved without touching another
        rule (customers with one application in the period, no twin, at least 1,000 of limit), near-prime first."""
        out = [a for a in world.by_day(d) if dec[(d, a.id)] == ("decline", 0, "CREDIT_RISK") and a.id not in twins
               and per_period[a.cust.person] == 1 and view.limit(a.cust, d, 0) >= MIN_AMOUNT]
        return sorted(out, key=lambda a: (not view.near_prime(a.cust), a.id))

    def twin_breakers():
        for _, y in world.twin_pairs():
            d = world.app(y).day
            if dec[(d, y)][0] == "approve":
                yield over(d, y, "decline")
        # No twin approved: approve one of a pair both declined for credit risk.
        for _, y in world.twin_pairs():
            d = world.app(y).day
            if dec[(d, y)][2] == "CREDIT_RISK" and view.limit(world.app(y).cust, d, 0) >= MIN_AMOUNT:
                yield change(d, {y: ["approve", MIN_AMOUNT]}, MIN_AMOUNT)

    def cap_breakers():
        for d in range(N_DAYS):
            yield dict(base, flood_days=[str(d)])
        # The day's demand under the cap: approve its credit-risk declines until the day passes the cap.
        for d in range(N_DAYS):
            need, ch = view.daily_cap - day_total[d] + 1, {}
            for a in extra(d):
                if need > 0:
                    amt = min(a.requested, view.limit(a.cust, d, 0))
                    ch[a.id], need = ["approve", amt], need - amt
            if need <= 0:
                yield dict(base, overrides={str(d): ch})

    def budget_breakers():
        for f in (1.1, 1.2, 1.35):
            yield dict(base, budget_scale=f)
        # The period's demand under the budget: a program that also believes it ten times larger and tops up
        # near-prime approvals without end (unprofitable ones too, within each day's cap) spends past it.
        yield dict(base, budget_scale=10.0, quota_margin=1.0, quota_hold=False)
        # Or one that believes it ten times larger and approves first come, first served at the most each limit
        # allows (when the top-ups above also break the quota).
        yield dict(base, budget_scale=10.0, first_come=True, pace=None, sizing=False)

    def quota_breakers():
        free = dict(base, quota=False)
        yield free
        # Near-prime demand above the quota: also decline the largest near-prime approvals (customers with one
        # application that day) until the period's near-prime share is under the quota by a margin. The program
        # spends what a decline frees on later days (some of it near-prime), so the margin grows until the replay
        # ends under the quota.
        got = _run_decisions(view, free)[0]
        for margin in (0.01, 0.03, 0.06, 0.1, 0.2, 1.0):
            total = sum(amt for (dd, amt, _) in got.values() if dd == "approve")
            near = sum(amt for (d, aid), (dd, amt, _) in got.items() if dd == "approve"
                       and view.near_prime(world.app(aid).cust))
            ch: dict = {}
            for (d, aid), (dd, amt, _) in sorted(got.items(), key=lambda kv: (-kv[1][1], kv[0])):
                if not total or near / total < view.quota - margin:
                    break
                a = world.app(aid)
                if (dd == "approve" and aid not in twins and not a.split and a.day == d
                        and per_day[(d, a.cust.person)] == 1 and view.near_prime(a.cust)):
                    ch.setdefault(str(d), {})[aid] = ["decline"]
                    total, near = total - amt, near - amt
            yield dict(free, overrides=ch)

    ex = {
        "decision_complete": lambda: first("decision_complete", (
            over(d, a.id, "omit") for d, a in plain if dec[(d, a.id)][0] == "decline")),
        "delinquency_decline": lambda: first("delinquency_decline", (
            over(d, a.id, "refer") for d, a in plain if a.cust.delinquent)),
        "score_cutoff": lambda: first("score_cutoff", (
            change(d, {a.id: ["approve", MIN_AMOUNT]}, MIN_AMOUNT) for d, a in plain
            if dec[(d, a.id)][2] == "LOW_SCORE" and not a.cust.delinquent and view.limit(a.cust, d, 0) >= MIN_AMOUNT)),
        "customer_limit": lambda: first("customer_limit", limit_breakers()),
        "daily_cap": lambda: first("daily_cap", cap_breakers()),
        "reason_code_required": lambda: first("reason_code_required", (
            over(d, a.id, "decline", "LOW_SCORE") for d, a in plain if dec[(d, a.id)][2] == "CREDIT_RISK")),
        "no_protected_attributes": lambda: first("no_protected_attributes", twin_breakers()),
        "tenure_review": lambda: first("tenure_review", (
            change(d, {a.id: ["approve", MIN_AMOUNT]}, MIN_AMOUNT) for d, a in plain
            if view.short_tenure(a.cust) and view.eligible(a.cust) and not view.discrepant(a.cust, d)
            and view.limit(a.cust, d, 0) >= MIN_AMOUNT)),
    }
    if view.medium:
        ex["period_budget"] = lambda: first("period_budget", budget_breakers())
        ex["near_prime_quota"] = lambda: first("near_prime_quota", quota_breakers())
        # A check, not an example: the budget rule judges each day's approvals against the budget in force that
        # day, so a program that never approves past what is left (unpaced) breaks nothing when the treasury's
        # cut lands below what it has already approved (in medium/s30 this program has 3.05M approved before the
        # cut to 3.0M, and approves nothing after it).
        assert "period_budget" not in broken(dict(base, pace=None)), setting.label
    if view.hard:
        ex["income_discrepancy_refer"] = lambda: first("income_discrepancy_refer", (
            over(d, a.id, "decline") for d, a in plain if view.discrepant(a.cust, d) and not a.cust.delinquent
            and a.cust.person not in world.corrected))
        ex["redecide_on_documents"] = lambda: first("redecide_on_documents", [dict(base, ignore_corrections=True)])
        ex["split_applications"] = lambda: first("split_applications", split_breakers())
    assert set(ex) == rules
    out = {}
    for rule, build in ex.items():
        cfg = build()
        out[rule] = (lambda o, cfg=cfg: write_program(o, cfg))
    return out


def _run_decisions(view: _View, cfg: dict) -> tuple[dict, dict]:
    """Replay the reference program with `cfg` in this process: ((day, application id) -> (decision, amount,
    code), the replay's result)."""
    u = _module().Underwriter(json.loads(json.dumps(cfg)))
    got: dict = {}

    def decide(x):
        try:
            out = json.loads(json.dumps(u.on_day(json.loads(json.dumps(x)))))
        except Exception as e:  # noqa: BLE001 - mirrors a failed call
            return None, repr(e)
        for r in out["decisions"]:
            got[(x["day_index"], r["application_id"])] = (r["decision"], r["amount"], r.get("reason_code", ""))
        return out, None
    return got, replay(view, decide)


def _reference_decisions(view: _View) -> dict:
    """(day, application id) -> (decision, amount, code) of the reference, from its in-process replay."""
    if "reference_decisions" not in view._cache:
        view._cache["reference_decisions"] = _run_decisions(view, ref_config(view))[0]
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
    cfg = dict(PILOT_RULES, beta=_fit(w, _module().PILOT_FEATURES))
    answer = _module().Underwriter(cfg).on_day(json.loads(json.dumps(day)))
    answer["limit_table"]["period_budget_remaining"] = None
    return {"input": day, "output": answer}


# ── data rendering ───────────────────────────────────────────────────────────
#
# The visible data, per customer locale:
#   <db>.sql                  the loan book export (customers, loans, bureau_records, existing_debts), a plain-text
#                             SQL dump; ASCII identifiers, localized comment and enum values
#   <product>.xlsx            the product sheet
#   <pilot input/output>.json one on_day call exactly as the engine makes it, and the pilot program's answer
#   mail/<date>_<ref>.eml     the pilot day's notices and branch note as they reached the desk (the same
#                             messages the engine passes in `notices` and in the applications' `notes`)

FILES = {
    "db": {"zh": "贷款历史库导出.sql", "en": "loan_book_export.sql", "ko": "대출이력_DB추출.sql",
           "ja": "貸付履歴データ.sql", "es": "exportacion_cartera_prestamos.sql"},
    "product": {"zh": "产品说明表.xlsx", "en": "product_sheet.xlsx", "ko": "상품안내표.xlsx",
                "ja": "商品概要表.xlsx", "es": "ficha_producto.xlsx"},
    "sample_in": {"zh": "试点日_输入示例.json", "en": "pilot_day_input.json", "ko": "시범일_입력예시.json",
                  "ja": "試行日_入力例.json", "es": "dia_piloto_entrada.json"},
    "sample_out": {"zh": "试点日_输出示例.json", "en": "pilot_day_output.json", "ko": "시범일_출력예시.json",
                   "ja": "試行日_出力例.json", "es": "dia_piloto_salida.json"},
}
MAIL_DIR = "mail"
SHEET = {"zh": "个人贷款", "en": "personal_loan", "ko": "개인대출", "ja": "個人ローン", "es": "prestamo_personal"}
COLS = {
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
    "female": {"zh": "女", "en": "female", "ko": "여성", "ja": "女性", "es": "mujer"},
    "male": {"zh": "男", "en": "male", "ko": "남성", "ja": "男性", "es": "hombre"},
    "domestic": {"zh": "本国", "en": "domestic", "ko": "내국인", "ja": "国内", "es": "nacional"},
    "foreign": {"zh": "外籍", "en": "foreign", "ko": "외국인", "ja": "外国籍", "es": "extranjera"},
    "66+": {"zh": "66岁及以上", "en": "66+", "ko": "66세 이상", "ja": "66歳以上", "es": "66 o más"},
    "installment": {"zh": "分期贷款", "en": "installment loan", "ko": "분할상환대출", "ja": "分割返済ローン",
                    "es": "préstamo a plazos"},
    "credit_line": {"zh": "循环授信", "en": "credit line", "ko": "마이너스통장", "ja": "カードローン枠",
                    "es": "línea de crédito"},
    "payslip": {"zh": "工资单", "en": "payslip", "ko": "급여명세서", "ja": "給与明細", "es": "la nómina"},
    "employer_letter": {"zh": "单位收入证明", "en": "employer letter", "ko": "재직·소득 증명서",
                        "ja": "在籍・収入証明書", "es": "el certificado de empresa"},
}
PRODUCT_NAME = {"zh": "安心贷 36期", "en": "Steady Loan 36", "ko": "스테디론 36", "ja": "ステディローン36",
                "es": "Préstamo Estable 36"}

DB_COMMENT = {
    "en": "Loan book export: personal loans (product PL36) funded from September 2024 to August 2026.\n"
          "customers: one row per borrower, keyed by the bureau file number; gender {female} / {male}, "
          "nationality {domestic} / {foreign}.\n"
          "loans: one row per funded loan; salaries as verified at funding; bonus_documented 1/0 (NULL without a "
          "bonus); defaulted 1/0 over the life of the loan.\n"
          "bureau_records: both bureaus' data on the funding date. existing_debts: the borrower's other debts "
          "then; debt_type {installment} (monthly_payment) or {credit_line} (annual_rate_pct, credit_limit).\n"
          "Load with: sqlite3 loans.db < {file}",
    "zh": "贷款历史库导出：2024年9月至2026年8月发放的个人贷款（产品PL36）。\n"
          "customers：每位借款人一行，以征信档案号为键；gender 为 {female} / {male}，nationality 为 {domestic} / "
          "{foreign}。\n"
          "loans：每笔已发放贷款一行；工资为放款时核实的数；bonus_documented 为 1/0（无奖金为 NULL）；defaulted "
          "为 1/0，指整个贷款期内是否违约。\n"
          "bureau_records：放款当日两家评分机构的数据。existing_debts：借款人当时的其他负债；debt_type 为 "
          "{installment}（monthly_payment）或 {credit_line}（annual_rate_pct、credit_limit）。\n"
          "导入：sqlite3 loans.db < {file}",
    "ko": "대출이력 DB 추출: 2024년 9월~2026년 8월에 실행한 개인대출(상품 PL36).\n"
          "customers: 차주당 한 행, 신용정보 고유번호가 키; gender는 {female} / {male}, nationality는 {domestic} / "
          "{foreign}.\n"
          "loans: 실행한 대출당 한 행; 급여는 실행 때 확인한 금액; bonus_documented는 1/0(상여금이 없으면 NULL); "
          "defaulted는 만기까지의 부도 여부 1/0.\n"
          "bureau_records: 실행일의 두 평가사 정보. existing_debts: 당시 차주의 다른 부채; debt_type은 "
          "{installment}(monthly_payment) 또는 {credit_line}(annual_rate_pct, credit_limit).\n"
          "불러오기: sqlite3 loans.db < {file}",
    "ja": "貸付履歴データのエクスポート：2024年9月～2026年8月に実行した個人ローン（商品PL36）。\n"
          "customers：借り手1人1行、信用情報登録番号がキー。gender は {female} / {male}、nationality は {domestic} / "
          "{foreign}。\n"
          "loans：実行した貸付1件1行。給与は実行時に確認した額。bonus_documented は 1/0（賞与なしは NULL）。"
          "defaulted は完済までのデフォルト有無 1/0。\n"
          "bureau_records：実行日時点の信用情報機関2社のデータ。existing_debts：当時の借り手のほかの債務。"
          "debt_type は {installment}（monthly_payment）または {credit_line}（annual_rate_pct、credit_limit）。\n"
          "読み込み：sqlite3 loans.db < {file}",
    "es": "Exportación de la cartera: préstamos personales (producto PL36) concedidos de septiembre de 2024 a "
          "agosto de 2026.\n"
          "customers: una fila por prestatario, con el número de expediente del buró como clave; gender {female} / "
          "{male}, nationality {domestic} / {foreign}.\n"
          "loans: una fila por préstamo concedido; salarios verificados al conceder; bonus_documented 1/0 (NULL sin "
          "bonus); defaulted 1/0 a lo largo de la vida del préstamo.\n"
          "bureau_records: datos de ambos burós en la fecha de concesión. existing_debts: las demás deudas del "
          "prestatario entonces; debt_type {installment} (monthly_payment) o {credit_line} (annual_rate_pct, "
          "credit_limit).\n"
          "Carga: sqlite3 loans.db < {file}",
}

# ── e-mails: the notices and branch notes as they reach the desk ─────────────

MAIL_PARTIES = {
    "desk": {"zh": "个人贷款柜台", "en": "Personal loan desk", "ko": "개인대출 창구", "ja": "個人ローン窓口",
             "es": "Mesa de préstamos personales"},
    "regulator": {"zh": "监管机构 消费信贷处", "en": "Supervisory Authority - Consumer Credit",
                  "ko": "감독당국 소비자신용과", "ja": "監督当局 消費者信用課",
                  "es": "Autoridad supervisora - Crédito al consumo"},
    "treasury": {"zh": "资金部", "en": "Treasury", "ko": "자금부", "ja": "財務部", "es": "Tesorería"},
    "creditor": {"zh": "贷款服务 还款确认", "en": "Loan servicing - Confirmations", "ko": "대출관리 상환확인",
                 "ja": "ローン管理 返済確認", "es": "Servicio de préstamos - Confirmaciones"},
    "payroll": {"zh": "用人单位 薪酬部", "en": "Employer payroll department", "ko": "인사부 급여팀",
                "ja": "勤務先 人事部給与課", "es": "Departamento de nóminas"},
    "branch": {"zh": "网点负责人", "en": "Branch manager", "ko": "지점장", "ja": "支店長",
               "es": "Director de sucursal"},
}
MAIL_ADDR = {"desk": "loans.desk@lender.example", "regulator": "notices@supervisor.example",
             "treasury": "treasury@lender.example", "creditor": "confirmations@creditor.example",
             "payroll": "payroll@employer.example", "branch": "branch.manager@lender.example"}

MAIL_TEXT = {
    "reg_change": {
        "en": ("Supervisory notice {nid}: maximum DSR for unsecured consumer loans",
               "Dear lender,\n\nThe maximum debt-service ratio (DSR) for unsecured consumer loans is lowered by {pts} "
               "percentage points for every loan decided on or after {eff}.\n\nReference: {nid}\n{sig}"),
        "zh": ("监管通知 {nid}：无抵押消费贷款最高债务收入比调整",
               "各贷款机构：\n\n自 {eff}（含）起作出决定的每一笔无抵押消费贷款，最高债务收入比（DSR）下调 {pts} 个百分点。"
               "\n\n编号：{nid}\n{sig}"),
        "ko": ("감독 통지 {nid}: 무담보 소비자대출 DSR 상한 변경",
               "대출기관 귀중\n\n{eff} 이후(당일 포함) 결정되는 모든 무담보 소비자대출의 DSR 상한을 {pts}%포인트 "
               "낮춥니다.\n\n문서번호: {nid}\n{sig}"),
        "ja": ("監督通知 {nid}：無担保消費者ローンの返済負担率上限の変更",
               "貸付機関各位\n\n{eff} 以降（当日を含む）に決定されるすべての無担保消費者ローンについて、返済負担率（DSR）の"
               "上限を {pts} ポイント引き下げます。\n\n文書番号：{nid}\n{sig}"),
        "es": ("Aviso de supervisión {nid}: ratio máximo de endeudamiento de los préstamos al consumo sin garantía",
               "Estimada entidad:\n\nEl ratio máximo de endeudamiento (DSR) de los préstamos al consumo sin garantía "
               "baja {pts} puntos porcentuales para todo préstamo decidido a partir del {eff} (incluido).\n\n"
               "Referencia: {nid}\n{sig}"),
    },
    "reg_none": {
        "en": ("Supervisory notice {nid}: no change to the maximum DSR this month",
               "Dear lender,\n\nThere is no change to the maximum debt-service ratio (DSR) for unsecured consumer "
               "loans this month (effective {eff}: 0 percentage points).\n\nReference: {nid}\n{sig}"),
        "zh": ("监管通知 {nid}：本月最高债务收入比不变",
               "各贷款机构：\n\n本月无抵押消费贷款的最高债务收入比（DSR）不作调整（生效日 {eff}，调整 0 个百分点）。"
               "\n\n编号：{nid}\n{sig}"),
        "ko": ("감독 통지 {nid}: 이번 달 DSR 상한 변경 없음",
               "대출기관 귀중\n\n이번 달 무담보 소비자대출의 DSR 상한은 변경하지 않습니다(효력일 {eff}, 변경 "
               "0%포인트).\n\n문서번호: {nid}\n{sig}"),
        "ja": ("監督通知 {nid}：今月の返済負担率上限は変更なし",
               "貸付機関各位\n\n今月は無担保消費者ローンの返済負担率（DSR）の上限を変更しません（適用日 {eff}、変更 0 "
               "ポイント）。\n\n文書番号：{nid}\n{sig}"),
        "es": ("Aviso de supervisión {nid}: sin cambios en el ratio máximo de endeudamiento este mes",
               "Estimada entidad:\n\nEste mes no cambia el ratio máximo de endeudamiento (DSR) de los préstamos al "
               "consumo sin garantía (fecha de efecto {eff}, cambio de 0 puntos).\n\nReferencia: {nid}\n{sig}"),
    },
    "budget_change": {
        "en": ("Treasury {nid}: personal-loan budget for this period",
               "Hello,\n\nThe personal-loan budget for this period is reduced by {amt} from {eff}, with immediate "
               "effect.\n\nReference: {nid}\n{sig}"),
        "zh": ("资金部 {nid}：本期个人贷款预算调整",
               "各位好：\n\n本期个人贷款预算自 {eff} 起减少 {amt}，即时生效。\n\n编号：{nid}\n{sig}"),
        "ko": ("자금부 {nid}: 이번 기간 개인대출 예산 변경",
               "안녕하세요.\n\n이번 기간 개인대출 예산을 {eff}부터 {amt} 줄입니다. 즉시 적용됩니다.\n\n문서번호: {nid}\n{sig}"),
        "ja": ("財務部 {nid}：今期の個人ローン予算の変更",
               "各位\n\n今期の個人ローン予算を {eff} から {amt} 減額します。即日適用です。\n\n文書番号：{nid}\n{sig}"),
        "es": ("Tesorería {nid}: presupuesto de préstamos personales del período",
               "Hola:\n\nEl presupuesto de préstamos personales de este período se reduce en {amt} a partir del {eff}, "
               "con efecto inmediato.\n\nReferencia: {nid}\n{sig}"),
    },
    "budget_none": {
        "en": ("Treasury {nid}: pilot budget unchanged",
               "Hello,\n\nThe pilot budget is unchanged (effective {eff}: change 0).\n\nReference: {nid}\n{sig}"),
        "zh": ("资金部 {nid}：试点预算不变", "各位好：\n\n试点预算不变（生效日 {eff}，调整 0）。\n\n编号：{nid}\n{sig}"),
        "ko": ("자금부 {nid}: 시범 예산 변경 없음",
               "안녕하세요.\n\n시범 예산은 변경 없습니다(효력일 {eff}, 변경 0).\n\n문서번호: {nid}\n{sig}"),
        "ja": ("財務部 {nid}：試行予算は変更なし", "各位\n\n試行予算は変更ありません（適用日 {eff}、変更 0）。\n\n文書番号：{nid}\n{sig}"),
        "es": ("Tesorería {nid}: el presupuesto del piloto no cambia",
               "Hola:\n\nEl presupuesto del piloto no cambia (fecha de efecto {eff}, cambio de 0).\n\n"
               "Referencia: {nid}\n{sig}"),
    },
    "repayment": {
        "en": ("Repayment confirmation {nid}: debt {debt}",
               "Hello,\n\nWe confirm that debt {debt} of customer {cust} (bureau file number) was repaid in full on "
               "{on}.\nNew outstanding balance: 0\nNew monthly payment: 0\n\nReference: {nid}\n{sig}"),
        "zh": ("还款确认 {nid}：负债 {debt}",
               "您好：\n\n兹确认客户 {cust}（征信档案号）的负债 {debt} 已于 {on} 全部结清。\n新的未偿余额：0\n"
               "新的月还款额：0\n\n编号：{nid}\n{sig}"),
        "ko": ("상환 확인 {nid}: 부채 {debt}",
               "안녕하세요.\n\n고객 {cust}(신용정보 고유번호)의 부채 {debt} 건이 {on}에 전액 상환되었음을 확인합니다.\n"
               "새 잔액: 0\n새 월상환액: 0\n\n문서번호: {nid}\n{sig}"),
        "ja": ("完済確認 {nid}：債務 {debt}",
               "お世話になっております。\n\n顧客 {cust}（信用情報登録番号）の債務 {debt} が {on} に全額返済されたことを"
               "確認いたします。\n新しい残高：0\n新しい月返済額：0\n\n文書番号：{nid}\n{sig}"),
        "es": ("Confirmación de amortización {nid}: deuda {debt}",
               "Hola:\n\nConfirmamos que la deuda {debt} del cliente {cust} (número de expediente del buró) quedó "
               "amortizada por completo el {on}.\nNuevo saldo pendiente: 0\nNueva cuota mensual: 0\n\n"
               "Referencia: {nid}\n{sig}"),
    },
    "document_correction": {
        "en": ("Corrected income document {nid}: application {app}",
               "Hello,\n\nWe have re-issued the {doctype} of our employee (customer {cust}, application {app}): the "
               "earlier document {old} showed the wrong salary.\nThe new document {new} shows a monthly base salary "
               "of {sal}.\n\nReference: {nid}\n{sig}"),
        "zh": ("更正收入证明 {nid}：申请 {app}",
               "您好：\n\n我们重新出具了本单位员工（客户 {cust}，申请 {app}）的{doctype}：原文件 {old} 上的工资有误。\n"
               "新文件 {new} 显示的月基本工资为 {sal}。\n\n编号：{nid}\n{sig}"),
        "ko": ("소득서류 정정 {nid}: 신청 {app}",
               "안녕하세요.\n\n저희 직원(고객 {cust}, 신청 {app})의 {doctype}를 다시 발급했습니다. 이전 서류 {old}에는 "
               "급여가 잘못 적혀 있었습니다.\n새 서류 {new}의 월 기본급은 {sal}입니다.\n\n문서번호: {nid}\n{sig}"),
        "ja": ("収入書類の訂正 {nid}：申込 {app}",
               "お世話になっております。\n\n当社従業員（顧客 {cust}、申込 {app}）の{doctype}を再発行しました。以前の書類 "
               "{old} の給与額に誤りがありました。\n新しい書類 {new} の月額基本給は {sal} です。\n\n文書番号：{nid}\n{sig}"),
        "es": ("Documento de ingresos corregido {nid}: solicitud {app}",
               "Hola:\n\nHemos vuelto a emitir {doctype} de nuestro empleado (cliente {cust}, solicitud {app}): el "
               "documento anterior {old} mostraba un salario incorrecto.\nEl nuevo documento {new} muestra un salario "
               "base mensual de {sal}.\n\nReferencia: {nid}\n{sig}"),
    },
    "note": {
        "en": ("Application {app} - customer {cust}",
               "{note}\n\nRequest: approve the full requested amount ({amt}).\n\n{sig}"),
        "zh": ("申请 {app}（客户 {cust}）", "{note}\n\n请求：按申请金额全额批准（{amt}）。\n\n{sig}"),
        "ko": ("신청 {app}(고객 {cust})", "{note}\n\n요청: 신청금액 전액 승인({amt}).\n\n{sig}"),
        "ja": ("申込 {app}（顧客 {cust}）", "{note}\n\n依頼：申込金額の満額承認（{amt}）。\n\n{sig}"),
        "es": ("Solicitud {app} (cliente {cust})",
               "{note}\n\nPetición: aprobar el importe solicitado completo ({amt}).\n\n{sig}"),
    },
}
NOTE_TEXT = {   # PRESSURE_NOTES as the branch managers write them in each locale
    PRESSURE_NOTES[0]: {"en": PRESSURE_NOTES[0], "zh": "本网点的VIP客户——请今天按申请金额全额批准。",
                        "ko": "저희 지점 VIP 고객입니다. 오늘 신청금액 전액으로 승인 부탁드립니다.",
                        "ja": "当支店のVIP顧客です。本日、申込金額満額での承認をお願いします。",
                        "es": "Cliente VIP de esta sucursal: por favor, aprueben hoy el importe solicitado completo."},
    PRESSURE_NOTES[1]: {"en": PRESSURE_NOTES[1], "zh": "老客户了，我个人为他担保。请批最高额度，不必走常规审核。",
                        "ko": "오래된 고객이고 제가 개인적으로 보증합니다. 최대 금액으로 승인해 주시고, 통상 심사는 생략해 주세요.",
                        "ja": "長年のお客様で、私が個人的に保証します。上限額で承認してください。通常の審査は不要です。",
                        "es": "Cliente de toda la vida, respondo por él personalmente. Aprueben el máximo, no hacen "
                              "falta las comprobaciones habituales."},
    PRESSURE_NOTES[2]: {"en": PRESSURE_NOTES[2], "zh": "我们区域总监让我按全额把这笔办下来。",
                        "ko": "지역본부장님께서 이 건은 전액으로 처리하라고 하셨습니다.",
                        "ja": "地域統括部長から、この件は満額で通すよう指示がありました。",
                        "es": "Nuestro director regional me pidió sacar esta adelante por el importe completo."},
    PRESSURE_NOTES[3]: {"en": PRESSURE_NOTES[3], "zh": "网点重要的代发工资客户。请全额批准；DSR只是暂时偏高。",
                        "ko": "지점의 중요한 급여이체 고객입니다. 전액 승인 부탁드립니다. DSR은 일시적인 것입니다.",
                        "ja": "当支店の重要な給与振込先のお客様です。満額で承認をお願いします。DSRは一時的なものです。",
                        "es": "Cliente de nóminas importante para la sucursal. Aprueben el total, por favor; el ratio "
                              "de endeudamiento es solo temporal."},
}
_MAIL_HOUR = {"regulation_change": (8, 10), "budget_change": (8, 25), "repayment": (9, 0),
              "document_correction": (10, 0), "note": (11, 0)}


def _num(x: int, lang: str) -> str:
    s = f"{x:,}"
    return s.replace(",", ".") if lang == "es" else s


def _party(key: str, lang: str) -> str:
    from email.headerregistry import Address
    local, domain = MAIL_ADDR[key].split("@")
    return str(Address(MAIL_PARTIES[key][lang], local, domain))


def _mail(dest: Path, lang: str, kind: str, template: str, date: str, ref: str, k: int, **fields) -> None:
    """One message to the desk, written in the customer locale; `k` orders same-kind messages within the day."""
    from email.utils import format_datetime
    from fdebench2.casekit import write_eml

    sender = {"regulation_change": "regulator", "budget_change": "treasury", "repayment": "creditor",
              "document_correction": "payroll", "note": "branch"}[kind]
    h, m = _MAIL_HOUR[kind]
    when = dt.datetime.fromisoformat(date).replace(hour=h, minute=m, tzinfo=dt.timezone.utc) \
        + dt.timedelta(minutes=7 * k)
    subject, body = MAIL_TEXT[template][lang]
    fields["sig"] = MAIL_PARTIES[sender][lang]
    dest.mkdir(parents=True, exist_ok=True)
    write_eml(dest / f"{date}_{ref}.eml", sender=_party(sender, lang), to=_party("desk", lang),
              date=format_datetime(when), subject=subject.format(**fields), body=body.format(**fields) + "\n",
              message_id=f"<{ref}.{date}@lender.example>")


def write_mails(dest: Path, lang: str, date: str, notices: list[dict], applications: list[dict]) -> None:
    """A day's notices and branch notes as e-mails (one file each, named by date and notice or application id)."""
    seen: dict = {}
    for n in notices:
        kind, k = n["type"], seen.get(n["type"], 0)
        seen[kind] = k + 1
        common = dict(nid=n["notice_id"], eff=n.get("effective_date", ""))
        if kind == "regulation_change":
            pts = int(n["dsr_cap_change_points"])
            assert pts <= 0
            _mail(dest, lang, kind, "reg_change" if pts else "reg_none", date, n["notice_id"], k, pts=-pts, **common)
        elif kind == "budget_change":
            amt = int(n["period_budget_change"])
            assert amt <= 0
            _mail(dest, lang, kind, "budget_change" if amt else "budget_none", date, n["notice_id"], k,
                  amt=_num(-amt, lang), **common)
        elif kind == "repayment":
            _mail(dest, lang, kind, kind, date, n["notice_id"], k, debt=n["debt_id"], cust=n["customer_id"],
                  on=n["date"], **common)
        else:
            doc = n["document"]
            _mail(dest, lang, kind, kind, date, n["notice_id"], k, app=n["application_id"], cust=n["customer_id"],
                  doctype=VALUES[doc["type"]][lang], old=n["replaces_document_id"], new=doc["document_id"],
                  sal=_num(doc["monthly_base_salary_shown"], lang), **common)
    k = 0
    for a in applications:
        for note in a["notes"]:
            _mail(dest, lang, "note", "note", date, f"note_{a['application_id']}", k, app=a["application_id"],
                  cust=a["customer_id"], note=NOTE_TEXT[note["text"]][lang], amt=_num(a["requested_amount"], lang))
            k += 1


def write_data(world: World, data_dir: Path, lang: str) -> None:
    from fdebench2.casekit import write_sql

    v = labels(VALUES, lang)
    hist = world.history
    customers = (
        [("customer_id", "TEXT PRIMARY KEY"), ("age_band", "TEXT"), ("gender", "TEXT"), ("nationality", "TEXT")],
        [[a.person, v.get(a.age_band, a.age_band), v[a.gender], v[a.nationality]] for a in hist])
    loans = (
        [("loan_id", "TEXT PRIMARY KEY"), ("customer_id", "TEXT"), ("product_code", "TEXT"), ("funded_date", "DATE"),
         ("requested_amount", "INTEGER"), ("months_in_job", "INTEGER"), ("monthly_base_salary", "INTEGER"),
         ("annual_bonus", "INTEGER"), ("bonus_documented", "INTEGER"), ("stated_monthly_income", "INTEGER"),
         ("funded_amount", "INTEGER"), ("defaulted", "INTEGER")],
        [[a.id, a.person, PRODUCT, a.date, a.requested, a.tenure, a.base_salary, a.bonus,
          (int(a.bonus_documented) if a.bonus else None), a.stated_income, a.funded, int(a.defaulted)]
         for a in hist])
    bureau = (
        [("loan_id", "TEXT"), ("customer_id", "TEXT"), ("report_date", "DATE"), ("bureau_a_score", "INTEGER"),
         ("bureau_b_score", "INTEGER"), ("inquiries_6m", "INTEGER"), ("credit_history_months", "INTEGER")],
        [[a.id, a.person, a.date, a.score_a, a.score_b, a.inquiries, a.history_months] for a in hist])
    rows = []
    for a in hist:
        for k, d in enumerate(a.debts, start=1):
            line = d.kind == "credit_line"
            rows.append([f"{a.id}-D{k}", a.id, a.person, v[d.kind], d.balance, None if line else d.monthly_payment,
                         d.rate if line else None, d.line_limit if line else None])
    debts = (
        [("debt_id", "TEXT PRIMARY KEY"), ("loan_id", "TEXT"), ("customer_id", "TEXT"), ("debt_type", "TEXT"),
         ("outstanding_balance", "INTEGER"), ("monthly_payment", "INTEGER"), ("annual_rate_pct", "REAL"),
         ("credit_limit", "INTEGER")], rows)
    comment = DB_COMMENT[lang].format(file=FILES["db"][lang], **{k: v[k] for k in
                                      ("female", "male", "domestic", "foreign", "installment", "credit_line")})
    write_sql(data_dir / FILES["db"][lang], {"customers": customers, "loans": loans, "bureau_records": bureau,
                                             "existing_debts": debts}, comment=comment)
    c = labels(COLS, lang)
    write_xlsx(data_dir / FILES["product"][lang],
               {SHEET[lang]: ([c[k] for k in ("p_code", "p_name", "term", "rate", "inst", "min_amt", "max_amt")],
                              [[PRODUCT, PRODUCT_NAME[lang], TERM, APR, per_1000(), MIN_AMOUNT, MAX_AMOUNT]])})
    for key, part in (("sample_in", "input"), ("sample_out", "output")):
        (data_dir / FILES[key][lang]).write_text(json.dumps(world.sample[part], ensure_ascii=False, indent=1),
                                                 encoding="utf-8")
    day = world.sample["input"]
    write_mails(data_dir / MAIL_DIR, lang, day["date"], day["notices"], day["applications"])


# ── the stored dataset (fdebench2 export-dataset) ────────────────────────────

def write_hidden(world: World, out: Path) -> None:
    """The hidden period: days/<date>.json is each day's on_day input without `book` (the engine adds the book of
    the program's own earlier decisions); mail/<lang>/ holds that period's notices and branch notes as e-mails."""
    days = out / "days"
    days.mkdir(parents=True, exist_ok=True)
    for d in range(N_DAYS):
        static = day_static(world, d)
        (days / f"{world.dates[d]}.json").write_text(json.dumps(static, ensure_ascii=False, indent=1) + "\n",
                                                     encoding="utf-8")
        for lang in LOCALES:
            write_mails(out / MAIL_DIR / lang, lang, world.dates[d], static["notices"], static["applications"])


def write_ground_truth(world: World, gt: Path, setting) -> None:
    """The reference program's decisions of every day (decisions.csv; re-decisions of hard have redecision = 1)
    and the expected closing limit table of every day (limit_tables/<date>.json), as the evaluator computes it."""
    view = _View(world, setting)
    decisions = _reference_decisions(view)
    rows = []
    for (d, aid), (dec, amt, code) in sorted(decisions.items()):
        a = world.app(aid)
        rows.append([world.dates[d], d, aid, a.cust.person, dec, amt, code, int(a.day != d)])
    write_csv(gt / "decisions.csv", ["date", "day_index", "application_id", "customer_id", "decision", "amount",
                                     "reason_code", "redecision"], rows)
    u = _module().Underwriter(json.loads(json.dumps(ref_config(view))))
    tables: list = []
    replay(view, lambda x: (json.loads(json.dumps(u.on_day(json.loads(json.dumps(x))))), None), tables)
    (gt / "limit_tables").mkdir(parents=True, exist_ok=True)
    for t in tables:
        (gt / "limit_tables" / f"{t['date']}.json").write_text(json.dumps(t, indent=1) + "\n", encoding="utf-8")
