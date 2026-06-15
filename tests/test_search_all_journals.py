"""search_all_journals aracı — uçtan uca, bellek-içi indeksle, OFFLINE (ağsız).

Araç ağ harvest'i yapmaz (yalnızca indeksli havuzda arar), bu yüzden tamamen
deterministik ve offline test edilebilir. Mevcut search_articles testleri canlıdır;
bu yeni araç için ayrı, ağsız bir kapsam veriyoruz.
"""

from dataclasses import dataclass, field

import pytest
from fastmcp import Client

from dergipark_mcp import index as _index
from dergipark_mcp.server import mcp


@dataclass
class FakeArticle:
    id: str
    title: str | None = None
    title_en: str | None = None
    authors: list = field(default_factory=list)
    abstract: str | None = None
    date: str | None = None
    url: str | None = None
    subjects: list = field(default_factory=list)
    keywords: list = field(default_factory=list)
    type: str | None = "article"
    article_type: str | None = None


@pytest.fixture
def memory_index():
    """_default_index'i bellek-içi bir indeksle değiştirir, sonra geri alır."""
    prev = _index._default_index
    _index._default_index = _index.SearchIndex(":memory:")
    try:
        yield _index._default_index
    finally:
        _index._default_index.close()
        _index._default_index = prev


async def test_search_all_journals_cross_journal(memory_index):
    memory_index.index_articles("khm", [FakeArticle("1", title="Türk Hukuk Tarihi Üzerine", date="2022")])
    memory_index.mark_harvested("khm", 1, complete=True)
    memory_index.index_articles("ihm", [FakeArticle("2", title="Hukuk tarihi ve Mecelle", date="2020")])
    memory_index.mark_harvested("ihm", 1, complete=True)

    async with Client(mcp) as client:
        res = await client.call_tool("search_all_journals", {"query": "hukuk tarihi", "limit": 10})
    data = res.data
    assert data["scope"] == "all_indexed_journals"
    assert data["indexed_journal_count"] == 2
    assert data["indexed_article_total"] == 2
    assert data["total"] == 2
    assert {r["journal_slug"] for r in data["results"]} == {"khm", "ihm"}
    # Her sonuç hangi dergiden geldiğini taşır + dürüst kapsam notu var.
    assert "KAPSAM" in data["note"]
    assert set(data["journals_in_scope"]) == {"khm", "ihm"}


async def test_search_all_journals_empty_pool(memory_index):
    async with Client(mcp) as client:
        res = await client.call_tool("search_all_journals", {"query": "hukuk"})
    data = res.data
    assert data["indexed_journal_count"] == 0
    assert data["total"] == 0
    assert "Havuz boş" in data["note"]
