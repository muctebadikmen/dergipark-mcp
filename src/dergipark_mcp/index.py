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

import os
import re
import shutil
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
            "journal_slug TEXT PRIMARY KEY, harvested_at REAL, count INTEGER, complete INTEGER DEFAULT 0)"
        )
        # Eski şemadan göç: 'complete' sütunu yoksa ekle (önbellek dosyası taşınabilir kalsın).
        try:
            c.execute("ALTER TABLE harvest_meta ADD COLUMN complete INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass  # sütun zaten var
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

    def mark_harvested(self, journal_slug: str, count: int, complete: bool = True) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO harvest_meta(journal_slug,harvested_at,count,complete) VALUES(?,?,?,?)",
            (journal_slug, time.time(), count, 1 if complete else 0),
        )
        self._conn.commit()

    def harvested_recently(self, journal_slug: str, ttl: float) -> bool:
        row = self._conn.execute(
            "SELECT harvested_at FROM harvest_meta WHERE journal_slug=?", (journal_slug,)
        ).fetchone()
        return bool(row and row["harvested_at"] and (time.time() - row["harvested_at"]) < ttl)

    def is_complete(self, journal_slug: str) -> bool:
        """Bu dergi için son harvest, derginin TAMAMINI kapsadı mı (cap'e takılmadı mı)?"""
        row = self._conn.execute(
            "SELECT complete FROM harvest_meta WHERE journal_slug=?", (journal_slug,)
        ).fetchone()
        return bool(row and row["complete"])

    def indexed_count(self, journal_slug: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM articles WHERE journal_slug=?", (journal_slug,)
        ).fetchone()
        return int(row["n"]) if row else 0

    def indexed_journals(self) -> list[dict]:
        """İndekste (havuzda) bulunan dergiler: ``slug`` + makale ``count`` +
        ``complete`` (tam kapsam). Dergiler-arası aramanın kapsamını dürüstçe
        bildirmek için kullanılır. En çok makaleli dergi başta."""
        rows = self._conn.execute(
            "SELECT a.journal_slug AS slug, COUNT(*) AS n, COALESCE(m.complete,0) AS complete "
            "FROM articles a LEFT JOIN harvest_meta m ON m.journal_slug=a.journal_slug "
            "GROUP BY a.journal_slug ORDER BY n DESC, a.journal_slug"
        ).fetchall()
        return [{"slug": r["slug"], "count": int(r["n"]), "complete": bool(r["complete"])} for r in rows]

    # ---------------------------------------------------------------- search
    def search(
        self,
        journal_slug: str | None,
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
        boost + tam-ifade başlık bonusu. ``(total_matched, page_rows)`` döndürür.

        ``journal_slug`` bir slug ise yalnız o dergide; ``None`` ise indekslenmiş
        TÜM dergilerde (havuz) arar. Sonuç satırları her durumda ``journal_slug``
        taşır."""
        terms = _query_terms(query)
        if not terms:
            return (0, [])
        match = " ".join(f"{t}*" for t in terms)

        sql = (
            "SELECT a.art_id,a.journal_slug,a.title,a.title_en,a.authors,a.abstract,a.date,a.url,"
            "a.article_type,a.keywords, bm25(articles_fts,5.0,3.0,2.0,1.0) AS score "
            "FROM articles_fts JOIN articles a ON a.rowid=articles_fts.rowid "
            "WHERE articles_fts MATCH ?"
        )
        params: list = [match]
        if journal_slug is not None:
            sql += " AND a.journal_slug=?"
            params.append(journal_slug)
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

        # Sıralama sinyalleri. Eşleşme kümesi (AND-of-prefix) DEĞİŞMEZ; yalnızca
        # sıralama iyileşir. ``phrase`` = stopword'süz katlanmış terimlerin ardışık
        # ifadesi (örn. "hukuk tarihi"); qfold yerine bunu kullanırız ki araya giren
        # durak-kelimeler ("hukuk ve tarihi") tam-ifade eşleşmesini bozmasın.
        phrase = " ".join(terms)
        multi = len(terms) >= 2

        def adjusted(r: dict) -> float:
            score = r["score"]  # bm25: küçük (negatif) = daha iyi
            title_f = tr_fold((r["title"] or "") + " " + (r["title_en"] or ""))
            bonus = 0.0
            # Tam-ifade (phrase) bonusu — en güçlü sinyal başlıkta, sonra anahtar
            # kelime, sonra özet. Tek terimde eski davranış korunur (-2.0 başlık).
            if phrase and phrase in title_f:
                bonus -= 4.0 if multi else 2.0
            elif multi and phrase in tr_fold(r["keywords"] or ""):
                bonus -= 2.5
            elif multi and phrase in tr_fold(r["abstract"] or ""):
                bonus -= 1.5
            # Başlıkta kaç AYRI sorgu terimi geçiyor (konusallık). Tek bir ortak
            # terimle gelen gürültüyü (ör. "Karar Tarihi"de yalnız "tarihi") gerçek
            # çok-terimli başlıkların altına iter.
            if multi:
                bonus -= 0.7 * sum(1 for t in terms if t in title_f)
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
            r.pop("keywords", None)  # yalnız sıralama içindi; sonuç şeklini kirletmesin
        return (total, page)

    def close(self) -> None:
        self._conn.close()


_default_index: SearchIndex | None = None


def _seed_index_path() -> Path | None:
    """Bake'lenmiş seed indeksinin yolu (varsa). Önce ``DERGIPARK_SEED_INDEX`` env'i
    (verilmişse YALNIZ o; yoksa None), aksi halde pakete gömülü ``data/seed_index.db``.
    Dosya yoksa/boşsa None."""
    override = os.environ.get("DERGIPARK_SEED_INDEX")
    candidates = [Path(override)] if override else [Path(__file__).parent / "data" / "seed_index.db"]
    for p in candidates:
        try:
            if p.exists() and p.stat().st_size > 0:
                return p
        except OSError:
            continue
    return None


def get_default_index() -> SearchIndex:
    """Uygulama genelinde paylaşılan kalıcı indeks (lazy).

    İlk kullanımda çalışma indeksi (``cache_dir/index.db``) henüz YOKSA ve bir
    bake'lenmiş seed indeksi mevcutsa, seed YAZILABİLİR konuma kopyalanır →
    dergiler-arası arama ilk istekte sıcak olur; on-demand harvest yine ekleyebilir.
    Mevcut bir çalışma indeksi varsa asla üzerine yazılmaz (yerel veriyi korur).
    """
    global _default_index
    if _default_index is None:
        d = cache_dir()
        d.mkdir(parents=True, exist_ok=True)
        target = d / "index.db"
        if not target.exists():
            seed = _seed_index_path()
            if seed is not None:
                try:
                    shutil.copy2(seed, target)
                except OSError:
                    pass  # kopyalanamazsa boş indeksle güvenle devam et (bozma)
        _default_index = SearchIndex()
    return _default_index
