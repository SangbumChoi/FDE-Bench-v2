"""Bakery morning delivery routing (original FDE-Bench v2 case).

A central kitchen delivers bread trays to cafés with a small van fleet on a Monday morning. The request only says
"plan the routes"; the rules that decide validity and quality are in the requirements and must be asked for.

Settings (case.yaml): three tiers, and a rule seed that draws the client's parameters. Easy is the routing core:
this week's tray limit per van, the shift end, one visit per café, the café closed this week, a constant 25 km/h
and the lateness cost. Medium adds the partner cold chain and, when the rule seed draws it, the premium-first habit.
Hard adds the morning rush (30 km/h before a drawn time, 20 km/h from it, also on a leg already under way), a dated
event (V2 is in the workshop until 06:40 on Monday) and a premium café manager's pressure to be served first. The
data is the same in every setting.
"""

from __future__ import annotations

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

    def earliest(self, van_id: str) -> int:
        return dict(self.ready).get(van_id, DAY_START)


def _rules(tier: str, p: dict) -> Rules:
    def at_least(t: str) -> bool:
        return TIERS.index(tier) >= TIERS.index(t)

    return Rules(tier=tier, closed=None if p["closed_cafe"] is None else str(p["closed_cafe"]),
                 capacity=int(p["van_capacity"]), shift_end=_minutes(p["shift_end"]), late_weight=float(p["late_cost"]),
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
                         "late_cost": pool["late_cost"][0], "rush_start": _hhmm(min(rushes)) if rushes else "none",
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


def _matters(tier: str, name: str) -> bool:
    """Whether the parameter has two or more candidates in the tier and none in a higher tier: the validator checks
    that it changes the answer in this tier."""
    return (len(set(map(str, POOLS[name][tier]))) >= 2
            and all(len(set(map(str, POOLS[name][t]))) < 2 for t in TIERS[TIERS.index(tier) + 1:]))


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


@dataclass
class World:
    cafes: list[Cafe]
    vans: list[dict] = field(default_factory=list)
    fallback: dict[str, list[dict]] = field(default_factory=dict, repr=False)  # per tier: every café served
    cache: dict = field(default_factory=dict, repr=False, compare=False)  # reference plans per Rules

    def __post_init__(self):
        self.by_id = {c.id: c for c in self.cafes}

    def cafe(self, cid: str) -> Cafe | None:
        return self.by_id.get(cid)

    def open_cafes(self, rules: Rules) -> list[Cafe]:
        return [c for c in self.cafes if c.id != rules.closed]


def _draw_world(rng: random.Random) -> World:
    cafes = []
    for i in range(18):
        ang, r = rng.uniform(0, 2 * math.pi), rng.uniform(2.0, 11.0)
        open_min = rng.choice([6 * 60, 6 * 60 + 30, 7 * 60, 7 * 60 + 30])
        cafes.append(Cafe(id=f"C{i + 1:02d}", district=i, x=round(r * math.cos(ang), 2), y=round(r * math.sin(ang), 2),
                          trays=rng.randint(8, 30), tier="A" if i % 3 == 0 else "B", open_min=open_min,
                          latest_min=open_min + rng.choice([30, 45, 60]), partner=i in (4, 9, 15)))
    vans = [{"id": f"V{i}", "capacity": CAPACITY, "refrigerated": i == 4} for i in range(1, 5)]
    return World(cafes, vans)


def _usable(world: World) -> bool:
    """Whether every setting has a valid plan and every parameter can change the answer.

    For each tier, the reference solver must serve every café under the tier's strictest rules (the plan is kept
    as the tier's fallback). And in the tier where a parameter's candidates differ most (the highest tier in which
    it has two or more), the reference under _headline must bring a van back after the tier's earliest shift end,
    load one above its smallest tray limit, reach cafés late for at least MATTERS of its objective, and cost at
    least MATTERS more than the reference without the premium-first habit: otherwise the shift end, the tray
    limit, the lateness cost or the habit could not change the plan. (Which café is closed and when the rush
    starts change it in any world.)"""
    for tier in TIERS:
        plan = _solve(world, _strictest(tier))
        if plan is None or simulate(world, plan, _strictest(tier))[0]:
            return False
        world.fallback[tier] = plan
    for tier in TIERS:
        shift, cap, late, habit = (_matters(tier, name) for name in ("shift_end", "van_capacity", "late_cost",
                                                                      "premium_first"))
        if not (shift or cap or late or habit):
            continue
        rules = _headline(tier)
        plan = _plan(world, rules)
        routes = [[world.cafe(s) for s in r["stops"]] for r in plan]
        backs = [_run(rules, cafes, _minutes(r["depart"]))[0] for r, cafes in zip(plan, routes)]
        if shift and max(backs) <= _strictest(tier).shift_end:
            return False
        if cap and max(sum(c.trays for c in cafes) for cafes in routes) <= _strictest(tier).capacity:
            return False
        _, objective, metrics = simulate(world, plan, rules)
        if late and metrics["late_minutes"] < MATTERS * objective:
            return False
        if habit and rules.premium_first:
            free = replace(rules, premium_first=False)
            if simulate(world, _plan(world, free), free)[1] > (1 - MATTERS) * objective:
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

def _km(a: tuple[float, float], b: tuple[float, float]) -> float:
    return ROAD_FACTOR * math.hypot(a[0] - b[0], a[1] - b[1])


def _drive(km: float, t: float, rush: int | None) -> float:
    """Minutes to drive `km` leaving at minute t: AVERAGE without a rush; else FAST before the rush and SLOW from
    it, also on a leg under way."""
    if rush is None:
        return km / AVERAGE * 60.0
    fast = km / FAST * 60.0
    if t + fast <= rush:
        return fast
    if t >= rush:
        return km / SLOW * 60.0
    return (rush - t) + (km - (rush - t) / 60.0 * FAST) / SLOW * 60.0


def _service(trays: int) -> float:
    return 4.0 + 0.2 * trays


def _run(rules: Rules, cafes: list[Cafe], depart: float, waits: bool = False) -> tuple:
    """(return time, late minutes) of a route through `cafes` leaving at `depart`; a van waits for opening.
    With waits=True also whether it waits anywhere."""
    pos, t, late, waited = (0.0, 0.0), float(depart), 0.0, False
    for cafe in cafes:
        t += _drive(_km(pos, (cafe.x, cafe.y)), t, rules.rush)
        if t < cafe.open_min:
            t, waited = cafe.open_min, True
        late += max(0.0, t - cafe.latest_min)
        t += _service(cafe.trays)
        pos = (cafe.x, cafe.y)
    back = t + _drive(_km(pos, (0.0, 0.0)), t, rules.rush)
    return (back, late, waited) if waits else (back, late)


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


class _Routes:
    """Route costs for one world and one set of rules, each route evaluated once (with its best departure)."""

    def __init__(self, world: World, rules: Rules):
        self.world, self.rules = world, rules
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
        tiers = [c.tier for c in cafes]
        return not (rules.premium_first and "B" in tiers and "A" in tiers[tiers.index("B"):])

    def best(self, van_id: str, stops: list[str]) -> tuple[float, int] | None:
        """(objective contribution, departure) of the route at its best departure on the GRID, or None if no
        departure keeps every rule."""
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
        first, km = cafes[0], _km((0.0, 0.0), (cafes[0].x, cafes[0].y))
        lo = rules.earliest(van_id)
        start = lo + max(0, int((first.open_min - _drive(km, 0.0, None if rules.rush is None else 10 ** 6) - lo)
                                    // GRID)) * GRID
        while start > lo and start + _drive(km, start, rules.rush) > first.open_min:
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


def _ruin_recreate(rc: _Routes, routes: dict[str, list[str]], rounds: int = RUIN_ROUNDS) -> dict[str, list[str]]:
    """Large-neighbourhood search: take 2-4 cafés out (a café and its nearest neighbours, or cafés at random) and
    put them back by cheapest insertion, keeping the result when the total objective drops. Taking cafés out
    never breaks a rule (an earlier arrival everywhere), so every round starts from a valid plan. Deterministic:
    its random choices come from a fixed seed."""
    rng = random.Random(0)
    world = rc.world
    cur, cur_cost = {vid: list(stops) for vid, stops in routes.items()}, _total(rc, routes)
    ids = [s for stops in routes.values() for s in stops]
    for k in range(rounds):
        if k % 2 == 0:
            centre = world.cafe(rng.choice(ids))
            near = sorted(ids, key=lambda s: (_km((centre.x, centre.y), (world.cafe(s).x, world.cafe(s).y)), s))
            out = near[:rng.randint(2, 4)]
        else:
            out = rng.sample(ids, rng.randint(2, 4))
        rng.shuffle(out)
        cand = {vid: [s for s in stops if s not in out] for vid, stops in cur.items()}
        if _insert_all(rc, [world.cafe(s) for s in out], cand):
            cost = _total(rc, cand)
            if cost < cur_cost - 1e-6:
                cur, cur_cost = cand, cost
    return _relocate(rc, cur)


def _plan(world: World, rules: Rules) -> list[dict]:
    """The reference routes under `rules` (computed once per world and rules).

    Two starts, each improved by relocation: the greedy construction, and the world's fallback without the closed
    café (valid under any rules a setting draws, so there is always one). The cheaper one is improved further by
    ruin and recreate. The greedy construction is not monotone in the rules (a looser shift can corner it where a
    tighter one does not), which is why the fallback is always tried too."""
    if rules not in world.cache:
        rc = _Routes(world, rules)
        found = []
        built = _construct(rc)
        if built is not None:
            found.append(_relocate(rc, built))
        routes = {vid: [] for vid in rc.vans}
        for r in world.fallback[rules.tier]:
            routes[r["van"]] = [s for s in r["stops"] if s != rules.closed]
        found.append(_relocate(rc, routes))
        best = min(found, key=lambda routes: _total(rc, routes))
        world.cache[rules] = rc.plan(_ruin_recreate(rc, best))
    return json.loads(json.dumps(world.cache[rules]))


def reference_solution(world: World, out_dir: Path, setting: Setting) -> None:
    plan = _plan(world, rules_of(setting))
    (out_dir / "routes.json").write_text(json.dumps({"routes": plan}, indent=2), encoding="utf-8")


# ── baseline: the dispatcher's own plan ──────────────────────────────────────

def _fits(world: World, rules: Rules, van_id: str, stops: list[str]) -> bool:
    """The route leaving as early as the van may breaks no rule (cafés on other routes aside)."""
    route = {"van": van_id, "depart": _hhmm(rules.earliest(van_id)), "stops": stops}
    return all(rule == "serve_each_once" for rule, _ in simulate(world, [route], rules)[0])


def _sweep(world: World, rules: Rules, start: float) -> dict[str, list[str]] | None:
    """The dispatcher's split of the map, cafés taken by bearing from `start` (None if a café fits on no van)."""
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
        cafes = sorted((world.cafe(s) for s in extra[vid] + list(more)), key=lambda c: (c.tier, c.open_min, c.id))
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


def baseline_solution(world: World, out_dir: Path, setting: Setting) -> None:
    """What the dispatcher does without an engineer: split the map by bearing and send every van out at once.

    When the cold chain applies (medium, hard), V4 takes the partner cafés, premium first, in the order that brings
    it back soonest. The other cafés are taken in bearing order round the kitchen, starting due west (negative x),
    and loaded onto V1, V2, V3 and then V4 until the next one no longer fits (this week's tray limit, back by the
    shift end); each van serves its premium cafés first, then the rest in order of opening. A café that fits nowhere
    at its turn goes on the first van that can still take it; if one is still left over, the sweep starts again
    from the next café round. Every van leaves at 05:00, when the drivers' shift starts (in hard V2 as soon as it
    is out of the workshop), so the vans wait at cafés that are not open yet, and deliver_by is ignored. If no start
    places every café (no world built so far needs it), the world's fallback routes without the closed café are
    driven, every van leaving as early as it may: valid, since an earlier start never brings a van back later.
    """
    rules = rules_of(setting)
    first = sorted((c for c in world.open_cafes(rules) if not (c.partner and rules.cold_chain)),
                   key=lambda c: ((math.atan2(c.y, c.x) - math.pi) % (2 * math.pi), c.id))
    for start in [math.pi] + [math.atan2(c.y, c.x) for c in first[1:]]:
        routes = _sweep(world, rules, start)
        if routes is not None:
            plan = [{"van": vid, "depart": _hhmm(rules.earliest(vid)), "stops": stops}
                    for vid, stops in routes.items() if stops]
            break
    else:
        plan = [{"van": r["van"], "depart": _hhmm(rules.earliest(r["van"])),
                 "stops": [s for s in r["stops"] if s != rules.closed]} for r in world.fallback[rules.tier]]
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
