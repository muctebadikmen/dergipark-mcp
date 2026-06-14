# DergiPark MCP — Kalite Yükseltme: Sıfır-Bağlam Çalıştırma Promptu

> Bu dosya, **tek başına yeterli** bir görev tanımıdır. Sıfır bağlamla başlayan bir Claude Code oturumuna bu dosyanın tamamı verildiğinde, projeyi "olabilecek en kaliteli DergiPark MCP" haline getirecek tüm bilgi, karar ve adımlar burada vardır. Tahmin yürütme; burada yazan doğrulanmış gerçeklere ve kararlara uy. Belirsizlik varsa "AÇIK SORULAR" bölümündeki kurala göre davran.

---

## 0) ROL & MİSYON

Sen kıdemli bir Python/MCP mühendisisin. Görev: `/Users/mustafa/Desktop/Projects/dergipark-mcp` altındaki mevcut DergiPark MCP sunucusunu, **Türk akademisyenler için sınıfının en iyisi (best-in-class)** bir ürüne dönüştürmek.

Hedef kitle: **teknik olmayan akademisyenler.** İki şey en önemli: (1) kurulum kolaylığı (terminal/JSON yok), (2) aramanın ve tam-metin erişiminin gerçekten işe yaraması.

Stratejik kale (moat): Rakipler (`saidsurucu/literatur-mcp`) DergiPark'ı **scraping + ücretli CapSolver CAPTCHA + Mistral** ile kazıyor (kırılgan). Biz DergiPark'ın **resmî, ücretsiz, ToS-temiz OAI-PMH'ini** kullanıyoruz: anahtar yok, CAPTCHA yok, site JS'i değişince kırılmaz. **Bunu README'de en başa yaz ve her tasarım kararında koru.**

---

## 1) MEVCUT DURUM (neyin üzerine inşa ediyorsun)

Konum: `/Users/mustafa/Desktop/Projects/dergipark-mcp` (git YOK — gerekirse `git init`, ama push'u kullanıcı yapar).

Yığın: Python ≥3.10, `fastmcp` (v3.x), `httpx`, `beautifulsoup4`, `pypdf`. `uv` ile yönetiliyor. src-layout: `src/dergipark_mcp/`. MIT.

Mevcut modüller:
- `__init__.py` — BASE_URL, OAI_URL, OAI_NAMESPACE sabitleri
- `http.py` — paylaşılan async httpx; rate-limit (şu an MIN_INTERVAL=0.5s, MAX_CONCURRENCY=2 — **DÜZELTİLECEK, aşağıya bak**) + 429/503 backoff
- `oai.py` — OAI-PMH istemcisi + Dublin Core parser (`Article`/`Journal` dataclass; `html.unescape` ile CDATA entity düzeltmesi var)
- `site.py` — makale sayfası parse (citation_pdf_url + referanslar + BibTeX `cite-file/{id}/type/2`)
- `pdf.py` — pypdf çıkarım + taranmış/bozuk-font tespiti (`readable_ratio`, EXPECTED_LETTERS, eşik 0.80)
- `server.py` — 6 FastMCP aracı: `list_journals`, `list_journal_articles`, `search_articles` (dergi-içi), `get_article` (+bibtex), `get_article_fulltext`, `get_article_references`

Test: `uv run pytest -q` → 23 test (10 offline + 13 canlı, bellek-içi FastMCP Client e2e dahil). Offline: `-m "not live"`, canlı: `-m live`.

Çalıştırma: `uv run dergipark-mcp` (stdio). `claude_desktop_config.example.json` mevcut.

---

## 2) DOĞRULANMIŞ TEKNİK GERÇEKLER (hepsi canlı test edildi — yeniden araştırma)

### DergiPark erişim yüzeyi
- **OAI-PMH** (tek temiz API): `https://dergipark.org.tr/api/public/oai/`. Verbs: Identify/ListSets/ListIdentifiers/ListRecords/GetRecord. Formatlar: `oai_dc`, `oai_mods`, `oai_marc`, `oai_etdms`.
- Identifier şeması: `oai:dergipark.org.tr:article/<id>` (`record/<id>` de kabul). Sets = dergiler (setSpec = slug, bazen sayısal). Her `<header>`'da setSpec var (100/100 doğrulandı).
- Sayfalama: base64 `resumptionToken`, 100 kayıt/sayfa. `completeListSize` VERİLMEZ.
- **`from=YYYY-MM-DD` / `until=` çalışıyor** (saniye granülerliği de: `from=...T00:00:00Z`). Artımlı harvest için kullan.
- **`oai_mods` PRİMER FORMAT olsun**: bölünmüş yazar adları (given/family) + yapısal cilt/sayı/sayfa verir. `oai_dc` yedek (izlik.org persistent id + relation linkleri için). `oai_marc` özet (abstract) DÜŞÜRÜR — kullanma.
- **En zengin veri makale HTML sayfasındadır** (`/<en|tr>/pub/<slug>/article/<id>`, CAPTCHA YOK), Google-Scholar `<meta name="citation_*">` etiketlerinde:
  - `citation_pdf_url` (PDF linki — birincil yöntem), `citation_doi`, `citation_issn` (print+online)
  - `citation_author_institution` (AFİLİASYON), `citation_author_orcid` (ORCID)
  - `citation_reference` × N → **TAM REFERANS LİSTESİ** (örnek makalede 21 referans, tam künyelerle)
- **Tam dergi dizini** (ListSets sadece 100 verir, resumptionToken YOK): `https://dergipark.org.tr/en/pub/explore/journals?page=1..26` — sunucu-render HTML, 100 dergi/sayfa (sayfa 26'da 50), her kayıtta `/en/pub/<slug>` linki + yayıncı + konu etiketleri. **robots-serbest** (yalnız /search, /login yasak). **TOPLAM ≈ 2.550 dergi.** Konu taksonomisi: `/en/pub/subjects`.
- **Tam metin PDF**: `https://dergipark.org.tr/<lang>/download/article-file/<fileId>` (200, application/pdf, CAPTCHA yok). **fileId ≠ article id** → makale sayfasından `citation_pdf_url` ile al.
- **BibTeX**: `/<lang>/download/article-cite-file/<id>/type/2`. (type/2 = BibTeX; diğer tipler 404/değişken.)
- **Korpus ≈ 750.000–800.000 makale.** Tam metadata harvest: ~1 req/s'de ~4-8 saat, ~250-350 MB gzip. record id'leri seyrek (max ~1.94M) → id-aralığıyla saymak GEÇERSİZ.
- **REST API (`/api/public/v1/*`) ÖLÜ** — hepsi 404. OAI tek yapısal API.
- **izlik.org** persistent id HER kayıtta (`https://izlik.org/JA<kod>`). DOI sadece dergi mint ettiyse var → izlik birincil çapraz-referans anahtarı.

### Rate limit (kesin, ölçüldü)
- Tavan ≈ **5-6 istek / yuvarlanan saniye**, ~1 sn'de toparlıyor. **Retry-After YOK** (429 = statik nginx HTML). 429'u status koduyla yakala.
- **Güvenli ayar: concurrency = 1, ~1 istek/saniye (≈1000ms ara), 429'da üstel backoff (2,4,8s).** Paralelleştirme.
- → **`http.py`'yi düzelt**: MIN_INTERVAL≈1.0, MAX_CONCURRENCY=1.

### Önemli tuzaklar
- **Datestamp güvenilmez**: Mayıs 2026 redesign'da tüm repo toplu yeniden-datestamp'lendi. `from=` ileriye dönük yeni/değişeni yakalar ama datestamp'i yayın tarihi sanma — **yayın tarihi = `dc:date`**.
- **`deletedRecord=no`** → tombstone yok; çekilen makale sessizce kaybolur. Yerel indeks silmeleri artımlı yakalayamaz → periyodik tam ListIdentifiers sweep ile uzlaştır (reconcile).
- **PDF her zaman yok**: eski kayıtlarda `application/pdf` olmayabilir. `citation_pdf_url` varlığını kontrol et, sonra indir.
- **Çok dilli**: title/description/subject `xml:lang="tr-TR"` ve `en-US` varyantlı. tr tercih et, en yedek.
- **GetRecord yok id** → HTTP 404 JSON sayfası döner (OAI XML `idDoesNotExist` değil); ikisini de ele al.
- **Encoding**: UTF-8 ama CDATA içinde `&#039;` gibi entity'ler → `html.unescape` (mevcut kod yapıyor, koru).

### PDF → Markdown / OCR (test edildi)
- **pypdf (BSD) PRİMER kal** — born-digital PDF'lerde temiz. **PyMuPDF, pymupdf4llm, marker = AGPL-3.0 → MIT projeyle uyumsuz, KULLANMA** (viral lisans). `pymupdf-layout` = PolyForm Noncommercial (ticari yasak) — kesinlikle hayır.
- İzinli alternatifler: `pdfplumber`/`pdfminer.six` (MIT, layout daha iyi ama yavaş), `markitdown` (MIT ama bu PDF'lerde zayıf — boşluk düşürüyor), `docling` (MIT ama 1.1GB/çok yavaş — sadece opsiyonel ağır ekstra).
- **Bozuk-font PDF'ler**: gömülü font Identity-H + ToUnicode CMap YOK → gerçek karakter bilgisi dosyada FİZİKSEL OLARAK YOK. `ftfy` ÇÖZMEZ (kanıtlandı). Deterministik non-OCR çözüm yok. **Tek çare: rasterize + OCR.**
- **OCR (opsiyonel `[ocr]` ekstra, varsayılan KAPALI)**: `pdf2image` (poppler) + `pytesseract` + Tesseract `tur+eng` traineddata. İzinli, offline, **anahtar gerektirmez**. Hem taranmış hem bozuk-font PDF'i kurtardığı test edildi (~1-1.5s/sayfa). Yüksek-kalite opsiyonu olarak vision-LLM/Mistral OCR'ı API-anahtarı flag'i arkasında sun.
- **Tespit eşikleri (doğrulandı)**: harf yoksa/çok az = taranmış; `readable_ratio < ~0.7` ve harf varsa = bozuk-font (temiz=1.00, bozuk=0.11 — net ayrım). Mevcut `pdf.py` bunu yapıyor; koru/iyileştir.

### .mcpb paketleme (tek-tık kurulum) — KRİTİK
- Format `.mcpb` (eski adı `.dxt`; ikisi de kurulur). CLI: `npm i -g @anthropic-ai/mcpb` → `mcpb init` / `mcpb validate manifest.json` / `mcpb pack` / `mcpb sign|verify`.
- **EN BÜYÜK TUZAK: Python, Claude Desktop ile GELMEZ (Node gelir).** `python`/`uv` tipi bundle'lar, sistemde Python yoksa kurulumu REDDEDİLEBİLİR ([mcpb #84]). Üç seçenek:
  - `python` tipi: deps'i `pip install --target server/lib` ile göm; ama C-extension wheel'leri platforma özgü → OS/arch başına ayrı bundle. Saf-Python deps gerekir.
  - `uv` tipi: en temiz build ama kullanıcıda `uv` + Python şartı (sıfır-kurulum DEĞİL).
  - **`binary` tipi (teknik olmayan kullanıcı için ÖNERİLEN): PyInstaller ile tek çalıştırılabilir** → kullanıcıda HİÇBİR şey gerekmez. OS/arch başına bir bundle (darwin-arm64, ops. darwin-x64, win32-x64). macOS'te Gatekeeper, Windows'ta SmartScreen için **gömülü binary'yi codesign + notarize** etmek gerekir (Apple Developer ID / Authenticode) — bu kullanıcı kararı/maliyeti.
- `user_config` ile ayarlar Claude Desktop UI'ından alınır (env/JSON yok): opsiyonel OCR anahtarı `"sensitive": true` (keychain'e gider) → `mcp_config.env` ile sürece geçir.
- Dağıtım: **GitHub Releases** (en basit). Stdout'a SADECE JSON-RPC; loglar stderr'e (FastMCP `ctx` logu güvenli).

### FastMCP v3.4.x özellikleri (benimse)
- **Structured output**: araç dönüş tiplerini (dataclass/pydantic) tipli yap → istemci `structuredContent` alır. (P0)
- **Tool annotations**: tüm araçlar read-only → `ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=True)`. (P0)
- **Hata**: kullanıcıya yönelik `ToolError`; `FastMCP(..., mask_error_details=True)` ile iç stack izini gizle. (P1)
- **Context**: uzun işlemlerde `ctx.info(...)` + `ctx.report_progress(...)`. (P1)
- **Prompts**: `@mcp.prompt` ile şablon iş akışları. (P1)
- **Resources**: `dergipark://journal/{slug}`, `dergipark://article/{id}` (opsiyonel, P2).
- **Pagination**: FastMCP yerleşik sayfalama yalnız liste-op'ları kapsar, BÜYÜK araç sonuçlarını DEĞİL → büyük sonuçlarda araç içinde `page`/`page_size` + `next_page` döndür.

---

## 3) RAKİP ANALİZİ — neyi ödünç al, nerede geç

- **yoktez-mcp** (118★, aynı yazar, FastMCP/pydantic/markitdown): keşif→arama iki-adımlı akış (anabilim dalı listele→ara) — bizdeki `list_journals`→`search_articles` ile birebir; **5 atıf formatı** (APA/IEEE/MLA/Chicago/Harvard); **"PDF'siz detay" ucuz aracı**; **`cache.py` = MultiTierCache** (LRU bellek + disk, env-gated) — LİFT ET (aynı yazar MIT); geriye-uyumlu deprecated alias'lar; tip'li hata + boş-vs-hata ayrımı + `query_used_parameters` echo.
- **literatur-mcp** (DergiPark, scraping): tek gerçek üstünlüğü **site-geneli arama** + **`index_filter` (TR-Dizin)** + index rozetleri + atıf sayıları + Mistral OCR + hosted instance. TR-Dizin filtresi Türk akademisi için kritik (terfide TR-Dizin sayılır).
- **arxiv-mcp-server** (2.860★): altın standart — **MCP Prompts** (research-discovery, deep-paper-analysis, literature_review; `expertise_level` arg), **Resources** (`arxiv://{id}`), tool annotations, **arama açıklamasının kendisi UX** (sorgu sözdizimini öğretir), **[EXTERNAL CONTENT] etiketleme + prompt-injection notu**, fail-fast rate-limit.
- **pubmed (cyanheads)**: çok-format atıf (APA/MLA/BibTeX/RIS/Vancouver), **katmanlı tam-metin fallback** + tip'li `unavailable` nedenleri + her yanıtta provenance/sorgu-echo.
- **semantic-scholar**: `fields` seçimi (token kontrolü), `open_access_pdf`/`min_citation_count`/yıl-aralığı/venue filtreleri, niyet-ayrık arama araçları.
- **openalex**: küratörlü presetler (UTD24/FT50…) → bizde **TR-Dizin/ULAKBİM/SOBİAD presetleri**.
- **zotero (3.800★)**: markdown VEYA BibTeX export; **opsiyonel ekstralar** (`[semantic]`,`[pdf]`) ile hafif çekirdek.

---

## 4) PLAN — Fazlar (sırayla yap, her fazı doğrula, sonra ilerle)

> Her fazın sonunda: (a) `uv run pytest -q` yeşil, (b) bellek-içi FastMCP Client ile canlı duman testi + gerçek çıktı göster, (c) kısa ilerleme raporu. **Sunucu/para/anahtar/imza gerektiren işleri (v2 hosting, codesign sertifikası, vision-LLM anahtarı) kullanıcıya bırak**; kodu hazırla ama o adımı işaretle.

### FAZ 0 — Temel sağlamlaştırma (refactor, davranış aynı kalsın)
1. `http.py`: MIN_INTERVAL≈1.0, MAX_CONCURRENCY=1; 429 backoff'u koru (Retry-After yok varsay).
2. OAI primer formatı `oai_mods`'a geçir (parser'a mods desteği ekle; `oai_dc` yedek). Yazar adlarını given/family yapısal al; cilt/sayı/sayfa yapısal.
3. **Cache katmanı** ekle: bellek (LRU+TTL) + opsiyonel disk (`~/.dergipark-mcp/cache.db` ya da `platformdirs.user_cache_dir`), env-gated (`DERGIPARK_ENABLE_DISK_CACHE`). yoktez `cache.py` desenini referans al.
4. **FastMCP kalite**: pydantic/dataclass structured output dönüş tipleri; `ToolAnnotations(readOnlyHint=True…)` tüm araçlara; `ToolError` + `mask_error_details=True`; `ctx.info/report_progress` uzun işlemlerde; tip'li hata sözleşmeleri + boş-vs-hata ayrımı + `query_used_parameters` echo.
5. Abstract/tam-metin gibi dış içeriği `[EXTERNAL CONTENT] … [/EXTERNAL CONTENT]` ile etiketle; README'ye prompt-injection notu.
- **Kabul**: tüm mevcut testler + yeni cache/format/annotation testleri yeşil; davranış geriye-uyumlu.

### FAZ 1 — Tam dergi dizini + keşif
1. `directory.py`: `/en/pub/explore/journals?page=1..26` parse → tüm ~2.550 dergi (slug, ad, yayıncı, konular). `/en/pub/subjects` → konu taksonomisi.
2. Dizini **pakete gömülü statik JSON** olarak üret (build-time script: `scripts/build_directory.py`) + çalışma anında canlı yedek/yenileme. Yeni dergiler için `list_journals`'a canlı sorgu melezi.
3. `list_journals(query, subject, limit, offset)` tam dizin üzerinde; konuya göre filtre. Mümkünse **TR-Dizin/ULAKBİM/SOBİAD küratörlü presetleri**.
- **Kabul**: `list_journals` ~2.550 dergiyi kapsıyor, konu filtresi çalışıyor, ad/slug araması doğru.

### FAZ 2 — Zengin makale verisi + atıflar + referans + tam metin
1. `get_article`: `oai_mods` metadata + makale HTML zenginleştirme (afiliasyon, ORCID, DOI) + **çok-format atıf**: BibTeX, RIS, CSL-JSON, APA, MLA, IEEE, Chicago, Harvard (metadata'dan üret, ek bağımlılık yok). `include_*` flag'leriyle token kontrolü.
2. `get_article_references`: `citation_reference` meta'larından tam liste (doğrulandı), `#sec-references` yedeği, son çare BibTeX.
3. `get_article_fulltext`: pypdf primer + taranmış/bozuk-font tespiti + **opsiyonel `[ocr]` fallback** (pdf2image+pytesseract, `tur+eng`, flag/anahtar arkasında, varsayılan kapalı) + bölüm ayırma (ÖZET/ABSTRACT/GİRİŞ/KAYNAKÇA…) + dehyphenation + sayfa-bazlı + `max_pages` + araç-içi sayfalama. `text_reliable` bayrağını koru.
4. **TR-Dizin index rozetleri + atıf sayıları** (dergi `/indexes` sayfalarından veya OAI set metadata) — yapılabildiği kadar.
- **Kabul**: temiz PDF'te tam metin temiz; bozuk/taranmışta dürüst bayrak (+OCR ekstrası kuruluysa kurtarıyor); 8 atıf formatı geçerli; referanslar dolu.

### FAZ 3 — Dergi-içi arama v1 (yerel SQLite FTS5)
1. `index.py`: SQLite FTS5 (`tokenize="unicode61 remove_diacritics 1"`, prefix index `'2 3 4'`), `articles` + `articles_fts` şeması (bkz. araştırma şeması). Cache `~/.dergipark-mcp/cache.db`.
2. **Türkçe normalizasyon** (index ve sorguya SİMETRİK uygula): `tr_fold()` — `İ I ı i → i`, `ş→s ğ→g ü→u ö→o ç→c`, lower; küçük Türkçe stopword listesi; sorgu terimlerine prefix `*`.
3. `search_articles`: dergi-içi; on-demand harvest (`ListRecords&set=`, ~0.7s/sayfa, incremental `from=last_harvest`), FTS5 **BM25 ağırlıklı** (title 5× / keywords 3× / authors 2× / abstract 1×) + hafif recency boost + tam-ifade title bonusu. Harvest sırasında `ctx` ilerleme bildirimi.
4. **Zengin arama parametreleri**: `year_from`/`year_to` (OAI from/until ile ~bedava), `sort` (relevance/newest/oldest), `article_type`, author filtresi, `limit`/`offset`, `fields` seçimi, abstract truncation, `total` içeren sayfalama zarfı.
- **Kabul**: Türkçe sorgular (eğitim≈eğitimde≈Eğitim, İletişim≈iletisim) doğru eşleşiyor; ikinci arama cache'ten anında; ranking makul.

### FAZ 4 — MCP-yerel ergonomi
1. **Prompts**: `literature_review(topic, journal_slug)`, `summarize_article(article)`, `compare_articles(...)`, `research_discovery(topic, expertise_level, year_range)`.
2. **Resources**: `dergipark://journal/{slug}`, `dergipark://article/{id}`; arama sonuçlarına `resource_uri`.
3. Büyük sonuçlarda araç-içi sayfalama + truncation + field selection (tutarlı zarf).
- **Kabul**: prompt'lar Claude Desktop'ta görünür/çalışır; resource'lar çözülüyor.

### FAZ 5 — Paketleme & dağıtım (akademisyen için tek-tık) + cila
1. **README (Türkçe)**: moat'ı en başa yaz (resmî API, anahtar yok, CAPTCHA yok); örnekli kullanım; "good citizen"/rate-limit notu; prompt-injection notu; CC lisans/yasal notu; LICENSE'ta isim/yıl.
2. **.mcpb paketi**: `binary` (PyInstaller) yolunu hedefle (gerçek sıfır-kurulum); `manifest.json` (display_name, server.type, mcp_config, tools, prompts, `user_config` opsiyonel OCR anahtarı `sensitive:true`, compatibility). OS/arch başına pack. **codesign/notarize adımını kullanıcı kararı olarak belgele.** Alternatif `uv` manifest'i de README'de ver (Python'ı olanlar için).
3. **CI** (GitHub Actions): offline testler + lint; canlı testler opsiyonel/nightly.
4. Kapsamlı test: offline parser/pdf/normalize/citation + canlı OAI + bellek-içi Client e2e; fixture'lar.
- **Kabul**: `mcpb validate` + `mcpb pack` başarılı; temiz makinede kurulum talimatı net; tüm testler yeşil.

### FAZ 6 — (OPSİYONEL, talebe bağlı) Global arama v2 + semantik v3
- **v2 (hosted)**: tüm korpusu OAI ile harvest → tek **SQLite FTS5** dosyası ($6 VPS), nightly+weekly cron incremental (`from=`), streamable-HTTP remote MCP, per-IP rate-limit, periyodik full reconcile (silmeler için). **Sunucu+para+bakım kullanıcı kararı.**
- **v3 (semantik)**: `multilingual-e5-large` (1024-dim) embeddings + `sqlite-vec` + BM25 ile **RRF** hibrit. Bir-kerelik GPU pass (~$5-20). Yalnızca v2 kullanımda gerçek başarısız sorgular görülünce.

---

## 5) MİMARİ HEDEF (modüller)
```
src/dergipark_mcp/
  __init__.py        sabitler
  http.py            nazik httpx (1 req/s, conc=1, 429 backoff)
  cache.py           bellek LRU+TTL + opsiyonel disk (env-gated)
  oai.py             OAI istemci + mods/dc parser (yapısal yazar/cilt/sayı)
  site.py            makale HTML: citation_* (pdf_url, refs, affil, orcid, doi) + bibtex
  citations.py       BibTeX/RIS/CSL-JSON/APA/MLA/IEEE/Chicago/Harvard üreticiler
  directory.py       /explore/journals + /subjects parse → tam dergi dizini
  pdf.py             pypdf + tespit + opsiyonel OCR fallback + bölüm/markdown
  index.py           SQLite FTS5 + tr_fold normalizasyon + BM25 arama
  prompts.py         MCP prompt şablonları
  server.py          FastMCP araçları + resources + annotations + structured output
data/journals.json   gömülü dergi dizini (build script'iyle üretilir)
scripts/build_directory.py
tests/...            offline + live + e2e
manifest.json + icon.png   (.mcpb)
```

## 6) KISITLAR (her zaman uy)
- **Nazik ol**: concurrency 1, ~1 req/s, 429'da backoff. ASLA /search veya /login'e dokunma (robots yasak). Sadece OAI + /pub + /download + /explore.
- **Lisans temizliği**: yalnız izinli (MIT/BSD/Apache) bağımlılıklar. **AGPL YASAK** (PyMuPDF/marker/pymupdf4llm/docling-default). OCR opsiyonel ekstra, varsayılan kapalı, anahtarsız (Tesseract).
- **Dürüstlük**: bozuk/taranmış metni "gerçek" diye sunma — `text_reliable=false` + açık not.
- **Yasal**: metadata serbest (OAI amacı bu); tam metin son-kullanıcıya anlık; yeniden dağıtımda CC lisansına uy. README'de belirt.
- **Stdout temiz**: sadece JSON-RPC; loglar stderr/`ctx`.

## 7) ÇALIŞMA PROTOKOLÜ
1. Önce `uv run pytest -q` ile mevcut yeşili doğrula, sonra başla.
2. Fazları sırayla yap. Her faz: küçük adımlar, sık test, bellek-içi Client ile gerçek çıktı göster, kısa rapor, sonra ilerle.
3. DergiPark'a karşı testleri canlı yap ama nazik (rate-limit). Birim testleri fixture ile offline.
4. Kararı kullanıcıya bırakman gereken yerler: v2 hosting (sunucu/para), codesign sertifikaları, vision-LLM/Mistral anahtarı, GitHub'a push/release. Bunların kodunu/manifestini hazırla, adımı "kullanıcı yapacak" diye işaretle.
5. Bittiğinde: özet + tek-tık kurulum talimatı + neyin kullanıcıya kaldığı.

## 8) AÇIK SORULAR (kullanıcıya sor — varsayma)
- `.mcpb` için `binary` (PyInstaller, sıfır-kurulum ama imza maliyeti) mı yoksa `uv` (kolay build, kullanıcıda Python şartı) tipi mi? (Öneri: önce `uv` ile çalışır sürüm, sonra `binary`.)
- Faz 6 (hosted global arama) bu turda kapsam içi mi? (Öneri: v1-v5'i bitir, v6'yı talebe göre.)
- OCR'ı varsayılan opsiyonel ekstra olarak bırakmak yeterli mi, yoksa vision-LLM yüksek-kalite modu da istiyor musun?

## 9) BAŞARI ÖLÇÜTÜ
Bittiğinde ürün: ~2.550 derginin tamamını keşfeder; dergi-içi Türkçe-duyarlı arama yapar; zengin metadata + 8 atıf formatı + tam referans + (temiz PDF'lerde) temiz tam metin verir; teknik-olmayan akademisyen tek-tık kurar; resmî API sayesinde anahtarsız/CAPTCHA'sız/kırılmaz çalışır; rakip literatur-mcp ve yoktez-mcp'yi MCP-yerel ergonomi (Prompts/Resources/annotations/structured output) ve Türk-akademi odağında (TR-Dizin, çok-format atıf, çok-dilli) geçer.
```
