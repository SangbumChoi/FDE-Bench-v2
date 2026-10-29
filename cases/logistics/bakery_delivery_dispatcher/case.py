"""Bakery morning delivery routing (original FDE-Bench v2 case).

A central kitchen delivers bread trays to cafés with a small van fleet on a
Monday morning. The request only says "plan the routes"; the rules that decide
validity and quality (travel model, service time, a café closed this week,
cold-chain partners, shift end, premium-first habit, lateness cost) are in the
requirements and must be asked for.
"""

from __future__ import annotations

import itertools
import json
import math
import random
from dataclasses import dataclass, field, replace
from pathlib import Path

from fdebench2.casekit import Fatal, labels, read_json, write_csv

# ── world ────────────────────────────────────────────────────────────────────

DAY_START = 5 * 60            # vans may leave from 05:00
SHIFT_END = 9 * 60 + 30       # and must be back by 09:30
RUSH_FROM = 7 * 60            # 30 km/h before 07:00, 20 km/h from 07:00 (by leg start time)
ROAD_FACTOR = 1.3
LATE_WEIGHT = 3.0
CAPACITY = 120
MAX_DRAWS = 50                # draws per seed before giving up on finding a solvable world


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
    partner: bool        # cold-chain partner: refrigerated van only
    closed: bool = False


@dataclass
class World:
    cafes: list[Cafe]
    vans: list[dict] = field(default_factory=list)
    plan: list[dict] = field(default_factory=list, repr=False)  # reference routes, found while generating

    @property
    def open_cafes(self) -> list[Cafe]:
        return [c for c in self.cafes if not c.closed]

    def cafe(self, cid: str) -> Cafe | None:
        return next((c for c in self.cafes if c.id == cid), None)


def _draw_world(rng: random.Random) -> World:
    cafes = []
    for i in range(18):
        ang, r = rng.uniform(0, 2 * math.pi), rng.uniform(2.0, 11.0)
        open_min = rng.choice([6 * 60, 6 * 60 + 30, 7 * 60, 7 * 60 + 30])
        cafes.append(Cafe(id=f"C{i + 1:02d}", district=i, x=round(r * math.cos(ang), 2), y=round(r * math.sin(ang), 2),
                          trays=rng.randint(8, 30), tier="A" if i % 3 == 0 else "B", open_min=open_min,
                          latest_min=open_min + rng.choice([45, 60, 90]), partner=i in (4, 9, 15)))
    cafes[10].closed = True  # C11: closed for renovation this week (known only to the client)
    vans = [{"id": f"V{i}", "capacity": CAPACITY, "refrigerated": i == 4} for i in range(1, 5)]
    return World(cafes, vans)


def build_world(seed: int) -> World:
    """The first usable world drawn from the seed's random stream.

    Not every draw is usable. Some have no plan that keeps all rules: only V4 may serve the three partner cafés,
    and when they open late and lie far apart V4 cannot also be back by 09:30. In others a rule cannot bind, so no
    plan breaks it alone: e.g. no route reaches 121 trays before 09:30, or the morning is too tight to also visit
    the closed café. Draws continue from the same stream until the reference solver finds a plan that breaks no
    rule (kept as the world's reference) and every rule has a plan that breaks only it.
    """
    rng = random.Random(seed)
    for _ in range(MAX_DRAWS):
        world = _draw_world(rng)
        plan = _solve(world)
        if plan is None or simulate(world, plan)[0]:
            continue
        world.plan = plan
        try:
            violating_examples(world)
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


def _hhmm(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"


def write_data(world: World, data_dir: Path, lang: str) -> None:
    c, v = labels(COLS, lang), labels(VALUES, lang)
    rows = [[cf.id, BRANCH[lang].format(d=DISTRICTS[lang][cf.district]), cf.x, cf.y, cf.trays, v[cf.tier],
             _hhmm(cf.open_min), _hhmm(cf.latest_min), v["yes" if cf.partner else "no"]] for cf in world.cafes]
    write_csv(data_dir / FILES["cafes"][lang],
              [c["id"], c["name"], c["x"], c["y"], c["trays"], c["tier"], c["open"], c["latest"], c["partner"]], rows)
    write_csv(data_dir / FILES["vans"][lang], [c["van"], c["capacity"], c["fridge"]],
              [[vn["id"], vn["capacity"], v["yes" if vn["refrigerated"] else "no"]] for vn in world.vans])


# ── simulation and scoring ───────────────────────────────────────────────────

def _travel(a: tuple[float, float], b: tuple[float, float], t: float) -> float:
    km = ROAD_FACTOR * math.hypot(a[0] - b[0], a[1] - b[1])
    return km / (30.0 if t < RUSH_FROM else 20.0) * 60.0


def _service(trays: int) -> float:
    return 4.0 + 0.2 * trays


def _parse_time(v, what: str) -> int:
    if v is None:
        return DAY_START
    try:
        h, m = str(v).strip().split(":")
        return int(h) * 60 + int(m)
    except ValueError as e:
        raise Fatal(f"{what}: time must be HH:MM, got {v!r}") from e


def simulate(world: World, routes: list[dict]) -> tuple[list[tuple[str, str]], float, dict]:
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
        load = 0
        pos, t = (0.0, 0.0), float(depart)
        seen_tier_b = False
        for sid in stops:
            cafe = world.cafe(sid)
            if cafe is None:
                raise Fatal(f"{van}: unknown stop {sid!r}")
            if sid in seen:
                violations.append(("serve_each_once", f"{sid} is served by both {seen[sid]} and {van}"))
            seen[sid] = van
            if cafe.closed:
                violations.append(("closed_cafe", f"{van} delivers to {sid}, which is closed this week"))
            if cafe.partner and not vans[van]["refrigerated"]:
                violations.append(("cold_chain", f"{sid} is a cold-chain partner but {van} is not refrigerated"))
            if cafe.tier == "B":
                seen_tier_b = True
            elif seen_tier_b:
                violations.append(("premium_first", f"{van} serves premium café {sid} after a standard café"))
            load += cafe.trays
            t += _travel(pos, (cafe.x, cafe.y), t)
            t = max(t, cafe.open_min)
            total_late += max(0.0, t - cafe.latest_min)
            t += _service(cafe.trays)
            pos = (cafe.x, cafe.y)
        t += _travel(pos, (0.0, 0.0), t)
        if load > vans[van]["capacity"]:
            violations.append(("van_capacity", f"{van} carries {load} trays > {vans[van]['capacity']}"))
        if t > SHIFT_END + 1e-9:
            violations.append(("shift_window", f"{van} returns at {_hhmm(int(math.ceil(t)))}, after 09:30"))
        total_duration += t - depart
    for cafe in world.open_cafes:
        if cafe.id not in seen:
            violations.append(("serve_each_once", f"{cafe.id} is not served"))
    objective = total_duration + LATE_WEIGHT * total_late
    return violations, objective, {"route_minutes": round(total_duration, 2), "late_minutes": round(total_late, 2)}


def score(world: World, submission_dir: Path) -> dict:
    try:
        doc = read_json(submission_dir, "routes.json")
        routes = doc.get("routes") if isinstance(doc, dict) else None
        if not isinstance(routes, list):
            raise Fatal("routes.json must be an object with a 'routes' list")
        violations, objective, metrics = simulate(world, routes)
    except Fatal as e:
        return {"fatal": str(e)}
    return {"violations": violations, "objective": objective, "metrics": metrics}


# ── reference solution ───────────────────────────────────────────────────────

SHUFFLES = 30        # shuffled insertion orders tried when the plain greedy construction corners itself


def _route_cost(world: World, van: dict, stops: list[str]) -> float | None:
    """Objective contribution of one route with the best departure time, or None if infeasible."""
    if not stops:
        return 0.0
    cafes = [world.cafe(s) for s in stops]
    if sum(c.trays for c in cafes) > van["capacity"]:
        return None
    if any(c.partner and not van["refrigerated"] for c in cafes):
        return None
    tiers = [c.tier for c in cafes]
    if "B" in tiers and "A" in tiers[tiers.index("B"):]:
        return None
    best = None
    for depart in range(DAY_START, SHIFT_END, 5):
        v, obj, _ = simulate(world, [{"van": van["id"], "depart": _hhmm(depart), "stops": stops}])
        v = [x for x in v if x[0] != "serve_each_once"]
        if not v and (best is None or obj < best[0]):
            best = (obj, depart)
    return None if best is None else best[0]


def _best_depart(world: World, van: dict, stops: list[str]) -> int:
    best = None
    for depart in range(DAY_START, SHIFT_END, 5):
        v, obj, _ = simulate(world, [{"van": van["id"], "depart": _hhmm(depart), "stops": stops}])
        v = [x for x in v if x[0] != "serve_each_once"]
        if not v and (best is None or obj < best[0]):
            best = (obj, depart)
    return best[1]


def _insert_all(world: World, by_id: dict, order: list[Cafe], routes: dict[str, list[str]]) -> bool:
    """Cheapest feasible insertion of each café of `order`, in turn (routes change in place).

    False when a café fits on no route."""
    for cafe in order:
        best = None
        for vid, stops in routes.items():
            base = _route_cost(world, by_id[vid], stops)
            if base is None:
                continue
            for pos in range(len(stops) + 1):
                cand = stops[:pos] + [cafe.id] + stops[pos:]
                cost = _route_cost(world, by_id[vid], cand)
                if cost is not None and (best is None or cost - base < best[0]):
                    best = (cost - base, vid, cand)
        if best is None:
            return False
        routes[best[1]] = best[2]
    return True


def _starts(world: World):
    """(insertion order, initial routes) for the construction, tried in turn until one places every café.

    First the plain greedy: cold-chain partners first (only the refrigerated van can take them), then the rest by
    tier, biggest first. Greedy insertion can corner itself (two partners in an order that leaves V4 no time for
    the third, or the last cafés finding no van with room and time), so next the refrigerated van starts from each
    workable order of the partners, cheapest first, and last from the cheapest one with the others in shuffled orders.
    """
    order = sorted(world.open_cafes, key=lambda c: (not c.partner, c.tier, -c.trays))
    yield order, {}
    fridge = next(vn for vn in world.vans if vn["refrigerated"])
    rest = [c for c in order if not c.partner]
    seeded = []
    for perm in itertools.permutations([c.id for c in order if c.partner]):
        cost = _route_cost(world, fridge, list(perm))
        if cost is not None:
            seeded.append((cost, list(perm)))
    seeded.sort()
    for _, perm in seeded:
        yield rest, {fridge["id"]: perm}
    rng = random.Random(0)
    for _ in range(SHUFFLES if seeded else 0):
        shuffled = rest[:]
        rng.shuffle(shuffled)
        yield shuffled, {fridge["id"]: seeded[0][1]}


def _solve(world: World) -> list[dict] | None:
    """Routes that break no rule (greedy insertion, then single-stop relocation), or None if none is found."""
    by_id = {vn["id"]: vn for vn in world.vans}
    for order, start in _starts(world):
        routes = {vid: list(start.get(vid, [])) for vid in by_id}
        if _insert_all(world, by_id, order, routes):
            break
    else:
        return None
    # Improvement: relocate single stops while the total objective drops.
    improved = True
    while improved:
        improved = False
        for src in list(routes):
            for sid in list(routes[src]):
                src_without = [s for s in routes[src] if s != sid]
                gain_src = _route_cost(world, by_id[src], routes[src]) - _route_cost(world, by_id[src], src_without)
                for dst in routes:
                    base_dst = _route_cost(world, by_id[dst], routes[dst] if dst != src else src_without)
                    target = routes[dst] if dst != src else src_without
                    for pos in range(len(target) + 1):
                        cand = target[:pos] + [sid] + target[pos:]
                        cost = _route_cost(world, by_id[dst], cand)
                        if cost is not None and base_dst is not None and cost - base_dst < gain_src - 1e-6:
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
    return [{"van": vid, "depart": _hhmm(_best_depart(world, by_id[vid], stops)), "stops": stops}
            for vid, stops in routes.items() if stops]


def reference_solution(world: World, out_dir: Path) -> None:
    (out_dir / "routes.json").write_text(json.dumps({"routes": world.plan}, indent=2), encoding="utf-8")


# ── baseline: the dispatcher's own plan ──────────────────────────────────────

def _fits(world: World, van_id: str, stops: list[str]) -> bool:
    """The route leaving at 05:00 breaks no rule (cafés on other routes aside)."""
    v = simulate(world, [{"van": van_id, "depart": _hhmm(DAY_START), "stops": stops}])[0]
    return all(rule == "serve_each_once" for rule, _ in v)


def _sweep(world: World, start: float) -> dict[str, list[str]] | None:
    """The dispatcher's split of the map, cafés taken by bearing from `start` (None if a café fits on no van)."""
    vans = [vn["id"] for vn in world.vans]
    fridge = next(vn["id"] for vn in world.vans if vn["refrigerated"])
    orders = [list(p) for p in itertools.permutations(c.id for c in world.open_cafes if c.partner)
              if _fits(world, fridge, list(p))]
    if not orders:
        return None
    fixed = {vid: [] for vid in vans}
    fixed[fridge] = min(orders, key=lambda p: simulate(world, [{"van": fridge, "stops": p}])[2]["route_minutes"])
    extra: dict[str, list[str]] = {vid: [] for vid in vans}

    def route(vid: str, more: tuple[str, ...] = ()) -> list[str]:
        cafes = sorted((world.cafe(s) for s in extra[vid] + list(more)), key=lambda c: (c.tier, c.open_min, c.id))
        return fixed[vid] + [c.id for c in cafes]

    order = [vid for vid in vans if vid != fridge] + [fridge]
    rest = sorted((c for c in world.open_cafes if not c.partner),
                  key=lambda c: ((math.atan2(c.y, c.x) - start) % (2 * math.pi), c.id))
    i, left = 0, []
    for c in rest:
        while i < len(order) and not _fits(world, order[i], route(order[i], (c.id,))):
            i += 1
        (extra[order[i]] if i < len(order) else left).append(c.id)
    for cid in left:
        vid = next((v for v in order if _fits(world, v, route(v, (cid,)))), None)
        if vid is None:
            return None
        extra[vid].append(cid)
    return {vid: route(vid) for vid in vans}


def baseline_solution(world: World, out_dir: Path) -> None:
    """What the dispatcher does without an engineer: split the map by bearing and send every van at 05:00.

    V4 takes the partner cafés, premium first, in the order that brings it back soonest. The other cafés are
    taken in bearing order round the kitchen, starting due west (negative x), and loaded onto V1, V2, V3 and then
    V4 until the next one no longer fits (tray capacity, back by 09:30); each van serves its premium cafés first,
    then the rest in order of opening. A café that fits nowhere at its turn goes on the first van that can still
    take it; if one is still left over, the sweep starts again from the next café round. Every van leaves at 05:00,
    when the drivers' shift starts, so the vans wait at cafés that are not open yet, and deliver_by is ignored.
    If no start places every café (no world built so far needs it), the reference routes are driven, every van
    leaving at 05:00: valid, since an earlier start never brings a van back later.
    """
    first = sorted((c for c in world.open_cafes if not c.partner),
                   key=lambda c: ((math.atan2(c.y, c.x) - math.pi) % (2 * math.pi), c.id))
    for start in [math.pi] + [math.atan2(c.y, c.x) for c in first[1:]]:
        routes = _sweep(world, start)
        if routes is not None:
            plan = [{"van": vid, "depart": _hhmm(DAY_START), "stops": stops} for vid, stops in routes.items() if stops]
            break
    else:
        plan = [{**r, "depart": _hhmm(DAY_START)} for r in world.plan]
    (out_dir / "routes.json").write_text(json.dumps({"routes": plan}, indent=2), encoding="utf-8")


# ── violating examples ───────────────────────────────────────────────────────

OVERFULL_BUDGET = 20000   # route evaluations per search for an over-full route


class NoExample(Exception):
    """No plan breaks this rule alone in this world (build_world draws again)."""


def _retimed(world: World, route: dict, rule: str) -> dict | None:
    """`route` at its best departure among those where it breaks no rule but `rule` (None if there is none)."""
    best = None
    for depart in range(DAY_START, SHIFT_END, 5):
        cand = {**route, "depart": _hhmm(depart)}
        v, obj, _ = simulate(world, [cand])
        if {x[0] for x in v} <= {rule, "serve_each_once"} and (best is None or obj < best[0]):
            best = (obj, cand)
    return None if best is None else best[1]


def _tier_positions(world: World, stops: list[str], cid: str) -> range:
    """Where café `cid` can join `stops` with premium cafés still ahead of standard ones."""
    tiers = [world.cafe(s).tier for s in stops]
    if world.cafe(cid).tier == "A":
        return range(0, (tiers.index("B") if "B" in tiers else len(tiers)) + 1)
    return range(max((k for k, t in enumerate(tiers) if t == "A"), default=-1) + 1, len(stops) + 1)


def _overfull_routes(world: World, van: dict, base: list[str], budget: int = OVERFULL_BUDGET):
    """Supersets of route `base` for `van` that carry more than it holds but keep every other rule, depth first.

    Each step adds an open café at its cheapest position, trying first the café that adds the fewest route minutes
    per tray. Leaving at 05:00 is enough to test the shift: an earlier start never brings a van back later. Stops
    after `budget` route evaluations.
    """
    spent = 0

    def minutes(stops: list[str]) -> float | None:
        nonlocal spent
        spent += 1
        v, _, metrics = simulate(world, [{"van": van["id"], "depart": _hhmm(DAY_START), "stops": stops}])
        return None if {x[0] for x in v} - {"serve_each_once", "van_capacity"} else metrics["route_minutes"]

    def grow(stops: list[str], load: int, now: float):
        if load > van["capacity"]:
            yield stops
            return
        nexts = []
        for c in world.open_cafes:
            if c.id in stops:
                continue
            best = None
            for pos in _tier_positions(world, stops, c.id):
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


def violating_examples(world: World) -> dict:
    """One deliverable per rule that breaks exactly that rule (for the validator).

    Each example edits the reference plan. Candidate edits are tried in turn, retiming the edited route where that
    helps, and the first one the scorer finds breaking that rule and nothing else is kept, so an edit cannot push a
    route past 09:30 or over capacity by accident.
    """
    ref = world.plan
    vans = {vn["id"]: vn for vn in world.vans}
    fridge = next(vid for vid, vn in vans.items() if vn["refrigerated"])
    closed = next(c.id for c in world.cafes if c.closed)

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
        yield replaced(plan, i, _retimed(world, {**plan[i], "stops": stops}, rule))

    def insertions(plan: list[dict], cid: str, rule: str, van_ids):
        """Café cid added to a route of one of `van_ids` (least loaded first), or alone on an unused one."""
        for i in sorted(range(len(plan)), key=lambda i: load(plan[i]["stops"])):
            if plan[i]["van"] in van_ids:
                stops = plan[i]["stops"]
                for pos in reversed(_tier_positions(world, stops, cid)):
                    yield from edits(plan, i, stops[:pos] + [cid] + stops[pos:], rule)
        used = {r["van"] for r in plan}
        for vid in van_ids:
            if vid not in used:
                route = _retimed(world, {"van": vid, "stops": [cid]}, rule)
                if route is not None:
                    yield copy(plan) + [route]

    def first(rule: str, candidates) -> list[dict]:
        for plan in candidates:
            if plan is not None and {x[0] for x in simulate(world, plan)[0]} == {rule}:
                return plan
        raise NoExample(f"no edit of the reference plan breaks only {rule}")

    def add_closed():
        # Also deliver to the closed café, on a route that has room and time for it; else plan the morning as if it
        # were open, which keeps every other rule.
        yield from insertions(ref, closed, "closed_cafe", list(vans))
        yield _solve(replace(world, cafes=[replace(c, closed=False) for c in world.cafes], plan=[]))

    def drop_one():
        # Leave one café out; dropping a stop never makes a route later or heavier.
        for i, r in enumerate(ref):
            for pos in reversed(range(len(r["stops"]))):
                yield from edits(ref, i, r["stops"][:pos] + r["stops"][pos + 1:], "serve_each_once")

    def partner_on_dry_van():
        # The refrigerated van's route driven by a dry van (swapping routes with it), else one partner moved over.
        dry = [vid for vid in vans if not vans[vid]["refrigerated"]]
        for c in [i for i, r in enumerate(ref) if r["van"] == fridge]:
            for vid in dry:
                plan = copy(ref)
                for r in plan:
                    if r["van"] == vid:
                        r["van"] = fridge
                plan[c]["van"] = vid
                yield plan
            for sid in [s for s in ref[c]["stops"] if world.cafe(s).partner]:
                rest = copy(ref)
                rest[c]["stops"].remove(sid)
                yield from insertions(rest, sid, "cold_chain", dry)

    def overload():
        # One van carries more than it holds. First a route of the plan grows with cafés from the other routes,
        # which only get shorter (heaviest route first); else a van's route is rebuilt from its partner cafés alone
        # (no dry van may take them; unused vans first) and the cafés it displaces move to the other vans by
        # cheapest feasible insertion.
        stops_of = {vid: next((r["stops"] for r in ref if r["van"] == vid), []) for vid in vans}
        starts = ([(vid, stops_of[vid]) for vid in sorted(vans, key=lambda v: -load(stops_of[v]))]
                  + [(vid, [s for s in stops_of[vid] if world.cafe(s).partner])
                     for vid in sorted(vans, key=lambda v: len(stops_of[v]))])
        for vid, base in starts:
            for stops in _overfull_routes(world, vans[vid], base):
                full = _retimed(world, {"van": vid, "stops": stops}, "van_capacity")
                others = {v: [s for s in stops_of[v] if s not in stops] for v in vans if v != vid}
                if full and _insert_all(world, vans, [world.cafe(s) for s in stops_of[vid] if s not in stops], others):
                    yield [{"van": v, "depart": _hhmm(_best_depart(world, vans[v], s)), "stops": s}
                           for v, s in others.items() if s] + [full]

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
                    if world.cafe(sid).partner and not vans[r["van"]]["refrigerated"]:
                        continue
                    tiers = [world.cafe(s).tier for s in r["stops"]]
                    if "B" not in tiers:
                        continue
                    for pos in range(tiers.index("B") + 1, len(r["stops"]) + 1):
                        yield from edits(rest, i, r["stops"][:pos] + [sid] + r["stops"][pos:], "premium_first")

    def outside_shift():
        # Leave before 05:00 (an earlier start never makes a route later), else leave so late it returns after 09:30.
        for i, r in enumerate(ref):
            yield replaced(ref, i, {**r, "depart": "04:30"})
        for i, r in enumerate(ref):
            for depart in range(SHIFT_END, DAY_START, -5):
                yield replaced(ref, i, {**r, "depart": _hhmm(depart)})

    def write(routes: list[dict]):
        return lambda out: (out / "routes.json").write_text(json.dumps({"routes": routes}), encoding="utf-8")

    makers = {"closed_cafe": add_closed, "serve_each_once": drop_one, "cold_chain": partner_on_dry_van,
              "van_capacity": overload, "premium_first": premium_after_standard, "shift_window": outside_shift}
    return {rule: write(first(rule, make())) for rule, make in makers.items()}
