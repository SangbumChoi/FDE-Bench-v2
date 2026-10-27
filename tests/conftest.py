import shutil
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
NATIVE = "logistics/bakery_delivery_dispatcher"


@pytest.fixture
def cases_root(tmp_path):
    """A private copy of one native case, so tests can prove the original is never modified."""
    dest = tmp_path / "cases"
    shutil.copytree(REPO / "cases" / NATIVE, dest / NATIVE, ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copy2(REPO / "cases" / "fields.yaml", dest / "fields.yaml")
    return dest
