"""Bakery morning delivery routing (original FDE-Bench v2 case).

A central kitchen delivers bread trays to cafés with a small van fleet on a
Monday morning. The request only says "plan the routes"; the rules that decide
validity and quality (travel model, service time, a café closed this week,
cold-chain partners, shift end, premium-first habit, lateness cost) are in the
requirements and must be asked for.
"""

from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass, field
from pathlib import Path

from fdebench2.casekit import Fatal, labels, read_json, write_csv

# ── world ────────────────────────────────────────────────────────────────────

DAY_START = 5 * 60            # vans may leave from 05:00
SHIFT_END = 9 * 60 + 30       # and must be back by 09:30
RUSH_FROM = 7 * 60            # 30 km/h before 07:00, 20 km/h from 07:00 (by leg start time)
ROAD_FACTOR = 1.3
LATE_WEIGHT = 3.0
CAPACITY = 120


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

    @property
    def open_cafes(self) -> list[Cafe]:
        return [c for c in self.cafes if not c.closed]

    def cafe(self, cid: str) -> Cafe | None:
        return next((c for c in self.cafes if c.id == cid), None)


def build_world(seed: int) -> World:
    rng = random.Random(seed)
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
    "latest": {"zh": "最晚到货", "en": "deliver_by", "ko": "최종도착", "ja": "納品期限", "es": "entregar_antes"},
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


def _solve(world: World) -> list[dict]:
    vans = world.vans
    routes: dict[str, list[str]] = {vn["id"]: [] for vn in vans}
    by_id = {vn["id"]: vn for vn in vans}
    # Cold-chain partners first (only the refrigerated van can take them), then the rest by tier, biggest first.
    order = sorted(world.open_cafes, key=lambda c: (not c.partner, c.tier, -c.trays))
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
            raise AssertionError(f"reference solver cannot place {cafe.id}")
        routes[best[1]] = best[2]
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
    (out_dir / "routes.json").write_text(json.dumps({"routes": _solve(world)}, indent=2), encoding="utf-8")


def violating_examples(world: World) -> dict:
    """One deliverable per rule that breaks exactly that rule (for the validator)."""
    ref = _solve(world)

    def write(routes):
        return lambda out: (out / "routes.json").write_text(json.dumps({"routes": routes}), encoding="utf-8")

    def mutate(fn):
        routes = json.loads(json.dumps(ref))
        fn(routes)
        return write(routes)

    closed = next(c.id for c in world.cafes if c.closed)
    partner = next(c.id for c in world.open_cafes if c.partner)
    fridge = next(v["id"] for v in world.vans if v["refrigerated"])

    def add_closed(rs):
        # Visit the closed café last on the refrigerated route's van with the most slack.
        r = min(rs, key=lambda r: sum(world.cafe(s).trays for s in r["stops"]))
        r["stops"].append(closed)

    def drop_one(rs):
        r = next(r for r in rs if len(r["stops"]) > 1)
        r["stops"].pop()

    def partner_on_dry_van(rs):
        # Same routes, but the refrigerated van and a dry van swap assignments.
        cold = next(r for r in rs if partner in r["stops"])
        dry = next(r for r in rs if r["van"] != fridge)
        cold["van"], dry["van"] = dry["van"], cold["van"]

    def overload(rs):
        # Pull standard cafés from other dry routes onto one route until it is over capacity.
        r = next(r for r in rs if r["van"] != fridge)
        load = sum(world.cafe(s).trays for s in r["stops"])
        for other in rs:
            if other is r or other["van"] == fridge:
                continue
            for sid in [s for s in other["stops"] if world.cafe(s).tier == "B"]:
                if load > CAPACITY:
                    return
                other["stops"].remove(sid)
                r["stops"].append(sid)
                load += world.cafe(sid).trays

    def premium_after_standard(rs):
        # Swap a premium café behind a standard one, choosing a swap that breaks nothing else.
        for r in rs:
            for i in range(len(r["stops"])):
                for j in range(i + 1, len(r["stops"])):
                    a, b = world.cafe(r["stops"][i]), world.cafe(r["stops"][j])
                    if a.tier == "A" and b.tier == "B":
                        trial = r["stops"][:]
                        trial[i], trial[j] = trial[j], trial[i]
                        v, _, _ = simulate(world, [{**r, "stops": trial}])
                        if {x[0] for x in v} - {"serve_each_once"} == {"premium_first"}:
                            r["stops"] = trial
                            return
        raise AssertionError("no clean premium_first example")

    def too_early(rs):
        rs[0]["depart"] = "04:30"

    return {"closed_cafe": mutate(add_closed), "serve_each_once": mutate(drop_one),
            "cold_chain": mutate(partner_on_dry_van), "van_capacity": mutate(overload),
            "premium_first": mutate(premium_after_standard), "shift_window": mutate(too_early)}
