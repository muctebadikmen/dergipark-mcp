"""Seed indeksi üretici — seçili dergileri önceden harvest edip taşınabilir bir
``index.db``'ye yazar.

Üretilen dosya pakete ``data/seed_index.db`` olarak gömülür (pyproject force-include)
ve sunucu açılışında seed olarak yüklenir → ``search_all_journals`` (dergiler-arası
arama) ilk istekte SICAK olur, soğuk-harvest beklemesi olmaz.

Robots/nezaket: harvest, projenin http katmanı üzerinden saniyede 1 istek + 5xx
retry ile yapılır (DergiPark OAI'ye kibar). Bir dergi patlarsa diğerleri devam eder.

Kullanım:
  uv run python scripts/build_index.py --subject Law --max-records 2000
  uv run python scripts/build_index.py --slugs mulkiye,ihm,khm
  uv run python scripts/build_index.py --subject Law --limit-journals 5 --out /tmp/seed.db
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# src-layout: editable kurulum olmadan da paket import edilebilsin.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from dergipark_mcp import directory, http, oai  # noqa: E402
from dergipark_mcp.index import SearchIndex  # noqa: E402

DEFAULT_OUT = (
    Path(__file__).resolve().parent.parent / "src" / "dergipark_mcp" / "data" / "seed_index.db"
)


def _select_slugs(args: argparse.Namespace) -> list[str]:
    if args.slugs:
        return [s.strip().strip("/") for s in args.slugs.split(",") if s.strip()]
    entries = directory.embedded_entries()
    if args.query or args.subject:
        entries = directory.filter_journals(entries, query=args.query, subject=args.subject)
    slugs = [e.slug for e in entries]
    if args.limit_journals:
        slugs = slugs[: args.limit_journals]
    return slugs


async def _build(slugs: list[str], out: Path, max_records: int) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    idx = SearchIndex(str(out))
    total_new = 0
    ok = 0
    for i, slug in enumerate(slugs, 1):
        try:
            articles = await oai.list_records(slug, max_records=max_records)
        except Exception as exc:  # noqa: BLE001 — bir dergi patlarsa diğerleri devam etsin
            print(f"[{i}/{len(slugs)}] {slug}: HATA {exc!r} — atlandı", flush=True)
            continue
        added = idx.index_articles(slug, articles)
        idx.mark_harvested(slug, len(articles), complete=len(articles) < max_records)
        total_new += added
        ok += 1
        print(
            f"[{i}/{len(slugs)}] {slug}: {len(articles)} makale ({added} yeni) "
            f"| havuz: {total_new}",
            flush=True,
        )
    idx.close()
    await http.aclose()
    size_mb = out.stat().st_size / 1e6 if out.exists() else 0.0
    print(
        f"\nBitti → {out}\n  {ok}/{len(slugs)} dergi, {total_new} makale, {size_mb:.1f} MB",
        flush=True,
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="DergiPark seed indeksi üretici")
    ap.add_argument("--slugs", help="Virgülle ayrılmış dergi slug'ları (ör. mulkiye,ihm)")
    ap.add_argument("--query", help="Dergi ADI/slug filtresi (ör. 'hukuk' → hukuk dergileri)")
    ap.add_argument("--subject", help="Konu filtresi (taksonomi İngilizce, ör. 'Law')")
    ap.add_argument("--max-records", type=int, default=2000, help="Dergi başına en fazla makale")
    ap.add_argument("--limit-journals", type=int, default=0, help="En fazla dergi (0=sınırsız; test için)")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="Çıktı index.db yolu")
    args = ap.parse_args()

    if not (args.slugs or args.query or args.subject):
        ap.error("En az bir seçici verin: --slugs, --query veya --subject (tümünü bake etmeyi önler).")
    slugs = _select_slugs(args)
    if not slugs:
        ap.error("Seçilen dergi yok — filtreyi gözden geçirin.")
    print(
        f"{len(slugs)} dergi harvest edilecek (max_records={args.max_records}) → {args.out}\n",
        flush=True,
    )
    asyncio.run(_build(slugs, Path(args.out), args.max_records))


if __name__ == "__main__":
    main()
