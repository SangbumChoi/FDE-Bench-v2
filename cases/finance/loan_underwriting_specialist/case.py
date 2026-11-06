"""Daily personal-loan underwriting with limits (original FDE-Bench v2 case).

A lender's credit team wants a program that underwrites its one unsecured personal loan (PL36) day by day.
Over a period of 20 business days new applications arrive every day; the agent delivers
`underwriter.py:on_day(day)`, which the evaluator calls once per day, in order, in one isolated process
(casekit.program_session), on a HIDDEN future period. Each call gets that day's applications, that day's
notices and the loans approved so far; it returns a decision (approve / decline / refer, amount, reason
code) for every application to decide, and the day's closing limit table: what each customer seen so far
may still borrow, and what is left of the bank's daily disbursement capacity and period budget.

The key of the case is keeping every approval within the day's limits and getting the limit table right. The table
is a mandatory output (limit_table_complete), and objective = expected profit / the reference program's expected
profit x limit-table accuracy, scored on the entries that change each day, so no profit buys a wrong table back;
the baseline (first come, first served, no scorecard) anchors quality 0. Referrals beyond the mandated ones are
capped at the underwriters' capacity (referral_capacity), so referring is no way around the reason codes.

The ground truth audit hooks (ablations, shortcuts, robust_solution, best_known_solution, objective_bound and the
per-target diagnostic diagnose(), which reads the run score() records) are documented where they are defined; GT.md
holds what they measure.

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
          tier: following them breaks a limit or the tenure habit.

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
REFERRAL_CAPACITY = 3     # referrals a day beyond those the tenure habit (hard: also the discrepancy rule) requires
LINE_YEARS = 5            # medium+: credit lines count as their balance repaid over 5 years plus interest
STRESS_THRESHOLD = 60000  # medium+: total unsecured debt after the loan above this -> stressed rate

N_HISTORY = 3000
N_DAYS = 20
FIRST_DAY = dt.date(2026, 11, 2)     # a Monday
N_TWINS = 14
N_SPLITS = 12
N_RETURNING = 45
N_CORRECTIONS = 8
N_REPAY_SAME_DAY, N_REPAY_LATER = 7, 8
N_PRESSURE = 10
N_SHORT_NOTES = 3         # of the six notes drawn on over-limit requests, three move to applicants new in their job
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
    """The world as one setting's policy sees it: which tier's rules apply and the rule seed's parameters.

    `misread` reads some client facts the other way, as the case's ablations do (MISREADINGS): the diagnostics
    compare a deliverable's limit table with the true one and with such a misreading."""

    def __init__(self, world: World, setting, misread=()):
        self._w, self.setting = world, setting
        self.misread = frozenset(misread)
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
        mis = self.misread
        self.lines = self.medium or "lines_in" in mis or "lines_interest" in mis
        self.stress = self.medium and "no_stress" not in mis
        self.verified = (self.hard and "declared_income" not in mis) or "verify_income" in mis
        self.repayments = (self.hard and "ignore_repayments" not in mis) or "apply_repayments" in mis
        self.reg = (self.medium and "ignore_reg_notice" not in mis) or "apply_reg_notice" in mis
        self._cache = world._cache.setdefault(("setting", setting.label, self.misread), {})

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

    def mandated_referral(self, c: App, d: int) -> bool:
        """Whether the rules send this application to an underwriter: the tenure habit, and in hard the income
        discrepancy procedure (a delinquent applicant is declined instead)."""
        return not c.delinquent and (self.short_tenure(c) or self.discrepant(c, d))

    def dsr_cap_pct(self, d: int) -> int:
        """The DSR cap of day d (misread "reg_on_notice": the regulator's cut from the day its notice arrives)."""
        start = REG_NOTICE_DAY if "reg_on_notice" in self.misread else REG_DAY
        return self.max_dsr_pct - (REG_CUT if self.reg and d >= start else 0)

    def budget(self, d: int) -> int:
        return self.period_budget - (BUDGET_CUT if d >= BUDGET_CUT_DAY else 0)

    def debts(self, c: App, d: int) -> list[Debt]:
        """Hard: every repayment notice up to day d applied; easy/medium: the bureau snapshot of the customer's
        latest application. Easy counts installment loans only."""
        if self.repayments:
            debts = self._w.debts_at(c, d, inclusive=True)
        else:
            debts = self._w.debts_at(c, self._w.snapshot_day(c, d), inclusive=False)
        return debts if self.lines else [x for x in debts if x.kind == "installment"]

    def service(self, x: Debt) -> float:
        if x.kind == "credit_line" and "lines_interest" in self.misread:
            return x.balance * x.rate / 100
        return x.annual_service

    def base(self, c: App, d: int) -> int:
        """Hard: the verified salary (lowest of declared and the documents); easy/medium: the declared one."""
        if not self.verified:
            return c.base_salary
        return min([c.base_salary] + [x.base_salary for x in self._w.docs_at(c, d)])

    def income(self, c: App, d: int) -> int:
        bonus = c.bonus_documented or "count_bonus" in self.misread
        return 12 * self.base(c, d) + (c.bonus if bonus else 0)

    def discrepant(self, c: App, d: int) -> bool:
        return self.hard and c.base_salary - self.base(c, d) > self.discrepancy * c.base_salary + 1e-9

    def _terms(self, c: App, d: int) -> tuple:
        key = ("terms", c.person, d)
        if key not in self._cache:
            debts = self.debts(c, d)
            self._cache[key] = (self.income(c, d), sum(self.service(x) for x in debts),
                                sum(x.balance for x in debts), self.dsr_cap_pct(d))
        return self._cache[key]

    def dsr(self, c: App, d: int, ours: float) -> float:
        """DSR with `ours` of our PL36 lending to the customer outstanding (earlier and new approvals)."""
        income, service, balances, _ = self._terms(c, d)
        stressed = self.stress and balances + ours > STRESS_THRESHOLD
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
        return max(0, self.limit(c, d, lent)) if self.eligible(c) or "formula" in self.misread else 0


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
    over_noted = pick(over, 6)
    for k, a in enumerate(over_noted + pick(bad, N_PRESSURE - 6)):
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
    # Same-day repayments go first to customers whose limit the repayment lifts from under 1,000 to several thousand
    # in every setting (so a program that misses the repayment, or applies it when the round does not, decides and
    # codes them wrongly: F8), eligible in every setting and past every tenure threshold where the period has them.
    rank = {id(a): _repayment_rank(a.cust) for a in pool}
    same: list = []
    for r in range(4):
        same += _sample(rs, [a for a in pool if rank[id(a)] == r], N_REPAY_SAME_DAY - len(same))
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
    _renote(w, seed, over_noted[6 - N_SHORT_NOTES:])


def _strict_limit(c: App) -> float:
    """A lower bound of a first application's customer limit under every setting: every debt (credit lines as from
    medium), the verified salary, the lowest income cap, the lowest DSR cap less the regulator's cut, at the stressed
    rate."""
    cand = _candidates()
    income = 12 * c.verified_base + (c.bonus if c.bonus_documented else 0)
    head = ((min(cand["max_dsr_pct"]) - REG_CUT) / 100 * income - sum(x.annual_service for x in c.debts)) \
        * 1000 / (12 * per_1000(STRESS_APR))
    return min(MAX_AMOUNT, min(cand["income_cap_pct"]) / 100 * income, head)


def _repayment_rank(c: App) -> int:
    """How well repaying the customer's largest debt (by annual service) tests the repayment rules, 0 best: the
    limit under 1,000 before it and at least 3,000 after it in every setting, read as hard reads it (every debt, the
    verified salary, the lowest income cap; after it, the DSR cap less the regulator's cut) and as easy reads it
    (installment loans, the declared salary), the customer eligible under every cutoff and past every tenure
    threshold (0); the same without the tenure (1); in hard's reading only (2); anything else (3)."""
    cand = _candidates()
    x = max(c.debts, key=lambda x: (x.annual_service, x.id))
    rest = [y for y in c.debts if y is not x]

    def head(debts, dsr, hard) -> float:
        income = 12 * (c.verified_base if hard else c.base_salary) + (c.bonus if c.bonus_documented else 0)
        service = sum(y.annual_service for y in debts if hard or y.kind == "installment")
        return min(MAX_AMOUNT, min(cand["income_cap_pct"]) / 100 * income,
                   (dsr * income - service) * 1000 / (12 * per_1000(STRESS_APR if hard else APR)))

    def crosses(hard: bool) -> bool:
        return all(head(c.debts, p / 100, hard) < MIN_AMOUNT and head(rest, (p - REG_CUT) / 100, hard) >= 3000
                   for p in cand["max_dsr_pct"])
    top = max(cand["min_score_a"])
    eligible = c.score_a >= top and c.score_b >= policy_score("B", top)
    if eligible and crosses(True) and crosses(False):
        return 0 if c.tenure >= max(cand["min_tenure"]) else 1
    return 2 if eligible and crosses(True) else 3


def _renote(w: World, seed: int, movable: list) -> None:
    """Three of the six branch notes drawn on requests over every limit move to applicants new in their job (F8):
    under every tenure threshold, so referred in every setting (a branch manager cannot grant the head of credit's
    exception), and otherwise eligible and within their limit in every setting, with one application in the period
    and no other part in it. Following such a note breaks the tenure habit even within the limits. Drawn with its
    own random stream once the period is built, so nothing else in the period moves."""
    rng = random.Random(seed * 10 + 12)
    cand = _candidates()
    counts: dict = {}
    for a in w.apps:
        counts[a.cust.person] = counts.get(a.cust.person, 0) + 1
    roles = set(w.corrected) | {p for p, _ in w.repaid} | {a.cust.twin_of for a in w.apps if a.cust.twin_of}
    top = max(cand["min_score_a"])
    short = [a for a in w.apps if counts[a.cust.person] == 1 and not a.cust.twin_of and not a.notes and not a.split
             and a.cust.person not in roles and not a.cust.delinquent and a.cust.tenure < min(cand["min_tenure"])
             and a.cust.score_a >= top and a.cust.score_b >= policy_score("B", top)
             and a.requested <= _strict_limit(a.cust)
             and a.cust.base_salary - a.cust.verified_base <= min(cand["discrepancy_pct"]) / 100 * a.cust.base_salary]
    for src, dst in zip(movable, _sample(rng, short, N_SHORT_NOTES)):
        src.notes = []
        dst.notes = [{"author_role": "branch_manager", "request": "approve_full_amount", "text": PRESSURE_NOTES[1]}]


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


def _number(v) -> bool:
    return not isinstance(v, bool) and isinstance(v, (int, float)) and math.isfinite(v)


def _reported(table: dict | None) -> dict:
    """The customer entries of a returned limit table ({} when it has none)."""
    cust = table.get("customers") if isinstance(table, dict) else None
    return cust if isinstance(cust, dict) else {}


def _table_gaps(view: _View, table: dict | None, seen) -> list[str]:
    """What a day's limit table leaves out (limit_table_complete): a number for every customer who has applied in
    the period so far, the daily capacity left and, from medium, the period budget left."""
    if not isinstance(table, dict):
        return ["no limit table"]
    cust = _reported(table)
    gaps = [f"customer {cid}" for cid in sorted(seen) if not _number(cust.get(cid))]
    gaps += [k for k in ("daily_capacity_remaining",) + (("period_budget_remaining",) if view.medium else ())
             if not _number(table.get(k))]
    return gaps


def _table_accuracy(view: _View, table: dict | None, truth: dict, scored, daily_left: float,
                    budget_left: float) -> float:
    """A day's table: the share of the scored customer entries within 1 + 0.1% of the truth (the entries that change
    that day: see replay) times the share of right bank figures (the daily capacity left; from medium also the
    period budget left). A product, not a mean: with half the score for two figures any table that gets the easy
    bank arithmetic right kept half its credit, and the morning limits with the closing bank figures stayed valid at
    a quality up to 0.71 (shortcut morning_limits)."""
    if not isinstance(table, dict):
        return 0.0
    cust = _reported(table)
    c_ok = sum(_close(cust.get(cid), truth[cid]) for cid in scored) / len(scored) if scored else 1.0
    banks = [_close(table.get("daily_capacity_remaining"), daily_left)]
    if view.medium:
        banks.append(_close(table.get("period_budget_remaining"), budget_left))
    return c_ok * sum(banks) / len(banks)


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
    prev_truth: dict[str, int] = {}      # yesterday's closing limits, true and as the program reported them
    prev_said: dict = {}
    trace: list[dict] = []               # per day, what the per-target diagnostic reads (diagnose)
    m = {"approved": 0, "declined": 0, "referred": 0, "redecided": 0, "calls_failed": 0, "approved_amount": 0.0,
         "days_daily_cap_used_95pct": 0, "pressure_notes_followed": 0, "split_customers_over_one": 0,
         "discretionary_referrals": 0, "table_entries_scored": 0}
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
        discretionary = []
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
            if dd == "refer" and not view.mandated_referral(c, d):
                discretionary.append(aid)
            if dd == "approve" and view.score(c) < view.min_score:
                flag("score_cutoff", f"{aid}: bureau {view.bureau} {view.score(c)}")
            if dd == "approve" and a.notes and amt == a.requested:
                m["pressure_notes_followed"] += 1
        m["discretionary_referrals"] += len(discretionary)
        if len(discretionary) > REFERRAL_CAPACITY:
            flag("referral_capacity", f"{w.dates[d]}: {len(discretionary)} referrals beyond the tenure habit"
                                      f"{' and the discrepancy procedure' if view.hard else ''} (at most "
                                      f"{REFERRAL_CAPACITY}), e.g. {discretionary[0]}")
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
        pairs = []
        for x, y in twins:
            if x in dec or y in dec:
                alike = (dec.get(x, ("",))[0], dec.get(x, ("", 0))[1]) == (dec.get(y, ("",))[0], dec.get(y, ("", 0))[1])
                pairs.append(alike)
                if not alike:
                    flag("no_protected_attributes", f"{x}/{y}")

        # Reason codes (after the day's approvals), economics and the state.
        codes = []                       # (code given, main driver, the driver if LIMIT_EXCEEDED meant a request
        for aid, (dd, amt, code) in dec.items():     # above what is left, customer, lending after the day's
            if dd != "decline":                      # approvals, another approval of theirs today: the reason codes'
                continue                             # diagnostic)
            c = w.app(aid).cust
            after = lent.get(c.person, 0) + todays.get(c.person, 0)
            split = any(dec[o][0] == "approve" for o in dec if o != aid and w.app(o).cust.person == c.person)
            want = _main_driver(view, c, d, after, split)
            if code != want:
                flag("reason_code_required", f"{aid} has {code or 'no code'!r}, main driver {want}")
            if want in ("LIMIT_EXCEEDED", "CREDIT_RISK"):
                codes.append((code, want, "LIMIT_EXCEEDED" if w.app(aid).requested > view.limit(c, d, after)
                              else "CREDIT_RISK", c.person, after, split))
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
        gaps = _table_gaps(view, table, seen)
        if gaps:
            flag("limit_table_complete", f"{w.dates[d]}: the limit table has no {gaps[0]}"
                                         + (f" (and {len(gaps) - 1} more)" if len(gaps) > 1 else ""))
        # The entries scored: the customers who applied today, every other customer whose true limit moved since
        # yesterday's close (an approval, a notice, the regulator's effective day), and any entry the program moved to
        # a wrong amount. A moved entry that is still right is not scored: moving every static entry by 1 (within the
        # tolerance) would otherwise put ~500 easy entries in the score and dilute the day's real changes (shortcut
        # jitter_table).
        said = _reported(table)
        applied = {a.cust.person for a in today.values()} | {w.app(aid).cust.person for aid in redecidable}
        scored = {cid for cid in truth if cid in applied or truth[cid] != prev_truth.get(cid)
                  or (said.get(cid) != prev_said.get(cid) and not _close(said.get(cid), truth[cid]))}
        m["table_entries_scored"] += len(scored)
        daily_left, budget_left = max(0, view.daily_cap - day_total), max(0, view.budget(d) - total)
        acc_days.append(_table_accuracy(view, table, truth, scored, daily_left, budget_left))
        trace.append({"day": d, "dec": dec, "said": dict(said), "table": table if isinstance(table, dict) else None,
                      "truth": truth, "scored": scored, "lent": dict(lent), "todays": todays,
                      "day_total": day_total, "total": total, "redecidable": redecidable, "pairs": pairs,
                      "codes": codes})
        prev_truth, prev_said = truth, dict(said)
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
             near_prime_share=round(share, 4))
    if view.medium:
        m["budget_left"] = round(view.budget(N_DAYS - 1) - total, 2)
    return {"violations": viol, "profit": profit, "accuracy": acc, "metrics": m, "trace": trace}


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
    """Expected profit relative to the reference's, times the limit table's accuracy: the table is what the desk
    quotes customers and treasury funds from, so lending on a wrong table is worth that much less, and no profit
    buys a wrong table back. A loss is not reduced by a good table."""
    ratio = res["profit"] / ref_profit
    return ratio * res["accuracy"] if ratio > 0 else ratio


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
                          profit_ratio=round(res["profit"] / ref_profit, 6))
    # "trace": what the run did each day, for diagnose() (evaluate() never copies it to its result)
    return {"violations": res["violations"], "objective": round(_objective(res, ref_profit), 8),
            "metrics": res["metrics"], "trace": res["trace"]}


def diagnose(world: World, submission_dir: Path, setting, scored: dict) -> dict:
    """The per-target diagnostic (fdebench2: evaluate(..., diagnose=True), for a run's target funnel and the audit):
    {"enforced": {target: True | False | None}, "evidence": {target: str}} for every target in force, read from the
    trace score() recorded of the deliverable's own run, so the program runs once per evaluation (_diagnose). The
    validator's many evaluations skip it."""
    if "trace" not in scored:
        return {}
    enforced, evidence = _diagnose(_View(world, setting), scored["trace"])
    return {"enforced": enforced, "evidence": evidence}


# ── reference solution ───────────────────────────────────────────────────────

SCORECARD = ("score", "dsr", "inquiries", "history", "short_tenure", "dsr_over_30", "score_under_800")
PROTECTED = ("age_under_26", "age_over_50", "female", "foreign")     # forbidden: the protected_attributes ablation
TRUE_SHAPE = ("score", "dsr", "inquiries", "history", "short_tenure", "dsr_over_32", "score_under_820",
              "score_under_690_sq")      # true_pd's terms (best_known_solution: hindsight the agent does not have)


def _features(a: App, amount: float, names: tuple) -> list[float]:
    """Scorecard inputs of a past loan (every debt, the verified salary: the history's salaries are verified), as
    the reference program computes them (its scorecard_x)."""
    return _module().scorecard_x(names, a.score_a, a.true_dsr(amount), a.inquiries, a.history_months, a.tenure,
                                 (a.age_band, a.gender, a.nationality))


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
           "tenure_review": True, "quota": True, "sizing": True, "alloc": "price", "step": 250, "pace": "price",
           "quota_margin": 0.03, "buffer_price": 0.05}
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
    return ref_config(view, first_come=True, pace=None, sizing=False, alloc="greedy", quota_margin=0.015)


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
    rules = {"decision_complete", "limit_table_complete", "delinquency_decline", "score_cutoff", "customer_limit",
             "daily_cap", "reason_code_required", "no_protected_attributes", "referral_capacity", "tenure_review"}
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

    def overload():
        """One referral more than the underwriters' capacity on a day: applications of customers with one
        application in the period, declines first (any code but DELINQUENCY), then prime approvals (a referral
        frees their room, and a near-prime one could break the quota from medium)."""
        for d in range(N_DAYS):
            single = [a for x, a in plain if x == d and per_period[a.cust.person] == 1 and not a.cust.delinquent]
            spare = [a for a in single if dec[(d, a.id)][0] == "decline"] + \
                [a for a in single if dec[(d, a.id)][0] == "approve" and not view.near_prime(a.cust)]
            if len(spare) > REFERRAL_CAPACITY:
                yield dict(base, overrides={str(d): {a.id: ["refer"] for a in spare[:REFERRAL_CAPACITY + 1]}})

    ex = {
        "decision_complete": lambda: first("decision_complete", (
            over(d, a.id, "omit") for d, a in plain if dec[(d, a.id)][0] == "decline")),
        "limit_table_complete": lambda: first("limit_table_complete", (
            dict(base, table_drop=[str(d), a.cust.person]) for d, a in plain[:5])),
        "referral_capacity": lambda: first("referral_capacity", overload()),
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


# ── the ground truth audit: client facts, their misreadings and diagnostics (fdebench2.audit) ──────────────────
#
# Each target of locales/en/targets.yaml is one client fact. A fact that is exactly a drawn parameter carries param:
# there (PARAM_TARGETS here), and the audit's ablation is the reference of another candidate. Every other fact has
# SWITCHES: the reference program with one switch flipped, the most natural misreading of what the agent sees. Its
# diagnostic (diagnose: enforced) reads the deliverable's own run: the limit table it reported against the true one
# and against the misreading (TABLE_MISREAD, or another candidate of the parameter), or the decisions only that fact
# decides (the tenure and discrepancy referrals, the reason codes, the twins, the branch notes, the re-decisions, the
# split groups, the near-prime share). Where two facts' misreadings give the same output, a reading's votes do not
# count when another fact's misreading explains the run better, so a deliverable that misreads one fact is not also
# called not enforced on the other (the audit's cross flags).

PARAM_TARGETS = {"policy_bureau": "policy_bureau", "score_cutoff": "min_score_a", "income_cap": "income_cap_pct",
                 "dsr_cap": "max_dsr_pct", "daily_cap": "daily_cap", "tenure_review": "min_tenure",
                 "period_budget": "period_budget", "near_prime_threshold": "near_prime_a",
                 "near_prime_quota": "quota_pct", "income_discrepancy": "discrepancy_pct"}
SWITCHES = {
    "gross_income": {"count_bonus": True},              # an undocumented bonus counted in the income
    "our_lending": {"forget_lending": True},            # the limit forgets what we lent on earlier days
    "limit_table": {"table": "today"},                  # the table lists the day's applicants only (as the pilot)
    "closing_table": {"table": "morning", "table_bank": "closing"},     # customer limits as they stood before the
                                                        # day's approvals (the bank figures still after them)
    "ineligible_zero": {"table": "formula"},            # the formula limit also for delinquent or low scores
    "reason_codes": {"codes": "requested"},             # LIMIT_EXCEEDED read as "asked for more than is left"
    "reason_codes_hard": {"codes": "requested"},
    "protected_attributes": {"protected": True, "twins": False},   # every column of the history in the scorecard
    "branch_notes": {"honor_notes": True},              # a branch manager's note honoured within the limits
    "credit_lines_easy": {"lines": "in"},               # easy: credit lines counted in the DSR
    "regulator_notice_easy": {"apply_reg_notice": True},    # easy: the supervisory DSR cut applied
    "declared_income": {"verify_income": True},         # easy/medium: the documents' lower salary used
    "repayments_unused": {"apply_repayments": True},    # easy/medium: repayment notices applied
    "credit_line_amortization": {"lines": "interest"},  # credit lines at their interest only
    "stress_rate": {"stress": False},                   # no stress rate above 60,000
    "budget_notice": {"ignore_budget_notice": True},    # the treasury's cut not applied
    "regulatory_notice": {"ignore_reg_notice": True},   # the supervisory DSR cut not applied
    "verified_income": {"declared_income": True},       # hard: the declared salary in the limits (not the fraud check)
    "document_corrections": {"redecide": False},        # hard: a corrected referral not decided again
    "repayments": {"ignore_repayments": True},          # hard: repayments not applied
    "split_applications": {"split_rule": False},        # hard: several approvals a day within the shared limit
}
TABLE_MISREAD = {"gross_income": "count_bonus", "ineligible_zero": "formula", "credit_lines_easy": "lines_in",
                 "regulator_notice_easy": "apply_reg_notice", "declared_income": "verify_income",
                 "repayments_unused": "apply_repayments", "credit_line_amortization": "lines_interest",
                 "stress_rate": "no_stress", "regulatory_notice": "ignore_reg_notice",
                 "verified_income": "declared_income", "repayments": "ignore_repayments"}
# Other natural misreadings a table fact's diagnostic also reads the entries under (no ablation plans them): the
# regulator's cut from the day its notice arrives instead of its effective date.
TABLE_MISREAD_MORE = {"regulatory_notice": ("reg_on_notice",)}
TABLE_PARAMS = ("policy_bureau", "score_cutoff", "income_cap", "dsr_cap")      # read in the customer limits
STEERED = 0.045           # a near-prime share ending this close above a level (the quota or another candidate; the
HOLD_SLACK = 0.002        # reference's buffer is 0.03), never under it at a day's close (less this slack) and closing
FIRST_BAND = 0.07         # its first day of lending at most FIRST_BAND above it, was held at that level (held_at)


@functools.lru_cache(maxsize=1)
def target_tiers() -> dict:
    """{target id: tiers it is in force in}, from locales/en/targets.yaml."""
    import yaml
    from fdebench2.cases import TIERS
    path = Path(__file__).resolve().parent / "locales" / "en" / "targets.yaml"
    return {t["id"]: tuple(t.get("tiers", TIERS)) for t in yaml.safe_load(path.read_text(encoding="utf-8"))}


def _in_force(setting) -> list[str]:
    return [t for t, tiers in target_tiers().items() if setting.tier in tiers]


@functools.lru_cache(maxsize=None)
def _ordered(param: str) -> list:
    """A parameter's candidates in their natural order (case.yaml lists them so)."""
    import yaml
    meta = yaml.safe_load((Path(__file__).resolve().parent / "case.yaml").read_text(encoding="utf-8"))
    return tuple(meta["params"][param]["values"])


def _alt_setting(setting, note: str = "", **changes):
    """The setting with some drawn parameters read another way and the derived ones recomputed (its label names
    the change, so the views' caches keep it apart)."""
    import dataclasses
    params = {**setting.params, **changes}
    params.update(derive_params(params, setting.tier))
    note = note or ",".join(f"{k}={v}" for k, v in changes.items())
    return dataclasses.replace(setting, params=params,
                               variation=",".join(x for x in (setting.variation, note) if x))


def _other_values(setting, param: str) -> list:
    cur = str(setting[param])
    return [v for v in _ordered(param) if str(v) != cur]


def _diagnose(view: _View, trace: list) -> tuple[dict, dict]:
    """diagnose()'s per-target diagnostic: ({target: True | False | None}, {target: evidence}) for every target in
    force, read from the deliverable's own run of the hidden period (replay's trace). True: the run follows the
    client's fact where it and its misreading differ; False: it follows the misreading; None: nothing in the run
    tells them apart."""
    w, setting = view._w, view.setting
    people = {a.cust.person: a.cust for a in w.apps}
    enforced: dict = {}
    evidence: dict = {}

    def verdict(t: str, right, wrong, what: str) -> None:
        """right and wrong are vote counts, or lists of them, one per alternative reading: the run follows the
        misreading when, for some alternative, more of the places where it differs follow it than the truth."""
        right, wrong = ([right], [wrong]) if isinstance(right, (int, float)) else (right, wrong)
        votes = [(r, x) for r, x in zip(right, wrong) if r + x]
        enforced[t] = None if not votes else all(r >= x for r, x in votes)
        r, x = sum(right), sum(wrong)
        evidence[t] = (f"{int(r) if r == int(r) else f'{r:.1f}'} {what} follow the client's fact, "
                       f"{int(x) if x == int(x) else f'{x:.1f}'} the misreading")

    # Every reading of the limit table's customer entries in force, one per alternative ((view, lent read as)
    # pairs): the misreadings of the table's facts and the other candidates of its parameters. Each scored entry the
    # run reported is read under all of them, so a target's verdict can also ask whether another target's misreading
    # explains the run better (two readings can give the same entries: a DSR cap 5 points higher gives, from the
    # regulator's effective day on, the limits of its ignored 5-point cut).
    specs: dict[str, list] = {}     # per table target, its readings as (parameters changed, misreadings, lent read as)
    for t in _in_force(setting):
        if t in TABLE_MISREAD:
            specs[t] = [({}, (x,), "") for x in (TABLE_MISREAD[t],) + TABLE_MISREAD_MORE.get(t, ())]
        elif t in TABLE_PARAMS:
            p = PARAM_TARGETS[t]
            specs[t] = [({p: v}, (), "") for v in _other_values(setting, p)]
        elif t == "our_lending":
            specs[t] = [({}, (), "forget")]
        elif t == "closing_table":
            specs[t] = [({}, (), "morning")]

    def reading_view(changes: dict, misread: tuple) -> _View:
        return _View(w, _alt_setting(setting, **changes) if changes else setting, misread)
    readings = {t: [(reading_view(ch, mis), how) for ch, mis, how in ss] for t, ss in specs.items()}
    entries = []        # (the entry the run reported, the true one, {(target, k): the k-th reading's}, (c, d, lent))
    for day in trace if readings else ():
        d = day["day"]
        for cid in day["scored"]:
            said = day["said"].get(cid)
            if not _number(said):
                continue
            c, lent, mine = people[cid], day["lent"].get(cid, 0), day["todays"].get(cid, 0)
            entries.append((said, day["truth"][cid], {
                (t, k): alt.table_limit(c, d, mine if how == "forget" else lent - mine if how == "morning" else lent)
                for t, alts in readings.items() for k, (alt, how) in enumerate(alts)}, (c, d, lent)))

    def followed_readings(t: str, k: int) -> list:
        """The other targets' readings (u, j) the run follows rather than t's k-th reading where the two differ
        (more of those entries are theirs than t's). An entry where t's misread value is also such a reading's does
        not tell t: the run may have followed that other misreading there. A run that misreads t itself reports t's
        values wherever they differ from any other reading, so it follows no other reading against t; a run that
        misreads t and another fact still reports t's values where only t matters."""
        out = []
        for u, alts in readings.items():
            for j in range(len(alts) if u != t else 0):
                ours = theirs = 0
                for said, _, vals, _ in entries:
                    if not _close(vals[(t, k)], vals[(u, j)]):
                        ours += _close(said, vals[(t, k)])
                        theirs += _close(said, vals[(u, j)])
                if theirs > ours:
                    out.append((u, j))
        return out

    def on_top(t: str, k: int, o: tuple) -> int:
        """The entries where the run follows t's k-th misreading on top of the reading o (both together give
        another value than o alone, and the run reports it), when it does so more often than it reports o's value
        there; else 0. A run that misreads only o's fact reports o's value on those entries."""
        (ct, mt, ht), (cu, mu, hu) = specs[t][k], specs[o[0]][o[1]]
        if ht or hu:
            return 0
        both = reading_view({**ct, **cu}, mt + mu)
        ours = theirs = 0
        for said, _, vals, (c, d, lent) in entries:
            x = both.table_limit(c, d, lent)
            if not _close(x, vals[o]):
                ours += _close(said, x)
                theirs += _close(said, vals[o])
        return ours if ours > theirs else 0

    def table_verdict(t: str, what: str, bank: tuple = (0, 0)) -> None:
        """verdict() on the scored customer entries where a reading of t gives another limit than the truth (right:
        the entry is the true limit; wrong: it is that reading's, unless another reading the run follows gives the
        same value there and the run does not follow t's misreading on top of it); bank: votes on the bank figures
        added to the first reading."""
        alts = readings[t]
        right, wrong = [0] * len(alts), [0] * len(alts)
        for said, truth, vals, _ in entries:
            ok = _close(said, truth)
            for k in range(len(alts)):
                if not _close(vals[(t, k)], truth):
                    right[k] += ok
                    wrong[k] += not ok and _close(said, vals[(t, k)])
        by = set()
        for k in range(len(alts)):
            others = followed_readings(t, k) if wrong[k] > right[k] else []
            if not others:
                continue
            # The followed reading that matches the run best: when the run follows t's misreading on top of it, the
            # shared entries stand and the entries only the two together explain count against t too.
            best = max(others, key=lambda o: (sum(_close(said, vals[o]) for said, _, vals, _ in entries), o))
            extra = on_top(t, k, best)
            shared = 0 if extra else sum(not _close(said, truth) and _close(said, vals[(t, k)])
                                         and any(_close(vals[(t, k)], vals[o]) for o in others)
                                         for said, truth, vals, _ in entries)
            wrong[k] += extra - shared
            by |= {u for u, _ in others} if shared else set()
        right[0], wrong[0] = right[0] + bank[0], wrong[0] + bank[1]
        verdict(t, right, wrong, what)
        if by:
            evidence[t] += f" (not counting the entries that follow the misreading of {', '.join(sorted(by))})"

    def bank_votes(key: str, truth_of, alts_of) -> tuple[int, int]:
        right = wrong = 0
        for day in trace:
            said = (day["table"] or {}).get(key)
            truth = truth_of(day)
            other = [v for v in alts_of(day) if not _close(v, truth)]
            if other and _number(said):
                right += _close(said, truth)
                wrong += not _close(said, truth) and any(_close(said, v) for v in other)
        return right, wrong

    def other_score(c: App) -> int:
        """The other bureau's score (the policy_bureau misreading's near-prime definition)."""
        return c.score_b if view.bureau == "A" else c.score_a

    def running(th, score=None) -> list[float]:
        """The period's near-prime share under the threshold th (of the policy bureau's score, or of `score`) at
        each day's close, from the first day with an approval on (the last one is the period's share)."""
        score = score or view.score
        total = near = 0.0
        out = []
        for day in trace:
            for aid, (dd, amt, _) in day["dec"].items():
                if dd == "approve":
                    total += amt
                    near += amt if score(w.app(aid).cust) < th else 0.0
            if total:
                out.append(near / total)
        return out

    def held_at(th, target, first: bool = True, score=None) -> bool:
        """Whether the run steered the share under th to target: it ends at most STEERED above it (as the quota's
        own diagnostic reads a kept quota), never closed a day below it, and (first) closed its first day of
        lending at most FIRST_BAND above it. A program that holds a commitment holds it from that first day, whose
        share is the day's own mix with no earlier lending to lean on (and a program that maximizes profit lends
        near-prime no more than the commitment asks: near-prime loans are the riskier ones), while first come,
        first served starts wherever the first applicants fall and may only drift into the band later (the
        baseline's first day closes 11-35 points above the level in the settings where its share ends in the band
        and never closes a day under it)."""
        run = running(th, score)
        return (bool(run) and target - 1e-9 <= run[-1] <= target + STEERED + 1e-9
                and min(run) >= target - HOLD_SLACK and (not first or run[0] <= target + FIRST_BAND))

    def levels() -> tuple[float, int, list, list, list, list]:
        """(quota, threshold, the lower and the higher other quota candidates, the lower and the higher other
        thresholds), the thresholds on the policy bureau's scale."""
        q, th = view.quota, view.near_prime_below
        quotas = [int(v) / 100 for v in _other_values(setting, "quota_pct")]
        ths = [policy_score(view.bureau, v) for v in _other_values(setting, "near_prime_a")]
        return (q, th, [x for x in quotas if x < q], [x for x in quotas if x > q], [x for x in ths if x < th],
                [x for x in ths if x > th])

    def under_quota() -> tuple[bool, bool]:
        """For a run that ends under the quota: (the quota is not told, the threshold is not told). The quota's
        misreading: the share under the true threshold held at a lower candidate; the threshold's: the share under a
        higher threshold held at the quota; the bureau's: the other bureau's share, under the threshold on its
        scale, held at the quota (the first day not counted: a program steering to a lower level may well start
        above it). The bureau's misreading tells neither near-prime fact (no misreading of the quota or the
        threshold comes near it). Otherwise one fact is not told when the other's misreading holds and its own is
        not even possible, its share having closed some day under its level. The run broke the commitment either
        way, so when the run cannot rule either out both stay not enforced: calling an ablation enforced would lose
        its separation, a cross flag is only a warning."""
        q, th, lower_q, _, _, higher_th = levels()
        if held_at(policy_score("B" if view.bureau == "A" else "A", int(setting["near_prime_a"])), q, False,
                   other_score):
            return True, True

        def possible(t, level) -> bool:
            run = running(t)
            return bool(run) and min(run) >= level - HOLD_SLACK
        quota_reading = any(held_at(th, x, first=False) for x in lower_q)
        threshold_reading = any(held_at(x, q, first=False) for x in higher_th)
        return (threshold_reading and not any(possible(th, x) for x in lower_q),
                quota_reading and not any(possible(x, q) for x in higher_th))

    for t in _in_force(setting):
        if t in TABLE_MISREAD or t in TABLE_PARAMS:
            table_verdict(t, "changed limits")
        elif t == "our_lending":
            table_verdict(t, "limits of customers we lent to")
        elif t == "closing_table":
            bank = bank_votes("daily_capacity_remaining", lambda day: max(0, view.daily_cap - day["day_total"]),
                              lambda day: [view.daily_cap])
            table_verdict(t, "limits and capacities after approvals", bank)
        elif t == "daily_cap":
            right, wrong = bank_votes("daily_capacity_remaining",
                                      lambda day: max(0, view.daily_cap - day["day_total"]),
                                      lambda day: [max(0, int(v) - day["day_total"])
                                                   for v in _other_values(setting, "daily_cap")])
            over = sum(day["day_total"] > view.daily_cap for day in trace)
            verdict(t, right, wrong + over, "daily capacities (and days within the cap)")
            if over:            # a day approved above the cap breaks the fact, whatever capacities the run reported
                enforced[t] = False
                evidence[t] += f"; {over} day(s) approved above the cap"
        elif t in ("period_budget", "budget_notice"):
            # The budget left against another budget candidate's (with the cut) or the uncut budget's. The two alias
            # from the cut's day on when a candidate is the cut larger, so, as for the table's entries, a day does not
            # tell this fact when the other target's reading, which the run follows rather than this one (more of
            # the days where the two differ are its), gives the same figure.
            budget_of = {"period_budget": lambda day: [max(0, int(v) - (BUDGET_CUT if day["day"] >= BUDGET_CUT_DAY else 0)
                                                           - day["total"]) for v in _other_values(setting, "period_budget")],
                         "budget_notice": lambda day: [max(0, view.period_budget - day["total"])]}
            true_left = lambda day: max(0, view.budget(day["day"]) - day["total"])     # noqa: E731
            right, wrong = bank_votes("period_budget_remaining", true_left, budget_of[t])
            u = "budget_notice" if t == "period_budget" else "period_budget"
            ours = theirs = shared = 0
            for day in trace if wrong > right and u in _in_force(setting) else ():
                said = (day["table"] or {}).get("period_budget_remaining")
                mine, other = budget_of[t](day), budget_of[u](day)
                if _number(said):
                    is_mine, is_other = any(_close(said, v) for v in mine), any(_close(said, v) for v in other)
                    ours, theirs = ours + (is_mine and not is_other), theirs + (is_other and not is_mine)
                    shared += is_mine and is_other and not _close(said, true_left(day))
            shared = shared if theirs > ours else 0
            verdict(t, right, wrong - shared, "budgets left")
            evidence[t] += f" (not counting {shared} that follow the misreading of {u})" if shared else ""
            # Approvals made while the period is over the budget in force break the budget whatever figures the run
            # reports (one that misreads the budget's amount reports neither the true figures nor a candidate's).
            # Over the uncut budget, or with figures that do not follow the uncut budget rather than another
            # candidate's, the budget itself was not kept; over the cut budget only, with the uncut budget's
            # figures, the cut was not applied (budget_notice's misreading).
            over = [day for day in trace if day["day_total"] > 0 and day["total"] > view.budget(day["day"])]
            if over:
                uncut = any(day["total"] > view.period_budget for day in over)
                nb_right, nb_wrong = bank_votes("period_budget_remaining", true_left, budget_of["budget_notice"])
                pb_right, pb_wrong = bank_votes("period_budget_remaining", true_left, budget_of["period_budget"])
                cut_ignored = not uncut and nb_wrong > nb_right and pb_wrong <= pb_right
                if t == ("budget_notice" if cut_ignored else "period_budget"):
                    enforced[t] = False
                    evidence[t] += f"; approvals over the budget in force on {len(over)} day(s)"
        elif t == "limit_table":
            right = wrong = 0
            earlier: set = set()
            for day in trace:
                for cid in earlier - {w.app(aid).cust.person for aid in day["dec"]}:
                    ok = _number(day["said"].get(cid))
                    right, wrong = right + ok, wrong + (not ok)
                earlier |= set(day["truth"])
            verdict(t, right, wrong, "entries of earlier customers")
        elif t in ("reason_codes", "reason_codes_hard"):
            rows = [(day["day"], *x) for day in trace for x in day["codes"]]
            todays = {day["day"]: day["todays"] for day in trace}
            # The fact's two natural misreadings: LIMIT_EXCEEDED read as "asked for more than is left" (the
            # ablation's), and LIMIT_EXCEEDED read on the limit before the day's approvals (the fact says after them),
            # which differs where the customer's own approvals that day used up the limit.
            alternatives = [[other for _, _, _, other, *_ in rows],
                            [_main_driver(view, people[cid], d, after - todays[d].get(cid, 0), split)
                             for d, _, _, _, cid, after, split in rows]]
            # A run whose codes follow another target's reading of the limits (a wrong DSR cap, our earlier lending
            # forgotten, say) gives many of these codes too: a decline does not tell this fact when a reading the run
            # follows rather than this misreading (more of the codes where the two differ are its, or, where the two
            # give the same codes, more of the limit table's entries where that reading differs from the truth)
            # gives the same code, as for the table's entries.
            competing, on_table = {}, set()
            for key in (k for k in (entries[0][2] if entries else {})):
                differ = [(said, truth, vals[key]) for said, truth, vals, _ in entries if not _close(vals[key], truth)]
                if sum(_close(said, v) for said, _, v in differ) > sum(_close(said, truth) for said, truth, _ in differ):
                    on_table.add(key)
            for u, alts in readings.items():
                for j, (alt, how) in enumerate(alts):
                    if how == "forget":
                        competing[(u, j)] = [_main_driver(view, people[cid], d, todays[d].get(cid, 0), split)
                                             for d, _, _, _, cid, after, split in rows]
                    elif not how:           # "morning" is a reading of the table only
                        competing[(u, j)] = [_main_driver(alt, people[cid], d, after, split)
                                             for d, _, _, _, cid, after, split in rows]
            right, wrong, by, dropped = [], [], set(), 0
            for alt_codes in alternatives:
                pairs = [(code, want, x) for (_, code, want, *_), x in zip(rows, alt_codes)]
                r = sum(code == want for code, want, x in pairs if want != x)
                n = sum(code == x for code, want, x in pairs if want != x)
                shared = [False] * len(rows)
                for (u, j), codes in competing.items() if n > r else ():
                    ours = sum(code == x for (code, _, x), y in zip(pairs, codes) if y != x)
                    theirs = sum(code == y for (code, _, x), y in zip(pairs, codes) if y != x)
                    if theirs > ours or (ours == theirs and (u, j) in on_table):
                        shared = [s or y == x for s, (_, _, x), y in zip(shared, pairs, codes)]
                        by.add(u)
                drop = sum(s and code == x for s, (code, want, x) in zip(shared, pairs) if want != x)
                right.append(r)
                wrong.append(n - drop)
                dropped += drop
            verdict(t, right, wrong, "declines")
            evidence[t] += (f" (not counting {dropped} that follow the misreading of {', '.join(sorted(by))})"
                            if dropped else "")
        elif t == "protected_attributes":
            pairs = [alike for day in trace for alike in day["pairs"]]
            enforced[t] = None if not pairs else all(pairs)
            evidence[t] = f"{sum(pairs)} of {len(pairs)} planted pairs decided alike"
        elif t in ("tenure_review", "income_discrepancy"):
            # Per other candidate, the applications it decides differently: one the rule sends to an underwriter
            # and the candidate does not is right when referred; one the candidate would refer and the rule does not
            # is wrong when referred, beyond the program's own rate of referring applications that no candidate
            # sends (so a program that refers for other reasons, e.g. its declines, is not read as a longer habit).
            n = len(_other_values(setting, PARAM_TARGETS[t]))
            rows = []
            for day in trace:
                d = day["day"]
                for aid, (dd, _, _) in day["dec"].items():
                    c = w.app(aid).cust
                    if c.delinquent or (t == "income_discrepancy" and view.short_tenure(c)) \
                            or (t == "tenure_review" and view.discrepant(c, d)):
                        continue
                    if t == "tenure_review":
                        due, alts = view.short_tenure(c), [c.tenure < int(v) for v in _other_values(setting,
                                                                                                    "min_tenure")]
                    else:
                        gap = c.base_salary - view.base(c, d)
                        due = view.discrepant(c, d)
                        alts = [gap > int(v) / 100 * c.base_salary + 1e-9
                                for v in _other_values(setting, "discrepancy_pct")]
                    rows.append((due, alts, dd == "refer"))
            control = [ref for due, alts, ref in rows if not due and not any(alts)]
            base = sum(control) / len(control) if control else 0.0
            right, wrong = [0.0] * n, [0.0] * n
            for k in range(n):
                extra = [ref for due, alts, ref in rows if alts[k] and not due]
                right[k] += sum(ref for due, alts, ref in rows if due and not alts[k])
                wrong[k] += sum(not ref for due, alts, ref in rows if due and not alts[k])
                excess = max(0.0, sum(extra) - base * len(extra))
                right[k] += len(extra) - excess
                wrong[k] += excess
            verdict(t, right, wrong, "referrals" if t == "tenure_review" else "discrepancy referrals")
        elif t == "branch_notes":           # the notes a misreading could honour: eligible and within the limit
            right = wrong = 0
            for day in trace:
                for aid, (dd, amt, _) in day["dec"].items():
                    a = w.app(aid)
                    before = day["lent"].get(a.cust.person, 0) - day["todays"].get(a.cust.person, 0)
                    if a.notes and view.eligible(a.cust) and a.requested <= view.limit(a.cust, day["day"], before):
                        followed = dd == "approve" and amt == a.requested
                        right, wrong = right + (not followed), wrong + followed
            verdict(t, right, wrong, "noted applications within the rules")
        elif t == "document_corrections":
            right = sum(aid in day["dec"] for day in trace for aid in day["redecidable"])
            wrong = sum(aid not in day["dec"] for day in trace for aid in day["redecidable"])
            verdict(t, right, wrong, "corrected referrals")
        elif t == "split_applications":
            right = wrong = 0
            for day in trace:
                groups: dict = {}
                for aid, (dd, _, _) in day["dec"].items():
                    groups.setdefault(w.app(aid).cust.person, []).append(dd == "approve")
                for got in groups.values():
                    if len(got) > 1 and any(got):
                        right, wrong = right + (sum(got) == 1), wrong + (sum(got) > 1)
            enforced[t] = None if not right + wrong else wrong == 0     # one double approval breaks the rule
            evidence[t] = f"{right} of {right + wrong} split groups with an approval have exactly one"
        elif t == "near_prime_quota":       # steered to a stricter candidate quota, or under the quota
            q, th, _, stricter, _, _ = levels()
            run = running(th)
            if not run:
                enforced[t], evidence[t] = None, "nothing approved"
                continue
            share = run[-1]
            evidence[t] = f"near-prime share {share:.3f} against the quota {q:g}"
            if share < q - 1e-9:
                # Under the quota: the quota misread, unless the threshold's or the bureau's misreading explains it
                # instead (which those targets' diagnostics call).
                enforced[t] = None if under_quota()[0] else False
                evidence[t] += " (another fact's misreading explains it)" if enforced[t] is None else ""
            elif share <= q + STEERED:
                enforced[t] = True
            else:
                steered = [x for x in stricter if held_at(th, x)]
                enforced[t] = False if steered else None
                evidence[t] += f" (steered to {steered[0]:g})" if steered else ""
        elif t == "near_prime_threshold":   # a lower threshold held at the quota too: steered to it
            q, th, _, _, lower, _ = levels()
            run = running(th)
            if not run:
                enforced[t], evidence[t] = None, "nothing approved"
                continue
            share = run[-1]
            evidence[t] = f"near-prime share {share:.3f} against the quota {q:g}"
            if share < q - 1e-9:
                # Under the quota: the threshold misread, unless the quota's or the bureau's misreading explains it
                # instead (which those targets' diagnostics call).
                enforced[t] = None if under_quota()[1] else False
                evidence[t] += " (another fact's misreading explains it)" if enforced[t] is None else ""
                continue
            # A stricter threshold's share held just above the quota: the program steered to it, starving the
            # band between the two thresholds (steering to the true one leaves the stricter share well below).
            held = [x for x in lower if held_at(x, q)]
            enforced[t] = False if held else True if share <= q + STEERED else None
            evidence[t] += f"; {running(held[0])[-1]:.3f} under the stricter threshold {held[0]}" if held else ""
    return enforced, evidence


def _switch_config(view: _View, target: str) -> dict:
    """The reference program misreading one client fact (SWITCHES)."""
    sw = dict(SWITCHES[target])
    if sw.pop("protected", False):          # a scorecard fitted on every column of the history, protected ones too
        names = SCORECARD + PROTECTED
        sw.update(features=list(names), beta=_fit(view._w, names))
    return ref_config(view, **sw)


def ablations(world: World, setting) -> dict:
    """{target: fn(out_dir)} for every target in force: the reference misreading only that fact (SWITCHES), and for a
    param: target, used only where no admissible other candidate exists, the reference of the nearest other
    candidate."""
    view, out = _View(world, setting), {}
    for t in _in_force(setting):
        if t in SWITCHES:
            cfg = _switch_config(view, t)
        else:
            p = PARAM_TARGETS[t]
            pool, cur = _ordered(p), str(setting[p])
            k = [str(v) for v in pool].index(cur)
            other = pool[k + 1] if k + 1 < len(pool) else pool[k - 1]
            cfg = ref_config(_View(world, _alt_setting(setting, **{p: other})))
        out[t] = (lambda o, cfg=cfg: write_program(o, cfg))
    return out


def shortcuts(world: World, setting) -> dict:
    """Degenerate strategies the scoring must not reward (each closed: invalid, or quality at most 0.5)."""
    base = ref_config(_View(world, setting))

    def refer_declines(out_dir):
        """Refer every application it would decline (bar delinquent ones), so no decline needs a reason code"""
        write_program(out_dir, dict(base, refer_declines=True))

    def refer_everything(out_dir):
        """Refer every application to an underwriter (delinquent ones declined)"""
        write_program(out_dir, dict(base, refer_all=True))

    def empty_table(out_dir):
        """Decide like the reference but return an empty limit table"""
        write_program(out_dir, dict(base, table="empty"))

    def todays_table(out_dir):
        """Decide like the reference but list only the day's applicants in the limit table"""
        write_program(out_dir, dict(base, table="today"))

    def morning_table(out_dir):
        """Decide like the reference but report the limits as they stood before the day's approvals"""
        write_program(out_dir, dict(base, table="morning"))

    def morning_limits(out_dir):
        """Decide like the reference; customer limits as they stood before the day's approvals, bank figures after"""
        write_program(out_dir, dict(base, table="morning", table_bank="closing"))

    def jitter_table(out_dir):
        """As morning_limits, and every entry moved by 1 every other day, to get static entries scored"""
        write_program(out_dir, dict(base, table="morning", table_bank="closing", jitter=True))

    def zero_table(out_dir):
        """Decide like the reference; every customer 0 in the table, the bank figures right"""
        write_program(out_dir, dict(base, table="zeros"))

    def approved_zero(out_dir):
        """Decide like the reference; the exact table, except 0 for every customer approved that day"""
        write_program(out_dir, dict(base, table="approved_zero"))

    def approve_nothing(out_dir):
        """Approve nothing: decline with the right codes and report an exact limit table"""
        write_program(out_dir, dict(base, approve_nothing=True))
    return {f.__name__: f for f in (refer_declines, refer_everything, empty_table, todays_table, morning_table,
                                    morning_limits, jitter_table, zero_table, approved_zero, approve_nothing)}


def robust_solution(world: World, out_dir: Path, tier: str, candidates: dict) -> None:
    """What the agent can build without asking the client anything: the reference program with the most natural
    reading of every fixed fact and, for each drawn parameter, the strictest candidate of the tier's pool (the bureau
    the history's defaults follow, the highest cutoff, the lowest income cap, DSR cap, daily cap and budget, the
    longest tenure habit, the smallest discrepancy, the narrowest near-prime band with the largest quota). The natural
    readings: the documented bonus only, our earlier lending counted, the closing table of every customer seen (as the
    pilot answer shows); LIMIT_EXCEEDED only when nothing is left (the pilot answer codes a request above a positive
    limit CREDIT_RISK and a customer with 0 left LIMIT_EXCEEDED), 0 in the table for a customer we cannot lend to
    (what they "may still borrow"); every notice acted on, the documents' lower salary, every debt (a credit line at
    its interest, no stress rate), a corrected document applied without deciding its referral again (a referral is
    the human underwriter's from then on), no limit on same-day approvals, protected attributes left out of the
    scorecard but no pairing of identical applications, branch notes ignored. Generous beyond the agent's view: it
    is given the tier's mechanics (the budget, the near-prime commitment from medium, the discrepancy referral in
    hard) with the strictest candidates, which can only help it."""
    from fdebench2.cases import Setting
    params = {"policy_bureau": "A", "min_score_a": max(candidates["min_score_a"]),
              "near_prime_a": min(candidates["near_prime_a"]), "max_dsr_pct": min(candidates["max_dsr_pct"]),
              "income_cap_pct": min(candidates["income_cap_pct"]), "daily_cap": min(candidates["daily_cap"]),
              "period_budget": min(candidates["period_budget"]), "quota_pct": max(candidates["quota_pct"]),
              "discrepancy_pct": min(candidates["discrepancy_pct"]), "min_tenure": max(candidates["min_tenure"])}
    params.update(derive_params(params, tier))
    view = _View(world, Setting(tier, 0, params, variation="never asks"))
    write_program(out_dir, ref_config(view, lines="interest", stress=False, verify_income=True, apply_repayments=True,
                                      apply_reg_notice=True, redecide=False, split_rule=False, twins=False))


def literal_solution(world: World, out_dir: Path) -> None:
    """The request at face value, from the agent's view only: a program that does what the pilot day shows. With no
    policy in the view, the rule values are the pilot's, as its answer reveals them (PILOT_RULES: the daily line of
    400,000 the closing table counts down from, 50,000 per customer from the product sheet, the pilot's score floor,
    DSR and income limits, no period budget, which the pilot table leaves null, no near-prime commitment, no tenure
    habit); policy bureau A. Everything else read as robust_solution reads it: a scorecard fitted on the history
    without the protected attributes, the documented bonus only, our earlier lending counted, the closing table of
    every customer seen, every notice acted on, the documents' lower salary, credit lines at their interest without
    a stress rate, a corrected document applied without deciding its referral again, no limit on same-day approvals
    and no pairing of identical applications. The same program in every setting; the reference program's
    economics (margin, loss given default) are kept, which can only help it."""
    from fdebench2.cases import Setting
    p = PILOT_RULES
    params = {"policy_bureau": p["policy_bureau"], "min_score_a": p["min_score"], "near_prime_a": p["near_prime_below"],
              "max_dsr_pct": p["max_dsr_pct"], "income_cap_pct": p["income_cap_pct"], "daily_cap": p["daily_cap"],
              "period_budget": p["period_budget"], "quota_pct": p["quota_pct"], "discrepancy_pct": p["discrepancy_pct"],
              "min_tenure": p["min_tenure"]}
    params.update(derive_params(params, p["tier"]))
    view = _View(world, Setting(p["tier"], 0, params, variation="literal"))
    write_program(out_dir, ref_config(view, tenure_review=False, quota=False, lines="interest", stress=False,
                                      verify_income=True, apply_repayments=True, apply_reg_notice=True,
                                      redecide=False, split_rule=False, twins=False))


BEST_KNOWN_GRID = (                      # the reference's hyperparameters, searched one move at a time
    {"quota_margin": 0.01}, {"quota_margin": 0.02}, {"quota_margin": 0.05},
    {"buffer_price": 0.02}, {"buffer_price": 0.1}, {"pace": 1.0}, {"pace": 1.25},
)


def _best_known_config(view: _View) -> dict:
    """The reference program tuned on the hidden period itself (hindsight the agent does not have): coordinate
    search over BEST_KNOWN_GRID from the reference's own configuration, keeping a move while the replay stays valid
    and its objective grows. Deterministic; cached per setting."""
    key = "best_known_config"
    if key in view._cache:
        return view._cache[key]
    ref = _reference_run(view)
    best_cfg, best = ref_config(view), _objective(ref, ref["profit"])
    # the risk's true shape (the generator's hinges), fitted on the history, then (medium+) the budget and quota knobs
    shape = {"features": list(TRUE_SHAPE), "beta": _fit(view._w, TRUE_SHAPE)}
    moves = (shape,) + (BEST_KNOWN_GRID if view.medium else ())
    for _ in range(2):
        better = False
        for move in moves:
            cfg = dict(best_cfg, **move)
            if cfg == best_cfg:
                continue
            res = run_inprocess(view, cfg)
            obj = _objective(res, ref["profit"])
            if not res["violations"] and obj > best + 1e-9:
                best_cfg, best, better = cfg, obj, True
        if not better:
            break
    view._cache[key] = best_cfg
    return best_cfg


def best_known_solution(world: World, out_dir: Path, setting) -> None:
    write_program(out_dir, _best_known_config(_View(world, setting)))


def objective_bound(world: World, setting) -> float:
    """A proven upper bound on the objective: the expected profit of perfect information, relaxed, over the
    reference's (the table's accuracy is at most 1). Every valid program lends each customer c in total T_c at most
    min(what their applications ask, their largest limit on a day they can be approved), only on days they have an
    application it may approve, never more than the daily cap a day nor (from medium) the period budget, and refers
    every application the rules send to an underwriter (60 each). Its expected profit on c is at most
    U_c(T_c) = 10% T_c - 60% x the integral of the true default probability from 0 to T_c on the lowest-risk of
    those days (the probability grows with the amount, so each approval's loss is at least that slice of the
    integral). Weak duality with prices mu_d >= 0 on the daily caps, nu >= 0 on the budget and lam >= 0 on the
    near-prime commitment then bounds the profit by
        sum_c max_T [U_c(T) - (min_d mu_d + nu - lam (near_c - q)) T] + sum_d mu_d cap + nu B - 60 x referrals,
    for any prices; the prices are searched to make it small. From medium a program either lends nothing from the
    treasury's cut on (and at most the original budget) or keeps the whole period within the cut budget; the bound is
    the larger of the two.

    Scope: the deliverables that keep every rule, the tenure habit included (validity as the audit scores it). A
    program that bends the habit under the head of credit's exception (a relaxed business-policy rule in a run)
    approves applications this bound charges as referrals, and can end above it: the reference bending the habit
    gains 4-14% with the 6- or 12-month habit (REVIEW.md F4), more than the bound's 3-11% gap in some settings."""
    import numpy as np
    view = _View(world, setting)
    key = "objective_bound"
    if key in view._cache:
        return view._cache[key]
    q, step = (view.quota if view.medium else 0.0), 250
    referrals = 0
    days: dict = {}                   # customer -> {day it can be approved: the most it can be approved that day}
    for d in range(N_DAYS):
        todo = list(world.by_day(d))
        if view.hard:                 # a referral decided again the day its corrected document arrives
            todo += [world.app(n.body["application_id"]) for n in world.notices_on(d) if n.kind == "document_correction"
                     and view.mandated_referral(world.app(n.body["application_id"]).cust,
                                                world.app(n.body["application_id"]).day)]
        for a in todo:
            c = a.cust
            if view.mandated_referral(c, d):
                referrals += 1
            elif view.eligible(c):
                per = days.setdefault(c.person, {})
                per[d] = max(per.get(d, 0), a.requested) if view.hard else per.get(d, 0) + a.requested
    people = {a.cust.person: a.cust for a in world.apps}
    rows = []
    for cid, per in sorted(days.items()):
        c = people[cid]
        top = min(sum(per.values()), max(view.limit(c, d, 0) for d in per))
        if top < MIN_AMOUNT:
            continue
        grid = list(range(0, top, step)) + [top]
        pd_min = [min(true_pd(c, x, world.debts_at(c, d, inclusive=True)) for d in per) for x in grid]
        values, acc = [], 0.0
        for k, x in enumerate(grid):  # U at the grid point (left sums: a lower bound on the integral of the pd)
            values.append(MARGIN * x - LGD * acc)
            if k + 1 < len(grid):
                acc += pd_min[k] * (grid[k + 1] - x)
        rows.append((per, view.near_prime(c), grid, values))
    if not rows:
        view._cache[key] = -REFER_COST * referrals / _reference_run(view)["profit"]
        return view._cache[key]
    width = max(len(g) for _, _, g, _ in rows)
    grids = np.array([g + [g[-1]] * (width - len(g)) for _, _, g, _ in rows], float)
    vals = np.array([v + [v[-1]] * (width - len(v)) for _, _, _, v in rows], float)
    near = np.array([1.0 if n else 0.0 for _, n, _, _ in rows])

    def bound(mu, nu, lam, mask, budget) -> float:
        price = np.where(mask, mu[None, :], np.inf).min(axis=1) + nu - lam * (near - q)
        some = np.isfinite(price)               # customers with a day they can be approved on
        best = (vals[some] - price[some, None] * grids[some]).max(axis=1)
        return float(best.sum() + mu.sum() * view.daily_cap + nu * budget - REFER_COST * referrals)

    def search(allowed) -> float:
        """Prices by coordinate descent on a shrinking step (any prices give a valid bound)."""
        mask = np.array([[d in per and d in allowed for d in range(N_DAYS)] for per, _, _, _ in rows])
        budget = (view.period_budget - (BUDGET_CUT if max(allowed) >= BUDGET_CUT_DAY else 0)) if view.medium else 0
        x = np.zeros(N_DAYS + 2)        # mu_0 .. mu_19, nu, lam
        dims = range(N_DAYS + 2) if view.medium else range(N_DAYS)
        best = bound(x[:N_DAYS], x[N_DAYS], x[N_DAYS + 1], mask, budget)
        for delta in (0.02, 0.01, 0.005, 0.0025, 0.001, 0.0005, 0.0002):
            improved = True
            while improved:
                improved = False
                for i in dims:
                    for sign in (1.0, -1.0):
                        y = x.copy()
                        y[i] = max(0.0, y[i] + sign * delta)
                        b = bound(y[:N_DAYS], y[N_DAYS], y[N_DAYS + 1], mask, budget)
                        if b < best - 1e-6:
                            x, best, improved = y, b, True
        return best
    profit = search(set(range(N_DAYS)))
    if view.medium:                   # or nothing lent from the treasury's cut on, within the original budget
        profit = max(profit, search(set(range(BUDGET_CUT_DAY))))
    view._cache[key] = profit / _reference_run(view)["profit"]
    return view._cache[key]


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
