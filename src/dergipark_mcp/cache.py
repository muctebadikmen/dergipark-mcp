"""Çok katmanlı önbellek: bellek (LRU + TTL) + opsiyonel disk (SQLite).

DergiPark'a yapılan istekler nazik (1 req/s) olduğundan, tekrarlı erişimleri
önbelleğe almak hem hızı hem de siteye saygıyı artırır. İki katman:

  * **Bellek** (her zaman açık): ``OrderedDict`` tabanlı LRU + giriş başına TTL.
  * **Disk** (opsiyonel, env ile açılır): ``DERGIPARK_ENABLE_DISK_CACHE=1`` ise
    ``platformdirs.user_cache_dir("dergipark-mcp")/cache.db`` altında SQLite.
    Değerler JSON olarak saklanır → süreçler arası kalıcı, taşınabilir.

Değerlerin JSON-serileştirilebilir (dict/list/str/sayı) olması beklenir; aksi
halde disk yazımı sessizce atlanır (bellek katmanı yine çalışır).
"""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any, Awaitable, Callable

import platformdirs

# Disk şeması sürümü — uyumsuz değişikliklerde artırılır (eski db yok sayılır).
_SCHEMA_VERSION = "v1"
_MISSING = object()


def _disk_enabled_default() -> bool:
    return os.environ.get("DERGIPARK_ENABLE_DISK_CACHE", "").strip().lower() in {
        "1", "true", "yes", "on",
    }


def cache_dir() -> Path:
    """Disk önbelleğinin yaşadığı dizin (env ``DERGIPARK_CACHE_DIR`` ile override)."""
    override = os.environ.get("DERGIPARK_CACHE_DIR")
    base = Path(override) if override else Path(platformdirs.user_cache_dir("dergipark-mcp"))
    return base


class Cache:
    """Bellek-LRU + opsiyonel disk önbelleği.

    Thread/async-güvenli değildir; tek event-loop kullanımı için tasarlanmıştır.
    ``get_or_compute`` çağrıları için key-bazlı kilit, aynı anahtarın eşzamanlı
    iki kez hesaplanmasını (thundering herd) engeller.
    """

    def __init__(
        self,
        *,
        memory_maxsize: int = 512,
        default_ttl: float = 3600.0,
        disk_enabled: bool | None = None,
        namespace: str = _SCHEMA_VERSION,
    ) -> None:
        self.memory_maxsize = memory_maxsize
        self.default_ttl = default_ttl
        self.namespace = namespace
        self._disk_enabled = _disk_enabled_default() if disk_enabled is None else disk_enabled
        self._mem: "OrderedDict[str, tuple[float, Any]]" = OrderedDict()
        self._locks: dict[str, asyncio.Lock] = {}
        self._db: sqlite3.Connection | None = None
        self._db_failed = False

    # ----------------------------------------------------------------- disk --
    def _ensure_db(self) -> sqlite3.Connection | None:
        if not self._disk_enabled or self._db_failed:
            return None
        if self._db is not None:
            return self._db
        try:
            d = cache_dir()
            d.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(d / "cache.db"))
            conn.execute(
                "CREATE TABLE IF NOT EXISTS cache "
                "(key TEXT PRIMARY KEY, expiry REAL, value TEXT)"
            )
            conn.commit()
            self._db = conn
            return conn
        except Exception:
            # Disk yazılamıyorsa (izin/path) sessizce bellek-only'a düş.
            self._db_failed = True
            return None

    def _disk_get(self, key: str) -> Any:
        conn = self._ensure_db()
        if conn is None:
            return _MISSING
        try:
            row = conn.execute(
                "SELECT expiry, value FROM cache WHERE key = ?", (key,)
            ).fetchone()
        except Exception:
            return _MISSING
        if row is None:
            return _MISSING
        expiry, value = row
        if expiry is not None and expiry < time.time():
            try:
                conn.execute("DELETE FROM cache WHERE key = ?", (key,))
                conn.commit()
            except Exception:
                pass
            return _MISSING
        try:
            return json.loads(value)
        except Exception:
            return _MISSING

    def _disk_set(self, key: str, value: Any, expiry: float) -> None:
        conn = self._ensure_db()
        if conn is None:
            return
        try:
            payload = json.dumps(value, ensure_ascii=False)
        except (TypeError, ValueError):
            return  # JSON'lanamayan değer → diske yazma
        try:
            conn.execute(
                "INSERT OR REPLACE INTO cache (key, expiry, value) VALUES (?, ?, ?)",
                (key, expiry, payload),
            )
            conn.commit()
        except Exception:
            pass

    # --------------------------------------------------------------- memory --
    def _ns(self, key: str) -> str:
        return f"{self.namespace}:{key}"

    def get(self, key: str) -> Any:
        """Önbellekten getir; yoksa ``_MISSING`` (modül sabiti) döner."""
        k = self._ns(key)
        item = self._mem.get(k)
        now = time.time()
        if item is not None:
            expiry, value = item
            if expiry is None or expiry >= now:
                self._mem.move_to_end(k)
                return value
            del self._mem[k]
        # Bellekte yok → disk
        disk_val = self._disk_get(k)
        if disk_val is not _MISSING:
            self._mem[k] = (now + self.default_ttl, disk_val)
            self._mem.move_to_end(k)
            self._evict()
            return disk_val
        return _MISSING

    def set(self, key: str, value: Any, ttl: float | None = None) -> None:
        k = self._ns(key)
        ttl = self.default_ttl if ttl is None else ttl
        expiry = time.time() + ttl if ttl and ttl > 0 else None
        self._mem[k] = (expiry, value)
        self._mem.move_to_end(k)
        self._evict()
        self._disk_set(k, value, expiry if expiry is not None else time.time() + 10 * 365 * 86400)

    def _evict(self) -> None:
        while len(self._mem) > self.memory_maxsize:
            self._mem.popitem(last=False)

    def clear(self) -> None:
        self._mem.clear()
        conn = self._ensure_db()
        if conn is not None:
            try:
                conn.execute("DELETE FROM cache")
                conn.commit()
            except Exception:
                pass

    # ---------------------------------------------------------------- async --
    async def get_or_compute(
        self,
        key: str,
        factory: Callable[[], Awaitable[Any]],
        ttl: float | None = None,
    ) -> Any:
        """Önbellekte varsa döndür; yoksa ``factory()`` (async) ile hesapla ve sakla.

        Aynı anahtar için eşzamanlı iki hesaplama olmaması adına key-bazlı kilit kullanır.
        """
        hit = self.get(key)
        if hit is not _MISSING:
            return hit
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            hit = self.get(key)  # kilidi beklerken başkası doldurmuş olabilir
            if hit is not _MISSING:
                return hit
            value = await factory()
            self.set(key, value, ttl=ttl)
            return value
        # not: kilidi bilinçli olarak _locks'tan temizlemiyoruz; sayısı sınırlı kalır.


# Modül seviyesi varsayılan önbellek (uygulama genelinde paylaşılır).
default_cache = Cache()
