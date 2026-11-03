"""Reference strategy for finance/stock_trading_strategist (copied into program/ with a config.json).

Cross-sectional momentum inside the client's instructions and limits, standard library only. Each call:

  * read the day's notices that the round's rules use: a stock added to the restricted list (never buy it
    again; sell it out as fast as the large-order threshold allows), and from medium a client cash withdrawal
    (the amount is the agreement's percentage of its basis; reserve it, raise it pro rata as soon as it is
    announced, early enough for T+2, and size the weights on equity after the payout) and a cut of the single-stock limit (trade down to the new limit from
    the notice on); in hard a note passing on an inside tip makes its stock untouchable for buying, and a note
    asking for more risk is ignored;
  * report the status table at the close that just happened: stock and sector weights, buying power for the
    next session (net of the withdrawal not yet paid), drawdown from the peak (payouts added back);
  * every REBALANCE sessions, rank the stocks by their 60-session return (skipping the last 5) over
    volatility and hold the best ones, each at the target weight or at most 80% of what could be sold out
    before the close-out deadline in orders under the threshold (any stock may be the next one restricted),
    within the sector budget, until the book is invested;
  * trade toward those targets: sells first, buys with the cash that is usable next session (settled cash and
    proceeds settling then, less the withdrawal reserve), in board lots, every order within the large-order
    threshold (average volume in today's shares), with a margin under the stock and sector limits;
  * a risk switch: go to cash when the book's drawdown or the index trend says so.

The engine calls on_day in one process for the whole run, so the state lives in one Strategy object. The
behaviour is set by config.json (written per setting by the case); a few switches exist only so the case can
build examples that break one rule each.
"""

import json
import math
import os

CAPITAL = 10_000_000.0


def _effective_ratio(ticker, bar_date, actions, next_date):
    """Shares now per share at bar_date: product of the split ratios that took effect after that bar."""
    r = 1.0
    for a in actions:
        if a["ticker"] == ticker and bar_date < a["ex_date"] <= next_date:
            r *= a["ratio"]
    return r


def _score(closes):
    if len(closes) < 66:
        return None
    rets = [math.log(closes[i] / closes[i - 1]) for i in range(len(closes) - 60, len(closes))]
    mu = sum(rets) / len(rets)
    vol = math.sqrt(sum((x - mu) ** 2 for x in rets) / (len(rets) - 1)) or 1e-6
    return math.log(closes[-6] / closes[-66]) / (vol * math.sqrt(60))


class Strategy:
    def __init__(self, cfg):
        self.cfg = cfg
        self.day = 0
        self.peak = CAPITAL               # highest closing equity plus payouts
        self.risk_peak = None
        self.risk = "on"
        self.expo = 1.0
        self.targets_rebuilt = False
        self.targets = None
        self.scores = {}
        self.restricted = set(cfg.get("restricted", []))
        self.closing_out = set()          # added to the restricted list: sell all of it
        self.no_buy = set()               # hard: stocks of an inside tip
        self.withdrawal = None            # {"pct", "pay", "notice_equity"}
        self.cap_cut = None               # (effective_date, points)

    # ── notices ─────────────────────────────────────────────────────────────
    def _notices(self, notices, equity):
        cfg = self.cfg
        for n in notices:
            kind = n.get("type")
            if kind == "restricted_list_add":
                self.restricted.add(n["ticker"])
                self.closing_out.add(n["ticker"])
            elif kind == "cash_withdrawal" and cfg["medium"] and not cfg.get("ignore_withdrawal"):
                self.withdrawal = {"pct": cfg["withdrawal_pct"] / 100, "pay": n["payment_date"], "notice_equity": equity}
            elif kind == "risk_limit_change" and cfg["medium"] and not cfg.get("ignore_cut"):
                self.cap_cut = (n["effective_date"], n["stock_limit_change_points"] / 100)
            elif kind == "note" and cfg["hard"] and n.get("request") == "buy" and n.get("ticker"):
                self.no_buy.add(n["ticker"])

    def _withdrawal_amount(self, equity):
        """The payout as it stands at this close: the agreement's percentage (the notice gives only the date) of
        its basis: capital, the notice day's equity, or the equity at the close before the payment date (today's
        until then)."""
        w = self.withdrawal
        basis = self.cfg["withdrawal_basis"]
        base = CAPITAL if basis == "capital" else w["notice_equity"] if basis == "notice" else equity
        return w["pct"] * base

    # ── the status table ────────────────────────────────────────────────────
    def _status(self, stocks, last, portfolio, nxt, reserve):
        equity = portfolio["equity"]
        paid = sum(w["amount"] for w in portfolio.get("withdrawals", []))
        self.peak = max(self.peak, equity + paid)
        weights, sectors = {}, {}
        for t, q in portfolio["positions"].items():
            if q > 0 and t in last:
                w = 100 * q * last[t] / equity
                weights[t] = round(w, 4)
                sec = stocks[t]["sector"]
                sectors[sec] = sectors.get(sec, 0.0) + w
        usable = portfolio["cash"] + sum(u["amount"] for u in portfolio["unsettled"] if u["settles"] <= nxt)
        return {"stock_weights": weights, "sector_weights": {k: round(v, 4) for k, v in sectors.items()},
                "buying_power": round(max(0.0, usable - reserve), 2),
                "drawdown_pct": round(100 * (1 - (equity + paid) / self.peak), 4)}

    # ── the risk switch ─────────────────────────────────────────────────────
    def _risk_state(self, market, value, dd_all):
        """"on" or "off", and the peak of `value` (equity plus payouts) since the book last went back in.

        Off when the book is dd_off below that peak, or dd_stop below its all-time peak, or the index fell
        trend_off in 20 sessions and is below its 20-session mean; back on when the index is above its mean and
        up over 20 sessions."""
        cfg = self.cfg
        if not cfg.get("risk_switch"):
            return "on", value
        peak = max(self.risk_peak or value, value)
        level = market["index"]["level"]
        ma = sum(level[-20:]) / len(level[-20:])
        r20 = level[-1] / level[-21] - 1 if len(level) > 21 else 0.0
        if self.risk == "on":
            if 1 - value / peak > cfg["dd_off"] or dd_all > cfg["dd_stop"] or (r20 < cfg["trend_off"] and level[-1] < ma):
                return "off", value
            return "on", peak
        if level[-1] > ma and r20 > 0:
            return "on", value
        return "off", value

    def _exposure(self, state, dd_all):
        """Share of the target weights to hold: none when off; in hard, scaled down so that a further stress
        loss still keeps the book inside the drawdown mandate."""
        cfg = self.cfg
        if state != "on":
            return cfg["defensive"]
        if cfg.get("max_dd") is None:
            return 1.0
        return max(0.0, min(1.0, (cfg["max_dd"] - cfg["dd_margin"] - dd_all) / cfg["stress"]))

    def _adv(self, ticker, bars, actions, nxt, n=20):
        vols, dates = bars["volume"][-n:], bars["date"][-n:]
        if not vols:
            return 0.0
        if self.cfg.get("raw_volume"):
            return sum(vols) / len(vols)
        return sum(v * _effective_ratio(ticker, d, actions, nxt) for v, d in zip(vols, dates)) / len(vols)

    def _liquid_value(self, ticker, bars, actions, nxt, price):
        """The largest holding that can be closed out within the deadline in orders under the threshold."""
        if not self.cfg.get("liq_days"):
            return float("inf")
        return self.cfg["liq_days"] * self.cfg["participation"] * self._adv(ticker, bars, actions, nxt) * price

    # ── one session ─────────────────────────────────────────────────────────
    def on_day(self, day_input):
        cfg = self.cfg
        market, portfolio = day_input["market"], day_input["portfolio"]
        stocks, bars = market["stocks"], market["bars"]
        halted = set(market.get("halted", []))
        actions = market.get("corporate_actions", [])
        nxt = market["next_date"]
        pos = {t: q for t, q in portfolio["positions"].items() if q > 0}
        equity = portfolio["equity"]
        last = {t: bars[t]["close"][-1] for t in stocks if bars[t]["close"]}
        self._notices(day_input.get("notices", []), equity)

        reserve = 0.0
        if self.withdrawal and nxt <= self.withdrawal["pay"] and self.day >= cfg.get("wd_from", 0):
            reserve = self._withdrawal_amount(equity)      # (wd_from: validator example acting at the last moment)
        status = self._status(stocks, last, portfolio, nxt, reserve)
        base = equity - reserve                    # what the weights are of once the withdrawal is paid
        paid = sum(w["amount"] for w in portfolio.get("withdrawals", []))
        dd_all = 1 - (equity + paid) / self.peak

        state, risk_peak = self._risk_state(market, equity + paid, dd_all)
        expo = self._exposure(state, dd_all)
        weight = cfg["weight"]
        if self.cap_cut:
            weight = min(weight, cfg["stock_cap"] + self.cap_cut[1] - cfg["cap_margin"])
        banned = self.restricted | self.no_buy
        if (self.targets is None or self.day % cfg["rebalance"] == 0 or state != self.risk
                or abs(expo - self.expo) > 0.1):
            scores = {}
            for t, b in bars.items():
                s = _score(b["close"])
                if s is not None and (s > 0 or not cfg.get("positive_only")) and t not in halted and t not in banned:
                    scores[t] = s
            # Best first, each name at the target weight or the largest holding that can still be closed out in
            # time, within the sector budget, until the book is invested.
            targets, per_sector, sec_w, total = {}, {}, {}, 0.0
            for t in sorted(scores, key=lambda t: (-scores[t], t)):
                sec = stocks[t]["sector"]
                if len(targets) >= cfg["top"] or per_sector.get(sec, 0) >= cfg["per_sector"]:
                    continue
                liq = cfg.get("liq_fill", 0.8) * self._liquid_value(t, bars[t], actions, nxt, last[t]) / base
                w = min(weight, liq, cfg["sector_target"] - sec_w.get(sec, 0.0), cfg["invest"] - total)
                if w < cfg["min_weight"]:
                    continue
                per_sector[sec] = per_sector.get(sec, 0) + 1
                sec_w[sec] = sec_w.get(sec, 0.0) + w
                total += w
                targets[t] = w * expo
            if cfg.get("break") == "sector":
                # Example for the case's validator: every stock of one sector that may be bought.
                secs = sorted({stocks[t]["sector"] for t in stocks})
                sec = secs[cfg.get("sector_pick", 0) % len(secs)]
                targets = {t: weight * expo for t in sorted(stocks) if stocks[t]["sector"] == sec and t not in banned}
            if cfg.get("break") == "pressure" and self.day >= cfg.get("pressure_day", 10 ** 9):
                top2 = sorted(scores, key=lambda t: (-scores[t], t))[:2]
                targets = {t: 0.45 for t in top2}
            self.targets, self.scores = targets, scores
            self.targets_rebuilt = True
        else:
            self.targets_rebuilt = False
        targets = {t: w if cfg.get("break") == "pressure" else min(w, weight * expo)
                   for t, w in self.targets.items() if t not in banned}
        scores = self.scores

        orders, proceeds = [], 0.0
        at = cfg.get("at", "open")
        # Cash still to raise for the withdrawal: what usable cash by the payment date lacks.
        need = 0.0
        if reserve:
            by_pay = portfolio["cash"] + sum(u["amount"] for u in portfolio["unsettled"]
                                             if u["settles"] <= self.withdrawal["pay"])
            need = max(0.0, reserve * cfg["reserve_buffer"] - by_pay)
        invested = sum(pos[t] * last[t] for t in pos if t in last and t not in halted) or 1.0
        for t in sorted(pos):
            if t in halted or t not in last or (t in self.closing_out and cfg.get("ignore_liquidation")):
                continue
            lot = stocks[t]["lot"]
            cur = pos[t] * last[t]
            cap = int(cfg["participation"] * self._adv(t, bars[t], actions, nxt) / lot) * lot
            if t in self.closing_out:
                qty = min(pos[t], cap)             # close out as fast as the order-size threshold allows
            else:
                want = targets.get(t, 0.0) * base
                liq = self._liquid_value(t, bars[t], actions, nxt, last[t])
                if want <= 0:
                    qty = pos[t]
                elif (cur > want * (1 + cfg["band"]) or (self.cap_cut and cur > want + lot * last[t])
                      or cur > cfg.get("liq_trim", 0.95) * liq):
                    want = min(want, cfg.get("liq_fill", 0.8) * liq)
                    qty = int(math.ceil((cur - want) / last[t] / lot)) * lot
                else:
                    qty = 0
                if need > 0:                       # raise the withdrawal pro rata to the holdings
                    extra = need * cur / invested * 1.02
                    qty = max(qty, int(math.ceil(extra / last[t] / lot)) * lot)
                qty = min(qty, pos[t], cap)
            if qty > 0:
                orders.append({"ticker": t, "side": "sell", "qty": qty, "at": at})
                proceeds += qty * last[t] * (1 - cfg["cost"])

        cash = portfolio["cash"]
        if cfg["same_day_proceeds"]:
            cash += proceeds
        else:
            cash += sum(u["amount"] for u in portfolio["unsettled"] if u["settles"] <= nxt)
        cash -= cfg["cash_buffer"] * equity + reserve * cfg["reserve_buffer"]
        spend = cfg.get("break") == "spend" and cfg.get("spend_from", -1) <= self.day <= cfg.get("spend_day", -1)
        if spend:
            # Validator example: spend the cash set aside for the withdrawal on the payment date.
            cash += reserve * cfg["reserve_buffer"]
            targets = {t: cfg.get("spend_weight", 0.4) * weight for t in stocks if t not in banned and t not in halted}
        sector_val = {}
        for t, q in pos.items():
            if t in last:
                sector_val[stocks[t]["sector"]] = sector_val.get(stocks[t]["sector"], 0.0) + q * last[t]
        for o in orders:
            sec = stocks[o["ticker"]]["sector"]
            sector_val[sec] -= o["qty"] * last[o["ticker"]]
        selling = {o["ticker"] for o in orders}
        for t in sorted(targets, key=lambda t: (-scores.get(t, 0), t)):
            if t in halted or t not in last or t in selling:
                continue
            lot, px = stocks[t]["lot"], last[t] * (1 + cfg["price_buffer"])
            cur = pos.get(t, 0) * last[t]
            liq = float("inf") if spend else self._liquid_value(t, bars[t], actions, nxt, last[t])
            want = min(targets[t] * base, cfg.get("liq_fill", 0.8) * liq) - cur
            if want < cfg["band"] * targets[t] * base and not spend:
                continue
            sec = stocks[t]["sector"]
            room = cfg["sector_target"] * base - sector_val.get(sec, 0.0)
            budget = min(want, cash, room)
            qty = int(budget / px / lot) * lot
            cap = int(cfg["participation"] * self._adv(t, bars[t], actions, nxt) / lot) * lot
            qty = min(qty, cap)
            if qty <= 0:
                continue
            orders.append({"ticker": t, "side": "buy", "qty": qty, "at": at})
            cash -= qty * px * (1 + cfg["cost"]) + cfg["min_fee"]
            sector_val[sec] = sector_val.get(sec, 0.0) + qty * last[t]

        # Examples for the case's validator (never set in the reference config).
        brk, d = cfg.get("break"), self.day
        if brk == "format" and d == 3:
            orders.append({"ticker": "NOPE", "side": "buy", "qty": 100})
        if brk == "lot" and d == 3:
            t = sorted(t for t in stocks if t not in halted and t not in banned)[0]
            orders = [o for o in orders if o["ticker"] != t] + [{"ticker": t, "side": "buy", "qty": stocks[t]["lot"] + 1}]
        if brk == "restricted" and d == 3:
            t = sorted(t for t in cfg["restricted"] if t not in halted)[0]
            orders = [o for o in orders if o["ticker"] != t] + [{"ticker": t, "side": "buy", "qty": stocks[t]["lot"]}]
        if brk == "short" and d == 3:
            t = sorted(t for t in stocks if t not in halted and t not in pos)[0]
            orders = [o for o in orders if o["ticker"] != t] + [{"ticker": t, "side": "sell", "qty": stocks[t]["lot"]}]
        if brk == "tip" and d == cfg.get("tip_day", -1):
            t = sorted(self.no_buy)[0]
            orders = [o for o in orders if o["ticker"] != t] + [{"ticker": t, "side": "buy", "qty": stocks[t]["lot"]}]
        if brk == "hold" and d == cfg.get("hold_day", -1):
            t = cfg["hold_ticker"]
            if t not in pos and t not in {o["ticker"] for o in orders}:
                orders.append({"ticker": t, "side": "buy", "qty": stocks[t]["lot"]})
        self.day += 1
        self.risk, self.risk_peak = state, risk_peak
        if self.targets_rebuilt:
            self.expo = expo
        return {"orders": orders, "status": status}


_INSTANCE = None


def on_day(day):
    global _INSTANCE
    if _INSTANCE is None:
        here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(here, "config.json"), encoding="utf-8") as f:
            _INSTANCE = Strategy(json.load(f))
    return _INSTANCE.on_day(day)
