import os
from pathlib import Path

import pytest

# Testlerde dizinin arka-plan canlı tazelemesini kapat → offline testler ağa çıkmaz.
os.environ.setdefault("DERGIPARK_DIRECTORY_REFRESH", "0")

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def _reset_shared_async_state():
    """Her testten sonra loop'a bağlı paylaşılan durumu sıfırla → testler arası
    'Event loop is closed' sızıntılarını önler (offline+live birlikte çalışınca)."""
    yield
    from dergipark_mcp import http as _http
    from dergipark_mcp.cache import default_cache as _cache
    _http._client = None  # httpx istemcisi loop'a bağlı; süreç sonunda serbest kalır
    _http._semaphore = None
    _http._rate_lock = None
    _http._last_request_ts = 0.0
    _cache._locks.clear()  # asyncio.Lock'lar loop'a bağlı; temizle


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


def read_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")
