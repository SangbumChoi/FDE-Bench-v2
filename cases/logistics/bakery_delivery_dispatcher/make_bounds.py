"""Writes reference/best_known.json: for each setting the ground truth audit measures on the public world (and the
leaderboard round's rule seeds), the best plan known and a proven lower bound on its objective.

    python cases/logistics/bakery_delivery_dispatcher/make_bounds.py [--time-limit 300] [--rounds 3000] [--refresh]

Each setting gets two solvers. A mixed-integer model (scipy's HiGHS) of a relaxation of the setting: every café
visited once by one of at most four routes from the kitchen, this week's tray limit, back by the shift end, the cold
chain (all partner cafés on one route), premium cafés never right after a standard one where the habit holds,
waiting until a café opens and lateness at three van minutes a minute. The travel times are the client's, the
morning rush included: every leg costs its drive at the speed before the rush, plus the extra minutes the rush adds
to it, which a binary per leg prices exactly (below). What the model relaxes: departures are free to the second, a
van may wait anywhere (the simulator waits only for an opening), and V2's workshop morning becomes "at most three
routes leave before 06:40" (the model does not know which route is V2's). Every valid plan therefore maps onto a
solution of the model with an objective no higher, so the model's dual bound is a lower bound on the objective of
every valid plan. Its best routes, given to the vans in the cheapest valid way and driven with departures to the
minute, are a candidate plan. The second solver is a long ruin-and-recreate search from the reference and from that
plan (several seeds, many more rounds). The cheaper valid plan is stored when it beats the reference.

The rush. A leg whose drive at the fast speed takes tf minutes and that starts at t takes tf while t + tf <= rush,
tf + k (t + tf - rush) while it crosses the rush and tf + k tf once t >= rush (k = fast/slow - 1 = 0.5). On each side
of the rush that extra is at least the linear piece that holds there, and a binary per leg start (the leg out of
each café, and each route's first leg) says which side the leg starts on; for a first leg the extra is written in
terms of its arrival a: (a - rush) k / (1 + k) up to a = rush + (1 + k) tf, k tf after. Without a rush the model is
the setting itself apart from the minute departures, and it is solved to optimality in every easy and most medium
settings.

The stored entries are keyed by a fingerprint of the world's data, so a changed world is never read with old
results (case.py then falls back to the reference and the service-time bound). `--refresh` recomputes entries
made by an older model.
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
import time
from pathlib import Path

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import lil_matrix

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parents[2]))

from fdebench2.audit import measured_settings  # noqa: E402
from fdebench2.cases import NativeCase  # noqa: E402

ROUND_SEEDS = (108807, 519122, 904685)
MODEL = "rush-exact-1"        # the model version stored with each entry (--refresh recomputes older ones)


def mip(m, world, rules, time_limit: float) -> tuple[float | None, list[dict] | None, str]:
    """(dual bound, plan or None, status) of the relaxation described above."""
    cafes = world.open_cafes(rules)
    n = len(cafes)
    nodes = [None] + cafes
    tr = rules.travel
    rush = rules.rush
    fast = tr.fast if rush is not None else tr.average
    k_extra = (fast / tr.slow - 1.0) if rush is not None else 0.0

    def tf(i: int, j: int) -> float:
        a = (0.0, 0.0) if i == 0 else (nodes[i].x, nodes[i].y)
        b = (0.0, 0.0) if j == 0 else (nodes[j].x, nodes[j].y)
        return m._km(a, b, tr.road) / fast * 60.0

    svc = [0.0] + [m._service(c.trays, tr) for c in cafes]
    arcs = [(i, j) for i in range(n + 1) for j in range(n + 1) if i != j
            and not (i and j and rules.premium_first and nodes[i].tier == "B" and nodes[j].tier == "A")]
    ix = {a: k for k, a in enumerate(arcs)}
    nx = len(arcs)
    names = ("S", "A", "L", "U", "R", "Y", "z", "dl", "zd", "d0", "w")
    base = {name: nx + k * n for k, name in enumerate(names)}
    nv = nx + len(names) * n

    def v(name: str, i: int) -> int:
        return base[name] + i - 1

    end, start = rules.shift_end, m.DAY_START
    lo, hi, cost = np.zeros(nv), np.ones(nv), np.zeros(nv)
    integrality = np.zeros(nv)
    integrality[:nx] = 1
    for name in ("R", "Y", "z", "zd", "w"):
        integrality[base[name]:base[name] + n] = 1
    for (i, j), k in ix.items():
        cost[k] = tf(i, j)
    for i in range(1, n + 1):
        c = nodes[i]
        latest_start = end - svc[i] - tf(i, 0)
        lo[v("S", i)], hi[v("S", i)] = c.open_min, latest_start
        lo[v("A", i)], hi[v("A", i)] = start + tf(0, i), latest_start
        lo[v("L", i)], hi[v("L", i)] = 0.0, max(0.0, latest_start - c.latest_min)
        lo[v("U", i)], hi[v("U", i)] = c.trays, rules.capacity
        hi[v("dl", i)] = hi[v("d0", i)] = 200.0 if rush is not None else 0.0
        if rules.cold_chain and c.partner:
            lo[v("R", i)] = 1.0
        if rush is None:
            hi[v("z", i)] = hi[v("zd", i)] = 0.0
        if not rules.ready:
            hi[v("w", i)] = 0.0
        cost[v("S", i)] += 1.0               # waiting at i = start of service - arrival
        cost[v("A", i)] -= 1.0
        cost[v("L", i)] = rules.late_weight
        cost[v("dl", i)] = cost[v("d0", i)] = 1.0
    if any(lo[k] > hi[k] + 1e-9 for k in range(nv)):
        return None, None, "infeasible bounds"
    rows, rlo, rhi = [], [], []

    def row(coefs: dict, low: float, high: float) -> None:
        rows.append(coefs)
        rlo.append(low)
        rhi.append(high)

    big = (end - start) + 250.0
    for i in range(1, n + 1):
        row({ix[(i, j)]: 1 for j in range(n + 1) if (i, j) in ix}, 1, 1)
        row({ix[(j, i)]: 1 for j in range(n + 1) if (j, i) in ix}, 1, 1)
        row({v("S", i): 1, v("A", i): -1}, 0, np.inf)
        row({v("L", i): 1, v("S", i): -1}, -nodes[i].latest_min, np.inf)
        if rush is not None:
            # z_i: the leg out of i starts before the rush (0) or at or after it (1)
            row({v("S", i): 1, v("z", i): -big}, -np.inf, rush - svc[i])
            row({v("S", i): 1, v("z", i): -big}, rush - svc[i] - big, np.inf)
            out = {ix[(i, j)]: tf(i, j) for j in range(n + 1) if (i, j) in ix}
            after = {v("dl", i): 1, v("z", i): -big}                         # z_i = 1: dl_i >= k tf(out)
            before = {v("dl", i): 1, v("z", i): big, v("S", i): -k_extra}    # z_i = 0: dl_i >= k (t + tf - rush)
            for kk, t in out.items():
                after[kk] = -k_extra * t
                before[kk] = -k_extra * t
            row(after, -big, np.inf)
            row(before, k_extra * (svc[i] - rush), np.inf)
            # the route's first leg, in terms of the arrival A_i (zd_i: at or after rush + its slow drive)
            slow0, x0, g = tf(0, i) * (1 + k_extra), ix[(0, i)], k_extra / (1 + k_extra)
            row({v("A", i): 1, v("zd", i): -big}, -np.inf, rush + slow0)
            row({v("A", i): 1, v("zd", i): -big}, rush + slow0 - big, np.inf)
            row({v("d0", i): 1, v("A", i): -g, x0: -big, v("zd", i): big}, -g * rush - big, np.inf)
            row({v("d0", i): 1, x0: -big, v("zd", i): -big}, k_extra * tf(0, i) - 2 * big, np.inf)
        if rules.ready:
            # w_i = 1: the route starting at i leaves the kitchen at or after the held van's time
            row({v("A", i): 1, v("d0", i): -1, v("w", i): -big}, rules.ready[0][1] + tf(0, i) - big, np.inf)
            row({v("w", i): 1, ix[(0, i)]: -1}, -np.inf, 0)
    row({ix[(0, j)]: 1 for j in range(1, n + 1)}, 1, len(world.vans))
    if rules.ready:
        # at most (vans - held vans) routes leave before the held vans may
        held = {ix[(0, j)]: 1 for j in range(1, n + 1)}
        held.update({v("w", j): -1 for j in range(1, n + 1)})
        row(held, -np.inf, len(world.vans) - len(rules.ready))
    for (i, j), k in ix.items():
        if i == 0:
            continue
        if j == 0:          # back by the shift end
            row({v("S", i): 1, v("dl", i): 1, k: big}, -np.inf, end - svc[i] - tf(i, 0) + big)
            continue
        t = svc[i] + tf(i, j)
        row({v("A", j): 1, v("S", i): -1, v("dl", i): -1, k: -big}, t - big, np.inf)
        row({v("A", j): 1, v("S", i): -1, v("dl", i): -1, k: big}, -np.inf, t + big)
        row({v("U", j): 1, v("U", i): -1, k: -rules.capacity}, nodes[j].trays - rules.capacity, np.inf)
        if rules.cold_chain:
            row({v("R", j): 1, v("R", i): -1, k: 1}, -np.inf, 1)
            row({v("R", i): 1, v("R", j): -1, k: 1}, -np.inf, 1)
    if rules.cold_chain:
        for j in range(1, n + 1):
            row({v("Y", j): 1, ix[(0, j)]: -1, v("R", j): -1}, -1, np.inf)
        row({v("Y", j): 1 for j in range(1, n + 1)}, -np.inf, 1)
    mat = lil_matrix((len(rows), nv))
    for r, coefs in enumerate(rows):
        for k, val in coefs.items():
            mat[r, k] = val
    res = milp(cost, constraints=LinearConstraint(mat.tocsr(), rlo, rhi), integrality=integrality,
               bounds=Bounds(lo, hi), options={"time_limit": time_limit, "disp": False, "mip_rel_gap": 1e-7})
    const = sum(svc)
    bound = getattr(res, "mip_dual_bound", None)
    bound = None if bound is None or not np.isfinite(bound) else float(bound) + const
    if res.status == 0:
        bound = float(res.fun) + const if bound is None else bound
    plan = None
    if res.x is not None:
        succ = {i: j for (i, j), k in ix.items() if res.x[k] > 0.5}
        routes = []
        for j in [j for j in range(1, n + 1) if res.x[ix[(0, j)]] > 0.5]:
            stops, k = [], j
            while k != 0:
                stops.append(nodes[k].id)
                k = succ[k]
            routes.append(stops)
        plan = assign(m, world, rules, routes)
    return bound, plan, {0: "optimal", 1: "time limit"}.get(res.status, f"status {res.status}")


def assign(m, world, rules, routes: list[list[str]]) -> list[dict] | None:
    """The model's routes given to the vans in the cheapest way that keeps every rule (each van at its best
    departure), polished by local search; None when no assignment keeps them."""
    rc = m._Routes(world, rules)
    vans = [v["id"] for v in world.vans]
    routes = routes + [[]] * (len(vans) - len(routes))
    best = None
    for perm in itertools.permutations(range(len(vans))):
        rounds = {vans[p]: routes[k] for k, p in enumerate(perm)}
        costs = [rc.cost(vid, stops) for vid, stops in rounds.items()]
        if all(c is not None for c in costs) and (best is None or sum(costs) < best[0]):
            best = (sum(costs), rounds)
    return None if best is None else rc.plan(m._polish(rc, best[1]))


def search(m, world, rules, start: list[dict], rounds: int, seeds: int) -> list[dict]:
    """A long ruin-and-recreate search from `start` (several seeds), polished with departures to the minute."""
    rc = m._Routes(world, rules, fine=False)
    routes = {v["id"]: [] for v in world.vans}
    for r in start:
        routes[r["van"]] = list(r["stops"])
    runs = [m._ruin_recreate(rc, routes, rounds=rounds, seed=100 + k, cooling=0.01 * (k % 2)) for k in range(seeds)]
    fine = m._Routes(world, rules)
    best = min(runs, key=lambda r: m._total(rc, r))
    return fine.plan(m._polish(fine, best))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--time-limit", type=float, default=300.0)
    ap.add_argument("--rounds", type=int, default=3000)
    ap.add_argument("--seeds", type=int, default=4)
    ap.add_argument("--refresh", action="store_true", help="recompute entries made by an older model")
    args = ap.parse_args()
    case = NativeCase(ROOT)
    m = case.module
    world = case.world
    out_path = m.BOUNDS_FILE
    store = json.loads(out_path.read_text(encoding="utf-8")) if out_path.is_file() else {}
    store = {k: v for k, v in store.items() if k == m.world_key(world)}
    entries = store.setdefault(m.world_key(world), {})
    settings = [s.case for ss in measured_settings(case).values() for s in ss]
    settings += [case.at(t, seed) for t in case.tiers for seed in ROUND_SEEDS]
    for c in settings:
        key = m.setting_key(c.setting)
        old = entries.get(key)
        if old is not None and (old.get("model") == MODEL or not args.refresh):
            continue
        t0 = time.time()
        rules = m.rules_of(c.setting)
        ref = m._plan(world, rules)
        ref_obj = m.simulate(world, ref, rules)[1]
        bound, plan, status = mip(m, world, rules, args.time_limit)
        cands = [ref, search(m, world, rules, ref, args.rounds, args.seeds)]
        if plan is not None:
            cands.append(plan)
            cands.append(search(m, world, rules, plan, args.rounds // 2, 2))
        if old is not None and old.get("plan"):
            cands.append(old["plan"])
        valid = [(m.simulate(world, p, rules)[1], k, p) for k, p in enumerate(cands)
                 if not m.simulate(world, p, rules)[0]]
        obj, _, best = min(valid, key=lambda x: (x[0], x[1]))
        if old is not None and old.get("bound") is not None and (bound is None or old["bound"] > bound):
            bound = old["bound"]       # both are proven: keep the tighter
        entries[key] = {"objective": round(obj, 6), "reference": round(ref_obj, 6), "bound": bound,
                        "mip": status, "model": MODEL, "plan": best if obj < ref_obj - 1e-9 else None}
        print(f"{key}: reference {ref_obj:.2f}, best {obj:.2f}, bound {bound if bound is None else round(bound, 2)} "
              f"({status}, {time.time() - t0:.0f} s)", flush=True)
        out_path.parent.mkdir(exist_ok=True)
        out_path.write_text(json.dumps(store, indent=1, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
