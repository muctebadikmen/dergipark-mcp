"""MCP Prompt'lar + (gömülü) dergi kaynağı — offline (ağsız)."""

import json

from fastmcp import Client

from dergipark_mcp.server import mcp


async def test_prompts_registered_and_render():
    async with Client(mcp) as c:
        names = {p.name for p in await c.list_prompts()}
        assert {
            "literature_review", "summarize_article",
            "compare_articles", "research_discovery",
        } <= names

        pr = await c.get_prompt("literature_review", {"topic": "eğitim", "journal_slug": "mulkiye"})
        text = pr.messages[0].content.text
        assert "search_articles" in text and "mulkiye" in text and "eğitim" in text

        pr2 = await c.get_prompt("literature_review", {"topic": "iletişim"})
        # journal verilmeyince list_journals'a yönlendirmeli
        assert "list_journals" in pr2.messages[0].content.text

        pr3 = await c.get_prompt("research_discovery", {"topic": "yapay zeka", "expertise_level": "advanced"})
        assert "search_articles" in pr3.messages[0].content.text


async def test_journal_resource_offline():
    async with Client(mcp) as c:
        templates = {t.uriTemplate for t in await c.list_resource_templates()}
        assert "dergipark://journal/{slug}" in templates
        assert "dergipark://article/{article_id}" in templates

        got = await c.read_resource("dergipark://journal/mulkiye")
        data = json.loads(got[0].text)
        assert data["slug"] == "mulkiye"
        assert data["url"].endswith("/pub/mulkiye")
        assert "subjects" in data or "name" in data
