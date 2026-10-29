"""Grocery daily demand forecast (original FDE-Bench v2 case).

A regional grocery chain wants a 14-day daily forecast per store x item for
ordering. The request only says "forecast what each store will sell"; the
rules that decide validity and quality (censored sales on stockout days,
returns logged as negative rows, a store closed on Sundays, the promotion plan
for the horizon, a one-off public holiday inside the horizon, a unit change of
one item, the display-stock floor for core items, WAPE per store) are in the
requirements and must be asked for.
"""

from __future__ import annotations

import datetime as dt
import math
import random
from dataclasses import dataclass, field
from pathlib import Path

from fdebench2.casekit import Fatal, labels, number, read_csv, write_csv

# ── world ────────────────────────────────────────────────────────────────────

HIST_START = dt.date(2024, 11, 4)        # Monday; 104 weeks of history
HORIZON_START = dt.date(2026, 11, 2)     # Monday
HORIZON_DAYS = 14
UNIT_CHANGE = dt.date(2026, 6, 1)        # I07 recorded per piece before this date, per 6-pack from it
PACK = 6
HORIZON_HOLIDAY = dt.date(2026, 11, 11)  # one-off regional holiday, known only to the client
CLOSED_STORE, CLOSED_WEEKDAY = "S4", 6   # S4 closes on Sundays
MIN_DISPLAY = 6.0
CORE_CATEGORIES = ("produce", "dairy")

STORES = {"S1": (1.30, 0.03), "S2": (1.00, 0.08), "S3": (0.85, 0.00), "S4": (0.60, 0.02), "S5": (1.10, -0.05)}
# item id: (category, base units/day at store scale 1, base stockout probability)
ITEMS = {
    "I01": ("produce", 80.0, 0.06), "I02": ("produce", 50.0, 0.08), "I03": ("produce", 2.6, 0.15),
    "I04": ("dairy", 90.0, 0.05), "I05": ("dairy", 36.0, 0.08), "I06": ("dairy", 3.0, 0.06),
    "I07": ("bakery", 25.0, 0.10), "I08": ("bakery", 20.0, 0.08), "I09": ("bakery", 45.0, 0.20),
    "I10": ("beverages", 60.0, 0.05), "I11": ("beverages", 24.0, 0.06), "I12": ("beverages", 15.0, 0.10),
}
WEEKDAY = {  # Monday .. Sunday
    "produce": (1.00, 0.90, 0.95, 1.00, 1.15, 1.35, 0.80),
    "dairy": (1.00, 0.95, 0.95, 1.00, 1.10, 1.30, 0.85),
    "bakery": (0.90, 0.85, 0.90, 0.95, 1.10, 1.45, 1.20),
    "beverages": (0.85, 0.85, 0.90, 0.95, 1.15, 1.40, 1.10),
}
SEASON = {"produce": (0.10, 200), "dairy": (0.05, 20), "bakery": (0.15, 355), "beverages": (0.30, 196)}  # amp, peak doy
PROMO_ELASTICITY = {"produce": 1.5, "dairy": 2.0, "bakery": 2.5, "beverages": 3.0}  # uplift = 1 + e * pct/100
HOLIDAY_EFFECT = {"produce": 1.35, "dairy": 1.20, "bakery": 1.80, "beverages": 1.55}
HIST_HOLIDAYS = [  # (date, holiday key); none falls in the horizon
    ("2024-12-25", "christmas"), ("2025-01-01", "new_year"), ("2025-04-18", "spring"), ("2025-05-01", "labour"),
    ("2025-08-15", "summer"), ("2025-10-12", "autumn"), ("2025-12-25", "christmas"), ("2026-01-01", "new_year"),
    ("2026-04-03", "spring"), ("2026-05-01", "labour"), ("2026-08-15", "summer"), ("2026-10-12", "autumn"),
]
NOISE = 0.07


@dataclass
class World:
    history: list[tuple] = field(default_factory=list)       # (date, store, item, units, promo_pct, stockout)
    holidays: list[tuple[str, str]] = field(default_factory=list)
    promo_plan: list[tuple] = field(default_factory=list)    # (store, item, start, end, pct) in the horizon
    truth: dict[tuple[str, str, str], float] = field(default_factory=dict)  # (store, item, date) -> demand (packs)

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


def _mean(store: str, item: str, day: dt.date, promo: int, holiday: bool) -> float:
    cat, base, _ = ITEMS[item]
    scale, trend = STORES[store]
    amp, peak = SEASON[cat]
    years = (day - HIST_START).days / 365.0
    m = base * scale * (1 + trend * years) * WEEKDAY[cat][day.weekday()]
    m *= 1 + amp * math.cos(2 * math.pi * (day.timetuple().tm_yday - peak) / 365.0)
    m *= 1 + PROMO_ELASTICITY[cat] * promo / 100.0
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
                p_out = ITEMS[i][2] + (0.20 if pct else 0.0)
                stockout = demand > 0 and rng.random() < p_out
                units = int(demand * rng.uniform(0.3, 0.85)) if stockout else demand
                w.history.append((ds, s, i, units, pct, stockout))
                if rng.random() < 0.03:
                    w.history.append((ds, s, i, -rng.randint(1, PACK if pieces else 2), pct, False))

    for day in w.horizon:
        for s in STORES:
            for i in ITEMS:
                pct = next((p[4] for p in w.promo_plan if p[0] == s and p[1] == i and p[2] <= day <= p[3]), 0)
                mean = _mean(s, i, day, pct, day == HORIZON_HOLIDAY) * math.exp(rng.gauss(0, NOISE))
                w.truth[(s, i, day.isoformat())] = 0.0 if is_closed(s, day) else float(_poisson(rng, mean))
    return w


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


def write_data(world: World, data_dir: Path, lang: str) -> None:
    c, v = labels(COLS, lang), labels(VALUES, lang)
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

COLUMNS = ("store_id", "item_id", "date", "forecast")


def evaluate_forecast(world: World, fc: dict[tuple[str, str, str], float], missing: int, dupes: int):
    violations: list[tuple[str, str]] = []
    if missing:
        violations.append(("complete_grid", f"{missing} store x item x date rows are missing"))
    if dupes:
        violations.append(("complete_grid", f"{dupes} store x item x date rows appear more than once"))
    neg = [k for k, x in fc.items() if x < 0]
    if neg:
        violations.append(("non_negative", f"{len(neg)} negative forecasts, e.g. {'/'.join(neg[0])}"))
    closed = [k for k, x in fc.items() if x != 0 and is_closed(k[0], dt.date.fromisoformat(k[2]))]
    if closed:
        violations.append(("closed_day_zero", f"{len(closed)} non-zero forecasts for {CLOSED_STORE} on Sundays, "
                                              f"e.g. {'/'.join(closed[0])}"))
    low = [k for k, x in fc.items() if ITEMS[k[1]][0] in CORE_CATEGORIES and x < MIN_DISPLAY
           and not is_closed(k[0], dt.date.fromisoformat(k[2]))]
    if low:
        violations.append(("min_display_stock", f"{len(low)} core-item forecasts below {MIN_DISPLAY:g} on open days, "
                                                f"e.g. {'/'.join(low[0])}"))
    wape = {}
    for s in STORES:
        err = tot = 0.0
        for (ks, ki, kd), actual in world.truth.items():
            if ks == s:
                err += abs(fc.get((ks, ki, kd), 0.0) - actual)
                tot += actual
        wape[s] = err / tot
    objective = sum(wape.values()) / len(wape)
    return violations, objective, {"wape_by_store": {s: round(x, 5) for s, x in wape.items()},
                                   "mean_wape": round(objective, 5)}


def score(world: World, submission_dir: Path) -> dict:
    try:
        rows = read_csv(submission_dir, "forecast.csv", COLUMNS)
        if not rows:
            raise Fatal("forecast.csv has no rows")
        horizon = {d.isoformat() for d in world.horizon}
        fc: dict[tuple[str, str, str], float] = {}
        dupes = 0
        for n, r in enumerate(rows, start=2):
            s, i, d = (str(r.get(k) or "").strip() for k in COLUMNS[:3])
            if s not in STORES:
                raise Fatal(f"forecast.csv line {n}: unknown store_id {s!r}")
            if i not in ITEMS:
                raise Fatal(f"forecast.csv line {n}: unknown item_id {i!r}")
            if d not in horizon:
                raise Fatal(f"forecast.csv line {n}: date {d!r} is not a YYYY-MM-DD date in the forecast horizon")
            if (s, i, d) in fc:
                dupes += 1
            fc[(s, i, d)] = number(r.get("forecast"), f"forecast.csv line {n} forecast")
        missing = len(world.truth) - len(fc)
        violations, objective, metrics = evaluate_forecast(world, fc, missing, dupes)
    except Fatal as e:
        return {"fatal": str(e)}
    return {"violations": violations, "objective": objective, "metrics": metrics}


# ── reference solution ───────────────────────────────────────────────────────

POOL = "*"  # the reference pools promo and holiday effects over all categories


def _forecast(world: World) -> dict[tuple[str, str, str], float]:
    """Censoring-aware weekday-level model with promo, holiday and seasonal multipliers, from the history only.

    Deliberately plain (recent mean level, effects pooled over categories) so a careful agent can beat it.
    """
    n = (HORIZON_START - HIST_START).days
    days = [HIST_START + dt.timedelta(days=t) for t in range(n)]
    hol = {d for d, _ in world.holidays}
    sales: dict[tuple[str, str], list[float]] = {(s, i): [0.0] * n for s in STORES for i in ITEMS}
    present = {k: [False] * n for k in sales}
    out = {k: [False] * n for k in sales}
    promo = {k: [0] * n for k in sales}
    for d, s, i, u, p, so in world.history:
        t = (dt.date.fromisoformat(d) - HIST_START).days
        k = (s, i)
        promo[k][t] = p
        if u < 0:
            continue  # returns are not demand
        x = u / PACK if i == "I07" and days[t] < UNIT_CHANGE else u
        sales[k][t] += x
        present[k][t] = True
        out[k][t] = out[k][t] or so

    holiday_day = [d.isoformat() in hol for d in days]
    result: dict[tuple[str, str, str], float] = {}
    promo_num: dict[tuple[str, int], float] = {}
    promo_den: dict[tuple[str, int], float] = {}
    hol_num: dict[str, float] = {}
    hol_den: dict[str, float] = {}
    level_now, level_ly, level_ly_h, wday = {}, {}, {}, {}
    for k in sales:
        cat = ITEMS[k[1]][0]
        x, ok = sales[k], [present[k][t] and not out[k][t] for t in range(n)]
        clean = [ok[t] and promo[k][t] == 0 and not holiday_day[t] for t in range(n)]
        by_wd = [[x[t] for t in range(n - 364, n) if clean[t] and days[t].weekday() == wd] for wd in range(7)]
        overall = sum(map(sum, by_wd)) / max(1, sum(map(len, by_wd)))
        w = [(sum(b) / len(b)) / overall if b and overall > 0 else 0.0 for b in by_wd]
        wday[k] = w
        v = [x[t] / w[days[t].weekday()] if clean[t] and w[days[t].weekday()] > 0 else None for t in range(n)]

        def level(a: int, b: int) -> float | None:
            vals = [v[t] for t in range(max(0, a), min(n, b)) if v[t] is not None]
            return sum(vals) / len(vals) if vals else None

        level_now[k] = level(n - 56, n) or 0.0
        level_ly[k] = level(n - 56 - 364, n - 364) or 0.0
        level_ly_h[k] = level(n - 364 - 14, n - 364 + HORIZON_DAYS + 14) or 0.0
        for t in range(n):
            if not ok[t] or (promo[k][t] == 0 and not holiday_day[t]):
                continue
            if promo[k][t] and holiday_day[t]:
                continue
            loc = level(t - 28, t + 29)
            wt = w[days[t].weekday()]
            if loc is None or wt == 0:
                continue
            if promo[k][t]:
                key = (POOL, promo[k][t])
                promo_num[key] = promo_num.get(key, 0.0) + x[t]
                promo_den[key] = promo_den.get(key, 0.0) + loc * wt
            else:
                hol_num[POOL] = hol_num.get(POOL, 0.0) + x[t]
                hol_den[POOL] = hol_den.get(POOL, 0.0) + loc * wt

    seas = {}
    for cat in WEEKDAY:
        keys = [k for k in sales if ITEMS[k[1]][0] == cat]
        seas[cat] = sum(level_ly_h[k] for k in keys) / max(1e-9, sum(level_ly[k] for k in keys))
    for day in world.horizon:
        ds = day.isoformat()
        for s in STORES:
            for i in ITEMS:
                cat = ITEMS[i][0]
                if is_closed(s, day):
                    result[(s, i, ds)] = 0.0
                    continue
                f = level_now[(s, i)] * seas[cat] * wday[(s, i)][day.weekday()]
                pct = next((p[4] for p in world.promo_plan if p[0] == s and p[1] == i and p[2] <= day <= p[3]), 0)
                if pct:
                    f *= promo_num[(POOL, pct)] / promo_den[(POOL, pct)]
                if day == HORIZON_HOLIDAY:
                    f *= hol_num[POOL] / hol_den[POOL]
                if cat in CORE_CATEGORIES:
                    f = max(MIN_DISPLAY, f)
                result[(s, i, ds)] = round(f, 2)
    return result


def _write(out_dir: Path, fc: dict[tuple[str, str, str], float]) -> None:
    write_csv(out_dir / "forecast.csv", list(COLUMNS), [[s, i, d, x] for (s, i, d), x in fc.items()])


def reference_solution(world: World, out_dir: Path) -> None:
    _write(out_dir, _forecast(world))


def _baseline(world: World) -> dict[tuple[str, str, str], float]:
    """Seasonal naive, the store's habit without an engineer: order what the till recorded on the same weekday of
    the last history week (2026-10-26 .. 2026-11-01), with S4's Sundays at 0 and the display floor on core items.

    No stockout, promotion or holiday adjustment; return rows (negative units) are not sales and are skipped.
    """
    last = {d.isoformat() for d in (HORIZON_START - dt.timedelta(days=k) for k in range(1, 8))}
    sold = {(s, i, d): float(u) for d, s, i, u, _, _ in world.history if d in last and u >= 0}
    result: dict[tuple[str, str, str], float] = {}
    for day in world.horizon:
        seen = (HORIZON_START - dt.timedelta(days=7 - day.weekday())).isoformat()  # same weekday, last week
        for s in STORES:
            for i in ITEMS:
                f = 0.0 if is_closed(s, day) else sold.get((s, i, seen), 0.0)
                if ITEMS[i][0] in CORE_CATEGORIES and not is_closed(s, day):
                    f = max(MIN_DISPLAY, f)
                result[(s, i, day.isoformat())] = f
    return result


def baseline_solution(world: World, out_dir: Path) -> None:
    _write(out_dir, _baseline(world))


def violating_examples(world: World) -> dict:
    """One deliverable per rule that breaks exactly that rule (for the validator)."""
    ref = _forecast(world)
    keys = list(ref)
    open_key = next(k for k in keys if ITEMS[k[1]][0] == "beverages" and not is_closed(k[0], dt.date.fromisoformat(k[2])))
    core_key = next(k for k in keys if ITEMS[k[1]][0] in CORE_CATEGORIES
                    and not is_closed(k[0], dt.date.fromisoformat(k[2])))
    closed_key = next(k for k in keys if is_closed(k[0], dt.date.fromisoformat(k[2])))

    def variant(change):
        def make(out: Path) -> None:
            fc = dict(ref)
            change(fc)
            _write(out, fc)
        return make

    return {
        "complete_grid": variant(lambda fc: fc.pop(open_key)),
        "non_negative": variant(lambda fc: fc.update({open_key: -1.0})),
        "closed_day_zero": variant(lambda fc: fc.update({closed_key: 5.0})),
        "min_display_stock": variant(lambda fc: fc.update({core_key: 1.0})),
    }
