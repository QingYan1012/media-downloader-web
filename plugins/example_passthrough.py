"""示例：直链 / m3u8 放行（可复制改写成站点专用解析）。"""

NAME = "直链/HLS 透传"
DESCRIPTION = "匹配已是媒体文件或 HLS 的 URL，设置 use_hls_engine / direct_cdn"
PRIORITY = 200  # 数字越小越优先

import re


def match(url: str) -> bool:
    u = (url or "").lower()
    return bool(
        re.search(r"\.(m3u8|mpd|mp4|flv|mkv|webm|m4s)(\?|$)", u)
        or "/hls/" in u
        or "/hls3/" in u
        or "/dash/" in u
    )


def resolve(url: str, ctx: dict) -> dict:
    low = (url or "").lower()
    opts = {}
    if any(x in low for x in (".m3u8", ".mpd", "/hls", "/dash")):
        opts["use_hls_engine"] = True
        opts["direct_cdn"] = False
    else:
        opts["direct_cdn"] = True
    return {"urls": [url], "title": "", "options": opts}
