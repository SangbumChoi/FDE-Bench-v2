import importlib.util
from pathlib import Path
import sys

import pytest


def test_approved_email_price_by_order_week():
    path = Path(__file__).parents[1] / 'cases/manufacturing/procurement_specialist/case.py'
    spec = importlib.util.spec_from_file_location('procurement_price_case', path)
    case = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = case
    spec.loader.exec_module(case)
    world = case.build_world(20261123)
    for setting in case.all_settings():
        view = case._View(world, setting)
        q = world.quotes['C01', 'S03']
        for qty in (q.moq, max([q.moq] + [b for b, _ in q.breaks])):
            before = view.line_cost('C01', 'S03', qty, 3)
            after = view.line_cost('C01', 'S03', qty, 4)
            assert after == pytest.approx(before * 1.20)
            spend = case._spend(view, [{'week': 4, 'component': 'C01', 'supplier': 'S03', 'qty': qty}])
            assert spend[case.month_of_week(4)] == pytest.approx(after)
        other = next(q for q in world.quotes.values() if (q.component, q.supplier) != ('C01', 'S03'))
        assert view.unit_krw(other, other.moq, 4) == view.unit_krw(other, other.moq, 3)


def test_email_changes_supplier_comparison():
    path = Path(__file__).parents[1] / 'cases/manufacturing/procurement_specialist/case.py'
    spec = importlib.util.spec_from_file_location('procurement_price_case_comparison', path)
    case = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = case
    spec.loader.exec_module(case)
    view = case._View(case.build_world(20261123), case.all_settings()[0])
    a, b = view.quotes['C01', 'S03'], view.quotes['C01', 'S01']
    assert view.unit_krw(a, a.moq, 3) < view.unit_krw(b, b.moq, 3)
    assert view.unit_krw(a, a.moq, 4) > view.unit_krw(b, b.moq, 4)
