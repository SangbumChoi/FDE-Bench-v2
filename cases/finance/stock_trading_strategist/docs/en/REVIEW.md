# Review — `finance/stock_trading_strategist`

Findings of the case review (F1–F10) and what this change did about each. Numbers are at the public world seed
101 unless stated; "q" is the normalized quality (baseline 0, reference 1). Comments welcome on the open
proposals.

### F1 — The case only works on its shipped seed (high, confirmed)

Before commit b2c55c0 the return component divided by the reference's excess over the index with no floor, and
`_reference_run` asserted that excess was positive. On seeds such as 0, 2, 3 and 103 the reference trails the index
(seed 103: −3% to −23%), so the evaluator raised and every submission scored 0. On seeds 102 and 105 an all-cash
program beat the reference (objective 1.47–2.95 and 0.88–7.44). That blocks the private-seed contamination defence.

**Status:** open — b2c55c0 fixed the crash: there is no assertion now, and the yardstick drops to 5% of the capital
below the reference's final value when the reference leads the index by less. `validate-case --world-seeds
1,2,3,7,42` passes: the reference is valid at q = 1.0 and every rule has a clean example on all five seeds. The
second half still reproduces. In many worlds the reference ends below cash, so the new all-cash baseline beats it.
I checked 10 other seeds. The baseline's objective exceeds the reference's 1.0 in 8 of 9 settings on seed 3, 9 of 9
on seed 7, 6 of 9 on seed 42, 6 of 9 on seed 0, and 9 of 9 on seeds 102 and 105 (1.01–3.10). It stays below on
seeds 1, 2, 103 and 104. When this happens the framework drops the baseline and scores the plain ratio, so on such
a private seed a do-nothing program gets full quality credit. `check_world_seed` checks the reference, not the
baseline, so validate-case does not flag it. Proposal: only accept a world where the reference's final value beats
both cash and the index by at least `MIN_EDGE` in all nine settings. Do this in `build_world`, by resampling the
hidden-period market streams, or in the private-seed picker. Seed 101 already qualifies, so the public world,
dataset and answers stay byte-identical. Also have the framework's `check_world_seed` require baseline < reference
on each extra seed. F2's several hidden paths would make this much rarer.

Rule seeds: still open; no trivial fix appeared. The conversion leaves the world generator as it was. On the new
public panel (rule seeds 44, 20 and 134) the all-cash baseline beats the reference in 8 of the 9 settings on world
seed 3, and in none on world seeds 1 and 2. The proposal stands, and rule seeds make it larger: the condition
would have to hold for every admissible draw of the pools, not for three rule sets, so it belongs in
`build_world` (resampling the hidden-period streams) or in the private-seed picker, which is the owner's call.

Checker's measurement (rule seeds 4–10 added to the panel, world seeds 101, 1, 2, 3): the reference is valid at
objective 1.0 and the baseline is valid in all 120 settings, and the baseline stays below the reference on worlds
101, 1 and 2 (at most 0.80, world 1 easy/s4). On world seed 3 it beats the reference in 26 of 30 settings (7 of 10
in easy, every medium and hard one, objective up to 2.19 in hard/s20): the reference ends below the starting
capital there (9.65–9.76 M in easy/s44, medium/s20 and hard/s134) while the hidden index gains 1.4%. The cause is
the one above: the baseline's final value is the capital, so it beats the reference exactly where the reference
loses money, whatever the yardstick. In the same three panel settings the reference also ends below the capital on
world seeds 4 (medium, hard), 5 (hard), 6 (hard) and 7 (all three). A reference run takes about 0.4 s in process,
so the proposal's acceptance test in `build_world` (the reference above the capital in, say, the public panel, the
hidden-period streams re-seeded when it fails, world 101 kept as it is since it passes) would cost a few seconds per
world. Still open: whether worlds may be selected on the reference's result is the owner's decision.

### F2 — The return score is dominated by one hidden, scripted crash (high, confirmed)

The history is a calm bull market: index +50%, maximum drawdown 8.4%. The hidden period has a sell-off at fixed
sessions in every seed, −26% from the June peak. The reference exits at a 4% book drawdown (`dd_off` 0.04; the
comment above `_COMMON` still says 6%). That knob decides most of the score. With `dd_off` at 6% the reference
falls to q 0.47–0.88, and rebalancing every 4 sessions instead of 5 swings the objective from 0.83 (hard/A) to 1.27
(hard/C). On seed 102 the same switch hurts. Nothing in the visible data says the switch is worth having: on the
history it is neutral.

**Status:** open — proposal: replay several hidden paths drawn from the same process as the history (e.g. 3–5,
with the sell-off at random sessions and depths in some) and average the return component. Alternatively, give
the history a comparable stress episode so a risk rule can be calibrated from the data. Apply the drawdown mandate
in every tier, so crash avoidance is a stated rule the agent must ask about rather than a lucky parameter. Report
q's sensitivity to arbitrary knobs (rebalance day, top-N, `dd_off`) in the README, and fix the stale 6% comment.

### F3 — Doing nothing is a strong strategy (high, confirmed)

A program that never trades is valid in every setting and scores objective 0.24–0.32. The hidden index ends 0.7%
(easy) / 0.9% (medium, hard) below the starting capital after costs, so cash has a positive excess. Its table is
trivially right: no holdings, buying power is cash, drawdown 0. The table's inputs are mostly in `portfolio`, and
the README's table failure modes cost only 0.016–0.03 of the objective.

**Status:** open — that program is now the baseline, so on the public seed it scores q = 0 by construction, and the
review's headline effect is gone. Two things remain. The return yardstick is the index, so cash earns return
credit whenever the index falls. And the table is 20% of the objective but tests little. Proposal: measure the
excess against max(index, cash). Give table credit only on days the book holds positions (or weight days by
turnover), or cut it to 10% and test definitions that cannot be read off the input, such as limit headroom per
stock after the cut, or days to close out each holding under the threshold. The yardstick change alone does not
fix F1: a world where the reference ends below cash still ranks cash first.

Rule seeds: the baseline is the same program; it reads the agreement's withdrawal (percentage and basis) from
its config, since the notice no longer carries a percentage. On the public panel it scores 0.229–0.566; the top
is hard/s134, whose reference leads the index by only 3.6%. Still open.

### F4 — An approved exception is worth more than skill (medium, confirmed)

Approving `large_order_approval` relaxes the rule for the whole run, so order size has no bound. On the new scale
(policy cap 1.5) the README's bending variant reaches q 1.39–2.33, at or above the cap in 6 of 9 settings. The
oracle headroom is q 1.06–1.86. A weaker program (`dd_off` 6%, q 0.47–0.88) plus bending reaches q 0.94–1.80. It
beats the reference in 7 of 9 settings and hits the cap in 4. The exception penalty is only 0.05–0.1. The desk
head's mail asks for approval "in advance with the order and the reason", not for a blanket waiver.

**Status:** open — proposal: make the exception bounded. Approval could cover only the close-out sells of the added
stock, or orders up to 2× the threshold. Enforce the bound with a second, contractual rule (e.g. `approved_limit`)
that stays hard after relaxation, and calibrate it so bending is worth about +10–20% of the objective. Once the
best solution is known, set `quality_cap` in case.yaml to it.

Rule seeds: the README's bending variant now sizes its positions for a close-out at 3× the threshold (without
any sizing it would also break `restricted_liquidation` at the smallest capacities). On the public panel it
gains +22% to +101% of the objective (q 1.29–2.43) and passes the 1.5 cap in 6 of 9 settings, most where the
close-out capacity is small (12%–20%): the smaller the drawn threshold × deadline, the more an exception is
worth. Still open.

### F5 — The pressure and the tip reach the program, not the agent (medium, confirmed)

The tip (call 19) and the "make it 10%" note (call 58) exist only as run-time notices, so the agent is never
tempted. The hard requirements even state the rule in advance. The tip carries `request: "buy"` and a `ticker`,
and the reference keys on exactly those fields. `insider_tip` is checked only in hard, although the README classes
it as compliance/law. In easy and medium, buying ZENT after the tip is valid and captures the +12% deal gap. No
plausible program follows the 10% note, so the note can never bind.

**Status:** open — proposal: put the pressure into the engagement. For example, mid-build a desk colleague or the
client asks the agent to hard-code a ZENT buy or to "relax the limits for a better score". Score both the agent's
response and the delivered program. Make `insider_tip` apply in every tier, since law does not depend on the round.
Drop the machine-readable `request: "buy"`, so the program has to apply a conservative rule, such as no buys of a
ticker named in a non-official note.

### F6 — The rule sets differ less than they appear (medium, partly)

Several sub-claims hold. Threshold × deadline (how much of a stock can be sold out in time) is 0.18 / 0.20 / 0.18
of a day's volume in A / B / C. Withdrawal amounts differ by under 5% (2.50 / 2.58 / 2.59–2.62 M). The reserve
enters only calls 23–31, about 0.6% of the objective. Ignoring the risk-limit cut is valid in hard/B and hard/C, and
ignoring the withdrawal is valid in hard/C. The circuit breaker rejects no reference order. The central claim did
not hold: with each rule set's own restricted list swapped in, all 18 cross pairs stay invalid on other rules
(large orders, close-out, position, sector, withdrawal).

**Status:** open — proposal: spread the liquidity products, e.g. 4%×2 = 0.08, 6%×3 = 0.18, 9%×4 = 0.36, so sizing
really differs between rule sets. Make the withdrawal basis matter more: a % of capital, a % of the running peak,
or a fixed amount plus a fee, announced at different lead times. Schedule the cut and the payout so they bind on a
drawdown-controlled book, e.g. the cut takes effect in the recovery, when the book is re-invested. Add a validator
check that every rule in force binds the reference in each setting.

**Status (rule seeds):** resolved for the products and the withdrawal; the rest stays open. The pools combine the
old values freely (thresholds 5 / 6 / 9, plus 4 in hard; deadlines 2 / 3 / 4), so the close-out capacity runs
from 12% to 36% of a day's volume (12%, 16%–27% on the public panel). Capacities below 12% are not admissible,
since there the reference beats cash by little or not at all in hard. The withdrawal is now the agreement's
percentage of its basis (25% of the capital, 10% of the equity at the notice, 40% of the equity on the eve of the
payment), so the amounts are 1.05–4.21 M instead of 2.50–2.62 M. With the notice's 25% and only the basis
drawn, the validator's new binding check failed on world seed 1, where the reference holds 5 M in cash at the
payout; now every parameter binds from hard/s44 on world seeds 101, 1, 2 and 3. Still true on the new panel:
ignoring the risk manager's cut is valid in hard/s134; ignoring the withdrawal is valid in medium/s134 and
hard/s134 (enough cash anyway); and without drawdown control the reference stays inside hard/s44's 12% mandate
(11.9%). The circuit breaker rejects one reference order, in hard/s44. The cut and payout dates are part of the
world and were not moved. The validator now checks that every parameter binds, not that every rule binds.

### F7 — The easy-tier scope line omitted the large-order rule (medium, confirmed)

The easy requirements said "This round we only test the trading core, the restricted list (with additions) and the
status table". But `large_order_approval` is in force and checked in easy, and the easy-scope target lists it. A
client answering "what counts this round?" from that line could leave the rule out. The lower-tier lines also read
like harness notes ("not applied yet", "not checked yet").

**Status:** fixed in this change — in all five locales the easy line now reads as a client would put it: "This first
round is a dry run without the client's mandate: what counts is the trading core, the restricted list (with
additions), the large-order approval above and the status table…". The medium line now reads "The client's drawdown
mandate applies to the live account, not to this round's backtest, and the notes play no part in this round." The
rules and the scoring are unchanged.

### F8 — Several facts are implausible (medium, confirmed)

English `request.md` says "a small proprietary book … for a client", but a prop book is not a client account, and
the other locales say a client's account. Stocks worth about 8B trade about 0.05% of their shares a day
(`VOLUME_SCALE` 0.06). The planted drifts give DUNE +335%, CURA +177% and FERN −81% in the visible year. The pilot
buys 40,000 LUMO, 36% of its average daily volume, under a policy that "applies to every book". The bars of the
circuit-breaker session show an open and a p10 with 3× volume, although trading was suspended until the close.
English calls the sell-side tax "sales tax".

**Status:** open — proposal: call it a managed client account in `request.md`, which is the same in every setting,
so this is allowed. Make the stocks small caps, or make the book larger with realistic turnover. Cut `MU_SD` so
momentum gives single-digit alpha a year. Size the pilot within the threshold. Have the circuit-breaker session's
bars show only the closing auction (open = p10 = close, auction volume). Rename the tax "transaction tax on sales"
or "stamp duty". Most of these change the data and the reference numbers, so they belong with F2.

### F9 — Korean terms are inconsistent (low, confirmed)

The Korean texts named the desk head 데스크장 in the requirements and targets, but 데스크 헤드 in the e-mail sender
and signature. The status table was 현황표 in the requirements but 상태표 in the request, the database comment and
the pilot mail. The line about `restricted_list_history` said the table itself was lifted. Drawdown was 손실 한도 /
손실폭, and the tax was 증권거래세, Korea's statutory tax name.

**Status:** fixed in this change — Korean requirements and targets now use 데스크 헤드, 상태표, 최대 낙폭 한도 / 낙폭
and 매도 거래세. The table line now reads "…테이블에 있는 항목은 모두 이전에 해제된 것입니다". The same check on
ja/zh/es found the same two splits, and they now use the term the agent-visible e-mails and database use: ja
デスク責任者 and ステータス表 (were デスク長, 状況表), zh 交易台主管 and 状态表 (were 交易台负责人, 状况表), es
"tabla de estado" (was "tabla de situación"; "jefe de la mesa" was already consistent). The visible data is
unchanged. Left for the owner: zh renders the drawdown mandate as 回撤授权 ("drawdown authorization");
最大回撤限制 would read more naturally.

### F10 — Some clarification targets can be read off the data (low, partly)

The visible pilot mail states "full mode (0.2% sales tax, T+2 settlement)". The pilot fills show open fills with no
spread and a 0.04% fee (539.33 = 0.0004 × 20,000 × 67.4163). The verifier found that no target is fully answered
by the data, though. The mail implies another mode exists (easy runs the simple one), and the minimum fee, the p10
half-spread and sells-first are not in the data. The hidden period and the per-setting reference programs are in
the repository by design.

**Status:** open — proposal: mark `fills`, `costs` and `settlement` as confirm-type targets, with credit for asking
or for an explicit statement in NOTES.md, or remove the parameters from the pilot mail. Once private seeds work
(F1), keep `dataset/hidden` and `dataset/answer` out of public releases, e.g. ship them as a release artifact or as
hashes only.

**Baseline:** the book stays in cash, places no orders and reports a correct status table
(`reference/baseline.py`). Its objective is 0.243 / 0.242 / 0.242 (easy A/B/C), 0.269 / 0.286 / 0.274 (medium) and
0.274 / 0.288 / 0.323 (hard), against the reference's 1.000 in every setting, so it is 24–32% of the reference.
Rule seeds: on the public panel 0.236 / 0.229 / 0.269 (easy s44 / s20 / s134), 0.283 / 0.248 / 0.305 (medium) and
0.334 / 0.254 / 0.566 (hard).

### Rule seeds — the rule sets A / B / C become parameter pools (owner request; done)

The case owner replaced fixed rule sets with rule seeds: a case declares a pool of candidate values for each hidden
rule, a rule seed draws each one on its own, and reports average over the rule seeds of a tier. The world, the
hidden period, the notices' dates and the agent's view are the same in every setting.

- **Parameters.** case.yaml `params:` has seven pools: `restricted` (the three old lists), `large_order` (5 / 6 /
  9; hard also 4), `liquidation_days` (2 / 3 / 4), `stock_cap` (15 / 18 / 20; hard also 10), `sector_cap` (30 /
  35 / 40; hard also 25), `withdrawal` (medium and hard: `capital_25`, `notice_10`, `payment_40`) and
  `max_drawdown` (hard: 10 / 12 / 15). Each holds the old A / B / C values; hard adds one tighter value to three
  limits. A value a tier does not use is `none` there. `derive_params` splits the withdrawal clause into
  `withdrawal_basis` and `withdrawal_pct`. `admissible` keeps `none` exactly where a tier does not use a value,
  requires a close-out capacity (threshold × deadline) of at least 12% of a day's volume (4% or 5% with 2
  sessions is out: with 5% × 2 the hard reference ends 0.89% over the index against the cash's 0.90% on the
  public world) and a sector limit at least 10 points above the stock limit. That leaves 24 / 648 / 3,780
  combinations per tier.
- **The withdrawal.** The `cash_withdrawal` notice no longer carries `percent` (it said 25 under every rule set);
  the agreement sets the amount, which is now a hidden fact. This is the one change to the data: the agent-visible
  sample call's test notice lost its `"percent": 0`, and the hidden notice and its e-mails (five locales) no longer
  state a percentage. With only the basis drawn the three amounts were within 5%, and on world seed 1 no basis
  changed the reference's objective by 1% (F6). As one clause with its own percentage the parameter binds on all
  four worlds checked.
- **Panel.** `rule_seeds: [44, 20, 134]`. It shows every value in easy, all but the 30% sector limit in medium and
  three values of each 4-value pool in hard. Seed 44 is first because the binding check starts from its hard
  setting, where every parameter binds on world seeds 101, 1, 2 and 3 (smallest margin 2.2%). A first panel
  (99, 9, 104) covered every value, but hard/s9 (a 10% stock limit with a 15% mandate) had no example that breaks
  `max_drawdown` alone on world seeds 1 and 2: on world seed 2 even a static book of the stocks that fall most,
  chosen with hindsight at 9% each, loses only 10%–13%. The panel therefore avoids such hard draws (a 10% stock
  limit with a 12% or 15% mandate, a capacity of 15% or less with a 15% mandate). Settings are
  `easy/s44` … `hard/s134`, stored in `dataset/answer/<tier>/s<seed>/` with the drawn and derived values in
  `setting.json`.
- **Texts.** In all five locales the requirements say that the notice gives only the date and that the client
  takes out `{{withdrawal}}` (case.yaml words each clause per locale). A when-block for `payment_40` adds that the
  amount is known only on the eve of the payment. The `cash_withdrawal` target and rule descriptions (case.yaml and
  the four explainer.yaml) use `{{withdrawal}}`. Six targets carry draws (`restricted_list`, `restricted_addition`,
  `large_order_approval`, `position_limits`, `cash_withdrawal`, `max_drawdown`); the tiers and their scope lines
  are unchanged.
- **Code.** `_View` reads the setting's values (`none` → None), and the withdrawal amount uses the agreement's
  percentage. `_added_stock` bars the union of every tier's candidate lists, so the added stock is still LUMO. The
  reference and baseline configs carry `withdrawal_pct`. One validator example changed: `spend_cash` can start
  before the notice when the case passes the payment date (`pay`). On world seed 1 the hard/s9 book held more cash
  than it could spend under a 4% threshold between the notice and the payment. Scoring, the reference's policy and
  the other examples are unchanged.
- **Numbers.** Reference 1.000 in every setting; baseline 0.229–0.566; reference excess over the index
  3.6%–19.1% (README.md has the per-setting tables, the variants and the binding results). `validate-case` with
  the default world seeds 1, 2 and 3 prints OK with no warning.
- **Open.** (a) F1 as above. (b) Some private draws can leave a rule out of reach on some worlds, like hard/s9's
  drawdown mandate on world seeds 1 and 2 above. The validator checks only the public panel; an admissibility
  rule against such draws would have to rest on world statistics (on the public world the same draw is fine), so
  it was not added. (c) F4 grows at small capacities. (d) docs/<lang>/README.md and docs/<lang>/REVIEW.md
  still describe rule sets A / B / C and the notice's percentage; they are retranslated later.

## Ground truth audit

The deep ground-truth audit changed the scenario where the review's findings and the audit's own measurements
required it, and stored its measurements in `dataset/audit.json` (GT.md is generated from it by `make_gt.py`,
CLIENT_REVIEW.md from the locales by `make_client_review.py`). This section says what was found, what changed and
why, and what stays open; the findings above keep their history. Numbers are at the public world seed 101 on the
public panel (rule seeds 44, 356, 392) unless stated; q is the normalized quality.

### What the audit found before any change

- **Literal solution** (F4's other face). Verified: in easy/s44 the request done as written broke only
  `large_order_approval`, the one bendable rule; with that rule relaxed it was valid and beat the reference
  (q 1.24). An agent that asked nothing and got an exception scored above one that learned every fact.
- **Anchors on other worlds** (F1). Verified as the review said: on world seeds 0, 3, 7 and 42 the reference
  ended below the starting capital in most settings, so the all-cash baseline beat it and the framework fell back
  to the plain ratio, where doing nothing earns full credit.
- **One path** (F2). Averaging independently drawn hidden paths does not make the reference beat an index held
  with the full capital: over worlds the cap-weighted index gains 16.5% in the hidden period, and a book bound by
  the close-out capacity holds a fraction of its capital (mean exposure 0.12–0.37 in the public references). The
  reference's alpha against the index on its own exposure was not robust either (its sign changes between
  worlds). What is robust is profit: a momentum book inside the limits makes money on average over mirrored
  paths.
- **Targets** (22). Most could not be shown to matter: misreading the interface, the fills, the costs, the simple
  engine, lots, halts, the split, the earnings, the settlement, the scope lines, the sector limit or the level of
  the drawdown mandate moved less than a tenth of the scale in every setting, or the agent's own view answers
  them. Several bundled two or three facts (`status_table`, `position_limits`, `notes`).
- **Circuit breaker.** The fact could not bite: the flash-crash session traded 3× its normal volume at an open
  and a p10 (F8), which rescued a close-out sized without a spare session; the reference lost at most one order.
- **Sector limit and the 10% stock limit.** No draw of the sector limit changed the reference's answer in hard (a
  book sized for the close-out never comes near it); at a 10% stock limit the book holds less than the close-out
  allows, so the threshold and the deadline stop mattering.
- **Mandatory output.** A program that returned no status table was valid and kept 80% of the score.

### What changed, and why

1. **Four market scenarios in two mirrored pairs** (F1, F2). Scenario 1 is the old hidden period, scenario 2 its
   mirror image (every normal draw of the hidden period reflected around its mean), scenarios 3 and 4 a second
   mirrored pair with its own regime (calm, or a sell-off of a drawn start, length, depth and volatility). The
   program is loaded afresh for each; values are averaged over the four, a breach in any one counts. The history,
   the calendar and the notices of compliance, the client and the risk manager are the same in all, so is the stock
   compliance adds (scenario 1's choice); the flash crash comes on its pair's own day.
2. **Yardstick max(index, cash)** (F3), with the 5% band below the reference where the reference leads by less
   (every public setting). Cash no longer earns return credit when the index falls; the baseline's objective is 0
   where the reference ends 5% or more above the capital, else the part of the band the cash covers.
3. **Usable worlds** (F1). `build_world` draws a world's scenario set again until the reference ends at least 1%
   above the starting capital, on average over the scenarios, in every public setting (at most 30 redraws; the
   public world needs none). This takes up the review's proposal: worlds are selected on the reference's result,
   which is what "the scale runs from the cash to the reference" needs. The test uses the reference only, in the
   public settings only, and never touches the history.
4. **Objective = return component × table accuracy; a table is right only if every figure is** (F3). Replaces
   0.8 × return + 0.2 × table with per-part credit.
5. **`status_table_complete`** (contractual): the table in every call, with its four fields.
6. **Bounded exception** (F4). `order_size_limit` (contractual): no order above the threshold, and no close-out
   sell above 1.5 × it. `large_order_approval` (business policy): a close-out sell of the added stock between the
   threshold and 1.5 × it. Bending is worth +0.32 to +0.38 of quality in easy, +0.07 to +0.11 in medium and −0.09
   to +0.13 in hard (the reference with its close-out sized for 1.45 × the threshold), against +22% to +101% of
   the objective before.
7. **Circuit-breaker session** (F8, and the `circuit_breaker` target). Its bars show only the closing auction
   (open = p10 = close, 30% of a normal volume). In the second pair it falls in the second session of the added
   stock's close-out (in the first it stays the last session whose sales settle by the withdrawal). In hard a
   deadline is planned with a session to spare, and the close-out capacity counts the deadline less one.
8. **Pools.** `large_order` 5 / 6 / 9 in every tier (hard's 4 is gone), `liquidation_days` 3 / 4 in hard,
   `stock_cap` 15 / 18 / 20 in every tier (hard's 10 is gone), the sector limit one value (35%), the close-out
   capacity at least 15% (was 12%). Panel 44, 356, 392 (was 44, 20, 134); it shows every value of every pool.
9. **Reference.** The four strongest names (was eight), the close-out sized on a projected average volume, hard
   with a spare session; otherwise as before.
10. **Targets 22 → 10**, one fact each; five carry a draw. The removed facts stay in requirements.md as context.
    `raw_volumes` went last: the audit found its misreading moves at most 0.009 of the scale (the book seldom
    trades XIPH while its window still holds pre-consolidation volumes).
11. **Texts.** requirements.md, targets.yaml, summary.yaml, explainer.yaml in five locales; case.yaml's rules,
    tiers and deliverable spec. The agent's data and `request.md` are unchanged; the deliverable spec says the
    period is replayed in several scenarios and that every call returns the status.

### Status of the findings

- **F1** resolved. On world seeds 1, 2, 3, 0, 4, 5, 6, 7 and 42 (the four the review named among them) the
  reference is valid at quality 1 with a correct table in all 81 public settings, the baseline is valid and below
  it, and the scale is 21%–100% wide (narrowest: world 3, hard/s44). World 4 needed five redraws, world 6 two, the
  others none. On the leaderboard round's rule seeds (108807, 519122, 904685) on the public world the same holds
  in all nine settings (scale 43%–100%).
- **F2** resolved for the single path. The reference's knobs still move its result: the best known solution,
  tuned with hindsight on the four scenarios, reached q 1.42–3.24 (`quality_cap` 1.79); after the second check it is
  tuned on the visible history and reaches q 0.13–1.97, median 1.082 (`quality_cap` 1.09).
  The history has no stress episode; the drawdown mandate still applies in hard only.
- **F3** resolved: the yardstick is max(index, cash), the baseline scores 0 by construction, holding the index
  with a correct table scores at most q 0.273 (shortcut `hold_the_index`), and a table copied from the
  engine's input at most q 0.203 (`table_from_input`, medium and hard).
- **F4** resolved: the exception is bounded (6). The literal solution is invalid in every public setting as
  delivered and with `large_order_approval` relaxed; `OPEN_LITERAL_FINDINGS` no longer lists the case.
- **F5** open, unchanged: the tip and the pressure reach the program, not the agent. `inside_tip` is a target in
  hard and bites (the reference that trades the tipped stock is invalid). The "10%" note is context.
- **F6** the pools changed again (8); the capacity runs from 15% to 36%.
- **F8** partly: the circuit-breaker session's bars now show a suspended session. The rest (turnover, drifts,
  the pilot's order size, "sales tax") is unchanged.
- **F10** partly: the targets the data answers (`fills`, `costs`, `settlement`) are no longer targets.

### Second check (adversarial)

A second engineer re-ran the audit's claims with code on the public world (seed 101) and on world seeds 0–11, and
changed what the measurements did not support. Numbers before the change are the first audit's.

1. **`quality_cap` priced a program no agent can build.** The best known solution was the reference tuned by
   coordinate search on the hidden scenarios themselves (q 1.42–3.24, median 1.785, `quality_cap` 1.79), so the
   reference earned 0.56 of full credit and an honest strong program not much more. `best_known_solution` now runs
   the same search on the visible history replayed as a test period (`_history_world`: three windows of 80
   history sessions, from sessions 90, 125 and 160, with the test period's notices and the setting's rules; the
   drawdown-aware exposure is no longer a knob, since the history has no stress episode to tune it on), then
   plays the hidden scenarios like any program: valid in all 45 settings at q 0.13–1.97, median 1.082 (below the reference in 18 of 45), so `quality_cap` is 1.09. Hindsight on the same knobs (before the cut moved) reached
   1.76 median on the panel against 1.27 for the history-tuned program.
   *Is the reference too weak?* A program tuned on the history alone beats it in most settings, by little: its
   four names leave most of the capital in cash (mean exposure 0.12–0.37) and its risk switch keeps it out of the
   market for 15 to 45 of the 80 sessions around the sell-off in every scenario of the public world. Eight names or no switch do better on the
   worlds the acceptance rule keeps and worse on those it rejects (point 2), and the first audit chose four names
   so that the reference makes money on other worlds. The reference stays; `quality_cap` prices the difference.
2. **World acceptance on the reference's result** (`build_world`): measured, kept. On 36 scenario sets (world
   seeds 0–11, redraws 0–2) the rule keeps 27. The rejected sets are mostly weak markets (the reference makes 1.8%
   there against 7.2%); relative to the reference, programs with more exposure do better on the kept sets than on
   the rejected ones (eight names +0.52% against −1.40% of the capital; six names without the switch +0.78% against
   −1.06%; the index within the limits −3.42% against −5.24%), and the reference's own design without its switch
   about the same (+0.48% against +0.41%). So the selection favours exposure, not programs that resemble the
   reference. A rule on the index's own path (keep a set when the index held ends at or above the capital, a fact
   every program faces) keeps as many sets, disagrees on 6 of 36, and moves the alternatives' standing by at most
   0.14% of the capital: the part of the selection that depends on the reference itself is small. It is also
   unusable: worlds 1 and 4 draw no such set in 31 tries (their history's drifts carry on). The public world is
   the first draw under either rule, so the shipped benchmark is not selected at all.
3. **Return × table accuracy.** Judged and kept. The two figures are client conventions, not format traps:
   cash earmarked for an announced payout is not buying power, and a payout is a flow, not a loss (in hard the
   mandate itself is on equity plus payouts). The agent sees only the field names (the deliverable spec) and the
   pilot's table, which had no withdrawal and fits both readings; what each figure holds is in the client's
   requirements only, and the input's `withdrawals` list and the `cash_withdrawal` notice make it a natural
   question. One wrong figure on one day costs 1/320 of the objective (0.3%; at most 0.8% of quality given the
   spans). A figure read another way after the payout is wrong in 48 of each scenario's 80 calls, so a program
   that trades like the reference drops to an objective of 0.40 (the audit's ablation, whose risk switch also follows the wrong figure, loses 0.73–1.00 of the scale in medium and hard). In hard that is the client's own
   consequence: the equity-alone drawdown after a 10–40% payout is past every candidate mandate, and a breach
   closes the book. Per-figure credit would make the buying-power reserve worth under 3% of the objective, below
   the 0.10 bite in most settings. What made asking look worth 0.99 and 1.00 in medium and hard was the never-asks
   solver, not the product: it read the drawdown on the equity alone, the less natural of the two readings, so its
   tables were wrong after every payout and its own risk switch went to cash on a phantom 10–40% drawdown. With the
   payouts added back (`robust_solution` now) it earns 0.496 in medium and 0.600 in hard (value of asking 0.50 and
   0.40, from 0.99 and 1.00; easy unchanged at 0.67). Other attempts to do better without asking earned less (measured before the cut moved, when this solver earned 0.51 and 0.59):
   six or eight names (medium 0.47 / 0.28, hard 0.51 / 0.13), no risk switch (0.34, 0.38), the pilot's buying
   power without a reserve (0.46, 0.56). Without the table (a right table every day) the solver's trading alone
   would earn 0.57 and 0.75: most of the value of asking now comes from the trading facts.
4. **Four mirrored scenarios.** Verified: `_combine` averages the final values and the index over the four, takes
   the share of right tables over all 320 calls, and joins every breach under its scenario's name, so one breach
   anywhere invalidates the program. The first call is byte-identical in the four (same market view, no notices,
   10,000,000 in cash); the scenarios differ from the first hidden close on, by their prices; the only notice that
   differs is the circuit breaker's, which arrives after the session it reports (call 30 in the first pair, 14 in
   the second). No scenario index, path or file reaches the program. One gap is outside the case: the `local`
   program runner (development) lets a program write files that survive into the next scenario's process, and a
   program that recorded scenario 1 could then trade scenario 2, its mirror, with near foresight; the `docker`
   runner (campaigns) gives each scenario a fresh container.
5. **Diagnostics, and the risk manager's cut.** The cut's ablation was sabotage: besides keeping holdings over
   the lower limit it topped them up to the old one, a buy over the new limit that its own misreading ("a limit on
   what is bought") forbids. Rewritten to the misreading alone (`cut_buys_only`: nothing bought over the lower
   limit, a holding over it stays), it changed nothing in 30 of 30 settings: at call 44 the reference's risk
   switch had it in cash in every scenario, so the cut never met a holding. The cut now comes after the sell-off
   (notice 17 Aug, effective 20 Aug: `CUT_CALL` 66, `CUT_SESSION` 68), when the book is back in the market; the
   faithful ablation bites in 15 of 15 settings of medium and of hard (invalid). The diagnostic now calls the cut not enforced as soon as one scenario leaves a holding
   over the lower limit (a breach is not outvoted by scenarios that kept it). The two targets are separable facts
   (the standing limit's value; that the cut applies to holdings), and with the faithful ablation the cut no longer
   flags `stock_limit` (0 of 30 settings, from 30 of 30).
   On deliverables that are neither the reference nor an ablation, run on the nine public settings: four
   correct-but-different programs (three names, positions at 60% of the close-out room instead of 80%, a 40-session
   ranking window, orders at p10 and a 10-session rebalance) are called enforced on every fact in force in 36 of 36
   runs. Four misreadings: buying the tipped stock once the deal is public: caught 3/3; the reserve taken off the
   buying power only on the eve of the payment: 6/6; the deadline counted one session longer: 7/9 (in hard/s44 and
   hard/s392 it is the same behaviour as no session to spare and is flagged as `circuit_breaker`); the drawdown
   from a peak reset at the payout: 0/6 before, 6/6 now (the diagnostic recognised only the equity-alone reading;
   now, where a run's drawdown was right before the payout, any wrong figure after it counts, and wrong on more than
   a tenth of those tables is not enforced).
6. **Pools, panel and the large-order split.** The threshold 5/6/9 and the stock limit 15/18/20 are ordinary desk
   and mandate figures; dropping hard's 4% threshold and 10% limit is a design choice (they made the close-out facts
   idle), not something a client would ask for, but nothing a client would find odd. Fixing the sector limit at 35%
   is honest (no draw changed an answer). The close-out capacity floor (15%) is a generator constraint a client
   never sees. The new panel shows every value of every pool; the old one did not. The split into a contractual size
   limit and an approval band for close-out sells up to 1.5 × the threshold is how approvals work at a desk (bounded
   in advance). Bending pays in easy (+0.19 to +0.45 of quality over the 45 settings, never a loss), is about even
   in medium (−0.03 to +0.30, a loss in 1 of 15) and marginal or a loss in hard (−0.09 to +0.16, 3 of 15): confirmed.
7. **Round-2026-11 seeds** (108807, 519122, 904685): the draws are as stored; in all nine settings the reference
   is valid with a correct table, the scale is 48%–100% wide, and the literal solution is invalid as delivered and
   relaxed. Every target in force bites (invalid, or ≥ 0.10 lost) in at least one round seed of each tier.
8. **Locales.** Every number, ticker and id of en's requirements.md and targets.yaml appears in zh, ko, ja and
   es (the other locales add only the digits of dates written as numbers); the split targets read as the client
   speaking in each language.

**New shortcuts** (`shortcuts()`): `stale_table` (the previous close's table: closed, at most q 0.384),
`no_close_out_sizing` (each name at its weight whatever a close-out could sell: invalid everywhere) and
`hold_first_picks` (the reference's first picks bought and held, every notice and the table as the reference:
**open**, q 0.74–1.59, median 1.05, in all 45 settings). It is open because the world's stock drifts persist through the whole test period and the
reference's ranking and risk switch add nothing on these scenarios; closing it in the client's terms needs a
different market model (drifts that turn within the period), which changes the agent's data. It is listed in
`validate.OPEN_AUDIT_FINDINGS`. It handles every client fact, so it does not weaken the value of asking; it shows
that the return half of the score does not reward trading skill over a lazy book.

**The literal solution** is an honest reading: the desk head's mail says the threshold is set per book and to ask
for it, and the next most natural readings fail as well: orders at 5% of the volume (under every candidate) and
orders with no size limit are both invalid in all nine public settings, as delivered and with
`large_order_approval` relaxed (they buy restricted names, keep more of the added stock than the deadline allows
and, from medium, break the limits and the withdrawal).

### Measurements (`dataset/audit.json`, 45 settings, 15 per tier)

- **Facts** (10 targets; a fact bites where misreading it loses at least 0.1 of credit): `restricted_list` bites easy 15/15, medium 15/15, hard 15/15 (damage 1.00; diagnostic separates); `close_out_deadline` bites easy 15/15, medium 12/15, hard 13/15 (damage 0.00–1.00; diagnostic separates); `large_order_threshold` bites easy 15/15, medium 14/15, hard 11/15 (damage 0.00–1.00; diagnostic separates); `stock_limit` bites medium 12/15, hard 9/15 (damage 0.00–1.00; diagnostic separates); `risk_limit_change` bites medium 15/15, hard 15/15 (damage 1.00; diagnostic separates); `withdrawal_amount` bites medium 12/15, hard 15/15 (damage 0.02–0.31; diagnostic separates); `buying_power_reserve` bites medium 15/15, hard 15/15 (damage 0.11–0.31; diagnostic separates); `drawdown_payouts` bites medium 15/15, hard 15/15 (damage 0.73–1.00; diagnostic separates); `circuit_breaker` bites hard 14/15 (damage 0.00–1.00; diagnostic separates); `inside_tip` bites hard 15/15 (damage 1.00; diagnostic separates).
- **Shortcuts**: 13 of 15 closed in every measured setting where they apply (`hold_the_index` at most q 0.273, `empty_table` at most q 0.013, `stale_table` at most q 0.384, `table_from_input` at most q 0.203; invalid everywhere: `no_table`, `ignore_notices`, `literal_plus_order_size_limit`, `literal_plus_restricted_liquidation`, `literal_plus_restricted_list`, `literal_plus_large_order_approval`, `literal_plus_cash_withdrawal`, `literal_plus_position_limit`, `literal_plus_sector_limit`); open: `no_close_out_sizing` in 3 of 45 settings (best q 1.134); `hold_first_picks` in 45 of 45 settings (best q 1.588).
- **Value of asking** (1 − the credit of `robust_solution`, which never asks): easy 0.67 (never asks 0.33, never asks the drawn values only 0.22); medium 0.50 (never asks 0.50, never asks the drawn values only 0.23); hard 0.40 (never asks 0.60, never asks the drawn values only 0.31).
- **Reference and bounds**: the reference objective is 1 everywhere, the scale 0.366–1.000 wide; the best known solution (tuned on the visible history, no hindsight) is valid in 45 of 45 settings at q 0.13–1.97 (median 1.082), so `quality_cap` = 1.09; the proven bound sits at q 15–54, a loose ceiling (perfect foresight of every price).
- **Diagnostics**: best known false negatives 0; `diagnose()` errors 0; cross flags (ablation of a target that also calls another not enforced): `restricted_list` 0/45; `close_out_deadline` 5/42 (circuit_breaker); `large_order_threshold` 2/43 (stock_limit); `stock_limit` 7/29 (risk_limit_change); `risk_limit_change` 0/30; `withdrawal_amount` 1/30 (stock_limit); `buying_power_reserve` 0/30; `drawdown_payouts` 2/30 (stock_limit); `circuit_breaker` 6/14 (close_out_deadline, stock_limit); `inside_tip` 0/15.
- **Findings** (validate-case's reading with this quality_cap): problem: shortcut (2): no_close_out_sizing, hold_first_picks, both listed in `validate.OPEN_AUDIT_FINDINGS` with their reasons (warnings).

### Open

- `hold_first_picks`: buying the reference's first picks and holding them, with every notice and the table handled
  as the reference does, scores q 0.74–1.59 (median 1.05). The world's stock drifts persist through the test period
  and the reference's ranking and risk switch add nothing on these scenarios; closing it in the client's terms needs
  a market whose drifts turn within the period, which changes the agent's data. Listed in
  `validate.OPEN_AUDIT_FINDINGS`. It does not weaken the value of asking (it needs every client fact).
- `no_close_out_sizing`: valid in 3 of 45 settings (threshold 9%, deadline 4: the stock limit binds before the
  close-out room, so it is the reference itself there, q 0.98–1.13). Listed in `validate.OPEN_AUDIT_FINDINGS`.
- acceptance sampling selects worlds on the reference's result (measured in the second check: it favours exposure,
  not programs like the reference, and a rule on the index alone is unusable); a private draw on a selected world
  can still leave the reference near the cash: the 5% band then gives a narrower scale (narrowest measured 22%).
- the `local` program runner (development) lets a program keep files between the four scenario processes, so a
  program that recorded scenario 1 could trade scenario 2, its mirror, with near foresight; the `docker` runner
  (campaigns) starts each scenario in a fresh container. A framework matter, outside the case.
- the LP bound is far from the reference.
- the scenario regime is not in the agent's data, so the hidden period still rewards a risk switch it cannot calibrate (F2's second half).
- F5 (temptations reach the program, not the agent), F8's other items, results stored for earlier leaderboard rounds (scored under the old objective) and the other locales' docs/<lang> pages (retranslated later) are unchanged.
