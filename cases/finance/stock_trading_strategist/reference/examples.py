"""Validator examples for finance/stock_trading_strategist: the reference strategy with one deviation each.

Never part of a reference solution. The case copies this file into an example's program/ as strategy.py, next to
the reference strategy (as reference_strategy.py) and a config.json: the reference's config plus an "example"
entry that names the deviation. Each deviation starts from the reference's orders of the day and stays inside
every other rule (board lots, the large-order threshold, the restricted list and the tip, the stock and sector
limits, the cash kept for the withdrawal), so that the example breaks one rule only:

  spend_cash   (cash_withdrawal) from call `from_day` to the payment date, buys stock with the cash kept for the
               client's withdrawal, most liquid names first, until settled cash at the payment falls to half of it;
               in call `rotate_day` (the session before the payment) it also sells holdings to buy them back on
               the date, since those proceeds settle only after it. With `pay` (the payment date, which the case
               passes) it starts before the notice too, for a book that holds more cash than it can spend in the
               sessions between the notice and the payment
  overweight   (position_limit) from call `from_day` to `until_day`, takes the most liquid stock that may be
               bought, and whose sector has room, to `over` above the stock limit, then leaves it to the reference
               to trade back
  oversector   (sector_limit) from call `from_day` to `until_day`, takes a sector whose stocks that may be bought
               can hold it, the most liquid such sector, to `over` above the sector limit with every stock `margin`
               under the stock limit, then leaves it to the reference to trade back
  keep_lot     (restricted_liquidation) holds one lot of the stock compliance adds (`ticker`, bought in the
               session before the addition if the book holds none) until the close-out deadline has passed
  hold_list    (max_drawdown) ranks the stocks in the order of `names[call]` (the case passes, per call, the
               stocks every rule lets it hold, weakest first over the sessions ahead) instead of by their trend,
               and holds only those
"""

import importlib.util
import json
import math
import os

_HERE = os.path.dirname(os.path.abspath(__file__))


def _load(path):
    spec = importlib.util.spec_from_file_location("fdeb2_stock_example_reference", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def make(cfg, reference_path):
    """A strategy object for `cfg`, built on a private copy of the reference module at `reference_path`."""
    ref = _load(reference_path)
    ex = cfg.get("example") or {}
    ids = {}                                          # id of a stock's close series -> ticker, for this call
    rank = {}                                         # ticker -> its score in this call (hold_list)
    if ex.get("kind") == "hold_list":
        ref._score = lambda closes: rank.get(ids.get(id(closes)))

    class Example(ref.Strategy):
        def __init__(self, cfg):
            super().__init__(cfg)
            self.ex = ex
            self.picked = None
            self.done = False

        def on_day(self, day_input):
            ids.clear()
            ids.update({id(b["close"]): t for t, b in day_input["market"]["bars"].items()})
            if self.ex.get("kind") == "hold_list":
                names = self.ex["names"][min(self.day, len(self.ex["names"]) - 1)]
                rank.clear()
                rank.update({t: len(names) - i for i, t in enumerate(names)})
            out = super().on_day(day_input)
            k = self.day - 1                          # this call (the reference counts its calls)
            kind = self.ex.get("kind")
            if kind == "spend_cash":
                self._spend_cash(day_input, out["orders"], k)
            elif kind == "overweight":
                out["orders"] = self._overweight(day_input, out["orders"], k)
            elif kind == "oversector":
                out["orders"] = self._oversector(day_input, out["orders"], k)
            elif kind == "keep_lot":
                out["orders"] = self._keep_lot(day_input, out["orders"], k)
            return out

        # ── the day's book as the reference sees it ─────────────────────────
        def _ctx(self, day_input, orders):
            cfg = self.cfg
            market, pf = day_input["market"], day_input["portfolio"]
            stocks, bars = market["stocks"], market["bars"]
            nxt = market["next_date"]
            c = {"stocks": stocks, "bars": bars, "nxt": nxt, "actions": market.get("corporate_actions", []),
                 "halted": set(market.get("halted", [])),
                 "last": {t: bars[t]["close"][-1] for t in stocks if bars[t]["close"]},
                 "pos": {t: q for t, q in pf["positions"].items() if q > 0}, "equity": pf["equity"]}
            c["reserve"] = 0.0
            if self.withdrawal and nxt <= self.withdrawal["pay"]:
                c["reserve"] = self._withdrawal_amount(c["equity"])
            c["usable"] = pf["cash"] + sum(u["amount"] for u in pf["unsettled"] if u["settles"] <= nxt)
            c["by_pay"] = pf["cash"] + sum(u["amount"] for u in pf["unsettled"]
                                           if self.withdrawal and u["settles"] <= self.withdrawal["pay"])
            weight = cfg["weight"]
            if self.cap_cut:
                weight = min(weight, cfg["stock_cap"] + self.cap_cut[1] - cfg["cap_margin"])
            c["weight"] = weight
            sector_val = {}
            for t, q in c["pos"].items():
                if t in c["last"]:
                    sec = stocks[t]["sector"]
                    sector_val[sec] = sector_val.get(sec, 0.0) + q * c["last"][t]
            for o in orders:
                sec = stocks[o["ticker"]]["sector"]
                sign = 1 if o["side"] == "buy" else -1
                sector_val[sec] = sector_val.get(sec, 0.0) + sign * o["qty"] * c["last"][o["ticker"]]
            c["sector_val"] = sector_val
            c["buys_cost"] = sum(self._cost(o["qty"], c["last"][o["ticker"]]) for o in orders if o["side"] == "buy")
            return c

        def _cost(self, qty, last):
            return qty * last * (1 + self.cfg["price_buffer"]) * (1 + self.cfg["cost"]) + self.cfg["min_fee"]

        def _cap_qty(self, c, t):
            lot = c["stocks"][t]["lot"]
            return int(self.cfg["participation"] * self._adv(t, c["bars"][t], c["actions"], c["nxt"]) / lot) * lot

        def _buyable(self, c):
            """Stocks that may be bought next session, the most liquid (largest order under the threshold) first."""
            banned = self.restricted | self.no_buy | self.closing_out
            names = [t for t in c["stocks"] if t in c["last"] and t not in banned and t not in c["halted"]]
            return sorted(names, key=lambda t: (-self._cap_qty(c, t) * c["last"][t], t))

        # ── the deviations ───────────────────────────────────────────────────
        def _spend_cash(self, day_input, orders, k):
            pay = self.withdrawal["pay"] if self.withdrawal else self.ex.get("pay", "")
            if k < self.ex["from_day"] or day_input["market"]["next_date"] > pay:
                return
            # no sells but the close-out: they would raise cash for the payment, or take a ticker's order
            orders[:] = [o for o in orders if o["side"] == "buy" or o["ticker"] in self.closing_out]
            c = self._ctx(day_input, orders)
            if k == self.ex.get("rotate_day"):
                # the session before the payment: sell holdings to buy back on the payment date (their proceeds
                # settle after it), so the cash goes into stock without adding to any weight
                busy = {o["ticker"] for o in orders}
                for t in sorted(c["pos"], key=lambda t: (-self._cap_qty(c, t) * c["last"].get(t, 0.0), t)):
                    if t in busy or t in c["halted"] or t not in c["last"]:
                        continue
                    qty = min(c["pos"][t], self._cap_qty(c, t))
                    if qty > 0:
                        orders.append({"ticker": t, "side": "sell", "qty": qty, "at": self.cfg.get("at", "open")})
                c = self._ctx(day_input, orders)
            base = c["equity"] - c["reserve"]           # the weights are of the equity after the payout
            budget = min(c["usable"] - c["buys_cost"] - self.cfg["cash_buffer"] * c["equity"],
                         c["by_pay"] - c["buys_cost"] - 0.5 * c["reserve"])
            by_ticker = {o["ticker"]: o for o in orders}
            for t in self._buyable(c):
                o = by_ticker.get(t)
                if budget <= 0:
                    break
                if o is not None and o["side"] == "sell":
                    continue
                lot, last = c["stocks"][t]["lot"], c["last"][t]
                have = c["pos"].get(t, 0) + (o["qty"] if o else 0)
                sec = c["stocks"][t]["sector"]
                room = min(c["weight"] * base - have * last,
                           self.cfg["sector_target"] * base - c["sector_val"].get(sec, 0.0), budget)
                qty = min(int(room / (last * (1 + self.cfg["price_buffer"])) / lot) * lot,
                          self._cap_qty(c, t) - (o["qty"] if o else 0))
                if qty <= 0:
                    continue
                if o is None:
                    o = {"ticker": t, "side": "buy", "qty": 0, "at": self.cfg.get("at", "open")}
                    orders.append(o)
                    by_ticker[t] = o
                o["qty"] += qty
                budget -= self._cost(qty, last)
                c["sector_val"][sec] = c["sector_val"].get(sec, 0.0) + qty * last

        def _overweight(self, day_input, orders, k):
            if not self.ex["from_day"] <= k <= self.ex["until_day"] or self.done:
                return orders
            c = self._ctx(day_input, [])                  # the holdings at the close, before the day's orders
            cap = self.cfg["stock_cap"] + (self.cap_cut[1] if self.cap_cut and self.cap_cut[0] <= c["nxt"] else 0.0)
            t = self.picked
            if t is not None and c["pos"].get(t, 0) * c["last"].get(t, 0.0) > cap * c["equity"]:
                self.done = True                          # over the limit at the close of its last buy
                return orders
            if c["reserve"] or (self.withdrawal and c["nxt"] == self.withdrawal["pay"]):
                return orders                             # not while cash is kept for the withdrawal
            goal = (cap + self.ex["over"]) * c["equity"]
            if t is None:                                 # sector value counted before the day's sells: a margin
                for x in self._buyable(c):
                    sec = c["stocks"][x]["sector"]
                    extra = goal - c["pos"].get(x, 0) * c["last"][x]
                    if c["sector_val"].get(sec, 0.0) + extra <= (self.ex["sector_cap"] - 0.02) * c["equity"]:
                        t = self.picked = x
                        break
            if t is None or t not in self._buyable(c):
                return orders
            lot, last = c["stocks"][t]["lot"], c["last"][t]
            need = int(math.ceil((goal - c["pos"].get(t, 0) * last) / last / lot)) * lot
            cash = c["usable"] - self.cfg["cash_buffer"] * c["equity"]
            qty = min(need, self._cap_qty(c, t), int(cash / (last * (1 + self.cfg["price_buffer"])) / lot) * lot)
            if qty <= 0:
                return orders
            # the reference's sells of the day stay; its buys make way (cash and sector room)
            others = [o for o in orders if o["side"] == "sell" and o["ticker"] != t]
            return others + [{"ticker": t, "side": "buy", "qty": qty, "at": self.cfg.get("at", "open")}]

        def _oversector(self, day_input, orders, k):
            if not self.ex["from_day"] <= k <= self.ex["until_day"] or self.done:
                return orders
            c = self._ctx(day_input, [])                  # the holdings at the close, before the day's orders
            sector_cap, eq = self.ex["sector_cap"], c["equity"]
            if self.picked is not None and c["sector_val"].get(self.picked, 0.0) > sector_cap * eq:
                self.done = True                          # over the limit at the close of its last buy
                return orders
            if c["reserve"] or (self.withdrawal and c["nxt"] == self.withdrawal["pay"]):
                return orders                             # not while cash is kept for the withdrawal
            cap = self.cfg["stock_cap"] + (self.cap_cut[1] if self.cap_cut and self.cap_cut[0] <= c["nxt"] else 0.0)
            w = cap - self.ex["margin"]                   # each stock stays under the stock limit
            goal = (sector_cap + self.ex["over"]) * eq
            buyable = self._buyable(c)

            def value(t):
                return c["pos"].get(t, 0) * c["last"].get(t, 0.0)
            if self.picked is None:                       # the sector whose names reach the goal in the fewest sessions
                best = None
                for sec in sorted({c["stocks"][t]["sector"] for t in buyable}):
                    names = [t for t in buyable if c["stocks"][t]["sector"] == sec]
                    rooms = [(max(0.0, w * eq - value(t)), self._cap_qty(c, t) * c["last"][t]) for t in names]
                    need = goal - c["sector_val"].get(sec, 0.0)
                    for n in range(1, self.ex["until_day"] - k + 2):
                        if sum(min(room, n * speed) for room, speed in rooms) >= need:
                            if best is None or n < best[0]:
                                best = (n, sec)
                            break
                self.picked = best and best[1]
            sec = self.picked
            if sec is None:
                return orders
            names = [t for t in buyable if c["stocks"][t]["sector"] == sec]
            need, cash = goal - c["sector_val"].get(sec, 0.0), c["usable"] - self.cfg["cash_buffer"] * eq
            buys = []
            for t in names:
                lot, last = c["stocks"][t]["lot"], c["last"][t]
                amount = min(w * eq - value(t), need, cash)
                qty = min(int(amount / (last * (1 + self.cfg["price_buffer"])) / lot) * lot, self._cap_qty(c, t))
                if qty <= 0:
                    continue
                buys.append({"ticker": t, "side": "buy", "qty": qty, "at": self.cfg.get("at", "open")})
                need -= qty * last
                cash -= self._cost(qty, last)
                if need <= 0:
                    break
            if not buys:
                return orders
            # the reference's sells outside the sector stay; its buys make way (cash, and no other sector bought)
            others = [o for o in orders if o["side"] == "sell" and c["stocks"][o["ticker"]]["sector"] != sec]
            return others + buys

        def _keep_lot(self, day_input, orders, k):
            t, add_day, deadline = self.ex["ticker"], self.ex["add_day"], self.ex["deadline_day"]
            if not add_day - 1 <= k <= deadline:
                return orders
            market, pf = day_input["market"], day_input["portfolio"]
            lot = market["stocks"][t]["lot"]
            held = pf["positions"].get(t, 0)
            rest = [o for o in orders if o["ticker"] != t]
            mine = [o for o in orders if o["ticker"] == t]
            if held >= lot:                               # sell all but one lot
                if mine and mine[0]["side"] == "sell":
                    qty = min(mine[0]["qty"], held - lot)
                    return rest + ([dict(mine[0], qty=qty)] if qty > 0 else [])
                return orders
            if k == add_day - 1 and not mine and t not in market.get("halted", []):
                return orders + [{"ticker": t, "side": "buy", "qty": lot, "at": self.cfg.get("at", "open")}]
            return orders

    return Example(cfg)


_INSTANCE = None


def on_day(day):
    global _INSTANCE
    if _INSTANCE is None:
        with open(os.path.join(_HERE, "config.json"), encoding="utf-8") as f:
            cfg = json.load(f)
        _INSTANCE = make(cfg, os.path.join(_HERE, "reference_strategy.py"))
    return _INSTANCE.on_day(day)
