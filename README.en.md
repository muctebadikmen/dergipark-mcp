# DergiPark MCP

🇹🇷 [Türkçe](README.md) · 🇬🇧 English (this file)

A **Model Context Protocol (MCP)** server for [DergiPark](https://dergipark.org.tr) (Turkey's TÜBİTAK ULAKBİM academic journal platform). It lets Claude (Desktop/Code) and other MCP clients discover **~2,550 DergiPark journals**, run **Turkish-aware** search within a journal, generate rich article metadata + **8 citation formats**, and read full texts (PDF).

---

## ⭐ Why this MCP? (Moat)

Existing DergiPark MCPs work by **scraping** the site + a **paid CAPTCHA solver** (CapSolver) + an **external OCR API**. That approach is fragile, requires keys/money, and breaks whenever the site's UI changes.

**This project uses DergiPark's official, free, open `OAI-PMH` service and its open article pages:**

| | This project | Scraping-based competitors |
|---|---|---|
| **API key** | ❌ Not required | ✅ CapSolver / OCR key |
| **Cost** | ❌ Completely free | 💸 Pay per CAPTCHA + OCR |
| **CAPTCHA** | ❌ None (official API) | 🤖 Turnstile solver required |
| **robots.txt** | ✅ Compliant (only allowed paths) | ⚠️ /search is robots-blocked |
| **Resilience** | ✅ Doesn't break when site JS changes | ❌ Breaks when the UI changes |

> **Design principle:** Only **OAI-PMH** (`/api/public/oai/`), open **article pages** (`/pub/.../article/...`), **PDF downloads** (`/download/...`), and the **journal directory** (`/pub/explore/journals`) are used. The `/search` and `/login` paths that are disallowed by `robots.txt` are **never** touched.

---

## What does it do?

### 🔧 Tools (7)

| Tool | Description |
|---|---|
| `list_journals` | Search the **full directory** (~2,550 journals) by name/slug + **subject**; paginated; shows the most common subjects. Self-updates in the background. |
| `get_journal_info` | A journal's masthead + **index/directory membership** (TR Dizin, DOAJ, Scopus, EBSCO, SOBIAD…) and the `tr_dizin` flag — critical for promotion/incentives. |
| `list_journal_articles` | List a journal's articles (date-filtered, paginated). |
| `search_articles` | **Turkish-aware** keyword search **within** a journal (SQLite FTS5 + BM25). Year/author/type filters, sorting, pagination. |
| `get_article` | Rich metadata: author **+ affiliation + ORCID**, DOI, ISSN, volume/issue/page, keywords + **8 citation formats**. |
| `get_article_fulltext` | Downloads the PDF and converts it to Markdown; **section map** (ABSTRACT/INTRODUCTION/METHODS/…/REFERENCES), page-by-page navigation. For broken/scanned text it **honestly** reports `text_reliable=false`. |
| `get_article_references` | The article's complete reference (bibliography) list. |

### 💬 Prompts (4) — ready-made research workflows

`literature_review` · `summarize_article` · `compare_articles` · `research_discovery` (by expertise level). They appear in the "/" menu in Claude Desktop.

### 📦 Resources (2)

`dergipark://journal/{slug}` · `dergipark://article/{id}`

### ✨ Highlights

- **Full journal directory** (~2,550 journals) embedded in the package — instant, offline discovery + subject filter.
- **Turkish-aware search:** `İ/ı/ş/ğ/ü/ö/ç` are folded → "eğitim" ≈ "Eğitim" ≈ "egitim"; prefix matching works (eğitim → eğitimde). The first search indexes; subsequent ones are **instant** (persistent cache).
- **8 citation formats:** APA, MLA, IEEE, Chicago, Harvard, BibTeX, RIS, CSL-JSON — with Turkish characters preserved.
- **Rich metadata:** structured authors (given/family), **affiliation, ORCID**, DOI, ISSN — by merging `oai_dc` + `oai_mods` + the article HTML.
- **TR-Dizin/index badges:** a journal's **TR Dizin/ULAKBİM**, DOAJ, Scopus, EBSCO, SOBIAD membership + the `tr_dizin` flag (important for promotion/incentives).
- **Dynamic directory:** the journal list always returns instantly and self-refreshes once a day in the background — newly launched journals show up automatically.
- **Multi-layer cache** (memory + optional disk) → respect for the site + speed.
- **Honesty:** broken-font/scanned PDFs are not presented as "real text"; they are marked with `text_reliable=false`.

---

## 🔑 Key concept: **slug**

A journal is accessed by its **slug**. The slug is the `/pub/<slug>/` part of the journal's DergiPark URL:

```
https://dergipark.org.tr/tr/pub/mulkiye/...   ->   slug = "mulkiye"
```

You can find a slug with `list_journals`, or use a slug you already know directly.

---

## 🚀 Installation

### Option A — with `uv` (the path that currently works)

Requirements: **Python ≥ 3.10** and [**uv**](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/muctebadikmen/dergipark-mcp.git
cd dergipark-mcp
uv sync
```

**Adding to Claude Desktop** — add this to the config file (macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`) (see the `claude_desktop_config.example.json` example):

```json
{
  "mcpServers": {
    "dergipark": {
      "command": "uv",
      "args": ["--directory", "/ABSOLUTE/PATH/dergipark-mcp", "run", "dergipark-mcp"]
    }
  }
}
```

Replace the `--directory` value with the **absolute path** of this folder; restart Claude Desktop.

### Option B — one-click with `.mcpb` (for non-technical users)

An `.mcpb` package is a single file you install into Claude Desktop via drag-and-drop. Two routes are ready in this repo (see [`packaging/`](packaging/)):

- **`uv` type** (`manifest.json`): the user needs `uv` + Python; the easiest build.
- **`binary` type** (PyInstaller): the user needs **nothing** (truly zero-install). On macOS/Windows the operating system will ask for a signature → this step (**signing/notarization** with an Apple Developer ID / Authenticode) depends on the packager/their cost. The code and spec are ready; see [`packaging/README.md`](packaging/README.md).

```bash
# Build the .mcpb (requires Node):
npm i -g @anthropic-ai/mcpb
cd packaging && mcpb validate manifest.json && mcpb pack
```

---

## 🗣️ Example usage (natural language to Claude)

- *"List DergiPark journals about education."* → `list_journals(subject=…)`
- *"Is the mulkiye journal in TR Dizin? Which indexes is it covered by?"* → `get_journal_info`
- *"Search the mulkiye journal for articles mentioning 'siyaset' published after 2015, sorted newest to oldest."*
- *"Give me the metadata for this article in APA and IEEE format: https://dergipark.org.tr/tr/pub/mulkiye/article/1000"*
- *"Read the full text of article 29mayisegitim/1816398 and summarize the methods section."*
- *"/literature_review topic=okul öncesi eğitim"* (prompt)

---

## ⚙️ Environment variables (optional)

| Variable | Default | Description |
|---|---|---|
| `DERGIPARK_MIN_INTERVAL` | `1.0` | Min seconds between requests (politeness). |
| `DERGIPARK_MAX_CONCURRENCY` | `1` | Number of concurrent requests. |
| `DERGIPARK_ENABLE_DISK_CACHE` | off | `1` → enables the disk cache (persistent across processes). |
| `DERGIPARK_CACHE_DIR` | platform-specific | Cache + search index directory. |

---

## 🔒 Security (prompt-injection)

Full texts/abstracts/references coming from DergiPark are **external content**. This server wraps the full text with `[EXTERNAL CONTENT] … [/EXTERNAL CONTENT]` and adds a `source_notice` to responses: this content should be treated as **data**, not as **instructions**. The client model (Claude) is guided to honor this marker.

---

## 🙏 Polite usage (good citizen)

DergiPark returns HTTP 429 on consecutive requests and does not send `Retry-After`. By default the client keeps **concurrency at 1** and a **request interval of ~1 s**, applies **exponential backoff** on 429, and identifies itself in the `User-Agent`. Please do not make these settings unnecessarily aggressive.

---

## ⚖️ Legal / ethical

DergiPark is an open-access platform; journals use various **Creative Commons** licenses (CC BY-NC, CC BY-NC-ND, etc.).

- **Metadata** (title, author, abstract) can be freely harvested via OAI-PMH — that is the protocol's purpose.
- **Full text** is fetched on demand for the end user (like a browser). If you intend to redistribute, comply with each article's **CC license** (NC: non-commercial; ND: no derivatives/modifications).
- The client obeys `robots.txt`, rate-limits its requests, and identifies itself.

This software is provided "as is"; responsibility for the use of the content rests with the user.

---

## ⚠️ Honest limitations

- **There is no cross-site (global) keyword search.** DergiPark does not offer a public general search API, and `/search` is closed off by robots. That is why `search_articles` works **within a single journal**. (Global search would require a paid server + harvesting; this project is deliberately **serverless/local**.)
- **There is no OCR.** Text cannot be physically extracted from scanned or broken-font PDFs (those without a Unicode/ToUnicode mapping). Since there is no free, key-free, friction-free OCR path for everyone (one that doesn't require a system binary), OCR is out of scope; such documents are honestly marked with **`text_reliable=false`**.
- **The subject taxonomy is in English** ("Law", "Education", "Sociology" …). When `list_journals` is called without a filter, you can see the available subjects via `available_subjects`.

---

## 🧱 Architecture

```
Client (Claude) ──MCP──> server.py (6 tools + 4 prompts + 2 resources)
                               │
   ┌─────────────┬─────────────┼───────────────┬──────────────┬───────────┐
   ▼             ▼             ▼               ▼              ▼           ▼
directory.py   oai.py        site.py         pdf.py       index.py   citations.py
(~2550 journal (OAI-PMH:     (article HTML:  (PDF→md +     (FTS5 +    (8 citation
 directory +    oai_dc +      citation_*:     section +    Turkish    formats)
 subject)       oai_mods)     affil/orcid/    reliability  fold +
                             doi + refs)     flag)         BM25)
                               │
                               ▼
                  cache.py (memory + disk) · http.py (1 req/s, conc=1, 429 backoff)
```

---

## 🧪 Development & testing

```bash
uv sync
uv run pytest -m "not live" -q     # offline (parser/pdf/cache/index/citations/prompts) — fast
uv run pytest -m live -q           # live (real DergiPark traffic — polite, slow)
uvx ruff check src/ tests/         # lint
```

**Refreshing the journal directory** (as new journals are added):

```bash
uv run python scripts/build_directory.py   # regenerates data/journals.json
```

---

## 📄 License

MIT — see [LICENSE](LICENSE).
