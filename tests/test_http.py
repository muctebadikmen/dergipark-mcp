"""Nazik HTTP istemcisi — geçici 5xx retry davranışı (offline, mock transport).

DergiPark'ın OAI ucu ara sıra geçici 500 döndürür; GET'ler salt-okunur olduğundan
yeniden denenmeli. Bu testler retry'in çalıştığını ve kalıcı hatada pes ettiğini doğrular.
"""

import httpx
import pytest

from dergipark_mcp import http


@pytest.fixture
def fast_retry(monkeypatch):
    # Testi yavaşlatan throttle/backoff beklemelerini sıfırla.
    monkeypatch.setattr(http, "MIN_INTERVAL", 0.0)
    monkeypatch.setattr(http, "BACKOFF_BASE", 0.0)
    http._client = None
    http._semaphore = None
    http._rate_lock = None


def _install(handler) -> None:
    http._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    http._semaphore = None
    http._rate_lock = None


async def test_get_retries_transient_500(fast_retry):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(500 if calls["n"] == 1 else 200, text="ok")

    _install(handler)
    resp = await http.get("https://dergipark.org.tr/api/public/oai/")
    assert resp.status_code == 200
    assert calls["n"] == 2  # ilk 500 yeniden denendi


async def test_get_gives_up_after_persistent_5xx(fast_retry, monkeypatch):
    monkeypatch.setattr(http, "MAX_RETRIES", 2)
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503, text="down")

    _install(handler)
    with pytest.raises(httpx.HTTPStatusError):
        await http.get("https://dergipark.org.tr/api/public/oai/")
    assert calls["n"] == 3  # 1 ilk deneme + 2 retry, sonra pes


async def test_get_does_not_retry_404(fast_retry):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(404, text="nope")

    _install(handler)
    with pytest.raises(httpx.HTTPStatusError):
        await http.get("https://dergipark.org.tr/api/public/oai/")
    assert calls["n"] == 1  # 4xx (404) yeniden DENENMEZ
