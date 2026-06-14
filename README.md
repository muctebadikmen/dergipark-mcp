# DergiPark MCP

🇹🇷 Türkçe (bu dosya) · 🇬🇧 [English](README.en.md)

[DergiPark](https://dergipark.org.tr) (Türkiye'nin TÜBİTAK ULAKBİM akademik dergi platformu) için bir **Model Context Protocol (MCP)** sunucusu. Claude (Desktop/Code) ve diğer MCP istemcilerinin **~2.550 DergiPark dergisini** keşfetmesini, dergi içinde **Türkçe-duyarlı** arama yapmasını, zengin makale künyeleri + **8 atıf formatı** üretmesini ve tam metinleri (PDF) okumasını sağlar.

---

## ⭐ Neden bu MCP? (Kale / Moat)

Mevcut DergiPark MCP'leri siteyi **kazıyarak** (scraping) + **ücretli CAPTCHA çözücü** (CapSolver) + **harici OCR API** ile çalışır. Bu yaklaşım kırılgandır, anahtar/para gerektirir ve sitenin arayüzü değişince bozulur.

**Bu proje, DergiPark'ın resmî, ücretsiz, açık `OAI-PMH` servisini ve açık makale sayfalarını kullanır:**

| | Bu proje | Kazıma-tabanlı rakipler |
|---|---|---|
| **API anahtarı** | ❌ Gerekmez | ✅ CapSolver / OCR anahtarı |
| **Ücret** | ❌ Tamamen ücretsiz | 💸 CAPTCHA + OCR başına ödeme |
| **CAPTCHA** | ❌ Yok (resmî API) | 🤖 Turnstile çözücü şart |
| **robots.txt** | ✅ Uyumlu (yalnız izinli yollar) | ⚠️ /search robots-yasaklı |
| **Dayanıklılık** | ✅ Site JS'i değişince bozulmaz | ❌ Arayüz değişince kırılır |

> **Tasarım ilkesi:** Yalnızca **OAI-PMH** (`/api/public/oai/`), açık **makale sayfaları** (`/pub/.../article/...`), **PDF indirme** (`/download/...`) ve **dergi dizini** (`/pub/explore/journals`) kullanılır. `robots.txt` ile yasak olan `/search` ve `/login` yollarına **asla** dokunulmaz.

---

## Ne yapar?

### 🔧 Araçlar (7)

| Araç | Açıklama |
|---|---|
| `list_journals` | **Tam dizin** (~2.550 dergi) içinde ada/slug + **konuya** göre ara; sayfalı; en yaygın konuları gösterir. Arka planda kendiliğinden güncellenir. |
| `get_journal_info` | Bir derginin künyesi + **index/dizin üyeliği** (TR Dizin, DOAJ, Scopus, EBSCO, SOBIAD…) ve `tr_dizin` bayrağı — terfi/teşvik için kritik. |
| `list_journal_articles` | Bir derginin makalelerini listele (tarih filtreli, sayfalı). |
| `search_articles` | Bir dergi **içinde** **Türkçe-duyarlı** anahtar kelime araması (SQLite FTS5 + BM25). Yıl/yazar/tür filtresi, sıralama, sayfalama. |
| `get_article` | Zengin künye: yazar **+ afiliasyon + ORCID**, DOI, ISSN, cilt/sayı/sayfa, anahtar kelime + **8 atıf formatı**. |
| `get_article_fulltext` | PDF'i indirip Markdown'a çevirir; **bölüm haritası** (ÖZET/GİRİŞ/YÖNTEM/…/KAYNAKÇA), sayfa-sayfa gezinme. Bozuk/taranmış metinde **dürüstçe** `text_reliable=false`. |
| `get_article_references` | Makalenin tam kaynakça (referans) listesi. |

### 💬 Prompt'lar (4) — hazır araştırma iş akışları

`literature_review` · `summarize_article` · `compare_articles` · `research_discovery` (uzmanlık düzeyine göre). Claude Desktop'ta "/" menüsünde görünür.

### 📦 Kaynaklar (Resources, 2)

`dergipark://journal/{slug}` · `dergipark://article/{id}`

### ✨ Öne çıkan özellikler

- **Tam dergi dizini** (~2.550 dergi) pakete gömülü — anında, ağsız keşif + konu filtresi.
- **Türkçe-duyarlı arama:** `İ/ı/ş/ğ/ü/ö/ç` katlanır → "eğitim" ≈ "Eğitim" ≈ "egitim"; ön-ek eşleşir (eğitim → eğitimde). İlk arama indeksler, sonrakiler **anında** (kalıcı önbellek).
- **8 atıf formatı:** APA, MLA, IEEE, Chicago, Harvard, BibTeX, RIS, CSL-JSON — Türkçe karakterler korunarak.
- **Zengin meta:** yapısal yazar (given/family), **afiliasyon, ORCID**, DOI, ISSN — `oai_dc` + `oai_mods` + makale HTML birleştirilerek.
- **TR-Dizin/index rozetleri:** bir derginin **TR Dizin/ULAKBİM**, DOAJ, Scopus, EBSCO, SOBIAD üyeliği + `tr_dizin` bayrağı (terfi/teşvikte önemli).
- **Dinamik dizin:** dergi listesi her zaman anında döner ve arka planda günde bir kez kendiliğinden tazelenir — yeni açılan dergiler otomatik gelir.
- **Çok-katmanlı önbellek** (bellek + opsiyonel disk) → siteye saygı + hız.
- **Dürüstlük:** bozuk-font/taranmış PDF "gerçek metin" gibi sunulmaz; `text_reliable=false` ile işaretlenir.

---

## 🔑 Önemli kavram: **slug**

Bir dergiye onun **slug**'ı ile erişilir. Slug, derginin DergiPark URL'sindeki `/pub/<slug>/` kısmıdır:

```
https://dergipark.org.tr/tr/pub/mulkiye/...   ->   slug = "mulkiye"
```

`list_journals` ile slug bulabilir veya doğrudan bildiğiniz bir slug'ı kullanabilirsiniz.

---

## 🚀 Kurulum

### Seçenek A — `uv` ile (şu an çalışan yol)

Gereksinim: **Python ≥ 3.10** ve [**uv**](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/muctebadikmen/dergipark-mcp.git
cd dergipark-mcp
uv sync
```

**Claude Desktop'a ekleme** — config dosyasına (macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`) ekleyin (`claude_desktop_config.example.json` örneğine bakın):

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

`--directory` değerini bu klasörün **mutlak yolu** ile değiştirin; Claude Desktop'ı yeniden başlatın.

### Seçenek B — `.mcpb` ile tek-tık (teknik olmayan kullanıcılar için)

`.mcpb` paketi, Claude Desktop'a sürükle-bırak ile kurulan tek dosyadır. Bu repoda iki yol hazırdır (bkz. [`packaging/`](packaging/)):

- **`uv` tipi** (`manifest.json`): kullanıcının `uv` + Python'u olması gerekir; en kolay build.
- **`binary` tipi** (PyInstaller): kullanıcıda **hiçbir şey gerekmez** (gerçek sıfır-kurulum). macOS/Windows'ta işletim sistemi imza ister → bu adım (Apple Developer ID / Authenticode ile **imzalama/notarize**) paketleyen kişiye/maliyetine bağlıdır. Kod ve spec hazırdır; bkz. [`packaging/README.md`](packaging/README.md).

```bash
# .mcpb üretmek (Node gerektirir):
npm i -g @anthropic-ai/mcpb
cd packaging && mcpb validate manifest.json && mcpb pack
```

---

## 🗣️ Örnek kullanım (Claude'a doğal dille)

- *"Eğitim konulu DergiPark dergilerini listele."* → `list_journals(subject=…)`
- *"mulkiye dergisi TR Dizin'de mi? Hangi indekslerde taranıyor?"* → `get_journal_info`
- *"mulkiye dergisinde 'siyaset' geçen 2015 sonrası makaleleri ara, en yeniden eskiye sırala."*
- *"Şu makalenin künyesini APA ve IEEE formatında ver: https://dergipark.org.tr/tr/pub/mulkiye/article/1000"*
- *"29mayisegitim/1816398 makalesinin tam metnini oku ve yöntem bölümünü özetle."*
- *"/literature_review topic=okul öncesi eğitim"* (prompt)

---

## ⚙️ Çevre değişkenleri (opsiyonel)

| Değişken | Varsayılan | Açıklama |
|---|---|---|
| `DERGIPARK_MIN_INTERVAL` | `1.0` | İstekler arası min saniye (nezaket). |
| `DERGIPARK_MAX_CONCURRENCY` | `1` | Eşzamanlı istek sayısı. |
| `DERGIPARK_ENABLE_DISK_CACHE` | kapalı | `1` → disk önbelleğini açar (süreçler arası kalıcı). |
| `DERGIPARK_CACHE_DIR` | platforma özgü | Önbellek + arama indeksi dizini. |

---

## 🔒 Güvenlik (prompt-injection)

DergiPark'tan gelen tam metin/özet/referanslar **dış içeriktir**. Bu sunucu, tam metni `[EXTERNAL CONTENT] … [/EXTERNAL CONTENT]` ile sarar ve yanıtlara `source_notice` ekler: bu içerik **veri** olarak değerlendirilmeli, **talimat** olarak değil. İstemci modeli (Claude) bu işarete uyacak şekilde yönlendirilir.

---

## 🙏 Nazik kullanım (good citizen)

DergiPark ardışık isteklerde HTTP 429 döndürür ve `Retry-After` göndermez. İstemci varsayılan olarak **eşzamanlılığı 1**, **istek aralığını ~1 sn** tutar, 429'da **üstel backoff** uygular ve `User-Agent`'ta kendini tanıtır. Lütfen bu ayarları gereksiz yere agresifleştirmeyin.

---

## ⚖️ Yasal / etik

DergiPark açık erişimli bir platformdur; dergiler çeşitli **Creative Commons** lisansları kullanır (CC BY-NC, CC BY-NC-ND vb.).

- **Metadata** (başlık, yazar, özet) OAI-PMH ile serbestçe toplanabilir — protokolün amacı budur.
- **Tam metin**, son kullanıcı için anlık getirilir (tarayıcı gibi). Yeniden dağıtım yapacaksanız her makalenin **CC lisansına** uyun (NC: ticari değil; ND: türev/değişiklik yok).
- İstemci `robots.txt`'e uyar, istekleri hız-sınırlar ve kendini tanıtır.

Bu yazılım "olduğu gibi" sağlanır; içeriğin kullanım sorumluluğu kullanıcıya aittir.

---

## ⚠️ Dürüst sınırlamalar

- **Siteler-arası (global) anahtar kelime araması yoktur.** DergiPark herkese açık genel arama API'si sunmaz ve `/search` robots ile kapalıdır. Bu yüzden `search_articles` bir **dergi kapsamında** çalışır. (Global arama, ücretli bir sunucu + harvest gerektirir; bu proje bilinçli olarak **sunucusuz/yerel**dir.)
- **OCR yoktur.** Taranmış veya bozuk-font (Unicode/ToUnicode eşlemesi olmayan) PDF'lerde metin fiziksel olarak çıkarılamaz. Ücretsiz, anahtarsız ve herkes için sürtünmesiz (sistem ikilisi gerektirmeyen) bir OCR yolu olmadığından OCR kapsam dışıdır; bu tür belgeler **`text_reliable=false`** ile dürüstçe işaretlenir.
- **Konu taksonomisi İngilizcedir** ("Law", "Education", "Sociology" …). `list_journals` filtresiz çağrıldığında `available_subjects` ile mevcut konuları görebilirsiniz.

---

## 🧱 Mimari

```
İstemci (Claude) ──MCP──> server.py (6 araç + 4 prompt + 2 kaynak)
                               │
   ┌─────────────┬─────────────┼───────────────┬──────────────┬───────────┐
   ▼             ▼             ▼               ▼              ▼           ▼
directory.py   oai.py        site.py         pdf.py       index.py   citations.py
(~2550 dergi  (OAI-PMH:     (makale HTML:   (PDF→md +     (FTS5 +    (8 atıf
 dizini +      oai_dc +      citation_*:     bölüm +      Türkçe     formatı)
 konu)         oai_mods)     affil/orcid/    güvenilirlik  fold +
                             doi + refs)     bayrağı)      BM25)
                               │
                               ▼
                  cache.py (bellek + disk) · http.py (1 req/s, conc=1, 429 backoff)
```

---

## 🧪 Geliştirme & test

```bash
uv sync
uv run pytest -m "not live" -q     # offline (parser/pdf/cache/index/citations/prompts) — hızlı
uv run pytest -m live -q           # canlı (gerçek DergiPark trafiği — nazik, yavaş)
uvx ruff check src/ tests/         # lint
```

**Dergi dizinini yenileme** (yeni dergiler eklendikçe):

```bash
uv run python scripts/build_directory.py   # data/journals.json'u yeniden üretir
```

---

## 📄 Lisans

MIT — bkz. [LICENSE](LICENSE).
