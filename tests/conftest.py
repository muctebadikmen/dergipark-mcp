import os
from pathlib import Path

import pytest

# Testlerde dizinin arka-plan canlı tazelemesini kapat → offline testler ağa çıkmaz.
os.environ.setdefault("DERGIPARK_DIRECTORY_REFRESH", "0")

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


def read_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")
