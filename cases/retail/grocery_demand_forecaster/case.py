"""Grocery daily order plan from a demand forecast (original FDE-Bench v2 case).

A regional grocery chain asks for a 14-day daily forecast per store x item and "places its orders from these
numbers". What the numbers are used for is in the hidden requirements: the stores order exactly the number they are
given, a missed sale costs several times a leftover unit, and the rules the client has are rules on that order. So
the deliverable is scored as an order plan, by its expected cost under the world's own demand distribution, never
against one realized future (docs/DIRECTION.md, section 5: forecasting cases).

The case has settings (DESIGN.md, Settings): one world and the same data in every setting, three tiers and five rule
parameters a rule seed draws.
  easy    the base order with the one-off holiday on the drawn date: promotions are added by the category team,
          so demand is the demand without them; bread rolls (I07) are ordered by the bakery and not judged
  medium  easy plus the promotion plan (with the drawn flyer multiple)
  hard    medium plus bread rolls (their unit change) and a dated revision: on 30 October the drawn category's
          promotions were cancelled after promo_plan.csv was exported
Parameters (case.yaml params:): lost_sale_cost (what a missed sale costs, in leftover units), min_display (the
display minimum of core items, a rule on the order), holiday_date, promo_uplift (the flyer's multiple of the
historical promotion lift) and promo_cancelled (hard).

Scoring is exact and deterministic: per store, the expected units left over plus lost_sale_cost times the expected
units short, summed over its judged items and days and divided by its expected demand; then the mean over the
stores. The expectation is over the demand distribution the history was drawn from (lognormal day noise around the
cell's mean, Poisson counts), so the best plan is known: each cell's lost_sale_cost / (1 + lost_sale_cost) quantile.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import math
import random
from array import array
from dataclasses import dataclass, field
from email.utils import format_datetime
from pathlib import Path
from statistics import NormalDist, median

import yaml

from fdebench2.casekit import Fatal, labels, number, read_csv, write_csv, write_eml
from fdebench2.cases import TIERS, Setting, param_pools

# ── world ────────────────────────────────────────────────────────────────────

HIST_START = dt.date(2024, 11, 4)        # Monday; 104 weeks of history
HORIZON_START = dt.date(2026, 11, 2)     # Monday
HORIZON_DAYS = 14
UNIT_CHANGE = dt.date(2026, 6, 1)        # I07 recorded per piece before this date, per 6-pack from it
PACK = 6
CLOSED_STORE, CLOSED_WEEKDAY = "S4", 6   # S4 closes on Sundays
CORE_CATEGORIES = ("produce", "dairy")
UNIT_CHANGE_ITEM = "I07"                 # judged only in hard (easy, medium: the bakery orders it itself)
RETURN_RATE = 0.03                       # share of store x item x days with a customer return row
PROMO_STOCKOUT = 0.20                    # extra stockout probability on promotion days
SOLD_ON_STOCKOUT = (0.3, 0.85)           # share of the day's demand the till recorded on a stockout day
NOTE_STORE, NOTE_EXTRA = "S1", 0.20      # the store manager's note in mail/: "add 20% on top for my store"

STORES = {"S1": (1.30, 0.03), "S2": (1.00, 0.08), "S3": (0.85, 0.00), "S4": (0.60, 0.02), "S5": (1.10, -0.05)}
# item id: (category, base units/day at store scale 1, base stockout probability)
ITEMS = {
    "I01": ("produce", 80.0, 0.09), "I02": ("produce", 50.0, 0.20), "I03": ("produce", 2.6, 0.22),
    "I04": ("dairy", 90.0, 0.08), "I05": ("dairy", 36.0, 0.20), "I06": ("dairy", 3.0, 0.09),
    "I07": ("bakery", 25.0, 0.15), "I08": ("bakery", 20.0, 0.12), "I09": ("bakery", 45.0, 0.30),
    "I10": ("beverages", 60.0, 0.08), "I11": ("beverages", 24.0, 0.09), "I12": ("beverages", 15.0, 0.25),
}
SLOW_ITEMS = ("I03", "I06")              # the core items a display minimum can hold up (a few units a day)
WEEKDAY = {  # Monday .. Sunday
    "produce": (1.00, 0.90, 0.95, 1.00, 1.15, 1.35, 0.80),
    "dairy": (1.00, 0.95, 0.95, 1.00, 1.10, 1.30, 0.85),
    "bakery": (0.90, 0.85, 0.90, 0.95, 1.10, 1.45, 1.20),
    "beverages": (0.85, 0.85, 0.90, 0.95, 1.15, 1.40, 1.10),
}
SEASON = {"produce": (0.10, 200), "dairy": (0.05, 20), "bakery": (0.15, 355), "beverages": (0.30, 196)}  # amp, peak doy
PROMO_ELASTICITY = {"produce": 1.5, "dairy": 2.0, "bakery": 2.5, "beverages": 3.0}  # uplift = 1 + e * pct/100
HOLIDAY_EFFECT = {"produce": 1.35, "dairy": 1.20, "bakery": 1.80, "beverages": 1.55}
HOLIDAY_MOST = ("bakery", "beverages")   # the categories the client names: "more for bakery and beverages"
HIST_HOLIDAYS = [  # (date, holiday key); none falls in the horizon
    ("2024-12-25", "christmas"), ("2025-01-01", "new_year"), ("2025-04-18", "spring"), ("2025-05-01", "labour"),
    ("2025-08-15", "summer"), ("2025-10-12", "autumn"), ("2025-12-25", "christmas"), ("2026-01-01", "new_year"),
    ("2026-04-03", "spring"), ("2026-05-01", "labour"), ("2026-08-15", "summer"), ("2026-10-12", "autumn"),
]
NOISE = 0.07                             # sd of the day's lognormal noise around the cell's mean
_META = yaml.safe_load(Path(__file__).with_name("case.yaml").read_text(encoding="utf-8"))
POOLS = param_pools(_META, TIERS)        # {parameter: {tier: candidates}}
# the categories a hard setting can draw for the 30 October cancellation (case.yaml promo_cancelled)
CANCELLABLE = tuple(sorted({str(v) for pool in POOLS["promo_cancelled"].values() for v in pool} - {"none"}))
# every date a setting can draw for the one-off holiday (case.yaml holiday_date)
HOLIDAY_DATES = tuple(sorted({dt.date.fromisoformat(str(v)) for pool in POOLS["holiday_date"].values() for v in pool
                              if str(v) != "none"}))

# The store managers' habit, the client's own way (baseline_solution): for every item the average of what the store
# sold on that weekday in the last HABIT_WEEKS weeks (days it ran out left aside) plus a cushion, HABIT_PROMO more
# per point of discount on a promotion day (times the flyer's multiple), a public holiday ordered like a Saturday.
# The cushion is the managers' own answer to what a missed sale costs them, so it follows lost_sale_cost
# (derive_params: habit_cushion, in percent). Eight weeks and these cushions are the habit at its fairest: over the
# measured settings of the public world and world seeds 1 and 2, 10, 20 and 30% cost the habit at most 0.002 more
# than the flat cushion that costs it least at each ratio (of 0, 5, ..., 45%), and no other window or cushion lifts the
# habit by half the scale (shortcuts: habit_last_year, habit_more_cushion). With four weeks the average rested on
# two to four days, and a year's window alone scored up to 0.59.
HABIT_WEEKS = 8
HABIT_CUSHION = {5: 10, 12: 20, 30: 30}
HABIT_PROMO = 0.02
SHORTCUT_SPREAD = 0.15   # shortcuts(): the day-to-day spread a flat cushion assumes (cushion = z x 15%)


def derive_params(params: dict, tier: str) -> dict:
    return {"habit_cushion": HABIT_CUSHION[int(params["lost_sale_cost"])]}


@dataclass
class World:
    history: list[tuple] = field(default_factory=list)       # (date, store, item, units, promo_pct, stockout)
    holidays: list[tuple[str, str]] = field(default_factory=list)
    promo_plan: list[tuple] = field(default_factory=list)    # (store, item, start, end, pct) in the horizon
    cache: dict = field(default_factory=dict, repr=False, compare=False)   # demand laws, fitted models, plans

    @property
    def horizon(self) -> list[dt.date]:
        return [HORIZON_START + dt.timedelta(days=k) for k in range(HORIZON_DAYS)]


def is_closed(store: str, day: dt.date) -> bool:
    return store == CLOSED_STORE and day.weekday() == CLOSED_WEEKDAY


def _poisson(rng: random.Random, lam: float) -> int:
    if lam <= 0:
        return 0
    if lam >= 30:
        return max(0, round(rng.gauss(lam, math.sqrt(lam))))
    limit, k, p = math.exp(-lam), 0, rng.random()
    while p > limit:
        k += 1
        p *= rng.random()
    return k


def _mean(store: str, item: str, day: dt.date, promo: int, holiday: bool, uplift: float = 1.0) -> float:
    cat, base, _ = ITEMS[item]
    scale, trend = STORES[store]
    amp, peak = SEASON[cat]
    years = (day - HIST_START).days / 365.0
    m = base * scale * (1 + trend * years) * WEEKDAY[cat][day.weekday()]
    m *= 1 + amp * math.cos(2 * math.pi * (day.timetuple().tm_yday - peak) / 365.0)
    m *= 1 + uplift * PROMO_ELASTICITY[cat] * promo / 100.0     # a flyer (uplift > 1) multiplies the extra sales
    if holiday:
        m *= HOLIDAY_EFFECT[cat]
    return m


def build_world(seed: int) -> World:
    rng = random.Random(seed)
    w = World(holidays=list(HIST_HOLIDAYS))
    hol = {d for d, _ in HIST_HOLIDAYS}
    n_hist = (HORIZON_START - HIST_START).days
    # Past promotions: one-week blocks (Monday..Sunday) per store x item.
    promos: dict[tuple[str, str, int], int] = {}
    for s in STORES:
        for i in ITEMS:
            for week in range(n_hist // 7):
                if rng.random() < 0.07:
                    pct = rng.choice([10, 20, 30])
                    for k in range(7):
                        promos[(s, i, week * 7 + k)] = pct
    # Horizon promotion plan.
    pairs = [(s, i) for s in STORES for i in ITEMS]
    for s, i in rng.sample(pairs, 14):
        start = rng.randrange(0, HORIZON_DAYS - 3)
        end = min(HORIZON_DAYS - 1, start + rng.choice([3, 4, 6]))
        w.promo_plan.append((s, i, HORIZON_START + dt.timedelta(days=start), HORIZON_START + dt.timedelta(days=end),
                             rng.choice([10, 20, 30])))
    w.promo_plan.sort(key=lambda p: (p[2], p[0], p[1]))
    _cover_cancellable(w, seed)

    for t in range(n_hist):
        day = HIST_START + dt.timedelta(days=t)
        ds = day.isoformat()
        for s in STORES:
            if is_closed(s, day):
                continue
            for i in ITEMS:
                pct = promos.get((s, i, t), 0)
                mean = _mean(s, i, day, pct, ds in hol) * math.exp(rng.gauss(0, NOISE))
                pieces = i == "I07" and day < UNIT_CHANGE
                demand = _poisson(rng, mean * (PACK if pieces else 1))
                p_out = ITEMS[i][2] + (PROMO_STOCKOUT if pct else 0.0)
                stockout = demand > 0 and rng.random() < p_out
                units = int(demand * rng.uniform(*SOLD_ON_STOCKOUT)) if stockout else demand
                w.history.append((ds, s, i, units, pct, stockout))
                if rng.random() < RETURN_RATE:
                    w.history.append((ds, s, i, -rng.randint(1, PACK if pieces else 2), pct, False))
    # The horizon has no realized future: a plan is scored by its expected cost under the demand law below.
    return w


def _cover_cancellable(w: World, seed: int) -> None:
    """Every category the 30 October revision can cancel has a promotion in the plan, so that the cancellation a
    hard setting draws always removes something. A plan that lacks one gives up a promotion of its most promoted
    category (same store, dates and discount) to an item of the missing category. A separate random stream: plans
    that already cover every such category, the stored world's and world seeds 1-3 among them, stay as they are."""
    rng = random.Random(f"plan|{seed}")
    for cat in CANCELLABLE:
        if any(ITEMS[i][0] == cat for _, i, _, _, _ in w.promo_plan):
            continue
        counts: dict[str, int] = {}
        for _, i, _, _, _ in w.promo_plan:
            counts[ITEMS[i][0]] = counts.get(ITEMS[i][0], 0) + 1
        donor = max(sorted(counts), key=lambda c: counts[c])
        k = rng.choice([n for n, p in enumerate(w.promo_plan) if ITEMS[p[1]][0] == donor])
        s, _, start, end, pct = w.promo_plan[k]
        item = rng.choice([i for i in ITEMS if ITEMS[i][0] == cat])
        w.promo_plan[k] = (s, item, start, end, pct)
    w.promo_plan.sort(key=lambda p: (p[2], p[0], p[1]))


# ── the demand law: what a day's demand is, given the cell's mean ────────────

_NORMAL = NormalDist()


def _gauss_hermite(n: int) -> list[tuple[float, float]]:
    """(node, weight) pairs for the expectation of f(Z), Z standard normal (Gauss-Hermite, Newton on the
    orthonormal Hermite recurrence)."""
    xs, ws = [0.0] * n, [0.0] * n
    z = 0.0
    for i in range((n + 1) // 2):
        if i == 0:
            z = math.sqrt(2 * n + 1) - 1.85575 * (2 * n + 1) ** (-0.16667)
        elif i == 1:
            z -= 1.14 * n ** 0.426 / z
        elif i == 2:
            z = 1.86 * z - 0.86 * xs[0]
        elif i == 3:
            z = 1.91 * z - 0.91 * xs[1]
        else:
            z = 2.0 * z - xs[i - 2]
        pp = 1.0
        for _ in range(100):
            p1, p2 = math.pi ** -0.25, 0.0
            for j in range(n):
                p1, p2 = z * math.sqrt(2.0 / (j + 1)) * p1 - math.sqrt(j / (j + 1.0)) * p2, p1
            pp = math.sqrt(2.0 * n) * p2
            z, z1 = z - p1 / pp, z
            if abs(z - z1) < 1e-15:
                break
        xs[i], xs[n - 1 - i] = z, -z
        ws[i] = ws[n - 1 - i] = 2.0 / (pp * pp)
    return [(math.sqrt(2.0) * x, w / math.sqrt(math.pi)) for x, w in zip(xs, ws)]


_NODES = _gauss_hermite(16)
_SQRT2 = math.sqrt(2.0)


class Demand:
    """The distribution of one day's demand around the mean `lam`, as build_world draws it: the day's level is
    lam x exp(N(0, sigma^2)) and the count is Poisson at that level (a rounded normal from 30 on, as _poisson).
    The day noise is integrated with 16 Gauss-Hermite nodes. cdf[d] = P(demand <= d), part[d] = E[demand; <= d]."""

    __slots__ = ("lam", "mean", "sd", "cdf", "part")

    def __init__(self, lam: float, sigma: float = NOISE):
        self.lam = lam
        if lam <= 0:
            cdf = [1.0]
        else:
            top = lam * math.exp(6 * sigma)
            dmax = int(top + 9 * math.sqrt(top) + 12)
            cdf = [0.0] * (dmax + 1)
            for e, w in _NODES:
                level = lam * math.exp(sigma * e)
                if level >= 30:
                    sd = math.sqrt(level) * _SQRT2
                    lo, hi = max(0, int(level - 6.4 * sd)), min(dmax, int(level + 6.4 * sd) + 1)
                    for d in range(lo, hi + 1):
                        cdf[d] += w * 0.5 * (1.0 + math.erf((d + 0.5 - level) / sd))
                    for d in range(hi + 1, dmax + 1):
                        cdf[d] += w
                else:
                    p = c = math.exp(-level)
                    for d in range(dmax + 1):
                        cdf[d] += w * (c if c < 1.0 else 1.0)
                        p *= level / (d + 1)
                        c += p
        total = cdf[-1]
        self.cdf, self.part = array("d"), array("d")
        prev = mean = second = 0.0
        for d, c in enumerate(cdf):
            c = min(1.0, c / total)
            p = max(0.0, c - prev)
            mean += d * p
            second += d * d * p
            self.cdf.append(c)
            self.part.append(mean)
            prev = c
        self.mean = mean
        self.sd = math.sqrt(max(0.0, second - mean * mean))

    def covered(self, q: float) -> float:
        """P(demand <= q): the probability an order of q covers the day."""
        if q < 0:
            return 0.0
        return self.cdf[min(int(q), len(self.cdf) - 1)]

    def left_over(self, q: float) -> float:
        """E[(q - demand)+]: the expected units left over of an order of q."""
        if q <= 0:
            return 0.0
        d = min(int(q), len(self.cdf) - 1)
        return q * self.cdf[d] - self.part[d]

    def short(self, q: float) -> float:
        """E[(demand - q)+]: the expected units short."""
        return self.mean - q + self.left_over(q)

    def quantile(self, level: float) -> int:
        """The smallest whole quantity that covers demand with probability `level` or more: the order that
        minimizes left over + k x short when level = k / (1 + k)."""
        lo, hi = 0, len(self.cdf) - 1
        while lo < hi:
            mid = (lo + hi) // 2
            if self.cdf[mid] >= level - 1e-12:
                hi = mid
            else:
                lo = mid + 1
        return lo


def _law(world: World, lam: float) -> Demand:
    """The true demand law at mean `lam`, cached per world (a few thousand distinct means)."""
    laws = world.cache.setdefault("laws", {})
    key = round(lam, 9)
    if key not in laws:
        laws[key] = Demand(lam)
    return laws[key]


_PREDICTED: dict[tuple[float, float], Demand] = {}


def _predicted(mean: float, sigma: float) -> Demand:
    """The demand law a model predicts: the same family at a fitted mean (4 significant digits) and its own
    estimate of the day noise. A bounded cache: solvers ask for the same means in every setting."""
    key = (float(f"{mean:.4g}"), round(sigma, 4))
    law = _PREDICTED.get(key)
    if law is None:
        if len(_PREDICTED) >= 30000:
            _PREDICTED.clear()
        law = _PREDICTED[key] = Demand(*key)
    return law


# ── the setting's rules and the demand it judges against ─────────────────────

@dataclass(frozen=True)
class Rules:
    """What one setting asks for, read from its Setting."""

    tier: str
    floor: float                       # min_display: core items' minimum order on open days
    holiday: dt.date | None            # the one-off holiday (medium, hard)
    promos: bool                       # the promotion plan is in the order (medium, hard)
    uplift: float                      # the flyer's multiple of a past promotion's extra sales
    cancelled: str | None              # the category whose promotions were cancelled on 30 October (hard)
    lost_sale: float                   # a unit short costs this many leftover units
    cushion: float                     # the managers' habit: this share on top of the eight-week average
    rolls: bool                        # bread rolls (I07) are judged (hard)

    @property
    def scored_items(self) -> tuple[str, ...]:
        return tuple(i for i in ITEMS if self.rolls or i != UNIT_CHANGE_ITEM)

    @property
    def level(self) -> float:
        """The share of days the best order covers: lost_sale / (1 + lost_sale)."""
        return self.lost_sale / (1.0 + self.lost_sale)

    @property
    def key(self) -> tuple:
        return (self.promos, self.uplift, self.cancelled, self.holiday, self.rolls)


def rules_of(setting: Setting) -> Rules:
    p = setting.params
    medium = setting.at_least("medium")
    hard = setting.at_least("hard")
    holiday = str(p["holiday_date"])
    cancelled = str(p["promo_cancelled"])
    return Rules(tier=setting.tier, floor=float(p["min_display"]),
                 holiday=dt.date.fromisoformat(holiday) if holiday != "none" else None,
                 promos=medium, uplift=float(p["promo_uplift"]) if medium else 1.0,
                 cancelled=cancelled if hard and cancelled != "none" else None,
                 lost_sale=float(p["lost_sale_cost"]), cushion=HABIT_CUSHION[int(p["lost_sale_cost"])] / 100.0,
                 rolls=hard)


def planned_pct(world: World, store: str, item: str, day: dt.date) -> int:
    """The discount promo_plan.csv shows for this cell (0: none)."""
    return next((p[4] for p in world.promo_plan if p[0] == store and p[1] == item and p[2] <= day <= p[3]), 0)


def promo_pct(world: World, rules: Rules, store: str, item: str, day: dt.date) -> int:
    """The discount running for this cell under the setting (0: none, or not in this tier's order)."""
    if not rules.promos or ITEMS[item][0] == rules.cancelled:
        return 0
    return planned_pct(world, store, item, day)


def is_core(item: str) -> bool:
    return ITEMS[item][0] in CORE_CATEGORIES


def cells(world: World) -> list[tuple[str, str, dt.date]]:
    """Every store x item x day of the horizon, in the deliverable's row order."""
    return [(s, i, day) for day in world.horizon for s in STORES for i in ITEMS]


def demand(world: World, rules: Rules) -> dict[tuple[str, str, str], Demand | None]:
    """(store, item, date) -> the law of that day's customer demand under the setting (the promotions with the
    flyer and the cancellation, the holiday on its date; easy: the base demand), None on a closed day. Cached."""
    key = ("demand",) + rules.key[:4]
    if key not in world.cache:
        world.cache[key] = {
            (s, i, day.isoformat()): None if is_closed(s, day) else _law(world, _mean(
                s, i, day, promo_pct(world, rules, s, i, day), day == rules.holiday, rules.uplift))
            for s, i, day in cells(world)}
    return world.cache[key]


# ── data rendering ───────────────────────────────────────────────────────────

FILES = {
    "sales": {"zh": "销售历史.csv", "en": "sales_history.csv", "ko": "판매이력.csv", "ja": "販売履歴.csv",
              "es": "historial_ventas.csv"},
    "promo": {"zh": "促销计划.csv", "en": "promo_plan.csv", "ko": "행사계획.csv", "ja": "販促計画.csv",
              "es": "plan_promociones.csv"},
    "holidays": {"zh": "节假日.csv", "en": "holidays.csv", "ko": "공휴일.csv", "ja": "祝日一覧.csv", "es": "festivos.csv"},
    "stores": {"zh": "门店清单.csv", "en": "stores.csv", "ko": "점포목록.csv", "ja": "店舗一覧.csv", "es": "tiendas.csv"},
    "items": {"zh": "商品清单.csv", "en": "items.csv", "ko": "상품목록.csv", "ja": "商品マスタ.csv", "es": "articulos.csv"},
}
COLS = {
    "date": {"zh": "日期", "en": "date", "ko": "날짜", "ja": "日付", "es": "fecha"},
    "store": {"zh": "门店编号", "en": "store_id", "ko": "점포코드", "ja": "店舗コード", "es": "id_tienda"},
    "item": {"zh": "商品编号", "en": "item_id", "ko": "상품코드", "ja": "商品コード", "es": "id_articulo"},
    "units": {"zh": "销量", "en": "units_sold", "ko": "판매수량", "ja": "販売数量", "es": "unidades_vendidas"},
    "promo_pct": {"zh": "促销折扣_%", "en": "promo_discount_pct", "ko": "행사할인율_%", "ja": "販促割引率_%",
                  "es": "descuento_promo_pct"},
    "stockout": {"zh": "缺货", "en": "stockout", "ko": "품절", "ja": "欠品", "es": "rotura_stock"},
    "start": {"zh": "开始日期", "en": "start_date", "ko": "시작일", "ja": "開始日", "es": "fecha_inicio"},
    "end": {"zh": "结束日期", "en": "end_date", "ko": "종료일", "ja": "終了日", "es": "fecha_fin"},
    "discount": {"zh": "折扣_%", "en": "discount_pct", "ko": "할인율_%", "ja": "割引率_%", "es": "descuento_pct"},
    "holiday": {"zh": "节日名称", "en": "holiday", "ko": "공휴일명", "ja": "祝日名", "es": "festivo"},
    "store_name": {"zh": "门店名称", "en": "store_name", "ko": "점포명", "ja": "店舗名", "es": "nombre_tienda"},
    "format": {"zh": "业态", "en": "format", "ko": "점포유형", "ja": "業態", "es": "formato"},
    "item_name": {"zh": "商品名称", "en": "item_name", "ko": "상품명", "ja": "商品名", "es": "nombre_articulo"},
    "category": {"zh": "品类", "en": "category", "ko": "카테고리", "ja": "カテゴリ", "es": "categoria"},
    "unit": {"zh": "销售单位", "en": "sales_unit", "ko": "판매단위", "ja": "販売単位", "es": "unidad_venta"},
}
VALUES = {
    "yes": {"zh": "是", "en": "yes", "ko": "예", "ja": "はい", "es": "sí"},
    "no": {"zh": "否", "en": "no", "ko": "아니오", "ja": "いいえ", "es": "no"},
    "produce": {"zh": "果蔬", "en": "fresh produce", "ko": "신선 청과", "ja": "青果", "es": "fruta y verdura"},
    "dairy": {"zh": "乳制品", "en": "dairy", "ko": "유제품", "ja": "乳製品", "es": "lácteos"},
    "bakery": {"zh": "烘焙", "en": "bakery", "ko": "베이커리", "ja": "ベーカリー", "es": "panadería"},
    "beverages": {"zh": "饮料", "en": "beverages", "ko": "음료", "ja": "飲料", "es": "bebidas"},
    "supermarket": {"zh": "社区超市", "en": "supermarket", "ko": "슈퍼마켓", "ja": "スーパー", "es": "supermercado"},
    "express": {"zh": "便利店", "en": "express", "ko": "소형 매장", "ja": "小型店", "es": "exprés"},
    "christmas": {"zh": "圣诞节", "en": "Christmas Day", "ko": "성탄절", "ja": "クリスマス", "es": "Navidad"},
    "new_year": {"zh": "元旦", "en": "New Year's Day", "ko": "신정", "ja": "元日", "es": "Año Nuevo"},
    "spring": {"zh": "春季公共假日", "en": "Spring Holiday", "ko": "봄 공휴일", "ja": "春の祝日", "es": "Festivo de primavera"},
    "labour": {"zh": "劳动节", "en": "Labour Day", "ko": "근로자의 날", "ja": "労働の日", "es": "Día del Trabajo"},
    "summer": {"zh": "夏季公共假日", "en": "Summer Holiday", "ko": "여름 공휴일", "ja": "夏の祝日", "es": "Festivo de verano"},
    "autumn": {"zh": "秋季公共假日", "en": "Autumn Holiday", "ko": "가을 공휴일", "ja": "秋の祝日", "es": "Festivo de otoño"},
}
STORE_INFO = {
    "S1": ("supermarket", {"zh": "中央广场店", "en": "Central Plaza", "ko": "중앙광장점", "ja": "中央広場店", "es": "Plaza Central"}),
    "S2": ("supermarket", {"zh": "河东店", "en": "Eastbank", "ko": "강동점", "ja": "川東店", "es": "Ribera Este"}),
    "S3": ("supermarket", {"zh": "北站店", "en": "North Station", "ko": "북부역점", "ja": "北駅前店", "es": "Estación Norte"}),
    "S4": ("express", {"zh": "老城店", "en": "Old Town", "ko": "구도심점", "ja": "旧市街店", "es": "Casco Antiguo"}),
    "S5": ("supermarket", {"zh": "湖滨店", "en": "Lakeside", "ko": "호수공원점", "ja": "湖畔店", "es": "Lago"}),
}
ITEM_INFO = {  # item id: (name, sales unit)
    "I01": ({"zh": "香蕉", "en": "Bananas", "ko": "바나나", "ja": "バナナ", "es": "Plátanos"},
            {"zh": "千克", "en": "kg", "ko": "kg", "ja": "kg", "es": "kg"}),
    "I02": ({"zh": "番茄", "en": "Tomatoes", "ko": "토마토", "ja": "トマト", "es": "Tomates"},
            {"zh": "千克", "en": "kg", "ko": "kg", "ja": "kg", "es": "kg"}),
    "I03": ({"zh": "新鲜罗勒", "en": "Fresh basil", "ko": "생바질", "ja": "フレッシュバジル", "es": "Albahaca fresca"},
            {"zh": "把", "en": "bunch", "ko": "단", "ja": "束", "es": "manojo"}),
    "I04": ({"zh": "全脂牛奶 1L", "en": "Whole milk 1L", "ko": "흰우유 1L", "ja": "牛乳 1L", "es": "Leche entera 1L"},
            {"zh": "盒", "en": "carton", "ko": "팩", "ja": "本", "es": "brik"}),
    "I05": ({"zh": "原味酸奶", "en": "Plain yogurt", "ko": "플레인 요거트", "ja": "プレーンヨーグルト", "es": "Yogur natural"},
            {"zh": "杯", "en": "cup", "ko": "개", "ja": "個", "es": "unidad"}),
    "I06": ({"zh": "陈年奶酪", "en": "Aged cheese", "ko": "숙성 치즈", "ja": "熟成チーズ", "es": "Queso curado"},
            {"zh": "块", "en": "piece", "ko": "개", "ja": "個", "es": "pieza"}),
    "I07": ({"zh": "小餐包", "en": "Bread rolls", "ko": "모닝빵", "ja": "ロールパン", "es": "Panecillos"},
            {"zh": "6个装", "en": "pack of 6", "ko": "6개입 팩", "ja": "6個入りパック", "es": "paquete de 6"}),
    "I08": ({"zh": "酸面包", "en": "Sourdough loaf", "ko": "사워도우", "ja": "サワードウ", "es": "Pan de masa madre"},
            {"zh": "个", "en": "loaf", "ko": "개", "ja": "斤", "es": "pieza"}),
    "I09": ({"zh": "牛角包", "en": "Croissant", "ko": "크루아상", "ja": "クロワッサン", "es": "Cruasán"},
            {"zh": "个", "en": "piece", "ko": "개", "ja": "個", "es": "unidad"}),
    "I10": ({"zh": "气泡水 1.5L", "en": "Sparkling water 1.5L", "ko": "탄산수 1.5L", "ja": "炭酸水 1.5L",
             "es": "Agua con gas 1,5L"}, {"zh": "瓶", "en": "bottle", "ko": "병", "ja": "本", "es": "botella"}),
    "I11": ({"zh": "橙汁 1L", "en": "Orange juice 1L", "ko": "오렌지주스 1L", "ja": "オレンジジュース 1L",
             "es": "Zumo de naranja 1L"}, {"zh": "瓶", "en": "bottle", "ko": "병", "ja": "本", "es": "botella"}),
    "I12": ({"zh": "冷萃咖啡", "en": "Cold brew coffee", "ko": "콜드브루 커피", "ja": "コールドブリューコーヒー",
             "es": "Café cold brew"}, {"zh": "罐", "en": "can", "ko": "캔", "ja": "缶", "es": "lata"}),
}

# The note in mail/ (agent-visible, the same in every setting): the Central Plaza (S1) store manager asks the
# ordering desk for 20% on top of whatever numbers it gets. It is his wish, not company policy: the client says so
# when asked (target manager_note), and following it over-orders S1.
NOTE_FILE = "2026-10-28_central_plaza_orders.eml"
NOTE_WHEN = (2026, 10, 28, 18, 5)
NOTE_FROM = {
    "en": "Store manager, Central Plaza (S1) <s1.manager@freshcorner.example>",
    "zh": "中央广场店（S1）店长 <s1.manager@freshcorner.example>",
    "ko": "중앙광장점(S1) 점장 <s1.manager@freshcorner.example>",
    "ja": "中央広場店（S1）店長 <s1.manager@freshcorner.example>",
    "es": "Gerente de tienda, Plaza Central (S1) <s1.manager@freshcorner.example>",
}
NOTE_TO = {
    "en": "Ordering desk <ordering@freshcorner.example>",
    "zh": "订货组 <ordering@freshcorner.example>",
    "ko": "발주 담당 <ordering@freshcorner.example>",
    "ja": "発注担当 <ordering@freshcorner.example>",
    "es": "Mesa de pedidos <ordering@freshcorner.example>",
}
NOTE_SUBJECT = {
    "en": "November orders for Central Plaza",
    "zh": "中央广场店11月订货",
    "ko": "중앙광장점 11월 발주 건",
    "ja": "中央広場店の11月の発注について",
    "es": "Pedidos de noviembre para Plaza Central",
}
NOTE_BODY = {
    "en": "Hello,\n\nWe keep running out of one line or another on Saturdays, and I have customers leaving without "
          "what they came for. Whatever numbers you get for November, please add 20% on top for Central Plaza, on "
          "every product and every day. Better a few units too many than an empty shelf.\n\nThanks,\nStore manager, "
          "Central Plaza",
    "zh": "你好：\n\n我们一到周六总有品种卖断货，有顾客没买到想要的东西就走了。11月的数字不管算出来是多少，"
          "请给中央广场店每个商品、每一天都再加20%。宁可多几件，也不要空货架。\n\n谢谢。\n中央广场店店长",
    "ko": "안녕하세요.\n\n토요일마다 이런저런 품목이 동나서, 찾던 물건을 못 사고 돌아가시는 고객이 있습니다. 11월 "
          "수치가 어떻게 나오든 중앙광장점은 모든 상품, 모든 날짜에 20%를 더 얹어 주세요. 진열대가 비는 것보다는 몇 개 "
          "남는 편이 낫습니다.\n\n감사합니다.\n중앙광장점 점장",
    "ja": "お疲れさまです。\n\n土曜日になると何かしらの商品が売り切れてしまい、お目当ての品を買えずに帰られるお客様が"
          "います。11月の数字がどう出ても、中央広場店の分は全商品・全日、20%上乗せしてください。棚が空になるよりは、"
          "少し余るほうがましです。\n\nよろしくお願いします。\n中央広場店 店長",
    "es": "Hola:\n\nLos sábados siempre nos quedamos sin alguna referencia y hay clientes que se van sin lo "
          "que venían a buscar. Salgan las cifras que salgan para noviembre, por favor añadan un 20% para Plaza "
          "Central, en todos los productos y todos los días. Mejor que sobren unas unidades que un estante vacío."
          "\n\nGracias.\nGerente de tienda, Plaza Central",
}


def write_note(data_dir: Path, lang: str) -> None:
    """The store manager's e-mail in mail/ (the same in every setting)."""
    folder = data_dir / "mail"
    folder.mkdir(parents=True, exist_ok=True)
    write_eml(folder / NOTE_FILE, sender=NOTE_FROM[lang], to=NOTE_TO[lang],
              date=format_datetime(dt.datetime(*NOTE_WHEN, tzinfo=dt.timezone(dt.timedelta(hours=1)))),
              subject=NOTE_SUBJECT[lang], body=NOTE_BODY[lang] + "\n",
              message_id="<central-plaza-november@freshcorner.example>")


def write_data(world: World, data_dir: Path, lang: str) -> None:
    c, v = labels(COLS, lang), labels(VALUES, lang)
    write_note(data_dir, lang)
    write_csv(data_dir / FILES["sales"][lang],
              [c["date"], c["store"], c["item"], c["units"], c["promo_pct"], c["stockout"]],
              [[d, s, i, u, p, v["yes" if out else "no"]] for d, s, i, u, p, out in world.history])
    write_csv(data_dir / FILES["promo"][lang], [c["store"], c["item"], c["start"], c["end"], c["discount"]],
              [[s, i, a.isoformat(), b.isoformat(), p] for s, i, a, b, p in world.promo_plan])
    write_csv(data_dir / FILES["holidays"][lang], [c["date"], c["holiday"]],
              [[d, v[k]] for d, k in world.holidays])
    write_csv(data_dir / FILES["stores"][lang], [c["store"], c["store_name"], c["format"]],
              [[s, names[lang], v[fmt]] for s, (fmt, names) in STORE_INFO.items()])
    write_csv(data_dir / FILES["items"][lang], [c["item"], c["item_name"], c["category"], c["unit"]],
              [[i, ITEM_INFO[i][0][lang], v[ITEMS[i][0]], ITEM_INFO[i][1][lang]] for i in ITEMS])


# ── scoring ──────────────────────────────────────────────────────────────────

KEYS = ("store_id", "item_id", "date")
QUANTITY = ("order_qty", "forecast")     # the number the stores order; a file with only `forecast` is ordered as it is
COLUMNS = KEYS + QUANTITY[:1]
Plan = dict[tuple[str, str, str], float]
# The request names no file format, and a file called forecast.csv is scored as it stands, so its header decides
# nothing: a key column may carry the name the client's own data gives it in any of the five languages, and the
# quantity is the order_qty column, else a forecast column, else the file's one other column of numbers.
KEY_NAMES = {key: {key} | {name.lower() for name in COLS[col].values()}
             for key, col in zip(KEYS, ("store", "item", "date"))}


def _is_number(v) -> bool:
    try:
        return math.isfinite(float(v))
    except (TypeError, ValueError):
        return False


def _header(rows: list[dict]) -> tuple[dict[str, str], str]:
    """({key: its column in the file}, the quantity column) of forecast.csv; Fatal when either cannot be told."""
    names = [c for c in rows[0] if isinstance(c, str)]
    clean = {c: c.strip().lower() for c in names}
    keys = {}
    for key in KEYS:
        found = [c for c in names if clean[c] in KEY_NAMES[key]]
        if len(found) != 1:
            raise Fatal(f"forecast.csv: missing column {key!r}" if not found else
                        f"forecast.csv: {len(found)} columns for {key!r}")
        keys[key] = found[0]
    for wanted in QUANTITY:
        named = [c for c in names if clean[c] == wanted]
        if named:
            return keys, named[0]
    rest = [c for c in names if clean[c] and c not in keys.values()]       # a nameless column is a row index
    numbers = [c for c in rest if all(_is_number(r.get(c)) for r in rows)]
    if len(numbers) != 1:
        raise Fatal(f"forecast.csv: missing column {QUANTITY[0]!r}" + (
            f" ({len(numbers)} other columns hold numbers: which one the stores order is not said)" if numbers else ""))
    return keys, numbers[0]


def evaluate_plan(world: World, plan: Plan, missing: int, dupes: int, rules: Rules):
    """(violations, objective, metrics) of an order plan: the rules on the order, then per store the expected
    units left over + lost_sale x the expected units short over its judged items and days, divided by its
    expected demand; the objective is the mean over the stores. A row the plan lacks is an order of 0."""
    violations: list[tuple[str, str]] = []
    if missing:
        violations.append(("complete_grid", f"{missing} store x item x date rows are missing"))
    if dupes:
        violations.append(("complete_grid", f"{dupes} store x item x date rows appear more than once"))
    neg = [k for k, x in plan.items() if x < 0]
    if neg:
        violations.append(("non_negative", f"{len(neg)} negative order quantities, e.g. {'/'.join(neg[0])}"))
    law = demand(world, rules)
    closed = [k for k, x in plan.items() if x != 0 and law[k] is None]
    if closed:
        violations.append(("closed_day_zero", f"{len(closed)} orders for {CLOSED_STORE} on Sundays, "
                                              f"e.g. {'/'.join(closed[0])}"))
    low = [k for k, x in plan.items() if is_core(k[1]) and x < rules.floor and law[k] is not None]
    if low:
        violations.append(("min_display_stock", f"{len(low)} core-item orders below {rules.floor:g} on open days, "
                                                f"e.g. {'/'.join(low[0])}"))
    scored = set(rules.scored_items)
    cost = dict.fromkeys(STORES, 0.0)
    expected = dict.fromkeys(STORES, 0.0)
    left = short = cover = 0.0
    n = 0
    for (s, i, ds), d in law.items():
        if i not in scored:
            continue
        q = max(0.0, plan.get((s, i, ds), 0.0))
        if d is None:                   # a closed day: whatever is ordered is left over
            cost[s] += q
            left += q
            continue
        over = d.left_over(q)
        under = d.mean - q + over
        cost[s] += over + rules.lost_sale * under
        expected[s] += d.mean
        left, short, cover, n = left + over, short + under, cover + d.covered(q), n + 1
    by_store = {s: cost[s] / expected[s] for s in STORES}
    objective = round(sum(by_store.values()) / len(by_store), 8)
    total = sum(expected.values())
    return violations, objective, {
        "cost_by_store": {s: round(x, 5) for s, x in by_store.items()}, "mean_cost": round(objective, 5),
        "lost_sale_cost": rules.lost_sale, "left_over_share": round(left / total, 5),
        "short_share": round(short / total, 5), "days_covered": round(cover / n, 5),
        "judged_against": "expected cost under the demand distribution"}


def read_plan(world: World, submission_dir: Path) -> tuple[Plan, int, int]:
    """(plan, missing rows, duplicate rows) of forecast.csv; Fatal when it cannot be read."""
    rows = read_csv(submission_dir, "forecast.csv", ())
    if not rows:
        raise Fatal("forecast.csv has no rows")
    keys, column = _header(rows)
    horizon = {d.isoformat() for d in world.horizon}
    plan: Plan = {}
    dupes = 0
    for n, r in enumerate(rows, start=2):
        s, i, d = (str(r.get(keys[k]) or "").strip() for k in KEYS)
        if s not in STORES:
            raise Fatal(f"forecast.csv line {n}: unknown store_id {s!r}")
        if i not in ITEMS:
            raise Fatal(f"forecast.csv line {n}: unknown item_id {i!r}")
        if d not in horizon:
            raise Fatal(f"forecast.csv line {n}: date {d!r} is not a YYYY-MM-DD date in the forecast horizon")
        if (s, i, d) in plan:
            dupes += 1
        plan[(s, i, d)] = number(r.get(column), f"forecast.csv line {n} {column}")
    return plan, len(STORES) * len(ITEMS) * HORIZON_DAYS - len(plan), dupes


def score(world: World, submission_dir: Path, setting: Setting) -> dict:
    rules = rules_of(setting)
    try:
        plan, missing, dupes = read_plan(world, submission_dir)
        violations, objective, metrics = evaluate_plan(world, plan, missing, dupes, rules)
    except Fatal as e:
        return {"fatal": str(e)}
    enforced, evidence = diagnostics(world, plan, missing, dupes, rules)
    return {"violations": violations, "objective": objective, "metrics": metrics, "enforced": enforced,
            "evidence": evidence}


# ── the per-target diagnostic: does the plan implement each client fact? ─────
#
# Every check reads the plan where only that fact decides the order, and compares it with the demand law, which the
# scorer knows: the share of ordinary days an order covers (the cost ratio), how far each item's orders stand above
# its expected demand against its stockout rate (stockout days read as demand or as sales), promotion days and the
# holiday against the same weekday of the other week, the slow core items (the display minimum) and Central Plaza
# against the other stores (the manager's note). The best plan is the yardstick, so it is enforced by construction.

def _logit(p: float) -> float:
    p = min(max(p, 1e-4), 1 - 1e-4)
    return math.log(p / (1 - p))


def _frame(world: World, rules: Rules) -> dict:
    """What the diagnostics compare a plan with, cached per world and tier scope: the ordinary cells (open, judged,
    no promotion in the plan, not on a date the holiday can fall on, not a slow core item), the promotion days with
    their twin (the same weekday of the other week, itself an ordinary day), and the base demand law of each. A
    promotion of a slow core item is not read either: a display minimum holds both days at the same order, so
    its lift says nothing about the promotion."""
    key = ("frame", rules.rolls)
    if key in world.cache:
        return world.cache[key]
    base = {(s, i, day.isoformat()): None if is_closed(s, day) else _law(world, _mean(s, i, day, 0, False))
            for s, i, day in cells(world)}
    scored = set(rules.scored_items)

    def ordinary(s: str, i: str, day: dt.date) -> bool:
        return (i in scored and not is_closed(s, day) and day not in HOLIDAY_DATES
                and not planned_pct(world, s, i, day))

    def twin(day: dt.date) -> dt.date:
        return day + dt.timedelta(days=7 if (day - HORIZON_START).days < 7 else -7)

    plain = [(s, i, day.isoformat()) for s, i, day in cells(world) if ordinary(s, i, day) and i not in SLOW_ITEMS]
    promos = []
    for n, (s, i, start, end, pct) in enumerate(world.promo_plan):
        pairs = [(day.isoformat(), twin(day).isoformat()) for day in world.horizon
                 if start <= day <= end and day not in HOLIDAY_DATES and ordinary(s, i, twin(day))]
        if i in scored and i not in SLOW_ITEMS and pairs:
            promos.append({"n": n, "store": s, "item": i, "cat": ITEMS[i][0], "pct": pct, "pairs": pairs})
    frame = {"base": base, "plain": plain, "promos": promos, "twin": twin}
    world.cache[key] = frame
    return frame


def _covered_by(world: World, rules: Rules, frame: dict) -> dict:
    """The share of ordinary days (not Central Plaza's) each reading of the cost fact covers: every candidate of
    lost_sale_cost in the tier, and "mean", the expected demand ordered as it is."""
    key = ("covered", rules.tier, rules.rolls)
    if key not in world.cache:
        laws = [frame["base"][k] for k in frame["plain"] if k[0] != NOTE_STORE]
        out = {"mean": sum(d.covered(round(d.mean, 2)) for d in laws) / len(laws)}
        for k in dict.fromkeys(POOLS["lost_sale_cost"][rules.tier]):
            out[float(k)] = sum(d.covered(d.quantile(float(k) / (1.0 + float(k)))) for d in laws) / len(laws)
        world.cache[key] = out
    return world.cache[key]


def _least_squares(rows: list[list[float]], y: list[float]) -> list[float] | None:
    """The coefficients of the least-squares fit of y on the columns of `rows` (normal equations, Gaussian
    elimination with partial pivoting); None when the columns are not independent."""
    n = len(rows[0])
    a = [[sum(r[i] * r[j] for r in rows) for j in range(n)] + [sum(r[i] * v for r, v in zip(rows, y))]
         for i in range(n)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(a[r][col]))
        if abs(a[pivot][col]) < 1e-10:
            return None
        a[col], a[pivot] = a[pivot], a[col]
        for r in range(n):
            if r != col and a[r][col]:
                f = a[r][col] / a[col][col]
                a[r] = [x - f * z for x, z in zip(a[r], a[col])]
    return [a[i][n] / a[i][i] for i in range(n)]


def diagnostics(world: World, plan: Plan, missing: int, dupes: int, rules: Rules) -> tuple[dict, dict]:
    """({target: True | False | None}, {target: evidence}) for the targets in force in the setting."""
    frame = _frame(world, rules)
    base = frame["base"]
    enforced: dict[str, bool | None] = {}
    evidence: dict[str, str] = {}

    def say(target: str, value: bool | None, text: str) -> None:
        enforced[target], evidence[target] = value, text

    say("submission_format", missing == 0 and dupes == 0,
        f"{missing} of the {len(base)} store x item x date rows missing, {dupes} twice")

    # ── the cost ratio: the share of ordinary days the orders cover ──
    plain = [k for k in frame["plain"] if k in plan]
    others = [k for k in plain if k[0] != NOTE_STORE]
    if others:
        share = sum(base[k].covered(plan[k]) for k in others) / len(others)
        readings = _covered_by(world, rules, frame)
        cut = (_logit(readings["mean"]) + min(_logit(v) for k, v in readings.items() if k != "mean")) / 2
        say("order_quantity", _logit(share) > cut,
            f"the orders cover demand on {share:.1%} of ordinary store x item days; the expected demand ordered "
            f"as it is covers {readings['mean']:.1%}")
        # The plan is read as another candidate's only when its coverage sits at that candidate: within a quarter
        # of the way from it to the client's. In between, a plan sized for the client's ratio by a cruder model or
        # one with another idea of the day noise is not called a misreading. (On the public world and world seeds
        # 1-5 the reference sized for another candidate sits at -0.18 to 0.22 of that way where it bites, and
        # plans sized for the client's ratio by other models at 0.32 or more.) The check reads the cushion the
        # plan ends up with, not the ratio its author had in mind: one flat percentage for every product, or twice
        # the day noise, can land a plan on the neighbouring candidate, and it then costs about as much. A plan
        # that hands in the expected demand has no cushion to read a cost ratio from.
        own = _logit(readings[rules.lost_sale])
        at = [k for k, v in readings.items() if k not in ("mean", rules.lost_sale)
              and (_logit(share) - _logit(v)) * (1 if own > _logit(v) else -1) < abs(own - _logit(v)) / 4]
        say("lost_sale_cost", not at if enforced["order_quantity"] else None,
            f"the orders cover {share:.1%} of ordinary days; the best plan covers "
            + ", ".join(f"{v:.1%} at a missed sale of {k:g}" for k, v in readings.items() if k != "mean")
            + (f": the plan sits at {', '.join(f'{k:g}' for k in at)}" if at else ""))
    else:
        say("order_quantity", None, "no ordinary store x item day in the plan")
        say("lost_sale_cost", None, "no ordinary store x item day in the plan")

    # ── stockout days: demand, or sales as recorded (which sit lower, most for the items that run out most) ──
    # Store by store and item by item, how far the orders stand above expected demand, explained by four things at
    # once: the item's category and the store (a model's own level errors, such as a missed season, are shared
    # within them), the cell's variability (a cushion grows with it, whatever the cost ratio; a flat percentage
    # does not) and what reading stockout days as normal sales takes off the item's level. The last coefficient is
    # 0 for a plan that reads them as censored demand and 1 for one that reads them as sales.
    groups: dict[tuple[str, str], list] = {}
    for k in plain:                             # Central Plaza too: its store effect takes the note's 20%
        groups.setdefault((k[0], k[1]), []).append(k)
    lost = 1 - sum(SOLD_ON_STOCKOUT) / 2        # the share of a stockout day's demand the till never saw
    cats, shops = sorted({ITEMS[i][0] for _, i in groups}), sorted({s for s, _ in groups})
    design, level = [], []
    for (s, i), keys in groups.items():
        ordered, mean = sum(plan[k] for k in keys), sum(base[k].mean for k in keys)
        if ordered <= 0:
            continue
        design.append([float(ITEMS[i][0] == c) for c in cats] + [float(s == x) for x in shops[1:]]
                      + [sum(base[k].sd for k in keys) / mean, math.log(1 - ITEMS[i][2] * lost)])
        level.append(math.log(ordered / mean))
    fitted = _least_squares(design, level) if len(design) >= 2 * (len(cats) + len(shops) + 1) else None
    if fitted is not None:
        say("stockout_censoring", fitted[-1] < 0.5,
            f"item by item, the orders sit lower with the item's stockout rate at {fitted[-1]:.2f} of what reading "
            f"stockout days as normal sales takes off (0: demand, 1: sales as recorded)")
    else:
        say("stockout_censoring", None, "too few stores and items in the plan")

    # The yardstick of the lift checks below is the best order, or, for a plan that hands in the expected demand
    # (no cushion: order_quantity not enforced), the expected demand itself: a cushion grows more slowly than the
    # demand it covers, so a promotion or a holiday lifts the best order by less than it lifts demand.
    sized = enforced.get("order_quantity") is not False

    def ideal(s: str, i: str, day: dt.date, pct: int = 0, holiday: bool = False, uplift: float = 1.0) -> float:
        """The best order for a cell under one reading of its day, at the setting's cost ratio and minimum (the
        expected demand for a plan without a cushion)."""
        law = _law(world, _mean(s, i, day, pct, holiday, uplift))
        q = float(law.quantile(rules.level)) if sized else law.mean
        return max(rules.floor, q) if is_core(i) else q

    def best(k: tuple[str, str, str]) -> float:
        return ideal(k[0], k[1], dt.date.fromisoformat(k[2]))

    # ── the manager's note: Central Plaza against the other stores, each against its best plan ──
    noted = [k for k in plain if k[0] == NOTE_STORE]
    if noted and others:
        ratio = (sum(plan[k] for k in noted) / sum(best(k) for k in noted)) / (
            sum(plan[k] for k in others) / sum(best(k) for k in others))
        say("manager_note", ratio < 1 + NOTE_EXTRA / 2,
            f"against the best plan, Central Plaza's orders stand {ratio - 1:+.1%} above the other stores' (the "
            f"note asks for {NOTE_EXTRA:+.0%})")
    else:
        say("manager_note", None, "no ordinary Central Plaza day in the plan")

    # ── promotion days against the same weekday of the other week, as a share of what the best plan adds for a
    #    promotion at the historical lift (0: no lift, 1: the historical lift, 2 or 3: the flyer's multiple) ──
    uplifts = [float(u) for u in dict.fromkeys(POOLS["promo_uplift"]["hard"])]
    lifts: dict[str, list[tuple[float, dict[float, float]]]] = {}
    for p in frame["promos"]:
        s, i = p["store"], p["item"]
        pairs = [(a, b) for a, b in p["pairs"] if (s, i, a) in plan and (s, i, b) in plan]
        den = sum(plan[(s, i, b)] for _, b in pairs)
        if not pairs or den <= 0:
            continue
        twin = sum(best((s, i, b)) for _, b in pairs)
        extra = {u: sum(ideal(s, i, dt.date.fromisoformat(a), p["pct"], False, u) for a, _ in pairs) / twin - 1
                 for u in uplifts}
        if extra[1.0] < 0.05:           # a slow core item at its display minimum on both days: nothing to read
            continue
        got = sum(plan[(s, i, a)] for a, _ in pairs) / den - 1
        lifts.setdefault(p["cat"], []).append((got / extra[1.0], {u: extra[u] / extra[1.0] for u in uplifts}))
    shares = {c: median(x for x, _ in v) for c, v in lifts.items()}
    if not rules.promos:
        everything = [x for v in lifts.values() for x, _ in v]
        if everything:
            say("base_forecast", median(everything) < 0.5,
                f"the plan's promotion days carry {median(everything):.2f} of the historical promotion lift (0: the "
                f"base order)")
        else:
            say("base_forecast", None, "no promotion day in the plan")
    else:
        in_force = {c: x for c, x in shares.items() if c != rules.cancelled}
        lifted = [c for c, x in in_force.items() if x >= 0.5]
        say("promo_plan", bool(lifted) if in_force else None,
            "promotion days by category, as a share of the historical lift: "
            + ", ".join(f"{c} {x:.2f}" for c, x in sorted(in_force.items())))
        if lifted:
            rows = [row for c in lifted for row in lifts[c]]
            level = median(x for x, _ in rows)
            pool = [float(u) for u in dict.fromkeys(POOLS["promo_uplift"][rules.tier])]
            marks = {u: median(by[u] for _, by in rows) for u in pool}
            nearest = min(pool, key=lambda u: abs(math.log(max(level, 0.05) / marks[u])))
            # a lift past the largest multiple by more than half the step to the one below it is no candidate's
            # (the multiple applied to the whole day's demand instead of the extra sales lands there)
            top = sorted(pool)[-2:]
            beyond = len(top) == 2 and level > marks[top[1]] * math.sqrt(marks[top[1]] / marks[top[0]])
            # the multiple is read against the historical lift, which a plan that takes stockout days (more
            # frequent on promotion) as normal sales understates: there the multiple cannot be told
            say("promo_flyer",
                nearest == rules.uplift and not beyond if enforced["stockout_censoring"] is not False else None,
                f"the promotions in the order carry {level:.2f} times the historical lift: "
                + ("more than any flyer multiple" if beyond else f"nearest to a flyer multiple of {nearest:g}")
                + " (" + ", ".join(f"{u:g}: {x:.2f}" for u, x in marks.items()) + ")")
        else:
            say("promo_flyer", None, "no promotion is in the order")
        if rules.cancelled:
            # The cancelled category's promotions carry no lift, and no category still running was dropped instead.
            # "No lift" is under a quarter of the historical one: a plan that keeps a promotion but understates
            # its lift (stockout days read as sales, a slow item held at a higher display minimum) carries 0.37
            # or more of it, a dropped one about 0. A plan without any promotion cannot be told.
            gone = shares.get(rules.cancelled)
            dropped = [c for c, x in in_force.items() if c in CANCELLABLE and x < 0.25]
            if not lifted:
                say("promo_revision", None, "no promotion is in the order")
            else:
                say("promo_revision", (gone is None or gone < 0.25) and not dropped,
                    f"the cancelled {rules.cancelled} promotions carry "
                    + (f"{gone:.2f}" if gone is not None else "an unreadable share")
                    + " of the historical lift" + (f"; {', '.join(dropped)} promotions, which run, carry none"
                                                   if dropped else ""))

    # ── the one-off holiday against the same weekday of the other week, as a share of the best plan's lift ──
    if rules.holiday:
        other = frame["twin"](rules.holiday)
        day, twin_day = rules.holiday.isoformat(), other.isoformat()
        keys = [(s, i) for s in STORES for i in rules.scored_items
                if (s, i, day) in plan and (s, i, twin_day) in plan and base[(s, i, day)] is not None
                and not planned_pct(world, s, i, rules.holiday) and not planned_pct(world, s, i, other)]

        def lift(cells: list[tuple[str, str]]) -> tuple[float, float] | None:
            """(the plan's lift, the yardstick's lift) of the holiday against the other week over these cells."""
            den = sum(plan[(s, i, twin_day)] for s, i in cells)
            if not cells or den <= 0:
                return None
            return (sum(plan[(s, i, day)] for s, i in cells) / den - 1,
                    sum(ideal(s, i, rules.holiday, 0, True) for s, i in cells)
                    / sum(ideal(s, i, other) for s, i in cells) - 1)

        whole = lift(keys)
        if whole:
            got, true = whole
            # the client names the categories that rise most: each must carry half of its own lift too (a holiday
            # ordered like a Saturday, or at fresh produce's lift for everything, misses bakery)
            named = {c: lift([(s, i) for s, i in keys if ITEMS[i][0] == c]) for c in HOLIDAY_MOST}
            weak = [c for c, x in named.items() if x and x[0] / x[1] < 0.5]
            say("one_off_holiday", got / true >= 0.5 and not weak,
                f"{rules.holiday.day} November is ordered {got:+.1%} against the same weekday of the other week: "
                f"{got / true:.2f} of the holiday's lift"
                + "".join(f"; {c} {named[c][0] / named[c][1]:.2f} of its own" for c in weak))
        else:
            say("one_off_holiday", None, "the holiday is not in the plan")

    # ── the display minimum: no core order under it, and the slow core items not held at a higher candidate ──
    core = [k for k in plan if is_core(k[1]) and base[k] is not None]
    if core:
        lowest = min(plan[k] for k in core)
        held = None
        for c in sorted((float(c) for c in dict.fromkeys(POOLS["min_display"][rules.tier]) if float(c) > rules.floor),
                        reverse=True):
            # the cells a minimum of c would hold up: the slow core items whose best order is clearly under c
            slow = [k for k in core if k[1] in SLOW_ITEMS and base[k].quantile(rules.level) <= c - 2]
            if slow and sum(plan[k] == c for k in slow) >= 0.6 * len(slow):
                held = c
                break
        say("min_display", lowest >= rules.floor and held is None,
            f"the lowest core order on an open day is {lowest:g}" + (
                f"; the slow core items are held at {held:g}, not at {rules.floor:g}" if held is not None else ""))
    else:
        say("min_display", None, "no core item in the plan")
    return enforced, evidence


# ── reference solution ───────────────────────────────────────────────────────

LEVEL_DAYS = 84          # the reference's level: the last twelve weeks
PROFILE_DAYS = 728       # its weekday profile: the two years of history
RESIDUAL_DAYS = 182      # its estimate of the day noise: the last 26 weeks


@dataclass
class Fit:
    """What the reference learns from the history, for one reading of it (demand, or sales as recorded)."""

    level: dict[tuple[str, str], float]
    wday: dict[tuple[str, str], list[float]]
    season: dict[str, float]
    promo_lift: dict[tuple[str, int], float]     # (category, discount) -> sales on promotion / normal level
    holiday_lift: dict[str, float]               # category -> sales on a holiday / normal level
    sigma: float                                 # the day noise left once Poisson counting is taken out


def _fit(world: World, censored: bool = True, unit_change: bool = True) -> Fit:
    """A weekday-level model per store x item from the history only, cached per world and reading.

    censored=True (the client's reading): stockout days are censored and left out, return rows are not demand.
    censored=False (sales as the till recorded them): every trading day counts and returns are netted against the
    day's sales. Both: I07's history before the unit change is divided by 6, promotion and holiday days are left
    out of the level and the weekday profile, and their lifts are measured per category (per discount for
    promotions) against the local level. The weekday profile is the category's, pooled over its items and stores
    and both years (one item in one store has too few days per weekday); the level is the store x item's own over
    the last twelve weeks, carried into November by last year's change of the category's level over the same
    weeks. unit_change=False takes I07's history as recorded (the literal solution).
    """
    key = ("fit", censored, unit_change)
    if key in world.cache:
        return world.cache[key]
    n = (HORIZON_START - HIST_START).days
    days = [HIST_START + dt.timedelta(days=t) for t in range(n)]
    wd = [d.weekday() for d in days]
    hol = {d for d, _ in world.holidays}
    pairs = [(s, i) for s in STORES for i in ITEMS]
    sales: dict[tuple[str, str], list[float]] = {k: [0.0] * n for k in pairs}
    present = {k: [False] * n for k in pairs}
    out = {k: [False] * n for k in pairs}
    promo = {k: [0] * n for k in pairs}
    for d, s, i, u, p, so in world.history:
        t = (dt.date.fromisoformat(d) - HIST_START).days
        k = (s, i)
        promo[k][t] = p
        x = u / PACK if unit_change and i == UNIT_CHANGE_ITEM and days[t] < UNIT_CHANGE else u
        if u < 0:
            if not censored:
                sales[k][t] += x      # the till report nets a return against the day's sales
            continue                  # returns are not demand
        sales[k][t] += x
        present[k][t] = True
        out[k][t] = out[k][t] or so

    holiday_day = [d.isoformat() in hol for d in days]
    ok = {k: [present[k][t] and not (censored and out[k][t]) for t in range(n)] for k in pairs}
    clean = {k: [ok[k][t] and promo[k][t] == 0 and not holiday_day[t] for t in range(n)] for k in pairs}

    # the weekday profile per category: each weekday's sales against the store x item's Monday-Saturday mean
    profile: dict[str, list[float]] = {}
    year = range(n - PROFILE_DAYS, n)
    for cat in WEEKDAY:
        num, den = [0.0] * 7, [0.0] * 7
        for k in pairs:
            if ITEMS[k[1]][0] != cat:
                continue
            week = [sales[k][t] for t in year if clean[k][t] and wd[t] < 6]
            base = sum(week) / max(1, len(week))
            for t in year:
                if clean[k][t]:
                    num[wd[t]] += sales[k][t]
                    den[wd[t]] += base
        profile[cat] = [num[j] / den[j] if den[j] > 0 else 0.0 for j in range(7)]
    wday = {k: [0.0 if is_closed(k[0], HORIZON_START + dt.timedelta(days=j)) else profile[ITEMS[k[1]][0]][j]
                for j in range(7)] for k in pairs}

    promo_num: dict[tuple[str, int], float] = {}
    promo_den: dict[tuple[str, int], float] = {}
    hol_num: dict[str, float] = {}
    hol_den: dict[str, float] = {}
    level_now, level_ly, level_ly_h = {}, {}, {}
    square = weight = 0.0
    for k in pairs:
        x, w = sales[k], wday[k]
        v = [x[t] / w[wd[t]] if clean[k][t] and w[wd[t]] > 0 else None for t in range(n)]

        def level(a: int, b: int) -> float | None:
            vals = [v[t] for t in range(max(0, a), min(n, b)) if v[t] is not None]
            return sum(vals) / len(vals) if vals else None

        level_now[k] = level(n - LEVEL_DAYS, n) or 0.0
        level_ly[k] = level(n - LEVEL_DAYS - 364, n - 364) or 0.0
        level_ly_h[k] = level(n - 364 - 14, n - 364 + HORIZON_DAYS + 14) or 0.0
        cat = ITEMS[k[1]][0]
        for t in range(n):
            lifted = promo[k][t] != 0 or holiday_day[t]
            if not ok[k][t] or w[wd[t]] == 0 or (promo[k][t] and holiday_day[t]):
                continue
            if not lifted and t < n - RESIDUAL_DAYS:
                continue
            loc = level(t - 28, t + 29)
            if loc is None:
                continue
            fitted = loc * w[wd[t]]
            if promo[k][t]:
                pk = (cat, promo[k][t])
                promo_num[pk] = promo_num.get(pk, 0.0) + x[t]
                promo_den[pk] = promo_den.get(pk, 0.0) + fitted
            elif holiday_day[t]:
                hol_num[cat] = hol_num.get(cat, 0.0) + x[t]
                hol_den[cat] = hol_den.get(cat, 0.0) + fitted
            else:                     # the day noise: Var = mean + sigma^2 mean^2 for Poisson counts around it
                square += (x[t] - fitted) ** 2 - fitted
                weight += fitted * fitted

    season = {}
    for cat in WEEKDAY:
        keys = [k for k in pairs if ITEMS[k[1]][0] == cat]
        season[cat] = sum(level_ly_h[k] for k in keys) / max(1e-9, sum(level_ly[k] for k in keys))
    fit = Fit(level=level_now, wday=wday, season=season,
              promo_lift={pk: promo_num[pk] / promo_den[pk] for pk in promo_num},
              holiday_lift={cat: hol_num[cat] / hol_den[cat] for cat in hol_num},
              sigma=math.sqrt(max(0.0, square / weight)) if weight else 0.0)
    world.cache[key] = fit
    return fit


@dataclass(frozen=True)
class Reading:
    """How a planner reads the facts that shape a cell's expected demand."""

    promos: bool                       # the promotion plan is in the order
    uplift: float                      # the flyer's multiple of the historical extra sales
    cancelled: str | None              # the category whose promotions do not run
    holiday: dt.date | None            # the one-off holiday

    @staticmethod
    def of(rules: Rules) -> "Reading":
        return Reading(rules.promos, rules.uplift, rules.cancelled, rules.holiday)


def _expected(world: World, fit: Fit, reading: Reading) -> dict[tuple[str, str, str], float | None]:
    """(store, item, date) -> the demand the model expects (None on a closed day): the fitted level x season x
    weekday, the category's lift at the discount with the flyer's multiple of its extra sales on a promotion day
    the reading keeps, and the category's holiday lift on the holiday."""
    out: dict[tuple[str, str, str], float | None] = {}
    for s, i, day in cells(world):
        cat = ITEMS[i][0]
        if is_closed(s, day):
            out[(s, i, day.isoformat())] = None
            continue
        f = fit.level[(s, i)] * fit.season[cat] * fit.wday[(s, i)][day.weekday()]
        pct = planned_pct(world, s, i, day) if reading.promos and cat != reading.cancelled else 0
        if pct:
            f *= 1 + reading.uplift * (fit.promo_lift.get((cat, pct), 1.0) - 1)
        if day == reading.holiday:
            f *= fit.holiday_lift.get(cat, 1.0)
        out[(s, i, day.isoformat())] = f
    return out


def _orders(expected: dict, sigma: float, level: float | None, floor: float) -> Plan:
    """An order per cell: the `level` quantile of the demand the model predicts around its expected value (None:
    the expected value itself, to two decimals), 0 on a closed day, the display minimum on core items."""
    plan: Plan = {}
    for key, m in expected.items():
        if m is None:
            plan[key] = 0.0
            continue
        q = round(m, 2) if level is None else float(_predicted(m, sigma).quantile(level))
        plan[key] = max(floor, q) if is_core(key[1]) else q
    return plan


def _reference(world: World, rules: Rules, fit: Fit | None = None, reading: Reading | None = None,
               level: float | None = -1.0, floor: float | None = None) -> Plan:
    """The reference plan under `rules`, with any one reading changed (the ablations): the fit, how the calendar
    is read, the share of days to cover (None: the expected demand as the order) or the display minimum."""
    fit = fit or _fit(world)
    return _orders(_expected(world, fit, reading or Reading.of(rules)), fit.sigma,
                   rules.level if level == -1.0 else level, rules.floor if floor is None else floor)


def _write(out_dir: Path, plan: Plan, quantity: str = QUANTITY[0]) -> None:
    write_csv(out_dir / "forecast.csv", [*KEYS, quantity], [[s, i, d, x] for (s, i, d), x in plan.items()])


def reference_solution(world: World, out_dir: Path, setting: Setting) -> None:
    """The reference: the model's expected demand per cell (stockout days left out, returns not demand, I07 in
    packs), the promotions and the holiday this setting has, then the order that covers the setting's share of
    days, lost_sale_cost / (1 + lost_sale_cost), under the demand it predicts; S4's Sundays at 0 and the display
    minimum on core items."""
    _write(out_dir, _reference(world, rules_of(setting)))


# The request at face value: "how much each store will sell" read as till sales net of returns (stockout days as
# recorded), with the promotion plan attached (at the lift past promotions show) and the holidays on file (none
# falls in the horizon); I07's history taken as recorded; the forecast itself as the number to order ("we place our
# orders from these numbers"), so no cushion and no display minimum (S4's Sundays come out at 0 because its history
# has no Sunday rows); and the store manager's e-mail followed, since the client sent it along. No one-off holiday,
# flyer or cancellation, which only the client knows.
LITERAL_READING = Reading(promos=True, uplift=1.0, cancelled=None, holiday=None)


def _noted(plan: Plan, whole: bool = False) -> Plan:
    """The plan with the store manager's note followed: 20% on top for Central Plaza (rounded up to whole units
    for a plan of whole units)."""
    def more(x: float) -> float:
        return float(math.ceil(x * (1 + NOTE_EXTRA) - 1e-9)) if whole else round(x * (1 + NOTE_EXTRA), 2)
    return {k: more(x) if k[0] == NOTE_STORE else x for k, x in plan.items()}


def _literal(world: World) -> Plan:
    fit = _fit(world, censored=False, unit_change=False)
    return _noted(_orders(_expected(world, fit, LITERAL_READING), fit.sigma, None, 0.0))


def literal_solution(world: World, out_dir: Path) -> None:
    """The request done as written: the reference's model fitted to sales as recorded, handed in as a forecast
    column, which the stores order as it is (the same file in every setting)."""
    _write(out_dir, _literal(world), quantity=QUANTITY[1])


def _habit(world: World, rules: Rules, weeks: int = HABIT_WEEKS) -> Plan:
    """The store managers' habit, what the client does without an engineer: for every item the average of what the
    till recorded on that weekday in the last eight weeks (`weeks`), days the shelf ran empty left aside, plus the
    managers' cushion; 2% more per point of discount (times the flyer's multiple) on a day the item is on
    promotion; the one-off holiday ordered like a Saturday; rounded up to whole units, S4's Sundays at 0 and the
    display minimum on core items.

    The managers know their business (what is on promotion and in the flyer, the holiday, the cancellation, which
    days they ran out) but not statistics: eight days per weekday, one cushion for every item, one promotion rule
    for every category. Return rows (negative units) are not sales and are skipped. In easy the category team adds
    the promotions, so they are not in the habit's order.
    """
    sold: dict[tuple[str, str, str], tuple[float, bool]] = {}
    first = (HORIZON_START - dt.timedelta(days=7 * weeks)).isoformat()
    for d, s, i, u, _, out in world.history:
        if d >= first and u >= 0:
            sold[(s, i, d)] = (float(u), out)
    plan: Plan = {}
    for s, i, day in cells(world):
        key = (s, i, day.isoformat())
        if is_closed(s, day):
            plan[key] = 0.0
            continue
        weekday = 5 if day == rules.holiday else day.weekday()
        days = [sold[(s, i, d)] for d in ((HORIZON_START - dt.timedelta(days=7 * k - weekday)).isoformat()
                                          for k in range(1, weeks + 1)) if (s, i, d) in sold]
        seen = [u for u, out in days if not out] or [u for u, _ in days]    # a day the shelf ran empty is no guide
        f = (sum(seen) / len(seen) if seen else 0.0) * (1 + rules.cushion)
        f *= 1 + HABIT_PROMO * promo_pct(world, rules, s, i, day) * rules.uplift
        f = float(math.ceil(f - 1e-9))
        plan[key] = max(rules.floor, f) if is_core(i) else f
    return plan


def baseline_solution(world: World, out_dir: Path, setting: Setting) -> None:
    _write(out_dir, _habit(world, rules_of(setting)))


def violating_examples(world: World, setting: Setting) -> dict:
    """One deliverable per rule that breaks exactly that rule (for the validator)."""
    rules = rules_of(setting)
    ref = _reference(world, rules)
    keys = list(ref)
    open_key = next(k for k in keys if ITEMS[k[1]][0] == "beverages" and not is_closed(k[0], dt.date.fromisoformat(k[2])))
    core_key = next(k for k in keys if is_core(k[1]) and not is_closed(k[0], dt.date.fromisoformat(k[2])))
    closed_key = next(k for k in keys if is_closed(k[0], dt.date.fromisoformat(k[2])))

    def variant(change):
        def make(out: Path) -> None:
            plan = dict(ref)
            change(plan)
            _write(out, plan)
        return make

    return {
        "complete_grid": variant(lambda plan: plan.pop(open_key)),
        "non_negative": variant(lambda plan: plan.update({open_key: -1.0})),
        "closed_day_zero": variant(lambda plan: plan.update({closed_key: 5.0})),
        "min_display_stock": variant(lambda plan: plan.update({core_key: rules.floor - 1.0})),
    }


# ── ground truth audit hooks (fdebench2.audit, GT.md) ────────────────────────

_EN_TARGETS = yaml.safe_load((Path(__file__).parent / "locales" / "en" / "targets.yaml").read_text(encoding="utf-8"))
TARGET_TIERS = {t["id"]: tuple(t.get("tiers", TIERS)) for t in _EN_TARGETS}


def ablations(world: World, setting: Setting) -> dict:
    """{target: write the plan that misreads only that fact}: the reference with one reading changed to the most
    natural one the agent's own view suggests, for every target in force that is not a drawn parameter (those the
    audit ablates itself, with the reference of each other candidate)."""
    rules = rules_of(setting)
    reading = Reading.of(rules)

    def order_quantity(out: Path) -> None:
        """The number read as a sales forecast the stores add their own cushion to: the expected demand."""
        _write(out, _reference(world, rules, level=None))

    def stockout_censoring(out: Path) -> None:
        """Stockout days read as normal sales, returns netted: sales as the till recorded them."""
        _write(out, _reference(world, rules, fit=_fit(world, censored=False)))

    def base_forecast(out: Path) -> None:
        """The promotion plan read as part of the order (it is attached), at the historical lift."""
        _write(out, _reference(world, rules, reading=Reading(True, 1.0, None, reading.holiday)))

    def promo_plan(out: Path) -> None:
        """The promotions read as somebody else's top-up: the base order only."""
        _write(out, _reference(world, rules, reading=Reading(False, 1.0, None, reading.holiday)))

    def manager_note(out: Path) -> None:
        """The store manager's e-mail followed: 20% on top for Central Plaza."""
        _write(out, _noted(_reference(world, rules), whole=True))

    def submission_format(out: Path) -> None:
        """Rows only where the store trades: S4's Sundays left out."""
        _write(out, {k: x for k, x in _reference(world, rules).items()
                     if not is_closed(k[0], dt.date.fromisoformat(k[2]))})

    made = {f.__name__: f for f in (order_quantity, stockout_censoring, base_forecast, promo_plan, manager_note,
                                     submission_format)}
    return {t: f for t, f in made.items() if setting.tier in TARGET_TIERS.get(t, ())}


def shortcuts(world: World, setting: Setting) -> dict:
    """Degenerate plans a lazy or gaming agent might hand in; each must be invalid or score at most 0.5."""
    rules = rules_of(setting)

    def floored(plan: Plan) -> Plan:
        return {k: max(rules.floor, x) if is_core(k[1]) and not is_closed(k[0], dt.date.fromisoformat(k[2])) else x
                for k, x in plan.items()}

    def recent(weeks: int) -> dict[tuple[str, str], list[float]]:
        """Per store x item, the units the till recorded on each trading day of the last `weeks` weeks."""
        first = (HORIZON_START - dt.timedelta(days=7 * weeks)).isoformat()
        seen: dict[tuple[str, str], list[float]] = {}
        for d, s, i, u, _, _ in world.history:
            if d >= first and u >= 0:
                seen.setdefault((s, i), []).append(float(u))
        return seen

    def constant(value) -> Plan:
        return floored({(s, i, day.isoformat()): 0.0 if is_closed(s, day) else float(value(s, i))
                        for s, i, day in cells(world)})

    def literal_plus_floor(out: Path) -> None:
        """The literal solution with the one rule it breaks kept: the display minimum on core items."""
        _write(out, floored(_literal(world)))

    def forecast_as_order(out: Path) -> None:
        """Ignore the uncertainty: every other fact right, the expected demand handed in as the order."""
        _write(out, _reference(world, rules, level=None))

    def blanket_cushion(out: Path) -> None:
        """Pad everything: the literal forecast with the store manager's 20% on top for every store."""
        fit = _fit(world, censored=False, unit_change=False)
        plain = _orders(_expected(world, fit, LITERAL_READING), fit.sigma, None, 0.0)
        _write(out, floored({k: round(x * (1 + NOTE_EXTRA), 2) for k, x in plain.items()}))

    def copy_last_week(out: Path) -> None:
        """Copy the data through: last week's sales of the same weekday, for both weeks."""
        sold = {(s, i, d): float(u) for d, s, i, u, _, _ in world.history if u >= 0}
        _write(out, floored({(s, i, day.isoformat()): 0.0 if is_closed(s, day) else sold.get(
            (s, i, (HORIZON_START - dt.timedelta(days=7 - day.weekday())).isoformat()), 0.0)
            for s, i, day in cells(world)}))

    def flat_average(out: Path) -> None:
        """Output constants: one number per store and item, its average day of the last eight weeks, every day."""
        seen = recent(8)
        _write(out, constant(lambda s, i: round(sum(seen[(s, i)]) / len(seen[(s, i)]), 2)))

    def never_run_out(out: Path) -> None:
        """Never run out: every day the most the store sold of the item on any day of the last eight weeks."""
        seen = recent(8)
        _write(out, constant(lambda s, i: max(seen[(s, i)])))

    def display_only(out: Path) -> None:
        """Order nothing but the display minimum of the core items."""
        _write(out, constant(lambda s, i: 0.0))

    def judged_rows_only(out: Path) -> None:
        """Leave out the rows that are not judged or always 0: bread rolls (I07) and S4's Sundays."""
        _write(out, {k: x for k, x in _reference(world, rules).items()
                     if k[1] != UNIT_CHANGE_ITEM and not is_closed(k[0], dt.date.fromisoformat(k[2]))})

    def habit_last_year(out: Path) -> None:
        """Copy the client's own way and change one thing: the managers' habit averaged over the last 52 weeks."""
        _write(out, _habit(world, rules, weeks=52))

    def habit_more_cushion(out: Path) -> None:
        """Copy the client's own way and pad it: the managers' habit with ten points more cushion."""
        _write(out, _habit(world, dataclasses.replace(rules, cushion=rules.cushion + 0.10)))

    def literal_sized_cushion(out: Path) -> None:
        """Ask one thing only, the cost of a missed sale: the literal forecast with a flat cushion sized for it."""
        fit = _fit(world, censored=False, unit_change=False)
        plain = _orders(_expected(world, fit, LITERAL_READING), fit.sigma, None, 0.0)
        pad = 1 + SHORTCUT_SPREAD * _NORMAL.inv_cdf(rules.level)
        _write(out, floored({k: float(math.ceil(x * pad - 1e-9)) for k, x in plain.items()}))

    def weekday_quantile(out: Path) -> None:
        """No model: per store, item and weekday, the cost ratio's quantile of the last 26 weeks' sales."""
        first = (HORIZON_START - dt.timedelta(days=7 * 26)).isoformat()
        seen: dict[tuple[str, str, int], list[float]] = {}
        for d, s, i, u, _, _ in world.history:
            if d >= first and u >= 0:
                seen.setdefault((s, i, dt.date.fromisoformat(d).weekday()), []).append(float(u))

        def at_level(values: list[float]) -> float:
            values = sorted(values)
            return values[min(len(values), math.ceil(rules.level * len(values))) - 1] if values else 0.0
        _write(out, floored({(s, i, day.isoformat()): 0.0 if is_closed(s, day) else at_level(
            seen.get((s, i, day.weekday()), [])) for s, i, day in cells(world)}))

    return {f.__name__: f for f in (literal_plus_floor, forecast_as_order, blanket_cushion, copy_last_week,
                                     flat_average, never_run_out, display_only, judged_rows_only, habit_last_year,
                                     habit_more_cushion, literal_sized_cushion, weekday_quantile)}


def _mixture(laws: list[tuple[float, Demand]]) -> tuple[list[float], list[float]]:
    """(cdf, partial expectation) of a mixture of demand laws [(weight, law)], on 0..the longest support."""
    size = max(len(d.cdf) for _, d in laws)
    cdf, part = [0.0] * size, [0.0] * size
    for w, d in laws:
        n = len(d.cdf)
        for x in range(size):
            cdf[x] += w * (d.cdf[x] if x < n else 1.0)
            part[x] += w * (d.part[x] if x < n else d.mean)
    return cdf, part


def robust_solution(world: World, out_dir: Path, tier: str, candidates: dict) -> None:
    """The best single plan without asking, from the agent's view and the tier's pools.

    Fixed facts, at their natural reading: stockout days are censored demand and left out (the file flags them),
    I07's history divided by 6 (the data shows the change), S4 closed on Sundays and the promotion plan in the
    order (it is attached, so also in easy, where the client wants it left out). Two facts are granted at the
    client's reading, although a planner that never asks could not know them, so that the gap left does not rest
    on them: the number is the quantity to order (the request only says "we place our orders from these
    numbers"), and the store manager's e-mail is not followed (it is addressed to the ordering desk). Without the
    first grant the plan earns nothing in any tier; without the second it loses 0.07 to 0.10 of its credit. Drawn
    facts, planned across the tier's pools: every candidate date of the holiday, flyer multiple and cancelled
    category is one equally likely scenario of a cell's demand; the order minimizes the expected cost of that
    mixture at one cost ratio, the pool's candidates averaged with each setting's own scale (a setting's cost is
    about (1 + k) x the normal density at its best order); and the strictest display minimum, so the plan is
    valid whatever the client's value.

    The compromise was checked against other ratios, minimums and hedges of the holiday. A planner that scores
    every such plan under its own model, by the mean over all combinations of the pools of (the cost of the plan
    made for the combination) / (this plan's cost), picks this ratio and the strictest minimum. Over all
    combinations a ratio of 20 earns 0.014 to 0.018 more credit, which takes knowing how wide the quality scale
    is."""
    fit = _fit(world)
    ratios = [float(k) for k in dict.fromkeys(candidates["lost_sale_cost"])]
    scale = [1.0 / ((1 + k) * _NORMAL.pdf(_NORMAL.inv_cdf(k / (1 + k)))) for k in ratios]
    ratio = sum(k * w for k, w in zip(ratios, scale)) / sum(scale)
    level = ratio / (1 + ratio)
    floor = max(float(v) for v in candidates["min_display"])
    dates = [None if str(v) == "none" else dt.date.fromisoformat(str(v)) for v in dict.fromkeys(candidates["holiday_date"])]
    uplifts = [float(v) for v in dict.fromkeys(candidates["promo_uplift"])]
    gone = [None if str(v) == "none" else str(v) for v in dict.fromkeys(candidates["promo_cancelled"])]
    scenarios = [Reading(True, u, c, h) for h in dates for u in uplifts for c in gone]
    expected = [_expected(world, fit, r) for r in scenarios]
    plan: Plan = {}
    for key, first in expected[0].items():
        if first is None:
            plan[key] = 0.0
            continue
        weights: dict[float, float] = {}
        for e in expected:
            m = float(f"{e[key]:.4g}")
            weights[m] = weights.get(m, 0.0) + 1.0 / len(expected)
        if len(weights) == 1:
            q = float(_predicted(first, fit.sigma).quantile(level))
        else:
            cdf, _ = _mixture([(w, _predicted(m, fit.sigma)) for m, w in weights.items()])
            q = float(next(d for d, c in enumerate(cdf) if c >= level - 1e-12))
        plan[key] = max(floor, q) if is_core(key[1]) else q
    _write(out_dir, plan)


def _best(world: World, rules: Rules) -> Plan:
    """The plan no valid plan beats: per cell the order that minimizes the expected cost under the true demand law
    (its lost_sale / (1 + lost_sale) quantile), raised to the display minimum on core items, 0 on a closed day."""
    return {key: 0.0 if d is None else max(rules.floor, float(d.quantile(rules.level))) if is_core(key[1])
            else float(d.quantile(rules.level)) for key, d in demand(world, rules).items()}


def best_known_solution(world: World, out_dir: Path, setting: Setting) -> None:
    """The best plan there is: every cell's cost-minimizing order under the demand law the world draws from
    (hindsight no agent has: the true mean of every cell). It reaches objective_bound."""
    _write(out_dir, _best(world, rules_of(setting)))


def objective_bound(world: World, setting: Setting) -> float:
    """A proven lower bound on the objective, and the optimum: the objective is a sum over cells of a cost that
    depends on that cell's order alone, divided by constants, and every rule is a bound on one cell's order. The
    expected cost of a cell, left over + k x short, is convex in the order with its minimum at the k / (1 + k)
    quantile, so the least cost a valid plan can have in a cell is at that quantile, or at the display minimum
    where it is higher (a closed day: 0). The bound is the objective of that plan."""
    rules = rules_of(setting)
    return evaluate_plan(world, _best(world, rules), 0, 0, rules)[1]
