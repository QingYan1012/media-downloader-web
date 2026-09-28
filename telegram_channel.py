"""Telegram 公开频道批量：匿名读 t.me/s/<频道>，把帖子里的视频/音频/文件列出来。

为什么不把整页丢给 yt-dlp：它在这个页面上走的是 generic，标题只会是
"Europa Press (1)(2)…"，同一个视频给两条，而且不认识 ?before= —— 翻不了历史。
这里只管"有什么"，下载仍然交回 yt-dlp 逐条解析：telesco.pe 的直链带短时效
token，入队那一刻现取才拿得到活的地址，提前抓下来的链接排队时就过期了。

能匿名拿到的只有视频（页面里就有 <video src>）。文件/音频帖在匿名页上
只有文件名和大小，真链接要登录会话 —— 这类条目照样列出，但标成不可下载并
写清原因，比直接不显示诚实。
"""
from __future__ import annotations

import re
import time
from datetime import datetime
from typing import Callable, Dict, List, Optional, Tuple

import requests

TYPE_VIDEO = "video"
TYPE_AUDIO = "audio"
TYPE_DOCUMENT = "document"
TYPE_PHOTO = "photo"
TYPE_VOICE = "voice"
ALL_TYPES = (TYPE_VIDEO, TYPE_AUDIO, TYPE_DOCUMENT, TYPE_PHOTO, TYPE_VOICE)

TYPE_LABELS = {
    TYPE_VIDEO: "视频",
    TYPE_AUDIO: "音频文件",
    TYPE_DOCUMENT: "文档",
    TYPE_PHOTO: "图片",
    TYPE_VOICE: "语音",
}

AUDIO_EXT = ("mp3", "m4a", "m4b", "aac", "ogg", "oga", "opus", "wav", "flac", "wma", "aiff")

# 一次 20 条，翻页靠 ?before=<最小帖号>（实测连翻 3 页稳定往前推 20 条）
PAGE_SIZE_HINT = 20
DEFAULT_LIMIT = 60
MAX_LIMIT = 2000
DEFAULT_PAGE_SLEEP = 0.8
DEFAULT_BUDGET = 240
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

NEEDS_LOGIN_NOTE = "匿名页面只有文件名和大小，实体链接要 Telegram 登录会话"
NEEDS_APP_NOTE = "页面里没给 <video>（多为只有 App 才播的编码），yt-dlp 同样取不到地址"
PROXY_DIRECT = "direct"   # 与 server.PROXY_DIRECT 同值：只收代理字符串的地方用哨兵表"强制直连"

_SPLIT_RE = re.compile(r'data-post="(?P<post>[^"/]+)/(?P<id>\d+)"')
_TEXT_RE = re.compile(r'tgme_widget_message_text[^>]*>(?P<html>.*?)</div>', re.S)
_TIME_RE = re.compile(r'<time datetime="(?P<iso>[^"]+)"')
_VID_ANCHOR_RE = re.compile(
    r'<a[^>]*class="[^"]*js-message_video_player[^"]*"[^>]*href="(?P<href>[^"]+)"', re.S
)
_VID_SRC_RE = re.compile(r'<video[^>]+src="(?P<src>[^"]+)"', re.S)
_THUMB_RE = re.compile(r'tgme_widget_message_video_thumb[^>]*background-image:url\(\'(?P<u>[^\']+)\'\)')
_DUR_RE = re.compile(r'message_video_duration[^>]*>(?P<d>\d+:\d+(?::\d+)?)<')
_DOC_WRAP_RE = re.compile(
    r'<a[^>]*class="[^"]*tgme_widget_message_document_wrap[^"]*"[^>]*href="(?P<href>[^"]+)"'
    r'(?P<body>.*?</a>)',
    re.S,
)
_DOC_TITLE_RE = re.compile(r'tgme_widget_message_document_title[^>]*>(?P<t>[^<]*)<')
_DOC_EXTRA_RE = re.compile(r'tgme_widget_message_document_extra[^>]*>(?P<t>[^<]*)<')
_PHOTO_RE = re.compile(r'tgme_widget_message_photo_wrap')
_VOICE_RE = re.compile(r'tgme_widget_message_voice')
_TAG_RE = re.compile(r"<[^>]+>")
_EMOJI_IMG_RE = re.compile(r'<i class="emoji"[^>]*>\s*([^<]*)\s*</i>')


def normalize_channel(raw: str) -> str:
    """t.me/s/x / @x / https://t.me/x/123 / 裸名 都收敛成频道名；认不出返回空串。

    频道名只能是公开用户名，私有链接 t.me/c/<id>/... 属于必须登录那一类，
    在这里直接判死，不要到翻页时才报一堆 404。
    """
    s = str(raw or "").strip()
    if not s:
        return ""
    s = re.sub(r"^https?://", "", s, flags=re.I)
    s = re.sub(r"^www\.", "", s, flags=re.I)
    s = re.sub(r"^(?:t|telegram)\.me/", "", s, flags=re.I)
    parts = [p for p in s.split("/") if p]
    if not parts:
        return ""
    head = parts[0]
    if head.lower() == "s" and len(parts) > 1:
        head = parts[1]
    if head.lower() == "c" and len(parts) > 1:
        return ""          # 私有频道编号，匿名爬不了
    head = head.lstrip("@").strip()
    return head if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{3,31}", head) else ""


def _clean_text(html: str) -> str:
    t = _EMOJI_IMG_RE.sub(lambda m: m.group(1), html or "")
    t = _TAG_RE.sub(" ", t)
    t = (
        t.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
    )
    return re.sub(r"\s+", " ", t).strip()


def _dur_sec(text: str) -> int:
    try:
        parts = [int(x) for x in str(text or "").split(":")]
    except ValueError:
        return 0
    sec = 0
    for p in parts:
        sec = sec * 60 + p
    return sec


def parse_messages(html: str, channel: str = "") -> List[dict]:
    """把一页 t.me/s/ 解析成条目：一条帖 × 一个媒体 = 一行，纯文本函数，可离线测。"""
    items: List[dict] = []
    marks = list(_SPLIT_RE.finditer(html or ""))
    for i, m in enumerate(marks):
        ch, pid = m.group("post"), int(m.group("id"))
        if channel and ch != channel:
            continue
        chunk = html[m.start(): marks[i + 1].start() if i + 1 < len(marks) else len(html)]
        tm = _TIME_RE.search(chunk)
        iso = tm.group("iso") if tm else ""
        date = iso[:10]
        text = _clean_text((_TEXT_RE.search(chunk).group("html")) if _TEXT_RE.search(chunk) else "")
        common = {
            "id": f"{ch}-{pid}",
            "channel": ch,
            "post_id": pid,
            "url": f"https://t.me/{ch}/{pid}",
            "date": date,
            "datetime": iso,
            "text": text[:200],
        }
        seen_here = 0

        for a in _VID_ANCHOR_RE.finditer(chunk):
            tail = chunk[a.end():]
            nxt = _VID_ANCHOR_RE.search(tail)
            seg = tail[: nxt.start()] if nxt else tail
            src = _VID_SRC_RE.search(seg)
            thumb = _THUMB_RE.search(seg)
            dur = _DUR_RE.search(seg)
            items.append({
                **common,
                "type": TYPE_VIDEO,
                "title": text or f"{ch} {pid}",
                "duration": (dur.group("d") if dur else ""),
                "duration_sec": _dur_sec(dur.group("d")) if dur else 0,
                "filename": "",
                "size_text": "",
                "thumb": thumb.group("u") if thumb else "",
                "direct_url": src.group("src") if src else "",
                "downloadable": bool(src),
                "note": "" if src else NEEDS_APP_NOTE,
            })
            seen_here += 1

        for d in _DOC_WRAP_RE.finditer(chunk):
            body = d.group("body") or ""
            name = (_DOC_TITLE_RE.search(body).group("t").strip()
                    if _DOC_TITLE_RE.search(body) else "")
            size = (_DOC_EXTRA_RE.search(body).group("t").strip()
                    if _DOC_EXTRA_RE.search(body) else "")
            ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
            typ = TYPE_AUDIO if ext in AUDIO_EXT else TYPE_DOCUMENT
            items.append({
                **common,
                "type": typ,
                "title": name or text or f"{ch} {pid}",
                "duration": "",
                "duration_sec": 0,
                "filename": name,
                "size_text": size,
                "thumb": "",
                "direct_url": "",
                "downloadable": False,
                "note": NEEDS_LOGIN_NOTE,
            })
            seen_here += 1

        if not seen_here and _VOICE_RE.search(chunk):
            items.append({
                **common, "type": TYPE_VOICE, "title": text or f"{ch} {pid}",
                "duration": "", "duration_sec": 0, "filename": "", "size_text": "",
                "thumb": "", "direct_url": "", "downloadable": False,
                "note": NEEDS_LOGIN_NOTE,
            })
            seen_here += 1

        if not seen_here and _PHOTO_RE.search(chunk):
            items.append({
                **common, "type": TYPE_PHOTO, "title": text or f"{ch} {pid}",
                "duration": "", "duration_sec": 0, "filename": "", "size_text": "",
                "thumb": "", "direct_url": "", "downloadable": False,
                "note": "图片帖：本工具只做音视频，列出来是为了让历史连续",
            })
    return items


def _post_marks(html: str) -> int:
    return len(_SPLIT_RE.findall(html or ""))


def _fetch(page_url: str, params: dict, proxy: str, timeout: tuple):
    if proxy == PROXY_DIRECT:
        proxies = {"http": None, "https": None}   # 显式压过系统代理
    elif proxy:
        proxies = {"http": proxy, "https": proxy}
    else:
        proxies = None                            # 不干预，跟随系统
    r = requests.get(page_url, params=params, headers={"User-Agent": UA},
                     proxies=proxies, timeout=timeout)
    return r.status_code, r.text


def list_channel_history(
    channel_raw: str,
    *,
    limit: int = DEFAULT_LIMIT,
    types: Optional[List[str]] = None,
    since: str = "",
    until: str = "",
    budget: int = DEFAULT_BUDGET,
    page_sleep: float = DEFAULT_PAGE_SLEEP,
    proxy: str = "",
    timeout: tuple = (10, 30),
    log: Callable = print,
) -> Tuple[List[dict], dict]:
    """从最新往最早翻 t.me/s/<频道>，直到够数/够日期/没历史/预算用完。

    返回 (条目, 诊断)。诊断里的 stopped 是给人看的收尾结论 —— 批量爬最怕
    不声不响少给一半，翻到哪儿了必须说清。
    """
    ch = normalize_channel(channel_raw)
    diag = {"channel": ch, "pages": 0, "media_posts": 0, "matched": 0,
            "stopped": "", "errors": {}, "budget": int(budget or 0)}
    if not ch:
        diag["stopped"] = "频道名无效（私有 t.me/c/ 链接匿名爬不了）"
        return [], diag
    want = set(types) if types else {TYPE_VIDEO}
    cap = max(1, min(int(limit or DEFAULT_LIMIT), MAX_LIMIT))
    t0 = time.time()

    def in_window(d: str) -> bool:
        if since and d and d < since:
            return False
        if until and d and d > until:
            return False
        return True

    out: List[dict] = []
    seen_ids: set = set()
    before = 0
    page_url = f"https://t.me/s/{ch}"
    while len(out) < cap:
        params = {"before": before} if before else None
        try:
            status, html = _fetch(page_url, params, proxy, timeout)
        except Exception as e:
            diag["errors"][f"第 {diag['pages'] + 1} 页"] = f"{type(e).__name__}: {e}"
            diag["stopped"] = "网络中断，已按拿到的部分继续"
            break
        diag["pages"] += 1
        if status in (429, 420):
            diag["stopped"] = f"被 t.me 限流（HTTP {status}），歇一会儿再翻"
            diag["errors"][f"第 {diag['pages']} 页"] = f"HTTP {status} Flood Wait"
            break
        if status != 200:
            diag["stopped"] = f"第 {diag['pages']} 页返回 HTTP {status}"
            diag["errors"][f"第 {diag['pages']} 页"] = f"HTTP {status}"
            break
        rows = parse_messages(html, ch)
        if not _post_marks(html):
            # 不存在的频道照样回 200，只是给一张 "Telegram: Contact @x" 占位页
            diag["stopped"] = "页面一条帖子都没有：频道不存在、名字打错，或它没开放网页预览"
            diag["errors"][f"第 {diag['pages']} 页"] = "200 但没有帖子（占位页）"
            break
        ids = {r["post_id"] for r in rows}
        diag["media_posts"] += len(ids)
        if not ids or not (ids - seen_ids):
            diag["stopped"] = "到底了：这个频道没有更早的历史"
            break
        seen_ids |= ids
        newest_older_stop = False
        for r in sorted(rows, key=lambda x: -x["post_id"]):
            if r["type"] not in want:
                continue
            if not in_window(r["date"]):
                if since and r["date"] and r["date"] < since:
                    newest_older_stop = True
                continue
            out.append(r)
            if len(out) >= cap:
                break
        if len(out) >= cap:
            diag["stopped"] = f"已到数量上限 {cap} 条"
            break
        if newest_older_stop:
            diag["stopped"] = f"已翻到 {since} 之前，按日期收工"
            break
        before = min(ids)
        if budget and (time.time() - t0) > budget:
            diag["stopped"] = f"翻页预算 {budget}s 用完，先给拿到的 {len(out)} 条"
            break
        time.sleep(max(0.0, float(page_sleep)))

    if not diag["stopped"]:
        diag["stopped"] = "收工" if out else "没找到匹配的媒体（换个类型或放宽日期）"
    diag["matched"] = len(out)
    diag["no_link"] = sum(1 for r in out if not r["downloadable"])
    if out and diag["no_link"] == len(out):
        diag["stopped"] += f"；{diag['no_link']} 条全都拿不到匿名直链，得登录会话才下得动"
    elif diag["no_link"]:
        diag["stopped"] += f"（其中 {diag['no_link']} 条只能列出、匿名下不动）"
    diag["elapsed"] = round(time.time() - t0, 1)
    log(f"Telegram 爬取: 频道={ch} 翻 {diag['pages']} 页 / 含媒体帖 {diag['media_posts']}"
        f" → {len(out)} 条 · {diag['elapsed']}s ｜ {diag['stopped']}")
    for k, v in diag["errors"].items():
        log(f"  [{k}] {v}", "warning")
    return out, diag
