# DergiPark MCP

🇹🇷 Türkçe (bu dosya) · 🇬🇧 [English](README.en.md)

[DergiPark](https://dergipark.org.tr) (Türkiye'nin TÜBİTAK ULAKBİM akademik dergi platformu) için bir **Model Context Protocol (MCP)** sunucusu. Claude (Desktop / claude.ai / mobil) ve diğer MCP istemcilerinin **~2.550 DergiPark dergisini** keşfetmesini, **Türkçe-duyarlı** arama yapmasını (dergi içi **ve** dergiler-arası), yazar bazlı keşif, benzer-makale önerisi, zengin künye + **8 atıf formatı** ve tam metin (PDF) okuması sağlar.

> ⚡ **En kolay kullanım: kurulum yok.** Aşağıdaki tek bir URL'yi Claude'a yapıştırın — uygulama, config, Python, hiçbiri gerekmez. [→ Hemen başla](#-en-hızlı-kurulum-urlyi-yapıştır-önerilen)

---

## 🚀 En hızlı kurulum: URL'yi yapıştır (önerilen)

Bu MCP **çevrimiçi bir sunucu** olarak yayında (Hugging Face Spaces, ücretsiz). Hiçbir şey indirmeden, **tek bir URL** ile birkaç tıkta eklenir — **Claude Desktop, claude.ai (tarayıcı) ve mobil** uygulamada çalışır.

**1) Şu URL'yi kopyala:**

```
https://muctebadikmen-dergipark-mcp.hf.space/mcp
```

**2) Claude'da bağla:** **Settings → Connectors → Add custom connector** → URL'yi yapıştır → **Add**.

**3) Test et:** Claude'a şunu yaz:
> *"DergiPark'ta hukuk tarihi üzerine birbirinden farklı dergilerden makaleler bul."*

Bu kadar. Config dosyası yok, `uv`/Python kurulumu yok, sürükle-bırak yok.

> ℹ️ **Dürüst not:** Ücretsiz sunucu uzun süre (≈48 saat) hiç kullanılmazsa uykuya geçer; ilk istekte **~30–60 sn** uyanır, sonra hızlıdır. Açık ve anahtarsızdır — URL'yi bilen herkes kullanabilir (akademik açık araç).

<details>
<summary>🖥️ Kendi bilgisayarında <b>yerel</b> çalıştırmak istersen (gelişmiş / opsiyonel)</summary>

URL yöntemi çoğu kişi için yeterlidir. Ama sunucuyu **kendi makinende** çalıştırmak istersen (gizlilik, çevrimdışı önbellek, hosted sunucuya bağımlı olmamak) iki yol var. İkisi de `uv` (Python yöneticisi) ister.

### a) Tek-satır `uvx` (yerel, önerilen yerel yöntem)

**1) `uv`'yi kur:**
- macOS / Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`
- Windows (PowerShell): `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"` (sonra terminali yeniden aç)

**2) Claude Desktop → Settings → Developer → Edit Config** (`claude_desktop_config.json`) açılır.

**3) Şu bloğu ekle:**
```json
{
  "mcpServers": {
    "dergipark": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/muctebadikmen/dergipark-mcp", "dergipark-mcp"]
    }
  }
}
```

**4) Kaydet, Claude Desktop'ı tamamen kapat-aç** (Mac'te **Cmd+Q**).

- *"uvx bulunamadı":* tam yolu yaz — Mac/Linux `which uvx`, Windows `where uvx`.
- *Güncelleme:* `uvx --refresh --from git+https://github.com/muctebadikmen/dergipark-mcp dergipark-mcp`

### b) `.mcpb` dosyası (sürükle-bırak)
[Releases](https://github.com/muctebadikmen/dergipark-mcp/releases/latest)'tan `.mcpb`'yi indir → Claude Desktop → Settings → Extensions/Connectors → pencereye sürükle. (Bu da `uv` + Python ister; macOS Tahoe 26.x'te eklenti kurulumu bilinen bir hatayla sessizce başarısız olabilir — o durumda URL yöntemini veya (a)'yı kullan.)

### c) Claude Code (CLI)
```bash
claude mcp add --transport http dergipark https://muctebadikmen-dergipark-mcp.hf.space/mcp   # hosted URL
# veya yerel:
claude mcp add dergipark -- uvx --from git+https://github.com/muctebadikmen/dergipark-mcp dergipark-mcp
```
</details>

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

> **Tasarım ilkesi:** Yalnızca **OAI-PMH** (`/api/public/oai/`), açık **makale sayfaları** (`/pub/.../article/...`), **PDF indirme** (`/download/...`) ve **dergi dizini** kullanılır. `robots.txt` ile yasak olan `/search` ve `/login` yollarına **asla** dokunulmaz.

---

## Ne yapar?

### 🔧 Araçlar (10)

| Araç | Açıklama |
|---|---|
| `list_journals` | **Tam dizin** (~2.550 dergi) içinde ada/slug + **konuya** göre ara; sayfalı. Arka planda kendiliğinden güncellenir. |
| `get_journal_info` | Bir derginin künyesi + **index/dizin üyeliği** (TR Dizin, DOAJ, Scopus, EBSCO, SOBIAD…) ve `tr_dizin` bayrağı — terfi/teşvik için kritik. |
| `list_journal_articles` | Bir derginin makalelerini listele (tarih filtreli, sayfalı). |
| `search_articles` | **TEK bir dergi içinde** Türkçe-duyarlı anahtar kelime araması (SQLite FTS5 + BM25). Yıl/yazar/tür filtresi, sıralama, sayfalama. |
| `search_all_journals` | **Dergiler-arası** (cross-journal) arama — bir konuyu **birden çok / farklı dergide** tek seferde. İndekslenmiş havuzda arar; kapsamı dürüstçe bildirir. |
| `find_author` | **Yazar bazlı keşif** — bir yazarın havuzdaki tüm makaleleri. Konu gerekmez; ad-sırasından bağımsız ("Aybars Pamir" ≈ "Pamir, Aybars"). |
| `related_articles` | Verilen bir makaleye **benzer / ilgili** makaleler (anahtar kelime + başlık örtüşmesi) — literatür "kartopu". |
| `get_article` | Zengin künye: yazar **+ afiliasyon + ORCID**, DOI, ISSN, cilt/sayı/sayfa, anahtar kelime + **8 atıf formatı**. |
| `get_article_fulltext` | PDF'i indirip Markdown'a çevirir; **bölüm haritası** (ÖZET/GİRİŞ/YÖNTEM/…/KAYNAKÇA), sayfa-sayfa gezinme. Bozuk/taranmış metinde **dürüstçe** `text_reliable=false`. |
| `get_article_references` | Makalenin tam kaynakça (referans) listesi. |

### 💬 Prompt'lar (4) — hazır araştırma iş akışları

`literature_review` · `summarize_article` · `compare_articles` · `research_discovery`. Claude Desktop'ta "/" menüsünde görünür.

### 📦 Kaynaklar (Resources, 2)

`dergipark://journal/{slug}` · `dergipark://article/{id}`

### ✨ Öne çıkan özellikler

- **Dergiler-arası arama (yeni):** bir konuyu tek dergiyle sınırlamadan, **tüm büyük alanlardan** (hukuk, iktisat, sosyoloji, eğitim, ilahiyat, tıp, felsefe…) **221 dergi / ~37 bin makale** üzerinde anında ara — sunucuyla birlikte gelen **bake'lenmiş indeks** sayesinde. Havuzda olmayan dergiler `search_articles` ile anında havuza eklenir (hiçbir şey sınırlanmaz; tüm 2.548 dergi her zaman erişilebilir).
- **Türkçe-duyarlı arama:** `İ/ı/ş/ğ/ü/ö/ç` katlanır → "eğitim" ≈ "Eğitim" ≈ "egitim"; ön-ek eşleşir; çok-kelimeli sorgularda tam-ifade ve başlık eşleşmeleri öne çıkar.
- **8 atıf formatı:** APA, MLA, IEEE, Chicago, Harvard, BibTeX, RIS, CSL-JSON — Türkçe karakterler korunarak.
- **Zengin meta:** yapısal yazar (given/family), **afiliasyon, ORCID**, DOI, ISSN — `oai_dc` + `oai_mods` + makale HTML birleştirilerek.
- **TR-Dizin/index rozetleri:** TR Dizin/ULAKBİM, DOAJ, Scopus, EBSCO, SOBIAD üyeliği + `tr_dizin` bayrağı.
- **Dürüstlük:** bozuk-font/taranmış PDF "gerçek metin" gibi sunulmaz; `text_reliable=false` ile işaretlenir. Dergiler-arası aramanın kapsamı (kaç/hangi dergi) her yanıtta bildirilir.

---

## 🔑 Önemli kavram: **slug**

Bir dergiye onun **slug**'ı ile erişilir. Slug, derginin DergiPark URL'sindeki `/pub/<slug>/` kısmıdır:

```
https://dergipark.org.tr/tr/pub/mulkiye/...   ->   slug = "mulkiye"
```

`list_journals` ile slug bulabilir veya doğrudan bildiğiniz bir slug'ı kullanabilirsiniz.

---

## 🗣️ Örnek kullanım (Claude'a doğal dille)

- *"DergiPark'ta hukuk tarihi üzerine **farklı dergilerden** makaleler bul."* → `search_all_journals`
- *"**Belkıs Konan**'ın DergiPark'taki makalelerini listele."* → `find_author`
- *"Şu makaleye **benzer** çalışmalar öner: dergipark.org.tr/.../article/1071191"* → `related_articles`
- *"Eğitim konulu DergiPark dergilerini listele."* → `list_journals(subject=…)`
- *"mulkiye dergisi TR Dizin'de mi?"* → `get_journal_info`
- *"mulkiye dergisinde 'siyaset' geçen 2015 sonrası makaleleri, en yeniden eskiye sırala."* → `search_articles`
- *"Şu makalenin künyesini APA ve IEEE ver: .../article/1000"* → `get_article`
- *"29mayisegitim/1816398'in tam metnini oku, yöntem bölümünü özetle."* → `get_article_fulltext`
- *"/literature_review topic=okul öncesi eğitim"* (prompt)

---

## ⚙️ Çevre değişkenleri (opsiyonel — yerel çalıştırma)

| Değişken | Varsayılan | Açıklama |
|---|---|---|
| `DERGIPARK_MIN_INTERVAL` | `1.0` | İstekler arası min saniye (nezaket). |
| `DERGIPARK_MAX_CONCURRENCY` | `1` | Eşzamanlı istek sayısı. |
| `DERGIPARK_MAX_SCAN_DEFAULT` | `2000` | `search_articles` varsayılan tarama derinliği (hosted'da düşürülür). |
| `DERGIPARK_ENABLE_DISK_CACHE` | kapalı | `1` → disk önbelleğini açar (süreçler arası kalıcı). |
| `DERGIPARK_CACHE_DIR` | platforma özgü | Önbellek + arama indeksi dizini. |
| `DERGIPARK_SEED_INDEX` | paket içi | Bake'lenmiş seed indeksinin yolu (`.db` veya `.db.gz`). |

---

## ⚠️ Dürüst sınırlamalar

- **Dergiler-arası arama, indekslenmiş havuzla sınırlıdır.** DergiPark herkese açık siteler-arası arama API'si sunmaz ve `/search` robots ile kapalıdır. `search_all_journals`, sunucuyla gelen bake'lenmiş **221 dergilik** havuzda (+ o oturumda taranan dergiler) arar — **tüm 2.548 dergiyi anında değil.** Havuzda olmayan bir dergi `search_articles(journal=…)` ile **anında** taranıp havuza eklenir; yani hiçbir dergi/alan kalıcı olarak dışarıda değildir.
- **OCR yoktur.** Taranmış/bozuk-font PDF'lerde metin fiziksel olarak çıkarılamaz. Ücretsiz, anahtarsız, sürtünmesiz bir OCR yolu olmadığından kapsam dışıdır; bu belgeler **`text_reliable=false`** ile işaretlenir.
- **Konu taksonomisi İngilizcedir** ("Law", "Education", "Sociology"…). `list_journals` filtresiz çağrıldığında `available_subjects` ile mevcut konuları görebilirsiniz.

---

## 🔒 Güvenlik (prompt-injection)

DergiPark'tan gelen tam metin/özet/referanslar **dış içeriktir**. Sunucu, tam metni `[EXTERNAL CONTENT] … [/EXTERNAL CONTENT]` ile sarar ve yanıtlara `source_notice` ekler: bu içerik **veri** olarak değerlendirilmeli, **talimat** olarak değil.

## 🙏 Nazik kullanım (good citizen)

DergiPark ardışık isteklerde HTTP 429 döndürür ve `Retry-After` göndermez. İstemci varsayılan olarak **eşzamanlılığı 1**, **istek aralığını ~1 sn** tutar, 429/geçici 5xx'te **üstel backoff** uygular ve `User-Agent`'ta kendini tanıtır.

## ⚖️ Yasal / etik

DergiPark açık erişimli bir platformdur; dergiler çeşitli **Creative Commons** lisansları kullanır.

- **Metadata** (başlık, yazar, özet) OAI-PMH ile serbestçe toplanabilir — protokolün amacı budur.
- **Tam metin**, son kullanıcı için anlık getirilir. Yeniden dağıtım yapacaksanız her makalenin **CC lisansına** uyun (NC: ticari değil; ND: türev yok).
- İstemci `robots.txt`'e uyar, hız-sınırlar ve kendini tanıtır.

Bu yazılım "olduğu gibi" sağlanır; içeriğin kullanım sorumluluğu kullanıcıya aittir.

---

## 🧱 Mimari

```
İstemci (Claude)  ──MCP──>  server.py (10 araç + 4 prompt + 2 kaynak)
   • Hosted: https://muctebadikmen-dergipark-mcp.hf.space/mcp  (HTTP)
   • Yerel:  uvx / .mcpb  (stdio)
                               │
   ┌─────────────┬─────────────┼───────────────┬──────────────┬───────────┐
   ▼             ▼             ▼               ▼              ▼           ▼
directory.py   oai.py        site.py         pdf.py       index.py   citations.py
(~2550 dergi  (OAI-PMH:     (makale HTML:   (PDF→md +     (FTS5 +    (8 atıf
 dizini +      oai_dc +      citation_*:     bölüm +      Türkçe     formatı)
 konu)         oai_mods)     affil/orcid/    güvenilirlik  fold + BM25 +
                             doi + refs)     bayrağı)      bake'li seed)
                               │
                               ▼
                  cache.py (bellek + disk) · http.py (1 req/s, conc=1, 429/5xx backoff)
```

Hosted sürüm pakete gömülü, gzip'li bir **seed indeksi** (`data/seed_index.db.gz`, 221 dergi / ~37 bin makale) ile gelir; açılışta açılarak dergiler-arası aramayı **sıcak** başlatır.

---

## 🧪 Geliştirme & test

```bash
uv sync
uv run pytest -m "not live" -q     # offline (hızlı): parser/pdf/cache/index/citations/prompts
uv run pytest -m live -q           # canlı (gerçek DergiPark trafiği — nazik, yavaş)
uvx ruff check src/ tests/         # lint
```

**Dergi dizinini yenileme:**
```bash
uv run python scripts/build_directory.py    # data/journals.json'u yeniden üretir
```

**Bake'lenmiş seed indeksini (yeniden) üretme** (dergiler-arası havuzu büyütmek/tazelemek için):
```bash
uv run python scripts/build_index.py --slugs <virgüllü slug listesi> --max-records 300 --max-db-mb 190
gzip -9 -c <out.db> > src/dergipark_mcp/data/seed_index.db.gz
```

---

## 📄 Lisans

MIT — bkz. [LICENSE](LICENSE).
