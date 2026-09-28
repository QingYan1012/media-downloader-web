"""示例包：B站短链 b23.tv / bilibili.com/video 规范化。"""

NAME = "B站短链规范化"
DESCRIPTION = "把 b23.tv 或 av/BV 形态整理成标准视频页（真正解析仍交给 yt-dlp）"
PRIORITY = 50

import re


def match(url: str) -> bool:
    u = (url or "").lower()
    return "b23.tv" in u or bool(re.search(r"bilibili\.com/video/(av\d+|BV[\w]+)", url or "", re.I))


def resolve(url: str, ctx: dict) -> dict:
    # 不替换最终流，只保证入口 URL 干净并带上推荐选项
    u = (url or "").strip()
    m = re.search(r"(https?://(?:www\.)?bilibili\.com/video/(?:av\d+|BV[\w]+))", u, re.I)
    if m:
        u = m.group(1)
    opts = {
        "bilibili_m4s": True,
        "http_headers": {
            "Referer": "https://www.bilibili.com",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
        },
    }
    return {"urls": [u], "title": "", "options": opts}
