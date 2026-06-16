"""Dergi-içi FTS5 arama + Türkçe normalizasyon — offline (ağsız)."""

from dataclasses import dataclass, field

import pytest

from dergipark_mcp import index
from dergipark_mcp.index import SearchIndex, tr_fold


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


SAMPLE = [
    FakeArticle("1", title="Eğitimde teknoloji kullanımı", authors=["Ayşe Yılmaz"],
                abstract="Bu çalışma eğitimde dijital araçları inceler.", date="2021-05-01",
                subjects=["Education"], article_type="Research Article"),
    FakeArticle("2", title="İletişim ve toplum", authors=["Mehmet Demir"],
                abstract="İletişim kuramları üzerine.", date="2019-03-10",
                subjects=["Communication"], article_type="Review"),
    FakeArticle("3", title="Siyaset bilimi giriş", authors=["Ali Veli Öztürk"],
                abstract="Siyaset ve yönetim.", date="2023-11-20",
                subjects=["Political Science"], article_type="Research Article"),
    FakeArticle("4", title="Eğitim psikolojisi temelleri", authors=["Ayşe Yılmaz", "Zeynep Kaya"],
                abstract="Öğrenme ve gelişim.", date="2024-01-15",
                subjects=["Education", "Psychology"], article_type="Research Article"),
]


@pytest.fixture
def idx():
    ix = SearchIndex(":memory:")
    ix.index_articles("test", SAMPLE)
    ix.mark_harvested("test", len(SAMPLE))
    yield ix
    ix.close()


def test_tr_fold_symmetry():
    assert tr_fold("Eğitim") == tr_fold("eğitim") == tr_fold("egitim") == "egitim"
    assert tr_fold("İletişim") == tr_fold("iletisim") == "iletisim"
    assert tr_fold("ÇĞIİÖŞÜ") == "cgiiosu"


def test_query_terms_drop_stopwords():
    assert index._query_terms("eğitim ve teknoloji") == ["egitim", "teknoloji"]
    assert index._query_terms("ve ile bu") == []


def test_stopword_turkish_icin_filtered():
    # "için" katlanınca "icin" olur; stopword seti de katlanmış tutulduğundan elenmeli.
    assert index._query_terms("eğitim için politika") == ["egitim", "politika"]


def test_year_filter_year_only_date():
    # Yıl-tek tarihli ("2020") kayıt, year_from=2020 ile DAHİL edilmeli
    # (sözlüksel string karşılaştırması bunu yanlışlıkla elerdi).
    ix = SearchIndex(":memory:")
    ix.index_articles("t", [FakeArticle("9", title="eğitim çalışması", date="2020")])
    total, rows = ix.search("t", "eğitim", year_from=2020)
    assert {r["art_id"] for r in rows} == {"9"}
    total2, rows2 = ix.search("t", "eğitim", year_from=2021)
    assert total2 == 0
    ix.close()


def test_search_turkish_insensitive(idx):
    # Hepsi aynı sonucu vermeli (folding simetrik)
    for q in ["eğitim", "Eğitim", "egitim", "EGITIM"]:
        total, rows = idx.search("test", q)
        ids = {r["art_id"] for r in rows}
        assert ids == {"1", "4"}, q


def test_search_prefix_match(idx):
    # "egitimde" araması "Eğitimde teknoloji" (id 1) bulmalı; ön-ek "egit" de
    total, rows = idx.search("test", "egit")
    assert {"1", "4"} <= {r["art_id"] for r in rows}


def test_search_iletisim_dotted(idx):
    total, rows = idx.search("test", "iletişim")
    assert [r["art_id"] for r in rows] == ["2"]


def test_bm25_title_weight_ranks_title_hit_first(idx):
    # "eğitim": id 1 ve 4 başlıkta; relevance + recency → 4 (2024) 1'den (2021) önce
    total, rows = idx.search("test", "eğitim", sort="relevance")
    assert rows[0]["art_id"] == "4"


def test_sort_newest_oldest(idx):
    _, newest = idx.search("test", "eğitim", sort="newest")
    assert newest[0]["art_id"] == "4"  # 2024
    _, oldest = idx.search("test", "eğitim", sort="oldest")
    assert oldest[0]["art_id"] == "1"  # 2021


def test_year_filter(idx):
    total, rows = idx.search("test", "eğitim", year_from=2023)
    assert {r["art_id"] for r in rows} == {"4"}


def test_author_filter(idx):
    total, rows = idx.search("test", "eğitim", author="zeynep")
    assert {r["art_id"] for r in rows} == {"4"}


def test_article_type_filter(idx):
    total, rows = idx.search("test", "iletişim", article_type="Review")
    assert {r["art_id"] for r in rows} == {"2"}
    total2, rows2 = idx.search("test", "iletişim", article_type="Research Article")
    assert total2 == 0


def test_pagination_total_and_offset(idx):
    total, page1 = idx.search("test", "eğitim", limit=1, offset=0)
    assert total == 2 and len(page1) == 1
    _, page2 = idx.search("test", "eğitim", limit=1, offset=1)
    assert page1[0]["art_id"] != page2[0]["art_id"]


def test_dedup_no_duplicate_on_reindex(idx):
    # Aynı makaleleri tekrar indekslemek yeni kayıt eklememeli
    added = idx.index_articles("test", SAMPLE)
    assert added == 0
    assert idx.indexed_count("test") == 4


def test_empty_query_returns_nothing(idx):
    assert idx.search("test", "ve ile") == (0, [])


def test_phrase_in_title_outranks_scattered_terms():
    # "hukuk tarihi": p = ifade başlıkta; n = terimler dağınık ("tarihi" başlıkta
    # "Karar Tarihi" gürültüsü + "hukuk" özette). İkisi de AND eşleşir ama p,
    # daha YENİ olan n'e rağmen tam-ifade bonusuyla en üstte gelmeli.
    ix = SearchIndex(":memory:")
    ix.index_articles("t", [
        FakeArticle("p", title="Türk Hukuk Tarihi Üzerine", date="2010"),
        FakeArticle("n", title="Karar Tarihi: 2024/15", abstract="… hukuk konuları …", date="2024"),
    ])
    total, rows = ix.search("t", "hukuk tarihi")
    assert total == 2  # her ikisi de "hukuk" + "tarihi" içerir (AND korunur)
    assert rows[0]["art_id"] == "p"  # tam ifade başlıkta → recency'e rağmen en üstte
    ix.close()


def test_search_returns_journal_slug(idx):
    # Sonuç satırları artık hangi dergiden geldiğini taşır (dergiler-arası arama için).
    _, rows = idx.search("test", "eğitim")
    assert rows and all(r["journal_slug"] == "test" for r in rows)


def test_cross_journal_search_none_slug():
    # journal_slug=None → indekslenmiş TÜM dergilerde arar; slug verilince izole kalır.
    ix = SearchIndex(":memory:")
    ix.index_articles("j1", [FakeArticle("a", title="Eğitim ve hukuk reformu")])
    ix.index_articles("j2", [FakeArticle("b", title="Hukuk tarihi araştırması")])
    total, rows = ix.search(None, "hukuk")
    assert total == 2
    assert {r["journal_slug"] for r in rows} == {"j1", "j2"}
    # tek dergi araması yalnız o dergiyi döndürür
    _, only_j2 = ix.search("j2", "hukuk")
    assert {r["journal_slug"] for r in only_j2} == {"j2"}
    ix.close()


def test_indexed_journals_inventory():
    ix = SearchIndex(":memory:")
    ix.index_articles("j1", [FakeArticle("a", title="x")])
    ix.mark_harvested("j1", 1, complete=True)
    ix.index_articles("j2", [FakeArticle("b", title="y"), FakeArticle("c", title="z")])
    ix.mark_harvested("j2", 2, complete=False)
    pool = ix.indexed_journals()
    by = {p["slug"]: p for p in pool}
    assert by["j1"]["count"] == 1 and by["j1"]["complete"] is True
    assert by["j2"]["count"] == 2 and by["j2"]["complete"] is False
    assert pool[0]["slug"] == "j2"  # en çok makaleli başta
    ix.close()


def test_search_by_author_order_independent():
    # "Aybars Pamir" (ad soyad), kayıt "Pamir, Aybars" (soyad, ad) olsa da eşleşmeli.
    ix = SearchIndex(":memory:")
    ix.index_articles("j1", [FakeArticle("1", title="A", authors=["Pamir, Aybars"], date="2020")])
    ix.index_articles("j2", [FakeArticle("3", title="C", authors=["Pamir, Aybars"], date="2022")])
    ix.index_articles("j1", [FakeArticle("2", title="B", authors=["Yılmaz, Ayşe"], date="2021")])
    total, rows = ix.search_by_author("Aybars Pamir")
    assert {r["art_id"] for r in rows} == {"1", "3"}
    assert rows[0]["art_id"] == "3"  # newest (2022) önce
    # dergiler-arası: iki ayrı dergiden geldi
    assert {r["journal_slug"] for r in rows} == {"j1", "j2"}
    ix.close()


def test_find_similar_or_overlap():
    ix = SearchIndex(":memory:")
    ix.index_articles("j", [
        FakeArticle("src", title="Osmanlı hukuku tarihi", keywords=["Osmanlı", "hukuk tarihi"]),
        FakeArticle("a", title="Osmanlı hukukunda kefalet", keywords=["Osmanlı", "hukuk"]),
        FakeArticle("z", title="Deniz biyolojisi", keywords=["deniz", "biyoloji"]),
    ])
    terms = index._query_terms("Osmanlı hukuku tarihi hukuk")
    total, rows = ix.find_similar(terms, exclude_art_id="src", limit=10)
    ids = [r["art_id"] for r in rows]
    assert "src" not in ids       # kaynağın kendisi elenir
    assert "a" in ids             # ortak terimler (Osmanlı/hukuk)
    assert "z" not in ids         # alakasız
    ix.close()


def test_get_indexed_article():
    ix = SearchIndex(":memory:")
    ix.index_articles("j", [FakeArticle("7", title="X", keywords=["kavram1"])])
    row = ix.get_indexed_article("7")
    assert row and row["art_id"] == "7" and "kavram1" in (row["keywords"] or "")
    assert ix.get_indexed_article("999") is None
    ix.close()


def test_seed_loads_into_empty_cache(tmp_path, monkeypatch):
    # Bake'lenmiş seed: boş bir cache'e açılışta kopyalanıp yüklenmeli (havuz sıcak).
    seed = tmp_path / "seed.db"
    s = SearchIndex(str(seed))
    s.index_articles("j", [FakeArticle("1", title="Hukuk tarihi")])
    s.mark_harvested("j", 1, complete=True)
    s.close()

    cache = tmp_path / "cache"
    monkeypatch.setenv("DERGIPARK_CACHE_DIR", str(cache))
    monkeypatch.setenv("DERGIPARK_SEED_INDEX", str(seed))
    index._default_index = None
    try:
        idx2 = index.get_default_index()
        total, rows = idx2.search(None, "hukuk")
        assert total == 1 and rows[0]["journal_slug"] == "j"
        assert (cache / "index.db").exists()  # seed yazılabilir konuma kopyalandı
    finally:
        if index._default_index is not None:
            index._default_index.close()
        index._default_index = None


def test_seed_loads_from_gzip(tmp_path, monkeypatch):
    # Bake'lenmiş seed GZIP'li gelir → açılışta çözülerek yüklenmeli.
    import gzip
    import shutil as _sh
    seed = tmp_path / "seed.db"
    s = SearchIndex(str(seed))
    s.index_articles("j", [FakeArticle("1", title="Hukuk tarihi")])
    s.mark_harvested("j", 1, complete=True)
    s.close()
    gz = tmp_path / "seed.db.gz"
    with open(seed, "rb") as fi, gzip.open(gz, "wb") as fo:
        _sh.copyfileobj(fi, fo)

    cache = tmp_path / "cache"
    monkeypatch.setenv("DERGIPARK_CACHE_DIR", str(cache))
    monkeypatch.setenv("DERGIPARK_SEED_INDEX", str(gz))
    index._default_index = None
    try:
        idx2 = index.get_default_index()
        total, rows = idx2.search(None, "hukuk")
        assert total == 1 and rows[0]["journal_slug"] == "j"
        assert (cache / "index.db").exists()  # gzip çözülüp yazılabilir db'ye yazıldı
    finally:
        if index._default_index is not None:
            index._default_index.close()
        index._default_index = None


def test_no_seed_starts_empty(tmp_path, monkeypatch):
    # Seed yoksa (env var ama dosya yok) → boş indeksle güvenle başlar, çökmez.
    cache = tmp_path / "cache"
    monkeypatch.setenv("DERGIPARK_CACHE_DIR", str(cache))
    monkeypatch.setenv("DERGIPARK_SEED_INDEX", str(tmp_path / "yok.db"))  # deterministik: seed yok
    index._default_index = None
    try:
        idx2 = index.get_default_index()
        assert idx2.search(None, "hukuk") == (0, [])
    finally:
        if index._default_index is not None:
            index._default_index.close()
        index._default_index = None


def test_coverage_complete_flag(idx):
    # mark_harvested complete bayrağını doğru saklamalı
    idx.mark_harvested("test", 4, complete=True)
    assert idx.is_complete("test") is True
    idx.mark_harvested("test", 4, complete=False)
    assert idx.is_complete("test") is False
    # hiç harvest edilmemiş dergi → complete değil
    assert idx.is_complete("bilinmeyen") is False
