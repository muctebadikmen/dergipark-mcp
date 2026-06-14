"""MCP sunucusunu uçtan uca, bellek içi FastMCP Client ile test eder (canlı).

Bu, araçların gerçekten MCP protokolü üzerinden çağrılabildiğini ve geçerli
çıktı döndürdüğünü doğrular — Claude Desktop'ın yapacağı şeyin aynısı.

Çalıştırma: uv run pytest -m live tests/test_server.py
"""

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from dergipark_mcp import http as dphttp
from dergipark_mcp.server import mcp

pytestmark = pytest.mark.live


@pytest.fixture(autouse=True)
async def _close_client():
    yield
    await dphttp.aclose()


async def test_tools_are_registered():
    async with Client(mcp) as client:
        tools = await client.list_tools()
    names = {t.name for t in tools}
    assert {
        "list_journals",
        "list_journal_articles",
        "search_articles",
        "get_article",
        "get_article_fulltext",
        "get_article_references",
    } <= names


async def test_get_article_via_client():
    async with Client(mcp) as client:
        res = await client.call_tool("get_article", {"article": "1000"})
    data = res.data
    assert data["id"] == "1000"
    assert data["title"]
    # 8 atıf formatı
    cites = data["citations"]
    assert cites["bibtex"].startswith("@")
    assert {"apa", "mla", "ieee", "chicago", "harvard", "ris", "csl_json"} <= set(cites)
    # yapısal yazar (oai_mods)
    assert data["authors_detailed"][0]["family"] == "Bakırcı"
    # cilt/sayı/sayfa (mods/HTML)
    assert data["volume"] == "29" and data["issue"] == "247"


async def test_get_article_rich_enrichment_via_client():
    # Zengin makale: afiliasyon + ORCID + çok yazarlı
    async with Client(mcp) as client:
        res = await client.call_tool("get_article", {"article": "1816398"})
    data = res.data
    dets = data["authors_detailed"]
    assert len(dets) == 2
    assert any(d.get("orcid") for d in dets)
    assert any(d.get("affiliation") for d in dets)
    assert data["citations"]["apa"]


async def test_get_article_by_url_via_client():
    async with Client(mcp) as client:
        res = await client.call_tool(
            "get_article",
            {"article": "https://dergipark.org.tr/tr/pub/mulkiye/article/1000",
             "include_bibtex": False},
        )
    assert res.data["url"].endswith("/article/1000")


async def test_list_journal_articles_via_client():
    async with Client(mcp) as client:
        res = await client.call_tool(
            "list_journal_articles", {"journal": "mulkiye", "limit": 3}
        )
    data = res.data
    assert data["count"] == 3
    assert data["articles"][0]["id"]


async def test_search_articles_via_client():
    async with Client(mcp) as client:
        res = await client.call_tool(
            "search_articles",
            {"query": "siyaset", "journal": "mulkiye", "limit": 5, "max_scan": 120},
        )
    data = res.data
    assert data["indexed"] > 0
    assert "results" in data and "total" in data
    # ikinci arama indeksten anında (harvested_recently) çalışmalı
    async with Client(mcp) as client:
        res2 = await client.call_tool(
            "search_articles", {"query": "siyaset", "journal": "mulkiye", "sort": "newest"}
        )
    assert "results" in res2.data


async def test_fulltext_via_client():
    async with Client(mcp) as client:
        res = await client.call_tool(
            "get_article_fulltext", {"article": "1000", "max_pages": 2}
        )
    data = res.data
    assert data["pdf_url"]
    assert data["page_count"] >= 1
    assert "markdown" in data


async def test_article_resource_live():
    import json
    async with Client(mcp) as client:
        got = await client.read_resource("dergipark://article/1000")
    data = json.loads(got[0].text)
    assert data["id"] == "1000"
    assert data["resource_uri"] == "dergipark://article/1000"


async def test_search_results_have_resource_uri():
    async with Client(mcp) as client:
        res = await client.call_tool(
            "search_articles", {"query": "siyaset", "journal": "mulkiye", "limit": 2}
        )
    if res.data["results"]:
        assert res.data["results"][0]["resource_uri"].startswith("dergipark://article/")


async def test_resolve_bad_id():
    # Çözümlenemez girdi artık ToolError yükseltir (dict'te "error" yerine).
    async with Client(mcp) as client:
        with pytest.raises(ToolError):
            await client.call_tool("get_article", {"article": "not-an-id"})
