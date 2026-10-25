"""Relaxed re-scoring for the toy case: same shape as fdebench2/case_hooks/c010_*."""
import importlib.util
import json


def relaxed_score(case, submission_dir, relaxed, rules):
    spec = importlib.util.spec_from_file_location("toy_eval", case.evaluator)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    orders, stock = m.load_data(case.data_dir)
    violations, cost = m.simulate(orders, stock, json.loads((submission_dir / m.PLAN_FILE).read_text()))
    if [v for v in violations if (r := rules.classify(v)) is None or r.id not in relaxed]:
        return {"validity_score": 0.0, "quality_score": 0.0}
    return {"validity_score": 1.0, "quality_score": m.load_baseline() / cost}
