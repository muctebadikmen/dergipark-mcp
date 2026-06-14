#!/usr/bin/env bash
# PyInstaller ile tek-dosya, sıfır-kurulum çalıştırılabilir üretir ve onu
# .mcpb (binary tipi) paketine hazırlar.
#
# Her İŞLETİM SİSTEMİ/MİMARİ için ayrı çalıştırılmalıdır (darwin-arm64, darwin-x64,
# win32-x64, linux-x64). Çıktı: dist/dergipark-mcp[.exe]
#
# Kullanım:  bash packaging/build_binary.sh
set -euo pipefail

cd "$(dirname "$0")/.."

echo "==> Bağımlılıklar senkronize ediliyor"
uv sync

echo "==> Gömülü dizin güncel mi? (data/journals.json)"
test -s src/dergipark_mcp/data/journals.json || uv run python scripts/build_directory.py

echo "==> PyInstaller ile derleniyor"
uv run --with pyinstaller pyinstaller packaging/dergipark_mcp.spec \
  --distpath packaging/dist --workpath packaging/build --noconfirm

echo "==> Çıktı:"
ls -lh packaging/dist/

cat <<'NOTE'

------------------------------------------------------------------------
SONRAKİ ADIMLAR (PAKETLEYEN KİŞİ / KULLANICI KARARI):

macOS — Gatekeeper için imzala + notarize et:
  codesign --deep --force --options runtime \
    --sign "Developer ID Application: ADINIZ (TEAMID)" packaging/dist/dergipark-mcp
  # sonra notarytool ile notarize + staple

Windows — SmartScreen için Authenticode imzası:
  signtool sign /fd sha256 /a packaging\dist\dergipark-mcp.exe

İmzalama bir Apple Developer ID / kod imzalama sertifikası (ücretli) gerektirir.
İmzasız binary de çalışır ama işletim sistemi ek onay isteyebilir.

.mcpb paketi (binary tipi):
  cp packaging/manifest.binary.json <bundle>/manifest.json
  cp packaging/dist/dergipark-mcp   <bundle>/server/dergipark-mcp
  cd <bundle> && mcpb pack
------------------------------------------------------------------------
NOTE
