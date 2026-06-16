# DergiPark MCP

🇹🇷 [Türkçe](README.md) · 🇬🇧 English (this file)

A **Model Context Protocol (MCP)** server for [DergiPark](https://dergipark.org.tr) (Turkey's TÜBİTAK ULAKBİM academic journal platform). It lets Claude (Desktop / claude.ai / mobile) and other MCP clients discover **~2,550 DergiPark journals**, run **Turkish-aware** search (within a journal **and** cross-journal), do author-based discovery, find similar articles, generate rich metadata + **8 citation formats**, and read full texts (PDF).

> ⚡ **Easiest use: no installation.** Paste a single URL into Claude — no app, no config, no Python. [→ Get started](#-fastest-install-paste-a-url-recommended)

---

## 🚀 Fastest install: paste a URL (recommended)

This MCP is live as an **online server** (Hugging Face Spaces, free). With no downloads, a **single URL** adds it in a few clicks — and it works in **Claude Desktop, claude.ai (browser), and mobile**.

**1) Copy this URL:**

```
https://muctebadikmen-dergipark-mcp.hf.space/mcp
```

**2) Connect in Claude:** **Settings → Connectors → Add custom connector** → paste the URL → **Add**.

**3) Test it:** ask Claude:
> *"Find DergiPark articles on legal history from several different journals."*

That's it. No config file, no `uv`/Python, no drag-and-drop.

> ℹ️ **Honest note:** the free server sleeps after long idle (~48h); the first request takes **~30–60s** to wake, then it's fast. It's open and keyless — anyone with the URL can use it (an open academic tool).

<details>
<summary>🖥️ Want to run it <b>locally</b> on your own machine? (advanced / optional)</summary>

The URL method is enough for most people. But if you want to run the server **on your own machine** (privacy, offline cache, no dependency on the hosted server), there are two ways. Both require `uv` (a Python manager).

### a) One-line `uvx` (recommended local method)

**1) Install `uv`:**
- macOS / Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`
- Windows (PowerShell): `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"` (then reopen the terminal)

**2) Claude Desktop → Settings → Developer → Edit Config** (opens `claude_desktop_config.json`).

**3) Add this block:**
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

**4) Save and fully quit-and-reopen Claude Desktop** (**Cmd+Q** on Mac).

- *"uvx not found":* use the full path — `which uvx` (Mac/Linux), `where uvx` (Windows).
- *Update:* `uvx --refresh --from git+https://github.com/muctebadikmen/dergipark-mcp dergipark-mcp`

### b) `.mcpb` file (drag-and-drop)
Download `.mcpb` from [Releases](https://github.com/muctebadikmen/dergipark-mcp/releases/latest) → Claude Desktop → Settings → Extensions/Connectors → drag onto the window. (Also needs `uv` + Python; on macOS Tahoe 26.x extension installs may silently fail due to a known bug — use the URL method or (a) instead.)

### c) Claude Code (CLI)
```bash
claude mcp add --transport http dergipark https://muctebadikmen-dergipark-mcp.hf.space/mcp   # hosted URL
# or local:
claude mcp add dergipark -- uvx --from git+https://github.com/muctebadikmen/dergipark-mcp dergipark-mcp
```
</details>

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

> **Design principle:** Only **OAI-PMH** (`/api/public/oai/`), open **article pages** (`/pub/.../article/...`), **PDF downloads** (`/download/...`), and the **journal directory** are used. The `/search` and `/login` paths disallowed by `robots.txt` are **never** touched.

---

## What does it do?

### 🔧 Tools (10)

| Tool | Description |
|---|---|
| `list_journals` | Search the **full directory** (~2,550 journals) by name/slug + **subject**; paginated. Self-updates in the background. |
| `get_journal_info` | A journal's masthead + **index/directory membership** (TR Dizin, DOAJ, Scopus, EBSCO, SOBIAD…) and the `tr_dizin` flag — critical for promotion/incentives. |
| `list_journal_articles` | List a journal's articles (date-filtered, paginated). |
| `search_articles` | Turkish-aware keyword search **within ONE journal** (SQLite FTS5 + BM25). Year/author/type filters, sorting, pagination. |
| `search_all_journals` | **Cross-journal** search — a topic across **several / different journals** at once. Searches the indexed pool; reports coverage honestly. |
| `find_author` | **Author-based discovery** — all of an author's articles in the pool. No topic needed; name-order independent ("Aybars Pamir" ≈ "Pamir, Aybars"). |
| `related_articles` | Articles **similar/related** to a given one (keyword + title overlap) — literature "snowballing". |
| `get_article` | Rich metadata: author **+ affiliation + ORCID**, DOI, ISSN, volume/issue/page, keywords + **8 citation formats**. |
| `get_article_fulltext` | Downloads the PDF and converts it to Markdown; **section map** (ABSTRACT/INTRODUCTION/METHODS/…/REFERENCES), page-by-page navigation. For broken/scanned text it **honestly** reports `text_reliable=false`. |
| `get_article_references` | The article's complete reference (bibliography) list. |

### 💬 Prompts (4) — ready-made research workflows

`literature_review` · `summarize_article` · `compare_articles` · `research_discovery`. They appear in the "/" menu in Claude Desktop.

### 📦 Resources (2)

`dergipark://journal/{slug}` · `dergipark://article/{id}`

### ✨ Highlights

- **Cross-journal search (new):** search a topic across **all major fields** (law, economics, sociology, education, theology, medicine, philosophy…) over **221 journals / ~37k articles** instantly — thanks to a **baked index** shipped with the server. Journals not in the pool are added on demand via `search_articles` (nothing is limited; all 2,548 journals are always reachable).
- **Turkish-aware search:** `İ/ı/ş/ğ/ü/ö/ç` are folded → "eğitim" ≈ "Eğitim" ≈ "egitim"; prefix matching; for multi-word queries, exact-phrase and title matches rank higher.
- **8 citation formats:** APA, MLA, IEEE, Chicago, Harvard, BibTeX, RIS, CSL-JSON — with Turkish characters preserved.
- **Rich metadata:** structured authors (given/family), **affiliation, ORCID**, DOI, ISSN — merging `oai_dc` + `oai_mods` + the article HTML.
- **TR-Dizin/index badges:** TR Dizin/ULAKBİM, DOAJ, Scopus, EBSCO, SOBIAD membership + the `tr_dizin` flag.
- **Honesty:** broken-font/scanned PDFs are not presented as "real text" (`text_reliable=false`). Cross-journal coverage (how many/which journals) is reported in every response.

---

## 🔑 Key concept: **slug**

A journal is accessed by its **slug** — the `/pub/<slug>/` part of its DergiPark URL:

```
https://dergipark.org.tr/tr/pub/mulkiye/...   ->   slug = "mulkiye"
```

Find a slug with `list_journals`, or use one you already know.

---

## 🗣️ Example usage (natural language to Claude)

- *"Find DergiPark articles on legal history from **several different journals**."* → `search_all_journals`
- *"List **Belkıs Konan**'s articles on DergiPark."* → `find_author`
- *"Suggest articles **similar** to dergipark.org.tr/.../article/1071191"* → `related_articles`
- *"List DergiPark journals on education."* → `list_journals(subject=…)`
- *"Is the mulkiye journal in TR Dizin?"* → `get_journal_info`
- *"In mulkiye, find articles with 'siyaset' after 2015, newest first."* → `search_articles`
- *"Give the citation for .../article/1000 in APA and IEEE."* → `get_article`
- *"Read the full text of 29mayisegitim/1816398 and summarize the methods."* → `get_article_fulltext`
- *"/literature_review topic=early childhood education"* (prompt)

---

## ⚙️ Environment variables (optional — local runs)

| Variable | Default | Description |
|---|---|---|
| `DERGIPARK_MIN_INTERVAL` | `1.0` | Min seconds between requests (politeness). |
| `DERGIPARK_MAX_CONCURRENCY` | `1` | Concurrent requests. |
| `DERGIPARK_MAX_SCAN_DEFAULT` | `2000` | Default `search_articles` scan depth (lowered on hosted). |
| `DERGIPARK_ENABLE_DISK_CACHE` | off | `1` → enables disk cache (persists across processes). |
| `DERGIPARK_CACHE_DIR` | platform-specific | Cache + search-index directory. |
| `DERGIPARK_SEED_INDEX` | bundled | Path to the baked seed index (`.db` or `.db.gz`). |

---

## ⚠️ Honest limitations

- **Cross-journal search is limited to the indexed pool.** DergiPark offers no public site-wide search API and `/search` is robots-blocked. `search_all_journals` searches the baked **221-journal** pool (+ journals harvested in the session) — **not all 2,548 instantly.** A journal not in the pool is harvested **instantly** via `search_articles(journal=…)` and joins the pool; so no journal/field is permanently excluded.
- **No OCR.** Scanned/broken-font PDFs cannot yield real text. With no free, keyless, frictionless OCR path available, it's out of scope; such documents are marked `text_reliable=false`.
- **The subject taxonomy is in English** ("Law", "Education", "Sociology"…). Call `list_journals` with no filter to see `available_subjects`.

---

## 🔒 Security (prompt-injection)

Full text/abstracts/references from DergiPark are **external content**. The server wraps full text in `[EXTERNAL CONTENT] … [/EXTERNAL CONTENT]` and adds a `source_notice`: treat it as **data**, not **instructions**.

## 🙏 Good citizen

DergiPark returns HTTP 429 on rapid requests and sends no `Retry-After`. The client keeps **concurrency 1**, **~1s** spacing, applies **exponential backoff** on 429/transient 5xx, and identifies itself in the `User-Agent`.

## ⚖️ Legal / ethics

DergiPark is open-access; journals use various **Creative Commons** licenses.

- **Metadata** (title, author, abstract) may be freely harvested via OAI-PMH — that's the protocol's purpose.
- **Full text** is fetched on demand for the end user. If you redistribute, honor each article's **CC license** (NC: non-commercial; ND: no derivatives).
- The client respects `robots.txt`, rate-limits, and identifies itself.

Provided "as is"; responsibility for content use lies with the user.

---

## 🧱 Architecture

```
Client (Claude)  ──MCP──>  server.py (10 tools + 4 prompts + 2 resources)
   • Hosted: https://muctebadikmen-dergipark-mcp.hf.space/mcp  (HTTP)
   • Local:  uvx / .mcpb  (stdio)
                               │
   ┌─────────────┬─────────────┼───────────────┬──────────────┬───────────┐
   ▼             ▼             ▼               ▼              ▼           ▼
directory.py   oai.py        site.py         pdf.py       index.py   citations.py
(~2550 journal (OAI-PMH:     (article HTML:  (PDF→md +     (FTS5 +    (8 citation
 directory +    oai_dc +      citation_*:     section +    Turkish    formats)
 subject)       oai_mods)     affil/orcid/    reliability  fold + BM25 +
                             doi + refs)     flag)         baked seed)
                               │
                               ▼
                  cache.py (memory + disk) · http.py (1 req/s, conc=1, 429/5xx backoff)
```

The hosted build ships a bundled, gzipped **seed index** (`data/seed_index.db.gz`, 221 journals / ~37k articles); it's decompressed at startup to make cross-journal search **warm**.

---

## 🧪 Development & testing

```bash
uv sync
uv run pytest -m "not live" -q     # offline (fast): parser/pdf/cache/index/citations/prompts
uv run pytest -m live -q           # live (real DergiPark traffic — polite, slow)
uvx ruff check src/ tests/         # lint
```

**Refresh the journal directory:**
```bash
uv run python scripts/build_directory.py    # regenerates data/journals.json
```

**(Re)build the baked seed index** (to grow/refresh the cross-journal pool):
```bash
uv run python scripts/build_index.py --slugs <comma-separated slugs> --max-records 300 --max-db-mb 190
gzip -9 -c <out.db> > src/dergipark_mcp/data/seed_index.db.gz
```

---

## 📄 License

MIT — see [LICENSE](LICENSE).
