"""Makale sayfası ayrıştırma ve PDF metin normalizasyonu — offline."""

from conftest import read_fixture

from dergipark_mcp import pdf, site


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


def test_citation_authors_parallel_arrays():
    page = site.parse_article_html(read_fixture("article_rich.html"), "http://x/article/1816398")
    authors = site.citation_authors(page.citation_meta)
    assert len(authors) == 2
    assert authors[0]["name"] == "Tunahan Karaarslan"
    assert authors[0]["affiliation"] == "İSTANBUL ESENYURT ÜNİVERSİTESİ"
    assert authors[0]["orcid"] == "0009-0003-5177-4073"
    assert authors[1]["orcid"] == "0000-0002-9638-025X"


def test_citation_bibliographic_fields():
    page = site.parse_article_html(read_fixture("article_rich.html"), "http://x")
    b = site.citation_bibliographic(page.citation_meta)
    assert b["journal"].startswith("İstanbul 29 Mayıs")
    assert b["volume"] == "1" and b["issue"] == "1"
    assert b["first_page"] == "1" and b["last_page"] == "12"
    assert b["issn"] == "3108-7434"
    assert b["date"] == "2026-01-30"
    assert any("Critical Thinking" in k for k in b["keywords"])


def test_rich_references_full_list():
    page = site.parse_article_html(read_fixture("article_rich.html"), "http://x")
    assert len(page.references) == 38  # canlı doğrulandı
    assert page.references[0].startswith("Abrami")
    assert "-" not in page.references


def test_citation_authors_no_misattribution_on_count_mismatch():
    # Bir yazarın afiliasyonu eksik → institutions dizisi kısa. YANLIŞ atıf OLMAMALI:
    # institutions yazar sayısıyla eşleşmediği için tüm afiliasyonlar None döner.
    meta = {
        "citation_author": ["A Yazar", "B Yazar"],
        "citation_author_institution": "Üniversite X",  # tek (eksik hizalama)
        "citation_author_orcid": ["0000-0000-0000-0001", "0000-0000-0000-0002"],
    }
    authors = site.citation_authors(meta)
    assert [a["name"] for a in authors] == ["A Yazar", "B Yazar"]
    assert all(a["affiliation"] is None for a in authors)  # misattribution yok
    # orcid sayısı eşleştiği için doğru hizalanır
    assert authors[0]["orcid"].endswith("0001")
    assert authors[1]["orcid"].endswith("0002")


def test_citation_author_single_string():
    page = site.parse_article_html(read_fixture("article.html"), "http://x")
    authors = site.citation_authors(page.citation_meta)
    assert len(authors) == 1
    assert authors[0]["name"] == "Fahri Bakırcı"


def test_parse_journal_indexes():
    idx = site.parse_journal_indexes(read_fixture("journal_page.html"))
    assert idx["tr_dizin"] is True
    low = [n.lower().replace("-", " ") for n in idx["indexes"]]
    assert any(n.startswith("tr dizin") for n in low)
    assert any("scilit" in n for n in low)
    assert any("sobiad" in n for n in low)
    # "Aim & Scope" bölümündeki "Scopus" kelimesi index sayılmamalı (kart-kapsamlı)
    assert not any("scopus" in n for n in low)


def test_parse_journal_indexes_none():
    idx = site.parse_journal_indexes("<html><body><p>index yok</p></body></html>")
    assert idx["tr_dizin"] is False
    assert idx["indexes"] == []


def test_split_sections_turkish_english():
    text = (
        "Makale başlığı ve yazarlar\n\n"
        "ÖZET\nBu çalışma eleştirel düşünmeyi inceler.\n\n"
        "GİRİŞ\nGiriş metni burada.\n\n"
        "1. YÖNTEM\nNitel yöntem kullanıldı.\n\n"
        "BULGULAR\nBulgular şöyle.\n\n"
        "KAYNAKÇA\nYazar A. (2020).\nYazar B. (2021)."
    )
    secs = pdf.split_sections(text)
    heads = [s["heading"] for s in secs]
    assert any("ÖZET" in h for h in heads)
    assert any("GİRİŞ" in h for h in heads)
    assert any("YÖNTEM" in h for h in heads)
    assert any("KAYNAKÇA" in h for h in heads)
    # KAYNAKÇA bölümünde iki referans satırı olmalı
    kaynak = next(s for s in secs if "KAYNAKÇA" in s["heading"])
    assert "Yazar A." in kaynak["text"] and "Yazar B." in kaynak["text"]


def test_split_sections_none_found():
    assert pdf.split_sections("başlık yok, sadece düz metin paragrafı.") == []


def test_extract_pagination_out_of_range():
    minimal = _minimal_pdf_bytes()
    r = pdf.extract(minimal, "http://x/file/1", start_page=2)
    assert r.page_count == 1
    assert r.start_page == 2
    assert not r.has_more_pages
    assert not r.has_text  # 2. sayfadan başlayınca boş


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
        xref += (f"{off:010d} 00000 n \n").encode()
    trailer = (
        b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n"
        + str(xref_pos).encode()
        + b"\n%%EOF"
    )
    return header + body + xref + trailer
