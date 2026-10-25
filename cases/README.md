# Cases

Example cases in the FDE-Bench v2 format, each authored natively in zh / en / ko / ja / es and checked by
`fdebench2 validate-case`. Add your own cases next to them; every directory with a `case.yaml` is picked up.
Format and conventions: [DESIGN.md §3](../DESIGN.md#3-native-case-format).

| Case | Type | Domain | What the client asks | Hidden requirements (targets) | Bendable rule |
|---|---|---|---|---|---|
| `logistics_bakery_routing` | optimization | logistics | Plan Monday's van routes from the central kitchen to the cafés | 9: road/speed/unloading model, shift window, café closed this week, cold-chain partners, one visit, premium-first habit, lateness cost | `premium_first` |
| `services_callcenter_rostering` | optimization | services | Build next week's multilingual support roster | 9: one language per shift, 30-min coverage, holiday at 60% demand, contract limits, 11 h rest, leave dates (d/m/y, rejected requests), overtime, buddy rule, under-staffing penalty | `buddy_rule` |
| `retail_grocery_demand_forecast` | machine learning | retail | Forecast daily sales per store × item for two weeks | 9: stockout censoring, returns rows, store closed Sundays, promo plan, unlisted holiday, unit change pieces → 6-packs, minimum-display habit, WAPE metric, submission grid | `min_display_stock` |
