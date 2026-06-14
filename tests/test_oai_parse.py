"""OAI Dublin Core ayrıştırma — offline (ağ gerektirmez)."""

import xml.etree.ElementTree as ET

from dergipark_mcp import oai
from conftest import read_fixture


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
