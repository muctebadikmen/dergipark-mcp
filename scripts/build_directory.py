#!/usr/bin/env python3
"""Tam dergi dizinini DergiPark keşif sayfalarından toplar ve pakete gömülü
``src/dergipark_mcp/data/journals.json`` dosyasına yazar.

Çalıştırma:  uv run python scripts/build_directory.py

Nazik (1 req/s, conc=1) çalışır; ~26 sayfa → birkaç dakika. Çıktı, çalışma anında
gömülü dizin olarak kullanılır; yeniden üretmek için bu betiği periyodik çalıştırın.
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from dergipark_mcp import directory, http  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "src" / "dergipark_mcp" / "data" / "journals.json"


async def main() -> None:
    print("DergiPark dergi dizini toplanıyor (nazik, ~1 req/s)…", file=sys.stderr)
    entries = await directory.harvest_directory()
    await http.aclose()

    entries.sort(key=lambda e: e.slug)
    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": directory.DIRECTORY_URL,
        "count": len(entries),
        "journals": [e.to_dict() for e in entries],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    # Kompakt (girintisiz) — gömülü veri; insan-okuması için değil, hız/boyut için.
    OUT.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )

    subjects = directory.subject_counts(entries)
    print(f"✓ {len(entries)} dergi yazıldı → {OUT}", file=sys.stderr)
    print(f"✓ {len(subjects)} farklı konu etiketi", file=sys.stderr)
    print("  En yaygın 8 konu:", file=sys.stderr)
    for sub, n in list(subjects.items())[:8]:
        print(f"    {n:4d}  {sub}", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
