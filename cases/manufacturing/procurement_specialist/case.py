"""Eight-week purchase-order planning for an electronics assembler (original FDE-Bench v2 case).

A contract manufacturer of two control-board models needs to know what to
order from which supplier over the next eight weeks. The request only says "so
production doesn't stop and we don't overspend"; what decides validity and
quality is in the requirements and must be asked for.

The data is the same in every setting: board plan, BOM with the engineering
change (C04 -> C25 from W6), stock, open orders, quotes (with currency, price
breaks and lead times in business days), approved-vendor list, budget, six
months of delivery history, the allocation notice and the supplier price e-mail
(C01 from S03 +20% for orders from W4, in every tier). A setting decides which
rules and cost terms apply and with which parameters:

  tiers
    easy    the MRP core: demand exploded from the board plan and the BOM, lead
            times as whole weeks (days / 5 rounded up), list prices, MOQ per
            order line, the approved-vendor list, a hard monthly budget cap,
            resistor stock in reels, safety stock for critical parts, a supplier
            on quality hold, the dual-sourcing habit (a bendable business
            policy), and the cost model (purchases + holding + backlog +
            safety-stock shortfall). The engineering change, the price breaks,
            the holiday calendar, the delivery history and the allocation are
            out of scope this round.
    medium  + all-units price breaks per order line and lead times in business
            days with two short holiday weeks
    hard    + supply uncertainty: each supplier delivers one or two weeks late
            with a hidden probability (the history is a sample), monthly
            allocation caps on three constrained parts, and the engineering
            change (C04 left at the end of W5 is scrapped). Quality is the exact
            expected cost over the true lateness distribution, computed by
            enumeration (no sampling)
  rule parameters (case.yaml `params`, each drawn by the rule seed from its pool)
    usd_krw         planning rate for the USD quotes of Pacific Parts (S04); fixed at 1,380 in hard
    safety_weeks    safety stock of critical parts, in average weeks of demand
    max_share       dual sourcing: most any one supplier may get of a critical part; fixed at 80% in hard
    quality_hold    which supplier is on quality hold and up to which week its lots are rejected, "S07-W3"
                    (hard: longer holds, and the main semiconductor maker S03 instead of S07)
  derived: hold_supplier (its name in each locale) and hold_until (the week), for the texts

The budget in the data is calibrated over the candidate pools (`_calibrate`). Whatever a rule seed draws, the
reference and the baseline stay valid: a month they cannot bring under its cap by moving orders in time is
brought under it by moving orders late, pulling them forward or cutting order lines (accepting shortfall or
backlog), see `_defer`.
"""

from __future__ import annotations

import datetime as dt
import itertools
import math
import random
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from fdebench2.cases import TIERS, Setting, param_pools
from fdebench2.casekit import Fatal, labels, number, read_csv, write_csv, write_xlsx

# ── world ────────────────────────────────────────────────────────────────────

N_WEEKS = 10                                     # weeks simulated (the production plan)
N_ORDER_WEEKS = 8                                # orders are placed in W1..W8
W1 = dt.date(2026, 11, 23)                       # Monday of W1
WEEK_START = [W1 + dt.timedelta(days=7 * i) for i in range(N_WEEKS)]
BUSINESS_DAYS = [5, 5, 5, 5, 4, 4, 5, 5, 5, 5]   # medium/hard: W5 has 25 Dec, W6 has 1 Jan
QUOTE_FX = 1380.0                                # rate at which S04's USD quotes were drawn (not a rule parameter)
REEL = 5000                                      # SMD resistors are counted in reels of 5000 in the inventory file
HOLDING_RATE = 0.005                             # per unit per week, of the standard cost
BACKLOG_FACTOR = 5.0                             # per unit short per week (boards waiting for the part), x std cost
SAFETY_FACTOR = 1.5                              # per unit-week below safety stock (critical parts), x std cost
MONTHS = ["2026-11", "2026-12", "2027-01"]
ECO_OLD, ECO_NEW, ECO_WEEK = "C04", "C25", 6     # boards built from W6 use C25 instead of C04 (applies in hard)
ALLOC_PAIRS = [("C01", "S03"), ("C03", "S03"), ("C06", "S08")]   # parts on allocation (applies in hard)
ALLOC_SHARE = 0.6                                # allocation = 60% of the unconstrained reference's peak month
MAX_LATE = 2                                     # deliveries are at most two weeks late
SLT_THRESHOLD = 0.05                             # reference: plan one week of safety lead time above this

_META = yaml.safe_load((Path(__file__).with_name("case.yaml")).read_text(encoding="utf-8"))
PARAM_POOLS = param_pools(_META, TIERS)          # {parameter: {tier: candidates}}: what the budget is calibrated on
# The allocation is calibrated on one plan: the first version's rule set A.
CALIBRATION = {"usd_krw": 1380, "safety_weeks": 1, "max_share": 80, "quality_hold": "S07-W3"}
NOV_SHARE = 0.95                                 # November's cap: this share of the least unconstrained spend there
HEADROOM = 1.05                                  # December and January: headroom over the most any combination spends


def month_of_week(w: int) -> str:
    """Budget month of an order placed in week w (1-based): the month of that week's Monday."""
    return WEEK_START[w - 1].strftime("%Y-%m")


@dataclass
class Component:
    id: str
    key: str
    category: str
    critical: bool
    std_cost: float
    reel: bool                    # inventory counted in reels
    on_hand: int                  # units (truth)
    demand: list[int] = field(default_factory=lambda: [0] * N_WEEKS)   # per week, in the setting's BOM
    first: int = 1                # first week the part is used
    last: int = N_WEEKS           # last week the part is used (0: not used at all)
    safety: int = 0               # safety stock (units), at the end of every week in use

    @property
    def in_use(self) -> bool:
        return self.last >= self.first

    @property
    def phased_out(self) -> bool:
        return self.in_use and self.last < N_WEEKS

    def target(self, w: int) -> int:
        return self.safety if self.first <= w <= self.last else 0


@dataclass
class Quote:
    component: str
    supplier: str
    currency: str
    price: float                  # list price in quote currency
    moq: int
    breaks: list[tuple[int, float]]   # (min qty, unit price) ascending
    lead: int                     # business days

    @property
    def lead_weeks(self) -> int:
        return math.ceil(self.lead / 5)


@dataclass
class World:
    """Everything every setting needs; the agent-visible data is rendered from it alone."""

    components: list[Component]   # stock and master data (demand is filled in by the setting's view)
    quotes: dict                  # (component, supplier) -> Quote
    avl: dict                     # (component, supplier) -> "approved" | "pending" | "suspended"
    open_orders: list[dict]       # {po, component, supplier, qty, arrival}
    boards: dict                  # product -> boards per week
    bom: list[tuple]              # (product, component, qty per board, first week, last week), with the change
    late: dict                    # supplier -> (P(1 week late), P(2 weeks late)), hidden
    history: list                 # past deliveries (agent-visible)
    est_late: dict                # the reference's estimates from the history
    budget: dict = field(default_factory=dict)    # month -> KRW cap
    alloc: dict = field(default_factory=dict)     # (component, supplier) -> max qty ordered per month


class _View:
    """The world as one setting sees it: which tier's rules apply and the rule seed's parameters."""

    def __init__(self, world: World, setting: Setting):
        self._w, self.setting = world, setting
        self.tier = setting.tier
        self.medium, self.hard = setting.at_least("medium"), setting.at_least("hard")
        self.fx = float(setting["usd_krw"])
        self.safety_weeks = float(setting["safety_weeks"])
        self.max_share = float(setting["max_share"]) / 100.0
        self.hold_supplier, self.hold_until = _hold(setting["quality_hold"])
        self.alloc = world.alloc if self.hard else {}
        self.late = world.late if self.hard else None
        self.est_late = world.est_late if self.hard else None
        self.components = self._parts()
        self._by_id = {c.id: c for c in self.components}

    def __getattr__(self, name):
        return getattr(self._w, name)

    def _parts(self) -> list[Component]:
        """Demand per part under this setting's BOM: the engineering change applies only in hard."""
        out = []
        for c in self._w.components:
            rows = []
            for p, cid, qty, f, la in self._w.bom:
                if cid != c.id:
                    continue
                if not self.hard:
                    if cid == ECO_NEW:
                        continue
                    f, la = (1, N_WEEKS) if cid == ECO_OLD else (f, la)
                rows.append((p, qty, f, la))
            demand = [0] * N_WEEKS
            for p, qty, f, la in rows:
                for w in range(f - 1, la):
                    demand[w] += self._w.boards[p][w] * qty
            first = min((f for _, _, f, _ in rows), default=1)
            last = max((la for _, _, _, la in rows), default=0)
            k = Component(c.id, c.key, c.category, c.critical, c.std_cost, c.reel, c.on_hand, demand, first, last)
            if k.critical and k.in_use and not k.phased_out:
                k.safety = math.ceil(self.safety_weeks * sum(demand) / (last - first + 1) - 1e-9)
            out.append(k)
        return out

    def cap(self, month: str) -> float:
        """What the plan may spend in a month (budget.csv)."""
        return self._w.budget[month]

    def comp(self, cid: str) -> Component | None:
        return self._by_id.get(cid)

    def suppliers_of(self, cid: str) -> list[str]:
        return sorted(s for (c, s) in self._w.quotes if c == cid)

    def approved(self, cid: str, sid: str) -> bool:
        return self._w.avl.get((cid, sid)) == "approved"

    def breaks(self, q: Quote) -> list[tuple[int, float]]:
        return q.breaks if self.medium else []      # easy plans at list prices

    def unit_krw(self, q: Quote, qty: float, week: int = 1) -> float:
        p = q.price
        for b, bp in self.breaks(q):
            if qty >= b:
                p = bp
        return p * (1.20 if (q.component, q.supplier) == ("C01", "S03") and week >= 4 else 1.0) * (self.fx if q.currency == "USD" else 1.0)

    def line_cost(self, cid: str, sid: str, qty: float, week: int = 1) -> float:
        return qty * self.unit_krw(self._w.quotes[(cid, sid)], qty, week)

    def arrival(self, order_week: int, q: Quote) -> int:
        """Promised arrival week: the first week whose Monday comes after delivery. Easy: lead in whole weeks
        (days / 5 rounded up). Medium/hard: the business days from the order week's Monday up to the end of week
        k-1 cover the lead."""
        if not self.medium:
            return order_week + q.lead_weeks
        k, acc = order_week, 0
        while True:
            acc += BUSINESS_DAYS[k - 1] if 1 <= k <= N_WEEKS else 5
            k += 1
            if acc >= q.lead:
                return k

    def on_hold(self, sid: str, arrival: int) -> bool:
        return sid == self.hold_supplier and arrival <= self.hold_until

    def dual_parts(self) -> list[Component]:
        """Critical parts the dual-sourcing policy applies to (unused or phased-out parts are exempt)."""
        return [k for k in self.components if k.critical and k.in_use and not k.phased_out]


SUPPLIERS = {
    "S01": ("Hanbit Electronics", "KR"), "S02": ("Daeyang Components", "KR"), "S03": ("Mirae Semicon", "KR"),
    "S04": ("Pacific Parts Inc.", "US"), "S05": ("Seoul PCB Tech", "KR"), "S06": ("Jinwoo Plastics", "KR"),
    "S07": ("Kowon Passive", "KR"), "S08": ("Nara Display", "KR"), "S09": ("Express Parts Korea", "KR"),
}
SUPPLIER_KO = {
    "S01": "한빛전자", "S02": "대양부품", "S03": "미래반도체", "S04": "Pacific Parts Inc.", "S05": "서울PCB테크",
    "S06": "진우플라스틱", "S07": "고원패시브", "S08": "나라디스플레이", "S09": "익스프레스파츠코리아",
}

PRODUCTS = ["B100", "B200"]                      # basic board; board with display
# id, key, category, critical, standard cost KRW, qty per B100, qty per B200, reel
CATALOG = [
    ("C01", "mcu", "ic", True, 4200, 1, 1, False),
    ("C02", "pmic", "ic", True, 1850, 1, 1, False),
    ("C03", "dram", "ic", True, 3300, 1, 2, False),
    ("C04", "flash", "ic", True, 1400, 1, 1, False),
    ("C05", "pcb", "pcb", True, 2600, 1, 1, False),
    ("C06", "display", "display", True, 14800, 0, 1, False),
    ("C07", "r10k", "resistor", False, 3.0, 20, 26, True),
    ("C08", "r4k7", "resistor", False, 3.0, 14, 18, True),
    ("C09", "r100", "resistor", False, 4.0, 6, 10, True),
    ("C10", "c100n", "capacitor", False, 6.0, 26, 32, False),
    ("C11", "c10u", "capacitor", False, 18.0, 8, 12, False),
    ("C12", "c47u", "capacitor", False, 55.0, 4, 4, False),
    ("C13", "elcap", "capacitor", False, 95.0, 2, 2, False),
    ("C14", "inductor", "inductor", False, 140.0, 3, 3, False),
    ("C15", "crystal", "ic", False, 230.0, 1, 1, False),
    ("C16", "usbc", "connector", False, 420.0, 1, 1, False),
    ("C17", "b2b", "connector", False, 380.0, 1, 3, False),
    ("C18", "led", "led", False, 22.0, 4, 4, False),
    ("C19", "tsensor", "ic", False, 650.0, 1, 1, False),
    ("C20", "antenna", "connector", False, 310.0, 0, 1, False),
    ("C21", "coin", "mechanical", False, 120.0, 1, 1, False),
    ("C22", "enc_top", "mechanical", False, 900.0, 1, 1, False),
    ("C23", "enc_bot", "mechanical", False, 780.0, 1, 1, False),
    ("C24", "screw", "mechanical", False, 9.0, 4, 4, False),
]
# hard: the successor of C04 (same function, new die revision), used from W6
ECO_PART = ("C25", "flash_b", "ic", True, 1500, 1, 1, False)
ECO_TEMPLATE = [("S03", 1.00, 12, 1.0, "approved"), ("S01", 1.12, 7, 0.8, "approved"),
                ("S09", 1.28, 3, 0.05, "approved")]
BOARDS = [2400, 2550, 2650, 2700, 1900, 1650, 2750, 2850, 2800, 2900]   # boards built per week (holiday weeks lower)

# Quote templates per category: (supplier, price factor vs std cost, lead business days, moq in weeks of demand,
# AVL status). Price factors and leads get a little noise.
TEMPLATES = {
    "ic": [("S03", 1.00, 12, 1.6, "approved"), ("S01", 1.14, 7, 1.4, "approved"),
           ("S04", None, 20, 2.0, "approved"), ("S09", 1.27, 3, 0.05, "approved")],
    "pcb": [("S05", 1.00, 12, 1.6, "approved"), ("S01", 1.15, 8, 1.6, "approved"), ("S09", 1.30, 4, 0.1, "approved")],
    "display": [("S08", 1.00, 12, 1.5, "approved"), ("S04", 0.97, 22, 1.5, "approved"),
                ("S09", 1.24, 4, 0.1, "approved")],
    "resistor": [("S02", 1.00, 7, 2.5, "approved"), ("S07", 0.82, 5, 2.0, None), ("S01", 1.10, 5, 1.0, "approved"),
                 ("S09", 1.35, 3, 0.1, "approved")],
    "capacitor": [("S02", 1.00, 7, 2.0, "approved"), ("S07", 0.84, 5, 2.0, None), ("S01", 1.09, 5, 1.0, "approved"),
                  ("S09", 1.33, 3, 0.1, "approved")],
    "inductor": [("S02", 1.00, 8, 1.6, "approved"), ("S07", 0.86, 6, 1.6, "approved"),
                 ("S09", 1.30, 3, 0.1, "approved")],
    "led": [("S02", 1.00, 7, 2.0, "approved"), ("S07", 0.80, 5, 1.2, "pending"), ("S09", 1.35, 3, 0.1, "approved")],
    "connector": [("S01", 1.00, 8, 1.5, "approved"), ("S03", 0.95, 18, 1.5, "approved"),
                  ("S07", 0.83, 6, 1.0, "suspended"), ("S09", 1.28, 3, 0.1, "approved")],
    "mechanical": [("S06", 1.00, 12, 2.0, "approved"), ("S07", 0.85, 7, 1.5, "approved"),
                   ("S09", 1.32, 4, 0.1, "approved")],
}
# S04 price factor vs std cost for the parts it quotes: cheaper for some, dearer for others.
S04_FACTOR = {"C01": 0.88, "C02": 1.08, "C03": 0.89, "C04": 1.10, "C06": 1.12, "C15": 1.12, "C19": 0.94}
# S07 AVL status where the template leaves it open
S07_STATUS = {"C07": "approved", "C08": "pending", "C09": "approved", "C10": "approved", "C11": "pending",
              "C12": "approved", "C13": "suspended"}
# Weeks of demand initially on hand (critical parts get enough to bridge their main supplier's lead time)
COVER = {"C01": 5.3, "C02": 4.2, "C03": 5.3, "C04": 4.3, "C05": 4.2, "C06": 4.3, "C07": 1.6, "C08": 2.2,
         "C09": 1.4, "C10": 1.8, "C11": 2.1, "C12": 1.5, "C13": 2.4, "C14": 1.9, "C15": 2.2, "C16": 1.7,
         "C17": 2.3, "C18": 2.6, "C19": 2.0, "C20": 1.6, "C21": 3.1, "C22": 2.2, "C23": 1.9, "C24": 2.8}
# hard: typical lateness per supplier, P(1 week late), P(2 weeks late); each world draws around these
LATE_BASE = {"S01": (0.07, 0.02), "S02": (0.10, 0.02), "S03": (0.26, 0.10), "S04": (0.22, 0.12),
             "S05": (0.10, 0.03), "S06": (0.16, 0.05), "S07": (0.18, 0.06), "S08": (0.12, 0.04),
             "S09": (0.03, 0.0)}



def _round_qty(q: float) -> int:
    step = 5000 if q >= 50000 else 1000 if q >= 5000 else 100
    return int(max(step, round(q / step) * step))


def _round_price(p: float, currency: str) -> float:
    if currency == "USD":
        return round(p, 4)
    return round(p, 2) if p < 10 else round(p, 1) if p < 100 else float(round(p))


def _ceil_cap(x: float) -> float:
    return float(math.ceil(x / 5e6) * 5e6)


def _quote_cores(rng: random.Random, cid: str, cost: float, cat_rows, avg: float) -> list[tuple]:
    out = []
    for sid, factor, lead, moq_w, status in cat_rows:
        if sid == "S04" and cid not in S04_FACTOR:
            continue
        if sid == "S04":
            factor = S04_FACTOR[cid]
        if status is None:
            status = S07_STATUS[cid]
        krw = cost * factor * rng.uniform(0.985, 1.015)
        lead_d = max(2, lead + rng.choice([-1, 0, 0, 1]))
        moq = _round_qty(avg * moq_w * rng.uniform(0.9, 1.1))
        out.append((cid, sid, krw, lead_d, moq, status))
    return out


def _make_quote(core: tuple, avg: float, rb: random.Random) -> Quote:
    cid, sid, krw, lead_d, moq, _ = core
    currency = "USD" if sid == "S04" else "KRW"
    base = krw / QUOTE_FX if currency == "USD" else krw
    breaks = []
    if sid != "S09":
        b1 = _round_qty(max(moq * 2, avg * 2.2))
        b2 = _round_qty(max(b1 * 2, avg * 4.5))
        d1, d2 = rb.uniform(0.035, 0.05), rb.uniform(0.07, 0.095)
        breaks = [(b1, _round_price(base * (1 - d1), currency)), (b2, _round_price(base * (1 - d2), currency))]
    return Quote(cid, sid, currency, _round_price(base, currency), moq, breaks, lead_d)


def build_world(seed: int) -> World:
    """One world for every setting; the budget is calibrated over the candidate pools of every tier (`_calibrate`)."""
    rng = random.Random(seed)
    b200 = [int(round(b * rng.uniform(0.55, 0.65))) for b in BOARDS]
    boards = {"B100": [b - x for b, x in zip(BOARDS, b200)], "B200": b200}
    catalog = CATALOG + [ECO_PART]
    bom = []
    for cid, _, _, _, _, q1, q2, _ in catalog:
        first, last = (ECO_WEEK, N_WEEKS) if cid == ECO_NEW else (1, ECO_WEEK - 1) if cid == ECO_OLD \
            else (1, N_WEEKS)
        for p, qty in zip(PRODUCTS, (q1, q2)):
            if qty:
                bom.append((p, cid, qty, first, last))

    comps: list[Component] = []
    for cid, key, cat, crit, cost, q1, q2, reel in catalog:
        full = [boards["B100"][w] * q1 + boards["B200"][w] * q2 for w in range(N_WEEKS)]  # before the change
        on_hand = int(sum(full) / N_WEEKS * COVER.get(cid, 0.0))
        if reel:
            on_hand = int(round(on_hand / REEL)) * REEL
        comps.append(Component(cid, key, cat, crit, float(cost), reel, on_hand))

    def full_avg(q1, q2):
        return sum(boards["B100"][w] * q1 + boards["B200"][w] * q2 for w in range(N_WEEKS)) / N_WEEKS

    # Core quote facts (base price, lead, MOQ, AVL status) from the core stream, for the 24 standard parts.
    cores = []
    for cid, _, cat, _, cost, q1, q2, _ in CATALOG:
        avg = full_avg(q1, q2)
        cores += [(c, avg) for c in _quote_cores(rng, cid, cost, TEMPLATES[cat], avg)]

    open_orders = []
    po = 4501
    for cid, _, cat, _, _, q1, q2, _ in CATALOG:
        if cid in ("C02", "C07", "C09", "C12", "C16", "C20", "C23"):
            sup = next(core[1] for core, _ in cores if core[0] == cid and core[5] == "approved")
            open_orders.append({"po": f"PO-{po}", "component": cid, "supplier": sup,
                                "qty": _round_qty(full_avg(q1, q2) * 1.1), "arrival": 2 if po % 2 else 1})
            po += 1

    rm = random.Random(seed * 7 + 1)     # price breaks
    rh = random.Random(seed * 7 + 2)     # the new flash's quotes, lateness and history
    eco_avg = sum(boards[p][w] * qty for p, cid, qty, f, la in bom if cid == ECO_NEW
                  for w in range(f - 1, la)) / (N_WEEKS - ECO_WEEK + 1)
    cores += [(c, eco_avg) for c in _quote_cores(rh, ECO_NEW, ECO_PART[4], ECO_TEMPLATE, eco_avg)]
    quotes, avl = {}, {}
    for core, avg in cores:
        quotes[(core[0], core[1])] = _make_quote(core, avg, rm if core[0] != ECO_NEW else rh)
        avl[(core[0], core[1])] = core[5]
    # The connector maker S03 is still in qualification for the antenna.
    avl[("C20", "S03")] = "pending"

    late, history, est_late = {}, [], {}
    for sid, (b1, b2) in sorted(LATE_BASE.items()):
        late[sid] = (round(b1 * rh.uniform(0.7, 1.3), 3), round(b2 * rh.uniform(0.7, 1.3), 3))
    rows = []
    for sid in sorted(SUPPLIERS):
        parts = sorted({c for (c, s) in quotes if s == sid and c != ECO_NEW})
        p1, p2 = late[sid]
        n = rh.randint(10, 28)
        k1 = k2 = 0
        for _ in range(n):
            promised = W1 - dt.timedelta(days=7 * rh.randint(1, 26))
            u = rh.random()
            d = 2 if u < p2 else 1 if u < p1 + p2 else 0
            off = -rh.randint(0, 4) if d == 0 else rh.randint(1, 7) if d == 1 else rh.randint(8, 14)
            rows.append((promised, sid, rh.choice(parts), promised + dt.timedelta(days=off)))
            k1 += d == 1
            k2 += d == 2
        # The reference's estimate: smoothed frequencies (what an agent can see), not the true rates.
        est_late[sid] = ((k1 + 1) / (n + 4), (k2 + 0.5) / (n + 4))
    for po, (promised, sid, cid, received) in enumerate(sorted(rows), start=3101):
        history.append({"po": f"PO-{po}", "supplier": sid, "component": cid, "promised": promised,
                        "received": received})

    world = World(comps, quotes, avl, open_orders, boards, bom, late, history, est_late)
    _calibrate(world)
    return world


# How the supplier on quality hold reads in each locale's text (the derived `hold_supplier`).
HOLD_NAMES = {
    "S01": {"zh": "Hanbit Electronics（S01）", "en": "Hanbit Electronics (S01)", "ko": "한빛전자(S01)",
            "ja": "Hanbit Electronics（S01）", "es": "Hanbit Electronics (S01)"},
    "S03": {"zh": "Mirae Semicon（S03）", "en": "Mirae Semicon (S03)", "ko": "미래반도체(S03)",
            "ja": "Mirae Semicon（S03）", "es": "Mirae Semicon (S03)"},
    "S05": {"zh": "Seoul PCB Tech（S05）", "en": "Seoul PCB Tech (S05)", "ko": "서울PCB테크(S05)",
            "ja": "Seoul PCB Tech（S05）", "es": "Seoul PCB Tech (S05)"},
    "S07": {"zh": "Kowon Passive（S07）", "en": "Kowon Passive (S07)", "ko": "고원패시브(S07)",
            "ja": "Kowon Passive（S07）", "es": "Kowon Passive (S07)"},
}


def _hold(value: str) -> tuple[str, int]:
    """A quality_hold candidate, "S07-W3": the supplier and the last week whose arrivals are rejected."""
    sid, week = str(value).split("-W")
    return sid, int(week)


def derive_params(params: dict, tier: str) -> dict:
    """The supplier on hold (worded per locale) and the hold's last week, for the texts."""
    sid, until = _hold(params["quality_hold"])
    return {"hold_supplier": dict(HOLD_NAMES[sid]), "hold_until": until}


def _earliest_arrival(sid: str) -> int:
    """The first week goods of `sid` can arrive in any world and tier: an order in W1 with its shortest lead time
    (the templates' lead less the one day of noise), in whole weeks or in business days alike."""
    rows = [r for rows in TEMPLATES.values() for r in rows] + ECO_TEMPLATE
    return 1 + math.ceil(max(2, min(lead for s, _, lead, *_ in rows if s == sid) - 1) / 5)


def admissible(params: dict, tier: str) -> bool:
    """A quality hold reaches a week in which the supplier's goods could arrive at all: Seoul PCB Tech (S05) and
    Mirae Semicon (S03) quote 11-13 business days, so nothing of theirs arrives before W4, and a hold up to W3
    would change nothing. (The pools hold only such holds; this guards edits to them.)"""
    sid, until = _hold(params["quality_hold"])
    return until >= _earliest_arrival(sid)


def _combinations(tier: str) -> list[dict]:
    """Every admissible parameter combination a rule seed can draw in `tier`, with the derived values."""
    pools = {n: list(dict.fromkeys(by_tier[tier])) for n, by_tier in PARAM_POOLS.items()}
    out = []
    for combo in itertools.product(*pools.values()):
        drawn = dict(zip(pools, combo))
        full = {**drawn, **derive_params(drawn, tier)}
        if admissible(full, tier):
            out.append(full)
    return out


def _calibrate(world: World) -> None:
    """Allocation and budget, written into the data, so that they bind in the settings that use them.

    Allocation (hard only): 60% of the peak month the unconstrained hard plan of the calibration parameters would
    order from that supplier. The budget is calibrated over every combination of the candidate pools in every
    tier (a private rule seed may draw any of them), on the unconstrained plans: November's cap is NOV_SHARE of
    the least any combination spends there, so that it binds whatever is drawn; December's has HEADROOM over the
    most any combination spends there plus what it spends in November above that cap, and January's HEADROOM
    over the most any combination spends there, so that those two bind only where deferrals pile up. Whatever
    the reference cannot defer in time it defers late, pulls forward or cuts (`_defer`), so every combination
    stays feasible."""
    nov, dec, jan = MONTHS
    world.budget = {m: math.inf for m in MONTHS}
    calibration = {**CALIBRATION, **derive_params(CALIBRATION, "hard")}
    loose = _solve(_View(world, Setting("hard", 0, calibration)), budget=False, trim=False)
    for cid, sid in ALLOC_PAIRS:
        per = {m: 0 for m in MONTHS}
        for ln in loose:
            if (ln["component"], ln["supplier"]) == (cid, sid):
                per[month_of_week(ln["week"])] += ln["qty"]
        moq = world.quotes[(cid, sid)].moq
        world.alloc[(cid, sid)] = max(int(ALLOC_SHARE * max(per.values()) // 500 * 500),
                                      int(math.ceil(1.5 * moq / 500) * 500))
    spends = []
    for tier in TIERS:
        for params in _combinations(tier):
            v = _View(world, Setting(tier, 0, params))
            spends.append(_spend(v, _solve(v, budget=False, trim=False)))
    world.budget[nov] = float(math.floor(NOV_SHARE * min(s[nov] for s in spends) / 5e6) * 5e6)
    world.budget[dec] = _ceil_cap(HEADROOM * max(s[dec] + max(0.0, s[nov] - world.budget[nov]) for s in spends))
    world.budget[jan] = _ceil_cap(HEADROOM * max(s[jan] for s in spends))


# ── data rendering ───────────────────────────────────────────────────────────

FILES = {
    "components": {"zh": "物料主数据.csv", "en": "components.csv", "ko": "부품마스터.csv", "ja": "部品マスタ.csv",
                   "es": "componentes.csv"},
    "plan": {"zh": "生产计划.csv", "en": "production_plan.csv", "ko": "생산계획.csv", "ja": "生産計画.csv",
             "es": "plan_produccion.csv"},
    "bom": {"zh": "物料清单.csv", "en": "bom.csv", "ko": "자재명세서.csv", "ja": "部品表.csv",
            "es": "lista_materiales.csv"},
    "inventory": {"zh": "当前库存.csv", "en": "inventory.csv", "ko": "현재고.csv", "ja": "現在庫.csv",
                  "es": "inventario.csv"},
    "open": {"zh": "在途采购单.csv", "en": "open_orders.csv", "ko": "미입고발주.csv", "ja": "未入荷発注.csv",
             "es": "pedidos_abiertos.csv"},
    "quotes": {"zh": "供应商报价.xlsx", "en": "supplier_quotes.xlsx", "ko": "공급사견적.xlsx", "ja": "仕入先見積.xlsx",
               "es": "cotizaciones_proveedores.xlsx"},
    "avl": {"zh": "合格供应商名录.csv", "en": "approved_vendors.csv", "ko": "승인업체목록.csv", "ja": "承認仕入先リスト.csv",
            "es": "proveedores_homologados.csv"},
    "budget": {"zh": "采购预算.csv", "en": "budget.csv", "ko": "구매예산.csv", "ja": "購買予算.csv",
               "es": "presupuesto.csv"},
    "history": {"zh": "交货记录.csv", "en": "delivery_history.csv", "ko": "납품이력.csv", "ja": "納入実績.csv",
                "es": "historial_entregas.csv"},
    "alloc": {"zh": "供应商配额.csv", "en": "allocations.csv", "ko": "공급배정.csv", "ja": "供給割当.csv",
              "es": "asignaciones.csv"},
}
SHEETS = {
    "quotes": {"zh": "报价", "en": "quotes", "ko": "견적", "ja": "見積", "es": "cotizaciones"},
    "suppliers": {"zh": "供应商", "en": "suppliers", "ko": "공급사", "ja": "仕入先", "es": "proveedores"},
}
COLS = {
    "component": {"zh": "物料编码", "en": "component_id", "ko": "부품코드", "ja": "部品コード", "es": "id_componente"},
    "desc": {"zh": "物料描述", "en": "description", "ko": "품명", "ja": "品名", "es": "descripcion"},
    "category": {"zh": "物料类别", "en": "category", "ko": "분류", "ja": "分類", "es": "categoria"},
    "critical": {"zh": "关键物料", "en": "critical", "ko": "핵심부품", "ja": "重要部品", "es": "critico"},
    "std_cost": {"zh": "标准成本_韩元", "en": "standard_cost_krw", "ko": "표준원가_원", "ja": "標準原価_ウォン",
                 "es": "costo_estandar_krw"},
    "week": {"zh": "周次", "en": "week", "ko": "주차", "ja": "週", "es": "semana"},
    "week_start": {"zh": "周一日期", "en": "week_start", "ko": "주시작일", "ja": "週開始日", "es": "inicio_semana"},
    "product": {"zh": "产品编码", "en": "product_id", "ko": "제품코드", "ja": "製品コード", "es": "id_producto"},
    "boards": {"zh": "计划产量_块", "en": "boards", "ko": "생산수량_장", "ja": "生産枚数", "es": "placas"},
    "qty_per": {"zh": "单板用量", "en": "qty_per_board", "ko": "보드당소요량", "ja": "基板当たり員数",
                "es": "cantidad_por_placa"},
    "valid_from": {"zh": "生效周次", "en": "valid_from_week", "ko": "적용시작주차", "ja": "適用開始週",
                   "es": "semana_desde"},
    "valid_to": {"zh": "失效周次", "en": "valid_to_week", "ko": "적용종료주차", "ja": "適用終了週",
                 "es": "semana_hasta"},
    "location": {"zh": "库位", "en": "location", "ko": "보관위치", "ja": "保管場所", "es": "ubicacion"},
    "on_hand": {"zh": "在库数", "en": "on_hand", "ko": "재고수량", "ja": "在庫数", "es": "existencias"},
    "count_date": {"zh": "盘点日期", "en": "count_date", "ko": "실사일", "ja": "棚卸日", "es": "fecha_recuento"},
    "po": {"zh": "采购单号", "en": "po_number", "ko": "발주번호", "ja": "発注番号", "es": "num_pedido"},
    "supplier": {"zh": "供应商编码", "en": "supplier_id", "ko": "공급사코드", "ja": "仕入先コード", "es": "id_proveedor"},
    "qty": {"zh": "数量", "en": "quantity", "ko": "수량", "ja": "数量", "es": "cantidad"},
    "arrival": {"zh": "到货周次", "en": "arrival_week", "ko": "입고주차", "ja": "入荷週", "es": "semana_llegada"},
    "currency": {"zh": "币种", "en": "currency", "ko": "통화", "ja": "通貨", "es": "moneda"},
    "price": {"zh": "单价", "en": "unit_price", "ko": "단가", "ja": "単価", "es": "precio_unitario"},
    "price_krw": {"zh": "单价_韩元", "en": "unit_price_krw", "ko": "단가_원", "ja": "単価_ウォン",
                  "es": "precio_unitario_krw"},
    "moq": {"zh": "最小起订量", "en": "moq", "ko": "최소주문수량", "ja": "最小発注数量", "es": "pedido_minimo"},
    "b1q": {"zh": "阶梯1数量", "en": "break1_qty", "ko": "구간1수량", "ja": "数量割引1_数量", "es": "tramo1_cantidad"},
    "b1p": {"zh": "阶梯1单价", "en": "break1_price", "ko": "구간1단가", "ja": "数量割引1_単価", "es": "tramo1_precio"},
    "b2q": {"zh": "阶梯2数量", "en": "break2_qty", "ko": "구간2수량", "ja": "数量割引2_数量", "es": "tramo2_cantidad"},
    "b2p": {"zh": "阶梯2单价", "en": "break2_price", "ko": "구간2단가", "ja": "数量割引2_単価", "es": "tramo2_precio"},
    "lead": {"zh": "交期_天", "en": "lead_time_days", "ko": "리드타임_일", "ja": "リードタイム_日", "es": "plazo_entrega_dias"},
    "lead_weeks": {"zh": "交期_周", "en": "lead_time_weeks", "ko": "리드타임_주", "ja": "リードタイム_週",
                   "es": "plazo_entrega_semanas"},
    "valid": {"zh": "报价有效期", "en": "valid_until", "ko": "견적유효기한", "ja": "見積有効期限", "es": "valida_hasta"},
    "sname": {"zh": "供应商名称", "en": "supplier_name", "ko": "공급사명", "ja": "仕入先名", "es": "nombre_proveedor"},
    "country": {"zh": "国家", "en": "country", "ko": "국가", "ja": "国", "es": "pais"},
    "status": {"zh": "认证状态", "en": "status", "ko": "승인상태", "ja": "承認状況", "es": "estado"},
    "month": {"zh": "月份", "en": "month", "ko": "월", "ja": "月", "es": "mes"},
    "budget": {"zh": "采购预算_韩元", "en": "purchase_budget_krw", "ko": "구매예산_원", "ja": "購買予算_ウォン",
               "es": "presupuesto_compras_krw"},
    "promised": {"zh": "承诺到货日", "en": "promised_date", "ko": "납기약속일", "ja": "納期回答日",
                 "es": "fecha_prometida"},
    "received": {"zh": "实际到货日", "en": "received_date", "ko": "실입고일", "ja": "実入荷日", "es": "fecha_recepcion"},
    "alloc": {"zh": "每月配额上限", "en": "max_qty_per_month", "ko": "월배정한도", "ja": "月間割当上限",
              "es": "maximo_mensual"},
}
VALUES = {
    "yes": {"zh": "是", "en": "yes", "ko": "예", "ja": "はい", "es": "sí"},
    "no": {"zh": "否", "en": "no", "ko": "아니오", "ja": "いいえ", "es": "no"},
    "approved": {"zh": "已认证", "en": "approved", "ko": "승인", "ja": "承認済", "es": "homologado"},
    "pending": {"zh": "认证中", "en": "pending", "ko": "심사중", "ja": "審査中", "es": "en evaluación"},
    "suspended": {"zh": "暂停", "en": "suspended", "ko": "거래정지", "ja": "取引停止", "es": "suspendido"},
    "KR": {"zh": "韩国", "en": "Korea", "ko": "한국", "ja": "韓国", "es": "Corea"},
    "US": {"zh": "美国", "en": "USA", "ko": "미국", "ja": "米国", "es": "EE. UU."},
}
CATEGORIES = {
    "ic": {"zh": "集成电路", "en": "IC", "ko": "IC", "ja": "IC", "es": "circuito integrado"},
    "pcb": {"zh": "印制电路板", "en": "PCB", "ko": "PCB", "ja": "プリント基板", "es": "placa de circuito"},
    "display": {"zh": "显示屏", "en": "display", "ko": "디스플레이", "ja": "ディスプレイ", "es": "pantalla"},
    "resistor": {"zh": "贴片电阻", "en": "SMD resistor", "ko": "칩저항", "ja": "チップ抵抗", "es": "resistencia SMD"},
    "capacitor": {"zh": "电容", "en": "capacitor", "ko": "커패시터", "ja": "コンデンサ", "es": "condensador"},
    "inductor": {"zh": "电感", "en": "inductor", "ko": "인덕터", "ja": "インダクタ", "es": "inductor"},
    "led": {"zh": "发光二极管", "en": "LED", "ko": "LED", "ja": "LED", "es": "LED"},
    "connector": {"zh": "连接器/天线", "en": "connector/antenna", "ko": "커넥터/안테나", "ja": "コネクタ/アンテナ",
                  "es": "conector/antena"},
    "mechanical": {"zh": "结构件", "en": "mechanical", "ko": "기구물", "ja": "機構部品", "es": "mecánico"},
}
DESCS = {
    "mcu": {"zh": "32位微控制器 QFN48", "en": "32-bit microcontroller QFN48", "ko": "32비트 MCU QFN48",
            "ja": "32ビットマイコン QFN48", "es": "microcontrolador de 32 bits QFN48"},
    "pmic": {"zh": "电源管理芯片", "en": "power management IC", "ko": "전원관리 IC", "ja": "電源管理IC",
             "es": "circuito de gestión de energía"},
    "dram": {"zh": "DRAM 4Gb", "en": "DRAM 4Gb", "ko": "DRAM 4Gb", "ja": "DRAM 4Gb", "es": "DRAM 4Gb"},
    "flash": {"zh": "NOR闪存 128Mb", "en": "NOR flash 128Mb", "ko": "NOR 플래시 128Mb", "ja": "NORフラッシュ 128Mb",
              "es": "memoria flash NOR 128Mb"},
    "flash_b": {"zh": "NOR闪存 128Mb（新版晶圆 B版）", "en": "NOR flash 128Mb, new die (rev. B)",
                "ko": "NOR 플래시 128Mb 신규 다이(B판)", "ja": "NORフラッシュ 128Mb 新ダイ（B版）",
                "es": "memoria flash NOR 128Mb, nuevo chip (rev. B)"},
    "pcb": {"zh": "六层裸板", "en": "bare PCB 6-layer", "ko": "6층 베어보드", "ja": "6層生基板",
            "es": "placa desnuda de 6 capas"},
    "display": {"zh": "3.5寸TFT显示模组", "en": "3.5-inch TFT display module", "ko": "3.5인치 TFT 디스플레이 모듈",
                "ja": "3.5インチTFT表示モジュール", "es": "módulo de pantalla TFT de 3,5 pulgadas"},
    "r10k": {"zh": "贴片电阻 0402 10kΩ", "en": "chip resistor 0402 10kΩ", "ko": "칩저항 0402 10kΩ",
             "ja": "チップ抵抗 0402 10kΩ", "es": "resistencia 0402 10kΩ"},
    "r4k7": {"zh": "贴片电阻 0402 4.7kΩ", "en": "chip resistor 0402 4.7kΩ", "ko": "칩저항 0402 4.7kΩ",
             "ja": "チップ抵抗 0402 4.7kΩ", "es": "resistencia 0402 4,7kΩ"},
    "r100": {"zh": "贴片电阻 0603 100Ω", "en": "chip resistor 0603 100Ω", "ko": "칩저항 0603 100Ω",
             "ja": "チップ抵抗 0603 100Ω", "es": "resistencia 0603 100Ω"},
    "c100n": {"zh": "贴片电容 0402 100nF", "en": "MLCC 0402 100nF", "ko": "적층세라믹 0402 100nF",
              "ja": "積層セラミック 0402 100nF", "es": "condensador cerámico 0402 100nF"},
    "c10u": {"zh": "贴片电容 0603 10µF", "en": "MLCC 0603 10µF", "ko": "적층세라믹 0603 10µF",
             "ja": "積層セラミック 0603 10µF", "es": "condensador cerámico 0603 10µF"},
    "c47u": {"zh": "贴片电容 1206 47µF", "en": "MLCC 1206 47µF", "ko": "적층세라믹 1206 47µF",
             "ja": "積層セラミック 1206 47µF", "es": "condensador cerámico 1206 47µF"},
    "elcap": {"zh": "电解电容 220µF", "en": "electrolytic capacitor 220µF", "ko": "전해커패시터 220µF",
              "ja": "電解コンデンサ 220µF", "es": "condensador electrolítico 220µF"},
    "inductor": {"zh": "功率电感 4.7µH", "en": "power inductor 4.7µH", "ko": "파워인덕터 4.7µH",
                 "ja": "パワーインダクタ 4.7µH", "es": "inductor de potencia 4,7µH"},
    "crystal": {"zh": "晶振 16MHz", "en": "crystal 16MHz", "ko": "크리스탈 16MHz", "ja": "水晶振動子 16MHz",
                "es": "cristal 16MHz"},
    "usbc": {"zh": "USB-C 插座", "en": "USB-C receptacle", "ko": "USB-C 리셉터클", "ja": "USB-C レセプタクル",
             "es": "conector USB-C"},
    "b2b": {"zh": "板对板连接器 40P", "en": "board-to-board connector 40P", "ko": "보드투보드 커넥터 40P",
            "ja": "基板対基板コネクタ 40P", "es": "conector placa a placa 40P"},
    "led": {"zh": "贴片LED 0603 绿色", "en": "LED 0603 green", "ko": "LED 0603 녹색", "ja": "LED 0603 緑",
            "es": "LED 0603 verde"},
    "tsensor": {"zh": "温度传感器芯片", "en": "temperature sensor IC", "ko": "온도센서 IC", "ja": "温度センサIC",
                "es": "sensor de temperatura"},
    "antenna": {"zh": "FPC天线", "en": "FPC antenna", "ko": "FPC 안테나", "ja": "FPCアンテナ", "es": "antena FPC"},
    "coin": {"zh": "纽扣电池座", "en": "coin cell holder", "ko": "코인전지 홀더", "ja": "コイン電池ホルダ",
             "es": "portapilas de botón"},
    "enc_top": {"zh": "外壳上盖", "en": "enclosure top", "ko": "케이스 상판", "ja": "筐体上カバー",
                "es": "carcasa superior"},
    "enc_bot": {"zh": "外壳下盖", "en": "enclosure bottom", "ko": "케이스 하판", "ja": "筐体下カバー",
                "es": "carcasa inferior"},
    "screw": {"zh": "M2 螺丝", "en": "M2 screw", "ko": "M2 나사", "ja": "M2 ねじ", "es": "tornillo M2"},
}
LOCATIONS = {"zh": "{n}号货架", "en": "Rack {n}", "ko": "{n}번 랙", "ja": "{n}番ラック", "es": "Estante {n}"}


def write_data(world: World, data_dir: Path, lang: str) -> None:
    c, v = labels(COLS, lang), labels(VALUES, lang)
    email = {
        "en": "Approved: for component C01 from supplier S03, all quoted unit prices increase by 20% for orders placed from W4 onward. Earlier orders retain their original prices. The proposed additional 5% increase is pending and must not be applied.",
        "ko": "승인됨: 공급사 S03의 부품 C01은 W4부터 발주하는 모든 견적 단가가 20% 인상됩니다. 이전 발주는 기존 단가를 유지합니다. 추가 5% 인상안은 승인 대기 중이므로 적용하지 마세요.",
        "ja": "承認済み: S03のC01はW4以降の発注について全見積単価を20%引き上げます。それ以前の発注は旧価格です。追加5%の値上げ案は承認待ちのため適用しません。",
        "zh": "已批准：供应商S03的C01自W4起下单的所有报价单价上调20%；此前订单保持原价。额外5%的提议尚待批准，不予应用。",
        "es": "Aprobado: todos los precios unitarios cotizados de C01 por S03 aumentan un 20% para pedidos desde W4. Los pedidos anteriores mantienen el precio original. El aumento adicional del 5% está pendiente y no se aplica.",
    }
    (data_dir / "supplier_price_email.txt").write_text(
        "From: purchasing@fictional.example\nDate: 2026-11-20\n"
        "Subject: C01 / S03 price revision\n\n" + email[lang] + "\n", encoding="utf-8")
    write_csv(data_dir / FILES["components"][lang],
              [c["component"], c["desc"], c["category"], c["critical"], c["std_cost"]],
              [[k.id, DESCS[k.key][lang], CATEGORIES[k.category][lang], v["yes" if k.critical else "no"],
                k.std_cost if k.std_cost < 10 else int(k.std_cost)] for k in world.components])
    write_csv(data_dir / FILES["plan"][lang], [c["week"], c["week_start"], c["product"], c["boards"]],
              [[f"W{w + 1}", WEEK_START[w].isoformat(), p, world.boards[p][w]]
               for w in range(N_WEEKS) for p in PRODUCTS])
    write_csv(data_dir / FILES["bom"][lang],
              [c["product"], c["component"], c["qty_per"], c["valid_from"], c["valid_to"]],
              [[p, cid, qty, f"W{f}", f"W{la}"] for p, cid, qty, f, la in world.bom])
    write_csv(data_dir / FILES["inventory"][lang], [c["component"], c["location"], c["on_hand"], c["count_date"]],
              [[k.id, LOCATIONS[lang].format(n=f"{(i // 4) + 1}-{(i % 4) + 1}"),
                k.on_hand // REEL if k.reel else k.on_hand, "2026-11-20"] for i, k in enumerate(world.components)])
    write_csv(data_dir / FILES["open"][lang], [c["po"], c["component"], c["supplier"], c["qty"], c["arrival"]],
              [[o["po"], o["component"], o["supplier"], o["qty"], f"W{o['arrival']}"] for o in world.open_orders])

    def blank(x):
        return "" if x is None else x
    qrows = []
    for (cid, sid), q in sorted(world.quotes.items()):
        b = q.breaks + [(None, None)] * (2 - len(q.breaks))
        qrows.append([cid, sid, q.currency, q.price, q.moq, blank(b[0][0]), blank(b[0][1]), blank(b[1][0]),
                      blank(b[1][1]), q.lead, "2027-01-31"])
    qhead = [c["component"], c["supplier"], c["currency"], c["price"], c["moq"], c["b1q"], c["b1p"], c["b2q"],
             c["b2p"], c["lead"], c["valid"]]
    srows = [[sid, SUPPLIER_KO[sid] if lang == "ko" else name, v[country]]
             for sid, (name, country) in SUPPLIERS.items()]
    write_xlsx(data_dir / FILES["quotes"][lang], {
        SHEETS["quotes"][lang]: (qhead, qrows),
        SHEETS["suppliers"][lang]: ([c["supplier"], c["sname"], c["country"]], srows),
    })
    write_csv(data_dir / FILES["avl"][lang], [c["component"], c["supplier"], c["status"]],
              [[cid, sid, v[st]] for (cid, sid), st in sorted(world.avl.items())])
    write_csv(data_dir / FILES["budget"][lang], [c["month"], c["budget"]],
              [[m, int(world.budget[m])] for m in MONTHS])
    write_csv(data_dir / FILES["history"][lang],
              [c["po"], c["supplier"], c["component"], c["promised"], c["received"]],
              [[h["po"], h["supplier"], h["component"], h["promised"].isoformat(), h["received"].isoformat()]
               for h in world.history])
    write_csv(data_dir / FILES["alloc"][lang], [c["supplier"], c["component"], c["alloc"]],
              [[sid, cid, world.alloc[(cid, sid)]] for cid, sid in ALLOC_PAIRS])


# ── simulation and scoring ───────────────────────────────────────────────────

def _parse_orders(world: _View, rows: list[dict]) -> list[dict]:
    """Merged order lines {week, component, supplier, qty}; same week/component/supplier rows are summed."""
    merged: dict = {}
    for i, r in enumerate(rows, start=2):
        wk = str(r.get("order_week", "")).strip().upper().lstrip("W")
        try:
            week = int(float(wk))
        except ValueError as e:
            raise Fatal(f"orders.csv line {i}: order_week must be 1..8 (or W1..W8), got {r.get('order_week')!r}") from e
        if not 1 <= week <= N_ORDER_WEEKS:
            raise Fatal(f"orders.csv line {i}: order_week {week} is outside W1..W8")
        cid = str(r.get("component_id", "")).strip()
        sid = str(r.get("supplier_id", "")).strip()
        if world.comp(cid) is None:
            raise Fatal(f"orders.csv line {i}: unknown component {cid!r}")
        if (cid, sid) not in world.quotes:
            raise Fatal(f"orders.csv line {i}: supplier {sid!r} has no quote for {cid}")
        qty = number(r.get("quantity"), f"orders.csv line {i} quantity")
        if qty < 0 or qty != int(qty):
            raise Fatal(f"orders.csv line {i}: quantity must be a whole number >= 0, got {r.get('quantity')!r}")
        if qty == 0:
            continue
        merged[(week, cid, sid)] = merged.get((week, cid, sid), 0) + int(qty)
    return [{"week": w, "component": c, "supplier": s, "qty": q} for (w, c, s), q in sorted(merged.items())]


def _spend(world: _View, lines: list[dict]) -> dict:
    spend = {m: 0.0 for m in MONTHS}
    for ln in lines:
        spend[month_of_week(ln["week"])] += world.line_cost(ln["component"], ln["supplier"], ln["qty"], ln["week"])
    return spend


def _late_dist(probs: dict | None, sid: str) -> list[float]:
    """P(a delivery is d weeks late), d = 0..MAX_LATE; always on time below the hard tier."""
    if probs is None:
        return [1.0, 0.0, 0.0]
    p1, p2 = probs[sid]
    return [1.0 - p1 - p2, p1, p2]


def _expected_costs(world: _View, k: Component, lots: dict, probs: dict | None) -> dict:
    """Exact expected holding, backlog, safety-shortfall and scrap cost of one part.

    lots: (supplier, promised arrival week) -> qty. Each such delivery is late by d weeks with the supplier's
    probability, independently of the other deliveries; the net position at the end of week w (stock minus
    boards waiting for the part) depends only on the deliveries promised for weeks w-MAX_LATE+1 .. w, whose
    joint outcomes are enumerated."""
    opened = [0] * (N_WEEKS + 2)
    for o in world.open_orders:
        if o["component"] == k.id:
            opened[o["arrival"]] += o["qty"]
    out = {"holding": 0.0, "backlog": 0.0, "safety": 0.0, "scrap": 0.0}
    cum_d = 0
    cum_open = 0
    dists = {s: _late_dist(probs, s) for s, _ in lots}
    for w in range(1, k.last + 1):
        cum_d += k.demand[w - 1]
        cum_open += opened[w]
        certain = k.on_hand + cum_open - cum_d
        unsure = []
        for (s, a), q in lots.items():
            if a > w:
                continue
            p = sum(dists[s][: w - a + 1])
            if p >= 1.0 - 1e-15:
                certain += q
            elif p > 0:
                unsure.append((q, p))
        states = {certain: 1.0}
        for q, p in unsure:
            nxt: dict = {}
            for n, pr in states.items():
                nxt[n + q] = nxt.get(n + q, 0.0) + pr * p
                nxt[n] = nxt.get(n, 0.0) + pr * (1.0 - p)
            states = nxt
        tgt = k.target(w)
        for n, pr in states.items():
            out["holding"] += pr * max(n, 0) * k.std_cost * HOLDING_RATE
            out["backlog"] += pr * max(-n, 0) * k.std_cost * BACKLOG_FACTOR
            if tgt:
                out["safety"] += pr * max(0, tgt - n) * k.std_cost * SAFETY_FACTOR
            if k.phased_out and w == k.last:
                out["scrap"] += pr * max(n, 0) * k.std_cost
    return out


def _lots_by_part(world: _View, lines: list[dict]) -> dict:
    """component -> {(supplier, promised arrival): qty}, without lots rejected under the quality hold."""
    lots: dict = {k.id: {} for k in world.components}
    for ln in lines:
        q = world.quotes[(ln["component"], ln["supplier"])]
        a = world.arrival(ln["week"], q)
        if world.on_hold(ln["supplier"], a) or a > N_WEEKS:
            continue
        key = (ln["supplier"], a)
        lots[ln["component"]][key] = lots[ln["component"]].get(key, 0) + ln["qty"]
    return lots


def simulate(world: _View, lines: list[dict]) -> tuple[list[tuple[str, str]], float, dict]:
    violations: list[tuple[str, str]] = []
    spend = _spend(world, lines)
    purchase = sum(spend.values())
    for ln in lines:
        q = world.quotes[(ln["component"], ln["supplier"])]
        tag = f"W{ln['week']} {ln['component']} from {ln['supplier']}"
        if not world.approved(ln["component"], ln["supplier"]):
            violations.append(("approved_vendor", f"{tag}: supplier is not approved for this part "
                                                  f"({world.avl.get((ln['component'], ln['supplier']), 'not listed')})"))
        if ln["qty"] < q.moq:
            violations.append(("moq", f"{tag}: {ln['qty']} is below the MOQ of {q.moq}"))
        arr = world.arrival(ln["week"], q)
        if world.on_hold(ln["supplier"], arr):
            violations.append(("quality_hold", f"{tag}: arrives in W{arr}, while {world.hold_supplier} is on "
                                               f"quality hold up to W{world.hold_until}"))
    for m in MONTHS:
        if spend[m] > world.cap(m) + 1e-6:
            violations.append(("budget_cap", f"{m}: purchases {spend[m]:,.0f} KRW exceed the cap {world.cap(m):,.0f}"))
    for (cid, sid), cap in sorted(world.alloc.items()):
        per = {m: 0 for m in MONTHS}
        for ln in lines:
            if (ln["component"], ln["supplier"]) == (cid, sid):
                per[month_of_week(ln["week"])] += ln["qty"]
        for m in MONTHS:
            if per[m] > cap:
                violations.append(("allocation_cap", f"{m}: {per[m]} of {cid} ordered from {sid}, above its "
                                                     f"allocation of {cap} per month"))
    for k in world.dual_parts():
        per = {}
        for ln in lines:
            if ln["component"] == k.id:
                per[ln["supplier"]] = per.get(ln["supplier"], 0) + ln["qty"]
        if len(per) < 2:
            violations.append(("dual_source_critical", f"{k.id} is ordered from {len(per)} supplier(s); critical "
                                                       f"parts need at least two"))
        elif max(per.values()) > world.max_share * sum(per.values()) + 1e-9:
            top = max(per, key=per.get)
            violations.append(("dual_source_critical", f"{k.id}: {top} has {per[top] / sum(per.values()):.0%} of the "
                                                       f"ordered quantity; at most {world.max_share:.0%} from one "
                                                       f"supplier"))
    lots = _lots_by_part(world, lines)
    tot = {"holding": 0.0, "backlog": 0.0, "safety": 0.0, "scrap": 0.0}
    short = {}
    for k in world.components:
        c = _expected_costs(world, k, lots[k.id], world.late)
        for key in tot:
            tot[key] += c[key]
        if c["backlog"] > 1e-9:
            short[k.id] = round(c["backlog"] / (k.std_cost * BACKLOG_FACTOR), 1)
    objective = purchase + sum(tot.values())
    metrics = {"purchase_krw": round(purchase), "holding_krw": round(tot["holding"]),
               "backlog_krw": round(tot["backlog"]), "safety_shortfall_krw": round(tot["safety"]),
               "scrap_krw": round(tot["scrap"]), "backlog_unit_weeks": short,
               "spend_by_month": {m: round(s) for m, s in spend.items()}, "order_lines": len(lines)}
    return violations, objective, metrics


def score(world: World, submission_dir: Path, setting: Setting) -> dict:
    view = _View(world, setting)
    try:
        rows = read_csv(submission_dir, "orders.csv", ["order_week", "component_id", "supplier_id", "quantity"])
        lines = _parse_orders(view, rows)
        violations, objective, metrics = simulate(view, lines)
    except Fatal as e:
        return {"fatal": str(e)}
    return {"violations": violations, "objective": objective, "metrics": metrics}


# ── reference solution ───────────────────────────────────────────────────────
# Time-phased MRP per part: net the stock and open orders against the exploded demand, and order from the
# cheapest supplier that still arrives in time, as late as possible, covering two weeks (or one) and rounding up to a
# price break when that costs less in total. Critical parts then move whole lines to a second source until the share
# rule holds, and leftover stock is trimmed (`_trim`). A month over budget defers whole lines to the first week of
# the next month with a supplier that still arrives in time (usually a faster, dearer one), cheapest extra cost per
# KRW deferred first, each re-sized to what the part still needs from its new arrival; failing that it moves a line
# late, pulls January's excess into December or cuts a line (`_defer`). The reference keeps the cheapest valid plan
# of fifteen variants: with and without the second-source step, two- or one-week lots, and the client's lot-for-lot
# planner with its quota split (`_mrp_component`), each with the trim before and after the budget step, only after
# it, or not at all (`_reference`).
# Hard tier: one week of safety lead time for suppliers whose smoothed late rate in the history is above 5%,
# allocation respected.

def _parr(world: _View, cid: str, sid: str, week: int) -> int:
    """Planned arrival: promised, plus one week of safety lead time for unreliable suppliers (hard)."""
    a = world.arrival(week, world.quotes[(cid, sid)])
    if world.est_late is not None and sum(world.est_late[sid]) > SLT_THRESHOLD:
        a += 1
    return a


def _alloc_used(lines: list[dict], sid: str, month: str) -> int:
    return sum(ln["qty"] for ln in lines if ln["supplier"] == sid and month_of_week(ln["week"]) == month)


def _ok(world: _View, k: Component, sid: str, week: int, lines: list[dict], qty: int = 0) -> bool:
    q = world.quotes[(k.id, sid)]
    if not world.approved(k.id, sid) or world.on_hold(sid, world.arrival(week, q)) or _parr(world, k.id, sid, week) > k.last:
        return False
    cap = world.alloc.get((k.id, sid))
    return cap is None or cap - _alloc_used(lines, sid, month_of_week(week)) >= max(q.moq, qty)


def _plan_component(world: _View, k: Component, cover: int = 2) -> list[dict]:
    rec = [0] * (N_WEEKS + 4)
    for o in world.open_orders:
        if o["component"] == k.id:
            rec[o["arrival"]] += o["qty"]
    lines: list[dict] = []
    sups = world.suppliers_of(k.id)

    def price(s):
        q = world.quotes[(k.id, s)]
        return world.unit_krw(q, q.moq, w)

    for w in range(1, N_ORDER_WEEKS + 1):
        cands = [s for s in sups if _ok(world, k, s, w, lines)]
        while cands:
            arr = {s: _parr(world, k.id, s, w) for s in cands}
            net, acc, cd = [0.0], k.on_hand, 0
            for j in range(1, k.last + 1):
                acc += rec[j]
                cd += k.demand[j - 1]
                net.append(acc - cd)
            first = min(arr.values())
            deficit = next((j for j in range(first, k.last + 1) if net[j] < k.target(j)), None)
            if deficit is None:
                break
            timely = [s for s in cands if arr[s] <= deficit]
            best = min(timely, key=price)
            if w < N_ORDER_WEEKS and _ok(world, k, best, w + 1, lines) and _parr(world, k.id, best, w + 1) <= deficit:
                break  # the same supplier can still be ordered next week: wait
            q = world.quotes[(k.id, best)]
            end = min(deficit + cover - 1, k.last)
            need = max(k.target(j) - net[j] for j in range(deficit, end + 1))
            qty = max(q.moq, int(math.ceil(max(need, 1) / 100.0)) * 100)
            for bq, _ in world.breaks(q):   # all-units discount: round up when the break costs less in total
                if qty < bq and world.line_cost(k.id, best, bq, w) < world.line_cost(k.id, best, qty, w):
                    qty = bq
            cap = world.alloc.get((k.id, best))
            if cap is not None:
                qty = min(qty, (cap - _alloc_used(lines, best, month_of_week(w))) // 100 * 100)
            lines.append({"week": w, "component": k.id, "supplier": best, "qty": qty})
            rec[arr[best]] += qty
            cands = [s for s in cands if _ok(world, k, s, w, lines)]
    return lines


def _dual_ok(world: _View, lines: list[dict]) -> bool:
    qty: dict = {}
    for ln in lines:
        qty[ln["supplier"]] = qty.get(ln["supplier"], 0) + ln["qty"]
    return len(qty) >= 2 and max(qty.values()) <= world.max_share * sum(qty.values()) + 1e-9


def _second_source(world: _View, k: Component, lines: list[dict]) -> list[dict]:
    """Move the latest orders of the main supplier of a critical part, one whole line at a time, to the cheapest
    other supplier that arrives no later, until the dual-sourcing rule holds."""
    lines = [dict(ln) for ln in lines]
    moved: set = set()
    while lines and not _dual_ok(world, lines):
        qty: dict = {}
        for ln in lines:
            qty[ln["supplier"]] = qty.get(ln["supplier"], 0) + ln["qty"]
        main = max(qty, key=qty.get)
        for i in range(len(lines) - 1, -1, -1):
            ln = lines[i]
            if ln["supplier"] != main or i in moved:
                continue
            a0 = _parr(world, k.id, main, ln["week"])
            rest = lines[:i] + lines[i + 1:]
            alts = [s for s in world.suppliers_of(k.id) if s != main
                    and _ok(world, k, s, ln["week"], rest, ln["qty"])
                    and _parr(world, k.id, s, ln["week"]) <= a0]
            if not alts:
                continue

            def cost(s):
                return world.line_cost(k.id, s, max(world.quotes[(k.id, s)].moq, ln["qty"]), ln["week"])
            s = min(alts, key=cost)
            lines[i] = {**ln, "supplier": s, "qty": max(world.quotes[(k.id, s)].moq, ln["qty"])}
            moved.add(i)
            break
        else:
            raise AssertionError(f"reference cannot second-source {k.id} ({world.setting.label})")
    return lines


def _plan_full(world: _View, k: Component, dual: bool = True, cover: int = 2) -> list[dict]:
    lines = _plan_component(world, k, cover)
    if dual and k in world.dual_parts():
        lines = _second_source(world, k, lines)
    return lines


def _merge(lines: list[dict]) -> list[dict]:
    merged: dict = {}
    for ln in lines:
        key = (ln["week"], ln["component"], ln["supplier"])
        merged[key] = merged.get(key, 0) + ln["qty"]
    return [{"week": w, "component": c, "supplier": s, "qty": q} for (w, c, s), q in sorted(merged.items())]


def _part_cost(world: _View, k: Component, lines: list[dict]) -> float:
    """The reference's own view of a part's cost (estimated lateness, never the hidden rates)."""
    lots = _lots_by_part(world, lines)[k.id]
    return sum(world.line_cost(k.id, ln["supplier"], ln["qty"], ln["week"]) for ln in lines) + \
        sum(_expected_costs(world, k, lots, world.est_late).values())


def _net(world: _View, k: Component, lines: list[dict]) -> list[float]:
    """The part's planned net position at the end of weeks 0..k.last: stock, open orders and `lines` at their
    planned arrival, less the demand so far."""
    rec = [0] * (N_WEEKS + 4)
    for o in world.open_orders:
        if o["component"] == k.id:
            rec[o["arrival"]] += o["qty"]
    for x in lines:
        a = _parr(world, k.id, x["supplier"], x["week"])
        if a <= k.last:
            rec[a] += x["qty"]
    net, acc, cd = [0.0], k.on_hand, 0
    for j in range(1, k.last + 1):
        acc += rec[j]
        cd += k.demand[j - 1]
        net.append(acc - cd)
    return net


def _trim(world: _View, k: Component, lines: list[dict]) -> list[dict]:
    """Leftover stock trimmed, latest arrival first. Each line may be cut by what the part holds above its target
    from the line's planned arrival to the part's last week (rounded down to hundreds, never below the MOQ; dropped
    when all of it is spare), or be replaced, in the same week, by a line from another supplier that arrives no
    later, sized to what the part still lacks (a small-MOQ supplier instead of a full MOQ). Whichever lowers the
    part's cost most by the reference's own view is kept, if it keeps dual sourcing."""
    lines = [dict(x) for x in lines if x["component"] == k.id]
    order = sorted(range(len(lines)), key=lambda i: (-_parr(world, k.id, lines[i]["supplier"], lines[i]["week"]),
                                                      -lines[i]["week"]))
    dual = k in world.dual_parts()
    for i in order:
        ln = lines[i]
        a = _parr(world, k.id, ln["supplier"], ln["week"])
        if not ln["qty"] or a > k.last:
            continue
        now = [x for x in lines if x["qty"]]
        rest = [x for j, x in enumerate(lines) if j != i and x["qty"]]
        net = _net(world, k, lines)
        slack = min(net[j] - k.target(j) for j in range(a, k.last + 1))
        moq = world.quotes[(k.id, ln["supplier"])].moq
        options = [{**ln, "qty": 0 if slack >= ln["qty"] else max(moq, ln["qty"] - int(max(slack, 0) // 100) * 100)}]
        for sid in world.suppliers_of(k.id):
            if sid != ln["supplier"] and _ok(world, k, sid, ln["week"], rest) \
                    and _parr(world, k.id, sid, ln["week"]) <= a:
                qty = _resize(world, k, rest, sid, ln["week"], ln["qty"])
                if _ok(world, k, sid, ln["week"], rest, qty):
                    options.append({**ln, "supplier": sid, "qty": qty})
        keep_dual = dual and _dual_ok(world, now)
        best, cost = None, _part_cost(world, k, now) - 1e-6
        for opt in options:
            if opt["supplier"] == ln["supplier"] and opt["qty"] >= ln["qty"]:
                continue
            cand = _merge(rest + ([opt] if opt["qty"] else []))
            if keep_dual and not _dual_ok(world, cand):
                continue
            c = _part_cost(world, k, cand)
            if c < cost:
                best, cost = opt, c
        if best is not None:
            lines[i] = best
    return _merge([x for x in lines if x["qty"]])


def _resize(world: _View, k: Component, rest: list[dict], sid: str, week: int, qty: int) -> int:
    """The quantity of a line of `qty` moved to `sid` in `week`: what the rest of the part's plan still lacks from
    the line's planned arrival on, rounded as the planner rounds (hundreds, the MOQ, a cheaper price break), and
    never more than the line it replaces."""
    net = _net(world, k, rest)
    q = world.quotes[(k.id, sid)]
    need = max(k.target(j) - net[j] for j in range(_parr(world, k.id, sid, week), k.last + 1))
    new = max(q.moq, int(math.ceil(max(need, 1) / 100.0)) * 100)
    for bq, _ in world.breaks(q):
        if new < bq and world.line_cost(k.id, sid, bq, week) < world.line_cost(k.id, sid, new, week):
            new = bq
    return min(new, max(q.moq, qty))


def _cut(world: _View, lines: list[dict], month: str, over: float, dual: set) -> tuple | None:
    """The cheapest way to spend less in `month` by ordering less: one line of the month dropped, cut to its MOQ,
    or trimmed (in hundreds) by about `over`, whichever adds the least to its part's cost per KRW saved (the
    shortfall or backlog it causes), keeping a critical part's dual sourcing. (ratio, part, part's new lines)."""
    best = None
    for ln in lines:
        if month_of_week(ln["week"]) != month:
            continue
        k = world.comp(ln["component"])
        part = [x for x in lines if x["component"] == k.id]
        rest = [x for x in part if x is not ln]
        q = world.quotes[(k.id, ln["supplier"])]
        old = world.line_cost(k.id, ln["supplier"], ln["qty"], ln["week"])
        trim = ln["qty"] - int(math.ceil(over / world.unit_krw(q, ln["qty"], ln["week"]) / 100.0)) * 100
        base = None
        for qty in sorted({0, q.moq, trim}):
            if qty != 0 and not q.moq <= qty < ln["qty"]:
                continue
            saved = old - (world.line_cost(k.id, ln["supplier"], qty, ln["week"]) if qty else 0.0)
            new = _merge(rest + ([{**ln, "qty": qty}] if qty else []))
            if saved <= 0 or (k.id in dual and not _dual_ok(world, new)):
                continue
            base = _part_cost(world, k, part) if base is None else base
            ratio = (_part_cost(world, k, new) - base) / saved
            if best is None or ratio < best[0]:
                best = (ratio, k.id, new)
    return best


def _moves(world: _View, lines: list[dict], month: str, target: int, late: bool, dual: set) -> tuple | None:
    """The cheapest line of `month` to move to week `target` (extra cost of its part per KRW moved), with any
    supplier that still arrives in time, or (late=True) with any supplier at all, accepting the gap until it
    arrives. A line moved into an earlier month must fit under that month's cap. (ratio, part, part's new lines)."""
    best = None
    earlier = month_of_week(target) if MONTHS.index(month_of_week(target)) < MONTHS.index(month) else None
    for ln in lines:
        if month_of_week(ln["week"]) != month:
            continue
        k = world.comp(ln["component"])
        part = [x for x in lines if x["component"] == k.id]
        rest = [x for x in part if x is not ln]
        a0 = _parr(world, k.id, ln["supplier"], ln["week"])
        base = _part_cost(world, k, part)
        saved = world.line_cost(k.id, ln["supplier"], ln["qty"], ln["week"])
        for sid in world.suppliers_of(k.id):
            if not _ok(world, k, sid, target, rest) or (not late and _parr(world, k.id, sid, target) > a0):
                continue
            qty = _resize(world, k, rest, sid, target, ln["qty"])
            if not _ok(world, k, sid, target, rest, qty):
                continue
            new = _merge(rest + [{"week": target, "component": k.id, "supplier": sid, "qty": qty}])
            if k.id in dual and not _dual_ok(world, new):
                continue
            if earlier and _spend(world, [x for x in lines if x["component"] != k.id] + new)[earlier] \
                    > world.cap(earlier) + 1e-6:
                continue
            ratio = (_part_cost(world, k, new) - base) / saved
            if best is None or ratio < best[0]:
                best = (ratio, k.id, new)
    return best


def _defer(world: _View, lines: list[dict], month: str, cap: float) -> list[dict]:
    """Bring `month`'s spend under `cap`, one line at a time: move a line to the first week of the next month with
    a supplier that still arrives in time; if none can, with any supplier (the part waits until it arrives). In
    the last month, move a line to the last week of the month before, where it still fits that month's cap and
    arrives in time. If no line can move, cut one (`_cut`). A moved line is re-sized to what the part still needs
    from its new arrival week (`_resize`)."""
    i = MONTHS.index(month)
    last = i == len(MONTHS) - 1
    weeks = [w for w in range(1, N_ORDER_WEEKS + 1) if month_of_week(w) == MONTHS[i - 1 if last else i + 1]]
    target = weeks[-1] if last else weeks[0]
    lines = _merge(lines)
    dual = {k.id for k in world.dual_parts()}
    while _spend(world, lines)[month] > cap + 1e-6:
        best = (_moves(world, lines, month, target, False, dual)
                or (None if last else _moves(world, lines, month, target, True, dual)))
        if best is None:
            best = _cut(world, lines, month, _spend(world, lines)[month] - cap, dual)
            if best is None:
                raise AssertionError(f"cannot meet the {month} budget ({world.setting.label})")
        lines = sorted([x for x in lines if x["component"] != best[1]] + best[2],
                       key=lambda ln: (ln["week"], ln["component"], ln["supplier"]))
    return lines


def _solve(world: _View, dual: bool = True, budget: bool = True, cover: int = 2, trim: bool | str = True,
           quota: bool = False) -> list[dict]:
    """One planner variant. quota: lot for lot, each order of a critical part split with a second source at the
    share cap (`_mrp_component`), instead of the netting planner with whole-line second sourcing. trim: True trims
    leftover stock before and after the budget step, "after" only after it, False never."""
    if quota:
        lines = _merge([ln for k in world.components for ln in _mrp_component(world, k)])
    else:
        lines = _merge([ln for k in world.components for ln in _plan_full(world, k, dual, cover)])
    if trim is True:
        lines = _merge([ln for k in world.components for ln in _trim(world, k, lines)])
    if budget:
        for m in MONTHS:
            if math.isfinite(world.cap(m)):
                lines = _defer(world, lines, m, world.cap(m))
    if trim == "after" or (trim and budget):
        lines = _merge([ln for k in world.components for ln in _trim(world, k, lines)])
    return sorted(lines, key=lambda ln: (ln["week"], ln["component"], ln["supplier"]))


def _reference(world: _View) -> list[dict]:
    """The cheapest valid plan by the reference's own cost view over fifteen planner variants: the netting planner
    with and without the second-source step (without it, budget deferrals to faster suppliers sometimes
    second-source the parts anyway), with lots covering two weeks or one (one-week lots leave less stock behind at
    the end of the horizon), and the lot-for-lot planner that splits every order of a critical part at the share
    cap (cheaper than whole-line second sourcing when the second source is dear); each with the leftover trim
    before and after the budget step, only after it (trimming first can leave the budget step only dearer
    deferrals), or not at all."""
    best = None
    trims = (True, "after", False)
    variants = [dict(dual=dual, cover=cover, trim=trim)
                for dual, cover, trim in itertools.product((True, False), (2, 1), trims)]
    variants += [dict(quota=True, trim=trim) for trim in trims]
    for kw in variants:
        try:
            lines = _solve(world, **kw)
        except AssertionError:          # a critical part it cannot second-source, or a budget it cannot meet
            continue
        if simulate(world, lines)[0]:
            continue
        cost = sum(_part_cost(world, k, [ln for ln in lines if ln["component"] == k.id]) for k in world.components)
        if best is None or cost < best[0]:
            best = (cost, lines)
    if best is None:
        raise AssertionError(f"reference plan is not valid ({world.setting.label})")
    return best[1]


def _write(lines: list[dict], out_dir: Path) -> None:
    write_csv(out_dir / "orders.csv", ["order_week", "component_id", "supplier_id", "quantity"],
              [[ln["week"], ln["component"], ln["supplier"], ln["qty"]] for ln in lines])


def reference_solution(world: World, out_dir: Path, setting: Setting) -> None:
    _write(_reference(_View(world, setting)), out_dir)


# ── baseline ─────────────────────────────────────────────────────────────────
# What the client does today without an engineer: the ERP's MRP run and the buyer's fixes. Every part is planned
# lot for lot (each order covers the first week short of stock or safety stock, at least the MOQ) from the cheapest
# approved supplier that still delivers in time, ordered as late as its lead time allows, at list prices and on
# the promised dates (no price breaks, no use of the delivery history). Critical parts follow a quota arrangement:
# every order is split with the cheapest other supplier so that neither gets more than the share cap (when the
# second supplier cannot deliver in time, the main one covers the whole need). A month over budget moves whole
# lines to the next month as the reference does; January's lines are pulled into the last week of December (and cut
# as the reference cuts when December has no room).

def _mrp_component(world: _View, k: Component) -> list[dict]:
    rec = [0] * (N_WEEKS + 4)
    for o in world.open_orders:
        if o["component"] == k.id:
            rec[o["arrival"]] += o["qty"]
    lines: list[dict] = []
    split, share = k in world.dual_parts(), world.max_share

    def price(s):
        q = world.quotes[(k.id, s)]
        return world.unit_krw(q, q.moq, w)

    def hundreds(x):
        return int(math.ceil(max(x, 1) / 100.0)) * 100

    for w in range(1, N_ORDER_WEEKS + 1):
        while True:
            cands = [s for s in world.suppliers_of(k.id) if _ok(world, k, s, w, lines)]
            if not cands:
                break
            arr = {s: _parr(world, k.id, s, w) for s in cands}
            net, acc, cd = [0.0], k.on_hand, 0
            for j in range(1, k.last + 1):
                acc += rec[j]
                cd += k.demand[j - 1]
                net.append(acc - cd)
            deficit = next((j for j in range(min(arr.values()), k.last + 1) if net[j] < k.target(j)), None)
            if deficit is None:
                break
            best = min((s for s in cands if arr[s] <= deficit), key=price)
            if w < N_ORDER_WEEKS and _ok(world, k, best, w + 1, lines) and _parr(world, k.id, best, w + 1) <= deficit:
                break  # the same supplier can still be ordered next week: wait
            need = k.target(deficit) - net[deficit]
            others = [s for s in cands if s != best]
            if split and others:
                second = min(others, key=lambda s: (arr[s] > deficit, price(s)))
                q1 = max(world.quotes[(k.id, best)].moq, hundreds(need * (share if arr[second] <= deficit else 1.0)))
                q2 = max(world.quotes[(k.id, second)].moq, hundreds(q1 * (1 - share) / share))
                new = [(best, max(q1, hundreds(q2 * (1 - share) / share))), (second, q2)]
            else:
                new = [(best, max(world.quotes[(k.id, best)].moq, hundreds(need)))]
            for s, qty in new:
                cap = world.alloc.get((k.id, s))
                if cap is not None:
                    qty = min(qty, (cap - _alloc_used(lines, s, month_of_week(w))) // 100 * 100)
                lines.append({"week": w, "component": k.id, "supplier": s, "qty": qty})
                rec[arr[s]] += qty
    return lines


def _pull(world: _View, lines: list[dict], month: str, cap: float) -> list[dict]:
    """Move whole lines of `month`, largest first, to the last week of the month before until its spend fits;
    when none fits there, cut lines as the reference does (`_defer` in the last month)."""
    target = max(w for w in range(1, N_ORDER_WEEKS + 1) if month_of_week(w) == MONTHS[MONTHS.index(month) - 1])
    lines = _merge(lines)
    while _spend(world, lines)[month] > cap + 1e-6:
        for ln in sorted((x for x in lines if month_of_week(x["week"]) == month),
                         key=lambda x: -world.line_cost(x["component"], x["supplier"], x["qty"], x["week"])):
            k = world.comp(ln["component"])
            rest = [x for x in lines if x is not ln]
            new = _merge(rest + [{**ln, "week": target}])
            if _ok(world, k, ln["supplier"], target, [x for x in rest if x["component"] == k.id], ln["qty"]) \
                    and _spend(world, new)[month_of_week(target)] <= world.cap(month_of_week(target)) + 1e-6:
                lines = new
                break
        else:
            return _defer(world, lines, month, cap)
    return lines


def _baseline(world: _View) -> list[dict]:
    lines = _merge([ln for k in world.components for ln in _mrp_component(world, k)])
    for m in MONTHS[:-1]:
        lines = _defer(world, lines, m, world.cap(m))
    lines = _pull(world, lines, MONTHS[-1], world.cap(MONTHS[-1]))
    if simulate(world, lines)[0]:
        raise AssertionError(f"baseline plan is not valid ({world.setting.label})")
    return lines


def baseline_solution(world: World, out_dir: Path, setting: Setting) -> None:
    view = _View(world, setting)
    view.est_late = None            # the ERP plans on the promised dates
    _write(_baseline(view), out_dir)


def violating_examples(world: World, setting: Setting) -> dict:
    """One deliverable per rule of the setting that breaks exactly that rule (for the validator)."""
    world = _View(world, setting)
    ref = _reference(world)

    def only(lines, rule):
        v, _, _ = simulate(world, lines)
        return {x[0] for x in v} == {rule}

    def first_ok(cands, rule):
        for lines in cands:
            if only(lines, rule):
                return lambda out, lines=lines: _write(lines, out)
        raise AssertionError(f"no clean example for {rule} ({setting.label})")

    def add(line):
        return sorted(ref + [line], key=lambda ln: (ln["week"], ln["component"], ln["supplier"]))

    def gen_av():   # an extra small order from a quoted but not approved supplier
        for (cid, sid), q in sorted(world.quotes.items()):
            if not world.approved(cid, sid):
                for w in range(4, 9):
                    yield add({"week": w, "component": cid, "supplier": sid, "qty": q.moq})

    def gen_mq():   # one reference line cut below its MOQ
        for i, ln in enumerate(ref):
            m = world.quotes[(ln["component"], ln["supplier"])].moq
            if m > 1:
                yield ref[:i] + [{**ln, "qty": m - 1}] + ref[i + 1:]

    def gen_bc():   # a large extra order from an approved supplier
        for m in MONTHS:
            weeks = [w for w in range(1, N_ORDER_WEEKS + 1) if month_of_week(w) == m]
            for (cid, sid), q in sorted(world.quotes.items()):
                if world.approved(cid, sid) and sid != world.hold_supplier and (cid, sid) not in world.alloc:
                    qty = int(math.ceil(world.cap(m) / world.unit_krw(q, 1e12) / 1000.0)) * 1000
                    yield add({"week": weeks[-1], "component": cid, "supplier": sid, "qty": qty})

    def gen_qh():   # an order from the supplier on hold that would arrive while the hold is on
        sid = world.hold_supplier
        order = lambda x: (x["week"], x["component"], x["supplier"])  # noqa: E731
        for i, ln in enumerate(ref):    # one of its own lines placed earlier (same quantity: the shares stay)
            q = world.quotes[(ln["component"], ln["supplier"])]
            if ln["supplier"] != sid:
                continue
            for w in range(1, ln["week"]):
                if not world.on_hold(sid, world.arrival(w, q)):
                    continue
                moved = ref[:i] + ref[i + 1:] + [{**ln, "week": w}]
                yield sorted(moved, key=order)
                for j, x in enumerate(moved[:-1]):  # the month it moves into is tight: swap a line into its week
                    if month_of_week(x["week"]) == month_of_week(w) and x["supplier"] != sid \
                            and (x["component"], x["supplier"]) not in world.alloc:
                        yield sorted(moved[:j] + moved[j + 1:-1] + [{**x, "week": ln["week"]}, moved[-1]], key=order)
        for i, ln in enumerate(ref):    # a reference line moved to that supplier (same month: same budget)
            q = world.quotes.get((ln["component"], sid))
            if q is None or not world.approved(ln["component"], sid) or (ln["component"], sid) in world.alloc:
                continue
            for w in range(1, N_ORDER_WEEKS + 1):
                if month_of_week(w) == month_of_week(ln["week"]) and world.on_hold(sid, world.arrival(w, q)):
                    yield sorted(ref[:i] + ref[i + 1:] + [{**ln, "week": w, "supplier": sid,
                                                           "qty": max(q.moq, ln["qty"])}],
                                 key=lambda x: (x["week"], x["component"], x["supplier"]))
        for (cid, sid), q in sorted(world.quotes.items()):
            if sid == world.hold_supplier and world.approved(cid, sid) and (cid, sid) not in world.alloc:
                for w in range(1, N_ORDER_WEEKS + 1):
                    if world.on_hold(sid, world.arrival(w, q)):
                        new = {"week": w, "component": cid, "supplier": sid, "qty": q.moq}
                        yield add(new)
                        # the month's budget is tight: make room by moving one other line to the next month
                        nxt = next((x for x in range(w, N_ORDER_WEEKS + 1) if month_of_week(x) != month_of_week(w)),
                                   None)
                        for j, ln in enumerate(ref):
                            if nxt and month_of_week(ln["week"]) == month_of_week(w) and ln["supplier"] != sid:
                                yield sorted(ref[:j] + ref[j + 1:] + [{**ln, "week": nxt}, new],
                                             key=lambda x: (x["week"], x["component"], x["supplier"]))

    def gen_ac():   # a constrained supplier's line raised just above its monthly allocation, or a new line
        for (cid, sid), cap in sorted(world.alloc.items()):
            part = [x for x in ref if x["component"] == cid]
            for i, ln in enumerate(ref):
                if (ln["component"], ln["supplier"]) == (cid, sid):
                    used = _alloc_used(part, sid, month_of_week(ln["week"]))
                    yield ref[:i] + [{**ln, "qty": ln["qty"] + cap - used + 100}] + ref[i + 1:]
            for w in range(N_ORDER_WEEKS, 0, -1):
                used = _alloc_used(part, sid, month_of_week(w))
                yield add({"week": w, "component": cid, "supplier": sid,
                           "qty": max(world.quotes[(cid, sid)].moq, cap - used + 100)})

    def gen_ds():   # the same planner without the second-source step, or a critical part left single-sourced
        yield _solve(world, dual=False)
        for k in world.dual_parts():
            qty: dict = {}
            for ln in ref:
                if ln["component"] == k.id:
                    qty[ln["supplier"]] = qty.get(ln["supplier"], 0) + ln["qty"]
            if qty:
                main = max(qty, key=qty.get)
                yield [ln for ln in ref if ln["component"] != k.id or ln["supplier"] == main]

    gens = {"approved_vendor": gen_av, "moq": gen_mq, "budget_cap": gen_bc, "quality_hold": gen_qh,
            "dual_source_critical": gen_ds}
    if world.hard:
        gens["allocation_cap"] = gen_ac
    return {rule: first_ok(g(), rule) for rule, g in gens.items()}
