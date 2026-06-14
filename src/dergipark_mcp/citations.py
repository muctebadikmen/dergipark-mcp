"""Akademik atıf biçimlendirme — DergiPark makaleleri için.

Bu modül saf Python standart kütüphanesi ile yazılmıştır (bağımlılık yok).
DergiPark'ın Google-Scholar `citation_*` meta etiketleri ve OAI Dublin Core
üzerinden açığa çıkardığı alanları alıp; makine-okunur (BibTeX, RIS, CSL-JSON)
ve insan-okunur (APA, MLA, IEEE, Chicago, Harvard) atıf çıktıları üretir.

Türkçe karakterler (İ ı ş ğ ü ö ç) insan-okunur çıktılarda, CSL-JSON ve RIS
çıktılarında KORUNUR — yalnızca BibTeX anahtarı ASCII'ye katlanır.

Çok yazarlı (3+) davranışı (tüm fonksiyonlarda tutarlı):
  * APA   : tüm yazarlar listelenir, son yazardan önce "& " kullanılır.
  * MLA   : ilk yazar + "et al." (3+ yazar olduğunda).
  * IEEE  : ilk yazar + "et al." (3+ yazar olduğunda).
  * Chicago: ilk yazar + "et al." (3+ yazar olduğunda).
  * Harvard: tüm yazarlar listelenir, son yazardan önce "and" kullanılır.

Eksik alanlar (yıl/cilt/sayı/sayfa) ilgili parçayı sarkık virgül veya boş
parantez bırakmadan temizce atlanır. Eksik yıl APA/Harvard'da "n.d." olur.
"""

from __future__ import annotations

import html
import re
import unicodedata
from dataclasses import dataclass, field


@dataclass
class CitationData:
    """DergiPark atıf meta verisi.

    Tüm alanlar opsiyoneldir. `authors` "Ad Soyad" sırasında tam isimler
    içerir (örn. "Tunahan Karaarslan"). Yüksek doğruluk gereken durumlarda
    `authors_structured` (given, family) ikilileri verilebilir; verildiğinde
    `authors` yerine bu kullanılır.
    """

    title: str | None = None
    authors: list[str] = field(default_factory=list)
    authors_structured: list[tuple[str, str]] | None = None
    year: str | None = None
    journal: str | None = None
    volume: str | None = None
    issue: str | None = None
    first_page: str | None = None
    last_page: str | None = None
    doi: str | None = None
    url: str | None = None
    issn: str | None = None
    publisher: str | None = None
    article_id: str | None = None


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------

def _clean(value: str | None) -> str | None:
    """HTML entity'lerini çöz, boşlukları normalize et, boşsa None döndür."""
    if value is None:
        return None
    text = html.unescape(str(value))
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def split_name(full_name: str) -> tuple[str, str]:
    """Tam ismi (given, family) olarak böler.

    Sezgisel kural: family = son boşlukla ayrılmış parça, given = öncesi.
    Tek parça varsa family = o parça, given = "".
    Örnekler:
        "Tunahan Karaarslan" -> ("Tunahan", "Karaarslan")
        "Ali Veli Han"       -> ("Ali Veli", "Han")
        "Madonna"            -> ("", "Madonna")
    """
    name = _clean(full_name) or ""
    parts = name.split()
    if not parts:
        return ("", "")
    if len(parts) == 1:
        return ("", parts[0])
    return (" ".join(parts[:-1]), parts[-1])


def _structured(d: CitationData) -> list[tuple[str, str]]:
    """(given, family) ikililerinin listesi; structured override önceliklidir."""
    if d.authors_structured is not None:
        out: list[tuple[str, str]] = []
        for given, family in d.authors_structured:
            out.append(((_clean(given) or ""), (_clean(family) or "")))
        return out
    return [split_name(a) for a in d.authors if _clean(a)]


def _initials(given: str) -> str:
    """Verilen adı baş harflere indirger: "Tunahan" -> "T.", "Ali Veli" -> "A. V.".

    Tireli adları da işler: "Ahmet-Can" -> "A.-C.". Türkçe karakterleri korur.
    """
    given = _clean(given) or ""
    if not given:
        return ""
    pieces: list[str] = []
    for word in given.split():
        # Tireli bileşik adlar için tireyi koruyarak böl.
        sub = [p for p in re.split(r"-", word) if p]
        if not sub:
            continue
        joined = "-".join(f"{p[0]}." for p in sub)
        pieces.append(joined)
    return " ".join(pieces)


def _ascii_fold(text: str) -> str:
    """Türkçe/Unicode karakterleri ASCII'ye katlar (yalnızca BibTeX anahtarı için)."""
    # Türkçe'ye özgü dönüşümler (NFKD bunları kaybedebilir, önce elle eşle).
    mapping = {
        "İ": "I", "ı": "i", "Ş": "S", "ş": "s", "Ğ": "G", "ğ": "g",
        "Ü": "U", "ü": "u", "Ö": "O", "ö": "o", "Ç": "C", "ç": "c",
    }
    text = "".join(mapping.get(ch, ch) for ch in text)
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return ascii_text


def _page_range(d: CitationData, sep: str) -> str | None:
    """Sayfa aralığı; last_page yoksa yalnızca first_page."""
    fp = _clean(d.first_page)
    lp = _clean(d.last_page)
    if fp and lp:
        return f"{fp}{sep}{lp}"
    if fp:
        return fp
    if lp:
        return lp
    return None


# ---------------------------------------------------------------------------
# Makine-okunur biçimler
# ---------------------------------------------------------------------------

def _bibtex_key(d: CitationData) -> str:
    """BibTeX/RIS anahtarı: <soyad><yıl>_<article_id>, ASCII'ye katlanmış."""
    authors = _structured(d)
    year = _clean(d.year) or ""
    aid = _clean(d.article_id)
    if authors:
        family = authors[0][1] or authors[0][0]
        base = _ascii_fold(family).lower()
        base = re.sub(r"[^a-z0-9]", "", base)
        key = f"{base}{year}"
        if aid:
            key = f"{key}_{aid}"
        return key or (f"dergipark{aid}" if aid else "article")
    if aid:
        return f"dergipark{aid}"
    return "article"


def _bibtex_escape(value: str) -> str:
    """BibTeX değer kaçışı — alanlar {} ile sarıldığı için minimal."""
    return value.replace("\\", "\\textbackslash{}").replace("{", "\\{").replace("}", "\\}")


def to_bibtex(d: CitationData) -> str:
    """`@article{...}` BibTeX girdisi döndürür. Yalnızca mevcut alanları yazar.

    author = "Soyad, Ad and Soyad, Ad"; pages = "ilk--son" (en-dash); number = issue.
    """
    authors = _structured(d)
    fields: list[tuple[str, str]] = []

    if authors:
        author_str = " and ".join(
            f"{family}, {given}".rstrip(", ").rstrip() if given else family
            for given, family in authors
        )
        fields.append(("author", author_str))

    title = _clean(d.title)
    if title:
        fields.append(("title", title))

    journal = _clean(d.journal)
    if journal:
        fields.append(("journal", journal))

    year = _clean(d.year)
    if year:
        fields.append(("year", year))

    volume = _clean(d.volume)
    if volume:
        fields.append(("volume", volume))

    issue = _clean(d.issue)
    if issue:
        fields.append(("number", issue))

    pages = _page_range(d, "--")
    if pages:
        fields.append(("pages", pages))

    doi = _clean(d.doi)
    if doi:
        fields.append(("doi", doi))

    url = _clean(d.url)
    if url:
        fields.append(("url", url))

    issn = _clean(d.issn)
    if issn:
        fields.append(("issn", issn))

    publisher = _clean(d.publisher)
    if publisher:
        fields.append(("publisher", publisher))

    key = _bibtex_key(d)
    lines = [f"@article{{{key},"]
    body = [f"  {name} = {{{_bibtex_escape(value)}}}" for name, value in fields]
    lines.append(",\n".join(body))
    lines.append("}")
    return "\n".join(lines)


def to_ris(d: CitationData) -> str:
    """RIS biçimi döndürür. `ER  - ` ile ve sondaki yeni satır ile biter."""
    lines: list[str] = ["TY  - JOUR"]

    for given, family in _structured(d):
        if given:
            lines.append(f"AU  - {family}, {given}")
        else:
            lines.append(f"AU  - {family}")

    title = _clean(d.title)
    if title:
        lines.append(f"TI  - {title}")

    journal = _clean(d.journal)
    if journal:
        lines.append(f"JO  - {journal}")

    year = _clean(d.year)
    if year:
        lines.append(f"PY  - {year}")

    volume = _clean(d.volume)
    if volume:
        lines.append(f"VL  - {volume}")

    issue = _clean(d.issue)
    if issue:
        lines.append(f"IS  - {issue}")

    fp = _clean(d.first_page)
    if fp:
        lines.append(f"SP  - {fp}")

    lp = _clean(d.last_page)
    if lp:
        lines.append(f"EP  - {lp}")

    doi = _clean(d.doi)
    if doi:
        lines.append(f"DO  - {doi}")

    url = _clean(d.url)
    if url:
        lines.append(f"UR  - {url}")

    issn = _clean(d.issn)
    if issn:
        lines.append(f"SN  - {issn}")

    publisher = _clean(d.publisher)
    if publisher:
        lines.append(f"PB  - {publisher}")

    lines.append("ER  - ")
    return "\n".join(lines) + "\n"


def to_csl_json(d: CitationData) -> dict:
    """CSL-JSON öğe sözlüğü döndürür. Eksik alanlar atlanır."""
    item: dict = {"type": "article-journal"}

    title = _clean(d.title)
    if title:
        item["title"] = title

    authors = _structured(d)
    if authors:
        item["author"] = [
            {"given": given, "family": family} if given else {"family": family}
            for given, family in authors
        ]

    journal = _clean(d.journal)
    if journal:
        item["container-title"] = journal

    year = _clean(d.year)
    if year:
        try:
            item["issued"] = {"date-parts": [[int(year)]]}
        except ValueError:
            item["issued"] = {"date-parts": [[year]]}

    volume = _clean(d.volume)
    if volume:
        item["volume"] = volume

    issue = _clean(d.issue)
    if issue:
        item["issue"] = issue

    pages = _page_range(d, "-")
    if pages:
        item["page"] = pages

    doi = _clean(d.doi)
    if doi:
        item["DOI"] = doi

    url = _clean(d.url)
    if url:
        item["URL"] = url

    issn = _clean(d.issn)
    if issn:
        item["ISSN"] = issn

    publisher = _clean(d.publisher)
    if publisher:
        item["publisher"] = publisher

    return item


# ---------------------------------------------------------------------------
# İnsan-okunur biçimler
# ---------------------------------------------------------------------------

def _doi_url(d: CitationData) -> str | None:
    doi = _clean(d.doi)
    if not doi:
        return None
    return f"https://doi.org/{doi}"


def _title_no_period(d: CitationData) -> str | None:
    title = _clean(d.title)
    if not title:
        return None
    return title.rstrip(".")


def format_apa(d: CitationData) -> str:
    """APA 7. baskı atıfı.

    Yazarlar "Soyad, A." biçiminde; çoklu yazarlarda son yazardan önce "& ".
    Eksik yıl "n.d." olur.
    """
    authors = _structured(d)
    author_segment = ""
    if authors:
        formatted = [
            f"{family}, {_initials(given)}".rstrip(", ").rstrip() if given else family
            for given, family in authors
        ]
        if len(formatted) == 1:
            author_segment = formatted[0]
        else:
            author_segment = ", ".join(formatted[:-1]) + ", & " + formatted[-1]

    year = _clean(d.year) or "n.d."
    parts: list[str] = []
    if author_segment:
        parts.append(f"{author_segment.rstrip('.')}.")
    parts.append(f"({year}).")

    title = _title_no_period(d)
    if title:
        parts.append(f"{title}.")

    journal = _clean(d.journal)
    tail = ""
    if journal:
        tail = journal
        vol = _clean(d.volume)
        issue = _clean(d.issue)
        if vol and issue:
            tail += f", {vol}({issue})"
        elif vol:
            tail += f", {vol}"
        pages = _page_range(d, "-")
        if pages:
            tail += f", {pages}"
        parts.append(f"{tail}.")

    citation = " ".join(parts)
    doi_url = _doi_url(d)
    if doi_url:
        citation = f"{citation} {doi_url}"
    return citation


def format_mla(d: CitationData) -> str:
    """MLA 9. baskı atıfı. 3+ yazarda ilk yazar + "et al.".

    İlk yazar "Soyad, Ad", sonrakiler "Ad Soyad". Başlık tırnak içinde.
    """
    authors = _structured(d)
    author_segment = ""
    if authors:
        first_given, first_family = authors[0]
        first = f"{first_family}, {first_given}".strip().rstrip(",") if first_given else first_family
        if len(authors) >= 3:
            author_segment = f"{first}, et al."
        elif len(authors) == 2:
            g2, f2 = authors[1]
            second = f"{g2} {f2}".strip() if g2 else f2
            author_segment = f"{first}, and {second}."
        else:
            author_segment = f"{first}."

    parts: list[str] = []
    if author_segment:
        parts.append(author_segment)

    title = _title_no_period(d)
    if title:
        parts.append(f'"{title}."')

    journal = _clean(d.journal)
    if journal:
        segs = [journal]
        vol = _clean(d.volume)
        if vol:
            segs.append(f"vol. {vol}")
        issue = _clean(d.issue)
        if issue:
            segs.append(f"no. {issue}")
        year = _clean(d.year)
        if year:
            segs.append(year)
        pages = _page_range(d, "-")
        if pages:
            segs.append(f"pp. {pages}")
        parts.append(", ".join(segs) + ".")

    return " ".join(parts)


def format_ieee(d: CitationData) -> str:
    """IEEE atıfı. Yazarlar "A. Soyad"; 3+ yazarda ilk yazar + "et al."."""
    authors = _structured(d)
    author_segment = ""
    if authors:
        def fmt(pair: tuple[str, str]) -> str:
            given, family = pair
            ini = _initials(given)
            return f"{ini} {family}".strip() if ini else family

        if len(authors) >= 3:
            author_segment = f"{fmt(authors[0])} et al."
        elif len(authors) == 2:
            author_segment = f"{fmt(authors[0])} and {fmt(authors[1])}"
        else:
            author_segment = fmt(authors[0])

    parts: list[str] = []
    title = _title_no_period(d)
    if author_segment and title:
        parts.append(f'{author_segment}, "{title},"')
    elif author_segment:
        parts.append(f"{author_segment},")
    elif title:
        parts.append(f'"{title},"')

    tail_segs: list[str] = []
    journal = _clean(d.journal)
    if journal:
        tail_segs.append(journal)
    vol = _clean(d.volume)
    if vol:
        tail_segs.append(f"vol. {vol}")
    issue = _clean(d.issue)
    if issue:
        tail_segs.append(f"no. {issue}")
    pages = _page_range(d, "-")
    if pages:
        tail_segs.append(f"pp. {pages}")
    year = _clean(d.year)
    if year:
        tail_segs.append(year)

    if tail_segs:
        parts.append(", ".join(tail_segs) + ".")
    elif parts:
        # Yalnızca yazar/başlık varsa sondaki virgülü noktaya çevir.
        parts[-1] = parts[-1].rstrip(",") + "."

    return " ".join(parts)


def format_chicago(d: CitationData) -> str:
    """Chicago (kaynakça) atıfı. 3+ yazarda ilk yazar + "et al."."""
    authors = _structured(d)
    author_segment = ""
    if authors:
        first_given, first_family = authors[0]
        first = f"{first_family}, {first_given}".strip().rstrip(",") if first_given else first_family
        if len(authors) >= 3:
            author_segment = f"{first}, et al."
        elif len(authors) == 2:
            g2, f2 = authors[1]
            second = f"{g2} {f2}".strip() if g2 else f2
            author_segment = f"{first}, and {second}."
        else:
            author_segment = f"{first}."

    parts: list[str] = []
    if author_segment:
        parts.append(author_segment)

    title = _title_no_period(d)
    if title:
        parts.append(f'"{title}."')

    journal = _clean(d.journal)
    if journal:
        seg = journal
        vol = _clean(d.volume)
        if vol:
            seg += f" {vol}"
        issue = _clean(d.issue)
        if issue:
            seg += f", no. {issue}"
        year = _clean(d.year)
        if year:
            seg += f" ({year})"
        pages = _page_range(d, "-")
        if pages:
            seg += f": {pages}"
        parts.append(seg + ".")

    return " ".join(parts)


def format_harvard(d: CitationData) -> str:
    """Harvard atıfı. Eksik yıl "n.d." olur; son yazardan önce "and"."""
    authors = _structured(d)
    author_segment = ""
    if authors:
        formatted = [
            f"{family}, {_initials(given)}".rstrip(", ").rstrip() if given else family
            for given, family in authors
        ]
        if len(formatted) == 1:
            author_segment = formatted[0]
        else:
            author_segment = ", ".join(formatted[:-1]) + " and " + formatted[-1]

    year = _clean(d.year) or "n.d."
    parts: list[str] = []
    if author_segment:
        parts.append(author_segment)
    parts.append(f"({year})")

    head = " ".join(parts)

    title = _title_no_period(d)
    segs: list[str] = []
    if title:
        segs.append(f"'{title}'")

    journal = _clean(d.journal)
    if journal:
        vi = journal
        vol = _clean(d.volume)
        issue = _clean(d.issue)
        if vol and issue:
            vi += f", {vol}({issue})"
        elif vol:
            vi += f", {vol}"
        segs.append(vi)

    pages = _page_range(d, "-")
    if pages:
        segs.append(f"pp. {pages}")

    if segs:
        return f"{head}, " + ", ".join(segs) + "."
    return head + "."


_DISPATCH = {
    "apa": format_apa,
    "mla": format_mla,
    "ieee": format_ieee,
    "chicago": format_chicago,
    "harvard": format_harvard,
}


def format_citation(d: CitationData, style: str) -> str:
    """Stil adına göre uygun biçimlendiriciyi çağırır (büyük/küçük harf duyarsız)."""
    key = (style or "").strip().lower()
    if key not in _DISPATCH:
        valid = ", ".join(sorted(_DISPATCH))
        raise ValueError(f"Bilinmeyen atıf stili: {style!r}. Geçerli: {valid}")
    return _DISPATCH[key](d)


def all_citations(d: CitationData) -> dict:
    """Tüm biçimleri tek sözlükte döndürür (8 anahtar)."""
    return {
        "bibtex": to_bibtex(d),
        "ris": to_ris(d),
        "csl_json": to_csl_json(d),
        "apa": format_apa(d),
        "mla": format_mla(d),
        "ieee": format_ieee(d),
        "chicago": format_chicago(d),
        "harvard": format_harvard(d),
    }
