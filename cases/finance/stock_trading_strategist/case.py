"""Stock trading strategy for a small proprietary book (original FDE-Bench v2 case).

A portfolio manager asks for a trading strategy that beats holding the index. The agent gets a year of
synthetic history for the 16 stocks of a fictional exchange and delivers a program `strategy.py:on_day`. The
evaluator replays a hidden, out-of-sample period generated from the same world: once per session, after the
close, it calls the strategy with the market data so far and the book's state, then executes the returned
orders in the next session under the exchange's and the client's rules. All prices are synthetic.

One world for every setting: the same 16 stocks, history, halts, consolidation, earnings, hidden split and
hidden sell-off. The setting decides how the engine executes and which client rules apply:

  easy    the engine's simple mode: fills at the price 10 minutes after the open plus half the spread (or in
          the opening auction at the open), commission with a minimum, board lots, cash only, no short sales,
          sale proceeds usable at once; the firm's restricted list; the desk's habit of not trading in the
          first 10 minutes (bendable)
  medium  + sales tax on sells, sale proceeds settle T+2; per-stock and per-sector limits after buying, an
          order-size cap as a share of the 20-session average volume in today's shares (the consolidation
          in the history leaves volumes raw)
  hard    + market impact that grows with the order's share of the session's volume, and a maximum-drawdown
          mandate (the hidden period holds a sell-off)

The rule sets A / B / C (case.yaml) set the restricted list, the stock and sector limits, the order-size cap
and the drawdown limit. The program cannot ask at run time, so the agent has to learn them from the client.
The whole replay runs in one isolated process (casekit.program_session): the strategy keeps its own state.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import random
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from fdebench2.casekit import Fatal, labels, program_session, write_csv

ENTRYPOINT = "strategy.py:on_day"

# ── market and mandate facts ─────────────────────────────────────────────────

N_HIST = 250                      # sessions of history the agent receives
N_HID = 80                        # hidden sessions the strategy is replayed on
LOOKBACK = 130                    # sessions of bars passed to each call
FIRST_DAY = dt.date(2025, 6, 2)   # a Monday; sessions are Monday-Friday
CAPITAL = 10_000_000.0
FEE_RATE = 0.0004                 # commission 0.04% of the traded value ...
MIN_FEE = 20.0                    # ... at least 20 per order
SALES_TAX = 0.002                 # medium+: 0.2% of the sale value
SETTLE_DAYS = 2                   # medium+: sale proceeds usable from the second session after the trade
ADV_SESSIONS = 20
IMPACT = 0.02                     # hard: extra price cost 0.02 x qty / session volume (0.1% per 5% of the volume)
ANNOUNCE_AHEAD = 10               # corporate actions are announced 10 sessions before the ex-date
CALL_TIMEOUT = 10.0               # seconds per call
TOTAL_TIMEOUT = 600.0             # seconds for the whole replay (one process)

MU_SD, MU_PHI = 0.003, 0.993           # persistent stock drift (AR(1)): what momentum can find
SEC_SD, SEC_PHI = 0.001, 0.99          # persistent sector drift
W_GAP, W10, W10_NOISE = 0.35, 0.3, 0.1   # shares of the drift in the overnight gap and the first 10 minutes
EARN_MOVE = 0.05                          # price reaction per unit of standardized earnings surprise ...
EARN_SPLIT = (0.4, 0.3, 0.3)               # ... split over the gap, the first 10 minutes and the next sessions
EARN_DRIFT_SESSIONS = 10
VOLUME_SCALE = 0.12                        # daily turnover multiplier: a 13% position is 2-3 sessions of the volume cap
SECTORS = ["TECH", "ENER", "HLTH", "CONS"]
#            ticker  sector  base price  shares (M)  daily turnover  half-spread bp  beta  idio vol
STOCK_PLAN = [
    ("QRVL", "TECH", 84.0, 120, 0.0060, 4, 1.25, 0.019),
    ("ZENT", "TECH", 31.5, 90, 0.0070, 7, 1.35, 0.022),
    ("KOVA", "ENER", 46.0, 150, 0.0050, 5, 0.90, 0.017),
    ("BRAX", "ENER", 12.8, 260, 0.0080, 9, 1.05, 0.021),
    ("MEDQ", "HLTH", 212.0, 40, 0.0045, 4, 0.75, 0.014),
    ("VYTA", "HLTH", 58.0, 70, 0.0065, 8, 0.85, 0.018),
    ("LUMO", "CONS", 27.0, 160, 0.0055, 5, 0.80, 0.015),
    ("TARK", "CONS", 143.0, 35, 0.0060, 10, 0.95, 0.017),
    ("XIPH", "TECH", 5.2, 300, 0.0090, 12, 1.45, 0.024),
    ("OMNY", "TECH", 318.0, 20, 0.0050, 6, 1.15, 0.018),
    ("PYRO", "ENER", 66.0, 60, 0.0070, 9, 1.10, 0.020),
    ("GLAC", "ENER", 19.4, 110, 0.0065, 11, 0.95, 0.019),
    ("CURA", "HLTH", 39.0, 80, 0.0060, 10, 0.80, 0.018),
    ("NEXO", "HLTH", 101.0, 45, 0.0055, 7, 0.90, 0.016),
    ("FERN", "CONS", 9.6, 200, 0.0075, 12, 0.85, 0.019),
    ("DUNE", "CONS", 74.0, 50, 0.0060, 8, 1.00, 0.017),
]
CONSOLIDATED = ("XIPH", N_HIST - 7, 0.2)            # 1-for-5 consolidation 7 sessions before the end of the history
SPLIT_HIDDEN = ("OMNY", N_HIST + 34, 2.0)           # 2-for-1 split in the hidden period
HALTS = [  # (ticker, first halted session, sessions, extra jump at resumption)
    ("CURA", 96, 3, -0.06),
    ("BRAX", 181, 2, 0.05),
    ("PYRO", N_HIST + 21, 4, -0.16),
    ("LUMO", N_HIST + 57, 2, 0.09),
]
SELLOFF = (N_HIST + 35, N_HIST + 63, -0.005, 0.016)  # sessions [a, b) with market drift and vol


@dataclass
class Stock:
    ticker: str
    sector: str
    lot: int
    spread_bp: int
    shares: float                 # shares outstanding in the first share basis
    beta: float
    ivol: float


@dataclass
class World:
    dates: list[str]
    stocks: list[Stock]
    # per ticker, per session, in the FIRST share basis (continuous across splits): None when halted
    open: dict
    p10: dict
    close: dict
    vol: dict                     # traded shares in the first share basis
    actions: list                 # (ticker, ex session, ratio new shares per old share)
    halts: list                   # (ticker, first session, last session)
    earnings: list                # (session after whose close it is announced, ticker, surprise %)
    index: list                   # index level per session (cap-weighted, last traded closes)
    _cache: dict = field(default_factory=dict)

    def stock(self, t: str) -> Stock | None:
        return next((s for s in self.stocks if s.ticker == t), None)

    def basis(self, t: str, s: int, asof: int) -> float:
        """Shares of the basis in force after the close of `asof` per share of the first basis, for session s:
        divide a first-basis price by it, multiply a first-basis volume by it. Actions take effect after the
        close of the session before their ex-date."""
        r = 1.0
        for tk, ex, ratio in self.actions:
            if tk == t and ex <= asof + 1:
                r *= ratio
        return r

    def raw_factor(self, t: str, s: int) -> float:
        """Basis in force when session s traded (for raw volumes and raw prices)."""
        r = 1.0
        for tk, ex, ratio in self.actions:
            if tk == t and ex <= s:
                r *= ratio
        return r


class _View:
    """The world as one setting sees it: which tier's engine and rules apply, and the rule set's parameters."""

    def __init__(self, world: World, setting):
        self._w, self.setting = world, setting
        self.medium, self.hard = setting.at_least("medium"), setting.at_least("hard")
        self.restricted = tuple(t.strip() for t in str(setting["restricted"]).split(","))
        self.stock_cap = setting["stock_cap"] / 100
        self.sector_cap = setting["sector_cap"] / 100
        self.participation = setting["participation"] / 100
        self.max_drawdown = setting["max_drawdown"] / 100

    def __getattr__(self, name):
        return getattr(self._w, name)


def _lot(price: float) -> int:
    return 10 if price >= 150 else 100


def build_world(seed: int) -> World:
    """Everything every setting needs (the data and the hidden period are the same in all of them)."""
    n = N_HIST + N_HID
    dates, d = [], FIRST_DAY
    while len(dates) < n + 10:            # a few calendar sessions past the end, for settlement dates
        if d.weekday() < 5:
            dates.append(d.isoformat())
        d += dt.timedelta(days=1)
    plan = STOCK_PLAN

    rm = random.Random(seed * 1000 + 900)
    market = [rm.gauss(0.0004, 0.009) for _ in range(n)]
    rh = random.Random(seed * 1000 + 970)
    a, b, mu, sd = SELLOFF
    for s in range(a, b):
        market[s] = mu + rh.gauss(0.0, sd)
    sector_ret = {}
    for k, sec in enumerate(SECTORS):
        rs = random.Random(seed * 1000 + 901 + k)
        drift, out = rs.gauss(0, SEC_SD), []
        for _ in range(n):
            drift = SEC_PHI * drift + rs.gauss(0, SEC_SD * math.sqrt(1 - SEC_PHI ** 2))
            out.append(drift + rs.gauss(0, 0.005))
        sector_ret[sec] = out

    halts = [(t, a, a + k - 1, jump) for t, a, k, jump in HALTS]
    actions = [CONSOLIDATED, SPLIT_HIDDEN]

    # Earnings announcements: once a quarter per stock, after the close; surprise in %.
    earn_shock: dict = {}
    earnings = []
    re_ = random.Random(seed * 1000 + 971)
    for k, row in enumerate(plan):
        phase = re_.randrange(5, 60)
        for e in range(phase, n - 1, 63):
            z = re_.gauss(0, 1)
            earnings.append((e, row[0], round(5.0 * z, 1)))
            earn_shock[(row[0], e)] = EARN_MOVE * z
    earnings.sort()

    stocks, O, P10, C, V = [], {}, {}, {}, {}
    for i, (t, sec, price0, shares_m, turnover, spread, beta, ivol) in enumerate(plan):
        rs = random.Random(seed * 1000 + i)
        mu = rs.gauss(0, MU_SD)
        logp = math.log(price0)
        o, p, c, v = [], [], [], []
        pend = 0.0                         # log return accumulated while halted
        drift_left = []                    # post-announcement drift still to come
        halted_at = {s: (a, b, j) for tk, a, b, j in halts if tk == t for s in range(a, b + 1)}
        for s in range(n):
            mu = MU_PHI * mu + rs.gauss(0, MU_SD * math.sqrt(1 - MU_PHI ** 2))
            sysr = beta * market[s] + sector_ret[sec][s] + mu
            eg, e10, er = rs.gauss(0, 0.45 * ivol), rs.gauss(0, W10_NOISE * ivol), rs.gauss(0, 0.88 * ivol)
            vn = math.exp(rs.gauss(0, 0.3))
            gap, seg10, rest = W_GAP * sysr + eg, W10 * sysr + e10, (1 - W_GAP - W10) * sysr + er
            shock = earn_shock.get((t, s - 1))
            if shock is not None:            # announced after yesterday's close
                gap += EARN_SPLIT[0] * shock
                seg10 += EARN_SPLIT[1] * shock
                drift_left = [EARN_SPLIT[2] * shock / EARN_DRIFT_SESSIONS] * EARN_DRIFT_SESSIONS
            elif drift_left:
                rest += drift_left.pop()
            if s in halted_at:
                pend += gap + seg10 + rest
                o.append(None), p.append(None), c.append(None), v.append(None)
                continue
            gap += pend
            if s - 1 in halted_at:
                gap += halted_at[s - 1][2]
            pend = 0.0
            lo = logp + gap
            l10 = lo + seg10
            logp = l10 + rest
            o.append(math.exp(lo))
            p.append(math.exp(l10))
            c.append(math.exp(logp))
            day_r = abs(gap + seg10 + rest)
            boost = 2.5 if shock is not None else 1.0
            v.append(shares_m * 1e6 * turnover * VOLUME_SCALE * vn * (1 + 12 * day_r / ivol * 0.1) * boost)
        O[t], P10[t], C[t], V[t] = o, p, c, v
        k = max(x for x in range(N_HIST) if c[x] is not None)
        price_now = c[k] / math.prod(r for tk, ex, r in actions if tk == t and ex <= N_HIST)
        stocks.append(Stock(t, sec, _lot(price_now), spread, shares_m * 1e6, beta, ivol))

    # Index: cap-weighted over all the stocks, on last traded closes (first-basis prices).
    level, lastc = [], {t: None for t in C}
    base = None
    for s in range(n):
        for t in C:
            if C[t][s] is not None:
                lastc[t] = C[t][s]
        cap = sum(st.shares * lastc[st.ticker] for st in stocks)
        base = base or cap
        level.append(1000.0 * cap / base)
    return World(dates, stocks, O, P10, C, V, sorted(actions, key=lambda a: a[1]),
                 [(t, a, b) for t, a, b, _ in halts], earnings, level)


# ── the market as the strategy sees it ───────────────────────────────────────

def market_view(world: World, asof: int) -> dict:
    """Market data after the close of session `asof`, for the call that decides session asof + 1.
    The same in every setting (cached on the world)."""
    cache = world._cache.setdefault("market_view", {})
    if asof in cache:
        return cache[asof]
    start = max(0, asof - LOOKBACK + 1)
    bars = {}
    for st in world.stocks:
        t = st.ticker
        cur = world.basis(t, 0, asof)
        b = {"date": [], "open": [], "p10": [], "close": [], "volume": []}
        for s in range(start, asof + 1):
            if world.close[t][s] is None:
                continue
            b["date"].append(world.dates[s])
            for k, arr in (("open", world.open), ("p10", world.p10), ("close", world.close)):
                b[k].append(round(arr[t][s] / cur, 4))
            b["volume"].append(int(round(world.vol[t][s] * world.raw_factor(t, s))))
        bars[t] = b
    view = {
        "date": world.dates[asof],
        "next_date": world.dates[asof + 1],
        "stocks": {st.ticker: {"sector": st.sector, "lot": st.lot, "half_spread_bp": st.spread_bp}
                   for st in world.stocks},
        "bars": bars,
        "index": {"date": world.dates[start:asof + 1], "level": [round(x, 3) for x in world.index[start:asof + 1]]},
        "halted": sorted(st.ticker for st in world.stocks if world.close[st.ticker][asof] is None),
        "corporate_actions": [{"ex_date": world.dates[ex], "ticker": t, "ratio": ratio}
                              for t, ex, ratio in world.actions if ex <= asof + 1 + ANNOUNCE_AHEAD],
        "earnings": [{"date": world.dates[e], "ticker": t, "surprise_pct": z}
                     for e, t, z in world.earnings if start <= e <= asof],
    }
    cache[asof] = view
    return view


def _adv_now(world: World, t: str, asof: int) -> float:
    """20-session average volume in the shares in force after the close of `asof` (traded sessions only)."""
    cur = world.basis(t, 0, asof)
    vols = [world.vol[t][s] * cur for s in range(asof, -1, -1) if world.vol[t][s] is not None][:ADV_SESSIONS]
    return sum(vols) / len(vols) if vols else 0.0


# ── execution ────────────────────────────────────────────────────────────────

@dataclass
class Book:
    cash: float = CAPITAL                         # settled, usable cash
    pending: list = field(default_factory=list)   # [amount, session it settles at]
    pos: dict = field(default_factory=dict)       # ticker -> shares (current basis)
    peak: float = CAPITAL


def _price(world: World, arr: dict, t: str, s: int) -> float:
    """Price in the basis in force during session s (actions effective after the previous close)."""
    return arr[t][s] / world.basis(t, 0, s - 1)


def _close_now(world: World, t: str, s: int) -> float:
    """Last traded close up to session s, in the basis in force after the close of s."""
    k = s
    while world.close[t][k] is None:
        k -= 1
    return world.close[t][k] / world.basis(t, 0, s)


def _equity(world: World, book: Book, s: int) -> float:
    return book.cash + sum(a for a, _ in book.pending) + sum(q * _close_now(world, t, s) for t, q in book.pos.items())


def _parse_orders(world: World, out, err) -> tuple[list, list]:
    """(orders, problems): well-formed orders and the order_format problems of one call."""
    if err is not None:
        return [], [f"call failed: {err}"[:200]]
    if isinstance(out, dict):
        out = out.get("orders", [])
    if not isinstance(out, list):
        return [], [f"orders is not a list: {type(out).__name__}"]
    orders, problems, seen = [], [], set()
    for k, o in enumerate(out):
        if not isinstance(o, dict):
            problems.append(f"order {k} is not an object")
            continue
        t, side, qty, at = o.get("ticker"), o.get("side"), o.get("qty"), o.get("at", "p10")
        if world.stock(t) is None if isinstance(t, str) else True:
            problems.append(f"order {k}: unknown ticker {t!r}")
        elif side not in ("buy", "sell"):
            problems.append(f"order {k}: side {side!r}")
        elif isinstance(qty, bool) or not isinstance(qty, int) or qty <= 0:
            problems.append(f"order {k}: quantity {qty!r}")
        elif at not in ("open", "p10"):
            problems.append(f"order {k}: at {at!r}")
        elif t in seen:
            problems.append(f"order {k}: second order for {t} in one session")
        else:
            seen.add(t)
            orders.append({"ticker": t, "side": side, "qty": qty, "at": at})
    return orders, problems


def replay(world: _View, decide) -> dict:
    """Run the hidden period in one setting. `decide(market, portfolio)` returns (output, error) for one call."""
    viol: list = []
    book = Book()
    last_fills: list = []
    last_rejects: list = []
    m = {"orders": 0, "filled": 0, "rejected_cash": 0, "rejected_halted": 0, "skipped_invalid": 0,
         "fees": 0.0, "taxes": 0.0, "spread_and_impact": 0.0, "traded_value": 0.0, "open_auction_orders": 0,
         "max_drawdown": 0.0, "max_stock_weight_bought": 0.0, "max_sector_weight_bought": 0.0,
         "participation_breaches": 0, "restricted_orders": 0, "calls_failed": 0}
    dd_reported = False
    for k in range(N_HID):
        s = N_HIST + k
        asof = s - 1
        eq = _equity(world, book, asof)
        portfolio = {"date": world.dates[asof], "cash": round(book.cash, 2),
                     "unsettled": [{"amount": round(a, 2), "settles": world.dates[ss]} for a, ss in book.pending],
                     "positions": {t: q for t, q in sorted(book.pos.items()) if q},
                     "equity": round(eq, 2), "peak_equity": round(book.peak, 2),
                     "fills": last_fills, "rejected": last_rejects}
        out, err = decide(market_view(world, asof), portfolio)
        if err is not None:
            m["calls_failed"] += 1
        orders, problems = _parse_orders(world, out, err)
        for p in problems:
            viol.append(("order_format", f"{world.dates[s]}: {p}"))
        m["orders"] += len(orders)

        # Settlement before trading: amounts that settle at this session become usable.
        book.cash += sum(a for a, ss in book.pending if ss <= s)
        book.pending = [[a, ss] for a, ss in book.pending if ss > s]
        fills, rejects, bought = [], [], set()
        valid = []
        for o in orders:
            st, t, q = world.stock(o["ticker"]), o["ticker"], o["qty"]
            if q % st.lot:
                viol.append(("lot_size", f"{world.dates[s]}: {t} {q} is not a multiple of the board lot {st.lot}"))
                m["skipped_invalid"] += 1
                continue
            if o["side"] == "sell" and q > book.pos.get(t, 0):
                viol.append(("no_short_selling", f"{world.dates[s]}: sells {q} {t}, holds {book.pos.get(t, 0)}"))
                m["skipped_invalid"] += 1
                continue
            if o["at"] == "open":
                viol.append(("no_first_10_minutes", f"{world.dates[s]}: {o['side']} {t} in the opening auction"))
                m["open_auction_orders"] += 1
            if o["side"] == "buy" and t in world.restricted:
                viol.append(("restricted_list", f"{world.dates[s]}: buys {t}, which is on the restricted list"))
                m["restricted_orders"] += 1
            if world.medium:
                cap = world.participation * _adv_now(world, t, asof)
                if q > cap + 1e-9:
                    viol.append(("volume_participation", f"{world.dates[s]}: {t} {q} > {world.participation:.0%} "
                                                         f"of the 20-session average volume ({cap:.0f})"))
                    m["participation_breaches"] += 1
            valid.append(o)
        for o in sorted(valid, key=lambda o: o["side"] != "sell"):        # sells first, then buys in given order
            t, q, side = o["ticker"], o["qty"], o["side"]
            st = world.stock(t)
            if world.close[t][s] is None:
                rejects.append({"ticker": t, "side": side, "qty": q, "reason": "halted"})
                m["rejected_halted"] += 1
                continue
            base = _price(world, world.open if o["at"] == "open" else world.p10, t, s)
            slip = 0.0 if o["at"] == "open" else st.spread_bp / 10000
            if world.hard:
                slip += IMPACT * q / (world.vol[t][s] * world.basis(t, 0, s - 1))
            px = base * (1 + slip) if side == "buy" else base * (1 - slip)
            value = q * px
            fee = max(MIN_FEE, FEE_RATE * value)
            if side == "buy":
                if value + fee > book.cash + 1e-6:
                    rejects.append({"ticker": t, "side": side, "qty": q, "reason": "cash"})
                    m["rejected_cash"] += 1
                    continue
                book.cash -= value + fee
                book.pos[t] = book.pos.get(t, 0) + q
                bought.add(t)
            else:
                tax = SALES_TAX * value if world.medium else 0.0
                net = value - fee - tax
                book.pos[t] -= q
                if not book.pos[t]:
                    del book.pos[t]
                if world.medium:
                    book.pending.append([net, s + SETTLE_DAYS])
                else:
                    book.cash += net
                m["taxes"] += tax
            m["fees"] += fee
            m["spread_and_impact"] += abs(px - base) * q
            m["traded_value"] += value
            m["filled"] += 1
            fills.append({"ticker": t, "side": side, "qty": q, "price": round(px, 4), "fee": round(fee, 2)})

        # Corporate actions take effect after this close (ex-date = next session).
        for t, ex, ratio in world.actions:
            if ex == s + 1 and t in book.pos:
                book.pos[t] = int(book.pos[t] * ratio)
        eq = _equity(world, book, s)
        book.peak = max(book.peak, eq)
        dd = 1 - eq / book.peak
        m["max_drawdown"] = max(m["max_drawdown"], dd)
        if world.hard and dd > world.max_drawdown and not dd_reported:
            viol.append(("max_drawdown", f"{world.dates[s]}: equity {eq:,.0f} is {dd:.1%} below its peak"))
            dd_reported = True
        if world.medium and bought:
            sec_val: dict = {}
            for t, q in book.pos.items():
                sec = world.stock(t).sector
                sec_val[sec] = sec_val.get(sec, 0.0) + q * _close_now(world, t, s)
            for t in sorted(bought):
                w = book.pos.get(t, 0) * _close_now(world, t, s) / eq
                m["max_stock_weight_bought"] = max(m["max_stock_weight_bought"], w)
                if w > world.stock_cap:
                    viol.append(("position_limit", f"{world.dates[s]}: {t} is {w:.1%} of equity after buying"))
            for sec in sorted({world.stock(t).sector for t in bought}):
                w = sec_val.get(sec, 0.0) / eq
                m["max_sector_weight_bought"] = max(m["max_sector_weight_bought"], w)
                if w > world.sector_cap:
                    viol.append(("sector_limit", f"{world.dates[s]}: sector {sec} is {w:.1%} of equity after buying"))
        last_fills, last_rejects = fills, rejects

    s_end = N_HIST + N_HID - 1
    liq = 1 - FEE_RATE - (SALES_TAX if world.medium else 0.0)
    final = book.cash + sum(a for a, _ in book.pending) + sum(q * _close_now(world, t, s_end) * liq
                                                            for t, q in book.pos.items())
    m.update(final_net_equity=round(final, 2), return_pct=round(100 * (final / CAPITAL - 1), 3),
             index_buy_and_hold=round(index_buy_and_hold(world), 2))
    for key in ("fees", "taxes", "spread_and_impact", "traded_value", "max_drawdown", "max_stock_weight_bought",
                "max_sector_weight_bought"):
        m[key] = round(m[key], 4)
    return {"violations": viol, "objective": round(final, 2), "metrics": m}


def index_buy_and_hold(world: _View) -> float:
    """Benchmark: buy the index weights (whole lots) at the first hidden session's p10 plus spread and
    commission, hold, and value the book net of liquidation costs at the end (no client rules applied)."""
    s0, s1 = N_HIST, N_HIST + N_HID - 1
    caps = {st.ticker: st.shares * _close_now(world, st.ticker, s0 - 1) * world.basis(st.ticker, 0, s0 - 1)
            for st in world.stocks}
    total = sum(caps.values())
    cash, pos = CAPITAL, {}
    for st in world.stocks:
        t = st.ticker
        if world.close[t][s0] is None:
            continue
        px = _price(world, world.p10, t, s0) * (1 + st.spread_bp / 10000)
        q = int(0.995 * CAPITAL * caps[t] / total / px / st.lot) * st.lot
        cash -= q * px + max(MIN_FEE, FEE_RATE * q * px)
        pos[t] = q
    for t, ex, ratio in world.actions:
        if s0 <= ex <= s1 and t in pos:
            pos[t] = int(pos[t] * ratio)
    liq = 1 - FEE_RATE - (SALES_TAX if world.medium else 0.0)
    return cash + sum(q * _close_now(world, t, s1) * liq for t, q in pos.items())


# ── running the delivered program ────────────────────────────────────────────

def score(world: World, submission_dir: Path, setting) -> dict:
    view = _View(world, setting)
    try:
        with program_session(Path(submission_dir), ENTRYPOINT, per_call_timeout=CALL_TIMEOUT,
                             total_timeout=TOTAL_TIMEOUT) as prog:
            return replay(view, lambda market, portfolio: prog.call({"market": market, "portfolio": portfolio}))
    except Fatal as e:
        return {"fatal": str(e)}


# ── reference solution ───────────────────────────────────────────────────────

REFERENCE = Path(__file__).resolve().parent / "reference" / "strategy.py"
# A risk switch in every tier: all to cash when the book is 6% below its peak since it last went in, dd_stop
# below its all-time peak, or when the index fell 6% in 20 sessions and is below its 20-session mean; back in
# when the index is above that mean and up over 20 sessions. Earnings are not used.
_COMMON = {"rebalance": 5, "band": 0.25, "cash_buffer": 0.005, "price_buffer": 0.02, "min_fee": MIN_FEE,
           "at": "p10", "risk_switch": True, "dd_off": 0.06, "dd_stop": 0.10, "trend_off": -0.06, "defensive": 0.0}


def ref_config(world: _View) -> dict:
    """The reference strategy's parameters in one setting: its tier's engine and rules, its rule set's values."""
    cfg = dict(_COMMON, restricted=sorted(world.restricted))
    if not world.medium:
        # 4 names at 24% (two per sector at most); sale proceeds reused the same session; no limits to respect.
        return dict(cfg, top=4, weight=0.24, per_sector=2, participation=1e12, sector_target=10.0,
                    same_day_proceeds=True, cost=0.001)
    # Names at 2 points under the stock limit, sectors 4 points under theirs, orders at 95% of the volume cap,
    # buys from settled cash only.
    weight = round(world.stock_cap - 0.02, 4)
    sector_target = round(world.sector_cap - 0.04, 4)
    cfg.update(top=min(8, int(0.92 / weight)), weight=weight, per_sector=max(1, int(sector_target / weight)),
               participation=round(0.95 * world.participation, 5), sector_target=sector_target,
               same_day_proceeds=False, cost=0.003)
    if world.hard:
        cfg["dd_stop"] = round(world.max_drawdown - 0.05, 4)       # 5 points inside the drawdown mandate
    return cfg


def write_program(out_dir: Path, cfg: dict) -> None:
    prog = Path(out_dir) / "program"
    prog.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(REFERENCE, prog / "strategy.py")
    (prog / "config.json").write_text(json.dumps(cfg, indent=1, sort_keys=True), encoding="utf-8")


def reference_solution(world: World, out_dir: Path, setting) -> None:
    write_program(out_dir, ref_config(_View(world, setting)))


def violating_examples(world: World, setting) -> dict:
    """One program per rule of the setting that breaks exactly that rule (for the validator)."""
    view = _View(world, setting)
    ref = ref_config(view)
    variants = {
        "order_format": dict(ref, **{"break": "format"}),         # an unknown ticker on one day
        "lot_size": dict(ref, **{"break": "lot"}),                # one lot plus one share, once
        "no_short_selling": dict(ref, **{"break": "short"}),      # sells a stock it does not hold, once
        "restricted_list": dict(ref, **{"break": "restricted"}),  # buys one lot of a restricted stock, once
        "no_first_10_minutes": dict(ref, at="open"),              # trades in the opening auction
    }
    if view.medium:
        w = round(view.stock_cap + 0.04, 4)                       # names over the stock limit, one per sector
        variants["position_limit"] = dict(ref, top=4, weight=w, per_sector=1, sector_target=w)
        # every stock of one sector, each under the stock limit: the sector goes over its limit
        variants["sector_limit"] = dict(ref, weight=round(view.stock_cap - 0.02, 4), sector_target=1.0,
                                        **{"break": "sector"})
        variants["volume_participation"] = dict(ref, participation=round(1.6 * view.participation, 5))
    if view.hard:
        variants["max_drawdown"] = dict(ref, risk_switch=False)    # rides the sell-off fully invested
    return {rule: (lambda out, cfg=cfg: write_program(out, cfg)) for rule, cfg in variants.items()}



# ── data rendering ───────────────────────────────────────────────────────────

FILES = {
    "stocks": {"zh": "股票清单.csv", "en": "stocks.csv", "ko": "종목목록.csv", "ja": "銘柄一覧.csv", "es": "valores.csv"},
    "prices": {"zh": "日行情.csv", "en": "daily_prices.csv", "ko": "일별시세.csv", "ja": "日次株価.csv",
               "es": "cotizaciones_diarias.csv"},
    "index": {"zh": "指数.csv", "en": "index_levels.csv", "ko": "지수.csv", "ja": "指数.csv", "es": "indice.csv"},
    "actions": {"zh": "公司行动.csv", "en": "corporate_actions.csv", "ko": "기업행위.csv", "ja": "コーポレートアクション.csv",
                "es": "operaciones_corporativas.csv"},
    "halts": {"zh": "停牌记录.csv", "en": "trading_halts.csv", "ko": "거래정지.csv", "ja": "売買停止.csv",
              "es": "suspensiones.csv"},
    "earnings": {"zh": "业绩公告.csv", "en": "earnings_announcements.csv", "ko": "실적발표.csv", "ja": "決算発表.csv",
                 "es": "resultados_trimestrales.csv"},
    "sample": {"zh": "调用示例.json", "en": "sample_call.json", "ko": "호출예시.json", "ja": "呼び出し例.json",
               "es": "ejemplo_llamada.json"},
}
COLS = {
    "ticker": {"zh": "代码", "en": "ticker", "ko": "종목코드", "ja": "銘柄コード", "es": "codigo"},
    "sector": {"zh": "行业", "en": "sector", "ko": "업종", "ja": "業種", "es": "sector"},
    "sector_code": {"zh": "行业代码", "en": "sector_code", "ko": "업종코드", "ja": "業種コード", "es": "codigo_sector"},
    "lot": {"zh": "每手股数", "en": "board_lot", "ko": "매매단위", "ja": "売買単位", "es": "lote"},
    "spread": {"zh": "半价差_基点", "en": "half_spread_bp", "ko": "반스프레드_bp", "ja": "半スプレッド_bp",
               "es": "medio_diferencial_pb"},
    "shares": {"zh": "总股本", "en": "shares_outstanding", "ko": "상장주식수", "ja": "発行済株式数",
               "es": "acciones_en_circulacion"},
    "date": {"zh": "日期", "en": "date", "ko": "날짜", "ja": "日付", "es": "fecha"},
    "open": {"zh": "开盘价", "en": "open", "ko": "시가", "ja": "始値", "es": "apertura"},
    "p10": {"zh": "开盘10分钟价", "en": "p10", "ko": "개장10분가", "ja": "寄り10分値", "es": "precio_10min"},
    "close": {"zh": "收盘价", "en": "close", "ko": "종가", "ja": "終値", "es": "cierre"},
    "volume": {"zh": "成交量", "en": "volume", "ko": "거래량", "ja": "出来高", "es": "volumen"},
    "level": {"zh": "指数点位", "en": "level", "ko": "지수", "ja": "指数値", "es": "nivel"},
    "ex_date": {"zh": "除权日", "en": "ex_date", "ko": "기준일", "ja": "効力発生日", "es": "fecha_efectiva"},
    "action": {"zh": "类型", "en": "action", "ko": "구분", "ja": "種類", "es": "tipo"},
    "old": {"zh": "原股数", "en": "old_shares", "ko": "기존주식수", "ja": "旧株数", "es": "acciones_antiguas"},
    "new": {"zh": "新股数", "en": "new_shares", "ko": "신주식수", "ja": "新株数", "es": "acciones_nuevas"},
    "first": {"zh": "停牌首日", "en": "first_halted_day", "ko": "정지시작일", "ja": "停止開始日",
              "es": "primer_dia_suspendido"},
    "last": {"zh": "停牌末日", "en": "last_halted_day", "ko": "정지종료일", "ja": "停止最終日",
             "es": "ultimo_dia_suspendido"},
    "reason": {"zh": "原因", "en": "reason", "ko": "사유", "ja": "理由", "es": "motivo"},
    "surprise": {"zh": "业绩超预期幅度_pct", "en": "surprise_pct", "ko": "실적서프라이즈_pct", "ja": "サプライズ率_pct",
                 "es": "sorpresa_pct"},
    "timing": {"zh": "公布时间", "en": "released", "ko": "발표시점", "ja": "発表時刻", "es": "publicacion"},
}
VALUES = {
    "TECH": {"zh": "科技", "en": "Technology", "ko": "기술", "ja": "テクノロジー", "es": "Tecnología"},
    "ENER": {"zh": "能源", "en": "Energy", "ko": "에너지", "ja": "エネルギー", "es": "Energía"},
    "HLTH": {"zh": "医疗保健", "en": "Health care", "ko": "헬스케어", "ja": "ヘルスケア", "es": "Salud"},
    "CONS": {"zh": "消费", "en": "Consumer", "ko": "소비재", "ja": "消費財", "es": "Consumo"},
    "split": {"zh": "拆股", "en": "share split", "ko": "주식분할", "ja": "株式分割", "es": "desdoblamiento"},
    "consolidation": {"zh": "合股", "en": "share consolidation", "ko": "주식병합", "ja": "株式併合",
                      "es": "contrasplit"},
    "pending": {"zh": "待公告重大事项", "en": "pending announcement", "ko": "중요 공시 대기", "ja": "重要事実の公表待ち",
                "es": "anuncio pendiente"},
    "after_close": {"zh": "收盘后", "en": "after the close", "ko": "장 마감 후", "ja": "大引け後", "es": "tras el cierre"},
}


def _actions_rows(world: World, until: int, v: dict) -> list:
    rows = []
    for t, ex, ratio in world.actions:
        if ex <= until:
            old, new = (1, int(ratio)) if ratio >= 1 else (int(round(1 / ratio)), 1)
            rows.append([world.dates[ex], t, v["split" if ratio >= 1 else "consolidation"], old, new])
    return rows


def write_data(world: World, data_dir: Path, lang: str) -> None:
    c, v = labels(COLS, lang), labels(VALUES, lang)
    end = N_HIST - 1
    write_csv(data_dir / FILES["stocks"][lang], [c["ticker"], c["sector"], c["sector_code"], c["lot"], c["spread"],
                                                 c["shares"]],
              [[st.ticker, v[st.sector], st.sector, st.lot, st.spread_bp, int(st.shares * world.basis(st.ticker, 0, end))]
               for st in world.stocks])
    rows = []
    for s in range(N_HIST):
        for st in world.stocks:
            t = st.ticker
            if world.close[t][s] is None:
                continue
            cur = world.basis(t, 0, end)
            rows.append([world.dates[s], t, f"{world.open[t][s] / cur:.4f}", f"{world.p10[t][s] / cur:.4f}",
                         f"{world.close[t][s] / cur:.4f}", int(round(world.vol[t][s] * world.raw_factor(t, s)))])
    write_csv(data_dir / FILES["prices"][lang], [c["date"], c["ticker"], c["open"], c["p10"], c["close"], c["volume"]],
              rows)
    write_csv(data_dir / FILES["index"][lang], [c["date"], c["level"]],
              [[world.dates[s], f"{world.index[s]:.3f}"] for s in range(N_HIST)])
    write_csv(data_dir / FILES["actions"][lang], [c["ex_date"], c["ticker"], c["action"], c["old"], c["new"]],
              _actions_rows(world, end, v))
    write_csv(data_dir / FILES["halts"][lang], [c["ticker"], c["first"], c["last"], c["reason"]],
              [[t, world.dates[a], world.dates[b], v["pending"]] for t, a, b in world.halts if b < N_HIST])
    write_csv(data_dir / FILES["earnings"][lang], [c["date"], c["ticker"], c["surprise"], c["timing"]],
              [[world.dates[e], t, f"{z:.1f}", v["after_close"]] for e, t, z in world.earnings if e < N_HIST])
    # One call exactly as the engine makes it, taken from inside the history (no hidden information).
    asof = N_HIST - 61
    eq = CAPITAL
    sample = {"market": market_view(world, asof),
              "portfolio": {"date": world.dates[asof], "cash": eq, "unsettled": [], "positions": {}, "equity": eq,
                            "peak_equity": eq, "fills": [], "rejected": []}}
    (data_dir / FILES["sample"][lang]).write_text(json.dumps(sample, separators=(",", ":")), encoding="utf-8")
