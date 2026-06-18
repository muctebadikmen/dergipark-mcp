"""Tam dergi dizini — DergiPark'ın ~2.550 dergisini keşfet.

OAI ListSets yalnızca ~100 dergi verir (resumptionToken yok). Tam dizin
sunucu-render HTML keşif sayfalarındadır:
``https://dergipark.org.tr/en/pub/explore/journals?page=N`` — her sayfada ~100
dergi kartı (ad, yayıncı, konu etiketleri), **robots-serbest**.

Strateji:
  * **Gömülü statik JSON** (``data/journals.json``, build script'iyle üretilir)
    → anında, ağsız tam dizin.
  * **Canlı yedek/yenileme**: gömülü veri yoksa ya da ``refresh=True`` ise sayfalar
    nazikçe (1 req/s) gezilir ve önbelleğe alınır.

Konu taksonomisi dizinin kendisindeki konu etiketlerinden türetilir
(``/en/pub/subjects`` yalnızca robots-yasaklı /search'e link verdiği için kullanılmaz).
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from dataclasses import dataclass, field
from importlib.resources import files

from bs4 import BeautifulSoup

from . import BASE_URL, http
from .cache import _MISSING, default_cache

DIRECTORY_URL = f"{BASE_URL}/en/pub/explore/journals"

# Stale-while-revalidate ayarları:
#   - Liste her zaman ANINDA döner (gömülü ya da önbellekteki tazelenmiş sürüm).
#   - Bayatladıysa (TTL aşıldıysa) arka planda BİR kez canlı tazeleme tetiklenir;
#     mevcut çağrı beklemez. Böylece yeni dergiler otomatik gelir, DergiPark
#     günde ≤1 kez yüklenir (her çağrıda DEĞİL).
_REFRESH_TTL = float(os.environ.get("DERGIPARK_DIRECTORY_TTL", 24 * 3600))  # 1 gün
_PERSIST_TTL = 30 * 24 * 3600  # tazelenmiş liste önbellekte bu kadar yaşar
_CACHE_KEY = "directory:all"
_TS_KEY = "directory:refreshed_at"

_refresh_in_flight = False


def _auto_refresh_enabled() -> bool:
    return os.environ.get("DERGIPARK_DIRECTORY_REFRESH", "1").strip().lower() in {
        "1", "true", "yes", "on",
    }


# Keşif sayfasındaki /en/pub/<x> linklerinden dergi OLMAYANLAR.
_NAV_SLUGS = {"subjects", "trends", "announcement", "explore", "journals", "search"}


@dataclass
class JournalEntry:
    slug: str
    name: str
    publisher: str | None = None
    subjects: list[str] = field(default_factory=list)

    def to_dict(self, max_subjects: int | None = None) -> dict:
        """``max_subjects`` verilirse konu listesi ilk N ile kısaltılır (liste
        görünümünde token tasarrufu). Varsayılan ``None`` tam listeyi korur —
        journals.json/cache serileştirmesi bundan etkilenmez."""
        d: dict = {"slug": self.slug, "name": self.name}
        if self.publisher:
            d["publisher"] = self.publisher
        if self.subjects:
            d["subjects"] = (
                self.subjects if max_subjects is None else self.subjects[:max_subjects]
            )
        return d


# --------------------------------------------------------------------------- #
# Ayrıştırma
# --------------------------------------------------------------------------- #

def parse_directory_page(html: str) -> list[JournalEntry]:
    """Bir keşif sayfasının HTML'inden dergi kartlarını çıkarır.

    Kart yapısı (doğrulandı):
        <td> <h5><a href="/en/pub/<slug>">Ad</a></h5>
             <h6>Yayıncı</h6>
             <div class="journal-subjects"><span class="badge">Konu</span>…</div> </td>
    """
    soup = BeautifulSoup(html, "html.parser")
    out: list[JournalEntry] = []
    seen: set[str] = set()
    for a in soup.select('h5 > a[href^="/en/pub/"]'):
        href = a.get("href", "")
        m = re.match(r"^/en/pub/([A-Za-z0-9\-]+)/?$", href)
        if not m:
            continue
        slug = m.group(1)
        if slug in _NAV_SLUGS or slug in seen:
            continue
        name = a.get_text(" ", strip=True)
        if not name:
            continue
        td = a.find_parent("td")
        publisher = None
        subjects: list[str] = []
        if td is not None:
            h6 = td.find("h6")
            if h6 is not None:
                publisher = (h6.get_text(" ", strip=True) or None)
            for span in td.select("div.journal-subjects span.badge"):
                t = span.get_text(" ", strip=True)
                if t:
                    subjects.append(t)
        seen.add(slug)
        out.append(JournalEntry(slug=slug, name=name, publisher=publisher, subjects=subjects))
    return out


# --------------------------------------------------------------------------- #
# Canlı harvest
# --------------------------------------------------------------------------- #

async def harvest_directory(max_pages: int = 60, ctx=None) -> list[JournalEntry]:
    """Tüm keşif sayfalarını nazikçe gezerek tam dizini toplar.

    Yeni slug eklemeyen bir sayfaya gelince durur (boş sayfa ya da sitenin son
    sayfaya sabitlenmesi). ``max_pages`` güvenlik tavanıdır.
    """
    entries: list[JournalEntry] = []
    seen: set[str] = set()
    for page in range(1, max_pages + 1):
        html = await http.get_text(DIRECTORY_URL, params={"page": str(page)})
        page_entries = parse_directory_page(html)
        new = [e for e in page_entries if e.slug not in seen]
        if not new:
            break
        for e in new:
            seen.add(e.slug)
        entries.extend(new)
        if ctx is not None:
            await ctx.report_progress(progress=page, total=max_pages)
    return entries


# --------------------------------------------------------------------------- #
# Gömülü veri + erişim
# --------------------------------------------------------------------------- #

def _data_resource():
    return files("dergipark_mcp").joinpath("data", "journals.json")


_embedded_entries: list[JournalEntry] | None = None  # bir kez parse edilir, bellekte tutulur


def load_embedded() -> dict:
    """Pakete gömülü dizini yükler. Yoksa boş yapı döner."""
    try:
        text = _data_resource().read_text(encoding="utf-8")
        return json.loads(text)
    except (FileNotFoundError, ValueError, OSError):
        return {"generated_at": None, "count": 0, "journals": []}


def embedded_entries() -> list[JournalEntry]:
    """Gömülü dizini (parse edilmiş) döndürür — ilk çağrıda yüklenir, sonra bellekten."""
    global _embedded_entries
    if _embedded_entries is None:
        _embedded_entries = _entries_from_raw(load_embedded().get("journals", []))
    return _embedded_entries


def _entries_from_raw(raw: list[dict]) -> list[JournalEntry]:
    out: list[JournalEntry] = []
    for j in raw:
        if not j.get("slug") or not j.get("name"):
            continue
        out.append(
            JournalEntry(
                slug=j["slug"],
                name=j["name"],
                publisher=j.get("publisher"),
                subjects=list(j.get("subjects", [])),
            )
        )
    return out


def _served_entries() -> list[JournalEntry]:
    """ŞU AN sunulacak liste: önbellekte tazelenmiş sürüm varsa o, yoksa gömülü."""
    cached = default_cache.get(_CACHE_KEY)
    if cached is not _MISSING and cached:
        return _entries_from_raw(cached)
    return embedded_entries()


def _is_stale() -> bool:
    ts = default_cache.get(_TS_KEY)
    if ts is _MISSING or not ts:
        return True
    return (time.time() - float(ts)) >= _REFRESH_TTL


async def _refresh_now(ctx=None) -> list[JournalEntry]:
    """Canlı tam tarama yapar, önbelleğe (+ zaman damgası) yazar, listeyi döndürür."""
    ents = await harvest_directory(ctx=ctx)
    if ents:
        default_cache.set(_CACHE_KEY, [e.to_dict() for e in ents], ttl=_PERSIST_TTL)
        default_cache.set(_TS_KEY, time.time(), ttl=_PERSIST_TTL)
    return ents


async def _background_refresh() -> None:
    global _refresh_in_flight
    try:
        await _refresh_now()
    except Exception:
        pass  # tazeleme başarısızsa mevcut liste sunulmaya devam eder
    finally:
        _refresh_in_flight = False


def _maybe_spawn_refresh() -> None:
    """Bayatladıysa arka planda BİR tazeleme görevi başlatır (engellemez)."""
    global _refresh_in_flight
    if not _auto_refresh_enabled() or _refresh_in_flight or not _is_stale():
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    _refresh_in_flight = True
    loop.create_task(_background_refresh())


async def get_directory(refresh: bool = False, ctx=None) -> list[JournalEntry]:
    """Tam dizini döndürür (stale-while-revalidate).

    Her zaman ANINDA döner: önbellekte tazelenmiş sürüm varsa onu, yoksa pakete
    gömülü statik JSON'u. Liste bayatladıysa (``DERGIPARK_DIRECTORY_TTL``, vars. 1 gün)
    arka planda BİR canlı tazeleme tetiklenir — bu çağrı beklemez, sonraki çağrılar
    güncel listeyi alır. ``refresh=True`` ise hemen (engelleyerek) canlı tazeler.
    Otomatik tazeleme ``DERGIPARK_DIRECTORY_REFRESH=0`` ile kapatılabilir.
    """
    if refresh:
        ents = await _refresh_now(ctx=ctx)
        return ents or _served_entries()
    ents = _served_entries()
    _maybe_spawn_refresh()
    return ents


# --------------------------------------------------------------------------- #
# Filtreleme / arama
# --------------------------------------------------------------------------- #

def _fold(s: str) -> str:
    """Türkçe-duyarlı basit katlama (arama eşleştirmesi için)."""
    s = s.casefold()
    return (
        s.replace("ı", "i").replace("İ".casefold(), "i")
        .replace("ş", "s").replace("ğ", "g")
        .replace("ü", "u").replace("ö", "o").replace("ç", "c")
    )


def filter_journals(
    entries: list[JournalEntry],
    query: str | None = None,
    subject: str | None = None,
) -> list[JournalEntry]:
    """Ad/slug (query) ve konu (subject) filtreleri. İkisi de büyük/küçük + Türkçe duyarsız."""
    out = entries
    if query:
        q = _fold(query)
        out = [e for e in out if q in _fold(e.name) or q in _fold(e.slug)]
    if subject:
        s = _fold(subject)
        out = [e for e in out if any(s in _fold(sub) for sub in e.subjects)]
    return out


def subject_counts(entries: list[JournalEntry]) -> dict[str, int]:
    """Konu → o konuya sahip dergi sayısı (azalan)."""
    counts: dict[str, int] = {}
    for e in entries:
        for sub in e.subjects:
            counts[sub] = counts.get(sub, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))
