"""Answering managers' business questions from a subscription shop's export (original FDE-Bench v2 case).

A Seoul-based coffee & tea subscription shop exports its order database as CSV
tables and asks for answers to twelve managers' questions. The request only
says "answer them"; the definitions that decide every number (fiscal year and
how it is named, local day, test accounts, which orders count, net revenue,
refund booking, FX, "active", a renamed category, rounding of money figures)
are in the requirements, and so is what a wrong figure costs against a figure
left as "not available yet".

Every answer is a number or null ("don't know"). A scored question earns
right_reward (2) when correct, dont_know_reward when null and wrong_reward (0)
when wrong; the objective is the total over 2 x the number of scored questions.
So the case measures calibrated abstention: a sheet that knows the setting's
scheme answers a question only when its chance of being right is above
dont_know_reward / right_reward. One kind of question has no figure at all: a
period that is still running on the reference date. Finance's habit is to show
"not available yet" for it, so the right answer is null (rule running_period,
the bendable one: with the CFO's approval a figure to date is judged instead).

The data is the same in every setting. A setting (tier, rule seed) decides which
questions are scored and the client's conventions:

  tiers (which questions the board pack needs this round; others have no effect)
    easy    Q01, Q03, Q04, Q05, Q07, Q10, Q12: counted orders, test and staff
            accounts, the fiscal year and its naming, running periods,
            Korea-time days, net revenue and FX, the active window, rounding
    medium  + Q02, Q08, Q09, Q11: refund booking and the October refunds of
            September orders
    hard    all twelve: + Q06, which needs the snacks -> pantry rename
  parameters a rule seed draws, each on its own (case.yaml `params`, one pool for every tier)
    fy_start          first month of the fiscal year: September, April or July (never January: the
                      calendar year is what a sheet that never asks assumes)
    active_days       active-customer window: 30, 60 or 90 days
    rounding_unit     money is reported to the nearest 100, 1,000 or 10,000 KRW
    dont_know_reward  what a null earns: 0.5, 1 or 1.5 (wrong 0, right 2)
  derived (derive_params)
    fy2025, fy2026_q1, fy2026_h1, active_from
                      the periods these give, worded per locale as the requirements state them
    right_reward, wrong_reward
                      the fixed ends of the reward scheme (2 and 0)

A July year leaves the first half of FY2026 running on the reference date (Q07 is null), a September year
its first quarter too (Q02 and Q07); under an April year every period is over.

Ground truth audit hooks (fdebench2.audit): ablations (one misreading per fact), shortcuts, robust_solution
(the sheet that never asks), best_known_solution and objective_bound (the reference reaches the bound) and
diagnose (which reading of each fact the sheet's figures follow).

Table and column identifiers stay ASCII (they are SQL identifiers); categorical
labels, product names, the questions file and the data dictionary are localized.
"""

from __future__ import annotations

import itertools
import json
import math
import random
import tempfile
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

from fdebench2.cases import Setting
from fdebench2.casekit import Fatal, read_json, write_csv

# ── world ────────────────────────────────────────────────────────────────────

KST = timedelta(hours=9)
DAY = timedelta(days=1)
DATA_START = date(2025, 1, 1)
AS_OF = date(2026, 9, 30)
SALE_DAY = date(2026, 7, 1)
RENAME_DAY = date(2025, 10, 1)          # "snacks" renamed "pantry"; older products keep the old label
LOAD_TEST_START = date(2025, 4, 1)      # the QA load test on the first test account
AUG_2026 = (date(2026, 8, 1), date(2026, 8, 31))
SEP_2026 = (date(2026, 9, 1), date(2026, 9, 30))
TAX = {"KR": 0.10, "JP": 0.10, "US": 0.07}
CURRENCY = {"KR": "KRW", "JP": "JPY", "US": "USD"}
DECIMALS = {"KRW": 0, "JPY": 0, "USD": 2}
QIDS = [f"Q{i:02d}" for i in range(1, 13)]
MONEY_Q = ("Q01", "Q02", "Q06", "Q07", "Q09")
EXACT_Q = ("Q03", "Q04", "Q05", "Q10")       # counts and ids: exact match
PERCENT_Q = ("Q08", "Q11")
REL_TOL = 0.005
PP_TOL = 0.05                    # Q11 (a change in percent): percentage points, so one decimal place counts
SCORED = {                       # the questions the board pack needs this round, per tier
    "easy": ("Q01", "Q03", "Q04", "Q05", "Q07", "Q10", "Q12"),
    "medium": ("Q01", "Q02", "Q03", "Q04", "Q05", "Q07", "Q08", "Q09", "Q10", "Q11", "Q12"),
    "hard": tuple(QIDS),
}
PERIOD_OF = {                    # the fiscal period a question is about (Q03, Q05 and Q11 have dated ones)
    "Q01": "fy2025", "Q02": "q1", "Q04": "fy2025", "Q06": "fy2025", "Q07": "h1", "Q08": "fy2025",
    "Q09": "fy2025", "Q10": "fy2025", "Q12": "fy2025",
}
RIGHT_REWARD, WRONG_REWARD = 2, 0      # the fixed ends of the scheme; the rule seed draws dont_know_reward
ALL_TIERS = ("easy", "medium", "hard")
# The clarification targets and the tiers where each is in force (en/targets.yaml says the same; gt_report.py
# checks it). running_period is in force only where a scored period is still running (a July or September year).
TARGET_TIERS = {
    "fiscal_year": ALL_TIERS, "fy_naming": ALL_TIERS, "running_period": ALL_TIERS, "local_day": ALL_TIERS,
    "test_accounts": ALL_TIERS, "counted_orders": ALL_TIERS, "revenue_ex_tax": ALL_TIERS,
    "refund_period": ("medium", "hard"), "late_refunds": ("medium", "hard"), "fx_order_date": ALL_TIERS,
    "active_customer": ALL_TIERS, "category_rename": ("hard",), "report_rounding": ALL_TIERS,
}


def _first(year: int, month: int) -> date:
    """The first day of `month` of `year`; months past 12 run into the next years."""
    return date(year + (month - 1) // 12, (month - 1) % 12 + 1, 1)


def periods(fy_start: int, named: str = "start") -> dict[str, tuple[date, date]]:
    """FY2025 and the first quarter and first half of FY2026, whole, for a fiscal year that starts in month
    fy_start. The client names a fiscal year after the calendar year it starts in (named="start"); "end" is the
    other convention, the year it ends in (the same thing for a calendar year)."""
    year = 2025 if named == "start" or fy_start == 1 else 2024
    fy26 = _first(year + 1, fy_start)
    return {"fy2025": (_first(year, fy_start), fy26 - DAY),
            "q1": (fy26, _first(year + 1, fy_start + 3) - DAY),
            "h1": (fy26, _first(year + 1, fy_start + 6) - DAY)}


def running_questions(fy_start: int, named: str = "start") -> tuple:
    """The questions whose period is still running on the reference date (or has not started): no figure yet."""
    per = periods(fy_start, named)
    return tuple(q for q in QIDS if q in PERIOD_OF and per[PERIOD_OF[q]][1] > AS_OF)


@dataclass(frozen=True)
class Rules:
    """One setting's conventions and reward scheme."""

    fy_start: int
    active_days: int
    unit: int                    # money is reported to the nearest unit (KRW)
    right: float
    dont_know: float
    wrong: float
    scored: tuple
    running: tuple               # the scored questions whose period is still running: null is the right answer

    @property
    def bound(self) -> float:
        """The most a valid sheet can earn: 2 for every scored question with a figure, the null's reward for
        one whose period is still running (a number there breaks running_period)."""
        n, k = len(self.scored), len(self.running)
        return (self.right * (n - k) + self.dont_know * k) / (self.right * n)


def rules_of(setting: Setting) -> Rules:
    p = setting.params
    scored = SCORED[setting.tier]
    running = running_questions(int(p["fy_start"]))
    return Rules(int(p["fy_start"]), int(p["active_days"]), int(p["rounding_unit"]), float(p["right_reward"]),
                 float(p["dont_know_reward"]), float(p["wrong_reward"]), scored,
                 tuple(q for q in scored if q in running))


# ── rule seeds: what the drawn parameters give ───────────────────────────────

SPAN = {"zh": "{} 至 {}", "en": "{} to {}", "ko": "{} ~ {}", "ja": "{}〜{}", "es": "del {} al {}"}


def _span(a: date, b: date) -> dict:
    """A date range as each locale's requirements write it."""
    return {lang: fmt.format(a.isoformat(), b.isoformat()) for lang, fmt in SPAN.items()}


def derive_params(params: dict, tier: str) -> dict:
    """The periods the texts state, whole, from the drawn fiscal-year start, the first day of the active window,
    and the fixed ends of the reward scheme."""
    per = periods(int(params["fy_start"]))
    return {"fy2025": _span(*per["fy2025"]), "fy2026_q1": _span(*per["q1"]), "fy2026_h1": _span(*per["h1"]),
            "active_from": (AS_OF - timedelta(days=int(params["active_days"]) - 1)).isoformat(),
            "right_reward": RIGHT_REWARD, "wrong_reward": WRONG_REWARD}


def admissible(params: dict, tier: str) -> bool:
    """Rewards rise from wrong to don't know to right, FY2025 is over and FY2026 has started by the reference
    date, and the active window starts after the data does. Every combination of the current pools passes; this
    guards new ones."""
    rewards_rise = float(params["wrong_reward"]) < float(params["dont_know_reward"]) < float(params["right_reward"])
    per = periods(int(params["fy_start"]))
    fy_in_data = DATA_START <= per["fy2025"][0] and per["fy2025"][1] <= AS_OF and per["q1"][0] <= AS_OF
    window_in_data = 1 <= int(params["active_days"]) <= (AS_OF - DATA_START).days + 1
    return rewards_rise and fy_in_data and window_in_data


# product id -> (category key, KRW list price, launch date)
PRODUCTS = {
    "P01": ("box", 29000, None), "P02": ("box", 45000, None), "P03": ("box", 32000, None),
    "P04": ("coffee", 18000, None), "P05": ("coffee", 16000, None), "P06": ("coffee", 42000, None),
    "P07": ("coffee", 17000, None), "P08": ("coffee", 12000, None),
    "P09": ("tea", 15000, None), "P10": ("tea", 13000, None), "P11": ("tea", 12000, None),
    "P12": ("tea", 14000, None),
    "P13": ("snacks", 8500, None), "P14": ("snacks", 6500, None), "P15": ("snacks", 11000, None),
    "P16": ("snacks", 9000, None),
    "P17": ("pantry", 14000, date(2025, 10, 15)), "P18": ("pantry", 9500, date(2025, 11, 1)),
    "P19": ("pantry", 12500, date(2026, 1, 10)), "P20": ("pantry", 9800, date(2025, 10, 1)),
    "P21": ("accessories", 25000, None), "P22": ("accessories", 4500, None),
    "P23": ("accessories", 68000, None), "P24": ("accessories", 22000, None),
}
FOOD = ("snacks", "pantry")


def _price(krw: int, cur: str) -> float:
    if cur == "KRW":
        return float(krw)
    if cur == "USD":
        return round(krw / 1350.0, 2)
    return float(round(krw / 9.2 / 10) * 10)


def _money(x: float, cur: str) -> float:
    return round(x, DECIMALS[cur])


@dataclass
class Customer:
    id: int
    signup_utc: datetime
    country: str
    plan: str              # box | shop
    kind: str              # regular | staff | test


@dataclass
class Order:
    id: str
    customer: int
    ts_utc: datetime
    status: str            # completed | cancelled | payment_failed
    currency: str
    lines: list            # [(product_id, qty, unit_price)]
    subtotal: float
    tax: float
    total: float
    method: str
    paid: bool = False
    refunds: list = field(default_factory=list)   # [(refund_id, ts_utc, amount tax-incl, reason)]


@dataclass
class World:
    customers: list
    orders: list
    fx: dict               # (currency, local date) -> KRW per unit
    cust: dict = field(default_factory=dict)

    def __post_init__(self):
        self.cust = {c.id: c for c in self.customers}


HOURS = [3, 2, 1, 1, 1, 1, 2, 4, 5, 6, 6, 6, 7, 6, 5, 5, 5, 5, 6, 7, 8, 9, 8, 5]
SALE_HOURS = [30, 16, 8, 5, 4, 5, 7, 9, 10, 9, 7, 6, 5, 4, 4, 4, 4, 4, 5, 6, 6, 6, 5, 4]


def _local_ts(rng: random.Random, d: date, weights=HOURS) -> datetime:
    h = rng.choices(range(24), weights)[0]
    local = datetime(d.year, d.month, d.day, h, rng.randrange(60), rng.randrange(60))
    return local - KST


def build_world(seed: int) -> World:
    rng = random.Random(seed)
    # FX: KRW per unit, one rate per local calendar day. The won weakens steadily over the period (the dollar from
    # about 1,330 to 1,500 KRW, the yen from 8.80 to 9.90) with day-to-day swings around that trend, so on every
    # world the rate of an order's date is not the latest rate. (A walk without a trend ended near its own
    # average on some worlds, where the FX convention then decided no answer.) Two draws a day, as before.
    fx = {}
    usd = jpy = 0.0                 # the swing around the trend
    d = date(2024, 12, 1)
    while d <= AS_OF:
        t = (d - date(2024, 12, 1)).days
        usd = 0.9 * usd + rng.gauss(0, 5.0)
        jpy = 0.9 * jpy + rng.gauss(0, 0.035)
        fx[("USD", d)], fx[("JPY", d)], fx[("KRW", d)] = (round(1330.0 + 0.25 * t + usd, 2),
                                                          round(8.80 + 0.00165 * t + jpy, 4), 1.0)
        d += timedelta(days=1)

    n_real, n_test = 1400, 7
    kinds = ["regular"] * (n_real + n_test)
    idx = list(range(n_real + n_test))
    rng.shuffle(idx)
    for i in idx[:n_test]:
        kinds[i] = "test"
    for i in idx[n_test:n_test + 15]:
        kinds[i] = "staff"
    span = (date(2026, 9, 28) - date(2024, 7, 1)).days
    customers = []
    for i, kind in enumerate(kinds):
        sd = date(2024, 7, 1) + timedelta(days=int(span * rng.random() ** 0.85))
        country = "KR" if kind == "test" else rng.choices(["KR", "JP", "US"], [70, 18, 12])[0]
        plan = "shop" if kind == "test" else ("box" if rng.random() < 0.55 else "shop")
        customers.append(Customer(10001 + i, _local_ts(rng, sd), country, plan, kind))

    orders: list[Order] = []

    def avail(d: date):
        return [p for p, (cat, _, launch) in PRODUCTS.items() if cat != "box" and (launch is None or launch <= d)]

    def make_order(c: Customer, ts: datetime, lines_spec=None, force_status=None):
        cur = CURRENCY[c.country]
        d = (ts + KST).date()
        if lines_spec is None:
            pool = avail(d)
            lines_spec = []
            if c.plan == "box":
                lines_spec.append((rng.choices(["P01", "P02", "P03"], [5, 3, 2])[0], 1))
                extra = rng.choices([0, 1, 2], [60, 28, 12])[0]
            else:
                extra = rng.choices([1, 2, 3, 4], [40, 32, 18, 10])[0]
            # food items are popular add-ons
            for p in rng.sample(pool, extra):
                if rng.random() < 0.35:
                    p = rng.choice([q for q in pool if PRODUCTS[q][0] in FOOD])
                if p not in [x[0] for x in lines_spec]:
                    lines_spec.append((p, rng.choices([1, 2, 3], [65, 25, 10])[0]))
        lines = [(p, q, _price(PRODUCTS[p][1], cur)) for p, q in lines_spec]
        sub = _money(sum(q * u for _, q, u in lines), cur)
        tax = _money(sub * TAX[c.country], cur)
        status = force_status or rng.choices(["completed", "cancelled", "payment_failed"], [92, 5, 3])[0]
        o = Order("", c.id, ts, status, cur, lines, sub, tax, _money(sub + tax, cur),
                  rng.choices(["card", "bank", "wallet"], [65, 15, 20])[0])
        o.paid = status == "completed" or (status == "cancelled" and rng.random() < 0.7)
        if status == "completed" and rng.random() < 0.07:
            rts = ts + timedelta(days=rng.randint(2, 25), minutes=rng.randrange(1440))
            reason = rng.choice(["damaged", "wrong_item", "changed_mind", "late"])
            if rng.random() < 0.35 or len(lines) == 1 and rng.random() < 0.5:
                o.refunds.append([rts, o.total, reason])
            else:
                picks = rng.sample(range(len(lines)), min(len(lines), 2 if rng.random() < 0.12 else 1))
                for k, li in enumerate(picks):
                    p, q, u = lines[li]
                    amt = _money(q * u * (1 + TAX[c.country]), cur)
                    o.refunds.append([rts + timedelta(days=3 * k), amt, reason])
        orders.append(o)
        return o

    for c in customers:
        if c.kind == "test":
            continue
        d = max((c.signup_utc + KST).date(), DATA_START) + timedelta(days=rng.randint(0, 10))
        while d <= AS_OF:
            make_order(c, _local_ts(rng, d))
            if c.plan == "box":
                d += timedelta(days=30 + rng.randint(-4, 4))
                if rng.random() < 0.035:
                    break
            else:
                d += timedelta(days=3 + int(rng.expovariate(1 / 45)))
                if rng.random() < 0.08:
                    break
    # Mid-year sale (opens at local midnight on 2026-07-01).
    eligible = [c for c in customers if c.kind != "test" and (c.signup_utc + KST).date() < SALE_DAY]
    for c in rng.sample(eligible, 170):
        make_order(c, _local_ts(rng, SALE_DAY, SALE_HOURS))

    # Test accounts: QA load test (2025-04 to 2026-03) on the first one, scattered test orders on all (and sale night).
    tests = [c for c in customers if c.kind == "test"]
    for k in range(36):
        d = LOAD_TEST_START + timedelta(days=int(k * 10 + rng.randint(0, 6)))
        make_order(tests[0], _local_ts(rng, d), [("P23", 10), ("P06", 5)], "completed")
    for c in tests:
        for _ in range(rng.randint(6, 12)):
            d = DATA_START + timedelta(days=rng.randrange((AS_OF - DATA_START).days + 1))
            make_order(c, _local_ts(rng, d), None, "completed")
        make_order(c, _local_ts(rng, AS_OF - timedelta(days=rng.randint(0, 60))), None, "completed")
    for c in tests[:5]:
        local = datetime(2026, 7, 1, 0, rng.randint(1, 20), rng.randrange(60))
        make_order(c, local - KST, None, "completed")

    orders.sort(key=lambda o: (o.ts_utc, o.customer))
    rid = 0
    for i, o in enumerate(orders):
        o.id = f"O{i + 1:06d}"
    for o in sorted((o for o in orders if o.refunds), key=lambda o: o.refunds[0][0]):
        for r in o.refunds:
            rid += 1
            r.insert(0, f"R{rid:05d}")
    return World(customers, orders, fx)


# ── analysis (truth, reference and the other readings of the export) ─────────

# The client's reading of the export: one switch per fixed fact. compute() takes the others as keyword changes.
READING = {
    "fy_named": "start",         # start | end: the calendar year a fiscal year is named after
    "local_day": True,           # days in Korea time (UTC+9); False: the stored UTC dates; a number of hours
                                 # (never 0 or 1, which are False and True): days in that offset from UTC
    "accounts": "policy",        # policy: test accounts out, staff in | all: nobody out | internal_out: both out
    "orders": "completed",       # completed | paid: any order with a payment row | all: every order row
                                 # | not_failed: completed and cancelled orders | kept: completed orders that were
                                 # not refunded in full
    "tax": "ex",                 # ex: subtotal less the tax-free part of refunds | incl: total less refund amounts
                                 # | refund_incl: subtotal less the refund amounts as stored (tax included)
    "refund_period": "order",    # a refund is booked in the period of its order | refund: of the refund itself
    "late_refunds": True,        # refunds made after the reference date count; False: cut off at the reference date
    "fx": "order_date",          # the rate of the order's date | latest: the reference date's rate for everything
    "both_labels": True,         # pantry = the pantry and the old snacks label; False: the pantry label only;
                                 # "since_rename": the old label counts only for orders from the rename day on
}
# The misreadings a sheet is checked for, per fixed fact (diagnose); the first one is the fact's ablation, the
# most natural wrong reading of the export. The drawn facts (fiscal year, active window, rounding unit) are read
# as another value, and running_period as "counted up to the reference date".
MISREADINGS = {
    "fy_naming": {"fiscal years named after the year they end in": {"fy_named": "end"}},
    "local_day": {"the stored UTC dates": {"local_day": False}},
    "test_accounts": {"staff accounts left out with the test accounts": {"accounts": "internal_out"},
                      "test accounts kept in": {"accounts": "all"}},
    "counted_orders": {"every order with a payment row": {"orders": "paid"},
                       "every order row": {"orders": "all"}},
    "revenue_ex_tax": {"tax included (order total less refund amounts)": {"tax": "incl"}},
    "refund_period": {"refunds booked in the period of the refund": {"refund_period": "refund"}},
    "late_refunds": {"refunds cut off at the reference date": {"late_refunds": False}},
    "fx_order_date": {"the reference date's rate for every order": {"fx": "latest"}},
    "category_rename": {"the pantry label only": {"both_labels": False}},
}
# Further readings of a fact that a sheet may follow (diagnose). A sheet whose figures are a variant's does not
# enforce the fact; a sheet that merely avoids a variant shows nothing (staying clear of US time says little about
# Korea time), so only MISREADINGS count for a fact. Without them a sheet that followed one was called enforced
# on its own fact from the questions the variant leaves right, or not enforced on another fact whose misreading
# lies within the scorer's tolerance.
VARIANTS = {
    "local_day": {"days in UTC+8": {"local_day": 8},
                  "days in US Eastern time (UTC-5)": {"local_day": -5},
                  "days in US Pacific time (UTC-8)": {"local_day": -8}},
    "counted_orders": {"completed and cancelled orders (only failed payments left out)": {"orders": "not_failed"},
                       "completed orders refunded in full left out": {"orders": "kept"}},
    "revenue_ex_tax": {"refund amounts subtracted with their tax": {"tax": "refund_incl"}},
    "category_rename": {"the old label counted only from the rename day on": {"both_labels": "since_rename"}},
}
WINDOWS = (7, 14, 28, 30, 31, 45, 60, 61, 90, 91, 92, 120, 180, 365)    # active windows a sheet is checked for
NAN = float("nan")


def _ledger(world: World, local_day, accounts, orders, tax, refund_period, late_refunds, fx, both_labels):
    """The export's rows under one reading: per counted order (customer, day, revenue before refunds in KRW,
    units, the pantry part of that revenue); per refund of one (customer, order index, the day it is booked on,
    amount in KRW, its pantry part: an order's refunds are spread over its lines pro rata); and the sign-up day
    of every counted customer."""
    shift = KST if local_day is True else timedelta(hours=local_day or 0)

    def day(ts: datetime) -> date:
        return (ts + shift).date()

    skip = {"policy": ("test",), "all": (), "internal_out": ("test", "staff")}[accounts]
    counted = {"completed": lambda o: o.status == "completed", "paid": lambda o: o.paid, "all": lambda o: True,
               "not_failed": lambda o: o.status != "payment_failed",
               "kept": lambda o: o.status == "completed" and not (
                   o.refunds and abs(sum(r[2] for r in o.refunds) - o.total) < 0.005)}[orders]
    latest = {cur: world.fx[(cur, AS_OF)] for cur in DECIMALS}
    sales, refunds = [], []
    for o in world.orders:
        if not counted(o) or world.cust[o.customer].kind in skip:
            continue
        d = day(o.ts_utc)
        rate = latest[o.currency] if fx == "latest" else world.fx[(o.currency, d)]
        if tax == "incl":
            rate = rate * o.total / o.subtotal
        food = FOOD if both_labels is True or (both_labels == "since_rename" and d >= RENAME_DAY) else ("pantry",)
        share = sum(q * u for p, q, u in o.lines if PRODUCTS[p][0] in food) / o.subtotal
        gross = o.subtotal * rate
        sales.append((o.customer, d, gross, sum(q for _, q, _ in o.lines), gross * share))
        for _, ts, amount, _ in o.refunds:
            made = day(ts)
            if late_refunds or made <= AS_OF:
                back = (amount if tax == "refund_incl" else amount * o.subtotal / o.total) * rate
                refunds.append((o.customer, len(sales) - 1, d if refund_period == "order" else made, back,
                                back * share))
    signups = [day(c.signup_utc) for c in world.customers if c.kind not in skip]
    return sales, refunds, signups


def compute(world: World, fy_start: int = 4, active_days: int = 90, **reading) -> dict:
    """The twelve exact answers under one reading of the export: the client's own (READING) with the given fiscal
    year and active window, unless `reading` changes a switch. A period still running on the reference date is
    counted up to it (the figure to date; running_questions() says which questions that is)."""
    unknown = sorted(set(reading) - set(READING))
    if unknown:
        raise TypeError(f"compute(): unknown reading {unknown}")
    r = {**READING, **reading}
    memo = world.__dict__.setdefault("_answers", {})
    key = (fy_start, active_days) + tuple(r[k] for k in READING)
    if key not in memo:
        memo[key] = _compute(world, fy_start, active_days, **r)
    return dict(memo[key])


def _compute(world: World, fy_start: int, active_days: int, fy_named: str, **rows) -> dict:
    ledgers = world.__dict__.setdefault("_ledgers", {})
    key = tuple(rows[k] for k in READING if k != "fy_named")
    if key not in ledgers:
        ledgers[key] = _ledger(world, **rows)
    sales, refunds, signups = ledgers[key]

    def within(d, rng_):
        return rng_[0] <= d <= rng_[1]

    def net(rng_):
        return (sum(g for _, d, g, _, _ in sales if within(d, rng_))
                - sum(x for _, _, d, x, _ in refunds if within(d, rng_)))

    per = {k: (a, min(b, AS_OF)) for k, (a, b) in periods(fy_start, fy_named).items()}
    fy_, q1, h1 = per["fy2025"], per["q1"], per["h1"]
    window = (AS_OF - timedelta(days=active_days - 1), AS_OF)
    fy = [x for x in sales if within(x[1], fy_)]
    back = [x for x in refunds if within(x[2], fy_)]
    by_cust: dict[int, float] = {}
    for c, _, g, _, _ in fy:
        by_cust[c] = by_cust.get(c, 0.0) + g
    for c, _, _, x, _ in back:
        by_cust[c] = by_cust.get(c, 0.0) - x
    gross, refunded = sum(x[2] for x in fy), sum(x[3] for x in back)
    n_half, n_refunded = sum(1 for x in sales if within(x[1], h1)), len({x[1] for x in back})
    aug = net(AUG_2026)
    return {
        "Q01": gross - refunded,
        "Q02": net(q1),
        "Q03": len({x[0] for x in sales if within(x[1], window)}),
        "Q04": max(by_cust, key=lambda c: (by_cust[c], -c)) if by_cust else NAN,
        "Q05": sum(1 for x in sales if x[1] == SALE_DAY),
        "Q06": sum(x[4] for x in fy) - sum(x[4] for x in back),
        "Q07": net(h1) / n_half if n_half else NAN,
        "Q08": 100.0 * refunded / gross if gross else NAN,
        "Q09": refunded / n_refunded if n_refunded else NAN,
        "Q10": sum(1 for d in signups if within(d, fy_)),
        "Q11": 100.0 * (net(SEP_2026) / aug - 1.0) if aug else NAN,
        "Q12": sum(x[3] for x in fy) / len(fy) if fy else NAN,
    }


def truth(world: World, rules: Rules, **reading) -> dict:
    return compute(world, rules.fy_start, rules.active_days, **reading)


def _round_money(ans: dict, unit: int) -> dict:
    return {q: (round(v / unit) * unit if q in MONEY_Q and v is not None else v) for q, v in ans.items()}


def _sheet(world: World, rules: Rules, to_date: bool = False, every_question: bool = False, **reading) -> dict:
    """The answer sheet of a careful analyst who knows the setting: the exact figures under the client's reading
    (or with `reading` changed: one fact misread), money rounded to the setting's unit, null for a question the
    round does not need (unless every_question) and for one whose period is still running (unless to_date: the
    figure to date)."""
    ans = _round_money(truth(world, rules, **reading), rules.unit)
    running = set() if to_date else set(running_questions(rules.fy_start))
    return {q: (ans[q] if (every_question or q in rules.scored) and q not in running else None) for q in QIDS}


def _face_value(world: World) -> dict:
    """The export summed at face value, with none of the client's definitions: calendar-year periods on the
    stored UTC dates, every order row whatever its status, revenue = order `total` (tax included) less the
    refunds dated in the period, every currency at the reference date's rate, active = ordered in the last 30
    days, and "pantry" = the products labelled pantry. Test accounts are left out (the dictionary flags them)."""
    return compute(world, fy_start=1, active_days=30, local_day=False, orders="all", tax="incl",
                   refund_period="refund", fx="latest", both_labels=False)


# ── data rendering ───────────────────────────────────────────────────────────

L = {
    "completed": {"zh": "已完成", "en": "completed", "ko": "완료", "ja": "完了", "es": "completado"},
    "cancelled": {"zh": "已取消", "en": "cancelled", "ko": "취소", "ja": "キャンセル", "es": "cancelado"},
    "payment_failed": {"zh": "支付失败", "en": "payment_failed", "ko": "결제실패", "ja": "決済失敗", "es": "pago_fallido"},
    "regular": {"zh": "普通", "en": "regular", "ko": "일반", "ja": "一般", "es": "normal"},
    "staff": {"zh": "员工", "en": "staff", "ko": "직원", "ja": "社員", "es": "empleado"},
    "test": {"zh": "测试", "en": "test", "ko": "테스트", "ja": "テスト", "es": "prueba"},
    "box_plan": {"zh": "订阅", "en": "subscription", "ko": "구독", "ja": "定期便", "es": "suscripción"},
    "shop_plan": {"zh": "单次购买", "en": "one_off", "ko": "단품구매", "ja": "都度購入", "es": "compra_suelta"},
    "box": {"zh": "订阅盒", "en": "box", "ko": "구독박스", "ja": "定期便ボックス", "es": "caja"},
    "coffee": {"zh": "咖啡", "en": "coffee", "ko": "커피", "ja": "コーヒー", "es": "café"},
    "tea": {"zh": "茶", "en": "tea", "ko": "차", "ja": "お茶", "es": "té"},
    "snacks": {"zh": "零食", "en": "snacks", "ko": "스낵", "ja": "スナック", "es": "snacks"},
    "pantry": {"zh": "食品储藏", "en": "pantry", "ko": "팬트리", "ja": "パントリー", "es": "despensa"},
    "accessories": {"zh": "器具", "en": "accessories", "ko": "용품", "ja": "器具", "es": "accesorios"},
    "card": {"zh": "银行卡", "en": "card", "ko": "카드", "ja": "カード", "es": "tarjeta"},
    "bank": {"zh": "银行转账", "en": "bank_transfer", "ko": "계좌이체", "ja": "銀行振込", "es": "transferencia"},
    "wallet": {"zh": "电子钱包", "en": "wallet", "ko": "간편결제", "ja": "電子マネー", "es": "monedero"},
    "damaged": {"zh": "商品破损", "en": "damaged", "ko": "파손", "ja": "破損", "es": "dañado"},
    "wrong_item": {"zh": "发错商品", "en": "wrong_item", "ko": "오배송", "ja": "誤配送", "es": "artículo_erróneo"},
    "changed_mind": {"zh": "不想要了", "en": "changed_mind", "ko": "단순변심", "ja": "お客様都合", "es": "cambio_de_opinión"},
    "late": {"zh": "配送延迟", "en": "late_delivery", "ko": "배송지연", "ja": "配送遅延", "es": "retraso"},
}
NAMES = {
    "P01": ("经典咖啡订阅盒", "Classic Coffee Box", "클래식 커피 박스", "クラシックコーヒーボックス", "Caja Café Clásico"),
    "P02": ("精品咖啡订阅盒", "Premium Coffee Box", "프리미엄 커피 박스", "プレミアムコーヒーボックス", "Caja Café Premium"),
    "P03": ("茶饮探索订阅盒", "Tea Discovery Box", "티 디스커버리 박스", "ティーディスカバリーボックス", "Caja Descubre Tés"),
    "P04": ("埃塞俄比亚耶加雪菲 250g", "Ethiopia Yirgacheffe 250g", "에티오피아 예가체프 250g", "エチオピア イルガチェフェ 250g", "Etiopía Yirgacheffe 250g"),
    "P05": ("哥伦比亚慧兰 250g", "Colombia Huila 250g", "콜롬비아 우일라 250g", "コロンビア ウィラ 250g", "Colombia Huila 250g"),
    "P06": ("招牌拼配 1kg", "House Blend 1kg", "하우스 블렌드 1kg", "ハウスブレンド 1kg", "Mezcla de la Casa 1kg"),
    "P07": ("低因拼配 250g", "Decaf Blend 250g", "디카페인 블렌드 250g", "デカフェブレンド 250g", "Mezcla Descafeinada 250g"),
    "P08": ("挂耳咖啡 10袋", "Drip Bags 10-pack", "드립백 10개입", "ドリップバッグ 10袋", "Bolsitas de goteo x10"),
    "P09": ("济州绿茶", "Jeju Green Tea", "제주 녹차", "済州緑茶", "Té verde de Jeju"),
    "P10": ("伯爵红茶", "Earl Grey", "얼그레이", "アールグレイ", "Earl Grey"),
    "P11": ("南非国宝茶", "Rooibos", "루이보스", "ルイボス", "Rooibos"),
    "P12": ("焙茶", "Hojicha", "호지차", "ほうじ茶", "Hojicha"),
    "P13": ("杏仁意式脆饼", "Almond Biscotti", "아몬드 비스코티", "アーモンドビスコッティ", "Biscotti de almendra"),
    "P14": ("黑巧克力", "Dark Chocolate Bar", "다크 초콜릿", "ダークチョコレート", "Tableta de chocolate negro"),
    "P15": ("格兰诺拉麦片", "Granola", "그래놀라", "グラノーラ", "Granola"),
    "P16": ("黄油曲奇", "Butter Cookies", "버터 쿠키", "バタークッキー", "Galletas de mantequilla"),
    "P17": ("野花蜂蜜 250g", "Wildflower Honey 250g", "야생화 꿀 250g", "百花蜂蜜 250g", "Miel de flores 250g"),
    "P18": ("燕麦奶浓缩液", "Oat Milk Concentrate", "오트밀크 원액", "オーツミルク濃縮", "Concentrado de avena"),
    "P19": ("可可粉", "Cocoa Powder", "코코아 파우더", "ココアパウダー", "Cacao en polvo"),
    "P20": ("抹茶酥饼", "Matcha Shortbread", "말차 쇼트브레드", "抹茶ショートブレッド", "Galletas de matcha"),
    "P21": ("手冲滤杯", "Pour-over Dripper", "핸드드립 드리퍼", "ハンドドリッパー", "Gotero para filtrado"),
    "P22": ("滤纸 100张", "Paper Filters 100", "종이 필터 100매", "ペーパーフィルター 100枚", "Filtros de papel x100"),
    "P23": ("手摇磨豆机", "Hand Grinder", "핸드 그라인더", "手挽きミル", "Molinillo manual"),
    "P24": ("保温随行杯", "Travel Tumbler", "텀블러", "タンブラー", "Vaso térmico"),
}
LANG_IX = {"zh": 0, "en": 1, "ko": 2, "ja": 3, "es": 4}
DOC_FILES = {
    "questions": {"zh": "问题清单.md", "en": "questions.md", "ko": "질문목록.md", "ja": "質問一覧.md", "es": "preguntas.md"},
    "dictionary": {"zh": "数据字典.md", "en": "data_dictionary.md", "ko": "데이터사전.md", "ja": "データ辞書.md",
                   "es": "diccionario_de_datos.md"},
}

QUESTIONS = {
    "en": """# Questions from the management team

Reference date: 2026-09-30. Please give money figures in KRW. Answer every question with a single number.

- Q01: What was our total net revenue in FY2025?
- Q02: What was our net revenue in the first quarter of FY2026?
- Q03: How many active customers do we have as of the reference date?
- Q04: Which customer brought in the most net revenue in FY2025? (answer with the customer_id)
- Q05: How many orders did we get on our mid-year sale day, 2026-07-01?
- Q06: How much net revenue did the "pantry" category bring in during FY2025?
- Q07: What was our average order value in the first half of FY2026?
- Q08: What was our refund rate in FY2025, i.e. refunds as a percentage of revenue before refunds? (in percent)
- Q09: In FY2025, what was the average refund per refunded order?
- Q10: How many new customers signed up in FY2025?
- Q11: By how many percent did net revenue in September 2026 change compared with August 2026? (negative if it fell)
- Q12: On average, how many units were in one order in FY2025?
""",
    "zh": """# 管理层提出的问题

基准日期：2026-09-30。金额请以韩元（KRW）为单位。每个问题请用一个数字回答。

- Q01：FY2025 的净收入总额是多少？
- Q02：FY2026 第一季度的净收入是多少？
- Q03：截至基准日期，我们有多少活跃客户？
- Q04：FY2025 贡献净收入最多的客户是哪一位？（请回答 customer_id）
- Q05：年中大促当天（2026-07-01）我们一共接了多少笔订单？
- Q06：FY2025 期间，“食品储藏”品类带来了多少净收入？
- Q07：FY2026 上半年的平均客单价（每笔订单金额）是多少？
- Q08：FY2025 的退款率是多少，即退款占退款前收入的百分比？（以百分比表示）
- Q09：FY2025 中，每笔发生退款的订单平均退款多少？
- Q10：FY2025 新注册的客户有多少位？
- Q11：2026 年 9 月的净收入比 8 月变化了百分之多少？（下降请用负数）
- Q12：FY2025 平均每笔订单包含多少件商品？
""",
    "ko": """# 경영진 질문 목록

기준일: 2026-09-30. 금액은 원화(KRW)로 부탁드립니다. 모든 질문에 숫자 하나로 답해 주세요.

- Q01: FY2025 순매출 합계는 얼마인가요?
- Q02: FY2026 1분기 순매출은 얼마인가요?
- Q03: 기준일 현재 활성 고객은 몇 명인가요?
- Q04: FY2025에 순매출이 가장 많았던 고객은 누구인가요? (customer_id로 답해 주세요)
- Q05: 여름 세일 당일(2026-07-01)에 주문이 몇 건 들어왔나요?
- Q06: FY2025 동안 '팬트리' 카테고리의 순매출은 얼마인가요?
- Q07: FY2026 상반기 평균 주문 금액(객단가)은 얼마인가요?
- Q08: FY2025 환불률, 즉 환불 전 매출 대비 환불 비율은 몇 퍼센트인가요?
- Q09: FY2025에 환불이 발생한 주문 1건당 평균 환불액은 얼마인가요?
- Q10: FY2025에 신규 가입한 고객은 몇 명인가요?
- Q11: 2026년 9월 순매출은 8월 대비 몇 퍼센트 변했나요? (감소했다면 음수로)
- Q12: FY2025 주문 1건당 평균 상품 수량(낱개 기준)은 얼마인가요?
""",
    "ja": """# 経営陣からの質問

基準日：2026-09-30。金額はウォン（KRW）でお願いします。各質問には数値ひとつでお答えください。

- Q01：FY2025 の純売上の合計はいくらですか。
- Q02：FY2026 第1四半期の純売上はいくらですか。
- Q03：基準日時点のアクティブ顧客は何人ですか。
- Q04：FY2025 に最も純売上が多かった顧客は誰ですか。（customer_id でお答えください）
- Q05：中間セール当日（2026-07-01）の注文は何件でしたか。
- Q06：FY2025 の「パントリー」カテゴリの純売上はいくらですか。
- Q07：FY2026 上半期の平均注文単価はいくらですか。
- Q08：FY2025 の返金率、つまり返金前売上に対する返金の割合は何パーセントですか。
- Q09：FY2025 に返金が発生した注文1件あたりの平均返金額はいくらですか。
- Q10：FY2025 に新規登録した顧客は何人ですか。
- Q11：2026年9月の純売上は8月と比べて何パーセント変化しましたか。（減少の場合はマイナスで）
- Q12：FY2025 の注文1件あたりの平均点数はいくつですか。
""",
    "es": """# Preguntas del equipo directivo

Fecha de referencia: 2026-09-30. Indique los importes en KRW. Responda cada pregunta con un único número.

- Q01: ¿Cuál fue nuestro ingreso neto total en el FY2025?
- Q02: ¿Cuál fue el ingreso neto del primer trimestre del FY2026?
- Q03: ¿Cuántos clientes activos tenemos a la fecha de referencia?
- Q04: ¿Qué cliente generó más ingreso neto en el FY2025? (responda con el customer_id)
- Q05: ¿Cuántos pedidos recibimos el día de las rebajas de mitad de año, el 2026-07-01?
- Q06: ¿Cuánto ingreso neto aportó la categoría "despensa" durante el FY2025?
- Q07: ¿Cuál fue el valor medio por pedido en el primer semestre del FY2026?
- Q08: ¿Cuál fue la tasa de reembolso del FY2025, es decir, los reembolsos como porcentaje del ingreso antes de reembolsos? (en porcentaje)
- Q09: En el FY2025, ¿cuál fue el reembolso medio por pedido reembolsado?
- Q10: ¿Cuántos clientes nuevos se registraron en el FY2025?
- Q11: ¿En qué porcentaje cambió el ingreso neto de septiembre de 2026 respecto a agosto de 2026? (negativo si bajó)
- Q12: En promedio, ¿cuántas unidades tenía un pedido en el FY2025?
""",
}

DICTIONARY = {
    "en": """# Data dictionary

All files are CSV (UTF-8). Table and column names are kept in English so they can be used directly in SQL.

- `customers.csv`: customer_id, signup_at_utc (timestamp, UTC), country (KR / JP / US), plan (subscription, one_off)
- `accounts_meta.csv`: customer_id, account_type (regular, staff, test)
- `products.csv`: product_id, product_name, category (box, coffee, tea, snacks, pantry, accessories), list_price_krw
- `orders.csv`: order_id, customer_id, ordered_at_utc (timestamp, UTC), status (completed, cancelled, payment_failed), currency (KRW / JPY / USD), subtotal, tax, total (amounts in the order currency)
- `order_items.csv`: order_id, product_id, quantity, unit_price (order currency)
- `payments.csv`: payment_id, order_id, paid_at_utc (timestamp, UTC), amount (order currency), method (card, bank_transfer, wallet)
- `refunds.csv`: refund_id, order_id, refunded_at_utc (timestamp, UTC), amount (order currency), reason (damaged, wrong_item, changed_mind, late_delivery)
- `fx_rates.csv`: rate_date, currency, krw_per_unit (KRW for one unit of the currency)
""",
    "zh": """# 数据字典

所有文件均为 CSV（UTF-8）。表名和字段名保留英文，可直接用于 SQL。

- `customers.csv`：customer_id、signup_at_utc（时间戳，UTC）、country（KR / JP / US）、plan（订阅、单次购买）
- `accounts_meta.csv`：customer_id、account_type（普通、员工、测试）
- `products.csv`：product_id、product_name、category（订阅盒、咖啡、茶、零食、食品储藏、器具）、list_price_krw
- `orders.csv`：order_id、customer_id、ordered_at_utc（时间戳，UTC）、status（已完成、已取消、支付失败）、currency（KRW / JPY / USD）、subtotal、tax、total（以订单币种计）
- `order_items.csv`：order_id、product_id、quantity、unit_price（订单币种）
- `payments.csv`：payment_id、order_id、paid_at_utc（时间戳，UTC）、amount（订单币种）、method（银行卡、银行转账、电子钱包）
- `refunds.csv`：refund_id、order_id、refunded_at_utc（时间戳，UTC）、amount（订单币种）、reason（商品破损、发错商品、不想要了、配送延迟）
- `fx_rates.csv`：rate_date、currency、krw_per_unit（1 单位该币种折合的韩元）
""",
    "ko": """# 데이터 사전

모든 파일은 CSV(UTF-8)입니다. 테이블명과 컬럼명은 SQL에서 바로 쓸 수 있도록 영문으로 두었습니다.

- `customers.csv`: customer_id, signup_at_utc(타임스탬프, UTC), country(KR / JP / US), plan(구독, 단품구매)
- `accounts_meta.csv`: customer_id, account_type(일반, 직원, 테스트)
- `products.csv`: product_id, product_name, category(구독박스, 커피, 차, 스낵, 팬트리, 용품), list_price_krw
- `orders.csv`: order_id, customer_id, ordered_at_utc(타임스탬프, UTC), status(완료, 취소, 결제실패), currency(KRW / JPY / USD), subtotal, tax, total(주문 통화 기준 금액)
- `order_items.csv`: order_id, product_id, quantity, unit_price(주문 통화)
- `payments.csv`: payment_id, order_id, paid_at_utc(타임스탬프, UTC), amount(주문 통화), method(카드, 계좌이체, 간편결제)
- `refunds.csv`: refund_id, order_id, refunded_at_utc(타임스탬프, UTC), amount(주문 통화), reason(파손, 오배송, 단순변심, 배송지연)
- `fx_rates.csv`: rate_date, currency, krw_per_unit(해당 통화 1단위당 원화)
""",
    "ja": """# データ辞書

すべて CSV（UTF-8）です。テーブル名とカラム名は SQL でそのまま使えるよう英語のままにしています。

- `customers.csv`：customer_id、signup_at_utc（タイムスタンプ、UTC）、country（KR / JP / US）、plan（定期便、都度購入）
- `accounts_meta.csv`：customer_id、account_type（一般、社員、テスト）
- `products.csv`：product_id、product_name、category（定期便ボックス、コーヒー、お茶、スナック、パントリー、器具）、list_price_krw
- `orders.csv`：order_id、customer_id、ordered_at_utc（タイムスタンプ、UTC）、status（完了、キャンセル、決済失敗）、currency（KRW / JPY / USD）、subtotal、tax、total（注文通貨建ての金額）
- `order_items.csv`：order_id、product_id、quantity、unit_price（注文通貨）
- `payments.csv`：payment_id、order_id、paid_at_utc（タイムスタンプ、UTC）、amount（注文通貨）、method（カード、銀行振込、電子マネー）
- `refunds.csv`：refund_id、order_id、refunded_at_utc（タイムスタンプ、UTC）、amount（注文通貨）、reason（破損、誤配送、お客様都合、配送遅延）
- `fx_rates.csv`：rate_date、currency、krw_per_unit（その通貨1単位あたりのウォン）
""",
    "es": """# Diccionario de datos

Todos los archivos son CSV (UTF-8). Los nombres de tablas y columnas se mantienen en inglés para poder usarlos directamente en SQL.

- `customers.csv`: customer_id, signup_at_utc (marca de tiempo, UTC), country (KR / JP / US), plan (suscripción, compra_suelta)
- `accounts_meta.csv`: customer_id, account_type (normal, empleado, prueba)
- `products.csv`: product_id, product_name, category (caja, café, té, snacks, despensa, accesorios), list_price_krw
- `orders.csv`: order_id, customer_id, ordered_at_utc (marca de tiempo, UTC), status (completado, cancelado, pago_fallido), currency (KRW / JPY / USD), subtotal, tax, total (importes en la moneda del pedido)
- `order_items.csv`: order_id, product_id, quantity, unit_price (moneda del pedido)
- `payments.csv`: payment_id, order_id, paid_at_utc (marca de tiempo, UTC), amount (moneda del pedido), method (tarjeta, transferencia, monedero)
- `refunds.csv`: refund_id, order_id, refunded_at_utc (marca de tiempo, UTC), amount (moneda del pedido), reason (dañado, artículo_erróneo, cambio_de_opinión, retraso)
- `fx_rates.csv`: rate_date, currency, krw_per_unit (KRW por una unidad de la moneda)
""",
}


def _ts(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _amt(x: float, cur: str) -> str:
    return f"{x:.{DECIMALS[cur]}f}"


def write_data(world: World, data_dir: Path, lang: str) -> None:
    lab = {k: v[lang] for k, v in L.items()}
    write_csv(data_dir / "customers.csv", ["customer_id", "signup_at_utc", "country", "plan"],
              [[c.id, _ts(c.signup_utc), c.country, lab[f"{c.plan}_plan"]] for c in world.customers])
    write_csv(data_dir / "accounts_meta.csv", ["customer_id", "account_type"],
              [[c.id, lab[c.kind]] for c in world.customers])
    write_csv(data_dir / "products.csv", ["product_id", "product_name", "category", "list_price_krw"],
              [[p, NAMES[p][LANG_IX[lang]], lab[cat], krw] for p, (cat, krw, _) in PRODUCTS.items()])
    write_csv(data_dir / "orders.csv", ["order_id", "customer_id", "ordered_at_utc", "status", "currency",
                                        "subtotal", "tax", "total"],
              [[o.id, o.customer, _ts(o.ts_utc), lab[o.status], o.currency, _amt(o.subtotal, o.currency),
                _amt(o.tax, o.currency), _amt(o.total, o.currency)] for o in world.orders])
    write_csv(data_dir / "order_items.csv", ["order_id", "product_id", "quantity", "unit_price"],
              [[o.id, p, q, _amt(u, o.currency)] for o in world.orders for p, q, u in o.lines])
    pay = []
    for o in world.orders:
        if o.paid:
            pay.append([f"PM{len(pay) + 1:06d}", o.id, _ts(o.ts_utc + timedelta(seconds=40 + (len(pay) * 37) % 600)),
                        _amt(o.total, o.currency), lab[o.method]])
    write_csv(data_dir / "payments.csv", ["payment_id", "order_id", "paid_at_utc", "amount", "method"], pay)
    refunds = sorted(([r[0], o.id, _ts(r[1]), _amt(r[2], o.currency), lab[r[3]]] for o in world.orders
                      for r in o.refunds), key=lambda r: r[0])
    write_csv(data_dir / "refunds.csv", ["refund_id", "order_id", "refunded_at_utc", "amount", "reason"], refunds)
    write_csv(data_dir / "fx_rates.csv", ["rate_date", "currency", "krw_per_unit"],
              [[d.isoformat(), cur, rate] for (cur, d), rate in sorted(world.fx.items(), key=lambda kv: (kv[0][1], kv[0][0]))
               if cur != "KRW"])
    (data_dir / DOC_FILES["questions"][lang]).write_text(QUESTIONS[lang], encoding="utf-8")
    (data_dir / DOC_FILES["dictionary"][lang]).write_text(DICTIONARY[lang], encoding="utf-8")



# ── scoring ──────────────────────────────────────────────────────────────────

def _correct(q: str, got: float, exact: float, unit: int) -> bool:
    if q in EXACT_Q:
        return abs(got - exact) < 1e-9
    if q == "Q11":
        tol = PP_TOL
    elif q in MONEY_Q:     # half the rounding unit: the exact figure rounded as finance requires always counts
        tol = max(REL_TOL * abs(exact), unit / 2.0 + 1e-6)
    else:
        tol = REL_TOL * abs(exact)
    cands = [got, got * 100.0] if q in PERCENT_Q else [got]   # a percentage given as a fraction is accepted
    return any(abs(c - exact) <= tol for c in cands)


def _follows(q: str, got: float, figure: float, unit: int) -> bool:
    """Whether an answer is this figure as a sheet would write it: the count or id itself; a money figure rounded
    to the unit, or within 0.1%; a ratio rounded to two decimals, or within 0.1%. Five times tighter than the
    scorer's tolerance (_correct), which decides right and wrong: a wrong figure counts against a reading only
    when it is that reading's figure, not merely a figure within 0.5% of it (two misreadings of different facts
    often lie that close to each other)."""
    if q in EXACT_Q:
        return abs(got - figure) < 1e-9
    tol = max(1e-3 * abs(figure), unit / 2.0 + 1e-6 if q in MONEY_Q else 0.005 + 1e-9)
    cands = [got, got * 100.0] if q in PERCENT_Q else [got]
    return any(abs(c - figure) <= tol for c in cands)


def _is_number(v) -> bool:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return False
    try:
        return math.isfinite(v)
    except OverflowError:      # a JSON integer too large for a float is not a usable figure
        return False


def _rounded(v: float, unit: int) -> bool:
    return abs(v / unit - round(v / unit)) <= 1e-6


def _test_free_figures(world: World, rules: Rules) -> dict:
    """{count or id question: its figures under the other readings of the export that leave test accounts out}:
    every misreading of MISREADINGS but "test accounts kept in", another fiscal year, another active window. An
    answer equal to the figure with test accounts is not held against the sheet when one of these gives it too
    (a UTC-day count can equal the test-inclusive Korea-time count by coincidence)."""
    memo = world.__dict__.setdefault("_test_free", {})
    key = (rules.fy_start, rules.active_days)
    if key not in memo:
        others = [truth(world, rules, **change) for readings in MISREADINGS.values() for change in readings.values()
                  if change.get("accounts") != "all"]
        others += [compute(world, m, rules.active_days) for m in range(1, 13) if m != rules.fy_start]
        others += [compute(world, rules.fy_start, w) for w in WINDOWS if w != rules.active_days]
        memo[key] = {q: {x[q] for x in others} for q in EXACT_Q}
    return memo[key]


def score(world: World, submission_dir: Path, setting: Setting) -> dict:
    rules = rules_of(setting)
    try:
        doc = read_json(submission_dir, "answers.json")
        if not isinstance(doc, dict):
            raise Fatal("answers.json must be an object {\"Q01\": number or null, ...}")
    except Fatal as e:
        return {"fatal": str(e)}
    exact = truth(world, rules)            # for a period still running: the figure to date
    with_tests = truth(world, rules, accounts="all")
    violations = []
    for q in QIDS:     # the file's shape, for every question (used this round or not)
        if q not in doc:
            violations.append(("answer_format", f"{q} is missing"))
        elif doc[q] is not None and not _is_number(doc[q]):
            violations.append(("answer_format", f"{q} is neither a number nor null: {repr(doc[q])[:60]}"))
    status = {}
    for q in rules.scored:   # an answer to a question this round does not use has no effect
        v = doc.get(q)
        if v is None and q in doc:
            status[q] = "dont_know"
            continue
        if not _is_number(v):
            status[q] = "wrong"      # missing or malformed: already an answer_format violation
            continue
        v = float(v)
        if q in rules.running:       # finance's habit; with the CFO's exception the figure to date is judged
            violations.append(("running_period", f"{q} = {v:g} is a figure for a period that is still running on "
                                                 f"the reference date"))
        if q in MONEY_Q and not _rounded(v, rules.unit):
            violations.append(("report_rounding", f"{q} = {v} is a money figure not rounded to {rules.unit:,} KRW"))
        if (q in EXACT_Q and with_tests[q] != exact[q] and abs(v - with_tests[q]) < 1e-9
                and v not in _test_free_figures(world, rules)[q]):
            violations.append(("exclude_test_accounts", f"{q} = {v:g} matches the figure that includes test accounts"))
        status[q] = "right" if _correct(q, v, exact[q], rules.unit) else "wrong"
    reward = {"right": rules.right, "dont_know": rules.dont_know, "wrong": rules.wrong}
    count = {k: sum(1 for s in status.values() if s == k) for k in reward}
    n, answered = len(rules.scored), count["right"] + count["wrong"]
    total = sum(reward[s] for s in status.values())
    return {"violations": violations, "objective": total / (rules.right * n),
            "metrics": {"scored": n, "running": len(rules.running), "answered": answered, "right": count["right"],
                        "wrong": count["wrong"], "dont_know": count["dont_know"],
                        "accuracy_on_answered": round(count["right"] / answered, 6) if answered else None,
                        "coverage": round(answered / n, 6), "reward": total,
                        "wrong_questions": [q for q in rules.scored if status[q] == "wrong"],
                        "dont_know_questions": [q for q in rules.scored if status[q] == "dont_know"]}}


# ── diagnostic: which reading of each fact the sheet's figures follow ────────

def _other_readings(world: World, rules: Rules, tier: str) -> dict:
    """{(target, reading): the twelve figures under it} for every other reading a sheet is checked for in this
    setting: another first month of the fiscal year, the misreadings of the fixed facts in force in the tier
    (MISREADINGS, then their VARIANTS) and another active window."""
    out = {("fiscal_year", f"a fiscal year from month {m}"): compute(world, m, rules.active_days)
           for m in range(1, 13) if m != rules.fy_start}
    for known in (MISREADINGS, VARIANTS):
        for target, readings in known.items():
            if tier in TARGET_TIERS[target]:
                out.update({(target, name): truth(world, rules, **change) for name, change in readings.items()})
    out.update({("active_customer", f"a {w}-day window"): compute(world, rules.fy_start, w)
                for w in WINDOWS if w != rules.active_days})
    return out


def _verdict(tests: list) -> tuple:
    """(enforced, evidence, the readings followed) from [(reading, client's figures, the reading's figures, whether
    the reading is only a variant)]: not enforced when more of the questions that tell some reading from the
    client's carry that reading's figure than the client's; enforced when some carry the client's where a reading
    that is not a mere variant gives another; else not determinable."""
    followed = [(name, theirs) for name, ours, theirs, _ in tests if len(theirs) > len(ours)]
    if followed:
        name, theirs = max(followed, key=lambda x: len(x[1]))
        return False, f"{', '.join(sorted(theirs))}: the figure under {name}", [name for name, _ in followed]
    seen = sorted({q for _, ours, _, variant in tests if not variant for q in ours})
    if seen:
        return True, f"{', '.join(seen)}: the client's figure where another reading gives a different one", []
    return None, "no answered question tells the readings apart", []


def diagnose(world: World, submission_dir: Path, setting: Setting, scored: dict) -> dict:
    """enforced[target] for every target in force, from the sheet's own figures. For each fact: the scored
    questions with a figure where a misreading of that fact alone would be wrong, and whose figure the sheet gave
    there, the client's or the misreading's. A wrong figure counts for the one reading whose figure it is, as a
    sheet would write it (_follows: rounded to the unit or to two decimals, or within 0.1%), and for the nearest
    when several give it, so a sheet that misreads one fact is not also held to misread another whose figure
    happens to lie close; a figure no single reading explains tells nothing. Lazy (the audit and a run's scoring
    ask for it): it computes the export under every other reading once per world and conventions."""
    rules = rules_of(setting)
    try:
        doc = read_json(submission_dir, "answers.json")
    except Fatal:
        return {}
    if not isinstance(doc, dict):
        return {}
    exact, unit = truth(world, rules), rules.unit
    numbers = {q: float(doc[q]) for q in rules.scored if _is_number(doc.get(q))}
    given = {q: v for q, v in numbers.items() if q not in rules.running}
    readings = _other_readings(world, rules, setting.tier)

    def reported(q: str, x: float) -> float:        # as a sheet that follows the rounding rule writes the figure
        return round(x / unit) * unit if q in MONEY_Q and math.isfinite(x) else x

    def tells(q: str, other: dict) -> bool:         # this reading's figure for q, exact or rounded, would be wrong
        return not (_correct(q, other[q], exact[q], unit) or _correct(q, reported(q, other[q]), exact[q], unit))

    def distance(q: str, v: float, x: float) -> float:
        return min(abs(c - x) for c in ([v, v * 100.0] if q in PERCENT_Q else [v]))

    right = [q for q, v in given.items() if _correct(q, v, exact[q], unit)]
    theirs: dict = {key: [] for key in readings}    # the wrong figures each reading explains best
    for q, v in given.items():
        if q in right:
            continue
        near = [(distance(q, v, reported(q, other[q])), key) for key, other in readings.items()
                if tells(q, other) and _follows(q, v, other[q], unit)]
        keys = [key for d, key in near if d <= min(x for x, _ in near) + 1e-9]
        if len({target for target, _ in keys}) == 1:         # two facts' readings give this figure: it tells nothing
            for key in keys:
                theirs[key].append(q)
    enforced, evidence, other_years, misread = {}, {}, [], set()
    for target in dict.fromkeys(target for target, _ in readings):
        tests = [(name, [q for q in right if tells(q, other)], theirs[(t, name)], name in VARIANTS.get(t, ()))
                 for (t, name), other in readings.items() if t == target]
        enforced[target], evidence[target], followed = _verdict(tests)
        misread.update(q for name in followed for q in theirs[(target, name)])     # the figures of a reading followed
        if target in ("fiscal_year", "fy_naming"):
            other_years += [readings[(target, name)] for name in followed]

    # the rounding unit: every money figure a multiple of it, and none rounded to a coarser one where that is wrong
    # (a wrong figure of a misreading the sheet follows is that fact's, even when it happens to equal the exact
    # figure rounded coarsely)
    money = {q: v for q, v in numbers.items() if q in MONEY_Q}
    off = sorted(q for q, v in money.items() if not _rounded(v, unit))
    coarse = sorted(q for q, v in money.items() if q in given and q not in right and q not in misread
                    and any(abs(v - round(exact[q] / c) * c) < 1e-6 for c in (unit * 10, unit * 100)))
    if not money:
        enforced["report_rounding"], evidence["report_rounding"] = None, "no money figure given"
    elif off or coarse:
        enforced["report_rounding"] = False
        evidence["report_rounding"] = (f"{', '.join(off)}: not a multiple of {unit:,} KRW" if off else
                                       f"{', '.join(coarse)}: the exact figure rounded to a coarser unit")
    else:
        enforced["report_rounding"] = True
        evidence["report_rounding"] = f"{', '.join(sorted(money))}: multiples of {unit:,} KRW"

    # the running periods: null there, or a number. The figure to date breaks the habit; so does any other number
    # (a projection, a zero) on a sheet whose other answers follow the client's fiscal year. A number that another
    # fiscal year the sheet follows explains counts against that fact, not this one, and a number on a sheet
    # whose fiscal year cannot be told is not determinable.
    if rules.running:
        figures = [q for q in rules.running if q in numbers]
        other_year = [q for q in figures if any(_correct(q, numbers[q], other[q], unit) for other in other_years)]
        to_date = sorted(q for q in figures if q not in other_year and _correct(q, numbers[q], exact[q], unit))
        own_year = enforced.get("fiscal_year") is True and enforced.get("fy_naming") is not False
        numbered = sorted(q for q in figures if q not in other_year and q not in to_date and own_year)
        left = sorted(q for q in rules.running if q in doc and doc[q] is None)
        if to_date:
            enforced["running_period"] = False
            evidence["running_period"] = f"{', '.join(to_date)}: the figure to date for a period still running"
        elif numbered:
            enforced["running_period"] = False
            evidence["running_period"] = (f"{', '.join(numbered)}: a number for a period still running, on a sheet "
                                          f"that follows the client's fiscal year")
        elif left:
            enforced["running_period"] = True
            evidence["running_period"] = f"{', '.join(left)}: null for a period still running"
        else:
            enforced["running_period"] = None
            evidence["running_period"] = "a figure for a running period that is not the figure to date"
    return {"enforced": enforced, "evidence": evidence}


# ── reference, baseline and the other sheets ─────────────────────────────────

def _write(out_dir: Path, ans: dict) -> None:
    (out_dir / "answers.json").write_text(json.dumps(ans, indent=2), encoding="utf-8")


def reference_solution(world: World, out_dir: Path, setting: Setting) -> None:
    """A careful analyst who knows every one of the setting's conventions: the exact figure of each question the
    round needs, money rounded to the setting's unit; null for the questions the round does not need and for a
    period that is still running on the reference date. It reaches the bound (Rules.bound)."""
    _write(out_dir, _sheet(world, rules_of(setting)))


def baseline_solution(world: World, out_dir: Path, setting: Setting) -> None:
    """What finance reports without an analyst: "not available yet" (null) for every question. It earns the
    don't-know reward everywhere, so saying "don't know" to everything scores 0 on the normalized scale."""
    _write(out_dir, {q: None for q in QIDS})


def best_known_solution(world: World, out_dir: Path, setting: Setting) -> None:
    """The answer key for all twelve questions, whether the round needs them or not: another sheet than the
    reference in easy and medium, with the same objective (the bound)."""
    _write(out_dir, _sheet(world, rules_of(setting), every_question=True))


def objective_bound(world: World, setting: Setting) -> float:
    """A proven upper bound on a valid sheet's objective: a scored question earns at most 2, and one whose period
    is still running at most the null's reward (a number there breaks running_period)."""
    return rules_of(setting).bound


def _literal_answers(world: World) -> dict:
    ans = compute(world, fy_start=1, active_days=30, local_day=False, both_labels=False)
    return {q: (round(v) if q in MONEY_Q else v) for q, v in ans.items()}


def literal_solution(world: World, out_dir: Path) -> None:
    """The request done as written ("answer every question with a single number", money in KRW): a careful analysis
    of the export with the natural reading of every definition the client did not give. Completed orders only,
    test accounts out (the dictionary flags them), net revenue = subtotal less refunds (tax excluded) at the
    order date's rate, as compute() does; the fiscal year read as the calendar year, days as the stored UTC dates,
    "active" as ordered in the last 30 days, "pantry" as the products labelled pantry, and money to the whole won.
    Every question gets a number (the same sheet in every setting)."""
    _write(out_dir, _literal_answers(world))


def _export_days(world: World) -> bool:
    """What the export itself shows about its days, from orders.csv and the two dates the questions file names
    (the sale day and the reference date): True when they run on Korea time. The sale-day surge then fills one
    Korea-time day (it starts at 15:00 UTC on the eve, so the stored UTC dates split it over two days) and the
    export's last order falls on the reference date in Korea time (before 15:00 UTC); on UTC days the surge would
    fill the UTC date and the export would run on to midnight UTC. Nothing here is the client's word: an analyst
    who looks at the hours of the sale-day orders sees it."""
    stamps = [o.ts_utc for o in world.orders]
    korea = sum(1 for t in stamps if (t + KST).date() == SALE_DAY)
    utc = sum(1 for t in stamps if t.date() == SALE_DAY)
    return korea > utc and (max(stamps) + KST).date() <= AS_OF


def _never_asking_sheets(world: World, candidates: dict) -> list:
    """The sheets a careful analyst who never asks chooses from, each with the credit it expects under its own
    reading: [(expected credit, (fiscal year guessed or None, window guessed or None, rounding unit), sheet)].

    The reading is the literal sheet's (the pantry label, completed orders, test accounts out, revenue without tax
    at the order date's rate) except for the days, which it reads off the export (_export_days: Korea time). It
    knows the rules as rules, not their draw: money off the client's unit, or a number for a period that is still
    running under the client's fiscal year, makes the sheet unusable; every fiscal-year start, window, unit and
    reward for a null in the pools is equally likely, and all twelve questions count (it does not know which the
    round uses).

    A sheet starts from one guess of the fiscal year (or none: a fiscal-period question then gets a figure only
    when more than one fiscal year of the pool gives it, e.g. the units per order, which hardly move with the
    year), one window (or none: Q03 null) and one rounding unit, and then leaves null, one at a time, the answer
    whose absence raises its expected credit most (a figure it would only guess, a small money figure a coarse
    unit moves, a period that may still be running), until no such answer is left."""
    key = tuple(sorted((name, tuple(pool)) for name, pool in candidates.items()))
    memo = world.__dict__.setdefault("_never_asking", {})
    if key in memo:
        return memo[key]
    natural = {"local_day": _export_days(world), "both_labels": False}
    fys, windows = list(candidates["fy_start"]), list(candidates["active_days"])
    units, nulls = sorted(set(candidates["rounding_unit"])), [float(x) for x in candidates["dont_know_reward"]]
    belief = {(fy, w): compute(world, fy, w, **natural) for fy in fys for w in windows}
    running = {fy: running_questions(fy) for fy in fys}
    settings = list(itertools.product(fys, windows, units, nulls))
    n, marks = len(QIDS), {}

    def mark(q: str, v) -> list:
        """What the answer earns in each possible setting; None where it makes the sheet unusable."""
        if (q, v) not in marks:
            marks[(q, v)] = [dk if v is None else None if (q in MONEY_Q and not _rounded(v, u)) or q in running[f]
                             else RIGHT_REWARD if _correct(q, v, belief[(f, x)][q], u) else WRONG_REWARD
                             for f, x, u, dk in settings]
        return marks[(q, v)]

    def expected(sheet: dict) -> float:
        """The credit the sheet expects: 0 where it is unusable, else its place between the all-null sheet (0)
        and the sheet that is right wherever a figure exists (1)."""
        columns = [mark(q, sheet[q]) for q in QIDS]
        total = 0.0
        for i, (f, _, _, dk) in enumerate(settings):
            got = [c[i] for c in columns]
            if None not in got:
                best = RIGHT_REWARD * (n - len(running[f])) + dk * len(running[f])
                total += min(1.0, max(0.0, (sum(got) - dk * n) / (best - dk * n)))
        return total / len(settings)

    def figure(q: str, fy, w, unit: int):
        if q == "Q03":
            v = belief[(fys[0], w)][q] if w else None
        elif q not in PERIOD_OF:
            v = belief[(fys[0], windows[0])][q]
        elif fy:
            v = belief[(fy, windows[0])][q]
        else:           # no guess: the figure most fiscal years of the pool agree on, when more than one does
            figs = [belief[(f, windows[0])][q] for f in fys]
            agree = [sum(_correct(q, x, y, unit) for y in figs) for x in figs]
            v = figs[agree.index(max(agree))] if max(agree) > 1 or len(figs) == 1 else None
        return round(v / unit) * unit if q in MONEY_Q and v is not None else v

    out = []
    for fy, w, unit in itertools.product([None, *fys], [None, *windows], units):
        sheet = {q: figure(q, fy, w, unit) for q in QIDS}
        value = expected(sheet)
        while True:
            trials = [(expected({**sheet, q: None}), q) for q in QIDS if sheet[q] is not None]
            top = max(trials, key=lambda t: t[0], default=None)        # the first such answer on a tie
            if top is None or top[0] <= value + 1e-12:
                break
            value, sheet = top[0], {**sheet, top[1]: None}
        out.append((value, (fy, w, unit), sheet))
    memo[key] = out
    return out


def robust_solution(world: World, out_dir: Path, tier: str, candidates: dict) -> None:
    """The sheet that never asks, from the agent's view and the tier's pools alone: of the sheets a careful
    analyst who never asks chooses from (_never_asking_sheets), the one with the highest expected credit under
    its own reading (the first such sheet on a tie). It reads the days off the export, so its sale-day count and
    its September change are right; it cannot know that its pantry label is wrong, nor which fiscal year, window
    and unit are the client's, so it answers what does not depend on them and guesses or leaves null the rest."""
    best = None
    for value, _, sheet in _never_asking_sheets(world, candidates):
        if best is None or value > best[0] + 1e-12:
            best = (value, sheet)
    _write(out_dir, best[1])


def _score_answers(world: World, ans: dict, setting: Setting) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        _write(Path(tmp), ans)
        return score(world, Path(tmp), setting)


# ── ground truth audit: one misreading per fact, and the shortcuts ───────────

def ablations(world: World, setting: Setting) -> dict:
    """{target: the reference sheet with only that fact misread} for the facts that are not a drawn parameter:
    the first reading of MISREADINGS, and for the running periods the figure to date. Every other figure, the
    rounding and the nulls are the reference's."""
    rules = rules_of(setting)
    out = {target: (lambda out_dir, change=next(iter(readings.values())): _write(out_dir, _sheet(world, rules, **change)))
           for target, readings in MISREADINGS.items() if setting.tier in TARGET_TIERS[target]}
    if rules.running:
        out["running_period"] = lambda out_dir: _write(out_dir, _sheet(world, rules, to_date=True))
    return out


COARSE_UNIT = 10000      # whole 10,000 KRW: a multiple of every rounding unit of the pool, so valid under each of them


def _steady_units(world: World) -> float:
    """The units per order (Q12) as an analyst gives them who knows no fiscal year: the median over the fiscal
    years the export covers whole (FY2025 inside the data and over by the reference date). The figure hardly
    moves with the year."""
    local = _export_days(world)
    figures = sorted(compute(world, m, 30, local_day=local, both_labels=False)["Q12"] for m in range(1, 13)
                     if DATA_START <= periods(m)["fy2025"][0] and periods(m)["fy2025"][1] <= AS_OF)
    return figures[len(figures) // 2]


def shortcuts(world: World, setting: Setting) -> dict:
    """The sheets a lazy or gaming analyst would send; each must be invalid or score at most half the reference's
    quality. The literal sheet's near misses are here: the literal sheet with each rule it breaks kept, and with
    the one fact the export itself shows (its days are Korea-time days) read right. So are the sheets that play
    the scheme: one safe answer on the all-null sheet, only the answers that need no client fact, and every rule
    kept without knowing a parameter."""
    rules = rules_of(setting)
    literal, face = _literal_answers(world), _face_value(world)
    local = compute(world, fy_start=1, active_days=30, local_day=_export_days(world), both_labels=False)
    running = set(running_questions(rules.fy_start))

    def nulled(ans: dict, questions) -> dict:
        return {q: (None if q in questions else v) for q, v in ans.items()}

    def all_null(out_dir: Path) -> None:
        """Leave every question as "not available yet" (null), so that no figure can be wrong"""
        _write(out_dir, {q: None for q in QIDS})

    def face_value(out_dir: Path) -> None:
        """Sum the export at face value (calendar year, UTC dates, every order row, totals with tax, the latest rate), with both rules kept: rounded to the client's unit, null where the period is still running"""
        _write(out_dir, nulled(_round_money(face, rules.unit), running))

    def literal_rounded(out_dir: Path) -> None:
        """The literal sheet with the rounding rule kept: its money figures rounded to the client's unit"""
        _write(out_dir, _round_money(literal, rules.unit))

    def literal_running_null(out_dir: Path) -> None:
        """The literal sheet with the running-period habit kept: null where the client's period is still running, money to the whole won"""
        _write(out_dir, nulled(literal, running))

    def literal_valid(out_dir: Path) -> None:
        """The literal sheet with every rule kept: money rounded to the client's unit and null where the period is still running"""
        _write(out_dir, nulled(_round_money(literal, rules.unit), running))

    def no_money(out_dir: Path) -> None:
        """Dodge the rounding rule: leave every money figure null and answer the counts, the customer and the ratios from the natural reading"""
        _write(out_dir, nulled(literal, MONEY_Q))

    def dated_only(out_dir: Path) -> None:
        """Dodge the fiscal year: answer only the questions with their own dates (active customers, the sale day, September against August) and leave the rest null"""
        _write(out_dir, nulled(literal, PERIOD_OF))

    def one_safe_answer(out_dir: Path) -> None:
        """The all-null sheet with one thing changed: only the units per order (Q12) answered, the one figure that hardly moves with the fiscal year"""
        _write(out_dir, {q: (_steady_units(world) if q == "Q12" else None) for q in QIDS})

    def data_only(out_dir: Path) -> None:
        """Answer only what the export settles without any client fact (the sale-day orders and the September change on the Korea-time days its timestamps show, and the units per order) and leave the rest null"""
        _write(out_dir, {**{q: None for q in QIDS}, "Q05": local["Q05"], "Q11": local["Q11"],
                         "Q12": _steady_units(world)})

    def literal_local_days(out_dir: Path) -> None:
        """The literal sheet with its days read off the export (Korea time: the sale-day surge starts at 15:00 UTC on the eve) and every rule kept: money rounded to the client's unit, null where the period is still running"""
        _write(out_dir, nulled(_round_money(local, rules.unit), running))

    def strictest_rules(out_dir: Path) -> None:
        """Keep every rule without knowing one parameter: the literal sheet with its money in whole 10,000 KRW (a multiple of every unit) and the two FY2026 questions (Q02, Q07) null in case their period is still running"""
        _write(out_dir, nulled(_round_money(literal, COARSE_UNIT), ("Q02", "Q07")))

    return {"all_null": all_null, "face_value": face_value, "literal_rounded": literal_rounded,
            "literal_running_null": literal_running_null, "literal_valid": literal_valid, "no_money": no_money,
            "dated_only": dated_only, "one_safe_answer": one_safe_answer, "data_only": data_only,
            "literal_local_days": literal_local_days, "strictest_rules": strictest_rules}


def violating_examples(world: World, setting: Setting) -> dict:
    rules = rules_of(setting)
    ref = _sheet(world, rules)
    # Following the rules must never cost a question. The reference (exact figures rounded to the setting's unit,
    # null for a period still running) reaches the bound, and with the running-period habit set aside the figure
    # to date, rounded the same way, is right for every scored question.
    full = _score_answers(world, ref, setting)
    if full["violations"] or abs(full["objective"] - rules.bound) > 1e-12:
        raise AssertionError(f"the exact answers rounded to {rules.unit:,} KRW do not reach the bound "
                             f"({setting.label}): {full}")
    figures = _sheet(world, rules, to_date=True)
    to_date = _score_answers(world, figures, setting)
    if {r for r, _ in to_date["violations"]} - {"running_period"} or to_date["metrics"]["right"] != len(rules.scored):
        raise AssertionError(f"the exact answers to date rounded to {rules.unit:,} KRW are not all right "
                             f"({setting.label}): {to_date}")
    exact, with_tests = truth(world, rules), truth(world, rules, accounts="all")
    missing = object()

    def variant(**changes):
        ans = {k: v for k, v in {**ref, **changes}.items() if v is not missing}
        return lambda out: _write(out, ans)

    test_q = next((q for q in ("Q04", "Q03", "Q10", "Q05") if q in rules.scored and with_tests[q] != exact[q]
                   and with_tests[q] not in _test_free_figures(world, rules)[q]), None)
    if test_q is None:
        raise AssertionError(f"no scored count or id changes with the test accounts ({setting.label})")
    examples = {
        "answer_format": variant(Q12=missing),
        "exclude_test_accounts": variant(**{test_q: with_tests[test_q]}),
        "report_rounding": variant(**{q: exact[q] for q in MONEY_Q if ref[q] is not None}),
    }
    if rules.running:
        examples["running_period"] = variant(**{rules.running[0]: figures[rules.running[0]]})
    return examples
