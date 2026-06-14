# DergiPark MCP

[DergiPark](https://dergipark.org.tr) (Türkiye'nin TÜBİTAK ULAKBİM akademik dergi platformu) için bir **Model Context Protocol (MCP)** sunucusu. Claude Desktop ve diğer MCP istemcilerinin DergiPark'taki dergileri taramasını, makale metadata'sını çekmesini ve tam metinleri (PDF) Markdown olarak okumasını sağlar.

> **Tasarım ilkesi:** Yalnızca DergiPark'ın **resmî OAI-PMH** servisini ve **açık makale sayfalarını** kullanır. `robots.txt`'e uyumludur, **CAPTCHA çözmez**, ücretli bir servise bağımlı değildir. (`/search` yolu robots ile kapalı olduğundan kullanılmaz.)

---

## Ne yapar? (Araçlar)

| Araç | Açıklama |
|---|---|
| `list_journals` | Dergileri listele/ara (OAI ListSets — *kısmi dizin, ~100 dergi*). |
| `list_journal_articles` | Bir derginin makalelerini listele (tarih filtreli, sayfalı). |
| `search_articles` | Bir dergi **içinde** anahtar kelimeyle ara (başlık + özet + yazar). |
| `get_article` | Tek makalenin tam metadata'sı + BibTeX atıfı. |
| `get_article_fulltext` | Makalenin PDF'ini indirip Markdown'a çevirir (sayfa-bazlı). |
| `get_article_references` | Makalenin kaynakça (referans) listesini çıkarır. |

### Örnek kullanım (Claude'a doğal dille)
- *"Mülkiye dergisinde 2014'te yayımlanan makaleleri listele."*
- *"mulkiye dergisinde 'tezkere' geçen makaleleri ara ve ilkinin tam metnini ver."*
- *"https://dergipark.org.tr/tr/pub/mulkiye/article/1000 makalesinin künyesini ve kaynakçasını çıkar."*

---

## Önemli kavram: **slug**

Bir dergiye onun **slug**'ı ile erişilir. Slug, derginin DergiPark URL'sindeki `/pub/<slug>/` kısmıdır:

```
https://dergipark.org.tr/tr/pub/mulkiye/...   ->   slug = "mulkiye"
```

`list_journals` ile slug bulabilir veya doğrudan bildiğiniz bir slug'ı kullanabilirsiniz.

---

## Kurulum

Gereksinim: **Python ≥ 3.10** ve [**uv**](https://docs.astral.sh/uv/).

```bash
git clone <repo-url> dergipark-mcp
cd dergipark-mcp
uv venv
uv pip install -e .
```

### Claude Desktop'a ekleme

`claude_desktop_config.example.json` dosyasındaki yapılandırmayı, Claude Desktop'ın
config dosyasına ekleyin (macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "dergipark": {
      "command": "uv",
      "args": ["--directory", "/MUTLAK/YOL/dergipark-mcp", "run", "dergipark-mcp"]
    }
  }
}
```

`--directory` değerini bu klasörün **mutlak yolu** ile değiştirin. Claude Desktop'ı
yeniden başlatın; araçlar bağlanmış olmalı.

Hızlı manuel kontrol (stdio sunucusu açılıyor mu):

```bash
uv run dergipark-mcp   # Ctrl-C ile kapatın; hata vermeden beklemesi yeterli
```

---

## Test

```bash
# Offline (ağsız) testler — parser, PDF, çözümleme
uv run pytest -m "not live" -q

# Canlı entegrasyon testleri — gerçek DergiPark trafiği üretir (nazik, yavaş)
uv run pytest -m live -q

# Hepsi
uv run pytest -q
```

---

## Mimari

```
İstemci (Claude) ──MCP──>  server.py (FastMCP araçları)
                                │
                ┌───────────────┼───────────────────┐
                ▼               ▼                   ▼
            oai.py          site.py               pdf.py
        (OAI-PMH:        (makale sayfası:       (PDF indir +
         metadata,        citation_pdf_url,      pypdf ile
         listeleme)       referanslar,           Markdown)
                          BibTeX)
                                │
                                ▼
                         http.py  (rate-limit + 429 backoff)
```

- **OAI-PMH** (`/api/public/oai/`): metadata, dergi/makale listeleme, sayfalama (resumptionToken).
- **Makale sayfası** (`/pub/.../article/...`): PDF linki (Google Scholar `citation_pdf_url` meta etiketi), referanslar, BibTeX.
- **Nazik HTTP** (`http.py`): DergiPark ardışık isteklerde 429 döndürür; istemci istekleri sınırlar ve `Retry-After`/üstel backoff ile yeniden dener.

---

## Sınırlamalar ve dürüst notlar

- **Genel (siteler arası) anahtar kelime araması yoktur.** DergiPark herkese açık bir arama API'si sunmaz ve `/search` robots ile kapalıdır. Bu yüzden `search_articles` bir **dergi kapsamında** çalışır (o derginin metadata'sını OAI ile çekip yerel olarak arar).
- **`list_journals` kısmi bir dizindir** (~100 dergi). DergiPark'ın OAI ListSets servisi tam listeyi (resumptionToken ile) vermez. Bilinen bir slug ile her dergiye erişilebilir.
- **Taranmış (görüntü) PDF'ler:** Metin katmanı olmayan PDF'lerden metin çıkmaz; bu sürümde **OCR yoktur** (gelecekte eklenebilir).

---

## Yasal / etik

DergiPark açık erişimli bir platformdur; dergiler çeşitli **Creative Commons** lisansları kullanır (CC BY-NC, CC BY-NC-ND vb.).

- **Metadata** (başlık, yazar, özet) OAI-PMH ile serbestçe toplanabilir — protokolün amacı budur.
- **Tam metin**, son kullanıcı için anlık getirilir (tarayıcı gibi). Yeniden dağıtım yapacaksanız her makalenin **CC lisansına** uyun (NC: ticari değil, ND: türev/değişiklik yok).
- İstemci `robots.txt`'e uyar, istekleri hız-sınırlar ve `User-Agent`'ta kendini tanıtır.

Bu yazılım "olduğu gibi" sağlanır; içeriğin kullanım sorumluluğu kullanıcıya aittir.

## Lisans

MIT — bkz. [LICENSE](LICENSE).
