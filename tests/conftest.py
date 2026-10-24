import shutil
import sys
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
sys.path.insert(0, str(FIXTURES))


@pytest.fixture
def v1_root(tmp_path):
    """A private copy of the fixture case tree, so tests can prove the original is never modified."""
    dest = tmp_path / "v1"
    shutil.copytree(FIXTURES / "case", dest / "case")
    return dest
