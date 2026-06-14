"""Atıf biçimlendirme — offline (ağ gerektirmez)."""

import pytest

from dergipark_mcp import citations
from dergipark_mcp.citations import CitationData

# ---------------------------------------------------------------------------
# Ortak fixture'lar
# ---------------------------------------------------------------------------

def two_author_no_doi() -> CitationData:
    return CitationData(
        title="Okul Öncesi Eğitimde Oyun Temelli Yaklaşım",
        authors=["Tunahan Karaarslan", "Gülçin Güven"],
        year="2026",
        journal="İstanbul 29 Mayıs Üniversitesi Eğitim Fakültesi Dergisi",
        volume="1",
        issue="1",
        first_page="1",
        last_page="12",
        url="https://dergipark.org.tr/tr/pub/example/article/1816398",
        article_id="1816398",
    )


def two_author_with_doi() -> CitationData:
    d = two_author_no_doi()
    d.doi = "10.1234/abc"
    return d


def three_author() -> CitationData:
    return CitationData(
        title="Üç Yazarlı Bir Çalışma",
        authors=["Tunahan Karaarslan", "Gülçin Güven", "Ayşe Yılmaz"],
        year="2025",
        journal="Test Dergisi",
        volume="3",
        issue="2",
        first_page="10",
        last_page="20",
        article_id="999",
    )


# ---------------------------------------------------------------------------
# split_name
# ---------------------------------------------------------------------------

def test_split_name_two_tokens():
    assert citations.split_name("Tunahan Karaarslan") == ("Tunahan", "Karaarslan")


def test_split_name_three_tokens():
    assert citations.split_name("Ali Veli Han") == ("Ali Veli", "Han")


def test_split_name_single_token():
    assert citations.split_name("Madonna") == ("", "Madonna")


def test_split_name_empty():
    assert citations.split_name("   ") == ("", "")


# ---------------------------------------------------------------------------
# APA
# ---------------------------------------------------------------------------

def test_apa_two_author_core():
    out = citations.format_apa(two_author_no_doi())
    assert "Karaarslan, T." in out
    assert "Güven, G." in out
    assert ", & " in out          # APA çoklu yazar ayraç
    assert "(2026)" in out
    assert "1(1)" in out
    assert "1-12" in out
    assert "İstanbul 29 Mayıs" in out


def test_apa_doi_suffix():
    out = citations.format_apa(two_author_with_doi())
    assert out.rstrip().endswith("https://doi.org/10.1234/abc")


def test_apa_missing_year_is_nd():
    d = two_author_no_doi()
    d.year = None
    out = citations.format_apa(d)
    assert "(n.d.)" in out


# ---------------------------------------------------------------------------
# MLA
# ---------------------------------------------------------------------------

def test_mla_two_author_core():
    out = citations.format_mla(two_author_no_doi())
    assert "Karaarslan, Tunahan" in out
    assert "and Gülçin Güven" in out
    assert '"Okul Öncesi Eğitimde Oyun Temelli Yaklaşım."' in out
    assert "vol. 1" in out
    assert "no. 1" in out
    assert "2026" in out
    assert "pp. 1-12" in out


def test_mla_three_author_et_al():
    out = citations.format_mla(three_author())
    assert "Karaarslan, Tunahan, et al." in out
    assert "Güven" not in out      # 3+ -> yalnızca ilk yazar


# ---------------------------------------------------------------------------
# IEEE
# ---------------------------------------------------------------------------

def test_ieee_two_author_core():
    out = citations.format_ieee(two_author_no_doi())
    assert "T. Karaarslan and G. Güven" in out
    assert '"Okul Öncesi Eğitimde Oyun Temelli Yaklaşım,"' in out
    assert "vol. 1" in out
    assert "no. 1" in out
    assert "pp. 1-12" in out
    assert out.rstrip().endswith("2026.")


def test_ieee_three_author_et_al():
    out = citations.format_ieee(three_author())
    assert "T. Karaarslan et al." in out


# ---------------------------------------------------------------------------
# Chicago
# ---------------------------------------------------------------------------

def test_chicago_two_author_core():
    out = citations.format_chicago(two_author_no_doi())
    assert "Karaarslan, Tunahan, and Gülçin Güven." in out
    assert '"Okul Öncesi Eğitimde Oyun Temelli Yaklaşım."' in out
    assert "no. 1" in out
    assert "(2026)" in out
    assert ": 1-12" in out


def test_chicago_three_author_et_al():
    out = citations.format_chicago(three_author())
    assert "Karaarslan, Tunahan, et al." in out


# ---------------------------------------------------------------------------
# Harvard
# ---------------------------------------------------------------------------

def test_harvard_two_author_core():
    out = citations.format_harvard(two_author_no_doi())
    assert "Karaarslan, T. and Güven, G." in out
    assert "(2026)" in out
    assert "'Okul Öncesi Eğitimde Oyun Temelli Yaklaşım'" in out
    assert "1(1)" in out
    assert "pp. 1-12" in out


def test_harvard_missing_year_is_nd():
    d = two_author_no_doi()
    d.year = None
    out = citations.format_harvard(d)
    assert "(n.d.)" in out


# ---------------------------------------------------------------------------
# BibTeX
# ---------------------------------------------------------------------------

def test_bibtex_structure():
    out = citations.to_bibtex(two_author_no_doi())
    assert out.startswith("@article{")
    assert "author = {Karaarslan, Tunahan and Güven, Gülçin}" in out
    assert "pages = {1--12}" in out
    assert "number = {1}" in out
    assert "volume = {1}" in out
    assert out.rstrip().endswith("}")


def test_bibtex_key_ascii_folded():
    out = citations.to_bibtex(two_author_no_doi())
    # İlk satır anahtarı içerir; Türkçe karakter olmamalı, ascii katlanmış.
    first_line = out.splitlines()[0]
    assert first_line == "@article{karaarslan2026_1816398,"


def test_bibtex_doi_field():
    out = citations.to_bibtex(two_author_with_doi())
    assert "doi = {10.1234/abc}" in out


def test_bibtex_key_fallback_no_author():
    d = CitationData(title="Anonim", year="2020", article_id="42")
    out = citations.to_bibtex(d)
    assert out.splitlines()[0] == "@article{dergipark42,"


def test_bibtex_key_fallback_no_author_no_id():
    d = CitationData(title="Anonim")
    out = citations.to_bibtex(d)
    assert out.splitlines()[0] == "@article{article,"


# ---------------------------------------------------------------------------
# RIS
# ---------------------------------------------------------------------------

def test_ris_structure():
    out = citations.to_ris(two_author_no_doi())
    assert "TY  - JOUR" in out
    au_lines = [ln for ln in out.splitlines() if ln.startswith("AU  - ")]
    assert au_lines == ["AU  - Karaarslan, Tunahan", "AU  - Güven, Gülçin"]
    assert "TI  - Okul Öncesi Eğitimde Oyun Temelli Yaklaşım" in out
    assert "VL  - 1" in out
    assert "IS  - 1" in out
    assert "SP  - 1" in out
    assert "EP  - 12" in out
    assert out.endswith("ER  - \n")
    assert out.splitlines()[-1] == "ER  - "


def test_ris_doi_line():
    out = citations.to_ris(two_author_with_doi())
    assert "DO  - 10.1234/abc" in out


# ---------------------------------------------------------------------------
# CSL-JSON
# ---------------------------------------------------------------------------

def test_csl_json_structure():
    item = citations.to_csl_json(two_author_no_doi())
    assert item["type"] == "article-journal"
    assert item["title"].startswith("Okul Öncesi")
    assert item["author"] == [
        {"given": "Tunahan", "family": "Karaarslan"},
        {"given": "Gülçin", "family": "Güven"},
    ]
    assert item["container-title"].startswith("İstanbul")
    assert item["issued"] == {"date-parts": [[2026]]}
    assert item["volume"] == "1"
    assert item["issue"] == "1"
    assert item["page"] == "1-12"


def test_csl_json_omits_absent_fields():
    d = CitationData(title="Sade", authors=["Tek Yazar"])
    item = citations.to_csl_json(d)
    assert "DOI" not in item
    assert "issued" not in item
    assert "volume" not in item
    assert "page" not in item


def test_csl_json_doi():
    item = citations.to_csl_json(two_author_with_doi())
    assert item["DOI"] == "10.1234/abc"


# ---------------------------------------------------------------------------
# Edge cases: tek yazar, sıfır yazar
# ---------------------------------------------------------------------------

def test_single_author_apa():
    d = CitationData(
        title="Tek Yazarlı Makale",
        authors=["Tunahan Karaarslan"],
        year="2024",
        journal="Dergi",
        volume="2",
        issue="3",
        first_page="5",
        last_page="9",
    )
    out = citations.format_apa(d)
    assert "Karaarslan, T." in out
    assert "&" not in out          # tek yazarda ayraç olmamalı
    assert "2(3)" in out


def test_zero_author_does_not_crash():
    d = CitationData(
        title="Yazarsız Çalışma",
        year="2023",
        journal="Anonim Dergi",
        volume="1",
        first_page="1",
        last_page="4",
        article_id="7",
    )
    apa = citations.format_apa(d)
    mla = citations.format_mla(d)
    ieee = citations.format_ieee(d)
    chicago = citations.format_chicago(d)
    harvard = citations.format_harvard(d)
    for out in (apa, mla, ieee, chicago, harvard):
        assert "Yazarsız Çalışma" in out
        assert "(2023)" in out or "2023" in out
    # Sarkık virgül / boş parantez olmamalı.
    assert ", ," not in apa
    assert "()" not in apa
    ris = citations.to_ris(d)
    assert "AU  - " not in ris     # yazar yoksa AU satırı olmamalı
    bib = citations.to_bibtex(d)
    assert "author" not in bib


def test_missing_volume_issue_pages_clean():
    d = CitationData(
        title="Minimal",
        authors=["Tunahan Karaarslan"],
        year="2022",
        journal="Dergi",
    )
    apa = citations.format_apa(d)
    assert "Dergi." in apa
    assert "()" not in apa
    assert ", ," not in apa
    assert "(2022)" in apa


# ---------------------------------------------------------------------------
# authors_structured override
# ---------------------------------------------------------------------------

def test_authors_structured_override_multiword_surname():
    d = CitationData(
        title="Override Testi",
        authors=["YOK SAYILMALI"],
        authors_structured=[("Tunahan", "Arslan Nizam")],
        year="2026",
        journal="Dergi",
    )
    bib = citations.to_bibtex(d)
    assert "author = {Arslan Nizam, Tunahan}" in bib
    ris = citations.to_ris(d)
    assert "AU  - Arslan Nizam, Tunahan" in ris
    csl = citations.to_csl_json(d)
    assert csl["author"] == [{"given": "Tunahan", "family": "Arslan Nizam"}]
    apa = citations.format_apa(d)
    assert "Arslan Nizam, T." in apa
    assert "YOK" not in apa        # düz authors yok sayılmalı


# ---------------------------------------------------------------------------
# format_citation dispatch
# ---------------------------------------------------------------------------

def test_format_citation_case_insensitive():
    d = two_author_no_doi()
    assert citations.format_citation(d, "APA") == citations.format_apa(d)
    assert citations.format_citation(d, "Apa") == citations.format_apa(d)
    assert citations.format_citation(d, "ieee") == citations.format_ieee(d)


def test_format_citation_unknown_raises():
    with pytest.raises(ValueError):
        citations.format_citation(two_author_no_doi(), "vancouver")


# ---------------------------------------------------------------------------
# all_citations
# ---------------------------------------------------------------------------

def test_all_citations_keys():
    out = citations.all_citations(two_author_with_doi())
    assert set(out.keys()) == {
        "bibtex", "ris", "csl_json", "apa", "mla", "ieee", "chicago", "harvard"
    }
    assert isinstance(out["csl_json"], dict)
    assert out["bibtex"].startswith("@article{")
    assert out["ris"].endswith("ER  - \n")


# ---------------------------------------------------------------------------
# HTML entity unescape
# ---------------------------------------------------------------------------

def test_html_entities_unescaped():
    d = CitationData(
        title="Sa&#287;l&#305;k &amp; Eğitim",
        authors=["Ali Veli"],
        year="2021",
        journal="Bilim &amp; Teknoloji",
    )
    apa = citations.format_apa(d)
    assert "&amp;" not in apa
    assert "&#" not in apa
    assert "Bilim & Teknoloji" in apa


def test_initials_multi_given():
    # "Ali Veli" -> "A. V."
    d = CitationData(authors=["Ali Veli Han"], year="2020", title="X", journal="J")
    apa = citations.format_apa(d)
    assert "Han, A. V." in apa
