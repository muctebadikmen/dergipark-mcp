"""Dergi dizini ayrıştırma + filtreleme — offline."""

from dergipark_mcp import directory
from conftest import read_fixture


def _entries():
    return directory.parse_directory_page(read_fixture("journals_dir.html"))


def test_parse_excludes_nav_and_reads_cards():
    entries = _entries()
    assert [e.slug for e in entries] == ["mulkiye", "29mayisegitim", "jas"]
    m = entries[0]
    assert m.name == "Mülkiye Dergisi"
    assert m.publisher.startswith("Mülkiyeliler")
    assert "Political Science" in m.subjects and "Public Administration" in m.subjects
    assert entries[2].subjects == []  # boş journal-subjects


def test_filter_query_turkish_insensitive():
    entries = _entries()
    assert [e.slug for e in directory.filter_journals(entries, query="mülkiye")] == ["mulkiye"]
    assert [e.slug for e in directory.filter_journals(entries, query="MULKIYE")] == ["mulkiye"]
    # slug üzerinden de bulunur
    assert [e.slug for e in directory.filter_journals(entries, query="29mayis")] == ["29mayisegitim"]


def test_filter_by_subject():
    entries = _entries()
    res = directory.filter_journals(entries, subject="education")
    assert [e.slug for e in res] == ["29mayisegitim"]


def test_subject_counts_sorted():
    entries = _entries()
    counts = directory.subject_counts(entries)
    assert counts["Education"] == 1
    assert "Political Science" in counts


def test_entries_roundtrip():
    entries = _entries()
    raw = [e.to_dict() for e in entries]
    back = directory._entries_from_raw(raw)
    assert [e.slug for e in back] == [e.slug for e in entries]
    assert back[0].subjects == entries[0].subjects


def test_load_embedded_shape():
    data = directory.load_embedded()
    assert isinstance(data.get("journals"), list)
    assert "count" in data


def test_embedded_directory_is_populated():
    # Pakete gömülü gerçek dizin ~2.5k dergi içermeli (build_directory.py çıktısı).
    entries = directory.embedded_entries()
    assert len(entries) > 2000
    slugs = {e.slug for e in entries}
    assert "mulkiye" in slugs


async def test_list_journals_tool_offline():
    # list_journals aracı gömülü dizinle ÇALIŞIR (ağ gerekmez).
    from fastmcp import Client
    from dergipark_mcp.server import mcp

    async with Client(mcp) as client:
        res = await client.call_tool("list_journals", {"limit": 5})
        assert res.data["directory_size"] > 2000
        assert res.data["count"] == 5
        assert res.data["available_subjects"]
        res2 = await client.call_tool("list_journals", {"query": "eğitim", "limit": 3})
        assert res2.data["total"] > 10
