# Hugging Face Spaces — DergiPark MCP (remote HTTP sunucu)
# Bu dosya HF Space reposunun KÖKÜNDE "Dockerfile" olarak bulunur.
# Kaynak kodu public GitHub reposundan kurar → her rebuild en güncel main'i alır.
FROM python:3.11-slim

# Tek bağımlılık: paketin kendisi (fastmcp, httpx, bs4, pypdf, platformdirs onunla gelir).
# git+ yerine GitHub tarball'ı kullanıyoruz → slim imajda 'git' kurmaya gerek kalmaz.
RUN pip install --no-cache-dir \
    "https://github.com/muctebadikmen/dergipark-mcp/archive/refs/heads/main.tar.gz"

# Hosted/paylaşılan ortam ayarları
ENV PORT=7860 \
    DERGIPARK_MAX_SCAN_DEFAULT=600 \
    DERGIPARK_ENABLE_DISK_CACHE=1 \
    DERGIPARK_CACHE_DIR=/tmp/dergipark-cache \
    DERGIPARK_DIRECTORY_REFRESH=0

EXPOSE 7860

# Streamable HTTP transport, 0.0.0.0:7860, MCP endpoint: /mcp
CMD ["dergipark-mcp-serve"]
