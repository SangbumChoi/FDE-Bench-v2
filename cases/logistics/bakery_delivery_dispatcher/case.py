"""Bakery morning delivery routing (original FDE-Bench v2 case).

A central kitchen delivers bread trays to cafés with a small van fleet on a Monday morning. The request only says
"plan the routes"; the rules that decide validity and quality are in the requirements and must be asked for.

Settings (case.yaml): three tiers, and a rule seed that draws the client's parameters. Easy is the routing core:
this week's tray limit per van, the café closed this week, the travel times (road distance, a constant 25 km/h,
unloading), the cost of a late minute and the vans back by 10:00. Medium adds the partner cold chain and, when the
rule seed draws it, the premium-first habit. Hard fixes the tray limit at 110 and adds the morning rush (30 km/h
before a drawn time, 20 km/h from it, also on a leg already under way), a drawn shift end, a dated event (V2 is in
the workshop until 06:40 on Monday) and a premium café manager's pressure to be served first. The data is the same
in every setting.

The ground truth audit (GT.md, docs/en/REVIEW.md "Ground truth audit"): the zero of the quality scale is the
dispatcher's hand plan (baseline_solution), the literal solution guesses the travel times the request never gives,
and the hooks below give the misreadings, the lazy plans, the solver that never asks, the stored best plans and
bounds (make_bounds.py) and a diagnostic per client fact.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import math
import random
from dataclasses import dataclass, field, replace
from pathlib import Path

import yaml

from fdebench2.cases import TIERS, Setting, param_pools
from fdebench2.casekit import Fatal, labels, read_json, write_csv

# ── world ────────────────────────────────────────────────────────────────────

DAY_START = 5 * 60            # vans may leave from 05:00
FAST, SLOW = 30.0, 20.0       # km/h in hard: before the morning rush, and from it
AVERAGE = 25.0                # km/h all morning in easy and medium
ROAD_FACTOR = 1.3
CAPACITY = 120                # max_trays in the data: the vans' racks
WORKSHOP = ("V2", 6 * 60 + 40)  # hard: V2 is in the workshop on Monday until 06:40
PRESSURE_CAFE = "C07"         # hard: its manager wants to be the first stop of the morning, before 06:30
PRESSURE_BY = 6 * 60 + 30
LATE_COST = 3.0               # one late minute at a café costs as much as this many minutes of van time
GRID = 5                      # minutes between the departures the reference tries
MAX_DRAWS = 400               # draws per seed before giving up on finding a usable world
MATTERS = 0.01                # build_world: the least effect, as a share of the objective, that counts as a change

_META = yaml.safe_load(Path(__file__).with_name("case.yaml").read_text(encoding="utf-8"))


def _minutes(hhmm: str) -> int:
    h, m = str(hhmm).split(":")
    return int(h) * 60 + int(m)


def _hhmm(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"


@dataclass(frozen=True)
class Travel:
    """How long the vans take: road distance as a multiple of the straight line, the speeds (km/h: all morning
    without a rush; before and from the rush with one) and the unloading time per stop (minutes plus minutes per
    tray). The client's model is the default; a plan made with another one (a misreading) is still scored with it."""

    road: float = ROAD_FACTOR
    average: float = AVERAGE
    fast: float = FAST
    slow: float = SLOW
    stop: float = 4.0
    per_tray: float = 0.2


TRAVEL = Travel()


@dataclass(frozen=True)
class Rules:
    """The rules in force in one setting, as the simulation reads them."""

    tier: str                     # whose fallback plan applies (see build_world)
    closed: str | None            # the café closed this week (None: every café open, see _strictest)
    capacity: int                 # trays per van this week (at most the racks' max_trays)
    shift_end: int                # every van back at the kitchen by then (minutes)
    late_weight: float            # one late minute costs as much as this many minutes of van time
    rush: int | None              # from then vans drive at SLOW, FAST before (None: AVERAGE all morning)
    cold_chain: bool              # partner cafés only by the refrigerated van
    premium_first: bool           # on every route, premium cafés before standard ones
    ready: tuple[tuple[str, int], ...] = ()   # (van, earliest departure) for vans held back
    travel: Travel = TRAVEL       # the travel model a plan is made with (scoring always uses the client's)
    first: tuple[str, int] | None = None   # (café, minute): it must open its route and be reached by then (only a
                                           # misreading: the C07 manager's demand followed)

    def earliest(self, van_id: str) -> int:
        return dict(self.ready).get(van_id, DAY_START)


def _rules(tier: str, p: dict) -> Rules:
    def at_least(t: str) -> bool:
        return TIERS.index(tier) >= TIERS.index(t)

    return Rules(tier=tier, closed=None if p["closed_cafe"] is None else str(p["closed_cafe"]),
                 capacity=int(p["van_capacity"]), shift_end=_minutes(p["shift_end"]), late_weight=LATE_COST,
                 rush=None if p["rush_start"] == "none" else _minutes(p["rush_start"]),
                 cold_chain=at_least("medium"), premium_first=at_least("medium") and bool(p["premium_first"]),
                 ready=(WORKSHOP,) if at_least("hard") else ())


def rules_of(setting: Setting) -> Rules:
    return _rules(setting.tier, setting.params)


POOLS = param_pools(_META, TIERS)     # {parameter: {tier: candidates}} from case.yaml


def _strictest(tier: str) -> Rules:
    """The strictest rules a setting of `tier` can draw, with every café open. A plan that keeps them keeps the
    rules of every setting of the tier once the closed café is dropped: a smaller load, a later shift end, a later
    rush, no habit and one stop fewer never bring a van back later."""
    pool = {name: by_tier[tier] for name, by_tier in POOLS.items()}
    rushes = [_minutes(v) for v in pool["rush_start"] if v != "none"]
    return _rules(tier, {"closed_cafe": None, "van_capacity": min(int(v) for v in pool["van_capacity"]),
                         "shift_end": _hhmm(min(_minutes(v) for v in pool["shift_end"])),
                         "rush_start": _hhmm(min(rushes)) if rushes else "none",
                         "premium_first": any(pool["premium_first"])})


def _headline(tier: str) -> Rules:
    """The tier's latest shift end and largest tray limit, with the first candidate of every other parameter: the
    morning in which the shift end and the tray limit are furthest from cutting the plan. The public panel's first
    rule seed draws it in medium and hard."""
    pool = {name: by_tier[tier] for name, by_tier in POOLS.items()}
    return _rules(tier, {**{name: values[0] for name, values in pool.items()},
                         "van_capacity": max(int(v) for v in pool["van_capacity"]),
                         "shift_end": _hhmm(max(_minutes(v) for v in pool["shift_end"]))})


def _stress(tier: str) -> Rules:
    """_headline with the tier's earliest shift end: where a plan that breaks only the tray limit (a too-full route
    still back in time) is hardest to find."""
    return replace(_headline(tier), shift_end=_strictest(tier).shift_end)


def _varies(tier: str, name: str) -> bool:
    """Whether the parameter has two or more candidates in the tier (the validator checks that it binds there)."""
    return len(set(map(str, POOLS[name][tier]))) >= 2


@dataclass
class Cafe:
    id: str
    district: int
    x: float
    y: float
    trays: int
    tier: str            # "A" premium, "B" standard
    open_min: int
    latest_min: int
    partner: bool        # cold-chain partner: refrigerated van only (medium and hard)
    home: float = field(default=0.0, repr=False, compare=False)            # straight-line km to the kitchen
    to: dict = field(default_factory=dict, repr=False, compare=False)      # straight-line km to each other café


@dataclass
class World:
    cafes: list[Cafe]
    vans: list[dict] = field(default_factory=list)
    fallback: dict[str, list[dict]] = field(default_factory=dict, repr=False)  # per tier: every café served
    cache: dict = field(default_factory=dict, repr=False, compare=False)  # reference plans per Rules

    def __post_init__(self):
        self.by_id = {c.id: c for c in self.cafes}
        for a in self.cafes:
            a.home = math.hypot(a.x, a.y)
            a.to = {b.id: math.hypot(a.x - b.x, a.y - b.y) for b in self.cafes}

    def cafe(self, cid: str) -> Cafe | None:
        return self.by_id.get(cid)

    def open_cafes(self, rules: Rules) -> list[Cafe]:
        return [c for c in self.cafes if c.id != rules.closed]


OPENINGS = [6 * 60, 6 * 60 + 30, 7 * 60, 7 * 60 + 30, 8 * 60]   # a standard café opens on one of these
PREMIUM_OPENS = (6 * 60, 6 * 60 + 30)    # a premium café opens first: the drawn opening, folded onto these two
PRESSURE_OPENS = (7 * 60, 7 * 60 + 30)   # the East Lake café (C07), premium, opens after its manager's 06:30


def _draw_world(rng: random.Random) -> World:
    """18 cafés round the kitchen. A standard café opens on the half hour from 06:00 to 08:00. Premium cafés
    (every third) open first, at 06:00 or 06:30, except the East Lake café (C07), whose manager wants to be served
    before 06:30 in hard: it opens at 07:00 or 07:30. deliver_by is 30, 45 or 60 minutes after opening."""
    cafes = []
    for i in range(18):
        ang, r = rng.uniform(0, 2 * math.pi), rng.uniform(2.0, 11.0)
        k = rng.randrange(len(OPENINGS))
        x, y, trays = round(r * math.cos(ang), 2), round(r * math.sin(ang), 2), rng.randint(8, 30)
        window = rng.choice([30, 45, 60])
        cid, premium = f"C{i + 1:02d}", i % 3 == 0
        open_min = (PRESSURE_OPENS[k % 2] if cid == PRESSURE_CAFE else PREMIUM_OPENS[k % 2] if premium
                    else OPENINGS[k])
        cafes.append(Cafe(id=cid, district=i, x=x, y=y, trays=trays, tier="A" if premium else "B",
                          open_min=open_min, latest_min=open_min + window, partner=i in (4, 9, 15)))
    vans = [{"id": f"V{i}", "capacity": CAPACITY, "refrigerated": i == 4} for i in range(1, 5)]
    return World(cafes, vans)


def _binds(world: World, plan: list[dict], rules: Rules, tier: str, solve) -> bool:
    """Whether the tier's shift end, tray limit and habit (where they vary) can change `plan`, the plan for the
    tier's _headline: it brings a van back after the earliest shift end, loads one above the smallest tray limit,
    and costs at least MATTERS more than `solve`'s plan without the premium-first habit."""
    routes = [[world.cafe(s) for s in r["stops"]] for r in plan]
    backs = [_run(rules, cafes, _minutes(r["depart"]))[0] for r, cafes in zip(plan, routes)]
    if _varies(tier, "shift_end") and max(backs) <= _strictest(tier).shift_end:
        return False
    if _varies(tier, "van_capacity") and \
            max(sum(c.trays for c in cafes) for cafes in routes) <= _strictest(tier).capacity:
        return False
    if _varies(tier, "premium_first") and rules.premium_first:
        free = replace(rules, premium_first=False)
        if simulate(world, solve(world, free), free)[1] > (1 - MATTERS) * simulate(world, plan, rules)[1]:
            return False
    return True


def _usable(world: World) -> bool:
    """Whether every setting has a valid plan and every parameter can change the answer.

    For each tier, the reference solver must serve every café under the tier's strictest rules (the plan is kept
    as the tier's fallback). And in every tier where a parameter has two or more candidates, the reference under
    _headline must bring a van back after the tier's earliest shift end, load one above its smallest tray limit and
    cost at least MATTERS more than the reference without the premium-first habit (_binds): otherwise the shift
    end, the tray limit or the habit could not change the plan there. (Which café is closed and when the rush
    starts change it in any world.) The quick construction screens the draw first, and the reference confirms it,
    since most draws fail and the reference takes longer."""
    for tier in TIERS:
        plan = _solve(world, _strictest(tier))
        if plan is None or simulate(world, plan, _strictest(tier))[0]:
            return False
        world.fallback[tier] = plan
    for solve in (_solve, _plan):
        for tier in TIERS:
            plan = solve(world, _headline(tier))
            if plan is None or not _binds(world, plan, _headline(tier), tier, solve):
                return False
    return True


def build_world(seed: int) -> World:
    """The first usable world drawn from the seed's random stream.

    Not every draw is usable. Some have no plan that keeps the strictest rules a setting can draw (only V4 may serve
    the three partner cafés, and when they open late and lie far apart V4 cannot also be back in time). In others a
    parameter cannot matter (every van is back before the earliest shift end anyway) or a rule cannot bind, so no
    plan breaks it alone. Draws continue from the same stream until the world is _usable and every rule has a plan
    that breaks only it under _stress("hard"), where a too-full route is hardest to find.
    """
    rng = random.Random(seed)
    for _ in range(MAX_DRAWS):
        world = _draw_world(rng)
        if not _usable(world):
            continue
        try:
            _breaking_plans(world, _stress("hard"))
        except NoExample:
            continue
        return world
    raise RuntimeError(f"seed {seed}: no usable world in {MAX_DRAWS} draws")


# ── data rendering ───────────────────────────────────────────────────────────

FILES = {
    "cafes": {"zh": "门店清单.csv", "en": "cafes.csv", "ko": "매장목록.csv", "ja": "店舗一覧.csv", "es": "cafeterias.csv"},
    "vans": {"zh": "车辆.csv", "en": "vans.csv", "ko": "차량.csv", "ja": "車両.csv", "es": "furgonetas.csv"},
}
COLS = {
    "id": {"zh": "门店编号", "en": "cafe_id", "ko": "매장코드", "ja": "店舗コード", "es": "id_cafeteria"},
    "name": {"zh": "门店名称", "en": "name", "ko": "매장명", "ja": "店舗名", "es": "nombre"},
    "x": {"zh": "东西坐标_km", "en": "x_km", "ko": "동서좌표_km", "ja": "東西座標_km", "es": "x_km"},
    "y": {"zh": "南北坐标_km", "en": "y_km", "ko": "남북좌표_km", "ja": "南北座標_km", "es": "y_km"},
    "trays": {"zh": "托盘数", "en": "trays", "ko": "트레이수", "ja": "トレー数", "es": "bandejas"},
    "tier": {"zh": "门店等级", "en": "tier", "ko": "매장등급", "ja": "店舗ランク", "es": "categoria"},
    "open": {"zh": "开门时间", "en": "opens", "ko": "오픈시간", "ja": "開店時刻", "es": "apertura"},
    "latest": {"zh": "最晚到货", "en": "deliver_by", "ko": "납품마감", "ja": "納品期限", "es": "entregar_antes"},
    "partner": {"zh": "合作品牌", "en": "partner_brand", "ko": "제휴브랜드", "ja": "提携ブランド", "es": "marca_asociada"},
    "van": {"zh": "车辆编号", "en": "van_id", "ko": "차량번호", "ja": "車両番号", "es": "id_furgoneta"},
    "capacity": {"zh": "最大托盘数", "en": "max_trays", "ko": "최대트레이", "ja": "最大トレー数", "es": "max_bandejas"},
    "fridge": {"zh": "冷藏车", "en": "refrigerated", "ko": "냉장차량", "ja": "冷蔵車", "es": "refrigerada"},
}
VALUES = {
    "A": {"zh": "旗舰", "en": "premium", "ko": "프리미엄", "ja": "旗艦", "es": "premium"},
    "B": {"zh": "标准", "en": "standard", "ko": "일반", "ja": "標準", "es": "estándar"},
    "yes": {"zh": "是", "en": "yes", "ko": "예", "ja": "はい", "es": "sí"},
    "no": {"zh": "否", "en": "no", "ko": "아니오", "ja": "いいえ", "es": "no"},
}
DISTRICTS = {
    "zh": ["河畔", "老城", "北站", "樱花路", "港口", "大学城", "东湖", "西门", "新区", "钟楼", "南山", "花园街",
           "金桥", "梧桐里", "市场口", "体育中心", "海湾", "古镇"],
    "en": ["Riverside", "Old Town", "North Station", "Cherry Lane", "Harbour", "University", "East Lake", "West Gate",
           "New District", "Clock Tower", "South Hill", "Garden Street", "Golden Bridge", "Maple Row", "Market Square",
           "Stadium", "Bayside", "Heritage Quarter"],
    "ko": ["강변", "구도심", "북역", "벚꽃길", "항구", "대학가", "동호수", "서문", "신도시", "시계탑", "남산", "정원길",
           "금빛다리", "단풍길", "시장광장", "종합운동장", "해안", "옛마을"],
    "ja": ["川辺", "旧市街", "北駅", "桜通り", "港町", "大学前", "東湖", "西門", "新市街", "時計台", "南山", "庭園通り",
           "金橋", "楓並木", "市場前", "競技場前", "湾岸", "古町"],
    "es": ["Ribera", "Casco Antiguo", "Estación Norte", "Calle de los Cerezos", "Puerto", "Ciudad Universitaria",
           "Lago Este", "Puerta Oeste", "Barrio Nuevo", "Torre del Reloj", "Colina Sur", "Calle del Jardín",
           "Puente Dorado", "Paseo de los Arces", "Plaza del Mercado", "Estadio", "Bahía", "Barrio Histórico"],
}
BRANCH = {"zh": "{d}店", "en": "{d} café", "ko": "{d}점", "ja": "{d}店", "es": "Cafetería {d}"}


def cafe_name(index: int, lang: str) -> str:
    """The name the data gives café C<index + 1> (the same in every world: districts follow the café ids)."""
    return BRANCH[lang].format(d=DISTRICTS[lang][index])


def write_data(world: World, data_dir: Path, lang: str) -> None:
    c, v = labels(COLS, lang), labels(VALUES, lang)
    rows = [[cf.id, cafe_name(cf.district, lang), cf.x, cf.y, cf.trays, v[cf.tier],
             _hhmm(cf.open_min), _hhmm(cf.latest_min), v["yes" if cf.partner else "no"]] for cf in world.cafes]
    write_csv(data_dir / FILES["cafes"][lang],
              [c["id"], c["name"], c["x"], c["y"], c["trays"], c["tier"], c["open"], c["latest"], c["partner"]], rows)
    write_csv(data_dir / FILES["vans"][lang], [c["van"], c["capacity"], c["fridge"]],
              [[vn["id"], vn["capacity"], v["yes" if vn["refrigerated"] else "no"]] for vn in world.vans])


# ── simulation and scoring ───────────────────────────────────────────────────

def _km(a: tuple[float, float], b: tuple[float, float], road: float = ROAD_FACTOR) -> float:
    return road * math.hypot(a[0] - b[0], a[1] - b[1])


def _drive(km: float, t: float, rush: int | None, travel: Travel = TRAVEL) -> float:
    """Minutes to drive `km` leaving at minute t: the average speed without a rush; else the fast speed before the
    rush and the slow one from it, also on a leg under way."""
    if rush is None:
        return km / travel.average * 60.0
    fast = km / travel.fast * 60.0
    if t + fast <= rush:
        return fast
    if t >= rush:
        return km / travel.slow * 60.0
    return (rush - t) + (km - (rush - t) / 60.0 * travel.fast) / travel.slow * 60.0


def _service(trays: int, travel: Travel = TRAVEL) -> float:
    return travel.stop + travel.per_tray * trays


def _run(rules: Rules, cafes: list[Cafe], depart: float, waits: bool = False) -> tuple:
    """(return time, late minutes) of a route through `cafes` leaving at `depart`; a van waits for opening.
    With waits=True also whether it waits anywhere."""
    t, late, waited, tr, rush, prev = float(depart), 0.0, False, rules.travel, rules.rush, None
    for cafe in cafes:
        km = (cafe.home if prev is None else prev.to[cafe.id]) * tr.road
        t += km / tr.average * 60.0 if rush is None else _drive(km, t, rush, tr)
        if t < cafe.open_min:
            t, waited = cafe.open_min, True
        if t > cafe.latest_min:
            late += t - cafe.latest_min
        t += tr.stop + tr.per_tray * cafe.trays
        prev = cafe
    if prev is not None:
        km = prev.home * tr.road
        t += km / tr.average * 60.0 if rush is None else _drive(km, t, rush, tr)
    return (t, late, waited) if waits else (t, late)


def _parse_time(v, what: str) -> int:
    if v is None:
        return DAY_START
    try:
        h, m = str(v).strip().split(":")
        return int(h) * 60 + int(m)
    except ValueError as e:
        raise Fatal(f"{what}: time must be HH:MM, got {v!r}") from e


def simulate(world: World, routes: list[dict], rules: Rules) -> tuple[list[tuple[str, str]], float, dict]:
    violations: list[tuple[str, str]] = []
    vans = {vn["id"]: vn for vn in world.vans}
    seen: dict[str, str] = {}
    total_duration = total_late = 0.0
    used_vans = set()
    for r in routes:
        van = str(r.get("van", ""))
        if van not in vans:
            raise Fatal(f"unknown van {van!r}")
        if van in used_vans:
            raise Fatal(f"van {van} has more than one route")
        used_vans.add(van)
        stops = [str(s) for s in r.get("stops", [])]
        if not stops:
            continue
        depart = _parse_time(r.get("depart"), f"{van}.depart")
        if depart < DAY_START:
            violations.append(("shift_window", f"{van} leaves at {_hhmm(depart)}, before 05:00"))
        if depart < rules.earliest(van):
            violations.append(("van_ready", f"{van} leaves at {_hhmm(depart)}, but it is in the workshop until "
                                            f"{_hhmm(rules.earliest(van))}"))
        cafes, seen_tier_b = [], False
        for sid in stops:
            cafe = world.cafe(sid)
            if cafe is None:
                raise Fatal(f"{van}: unknown stop {sid!r}")
            cafes.append(cafe)
            if sid in seen:
                violations.append(("serve_each_once", f"{sid} is served by both {seen[sid]} and {van}"))
            seen[sid] = van
            if sid == rules.closed:
                violations.append(("closed_cafe", f"{van} delivers to {sid}, which is closed this week"))
            if rules.cold_chain and cafe.partner and not vans[van]["refrigerated"]:
                violations.append(("cold_chain", f"{sid} is a cold-chain partner but {van} is not refrigerated"))
            if cafe.tier == "B":
                seen_tier_b = True
            elif seen_tier_b and rules.premium_first:
                violations.append(("premium_first", f"{van} serves premium café {sid} after a standard café"))
        back, late = _run(rules, cafes, depart)
        load, cap = sum(c.trays for c in cafes), min(vans[van]["capacity"], rules.capacity)
        if load > cap:
            violations.append(("van_capacity", f"{van} carries {load} trays > {cap}"))
        if back > rules.shift_end + 1e-9:
            violations.append(("shift_window", f"{van} returns at {_hhmm(int(math.ceil(back)))}, after "
                                               f"{_hhmm(rules.shift_end)}"))
        total_duration += back - depart
        total_late += late
    for cafe in world.open_cafes(rules):
        if cafe.id not in seen:
            violations.append(("serve_each_once", f"{cafe.id} is not served"))
    objective = total_duration + rules.late_weight * total_late
    return violations, objective, {"route_minutes": round(total_duration, 2), "late_minutes": round(total_late, 2)}


def score(world: World, submission_dir: Path, setting: Setting) -> dict:
    try:
        doc = read_json(submission_dir, "routes.json")
        routes = doc.get("routes") if isinstance(doc, dict) else None
        if not isinstance(routes, list):
            raise Fatal("routes.json must be an object with a 'routes' list")
        violations, objective, metrics = simulate(world, routes, rules_of(setting))
    except Fatal as e:
        return {"fatal": str(e)}
    return {"violations": violations, "objective": objective, "metrics": metrics}


# ── reference solution ───────────────────────────────────────────────────────

SHUFFLES = 30        # shuffled insertion orders tried when the plain greedy construction corners itself
RUIN_ROUNDS = 300    # ruin-and-recreate rounds that improve the reference
LNS_RUNS = (0.0, 0.01, 0.0)   # one ruin-and-recreate run per entry, from the i-th best start: its cooling threshold


class _Routes:
    """Route costs for one world and one set of rules, each route evaluated once (with its best departure)."""

    def __init__(self, world: World, rules: Rules, fine: bool = True):
        self.world, self.rules, self.fine = world, rules, fine
        self.vans = {vn["id"]: vn for vn in world.vans}
        self.memo: dict[tuple, tuple[float, int] | None] = {}

    def allowed(self, van_id: str, stops: list[str]) -> bool:
        """Capacity, the closed café, the cold chain and the habit (the route's timing aside)."""
        cafes = [self.world.cafe(s) for s in stops]
        rules, van = self.rules, self.vans[van_id]
        if sum(c.trays for c in cafes) > min(van["capacity"], rules.capacity) or rules.closed in stops:
            return False
        if rules.cold_chain and any(c.partner and not van["refrigerated"] for c in cafes):
            return False
        if rules.first and rules.first[0] in stops[1:]:
            return False
        tiers = [c.tier for c in cafes]
        return not (rules.premium_first and "B" in tiers and "A" in tiers[tiers.index("B"):])

    def best(self, van_id: str, stops: list[str]) -> tuple[float, int] | None:
        """(objective contribution, departure) of the route at its best departure (the GRID, then, when fine, to the
        minute around its best step), or None if no departure keeps every rule."""
        key = (van_id, tuple(stops))
        if key not in self.memo:
            self.memo[key] = self._best(van_id, stops)
        return self.memo[key]

    def _best(self, van_id: str, stops: list[str]) -> tuple[float, int] | None:
        """The scan of the GRID skips what cannot win. Leaving earlier only to wait longer at the first café gives
        the same day one grid step longer, so it starts at the last departure that still waits there. Once a
        departure waits nowhere, leaving later is never cheaper (no waiting to save, drives no shorter, lateness no
        smaller), so it stops there; and at the first departure that brings the van back after the shift end."""
        if not stops:
            return 0.0, self.rules.earliest(van_id)
        if not self.allowed(van_id, stops):
            return None
        cafes, rules, best = [self.world.cafe(s) for s in stops], self.rules, None
        tr = rules.travel
        first, km = cafes[0], _km((0.0, 0.0), (cafes[0].x, cafes[0].y), tr.road)
        lo = rules.earliest(van_id)
        if rules.first and rules.first[0] == first.id:
            # reached by the demanded minute: the latest departure that makes it is the cheapest (the van waits
            # for the opening either way)
            depart = int(math.floor(rules.first[1] - _drive(km, rules.first[1], rules.rush, tr) + 1e-9))
            while depart >= lo and depart + _drive(km, depart, rules.rush, tr) > rules.first[1] + 1e-9:
                depart -= 1
            if depart < lo:
                return None
            back, late = _run(rules, cafes, depart)
            return None if back > rules.shift_end + 1e-9 else (back - depart + rules.late_weight * late, depart)
        start = lo + max(0, int((first.open_min - _drive(km, 0.0, None if rules.rush is None else 10 ** 6, tr) - lo)
                                    // GRID)) * GRID
        while start > lo and start + _drive(km, start, rules.rush, tr) > first.open_min:
            start -= GRID
        for depart in range(start, rules.shift_end, GRID):
            back, late, waited = _run(rules, cafes, depart, waits=True)
            if back > rules.shift_end + 1e-9:
                break                     # leaving later never brings a van back earlier
            cost = back - depart + rules.late_weight * late
            if best is None or cost < best[0]:
                best = (cost, depart)
            if not waited:
                break
        if best is not None and self.fine:   # then to the minute around the best step (a departure is HH:MM)
            for depart in range(max(lo, best[1] - GRID + 1), best[1] + GRID):
                back, late = _run(rules, cafes, depart)
                cost = back - depart + rules.late_weight * late
                if back <= rules.shift_end + 1e-9 and cost < best[0] - 1e-9:
                    best = (cost, depart)
        return best

    def cost(self, van_id: str, stops: list[str]) -> float | None:
        best = self.best(van_id, stops)
        return None if best is None else best[0]

    def plan(self, routes: dict[str, list[str]]) -> list[dict]:
        return [{"van": vid, "depart": _hhmm(self.best(vid, stops)[1]), "stops": stops}
                for vid, stops in routes.items() if stops]


def _insert_all(rc: _Routes, order: list[Cafe], routes: dict[str, list[str]]) -> bool:
    """Cheapest feasible insertion of each café of `order`, in turn (routes change in place).

    False when a café fits on no route."""
    for cafe in order:
        best = None
        for vid, stops in routes.items():
            base = rc.cost(vid, stops)
            if base is None:
                continue
            for pos in range(len(stops) + 1):
                cand = stops[:pos] + [cafe.id] + stops[pos:]
                cost = rc.cost(vid, cand)
                if cost is not None and (best is None or cost - base < best[0]):
                    best = (cost - base, vid, cand)
        if best is None:
            return False
        routes[best[1]] = best[2]
    return True


def _starts(rc: _Routes):
    """(insertion order, initial routes) for the construction, tried in turn until one places every café.

    First the plain greedy: cold-chain partners first when only the refrigerated van can take them, then the rest
    by tier, biggest first. Greedy insertion can corner itself (two partners in an order that leaves V4 no time for
    the third, or the last cafés finding no van with room and time), so next the refrigerated van starts from each
    workable order of the partners, cheapest first, and last from the cheapest one with the others in shuffled
    orders.
    """
    world, rules = rc.world, rc.rules
    chilled = [c for c in world.open_cafes(rules) if c.partner and rules.cold_chain]
    order = sorted(world.open_cafes(rules), key=lambda c: (c not in chilled, c.tier, -c.trays))
    yield order, {}
    fridge = next(vn["id"] for vn in world.vans if vn["refrigerated"])
    rest = [c for c in order if c not in chilled]
    seeded = []
    for perm in itertools.permutations([c.id for c in chilled]) if chilled else ():
        cost = rc.cost(fridge, list(perm))
        if cost is not None:
            seeded.append((cost, list(perm)))
    seeded.sort()
    for _, perm in seeded:
        yield rest, {fridge: perm}
    rng = random.Random(0)
    for _ in range(SHUFFLES if seeded or not chilled else 0):
        shuffled = rest[:]
        rng.shuffle(shuffled)
        yield shuffled, ({fridge: seeded[0][1]} if seeded else {})


def _relocate(rc: _Routes, routes: dict[str, list[str]]) -> dict[str, list[str]]:
    """Move single stops to their cheapest place while the total objective drops (routes change in place)."""
    improved = True
    while improved:
        improved = False
        for src in list(routes):
            for sid in list(routes[src]):
                src_without = [s for s in routes[src] if s != sid]
                base_src = rc.cost(src, src_without)
                if base_src is None:
                    continue
                gain_src = rc.cost(src, routes[src]) - base_src
                for dst in routes:
                    target = routes[dst] if dst != src else src_without
                    base_dst = rc.cost(dst, target)
                    if base_dst is None:
                        continue
                    for pos in range(len(target) + 1):
                        cand = target[:pos] + [sid] + target[pos:]
                        cost = rc.cost(dst, cand)
                        if cost is not None and cost - base_dst < gain_src - 1e-6:
                            routes[src] = src_without if dst != src else cand
                            if dst != src:
                                routes[dst] = cand
                            improved = True
                            break
                    if improved:
                        break
                if improved:
                    break
            if improved:
                break
    return routes


def _construct(rc: _Routes) -> dict[str, list[str]] | None:
    """Routes that break no rule by greedy insertion (see _starts), or None if every start corners itself."""
    for order, start in _starts(rc):
        routes = {vid: list(start.get(vid, [])) for vid in rc.vans}
        if _insert_all(rc, order, routes):
            return routes
    return None


def _solve(world: World, rules: Rules) -> list[dict] | None:
    """Routes that break no rule (greedy insertion, then single-stop relocation), or None if none is found."""
    rc = _Routes(world, rules)
    routes = _construct(rc)
    return None if routes is None else rc.plan(_relocate(rc, routes))


def _total(rc: _Routes, routes: dict[str, list[str]]) -> float:
    return sum(rc.cost(vid, stops) for vid, stops in routes.items())


def _swap(rc: _Routes, routes: dict[str, list[str]]) -> bool:
    """The first exchange of two stops on different routes (each taking the other's place) that lowers the total
    objective, made in place; False when none does."""
    vids = list(routes)
    for a, b in itertools.combinations(vids, 2):
        base = rc.cost(a, routes[a]) + rc.cost(b, routes[b])
        for i, j in itertools.product(range(len(routes[a])), range(len(routes[b]))):
            ra, rb = routes[a][:], routes[b][:]
            ra[i], rb[j] = routes[b][j], routes[a][i]
            ca, cb = rc.cost(a, ra), rc.cost(b, rb)
            if ca is not None and cb is not None and ca + cb < base - 1e-6:
                routes[a], routes[b] = ra, rb
                return True
    return False


def _two_opt(rc: _Routes, routes: dict[str, list[str]]) -> bool:
    """The first reversal of a stretch of one route that lowers its objective, made in place; False when none does."""
    for vid, stops in routes.items():
        base = rc.cost(vid, stops)
        for i, j in itertools.combinations(range(len(stops)), 2):
            cand = stops[:i] + stops[i:j + 1][::-1] + stops[j + 1:]
            cost = rc.cost(vid, cand)
            if cost is not None and cost < base - 1e-6:
                routes[vid] = cand
                return True
    return False


def _polish(rc: _Routes, routes: dict[str, list[str]]) -> dict[str, list[str]]:
    """Local search to a local optimum: single-stop relocation, exchanges between routes and reversals within one."""
    while True:
        _relocate(rc, routes)
        if not (_swap(rc, routes) or _two_opt(rc, routes)):
            return routes


def _ruin_recreate(rc: _Routes, routes: dict[str, list[str]], rounds: int = RUIN_ROUNDS, seed: int = 0,
                   cooling: float = 0.0) -> dict[str, list[str]]:
    """Large-neighbourhood search: take 2-5 cafés out (a café and its nearest neighbours in place and opening time,
    cafés at random, or a stretch of one route) and put them back by cheapest insertion in a random order, keeping
    the result when the total objective drops and, while the search is young, sometimes when it rises a little
    (a cooling threshold), from the best plan found so far every hundred rounds. Taking cafés out never breaks a
    rule (an earlier arrival everywhere), so every round starts from a valid plan. Deterministic: its random choices
    come from a fixed seed. The best plan found is polished by local search."""
    rng = random.Random(seed)
    world = rc.world
    best = cur = {vid: list(stops) for vid, stops in routes.items()}
    best_cost = cur_cost = _total(rc, routes)
    ids = [s for stops in routes.values() for s in stops]
    if len(ids) < 3:
        return _polish(rc, best)

    def near(centre: Cafe, s: str) -> float:
        c = world.cafe(s)
        return _km((centre.x, centre.y), (c.x, c.y)) + abs(c.open_min - centre.open_min) / 6.0

    for k in range(rounds):
        size = rng.randint(2, min(5, len(ids)))
        kind = k % 3
        if kind == 0:
            centre = world.cafe(rng.choice(ids))
            out = sorted(ids, key=lambda s: (near(centre, s), s))[:size]
        elif kind == 1:
            out = rng.sample(ids, size)
        else:
            vid = rng.choice([v for v, stops in cur.items() if stops])
            i = rng.randrange(len(cur[vid]))
            out = cur[vid][i:i + size] or cur[vid][-1:]
        rng.shuffle(out)
        cand = {vid: [s for s in stops if s not in out] for vid, stops in cur.items()}
        if _insert_all(rc, [world.cafe(s) for s in out], cand):
            cost = _total(rc, cand)
            threshold = cooling * cur_cost * max(0.0, 1.0 - k / (0.7 * rounds))
            if cost < cur_cost - 1e-6 or cost < cur_cost + threshold * rng.random():
                cur, cur_cost = cand, cost
                if cost < best_cost - 1e-6:
                    best, best_cost = cand, cost
        if k % 100 == 99:
            cur, cur_cost = best, best_cost
    return _polish(rc, best)


def _plan(world: World, rules: Rules) -> list[dict]:
    """The reference routes under `rules` (computed once per world and rules).

    Starts, each polished by local search: the greedy construction, the world's fallback without the closed café
    (valid under any rules a setting of its tier draws, so a setting always has one; a misreading may need another
    tier's) and the dispatcher's own plan, those that keep the rules. Ruin and recreate improves them further (one
    run per entry of LNS_RUNS, from the best starts in turn) with departures on the GRID, and the best result is
    polished again with departures to the minute. The greedy construction is not monotone in the rules (a looser
    shift can corner it where a tighter one does not), which is why the fallbacks are always tried too."""
    if rules not in world.cache:
        rc = _Routes(world, rules, fine=False)
        found = []
        built = _construct(rc)
        if built is not None:
            found.append(built)
        tiers = [rules.tier] + [t for t in TIERS if t != rules.tier]
        sources = [world.fallback[t] for t in tiers if t in world.fallback] + [_client_way(world, rules)]
        for plan in sources:
            routes = {vid: [] for vid in rc.vans}
            for r in plan:
                routes[r["van"]] = [s for s in r["stops"] if s != rules.closed]
            variants = [routes]
            if rules.first:             # the demanded café moved to the front of each route in turn
                cid = rules.first[0]
                variants = [{v: ([cid] if v == vid else []) + [s for s in stops if s != cid]
                             for v, stops in routes.items()} for vid in routes]
            found += [r for r in variants if all(rc.cost(vid, stops) is not None for vid, stops in r.items())]
        if not found:
            raise ValueError("no start keeps the rules")
        found = sorted((_polish(rc, {vid: list(stops) for vid, stops in r.items()}) for r in found),
                       key=lambda routes: _total(rc, routes))
        runs = [_ruin_recreate(rc, found[min(i, len(found) - 1)], seed=i, cooling=cool)
                for i, cool in enumerate(LNS_RUNS)]
        fine = _Routes(world, rules)
        world.cache[rules] = fine.plan(_polish(fine, min(runs, key=lambda routes: _total(rc, routes))))
    return json.loads(json.dumps(world.cache[rules]))


def reference_solution(world: World, out_dir: Path, setting: Setting) -> None:
    plan = _plan(world, rules_of(setting))
    (out_dir / "routes.json").write_text(json.dumps({"routes": plan}, indent=2), encoding="utf-8")


# ── baseline: the dispatcher's own plan ──────────────────────────────────────

def _leave_for(rules: Rules, van_id: str, first: Cafe) -> int:
    """The minute a van leaves to reach `first` as it opens (rounded down), or as early as it may if that is later."""
    km = _km((0.0, 0.0), (first.x, first.y))
    d = first.open_min - _drive(km, 0.0, None if rules.rush is None else 10 ** 6)
    for _ in range(8):                  # with a rush the drive depends on when the van leaves
        d = first.open_min - _drive(km, d, rules.rush)
    return max(rules.earliest(van_id), int(math.floor(d + 1e-9)))


def _habit_route(world: World, rules: Rules, van_id: str, stops: list[str]) -> tuple[int, float, float] | None:
    """(departure, return, arrival at the last stop) of a round as the dispatcher sends it, or None when it breaks a
    rule: this week's tray limit, the cold chain, the premium-first habit (the rules the dispatcher knows) or the
    shift end."""
    cafes = [world.cafe(s) for s in stops]
    van = next(vn for vn in world.vans if vn["id"] == van_id)
    if sum(c.trays for c in cafes) > min(van["capacity"], rules.capacity):
        return None
    if rules.cold_chain and any(c.partner and not van["refrigerated"] for c in cafes):
        return None
    tiers = [c.tier for c in cafes]
    if rules.premium_first and "B" in tiers and "A" in tiers[tiers.index("B"):]:
        return None
    depart = _leave_for(rules, van_id, cafes[0])
    back, _ = _run(rules, cafes, depart)
    if back > rules.shift_end + 1e-9:
        return None
    pos, t, arrive = (0.0, 0.0), float(depart), float(depart)
    for c in cafes:
        t += _drive(_km(pos, (c.x, c.y)), t, rules.rush)
        arrive = t
        t = max(t, c.open_min) + _service(c.trays)
        pos = (c.x, c.y)
    return depart, back, arrive


def _dispatch(world: World, rules: Rules, order: list[Cafe]) -> tuple[dict[str, list[str]] | None, Cafe | None]:
    """(rounds, None), or (None, the café that fits nowhere): the cafés of `order` given out in turn, each at the end
    of the round of the van that can be there first; else squeezed in where it adds the fewest route minutes; else
    squeezed in after moving one café of that round to the end of another van's round (or squeezed in there)."""
    vans = [vn["id"] for vn in world.vans]
    rounds: dict[str, list[str]] = {vid: [] for vid in vans}

    def minutes(vid: str, stops: list[str]) -> float | None:
        if not stops:
            return 0.0
        sent = _habit_route(world, rules, vid, stops)
        return None if sent is None else sent[1] - sent[0]

    def squeeze(cid: str, rounds: dict[str, list[str]], skip: str | None = None):
        """(added minutes, van, new round) of the cheapest place for cid on any round (not `skip`'s)."""
        best = None
        for vid in vans:
            if vid == skip:
                continue
            now = minutes(vid, rounds[vid])
            for pos in range(len(rounds[vid]) + 1):
                stops = rounds[vid][:pos] + [cid] + rounds[vid][pos:]
                after = minutes(vid, stops)
                if after is not None and now is not None and (best is None or (after - now, vid, pos) < best[:3]):
                    best = (after - now, vid, pos, stops)
        return None if best is None else (best[0], best[1], best[3])

    for cafe in order:
        best = None
        for vid in vans:
            sent = _habit_route(world, rules, vid, rounds[vid] + [cafe.id])
            if sent is not None and (best is None or (sent[2], vid) < best[:2]):
                best = (sent[2], vid)
        if best is not None:
            rounds[best[1]].append(cafe.id)
            continue
        found = squeeze(cafe.id, rounds)
        if found is None:
            for vid in vans:
                for out in rounds[vid]:
                    rest = [s for s in rounds[vid] if s != out]
                    placed = squeeze(cafe.id, {**rounds, vid: rest})
                    if placed is None or placed[1] != vid:
                        continue
                    moved = squeeze(out, {**rounds, vid: placed[2]}, skip=vid)
                    if moved is not None:
                        cost = placed[0] + moved[0]
                        if found is None or cost < found[0]:
                            found = (cost, vid, placed[2], moved[1], moved[2])
            if found is None:
                return None, cafe
            rounds[found[3]] = found[4]
        rounds[found[1]] = found[2]
    return rounds, None


HABIT_ORDER_MAX = 7           # the dispatcher sorts out the order of a round of up to this many cafés


def _round_cost(world: World, rules: Rules, van_id: str, stops: list[str]) -> float | None:
    """Minutes out plus the lateness cost of a round as the dispatcher sends it (None: it breaks a rule)."""
    sent = _habit_route(world, rules, van_id, stops)
    if sent is None:
        return None
    return sent[1] - sent[0] + rules.late_weight * _run(rules, [world.cafe(s) for s in stops], sent[0])[1]


def _sorted_round(world: World, rules: Rules, van_id: str, stops: list[str]) -> list[str]:
    """The round's cafés in the order that serves them best, the van leaving to reach the first as it opens (the
    round as given out when it has more than HABIT_ORDER_MAX cafés or no other order keeps the rules)."""
    if not stops:
        return stops
    best = (_round_cost(world, rules, van_id, stops), stops)
    if 1 < len(stops) <= HABIT_ORDER_MAX:
        for perm in itertools.permutations(stops):
            cost = _round_cost(world, rules, van_id, list(perm))
            if cost is not None and (best[0] is None or cost < best[0] - 1e-9):
                best = (cost, list(perm))
    return best[1]


def _habit(world: World, rules: Rules, by_deadline: bool = False) -> list[dict] | None:
    """The dispatcher's plan giving out the cafés by opening time, or by deliver_by (see baseline_solution); None
    when no order of giving out the cafés works."""
    order = sorted(world.open_cafes(rules), key=lambda c: (not (c.partner and rules.cold_chain),
                                                           c.tier if rules.premium_first else "",
                                                           *((c.latest_min, c.open_min) if by_deadline
                                                             else (c.open_min, c.latest_min)), c.id))
    first: list[Cafe] = []
    for _ in range(len(order)):
        rounds, stuck = _dispatch(world, rules, first + [c for c in order if c not in first])
        if rounds is not None:
            rounds = {vid: _sorted_round(world, rules, vid, stops) for vid, stops in rounds.items()}
            return [{"van": vid, "depart": _hhmm(_habit_route(world, rules, vid, stops)[0]), "stops": stops}
                    for vid, stops in rounds.items() if stops]
        if stuck in first:
            return None
        first.append(stuck)
    return None


def _fits(world: World, rules: Rules, van_id: str, stops: list[str]) -> bool:
    """The route leaving as early as the van may breaks no rule (cafés on other routes aside)."""
    route = {"van": van_id, "depart": _hhmm(rules.earliest(van_id)), "stops": stops}
    return all(rule == "serve_each_once" for rule, _ in simulate(world, [route], rules)[0])


def _sweep(world: World, rules: Rules, start: float) -> dict[str, list[str]] | None:
    """The map split into slices round the kitchen, cafés taken by bearing from `start` (None if a café fits on no
    van): V4 takes the partner cafés first when the cold chain applies, and every van serves its cafés in the order
    they open, premium cafés first while the habit holds."""
    vans = [vn["id"] for vn in world.vans]
    fridge = next(vn["id"] for vn in world.vans if vn["refrigerated"])
    fixed = {vid: [] for vid in vans}
    chilled = [c.id for c in world.open_cafes(rules) if c.partner] if rules.cold_chain else []
    if chilled:
        orders = [list(p) for p in itertools.permutations(chilled) if _fits(world, rules, fridge, list(p))]
        if not orders:
            return None
        fixed[fridge] = min(orders, key=lambda p: simulate(
            world, [{"van": fridge, "depart": _hhmm(rules.earliest(fridge)), "stops": p}], rules)[2]["route_minutes"])
    extra: dict[str, list[str]] = {vid: [] for vid in vans}

    def route(vid: str, more: tuple[str, ...] = ()) -> list[str]:
        cafes = sorted((world.cafe(s) for s in extra[vid] + list(more)),
                       key=lambda c: (c.tier if rules.premium_first else "", c.open_min, c.id))
        return fixed[vid] + [c.id for c in cafes]

    order = [vid for vid in vans if vid != fridge] + [fridge]
    rest = sorted((c for c in world.open_cafes(rules) if c.id not in chilled),
                  key=lambda c: ((math.atan2(c.y, c.x) - start) % (2 * math.pi), c.id))
    i, left = 0, []
    for c in rest:
        while i < len(order) and not _fits(world, rules, order[i], route(order[i], (c.id,))):
            i += 1
        (extra[order[i]] if i < len(order) else left).append(c.id)
    for cid in left:
        vid = next((v for v in order if _fits(world, rules, v, route(v, (cid,)))), None)
        if vid is None:
            return None
        extra[vid].append(cid)
    return {vid: route(vid) for vid in vans}


def _timed(world: World, rules: Rules, routes: dict[str, list[str]]) -> list[dict]:
    """Rounds with each van leaving so that it reaches its first café as it opens (when that keeps the rules the
    dispatcher checks; else as early as it may)."""
    plan = []
    for vid, stops in routes.items():
        if stops:
            sent = _habit_route(world, rules, vid, stops)
            plan.append({"van": vid, "depart": _hhmm(sent[0] if sent else rules.earliest(vid)), "stops": stops})
    return plan


def _slices(world: World, rules: Rules) -> list[dict] | None:
    """The dispatcher's older way: the map split into four slices round the kitchen (from due west, the next café
    round when a start leaves one over), each round in its best order and each van leaving to reach its first café
    as it opens; None when no start places every café."""
    first = sorted((c for c in world.open_cafes(rules) if not (c.partner and rules.cold_chain)),
                   key=lambda c: ((math.atan2(c.y, c.x) - math.pi) % (2 * math.pi), c.id))
    for start in [math.pi] + [math.atan2(c.y, c.x) for c in first[1:]]:
        routes = _sweep(world, rules, start)
        if routes is not None:
            routes = {vid: _sorted_round(world, rules, vid, stops) for vid, stops in routes.items()}
            plan = _timed(world, rules, routes)
            return None if simulate(world, plan, rules)[0] else plan
    return None


def _client_way(world: World, rules: Rules) -> list[dict]:
    """baseline_solution's plan (computed once per world and rules)."""
    key = ("habit", rules)
    if key not in world.cache:
        plans = [p for p in (_habit(world, rules), _habit(world, rules, by_deadline=True), _slices(world, rules))
                 if p is not None]
        if plans:
            plan = min(plans, key=lambda p: simulate(world, p, rules)[1])
        else:
            routes = {vn["id"]: [] for vn in world.vans}
            for r in world.fallback[rules.tier]:
                routes[r["van"]] = [s for s in r["stops"] if s != rules.closed]
            plan = [{"van": vid, "depart": _hhmm(rules.earliest(vid)), "stops": stops}
                    for vid, stops in routes.items() if stops]
        world.cache[key] = plan
    return json.loads(json.dumps(world.cache[key]))


def baseline_solution(world: World, out_dir: Path, setting: Setting) -> None:
    """What the client does without an engineer: the dispatcher's habit, as the requirements describe it.

    The dispatcher draws up the morning by hand in three ways and drives the one that costs least (minutes out plus
    lateness). His usual way goes through the cafés in the order they open (the earlier deliver_by first among those
    that open together; the partner cafés first when the cold chain gives them to V4, and premium cafés before all
    standard ones while the premium-first habit holds), or the same by deliver_by (the earlier opening first among
    equal ones), and gives each one to the van that can be there first, at the end of that van's round, as long as
    the van keeps this week's tray limit, is back by the end of the shift and, when the cold chain applies, is the
    refrigerated V4 for a partner café. A café that no round can take at its end is squeezed in where it adds the
    fewest route minutes, if need be after moving one café of that round to another; one that still fits nowhere is
    given out first and he starts again. His older way splits the map into four slices round the kitchen, one per van (V4 with the partner
    cafés when the cold chain applies). Either way he then puts each round in the order that serves it best (rounds
    of up to HABIT_ORDER_MAX cafés), and each van leaves so that it reaches its first café as it opens (in hard V2
    not before it is out of the workshop). He knows the client's rules and travel times but plans by hand: a café
    never moves to another van once the rounds are made. If neither way places every café, the world's fallback
    routes without the closed café are driven, every van leaving as early as it may (always valid; not needed in
    any world checked).
    """
    plan = _client_way(world, rules_of(setting))
    (out_dir / "routes.json").write_text(json.dumps({"routes": plan}, indent=2), encoding="utf-8")


# ── literal solution: the request as written ─────────────────────────────────

LITERAL_SHIFT_END = 12 * 60   # literal_solution: no shift end in the agent's view, so the whole morning
LITERAL_LATE = 10.0           # literal_solution: deliver_by read as a firm target, a late minute costing ten
# literal_solution: the travel times an agent assumes when nobody tells it: the straight line between the
# coordinates (they are in km), a city van's 30 km/h and five minutes at each café.
LITERAL_TRAVEL = Travel(road=1.0, average=30.0, stop=5.0, per_tray=0.0)
# shortcuts: another guess, a planner's without being told (a detour factor, an urban average speed, a short stop).
# With the closed café known it scores up to 0.93 in six of the nine easy settings, where the closed café is often
# the only rule the literal solution breaks: the travel times are guessable (GT.md, part 5; known and open in
# validate.OPEN_AUDIT_FINDINGS).
PLANNER_GUESS = Travel(road=1.3, average=25.0, stop=5.0, per_tray=0.0)


def _literal_rules() -> Rules:
    return Rules(tier="easy", closed=None, capacity=CAPACITY, shift_end=LITERAL_SHIFT_END, late_weight=LITERAL_LATE,
                 rush=None, cold_chain=False, premium_first=False, travel=LITERAL_TRAVEL)


def literal_solution(world: World, out_dir: Path) -> None:
    """The request at face value, from the agent's view alone: every café on the list gets its trays ("all our
    cafés"), any van may serve any café (nothing says the partner range needs the refrigerated van), up to its racks'
    max_trays, leaving from 05:00 and driving as long as the morning needs, with deliver_by as the target (a late
    minute weighted as ten van minutes) and the drivers' time otherwise kept short. The data gives positions but no
    travel times, so the plan assumes what an agent assumes when nobody says: the straight line between the
    coordinates, 30 km/h and five minutes at each café. The reference planner under those readings: no closed café,
    no week's tray limit, no shift end, no habit, no rush and no workshop day. It delivers to the café that is closed
    this week, so it is invalid in every setting."""
    plan = _plan(world, _literal_rules())
    (out_dir / "routes.json").write_text(json.dumps({"routes": plan}, indent=2), encoding="utf-8")


# ── violating examples ───────────────────────────────────────────────────────

OVERFULL_BUDGET = 20000   # route evaluations per search for an over-full route


class NoExample(Exception):
    """No plan breaks this rule alone in this world (build_world draws again)."""


def _retimed(world: World, rules: Rules, route: dict, rule: str) -> dict | None:
    """`route` at its best departure among those where it breaks no rule but `rule` (None if there is none)."""
    best = None
    for depart in range(DAY_START, rules.shift_end, GRID):
        cand = {**route, "depart": _hhmm(depart)}
        v, obj, _ = simulate(world, [cand], rules)
        if {x[0] for x in v} <= {rule, "serve_each_once"} and (best is None or obj < best[0]):
            best = (obj, cand)
    return None if best is None else best[1]


def _tier_positions(world: World, rules: Rules, stops: list[str], cid: str) -> range:
    """Where café `cid` can join `stops` keeping the habit (premium cafés ahead of standard ones), when it applies."""
    if not rules.premium_first:
        return range(len(stops) + 1)
    tiers = [world.cafe(s).tier for s in stops]
    if world.cafe(cid).tier == "A":
        return range(0, (tiers.index("B") if "B" in tiers else len(tiers)) + 1)
    return range(max((k for k, t in enumerate(tiers) if t == "A"), default=-1) + 1, len(stops) + 1)


def _overfull_routes(world: World, rules: Rules, van: dict, base: list[str], budget: int = OVERFULL_BUDGET):
    """Supersets of route `base` for `van` that carry more than it holds but keep every other rule, depth first.

    Each step adds an open café at its cheapest position, trying first the café that adds the fewest route minutes
    per tray. Leaving as early as the van may is enough to test the shift: an earlier start never brings a van back
    later. Stops after `budget` route evaluations.
    """
    spent = 0
    cap = min(van["capacity"], rules.capacity)

    def minutes(stops: list[str]) -> float | None:
        nonlocal spent
        spent += 1
        route = {"van": van["id"], "depart": _hhmm(rules.earliest(van["id"])), "stops": stops}
        v, _, metrics = simulate(world, [route], rules)
        return None if {x[0] for x in v} - {"serve_each_once", "van_capacity"} else metrics["route_minutes"]

    def grow(stops: list[str], load: int, now: float):
        if load > cap:
            yield stops
            return
        nexts = []
        for c in world.open_cafes(rules):
            if c.id in stops:
                continue
            best = None
            for pos in _tier_positions(world, rules, stops, c.id):
                cand = stops[:pos] + [c.id] + stops[pos:]
                after = minutes(cand) if spent < budget else None
                if after is not None and (best is None or after < best[0]):
                    best = (after, cand)
            if best is not None:
                nexts.append(((best[0] - now) / c.trays, c.id, c.trays, best))
        for _, _, trays, (after, cand) in sorted(nexts):
            yield from grow(cand, load + trays, after)

    now = minutes(base) if base else 0.0
    if now is not None:
        yield from grow(list(base), sum(world.cafe(s).trays for s in base), now)


def _breaking_plans(world: World, rules: Rules) -> dict[str, list[dict]]:
    """One plan per rule in force that breaks exactly that rule: edits of the reference plan.

    Candidate edits are tried in turn, retiming the edited route where that helps, and the first one the scorer
    finds breaking that rule and nothing else is kept, so an edit cannot push a route past the shift end or over
    capacity by accident. Raises NoExample when no candidate breaks a rule alone.
    """
    ref = _plan(world, rules)
    vans = {vn["id"]: vn for vn in world.vans}
    rc = _Routes(world, rules)
    fridge = next(vid for vid, vn in vans.items() if vn["refrigerated"])
    fallback = [{**r, "stops": [s for s in r["stops"] if s != rules.closed]} for r in world.fallback[rules.tier]]

    def copy(plan: list[dict]) -> list[dict]:
        return json.loads(json.dumps(plan))

    def load(stops: list[str]) -> int:
        return sum(world.cafe(s).trays for s in stops)

    def replaced(plan: list[dict], i: int, route: dict | None) -> list[dict] | None:
        if route is None:
            return None
        out = copy(plan)
        out[i] = route
        return out

    def edits(plan: list[dict], i: int, stops: list[str], rule: str):
        """Route i with new stops: at its own departure, then at the best departure that keeps the other rules."""
        yield replaced(plan, i, {**plan[i], "stops": stops})
        yield replaced(plan, i, _retimed(world, rules, {**plan[i], "stops": stops}, rule))

    def insertions(plan: list[dict], cid: str, rule: str, van_ids):
        """Café cid added to a route of one of `van_ids` (least loaded first), or alone on an unused one."""
        for i in sorted(range(len(plan)), key=lambda i: load(plan[i]["stops"])):
            if plan[i]["van"] in van_ids:
                stops = plan[i]["stops"]
                for pos in reversed(_tier_positions(world, rules, stops, cid)):
                    yield from edits(plan, i, stops[:pos] + [cid] + stops[pos:], rule)
        used = {r["van"] for r in plan}
        for vid in van_ids:
            if vid not in used:
                route = _retimed(world, rules, {"van": vid, "stops": [cid]}, rule)
                if route is not None:
                    yield copy(plan) + [route]

    def first(rule: str, candidates) -> list[dict]:
        for plan in candidates:
            if plan is not None and {x[0] for x in simulate(world, plan, rules)[0]} == {rule}:
                return plan
        raise NoExample(f"no edit of the reference plan breaks only {rule}")

    def add_closed():
        # Also deliver to the closed café, on a route that has room and time for it; else the world's fallback,
        # which serves every café and keeps every other rule of any setting.
        yield from insertions(ref, rules.closed, "closed_cafe", list(vans))
        yield copy(world.fallback[rules.tier])

    def drop_one():
        # Leave one café out; dropping a stop never makes a route later or heavier.
        for i, r in enumerate(ref):
            for pos in reversed(range(len(r["stops"]))):
                yield from edits(ref, i, r["stops"][:pos] + r["stops"][pos + 1:], "serve_each_once")

    def partner_on_dry_van():
        # The refrigerated van's route driven by a dry van (swapping routes with it), else one partner moved over;
        # last the same swaps on the fallback routes.
        dry = [vid for vid in vans if not vans[vid]["refrigerated"]]
        for plan in (ref, fallback):
            for c in [i for i, r in enumerate(plan) if r["van"] == fridge]:
                for vid in dry:
                    swapped = copy(plan)
                    for r in swapped:
                        if r["van"] == vid:
                            r["van"] = fridge
                    swapped[c]["van"] = vid
                    yield swapped
                for sid in [s for s in plan[c]["stops"] if world.cafe(s).partner]:
                    rest = copy(plan)
                    rest[c]["stops"].remove(sid)
                    yield from insertions(rest, sid, "cold_chain", dry)

    def overload():
        # One van carries more than it holds. First a route of the plan grows with cafés from the other routes,
        # which only get shorter (heaviest route first); else a van's route is rebuilt from its partner cafés alone
        # when the cold chain applies (no dry van may take them), from nothing otherwise (unused vans first), and
        # the cafés it displaces move to the other vans by cheapest feasible insertion.
        stops_of = {vid: next((r["stops"] for r in ref if r["van"] == vid), []) for vid in vans}
        starts = ([(vid, stops_of[vid]) for vid in sorted(vans, key=lambda v: -load(stops_of[v]))]
                  + [(vid, [s for s in stops_of[vid] if world.cafe(s).partner and rules.cold_chain])
                     for vid in sorted(vans, key=lambda v: len(stops_of[v]))])
        for vid, base in starts:
            for stops in _overfull_routes(world, rules, vans[vid], base):
                full = _retimed(world, rules, {"van": vid, "stops": stops}, "van_capacity")
                others = {v: [s for s in stops_of[v] if s not in stops] for v in vans if v != vid}
                if full and _insert_all(rc, [world.cafe(s) for s in stops_of[vid] if s not in stops], others):
                    yield rc.plan(others) + [full]

    def premium_after_standard():
        # A premium café behind a standard one: swap a pair on a route, else move a premium café behind a
        # standard one on its own route or on another.
        for i, r in enumerate(ref):
            for a in range(len(r["stops"])):
                for b in range(a + 1, len(r["stops"])):
                    if world.cafe(r["stops"][a]).tier == "A" and world.cafe(r["stops"][b]).tier == "B":
                        trial = r["stops"][:]
                        trial[a], trial[b] = trial[b], trial[a]
                        yield from edits(ref, i, trial, "premium_first")
        for j, src in enumerate(ref):
            for sid in [s for s in src["stops"] if world.cafe(s).tier == "A"]:
                rest = copy(ref)
                rest[j]["stops"].remove(sid)
                for i, r in enumerate(rest):
                    if rules.cold_chain and world.cafe(sid).partner and not vans[r["van"]]["refrigerated"]:
                        continue
                    tiers = [world.cafe(s).tier for s in r["stops"]]
                    if "B" not in tiers:
                        continue
                    for pos in range(tiers.index("B") + 1, len(r["stops"]) + 1):
                        yield from edits(rest, i, r["stops"][:pos] + [sid] + r["stops"][pos:], "premium_first")

    def outside_shift():
        # Leave before 05:00 (an earlier start never makes a route later), else leave so late it returns after the
        # shift end.
        for i, r in enumerate(ref):
            yield replaced(ref, i, {**r, "depart": "04:30"})
        for i, r in enumerate(ref):
            for depart in range(rules.shift_end, DAY_START, -GRID):
                yield replaced(ref, i, {**r, "depart": _hhmm(depart)})

    def out_of_workshop_early():
        # The held-back van leaves at 05:00: its own route if it has one, else a dry van's route handed to it.
        held = [vid for vid, _ in rules.ready]
        for i, r in enumerate(ref):
            if r["van"] in held:
                yield replaced(ref, i, {**r, "depart": _hhmm(DAY_START)})
        for vid in held:
            for i, r in enumerate(ref):
                if r["van"] not in held and not vans[r["van"]]["refrigerated"]:
                    plan = copy(ref)
                    for other in plan:
                        if other["van"] == vid:
                            other["van"] = r["van"]
                    plan[i] = {**r, "van": vid, "depart": _hhmm(DAY_START)}
                    yield plan

    makers = {"closed_cafe": add_closed, "serve_each_once": drop_one, "van_capacity": overload,
              "shift_window": outside_shift}
    if rules.cold_chain:
        makers["cold_chain"] = partner_on_dry_van
    if rules.premium_first:
        makers["premium_first"] = premium_after_standard
    if rules.ready:
        makers["van_ready"] = out_of_workshop_early
    return {rule: first(rule, make()) for rule, make in makers.items()}


def violating_examples(world: World, setting: Setting) -> dict:
    """One deliverable per rule in force that breaks exactly that rule (for the validator)."""
    def write(routes: list[dict]):
        return lambda out: (out / "routes.json").write_text(json.dumps({"routes": routes}), encoding="utf-8")

    return {rule: write(plan) for rule, plan in _breaking_plans(world, rules_of(setting)).items()}


# ── ground truth audit hooks (fdebench2.audit, GT.md) ────────────────────────

_EN_TARGETS = yaml.safe_load((Path(__file__).parent / "locales" / "en" / "targets.yaml").read_text(encoding="utf-8"))
TARGET_TIERS = {t["id"]: tuple(t.get("tiers", TIERS)) for t in _EN_TARGETS}
TARGET_PARAM = {t["id"]: t["param"] for t in _EN_TARGETS if t.get("param")}
TARGET_WHEN = {t["id"]: t.get("when") or {} for t in _EN_TARGETS}
FORCE_LATE = 10.0             # the lateness cost misread: deliver_by as a firm target, as the literal reads it


def _in_force(setting: Setting) -> list[str]:
    return [t for t, tiers in TARGET_TIERS.items() if setting.tier in tiers
            and all(str(setting.params.get(k)).lower() in [str(v).lower() for v in vs]
                    for k, vs in TARGET_WHEN[t].items())]


def _misread(rules: Rules, target: str) -> Rules | None:
    """The rules a plan is made with when one fixed fact is read the most natural wrong way (None: no such
    misreading here). Travel facts change only the planning model: the plan is still scored with the client's."""
    tr = rules.travel
    if target == "road_distance":
        return replace(rules, travel=replace(tr, road=1.0))                 # the straight line between the points
    if target == "speed":
        return replace(rules, travel=replace(tr, average=FAST))             # a city van's 30 km/h
    if target == "rush_hour":
        return replace(rules, rush=None, travel=replace(tr, average=FAST))  # 30 km/h all morning, no rush
    if target == "service_time":
        return replace(rules, travel=replace(tr, stop=5.0, per_tray=0.0))   # five minutes a stop (the literal's guess)
    if target == "tray_limit":
        return replace(rules, capacity=CAPACITY)                            # the racks' max_trays
    if target == "cold_chain":
        return replace(rules, cold_chain=False)                             # any van for the partner cafés
    if target == "partner_this_week":
        return replace(rules, cold_chain=True)                              # the refrigerated van only
    if target == "lateness":
        return replace(rules, late_weight=FORCE_LATE)                       # deliver_by as a firm target
    if target == "workshop":
        return replace(rules, ready=())                                     # V2 out from 05:00
    if target == "manager_pressure":
        return replace(rules, first=(PRESSURE_CAFE, PRESSURE_BY))           # her demand followed
    if target == "premium_first":
        return replace(rules, premium_first=True)                           # the habit kept although suspended
    return None


def _write(out_dir: Path, plan: list[dict]) -> None:
    (out_dir / "routes.json").write_text(json.dumps({"routes": plan}, indent=2), encoding="utf-8")


def ablations(world: World, setting: Setting) -> dict:
    """{target: write the plan that misreads only that fact}: the reference planner under the setting's rules with
    one fact read the most natural wrong way the agent's view allows (_misread), for every target in force that is
    not a drawn parameter with another candidate here (those the audit ablates itself, with the reference of each
    other candidate). The tray limit is ablated here in hard, where its parameter has one candidate: the racks'
    120 trays from the data."""
    rules = rules_of(setting)
    out = {}
    for t in _in_force(setting):
        param = TARGET_PARAM.get(t)
        if param and len(set(map(str, POOLS[param][setting.tier]))) > 1:
            continue
        wrong = _misread(rules, t)
        if wrong is not None:
            out[t] = (lambda w: lambda d: _write(d, _misread_plan(world, rules, w)))(wrong)
    return out


def _misread_plan(world: World, rules: Rules, wrong: Rules) -> list[dict]:
    """The reference planner's plan under the misread rules. Where the C07 manager's demand cannot be met within
    the other rules, the plan meets it anyway, as an agent that follows her would: the reference with her café moved
    to the front of the round where that costs least, the van leaving to reach it by 06:30."""
    try:
        return _plan(world, wrong)
    except ValueError:
        if not wrong.first:
            raise
    cid, by = wrong.first
    ref = _plan(world, rules)
    best = None
    for i in range(len(ref)):
        plan = json.loads(json.dumps(ref))
        for r in plan:
            r["stops"] = [s for s in r["stops"] if s != cid]
        plan[i]["stops"].insert(0, cid)
        c = world.cafe(cid)
        km = _km((0.0, 0.0), (c.x, c.y))
        depart = int(math.floor(by - _drive(km, by, rules.rush) + 1e-9))
        plan[i]["depart"] = _hhmm(max(rules.earliest(plan[i]["van"]), depart))
        violations, obj, _ = simulate(world, plan, rules)
        key = (len(violations), obj)
        if best is None or key < best[0]:
            best = (key, plan)
    return best[1]


# ── shortcuts: lazy plans that must not score ────────────────────────────────

def _rounds_plan(world: World, rules: Rules, rounds: dict[str, list[str]]) -> list[dict]:
    """Rounds as a plan, each van leaving at the best minute for its round (the reference's own timing)."""
    rc = _Routes(world, rules)
    plan = []
    for vid, stops in rounds.items():
        if stops:
            best = rc.best(vid, stops)
            plan.append({"van": vid, "depart": _hhmm(best[1] if best else rules.earliest(vid)), "stops": stops})
    return plan


def _cut(world: World, rules: Rules, order: list[Cafe]) -> dict[str, list[str]]:
    """Cafés of `order` loaded onto V1, V2, V3 and V4 in turn, the next van once the tray limit is reached (partner
    cafés on V4 when the cold chain applies; premium cafés first on each van while the habit holds)."""
    vans = [vn["id"] for vn in world.vans]
    fridge = next(vn["id"] for vn in world.vans if vn["refrigerated"])
    rounds = {vid: [] for vid in vans}
    if rules.cold_chain:
        rounds[fridge] = [c.id for c in order if c.partner]
        order = [c for c in order if not c.partner]
    i = 0
    for c in order:
        while i < len(vans) - 1 and sum(world.cafe(s).trays for s in rounds[vans[i]]) + c.trays > rules.capacity:
            i += 1
        rounds[vans[i]].append(c.id)
    if rules.premium_first:
        rounds = {vid: sorted(stops, key=lambda s: world.cafe(s).tier) for vid, stops in rounds.items()}
    return rounds


def shortcuts(world: World, setting: Setting) -> dict:
    """Lazy plans a gaming agent might hand in, given every rule of the setting where the plan can keep it; each
    must be invalid or score at most 0.5. Every departure is the best minute for its round."""
    rules = rules_of(setting)
    open_cafes = world.open_cafes(rules)

    def id_order(out: Path) -> None:
        """One route per van in café-id order: C01, C02, ... loaded onto V1 until the tray limit, then V2, V3, V4."""
        _write(out, _rounds_plan(world, rules, _cut(world, rules, sorted(open_cafes, key=lambda c: c.id))))

    def opening_order(out: Path) -> None:
        """Cafés in the order they open, loaded onto V1 until the tray limit, then V2, V3, V4 (time, not place)."""
        _write(out, _rounds_plan(world, rules, _cut(world, rules, sorted(open_cafes, key=lambda c: (c.open_min,
                                                                                                    c.id)))))

    def nearest_neighbour(out: Path) -> None:
        """Nearest neighbour without the delivery windows: each van drives to the nearest café not yet served until
        the tray limit, then the next van starts from the kitchen."""
        left = list(open_cafes)
        order, pos = [], (0.0, 0.0)
        while left:
            c = min(left, key=lambda c: (math.hypot(c.x - pos[0], c.y - pos[1]), c.id))
            order.append(c)
            left.remove(c)
            pos = (c.x, c.y)
        _write(out, _rounds_plan(world, rules, _cut(world, rules, order)))

    def map_slices(out: Path) -> None:
        """Four slices of the map round the kitchen, one per van, each in the order its cafés open."""
        start = math.pi
        rounds = None
        for s in [start] + [math.atan2(c.y, c.x) for c in open_cafes]:
            rounds = _sweep(world, rules, s)
            if rounds is not None:
                break
        _write(out, _rounds_plan(world, rules, rounds) if rounds else [])

    def habit_best_departures(out: Path) -> None:
        """Copy the client's way and change one thing, the timing: the dispatcher's rounds, each van at its best
        departure (and each round in its best order for that departure)."""
        rc = _Routes(world, rules)
        rounds = {vn["id"]: [] for vn in world.vans}
        for r in _client_way(world, rules):
            rounds[r["van"]] = r["stops"]
        for vid, stops in rounds.items():
            if 1 < len(stops) <= HABIT_ORDER_MAX:
                orders = [list(p) for p in itertools.permutations(stops) if rc.cost(vid, list(p)) is not None]
                rounds[vid] = min(orders, key=lambda p: rc.cost(vid, p), default=stops)
        _write(out, _rounds_plan(world, rules, rounds))

    def habit_one_move(out: Path) -> None:
        """Copy the client's way and change one thing: the one café whose move to another place saves the most."""
        plan = _client_way(world, rules)
        rounds = {vn["id"]: [] for vn in world.vans}
        for r in plan:
            rounds[r["van"]] = r["stops"]
        cost = {vid: _round_cost(world, rules, vid, stops) if stops else 0.0 for vid, stops in rounds.items()}
        best = None
        for src, stops in rounds.items():
            for cid in stops:
                rest = [x for x in stops if x != cid]
                left = _round_cost(world, rules, src, rest) if rest else 0.0
                if left is None:
                    continue
                for dst, other in rounds.items():
                    base = rest if dst == src else other
                    for pos in range(len(base) + 1):
                        cand = base[:pos] + [cid] + base[pos:]
                        new = _round_cost(world, rules, dst, cand)
                        if new is None:
                            continue
                        saving = cost[src] + (cost[dst] if dst != src else 0.0) - (new + (left if dst != src else 0.0))
                        if best is None or saving > best[0] + 1e-9:
                            best = (saving, src, rest, dst, cand)
        if best is not None and best[0] > 1e-9:
            rounds[best[1]] = best[2]
            rounds[best[3]] = best[4]
        _write(out, _timed(world, rules, rounds))

    def insertion_without_departures(out: Path) -> None:
        """Cheapest insertion with every rule and the client's travel times, the departures left out of the file
        (every van at the default 05:00)."""
        _write(out, [{"van": r["van"], "stops": r["stops"]} for r in insertion_plan(world, rules)])

    def deadline_balanced(out: Path) -> None:
        """Cafés by deliver_by, each to the van with the fewest trays so far (partner cafés on V4 when the cold chain
        applies, premium cafés first while the habit holds), each van at its best departure."""
        vans = [vn["id"] for vn in world.vans]
        fridge = next(vn["id"] for vn in world.vans if vn["refrigerated"])
        rounds, load = {vid: [] for vid in vans}, {vid: 0 for vid in vans}
        for c in sorted(open_cafes, key=lambda c: (c.tier if rules.premium_first else "", c.latest_min, c.id)):
            vid = fridge if rules.cold_chain and c.partner else min(vans, key=lambda v: (load[v], v))
            rounds[vid].append(c.id)
            load[vid] += c.trays
        _write(out, _rounds_plan(world, rules, rounds))

    def literal_plus_closed_cafe_planner_guess(out: Path) -> None:
        """The literal solution with the closed café known and the travel times guessed as a planner would without
        being told: 1.3 times the straight line, 25 km/h and five minutes a stop."""
        guess = replace(literal, tier=rules.tier, closed=rules.closed, travel=PLANNER_GUESS)
        _write(out, _plan(world, guess))

    made = [id_order, opening_order, nearest_neighbour, map_slices, habit_best_departures, habit_one_move,
            insertion_without_departures, deadline_balanced, literal_plus_closed_cafe_planner_guess]
    literal = _literal_rules()
    near = {"closed_cafe": dict(closed=rules.closed), "van_capacity": dict(capacity=rules.capacity),
            "shift_window": dict(shift_end=rules.shift_end), "cold_chain": dict(cold_chain=rules.cold_chain),
            "premium_first": dict(premium_first=rules.premium_first), "van_ready": dict(ready=rules.ready)}
    out = {f.__name__: f for f in made}
    for rule, change in near.items():
        def literal_plus(d: Path, change=change) -> None:
            _write(d, _plan(world, replace(literal, tier=rules.tier, **change)))
        literal_plus.__doc__ = (f"The literal solution with the one client fact behind rule {rule} known (planned "
                                f"anew with it, every other reading literal).")
        out[f"literal_plus_{rule}"] = literal_plus
    return out


def insertion_plan(world: World, rules: Rules) -> list[dict]:
    """Not a shortcut, a part of the work (GT.md): the cafés given out in the dispatcher's order, each put where it
    adds the least on any round (cheapest insertion) with the client's rules and travel times, each van at its best
    departure. It needs every fact the client knows."""
    rc = _Routes(world, rules)
    order = sorted(world.open_cafes(rules), key=lambda c: (c.tier if rules.premium_first else "", c.open_min,
                                                           c.latest_min, c.id))
    rounds = {vn["id"]: [] for vn in world.vans}
    if not _insert_all(rc, order, rounds):
        return _client_way(world, rules)
    return _rounds_plan(world, rules, rounds)


# ── the solver that never asks ───────────────────────────────────────────────

ROBUST_LATE = 5.0             # robust_solution: deliver_by read as a target the café expects, not a wall: a late
                              # minute weighs five van minutes (between the literal's firm ten and a soft one)


def robust_solution(world: World, out_dir: Path, tier: str, candidates: dict) -> None:
    """The one plan for every setting of the tier, from the agent's view and the tier's pools.

    Read from the data: the cafés, their trays, windows and tiers, the vans and that only V4 is refrigerated. The
    partner cafés go on V4 (the data pairs partner_brand with the refrigerated van and nothing settles that a dry
    van may take them; it is also valid in every tier). deliver_by is read as a target the café expects but not a
    wall, a late minute weighted as five van minutes: a solver that cannot ask hedges between the firm deadline the
    literal reads (ten) and a soft target (on the public world this scores 0.12 better in easy than the firm
    reading, 0.02 worse in medium and the same in hard). Granted, although nothing on hand settles it, so that the
    gap left does not rest on a guess: the client's travel times (1.3 times the straight line, 25 km/h, and in hard 30 km/h before the rush and 20 km/h
    from it; four minutes plus 0.2 a tray at each café). Planned across the pools: the smallest tray limit and the
    earliest shift end (valid whatever the client's value); the premium-first habit kept or not, the rush planned
    at each candidate start, and one candidate café left out as the closed one (any other choice serves the closed
    café in every setting). Among those plans it hands in the one with the best mean, over every combination of the
    pools read as above, of (valid there) x (the reference planner's objective there) / (its objective there): it
    never sees the client's own way, so it cannot weigh by the quality scale. Not granted, and not guessed: V2's
    workshop morning and the C07 manager's demand, which nothing on hand mentions (her demand is not followed)."""
    _write(out_dir, _robust_plan(world, tier, candidates))


def _robust_plan(world: World, tier: str, candidates: dict, cold_chain: bool = True) -> list[dict]:
    """robust_solution's plan; cold_chain=False reads the partner cafés as free for any van instead (GT.md reports
    that guess beside it)."""
    pools = {name: list(dict.fromkeys(values)) for name, values in candidates.items()}
    combos = [dict(zip(pools, values)) for values in itertools.product(*pools.values())]
    # each combination as the solver reads it: the tier's fixed facts at its own reading, not the client's
    true_rules = [replace(_rules(tier, c), cold_chain=cold_chain, ready=(), late_weight=ROBUST_LATE) for c in combos]
    refs = [simulate(world, _plan(world, r), r)[1] for r in true_rules]
    base = {"van_capacity": min(int(v) for v in pools["van_capacity"]),
            "shift_end": _hhmm(min(_minutes(v) for v in pools["shift_end"]))}
    best = None
    for closed, habit, rush in itertools.product(pools["closed_cafe"], pools["premium_first"], pools["rush_start"]):
        p = {**combos[0], **base, "closed_cafe": closed, "premium_first": habit, "rush_start": rush}
        rules = replace(_rules(tier, p), cold_chain=cold_chain, late_weight=ROBUST_LATE, ready=())
        plan = _plan(world, rules)
        score = 0.0
        for r, ref in zip(true_rules, refs):
            violations, obj, _ = simulate(world, plan, r)
            score += 0.0 if violations else ref / obj
        key = (-score / len(combos), str(closed), str(habit), str(rush))
        if best is None or key < best[0]:
            best = (key, plan)
    return best[1]


# ── best known solution and a proven bound ───────────────────────────────────

def best_known_solution(world: World, out_dir: Path, setting: Setting) -> None:
    """The best plan known: the stored result of the long search (reference/best_known.json, see make_bounds.py)
    for this world and setting when it is valid and no worse than the reference, else the reference."""
    rules = rules_of(setting)
    ref = _plan(world, rules)
    found = _stored(world, setting).get("plan")
    if found is not None:
        violations, obj, _ = simulate(world, found, rules)
        if not violations and obj <= simulate(world, ref, rules)[1] + 1e-9:
            ref = found
    _write(out_dir, ref)


def objective_bound(world: World, setting: Setting) -> float:
    """A proven lower bound on the objective (make_bounds.py: the dual bound of a mixed-integer relaxation of the
    setting with the client's travel times, the morning rush priced exactly, free departures and V2's workshop
    morning relaxed), stored for this world and setting; without one, the plain bound of service time alone."""
    bound = _stored(world, setting).get("bound")
    if bound is not None:
        return float(bound)
    rules = rules_of(setting)
    return sum(_service(c.trays) for c in world.open_cafes(rules))


BOUNDS_FILE = Path(__file__).with_name("reference") / "best_known.json"


def world_key(world: World) -> str:
    """A fingerprint of the world's data (a stored result belongs to the world it was computed on)."""
    rows = [[c.id, c.x, c.y, c.trays, c.tier, c.open_min, c.latest_min, c.partner] for c in world.cafes]
    return hashlib.sha256(json.dumps(rows).encode()).hexdigest()[:16]


def setting_key(setting: Setting) -> str:
    return setting.tier + "|" + ",".join(f"{k}={setting.params[k]}" for k in sorted(POOLS))


def _stored(world: World, setting: Setting) -> dict:
    if "stored" not in world.cache:
        data = json.loads(BOUNDS_FILE.read_text(encoding="utf-8")) if BOUNDS_FILE.is_file() else {}
        world.cache["stored"] = data.get(world_key(world), {})
    return world.cache["stored"].get(setting_key(setting), {})


# ── diagnostics: does a plan implement each client fact? ────────────────────
# A rule that only one fact states is checked on the plan itself: a plan that breaks it is not enforced on that
# fact (the closed café, the tray limit, the shift end, the cold chain, the habit where it holds, V2's workshop
# morning; the C07 demand: her café first on its round and reached by 06:30). Every other fact, and a plan that
# keeps such a rule, is told by its misreadings (another candidate of the fact's parameter, else _misread; then a
# small grid round the client's value, _other_way): a plan that breaks a rule of the client's that the misreading
# would allow follows it; so does one that loses at least DIAG_TOL of the quality scale against the reference under
# the client's reading when the misreading explains the loss (under the misread rules the plan is that much closer
# to the reference planner's own plan for them, and that covers DIAG_SHARE of its loss, DIAG_SHARE_OTHER for the
# grid). A plan that breaks a rule of the misreading that the client's rules allow does not follow it. The travel
# facts all change how long the vans take, so a plan made with one of them misread is often explained by another
# too (reported as cross flags).

DIAG_TOL = 0.05
DIAG_SHARE = 0.5
DIAG_SHARE_OTHER = 0.6      # the share a reading of _other_way must explain: a weak plan that knows the fact (cheapest
                            # insertion, late at many cafés) is otherwise half explained by deliver_by ignored
TARGET_RULE = {"closed_cafe": "closed_cafe", "tray_limit": "van_capacity", "shift_end": "shift_window",
               "cold_chain": "cold_chain", "premium_first": "premium_first", "workshop": "van_ready"}
RULE_ONLY = ("closed_cafe", "cold_chain", "workshop")    # a plan that keeps these rules implements the fact


def _span(world: World, rules: Rules) -> float:
    return abs(simulate(world, _client_way(world, rules), rules)[1]
               - simulate(world, _plan(world, rules), rules)[1]) or 1.0


def _other_way(rules: Rules, target: str) -> list[tuple[str, Rules]]:
    """Further misreadings of a fact (diagnostics only: the ablation is _misread's alone): the other direction and
    milder values, a small grid round the client's value. With _misread's alone, a plan made with the vans a little
    too slow, the roads too long, heavier unloading or deliver_by ignored was called enforced on that fact, since no
    listed misreading explained its loss."""
    tr = rules.travel
    if target == "road_distance":
        return [(f"road distance taken as {f} times the straight line", replace(rules, travel=replace(tr, road=f)))
                for f in (1.15, 1.45, 1.6)]
    if target == "speed":
        return [(f"speed taken as {v:g} km/h", replace(rules, travel=replace(tr, average=v)))
                for v in (20.0, 22.0, 28.0)]
    if target == "rush_hour":
        return [(f"{v:g} km/h all morning", replace(rules, rush=None, travel=replace(tr, average=v)))
                for v in (SLOW, AVERAGE)]
    if target == "service_time":
        return [("no time at the café", replace(rules, travel=replace(tr, stop=0.0, per_tray=0.0))),
                ("ten minutes at every café", replace(rules, travel=replace(tr, stop=10.0, per_tray=0.0))),
                ("two minutes plus 0.4 a tray", replace(rules, travel=replace(tr, stop=2.0, per_tray=0.4)))]
    if target == "lateness":
        return [("deliver_by ignored", replace(rules, late_weight=0.0)),
                ("a late minute worth one van minute", replace(rules, late_weight=1.0))]
    if target == "rush_start" and rules.rush is not None:
        return [(f"the rush taken to start at {_hhmm(t)}", replace(rules, rush=t)) for t in (6 * 60, 8 * 60)]
    return []


def _readings(rules: Rules, setting: Setting, t: str) -> list[tuple[str, Rules, float]]:
    """[(what, rules, share)]: the misreadings of target t (another candidate of its parameter, else _misread; then
    the further ones of _other_way) and the share of a plan's loss each must explain."""
    param = TARGET_PARAM.get(t)
    pool = list(dict.fromkeys(map(str, POOLS[param][setting.tier]))) if param else []
    other = [(what, wrong, DIAG_SHARE_OTHER) for what, wrong in _other_way(rules, t)]
    if param and len(pool) > 1:
        return [(f"{param} were {v}", _rules(setting.tier, {**setting.params, param: v}), DIAG_SHARE)
                for v in dict.fromkeys(POOLS[param][setting.tier]) if str(v) != str(setting.params[param])] + other
    wrong = _misread(rules, t)
    return ([(t.replace("_", " ") + " misread", wrong, DIAG_SHARE)] if wrong is not None else []) + other


def _regret_check(world: World, rules: Rules, plan: list[dict], readings) -> tuple[bool, str]:
    span = _span(world, rules)
    broken_s, g_s, _ = simulate(world, plan, rules)
    broken_s = {r for r, _ in broken_s}
    r_s = (g_s - simulate(world, _plan(world, rules), rules)[1]) / span
    seen = f"regret {r_s:+.1%} of the scale"
    for what, wrong, share in readings:
        broken_m, g_m, _ = simulate(world, plan, wrong)
        broken_m = {r for r, _ in broken_m}
        if broken_m - broken_s:
            continue                       # it breaks a rule only the misreading has: it does not follow it
        if broken_s - broken_m:
            return False, f"breaks {', '.join(sorted(broken_s - broken_m))}, which it would keep if {what}"
        try:
            misread_plan = _plan(world, wrong)
        except ValueError:
            continue                       # no plan keeps the misread rules: the reading explains nothing
        r_m = (g_m - simulate(world, misread_plan, wrong)[1]) / span
        if r_s > DIAG_TOL and r_s - r_m > max(DIAG_TOL, share * r_s):
            return False, f"regret {r_s:+.1%} of the scale under the client's reading, {r_m:+.1%} if {what}"
        seen = f"regret {r_s:+.1%} of the scale, {r_m:+.1%} if {what}"
    return True, seen


def _diagnostics(world: World, setting: Setting, plan: list[dict]) -> tuple[dict, dict]:
    rules = rules_of(setting)
    broken = {r for r, _ in simulate(world, plan, rules)[0]}
    enforced, evidence = {}, {}
    for t in _in_force(setting):
        rule = TARGET_RULE.get(t)
        if t == "premium_first" and not rules.premium_first:
            rule = None
        if t == "manager_pressure":
            first = [r for r in plan if r.get("stops") and str(r["stops"][0]) == PRESSURE_CAFE]
            reached = None
            if first:
                c = world.cafe(PRESSURE_CAFE)
                d = _parse_time(first[0].get("depart"), "depart")
                reached = d + _drive(_km((0.0, 0.0), (c.x, c.y)), d, rules.rush)
            ok = reached is None or reached > PRESSURE_BY + 1e-9
            why = (f"{PRESSURE_CAFE} first on its round, reached at {_hhmm(int(reached))}" if reached is not None
                   else f"{PRESSURE_CAFE} not first on its round")
        elif rule and rule in broken:
            ok, why = False, f"breaks {rule}"
        elif t in RULE_ONLY:
            ok, why = True, f"keeps {rule}"
        else:
            ok, why = _regret_check(world, rules, plan, _readings(rules, setting, t))
        enforced[t], evidence[t] = ok, why
    return enforced, evidence


def diagnose(world: World, submission_dir: Path, setting: Setting, scored: dict) -> dict:
    """{enforced, evidence} per target in force (see the section comment), for any plan that can be read."""
    if "fatal" in scored:
        return {}
    plan = read_json(submission_dir, "routes.json")["routes"]
    enforced, evidence = _diagnostics(world, setting, plan)
    return {"enforced": enforced, "evidence": evidence}
