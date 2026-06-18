"""DergiPark OAI-PMH istemcisi ve Dublin Core ayrıştırıcısı.

Endpoint: https://dergipark.org.tr/api/public/oai/
Doğrulanan davranışlar (canlı):
  * ListSets  -> en fazla 100 dergi (resumptionToken YOK -> kısmi dizin)
  * ListIdentifiers / ListRecords -> sayfa başına 100 kayıt, base64 resumptionToken
  * GetRecord -> tam Dublin Core (oai_dc)
  * identifier şeması: oai:dergipark.org.tr:article/<id>  (record/<id> de kabul edilir)
"""

from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from . import OAI_NAMESPACE, OAI_URL, http
from .cache import default_cache

# Önbellek TTL'leri (saniye). Metadata nadiren değişir → uzun tutulur.
_RECORD_TTL = 24 * 3600

NS = {
    "oai": "http://www.openarchives.org/OAI/2.0/",
    "oai_dc": "http://www.openarchives.org/OAI/2.0/oai_dc/",
    "dc": "http://purl.org/dc/elements/1.1/",
    "mods": "http://www.loc.gov/mods/v3",
    "xml": "http://www.w3.org/XML/1998/namespace",
}
XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"


class OAIError(Exception):
    """OAI-PMH <error> yanıtı (örn. noRecordsMatch, idDoesNotExist)."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"OAI hatası [{code}]: {message}")


@dataclass
class Author:
    """Yapısal yazar (oai_mods given/family + HTML afiliasyon/ORCID)."""

    name: str                       # tam ad, "Ad Soyad" sırası
    given: str | None = None
    family: str | None = None
    affiliation: str | None = None
    orcid: str | None = None

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v not in (None, "")}


@dataclass
class Article:
    id: str
    oai_identifier: str
    url: str | None = None
    persistent_id: str | None = None
    title: str | None = None
    title_en: str | None = None
    authors: list[str] = field(default_factory=list)
    abstract: str | None = None
    abstract_en: str | None = None
    date: str | None = None
    journal: str | None = None
    journal_slug: str | None = None
    publisher: str | None = None
    source: str | None = None
    language: str | None = None
    subjects: list[str] = field(default_factory=list)
    type: str | None = None
    rights: str | None = None
    # --- Yapısal bibliyografik alanlar (oai_mods + makale HTML ile dolar) ---
    authors_detailed: list[Author] = field(default_factory=list)
    volume: str | None = None
    issue: str | None = None
    first_page: str | None = None
    last_page: str | None = None
    doi: str | None = None
    issn: str | None = None
    keywords: list[str] = field(default_factory=list)
    article_type: str | None = None

    def to_dict(self) -> dict:
        d: dict = {}
        for k, v in self.__dict__.items():
            if v in (None, [], ""):
                continue
            if k == "authors_detailed":
                d[k] = [a.to_dict() for a in v]
            else:
                d[k] = v
        return d


@dataclass
class Journal:
    slug: str
    name: str


# --------------------------------------------------------------------------- #
# Yardımcılar
# --------------------------------------------------------------------------- #

def _clean(text: str | None) -> str | None:
    if text is None:
        return None
    # DergiPark, CDATA içine HTML entity'leri gömer (örn. "TBMM&#039;nin").
    # CDATA bunları çözmez; bu yüzden burada çözüyoruz.
    text = html.unescape(text).strip()
    return text or None


# Bazı DergiPark kayıtları anahtar kelime/konu değerinin başına etiketi ("Anahtar
# Kelimeler:") ya da başıboş bir ":" bırakır (gözlemlenen: dc:subject = ": Kagan").
# Görünür künyeyi (subjects/keywords) temiz tutmak için bunları ayıklarız.
_KW_LABEL_RE = re.compile(
    r"^\s*(anahtar\s*(?:kelimeler|kelime|sözcükler|sözcük)|key\s*words?|keywords?)\b\s*:?\s*",
    re.IGNORECASE,
)


def normalize_keyword(term: str | None) -> str | None:
    """Anahtar kelime/konu değerini temizler: baştaki etiket ('Anahtar Kelimeler:')
    ve kenardaki başıboş noktalama (':', ';', ',') atılır. Boşsa None döner."""
    if not term:
        return None
    t = _KW_LABEL_RE.sub("", term).strip().strip(":;,").strip()
    return t or None


def _check_error(root: ET.Element) -> None:
    err = root.find("oai:error", NS)
    if err is not None:
        raise OAIError(err.get("code", "unknown"), (err.text or "").strip())


def article_oai_identifier(numeric_id: str | int) -> str:
    return f"oai:{OAI_NAMESPACE}:article/{numeric_id}"


def _numeric_id_from_identifier(identifier: str) -> str:
    m = re.search(r"(?:article|record)/(\d+)", identifier)
    return m.group(1) if m else identifier


def _slug_from_url(url: str | None) -> str | None:
    if not url:
        return None
    m = re.search(r"/pub/([^/]+)/", url)
    return m.group(1) if m else None


# --------------------------------------------------------------------------- #
# Kayıt ayrıştırma
# --------------------------------------------------------------------------- #

def parse_record(record: ET.Element) -> Article:
    """Bir OAI <record> elemanını Article'a çevirir."""
    header = record.find("oai:header", NS)
    identifier = ""
    set_specs: list[str] = []
    if header is not None:
        identifier = _clean(header.findtext("oai:identifier", default="", namespaces=NS)) or ""
        set_specs = [
            s.text.strip() for s in header.findall("oai:setSpec", NS) if s.text and s.text.strip()
        ]

    dc = record.find(".//oai_dc:dc", NS)
    titles: list[tuple[str | None, str]] = []
    authors: list[str] = []
    identifiers: list[str] = []
    subjects: list[str] = []
    description = publisher = date = source = language = rights = dtype = None

    if dc is not None:
        for el in dc:
            tag = el.tag.split("}", 1)[-1]
            val = _clean(el.text)
            if val is None and tag not in ("title",):
                continue
            if tag == "title":
                titles.append((el.get(XML_LANG), val or ""))
            elif tag == "creator":
                authors.append(val)
            elif tag == "identifier":
                identifiers.append(val)
            elif tag == "subject":
                sv = normalize_keyword(val)
                if sv:
                    subjects.append(sv)
            elif tag == "description" and description is None:
                description = val
            elif tag == "publisher" and publisher is None:
                publisher = val
            elif tag == "date" and date is None:
                date = val
            elif tag == "source" and source is None:
                source = val
            elif tag == "language" and language is None:
                language = val
            elif tag == "rights" and rights is None:
                rights = val
            elif tag == "type" and dtype is None:
                dtype = val

    # Başlık: önce tr-TR, sonra ilk dolu olan
    title = title_en = None
    for lang, val in titles:
        if not val:
            continue
        if lang and lang.lower().startswith("tr"):
            title = title or val
        elif lang and lang.lower().startswith("en"):
            title_en = title_en or val
    if title is None:
        title = next((v for _, v in titles if v), None)

    url = next((i for i in identifiers if "dergipark.org.tr" in i), None)
    persistent = next(
        (i for i in identifiers if "izlik.org" in i or i.lower().startswith("doi") or "doi.org" in i),
        None,
    )

    numeric = _numeric_id_from_identifier(identifier)
    slug = _slug_from_url(url)
    if slug is None and set_specs and not set_specs[0].isdigit():
        slug = set_specs[0]

    return Article(
        id=numeric,
        oai_identifier=identifier or article_oai_identifier(numeric),
        url=url,
        persistent_id=persistent,
        title=title,
        title_en=title_en,
        authors=authors,
        abstract=description,
        date=date,
        journal=_journal_from_source(source),
        journal_slug=slug,
        publisher=publisher,
        source=source,
        language=language,
        subjects=subjects,
        type=(dtype.split("/")[-1] if dtype else None),
        rights=rights,
    )


def _journal_from_source(source: str | None) -> str | None:
    if not source:
        return None
    # "Mülkiye Dergisi, Vol. 29 No. 247" -> "Mülkiye Dergisi"
    return source.split(",")[0].strip() or None


# --------------------------------------------------------------------------- #
# oai_mods ayrıştırma — yapısal yazar (given/family) + cilt/sayı/sayfa
# --------------------------------------------------------------------------- #

def parse_mods_record(record: ET.Element) -> Article:
    """Bir oai_mods <record> elemanını Article'a çevirir.

    oai_dc'ye göre üstünlüğü: yazar adlarını given/family olarak ayrıştırılmış,
    cilt/sayı/sayfa bilgisini yapısal verir. (Eski kayıtlarda <abstract> olmayabilir;
    özet için oai_dc daha güvenilirdir.)
    """
    header = record.find("oai:header", NS)
    identifier = ""
    set_specs: list[str] = []
    if header is not None:
        identifier = _clean(header.findtext("oai:identifier", default="", namespaces=NS)) or ""
        set_specs = [
            s.text.strip() for s in header.findall("oai:setSpec", NS) if s.text and s.text.strip()
        ]

    mods = record.find(".//mods:mods", NS)

    title = title_en = None
    authors: list[str] = []
    authors_detailed: list[Author] = []
    abstract = abstract_en = None
    date = publisher = language = journal = None
    volume = issue = first_page = last_page = None
    doi = url = persistent = article_type = None
    subjects: list[str] = []

    if mods is not None:
        # Başlıklar (xml:lang ile tr/en)
        for ti in mods.findall("mods:titleInfo", NS):
            lang = (ti.get(XML_LANG) or "").lower()
            t = _clean(ti.findtext("mods:title", default="", namespaces=NS))
            if not t:
                continue
            if lang.startswith("tr"):
                title = title or t
            elif lang.startswith("en"):
                title_en = title_en or t
            elif title is None:
                title = t

        # Yazarlar (name[type=personal], roleTerm=author)
        for name in mods.findall("mods:name", NS):
            if name.get("type") not in (None, "personal"):
                continue
            roles = [
                (r.text or "").strip().lower()
                for r in name.findall("mods:role/mods:roleTerm", NS)
            ]
            if roles and "author" not in roles:
                continue
            given = family = None
            extra_parts: list[str] = []
            for np in name.findall("mods:namePart", NS):
                t = (np.get("type") or "").lower()
                val = _clean(np.text)
                if not val:
                    continue
                if t == "given":
                    given = val
                elif t == "family":
                    family = val
                else:
                    extra_parts.append(val)
            full = " ".join(p for p in [given, family] if p) or " ".join(extra_parts)
            if not full:
                continue
            authors.append(full)
            authors_detailed.append(Author(name=full, given=given, family=family))

        origin = mods.find("mods:originInfo", NS)
        if origin is not None:
            date = _clean(origin.findtext("mods:dateIssued", default="", namespaces=NS)) or date
            publisher = _clean(origin.findtext("mods:publisher", default="", namespaces=NS)) or publisher

        lt = mods.find("mods:language/mods:languageTerm", NS)
        if lt is not None:
            language = _clean(lt.text) or language

        for ident in mods.findall("mods:identifier", NS):
            val = _clean(ident.text)
            if not val:
                continue
            if "dergipark.org.tr" in val and url is None:
                url = val
            elif "izlik.org" in val and persistent is None:
                persistent = val
            elif ("doi.org" in val or val.lower().startswith("10.")) and doi is None:
                doi = val.replace("https://doi.org/", "").replace("http://doi.org/", "")
        if url is None:
            loc = mods.find("mods:location/mods:url", NS)
            if loc is not None:
                url = _clean(loc.text)

        genre = mods.find("mods:genre", NS)
        if genre is not None:
            article_type = _clean(genre.text)

        abstract = _clean(mods.findtext("mods:abstract", default="", namespaces=NS)) or None

        host = mods.find("mods:relatedItem[@type='host']", NS)
        if host is not None:
            journal = _clean(host.findtext("mods:titleInfo/mods:title", default="", namespaces=NS)) or journal
            part = host.find("mods:part", NS)
            if part is not None:
                for detail in part.findall("mods:detail", NS):
                    dt = detail.get("type")
                    num = _clean(detail.findtext("mods:number", default="", namespaces=NS))
                    if dt == "volume":
                        volume = num
                    elif dt == "issue":
                        issue = num
                extent = part.find("mods:extent", NS)
                if extent is not None:
                    first_page = _clean(extent.findtext("mods:start", default="", namespaces=NS))
                    last_page = _clean(extent.findtext("mods:end", default="", namespaces=NS))

        for subj in mods.findall("mods:subject/mods:topic", NS):
            v = normalize_keyword(_clean(subj.text))
            if v:
                subjects.append(v)

    numeric = _numeric_id_from_identifier(identifier)
    slug = _slug_from_url(url)
    if slug is None and set_specs and not set_specs[0].isdigit():
        slug = set_specs[0]

    return Article(
        id=numeric,
        oai_identifier=identifier or article_oai_identifier(numeric),
        url=url,
        persistent_id=persistent,
        title=title,
        title_en=title_en,
        authors=authors,
        abstract=abstract,
        abstract_en=abstract_en,
        date=date,
        journal=journal,
        journal_slug=slug,
        publisher=publisher,
        language=language,
        subjects=subjects,
        type=article_type,
        authors_detailed=authors_detailed,
        volume=volume,
        issue=issue,
        first_page=first_page,
        last_page=last_page,
        doi=doi,
        article_type=article_type,
    )


def merge_article(base: Article, extra: Article) -> Article:
    """``base``'in boş/None alanlarını ``extra``'dan doldurur (base önceliklidir).

    Yazar listelerinde: ``base.authors`` doluysa korunur; ``authors_detailed``
    için daha zengin (given/family/affiliation/orcid içeren) olan tercih edilir.
    """
    scalar_fields = (
        "url", "persistent_id", "title", "title_en", "abstract", "abstract_en",
        "date", "journal", "journal_slug", "publisher", "source", "language",
        "type", "rights", "volume", "issue", "first_page", "last_page",
        "doi", "issn", "article_type",
    )
    for f in scalar_fields:
        if not getattr(base, f, None) and getattr(extra, f, None):
            setattr(base, f, getattr(extra, f))
    for f in ("authors", "subjects", "keywords"):
        if not getattr(base, f) and getattr(extra, f):
            setattr(base, f, list(getattr(extra, f)))
    # authors_detailed: hangisinde daha çok bilgi (orcid/affil) varsa onu seç
    def _detail_score(lst: list[Author]) -> int:
        return sum(bool(a.orcid) + bool(a.affiliation) + bool(a.given) for a in lst)
    if _detail_score(extra.authors_detailed) > _detail_score(base.authors_detailed):
        base.authors_detailed = extra.authors_detailed
    return base


# --------------------------------------------------------------------------- #
# OAI çağrıları
# --------------------------------------------------------------------------- #

async def _request(params: dict, *, cache_key: str | None = None, ttl: float | None = None) -> ET.Element:
    """OAI isteği → kök eleman. ``cache_key`` verilirse başarılı yanıt önbelleğe alınır.

    OAI <error> (örn. idDoesNotExist) içeren yanıtlar önbelleğe ALINMAZ — factory
    içinde hata yükseltilir, böylece ``get_or_compute`` değeri saklamaz.
    """
    if cache_key is None:
        text = await http.get_text(OAI_URL, params=params)
        root = ET.fromstring(text.encode("utf-8"))
        _check_error(root)
        return root

    async def factory() -> str:
        t = await http.get_text(OAI_URL, params=params)
        r = ET.fromstring(t.encode("utf-8"))
        _check_error(r)  # hata varsa yükselt → önbelleğe yazılmaz
        return t

    text = await default_cache.get_or_compute(cache_key, factory, ttl=ttl)
    root = ET.fromstring(text.encode("utf-8"))
    _check_error(root)
    return root


async def get_record(numeric_id: str | int, metadata_prefix: str = "oai_dc") -> Article:
    """Tek bir makalenin tam metadata'sını getirir (GetRecord).

    ``metadata_prefix``: "oai_dc" (varsayılan; özet/konu/lisans için güvenilir) ya da
    "oai_mods" (yapısal yazar given/family + cilt/sayı/sayfa).
    """
    params = {
        "verb": "GetRecord",
        "metadataPrefix": metadata_prefix,
        "identifier": article_oai_identifier(numeric_id),
    }
    root = await _request(
        params, cache_key=f"getrecord:{metadata_prefix}:{numeric_id}", ttl=_RECORD_TTL
    )
    record = root.find(".//oai:GetRecord/oai:record", NS)
    if record is None:
        raise OAIError("idDoesNotExist", f"Kayıt bulunamadı: {numeric_id}")
    return parse_mods_record(record) if metadata_prefix == "oai_mods" else parse_record(record)


async def get_record_merged(numeric_id: str | int) -> Article:
    """oai_dc (özet/konu) + oai_mods (yapısal yazar/cilt/sayı) birleşimi.

    İki OAI isteği yapar; sonuçlar önbelleklenir. Özet oai_dc'den, yapısal
    bibliyografik alanlar oai_mods'tan gelir.
    """
    dc = await get_record(numeric_id, "oai_dc")
    try:
        mods = await get_record(numeric_id, "oai_mods")
    except OAIError:
        return dc
    return merge_article(dc, mods)


async def list_records(
    journal_slug: str,
    *,
    from_date: str | None = None,
    until_date: str | None = None,
    max_records: int = 100,
) -> list[Article]:
    """Bir derginin makalelerini listeler (ListRecords + resumptionToken).

    ``max_records`` toplam üst sınırdır; sayfalar otomatik dolaşılır.
    """
    out: list[Article] = []
    params: dict = {
        "verb": "ListRecords",
        "metadataPrefix": "oai_dc",
        "set": journal_slug,
    }
    if from_date:
        params["from"] = from_date
    if until_date:
        params["until"] = until_date

    while len(out) < max_records:
        try:
            root = await _request(params)
        except OAIError as exc:
            if exc.code == "noRecordsMatch":
                break
            raise
        for record in root.findall(".//oai:ListRecords/oai:record", NS):
            out.append(parse_record(record))
            if len(out) >= max_records:
                break
        token_el = root.find(".//oai:resumptionToken", NS)
        token = (token_el.text or "").strip() if token_el is not None else ""
        if not token:
            break
        params = {"verb": "ListRecords", "resumptionToken": token}

    return out[:max_records]


async def list_journals() -> list[Journal]:
    """OAI ListSets'ten dergileri döndürür (kısmi dizin: ~100 dergi).

    Not: DergiPark ListSets için resumptionToken vermez; bu yüzden tam dizin
    OAI üzerinden alınamaz. Herhangi bir dergiye slug ile erişilebilir.
    """
    params = {"verb": "ListSets"}
    root = await _request(params)
    journals: list[Journal] = []
    for s in root.findall(".//oai:ListSets/oai:set", NS):
        spec = _clean(s.findtext("oai:setSpec", default="", namespaces=NS)) or ""
        name = _clean(s.findtext("oai:setName", default="", namespaces=NS)) or spec
        if spec and not spec.isdigit():
            journals.append(Journal(slug=spec, name=name))
    return journals
