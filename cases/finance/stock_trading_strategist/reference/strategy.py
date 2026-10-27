"""Reference strategy for finance/stock_trading_strategist (copied into program/ with a config.json).

Cross-sectional momentum with risk limits, standard library only:

  * every REBALANCE sessions, rank the stocks by their 60-session return (skipping the last 5 sessions),
    scaled by volatility, and hold the top ones at a fixed weight, a few per sector at most;
  * every session, trade toward those targets: sell what is no longer wanted, buy with the cash that is
    usable (settled cash only when sale proceeds settle T+2), in board lots, within the per-order volume cap
    (measured on volumes converted to today's shares) and with a margin under the stock and sector limits;
  * never buy a stock on the client's restricted list;
  * a risk switch: go to cash when the book's drawdown or the index trend says so.

The engine calls on_day in one process for the whole run, so the strategy keeps its state in a module
variable. The behaviour is set by config.json (written per setting by the case: the client's limits and
restricted list); a few flags exist only so the case can build examples that break one rule each.
"""

import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(HERE, "config.json"), encoding="utf-8") as _f:
    CFG = json.load(_f)

STATE = {}          # survives from one call to the next (the engine keeps the process alive)


def _effective_ratio(ticker, bar_date, actions, next_date):
    """Shares now per share at bar_date: product of the split ratios that took effect after that bar."""
    r = 1.0
    for a in actions:
        if a["ticker"] == ticker and bar_date < a["ex_date"] <= next_date:
            r *= a["ratio"]
    return r


def _adv(ticker, bars, actions, next_date, n=20):
    vols, dates = bars["volume"][-n:], bars["date"][-n:]
    if not vols:
        return 0.0
    if CFG.get("raw_volume"):
        return sum(vols) / len(vols)
    return sum(v * _effective_ratio(ticker, d, actions, next_date) for v, d in zip(vols, dates)) / len(vols)


def _score(closes):
    if len(closes) < 66:
        return None
    rets = [math.log(closes[i] / closes[i - 1]) for i in range(len(closes) - 60, len(closes))]
    mu = sum(rets) / len(rets)
    vol = math.sqrt(sum((x - mu) ** 2 for x in rets) / (len(rets) - 1)) or 1e-6
    return math.log(closes[-6] / closes[-66]) / (vol * math.sqrt(60))


def _rank(market, halted):
    """Momentum scores of the stocks worth holding (positive scores only, restricted stocks left out)."""
    scores, banned = {}, set(CFG.get("restricted", []))
    for t, b in market["bars"].items():
        s = _score(b["close"])
        if s is not None and s > 0 and t not in halted and t not in banned:
            scores[t] = s
    return scores


def _risk_state(market, portfolio, mem):
    """"on" or "off", and the equity peak since the book last went back in.

    Off when the book is dd_off below that peak, or dd_stop below its all-time peak (the mandate's own
    measure), or the index fell trend_off in 20 sessions and is below its 20-session mean; back on when the
    index is above its mean and up over 20 sessions (and the all-time drawdown leaves room)."""
    equity = portfolio["equity"]
    if not CFG.get("risk_switch"):
        return "on", equity
    peak = max(mem.get("peak", equity), equity)
    state = mem.get("risk", "on")
    level = market["index"]["level"]
    ma = sum(level[-20:]) / len(level[-20:])
    r20 = level[-1] / level[-21] - 1 if len(level) > 21 else 0.0
    dd_all = 1 - equity / portfolio["peak_equity"]
    if state == "on":
        if 1 - equity / peak > CFG["dd_off"] or dd_all > CFG["dd_stop"] or (r20 < CFG["trend_off"] and level[-1] < ma):
            return "off", equity
        return "on", peak
    if level[-1] > ma and r20 > 0 and dd_all < CFG["dd_stop"]:
        return "on", equity
    return "off", equity


def on_day(day_input):
    market, portfolio = day_input["market"], day_input["portfolio"]
    day = STATE.get("day", 0)
    stocks, bars = market["stocks"], market["bars"]
    halted = set(market.get("halted", []))
    actions = market.get("corporate_actions", [])
    nxt = market["next_date"]
    pos = {t: q for t, q in portfolio["positions"].items() if q > 0}
    equity = portfolio["equity"]
    last = {t: bars[t]["close"][-1] for t in stocks if bars[t]["close"]}

    state, risk_peak = _risk_state(market, portfolio, STATE)
    expo = 1.0 if state == "on" else CFG["defensive"]
    targets = STATE.get("targets")
    scores = STATE.get("scores", {})
    if targets is None or day % CFG["rebalance"] == 0 or state != STATE.get("risk", "on"):
        scores = _rank(market, halted)
        targets, per_sector = {}, {}
        for t in sorted(scores, key=lambda t: (-scores[t], t)):
            sec = stocks[t]["sector"]
            if len(targets) >= CFG["top"] or per_sector.get(sec, 0) >= CFG["per_sector"]:
                continue
            per_sector[sec] = per_sector.get(sec, 0) + 1
            targets[t] = CFG["weight"] * expo
        if CFG.get("break") == "sector":
            # Example for the case's validator: every stock of the first sector without a restricted name.
            banned = {stocks[t]["sector"] for t in CFG.get("restricted", []) if t in stocks}
            sec = sorted({stocks[t]["sector"] for t in stocks} - banned)[0]
            targets = {t: CFG["weight"] * expo for t in sorted(stocks) if stocks[t]["sector"] == sec}

    orders, proceeds = [], 0.0
    at = CFG.get("at", "p10")
    for t in sorted(pos):
        if t in halted or t not in last:
            continue
        want = targets.get(t, 0.0) * equity
        cur = pos[t] * last[t]
        lot = stocks[t]["lot"]
        if want <= 0:
            qty = pos[t]
        elif cur > want * (1 + CFG["band"]):
            qty = int((cur - want) / last[t] / lot) * lot
        else:
            continue
        cap = int(CFG["participation"] * _adv(t, bars[t], actions, nxt) / lot) * lot
        qty = min(qty, cap)
        if qty > 0:
            orders.append({"ticker": t, "side": "sell", "qty": qty, "at": at})
            proceeds += qty * last[t] * (1 - CFG["cost"])

    cash = portfolio["cash"] + (proceeds if CFG.get("same_day_proceeds") else 0.0)
    cash -= CFG["cash_buffer"] * equity
    sector_val = {}
    for t, q in pos.items():
        if t in last:
            sector_val[stocks[t]["sector"]] = sector_val.get(stocks[t]["sector"], 0.0) + q * last[t]
    for t in sorted(targets, key=lambda t: (-scores.get(t, 0), t)):
        if t in halted or t not in last:
            continue
        lot, px = stocks[t]["lot"], last[t] * (1 + CFG["price_buffer"])
        cur = pos.get(t, 0) * last[t]
        want = targets[t] * equity - cur
        if want < CFG["band"] * targets[t] * equity:
            continue
        sec = stocks[t]["sector"]
        room = CFG["sector_target"] * equity - sector_val.get(sec, 0.0)
        budget = min(want, cash, room)
        qty = int(budget / px / lot) * lot
        cap = int(CFG["participation"] * _adv(t, bars[t], actions, nxt) / lot) * lot
        qty = min(qty, cap)
        if qty <= 0:
            continue
        orders.append({"ticker": t, "side": "buy", "qty": qty, "at": at})
        cash -= qty * px * (1 + CFG["cost"]) + CFG["min_fee"]
        sector_val[sec] = sector_val.get(sec, 0.0) + qty * last[t]

    # Examples for the case's validator (never set in the reference config).
    if CFG.get("break") == "format" and day == 3:
        orders.append({"ticker": "NOPE", "side": "buy", "qty": 100})
    if CFG.get("break") == "lot" and day == 3:
        t = sorted(t for t in stocks if t not in halted)[0]
        orders = [o for o in orders if o["ticker"] != t] + [{"ticker": t, "side": "buy", "qty": stocks[t]["lot"] + 1}]
    if CFG.get("break") == "restricted" and day == 3:
        t = sorted(t for t in CFG["restricted"] if t not in halted)[0]
        orders = [o for o in orders if o["ticker"] != t] + [{"ticker": t, "side": "buy", "qty": stocks[t]["lot"]}]
    if CFG.get("break") == "short" and day == 3:
        t = sorted(t for t in stocks if t not in halted and t not in pos)[0]
        orders = [o for o in orders if o["ticker"] != t] + [{"ticker": t, "side": "sell", "qty": stocks[t]["lot"]}]
    STATE.update(day=day + 1, targets=targets, scores=scores, risk=state, peak=risk_peak)
    return {"orders": orders}
