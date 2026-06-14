"""PyInstaller giriş noktası — tek-dosya çalıştırılabilir için.

`dergipark_mcp` paketini içe alıp sunucuyu stdio üzerinden başlatır.
"""

from dergipark_mcp.server import main

if __name__ == "__main__":
    main()
