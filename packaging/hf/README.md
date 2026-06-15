---
title: DergiPark MCP
emoji: 📚
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: DergiPark Türk akademik dergileri için MCP sunucusu (OAI-PMH)
---

# DergiPark MCP — uzak (remote) sunucu

DergiPark (Türk akademik dergileri) için **Model Context Protocol (MCP)** sunucusu —
resmî OAI-PMH servisini kullanır; anahtarsız, CAPTCHA'sız, robots.txt'e uyumlu.
~2.550 dergiyi keşfeder, dergi içinde Türkçe-duyarlı arama yapar, zengin künye +
8 atıf formatı + tam metin sağlar.

## Bağlanma (Claude)

**MCP endpoint:**

```
https://mmd1999-dergipark-mcp.hf.space/mcp
```

Claude (Desktop veya claude.ai) → **Settings → Connectors → Add custom connector** →
yukarıdaki URL'yi yapıştır → **Add**. Yapılandırma dosyası gerekmez; tarayıcıda da çalışır.

## Notlar

- İlk istek, sunucu uykudaysa ~30–60 sn (HF ücretsiz katman) + bir dergi ilk kez
  arandığında kısa bir tarama (harvest) gerektirebilir.
- Kaynak kod (MIT): <https://github.com/muctebadikmen/dergipark-mcp>
