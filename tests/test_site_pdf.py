"""Makale sayfası ayrıştırma ve PDF metin normalizasyonu — offline."""

from dergipark_mcp import site, pdf
from conftest import read_fixture


def test_article_html_pdf_link_and_meta():
    page = site.parse_article_html(
        read_fixture("article.html"),
        "https://dergipark.org.tr/en/pub/mulkiye/article/1000",
    )
    # citation_pdf_url meta etiketinden mutlak PDF linki
    assert page.pdf_url == "https://dergipark.org.tr/en/download/article-file/857"
    assert page.citation_meta.get("citation_journal_title") == "Mülkiye Dergisi"
    assert page.citation_meta.get("citation_issn") == "1305-9971"


def test_references_fallback_when_meta_dash():
    # Fixture'da citation_reference = "-" (referans yok) -> liste boş kalmalı,
    # patlamamalı.
    page = site.parse_article_html(
        read_fixture("article.html"),
        "https://dergipark.org.tr/en/pub/mulkiye/article/1000",
    )
    assert isinstance(page.references, list)
    assert "-" not in page.references


def test_synthetic_references_meta():
    html = """
    <html><head>
    <meta name="citation_reference" content="Yazar A. (2020). Başlık. Dergi 1(1)." />
    <meta name="citation_reference" content="Yazar B. (2021). İkinci. Dergi 2(2)." />
    <meta name="citation_reference" content="-" />
    <meta name="citation_pdf_url" content="/tr/download/article-file/99" />
    </head><body></body></html>
    """
    page = site.parse_article_html(html, "http://x/article/1")
    assert len(page.references) == 2
    assert page.references[0].startswith("Yazar A.")
    assert page.pdf_url == "https://dergipark.org.tr/tr/download/article-file/99"


def test_pdf_normalize_dehyphenation():
    raw = "bu bir cüm-\nle ve devamı\n\n\n\nyeni paragraf"
    out = pdf._normalize(raw)
    assert "cümle" in out
    assert "\n\n\n" not in out


def test_readable_ratio_distinguishes_garbled():
    # Türkçe (ç/ğ/ı/ö/ş/ü dahil) beklenen harflerdir -> ~1.0
    clean = "Toplumun Siyaseti Mülkiye Dergisi çağdaş düşünce ağ ışık öz"
    # Gerçek bozuk-font çıktısı: harfler egzotik Latin-Extended glyph'lerine düşer
    garbled = "zŦůŵĂǌ dŽƉůƵŵƵŶ ^ŝǇĂƐĞƚŝ DĂŬĂůĞ ƂŶĚĞƌŝŵ ,ĂďĞƌŵĂƐ ƚĂƌƨƔŦŵ"
    assert pdf.readable_ratio(clean) > 0.95
    assert pdf.readable_ratio(garbled) < 0.50


def test_pdf_extract_minimal():
    # Metin içeren minimal, geçerli bir PDF (tek sayfa, "Hello DergiPark").
    minimal = _minimal_pdf_bytes()
    result = pdf.extract(minimal, "http://x/file/1")
    assert result.page_count == 1
    assert result.has_text
    assert "Hello DergiPark" in result.markdown


def _minimal_pdf_bytes() -> bytes:
    objs = []
    objs.append(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")
    objs.append(b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n")
    objs.append(
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>\nendobj\n"
    )
    stream = b"BT /F1 24 Tf 72 700 Td (Hello DergiPark) Tj ET"
    objs.append(
        b"4 0 obj\n<< /Length " + str(len(stream)).encode() + b" >>\nstream\n"
        + stream + b"\nendstream\nendobj\n"
    )
    objs.append(
        b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
    )
    header = b"%PDF-1.4\n"
    body = b""
    offsets = []
    pos = len(header)
    for o in objs:
        offsets.append(pos)
        body += o
        pos += len(o)
    xref_pos = len(header) + len(body)
    xref = b"xref\n0 6\n0000000000 65535 f \n"
    for off in offsets:
        xref += ("%010d 00000 n \n" % off).encode()
    trailer = (
        b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n"
        + str(xref_pos).encode()
        + b"\n%%EOF"
    )
    return header + body + xref + trailer
