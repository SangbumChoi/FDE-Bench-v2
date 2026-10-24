"""Toy evaluator in the v1 style (synthetic fixture for fdebench2 tests).

EXTRACTOR_SPEC:
    solution.json = {"assignments": [{"order_id": str, "warehouse": str}]}
"""
import csv
import json
from pathlib import Path

_HERE = Path(__file__).resolve().parent
PLAN_FILE = "solution.json"


def load_data(data_dir):
    d = Path(data_dir)
    with open(d / "orders.csv", encoding="utf-8") as f:
        orders = {r["订单号"]: int(r["数量"]) for r in csv.DictReader(f)}
    with open(d / "stock.csv", encoding="utf-8") as f:
        stock = {r["仓库"]: (float(r["库存"]), float(r["单位成本"])) for r in csv.DictReader(f)}
    return orders, stock


def load_baseline():
    return json.loads((_HERE / "baseline" / "reference_metrics.json").read_text())["reference_value"]


def simulate(orders, stock, submission):
    violations, used, cost, seen = [], {}, 0.0, set()
    for a in submission.get("assignments", []):
        oid, wh = str(a.get("order_id")), str(a.get("warehouse"))
        if oid not in orders or wh not in stock or oid in seen:
            violations.append(f"HC0_非法分配: {oid}->{wh}")
            continue
        seen.add(oid)
        if wh == "W3":
            violations.append(f"HC2_W3盘点: {oid}")
        used[wh] = used.get(wh, 0) + orders[oid]
        cost += orders[oid] * stock[wh][1]
    for wh, q in used.items():
        if q > stock[wh][0]:
            violations.append(f"HC1_库存超用: {wh} {q} > {stock[wh][0]}")
    if seen != set(orders):
        violations.append(f"HC0_漏单: {len(set(orders) - seen)}")
    return violations, cost


def evaluate(submission_dir, data_dir):
    metrics = {"validity_score": 0.0, "quality_score": 0.0, "error_info": {}}
    p = Path(submission_dir) / PLAN_FILE
    if not p.exists():
        metrics["error_info"] = {"fatal": ["missing solution.json"]}
        return metrics
    orders, stock = load_data(data_dir)
    violations, cost = simulate(orders, stock, json.loads(p.read_text(encoding="utf-8")))
    metrics["total_cost"] = cost
    if violations:
        metrics["error_info"] = {"constraint": violations[:8]}
        return metrics
    metrics["validity_score"] = 1.0
    metrics["quality_score"] = load_baseline() / cost if cost > 0 else 0.0
    return metrics
