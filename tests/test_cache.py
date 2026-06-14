"""Önbellek (bellek + disk) — offline testler."""

import time

import pytest

from dergipark_mcp import cache as cmod
from dergipark_mcp.cache import Cache


def test_memory_set_get():
    c = Cache(disk_enabled=False)
    c.set("k", {"a": 1})
    assert c.get("k") == {"a": 1}


def test_miss_returns_sentinel():
    c = Cache(disk_enabled=False)
    assert c.get("yok") is cmod._MISSING


def test_ttl_expiry():
    c = Cache(disk_enabled=False)
    c.set("k", "v", ttl=0.05)
    assert c.get("k") == "v"
    time.sleep(0.07)
    assert c.get("k") is cmod._MISSING


def test_lru_eviction():
    c = Cache(memory_maxsize=3, disk_enabled=False)
    for i in range(5):
        c.set(f"k{i}", i)
    # En eski iki giriş düşmeli (k0, k1)
    assert c.get("k0") is cmod._MISSING
    assert c.get("k1") is cmod._MISSING
    assert c.get("k4") == 4


async def test_get_or_compute_dedup():
    c = Cache(disk_enabled=False)
    calls = {"n": 0}

    async def factory():
        calls["n"] += 1
        return 42

    a = await c.get_or_compute("k", factory)
    b = await c.get_or_compute("k", factory)
    assert a == b == 42
    assert calls["n"] == 1  # ikinci çağrı önbellekten


async def test_get_or_compute_does_not_cache_errors():
    c = Cache(disk_enabled=False)

    async def boom():
        raise ValueError("patladı")

    with pytest.raises(ValueError):
        await c.get_or_compute("k", boom)
    # Hata önbelleğe yazılmamış olmalı → tekrar dene mümkün
    assert c.get("k") is cmod._MISSING


def test_disk_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("DERGIPARK_CACHE_DIR", str(tmp_path))
    c1 = Cache(disk_enabled=True)
    c1.set("k", {"x": [1, 2, 3]}, ttl=3600)
    # Yeni bir Cache örneği (boş bellek) diskten okumalı
    c2 = Cache(disk_enabled=True)
    assert c2.get("k") == {"x": [1, 2, 3]}


def test_disk_skips_unserializable(tmp_path, monkeypatch):
    monkeypatch.setenv("DERGIPARK_CACHE_DIR", str(tmp_path))
    c = Cache(disk_enabled=True)
    # JSON'lanamayan değer bellek katmanında çalışır, diske yazılmaz (patlamaz)
    obj = object()
    c.set("k", obj)
    assert c.get("k") is obj
