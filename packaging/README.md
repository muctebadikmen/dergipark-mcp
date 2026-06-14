# `.mcpb` Paketleme

Bu klasör, DergiPark MCP'yi **tek-tık kurulabilir** `.mcpb` paketine dönüştürmek için
gereken her şeyi içerir. İki yol vardır.

> Gereksinim: `npm i -g @anthropic-ai/mcpb` (paketleme CLI'si).

---

## Yol 1 — `uv` tipi (en kolay build; kullanıcıda Python + uv şart)

`manifest.json` `uv` ile çalışır. Bundle, projenin kendisini `server/` altına koyar.

```bash
# repo kökünden
mkdir -p build/uv-bundle/server
cp -R src pyproject.toml uv.lock README.md build/uv-bundle/server/
cp packaging/manifest.json build/uv-bundle/manifest.json

cd build/uv-bundle
mcpb validate manifest.json
mcpb pack          # -> dergipark-mcp.mcpb
```

Kullanıcı `.mcpb` dosyasını Claude Desktop'a sürükler. **Kullanıcının `uv` + Python'u
olmalıdır** (gerçek sıfır-kurulum değil).

---

## Yol 2 — `binary` tipi (gerçek sıfır-kurulum; kullanıcıda HİÇBİR şey gerekmez)

PyInstaller ile tek-dosya çalıştırılabilir derlenir. **Her işletim sistemi/mimari için
ayrı** build gerekir (o platformda çalıştırılmalıdır).

```bash
bash packaging/build_binary.sh          # -> packaging/dist/dergipark-mcp[.exe]

mkdir -p build/bin-bundle/server
cp packaging/dist/dergipark-mcp build/bin-bundle/server/
cp packaging/manifest.binary.json build/bin-bundle/manifest.json

cd build/bin-bundle
mcpb validate manifest.json
mcpb pack          # -> dergipark-mcp.mcpb
```

### İmzalama / notarize (KULLANICI KARARI — maliyet gerektirir)

İşletim sistemleri imzasız çalıştırılabilirleri uyarır:

- **macOS (Gatekeeper):** Apple **Developer ID** ile `codesign` + `notarytool` ile
  notarize + `stapler staple`. Apple Developer hesabı (yıllık ücret) gerekir.
- **Windows (SmartScreen):** **Authenticode** kod imzalama sertifikası ile `signtool`.

İmzalama yapılmazsa paket yine kurulabilir ama işletim sistemi ek onay isteyebilir.
`build_binary.sh` çıktısında tam komutlar yazılıdır.

---

## Dağıtım

`.mcpb` dosyalarını **GitHub Releases**'e yükleyin (her platform için ayrı binary
bundle + bir adet uv bundle). Kullanıcı indirir, çift tıklar / sürükler.

> Not: `manifest.binary.json` varsayılan olarak yalnızca `darwin` platformunu listeler.
> Başka platformlar için o platformda build alıp `compatibility.platforms`'u güncelleyin.
