"""FastMCP Cloud / Prefect Horizon giriş noktası.

Horizon panelinde **Entrypoint** olarak ``main.py:mcp`` verin. Bu dosya tek iş yapar:
FastMCP sunucu nesnesini (``mcp``) modül düzeyinde dışa açar. Horizon onu içe aktarıp
HTTP üzerinden yayınlar (kod değişikliği gerekmez; ``mcp.run()`` çağrılmaz).

src-layout kullandığımız için paketi içe aktarmadan önce ``src/`` dizinini yola ekliyoruz;
böylece Horizon projeyi editable kurmasa bile ``dergipark_mcp`` içe aktarılabilir kalır.

Yerel (stdio) çalıştırma için bu dosya GEREKMEZ — onun için ``dergipark-mcp`` script'i
(``dergipark_mcp.server:main``) kullanılır.
"""

from __future__ import annotations

import os
import sys

_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from dergipark_mcp.server import mcp  # noqa: E402

__all__ = ["mcp"]
