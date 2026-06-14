"""PDF indirme ve metne/Markdown'a dönüştürme.

Dijital (metin katmanı olan) PDF'ler için pypdf ile sayfa-bazlı metin çıkarımı.
Taranmış (görüntü) PDF'ler için OCR bu MVP kapsamında değildir; böyle bir PDF'te
metin boş döner ve uyarı verilir (gelecekte OCR fallback eklenebilir).
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

from pypdf import PdfReader

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

from . import http

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


def extract(data: bytes, source_url: str, max_pages: int | None = None) -> ExtractedPDF:
    reader = PdfReader(io.BytesIO(data))
    total = len(reader.pages)
    limit = total if max_pages is None else min(max_pages, total)

    pages: list[str] = []
    for i in range(limit):
        try:
            raw = reader.pages[i].extract_text() or ""
        except Exception as exc:  # bozuk sayfa tek tek atlanır
            raw = ""
            page_note = f"[sayfa {i + 1} çıkarılamadı: {exc}]"
            pages.append(page_note)
            continue
        pages.append(_normalize(raw))

    body = "\n\n".join(
        f"## Sayfa {i + 1}\n\n{txt}" if txt else f"## Sayfa {i + 1}\n\n_(boş veya görüntü)_"
        for i, txt in enumerate(pages)
    )
    # Taranmış (görüntü) PDF'ler ~0 karakter verir; gerçek metin katmanı yüzlerce+.
    # Eşik düşük tutulur ki kısa ama gerçek sayfalar yanlışlıkla "boş" sayılmasın.
    has_text = sum(len(p.strip()) for p in pages) > 10
    truncated = limit < total
    text_reliable = True
    note = None
    if not has_text:
        if truncated:
            # Sadece ilk birkaç sayfa çekildi ve onlar seyrek (kapak/başlık olabilir);
            # "taranmış" demek yanıltıcı olur.
            note = (
                f"İlk {limit} sayfada anlamlı metin bulunamadı (belge {total} sayfa). "
                "Daha fazla sayfa için max_pages değerini artırın; ya da belge taranmış olabilir."
            )
        else:
            note = (
                "Bu PDF'ten metin çıkarılamadı — büyük olasılıkla taranmış (görüntü) "
                "bir belge. OCR bu sürümde desteklenmiyor."
            )
    else:
        ratio = readable_ratio("\n".join(pages))
        if ratio < READABLE_RATIO_THRESHOLD:
            text_reliable = False
            note = (
                f"Çıkarılan metin güvenilir görünmüyor (okunabilir karakter oranı %{ratio * 100:.0f}). "
                "PDF fontu düzgün Unicode eşlemesi içermiyor; çıkarılan metin bozuk. "
                "Bu tür belgeler için OCR gerekir (bu sürümde yok)."
            )

    header = f"# Tam metin (PDF)\n\nKaynak: {source_url}\nSayfa: {limit}/{total}\n\n---\n\n"
    return ExtractedPDF(
        source_url=source_url,
        page_count=total,
        pages=pages,
        markdown=header + body,
        has_text=has_text,
        text_reliable=text_reliable,
        note=note,
    )


async def download_and_extract(
    pdf_url: str, max_pages: int | None = None
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
    return extract(data, pdf_url, max_pages=max_pages)
