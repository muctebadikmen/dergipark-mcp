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
from typing import Iterable

from . import OAI_NAMESPACE, OAI_URL
from . import http

NS = {
    "oai": "http://www.openarchives.org/OAI/2.0/",
    "oai_dc": "http://www.openarchives.org/OAI/2.0/oai_dc/",
    "dc": "http://purl.org/dc/elements/1.1/",
    "xml": "http://www.w3.org/XML/1998/namespace",
}
XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"


class OAIError(Exception):
    """OAI-PMH <error> yanıtı (örn. noRecordsMatch, idDoesNotExist)."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"OAI hatası [{code}]: {message}")


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
    date: str | None = None
    journal: str | None = None
    journal_slug: str | None = None
    publisher: str | None = None
    source: str | None = None
    language: str | None = None
    subjects: list[str] = field(default_factory=list)
    type: str | None = None
    rights: str | None = None

    def to_dict(self) -> dict:
        d = {k: v for k, v in self.__dict__.items() if v not in (None, [], "")}
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
                subjects.append(val)
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
# OAI çağrıları
# --------------------------------------------------------------------------- #

async def _request(params: dict) -> ET.Element:
    text = await http.get_text(OAI_URL, params=params)
    root = ET.fromstring(text.encode("utf-8"))
    _check_error(root)
    return root


async def get_record(numeric_id: str | int) -> Article:
    """Tek bir makalenin tam metadata'sını getirir (GetRecord)."""
    params = {
        "verb": "GetRecord",
        "metadataPrefix": "oai_dc",
        "identifier": article_oai_identifier(numeric_id),
    }
    root = await _request(params)
    record = root.find(".//oai:GetRecord/oai:record", NS)
    if record is None:
        raise OAIError("idDoesNotExist", f"Kayıt bulunamadı: {numeric_id}")
    return parse_record(record)


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
