# Stock Trading Strategist — `finance/stock_trading_strategist`

The portfolio manager of a small proprietary book on the fictional Arden Exchange asks for "a trading
strategy that beats just holding the index". The agent gets a year of synthetic history for 16 stocks in 4
sectors (250 sessions, 2 June 2025 to 15 May 2026: open, the price 10 minutes after the open, close and
volume per stock, plus the index, the corporate actions, the trading halts and the quarterly earnings
announcements) and delivers a **program**, `program/strategy.py:on_day`. The evaluator replays the **hidden
80 sessions that follow** (18 May to 4 September 2026), generated from the same world: after each close it
calls the strategy with the market so far and the book's state, then executes the returned orders in the
next session under the exchange's and the client's rules. The book starts with 10,000,000 in cash. All prices
are synthetic and the exchange is country-neutral (its rules are stated, not borrowed from a real market).

The case has nine settings, 3 tiers × 3 rule sets. **The world, the data files, the hidden period and the
request are the same in all of them**; the agent's view is byte-identical (the validator checks it). The
tier decides how the engine executes and which client rules are checked; the rule set decides the values of
those rules. Both live only in the hidden requirements (which the simulated client answers from) and in the
evaluator. The program cannot ask anything at run time, so the agent has to learn the restricted list and
the limits from the client and build them into the program. Evaluation runs a tier under A, B and C and
reports the mean. The engagement knobs (full spec vs. clarify first, client persona, data noise, events)
apply on top, as for every case (see [cases/README.md](../../README.md)).

## The world (every setting)

16 stocks (QRVL, ZENT, XIPH, OMNY in Technology; KOVA, BRAX, PYRO, GLAC in Energy; MEDQ, VYTA, CURA, NEXO in
Health care; LUMO, TARK, FERN, DUNE in Consumer), each with a board lot (100, or 10 above 150) and a half
spread. Facts that are in the data and the replay whatever the setting:

- **XIPH's 5-to-1 consolidation** on 7 May 2026: prices in the data adjusted, **volumes raw** (5× too high
  before that date in today's shares).
- **Trading halts**: CURA and BRAX in the history; PYRO for 4 sessions in June (reopens −16%) and LUMO for 2
  in August (+9%) in the hidden period: no bars, orders rejected.
- **Earnings** once a quarter per stock after the close; the reaction splits 40% overnight gap, 30% first 10
  minutes, 30% over 10 sessions.
- **OMNY 2-for-1 split** on 3 July 2026 (announced 10 sessions ahead in `market.corporate_actions`).
- A **sell-off** from 6 July to 12 August: the cap-weighted index draws down 21.5%; holding it from the first
  hidden session (whole lots, costs, net of liquidation) ends about 12% down.

## Tiers

| | easy | medium | hard |
|---|---|---|---|
| **Engine** | Simple mode: fills at next session's `p10` ± half spread, or the opening auction at `open` with no spread; commission 0.04%, min 20; board lots; cash only, no shorts; a buy above usable cash is rejected whole; sells before buys; sale proceeds usable the same session | + 0.2% sales tax on sells; proceeds settle **T+2** | + **market impact** 0.02 × qty / session volume (at the open too) |
| **Rules** | `order_format`, `lot_size`, `no_short_selling` (physical); `restricted_list` (contractual); `no_first_10_minutes` (business policy, bendable) | + `position_limit`, `sector_limit` (at the close of a session in which the book bought), `volume_participation` (each order ≤ x% of the 20-session average volume in today's shares) (contractual) | + `max_drawdown` (closing equity never more than x% below its running peak) (contractual) |
| **Out of scope this round** (said in the requirements) | Limits, order size, drawdown | Drawdown | — |
| **Quality (higher is better)** | Final net equity on 4 September: cash + unsettled proceeds + positions at the last close net of commission | Same, also net of sales tax | Same |
| **Clarification targets** | 12: interface, evaluation period, fills, costs, simple engine, lots and cash, restricted list, first 10 minutes, objective, halts, upcoming split, earnings | 15: easy without simple engine, + settlement and tax, raw volumes, position limits, order size | 17: medium + market impact, max drawdown |
| **What it tests** | Writing a deterministic, stateful strategy against an engine contract; costs and sizing in lots; a compliance list; when a desk habit is worth an exception | Cash management under T+2, compliance margins, adjusting volumes but not prices, halted positions | Trading out of a regime change inside a hard risk mandate, impact-aware sizing |

## Rule sets

| | A | B | C |
|---|---|---|---|
| Restricted list (no buy orders; all tiers) | MEDQ, ZENT | NEXO, PYRO | BRAX, DUNE |
| Stock limit after buying (medium+) | 15% | 10% | 20% |
| Sector limit after buying (medium+) | 40% | 25% | 50% |
| Order size, % of 20-session average volume (medium+) | 10% | 15% | 5% |
| Maximum drawdown (hard) | 15% | 10% | 12% |

The restricted list is the non-nested parameter: it changes *which* stocks may be bought, and every rule
set's reference buys names on both other lists, so within each tier every reference is invalid under the
other two rule sets (`restricted_list`). The limits are deliberately not nested either (B is tight on
stocks and sectors but loose on order size, C the opposite; the drawdown limit is tightest in B).

## Reference numbers (seed 101)

The reference (`reference/strategy.py` + a per-setting `config.json`) is cross-sectional momentum: every 5
sessions it ranks the stocks that are not restricted by their 60-session return (skipping the last 5) over
volatility and holds the top ones, at most two per sector in easy; every session it trades toward those
targets in board lots, with a 2% price buffer for cash. Easy: 4 names × 24%, sale proceeds reused at once.
Medium and hard: names at the stock limit − 2 points, sectors at the sector limit − 4 points, orders at 95%
of the order-size cap on split-adjusted volumes, buys from settled cash only. Every tier has a risk switch
(all to cash 6% below the peak since it last went in, `dd_stop` below the all-time peak — 10% in easy and
medium, the mandate − 5 points in hard — or when the index is down 6% over 20 sessions and below its
20-session mean; back in when the index recovers). It keeps the 10-minute habit and ignores earnings. State
lives in a module variable (one process per replay).

| Setting | Reference final net equity | vs index held (8,827,053 easy; 8,809,552 medium/hard) | Max drawdown | Bending `no_first_10_minutes` (same strategy, all orders at the open) | Headroom: oracle ranking (true next-5-session return, same rules) |
|---|---|---|---|---|---|
| easy A | 10,385,707 | +17.7% | 10.6% | +0.84% | +36.8% |
| easy B | 10,189,279 | +15.4% | 11.0% | +1.83% | +35.5% |
| easy C | 10,274,636 | +16.4% | 9.8% | +0.87% | +34.6% |
| medium A | 9,801,485 | +11.3% | 11.6% | +1.17% | +19.6% |
| medium B | 10,022,637 | +13.8% | 7.4% | +0.99% | +13.1% |
| medium C | 10,049,530 | +14.1% | 8.4% | +0.26% | +10.3% |
| hard A | 9,816,696 | +11.4% | 11.0% (limit 15%) | +0.17% | +17.8% |
| hard B | 10,063,807 | +14.2% | 6.4% (limit 10%) | +0.95% | +11.7% |
| hard C | 10,039,283 | +14.0% | 7.7% (limit 12%) | +0.27% | +9.3% |

Per-tier means over A/B/C:

| | easy | medium | hard |
|---|---|---|---|
| Reference final net equity | 10,283,208 | 9,957,884 | 9,973,262 |
| Index bought on day 1 and held | 8,827,053 | 8,809,552 | 8,809,552 |
| Bending the 10-minute habit | +1.18% | +0.81% | +0.47% |
| Oracle headroom | +35.6% | +14.3% | +12.9% |

How the rules bind (same seed, reference variants; each is also a validator example that breaks only its rule):

| Rule or fact | Variant | Effect |
|---|---|---|
| `restricted_list` | the reference of another rule set | invalid in every tier and every pair (the validator's distinctness check) |
| `position_limit` | 4 names at the stock limit + 4 points, one per sector | breaches in all six medium/hard settings (+0.4% to +3.6% equity if allowed, except −1.0% in hard B) |
| `sector_limit` | every stock of one unrestricted sector at the stock limit − 2 points | breaches in all six (−3.7% to +2.2%) |
| `volume_participation` | order cap 1.6× the limit | breaches in all six; removing the cap entirely: +0.8% (medium A), −0.1% to −2.0% elsewhere |
| raw-volume trap | cap computed on raw volumes (XIPH's pre-consolidation volumes 5× too high) | 1 order over the cap in A, 5 in C (invalid); none in B, whose 15% cap does not bind on XIPH |
| `max_drawdown` | hard reference without its risk switch | drawdown 15.2% (A), 11.2% (B), 19.6% (C): invalid in each, and −3.7% / −3.9% / −11.4% equity |

Robustness over 16 seeds (101–116) × 3 rule sets with the same reference configs: the reference beats
holding the index in 40, 36 and 35 of 48 runs (easy, medium, hard); it is valid in all 48 hard runs (worst
drawdown 11.0%, under every rule set's mandate). Bending the 10-minute habit pays in 35, 38 and 40 of 48
(mean +0.5%, +0.4%, +0.4% of final equity).

## Notes

- **One process per replay.** The case drives the program with `casekit.program_session`: the engine loads
  `strategy.py` once and makes the 80 calls in the same isolated process, so the strategy keeps its state in
  module variables (no `memo`). `validate-case` (9 settings: reference twice, empty submission, one example
  per rule plus its relaxed re-score, and the 18 cross-rule-set evaluations; about 150 replays) takes about
  **60 seconds**.
- Quality is the ratio of final equities, so it is compressed: holding the index scores about 0.85–0.88 of
  the reference, and a 1% better strategy scores 1.01. Validity is where most agents will be separated (the
  order contract, lots, the restricted list, the limits, the drawdown, and the raw-volume trap).
- The world is a factor model: market, AR(1) sector and stock drifts (the momentum the reference exploits),
  idiosyncratic noise, each day split into an overnight gap, the first 10 minutes and the rest of the session,
  plus halts, corporate actions, earnings and the sell-off from their own random streams. Tickers and the
  exchange are invented.
- `validate-case` checks every setting: deterministic data in five locales, the reference at quality 1.0
  (run twice for determinism), one program per rule of the setting that breaks only that rule, that the rule
  sets lead to different solutions, and that the agent's prompt and workspace are identical in all nine.
