"""DergiPark MCP sunucusu — FastMCP araç tanımları.

Tüm erişim OAI-PMH + açık makale sayfaları üzerinden yapılır:
robots.txt'e uyumludur, CAPTCHA gerektirmez, ücretli servis kullanmaz.
"""

from __future__ import annotations

import re

from fastmcp import FastMCP

from . import oai, pdf, site

mcp = FastMCP(
    name="dergipark-mcp",
    instructions=(
        "DergiPark (Türk akademik dergileri) için araçlar. "
        "Bir dergiye onun 'slug'u ile erişilir — slug, dergipark.org.tr URL'sindeki "
        "/pub/<slug>/ kısmıdır (örn. .../pub/mulkiye/ -> slug 'mulkiye'). "
        "Anahtar kelime araması bir dergi kapsamında çalışır (DergiPark genel arama "
        "API'si sunmaz). Önce list_journals ile dergiyi bulabilir, sonra o derginin "
        "içinde search_articles ile arayabilir, get_article ile metadata ve "
        "get_article_fulltext ile tam metni alabilirsiniz."
    ),
)


# --------------------------------------------------------------------------- #
# Girdi çözümleme
# --------------------------------------------------------------------------- #

def _resolve_id_and_url(article: str) -> tuple[str | None, str | None]:
    """Esnek girdi -> (numeric_id, article_page_url | None).

    Kabul edilen biçimler:
      * "1000"
      * "oai:dergipark.org.tr:article/1000"
      * "https://dergipark.org.tr/tr/pub/mulkiye/article/1000"
      * "mulkiye/1000"
    """
    article = article.strip()
    url = article if article.startswith("http") and "dergipark.org.tr" in article else None
    m = re.search(r"(?:article|record)/(\d+)", article)
    if m:
        return m.group(1), url
    if article.isdigit():
        return article, url
    # "slug/1000" gibi -> sondaki sayı
    m = re.search(r"(\d+)\s*$", article)
    if m:
        return m.group(1), url
    return None, url


# --------------------------------------------------------------------------- #
# Araçlar
# --------------------------------------------------------------------------- #

@mcp.tool
async def list_journals(query: str | None = None, limit: int = 50) -> dict:
    """DergiPark dergilerini listele/ara.

    NOT: Bu kısmi bir dizindir — DergiPark'ın OAI servisi yaklaşık 100 dergi
    döndürür (tam dizin programatik olarak verilmez). Herhangi bir dergiye yine de
    slug'ı ile (list_journal_articles / search_articles) erişebilirsiniz.

    Args:
        query: Dergi adında geçen metin (büyük/küçük harf duyarsız). Boşsa hepsi.
        limit: Döndürülecek en fazla dergi sayısı.
    """
    journals = await oai.list_journals()
    if query:
        q = query.casefold()
        journals = [j for j in journals if q in j.name.casefold() or q in j.slug.casefold()]
    journals = journals[:limit]
    return {
        "count": len(journals),
        "partial_directory": True,
        "note": (
            "Kısmi dizin (~100 dergi). Bir derginin slug'ını onun dergipark.org.tr "
            "URL'sindeki /pub/<slug>/ kısmından da alabilirsiniz."
        ),
        "journals": [{"slug": j.slug, "name": j.name} for j in journals],
    }


@mcp.tool
async def list_journal_articles(
    journal: str,
    from_date: str | None = None,
    until_date: str | None = None,
    limit: int = 25,
) -> dict:
    """Bir derginin makalelerini (en yeni harvest sırasına göre) listele.

    Args:
        journal: Dergi slug'ı (örn. "mulkiye"). dergipark.org.tr/.../pub/<slug>/.
        from_date: Bu tarihten itibaren (YYYY-MM-DD), opsiyonel.
        until_date: Bu tarihe kadar (YYYY-MM-DD), opsiyonel.
        limit: En fazla makale sayısı (sayfalar otomatik dolaşılır).
    """
    articles = await oai.list_records(
        journal, from_date=from_date, until_date=until_date, max_records=limit
    )
    if not articles:
        return {"journal": journal, "count": 0, "articles": [],
                "note": "Kayıt bulunamadı. Slug doğru mu? (Tarih filtresi varsa genişletin.)"}
    return {
        "journal": articles[0].journal or journal,
        "journal_slug": journal,
        "count": len(articles),
        "articles": [
            {
                "id": a.id,
                "title": a.title or a.title_en,
                "authors": a.authors,
                "date": a.date,
                "url": a.url,
            }
            for a in articles
        ],
    }


@mcp.tool
async def search_articles(
    query: str,
    journal: str,
    limit: int = 15,
    max_scan: int = 300,
) -> dict:
    """Bir dergi İÇİNDE anahtar kelimeyle makale ara.

    DergiPark genel (siteler arası) bir arama API'si sunmaz ve /search yolu
    robots.txt ile kapalıdır. Bu araç, belirtilen derginin metadata'sını OAI ile
    çekip yerel olarak (başlık + özet + yazar üzerinde) arar. Bu yüzden bir
    'journal' slug'ı zorunludur.

    Args:
        query: Aranacak kelimeler (boşlukla ayrılır; hepsi/çoğu eşleşenler öne gelir).
        journal: Dergi slug'ı (örn. "mulkiye").
        limit: Döndürülecek en fazla sonuç.
        max_scan: Taranacak en fazla makale (büyük dergilerde hız/derinlik dengesi).
    """
    articles = await oai.list_records(journal, max_records=max_scan)
    terms = [t for t in re.split(r"\s+", query.casefold()) if t]
    if not terms:
        return {"error": "Boş sorgu."}

    scored: list[tuple[int, oai.Article]] = []
    for a in articles:
        hay = " ".join(
            filter(None, [a.title, a.title_en, a.abstract, " ".join(a.authors), " ".join(a.subjects)])
        ).casefold()
        hits = sum(1 for t in terms if t in hay)
        if hits:
            scored.append((hits, a))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = [a for _, a in scored[:limit]]
    return {
        "query": query,
        "journal_slug": journal,
        "scanned": len(articles),
        "matched": len(scored),
        "results": [
            {
                "id": a.id,
                "title": a.title or a.title_en,
                "authors": a.authors,
                "date": a.date,
                "abstract": (a.abstract[:300] + "…") if a.abstract and len(a.abstract) > 300 else a.abstract,
                "url": a.url,
            }
            for a in top
        ],
        "note": (
            None if articles else
            "Dergi taranamadı — slug'ı doğrulayın."
        ),
    }


@mcp.tool
async def get_article(article: str, include_bibtex: bool = True) -> dict:
    """Tek bir makalenin tam metadata'sını getir (başlık, yazarlar, özet, tarih, dergi, kalıcı kimlik).

    Args:
        article: Makale kimliği — sayısal id ("1000"), tam URL
            ("https://dergipark.org.tr/tr/pub/mulkiye/article/1000"),
            "slug/1000" veya OAI identifier.
        include_bibtex: True ise BibTeX atıf dizesi de eklenir.
    """
    numeric, _ = _resolve_id_and_url(article)
    if not numeric:
        return {"error": f"Makale kimliği çözümlenemedi: {article!r}"}
    try:
        meta = await oai.get_record(numeric)
    except oai.OAIError as exc:
        return {"error": str(exc)}
    result = meta.to_dict()
    if include_bibtex:
        bib = await site.fetch_bibtex(numeric)
        if bib:
            result["bibtex"] = bib
    return result


@mcp.tool
async def get_article_fulltext(article: str, max_pages: int | None = None) -> dict:
    """Bir makalenin tam metnini (PDF) indirip Markdown'a çevirerek döndür.

    Robots-uyumlu: makale sayfasından citation_pdf_url alınır, PDF indirilir.
    Taranmış (görüntü) PDF'lerde metin boş dönebilir (bu sürümde OCR yok).

    Args:
        article: Makale kimliği (sayısal id, URL, "slug/id" veya OAI id).
        max_pages: Çıkarılacak en fazla sayfa (uzun belgelerde bağlamı sınırlamak için).
    """
    numeric, url = _resolve_id_and_url(article)
    if not numeric and not url:
        return {"error": f"Makale kimliği çözümlenemedi: {article!r}"}

    if not url:
        try:
            meta = await oai.get_record(numeric)
        except oai.OAIError as exc:
            return {"error": str(exc)}
        url = meta.url
        if not url:
            return {"error": "Makale sayfası URL'si bulunamadı."}

    page = await site.fetch_article_page(url)
    if not page.pdf_url:
        return {
            "article_url": url,
            "error": "Bu makalede indirilebilir PDF bulunamadı (yalnızca metadata mevcut olabilir).",
        }

    extracted = await pdf.download_and_extract(page.pdf_url, max_pages=max_pages)
    return {
        "article_url": url,
        "pdf_url": page.pdf_url,
        "page_count": extracted.page_count,
        "pages_extracted": len(extracted.pages),
        "has_text": extracted.has_text,
        "text_reliable": extracted.text_reliable,
        "note": extracted.note,
        "markdown": extracted.markdown,
    }


@mcp.tool
async def get_article_references(article: str) -> dict:
    """Bir makalenin kaynakça (referans) listesini çıkar.

    Önce makale sayfasındaki citation_reference meta etiketleri / #sec-references
    bölümü kullanılır; yoksa BibTeX atıfı yedek olarak döndürülür.

    Args:
        article: Makale kimliği (sayısal id, URL, "slug/id" veya OAI id).
    """
    numeric, url = _resolve_id_and_url(article)
    if not numeric and not url:
        return {"error": f"Makale kimliği çözümlenemedi: {article!r}"}

    if not url:
        try:
            meta = await oai.get_record(numeric)
        except oai.OAIError as exc:
            return {"error": str(exc)}
        url = meta.url
        if not url:
            return {"error": "Makale sayfası URL'si bulunamadı."}

    page = await site.fetch_article_page(url)
    result = {
        "article_url": url,
        "reference_count": len(page.references),
        "references": page.references,
    }
    if not page.references and numeric:
        bib = await site.fetch_bibtex(numeric)
        if bib:
            result["note"] = "Yapılandırılmış referans bulunamadı; makalenin kendi BibTeX atıfı döndürüldü."
            result["bibtex"] = bib
    return result


def main() -> None:
    """Konsol giriş noktası: stdio transport üzerinden çalışır (Claude Desktop uyumlu)."""
    mcp.run()


if __name__ == "__main__":
    main()
