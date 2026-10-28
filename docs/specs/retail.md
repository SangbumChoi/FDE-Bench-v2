# Retail & E-commerce — case specs

AI in retail is used most in pricing and promotions, followed by search ranking and workforce scheduling.
Markdown engines such as Zalando's Promotheus, which beat manual markdown decisions on profit in an online test,
and vendor tools from invent.ai, Peak and Competera estimate a price elasticity for each SKU and optimise prices
inside guardrails: price ladders, margin floors and reference-price law. Trade-promotion tools try to separate
true incremental volume from cannibalisation and pull-forward. Marketing-mix models (Google Meridian, Meta Robyn)
pair adstock and Hill saturation curves with a budget allocator that respects per-channel bounds. In every case
the model is the easy part. Most of the value, and most of the failures, come from unwritten rules: which
"was" price is legal to show, which vendor deals are actually signed, which returns fall outside the window,
which labour rule applies to a shift. These rules differ sharply between Korea, Japan, China, the EU/Spain and
the US, which makes the field a good fit for a multilingual clarify-then-build benchmark.

| Role | Task type | Deliverable | Hook |
|---|---|---|---|
| Grocery Demand Forecaster ✅ | ML | Batch `forecast.csv` | (built) |
| Markdown Pricing Manager | Optimization | Batch `markdowns.csv` | The legal "was" price is the lowest price of the last 30 days, not the ticket |
| Promotion Planner | Optimization | Batch `promo_calendar.csv` | Only signed vendor deals pay; pantry promos steal from next week |
| Assortment & Shelf Space Planner | Optimization | Batch `planogram.csv` | Facings must hold a case pack plus safety stock; delisted demand partly transfers |
| E-commerce Search Merchandiser | Ranking | Program `rank(query, items)` | Paid slots must be labelled and capped; queries arrive in five scripts |
| Returns Fraud Analyst | ML | Batch `return_flags.csv` | The return window depends on category and channel; serial returners hide behind several accounts |
| Store Staffing Planner | Optimization | Batch `roster.csv` | Breaks, 11 h rest and minors' hours turn traffic curves into legal shifts |
| Marketing Budget Allocator | Optimization | Batch `budget.csv` | Diminishing returns with adstock lag; contracted minimums; Q4 spend lands in Q1 |

No catalog role is replaced. All seven unbuilt roles have strong real-world adoption and a distinct regulatory
hook, and together they cover pricing, space, ranking, ML detection, labour and media without overlap.

Research note: the web-search quota for this session ran out partway through. The labour-law figures for Korea
and Japan in the staffing spec, and the Korean promotion-cost rule, rest on secondary sources and well-known
statute provisions rather than fetched primary text. Case authors should check them against
law.go.kr and e-Gov before building.

---

### Markdown Pricing Manager — `retail/markdown_pricing_manager`
- **Why it matters** — End-of-season markdown is the classic retail use of elasticity models. Zalando's KDD 2022
  system beat manual markdown decisions on profitability in a live test, and vendors report gains of a few
  percent in revenue and markdown loss. Regulators also police the "was" price: EU Art. 6a (Omnibus), Korea's
  KFTC guideline, Japan's CAA 8-week test, China's SAMR 2022 rule and the FTC's 16 CFR 233.1 each limit which
  reference price a markdown may advertise.
- **Client & request** — Head of merchandising at a fashion chain: "Season ends in six weeks. Set the markdowns
  so we clear the winter stock without giving the margin away."
- **Deliverable** — Batch `markdowns.csv`: `sku_id,week,price,advertised_ref_price`. One row per SKU for each of
  weeks 1-6 (ISO weeks starting Monday 2027-01-04). `price` has 2 decimals; `advertised_ref_price` is the
  struck-through price, or empty if no discount is advertised.
- **World & data** — 60 SKUs in 4 categories (coats, knitwear, boots, accessories). `skus.csv` (sku_id,
  category, ticket_price, unit_cost), `stock.csv` (sku_id, on_hand, in_transit, arrival_week),
  `sales_history.csv` (two past seasons, weekly: sku_id, fiscal_week, price, units), `price_log.csv`
  (sku_id, date, price, the last 60 days). Hidden: each SKU's elasticity by category, base demand decay, and
  the salvage value.
- **Hidden requirements**
  - `ref_price_30d` (missing; business rule) — `advertised_ref_price` may be no higher than the lowest price
    charged in the 30 days before the markdown week (EU Art. 6a, Spain Ley 7/1996 art. 20). 9 SKUs had a
    flash sale 3 weeks ago, so their legal reference is the flash price.
  - `no_price_up` (missing; business rule) — Once marked down, a price never rises again within the season.
  - `min_step` (ambiguous; calculation) — Each new markdown is at least 10 points deeper than the previous one,
    measured as % off the ticket price. The FTC treats trivial reductions as misleading.
  - `below_cost` (missing; business rule) — Price ≥ unit_cost until week 5. In weeks 5-6 only, items flagged
    `exit=Y` may go below cost (Spain allows loss sales only when they are not unfair, e.g. clearance).
  - `in_transit` (ambiguous; data semantics) — `in_transit` units arrive in `arrival_week` and are sellable from
    that week on.
  - `fiscal_calendar` (ambiguous; data semantics) — `fiscal_week` in the history follows a 4-5-4 retail
    calendar whose year starts in February, not ISO weeks.
  - `salvage` (missing; scoring) — Stock left after week 6 goes to a jobber at 15% of unit_cost.
  - `objective_def` (missing; scoring) — Score = revenue − cost of goods sold + salvage over the horizon.
    Sell-through alone does not count.
- **Rules**

| id | class | check | why |
|---|---|---|---|
| complete_grid | contractual | One row per SKU × week | Deliverable contract |
| ref_price_legal | contractual | ref ≤ lowest price in the prior 30 days | Consumer-protection law; hard under every policy |
| no_below_cost | contractual | price ≥ cost except `exit` SKUs in weeks 5-6 | Loss-sale law and the supplier agreement |
| monotone | physical | Price never increases | Tickets are physically relabelled; POS blocks re-raises |
| charm_ending | business_policy | Every price ends in .99 | Brand guideline. Rounding down to .99 moves prices off the optimum and loses about 1-2% margin on low-ticket accessories |

- **Objective** — Maximize realised gross profit plus salvage. The world simulates true demand at each price.
  Reference: estimate one elasticity per category with a log-log regression on history, then greedily set
  each SKU's price to the deepest allowed step that clears projected stock by week 6. Headroom of about 8-12%
  comes from per-SKU elasticity and timing.
- **Hard tier** — Duplicate rows in `price_log.csv`. A stale `stock_backup.csv` from two weeks ago. A data
  correction moves 400 coats to `in_transit`. Twist: the buyer insists the ticket price is the legal
  reference; the merchandising head (the owner) overrules.
- **Policy & language angles** — regulated_strict: no exceptions, and NOTES must state the 30-day reference.
  startup_velocity: charm can bend when justified. Localize category labels and currency symbols; numbers stay
  identical. The real-world lookback differs by locale (KR 20 days, lowest price; JP 8-week majority; CN 7 days,
  lowest transaction; EU/ES 30 days; US "reasonably substantial period"). The case fixes 30 days in every
  locale and says so, to keep scoring language-independent.
- **Authoring risks** — The flash-sale SKUs must be visible in `price_log.csv`, not only stated. Make sure the
  charm rule and the 10-point step can always be met together; the ticket prices already end in .99.
- **Sources**
  - https://arxiv.org/abs/2207.01137v2
  - https://www.invent.ai/case-study/markdown-optimization-solutions-case-study
  - https://peak.ai/hub/blog/how-to-build-a-successful-markdown-application/
  - https://www.rpclegal.com/snapshots/consumer/spring-2022/european-commission-publishes-guidance-on-price-promotions-under-the-omnibus-directive/
  - https://www.caa.go.jp/policies/policy/representation/fair_labeling/faq/representation
  - https://www.nepla.ai/wiki/기업과-소비자/공정거래/가격할인-마케팅-기존-판매가의-표시를-유의하자-j21nmvrlxn73
  - https://www.allbrightlaw.com/CN/10531/bca261910c3b9b82.aspx
  - https://www.law.cornell.edu/cfr/text/16/233.1
  - https://www.ineaf.es/tribuna/ley-de-ordenacion-del-comercio-minorista/
  - https://www.ga-p.com/wp-content/uploads/2021/11/Venta_a_perdida.pdf

---

### Promotion Planner — `retail/promotion_planner`
- **Why it matters** — Trade promotions are among the largest P&L lines in grocery. Practitioners agree that
  promo-period lift overstates the real effect once cannibalisation, halo and pull-forward are netted out.
  Korea's Large-Scale Retail Business Act requires a written agreement before a promotion and caps the
  supplier's share of promotion cost at 50%. The KFTC sanctioned SSG.com and Kurly in 2024 for unsigned
  promotions. Japan's FTC addresses supplier contributions as abuse of a superior bargaining position.
- **Client & request** — Category director at a supermarket chain: "Plan next quarter's promotions. Vendors
  are paying for a lot of them, so make the most of it."
- **Deliverable** — Batch `promo_calendar.csv`: `week,sku_id,discount_pct,vendor_deal_id`. Only promoted
  SKU-weeks are listed. `week` runs 1-13 (ISO Mondays from 2027-01-04). `discount_pct` ∈ {15, 25, 35}.
  `vendor_deal_id` is empty when the retailer pays the whole cost.
- **World & data** — 80 SKUs in 8 categories, each split into 2-3 subcategories. `skus.csv` (sku_id,
  category, subcategory, regular_price, unit_cost, storable Y/N), `sales_history.csv` (104 weeks:
  sku_id, week, price, units, promo_flag), `vendor_deals.csv` (deal_id, vendor, sku_ids, funding_per_unit,
  min_discount, valid_from, valid_to, status), `circular_slots.csv`. Hidden: own lift and cross-elasticities
  within each subcategory, the post-promo dip, and baseline demand.
- **Hidden requirements**
  - `signed_only` (ambiguous; business rule) — Only deals with `status=signed` and signed before the promotion
    week may be used. `draft` and `verbal` do not count (the Korean prior-written-agreement rule).
  - `vendor_share_cap` (missing; calculation) — Vendor funding counts only up to 50% of the promotion's markdown
    cost for that SKU-week. Anything above the cap is not received.
  - `deal_window` (ambiguous; data semantics) — `valid_to` is exclusive, and a deal applies only if
    discount_pct ≥ min_discount.
  - `cannibalisation` (missing; calculation) — A promoted SKU takes volume from the other SKUs in its
    subcategory in the same week.
  - `pull_forward` (missing; calculation) — For storable SKUs, the 2 weeks after a promotion lose 30%/15% of
    the promo's incremental volume. Fresh SKUs have no dip.
  - `slot_limit` (missing; business rule) — At most 2 promoted SKUs per category per week (circular space).
  - `regular_price_validity` (missing; business rule) — A SKU may be on promotion in at most 3 of any 8
    consecutive weeks, so that the regular price stays the price charged most of the time (Japan's 8-week
    majority test).
  - `metric` (missing; scoring) — Score = incremental gross margin net of cannibalisation and dip, plus vendor
    funding received.
- **Rules**

| id | class | check | why |
|---|---|---|---|
| valid_values | contractual | Discounts in the allowed set; known SKUs and weeks | Deliverable contract |
| signed_deals | contractual | Every referenced deal is signed, in its window, and meets min_discount | Supplier law and contracts |
| slot_limit | physical | ≤ 2 per category per week | Physical circular and endcap space |
| ref_validity | contractual | ≤ 3 promo weeks in any 8 | Price-display law |
| no_hero_promo | business_policy | The 6 hero SKUs (flag in `skus.csv`) are never promoted | Brand price image. Heroes have the highest lift, so keeping the rule costs about 4-6% of the objective |

- **Objective** — Maximize total profit versus a no-promotion baseline, computed in the world from true demand.
  Reference: fit lift per category from history, rank SKU-weeks by funded margin per slot, fill greedily
  under the limits, ignoring cross-effects. Headroom of 8-12% comes from modelling cannibalisation and dips.
- **Hard tier** — Duplicate deal rows (one signed, one draft). A legacy-encoded `vendor_deals.csv`. A late
  requirement: a vendor deal is withdrawn mid-task. Twist: a vendor's account manager emails that their verbal
  deal is "as good as signed"; the client says no.
- **Policy & language angles** — enterprise_balanced: the hero rule can bend only through approved
  escalation. regulated_strict: draft deals must be raised in NOTES. Localize vendor names, category labels
  and the deal status values (서명완료 / 締結済 / firmado). Week numbering must not change across locales.
- **Authoring risks** — Make the dip parameters learnable from history. Keep the cap deterministic and rounded
  to cents. The reference must stay feasible when the heroes are excluded.
- **Sources**
  - https://www.tredence.com/blog/trade-promotion-optimization-how-global-cpgs-separate-true-incrementality-from-lift-and-cannibalization
  - https://www.griddynamics.com/solutions/trade-promotion-optimization
  - https://gravitee.io/corpus/gen-1306/efficient-consumer-response/promotion-optimization.html
  - https://news.mtn.co.kr/news-detail/2024052010311115757
  - https://www.shokusan.or.jp/wp-content/uploads/2019/03/669pdf1.pdf
  - https://www.caa.go.jp/policies/policy/representation/fair_labeling/faq/representation

---

### Assortment & Shelf Space Planner — `retail/assortment_shelf_planner`
- **Why it matters** — A meta-analysis of 1,268 estimates found that doubling facings lifts sales by about 17%,
  with diminishing returns. Shelf height alone can swing sales by about 39%. Planners also add facings beyond
  what sales justify so the shelf holds enough stock between deliveries. Placement is regulated in some
  markets: the UK bans less-healthy food at checkouts, at aisle ends and near entrances in stores over 185.8 m².
- **Client & request** — Space planning manager at a convenience-store chain: "New season: allocate the snack
  and drinks shelves, and drop what doesn't earn its place."
- **Deliverable** — Batch `planogram.csv`: `store_cluster,fixture_id,shelf,sku_id,facings,position`. Delisted
  SKUs are simply absent.
- **World & data** — 3 store clusters; per cluster 4 fixtures × 5 shelves of 120 cm. 140 candidate SKUs.
  `skus.csv` (sku_id, subcategory, brand, width_mm, case_pack, price, margin, hfss Y/N, contract_listing
  Y/N), `sales.csv` (cluster, sku_id, 52 weeks of units, store_count), `fixtures.csv`, `deliveries.csv`
  (cluster, deliveries_per_week). Hidden: the space elasticity per subcategory, the demand transfer rate when
  a SKU is delisted, and the shelf-height effect.
- **Hidden requirements**
  - `width_units` (ambiguous; data semantics) — `width_mm` is the width of one unit. Facings × width plus 5 mm
    gaps must fit within 1,200 mm per shelf.
  - `holding_power` (missing; calculation) — Facings × depth units (the per-SKU column `depth_units`) must hold
    at least one case pack plus 1.5 days of demand at the cluster's delivery frequency.
  - `min_facings` (missing; business rule) — Every listed SKU has ≥ 2 facings, and top-20 SKUs have ≥ 3.
  - `contract_listings` (missing; business rule) — SKUs with `contract_listing=Y` (supplier listing fees
    already paid) may not be delisted this season.
  - `transfer` (ambiguous; calculation) — When a SKU is delisted, 40% of its volume moves to the remaining SKUs
    in its subcategory. Lost volume is not 100%.
  - `per_store_sales` (ambiguous; data semantics) — `units` is summed over stores, and store counts differ by
    cluster, so compare SKUs per store.
  - `hfss_placement` (missing; business rule) — HFSS SKUs may not sit on fixture F1, the aisle end facing the
    main route (modelled on UK SI 2021/1368 reg. 7).
  - `metric` (missing; scoring) — Score = weekly gross margin across clusters from the world's space-response
    model.
- **Rules**

| id | class | check | why |
|---|---|---|---|
| shelf_fit | physical | Total width per shelf ≤ 1,200 mm | Physical fixture |
| holding_power | physical | Capacity ≥ case pack + safety stock | A case must fit on the shelf at delivery |
| contract_listing | contractual | Contracted SKUs are listed in every cluster | Supplier listing agreements |
| hfss_location | contractual | No HFSS SKU on F1 | Placement law; hard under every policy |
| brand_block | business_policy | Each brand's SKUs are contiguous on a shelf | Shopper-navigation guideline. Blocking prevents putting high-margin SKUs at eye level and costs about 3-5% |

- **Objective** — Maximize margin. Reference: rank SKUs by margin per store per mm and delist the bottom ones
  where contracts allow. Allocate facings in proportion to sales subject to minimums and holding power.
  Place top SKUs on shelves 2-3. Headroom of 6-12% comes from using transfer demand and space elasticity.
- **Hard tier** — Duplicate SKU rows with old widths. A stale fixture file. A data correction: one cluster
  gets fewer deliveries. Twist: category buyer and supplier disagree on a contracted SKU; the contract
  register decides.
- **Policy & language angles** — startup_velocity may break brand blocking. regulated_strict requires NOTES to
  list every delisting. Localize subcategory and brand names (keep IDs). Watch for mm versus inches in the US
  framing, and for full-width brand names that affect the data but not the widths.
- **Authoring risks** — Holding power must be feasible for every contracted SKU. Keep the transfer rate
  learnable from 3-4 historic delistings in `sales.csv`.
- **Sources**
  - https://en.wikipedia.org/wiki/Planogram
  - https://www.legislation.gov.uk/uksi/2021/1368/regulation/7
  - https://www.legislation.gov.uk/uksi/2021/1368/contents

---

### E-commerce Search Merchandiser — `retail/search_merchandiser`
- **Why it matters** — Amazon's Shopping Queries Dataset (about 130k queries in English, Spanish and Japanese,
  graded Exact/Substitute/Complement/Irrelevant) shows that product search is graded and multilingual. Ranking
  is regulated. EU UCPD Art. 7(4a) and Annex I point 11a, added by Directive 2019/2161, require disclosure of
  the main ranking parameters and ban hidden paid placement. The DSA adds recommender transparency. The KFTC
  acted against Coupang in 2024 over search results that favoured its own private-label goods (reported; not
  verified here).
- **Client & request** — Head of e-commerce at a marketplace: "Our search results are bad. Make the ranking
  better."
- **Deliverable** — Program: `def rank(query: str, items: list[dict]) -> list[str]`. It returns item_ids, best
  first, as a permutation of the candidate list (up to 50 items). Each item dict has item_id, title, brand,
  category, price, in_stock, rating, n_reviews, sponsored, is_house_brand, lang.
- **World & data** — 2,000 products. `catalog.csv`, `queries_train.csv` (600 queries with clicks and
  purchases), `judgments_sample.csv` (60 queries graded E/S/C/I). Hidden: graded judgments for 400 test
  queries, mixed across five languages including romanised and script variants.
- **Hidden requirements**
  - `grades` (missing; scoring) — Gains are E=3, S=1, C=0.5, I=0. The metric is mean nDCG@10.
  - `clicks_bias` (ambiguous; data semantics) — Clicks in the training log carry position bias (logged ranks
    are included). They are not relevance.
  - `sponsored_slots` (missing; business rule) — Exactly the positions 2 and 6 hold a sponsored item when one
    exists among the candidates. Sponsored items are never placed elsewhere in the top 10.
  - `oos_demote` (missing; business rule) — Out-of-stock items rank below every in-stock item with grade ≥ S.
  - `multilingual` (ambiguous; data semantics) — Queries come in zh/en/ko/ja/es. Titles may be in another
    language, and brands match across scripts (e.g. katakana and Latin).
  - `unit_queries` (ambiguous; calculation) — Queries such as "500ml" or "2L" must match normalised sizes
    (ml/L/oz).
  - `adult_filter` (missing; business rule) — Items in category `restricted` are excluded entirely for queries
    without an explicit term from a supplied list.
- **Rules**

| id | class | check | why |
|---|---|---|---|
| permutation | contractual | Output is a permutation of the input ids | Interface contract |
| sponsored_positions | contractual | Sponsored items only at 2 and 6, labelled by the front end | Advertiser contracts and the hidden-ad ban |
| restricted_excluded | contractual | No restricted items without a trigger term | Platform policy and youth-protection law |
| oos_demotion | physical | No out-of-stock item above an in-stock item with grade ≥ S | Out-of-stock items cannot be bought |
| house_brand_boost | business_policy | The house brand appears in the top 3 when any is a candidate | Commercial goal. It displaces better-graded items (about 3-5% nDCG) and raises self-preferencing risk |

- **Objective** — Maximize mean nDCG@10 on hidden queries. Reference: BM25 over title/brand with a
  character-n-gram tokenizer, plus log(n_reviews) and in-stock features, with deterministic tie-break by
  item_id. Headroom of 8-15% from cross-lingual matching and unit handling.
- **Hard tier** — Duplicate catalog rows with conflicting stock. A Shift_JIS/CP949 catalog copy. A late
  requirement: a third sponsored slot from next week, which the client later withdraws. Twist: the marketing
  lead demands the house-brand boost; legal (via the client) warns about self-preferencing.
- **Policy & language angles** — regulated_strict: no house-brand boost. NOTES must describe the ranking
  parameters (Art. 7(4a)). Localize the restricted trigger terms in each language. Watch for full-width digits
  and for Chinese/Japanese queries without spaces.
- **Authoring risks** — Judgments must be generated from latent attributes so they are reproducible.
  Guarantee that the slot rule and the out-of-stock rule never conflict: sponsored candidates are always in
  stock. Run the program in a sandbox with a time limit.
- **Sources**
  - https://github.com/amazon-science/esci-data
  - https://arxiv.org/abs/2206.06588
  - https://en.wikipedia.org/wiki/Discounted_cumulative_gain
  - https://en.wikipedia.org/wiki/Learning_to_rank
  - https://commission.europa.eu/law/law-topic/consumer-protection-law/unfair-commercial-practices-law/unfair-commercial-practices-directive_en
  - https://en.wikipedia.org/wiki/Digital_Services_Act

---

### Returns Fraud Analyst — `retail/returns_fraud_analyst`
- **Why it matters** — NRF puts US returns at $743 billion (14.5% of sales) in 2023 and 17.6% for online. 93%
  of retailers call return fraud a major problem. The common abuse patterns are wardrobing, receipt fraud,
  price switching and returning stolen goods. Statutory return rights differ: EU 14 days from delivery for
  distance sales, Japan 8 days for mail order unless the seller states its own return terms, China 7-day
  no-reason returns, Korea 7 days under the E-Commerce Act. A legitimate return inside the window must never be
  treated as fraud just for being a return.
- **Client & request** — Loss-prevention lead at an omnichannel apparel retailer: "Find the abusive returns
  in last quarter's data so we can act on them."
- **Deliverable** — Batch `return_flags.csv`: `return_id,flag,score`. `flag` ∈ {0,1} for every return;
  `score` ∈ [0,1].
- **World & data** — 25,000 customers, 120,000 orders, 18,000 returns. `orders.csv`, `order_lines.csv`
  (sku, category, price_paid), `returns.csv` (return_id, order_line_id, return_date, channel, reason_code,
  condition_code, refund_amount), `customers.csv` (customer_id, email_hash, phone_hash, address_hash,
  loyalty_tier). Hidden: the true abuse labels (wardrobing, cross-account serial returning, price switching).
- **Hidden requirements**
  - `windows` (missing; business rule) — Return windows are 30 days for apparel, 14 for electronics and 0 for
    underwear and swimwear unless defective. Online orders count from delivery_date, store orders from
    order_date.
  - `statutory_safe` (missing; business rule) — An online return within 14 days of delivery with condition
    "unused" is a statutory withdrawal and can never be flagged.
  - `linked_accounts` (ambiguous; data semantics) — Accounts sharing a phone_hash or address_hash count as one
    person for serial-return counts.
  - `wardrobing_pattern` (ambiguous; data semantics) — Event-wear SKUs bought before a weekend and returned
    with `condition=worn_tags_reattached` within 3 days.
  - `price_switch` (ambiguous; calculation) — refund_amount > price_paid on the line means price switching.
  - `exchanges` (ambiguous; data semantics) — `reason_code=EXCH` rows are exchanges, not refunds; exclude them
    from abuse rates.
  - `review_capacity` (missing; scoring) — The team can review at most 2% of returns (360). Score = recall of
    abusive refund value at that flag budget, minus a 1:5 cost for false flags.
  - `currency` (ambiguous; data semantics) — `refund_amount` is in minor units (cents) in the online channel
    and in major units in stores.
- **Rules**

| id | class | check | why |
|---|---|---|---|
| complete | contractual | One row per return_id | Deliverable contract |
| flag_budget | physical | ≤ 360 flags | Physical review capacity |
| statutory_protected | contractual | No flag on a statutory withdrawal | Consumer law; hard under every policy |
| loyalty_exempt | business_policy | Never flag the top loyalty tier | CRM preference. About 8% of abusive value sits in that tier, so the rule costs real recall |

- **Objective** — Maximize the net detected abusive refund value (as above). Reference: a rules score (window
  breach, price switch, linked-account return count ≥ 5 in 90 days, worn condition) ranked into the top 360.
  Headroom of 8-15% from a learned model and better linking.
- **Hard tier** — Duplicate returns from a re-sync. A stale customer file without the phone hash. A data
  correction to delivery dates. Twist: the store-ops director wants every no-receipt return flagged, but no
  receipt is not abuse; the client overrules.
- **Policy & language angles** — regulated_strict: no loyalty exception, and every flag rule documented
  (GDPR Art. 22 / PIPA profiling concerns). Localize reason and condition labels. Use day-first dates in the
  es locale.
- **Authoring risks** — The labels must be generated by the same mechanisms the hidden requirements describe.
  Keep the currency quirk detectable from magnitudes.
- **Sources**
  - https://www.nrf.com/research/2023-consumer-returns-retail-industry
  - https://nrf.com/research/2024-consumer-returns-retail-industry
  - https://en.wikipedia.org/wiki/Return_fraud
  - https://europa.eu/youreurope/citizens/consumers/shopping/returns/index_en.htm
  - https://www.no-trouble.caa.go.jp/what/mailorder/

---

### Store Staffing Planner — `retail/store_staffing_planner`
- **Why it matters** — Labour is retail's largest controllable cost, and workforce-management tools turn
  traffic forecasts into shifts. The binding constraints are legal and local. EU Working Time Directive: 11 h
  daily rest and a break once a day exceeds 6 h. Spain: 12 h between shifts, a 15-minute break over 6 h and a
  daily time record. California: a 30-minute meal before the end of the 5th hour, with one hour's pay as the
  penalty. Korea LSA Art. 54: 30 minutes per 4 hours. Japan LSA Art. 34: 45 minutes over 6 hours and 60 over 8.
- **Client & request** — Regional operations manager for 4 stores: "Staff the stores for next week based on
  the traffic forecast."
- **Deliverable** — Batch `roster.csv`: `employee_id,store_id,date,start,end,break_start,department`. Times are
  HH:MM on a 15-minute grid. One row per shift.
- **World & data** — 4 stores, 70 employees, 7 days, 30-minute traffic slots. `employees.csv` (id,
  home_store, skills, contract_hours, birth_date, is_manager, hourly_cost), `traffic_forecast.csv` (store,
  date, slot, customers), `availability.csv`, `store_hours.csv`. Hidden: the true service level as a function
  of staff per customer flow.
- **Hidden requirements**
  - `conversion` (missing; calculation) — Staff needed per slot = ceil(customers / 18) on the floor, plus 1
    cashier per 25 customers.
  - `break_rule` (missing; business rule) — Shifts over 6 h include an unpaid 30-minute break that starts
    between hours 3 and 5. Break time does not count as coverage.
  - `rest_11h` (missing; business rule) — ≥ 11 h between shifts, including the last shift of the previous week
    (`last_week.csv`).
  - `minors` (missing; business rule) — Employees under 18 on the shift date: ≤ 8 h a day, no work after
    22:00.
  - `opening_min` (missing; business rule) — ≥ 2 staff from 30 minutes before opening (cash-up and
    lone-working safety).
  - `contract_hours` (ambiguous; calculation) — contract_hours is weekly and paid. Rostered hours must lie
    within ±10% of it, and hours above 110% cost 1.5×.
  - `skills` (ambiguous; data semantics) — Pharmacy-counter slots need skill `PH`. The skills list is
    semicolon-separated.
  - `metric` (missing; scoring) — Cost = wages + €25 per understaffed staff-slot (lost sales).
- **Rules**

| id | class | check | why |
|---|---|---|---|
| availability | physical | Shifts only within availability | The person is not there |
| rest_and_breaks | contractual | 11 h rest, breaks as specified | Labour law; hard under every policy |
| minors_hours | contractual | Limits for under-18s | Youth labour law |
| skills | physical | Pharmacy slots staffed by PH | Licensed task |
| manager_on_duty | business_policy | A manager present every open hour | Key-holder policy. With 9 managers it forces extra paid hours and costs about 4-7% |

- **Objective** — Minimize total cost. Reference: greedy shift templates (4/6/8 h) laid over the demand
  profile, assigned by lowest cost while respecting constraints. Headroom of 6-12% from flexible breaks and
  split coverage.
- **Hard tier** — Duplicate availability rows. A CP1252 `employees.csv`. Client unavailable for one round.
  Late requirement: one store closes at 18:00 on Saturday for a stocktake. Twist: an employee turns 18 midweek,
  so the minor rule applies only before that date.
- **Policy & language angles** — Localize names, department labels and date formats. The world fixes one rule
  set and states it, and NOTES should name the local statute (KR, JP, ES, US-CA, CN). In Spain the 11 h EU
  minimum is raised to 12 h; the case uses 11 h but the es locale's NOTES should mention 12 h as a legal risk.
- **Authoring risks** — The traffic forecast is the only demand input. Make sure a feasible roster exists with
  the manager rule kept.
- **Sources**
  - https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32003L0088
  - https://www.boe.es/buscar/act.php?id=BOE-A-2015-11430
  - https://www.dir.ca.gov/dlse/faq_mealperiods.htm

---

### Marketing Budget Allocator — `retail/marketing_budget_allocator`
- **Why it matters** — Marketing-mix models are back as cookies and tracking decline. Google's open-source
  Meridian and Meta's Robyn both model carryover (geometric or Weibull adstock), Hill saturation, and a budget
  allocator with per-channel constraints, calibrated with geo experiments. Known pitfalls: seasonal demand
  mistaken for marketing effect, correlated spend, short-term bias, and lagged effects. Japan made undisclosed
  influencer advertising (stealth marketing) illegal under its Premiums and Representations Act from
  1 October 2023.
- **Client & request** — CMO of an online retailer: "Split next quarter's marketing budget across channels so
  we get the most out of it."
- **Deliverable** — Batch `budget.csv`: `channel,week,spend`. 13 weeks × 7 channels; spend in currency units.
- **World & data** — 7 channels (TV, search, social, display, influencer, email, retail media). 104 weeks of
  `spend_history.csv` (channel, week, spend, impressions), `sales_weekly.csv` (week, revenue, orders,
  promo_flag, holiday_flag), `contracts.csv` (channel, min_spend, period), `geo_tests.csv` (2 lift tests).
  Hidden: the true adstock decay, saturation and ROI per channel, plus the seasonal base.
- **Hidden requirements**
  - `total_budget` (missing; business rule) — The total is 3.0M, with ±1% tolerance and no carry-over.
  - `contract_min` (missing; business rule) — The TV upfront is 450k for the quarter and the retail-media
    commitment is 60k a month.
  - `adstock_lag` (ambiguous; calculation) — TV and influencer effects decay over about 4-6 weeks, so
    spend in weeks 12-13 mostly lands next quarter. Score only revenue inside the quarter plus a 4-week tail.
  - `seasonality` (ambiguous; data semantics) — The November peak in the history is seasonal base, not TV
    effect. Use `holiday_flag` and promo_flag as controls.
  - `calibration` (missing; calculation) — The geo tests give the true incremental ROI of search and social;
    the model must agree with them.
  - `gross_vs_net` (ambiguous; data semantics) — `revenue` is gross of returns. Margin is 38% of net revenue,
    and the return rate is 22%.
  - `influencer_disclosure` (missing; business rule) — Influencer spend is allowed only through the disclosed
    #ad programme, capped at 10% of budget (JP stealth-marketing rule, FTC endorsement guides).
  - `metric` (missing; scoring) — Score = incremental net margin − spend.
- **Rules**

| id | class | check | why |
|---|---|---|---|
| budget_total | contractual | Sum within ±1% of 3.0M | Approved budget |
| contract_minimums | contractual | Contract minimums met | Signed media contracts |
| non_negative | physical | spend ≥ 0 | Impossible otherwise |
| influencer_cap | contractual | Influencer ≤ 10% | Advertising disclosure law and programme terms |
| tv_floor | business_policy | TV ≥ 900k (twice the upfront) | Brand-team preference. Above the upfront, TV sits on the flat part of its curve, so the floor costs about 5-8% |

- **Objective** — Maximize incremental net margin minus spend, simulated in the world. Reference: a
  geometric-adstock and Hill model fitted per channel by grid search, then greedy marginal-ROI allocation in
  10k steps under constraints. Headroom of 6-12% from calibration and timing.
- **Hard tier** — Duplicate spend weeks. An updated contracts file arrives mid-task. Stakeholder conflict: the
  brand lead claims TV drives November. Twist: a deadline pulled in.
- **Policy & language angles** — Localize channel names and currency scaling: the KRW/JPY worlds keep the same
  numbers with a label only. Watch ISO week versus local fiscal week.
- **Authoring risks** — Saturation must be identifiable from spend variation in the history (inject planned
  variation). Keep the tail rule unambiguous.
- **Sources**
  - https://developers.google.com/meridian
  - https://developers.google.com/meridian/docs/basics/about-the-project
  - https://facebookexperimental.github.io/Robyn/docs/features/
  - https://en.wikipedia.org/wiki/Marketing_mix_modeling
  - https://www.caa.go.jp/policies/policy/representation/fair_labeling/stealth_marketing/
