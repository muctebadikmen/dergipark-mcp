"""Canlı entegrasyon testleri — gerçek DergiPark trafiği üretir.

Çalıştırma:  uv run pytest -m live
Atlama:      uv run pytest -m "not live"

İstekler nazik HTTP katmanı (rate-limit + backoff) üzerinden gider; yine de
ağ erişimi ve birkaç saniye gerektirir.
"""

import pytest

from dergipark_mcp import oai, site
from dergipark_mcp import http as dphttp

pytestmark = pytest.mark.live


@pytest.fixture(autouse=True)
async def _close_client():
    yield
    await dphttp.aclose()


async def test_get_record_live():
    a = await oai.get_record("1000")
    assert a.id == "1000"
    assert a.title
    assert a.url and "dergipark.org.tr" in a.url
    assert a.journal_slug == "mulkiye"


async def test_list_records_live():
    arts = await oai.list_records("mulkiye", max_records=5)
    assert len(arts) == 5
    assert all(a.id for a in arts)
    assert all(a.url for a in arts)


async def test_list_journals_live():
    journals = await oai.list_journals()
    assert len(journals) > 0
    assert all(j.slug for j in journals)


async def test_article_page_pdf_live():
    page = await site.fetch_article_page(
        "https://dergipark.org.tr/en/pub/mulkiye/article/1000"
    )
    assert page.pdf_url and "download/article-file" in page.pdf_url


async def test_bibtex_live():
    bib = await site.fetch_bibtex("1000")
    assert bib and bib.startswith("@")
