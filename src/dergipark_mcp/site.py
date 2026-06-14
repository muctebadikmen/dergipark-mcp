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

from . import BASE_URL
from . import http


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


async def fetch_article_page(url: str) -> ArticlePage:
    html = await http.get_text(url)
    return parse_article_html(html, url)


async def fetch_bibtex(numeric_id: str | int, lang: str = "en") -> str | None:
    """Makalenin BibTeX atıfını getirir (type/2)."""
    url = f"{BASE_URL}/{lang}/download/article-cite-file/{numeric_id}/type/2"
    try:
        text = await http.get_text(url)
    except Exception:
        return None
    text = text.strip()
    if text.startswith("@"):
        return text
    return None
