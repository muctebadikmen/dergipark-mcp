"""Paylaşılan, nazik (rate-limited + retry'li) async HTTP istemcisi.

DergiPark art arda gelen isteklerde HTTP 429 döndürür. Bu modül:
  * istekler arasında en az ``MIN_INTERVAL`` saniye boşluk bırakır,
  * eşzamanlılığı ``MAX_CONCURRENCY`` ile sınırlar,
  * 429 ve geçici 5xx (500/502/503/504) durumunda ``Retry-After`` başlığına ve
    üstel geri çekilmeye (backoff) saygı göstererek yeniden dener.

Bu davranış hem teknik dayanıklılık hem de sunucuya saygılı (etik) kullanım içindir.
"""

from __future__ import annotations

import asyncio
import os
import time

import httpx

from . import __version__

USER_AGENT = (
    f"dergipark-mcp/{__version__} "
    "(+https://github.com/muctebadikmen/dergipark-mcp; "
    "OAI-PMH harvester; respects robots.txt)"
)


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ[name])
    except (KeyError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ[name])
    except (KeyError, ValueError):
        return default


# Nazik kullanım parametreleri — ortam değişkeniyle override edilebilir.
#
# DergiPark'ın ölçülen tavanı ~5-6 istek/yuvarlanan saniye ve **Retry-After
# göndermez** (429 = statik nginx HTML). Bu yüzden varsayılan olarak eşzamanlılığı
# 1'e, istek aralığını ~1 sn'ye çekeriz: hem dayanıklı hem de siteye saygılı.
MIN_INTERVAL = _env_float("DERGIPARK_MIN_INTERVAL", 1.0)   # saniye: istekler arası min boşluk
MAX_CONCURRENCY = _env_int("DERGIPARK_MAX_CONCURRENCY", 1)  # aynı anda en fazla istek
MAX_RETRIES = _env_int("DERGIPARK_MAX_RETRIES", 4)         # 429/503 için yeniden deneme sayısı
BACKOFF_BASE = _env_float("DERGIPARK_BACKOFF_BASE", 2.0)   # saniye: üstel backoff tabanı
DEFAULT_TIMEOUT = _env_float("DERGIPARK_TIMEOUT", 60.0)    # saniye

# DergiPark'ın OAI ucu ara sıra geçici 500 döndürür (gözlemlendi); GET'ler salt-okunur
# ve idempotent olduğundan 5xx'i yeniden denemek güvenli ve dayanıklılık için gerekli.
_RETRY_STATUS = {429, 500, 502, 503, 504}

_client: httpx.AsyncClient | None = None
_semaphore: asyncio.Semaphore | None = None
_rate_lock: asyncio.Lock | None = None
_last_request_ts: float = 0.0


def _ensure() -> tuple[httpx.AsyncClient, asyncio.Semaphore, asyncio.Lock]:
    global _client, _semaphore, _rate_lock
    if _client is None:
        _client = httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate"},
            timeout=DEFAULT_TIMEOUT,
            follow_redirects=True,
        )
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(MAX_CONCURRENCY)
    if _rate_lock is None:
        _rate_lock = asyncio.Lock()
    return _client, _semaphore, _rate_lock


async def _throttle() -> None:
    """İstek başlangıçları arasında MIN_INTERVAL boşluk garantisi."""
    global _last_request_ts
    _, _, rate_lock = _ensure()
    async with rate_lock:
        now = time.monotonic()
        wait = MIN_INTERVAL - (now - _last_request_ts)
        if wait > 0:
            await asyncio.sleep(wait)
        _last_request_ts = time.monotonic()


def _retry_after_seconds(resp: httpx.Response, attempt: int) -> float:
    header = resp.headers.get("Retry-After")
    if header:
        try:
            return float(header)
        except ValueError:
            pass
    return BACKOFF_BASE * (2 ** attempt)


async def get(url: str, params: dict | None = None) -> httpx.Response:
    """Nazik GET: throttle + eşzamanlılık sınırı + 429/5xx retry.

    Başarılı (2xx) yanıtı döndürür; kalıcı hata durumunda
    ``httpx.HTTPStatusError`` yükseltir.
    """
    client, sem, _ = _ensure()
    last_exc: Exception | None = None

    async with sem:
        for attempt in range(MAX_RETRIES + 1):
            await _throttle()
            try:
                resp = await client.get(url, params=params)
            except (httpx.TransportError, httpx.TimeoutException) as exc:
                last_exc = exc
                if attempt >= MAX_RETRIES:
                    raise
                await asyncio.sleep(BACKOFF_BASE * (2 ** attempt))
                continue

            if resp.status_code in _RETRY_STATUS and attempt < MAX_RETRIES:
                await asyncio.sleep(_retry_after_seconds(resp, attempt))
                continue

            resp.raise_for_status()
            return resp

    if last_exc:
        raise last_exc
    raise RuntimeError(f"İstek başarısız: {url}")


async def get_bytes(url: str, params: dict | None = None) -> bytes:
    resp = await get(url, params=params)
    return resp.content


async def get_text(url: str, params: dict | None = None) -> str:
    resp = await get(url, params=params)
    return resp.text


async def aclose() -> None:
    """İstemciyi kapatır ve loop'a bağlı durumu sıfırlar.

    Semaphore/lock sıfırlanır ki (test'lerde) farklı bir event loop'ta yeniden
    yaratılabilsinler; aksi halde 'bound to a different event loop' hatası olur.
    """
    global _client, _semaphore, _rate_lock, _last_request_ts
    if _client is not None:
        try:
            await _client.aclose()
        except RuntimeError:
            # Farklı/kapalı bir event loop'ta yaratılmış olabilir (test izolasyonu) —
            # bağlantılar süreç sonunda zaten serbest kalır.
            pass
        _client = None
    _semaphore = None
    _rate_lock = None
    _last_request_ts = 0.0
