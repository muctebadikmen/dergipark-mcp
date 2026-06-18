"""Makale sayfası (HTML) ve atıf dosyası erişimi.

Robots.txt'e uyumlu: yalnızca /pub/.../article/... (makale sayfası) ve
/download/... (PDF + atıf dosyası) yollarını kullanır. /search KULLANILMAZ.

Doğrulanan davranışlar (canlı):
  * Makale sayfasında CAPTCHA/Cloudflare YOK (HTTP 200).
  * PDF linki Google Scholar meta etiketinde: <meta name="citation_pdf_url" ...>
  * Referanslar: <meta name="citation_reference" ...> ve #sec-references bölümü.
  * BibTeX: /<lang>/download/article-cite-file/<id>/type/2
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup

from . import BASE_URL, http
from .cache import default_cache
from .oai import normalize_keyword

_PAGE_TTL = 24 * 3600


@dataclass
class ArticlePage:
    url: str
    pdf_url: str | None = None
    references: list[str] = field(default_factory=list)
    citation_meta: dict = field(default_factory=dict)


def _absolute(href: str) -> str:
    if href.startswith("http"):
        return href
    return f"{BASE_URL}{href if href.startswith('/') else '/' + href}"


def parse_article_html(html: str, url: str) -> ArticlePage:
    soup = BeautifulSoup(html, "html.parser")

    # Highwire/Google Scholar citation_* meta etiketleri
    citation_meta: dict[str, list[str]] = {}
    for meta in soup.find_all("meta"):
        name = meta.get("name", "")
        if name.startswith("citation_"):
            content = (meta.get("content") or "").strip()
            if content:
                citation_meta.setdefault(name, []).append(content)

    # PDF linki: önce citation_pdf_url, sonra <a href=download/article-file>
    pdf_url = None
    if citation_meta.get("citation_pdf_url"):
        pdf_url = _absolute(citation_meta["citation_pdf_url"][0])
    else:
        a = soup.find("a", href=re.compile(r"/download/article-file/\d+"))
        if a:
            pdf_url = _absolute(a["href"])

    # Referanslar: önce citation_reference meta etiketleri
    references: list[str] = []
    for ref in citation_meta.get("citation_reference", []):
        if ref and ref != "-":
            references.append(ref)

    # Yedek: #sec-references bölümündeki .citation-text düğümleri
    if not references:
        sec = soup.find(id="sec-references")
        container = sec.find_parent() if sec else None
        scope = container or soup
        for node in scope.select(".citation-text"):
            txt = node.get_text(" ", strip=True)
            if txt and txt != "-":
                references.append(txt)

    # citation_meta'yı sadeleştir (tek değerliler düz string)
    flat = {k: (v[0] if len(v) == 1 else v) for k, v in citation_meta.items()}

    return ArticlePage(
        url=url,
        pdf_url=pdf_url,
        references=references,
        citation_meta=flat,
    )


def _as_list(value) -> list[str]:
    """citation_meta değeri tek (str) ya da çoklu (list) olabilir → her zaman liste."""
    if value is None:
        return []
    if isinstance(value, list):
        return [v for v in value if v and v != "-"]
    return [value] if value != "-" else []


def _first(value) -> str | None:
    items = _as_list(value)
    return items[0] if items else None


def citation_authors(meta: dict) -> list[dict]:
    """``citation_author`` + paralel ``citation_author_institution``/``_orcid`` dizilerini
    sıraya göre eşleştirir → ``[{name, affiliation, orcid}]``.

    DergiPark bu üç meta'yı çoğunlukla aynı sırada yayınlar; ANCAK bir yazarın
    afiliasyonu/ORCID'i yoksa o meta etiketi atlanabilir → diziler kısalır ve
    indeks kayar. YANLIŞ atfı önlemek için: bir yan dizi yazar sayısıyla TAM
    eşleşmiyorsa o alanı hiç eşleştirmeyiz (None bırakırız). Doğruluk > eksiksizlik.
    """
    names = _as_list(meta.get("citation_author"))
    insts = _as_list(meta.get("citation_author_institution"))
    orcids = _as_list(meta.get("citation_author_orcid"))
    n = len(names)
    insts_aligned = insts if len(insts) == n else None
    orcids_aligned = orcids if len(orcids) == n else None
    out: list[dict] = []
    for i, name in enumerate(names):
        out.append({
            "name": name,
            "affiliation": insts_aligned[i] if insts_aligned else None,
            "orcid": orcids_aligned[i] if orcids_aligned else None,
        })
    return out


def citation_bibliographic(meta: dict) -> dict:
    """Makale HTML'inden yapısal bibliyografik alanlar (citation_* meta)."""
    raw_doi = _first(meta.get("citation_doi"))
    doi = None
    if raw_doi:
        doi = raw_doi.replace("https://doi.org/", "").replace("http://doi.org/", "").strip()
    kw_raw = _first(meta.get("citation_keywords")) or ""
    # Anahtar kelimeler ";" (bazen ",") ile ayrılır. Bazı kayıtlar baştaki segmente
    # "Anahtar Kelimeler:" etiketini/başıboş ":" sızdırır; normalize_keyword temizler.
    keywords = [k for k in (normalize_keyword(p) for p in re.split(r"[;,]", kw_raw)) if k]
    return {
        "title": _first(meta.get("citation_title")),
        "journal": _first(meta.get("citation_journal_title")),
        "issn": _first(meta.get("citation_issn")),
        "volume": _first(meta.get("citation_volume")),
        "issue": _first(meta.get("citation_issue")),
        "first_page": _first(meta.get("citation_firstpage")),
        "last_page": _first(meta.get("citation_lastpage")),
        "doi": doi,
        "date": _first(meta.get("citation_publication_date")) or _first(meta.get("citation_date")),
        "article_type": _first(meta.get("citation_article_type")),
        "keywords": keywords,
        "language": _first(meta.get("citation_language")),
        "publisher": _first(meta.get("citation_publisher")),
    }


# Dergi "Indexes/Dizinler/Abstracting & Indexing" bölümünü tanıyan başlıklar.
_INDEX_HEADINGS = {
    "indexes", "index", "indexing", "dizinler", "dizin",
    "abstracting & indexing", "abstracting and indexing",
}
# Metin-temelli kartlarda (anchor yoksa) tanınacak bilinen index adları.
_KNOWN_INDEXES = [
    "TR Dizin", "TR-Dizin", "ULAKBİM", "ULAKBIM", "TÜBİTAK-Ulakbim",
    "DOAJ", "Scopus", "Web of Science", "EBSCO", "EBSCOhost", "SOBIAD",
    "Index Copernicus", "ERIC", "Crossref", "CrossRef", "Scilit", "ProQuest",
    "Google Scholar", "MIAR", "ASOS", "ROAD", "Sherpa",
]


def parse_journal_indexes(html: str) -> dict:
    """Dergi landing sayfasından index/dizin bilgisini çıkarır (en iyi çaba).

    Döndürür: ``{"indexes": [adlar], "tr_dizin": bool}``. TR Dizin bayrağı, DergiPark'ın
    resmî "Indexes/Dizinler" bölümünden gelir (terfide TR-Dizin üyeliği sayılır).
    """
    soup = BeautifulSoup(html, "html.parser")
    names: list[str] = []
    seen: set[str] = set()

    def _add(name: str) -> None:
        name = name.strip()
        if not name or len(name) > 40:
            return
        key = name.lower().replace("-", " ").replace("ı", "i")
        if key in seen or name.lower() in _INDEX_HEADINGS:
            return
        seen.add(key)
        names.append(name)

    for h in soup.find_all(["h2", "h3", "h4", "h5"]):
        htxt = h.get_text(" ", strip=True)
        if htxt.lower() not in _INDEX_HEADINGS:
            continue
        # Başlıktan sonra index adlarını içeren dar kart gövdesini bul.
        node = h
        for _ in range(6):
            node = node.find_parent()
            if node is None:
                break
            full = node.get_text(" ", strip=True)
            after = full.split(htxt, 1)[-1].strip()
            if after and len(after) <= 300:
                # (a) anchor metinleri
                for a in node.find_all("a"):
                    _add(a.get_text(" ", strip=True))
                # (b) anchor yoksa: bilinen index adlarını metinde ara
                for known in _KNOWN_INDEXES:
                    if known.lower() in after.lower():
                        _add(known)
                break

    tr_dizin = any(
        n.lower().replace("-", " ").startswith("tr dizin") for n in names
    )
    return {"indexes": names, "tr_dizin": tr_dizin}


async def fetch_journal_indexes(slug: str) -> dict:
    """Dergi landing sayfasını çekip index bilgisini döndürür (önbellekli)."""
    url = f"{BASE_URL}/en/pub/{slug}"
    try:
        html = await default_cache.get_or_compute(
            f"journalpage:{slug}", lambda: http.get_text(url), ttl=_PAGE_TTL
        )
    except Exception:
        return {"indexes": [], "tr_dizin": False}
    return parse_journal_indexes(html)


async def fetch_article_page(url: str) -> ArticlePage:
    html = await default_cache.get_or_compute(
        f"page:{url}", lambda: http.get_text(url), ttl=_PAGE_TTL
    )
    return parse_article_html(html, url)


async def fetch_bibtex(numeric_id: str | int, lang: str = "en") -> str | None:
    """Makalenin BibTeX atıfını getirir (type/2). DergiPark'ın kendi ürettiği BibTeX."""
    url = f"{BASE_URL}/{lang}/download/article-cite-file/{numeric_id}/type/2"
    try:
        text = await default_cache.get_or_compute(
            f"bibtex:{lang}:{numeric_id}", lambda: http.get_text(url), ttl=_PAGE_TTL
        )
    except Exception:
        return None
    text = (text or "").strip()
    if text.startswith("@"):
        return text
    return None
