"""Answering managers' business questions from a subscription shop's export (original FDE-Bench v2 case).

A Seoul-based coffee & tea subscription shop exports its order database as CSV
tables and asks for answers to twelve managers' questions. The request only
says "answer them"; the definitions that decide every number (fiscal year,
local day, test accounts, which orders count, net revenue, FX, "active",
a renamed category, rounding of money figures) are in the requirements, and so
is what a wrong figure costs against a figure left as "not available yet".

Every answer is a number or null ("don't know"). A scored question earns
right_reward (2) when correct, dont_know_reward when null and wrong_reward (0)
when wrong; the objective is the total over 2 x the number of scored questions.
So the case measures calibrated abstention: a sheet that knows the setting's
scheme answers a question only when its chance of being right is above
dont_know_reward / right_reward.

The data is the same in every setting. A setting (tier, rule seed) decides which
questions are scored and the client's conventions:

  tiers (which questions the board pack needs this round; others have no effect)
    easy    Q01, Q03, Q04, Q10, Q12: counted orders, test and staff accounts,
            the fiscal year, the active window, rounding
    medium  + Q02, Q05, Q07, Q08, Q09, Q11: net revenue, FX and Korea-time days
            (and the October refunds of September orders)
    hard    all twelve: + Q06, which needs the snacks -> pantry rename
  parameters a rule seed draws, each on its own (case.yaml `params`, one pool for every tier)
    fy_start          first month of the fiscal year: January, April or July
    active_days       active-customer window: 30, 60 or 90 days
    rounding_unit     money is reported to the nearest 100, 1,000 or 10,000 KRW
    dont_know_reward  what a null earns: 0.5, 1 or 1.5 (wrong 0, right 2)
  derived (derive_params)
    fy2025, fy2026_q1, fy2026_h1, active_from
                      the periods these give, worded per locale as the requirements state them
    right_reward, wrong_reward
                      the fixed ends of the reward scheme (2 and 0)

Table and column identifiers stay ASCII (they are SQL identifiers); categorical
labels, product names, the questions file and the data dictionary are localized.
"""

from __future__ import annotations

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
    "easy": ("Q01", "Q03", "Q04", "Q10", "Q12"),
    "medium": ("Q01", "Q02", "Q03", "Q04", "Q05", "Q07", "Q08", "Q09", "Q10", "Q11", "Q12"),
    "hard": tuple(QIDS),
}
UNRESOLVED = ("Q06",)            # what the reference cannot settle: it misses the snacks -> pantry rename
GUESS_BELIEF = 0.5               # the reference's chance that its unsettled answer is right
RIGHT_REWARD, WRONG_REWARD = 2, 0      # the fixed ends of the scheme; the rule seed draws dont_know_reward


def _first(year: int, month: int) -> date:
    """The first day of `month` of `year`; months past 12 run into the next years."""
    return date(year + (month - 1) // 12, (month - 1) % 12 + 1, 1)


def periods(fy_start: int) -> dict[str, tuple[date, date]]:
    """FY2025, the first quarter and the first half of FY2026 for a fiscal year that starts in month fy_start
    and is named after the calendar year it starts in. A period still running on the reference date counts up
    to the reference date."""
    fy26 = _first(2026, fy_start)
    return {"fy2025": (_first(2025, fy_start), fy26 - DAY),
            "q1": (fy26, min(_first(2026, fy_start + 3) - DAY, AS_OF)),
            "h1": (fy26, min(_first(2026, fy_start + 6) - DAY, AS_OF))}


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

    @property
    def answers_unsettled(self) -> bool:
        """The reference's abstention policy: answer an unsettled question only when its expected reward beats
        "don't know" (a tie abstains). With even odds: answer iff dont_know < right / 2, i.e. when a null earns
        0.5 (not at 1, a tie, nor at 1.5)."""
        return GUESS_BELIEF * self.right + (1 - GUESS_BELIEF) * self.wrong > self.dont_know


def rules_of(setting: Setting) -> Rules:
    p = setting.params
    return Rules(int(p["fy_start"]), int(p["active_days"]), int(p["rounding_unit"]), float(p["right_reward"]),
                 float(p["dont_know_reward"]), float(p["wrong_reward"]), SCORED[setting.tier])


# ── rule seeds: what the drawn parameters give ───────────────────────────────

SPAN = {"zh": "{} 至 {}", "en": "{} to {}", "ko": "{} ~ {}", "ja": "{}〜{}", "es": "del {} al {}"}


def _span(a: date, b: date) -> dict:
    """A date range as each locale's requirements write it."""
    return {lang: fmt.format(a.isoformat(), b.isoformat()) for lang, fmt in SPAN.items()}


def derive_params(params: dict, tier: str) -> dict:
    """The periods the texts state, from the drawn fiscal-year start and active window, and the fixed ends of
    the reward scheme. The first half of FY2026 is stated whole (a July year's runs to December); the code
    counts a period still running on the reference date up to it (periods())."""
    fy_start = int(params["fy_start"])
    per = periods(fy_start)
    return {"fy2025": _span(*per["fy2025"]),
            "fy2026_q1": _span(per["q1"][0], _first(2026, fy_start + 3) - DAY),
            "fy2026_h1": _span(per["h1"][0], _first(2026, fy_start + 6) - DAY),
            "active_from": (AS_OF - timedelta(days=int(params["active_days"]) - 1)).isoformat(),
            "right_reward": RIGHT_REWARD, "wrong_reward": WRONG_REWARD}


def admissible(params: dict, tier: str) -> bool:
    """Rewards rise from wrong to don't know to right, FY2026 has started by the reference date, and the active
    window starts after the data does. Every combination of the current pools passes; this guards new ones."""
    rewards_rise = float(params["wrong_reward"]) < float(params["dont_know_reward"]) < float(params["right_reward"])
    fy_started = _first(2026, int(params["fy_start"])) <= AS_OF
    window_in_data = 1 <= int(params["active_days"]) <= (AS_OF - DATA_START).days + 1
    return rewards_rise and fy_started and window_in_data


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
    # FX: KRW per unit, one rate per local calendar day.
    fx = {}
    usd, jpy = 1440.0, 9.40
    d = date(2024, 12, 1)
    while d <= AS_OF:
        usd = min(1500.0, max(1300.0, usd + rng.gauss(0, 5.0)))
        jpy = min(9.9, max(8.6, jpy + rng.gauss(0, 0.035)))
        fx[("USD", d)], fx[("JPY", d)], fx[("KRW", d)] = round(usd, 2), round(jpy, 4), 1.0
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


# ── analysis (truth, reference and signature variants) ───────────────────────

def compute(world: World, fy_start: int = 4, active_days: int = 90, local_day=True, exclude_test=True,
            both_labels=True) -> dict:
    """The twelve exact answers under one set of conventions (the truth with every flag left on)."""
    def day(ts: datetime) -> date:
        return (ts + KST).date() if local_day else ts.date()

    def within(d, rng_):
        return rng_[0] <= d <= rng_[1]

    per = periods(fy_start)
    fy_, q1, h1 = per["fy2025"], per["q1"], per["h1"]
    window = (AS_OF - timedelta(days=active_days - 1), AS_OF)
    food = FOOD if both_labels else ("pantry",)
    rows = []   # per completed order: (customer, local date, gross KRW, refund ex-tax KRW, units, food net KRW)
    for o in world.orders:
        if o.status != "completed":
            continue
        if exclude_test and world.cust[o.customer].kind == "test":
            continue
        d = day(o.ts_utc)
        rate = world.fx[(o.currency, d)]
        refund_incl = sum(r[2] for r in o.refunds)
        refund_ex = refund_incl * o.subtotal / o.total
        keep = 1.0 - refund_ex / o.subtotal
        food_net = sum(q * u for p, q, u in o.lines if PRODUCTS[p][0] in food) * keep * rate
        rows.append((o.customer, d, o.subtotal * rate, refund_ex * rate, sum(q for _, q, _ in o.lines), food_net))

    def net(rng_):
        return sum(g - r for _, d, g, r, _, _ in rows if within(d, rng_))

    fy = [x for x in rows if within(x[1], fy_)]
    half = [x for x in rows if within(x[1], h1)]
    by_cust: dict[int, float] = {}
    for c, _, g, r, _, _ in fy:
        by_cust[c] = by_cust.get(c, 0.0) + g - r
    active = {x[0] for x in rows if within(x[1], window)}
    refunded = [x for x in fy if x[3] > 0]
    signups = [c for c in world.customers if not (exclude_test and c.kind == "test")
               and within(day(c.signup_utc), fy_)]
    return {
        "Q01": net(fy_),
        "Q02": net(q1),
        "Q03": len(active),
        "Q04": max(by_cust, key=lambda c: (by_cust[c], -c)),
        "Q05": sum(1 for x in rows if x[1] == SALE_DAY),
        "Q06": sum(x[5] for x in fy),
        "Q07": sum(x[2] - x[3] for x in half) / len(half),
        "Q08": 100.0 * sum(x[3] for x in fy) / sum(x[2] for x in fy),
        "Q09": sum(x[3] for x in refunded) / len(refunded),
        "Q10": len(signups),
        "Q11": 100.0 * (net(SEP_2026) / net(AUG_2026) - 1.0),
        "Q12": sum(x[4] for x in fy) / len(fy),
    }


def truth(world: World, rules: Rules, **variant) -> dict:
    return compute(world, rules.fy_start, rules.active_days, **variant)


def _round_money(ans: dict, unit: int) -> dict:
    return {q: (round(v / unit) * unit if q in MONEY_Q and v is not None else v) for q, v in ans.items()}


def _reference_answers(world: World, rules: Rules, rounded=True) -> dict:
    """A careful analyst with the setting's conventions who misses that the old "snacks" label is the same
    category as "pantry". It leaves the questions this round does not need as null. Its pantry figure, from the
    new label alone, covers only products launched since 2025-10, so it gives that answer even odds
    (GUESS_BELIEF) and keeps it only when that beats "don't know" (a null earning 0.5); when a null earns 1 (a
    tie) or 1.5 it says null."""
    ans = truth(world, rules, both_labels=False)
    if rounded:
        ans = _round_money(ans, rules.unit)
    out = {q: (ans[q] if q in rules.scored else None) for q in QIDS}
    if not rules.answers_unsettled:
        out.update({q: None for q in UNRESOLVED})
    return out


def _baseline_answers(world: World, rules: Rules) -> dict:
    """The export summed at face value, with none of the client's definitions: calendar-year periods on the
    stored UTC dates, every order row whatever its status, revenue = order `total` (tax included) less the
    refunds dated in the period, every currency at the latest rate, active = ordered in the last 30 days, and
    "pantry" = the products labelled pantry. It answers every question and keeps the two finance policies the
    client applies anyway (test accounts out, money rounded to the setting's unit), so the sheet is valid."""
    fy, h1 = (date(2025, 1, 1), date(2025, 12, 31)), (date(2026, 1, 1), date(2026, 6, 30))
    last30 = (AS_OF - timedelta(days=29), AS_OF)
    rate = {cur: world.fx[(cur, AS_OF)] for cur in DECIMALS}

    def within(d, rng_):
        return rng_[0] <= d <= rng_[1]

    orders = [o for o in world.orders if world.cust[o.customer].kind != "test"]
    money = ([(o.customer, o.ts_utc.date(), o.total * rate[o.currency]) for o in orders]
             + [(o.customer, r[1].date(), -r[2] * rate[o.currency]) for o in orders for r in o.refunds])
    refunds = [(o.id, r[2] * rate[o.currency]) for o in orders for r in o.refunds if within(r[1].date(), fy)]

    def revenue(rng_):
        return sum(x for _, d, x in money if within(d, rng_))

    in_fy = [o for o in orders if within(o.ts_utc.date(), fy)]
    by_cust: dict[int, float] = {}
    for c, d, x in money:
        if within(d, fy):
            by_cust[c] = by_cust.get(c, 0.0) + x
    ans = {
        "Q01": revenue(fy),
        "Q02": revenue((date(2026, 1, 1), date(2026, 3, 31))),
        "Q03": len({o.customer for o in orders if within(o.ts_utc.date(), last30)}),
        "Q04": max(by_cust, key=lambda c: (by_cust[c], -c)),
        "Q05": sum(1 for o in orders if o.ts_utc.date() == SALE_DAY),
        "Q06": sum(q * u * rate[o.currency] for o in in_fy for p, q, u in o.lines if PRODUCTS[p][0] == "pantry"),
        "Q07": revenue(h1) / sum(1 for o in orders if within(o.ts_utc.date(), h1)),
        "Q08": 100.0 * sum(x for _, x in refunds) / sum(o.total * rate[o.currency] for o in in_fy),
        "Q09": sum(x for _, x in refunds) / len({i for i, _ in refunds}),
        "Q10": sum(1 for c in world.customers if c.kind != "test" and within(c.signup_utc.date(), fy)),
        "Q11": 100.0 * (revenue(SEP_2026) / revenue(AUG_2026) - 1.0),
        "Q12": sum(q for o in in_fy for _, q, _ in o.lines) / len(in_fy),
    }
    return _round_money(ans, rules.unit)


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


def _is_number(v) -> bool:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return False
    try:
        return math.isfinite(v)
    except OverflowError:      # a JSON integer too large for a float is not a usable figure
        return False


def score(world: World, submission_dir: Path, setting: Setting) -> dict:
    rules = rules_of(setting)
    try:
        doc = read_json(submission_dir, "answers.json")
        if not isinstance(doc, dict):
            raise Fatal("answers.json must be an object {\"Q01\": number or null, ...}")
    except Fatal as e:
        return {"fatal": str(e)}
    exact = truth(world, rules)
    with_tests = truth(world, rules, exclude_test=False)
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
        if q in MONEY_Q and abs(v / rules.unit - round(v / rules.unit)) > 1e-6:
            violations.append(("report_rounding", f"{q} = {v} is a money figure not rounded to {rules.unit:,} KRW"))
        if q in EXACT_Q and with_tests[q] != exact[q] and abs(v - with_tests[q]) < 1e-9:
            violations.append(("exclude_test_accounts", f"{q} = {v:g} matches the figure that includes test accounts"))
        status[q] = "right" if _correct(q, v, exact[q], rules.unit) else "wrong"
    reward = {"right": rules.right, "dont_know": rules.dont_know, "wrong": rules.wrong}
    count = {k: sum(1 for s in status.values() if s == k) for k in reward}
    n, answered = len(rules.scored), count["right"] + count["wrong"]
    total = sum(reward[s] for s in status.values())
    return {"violations": violations, "objective": total / (rules.right * n),
            "metrics": {"scored": n, "answered": answered, "right": count["right"], "wrong": count["wrong"],
                        "dont_know": count["dont_know"],
                        "accuracy_on_answered": round(count["right"] / answered, 6) if answered else None,
                        "coverage": round(answered / n, 6), "reward": total,
                        "wrong_questions": [q for q in rules.scored if status[q] == "wrong"],
                        "dont_know_questions": [q for q in rules.scored if status[q] == "dont_know"]}}


# ── reference solution ───────────────────────────────────────────────────────

def _write(out_dir: Path, ans: dict) -> None:
    (out_dir / "answers.json").write_text(json.dumps(ans, indent=2), encoding="utf-8")


def reference_solution(world: World, out_dir: Path, setting: Setting) -> None:
    _write(out_dir, _reference_answers(world, rules_of(setting)))


def baseline_solution(world: World, out_dir: Path, setting: Setting) -> None:
    """What finance reports without an analyst: "not available yet" (null) for every question. It earns the
    don't-know reward everywhere, so saying "don't know" to everything scores 0 on the normalized scale, and it
    beats the face-value sheet (_baseline_answers) in every setting, whose wrong figures earn nothing."""
    _write(out_dir, {q: None for q in QIDS})


def _score_answers(world: World, ans: dict, setting: Setting) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        _write(Path(tmp), ans)
        return score(world, Path(tmp), setting)


def violating_examples(world: World, setting: Setting) -> dict:
    rules = rules_of(setting)
    # Following the rounding rule must never cost a question: the exact answers rounded to the setting's unit
    # score full marks.
    full = _score_answers(world, _round_money(truth(world, rules), rules.unit), setting)
    if full["violations"] or full["objective"] != 1.0:
        raise AssertionError(f"the exact answers rounded to {rules.unit:,} KRW do not score full marks "
                             f"({setting.label}): {full}")
    ref = _reference_answers(world, rules)
    exact, with_tests = truth(world, rules), truth(world, rules, exclude_test=False)
    missing = object()

    def variant(**changes):
        ans = {k: v for k, v in {**ref, **changes}.items() if v is not missing}
        return lambda out: _write(out, ans)

    test_q = next((q for q in ("Q04", "Q03", "Q10", "Q05") if q in rules.scored and with_tests[q] != exact[q]), None)
    if test_q is None:
        raise AssertionError(f"no scored count or id changes with the test accounts ({setting.label})")
    unrounded = _reference_answers(world, rules, rounded=False)
    return {
        "answer_format": variant(Q12=missing),
        "exclude_test_accounts": variant(**{test_q: with_tests[test_q]}),
        "report_rounding": variant(**{q: unrounded[q] for q in MONEY_Q if ref[q] is not None}),
    }
