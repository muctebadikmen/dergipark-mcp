"""OAI Dublin Core ayrıştırma — offline (ağ gerektirmez)."""

import xml.etree.ElementTree as ET

from conftest import read_fixture

from dergipark_mcp import oai


def test_normalize_keyword_strips_label_and_stray_punct():
    # Bazı DergiPark kayıtları dc:subject'e etiket ya da başıboş ":" sızdırır.
    assert oai.normalize_keyword(": Kagan") == "Kagan"
    assert oai.normalize_keyword("Anahtar Kelimeler: Kağan") == "Kağan"
    assert oai.normalize_keyword("Keywords: Roman Law") == "Roman Law"
    # Temiz değerler aynen korunur (Türkçe karakterler dahil)
    assert oai.normalize_keyword("Roma Hukuku") == "Roma Hukuku"
    assert oai.normalize_keyword("  ") is None
    assert oai.normalize_keyword(None) is None


def test_dc_subject_cleaned_in_parse():
    xml = (
        '<record xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/">'
        '<header><identifier>oai:dergipark.org.tr:record/1</identifier></header>'
        '<metadata><oai_dc:dc>'
        '<dc:title>Başlık</dc:title>'
        '<dc:subject>: Kagan</dc:subject>'
        '<dc:subject>Egemenlik</dc:subject>'
        '</oai_dc:dc></metadata></record>'
    )
    art = oai.parse_record(ET.fromstring(xml))
    assert art.subjects == ["Kagan", "Egemenlik"]


def _parse_fixture_record():
    root = ET.fromstring(read_fixture("getrecord.xml").encode("utf-8"))
    record = root.find(".//oai:GetRecord/oai:record", oai.NS)
    assert record is not None
    return oai.parse_record(record)


def test_basic_fields():
    a = _parse_fixture_record()
    assert a.id == "1000"
    assert a.title.startswith("TBMM")
    assert a.title_en.startswith("On the Method")
    assert a.authors == ["Bakırcı, Fahri"]
    assert a.date == "2014-03-06"
    assert a.abstract and "tezkere" in a.abstract


def test_identifiers_split():
    a = _parse_fixture_record()
    assert a.url == "https://dergipark.org.tr/en/pub/mulkiye/article/1000"
    assert a.persistent_id == "https://izlik.org/JA26ZK54BZ"


def test_journal_and_slug():
    a = _parse_fixture_record()
    assert a.journal == "Mülkiye Dergisi"          # source'tan türetildi
    assert a.journal_slug == "mulkiye"              # URL'den türetildi
    assert a.type == "article"
    assert "Creative Commons" in (a.rights or "")


def test_oai_identifier_helper():
    assert oai.article_oai_identifier(1000) == "oai:dergipark.org.tr:article/1000"
    assert oai._numeric_id_from_identifier("oai:dergipark.org.tr:record/55") == "55"


def _parse_mods(name: str):
    root = ET.fromstring(read_fixture(name).encode("utf-8"))
    record = root.find(".//oai:GetRecord/oai:record", oai.NS)
    assert record is not None
    return oai.parse_mods_record(record)


def test_mods_single_author():
    a = _parse_mods("getrecord_mods.xml")
    assert a.id == "1000"
    assert a.journal_slug == "mulkiye"
    assert a.journal == "Mülkiye Dergisi"
    assert len(a.authors_detailed) == 1
    assert a.authors_detailed[0].given == "Fahri"
    assert a.authors_detailed[0].family == "Bakırcı"
    assert a.authors == ["Fahri Bakırcı"]
    assert a.volume == "29" and a.issue == "247"
    assert a.first_page == "87" and a.last_page == "97"
    assert a.date == "2014-03-06"
    assert a.url == "https://dergipark.org.tr/en/pub/mulkiye/article/1000"
    assert a.persistent_id == "https://izlik.org/JA26ZK54BZ"


def test_mods_multi_author():
    a = _parse_mods("getrecord_mods_multi.xml")
    assert a.id == "1816398"
    assert [d.family for d in a.authors_detailed] == ["Karaarslan", "Güven"]
    assert [d.given for d in a.authors_detailed] == ["Tunahan", "Gülçin"]
    assert a.abstract  # daha yeni kayıt → mods'ta abstract var
    assert a.date == "2026-01-30"
    assert a.volume == "1" and a.issue == "1"
    assert a.first_page == "1" and a.last_page == "12"


def test_merge_article_fills_gaps():
    dc = oai.Article(id="1", oai_identifier="x", abstract="özet", subjects=["a"], title="Başlık")
    mods = oai.Article(
        id="1", oai_identifier="x", volume="3", issue="2",
        authors=["Ad Soyad"],
        authors_detailed=[oai.Author(name="Ad Soyad", given="Ad", family="Soyad")],
    )
    merged = oai.merge_article(dc, mods)
    assert merged.abstract == "özet"       # base korunur
    assert merged.subjects == ["a"]
    assert merged.volume == "3" and merged.issue == "2"   # extra'dan dolar
    assert merged.authors == ["Ad Soyad"]
    assert merged.authors_detailed[0].family == "Soyad"


def test_error_detection():
    xml = (
        '<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">'
        '<error code="idDoesNotExist">bad id</error></OAI-PMH>'
    )
    root = ET.fromstring(xml)
    try:
        oai._check_error(root)
    except oai.OAIError as exc:
        assert exc.code == "idDoesNotExist"
    else:
        raise AssertionError("OAIError beklenmişti")
