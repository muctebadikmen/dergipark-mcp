"""Dergi-içi arama — SQLite FTS5 + Türkçe-duyarlı normalizasyon.

DergiPark genel arama API'si sunmaz ve /search robots-yasaklıdır. Bu modül, bir
derginin OAI metadata'sını yerel bir FTS5 indeksine harvest eder ve BM25 ağırlıklı,
Türkçe-duyarlı arama yapar.

Türkçe normalizasyon (``tr_fold``) hem INDEKSE hem SORGUYA **simetrik** uygulanır:
``İ I ı i → i``, ``ş→s ğ→g ü→u ö→o ç→c`` + küçük harf. Böylece "eğitim", "Eğitim",
"egitim" ve "İletişim"/"iletisim" tutarlı eşleşir. unicode61'in Türkçe i/ı
tuhaflıklarına bağımlı kalınmaz (içerik zaten ASCII'ye katlanmış olur).

İndeks ``platformdirs`` cache dizininde kalıcıdır → ikinci arama ağsız ve anında.
"""

from __future__ import annotations

import re
import sqlite3
import time
from pathlib import Path

from .cache import cache_dir

_TR_MAP = str.maketrans({
    "ı": "i", "İ": "i", "I": "i",
    "ş": "s", "Ş": "s",
    "ğ": "g", "Ğ": "g",
    "ü": "u", "Ü": "u",
    "ö": "o", "Ö": "o",
    "ç": "c", "Ç": "c",
})


def tr_fold(s: str | None) -> str:
    """Türkçe-duyarlı katlama: Türkçe harfleri ASCII'ye indirger, küçük harfe çevirir."""
    if not s:
        return ""
    return s.translate(_TR_MAP).casefold()


# Küçük Türkçe/İngilizce stopword listesi. Sorgu terimleriyle aynı (KATLANMIŞ)
# uzayda karşılaştırılması için fold edilmiş tutulur; aksi halde "için" → "icin"
# eşleşmez ve hiç filtrelenmezdi (hata düzeltildi).
_STOPWORDS = {
    tr_fold(w) for w in {
        "ve", "ile", "bir", "bu", "da", "de", "için", "olarak", "the", "of",
        "and", "in", "on", "a", "an", "to", "ya", "veya", "mi", "mu",
    }
}


def _query_terms(query: str) -> list[str]:
    """Sorguyu katlanmış, stopword'süz, FTS5-güvenli terimlere böler."""
    folded = tr_fold(query)
    terms = re.findall(r"\w+", folded, flags=re.UNICODE)
    return [t for t in terms if t not in _STOPWORDS]


class SearchIndex:
    """Dergi-içi FTS5 indeksi. Tek event-loop'ta kullanılmak üzere tasarlanmıştır."""

    def __init__(self, db_path: str | Path | None = None):
        if db_path is None:
            d = cache_dir()
            d.mkdir(parents=True, exist_ok=True)
            db_path = d / "index.db"
        self.db_path = str(db_path)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        c = self._conn
        c.execute(
            """CREATE TABLE IF NOT EXISTS articles(
                rowid INTEGER PRIMARY KEY,
                journal_slug TEXT NOT NULL,
                art_id TEXT NOT NULL,
                title TEXT, title_en TEXT, authors TEXT, abstract TEXT,
                date TEXT, url TEXT, keywords TEXT, article_type TEXT,
                UNIQUE(journal_slug, art_id)
            )"""
        )
        c.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS articles_fts USING fts5("
            "title, keywords, authors, abstract, "
            "content='', tokenize='unicode61 remove_diacritics 1', prefix='2 3 4')"
        )
        c.execute(
            "CREATE TABLE IF NOT EXISTS harvest_meta("
            "journal_slug TEXT PRIMARY KEY, harvested_at REAL, count INTEGER)"
        )
        c.commit()

    # --------------------------------------------------------------- indexing
    def index_articles(self, journal_slug: str, articles: list) -> int:
        """Makaleleri indeksler (yeni olanları). Eklenen yeni kayıt sayısını döndürür."""
        c = self._conn
        new = 0
        for a in articles:
            authors = "; ".join(getattr(a, "authors", []) or [])
            keywords = "; ".join(
                (getattr(a, "keywords", []) or []) + (getattr(a, "subjects", []) or [])
            )
            cur = c.execute(
                "INSERT OR IGNORE INTO articles"
                "(journal_slug,art_id,title,title_en,authors,abstract,date,url,keywords,article_type) "
                "VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    journal_slug, a.id, a.title, a.title_en, authors, a.abstract,
                    a.date, a.url, keywords, getattr(a, "article_type", None) or a.type,
                ),
            )
            if cur.rowcount:
                rid = cur.lastrowid
                c.execute(
                    "INSERT INTO articles_fts(rowid,title,keywords,authors,abstract) VALUES(?,?,?,?,?)",
                    (
                        rid,
                        tr_fold(" ".join(filter(None, [a.title, a.title_en]))),
                        tr_fold(keywords),
                        tr_fold(authors),
                        tr_fold(a.abstract or ""),
                    ),
                )
                new += 1
        c.commit()
        return new

    def mark_harvested(self, journal_slug: str, count: int) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO harvest_meta(journal_slug,harvested_at,count) VALUES(?,?,?)",
            (journal_slug, time.time(), count),
        )
        self._conn.commit()

    def harvested_recently(self, journal_slug: str, ttl: float) -> bool:
        row = self._conn.execute(
            "SELECT harvested_at FROM harvest_meta WHERE journal_slug=?", (journal_slug,)
        ).fetchone()
        return bool(row and row["harvested_at"] and (time.time() - row["harvested_at"]) < ttl)

    def indexed_count(self, journal_slug: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM articles WHERE journal_slug=?", (journal_slug,)
        ).fetchone()
        return int(row["n"]) if row else 0

    # ---------------------------------------------------------------- search
    def search(
        self,
        journal_slug: str,
        query: str,
        *,
        year_from: int | None = None,
        year_to: int | None = None,
        article_type: str | None = None,
        author: str | None = None,
        sort: str = "relevance",
        limit: int = 15,
        offset: int = 0,
    ) -> tuple[int, list[dict]]:
        """FTS5 BM25 (title 5× / keywords 3× / authors 2× / abstract 1×) + recency
        boost + tam-ifade başlık bonusu. ``(total_matched, page_rows)`` döndürür."""
        terms = _query_terms(query)
        if not terms:
            return (0, [])
        match = " ".join(f"{t}*" for t in terms)

        sql = (
            "SELECT a.art_id,a.title,a.title_en,a.authors,a.abstract,a.date,a.url,"
            "a.article_type, bm25(articles_fts,5.0,3.0,2.0,1.0) AS score "
            "FROM articles_fts JOIN articles a ON a.rowid=articles_fts.rowid "
            "WHERE articles_fts MATCH ? AND a.journal_slug=?"
        )
        params: list = [match, journal_slug]
        # Yıl filtresi: tarihin YIL bileşeni üzerinden karşılaştır. (Sözlüksel
        # string karşılaştırması "2021" gibi yıl-tek tarihleri yanlış eler;
        # CAST(substr(...)) sağlamdır — "2021" ve "2021-05-01" ikisi de 2021 olur.)
        if year_from:
            sql += " AND a.date IS NOT NULL AND CAST(substr(a.date,1,4) AS INTEGER) >= ?"
            params.append(int(year_from))
        if year_to:
            sql += " AND a.date IS NOT NULL AND CAST(substr(a.date,1,4) AS INTEGER) <= ?"
            params.append(int(year_to))
        sql += " ORDER BY score LIMIT 3000"

        rows = [dict(r) for r in self._conn.execute(sql, params).fetchall()]

        # Python tarafı filtreler (folding ile)
        if author:
            af = tr_fold(author)
            rows = [r for r in rows if af in tr_fold(r["authors"] or "")]
        if article_type:
            atf = tr_fold(article_type)
            rows = [r for r in rows if atf in tr_fold(r["article_type"] or "")]

        qfold = tr_fold(query)

        def adjusted(r: dict) -> float:
            score = r["score"]  # bm25: küçük (negatif) = daha iyi
            title_f = tr_fold((r["title"] or "") + " " + (r["title_en"] or ""))
            bonus = 0.0
            if qfold and qfold in title_f:
                bonus -= 2.0  # tam ifade başlıkta geçiyor
            y = r["date"][:4] if r["date"] and r["date"][:4].isdigit() else None
            if y:
                bonus -= min(max(int(y) - 2000, 0), 30) * 0.03  # hafif recency
            return score + bonus

        if sort == "newest":
            rows.sort(key=lambda r: (r["date"] or ""), reverse=True)
        elif sort == "oldest":
            rows.sort(key=lambda r: (r["date"] or "9999"))
        else:  # relevance
            rows.sort(key=adjusted)

        total = len(rows)
        page = rows[offset:offset + limit]
        for r in page:
            r.pop("score", None)
        return (total, page)

    def close(self) -> None:
        self._conn.close()


_default_index: SearchIndex | None = None


def get_default_index() -> SearchIndex:
    """Uygulama genelinde paylaşılan kalıcı indeks (lazy)."""
    global _default_index
    if _default_index is None:
        _default_index = SearchIndex()
    return _default_index
