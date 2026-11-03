"""Baseline for finance/stock_trading_strategist (copied into program/ with a config.json).

What the desk has without an engineer: the book stays in cash and places no orders, and the daily status table
is filled in from the engine's input (no holdings, buying power = settled cash plus proceeds usable by next_date,
less, from medium, the client withdrawal announced and not yet paid; drawdown from the peak of equity plus
payouts). It keeps to every rule in every setting and scores what doing nothing earns: the cash's excess over
the index plus a perfect table. config.json says whether the withdrawal is in force (medium) and what the
client's agreement sets: its percentage and basis (the notice gives only the payment date).
"""

import json
import os

CAPITAL = 10_000_000.0

with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json"), encoding="utf-8") as _f:
    CFG = json.load(_f)

_state = {"peak": CAPITAL, "withdrawal": None}


def on_day(day):
    market, portfolio = day["market"], day["portfolio"]
    equity, nxt = portfolio["equity"], market["next_date"]
    for n in day.get("notices", []):
        if n.get("type") == "cash_withdrawal" and CFG["medium"]:
            _state["withdrawal"] = {"pct": CFG["withdrawal_pct"] / 100, "pay": n["payment_date"],
                                    "notice_equity": equity}
    reserve = 0.0
    w = _state["withdrawal"]
    if w and nxt <= w["pay"]:
        basis = CFG["withdrawal_basis"]
        reserve = w["pct"] * (CAPITAL if basis == "capital" else w["notice_equity"] if basis == "notice" else equity)
    paid = sum(x["amount"] for x in portfolio.get("withdrawals", []))
    _state["peak"] = max(_state["peak"], equity + paid)
    usable = portfolio["cash"] + sum(u["amount"] for u in portfolio["unsettled"] if u["settles"] <= nxt)
    return {"orders": [],
            "status": {"stock_weights": {}, "sector_weights": {}, "buying_power": round(max(0.0, usable - reserve), 2),
                       "drawdown_pct": round(100 * (1 - (equity + paid) / _state["peak"]), 4)}}
