"""PDF indirme ve metne/Markdown'a dönüştürme.

Dijital (metin katmanı olan) PDF'ler için pypdf ile sayfa-bazlı metin çıkarımı.
Taranmış (görüntü) ya da bozuk-font PDF'lerde metin güvenilmezdir; bu durumda
DÜRÜSTÇE ``text_reliable=False`` döner. OCR YAPILMAZ: ücretsiz, anahtarsız ve
herkes için sürtünmesiz bir OCR yolu (sistem ikilisi gerektirmeyen) bulunmadığından
bilinçli olarak kapsam dışıdır — bkz. README.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

from pypdf import PdfReader

from . import http

# Türkçe + yaygın Batı Avrupa harfleri. Bazı bozuk PDF fontları (düzgün ToUnicode
# CMap'i olmayan) gerçek harfleri egzotik Latin-Extended glyph'lerine (ů ŵ Ă ǌ Ŧ …)
# eşler; bunlar teknik olarak "Latin"dir ama Türkçe/İngilizce'de geçmez. Bu yüzden
# "beklenen karakter" kümesine göre oran bakarız.
EXPECTED_LETTERS = set(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "çğıİöşüÇĞÖŞÜ"
    "àáâäãåèéêëìíîïòóôöõùúûüñýÿæœøÀÁÂÄÃÅÈÉÊËÌÍÎÏÒÓÔÖÕÙÚÛÜÑ"
)
# Oran bu eşiğin altındaysa metin büyük olasılıkla bozuk/yanlış kodlanmıştır.
READABLE_RATIO_THRESHOLD = 0.80

MAX_PDF_BYTES = 80 * 1024 * 1024  # 80 MB güvenlik sınırı


@dataclass
class ExtractedPDF:
    source_url: str
    page_count: int
    pages: list[str] = field(default_factory=list)
    markdown: str = ""
    has_text: bool = True
    text_reliable: bool = True
    note: str | None = None
    sections: list[dict] = field(default_factory=list)
    start_page: int = 1
    end_page: int = 0
    has_more_pages: bool = False


# Bölüm başlıkları (Türkçe + İngilizce). Satır, opsiyonel numaralandırmadan sonra
# bu anahtarlardan birine eşitse bölüm sınırı sayılır.
_SECTION_KEYWORDS = {
    "OZ", "OZET", "ABSTRACT", "EXTENDED ABSTRACT", "GENISLETILMIS OZET",
    "GIRIS", "INTRODUCTION",
    "LITERATUR", "LITERATURE REVIEW", "KAVRAMSAL CERCEVE", "KURAMSAL CERCEVE",
    "YONTEM", "YONTEMLER", "MATERYAL VE YONTEM", "GEREC VE YONTEM", "ARASTIRMA YONTEMI",
    "METHOD", "METHODS", "METHODOLOGY", "MATERIALS AND METHODS", "MATERIAL AND METHODS",
    "BULGULAR", "RESULTS", "FINDINGS", "RESULTS AND DISCUSSION", "BULGULAR VE TARTISMA",
    "TARTISMA", "DISCUSSION",
    "SONUC", "SONUCLAR", "SONUC VE ONERILER", "CONCLUSION", "CONCLUSIONS",
    "CONCLUSION AND RECOMMENDATIONS", "ONERILER", "RECOMMENDATIONS",
    "TESEKKUR", "ACKNOWLEDGEMENT", "ACKNOWLEDGEMENTS", "ACKNOWLEDGMENTS",
    "KAYNAKCA", "KAYNAKLAR", "REFERANSLAR", "REFERENCES", "BIBLIOGRAPHY",
}


def _fold_upper(s: str) -> str:
    """Türkçe-duyarlı büyük-harf katlama: ı/İ/ş/ğ/ü/ö/ç → I/I/S/G/U/O/C, sonra upper."""
    table = str.maketrans({
        "ı": "i", "İ": "i", "ş": "s", "ğ": "g", "ü": "u", "ö": "o", "ç": "c",
        "Ş": "S", "Ğ": "G", "Ü": "U", "Ö": "O", "Ç": "C", "I": "I",
    })
    return s.translate(table).upper()


def _heading_if_any(line: str) -> str | None:
    """Satır bir bölüm başlığıysa (numaralandırma toleranslı) orijinal satırı döndürür."""
    stripped = line.strip()
    if not stripped or len(stripped) > 60:
        return None
    # Baştaki "1.", "1.2", "I.", "A)" gibi numaralandırmayı at.
    core = re.sub(r"^\s*([0-9]+([.\)][0-9]*)*|[IVXLC]+|[A-Da-d])[.\)]\s*", "", stripped).strip()
    if _fold_upper(core) in _SECTION_KEYWORDS:
        return stripped
    return None


def split_sections(text: str) -> list[dict]:
    """Düz metni bölümlere ayırır (en iyi çaba). ``[{heading, text}]`` döndürür.

    Hiç başlık bulunamazsa boş liste döner (markdown yine tam metni içerir).
    """
    sections: list[dict] = []
    cur_head: str | None = None
    cur: list[str] = []
    found_any = False
    for line in text.split("\n"):
        h = _heading_if_any(line)
        if h is not None:
            body = "\n".join(cur).strip()
            if cur_head is not None or body:
                sections.append({"heading": cur_head or "(başlık öncesi)", "text": body})
            cur_head = h
            cur = []
            found_any = True
        else:
            cur.append(line)
    if found_any:
        body = "\n".join(cur).strip()
        if cur_head is not None or body:
            sections.append({"heading": cur_head or "(başlık öncesi)", "text": body})
    return [s for s in sections if s["text"]]


def readable_ratio(text: str, sample: int = 3000) -> float:
    """Alfabetik karakterler içinde "beklenen" (Türkçe/Batı Avrupa) harf oranı.

    Düzgün metinde ~1.0; yanlış kodlanmış (bozuk font) metinde belirgin düşer
    (gerçek dünyada temiz ~1.00, bozuk ~0.11). Hız için ilk ``sample`` alfabetik
    karakter örneklenir.
    """
    letters: list[str] = []
    for ch in text:
        if ch.isalpha():
            letters.append(ch)
            if len(letters) >= sample:
                break
    if not letters:
        return 1.0
    good = sum(1 for ch in letters if ch in EXPECTED_LETTERS)
    return good / len(letters)


def _normalize(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Satır sonu tireleme birleştirme: "kelime-\ndevam" -> "kelimedevam"
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    # Aşırı boş satırları sadeleştir
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract(
    data: bytes,
    source_url: str,
    max_pages: int | None = None,
    start_page: int = 1,
) -> ExtractedPDF:
    """PDF'ten metin çıkarır. ``start_page`` (1-tabanlı) ve ``max_pages`` ile
    uzun belgeler sayfa-sayfa gezilebilir (araç-içi sayfalama)."""
    reader = PdfReader(io.BytesIO(data))
    total = len(reader.pages)

    start_idx = max(0, start_page - 1)
    end_idx = total if max_pages is None else min(start_idx + max_pages, total)
    start_idx = min(start_idx, total)

    pages: list[str] = []
    for i in range(start_idx, end_idx):
        try:
            raw = reader.pages[i].extract_text() or ""
        except Exception as exc:  # bozuk sayfa tek tek atlanır
            pages.append(f"[sayfa {i + 1} çıkarılamadı: {exc}]")
            continue
        pages.append(_normalize(raw))

    body = "\n\n".join(
        f"## Sayfa {start_idx + i + 1}\n\n{txt}" if txt
        else f"## Sayfa {start_idx + i + 1}\n\n_(boş veya görüntü)_"
        for i, txt in enumerate(pages)
    )
    full_text = "\n".join(pages)
    # Taranmış (görüntü) PDF'ler ~0 karakter verir; gerçek metin katmanı yüzlerce+.
    has_text = sum(len(p.strip()) for p in pages) > 10
    has_more = end_idx < total
    text_reliable = True
    note = None
    if not has_text:
        if start_idx > 0 or has_more:
            note = (
                f"Çekilen sayfa aralığında ({start_idx + 1}-{end_idx}/{total}) anlamlı metin yok. "
                "Aralığı genişletin/kaydırın (start_page, max_pages); ya da belge taranmış olabilir."
            )
        else:
            note = (
                "Bu PDF'ten metin çıkarılamadı — büyük olasılıkla taranmış (görüntü) bir belge. "
                "Dürüstçe belirtmek gerekir ki güvenilir metin elde edilemedi (OCR yapılmaz)."
            )
    else:
        ratio = readable_ratio(full_text)
        if ratio < READABLE_RATIO_THRESHOLD:
            text_reliable = False
            note = (
                f"DİKKAT: Çıkarılan metin güvenilir DEĞİL (okunabilir karakter oranı %{ratio * 100:.0f}). "
                "PDF fontu düzgün Unicode (ToUnicode) eşlemesi içermiyor; çıkarılan metin bozuk/anlamsız. "
                "Bu metne güvenmeyin — makaleyi orijinal kaynağından okuyun."
            )

    sections = split_sections(full_text) if (has_text and text_reliable) else []

    header = (
        f"# Tam metin (PDF)\n\nKaynak: {source_url}\n"
        f"Sayfa aralığı: {start_idx + 1}-{end_idx} / {total}\n\n---\n\n"
    )
    return ExtractedPDF(
        source_url=source_url,
        page_count=total,
        pages=pages,
        markdown=header + body,
        has_text=has_text,
        text_reliable=text_reliable,
        note=note,
        sections=sections,
        start_page=start_idx + 1,
        end_page=end_idx,
        has_more_pages=has_more,
    )


async def download_and_extract(
    pdf_url: str, max_pages: int | None = None, start_page: int = 1
) -> ExtractedPDF:
    resp = await http.get(pdf_url)
    data = resp.content
    if len(data) > MAX_PDF_BYTES:
        raise ValueError(
            f"PDF çok büyük ({len(data)} bayt > {MAX_PDF_BYTES}). İndirme iptal edildi."
        )
    ctype = resp.headers.get("content-type", "")
    if "pdf" not in ctype.lower() and not data[:5].startswith(b"%PDF"):
        raise ValueError(f"Beklenen PDF değil (content-type: {ctype}).")
    return extract(data, pdf_url, max_pages=max_pages, start_page=start_page)
