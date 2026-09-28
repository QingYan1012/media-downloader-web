# URL 解析插件

`match` + `resolve` 写入本目录 `*.py`（勿以 `_` 开头）。按 mtime **热加载**，或调用 `POST /api/plugins/reload`。

## 约定

- NAME / DESCRIPTION / PRIORITY（越小越先）
- match(url) -> bool
- resolve(url, ctx) -> {urls, title?, options?}
- options 可含: use_hls_engine, direct_cdn, http_headers, referer, cookie, proxy

## 示例

- example_passthrough.py — 直链/HLS
- site_b23_short.py — B站短链 + Referer
