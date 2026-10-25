import shutil
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures"
sys.path.insert(0, str(FIXTURES))

NATIVE = "logistics_bakery_routing"
V1_TOY = "toy_001_order_allocation"


@pytest.fixture
def cases_root(tmp_path):
    """A private copy of one native case, so tests can prove the original is never modified."""
    dest = tmp_path / "cases"
    shutil.copytree(REPO / "cases" / NATIVE, dest / NATIVE, ignore=shutil.ignore_patterns("__pycache__"))
    return dest


@pytest.fixture
def v1_root(tmp_path):
    """A synthetic case in the external FDE-Bench v1 layout (written for these tests, not v1 material)."""
    dest = tmp_path / "v1"
    shutil.copytree(FIXTURES / "case", dest / "case")
    return dest
