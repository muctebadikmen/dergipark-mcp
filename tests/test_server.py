"""MCP sunucusunu uçtan uca, bellek içi FastMCP Client ile test eder (canlı).

Bu, araçların gerçekten MCP protokolü üzerinden çağrılabildiğini ve geçerli
çıktı döndürdüğünü doğrular — Claude Desktop'ın yapacağı şeyin aynısı.

Çalıştırma: uv run pytest -m live tests/test_server.py
"""

import pytest
from fastmcp import Client

from dergipark_mcp.server import mcp
from dergipark_mcp import http as dphttp

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
    assert "bibtex" in data


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
            {"query": "siyaset", "journal": "mulkiye", "limit": 5, "max_scan": 60},
        )
    data = res.data
    assert data["scanned"] > 0
    assert "results" in data


async def test_fulltext_via_client():
    async with Client(mcp) as client:
        res = await client.call_tool(
            "get_article_fulltext", {"article": "1000", "max_pages": 2}
        )
    data = res.data
    assert data["pdf_url"]
    assert data["page_count"] >= 1
    assert "markdown" in data


async def test_resolve_bad_id():
    async with Client(mcp) as client:
        res = await client.call_tool("get_article", {"article": "not-an-id"})
    assert "error" in res.data
