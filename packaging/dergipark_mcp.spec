# PyInstaller spec — tek-dosya, sıfır-kurulum çalıştırılabilir üretir.
#
# Kullanım (build_binary.sh bunu çağırır):
#   uv run --with pyinstaller pyinstaller packaging/dergipark_mcp.spec --noconfirm
#
# Çıktı: dist/dergipark-mcp (macOS/Linux) veya dist/dergipark-mcp.exe (Windows).
# Gömülü dergi dizini (journals.json) datas ile pakete dahil edilir.

import importlib.util
from pathlib import Path

from PyInstaller.utils.hooks import copy_metadata, collect_submodules

pkg = Path(importlib.util.find_spec("dergipark_mcp").origin).parent
datas = [(str(pkg / "data" / "journals.json"), "dergipark_mcp/data")]

# KRİTİK: fastmcp/mcp çalışma anında importlib.metadata.version("fastmcp") çağırır.
# Dist metadata pakete dahil edilmezse binary açılışta PackageNotFoundError ile çöker.
# (Doğrulandı: bu olmadan binary başlamaz.)
for dist in ("fastmcp", "mcp", "pydantic", "httpx", "platformdirs"):
    try:
        datas += copy_metadata(dist, recursive=True)
    except Exception:
        pass

# FastMCP ve bağımlılıkları bazı modülleri dinamik içe alır → gizli importlar.
hiddenimports = [
    "dergipark_mcp",
    "dergipark_mcp.server",
    "dergipark_mcp.oai",
    "dergipark_mcp.site",
    "dergipark_mcp.pdf",
    "dergipark_mcp.index",
    "dergipark_mcp.cache",
    "dergipark_mcp.directory",
    "dergipark_mcp.citations",
    "dergipark_mcp.prompts",
]
hiddenimports += collect_submodules("fastmcp") + collect_submodules("mcp")

a = Analysis(
    ["launcher.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="dergipark-mcp",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,          # stdio MCP — konsol gerekir (stdout JSON-RPC, stderr log)
    disable_windowed_traceback=False,
    target_arch=None,      # ana makine mimarisi (darwin-arm64 vb.)
    codesign_identity=None,  # imzalama build_binary.sh / kullanıcı tarafından yapılır
    entitlements_file=None,
)
