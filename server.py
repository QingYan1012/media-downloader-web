#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多媒体下载器 Web 版 — FastAPI + Element Plus
启动: python server.py
浏览器访问: http://127.0.0.1:8765
"""
from __future__ import annotations

import asyncio
import base64
import errno
import hashlib
import hmac
import io
import json
import os
import re
import secrets
import shlex
import shutil
import subprocess
import sys
import threading
import time
import uuid
import zipfile
from queue import Empty as QueueEmpty, Full as QueueFull, Queue as ThreadQueue
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import parse_qsl, parse_qs, quote, unquote, urlencode, urlsplit, urlunsplit

import requests
from fastapi import UploadFile, File, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# -------------------- 路径（工具/Cookie 均在项目目录内）--------------------
HOME = Path.home()
APP_DIR = Path(__file__).resolve().parent
# 便携版的内嵌 Python 带 python312._pth，sys.path 会被锁死在 runtime 里：既不加
# 入口脚本所在目录，也不认 PYTHONPATH。于是同目录的 music_search / voice_tools 等
# 全部 ModuleNotFoundError（视频下载不受影响，只有这些按需导入的功能会炸）。
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))
import pkg_update  # noqa: E402  同目录模块，必须等上面的 sys.path 引导之后才导得到
import risk_control  # noqa: E402  同上：站点风控 / 登录墙 / 限流的判定
import bt_trackers  # noqa: E402  同上：磁力/种子的 tracker 来源清单与运行时抓取
TOOLS_DIR = APP_DIR / "tools"              # FFmpeg、yt-dlp
# 容器/服务化部署时把可变状态整体挪到一个目录（挂一卷就走），代码与工具仍留在 APP_DIR。
# 不设这个环境变量时 STATE_DIR == APP_DIR，本机行为与历史完全一致。
STATE_DIR = Path(os.environ.get("MEDIADOWNLOADER_STATE_DIR") or APP_DIR)
COOKIES_DIR = STATE_DIR / "cookies"          # Cookie 文件
DEFAULT_COOKIE_FILE = COOKIES_DIR / "cookies.txt"
CONFIG_FILE = STATE_DIR / "config.json"
HISTORY_FILE = STATE_DIR / "history.json"
SUBS_FILE = STATE_DIR / "subscriptions.json"
LIVE_MONITORS_FILE = STATE_DIR / "live_monitors.json"
MUSIC_FAVS_FILE = STATE_DIR / "music_favorites.json"   # 自建音乐收藏清单（跨源聚合的一单）
NOTIFY_OUTBOX_FILE = STATE_DIR / "notify_outbox.json"  # 没送出去的通知（重启后接着补发）
AUTH_STATE_FILE = STATE_DIR / "login_state.json"       # 登录失败计数与锁定名单（重启后仍在）
COOKIECLOUD_STATE_FILE = STATE_DIR / "cookiecloud_state.json"  # CookieCloud 上次拉/推的时间与条数
CLEANUP_STATE_FILE = STATE_DIR / "cleanup_state.json"          # 按龄清理上次跑的时间与结果
LOG_FILE = STATE_DIR / "app.log"
DEFAULT_DOWNLOAD_DIR = STATE_DIR / "Downloads"  # 项目内 Downloads
WHISPER_DIR = APP_DIR / "Whisper"             # 本地 Whisper 目录
PLUGINS_DIR = APP_DIR / "plugins"            # URL 解析插件

for _d in (TOOLS_DIR, COOKIES_DIR, DEFAULT_DOWNLOAD_DIR, WHISPER_DIR, PLUGINS_DIR):
    _d.mkdir(parents=True, exist_ok=True)


_PLUGIN_CACHE: Dict[str, Any] = {"mtime": 0.0, "mods": []}


def _plugins_dir_mtime() -> float:
    if not PLUGINS_DIR.is_dir():
        return 0.0
    mt = 0.0
    for path in PLUGINS_DIR.glob("*.py"):
        try:
            mt = max(mt, path.stat().st_mtime)
        except Exception:
            pass
    return mt


def load_url_plugins(force: bool = False) -> List[Any]:
    """加载 plugins/*.py（match/resolve）。按目录 mtime 热更新。"""
    global _PLUGIN_CACHE
    mt = _plugins_dir_mtime()
    if not force and _PLUGIN_CACHE["mods"] and abs(mt - float(_PLUGIN_CACHE["mtime"])) < 0.01:
        return list(_PLUGIN_CACHE["mods"])
    plugins = []
    if not PLUGINS_DIR.is_dir():
        _PLUGIN_CACHE = {"mtime": mt, "mods": plugins}
        return plugins
    for path in sorted(PLUGINS_DIR.glob("*.py")):
        if path.name.startswith("_"):
            continue
        try:
            import importlib.util
            # 文件名+mtime 作模块名，避免热加载缓存旧代码
            spec = importlib.util.spec_from_file_location(
                f"md_plugin_{path.stem}_{int(path.stat().st_mtime)}", path
            )
            if not spec or not spec.loader:
                continue
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            if callable(getattr(mod, "match", None)) and callable(getattr(mod, "resolve", None)):
                mod.__plugin_file__ = path.name  # type: ignore
                plugins.append(mod)
        except Exception as e:
            print(f"[plugin] load {path.name} failed: {e}")
    _PLUGIN_CACHE = {"mtime": mt, "mods": plugins}
    return plugins


def list_url_plugins() -> List[dict]:
    mods = load_url_plugins()
    out = []
    for m in mods:
        out.append({
            "file": getattr(m, "__plugin_file__", path_name(m)),
            "name": getattr(m, "NAME", path_name(m)),
            "description": getattr(m, "DESCRIPTION", ""),
            "priority": int(getattr(m, "PRIORITY", 100)),
        })
    out.sort(key=lambda x: x["priority"])
    return out


def try_resolve_with_plugins(url: str, ctx: Optional[dict] = None) -> Optional[dict]:
    """返回插件 resolve 结果或 None。按 PRIORITY 升序。"""
    ctx = dict(ctx or {})
    mods = load_url_plugins()
    mods = sorted(mods, key=lambda m: int(getattr(m, "PRIORITY", 100)))
    for mod in mods:
        try:
            if not mod.match(url):
                continue
            result = mod.resolve(url, ctx)
            if result and (result.get("urls") or result.get("url")):
                if "url" in result and "urls" not in result:
                    result["urls"] = [result["url"]]
                result["_plugin"] = getattr(mod, "NAME", path_name(mod))
                return result
        except Exception as e:
            print(f"[plugin] resolve error: {e}")
    return None


def path_name(mod) -> str:
    try:
        return Path(getattr(mod, "__file__", "") or "").name or "plugin"
    except Exception:
        return "plugin"

def github_mirror_url(url: str) -> str:
    """GitHub / HF 资源走镜像加速（可在设置 github_mirror 关闭）。"""
    u = (url or "").strip()
    if not u.startswith("http"):
        return u
    try:
        mirror = (cfg.data.get("github_mirror") or "").strip()  # type: ignore[name-defined]
    except Exception:
        mirror = "https://ghproxy.net/"
    if not mirror:
        return u
    low = u.lower()
    if not any(
        x in low
        for x in (
            "github.com/",
            "githubusercontent.com/",
            "huggingface.co/",
            "hf.co/",
        )
    ):
        return u
    if mirror.rstrip("/") in u:
        return u
    return mirror.rstrip("/") + "/" + u


TLS_FINGERPRINTS = ("chrome131", "chrome120", "safari17_0", "edge101")


def _impersonate_on() -> bool:
    try:
        return bool(cfg.data.get("http_impersonate", True))  # type: ignore[name-defined]
    except Exception:
        return True


def _impersonate_get(url: str, *, headers: dict, timeout, **kw):
    """按 TLS 指纹链依次尝试（chrome→safari→edge），返回 (response, 指纹名)。"""
    from curl_cffi import requests as creq  # type: ignore

    last: Optional[Exception] = None
    for fp in TLS_FINGERPRINTS:
        r = None
        try:
            r = creq.get(url, headers=headers, timeout=timeout, impersonate=fp, **kw)
            r.raise_for_status()
            return r, fp
        except Exception as e:
            last = e
            if r is not None:
                try:
                    r.close()
                except Exception:
                    pass
    raise last  # type: ignore[misc]


def http_get_bytes(url: str, timeout: int = 60, headers: Optional[dict] = None) -> bytes:
    """带 TLS 指纹回退链的 GET，降低 Cloudflare 403。"""
    headers = dict(headers or {})
    headers.setdefault(
        "User-Agent",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    )
    if _impersonate_on():
        try:
            r, _fp = _impersonate_get(url, headers=headers, timeout=timeout)
            return r.content
        except Exception:
            pass
    r = requests.get(url, headers=headers, timeout=timeout, verify=False)
    r.raise_for_status()
    return r.content


def _download_with_mirrors(urls: List[str], dest: Path, log: Callable = lambda *a, **k: None,
                           timeout: int = 180) -> str:
    """按候选顺序下载二进制（直连 / 各镜像），第一个成功的就是它，返回实际用的地址。"""
    last: Optional[Exception] = None
    for i, u in enumerate(urls, 1):
        try:
            log(f"下载（{i}/{len(urls)}）：{u}")
            with requests.get(u, stream=True, timeout=timeout, verify=False) as r:
                r.raise_for_status()
                with open(dest, "wb") as f:
                    for chunk in r.iter_content(chunk_size=256 * 1024):
                        if chunk:
                            f.write(chunk)
            if dest.stat().st_size <= 0:
                raise OSError("下载内容为空")
            return u
        except Exception as e:
            last = e
            log(f"该地址没成：{str(e)[:160]}", "warning")
    raise last or OSError("没有可用下载地址")


FFMPEG_ZIP_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
FFMPEG_FALLBACK_API = "https://api.github.com/repos/BtbN/FFmpeg-Builds/releases/latest"
YTDLP_EXE_URL = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
YTDLP_SRC_ZIP_URL = "https://github.com/yt-dlp/yt-dlp/archive/refs/heads/master.zip"
YTDLP_LOCAL_PKG = TOOLS_DIR / "yt_dlp"
YTDLP_LOCAL_EXE = TOOLS_DIR / "yt-dlp.exe"
SB_CATEGORIES = "sponsor,selfpromo,interaction,intro,outro,preview"


def normalize_url(url: str) -> str:
    """规范化各平台分享链接，便于 yt-dlp 识别"""
    if not url:
        return url
    # 去掉不可见字符、引号、多余空白
    url = url.strip().strip('"').strip("'")
    for ch in ("\u200b", "\u200c", "\u200d", "\ufeff", "\xa0"):
        url = url.replace(ch, "")
    url = url.strip()
    u = (url or "").strip()
    if not u:
        return u
    low = u.lower()
    # 磁力与本地种子文件的参数就是内容标识本身（xt=urn:btih、tr、dn），
    # 一旦被当统计参数删掉，同一个种子会排成两条任务，去重也就失效了
    if low.startswith(("magnet:", "file://")) or low.endswith(".torrent"):
        return u
    # 抖音：精选页 modal_id / share / aweme_id
    if "douyin.com" in low or "iesdouyin.com" in low:
        for pat in (
            r"[?&]modal_id=(\d+)",
            r"/video/(\d+)",
            r"/share/video/(\d+)",
            r"[?&]aweme_id=(\d+)",
            r"/note/(\d+)",
        ):
            m = re.search(pat, u)
            if m:
                return f"https://www.douyin.com/video/{m.group(1)}"
    # TikTok
    if "tiktok.com" in low:
        m = re.search(r"/video/(\d+)", u)
        if m:
            return f"https://www.tiktok.com/video/{m.group(1)}"
    # 小红书：探索页 / 发现页 / 短链保留完整参数
    if "xiaohongshu.com" in low or "xhslink.com" in low:
        m = re.search(r"/explore/([a-zA-Z0-9]+)", u)
        if m:
            base = f"https://www.xiaohongshu.com/explore/{m.group(1)}"
            # 若带 xsec_token 等参数则保留，提高解析成功率
            qpos = u.find("?")
            return (base + u[qpos:]) if qpos > 0 else base
        m = re.search(r"/discovery/item/([a-zA-Z0-9]+)", u)
        if m:
            return f"https://www.xiaohongshu.com/explore/{m.group(1)}"
        m = re.search(r"/user/profile/([a-zA-Z0-9]+)", u)
        if m:
            return f"https://www.xiaohongshu.com/user/profile/{m.group(1)}"
    return _drop_tracking(u)


# 这些参数只用于统计来源，删掉不影响解析；留着会让同一条内容因分享参数不同被排成两个任务
_TRACKING_KEYS = {
    "gclid", "fbclid", "msclkid", "dclid", "twclid", "yclid", "_ga", "gcref",
    "ref", "ref_url", "ref_src", "ref_srcid", "refer", "refer_url", "referrer",
    "sourcefrom", "srcid", "from_source", "from_url", "from_share", "is_story",
    "share_from", "share_medium", "share_plat", "share_session_id", "share_source",
    "share_tag", "share_token", "vd_source", "spm_id_from", "time_zone",
    "web_location", "force_parent", "unique_k", "not_recursive_head",
}
_TRACKING_PREFIXES = ("utm_", "spm_")
# 各站点「只用于分享/统计」的额外参数。B 站的 ?p= ?t=、抖音的 ?modal_id= 是内容参数，绝不进表
_HOST_TRACKING = {
    ("youtube.com", "youtu.be"): {"si", "feature", "pp", "app", "start_radio", "embeds", "play_next"},
    ("twitter.com", "x.com", "fxtwitter.com", "vxtwitter.com", "fixupx.com"): {
        "s", "t", "c", "lang", "ref_src", "src", "twid",
    },
    ("douyin.com", "iesdouyin.com"): {
        "from", "from_share_to", "is_from_webapp", "sender_device", "enter_method",
        "activity_count", "app_language", "region",
    },
    ("instagram.com", "pinterest.com"): {"igsh", "hl", "igshid"},
}


def _drop_tracking(u: str) -> str:
    """剥掉跟踪 query 参数、#t= 定位片段和多余尾斜杠；解析不出结构就原样返回。"""
    try:
        sp = urlsplit(u)
        host = (sp.hostname or "").lower()
    except ValueError:
        return u
    if host.startswith("www."):
        host = host[4:]
    drop = set(_TRACKING_KEYS)
    for suffixes, keys in _HOST_TRACKING.items():
        if any(host == s or host.endswith("." + s) for s in suffixes):
            drop |= keys
            break
    query = sp.query
    if query:
        kept = [
            (k, v)
            for k, v in parse_qsl(query, keep_blank_values=True)
            if k.lower() not in drop and not k.lower().startswith(_TRACKING_PREFIXES)
        ]
        query = urlencode(kept)
    frag = "" if sp.fragment.lower().startswith("t=") else sp.fragment
    path = sp.path[:-1] if len(sp.path) > 1 and sp.path.endswith("/") else sp.path
    out = urlunsplit((sp.scheme, sp.netloc, path, query, frag))
    return out or u


_BILI_PART_RE = re.compile(r"[?&]p=(\d+)", re.I)


def url_dedup_key(url: str) -> str:
    """「这两条链接是不是同一个东西」的判据：优先用站内 ID，拿不到就用归一化后的 URL。"""
    u = normalize_url(url)
    low = u.lower()
    if "youtube." in low or "youtu.be" in low:
        vid = extract_youtube_video_id(u)
        if vid:
            lst = re.search(r"[?&]list=([\w-]+)", u, re.I)
            # 带 list= 的是「播单里的这一集」，和不带播单的裸视频不是一回事
            return f"youtube:{vid.lower()}" + (f"+{lst.group(1).lower()}" if lst else "")
    m = re.search(r"bilibili\.com/video/(bv[\w]+)", low)
    if m:
        p = _BILI_PART_RE.search(u)
        return f"bili:{m.group(1)}" + (f":p{p.group(1)}" if p and p.group(1) != "1" else "")
    # 磁力：同一内容换个 tracker / 换个 dn 还是同一个种子，只能按 info hash 认
    bt = parse_torrent_ref(u)
    if bt:
        if bt["kind"] == "magnet":
            return f"btih:{bt['info_hash']}"
        ident = torrent_file_identity(bt["path"])
        # 本地种子能算出 info 段哈希就和磁力共用 btih:，同一个内容不管从哪个入口进来都合成一条
        return ("btih:" + ident) if len(ident) == 40 else "torrent-file:" + ident
    return u


# -------------------- Bilibili 弹幕 / 搜索 --------------------
_BILI_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Referer": "https://www.bilibili.com",
    "Origin": "https://www.bilibili.com",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


def _bili_request_kwargs(proxy: str = "", extra_headers: dict = None, for_search: bool = False) -> dict:
    """构造 B站 API 请求参数，尽量带上 Cookie / buvid 避免 -412 风控"""
    headers = dict(_BILI_HEADERS)
    if for_search:
        headers["Referer"] = "https://search.bilibili.com/"
        headers["Origin"] = "https://search.bilibili.com"
    if extra_headers:
        headers.update(extra_headers)
    kw = {"timeout": 15, "headers": headers}
    pr = http_proxies("", proxy, source="bilibili")
    if pr:
        kw["proxies"] = pr

    # 优先使用平台 Cookie 文件
    cookies = {}
    try:
        pc = (cfg.data.get("platform_cookies") or {}).get("bilibili") or {}
        src = (pc.get("source") or "").strip().lower()
        cookie_file = (pc.get("file") or "").strip()
        if not cookie_file:
            cookie_file = str(platform_cookie_path("bilibili"))
        if src == "file" and cookie_file and Path(cookie_file).exists():
            # 简易解析 Netscape cookies.txt
            for line in Path(cookie_file).read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split("\t")
                if len(parts) >= 7:
                    cookies[parts[5]] = parts[6]
        elif src == "browser":
            # 浏览器 Cookie 交给 yt-dlp 处理；API 这里用生成 buvid 兜底
            pass
    except Exception:
        pass

    # 没有真实 Cookie 时生成一个看起来合法的 buvid3，可显著降低 -412
    if "buvid3" not in cookies:
        import random
        import string
        rand = "".join(random.choices(string.ascii_uppercase + string.digits, k=32))
        cookies["buvid3"] = f"{rand[:8]}-{rand[8:12]}-{rand[12:16]}-{rand[16:20]}-{rand[20:32]}infoc"
    if cookies:
        kw["cookies"] = cookies
    return kw


def check_bilibili_live(room_url: str, proxy: str = "") -> dict:
    """返回 {live: bool, title, room_id, status_text}"""
    m = re.search(r"live\.bilibili\.com/(\d+)", room_url)
    if not m:
        return {"live": False, "title": "", "room_id": "", "status_text": "非B站直播间"}
    rid = m.group(1)
    try:
        kw = _bili_request_kwargs(proxy=proxy)
        r = requests.get(
            f"https://api.live.bilibili.com/room/v1/Room/get_info?room_id={rid}",
            **kw,
        )
        data = (r.json() or {}).get("data") or {}
        # live_status: 0未开播 1直播中 2轮播
        st = int(data.get("live_status") or 0)
        title = data.get("title") or ""
        live = st == 1
        text = {0: "等待开播", 1: "直播中", 2: "轮播中"}.get(st, f"状态{st}")
        return {"live": live, "title": title, "room_id": rid, "status_text": text, "live_status": st}
    except Exception as e:
        return {"live": False, "title": "", "room_id": rid, "status_text": f"检测失败: {e}"}


def is_bilibili_url(url: str) -> bool:
    u = (url or "").lower()
    return any(x in u for x in ("bilibili.com", "b23.tv", "bili2233.cn"))


def _extract_bvid(url: str) -> Optional[str]:
    m = re.search(r"(BV[\w]+)", url, re.I)
    if m:
        return m.group(1)
    m = re.search(r"[?&]bvid=(BV[\w]+)", url, re.I)
    if m:
        return m.group(1)
    return None


def _extract_aid(url: str) -> Optional[str]:
    m = re.search(r"/av(\d+)", url, re.I)
    if m:
        return m.group(1)
    m = re.search(r"[?&]aid=(\d+)", url, re.I)
    return m.group(1) if m else None


def bilibili_fetch_cid(url: str, proxy: str = "") -> Optional[tuple]:
    """返回 (cid, title) 或 None"""
    session = requests.Session()
    session.headers.update(_BILI_HEADERS)
    pr = http_proxies(url, proxy, source="bilibili")
    if pr:
        session.proxies = pr
    # 短链先展开
    try:
        if "b23.tv" in url or "bili2233" in url:
            r = session.get(url, timeout=15, allow_redirects=True)
            url = r.url
    except Exception:
        pass
    bvid = _extract_bvid(url)
    aid = _extract_aid(url)
    api = None
    if bvid:
        api = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
    elif aid:
        api = f"https://api.bilibili.com/x/web-interface/view?aid={aid}"
    if not api:
        return None
    try:
        data = session.get(api, timeout=20).json()
        if data.get("code") != 0:
            return None
        d = data.get("data") or {}
        pages = d.get("pages") or []
        cid = pages[0].get("cid") if pages else d.get("cid")
        title = d.get("title") or "bilibili"
        if not cid:
            return None
        return int(cid), str(title)
    except Exception:
        return None


def bilibili_download_danmaku_xml(cid: int, proxy: str = "") -> Optional[str]:
    """下载原始弹幕 XML 文本"""
    session = requests.Session()
    session.headers.update(_BILI_HEADERS)
    pr = http_proxies("", proxy, source="bilibili")
    if pr:
        session.proxies = pr
    urls = [
        f"https://comment.bilibili.com/{cid}.xml",
        f"https://api.bilibili.com/x/v1/dm/list.so?oid={cid}",
    ]
    for u in urls:
        try:
            r = session.get(u, timeout=30)
            if r.status_code == 200 and r.content and b"<d " in r.content:
                # bilibili 常为 deflate/utf-8
                try:
                    text = r.content.decode("utf-8")
                except Exception:
                    text = r.text
                return text
        except Exception:
            continue
    return None


def bilibili_xml_to_ass(xml_text: str, title: str = "danmaku") -> str:
    """简易 XML → ASS，便于 PotPlayer / MPC 直接加载"""
    header = f"""[Script Info]
Title: {title}
ScriptType: v4.00+
Collisions: Normal
PlayResX: 1920
PlayResY: 1080
Timer: 100.0000

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Microsoft YaHei,48,&H00FFFFFF,&H000000FF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,2,0,2,20,20,20,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]
    # <d p="time,mode,size,color,...">text</d>
    for m in re.finditer(r'<d p="([^"]+)">([^<]*)</d>', xml_text):
        props, text = m.group(1), m.group(2)
        parts = props.split(",")
        if len(parts) < 4:
            continue
        try:
            t = float(parts[0])
            mode = int(parts[1])
            color_int = int(parts[3])
        except Exception:
            continue
        # 过滤空
        text = text.replace("\n", " ").strip()
        if not text:
            continue
        text = text.replace("{", "｛").replace("}", "｝")
        start = _sec_to_ass(t)
        end = _sec_to_ass(t + 8.0)
        # BGR for ASS
        r = color_int & 0xFF
        g = (color_int >> 8) & 0xFF
        b = (color_int >> 16) & 0xFF
        c = f"&H00{b:02X}{g:02X}{r:02X}"
        if mode in (4, 5):  # 底端/顶端
            align = 8 if mode == 5 else 2
            lines.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{{\\an{align}\\c{c}}}{text}\n")
        else:  # 滚动
            lines.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{{\\move(1920,100,0,100)\\c{c}}}{text}\n")
    return "".join(lines)


def _sec_to_ass(sec: float) -> str:
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    cs = int((sec - int(sec)) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _find_local_whisper_bin() -> Optional[str]:
    """查找 web_app/Whisper 或 PATH 中的 whisper 可执行文件"""
    candidates = []
    if WHISPER_DIR.is_dir():
        for name in ("whisper.exe", "whisper-cli.exe", "main.exe", "whisper"):
            p = WHISPER_DIR / name
            if is_native_binary(p):
                candidates.append(str(p))
        # Windows 随包常把二进制放在子目录，所以按 whisper*.exe 递归；
        # Linux/macOS 的文件名没有 .exe，通配放宽到 whisper*，再由能否执行来收口。
        pattern = "whisper*.exe" if sys.platform == "win32" else "whisper*"
        for p in WHISPER_DIR.rglob(pattern):
            if is_native_binary(p):
                candidates.append(str(p))
    w = shutil.which("whisper")
    if w and is_native_binary(w):
        candidates.append(w)
    return candidates[0] if candidates else None


def _whisper_cfg() -> dict:
    """从全局配置读取 Whisper 参数。"""
    try:
        data = cfg.data  # type: ignore[name-defined]
    except Exception:
        data = {}
    return {
        "model": (data.get("whisper_model") or "base").strip() or "base",
        "device": (data.get("whisper_device") or "auto").strip() or "auto",
        "compute": (data.get("whisper_compute") or "auto").strip() or "auto",
        "lang": (data.get("local_ai_lang") or "zh").strip() or "zh",
        "diarize": bool(data.get("diarization_enabled")),
        "max_speakers": int(data.get("diarization_max_speakers") or 4),
    }


def _whisper_via_faster(
    media: Path,
    task: str,
    lang: str,
    log: Callable,
    model_size: str = "",
    device_pref: str = "auto",
    compute_pref: str = "auto",
) -> Optional[Path]:
    """优先 faster-whisper；模型单例缓存 + CPU/CUDA 优化（类 whisper.app 本地推理）。"""
    try:
        from faster_whisper import WhisperModel  # type: ignore
    except ImportError:
        return None
    wc = _whisper_cfg()
    model_size = (model_size or wc["model"] or "base").strip()
    device_pref = (device_pref or wc["device"] or "auto").strip().lower()
    compute_pref = (compute_pref or wc["compute"] or "auto").strip().lower()

    device, ctype = "cpu", "int8"
    if device_pref == "cpu":
        device, ctype = "cpu", "int8"
    elif device_pref in ("cuda", "gpu"):
        device, ctype = "cuda", "float16"
    else:
        try:
            import torch  # type: ignore
            if torch.cuda.is_available():
                device, ctype = "cuda", "float16"
        except Exception:
            pass
    if compute_pref and compute_pref != "auto":
        ctype = compute_pref

    models_dir = WHISPER_DIR / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    model_path = model_size
    # 本机 whisper.app / ggml 同级目录、以及 Whisper/models 缓存
    search_roots = [
        models_dir,
        WHISPER_DIR,
        Path.home() / "Library" / "Application Support" / "whisper",  # mac whisper.app 常见
        Path.home() / ".cache" / "whisper",
        Path.home() / ".cache" / "huggingface" / "hub",
    ]
    for cand in search_roots:
        if not cand.is_dir():
            continue
        named = cand / model_size
        if named.is_dir() and (
            (named / "model.bin").exists()
            or (named / "config.json").exists()
            or any(named.glob("*.bin"))
        ):
            model_path = str(named)
            break
        for sub in cand.iterdir():
            if not sub.is_dir():
                continue
            if model_size in sub.name and (
                (sub / "model.bin").exists()
                or (sub / "config.json").exists()
                or any(sub.glob("*.bin"))
            ):
                model_path = str(sub)
                break
        else:
            continue
        break
    download_root = str(models_dir)
    log(f"faster-whisper: model={model_path} device={device} compute={ctype} task={task}")

    # 进程内模型缓存，避免每次重新加载（大幅加速连续转写）
    global _FW_MODEL_CACHE
    try:
        _FW_MODEL_CACHE
    except NameError:
        _FW_MODEL_CACHE = {}
    cache_key = f"{model_path}|{device}|{ctype}"
    model = _FW_MODEL_CACHE.get(cache_key)
    if model is None:
        try:
            model = WhisperModel(
                model_path,
                device=device,
                compute_type=ctype,
                download_root=download_root,
                cpu_threads=max(1, (os.cpu_count() or 4) // 2),
                num_workers=1,
            )
        except Exception as e:
            if device == "cuda":
                log(f"CUDA 加载失败，回退 CPU int8: {e}", "warning")
                device, ctype = "cpu", "int8"
                cache_key = f"{model_path}|{device}|{ctype}"
                model = WhisperModel(
                    model_path, device="cpu", compute_type="int8",
                    download_root=download_root,
                    cpu_threads=max(1, (os.cpu_count() or 4) // 2),
                )
            else:
                raise
        _FW_MODEL_CACHE[cache_key] = model
        log(f"faster-whisper 模型已缓存: {cache_key}")
    else:
        log("faster-whisper 使用缓存模型")

    lang_arg, init_prompt = _whisper_lang_and_prompt(lang)
    if lang and str(lang).lower() in ("yue", "cantonese", "zh-yue", "粤语", "广东话", "nan", "minnan", "wuu", "wu"):
        log(f"方言模式: UI={lang} → whisper_lang={lang_arg or 'auto'}")
    # 推理优化：VAD 切静音、不强制温度、适度 beam
    kw = dict(
        task=task,
        language=lang_arg,
        beam_size=5 if device == "cuda" else 3,
        best_of=5 if device == "cuda" else 3,
        patience=1.0,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=400),
        condition_on_previous_text=True,
        compression_ratio_threshold=2.4,
        no_speech_threshold=0.6,
    )
    if init_prompt:
        kw["initial_prompt"] = init_prompt
    segments, info = model.transcribe(str(media), **kw)
    # 写 srt：转写用 .srt；Whisper 官方 translate 仅→英文用 .en.srt
    out = media.with_suffix(".srt") if task == "transcribe" else media.with_name(media.stem + ".en.srt")
    segs = [(s.start, s.end, (s.text or "").strip()) for s in segments]
    segs = [s for s in segs if s[2]]
    if wc.get("diarize") and segs:
        prefix = _diarize_prefixes(media, segs, wc.get("max_speakers") or 4, log)
        if prefix:
            segs = [(a, b, f"{p} {t}") for (a, b, t), p in zip(segs, prefix)]
    lines = []
    for idx, (start, end, text) in enumerate(segs, 1):
        lines.append(f"{idx}\n{_srt_ts(start)} --> {_srt_ts(end)}\n{text}\n\n")
    out.write_text("".join(lines), encoding="utf-8")
    log(f"{'转写' if task == 'transcribe' else '翻译'}完成: {out.name} "
        f"(lang={getattr(info, 'language', '?')}, {len(segs)} 句)")
    return out


def _diarize_prefixes(media: Path, segs: list, max_speakers: int, log: Callable) -> list:
    """按声纹给每句字幕贴 [说话人N]。分不出来就返回空列表，字幕保持原样。"""
    if not segs:
        return []
    try:
        import diarize_tools
    except Exception as e:
        log(f"说话人分离模块加载失败: {e}", "warning")
        return []
    if not diarize_tools.available():
        log("说话人分离已跳过：本机没有 ffmpeg 或 numpy", "warning")
        return []
    diarize_tools.set_ffmpeg(ffmpeg_mgr.find() or "")
    labels = diarize_tools.diarize_segments(
        str(media), [(s[0], s[1]) for s in segs], log=log, max_speakers=max_speakers
    )
    if not labels:
        return []
    k = len({x for x in labels if x})
    if k <= 1:
        log("说话人分离：只听出一个人的音色，未加标记（声音接近时常见）")
        return []
    log(f"说话人分离：{len(segs)} 句分成 {k} 个人（轻量声纹，音色接近者可能混标）")
    return [f"[说话人{x}]" if x else "" for x in labels]


def _srt_ts(sec: float) -> str:
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    ms = int((sec - int(sec)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


# Whisper 官方多语言代码（openai-whisper / faster-whisper）
WHISPER_LANG_CODES = {
    "af", "am", "ar", "as", "az", "ba", "be", "bg", "bn", "bo", "br", "bs", "ca", "cs", "cy",
    "da", "de", "el", "en", "es", "et", "eu", "fa", "fi", "fo", "fr", "gl", "gu", "ha", "haw",
    "he", "hi", "hr", "ht", "hu", "hy", "id", "is", "it", "ja", "jw", "ka", "kk", "km", "kn",
    "ko", "la", "lb", "ln", "lo", "lt", "lv", "mg", "mi", "mk", "ml", "mn", "mr", "ms", "mt",
    "my", "ne", "nl", "nn", "no", "oc", "pa", "pl", "ps", "pt", "ro", "ru", "sa", "sd", "si",
    "sk", "sl", "sn", "so", "sq", "sr", "su", "sv", "sw", "ta", "te", "tg", "th", "tk", "tl",
    "tr", "tt", "uk", "ur", "uz", "vi", "yi", "yo", "zh",
}

# 方言 / 别名 → (whisper_code, initial_prompt 可选)
# 说明：官方模型无独立「粤语」码，粤语/闽南等走 zh + 提示词；效果因口音与模型大小而异
WHISPER_LANG_ALIASES = {
    "zh": ("zh", None),
    "zh-cn": ("zh", None),
    "zh-hans": ("zh", None),
    "zh-tw": ("zh", "這是繁體中文的字幕。"),
    "zh-hant": ("zh", "這是繁體中文的字幕。"),
    "chinese": ("zh", None),
    "mandarin": ("zh", "以下是普通话内容。"),
    "yue": ("zh", "以下是粤语（广东话）口语内容，请按实际听到的粤语转写。"),
    "cantonese": ("zh", "以下是粤语（广东话）口语内容，请按实际听到的粤语转写。"),
    "zh-yue": ("zh", "以下是粤语（广东话）口语内容，请按实际听到的粤语转写。"),
    "粤语": ("zh", "以下是粤语（广东话）口语内容，请按实际听到的粤语转写。"),
    "广东话": ("zh", "以下是粤语（广东话）口语内容，请按实际听到的粤语转写。"),
    "nan": ("zh", "以下是闽南语/台语口语内容。"),
    "minnan": ("zh", "以下是闽南语/台语口语内容。"),
    "hokkien": ("zh", "以下是闽南语/台语口语内容。"),
    "闽南语": ("zh", "以下是闽南语/台语口语内容。"),
    "wuu": ("zh", "以下是吴语/上海话口语内容。"),
    "wu": ("zh", "以下是吴语/上海话口语内容。"),
    "shanghai": ("zh", "以下是吴语/上海话口语内容。"),
    "吴语": ("zh", "以下是吴语/上海话口语内容。"),
    "en": ("en", None),
    "english": ("en", None),
    "ja": ("ja", None),
    "jp": ("ja", None),
    "japanese": ("ja", None),
    "日文": ("ja", None),
    "日语": ("ja", None),
    "ko": ("ko", None),
    "korean": ("ko", None),
    "韩文": ("ko", None),
    "fr": ("fr", None),
    "de": ("de", None),
    "es": ("es", None),
    "ru": ("ru", None),
    "pt": ("pt", None),
    "it": ("it", None),
    "vi": ("vi", None),
    "th": ("th", None),
    "ar": ("ar", None),
    "hi": ("hi", None),
    "id": ("id", None),
    "ms": ("ms", None),
    "tr": ("tr", None),
    "pl": ("pl", None),
    "nl": ("nl", None),
    "sv": ("sv", None),
    "uk": ("uk", None),
    "he": ("he", None),
    "fa": ("fa", None),
    "cs": ("cs", None),
    "ro": ("ro", None),
    "hu": ("hu", None),
    "el": ("el", None),
    "bg": ("bg", None),
    "fi": ("fi", None),
    "da": ("da", None),
    "no": ("no", None),
    "nn": ("nn", None),
    "tl": ("tl", None),
    "fil": ("tl", None),
    "my": ("my", None),
    "km": ("km", None),
    "lo": ("lo", None),
    "yue-hint": ("zh", "以下是粤语口语。"),
}


def _normalize_whisper_lang(lang: str) -> Optional[str]:
    """映射 UI 语言到 Whisper 代码；auto → None。返回 code 或 None。"""
    code, _ = _whisper_lang_and_prompt(lang)
    return code


def _whisper_lang_and_prompt(lang: str) -> tuple:
    """返回 (language_code|None, initial_prompt|None)。"""
    if not lang or str(lang).strip().lower() in ("auto", "none", "detect", ""):
        return None, None
    low = str(lang).strip().lower().replace("_", "-")
    if low in WHISPER_LANG_ALIASES:
        return WHISPER_LANG_ALIASES[low]
    # 直接是官方两字母代码
    if low in WHISPER_LANG_CODES:
        return low, None
    if len(low) <= 3 and low.isalpha():
        return low, None
    return None, None


def parse_srt(text: str) -> List[dict]:
    """解析 SRT → [{idx, start, end, text}, ...]"""
    blocks = re.split(r"\n\s*\n", (text or "").replace("\r\n", "\n").strip())
    cues = []
    for block in blocks:
        lines = [ln for ln in block.split("\n") if ln.strip() is not None]
        if len(lines) < 2:
            continue
        # 可能无序号行
        if "-->" in lines[0]:
            timing, body = lines[0], lines[1:]
            idx = len(cues) + 1
        elif len(lines) >= 2 and "-->" in lines[1]:
            try:
                idx = int(lines[0].strip())
            except Exception:
                idx = len(cues) + 1
            timing, body = lines[1], lines[2:]
        else:
            continue
        text_body = "\n".join(body).strip()
        if not text_body:
            continue
        cues.append({"idx": idx, "timing": timing.strip(), "text": text_body})
    return cues


def write_srt(cues: List[dict]) -> str:
    parts = []
    for i, c in enumerate(cues, 1):
        parts.append(f"{i}\n{c.get('timing') or '00:00:00,000 --> 00:00:00,000'}\n{c.get('text') or ''}\n")
    return "\n".join(parts) + ("\n" if parts else "")


def _char_units(ch: str) -> float:
    """显示宽度权重：CJK / 全角标点 / emoji 记 1，半角记 0.5。"""
    o = ord(ch)
    wide = (
        0x1100 <= o <= 0x115F
        or 0x2E80 <= o <= 0x303F
        or 0x3041 <= o <= 0x33FF
        or 0x3400 <= o <= 0x4DBF
        or 0x4E00 <= o <= 0x9FFF
        or 0xA960 <= o <= 0xD7FF
        or 0xF900 <= o <= 0xFAFF
        or 0xFE30 <= o <= 0xFE6F
        or 0xFF00 <= o <= 0xFF60
        or 0xFFE0 <= o <= 0xFFE6
        or o >= 0x1F000
    )
    return 1.0 if wide else 0.5


def text_units(s: str) -> float:
    return sum(_char_units(c) for c in (s or ""))


_BREAK_AFTER = set("，。！？；：、,.)）]》」”’-—·/、")
_NO_LINE_START = set("，。！？；：、,.)）]》」”’%…—/")


def _split_balanced(line: str, max_units: float, k: int) -> List[str]:
    """把一行按显示宽度等分成最多 k 段，断点优先落在标点/词边界，且不留行首禁排标点。"""
    chars = list(line)
    n = len(chars)
    if k <= 1 or n < 2:
        return [line]
    pref = [0.0] * (n + 1)
    for i, ch in enumerate(chars):
        pref[i + 1] = pref[i] + _char_units(ch)
    total = pref[n]
    if total <= max_units:
        return [line]
    cuts = []
    for i in range(1, n):
        prev, cur = chars[i - 1], chars[i]
        if cur in _NO_LINE_START:
            continue
        if prev in _BREAK_AFTER:
            score = 3
        elif prev == " " or cur == " ":
            score = 2
        elif _char_units(cur) == 1.0 and _char_units(prev) == 1.0:
            score = 1
        else:
            continue
        cuts.append((i, score))
    if not cuts:
        step = max(1, n // k)
        idxs = [step * (j + 1) for j in range(k - 1)]
    else:
        idxs = []
        prev_i = 0
        for seg in range(1, k):
            ideal = total * seg / k
            floor_w = total - max_units * (k - seg)  # 剩余段落得放得下
            ceil_w = pref[prev_i] + max_units        # 当前段别超标

            def cost(ic):
                i, sc = ic
                w = pref[i]
                pen = 0.0
                if w < floor_w:
                    pen += (floor_w - w) * 4
                if w > ceil_w:
                    pen += (w - ceil_w) * 4
                return pen + abs(w - ideal) - 0.9 * sc

            avail = [ic for ic in cuts if ic[0] > prev_i]
            if not avail:
                break
            prev_i = min(avail, key=cost)[0]
            idxs.append(prev_i)
    pieces = []
    prev = 0
    for i in sorted(set(idxs)):
        pieces.append(line[prev:i].strip())
        prev = i
    pieces.append(line[prev:].strip())
    return [p for p in pieces if p]


def wrap_subtitle_text(text: str, max_units: float = 16.0, max_lines: int = 3) -> str:
    """按显示宽度加权换行：中文记 1、英文记 0.5，每行不超宽，整条最多 max_lines 行。

    先把已有的断行接回正文再重排：同一句无论点几次「重排」都断在同一处，不会每次都挪。
    """
    lines = [ln.strip() for ln in (text or "").split("\n") if ln.strip()]
    if not lines:
        return ""
    flow = ""
    for part in lines:
        wide_join = _char_units(flow[-1]) == 1.0 and _char_units(part[0]) == 1.0 if flow else False
        flow += ("" if wide_join else " ") + part if flow else part
    if max_lines <= 1:
        return flow
    need = int(-(-text_units(flow) // max_units))
    if need <= 1:
        return flow
    return "\n".join(_split_balanced(flow, max_units, min(need, max_lines)))


def wrap_cues(cues: List[dict], max_units: float = 16.0, max_lines: int = 3) -> List[dict]:
    out = []
    for c in cues:
        d = dict(c)
        d["text"] = wrap_subtitle_text(c.get("text") or "", max_units, max_lines)
        out.append(d)
    return out


_LANG_SUFFIX_RE = re.compile(r"\.(zh|zh-cn|zh-hans|zh-tw|en|en-us|ja|ko|fr|de|es|ru|pt|vi|th|ar|hi|translated)$", re.I)


def _lang_suffix_of(p: Path) -> str:
    m = re.search(r"\.([a-z]{2}(?:[-_][a-z]{2,4})?)$", p.stem, re.I)
    return (m.group(1) if m else "").lower()


def _push_cand(out: list, cand: Path, self_resolved) -> None:
    try:
        if not cand.is_file() or cand.resolve() == self_resolved:
            return
        low = cand.name.lower()
        if ".bi." in low or ".sync" in low or "polished" in low:
            return
        out.append((cand.stat().st_mtime, cand))
    except Exception:
        return


def find_subtitle_counterpart(srt_path) -> Optional[Path]:
    """找同一字幕的另一路文本：原文 ↔ 机翻译文。"""
    p = Path(srt_path)
    try:
        self_resolved = p.resolve()
    except Exception:
        return None
    dirn = p.parent

    # 1) 手上这份像派生译文：demo.en.zh.srt → demo.en.srt
    base = _LANG_SUFFIX_RE.sub("", p.stem)
    if base != p.stem:
        tier1: list = []
        _push_cand(tier1, dirn / (base + ".srt"), self_resolved)
        if tier1:
            return min(tier1, key=lambda x: x[0])[1]

    # 2) 手上这份像原文：demo.en.srt → demo.en.<lang>.srt
    tier2: list = []
    for cand in dirn.glob(p.stem + ".*.srt"):
        if _LANG_SUFFIX_RE.search(cand.stem):
            _push_cand(tier2, cand, self_resolved)
    if tier2:
        return max(tier2, key=lambda x: x[0])[1]

    # 3) 同主干的其它语言兄弟：demo.zh.srt ↔ demo.en.srt
    stem = _LANG_SUFFIX_RE.sub("", p.stem)
    mine = _lang_suffix_of(p)
    tier3: list = []
    if stem:
        for cand in list(dirn.glob(stem + ".*.srt")) + [dirn / (stem + ".srt")]:
            if _LANG_SUFFIX_RE.sub("", cand.stem).lower() != stem.lower():
                continue
            if _lang_suffix_of(cand) == mine:
                continue
            _push_cand(tier3, cand, self_resolved)
    if tier3:
        return min(tier3, key=lambda x: x[0])[1]
    return None


def merge_bilingual_cues(a_cues: List[dict], b_cues: List[dict]) -> List[dict]:
    """把两路字幕合成双语字幕，时间轴取第一条，行序为 a 在上、b 在下。"""
    merged = []
    for i, c in enumerate(a_cues):
        text = (c.get("text") or "").strip()
        other = (b_cues[i].get("text") or "").strip() if i < len(b_cues) else ""
        if other:
            text = f"{text}\n{other}" if text else other
        if not text:
            continue
        merged.append({"idx": i + 1, "timing": c.get("timing"), "text": text})
    return merged


def _srt_ts_to_ass_ts(ts: str) -> str:
    ts = (ts or "").strip().replace(".", ",")
    m = re.match(r"(\d+):(\d+):(\d+),(\d+)", ts)
    if not m:
        return "0:00:00.00"
    h, mi, s, ms = m.groups()
    return f"{int(h)}:{mi}:{s}.{int(ms) // 10:02d}"


def srt_to_ass(
    top_cues: List[dict],
    bottom_cues: Optional[List[dict]] = None,
    *,
    title: str = "",
    main_style: Optional[dict] = None,
) -> str:
    """SRT 列表 → ASS 文本。top 走顶部小字号次样式，bottom 走底部主样式。

    main_style 只覆盖主样式（烧字幕时用）；不传就是原来双语导出的样子。
    """
    st = {"font": "Noto Sans CJK SC", "fontsize": 44, "align": 2, "marginv": 36, "outline": 2.2}
    st.update({k: v for k, v in (main_style or {}).items() if k in st})
    head = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "PlayResX: 1280\nPlayResY: 720\nScaledBorderAndShadow: yes\n"
        f"Title: {title or 'bilingual subtitles'}\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Main,{st['font']},{st['fontsize']},&H00FFFFFF,&H000000FF,&H00101010,&H7F000000,"
        f"-1,0,0,0,100,100,0,0,1,{st['outline']},1.2,{st['align']},40,40,{st['marginv']},1\n"
        "Style: Side,Noto Sans CJK SC,32,&H00C8C8C8,&H000000FF,&H00101010,&H7F000000,"
        "0,0,0,0,100,100,0,0,1,1.8,1.0,8,40,40,32,1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    rows = []
    for c in bottom_cues or []:
        timing = c.get("timing") or ""
        parts = re.split(r"\s*-->\s*", timing)
        if len(parts) != 2:
            continue
        text = (c.get("text") or "").replace("\n", "\\N")
        rows.append(
            f"Dialogue: 0,{_srt_ts_to_ass_ts(parts[0])},{_srt_ts_to_ass_ts(parts[1])},Main,,0,0,0,,{text}"
        )
    for c in top_cues or []:
        timing = c.get("timing") or ""
        parts = re.split(r"\s*-->\s*", timing)
        if len(parts) != 2:
            continue
        text = (c.get("text") or "").replace("\n", "\\N")
        rows.append(
            f"Dialogue: 0,{_srt_ts_to_ass_ts(parts[0])},{_srt_ts_to_ass_ts(parts[1])},Side,,0,0,0,,{text}"
        )
    return head + "\n".join(rows) + "\n"


def write_vtt(cues: List[dict]) -> str:
    lines = ["WEBVTT", ""]
    for i, c in enumerate(cues, 1):
        timing = re.sub(r"\s*-->\s*", " --> ", (c.get("timing") or "00:00:00,000 --> 00:00:00,000"))
        lines.append(str(i))
        lines.append(timing.replace(",", "."))
        lines.append((c.get("text") or "").replace("\r", ""))
        lines.append("")
    return "\n".join(lines)


def _srt_ts_to_ms(ts: str) -> int:
    """00:01:02,300 或 00:01:02.300 → 毫秒

    毫秒那一段按**位数**换算，不能按数值大小猜：`00:00:10,040` 是 40 毫秒，
    若看 int 值是 40 就当两位小数乘 10，会变成 400 毫秒，整条字幕晚 0.36 秒。
    """
    ts = (ts or "").strip().replace(".", ",")
    m = re.match(r"(\d+):(\d+):(\d+),(\d+)", ts)
    if not m:
        return 0
    h, mi, s, frac = int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4)
    return ((h * 60 + mi) * 60 + s) * 1000 + int(frac[:3]) * 10 ** max(0, 3 - len(frac))


def _ms_to_srt_ts(ms: int) -> str:
    ms = max(0, int(ms))
    h = ms // 3600000
    ms %= 3600000
    mi = ms // 60000
    ms %= 60000
    s = ms // 1000
    milli = ms % 1000
    return f"{h:02d}:{mi:02d}:{s:02d},{milli:03d}"


def shift_srt_cues(
    cues: List[dict],
    *,
    offset_ms: int = 0,
    scale: float = 1.0,
) -> List[dict]:
    """
    时间轴校准：
    - offset_ms: 整体平移（正=延后，负=提前）
    - scale: 以第一条起点为锚缩放（>1 拉长，<1 压缩），用于片速略不一致
    """
    scale = float(scale) if scale else 1.0
    if scale <= 0:
        scale = 1.0
    # 解析每条 start/end
    parsed = []
    for c in cues:
        timing = c.get("timing") or ""
        if "-->" not in timing:
            parsed.append(c)
            continue
        left, right = [x.strip() for x in timing.split("-->", 1)]
        # 去掉可能的 position 后缀
        right = right.split(" ")[0].strip()
        t0 = _srt_ts_to_ms(left)
        t1 = _srt_ts_to_ms(right)
        parsed.append({**c, "_t0": t0, "_t1": t1})

    anchor = None
    for c in parsed:
        if "_t0" in c:
            anchor = c["_t0"]
            break
    if anchor is None:
        anchor = 0

    out = []
    for c in parsed:
        if "_t0" not in c:
            out.append({"timing": c.get("timing"), "text": c.get("text")})
            continue
        t0, t1 = c["_t0"], c["_t1"]
        if abs(scale - 1.0) > 1e-9:
            t0 = int(anchor + (t0 - anchor) * scale)
            t1 = int(anchor + (t1 - anchor) * scale)
        t0 = max(0, t0 + int(offset_ms))
        t1 = max(t0 + 40, t1 + int(offset_ms))  # 至少 40ms 时长
        out.append({
            "timing": f"{_ms_to_srt_ts(t0)} --> {_ms_to_srt_ts(t1)}",
            "text": c.get("text") or "",
        })
    return out


def calibrate_srt_file(
    srt_path: str,
    *,
    offset_ms: int = 0,
    offset_sec: float = 0.0,
    scale: float = 1.0,
    inplace: bool = False,
    log: Callable = print,
) -> str:
    """校准 SRT 时间轴，返回输出路径。"""
    p = Path(srt_path)
    if not p.is_file():
        raise FileNotFoundError(str(p))
    total_ms = int(offset_ms) + int(float(offset_sec) * 1000)
    cues = parse_srt(p.read_text(encoding="utf-8", errors="ignore"))
    if not cues:
        raise RuntimeError("SRT 无有效条目")
    new_cues = shift_srt_cues(cues, offset_ms=total_ms, scale=scale)
    if inplace:
        out = p
    else:
        tag = []
        if total_ms:
            tag.append(f"{'+' if total_ms >= 0 else ''}{total_ms}ms")
        if abs(scale - 1.0) > 1e-9:
            tag.append(f"x{scale:.4g}")
        suffix = "_".join(tag) if tag else "calibrated"
        out = p.with_name(f"{p.stem}.sync{suffix}.srt")
    out.write_text(write_srt(new_cues), encoding="utf-8")
    log(f"时间轴校准: {p.name} → {out.name} (offset={total_ms}ms scale={scale})")
    return str(out)


GLOSSARY_SEP_RE = re.compile(r"\s*(?:=>|→|->|∶|：|:=|=|:)\s*")


def parse_glossary(raw: Optional[str] = None) -> List[Tuple[str, str]]:
    """把术语表文本解析成 (原文, 译文) 列表；不传 raw 则读全局设置。"""
    text = raw if raw is not None else (cfg.data.get("subtitle_glossary") or "")
    pairs: List[Tuple[str, str]] = []
    seen: set = set()
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("//"):
            continue
        parts = GLOSSARY_SEP_RE.split(line, maxsplit=1)
        if len(parts) != 2:
            continue
        term, value = parts[0].strip(), parts[1].strip()
        if not term or not value:
            continue
        key = term.lower()
        if key in seen:
            continue
        seen.add(key)
        pairs.append((term, value))
    return pairs


def glossary_prompt_block(pairs: Optional[List[Tuple[str, str]]] = None) -> str:
    """LLM 翻译时的术语约束段。"""
    if pairs is None:
        pairs = parse_glossary()
    if not pairs:
        return ""
    rows = "\n".join(f"- {a} => {b}" for a, b in pairs)
    return (
        "\n\nTERMINOLOGY (mandatory, take precedence over your own judgement). "
        "Whenever a source term below appears, render it exactly as given:\n"
        f"{rows}\n"
        "Never re-translate or localize these terms, and keep their capitalization."
    )


def _glossary_term_re(term: str) -> "re.Pattern[str]":
    escaped = re.escape(term)
    if re.fullmatch(r"[A-Za-z0-9 ._'\-()+&%]+", term):
        return re.compile(rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])", re.I)
    return re.compile(escaped)


def apply_glossary(text: str, pairs: List[Tuple[str, str]]) -> str:
    """翻译后兜底：源术语若被原样保留（或大小写变了），强制换成指定译文。"""
    if not text or not pairs:
        return text
    out = text
    for term, value in pairs:
        if term == value:
            continue
        rx = _glossary_term_re(term)
        candidate, n = rx.subn(lambda m: value, out)
        if n:
            out = candidate
    return out


QC_KIND_LABELS = {
    "empty": "没有译文",
    "same": "没翻译",
    "untranslated": "没换成目标语言",
    "short": "疑似漏译",
    "long": "疑似加戏",
    "term": "术语没照表",
    "number": "数字对不上",
    "repeat": "疑似复读",
    "over": "超出每行字数",
    "tag": "样式标签丢失",
}
# 这些类型可以靠模型再看一遍重写；超行是换行的事、标签丢失是格式的事，反射修不了
QC_REFLECT_KINDS = ("same", "untranslated", "short", "long", "term", "number", "repeat")
_CJK_TXT_RE = re.compile(r"[　-〿぀-ヿ一-鿿豈-﫿가-힯]")
_TAG_TXT_RE = re.compile(r"</?[iubIan]\b[^>]*>")
_NUM_TXT_RE = re.compile(r"\d+(?:[.,]\d+)*")


def _qc_norm(s: str) -> str:
    return re.sub(r"[\W_]+", "", (s or "").lower(), flags=re.UNICODE)


def _qc_nums(s: str) -> set:
    t = re.sub(r"(?<=\d),(?=\d{3}(?:\D|$))", "", s or "")  # 千分位逗号不当小数点
    return set(_NUM_TXT_RE.findall(t))


# 汉字写的数：「一」在中文里太常用，单个数字要字形对上才算，多位数要看有没有一段同样长的汉字数字
_QC_CN_NUM_RE = re.compile(r"[〇零一二两三四五六七八九十百千万亿]+")
_QC_CN_ONE = {"0": "〇零", "1": "一", "2": "二两", "3": "三", "4": "四",
              "5": "五", "6": "六", "7": "七", "8": "八", "9": "九"}


def _qc_num_spelled(dst: str, num: str) -> bool:
    """原文的数字在译文里有没有用汉字写出来。"""
    d = (num.split(".")[0] or "").lstrip("-")
    if not d.isdigit():
        return False
    if len(d) == 1:
        return any(c in dst for c in _QC_CN_ONE.get(d, ""))
    return any(len(run) >= len(d) for run in _QC_CN_NUM_RE.findall(dst))


def qc_cue_pairs(
    orig_texts: List[str],
    trans_texts: List[str],
    *,
    target_lang: str = "zh",
    glossary: Optional[List[Tuple[str, str]]] = None,
    max_units: float = 16.0,
    max_lines: int = 3,
) -> List[dict]:
    """机翻字幕对照质检：只报能当场判定的可疑句，回 [{i, kinds, why}]（i 从 1 开始）。

    orig_texts 传空串就是跳过所有需要原文的规则 —— 手上只有译文时也能自查换行与复读。
    """
    lang = (target_lang or "zh").strip().lower()
    cjk_target = lang.startswith(("zh", "ja", "ko", "yue"))
    rows: List[dict] = []
    prev_dst = ""
    for i in range(min(len(orig_texts), len(trans_texts))):
        src = (orig_texts[i] or "").strip()
        dst = (trans_texts[i] or "").strip()
        kinds: List[str] = []
        why: List[str] = []
        if not dst:
            if src:
                kinds.append("empty")
                why.append("这一句没有译文")
        else:
            if src and re.search(r"[A-Za-z]{4}", src) and _qc_norm(dst) == _qc_norm(src):
                kinds.append("same")
                why.append("译文和原文一字不差，等于没翻")
            lines = [ln.strip() for ln in dst.split("\n") if ln.strip()]
            worst = max((text_units(ln) for ln in lines), default=0.0)
            if len(lines) > max_lines or worst > max_units * 1.25:
                kinds.append("over")
                why.append(
                    f"最长一行 {worst:g} 个全角宽、整句 {len(lines)} 行，"
                    f"超出每行 ≤{max_units:g} / 最多 {max_lines} 行"
                )
            if i and dst == prev_dst and text_units(dst) >= 6:
                kinds.append("repeat")
                why.append("和上一句的译文完全相同，疑似模型复读")
            tags = _TAG_TXT_RE.findall(src)
            if tags and not _TAG_TXT_RE.findall(dst):
                kinds.append("tag")
                why.append(f"原文的样式标签 {tags[0]} 在译文里丢了")
            us, ud = text_units(src), text_units(dst)
            if src and us >= 8:
                lo, hi = (0.25, 1.6) if cjk_target else (0.6, 3.0)
                if ud < us * lo:
                    kinds.append("short")
                    why.append(f"译文只有 {ud:g} 个全角宽，原文有 {us:g}，可能整段没译")
                elif ud > us * hi:
                    kinds.append("long")
                    why.append(f"译文 {ud:g} 个全角宽，原文只有 {us:g}，可能加了原文没有的内容")
            # 一字不差时「没换成目标语言」是同一件事的另一种说法，只留更准的那条
            if (cjk_target and src and "same" not in kinds
                    and re.search(r"[A-Za-z]{4}", src) and not _CJK_TXT_RE.search(dst)):
                kinds.append("untranslated")
                why.append(f"目标语言是 {_mt_target_name(target_lang)}，这一句里没有出现对应的文字")
            if src:
                ns_, nd_ = _qc_nums(src), _qc_nums(dst)
                lost = [n for n in sorted(ns_ - nd_) if not _qc_num_spelled(dst, n)]
                if lost:
                    kinds.append("number")
                    shown = " / ".join(lost[:3]) + ("…" if len(lost) > 3 else "")
                    why.append(f"原文里的数字 {shown} 在译文里找不到")
        for term, want in (glossary or []):
            if not src or term == want:
                continue
            rx = _glossary_term_re(term)
            if rx.search(src) and want not in dst and not rx.search(dst):
                kinds.append("term")
                why.append(f"术语「{term}」表里要求写作「{want}」，这一句两头都没沾")
        if kinds:
            rows.append({"i": i + 1, "kinds": kinds, "why": why})
        prev_dst = dst
    return rows


def qc_stats(rows: List[dict]) -> dict:
    st: dict = {}
    for r in rows:
        for k in set(r.get("kinds") or []):
            st[k] = st.get(k, 0) + 1
    return st


def qc_stats_text(rows: List[dict]) -> str:
    st = qc_stats(rows)
    return " · ".join(
        f"{QC_KIND_LABELS.get(k, k)} {v}" for k, v in sorted(st.items(), key=lambda x: (-x[1], x[0]))
    )


# -------------------- 字幕时间轴质检：覆盖率 / 最大间隙 / 字符速率 --------------------
# 上面那套是「这句话译得对不对」，得有两路文字才查得了。下面这三条只看这一份字幕自己的
# 时间轴，单语字幕、站点下下来的自动字幕、Whisper 转写产物都能查，不需要另一路原文。
QC_TL_GAP_WARN = 30.0      # 相邻两句之间空多久算「大段没字幕」
QC_TL_MIN_SHOW = 0.4       # 一句显示短于这个秒数，正常速度也读不完
QC_TL_CJK_CPS = 9.0        # 读速上限（全角宽 / 秒）：目标语言是中日韩时
QC_TL_LATIN_CPS = 14.0     # 拉丁语字幕换算成全角宽后的上限
QC_TL_COVERAGE_LOW = 0.35  # 覆盖率低于此值提个醒；这不判错，器乐与无人声段本来就该空着
QC_TL_HALLUC_RUN = 3       # 同一句连着复读这么多条起才报「疑似幻觉」
QC_TL_FILLER_UNITS = 3.0   # 整句不超过这么多个全角宽才有资格被当成语气词

_QC_FILLER_CHARS = set("嗯啊呃哦噢喔唔呜哎唉哎呀啦嘛呗哟哈嘶呐哦嘞")
_QC_FILLER_WORDS = {
    "嗯", "啊", "呃", "哦", "噢", "唔", "呜", "哎", "唉", "呀", "啦", "嘛", "呗", "哟", "哈", "嘶", "嘞",
    "那个", "这个", "就是说", "然后呢", "然后", "对吧", "是吧", "好吧", "好的",
    "um", "uh", "umm", "uhh", "er", "eh", "ah", "oh", "hmm", "hm", "mm", "mhm", "so", "like",
    "yeah", "yep", "well", "right", "ok", "okay", "youknow", "imean", "kinda", "sorta", "righthere",
}
_QC_FILL_SPLIT_RE = re.compile(r"[^\w一-鿿豈-﫿]+", flags=re.UNICODE)
_QC_TAG_ANY_RE = re.compile(r"<[^>]*>")
QC_TL_FLASH = 0.1  # 比这还短的一条是排布产物（滚动式字幕的 0.01 秒闪光条），不参与读速


def _qc_plain(text: str) -> str:
    """量显示宽度之前先把 VTT 的内联标记剥掉。

    karaoke 式字幕每个字后面都挂一个 <00:00:35.626> 时间戳与 <c>，不剥的话一行歌词能算出
    「2500 字每秒」——这是本机一份真字幕实测出来的假数字。
    """
    t = _QC_TAG_ANY_RE.sub("", text or "")
    return t.replace("&nbsp;", " ").strip()


def _qc_is_filler(text: str) -> bool:
    """整句只是语气词 / 口头禅。只报不删 —— 歌词与台词里「啊」「嗯」本来就是要的内容。"""
    t = _QC_FILL_SPLIT_RE.sub(" ", _qc_plain(text)).strip().lower()
    if not t or text_units(t) > QC_TL_FILLER_UNITS:
        return False
    toks = [w for w in t.split() if w]
    if not toks:
        return False
    if all(w in _QC_FILLER_WORDS for w in toks):
        return True
    joined = "".join(toks)
    if joined in _QC_FILLER_WORDS:
        return True
    return len(joined) <= 4 and all(ch in _QC_FILLER_CHARS for ch in joined)


def _qc_halluc_runs(items: List[tuple]) -> List[dict]:
    """同一句连续复读 ≥QC_TL_HALLUC_RUN 条：Whisper 在静音、片尾背景乐上最容易这样吐。"""
    out: List[dict] = []
    norm = [_qc_norm(_qc_plain(tx)) for _n, _s, _e, tx in items]
    i = 0
    while i < len(norm):
        j = i
        while norm[i] and j + 1 < len(norm) and norm[j + 1] == norm[i]:
            j += 1
        if j - i + 1 >= QC_TL_HALLUC_RUN:
            out.append({"from": items[i][0], "to": items[j][0], "count": j - i + 1,
                        "text": (items[i][3] or "")[:60]})
        i = j + 1
    return out


def _qc_tail_band(media_seconds: float) -> float:
    """片尾容忍带：末尾这一段内的空档不计入「最大间隙」。字幕说完后剩的是演职员表与片尾曲。"""
    if media_seconds <= 0:
        return 0.0
    return round(max(10.0, min(90.0, media_seconds * 0.08)), 2)


def _qc_merged(spans: List[Tuple[float, float]]) -> float:
    """区间并集总长（重叠部分只算一次）。"""
    total, cur_s, cur_e = 0.0, None, None
    for s, e in sorted(spans):
        if cur_e is None or s > cur_e:
            if cur_e is not None:
                total += cur_e - cur_s
            cur_s, cur_e = s, e
        else:
            cur_e = max(cur_e, e)
    if cur_e is not None:
        total += cur_e - cur_s
    return round(total, 2)


def qc_timeline(cues: List[dict], *, media_seconds: float = 0.0, target_lang: str = "zh",
                why_no_media: str = "") -> dict:
    """时间轴三维质检。cues 要带 start / end / text（校对台那份行序就是这里的句序）。

    拿不到的输入要如实说「这一项没算」，不能让界面看起来像用户把质检关了。
    """
    lang = (target_lang or "zh").strip().lower()
    cps_limit = QC_TL_CJK_CPS if lang.startswith(("zh", "ja", "ko", "yue")) else QC_TL_LATIN_CPS
    rows = [(i + 1, float(c.get("start") or 0), float(c.get("end") or 0), (c.get("text") or "").strip())
            for i, c in enumerate(cues)]
    band = _qc_tail_band(media_seconds)

    # 覆盖率：有重叠的自动字幕按并集算，不然会算出超过 100%
    spans = [(max(0.0, s), max(0.0, e)) for _n, s, e, _t in rows if e > s]
    spoken = _qc_merged(spans)
    if media_seconds > 0:
        ratio = round(min(spoken / media_seconds, 1.0), 4)
        coverage = {"available": True, "spoken": spoken, "media": round(media_seconds, 2), "ratio": ratio,
                    "level": "low" if ratio < QC_TL_COVERAGE_LOW else "ok",
                    "note": ("覆盖率低本身不是错：器乐、无人声、纯画面的段落本来就该空着，"
                             f"它要和「最大间隙」合起来看才说明问题")}
    else:
        coverage = {"available": False, "spoken": spoken, "media": 0.0, "ratio": None, "level": "unknown",
                    "note": (f"这一项没算：{why_no_media or '拿不到媒体时长'}"
                             "（是缺输入，不是质检被关着）")}

    # 最大间隙
    ordered = sorted(rows, key=lambda r: (r[1], r[2]))
    gaps, overlaps, overlap_secs = [], 0, 0.0
    if ordered and ordered[0][1] > 0.05:
        # 片头空档：第一条字幕之前那段没人说话（或转写没开头），也算一条空档
        gaps.append({"before": ordered[0][0], "at": 0.0, "start": round(ordered[0][1], 2),
                     "seconds": round(ordered[0][1], 2), "in_tail_band": False, "leading": True})
    prev_end = None
    for n, s, e, _t in ordered:
        if prev_end is not None:
            d = round(s - prev_end, 2)
            if d > 0.05:
                gaps.append({"before": n, "at": round(prev_end, 2), "start": round(s, 2), "seconds": d,
                             "in_tail_band": bool(band and media_seconds and prev_end >= media_seconds - band)})
            elif d < -0.05:
                overlaps += 1
                overlap_secs = round(overlap_secs - d, 2)
        prev_end = e if prev_end is None else max(prev_end, e)
    counted = [g for g in gaps if not g["in_tail_band"]]
    worst = max(counted, key=lambda g: g["seconds"]) if counted else None
    tail_gap = round(max(0.0, media_seconds - ordered[-1][2]), 2) if (media_seconds > 0 and ordered) else None
    over_list = sorted((g for g in gaps if g["seconds"] > QC_TL_GAP_WARN), key=lambda g: -g["seconds"])[:8]
    gaps_out = {
        "available": bool(ordered),
        "max": worst["seconds"] if worst else 0.0,
        "before": worst["before"] if worst else 0,
        "count_over": len([g for g in gaps if g["seconds"] > QC_TL_GAP_WARN]),
        "warn": QC_TL_GAP_WARN,
        "over": over_list,
        "leading": round(ordered[0][1], 2) if ordered else 0.0,
        # 拿不到媒体时长时，片尾那段就报「没算」，别让它看起来像量出来是 0 秒
        "tail": ({"available": True, "seconds": tail_gap, "tolerated": True} if tail_gap is not None
                 else {"available": False, "seconds": None, "tolerated": False}),
        "band": band,
        "overlaps": overlaps,
        "overlap_secs": overlap_secs,
        "note": (f"句与句之间超过 {QC_TL_GAP_WARN:g} 秒的空档算一条，第一条之前的片头空档也算一条；"
                 + (f"片尾 {band:g} 秒以内（或末句之后）的空档不计入最大间隙，那段一般是演职员表与片尾曲。" if media_seconds > 0
                    else "末句之后那段没算（拿不到媒体时长，片尾容忍带也无从谈起）。")
                 + "句子之间的少量重叠不算问题：站点自动字幕常用滚动式排布，两条本来就叠在一起。"),
    }

    # 字符速率
    fast, short, reversed_, flash = [], [], [], []
    filler_cues, timed_units = [], []
    for n, s, e, t in rows:
        plain = _qc_plain(t)
        if not plain:
            continue
        if _qc_is_filler(plain):
            filler_cues.append({"i": n, "text": plain[:40], "start": round(s, 2)})
            continue
        if e <= s:
            reversed_.append({"i": n, "text": plain[:40], "start": round(s, 2), "end": round(e, 2)})
            continue
        u = text_units(plain)
        if (e - s) < QC_TL_FLASH:
            # 滚动式字幕会插一条只有 0.01 秒的重复条，它不是给人读的，别拿它算读速
            flash.append({"i": n, "dur": round(e - s, 3), "text": plain[:40]})
            continue
        timed_units.append(round(u / (e - s), 2))
        if u / (e - s) > cps_limit:
            fast.append({"i": n, "start": round(s, 2), "cps": round(u / (e - s), 2), "units": round(u, 1),
                         "dur": round(e - s, 2), "text": plain[:60]})
        elif (e - s) < QC_TL_MIN_SHOW and u >= 1:
            short.append({"i": n, "dur": round(e - s, 2), "text": plain[:40]})
    fast.sort(key=lambda x: -x["cps"])
    speed = {
        "available": bool(timed_units),
        "limit": cps_limit,
        "over": fast[:8],
        "over_count": len(fast),
        "short": short[:8],
        "short_count": len(short),
        "reversed": reversed_[:8],
        "reversed_count": len(reversed_),
        "flash": flash[:8],
        "flash_count": len(flash),
        "median_cps": round(sorted(timed_units)[len(timed_units) // 2], 2) if timed_units else 0.0,
        "note": (f"按显示宽度算，且先把 VTT 的内联标记剥掉：一句 {cps_limit:g} 个全角宽每秒是上限"
                 "（中文约 9、外文换算后约 14）；"
                 f"显示不足 {QC_TL_MIN_SHOW:g} 秒的句子基本读不完。"
                 f"比 {QC_TL_FLASH:g} 秒还短的条目按排布产物看待（站点滚动式字幕的重复闪光条就是这种），"
                 "不参与读速；纯语气词也不参与。"),
    }

    halluc = _qc_halluc_runs(ordered)
    drop = sorted({c["i"] for c in filler_cues} | {n for r in halluc for n in range(r["from"], r["to"] + 1)})
    noise = {
        "fillers": filler_cues,
        "filler_count": len(filler_cues),
        "halluc": halluc,
        "halluc_count": sum(r["count"] for r in halluc),
        "drop": drop,
        "note": ("这两类都只列出来，程序没有替你删：歌词副歌本来就会连着重复，"
                 "纪录片里的「嗯」也可能正是要的内容。要删就在逐句校对台按名单删，保存前照例留一份备份。"),
    }

    bits = []
    if coverage["available"]:
        bits.append(f"覆盖率 {coverage['ratio'] * 100:.0f}%")
    else:
        bits.append("覆盖率没算")
    bits.append((f"片头空了 {gaps_out['max']:g} 秒" if worst and worst.get("leading")
                 else f"最大间隙 {gaps_out['max']:g} 秒" + (f"（第 {gaps_out['before']} 句之前）" if worst else "")))
    if gaps_out["count_over"]:
        bits.append(f"超 {QC_TL_GAP_WARN:g} 秒的空档 {gaps_out['count_over']} 处")
    if speed["available"]:
        bits.append(f"最快读速 {max(timed_units):g} 字每秒" if fast else f"读速最高 {max(timed_units):g} 字每秒")
    if noise["filler_count"] or noise["halluc_count"]:
        bits.append(f"语气词 {noise['filler_count']} 句 / 疑似复读 {noise['halluc_count']} 句")
    return {"thresholds": {"gap": QC_TL_GAP_WARN, "min_show": QC_TL_MIN_SHOW, "cps": cps_limit,
                           "coverage_low": QC_TL_COVERAGE_LOW, "halluc_run": QC_TL_HALLUC_RUN,
                           "tail_band": band},
            "cues": len(rows),
            "coverage": coverage,
            "gaps": gaps_out,
            "speed": speed,
            "noise": noise,
            "message": " · ".join(bits)}


def _qc_media_stems(srt: Path) -> List[str]:
    """字幕文件名剥掉语言后缀后剩下的候选主干，用来在同一个目录里找回配对的媒体文件。"""
    stems, cur = [], srt.stem
    for _ in range(3):
        stems.append(cur)
        m = re.search(r"[._]([A-Za-z][A-Za-z0-9-]{1,7})$", cur)
        if not m:
            break
        tail = m.group(1).lower()
        if not re.fullmatch(r"[a-z]{2,3}(-[a-z0-9]{2,4})?", tail) and tail not in ("bi", "ai", "orig"):
            break
        cur = cur[:m.start()]
    return [s for s in stems if s]


def _qc_media_seconds(srt: Path, media_hint: str = "") -> Tuple[float, str, str]:
    """给时间轴质检找媒体时长。回 (秒数, 媒体路径, 拿不到时的原因)。"""
    cand: Optional[Path] = None
    if (media_hint or "").strip():
        p = Path(media_hint)
        if p.is_file():
            cand = p
    if cand is None:
        for stem in _qc_media_stems(srt):
            for ext in _MEDIA_EXTS:
                q = srt.with_name(stem + ext)
                if q.is_file():
                    cand = q
                    break
            if cand:
                break
            hits = sorted(q for q in srt.parent.glob(stem + "*") if q.suffix.lower() in _MEDIA_EXTS)
            if hits:
                cand = hits[0]
                break
    if cand is None:
        return 0.0, "", f"{srt.name} 旁边找不到配对的媒体文件"
    if not _ffprobe_bin():
        return 0.0, str(cand), "本机没有 ffprobe，探不到媒体时长"
    dur = float((_ffprobe_info(cand) or {}).get("duration") or 0)
    if dur <= 0:
        return 0.0, str(cand), f"ffprobe 读不出 {cand.name} 的时长"
    return round(dur, 2), str(cand), ""


def qc_timeline_of_file(srt: Path, media_hint: str = "", target_lang: str = "zh") -> dict:
    """把一份字幕文件算成时间轴结果。读不动就回空字典 —— 这是自检，不该把流水线带崩。"""
    try:
        cues = _edit_cues(srt)
    except Exception:
        return {}
    if not cues:
        return {}
    secs, _mp, why = _qc_media_seconds(srt, media_hint)
    return qc_timeline(cues, media_seconds=secs, target_lang=target_lang, why_no_media=why)


def qc_timeline_text(tl: dict) -> str:
    """时间轴质检压成一句日志用的话（流水线里用，界面上另有结构化的一份）。"""
    if not tl:
        return ""
    cov, gp, sp, nz = tl["coverage"], tl["gaps"], tl["speed"], tl["noise"]
    head = (f"覆盖率 {cov['ratio'] * 100:.0f}%（{cov['spoken']:g} 秒有字幕 / 媒体 {cov['media']:g} 秒）"
            if cov["available"] else f"覆盖率没算（{cov['note'].split('：', 1)[-1].split('（')[0]}）")
    seg = [head,
           (f"片头空了 {gp['max']:g} 秒（第一条字幕之前）" if gp["leading"] == gp["max"] and gp["max"] > 0
            else f"最大间隙 {gp['max']:g} 秒" + (f"（第 {gp['before']} 句之前）" if gp["max"] else ""))]
    if gp["tail"]["available"]:
        seg.append(f"片尾空档 {gp['tail']['seconds']:g} 秒（不计入）")
    if gp["count_over"]:
        seg.append(f"超 {gp['warn']:g} 秒的空档 {gp['count_over']} 处")
    if sp["available"]:
        seg.append(f"读速超上限 {sp['over_count']} 句" if sp["over_count"] else f"读速都在上限内（中位 {sp['median_cps']:g}）")
    if sp["reversed_count"]:
        seg.append(f"时间轴倒挂 {sp['reversed_count']} 句")
    if nz["filler_count"] or nz["halluc_count"]:
        seg.append(f"语气词 {nz['filler_count']} 句、疑似复读 {nz['halluc_count']} 句（都没替你删）")
    return "字幕时间轴: " + " · ".join(seg)


def _translate_batch_deepl(texts: List[str], target: str, source: str = "", log: Callable = print) -> List[str]:
    key = (cfg.data.get("deepl_api_key") or "").strip()
    if not key:
        raise RuntimeError("未配置 DeepL API Key（设置 → 字幕翻译）")
    # free: https://api-free.deepl.com  pro: https://api.deepl.com
    base = (cfg.data.get("deepl_api_url") or "").strip() or (
        "https://api-free.deepl.com" if key.endswith(":fx") or "free" in key.lower() else "https://api.deepl.com"
    )
    if key.endswith(":fx"):
        base = "https://api-free.deepl.com"
    url = base.rstrip("/") + "/v2/translate"
    tgt = (target or "ZH").upper()
    if tgt in ("ZH-HANS", "ZH-CN", "CHINESE"):
        tgt = "ZH"
    if tgt in ("JA", "JP"):
        tgt = "JA"
    if tgt in ("EN", "EN-US", "EN-GB"):
        tgt = "EN-US"
    data = [("text", t) for t in texts]
    data.append(("target_lang", tgt))
    src = (source or "").upper()
    if src and src not in ("AUTO", ""):
        if src in ("ZH-HANS", "ZH-CN"):
            src = "ZH"
        if src == "JP":
            src = "JA"
        data.append(("source_lang", src))
    headers = {"Authorization": f"DeepL-Auth-Key {key}"}
    r = requests.post(url, data=data, headers=headers, timeout=120)
    if r.status_code >= 400:
        raise RuntimeError(f"DeepL HTTP {r.status_code}: {r.text[:300]}")
    out = r.json().get("translations") or []
    if len(out) != len(texts):
        log(f"DeepL 返回条数 {len(out)} ≠ 请求 {len(texts)}", "warning")
    return [(x.get("text") or "") for x in out]


def _mt_target_name(target: str) -> str:
    return {
        "zh": "Simplified Chinese",
        "zh-cn": "Simplified Chinese",
        "zh-tw": "Traditional Chinese",
        "en": "English",
        "ja": "Japanese",
        "ko": "Korean",
        "fr": "French",
        "de": "German",
        "es": "Spanish",
        "ru": "Russian",
        "pt": "Portuguese",
        "vi": "Vietnamese",
        "th": "Thai",
        "ar": "Arabic",
        "hi": "Hindi",
    }.get((target or "zh").lower(), target or "Simplified Chinese")


def _parse_numbered_lines(content: str, n: int, fallback: List[str]) -> List[str]:
    lines = [ln.strip() for ln in (content or "").split("\n") if ln.strip()]
    cleaned = []
    for ln in lines:
        m = re.match(r"^\d+[\.\)]\s*(.*)$", ln)
        cleaned.append(m.group(1) if m else ln)
    while len(cleaned) < n:
        cleaned.append(fallback[len(cleaned)] if len(cleaned) < len(fallback) else "")
    return cleaned[:n]


def _translate_batch_openai(texts: List[str], target: str, source: str = "", log: Callable = print) -> List[str]:
    key = (cfg.data.get("openai_api_key") or "").strip()
    if not key:
        raise RuntimeError("未配置 OpenAI API Key（设置 → 字幕翻译）")
    base = (cfg.data.get("openai_base_url") or "https://api.openai.com/v1").rstrip("/")
    model = (cfg.data.get("openai_model") or "gpt-4o-mini").strip()
    target_name = _mt_target_name(target)
    src_hint = source or "auto-detect"
    system = (
        "You are a professional subtitle translator. "
        f"Translate each line to {target_name}. "
        "Keep the same number of lines, one translation per line, no numbering, no explanation. "
        "Preserve names/terms when appropriate."
        + glossary_prompt_block()
    )
    results: List[str] = []
    batch_size = 40
    for i in range(0, len(texts), batch_size):
        chunk = texts[i : i + batch_size]
        user = f"Source language hint: {src_hint}\n\n" + "\n".join(
            f"{j+1}. {t}" for j, t in enumerate(chunk)
        )
        payload = {
            "model": model,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        r = requests.post(
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json=payload,
            timeout=180,
        )
        if r.status_code >= 400:
            raise RuntimeError(f"OpenAI HTTP {r.status_code}: {r.text[:300]}")
        content = (((r.json().get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
        results.extend(_parse_numbered_lines(content, len(chunk), chunk))
        log(f"OpenAI 已译 {min(i+batch_size, len(texts))}/{len(texts)}")
    return results


def _translate_batch_claude(texts: List[str], target: str, source: str = "", log: Callable = print) -> List[str]:
    key = (cfg.data.get("anthropic_api_key") or "").strip()
    if not key:
        raise RuntimeError("未配置 Anthropic API Key（Claude）")
    model = (cfg.data.get("anthropic_model") or "claude-sonnet-4-20250514").strip()
    target_name = _mt_target_name(target)
    src_hint = source or "auto-detect"
    system = (
        "You are a professional subtitle translator. "
        f"Translate each line to {target_name}. "
        "Same number of lines, one per line, no numbering or commentary."
        + glossary_prompt_block()
    )
    results: List[str] = []
    batch_size = 40
    for i in range(0, len(texts), batch_size):
        chunk = texts[i : i + batch_size]
        user = f"Source language hint: {src_hint}\n\n" + "\n".join(
            f"{j+1}. {t}" for j, t in enumerate(chunk)
        )
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": 4096,
                "temperature": 0.2,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            },
            timeout=180,
        )
        if r.status_code >= 400:
            raise RuntimeError(f"Claude HTTP {r.status_code}: {r.text[:300]}")
        parts = r.json().get("content") or []
        content = ""
        for p in parts:
            if isinstance(p, dict) and p.get("type") == "text":
                content += p.get("text") or ""
        results.extend(_parse_numbered_lines(content, len(chunk), chunk))
        log(f"Claude 已译 {min(i+batch_size, len(texts))}/{len(texts)}")
    return results


def _translate_batch_gemini(texts: List[str], target: str, source: str = "", log: Callable = print) -> List[str]:
    key = (cfg.data.get("gemini_api_key") or "").strip()
    if not key:
        raise RuntimeError("未配置 Gemini API Key")
    model = (cfg.data.get("gemini_model") or "gemini-2.0-flash").strip()
    target_name = _mt_target_name(target)
    src_hint = source or "auto-detect"
    results: List[str] = []
    batch_size = 40
    glossary_block = glossary_prompt_block()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    for i in range(0, len(texts), batch_size):
        chunk = texts[i : i + batch_size]
        prompt = (
            f"Professional subtitle translation to {target_name}. "
            "Same number of lines, one translation per line, no numbers/comments.\n"
            f"Source hint: {src_hint}{glossary_block}\n\n"
            + "\n".join(f"{j+1}. {t}" for j, t in enumerate(chunk))
        )
        r = requests.post(
            url,
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.2},
            },
            timeout=180,
        )
        if r.status_code >= 400:
            raise RuntimeError(f"Gemini HTTP {r.status_code}: {r.text[:300]}")
        cands = r.json().get("candidates") or []
        content = ""
        try:
            content = cands[0]["content"]["parts"][0]["text"]
        except Exception:
            content = ""
        results.extend(_parse_numbered_lines(content, len(chunk), chunk))
        log(f"Gemini 已译 {min(i+batch_size, len(texts))}/{len(texts)}")
    return results


LLM_REFLECT_KINDS = {
    "openai": "openai", "gpt": "openai", "openrouter": "openai",
    "claude": "anthropic", "anthropic": "anthropic",
    "gemini": "gemini", "google-ai": "gemini",
}
REFLECT_BATCH = 25
REFLECT_CAP = 80
_REFLECT_NO_RE = re.compile(r"(\d+)\s*[.)、:：]\s*(.*)$")


def _parse_reflect_lines(content: str, n: int, fallback: List[str]) -> List[str]:
    """反射修正只收带序号的行。

    模型改成讲道理、合并成一段时按位置硬套会把说明抄进字幕，宁可整句留着第一遍的译文。
    """
    outs: List[str] = []
    for ln in (content or "").splitlines():
        m = _REFLECT_NO_RE.match(ln.strip().lstrip("*#>- ").strip())
        if not m:
            continue
        if len(outs) < n:
            outs.append((m.group(2).strip().strip("*`_").strip() or fallback[len(outs)]))
    while len(outs) < n:
        outs.append(fallback[len(outs)] if len(outs) < len(fallback) else "")
    return outs[:n]


def _reflect_blocks(items: List[Tuple[str, str, str]]) -> str:
    parts = []
    for j, (src, cur, why) in enumerate(items):
        parts.append(f"{j + 1}.\nSOURCE: {src}\nCURRENT: {cur}\nPROBLEM: {why}")
    return "\n".join(parts)


def _reflect_system(target: str) -> str:
    return (
        "You are a professional subtitle editor reviewing machine translation. "
        f"The target language is {_mt_target_name(target)}. "
        "Each block gives a SOURCE line, its CURRENT TRANSLATION and the problem detected. "
        "Rewrite each translation so it is complete, faithful and reads naturally as a subtitle. "
        "Output exactly one numbered line per block containing only the corrected translation "
        "in the target language - no notes, no alternatives, no explanation."
        + glossary_prompt_block()
    )


def _reflect_batch(
    provider: str,
    items: List[Tuple[str, str, str]],
    target: str,
    log: Callable = print,
) -> List[str]:
    """反射修正：可疑句连原文带现译一起交给对话模型再看一遍，回每句的重译（拿不到就留原译）。"""
    kind = LLM_REFLECT_KINDS.get((provider or "").strip().lower())
    if not kind:
        raise RuntimeError(f"{provider} 不是对话模型，做不了反射修正")
    outs: List[str] = []
    prompt_system = _reflect_system(target)
    for i in range(0, len(items), REFLECT_BATCH):
        chunk = items[i : i + REFLECT_BATCH]
        fallback = [c[1] for c in chunk]
        user = _reflect_blocks(chunk)
        content = ""
        if kind == "openai":
            key = (cfg.data.get("openai_api_key") or "").strip()
            if not key:
                raise RuntimeError("未配置 OpenAI API Key（设置 → 字幕翻译）")
            base = (cfg.data.get("openai_base_url") or "https://api.openai.com/v1").rstrip("/")
            model = (cfg.data.get("openai_model") or "gpt-4o-mini").strip()
            r = requests.post(
                f"{base}/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "temperature": 0.2,
                    "messages": [
                        {"role": "system", "content": prompt_system},
                        {"role": "user", "content": user},
                    ],
                },
                timeout=180,
            )
            if r.status_code >= 400:
                raise RuntimeError(f"OpenAI HTTP {r.status_code}: {r.text[:300]}")
            content = (((r.json().get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
        elif kind == "anthropic":
            key = (cfg.data.get("anthropic_api_key") or "").strip()
            if not key:
                raise RuntimeError("未配置 Anthropic API Key（Claude）")
            model = (cfg.data.get("anthropic_model") or "claude-sonnet-4-20250514").strip()
            r = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "max_tokens": 4096,
                    "temperature": 0.2,
                    "system": prompt_system,
                    "messages": [{"role": "user", "content": user}],
                },
                timeout=180,
            )
            if r.status_code >= 400:
                raise RuntimeError(f"Claude HTTP {r.status_code}: {r.text[:300]}")
            for p in r.json().get("content") or []:
                if isinstance(p, dict) and p.get("type") == "text":
                    content += p.get("text") or ""
            content = content.strip()
        else:
            key = (cfg.data.get("gemini_api_key") or "").strip()
            if not key:
                raise RuntimeError("未配置 Gemini API Key")
            model = (cfg.data.get("gemini_model") or "gemini-2.0-flash").strip()
            r = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}",
                headers={"Content-Type": "application/json"},
                json={
                    "contents": [{"parts": [{"text": prompt_system + "\n\n" + user}]}],
                    "generationConfig": {"temperature": 0.2},
                },
                timeout=180,
            )
            if r.status_code >= 400:
                raise RuntimeError(f"Gemini HTTP {r.status_code}: {r.text[:300]}")
            try:
                content = ((r.json().get("candidates") or [{}])[0]["content"]["parts"][0]["text"]).strip()
            except Exception:
                content = ""
        outs.extend(_parse_reflect_lines(content, len(chunk), fallback))
        log(f"反射修正已处理 {min(i + REFLECT_BATCH, len(items))}/{len(items)}")
    return outs


def _google_lang_code(code: str) -> str:
    c = (code or "zh").lower()
    return {
        "zh": "zh-CN",
        "zh-cn": "zh-CN",
        "zh-tw": "zh-TW",
        "en": "en",
        "ja": "ja",
        "ko": "ko",
        "fr": "fr",
        "de": "de",
        "es": "es",
        "ru": "ru",
        "pt": "pt",
        "vi": "vi",
        "th": "th",
        "ar": "ar",
        "hi": "hi",
        "auto": "",
    }.get(c, c)


def _translate_batch_google(texts: List[str], target: str, source: str = "", log: Callable = print) -> List[str]:
    """Google Cloud Translation API v2（API Key）。"""
    key = (cfg.data.get("google_translate_api_key") or "").strip()
    if not key:
        raise RuntimeError("未配置 Google Translate API Key")
    target_c = _google_lang_code(target) or "zh-CN"
    source_c = _google_lang_code(source) if source and source not in ("auto", "") else None
    results: List[str] = []
    batch_size = 50  # v2 单次建议不要过大
    url = "https://translation.googleapis.com/language/translate/v2"
    for i in range(0, len(texts), batch_size):
        chunk = texts[i : i + batch_size]
        params = {"key": key}
        data = {"q": chunk, "target": target_c, "format": "text"}
        if source_c:
            data["source"] = source_c
        r = requests.post(url, params=params, json=data, timeout=120)
        if r.status_code >= 400:
            raise RuntimeError(f"Google Translate HTTP {r.status_code}: {r.text[:300]}")
        tr = ((r.json().get("data") or {}).get("translations")) or []
        for j, item in enumerate(tr):
            results.append(item.get("translatedText") or chunk[j])
        while len(results) < i + len(chunk):
            results.append(chunk[len(results) - i])
        log(f"Google 已译 {min(i+batch_size, len(texts))}/{len(texts)}")
    return results[: len(texts)]


def _translate_batch_azure(texts: List[str], target: str, source: str = "", log: Callable = print) -> List[str]:
    key = (cfg.data.get("azure_translator_key") or "").strip()
    region = (cfg.data.get("azure_translator_region") or "global").strip()
    if not key:
        raise RuntimeError("未配置 Azure Translator Key")
    endpoint = (cfg.data.get("azure_translator_endpoint") or "https://api.cognitive.microsofttranslator.com").rstrip("/")
    tgt = _google_lang_code(target).replace("zh-CN", "zh-Hans").replace("zh-TW", "zh-Hant") or "zh-Hans"
    src = _google_lang_code(source).replace("zh-CN", "zh-Hans") if source and source not in ("auto", "") else None
    results: List[str] = []
    batch_size = 50
    headers = {
        "Ocp-Apim-Subscription-Key": key,
        "Ocp-Apim-Subscription-Region": region,
        "Content-Type": "application/json",
    }
    for i in range(0, len(texts), batch_size):
        chunk = texts[i : i + batch_size]
        params = {"api-version": "3.0", "to": tgt}
        if src:
            params["from"] = src
        body = [{"text": t} for t in chunk]
        r = requests.post(f"{endpoint}/translate", params=params, headers=headers, json=body, timeout=120)
        if r.status_code >= 400:
            raise RuntimeError(f"Azure Translator HTTP {r.status_code}: {r.text[:300]}")
        arr = r.json() if isinstance(r.json(), list) else []
        for j, item in enumerate(arr):
            trs = item.get("translations") or []
            results.append((trs[0].get("text") if trs else None) or chunk[j])
        log(f"Azure 已译 {min(i+batch_size, len(texts))}/{len(texts)}")
    return results[: len(texts)]


def translate_srt_file(
    srt_path: str,
    *,
    provider: str = "",
    target_lang: str = "zh",
    source_lang: str = "",
    log: Callable = print,
) -> str:
    """
    将已有 SRT 机翻为新文件。
    provider: deepl | openai | claude | gemini | google | azure
    """
    p = Path(srt_path)
    if not p.is_file():
        raise FileNotFoundError(str(p))
    cues = parse_srt(p.read_text(encoding="utf-8", errors="ignore"))
    if not cues:
        raise RuntimeError("SRT 无有效条目")
    provider = (provider or cfg.data.get("subtitle_translate_provider") or "deepl").strip().lower()
    target_lang = (target_lang or cfg.data.get("subtitle_target_lang") or "zh").strip()
    texts = [c["text"] for c in cues]
    glossary = parse_glossary()
    if glossary:
        log(f"字幕机翻: 术语表已启用（{len(glossary)} 条）")
    log(f"字幕机翻: {p.name} → {target_lang} prefer={provider}（{len(texts)} 条）")

    def _dt_fn(tx, tgt, src, lg):
        from voice_tools import translate_batch_deep_translator
        return translate_batch_deep_translator(tx, tgt, src or "auto", lg)

    fns = {
        "deepl": lambda tx, tgt, src, lg: _translate_batch_deepl(tx, tgt, src, lg),
        "openai": lambda tx, tgt, src, lg: _translate_batch_openai(tx, tgt, src, lg),
        "gpt": lambda tx, tgt, src, lg: _translate_batch_openai(tx, tgt, src, lg),
        "openrouter": lambda tx, tgt, src, lg: _translate_batch_openai(tx, tgt, src, lg),
        "claude": lambda tx, tgt, src, lg: _translate_batch_claude(tx, tgt, src, lg),
        "anthropic": lambda tx, tgt, src, lg: _translate_batch_claude(tx, tgt, src, lg),
        "gemini": lambda tx, tgt, src, lg: _translate_batch_gemini(tx, tgt, src, lg),
        "google-ai": lambda tx, tgt, src, lg: _translate_batch_gemini(tx, tgt, src, lg),
        "google": lambda tx, tgt, src, lg: _translate_batch_google(tx, tgt, src, lg),
        "google-translate": lambda tx, tgt, src, lg: _translate_batch_google(tx, tgt, src, lg),
        "azure": lambda tx, tgt, src, lg: _translate_batch_azure(tx, tgt, src, lg),
        "microsoft": lambda tx, tgt, src, lg: _translate_batch_azure(tx, tgt, src, lg),
        "deep_translator": _dt_fn,
        "deep-translator": _dt_fn,
        "free": _dt_fn,
    }
    auto_fb = cfg.data.get("translate_auto_fallback", True)
    used = provider
    if auto_fb:
        from voice_tools import translate_with_fallback
        translated, used = translate_with_fallback(
            texts, preferred=provider, target_lang=target_lang,
            source_lang=source_lang, translate_fns=fns, log=log,
        )
        log(f"机翻实际使用引擎: {used}")
    else:
        fn = fns.get(provider)
        if not fn:
            raise RuntimeError(f"不支持的翻译引擎: {provider}")
        translated = fn(texts, target_lang, source_lang, log)

    timings = [c.get("timing") for c in cues]
    raw_trans: List[str] = []
    fixed = 0
    for c, t in zip(cues, translated):
        t = t or c["text"]
        if glossary:
            g = apply_glossary(t, glossary)
            if g != t:
                fixed += 1
                t = g
        c["text"] = t
        raw_trans.append(t)
    if glossary and fixed:
        log(f"术语表统一了 {fixed} 条字幕的译名")

    max_units = float(cfg.data.get("subtitle_wrap_width") or 16)
    max_units = max(8.0, min(40.0, max_units))
    max_lines = int(cfg.data.get("subtitle_wrap_lines") or 3)
    max_lines = max(1, min(4, max_lines))
    do_wrap = bool(cfg.data.get("subtitle_wrap", True))

    def _wrap(raw: List[str]) -> List[dict]:
        cues2 = [{"timing": tm, "text": tx} for tm, tx in zip(timings, raw)]
        return wrap_cues(cues2, max_units, max_lines) if do_wrap else cues2

    trans_cues = _wrap(raw_trans)
    orig_cues = _wrap(texts)
    if do_wrap:
        log(f"字幕换行: 每行 ≤{max_units:g} 个全角宽、最多 {max_lines} 行（中英文按显示宽度加权）")

    qc_rows: List[dict] = []
    if bool(cfg.data.get("subtitle_qc", True)):
        qc_rows = qc_cue_pairs(
            texts, [c["text"] for c in trans_cues], target_lang=target_lang,
            glossary=glossary, max_units=max_units, max_lines=max_lines,
        )
        if qc_rows:
            log(f"字幕质检: {len(qc_rows)} 句可疑（{qc_stats_text(qc_rows)}）")
            for r in qc_rows[:20]:
                log(f"  可疑第 {r['i']} 句: " + "；".join(r["why"]), "warning")
            if len(qc_rows) > 20:
                log(f"  其余 {len(qc_rows) - 20} 句同上，逐句校对台里能看全")
        else:
            log("字幕质检: 没有发现可疑句")

        fixable = [r for r in qc_rows if set(r["kinds"]) & set(QC_REFLECT_KINDS)]
        if fixable and bool(cfg.data.get("subtitle_qc_reflect", False)):
            picked = fixable[:REFLECT_CAP]
            if len(fixable) > REFLECT_CAP:
                log(f"可疑 {len(fixable)} 句，本轮只反射修正前 {REFLECT_CAP} 句")
            try:
                answers = _reflect_batch(
                    used, [(texts[r["i"] - 1], raw_trans[r["i"] - 1], "；".join(r["why"])) for r in picked],
                    target_lang, log,
                )
            except Exception as e:
                answers = []
                log(f"反射修正没做成（{e}），保留第一遍译文", "warning")
            applied = 0
            for r, ans in zip(picked, answers):
                a = (ans or "").strip()
                k = r["i"] - 1
                if a and a != raw_trans[k]:
                    raw_trans[k] = apply_glossary(a, glossary) if glossary else a
                    applied += 1
            if applied:
                log(f"反射修正重写了 {applied} 句，重新换行并复检")
                trans_cues = _wrap(raw_trans)
                re_rows = qc_cue_pairs(
                    texts, [c["text"] for c in trans_cues], target_lang=target_lang,
                    glossary=glossary, max_units=max_units, max_lines=max_lines,
                )
                log(f"复检: 仍有 {len(re_rows)} 句可疑" + (f"（{qc_stats_text(re_rows)}）" if re_rows else ""))
                qc_rows = re_rows
        elif fixable:
            log("反射修正没开（设置 → 字幕翻译），可疑句只报告不改动")

        # 时间轴三维：覆盖率 / 最大间隙 / 字符速率 —— 不吃「另一路」，单语字幕也算得出来
        tl_cues = []
        for c in trans_cues:
            left, _, right = (c.get("timing") or "").partition("-->")
            tl_cues.append({"start": _srt_ts_to_ms(left) / 1000.0,
                            "end": _srt_ts_to_ms(right) / 1000.0,
                            "text": c.get("text") or ""})
        secs, _mp, why = _qc_media_seconds(p, "")
        tl = qc_timeline(tl_cues, media_seconds=secs, target_lang=target_lang, why_no_media=why)
        log(qc_timeline_text(tl))
        for g in tl["gaps"]["over"][:3]:
            log(f"  {'片头空了' if g.get('leading') else '第 ' + str(g['before']) + ' 句之前空了'} {g['seconds']:g} 秒", "warning")
        for f in tl["speed"]["over"][:3]:
            log(f"  第 {f['i']} 句读速 {f['cps']:g} 字 / 秒（{f['units']:g} 个字挤在 {f['dur']:g} 秒里）", "warning")
        for r in tl["speed"]["reversed"]:
            log(f"  第 {r['i']} 句结束时间比开始还早（{r['start']:g} → {r['end']:g}）", "warning")
        for h in tl["noise"]["halluc"][:3]:
            log(f"  第 {h['from']}～{h['to']} 句是同一句连着复读 {h['count']} 遍：{h['text']}", "warning")
        if tl["noise"]["drop"]:
            d = tl["noise"]["drop"]
            log("  上面点名的语气词与复读句没有替你删（歌词副歌本来就会重复，得看片子）；"
                "要删请在「逐句校对 → 字幕质检」按名单删："
                + "、".join(str(x) for x in d[:12]) + ("…" if len(d) > 12 else ""))
    else:
        log("字幕质检没开（设置 → 字幕翻译）：这一轮逐句对照与时间轴三维都没跑，"
            "日志里看不到质检行不等于「查过且没问题」")

    suffix = target_lang.lower().replace("en-us", "en").replace("zh-cn", "zh").replace("zh-hans", "zh")
    out = p.with_name(p.stem + f".{suffix}.srt")
    if out.resolve() == p.resolve():
        out = p.with_name(p.stem + ".translated.srt")
    out.write_text(write_srt(trans_cues), encoding="utf-8")
    log(f"机翻完成: {out.name}")

    export_set = str(cfg.data.get("subtitle_export_set") or "single").strip().lower()
    if export_set in ("bilingual", "all", "full", "双语", "全部"):
        bi_lines = max(1, min(2, max_lines))
        bi_trans = wrap_cues([{"timing": tm, "text": tx} for tm, tx in zip(timings, raw_trans)], max_units, bi_lines) if do_wrap else trans_cues
        bi_orig = wrap_cues([{"timing": tm, "text": tx} for tm, tx in zip(timings, texts)], max_units, bi_lines) if do_wrap else orig_cues
        bi = merge_bilingual_cues(bi_trans, bi_orig)
        bi_srt = p.with_name(f"{p.stem}.{suffix}.bi.srt")
        bi_srt.write_text(write_srt(bi), encoding="utf-8")
        log(f"双语字幕(译上原下): {bi_srt.name}")
        if export_set in ("all", "full"):
            bi_vtt = p.with_name(f"{p.stem}.{suffix}.bi.vtt")
            bi_vtt.write_text(write_vtt(bi), encoding="utf-8")
            log(f"双语字幕 VTT: {bi_vtt.name}")
            bi_ass = p.with_name(f"{p.stem}.{suffix}.bi.ass")
            bi_ass.write_text(
                srt_to_ass(wrap_cues(bi_orig, max_units * 1.6, 1), bi_trans, title=p.stem),
                encoding="utf-8",
            )
            log(f"双语字幕 ASS(译文居下/原文居上): {bi_ass.name}")
    return str(out)


def _qc_report_written(paths: List[str], media: Path, lang: str, log: Callable = print) -> None:
    """刚转写出来的字幕顺手算一遍时间轴三维：只写日志，一个字都不动文件。"""
    for f in paths:
        q = Path(f)
        if q.suffix.lower() not in (".srt", ".vtt") or not q.is_file():
            continue
        tl = qc_timeline_of_file(q, str(media), lang or "zh")
        if not tl:
            continue
        log(qc_timeline_text(tl))
        if tl["noise"]["drop"]:
            d = tl["noise"]["drop"]
            log("  转写产物里的语气词与复读句没有替你删（Whisper 在静音与片尾背景乐上最容易复读，"
                "歌词副歌又是真的会重复）：句 " + "、".join(str(x) for x in d[:10])
                + ("…" if len(d) > 10 else "") + "；要删请在「逐句校对 → 字幕质检」按名单删")


def run_local_ai_on_file(
    media_path: str,
    *,
    transcribe: bool = True,
    translate: bool = False,
    lang: str = "zh",
    log: Callable = print,
    model: str = "",
    device: str = "",
    compute: str = "",
) -> List[str]:
    """
    本地 AI 转写/翻译：
    1) faster-whisper（可配置模型/设备）
    2) web_app/Whisper 目录内可执行文件
    3) PATH 中的 whisper CLI
    """
    out_files: List[str] = []
    p = Path(media_path)
    if not p.exists():
        return out_files

    wc = _whisper_cfg()
    model = model or wc["model"]
    device = device or wc["device"]
    compute = compute or wc["compute"]
    lang = lang or wc["lang"]

    # 1) faster-whisper
    if transcribe:
        try:
            r = _whisper_via_faster(
                p, "transcribe", lang, log,
                model_size=model, device_pref=device, compute_pref=compute,
            )
            if r and r.exists():
                out_files.append(str(r))
                transcribe = False  # 已完成
        except Exception as e:
            log(f"faster-whisper 转写失败，尝试 CLI: {e}", "warning")
    if translate:
        try:
            r = _whisper_via_faster(
                p, "translate", lang, log,
                model_size=model, device_pref=device, compute_pref=compute,
            )
            if r and r.exists():
                out_files.append(str(r))
                translate = False
        except Exception as e:
            log(f"faster-whisper 翻译失败，尝试 CLI: {e}", "warning")

    if not transcribe and not translate:
        _qc_report_written(out_files, p, lang, log)
        return out_files

    # 2/3) CLI
    whisper = _find_local_whisper_bin()
    if not whisper:
        log(
            "本地 AI: 未找到 faster-whisper 或 Whisper 可执行文件。"
            f"请 pip install faster-whisper 或把程序放到 {WHISPER_DIR}",
            "warning",
        )
        _qc_report_written(out_files, p, lang, log)
        return out_files
    out_dir = str(p.parent)
    base_cmd = [whisper, str(p), "--output_dir", out_dir, "--output_format", "srt"]
    if transcribe:
        cmd = base_cmd + ["--task", "transcribe"]
        if lang and lang not in ("auto", ""):
            cmd += ["--language", "Chinese" if lang in ("zh", "chinese") else lang]
        log(f"Whisper CLI 转写: {cmd[0]}")
        try:
            kw: dict = {"capture_output": True, "timeout": 7200}
            if sys.platform == "win32":
                kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            subprocess.run(cmd, **kw)
            srt = p.with_suffix(".srt")
            if srt.exists():
                out_files.append(str(srt))
                log(f"转写完成: {srt.name}")
        except Exception as e:
            log(f"转写异常: {e}", "warning")
    if translate:
        cmd = base_cmd + ["--task", "translate"]
        log(f"Whisper CLI 翻译: {cmd[0]}")
        try:
            kw = {"capture_output": True, "timeout": 7200}
            if sys.platform == "win32":
                kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            subprocess.run(cmd, **kw)
            srt = p.with_suffix(".srt")
            en_srt = p.with_name(p.stem + ".en.srt")
            if srt.exists():
                try:
                    shutil.copy(srt, en_srt)
                    out_files.append(str(en_srt))
                    log(f"翻译完成: {en_srt.name}")
                except Exception:
                    out_files.append(str(srt))
        except Exception as e:
            log(f"翻译异常: {e}", "warning")
    _qc_report_written(out_files, p, lang, log)
    return out_files


def download_bilibili_danmaku(url: str, out_dir: str, base_name: str, proxy: str = "", log: Callable = print) -> List[str]:
    """下载 bilibili 弹幕，保存 xml + ass，返回文件路径列表"""
    if not is_bilibili_url(url):
        return []
    meta = bilibili_fetch_cid(url, proxy)
    if not meta:
        log(f"弹幕: 无法解析 cid — {url}", "warning")
        return []
    cid, title = meta
    xml_text = bilibili_download_danmaku_xml(cid, proxy)
    if not xml_text:
        log(f"弹幕: 下载 XML 失败 cid={cid}", "warning")
        return []
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    safe = re.sub(r'[<>:"/\\|?*]', "_", base_name or title)[:80]
    xml_path = Path(out_dir) / f"{safe}.danmaku.xml"
    ass_path = Path(out_dir) / f"{safe}.danmaku.ass"
    xml_path.write_text(xml_text, encoding="utf-8")
    try:
        ass_path.write_text(bilibili_xml_to_ass(xml_text, title), encoding="utf-8")
    except Exception as e:
        log(f"弹幕 ASS 转换失败: {e}", "warning")
        return [str(xml_path)]
    log(f"弹幕已保存: {xml_path.name} / {ass_path.name}")
    return [str(xml_path), str(ass_path)]


def _stop_live_recorder_children(hints: List[str], log: Callable = None) -> List[str]:
    """结束直播录制时把 yt-dlp 派出去拉流的 ffmpeg 子进程收掉。

    停止标记只是让 Python 侧别再开新场次：HLS 直播是由 ffmpeg 直接写文件的，它的 stderr
    是静默的，progress_hook 全程不回调，所以任务已经标成「已结束」、这个子进程还在往成品里
    写（文件一直变大、也删不掉，下次扫描还会撞上没写完的那一份）。只认「本程序派下的 +
    命令行里点名了这场成品」的那几个；认不出来就只在本目录恰好只剩一路拉流时收，
    分不清是谁的宁可不杀，免得误伤另一间房 or 用户自己的 ffmpeg。
    """
    killed: List[str] = []
    try:
        import psutil
    except Exception:
        if log:
            log("缺 psutil，结束录制时没法核对拉流子进程：成品可能还在变大", "warning")
        return killed
    me = os.getpid()
    cands = []
    for p in psutil.process_iter(["pid", "ppid", "name", "cmdline"]):
        try:
            if int(p.info.get("ppid") or -1) != me:
                continue
            nm = str(p.info.get("name") or "").lower()
            if not (nm.startswith("ffmpeg") or nm.startswith("avconv")):
                continue
            cmd = " ".join(p.info.get("cmdline") or [])
            if "://" not in cmd:
                # 拉流子进程的输入是 URL；本机转码/剪辑的输入都是本地文件，靠这条分开
                continue
            cands.append((p, cmd))
        except Exception:
            continue
    if not cands:
        return killed
    targets = [(p, c) for p, c in cands if any(h and h in c for h in (hints or []))]
    if not targets and len(cands) == 1:
        targets = list(cands)
    for p, _ in targets:
        try:
            p.terminate()
            try:
                p.wait(5)
            except Exception:
                p.kill()
            killed.append(str(p.pid))
            if log:
                log(f"已结束这一场的拉流子进程（PID {p.pid}），成品不再继续变大")
        except Exception as e:
            if log:
                log(f"拉流子进程 PID {p.pid} 没能收掉: {e}", "warning")
    return killed


def _find_recent_media_files(out_dir: str, hint: str = "", within_sec: int = 86400) -> List[str]:
    """在下载目录找最近生成的媒体文件（直播结束收尾用）"""
    root = Path(out_dir)
    if not root.is_dir():
        return []
    now = time.time()
    hint_tokens = []
    if hint:
        hint_tokens = re.findall(r"\d{5,}", hint) + [hint[-20:].lower()]
    exts = {".flv", ".mp4", ".mkv", ".ts", ".webm", ".m4a", ".mp3"}
    found = []
    for p in root.iterdir():
        if not p.is_file():
            continue
        name = p.name
        low = name.lower()
        if low.endswith(".part"):
            # 一并纳入，由 finalize 处理
            pass
        suf = p.suffix.lower()
        if suf not in exts and not low.endswith(".part"):
            continue
        try:
            if now - p.stat().st_mtime > within_sec:
                continue
        except Exception:
            continue
        if hint_tokens:
            if not any(tok and tok in name for tok in hint_tokens):
                continue
        found.append(p)
    found.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    return [str(p) for p in found]


def finalize_part_files(out_dir: str, hint: str = "", log: Callable = print) -> List[str]:
    """结束直播后：把 .part 收成可播放文件（改名 + 可选封装 mkv）"""
    root = Path(out_dir)
    if not root.is_dir():
        return []
    done = []
    hint_low = (hint or "").lower().strip()
    candidates = []
    for p in root.iterdir():
        if not p.is_file():
            continue
        name = p.name
        if not (name.endswith(".part") or name.endswith(".ytdl")):
            continue
        if hint_low:
            # 房间号或关键词命中优先；hint 为空则处理全部
            if hint_low not in name.lower() and not any(
                tok and tok in name for tok in re.findall(r"\d{5,}", hint_low)
            ):
                # 仍允许：无匹配时若只有少量 part 也处理
                pass
        candidates.append(p)

    for part in sorted(candidates, key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            if part.name.endswith(".ytdl"):
                part.unlink(missing_ok=True)
                continue
            # file.flv.part → file.flv
            final_name = part.name
            if final_name.endswith(".part"):
                final_name = final_name[:-5]
            final = part.with_name(final_name)
            if final.exists():
                # 若成品已存在且不更小，删 part
                if final.stat().st_size >= part.stat().st_size * 0.9:
                    part.unlink(missing_ok=True)
                    done.append(str(final))
                    continue
                final = part.with_name(f"{final.stem}_fixed{final.suffix}")
            try:
                part.rename(final)
            except Exception:
                import shutil
                shutil.copy2(part, final)
                try:
                    part.unlink()
                except Exception:
                    pass
            log(f"已收尾临时文件 → {final.name}")
            done.append(str(final))
            # flv/ts → mkv 便于通用播放器
            if final.suffix.lower() in (".flv", ".ts") and ffmpeg_mgr.find():
                mkv = final.with_suffix(".mkv")
                if not mkv.exists():
                    try:
                        import subprocess
                        cmd = [
                            ffmpeg_mgr.find(), "-y", "-err_detect", "ignore_err",
                            "-i", str(final), "-c", "copy",
                            "-avoid_negative_ts", "make_zero", str(mkv),
                        ]
                        subprocess.run(cmd, capture_output=True, timeout=900)
                        if mkv.exists() and mkv.stat().st_size > 1024:
                            log(f"已封装为 {mkv.name}")
                            done.append(str(mkv))
                    except Exception as e:
                        log(f"封装 mkv 跳过: {e}", "warning")
        except Exception as e:
            log(f"收尾 {part.name} 失败: {e}", "warning")
    return done


def _ass_time(sec: float) -> str:
    sec = max(0.0, float(sec))
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _srt_time(sec: float) -> str:
    sec = max(0.0, float(sec))
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    ms = int(round((sec - int(sec)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_chat_subtitle_files(
    base_path: Path,
    messages: List[dict],
    title: str = "live chat",
    duration_each: float = 4.0,
) -> List[str]:
    """
    把聊天列表写成播放器可读字幕：
    - .ass（推荐，弹幕风）
    - .srt（通用）
    messages: {time, user, text, t_sec?}
    """
    if not messages:
        return []
    out = []
    # 为每条分配时间轴：优先 t_sec，否则顺序递增
    timed = []
    cursor = 0.0
    for i, m in enumerate(messages):
        text = (m.get("text") or "").strip()
        if not text:
            continue
        user = (m.get("user") or "").strip()
        line = f"{user}: {text}" if user else text
        line = line.replace("\n", " ").replace("{", "(").replace("}", ")")
        t0 = m.get("t_sec")
        if t0 is None:
            t0 = cursor
        try:
            t0 = float(t0)
        except Exception:
            t0 = cursor
        t1 = t0 + duration_each
        timed.append((t0, t1, line))
        cursor = t0 + 0.6

    if not timed:
        return []

    # ASS
    ass_path = base_path.with_suffix(".ass")
    try:
        header = (
            "[Script Info]\n"
            f"Title: {title}\n"
            "ScriptType: v4.00+\n"
            "PlayResX: 1920\n"
            "PlayResY: 1080\n"
            "WrapStyle: 0\n"
            "ScaledBorderAndShadow: yes\n\n"
            "[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
            "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
            "Alignment, MarginL, MarginR, MarginV, Encoding\n"
            "Style: Default,Microsoft YaHei,42,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,"
            "0,0,0,0,100,100,0,0,1,2,1,2,20,20,40,1\n\n"
            "[Events]\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        )
        events = []
        for t0, t1, line in timed:
            events.append(
                f"Dialogue: 0,{_ass_time(t0)},{_ass_time(t1)},Default,,0,0,0,,{line}"
            )
        ass_path.write_text(header + "\n".join(events) + "\n", encoding="utf-8-sig")
        out.append(str(ass_path))
    except Exception:
        pass

    # SRT
    srt_path = base_path.with_suffix(".srt")
    try:
        blocks = []
        for i, (t0, t1, line) in enumerate(timed, 1):
            blocks.append(f"{i}\n{_srt_time(t0)} --> {_srt_time(t1)}\n{line}\n")
        srt_path.write_text("\n".join(blocks), encoding="utf-8-sig")
        out.append(str(srt_path))
    except Exception:
        pass
    return out


def live_stream_pref_for_url(url: str, cfg_data: dict) -> str:
    """根据平台返回直播流偏好: auto|hls|flv|dash"""
    low = (url or "").lower()
    if "live.bilibili.com" in low or "bilibili.com" in low:
        return (cfg_data.get("live_stream_pref_bilibili") or "flv").lower()
    if "youtube.com" in low or "youtu.be" in low:
        return (cfg_data.get("live_stream_pref_youtube") or "dash").lower()
    if "douyin.com" in low or "iesdouyin.com" in low or "tiktok.com" in low:
        return (cfg_data.get("live_stream_pref_douyin") or "hls").lower()
    if "twitch.tv" in low:
        return (cfg_data.get("live_stream_pref_twitch") or "hls").lower()
    return (cfg_data.get("live_stream_pref_default") or "auto").lower()


def live_format_selector(pref: str, *, platform_hint: str = "") -> str:
    """
    把流偏好转成 yt-dlp format 串。
    flv: 倾向 http-flv
    hls: 倾向 m3u8
    dash: 分轨 bestvideo+bestaudio
    auto: 通用 best
    """
    p = (pref or "auto").lower()
    if p == "flv":
        # 优先带 flv 的格式，否则退回 best
        return "best[protocol*=http]/best[ext=flv]/best/bestvideo+bestaudio/best"
    if p == "hls":
        return "best[protocol*=m3u8]/best[protocol*=hls]/best/bestvideo+bestaudio/best"
    if p == "dash":
        return "bestvideo+bestaudio/best[protocol*=http]/best"
    return "best/bestvideo+bestaudio/best"


def extract_bilibili_live_room_id(url: str) -> Optional[str]:
    m = re.search(r"live\.bilibili\.com/(\d+)", url or "")
    return m.group(1) if m else None


def extract_youtube_video_id(url: str) -> Optional[str]:
    u = url or ""
    m = re.search(r"(?:v=|/live/|youtu\.be/)([\w-]{11})", u)
    return m.group(1) if m else None


def extract_twitch_channel(url: str) -> Optional[str]:
    m = re.search(r"(?:twitch\.tv/)([A-Za-z0-9_]+)", url or "", re.I)
    if not m:
        return None
    ch = m.group(1)
    if ch.lower() in ("videos", "directory", "downloads", "settings", "login"):
        return None
    return ch


def fetch_bilibili_live_chat_history(room_id: str, proxy: str = "") -> List[dict]:
    """拉取 B站直播间近期弹幕/聊天（官方历史接口）"""
    if not room_id:
        return []
    try:
        kw = _bili_request_kwargs(proxy=proxy)
        r = requests.get(
            "https://api.live.bilibili.com/xlive/web-room/v1/dM/gethistory",
            params={"roomid": room_id},
            **kw,
        )
        j = r.json() or {}
        data = j.get("data") or {}
        msgs = []
        for it in (data.get("room") or []):
            msgs.append({
                "time": it.get("timeline") or it.get("ts") or "",
                "user": it.get("nickname") or it.get("uname") or "",
                "text": it.get("text") or "",
                "uid": it.get("uid") or "",
            })
        return msgs
    except Exception:
        return []


def convert_youtube_live_chat_json_to_txt(json_path: Path, txt_path: Path) -> int:
    """把 yt-dlp 下载的 YouTube live_chat json/json3 转成可读 txt"""
    count = 0
    try:
        raw = json_path.read_text(encoding="utf-8", errors="ignore")
        data = json.loads(raw)
    except Exception:
        return 0
    lines = []
    # json3 结构：events 列表
    events = data.get("events") or data.get("replayChatItemAction") or []
    if isinstance(data, list):
        events = data
    for ev in events:
        try:
            if not isinstance(ev, dict):
                continue
            # youtube json3 live_chat
            segs = (
                ((ev.get("message") or {}).get("runs") or [])
                or ((ev.get("a11y_message") or "").split() and [])
            )
            text = ""
            if segs:
                text = "".join(s.get("text") or "" for s in segs if isinstance(s, dict))
            if not text:
                text = ev.get("message") or ev.get("a11y_message") or ""
                if isinstance(text, dict):
                    text = "".join(
                        (r.get("text") or "") for r in (text.get("runs") or []) if isinstance(r, dict)
                    )
            author = ""
            auth = ev.get("author") or ev.get("author_external_channel_id") or ""
            if isinstance(auth, dict):
                author = auth.get("name") or auth.get("id") or ""
            else:
                author = str(auth or "")
            ts = ev.get("timestamp") or ev.get("time_text") or ev.get("t") or ""
            if not text:
                # replayChatItemAction 嵌套
                actions = (ev.get("replayChatItemAction") or {}).get("actions") or []
                for act in actions:
                    item = (
                        (act.get("addChatItemAction") or {}).get("item")
                        or {}
                    )
                    live = item.get("liveChatTextMessageRenderer") or item.get(
                        "liveChatPaidMessageRenderer"
                    ) or {}
                    runs = ((live.get("message") or {}).get("runs")) or []
                    text = "".join(r.get("text") or "" for r in runs)
                    author = ((live.get("authorName") or {}).get("simpleText")) or author
                    ts = live.get("timestampText", {}).get("simpleText") or ts
            if text:
                lines.append(f"[{ts}] {author}: {text}")
                count += 1
        except Exception:
            continue
    if lines:
        txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return count


def harvest_ytdlp_live_chat_files(out_dir: str, log: Callable = print) -> List[str]:
    """扫描下载目录，把 live_chat 转成 .chat.txt / .ass / .srt（播放器可读）"""
    root = Path(out_dir)
    if not root.is_dir():
        return []
    out = []
    for p in root.iterdir():
        if not p.is_file():
            continue
        name = p.name.lower()
        if "live_chat" not in name:
            continue
        if p.suffix.lower() not in (".json", ".json3", ".vtt", ".srv3", ".ttml"):
            continue
        txt = p.with_name(p.stem + ".chat.txt")
        msgs: List[dict] = []
        if p.suffix.lower() in (".json", ".json3"):
            n = convert_youtube_live_chat_json_to_txt(p, txt)
            if n:
                log(f"YouTube 聊天已转换: {txt.name} ({n} 条)")
                out.append(str(txt))
                # 再从 txt 粗解析为 msgs 生成 ass
                try:
                    for i, line in enumerate(txt.read_text(encoding="utf-8", errors="ignore").splitlines()):
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        user, text = "", line
                        if "]: " in line:
                            # [ts] user: text
                            try:
                                rest = line.split("]", 1)[1].strip()
                                if ": " in rest:
                                    user, text = rest.split(": ", 1)
                                else:
                                    text = rest
                            except Exception:
                                text = line
                        msgs.append({"user": user, "text": text, "t_sec": float(i) * 0.8})
                except Exception:
                    pass
        else:
            try:
                content = p.read_text(encoding="utf-8", errors="ignore")
                txt.write_text(content, encoding="utf-8")
                out.append(str(txt))
                # vtt 可能已可播放，再复制一份 ass 文件名便于寻找
                for i, line in enumerate(content.splitlines()):
                    line = line.strip()
                    if not line or line.startswith("WEBVTT") or "-->" in line or line.isdigit():
                        continue
                    msgs.append({"user": "", "text": line, "t_sec": float(i) * 0.5})
            except Exception:
                pass
        if msgs:
            paths = write_chat_subtitle_files(txt, msgs, title=p.stem)
            out.extend(paths)
    return out


# 直播聊天抓取线程：task_id -> stop_event
_live_chat_stop: Dict[str, threading.Event] = {}


def start_live_chat_capture(task_id: str, url: str, out_dir: str, log: Callable = print) -> str:
    """
    多平台直播聊天/弹幕抓取：
    - B站：历史弹幕 API 轮询
    - Twitch：IRC 聊天
    - YouTube：依赖 yt-dlp 写 live_chat 字幕 + 结束时转换；同时尝试轻量轮询
    - 其它：尽量用 yt-dlp live_chat 字幕（在下载选项里开启）
    """
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    low = (url or "").lower()
    stop_ev = threading.Event()
    _live_chat_stop[task_id] = stop_ev
    plat = detect_platform(url)
    stamp = task_id[:8]

    # ---- B站 ----
    room_id = extract_bilibili_live_room_id(url)
    if room_id:
        chat_path = Path(out_dir) / f"live_bilibili_{room_id}_{stamp}.chat.txt"
        seen = set()
        collected: List[dict] = []
        t0 = time.time()

        def loop_bili():
            proxy = resolve_proxy(source="bilibili")
            log(f"[{stamp}] 抓取 B站直播弹幕 room={room_id}")
            try:
                with chat_path.open("a", encoding="utf-8") as f:
                    f.write(f"# bilibili live chat room={room_id} start={datetime.now().isoformat()}\n")
                    while not stop_ev.is_set():
                        try:
                            for m in fetch_bilibili_live_chat_history(room_id, proxy):
                                key = f"{m.get('time')}|{m.get('user')}|{m.get('text')}"
                                if key in seen or not (m.get("text") or "").strip():
                                    continue
                                seen.add(key)
                                item = {
                                    "time": m.get("time") or "",
                                    "user": m.get("user") or "",
                                    "text": m.get("text") or "",
                                    "t_sec": max(0.0, time.time() - t0),
                                }
                                collected.append(item)
                                f.write(f"[{item['time']}] {item['user']}: {item['text']}\n")
                                f.flush()
                                # 每 15 条刷新一次播放器可读字幕，避免结束时丢失
                                if len(collected) % 15 == 0:
                                    write_chat_subtitle_files(
                                        chat_path, collected, title=f"bilibili-{room_id}"
                                    )
                        except Exception:
                            pass
                        stop_ev.wait(3.0)
                    f.write(f"# end={datetime.now().isoformat()} count≈{len(seen)}\n")
                # 播放器可读 ASS/SRT（最终完整版）
                paths = write_chat_subtitle_files(
                    chat_path, collected, title=f"bilibili-{room_id}"
                )
                if paths:
                    log(f"[{stamp}] 弹幕字幕已保存: {', '.join(Path(p).name for p in paths)}")
                elif collected:
                    log(f"[{stamp}] 已抓取 {len(collected)} 条弹幕 → {chat_path.name}")
                else:
                    log(f"[{stamp}] 本场未抓到弹幕（接口可能为空，请确认 Cookie/房间）", "warning")
            finally:
                _live_chat_stop.pop(task_id, None)
                log(f"[{stamp}] B站聊天已保存: {chat_path.name}")

        threading.Thread(target=loop_bili, daemon=True).start()
        return str(chat_path)

    # ---- Twitch IRC ----
    tw_ch = extract_twitch_channel(url)
    if tw_ch and "twitch.tv" in low:
        chat_path = Path(out_dir) / f"live_twitch_{tw_ch}_{stamp}.chat.txt"
        collected: List[dict] = []
        t0 = time.time()

        def loop_twitch():
            log(f"[{stamp}] 抓取 Twitch 聊天 channel={tw_ch}")
            import socket
            try:
                with chat_path.open("a", encoding="utf-8") as f:
                    f.write(f"# twitch chat #{tw_ch} start={datetime.now().isoformat()}\n")
                    while not stop_ev.is_set():
                        sock = None
                        try:
                            sock = socket.create_connection(("irc.chat.twitch.tv", 6667), timeout=15)
                            sock.settimeout(10)
                            nick = "justinfan%d" % (10000 + (hash(task_id) % 50000))
                            sock.sendall(f"PASS SCHMOOPIIE\r\nNICK {nick}\r\n".encode())
                            sock.sendall(f"JOIN #{tw_ch.lower()}\r\n".encode())
                            buf = b""
                            while not stop_ev.is_set():
                                try:
                                    chunk = sock.recv(4096)
                                    if not chunk:
                                        break
                                    buf += chunk
                                    while b"\r\n" in buf:
                                        line, buf = buf.split(b"\r\n", 1)
                                        text = line.decode("utf-8", errors="ignore")
                                        if text.startswith("PING"):
                                            sock.sendall(text.replace("PING", "PONG").encode() + b"\r\n")
                                            continue
                                        if "PRIVMSG" in text:
                                            try:
                                                user = text.split("!", 1)[0].lstrip(":")
                                                msg = text.split("PRIVMSG", 1)[1].split(":", 1)[1]
                                                ts = datetime.now().strftime("%H:%M:%S")
                                                item = {
                                                    "time": ts,
                                                    "user": user,
                                                    "text": msg,
                                                    "t_sec": max(0.0, time.time() - t0),
                                                }
                                                collected.append(item)
                                                f.write(f"[{ts}] {user}: {msg}\n")
                                                f.flush()
                                            except Exception:
                                                pass
                                except socket.timeout:
                                    continue
                                except Exception:
                                    break
                        except Exception as e:
                            log(f"[{stamp}] Twitch IRC 重连: {e}", "warning")
                            stop_ev.wait(5.0)
                        finally:
                            if sock:
                                try:
                                    sock.close()
                                except Exception:
                                    pass
                    f.write(f"# end={datetime.now().isoformat()}\n")
                paths = write_chat_subtitle_files(
                    chat_path, collected, title=f"twitch-{tw_ch}"
                )
                if paths:
                    log(f"[{stamp}] Twitch 字幕已保存: {', '.join(Path(p).name for p in paths)}")
            finally:
                _live_chat_stop.pop(task_id, None)
                log(f"[{stamp}] Twitch 聊天已保存: {chat_path.name}")

        threading.Thread(target=loop_twitch, daemon=True).start()
        return str(chat_path)

    # ---- YouTube / 其它：旁路用 yt-dlp 拉 live_chat，并结束时转换目录内字幕 ----
    chat_path = Path(out_dir) / f"live_{plat}_{stamp}.chat.txt"
    yt_id = extract_youtube_video_id(url)

    def loop_ytdlp_chat():
        log(f"[{stamp}] 启用通用直播聊天抓取 platform={plat}")
        try:
            with chat_path.open("a", encoding="utf-8") as f:
                f.write(
                    f"# live chat platform={plat} url={url} start={datetime.now().isoformat()}\n"
                    f"# YouTube 等平台主要依赖 yt-dlp 的 live_chat 字幕，结束录制后自动转换\n"
                )
            # 周期性尝试只拉 live_chat（不下载视频）
            while not stop_ev.is_set():
                try:
                    if yt_id or plat in ("youtube", "default"):
                        import yt_dlp
                        yopts = {
                            "skip_download": True,
                            "writesubtitles": True,
                            "writeautomaticsub": False,
                            "subtitleslangs": ["live_chat"],
                            "subtitlesformat": "json3/json/vtt/best",
                            "outtmpl": str(Path(out_dir) / f"%(title).60B [{stamp}].%(ext)s"),
                            "quiet": True,
                            "no_warnings": True,
                            "ignoreerrors": True,
                        }
                        # 带 cookie
                        try:
                            pc = (cfg.data.get("platform_cookies") or {}).get("youtube") or {}
                            cf = (pc.get("file") or "").strip()
                            if cf and Path(cf).exists():
                                yopts["cookiefile"] = cf
                            elif (cfg.data.get("cookie_source") or "") == "file":
                                cf = (cfg.data.get("cookie_file") or "").strip()
                                # 默认值指向 cookies/cookies.txt，全新环境里它可能不存在
                                if cf and Path(cf).exists():
                                    yopts["cookiefile"] = cf
                        except Exception:
                            pass
                        po = task_proxy_override(cfg.data) or ydl_proxy_opt(url)
                        if po is not None:
                            yopts["proxy"] = po
                        with yt_dlp.YoutubeDL(yopts) as ydl:
                            ydl.download([url])
                        harvest_ytdlp_live_chat_files(out_dir, log=log)
                except Exception as e:
                    log(f"[{stamp}] live_chat 拉取: {e}", "info")
                # YouTube live_chat 文件会持续更新；不要太频繁
                stop_ev.wait(45.0)
            harvest_ytdlp_live_chat_files(out_dir, log=log)
            try:
                with chat_path.open("a", encoding="utf-8") as f:
                    f.write(f"# end={datetime.now().isoformat()}\n")
            except Exception:
                pass
        finally:
            _live_chat_stop.pop(task_id, None)
            log(f"[{stamp}] 通用聊天抓取结束: {chat_path.name}")

    threading.Thread(target=loop_ytdlp_chat, daemon=True).start()
    return str(chat_path)


def stop_live_chat_capture(task_id: str):
    ev = _live_chat_stop.get(task_id)
    if ev:
        ev.set()


# -------------------- NAS / WebDAV 存储转存 --------------------
def _webdav_join(base: str, *parts: str) -> str:
    base = (base or "").rstrip("/") + "/"
    for p in parts:
        p = (p or "").strip("/")
        if p:
            base = base.rstrip("/") + "/" + p
    return base


def webdav_upload_file(
    local_path: str,
    remote_url: str,
    user: str = "",
    password: str = "",
    remote_dir: str = "/",
    log: Callable = print,
) -> str:
    """上传文件到 WebDAV（群晖 / 威联通 / Nextcloud / Alist 等）"""
    lp = Path(local_path)
    if not lp.is_file():
        raise FileNotFoundError(local_path)
    base = (remote_url or "").strip()
    if not base:
        raise ValueError("WebDAV URL 为空")
    if not base.endswith("/"):
        base += "/"
    dest_dir = (remote_dir or "/").strip() or "/"
    # 确保目录存在（MKCOL 逐级）
    auth = (user, password) if user else None
    segments = [s for s in dest_dir.strip("/").split("/") if s]
    cur = base
    for seg in segments:
        cur = cur.rstrip("/") + "/" + seg
        try:
            requests.request("MKCOL", cur, auth=auth, timeout=30)
        except Exception:
            pass
    dest = cur.rstrip("/") + "/" + lp.name
    with lp.open("rb") as f:
        r = requests.put(dest, data=f, auth=auth, timeout=600)
    if r.status_code not in (200, 201, 204):
        raise RuntimeError(f"WebDAV 上传失败 HTTP {r.status_code}: {r.text[:200]}")
    log(f"WebDAV 已上传: {lp.name} → {dest}")
    return dest


def transfer_to_storage(local_path: str, cfg_data: dict, log: Callable = print) -> dict:
    """
    下载完成后转存：
    - NAS 路径：复制/移动到本地挂载或 UNC 路径
    - WebDAV：上传到网盘/NAS WebDAV
    """
    result = {"nas": "", "webdav": "", "action": cfg_data.get("storage_post_action") or "none"}
    action = (cfg_data.get("storage_post_action") or "none").lower()
    if action not in ("copy", "move"):
        action = "copy" if (
            cfg_data.get("storage_nas_enabled") or cfg_data.get("storage_webdav_enabled")
        ) else "none"
    if action == "none":
        return result
    lp = Path(local_path)
    if not lp.is_file():
        return result

    # NAS / 网络路径
    if cfg_data.get("storage_nas_enabled"):
        nas = (cfg_data.get("storage_nas_path") or "").strip()
        if nas:
            try:
                dest_dir = Path(nas)
                dest_dir.mkdir(parents=True, exist_ok=True)
                dest = dest_dir / lp.name
                import shutil
                if action == "move":
                    shutil.move(str(lp), str(dest))
                else:
                    shutil.copy2(str(lp), str(dest))
                result["nas"] = str(dest)
                log(f"已转存 NAS: {dest}")
            except Exception as e:
                log(f"NAS 转存失败: {e}", "warning")

    # WebDAV
    if cfg_data.get("storage_webdav_enabled"):
        try:
            dest = webdav_upload_file(
                str(lp),
                remote_url=cfg_data.get("storage_webdav_url") or "",
                user=cfg_data.get("storage_webdav_user") or "",
                password=cfg_data.get("storage_webdav_pass") or "",
                remote_dir=cfg_data.get("storage_webdav_path") or "/",
                log=log,
            )
            result["webdav"] = dest
            # 仅 WebDAV 且 move：上传成功后删本地（未做 NAS move 时）
            if action == "move" and not result.get("nas"):
                try:
                    lp.unlink(missing_ok=True)
                except Exception:
                    pass
        except Exception as e:
            log(f"WebDAV 转存失败: {e}", "warning")
    return result


def _local_ytdlp_ok() -> bool:
    """tools/yt_dlp 是否完整可用（必须有 youtube 提取器）"""
    if not YTDLP_LOCAL_PKG.is_dir() or not (YTDLP_LOCAL_PKG / "__init__.py").exists():
        return False
    # 关键标志：youtube 提取器文件存在
    yt_ie = YTDLP_LOCAL_PKG / "extractor" / "youtube.py"
    yt_ie2 = YTDLP_LOCAL_PKG / "extractor" / "youtube" / "__init__.py"
    if not yt_ie.exists() and not yt_ie2.exists():
        return False
    return True


def _prefer_local_ytdlp(force_clear: bool = False):
    for k in list(sys.modules):
        if k == "yt_dlp" or k.startswith("yt_dlp."):
            del sys.modules[k]
    if force_clear:
        return
    if _local_ytdlp_ok():
        p = str(TOOLS_DIR)
        if p not in sys.path:
            sys.path.insert(0, p)


_prefer_local_ytdlp()


# -------------------- 模型 --------------------
class TaskStatus(str, Enum):
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    FINISHED = "finished"
    FAILED = "failed"
    STOPPED = "stopped"
    PAUSED = "paused"
    LATER = "later"  # 稍后下载：不自动进入 pending，需手动启动


@dataclass
class DownloadTask:
    id: str
    url: str
    title: str = "等待中..."
    status: str = TaskStatus.QUEUED.value
    progress: float = 0.0
    speed: str = ""
    eta: str = ""
    error_msg: str = ""
    filepath: str = ""
    res_label: str = ""         # 卡片上的清晰度/格式标签，下载中由进度回调填入
    thumbnail: str = ""         # 封面图 URL，同上
    total_bytes: int = 0        # 本次任务总字节，进度回调填入
    done_bytes: int = 0         # 已下载字节
    is_live: bool = False
    started_at: str = ""
    chat_file: str = ""
    pinned: bool = False  # 置顶
    priority: int = 0     # 越大越靠前；置顶时自动抬高
    created_at: str = ""  # 入队时间，用于排序
    queue_name: str = "default"  # 命名队列：default / night / subscribe ...
    retry_count: int = 0       # 已重试次数
    max_retries: int = 3       # 最大重试
    resume_hint: str = ""      # 断点提示：续传 / 新任务 / 有.part
    kind: str = "link"            # link=常规链接；torrent=磁力/种子文件（走 aria2）
    files: List[dict] = field(default_factory=list)  # 种子内文件清单，拿到元数据后填
    result_dir: str = ""          # 种子落盘目录（多个文件时用它兜底）
    category: str = ""            # 自动分类命中的规则名，空=没走规则
    gid: str = ""                 # aria2 的下载 id：停种、改选文件都要它
    seeding: bool = False         # 下完后是否还在做种
    uploaded: int = 0             # 已上传字节
    share_ratio: float = 0.0      # 上传 / 下载比率
    seed_seconds: int = 0         # 已做种秒数
    verify_note: str = ""         # 成品回读：实得高度与所选档位对不上时的一句说明，空=没偏差
    expect_hash: str = ""         # 入队时给的期望摘要（小写 hex），空=没让核对校验值
    hash_algo: str = ""           # md5 / sha1 / sha256 / sha512，跟期望值一起定下来
    file_hash: str = ""           # 下完对成品实算的摘要，核对过才有值
    hash_state: str = ""          # 核对结论："" 没核对 / ok 一致 / bad 对不上 / unknown 判不出

    def to_dict(self):
        d = asdict(self)
        elapsed = 0
        if self.started_at:
            try:
                t0 = datetime.fromisoformat(self.started_at)
                elapsed = max(0, int((datetime.now() - t0).total_seconds()))
            except Exception:
                elapsed = 0
        d["elapsed_sec"] = elapsed
        # 仅进行中任务且线程仍在跑才显示「聊天记录中」
        capturing = False
        try:
            if self.status in (
                TaskStatus.DOWNLOADING.value,
                TaskStatus.QUEUED.value,
                TaskStatus.PAUSED.value,
            ):
                capturing = self.id in _live_chat_stop
        except Exception:
            capturing = False
        d["chat_capturing"] = capturing
        if self.is_live:
            # 界面上的「录满 X 分钟自动保存」要用：任务自己带了时长就按它，否则跟随全局默认
            try:
                d["live_limit_min"] = _live_effective_minutes(
                    (getattr(self, "_opts", {}) or {}).get("live_max_minutes"),
                    cfg.data.get("live_max_minutes"),
                )
            except Exception:
                d["live_limit_min"] = 0
        return d


class ConfigManager:
    DEFAULTS = {
        "download_dir": str(DEFAULT_DOWNLOAD_DIR),
        "video_quality": "best",
        "audio_quality": "best",
        "format": "mkv",
        # 转码 / 烧字幕时用什么编码器。默认就是以前那一种：CPU 的 libx264。
        "video_encoder": "cpu",  # auto / cpu / nvidia / intel / amd
        "video_cpu_codec": "x264",  # x264 / x265（硬件起不来时兜底用这个）
        "video_cpu_preset": "medium",  # veryfast / fast / medium / slow
        "embed_sub": True,
        "audio_only": False,
        "proxy": "",
        "proxy_mode": "auto",  # auto=按平台判断 always=全部走代理 none=交回系统
        "proxy_by_platform": {},  # {平台键: true 走代理 / false 强制直连}，仅 auto 时生效
        "cookie_source": "file",
        "cookie_browser": "chrome",
        # 默认使用项目内 cookies/cookies.txt
        "cookie_file": str(DEFAULT_COOKIE_FILE),
        # 公开优先：默认关 —— 关着时解析与下载都照旧无条件带上 Cookie，行为一字不变。
        # 开着时先按不带 Cookie 解析一次，只有那一次被登录墙/会员/年龄/风控页挡住（或只给到
        # 被裁的清单）才带 Cookie 再解析；429 与网络错不重跑。判过的结论按 URL 记一阵子。
        "cookie_public_first": False,
        # CookieCloud：浏览器插件把 Cookie 推到自己架的服务器上，这边再拉成本地 cookies/*.txt。
        # 默认关 —— 开着也不会自己动，要点「从云端拉取」才发请求。服务器/UUID/密钥只在
        # /api/cookiecloud/account 这一条路上读写（密钥不回显、不进日志），不跟着整包设置走。
        "cookiecloud_enabled": False,
        "cookiecloud_server": "",
        "cookiecloud_uuid": "",
        "cookiecloud_key": "",
        "cookiecloud_scheme": "auto",   # auto / legacy / aes-128-cbc-fixed
        "cookiecloud_domains": "",      # 换行分隔的域名过滤，空 = 云端给什么就收什么
        # 按龄清理。默认关，而且**开着开关也只自动清程序自己造的垃圾**（日志归档与 .bak 备份）；
        # 下载目录那一档永远只在用户看过名单、点过「按名单删除」之后才动，动的也不是删除 ——
        # 是先挪进 Downloads/_cleanup_trash/ 待一段时间，超过回收保留天数才真删。
        # 天数填 0 就是这一档不碰。日志归档那条本来就有（启动时按 7 天删一次），
        # 这一轮把它变成可配，并且让长跑几天的进程每天也真跑一次，而不是只有重启时才清。
        "cleanup_enabled": False,
        "cleanup_log_days": 7,
        "cleanup_backup_days": 0,
        "cleanup_download_days": 0,
        "cleanup_trash_days": 30,
        "concurrent": 3,
        "sponsorblock": "off",
        "filename_template": "%(title).60B [%(id)s].%(ext)s",
        "embed_thumb": True,
        "embed_meta": True,
        "embed_chapters": True,
        "local_ai_transcribe": False,
        "local_ai_translate": False,
        "local_ai_lang": "auto",
        # 本地语音识别（faster-whisper）
        "whisper_model": "base",  # tiny|base|small|medium|large-v3
        "whisper_device": "auto",  # auto|cuda|cpu
        "whisper_compute": "auto",  # auto|float16|int8|int8_float16
        # 说话人分离：给转写字幕按声纹贴 [说话人N]，纯 numpy 轻量版，默认关
        "diarization_enabled": False,
        "diarization_max_speakers": 4,  # 2-8，最多分几个人
        "hf_token": "",  # HuggingFace Token，可选，加速/提高模型下载限额
        # 语音工具那两项以前只写在读取处的兜底里，默认值表没登记：界面上有这两项，
        # 「恢复默认」的名单里就没有它们。默认值和代码里那份兜底保持一致。
        "demucs_model": "htdemucs",
        # #78 人声分离：引擎 / RoFormer 权重 / 设备三档。默认走新装的 RoFormer，
        # 设备默认 auto —— 默认值不能替用户挑 GPU：装了别的程序占着显存时，
        # auto 会自己回到 CPU，写死 cuda 就变成「一按分离就报错」。
        "vocal_engine": "roformer",
        "roformer_model": "bs_1297",
        "ai_device": "auto",
        "vocal_native_fp16": False,
        "edge_tts_voice": "",  # 空 = 按字幕目标语言挑预设音色（voice_tools.EDGE_VOICE_PRESETS）
        # 字幕机翻（DeepL / OpenAI）
        "subtitle_translate_provider": "deepl",  # deepl|openai|claude|gemini|google|azure|none
        "subtitle_target_lang": "zh",
        "translate_auto_fallback": True,  # 主力翻译源失败时自动换备份源（读取处那份兜底同值）
        "subtitle_glossary": "",  # 术语表：一行一条「原文 -> 译文」，# 开头为注释
        "subtitle_wrap": True,  # 成品字幕按显示宽度加权换行（中 1 / 英 0.5）
        "subtitle_wrap_width": 16,  # 每行最多多少个全角宽
        "subtitle_wrap_lines": 3,  # 每条字幕最多几行
        "subtitle_qc": True,  # 机翻后对照质检，可疑句写进运行日志
        "subtitle_qc_reflect": False,  # 可疑句再交对话模型改一遍（要花 token）
        "subtitle_export_set": "single",  # single|bilingual|all 单语 / +双语SRT / +VTT+ASS
        "deepl_api_key": "",
        "deepl_api_url": "",  # 空则按 key 自动 free/pro
        "openai_api_key": "",
        "openai_base_url": "https://api.openai.com/v1",
        "openai_model": "gpt-4o-mini",
        "anthropic_api_key": "",
        "anthropic_model": "claude-sonnet-4-20250514",
        "gemini_api_key": "",
        "gemini_model": "gemini-2.0-flash",
        "google_translate_api_key": "",
        "azure_translator_key": "",
        "azure_translator_region": "eastasia",
        "azure_translator_endpoint": "https://api.cognitive.microsofttranslator.com",
        "local_ai_mt_after_transcribe": False,  # 转写后自动机翻（非 Whisper translate）
        "subtitle_first": True,   # 优先平台/旁路字幕，Whisper 兜底
        "ai_polish": False,       # LLM 润色转写
        "ai_summarize": False,    # LLM 摘要
        "summary_lang": "zh",
        "skip_downloaded": True,
        "verify_download": True,    # 下载完体检文件：网页伪装/空壳/截断
        "allow_playlist": False,
        # 合集/播放列表整批下时先在下载目录里建一层同名文件夹（默认关：老目录结构不突变）
        "playlist_subdir": False,
        "playlist_start": 0,
        "playlist_end": 0,
        "playlist_items": "",
        "max_retries": 3,
        # 自定义 yt-dlp 参数：一行命令行式参数，解析与下载都按它走（危险项与冲突项点名后忽略）
        "ytdlp_extra_args": "",
        "musicdl_cookies": "",
        # 各音乐平台自己的登录 Cookie：{平台: {"cookie": "k=v; ...", "via": "扫码登录", "at": "..."}}
        # 只写进本机 config.json，分享包与日志都不带值
        "music_platform_cookies": {},
        "musicdl_sources": [],
        "music_filename_template": "{artist}/{name} - {artist}",
        "music_embed_metadata": True,
        "music_hide_unavailable": True,
        "music_include_local": False,
        "music_playlist_mode": "fast",
        # 搬运版守门：默认关。Spotify/Apple 的音频本来就只能经转链站从 YouTube 取回，
        # 默认开会把整张歌单拦空；它拦的是"取回的元数据对不上歌单标注"那几首。
        "music_block_reupload": False,
        # 无损参照：附带查 Qobuz/Tidal 官方曲库的元数据（ISRC/时长/位深/官方链接）。
        # 每次搜索多问一次外部站，所以默认关；参照行只读，音频一律不从这里下。
        "music_include_reference": False,
        # 音质要求：默认「不限」。musicdl 各源的档位阶梯写死在它自己代码里，钉不住，
        # 所以这一项只用于「多候选挑达标的那条」与「下完核对成品实际档位」，见 music_search.norm_quality_spec
        "music_quality_spec": {"format": "", "min_bit_depth": 0,
                               "min_sample_rate": 0, "min_bitrate": 0, "strict": False},
        "acoustid_api_key": "",
        "acoustid_min_score": 0.5,
        "musicdl_strategy": {
            "mode": "parallel",
            "search_size": 12,
            "max_retries": 3,
            "connect_timeout": 10,
            "read_timeout": 30,
            "threads_per_source": 5,
            "order": "as_is",
            "dedupe": "global",
            "per_source_budget": 180,
        },
        "backoff_base": 30,
        "backoff_max": 600,
        "backoff_jitter": 0.25,
        "speed_limit": "",
        "write_description": False,
        "write_info_json": False,
        "write_sub_files": True,
        "dark_mode": False,
        # 2027 年度色主题：blue / orange / pink / green / clay
        "ui_theme": "blue",
        # 界面语言：auto / zh / en，默认跟随浏览器
        "ui_language": "auto",
        # 留空则优先使用 tools/ 下的 ffmpeg
        "ffmpeg_path": "",
        "retry_on_429": True,
        "subtitle_langs": "all",
        # Telegram
        "telegram_enabled": False,
        "telegram_bot_token": "",
        "telegram_chat_id": "",
        "telegram_notify_done": True,
        "telegram_notify_fail": True,
        "telegram_notify_sub": True,
        "telegram_commands_enabled": True,
        "telegram_offset": 0,
        # Telegram 用户会话（MTProto）：翻私有/需登录频道的历史并下载，与上面的机器人通知无关
        "tgmt_api_id": "",
        "tgmt_api_hash": "",
        "tgmt_session_name": "media_downloader",
        "tgmt_proxy": "",  # 留空=直连；Python 不读注册表代理，被墙时要填 socks5 的 host:port
        "tgmt_skip_seen": True,
        "tgmt_ack": [],  # 已确认过「限制保存内容」的频道 peer 列表
        # 订阅
        "sub_interval_min": 60,
        "sub_auto_download": True,
        # 直播
        "live_from_start": True,
        # 录满这么多分钟自动收尾保存：手动录制与未单独设时长的监控房间采用，0 = 不限时长
        "live_max_minutes": 0,
        # 多平台 Cookie：platform -> {source, file, browser, status}
        "platform_cookies": {},
        # 风控
        "risk_delay_sec": 1.0,
        "risk_max_per_host": 2,
        "risk_cooldown_429": 60,
        "risk_user_agent": "",
        "risk_preset": "standard",  # fast | standard | safe | extreme
        "concurrent_fragments": 4,
        "fragment_min_size_mb": 20,
        "risk_api_rate": 4,
        "sub_scan_delay_sec": 10,
        # 命名队列与同域并发
        "named_queues": ["default", "night", "subscribe", "sniff"],
        "max_per_host": 2,
        "adaptive_throttle": True,  # 命中 429 后自动把该站点并发降到 1 并冷却
        "global_speed_limit": "",  # 全局限速，如 2M；空=不限
        "speed_windows": "",  # 限速时段，一行一条：00:00-08:00 -> 2M
        "run_window": "",  # 队列定时窗（全局），一行一条：22:00-06:00；空=什么时候都能开新任务
        "queue_windows": {},  # 每条命名队列各自的窗 {队列名: "22:00-06:00"}，没填的只看全局
        # 解析插件
        "plugins_enabled": True,
        # aria2 可选后端
        "aria2_enabled": False,
        "aria2_rpc": "http://127.0.0.1:6800/jsonrpc",
        "aria2_secret": "",
        "aria2_split": 8,
        "aria2_for_large_mb": 50,  # 直链超过该 MB 自动尝试 aria2（即使未全局开启）
        "aria2_bin": "",  # aria2c 的路径，空=自己找（tools/ → PATH → 环境变量）
        "aria2_autostart": True,  # RPC 没人应答时，由程序拉起一个只监听 127.0.0.1 的 aria2c
        # 磁力/种子：下载完转做种，传到比率或做满时长就停（两个都设 0 = 一直做种，只能手动停）
        "torrent_seed_ratio": 1.0,
        "torrent_seed_time": 3600,
        "torrent_meta_timeout": 180,  # 等种子元数据的上限，超了就说明这会儿没人在做种
        # 磁力/种子加料（参照 qBittorrent-Enhanced-Edition）：tracker 只存来源地址，正文运行时抓、只落本机
        "bt_trackers": "",           # 自己加的 announce 地址，一行一个，排在抓来的前面
        "bt_tracker_sources": "\n".join(s["url"] for s in bt_trackers.DEFAULT_SOURCES),
        "bt_tracker_auto_update": True,
        "bt_tracker_max": 30,        # 一次注入多少条：announce 是串行问的，堆太多首轮会很慢
        "bt_dl_limit": "",           # 每个种子任务的下载限速，aria2 认 1M / 512K，空=不限
        "bt_ul_limit": "",           # 每个种子任务的上传限速（做种也吃这条）
        "bt_prioritize_piece": False,  # 先下每个文件的首尾各 1M，边下边预览用得上
        # 自动分类（参照 qBittorrent 的分类/自动追加）：按种子里的名字或按链接决定存到下载目录下的哪个子目录
        "bt_auto_rules": [],         # [{name, scope: name|url, mode: contains|regex, pattern, subdir, enabled}]，从上往下第一条命中生效
        "bt_auto_fallback": "",      # 一条规则都没命中时存到这里（空=就用默认下载目录）
        "clipboard_watch": False,    # 剪贴板监听：默认关，发现了也只是问一句，绝不自动入队
        "http_impersonate": True,  # 用 curl_cffi 模拟浏览器 TLS，降低 403
        "po_provider_enabled": False,  # 有 bgutil PO Token 服务时才试需要票的播放器客户端
        "po_provider_url": "http://127.0.0.1:4416",
        "yt_player_clients": "default,web_safari,tv,android,ios",  # 从左到右回退，被拒时换下一个
        "github_mirror": "https://ghproxy.net/",  # GitHub/HF 下载镜像前缀，空=直连
        "pip_mirror": "https://pypi.tuna.tsinghua.edu.cn/simple",  # 程序内 pip 更新依赖的镜像源，空=官方
        "components_auto_check": True,  # 打开程序时自动查一遍上游最新版，有得更新就在侧栏「设置」标橙点并弹窗
        # 订阅首次可下最近 N 条（0=只记 ID）
        "sub_first_download_n": 0,

        "serverchan_sendkey": "",
        # 企业微信
        "wecom_enabled": False,
        "wecom_corp_id": "",
        "wecom_corp_secret": "",
        "wecom_agent_id": "",
        "wecom_touser": "@all",
        "wecom_notify_done": True,
        "wecom_notify_fail": True,
        "wecom_notify_sub": False,
        # NAS / 网盘存储
        "storage_post_action": "none",  # none | copy | move
        "storage_nas_enabled": False,
        "storage_nas_path": "",  # 如 \\\\NAS\\media 或 /mnt/nas/downloads 或 Z:/Videos
        "storage_webdav_enabled": False,
        "storage_webdav_url": "",  # https://nas.example.com/webdav/ or alist
        "storage_webdav_user": "",
        "storage_webdav_pass": "",
        "storage_webdav_path": "/",  # 远端子目录
        # SSL：抖音等 CDN 证书域名不匹配时需关闭校验
        "nocheckcertificate": True,
        # 直播流偏好：auto | hls | flv | dash
        "live_stream_pref_bilibili": "flv",
        "live_stream_pref_youtube": "dash",
        "live_stream_pref_douyin": "hls",
        "live_stream_pref_twitch": "hls",
        "live_stream_pref_default": "auto",
        "live_stream_fallback": True,
        # 访问保护（登录）：默认关，开着才对「非本机来的连接」生效，127.0.0.1 一律不受影响
        "web_auth_enabled": False,
        "web_auth_session_hours": 12,   # 空闲多久要重登
        "web_auth_remember_days": 30,   # 勾了「记住这台设备」后的最长有效天数
        "web_auth_max_fails": 5,        # 连错几次锁
        "web_auth_lock_minutes": 15,    # 锁多久
        # 下面三条是只写不读的：口令只存加盐哈希，SECRET_KEY 与机器令牌由程序生成
        "secret_key": "",
        "web_auth_password_hash": "",
        "web_auth_machine_token": "",
    }

    def __init__(self):
        self.data = dict(self.DEFAULTS)
        self.load()

    def load(self):
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    self.data.update(json.load(f))
            except Exception:
                pass

    def save(self):
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass


# 平台识别与默认 cookie 文件名
PLATFORM_RULES = [
    ("youtube", ("youtube.com", "youtu.be", "youtube-nocookie.com")),
    ("telegram", ("t.me/", "telegram.me/", "telegram.org", "telesco.pe")),
    ("bilibili", ("bilibili.com", "b23.tv", "bilivideo.com")),
    ("douyin", ("douyin.com", "iesdouyin.com", "tiktok.com")),
    ("xiaohongshu", ("xiaohongshu.com", "xhslink.com")),
    ("instagram", ("instagram.com",)),
    ("twitter", ("twitter.com", "x.com")),
    ("pinterest", ("pinterest.com", "pin.it")),
    ("weixin", ("channels.weixin.qq.com", "weixin.qq.com")),
    ("xinpianchang", ("xinpianchang.com",)),
    # 下面这几条是 10-13 补的：facebook / twitch / reddit 早就写在 PROXY_NEEDED_PLATFORMS 里，
    # 但这张表没有对应键，detect_platform 永远返回 default，那几个集合项等于死代码 ——
    # 用户在「网络策略」里也看不到这几行，没法单独指定走/不走代理。
    ("facebook", ("facebook.com", "fb.watch", "fb.com")),
    ("twitch", ("twitch.tv",)),
    ("reddit", ("reddit.com", "redd.it")),
    ("vimeo", ("vimeo.com",)),
    ("soundcloud", ("soundcloud.com",)),
    ("linkedin", ("linkedin.com",)),
    ("weibo", ("weibo.com", "weibo.cn")),
    ("acfun", ("acfun.cn",)),
]
PLATFORM_LABELS = {
    "youtube": "YouTube",
    "telegram": "Telegram",
    "bilibili": "B站",
    "douyin": "抖音/TikTok",
    "xiaohongshu": "小红书",
    "instagram": "Instagram",
    "twitter": "Twitter/X",
    "pinterest": "Pinterest",
    "weixin": "微信视频号",
    "xinpianchang": "新片场",
    "facebook": "Facebook",
    "twitch": "Twitch",
    "reddit": "Reddit",
    "vimeo": "Vimeo",
    "soundcloud": "SoundCloud",
    "linkedin": "LinkedIn",
    "weibo": "微博",
    "acfun": "AcFun",
    "default": "默认/其它",
}


def detect_platform(url: str) -> str:
    low = (url or "").lower()
    for name, domains in PLATFORM_RULES:
        if any(d in low for d in domains):
            return name
    return "default"


def platform_cookie_path(platform: str) -> Path:
    return COOKIES_DIR / f"{platform}_cookies.txt"


# --------------------------------------------------------------- 代理策略
# 本机常年挂着注册表代理（127.0.0.1:789x），requests / urllib / yt-dlp 会自动走它。
# 老做法"填了代理就全都走代理"会让 B 站、网易云这些国内站点也跟着绕一圈：代理节点一抖，
# 整批任务一起挂；反过来强制直连又会杀掉 YouTube 这类必须出国的站。
# 所以按平台判三档：proxy=走代理（没填就取系统代理）、direct=强制直连、
# inherit=不干预（跟随系统，认不出归属的站用它，免得把能下的东西判死）。
PROXY_MODES = ("auto", "always", "none")
UI_THEMES = ("blue", "orange", "pink", "green", "clay")
# 界面语言只有前端认得：后端话术（报错正文、运行日志、订阅规则摘要）始终是中文，
# 这一项存的只是「界面按哪份词表渲染」，auto = 由浏览器 navigator.language 决定。
UI_LANGUAGES = ("auto", "zh", "en")
PROXY_DIRECT = "direct"  # 传给只收代理字符串的下游（music_search）的"强制直连"哨兵

# 国内直连通常不通、必须走代理的站点
PROXY_NEEDED_PLATFORMS = {
    "youtube", "instagram", "twitter", "pinterest", "tiktok",
    "facebook", "telegram", "reddit", "twitch",
    # 补的这三条要和上面的新键一起看：键不存在时这个集合里写什么都是空的
    "vimeo", "soundcloud", "linkedin",
}
# 国内能直连、绕代理只会更慢更不稳的站点
PROXY_DIRECT_PLATFORMS = {
    "bilibili", "douyin", "xiaohongshu", "weixin", "xinpianchang",
    "weibo", "acfun",
}
# 音乐源同理：Spotify 之类必须出国，腾讯系/网易云直连更快。Apple 国内可达，算直连档。
PROXY_NEEDED_SOURCES = {
    "SpotifyMusicClient", "SoundCloudMusicClient", "DeezerMusicClient", "QobuzMusicClient",
    "TIDALMusicClient", "JooxMusicClient", "MOOVMusicClient", "StreetVoiceMusicClient",
    "JioSaavnMusicClient", "JamendoMusicClient", "AudiusMusicClient", "FMAMusicClient",
    "CCMixterMusicClient", "SunoMusicClient",
}
PROXY_DIRECT_SOURCES = {
    "NeteaseMusicClient", "QQMusicClient", "KugouMusicClient", "KuwoMusicClient",
    "MiguMusicClient", "QianqianMusicClient", "FiveSingMusicClient", "BodianMusicClient",
    "SodaMusicClient", "AppleMusicClient",
}
# PLATFORM_RULES 把 TikTok 和抖音并成同一个 cookie 键（同属字节），但代理归属相反
PROXY_TIKTOK_HINT = "tiktok"


def system_proxy_detail() -> tuple:
    """(系统代理地址, 来源说明) —— 来源要能说出口，用户才知道该去哪儿改。"""
    import os
    for k in ("https_proxy", "http_proxy"):
        v = (os.environ.get(k) or "").strip()
        if v and v.lower() != "none":
            return v, f"环境变量 {k.upper()}"
    try:
        import urllib.request
        px = urllib.request.getproxies() or {}
        v = str(px.get("https") or px.get("http") or "")
        if v:
            name = {"win32": "Windows 系统代理设置", "darwin": "macOS 网络代理设置"}.get(
                sys.platform, "系统代理设置"
            )
            return v, name
    except Exception:
        pass
    return "", ""


def system_proxy() -> str:
    """注册表 / 环境变量里已生效的 HTTP(S) 代理，没有则 ""。"""
    return system_proxy_detail()[0]


def proxy_platform_key(url: str) -> str:
    """代理归属用的平台键：比 detect_platform 多把 TikTok 拆出来。"""
    low = (url or "").lower()
    if PROXY_TIKTOK_HINT in low:
        return "tiktok"
    return detect_platform(url)


def proxy_needs_override(key: str, cfg_data: dict) -> Optional[bool]:
    """用户在设置里对该平台手动指定的走/不走代理，没指定返回 None。"""
    table = cfg_data.get("proxy_by_platform") or {}
    if isinstance(table, dict):
        return table.get(key) if isinstance(table.get(key), bool) else None
    return None


def _decide_by_key(key: str, d: dict) -> tuple:
    mode = str(d.get("proxy_mode") or "auto")
    if mode == "none":                      # 全部交回系统，本程序不加判断
        return ("inherit", "")
    if mode != "always":
        forced = proxy_needs_override(key, d)
        if forced is False:
            return ("direct", "")
        if forced is not True:
            if key in PROXY_NEEDED_SOURCES or key in PROXY_NEEDED_PLATFORMS:
                pass
            elif key in PROXY_DIRECT_SOURCES or key in PROXY_DIRECT_PLATFORMS:
                return ("direct", "")
            else:
                # 认不出归属：用户手填的代理照用，但不把系统代理硬塞给它
                fp = (d.get("proxy") or "").strip()
                return ("proxy", fp) if fp else ("inherit", "")
    px = (d.get("proxy") or "").strip() or system_proxy()
    if not px:
        return ("inherit", "")              # 该走代理但一个都没有：交给系统
    return ("proxy", px)


def proxy_decision(target: str = "", source: str = "", cfg_data: dict = None) -> tuple:
    """该目标/该源该怎么连：("proxy", 地址) | ("direct", "") | ("inherit", "")。"""
    d = cfg.data if cfg_data is None else cfg_data
    key = (source or "").strip() or proxy_platform_key(target)
    return _decide_by_key(key, d)


def resolve_proxy(target: str = "", source: str = "", cfg_data: dict = None) -> str:
    """下游只吃代理字符串的地方用这个（拿不到"强制直连"这层意思）。"""
    m, px = proxy_decision(target, source, cfg_data)
    return px if m == "proxy" else ""


def music_proxy(target: str = "", source: str = "", cfg_data: dict = None) -> str:
    """给 music_search 用：地址 / PROXY_DIRECT / ""（不干预）。"""
    m, px = proxy_decision(target, source, cfg_data)
    return px if m == "proxy" else (PROXY_DIRECT if m == "direct" else "")


def music_proxy_for_source(src: str) -> str:
    """一个 musicdl 源该走哪个代理（源名可以是 Netease 这种短名）。"""
    name = str(src or "").strip()
    if name and not name.endswith("Client"):
        try:
            from music_search import normalize_source_name
            name = normalize_source_name(name)
        except Exception:
            pass
    return music_proxy(source=name)


def music_proxy_resolver(explicit: str = "") -> Callable[[str], str]:
    """搜索/下载按源问代理；调用方显式给了地址就一律用它。"""
    e = (explicit or "").strip()
    if e:
        return lambda src: e
    return music_proxy_for_source


def requests_proxies(target: str = "", source: str = "",
                     cfg_data: dict = None) -> Optional[dict]:
    """requests 的 proxies 参数；None 表示别传，让它跟随环境。"""
    m, px = proxy_decision(target, source, cfg_data)
    if m == "proxy":
        return {"http": px, "https": px}
    if m == "direct":
        return {"http": None, "https": None}
    return None


def http_proxies(url: str = "", proxy_override: str = "", source: str = "") -> Optional[dict]:
    """显式代理参数（含 PROXY_DIRECT 哨兵）优先，其次按平台策略。"""
    po = (proxy_override or "").strip()
    if po == PROXY_DIRECT:
        return {"http": None, "https": None}
    if po:
        return {"http": po, "https": po}
    return requests_proxies(url, source)


def proxy_arg(url: str = "", proxy_override: str = "", source: str = "") -> str:
    """只吃代理字符串的下游（aria2 --custom-proxy / 插件 / musicdl）用的地址。"""
    po = (proxy_override or "").strip()
    if po:
        return "" if po == PROXY_DIRECT else po
    return resolve_proxy(url, source)


def task_proxy_override(opts: dict) -> str:
    """任务级代理覆写；和全局设置里的代理是同一个值就不算覆写。"""
    tp = ((opts or {}).get("proxy") or "").strip()
    return tp if tp and tp != (cfg.data.get("proxy") or "").strip() else ""


def ydl_proxy_opt(target: str = "", source: str = "", cfg_data: dict = None) -> Optional[str]:
    """yt-dlp 的 opts["proxy"]：None=跟随系统，""=强制直连，其它=走该代理。"""
    m, px = proxy_decision(target, source, cfg_data)
    if m == "proxy":
        return px
    return "" if m == "direct" else None


def apply_proxy_env(env: dict, target: str = "", source: str = "",
                    cfg_data: dict = None, proxy_override: str = "") -> dict:
    """子进程（ffmpeg / aria2）的代理环境：直连档要把继承来的变量清掉才真走得成直连。"""
    po = (proxy_override or "").strip()
    if po == PROXY_DIRECT:
        m, px = "direct", ""
    elif po:
        m, px = "proxy", po
    else:
        m, px = proxy_decision(target, source, cfg_data)
    if m == "direct":
        for k in ("http_proxy", "https_proxy", "all_proxy",
                  "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
            env.pop(k, None)
        env["no_proxy"] = "*"
        env["NO_PROXY"] = "*"
    elif m == "proxy":
        env["http_proxy"] = px
        env["https_proxy"] = px
        env["HTTP_PROXY"] = px
        env["HTTPS_PROXY"] = px
    return env


LOG_KEEP_DAYS = 7


def _prune_old_logs(days: int = None) -> int:
    """删除超过 N 天的按天归档（app-YYYY-MM-DD.log），按修改时间判断。

    days 不传时读清理配置：开着按龄清理就按它填的天数删（填 0 = 这一档不碰，一份都不删），
    没开才退回写死的 LOG_KEEP_DAYS。启动时这一趟因此跟着设置走，而不是只顾默认 7 天。
    """
    if days is None:
        try:
            days = int(cfg.data.get("cleanup_log_days", LOG_KEEP_DAYS)) if cfg.data.get("cleanup_enabled") \
                else LOG_KEEP_DAYS
        except Exception:
            days = LOG_KEEP_DAYS
    if days <= 0:
        return 0
    cutoff = time.time() - days * 86400
    n = 0
    try:
        files = list(APP_DIR.glob("app-*.log"))
    except Exception:
        return 0
    for p in files:
        try:
            if p.stat().st_mtime < cutoff:
                p.unlink()
                n += 1
        except Exception:
            pass
    return n


class LogManager:
    def __init__(self, max_entries: int = 500):
        self.entries: List[dict] = []
        self.max_entries = max_entries
        self._lock = threading.Lock()
        self._seq = 0  # 单调递增，clear() 不回头，SSE 靠它判断有没有新行
        self._day = datetime.now().strftime("%Y-%m-%d")
        try:
            keep = int(cfg.data.get("cleanup_log_days", LOG_KEEP_DAYS)) if cfg.data.get("cleanup_enabled") \
                else LOG_KEEP_DAYS
        except Exception:
            keep = LOG_KEEP_DAYS
        removed = _prune_old_logs(keep)
        if removed:
            self.log(f"已清理 {removed} 个超过 {keep} 天的日志归档", "info")

    def _rollover_locked(self, today: str):
        """跨天时把昨天的 app.log 归档，保证单个文件内最多只有一天的内容（持锁调用）"""
        target = APP_DIR / f"app-{self._day}.log"
        try:
            if LOG_FILE.exists():
                if target.exists():
                    with open(target, "a", encoding="utf-8") as dst, open(LOG_FILE, "r", encoding="utf-8") as src:
                        shutil.copyfileobj(src, dst)
                    LOG_FILE.unlink()
                else:
                    LOG_FILE.rename(target)
        except Exception:
            pass
        self._day = today

    def log(self, message: str, level: str = "info", k: str = "", kv: dict | None = None):
        """message 永远是人读得下去的那句话（中文），落盘、进 SSE、被自检断言的都是它。

        k/kv 是可选的一组「键 + 参数」：英文界面按它现拼一句，没带键的条目和旧条目一律显示 message。
        这样「界面切英文」不会去改动已经落盘的记录，也不改任何一句中文原话。
        """
        with self._lock:
            self._seq += 1
            entry = {
                "seq": self._seq,
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "level": level,
                "message": message,
            }
            if k:
                entry["k"] = k
                entry["kv"] = dict(kv or {})
            self.entries.append(entry)
            if len(self.entries) > self.max_entries:
                self.entries = self.entries[-self.max_entries :]
            today = entry["time"][:10]
            if today != self._day:
                self._rollover_locked(today)
        try:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def get(self, level: str = "", search: str = "") -> List[dict]:
        with self._lock:
            result = list(self.entries)
        if level and level != "all":
            result = [e for e in result if e["level"] == level]
        if search:
            s = search.lower()
            result = [e for e in result if s in e["message"].lower()]
        return result[-200:]

    def clear(self):
        with self._lock:
            self.entries.clear()


class HistoryManager:
    def __init__(self, max_entries: int = 300):
        self.history: List[dict] = []
        self.max_entries = max_entries
        self._lock = threading.Lock()
        self.load()

    def load(self):
        if HISTORY_FILE.exists():
            try:
                with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                    self.history = json.load(f)
            except Exception:
                self.history = []

    def save(self):
        try:
            with self._lock:
                data = self.history[-self.max_entries :]
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def add(self, item: dict):
        with self._lock:
            self.history.insert(0, item)
        self.save()

    def get(self, keyword: str = "") -> List[dict]:
        with self._lock:
            if not keyword:
                return list(self.history[:100])
            kw = keyword.lower()
            return [
                h
                for h in self.history
                if kw in h.get("title", "").lower() or kw in h.get("url", "").lower()
            ][:100]

    def clear(self):
        with self._lock:
            self.history.clear()
        self.save()

    def stats(self) -> dict:
        with self._lock:
            hist = list(self.history)
        total = len(hist)
        success = sum(1 for h in hist if h.get("status") == "finished")
        failed = sum(1 for h in hist if h.get("status") == "failed")
        return {
            "total": total,
            "success": success,
            "failed": failed,
            "success_rate": f"{success / total * 100:.1f}%" if total else "0%",
        }


# -------------------- FFmpeg --------------------
class FFmpegManager:
    def __init__(self, log: Callable = None):
        # k/kv 是「这句在词表里叫什么」，落盘的永远是那句中文；直连 print 的那份收下但不参与翻译
        self.log = log or (lambda m, level="info", k="", kv=None: print(m))
        self.manual_path = ""
        self.local_bin = TOOLS_DIR / ("ffmpeg.exe" if sys.platform == "win32" else "ffmpeg")

    def find(self, manual: str = "") -> Optional[str]:
        # 1) 用户手动指定
        if manual and Path(manual).exists():
            return str(Path(manual).resolve())
        # 2) 项目 tools/ 目录（优先）
        if self.local_bin.exists():
            return str(self.local_bin.resolve())
        try:
            name = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
            for p in TOOLS_DIR.rglob(name):
                if p.is_file():
                    return str(p.resolve())
        except Exception:
            pass
        # 3) 系统 PATH
        return shutil.which("ffmpeg")

    def version(self) -> str:
        path = self.find(self.manual_path)
        if not path:
            return "未找到"
        try:
            kwargs: dict = {
                "args": [path, "-version"],
                "capture_output": True,
                "timeout": 12,
            }
            if sys.platform == "win32":
                kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                kwargs["encoding"] = "utf-8"
                kwargs["errors"] = "replace"
            else:
                kwargs["text"] = True
            r = subprocess.run(**kwargs)
            out, err = r.stdout or "", r.stderr or ""
            if isinstance(out, bytes):
                out = out.decode("utf-8", errors="replace")
            if isinstance(err, bytes):
                err = err.decode("utf-8", errors="replace")
            text = f"{out}\n{err}"
            m = re.search(r"ffmpeg version\s+([^\s]+)", text, re.I)
            if m:
                return m.group(1)
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue
                m2 = re.search(r"version\s+([^\s]+)", line, re.I)
                if m2:
                    return m2.group(1)
                return line[:48]
            return f"无法解析 (code={r.returncode})"
        except FileNotFoundError:
            return "文件无效"
        except subprocess.TimeoutExpired:
            return "检测超时"
        except Exception as e:
            return f"检测失败:{type(e).__name__}"

    def location_for_ytdlp(self) -> Optional[str]:
        path = self.find(self.manual_path)
        return str(Path(path).parent) if path else None

    def update(self) -> bool:
        self.log(f"FFmpeg 更新: 下载至 {TOOLS_DIR}")
        if sys.platform != "win32":
            self.log("非 Windows 请用系统包管理器安装 ffmpeg")
            return self.find() is not None
        tmp_zip = TOOLS_DIR / "ffmpeg_dl.zip"
        try:
            with requests.get(FFMPEG_ZIP_URL, stream=True, timeout=120) as r:
                r.raise_for_status()
                with open(tmp_zip, "wb") as f:
                    for chunk in r.iter_content(chunk_size=256 * 1024):
                        if chunk:
                            f.write(chunk)
            with zipfile.ZipFile(tmp_zip, "r") as zf:
                for name in zf.namelist():
                    if Path(name).name.lower() in ("ffmpeg.exe", "ffprobe.exe"):
                        dest = TOOLS_DIR / Path(name).name
                        with zf.open(name) as src, open(dest, "wb") as dst:
                            shutil.copyfileobj(src, dst)
            tmp_zip.unlink(missing_ok=True)
            if not self.local_bin.exists():
                return self._update_btbn()
            self.log(f"FFmpeg 已就绪: {self.version()}")
            return True
        except Exception as e:
            self.log(f"官方源失败: {e}，尝试备用源...")
            try:
                return self._update_btbn()
            except Exception as e2:
                self.log(f"备用源失败: {e2}")
                return False
        finally:
            tmp_zip.unlink(missing_ok=True)

    def _update_btbn(self) -> bool:
        api = requests.get(FFMPEG_FALLBACK_API, timeout=30)
        api.raise_for_status()
        data = api.json()
        asset_url = None
        for a in data.get("assets", []):
            name = a.get("name", "")
            if "win64" in name and "essentials" in name and name.endswith(".zip"):
                asset_url = a.get("browser_download_url")
                break
        if not asset_url:
            raise RuntimeError("未找到合适的 BtbN 包")
        try:
            gh = str(cfg.data.get("github_mirror") or "")
        except Exception:
            gh = ""
        tmp_zip = TOOLS_DIR / "ffmpeg_btbn.zip"
        _download_with_mirrors(
            pkg_update.github_url_candidates(asset_url, gh), tmp_zip,
            log=self.log, timeout=300,
        )
        with zipfile.ZipFile(tmp_zip, "r") as zf:
            for name in zf.namelist():
                if Path(name).name.lower() in ("ffmpeg.exe", "ffprobe.exe"):
                    dest = TOOLS_DIR / Path(name).name
                    with zf.open(name) as src, open(dest, "wb") as dst:
                        shutil.copyfileobj(src, dst)
        tmp_zip.unlink(missing_ok=True)
        return self.local_bin.exists()


# -------------------- 视频编码器：选择、探测与降级链 --------------------
# 默认 cpu + x264 + medium 就是加这一段之前的行为：不升驱动、不装新 FFmpeg 的人，
# 成品编码一个字都不该变。硬件编码与 x265 都要自己在设置里点一下才生效。
VIDEO_ENCODER_MODES = ("auto", "cpu", "nvidia", "intel", "amd")
VIDEO_CPU_CODECS = ("x264", "x265")
VIDEO_CPU_PRESETS = ("veryfast", "fast", "medium", "slow")
CPU_ENCODER = {"x264": "libx264", "x265": "libx265"}
HW_ENCODER_BY_VENDOR = {"nvidia": "hevc_nvenc", "intel": "hevc_qsv", "amd": "hevc_amf"}
# 「自动」就按这个顺序挨个试；Linux 的 VAAPI 这轮不做 —— 它要 -vaapi_device 加
# hwupload 改写滤镜链，会和烧字幕那条 ass= 滤镜打架。
HW_ENCODER_ORDER = ["hevc_nvenc", "hevc_qsv", "hevc_amf"]
NVENC_PRESET_MAP = {"veryfast": "p1", "fast": "p2", "medium": "p4", "slow": "p5"}
ENCODER_LABELS = {
    "libx264": "H.264（CPU · libx264）",
    "libx265": "H.265/HEVC（CPU · libx265）",
    "hevc_nvenc": "H.265/HEVC（NVIDIA 硬件）",
    "hevc_qsv": "H.265/HEVC（Intel 核显 QSV）",
    "hevc_amf": "H.265/HEVC（AMD 硬件 AMF）",
}
# x265 明显比 x264 慢，超时预算按同一倍数放大，否则慢机器上会被自己的预算掐死。
# 本机实测（1080p30、同一 30 秒片段、CRF 23 / preset medium）：libx264 4.3s，libx265 11.9s = 2.75 倍；
# 合成噪声源那一次是 3.6 倍。取 3.0 是给慢机器留余量的口径，不是猜的。
X265_TIMEOUT_MULT = 3.0
_ENCODER_PROBE_TTL = 600.0
_encoder_probe_cache: dict = {"ts": 0.0, "ffmpeg": "", "items": {}}


def _sub_kwargs() -> dict:
    kw = {"capture_output": True, "text": True, "encoding": "utf-8", "errors": "replace"}
    if sys.platform == "win32":
        kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return kw


def _encoder_args(name: str, quality: int, preset: str) -> List[str]:
    """这个编码器在命令行里长什么样。

    quality 对外只露一个「越小越费码率」的 CRF 口径数字，各家参数名不同
    （crf / cq / global_quality / qp_i+qp_p），在这一个函数里做映射。
    HEVC 装进 mp4 要补 `-tag:v hvc1`，否则 QuickTime 和部分播放器认不出轨道。
    """
    q = str(max(0, min(51, int(quality))))
    p = preset if preset in VIDEO_CPU_PRESETS else "medium"
    if name == "libx264":
        return ["-c:v", "libx264", "-preset", p, "-crf", q, "-pix_fmt", "yuv420p"]
    if name == "libx265":
        return ["-c:v", "libx265", "-preset", p, "-crf", q, "-pix_fmt", "yuv420p", "-tag:v", "hvc1"]
    if name == "hevc_nvenc":
        return ["-c:v", "hevc_nvenc", "-preset", NVENC_PRESET_MAP[p], "-rc", "vbr",
                "-cq", q, "-b:v", "0", "-pix_fmt", "yuv420p", "-tag:v", "hvc1"]
    if name == "hevc_qsv":
        return ["-c:v", "hevc_qsv", "-preset", p, "-global_quality", q,
                "-pix_fmt", "nv12", "-tag:v", "hvc1"]
    if name == "hevc_amf":
        return ["-c:v", "hevc_amf", "-quality", "balanced", "-rc", "cqp",
                "-qp_i", q, "-qp_p", q, "-pix_fmt", "nv12", "-tag:v", "hvc1"]
    raise ValueError(f"不支持的编码器: {name}")


def _video_encode_pref() -> dict:
    """设置里那三个下拉的当前取值；认不出的写法一律退回默认，不静默改用别的。"""
    try:
        mode = str(cfg.data.get("video_encoder") or "cpu").strip().lower()
        codec = str(cfg.data.get("video_cpu_codec") or "x264").strip().lower()
        preset = str(cfg.data.get("video_cpu_preset") or "medium").strip().lower()
    except Exception:
        mode, codec, preset = "cpu", "x264", "medium"
    return {"mode": mode if mode in VIDEO_ENCODER_MODES else "cpu",
            "codec": codec if codec in VIDEO_CPU_CODECS else "x264",
            "preset": preset if preset in VIDEO_CPU_PRESETS else "medium"}


def _video_encode_chain(quality: int) -> List[dict]:
    """排出「先试哪个编码器、失败换哪个」。

    CPU 那条永远垫底，x265 与 x264 互为兜底：只缺 libx265 的 FFmpeg 构建不该让整件事失败。
    探测缓存说硬件编码器起不来时，这里把它从链上摘掉（CPU 的两条永不摘），
    省得在大文件上白等一趟注定失败的编码。
    """
    pref = _video_encode_pref()
    cpu_first = CPU_ENCODER[pref["codec"]]
    cpu_second = CPU_ENCODER["x264" if pref["codec"] == "x265" else "x265"]
    if pref["mode"] == "cpu":
        cands = [cpu_first, cpu_second]
    elif pref["mode"] in HW_ENCODER_BY_VENDOR:
        cands = [HW_ENCODER_BY_VENDOR[pref["mode"]], cpu_first, cpu_second]
    else:
        cands = list(HW_ENCODER_ORDER) + [cpu_first, cpu_second]
    probe = _encoder_probe_cache
    fresh = bool(probe.get("items")) and time.time() - float(probe.get("ts") or 0) < _ENCODER_PROBE_TTL
    out, seen = [], set()
    for name in cands:
        if name in seen:
            continue
        seen.add(name)
        if fresh and not name.startswith("libx"):
            if not (probe["items"].get(name) or {}).get("available", True):
                continue
        out.append({"encoder": name, "label": ENCODER_LABELS.get(name, name),
                    "args": _encoder_args(name, quality, pref["preset"]),
                    "timeout_mult": X265_TIMEOUT_MULT if name == "libx265" else 1.0})
    return out or [{"encoder": "libx264", "label": ENCODER_LABELS["libx264"],
                    "args": _encoder_args("libx264", quality, "medium"), "timeout_mult": 1.0}]


def _encoders_built(ff: str) -> set:
    """`ffmpeg -encoders` 里列得出的编码器名。列不出来就当没有，省得白跑一次探测。"""
    try:
        r = subprocess.run([ff, "-hide_banner", "-encoders"], timeout=15, **_sub_kwargs())
        text = (r.stdout or "") + "\n" + (r.stderr or "")
    except Exception:
        return set()
    names = set()
    for line in text.splitlines():
        m = re.match(r"^\s*V[.\w]{5}\s+(\S+)", line)
        if m:
            names.add(m.group(1))
    return names


def _encoder_fail_reason(text: str) -> str:
    """把 ffmpeg 那句英文报错翻成一句能照着办事的中文。"""
    t = (text or "").strip()
    m = re.search(r"Driver does not support the required nvenc API version\.\s*"
                  r"Required:\s*([\d.]+)\s*Found:\s*([\d.]+)", t, re.I)
    if m:
        return (f"显卡驱动不支持这个 FFmpeg 要的 NVENC API 版本（要 {m.group(1)}，"
                f"本机驱动只有 {m.group(2)}）—— 升 NVIDIA 驱动，或换更旧的 FFmpeg")
    m = re.search(r"minimum required Nvidia driver for nvenc is ([\d.]+)", t, re.I)
    if m:
        return f"NVIDIA 驱动需要 {m.group(1)} 或更新，本机不满足"
    if "Cannot load" in t and ("nv-codec" in t or "cuda" in t.lower()):
        return "加载不到 NVIDIA 的编解码库（没装驱动，或驱动不完整）"
    if "Unknown encoder" in t:
        return "这个 FFmpeg 构建里没有该编码器"
    m = re.search(r"([^:\n]*(?:not supported|unusable|failed|Invalid|denied)[^\n]*)", t, re.I)
    tail = (m.group(1) if m else "") or t.splitlines()[-1][:120] if t else ""
    return f"起不来：{tail.strip()}"[:180] if tail else "编码器初始化失败（ffmpeg 没给出原因）"


def _probe_encoder(ff: str, name: str, timeout_s: float = 8.0) -> tuple:
    """真喂一帧黑场进去，看它开不开得起。

    `-encoders` 列得出名字不代表能用：本机就遇到过 NVENC「列得出、驱动不认」。
    AMF 在这类机器上会**直接挂住不返回**，所以必须带硬超时并当成不可用 ——
    不然探测这一步会把界面卡死。
    """
    try:
        args = _encoder_args(name, 28, "fast")
    except Exception as e:
        return False, str(e)
    cmd = ([ff, "-hide_banner", "-loglevel", "error", "-f", "lavfi",
            "-i", "color=c=black:s=320x320:r=25:d=0.2"] + list(args) + ["-f", "null", "-"])
    try:
        r = subprocess.run(cmd, timeout=timeout_s, **_sub_kwargs())
    except subprocess.TimeoutExpired:
        return False, (f"试了 {int(timeout_s)} 秒没反应 —— 这个编码器会在真转码时把进程挂住，"
                       "所以按不可用处理，降级链会直接跳过它")
    except Exception as e:
        return False, f"探测本身没跑起来：{type(e).__name__}: {e}"[:120]
    if r.returncode == 0:
        return True, ""
    return False, _encoder_fail_reason((r.stderr or "") + "\n" + (r.stdout or ""))


def _encoder_probe_status(refresh: bool = False) -> dict:
    # 带 manual_path：设置里指了别的 FFmpeg 时，探测的必须是转码真要用的那一个
    ff = ffmpeg_mgr.find(ffmpeg_mgr.manual_path)
    now = time.time()
    if not ff:
        return {"ok": False, "message": "未找到 FFmpeg", "items": [],
                "ffmpeg_path": "", "probed_at": 0, "ttl": _ENCODER_PROBE_TTL}
    c = _encoder_probe_cache
    c = _encoder_probe_cache
    # refresh=1 必须真的重探：否则「换了 FFmpeg / 升了驱动再点探测」只会拿旧答案
    if refresh or not (c["items"] and c["ffmpeg"] == str(ff) and now - float(c["ts"]) < _ENCODER_PROBE_TTL):
        built = _encoders_built(ff)
        items = {}
        for name in list(HW_ENCODER_ORDER) + ["libx265", "libx264"]:
            if built and name not in built:
                items[name] = {"available": False, "reason": "这个 FFmpeg 构建里没有它"}
                continue
            ok, why = _probe_encoder(ff, name)
            items[name] = {"available": ok, "reason": why}
        _encoder_probe_cache.update(ts=now, ffmpeg=str(ff), items=items, built=built)
    c = _encoder_probe_cache
    built = c.get("built") or set()
    items = [{"encoder": k, "label": ENCODER_LABELS.get(k, k),
              "available": bool(v.get("available")), "reason": v.get("reason") or "",
              # 列不出来就是「不知道」，别报 True 说「这个构建里有」
              "built": (k in built) if built else None}
             for k, v in (c.get("items") or {}).items()]
    return {"ok": True, "items": items, "ffmpeg_path": c["ffmpeg"],
            "ffmpeg_version": ffmpeg_mgr.version(), "probed_at": c["ts"],
            "ttl": _ENCODER_PROBE_TTL, "message": ""}


def _swap_encoder(args: List[str], encoder_args: List[str]) -> List[str]:
    """把预设里写死的那串 libx264 参数换成当前编码器的参数。

    预设自带的其余内容（`-vf scale`、音频那几段、`-b:a`）一个字都不动 ——
    换的只有视频编码器自己那一段。
    """
    out, i = list(args), 0
    while i < len(out):
        if out[i] == "-c:v" and i + 1 < len(out):
            j = i + 2
            while j < len(out) and out[j] not in ("-c:a", "-c", "-map", "-movflags", "-vn"):
                j += 1
            out[i:j] = list(encoder_args)
            break
        i += 1
    return out


def _preset_needs_encoder(args: List[str]) -> bool:
    """只有真的重编视频的预设才参与编码器替换；`-c copy` 和抽音频那几条原样走。"""
    return "-c:v" in args and "copy" not in args and "-vn" not in args


def _video_encoders_payload(refresh: bool = False) -> dict:
    """界面「设置 → 视频编码」那张卡片的读数：本机每个候选编码器起不起得来、起不来为什么。
    路由在下方 app 建好之后注册（这一段还在 `app` 之前，装饰器会 NameError）。"""
    st = _encoder_probe_status(bool(refresh))
    st["preference"] = _video_encode_pref()
    st["modes"] = list(VIDEO_ENCODER_MODES)
    st["cpu_codecs"] = list(VIDEO_CPU_CODECS)
    st["presets"] = list(VIDEO_CPU_PRESETS)
    st["chain"] = [{"encoder": x["encoder"], "label": x["label"],
                    "timeout_mult": x["timeout_mult"]} for x in _video_encode_chain(23)]
    return st


def is_native_binary(path) -> bool:
    """这个文件在当前系统上能不能直接 exec。

    Docker 的 COPY 会把 Windows 的 tools\\*.exe 一起带进 Linux 镜像：文件存在、is_file() 为真，
    但执行报 Exec format error，而调用处普遍用 try 把异常吞成「未安装」——只看存在性就会误报有。
    """
    try:
        p = Path(path)
        if not p.is_file():
            return False
        if sys.platform == "win32":
            return True
        if not os.access(p, os.X_OK):
            return False
        with p.open("rb") as fh:
            head = fh.read(4)
        # ELF 或 shebang 脚本才认；MZ（PE / .exe）在 Linux/macOS 上跑不起来。
        return head[:4] == b"\x7fELF" or head[:2] == b"#!"
    except Exception:
        return False


def find_n_m3u8dl() -> Optional[str]:
    """查找 N_m3u8DL-RE 专用 HLS/DASH 引擎（Ghost 同款思路）"""
    exe = ".exe" if sys.platform == "win32" else ""
    names = (
        f"N_m3u8DL-RE{exe}", f"N_m3u8DL-CLI{exe}", f"m3u8dl{exe}",
    )
    if exe:
        names += ("N_m3u8DL-RE", "N_m3u8DL-CLI", "m3u8dl")
    for n in names:
        p = TOOLS_DIR / n
        if is_native_binary(p):
            return str(p)
    for n in names:
        found = shutil.which(n)
        if found and is_native_binary(found):
            return found
    # 递归 tools：只认当前平台跑得起来的，避免 Windows 包留在镜像里被选中
    for n in names:
        for p in TOOLS_DIR.rglob(n):
            if is_native_binary(p):
                return str(p)
    return None


def n_m3u8dl_version() -> str:
    path = find_n_m3u8dl()
    if not path:
        return "未安装"
    try:
        kw: dict = {"capture_output": True, "timeout": 8, "text": True}
        if sys.platform == "win32":
            kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        r = subprocess.run([path, "--version"], **kw)
        out = ((r.stdout or "") + (r.stderr or "")).strip()
        # 取第一行版本号
        line = (out.splitlines() or [""])[0].strip()
        return line[:80] if line else Path(path).name
    except Exception:
        return Path(path).name


def _n_m3u8dl_asset_name() -> str:
    """按当前平台选择资源 id，如 win-x64 / linux-x64"""
    machine = ""
    try:
        machine = (os.uname().machine if hasattr(os, "uname") else "").lower()
    except Exception:
        pass
    if sys.platform == "win32":
        arch = (os.environ.get("PROCESSOR_ARCHITECTURE") or platform_machine_safe()).lower()
        if "arm" in arch:
            return "win-arm64"
        return "win-x64"
    if sys.platform == "darwin":
        if "arm" in machine or "aarch64" in machine:
            return "osx-arm64"
        return "osx-x64"
    if "aarch64" in machine or "arm64" in machine:
        return "linux-arm64"
    return "linux-x64"


def platform_machine_safe() -> str:
    try:
        import platform
        return platform.machine() or ""
    except Exception:
        return ""


# 固定直链（避免 GitHub API 403 rate limit），可按需改版本号
# 来源: https://github.com/nilaoda/N_m3u8DL-RE/releases/tag/v0.6.0-beta
_NM3U8DL_TAG = "v0.6.0-beta"
_NM3U8DL_DATE = "20260629"
_NM3U8DL_DIRECT = {
    "win-x64": f"https://github.com/nilaoda/N_m3u8DL-RE/releases/download/{_NM3U8DL_TAG}/N_m3u8DL-RE_{_NM3U8DL_TAG}_win-x64_{_NM3U8DL_DATE}.zip",
    "win-arm64": f"https://github.com/nilaoda/N_m3u8DL-RE/releases/download/{_NM3U8DL_TAG}/N_m3u8DL-RE_{_NM3U8DL_TAG}_win-arm64_{_NM3U8DL_DATE}.zip",
    "win-NT6.0-x86": f"https://github.com/nilaoda/N_m3u8DL-RE/releases/download/{_NM3U8DL_TAG}/N_m3u8DL-RE_{_NM3U8DL_TAG}_win-NT6.0-x86_{_NM3U8DL_DATE}.zip",
    "linux-x64": f"https://github.com/nilaoda/N_m3u8DL-RE/releases/download/{_NM3U8DL_TAG}/N_m3u8DL-RE_{_NM3U8DL_TAG}_linux-x64_{_NM3U8DL_DATE}.tar.gz",
    "linux-arm64": f"https://github.com/nilaoda/N_m3u8DL-RE/releases/download/{_NM3U8DL_TAG}/N_m3u8DL-RE_{_NM3U8DL_TAG}_linux-arm64_{_NM3U8DL_DATE}.tar.gz",
    "osx-x64": f"https://github.com/nilaoda/N_m3u8DL-RE/releases/download/{_NM3U8DL_TAG}/N_m3u8DL-RE_{_NM3U8DL_TAG}_osx-x64_{_NM3U8DL_DATE}.tar.gz",
    "osx-arm64": f"https://github.com/nilaoda/N_m3u8DL-RE/releases/download/{_NM3U8DL_TAG}/N_m3u8DL-RE_{_NM3U8DL_TAG}_osx-arm64_{_NM3U8DL_DATE}.tar.gz",
}
# ghproxy 等镜像前缀（国内/限流时自动尝试）
_NM3U8DL_MIRRORS = (
    "",  # 官方
    "https://ghproxy.net/",
    "https://mirror.ghproxy.com/",
    "https://gh.ddlc.top/",
)


def _extract_n_m3u8dl_archive(tmp: Path, name: str, log: Callable) -> bool:
    """从 zip/tar.gz 解出可执行文件到 tools/"""
    installed = False
    if name.endswith(".zip") or tmp.suffix.lower() == ".zip":
        with zipfile.ZipFile(tmp, "r") as zf:
            for member in zf.namelist():
                base = Path(member).name
                if not base:
                    continue
                low = base.lower()
                if "n_m3u8dl" in low or (sys.platform == "win32" and low.endswith(".exe") and "m3u8" in low):
                    dest = TOOLS_DIR / base
                    with zf.open(member) as src, open(dest, "wb") as out:
                        shutil.copyfileobj(src, out)
                    if sys.platform != "win32":
                        try:
                            dest.chmod(0o755)
                        except Exception:
                            pass
                    log(f"已安装: {dest.name}")
                    installed = True
    elif ".tar" in name or tmp.suffixes[-2:] == [".tar", ".gz"] or name.endswith(".tgz"):
        import tarfile
        with tarfile.open(tmp, "r:gz") as tf:
            for member in tf.getmembers():
                base = Path(member.name).name
                if not base or not member.isfile():
                    continue
                if "n_m3u8dl" in base.lower():
                    dest = TOOLS_DIR / base
                    src = tf.extractfile(member)
                    if src:
                        with open(dest, "wb") as out:
                            shutil.copyfileobj(src, out)
                    try:
                        dest.chmod(0o755)
                    except Exception:
                        pass
                    log(f"已安装: {dest.name}")
                    installed = True
    return installed


def update_n_m3u8dl(log: Callable = print) -> str:
    """下载 N_m3u8DL-RE 到 tools/：优先固定直链（不走 API），避免 403 rate limit。"""
    rid = _n_m3u8dl_asset_name()
    url = _NM3U8DL_DIRECT.get(rid)
    if not url:
        return f"当前平台 {rid} 无预置下载地址"

    name = url.rsplit("/", 1)[-1]
    log(f"准备下载 N_m3u8DL-RE {_NM3U8DL_TAG} ({rid}) …")

    tmp = TOOLS_DIR / f"_nm3u8dl_dl{Path(name).suffix if Path(name).suffix else '.bin'}"
    if name.endswith(".tar.gz"):
        tmp = TOOLS_DIR / "_nm3u8dl_dl.tar.gz"

    last_err = ""
    downloaded = False
    mirror_list = list(_NM3U8DL_MIRRORS)
    # 设置中的 github_mirror 优先
    try:
        gm = (cfg.data.get("github_mirror") or "").strip()
        if gm:
            mirror_list = [gm if gm.endswith("/") else gm + "/"] + [m for m in mirror_list if m != gm]
    except Exception:
        pass
    for mirror in mirror_list:
        full = (mirror + url) if mirror else url
        try:
            log(f"尝试: {full[:80]}…")
            with requests.get(
                full,
                stream=True,
                timeout=300,
                headers={"User-Agent": "Mozilla/5.0 MediaDownloader-Web"},
                allow_redirects=True,
            ) as resp:
                if resp.status_code != 200:
                    last_err = f"HTTP {resp.status_code}"
                    log(f"失败 {last_err}", "warning")
                    continue
                with open(tmp, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=256 * 1024):
                        if chunk:
                            f.write(chunk)
            if tmp.exists() and tmp.stat().st_size > 10000:
                downloaded = True
                log(f"下载完成 ({tmp.stat().st_size // 1024} KB)")
                break
            last_err = "文件过小或为空"
        except Exception as e:
            last_err = str(e)
            log(f"下载异常: {e}", "warning")
            continue

    if not downloaded:
        tmp.unlink(missing_ok=True)
        return (
            f"下载失败: {last_err}。"
            f"可手动下载后放到 tools/：\n{url}"
        )

    try:
        ok = _extract_n_m3u8dl_archive(tmp, name, log)
        if not ok:
            return "解压后未找到 N_m3u8DL-RE 可执行文件"
    except Exception as e:
        return f"解压失败: {e}"
    finally:
        tmp.unlink(missing_ok=True)

    ver = n_m3u8dl_version()
    return f"成功 {_NM3U8DL_TAG} → {ver}"


# ---------- aria2c：安装入口与「连不上」的人话 ----------
# 磁力/种子只有 aria2 一条路。本机没有 aria2c 时「自动拉起」是空的，界面只剩 urllib 甩出来的
# WinError 10061，看不出下一步该干什么，所以这里补两件事：报错按「为什么连不上」分档说清，
# 外加一个把 aria2c 装进 tools/ 的入口（官方发布页的 Windows 包，和 N_m3u8DL-RE 走同一套镜像）。
_ARIA2_DIRECT = {
    "win-64": "https://github.com/aria2/aria2/releases/download/release-1.37.0/aria2-1.37.0-win-64bit-build1.zip",
    "win-32": "https://github.com/aria2/aria2/releases/download/release-1.37.0/aria2-1.37.0-win-32bit-build1.zip",
}


def _aria2_asset_id() -> str:
    """aria2 官方发布页只出 Windows 预编译包，其它平台走系统包管理器。"""
    if sys.platform == "win32":
        arch = (os.environ.get("PROCESSOR_ARCHITECTURE") or platform_machine_safe()).lower()
        return "win-32" if arch in ("x86", "wow64") else "win-64"
    return ""


def aria2_err_cn(err, cfg_data: Optional[dict] = None, app_dir: Optional[Path] = None) -> str:
    """把 aria2 RPC 的原始异常翻成人话。

    连接被拒（WinError 10061）在这里是最常见的一种，而它真正的原因往往是「本机根本没有
    aria2c」—— 那时「自动拉起」这个开关是空的，界面却只会甩 urllib 的原文，看不出下一步该干什么。
    """
    s = str(err or "")
    low = s.lower()
    rpc = str((cfg_data or {}).get("aria2_rpc") or "http://127.0.0.1:6800/jsonrpc")
    if "10061" in s or "connection refused" in low or "积极拒绝" in s:
        head = f"aria2 没有在跑（{rpc} 这个端口上没人应答）。"
        found = True
        try:
            import aria2_daemon
            d = aria2_daemon
            found = bool(d.find_binary(str((cfg_data or {}).get("aria2_bin") or ""),
                                        app_dir or APP_DIR, is_native_binary))
        except Exception:
            found = True
        if not found:
            return head + ("而且本机找不到 aria2c 可执行文件，所以「自动拉起 aria2」这个开关开着也是空的："
                           "去「组件与依赖」点 aria2 那行的安装（会下到 tools\\aria2c.exe），"
                           "或自己装一个后在设置里把路径指对。")
        return head + "点「检测 aria2」或重新提交任务会自动拉起本机 aria2c；反复拉不起来时看 Logs\\aria2_daemon.log。"
    if "timed out" in low or "timeout" in low:
        return f"连 aria2（{rpc}）超时：多半是那个端口上别的服务卡住，或被防火墙拦了，检查设置里的 RPC 地址。"
    if "401" in low or "403" in low or "unauthorized" in low or "secret" in low:
        return "aria2 拒绝了这次请求：RPC Secret 不对。设置里的「aria2 Secret」要么填 aria2c 自己配的那个，要么留空。"
    return f"aria2 连接异常：{s[:160]}"


def aria2_local_version() -> str:
    """本机 aria2c 的版本行；没装返回空串（「组件与依赖」那行按它决定显示「未安装」）。"""
    try:
        import aria2_daemon
        p = aria2_daemon.find_binary(str(cfg.data.get("aria2_bin") or ""), APP_DIR, is_native_binary)
    except Exception:
        p = ""
    if not p:
        return ""
    try:
        kw: dict = {"capture_output": True, "timeout": 8, "text": True}
        if sys.platform == "win32":
            kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        r = subprocess.run([p, "--version"], **kw)
        out = ((r.stdout or "") + (r.stderr or "")).strip()
        line = (out.splitlines() or [""])[0].strip()
        return line[:80] if line else Path(p).name
    except Exception:
        return Path(p).name


def _extract_aria2_archive(tmp: Path, log: Callable) -> bool:
    """官方 zip 里是一个带版本号的目录：只取 aria2c.exe 和它要用的 dll，文档与许可证不落地。"""
    want = ("aria2c.exe", "aria2c")
    installed = False
    with zipfile.ZipFile(tmp, "r") as zf:
        for member in zf.namelist():
            base = Path(member).name
            low = base.lower()
            if not base or (low not in want and not low.endswith(".dll")):
                continue
            dest = TOOLS_DIR / base
            with zf.open(member) as src, open(dest, "wb") as out:
                shutil.copyfileobj(src, out)
            log(f"已安装: {dest.name}")
            if low in want:
                installed = True
    return installed


def update_aria2(log: Callable = print) -> str:
    """下载 aria2c 到 tools/ 并当场拉起 RPC：磁力/种子页在没有它的机器上本来就跑不动。"""
    rid = _aria2_asset_id()
    if not rid:
        return "当前平台没有 aria2 的官方预编译包，请用系统包管理器装（Debian/Ubuntu：apt install aria2，" \
               "Fedora：dnf install aria2，Arch：pacman -S aria2），装完点「检测 aria2」即可"
    url = _ARIA2_DIRECT[rid]
    name = url.rsplit("/", 1)[-1]
    log(f"准备下载 aria2c（{rid}）…")
    tmp = TOOLS_DIR / "_aria2_dl.zip"
    last_err = ""
    downloaded = False
    mirror_list = list(_NM3U8DL_MIRRORS)
    try:
        gm = (cfg.data.get("github_mirror") or "").strip()
        if gm:
            mirror_list = [gm if gm.endswith("/") else gm + "/"] + [m for m in mirror_list if m != gm]
    except Exception:
        pass
    for mirror in mirror_list:
        full = (mirror + url) if mirror else url
        try:
            log(f"尝试: {full[:80]}…")
            with requests.get(full, stream=True, timeout=300,
                              headers={"User-Agent": "Mozilla/5.0 MediaDownloader-Web"},
                              allow_redirects=True) as resp:
                if resp.status_code != 200:
                    last_err = f"HTTP {resp.status_code}"
                    log(f"失败 {last_err}", "warning")
                    continue
                with open(tmp, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=256 * 1024):
                        if chunk:
                            f.write(chunk)
            if tmp.exists() and tmp.stat().st_size > 100000:
                downloaded = True
                log(f"下载完成 ({tmp.stat().st_size // 1024} KB)")
                break
            last_err = "文件过小或为空"
        except Exception as e:
            last_err = str(e)
            log(f"下载异常: {e}", "warning")
            continue
    if not downloaded:
        tmp.unlink(missing_ok=True)
        return f"下载失败: {last_err}。可手动下载后把 aria2c.exe 放进 tools\\：\n{url}"
    try:
        if not _extract_aria2_archive(tmp, log):
            return "解压后没找到 aria2c.exe，包可能不完整"
    except Exception as e:
        return f"解压失败: {e}"
    finally:
        tmp.unlink(missing_ok=True)
    ok, why = bt_ensure(
        dict(cfg.data),
        lambda m, level="info": log_mgr.log(f"[aria2 安装] {m}", level,
                                            k="srv.comp.aria2_install_line", kv={"detail": m}))
    return ("装好并已自动拉起 aria2" if ok else f"装好了，但拉起失败：{why}")


def _probe_hls_playlist(url: str, headers: Optional[dict] = None, proxy: str = "") -> tuple:
    """
    预取播放列表，确认是 m3u8 内容。返回 (ok, text_or_err, final_url)。
    """
    hdrs = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
        "Accept": "*/*",
    }
    if headers:
        hdrs.update(headers)
    proxies = http_proxies(url, proxy)
    try:
        r = requests.get(
            url,
            headers=hdrs,
            proxies=proxies,
            timeout=25,
            verify=False,
            allow_redirects=True,
        )
        if r.status_code >= 400:
            return False, f"HTTP {r.status_code}", url
        text = (r.text or "")[:8000]
        low = text.lstrip().lower()
        if "#extm3u" in low or "#ext-x-" in low or "#extinf" in low:
            return True, text, str(r.url)
        # 有些返回 gzip 乱码已由 requests 解码；仍不像列表
        return False, f"内容不像 m3u8（前 80 字: {text[:80]!r}）", str(r.url)
    except Exception as e:
        return False, str(e), url


def download_hls_with_engine(
    m3u8_url: str,
    out_dir: str,
    title: str = "",
    proxy: str = "",
    headers: Optional[dict] = None,
    log: Callable = print,
    stop_flag: Optional[Callable[[], bool]] = None,
    progress_cb: Optional[Callable] = None,
    task_id: str = "",
    key_info: str = "",
) -> tuple:
    """
    专用 HLS 引擎下载：优先 N_m3u8DL-RE，其次 ffmpeg。
    key_info 是 16 进制 AES-128 密钥（猫抓「抓取密钥」推来的那种），空则按列表自带方式解密。
    返回 (ok: bool, filepath: str)
    """
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    safe = safe_filename_component(title or "hls", 60)
    dest_base = out_path / safe

    def _prog(pct: float):
        if progress_cb and task_id:
            try:
                progress_cb(task_id, pct, "", "")
            except Exception:
                pass

    _prog(2)
    log(f"HLS 探测播放列表…")
    ok_probe, body, final_url = _probe_hls_playlist(m3u8_url, headers=headers, proxy=proxy)
    if not ok_probe:
        log(f"HLS 播放列表不可用: {body}", "error")
        return False, ""
    log(f"HLS 列表 OK（{len(body)} 字节）→ 开始拉流")
    _prog(8)
    # 使用探测后的最终 URL（含重定向）
    m3u8_url = final_url or m3u8_url

    def _poll_hls_proc(proc) -> None:
        """拉流期间按输出文件大小更新进度，避免界面一直停在 10%。"""
        deadline = time.time() + 7200
        last_sz = 0
        while proc.poll() is None:
            if stop_flag and stop_flag():
                try:
                    proc.kill()
                except Exception:
                    pass
                log("用户停止 HLS", "warning")
                return
            if time.time() > deadline:
                try:
                    proc.kill()
                except Exception:
                    pass
                log("HLS 超时已终止", "warning")
                return
            try:
                cands = [
                    p
                    for p in list(out_path.glob(f"{safe}.*")) + list(out_path.glob(f"{safe}*"))
                    if p.is_file()
                    and p.suffix.lower() in (".mp4", ".mkv", ".ts", ".m4s", ".flv", ".part")
                ]
                if cands:
                    best = max(cands, key=lambda p: p.stat().st_size)
                    sz = best.stat().st_size
                    if sz > last_sz:
                        last_sz = sz
                        _prog(min(90.0, 12.0 + (sz / (80 * 1024 * 1024)) * 75))
            except Exception:
                pass
            time.sleep(1.0)

    engine = find_n_m3u8dl()
    if engine:
        log(f"HLS 专用引擎: {Path(engine).name}（拉流中…）")
        cmd = [
            engine,
            m3u8_url,
            "--save-dir", str(out_path),
            "--save-name", safe,
            "--auto-select",
            "--thread-count", "8",
            "--download-retry-count", "5",
            "--http-request-timeout", "30",
        ]
        po = proxy_arg(m3u8_url, proxy)
        if po:
            cmd += ["--custom-proxy", po]
        if key_info:
            cmd += ["--key", key_info]
            log("已带上外部获取的 HLS 解密钥（猫抓「抓取密钥」或界面填写）")
        if headers:
            for k, v in headers.items():
                cmd += ["--header", f"{k}: {v}"]
        try:
            _prog(10)
            kw: dict = {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE}
            if sys.platform == "win32":
                kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            proc = subprocess.Popen(cmd, **kw)
            _poll_hls_proc(proc)
            stdout, stderr = b"", b""
            try:
                stdout, stderr = proc.communicate(timeout=60)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
            candidates = [
                p
                for p in list(out_path.glob(f"{safe}.*")) + list(out_path.glob(f"{safe}*"))
                if p.is_file()
                and p.suffix.lower() in (".mp4", ".mkv", ".ts", ".m4s", ".flv")
                and p.stat().st_size > 10_000
            ]
            if candidates:
                best = max(candidates, key=lambda p: p.stat().st_size)
                log(f"N_m3u8DL 完成: {best.name} ({best.stat().st_size // 1024} KB)")
                _prog(100)
                return True, str(best)
            err = (stderr or stdout or b"").decode("utf-8", errors="ignore")[-500:]
            log(f"N_m3u8DL 失败 rc={proc.returncode}: {err}", "warning")
        except Exception as e:
            log(f"N_m3u8DL 异常: {e}", "warning")

    # 回退 ffmpeg
    ff = None
    try:
        ff = ffmpeg_mgr.find()
    except Exception:
        pass
    if not ff:
        for name in ("ffmpeg.exe", "ffmpeg"):
            p = TOOLS_DIR / name
            if p.is_file():
                ff = str(p)
                break
        if not ff:
            ff = shutil.which("ffmpeg")
    if not ff:
        log("未找到 N_m3u8DL-RE 或 ffmpeg，无法下载 HLS", "error")
        return False, ""

    out_file = dest_base.with_suffix(".mp4")
    log(f"HLS 回退 ffmpeg → {out_file.name}")
    # 将 header 传给 ffmpeg
    cmd = [
        ff, "-y", "-hide_banner", "-loglevel", "warning",
        "-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5",
        "-rw_timeout", "30000000",
    ]
    if headers:
        # ffmpeg: -headers "Referer: xxx\r\nUser-Agent: xxx\r\n"
        hlines = "".join(f"{k}: {v}\r\n" for k, v in headers.items())
        cmd += ["-headers", hlines]
    if key_info:
        cmd += ["-decryption_key", key_info]
        log("已带上外部获取的 HLS 解密钥（ffmpeg -decryption_key）")
    cmd += ["-i", m3u8_url, "-c", "copy", "-bsf:a", "aac_adtstoasc", str(out_file)]
    env = apply_proxy_env(os.environ.copy(), m3u8_url, proxy_override=proxy)
    try:
        _prog(15)
        kw: dict = {"capture_output": True, "timeout": 7200, "env": env}
        if sys.platform == "win32":
            kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        r = subprocess.run(cmd, **kw)
        if out_file.exists() and out_file.stat().st_size > 10_000:
            log(f"ffmpeg HLS 完成: {out_file.name} ({out_file.stat().st_size // 1024} KB)")
            _prog(100)
            return True, str(out_file)
        err = (r.stderr or b"").decode("utf-8", errors="ignore")[-500:]
        log(f"ffmpeg HLS 失败 rc={r.returncode}: {err}", "error")
        return False, ""
    except subprocess.TimeoutExpired:
        log("ffmpeg HLS 超时", "error")
        return False, ""
    except Exception as e:
        log(f"ffmpeg HLS 异常: {e}", "error")
        return False, ""


# Windows 保留名（CON/NUL/COM1…）带扩展名一样禁用；Win11 24H2 起系统放开了，
# 但便携包用户不一定在 24H2，仍按最老系统的口径收掉
# 后缀段允许多个点（nul.tar.gz 在老系统同样指向设备），裸字母后缀不算（com1abc 是合法名字）
_WIN_RESERVED_RE = re.compile(r"^(con|prn|aux|nul|com[1-9]|lpt[1-9])(\..*)?$", re.I)
# 零宽与方向控制符：列表里看着是正常名字，实际写盘是另一个名字（可用来伪装 .exe.txt）
_BIDI_CTRL_RE = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff\u2060]")


def safe_filename_component(s: str, max_len: int = 60) -> str:
    """Windows 安全文件名片段：去掉 <>:"/\\|?* 及全角同形字符，限制长度。

    上游标题里的保留名、方向控制符、首尾点都会让写盘失败或写出误导性名字，所以一并收掉。
    """
    if not s:
        return "download"
    s = str(s)
    # 全角标点 → 安全替代（Errno 22 常见来源）
    trans = str.maketrans({
        "：": "-", "？": "", "｜": "-", "＊": "", "＂": "",
        "“": "", "”": "", "‘": "", "’": "",
        "＜": "", "＞": "", "／": "_", "＼": "_",
        "<": "", ">": "", "|": "-", "?": "", "*": "",
        "/": "_", "\\": "_", '"': "", ":": "-",
        "\n": " ", "\r": " ", "\t": " ", "\x00": "",
    })
    s = s.translate(trans)
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f\x7f]', "_", s)
    s = _BIDI_CTRL_RE.sub("", s)
    s = re.sub(r"\s+", " ", s).strip(" .")
    if len(s) > max_len:
        s = s[:max_len].rstrip(" .")
    # 保留名要在截断之后再查：截短本身可能把名字截成 CON/NUL
    if _WIN_RESERVED_RE.match(s):
        s = ("_" + s)[:max_len]
    return s or "download"


# -------------------- 下载引擎 --------------------
PO_DEFAULT_URL = "http://127.0.0.1:4416"
# 这些客户端没有 PO Token 基本拿不到流，服务不通就别浪费时间试
PO_ONLY_CLIENTS = ("web", "mweb", "tv", "web_embedded")
# yt-dlp 报这些通常不是链接坏了，而是播放器/BOT 校验挡路 → 值得换个 player_client
PLAYER_ERR_KEYS = (
    "sign in to confirm",
    "not a bot",
    "please sign in",
    "login required",
    "player response",
    "po token",
    "getpot",
    "requested format is not available",
    "precondition failed",
    "403 forbidden",
)
_PO_CACHE: Dict = {"ts": 0.0, "ok": False, "installed": False, "detail": "", "url": PO_DEFAULT_URL}
# pip 包名。落盘的不是同名模块，而是 yt_dlp_plugins/extractor/getpot_bgutil*.py
POT_PROVIDER_PKG = "bgutil-ytdlp-pot-provider"
# 造票那个服务端随程序放在 tools/ 下（要本机有 node 才起得来，程序不带 node 二进制）
POT_SERVER_DIR_NAME = "bgutil-pot-server"
# 被裁时补试的那一套：yt-dlp 的 all = 把所有播放器客户端各解一遍再合并，是唯一吃到票的那类
YT_WIDE_CLIENTS = ["all"]

# 画质档位名 → 高度上限。口径只在这里写一次：_resolve_format 用它拼 b[height<=…]，
# 解析页的体积估算（_VIDEO_TIERS）和成品回读比对（tier_readback）都跟着它，
# 否则「用户点的档」「程序限的高」「回读判的达标」三处会各算各的。
VIDEO_QUALITY_HEIGHTS = {
    "4K": 2160, "1440p": 1440, "1080p": 1080, "720p": 720, "480p": 480, "360p": 360,
}


def quality_height_cap(video_q) -> int:
    """所选档位对应的高度上限，0 = 没设上限（best / 空 / 认不出的写法）。"""
    return int(VIDEO_QUALITY_HEIGHTS.get(str(video_q or "").strip(), 0) or 0)


def _pot_plugin_installed() -> bool:
    # 装的到底是什么：pip 包名 bgutil-ytdlp-pot-provider 落盘的不是同名模块，
    # 而是 yt-dlp 插件目录下的 yt_dlp_plugins/extractor/getpot_bgutil*.py，
    # yt-dlp 只认后者。查错名字会把「已经装好」一直报成「没装」。
    import importlib.util

    for mod in ("yt_dlp_plugins.extractor.getpot_bgutil",
                "yt_dlp_plugins.extractor.getpot_bgutil_http",
                "yt_dlp_plugins.extractor.getpot_bgutil_script"):
        try:
            if importlib.util.find_spec(mod) is not None:
                return True
        except Exception:
            continue
    return False


def _po_err_cn(e: Exception) -> str:
    low = str(e or "").lower()
    if "read timed out" in low or "readtimeout" in low:
        return "探测超时（服务没响应）"
    if "getaddrinfo" in low or "name resolution" in low or "failed to resolve" in low:
        return "地址无法解析（检查服务 URL）"
    if ("connecttimeout" in low or "max retries exceeded" in low
            or "connection refused" in low or "newconnectionerror" in low
            or "failed to establish" in low):
        return "连不上该地址（服务没启动或端口不对）"
    return str(e)[:100]


def _po_ping_ok(url: str, timeout: float = 2.5) -> bool:
    try:
        return requests.get(str(url).rstrip("/") + "/ping", timeout=timeout, verify=False).status_code == 200
    except Exception:
        return False


def po_token_health(*, force: bool = False, timeout: float = 2.5,
                    cfg_override: Optional[dict] = None) -> Dict:
    """PO Token 服务健康门控：插件装了且 /ping 通才认为可用（结果缓存 60s）。"""
    now = time.time()
    src = cfg_override if isinstance(cfg_override, dict) else cfg.data  # type: ignore[name-defined]
    url = str(src.get("po_provider_url") or PO_DEFAULT_URL).strip().rstrip("/") or PO_DEFAULT_URL
    if not force and not src.get("po_provider_enabled"):
        return {"ts": now, "ok": False, "installed": _PO_CACHE.get("installed", False),
                "detail": "未启用", "url": url, "cached": True}
    if (not force and url == str(_PO_CACHE.get("url") or "")
            and now - float(_PO_CACHE.get("ts") or 0) < 60):
        return dict(_PO_CACHE, cached=True)
    installed = _pot_plugin_installed()
    ok = False
    detail = ""
    try:
        r = requests.get(url + "/ping", timeout=timeout, verify=False)
        ok = r.status_code == 200
        detail = f"HTTP {r.status_code} {(r.text or '').strip()[:30]}"
        if ok and not installed:
            detail += "（未装 bgutil 插件，拿不到票）"
    except Exception as e:
        detail = _po_err_cn(e)
        # 「连不上这个地址」基本等于服务端没在跑，而不是人把地址写错了 —— 顺手拉一次
        if "连不上该地址" in detail:
            try:
                import pot_daemon

                got, why = pot_daemon.ensure_running(
                    url=url, app_dir=APP_DIR,
                    ping=lambda: _po_ping_ok(url, timeout),
                    log=lambda m: log_mgr.log(m),
                )
                if got:
                    ok = True
                    detail = f"{why}（tools/{pot_daemon.SERVER_DIR_NAME}，程序代起）"
                else:
                    detail += f"；自动拉起没成：{why}"
            except Exception as ee:
                detail += f"；自动拉起失败 {str(ee)[:60]}"
    _PO_CACHE.update({"ts": now, "ok": ok, "installed": installed, "detail": detail, "url": url})
    return dict(_PO_CACHE, cached=False)


# ---------- 自定义 yt-dlp 参数 ----------
# 「设置 → 下载行为」里可以写一行 yt-dlp 命令行参数（下载页还能给单批任务临时换一串），
# 例如 --socket-timeout 60 -N 4。解析完全跟着本机 yt-dlp 的参数表走：
# shlex 切词 → 查它注册过的参数决定每个写法吃几个值 → 危险项和与软件冲突的项当场点名 →
# 剩下的和「空跑一遍 parse_options」的基线做差，才是要并进去的真差异。
# （命令行默认值有 170 多项，不对差就会把 yt-dlp 的默认当成用户特意要的东西。）

# yt-dlp 内部字段名 -> 不接受的原因。按字段名挡，别名（--external-downloader）和
# 缩写（--no-check-certi）都逃不掉；值一律不进说明文字，因为 --username/--password
# 这类是允许写的，凭据不能落日志。
_YDL_ARG_FORBIDDEN = {
    "exec_cmd": "会在下载完成后执行任意命令",
    "exec_before_dl_cmd": "会在下载前后执行任意命令",
    "netrc_cmd": "会执行任意命令去取凭据",
    "external_downloader_args": "会向外部程序注入任意参数",
    "plugin_dirs": "会加载指定目录里的插件，等同执行别人的代码",
    "update_self": "会改动本机 yt-dlp 本体；更新请到「设置 → 组件与依赖」",
    "rm_cachedir": "会清空 yt-dlp 的缓存目录",
    "config_locations": "配置文件由软件统一管理",
    "batchfile": "不接受 URL 清单文件，链接请在下载页输入",
    "load_info_filename": "不接受本地 info.json 当作下载来源",
    "enable_file_urls": "会打开 file:// 协议，有安全风险",
    "cookiefile": "Cookie 请用「设置 → Cookie 与登录」提供",
    "cookiesfrombrowser": "Cookie 请用「设置 → Cookie 与登录」提供",
    "usenetrc": "不读取 .netrc 凭据",
    "netrc_location": "不读取 .netrc 凭据",
    "outtmpl": "成品文件名由「设置 → 文件名模板」决定",
    "paths": "成品存放位置由下载页与设置里的下载目录决定",
    "simulate": "会让任务只解析不下载",
    "skip_download": "会让任务只解析不下载",
    "dumpjson": "属于只打印信息的模式，会跳过下载",
    "print_json": "属于只打印信息的模式，会跳过下载",
    "dump_single_json": "属于只打印信息的模式，会跳过下载",
    "forceprint": "属于只打印信息的模式，会跳过下载",
    "print_to_file": "会把字段写到磁盘文件",
    "listformats": "属于只列出信息的模式，会跳过下载",
    "listformats_table": "属于只列出信息的模式，会跳过下载",
    "listsubtitles": "属于只列出信息的模式，会跳过下载",
    "list_thumbnails": "属于只列出信息的模式，会跳过下载",
    "list_extractors": "只列出支持的平台，不下载",
    "list_extractor_descriptions": "只列出支持的平台，不下载",
    "list_impersonate_targets": "只列出可用的浏览器指纹，不下载",
    "ap_list_mso": "只列出频道商，不下载",
    "gettitle": "属于只打印信息的模式，会跳过下载",
    "getid": "属于只打印信息的模式，会跳过下载",
    "getthumbnail": "属于只打印信息的模式，会跳过下载",
    "getdescription": "属于只打印信息的模式，会跳过下载",
    "getduration": "属于只打印信息的模式，会跳过下载",
    "getfilename": "属于只打印信息的模式，会跳过下载",
    "getformat": "属于只打印信息的模式，会跳过下载",
    "geturl": "属于只打印信息的模式，会跳过下载",
    "print_help": "只打印帮助",
    "verbose": "详细输出会把请求头（含 Cookie）写进日志",
    "dump_intermediate_pages": "会把下载到的页面内容写进日志",
    "write_pages": "会把下载到的页面写成文件",
    "debug_printtraffic": "会把 HTTP 请求头（含 Cookie）写进日志",
    "load_pages": "会读取本地页面文件",
}
# 软件自己决定的字段：用户写了也点名后忽略，不能让他以为生效了
_YDL_ARG_CONFLICT = {
    "format": "格式由首页的清晰度档位决定，指定某条流请用「指定 format_id」",
    "format_sort": "分流的排序由软件按画质与码率固定",
    "windowsfilenames": "文件名里的非法字符由软件统一清理",
    "restrictfilenames": "文件名里的非法字符由软件统一清理",
    "ignoreerrors": "播放列表里个别条目失败时的处理方式由软件控制",
}
# 只能填这几个名字的字段（填路径等于让 yt-dlp 去跑任意程序）
_YDL_ARG_NAMES = {
    "external_downloader": ("native", "aria2c", "axel", "curl", "wget", "ffmpeg", "httpie"),
}
# 值写成 "-" 是要在终端里逐条问人，后台任务会一直等下去
_YDL_ARG_NO_DASH = ("match_filter", "breaking_match_filter")
# 这几个按 dest 分不出来（dest 是 "_" 或 None），只能按命令行写法挡
_YDL_ARG_FORBIDDEN_FLAG = {
    "--alias": "别名会展开成一串参数，请把要用的参数直接写全",
    "-t": "预设方案会连带指定格式，请把要用的参数直接写全",
    "--preset-alias": "预设方案会连带指定格式，请把要用的参数直接写全",
    "--version": "只输出版本号",
}
# 缓存本机 yt-dlp 的参数表与基线差异；yt-dlp 在程序里更新过之后要重算
_YDL_ARG_CACHE = {"ver": None, "table": {}, "base": {}}


def _ydl_arg_table() -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """({命令行写法: Option}, 空跑一遍得到的默认 ydl_opts)，进程内缓存。"""
    try:
        import yt_dlp
        from yt_dlp.version import __version__ as _v
    except Exception:
        return {}, {}
    if _YDL_ARG_CACHE["ver"] != _v:
        try:
            # --ignore-config 让两次调用都不读用户配置文件，做差才干净
            parsed = yt_dlp.parse_options(["--ignore-config"])
            table = dict(getattr(parsed.parser, "_short_opt", {}) or {})
            table.update(dict(getattr(parsed.parser, "_long_opt", {}) or {}))
            _YDL_ARG_CACHE.update({"ver": _v, "table": table, "base": dict(parsed.ydl_opts or {})})
        except Exception:
            _YDL_ARG_CACHE.update({"ver": _v, "table": {}, "base": {}})
    return _YDL_ARG_CACHE["table"], _YDL_ARG_CACHE["base"]


def _split_ydl_args(text: str) -> Tuple[List[str], List[str]]:
    """把一行参数切成 yt-dlp 认识的 argv，危险项与冲突项挑出来写成说明。

    返回 (保留的参数, 说明)。说明只写参数名，不写参数值。
    """
    table, _base = _ydl_arg_table()
    try:
        toks = shlex.split(str(text or "").strip(), posix=True)
    except Exception as e:
        return [], [f"引号没配对，这一串参数一条都没生效（{type(e).__name__}: {str(e)[:60]}）"]
    if not table:
        return [], ["本机导入不了 yt-dlp，没法核对参数，这一串参数一条都没生效"]
    argv: List[str] = []
    notes: List[str] = []
    i = 0
    while i < len(toks):
        tok = toks[i]
        i += 1
        if not tok.startswith("-") or tok in ("-", "--"):
            notes.append(f"「{tok[:40]}」不是参数：这里只写 yt-dlp 的参数，链接请在下载页输入")
            continue
        flag, sep, inline = tok.partition("=")
        opt = table.get(flag)
        if opt is None and flag.startswith("--"):
            # yt-dlp 认不歧义的缩写，这里也跟着认，否则 --no-check-certi 会被当成不认识的参数
            cands = sorted({k for k in table if k.startswith(flag)})
            if len(cands) == 1:
                flag, opt = cands[0], table[cands[0]]
            elif len(cands) > 1:
                notes.append(f"「{tok[:60]}」有多个参数都对得上（{'、'.join(cands[:4])}），请写全，已跳过")
                continue
        if opt is None:
            notes.append(f"「{tok[:60]}」本机 yt-dlp 没有这个参数，已跳过")
            continue
        nval = int(getattr(opt, "nargs", 0) or 0)
        if not nval and getattr(opt, "action", "") in ("store", "append", "callback"):
            nval = 1
        vals: List[str] = []
        if sep:
            if nval > 1:
                notes.append(f"「{flag}」需要 {nval} 个值，不能用 --参数=值 的写法，已跳过")
                continue
            vals = [inline]
        else:
            for _ in range(nval):
                if i < len(toks):
                    vals.append(toks[i])
                    i += 1
        dest = str(getattr(opt, "dest", "") or "")
        reason = _YDL_ARG_FORBIDDEN_FLAG.get(flag) or _YDL_ARG_FORBIDDEN.get(dest)
        if reason:
            notes.append(f"{flag} 已跳过：{reason}")
            continue
        clash = _YDL_ARG_CONFLICT.get(dest)
        if clash:
            notes.append(f"{flag} 已跳过：{clash}")
            continue
        if dest in _YDL_ARG_NO_DASH and any(str(v).strip() == "-" for v in vals):
            notes.append(f"{flag} 已跳过：值写成「-」是要在终端里逐条确认，后台任务会一直等")
            continue
        wl = _YDL_ARG_NAMES.get(dest)
        if wl and any(str(v).rsplit(":", 1)[-1].strip().lower() not in wl for v in vals):
            notes.append(f"{flag} 已跳过：只能填 {'、'.join(wl)} 之一（填程序路径等于让软件去跑任意程序）")
            continue
        argv.append(flag)
        argv.extend(vals)
    return argv, notes


def _ydl_extra_opts(text: str) -> Tuple[Dict[str, Any], List[str]]:
    """算出「用户这串参数相对 yt-dlp 默认值改了什么」。

    返回 (要并进去的差异, 说明)。参数本身校验不过时差异为空，整串不生效，
    免得一半生效留下一份看不出根因的成品。
    """
    argv, notes = _split_ydl_args(text)
    if not argv:
        return {}, notes
    try:
        import yt_dlp
        base = _ydl_arg_table()[1]
        got = dict(yt_dlp.parse_options(["--ignore-config"] + argv).ydl_opts or {})
    except SystemExit:
        return {}, notes + ["这一串里有让 yt-dlp 直接结束的写法，全部没有生效"]
    except Exception as e:
        msg = re.sub(r"\s+", " ", str(e)).strip()[:160]
        return {}, notes + [f"参数校验没通过（{msg}），这一串参数全部没有生效"]
    delta: Dict[str, Any] = {}
    for k, v in got.items():
        # _warnings 是 yt-dlp 内部字段；outtmpl/paths 会被 --embed-thumbnail 这类顺带填上，
        # 而输出位置始终由软件决定
        if k.startswith("_") or k in ("outtmpl", "paths"):
            continue
        try:
            if k not in base or base[k] != v:
                delta[k] = v
        except Exception:
            delta[k] = v
    return delta, notes


def _ydl_merge_extra(opts: dict, delta: Dict[str, Any]) -> List[str]:
    """把差异并进软件已经算好的 ydl_opts：软件没提到的键直接采用，软件也有的键按语义合。"""
    notes: List[str] = []
    for k, v in (delta or {}).items():
        if k == "http_headers" and isinstance(v, dict):
            # 只覆盖用户写到的那几个头：整个字典换掉会把软件放的 UA / Referer / Cookie 抹平
            hdrs = dict(opts.get("http_headers") or {})
            hdrs.update(v)
            opts["http_headers"] = hdrs
        elif k == "extractor_args" and isinstance(v, dict):
            ea = dict(opts.get("extractor_args") or {})
            for ie, args in v.items():
                if isinstance(args, dict):
                    cur = dict(ea.get(ie) or {})
                    cur.update(args)
                    ea[ie] = cur
                else:
                    ea[ie] = args
            opts["extractor_args"] = ea
        elif k == "postprocessors" and isinstance(v, list):
            pps = list(opts.get("postprocessors") or [])
            have = {str(p.get("key") or "") for p in pps if isinstance(p, dict)}
            for p in v:
                key = str((p or {}).get("key") or "")
                if key in have:
                    notes.append(f"{key} 这一步软件已按界面上的勾选做过，用软件的")
                    continue
                pps.append(p)
                have.add(key)
            opts["postprocessors"] = pps
        else:
            opts[k] = v
    return notes


_SPEED_ARROW_RE = re.compile(r"(?:->|=>|→|\s=\s)")
_SPEED_SPAN_RE = re.compile(r"^(\d{1,2}:\d{2})\s*(?:-|–|~|至|到)\s*(\d{1,2}:\d{2})$")


def parse_speed_windows(text: str) -> Tuple[List[Tuple[str, str, str, str]], List[str]]:
    """把「限速时段」那几行收成 [(起, 止, 限速, 说明)]，并逐行给出识别不了的原因。

    一行一条：00:00-08:00 -> 2M。开始晚于结束就按跨零点算（22:00-02:00 是当晚到凌晨）。
    分隔符认 -> / => / → / 空格，限速单位认 M / K / 纯字节数，和 aria2 那套一致。
    """
    out: List[Tuple[str, str, str, str]] = []
    errs: List[str] = []
    for ln, raw in enumerate(str(text or "").splitlines(), 1):
        line = raw.strip().replace("：", ":")
        if not line or line.startswith("#") or line.startswith("//"):
            continue
        m = _SPEED_ARROW_RE.search(line)
        if m:
            span, speed = line[:m.start()].strip(), line[m.end():].strip()
        else:
            parts = line.rsplit(None, 1)
            if len(parts) != 2:
                errs.append(f"第 {ln} 行「{line[:40]}」：缺限速值，要写成 00:00-08:00 -> 2M")
                continue
            span, speed = parts[0], parts[1]
        got = bt_trackers.norm_speed(speed)
        if not got:
            errs.append(f"第 {ln} 行：限速值「{speed[:16]}」看不懂，要写成 1M / 512K / 纯字节数")
            continue
        sm = _SPEED_SPAN_RE.match(span)
        if not sm:
            errs.append(f"第 {ln} 行：时段「{span[:24]}」要写成 08:00-12:00（24 小时制，跨零点照写）")
            continue
        a, b = _hhmm(sm.group(1)), _hhmm(sm.group(2))
        if not a or not b:
            errs.append(f"第 {ln} 行：时段「{span[:24]}」里有不存在的钟点（小时 0–23、分钟 0–59）")
            continue
        out.append((a, b, got.upper(), f"{a}–{b} 限速 {got.upper()}"))
    return out, errs


def resolve_speed_limit(c: dict, now=None) -> Tuple[str, str]:
    """这一趟该用哪档限速：任务级 > 命中的时段 > 全局。返回 (限速串, 说明)，空串表示不限速。"""
    raw_task = str(c.get("speed_limit") or "").strip()
    if raw_task:
        got = bt_trackers.norm_speed(raw_task)
        if got:
            return got.upper(), "任务级限速"
        if bt_trackers.to_bytes(raw_task) == 0:
            return "", "任务级填的是 0，按不限速处理"
        return "", f"任务级限速「{raw_task[:16]}」写法不对，这一趟没限速"
    cur = (now or datetime.now()).strftime("%H:%M")
    for a, b, got, label in parse_speed_windows(c.get("speed_windows") or "")[0]:
        hit = (a <= cur <= b) if a <= b else (cur >= a or cur <= b)
        if hit:
            return got, f"时段{label}"
    got = bt_trackers.norm_speed(c.get("global_speed_limit"))
    if got:
        return got.upper(), "全局限速"
    return "", ""


def _hm_to_min(v: str) -> int:
    return int(str(v)[:2]) * 60 + int(str(v)[3:5])


def _hm_until(target: str, cur: str) -> int:
    """从 cur 到下一个 target 还差几分钟（按 24 小时圈算，结果恒为非负）。"""
    return (_hm_to_min(target) - _hm_to_min(cur)) % 1440


def window_hit(a: str, b: str, cur: str) -> bool:
    """这个时段此刻算不算命中：起 ≤ 止是当天内，反之按跨零点（22:00-06:00 是当晚到凌晨）。"""
    return (a <= cur <= b) if a <= b else (cur >= a or cur <= b)


# 后端自己会往队列里塞的名字：订阅追新走 subscribe（见 7401 那条入队），音乐下载走 music。
# 界面上没有「建队列」这一处，所以校验要拿这三条与设置里那张 named_queues 并起来，
# 只按表校验会把 music 这种正在用着的队列顶回去。
KNOWN_QUEUE_NAMES = {"default", "subscribe", "music"}


def parse_run_windows(text: str) -> Tuple[List[Tuple[str, str]], List[str]]:
    """把「队列定时窗」收成 [(起, 止)]，一行一条：22:00-06:00。

    钟点口径与限速时段同源（同一个 _SPEED_SPAN_RE 与 _hhmm），多带一段 `-> 2M` 也只取前面那半，
    用户从限速那栏照抄过来不会报错。一条都没填 = 不限时段。
    """
    out: List[Tuple[str, str]] = []
    errs: List[str] = []
    for ln, raw in enumerate(str(text or "").splitlines(), 1):
        line = raw.strip().replace("：", ":")
        if not line or line.startswith("#") or line.startswith("//"):
            continue
        span = _SPEED_ARROW_RE.split(line, 1)[0].strip() or line
        m = _SPEED_SPAN_RE.match(span)
        if not m:
            errs.append(f"第 {ln} 行「{line[:32]}」：时段要写成 22:00-06:00（24 小时制，跨零点照写）")
            continue
        a, b = _hhmm(m.group(1)), _hhmm(m.group(2))
        if not a or not b:
            errs.append(f"第 {ln} 行：时段「{span[:24]}」里有不存在的钟点（小时 0–23、分钟 0–59）")
            continue
        if a == b:
            errs.append(f"第 {ln} 行：{a}–{a} 说不上是整圈还是零圈，起与止要写两个不同的钟点")
            continue
        out.append((a, b))
    return out, errs


def window_open(text: str, now=None) -> Tuple[bool, str, str, int]:
    """这一刻能不能开新任务。返回 (能不能跑, 一句说明, 下一次开门的钟点, 还差几分钟)。

    没填时段就是一直能跑 —— 这条默认值必须守住：升级上来的人没配过它，行为要和从前一字不差。
    """
    wins, errs = parse_run_windows(text)
    cur = (now or datetime.now()).strftime("%H:%M")
    warn = ("；没认出来的行：" + "；".join(errs[:2])) if errs else ""
    if not wins:
        return True, "没设定时窗，什么时候都能跑" + warn, "", 0
    for a, b in wins:
        if window_hit(a, b, cur):
            return True, f"现在在运行时段 {a}–{b} 内" + warn, "", 0
    best = min(wins, key=lambda p: _hm_until(p[0], cur))
    left = _hm_until(best[0], cur)
    return False, f"现在不在运行时段（{'、'.join(f'{a}–{b}' for a, b in wins)}）" + warn, best[0], left


_COOKIE_HELP_KINDS = (risk_control.LOGIN_REQUIRED, risk_control.DENIED, risk_control.BOT_CHALLENGE)
# 风控那套规则没覆盖到、却正是「登录 / 会员 / 年龄」墙的原文，单独兜住：
# YouTube 的年龄门与「Sign in to confirm you're not a bot」都落在 classify 的 UNKNOWN 里，
# 而它们恰是最该带 Cookie 再试一次的两种情况。
_COOKIE_HELP_RE = re.compile(
    r"age[- ]?restrict|confirm your age|sign in to (?:confirm|continue|download)|"
    r"login required|members? only|premium|subscription required|"
    r"需要登录|请先登录|仅限会员|大会员|需要会员",
    re.I,
)


def cookie_might_help(text, url: str = "") -> bool:
    """匿名解析失败那句原始报错，值不值得带 Cookie 再打一次平台接口。

    限流与网络错明确不给重跑：多打一次只会把 429 的冷却拉长，也不会让链路通。
    内容不存在同理 —— 带不带 Cookie 它都不在。
    YouTube 那一支要多看一眼：活体读数里，这台机器匿名打开公开视频回的是「一条流都不给」
    （No video formats found），带 Cookie 那份却有 43 条流到 2160p。那种形状落在 UNKNOWN 里，
    按「只认登录墙那几句话」就会把整条链接判死，所以 YouTube 的「整条解不开」也算值得再打一次。
    """
    raw = str(text or "")
    if not raw.strip():
        return False
    try:
        kind = str(risk_control.classify_failure_text(raw).get("kind") or "")
    except Exception:
        kind = ""
    if kind in (risk_control.RATE_LIMITED, risk_control.NETWORK, risk_control.NOT_FOUND):
        return False
    if kind in _COOKIE_HELP_KINDS:
        return True
    if _COOKIE_HELP_RE.search(raw):
        return True
    # 风控那套话术对不上、又没被明确排除：YouTube 上认「没给清单」这一种，别的平台不猜
    if kind in (risk_control.UNKNOWN, risk_control.EMPTY):
        try:
            return detect_platform(url or "") == "youtube"
        except Exception:
            return False
    return False


def cfg_without_cookie(cfg: dict) -> dict:
    """把所有 Cookie 入口都关掉的那份配置副本（公开优先的第一次尝试用的就是它）。

    三条都得清干净：全局来源、逐平台覆写、以及手工粘进请求头的那串 —— 少清一条就还是带了 Cookie，
    那这一次「匿名先试」就成了假的那次，缓存与日志都会照着它编。
    """
    out = dict(cfg or {})
    out["cookie_source"] = "none"
    out["cookie_browser"] = ""
    out["cookie_file"] = ""
    out["platform_cookies"] = {}
    out["cookie"] = ""
    hdrs = dict(out.get("http_headers") or {})
    for k in [k for k in hdrs if str(k).strip().lower() == "cookie"]:
        hdrs.pop(k, None)
    out["http_headers"] = hdrs
    return out


# 「人动了 Cookie 这一层」的键：只要这几个变了，之前那次「这条匿名就够」的判定就该作废
COOKIE_LAYER_KEYS = ("cookie_source", "cookie_browser", "cookie_file",
                     "platform_cookies", "cookie", "cookie_public_first")


def drop_all_cookie_prefs():
    """Cookie 这一层刚被人改过：把所有「匿名够用 / 得带 Cookie」的判定一次清掉。

    不清的后果是配好了 Cookie 却还是不登录 —— 那条 15 分钟内的旧结论会把新 Cookie 又关掉。
    清了的代价只是下一条链接重新匿名试一次，一边是错、一边是多打一次，选后面那个。
    """
    try:
        engine.drop_cookie_pref()
    except Exception:
        pass


class DownloaderEngine:
    def __init__(self, log_cb=None, ffmpeg_mgr: FFmpegManager = None):
        self.log = log_cb or (lambda m, level="info", k="", kv=None: print(m))
        self.ffmpeg = ffmpeg_mgr or FFmpegManager()
        self._stop_flags: Dict[str, bool] = {}
        # 直播这一场真正落盘的文件名主干：结束录制时要靠它点名找回 yt-dlp 派出去的拉流子进程
        self._live_stems: Dict[str, str] = {}
        # download() 只返回 (ok, path)，失败原因先按任务暂存在这里，交给队列写进任务卡
        self._err_notes: Dict[str, str] = {}
        self.max_retries = 3
        self.base_delay = 30  # 429 指数退避基数（秒）
        self.backoff_max = 600
        self.backoff_jitter = 0.25

    def note_error(self, task_id: str, msg: str):
        clean = re.sub(r"\x1b\[[0-9;]*m", "", str(msg or "")).strip()
        if clean and task_id:
            self._err_notes[task_id] = clean[:600]

    def pop_error(self, task_id: str) -> str:
        return self._err_notes.pop(task_id or "", "")

    def check_ytdlp(self) -> str:
        _prefer_local_ytdlp()
        try:
            import yt_dlp
            ver = getattr(yt_dlp.version, "__version__", None) or getattr(yt_dlp, "version", None)
            if callable(ver):
                ver = ver()
            if not ver:
                from yt_dlp.version import __version__ as ver
            # 探测是否真有 youtube 提取器
            try:
                from yt_dlp.extractor import gen_extractor_classes
                names = {c.IE_NAME for c in gen_extractor_classes() if getattr(c, "IE_NAME", None)}
                if "youtube" not in names and "Youtube" not in names:
                    note = " (extractors incomplete!)"
                    if YTDLP_LOCAL_PKG.is_dir():
                        note = " (local broken)"
                    return f"{ver}{note}"
            except Exception:
                pass
            note = " (local)" if _local_ytdlp_ok() else ""
            return f"{ver}{note}"
        except Exception:
            try:
                _prefer_local_ytdlp(force_clear=True)
                from yt_dlp.version import __version__
                return f"{__version__} (pip)"
            except Exception:
                return "not found"

    def update_ytdlp(self) -> str:
        self.log(f"yt-dlp 更新 → {TOOLS_DIR}", k="srv.engine.ytdlp_update", kv={"dir": str(TOOLS_DIR)})
        gh = ""
        idx = ""
        try:
            gh = str(cfg.data.get("github_mirror") or "")
            idx = str(cfg.data.get("pip_mirror") or "")
        except Exception:
            pass
        try:
            exe_urls = pkg_update.github_url_candidates(YTDLP_EXE_URL, gh)
            src_urls = pkg_update.github_url_candidates(YTDLP_SRC_ZIP_URL, gh)
            # 真正被 import 的是下面解出来的 tools/yt_dlp 源码包；yt-dlp.exe 只是 Windows 命令行壳，
            # 在 Linux/macOS 上下回来既跑不了也没人调用，白占十几 MB。
            if sys.platform == "win32":
                _download_with_mirrors(exe_urls, YTDLP_LOCAL_EXE, log=self.log, timeout=180)
            _download_with_mirrors(src_urls, TOOLS_DIR / "yt_dlp_src.zip", log=self.log, timeout=300)
            tmp_zip = TOOLS_DIR / "yt_dlp_src.zip"
            if YTDLP_LOCAL_PKG.exists():
                shutil.rmtree(YTDLP_LOCAL_PKG, ignore_errors=True)
            with zipfile.ZipFile(tmp_zip, "r") as zf:
                for name in zf.namelist():
                    if "/yt_dlp/" not in name.replace("\\", "/"):
                        continue
                    parts = Path(name).parts
                    try:
                        idx2 = parts.index("yt_dlp")
                    except ValueError:
                        continue
                    rel = Path(*parts[idx2:])
                    dest = TOOLS_DIR / rel
                    if name.endswith("/"):
                        dest.mkdir(parents=True, exist_ok=True)
                    else:
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        with zf.open(name) as src, open(dest, "wb") as dst:
                            shutil.copyfileobj(src, dst)
            tmp_zip.unlink(missing_ok=True)
            _prefer_local_ytdlp()
            ver = self.check_ytdlp()
            self.log(f"yt-dlp 已就绪: {ver}", k="srv.engine.ytdlp_ready", kv={"ver": ver})
            return "updated"
        except Exception as e:
            self.log(f"yt-dlp 直连/镜像下载都失败: {e}，改用 pip 更新", "warning",
                     k="srv.engine.ytdlp_all_failed", kv={"e": str(e)})
            ok, res = pkg_update.pip_install(["yt-dlp"], log=self.log, mirror=idx)
            if ok:
                _prefer_local_ytdlp(force_clear=True)
                return "updated (pip)"
            return str(res)

    def cookie_pref_state(self, cfg: dict, url: str = "") -> str:
        """这条 URL 在「公开优先」下判过没有："" 没判 / "anon" 匿名就能开 / "cookie" 得带 Cookie。

        判过一次就记在 `_cookie_pref` 里，解析、下载、CDN 直链请求头三处都问这里，
        免得各自读一遍开关读出三种结果。开关关着或过期时回 ""：那时行为与从前一字不差。
        """
        if not cfg or not cfg.get("cookie_public_first") or not url:
            return ""
        try:
            rec = self._cookie_pref.get(url)
        except Exception:
            return ""
        if not rec:
            return ""
        try:
            stamp, use_cookie = rec
        except Exception:
            return ""
        if time.time() - float(stamp) > self._COOKIE_PREF_TTL:
            try:
                self._cookie_pref.pop(url, None)
            except Exception:
                pass
            return ""
        return "cookie" if use_cookie else "anon"

    def cookie_off(self, cfg: dict, url: str = "") -> bool:
        """这一条是不是已经判过「匿名就能开」—— 所有该不带 Cookie 的地方都问这一个问题。"""
        return self.cookie_pref_state(cfg, url) == "anon"

    def note_cookie_pref(self, url: str, use_cookie: bool):
        """记下「这条 URL 匿名解析开了 / 得带 Cookie」，过期与取用都走 cookie_pref_state。"""
        try:
            self._cookie_pref[url] = (time.time(), bool(use_cookie))
        except Exception:
            pass

    def drop_cookie_pref(self, url: str = ""):
        """作废一条（或全部）判定：Cookie 这一层被人改过，旧的结论就不能再替它决定带不带。"""
        try:
            if not url:
                self._cookie_pref.clear()
                return
            for k in {url, normalize_url(url)}:
                self._cookie_pref.pop(k, None)
        except Exception:
            pass

    def _cookie_source(self, cfg: dict, url: str = "") -> tuple:
        """该 URL 实际能用的 Cookie：("browser", 浏览器名) / ("file", 路径) / (None, None)。
        只选了来源但文件不存在时算「没有 Cookie」。"""
        # 公开优先判过「这条匿名就能开」之后，这里就是唯一出口：客户端链、下载、直链请求头
        # 全都跟着不带 Cookie，不需要各自再抄一遍判断。
        if self.cookie_off(cfg, url):
            return None, None
        plat = detect_platform(url) if url else "default"
        pc = (cfg.get("platform_cookies") or {}).get(plat) or {}
        src = (pc.get("source") or cfg.get("cookie_source") or "none").strip().lower()
        if src == "browser":
            return "browser", (pc.get("browser") or cfg.get("cookie_browser") or "chrome").strip().lower()
        if src == "file":
            f = (pc.get("file") or cfg.get("cookie_file") or "").strip()
            if not f:
                f = str(platform_cookie_path(plat))
            if f and Path(f).exists():
                return "file", f
        return None, None

    def _yt_player_chain(self, cfg: dict, url: str = "") -> Tuple[List[str], str]:
        """YouTube player_client 回退链：按设置顺序，Cookie/PO 健康度会剪掉注定失败的客户端。"""
        raw = str(cfg.get("yt_player_clients") or "default,web_safari,android,ios,tv")
        chain = [x.strip().lower() for x in re.split(r"[,\n/]| +", raw) if x.strip()]
        chain = list(dict.fromkeys(chain)) or ["default"]
        notes = []
        if self._cookie_source(cfg, url)[0]:
            kept = [c for c in chain if c not in ("android", "ios")]
            if kept and len(kept) != len(chain):
                notes.append("带 Cookie，已跳过 android/ios")
            chain = kept or ["default"]
        po_on = bool(cfg.get("po_provider_enabled"))
        if po_on and not po_token_health(cfg_override=cfg)["ok"]:
            kept = [c for c in chain if c not in PO_ONLY_CLIENTS]
            if kept and len(kept) != len(chain):
                notes.append("PO Token 服务未响应，已跳过 " + "/".join(PO_ONLY_CLIENTS))
            chain = kept or chain
        return chain, "；".join(notes)

    def _log_proxy_decision(self, task_id: str, url: str, cfg: dict):
        key = proxy_platform_key(url)
        ov = (cfg.get("proxy_by_platform") or {}).get(key)
        mode, px = proxy_decision(url, cfg_data=cfg)
        tp = task_proxy_override(cfg)
        txt = f"任务指定 {tp}" if tp else ({"proxy": f"走 {px}", "direct": "强制直连"}.get(mode) or "跟随系统")
        self.log(
            f"[{task_id[:8]}] 代理: {txt}"
            f"（{key}，{'手动覆写' if isinstance(ov, bool) else cfg.get('proxy_mode') or 'auto'}）"
        )

    def _ydl_opts(self, cfg: dict, *, for_info: bool = False, player_clients=None, url: str = "") -> dict:
        opts: dict = {
            "quiet": True,
            "no_warnings": True,
            "noprogress": for_info,
            "noplaylist": for_info,
            "ignore_no_formats_error": True,
            "skip_download": for_info,
            "socket_timeout": 30,
            "retries": 3,
            "fragment_retries": 3,
            "extractor_retries": 3,
        }
        # SSL：国内 CDN Hostname mismatch 极常见，默认跳过证书校验
        # （含 live.bilibili 实际拉到 bytefcdn 等节点）
        if cfg.get("nocheckcertificate", True) is not False:
            opts["nocheckcertificate"] = True
            try:
                opts["legacy_server_connect"] = True
            except Exception:
                pass
            # 全局放宽 Python SSL（yt-dlp/urllib 均受益）
            try:
                import ssl as _ssl
                _ssl._create_default_https_context = _ssl._create_unverified_context
            except Exception:
                pass
        # 风控 UA + 任务级 http_headers（中途可改）
        hdrs = dict(cfg.get("http_headers") or {})
        ua = (cfg.get("risk_user_agent") or cfg.get("user_agent") or "").strip()
        if ua and "User-Agent" not in hdrs:
            hdrs["User-Agent"] = ua
        if cfg.get("referer") and "Referer" not in hdrs:
            hdrs["Referer"] = cfg.get("referer")
        # 手工粘的那串 Cookie 也是 Cookie：判过「这条匿名就能开」之后不能只挡 cookiefile 那两路
        if cfg.get("cookie") and "Cookie" not in hdrs and not self.cookie_off(cfg, url):
            hdrs["Cookie"] = cfg.get("cookie")
        if hdrs:
            opts["http_headers"] = hdrs
        # 多平台 Cookie：按 URL 域名优先
        ck_kind, ck_val = self._cookie_source(cfg, url)
        if player_clients is None and not ck_kind:
            player_clients, _note = self._yt_player_chain(cfg, url)
            player_clients = player_clients[:1]
        if player_clients is not None:
            ea = dict(opts.get("extractor_args") or {})
            yt = dict(ea.get("youtube") or {})
            yt["player_client"] = list(player_clients)
            ea["youtube"] = yt
            opts["extractor_args"] = ea
        ffdir = self.ffmpeg.location_for_ytdlp()
        if ffdir:
            opts["ffmpeg_location"] = ffdir
        # 代理：任务级覆写最优先，其次按平台策略（ydl_proxy_opt 返回 "" 是 yt-dlp 的强制直连
        # 语义，None 才是不干预）
        tp = task_proxy_override(cfg)
        px = tp or ydl_proxy_opt(url)
        if px is not None:
            opts["proxy"] = px
        if ck_kind == "browser":
            opts["cookiesfrombrowser"] = (ck_val, None, None, None)
        elif ck_kind == "file":
            opts["cookiefile"] = ck_val
        extra_args = str(cfg.get("ytdlp_extra_args") or "").strip()
        if for_info:
            # 解析阶段也把参数用上，「解析看到的」和「下载做到的」才是同一套设置；
            # 说明文字只在下载任务里打，免得每解析一次就刷一遍日志
            if extra_args:
                _ydl_merge_extra(opts, _ydl_extra_opts(extra_args)[0])
            return opts
        # 是否下载播放列表（默认否：只下单条）
        opts["noplaylist"] = not bool(cfg.get("allow_playlist", False))
        # 播放列表区间（lux 风格 start/end/items）
        try:
            ps = int(cfg.get("playlist_start") or 0)
            if ps > 0:
                opts["playliststart"] = ps
                opts["noplaylist"] = False
        except Exception:
            pass
        try:
            pe = int(cfg.get("playlist_end") or 0)
            if pe > 0:
                opts["playlistend"] = pe
                opts["noplaylist"] = False
        except Exception:
            pass
        items = (cfg.get("playlist_items") or "").strip()
        if items:
            opts["playlist_items"] = items
            opts["noplaylist"] = False
        opts["updatetime"] = False
        # 限速：任务级 > 命中的时段 > 全局。ratelimit 是任务建立时定下的，跑到一半不回头改档
        sl, _sl_note = resolve_speed_limit(cfg)
        if sl:
            nbytes = bt_trackers.to_bytes(sl)
            if nbytes > 0:
                opts["ratelimit"] = nbytes
        # 写出描述 / info.json
        if cfg.get("write_description"):
            opts["writedescription"] = True
        if cfg.get("write_info_json"):
            opts["writeinfojson"] = True
        # 跳过已下载（MediaSync 同类能力）
        if cfg.get("skip_downloaded", True):
            arch = Path(cfg.get("download_dir") or DEFAULT_DOWNLOAD_DIR) / "download_archive.txt"
            try:
                arch.parent.mkdir(parents=True, exist_ok=True)
                opts["download_archive"] = str(arch)
            except Exception:
                pass
        # 嵌入类选项：embedthumbnail / embedmetadata / sponsorblock_remove 这些名字只是
        # 命令行参数，CLI 层会把它们翻译成 postprocessors 再交给 YoutubeDL；当 params 直接
        # 传进去没人读，所以必须走 postprocessors，否则「嵌入…」全是空操作。
        pps: List[Dict[str, Any]] = []
        sb = (cfg.get("sponsorblock") or "off").strip().lower()
        if sb in ("remove", "mark"):
            sb_cats = set(SB_CATEGORIES.split(","))
            pps.append({"key": "SponsorBlock", "categories": sb_cats, "when": "after_filter"})
            pps.append({
                "key": "ModifyChapters",
                "remove_sponsor_segments": sb_cats if sb == "remove" else set(),
            })
        if cfg.get("embed_meta", True) or cfg.get("embed_chapters", True):
            pps.append({
                "key": "FFmpegMetadata",
                "add_metadata": bool(cfg.get("embed_meta", True)),
                "add_chapters": bool(cfg.get("embed_chapters", True)),
            })
        # EmbedThumbnailPP 只负责「把已落到磁盘的缩略图塞进容器」；缩略图没人下载时
        # 它只会说一句 "There are no thumbnails on disk" 就静默跳过。CLI 的
        # --embed-thumbnail 会顺手打开 writethumbnail，直传 params 时得自己做。
        if cfg.get("embed_thumb", True):
            opts["writethumbnail"] = True
            pps.append({"key": "EmbedThumbnail", "already_have_thumbnail": False})
        if pps:
            opts["postprocessors"] = pps
        # 自定义参数最后并入：软件没写过的键直接采用，写过的按上面的口径合
        if extra_args:
            _delta, _notes = _ydl_extra_opts(extra_args)
            for _n in _notes + _ydl_merge_extra(opts, _delta):
                self.log(f"自定义 yt-dlp 参数：{_n}", "warning",
                         k="srv.download.ytdlp_args", kv={"note": _n})
            if _delta:
                _ks = sorted(_delta)
                # 省略号折进名单本身：句子里只留两个洞，模板才钉得住（三个洞配两个 kv，K3 红）
                _shown = '、'.join(_ks[:6]) + ('…' if len(_ks) > 6 else '')
                self.log(f"自定义 yt-dlp 参数：已并入 {len(_ks)} 项（{_shown}）",
                         k="srv.engine.ytdlp_args_merged",
                         kv={"n": len(_ks), "list": _shown})
        return opts

    @staticmethod
    def _resolve_format(media, video_q, audio_q, audio_only, prefer_codec: str = "auto"):
        """
        生成 yt-dlp format 选择串。
        注意：YouTube 上仅返回 progressive（如 format 18=360p）时，不能直接用 format_id，
        必须用 bv*+ba 表达式让 yt-dlp 再协商自适应流，否则会一直下到 360p。
        """
        audio_cap = {"320k": 320, "256k": 256, "192k": 192, "128k": 128}.get(audio_q)
        pref = (prefer_codec or "auto").lower()
        if pref == "avc":
            codec_f = "[vcodec^=avc1][vcodec^=avc]"
            # yt-dlp 过滤器用 / 串联备选
            vcodec_pref = "[vcodec^=avc1]/[vcodec*=avc]"
        elif pref == "vp9":
            vcodec_pref = "[vcodec*=vp9]/[vcodec*=vp09]"
        elif pref == "av1":
            vcodec_pref = "[vcodec*=av01]/[vcodec*=av1]"
        else:
            vcodec_pref = ""

        if audio_only:
            if audio_cap:
                return f"ba[abr<={audio_cap}]/bestaudio/best"
            return "bestaudio/best"

        max_h = quality_height_cap(video_q)

        # 检查列表里是否有真正的「分离视频流」（非 progressive）
        separate_vids = [
            f for f in (media or [])
            if f.get("vcodec") and f.get("vcodec") != "none"
            and (not f.get("acodec") or f.get("acodec") == "none")
            and (f.get("height") or 0) > 0
        ]
        best_listed_h = max((f.get("height") or 0 for f in separate_vids), default=0)

        # 列表只有低清 progressive（常见于客户端受限只返回 format 18）时，强制用表达式
        use_expr = True
        if separate_vids and best_listed_h >= (max_h or 1080):
            # 列表足够完整时，可精确拼 format_id
            vids = separate_vids
            if max_h:
                vids = [f for f in vids if (f.get("height") or 0) <= max_h] or vids
            if vcodec_pref:
                keys = {"avc": ("avc", "h264", "avc1"), "vp9": ("vp9", "vp09"), "av1": ("av01", "av1")}.get(pref, ())
                filtered = [f for f in vids if any(k in (f.get("vcodec") or "").lower() for k in keys)]
                if filtered:
                    vids = filtered
            auds = [
                f for f in (media or [])
                if f.get("acodec") and f.get("acodec") != "none"
                and (not f.get("vcodec") or f.get("vcodec") == "none")
            ]
            if audio_cap:
                capped = [f for f in auds if (f.get("abr") or f.get("tbr") or 9999) <= audio_cap]
                if capped:
                    auds = capped
            if vids and auds:
                v0 = sorted(vids, key=lambda f: (f.get("height") or 0, f.get("tbr") or 0), reverse=True)[0]
                a0 = sorted(auds, key=lambda f: f.get("abr") or f.get("tbr") or 0, reverse=True)[0]
                return f"{v0['format_id']}+{a0['format_id']}"

        # 默认：可靠的 format 表达式（避免锁死在 360p progressive）
        # 音频档位在这里也要生效：以前只有「列表完整到能点名 format_id」那一支认 audio_cap，
        # 走表达式时用户选的 128k/192k 被无声丢掉，等于只下最高码率音频。
        # 带码率上限的候选后面紧跟一条不带上限的同形状候选，源里没有那一档时 yt-dlp 顺 / 回退，
        # 不至于整个任务无解。
        def _vplus(vf: str, hcap) -> str:
            h = f"[height<={hcap}]" if hcap else ""
            one = f"bv*{vf}{h}+ba"
            return f"{one}[abr<={audio_cap}]/{one}" if audio_cap else one

        # 编解码偏好本身是 "[vcodec*=av01]/[vcodec*=av1]" 这种 / 串联的备选，直接拼进
        # bv*[...][height<=2160] 里，那个高度上限就只挂在最后一个备选上：
        # 第一个备选 bv*[vcodec*=av01] 变成「不限高度」，选 4K 实际下成 8K（10-13 实测，519.8 MB）。
        # 所以每个备选都得各自带上上限，不能整串塞进去。
        codec_alts = [c for c in (vcodec_pref.split("/") if vcodec_pref else []) if c]
        if max_h:
            parts = [_vplus(c, max_h) for c in codec_alts] + [_vplus("", max_h)]
            parts += [f"b[height<={max_h}]", "bv*+ba/b"]
            return "/".join(parts)
        parts = [_vplus(c, 0) for c in codec_alts] + [_vplus("", 0), "b"]
        return "/".join(parts)

    # 解析结果短缓存，避免重复点「解析」反复打平台
    _info_cache: Dict[str, tuple] = {}
    _INFO_CACHE_TTL = 180  # 秒

    # 「公开优先」判过的 URL → (时间, 这次要不要带 Cookie)。判一次管一阵：
    # 每条新解析都先匿名试一遍意味着同一个登录墙视频要被打两次平台接口，
    # 而 429 的账是按域名累计的，多出来的那次没有换来任何东西。
    # TTL 比解析缓存长一倍：下载本身可能跑十几分钟，中途重解析（清缓存那条路）还得沿用同一次判定。
    _cookie_pref: Dict[str, tuple] = {}
    _COOKIE_PREF_TTL = 900  # 秒

    # 本次下载「解析清单里最高的那条视频轨」，交给队列收尾做成品回读比对。
    # 不塞进 _info_cache 是因为那一份 180 秒就过期，而下载本身可能跑十几分钟：
    # 收尾再去读缓存多半已经没了，就永远判不出「清单里有 4K、成品却只有 1080p」这一类偏差。
    _listed_max: Dict[str, int] = {}

    # 这一单是不是走了「原样落盘」那几条路（CDN 直链绕过 yt-dlp、种子由 aria2 直接写文件）。
    # 校验值核对要用它：走这两条路时成品就是上游那份字节，期望值对不上是真对不上；
    # 而解析下载那侧还要转封装、嵌字幕，成品字节被本机重写过，不能混成一句「下载坏了」。
    # 记在引擎侧而不是让收尾去猜 URL：判断「算不算直链」的口径只在这里有一份。
    _raw_bytes: Dict[str, bool] = {}

    def note_raw_bytes(self, task_id: str):
        try:
            self._raw_bytes[task_id] = True
        except Exception:
            pass

    def pop_raw_bytes(self, task_id: str) -> bool:
        """取走并清掉「这单原样落盘」的标记，和 pop_listed_max 同一口径：不留残值给下一个任务。"""
        try:
            return bool(self._raw_bytes.pop(task_id, False))
        except Exception:
            return False

    def pop_listed_max(self, task_id: str) -> int:
        """取走并清掉该任务清单里的最高视频轨高度。0 = 没预解析到（直播或解析失败）。"""
        try:
            return int(self._listed_max.pop(task_id, 0) or 0)
        except Exception:
            return 0

    def get_info(self, url: str, cfg: dict) -> Optional[Dict]:
        """解析一条 URL：查缓存、展开短链，然后按「公开优先」决定要不要先匿名试一次。

        开关关着时这条路就是原样一次 `_get_info_once`，一字不差。开着且这条确有 Cookie 可用时，
        第一次不带 Cookie：公开能拿到的东西没必要把登录态发给平台，何况带 Cookie 会被 yt-dlp
        剪掉 android/ios 那两个客户端（两条链本来就不是同一份清单）。代价是登录墙的视频要多打
        一次接口，所以判过一次就记下来（`_cookie_pref`），而且只在那类「带 Cookie 才可能有救」的
        失败上才重跑 —— 429 与网络错重跑没有意义，只会把冷却加长。
        """
        import time as _time

        url = normalize_url(url)
        cache_key = url
        now = _time.time()
        cached = self._info_cache.get(cache_key)
        if cached and now - cached[0] < self._INFO_CACHE_TTL:
            return cached[1]

        # 抖音/TikTok 短链展开（限制超时）—— 两次尝试用的是同一份展开结果
        try:
            if any(x in url.lower() for x in ("v.douyin.com", "v.kuaishou.com", "vm.tiktok.com")):
                kw = {"timeout": 8, "allow_redirects": True, "headers": {"User-Agent": _BILI_HEADERS["User-Agent"]}}
                pr = http_proxies(url, task_proxy_override(cfg))
                if pr:
                    kw["proxies"] = pr
                r = requests.get(url, **kw)
                if r.url:
                    url = normalize_url(r.url)
        except Exception:
            pass

        state = self.cookie_pref_state(cfg, url)
        if state == "cookie":
            # 上次判过「这条得带 Cookie」：不再重跑匿名那次。多打一次平台接口只会加长 429 的冷却
            info, _err = self._get_info_once(url, cfg, cache_key, now)
            return info
        if not cfg.get("cookie_public_first") or not self._cookie_source(cfg, url)[0]:
            # 开关关着 / 这条本来就没 Cookie 可用 —— 与从前同一条路，一次到底。
            # 判过「匿名就能开」的也落在这里：`_cookie_source` 已经把 Cookie 收起来了。
            info, _err = self._get_info_once(url, cfg, cache_key, now)
            return info

        # 短链展开过一次之后，下载那侧用的仍是用户输入的那条，两张 key 都记上才拦得住 Cookie
        def _note(use_ck: bool):
            self.note_cookie_pref(url, use_ck)
            if cache_key != url:
                self.note_cookie_pref(cache_key, use_ck)

        anon, anon_err = self._get_info_once(url, cfg_without_cookie(cfg), cache_key, now)
        if anon is not None and not _anon_list_clipped(anon, url):
            _note(False)
            self.log(f"公开优先：这条没带 Cookie 就解析开了（{len(anon.get('formats') or [])} 条流）",
                     k="srv.engine.public_first_anon_ok",
                     kv={"n": len(anon.get("formats") or [])})
            return anon
        if anon is None and not cookie_might_help(anon_err, url):
            # 限流、网络错、内容不存在：带 Cookie 再打一次不改变任何东西
            self.log("公开优先：匿名那一次失败的原因不是登录墙那类，不为此带 Cookie 重跑", "warning",
                     k="srv.engine.public_first_not_login_wall")
            return None
        _note(True)
        # 条件式句子拆成两处调用：拼在句中间的中文片段键化不了，落盘的中文原话必须逐字不变
        if anon is not None:
            self.log("公开优先：匿名那份清单被裁了（只有影音同条），带 Cookie 再解析一次", "warning",
                     k="srv.engine.public_first_clipped")
        else:
            self.log("公开优先：匿名那一次被挡，带 Cookie 再解析一次", "warning",
                     k="srv.engine.public_first_blocked")
        got, got_err = self._get_info_once(url, cfg, cache_key, now)
        if got is None:
            if anon is not None:
                # 带 Cookie 那次反而没解析开（活体读数里就是那次的 429）：先吃已经拿到的匿名那份。
                # 判定仍记「得带 Cookie」—— 能走到这里说明匿名那份是被裁的那份，把它钉成「匿名就够了」
                # 等于接下来 15 分钟都照着 1080p 的清单下，那正是这个开关要防的静默降质。
                self.log(f"带 Cookie 那次没解析开（{str(got_err)[:80]}），先用匿名那份；"
                         f"这条下次解析还带 Cookie", "warning",
                         k="srv.engine.cookie_failed_use_anon", kv={"e": str(got_err)[:80]})
                return anon
            return None
        if anon is not None and _yt_max_h(anon.get("formats") or []) > _yt_max_h(got.get("formats") or []):
            self.log("带 Cookie 那份反而更低，用匿名那份", "warning",
                     k="srv.engine.cookie_rower_than_anon")
            _note(False)
            # 缓存位上此时是带 Cookie 那次写进去的较低那份，跟着结论一起改回来
            self._info_cache[cache_key] = (now, anon)
            return anon
        return got

    def _get_info_once(self, url: str, cfg: dict, cache_key: str, now: float) -> Tuple[Optional[Dict], str]:
        """打一次平台接口拿清单，回 (清单或 None, 最后一次原始报错)。

        `url` 已规范化并展开过短链；`cache_key` / `now` 由调用方给，因为公开优先那两次尝试
        共用的是一条 URL 的缓存位（判过就不该再换 key，否则匿名那份低清会被当答案缓存 180 秒）。
        """
        import yt_dlp

        low = url.lower()
        is_youtube = any(x in low for x in ("youtube.com", "youtu.be", "youtube-nocookie.com"))
        is_bili = "bilibili.com" in low or "b23.tv" in low
        # YouTube 才多客户端；其它平台一次即可（失败再补 1 次）
        if is_youtube:
            # 带 Cookie 时 yt-dlp 会跳过 android/ios（这两个客户端不支持 Cookie）。
            # default 给完整 DASH（可到 4K，且带 filesize）；web_safari 给 HLS，
            # 部分被限制的视频只从 HLS 吐高清。两者一次取并集最稳。
            yt_has_ck = bool(self._cookie_source(cfg, url)[0])
            first = ["default", "web_safari"]
            widen = _yt_widen_attempt(cfg)
            if yt_has_ck:
                client_tries = [first] + widen + [None]
            else:
                client_tries = [first, ["android", "web"], ["ios", "web"]] + widen + [None]
        else:
            client_tries = [None]

        last_err = None
        used_fallback_pip = False
        # 这一轮试到底也没拿到分流清单时用的那份「能用但被裁」的信息。
        # 放在 get_info 的局部而不是 self 上：同时解析两个链接时不该互相盖掉
        fb_box = [None]

        def _keep_best(info):
            cur = fb_box[0]
            if cur is None or _yt_max_h(info.get("formats") or []) > _yt_max_h(cur.get("formats") or []):
                fb_box[0] = info

        def _run_tries():
            nonlocal last_err
            import yt_dlp

            for ci, clients in enumerate(client_tries):
                # 后面还排着「会吃票」的那次尝试吗？还排着，这份没有独立视频轨的清单就不算数
                widen_pending = is_youtube and any(
                    c == YT_WIDE_CLIENTS for c in client_tries[ci + 1:] if c
                )
                try:
                    opts = self._ydl_opts(cfg, for_info=True, player_clients=clients, url=url)
                    opts.pop("format", None)
                    opts["socket_timeout"] = 12
                    opts["retries"] = 1
                    opts["fragment_retries"] = 1
                    opts["extractor_retries"] = 1
                    opts["skip_download"] = True
                    opts["extract_flat"] = "in_playlist"
                    opts["writesubtitles"] = False
                    opts["writeautomaticsub"] = False
                    opts["ignoreerrors"] = True
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        info = ydl.extract_info(url, download=False)
                        if not info:
                            continue
                        if info.get("_type") == "playlist" or "entries" in info:
                            entries = [e for e in (info.get("entries") or []) if e]
                            # 空列表时再试一次非 flat
                            if not entries:
                                try:
                                    opts2 = dict(opts)
                                    opts2["extract_flat"] = False
                                    opts2["playlistend"] = 100
                                    with yt_dlp.YoutubeDL(opts2) as ydl2:
                                        info2 = ydl2.extract_info(url, download=False)
                                    if info2:
                                        entries = [e for e in (info2.get("entries") or []) if e]
                                        info = info2
                                except Exception as _:
                                    pass
                            result = {
                                "_type": "playlist",
                                "title": info.get("title") or "Playlist",
                                "uploader": info.get("uploader") or info.get("channel") or "",
                                "webpage_url": info.get("webpage_url") or url,
                                "thumbnail": info.get("thumbnail") or "",
                                "entries": entries,
                                "_md_clients": clients,
                            }
                            self._info_cache[cache_key] = (now, result)
                            return result
                        fmts = info.get("formats") or []
                        if is_youtube and not fmts:
                            last_err = "No video formats found"
                            self.log(f"客户端 {clients} 无格式，尝试下一个", "warning",
                                     k="srv.engine.client_no_formats", kv={"clients": clients})
                            continue
                        # YouTube：评估最高可用高度（兼容 height 缺失、仅有 resolution 的情况）
                        if is_youtube and fmts:
                            def _h(ff):
                                h = ff.get("height") or 0
                                if h:
                                    return int(h)
                                res = str(ff.get("resolution") or "")
                                m = re.search(r"(\d{3,4})", res)
                                return int(m.group(1)) if m else 0

                            sep_h = 0
                            any_h = 0
                            for f in fmts:
                                vc = (f.get("vcodec") or "none")
                                ac = (f.get("acodec") or "none")
                                hh = _h(f)
                                any_h = max(any_h, hh)
                                # 分离视频流，或带高度的视频轨
                                if vc != "none" and (ac == "none" or hh >= 720):
                                    sep_h = max(sep_h, hh)
                            # 只有确实「什么高清都没有」才换客户端；不要误杀 1080 列表
                            if any_h >= 720 or sep_h >= 480:
                                info["_md_clients"] = clients
                                # 拿得到票却全是影音同条 = 客户端选错（default/web_safari 不吃票），
                                # 不是站点不给高清。留着这份兜底，先让后面那次 all 重解
                                if widen_pending and not _yt_has_dash(fmts):
                                    self.log(
                                        f"客户端 {clients} 只给影音同条（最高 {any_h}p），"
                                        f"带票的 {YT_WIDE_CLIENTS[0]} 还没试，重解一遍取优",
                                        "warning",
                                        k="srv.engine.client_progressive_only",
                                        kv={"clients": clients, "h": any_h, "wide": YT_WIDE_CLIENTS[0]},
                                    )
                                    _keep_best(info)
                                    continue
                                self._info_cache[cache_key] = (now, info)
                                return info
                            last_err = f"only low progressive (any_h={any_h}, sep_h={sep_h})"
                            self.log(
                                f"客户端 {clients} 最高约 {any_h}p，尝试下一个",
                                "warning",
                                k="srv.engine.client_max_progressive",
                                kv={"clients": clients, "h": any_h},
                            )
                            info["_md_clients"] = clients
                            _keep_best(info)
                            continue
                        info["_md_clients"] = clients
                        self._info_cache[cache_key] = (now, info)
                        return info
                except Exception as e:
                    last_err = str(e)
                    err_l = last_err.lower()
                    # 本地 yt_dlp 损坏时立即跳出，改用 pip 版
                    if "no suitable extractor" in err_l or "unsupported url" in err_l:
                        raise
                    continue
            return None

        try:
            result = _run_tries()
            if result:
                return result, last_err
        except Exception as e:
            last_err = str(e)

        # 回退：丢弃可能损坏的 tools/yt_dlp，改用系统/pip 安装的版本
        if last_err and ("no suitable extractor" in last_err.lower() or "unsupported url" in last_err.lower()):
            self.log("本地 yt-dlp 可能损坏，回退到系统/pip 版本重试", "warning",
                     k="srv.engine.local_ytdlp_broken")
            try:
                _prefer_local_ytdlp(force_clear=True)
                used_fallback_pip = True
                result = _run_tries()
                if result:
                    return result, last_err
            except Exception as e:
                last_err = str(e)

        # 所有客户端都只有低清时，退回最好的一份（仍可下 1080p，总比失败强）
        if fb_box[0]:
            fb = fb_box[0]
            self.log("试过的客户端都没给出独立视频轨，用其中最高的一份", "warning",
                     k="srv.engine.all_clients_no_dash")
            self._info_cache[cache_key] = (now, fb)
            return fb, last_err

        if last_err:
            # 「要不要劝一句更新」是句子后半段的分歧，拆成两处调用：拼在句中间的中文键化不了
            if used_fallback_pip or "extractor" in last_err.lower():
                self.log(f"提取失败: {last_err[:160]} | 请点「更新 yt-dlp」或 pip install -U yt-dlp", "warning",
                         k="srv.engine.extract_failed_update_hint", kv={"err": last_err[:160]})
            else:
                self.log(f"提取失败: {last_err[:160]}", "warning",
                         k="srv.engine.extract_failed", kv={"err": last_err[:160]})
        return None, last_err

    def download(
        self,
        task_id: str,
        url: str,
        out_dir: str,
        cfg: dict,
        video_q: str,
        audio_q: str,
        fmt: str,
        audio_only: bool,
        embed_sub: bool,
        sub_langs: str = "all",
        progress_cb=None,
        force_format: str = None,
        download_section: str = None,
        is_live: bool = False,
    ):
        self._stop_flags[task_id] = False
        self._err_notes.pop(task_id, None)
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        orig_url = url
        url = normalize_url(url)
        if url != orig_url:
            self.log(f"[{task_id[:8]}] URL 规范化: {orig_url} → {url}",
                     k="srv.download.url_normalized", kv={"tid": task_id[:8], "from": orig_url, "to": url})
        self.log(f"[{task_id[:8]}] 开始: {url}", k="srv.download.task_start", kv={"tid": task_id[:8], "url": url})
        self._log_proxy_decision(task_id, url, cfg)
        retry_count = 0
        try:
            self.max_retries = max(0, int(cfg.get("max_retries") or self.max_retries or 3))
        except Exception:
            pass
        skip_subtitles = False

        low0 = (url or "").lower()

        # —— 先判 HLS（含 master.txt 伪装），再判 CDN 直链，避免把播放列表存成 .bin ——
        is_disguised_hls = bool(
            re.search(
                r"(master|index|playlist|chunklist)[^/]*\.(txt|m3u)(\?|$)",
                low0,
            )
            or ("/hls" in low0 and (".txt" in low0 or ".m3u" in low0))
            or ("/hls" in low0 and ".urlset" in low0)
            or "/hls3/" in low0
            or "/hls/" in low0
        )
        is_dash = ".mpd" in low0 or low0.endswith(".mpd") or "/dash/" in low0
        is_pure_hls = (
            ".m3u8" in low0
            or low0.endswith("m3u8")
            or is_disguised_hls
            or "application/vnd.apple.mpegurl" in low0
            or is_dash  # DASH 也走 N_m3u8DL-RE / ffmpeg 专用路径
        )
        use_hls = bool(cfg.get("use_hls_engine")) or (
            is_pure_hls
            and not any(x in low0 for x in ("youtube.com", "youtu.be", "bilibili.com/video", "b23.tv"))
        )
        if is_dash:
            self.log(f"[{task_id[:8]}] 检测到 DASH/MPD，使用流媒体专用引擎",
                     k="srv.download.dash_detected", kv={"tid": task_id[:8]})

        # 嗅探到的 CDN 直链（bilivideo m4s/mp4 等）：禁止走 yt-dlp generic
        is_direct_cdn = bool(cfg.get("direct_cdn")) or (
            ".m4s" in low0
            or "bilivideo.com" in low0
            or "mcdn.bilivideo" in low0
            or "upos-" in low0
            or "googlevideo.com" in low0
            or "douyinvod" in low0
        )
        # 排除：页面 URL、以及 HLS 播放列表（绝不能当二进制直存）
        if (
            "bilibili.com/video" in low0
            or "bilibili.com/bangumi" in low0
            or is_pure_hls
            or is_disguised_hls
        ):
            is_direct_cdn = False

        if is_direct_cdn and not is_live:
            title_hint = safe_filename_component(
                cfg.get("_title") or Path(url.split("?")[0]).stem or "cdn", 60
            )
            dest = Path(out_dir) / f"{title_hint}.bin"
            if ".m4s" in low0:
                dest = dest.with_suffix(".m4s")
            elif ".mp4" in low0:
                dest = dest.with_suffix(".mp4")
            elif ".flv" in low0:
                dest = dest.with_suffix(".flv")
            try:
                self.note_raw_bytes(task_id)   # 这一支不转封装不嵌轨，成品=上游那份字节
                self.log(f"[{task_id[:8]}] CDN 直链下载（绕过 yt-dlp）…",
                         k="srv.download.cdn_direct_start", kv={"tid": task_id[:8]})
                if progress_cb:
                    try:
                        progress_cb(task_id, 5, "", "")
                    except Exception:
                        pass
                used_aria = False
                try_aria = bool(cfg.get("aria2_enabled"))
                # 未全局开启时，若本机 aria2 在线且为常见大文件后缀，仍尝试
                if not try_aria and int(cfg.get("aria2_for_large_mb") or 0) > 0:
                    if any(x in low0 for x in (".mp4", ".mkv", ".zip", ".flv", ".webm")):
                        try_aria = True
                if try_aria:
                    try:
                        from aria2_client import Aria2Client
                        ac = Aria2Client(
                            rpc_url=cfg.get("aria2_rpc") or "http://127.0.0.1:6800/jsonrpc",
                            secret=cfg.get("aria2_secret") or "",
                        )
                        if ac.ping():
                            hdrs = [
                                "User-Agent: Mozilla/5.0",
                                "Referer: https://www.bilibili.com",
                            ]
                            gid = ac.add_uri(
                                [url],
                                out_dir=str(Path(out_dir)),
                                filename=dest.name,
                                headers=hdrs,
                                split=int(cfg.get("aria2_split") or 8),
                            )
                            self.log(f"[{task_id[:8]}] aria2 任务 {gid}",
                                     k="srv.download.cdn_aria2_gid", kv={"tid": task_id[:8], "gid": gid})
                            for _ in range(7200):
                                if self._stop_flags.get(task_id):
                                    ac.remove(gid)
                                    break
                                st = ac.tell_status(gid)
                                status = (st.get("status") or "")
                                completed = int(st.get("completedLength") or 0)
                                total = int(st.get("totalLength") or 0) or 1
                                if progress_cb:
                                    try:
                                        progress_cb(task_id, min(99, completed * 100 / total), "", "")
                                    except Exception:
                                        pass
                                if status == "complete":
                                    used_aria = True
                                    break
                                if status in ("error", "removed"):
                                    raise RuntimeError(st.get("errorMessage") or "aria2 error")
                                time.sleep(1)
                    except Exception as ae:
                        self.log(f"[{task_id[:8]}] aria2 不可用/失败: {ae}，回退 HTTP", "warning",
                                 k="srv.download.aria2_failed", kv={"tid": task_id[:8], "e": str(ae)})
                if not used_aria:
                    _download_url_to_file(
                        url,
                        dest,
                        proxy=task_proxy_override(cfg),
                        referer="https://www.bilibili.com",
                    )
                if dest.exists() and dest.stat().st_size > 0:
                    if progress_cb:
                        try:
                            progress_cb(task_id, 100, "", "")
                        except Exception:
                            pass
                    self.log(f"[{task_id[:8]}] CDN 完成: {dest.name} ({dest.stat().st_size // 1024} KB)",
                             k="srv.download.cdn_done",
                             kv={"tid": task_id[:8], "name": dest.name,
                                 "kb": dest.stat().st_size // 1024})
                    return True, str(dest)
                self.log(f"[{task_id[:8]}] CDN 下载文件为空", "warning",
                         k="srv.download.cdn_empty", kv={"tid": task_id[:8]})
            except Exception as e:
                self.log(f"[{task_id[:8]}] CDN 直链失败: {e}，尝试其它方式", "warning",
                         k="srv.download.cdn_failed", kv={"tid": task_id[:8], "e": str(e)})

        # 嗅探到的纯 HLS：专用引擎（N_m3u8DL-RE / ffmpeg）解析分片
        if use_hls and is_pure_hls and not is_live:
            title_hint = safe_filename_component(
                cfg.get("_title") or Path(url.split("?")[0]).stem or "hls", 60
            )
            hls_headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
                ),
                "Accept": "*/*",
            }
            # 伪装 txt 播放列表常见于成人站 CDN，带 Referer 降低 403
            if is_disguised_hls or ".txt" in low0:
                try:
                    from urllib.parse import urlparse
                    host = urlparse(url).hostname or ""
                    if host:
                        hls_headers["Referer"] = f"https://{host}/"
                        hls_headers["Origin"] = f"https://{host}"
                except Exception:
                    pass
            ok, path = download_hls_with_engine(
                m3u8_url=url,
                out_dir=out_dir,
                title=title_hint,
                proxy=task_proxy_override(cfg),
                headers=hls_headers,
                log=lambda m, level="info": self.log(f"[{task_id[:8]}] {m}", level),
                stop_flag=lambda: bool(self._stop_flags.get(task_id)),
                progress_cb=progress_cb,
                task_id=task_id,
                key_info=str(cfg.get("hls_key") or ""),
            )
            if ok and path:
                if progress_cb:
                    try:
                        progress_cb(task_id, 100, "", "")
                    except Exception:
                        pass
                return True, path
            # 伪装 txt / 纯 HLS 再走 yt-dlp 几乎必然卡死或 403，直接失败
            if is_disguised_hls or is_pure_hls:
                self.log(
                    f"[{task_id[:8]}] HLS 引擎失败且不再回退 yt-dlp（请确认 N_m3u8DL-RE/ffmpeg、链接未过期）",
                    "error",
                    k="srv.download.hls_no_fallback", kv={"tid": task_id[:8]},
                )
                return False, ""
            self.log(f"[{task_id[:8]}] 专用 HLS 引擎未成功，回退 yt-dlp", "warning",
                     k="srv.download.hls_fallback", kv={"tid": task_id[:8]})

        pc_chain: List[str] = []
        if "youtube.com" in url.lower() or "youtu.be" in url.lower():
            pc_chain, pc_note = self._yt_player_chain(cfg, url)
            if pc_note:
                self.log(f"[{task_id[:8]}] YouTube 客户端链 {pc_chain}（{pc_note}）",
                         k="srv.download.yt_client_chain",
                         kv={"tid": task_id[:8], "chain": str(pc_chain), "note": pc_note})
            else:
                self.log(f"[{task_id[:8]}] YouTube 客户端链: {' → '.join(pc_chain)}",
                         k="srv.download.yt_client_chain_join",
                         kv={"tid": task_id[:8], "chain": ' → '.join(pc_chain)})

        while retry_count <= self.max_retries:
            try:
                import yt_dlp

                # 下载前清掉解析缓存，避免沿用「不完整 formats」导致锁死 360p
                try:
                    self._info_cache.pop(url, None)
                    self._info_cache.pop(normalize_url(url), None)
                except Exception:
                    pass
                low = url.lower()
                is_yt = "youtube.com" in low or "youtu.be" in low
                is_bili_live = "live.bilibili.com" in low
                clients = None
                max_listed = 0
                media = []
                info = None
                # 直播：解析失败也继续用 best 尝试录制（房间可能稍后开播）
                if not is_live:
                    info = self.get_info(url, cfg)
                    if self._stop_flags.get(task_id):
                        return False, ""
                    if not info:
                        raise RuntimeError(
                            "无法提取媒体信息（可尝试：更新 yt-dlp、配置有效 Cookie、检查代理/地区限制）"
                        )
                    clients = info.get("_md_clients")
                    fmts = info.get("formats") or []
                    media = [
                        f
                        for f in fmts
                        if (f.get("vcodec") and f.get("vcodec") != "none")
                        or (f.get("acodec") and f.get("acodec") != "none")
                    ]
                    for f in media:
                        if f.get("vcodec") and f.get("vcodec") != "none":
                            max_listed = max(max_listed, f.get("height") or 0)
                    # 记下清单上限：收尾的回读要比「实得 vs 所选」，得知道上游本来给到哪儿。
                    # 重试几轮就取几轮的最大值——补试 all 那轮往往才是清单最全的那一份。
                    if max_listed > 0:
                        self._listed_max[task_id] = max(
                            int(self._listed_max.get(task_id) or 0), max_listed
                        )
                else:
                    self.log(f"[{task_id[:8]}] 直播模式：跳过预解析，直接录制",
                             k="srv.download.live_skip_preparse", kv={"tid": task_id[:8]})
                    try:
                        # 轻量探测标题（失败忽略）
                        info = self.get_info(url, cfg)
                    except Exception:
                        info = None

                if force_format:
                    format_sel = str(force_format).strip()
                    self.log(f"[{task_id[:8]}] 指定格式: {format_sel}",
                             k="srv.download.format_pinned", kv={"tid": task_id[:8], "fmt": format_sel})
                elif is_live:
                    # 直播流用 best，避免 bv* 在直播上失败
                    format_sel = "best/bestvideo+bestaudio/best"
                    self.log(f"[{task_id[:8]}] 直播格式: {format_sel}",
                             k="srv.download.live_format", kv={"tid": task_id[:8], "fmt": format_sel})
                elif is_yt and not audio_only:
                    format_sel = self._resolve_format(
                        [], video_q, audio_q, audio_only, cfg.get("prefer_codec", "auto")
                    )
                    # 解析清单是哪个客户端解出来的就照它下载：窄客户端（default/tv/web_safari）
                    # 不给独立视频轨，bv* 那一串会一路退到末尾的 b[height<=…]，
                    # 用户点的 4K 就静默下成 1080p 渐进流，任务还是「成功」
                    wide = bool(clients) and any(str(c).lower() in YT_WIDE_CLIENTS for c in clients)
                    if wide:
                        self.log(
                            f"[{task_id[:8]}] 解析出的清单来自 {'/'.join(map(str, clients))}（含独立视频轨），"
                            f"下载沿用同一套客户端，列表最高约 {max_listed}p",
                            k="srv.download.dash_list_from",
                            kv={"tid": task_id[:8], "clients": '/'.join(map(str, clients)), "h": max_listed},
                        )
                    elif pc_chain:
                        pci = max(0, min(int(cfg.get("_pc_idx") or 0), len(pc_chain) - 1))
                        clients = [pc_chain[pci]]
                    else:
                        clients = None
                    self.log(f"[{task_id[:8]}] YouTube 使用格式表达式: {format_sel}（列表最高约 {max_listed}p）",
                             k="srv.download.yt_format_sel",
                             kv={"tid": task_id[:8], "fmt": format_sel, "h": max_listed})
                else:
                    format_sel = self._resolve_format(
                        media, video_q, audio_q, audio_only, cfg.get("prefer_codec", "auto")
                    )
                # 过长/含全角非法字符的标题在 Windows 会触发 Errno 22 Invalid argument
                # 若已有 info，预先净化 title/id，拼成固定安全路径（比仅靠 windowsfilenames 更稳）
                # 但合集/播放列表拿到的 info 是容器：title 整表相同、id 为空（会退化成任务号），
                # 拼成固定名等于让每条分集写进同一个路径互相覆盖，只能交给模板逐条展开
                is_pl_info = bool(info) and (
                    info.get("_type") in ("playlist", "multi_video") or bool(info.get("entries"))
                )
                # 合集整批的落点：勾了「整批存进同名文件夹」才多建这一层，单视频与直播录制不加。
                # 名字有两个来处：① 解析回的 info 本身就是容器（下载页直接下整表那一颗），标题即合集名；
                # ② 逐条链接那一侧（整表/选中分集走的是 N 条独立任务）容器不在手上，用入队时带过来的那份。
                dl_dir, pl_note = playlist_landing_dir(
                    out_dir,
                    str((info or {}).get("title") or "") if is_pl_info
                    else str(cfg.get("playlist_folder") or ""),
                    bool(cfg.get("playlist_subdir")),
                    is_playlist=is_pl_info,
                    is_live=is_live,
                )
                if pl_note:
                    self.log(f"[{task_id[:8]}] {pl_note}")
                if info and not is_pl_info and (info.get("title") or info.get("id")):
                    raw_title = str(info.get("title") or "video")
                    safe_title = safe_filename_component(raw_title, 60)
                    safe_id = safe_filename_component(str(info.get("id") or task_id[:8]), 40)
                    if safe_title != raw_title.strip():
                        self.log(f"[{task_id[:8]}] 标题里有 Windows 不能用于文件名的字符，"
                                 f"落盘名已清洗为「{safe_title}」",
                                 k="srv.download.title_cleaned", kv={"tid": task_id[:8], "name": safe_title})
                    out_tmpl = str(Path(dl_dir) / f"{safe_title} [{safe_id}].%(ext)s")
                    if is_live:
                        # 记下真正落盘的文件名主干，结束录制时靠它点名找回拉流子进程
                        self._live_stems[task_id] = f"{safe_title} [{safe_id}]"
                else:
                    template = cfg.get("filename_template") or "%(title).60B [%(id)s].%(ext)s"
                    template = _BIDI_CTRL_RE.sub("", str(template))[:120]
                    template = template.replace("/", "_").replace("\\", "_").replace("\0", "")
                    out_tmpl = str(Path(dl_dir) / template)
                opts = self._ydl_opts(cfg, for_info=False, player_clients=clients, url=url)
                sl_now, sl_note = resolve_speed_limit(cfg)
                if opts.get("ratelimit") or sl_note:
                    self.log(f"[{task_id[:8]}] 限速：{sl_now or '不限速'}（{sl_note}）"
                             f"· 这一档在任务开始时定下，跑到一半不会改")
                opts["outtmpl"] = out_tmpl
                if opts.get("writethumbnail"):
                    # 与 CLI 一致：嵌封面要写缩略图文件，但播放列表级的那张不要
                    opts["outtmpl"] = {"default": out_tmpl, "pl_thumbnail": ""}
                # Windows 禁字符（含 ：？｜＊等）再兜一层
                opts["windowsfilenames"] = True
                opts["restrictfilenames"] = False  # 保留中文，只净化禁字符
                opts["format"] = format_sel
                opts["format_sort"] = ["res", "tbr"]
                opts["ignoreerrors"] = False
                opts["skip_download"] = False
                opts["prefer_ffmpeg"] = True
                # 分片并发（加速大文件）
                try:
                    nfrag = int(cfg.get("concurrent_fragments") or 0)
                    if nfrag > 1:
                        opts["concurrent_fragment_downloads"] = min(nfrag, 16)
                except Exception:
                    pass
                # 直播录制
                if is_live:
                    opts.pop("download_archive", None)
                    opts["noplaylist"] = True
                    opts["retries"] = 15
                    opts["fragment_retries"] = 15
                    # 不用 .part，中断时也更容易得到可改名的成品
                    opts["nopart"] = True
                    opts["continuedl"] = True
                    # 直播 HLS/fmp4：用 mpegts，避免 fmp4 扩展名被安全策略跳过
                    opts["hls_use_mpegts"] = True
                    opts["allow_unplayable_formats"] = True
                    # 输出用 ts/mkv，避免 ext=fmp4 被拒
                    if (fmt or "").lower() in ("", "mp4", "mkv", "best"):
                        opts["merge_output_format"] = "mkv"
                    # YouTube 等：同步写入 live_chat 字幕（聊天记录）
                    try:
                        opts["writesubtitles"] = True
                        opts["subtitleslangs"] = list(
                            dict.fromkeys(
                                list(opts.get("subtitleslangs") or []) + ["live_chat"]
                            )
                        )
                        opts["subtitlesformat"] = "json3/json/vtt/best"
                    except Exception:
                        pass
                    # 直播不写字幕轨（避免多余请求；弹幕走独立抓取）
                    opts.pop("writesubtitles", None)
                    opts.pop("writeautomaticsub", None)
                    opts.pop("subtitleslangs", None)
                    opts["postprocessors"] = [
                        p for p in (opts.get("postprocessors") or [])
                        if p.get("key") != "FFmpegEmbedSubtitle"
                    ]
                    # 按平台流偏好选择 format
                    stream_pref = live_stream_pref_for_url(url, cfg)
                    # 失败回退时换另一种偏好
                    if cfg.get("_live_pref_fallback"):
                        alt = {"flv": "hls", "hls": "flv", "dash": "hls"}.get(stream_pref, "auto")
                        stream_pref = alt
                        self.log(f"[{task_id[:8]}] 流偏好回退 → {stream_pref}",
                                 k="srv.download.live_pref_switch", kv={"tid": task_id[:8], "pref": stream_pref})
                    format_sel = live_format_selector(stream_pref)
                    opts["format"] = format_sel
                    self.log(f"[{task_id[:8]}] 直播流偏好={stream_pref} format={format_sel}",
                             k="srv.download.live_pref_format",
                             kv={"tid": task_id[:8], "pref": stream_pref, "fmt": format_sel})
                    # B站直播
                    if is_bili_live:
                        opts.pop("live_from_start", None)
                        if cfg.get("_live_ffmpeg_ssl") or stream_pref == "flv":
                            # FLV 或 SSL 回退：ffmpeg 拉流
                            opts["external_downloader"] = {
                                "default": "ffmpeg",
                                "m3u8": "ffmpeg",
                                "http_dash_segments": "ffmpeg",
                            }
                            ff_args = [
                                "-reconnect", "1",
                                "-reconnect_streamed", "1",
                                "-reconnect_delay_max", "5",
                            ]
                            if cfg.get("nocheckcertificate", True) is not False:
                                ff_args += ["-tls_verify", "0"]
                            opts["external_downloader_args"] = {"ffmpeg": ff_args}
                            self.log(f"[{task_id[:8]}] B站直播录制（ffmpeg，偏好={stream_pref}）",
                                     k="srv.download.bili_live_ffmpeg", kv={"tid": task_id[:8], "pref": stream_pref})
                        else:
                            opts.pop("external_downloader", None)
                            opts.pop("external_downloader_args", None)
                            opts["hls_prefer_native"] = True
                            self.log(f"[{task_id[:8]}] B站直播录制（原生，偏好={stream_pref}）",
                                     k="srv.download.bili_live_native", kv={"tid": task_id[:8], "pref": stream_pref})
                    else:
                        if cfg.get("live_from_start", True) and (
                            "youtube.com" in low or "youtu.be" in low
                        ):
                            opts["live_from_start"] = True
                        try:
                            opts["wait_for_video"] = (5, 60)
                        except Exception:
                            pass
                        self.log(
                            f"[{task_id[:8]}] 直播录制 偏好={stream_pref} "
                            f"从开头={bool(cfg.get('live_from_start', True))}",
                            k="srv.download.live_record_opts",
                            kv={"tid": task_id[:8], "pref": stream_pref,
                                "from_start": bool(cfg.get("live_from_start", True))},
                        )
                # 片段下载：*开始-结束，如 *01:00-02:30
                sec = (download_section or cfg.get("download_section") or "").strip()
                if sec:
                    if not sec.startswith("*"):
                        sec = "*" + sec
                    try:
                        from yt_dlp.utils import download_range_func
                        opts["download_ranges"] = download_range_func(None, [sec])
                        self.log(f"[{task_id[:8]}] 片段裁剪: {sec}",
                                 k="srv.download.section_clip", kv={"tid": task_id[:8], "sec": sec})
                    except Exception as e:
                        self.log(f"[{task_id[:8]}] 片段参数无效，忽略: {e}", "warning",
                                 k="srv.download.section_invalid", kv={"tid": task_id[:8], "e": str(e)})
                # 风控：请求间隔
                delay = float(cfg.get("risk_delay_sec") or 0)
                if delay > 0:
                    time.sleep(min(delay, 30))
                opts["progress_hooks"] = [
                    lambda d, tid=task_id, th=(info or {}).get("thumbnail") or "": self._hook(
                        tid, d, progress_cb, th
                    )
                ]
                if audio_only:
                    # 容器留着 mkv/mp4 时以前会跳过抽音轨：勾了「仅音频」还是原样下回一个视频，
                    # 而且状态是「完成」—— 只有 ffprobe 能看出来。所以这里无论容器都抽。
                    codec = fmt if fmt in ("mp3", "m4a", "flac", "wav", "opus") else "m4a"
                    opts.setdefault("postprocessors", []).insert(
                        0, {"key": "FFmpegExtractAudio", "preferredcodec": codec}
                    )
                    if codec != fmt:
                        self.log(
                            f"[{task_id[:8]}] 仅音频：容器 {fmt or '未选'} 装不了纯音轨，成品转成 {codec}"
                        )
                elif fmt in ("mp4", "mkv", "webm"):
                    opts["merge_output_format"] = fmt
                    # merge_output_format 只在「视频流 + 音频流需要合并」时才决定容器；
                    # 命中的若是单条音视频同流格式（如 web_safari 的融合 mp4），成品就还是 mp4。
                    # 所以再挂一个无损 remux（不重编码）放在最前，保证容器 = 用户选的那个。
                    opts.setdefault("postprocessors", []).insert(
                        0, {"key": "FFmpegVideoRemuxer", "preferedformat": fmt}
                    )
                want_langs: List[str] = []
                if is_live:
                    # 直播不嵌字幕
                    skip_subtitles = True
                # 「嵌进容器」和「旁边留一份字幕文件」是两回事，但都得先把字幕下载下来：
                # 以前只有 embed_sub 会去要字幕，关掉嵌入就没法只要外挂 .vtt
                keep_files = bool(cfg.get("write_sub_files", True))
                if (embed_sub or keep_files) and not skip_subtitles and not is_live:
                    # yt-dlp 用 `re.compile(码, re.I).fullmatch(站点语言列表)` 匹配：
                    # 大小写不敏感，但必须整码相等 —— "zh" 匹配不到 "zh-Hant"，
                    # 所以简繁各种变体得逐个列，不能只写一个 zh
                    raw = (sub_langs or cfg.get("subtitle_langs") or "zh").strip()
                    if raw.lower() in ("all", "*", ""):
                        # 注意：交给 yt-dlp 的 "all"、或写 zh.* 这类族正则，都会把 YouTube
                        # 的机器翻译组合码一起捞进来（实测一条 5 分钟视频 130+ 个 .vtt /
                        # 31 条字幕轨），所以只列站点里真实存在的原始字幕码
                        langs = ["zh-Hans", "zh-Hant", "zh-CN", "zh-TW", "zh",
                                 "ja", "ko", "en", "en-US", "en-GB"]
                    else:
                        langs = [x.strip() for x in raw.replace(";", ",").split(",") if x.strip()]
                        if not langs:
                            langs = ["zh-Hans", "zh", "en"]
                    opts["writesubtitles"] = True
                    opts["writeautomaticsub"] = True
                    opts["subtitleslangs"] = langs
                    want_langs = list(langs)
                    if embed_sub:
                        # embedsubtitles 只是 CLI 参数名，YoutubeDL 不读 —— 要挂 postprocessor
                        pps = opts.setdefault("postprocessors", [])
                        at = next(
                            (i for i, p in enumerate(pps) if p.get("key") == "FFmpegMetadata"),
                            len(pps),
                        )
                        pps.insert(at, {
                            "key": "FFmpegEmbedSubtitle",
                            # True = 嵌完再留一份外挂文件；False = 只留在容器里
                            "already_have_subtitle": keep_files,
                        })
                    how = "＋".join(
                        x for x in (("嵌进容器" if embed_sub else ""),
                                    ("外挂文件" if keep_files else "")) if x
                    )
                    self.log(f"[{task_id[:8]}] 格式={format_sel} 字幕={langs}（{how}）")
                else:
                    # 无字幕降级：仅去掉字幕相关选项，画质/音质不变
                    opts.pop("writesubtitles", None)
                    opts.pop("writeautomaticsub", None)
                    opts.pop("subtitleslangs", None)
                    opts["postprocessors"] = [
                        p for p in (opts.get("postprocessors") or [])
                        if p.get("key") != "FFmpegEmbedSubtitle"
                    ]
                    if skip_subtitles:
                        self.log(f"[{task_id[:8]}] 无字幕降级 | 画质/音质保持 format={format_sel}",
                                 k="srv.download.no_sub_fallback", kv={"tid": task_id[:8], "fmt": format_sel})
                    else:
                        self.log(f"[{task_id[:8]}] 格式={format_sel} 无字幕",
                                 k="srv.download.format_no_sub", kv={"tid": task_id[:8], "fmt": format_sel})
                t_try = time.time()
                self.log(
                    f"[{task_id[:8]}] 目标容器={opts.get('merge_output_format') or fmt} "
                    f"后期处理={','.join(p.get('key', '?') for p in (opts.get('postprocessors') or [])) or '无'}"
                )
                arch_file = opts.get("download_archive") or ""
                m_arch = re.search(
                    r"(?:[?&]v=|youtu\.be/|/shorts/|/embed/|/live/)([A-Za-z0-9_-]{6,})",
                    url or "",
                )
                arch_vid = m_arch.group(1) if m_arch else ""
                # yt-dlp 往记录里写的是「<站点键去冒号小写> <id>」（如 telegramembed 18465），
                # 只按 YouTube 的 v= 认键，别的站命中记录就会被误报成「站点没返回媒体信息」。
                arch_ids = {x for x in (str((info or {}).get("id") or ""), arch_vid) if x}
                arch_type = re.sub(r"[\s:]+", "", str((info or {}).get("extractor_key")
                                                     or (info or {}).get("extractor") or "").lower())

                def _ids_in_archive(ids, strict_type=True):
                    """这些 id 里已经在下载记录中的那些。命中记录时 yt-dlp 既不下载也不报错"""
                    want = {str(x or "") for x in ids if x}
                    if not (arch_file and want):
                        return set()
                    hit = set()
                    try:
                        with open(arch_file, "r", encoding="utf-8", errors="ignore") as fh:
                            for ln in fh:
                                parts = ln.split()
                                if len(parts) < 2 or parts[-1] not in want:
                                    continue
                                # 键对不上时（直播没有预解析，info 可能为空）只认 id，别放过
                                if not arch_type or not strict_type or (
                                    re.sub(r"[\s:]+", "", parts[0].lower()) == arch_type
                                ):
                                    hit.add(parts[-1])
                        return hit
                    except Exception:
                        return set()

                def _already_recorded():
                    return bool(_ids_in_archive(arch_ids))

                with yt_dlp.YoutubeDL(opts) as ydl:
                    if self._stop_flags.get(task_id):
                        return False, ""
                    info2 = ydl.extract_info(url, download=True)
                    if info2:
                        filepath = ""
                        # 这一趟要的成品容器：转封装/抽音频之后工具报回来的名字还是换容器前那一个，
                        # 找回文件时先按它找（同一个基名旁边可能躺着上一次的旧容器）
                        want_ext = (str(opts.get("merge_output_format") or fmt or ""),)
                        is_pl_result = info2.get("_type") in ("playlist", "multi_video") or bool(
                            info2.get("entries")
                        )
                        pl_files = []
                        if is_pl_result:
                            # 容器自己那份 info 没有分集字段，prepare_filename 只会渲染出 .NA；
                            # 分集的落点在 entries 里（yt-dlp 处理完会写回 filepath）
                            for e in info2.get("entries") or []:
                                if not isinstance(e, dict):
                                    continue
                                pth = str(e.get("filepath") or "")
                                if not pth:
                                    try:
                                        pth = ydl.prepare_filename(e)
                                    except Exception:
                                        pth = ""
                                # 换过容器的分集，这个 pth 是换之前的名字，文件躺在旁边换了后缀
                                pth = resolve_written_file(pth, want_ext)
                                if pth and Path(pth).exists():
                                    pl_files.append(pth)
                            filepath = pl_files[-1] if pl_files else ""
                            n_ent = len([e for e in (info2.get("entries") or [])
                                         if isinstance(e, dict)])
                            if len(pl_files) != n_ent or n_ent > 1:
                                self.log(
                                    f"[{task_id[:8]}] 列表 {n_ent} 条，本次在下载目录写出 "
                                    f"{len(pl_files)} 个文件"
                                    + ("（差额是命中下载记录或抽取失败的条目）" if len(pl_files) != n_ent else "")
                                    + (f"；任务记录最后 1 个：{Path(filepath).name}" if filepath else ""),
                                    "warning",
                                )
                            if not pl_files and _ids_in_archive(
                                [e.get("id") for e in (info2.get("entries") or [])
                                 if isinstance(e, dict)]
                            ):
                                # 整表一条都没写出：是命中记录，不是坏文件
                                self.note_error(
                                    task_id,
                                    "这条列表的每一项此前都已下载过（命中下载记录），本次没有重新下载；"
                                    "要重新下载请在下载选项里关掉「跳过已下载」",
                                )
                                return False, ""
                        if not filepath:
                            filepath = ydl.prepare_filename(info2)
                        # 单条那一支同样会被转封装换了名字，两条路共用同一个找回逻辑（别再各写一份名单）
                        filepath = resolve_written_file(filepath, want_ext)
                        # 命中下载记录的单条视频同样走到这里，只是永远不会有文件：
                        # 不点名原因就会被完整性校验说成「文件不可用」
                        if not Path(filepath).exists() and _already_recorded():
                            self.log(
                                f"[{task_id[:8]}] 跳过：下载记录里已有本视频（此前已成功下载），"
                                f"要重新下载请关掉「跳过已下载」",
                                "warning",
                                k="srv.download.skipped_archive", kv={"tid": task_id[:8]},
                            )
                            self.note_error(
                                task_id,
                                "此前已下载过（命中下载记录），本次跳过；要重新下载请在下载选项里关掉「跳过已下载」",
                            )
                            return False, ""
                        # 命中下载记录时 yt-dlp 什么都不做就返回，不说一句会被当成「设置没生效」
                        try:
                            if filepath and Path(filepath).exists() \
                                    and Path(filepath).stat().st_mtime < t_try - 2:
                                self.log(
                                    f"[{task_id[:8]}] 本次未重新下载：{Path(filepath).name} 已在下载记录里，"
                                    f"要重下请关掉「跳过已下载」",
                                    "warning",
                                    k="srv.download.not_redownloaded",
                                    kv={"tid": task_id[:8], "name": Path(filepath).name},
                                )
                        except Exception:
                            pass
                        # 记录实际分辨率便于确认
                        try:
                            h = info2.get("height") or 0
                            if not h:
                                for f in info2.get("requested_formats") or []:
                                    h = max(h, f.get("height") or 0)
                            if h:
                                self.log(f"[{task_id[:8]}] 实际下载分辨率约 {h}p",
                                         k="srv.download.actual_height", kv={"tid": task_id[:8], "h": h})
                        except Exception:
                            pass
                        # 字幕按语言码精确匹配，站点没有的那几种会被直接跳过 —— 不说清楚
                        # 就成了「明明勾了中文字幕怎么没有」
                        try:
                            if want_langs:
                                got = list((info2.get("requested_subtitles") or {}).keys())
                                miss = [x for x in want_langs if x not in got and x != "all"]
                                if got:
                                    self.log(
                                        f"[{task_id[:8]}] 字幕已写入 {len(got)} 条：{'、'.join(got)}"
                                        + (f"；视频没有这些语言，已跳过：{'、'.join(miss)}" if miss else "")
                                    )
                                else:
                                    self.log(
                                        f"[{task_id[:8]}] 该视频没有所请求的字幕语言"
                                        f"（{'、'.join(want_langs)}），成品不含字幕轨",
                                        "warning",
                                        k="srv.download.subtitle_langs_missing",
                                        kv={"tid": task_id[:8], "langs": '、'.join(want_langs)},
                                    )
                        except Exception:
                            pass
                        ok = not self._stop_flags.get(task_id)
                        return ok, (filepath if ok else "")
                    # extract_info 无返回时不得死循环
                    # 命中下载记录时 yt-dlp 既不下载也不报错，只返回 None —— 不说清楚
                    # 就会被当成「字幕/格式设置没生效」。
                    if _already_recorded():
                        self.log(
                            f"[{task_id[:8]}] 跳过：下载记录里已有本视频（此前已成功下载），"
                            f"要重新下载请关掉「跳过已下载」",
                            "warning",
                            k="srv.download.skipped_archive", kv={"tid": task_id[:8]},
                        )
                        self.note_error(
                            task_id,
                            "此前已下载过（命中下载记录），本次跳过；要重新下载请在下载选项里关掉「跳过已下载」",
                        )
                        return False, ""
                    retry_count += 1
                    self.log(f"[{task_id[:8]}] 下载无返回信息，重试 ({retry_count}/{self.max_retries})", "warning",
                             k="srv.download.no_info_retry",
                             kv={"tid": task_id[:8], "n": retry_count, "max": self.max_retries})
                    self.note_error(task_id, "站点没有返回可下载的媒体信息（已重试）")
                    if progress_cb:
                        try:
                            progress_cb(task_id, -1, f"retry {retry_count}/{self.max_retries}", "")
                        except Exception:
                            pass
                    if retry_count > self.max_retries:
                        return False, ""
                    time.sleep(2)
                    continue
            except Exception as e:
                msg = str(e)
                clean = re.sub(r"\x1b\[[0-9;]*m", "", msg)
                low = clean.lower()
                # 用户结束 / ffmpeg 255：直播视为正常收尾，尝试找回已写入文件
                if is_live and (
                    self._stop_flags.get(task_id)
                    or "ffmpeg exited" in low
                    or "code 255" in low
                    or "cancelled" in low
                ):
                    found = _find_recent_media_files(out_dir, hint=url, within_sec=86400)
                    if found:
                        self.log(f"[{task_id[:8]}] 直播已结束，收尾文件: {Path(found[0]).name}",
                                 k="srv.download.live_ended_file",
                                 kv={"tid": task_id[:8], "name": Path(found[0]).name})
                        return True, found[0]
                    if self._stop_flags.get(task_id):
                        return False, ""
                if self._stop_flags.get(task_id):
                    return False, ""
                self.log(f"[{task_id[:8]}] 错误: {clean[:200]}", "warning",
                         k="srv.download.error_line", kv={"tid": task_id[:8], "err": clean[:200]})
                self.note_error(task_id, clean)

                # 仅字幕相关错误才降级；不要把泛化 timeout 当成字幕错误（否则会空转）
                is_sub_err = any(
                    k in low
                    for k in (
                        "unable to download video subtitles",
                        "unable to download webpage subtitles",
                        "http error 429",
                    )
                ) and ("sub" in low)
                if (is_sub_err or ("subtitle" in low and "429" in low)) and not skip_subtitles:
                    skip_subtitles = True
                    self.log(
                        f"[{task_id[:8]}] 字幕失败，跳过字幕并以原画质/音质重新下载 "
                        f"(video={video_q}, audio={audio_q})",
                        k="srv.download.subtitle_failed_retry",
                        kv={"tid": task_id[:8], "video": video_q, "audio": audio_q},
                    )
                    time.sleep(2)
                    continue

                # 后期处理（合并/嵌字幕/嵌封面/写元数据）失败：mkv 退回 mp4 再试一次
                if fmt == "mkv" and not cfg.get("_fmt_fallback") and any(
                    k in low for k in ("postprocessing", "ffmpeg exited", "embed", "merge", "remux")
                ):
                    cfg["_fmt_fallback"] = True
                    fmt = "mp4"
                    self.log(f"[{task_id[:8]}] 封装/后期处理失败，退回 mp4 重试（画质音质与字幕不变）",
                             k="srv.download.postprocess_fallback", kv={"tid": task_id[:8]})
                    time.sleep(1)
                    continue

                # 直播：首选流失败时按设置回退另一种协议
                if is_live and cfg.get("live_stream_fallback", True) and not cfg.get("_live_pref_fallback"):
                    if any(
                        k in low
                        for k in (
                            "no video formats",
                            "no formats",
                            "not available",
                            "unable to download video data",
                            "404",
                            "403",
                            "certificate",
                            "ssl",
                        )
                    ):
                        cfg["_live_pref_fallback"] = True
                        self.log(f"[{task_id[:8]}] 当前流失败，尝试备选协议…",
                                 k="srv.download.live_pref_fallback", kv={"tid": task_id[:8]})
                        time.sleep(1)
                        continue

                # SSL 证书域名不匹配：关闭校验 +（直播）改用 ffmpeg -tls_verify 0 再试
                if "certificate" in low or "ssl" in low or "hostname mismatch" in low:
                    if not cfg.get("_ssl_retry"):
                        cfg["_ssl_retry"] = True
                        cfg["nocheckcertificate"] = True
                        try:
                            import ssl as _ssl
                            _ssl._create_default_https_context = _ssl._create_unverified_context
                        except Exception:
                            pass
                        if is_live:
                            cfg["_live_ffmpeg_ssl"] = True
                        self.log(f"[{task_id[:8]}] SSL 证书错误，关闭校验后重试",
                                 k="srv.download.ssl_retry", kv={"tid": task_id[:8]})
                        time.sleep(1)
                        continue
                    return False, ""

                # YouTube 播放器被拒（BOT 校验 / 缺 PO Token / 格式不可用）：换下一个 player_client
                if is_yt and pc_chain and not is_live and any(k in low for k in PLAYER_ERR_KEYS):
                    nxt = int(cfg.get("_pc_idx") or 0) + 1
                    if nxt < len(pc_chain):
                        cfg["_pc_idx"] = nxt
                        self.log(
                            f"[{task_id[:8]}] 播放器客户端 {pc_chain[nxt - 1]} 被拒，"
                            f"改用 {pc_chain[nxt]} 重试（{nxt + 1}/{len(pc_chain)}）",
                            "warning",
                            k="srv.download.client_rejected",
                            kv={"tid": task_id[:8], "from": pc_chain[nxt - 1], "to": pc_chain[nxt],
                                "i": nxt + 1, "n": len(pc_chain)},
                        )
                        time.sleep(1)
                        continue

                # 非字幕的 429：指数退避
                if "429" in clean or "too many requests" in low:
                    retry_count += 1
                    if retry_count <= self.max_retries and cfg.get("retry_on_429", True):
                        delay = compute_backoff_delay(
                            retry_count,
                            base=float(cfg.get("backoff_base") or self.base_delay),
                            cap=float(cfg.get("backoff_max") or self.backoff_max),
                            jitter=float(cfg.get("backoff_jitter") if cfg.get("backoff_jitter") is not None else self.backoff_jitter),
                        )
                        # 尊重服务端 Retry-After（若错误信息里带秒数）
                        m_ra = re.search(r"retry[- ]after[:\s]+(\d+)", clean, re.I)
                        if m_ra:
                            delay = max(delay, float(m_ra.group(1)))
                        if cfg.get("adaptive_throttle", True):
                            th = HOST_THROTTLE.hit(
                                url,
                                cooldown=float(cfg.get("risk_cooldown_429") or 60),
                                wait=delay,
                            )
                            if th:
                                self.log(
                                    f"[{task_id[:8]}] 站点 {th['host']} 被限流，已降速："
                                    f"该域同时只跑 1 个，冷却 {th['cooldown']:.0f}s"
                                    f"（第 {th['strikes']} 次命中）",
                                    "warning",
                                    k="srv.download.host_throttled",
                                    kv={"tid": task_id[:8], "host": th["host"],
                                        "cooldown": f"{th['cooldown']:.0f}", "strikes": th["strikes"]},
                                )
                        self.log(
                            f"[{task_id[:8]}] 命中 HTTP 429，指数退避+抖动 {delay:.1f}s "
                            f"后重试 ({retry_count}/{self.max_retries})",
                            k="srv.download.backoff_429",
                            kv={"tid": task_id[:8], "delay": f"{delay:.1f}",
                                "n": retry_count, "max": self.max_retries},
                        )
                        if progress_cb:
                            try:
                                progress_cb(
                                    task_id, -1,
                                    f"429 退避{delay:.0f}s {retry_count}/{self.max_retries}",
                                    "",
                                )
                            except Exception:
                                pass
                        time.sleep(delay)
                        continue
                    return False, ""

                # 无格式：改用更宽的格式串再试（不要沿用失效的 format_id）
                if "no video formats" in low or "no formats" in low or "requested format is not available" in low:
                    retry_count += 1
                    if retry_count <= self.max_retries:
                        self.log(
                            f"[{task_id[:8]}] 无可用格式，改用 bv*/best 重试 ({retry_count}/{self.max_retries})",
                            k="srv.download.no_formats_retry",
                            kv={"tid": task_id[:8], "n": retry_count, "max": self.max_retries},
                        )
                        # 下次循环前清缓存，避免沿用坏列表
                        try:
                            self._info_cache.clear()
                        except Exception:
                            pass
                        time.sleep(2)
                        continue
                    return False, ""

                return False, ""
        return False, ""

    def _hook(self, task_id, d, progress_cb, thumbnail=""):
        if self._stop_flags.get(task_id):
            raise Exception("cancelled")
        if not progress_cb:
            return
        status = d.get("status")
        if status not in ("downloading", "finished"):
            return
        total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
        done = d.get("downloaded_bytes") or 0
        pct = (done / total * 100) if total else 0
        if status == "finished":
            pct = 100.0
        speed = d.get("_speed_str") or ""
        eta = d.get("_eta_str") or ""
        info = d.get("info_dict") or {}
        meta = {"done_bytes": done, "total_bytes": total}
        label = self._stream_label(info)
        if label:
            meta["res_label"] = label
        if thumbnail:
            meta["thumbnail"] = info.get("thumbnail") or thumbnail
        try:
            progress_cb(task_id, pct, speed, eta, meta)
        except Exception:
            pass

    @staticmethod
    def _stream_label(info: dict) -> str:
        """把 yt-dlp 分流的 info_dict 压成卡片上的一行清晰度标签

        合并下载时视频流和音频流会各回调一次，这里只在真视频流上给「1080p」，
        纯音频流给「M4A 128k」，由队列端决定哪个留得下。
        """
        h = int(info.get("height") or 0)
        if h:
            parts = [f"{h}p"]
            dr = str(info.get("dynamic_range") or "").upper()
            if dr in ("HDR", "HDR10", "HDR10+", "DOLBYVISION"):
                parts.append(dr)
            try:
                fps = float(info.get("fps") or 0)
            except Exception:
                fps = 0
            if fps > 30:
                parts.append(f"{int(round(fps))}fps")
            return " ".join(parts)
        if str(info.get("vcodec") or "none") != "none":
            return ""
        ext = str(info.get("ext") or "").upper()
        try:
            abr = float(info.get("abr") or 0)
        except Exception:
            abr = 0
        bits = ([ext] if ext else []) + ([f"{int(round(abr))}k"] if abr else [])
        return " ".join(bits)

    def stop(self, task_id=None):
        if task_id:
            self._stop_flags[task_id] = True
        else:
            for tid in list(self._stop_flags):
                self._stop_flags[tid] = True

    def live_output_stem(self, task_id=None):
        """这一场直播真正在写的文件名主干（结束录制时用来点名拉流子进程），没记到就回空"""
        if not task_id:
            return ""
        return self._live_stems.pop(task_id, "") or ""


# -------------------- 通知 outbox：事件先落盘，再由后台线程逐通道送 --------------------
# 旧做法是「事件发生时同步发一次」：对端抖一下、正好断网、或者赶上程序重启，这条通知就永久
# 没了，只在运行日志里留一行 warning。现在事件先进 outbox 写盘，后台线程按递增间隔重试，
# 重启后接着补发；每个通道各自记账，所以补发不会把已经送到的那一份再发一遍。
NOTIFY_RETRY_DELAYS = (30, 120, 600, 1800, 3600)   # 第 N 次失败后等多久再试
NOTIFY_CHANNEL_LABELS = {"telegram": "Telegram", "serverchan": "Server酱", "wecom": "企业微信"}
NOTIFY_KIND_LABELS = {"done": "下载完成", "fail": "下载失败", "sub": "订阅更新", "live": "直播开播"}
_OUTBOX_KEEP = 50            # 磁盘上最多留这么多条（含已发出的，界面上看的是最近动态）
_OUTBOX_MAX_AGE = 7 * 86400  # 一周前的事件不再补发：那时候人多半已经不需要这条了
_NOTIFY_OUTBOX_TICK = 5.0    # 空闲时每隔几秒看一眼有没有到期的；新事件会直接踢一脚

_outbox_lock = threading.Lock()
_outbox_state = {"seq": 0, "records": []}
_notify_outbox_kick = threading.Event()
_notify_outbox_stop = threading.Event()
_notify_outbox_thread = None


def _outbox_save():
    """把当前表写盘。先取快照再落盘，且走临时文件替换：写到一半崩了不该让下次启动读回半个 JSON。"""
    with _outbox_lock:
        payload = {"seq": _outbox_state["seq"],
                   "records": [dict(r) for r in _outbox_state["records"]]}
    try:
        NOTIFY_OUTBOX_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = Path(str(NOTIFY_OUTBOX_FILE) + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, NOTIFY_OUTBOX_FILE)
    except Exception as e:
        log_mgr.log(f"通知 outbox 写入失败: {e}", "warning", k="srv.outbox.save_failed", kv={"e": str(e)})


def _outbox_load() -> int:
    """开机把上次没送完的读回来，返回还在排队的条数。文件坏了就从空表开始，不影响启动。"""
    now = time.time()
    try:
        raw = json.loads(NOTIFY_OUTBOX_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return 0
    except Exception as e:
        log_mgr.log(f"通知 outbox 读取失败，本次从空表开始: {e}", "warning",
                    k="srv.outbox.load_failed", kv={"e": str(e)})
        return 0
    records, too_old = [], 0
    for r in (raw.get("records") or []):
        if not isinstance(r, dict) or not r.get("text"):
            continue
        r["channels"] = [c for c in (r.get("channels") or []) if c in NOTIFY_CHANNEL_LABELS]
        r["attempts"] = int(r.get("attempts") or 0)
        r["next_try"] = float(r.get("next_try") or now)
        r["created_at"] = float(r.get("created_at") or now)
        if r.get("status") != "pending":
            records.append(r)
            continue
        if now - r["created_at"] > _OUTBOX_MAX_AGE:
            too_old += 1
            continue
        if not r["channels"]:
            r["status"], r["done_at"], r["last_error"] = "dropped", now, "待发通道为空"
        records.append(r)
    with _outbox_lock:
        _outbox_state["seq"] = int(raw.get("seq") or 0)
        _outbox_state["records"] = records
    if too_old:
        log_mgr.log(f"通知 outbox：{_OUTBOX_MAX_AGE // 86400} 天前的 {too_old} 条不再补发", "warning",
                    k="srv.outbox.drop_old", kv={"d": _OUTBOX_MAX_AGE // 86400, "n": too_old})
    return sum(1 for r in records if r.get("status") == "pending")


def _outbox_prune_locked():
    """表太长时先淘汰已经了结的（从最老的开始），还是超就丢最老的待发 —— 队列爆表说明通道一直坏。"""
    recs = _outbox_state["records"]
    if len(recs) <= _OUTBOX_KEEP:
        return
    for r in [x for x in recs if x.get("status") != "pending"]:
        if len(_outbox_state["records"]) <= _OUTBOX_KEEP:
            return
        _outbox_state["records"].remove(r)
    while len(_outbox_state["records"]) > _OUTBOX_KEEP:
        _outbox_state["records"].pop(0)


def _notify_targets(kind: str) -> List[str]:
    """这个事件现在该发给哪些通道 —— 沿用各通道自己的开关，不新增设置项。"""
    d = cfg.data
    out = []
    if tg_notifier.enabled() and (kind == "live" or d.get(f"telegram_notify_{kind}", True)):
        out.append("telegram")
    if kind == "done" and (d.get("serverchan_sendkey") or "").strip():
        out.append("serverchan")
    if d.get("wecom_enabled") and kind in ("done", "fail", "sub") and d.get(f"wecom_notify_{kind}", True):
        out.append("wecom")
    return out


def _notify_send_channel(ch: str, title: str, text: str):
    if ch == "telegram":
        return tg_notifier.send_detail(text)
    if ch == "serverchan":
        return tg_notifier.send_serverchan_detail(title, text)
    if ch == "wecom":
        return wecom_send_detail(text)
    return False, f"不认识的通道 {ch}"


def _notify_enqueue(kind: str, title: str, text: str) -> bool:
    """把一条通知事件写进 outbox。一个通道都没开时和过去一样静默跳过，连盘都不写。"""
    targets = _notify_targets(kind)
    if not targets:
        return False
    now = time.time()
    with _outbox_lock:
        _outbox_state["seq"] += 1
        rec = {"id": _outbox_state["seq"], "kind": kind, "title": title, "text": text,
               "created_at": now, "channels": list(targets), "attempts": 0,
               "next_try": now, "last_error": "", "status": "pending", "done_at": 0.0}
        _outbox_state["records"].append(rec)
        _outbox_prune_locked()
    _outbox_save()
    _notify_outbox_kick.set()   # 让后台线程立刻来拿，正常情况就是秒级送达
    return True


def _outbox_replace(rec: dict):
    """按 id 整条换回去：投递途中不改共享对象，界面读数就不会看到改了一半的记录。"""
    with _outbox_lock:
        for i, r in enumerate(_outbox_state["records"]):
            if r.get("id") == rec.get("id"):
                _outbox_state["records"][i] = rec
                return


def _outbox_attempt(rec: dict) -> None:
    """跑一次投递：只碰还没成功的通道，成功一个划掉一个。"""
    now = time.time()
    wanted = _notify_targets(rec["kind"])
    rec["channels"] = [c for c in rec["channels"] if c in wanted]
    if not rec["channels"]:
        rec["status"], rec["done_at"] = "dropped", now
        rec["last_error"] = "这些通道后来都关了，不再补发"
        return
    rec["attempts"] += 1
    errs, sent = [], []
    for ch in list(rec["channels"]):
        try:
            ok, err = _notify_send_channel(ch, rec.get("title") or "", rec.get("text") or "")
        except Exception as e:
            ok, err = False, f"发送函数抛异常：{e}"
        (sent if ok else errs).append(ch if ok else f"{NOTIFY_CHANNEL_LABELS.get(ch, ch)}：{err}")
    for ch in sent:
        rec["channels"].remove(ch)
    if not rec["channels"]:
        rec["status"], rec["done_at"], rec["last_error"] = "sent", now, ""
        if rec["attempts"] > 1:
            names = "、".join(NOTIFY_CHANNEL_LABELS.get(c, c) for c in sent) or "通道"
            log_mgr.log(f"通知补发成功（第 {rec['attempts']} 次尝试）：{names} · {rec['title']}",
                        k="srv.outbox.retry_sent",
                        kv={"n": rec["attempts"], "ch": names, "t": rec["title"]})
        return
    rec["last_error"] = "；".join(errs)[:300]
    if rec["attempts"] > len(NOTIFY_RETRY_DELAYS):
        rec["status"], rec["done_at"] = "dropped", now
        log_mgr.log(f"通知试了 {rec['attempts']} 次仍没送出去，丢弃：{rec['title']}（{rec['last_error']}）",
                    "warning", k="srv.outbox.retry_dropped",
                    kv={"n": rec["attempts"], "t": rec["title"], "e": rec["last_error"]})
        return
    delay = NOTIFY_RETRY_DELAYS[min(rec["attempts"] - 1, len(NOTIFY_RETRY_DELAYS) - 1)]
    rec["next_try"] = now + delay


def _outbox_tick() -> int:
    """把到期的待发消息各试一次，返回处理了几条。"""
    now = time.time()
    with _outbox_lock:
        due = [dict(r, channels=list(r.get("channels") or [])) for r in _outbox_state["records"]
               if r.get("status") == "pending" and float(r.get("next_try") or 0) <= now]
    if not due:
        return 0
    for r in due:
        try:
            _outbox_attempt(r)
        except Exception as e:
            r["last_error"] = f"投递异常：{e}"
            r["next_try"] = now + NOTIFY_RETRY_DELAYS[0]
        _outbox_replace(r)
    _outbox_save()
    return len(due)


def _outbox_mark_due() -> int:
    """界面上点「立即重试」：把所有待发的推到「现在就试」，真正的发送仍交给后台线程，
    不让这个请求替用户等满 15 秒超时。"""
    now = time.time()
    with _outbox_lock:
        n = 0
        for i, r in enumerate(_outbox_state["records"]):
            if r.get("status") == "pending":
                _outbox_state["records"][i] = dict(r, next_try=now)
                n += 1
    _outbox_save()
    _notify_outbox_kick.set()
    return n


def _outbox_clear_all() -> int:
    """界面上点「清空」：待发的一并作废，已发出的记录抹掉。"""
    with _outbox_lock:
        n = len(_outbox_state["records"])
        _outbox_state["records"] = []
    _outbox_save()
    return n


def _outbox_payload() -> dict:
    now = time.time()
    with _outbox_lock:
        recs = [dict(r, channels=list(r.get("channels") or [])) for r in _outbox_state["records"]]
    records = []
    for r in sorted(recs, key=lambda x: float(x.get("created_at") or 0), reverse=True):
        pending = r.get("status") == "pending"
        records.append({
            "id": r.get("id"), "kind": r.get("kind"),
            "kind_label": NOTIFY_KIND_LABELS.get(r.get("kind"), r.get("kind")),
            "title": r.get("title") or "", "text": (r.get("text") or "")[:300],
            "created_at": r.get("created_at"), "status": r.get("status"),
            "attempts": r.get("attempts"),
            "channels": [NOTIFY_CHANNEL_LABELS.get(c, c) for c in r.get("channels") or []],
            "error": r.get("last_error") or "",
            "next_in": max(0, round(float(r.get("next_try") or 0) - now)) if pending else 0,
        })
    counts = {k: sum(1 for x in records if x["status"] == k) for k in ("pending", "sent", "dropped")}
    return {"ok": True, "records": records, "counts": counts,
            "retry_delays": list(NOTIFY_RETRY_DELAYS), "tick_sec": _NOTIFY_OUTBOX_TICK,
            "keep": _OUTBOX_KEEP, "file": str(NOTIFY_OUTBOX_FILE)}


def start_notify_outbox():
    """后台线程：新事件被踢一脚就立刻发，空闲时每 5 秒看一眼有没有到期待重试的。"""
    global _notify_outbox_thread
    if _notify_outbox_thread and _notify_outbox_thread.is_alive():
        return
    pending = _outbox_load()
    if pending:
        cadence = " → ".join(f"{d}s" for d in NOTIFY_RETRY_DELAYS)
        log_mgr.log(f"通知 outbox：读回 {pending} 条上次没送出去的，按 {cadence} 的节奏继续重试",
                    k="srv.outbox.loaded", kv={"n": pending, "r": cadence})

    def loop():
        while not _notify_outbox_stop.is_set():
            try:
                _outbox_tick()
            except Exception as e:
                log_mgr.log(f"通知 outbox 轮询异常: {e}", "warning",
                            k="srv.outbox.loop_error", kv={"e": str(e)})
            _notify_outbox_kick.wait(_NOTIFY_OUTBOX_TICK)
            _notify_outbox_kick.clear()

    _notify_outbox_stop.clear()
    _notify_outbox_thread = threading.Thread(target=loop, daemon=True, name="notify-outbox")
    _notify_outbox_thread.start()
    log_mgr.log("通知 outbox 已启动（失败的通知会落盘重试，重启不丢）", k="srv.outbox.started")


# -------------------- 剪贴板监听（#206④）--------------------
# 只做「看见了一条链接，问一句要不要用」这一件事：默认关、读到的内容不落盘也不写日志，
# 点「加入」也只是把链接填进下载输入框 —— 入队、发请求永远由用户自己按那一下决定。
CLIP_POLL_SEC = 2.0
CLIP_SEEN_KEEP = 30          # 记住最近这么多份内容，翻回去复制同一条不该再弹一次
CLIP_TEXT_CAP = 4000         # 剪贴板里是一大段文字时不去里面刨链接
# 中英文标点都不算链接的一部分：复制链接时旁边常跟着「」，、：，而 URL 里出现这些的极少，
# 留在链接里会让浏览器一进去就 404。半角括号照旧放行（文件名里 a(1).mkv 太常见），
# 冒号只排全角（端口要留）。
_CLIP_STOP = r"\s<>\"'（）【】「」『』，。、；：！？…　"
_CLIP_URL_RE = re.compile(r"(magnet:\?[^" + _CLIP_STOP + r"]+|https?://[^" + _CLIP_STOP + r"]+)",
                          re.IGNORECASE)

_clip_lock = threading.Lock()
_clip_state: dict = {"last_key": "", "seen": [], "pending": None, "error": "",
                     "checks": 0, "hits": 0, "since": 0.0}
_clip_stop = threading.Event()
_clip_thread: Optional[threading.Thread] = None


def clipboard_text() -> Tuple[str, str]:
    """读一次系统剪贴板里的纯文本，回 (内容, 说不清的缘故)。只读：不写、不清、不动别的格式。

    用 ctypes 走 user32/kernel32 是为了零新依赖（本机已经有 pywin32 之外的东西都要用户自己装）。
    剪贴板是全局锁资源，别的程序正写着时 OpenClipboard 会失败 —— 这不是错误，下一轮再读就是，
    所以这里只把原因回给调用者，绝不重试到把界面卡住。
    """
    if sys.platform != "win32":
        return "", "这一功能只在 Windows 上读系统剪贴板（其它系统走各自的接口，本机用不上）"
    try:
        import ctypes
        from ctypes import wintypes
    except Exception as e:      # 极老的 Python / 非 Windows 上 windll 根本不存在
        return "", f"这个环境用不了 Windows 剪贴板接口：{type(e).__name__}"
    CF_UNICODETEXT = 13
    user32 = ctypes.windll.user32      # type: ignore[attr-defined]
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    # 64 位上 HANDLE 是指针，默认 restype（c_int）会把它截断成 32 位，读出来必是垃圾
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.IsClipboardFormatAvailable.restype = wintypes.BOOL
    user32.IsClipboardFormatAvailable.argtypes = [wintypes.UINT]
    user32.GetClipboardData.restype = ctypes.c_void_p
    user32.GetClipboardData.argtypes = [wintypes.UINT]
    user32.CloseClipboard.restype = wintypes.BOOL
    kernel32.GlobalSize.restype = ctypes.c_size_t
    kernel32.GlobalSize.argtypes = [ctypes.c_void_p]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    if not user32.OpenClipboard(None):
        return "", "剪贴板正被别的程序占着，下一次轮询自动再试"
    try:
        if not user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
            return "", ""       # 图片 / 文件列表这一类没有文本可比，不算异常
        h = user32.GetClipboardData(CF_UNICODETEXT)
        if not h:
            return "", "读不到剪贴板里的文本（可能刚被改写过）"
        size = kernel32.GlobalSize(h)
        ptr = kernel32.GlobalLock(h)
        try:
            if not ptr or not size:
                return "", "剪贴板内容锁不住（可能刚被别的程序改写）"
            raw = ctypes.string_at(ptr, size)
        finally:
            kernel32.GlobalUnlock(h)
        text = raw.decode("utf-16-le", "ignore").strip("\x00").strip()
        return text, ""
    finally:
        user32.CloseClipboard()


def clip_extract_link(text: str) -> str:
    """从剪贴板内容里认出一条可下载的链接；认不出就回空串（一大段文章不该被当成链接）。"""
    t = str(text or "").strip()
    if not t or len(t) > CLIP_TEXT_CAP:
        return ""
    m = _CLIP_URL_RE.search(t)
    if not m:
        return ""
    link = m.group(1).strip()
    # 半角标点能出现在 URL 里，所以尾巴上那一个才切（a(1).mkv 里的括号得留着）
    return link[:-1] if len(link) > 12 and link[-1] in ",.)]" else link


def _clip_tick() -> None:
    """轮询一次：换了内容、且里面确实有链接，才把这一条挂到「待定」上。"""
    text, err = clipboard_text()
    with _clip_lock:
        _clip_state["checks"] += 1
        _clip_state["error"] = err
        if not text:
            return
        key = hashlib.sha1(text.encode("utf-8", "ignore")).hexdigest()[:16]
        if key == _clip_state["last_key"] or key in _clip_state["seen"]:
            return          # 同一份内容来回弹才是问题，改过的不算
        _clip_state["last_key"] = key
        _clip_state["seen"] = (_clip_state["seen"] + [key])[-CLIP_SEEN_KEEP:]
        link = clip_extract_link(text)
        if not link:
            return
        _clip_state["hits"] += 1
        # 只挂这一条：界面每 2 秒来取，取走前新的会把旧的顶掉（用户复制得快，说明旧的那条不要了）
        _clip_state["pending"] = {"link": link, "kind": "magnet" if link.lower().startswith("magnet:") else "http",
                                  "chars": len(text), "ts": datetime.now().isoformat(timespec="seconds")}


def start_clipboard_watch() -> None:
    """后台线程常驻，但只有设置里打开了才真去读剪贴板 —— 默认关着时它一趟也不碰。"""
    global _clip_thread
    if _clip_thread and _clip_thread.is_alive():
        return
    with _clip_lock:
        _clip_state["since"] = time.time()

    def loop():
        while not _clip_stop.is_set():
            try:
                if cfg.data.get("clipboard_watch"):
                    _clip_tick()
            except Exception as e:
                log_mgr.log(f"剪贴板监听轮询异常：{type(e).__name__}: {str(e)[:120]}", "warning")
            _clip_stop.wait(CLIP_POLL_SEC)

    _clip_stop.clear()
    _clip_thread = threading.Thread(target=loop, daemon=True, name="clipboard-watch")
    _clip_thread.start()


# -------------------- Telegram 通知 --------------------
class TelegramNotifier:
    def __init__(self, cfg: ConfigManager, log: Callable = None):
        self.cfg = cfg
        self.log = log or (lambda m, level="info", k="", kv=None: None)

    def enabled(self) -> bool:
        d = self.cfg.data
        return bool(d.get("telegram_enabled") and d.get("telegram_bot_token") and d.get("telegram_chat_id"))

    def send_detail(self, text: str):
        """真发一条 Telegram 消息，返回 (成功, 失败原因)。原因会被界面读，所以要说人话。"""
        if not self.enabled():
            return False, "Telegram 没启用，或 Bot Token / Chat ID 是空的"
        token = (self.cfg.data.get("telegram_bot_token") or "").strip()
        chat_id = (self.cfg.data.get("telegram_chat_id") or "").strip()
        try:
            r = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": text[:3500], "disable_web_page_preview": True},
                timeout=15,
            )
            if r.status_code != 200:
                self.log(f"Telegram 发送失败: {r.text[:120]}", "warning")
                return False, f"HTTP {r.status_code}：{(r.text or '')[:160]}"
            return True, ""
        except Exception as e:
            self.log(f"Telegram 异常: {e}", "warning")
            return False, f"请求没发出去：{e}"

    def send(self, text: str) -> bool:
        return self.send_detail(text)[0]

    def notify_done(self, title: str, url: str = "", path: str = ""):
        _notify_enqueue("done", "下载完成", f"✅ 下载完成\n{title or url}\n{path or url}")

    def notify_fail(self, title: str, url: str = "", err: str = ""):
        _notify_enqueue("fail", "下载失败", f"❌ 下载失败\n{title or url}\n{(err or '')[:200]}")

    def notify_sub(self, sub_title: str, new_count: int, samples: List[str] = None):
        extra = "\n".join(f"· {x}" for x in (samples or [])[:5])
        _notify_enqueue("sub", "订阅更新", f"📢 订阅更新: {sub_title}\n新增 {new_count} 条\n{extra}")

    def test(self) -> str:
        ok = self.send("🔔 MediaDownloader 测试消息\nTelegram 通知已连通。\n发送 /help 查看远程命令。")
        return "ok" if ok else "failed"

    def send_serverchan_detail(self, title: str, desp: str = ""):
        key = (self.cfg.data.get("serverchan_sendkey") or "").strip()
        if not key:
            return False, "Server酱 SendKey 没填"
        try:
            # Server酱 Turbo
            r = requests.post(
                f"https://sctapi.ftqq.com/{key}.send",
                data={"title": title[:100], "desp": desp[:2000]},
                timeout=15,
            )
            if r.status_code != 200:
                self.log(f"Server酱失败: HTTP {r.status_code} {(r.text or '')[:120]}", "warning")
                return False, f"HTTP {r.status_code}：{(r.text or '')[:160]}"
            return True, ""
        except Exception as e:
            self.log(f"Server酱失败: {e}", "warning")
            return False, f"请求没发出去：{e}"

    def send_serverchan(self, title: str, desp: str = "") -> bool:
        return self.send_serverchan_detail(title, desp)[0]

    def _extract_urls(self, text: str) -> List[str]:
        if not text:
            return []
        return re.findall(r"https?://[^\s<>\"']+", text)

    def handle_command(self, text: str, queue: "TaskQueue" = None, sub_mgr: "SubscriptionManager" = None) -> str:
        """处理 Telegram 远程命令，返回回复文本"""
        raw = (text or "").strip()
        if not raw:
            return ""
        low = raw.lower()
        # 去掉 bot 用户名：/download@MyBot
        cmd = low.split()[0].split("@")[0] if low.startswith("/") else ""
        rest = raw[len(raw.split()[0]):].strip() if raw.startswith("/") else raw
        urls = self._extract_urls(rest) or self._extract_urls(raw)

        help_text = (
            "🤖 MediaDownloader 远程命令\n"
            "直接发送链接 → 自动加入下载\n"
            "/d 或 /download [链接] — 下载\n"
            "/s 或 /subscribe [链接] — 订阅频道/播放列表\n"
            "/st 或 /status — 查看队列状态\n"
            "/a 或 /analyze [链接] — 简单解析标题\n"
            "/h 或 /help — 帮助"
        )

        if cmd in ("/help", "/h", "/start") or low in ("帮助", "help"):
            return help_text

        if cmd in ("/status", "/st") or low in ("状态", "status"):
            try:
                running = getattr(queue, "running", 0) if queue else 0
                pending = len(getattr(queue, "pending", []) or []) if queue else 0
                tasks = list((getattr(queue, "tasks", {}) or {}).values()) if queue else []
                finished = sum(1 for t in tasks if getattr(t, "status", "") == "finished")
                failed = sum(1 for t in tasks if getattr(t, "status", "") == "failed")
                subs_n = len(sub_mgr.list()) if sub_mgr else 0
                return (
                    f"📊 状态\n"
                    f"运行中: {running}\n"
                    f"排队: {pending}\n"
                    f"已完成: {finished}\n"
                    f"失败: {failed}\n"
                    f"订阅数: {subs_n}"
                )
            except Exception as e:
                return f"状态获取失败: {e}"

        if cmd in ("/subscribe", "/s", "/sub") or low.startswith("订阅"):
            if not urls:
                return "请提供要订阅的链接，例如：\n/subscribe https://www.youtube.com/@channel"
            if not sub_mgr:
                return "订阅模块未就绪"
            lines = []
            for u in urls[:5]:
                try:
                    item = sub_mgr.add(u, "")
                    try:
                        sub_mgr.scan_one(item, auto_download=False)
                    except Exception:
                        pass
                    lines.append(f"✅ 已订阅: {item.get('title') or u}")
                except Exception as e:
                    lines.append(f"❌ 订阅失败: {u}\n{e}")
            return "\n".join(lines) or "无有效链接"

        if cmd in ("/analyze", "/a", "/parse") or low.startswith("解析"):
            if not urls:
                return "请提供要解析的链接"
            try:
                info = engine.get_info(urls[0], self.cfg.data)
                if not info:
                    return "解析失败：无结果"
                title = info.get("title") or ""
                dur = info.get("duration_string") or info.get("duration") or ""
                up = info.get("uploader") or ""
                return f"🔍 解析结果\n标题: {title}\nUP: {up}\n时长: {dur}\n{urls[0]}"
            except Exception as e:
                return f"解析失败: {e}"

        # 下载：命令或纯链接
        if cmd in ("/download", "/d", "/dl") or urls:
            if not urls:
                return "请提供下载链接，例如：\n/download https://..."
            if not queue:
                return "下载队列未就绪"
            try:
                ids = queue.add_urls(urls[:10], {
                    "video_quality": self.cfg.data.get("video_quality", "best"),
                    "audio_quality": self.cfg.data.get("audio_quality", "best"),
                    "format": self.cfg.data.get("format", "mkv"),
                    "skip_downloaded": True,
                    "allow_playlist": False,
                })
                return f"⬇️ 已加入下载队列\n共 {len(ids)} 个任务\n" + "\n".join(urls[:5])
            except Exception as e:
                return f"加入下载失败: {e}"

        return help_text

    def poll_once(self, queue: "TaskQueue" = None, sub_mgr: "SubscriptionManager" = None) -> int:
        """拉取并处理一条更新，返回处理条数"""
        if not self.enabled() or not self.cfg.data.get("telegram_commands_enabled", True):
            return 0
        token = (self.cfg.data.get("telegram_bot_token") or "").strip()
        chat_id = str(self.cfg.data.get("telegram_chat_id") or "").strip()
        offset = int(self.cfg.data.get("telegram_offset") or 0)
        try:
            r = requests.get(
                f"https://api.telegram.org/bot{token}/getUpdates",
                params={"offset": offset, "timeout": 0, "limit": 10},
                timeout=12,
            )
            data = r.json() if r.status_code == 200 else {}
            results = data.get("result") or []
            handled = 0
            for upd in results:
                uid = int(upd.get("update_id") or 0) + 1
                if uid > offset:
                    offset = uid
                msg = upd.get("message") or upd.get("edited_message") or {}
                from_chat = str((msg.get("chat") or {}).get("id") or "")
                # 仅响应配置的 chat_id，避免被他人滥用
                if chat_id and from_chat and from_chat != chat_id:
                    continue
                text = (msg.get("text") or "").strip()
                if not text:
                    continue
                reply = self.handle_command(text, queue=queue, sub_mgr=sub_mgr)
                if reply:
                    self.send(reply)
                    handled += 1
            if offset != int(self.cfg.data.get("telegram_offset") or 0):
                self.cfg.data["telegram_offset"] = offset
                try:
                    self.cfg.save()
                except Exception:
                    pass
            return handled
        except Exception as e:
            self.log(f"Telegram 轮询异常: {e}", "warning")
            return 0


# -------------------- 订阅追踪 --------------------
# 后两类只有 Telegram 源能命中：别的平台不会列出图片帖 / 文件帖
SUB_TYPES = {"video": "长视频", "short": "短视频", "live": "直播", "audio": "音频/播客",
             "photo": "图片", "file": "文件/文档"}
SUB_FORMATS = ("mkv", "mp4", "webm", "mp3", "m4a", "flac")
SUB_QUALITIES = ("best", "4K", "1440p", "1080p", "720p", "480p", "360p")
SUB_CAP_DEFAULT = 20  # 没设过规则的旧订阅沿用原来的单次 20 条封顶
SUB_SEEN_CAP = 300   # 追新游标最多记多少条 id
MUSIC_SUB_WINDOW = 300  # 同 parse_playlist 的取数上限：歌单里的歌不能因为窗口太窄而被永久漏掉
SUB_FEED_CAP = 200      # 上游窗口对照清单每源记多少条：用来分辨「上游删了」还是「滑出窗口」
SUB_ARCHIVE_CAP = 100   # 每源留档多少条「上游已删除」的条目
SUB_TEXT_CAP = 160      # 对照清单 / 归档记录里标题与链接截多长，免得 subscriptions.json 撑爆


def _sub_window(kind: str) -> Tuple[int, int]:
    """这条订阅每轮看多少条 / 游标存多少条。

    游标必须装得下窗口 —— 窗口内的条目若被游标截断丢掉，下一轮就会当成新增重复下载。
    """
    if kind == "music":
        return MUSIC_SUB_WINDOW, MUSIC_SUB_WINDOW
    return 200, SUB_SEEN_CAP


def _feed_sync(feed: List[dict], cur: List[dict], now: str) -> Tuple[List[dict], List[dict], int]:
    """上一轮的窗口清单 + 这一轮读到的条目 → (新对照清单, 上游已删除, 自然滑出的条数)。

    订阅源都是新的在前、旧的在后：一轮之间从尾部少掉几条只是窗口滑动，从中间空掉一块才是删帖。
    判据就一条 —— 本轮还有比它更旧的条目在场，它就不可能是滑出去的。
    整轮一条都没续上（surv 为空，例如换了链接）也按滑出处理：宁可不报，也不因为一次网络抖动
    把上游还留着的东西说成已删除。
    """
    cur_ids = [str((c or {}).get("id") or "") for c in (cur or [])]
    cur_ids = [x for x in cur_ids if x]
    present = set(cur_ids)
    surv = [i for i, r in enumerate(feed or []) if str((r or {}).get("id") or "") in present]
    oldest = max(surv) if surv else -1
    deleted: List[dict] = []
    aged = 0
    for i, r in enumerate(feed or []):
        rid = str((r or {}).get("id") or "")
        if not rid or rid in present:
            continue
        if surv and i < oldest:
            deleted.append({**r, "gone_at": now})
        else:
            aged += 1
    rows: List[dict] = []
    seen: set = set()
    for e in cur or []:
        rid = str((e or {}).get("id") or "")
        if not rid or rid in seen:
            continue
        seen.add(rid)
        rows.append({
            "id": rid[:200],
            "title": str(e.get("title") or rid)[:SUB_TEXT_CAP],
            "url": str(e.get("url") or e.get("webpage_url") or "")[:SUB_TEXT_CAP],
            "last_seen": now,
        })
    return rows[:SUB_FEED_CAP], deleted, aged


def _reject_rows(rejected: List[tuple], cap: int = 30) -> List[dict]:
    """被规则挡掉的明细（(标题, 原因)）收成 JSON 行，给预览面板列出来。"""
    return [{"title": t, "why": w} for t, w in rejected[:cap]]


def _sub_kw_list(raw) -> List[str]:
    """关键词一条订阅最多 20 个，逗号 / 顿号 / 分号 / 换行都当分隔符。

    存盘的规则本来就是列表，读取时会再清洗一遍 —— 所以列表和字符串都得吃，且清洗两次结果一样。
    """
    items = list(raw) if isinstance(raw, (list, tuple)) else re.split(r"[,，、;；\n]+", str(raw or ""))
    out: List[str] = []
    for p in items:
        p = str(p).strip()
        if p and p not in out:
            out.append(p)
    return out[:20]


def _sub_entry_kind(e: dict) -> str:
    k = str(e.get("kind") or "")
    if k in SUB_TYPES:
        return k
    u = str(e.get("url") or e.get("webpage_url") or "").lower()
    host = u.split("/")[2] if u.count("/") >= 3 else ""
    ie = str(e.get("ie_key") or "")
    if e.get("is_live") or str(e.get("live_status") or "") in ("now", "is_live") \
            or "/live" in u or host.startswith("live."):
        return "live"
    if "/shorts/" in u or "/reel/" in u or "/stories/" in u or ie == "YouTubeShorts":
        return "short"
    if str(e.get("vcodec") or "") == "none" or "podcast" in u or ie in ("SoundCloud", "Mixcloud"):
        return "audio"
    return "video"


def _sub_date(e: dict) -> str:
    """条目日期，收成 YYYY-MM-DD；没有就空 —— 日期窗不猜，缺日期的条目一律放行。"""
    d = str(e.get("date") or e.get("upload_date") or e.get("datetime") or "").strip()
    if len(d) >= 10 and d[4] == "-":
        return d[:10]
    m = re.match(r"^(\d{4})(\d{2})(\d{2})", d)
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else ""


def _norm_date_str(v) -> str:
    s = re.sub(r"[/.]", "-", str(v or "").strip())[:10]
    try:
        return datetime.strptime(s, "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        return ""


def _sub_duration(e: dict) -> float:
    try:
        return float(e.get("duration") or 0)
    except Exception:
        return 0.0


def _fmt_dur(sec: int) -> str:
    sec = int(sec or 0)
    if sec < 90:
        return f"{sec}秒"
    if sec < 5400:
        return f"{round(sec / 60)}分钟"
    return f"{round(sec / 3600, 1)}小时"


def _norm_sub_rules(raw) -> dict:
    """把前端传来的规则收成干净字典：空值一律不落盘，越界值夹回可用区间。"""
    src = raw if isinstance(raw, dict) else {}
    r: dict = {}
    types = [t for t in dict.fromkeys(src.get("types") or []) if t in SUB_TYPES]
    if types and len(types) < len(SUB_TYPES):
        r["types"] = types
    for k in ("only_kw", "skip_kw"):
        kw = _sub_kw_list(src.get(k))
        if kw:
            r[k] = kw
    for k in ("min_dur", "max_dur"):
        try:
            v = max(0, min(86400, int(float(src.get(k) or 0))))
        except Exception:
            v = 0
        if v:
            r[k] = v
    since, until = _norm_date_str(src.get("since")), _norm_date_str(src.get("until"))
    if since and until and since > until:
        since, until = until, since
    if since:
        r["since"] = since
    if until:
        r["until"] = until
    if src.get("audio_only"):
        r["audio_only"] = True
    q = str(src.get("video_quality") or "").strip()
    if q in SUB_QUALITIES:
        r["video_quality"] = q
    fmt = str(src.get("format") or "").strip().lower()
    if fmt in SUB_FORMATS:
        r["format"] = fmt
    ai = str(src.get("run_ai") or "").strip()
    if ai in ("on", "off"):
        r["run_ai"] = ai
    tpl = str(src.get("filename_template") or "").strip()[:200]
    if tpl:
        r["filename_template"] = tpl
    d = str(src.get("download_dir") or "").strip()[:300]
    if d:
        r["download_dir"] = d
    raw_cap = src.get("max_per_scan")
    if raw_cap is None or str(raw_cap).strip() == "":
        r["max_per_scan"] = SUB_CAP_DEFAULT
    else:
        try:
            r["max_per_scan"] = max(0, min(50, int(float(raw_cap))))
        except Exception:
            r["max_per_scan"] = SUB_CAP_DEFAULT
    return r


def _sub_rule_match(e: dict, r: dict):
    """逐条判定：返回 (要不要, 被挡原因)。"""
    types = r.get("types")
    if types:
        k = _sub_entry_kind(e)
        if k not in types:
            return False, f"类型是{SUB_TYPES.get(k, k)}"
    dur = _sub_duration(e)
    if dur:
        if r.get("min_dur") and dur < int(r["min_dur"]):
            return False, f"时长 {_fmt_dur(dur)} 偏短"
        if r.get("max_dur") and dur > int(r["max_dur"]):
            return False, f"时长 {_fmt_dur(dur)} 偏长"
    d = _sub_date(e)
    if d:
        if r.get("since") and d < r["since"]:
            return False, f"{d} 早于日期窗"
        if r.get("until") and d > r["until"]:
            return False, f"{d} 晚于日期窗"
    low = str(e.get("title") or "").lower()
    for kw in r.get("skip_kw") or []:
        if kw.lower() in low:
            return False, f"命中排除词「{kw}」"
    only = r.get("only_kw") or []
    if only and not any(kw.lower() in low for kw in only):
        return False, "标题不含关键词"
    return True, ""


def _sub_rules_text(r: dict) -> str:
    """规则的人话摘要 —— 日志和订阅列表都要能一眼看出这条订阅按什么口径下。"""
    parts = []
    if r.get("types"):
        parts.append("只要 " + "/".join(SUB_TYPES[t] for t in r["types"]))
    if r.get("min_dur"):
        parts.append(f"时长≥{_fmt_dur(r['min_dur'])}")
    if r.get("max_dur"):
        parts.append(f"时长≤{_fmt_dur(r['max_dur'])}")
    if r.get("since") or r.get("until"):
        parts.append(f"只下 {r.get('since') or '最早'}~{r.get('until') or '最新'}")
    if r.get("only_kw"):
        parts.append("标题含「" + "」「".join(r["only_kw"]) + "」")
    if r.get("skip_kw"):
        parts.append("排除「" + "」「".join(r["skip_kw"]) + "」")
    if r.get("audio_only"):
        parts.append("只下音频")
    if r.get("video_quality"):
        parts.append(f"画质 {r['video_quality']}")
    if r.get("format"):
        parts.append(f"封装 {r['format']}")
    if r.get("run_ai") == "on":
        parts.append("下完转写")
    elif r.get("run_ai") == "off":
        parts.append("不转写")
    if r.get("filename_template"):
        parts.append("自定义命名")
    if r.get("download_dir"):
        parts.append("存到 " + str(r["download_dir"]).replace("\\", "/").rstrip("/").split("/")[-1])
    cap = int(r.get("max_per_scan") or 0)
    parts.append(f"每次最多 {cap} 条" if cap else "单次不限条数")
    return "、".join(parts)


# Telegram 频道当订阅源：公开频道匿名翻 t.me/s/，私有 / 需登录的走已登录的用户会话
TG_KIND_TO_SUB = {"video": "video", "audio": "audio", "voice": "audio",
                  "document": "file", "photo": "photo"}
SUB_KIND_TO_TG = {"video": ("video",), "short": ("video",), "audio": ("audio", "voice"),
                  "photo": ("photo",), "file": ("document",)}


def _tg_sub_ref(url: str, mode: str = "") -> Tuple[str, str]:
    """订阅链是不是 Telegram 频道 → ("anon", 频道名) / ("mt", 实体) / ("", "")。

    mode 留空走自动：公开名匿名翻页就够，t.me/c/… 和裸 -100 id 只有会话能读。
    """
    u = (url or "").strip()
    if not u:
        return "", ""
    from telegram_channel import normalize_channel
    ch = normalize_channel(u)
    if ch and (mode or "") != "mt":
        return "anon", ch
    from telegram_mt import normalize_entity
    ent = normalize_entity(u)
    if ent:
        return "mt", ent
    return ("anon", ch) if ch else ("", "")


def _tg_sub_entries(rows: List[dict], is_mt: bool) -> List[dict]:
    """telegram 条目 → 订阅规则认识的形状。

    匿名页只有视频能给 yt-dlp，文档 / 图片帖只列了个名字，所以匿名模式把这些丢掉 ——
    订阅最怕的是把下不动的东西当成新增推一次。
    """
    out: List[dict] = []
    for r in rows or []:
        rid = str(r.get("id") or "")
        link = str((r.get("mt_url") if is_mt else r.get("url")) or r.get("url") or "")
        if not rid or not link:
            continue
        if not is_mt and not r.get("downloadable"):
            continue
        out.append({
            "id": ("tgmt:" if is_mt else "tgs:") + rid,
            "url": link,
            "title": r.get("title") or r.get("filename") or link,
            "duration": r.get("duration_sec") or 0,
            "kind": TG_KIND_TO_SUB.get(str(r.get("type") or ""), "video"),
            "date": r.get("date") or "",
        })
    return out


TG_SUB_BUDGET = 240   # 后台扫描的墙钟预算：卡住的一个频道不该拖垮整轮订阅扫描
_TG_FAIL_WORDS = ("限流", "HTTP", "不存在", "无效", "中断", "登录", "私有", "超时", "失效", "失败")


def _tg_scan_err(rows: List[dict], diag: dict) -> str:
    """0 条要分清「频道真没可读的东西」和「这次没读到」—— 后者不能当成没有新增记进 last_ids。"""
    if rows:
        return ""
    stopped = str(diag.get("stopped") or "")
    if diag.get("errors") or any(w in stopped for w in _TG_FAIL_WORDS):
        return stopped or "读不到任何条目（原因未上报）"
    return ""


RSS_HINTS = (".rss", ".atom", ".xml", "/feed", "/rss", "feed://")
RSS_AUDIO_EXT = (".mp3", ".m4a", ".aac", ".opus", ".ogg", ".wav", ".flac")


def _looks_like_feed(url: str) -> bool:
    u = str(url or "").strip().lower()
    return u.startswith("feed://") or any(h in u for h in RSS_HINTS)


def _sub_kind_of(sub: dict) -> str:
    """这条订阅走哪条读取分支：rss（XML 订阅源）/ tg（Telegram 频道）/ music（音乐平台歌单）/ ""（yt-dlp 直接读）。

    旧数据没有 kind 字段，所以认不出来时按链接形状现推，别让搬家前后的订阅走岔。
    """
    k = str(sub.get("kind") or "").strip().lower()
    if k in ("rss", "tg", "music"):
        return k
    url = str(sub.get("url") or "")
    if _tg_sub_ref(url, str(sub.get("mode") or ""))[0]:
        return "tg"
    if _looks_like_feed(url):
        return "rss"
    return "music" if _is_music_playlist(url) else ""


def _rss_pub_date(v) -> str:
    d = _norm_date_str(v)
    if d:
        return d
    s = str(v or "").strip()
    if not s:
        return ""
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(s).strftime("%Y-%m-%d")
    except Exception:
        return ""


def _rss_sub_entries(feed_url: str) -> Tuple[List[dict], str, str]:
    """RSS / Atom 订阅源 → (条目, 源标题, 报错)。读失败必须回错误，不能当成「没有新增」。"""
    mode, px = proxy_decision(feed_url)
    try:
        parsed = parse_rss_feed(feed_url, px if mode == "proxy" else "")
    except Exception as e:
        return [], "", f"RSS 读取失败：{type(e).__name__}: {e}"
    out: List[dict] = []
    for e in parsed.get("entries") or []:
        link = str(e.get("enclosure") or e.get("link") or "")
        if not link.startswith("http"):
            continue
        low = link.lower()
        out.append({
            "id": str(e.get("id") or link),
            "url": link,
            "title": str(e.get("title") or link)[:200],
            "date": _rss_pub_date(e.get("published")),
            "kind": "audio" if low.endswith(RSS_AUDIO_EXT) or "podcast" in low else "video",
        })
    if not out:
        return [], str(parsed.get("title") or ""), "这个订阅源里没有可下载的条目（条目里没有媒体链接）"
    return out, str(parsed.get("title") or ""), ""


def _is_music_playlist(url: str) -> bool:
    """链接是不是某家音乐平台的歌单页（musicdl 没装时也不能炸，判不了就当不是）。"""
    try:
        from music_search import playlist_owner
        return bool(playlist_owner(url))
    except Exception:
        return False


def _music_entry_id(title: str, artists: str, dur: int, link: str = "") -> str:
    """曲目的追新游标。

    不能用行上的缓存 id：每次解析都会另铸一个 uuid，那样每轮扫描都会把整张歌单当成新增。
    所以按「曲名 + 歌手 + 时长」拼一条可读的稳定键 —— 同一首歌换个平台收录也不会重复下。

    快列模式（yt-dlp 的 flat 子条目）给的行常常只有曲名：歌手与时长都空着时这条键就退化
    成曲名本身，一张歌单里两首同名不同曲（原声版与混音版、重名专辑曲）会并成一条，
    后一首被当成已读、永远下不到。那种情况下补一段链接哈希把两首分开；
    歌手或时长任一还在时不动键的形状，免得把已有订阅的游标整体挪一遍、隔日重下一张歌单。
    没传 link 就不加这段哈希：收藏清单那一头拿它当清单主键（存盘的），形状一改，
    清单里已有的「只有曲名」那些行就不再被认成同一首，会存进第二遍。
    """
    parts = [re.sub(r"\s+", " ", str(x or "")).strip() for x in (title, artists)]
    key = f"mus:{parts[0]}|{parts[1]}|{int(dur or 0)}"
    if link and not (parts[1] or int(dur or 0)):
        token = hashlib.md5(str(link).encode("utf-8")).hexdigest()[:12]
        # 曲名先截到 80：整条键末尾要砍到 120，超长曲名会把后面这段判别式切掉，
        # 切掉之后又变回「同名并一条」，而且看不出来。
        key = f"mus:{parts[0][:80]}|{parts[1]}|{int(dur or 0)}#{token}"
    return key[:120]


def _music_sub_entries(sub: dict) -> Tuple[List[dict], str, str]:
    """音乐歌单订阅扫一次 → (条目, 歌单名, 报错)。报错非空表示这次没读到，不能当成「没有新增」。"""
    url = str(sub.get("url") or "")
    out_dir = str(cfg.data.get("download_dir") or DEFAULT_DOWNLOAD_DIR)
    cookies = music_cookie_string().strip()
    proxy = music_proxy(url)
    prefer = str(cfg.data.get("music_playlist_mode") or "fast").strip().lower()
    srcs = list(cfg.data.get("musicdl_sources") or [])
    try:
        from music_search import parse_playlist
    except Exception as e:
        return [], "", f"音乐模块不可用：{type(e).__name__}: {e}"
    try:
        items = parse_playlist(url, sources=srcs, work_dir=out_dir, cookies=cookies,
                               proxy=proxy, log=log_mgr.log, prefer=prefer)
    except Exception as e:
        return [], "", f"歌单读取失败：{type(e).__name__}: {e}"
    from music_search import _LAST_PLAYLIST_DIAG as diag
    diag = dict(diag or {})
    if not items:
        return [], "", str(diag.get("hint") or "这张歌单没读到任何曲目（链接可能已失效、需要 Cookie 或代理）")
    from music_search import _dur_seconds, set_cached_song
    entries: List[dict] = []
    for row in items:
        title = str(row.get("title") or "").strip()
        artists = str(row.get("artists") or "").strip()
        dur = _dur_seconds(row.get("duration_s") or row.get("duration"))
        link = str(row.get("url") or "")
        sid = str(row.get("id") or "")
        if not sid and title:
            # 快列模式（yt-dlp 列曲目）只给曲名与歌页链接：这种行没有音频地址，而把
            # 「music.163.com/#/song?id=…」丢进通用队列让 yt-dlp 去抽，对音乐平台从来就不稳。
            # 所以立一个「只有曲名」的占位交给按曲名匹配那一轮去取地址 —— 与收藏清单空槽同一套。
            sid = str(uuid.uuid4())
            set_cached_song(sid, {"title": title, "artists": artists,
                                  "duration_s": int(dur or 0), "needs_match": True})
        entries.append({
            "id": _music_entry_id(title, artists, dur, link),
            "sid": sid,                              # 缓存 id：下载这一首轮里交给 musicdl
            "url": link,
            "title": title or "（无曲名）",
            "duration": dur,
            "kind": "audio",
            "date": "",
        })
    return entries, str(diag.get("name") or ""), ""


def _music_sub_label(url: str) -> str:
    """平台不报歌单名时的兜底标题：「网易云歌单 8123456789」比一串 URL 好认。"""
    owner = ""
    try:
        from music_search import playlist_owner
        owner = playlist_owner(url)
    except Exception:
        owner = ""
    if not owner:
        return ""
    short = NET_MUSIC_SOURCES.get(owner) or owner.replace("MusicClient", "")
    nums = re.findall(r"(\d{4,})", str(url or ""))
    return f"{short}歌单 {nums[0]}" if nums else f"{short}歌单"


class SubscriptionManager:
    def __init__(self, engine: "DownloaderEngine", cfg: ConfigManager, queue: "TaskQueue", tg: TelegramNotifier, log: Callable):
        self.engine = engine
        self.cfg = cfg
        self.queue = queue
        self.tg = tg
        self.log = log
        self.subs: List[dict] = []
        self._lock = threading.Lock()
        self._busy: set = set()   # 正在扫描的订阅 id：手动回填和定时扫描不能同时跑一条订阅
        self._stop = False
        self._thread: Optional[threading.Thread] = None
        self.load()

    def load(self):
        if SUBS_FILE.exists():
            try:
                with open(SUBS_FILE, "r", encoding="utf-8") as f:
                    self.subs = json.load(f)
            except Exception:
                self.subs = []
        else:
            self.subs = []

    def save(self):
        try:
            with self._lock:
                data = list(self.subs)
            with open(SUBS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def list(self) -> List[dict]:
        with self._lock:
            return list(self.subs)

    def add(self, url: str, title: str = "", mode: str = "", kind: str = "",
            auto_download: Optional[bool] = None) -> dict:
        url = normalize_url((url or "").strip())
        mode = "mt" if str(mode or "").strip().lower() == "mt" else ""
        kind = str(kind or "").strip().lower()
        kind = kind if kind in ("rss", "tg", "music") else ""
        # 界面上的来源标签只是预览，落到哪条读取分支由这里说了算：客户端说是音乐歌单、
        # 域名表不认（例如抖音单视频链接），就退回按链接重推。
        if kind == "music" and not _is_music_playlist(url):
            kind = ""
        if not kind:
            kind = "tg" if _tg_sub_ref(url, mode)[0] else (
                "rss" if _looks_like_feed(url) else ("music" if _is_music_playlist(url) else ""))
        if kind == "rss" and not url.startswith("http"):
            raise ValueError("RSS 订阅源要填完整的 http(s) 链接，例如 https://example.com/feed.xml")
        if not url.startswith("http") and kind != "tg":
            raise ValueError("无效 URL：要 http 链接、RSS 订阅源，或 Telegram 频道（@名字 / t.me/名字 / t.me/c/内部id）")
        hit = None
        with self._lock:
            for s in self.subs:
                if s.get("url") == url and (s.get("mode") or "") == mode and (not kind or _sub_kind_of(s) == kind):
                    hit = s
                    if auto_download is not None and bool(s.get("auto_download", True)) != bool(auto_download):
                        s["auto_download"] = bool(auto_download)
                    break
            if hit is None:
                hit = {
                    "id": uuid.uuid4().hex[:10],
                    "url": url,
                    "kind": kind,
                    "mode": mode,
                    "title": title or url,
                    "enabled": True,
                    "auto_download": True if auto_download is None else bool(auto_download),
                    "last_ids": [],
                    "last_check": "",
                    "last_error": "",
                    "added_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "new_count": 0,
                    "rules": {},
                    "feed": [],      # 上一轮窗口里看到的条目（轻量清单），用来分辨删帖与滑出
                    "archived": [],  # 上游已删除的条目留档
                }
                self.subs.insert(0, hit)
        self.save()
        return hit

    def remove(self, sid: str):
        with self._lock:
            self.subs = [s for s in self.subs if s.get("id") != sid]
        self.save()

    def set_enabled(self, sid: str, enabled: bool):
        with self._lock:
            for s in self.subs:
                if s.get("id") == sid:
                    s["enabled"] = bool(enabled)
                    break
        self.save()

    def set_rules(self, sid: str, raw: dict, mode: Optional[str] = None,
                  auto_download: Optional[bool] = None) -> dict:
        tpl = str((raw or {}).get("filename_template") or "").strip()
        if tpl and "%(ext)s" not in tpl:
            raise ValueError("命名模板结尾要留 %(ext)s，否则下下来的文件没有扩展名")
        if mode is not None and str(mode).strip().lower() not in ("", "mt"):
            raise ValueError("读取方式只能是「自动」或「用账号会话」")
        rules = _norm_sub_rules(raw)
        with self._lock:
            sub = next((s for s in self.subs if s.get("id") == sid), None)
            if not sub:
                raise ValueError("订阅不存在")
            sub["rules"] = rules
            if mode is not None:
                sub["mode"] = "mt" if str(mode).strip().lower() == "mt" else ""
            if auto_download is not None:
                sub["auto_download"] = bool(auto_download)
        self.save()
        self.log(f"订阅「{sub.get('title')}」规则已更新：{_sub_rules_text(rules)}")
        return rules

    def _entry_id(self, e: dict) -> str:
        return str(e.get("id") or e.get("url") or e.get("webpage_url") or "")

    def _entry_url(self, e: dict, sub_url: str) -> str:
        u = str(e.get("url") or e.get("webpage_url") or "")
        if not u and e.get("id") and "youtube" in (sub_url or "").lower():
            u = f"https://www.youtube.com/watch?v={e['id']}"
        return u

    def _rule_opts(self, r: dict) -> dict:
        """规则 → 入队选项；没设的项仍走全局设置。"""
        o = {
            "queue_name": "subscribe",
            "skip_downloaded": True,
            "allow_playlist": False,
            "audio_quality": self.cfg.data.get("audio_quality", "best"),
        }
        o["video_quality"] = r.get("video_quality") or self.cfg.data.get("video_quality", "best")
        o["format"] = r.get("format") or self.cfg.data.get("format", "mkv")
        o["audio_only"] = bool(r.get("audio_only")) or bool(self.cfg.data.get("audio_only", False))
        if r.get("filename_template"):
            o["filename_template"] = r["filename_template"]
        if r.get("download_dir"):
            o["download_dir"] = r["download_dir"]
        if r.get("run_ai") == "on":
            o["local_ai_transcribe"] = True
        elif r.get("run_ai") == "off":
            o["local_ai_transcribe"] = False
            o["local_ai_translate"] = False
        return o

    def _filter_entries(self, entries: List[dict], r: dict, hard_cap: int = 0):
        """按这条订阅的规则筛条目，返回 (入选, 被挡明细, 超出单次上限的部分)。"""
        kept, rejected = [], []
        for e in entries:
            ok, why = _sub_rule_match(e, r)
            if ok:
                kept.append(e)
            else:
                rejected.append((str(e.get("title") or self._entry_id(e))[:40], why))
        cap = int(r.get("max_per_scan") or 0)
        if hard_cap:
            cap = min(cap, hard_cap) if cap else hard_cap
        over = kept[cap:] if cap else []
        return (kept[:cap] if cap else kept), rejected, over

    def _enqueue(self, sub: dict, entries: List[dict], r: dict):
        if _sub_kind_of(sub) == "music":
            return self._enqueue_music(sub, entries)
        urls, samples = [], []
        for e in entries:
            u = self._entry_url(e, sub.get("url") or "")
            if u:
                urls.append(u)
                samples.append(e.get("title") or u)
        if urls:
            self.queue.add_urls(urls, self._rule_opts(r))
        return len(urls), samples

    def _enqueue_music(self, sub: dict, entries: List[dict]) -> Tuple[int, List[str]]:
        """新歌交给音乐页那套流程下：目录里已有的不再下第二份、只列了曲名的先按曲名匹配取址。"""
        ids = [str(e.get("sid") or "") for e in entries if e.get("sid")]
        urls = [str(e.get("url") or "") for e in entries
                if not e.get("sid") and str(e.get("url") or "").startswith("http")]
        samples = [str(e.get("title") or "")[:40] for e in entries][:5]
        if not ids and not urls:
            self.log(f"订阅「{sub.get('title')}」这批新歌一条都没法下"
                     "（歌单里既没有可取的曲目、也没有直链）", "warning")
            return 0, samples
        n = 0
        if ids:
            res = api_music_download({"ids": ids, "skip_downloaded": True})
            n += max(0, len(ids) - int(res.get("already") or 0))
            if res.get("message"):
                self.log(f"订阅「{sub.get('title')}」→ {res['message']}")
        if urls:
            res = api_music_download({"urls": urls, "skip_downloaded": True})
            n += int(res.get("count") or 0)
            if res.get("message"):
                self.log(f"订阅「{sub.get('title')}」→ {res['message']}")
        return n, samples

    def _tg_scan(self, sub: dict, ref: Tuple[str, str], wide: bool = False) -> Tuple[List[dict], str, str]:
        """Telegram 订阅源扫一次 → (条目, 频道标题, 报错)。报错非空表示这次没读到，不能当成「没有新增」。

        wide=True 是按日期窗回填历史：条数和时间预算都要放宽，否则窗口会被默认的 30 条 / 240 秒截断。
        """
        from telegram_channel import ALL_TYPES, PROXY_DIRECT, list_channel_history

        kind, target = ref
        r = _norm_sub_rules(sub.get("rules"))
        want = {t for x in (r.get("types") or []) for t in SUB_KIND_TO_TG.get(x) or ()}
        types = [t for t in ALL_TYPES if t in want] if want else list(ALL_TYPES)
        cap = int(r.get("max_per_scan") or 0) or SUB_CAP_DEFAULT
        budget = TG_SUB_BUDGET if not wide else max(TG_SUB_BUDGET, 900)
        limit = max(30, min(300, cap * 3)) if not wide else max(500, min(2000, cap * 25))
        if kind == "mt":
            st = tg_session.status()
            if not st.get("logged_in"):
                return [], "", ("这个账号还没登录 Telegram，私有 / 需登录频道的订阅读不到："
                                "去 Telegram 页登录会话"
                                + ("" if st.get("configured") else "（还差 api_id / api_hash）"))
            items, diag = tg_session.list_media(
                target, limit=limit, types=types,
                since=r.get("since") or "", until=r.get("until") or "")
            rows = _tg_sub_entries(items, True)
            return rows, str(diag.get("title") or target), _tg_scan_err(rows, diag)
        mode, px = proxy_decision("https://t.me/" + target)
        proxy = px if mode == "proxy" else (PROXY_DIRECT if mode == "direct" else "")
        items, diag = list_channel_history(
            target, limit=limit, types=types,
            since=r.get("since") or "", until=r.get("until") or "",
            budget=budget, proxy=proxy, log=self.log)
        rows = _tg_sub_entries(items, False)
        return rows, target, _tg_scan_err(rows, diag)

    def scan_one(self, sub: dict, auto_download: bool = True, backfill: dict = None) -> int:
        """扫描订阅，返回新增数量（每条订阅按自己的规则筛、按自己的口径下）。

        同一条订阅同一时刻只允许一轮扫描 —— 手动回填撞上定时扫描会重复入队同一批条目。
        """
        sid = str(sub.get("id") or "")
        with self._lock:
            if sid in self._busy:
                self.log(f"订阅「{sub.get('title') or sub.get('url')}」上一轮还没扫完，这次先跳过", "warning")
                return 0
            self._busy.add(sid)
        try:
            return self._scan_one_inner(sub, auto_download=auto_download, backfill=backfill)
        finally:
            with self._lock:
                self._busy.discard(sid)

    def _fetch_sub_entries(self, sub: dict, wide: bool = False) -> Tuple[List[dict], str, str]:
        """按这条订阅的来源读一次 → (条目, 来源标题, 报错)。报错非空表示这次没读到，不能当成「没有新增」。

        正式扫描和「同步计划预览」共用这一条路，预览看到的才是下一轮真要处理的那批条目；
        这里只读不写，sub 上的字段一个都不动。
        """
        url = sub.get("url") or ""
        kind = _sub_kind_of(sub)
        if kind == "rss":
            return _rss_sub_entries(url)
        if kind == "music":
            entries, pl_name, err = _music_sub_entries(sub)
            return entries, (pl_name or _music_sub_label(url)), err
        ref = ("", "") if kind == "rss" else _tg_sub_ref(url, str(sub.get("mode") or ""))
        if ref[0]:
            return self._tg_scan(sub, ref, wide=wide)
        info = self.engine.get_info(url, self.cfg.data)
        if not info:
            return [], "", "解析不到这个链接的内容（yt-dlp 没有返回信息），可能是链接已失效或需要登录 Cookie"
        if info.get("_type") == "playlist" or info.get("entries"):
            return [e for e in (info.get("entries") or []) if e], str(info.get("title") or ""), ""
        # 单视频也当订阅源（检测更新意义不大，但游标照记）
        return [info], str(info.get("title") or ""), ""

    def _light(self, sub: dict, entries: List[dict], cap: int = 50) -> List[dict]:
        """条目收成预览用的轻记录：标题 / 日期 / 时长 / 链接。"""
        out = []
        for e in entries[:cap]:
            out.append({
                "title": str(e.get("title") or self._entry_id(e) or "（无标题）")[:120],
                "date": _sub_date(e),
                "duration": int(_sub_duration(e)),
                "url": (self._entry_url(e, sub.get("url") or "") or "")[:200],
            })
        return out

    def _feed_round(self, sub: dict, rows: List[dict], now: str) -> int:
        """每轮追新后更新上游窗口对照清单，把本轮从源头消失的条目录进归档 → 返回本轮新归档几条。"""
        feed, deleted, _aged = _feed_sync(sub.get("feed") or [], rows, now)
        sub["feed"] = feed
        if deleted:
            arch = list(sub.get("archived") or [])
            arch[:0] = deleted
            sub["archived"] = arch[:SUB_ARCHIVE_CAP]
            names = "、".join((d.get("title") or d.get("id") or "")[:40] for d in deleted[:3])
            self.log(f"订阅「{sub.get('title') or sub.get('url')}」本轮有 {len(deleted)} 条已从源头消失"
                     f"（上游删除，比它更旧的条目还在），已记入归档：{names}"
                     + ("等" if len(deleted) > 3 else ""))
        if sub.get("archived"):
            back = {str(r.get("id") or "") for r in feed}
            kept = [a for a in sub["archived"] if str(a.get("id") or "") not in back]
            if len(kept) != len(sub["archived"]):
                self.log(f"订阅「{sub.get('title') or sub.get('url')}」有 "
                         f"{len(sub['archived']) - len(kept)} 条重新出现在源头，已从归档清单退回")
            sub["archived"] = kept
        return len(deleted)

    def preview_one(self, sub: dict) -> dict:
        """干跑一轮追新：读源、按规则筛、算上游删除归档 —— 不入队、不动游标、不落盘。"""
        sid = str(sub.get("id") or "")
        kind = _sub_kind_of(sub)
        r = _norm_sub_rules(sub.get("rules"))
        plan = {
            "id": sid, "title": sub.get("title") or sub.get("url") or "", "kind": kind,
            "url": sub.get("url") or "", "rules_text": _sub_rules_text(r),
            "last_check": str(sub.get("last_check") or ""),
            "cursor": len(sub.get("last_ids") or []),
            "error": "", "busy": False, "read": 0, "new": 0, "seen": 0, "is_first": False,
            "picked": [], "picked_total": 0, "rejected": [], "rejected_total": 0, "over": 0,
            "archive": [], "archive_total": 0, "archived_count": len(sub.get("archived") or []),
            "enqueue": False, "why": "",
        }
        with self._lock:
            if sid in self._busy:
                plan["busy"] = True
                plan["error"] = ("这一条正在扫描（定时或手动），这轮先不预览 —— "
                                 "预览也要把源读一遍，两遍并行会重复取数")
                return plan
        entries, _src_title, err = self._fetch_sub_entries(sub)
        if err:
            plan["error"] = err
            return plan
        win_n, _seen_cap = _sub_window(kind)
        rows = entries[:win_n]
        known = set(sub.get("last_ids") or [])
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        plan["read"] = len(rows)
        plan["seen"] = sum(1 for e in rows if not (self._entry_id(e) and self._entry_id(e) not in known))
        new_entries = [e for e in rows if self._entry_id(e) and self._entry_id(e) not in known]
        plan["new"] = len(new_entries)
        plan["is_first"] = not known
        _feed, would_del, _aged = _feed_sync(sub.get("feed") or [], rows, now)
        plan["archive"] = [{"title": d.get("title") or d.get("id") or "",
                            "url": d.get("url") or "", "last_seen": d.get("last_seen") or ""}
                           for d in would_del[:20]]
        plan["archive_total"] = len(would_del)
        do_dl = bool(sub.get("auto_download", True)) and bool(self.cfg.data.get("sub_auto_download", True))

        if plan["is_first"]:
            first_n = int(self.cfg.data.get("sub_first_download_n") or 0)
            if first_n > 0 and do_dl:
                picked, rejected, over = self._filter_entries(entries, r, hard_cap=first_n)
                plan["picked"], plan["picked_total"] = self._light(sub, picked), len(picked)
                plan["rejected"], plan["rejected_total"] = _reject_rows(rejected), len(rejected)
                plan["over"] = len(over)
                plan["enqueue"] = bool(picked)
                plan["why"] = f"首轮：现有 {len(rows)} 条记为已读，并按设置下载最近 {first_n} 条"
            else:
                plan["why"] = (f"首轮：只把现有 {len(rows)} 条记为已读，不下载"
                               "（设置页「订阅首次下载条数」为 0；要补下历史请用「按日期回填」）")
            return plan
        if not new_entries:
            plan["why"] = "本轮没有未读条目"
            if would_del:
                plan["why"] += f"；会有 {len(would_del)} 条从源头消失并记入归档"
            return plan
        if kind == "music" and do_dl and _MUSIC_JOB.get("running"):
            plan["busy"] = True
            plan["why"] = (f"上一批音乐下载还没结束：真执行这一轮会整轮跳过，"
                           f"{len(new_entries)} 首不会记成已读，下一轮再补")
            return plan
        picked, rejected, over = self._filter_entries(new_entries, r)
        plan["picked"], plan["picked_total"] = self._light(sub, picked), len(picked)
        plan["rejected"], plan["rejected_total"] = _reject_rows(rejected), len(rejected)
        plan["over"] = len(over)
        if not do_dl:
            which = []
            if not sub.get("auto_download", True):
                which.append("这条订阅的「自动下载」已关")
            if not self.cfg.data.get("sub_auto_download", True):
                which.append("设置页的「订阅新条目自动下载」已关")
            plan["why"] = f"新增 {len(new_entries)} 条只列出、不入队：" + "、".join(which)
            return plan
        if not picked:
            plan["why"] = f"新增 {len(new_entries)} 条，按规则[{plan['rules_text']}]一条都不该下"
            return plan
        plan["enqueue"] = True
        plan["why"] = (f"新增 {len(new_entries)} 条，按规则[{plan['rules_text']}]入队 {len(picked)} 条"
                       + (f"，另有 {len(over)} 条超出单次上限留到下次" if over else ""))
        return plan

    def clear_archived(self, sid: str, entry_id: str = "") -> int:
        """删掉「上游已删除」的归档记录（单条或整单）。只清账本，不动追新游标 ——
        条目就算重新出现在源头，也仍按已读处理，不会因为清过归档而重下一遍。"""
        with self._lock:
            sub = next((s for s in self.subs if s.get("id") == sid), None)
            if not sub:
                raise ValueError("订阅不存在")
            arch = list(sub.get("archived") or [])
            kept = [a for a in arch if str(a.get("id") or "") != entry_id] if entry_id else []
            sub["archived"] = kept
            removed = len(arch) - len(kept)
        self.save()
        return removed

    def _scan_one_inner(self, sub: dict, auto_download: bool = True, backfill: dict = None) -> int:
        entries, src_title, err = self._fetch_sub_entries(sub, wide=bool(backfill))
        if err:
            sub["last_error"] = err
            self.save()
            self.log(f"订阅「{sub.get('title') or sub.get('url')}」读不到：{err}", "warning")
            return 0
        url = sub.get("url") or ""
        kind = _sub_kind_of(sub)
        sub["last_error"] = ""
        if src_title:
            sub["title"] = src_title
        sub["title"] = sub.get("title") or url

        r = _norm_sub_rules(sub.get("rules"))
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if backfill:
            win = {k: v for k, v in _norm_sub_rules(backfill).items() if k in ("since", "until")}
            r.update(win)
            return self._backfill(sub, entries, r, now)

        rtext = _sub_rules_text(r)
        known = set(sub.get("last_ids") or [])
        new_entries = []
        all_ids = []
        win_n, seen_cap = _sub_window(kind)
        for e in entries[:win_n]:
            eid = self._entry_id(e)
            if not eid:
                continue
            all_ids.append(eid)
            if eid not in known:
                new_entries.append(e)

        do_dl = bool(auto_download) and bool(sub.get("auto_download", True)) \
            and bool(self.cfg.data.get("sub_auto_download", True))

        if kind == "music" and do_dl and new_entries and _MUSIC_JOB.get("running"):
            # 音乐批量只有一条通道（进度是全局单槽），两批并行会互相盖掉对方的进度。
            # 这里必须原样返回：这一轮的新歌不能记成已读，记了就没人补下了。
            self.log(f"订阅「{sub.get('title')}」有 {len(new_entries)} 首新歌，"
                     "但上一批音乐下载还没结束 —— 这次不记录新增，等下轮扫描再补", "warning")
            return 0

        # 上游窗口对照：这一轮读到的这批就是下轮的比较基准，中间空掉的那些记成上游删除
        self._feed_round(sub, entries[:win_n], now)

        # 首次订阅：默认只记 ID；sub_first_download_n>0 时下载最近 N 条（同样受规则约束）
        is_first = not known
        if is_first:
            first_n = int(self.cfg.data.get("sub_first_download_n") or 0)
            sub["last_ids"] = all_ids[:win_n]
            sub["last_check"] = now
            sub["new_count"] = 0
            self.save()
            if first_n > 0 and do_dl:
                picked, rejected, _over = self._filter_entries(entries, r, hard_cap=first_n)
                n, _ = self._enqueue(sub, picked, r)
                extra = f"，规则挡掉 {len(rejected)} 条" if rejected else ""
                self.log(f"订阅初始化: {sub.get('title')} 记录 {len(all_ids)} 条，"
                         f"按规则[{rtext}]首次下载 {n} 条{extra}")
                return n
            self.log(f"订阅初始化: {sub.get('title')} 记录 {len(all_ids)} 条，跳过首次下载")
            return 0

        if not new_entries:
            sub["last_check"] = now
            self.save()
            return 0

        picked, rejected, over = self._filter_entries(new_entries, r)
        # 超出单次上限的那些不算见过 —— 下次扫描还会补上，规则只管节奏不管取舍
        defer_ids = {self._entry_id(e) for e in over}
        mark = [i for i in all_ids if i not in defer_ids]
        sub["last_ids"] = list(dict.fromkeys(mark + list(known)))[:300]
        sub["last_check"] = now
        sub["new_count"] = int(sub.get("new_count") or 0) + len(new_entries)
        self.save()

        extra = ""
        if rejected:
            extra += f"，规则挡掉 {len(rejected)} 条（{rejected[0][0]}：{rejected[0][1]}"
            extra += f" 等）" if len(rejected) > 1 else "）"
        if over:
            extra += f"，另有 {len(over)} 条超出单次上限，留到下次扫描"

        samples = []
        if do_dl:
            n, samples = self._enqueue(sub, picked, r)
            if n:
                self.log(f"订阅「{sub.get('title')}」新增 {len(new_entries)} 条，"
                         f"按规则[{rtext}]入队 {n} 条{extra}")
            else:
                self.log(f"订阅「{sub.get('title')}」新增 {len(new_entries)} 条，"
                         f"按规则[{rtext}]一条都不该下{extra}")
        else:
            samples = [e.get("title") or self._entry_id(e) for e in new_entries[:5]]
            self.log(f"订阅「{sub.get('title')}」新增 {len(new_entries)} 条（未开自动下载）{extra}")

        self.tg.notify_sub(sub.get("title") or url, len(new_entries), samples[:5])
        return len(new_entries)

    def _backfill(self, sub: dict, entries: List[dict], r: dict, now: str) -> int:
        """按日期窗回填一次历史：不看追新游标，只把这次真正入队的条目标成已见。"""
        picked, rejected, over = self._filter_entries(entries, r)
        rtext = _sub_rules_text({**r})
        no_date = _sub_kind_of(sub) == "music" and not (r.get("since") or r.get("until"))
        win = "整张歌单" if no_date else f"{r.get('since') or '最早'}~{r.get('until') or '最新'}"
        byd = "" if no_date else "按日期"
        scope = "歌单" if no_date else "窗口"
        sub["last_check"] = now
        if not picked:
            self.save()
            why = f"（例如「{rejected[0][0]}」：{rejected[0][1]}）" if rejected else ""
            self.log(f"订阅「{sub.get('title')}」{byd}回填 {win}：{scope}内没有可下条目{why}", "warning")
            return 0
        n, samples = self._enqueue(sub, picked, r)
        ids = [self._entry_id(e) for e in picked if self._entry_id(e)]
        # 只标记这次下掉的：窗口外的条目还得留给以后的追新，不能被回填顺手吞掉
        sub["last_ids"] = list(dict.fromkeys(ids + list(sub.get("last_ids") or []))) \
            [:_sub_window(_sub_kind_of(sub))[1]]
        sub["new_count"] = int(sub.get("new_count") or 0) + len(picked)
        self.save()
        extra = f"，另有 {len(rejected)} 条被规则{'挡掉' if no_date else '或窗口挡掉'}" if rejected else ""
        if over:
            extra += f"，还有 {len(over)} 条在{scope}内但超出单次上限 —— 再点一次回填可以接着往下取"
        self.log(f"订阅「{sub.get('title')}」{byd}回填 {win}：入选 {len(picked)} 条，入队 {n} 条"
                 f"（规则[{rtext}]）{extra}")
        self.tg.notify_sub(sub.get("title") or sub.get("url") or "", len(picked), samples[:5])
        return len(picked)

    def scan_all(self) -> dict:
        total_new = 0
        checked = 0
        with self._lock:
            items = [s for s in self.subs if s.get("enabled")]
        for s in items:
            try:
                n = self.scan_one(s, auto_download=bool(self.cfg.data.get("sub_auto_download", True)))
                total_new += n
                checked += 1
            except Exception as e:
                self.log(f"订阅扫描异常: {e}", "warning")
        return {"checked": checked, "new": total_new}

    def start_scheduler(self):
        if self._thread and self._thread.is_alive():
            return

        def loop():
            while not self._stop:
                try:
                    interval = max(15, int(self.cfg.data.get("sub_interval_min") or 60))
                    # 分段 sleep，便于停止
                    for _ in range(interval * 6):
                        if self._stop:
                            return
                        time.sleep(10)
                    if self.subs:
                        self.log("开始定时扫描订阅…")
                        res = self.scan_all()
                        self.log(f"订阅扫描完成: 检查 {res['checked']} 源，新增 {res['new']}")
                except Exception as e:
                    self.log(f"订阅调度异常: {e}", "warning")

        self._stop = False
        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()

    def stop_scheduler(self):
        self._stop = True


# -------------------- 磁力 / 种子（一律交给本机 aria2） --------------------
from aria2_client import BT_KEYS  # tellStatus 一次要读的字段，与客户端保持同一份

_MAGNET_XT_RE = re.compile(r"^urn:btih:([0-9a-fA-F]{40}|[A-Za-z2-7]{32})$")
_BT_WATCH: Dict[str, dict] = {}          # gid → {task_id, ratio, seconds}
_BT_WATCH_LOCK = threading.Lock()


def parse_torrent_ref(url: str) -> Optional[dict]:
    """把磁力链接或本地 .torrent 拆成 {kind, info_hash, name, path}；两类都不是就回 None。

    磁力只认 xt=urn:btih（40 位十六进制或 32 位 base32）。别的 xt（ipfs 之类）aria2 也接不了，
    与其让任务卡在队列里，不如在入队当场说清楚。
    """
    u = (url or "").strip()
    low = u.lower()
    if low.startswith("http://") or low.startswith("https://"):
        return None  # 网上的 .torrent 链接交给普通下载，本地这条路只认已经存在的种子文件
    if low.startswith("magnet:"):
        try:
            q = parse_qs(urlsplit(u).query, keep_blank_values=True)
        except ValueError:
            return None
        xt = (q.get("xt") or [""])[0].strip()
        m = _MAGNET_XT_RE.match(xt)
        if not m:
            return None
        dn = unquote((q.get("dn") or [""])[0]).strip()
        return {"kind": "magnet", "info_hash": m.group(1).lower(),
                "name": dn or m.group(1).lower()[:12], "path": "", "has_dn": bool(dn)}
    if low.startswith("file://"):
        p = unquote(urlsplit(u).path)
        p = p[1:] if len(p) > 2 and p[2] == ":" else p
    elif low.endswith(".torrent"):
        p = u
    else:
        return None
    if not p.lower().endswith(".torrent"):
        return None
    try:
        ap = str(Path(p).resolve())
    except OSError:
        return None
    return {"kind": "torrent-file", "info_hash": "", "name": Path(ap).stem, "path": ap}


def _benc_skip(raw: bytes, i: int) -> int:
    """跳到 raw[i] 这个 bencode 值的末尾下标。

    必须按长度前缀整体跳过二进制段：pieces 那种字节里满是 d/l/e，靠数字符会算错位置。
    """
    c = raw[i:i + 1]
    if c == b"i":
        j = raw.index(b"e", i)
        return j + 1
    if c in (b"l", b"d"):
        j = i + 1
        while True:
            n = raw[j:j + 1]
            if n == b"e":
                return j + 1
            if not n:
                raise ValueError("种子内容不完整")
            j = _benc_skip(raw, j)
    if c.isdigit():
        j = i
        while raw[j:j + 1].isdigit():
            j += 1
        if raw[j:j + 1] != b":":
            raise ValueError("种子格式不对")
        return j + int(raw[i:j]) + 1
    raise ValueError("种子格式不对")


def torrent_info_hash(data: bytes) -> str:
    """info 段原始字节的 SHA-1，和磁力链接 xt=urn:btih 用的是同一个算法；解析不出就回空串。

    只认顶层字典里键名正好是 info 的那一段，不去文件里搜 "4:info"——那个串也可能出现在二进制段里。
    """
    try:
        if (data or b"")[:1] != b"d":
            return ""
        j = 1
        while data[j:j + 1] != b"e":
            ks = j
            j = _benc_skip(data, j)
            vs = j
            j = _benc_skip(data, j)
            if data[ks:vs] == b"4:info":
                return hashlib.sha1(data[vs:j]).hexdigest()
        return ""
    except Exception:
        return ""


def torrent_bytes_identity(data: bytes) -> str:
    """种子的身份 = info 段哈希（拿不到时退回整文件哈希）。

    同一个内容换个 tracker、换个文件名，甚至一条走磁力、一条走本地种子，
    都该合成一条任务；按 .torrent 文件整体哈希就分不出来了。
    """
    ih = torrent_info_hash(data or b"")
    if ih:
        return ih
    return hashlib.sha1(data or b"").hexdigest()[:16]


def torrent_file_identity(path: str) -> str:
    try:
        return torrent_bytes_identity(Path(path).read_bytes())
    except OSError:
        return "path:" + str(path)


def bt_torrent_name(data: bytes) -> str:
    """取出 .torrent 里 info 段的名称，取不到回空串。

    自动分类要认的是种子内部的名字，不是本地那个文件名：同一份内容换个 .torrent 文件名还是那个种子，
    按文件名归类就等于让用户手工改一次名，前后两次落到两个目录里。
    """
    try:
        if (data or b"")[:1] != b"d":
            return ""
        j = 1
        while data[j:j + 1] != b"e":
            ks = j
            j = _benc_skip(data, j)
            vs = j
            j = _benc_skip(data, j)
            # 只认顶层键正好叫 info 的那一段：注释里塞一个 "4:info" 不算
            if data[ks:vs] != b"4:info":
                continue
            if data[vs:vs + 1] != b"d":
                return ""
            k = vs + 1
            while data[k:k + 1] != b"e":
                s = k
                k = _benc_skip(data, k)
                t = k
                k = _benc_skip(data, k)
                if data[s:t] != b"4:name":
                    continue
                raw = data[t:k]
                head, sep, body = raw.partition(b":")
                if not sep or not head.isdigit():
                    return ""
                return body[:int(head)].decode("utf-8", "replace")
            return ""
        return ""
    except Exception:
        return ""


def torrent_reject_reason(url: str) -> str:
    """磁力/种子链接为什么收不下（收得下回空串）：报错要能指着链接说出缺哪一段。"""
    u = (url or "").strip()
    low = u.lower()
    if not (low.startswith("magnet:") or low.startswith("file://") or low.endswith(".torrent")):
        return ""
    if parse_torrent_ref(u):
        return ""
    if low.startswith("magnet:"):
        if "xt=urn:btih" not in low:
            return "这条 magnet 里没有 xt=urn:btih 内容标识，定不下要下哪个种子"
        return "xt=urn:btih 的取值既不是 40 位十六进制也不是 32 位 base32，aria2 认不出来"
    return "本地种子要指向一个 .torrent 文件（file:// 或直接写路径都行），这条对不上"


def _bt_client(cfg: dict):
    from aria2_client import Aria2Client
    return Aria2Client(
        rpc_url=cfg.get("aria2_rpc") or "http://127.0.0.1:6800/jsonrpc",
        secret=cfg.get("aria2_secret") or "",
    )


def _bt_add_options(cfg: dict, log_fn: Callable = lambda *a, **k: None) -> dict:
    """把「加料」设置摊成 aria2 添加任务时的选项。

    这些只能在新任务提交时给：实测改不动——aria2.changeOption 对 bt-tracker 当场回
    「Cannot change option for GID#…」，对 seed-ratio / bt-prioritize-piece / check-integrity
    甚至是回 OK 但值原样不动。所以界面上只有下载/上传限速能写成「立即生效」，其余都得写明
    「对新任务生效」。tracker 抓不到就照旧下载，只是少了几个发现节点的入口，别把它变成拦路。
    """
    out: Dict[str, str] = {}
    try:
        trk, note = bt_trackers.effective(
            cfg, APP_DIR, getter=lambda u: http_get_bytes(u, timeout=20))
    except Exception as e:
        trk, note = [], f"读 tracker 列表失败：{type(e).__name__}: {str(e)[:120]}"
    if trk:
        out["bt-tracker"] = ",".join(trk)
    if note:
        log_fn(f"tracker：{note}", "warning")
    dl = bt_trackers.norm_speed(cfg.get("bt_dl_limit"))
    ul = bt_trackers.norm_speed(cfg.get("bt_ul_limit"))
    if dl:
        out["max-download-limit"] = dl
    if ul:
        out["max-upload-limit"] = ul
    if cfg.get("bt_prioritize_piece"):
        out["bt-prioritize-piece"] = "head,tail"
    return out


_BT_RULE_MODES = ("contains", "regex")
# 规则可以问「名字」也可以问「链接」：磁力/种子那侧一直是名字（种子里的标题才是人能读懂的东西），
# 而普通下载（YouTube / B 站 / 直链）根本没有名字可比，只有 URL。两类规则排在同一张表里，
# 同一条匹配口径（包含 / 正则、忽略大小写、从上往下先命中先得），只是问的对象不同。
_BT_RULE_SCOPES = ("name", "url")
_BT_SCOPE_LABELS = {"name": "名字", "url": "链接"}


def bt_rule_subdir(raw) -> Tuple[str, str]:
    """把规则里的「存到」收成下载目录下面的相对子目录；收成不了就说明为什么。

    只吃相对路径：规则拿来做批量归类，一条写成绝对路径或带 .. 的规则，只要有人把名字打错，
    成品就会落到下载目录之外，回头连程序自己都说不清它去了哪儿。
    """
    s = str(raw or "").strip()
    if not s:
        return "", ""
    parts = [p for p in re.split(r"[\\/]+", s) if p]
    if not parts:
        return "", ""
    if any(":" in p or p in (".", "..") for p in parts):
        return "", f"要写成下载目录下面的相对子目录（例如 剧集/2026），不能带盘符或 ..：{s[:60]}"
    return "/".join(parts), ""


def bt_rules_clean(raw) -> Tuple[List[dict], List[str]]:
    """把界面传来的规则列表收成统一形状，顺手把用不了的挑出来，一条条点名给用户看。"""
    out: List[dict] = []
    bad: List[str] = []
    for i, r in enumerate(raw or [], 1):
        if not isinstance(r, dict):
            bad.append(f"第 {i} 条不是规则的形状（每条要写名称、匹配方式、关键词、存到）")
            continue
        name = str(r.get("name") or "").strip()[:60] or f"规则 {i}"
        pattern = str(r.get("pattern") or "")
        mode = str(r.get("mode") or "contains").strip().lower()
        scope = str(r.get("scope") or "name").strip().lower()
        if scope not in _BT_RULE_SCOPES:
            bad.append(f"第 {i} 条「{name}」的匹配对象只认「名字」或「链接」，现在收到的是「{scope[:20]}」")
            continue
        if not pattern.strip():
            bad.append(f"第 {i} 条「{name}」没写要匹配的"
                       + ("链接" if scope == "url" else "名字"))
            continue
        if mode not in _BT_RULE_MODES:
            bad.append(f"第 {i} 条「{name}」的匹配方式只认「包含」或「正则」，现在收到的是「{mode[:20]}」")
            continue
        sub, why = bt_rule_subdir(r.get("subdir"))
        if why:
            bad.append(f"第 {i} 条「{name}」的存到哪里不对：{why}")
            continue
        if mode == "regex":
            try:
                re.compile(pattern)
            except re.error as e:
                bad.append(f"第 {i} 条「{name}」的正则没写对：{e}")
                continue
        out.append({"name": name, "pattern": pattern, "mode": mode, "subdir": sub,
                    "scope": scope, "enabled": bool(r.get("enabled", True))})
    return out, bad


def bt_rule_match(name: str, rules: List[dict], scope: str = "name") -> Tuple[dict, str]:
    """按上下顺序问一遍，命中第一条就定下来（照 qBittorrent 自动分类的口径：先命中先得）。

    只问 scope 这一类规则（名字 / 链接）—— 一张表里两种规则混排时，
    「这条是问链接的」不能被拿去比种子名，否则 `https://` 这种词会把所有种子都收走。

    比大小写一律忽略：种子里的名字同一批人一会儿 1080P 一会儿 1080p，
    分两种写法只会让规则表越写越长。
    """
    s = str(name or "")
    low = s.lower()
    for r in rules or []:
        if not isinstance(r, dict) or not r.get("enabled", True):
            continue
        if str(r.get("scope") or "name") != scope:
            continue
        pat = str(r.get("pattern") or "")
        if not pat:
            continue
        if str(r.get("mode") or "contains") == "regex":
            try:
                if re.search(pat, s, re.IGNORECASE):
                    return r, f"正则「{pat[:40]}」对上了「{s[:60]}」"
            except re.error:
                continue  # 保存时已经挡过一遍；这里再撞上就跳过这条，不能让它把任务卡住
            continue
        if pat.lower() in low:
            return r, f"「{s[:60]}」里含「{pat[:40]}」"
    return None, ""


def bt_rule_name(ref: dict, log_fn: Callable = lambda *a, **k: None) -> Tuple[str, str]:
    """自动分类这一刻手上能拿到的名字，以及它从哪来（说不清来源就别装作说得清）。"""
    kind = str((ref or {}).get("kind") or "")
    if kind == "magnet":
        if (ref or {}).get("has_dn"):
            return str(ref.get("name") or ""), "磁力链接里带的 dn"
        return "", "这条磁力没写 dn，文件名要等种子元数据到手才知道"
    p = str((ref or {}).get("path") or "")
    try:
        nm = bt_torrent_name(Path(p).read_bytes())
    except (OSError, ValueError) as e:
        nm = ""
        log_fn(f"读种子文件里的名称失败：{type(e).__name__}: {str(e)[:100]}", "warning")
    if nm:
        return nm, "种子文件内的名称"
    stem = Path(p).stem if p else str((ref or {}).get("name") or "")
    return stem, "种子文件名（种子内没读到名称）"


def _rule_decide(name: str, url: str, rules: List[dict]) -> Tuple[dict, str]:
    """先问名字规则、没中再问链接规则 —— 真正落点与界面「试跑」共用这一句，免得两处顺序漂移。"""
    hit, why = (bt_rule_match(name, rules, "name") if name else (None, ""))
    if not hit and url:
        hit, why = bt_rule_match(url, rules, "url")
    return hit, why


def bt_target_dir(ref: dict, cfg: dict, base_dir: str,
                  log_fn: Callable = lambda *a, **k: None,
                  url: str = "") -> Tuple[str, str, str]:
    """按自动分类规则决定这个种子存到哪儿，回 (落盘目录, 分类名, 说给用户听的缘故)。

    先问「名字」规则（种子里的标题是人能读懂的东西），名字没命中才问「链接」规则
    （磁力链接多半只有一串 xt 哈希，按链接分类靠的是 dn / 来源写法）。
    没配规则就原样回默认目录，一条日志都不多写——不该出现「开着默认设置却莫名其妙多了层目录」。
    """
    rules = [r for r in (cfg.get("bt_auto_rules") or []) if isinstance(r, dict)]
    if not rules:
        return base_dir, "", ""
    name, whence = bt_rule_name(ref, log_fn)
    hit, why = _rule_decide(name, url, rules)
    has_url = any(str(r.get("scope") or "name") == "url" for r in rules)
    if name:
        head = (f"名字「{name[:60]}」与链接都没命中任何规则" if has_url
                else f"名字「{name[:60]}」没命中任何规则")
    else:
        head = f"这条现在还没有可比的名字（{whence}）"
    if hit:
        sub = str(hit.get("subdir") or "")
        if not sub:
            log_fn(f"自动分类：{why} → 规则「{hit.get('name')}」没填子目录，仍存默认目录")
            return base_dir, "", f"规则「{hit.get('name')}」没填子目录"
        target = str(Path(base_dir) / sub)
        log_fn(f"自动分类：{why} → 规则「{hit.get('name')}」，存到 {target}")
        return target, str(hit.get("name") or ""), f"命中规则「{hit.get('name')}」（{why}）"
    fb, bad = bt_rule_subdir(cfg.get("bt_auto_fallback"))
    if bad:
        log_fn(f"自动分类的兜底目录用不了：{bad}；{head}，仍存默认目录", "warning")
    elif fb:
        target = str(Path(base_dir) / fb)
        log_fn(f"自动分类：{head} → 按兜底目录存到 {target}")
        return target, "兜底", f"没命中规则，按兜底目录 {fb}"
    log_fn(f"自动分类：{head}，仍存默认目录")
    return base_dir, "", "没命中规则"


def _opts_dir_is_manual(task_dir, global_dir) -> bool:
    """这一批任务是不是用户自己在「保存目录」那一格点了别的目录。

    界面那一格预填的就是全局目录（loadConfig 里 opts.download_dir = data.download_dir），
    所以「非空」不等于手动指定，只有与全局不一样才算。判错的代价都看得见：当成手动则链接
    规则永远不生效，当成非手动则用户手选的目录被规则改掉 —— 后一条是「开着默认设置却多了
    一层目录」的翻版，所以规则给手动的让路，并在日志写明。
    """
    a = str(task_dir or "").strip()
    if not a:
        return False
    return not _same_dir(a, str(global_dir or "").strip())


# 成品换了容器之后，工具报回来的名字仍是换容器前那一个（见 resolve_written_file）。
# 这一份名单只在这里定义，两处调用点共用，别再抄第二份出来各自漂移。
REMUX_FALLBACK_EXTS = (".mp4", ".mkv", ".webm", ".mp3", ".m4a", ".flac", ".wav")


def resolve_written_file(pth: str, prefer=()) -> str:
    """工具报的路径不在场时，按同一个基名换扩展，找回真正写出来的那个文件。

    挂 FFmpegVideoRemuxer（目标容器=mkv/mp4/webm）或转音频时，yt-dlp 处理完写回分集 info 的
    filepath 仍是换容器前那个名字，成品其实躺在旁边换了后缀。照那个名字判在场，整批就得到
    「写出 0 个文件」，再被完整性校验说成「下载完成但文件不可用」—— 文件明明在盘上。

    给的名字在场就原样还；prefer 是这一趟要的容器（先找它，因为同一个基名旁边可能既躺着
    上一次的旧容器、又躺着这次的成品，按目标容器先找才不会认领错文件）；都没找到仍把原名
    还回去，让调用方照实说「文件不存在」，这里不替工具撒谎。
    """
    if not pth:
        return ""
    p = Path(pth)
    if p.exists():
        return str(p)
    order: List[str] = []
    for e in (prefer or ()):
        ext = str(e or "").strip().lower()
        ext = ("." + ext.lstrip(".")) if ext else ""
        if ext and ext not in order:
            order.append(ext)
    for ext in REMUX_FALLBACK_EXTS:
        if ext not in order:
            order.append(ext)
    base = str(p.with_suffix(""))
    for ext in order:
        cand = Path(base + ext)
        if cand.exists():
            return str(cand)
    return pth


def playlist_folder_name(raw: str) -> str:
    """把合集/播放列表的标题变成一层文件夹名；标题里没剩下可用字符时回空串（＝不建这层）。

    安全文件名那套会给空标题兜一个 "download"，那是给成品文件名准备的；这一层是用来分堆的
    目录名，宁可照实说「这一批没拿到合集名，仍平铺」，也不要造出一个谁都想不到的文件夹。
    """
    s = str(raw or "").strip()
    if not s or not re.search(r"\w", s):
        return ""
    return safe_filename_component(s, 60)


def playlist_landing_dir(base_dir: str, title: str, want: bool, *,
                         is_playlist: bool = False,
                         is_live: bool = False) -> Tuple[str, str]:
    """合集整批这一趟写进哪一层，以及给用户的那句话（空串＝没什么要解释的）。

    base_dir 是这一趟原本的落点（下载目录，或自动分类规则给出的那个子目录）：合集这一层加在它
    下面，不替掉它。名字有两个来处 —— 整表下载那一颗是容器自己的标题，逐条链接那一侧是解析页
    带过来的那份合集名。文件夹在这里就建出来：日志说「存到 X」的时候 X 得真的在场，不能先报后建。
    """
    if not want or is_live:
        return base_dir, ""
    folder = playlist_folder_name(title)
    if not folder:
        raw = str(title or "").strip()
        if is_playlist:
            return base_dir, f"容器没给出能当目录名的合集标题，这一批仍平铺在 {base_dir}"
        if raw:
            return base_dir, (f"合集名「{raw[:40]}」清洗后没剩下可用字符，"
                              f"这一批仍平铺在 {base_dir}")
        return base_dir, ""
    target = str(Path(base_dir) / folder)
    try:
        Path(target).mkdir(parents=True, exist_ok=True)
    except Exception as e:
        return base_dir, (f"合集文件夹「{folder}」建不出来：{e}；"
                          f"这一批仍平铺在 {base_dir}")
    return target, (f"合集整批存到 {target}"
                    f"（名字来自{'容器标题' if is_playlist else '解析页带过来的合集名'}）")


def url_target_dir(url: str, cfg: dict, base_dir: str,
                   log_fn: Callable = lambda *a, **k: None,
                   manual: bool = False) -> Tuple[str, str, str]:
    """普通下载（YouTube / B 站 / 直链这些没有「种子名」可比的东西）按链接规则决定落点。

    与种子那条同一套口径：规则从上往下先命中先得，落到下载目录下面的相对子目录。
    **不看「都不命中时存到」那个兜底目录** —— 兜底是给磁力那一页「没名字可比」准备的，
    普通下载一旦也走兜底，等于只加了一条链接规则就把整个下载目录改了地方，那是意外。
    manual=True 时规则给手动指定的目录让路，但命中了还是要说一声，不然用户不知道规则写对了。
    """
    rules = [r for r in (cfg.get("bt_auto_rules") or []) if isinstance(r, dict)]
    if not any(str(r.get("scope") or "name") == "url" for r in rules):
        return base_dir, "", ""
    hit, why = bt_rule_match(url, rules, "url")
    if not hit:
        return base_dir, "", ""
    if manual:
        log_fn(f"自动分类：{why} → 这一条已手动指定保存目录，规则不改落点（仍存 {base_dir}）")
        return base_dir, "", ""
    sub = str(hit.get("subdir") or "")
    if not sub:
        log_fn(f"自动分类：{why} → 规则「{hit.get('name')}」没填子目录，仍存默认目录")
        return base_dir, "", f"规则「{hit.get('name')}」没填子目录"
    target = str(Path(base_dir) / sub)
    log_fn(f"自动分类：{why} → 规则「{hit.get('name')}」，这一条存到 {target}")
    return target, str(hit.get("name") or ""), f"命中规则「{hit.get('name')}」（{why}）"


def bt_ensure(cfg: dict, log_fn) -> Tuple[bool, str]:
    """RPC 没人应答时，按设置决定「自己拉一个本机 aria2c」还是把缺的东西讲清楚。"""
    ac = _bt_client(cfg)
    if ac.ping():
        return True, ""
    if not cfg.get("aria2_autostart", True):
        return False, ("aria2 的 RPC（" + str(cfg.get("aria2_rpc") or "http://127.0.0.1:6800/jsonrpc")
                       + "）没有应答，而设置里「自动拉起 aria2」是关闭的："
                         "自己开一个 aria2c，或把这个开关打开后重试")
    import aria2_daemon
    binp = aria2_daemon.find_binary(str(cfg.get("aria2_bin") or ""), APP_DIR, is_native_binary)
    return aria2_daemon.ensure_running(
        rpc_url=str(cfg.get("aria2_rpc") or "http://127.0.0.1:6800/jsonrpc"),
        binary=binp,
        download_dir=str(cfg.get("download_dir") or DEFAULT_DOWNLOAD_DIR),
        app_dir=STATE_DIR,
        ping=ac.ping,
        log=log_fn,
    )


def _bt_daemon_stop():
    """退出前收掉自己拉起来的 aria2：先走 RPC 让它把会话文件写完，再兜底终止进程。"""
    try:
        import aria2_daemon
        if not aria2_daemon.owned().get("owned"):
            return
        _bt_client(dict(cfg.data)).force_shutdown()
        time.sleep(1.0)
        aria2_daemon.shutdown()
    except Exception:
        pass


def _bt_hsize(v) -> str:
    """aria2 把字节数当字符串给回来，界面上得是「12.3 MB」这样才看得懂。"""
    try:
        b = float(v)
    except (TypeError, ValueError):
        return "0 B"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if b < 1024 or unit == "TB":
            return f"{b:.0f} {unit}" if unit == "B" else f"{b:.1f} {unit}"
        b /= 1024.0
    return "0 B"


def _pot_daemon_stop():
    """退出前收掉程序自己拉起的那个 node POT 服务端；用户自己开的（owned=False）不碰。"""
    try:
        import pot_daemon
        if pot_daemon.owned().get("owned"):
            pot_daemon.shutdown()
    except Exception:
        pass


def bt_pick_primary(paths: List[str]) -> str:
    """种子里挑「这一个文件」当任务成品：先看媒体后缀，再在同组里挑最大的。

    界面与后续处理（校验、转写、搬运）都按一个主文件走；整包目录另记在 result_dir，
    两个都给前端，用户既看得到主成品也看得到其余文件。
    """
    exist = [p for p in paths if p and Path(p).is_file()]
    if not exist:
        return ""
    media = [p for p in exist if Path(p).suffix.lower() in _MEDIA_EXTS]
    pool = media or exist
    try:
        return max(pool, key=lambda p: Path(p).stat().st_size)
    except OSError:
        return pool[0]


def bt_error_text(code: str, msg: str) -> str:
    """把 aria2 的报错夹成人话，但代码和原话一个字不删——用户要能对着代码去搜官方说法。

    代码 13 是实测撞上的那条死路：下载目录里已经有这份内容、却没有 .aria2 续传记录，
    aria2 为防把成品截断成 0 字节当场取消。这里补的是「接下来按哪个按钮」，不替换它的原话。
    试过传 check-integrity=true 让它直接认领本地数据：实测连把 piece 开头都改坏了它照样
    报 completedLength=totalLength，等于把没验过的东西当成品，所以不自动那么干。
    """
    head = f"aria2 报错（代码 {code}）：{msg or '未知原因'}"
    if code == "13":
        head += ("——两条走法：把下载目录里这份同名的旧内容删掉再重下；"
                 "或在任务行勾「只做种」，让本地成品直接挂上传，不重新下载")
    if code == "12":
        # 实测：同一个 .torrent 提交第二次就撞上它，aria2 里同一个 infohash 只认一条，
        # 而下完转做种的那条也还算数，所以「列表里看不到」不等于「aria2 已经放手」。
        head += ("——同一个种子在 aria2 里只能登记一次：先在任务列表或「正在做种」面板里把"
                 "原来那条删掉或停止做种，再重新提交")
    return head


def bt_file_list(raw: List[dict]) -> List[dict]:
    """aria2.getFiles 的返回 → 界面要的形状：序号、路径、大小、完成度、是否要下。"""
    out = []
    for i, f in enumerate(raw or [], 1):
        path = str(f.get("path") or "")
        # 磁力在「还没拿到种子元数据」那段，aria2 会先挂一行 [METADATA] 占位，它不是种子里的文件
        if not path or Path(path).name.startswith("[METADATA]"):
            continue
        try:
            idx = int(f.get("index") or i)
        except (TypeError, ValueError):
            idx = i
        size = 0
        try:
            size = max(int(f.get("length") or 0), int(f.get("size") or 0))
        except (TypeError, ValueError):
            size = 0
        done = 0
        try:
            prog = f.get("progress") or (f.get("completedLength") or "")
            done = int(str(prog).strip() or 0)
        except (TypeError, ValueError):
            done = 0
        out.append({
            "index": idx,
            "path": path,
            "name": Path(path).name,
            "size": size,
            "done": done,
            "selected": str(f.get("selected", "true")).lower() != "false",
        })
    return out


# -------------------- 队列调度 --------------------
class TaskQueue:
    def __init__(self, engine: DownloaderEngine, cfg: ConfigManager, log: LogManager, history: HistoryManager):
        self.engine = engine
        self.cfg = cfg
        self.log = log
        self.history = history
        self.tasks: Dict[str, DownloadTask] = {}
        self.pending: List[str] = []
        self.running = 0
        self.lock = threading.Lock()
        self.max_concurrent = int(cfg.data.get("concurrent", 3))
        self.paused = False  # 全局暂停：不再启动新任务
        self._wake_timer = None
        self._wake_at = 0.0
        self._window_timer = None
        self._window_wake_at = 0.0
        self._window_logged = ""  # 上一次为「窗关着」记过的那句话，避免每次泵都刷一行
        self._window_logged_q: Dict[str, str] = {}  # 队列级同理：{队列名: 上次记过的那句}

    def _task_host(self, url: str) -> str:
        return url_host(url)

    def _wake_later(self, seconds: float):
        """站点冷却结束后要把排队的任务再泵一次（调度只在事件驱动时跑）。"""
        until = time.time() + max(1.0, min(900.0, float(seconds)))
        if self._wake_timer is not None and self._wake_at <= until and self._wake_timer.is_alive():
            return
        if self._wake_timer is not None:
            self._wake_timer.cancel()
        self._wake_at = until
        t = threading.Timer(max(1.0, until - time.time()), self._wake_fire)
        t.daemon = True
        self._wake_timer = t
        t.start()

    def _wake_fire(self):
        self._wake_at = 0.0
        self._wake_timer = None
        self._pump()

    def _arm_window_wake(self, hhmm: str):
        """定时窗到点自己再来泵一次。

        不走 _wake_later：那条给站点冷却用，上限 900 秒，而窗口可能是六小时后才开，
        按它排就永远醒在错误的时间上。这里按真实剩余时间排一次性闹钟（最多一圈 24 小时）。
        """
        if not hhmm:
            return
        left = _hm_until(hhmm, datetime.now().strftime("%H:%M")) * 60 + 5
        until = time.time() + left
        if self._window_timer is not None and self._window_wake_at <= until and self._window_timer.is_alive():
            return  # 已经有个更早的闹钟在跑，让它先响
        if self._window_timer is not None:
            self._window_timer.cancel()
        self._window_wake_at = until
        t = threading.Timer(left, self._window_fire)
        t.daemon = True
        self._window_timer = t
        t.start()

    def _window_fire(self):
        self._window_timer = None
        self._window_wake_at = 0.0
        self._pump()

    def window_status(self) -> dict:
        """界面横幅要说清的三件事：现在能不能跑、不能跑到几点能跑、每条命名队列各自的窗与压着的条数。"""
        d = self.cfg.data
        open_, note, nxt, left = window_open(d.get("run_window") or "")
        out = {
            "open": open_,
            "note": note,
            "resume_at": nxt,
            "wait_minutes": left,
            "global_window": str(d.get("run_window") or "").strip(),
            "held": len(self.pending) if not open_ else 0,
            "queues": [],
        }
        qwins = d.get("queue_windows") or {}
        names = list(dict.fromkeys(
            list(d.get("named_queues") or [])
            + sorted(KNOWN_QUEUE_NAMES)
            + self.queue_names()
            + [str(k) for k in qwins.keys()]
        ))
        for name in names:
            text = str(qwins.get(name) or "").strip()
            if not text:
                # 没填窗的队列也要列出来：设置页要按这张表逐行给输入框，漏一行用户就没法给它填
                out["queues"].append({"name": name, "open": True, "windows": "", "note": "",
                                      "resume_at": "", "wait_minutes": 0, "held": 0})
                continue
            ok, qnote, nx, lf = window_open(text)
            held = 0
            if not ok:
                held = sum(
                    1 for t in self.tasks.values()
                    if (t.queue_name or "default") == name
                    and t.status == TaskStatus.QUEUED.value
                )
            out["queues"].append({
                "name": name, "open": ok, "windows": text, "note": qnote,
                "resume_at": nx, "wait_minutes": lf, "held": held,
            })
        return out

    def queue_names(self) -> List[str]:
        """当前任务里真实用过的队列名（含 default）。界面要列的那张表比设置里那份全。"""
        names = set()
        for t in self.tasks.values():
            names.add(t.queue_name or "default")
        return sorted(names)

    def _host_running_count(self, host: str) -> int:
        if not host:
            return 0
        n = 0
        for t in self.tasks.values():
            if t.status == TaskStatus.DOWNLOADING.value and self._task_host(t.url) == host:
                n += 1
        return n

    def add_urls(self, urls: List[str], options: dict) -> List[str]:
        ids = []
        options = dict(options or {})
        download_later = bool(options.pop("download_later", False))
        queue_name = (options.get("queue_name") or "default").strip() or "default"
        # 插件解析：页面链 → 真实媒体链
        if self.cfg.data.get("plugins_enabled", True) and not options.get("skip_plugins"):
            expanded = []
            for u in urls:
                if parse_torrent_ref(u) or torrent_reject_reason(u):
                    expanded.append((u, {}, ""))  # 磁力/种子是给 aria2 的，插件那套正则不接手
                    continue
                try:
                    resolved = try_resolve_with_plugins(
                        u,
                        {
                            "proxy": proxy_arg(u),
                            "log": self.log.log if hasattr(self.log, "log") else print,
                        },
                    )
                except Exception:
                    resolved = None
                if resolved and resolved.get("urls"):
                    ropts = dict(resolved.get("options") or {})
                    for nu in resolved["urls"]:
                        expanded.append((nu, ropts, resolved.get("title") or ""))
                    self.log.log(
                        f"插件解析: {u[:60]}… → {len(resolved['urls'])} 条 "
                        f"({resolved.get('_plugin', '')})",
                        k="srv.queue.plugin_resolved",
                        kv={"url": u[:60], "n": len(resolved['urls']),
                            "plugin": resolved.get('_plugin', '')})
                else:
                    expanded.append((u, {}, ""))
            # 重建 urls 与 per-url options 合并
            urls = [x[0] for x in expanded]
            # 若只有一条且有 title，写入 options
            if len(expanded) == 1 and expanded[0][2]:
                options.setdefault("_title", expanded[0][2])
            if expanded and expanded[0][1]:
                options = {**expanded[0][1], **options}

        existing = {
            url_dedup_key(t.url)
            for t in self.tasks.values()
            if t.status in (
                TaskStatus.QUEUED.value, TaskStatus.DOWNLOADING.value, TaskStatus.PAUSED.value, TaskStatus.LATER.value
            )
        }
        seen = set()
        merged = 0
        for raw in urls:
            u = normalize_url((raw or "").strip())
            if not u:
                continue
            key = url_dedup_key(u)
            if key in seen or key in existing:
                merged += 1
                continue
            seen.add(key)
            tid = str(uuid.uuid4())
            # 期望校验值：入队时可能已经规范化过（api_download），这里再规范化一次是幂等的，
            # 为的是别的入队口（订阅规则、嗅探、MCP）交来一串不像摘要的东西时别把它带进任务里。
            want_hex, want_algo, hash_err = normalize_hash_expect(
                options.get("expect_hash"), options.get("hash_algo") or "auto")
            if hash_err:
                self.log.log(f"这条期望校验值没被采用：{hash_err}", "warning",
                             k="srv.queue.hash_check_skipped", kv={"why": hash_err})
            task = DownloadTask(
                id=tid,
                url=u,
                is_live=bool(options.get("is_live")),
                created_at=datetime.now().isoformat(timespec="seconds"),
                pinned=bool(options.get("pinned")),
                priority=int(options.get("priority") or 0),
                queue_name=queue_name,
                expect_hash=want_hex,
                hash_algo=want_algo,
            )
            if task.pinned:
                task.priority = max(task.priority, 1000)
            if task.is_live:
                task.title = "直播录制中…"
            if options.get("_title") and task.title in ("等待中...", ""):
                task.title = str(options.get("_title"))[:120]
            if download_later:
                task.status = TaskStatus.LATER.value
            self.tasks[tid] = task
            task._opts = options  # type: ignore
            if not download_later:
                self._insert_pending(tid)
            ids.append(tid)
            existing.add(key)
        if merged:
            self.log.log(f"已合并 {merged} 条重复链接（同一内容的不同分享参数）",
                         k="srv.queue.dupes_merged", kv={"n": merged})
        if not download_later:
            self._pump()
        return ids

    def _insert_pending(self, tid: str):
        """按 pinned + priority 插入 pending（高优先级靠前）"""
        task = self.tasks.get(tid)
        if not task:
            return
        if tid in self.pending:
            self.pending.remove(tid)
        # 计算插入位置：先 pinned，再 priority 降序，再 FIFO
        pos = len(self.pending)
        for i, other_id in enumerate(self.pending):
            other = self.tasks.get(other_id)
            if not other:
                continue
            if task.pinned and not other.pinned:
                pos = i
                break
            if task.pinned == other.pinned and task.priority > other.priority:
                pos = i
                break
            if task.pinned == other.pinned and task.priority == other.priority:
                # 同优先级保持 FIFO，不插队
                continue
        self.pending.insert(pos, tid)

    def _pump(self):
        with self.lock:
            if self.paused:
                return
            d = self.cfg.data
            g_open, g_note, g_next, _gl = window_open(d.get("run_window") or "")
            if not g_open:
                # 全局窗关着：一条新的都不开，已经在跑的不动（掐断正在下的文件不是「定时跑队列」的意思）
                key = f"global:{g_next}"
                if self._window_logged != key:
                    self._window_logged = key
                    self.engine.log(f"[queue] 队列定时窗：{g_note}，{g_next} 自动开始", "info")
                self._arm_window_wake(g_next)
                return
            self._window_logged = ""
            self.max_concurrent = int(self.cfg.data.get("concurrent", 3) or 3)
            max_per_host = int(self.cfg.data.get("max_per_host", 2) or 2)
            try:
                risk_cap = int(self.cfg.data.get("risk_max_per_host", 0) or 0)
            except Exception:
                risk_cap = 0
            if risk_cap > 0:
                max_per_host = risk_cap if max_per_host <= 0 else min(max_per_host, risk_cap)
            adaptive = bool(self.cfg.data.get("adaptive_throttle", True))
            wake_in = 0.0
            skipped = []
            held = []
            qwins = d.get("queue_windows") or {}
            while self.running < self.max_concurrent and self.pending:
                tid = self.pending.pop(0)
                task = self.tasks.get(tid)
                if not task:
                    continue
                if task.status in (
                    TaskStatus.STOPPED.value,
                    TaskStatus.PAUSED.value,
                    TaskStatus.FINISHED.value,
                    TaskStatus.LATER.value,
                ):
                    continue
                qtext = str(qwins.get(task.queue_name or "default") or "")
                if qtext:
                    q_open, _qn, q_next, _ql = window_open(qtext)
                    if not q_open:
                        held.append(tid)
                        self._arm_window_wake(q_next)
                        qname = task.queue_name or "default"
                        # 泵一趟会把同一条队列的每个任务都过一遍，所以按「队列 + 开门钟点」去重：
                        # 一条队列一次窗只记一行，不然是排队多少刷多少
                        qkey = f"{qname}:{q_next}"
                        if self._window_logged_q.get(qname) != qkey:
                            self._window_logged_q[qname] = qkey
                            self.engine.log(
                                f"[queue] 队列「{qname}」定时窗：{q_next} 之前不开新任务", "info")
                        continue
                host = self._task_host(task.url)
                cap = HOST_THROTTLE.cap_for(host, max_per_host) if adaptive else max_per_host
                if host and cap > 0 and self._host_running_count(host) >= cap:
                    skipped.append(tid)
                    if adaptive and cap < max_per_host:
                        for snap in HOST_THROTTLE.snapshot():
                            if snap["host"] == host:
                                wake_in = snap["left"] if not wake_in else min(wake_in, snap["left"])
                                break
                    continue
                self.running += 1
                task.status = TaskStatus.DOWNLOADING.value
                # 断点状态：目录中是否有 .part / .ytdl
                try:
                    od = Path(
                        (getattr(task, "_opts", {}) or {}).get("download_dir")
                        or self.cfg.data.get("download_dir")
                        or DEFAULT_DOWNLOAD_DIR
                    )
                    has_part = any(od.glob("*.part")) or any(od.glob("*.ytdl"))
                    task.resume_hint = "可能续传(.part)" if has_part else "新下载/续传由引擎判定"
                    task.max_retries = int(
                        (getattr(task, "_opts", {}) or {}).get("max_retries")
                        or self.cfg.data.get("max_retries")
                        or 3
                    )
                except Exception:
                    task.resume_hint = "新下载"
                threading.Thread(target=self._run, args=(task,), daemon=True).start()
            # 因同域限制暂缓的任务放回队列头部之后；被定时窗压着的排更前，开窗那一刻先跑它们
            if held or skipped:
                self.pending = held + skipped + self.pending
            if wake_in > 0:
                self._wake_later(wake_in)

    def pin_tasks(self, ids: List[str], pinned: bool = True):
        for tid in ids:
            t = self.tasks.get(tid)
            if not t:
                continue
            t.pinned = pinned
            if pinned:
                t.priority = max(t.priority, 1000)
            else:
                t.priority = min(t.priority, 999)
            if t.status == TaskStatus.QUEUED.value and tid in self.pending:
                self._insert_pending(tid)

    def move_to_top(self, ids: List[str]):
        """置顶并立即提到 pending 最前"""
        for tid in reversed(ids):
            t = self.tasks.get(tid)
            if not t:
                continue
            t.pinned = True
            t.priority = max(t.priority, 1000)
            if t.status in (TaskStatus.QUEUED.value, TaskStatus.PAUSED.value, TaskStatus.LATER.value):
                if t.status == TaskStatus.LATER.value:
                    t.status = TaskStatus.QUEUED.value
                if tid in self.pending:
                    self.pending.remove(tid)
                self.pending.insert(0, tid)
        self._pump()

    def set_later(self, ids: List[str], later: bool = True):
        """稍后下载 / 取消稍后"""
        for tid in ids:
            t = self.tasks.get(tid)
            if not t:
                continue
            if later:
                if t.status in (TaskStatus.QUEUED.value, TaskStatus.PAUSED.value):
                    t.status = TaskStatus.LATER.value
                    if tid in self.pending:
                        self.pending.remove(tid)
            else:
                if t.status == TaskStatus.LATER.value:
                    t.status = TaskStatus.QUEUED.value
                    self._insert_pending(tid)
        if not later:
            self._pump()

    def reorder_pending(self, ordered_ids: List[str]):
        """按给定顺序重排 pending（仅影响仍在排队的任务）"""
        idset = set(ordered_ids)
        rest = [tid for tid in self.pending if tid not in idset]
        new_pending = [tid for tid in ordered_ids if tid in self.tasks and self.tasks[tid].status == TaskStatus.QUEUED.value]
        self.pending = new_pending + rest

    def list_tasks(self, sort_by: str = "queue") -> List[dict]:
        """sort_by: queue | created | status | title"""
        items = list(self.tasks.values())
        if sort_by == "queue":
            # pending 顺序优先，然后 pinned，再 priority，再创建时间
            order = {tid: i for i, tid in enumerate(self.pending)}
            def key(t: DownloadTask):
                return (
                    0 if t.status == TaskStatus.DOWNLOADING.value else 1,
                    order.get(t.id, 99999),
                    0 if t.pinned else 1,
                    -t.priority,
                    t.created_at or "",
                )
            items.sort(key=key)
        elif sort_by == "created":
            items.sort(key=lambda t: t.created_at or "", reverse=True)
        elif sort_by == "status":
            order = {"downloading": 0, "queued": 1, "paused": 2, "later": 3, "failed": 4, "stopped": 5, "finished": 6}
            items.sort(key=lambda t: (order.get(t.status, 9), 0 if t.pinned else 1, -t.priority))
        elif sort_by == "title":
            items.sort(key=lambda t: (t.title or t.url or "").lower())
        return [t.to_dict() for t in items]

    def _torrent_job(self, task: DownloadTask, cfg: dict, out_dir: str, on_progress) -> Tuple[bool, str, str]:
        """磁力/种子任务的完整一趟：提交给 aria2 → 等元数据 → 报进度 → 完成后转入做种看护。

        返回值沿用引擎那一套 (是否成功, 主成品路径, 提示)。种子的「主成品」是按媒体后缀
        挑出来的那一个文件，整包目录记在 task.result_dir，其余文件在 task.files 里，
        这样校验/转写/搬运这些只认单文件的后续步骤能照旧跑。
        """
        ref = parse_torrent_ref(task.url)
        if not ref:
            return False, "", "这条既不是磁力链接，也不是本地 .torrent 文件"
        task.kind = "torrent"
        ok, why = bt_ensure(cfg, self.engine.log)
        if not ok:
            return False, "", why
        seed_only = bool(cfg.get("torrent_seed_only"))
        if seed_only and (cfg.get("bt_auto_rules") or []):
            # 只做种不下载新东西，成品就躺在本地原来的位置；再按规则换个落点，
            # 下面逐个查文件时只会得到一句「下载目录里找不到种子里的 N 个文件」，白白吓人
            self.log.log("自动分类：这条勾了「只做种」，不改落点（规则只管新下载的内容存到哪）",
                         k="srv.queue.seed_only_keeps_dir")
        else:
            out_dir, task.category, _cat_why = bt_target_dir(ref, cfg, out_dir, self.log.log,
                                                             url=task.url)
        ac = _bt_client(cfg)
        meta_wait = max(30, int(cfg.get("torrent_meta_timeout") or 180))
        meta_deadline = time.time() + meta_wait
        # 停种由下面的看护线程按比率/时长决定，所以要让 aria2 自己永远不停种。
        # 只能给 seed-ratio=0（官方口径：0 就是不看比率、一直种）；这时候再带上 seed-time=0
        # 反而会让 aria2 立刻收摊——两个条件同时给时，满足任意一个就结束做种。
        extra = {"seed-ratio": "0"}
        extra.update(_bt_add_options(cfg, self.log.log))
        if seed_only and ref["kind"] == "magnet":
            return False, "", ("「只做种」得先认出手上有哪些文件，磁力链接这一刻还没有种子元数据："
                               "先把 .torrent 文件传上来再挂只做种")
        if seed_only:
            # 本地已经是完整成品，逐片哈希校验只是白等；aria2 的口径是「不做校验直接拿旧文件做种」
            extra["bt-seed-unverified"] = "true"
        try:
            if ref["kind"] == "magnet":
                gid = ac.add_uri([task.url], out_dir=out_dir, extra_opts=extra)
            else:
                tp = Path(ref["path"])
                if not tp.is_file():
                    return False, "", f"种子文件不存在：{tp}"
                gid = ac.add_torrent(str(tp), out_dir, extra_opts=extra)
        except Exception as e:
            return False, "", f"提交给 aria2 失败：{aria2_err_cn(e, cfg)}"
        task.gid = gid
        if seed_only:
            return self._torrent_seed_only(task, ac, cfg, gid, out_dir)
        if not task.title or task.title == "等待中...":
            task.title = ref["name"]
        task.resume_hint = f"aria2 {gid[:10]}"
        self.log.log(f"{'磁力' if ref['kind'] == 'magnet' else '种子'}任务交给 aria2："
                     f"{ref['name']}（任务号 {gid[:10]}，存到 {out_dir}）")
        # 磁力是两段下载：先只下元数据，元数据一到 aria2 就另起一个 gid 下真文件，
        # 父任务随即报 complete、totalLength 也只有元数据那一两百字节 —— 跟着父任务走会把这当成「下完了」。
        watch = gid
        followed = ref["kind"] != "magnet"
        while True:
            if self.engine._stop_flags.get(task.id):
                ac.remove(watch)
                return False, "", "已停止：aria2 那边的任务同时移除了"
            try:
                st = ac.tell_status(watch, BT_KEYS)
            except Exception as e:
                return False, "", f"读取 aria2 状态失败：{aria2_err_cn(e, cfg)}"
            status = str(st.get("status") or "")
            total = int(st.get("totalLength") or 0)
            done = int(st.get("completedLength") or 0)
            if status in ("error", "removed"):
                return False, "", bt_error_text(str(st.get("errorCode") or ""),
                                                st.get("errorMessage") or "")
            if not followed:
                kids = [str(x) for x in (st.get("followedBy") or []) if x]
                if kids:
                    watch = kids[0]
                    followed = True
                    task.gid = watch
                    task.resume_hint = f"aria2 {watch[:10]}"
                    self.log.log(f"磁力元数据到手，改跟真文件那一段下载（任务号 {watch[:10]}）",
                                 k="srv.queue.magnet_metadata_ready", kv={"gid": watch[:10]})
                    continue
            if status in ("error", "removed"):
                return False, "", bt_error_text(str(st.get("errorCode") or ""),
                                                st.get("errorMessage") or "")
            if not total or not followed:
                if time.time() > meta_deadline:
                    ac.remove(watch)
                    return False, "", (f"等了 {meta_wait} 秒还没拿到种子元数据："
                                       "多半是这会儿没人在做种，或 DHT/Tracker 被网络挡住")
                on_progress(task.id, 0, "等待种子元数据", "")
                time.sleep(2)
                continue
            if not task.files:
                try:
                    task.files = bt_file_list(ac.get_files(watch))
                    if task.files:
                        task.result_dir = str(Path(task.files[0]["path"]).parent)
                except Exception:
                    pass
            pct = min(99.0, done * 100.0 / total)
            on_progress(task.id, pct,
                        f"{_bt_hsize(st.get('speed'))}/s · {st.get('numPeers') or 0} 个节点", "",
                        {"done_bytes": int(done or 0), "total_bytes": int(total or 0)})
            if status == "complete":
                break
            # 带做种时 aria2 会一直停在 active：下满了也不报 complete（比率 0 就是永远不停种），
            # 所以「下载完成」只能自己判——分片补齐就可以收尾，上传交给下面的看护线程。
            if status == "active" and total and done >= total:
                break
            time.sleep(1)
        try:
            raw_files = bt_file_list(ac.get_files(watch))
        except Exception:
            raw_files = []
        if raw_files:
            task.files = raw_files
        paths = [f["path"] for f in (task.files or []) if f.get("selected") and int(f.get("size") or 0) > 0]
        primary = bt_pick_primary(paths)
        if not primary:
            return False, "", "下载已经满了，但一个文件都没落盘"
        task.result_dir = str(Path(primary).parent)
        try:
            want_ratio = float(cfg.get("torrent_seed_ratio"))
        except (TypeError, ValueError):
            want_ratio = 1.0
        try:
            want_time = int(float(cfg.get("torrent_seed_time")))
        except (TypeError, ValueError):
            want_time = 3600
        with _BT_WATCH_LOCK:
            _BT_WATCH[watch] = {"task_id": task.id, "ratio": want_ratio, "seconds": want_time,
                                "name": Path(primary).name}
        # 看护线程 15 秒才走一拍，标记先打上，界面立刻能看到这条在做种
        task.seeding = True
        self._bt_watch_start()
        n = len(paths)
        if not want_ratio and not want_time:
            note = f"{n} 个文件，一直做种（要停就在「做种中」那行按「停止做种」）"
        else:
            note = f"{n} 个文件，已转入做种"
        return True, primary, note

    def _torrent_seed_only(self, task: DownloadTask, ac, cfg: dict, gid: str,
                           out_dir: str) -> Tuple[bool, str, str]:
        """只做种：本地已有这份成品，直接挂上传，不走下载那一趟等待。

        aria2 收下 bt-seed-unverified 的任务后不会告诉我们文件到底齐不齐，所以这里自己按
        种子清单逐个查：少一个就当场退回并说明缺哪个，别留一个「在做种但其实没东西可传」的任务。
        """
        task.resume_hint = f"aria2 {gid[:10]}"
        try:
            files = bt_file_list(ac.get_files(gid))
        except Exception as e:
            ac.remove(gid)
            return False, "", f"读种子文件清单失败：{e}"
        want = [f for f in files if int(f.get("size") or 0) > 0]
        missing = [str(f["path"]) for f in want
                   if not (Path(out_dir) / str(f["path"])).is_file()]
        if missing:
            ac.remove(gid)
            head = "、".join(missing[:3])
            return False, "", (f"下载目录里找不到种子里的 {len(missing)} 个文件（{head}"
                               + ("…" if len(missing) > 3 else "")
                               + f"）：只做种得先把成品放到 {out_dir}")
        if not task.title or task.title == "等待中...":
            # 用种子里的名字，不是「清单第一个文件」的名字：一份 20 个文件的种子在清单上
            # 只显示第一个文件名，用户会以为做种的是那一个文件（实测 info.name 就在这条 RPC 里）
            seed_name = ""
            try:
                bt = (ac.tell_status(gid, ["bittorrent"]).get("bittorrent") or {})
                seed_name = str(((bt.get("info") or {}).get("name")) or "")
            except Exception:
                seed_name = ""
            task.title = seed_name or (Path(str(want[0]["path"])).name if want else gid[:10])
        task.files = files
        primary = bt_pick_primary([str(f["path"]) for f in want]) or ""
        task.result_dir = str(Path(primary).parent) if primary else out_dir
        try:
            want_ratio = float(cfg.get("torrent_seed_ratio"))
        except (TypeError, ValueError):
            want_ratio = 1.0
        try:
            want_time = int(float(cfg.get("torrent_seed_time")))
        except (TypeError, ValueError):
            want_time = 3600
        with _BT_WATCH_LOCK:
            _BT_WATCH[gid] = {"task_id": task.id, "ratio": want_ratio, "seconds": want_time,
                              "name": Path(primary).name if primary else task.title}
        task.seeding = True
        self._bt_watch_start()
        self.log.log(f"[只做种] {task.title}：本地 {len(want)} 个文件已交给 aria2 挂做种（{out_dir}）",
                     k="srv.queue.seed_local_files",
                     kv={"title": task.title, "n": len(want), "dir": out_dir})
        return True, primary, f"{len(want)} 个文件已挂上做种，没有重新下载"

    def _bt_watch_start(self):
        """做种看护线程：没有它做种任务会一直赖在 aria2 里占上传。线程空了就自己退出。"""
        th = getattr(self, "_bt_thread", None)
        if th is not None and th.is_alive():
            return
        self._bt_thread = threading.Thread(target=self._bt_watch_loop, daemon=True)
        self._bt_thread.start()

    def _bt_watch_loop(self):
        while True:
            with _BT_WATCH_LOCK:
                items = list(_BT_WATCH.items())
            if not items:
                return
            time.sleep(15)
            ac = _bt_client(dict(self.cfg.data))
            for gid, w in items:
                with _BT_WATCH_LOCK:
                    # 这 15 秒里用户可能已经手动停了做种：登记没了就跳过，别拿旧快照把它标回「做种中」
                    if gid not in _BT_WATCH:
                        continue
                t = self.tasks.get(w.get("task_id") or "")
                try:
                    st = ac.tell_status(gid, ["status", "uploadLength", "completedLength", "seedingTime"])
                except Exception:
                    # aria2 重启过或任务已不在：本地记录跟着清掉，别留一个永远不停的「做种中」
                    with _BT_WATCH_LOCK:
                        _BT_WATCH.pop(gid, None)
                    if t:
                        t.seeding = False
                    continue
                if not st.get("status"):
                    # 任务号已经从 aria2 摘掉时它不报错，只回一个空对象：这同样算没在做种了
                    with _BT_WATCH_LOCK:
                        _BT_WATCH.pop(gid, None)
                    if t:
                        t.seeding = False
                    continue
                stt = str(st.get("status") or "")
                if stt in ("error", "complete", "removed"):
                    # 实测三种读数各有含义：做种中是 active，按比率/时长停种后是 complete，
                    # 本地文件不齐是 error。这三种都别再挂「做种中」，更没必要留在看护表里
                    why = {"error": "aria2 那边这个任务已出错（多半是本地文件不齐或被占用）",
                           "complete": "aria2 已按做种比率/时长停种",
                           "removed": "任务已从 aria2 移除"}.get(stt, stt)
                    with _BT_WATCH_LOCK:
                        _BT_WATCH.pop(gid, None)
                    if t:
                        t.seeding = False
                        t.resume_hint = f"{why}，不再做种"
                    self.log.log(f"做种看护：{(t.title if t else w.get('name'))} {why}，已摘掉「做种中」",
                                 k="srv.queue.seed_unwatched",
                                 kv={"name": t.title if t else w.get('name'), "why": why})
                    continue
                if stt == "paused":
                    # 暂停的做种任务 aria2 不列进 tellActive（实测），但它确实还在传不了东西的状态里：
                    # 登记要留着，「停止做种」才点得掉；标记跟着改成没在做种，别说假话。
                    # 本程序的暂停/继续只管下载队列，不会去动 aria2，所以这里不承诺按哪个按钮能恢复。
                    if t:
                        t.seeding = False
                        t.resume_hint = "aria2 把这个做种任务停成了 paused，当前不上传；要恢复上传得重新提交这个种子"
                    continue
                up = int(st.get("uploadLength") or 0)
                dl = max(1, int(st.get("completedLength") or 0))
                ratio = up / dl
                try:
                    seed_t = int(float(st.get("seedingTime") or 0))
                except (TypeError, ValueError):
                    seed_t = 0
                if t:
                    t.uploaded, t.share_ratio, t.seed_seconds, t.seeding = up, ratio, seed_t, True
                stop = ""
                if w.get("ratio") and ratio >= float(w["ratio"]):
                    stop = f"上传比率到 {ratio:.2f}"
                elif w.get("seconds") and seed_t >= int(w["seconds"]):
                    stop = f"做种满 {seed_t} 秒"
                if stop:
                    ac.remove(gid)
                    with _BT_WATCH_LOCK:
                        _BT_WATCH.pop(gid, None)
                    if t:
                        t.seeding = False
                        # 任务卡上还写着「一直做种」的话就是假话：做种结束时一并改掉那行
                        t.resume_hint = f"做种结束（{stop}），已停止上传"
                    self.log.log(f"磁力做种结束：{(t.title if t else w.get('name'))}（{stop}），已停止上传",
                                 k="srv.queue.seed_stopped",
                                 kv={"name": t.title if t else w.get('name'), "stop": stop})

    def _run(self, task: DownloadTask):
        opts = getattr(task, "_opts", {}) or {}
        cfg = dict(self.cfg.data)
        out_dir = opts.get("download_dir") or cfg.get("download_dir") or str(DEFAULT_DOWNLOAD_DIR)
        # 自动分类的「链接规则」在这里生效（磁力那一页由 bt_target_dir 自己管，两边都跑会套两层目录）
        if not parse_torrent_ref(task.url or ""):
            nd, cat, _why = url_target_dir(
                task.url or "", cfg, out_dir, self.engine.log,
                manual=_opts_dir_is_manual(opts.get("download_dir"), cfg.get("download_dir")))
            if cat:
                out_dir, task.category = nd, cat
        if not task.started_at:
            task.started_at = datetime.now().isoformat(timespec="seconds")
        # 直播：抓取聊天弹幕
        if task.is_live or "live.bilibili.com" in (task.url or "").lower():
            try:
                chat = start_live_chat_capture(task.id, task.url, out_dir, log=self.engine.log)
                if chat:
                    task.chat_file = chat
            except Exception as e:
                self.engine.log(f"[{task.id[:8]}] 启动聊天抓取失败: {e}", "warning")

        def on_progress(tid, pct, speed, eta, meta=None):
            t = self.tasks.get(tid)
            if t:
                if pct is not None and float(pct) >= 0:
                    t.progress = pct
                t.speed = speed or t.speed
                t.eta = eta or t.eta
                md = meta or {}
                if int(md.get("done_bytes") or 0) > 0:
                    t.done_bytes = int(md["done_bytes"])
                if int(md.get("total_bytes") or 0) > 0:
                    t.total_bytes = int(md["total_bytes"])
                new_label = str(md.get("res_label") or "")
                if new_label:
                    # 合并下载时视频流、音频流各回调一次，别让用户看到标签在「1080p」和「M4A 128k」之间跳
                    v_new = bool(re.match(r"^\d{3,4}p\b", new_label))
                    v_cur = bool(re.match(r"^\d{3,4}p\b", t.res_label or ""))
                    if v_new or not v_cur:
                        t.res_label = new_label
                if md.get("thumbnail") and not t.thumbnail:
                    t.thumbnail = str(md["thumbnail"])
                # 重试可视化：speed 形如 "retry 1/3" / "429 退避2s 1/3"
                sp = str(speed or "")
                if "retry" in sp.lower() or "退避" in sp or "429" in sp:
                    t.resume_hint = sp
                    m = re.search(r"(\d+)\s*/\s*(\d+)", sp)
                    if m:
                        t.retry_count = int(m.group(1))
                        t.max_retries = int(m.group(2))

        # 本次任务选项覆盖全局配置（嵌入/字幕等）
        for k in (
            "embed_thumb", "embed_meta", "embed_chapters",
            "embed_sub", "subtitle_langs", "audio_only",
            "local_ai_transcribe", "local_ai_translate", "local_ai_lang",
            "whisper_model", "whisper_device", "whisper_compute",
            "skip_downloaded", "verify_download", "allow_playlist", "sponsorblock",
            "playlist_subdir", "playlist_folder",
            "write_description", "write_info_json", "write_sub_files",
            "speed_limit", "filename_template", "prefer_codec",
            "force_format", "download_section", "is_live", "use_hls_engine",
            "ytdlp_extra_args",
            "direct_cdn", "bilibili_m4s",
            "http_headers", "referer", "cookie", "user_agent", "proxy",
            "hls_key",
            "playlist_start", "playlist_end", "playlist_items",
            "max_retries",
            "torrent_seed_ratio", "torrent_seed_time", "torrent_seed_only",
        ):
            if opts.get(k) is not None:
                cfg[k] = opts[k]
        # 合并 http_headers → 供 yt-dlp / CDN 使用
        hdrs = dict(cfg.get("http_headers") or opts.get("http_headers") or {})
        if opts.get("referer") or cfg.get("referer"):
            hdrs["Referer"] = opts.get("referer") or cfg.get("referer")
        if opts.get("user_agent") or cfg.get("user_agent"):
            hdrs["User-Agent"] = opts.get("user_agent") or cfg.get("user_agent")
        if opts.get("cookie") or cfg.get("cookie"):
            hdrs["Cookie"] = opts.get("cookie") or cfg.get("cookie")
        # 公开优先判过「这条匿名就能开」之后，手工粘的那串 Cookie 也不该跟着发出去：
        # yt-dlp 那侧由 _cookie_source / _ydl_opts 收着，CDN 直链与 aria2 这一支只读这份请求头。
        if hdrs.get("Cookie") and (
            self.engine.cookie_off(cfg, normalize_url(task.url)) or self.engine.cookie_off(cfg, task.url)
        ):
            hdrs.pop("Cookie", None)
        if hdrs:
            cfg["http_headers"] = hdrs
        from telegram_mt import parse_tgmt

        bt_ref = parse_torrent_ref(task.url)
        mt_ref = None if bt_ref else parse_tgmt(task.url)
        if bt_ref:
            self.engine._stop_flags[task.id] = False
            task.status = TaskStatus.DOWNLOADING.value
            ok, path, bt_msg = self._torrent_job(task, cfg, out_dir, on_progress)
            if not ok:
                task.error_msg = bt_msg or "磁力/种子下载失败"
            elif bt_msg:
                task.resume_hint = bt_msg
        elif mt_ref:
            self.engine._stop_flags[task.id] = False
            task.status = TaskStatus.DOWNLOADING.value
            ok, path, mt_msg = tg_session.download_ref(
                task.url,
                out_dir,
                audio_only=bool(cfg.get("audio_only")),
                filename_template=cfg.get("filename_template") or "",
                progress=lambda pct, done, label, todo=0: on_progress(
                    task.id, pct, label, "",
                    {"done_bytes": int(done or 0), "total_bytes": int(todo or 0)},
                ),
                stopped=lambda: bool(self.engine._stop_flags.get(task.id)),
                force=not cfg.get("skip_downloaded", True),
            )
            if not ok:
                task.error_msg = mt_msg or "Telegram 会话下载失败"
            elif mt_msg:
                task.resume_hint = mt_msg
        else:
            ok, path = self.engine.download(
                task_id=task.id,
                url=task.url,
                out_dir=out_dir,
                cfg=cfg,
                video_q=opts.get("video_quality", cfg.get("video_quality", "best")),
                audio_q=opts.get("audio_quality", cfg.get("audio_quality", "best")),
                fmt=opts.get("format") or cfg.get("format") or "mkv",
                audio_only=opts.get("audio_only", cfg.get("audio_only", False)),
                embed_sub=opts.get("embed_sub", cfg.get("embed_sub", True)),
                sub_langs=opts.get("subtitle_langs", cfg.get("subtitle_langs", "all")),
                progress_cb=on_progress,
                force_format=opts.get("force_format") or cfg.get("force_format"),
                download_section=opts.get("download_section") or cfg.get("download_section"),
                is_live=bool(opts.get("is_live") or cfg.get("is_live")),
            )
        # 本地 AI：字幕优先流水线 / Whisper / 机翻 / 润色摘要
        if ok and path and (
            cfg.get("local_ai_transcribe")
            or cfg.get("local_ai_translate")
            or cfg.get("local_ai_mt_after_transcribe")
            or cfg.get("ai_polish")
            or cfg.get("ai_summarize")
        ):
            try:
                use_pipe = bool(
                    cfg.get("subtitle_first", True)
                    or cfg.get("ai_polish")
                    or cfg.get("ai_summarize")
                    or cfg.get("local_ai_transcribe")
                    or cfg.get("local_ai_mt_after_transcribe")
                )
                produced = []
                if use_pipe:
                    from ai_pipeline import run_pipeline
                    def _wfn(mp, lang="auto"):
                        return run_local_ai_on_file(
                            mp,
                            transcribe=True,
                            translate=False,
                            lang=lang,
                            model=(cfg.get("whisper_model") or "base"),
                            device=(cfg.get("whisper_device") or "auto"),
                            compute=(cfg.get("whisper_compute") or "auto"),
                            log=self.engine.log,
                        )
                    def _tfn(srt, tgt):
                        return translate_srt_file(
                            srt,
                            provider=(cfg.get("subtitle_translate_provider") or "deepl"),
                            target_lang=tgt,
                            source_lang=(cfg.get("local_ai_lang") or ""),
                            log=self.engine.log,
                        )
                    key = (cfg.get("openai_api_key") or "").strip()
                    pr = run_pipeline(
                        path,
                        subtitle_first=bool(cfg.get("subtitle_first", True)),
                        use_whisper=bool(
                            cfg.get("local_ai_transcribe")
                            or cfg.get("local_ai_mt_after_transcribe")
                        ),
                        polish=bool(cfg.get("ai_polish")) and bool(key),
                        summarize=bool(cfg.get("ai_summarize")) and bool(key),
                        translate_after=bool(cfg.get("local_ai_mt_after_transcribe")),
                        lang=(cfg.get("local_ai_lang") or "auto"),
                        summary_lang=(cfg.get("summary_lang") or "zh"),
                        target_lang=(cfg.get("subtitle_target_lang") or "zh"),
                        whisper_fn=_wfn,
                        translate_fn=_tfn if cfg.get("local_ai_mt_after_transcribe") else None,
                        openai_key=key,
                        openai_base=(cfg.get("openai_base_url") or "https://api.openai.com/v1"),
                        openai_model=(cfg.get("openai_model") or "gpt-4o-mini"),
                        log=self.engine.log,
                    )
                    if pr.get("srt"):
                        produced = [pr["srt"]]
                    badge = {"subtitle": "⚡平台字幕", "existing": "📄已有字幕", "whisper": "🎙Whisper"}.get(
                        pr.get("path_type") or "", pr.get("path_type") or ""
                    )
                    self.engine.log(f"[{task.id[:8]}] 流水线 [{badge}] {pr.get('message')}")
                else:
                    produced = run_local_ai_on_file(
                        path,
                        transcribe=bool(cfg.get("local_ai_transcribe") or cfg.get("local_ai_mt_after_transcribe")),
                        translate=bool(cfg.get("local_ai_translate")),
                        lang=(cfg.get("local_ai_lang") or "auto"),
                        model=(cfg.get("whisper_model") or "base"),
                        device=(cfg.get("whisper_device") or "auto"),
                        compute=(cfg.get("whisper_compute") or "auto"),
                        log=self.engine.log,
                    )
                if cfg.get("local_ai_translate"):
                    extra = run_local_ai_on_file(
                        path,
                        transcribe=False,
                        translate=True,
                        lang=(cfg.get("local_ai_lang") or "auto"),
                        model=(cfg.get("whisper_model") or "base"),
                        device=(cfg.get("whisper_device") or "auto"),
                        compute=(cfg.get("whisper_compute") or "auto"),
                        log=self.engine.log,
                    )
                    produced = list(produced or []) + list(extra or [])
            except Exception as e:
                self.engine.log(f"[{task.id[:8]}] 本地 AI 处理失败: {e}", "warning")
        # Bilibili 弹幕：视频成功后额外保存 xml + ass
        if ok and opts.get("download_danmaku", True) and is_bilibili_url(task.url):
            try:
                base = Path(path).stem if path else "danmaku"
                download_bilibili_danmaku(
                    url=task.url,
                    out_dir=str(Path(path).parent) if path else out_dir,
                    base_name=base,
                    proxy=task_proxy_override(cfg),
                    log=self.engine.log,
                )
            except Exception as e:
                self.engine.log(f"[{task.id[:8]}] 弹幕下载异常: {e}", "warning")
        # 停止直播聊天抓取 & 收尾 part
        try:
            stop_live_chat_capture(task.id)
        except Exception:
            pass
        if task.is_live or "live.bilibili.com" in (task.url or "").lower():
            try:
                room = extract_bilibili_live_room_id(task.url) or ""
                finalized = finalize_part_files(out_dir, hint=room or task.url, log=self.engine.log)
                if finalized and not path:
                    path = finalized[-1]
            except Exception as e:
                self.engine.log(f"[{task.id[:8]}] 直播收尾失败: {e}", "warning")

        # 清单上限只服务这一次收尾：取走即清，免得引擎那张表里留残值
        listed_max = self.engine.pop_listed_max(task.id)
        raw_bytes = False
        try:
            raw_bytes = self.engine.pop_raw_bytes(task.id)
        except Exception:
            pass
        # 转存/上报之前先确认「文件真的能用」：被反爬拦下时工具会正常退出并留下网页或空壳
        # 种子的主成品可能是压缩包或镜像，ffprobe 认不出的东西不该被判成「下载坏了」
        if ok and path and cfg.get("verify_download", True) and (
            task.kind != "torrent" or Path(path).suffix.lower() in _MEDIA_EXTS
        ):
            try:
                bad = verify_media_file(path)
            except Exception as e:  # 校验自身出问题不能拖累任务
                bad = ""
                self.engine.log(f"[{task.id[:8]}] 完整性校验异常（跳过）: {e}", "warning")
            if bad:
                ok = False
                task.error_msg = f"下载完成但文件不可用：{bad}（文件已保留，未转存网盘）"
                self.engine.log(f"[{task.id[:8]}] {task.error_msg}", "error")
            elif not task.is_live:
                # 直播这条路格式恒为 best（画质那一档对直播本来就不生效），回读只会怪错对象，跳过
                try:
                    task.verify_note = tier_readback(
                        path,
                        opts.get("video_quality", cfg.get("video_quality", "best")),
                        listed_max,
                        audio_only=bool(opts.get("audio_only", cfg.get("audio_only", False))),
                    )
                except Exception as e:  # 回读是附加信息，出问题也不该影响任务结论
                    self.engine.log(f"[{task.id[:8]}] 成品回读异常（跳过）: {e}", "warning")
                if task.verify_note:
                    self.engine.log(f"[{task.id[:8]}] 成品回读：{task.verify_note}", "warning")

        # 校验值核对放在 verify_download 这道闸门之外：体检说「文件能播」，
        # 摘要说的是「是不是这一份文件」，两件事各有各的开关，磁力任务也想要后一句。
        # 只在任务成功时算 —— 已经判失败的没必要再读一遍几个 G。
        if ok and path and task.expect_hash:
            hview = dict(cfg)
            hview["format"] = opts.get("format") or cfg.get("format") or "mkv"
            hsteps = [] if raw_bytes else hash_rewrite_steps(hview, task.kind)
            try:
                state, got, note = hash_readback(
                    path, task.expect_hash, task.hash_algo, hsteps,
                )
            except Exception as e:  # 和回读同一口径：核对本身出问题不牵连任务结论
                state, got, note = "", "", ""
                self.engine.log(f"[{task.id[:8]}] 校验值核对异常（跳过）: {e}", "warning")
            task.hash_state = state
            task.file_hash = got
            if note:
                task.verify_note = f"{task.verify_note}；{note}" if task.verify_note else note
                self.engine.log(f"[{task.id[:8]}] {note}", "warning")
            elif state == "ok":
                self.engine.log(f"[{task.id[:8]}] 校验值核对：{_HASH_LABELS.get(task.hash_algo, task.hash_algo)}"
                                f" 一致（{got[:16]}…）")

        # NAS / 网盘转存（成功或用户结束直播且有文件）
        if path and Path(path).is_file():
            try:
                if ok or task.status == TaskStatus.STOPPED.value or task.is_live:
                    tr = transfer_to_storage(path, self.cfg.data, log=self.engine.log)
                    if tr.get("nas"):
                        path = tr["nas"]
                        task.filepath = path
            except Exception as e:
                self.engine.log(f"[{task.id[:8]}] 存储转存异常: {e}", "warning")

        # 若用户中途暂停/停止，不要覆盖为完成/失败
        if task.status not in (TaskStatus.STOPPED.value, TaskStatus.PAUSED.value):
            # 进度回调的字节只到最后一个分片，合并/转码后的成品往往更大：收尾按真实文件算。
            # 种子不覆盖：aria2 报的 totalLength 是整个下载，path 只是挑出来的主文件
            if task.kind != "torrent":
                try:
                    if path and Path(path).is_file():
                        task.total_bytes = int(Path(path).stat().st_size)
                        task.done_bytes = task.total_bytes
                except Exception:
                    pass
            task.status = TaskStatus.FINISHED.value if ok else TaskStatus.FAILED.value
            task.filepath = path or task.filepath or ""
            task.progress = 100.0 if ok else task.progress
            if ok:
                task.error_msg = ""
                HOST_THROTTLE.recover(task.url)
            else:
                raw = task.error_msg or self.engine.pop_error(task.id) or "下载失败（详见运行日志）"
                if "原因：" not in raw and "文件不可用" not in raw:
                    try:
                        extra = risk_note_for_failure(raw, task.url or "", task.id)
                    except Exception:
                        extra = ""
                    if extra:
                        raw = f"{raw}｜{extra}"
                task.error_msg = raw
            if path and not (task.kind == "torrent" and len(task.files) > 1):
                task.title = Path(path).name
            self.history.add(
                {
                    "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "url": task.url,
                    "title": task.title,
                    "status": task.status,
                    "filepath": path or "",
                    "error": "" if ok else task.error_msg,
                    "verify_note": task.verify_note,
                }
            )
            # 通知（进 outbox 落盘，没送出去的重试）
            try:
                if ok:
                    tg_notifier.notify_done(task.title or task.url, task.url, path or "")
                else:
                    tg_notifier.notify_fail(task.title or task.url, task.url, task.error_msg)
            except Exception:
                pass
        elif task.status == TaskStatus.STOPPED.value and path:
            task.filepath = path
            if path:
                task.title = Path(path).name
        with self.lock:
            self.running = max(0, self.running - 1)
        self._pump()

    def stop_all(self):
        self.pending.clear()
        self.engine.stop()
        for t in self.tasks.values():
            if t.status == TaskStatus.DOWNLOADING.value:
                t.status = TaskStatus.STOPPED.value
                self.engine.stop(t.id)
        with self.lock:
            self.running = 0

    def end_live_tasks(self, ids: List[str] = None, reason: str = "用户结束录制") -> int:
        """结束直播录制：停止下载、收尾文件、停止聊天、暂停对应监控防自动再录"""
        count = 0
        idset = set(ids or [])
        targets = []
        if idset:
            targets = [self.tasks[tid] for tid in idset if tid in self.tasks]
        else:
            targets = [
                t for t in self.tasks.values()
                if t.is_live or (t.title or "").find("直播") >= 0
            ]
        out_dir = str(Path(cfg.data.get("download_dir") or DEFAULT_DOWNLOAD_DIR).resolve())
        paused_urls = []
        for t in targets:
            if t.status in (
                TaskStatus.DOWNLOADING.value,
                TaskStatus.QUEUED.value,
                TaskStatus.PAUSED.value,
                TaskStatus.STOPPED.value,
            ):
                try:
                    self.engine.stop(t.id)
                except Exception:
                    pass
                try:
                    stop_live_chat_capture(t.id)
                except Exception:
                    pass
                if t.id in self.pending:
                    try:
                        self.pending.remove(t.id)
                    except ValueError:
                        pass
                t.status = TaskStatus.STOPPED.value
                t.error_msg = reason
                t.speed = ""
                t.eta = ""
                paused_urls.append(t.url or "")
                # 稍等文件刷盘
                time.sleep(0.8)
                # 拉流的 ffmpeg 不会跟着停止标记退出（它全程没有进度回调），不收掉就会一直写下去
                hints = [h for h in (self.engine.live_output_stem(t.id),
                                     (t.title or "").strip(),
                                     Path(t.filepath or "").stem) if h]
                try:
                    _stop_live_recorder_children(hints, log=self.log.log)
                except Exception as e:
                    try:
                        self.log.log(f"收拉流子进程失败: {e}", "warning",
                                     k="srv.live.stream_proc_reap_failed", kv={"e": str(e)})
                    except Exception:
                        pass
                time.sleep(0.4)
                try:
                    room = extract_bilibili_live_room_id(t.url) or ""
                    finalized = finalize_part_files(
                        out_dir, hint=room or t.url, log=self.log.log
                    )
                    if not finalized:
                        finalized = _find_recent_media_files(out_dir, hint=room or t.url)
                    if not finalized:
                        # 直播成品是按标题命名的，房间号/链接对不上名字（B站标题里通常也没有房间号）。
                        # 只认收尾这一刻刚刚写完的那一份：窗口里出现两份以上说明分不清是谁的，宁可不写。
                        recent = _find_recent_media_files(out_dir, hint="", within_sec=90)
                        if len(recent) == 1:
                            finalized = recent
                    if finalized:
                        t.filepath = finalized[0]
                        t.title = Path(finalized[0]).name
                    chats = harvest_ytdlp_live_chat_files(out_dir, log=self.log.log)
                    # 也收集我们自己写的 chat 文件
                    for p in Path(out_dir).glob(f"*{t.id[:8]}*.chat.*"):
                        chats.append(str(p))
                    if room:   # 房间号为空时通配会变成「**.ass」，Path.glob 会当场抛错
                        for p in Path(out_dir).glob(f"*{room}*.ass"):
                            chats.append(str(p))
                    if chats:
                        t.chat_file = chats[-1]
                        self.log.log(f"聊天/弹幕文件: {Path(chats[-1]).name}",
                                     k="srv.live.chat_file", kv={"name": Path(chats[-1]).name})
                except Exception as e:
                    try:
                        self.log.log(f"收尾失败: {e}", "warning",
                                     k="srv.live.finalize_failed", kv={"e": str(e)})
                    except Exception:
                        pass
                count += 1
                try:
                    self.log.log(f"已结束直播录制: {(t.title or t.url)[:60]}",
                                 k="srv.live.recording_ended", kv={"what": (t.title or t.url)[:60]})
                except Exception:
                    pass
        # 暂停对应直播监控，避免立刻再次自动开录
        if paused_urls:
            try:
                items = _load_live_monitors()
                changed = False
                for m in items:
                    mu = (m.get("url") or "").rstrip("/")
                    for u in paused_urls:
                        uu = (u or "").rstrip("/")
                        room = extract_bilibili_live_room_id(uu) or ""
                        if mu == uu or (room and room in mu):
                            m["paused"] = True
                            m["status"] = "录制已暂停"
                            m["last_live"] = True
                            changed = True
                            self.log.log(f"已暂停监控自动录制: {mu}",
                                         k="srv.live.monitor_paused", kv={"mu": mu})
                if changed:
                    _save_live_monitors(items)
            except Exception as e:
                try:
                    self.log.log(f"暂停监控失败: {e}", "warning",
                                 k="srv.live.monitor_pause_failed", kv={"e": str(e)})
                except Exception:
                    pass
        return count

    def pause_all(self):
        """暂停队列：进行中的任务标记为暂停并取消下载，排队任务保持可恢复"""
        self.paused = True
        # 取出 pending 中的任务标为 paused（仍保留在 tasks）
        still = []
        while self.pending:
            tid = self.pending.pop(0)
            t = self.tasks.get(tid)
            if t and t.status == TaskStatus.QUEUED.value:
                t.status = TaskStatus.PAUSED.value
            else:
                still.append(tid)
        self.pending = still
        for t in self.tasks.values():
            if t.status == TaskStatus.DOWNLOADING.value:
                t.status = TaskStatus.PAUSED.value
                try:
                    self.engine.stop(t.id)
                except Exception:
                    pass
        self.log.log("队列已暂停", k="srv.queue.paused")

    def resume_all(self):
        self.paused = False
        for tid, t in self.tasks.items():
            if t.status == TaskStatus.PAUSED.value:
                t.status = TaskStatus.QUEUED.value
                t.progress = 0
                t.error_msg = ""
                if tid not in self.pending:
                    self.pending.append(tid)
        self.log.log("队列已继续", k="srv.queue.resumed")
        self._pump()

    def pause_tasks(self, ids: List[str]):
        idset = set(ids or [])
        self.pending = [tid for tid in self.pending if tid not in idset]
        for tid in idset:
            t = self.tasks.get(tid)
            if not t:
                continue
            if t.status == TaskStatus.DOWNLOADING.value:
                t.status = TaskStatus.PAUSED.value
                try:
                    self.engine.stop(tid)
                except Exception:
                    pass
            elif t.status == TaskStatus.QUEUED.value:
                t.status = TaskStatus.PAUSED.value

    def resume_tasks(self, ids: List[str]):
        for tid in ids or []:
            t = self.tasks.get(tid)
            if not t:
                continue
            if t.status in (TaskStatus.PAUSED.value, TaskStatus.STOPPED.value, TaskStatus.FAILED.value):
                t.status = TaskStatus.QUEUED.value
                t.progress = 0
                t.error_msg = ""
                if tid not in self.pending:
                    self.pending.append(tid)
        self.paused = False
        self._pump()

    def bt_release(self, t: DownloadTask):
        """任务行被删掉时顺带停掉 aria2 那边：留着就成了一个界面上看不见的上传进程。"""
        gid = (t.gid or "").strip()
        if not gid:
            return
        with _BT_WATCH_LOCK:
            _BT_WATCH.pop(gid, None)
        t.seeding = False
        try:
            _bt_client(dict(self.cfg.data)).remove(gid)
        except Exception as e:
            self.log.log(f"通知 aria2 移除任务失败（{gid[:10]}）：{e}", "warning",
                         k="srv.queue.aria2_remove_failed", kv={"gid": gid[:10], "e": str(e)})

    def delete_tasks(self, ids: List[str]):
        idset = set(ids or [])
        self.pending = [tid for tid in self.pending if tid not in idset]
        for tid in idset:
            t = self.tasks.get(tid)
            if not t:
                continue
            if t.status == TaskStatus.DOWNLOADING.value:
                try:
                    self.engine.stop(tid)
                except Exception:
                    pass
            self.bt_release(t)
            del self.tasks[tid]

    def retry_failed(self):
        for tid, t in self.tasks.items():
            if t.status == TaskStatus.FAILED.value:
                t.status = TaskStatus.QUEUED.value
                t.progress = 0
                t.error_msg = ""
                self.pending.append(tid)
        self.paused = False
        self._pump()

    def retry_one(self, tid: str, extra_opts: Optional[dict] = None) -> bool:
        t = self.tasks.get(tid)
        if not t:
            return False
        if t.status not in (
            TaskStatus.FAILED.value, TaskStatus.STOPPED.value, TaskStatus.PAUSED.value, TaskStatus.FINISHED.value
        ):
            return False
        if extra_opts:
            opts = dict(getattr(t, "_opts", {}) or {})
            opts.update(extra_opts)
            t._opts = opts  # type: ignore
            if any(k in extra_opts for k in COOKIE_LAYER_KEYS):
                # 人明确动了 Cookie 这一层：公开优先那次判定作废，按新配置重新判
                self.engine.drop_cookie_pref(t.url)
        t.status = TaskStatus.QUEUED.value
        t.progress = 0
        t.error_msg = ""
        t.started_at = ""
        if tid not in self.pending:
            self._insert_pending(tid)
        self.paused = False
        self._pump()
        return True

    def clear_finished(self):
        for tid in list(self.tasks.keys()):
            if self.tasks[tid].status == TaskStatus.FINISHED.value:
                del self.tasks[tid]


# -------------------- FastAPI --------------------
cfg = ConfigManager()
log_mgr = LogManager()
history_mgr = HistoryManager()
# 适配口统一带 k/kv：类里 self.log(...) 想挂键时得一路走到 LogManager，
# 不然 TypeError 只是推迟到下一批文案提交里才炸。
ffmpeg_mgr = FFmpegManager(log=lambda m, level="info", k="", kv=None: log_mgr.log(m, level, k=k, kv=kv))
ffmpeg_mgr.manual_path = (cfg.data.get("ffmpeg_path") or "").strip()
engine = DownloaderEngine(log_cb=lambda m, level="info", k="", kv=None: log_mgr.log(m, level, k=k, kv=kv),
                          ffmpeg_mgr=ffmpeg_mgr)
queue = TaskQueue(engine, cfg, log_mgr, history_mgr)
tg_notifier = TelegramNotifier(cfg, log=lambda m, level="info", k="", kv=None: log_mgr.log(m, level, k=k, kv=kv))
# Telegram 用户会话（私有/需登录频道）：客户端要跨请求存活，所以是模块级单例
from telegram_mt import TelegramSession  # noqa: E402

tg_session = TelegramSession(
    lambda: cfg.data,
    log=lambda m, level="info": log_mgr.log(m, level),
    session_dir=APP_DIR / "tg_session",
    index_path=APP_DIR / "tg_media_index.json",
)
sub_mgr = SubscriptionManager(
    engine, cfg, queue, tg_notifier,
    log=lambda m, level="info", k="", kv=None: log_mgr.log(m, level, k=k, kv=kv)
)
sub_mgr.start_scheduler()

app = FastAPI(title="多媒体下载器", version="2.0.0")
STATIC = APP_DIR / "static"
STATIC.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


# -------------------- 访问保护（登录）：只拦非本机来的连接 --------------------
# 8765 是裸 HTTP：谁能连上这个端口，谁就能改设置、翻下载目录、用已存好的平台 cookie。
# 口径（界面上那句话与代码同一套）：
#   - 开关默认关，开着也只在「来源不是 127.0.0.1/::1」时才要登录 —— 本机浏览器、MCP 桥、
#     自检、扩展的既有用法一律不受影响；
#   - 第二道门是机器令牌（X-MDL-Token）：给需要跨主机/走反向代理的自动调用用，
#     但它只开数据接口，改口令、开关这类动作仍得从界面来；
#   - 口令只存 PBKDF2 加盐哈希，SECRET_KEY（会话签名用）首次用到时生成并写进 config.json，
#     所以重启后浏览器不用重登。
AUTH_COOKIE = "mdl_session"
AUTH_TOKEN_HEADER = "x-mdl-token"
AUTH_COOKIE_VERSION = 1
AUTH_PBKDF2_ROUNDS = 240_000
AUTH_REFRESH_SLICE = 300          # 会话滑动续期的最小间隔：5 分钟内的请求不重设 cookie
AUTH_FAIL_WINDOW = 3600           # 隔了一小时再试，之前的失败次数不作数
AUTH_PUBLIC_PATHS = ("/", "/index.html", "/favicon.ico", "/api/auth/status", "/api/auth/login")
_auth_lock = threading.Lock()
_auth_state: Dict[str, Any] = {"fails": {}, "locked": {}}


def _is_loopback_host(host: str) -> bool:
    h = str(host or "").strip().lower()
    if h.startswith("::ffff:"):
        h = h[7:]
    if h in ("", "localhost", "::1"):
        return True
    return h == "127.0.0.1" or h.startswith("127.")


def _auth_client_ip(request: Request) -> str:
    # 只认 TCP 真实来源，故意不看 X-Forwarded-For：这个值同时用来判「本机免登录」，
    # 信了请求头就等于把门交给任何一个会写 header 的人。
    client = getattr(request, "client", None)
    return str(getattr(client, "host", "") or "")


def _auth_cfg_int(key: str, default: int, lo: int, hi: int) -> int:
    try:
        v = int(cfg.data.get(key))
    except (TypeError, ValueError):
        v = default
    return max(lo, min(hi, v))


def _auth_idle_seconds() -> int:
    return _auth_cfg_int("web_auth_session_hours", 12, 1, 720) * 3600


def _auth_remember_seconds() -> int:
    return _auth_cfg_int("web_auth_remember_days", 30, 1, 365) * 86400


def _auth_lock_seconds() -> int:
    return _auth_cfg_int("web_auth_lock_minutes", 15, 1, 1440) * 60


def _auth_secret_key(rotate: bool = False) -> str:
    """会话签名用的 256-bit 密钥：第一次用到时生成并落盘，重启后登录态不丢。"""
    with _auth_lock:
        cur = str(cfg.data.get("secret_key") or "").strip()
        if cur and not rotate:
            return cur
        cur = secrets.token_hex(32)
        cfg.data["secret_key"] = cur
        cfg.save()
        return cur


def _auth_machine_token_value() -> str:
    """只读当下存着的那串：读状态、比对令牌都不该顺手生成并落盘。"""
    return str(cfg.data.get("web_auth_machine_token") or "").strip()


def _auth_machine_token(rotate: bool = False) -> str:
    """确保有一串机器令牌（界面上点「重置」才走这里）；比对用的一律用上面那个只读版。"""
    with _auth_lock:
        cur = _auth_machine_token_value()
        if cur and not rotate:
            return cur
        cur = secrets.token_hex(24)
        cfg.data["web_auth_machine_token"] = cur
        cfg.save()
        return cur


def _auth_hash_password(pw: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), salt, AUTH_PBKDF2_ROUNDS)
    return ("pbkdf2_sha256$%d$%s$%s" % (AUTH_PBKDF2_ROUNDS,
                                        base64.b64encode(salt).decode(),
                                        base64.b64encode(dk).decode()))


def _auth_verify_password(pw: str, stored: str) -> bool:
    parts = str(stored or "").split("$")
    if len(parts) != 4 or parts[0] != "pbkdf2_sha256":
        return False
    try:
        rounds = int(parts[1])
        salt = base64.b64decode(parts[2])
        want = base64.b64decode(parts[3])
    except Exception:
        return False
    got = hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), salt, max(1, rounds))
    return hmac.compare_digest(got, want)


def _auth_password_set() -> bool:
    return bool(str(cfg.data.get("web_auth_password_hash") or "").strip())


def _auth_enforcing() -> bool:
    # 开了开关却还没设口令时不拦人：那时没人能登进来，拦了等于把服务锁死。
    # 这种情况在 /api/auth/status 里明说「保护还没生效」。
    return bool(cfg.data.get("web_auth_enabled")) and _auth_password_set()


def _auth_sign(body: str) -> str:
    return hmac.new(_auth_secret_key().encode(), body.encode(), hashlib.sha256).hexdigest()[:40]


def _auth_new_cookie(remember: bool) -> Tuple[str, int]:
    now = int(time.time())
    idle = _auth_idle_seconds()
    hard = max(idle, _auth_remember_seconds()) if remember else idle
    payload = {"v": AUTH_COOKIE_VERSION, "iat": now, "last": now, "exp": now + hard,
               "rm": 1 if remember else 0}
    body = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    return f"{body}.{_auth_sign(body)}", hard


def _auth_parse_cookie(val: str) -> Tuple[bool, str, dict]:
    """(有效?, 原因, payload)。原因：ok / empty / bad / expired / idle。"""
    raw = str(val or "")
    if "." not in raw:
        return False, "empty", {}
    body, sig = raw.rsplit(".", 1)
    if not hmac.compare_digest(sig, _auth_sign(body)):
        return False, "bad", {}
    try:
        payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    except Exception:
        return False, "bad", {}
    if int(payload.get("v") or 0) != AUTH_COOKIE_VERSION:
        return False, "bad", {}
    now = int(time.time())
    if now > int(payload.get("exp") or 0):
        return False, "expired", payload
    if now - int(payload.get("last") or 0) > _auth_idle_seconds():
        return False, "idle", payload
    return True, "ok", payload


def _auth_authorized(request: Request) -> bool:
    """这个请求自己有没有过门的凭据（不含「开关关着」这一层）。"""
    if _is_loopback_host(_auth_client_ip(request)):
        return True
    tok = str(request.headers.get(AUTH_TOKEN_HEADER) or "").strip()
    saved = _auth_machine_token_value()
    if tok and saved and hmac.compare_digest(tok, saved):
        return True
    ok, _, _ = _auth_parse_cookie(request.cookies.get(AUTH_COOKIE, ""))
    return ok


def _auth_token_only(request: Request) -> bool:
    """这个请求是不是「只靠机器令牌进来的」：本机直连或带有效会话都不算。"""
    if _is_loopback_host(_auth_client_ip(request)):
        return False
    ok, _, _ = _auth_parse_cookie(request.cookies.get(AUTH_COOKIE, ""))
    if ok:
        return False
    tok = str(request.headers.get(AUTH_TOKEN_HEADER) or "").strip()
    saved = _auth_machine_token_value()
    return bool(tok) and bool(saved) and hmac.compare_digest(tok, saved)


def _auth_gate_reason(request: Request) -> str:
    """""/api/* 这个请求拦不拦：返回 ""（放行）或拒绝原因。"""
    if not _auth_enforcing():
        return ""
    path = request.url.path
    if path in AUTH_PUBLIC_PATHS or path.startswith("/static/"):
        return ""
    if _is_loopback_host(_auth_client_ip(request)):
        return ""
    tok = str(request.headers.get(AUTH_TOKEN_HEADER) or "").strip()
    if tok and hmac.compare_digest(tok, _auth_machine_token_value()) and not path.startswith("/api/auth/"):
        return ""
    ok, why, _ = _auth_parse_cookie(request.cookies.get(AUTH_COOKIE, ""))
    return "" if ok else why


AUTH_DENIED_TEXT = {
    "empty": "要登录：请在弹出的窗口里输入访问口令",
    "bad": "登录状态已失效（口令改过或本机密钥换了），请重新登录",
    "expired": "登录状态过期了，请重新登录",
    "idle": "这台浏览器空闲太久，请重新登录",
}


def _auth_denied(request: Request, why: str) -> JSONResponse:
    return JSONResponse(status_code=401,
                        content={"detail": AUTH_DENIED_TEXT.get(why, "要登录"),
                                 "auth_required": True, "reason": why})


def _auth_state_load():
    global _auth_state
    try:
        if AUTH_STATE_FILE.exists():
            with open(AUTH_STATE_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
            with _auth_lock:
                _auth_state = {"fails": dict(raw.get("fails") or {}),
                               "locked": dict(raw.get("locked") or {})}
    except Exception as e:
        log_mgr.log(f"读取登录锁定状态失败（按无锁定处理）: {e}", "warning",
                    k="srv.auth.state_load_failed", kv={"e": str(e)})


def _auth_state_save():
    # 临时文件 + os.replace：被硬杀也不能把「谁正在被锁」忘掉，否则重启就给了爆破者新一轮机会
    with _auth_lock:
        snap = json.dumps({"fails": _auth_state["fails"], "locked": _auth_state["locked"]},
                          ensure_ascii=False, indent=2)
    tmp = Path(str(AUTH_STATE_FILE) + ".tmp")
    try:
        tmp.write_text(snap, encoding="utf-8")
        os.replace(tmp, AUTH_STATE_FILE)
    except Exception as e:
        log_mgr.log(f"保存登录锁定状态失败: {e}", "warning",
                    k="srv.auth.state_save_failed", kv={"e": str(e)})


def _auth_locked_seconds(ip: str, now: Optional[float] = None) -> int:
    now = now or time.time()
    with _auth_lock:
        until = float(_auth_state["locked"].get(ip) or 0)
    return max(0, int(round(until - now)))


def _auth_note_fail(ip: str) -> dict:
    """记一次失败口令。返回这次的计数情况，调用方据此决定回什么、要不要发通知。"""
    now = time.time()
    limit = _auth_cfg_int("web_auth_max_fails", 5, 1, 50)
    with _auth_lock:
        rec = dict(_auth_state["fails"].get(ip) or {})
        had_fails = bool(rec)
        if now - float(rec.get("last") or 0) > AUTH_FAIL_WINDOW:
            rec = {}
        rec["n"] = int(rec.get("n") or 0) + 1
        rec["first"] = float(rec.get("first") or now)
        rec["last"] = now
        _auth_state["fails"][ip] = rec
        n = int(rec["n"])
        just_locked, lock_secs = False, 0
        if n >= limit and ip not in _auth_state["locked"]:
            lock_secs = _auth_lock_seconds()
            _auth_state["locked"][ip] = now + lock_secs
            _auth_state["fails"].pop(ip, None)
            just_locked = True
    _auth_state_save()
    return {"just_locked": just_locked, "lock_seconds": lock_secs, "fails": n,
            "had_fails": had_fails, "limit": limit}


def _auth_clear_fails(ip: str):
    with _auth_lock:
        _auth_state["fails"].pop(ip, None)
        _auth_state["locked"].pop(ip, None)
    _auth_state_save()


def _auth_locks_payload() -> List[dict]:
    now = time.time()
    out = []
    with _auth_lock:
        for ip, until in sorted(_auth_state["locked"].items()):
            left = float(until) - now
            if left <= 0:
                continue
            out.append({"ip": ip, "left": int(round(left))})
        for ip, rec in sorted(_auth_state["fails"].items()):
            if now - float(rec.get("last") or 0) > AUTH_FAIL_WINDOW:
                continue
            out.append({"ip": ip, "left": 0, "fails": int(rec.get("n") or 0)})
    return out


def _auth_notify(text: str):
    # 走「失败/告警」这条通知开关：没开任何通道时静默跳过，绝不因为通知炸了把登录接口带崩
    try:
        _notify_enqueue("fail", "登录保护", text)
    except Exception as e:
        log_mgr.log(f"登录保护事件进通知队列失败: {e}", "warning",
                    k="srv.auth.notify_enqueue_failed", kv={"e": str(e)})


_auth_state_load()


@app.middleware("http")
async def web_auth_middleware(request: Request, call_next):
    why = _auth_gate_reason(request)
    if why:
        return _auth_denied(request, why)
    response = await call_next(request)
    # 词表每次启动都可能换一批键；静态文件默认走浏览器启发式缓存，页面重开还在用旧词表，
    # 新模板里的键就会原样印成 settings.xxx。要求每次回源校验，没变时仍是 304。
    if request.url.path == "/static/i18n.js":
        response.headers["Cache-Control"] = "no-cache"
    # 会话滑动续期：还活跃就不该在半路被踢，但也不必每个请求都重设 cookie
    if _auth_enforcing() and request.url.path not in AUTH_PUBLIC_PATHS \
            and not request.url.path.startswith("/api/auth/"):
        raw = request.cookies.get(AUTH_COOKIE, "")
        ok, _, payload = _auth_parse_cookie(raw)
        if ok and not payload.get("rm") and time.time() - int(payload.get("last") or 0) > AUTH_REFRESH_SLICE:
            value, max_age = _auth_new_cookie(False)
            response.set_cookie(AUTH_COOKIE, value, max_age=max_age, httponly=True,
                                samesite="lax", path="/")
    return response


class LoginBody(BaseModel):
    password: str = ""
    remember: bool = False


class PasswordBody(BaseModel):
    password: str = ""
    current: str = ""


class UnlockBody(BaseModel):
    ip: Optional[str] = None


@app.get("/api/auth/status")
def api_auth_status(request: Request):
    ip = _auth_client_ip(request)
    left = _auth_locked_seconds(ip)
    return {
        "enabled": bool(cfg.data.get("web_auth_enabled")),
        "enforcing": _auth_enforcing(),
        "password_set": _auth_password_set(),
        "loopback": _is_loopback_host(ip),
        "client_ip": ip,
        # 当前这个请求是不是「免登录的本机/带令牌/已登录」状态，界面据此决定要不要弹登录窗
        "authorized": _auth_authorized(request),
        "locked": bool(left),
        "lock_left": left,
        "locks": _auth_locks_payload(),
        "session_hours": _auth_cfg_int("web_auth_session_hours", 12, 1, 720),
        "remember_days": _auth_cfg_int("web_auth_remember_days", 30, 1, 365),
        "max_fails": _auth_cfg_int("web_auth_max_fails", 5, 1, 50),
        "lock_minutes": _auth_cfg_int("web_auth_lock_minutes", 15, 1, 1440),
        "machine_token_set": bool(str(cfg.data.get("web_auth_machine_token") or "").strip()),
        # 令牌只在「已经过了门」的请求里回给界面（本机也算），否则这个公开接口就把它白送出去了
        "machine_token": _auth_machine_token_value() if _auth_authorized(request) else "",
        "note": ("" if not cfg.data.get("web_auth_enabled") else
                 ("保护已生效：只有非本机来的连接要登录" if _auth_enforcing() else
                  "开关开了但口令还没设，保护暂时没生效")),
    }


@app.post("/api/auth/login")
def api_auth_login(body: LoginBody, request: Request):
    ip = _auth_client_ip(request)
    left = _auth_locked_seconds(ip)
    if left:
        log_mgr.log(f"登录被拒（这台设备正在锁定期内）：{ip}，还锁 {left} 秒", "warning",
                    k="srv.auth.login_locked_out", kv={"ip": ip, "n": left})
        raise HTTPException(423, f"连续错太多次，已锁到 {left} 秒之后")
    if not _auth_password_set():
        raise HTTPException(400, "还没设访问口令：先在「设置 → 访问保护」里设一个")
    pw = str(body.password or "")
    if not pw or not _auth_verify_password(pw, str(cfg.data.get("web_auth_password_hash"))):
        r = _auth_note_fail(ip)
        if r["just_locked"]:
            lock_minutes = r["lock_seconds"] // 60
            log_mgr.log(f"口令连续错 {r['limit']} 次，锁定 {ip} 共 {lock_minutes} 分钟", "error",
                        k="srv.auth.locked_after_fails",
                        kv={"n": r["limit"], "ip": ip, "m": lock_minutes})
            _auth_notify(f"⛔ 口令连续错满 {r['limit']} 次，{r['lock_seconds'] // 60} 分钟内不能再试\n来源：{ip}")
            raise HTTPException(423, f"口令连续错满 {r['limit']} 次，已锁 {r['lock_seconds'] // 60} 分钟")
        log_mgr.log(f"登录失败：口令不对（{ip}，第 {r['fails']} 次）", "warning",
                    k="srv.auth.login_wrong_password", kv={"ip": ip, "n": r["fails"]})
        raise HTTPException(401, f"口令不对，还能试 {max(0, r['limit'] - r['fails'])} 次")
    value, max_age = _auth_new_cookie(bool(body.remember))
    had_fails = bool(_auth_state["fails"].get(ip))
    _auth_clear_fails(ip)
    resp = JSONResponse(content={"ok": True, "remember": bool(body.remember),
                                 "expires_in": max_age,
                                 "detail": "登录成功"})
    resp.set_cookie(AUTH_COOKIE, value, max_age=max_age, httponly=True, samesite="lax", path="/")
    if body.remember:
        log_mgr.log(f"登录成功（{ip}，已记住这台设备）",
                    k="srv.auth.login_ok_remembered", kv={"ip": ip})
    else:
        log_mgr.log(f"登录成功（{ip}）", k="srv.auth.login_ok", kv={"ip": ip})
    if had_fails:
        _auth_notify(f"口令试错之后终于登进来了\n来源：{ip}")
    return resp


@app.post("/api/auth/logout")
def api_auth_logout(request: Request):
    resp = JSONResponse(content={"ok": True})
    resp.delete_cookie(AUTH_COOKIE, path="/")
    return resp


@app.post("/api/auth/password")
def api_auth_password(body: PasswordBody, request: Request):
    """设/改访问口令。改了就用新的 SECRET_KEY 重签会话，旧浏览器一律重新登录。"""
    pw = str(body.password or "")
    if len(pw) < 6:
        raise HTTPException(400, "口令至少 6 个字符")
    if len(pw.encode("utf-8")) > 256:
        raise HTTPException(400, "口令太长了（上限 256 字节）")
    if _auth_password_set():
        cur = str(body.current or "")
        if not _auth_verify_password(cur, str(cfg.data.get("web_auth_password_hash"))):
            _auth_note_fail(_auth_client_ip(request))
            raise HTTPException(401, "当前口令不对，没改")
    cfg.data["web_auth_password_hash"] = _auth_hash_password(pw)
    cfg.save()
    _auth_secret_key(rotate=True)
    log_mgr.log("访问口令已更新（这台服务上的旧登录状态全部作废）", k="srv.auth.password_updated")
    return {"ok": True, "password_set": True}


@app.get("/api/auth/machine_token")
def api_auth_machine_token_get(request: Request):
    return {"machine_token": _auth_machine_token_value() if _auth_authorized(request) else "",
            "header": AUTH_TOKEN_HEADER,
            "detail": ("把环境变量 MEDIADOWNLOADER_MCP_TOKEN 设成这串，"
                       "或直接让 MCP 桥读本机的 config.json")}


@app.post("/api/auth/machine_token")
def api_auth_machine_token_rotate(request: Request):
    if not _auth_authorized(request):
        raise HTTPException(401, AUTH_DENIED_TEXT["empty"])
    tok = _auth_machine_token(rotate=True)
    log_mgr.log("机器令牌已重置（旧的立即失效，MCP 桥那边要换新的）",
                k="srv.auth.machine_token_rotated")
    return {"ok": True, "machine_token": tok, "header": AUTH_TOKEN_HEADER}


@app.post("/api/auth/unlock")
def api_auth_unlock(body: UnlockBody):
    ip = str(body.ip or "").strip()
    if ip:
        _auth_clear_fails(ip)
        log_mgr.log(f"已解锁登录锁定：{ip}", k="srv.auth.unlocked", kv={"ip": ip})
    else:
        with _auth_lock:
            n = len(_auth_state["locked"])
            _auth_state["locked"].clear()
            _auth_state["fails"].clear()
        _auth_state_save()
        log_mgr.log(f"已清空全部登录锁定与失败计数（原来有 {n} 个在锁）",
                    k="srv.auth.locks_cleared", kv={"n": n})
    return {"ok": True, "locks": _auth_locks_payload()}


def _auth_config_mask(data: dict) -> dict:
    """口令哈希 / SECRET_KEY / 机器令牌不回显：哈希能被离线爆破，后两条是能直接开门的东西。"""
    out = dict(data)
    out["web_auth_password_set"] = bool(str(data.get("web_auth_password_hash") or "").strip())
    out["secret_key_set"] = bool(str(data.get("secret_key") or "").strip())
    # CookieCloud 的密钥是拿来看密文的口令，不是哈希，只能原样存，那就一份也别往外发
    out["cookiecloud_key_set"] = bool(str(data.get("cookiecloud_key") or "").strip())
    for k in ("secret_key", "web_auth_password_hash", "web_auth_machine_token", "cookiecloud_key"):
        out[k] = ""
    return out



class AddUrlsBody(BaseModel):
    urls: List[str]
    video_quality: str = "best"
    audio_quality: str = "best"
    format: str = "mkv"
    audio_only: bool = False
    embed_sub: bool = True
    subtitle_langs: str = "all"
    download_danmaku: bool = True
    embed_thumb: bool = True
    embed_meta: bool = True
    embed_chapters: bool = True
    local_ai_transcribe: bool = False
    local_ai_translate: bool = False
    local_ai_lang: str = "zh"
    skip_downloaded: bool = True
    verify_download: Optional[bool] = None  # 不传 = 跟随全局：下载完体检成品文件
    allow_playlist: bool = False
    # 合集/播放列表整批落点：开关 + 这一批属于哪个合集（解析页/搜索页带过来，逐条链接那一侧只有前端知道）
    playlist_subdir: Optional[bool] = None
    playlist_folder: Optional[str] = None
    sponsorblock: str = "off"
    prefer_codec: str = "auto"
    write_sub_files: Optional[bool] = None  # 不传 = 跟随全局设置：成品旁是否另存 .vtt/.srt
    download_dir: Optional[str] = None
    force_format: Optional[str] = None  # 指定 yt-dlp format_id 或表达式
    ytdlp_extra_args: Optional[str] = None  # 不传 = 跟随设置里的「自定义 yt-dlp 参数」
    download_section: Optional[str] = None  # 框选片段，如 *00:01:00-00:02:30 或 1:00-2:30
    is_live: bool = False  # 直播录制
    live_max_minutes: Optional[int] = None  # 直播：录满这么多分钟自动结束并保存，0 = 不限，不传 = 跟随设置
    download_later: bool = False  # 稍后下载（入队但不立即开始）
    pinned: bool = False
    priority: int = 0
    use_hls_engine: bool = False  # 嗅探到的 HLS 优先用专用引擎
    torrent_seed_ratio: Optional[float] = None  # 磁力/种子：传到这个比率就停种，0=不按比率
    torrent_seed_time: Optional[int] = None     # 磁力/种子：做满这么多秒就停种，0=不按时长
    torrent_seed_only: bool = False             # 磁力/种子：本地已经有这份文件，只挂做种、不再下一遍
    expect_hash: Optional[str] = None           # 成品校验值核对：期望的 MD5/SHA 摘要，留空=不核对
    hash_algo: str = "auto"                     # 算法；auto = 由这串的长度反推


class ConfigBody(BaseModel):
    download_dir: Optional[str] = None
    video_quality: Optional[str] = None
    audio_quality: Optional[str] = None
    format: Optional[str] = None
    video_encoder: Optional[str] = None
    video_cpu_codec: Optional[str] = None
    video_cpu_preset: Optional[str] = None
    embed_sub: Optional[bool] = None
    audio_only: Optional[bool] = None
    subtitle_langs: Optional[str] = None
    proxy: Optional[str] = None
    proxy_mode: Optional[str] = None
    proxy_by_platform: Optional[dict] = None
    concurrent: Optional[int] = None
    cookie_source: Optional[str] = None
    cookie_browser: Optional[str] = None
    cookie_file: Optional[str] = None
    cookie_public_first: Optional[bool] = None  # 公开优先：匿名先试、被登录墙那类挡住才带 Cookie
    ffmpeg_path: Optional[str] = None
    filename_template: Optional[str] = None
    speed_limit: Optional[str] = None
    write_description: Optional[bool] = None
    write_info_json: Optional[bool] = None
    write_sub_files: Optional[bool] = None
    dark_mode: Optional[bool] = None
    ui_theme: Optional[str] = None
    ui_language: Optional[str] = None
    skip_downloaded: Optional[bool] = None
    allow_playlist: Optional[bool] = None
    playlist_subdir: Optional[bool] = None  # 合集整批时自动建一层同名文件夹
    sponsorblock: Optional[str] = None
    ytdlp_extra_args: Optional[str] = None  # 自定义 yt-dlp 参数（一行命令行式参数）
    telegram_enabled: Optional[bool] = None
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    telegram_notify_done: Optional[bool] = None
    telegram_notify_fail: Optional[bool] = None
    telegram_notify_sub: Optional[bool] = None
    telegram_commands_enabled: Optional[bool] = None
    sub_interval_min: Optional[int] = None
    sub_auto_download: Optional[bool] = None
    live_from_start: Optional[bool] = None
    live_max_minutes: Optional[int] = None
    platform_cookies: Optional[dict] = None
    risk_delay_sec: Optional[float] = None
    risk_max_per_host: Optional[int] = None
    risk_cooldown_429: Optional[int] = None
    risk_user_agent: Optional[str] = None
    risk_preset: Optional[str] = None
    serverchan_sendkey: Optional[str] = None
    wecom_enabled: Optional[bool] = None
    wecom_corp_id: Optional[str] = None
    wecom_corp_secret: Optional[str] = None
    wecom_agent_id: Optional[str] = None
    wecom_touser: Optional[str] = None
    wecom_notify_done: Optional[bool] = None
    wecom_notify_fail: Optional[bool] = None
    wecom_notify_sub: Optional[bool] = None
    storage_post_action: Optional[str] = None
    storage_nas_enabled: Optional[bool] = None
    storage_nas_path: Optional[str] = None
    storage_webdav_enabled: Optional[bool] = None
    storage_webdav_url: Optional[str] = None
    storage_webdav_user: Optional[str] = None
    storage_webdav_pass: Optional[str] = None
    storage_webdav_path: Optional[str] = None
    nocheckcertificate: Optional[bool] = None
    live_stream_pref_bilibili: Optional[str] = None
    live_stream_pref_youtube: Optional[str] = None
    live_stream_pref_douyin: Optional[str] = None
    live_stream_pref_twitch: Optional[str] = None
    live_stream_pref_default: Optional[str] = None
    live_stream_fallback: Optional[bool] = None
    global_speed_limit: Optional[str] = None
    speed_windows: Optional[str] = None
    # 队列定时窗：这两个字段必须在这里挂着，ConfigBody 用 exclude_none 收身，
    # 没声明的键会在 model_dump 那一步被丢掉，表现就是「设置存了但没生效」
    run_window: Optional[str] = None
    queue_windows: Optional[dict] = None
    max_per_host: Optional[int] = None
    adaptive_throttle: Optional[bool] = None
    plugins_enabled: Optional[bool] = None
    aria2_enabled: Optional[bool] = None
    aria2_rpc: Optional[str] = None
    aria2_secret: Optional[str] = None
    aria2_split: Optional[int] = None
    aria2_for_large_mb: Optional[int] = None
    aria2_bin: Optional[str] = None
    aria2_autostart: Optional[bool] = None
    torrent_seed_ratio: Optional[float] = None
    torrent_seed_time: Optional[int] = None
    torrent_meta_timeout: Optional[int] = None
    bt_trackers: Optional[str] = None
    bt_tracker_sources: Optional[str] = None
    bt_tracker_auto_update: Optional[bool] = None
    bt_tracker_max: Optional[int] = None
    bt_dl_limit: Optional[str] = None
    bt_ul_limit: Optional[str] = None
    bt_prioritize_piece: Optional[bool] = None
    bt_auto_rules: Optional[list] = None
    bt_auto_fallback: Optional[str] = None
    clipboard_watch: Optional[bool] = None
    http_impersonate: Optional[bool] = None
    po_provider_enabled: Optional[bool] = None
    po_provider_url: Optional[str] = None
    yt_player_clients: Optional[str] = None
    github_mirror: Optional[str] = None
    pip_mirror: Optional[str] = None
    components_auto_check: Optional[bool] = None
    sub_first_download_n: Optional[int] = None
    named_queues: Optional[list] = None
    concurrent_fragments: Optional[int] = None
    local_ai_transcribe: Optional[bool] = None
    local_ai_translate: Optional[bool] = None
    local_ai_lang: Optional[str] = None
    whisper_model: Optional[str] = None
    whisper_device: Optional[str] = None
    whisper_compute: Optional[str] = None
    diarization_enabled: Optional[bool] = None
    diarization_max_speakers: Optional[int] = None
    hf_token: Optional[str] = None
    subtitle_translate_provider: Optional[str] = None
    subtitle_target_lang: Optional[str] = None
    subtitle_glossary: Optional[str] = None
    subtitle_wrap: Optional[bool] = None
    subtitle_wrap_width: Optional[int] = None
    subtitle_wrap_lines: Optional[int] = None
    subtitle_qc: Optional[bool] = None
    subtitle_qc_reflect: Optional[bool] = None
    subtitle_export_set: Optional[str] = None
    deepl_api_key: Optional[str] = None
    deepl_api_url: Optional[str] = None
    openai_api_key: Optional[str] = None
    openai_base_url: Optional[str] = None
    openai_model: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    anthropic_model: Optional[str] = None
    gemini_api_key: Optional[str] = None
    gemini_model: Optional[str] = None
    google_translate_api_key: Optional[str] = None
    azure_translator_key: Optional[str] = None
    azure_translator_region: Optional[str] = None
    azure_translator_endpoint: Optional[str] = None
    local_ai_mt_after_transcribe: Optional[bool] = None
    subtitle_first: Optional[bool] = None
    ai_polish: Optional[bool] = None
    ai_summarize: Optional[bool] = None
    summary_lang: Optional[str] = None
    translate_auto_fallback: Optional[bool] = None
    demucs_model: Optional[str] = None
    vocal_engine: Optional[str] = None
    roformer_model: Optional[str] = None
    ai_device: Optional[str] = None
    vocal_native_fp16: Optional[bool] = None
    edge_tts_voice: Optional[str] = None
    sub_scan_delay_sec: Optional[int] = None
    acoustid_api_key: Optional[str] = None
    acoustid_min_score: Optional[float] = None
    musicdl_cookies: Optional[str] = None
    musicdl_strategy: Optional[dict] = None
    music_filename_template: Optional[str] = None
    music_embed_metadata: Optional[bool] = None
    music_hide_unavailable: Optional[bool] = None
    music_include_local: Optional[bool] = None
    music_playlist_mode: Optional[str] = None
    music_block_reupload: Optional[bool] = None
    music_include_reference: Optional[bool] = None
    music_quality_spec: Optional[dict] = None
    # 访问保护：只放开这四个可调项，口令哈希 / SECRET_KEY / 机器令牌都走 /api/auth/* 专用接口
    web_auth_enabled: Optional[bool] = None
    web_auth_session_hours: Optional[int] = None
    web_auth_remember_days: Optional[int] = None
    web_auth_max_fails: Optional[int] = None
    web_auth_lock_minutes: Optional[int] = None


class SubAddBody(BaseModel):
    url: str
    title: str = ""
    mode: Optional[str] = None
    kind: Optional[str] = None
    auto_download: Optional[bool] = None


class SubIdBody(BaseModel):
    id: str
    enabled: Optional[bool] = None


class SubRulesBody(BaseModel):
    id: str
    rules: dict = {}
    mode: Optional[str] = None
    auto_download: Optional[bool] = None


class SubBackfillBody(BaseModel):
    id: str
    since: str = ""
    until: str = ""


class SubArchiveClearBody(BaseModel):
    id: str
    entry_id: str = ""


class AnalyzeBody(BaseModel):
    url: str


@app.get("/")
def index():
    html = STATIC / "index.html"
    if html.exists():
        return FileResponse(
            html,
            media_type="text/html",
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
            },
        )
    return HTMLResponse("<h1>缺少 static/index.html</h1>")


def whisper_status() -> dict:
    """检测 faster-whisper / CLI 是否可用。"""
    info = {
        "faster_whisper": False,
        "cli": _find_local_whisper_bin() or "",
        "dir": str(WHISPER_DIR),
        "label": "未安装",
    }
    try:
        import faster_whisper  # type: ignore
        ver = getattr(faster_whisper, "__version__", "ok")
        info["faster_whisper"] = True
        info["faster_whisper_ver"] = str(ver)
        info["label"] = f"faster-whisper {ver}"
    except Exception:
        pass
    if info["cli"] and not info["faster_whisper"]:
        info["label"] = f"CLI: {Path(info['cli']).name}"
    elif info["cli"] and info["faster_whisper"]:
        info["label"] = f"{info['label']} + CLI"
    return info


def update_whisper(log: Callable = print, model: str = "base") -> str:
    """
    安装/更新 faster-whisper 到当前 Python，并预下载模型到 Whisper/models。
    model: tiny / base / small / medium / large-v3
    """
    WHISPER_DIR.mkdir(parents=True, exist_ok=True)
    models_dir = WHISPER_DIR / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    # 可选 HF_TOKEN：提高 HuggingFace 下载限额
    try:
        tok = (
            (cfg.data.get("hf_token") or "").strip()
            or (os.environ.get("HF_TOKEN") or "").strip()
            or (os.environ.get("HUGGING_FACE_HUB_TOKEN") or "").strip()
        )
        if tok:
            os.environ["HF_TOKEN"] = tok
            os.environ["HUGGING_FACE_HUB_TOKEN"] = tok
            log("已使用 HF_TOKEN（提高模型下载限额）")
        else:
            log("未设置 HF_TOKEN，匿名下载模型（可能较慢或触发限流）", "warning")
    except Exception:
        pass
    log("正在 pip 安装/更新 faster-whisper …")
    try:
        idx = str(cfg.data.get("pip_mirror") or "")  # type: ignore[name-defined]
    except Exception:
        idx = ""
    ok, res = pkg_update.pip_install(["faster-whisper"], log=log, mirror=idx, timeout=900)
    if not ok:
        log(f"faster-whisper 安装失败: {res}", "error")
        return f"failed: {res}"
    log("faster-whisper 已安装")

    # 预下载模型（可选，失败不阻断）
    model = (model or "base").strip() or "base"
    try:
        log(f"预下载 Whisper 模型: {model} → {models_dir}")
        from faster_whisper import WhisperModel  # type: ignore
        # 下载到本地 cache
        os.environ.setdefault("HF_HOME", str(models_dir))
        os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(models_dir / "hub"))
        WhisperModel(model, device="cpu", compute_type="int8", download_root=str(models_dir))
        log(f"模型 {model} 已就绪")
    except Exception as e:
        log(f"模型预下载跳过/失败（运行时会再下）: {e}", "warning")

    st = whisper_status()
    return st.get("label") or "ok"


_MEDIA_EXTS = (".mp4", ".mkv", ".webm", ".flv", ".m4a", ".mp3", ".wav", ".aac", ".mov", ".ts", ".avi")


def _collect_batch_targets(paths: List[str], folder: str, mode: str) -> List[Path]:
    found: List[Path] = []
    seen = set()

    def add(p: Path):
        try:
            rp = str(p.resolve())
        except Exception:
            rp = str(p)
        if rp in seen or not p.is_file():
            return
        seen.add(rp)
        found.append(p)

    for raw in paths or []:
        p = Path(str(raw).strip())
        if p.is_file():
            add(p)
    folder = (folder or "").strip()
    if folder:
        root = Path(folder)
        if root.is_dir():
            for p in sorted(root.rglob("*")):
                if not p.is_file():
                    continue
                low = p.suffix.lower()
                if mode in ("transcribe", "both") and low in _MEDIA_EXTS:
                    add(p)
                elif mode in ("translate", "both") and low == ".srt":
                    stem = p.stem.lower()
                    if stem.endswith((".zh", ".en", ".ja", ".ko", ".translated")):
                        continue
                    # both 模式里 srt 仅在「只机翻」时单独处理；both 对媒体会转写后再译
                    if mode == "translate":
                        add(p)
    return found


@app.post("/api/ai/batch")
def api_ai_batch(body: dict):
    """批量：mode=transcribe|translate|both；paths 或 folder。"""
    mode = (body.get("mode") or "transcribe").strip().lower()
    if mode not in ("transcribe", "translate", "both"):
        raise HTTPException(400, "mode 须为 transcribe / translate / both")
    targets = _collect_batch_targets(list(body.get("paths") or []), str(body.get("folder") or ""), mode)
    if not targets:
        raise HTTPException(400, "未找到可处理文件")
    lang = (body.get("lang") or cfg.data.get("local_ai_lang") or "auto").strip()
    provider = (body.get("provider") or cfg.data.get("subtitle_translate_provider") or "deepl").strip()
    target_lang = (body.get("target_lang") or cfg.data.get("subtitle_target_lang") or "zh").strip()
    source_lang = (body.get("source_lang") or cfg.data.get("local_ai_lang") or "").strip()

    def job():
        total = len(targets)
        log_mgr.log(f"批量字幕开始: mode={mode} 共 {total} 个",
                    k="srv.ai.batch_start", kv={"mode": mode, "total": total})
        ok_n, fail_n = 0, 0
        for i, p in enumerate(targets, 1):
            try:
                log_mgr.log(f"批量 [{i}/{total}] {p.name}",
                            k="srv.ai.batch_item", kv={"i": i, "total": total, "name": p.name})
                low = p.suffix.lower()
                if mode in ("transcribe", "both") and low in _MEDIA_EXTS:
                    run_local_ai_on_file(
                        str(p),
                        transcribe=True,
                        translate=False,
                        lang=lang,
                        model=(cfg.data.get("whisper_model") or "base"),
                        device=(cfg.data.get("whisper_device") or "auto"),
                        compute=(cfg.data.get("whisper_compute") or "auto"),
                        log=log_mgr.log,
                    )
                    if mode == "both" and provider and provider != "none":
                        srt = p.with_suffix(".srt")
                        if srt.is_file():
                            translate_srt_file(
                                str(srt),
                                provider=provider,
                                target_lang=target_lang,
                                source_lang=source_lang if source_lang not in ("auto", "") else "",
                                log=log_mgr.log,
                            )
                elif mode == "translate" and low == ".srt" and provider and provider != "none":
                    translate_srt_file(
                        str(p),
                        provider=provider,
                        target_lang=target_lang,
                        source_lang=source_lang if source_lang not in ("auto", "") else "",
                        log=log_mgr.log,
                    )
                ok_n += 1
            except Exception as e:
                fail_n += 1
                log_mgr.log(f"批量失败 {p.name}: {e}", "error",
                            k="srv.ai.batch_item_failed", kv={"name": p.name, "e": str(e)})
        log_mgr.log(f"批量字幕结束: 成功 {ok_n}，失败 {fail_n}，共 {total}",
                    k="srv.ai.batch_done", kv={"ok": ok_n, "fail": fail_n, "total": total})

    threading.Thread(target=job, daemon=True).start()
    return {
        "ok": True,
        "message": f"已开始批量处理 {len(targets)} 个文件（{mode}）",
        "count": len(targets),
        "files": [p.name for p in targets[:40]],
    }


def compute_backoff_delay(
    attempt: int,
    *,
    base: float = 30.0,
    cap: float = 600.0,
    jitter: float = 0.25,
) -> float:
    """
    指数退避 + 全抖动（Full Jitter）：
    delay = min(cap, base * 2^(attempt-1))
    实际等待 = random.uniform(0, delay) * 不全空，保留至少 delay*(1-jitter)～delay
    用于 429/限流，避免雷群效应。
    """
    import random

    attempt = max(1, int(attempt or 1))
    base = max(0.5, float(base or 30))
    cap = max(base, float(cap or 600))
    exp = min(cap, base * (2 ** (attempt - 1)))
    jitter = max(0.0, min(1.0, float(jitter if jitter is not None else 0.25)))
    low = exp * (1.0 - jitter)
    high = exp
    if high <= low:
        return round(exp, 2)
    return round(random.uniform(low, high), 2)


def url_host(url: str) -> str:
    try:
        from urllib.parse import urlparse
        return (urlparse(str(url or "")).hostname or "").lower()
    except Exception:
        return ""


class HostThrottle:
    """按站点记住 429：冷却期内把该域并发压到 1，连续命中则拉长冷却。"""

    def __init__(self):
        self._d: Dict[str, Dict] = {}
        self._lock = threading.Lock()

    def hit(self, url: str, *, cooldown: float = 60.0, wait: float = 0.0,
            max_cooldown: float = 900.0) -> Dict:
        host = url_host(url)
        if not host:
            return {}
        now = time.time()
        cd = max(5.0, float(cooldown or 60))
        if wait:
            cd = max(cd, float(wait))
        with self._lock:
            e = self._d.setdefault(host, {"strikes": 0, "until": 0.0, "cooldown": cd})
            e["strikes"] = int(e.get("strikes") or 0) + 1
            e["cooldown"] = min(max(cd * (1 + 0.5 * (e["strikes"] - 1)), cd), max_cooldown)
            e["until"] = max(float(e.get("until") or 0.0), now + e["cooldown"])
            return {
                "host": host,
                "strikes": e["strikes"],
                "cooldown": round(e["cooldown"], 1),
                "left": round(max(0.0, e["until"] - now), 1),
            }

    def cap_for(self, host: str, base_cap: int) -> int:
        """当前该域允许的并发数；冷却未过则降到 1。"""
        if not host:
            return base_cap
        now = time.time()
        with self._lock:
            e = self._d.get(host)
            if not e:
                return base_cap
            if float(e.get("until") or 0.0) <= now:
                e["strikes"] = int(e.get("strikes") or 1) - 1
                if e["strikes"] <= 0:
                    self._d.pop(host, None)
                return base_cap
            return 1

    def recover(self, url: str):
        host = url_host(url)
        if not host:
            return
        with self._lock:
            e = self._d.get(host)
            if e and float(e.get("until") or 0.0) <= time.time():
                self._d.pop(host, None)

    def snapshot(self) -> List[Dict]:
        now = time.time()
        out = []
        with self._lock:
            for host in list(self._d):
                e = self._d[host]
                left = float(e.get("until") or 0.0) - now
                if left <= 0:
                    self._d.pop(host, None)
                    continue
                out.append({
                    "host": host,
                    "strikes": int(e.get("strikes") or 0),
                    "left": int(round(left)),
                    "cooldown": round(float(e.get("cooldown") or 60), 1),
                })
        out.sort(key=lambda x: -x["left"])
        return out

    def peek(self, url: str) -> Dict:
        """只读地问一句「这个域此刻还在冷却里吗」。

        与 cap_for / snapshot 的区别是一律不改状态：那两个会把过期条目减 strikes 或直接摘掉，
        拿它们做「发请求前的闸门」会让一次询问本身影响后续的降速计算。
        """
        host = url_host(url)
        if not host:
            return {}
        with self._lock:
            e = self._d.get(host)
            if not e:
                return {}
            left = float(e.get("until") or 0.0) - time.time()
            if left <= 0:
                return {}
            return {
                "host": host,
                "strikes": int(e.get("strikes") or 0),
                "cooldown": round(float(e.get("cooldown") or 60), 1),
                "left": round(left, 1),
            }

    def reset(self, host: str = "") -> int:
        host = (host or "").strip().lower()
        with self._lock:
            if host:
                return 1 if self._d.pop(host, None) else 0
            n = len(self._d)
            self._d.clear()
            return n


HOST_THROTTLE = HostThrottle()


def resolve_media_path(path: str) -> Path:
    """相对下载目录或绝对路径 → 已校验的绝对 Path。"""
    p = (path or "").strip()
    if not p:
        raise HTTPException(400, "无效文件路径")
    root = Path(cfg.data.get("download_dir") or DEFAULT_DOWNLOAD_DIR).resolve()
    cand = Path(p)
    if not cand.is_absolute():
        cand = (root / p).resolve()
    else:
        cand = cand.resolve()
    # 允许下载目录内；也允许绝对路径存在的文件（高级用法）
    try:
        if str(cand).startswith(str(root)) and cand.is_file():
            return cand
    except Exception:
        pass
    if cand.is_file():
        return cand
    raise HTTPException(400, f"无效文件路径: {p}")



@app.get("/api/ai/voice_status")
def api_voice_status(refresh: int = 0):
    """语音类依赖的可用性。人声分离这一项要能说出「缺的是哪一层」：
    venv 没建 / runner 不在 / 包 import 不动 / 权重缺 ckpt 还是缺 yaml / 要 GPU 但看不到 CUDA，
    这五种在界面上是五句不同的话，处置也各不相同（前两种是装环境，中间两种是补文件，
    最后一种是换设备或装驱动）。所以这里不打包成一个 bool。
    """
    try:
        from voice_tools import (SEP_RUNNER, EDGE_VOICE_PRESETS, deep_translator_available,
                                 edge_tts_available, roformer_model_states, separation_probe,
                                 separator_setup_running)
        probe = separation_probe(refresh=bool(refresh))
        venv = bool(probe.get("python_present"))
        runner = bool(probe.get("runner_present", SEP_RUNNER.is_file()))
        models = roformer_model_states()
        ready = [m["id"] for m in models if m["present"]]

        def why(engine_ok: bool, pkg_ok: bool) -> str:
            if not venv:
                return "venv"
            if not runner:
                return "runner"
            if not pkg_ok:
                return "import"
            if not ready:
                return "weights"
            return "" if engine_ok else "unknown"

        as_ok = probe.get("audio_separator_import") == "ok"
        dm_ok = probe.get("demucs_import") == "ok"
        return {
            "edge_tts": edge_tts_available(),
            "deep_translator": deep_translator_available(),
            "voices": EDGE_VOICE_PRESETS,
            "auto_fallback": bool(cfg.data.get("translate_auto_fallback", True)),
            "separation": {
                "venv": venv,
                "runner": runner,
                "torch": probe.get("torch", ""),
                "audio_separator_version": probe.get("audio_separator_version", ""),
                "demucs_version": probe.get("demucs_version", ""),
                "audio_separator_ok": as_ok,
                "demucs_ok": dm_ok,
                "cuda_available": bool(probe.get("cuda_available")),
                "gpu_name": probe.get("gpu_name", ""),
                "vram_gib": probe.get("vram_gib"),
                "probe_error": probe.get("probe_error", "") or probe.get("torch_error", ""),
                "models": models,
                "ready_models": ready,
                "default_model": ready[0] if ready else "",
                "engines": [
                    {"id": "roformer", "available": venv and runner and as_ok and bool(ready),
                     "reason": why(as_ok and bool(ready), as_ok)},
                    {"id": "demucs", "available": venv and dm_ok,
                     "reason": "" if (venv and dm_ok) else ("import" if venv else "venv")},
                ],
                "device": str(cfg.data.get("ai_device") or "auto"),
                "setup_running": separator_setup_running(),
            },
        }
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/subtitle/glossary_check")
def api_glossary_check(body: dict):
    """术语表格式体检：返回生效条数与无法识别的行，供设置页即时提示。"""
    raw = (body or {}).get("text")
    if raw is None:
        raw = cfg.data.get("subtitle_glossary") or ""
    pairs = parse_glossary(raw)
    bad: List[str] = []
    for line in (raw or "").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or s.startswith("//"):
            continue
        parts = GLOSSARY_SEP_RE.split(s, maxsplit=1)
        if len(parts) != 2 or not parts[0].strip() or not parts[1].strip():
            bad.append(s[:60])
    return {"ok": True, "count": len(pairs), "terms": pairs[:200], "bad": bad[:20]}


QC_ROWS_CAP = 200


def _qc_budget(body: dict) -> Tuple[float, int]:
    """每行字数 / 最多行数：请求体优先，越界就按能用的极限收住。"""
    width = float(body.get("width") or cfg.data.get("subtitle_wrap_width") or 16)
    width = max(8.0, min(40.0, width))
    lines = int(body.get("lines") or cfg.data.get("subtitle_wrap_lines") or 3)
    lines = max(1, min(4, lines))
    return width, lines


@app.post("/api/subtitle/qc")
def api_subtitle_qc(body: dict):
    """字幕质检：把这份字幕逐句对照它的另一路（原文 ↔ 译文），列出可疑行给校对台跳转。

    手上这份始终按「译文」处理，行号就是这份文件的句序；另一路只当原文用。
    """
    body = body or {}
    srt, _media = _subtitle_for_edit(body.get("path") or "")
    other = None
    if (body.get("with") or "").strip():
        try:
            other = resolve_media_path(body["with"].strip())
        except HTTPException:
            other = None
    else:
        other = find_subtitle_counterpart(srt)
    if other is not None and (not other.is_file() or other.suffix.lower() not in SUB_EDIT_EXTS):
        other = None

    target = str(cfg.data.get("subtitle_target_lang") or "zh").strip()
    width, max_lines = _qc_budget(body)
    dst = _edit_cues(srt)
    if not dst:
        raise HTTPException(400, f"{srt.name} 里没有解析出有效字幕，没法质检")

    src_texts: List[str] = [""] * len(dst)
    hint = ""
    if other is not None:
        src = _edit_cues(other)
        if not src:
            hint = f"另一路 {other.name} 没解析出有效字幕，本次只查不依赖对照的问题"
        else:
            src_texts = [c["text"] for c in src][: len(dst)]
            if len(src) < len(dst):
                hint = (f"两路句数不一致（{srt.name} {len(dst)} 句 / {other.name} {len(src)} 句），"
                        f"后 {len(dst) - len(src)} 句没有原文可对照")
            if _lang_suffix_of(other).lower().startswith(target.lower()[:2]) and not _lang_suffix_of(srt).lower().startswith(target.lower()[:2]):
                hint = (hint + " " if hint else "") + (
                    f"另一路的文件名带 {target} 后缀，可疑行号是按 {srt.name} 报的；"
                    "要是这份其实是原文，请改开译文那一份再查")
    else:
        hint = "找不到另一路原文，只查空句、换行超限、复读和样式标签丢失这几类不依赖对照的问题"

    glossary = parse_glossary()
    rows = qc_cue_pairs(
        src_texts, [c["text"] for c in dst], target_lang=target,
        glossary=glossary, max_units=width, max_lines=max_lines,
    )
    # 时间轴那三维不吃「另一路」，所以对照缺失时它照样算得出来
    media_secs, media_path, why_no_media = _qc_media_seconds(srt, _media)
    tl = qc_timeline(dst, media_seconds=media_secs, target_lang=target, why_no_media=why_no_media)
    out_rows = []
    for r in rows[:QC_ROWS_CAP]:
        c = dst[r["i"] - 1]
        out_rows.append({
            "i": r["i"],
            "start": c["start"],
            "end": c["end"],
            "speaker": c.get("speaker") or "",
            "src": (src_texts[r["i"] - 1] if r["i"] - 1 < len(src_texts) else "")[:300],
            "dst": (c["text"] or "")[:300],
            "kinds": r["kinds"],
            "why": r["why"],
            "labels": [QC_KIND_LABELS.get(k, k) for k in r["kinds"]],
        })
    return {
        "ok": True,
        "srt": _ui_path(srt),
        "counter": _ui_path(other) if other else "",
        "paired": bool(other),
        "total": len(dst),
        "lang": target,
        "wrap": {"width": width, "lines": max_lines},
        "reflect_on": bool(cfg.data.get("subtitle_qc_reflect", False)),
        "stats": qc_stats(rows),
        "stats_text": qc_stats_text(rows),
        "rows": out_rows,
        "truncated": len(rows) > QC_ROWS_CAP,
        "hint": hint,
        "media": _ui_path(media_path) if media_path else "",
        "media_seconds": media_secs,
        "timeline": tl,
        "timeline_text": qc_timeline_text(tl),
        "message": (f"{len(rows)} 句可疑（{qc_stats_text(rows)}）" if rows
                    else f"{len(dst)} 句都过了，没发现可疑行"),
    }


@app.post("/api/subtitle/rewrap")
def api_subtitle_rewrap(body: dict):
    """按每行字数重排一份字幕：只动换行不改文字，写回前先按校对台的规矩留一份备份。"""
    body = body or {}
    srt, _media = _subtitle_for_edit(body.get("path") or "")
    width, max_lines = _qc_budget(body)
    raw = srt.read_text(encoding="utf-8", errors="ignore")
    is_vtt = srt.suffix.lower() == ".vtt"
    cues = parse_srt(_vtt_to_srt_text(raw) if is_vtt else raw)
    cues = [c for c in cues if (c.get("text") or "").strip()]
    if not cues:
        raise HTTPException(400, f"{srt.name} 里没有解析出有效字幕，未改动")
    wrapped = wrap_cues(cues, width, max_lines)
    changed = sum(1 for a, b in zip(cues, wrapped) if (a.get("text") or "") != (b.get("text") or ""))
    over = sum(1 for c in wrapped if max((text_units(ln) for ln in (c.get("text") or "").split("\n")), default=0.0) > width * 1.25)
    info = f"每行 ≤{width:g} 个全角宽、最多 {max_lines} 行"
    if not changed:
        return {"ok": True, "changed": 0, "total": len(cues), "width": width, "lines": max_lines,
                "over": over, "message": f"已经符合{info}，没有改动"}
    backup = _edit_backup_path(srt)
    shutil.copy2(srt, backup)
    srt.write_text(write_vtt(wrapped) if is_vtt else write_srt(wrapped), encoding="utf-8")
    log_mgr.log(f"字幕重排: {srt.name} 改了 {changed} 句（{info}），原文件备份为 {backup.name}")
    tail = f"，其中 {over} 句没有合适的断点、仍然超行" if over else ""
    return {
        "ok": True, "changed": changed, "total": len(cues), "width": width, "lines": max_lines,
        "over": over, "backup": _ui_path(backup), "srt": _ui_path(srt),
        "message": f"按{info}重排了 {changed} 句{tail}，原文件备份为 {backup.name}",
    }


@app.post("/api/ai/analyze")
def api_ai_analyze(body: dict):
    """Librosa 音频分析摘要 → 日志 + .analysis.json"""
    import importlib.util

    media = resolve_media_path(body.get("path") or "")
    write_json = body.get("write_json")
    if write_json is None:
        write_json = True
    try:
        max_duration = float(body.get("max_duration") or 180)
    except Exception:
        max_duration = 180.0

    # 依赖缺失要在这里当场回错：起了线程就只能把失败埋进日志，界面上看着像成功了
    if importlib.util.find_spec("librosa") is None:
        msg = ("缺少 librosa，音频分析未启动：请在「设置 → 组件与依赖」的 Python 依赖里"
               "安装 librosa（会连带装 numba / llvmlite），或在本机执行 pip install librosa 后重试")
        log_mgr.log(msg, "warning")
        return {"ok": False, "message": msg}

    # 读不懂 / 没有声轨同理：只探一次 ffmpeg 头部，不必等后台线程跑完才发现
    try:
        from audio_analyze import preflight
        err = preflight(str(media))
    except Exception as e:
        err = f"探测音轨失败: {e}"
    if err:
        log_mgr.log(f"音频分析未启动（{media.name}）：{err}", "warning")
        return {"ok": False, "message": err}

    def job():
        try:
            from audio_analyze import analyze_audio
            r = analyze_audio(
                str(media),
                write_json=bool(write_json),
                max_duration=max_duration,
                log=log_mgr.log,
            )
            if not r.get("ok"):
                log_mgr.log(r.get("message") or "分析失败", "warning")
        except Exception as e:
            log_mgr.log(f"音频分析失败: {e}", "error",
                        k="srv.ai.analyze_failed", kv={"e": str(e)})

    threading.Thread(target=job, daemon=True).start()
    return {"ok": True, "message": f"正在分析: {media.name}（结果写运行日志{'与 JSON' if write_json else ''}）"}


@app.post("/api/ai/vocal_separate")
def api_ai_vocal_separate(body: dict):
    """人声/伴奏分离。引擎、权重、设备都取自设置，body 可以逐项覆盖。

    这一句里的 path 相对下载目录或绝对路径；设备只有三档（auto/cpu/cuda），
    传别的按 auto 处理 —— 宁可退回自动，也不要拿一个没听过的字符串去拼命令行参数。
    """
    media = resolve_media_path(body.get("path") or "")
    engine = (body.get("engine") or cfg.data.get("vocal_engine") or "roformer").strip().lower()
    if engine not in ("roformer", "demucs"):
        engine = "roformer"
    device = (body.get("device") or cfg.data.get("ai_device") or "auto").strip().lower()
    if device not in ("auto", "cpu", "cuda"):
        device = "auto"
    model_id = (body.get("model") or cfg.data.get("roformer_model") or "").strip()
    demucs_model = (body.get("demucs_model") or cfg.data.get("demucs_model") or "htdemucs").strip()
    out_dir = str(media.parent / ("separated" if engine == "roformer" else "demucs"))

    from voice_tools import SEP_RUNNER, separator_python
    if not separator_python() or not SEP_RUNNER.is_file():
        # 这一层缺了不用等三十秒：命令行了无音讯地失败，界面上只有一行日志，
        # 人会以为「分离慢」，其实引擎根本不在。
        return {"ok": False, "error": "分离引擎的独立环境还没建（tools/separator/venv 里没有 python）"}

    def job():
        try:
            from voice_tools import separate_demucs, separate_roformer
            if engine == "demucs":
                fact = separate_demucs(str(media), model=demucs_model, device=device,
                                       out_dir=out_dir, log=log_mgr.log)
            else:
                fact = separate_roformer(str(media), model_id=model_id, device=device,
                                         out_dir=out_dir,
                                         native_fp16=bool(cfg.data.get("vocal_native_fp16", False)),
                                         log=log_mgr.log)
            got = str(fact.get("actual_device") or "")
            outs = fact.get("outputs") or []
            if device == "cuda" and not got.startswith("cuda"):
                # 「选了 GPU、实际在 CPU 上跑」必须自己说破，不然设置里那格就成了谎话
                log_mgr.log(f"分离完成，但没跑在 GPU 上（实际用的是 {got or '未知'}）", "warning")
            for p in outs:
                log_mgr.log(f"分离成品: {p}", k="srv.ai.separate_file", kv={"file": p})
            if not outs:
                log_mgr.log("分离结束但一个成品都没有，按失败记", "error",
                            k="srv.ai.separate_empty")
        except Exception as e:
            log_mgr.log(f"人声分离失败: {e}", "error",
                        k="srv.ai.separate_failed", kv={"e": str(e)})

    threading.Thread(target=job, daemon=True).start()
    return {"ok": True, "message": f"人声分离中: {media.name}（{engine} / {device}）"}


@app.post("/api/ai/tts")
def api_ai_tts(body: dict):
    """Edge-TTS：SRT 或纯文本 → mp3。"""
    path = (body.get("path") or "").strip()
    text = (body.get("text") or "").strip()
    voice = (body.get("voice") or cfg.data.get("edge_tts_voice") or "").strip()
    lang = (body.get("lang") or cfg.data.get("subtitle_target_lang") or "zh").strip()

    def job():
        try:
            from voice_tools import edge_tts_from_srt, edge_tts_from_text
            if path:
                media = resolve_media_path(path)
                if media.suffix.lower() == ".srt":
                    edge_tts_from_srt(str(media), voice=voice, lang=lang, log=log_mgr.log)
                else:
                    # 同名 srt
                    srt = media.with_suffix(".srt")
                    if srt.is_file():
                        edge_tts_from_srt(str(srt), voice=voice, lang=lang, log=log_mgr.log)
                    else:
                        raise FileNotFoundError("请提供 .srt 或同名字幕")
            elif text:
                out = Path(cfg.data.get("download_dir") or DEFAULT_DOWNLOAD_DIR) / "tts_out.mp3"
                edge_tts_from_text(text, str(out), voice=voice, lang=lang, log=log_mgr.log)
            else:
                raise ValueError("需要 path 或 text")
        except Exception as e:
            log_mgr.log(f"Edge-TTS 失败: {e}", "error",
                        k="srv.ai.tts_failed", kv={"e": str(e)})

    threading.Thread(target=job, daemon=True).start()
    return {"ok": True, "message": "Edge-TTS 合成中"}


@app.post("/api/ai/install_voice")
def api_ai_install_voice(body: dict = None):
    body = body or {}
    which = (body.get("pkg") or "all").strip().lower()

    def job():
        from voice_tools import install_demucs, install_edge_tts, install_deep_translator
        idx = str(cfg.data.get("pip_mirror") or "")
        if which in ("all", "demucs"):
            install_demucs(log_mgr.log, mirror=idx)
        if which in ("all", "edge-tts", "edge_tts", "tts"):
            install_edge_tts(log_mgr.log, mirror=idx)
        if which in ("all", "deep-translator", "deep_translator", "dt"):
            install_deep_translator(log_mgr.log, mirror=idx)

    threading.Thread(target=job, daemon=True).start()
    return {"ok": True, "message": f"后台安装: {which}"}


@app.post("/api/ai/separator_setup")
def api_separator_setup(body: dict = None):
    """建分离用的独立环境 / 补 RoFormer 权重。

    便携包不带这两层（口径定的），所以缺的时候要在程序里点得齐：
    只把「缺 venv」这句话打在界面上，等于把功能做给了搭过环境的那台机器。
    两个动作都是分钟级、且要下两个多 GB，所以走后台任务 + 运行日志，不同步等。
    """
    step = ((body or {}).get("step") or "all").strip().lower()
    if step not in ("venv", "weights", "all", "engines"):
        raise HTTPException(400, f"step 只认 venv / weights / all / engines，收到的是「{step[:16]}」")

    def job():
        from voice_tools import setup_separator
        r = setup_separator(log_mgr.log, step=step, mirror=str(cfg.data.get("pip_mirror") or ""))
        if r == "busy":
            log_mgr.log("已经有一个搭建任务在跑了，这一次先不叠加", "warning",
                        k="srv.ai.setup_busy")
        elif r == "ok":
            if step == "engines":
                log_mgr.log("分离引擎已更新", k="srv.ai.update_ready")
            else:
                log_mgr.log("分离环境就绪", k="srv.ai.setup_ready")
        elif step == "engines":
            log_mgr.log(f"分离引擎更新未完成: {r}", "error",
                        k="srv.ai.update_failed", kv={"r": r})
        else:
            log_mgr.log(f"分离环境搭建未完成: {r}", "error",
                        k="srv.ai.setup_failed", kv={"r": r})

    threading.Thread(target=job, daemon=True).start()
    return {"ok": True,
            "message": "分离引擎更新中，进度看运行日志" if step == "engines"
                       else "分离环境搭建中，进度看运行日志"}


@app.post("/api/ai/realtime")
async def api_ai_realtime(file: UploadFile = File(...), lang: str = "auto", translate: bool = False, target_lang: str = "zh"):
    """
    实时/准实时：上传短音频块 → 转写（可选机翻）。
    浏览器可用 MediaRecorder 周期性 POST。
    """
    if file is None:
        raise HTTPException(400, "需要音频文件")
    import tempfile
    suffix = Path(file.filename or "chunk.webm").suffix or ".webm"
    raw = await file.read()
    if len(raw) < 100:
        raise HTTPException(400, "音频过短")
    tmp = Path(tempfile.gettempdir()) / f"md_rt_{uuid.uuid4().hex}{suffix}"
    tmp.write_bytes(raw)
    try:
        # 转写
        text = ""
        srt_path = ""
        try:
            from faster_whisper import WhisperModel
            model_name = cfg.data.get("whisper_model") or "base"
            device = cfg.data.get("whisper_device") or "cpu"
            if device == "auto":
                device = "cpu"
            compute = cfg.data.get("whisper_compute") or "int8"
            if compute == "auto":
                compute = "int8"
            wm = WhisperModel(model_name, device=device, compute_type=compute)
            segments, info = wm.transcribe(str(tmp), language=None if lang in ("", "auto") else lang)
            parts = []
            for seg in segments:
                parts.append(seg.text.strip())
            text = " ".join(parts).strip()
            detected = getattr(info, "language", lang)
        except Exception as e:
            log_mgr.log(f"实时转写失败: {e}", "error",
                        k="srv.ai.realtime_asr_failed", kv={"e": str(e)})
            raise HTTPException(500, f"转写失败: {e}")

        translated = ""
        if translate and text:
            try:
                cues = [{"idx": 1, "start": 0, "end": 1, "text": text}]
                # 复用单条机翻
                from voice_tools import translate_batch_deep_translator
                try:
                    translated = translate_batch_deep_translator([text], target_lang, "auto", log_mgr.log)[0]
                except Exception:
                    # 走完整 fallback
                    out = translate_srt_file  # type: ignore
                    # 写临时 srt
                    ts = tmp.with_suffix(".srt")
                    ts.write_text(f"1\n00:00:00,000 --> 00:00:05,000\n{text}\n", encoding="utf-8")
                    result = translate_srt_file(str(ts), provider=cfg.data.get("subtitle_translate_provider") or "deep_translator",
                                                target_lang=target_lang, log=log_mgr.log)
                    translated = Path(result).read_text(encoding="utf-8", errors="ignore")
            except Exception as e:
                log_mgr.log(f"实时翻译失败: {e}", "warning",
                            k="srv.ai.realtime_translate_failed", kv={"e": str(e)})

        return {
            "ok": True,
            "text": text,
            "translated": translated,
            "lang": detected if "detected" in dir() else lang,
        }
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass


@app.post("/api/ai/transcribe")
def api_ai_transcribe(body: dict):
    """对已下载媒体仅转写 → .srt（path 可为相对下载目录）"""
    media = resolve_media_path(body.get("path") or "")
    path = str(media)
    lang = (body.get("lang") or cfg.data.get("local_ai_lang") or "auto").strip()
    low = path.lower()
    if not any(low.endswith(ext) for ext in (".mp4", ".mkv", ".webm", ".flv", ".m4a", ".mp3", ".wav", ".aac", ".mov", ".ts")):
        raise HTTPException(400, "请选择音视频文件")

    def job():
        try:
            run_local_ai_on_file(
                path,
                transcribe=True,
                translate=False,
                lang=lang,
                model=(cfg.data.get("whisper_model") or "base"),
                device=(cfg.data.get("whisper_device") or "auto"),
                compute=(cfg.data.get("whisper_compute") or "auto"),
                log=log_mgr.log,
            )
        except Exception as e:
            log_mgr.log(f"仅转写失败: {e}", "error",
                        k="srv.ai.transcribe_only_failed", kv={"e": str(e)})

    threading.Thread(target=job, daemon=True).start()
    return {"ok": True, "message": f"已开始转写（语言={lang}）→ {media.name}"}



PIPELINE_CN = {
    "subtitle": "转写字幕",
    "polish": "LLM 润色",
    "summary": "内容摘要",
    "translate": "字幕机翻",
}


def _ui_path(p: Path) -> str:
    root = Path(cfg.data.get("download_dir") or DEFAULT_DOWNLOAD_DIR).resolve()
    try:
        return str(p.relative_to(root)).replace("\\", "/")
    except Exception:
        return str(p).replace("\\", "/")


@app.get("/api/ai/pipeline_status")
def api_ai_pipeline_status(path: str = ""):
    """查询某个媒体文件的 AI 流水线阶段产物落盘情况。"""
    from ai_pipeline import PIPELINE_STAGES, load_manifest, pipeline_manifest_path

    if not (path or "").strip():
        raise HTTPException(400, "缺少 path")
    media = resolve_media_path(path)
    mf = pipeline_manifest_path(media)
    data = load_manifest(media)
    stages = []
    for name in PIPELINE_STAGES:
        e = (data.get("stages") or {}).get(name) or {}
        out = e.get("out") or ""
        p = Path(out) if out else None
        exists = bool(p and p.is_file())
        stages.append({
            "name": name,
            "label": PIPELINE_CN.get(name, name),
            "status": e.get("status") or "pending",
            "note": e.get("note") or "",
            "at": e.get("at") or "",
            "out": _ui_path(p) if exists else "",
            "out_name": p.name if exists else (Path(out).name if out else ""),
            "size": p.stat().st_size if exists else 0,
        })
    return {
        "ok": True,
        "media": _ui_path(media),
        "has_manifest": mf.is_file(),
        "updated": data.get("updated") or "",
        "stages": stages,
    }


SPEAKER_PREFIX_RE = re.compile(r"^\s*[（(\[]?(说话人|Speaker)\s*(\d+)[）)\]]?\s*[:：]?\s*")


@app.get("/api/ai/transcript")
def api_ai_transcript(path: str = ""):
    """把某个媒体已落盘的字幕解析成逐行可点数据：[{start,end,speaker,text}]。

    说话人分离的结果只以 `[说话人N] ` 前缀写在 SRT 正文里（这样内嵌字幕、导出、
    硬字幕烧录都不用改），这里再把它剥出来单独成字段，前端才能分色显示。
    """
    from ai_pipeline import find_pipeline_srt

    if not (path or "").strip():
        raise HTTPException(400, "缺少 path")
    media = resolve_media_path(path)
    srt = find_pipeline_srt(media)
    if srt is None:
        return {"ok": False, "cues": [], "message": "这份文件还没有字幕，先跑一次转写或字幕流水线"}
    try:
        raw = srt.read_text(encoding="utf-8", errors="ignore")
    except OSError as e:
        raise HTTPException(500, f"读取字幕失败: {e}")
    cues = []
    for c in parse_srt(raw):
        timing = c.get("timing") or ""
        a, _, b = timing.partition("-->")
        text = c.get("text") or ""
        m = SPEAKER_PREFIX_RE.match(text)
        speaker = ""
        if m:
            speaker = m.group(2)
            text = text[m.end():]
        cues.append({
            "idx": c.get("idx"),
            "start": round(_srt_ts_to_ms(a) / 1000.0, 3),
            "end": round(_srt_ts_to_ms(b) / 1000.0, 3),
            "speaker": speaker,
            "text": text.strip(),
        })
    return {
        "ok": True,
        "media": _ui_path(media),
        "srt": _ui_path(srt),
        "cues": cues,
        "message": "" if cues else "字幕文件是空的",
    }


@app.post("/api/ai/pipeline")
def api_ai_pipeline(body: dict):
    """
    字幕优先流水线：已有字幕 → yt-dlp 平台字幕 → Whisper → 可选润色/摘要/机翻。
    body: path, polish, summarize, translate, lang, summary_lang, target_lang, subtitle_first, only
    only 取 subtitle|polish|summary|translate 时只重跑该阶段，输入用上次落盘产物。
    """
    media = resolve_media_path(body.get("path") or "")
    path = str(media)
    from ai_pipeline import PIPELINE_STAGES
    only = str(body.get("only") or "").strip().lower()
    lang = (body.get("lang") or cfg.data.get("local_ai_lang") or "auto").strip()
    summary_lang = (body.get("summary_lang") or cfg.data.get("summary_lang") or "zh").strip()
    target_lang = (body.get("target_lang") or cfg.data.get("subtitle_target_lang") or "zh").strip()
    subtitle_first = body.get("subtitle_first")
    if subtitle_first is None:
        subtitle_first = bool(cfg.data.get("subtitle_first", True))
    polish = body.get("polish")
    if polish is None:
        polish = bool(cfg.data.get("ai_polish", False))
    summarize = body.get("summarize")
    if summarize is None:
        summarize = bool(cfg.data.get("ai_summarize", False))
    translate = body.get("translate")
    if translate is None:
        translate = bool(cfg.data.get("local_ai_mt_after_transcribe", False))
    if only and only not in PIPELINE_STAGES:
        raise HTTPException(400, f"only 只支持 {'/'.join(PIPELINE_STAGES)}")

    def job():
        try:
            from ai_pipeline import run_pipeline

            def whisper_fn(mp, lang="auto"):
                files = run_local_ai_on_file(
                    mp,
                    transcribe=True,
                    translate=False,
                    lang=lang,
                    model=(cfg.data.get("whisper_model") or "base"),
                    device=(cfg.data.get("whisper_device") or "auto"),
                    compute=(cfg.data.get("whisper_compute") or "auto"),
                    log=log_mgr.log,
                )
                return files

            def translate_fn(srt, tgt):
                return translate_srt_file(
                    srt,
                    provider=(cfg.data.get("subtitle_translate_provider") or "deepl"),
                    target_lang=tgt,
                    log=log_mgr.log,
                )

            # OpenAI 兼容密钥：优先 openai，其次 openrouter 风格共用字段
            key = (cfg.data.get("openai_api_key") or cfg.data.get("openrouter_api_key") or "").strip()
            base = (cfg.data.get("openai_base_url") or "https://api.openai.com/v1").strip()
            model = (cfg.data.get("openai_model") or cfg.data.get("subtitle_openai_model") or "gpt-4o-mini").strip()

            r = run_pipeline(
                path,
                subtitle_first=bool(subtitle_first),
                use_whisper=True,
                polish=bool(polish) and bool(key),
                summarize=bool(summarize) and bool(key),
                translate_after=bool(translate),
                lang=lang,
                summary_lang=summary_lang,
                target_lang=target_lang,
                whisper_fn=whisper_fn,
                translate_fn=translate_fn,
                openai_key=key,
                openai_base=base,
                openai_model=model,
                only=only,
                log=log_mgr.log,
            )
            badge = {"subtitle": "⚡平台字幕", "existing": "📄已有字幕", "whisper": "🎙Whisper", "cached": "♻上一步产物"}.get(
                r.get("path_type") or "", r.get("path_type")
            )
            log_mgr.log(f"流水线完成{'' if not only else f'[{PIPELINE_CN.get(only, only)}]'} [{badge}] {r.get('message')}")
            if r.get("summary"):
                log_mgr.log(f"摘要文件: {r['summary']}",
                            k="srv.ai.pipeline_summary", kv={"file": r["summary"]})
            if r.get("polished"):
                log_mgr.log(f"润色文件: {r['polished']}",
                            k="srv.ai.pipeline_polished", kv={"file": r["polished"]})
        except Exception as e:
            log_mgr.log(f"流水线失败: {e}", "error",
                        k="srv.ai.pipeline_failed", kv={"e": str(e)})

    threading.Thread(target=job, daemon=True).start()
    return {
        "ok": True,
        "message": (
            f"已启动单步重跑[{PIPELINE_CN.get(only, only)}]: {media.name}"
            if only
            else f"流水线已启动: {media.name}（字幕优先={subtitle_first} 润色={polish} 摘要={summarize}）"
        ),
    }


@app.post("/api/ai/srt_calibrate")
def api_ai_srt_calibrate(body: dict):
    """
    字幕时间轴校准。
    path: srt 路径
    offset_ms / offset_sec: 平移（可同时给，会相加）
    scale: 缩放因子，默认 1.0
    inplace: true 则覆盖原文件
    """
    path = str(resolve_media_path(body.get("path") or ""))
    if not path.lower().endswith(".srt"):
        raise HTTPException(400, "仅支持 .srt")
    try:
        offset_ms = int(body.get("offset_ms") or 0)
    except Exception:
        offset_ms = 0
    try:
        offset_sec = float(body.get("offset_sec") or 0)
    except Exception:
        offset_sec = 0.0
    try:
        scale = float(body.get("scale") if body.get("scale") is not None else 1.0)
    except Exception:
        scale = 1.0
    inplace = bool(body.get("inplace"))
    try:
        out = calibrate_srt_file(
            path,
            offset_ms=offset_ms,
            offset_sec=offset_sec,
            scale=scale,
            inplace=inplace,
            log=log_mgr.log,
        )
        return {"ok": True, "path": out, "message": f"已校准 → {Path(out).name}"}
    except Exception as e:
        raise HTTPException(400, str(e))


SUB_EDIT_EXTS = (".srt", ".vtt")


def _subtitle_for_edit(path: str) -> Tuple[Path, str]:
    """校对台入口路径：给字幕文件直接用它，给媒体文件找回它那份字幕。回 (字幕文件, 媒体路径)。"""
    p = resolve_media_path(path)
    if p.suffix.lower() in SUB_EDIT_EXTS:
        return p, ""
    from ai_pipeline import find_pipeline_srt

    srt = find_pipeline_srt(p)
    if srt is None:
        raise HTTPException(400, f"{p.name} 还没有字幕文件，先跑一次转写或字幕流水线")
    if srt.suffix.lower() not in SUB_EDIT_EXTS:
        raise HTTPException(400, f"逐句校对只支持 .srt / .vtt，这份是 {srt.name}")
    return srt, str(p)


def _edit_cues(srt: Path) -> List[dict]:
    """字幕文件 → 逐行可编辑数据。说话人标记在文件里是正文前缀，这里剥成 speaker 字段供界面分色。"""
    try:
        raw = srt.read_text(encoding="utf-8", errors="ignore")
    except OSError as e:
        raise HTTPException(500, f"读取字幕失败: {e}")
    if srt.suffix.lower() == ".vtt":
        raw = _vtt_to_srt_text(raw)
    cues: List[dict] = []
    for c in parse_srt(raw):
        left, _, right = (c.get("timing") or "").partition("-->")
        text = c.get("text") or ""
        speaker = ""
        m = SPEAKER_PREFIX_RE.match(text)
        if m:
            speaker = m.group(2)
            text = text[m.end():]
        cues.append({
            "idx": len(cues) + 1,
            "start": round(_srt_ts_to_ms(left) / 1000.0, 3),
            "end": round(_srt_ts_to_ms(right) / 1000.0, 3),
            "speaker": speaker,
            "text": text.strip(),
        })
    return cues


def _edit_backup_path(p: Path) -> Path:
    """同目录备份名 = 原文件名 + .bak-<时间>；同一秒内连续保存时往后加序号，不覆盖上一份备份。"""
    base = p.name + ".bak-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    cand = p.with_name(base)
    i = 1
    while cand.exists():
        cand = p.with_name(f"{base}.{i}")
        i += 1
    return cand


@app.get("/api/ai/srt")
def api_ai_srt_read(path: str = ""):
    """逐句校对台：把一份字幕读成可编辑的行（每句起止秒、说话人、正文）。"""
    if not (path or "").strip():
        raise HTTPException(400, "缺少 path")
    srt, media = _subtitle_for_edit(path)
    cues = _edit_cues(srt)
    st = srt.stat()
    return {
        "ok": True,
        "srt": _ui_path(srt),
        "media": _ui_path(Path(media)) if media else "",
        "format": srt.suffix.lower().lstrip("."),
        "cues": cues,
        "mtime_ts": st.st_mtime,
        "mtime": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
        "message": "" if cues else "这份字幕里没有解析出有效句子",
    }


@app.post("/api/ai/srt/save")
def api_ai_srt_save(body: dict):
    """逐句校对台写回：整表覆盖，覆盖前先把原文件备份成 <原文件名>.bak-<时间>。

    body: path 字幕或媒体文件；cues 编辑后的整表（顺序即句序）；
          base_mtime 读入时拿到的 mtime_ts，用来挡「读完之后文件又被改写」这一类覆盖。
    """
    body = body or {}
    srt, _media = _subtitle_for_edit(body.get("path") or "")
    rows = body.get("cues")
    if not isinstance(rows, list) or not rows:
        raise HTTPException(400, "没有要写入的字幕行，原文件未改动")
    if len(rows) > 20000:
        raise HTTPException(400, f"这次送来 {len(rows)} 行，超出单份字幕上限，已拒绝写入")
    bm = body.get("base_mtime")
    if bm not in (None, ""):
        try:
            cur = srt.stat().st_mtime
            if abs(float(bm) - cur) > 0.01:
                raise HTTPException(
                    409,
                    f"这份字幕在你打开之后又被改写过（{srt.name}，改写于 "
                    f"{datetime.fromtimestamp(cur).strftime('%Y-%m-%d %H:%M:%S')}），本次没有写入。"
                    "请重新载入后再校对，以免覆盖掉刚生成的内容。",
                )
        except ValueError:
            pass

    cues: List[dict] = []
    dropped = 0
    for r in rows:
        if not isinstance(r, dict):
            raise HTTPException(400, f"第 {len(cues) + 1} 行不是字幕行，已拒绝写入")
        try:
            t0 = int(round(float(r.get("start") or 0) * 1000))
            t1 = int(round(float(r.get("end") or 0) * 1000))
        except (TypeError, ValueError):
            raise HTTPException(
                400, f"第 {len(cues) + 1} 句的时间不是数字（起={r.get('start')!r} 止={r.get('end')!r}），已拒绝写入"
            )
        text = str(r.get("text") or "").strip()
        sp = str(r.get("speaker") or "").strip()
        if sp:
            text = f"[说话人{sp}] {text}".strip()
        if not text:
            dropped += 1
            continue
        t0 = max(0, t0)
        if t1 <= t0:
            t1 = t0 + 40  # 与时间轴校准同一口径：一句至少留 40ms
        cues.append({"timing": f"{_ms_to_srt_ts(t0)} --> {_ms_to_srt_ts(t1)}", "text": text})
    if not cues:
        raise HTTPException(400, "每一句的正文都是空的，本次没有写入，原文件未改动")

    bak = _edit_backup_path(srt)
    try:
        shutil.copy2(srt, bak)
        txt = write_vtt(cues) if srt.suffix.lower() == ".vtt" else write_srt(cues)
        srt.write_text(txt, encoding="utf-8")
    except OSError as e:
        raise HTTPException(500, f"写入字幕失败: {e}（备份名 {bak.name}，原文件可能未改动）")

    log_mgr.log(
        f"逐句校对字幕：{srt.name} 写入 {len(cues)} 句"
        + (f"，其中 {dropped} 行正文为空已跳过" if dropped else "")
        + f"，原文件备份为 {bak.name}"
    )
    return {
        "ok": True,
        "srt": _ui_path(srt),
        "backup": _ui_path(bak),
        "count": len(cues),
        "dropped": dropped,
        "mtime_ts": srt.stat().st_mtime,
        "message": f"已写入 {len(cues)} 句" + (f"，跳过 {dropped} 行空正文" if dropped else ""),
    }


@app.post("/api/ai/translate_srt")
def api_ai_translate_srt(body: dict):
    """机翻已有 SRT（DeepL / OpenAI）。也可对视频：先找同名 .srt。"""
    try:
        p = resolve_media_path(body.get("path") or "")
    except HTTPException:
        raise
    if p.suffix.lower() != ".srt":
        cand = p.with_suffix(".srt")
        if cand.is_file():
            p = cand
        else:
            raise HTTPException(400, "请先转写生成 .srt，或直接选择 .srt 文件")
    provider = (body.get("provider") or cfg.data.get("subtitle_translate_provider") or "deepl").strip()
    target = (body.get("target_lang") or cfg.data.get("subtitle_target_lang") or "zh").strip()
    source = (body.get("source_lang") or cfg.data.get("local_ai_lang") or "").strip()

    def job():
        try:
            out = translate_srt_file(
                str(p),
                provider=provider,
                target_lang=target,
                source_lang=source if source not in ("auto", "") else "",
                log=log_mgr.log,
            )
            log_mgr.log(f"机翻任务完成: {out}",
                        k="srv.ai.srt_translate_done", kv={"out": out})
        except Exception as e:
            log_mgr.log(f"机翻失败: {e}", "error",
                        k="srv.ai.srt_translate_failed", kv={"e": str(e)})

    threading.Thread(target=job, daemon=True).start()
    return {"ok": True, "message": f"已开始机翻 → {target}（{provider}）"}


@app.post("/api/ai/subtitle_export")
def api_ai_subtitle_export(body: dict):
    """双语字幕导出：换行 + 双语 SRT / VTT / ASS 三件套。"""
    try:
        p = resolve_media_path(body.get("path") or "")
    except HTTPException:
        raise
    if p.suffix.lower() != ".srt":
        raise HTTPException(400, "请选择 .srt 字幕文件")
    other = None
    if (body.get("with") or "").strip():
        try:
            other = resolve_media_path(body["with"].strip())
        except HTTPException:
            other = None
    if other is None:
        other = find_subtitle_counterpart(p)
    if other is None or not other.is_file():
        raise HTTPException(400, f"找不到 {p.name} 的同名另一路字幕（原文或译文），无法合成双语")

    target = str(cfg.data.get("subtitle_target_lang") or "zh").strip().lower()[:2]
    main_cue_path, sec_cue_path = p, other
    if _lang_suffix_of(other).startswith(target) and not _lang_suffix_of(p).startswith(target):
        main_cue_path, sec_cue_path = other, p

    def _cues(sp: Path):
        cs = parse_srt(sp.read_text(encoding="utf-8", errors="ignore"))
        if not cs:
            raise HTTPException(400, f"{sp.name} 没有有效字幕条目")
        return cs

    main_cues, sec_cues = _cues(main_cue_path), _cues(sec_cue_path)
    max_units = float(body.get("width") or cfg.data.get("subtitle_wrap_width") or 16)
    max_units = max(8.0, min(40.0, max_units))
    do_wrap = body.get("wrap")
    do_wrap = bool(cfg.data.get("subtitle_wrap", True)) if do_wrap is None else bool(do_wrap)
    if do_wrap:
        main_cues = wrap_cues(main_cues, max_units, 2)
        sec_cues = wrap_cues(sec_cues, max_units, 2)

    bi = merge_bilingual_cues(main_cues, sec_cues)
    written = []
    outs = [
        (main_cue_path.with_name(main_cue_path.stem + ".bi.srt"), write_srt(bi)),
        (main_cue_path.with_name(main_cue_path.stem + ".bi.vtt"), write_vtt(bi)),
        (
            main_cue_path.with_name(main_cue_path.stem + ".bi.ass"),
            srt_to_ass(wrap_cues(sec_cues, max_units * 1.6, 1), main_cues, title=main_cue_path.stem),
        ),
    ]
    for path, content in outs:
        path.write_text(content, encoding="utf-8")
        written.append(str(path))
        log_mgr.log(f"双语导出: {path.name}",
                    k="srv.ai.bilingual_export", kv={"name": path.name})
    return {
        "ok": True,
        "files": written,
        "cues": len(bi),
        "message": f"已导出 {len(written)} 个文件（{len(bi)} 条，译文取 {main_cue_path.name}）",
    }


HARDSUB_ALIGN = {"bottom": 2, "top": 8, "middle": 5}
HARDSUB_JOBS: Dict[str, dict] = {}
HARDSUB_LOCK = threading.Lock()


def _vtt_to_srt_text(raw: str) -> str:
    """WEBVTT → SRT 文本，好让字幕解析器复用同一套逻辑。"""
    raw = raw.lstrip("\ufeff").strip()
    block = re.split(r"\r?\n\r?\n", raw)
    out, n = [], 0
    for b in block:
        lines = [l.rstrip("\r") for l in b.splitlines()]
        lines = [l for l in lines if l.strip() and not l.strip().startswith(("WEBVTT", "NOTE", "Kind:", "Language:"))]
        timing = next((i for i, l in enumerate(lines) if "-->" in l), None)
        if timing is None:
            continue
        n += 1
        out.append(f"{n}\n{lines[timing].replace('.', ',')}\n" + "\n".join(lines[timing + 1:]))
    return "\n\n".join(out)


def _burn_ass_text(sub: Path, fontsize: int, align: int, font: str, outline: float) -> str:
    """字幕文件 → 渲染用 ASS 文本。已排好版的 .ass 原样端上，srt/vtt 走主样式重排。"""
    raw = sub.read_text(encoding="utf-8", errors="ignore")
    if sub.suffix.lower() == ".ass":
        return raw
    cues = parse_srt(_vtt_to_srt_text(raw) if sub.suffix.lower() == ".vtt" else raw)
    cues = [c for c in cues if (c.get("text") or "").strip()]
    if not cues:
        raise HTTPException(400, f"{sub.name} 里没有有效字幕")
    width = max(8.0, min(40.0, float(cfg.data.get("subtitle_wrap_width") or 16)))
    cues = wrap_cues(cues, width, 2) if cfg.data.get("subtitle_wrap", True) else cues
    return srt_to_ass([], cues, title=sub.stem, main_style={
        "font": font, "fontsize": fontsize, "align": align, "outline": outline,
    })


def _auto_burn_sub(media: Path) -> Optional[Path]:
    """自动选轴只认流水线记录或严格同名 —— 烧进画面的字擦不掉，宁可不烧也不能拿错一份。"""
    from ai_pipeline import load_manifest
    out = ((load_manifest(media).get("stages") or {}).get("subtitle") or {}).get("out") or ""
    p = Path(out) if out else None
    if p and p.is_file():
        return p
    for ext in (".srt", ".ass", ".vtt"):
        cand = media.with_suffix(ext)
        if cand.is_file():
            return cand
    return None


@app.get("/api/ai/hardsub_jobs")
def api_ai_hardsub_jobs():
    with HARDSUB_LOCK:
        return {"ok": True, "jobs": [{k: v for k, v in j.items() if k != "proc"} for j in HARDSUB_JOBS.values()]}


@app.post("/api/ai/hardsub_stop")
def api_ai_hardsub_stop(body: dict):
    media = resolve_media_path((body or {}).get("path") or "")
    with HARDSUB_LOCK:
        rec = HARDSUB_JOBS.get(str(media)) or {}
        proc = rec.get("proc")
        if proc is not None:
            rec["stopping"] = True
            rec["message"] = "正在停止"
    if proc is None:
        return {"ok": False, "message": "这个文件没有在烧的任务了"}
    try:
        proc.terminate()
    except Exception:
        pass
    return {"ok": True, "message": "已请求停止，半成品会被删掉"}


@app.post("/api/ai/hardsub")
def api_ai_hardsub(body: dict):
    """硬字幕烧录：把字幕画进画面，输出 <原名>.hardsub.mp4（源文件不动）。"""
    body = body or {}
    media = resolve_media_path(body.get("path") or "")
    ff = ffmpeg_mgr.find(ffmpeg_mgr.manual_path)
    if not ff:
        raise HTTPException(400, "没找到 FFmpeg，先去「组件与依赖」装好再烧字幕")
    if not _ffprobe_info(media).get("width"):
        raise HTTPException(400, f"{media.name} 没有视频轨，没有画面可烧字幕")

    sub = None
    if (body.get("srt") or "").strip():
        sub = resolve_media_path(body["srt"].strip())
        if sub.suffix.lower() not in (".srt", ".ass", ".vtt"):
            raise HTTPException(400, "字幕只认 .srt / .ass / .vtt")
    if sub is None:
        sub = _auto_burn_sub(media)
        if sub is None:
            raise HTTPException(400, f"{media.name} 旁边没有同名字幕（.srt/.ass/.vtt），先跑一次转写，或在下载时带上字幕")

    try:
        fontsize = max(16, min(96, int(body.get("fontsize") or 44)))
    except Exception:
        fontsize = 44
    align = HARDSUB_ALIGN.get(str(body.get("position") or "bottom"), 2)
    font = str(body.get("font") or "Microsoft YaHei").strip()[:40] or "Microsoft YaHei"
    try:
        crf = max(14, min(38, int(body.get("crf") or 20)))
    except Exception:
        crf = 20

    out = media.with_name(media.stem + ".hardsub.mp4")
    if out.exists() and not body.get("overwrite"):
        raise HTTPException(409, f"已经烧过一份 {out.name}，要重来请勾「覆盖旧文件」")
    key = str(media)
    with HARDSUB_LOCK:
        if (HARDSUB_JOBS.get(key) or {}).get("status") == "running":
            raise HTTPException(409, f"{media.name} 正在烧字幕，等它跑完或先停止")
        if len(HARDSUB_JOBS) > 30:
            for k in [k for k, v in HARDSUB_JOBS.items() if v.get("status") != "running"][:10]:
                HARDSUB_JOBS.pop(k, None)
        HARDSUB_JOBS[key] = {
            "media": _ui_path(media), "out": _ui_path(out), "srt": _ui_path(sub),
            "status": "running", "elapsed": "", "total": 0.0, "message": "准备中",
        }

    def job():
        tmp = media.parent / f"_burnsub_{uuid.uuid4().hex[:8]}.ass"
        proc = None
        try:
            info = _ffprobe_info(media)
            total = float(info.get("duration") or 0)
            tmp.write_text(_burn_ass_text(sub, fontsize, align, font, 2.4), encoding="utf-8")
            # mp4 装不下 opus/vorbis 这类音轨，直接 copy 会让 ffmpeg 报错 —— 按源编码决定要不要重编音频
            acopy = (info.get("acodec") or "").lower() in ("aac", "mp3", "mp2", "ac3")
            head = [
                ff, "-hide_banner", "-nostdin", "-loglevel", "error", "-y",
                "-progress", "pipe:1", "-nostats", "-i", str(media),
                "-vf", f"ass=filename={tmp.name}",
            ]
            acmd = ["-c:a", "copy"] if acopy else ["-c:a", "aac", "-b:a", "192k"]
            chain = _video_encode_chain(crf)
            nxt = "，不行依次换 " + " → ".join(x["label"] for x in chain[1:]) if len(chain) > 1 else ""
            log_mgr.log(
                f"开始烧字幕: {media.name} ← {sub.name}"
                f"（{fontsize} 号 · 字幕{'居中' if align == 5 else '靠上' if align == 8 else '靠下'}"
                f" · crf {crf} · 用 {chain[0]['label']}{nxt}）"
            )

            def attempt(enc):
                """拿一个编码器烧一遍，返回 (ffmpeg 退出码, 是否被停止, 末尾报错行)。"""
                nonlocal proc
                cmd = head + list(enc["args"]) + acmd + ["-movflags", "+faststart", str(out)]
                proc = subprocess.Popen(
                    cmd, cwd=str(media.parent), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding="utf-8", errors="replace",
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                with HARDSUB_LOCK:
                    if key in HARDSUB_JOBS:
                        HARDSUB_JOBS[key]["proc"] = proc
                        HARDSUB_JOBS[key]["total"] = total
                last_log, tail = time.time(), []
                while True:
                    ln = proc.stdout.readline()
                    if not ln:
                        break
                    ln = ln.strip()
                    # ffmpeg 9 的 -progress 用的是 out_time=，写成 out_time_str= 会一条都读不到
                    if ln.startswith(("out_time=", "out_time_str=")):
                        elapsed = ln.split("=", 1)[1].split(".")[0]
                        with HARDSUB_LOCK:
                            if key in HARDSUB_JOBS:
                                HARDSUB_JOBS[key]["elapsed"] = elapsed
                        if total and time.time() - last_log > 20:
                            last_log = time.time()
                            h, mi, s = (int(x or 0) for x in elapsed.split(":"))
                            done = h * 3600 + mi * 60 + s
                            log_mgr.log(f"烧字幕中 {media.name}: {done}/{int(total)}s（{done * 100 // max(1, int(total))}%）",
                                        k="srv.ai.hardsub_progress",
                                        kv={"name": media.name, "done": done, "total": int(total),
                                            "pct": done * 100 // max(1, int(total))})
                    elif ln and len(ln) < 300 and not re.match(r"^\w+=", ln):
                        tail.append(ln)
                        del tail[:-30]
                code = proc.wait()
                with HARDSUB_LOCK:
                    rec = HARDSUB_JOBS.get(key) or {}
                    stopped = bool(rec.get("stopping"))
                    rec.pop("proc", None)
                return code, stopped, tail, rec

            used = None
            for idx, enc in enumerate(chain):
                code, stopped, tail, rec = attempt(enc)
                if stopped:
                    out.unlink(missing_ok=True)
                    with HARDSUB_LOCK:
                        rec.update(status="stopped", message="已停止，半成品已删除")
                    log_mgr.log(f"已停止烧字幕: {media.name}，半成品已删", "warning",
                                k="srv.ai.hardsub_stopped", kv={"name": media.name})
                    return
                if code == 0 and out.is_file():
                    used = enc
                    break
                # 半成品不能留着让下一次以为烧完了 —— 换编码器是从头再来一遍
                out.unlink(missing_ok=True)
                why = " / ".join(tail[-3:])[-260:] or f"ffmpeg 退出码 {code}"
                rest = chain[idx + 1:]
                if rest:
                    log_mgr.log(f"烧字幕用 {enc['label']} 没成（{why[:140]}），换 {rest[0]['label']} 重来", "warning")
                else:
                    raise RuntimeError(why or "ffmpeg 失败")
            size_mb = out.stat().st_size / 1048576.0
            with HARDSUB_LOCK:
                if key in HARDSUB_JOBS:
                    HARDSUB_JOBS[key].update(
                        status="done",
                        message=f"已生成 {out.name}（{size_mb:.0f} MB · {used['label']}）")
            log_mgr.log(f"烧字幕完成: {out.name}（{size_mb:.0f} MB · 用 {used['label']}）")
        except Exception as e:
            with HARDSUB_LOCK:
                if key in HARDSUB_JOBS:
                    HARDSUB_JOBS[key].update(status="failed", message=str(e)[:260])
            log_mgr.log(f"烧字幕失败: {e}", "error",
                        k="srv.ai.hardsub_failed", kv={"e": str(e)})
        finally:
            tmp.unlink(missing_ok=True)

    threading.Thread(target=job, daemon=True).start()
    return {"ok": True, "message": f"开始烧字幕：{sub.name} → {out.name}", "out": _ui_path(out), "srt": _ui_path(sub)}


@app.post("/api/update/whisper")
def api_update_whisper(body: dict = None):
    body = body or {}
    model = (body.get("model") if isinstance(body, dict) else None) or "base"

    def job():
        res = update_whisper(
            log=lambda m, level="info": log_mgr.log(m, level),
            model=str(model),
        )
        log_mgr.log(f"Whisper 更新结果: {res}", k="srv.comp.whisper_update_result", kv={"res": res})

    threading.Thread(target=job, daemon=True).start()
    return {"ok": True, "message": f"Whisper (faster-whisper + 模型 {model}) 更新已在后台开始"}


@app.get("/api/health")
def api_health():
    """存活探针：只读内存里的队列计数，供容器 HEALTHCHECK / 负载均衡每几十秒打一次。

    别用 /api/status 当探针——它会真的去跑 ffmpeg --version、导入 yt_dlp、递归扫 Whisper 目录，
    定期探活会把 CPU 全烧在工具检测上。
    """
    return {"ok": True, "running": queue.running, "paused": queue.paused, "pending": len(queue.pending)}


@app.get("/api/status")
def api_status():
    ff_path = ffmpeg_mgr.find(ffmpeg_mgr.manual_path)
    cookie_file = (cfg.data.get("cookie_file") or str(DEFAULT_COOKIE_FILE)).strip()
    nm = find_n_m3u8dl()
    w = whisper_status()
    return {
        "ffmpeg": ffmpeg_mgr.version(),
        "ffmpeg_path": ff_path or "",
        "ytdlp": engine.check_ytdlp(),
        "n_m3u8dl": n_m3u8dl_version(),
        "n_m3u8dl_path": nm or "",
        "whisper": w.get("label") or "未安装",
        "whisper_dir": w.get("dir") or "",
        "whisper_cli": w.get("cli") or "",
        "running": queue.running,
        "paused": queue.paused,
        "pending": len(queue.pending),
        "tasks": len(queue.tasks),
        "cookie_source": cfg.data.get("cookie_source", "none"),
        "cookie_file": cookie_file,
        "cookie_exists": Path(cookie_file).exists() if cookie_file else False,
        "tools_dir": str(TOOLS_DIR),
        "cookies_dir": str(COOKIES_DIR),
        "platform": sys.platform,
        "disk_free_gb": _disk_free_gb(cfg.data.get("download_dir") or str(DEFAULT_DOWNLOAD_DIR)),
        "extension_dir": str(APP_DIR / "extension"),
        "throttle": HOST_THROTTLE.snapshot(),
        "adaptive_throttle": bool(cfg.data.get("adaptive_throttle", True)),
        "po_token": po_token_health(),
    }


@app.post("/api/po_token/check")
def api_po_token_check():
    """强制探一次 bgutil PO Token 服务（不通会试着用本机 node 拉起 tools/ 里那份），
    并回给生效中的 YouTube 客户端链。"""
    st = po_token_health(force=True)
    chain, note = engine._yt_player_chain(cfg.data, "https://www.youtube.com/watch?v=x")
    try:
        import pot_daemon

        daemon = {**pot_daemon.status(APP_DIR), **pot_daemon.owned()}
    except Exception:
        daemon = {}
    return {
        "ok": True,
        **st,
        "enabled": bool(cfg.data.get("po_provider_enabled")),
        "daemon": daemon,
        "chain": chain,
        "note": note,
        "fingerprints": list(TLS_FINGERPRINTS),
        "impersonate": _impersonate_on(),
    }


@app.post("/api/queue/throttle_reset")
def api_throttle_reset(body: dict):
    """手动解除站点降速；host 留空则清空全部。"""
    host = str((body or {}).get("host") or "").strip().lower()
    n = HOST_THROTTLE.reset(host)
    if n:
        log_mgr.log(f"已清除 {n} 个站点的降速冷却" + (f"（{host}）" if host else ""))
    queue._pump()
    return {"ok": True, "cleared": n, "throttle": HOST_THROTTLE.snapshot()}


def _disk_free_gb(path: str) -> float:
    try:
        p = Path(path)
        p.mkdir(parents=True, exist_ok=True)
        usage = shutil.disk_usage(str(p))
        return round(usage.free / (1024 ** 3), 2)
    except Exception:
        return -1.0


@app.post("/api/update/ytdlp")
def api_update_ytdlp():
    def job():
        res = engine.update_ytdlp()
        log_mgr.log(f"yt-dlp 更新结果: {res}", k="srv.comp.ytdlp_update_result", kv={"res": res})

    threading.Thread(target=job, daemon=True).start()
    return {"ok": True, "message": "yt-dlp 更新已在后台开始"}


@app.post("/api/update/ffmpeg")
def api_update_ffmpeg():
    def job():
        ok = ffmpeg_mgr.update()
        # 条件句拆成两处调用（口径同 #55 前几批）：落盘的中文一个字不变，英文才有两把键可拼
        if ok:
            log_mgr.log("FFmpeg 更新结果: 成功", k="srv.comp.ffmpeg_update_ok")
        else:
            log_mgr.log("FFmpeg 更新结果: 失败", k="srv.comp.ffmpeg_update_fail")

    threading.Thread(target=job, daemon=True).start()
    return {"ok": True, "message": "FFmpeg 更新已在后台开始"}


@app.post("/api/update/n_m3u8dl")
def api_update_n_m3u8dl():
    def job():
        res = update_n_m3u8dl(log=lambda m, level="info": log_mgr.log(m, level))
        log_mgr.log(f"N_m3u8DL-RE 更新结果: {res}", k="srv.comp.nm3u8dl_update_result", kv={"res": res})

    threading.Thread(target=job, daemon=True).start()
    return {"ok": True, "message": "N_m3u8DL-RE 更新已在后台开始，请稍后刷新状态"}


@app.post("/api/update/aria2")
def api_update_aria2():
    def job():
        res = update_aria2(log=lambda m, level="info": log_mgr.log(m, level))
        log_mgr.log(f"aria2c 安装结果: {res}", k="srv.comp.aria2_install_result", kv={"res": res})

    threading.Thread(target=job, daemon=True).start()
    return {"ok": True, "message": "aria2c 安装已在后台开始（约 2 MB），完成后刷新「组件与依赖」"}


def path_dirs() -> List[str]:
    """工具落地的目录：命令行里要能直接敲 ffmpeg / yt-dlp / fpcalc，就得都在 PATH 上。"""
    out = [str(TOOLS_DIR)]
    chroma = APP_DIR / "chromaprint"
    if (chroma / "fpcalc.exe").exists() or (chroma / "fpcalc").exists() or chroma.exists():
        out.append(str(chroma))
    return out


def _path_split(cur: str) -> List[str]:
    """按当前平台的 PATH 分隔符拆。Linux/macOS 是「:」，写死「;」会把整条 PATH 当成一项。"""
    return [p for p in str(cur or "").split(os.pathsep) if p.strip()]


def _same_dir(a: str, b: str) -> bool:
    return os.path.normcase(str(a).rstrip("\\/ ")) == os.path.normcase(str(b).rstrip("\\/ "))


def _path_add(cur: str, dirs: Sequence[str]) -> str:
    parts = _path_split(cur)
    for d in dirs:
        if not any(_same_dir(p, d) for p in parts):
            parts.append(str(d))
    return os.pathsep.join(parts)


def _path_remove(cur: str, dirs: Sequence[str]) -> str:
    return os.pathsep.join(p for p in _path_split(cur) if not any(_same_dir(p, d) for d in dirs))


def user_path_read() -> tuple:
    """返回 (用户 PATH 原文, 注册表类型)。原文不展开，写回时才不会丢 %XXX% 变量。"""
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_READ) as k:
            val, typ = winreg.QueryValueEx(k, "Path")
        return str(val or ""), int(typ or winreg.REG_EXPAND_SZ)
    except FileNotFoundError:
        return "", 1  # REG_EXPAND_SZ


def user_path_write(val: str, typ: int) -> None:
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, "Path", 0, typ, val)
    _broadcast_env_change()


def _broadcast_env_change() -> None:
    """通知 explorer 重载环境，新开的 cmd / 资源管理器不用重启系统就能看到新 PATH。"""
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        result = wintypes.DWORD(0)
        user32.SendMessageTimeoutW(
            wintypes.HWND(0xFFFF),  # HWND_BROADCAST
            wintypes.UINT(0x1A),    # WM_SETTINGCHANGE
            wintypes.WPARAM(0),
            ctypes.c_wchar_p("Environment"),
            wintypes.UINT(0x0002),  # SMTO_ABORTIFHUNG
            wintypes.UINT(5000),
            ctypes.byref(result),
        )
    except Exception:
        pass


def env_path_status() -> dict:
    dirs = path_dirs()
    exe = ".exe" if sys.platform == "win32" else ""
    tools = {
        "ffmpeg": TOOLS_DIR / f"ffmpeg{exe}",
        "ffprobe": TOOLS_DIR / f"ffprobe{exe}",
        "yt-dlp": TOOLS_DIR / f"yt-dlp{exe}",
        "N_m3u8DL-RE": TOOLS_DIR / f"N_m3u8DL-RE{exe}",
        "fpcalc": APP_DIR / "chromaprint" / f"fpcalc{exe}",
    }
    present = [n for n, p in tools.items() if is_native_binary(p)]
    if not exe:
        # Linux/macOS 上工具常由 apt 装进系统 PATH，随包文件本来就不存在；
        # 只查 TOOLS_DIR 会把明明能跑的 ffmpeg 报成缺失。
        present += [n for n in tools if n not in present and shutil.which(n)]
    st = {
        "platform": sys.platform,
        "dirs": dirs,
        "present": present,
        "writable": sys.platform == "win32",
        "in_path": [],
        "export": "export PATH=\"" + ":".join(dirs) + ":$PATH\"",
    }
    try:
        if sys.platform == "win32":
            cur, _typ = user_path_read()
        else:
            cur = os.environ.get("PATH", "")
        st["current"] = cur
        st["in_path"] = [d for d in dirs if any(_same_dir(p, d) for p in _path_split(cur))]
        st["missing"] = [d for d in dirs if d not in st["in_path"]]
    except Exception as e:
        st["error"] = str(e)[:200]
    st["ok"] = len(st.get("in_path") or []) == len(dirs)
    return st


@app.get("/api/env/path")
def api_env_path_get():
    return env_path_status()


@app.post("/api/env/path")
def api_env_path(body: dict = None):
    body = body or {}
    action = str(body.get("action") or "check").lower()
    dirs = path_dirs()
    if action == "check":
        return env_path_status()
    if sys.platform != "win32":
        return {"ok": False, "message": "非 Windows 请手动把下面这行加进 ~/.bashrc 或 ~/.zshrc",
                "export": "export PATH=\"" + ":".join(dirs) + ":$PATH\"", "dirs": dirs}
    try:
        cur, typ = user_path_read()
        new = _path_add(cur, dirs) if action == "add" else _path_remove(cur, dirs)
        if new == cur:
            return {**env_path_status(), "ok": True, "message": "已经是当前状态，无需修改"}
        user_path_write(new, typ)
        after, _ = user_path_read()
        if after != new:
            user_path_write(cur, typ)  # 写歪了就还原，别把用户 PATH 留在半更新状态
            return {"ok": False, "message": "写入后校验不一致，已还原原 PATH"}
        return {**env_path_status(), "ok": True,
                "message": ("已加入 PATH（新开的命令行窗口即刻可用）" if action == "add"
                            else "已从 PATH 移除")}
    except Exception as e:
        return {**env_path_status(), "ok": False, "message": f"修改失败：{str(e)[:200]}"}


BUNDLED_FILE = APP_DIR / "components_bundled.json"
_bundled_cache: dict = {"mtime": None, "data": {}}
LATEST_TTL = 600
_latest_cache: dict = {"ts": 0.0, "mirror": None, "data": {}}


def bundled_manifest() -> dict:
    """便携包里的「随包版本」清单（打包时由 pack_release.py 写入）。源码运行没有这个文件 → 空。"""
    try:
        mt = BUNDLED_FILE.stat().st_mtime
    except Exception:
        return {}
    if _bundled_cache["mtime"] != mt:
        try:
            data = json.loads(BUNDLED_FILE.read_text(encoding="utf8"))
        except Exception:
            data = {}
        _bundled_cache.update(mtime=mt, data=data if isinstance(data, dict) else {})
    return _bundled_cache["data"]


def _bundled_version(manifest: dict, item: dict) -> str:
    tools = manifest.get("tools") or {}
    pip = manifest.get("pip") or {}
    for src, key in (("tools", item.get("tool")), ("pip", item.get("pkg"))):
        v = (tools if src == "tools" else pip).get(key or "")
        if v:
            return str(v)
    return ""


def latest_versions_cached(mirror: str) -> dict:
    """上游最新版要问 pip（一次约两秒），所以只在页面点「查询最新版本」时才查，结果缓存 10 分钟。"""
    now = time.time()
    if _latest_cache["data"] and _latest_cache["mirror"] == mirror and now - _latest_cache["ts"] < LATEST_TTL:
        return _latest_cache["data"]
    from voice_tools import SEP_ENGINE_PKGS
    names = [p["name"] for p in pkg_update.PIP_PACKAGES] + list(SEP_ENGINE_PKGS)
    data = pkg_update.latest_versions(names, mirror)
    _latest_cache.update(ts=now, mirror=mirror, data=data)
    return data


def _component_rows(lv: dict, manifest: dict) -> list:
    """拼「组件与依赖」那张表：当前版本现取，上游最新版由调用方传进来（传空就一律留白）。"""
    ff = str(ffmpeg_mgr.version() or "")
    ff_ok = bool(ffmpeg_mgr.find(ffmpeg_mgr.manual_path))
    ytd = str(engine.check_ytdlp() or "")
    nm = str(n_m3u8dl_version() or "")
    a2 = str(aria2_local_version() or "")
    w = whisper_status()
    exe = ".exe" if sys.platform == "win32" else ""
    items = [
        {"key": "ffmpeg", "cn": "视频合并 / 转码",
         "label": "FFmpeg / FFprobe（合并、转码、嵌封面字幕）",
         "tool": f"ffmpeg{exe}", "pkg": "",
         "active": ff or "未安装", "ok": ff_ok,
         "update": "/api/update/ffmpeg"},
        {"key": "ytdlp", "cn": "站点解析工具",
         "label": "yt-dlp（各站点解析规则，最常需要更新）",
         "tool": f"yt-dlp{exe}", "pkg": "yt-dlp",
         "active": ytd, "ok": "not found" not in ytd.lower(), "update": "/api/update/ytdlp"},
        {"key": "n_m3u8dl", "cn": "HLS 分片 / 直播录制",
         "label": "N_m3u8DL-RE（HLS 分片 / 直播录制）",
         "tool": f"N_m3u8DL-RE{exe}", "pkg": "",
         "active": nm or "未安装", "ok": bool(nm), "update": "/api/update/n_m3u8dl"},
        {"key": "aria2", "cn": "磁力 / 种子下载",
         "label": "aria2c（磁力 / 种子下载，本机没有它那一页就跑不动）",
         "tool": f"aria2c{exe}", "pkg": "",
         "active": a2 or "未安装", "ok": bool(a2), "update": "/api/update/aria2"},
        {"key": "faster-whisper", "cn": "本地转写（含模型）",
         "label": "faster-whisper（本地转写，含模型体积较大）",
         "tool": "", "pkg": "faster-whisper",
         "active": str(w.get("label") or "未安装"),
         "ok": bool(w.get("faster_whisper") or w.get("cli")),
         "update": "/api/update/whisper"},
    ]
    for p in pkg_update.PIP_PACKAGES:
        if p["name"] == "faster-whisper":
            continue  # 上面那条走 /api/update/whisper，还要顺带拉模型
        v = pkg_update.installed_version(p["name"])
        row = {"key": p["name"], "label": p["label"], "cn": str(p.get("cn") or ""),
               "tool": "", "pkg": p["name"],
               "active": v or "未安装", "ok": bool(v), "update": "/api/update/pkg"}
        _pot_row_extra(row, cfg.data)
        items.append(row)
    for it in items:
        it["bundled"] = _bundled_version(manifest, it)
        it["latest"] = ""
        it["latest_note"] = ""
        row = lv.get(it["pkg"]) or {}
        if row:
            it["latest"] = str(row.get("version") or "")
            it["latest_note"] = "" if it["latest"] else str(row.get("error") or "")
    return items


@app.get("/api/components")
def api_components(latest: str = ""):
    """设置页「组件与依赖」：随包版本 / 当前版本 /（点了「查询最新版本」才有）上游最新版。"""
    lv: dict = {}
    if latest:
        try:
            lv = latest_versions_cached(str(cfg.data.get("pip_mirror") or ""))
        except Exception as e:
            log_mgr.log(f"上游版本查询失败：{str(e)[:160]}", "warning",
                        k="srv.comp.upstream_query_failed", kv={"e": str(e)[:160]})
    manifest = bundled_manifest()
    return {
        "items": _component_rows(lv, manifest),
        "sep_engine": _sep_engine_state(lv),
        "env_path": env_path_status(),
        "pip": pkg_update.pip_available(),
        "pip_version": pkg_update.pip_version(),
        "python": sys.executable,
        "portable": (APP_DIR / "runtime" / "python.exe").exists(),
        "bundled": {"app": str(manifest.get("app") or ""), "built": str(manifest.get("built") or "")},
        "latest_checked": bool(latest),
        "pip_mirror": str(cfg.data.get("pip_mirror") or ""),
        "github_mirror": str(cfg.data.get("github_mirror") or ""),
        "pip_mirrors": [m for m in pkg_update.PIP_MIRRORS if m],
        "update_all": dict(_COMP_ALL),
        "auto_check": bool(cfg.data.get("components_auto_check")),
        "update_check": _comp_check_state(),
    }


def _ver_seg(s: str) -> list:
    """取版本号里第一段数字（'2026.8.19 (local)'、'未安装' 都要能进这里）。"""
    m = re.search(r"\d+(?:\.\d+)*", str(s or ""))
    return [int(x) for x in m.group(0).split(".")] if m else []


def _ver_newer(current: str, latest: str) -> bool:
    """上游版是否比本机版新。两侧都对齐补零后逐段比，全等则不算有新版。"""
    a, b = _ver_seg(current), _ver_seg(latest)
    if not b:
        return False
    if not a:
        return True
    for i in range(max(len(a), len(b))):
        d = (a[i] if i < len(a) else 0) - (b[i] if i < len(b) else 0)
        if d:
            return d < 0
    return False


def _sep_engine_rows(lv: dict) -> list:
    """分离引擎的两个包在独立 venv 里，组件表那套「当前版本」问不到它们，
    所以单独读元数据、单独比上游版。"""
    from voice_tools import SEP_ENGINE_PKGS, separator_engine_versions
    have = separator_engine_versions()
    out = []
    for pkg in SEP_ENGINE_PKGS:
        active = str(have.get(pkg) or "")
        row = lv.get(pkg) or {}
        latest = str(row.get("version") or "")
        out.append({"pkg": pkg, "active": active, "latest": latest,
                    "latest_note": "" if latest else str(row.get("error") or ""),
                    "updatable": bool(active and latest and _ver_newer(active, latest))})
    return out


def _sep_engine_state(lv: dict) -> dict:
    items = _sep_engine_rows(lv)
    return {"installed": any(i["active"] for i in items), "items": items}


def _sep_engine_available(lv: dict) -> list:
    """检测结果里只报一条：两个引擎是同一组一起升，列两行会变成两条同义通知。"""
    outdated = [i for i in _sep_engine_rows(lv) if i["updatable"]]
    if not outdated:
        return []
    e = outdated[0]
    return [{"key": "sep:engines", "pkg": e["pkg"],
             "label": "人声分离引擎（audio-separator / demucs）",
             "current": e["active"], "latest": e["latest"]}]


# 打开程序就自动查一遍上游版本：查一次要两三秒，绝不能挡在启动路径上，
# 所以只放后台线程跑，界面拿到的永远是「状态 + 上次结果」。
_COMP_CHECK: Dict[str, Any] = {"status": "idle", "started": "", "finished": "",
                               "available": [], "error": ""}
_COMP_CHECK_LOCK = threading.Lock()


def _comp_check_state() -> dict:
    with _COMP_CHECK_LOCK:
        st = dict(_COMP_CHECK)
    st["available"] = list(st["available"])
    return st


def _comp_check_with_flag() -> dict:
    """状态里始终带上开关，界面据此决定要不要自动弹窗。"""
    return {"auto_check": bool(cfg.data.get("components_auto_check")), **_comp_check_state()}


def _comp_available_updates(rows: list) -> list:
    """挑出确有可更新版本的组件。

    没装上的不算「有更新」：faster-whisper 这类是故意不随包发的，把它算进来就会每次开机
    都弹窗催装同一个东西。不在 PyPI 的（FFmpeg / N_m3u8DL-RE）没有上游版可比，同样跳过。
    """
    out = []
    for it in rows:
        if not it.get("pkg") or not it.get("ok"):
            continue
        latest = str(it.get("latest") or "")
        if latest and _ver_newer(str(it.get("active") or ""), latest):
            out.append({"key": it["key"], "label": it["label"],
                        "current": str(it.get("active") or ""), "latest": latest})
    return out


def _comp_check_worker() -> None:
    try:
        lv = latest_versions_cached(str(cfg.data.get("pip_mirror") or ""))
        available = _comp_available_updates(_component_rows(lv, bundled_manifest()))
        available += _sep_engine_available(lv)
        with _COMP_CHECK_LOCK:
            _COMP_CHECK.update(
                status="done",
                finished=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                available=available, error="")
        if available:
            log_mgr.log(f"[组件] 检测上游版本：{len(available)} 个组件有可更新版本",
                        k="srv.comp.check_available", kv={"n": len(available)})
        else:
            log_mgr.log("[组件] 检测上游版本：已在用组件都是最新",
                        k="srv.comp.check_all_latest")
    except Exception as e:
        with _COMP_CHECK_LOCK:
            _COMP_CHECK.update(
                status="error",
                finished=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                error=f"{type(e).__name__}: {str(e)[:160]}")
        log_mgr.log(f"[组件] 检测上游版本失败：{type(e).__name__}: {str(e)[:160]}", "warning",
                    k="srv.comp.check_failed",
                    kv={"cls": type(e).__name__, "detail": str(e)[:160]})


def _comp_check_start(force: bool = False) -> dict:
    """起一次检测；已经在跑就直接复用那一次，界面轮询时不会把同一个查询打很多遍。"""
    with _COMP_CHECK_LOCK:
        if _COMP_CHECK["status"] != "running":
            _COMP_CHECK["status"] = "running"
            _COMP_CHECK["started"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            _COMP_CHECK["error"] = ""
            run = True
        else:
            run = False
    if run:
        if force:
            _latest_cache["ts"] = 0.0  # 「立即检测」要看真实上游，不许吃 10 分钟前的缓存
        threading.Thread(target=_comp_check_worker, daemon=True).start()
    return _comp_check_with_flag()


@app.get("/api/components/update-check")
def api_components_update_check_get():
    return _comp_check_with_flag()


class CompCheckBody(BaseModel):
    force: bool = False
    kick: bool = True


@app.post("/api/components/update-check")
def api_components_update_check(body: CompCheckBody = None):
    """界面（或启动线程）用来触发一次上游版本检测：立即返回，结果靠后续 GET 轮。"""
    body = body or CompCheckBody()
    if not body.kick:
        return _comp_check_with_flag()
    return _comp_check_start(bool(body.force))


# 「一键更新」：一次只跑一批，批内串行 —— pip 并发装会互相踩，GitHub 大文件同时下也没意义
_COMP_ALL: Dict[str, Any] = {"running": False, "total": 0, "done": 0,
                             "current": "", "current_key": "", "results": [], "started": ""}
_COMP_ALL_LOCK = threading.Lock()


def _comp_update_one(key: str, mirror: str, log: Callable) -> tuple:
    """更新一个组件，返回 (是否成功, 给人看的说明)。"""
    if key == "sep:engines":
        from voice_tools import update_separator_engines
        res = str(update_separator_engines(log=log, mirror=mirror) or "")
        return res == "ok", res
    if key == "ffmpeg":
        ok = bool(ffmpeg_mgr.update())
        return ok, f"当前 {ffmpeg_mgr.version() or '未安装'}"
    if key == "ytdlp":
        res = str(engine.update_ytdlp() or "")
        return res.startswith("updated"), f"{res}｜当前 {engine.check_ytdlp()}"
    if key == "n_m3u8dl":
        res = str(update_n_m3u8dl(log=log) or "")
        return res.startswith("成功"), res
    if key == "aria2":
        res = str(update_aria2(log=log) or "")
        # 非 Windows 没有官方预编译包，那句「用 apt 装」是指引不是失败，别算成红项
        return (not res.startswith("下载失败") and not res.startswith("解压")
                and not res.startswith("装好了，但拉起失败")), res
    if key == "faster-whisper":
        res = str(update_whisper(log=log, model="base") or "")
        return not res.startswith("failed"), res
    ok, res = pkg_update.pip_install([key], log=log, mirror=mirror)
    return bool(ok), str(res)


def _comp_update_all(keys: List[str], mirror: str) -> None:
    labels = {p["name"]: p["label"] for p in pkg_update.PIP_PACKAGES}
    labels.update({"ffmpeg": "FFmpeg", "ytdlp": "yt-dlp", "n_m3u8dl": "N_m3u8DL-RE",
                   "faster-whisper": "faster-whisper", "aria2": "aria2c",
                   "sep:engines": "人声分离引擎"})
    try:
        for i, key in enumerate(keys, 1):
            with _COMP_ALL_LOCK:
                _COMP_ALL["done"] = i - 1
                _COMP_ALL["current"] = labels.get(key, key)
                _COMP_ALL["current_key"] = key
            log_mgr.log(f"一键更新（{i}/{len(keys)}）：开始 {labels.get(key, key)}",
                        k="srv.comp.update_start",
                        kv={"i": i, "total": len(keys), "label": labels.get(key, key)})
            try:
                ok, msg = _comp_update_one(key, mirror, log_mgr.log)
            except Exception as e:
                ok, msg = False, f"{type(e).__name__}: {str(e)[:200]}"
            if ok:
                log_mgr.log(f"一键更新（{i}/{len(keys)}）：{labels.get(key, key)} 成功 —— {msg}",
                            "info",
                            k="srv.comp.update_ok",
                            kv={"i": i, "total": len(keys), "label": labels.get(key, key),
                                "msg": msg})
            else:
                log_mgr.log(f"一键更新（{i}/{len(keys)}）：{labels.get(key, key)} 失败 —— {msg}",
                            "error",
                            k="srv.comp.update_failed",
                            kv={"i": i, "total": len(keys), "label": labels.get(key, key),
                                "msg": msg})
            with _COMP_ALL_LOCK:
                _COMP_ALL["results"].append({"key": key, "label": labels.get(key, key),
                                             "ok": bool(ok), "msg": msg[:300]})
    except Exception as e:   # 单项里的异常上面已经吞掉了，走到这里说明是这轮自己坏了
        log_mgr.log(f"一键更新中断：{type(e).__name__}: {str(e)[:200]}", "error",
                    k="srv.comp.update_aborted",
                    kv={"cls": type(e).__name__, "detail": str(e)[:200]})
    finally:
        # 无论怎么收尾都要把 running 清掉，否则界面永远发不起下一批
        with _COMP_ALL_LOCK:
            done = len(_COMP_ALL["results"])
            bad = [r["label"] for r in _COMP_ALL["results"] if not r["ok"]]
            _COMP_ALL["running"] = False
            _COMP_ALL["current"] = ""
            _COMP_ALL["current_key"] = ""
            _COMP_ALL["done"] = done
        log_mgr.log(f"一键更新结束：完成 {done}/{len(keys)} 项"
                    + (f"，失败 {len(bad)} 项（{'、'.join(bad)}），原因见上面各行" if bad
                       else "，全部成功"))


@app.post("/api/components/update-all")
def api_components_update_all(body: dict = None):
    """一键更新：界面按「未安装的 + 查到有最新版的」挑好条目，这里串行跑完并留进度。"""
    body = body or {}
    keys = [str(k).strip() for k in (body.get("keys") or []) if str(k).strip()]
    known = {p["name"] for p in pkg_update.PIP_PACKAGES} | {
        "ffmpeg", "ytdlp", "n_m3u8dl", "faster-whisper", "aria2", "sep:engines"}
    bad = [k for k in keys if k not in known]
    if bad:
        raise HTTPException(400, f"这些条目不能从这里更新：{'、'.join(bad[:6])}")
    if not keys:
        raise HTTPException(400, "没有要更新的条目")
    with _COMP_ALL_LOCK:
        if _COMP_ALL["running"]:
            return {"ok": False,
                    "message": f"已经有一批更新在跑（{_COMP_ALL['done']}/{_COMP_ALL['total']}，"
                               f"当前 {_COMP_ALL['current']}），请等它结束",
                    "update_all": dict(_COMP_ALL)}
        _COMP_ALL.update({"running": True, "total": len(keys), "done": 0,
                          "current": keys[0], "current_key": keys[0], "results": [],
                          "started": datetime.now().strftime("%H:%M:%S")})
    mirror = str(body.get("mirror") or cfg.data.get("pip_mirror") or "")
    log_mgr.log(f"一键更新开始：{len(keys)} 项（{'、'.join(keys[:8])}"
                + ("…" if len(keys) > 8 else "") + "），一项一项串行跑")
    threading.Thread(target=_comp_update_all, args=(keys, mirror), daemon=True).start()
    return {"ok": True, "message": f"一键更新已在后台开始（{len(keys)} 项，串行跑，进度见运行日志）",
            "update_all": dict(_COMP_ALL)}


@app.post("/api/update/pkg")
def api_update_pkg(body: dict = None):
    body = body or {}
    name = str(body.get("name") or "").strip()
    if name not in {p["name"] for p in pkg_update.PIP_PACKAGES}:
        raise HTTPException(400, f"不支持从这里更新的依赖：{name or '(空)'}")
    idx = str(body.get("mirror") or cfg.data.get("pip_mirror") or "")

    def job():
        ok, res = pkg_update.pip_install([name], log=log_mgr.log, mirror=idx)
        if ok:
            log_mgr.log(f"{name} 更新结果：成功（{res}）", k="srv.comp.pkg_update_ok",
                        kv={"name": name, "res": res})
        else:
            log_mgr.log(f"{name} 更新结果：失败（{res}）", k="srv.comp.pkg_update_fail",
                        kv={"name": name, "res": res})

    threading.Thread(target=job, daemon=True).start()
    return {"ok": True, "message": f"{name} 更新已在后台开始"}


@app.get("/api/extension/zip")
def api_extension_zip():
    """打包浏览器扩展供下载安装"""
    ext_dir = APP_DIR / "extension"
    if not (ext_dir / "manifest.json").is_file():
        raise HTTPException(404, "extension/manifest.json 不存在")
    import io
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in ext_dir.rglob("*"):
            if p.is_file():
                zf.write(p, arcname=str(p.relative_to(ext_dir)))
    buf.seek(0)
    from fastapi.responses import StreamingResponse
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=MediaDownloader-Sniffer-extension.zip"},
    )


@app.get("/api/extension/info")
def api_extension_info():
    ext_dir = APP_DIR / "extension"
    manifest = ext_dir / "manifest.json"
    info = {"exists": manifest.is_file(), "path": str(ext_dir), "files": []}
    if manifest.is_file():
        try:
            info["manifest"] = json.loads(manifest.read_text(encoding="utf-8"))
        except Exception:
            info["manifest"] = {}
        info["files"] = sorted(p.name for p in ext_dir.iterdir() if p.is_file())
    return info


@app.get("/api/config")
def api_get_config():
    return _auth_config_mask(cfg.data)


@app.post("/api/config")
def api_set_config(body: ConfigBody, request: Request = None):
    # 界面只交「刚改的那几项」：整包回存会把这一页打开之后别的入口改过的键一起盖回去
    return _apply_config(body.model_dump(exclude_none=True), request)


def _apply_config(data: dict, request: Request = None) -> dict:
    """一份配置写入的唯一通路：校验、落盘、副作用、日志都在这儿。
    `POST /api/config` 与 `POST /api/config/reset` 共用，所以「恢复默认」走的是同一条闸门，
    不是另一套宽松写法。"""
    if not data:
        # 一项都没交就别落盘、也别在日志里记一句「0 项变更」：那是空请求，不是改动
        return {"ok": True, "data": cfg.data, "ydl_arg_notes": []}
    if any(k.startswith("web_auth_") for k in data) and request is not None and _auth_token_only(request):
        # 令牌是「让自动脚本能读能写下载」的，不该顺手把这道门本身关掉或改口径
        raise HTTPException(403, "机器令牌只开数据接口：改访问保护的设置要从界面登录")
    from voice_tools import DEMUCS_MODELS, ROFORMER_MODELS, SEPARATION_DEVICES
    for k, allowed, label in (("video_encoder", VIDEO_ENCODER_MODES, "视频编码器"),
                              ("video_cpu_codec", VIDEO_CPU_CODECS, "CPU 编码器"),
                              ("video_cpu_preset", VIDEO_CPU_PRESETS, "编码档位"),
                              # 分离这三项也上闸门：它们是直接拼进子进程命令行的参数，
                              # 存进配置的脏值迟早被喂给 demucs / separator_runner
                              ("vocal_engine", ("roformer", "demucs"), "分离引擎"),
                              ("ai_device", tuple(SEPARATION_DEVICES), "分离设备"),
                              ("roformer_model", tuple(m["id"] for m in ROFORMER_MODELS), "分离权重"),
                              ("demucs_model", tuple(DEMUCS_MODELS), "Demucs 模型")):
        if k in data:
            v = str(data[k] or "").strip().lower()
            if v not in allowed:
                raise HTTPException(400, f"{label}只认 {' / '.join(allowed)}，收到的是「{str(data[k])[:24]}」")
            data[k] = v
    if "concurrent" in data:
        data["concurrent"] = max(1, min(10, int(data["concurrent"])))
        queue.max_concurrent = data["concurrent"]
    for k, lo, hi, label in (("web_auth_session_hours", 1, 720, "会话空闲时长（小时）"),
                             ("web_auth_remember_days", 1, 365, "记住设备天数"),
                             ("web_auth_max_fails", 1, 50, "连错几次就锁"),
                             ("web_auth_lock_minutes", 1, 1440, "锁定时长（分钟）")):
        if k in data:
            try:
                v = int(data[k])
            except (TypeError, ValueError):
                raise HTTPException(400, f"{label}要写整数，收到的是「{str(data[k])[:16]}」")
            if not lo <= v <= hi:
                raise HTTPException(400, f"{label}只能写 {lo}～{hi}，现在是 {v}")
            data[k] = v
    if data.get("web_auth_enabled"):
        # 先设口令再开开关：口令还没设就开保护，非本机的连接会谁也登不进来，等于自己把门锁死
        if not _auth_password_set():
            raise HTTPException(400, "先在「访问保护」里设好访问口令，再打开这个开关")
        # 改这几项不该静默生效：把当下的会话时长/锁定口径记一行，出问题时日志里能看到是哪一轮改的
        sess_hours = data.get('web_auth_session_hours', cfg.data.get('web_auth_session_hours'))
        max_fails = data.get('web_auth_max_fails', cfg.data.get('web_auth_max_fails'))
        lock_minutes = data.get('web_auth_lock_minutes', cfg.data.get('web_auth_lock_minutes'))
        log_mgr.log(f"访问保护已开启：非本机连接要登录，会话空闲 {sess_hours} 小时"
                    f"，连错 {max_fails} 次锁 {lock_minutes} 分钟",
                    k="srv.auth.enabled", kv={"h": sess_hours, "n": max_fails, "m": lock_minutes})
    if "torrent_seed_ratio" in data:
        # 做种参数直接决定 aria2 什么时候停上传：负值会让任务一建好就被判「已达标」而立刻停种
        data["torrent_seed_ratio"] = max(0.0, min(20.0, float(data["torrent_seed_ratio"])))
    if "torrent_seed_time" in data:
        data["torrent_seed_time"] = max(0, min(604800, int(data["torrent_seed_time"])))
    if "torrent_meta_timeout" in data:
        data["torrent_meta_timeout"] = max(30, min(1800, int(data["torrent_meta_timeout"])))
    if "bt_tracker_max" in data:
        # announce 是串行问的，条数没有上限会把「等元数据」拖到几十秒；0 表示不注入
        data["bt_tracker_max"] = max(0, min(200, int(data["bt_tracker_max"])))
    if "live_max_minutes" in data:
        # 0 = 不限时长，和每房间设置同一口径；上限也用它，超出的值到了录制那边也会被截断
        data["live_max_minutes"] = max(0, min(_LIVE_MAX_MINUTES, int(data["live_max_minutes"])))
    if "bt_auto_rules" in data:
        # 规则是「一条名字决定一批文件落到哪」的东西：写歪一条就把整批下载带偏，所以当场核对、不默默收下
        cleaned, bad = bt_rules_clean(data["bt_auto_rules"])
        if bad:
            raise HTTPException(400, "自动分类规则存不下：" + "；".join(bad[:5]))
        if len(cleaned) > 50:
            raise HTTPException(400, f"自动分类规则最多 50 条，现在有 {len(cleaned)} 条")
        data["bt_auto_rules"] = cleaned
    if "bt_auto_fallback" in data:
        fb, fb_why = bt_rule_subdir(data["bt_auto_fallback"])
        if fb_why:
            raise HTTPException(400, "自动分类的「都不命中时存到」存不下：" + fb_why)
        data["bt_auto_fallback"] = fb
    for k in ("bt_trackers", "bt_tracker_sources"):
        if k in data:
            # 只留文本本身，解析放在用的时候：填了非法行不该让整份设置存不下去
            data[k] = str(data[k] or "")[:20000]
    for k in ("bt_dl_limit", "bt_ul_limit"):
        if k in data:
            raw = str(data[k] or "").strip().upper()
            got = bt_trackers.norm_speed(raw)
            if raw and not got:
                raise HTTPException(400, f"{k} 要写成 1M / 512K / 纯字节数（空=不限），现在收到的是「{raw[:24]}」")
            data[k] = got
    if "speed_windows" in data:
        # 时段写歪等于悄悄不限速，用户看不出来：当场逐行核对，不默默收下
        rows, bad = parse_speed_windows(str(data["speed_windows"] or ""))
        if bad:
            raise HTTPException(400, "限速时段存不下：" + "；".join(bad[:5]))
        if len(rows) > 30:
            raise HTTPException(400, f"限速时段最多 30 行，现在有 {len(rows)} 行")
        data["speed_windows"] = str(data["speed_windows"] or "")[:4000]
    if "run_window" in data:
        rows, bad = parse_run_windows(str(data["run_window"] or ""))
        if bad:
            raise HTTPException(400, "队列定时窗存不下：" + "；".join(bad[:5]))
        data["run_window"] = "\n".join(f"{a}-{b}" for a, b in rows)[:2000]
    if "queue_windows" in data:
        # 队列名是用户自己起的：认不出来的名字当场顶回去，否则存进去一条永远对不上任何任务的窗，
        # 表现就是「设了没用」，界面上还看不出来
        raw_map = data["queue_windows"] or {}
        if not isinstance(raw_map, dict):
            raise HTTPException(400, '队列定时窗要写成 {"night": "22:00-06:00"} 这样一张表')
        known = set(cfg.data.get("named_queues") or []) | KNOWN_QUEUE_NAMES | set(queue.queue_names())
        cleaned: dict = {}
        errs: List[str] = []
        for k, v in raw_map.items():
            name = str(k or "").strip()
            text = str(v or "").strip()
            if not name or not text:
                continue
            if name not in known:
                errs.append(f"没有这条命名队列「{name[:20]}」")
                continue
            rows, bad = parse_run_windows(text)
            if bad:
                errs.append(f"「{name}」" + "；".join(bad[:2]))
                continue
            cleaned[name] = "\n".join(f"{a}-{b}" for a, b in rows)
        if errs:
            raise HTTPException(400, "队列定时窗存不下：" + "；".join(errs[:5]))
        data["queue_windows"] = cleaned
    if "bt_prioritize_piece" in data:
        data["bt_prioritize_piece"] = bool(data["bt_prioritize_piece"])
    if "clipboard_watch" in data:
        # 只把「开 / 关」记一行，读到的内容一个字都不落日志 —— 这行是给事后追责用的：
        # 谁在什么时候开始让程序盯剪贴板，应该看得出来，但盯到了什么不该留在盘上。
        on = bool(data["clipboard_watch"])
        if on != bool(cfg.data.get("clipboard_watch")):
            log_mgr.log("剪贴板监听已打开：发现链接只在界面上问一句，加入 / 忽略由你决定" if on
                        else "剪贴板监听已关闭：程序不再读系统剪贴板")
        data["clipboard_watch"] = on
    if "proxy_mode" in data:
        data["proxy_mode"] = (
            data["proxy_mode"] if data["proxy_mode"] in PROXY_MODES else "auto"
        )
    if "ui_theme" in data:
        data["ui_theme"] = data["ui_theme"] if data["ui_theme"] in UI_THEMES else "blue"
    if "ui_language" in data:
        data["ui_language"] = data["ui_language"] if data["ui_language"] in UI_LANGUAGES else "auto"
    if "proxy_by_platform" in data:
        data["proxy_by_platform"] = {
            str(k): v for k, v in (data["proxy_by_platform"] or {}).items() if isinstance(v, bool)
        }
    if "music_quality_spec" in data:
        # 存进去之前先清洗一遍：界面传来一个非法档位就得当场退回「不限」，
        # 否则会一直留着，之后每一批都按那个坏值判
        from music_search import norm_quality_spec
        data["music_quality_spec"] = norm_quality_spec(data["music_quality_spec"])
    if "ffmpeg_path" in data:
        ffmpeg_mgr.manual_path = (data["ffmpeg_path"] or "").strip()
    ydl_arg_notes: List[str] = []
    if "ytdlp_extra_args" in data:
        # 参数串照旧存下来（被挡掉的项也保留，用户改回原样就不用重打），但要告诉界面哪几项没生效
        data["ytdlp_extra_args"] = str(data["ytdlp_extra_args"] or "").strip()[:2000]
        if data["ytdlp_extra_args"]:
            ydl_arg_notes = _ydl_extra_opts(data["ytdlp_extra_args"])[1]
    cfg.data.update(data)
    cfg.save()
    if any(k in data for k in COOKIE_LAYER_KEYS):
        drop_all_cookie_prefs()
    # 只记变更项数量：配置值里有 Bot Token / Secret / Cookie 等敏感内容，一律不落日志
    log_mgr.log(f"[界面] 保存设置（{len(data)} 项变更）", k="log.settings_saved", kv={"n": len(data)})
    if "run_window" in data or "queue_windows" in data:
        # 改完窗立刻重新泵一次：刚被定时窗压住的排队任务该马上放出去，不该等下一条事件
        queue._pump()
    return {"ok": True, "data": cfg.data, "ydl_arg_notes": ydl_arg_notes}


# 这几项不是「一项设置」，是这门锁本身和它的钥匙：一键恢复默认绝不该顺手把它们抹掉
CONFIG_RESET_FORBIDDEN = ("secret_key", "web_auth_password_hash", "web_auth_machine_token",
                          "cookiecloud_key")
# 名字看着就像密钥的都别把值发出去（默认值表是给人对着看的，值本身不需要）
_CFG_SECRET_NAME_RE = re.compile(r"(?i)(key|token|secret|password|sendkey|passwd)")


def _cfg_copy(v):
    """默认值表里的表（dict / list）要拷一份再交给写入通路，别把 DEFAULTS 自己改脏。"""
    if isinstance(v, dict):
        return dict(v)
    if isinstance(v, list):
        return list(v)
    return v


# 这几项一恢复就把「指向这台机器」的东西抹了，和密钥一样：动手前值得留一份备份
CONFIG_RESET_BACKUP_KEYS = ("download_dir", "cookie_file", "cookie_source", "ffmpeg_path",
                             "aria2_bin", "platform_cookies")


def _cfg_backup_config() -> str:
    """给 config.json 留一份 .bak-<时间>，回的是文件名（没成或压根没这文件就回空串）。

    备份没成不该把恢复这件事整个卡住：那样用户看到的是「按钮按不动」，不如照常执行并把没留成备份记一行。
    """
    try:
        if not CONFIG_FILE.is_file():
            return ""
        dst = _edit_backup_path(CONFIG_FILE)
        shutil.copyfile(CONFIG_FILE, dst)
        return dst.name
    except OSError as e:
        log_mgr.log(f"[界面] 恢复默认前想留一份配置备份没成：{e}（恢复照常执行）", level="warning")
        return ""


def _cfg_defaultable() -> List[str]:
    """能默认、能恢复默认的键：既在 DEFAULTS 里，又在 ConfigBody 里声明过。

    只按 DEFAULTS 列会把界面根本写不进去的键也列出来，表现就是「点了恢复默认，什么都没发生」
    —— ConfigBody 没声明的键在 model_dump 那一步就掉了，这条线必须有断言钉着。
    """
    fields = set(ConfigBody.model_fields)
    return [k for k in cfg.DEFAULTS if k in fields and k not in CONFIG_RESET_FORBIDDEN]


@app.get("/api/config/defaults")
def api_config_defaults():
    """默认值表，连同每一项现在和默认差在哪。密钥类只报「已填」，值不发出去。"""
    cur = _auth_config_mask(cfg.data)
    items = []
    for k in _cfg_defaultable():
        d = cfg.DEFAULTS.get(k)
        v = cur.get(k, d)
        secret = bool(_CFG_SECRET_NAME_RE.search(k))
        same = v == d
        items.append({"key": k, "default": "" if secret else d, "value": "" if secret else v,
                      "secret": secret, "filled": bool(str(v or "").strip()) if isinstance(d, str) else True,
                      "differs": not same})
    return {"ok": True, "items": items, "count": len(items),
            "differs": sum(1 for i in items if i["differs"]),
            "forbidden": list(CONFIG_RESET_FORBIDDEN)}


class ConfigResetBody(BaseModel):
    keys: Optional[List[str]] = None
    all: bool = False


@app.post("/api/config/reset")
def api_reset_config(body: ConfigResetBody, request: Request = None):
    """把指定几项（或所有能默认的都）拧回 DEFAULTS 里的值，走的还是 `_apply_config` 那条闸门。"""
    if request is not None and _auth_token_only(request):
        raise HTTPException(403, "机器令牌只开数据接口：把设置拧回默认要从界面登录")
    allowed = set(_cfg_defaultable())
    want = [str(k) for k in (body.keys or []) if str(k)]
    if body.all:
        want = [i["key"] for i in api_config_defaults()["items"] if i["differs"]]
    if not want:
        raise HTTPException(400, "没说要恢复哪一项")
    bad = [k for k in want if k not in allowed]
    ok_keys = [k for k in want if k in allowed]
    if not ok_keys:
        raise HTTPException(400, "这几项恢复不了：" + " / ".join(
            f"{k}（{'这门锁本身，不在默认值表里' if k in CONFIG_RESET_FORBIDDEN else '界面写不进去的键'}）"
            for k in bad[:6]))
    # 恢复默认会把密钥、指向本机路径这类「界面上回不去」的值一起抹掉，动手前先留一份 config.json.bak-<时间>。
    # 命名照字幕编辑台那套（同目录、同一秒加序号），按龄清理的「编辑备份」那一组本来就收这种文件，不会堆到天荒地老。
    backup = ""
    if len(ok_keys) > 1 or any(_CFG_SECRET_NAME_RE.search(k) or k in CONFIG_RESET_BACKUP_KEYS
                               for k in ok_keys):
        backup = _cfg_backup_config()
    data = {k: _cfg_copy(cfg.DEFAULTS.get(k)) for k in ok_keys}
    out = _apply_config(data, request)
    names = " / ".join(ok_keys[:6]) + ("…" if len(ok_keys) > 6 else "")
    log_mgr.log(f"[界面] 恢复默认：{len(ok_keys)} 项（{names}）"
                + (f"，改动前的配置留在 {backup}" if backup else "")
                + (f"，另有 {len(bad)} 项没动（不在可默认名单里）" if bad else ""))
    out["restored"] = ok_keys
    out["refused"] = bad
    out["backup"] = backup
    return out


@app.post("/api/config/speed_windows/check")
def api_speed_windows_check(body: dict):
    """限速时段格式体检：列出认出的档位和逐行报错，并说明此刻会命中哪一档。这一步不写配置。"""
    raw = (body or {}).get("text")
    if raw is None:
        raw = cfg.data.get("speed_windows") or ""
    raw = str(raw)
    rows, bad = parse_speed_windows(raw)
    sl, note = resolve_speed_limit({**cfg.data, "speed_limit": "", "speed_windows": raw})
    return {"ok": not bad, "count": len(rows),
            "rows": [{"span": f"{a}-{b}", "speed": s, "label": lab} for a, b, s, lab in rows],
            "errors": bad[:20], "now": datetime.now().strftime("%H:%M"),
            "current": sl, "current_note": note}


@app.post("/api/config/run_window/check")
def api_run_window_check(body: dict):
    """定时窗格式体检：认出哪些时段、这一刻开不开门、下一次几点开门。这一步不写配置。"""
    raw = (body or {}).get("text")
    if raw is None:
        raw = cfg.data.get("run_window") or ""
    raw = str(raw)
    rows, bad = parse_run_windows(raw)
    is_open, note, nxt, left = window_open(raw)
    return {"ok": not bad, "count": len(rows),
            "rows": [{"span": f"{a}-{b}"} for a, b in rows],
            "errors": bad[:20], "now": datetime.now().strftime("%H:%M"),
            "open": is_open, "note": note, "resume_at": nxt, "wait_minutes": left,
            "live": queue.window_status()}


# 设置页「按平台代理」表要列出的音乐源（其余源走默认档，不逐个列）
NET_MUSIC_SOURCES = {
    "NeteaseMusicClient": "网易云",
    "QQMusicClient": "QQ 音乐",
    "KugouMusicClient": "酷狗",
    "MiguMusicClient": "咪咕",
    "AppleMusicClient": "Apple Music",
    "SpotifyMusicClient": "Spotify",
}


def net_policy_rows(cfg_data: dict = None) -> List[dict]:
    d = cfg.data if cfg_data is None else cfg_data
    items = [(k, PLATFORM_LABELS.get(k, k)) for k, _ in PLATFORM_RULES]
    items.append(("tiktok", "TikTok"))
    items.append(("default", "其它未识别站点"))
    items += [(s, label) for s, label in NET_MUSIC_SOURCES.items()]
    rows = []
    for key, label in items:
        m, px = _decide_by_key(key, d)
        rows.append({
            "key": key,
            "label": label,
            "verdict": m,                 # proxy / direct / inherit
            "proxy": px,
            "override": proxy_needs_override(key, d),
            "needs_by_default": key in PROXY_NEEDED_PLATFORMS or key in PROXY_NEEDED_SOURCES,
        })
    return rows


def net_info_payload() -> dict:
    sp, src = system_proxy_detail()
    return {
        "ok": True,
        "proxy_mode": str(cfg.data.get("proxy_mode") or "auto"),
        "configured_proxy": (cfg.data.get("proxy") or "").strip(),
        "system_proxy": sp,
        "system_proxy_source": src,
        "platforms": net_policy_rows(),
    }


@app.get("/api/net/info")
def api_net_info():
    """代理现状：填了什么、系统有什么、每个平台这次怎么走。"""
    return net_info_payload()


@app.post("/api/net/use_system_proxy")
def api_net_use_system_proxy():
    """一键配置系统代理：把 OS 里已生效的代理填进设置并启用。"""
    sp, src = system_proxy_detail()
    if not sp:
        raise HTTPException(400, "没读到系统代理（系统设置里本来就没开，或只配了 SOCKS）")
    cfg.data["proxy"] = sp
    try:
        cfg.save()
    except Exception:
        pass
    log_mgr.log(f"已填入系统代理: {sp}（来源：{src}）",
                k="srv.net.system_proxy_filled", kv={"sp": sp, "src": src})
    return {"ok": True, "proxy": sp, "source": src, "data": net_info_payload()}


@app.post("/api/net/reset")
def api_net_reset():
    """清空/重置网络：只动代理地址、按平台代理策略和嗅探到的资源列表。

    Cookie、下载历史、任务记录都不在这里 —— 它们和网络无关，误清一次的代价比多清一次高得多。
    嗅探浏览器的 Chrome profile（可能存着登录态）同样保留，清的只是这次抓到的资源清单。
    """
    cleared: List[str] = []
    # 界面按 key 取词表（#92）：这两份是同一件事的两种写法，cleared 留给日志原话和老调用方
    cleared_keys: List[str] = []
    if (cfg.data.get("proxy") or "").strip():
        cleared.append("代理地址")
        cleared_keys.append("proxy")
    if cfg.data.get("proxy_by_platform"):
        cleared.append("按平台代理策略")
        cleared_keys.append("proxy_by_platform")
    cfg.data["proxy"] = ""
    cfg.data["proxy_by_platform"] = {}
    cfg.data["proxy_mode"] = "auto"
    try:
        cfg.save()
    except Exception:
        pass
    try:
        browser_sniffer.clear()
        cleared.append("嗅探到的资源列表")
        cleared_keys.append("sniffed_list")
    except Exception as e:
        log_mgr.log(f"清空嗅探浏览器 profile 失败: {e}", "warning",
                    k="srv.net.sniff_profile_clear_failed", kv={"e": str(e)})
    cleared_text = "、".join(cleared) if cleared else "本来就是空的"
    log_mgr.log(f"网络设置已重置：{cleared_text}", k="srv.net.reset", kv={"what": cleared_text})
    return {"ok": True, "cleared": cleared, "cleared_keys": cleared_keys,
            "data": net_info_payload()}


def download_preflight(urls: List[str], opts: dict) -> Tuple[List[str], List[str]]:
    """入队前的依赖与目录检查：注定办不成的单子当场回错，别等任务跑几分钟才报「下载失败」。

    只拦「缺了就一定办不成」的；只是会慢、会降质的写日志提示，不拦。
    """
    errs: List[str] = []
    warns: List[str] = []
    mt = [u for u in urls if u.lower().startswith("tgmt://")]
    bt = [u for u in urls if parse_torrent_ref(u)]
    plain = [u for u in urls if u not in mt and u not in bt]
    # 期望校验值：写法收不干净就当场回错 —— 带着它跑完几分钟再来一句「对不上」，
    # 那句既不是下载坏了也不是算法问题，只是复制漏了字符，但界面上看不出来源。
    want_hex, want_algo, hash_err = normalize_hash_expect(
        opts.get("expect_hash"), opts.get("hash_algo"))
    if hash_err:
        errs.append("「期望校验值」这一项没收进来：" + hash_err + "——改对了再入队，或留空（留空就是不核对）")
    opts["expect_hash"] = want_hex
    opts["hash_algo"] = want_algo
    if want_hex and plain:
        hv = dict(opts)
        hv["format"] = opts.get("format") or cfg.data.get("format") or "mkv"
        steps = hash_rewrite_steps(hv, "link")
        if steps:
            warns.append("这批里有链接下载：这一路还勾着「" + "、".join(steps)
                         + "」这几步，除非它按 CDN 直链原样落盘，成品会被本机重写一遍，"
                         "摘要与上游那份原文件本来就不会相同 —— 真对不上时先看卡片上那句说的是哪一种，"
                         "别直接当成下载坏了（磁力/种子与直链原样那种才是可比的）")
    if plain and "not found" in str(engine.check_ytdlp() or "").lower():
        errs.append("本机没有可用的 yt-dlp（解析各站点靠它）：到「设置 → 组件与依赖」点 yt-dlp 那行的「安装」，装好再入队")
    if plain and not ffmpeg_mgr.find(ffmpeg_mgr.manual_path):
        need = [name for name, flag in (
            ("嵌入字幕", opts.get("embed_sub")),
            ("写出外挂字幕文件", opts.get("write_sub_files") if opts.get("write_sub_files") is not None
             else cfg.data.get("write_sub_files")),
            ("嵌入封面", opts.get("embed_thumb")),
            ("写入音频/视频标签", opts.get("embed_meta")),
            ("嵌入章节", opts.get("embed_chapters")),
            ("按 SponsorBlock 剪片头", str(opts.get("sponsorblock") or "off") != "off"),
            ("封装成 mkv", str(opts.get("format") or "") == "mkv"),
            ("按时间点选段", bool(opts.get("download_section"))),
        ) if flag]
        if need:
            errs.append("没有可用的 FFmpeg，而这一单要" + "、".join(need)
                        + "，这些步骤都要它：到「设置 → 组件与依赖」点 FFmpeg 那行的「安装」；"
                          "或先把上述选项取消勾选（「封装成 mkv」需把下载页「画质 / 封装」换成 mp4）再入队")
        else:
            warns.append("没有可用的 FFmpeg：视频与音频分开发布的站点（如 YouTube）只能下到单条流，"
                         "画质会明显偏低，也无法合并转封装。可在「设置 → 组件与依赖」安装 FFmpeg")
    if opts.get("local_ai_transcribe"):
        w = whisper_status()
        if not (w.get("faster_whisper") or w.get("cli")):
            errs.append("勾选了「下载后本地转写」，但本机没有 faster-whisper：到「设置 → 组件与依赖」"
                        "点 faster-whisper 那行的「安装」（体积较大），或取消这个勾选再入队")
    if opts.get("use_hls_engine") and not find_n_m3u8dl():
        errs.append("勾选了「HLS 用专用引擎」，但没找到 N_m3u8DL-RE：到「设置 → 组件与依赖」"
                    "点 N_m3u8DL-RE 那行的「安装」，或取消这个勾选再入队")
    if mt:
        import importlib.util
        if importlib.util.find_spec("telethon") is None:
            errs.append("tgmt:// 链接要走 Telegram 账号会话下载，但本机没有 telethon："
                        "到「设置 → 组件与依赖」点 telethon 那行的「安装」再入队")
    if bt:
        # 磁力/种子完全靠 aria2：起不来就一定办不成，当场说清缺什么（需要时按设置自己拉一个本机进程）
        for u in bt:
            ref = parse_torrent_ref(u) or {}
            if ref.get("kind") == "torrent-file" and not Path(str(ref.get("path") or "")).is_file():
                errs.append(f"种子文件不存在：{ref.get('path')}")
        ok_aria, why = bt_ensure(dict(cfg.data), log_mgr.log)
        if not ok_aria:
            errs.append("磁力/种子任务要靠本机 aria2，现在连不上：" + why)
    d = str(opts.get("download_dir") or cfg.data.get("download_dir") or "").strip()
    if d:
        try:
            p = Path(d).expanduser()
            p.mkdir(parents=True, exist_ok=True)
            probe = p / ".md_write_probe"
            probe.write_text("1", encoding="utf-8")
            probe.unlink(missing_ok=True)
        except Exception as e:
            errs.append(f"下载目录写不进去：{d}（{type(e).__name__}: {str(e)[:120]}）"
                        "——换个目录或确认该磁盘还在")
    return errs, warns


@app.post("/api/download")
def api_download(body: AddUrlsBody):
    raw = [u.strip() for u in body.urls if u and u.strip()]
    bt_ok = [u for u in raw if parse_torrent_ref(u)]
    bt_bad = [u for u in raw
              if (u.lower().startswith("magnet:") or u.lower().startswith("file://")) and u not in bt_ok]
    if bt_bad:
        msgs = "；".join(dict.fromkeys(torrent_reject_reason(u) for u in bt_bad if torrent_reject_reason(u)))
        log_mgr.log(f"入队前检查未通过（任务没有创建）：{msgs}", "error",
                    k="srv.download.precheck_failed", kv={"why": msgs})
        raise HTTPException(400, "入队前检查未通过：" + msgs)
    urls = [u for u in raw if u.startswith("http") or u.lower().startswith("tgmt://") or u in bt_ok]
    skipped = len(raw) - len(urls)
    if not urls:
        raise HTTPException(400, "请提供有效 URL")
    opts = body.model_dump()
    errs, warns = download_preflight(urls, opts)
    for msg in warns:
        log_mgr.log(msg, "warning")
    if errs:
        log_mgr.log(f"入队前检查未通过（任务没有创建）：{'；'.join(errs)}", "error",
                    k="srv.download.precheck_failed", kv={"why": "；".join(errs)})
        raise HTTPException(400, "入队前检查未通过：" + "；".join(errs))
    # 自定义 yt-dlp 参数入队前先核对一遍：被挡掉的项当场回给界面，别等任务跑起来才在日志里发现
    arg_text = str(opts.get("ytdlp_extra_args") or cfg.data.get("ytdlp_extra_args") or "").strip()
    arg_notes: List[str] = []
    if arg_text:
        _arg_delta, arg_notes = _ydl_extra_opts(arg_text)
        for _n in arg_notes:
            log_mgr.log(f"自定义 yt-dlp 参数：{_n}", "warning",
                        k="srv.download.ytdlp_args", kv={"note": _n})
    if body.is_live:
        # 录制时长上限只对直播生效：负数当作「不限」，过大的值截到上限，与每房间设置同一口径
        try:
            lm = int(opts.get("live_max_minutes") or 0)
        except (TypeError, ValueError):
            lm = 0
        opts["live_max_minutes"] = max(0, min(_LIVE_MAX_MINUTES, lm))
    ids = queue.add_urls(urls, opts)
    merged = max(0, len(urls) - len(ids))
    log_mgr.log(f"加入 {len(ids)} 个任务" + (f"（合并 {merged} 条重复）" if merged else "")
                + (f"（忽略 {skipped} 条无效链接）" if skipped else ""))
    return {"ok": True, "ids": ids, "added": len(ids), "merged": merged, "skipped": skipped,
            "arg_notes": arg_notes}


@app.get("/api/tasks")
def api_tasks(sort: str = "queue"):
    return {
        "tasks": queue.list_tasks(sort_by=sort or "queue"),
        "running": queue.running,
        "paused": queue.paused,
        "pending": len(queue.pending),
        "window": queue.window_status(),
    }


class IdsBody(BaseModel):
    """一组任务号。必须定义在第一个用到它的路由之前：注解是字符串，FastAPI 在装饰那一刻解析，
    晚定义会把请求体降级成查询参数——必填的当场报「缺参数」，选填的则永远收到 None。"""

    ids: List[str] = []


@app.post("/api/tasks/pin")
def api_tasks_pin(body: IdsBody):
    queue.pin_tasks(body.ids or [], pinned=True)
    return {"ok": True, "tasks": queue.list_tasks()}


@app.post("/api/tasks/unpin")
def api_tasks_unpin(body: IdsBody):
    queue.pin_tasks(body.ids or [], pinned=False)
    return {"ok": True, "tasks": queue.list_tasks()}


@app.post("/api/tasks/top")
def api_tasks_top(body: IdsBody):
    """任务置顶并提到队列最前"""
    queue.move_to_top(body.ids or [])
    return {"ok": True, "tasks": queue.list_tasks()}


@app.post("/api/tasks/later")
def api_tasks_later(body: IdsBody):
    """稍后下载"""
    queue.set_later(body.ids or [], later=True)
    return {"ok": True, "tasks": queue.list_tasks()}


@app.post("/api/tasks/start-later")
def api_tasks_start_later(body: IdsBody):
    """将「稍后」任务重新加入队列"""
    queue.set_later(body.ids or [], later=False)
    return {"ok": True, "tasks": queue.list_tasks()}


class ReorderBody(BaseModel):
    ids: List[str] = []


@app.post("/api/tasks/reorder")
def api_tasks_reorder(body: ReorderBody):
    queue.reorder_pending(body.ids or [])
    return {"ok": True, "tasks": queue.list_tasks()}


@app.post("/api/stop")
def api_stop():
    queue.stop_all()
    log_mgr.log("已停止全部下载", "warning", k="srv.queue.stop_all")
    return {"ok": True}


@app.post("/api/live/end")
def api_live_end(body: IdsBody = None):
    """结束指定或全部直播录制任务（保留已录文件并收尾 .part）"""
    ids = (body.ids if body else None) or []
    n = queue.end_live_tasks(ids if ids else None)
    if n:
        log_mgr.log(f"已结束 {n} 个直播录制任务", k="srv.live.end_tasks", kv={"n": n})
    # 额外再扫一遍下载目录，防止漏网 .part
    try:
        out_dir = str(cfg.data.get("download_dir") or DEFAULT_DOWNLOAD_DIR)
        finalize_part_files(out_dir, hint="", log=log_mgr.log)
    except Exception:
        pass
    return {"ok": True, "count": n}


@app.post("/api/files/finalize-parts")
def api_finalize_parts():
    """手动把下载目录里的 .part 收成可播放文件"""
    out_dir = str(cfg.data.get("download_dir") or DEFAULT_DOWNLOAD_DIR)
    done = finalize_part_files(out_dir, hint="", log=log_mgr.log)
    return {"ok": True, "files": done, "count": len(done)}


@app.get("/api/plugins")
def api_plugins_list():
    return {"plugins": list_url_plugins(), "dir": str(PLUGINS_DIR)}


@app.post("/api/plugins/reload")
def api_plugins_reload():
    mods = load_url_plugins(force=True)
    log_mgr.log(f"插件热加载: {len(mods)} 个", k="srv.plugin.reload", kv={"n": len(mods)})
    return {"ok": True, "count": len(mods), "plugins": list_url_plugins()}


@app.post("/api/tasks/edit")
def api_tasks_edit(body: dict):
    """
    中途改任务 URL / Header / 代理等。
    body: id, url?, headers? (dict), referer?, cookie?, user_agent?, proxy?,
          use_hls_engine?, direct_cdn?, restart? (默认 true：失败或进行中则重排队)
    """
    tid = (body.get("id") or body.get("task_id") or "").strip()
    if not tid or tid not in queue.tasks:
        raise HTTPException(404, "任务不存在")
    t = queue.tasks[tid]
    opts = dict(getattr(t, "_opts", {}) or {})
    if body.get("url"):
        t.url = str(body["url"]).strip()
    if isinstance(body.get("headers"), dict):
        h = dict(opts.get("http_headers") or {})
        h.update({str(k): str(v) for k, v in body["headers"].items() if v is not None})
        opts["http_headers"] = h
    for k in ("referer", "cookie", "user_agent", "proxy"):
        if body.get(k) is not None:
            opts[k] = str(body[k]).strip()
    for k in ("use_hls_engine", "direct_cdn", "aria2_enabled"):
        if k in body:
            opts[k] = bool(body[k])
    t._opts = opts  # type: ignore
    restart = body.get("restart", True)
    applied = "saved"
    if restart and t.status in (
        TaskStatus.FAILED.value,
        TaskStatus.STOPPED.value,
        TaskStatus.PAUSED.value,
        TaskStatus.DOWNLOADING.value,
        TaskStatus.FINISHED.value,
    ):
        # 进行中：停止后重入队（yt-dlp 进程无法无缝改 Header，需重启任务）
        if t.status == TaskStatus.DOWNLOADING.value:
            try:
                queue.engine.stop(tid)
            except Exception:
                pass
            t.status = TaskStatus.STOPPED.value
        queue.retry_one(tid, extra_opts=opts)
        applied = "restarted"
    log_mgr.log(f"[{tid[:8]}] 任务参数已更新 ({applied})",
                k="srv.tasks.params_updated", kv={"tid": tid[:8], "what": applied})
    return {"ok": True, "applied": applied, "opts_keys": list(opts.keys())}


@app.post("/api/retry-one")
def api_retry_one(body: dict):
    """重试任务；可选 refresh_cookie / use_hls_engine / direct_cdn / proxy。"""
    if isinstance(body, dict):
        ids = body.get("ids") or []
        tid = ids[0] if ids else body.get("id")
        extra = {
            k: body[k]
            for k in (
                "use_hls_engine",
                "direct_cdn",
                "proxy",
                "cookie_source",
                "aria2_enabled",
            )
            if k in body
        }
    else:
        tid = (getattr(body, "ids", None) or [None])[0]
        extra = {}
    if not tid:
        raise HTTPException(400, "缺少任务 id")
    ok = queue.retry_one(str(tid), extra_opts=extra or None)
    if not ok:
        raise HTTPException(400, "无法重试该任务（状态不允许）")
    return {"ok": True, "extra": extra}


@app.post("/api/cleanup-parts")
def api_cleanup_parts():
    """清理下载目录中的未完成 .part / .ytdl 临时文件"""
    root = Path(cfg.data.get("download_dir") or DEFAULT_DOWNLOAD_DIR).resolve()
    if not root.exists():
        return {"ok": True, "removed": 0}
    removed = 0
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        name = p.name.lower()
        if name.endswith(".part") or name.endswith(".ytdl") or name.endswith(".temp"):
            try:
                p.unlink()
                removed += 1
            except Exception:
                pass
    return {"ok": True, "removed": removed}


@app.get("/api/history/export")
def api_history_export():
    """导出历史为 CSV 文本"""
    rows = history_mgr.get("")
    lines = ["time,title,status,url,filepath"]
    for h in rows:
        def esc(s):
            s = str(s or "").replace('"', '""')
            return f'"{s}"'
        lines.append(
            ",".join(esc(h.get(k, "")) for k in ("time", "title", "status", "url", "filepath"))
        )
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse("\n".join(lines), media_type="text/csv; charset=utf-8")


@app.post("/api/retry")
def api_retry():
    queue.retry_failed()
    return {"ok": True}


class BrowseBody(BaseModel):
    mode: str = "folder"  # folder | file
    title: str = "选择"


@app.post("/api/pause")
def api_pause(body: IdsBody = None):
    body = body or IdsBody()
    if body.ids:
        queue.pause_tasks(body.ids)
    else:
        queue.pause_all()
    return {"ok": True, "paused": queue.paused}


@app.post("/api/resume")
def api_resume(body: IdsBody = None):
    body = body or IdsBody()
    if body.ids:
        queue.resume_tasks(body.ids)
    else:
        queue.resume_all()
    return {"ok": True, "paused": queue.paused}


@app.post("/api/tasks/delete")
def api_tasks_delete(body: IdsBody):
    ids = body.ids or []
    names = []
    for tid in ids:  # 任务马上就被删了，先取个能认出它是谁的名字
        t = queue.tasks.get(tid)
        if not t:
            continue
        names.append(" ".join((t.title or "").split())[:40] or url_host(t.url) or "未命名任务")
    queue.delete_tasks(ids)
    shown = "、".join(names[:5]) + ("…" if len(names) > 5 else "")
    log_mgr.log(f"[界面] 删除任务 {len(ids)} 个" + (f"：{shown}" if shown else ""))
    return {"ok": True}


@app.post("/api/browse")
def api_browse(body: BrowseBody = None):
    """本机运行时用系统对话框选择文件/文件夹（仅本地有效）"""
    body = body or BrowseBody()
    mode = (body.mode or "folder").lower()
    title = body.title or "选择"
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        if mode == "file":
            path = filedialog.askopenfilename(title=title)
        else:
            path = filedialog.askdirectory(title=title)
        root.destroy()
        return {"ok": True, "path": path or ""}
    except Exception as e:
        # 容器/服务器上没有桌面，弹不出选择框（python:slim 镜像甚至不带 tkinter 模块）。
        # 原先直接回一句 TclError 原文，界面看着像坏了；这里分档说明并给出替代动作。
        low = f"{type(e).__name__}: {e}".lower()
        if sys.platform != "win32" and ("display" in low or "tkinter" in low or "no module named" in low):
            raise HTTPException(503, "当前是无界面运行（容器/服务器没有桌面），无法弹出系统选择框：下载目录请直接在输入框里填写，例如 /data/Downloads")
        raise HTTPException(500, f"无法打开系统对话框: {e}")


@app.post("/api/clear-finished")
def api_clear_finished():
    n = sum(1 for t in queue.tasks.values() if t.status == TaskStatus.FINISHED.value)
    queue.clear_finished()
    log_mgr.log(f"[界面] 清除已完成任务（{n} 个）", "warning")
    return {"ok": True}


# 档位名与界面「视频画质 / 音频质量」的选项一一对应：
# 视频取 height<=上限里最高的分流，音频取码率<=上限里最高的分流，估出来的体积才对得上实际下到的流。
# 视频这边直接从 VIDEO_QUALITY_HEIGHTS 派生（原来是手抄一份，_resolve_format 一改这里就漂）。
_VIDEO_TIERS = (("best", 0),) + tuple(VIDEO_QUALITY_HEIGHTS.items())
_AUDIO_TIERS = (("best", 0), ("320k", 320), ("256k", 256), ("192k", 192), ("128k", 128))

# 编码族的展示顺序：AVC 兼容性最好放最前，4K 通常只有 VP9/AV1 分流
_CODEC_FAMILIES = (("AVC", "avc", ("avc", "h264")),
                   ("VP9", "vp9", ("vp9", "vp09")),
                   ("AV1", "av1", ("av01", "av1")),
                   ("HEVC", "hevc", ("hev", "h265", "hevc")),
                   ("VP8", "", ("vp8", "vp08")))


def _codec_family(vcodec) -> Tuple[str, str]:
    """返回 (展示名, _resolve_format 认的 prefer_codec 值)；认不出来给两个空串，让档位退回只写高度。"""
    vc = str(vcodec or "").lower()
    if not vc or vc == "none":
        return "", ""
    for label, pref, keys in _CODEC_FAMILIES:
        if any(k in vc for k in keys):
            return label, pref
    return "", ""


def _po_gate_tip(po: dict, cfg: dict) -> str:
    """PO Token 那一步的下一步该往哪走 —— 开关开没开、服务通不通、插件装没装是三件事。

    以前一律写成「启用 PO Token 服务」，可对方已经把开关打开了，看到的还是这句话，
    于是只能对着一个已经拧开的开关发呆。
    """
    c = cfg or {}
    url = str(c.get("po_provider_url") or PO_DEFAULT_URL)
    if not c.get("po_provider_enabled"):
        return ("打开「设置 → PO Token 服务门控」并填服务地址：4K/AV1 分流普遍要票，"
                "当前这个开关是关的，需要票的播放器客户端一律不试")
    plugin = "" if po.get("installed") else "，而且 yt-dlp 那边的 bgutil POT 插件也没装（票要靠它取）"
    return (f"PO Token 的开关已经打开，但 {url} 上没人应答（{po.get('detail') or '服务没响应'}）—— "
            f"造票的那个服务在 tools/{POT_SERVER_DIR_NAME}/ 里，程序探测到端口空着会拿本机 node 把它拉起来，"
            f"本机 PATH 没有 node 才起不来{plugin}；起不来时高清就退到「换网络出口 + 带 Cookie」")


def _yt_widen_attempt(cfg: dict) -> list:
    """被裁时值不值得再用 `all` 客户端解一次 —— 值得的前提是票取得到。

    10-13 实测，同一条 10-09 下过 AV1 8K 的视频（LTGkt3GrGNY）：
      票在  → all 回 38 条 / 最高 4320p / 独立视频轨 23 条（含 av01）
      票停  → all 掉回 11 条 / 1080p / 零分流
      default、web_safari、tv、tv_embedded、webclient → 两种情况下都只有 1080p 渐进流
    所以「票」和「会吃票的客户端」两样都要，缺一样高清就不在响应里 —— 光开开关不试 all
    看不到 4K，光试 all 没有票也看不到 4K。
    """
    try:
        c = cfg or {}
        if not c.get("po_provider_enabled"):
            return []
        return [list(YT_WIDE_CLIENTS)] if po_token_health(cfg_override=c).get("ok") else []
    except Exception:
        return []


def _yt_has_dash(formats: list) -> bool:
    """这份格式清单里有没有独立视频轨（DASH 分流）。没有 = 被裁成影音同条。"""
    return any((f.get("vcodec") or "none") != "none" and (f.get("acodec") or "none") == "none"
               for f in formats or [])


def _yt_max_h(formats: list) -> int:
    out = 0
    for f in formats or []:
        h = f.get("height") or 0
        if not h:
            # resolution 是 "1920x1080" 这种宽x高，取后半个；先匹配到的那个数是宽度
            m = re.search(r"\d{3,4}\s*[x×]\s*(\d{3,4})", str(f.get("resolution") or ""))
            h = int(m.group(1)) if m else 0
        out = max(out, int(h))
    return out


def _anon_list_clipped(info: dict, url: str) -> bool:
    """匿名那一次「算解析开了」吗 —— 只有 YouTube 需要额外这条判断。

    带不带 Cookie 在 YouTube 上是两条客户端链（Cookie 会让 yt-dlp 跳过 android/ios），
    所以一次「成功但只有 1080p 渐进流」的匿名清单不能被当成答案：那正是 1.3.2 修掉的那种
    静默降质，若照此收下并缓存 180 秒，用户点了 4K 只会拿到 1080p，还被判定为成功。
    有独立视频轨（DASH）就算这份清单是完整的；播放列表没有 formats，不参与这个判断。
    """
    if not info or not isinstance(info, dict):
        return True
    if info.get("_type") == "playlist" or "entries" in info:
        return False
    low = (url or "").lower()
    if not any(x in low for x in ("youtube.com", "youtu.be", "youtube-nocookie.com")):
        return False
    fmts = info.get("formats") or []
    if not fmts:
        return True
    return not _yt_has_dash(fmts)


def _pot_row_extra(row: dict, cfg: dict, po: Optional[dict] = None) -> dict:
    """给「组件与依赖」的 PO Token 那行补真实状态：装了插件不等于取得到票。"""
    if str(row.get("pkg") or "") != POT_PROVIDER_PKG:
        return row
    c = cfg or {}
    p = dict(po if isinstance(po, dict) else (po_token_health(cfg_override=c) or {}))
    # 门控关着时那份缓存里的 installed 可能是上次留下的旧值，插件层现查（一次 find_spec，很便宜）
    p["installed"] = _pot_plugin_installed()
    row["ok"] = bool(p.get("installed") and c.get("po_provider_enabled") and p.get("ok"))
    row["note"] = _pot_component_note(p, c)
    row["note_state"], row["note_kv"] = _pot_component_note_state(p, c)
    row["skip_all"] = True  # 「一键更新」不该在没跑服务端的机器上替人装插件
    return row


def _pot_component_note_state(po: dict, cfg: dict) -> tuple:
    """同一句 note 的语言无关状态码：前端按它取界面语言那句，后端 note 仍留中文原话。"""
    c = cfg or {}
    p = po or {}
    url = str(c.get("po_provider_url") or PO_DEFAULT_URL)
    if not p.get("installed"):
        return "install", {"dir": POT_SERVER_DIR_NAME}
    if not c.get("po_provider_enabled"):
        return "gate_off", {"url": url}
    if not p.get("ok"):
        return "no_server", {"url": url, "detail": str(p.get("detail") or "—"),
                             "dir": POT_SERVER_DIR_NAME}
    return "ready", {}


def _pot_component_note(po: dict, cfg: dict) -> str:
    """「组件与依赖」里 PO Token 那一行怎么解释自己 —— 插件和服务是两层，缺哪层说哪层。

    这一行点「安装」只装得到插件那层（pip 包）；服务端在 tools/ 里、要本机 node 才起得来，
    所以绿灯只在两层都通时亮。绿了之后要说清它换来的是什么（有票的客户端能解到分流），
    不要再说成「它不解决 4K」—— 10-13 实测正是这一层通了之后 4320p 才回到清单里。
    """
    c = cfg or {}
    p = po or {}
    url = str(c.get("po_provider_url") or PO_DEFAULT_URL)
    if not p.get("installed"):
        return ("这里点「安装」装的是插件层（pip 包）。服务端层在 tools/"
                f"{POT_SERVER_DIR_NAME}/ 里，程序会用本机 node 把它拉起来；"
                "两层都齐了这一行才转绿")
    if not c.get("po_provider_enabled"):
        return f"插件已装，但「设置 → PO Token 服务门控」是关的：关着就不去取票，{url} 通不通都一样"
    if not p.get("ok"):
        return (f"插件已装，缺的是服务端：{url} 上没人应答（{p.get('detail') or '服务没响应'}）—— "
                f"程序会拿本机 node 起 tools/{POT_SERVER_DIR_NAME}/，本机 PATH 里没有 node 就起不来")
    return ("插件和服务两层都通了，票取得到。4K 要「票 + 会吃票的客户端（all）」两样一起，"
            "清单被裁成影音同条时解析会自动换成 all 重解一遍")


def _po_ready_tip(po: dict, cfg: dict) -> str:
    """PO Token 那一层没问题、高清却仍不在清单里时的说法。

    别让人对着风控提示又回去拧那个已经开好的开关 —— 这一层不缺，缺的要说清是哪一层。
    """
    url = str((cfg or {}).get("po_provider_url") or PO_DEFAULT_URL)
    return (f"PO Token 这一层是通的（插件已装，{url} 在线取票），带票的 all 客户端也已试过，"
            "清单里仍没有更高的档位 —— 这一次是真的只发到这儿了，可动的只有换网络出口 / 换 Cookie")


def _format_gate_note(platform: str, formats: list, clients, cfg: dict, url: str = "") -> dict:
    """YouTube 只回渐进流时的「格式被上游裁剪」判定。

    4K/1440p 在 YouTube 上只有 DASH 分流（AV1/VP9），风控拦下时响应里一条分流都没有，
    只剩 itag 137 以下的 mp4 渐进流，最高 1080p。界面必须把这件事说清楚，否则用户以为
    是本程序把高清过滤掉了。
    """
    if str(platform or "").lower() != "youtube" or not formats:
        return {}
    videos = [f for f in formats if f.get("is_video")]
    if not videos:
        return {}
    separated = [f for f in videos if not f.get("has_audio")]
    max_h = max([int(f.get("height") or 0) for f in videos] or [0])
    if separated or max_h > 1080:
        return {}
    tips = []
    try:
        has_ck = bool(engine._cookie_source(cfg or {}, url)[0])
    except Exception:
        has_ck = False
    if not has_ck:
        tips.append("带 Cookie 再解析：设置 → Cookie → 「从浏览器读取」，或把 cookies.txt 放进 cookies\\")
    try:
        po = po_token_health(cfg_override=cfg) or {}
    except Exception:
        po = {}
    if not po.get("ok"):
        tips.append(_po_gate_tip(po, cfg or {}))
    else:
        tips.append(_po_ready_tip(po, cfg or {}))
    tips.append("换网络出口：同一个 IP 被 YouTube 计数后只发低清流，界面里的「更新 yt-dlp」也值得一并试")
    return {
        "limited": True,
        "max_height": max_h,
        "format_count": len(formats),
        "clients": list(clients or []),
        "text": (f"本次只拿到 {len(formats)} 条流，最高 {max_h}p，且全部是视频＋声音同一条的渐进流 —— "
                 "这是 YouTube 对这个出口做了风控（不是本程序把高清档过滤掉了）："
                 "1440p/4K 只走 DASH 分流，被拦时响应里根本不含这些流。"),
        "tips": tips,
    }


def _estimate_tier_sizes(formats):
    """每个画质/音质档位大概要下多少字节，供下载前对比体积。

    字节数取分流自带的 filesize，没有就取解析阶段按码率×时长算好的 filesize_est。
    音频行不含视频轨，前端按「分流是否自带声音」决定是否叠加。
    """
    def _rate(f):
        try:
            return float(f.get("tbr") or 0)
        except Exception:
            return 0.0

    def _size(f):
        return int(f.get("filesize") or f.get("filesize_est") or 0)

    videos = [f for f in formats if f.get("is_video") and int(f.get("height") or 0) > 0]
    # 只有渐进式（视频轨自带声音）的源没有纯音频分流，此时 ba/bestaudio 落到这些流上
    audios = [f for f in formats if f.get("is_audio")] or [f for f in formats if f.get("has_audio")]
    rows = []
    for tier, cap in _VIDEO_TIERS:
        # 上限之内一条都没有时 yt-dlp 的回退表达式会落到最高档，体积估算也跟着回退，
        # 这样界面列出来的数字才是真会下的量（并会因为体积相同被前端并成一档）
        cands = [f for f in videos if not cap or int(f.get("height") or 0) <= cap] or videos
        if not cands:
            continue
        pick = max(cands, key=lambda f: (int(f.get("height") or 0), _rate(f)))
        n = _size(pick)
        if n:
            rows.append({"kind": "video", "tier": tier, "bytes": n,
                         "has_audio": bool(pick.get("has_audio"))})
    for tier, cap in _AUDIO_TIERS:
        cands = [f for f in audios if not cap or (0 < _rate(f) <= cap)] or audios
        if not cands:
            continue
        n = _size(max(cands, key=_rate))
        if n:
            rows.append({"kind": "audio", "tier": tier, "bytes": n})
    return rows


@app.post("/api/analyze")
def api_analyze(body: AnalyzeBody):
    import time as _time

    t0 = _time.time()
    url = (body.url or "").strip()
    if not url.startswith("http"):
        raise HTTPException(400, "请提供有效 URL")
    info = engine.get_info(url, cfg.data)
    if not info:
        raise HTTPException(400, "解析失败：无法获取视频信息（可检查网络、Cookie 或更新 yt-dlp）")
    elapsed = f"{_time.time() - t0:.1f}"
    log_mgr.log(f"解析完成 {url[:60]} 耗时 {elapsed}s",
                k="srv.analyze.done", kv={"url": url[:60], "sec": elapsed})
    # 播放列表/合集
    if info.get("_type") == "playlist" or "entries" in info:
        entries = []
        for e in (info.get("entries") or [])[:200]:
            if not e:
                continue
            entries.append(
                {
                    "title": e.get("title") or "未命名",
                    "url": e.get("webpage_url") or e.get("url") or "",
                    "duration": e.get("duration_string") or str(e.get("duration") or ""),
                    "id": e.get("id") or "",
                }
            )
        return {
            "title": info.get("title") or "Playlist",
            "uploader": info.get("uploader") or info.get("channel") or "",
            "duration": "",
            "type": "playlist",
            "webpage_url": info.get("webpage_url") or body.url,
            "entries": entries,
            "formats": [],
            "thumbnail": info.get("thumbnail") or "",
        }
    return _analyze_single_formats(info, body.url)


def _quality_presets(formats: list) -> List[dict]:
    """按高度生成推荐清晰度档位，同一高度再按编码族拆开。

    只有一个族时补的那条「族名为空」的重复档位要去掉：界面上会出现两个「1080p」，
    点哪个下下来的都是同一条流，用户以为选了码率。
    """
    by_height: dict = {}
    for f in formats:
        h = int(f.get("height") or 0)
        if not f.get("is_video") or h <= 0:
            continue
        by_height.setdefault(h, []).append(f)
    presets = []
    for h, cands in by_height.items():
        # 同一清晰度优先用有真实 filesize 的 DASH/渐进流：单流可断点续传、比 HLS 分片快；
        # 只有 HLS 才提供该清晰度时（部分受限视频）再退回 m3u8
        cands.sort(
            key=lambda x: (
                1 if x.get("filesize") else 0,
                float(x.get("tbr") or 0) if x.get("tbr") != "" else 0,
            ),
            reverse=True,
        )
        fams: dict = {}
        for f in cands:
            fams.setdefault(_codec_family(f.get("vcodec"))[0], []).append(f)
        ordered = [lab for lab, _p, _k in _CODEC_FAMILIES if fams.get(lab)]
        ordered += [lab for lab in fams if lab and lab not in ordered]
        if not ordered:
            # 这一高度的编码族全认不出来（少见站点）：留一条不带族名的档位，别整个高度消失
            ordered = [""]
        show_codec = len(ordered) > 1
        for lab in ordered:
            f = (fams.get(lab) or cands)[0]
            fid = f.get("format_id") or ""
            if not fid:
                continue
            if f.get("has_audio"):
                fmt_expr = fid
            else:
                fmt_expr = f"{fid}+bestaudio/bestaudio/{fid}"
            presets.append({
                "label": f"{h}p · {lab}" if (show_codec and lab) else f"{h}p",
                "height": h,
                "format_id": fid,
                "format_expr": fmt_expr,
                "ext": f.get("ext") or "",
                "vcodec": f.get("vcodec") or "",
                "codec_family": lab or "",
                "prefer_codec": _codec_family(f.get("vcodec"))[1] or "auto",
                "tbr": f.get("tbr") or "",
                "filesize": f.get("filesize") or 0,
                "filesize_est": f.get("filesize_est") or 0,
            })
    _fam_order = {lab: i for i, (lab, _p, _k) in enumerate(_CODEC_FAMILIES)}
    presets.sort(key=lambda x: (-x["height"], _fam_order.get(x["codec_family"], 99)))
    # 最佳 / 仅音频
    presets.insert(0, {
        "label": "最佳画质",
        "height": 0,
        "format_id": "best",
        "format_expr": "bv*+ba/b",
        "ext": "",
        "vcodec": "",
        "codec_family": "",
        "prefer_codec": "auto",
        "tbr": "",
        "filesize": 0,
        "filesize_est": 0,
    })
    presets.append({
        "label": "仅音频",
        "height": -1,
        "format_id": "bestaudio",
        "format_expr": "ba/bestaudio",
        "ext": "m4a",
        "vcodec": "none",
        "codec_family": "",
        "prefer_codec": "auto",
        "tbr": "",
        "filesize": 0,
        "filesize_est": 0,
    })
    return presets


def _audio_abrs(formats: list) -> List[float]:
    """分流音频轨里真实存在的码率（降序 kbps），界面好告诉用户「320k 这档源里没有，会落到 X」。

    只有独立音轨才算：渐进流（影音同一条）的 tbr 里含画面码率，拿来当音质档位会显示成
    「3879 kbps」这种数，选了也没用。
    """
    got = sorted({
        float(f["tbr"]) for f in formats if f.get("is_audio")
        and isinstance(f.get("tbr"), (int, float)) and f["tbr"] > 0
    }, reverse=True)
    return [round(a, 1) for a in got[:8]]


def _analyze_single_formats(info: dict, url: str) -> dict:
    """单视频的解析结果：格式清单 + 画质/编码/音质三排选项都从这里来。"""
    formats = []
    try:
        dur_s = float(info.get("duration") or 0)
    except Exception:
        dur_s = 0.0
    for f in info.get("formats") or []:
        if not f:
            continue
        vcodec = f.get("vcodec")
        acodec = f.get("acodec")
        # None 是"提取器没报编码"（telegram:embed 就这样），不是"没有这条流"：
        # 当成 none 会把唯一的视频格式丢掉，解析面板就只剩空白
        if vcodec == "none" and acodec == "none":
            continue
        vcodec = vcodec or "unknown_video"
        acodec = acodec or "unknown_audio"
        height = f.get("height") or 0
        if not height:
            res0 = str(f.get("resolution") or "")
            m = re.search(r"(\d{3,4})", res0)
            if m:
                height = int(m.group(1))
        fid = f.get("format_id")
        tbr = f.get("tbr") or f.get("abr") or ""
        try:
            tbr = round(float(tbr), 1) if tbr != "" and tbr is not None else ""
        except Exception:
            tbr = str(tbr) if tbr is not None else ""
        formats.append(
            {
                "format_id": str(fid) if fid is not None else "",
                "ext": f.get("ext") or "",
                "resolution": f.get("resolution") or (f"{height}p" if height else ("未知" if vcodec != "none" else "audio")),
                "height": height or 0,
                "width": f.get("width") or 0,
                "fps": f.get("fps") or "",
                "vcodec": vcodec,
                "acodec": acodec,
                "tbr": tbr,
                "filesize": f.get("filesize") or f.get("filesize_approx") or 0,
                "filesize_est": 0 if (f.get("filesize") or f.get("filesize_approx"))
                else (int(float(tbr) * 125 * dur_s) if tbr != "" and dur_s else 0),
                "note": f.get("format_note") or f.get("format") or "",
                "protocol": (f.get("protocol") or "")[:24],
                "is_video": vcodec != "none",
                "is_audio": acodec != "none" and vcodec == "none",
                "has_audio": acodec != "none",
            }
        )
    formats.sort(key=lambda x: (x.get("height") or 0, float(x.get("tbr") or 0) if x.get("tbr") != "" else 0), reverse=True)

    quality_presets = _quality_presets(formats)
    audio_abrs = _audio_abrs(formats)

    return {
        "title": info.get("title"),
        "uploader": info.get("uploader") or info.get("channel"),
        "duration": info.get("duration_string") or str(info.get("duration", "")),
        "type": info.get("_type", "video"),
        "webpage_url": info.get("webpage_url") or url,
        "thumbnail": info.get("thumbnail") or "",
        "formats": formats[:120],
        "quality_presets": quality_presets,
        "tier_sizes": _estimate_tier_sizes(formats),
        "platform": detect_platform(info.get("webpage_url") or url),
        "audio_abrs": audio_abrs,
        "format_gate": _format_gate_note(
            detect_platform(info.get("webpage_url") or url),
            formats, info.get("_md_clients"), cfg.data,
            info.get("webpage_url") or url),
        "entries": [],
        "description": (info.get("description") or "")[:500],
    }


@app.get("/api/files")
def api_files(subdir: str = ""):
    """浏览下载目录文件（参考 MediaSync 文件管理）"""
    root = Path(cfg.data.get("download_dir") or DEFAULT_DOWNLOAD_DIR).resolve()
    root.mkdir(parents=True, exist_ok=True)
    target = (root / subdir).resolve() if subdir else root
    if not str(target).startswith(str(root)):
        raise HTTPException(400, "非法路径")
    if not target.exists():
        return {"root": str(root), "path": subdir, "items": []}
    items = []
    try:
        _hide_names = {
            "search_results.pkl", "download_results.pkl",
            "_musicdl_cache", "_preview", "__pycache__",
        }
        for p in sorted(target.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            if p.name.startswith("."):
                continue
            if p.name in _hide_names or p.suffix.lower() == ".pkl":
                continue
            if p.name.endswith(".pipeline.json"):
                continue
            st = p.stat()
            rel = str(p.relative_to(root)).replace("\\", "/")
            items.append(
                {
                    "name": p.name,
                    "path": rel,
                    "is_dir": p.is_dir(),
                    "size": st.st_size if p.is_file() else 0,
                    "mtime": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M"),
                    "ext": p.suffix.lower() if p.is_file() else "",
                }
            )
    except Exception as e:
        raise HTTPException(500, str(e))
    return {"root": str(root), "path": subdir.replace("\\", "/"), "items": items}


@app.get("/api/files/open")
def api_files_open(path: str):
    """打开/预览下载目录中的文件"""
    root = Path(cfg.data.get("download_dir") or DEFAULT_DOWNLOAD_DIR).resolve()
    target = (root / path).resolve()
    if not str(target).startswith(str(root)) or not target.is_file():
        raise HTTPException(404, "文件不存在")
    log_mgr.log(f"[文件] 打开：{target.name}")
    return FileResponse(target, filename=target.name)


class FilePathBody(BaseModel):
    path: str = ""


@app.post("/api/files/delete")
def api_files_delete(body: FilePathBody):
    root = Path(cfg.data.get("download_dir") or DEFAULT_DOWNLOAD_DIR).resolve()
    target = (root / body.path).resolve()
    if not str(target).startswith(str(root)):
        raise HTTPException(400, "非法路径")
    if not target.exists():
        raise HTTPException(404, "不存在")
    try:
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
        log_mgr.log(f"[文件] 已删除：{target.name}")
        return {"ok": True}
    except Exception as e:
        log_mgr.log(f"[文件] 删除失败：{target.name} —— {e}", "warning")
        raise HTTPException(500, str(e))


@app.post("/api/files/clear-archive")
def api_clear_archive():
    arch = Path(cfg.data.get("download_dir") or DEFAULT_DOWNLOAD_DIR) / "download_archive.txt"
    try:
        if arch.exists():
            arch.unlink()
        log_mgr.log("[文件] 已清空下载记录（download_archive.txt）", "warning")
        return {"ok": True, "path": str(arch)}
    except Exception as e:
        log_mgr.log(f"[文件] 清空下载记录失败：{e}", "warning")
        raise HTTPException(500, str(e))


@app.post("/api/open-folder")
def api_open_folder(body: FilePathBody = None):
    """在系统文件管理器中打开下载目录或指定子路径/文件所在文件夹"""
    body = body or FilePathBody()
    root = Path(cfg.data.get("download_dir") or DEFAULT_DOWNLOAD_DIR).resolve()
    p = (body.path or "").strip()
    if not p:
        target = root
    else:
        cand = Path(p)
        if cand.is_absolute():
            target = cand.resolve()
        else:
            target = (root / p).resolve()
    # 尽量打开目标文件夹；若路径不在根目录下也尝试打开其父目录（兼容历史记录绝对路径）
    folder = target if target.is_dir() else target.parent
    if not folder.exists():
        root.mkdir(parents=True, exist_ok=True)
        folder = root
    try:
        if sys.platform == "win32":
            os.startfile(str(folder))  # type: ignore
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(folder)])
        else:
            subprocess.Popen(["xdg-open", str(folder)])
        return {"ok": True, "path": str(folder)}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/test-cookie")
def api_test_cookie():
    """检测 Cookie 配置是否可用"""
    data = cfg.data
    src = (data.get("cookie_source") or "none").strip().lower()
    if src == "none":
        return {"ok": False, "message": "当前未启用 Cookie"}
    if src == "file":
        f = (data.get("cookie_file") or "").strip()
        if not f:
            return {"ok": False, "message": "未填写 Cookie 文件路径"}
        p = Path(f)
        if not p.exists():
            return {"ok": False, "message": f"文件不存在: {f}"}
        size = p.stat().st_size
        if size < 50:
            return {"ok": False, "message": f"文件过小({size}B)，可能无效"}
        return {"ok": True, "message": f"Cookie 文件可用（{size} 字节）"}
    if src == "browser":
        browser = (data.get("cookie_browser") or "chrome").strip()
        return {"ok": True, "message": f"将从浏览器读取: {browser}（实际有效性以下载结果为准）"}
    return {"ok": False, "message": "未知 Cookie 来源"}


class TelegramListBody(BaseModel):
    channel: str
    limit: int = 60
    types: Optional[List[str]] = None
    since: Optional[str] = None
    until: Optional[str] = None
    budget: Optional[int] = None
    page_sleep: Optional[float] = None


@app.post("/api/telegram/list")
def api_telegram_list(body: TelegramListBody):
    """公开频道批量：匿名翻 t.me/s/<频道> 历史，只列不下载。

    下载仍旧走 /api/download 逐条入队（每条帖子一个任务）—— telesco.pe 的直链
    带短时效 token，列表阶段抓下来的地址排队时就凉了，必须让 yt-dlp 现场重取。
    """
    from telegram_channel import ALL_TYPES, TYPE_LABELS, normalize_channel, list_channel_history

    ch = normalize_channel(body.channel)
    if not ch:
        raise HTTPException(400, "频道名无效：要 @名字 / t.me/名字 / t.me/s/名字 这种公开频道，"
                                "私有链接 t.me/c/… 匿名爬不了")
    types = [t for t in (body.types or []) if t in ALL_TYPES] or ["video"]
    limit = max(1, min(int(body.limit or 60), 2000))
    budget = max(10, min(int(body.budget or 240), 1800))
    sleep_s = max(0.0, min(float(body.page_sleep if body.page_sleep is not None else 0.8), 10.0))
    mode, px = proxy_decision("https://t.me/" + ch)
    # 空串在 requests 眼里是"不干预"，强制直连得用哨兵，否则照样被系统代理带走
    proxy = px if mode == "proxy" else (PROXY_DIRECT if mode == "direct" else "")
    items, diag = list_channel_history(
        ch,
        limit=limit,
        types=types,
        since=(body.since or "").strip(),
        until=(body.until or "").strip(),
        budget=budget,
        page_sleep=sleep_s,
        proxy=proxy,
        log=log_mgr.log,
    )
    return {
        "ok": True,
        "channel": ch,
        "items": items,
        "diag": diag,
        "proxy": {"mode": mode, "value": px if mode == "proxy" else ""},
        "type_labels": TYPE_LABELS,
    }


# -------------------- Telegram 用户会话（MTProto）：私有 / 需登录频道 --------------------
class TgmtConfigBody(BaseModel):
    api_id: Optional[str] = None
    api_hash: Optional[str] = None
    proxy: Optional[str] = None
    session_name: Optional[str] = None


class TgmtPhoneBody(BaseModel):
    phone: str


class TgmtSignInBody(BaseModel):
    code: str
    password: Optional[str] = ""


class TgmtListBody(BaseModel):
    channel: str
    limit: int = 100
    types: Optional[List[str]] = None
    since: Optional[str] = None
    until: Optional[str] = None
    budget: Optional[int] = None
    search: Optional[str] = None
    skip_seen: Optional[bool] = None


class TgmtAckBody(BaseModel):
    peer: str


def _tgmt_status() -> dict:
    from telegram_mt import NEED_CRED, NEED_LOGIN, NEED_TELETHON, PROTECTED_NOTE

    st = tg_session.status()
    st["ack"] = list(cfg.data.get("tgmt_ack") or [])
    st["skip_seen"] = bool(cfg.data.get("tgmt_skip_seen", True))
    st["has_hash"] = bool(str(cfg.data.get("tgmt_api_hash") or "").strip())
    st["api_id"] = str(cfg.data.get("tgmt_api_id") or "")
    st["session_name"] = str(cfg.data.get("tgmt_session_name") or "media_downloader")
    st["next_step"] = (
        NEED_TELETHON if not st["installed"]
        else NEED_CRED if not st["configured"]
        else NEED_LOGIN if not st["logged_in"]
        else ""
    )
    st["protected_note"] = PROTECTED_NOTE
    return st


@app.get("/api/telegram/mt/status")
def api_tgmt_status():
    return _tgmt_status()


@app.post("/api/telegram/mt/config")
def api_tgmt_config(body: TgmtConfigBody):
    """填 api_id / api_hash / 代理：改完必须重建客户端，所以先断开旧会话。"""
    changed = []
    if body.api_id is not None:
        cfg.data["tgmt_api_id"] = re.sub(r"\D", "", str(body.api_id))[:20]
        changed.append("api_id")
    if body.api_hash is not None:
        cfg.data["tgmt_api_hash"] = str(body.api_hash).strip()[:64]
        changed.append("api_hash")
    if body.proxy is not None:
        raw = str(body.proxy).strip()
        if raw and not re.fullmatch(r"(?:socks5h?://)?[\w.-]+:\d{2,5}", raw):
            raise HTTPException(400, "代理要么留空，要么写成 socks5 的 host:port（例如 127.0.0.1:7897）")
        cfg.data["tgmt_proxy"] = raw
        changed.append("proxy")
    if body.session_name is not None:
        cfg.data["tgmt_session_name"] = str(body.session_name).strip()[:40] or "media_downloader"
        changed.append("session_name")
    if not changed:
        return {"ok": True, "message": "没改动任何东西"}
    cfg.save()
    tg_session.reconnect()  # 换了凭据/代理，旧连接不能留（session 文件保留，不用重新登录）
    return {"ok": True, "message": f"已保存：{', '.join(changed)}", "status": _tgmt_status()}


@app.post("/api/telegram/mt/send-code")
def api_tgmt_send_code(body: TgmtPhoneBody):
    try:
        return tg_session.send_code(body.phone)
    except Exception as e:
        log_mgr.log(f"Telegram 发验证码失败: {e}", "warning")
        return {"ok": False, "message": str(e)}


@app.post("/api/telegram/mt/sign-in")
def api_tgmt_sign_in(body: TgmtSignInBody):
    if not str(body.code or "").strip():
        raise HTTPException(400, "要填收到的验证码")
    try:
        return tg_session.sign_in(body.code, body.password or "")
    except Exception as e:
        log_mgr.log(f"Telegram 登录失败: {e}", "warning")
        return {"ok": False, "message": str(e)}


@app.post("/api/telegram/mt/logout")
def api_tgmt_logout():
    return tg_session.logout()


@app.post("/api/telegram/mt/ack")
def api_tgmt_ack(body: TgmtAckBody):
    """记下「这个频道的限制保存内容我已经看过并确认」，同一频道只问一次。"""
    peer = str(body.peer or "").strip()
    if not peer:
        raise HTTPException(400, "缺少频道 id")
    acked = list(cfg.data.get("tgmt_ack") or [])
    if peer not in acked:
        acked.append(peer)
        cfg.data["tgmt_ack"] = acked[-200:]
        cfg.save()
    return {"ok": True, "ack": cfg.data["tgmt_ack"]}


@app.post("/api/telegram/mt/list")
def api_tgmt_list(body: TgmtListBody):
    """用登录后的账号会话翻历史：私有频道、匿名页上没有直链的文件/音频帖都走这里。"""
    from telegram_mt import NEED_CRED, NEED_LOGIN, NEED_TELETHON, TYPE_LABELS, normalize_entity

    st = _tgmt_status()
    if not st["installed"]:
        return {"ok": False, "items": [], "diag": {"stopped": NEED_TELETHON}, "message": NEED_TELETHON}
    if not st["configured"]:
        return {"ok": False, "items": [], "diag": {"stopped": NEED_CRED}, "message": NEED_CRED}
    if not st["logged_in"]:
        return {"ok": False, "items": [], "diag": {"stopped": NEED_LOGIN}, "message": NEED_LOGIN}
    ent = normalize_entity(body.channel)
    if not ent:
        raise HTTPException(400, "频道无效：支持 @名字 / t.me/名字 / t.me/c/内部id / -100… 数字 id")
    items, diag = tg_session.list_media(
        ent,
        limit=max(1, min(int(body.limit or 100), 2000)),
        types=body.types or None,
        since=(body.since or "").strip(),
        until=(body.until or "").strip(),
        budget=max(15, min(int(body.budget or 600), 1800)),
        search=(body.search or "").strip(),
        skip_seen=st["skip_seen"] if body.skip_seen is None else bool(body.skip_seen),
    )
    return {"ok": True, "entity": ent, "items": items, "diag": diag, "type_labels": TYPE_LABELS}


@app.get("/api/history")
def api_history(q: str = ""):
    return {"history": history_mgr.get(q), "stats": history_mgr.stats()}


@app.post("/api/history/clear")
def api_history_clear():
    n = len(history_mgr.history)
    history_mgr.clear()
    log_mgr.log(f"[界面] 清空下载历史（{n} 条）", "warning")
    return {"ok": True}


@app.get("/api/logs")
def api_logs(level: str = "all", search: str = ""):
    # 日志就写在程序自己所在的文件夹里，界面上要能报出这个位置并一键打开
    try:
        archives = sorted(p.name for p in APP_DIR.glob("app-*.log"))
    except Exception:
        archives = []
    return {"logs": log_mgr.get(level, search),
            "dir": str(APP_DIR), "file": LOG_FILE.name, "archives": archives}


@app.post("/api/logs/clear")
def api_logs_clear():
    n = len(log_mgr.entries)  # 先数清楚要清掉多少条，再真的清
    log_mgr.clear()
    log_mgr.log(f"[界面] 清空运行日志（{n} 条）", "warning")
    return {"ok": True}


class UiEventBody(BaseModel):
    text: str = ""
    level: str = "info"
    k: str = ""
    kv: dict | None = None


_LOG_KEY_RE = re.compile(r"^[a-z][a-z0-9]*(?:\.[a-z0-9_]+){1,4}$")


def _clean_log_kv(kv: object) -> dict:
    """埋点参数是浏览器发来的，进日志前先收口：只留少量标量，字符串截断。
    八条的上限数的是「收下来的」，不是「交来的」——否则乱键白占名额，正经参数反被挤掉。"""
    if not isinstance(kv, dict):
        return {}
    out: dict = {}
    for key, val in kv.items():
        if len(out) >= 8:
            break
        if not isinstance(key, str) or not re.fullmatch(r"[a-zA-Z][\w]{0,20}", key):
            continue
        if isinstance(val, bool) or isinstance(val, (int, float)):
            out[key] = val
        elif isinstance(val, str):
            out[key] = " ".join(val.split())[:80]
    return out


@app.post("/api/ui_event")
def api_ui_event(body: UiEventBody):
    """前端界面动作埋点：把「用户在哪儿点了什么」记成一条人话日志，方便事后排查。"""
    text = " ".join(str(body.text or "").split())[:200].strip()
    if not text:
        return {"ok": False}
    level = body.level if body.level in ("info", "warning") else "info"
    k = str(body.k or "")[:80]
    if k and not _LOG_KEY_RE.fullmatch(k):
        k = ""    # 键形不对就丢掉，只留那句人话，别把任意字符串塞成「键」
    log_mgr.log(f"[界面] {text}", level, k=k, kv=_clean_log_kv(body.kv) if k else None)
    return {"ok": True, "level": level}


# -------------------- 一键导出诊断包 --------------------
# 诊断包是发给别人看的：配置里的密钥、Cookie 内容、日志里可能夹带的凭据一律不能跟着走。
# 哪些算敏感按「键名」判，以后新增的 token / key / secret 字段会自动被收掉；
# cookie_file、cookie_source 这种只写路径和模式的键保留原值，否则对方看不出登录态是怎么配的。
_DIAG_SECRET_RE = re.compile(
    r"token|secret|api_?key|sendkey|send_key|passwd|password|_pass$|_hash$|credential|cookies?"
    r"|(?:^|[_-])key$|hls_key", re.I
)
_DIAG_COOKIE_PLAIN = {
    "cookie_file", "cookie_source", "cookie_browser", "cookie_exists", "cookies_dir",
    # 这层存的是每个平台的 Cookie 文件路径和取用方式，藏起来就没法排查登录态了
    "platform_cookies",
    # CookieCloud 这几项只是「开没开、按哪种算法、过滤哪些域、服务器在哪」；
    # 键名里带 cookie 会被整片收掉，但 uuid / key 仍然按名单藏（那两个才等于凭据）
    "cookiecloud_enabled", "cookiecloud_server", "cookiecloud_scheme", "cookiecloud_domains",
}
# 整份都是凭据的容器：里面每个叶子值都藏，不再逐个看键名（那层的键是平台名，不是 secret 名）
_DIAG_HIDE_ALL = {"music_platform_cookies", "musicdl_cookies", "platform_cookie_content"}
# 值本身不在敏感名单里、但写法自带凭据的几种
_DIAG_SHAPES = [
    # 代理 / 视频直链里的 user:pass@
    (re.compile(r"(?P<p>://[^/@\s:]+:)[^@\s/]+(?P<at>@)"), lambda m: m.group("p") + "<已隐藏>" + m.group("at")),
    # Telegram bot token 整串
    (re.compile(r"bot\d{6,12}:[A-Za-z0-9_-]{20,}", re.I), lambda m: "<已隐藏>"),
    # 鉴权头，带 Bearer/Basic 前缀的一起吃掉，只留头名
    (re.compile(
        r"(?P<k>(?:authorization|x-api-key|cookie|set-cookie|access_token)\s*[:=]\s*(?:bearer|basic|token)?\s*)"
        r"(?P<v>\S+)", re.I),
     lambda m: m.group("k") + "<已隐藏>"),
    # 键值写法：api_key=… / token: … / password=…
    (re.compile(
        r"(?P<k>(?:api[_-]?key|secret|token|password|passwd|sendkey|decryption_key|hls_key)\s*[:=]\s*)"
        r"(?P<v>\S+)", re.I),
     lambda m: m.group("k") + "<已隐藏>"),
    # 命令行写法：自定义 yt-dlp 参数串里最容易夹 --password 这种（空格的 = 的都认）
    (re.compile(
        r"(?P<k>--(?:password|passwd|api[_-]?key|apikey|token|secret|sendkey|decryption[_-]key|hls[_-]key))"
        r"(?:[=\s]+)(?P<v>\S+)", re.I),
     lambda m: m.group("k") + " <已隐藏>"),
    # URL 查询参数里名字带 token/sig/key/auth 的值（站点签名多半在这里）
    (re.compile(r"(?P<k>[?&][^&=\s]*(?:token|sig|key|auth|secret|password|expire)[^&=\s]*=)(?P<v>[^&\s]+)", re.I),
     lambda m: m.group("k") + "<已隐藏>"),
]
_DIAG_FILE_CAP = 4_000_000   # 单个日志文件最多读末尾这么多字节
_DIAG_LOG_LINES = 3000       # 当前日志最多带这么多行
_DIAG_ARCHIVE_LINES = 800    # 每份归档最多带这么多行
_DIAG_ARCHIVE_FILES = 3      # 最多带最近 3 份归档


def _diag_mask(value) -> str:
    """藏掉内容但留一个指纹：对方能判断「这里填过东西」「两次导出是同一个值」，看不到值本身。"""
    return f"<已隐藏 · 指纹 {hashlib.sha256(str(value).encode('utf-8')).hexdigest()[:8]}>"


def _diag_scrub_str(text, values: List[str]) -> Tuple[str, int]:
    s = str(text)
    n = 0
    for v in values:
        if v and v in s:
            s = s.replace(v, "<已隐藏>")
            n += 1
    out = s
    for pat, rep in _DIAG_SHAPES:
        out = pat.sub(rep, out)
    if out != s:
        n += 1
    return out, n


def _diag_hide_key(key, force: bool = False) -> bool:
    k = str(key)
    if force or k in _DIAG_HIDE_ALL:
        return True
    return k not in _DIAG_COOKIE_PLAIN and bool(_DIAG_SECRET_RE.search(k))


def diag_secret_values(data, force: bool = False) -> List[str]:
    """把配置里真实存在的敏感值收出来：日志和 URL 里出现原样字符串的，一并替换掉。"""
    vals: List[str] = []
    for k, v in (data or {}).items():
        hide = _diag_hide_key(k, force)
        if isinstance(v, dict):
            vals += diag_secret_values(v, hide)
        elif isinstance(v, list):
            for it in v:
                if isinstance(it, dict):
                    vals += diag_secret_values(it, hide)
        elif hide and isinstance(v, str):
            s = v.strip()
            # 太短的值拿去全文替换会把正常词句吃掉，这种值本来也过不了形状清洗
            if len(s) >= 8:
                vals.append(s)
    return sorted(set(vals), key=len, reverse=True)


def diag_redact_config(data, force: bool = False, values: Optional[List[str]] = None) -> Tuple[Any, int]:
    """配置副本：敏感值换成指纹，其余字符串也按已知密钥和常见写法洗一遍。原值不回写配置。"""
    vals = values or []
    out: Any = {}
    n = 0
    for k, v in (data or {}).items():
        key = str(k)
        hide = _diag_hide_key(k, force)
        m = 0
        if isinstance(v, dict):
            out[key], m = diag_redact_config(v, hide, vals)
        elif isinstance(v, list):
            rows = []
            for it in v:
                if isinstance(it, dict):
                    got, mm = diag_redact_config(it, hide, vals)
                elif hide and isinstance(it, str) and it.strip():
                    got, mm = _diag_mask(it), 1
                elif isinstance(it, str):
                    got, mm = _diag_scrub_str(it, vals)
                else:
                    got, mm = it, 0
                rows.append(got)
                m += mm
            out[key] = rows
        elif hide and isinstance(v, str) and v.strip():
            out[key], m = _diag_mask(v), 1
        elif isinstance(v, str):
            out[key], m = _diag_scrub_str(v, vals)
        else:
            out[key] = v
        n += m
    return out, n


def _diag_scrub_obj(obj, values: List[str]) -> Tuple[Any, int]:
    """状态 / 组件 / 任务这类读数：结构照原样保留，只清洗里面的字符串"""
    if isinstance(obj, dict):
        out = {}
        n = 0
        for k, v in obj.items():
            out[k], m = _diag_scrub_obj(v, values)
            n += m
        return out, n
    if isinstance(obj, list):
        rows = []
        n = 0
        for it in obj:
            got, m = _diag_scrub_obj(it, values)
            rows.append(got)
            n += m
        return rows, n
    if isinstance(obj, str):
        return _diag_scrub_str(obj, values)
    return obj, 0


def _diag_read_tail(path: Path, lines: int) -> List[str]:
    """日志按行取尾巴：文件可能很大，只读末尾一段，并丢掉截断的半行"""
    try:
        size = path.stat().st_size
        with open(path, "rb") as f:
            if size > _DIAG_FILE_CAP:
                f.seek(size - _DIAG_FILE_CAP)
                f.readline()
            raw = f.read()
    except Exception:
        return []
    return raw.decode("utf-8", "ignore").splitlines()[-lines:]


def _diag_log_rows(lines: List[str], values: List[str]) -> List[str]:
    """app.log 每行是一条 JSON，只洗 message；不是 JSON 的行原样洗"""
    out = []
    for ln in lines:
        try:
            e = json.loads(ln)
        except Exception:
            e = None
        if isinstance(e, dict):
            e["message"], _ = _diag_scrub_str(e.get("message", ""), values)
            out.append(json.dumps(e, ensure_ascii=False))
        else:
            out.append(_diag_scrub_str(ln, values)[0])
    return out


def build_diagnostics_zip() -> Tuple[bytes, dict]:
    """凑出诊断包：环境读数 + 脱敏配置 + 队列状态 + 近期日志。全程在内存里，不落盘。"""
    data = dict(cfg.data or {})
    values = diag_secret_values(data)
    conf, hidden = diag_redact_config(data, False, values)
    files: List[str] = []
    rows = 0

    def add(zf, name, text):
        nonlocal rows
        zf.writestr(name, text)
        files.append(name)
        rows += 1

    def dump(obj):
        return json.dumps(obj, ensure_ascii=False, indent=2, default=str)

    def safe(fn):
        try:
            return fn()
        except Exception as e:
            return {"error": str(e)[:200]}

    st, _ = _diag_scrub_obj(safe(api_status), values)
    comp, _ = _diag_scrub_obj(safe(lambda: api_components("")), values)
    tasks, _ = _diag_scrub_obj(safe(lambda: queue.list_tasks("queue")), values)
    meta = {
        "生成时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "程序目录": str(APP_DIR),
        "Python": sys.version.split()[0],
        "系统平台": sys.platform,
        "Windows 版本": getattr(sys.getwindowsversion(), "build", "") if os.name == "nt" else "",
        "界面版本": ((comp.get("bundled") or {}).get("app") if isinstance(comp, dict) else "") or "",
        "配置里隐藏了敏感值": hidden,
        "本包不含": [
            "Cookie 文件本身（只保留路径与来源模式）",
            "Telegram 会话文件 tg_session*.session",
            "下载目录里的成品",
            "磁力 / 种子的做种状态目录",
        ],
    }
    readme = "\n".join([
        "诊断包说明",
        "========",
        "",
        "这个包用来把排查问题需要的信息一次性交给别人，里面是：",
        "  meta.json         生成时间、程序目录、Python / 系统版本",
        "  status.json       组件版本、运行状态、目录与磁盘读数",
        "  components.json   随包版本 / 当前版本 / pip 环境",
        "  config.json       当前设置（密钥与 Cookie 内容已隐藏）",
        "  tasks.json        队列里的任务清单",
        "  logs/app.log      最近 " + str(_DIAG_LOG_LINES) + " 行运行日志",
        "  logs/archive/     最近 " + str(_DIAG_ARCHIVE_FILES) + " 份跨天归档，每份最多 "
        + str(_DIAG_ARCHIVE_LINES) + " 行",
        "",
        "敏感内容的处理：",
        "  1) 配置里的密钥、Token、密码等凭据（键名含 token / key / secret / password / hash / cookies）",
        "     一律不写明文，换成「<已隐藏 · 指纹 xxxxxxxx>」，凭指纹能判断填没填、两次是否同一个值。",
        "  2) Cookie 只保留文件路径与来源方式，内容不打包。",
        "  3) 日志、URL、任务标题里再按原值和常见写法（user:pass@、bot token、鉴权头）洗一遍。",
        "  4) 本包不下载成品文件，也不含 Telegram 登录会话。",
        "",
        "上传前建议自己再翻一眼 config.json 和 logs/，确认没有你额外写进备注的隐私内容。",
        "",
    ])
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        add(zf, "README.txt", readme)
        add(zf, "meta.json", dump(meta))
        add(zf, "config.json", dump(conf))
        add(zf, "status.json", dump(st))
        add(zf, "components.json", dump(comp))
        add(zf, "tasks.json", dump(tasks))
        cur = _diag_log_rows(_diag_read_tail(LOG_FILE, _DIAG_LOG_LINES), values)
        if cur:
            add(zf, "logs/app.log", "\n".join(cur) + "\n")
        try:
            archives = sorted(APP_DIR.glob("app-*.log"), key=lambda p: p.name)
        except Exception:
            archives = []
        for p in archives[-_DIAG_ARCHIVE_FILES:]:
            got = _diag_log_rows(_diag_read_tail(p, _DIAG_ARCHIVE_LINES), values)
            if got:
                add(zf, f"logs/archive/{p.name}", "\n".join(got) + "\n")
    blob = buf.getvalue()
    return blob, {"files": len(files), "bytes": len(blob), "hidden": hidden}


@app.post("/api/diagnostics/export")
def api_diagnostics_export():
    """一键导出诊断包：内存里凑一个 zip 直接回给浏览器，不在本机留文件。"""
    try:
        blob, info = build_diagnostics_zip()
    except Exception as e:
        raise HTTPException(500, f"诊断包生成失败：{str(e)[:200]}")
    name = f"diagnostics-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    log_mgr.log(
        f"[界面] 导出诊断包（{info['files']} 个文件 · {info['bytes']} 字节 · "
        f"配置里隐藏敏感值 {info['hidden']} 处）"
    )
    return StreamingResponse(
        io.BytesIO(blob),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{name}.zip"'},
    )


# ---------- 订阅 ----------
def _sub_view(s: dict) -> dict:
    r = _norm_sub_rules(s.get("rules"))
    v = {**s, "kind": _sub_kind_of(s), "auto_download": bool(s.get("auto_download", True)),
         "rules": r, "rules_text": _sub_rules_text(r)}
    # 窗口对照清单与归档明细是后端内部账本，整包塞进列表接口只会把响应撑大；界面只要条数
    v["archived_count"] = len(s.get("archived") or [])
    v.pop("feed", None)
    v.pop("archived", None)
    return v


@app.get("/api/subs")
def api_subs_list():
    try:
        from music_search import music_playlist_hosts
        hosts = music_playlist_hosts()
    except Exception:
        hosts = []
    return {"subs": [_sub_view(s) for s in sub_mgr.list()],
            "type_labels": SUB_TYPES, "qualities": list(SUB_QUALITIES),
            "formats": list(SUB_FORMATS), "music_hosts": hosts}


@app.post("/api/subs/add")
def api_subs_add(body: SubAddBody):
    try:
        item = sub_mgr.add(body.url, body.title or "", body.mode or "", body.kind or "",
                           body.auto_download)
        # 立即初始化扫描（只记 ID，不下载）
        try:
            n = sub_mgr.scan_one(item, auto_download=False)
            item = next((s for s in sub_mgr.list() if s.get("id") == item.get("id")), item)
        except Exception as ex:
            log_mgr.log(f"订阅初始化扫描: {ex}", "warning")
        return {"ok": True, "item": _sub_view(item), "init_count": len(item.get("last_ids") or [])}
    except Exception as e:
        raise HTTPException(400, str(e))


@app.post("/api/subs/backfill")
def api_subs_backfill(body: SubBackfillBody):
    """按日期窗给单个订阅回填一次历史 —— 追新只看窗口外的新条目，回填是明确点出来的动作。"""
    with sub_mgr._lock:
        sub = next((s for s in sub_mgr.subs if s.get("id") == body.id), None)
    if not sub:
        raise HTTPException(404, "订阅不存在")
    since, until = _norm_date_str(body.since), _norm_date_str(body.until)
    if not (since and until) and _sub_kind_of(sub) != "music":
        raise HTTPException(400, "回填要给完整的起止日期，不然和直接扫描没区别")
    try:
        n = sub_mgr.scan_one(sub, auto_download=True, backfill={"since": since, "until": until})
    except Exception as e:
        raise HTTPException(400, str(e))
    item = next((s for s in sub_mgr.list() if s.get("id") == body.id), sub)
    res = _sub_view(item)
    return {"ok": True, "new": n, "window": [since, until], "item": res,
            "rules_text": res["rules_text"], "last_error": res.get("last_error") or ""}


@app.post("/api/subs/rules")
def api_subs_rules(body: SubRulesBody):
    try:
        rules = sub_mgr.set_rules(body.id, body.rules or {}, body.mode, body.auto_download)
    except ValueError as e:
        raise HTTPException(404 if "不存在" in str(e) else 400, str(e))
    item = next((s for s in sub_mgr.list() if s.get("id") == body.id), None)
    return {"ok": True, "rules": rules, "rules_text": _sub_rules_text(rules), "item": _sub_view(item)}


@app.post("/api/subs/remove")
def api_subs_remove(body: SubIdBody):
    sub_mgr.remove(body.id)
    return {"ok": True}


@app.post("/api/subs/toggle")
def api_subs_toggle(body: SubIdBody):
    if body.enabled is None:
        raise HTTPException(400, "需要 enabled")
    sub_mgr.set_enabled(body.id, body.enabled)
    return {"ok": True}


@app.post("/api/subs/scan")
def api_subs_scan():
    res = sub_mgr.scan_all()
    log_mgr.log(f"手动订阅扫描: 检查 {res['checked']}，新增 {res['new']}")
    return {"ok": True, **res}


@app.post("/api/subs/scan-one")
def api_subs_scan_one(body: SubIdBody):
    with sub_mgr._lock:
        sub = next((s for s in sub_mgr.subs if s.get("id") == body.id), None)
    if not sub:
        raise HTTPException(404, "订阅不存在")
    n = sub_mgr.scan_one(sub)
    return {"ok": True, "new": n, "item": _sub_view(sub), "rules_text": _sub_view(sub)["rules_text"]}


@app.post("/api/subs/preview")
def api_subs_preview(body: SubIdBody):
    """干跑一轮追新：这份计划说明「真点扫描会做什么」，不入队、不动游标、不落盘。"""
    with sub_mgr._lock:
        sub = next((s for s in sub_mgr.subs if s.get("id") == body.id), None)
    if not sub:
        raise HTTPException(404, "订阅不存在")
    plan = sub_mgr.preview_one(sub)
    if plan.get("error"):
        log_mgr.log(f"订阅预览「{plan.get('title') or body.id}」：{plan['error']}", "warning")
    else:
        log_mgr.log(f"订阅预览「{plan.get('title') or body.id}」："
                    f"读到 {plan.get('read', 0)} 条，未读 {plan.get('new', 0)} 条，"
                    f"计划入队 {plan.get('picked_total', 0)} 条"
                    + (f"，上游删除待归档 {plan.get('archive_total', 0)} 条"
                       if plan.get("archive_total") else ""))
    return {"ok": True, "plan": plan}


@app.post("/api/subs/archived")
def api_subs_archived(body: SubIdBody):
    """读某条订阅的「上游已删除」留档清单。"""
    with sub_mgr._lock:
        sub = next((s for s in sub_mgr.subs if s.get("id") == body.id), None)
    if not sub:
        raise HTTPException(404, "订阅不存在")
    return {"ok": True, "title": sub.get("title") or sub.get("url") or "",
            "items": list(sub.get("archived") or [])}


@app.post("/api/subs/archived/clear")
def api_subs_archived_clear(body: SubArchiveClearBody):
    """清掉留档记录（单条或整单）；不影响追新游标，条目重现在源头也不会被当成新增。"""
    try:
        removed = sub_mgr.clear_archived(body.id, body.entry_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    item = next((s for s in sub_mgr.list() if s.get("id") == body.id), None)
    log_mgr.log(f"订阅「{(item or {}).get('title') or body.id}」"
                + (f"归档清单移除 1 条（{body.entry_id[:24]}）" if body.entry_id
                   else f"归档清单已清空（{removed} 条）"))
    return {"ok": True, "removed": removed, "item": _sub_view(item) if item else {}}


# ---------- Telegram ----------
@app.post("/api/telegram/test")
def api_telegram_test():
    res = tg_notifier.test()
    if res != "ok":
        raise HTTPException(400, "发送失败，请检查 Token / Chat ID 与网络")
    return {"ok": True, "message": "测试消息已发送"}


# ---------- 多平台 Cookie / 搜索 / 风控 / 同步 ----------
class PlatformCookieBody(BaseModel):
    platform: str
    source: str = "none"  # none | file | browser
    file: str = ""
    browser: str = "chrome"


class SearchBody(BaseModel):
    query: str
    platform: str = "youtube"  # youtube | bilibili | all | douyin
    content_type: str = "all"  # all | video | channel | playlist
    limit: int = 30
    sort: str = "relevance"    # relevance 相似度 | views 播放量 | newest 发布时间


@app.get("/api/platforms/cookies")
def api_platform_cookies():
    pc = cfg.data.get("platform_cookies") or {}
    flags = _login_flag_snapshot()
    items = []
    for key, label in PLATFORM_LABELS.items():
        if key == "default":
            continue
        info = dict(pc.get(key) or {})
        path = platform_cookie_path(key)
        f = info.get("file") or str(path)
        items.append({
            "platform": key,
            "label": label,
            "source": info.get("source") or "none",
            "file": f,
            "browser": info.get("browser") or "chrome",
            "configured": (info.get("source") in ("file", "browser")) and (
                info.get("source") == "browser" or Path(f).exists()
            ),
            "file_exists": Path(f).exists() if f else path.exists(),
            "default_path": str(path),
            "login_issue": flags.get(key),
        })
    return {"platforms": items, "cookies_dir": str(COOKIES_DIR),
            "login_issue_count": sum(1 for i in items if i["login_issue"])}


@app.post("/api/platforms/cookies")
def api_set_platform_cookie(body: PlatformCookieBody):
    plat = (body.platform or "").strip()
    if plat not in PLATFORM_LABELS:
        raise HTTPException(400, "未知平台")
    pc = dict(cfg.data.get("platform_cookies") or {})
    entry = {
        "source": (body.source or "none").strip().lower(),
        "file": (body.file or str(platform_cookie_path(plat))).strip(),
        "browser": (body.browser or "chrome").strip().lower(),
    }
    pc[plat] = entry
    cfg.data["platform_cookies"] = pc
    cfg.save()
    # 动过这一平台的 Cookie 来源，之前那枚「被判定为需要登录」就不再说明当前状态了
    _login_flag_clear(plat)
    drop_all_cookie_prefs()   # 同理，「这条匿名就够」的旧判定也不能接着替新配置做决定
    return {"ok": True, "item": entry}


@app.post("/api/platforms/cookies/upload")
async def api_upload_platform_cookie(platform: str, content: str = ""):
    """上传 Netscape cookies 文本"""
    plat = (platform or "").strip()
    if plat not in PLATFORM_LABELS:
        raise HTTPException(400, "未知平台")
    if not content or "http" not in content.lower() and "# netscape" not in content.lower():
        # 仍允许保存，用户可能格式略有不同
        pass
    path = platform_cookie_path(plat)
    path.write_text(content, encoding="utf-8")
    pc = dict(cfg.data.get("platform_cookies") or {})
    pc[plat] = {"source": "file", "file": str(path), "browser": "chrome"}
    cfg.data["platform_cookies"] = pc
    cfg.save()
    _login_flag_clear(plat)
    drop_all_cookie_prefs()
    return {"ok": True, "path": str(path)}


class CookieTextBody(BaseModel):
    platform: str
    content: str


@app.post("/api/platforms/cookies/save-text")
def api_save_cookie_text(body: CookieTextBody):
    plat = (body.platform or "").strip()
    if plat not in PLATFORM_LABELS:
        raise HTTPException(400, "未知平台")
    path = platform_cookie_path(plat)
    path.write_text(body.content or "", encoding="utf-8")
    pc = dict(cfg.data.get("platform_cookies") or {})
    pc[plat] = {"source": "file", "file": str(path), "browser": "chrome"}
    cfg.data["platform_cookies"] = pc
    cfg.save()
    _login_flag_clear(plat)
    drop_all_cookie_prefs()
    return {"ok": True, "path": str(path)}


class CookieFlagClearBody(BaseModel):
    platform: str


@app.post("/api/platforms/cookies/clear-flag")
def api_clear_cookie_flag(body: CookieFlagClearBody):
    """「清除标记」：这条判定只说明本次运行里被挡过一次，用户确认无误后可以直接抹掉。"""
    plat = (body.platform or "").strip()
    if plat not in PLATFORM_LABELS:
        raise HTTPException(400, "未知平台")
    had = bool(_login_flag_snapshot().get(plat))
    _login_flag_clear(plat)
    log_mgr.log(f"清除 {PLATFORM_LABELS.get(plat, plat)} 的 Cookie 登录态标记"
                + ("（本来就没有标记）" if not had else ""))
    return {"ok": True, "cleared": had}


# --------------------------------------------------------------- CookieCloud 同步
# 浏览器装 CookieCloud 插件，把登录 Cookie 加密推到自己架的服务器上；这台机器把它拉下来
# 写成 cookies/cookies.txt 与 cookies/<平台>_cookies.txt —— 下载链路本来就读这些文件，
# 拉完不用再改别的设置。接口与算法照 easychen/CookieCloud 的 api/app.js，不自己发明：
#   取   GET  {server}/get/{uuid}   → {"encrypted": "...", "crypto_type": "legacy"}
#   存   POST {server}/update       ← {"uuid": "...", "encrypted": "...", "crypto_type": "..."}
# 密钥材料 = md5(f"{uuid}-{同步密钥}") 的前 16 个字符，两种写法都从它出发：
#   legacy            那 16 个字符当「口令」，按 OpenSSL EVP_BytesToKey(MD5) 派生 32 字节 key
#                     + 16 字节 iv；密文是 base64("Salted__" + 8 字节随机盐 + 数据)，Pkcs7 填充。
#   aes-128-cbc-fixed 那 16 个字符直接当 AES-128 的 key，IV 固定 16 个 0，密文纯 base64。
# 官方插件至今只写 legacy（fixed 是服务端那侧加的），所以「自动」= 先按云端报的写法解，
# 解不开再换另一种；写出去时「自动」沿用上次解开的写法，没见过云端就按 legacy。
COOKIECLOUD_SCHEMES = ("auto", "legacy", "aes-128-cbc-fixed")
COOKIECLOUD_WRITE_SCHEMES = ("legacy", "aes-128-cbc-fixed")
COOKIECLOUD_TIMEOUT = 20
_CC_UUID_RE = re.compile(r"^[0-9A-Za-z._-]{4,128}$")


def _cc_now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _cc_cfg() -> dict:
    d = cfg.data
    return {
        "enabled": bool(d.get("cookiecloud_enabled")),
        "server": str(d.get("cookiecloud_server") or "").strip(),
        "uuid": str(d.get("cookiecloud_uuid") or "").strip(),
        "key": str(d.get("cookiecloud_key") or ""),
        "scheme": str(d.get("cookiecloud_scheme") or "auto").strip().lower(),
        "domains": str(d.get("cookiecloud_domains") or "").strip(),
    }


def _cc_ready(cc: dict, need_key: bool = True) -> None:
    """缺哪一层就点名哪一层，别笼统回一句「配置不完整」。"""
    if not cc["enabled"]:
        raise HTTPException(400, "CookieCloud 同步没打开（设置 → Cookie 与登录 → CookieCloud 同步）")
    if not cc["server"]:
        raise HTTPException(400, "没填 CookieCloud 服务器地址：插件设置里那个「同步地址」，端口和子目录一起抄过来")
    if not re.match(r"^https?://", cc["server"], re.I):
        raise HTTPException(400, f"服务器地址要带 http:// 或 https://，现在填的是「{cc['server'][:48]}」")
    if not cc["uuid"]:
        raise HTTPException(400, "没填 UUID：插件设置里的「用户标识 UUID」，它和密钥一起才解得开云端那一份")
    if not _CC_UUID_RE.match(cc["uuid"]):
        raise HTTPException(400, "UUID 里只该有字母、数字和 - _ .，现在这串不是（它要拼进请求路径）")
    if need_key and not cc["key"]:
        raise HTTPException(400, "没填同步密钥：这份只存在本机 config.json 里，界面不回显、日志里也不写")


def _cc_endpoint(server: str, tail: str) -> str:
    return server.rstrip("/") + "/" + tail.lstrip("/")


def _cc_domain_filter(raw: str) -> List[str]:
    out: List[str] = []
    for tok in re.split(r"[\n,;]", raw or ""):
        t = tok.strip().lower().lstrip(".")
        if t and t not in out:
            out.append(t)
    return out


def _cc_host(url: str) -> str:
    """只报主机和端口：netloc 里可能夹着 user:pass，那和密钥一样不能抄进日志与状态。"""
    u = urlsplit(url or "")
    try:
        h = (u.hostname or "").lower()
        return f"{h}:{u.port}" if h and u.port else h
    except Exception:
        return str(u.netloc or "")[:40]


def _cc_proxy_note(url: str) -> str:
    """连不上时把「这次是怎么走的」说清楚：策略给的代理、系统代理、还是直连。"""
    try:
        px = http_proxies(url)
    except Exception:
        px = None
    if isinstance(px, dict):
        addr = px.get("https") or px.get("http")
        return "按网络策略强制直连" if addr is None else f"按网络策略走代理 {addr}"
    host = (urlsplit(url).hostname or "").lower()
    if host == "localhost" or host == "::1" or host.startswith("127."):
        # 自建 CookieCloud 常跑在 127.0.0.1， requests 对回环地址本来就绕过系统代理，别说成「走了代理」
        return "本机地址，直连"
    sp, src = system_proxy_detail()
    return f"跟随{src}的 {sp}" if sp else "直连（策略和系统里都没有代理）"


def _cc_http(url: str, payload: Optional[dict] = None) -> Tuple[int, dict, str]:
    """CookieCloud 的一次请求：payload=None 走 GET，给了就走 POST(json)。回 (状态码, JSON, 错话)。"""
    kw = {
        "timeout": COOKIECLOUD_TIMEOUT,
        "proxies": http_proxies(url),
        "verify": not bool(cfg.data.get("nocheckcertificate", True)),
        "headers": {"User-Agent": "MediaDownloader-web/CookieCloud"},
    }
    try:
        r = requests.post(url, json=payload, **kw) if payload is not None else requests.get(url, **kw)
    except Exception as e:
        return 0, {}, f"连不上 {_cc_host(url)}：{type(e).__name__} {str(e)[:120]}（{_cc_proxy_note(url)}）"
    # 自己按 UTF-8 解：requests 遇到没带 charset 的响应会猜 ISO-8859-1，中文错话会变成乱码
    try:
        body = r.content.decode("utf-8").strip()
    except Exception:
        body = (r.text or "").strip()
    try:
        data = json.loads(body)
        return r.status_code, data if isinstance(data, dict) else {"_json": data}, ""
    except Exception:
        return r.status_code, ({"_text": body[:200]} if body else {}), ""


def _cc_key_str(uuid_: str, key: str) -> str:
    return hashlib.md5(f"{uuid_}-{key}".encode("utf-8")).hexdigest()[:16]


def _cc_aes():
    try:
        from Crypto.Cipher import AES
        return AES
    except Exception:
        raise HTTPException(500, "本机没有 pycryptodome，解不了 CookieCloud 的密文"
                                 "（pip install pycryptodome；便携包里它随 musicdl 一起装）")


def _cc_evpkdf(passphrase: bytes, salt: bytes, want: int = 48) -> bytes:
    """OpenSSL EVP_BytesToKey（MD5）：D1=MD5(pw+salt)，Dn=MD5(D(n-1)+pw+salt)，取前 want 字节。"""
    out, last = b"", b""
    while len(out) < want:
        last = hashlib.md5(last + passphrase + salt).digest()
        out += last
    return out[:want]


def _cc_pkcs7(buf: bytes, block: int = 16, unpad: bool = False) -> bytes:
    if unpad:
        if not buf:
            raise ValueError("密文是空的")
        pad = buf[-1]
        if pad < 1 or pad > block or buf[-pad:] != bytes([pad]) * pad:
            raise ValueError("Pkcs7 填充不对（多半是口令不对）")
        return buf[:-pad]
    pad = block - len(buf) % block
    return buf + bytes([pad]) * pad


def _cc_decrypt_blob(blob: str, kk: str, scheme: str) -> dict:
    AES = _cc_aes()
    # CryptoJS 写的是一整行 base64，别的工具（openssl -a 之类）会折行 —— 先抹掉空白再解
    raw = base64.b64decode(re.sub(r"\s+", "", str(blob or "")), validate=True)
    if scheme == "aes-128-cbc-fixed":
        if not raw or len(raw) % 16:
            raise ValueError("密文长度不是整块")
        plain = _cc_pkcs7(AES.new(kk.encode("utf-8"), AES.MODE_CBC, b"\x00" * 16).decrypt(raw), unpad=True)
    else:
        if len(raw) < 32 or raw[:8] != b"Salted__":
            raise ValueError("不是 CryptoJS 的 Salted__ 写法")
        dk = _cc_evpkdf(kk.encode("utf-8"), raw[8:16])
        plain = _cc_pkcs7(AES.new(dk[:32], AES.MODE_CBC, dk[32:48]).decrypt(raw[16:]), unpad=True)
    return json.loads(plain.decode("utf-8"))


def _cc_try_order(want: str, known: str) -> List[str]:
    if want in COOKIECLOUD_WRITE_SCHEMES:
        return [want]
    order = [known] if known in COOKIECLOUD_WRITE_SCHEMES else []
    return order + [s for s in COOKIECLOUD_WRITE_SCHEMES if s not in order]


def _cc_decrypt(encrypted: str, cc: dict, known: str = "") -> Tuple[dict, str]:
    kk = _cc_key_str(cc["uuid"], cc["key"])
    tried = []
    for scheme in _cc_try_order(cc["scheme"], known):
        try:
            return _cc_decrypt_blob(encrypted, kk, scheme), scheme
        except Exception as e:
            tried.append(f"{scheme}：{str(e)[:70] or type(e).__name__}")
    raise HTTPException(502, "云端那一份解不开（" + "；".join(tried) + "）。"
                             f"要么 UUID / 同步密钥不对，要么云端不是这两种写法存的；现在选的加密方式是「{cc['scheme']}」。")


def _cc_encrypt(payload: dict, cc: dict, scheme: str) -> str:
    AES = _cc_aes()
    text = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    kk = _cc_key_str(cc["uuid"], cc["key"]).encode("utf-8")
    if scheme == "aes-128-cbc-fixed":
        ct = AES.new(kk, AES.MODE_CBC, b"\x00" * 16).encrypt(_cc_pkcs7(text))
        return base64.b64encode(ct).decode("ascii")
    salt = secrets.token_bytes(8)
    dk = _cc_evpkdf(kk, salt)
    ct = AES.new(dk[:32], AES.MODE_CBC, dk[32:48]).encrypt(_cc_pkcs7(text))
    return base64.b64encode(b"Salted__" + salt + ct).decode("ascii")


def _cc_rows_from_cloud(data: dict) -> Tuple[List[dict], List[str]]:
    """云端 cookie_data → 归一化的 Cookie 行。正常形状是 {域: [cookie]}，第三方客户端有
    写成一条扁平列表的，两种都收；认不出的只记一句说明，不猜。"""
    notes: List[str] = []
    items: List[dict] = []
    cd = data.get("cookie_data")
    if isinstance(cd, dict):
        for key, val in cd.items():
            if isinstance(val, list):
                items.extend([c for c in val if isinstance(c, dict)])
            elif isinstance(val, dict):
                items.extend([c for c in val.values() if isinstance(c, dict)])
            else:
                notes.append(f"云端 {str(key)[:24]} 那一项不是列表，跳过了")
    elif isinstance(cd, list):
        items.extend([c for c in cd if isinstance(c, dict)])
    elif cd is not None:
        notes.append("云端 cookie_data 既不是对象也不是数组，读不出条目")
    rows: List[dict] = []
    for c in items:
        name = str(c.get("name") or "").strip()
        dom = str(c.get("domain") or "").strip().lower()
        if not name or not dom:
            continue
        exp = c.get("expirationDate")
        if exp is None:
            exp = c.get("expires")
        try:
            expiry = int(float(exp)) if exp not in (None, "", 0, False) else 0
        except Exception:
            expiry = 0
        rows.append({"name": name, "value": str(c.get("value") or ""), "domain": dom,
                     "path": str(c.get("path") or "/") or "/", "secure": bool(c.get("secure")),
                     "expires": max(0, expiry)})
    ls = data.get("local_storage_data")
    if isinstance(ls, dict) and ls:
        notes.append(f"云端还带了 {len(ls)} 个站的 localStorage，下载用不上，没写盘")
    return rows, notes


def _cc_filter_rows(rows: List[dict], want: List[str]) -> List[dict]:
    if not want:
        return rows
    # 和插件同一口径：域名里含这个词就算命中（.youtube.com 命中 youtube.com）
    return [r for r in rows if any(w in r["domain"] for w in want)]


def _cc_platform_for(domain: str) -> str:
    d = (domain or "").lower().lstrip(".")
    for name, hints in PLATFORM_RULES:
        for hint in hints:
            h = hint.lower().rstrip("/")
            if d == h or d.endswith("." + h):
                return name
    return "default"


def _cc_netscape_lines(rows: List[dict]) -> List[str]:
    """只有 Cookie 那几行（不含头部注释）—— 判断「内容变没变」比的是这些。
    头部那行同步时间每秒都在跳，拿整份文本比就等于每次拉取都算改过、每次都堆一份备份。"""
    dedup: Dict[tuple, dict] = {}
    for r in rows:
        dedup[(r["domain"], r["path"], r["name"])] = r
    lines: List[str] = []
    for key, r in sorted(dedup.items()):
        lines.append("\t".join([r["domain"], "TRUE" if r["domain"].startswith(".") else "FALSE",
                                r["path"], "TRUE" if r["secure"] else "FALSE",
                                str(int(r["expires"] or 0)), r["name"], r["value"]]))
    return lines


def _cc_netscape_text(rows: List[dict], note: str) -> str:
    """Netscape/Mozilla 格式：domain flag path secure expiry name value（制表符分隔）。"""
    lines = ["# Netscape HTTP Cookie File", f"# {note}",
             "# domain\tincludeSubDomains\tpath\tsecure\texpiry\tname\tvalue"]
    lines += _cc_netscape_lines(rows)
    return "\n".join(lines) + "\n"


def _cc_parse_netscape(text: str) -> List[dict]:
    """把本机的 cookies.txt 读回成行。#HttpOnly_ 开头那几条是真 Cookie，不能当注释扔了。"""
    rows: List[dict] = []
    for line in (text or "").splitlines():
        s = line.strip()
        if s.startswith("#HttpOnly_"):
            s = s[len("#HttpOnly_"):]
        if not s or s.startswith("#"):
            continue
        cols = s.split("\t") if "\t" in s else s.split()
        if len(cols) < 7:
            continue
        try:
            expiry = int(float(cols[4]))
        except Exception:
            expiry = 0
        rows.append({"name": cols[5].strip(), "value": "\t".join(cols[6:]).strip(),
                     "domain": cols[0].strip().lower(), "path": cols[2].strip() or "/",
                     "secure": cols[3].strip().upper() == "TRUE", "expires": max(0, expiry)})
    return rows


def _cc_dedup(rows: List[dict]) -> List[dict]:
    out: Dict[tuple, dict] = {}
    for r in rows:
        out[(r["domain"], r["path"], r["name"])] = r
    return list(out.values())


def _cc_body_same(path: Path, rows: List[dict]) -> bool:
    """文件里那些 Cookie 行与要写的这一批是否一模一样 —— 头部那行同步时间不算。

    以前这里比的是整份文本，而文本第二行写着「CookieCloud 同步写入 <时刻>」：同一个时刻之内
    拉两次才算没变，隔了一秒就必然「变了」，于是每次真拉取都多一份没人看的备份，
    还把「内容一样就不动」这条口径变成了看机器快慢。两边都过一遍同一个渲染再比，
    比的是格式化后的 Cookie 行，不是内存里的 dict。
    """
    if not path.is_file():
        return False
    try:
        old = _cc_parse_netscape(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return False
    return _cc_netscape_lines(old) == _cc_netscape_lines(rows)


def _cc_write_file(path: Path, rows: List[dict], label: str = "") -> dict:
    """覆盖前留 .bak-<时间>；Cookie 行一模一样就不动，免得每次拉取都堆一份没人看的备份。"""
    rows = _cc_dedup(rows)  # 先去重，头部注释里报的条数才和文件里真有的一致
    note = (f"CookieCloud 同步写入 {_cc_now()}，共 {len(rows)} 条；"
            f"手工改过的话下次拉取会被盖上（覆盖前留 {path.name}.bak-<时间>）")
    text = _cc_netscape_text(rows, note)
    info = {"file": path.name, "path": str(path), "label": label,
            "count": len(_cc_parse_netscape(text))}
    existed = path.is_file()
    if _cc_body_same(path, rows):
        info["changed"] = False
        info["backup"] = ""
        return info
    backup = ""
    if existed:
        bak = _edit_backup_path(path)
        shutil.copy2(path, bak)
        backup = bak.name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    info["changed"] = True
    info["backup"] = backup
    return info


def _cc_pull_rows(cc: dict) -> dict:
    """取云端那一份、解密、按域名过滤。测试连接与拉取共用这段，都不写盘。"""
    _cc_ready(cc)
    url = _cc_endpoint(cc["server"], "/get/" + cc["uuid"])
    code, data, err = _cc_http(url)
    if err:
        raise HTTPException(502, err)
    if code == 404:
        raise HTTPException(404, f"服务器上没有这个 UUID 的数据（{_cc_host(url)} 回 404）："
                                 "先在浏览器插件里按一次「上传」")
    if code != 200:
        raise HTTPException(502, f"服务器回了 HTTP {code}：{str(data.get('_text') or data)[:160]}")
    blob = str(data.get("encrypted") or "")
    if not blob:
        raise HTTPException(502, "服务器没回 encrypted 字段，不像 CookieCloud 的 /get 接口"
                                 f"（回的是：{str(data.get('_text') or json.dumps(data, ensure_ascii=False))[:120]}）")
    known = str(data.get("crypto_type") or "").strip().lower()
    parsed, scheme = _cc_decrypt(blob, cc, known)
    rows, notes = _cc_rows_from_cloud(parsed)
    want = _cc_domain_filter(cc["domains"])
    kept = _cc_dedup(_cc_filter_rows(rows, want))
    return {"rows": rows, "kept": kept, "notes": notes, "scheme": scheme, "server_scheme": known,
            "domains": sorted({r["domain"] for r in kept}), "update_time": str(parsed.get("update_time") or ""),
            "cloud_domains": sorted({r["domain"] for r in rows}), "filtered_out": len(rows) - len(kept),
            "want": want}


def _cc_local_rows() -> Tuple[List[dict], List[str]]:
    """本机这几个 Netscape 文件读回来（全局 cookies.txt + 每个平台的文件），推给云端用。"""
    paths: List[Path] = []
    gf = str(cfg.data.get("cookie_file") or DEFAULT_COOKIE_FILE).strip()
    if gf:
        paths.append(Path(gf))
    for name, _hints in PLATFORM_RULES:
        paths.append(platform_cookie_path(name))
    for entry in (cfg.data.get("platform_cookies") or {}).values():
        f = str((entry or {}).get("file") or "").strip() if isinstance(entry, dict) else ""
        if f:
            paths.append(Path(f))
    rows: List[dict] = []
    used: List[str] = []
    for p in paths:
        rp = str(p)
        if rp in used or not p.is_file():
            continue
        used.append(rp)
        try:
            rows.extend(_cc_parse_netscape(p.read_text(encoding="utf-8", errors="ignore")))
        except Exception:
            continue
    return _cc_dedup(rows), used


def _cc_state() -> dict:
    try:
        raw = json.loads(COOKIECLOUD_STATE_FILE.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def _cc_state_save(patch: dict) -> dict:
    st = _cc_state()
    st.update(patch)
    try:
        tmp = Path(str(COOKIECLOUD_STATE_FILE) + ".tmp")
        tmp.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
        os.replace(tmp, COOKIECLOUD_STATE_FILE)
    except Exception as e:
        log_mgr.log(f"[CookieCloud] 同步状态没写下去（{type(e).__name__}），界面上的时间戳这次不会更新", "warning")
    return st


def _cc_payload() -> dict:
    cc = _cc_cfg()
    st = _cc_state()
    return {
        "enabled": cc["enabled"], "server": cc["server"], "uuid": cc["uuid"],
        "key": "", "key_set": bool(cc["key"]),
        "scheme": cc["scheme"], "schemes": list(COOKIECLOUD_SCHEMES),
        "scheme_labels": {"auto": "自动 · 先按云端报的写法，解不开再换另一种",
                          "legacy": "legacy · CryptoJS/OpenSSL（官方插件那种）",
                          "aes-128-cbc-fixed": "aes-128-cbc-fixed · 固定 IV"},
        "domains": cc["domains"], "cookies_dir": str(COOKIES_DIR),
        "cookie_file": str(cfg.data.get("cookie_file") or DEFAULT_COOKIE_FILE),
        "state": st, "scheme_seen": str(st.get("scheme_seen") or ""),
        "platforms": [{"platform": k, "label": v, "file": str(platform_cookie_path(k))}
                      for k, v in PLATFORM_LABELS.items() if k != "default"],
    }


class CookieCloudAccountBody(BaseModel):
    server: Optional[str] = None
    uuid: Optional[str] = None
    key: Optional[str] = None
    clear_key: bool = False
    scheme: Optional[str] = None
    domains: Optional[str] = None
    enabled: Optional[bool] = None


@app.get("/api/cookiecloud")
def api_cookiecloud_get():
    return _cc_payload()


@app.post("/api/cookiecloud/account")
def api_cookiecloud_account(body: CookieCloudAccountBody, request: Request = None):
    """这几项只从这条口子写：机器令牌不该顺手把「往外送 Cookie」的开关和地址改掉。"""
    if request is not None and _auth_token_only(request):
        raise HTTPException(403, "机器令牌只开数据接口：CookieCloud 的服务器、UUID、密钥要从界面登录了再改")
    data = body.model_dump(exclude_none=True)
    upd: Dict[str, Any] = {}   # 只往带 cookiecloud_ 前缀的键上写，写成裸键的话配置根本存不住
    if "scheme" in data:
        scheme = str(data.get("scheme") or "").strip().lower()
        if scheme not in COOKIECLOUD_SCHEMES:
            raise HTTPException(400, f"加密方式只认 {' / '.join(COOKIECLOUD_SCHEMES)}，"
                                     f"收到的是「{str(data['scheme'])[:24]}」")
        upd["cookiecloud_scheme"] = scheme
    if "server" in data:
        server = str(data["server"] or "").strip()
        if server and not re.match(r"^https?://[^/]", server, re.I):
            raise HTTPException(400, "服务器地址要带 http:// 或 https://，后面还得跟上域名")
        # 存的时候就归一化：尾巴多打的斜杠收掉，界面回显与实际请求的是同一个串
        upd["cookiecloud_server"] = server.rstrip("/")
    if "uuid" in data:
        uid = str(data["uuid"] or "").strip()
        if uid and not _CC_UUID_RE.match(uid):
            raise HTTPException(400, "UUID 里只该有字母、数字和 - _ .")
        upd["cookiecloud_uuid"] = uid
    if "domains" in data:
        upd["cookiecloud_domains"] = str(data["domains"] or "").strip()
    if "enabled" in data:
        upd["cookiecloud_enabled"] = bool(data["enabled"])
    had_key = bool(str(cfg.data.get("cookiecloud_key") or "").strip())
    key_note = "密钥没动" if had_key else "密钥还没填"
    if bool(data.pop("clear_key", False)):
        cfg.data["cookiecloud_key"] = ""
        key_note = "密钥已清掉"
    else:
        new_key = str(data.pop("key", "") or "")
        if new_key:
            cfg.data["cookiecloud_key"] = new_key
            key_note = "密钥已更新" if had_key else "密钥已填上"
    cfg.data.update(upd)
    cfg.save()
    who = _cc_host(str(cfg.data.get("cookiecloud_server") or "")) or "地址没填"
    log_mgr.log(f"[CookieCloud] 设置已保存：{'开' if cfg.data.get('cookiecloud_enabled') else '关'} · "
                f"服务器 {who} · 加密 {cfg.data.get('cookiecloud_scheme')} · {key_note}")
    return _cc_payload()


def _cc_redact(text: str) -> str:
    """requests 的异常原话里带着 /get/<UUID>，这把 UUID 和密钥是一对，别把它抄进状态和日志。"""
    uid = str(cfg.data.get("cookiecloud_uuid") or "").strip()
    out = str(text or "")
    return out.replace(uid, "‹UUID›") if len(uid) >= 4 else out


def _cc_run(kind: str, label: str, fn) -> dict:
    """三个动作共用一条失败记录：失败了也要把时间和原话存进状态，界面上那句「上次测试」不能只报好消息。"""
    try:
        out = fn()
    except HTTPException as e:
        reason = _cc_redact(e.detail)
        _cc_state_save({f"last_{kind}_at": _cc_now(), f"last_{kind}_ok": False,
                        f"last_{kind}_error": reason[:180]})
        log_mgr.log(f"[CookieCloud] {label}没成：{reason[:160]}", "warning")
        raise
    except Exception as e:  # noqa: BLE001
        reason = _cc_redact(f"{type(e).__name__}: {e}")
        _cc_state_save({f"last_{kind}_at": _cc_now(), f"last_{kind}_ok": False,
                        f"last_{kind}_error": reason[:180]})
        log_mgr.log(f"[CookieCloud] {label}出错了：{reason[:140]}", "error")
        raise
    _cc_state_save({f"last_{kind}_at": _cc_now(), f"last_{kind}_ok": True,
                    f"last_{kind}_error": ""})   # 成功了要把上一次的错话擦掉，不然界面显示「通过：连不上…」
    return out


@app.post("/api/cookiecloud/test")
def api_cookiecloud_test():
    return _cc_run("test", "测试连接", _cc_do_test)


def _cc_do_test() -> dict:
    """只问一次、解一次，一个文件都不写：这条过了就说明地址、UUID、密钥、算法四样都对得上。"""
    cc = _cc_cfg()
    got = _cc_pull_rows(cc)
    cloud_domains = len({r["domain"] for r in got["rows"]})
    msg = (f"连上了：云端 {len(got['rows'])} 条 Cookie / {cloud_domains} 个域（加密 {got['scheme']}"
           + (f"，服务器标的写法是 {got['server_scheme']}" if got["server_scheme"] else "") + "）")
    if got["want"]:
        msg += f"；按填的 {len(got['want'])} 条域名过滤后本机要收 {len(got['kept'])} 条"
    _cc_state_save({"scheme_seen": got["scheme"]})
    log_mgr.log(f"[CookieCloud] 测试连接通过：云端 {len(got['rows'])} 条 / {cloud_domains} 个域，"
                f"加密 {got['scheme']}（这一趟没写盘）")
    return {"ok": True, "message": msg, "notes": got["notes"][:4], "cloud_rows": len(got["rows"]),
            "keep_rows": len(got["kept"]), "cloud_domains": cloud_domains, "domains": len(got["domains"]),
            "update_time": got["update_time"], "scheme": got["scheme"]}


@app.post("/api/cookiecloud/pull")
def api_cookiecloud_pull():
    return _cc_run("pull", "拉取", _cc_do_pull)


def _cc_do_pull() -> dict:
    """云端 → 本机：写 cookie_file 那份和匹配到的平台文件；一个 Cookie 都没命中的平台文件不动。"""
    cc = _cc_cfg()
    got = _cc_pull_rows(cc)
    rows = got["kept"]
    if not rows:
        raise HTTPException(400, f"云端那一份按域名过滤后一条都不剩（云端 {len(got['rows'])} 条，"
                                 f"被滤掉 {got['filtered_out']} 条）——把「域名过滤」清空或改成云端真有的域再来")
    targets: List[Tuple[Path, List[dict], str]] = [
        (Path(str(cfg.data.get("cookie_file") or DEFAULT_COOKIE_FILE)), rows, "全局 Cookie 文件")]
    by_plat: Dict[str, List[dict]] = {}
    for r in rows:
        p = _cc_platform_for(r["domain"])
        if p != "default":
            by_plat.setdefault(p, []).append(r)
    for p, rs in sorted(by_plat.items()):
        targets.append((platform_cookie_path(p), _cc_dedup(rs), PLATFORM_LABELS.get(p, p)))
    written: List[dict] = []
    for path, rs, label in targets:
        info = _cc_write_file(path, rs, label)
        if info["changed"] and label != "全局 Cookie 文件":
            for p in by_plat:
                if path == platform_cookie_path(p):
                    _login_flag_clear(p)
        written.append(info)
    now = _cc_now()
    changed = [w for w in written if w["changed"]]
    if changed:
        # Cookie 文件刚被换过内容：这条链接「匿名就够」的旧判定是配好之前的 Cookie 判出来的，不作废就会一直关掉刚同步来的那份
        drop_all_cookie_prefs()
    _cc_state_save({"pull_rows": len(rows),
                    "pull_domains": len(got["domains"]), "scheme_seen": got["scheme"],
                    "pull_files": [{"file": w["file"], "count": w["count"], "at": now} for w in written]})
    log_mgr.log(f"[CookieCloud] 拉取：云端 {len(got['rows'])} 条 → 收下 {len(rows)} 条"
                f"（{len(got['domains'])} 个域，加密 {got['scheme']}），写了 {len(changed)} 个文件："
                + ("、".join(f"{w['file']}({w['count']} 条)" for w in changed) if changed else "内容一样，没动"))
    for w in changed:
        if w["backup"]:
            log_mgr.log(f"[CookieCloud] {w['file']} 覆盖前的原样备份为 {w['backup']}")
    for n in got["notes"][:3]:
        log_mgr.log(f"[CookieCloud] {n}", "warning")
    return {"ok": True, "message": f"{now} 拉下 {len(rows)} 条 / {len(got['domains'])} 个域，"
                                   f"写了 {len(changed)} 个文件"
                                   + ("" if changed else "（本机这几份本来就是这个内容，一个文件都没动）"),
            "files": written, "notes": got["notes"][:4], "cloud_rows": len(got["rows"]),
            "filtered_out": got["filtered_out"], "scheme": got["scheme"], "update_time": got["update_time"]}


@app.post("/api/cookiecloud/push")
def api_cookiecloud_push():
    return _cc_run("push", "推送", _cc_do_push)


def _cc_do_push() -> dict:
    """本机 → 云端：整份覆盖服务器上那个 UUID 的数据，所以只由界面上确认过的按钮触发。"""
    cc = _cc_cfg()
    _cc_ready(cc)
    rows, files = _cc_local_rows()
    if not rows:
        raise HTTPException(400, f"本机没有可推的 Cookie 文件（读的是 "
                                 f"{str(cfg.data.get('cookie_file') or DEFAULT_COOKIE_FILE)} 和 "
                                 "cookies\\<平台>_cookies.txt，一个都没读到内容）")
    st = _cc_state()
    seen = str(st.get("scheme_seen") or "")
    scheme = cc["scheme"] if cc["scheme"] in COOKIECLOUD_WRITE_SCHEMES else (
        seen if seen in COOKIECLOUD_WRITE_SCHEMES else "legacy")
    groups: Dict[str, List[dict]] = {}
    for r in rows:
        groups.setdefault(r["domain"], []).append({
            "name": r["name"], "value": r["value"], "domain": r["domain"], "path": r["path"],
            "secure": r["secure"], "hostOnly": not r["domain"].startswith("."),
            "session": not r["expires"], "expirationDate": r["expires"] or None,
        })
    payload = {"cookie_data": groups, "local_storage_data": {}, "update_time": datetime.now().isoformat()}
    blob = _cc_encrypt(payload, cc, scheme)
    url = _cc_endpoint(cc["server"], "/update")
    code, data, err = _cc_http(url, {"uuid": cc["uuid"], "encrypted": blob, "crypto_type": scheme})
    if err:
        raise HTTPException(502, err)
    action = str(data.get("action") or "").strip().lower()
    if code != 200:
        raise HTTPException(502, f"服务器没收下（HTTP {code}）：{str(data.get('_text') or data)[:160]}")
    if action and action != "done":
        raise HTTPException(502, f"服务器回了 action={action}，没写成（它自己的日志里应该有原因）")
    now = _cc_now()
    _cc_state_save({"push_rows": len(rows),
                    "push_domains": len(groups), "scheme_seen": scheme,
                    "push_files": [Path(f).name for f in files]})
    log_mgr.log(f"[CookieCloud] 推送：本机 {len(rows)} 条 / {len(groups)} 个域（来自 {len(files)} 个文件）"
                f"已覆盖云端那一份，写法 {scheme}" + ("，服务器回 action=done" if action == "done" else ""))
    return {"ok": True, "message": f"{now} 推了 {len(rows)} 条 / {len(groups)} 个域（{scheme}），云端那一份已被覆盖",
            "rows": len(rows), "domains": len(groups), "scheme": scheme,
            "from_files": [Path(f).name for f in files]}


# ==================== 按龄清理（#31） ====================
# 三条口径是这一路的地基，动代码前先想清楚：
# 1) 下载成品不硬删 —— 先挪进 <下载目录>/_cleanup_trash/，在回收目录里待够 cleanup_trash_days
#    天才真删。日志归档是唯一直接删的一组（它记的就是这台机器自己跑过什么）。
# 2) 过期与否只认文件 mtime —— 历史里的时间、文件名里的日期都可能是下载器按元数据写死的，
#    mtime 才是「这个文件最后一次被动过」的真实时间。
# 3) 自动那一趟永远只碰日志归档、编辑备份和到期的回收目录 —— 下载目录里的东西必须用户看过
#    名单、点过「按名单删除」才动手，而 run 只认刚生成、还没过期的那份名单指纹。
CL_TRASH_DIRNAME = "_cleanup_trash"
CL_SCAN_CAP = 20000      # 一趟最多翻这么多文件：目录被挪到别处、深到没边时不把进程拖死
CL_LIST_CAP = 200        # 名单一次最多逐条列这么多，其余的只报条数和体积
CL_AUTO_HOUR = 3         # 每天这一趟自动跑（本地时区）
CL_AUTO_MIN = 5
CL_PLAN_TTL = 600        # 「先看名单」到「按名单删除」之间的有效期（秒）
CL_IN_PROGRESS_EXTS = (".part", ".ytdl", ".temp", ".aria2")   # 归 /api/cleanup-parts，这里不抢它的活
CL_SUBTITLE_EXTS = (".srt", ".vtt", ".ass", ".ssa", ".lrc", ".nfo")
CL_VIDEO_EXTS = (".mp4", ".mkv", ".webm", ".flv", ".ts", ".mov", ".avi", ".m4s")
CL_GROUPS = ("logs", "backups", "downloads", "trash")
CL_GROUP_LABELS = {"logs": "日志归档", "backups": "编辑备份", "downloads": "下载成品", "trash": "回收目录到期"}
# 自动那一趟能碰的组。downloads 不在里面 —— 这一条就是「自动只清程序自己造的垃圾」的落点。
CL_AUTO_GROUPS = ("logs", "backups", "trash")
CL_SKIP_DIRS = {"__pycache__", ".git", "node_modules", "runtime", "dist", "tools", CL_TRASH_DIRNAME}
CL_LOG_ARCHIVE_RE = re.compile(r"^app-\d{4}-\d{2}-\d{2}\.log$")
_CL_PLAN: Dict[str, Any] = {"hash": "", "at": 0.0, "days": {}}   # 名单指纹只在内存里：重启即失效，删不动
_CL_LOCK = threading.Lock()


def _cl_norm(p: Any) -> str:
    """路径的比较用键：正反斜杠、结尾分隔符、大小写都不该让两个名字看起来像两个文件。"""
    return str(p).replace("/", "\\").rstrip("\\").lower()


def _cl_int(key: str, default: int) -> int:
    try:
        v = int(float(cfg.data.get(key, default)))
    except Exception:
        return default
    return max(0, min(3650, v))


def _cl_cfg() -> dict:
    return {
        "enabled": bool(cfg.data.get("cleanup_enabled")),
        "log_days": _cl_int("cleanup_log_days", 7),
        "backup_days": _cl_int("cleanup_backup_days", 0),
        "download_days": _cl_int("cleanup_download_days", 0),
        "trash_days": _cl_int("cleanup_trash_days", 30),
    }


def _cl_download_root() -> Path:
    return Path(str(cfg.data.get("download_dir") or DEFAULT_DOWNLOAD_DIR))


def _cl_trash_root() -> Path:
    return _cl_download_root() / CL_TRASH_DIRNAME


def _cl_media_exts() -> set:
    """下载目录里按「成品」认的扩展名。音频口径跟 scan_library 取同一份，别自己另写一套。"""
    try:
        from music_search import MUSIC_AUDIO_EXTS
        audio = {e for e in MUSIC_AUDIO_EXTS if e != ".webm"}
    except Exception:
        audio = {".mp3", ".m4a", ".flac", ".opus", ".ogg", ".wav", ".aac", ".m4b", ".wma"}
    return set(CL_VIDEO_EXTS) | audio | set(CL_SUBTITLE_EXTS)


def _cl_walk(root: Path, match, skip: set) -> tuple:
    """按名字挑文件。返回 (命中, 翻过的文件数, 是否被上限截断)。

    用 os.walk 而不是 rglob，是为了能在中途数到上限就收口，也让每一层都能把要跳过的目录
    从 dirnames 里摘掉；os.walk 默认不跟随符号链接的目录，这一路也因此不会顺着链接跑出根外。
    """
    hits: List[Path] = []
    seen = 0
    trunc = False
    try:
        if not root.is_dir():
            return hits, seen, trunc
    except Exception:
        return hits, seen, trunc
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d.lower() not in skip and not d.startswith(".")]
        for fn in filenames:
            seen += 1
            if seen > CL_SCAN_CAP:
                trunc = True
                break
            p = Path(dirpath) / fn
            try:
                if p.is_symlink():
                    continue
            except Exception:
                continue
            try:
                if match(fn, p):
                    hits.append(p)
            except Exception:
                continue
        if trunc:
            break
    return hits, seen, trunc


def _cl_busy() -> tuple:
    """正在下、排队中、暂停/稍后、以及还在做种的任务占住的路径。

    返回 (精确路径集合, 目录前缀集合)。做种中的那一整条目录都要护住：种子目录下每个文件
    的 mtime 都可能很旧，按龄看它们全该删，而它们其实正被占用。
    """
    exact, prefixes = set(), set()
    try:
        tasks = list(queue.tasks.values())
    except Exception:
        return exact, prefixes
    hold = {TaskStatus.QUEUED.value, TaskStatus.DOWNLOADING.value,
            TaskStatus.PAUSED.value, TaskStatus.LATER.value}
    for t in tasks:
        try:
            busy = str(getattr(t, "status", "")) in hold or bool(getattr(t, "seeding", False))
            if not busy:
                continue
            for v in (getattr(t, "filepath", ""), getattr(t, "result_dir", "")):
                s = str(v or "").strip()
                if not s:
                    continue
                exact.add(_cl_norm(s))
                prefixes.add(_cl_norm(s))
                for e in CL_IN_PROGRESS_EXTS:
                    exact.add(_cl_norm(s + e))
        except Exception:
            continue
    return exact, prefixes


def _cl_blocked(p: Path, exact: set, prefixes: set) -> bool:
    k = _cl_norm(p)
    if k in exact:
        return True
    for pre in prefixes:
        if k == pre or k.startswith(pre + "\\"):
            return True
    return False


def _cl_row(group: str, p: Path, st, now: float, base: Path) -> dict:
    try:
        rel = str(p.relative_to(base))
    except Exception:
        rel = p.name
    return {
        "id": hashlib.md5(str(p).encode("utf-8")).hexdigest()[:12],
        "group": group,
        "label": CL_GROUP_LABELS.get(group, group),
        "path": str(p),
        "name": p.name,
        "rel": rel,
        "bytes": int(getattr(st, "st_size", 0) or 0),
        "mtime": int(getattr(st, "st_mtime", 0) or 0),
        "mtime_str": datetime.fromtimestamp(getattr(st, "st_mtime", 0) or 0).strftime("%Y-%m-%d %H:%M"),
        "age_days": round(max(0.0, (now - getattr(st, "st_mtime", now)) / 86400.0), 1),
        # 前端要说清这条是「挪进回收目录」还是「直接删」：只有日志那组是后者
        "hard": group in ("logs", "trash"),
    }


def _cl_manifest_path() -> Path:
    return _cl_trash_root() / "manifest.json"


def _cl_manifest() -> List[dict]:
    """回收目录的账本：每条记原位置、挪走的时间、体积。真删与还原都按这本账走。

    过期判定用的是 moved_at（挪进来的时间），不是文件 mtime —— 一条去年下完的片子今天
    被挪进回收目录，它在这里的 30 天才从今天算起。
    """
    try:
        raw = json.loads(_cl_manifest_path().read_text(encoding="utf-8"))
        rows = raw.get("entries") if isinstance(raw, dict) else raw
        return [r for r in (rows or []) if isinstance(r, dict)]
    except Exception:
        return []


def _cl_manifest_save(entries: List[dict]):
    try:
        tmp = Path(str(_cl_manifest_path()) + ".tmp")
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps({"entries": entries}, ensure_ascii=False, indent=1),
                       encoding="utf-8", newline="\n")
        os.replace(tmp, _cl_manifest_path())
    except Exception as e:
        log_mgr.log(f"[清理] 回收目录的账本没写下去（{type(e).__name__}），"
                    "界面上这些条目的原位置与到期时间这次会不准", "warning")


def _cl_collect(group: str, days: int, now: float, busy: tuple) -> dict:
    """一组里过期的那些文件（还没截断成名单，全量都在 rows 里）。"""
    info = {"rows": [], "scanned": 0, "truncated": False, "busy_skipped": 0, "bytes": 0,
            "days": days, "label": CL_GROUP_LABELS.get(group, group), "note": ""}
    if days <= 0:
        info["note"] = "这一档天数填的 0：不碰"
        return info
    cutoff = now - days * 86400.0
    exact, prefixes = busy
    out: List[Path] = []
    seen = 0
    trunc = False
    if group == "logs":
        for base in (APP_DIR, STATE_DIR):
            hits, s, t = _cl_walk(base, lambda fn, p: bool(CL_LOG_ARCHIVE_RE.match(fn)), CL_SKIP_DIRS)
            out += hits
            seen += s
            trunc = trunc or t
    elif group == "backups":
        for base in (_cl_download_root(), COOKIES_DIR, APP_DIR):
            hits, s, t = _cl_walk(base, lambda fn, p: ".bak-" in fn.lower(), CL_SKIP_DIRS)
            out += hits
            seen += s
            trunc = trunc or t
    elif group == "downloads":
        exts = _cl_media_exts()

        def _m(fn, p):
            e = Path(fn).suffix.lower()
            return e in exts and e not in CL_IN_PROGRESS_EXTS and not fn.startswith(".")
        out, seen, trunc = _cl_walk(_cl_download_root(), _m, CL_SKIP_DIRS)
    else:   # trash：按账本里的 moved_at 判过期，账本外（手工丢进去的）按 mtime 兜底
        trash = _cl_trash_root()
        by_path = {}
        for r in _cl_manifest():
            moved = str(r.get("moved") or "")
            if moved:
                by_path[_cl_norm(trash / moved)] = r
        hits, seen, trunc = _cl_walk(trash, lambda fn, p: fn != "manifest.json" and p.is_file(), set())
        rows = []
        for p in hits:
            try:
                st = p.stat()
            except Exception:
                continue
            ent = by_path.get(_cl_norm(p))
            ts = float(ent.get("moved_at") or 0) if ent else 0.0
            if ts <= 0:
                ts = st.st_mtime
            if ts < cutoff:
                row = _cl_row(group, p, st, now, trash)
                if ent:
                    row["orig"] = str(ent.get("orig") or "")
                row["mtime"] = int(ts)      # 展示的是进回收目录的时间，不是文件原本的 mtime
                row["mtime_str"] = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
                row["age_days"] = round(max(0.0, (now - ts) / 86400.0), 1)
                rows.append(row)
        rows.sort(key=lambda r: (-r["bytes"], r["name"]))
        info["rows"] = rows
        info["scanned"] = seen
        info["truncated"] = trunc
        info["bytes"] = sum(r["bytes"] for r in rows)
        return info
    rows, skipped, dedup = [], 0, set()
    for p in out:
        k = _cl_norm(p)
        if k in dedup:      # STATE_DIR == APP_DIR 是常态：同一份归档会被两个根各数一次
            continue
        dedup.add(k)
        try:
            st = p.stat()
        except Exception:
            continue
        if st.st_mtime >= cutoff:
            continue
        if group == "downloads" and _cl_blocked(p, exact, prefixes):
            skipped += 1
            continue
        rows.append(_cl_row(group, p, st, now, _cl_download_root() if group == "downloads" else STATE_DIR))
    rows.sort(key=lambda r: (-r["bytes"], r["name"]))
    info["rows"] = rows
    info["scanned"] = seen
    info["truncated"] = trunc
    info["busy_skipped"] = skipped
    info["bytes"] = sum(r["bytes"] for r in rows)
    return info


def _cl_hash_of(groups: dict) -> str:
    parts = []
    for g in CL_GROUPS:
        parts.append(g + ":" + ",".join(r["id"] for r in groups[g]["rows"]))
    return hashlib.md5("|".join(parts).encode("utf-8")).hexdigest()[:16]


def _cl_plan(now: float = None) -> dict:
    """算一遍四组的名单。只读：不删、不挪、不改缓存，所以「先看名单」没有副作用。"""
    now = time.time() if now is None else now
    c = _cl_cfg()
    busy = _cl_busy()
    days = {"logs": c["log_days"], "backups": c["backup_days"],
            "downloads": c["download_days"], "trash": c["trash_days"]}
    groups: Dict[str, Any] = {}
    total_n = total_b = 0
    for g in CL_GROUPS:
        info = _cl_collect(g, days[g], now, busy)
        rows = info["rows"]
        groups[g] = {
            "group": g, "label": info["label"], "days": info["days"], "note": info["note"],
            "count": len(rows), "bytes": info["bytes"], "scanned": info["scanned"],
            "truncated": info["truncated"], "busy_skipped": info["busy_skipped"],
            "hard": g in ("logs", "trash"),
            "rows": rows[:CL_LIST_CAP],
            "hidden": max(0, len(rows) - CL_LIST_CAP),
        }
        total_n += len(rows)
        total_b += info["bytes"]
    h = _cl_hash_of(groups)
    if h != _CL_PLAN.get("hash"):
        _CL_PLAN.update({"hash": h, "at": now, "days": dict(days)})
    return {"ok": True, "hash": h, "issued_at": now,
            "issued_str": datetime.fromtimestamp(now).strftime("%Y-%m-%d %H:%M:%S"),
            "ttl": CL_PLAN_TTL, "enabled": c["enabled"], "days": days,
            "groups": groups, "total_count": total_n, "total_bytes": total_b,
            "auto_groups": list(CL_AUTO_GROUPS), "trash_dir": str(_cl_trash_root())}


def _cl_forget_library(paths: List[str]) -> int:
    """把已经不在原位的成品从 library_cache.json 里摘掉，免得媒体库继续显示一份挪走的东西。

    下次 /api/library?refresh=1 或手动扫描本来就会按磁盘重建，这里只是让「删完立刻回看」
    不出现幽灵行。
    """
    keys = {_cl_norm(p) for p in paths}
    try:
        items = json.loads(LIBRARY_CACHE.read_text(encoding="utf-8"))
        if not isinstance(items, list):
            return 0
    except Exception:
        return 0
    kept, dropped = [], 0
    for it in items:
        p = _cl_norm(it.get("path") if isinstance(it, dict) else "")
        if p and (p in keys or any(p.startswith(k + "\\") for k in keys)):
            dropped += 1
            continue
        kept.append(it)
    if dropped:
        try:
            LIBRARY_CACHE.write_text(json.dumps(kept, ensure_ascii=False, indent=1), encoding="utf-8")
        except Exception:
            pass
    return dropped


def _cl_trash_dest(src: Path, rel: str) -> Path:
    """回收目录里保住相对路径，还原时一眼能看出它原来在库里的哪一层；重名往后加序号。"""
    trash = _cl_trash_root()
    dest = trash / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    i = 1
    while dest.exists():
        dest = dest.with_name(f"{Path(rel).name}.clash{i}")
        i += 1
    return dest


def _cl_apply(groups: List[str], expect_hash: str = "", by: str = "manual") -> dict:
    """按名单动手。groups 只认组名，不接受客户端传来的路径 —— 路径一律由服务端重算。"""
    bad = [g for g in groups if g not in CL_GROUPS]
    if bad:
        raise HTTPException(400, f"不认识的清理组：{' / '.join(bad)}")
    if not groups:
        raise HTTPException(400, "没说要清哪一组")
    if by != "auto":
        # 手工这一趟必须带刚生成的名单指纹：没看过名单（或看完又拖过了 10 分钟）就删不了
        if not expect_hash:
            raise HTTPException(400, "先点「先看名单」看过要删的东西，再回来点删除")
        if _CL_PLAN.get("hash") != expect_hash:
            raise HTTPException(409, "名单指纹对不上：要么还没生成过名单，要么这中间磁盘上的东西变了，重新看一遍")
        if time.time() - float(_CL_PLAN.get("at") or 0) > CL_PLAN_TTL:
            raise HTTPException(409, f"名单已经过了有效期（{CL_PLAN_TTL // 60} 分钟），重新看一遍再删")
    plan = _cl_plan()
    if expect_hash and plan["hash"] != expect_hash:
        raise HTTPException(409, "名单在这一趟运行前变了（有新文件到期或旧文件被移走），请重新看过再删")
    busy = _cl_busy()
    exact, prefixes = busy
    moved: List[dict] = []
    deleted: List[dict] = []
    errors: List[str] = []
    gone: List[str] = []          # 挪出原位的文件，攒到最后一次性从媒体库缓存里摘掉
    skipped_busy = 0
    entries = _cl_manifest()
    by_key = {_cl_norm(_cl_trash_root() / str(r.get("moved") or "")): r for r in entries}
    touched_manifest = False
    for g in groups:
        for r in plan["groups"][g]["rows"]:
            p = Path(r["path"])
            try:
                if not p.exists():
                    continue
                if _cl_blocked(p, exact, prefixes):
                    skipped_busy += 1
                    continue
                if g in ("logs", "trash"):
                    ent = by_key.get(_cl_norm(p))
                    if g == "trash":
                        entries = [x for x in entries if x is not ent]
                        touched_manifest = True
                    p.unlink()
                    deleted.append({"group": g, "name": r["name"], "bytes": r["bytes"],
                                    "orig": str((ent or {}).get("orig") or "")})
                    continue
                rel = _cl_rel_for(p)
                dest = _cl_trash_dest(p, rel)
                shutil.move(str(p), str(dest))
                ent = {"id": hashlib.md5(str(dest).encode("utf-8")).hexdigest()[:12],
                       "group": g, "orig": str(p), "moved": str(dest.relative_to(_cl_trash_root())),
                       "moved_at": time.time(), "bytes": r["bytes"], "name": r["name"]}
                entries.append(ent)
                touched_manifest = True
                moved.append({"group": g, "name": r["name"], "bytes": r["bytes"],
                              "orig": str(p), "moved": ent["moved"]})
                gone.append(str(p))
            except Exception as e:
                errors.append(f"{r['name']}：{type(e).__name__} {str(e)[:90]}")
    if touched_manifest:
        _cl_manifest_save(entries)
    if gone:
        _cl_forget_library(gone)
    if any(g == "trash" for g in groups):
        _cl_prune_empty_trash()
    now = datetime.now()
    st = _cl_state()
    hidden = sum(plan["groups"][g]["hidden"] for g in groups)
    done = {"by": by, "at": now.strftime("%Y-%m-%d %H:%M:%S"), "groups": list(groups),
            "moved": len(moved), "deleted": len(deleted), "bytes":
                sum(x["bytes"] for x in moved) + sum(x["bytes"] for x in deleted),
            "errors": len(errors), "hidden": hidden}
    patch = {"last_run": done, ("last_auto" if by == "auto" else "last_manual"): done,
             "auto_date": now.strftime("%Y-%m-%d") if by == "auto" else st.get("auto_date", "")}
    _cl_state_save(patch)
    mb = done["bytes"] / 1048576.0
    log_mgr.log(f"[清理] {'自动' if by == 'auto' else '手动'}一趟（{'/'.join(groups)}）："
                f"挪进回收目录 {len(moved)} 个、直接删 {len(deleted)} 个，"
                f"腾出 {mb:.1f} MB"
                + (f"，护住正在下/做种的 {skipped_busy} 个" if skipped_busy else "")
                + (f"，另有 {hidden} 个同规则但没进这份名单" if hidden else "")
                + (f"，{len(errors)} 个没动成（{errors[0]}）" if errors else ""))
    return {"ok": True, "by": by, "groups": list(groups), "moved": moved, "deleted": deleted,
            "count": len(moved) + len(deleted), "bytes": done["bytes"],
            "hidden": hidden, "skipped_busy": skipped_busy, "errors": errors[:8],
            "trash_dir": str(_cl_trash_root()),
            "message": f"{'自动' if by == 'auto' else ''}清理：{len(moved)} 个挪进回收目录、"
                       f"{len(deleted)} 个直接删，腾出 {mb:.1f} MB"
                       + (f"（{skipped_busy} 个正在下或在做种，护住了）" if skipped_busy else "")
                       + (f"；还有 {hidden} 个同规则的没列进名单，下一轮再清" if hidden else "")}


def _cl_rel_for(p: Path) -> str:
    """进回收目录时用的相对路径：下载目录下的保持相对，其余按「组/文件名」放。"""
    try:
        return str(p.relative_to(_cl_download_root()))
    except Exception:
        pass
    for base, tag in ((COOKIES_DIR, "cookies"), (STATE_DIR, "state"), (APP_DIR, "app")):
        try:
            return str(Path(tag) / p.relative_to(base))
        except Exception:
            continue
    return p.name


def _cl_prune_empty_trash():
    """真删过后把空壳目录收掉，回收目录里只留账本。"""
    trash = _cl_trash_root()
    if not trash.is_dir():
        return
    for dirpath, dirnames, filenames in sorted(os.walk(trash), key=lambda x: -len(x[0])):
        if dirpath == str(trash):
            continue
        try:
            if not os.listdir(dirpath):
                os.rmdir(dirpath)
        except Exception:
            pass


def _cl_state() -> dict:
    try:
        raw = json.loads(CLEANUP_STATE_FILE.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def _cl_state_save(patch: dict) -> dict:
    st = _cl_state()
    st.update(patch)
    try:
        tmp = Path(str(CLEANUP_STATE_FILE) + ".tmp")
        tmp.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
        os.replace(tmp, CLEANUP_STATE_FILE)
    except Exception as e:
        log_mgr.log(f"[清理] 清理状态没写下去（{type(e).__name__}），界面上「上次跑」的时间这次不会更新", "warning")
    return st


def _cl_restore_trash() -> List[dict]:
    """回收目录里还能还原的条目（账本里有原位置的）。"""
    trash = _cl_trash_root()
    out = []
    for r in _cl_manifest():
        moved = str(r.get("moved") or "")
        if not moved:
            continue
        p = trash / moved
        if not p.is_file():
            continue
        out.append({"id": r.get("id", ""), "name": str(r.get("name") or p.name),
                    "bytes": int(r.get("bytes") or 0), "group": str(r.get("group") or ""),
                    "orig": str(r.get("orig") or ""), "moved": moved,
                    "moved_at": float(r.get("moved_at") or 0),
                    "moved_str": datetime.fromtimestamp(float(r.get("moved_at") or 0)).strftime("%Y-%m-%d %H:%M")
                                 if r.get("moved_at") else "",
                    "path": str(p)})
    return out


def _cl_restore(ids: List[str]) -> dict:
    """从回收目录放回原位。原位置已经有文件就不覆盖 —— 那份可能是重新下过的新东西。"""
    want = {str(i) for i in (ids or []) if str(i)}
    if not want:
        raise HTTPException(400, "没说要还原哪几条")
    entries = _cl_manifest()
    trash = _cl_trash_root()
    restored, refused, errors = [], [], []
    left = []
    for r in entries:
        if r.get("id") in want:
            p = trash / str(r.get("moved") or "")
            orig = Path(str(r.get("orig") or ""))
            if not p.is_file():
                errors.append(f"{r.get('name')}：回收目录里已经找不到这个文件")
                left.append(r)
                continue
            if not orig.parent.is_dir() or orig.exists():
                refused.append({"name": str(r.get("name") or p.name), "orig": str(orig),
                                "why": "原位置已经有同名文件（没覆盖）" if orig.exists()
                                       else "原位置的目录已经不存在"})
                left.append(r)
                continue
            try:
                shutil.move(str(p), str(orig))
                restored.append({"name": orig.name, "path": str(orig)})
            except Exception as e:
                errors.append(f"{r.get('name')}：{type(e).__name__} {str(e)[:90]}")
                left.append(r)
                continue
            continue
        left.append(r)
    if len(left) != len(entries):
        _cl_manifest_save(left)
    if restored or refused or errors:
        parts = [f"{len(restored)} 个回到原位"] if restored else []
        if refused:
            parts.append(f"{len(refused)} 个原位置被占（没动）")
        if errors:
            parts.append(f"{len(errors)} 个没成")
        log_mgr.log("[清理] 还原：" + "，".join(parts))
    return {"ok": True, "restored": restored, "refused": refused, "errors": errors[:8],
            "count": len(restored),
            "message": f"放回原位 {len(restored)} 个"
                       + (f"，{len(refused)} 个原位置已经有同名文件（没覆盖）" if refused else "")
                       + (f"，{len(errors)} 个没成" if errors else "")}


def _cl_next_wake_ts(now_ts: float = None) -> float:
    """下一个 CL_AUTO_HOUR:CL_AUTO_MIN 的时间戳。

    跨夏令时那一圈可能差一个小时：一天只跑一趟家务活，差一小时不影响它跑不跑。
    """
    now_ts = time.time() if now_ts is None else now_ts
    lt = time.localtime(now_ts)
    target = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, CL_AUTO_HOUR, CL_AUTO_MIN, 0, 0, 0, -1))
    if now_ts >= target:
        target += 86400
    return target


def _cl_auto_pass(by: str = "auto") -> dict:
    """自动那一趟：只走 CL_AUTO_GROUPS，天数填 0 的组自动跳过。"""
    c = _cl_cfg()
    if not c["enabled"]:
        return {"ok": True, "skipped": "开关没开", "count": 0}
    days = {"logs": c["log_days"], "backups": c["backup_days"], "trash": c["trash_days"]}
    groups = [g for g in CL_AUTO_GROUPS if days.get(g, 0) > 0]
    if not groups:
        return {"ok": True, "skipped": "日志/备份/回收目录三档天数都填的 0", "count": 0}
    return _cl_apply(groups, by=by)


def _cl_auto_due() -> bool:
    """今天那个点已过、而今天这一趟还没跑过，才补。"""
    if not _cl_cfg()["enabled"]:
        return False
    now = time.time()
    lt = time.localtime(now)
    today_target = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday,
                                CL_AUTO_HOUR, CL_AUTO_MIN, 0, 0, 0, -1))
    if now < today_target:
        return False
    today = datetime.now().strftime("%Y-%m-%d")
    st = _cl_state()
    if str(st.get("auto_date") or "") == today:
        return False
    return not str((st.get("last_auto") or {}).get("at") or "").startswith(today)


def _cl_fire():
    with _CL_LOCK:
        _CL_TIMER["timer"] = None
        _CL_TIMER["wake_at"] = 0.0
    try:
        _cl_auto_pass()
    except Exception as e:
        log_mgr.log(f"[清理] 自动那一趟没跑成（{type(e).__name__}）：{str(e)[:120]}", "warning")
    _cl_arm()


_CL_TIMER: Dict[str, Any] = {"timer": None, "wake_at": 0.0, "lock": threading.Lock()}


def _cl_arm():
    """按真实剩余时间排一次性闹钟，响过再排下一次（跟定时窗那个闹钟一个写法）。"""
    with _CL_TIMER["lock"]:
        until = _cl_next_wake_ts()
        t = _CL_TIMER["timer"]
        if t is not None and _CL_TIMER["wake_at"] <= until and t.is_alive():
            return
        if t is not None:
            t.cancel()
        _CL_TIMER["wake_at"] = until
        nt = threading.Timer(max(5.0, until - time.time()), _cl_fire)
        nt.daemon = True
        _CL_TIMER["timer"] = nt
        nt.start()


def start_cleanup_scheduler():
    """开机排闹钟，并补上「进程在每天那个点之后才起来」漏掉的一趟。"""
    _cl_arm()
    try:
        if _cl_auto_due():
            log_mgr.log("[清理] 今天那一趟自动清理还没跑，开机补一次")
            _cl_auto_pass()
    except Exception as e:
        log_mgr.log(f"[清理] 开机补跑没跑成（{type(e).__name__}）：{str(e)[:120]}", "warning")


def _cl_payload() -> dict:
    c = _cl_cfg()
    st = _cl_state()
    trash = _cl_trash_root()
    # 账本自己不算「回收目录里的文件」：不然空目录会报成 1 个
    n = sum(1 for p in trash.rglob("*") if p.is_file() and p.name != "manifest.json") if trash.is_dir() else 0
    return {
        "enabled": c["enabled"], "log_days": c["log_days"], "backup_days": c["backup_days"],
        "download_days": c["download_days"], "trash_days": c["trash_days"],
        "auto_groups": list(CL_AUTO_GROUPS), "list_cap": CL_LIST_CAP, "plan_ttl": CL_PLAN_TTL,
        "auto_hour": f"{CL_AUTO_HOUR:02d}:{CL_AUTO_MIN:02d}",
        "download_dir": str(_cl_download_root()), "trash_dir": str(trash),
        "trash_count": n, "state": st, "last_auto": st.get("last_auto") or {},
        "last_manual": st.get("last_manual") or {},
        "labels": CL_GROUP_LABELS,
    }


class CleanupAccountBody(BaseModel):
    enabled: Optional[bool] = None
    log_days: Optional[int] = None
    backup_days: Optional[int] = None
    download_days: Optional[int] = None
    trash_days: Optional[int] = None


class CleanupRunBody(BaseModel):
    hash: str = ""
    groups: List[str] = []


class CleanupRestoreBody(BaseModel):
    ids: List[str] = []


@app.get("/api/cleanup")
def api_cleanup_get():
    return _cl_payload()


@app.get("/api/cleanup/trash")
def api_cleanup_trash():
    """回收目录里现在有什么、各来自哪儿（界面上的「回收目录」列表）。"""
    rows = _cl_restore_trash()
    return {"ok": True, "trash_dir": str(_cl_trash_root()), "count": len(rows),
            "bytes": sum(r["bytes"] for r in rows), "rows": rows[:CL_LIST_CAP],
            "hidden": max(0, len(rows) - CL_LIST_CAP)}


@app.post("/api/cleanup/account")
def api_cleanup_account(body: CleanupAccountBody, request: Request = None):
    """清理参数只从这条口子写：机器令牌不该顺手把「会删文件」的开关打开。"""
    if request is not None and _auth_token_only(request):
        raise HTTPException(403, "机器令牌只开数据接口：按龄清理的开关和天数要从界面登录了再改")
    data = body.model_dump(exclude_none=True)
    upd: Dict[str, Any] = {}
    if "enabled" in data:
        upd["cleanup_enabled"] = bool(data["enabled"])
    for k, key in (("log_days", "cleanup_log_days"), ("backup_days", "cleanup_backup_days"),
                   ("download_days", "cleanup_download_days"), ("trash_days", "cleanup_trash_days")):
        if k in data:
            try:
                v = int(float(data[k]))
            except Exception:
                raise HTTPException(400, f"{CL_GROUP_LABELS.get(k, k)}的天数要填整数（0 表示这一档不碰）")
            if v < 0 or v > 3650:
                raise HTTPException(400, f"{k} 只认 0–3650 天，收到的是 {v}")
            upd[key] = v
    if not upd:
        raise HTTPException(400, "没说要改哪一项")
    cfg.data.update(upd)
    cfg.save()
    _cl_arm()   # 天数、开关刚改过，闹钟按新时间重排
    if "cleanup_enabled" in upd:
        log_mgr.log(f"[清理] 按龄自动清理{'已打开' if upd['cleanup_enabled'] else '已关掉'}"
                    f"（日志 {int(cfg.data.get('cleanup_log_days', 7))} 天 / 备份 "
                    f"{int(cfg.data.get('cleanup_backup_days', 0))} 天 / 下载 "
                    f"{int(cfg.data.get('cleanup_download_days', 0))} 天 / 回收目录 "
                    f"{int(cfg.data.get('cleanup_trash_days', 30))} 天）")
    return {"ok": True, **_cl_payload()}


@app.post("/api/cleanup/preview")
def api_cleanup_preview():
    """干跑：只算名单，不删不挪。返回的指纹是给「按名单删除」用的。"""
    plan = _cl_plan()
    log_mgr.log(f"[清理] 看名单：日志 {plan['groups']['logs']['count']} 个 / 备份 "
                f"{plan['groups']['backups']['count']} 个 / 下载成品 {plan['groups']['downloads']['count']} 个 / "
                f"回收目录到期 {plan['groups']['trash']['count']} 个，"
                f"合计 {plan['total_bytes'] / 1048576.0:.1f} MB（一个都没动）")
    return plan


@app.post("/api/cleanup/run")
def api_cleanup_run(body: CleanupRunBody):
    with _CL_LOCK:
        return _cl_apply([g for g in (body.groups or []) if g], expect_hash=str(body.hash or ""))


@app.post("/api/cleanup/restore")
def api_cleanup_restore(body: CleanupRestoreBody):
    return _cl_restore(list(body.ids or []))


class MusicCookieBody(BaseModel):
    platform: str
    cookie: str = ""


# --------------------------------------------------------------- 音乐平台登录 Cookie
# musicdl 的网易云 / QQ / 酷狗三个源都是「带着登录 Cookie 才去够无损那一档」：
# 各源里都写着 lossless_quality_is_sufficient = False if cookies else True。
# 认哪些键照抄 musicdl 自己读 cookie 的那几行（sources/netease.py、utils/qqutils.py 的
# Credential.fromcookiesdict、utils/kugouutils.py 的 sendrequest），不自己臆造键名。
MUSIC_COOKIE_PLATFORMS: List[tuple] = [
    # (平台键, 界面名, musicdl 源名, 必需 Cookie 键（同组任一命中即可）, 去哪儿拿这条 Cookie)
    ("netease", "网易云音乐", "NeteaseMusicClient", [["MUSIC_U"]],
     "用手机上的网易云音乐 App 扫下面二维码，或在 music.163.com 登录后复制 Cookie"),
    ("qq", "QQ 音乐", "QQMusicClient", [["qqmusic_key", "musickey"], ["uin", "musicid"]],
     "在 y.qq.com 用 QQ 或微信扫码登录后，从浏览器开发者工具复制 Cookie 粘贴到此处"),
    ("kugou", "酷狗音乐", "KugouMusicClient", [["token"], ["userid"]],
     "在 kugou.com 登录后，从浏览器开发者工具复制 Cookie 粘贴到此处"),
]
MUSIC_COOKIE_LABELS: Dict[str, str] = {p[0]: p[1] for p in MUSIC_COOKIE_PLATFORMS}


def _parse_cookie_pairs(raw: str) -> Dict[str, str]:
    """Cookie 文本 → 键值字典。浏览器复制出来的请求头写法为主，也认 Netscape 文件。"""
    text = str(raw or "").strip()
    # 从浏览器开发者工具整行复制时会带上 "Cookie: " 这段头名，先摘掉
    if text[:7].lower() == "cookie:":
        text = text[7:].strip()
    out: Dict[str, str] = {}
    if not text:
        return out
    if any(line.count("\t") >= 5 for line in text.splitlines()):
        for line in text.splitlines():
            cols = line.split("\t")
            if len(cols) >= 7 and not cols[0].strip().startswith("#") and cols[5].strip():
                out[cols[5].strip()] = cols[6].strip()
        return out
    try:
        from http.cookies import SimpleCookie
        for k, m in SimpleCookie(text).items():
            if m.value:
                out[k] = m.value
    except Exception:
        out = {}
    if not out:
        # SimpleCookie 会因为字符不合法整段丢弃，退一步按分号硬切，别让一条怪 Cookie 判死
        for chunk in re.split(r"[;\n]", text):
            k, _, v = chunk.partition("=")
            if k.strip() and v.strip():
                out[k.strip()] = v.strip()
    return out


def _cookie_pairs_to_text(pairs: Dict[str, str]) -> str:
    return "; ".join(f"{k}={v}" for k, v in pairs.items())


def music_cookie_raw(platform: str) -> str:
    entry = (cfg.data.get("music_platform_cookies") or {}).get(platform)
    return str(entry.get("cookie") if isinstance(entry, dict) else entry or "")


def music_cookie_missing(platform: str, pairs: Dict[str, str]) -> List[str]:
    """这条 Cookie 还缺哪个键才算真登录上；缺了 musicdl 只会去够免费那一档。"""
    required = next((p[3] for p in MUSIC_COOKIE_PLATFORMS if p[0] == platform), [])
    return [" 或 ".join(group) for group in required if not any(pairs.get(x) for x in group)]


def music_cookie_string(extra: str = "") -> str:
    """全局 Cookie + 三个平台各自的登录 Cookie（+ 本次临时填的）合成一条交给 musicdl。

    musicdl 把这条字符串按源分发，各源只挑自己认的键，多余的键那个平台会直接忽略，
    所以三个平台的 Cookie 可以同时带着跑。临时填的那串只覆盖同名键——
    一次临时粘贴不该把设置页存好的平台登录整个挤掉。
    """
    merged = _parse_cookie_pairs(str(cfg.data.get("musicdl_cookies") or ""))
    for plat, _label, _src, _req, _how in MUSIC_COOKIE_PLATFORMS:
        merged.update(_parse_cookie_pairs(music_cookie_raw(plat)))
    merged.update(_parse_cookie_pairs(extra))
    return _cookie_pairs_to_text(merged)


def music_cookie_status() -> List[dict]:
    items = []
    store = cfg.data.get("music_platform_cookies") or {}
    for plat, label, src, _req, how in MUSIC_COOKIE_PLATFORMS:
        pairs = _parse_cookie_pairs(music_cookie_raw(plat))
        entry = store.get(plat) if isinstance(store.get(plat), dict) else {}
        items.append({
            "platform": plat, "label": label, "musicdl_source": src, "how": how,
            "configured": bool(pairs),
            "keys": sorted(pairs),
            "missing": music_cookie_missing(plat, pairs),
            "via": str(entry.get("via") or ""), "at": str(entry.get("at") or ""),
        })
    return items


def set_music_cookie(platform: str, raw: str, via: str = "粘贴") -> dict:
    """存一条音乐平台 Cookie。值只进 config.json，日志只写键名个数。"""
    label = MUSIC_COOKIE_LABELS.get(platform, platform)
    pairs = _parse_cookie_pairs(raw)
    store = dict(cfg.data.get("music_platform_cookies") or {})
    if pairs:
        store[platform] = {"cookie": _cookie_pairs_to_text(pairs), "via": via,
                           "at": time.strftime("%Y-%m-%d %H:%M")}
    else:
        store.pop(platform, None)
    cfg.data["music_platform_cookies"] = store
    cfg.save()
    missing = music_cookie_missing(platform, pairs)
    log_mgr.log(f"[界面] {'保存' if pairs else '清除'}{label} 登录 Cookie"
                + (f"（{len(pairs)} 个键" + (f"，缺 {' 或 '.join(missing)}" if missing else "，键齐了") + "）"
                   if pairs else ""))
    return {"ok": True, "configured": bool(pairs), "keys": sorted(pairs), "missing": missing}


@app.get("/api/music/cookies")
def api_music_cookies_get():
    """三个音乐平台的登录 Cookie 状态：只回键名与缺失项，绝不回 Cookie 内容"""
    return {"items": music_cookie_status(),
            "global_saved": bool(str(cfg.data.get("musicdl_cookies") or "").strip())}


@app.post("/api/music/cookies")
def api_music_cookies_set(body: MusicCookieBody):
    plat = (body.platform or "").strip()
    if plat not in MUSIC_COOKIE_LABELS:
        raise HTTPException(400, "未知音乐平台")
    raw = (body.cookie or "").strip()
    if raw and not _parse_cookie_pairs(raw):
        raise HTTPException(400, "没从这段内容里认出任何 Cookie 键值，请粘贴浏览器里那串 a=b; c=d 形式的内容")
    got = set_music_cookie(plat, raw)
    return {"ok": True, "items": music_cookie_status(), **got}


@app.get("/api/music/status")
def api_music_status():
    try:
        from music_search import (
            musicdl_available, list_registered_sources, SOURCE_PRESETS, DEFAULT_SOURCES,
            UI_SOURCE_OPTIONS, PARALLEL_STRATEGY_DEFAULT, CN_SOURCE_HINTS, GLOBAL_SOURCE_HINTS,
            norm_quality_spec, QUALITY_FORMAT_OPTIONS, QUALITY_BIT_DEPTH_OPTIONS,
            QUALITY_SAMPLE_RATE_OPTIONS, QUALITY_BITRATE_OPTIONS,
        )
        saved_st = cfg.data.get("musicdl_strategy") or {}
        strategy = dict(PARALLEL_STRATEGY_DEFAULT)
        if isinstance(saved_st, dict):
            strategy.update({k: v for k, v in saved_st.items() if v is not None})
        return {
            "musicdl": musicdl_available(),
            "musicdl_version": pkg_update.installed_version("musicdl") if musicdl_available() else "",
            "fallback": "yt-dlp ytsearch/scsearch",
            "default_sources": DEFAULT_SOURCES,
            "ui_sources": list(UI_SOURCE_OPTIONS),
            "presets": {k: v for k, v in SOURCE_PRESETS.items()},
            "registered": list_registered_sources() if musicdl_available() else [],
            "saved_sources": cfg.data.get("musicdl_sources") or [],
            "saved_cookies": bool(music_cookie_string()),
            "playlist_mode": cfg.data.get("music_playlist_mode") or "fast",
            "block_reupload": bool(cfg.data.get("music_block_reupload", False)),
            "include_reference": bool(cfg.data.get("music_include_reference", False)),
            # 界面重开时要照原样回填这几项：后端下载读的就是它们，界面显示默认值会把人骗到
            "filename_template": str(cfg.data.get("music_filename_template") or ""),
            "embed_metadata": bool(cfg.data.get("music_embed_metadata", True)),
            "hide_unavailable": bool(cfg.data.get("music_hide_unavailable", True)),
            "include_local": bool(cfg.data.get("music_include_local", False)),
            # 音质要求：存的就是下载时读的，重开页面必须原样回填；选项表也由此处给，
            # 界面不另抄一份档位清单（抄了就会和后端判的口径漂移）
            "quality_spec": norm_quality_spec(cfg.data.get("music_quality_spec")),
            "quality_options": {
                "format": [list(x) for x in QUALITY_FORMAT_OPTIONS],
                "bit_depth": list(QUALITY_BIT_DEPTH_OPTIONS),
                "sample_rate": list(QUALITY_SAMPLE_RATE_OPTIONS),
                "bitrate": list(QUALITY_BITRATE_OPTIONS),
            },
            "strategy": strategy,
            "strategy_default": PARALLEL_STRATEGY_DEFAULT,
            "source_hints": {
                "cn": list(CN_SOURCE_HINTS),
                "global": list(GLOBAL_SOURCE_HINTS),
            },
        }
    except Exception as e:
        return {"musicdl": False, "error": str(e)}


@app.get("/api/mirrors/probe")
def api_mirrors_probe(kind: str = "pypi"):
    """一键获取可用镜像：实测内置候选镜像的连通性与耗时，按可用+快慢排序返回。"""
    k = kind if kind in ("pypi", "github") else "pypi"
    try:
        return {"kind": k, "mirrors": pkg_update.probe_mirrors(k)}
    except Exception as e:
        raise HTTPException(500, f"镜像测速失败：{str(e)[:160]}")


@app.post("/api/music/search")
def api_music_search(body: dict):
    """关键词多平台搜索（musicdl MusicClient.search）。"""
    kw = (body.get("keyword") or body.get("q") or "").strip()
    if not kw:
        raise HTTPException(400, "缺少 keyword")
    limit = int(body.get("limit") or 10)
    sources = body.get("sources")
    preset = (body.get("preset") or "").strip()
    if not sources and preset:
        from music_search import SOURCE_PRESETS
        sources = list(SOURCE_PRESETS.get(preset) or [])
    out_dir = str(cfg.data.get("download_dir") or DEFAULT_DOWNLOAD_DIR)
    cookies = music_cookie_string(str(body.get("cookies") or ""))
    # 每源各问一次平台策略：网易云该直连、Spotify 该出国，一刀切必然一边出错
    proxy_for = music_proxy_resolver(body.get("proxy") or "")
    from music_search import search_music
    # 持久化勾选源（归一化去重后再存，否则 ['Spotify','SpotifyMusicClient'] 会一直复发）
    if sources:
        from music_search import canonical_sources
        sources = canonical_sources(sources)
        cfg.data["musicdl_sources"] = list(sources)
        if body.get("cookies") is not None:
            cfg.data["musicdl_cookies"] = str(body.get("cookies") or "")
        try:
            cfg.save()
        except Exception:
            pass
    strategy = body.get("strategy")
    if not isinstance(strategy, dict):
        strategy = cfg.data.get("musicdl_strategy") or {}
    if body.get("save_strategy"):
        cfg.data["musicdl_strategy"] = dict(strategy)
        try:
            cfg.save()
        except Exception:
            pass
    search_type = (body.get("search_type") or "song").strip().lower()
    from music_search import norm_quality_spec, quality_spec_active, quality_spec_label
    qspec = norm_quality_spec(body.get("quality_spec")
                               if body.get("quality_spec") is not None
                               else cfg.data.get("music_quality_spec"))
    if search_type == "album":
        from music_search import search_album
        items = search_album(
            kw,
            sources=sources,
            limit=limit,
            work_dir=out_dir,
            cookies=cookies,
            proxy_for=proxy_for,
            strategy=strategy if isinstance(strategy, dict) else None,
            log=log_mgr.log,
        )
        from music_search import annotate_quality_spec
        annotate_quality_spec(items, qspec)
    else:
        items = search_music(
            kw,
            sources=sources,
            limit=limit,
            work_dir=out_dir,
            cookies=cookies,
            proxy_for=proxy_for,
            include_ytdlp=bool(body.get("include_ytdlp", True)),
            strategy=strategy if isinstance(strategy, dict) else None,
            search_type=search_type,
            hide_unavailable=bool(body.get("hide_unavailable", cfg.data.get("music_hide_unavailable", True))),
            include_local=bool(body.get("include_local", cfg.data.get("music_include_local", False))),
            local_root=out_dir,
            include_reference=bool(body.get("include_reference",
                                            cfg.data.get("music_include_reference", False))),
            reference_proxy=proxy_arg("https://flacdownloader.com", str(body.get("proxy") or "")),
            quality_spec=qspec,
            log=log_mgr.log,
        )
    if quality_spec_active(qspec):
        log_mgr.log(f"本次音质要求：{quality_spec_label(qspec)}（不达标不下={'开' if qspec['strict'] else '关'}）")
    try:
        from music_search import _LAST_SEARCH_STATS
        stats = dict(_LAST_SEARCH_STATS)
    except Exception:
        stats = {}
    try:
        from music_search import _LAST_SEARCH_DIAG
        diag = dict(_LAST_SEARCH_DIAG or {})
    except Exception:
        diag = {}
    try:
        # musicdl 搜索会在每个源目录留下「时间戳 关键词」子目录 + search_results.pkl
        from music_search import musicdl_cache_dir, cleanup_musicdl_pkl, cleanup_empty_dirs
        _silent = lambda *a, **k: None
        _cd = musicdl_cache_dir(out_dir)
        cleanup_musicdl_pkl(_cd, log=_silent)
        cleanup_empty_dirs(_cd, log=_silent)
    except Exception:
        pass
    return {"ok": True, "keyword": kw, "count": len(items), "items": items,
            "source_stats": stats, "source_errors": diag.get("errors") or {},
            "elapsed": diag.get("elapsed") or 0}


@app.post("/api/music/playlist")
def api_music_playlist(body: dict):
    """解析歌单或单曲链接（musicdl parseplaylist，单曲走各自的元数据接口）。"""
    url = (body.get("url") or body.get("playlist_url") or "").strip()
    if not url.startswith("http"):
        raise HTTPException(400, "无效的歌单或单曲链接")
    sources = body.get("sources")
    out_dir = str(cfg.data.get("download_dir") or DEFAULT_DOWNLOAD_DIR)
    cookies = music_cookie_string(str(body.get("cookies") or ""))
    proxy = music_proxy(url, str(body.get("proxy") or ""))
    from music_search import parse_playlist
    prefer = (body.get("prefer") or cfg.data.get("music_playlist_mode") or "fast").strip().lower()
    items = parse_playlist(url, sources=sources, work_dir=out_dir, cookies=cookies, proxy=proxy,
                            log=log_mgr.log, prefer=prefer)
    try:
        from music_search import _LAST_PLAYLIST_DIAG
        diag = dict(_LAST_PLAYLIST_DIAG)
    except Exception:
        diag = {}
    return {"ok": True, "count": len(items), "items": items, "diag": diag}



@app.post("/api/music/probe")
def api_music_probe(body: dict):
    """Range/HEAD 探测文件大小。"""
    url = (body.get("url") or "").strip()
    if not url:
        raise HTTPException(400, "需要 url")
    from music_search import range_probe
    info = range_probe(url)
    return {"ok": True, **info}


@app.post("/api/music/switch_source")
def api_music_switch_source(body: dict):
    """换源：给结果清单里的某一首（或勾选的几首）在别的平台重新找同一条录音，换成那条的下载地址。

    只有过 #132 那道同曲打分闸门、并且新地址探测得到结果的才算换成；换不成清单保持原样，
    reason 里写明是被曲名、歌手还是时长挡的。
    """
    ids = body.get("ids") or ([body.get("id")] if body.get("id") else [])
    ids = [str(i) for i in ids if i]
    if not ids:
        raise HTTPException(400, "缺少要换源的曲目 id")
    not_down = [i for i in ids if i.startswith("ref:") or i.startswith("local:")]
    if not_down:
        raise HTTPException(400, f"有 {len(not_down)} 行不能换源：Qobuz/Tidal 无损参照只有元数据、"
                                 "本地音乐扫描出来的行本来就是磁盘上的成品，两者都没有「换一条来路」这回事")
    sources = (body.get("sources")
               or (cfg.data.get("musicdl_strategy") or {}).get("match_sources")
               or cfg.data.get("musicdl_sources") or [])
    if not sources:
        raise HTTPException(400, "没有可换的源：请在上方「匹配源」里勾选除当前平台外的其他平台")
    out_dir = str(cfg.data.get("download_dir") or DEFAULT_DOWNLOAD_DIR)
    cookies = music_cookie_string(str(body.get("cookies") or ""))
    proxy_for = music_proxy_resolver(body.get("proxy") or "")
    from music_search import switch_song_source, get_cached_song, song_field
    strategy = cfg.data.get("musicdl_strategy") or {}
    results: List[dict] = []
    for cid in ids:
        song = get_cached_song(cid)
        cur = song_field(song, "musicdl_source", "source") if song is not None else ""
        r = switch_song_source(cid, sources=sources, work_dir=out_dir, cookies=cookies,
                               proxy_for=proxy_for, current_source=cur, st=strategy)
        r["id"] = cid
        results.append(r)
        log_mgr.log(
            f"换源「{r.get('title') or cid[:8]}」："
            + (f"已换成 {r.get('to')}（同曲判定 {r.get('score')} 分，"
               f"时长 {r.get('row', {}).get('duration') or '未知'}）" if r.get("ok")
               else f"没换成 —— {r.get('reason') or '其他源里没有过闸门的结果'}"),
            "info" if r.get("ok") else "warning")
    switched = sum(1 for r in results if r.get("ok"))
    return {"ok": bool(switched), "count": len(results), "switched": switched,
            "results": results}


@app.post("/api/music/check_quality")
def api_music_check_quality(body: dict):
    """核对成品音质：读每份成品自己的标签，对照本批音质要求，可选再与无损参照比一比。

    只比元数据 —— Qobuz / Tidal 的音频那一步锁在对方有意设的人机校验后面，这里不碰。
    """
    paths = [str(x).strip() for x in (body.get("paths") or []) if str(x).strip()]
    if not paths:
        raise HTTPException(400, "缺少要核对的成品路径 paths")
    out_dir = str(cfg.data.get("download_dir") or DEFAULT_DOWNLOAD_DIR)
    root = os.path.normcase(out_dir).rstrip("\\/")
    bad: List[str] = []
    for p in paths:
        try:
            if os.path.commonpath([os.path.normcase(p), root]) != root:
                bad.append(p)
        except ValueError:      # 不同盘符没有公共路径，一律算越界
            bad.append(p)
    if bad:
        raise HTTPException(400, f"只能核对下载目录里的成品，有 {len(bad)} 个路径不在 {out_dir} 下")
    from music_search import norm_quality_spec, check_quality
    spec = norm_quality_spec(body.get("quality_spec")
                             if body.get("quality_spec") is not None
                             else cfg.data.get("music_quality_spec"))
    rows = check_quality(paths, spec=spec,
                         use_reference=bool(body.get("use_reference",
                                                     cfg.data.get("music_include_reference", False))),
                         proxy=proxy_arg("https://flacdownloader.com", str(body.get("proxy") or "")),
                         log=log_mgr.log)
    n_low = sum(1 for r in rows if r.get("state") == "low")
    n_ref_below = sum(1 for r in rows if r.get("ref_state") == "below")
    for r in rows:
        log_mgr.log(f"音质核对「{r['name']}」：{r['note']}"
                    + (f"｜{r['ref_note']}" if r.get("ref_note") else ""),
                    "warning" if r.get("state") == "low" or r.get("ref_state") == "below" else "info")
    return {"ok": True, "count": len(rows), "below_spec": n_low, "below_reference": n_ref_below,
            "spec": spec, "rows": rows}


# -------------------- 自建音乐收藏清单 --------------------
# 清单是用户自己一行行攒出来的「这一单」：跨平台无所谓，行按「曲名+歌手+时长」的稳定 id 认，
# 同一首歌不会存两遍。每行另配一个缓存槽位（slot）——同一轮搜索里加进来的歌，槽位里就住着
# 那条真结果，整单下载原样下即可；槽位空了（重启过、或被缓存挤掉）就在下载时立一个「只有曲名」
# 的占位，交给下载流程已有的匹配轮按曲名重新取址，取不到的那几首标成失效。

_MUSIC_FAVS_LOCK = threading.Lock()
MUSIC_FAV_NOTES = {
    "missing": "在「匹配源」里按曲名没找到同一首歌 —— 换个源、或先补上该平台登录再下这一单",
    "unsearched": "整轮匹配超时，这一首这轮没轮到搜（不是没找到），再下一遍即可",
}


def _music_favs_load() -> List[dict]:
    if not MUSIC_FAVS_FILE.exists():
        return []
    try:
        data = json.loads(MUSIC_FAVS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []
    rows = data.get("items") if isinstance(data, dict) else data
    return [r for r in (rows or []) if isinstance(r, dict) and str(r.get("id") or "")]


def _music_favs_save(items: List[dict]) -> None:
    MUSIC_FAVS_FILE.write_text(json.dumps({"items": items}, ensure_ascii=False, indent=1),
                               encoding="utf-8")


def _music_fav_row(row: dict) -> dict:
    """把一行搜索/歌单结果收成清单条目；没曲名的行返回 {}（那种行存进来也找不回去）。"""
    from music_search import _dur_seconds, song_field
    title = str(song_field(row, "title", "song_name", "name") or "").strip()
    if not title:
        return {}
    artists = str(song_field(row, "artists", "singers", "artist") or "").strip()
    dur = _dur_seconds(song_field(row, "duration_s") or song_field(row, "duration"))
    src_full = str(song_field(row, "musicdl_source") or "").strip()
    if src_full and "Client" not in src_full:
        src_full += "MusicClient"
    return {
        "id": _music_entry_id(title, artists, dur),
        "title": title,
        "artists": artists,
        "album": str(song_field(row, "album") or "").strip(),
        "duration": str(song_field(row, "duration") or "").strip(),
        "duration_s": dur,
        "source": str(song_field(row, "source") or "").strip(),
        "musicdl_source": src_full,
        "url": str(song_field(row, "url") or "").strip(),
        "cover": str(song_field(row, "cover") or "").strip(),
        "quality": str(song_field(row, "quality") or "").strip(),
        "slot": "",
        "added_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "state": "",
        "note": "",
    }


def _music_fav_grab_slot(row: dict) -> str:
    """给新行占一个槽位：这一轮的真结果还在缓存里就搬进去，之后整单下载不必重新找地址。"""
    from music_search import get_cached_song, set_cached_song
    slot = str(uuid.uuid4())
    song = get_cached_song(str(row.get("id") or ""))
    if song is not None:
        set_cached_song(slot, song)
    return slot


def _music_fav_sync(fav: dict) -> bool:
    """槽位里换成另一条结果（换源、或匹配轮跑过）就把清单上那行跟着刷新，返回改动没有。"""
    from music_search import get_cached_song, pick_play_url, song_field
    slot = str(fav.get("slot") or "")
    song = get_cached_song(slot) if slot else None
    if song is None or isinstance(song, dict):
        return False
    changed = False

    def put(key: str, value: str) -> None:
        nonlocal changed
        value = str(value or "").strip()
        if value and fav.get(key) != value:
            fav[key] = value
            changed = True

    url = pick_play_url(song)
    if url and fav.get("url") != url:
        # 匹配轮会把占位换成命中平台那一条，地址也跟着变了——留着旧地址，试听就是上一轮的曲子
        fav["url"] = url
        changed = True
    put("album", song_field(song, "album"))
    put("quality", song_field(song, "ext", "quality"))
    put("duration", song_field(song, "duration"))
    src_full = str(song_field(song, "source") or "").strip()
    if src_full:
        put("musicdl_source", src_full if "Client" in src_full else src_full + "MusicClient")
        short = str(fav["musicdl_source"]).replace("MusicClient", "").replace("Client", "")
        put("source", short)
    return changed


def _music_fav_state(fav: dict) -> str:
    """这一行现在能不能直接下：槽位里住着真结果才算 ready，空槽或只有曲名的占位都是 pending。"""
    from music_search import get_cached_song
    slot = str(fav.get("slot") or "")
    song = get_cached_song(slot) if slot else None
    return "ready" if song is not None and not isinstance(song, dict) else "pending"


@app.get("/api/music/favorites")
def api_music_favorites_list():
    """自建清单当前内容（每行带「能不能直接下」的实时读数）。"""
    with _MUSIC_FAVS_LOCK:
        items = _music_favs_load()
        touched = sum(1 for it in items if _music_fav_sync(it))
        if touched:
            _music_favs_save(items)
        rows = [dict(it, resolved=_music_fav_state(it)) for it in items]
    return {"ok": True, "count": len(rows), "items": rows,
            "missing": sum(1 for r in rows if r.get("state") == "missing")}


@app.post("/api/music/favorites")
def api_music_favorites_add(body: dict):
    """把勾选的几行收进清单：同一首歌（曲名+歌手+时长一致）不会存第二遍。"""
    rows = body.get("rows") or body.get("row") or []
    if isinstance(rows, dict):
        rows = [rows]
    added: List[dict] = []
    dup = no_title = refused = 0
    with _MUSIC_FAVS_LOCK:
        items = _music_favs_load()
        have = {str(it.get("id") or "") for it in items}
        for row in rows:
            if not isinstance(row, dict):
                continue
            cid = str(row.get("id") or "")
            if cid.startswith(("ref:", "local:")):
                # 参照行只有元数据、本地行本来就是磁盘上的成品：收进这一单就永远下不动
                refused += 1
                continue
            fav = _music_fav_row(row)
            if not fav:
                no_title += 1
                continue
            if fav["id"] in have:
                dup += 1
                continue
            fav["slot"] = _music_fav_grab_slot(row)
            have.add(fav["id"])
            items.append(fav)
            added.append(fav)
        if added:
            _music_favs_save(items)
        total = len(items)
    if added:
        log_mgr.log(f"收藏清单加入 {len(added)} 首："
                    + "、".join(f"「{a['title']}」" for a in added[:6])
                    + ("…" if len(added) > 6 else ""))
    if dup or no_title or refused:
        log_mgr.log(f"收藏清单跳过 {dup} 首（已在本清单里）"
                    + (f"、{refused} 行是无损参照或本地成品（这一单要能下，收进来也下不动）"
                       if refused else "")
                    + (f"、{no_title} 行没有曲名收不进来" if no_title else ""), "warning")
    return {"ok": True, "added": len(added), "duplicated": dup, "no_title": no_title,
            "refused": refused, "total": total}


@app.post("/api/music/favorites/remove")
def api_music_favorites_remove(body: dict):
    """按稳定 id 删行（勾选删除与清空走同一条）。"""
    want = {str(i) for i in (body.get("ids") or []) if str(i)}
    if not want:
        raise HTTPException(400, "没有要删除的行")
    with _MUSIC_FAVS_LOCK:
        items = _music_favs_load()
        keep = [it for it in items if str(it.get("id") or "") not in want]
        gone = len(items) - len(keep)
        if gone:
            _music_favs_save(keep)
    if not gone:
        raise HTTPException(404, "清单里没有这些行（页面刷新一下再看）")
    log_mgr.log(f"收藏清单删除 {gone} 首，还剩 {len(keep)} 首")
    return {"ok": True, "removed": gone, "total": len(keep)}


@app.post("/api/music/favorites/download")
def api_music_favorites_download(body: dict):
    """整单（或勾选的几行）下载：每行先换成一个可下的缓存 id，再走音乐页那套批量流程。"""
    want = {str(i) for i in (body.get("ids") or []) if str(i)}
    with _MUSIC_FAVS_LOCK:
        items = _music_favs_load()
    picked = [it for it in items if not want or str(it.get("id") or "") in want]
    if want:
        absent = len(want) - len({str(it.get("id") or "") for it in picked})
        if absent:
            raise HTTPException(400, f"有 {absent} 行不在清单里了（页面刷新一下再试）")
    if not picked:
        raise HTTPException(400, "收藏清单里没有可下载的行")
    if _MUSIC_JOB.get("running"):
        raise HTTPException(409, "上一批音乐下载还没结束 —— 音乐批量只有一条通道，等它跑完再下这一单")
    from music_search import get_cached_song, set_cached_song
    slots: List[str] = []
    reminted = 0
    for it in picked:
        slot = str(it.get("slot") or "") or str(uuid.uuid4())
        if get_cached_song(slot) is None:
            set_cached_song(slot, {"title": str(it.get("title") or ""),
                                   "artists": str(it.get("artists") or ""),
                                   "duration_s": int(it.get("duration_s") or 0),
                                   "needs_match": True})
            reminted += 1
        slots.append(slot)
    res = api_music_download({
        "ids": slots,
        "match_sources": body.get("match_sources") or [],
        "skip_downloaded": body.get("skip_downloaded"),
        "block_reupload": body.get("block_reupload"),
        "embed_metadata": body.get("embed_metadata"),
        "proxy": body.get("proxy") or "",
        "cookies": str(body.get("cookies") or ""),
    })
    res.update({"fav_total": len(picked), "reminted": reminted, "slots": slots})
    log_mgr.log(f"收藏清单开始下载 {len(picked)} 首"
                + (f"，其中 {reminted} 首要先按曲名重新找地址" if reminted else ""))
    return res


@app.post("/api/music/favorites/mark")
def api_music_favorites_mark(body: dict):
    """整单下载跑完回填结论：没找到的标失效，找到了的清掉标记（只动这一批的行）。"""
    missed = {str(t).strip() for t in (body.get("missed") or []) if str(t).strip()}
    lazy = {str(t).strip() for t in (body.get("unsearched") or []) if str(t).strip()}
    scope = {str(s) for s in (body.get("slots") or []) if str(s)}
    with _MUSIC_FAVS_LOCK:
        items = _music_favs_load()
        changed = 0
        for it in items:
            if scope and str(it.get("slot") or "") not in scope:
                continue
            title = str(it.get("title") or "")
            state = "missing" if title in missed else ("unsearched" if title in lazy else "")
            if state == str(it.get("state") or ""):
                continue
            it["state"] = state
            it["note"] = MUSIC_FAV_NOTES.get(state, "")
            changed += 1
        if changed:
            _music_favs_save(items)
        marked = sum(1 for it in items if it.get("state") == "missing")
    if changed:
        log_mgr.log(f"收藏清单核对完成：{changed} 行状态有变，现在标着失效 {marked} 行",
                    "warning" if marked else "info")
    return {"ok": True, "changed": changed, "missing": marked, "total": len(items)}


@app.post("/api/music/lyrics")
def api_music_lyrics(body: dict):
    """解析 LRC 为行/逐字结构；支持 offset_ms 校准。"""
    text = body.get("text") or ""
    path = (body.get("path") or "").strip()
    try:
        offset_ms = float(body.get("offset_ms") or 0)
    except Exception:
        offset_ms = 0.0
    save = bool(body.get("save"))
    if path and not text:
        try:
            p = Path(resolve_media_path(path))
            from music_search import LOCAL_AUDIO_EXTS, audio_embedded_lyrics
            if p.suffix.lower() in LOCAL_AUDIO_EXTS:
                text = audio_embedded_lyrics(str(p))
                if not text:
                    raise HTTPException(404, f"{p.name} 没有内嵌歌词")
            else:
                text = p.read_text(encoding="utf-8", errors="ignore")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(400, str(e))
    from music_search import parse_lrc_words, shift_lrc_text, LOCAL_AUDIO_EXTS
    if offset_ms and path and save:
        if Path(str(path)).suffix.lower() in LOCAL_AUDIO_EXTS:
            raise HTTPException(400, "内嵌歌词不支持就地平移，请把歌词存成同名 .lrc 文件后再校准")
        try:
            shifted = shift_lrc_text(text, offset_ms)
            Path(resolve_media_path(path)).write_text(shifted, encoding="utf-8")
            text = shifted
            log_mgr.log(f"LRC 已平移 {offset_ms}ms → {Path(path).name}")
        except Exception as e:
            raise HTTPException(400, str(e))
    rows = parse_lrc_words(text, offset_ms=0 if (offset_ms and save) else offset_ms)
    return {"ok": True, "lines": rows, "count": len(rows), "offset_ms": offset_ms}


@app.post("/api/music/local_scan")
def api_music_local_scan(body: dict = None):
    body = body or {}
    root = (body.get("path") or cfg.data.get("download_dir") or str(DEFAULT_DOWNLOAD_DIR)).strip()
    from music_search import local_music_snapshot, local_index_path
    # 这个按钮的意思就是「现在重扫一遍」，所以 force：TTL 快照会让它看起来按了没反应
    items = local_music_snapshot(root, log=log_mgr.log, force=True)
    return {"ok": True, "count": len(items), "items": items[:200],
            "index_file": str(local_index_path(root))}


@app.get("/api/music/local_cover")
def api_music_local_cover(path: str = ""):
    """本地音频的内嵌封面：取不到就 404，前端自行回落到同名图片。"""
    from fastapi.responses import Response
    from music_search import audio_embedded_cover
    p = resolve_media_path(path)
    data, mime = audio_embedded_cover(str(p))
    if not data:
        raise HTTPException(404, f"{p.name} 没有内嵌封面")
    return Response(content=data, media_type=mime,
                    headers={"Cache-Control": "private, max-age=86400"})


@app.get("/api/music/preview")
def api_music_preview(id: str = "", url: str = ""):
    """试听：直链代理，失败则 musicdl 临时下载后本地播放。"""
    from music_search import get_cached_song, download_songs, pick_play_url
    from fastapi.responses import StreamingResponse, FileResponse
    import urllib.request
    import tempfile
    import shutil

    song = get_cached_song(id) if id else None
    play = pick_play_url(song) if song is not None else ""
    if not play and url and str(url).startswith("http"):
        play = str(url)

    if play and play.startswith("http"):
        try:
            req = urllib.request.Request(
                play,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/122.0.0.0",
                    "Referer": play.split("/")[0] + "//" + play.split("/")[2] + "/",
                },
            )
            upstream = urllib.request.urlopen(req, timeout=15)
            headers = {k.lower(): v for k, v in upstream.headers.items()}
            media_type = headers.get("content-type") or "audio/mpeg"
            if getattr(upstream, "status", 200) in (200, 206) and "text/html" not in media_type:
                def gen():
                    try:
                        while True:
                            chunk = upstream.read(64 * 1024)
                            if not chunk:
                                break
                            yield chunk
                    finally:
                        try:
                            upstream.close()
                        except Exception:
                            pass
                return StreamingResponse(gen(), media_type=media_type)
            try:
                upstream.close()
            except Exception:
                pass
        except Exception as e:
            log_mgr.log(f"试听直链不可用: {e}", "warning",
                        k="srv.music.preview_link_failed", kv={"e": str(e)})

    if id and song is not None:
        try:
            tmp_dir = Path(tempfile.mkdtemp(prefix="music_preview_"))
            paths = download_songs(
                [id],
                work_dir=str(tmp_dir),
                cookies=music_cookie_string(),
                proxy_for=music_proxy_resolver(""),
                log=log_mgr.log,
            )
            audio = None
            for pp in paths or []:
                pth = Path(pp)
                if pth.is_file() and pth.suffix.lower() in (".mp3", ".flac", ".m4a", ".ogg", ".wav", ".aac", ".opus"):
                    audio = pth
                    break
            if not audio:
                for pth in tmp_dir.rglob("*"):
                    if pth.is_file() and pth.suffix.lower() in (".mp3", ".flac", ".m4a", ".ogg", ".wav", ".aac", ".opus"):
                        audio = pth
                        break
            if audio and audio.is_file():
                prev_dir = APP_DIR / "_preview"
                prev_dir.mkdir(parents=True, exist_ok=True)
                # 这份缓存以前摊在用户的下载目录里、看得见才会被手动清；搬进工具文件夹后得自己收
                old_prev = sorted((p for p in prev_dir.iterdir() if p.is_file()),
                                  key=lambda p: p.stat().st_mtime, reverse=True)[20:]
                for p in old_prev:
                    try:
                        p.unlink(missing_ok=True)
                    except Exception:
                        pass
                dest = prev_dir / f"{id[:16]}{audio.suffix}"
                shutil.copy2(audio, dest)
                try:
                    shutil.rmtree(tmp_dir, ignore_errors=True)
                except Exception:
                    pass
                mt = {
                    ".mp3": "audio/mpeg", ".flac": "audio/flac", ".m4a": "audio/mp4",
                    ".ogg": "audio/ogg", ".wav": "audio/wav", ".aac": "audio/aac",
                }.get(dest.suffix.lower(), "audio/mpeg")
                log_mgr.log(f"试听临时文件: {dest.name}",
                            k="srv.music.preview_temp", kv={"name": dest.name})
                try:
                    from music_search import cleanup_musicdl_pkl
                    cleanup_musicdl_pkl(str(tmp_dir), log=log_mgr.log)
                except Exception:
                    pass
                return FileResponse(dest, media_type=mt, filename=dest.name)
        except Exception as e:
            log_mgr.log(f"试听临时下载失败: {e}", "error",
                        k="srv.music.preview_dl_failed", kv={"e": str(e)})

    raise HTTPException(404, "无可试听地址（可直接下载；部分源需 Cookie）")



# 多选下载走的是裸线程，下载队列里完全看不到它 —— 界面只能靠这份最新批次进度判断
# 跑没跑完、跑到第几首。本机是单人桌面应用，同一时刻只会有一个批量下载，故只留一份。
_MUSIC_JOB: Dict[str, Any] = {}


def note_music_cover(job: Dict[str, Any], cv: dict, name: str, title: str, log: Callable) -> None:
    """封面这一趟：记账 + 逐行写结论。勾了内嵌就回读文件自己的标签，回读不到要说是为什么；
       没勾时回读还能读到图，说明那张（多半是下载器自己写的）没能移出去，照实报出来。"""
    from music_search import COVER_WHY_TEXT
    c = job.setdefault("cover", {"ok": 0, "kept": 0, "miss": []})
    if cv.get("want"):
        if cv.get("has"):
            c["ok"] = int(c.get("ok") or 0) + 1
            log(f"封面: 已嵌入 {name}")
        else:
            why = cv.get("why") or "failed"
            c.setdefault("miss", []).append({"title": title, "why": why})
            log(f"封面没嵌上: {name}（{COVER_WHY_TEXT.get(why, why)}）", "warning")
    elif cv.get("has"):
        c["kept"] = int(c.get("kept") or 0) + 1
        why = cv.get("why") or "kept"
        log(f"封面没移出: {name}（{COVER_WHY_TEXT.get(why, why)}）", "warning")


@app.post("/api/music/download")
def api_music_download(body: dict):
    """
    下载策略:
      1) 有 cache id 列表 → musicdl.download 精确下载
      2) 有 http URL → 入队仅音频
      3) 仅有 title → 重搜后 musicdl 下载
    """
    ids = body.get("ids") or body.get("cache_ids") or []
    if isinstance(ids, str):
        ids = [ids]
    ids = [str(i) for i in ids if i]
    ref_ids = [i for i in ids if i.startswith("ref:")]
    if ref_ids:
        raise HTTPException(400, f"有 {len(ref_ids)} 行是 Qobuz/Tidal 无损参照（只有元数据、没有音频地址），"
                                 "不参与下载；要下这首歌请勾同一批结果里本平台那一行")
    match_sources = body.get("match_sources") or []
    if not match_sources:
        # 勾选的搜索源不一定给得了音频地址（Spotify 只列清单），所以匹配源单独设，
        # 优先级：本次请求显式指定 → 并行策略里保存的 → 本次勾选的搜索源
        match_sources = ((cfg.data.get("musicdl_strategy") or {}).get("match_sources")
                         or body.get("sources") or [])
    urls = body.get("urls") or []
    if not urls and body.get("url"):
        urls = [body.get("url")]
    urls = [str(u).strip() for u in urls if str(u).strip().startswith("http")]
    title = (body.get("title") or "").strip()
    artists = (body.get("artists") or "").strip()
    source = (body.get("musicdl_source") or body.get("source") or "").strip()
    out_dir = str(cfg.data.get("download_dir") or DEFAULT_DOWNLOAD_DIR)
    cookies = music_cookie_string(str(body.get("cookies") or ""))
    proxy_for = music_proxy_resolver(body.get("proxy") or "")
    # 搬运版守门：只拦"取回来的元数据和歌单标注对不上"的那几首，默认关（见 music_search.audio_origin）
    block_reupload = body.get("block_reupload")
    if block_reupload is None:
        block_reupload = bool(cfg.data.get("music_block_reupload", False))
    block_reupload = bool(block_reupload)
    # 「内嵌封面」这一勾：界面每次下载都带上当前值。以前它只在点「保存策略」时才落进 config，
    # 勾完直接点下载就等于没勾 —— 和这个开关要修的那个毛病是同一类
    embed_meta = body.get("embed_metadata")
    if embed_meta is None:
        embed_meta = bool(cfg.data.get("music_embed_metadata", True))
    embed_meta = bool(embed_meta)
    # 音质要求：musicdl 每一源取哪一档写死在它自己里，这里只能用于「多候选挑达标的」
    # 与「下完核对成品实际什么档」，勾了不达标不下才整首跳过
    from music_search import norm_quality_spec, quality_spec_active, quality_spec_label
    quality_spec = norm_quality_spec(body.get("quality_spec")
                                     if body.get("quality_spec") is not None
                                     else cfg.data.get("music_quality_spec"))
    if quality_spec_active(quality_spec):
        log_mgr.log(f"本批音质要求：{quality_spec_label(quality_spec)}"
                    + ("｜已勾「不达标不下」" if quality_spec["strict"] else ""), "info")

    dup_skipped: List[dict] = []
    already_have: List[dict] = []
    # 下面去重和「跳过已下载」会先剔掉一部分行，剩下的下标就不再是用户清单里的第几首。
    # {track} 取不到平台序号时要用它兜底，所以在剔之前先把位置记下来（重复 id 以第一次为准）。
    orig_pos: Dict[str, int] = {}
    for _n, _cid in enumerate(ids):
        orig_pos.setdefault(_cid, _n + 1)
    if ids:
        from music_search import get_cached_song as _song_of, drop_duplicate_tracks
        songs = [_song_of(i) for i in ids]
        keep, dup_skipped = drop_duplicate_tracks(songs)
        if dup_skipped:
            # 判不了重的行（缓存查不到、没有曲名）在 _track_clusters 里各自成组，一定留在 keep 里
            ids = [i for n, i in enumerate(ids) if n in keep]
            songs = [s for n, s in enumerate(songs) if n in keep]
            log_mgr.log(
                f"下载清单里有 {sum(int(d['count']) - 1 for d in dup_skipped)} 首重复"
                "（同一首歌排了两遍），只下第一遍："
                + "、".join(f"「{d['title']}」×{d['count']}" for d in dup_skipped[:6])
                + ("…" if len(dup_skipped) > 6 else ""))
        # 上一次下的歌还躺在下载目录里，这次整张歌单再点一遍就会下一份 `_1` 副本。
        # 所以在建后台任务之前先按命名模板比一遍目录，已有同名成品的行直接不下。
        tpl = (cfg.data.get("music_filename_template") or "{artist}/{name} - {artist}").strip()
        skip_existing = body.get("skip_downloaded")
        if skip_existing is None:
            skip_existing = bool(cfg.data.get("skip_downloaded", True))
        if skip_existing and ids:
            from music_search import find_existing_local_songs, want_from_song, song_field, log_name_list
            # 同名文件判重在两处会失灵：同一首歌在各平台的写法不同（歌手分隔符、扩展名），
            # 以及改了命名模板之后老成品对不上号。所以扫一遍目录，按 #132 那道打分闸门认歌。
            hits = find_existing_local_songs([want_from_song(s) for s in songs], out_dir,
                                             log=log_mgr.log)
            if hits:
                drop = {i for i, _p, _sc, _t in hits}
                already_have = [{"title": (song_field(songs[i], "song_name", "title", "name")
                                           or "（未知曲名）"),
                                 "path": p, "score": sc, "local_title": mt}
                                for i, p, sc, mt in hits]
                ids = [i for n, i in enumerate(ids) if n not in drop]
                log_name_list(log_mgr.log,
                              f"有 {len(hits)} 首在下载目录里已经有一版（按曲名+歌手+时长认的同一首），"
                              "这次不再下第二份"
                              "（要重下就取消勾选清单上方的「跳过已下载的歌」）",
                              [f"「{d['title']}」→ {d['path']}" for d in already_have])
        _MUSIC_JOB.update({"running": True, "finished": False, "total": len(ids),
                           "done": 0, "ok": 0, "out_dir": out_dir, "last": "",
                           "dup_skipped": sum(int(d["count"]) - 1 for d in dup_skipped),
                           "already": len(already_have), "already_list": already_have,
                           "started_at": time.time(), "elapsed_s": 0, "match": {},
                           "cover": {"ok": 0, "kept": 0, "miss": []}})
        # 匹配那一轮直接往这个 dict 里写结论：download_status 是浅拷贝，轮询时读到的就是最新内容
        match_report: Dict[str, Any] = _MUSIC_JOB["match"]

        def job():
            try:
                from music_search import download_songs, format_music_path, get_cached_song, save_lyrics_and_cover
                from music_search import musicdl_cache_dir, SIDE_CAR_EXTS, cleanup_empty_dirs
                from music_search import promote_music_file
                cache_dir = musicdl_cache_dir(out_dir)
                embed = embed_meta
                # 这一句先落在日志里：不勾时后面每首都不会有封面的动静，
                # 没有这句就分不清「这个格式没封面可嵌」和「你本来就没勾」
                log_mgr.log(f"内嵌封面: {'开' if embed else '关'}"
                            + ("" if embed else
                               "（同名封面图片仍留在成品旁边；我们不写图，"
                               "下载器顺手写进标签的那张也会被移出去）"))

                def finish(i: int, path: str) -> None:
                    _MUSIC_JOB["done"] = int(_MUSIC_JOB.get("done") or 0) + 1
                    if not path:
                        return
                    pp = Path(path)
                    if not pp.is_file():
                        log_mgr.log(f"第 {i + 1} 首没有成品文件可收尾（{path}）——"
                                    f"没有重命名、也没有入库", "warning",
                                    k="srv.music.finish_no_file",
                                    kv={"n": i + 1, "path": path})
                        return
                    _MUSIC_JOB["ok"] = int(_MUSIC_JOB.get("ok") or 0) + 1
                    meta = {}
                    archive: Dict[str, str] = {}
                    if i < len(ids):
                        song = get_cached_song(ids[i])
                        if song is not None:
                            def g(obj, *names):
                                for n in names:
                                    v = getattr(obj, n, None) if not isinstance(obj, dict) else obj.get(n)
                                    if v not in (None, ""):
                                        return v
                                return ""
                            meta = {
                                "title": str(g(song, "song_name", "title", "name") or pp.stem),
                                "artists": str(g(song, "singers", "artists", "artist") or ""),
                                "album": str(g(song, "album") or ""),
                                "source": str(g(song, "source") or "music"),
                                "cover": str(g(song, "cover_url", "album_pic", "cover") or ""),
                                "lyric": str(g(song, "lyric", "lyrics") or ""),
                            }
                            if isinstance(meta["artists"], (list, tuple)):
                                meta["artists"] = ", ".join(str(a) for a in meta["artists"])
                            try:
                                # Emby / Jellyfin 认目录：{album}/{year}/{track} - {name} 这类归档口径
                                from music_search import song_archive_meta
                                archive = song_archive_meta(song)
                            except Exception as ae:
                                log_mgr.log(f"归档字段读取失败（按空处理）: {ae}", "warning",
                                            k="srv.music.archive_meta_failed", kv={"ae": str(ae)})
                                archive = {}
                    try:
                        pos = orig_pos.get(ids[i] if i < len(ids) else "", 0)
                        dest = format_music_path(
                            tpl,
                            title=meta.get("title") or pp.stem,
                            artists=meta.get("artists") or "",
                            album=meta.get("album") or "",
                            source=meta.get("source") or "music",
                            sid=ids[i] if i < len(ids) else "",
                            ext=pp.suffix.lstrip(".") or "mp3",
                            base_dir=out_dir,
                            track=archive.get("track") or pos,
                            disc=archive.get("disc") or "",
                            year=archive.get("year") or "",
                            date=archive.get("date") or "",
                        )
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        if dest.resolve() != pp.resolve():
                            siblings = [
                                s for s in pp.parent.glob(pp.stem + ".*")
                                if s.is_file() and s.suffix.lower() in SIDE_CAR_EXTS and s != pp
                            ]
                            promote_music_file(pp, dest, log=log_mgr.log)
                            pp = dest
                            for s in siblings:
                                try:
                                    s.replace(dest.parent / (dest.stem + s.suffix.lower()))
                                except Exception:
                                    pass
                            log_mgr.log(f"重命名: {pp.name}",
                                        k="srv.music.renamed", kv={"name": pp.name})
                        lr = save_lyrics_and_cover(
                            str(pp),
                            lyrics_text=meta.get("lyric") or "",
                            cover_url=meta.get("cover") or "",
                            log=log_mgr.log,
                        )
                        cover_file = (lr or {}).get("cover") or ""
                        try:
                            from music_search import auto_tag_audio, cover_verdict
                            auto_tag_audio(
                                str(pp),
                                title=meta.get("title") or "",
                                artists=meta.get("artists") or "",
                                album=meta.get("album") or "",
                                cover_path=cover_file,
                                embed_cover=embed,
                                log=log_mgr.log,
                            )
                            note_music_cover(_MUSIC_JOB, cover_verdict(str(pp), embed, cover_file),
                                             pp.name, meta.get("title") or pp.name, log_mgr.log)
                        except Exception as te:
                            log_mgr.log(f"自动标签: {te}", "warning",
                                        k="srv.music.autotag_failed", kv={"te": str(te)})
                    except Exception as re:
                        log_mgr.log(f"模板/歌词处理: {re}", "warning",
                                    k="srv.music.path_lyrics_failed", kv={"re": str(re)})
                    _MUSIC_JOB["last"] = pp.name

                download_songs(ids, work_dir=out_dir, cookies=cookies,
                               proxy_for=proxy_for, log=log_mgr.log,
                               match_sources=(match_sources or None), on_result=finish,
                               match_report=match_report, block_reupload=block_reupload,
                               quality_spec=quality_spec)
                try:
                    from music_search import cleanup_musicdl_pkl
                    cleanup_musicdl_pkl(cache_dir, log=log_mgr.log)
                    cleanup_musicdl_pkl(out_dir, log=log_mgr.log)
                    n_empty = cleanup_empty_dirs(cache_dir, log=log_mgr.log)
                    if n_empty:
                        log_mgr.log(f"已清理空缓存目录 × {n_empty}",
                                    k="srv.music.empty_cache_dirs", kv={"n": n_empty})
                except Exception:
                    pass
            except Exception as e:
                log_mgr.log(f"musicdl 批量下载失败: {e}", "error",
                            k="srv.music.batch_failed", kv={"e": str(e)})
            finally:
                _MUSIC_JOB["running"] = False
                _MUSIC_JOB["finished"] = True
                _MUSIC_JOB["elapsed_s"] = round(
                    time.time() - float(_MUSIC_JOB.get("started_at") or time.time()), 1)
                if int(_MUSIC_JOB.get("ok") or 0):
                    # 刚落地的成品要让「包含本地库」立刻搜得到：后台重扫索引，不挡收尾
                    from music_search import refresh_local_snapshot
                    refresh_local_snapshot(out_dir, log=log_mgr.log)
        if not ids:
            # 要下的歌目录里全都有了：不起线程，当场把这批结掉，界面照常拿到回执
            _MUSIC_JOB.update({"running": False, "finished": True, "elapsed_s": 0})
            return {"ok": True, "mode": "musicdl",
                    "message": f"这 {len(already_have)} 首在下载目录里都已经有了，没有重复下载"
                               "（要重下就取消勾选清单上方的「跳过已下载的歌」）",
                    "already": len(already_have), "started_at": _MUSIC_JOB.get("started_at")}
        threading.Thread(target=job, daemon=True).start()
        from music_search import get_cached_song as _gcs, DOWNLOAD_CHUNK, canonical_sources
        n_match = sum(1 for i in ids
                      if isinstance(_gcs(i), dict) and _gcs(i).get("needs_match"))
        msg = f"musicdl 下载 {len(ids)} 首（后台，每 {DOWNLOAD_CHUNK} 首归档一次）"
        n_dup = sum(int(d["count"]) - 1 for d in dup_skipped)
        if n_dup:
            msg += f"，已跳过 {n_dup} 首重复"
        if already_have:
            msg += f"，另有 {len(already_have)} 首目录里已有同名成品、这次不下"
        if n_match:
            labels = "/".join(str(s).replace("MusicClient", "")
                              for s in canonical_sources(match_sources))
            msg += (f"，其中 {n_match} 首要先去 {labels or '默认匹配源'} 按曲名匹配音频地址，"
                    "会慢一些（进度见日志）")
        return {"ok": True, "mode": "musicdl", "message": msg, "need_match": n_match,
                "already": len(already_have), "started_at": _MUSIC_JOB.get("started_at")}

    if not urls and (title or body.get("can_musicdl_download")):
        def job2():
            try:
                from music_search import download_via_musicdl
                download_via_musicdl(
                    title or "track", artists=artists, source=source,
                    save_dir=out_dir, cookies=cookies,
                    proxy=music_proxy_for_source(source), log=log_mgr.log,
                    embed_cover=embed_meta,
                )
            except Exception as e:
                log_mgr.log(f"musicdl 任务失败: {e}", "error")
        threading.Thread(target=job2, daemon=True).start()
        return {"ok": True, "mode": "musicdl", "message": f"已用 musicdl 下载：{title or artists}"}

    if not urls:
        raise HTTPException(400, "没有可下载链接 / 缓存 id / 歌名")
    opts = {
        "audio_only": True, "embed_meta": True,
        # 走队列兜底的这些行也听同一个开关：以前这里写死 True，勾选只管另一条路
        "embed_thumb": embed_meta,
        "format": "m4a", "queue_name": body.get("queue_name") or "music",
    }
    if title:
        opts["_title"] = title[:120]
    qids = queue.add_urls(urls, opts)
    return {"ok": True, "mode": "queue", "ids": qids, "count": len(qids)}


@app.get("/api/music/download_status")
def api_music_download_status():
    """多选批量的实时进度。这条路径不入下载队列，界面只能靠它判断跑完没有。"""
    st = dict(_MUSIC_JOB)
    st["skipped"] = max(0, int(st.get("total") or 0) - int(st.get("ok") or 0))
    return st



@app.post("/api/music/tag")
def api_music_tag(body: dict):
    """
    MusicBrainz 风格标签：用 mutagen 写入；若系统有 picard 可选用。
    body: path, title, artists, album, use_picard
    """
    path = str(resolve_media_path(body.get("path") or ""))
    if not Path(path).is_file():
        raise HTTPException(400, "文件不存在")
    title = (body.get("title") or "").strip()
    artists = (body.get("artists") or body.get("artist") or "").strip()
    album = (body.get("album") or "").strip()
    use_picard = bool(body.get("use_picard"))

    if use_picard:
        import shutil as _sh
        picard = _sh.which("picard") or _sh.which("picard.exe")
        if not picard:
            raise HTTPException(400, "未找到 Picard 可执行文件，请安装 MusicBrainz Picard 并加入 PATH")
        try:
            subprocess.Popen([picard, path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return {"ok": True, "message": f"已用 Picard 打开: {Path(path).name}"}
        except Exception as e:
            raise HTTPException(500, str(e))

    # mutagen 本地写标签
    try:
        from mutagen.easyid3 import EasyID3
        from mutagen.id3 import ID3, ID3NoHeaderError
        from mutagen.flac import FLAC
        from mutagen.mp4 import MP4
    except ImportError:
        raise HTTPException(400, "请 pip install mutagen")

    pth = Path(path)
    suf = pth.suffix.lower()
    try:
        if suf == ".mp3":
            try:
                tags = EasyID3(path)
            except Exception:
                audio = ID3()
                audio.save(path)
                tags = EasyID3(path)
            if title:
                tags["title"] = title
            if artists:
                tags["artist"] = artists
            if album:
                tags["album"] = album
            tags.save()
        elif suf == ".flac":
            audio = FLAC(path)
            if title:
                audio["title"] = title
            if artists:
                audio["artist"] = artists
            if album:
                audio["album"] = album
            audio.save()
        elif suf in (".m4a", ".mp4"):
            audio = MP4(path)
            if title:
                audio["\xa9nam"] = [title]
            if artists:
                audio["\xa9ART"] = [artists]
            if album:
                audio["\xa9alb"] = [album]
            audio.save()
        else:
            raise HTTPException(400, f"暂不支持格式 {suf}，请用 Picard")
        log_mgr.log(f"已写标签: {pth.name} title={title}")
        return {"ok": True, "message": f"已写入标签: {pth.name}"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/music/mb_lookup")
def api_music_mb_lookup(body: dict):
    """MusicBrainz 录音检索（REST + 时长加分）。"""
    q_title = (body.get("title") or "").strip()
    q_artist = (body.get("artists") or body.get("artist") or "").strip()
    if not q_title and not q_artist:
        raise HTTPException(400, "需要 title 或 artist")
    try:
        duration_ms = int(body.get("duration_ms") or 0)
    except Exception:
        duration_ms = 0
    from music_search import musicbrainz_search_recordings
    results = musicbrainz_search_recordings(
        title=q_title, artist=q_artist, duration_ms=duration_ms, limit=8, log=log_mgr.log,
    )
    return {"ok": True, "items": results, "count": len(results)}


@app.post("/api/music/mb_enrich")
def api_music_mb_enrich(body: dict):
    """MusicBrainz 匹配 + Cover Art Archive 封面 + mutagen 写标签。"""
    path = str(resolve_media_path(body.get("path") or ""))
    if not Path(path).is_file():
        raise HTTPException(400, "文件不存在")
    title = (body.get("title") or Path(path).stem).strip()
    artists = (body.get("artists") or body.get("artist") or "").strip()
    album = (body.get("album") or "").strip()
    try:
        duration_ms = int(body.get("duration_ms") or 0)
    except Exception:
        duration_ms = 0
    if not duration_ms:
        # ffprobe 粗取时长
        try:
            r = subprocess.run(
                ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", path],
                capture_output=True, text=True, timeout=30,
            )
            if r.returncode == 0 and r.stdout.strip():
                duration_ms = int(float(r.stdout.strip()) * 1000)
        except Exception:
            pass

    def job():
        try:
            from music_search import musicbrainz_enrich_and_tag
            r = musicbrainz_enrich_and_tag(
                path, title=title, artists=artists, album=album,
                duration_ms=duration_ms, download_cover=True, log=log_mgr.log,
            )
            log_mgr.log(r.get("message") or ("完成" if r.get("ok") else "未写入"))
        except Exception as e:
            log_mgr.log(f"MB 富化失败: {e}", "error")

    threading.Thread(target=job, daemon=True).start()
    return {"ok": True, "message": f"正在 MusicBrainz 匹配并写标签: {Path(path).name}"}




@app.get("/api/music/fpcalc_status")
def api_fpcalc_status():
    from music_search import find_fpcalc
    p = find_fpcalc()
    return {"ok": True, "fpcalc": p or "", "available": bool(p)}


@app.post("/api/music/fingerprint")
def api_music_fingerprint(body: dict):
    """
    方案 A：Chromaprint/fpcalc → AcoustID → 写标签。
    body: path, apply_tags (default true), min_score
    """
    path = str(resolve_media_path(body.get("path") or ""))
    if not Path(path).is_file():
        raise HTTPException(400, "文件不存在")
    apply_tags = body.get("apply_tags")
    if apply_tags is None:
        apply_tags = True
    try:
        min_score = float(body.get("min_score") if body.get("min_score") is not None else cfg.data.get("acoustid_min_score") or 0.5)
    except Exception:
        min_score = 0.5
    api_key = (body.get("api_key") or cfg.data.get("acoustid_api_key") or "").strip()

    # 下面三种失败原先只落在后台线程的日志里，界面上弹的是「正在指纹识别」，看着像成功
    from music_search import find_fpcalc
    if not find_fpcalc():
        if sys.platform == "win32":
            msg = ("未找到 fpcalc（Chromaprint），指纹识别未启动：随包的 chromaprint" + os.sep + "fpcalc.exe 缺失，"
                   "请重新解压便携包，或自行安装 Chromaprint 后把它加入 PATH")
        else:
            msg = ("未找到 fpcalc（Chromaprint），指纹识别未启动：随包的 chromaprint/fpcalc 缺失，"
                   "请自行安装 Chromaprint 后把它加入 PATH（Debian/Ubuntu：apt install libchromaprint-tools）")
        log_mgr.log(f"指纹识别未启动（{Path(path).name}）：{msg}", "warning",
                    k="srv.music.fp_not_started",
                    kv={"name": Path(path).name, "reason": msg})
        return {"ok": False, "message": msg}
    if not api_key:
        msg = "缺少 AcoustID API Key，指纹识别未启动：请在「设置 → 声学指纹 / AcoustID」填写 AcoustID API Key（免费申请：https://acoustid.org/api-key）"
        log_mgr.log(f"指纹识别未启动（{Path(path).name}）：未配置 AcoustID API Key", "warning",
                    k="srv.music.fp_no_api_key", kv={"name": Path(path).name})
        return {"ok": False, "message": msg}
    try:
        from audio_analyze import preflight
        err = preflight(str(path))
    except Exception as e:
        err = f"探测音轨失败: {e}"
    if err:
        log_mgr.log(f"指纹识别未启动（{Path(path).name}）：{err}", "warning",
                    k="srv.music.fp_not_started",
                    kv={"name": Path(path).name, "reason": err})
        return {"ok": False, "message": err}
    from music_search import acoustid_key_check
    err = acoustid_key_check(api_key, log=log_mgr.log)
    if err:
        log_mgr.log(f"指纹识别未启动（{Path(path).name}）：{err}", "warning",
                    k="srv.music.fp_not_started",
                    kv={"name": Path(path).name, "reason": err})
        return {"ok": False, "message": err}

    def job():
        try:
            from music_search import fingerprint_and_tag, fpcalc_fingerprint, acoustid_lookup
            if not apply_tags:
                fp = fpcalc_fingerprint(path, log=log_mgr.log)
                if not fp.get("fingerprint"):
                    log_mgr.log("指纹计算失败", "error", k="srv.music.fp_calc_failed")
                    return
                matches = acoustid_lookup(
                    fp["fingerprint"], fp.get("duration") or 0, api_key=api_key, log=log_mgr.log,
                ) if api_key else []
                log_mgr.log(f"指纹 duration={fp.get('duration')} 候选={len(matches)}",
                            k="srv.music.fp_candidates",
                            kv={"d": fp.get("duration"), "n": len(matches)})
                for m in matches[:3]:
                    log_mgr.log(f"  score={m.get('score'):.2f} {m.get('title')} — {m.get('artists')}")
                return
            r = fingerprint_and_tag(
                path, api_key=api_key, min_score=min_score, download_cover=True, log=log_mgr.log,
            )
            log_mgr.log(r.get("message") or ("完成" if r.get("ok") else "未写入"))
        except Exception as e:
            log_mgr.log(f"指纹识别失败: {e}", "error",
                        k="srv.music.lookup_failed", kv={"e": str(e)})

    threading.Thread(target=job, daemon=True).start()
    return {"ok": True, "message": f"正在指纹识别: {Path(path).name}"}


@app.post("/api/music/guess_tags")
def api_music_guess_tags(body: dict):
    """方案 D：路径启发式猜标签，可选写入。"""
    path = str(resolve_media_path(body.get("path") or ""))
    if not Path(path).is_file():
        raise HTTPException(400, "文件不存在")
    from music_search import brainztag_style_guess, auto_tag_audio
    g = brainztag_style_guess(path)
    if body.get("apply"):
        auto_tag_audio(
            path,
            title=g.get("title") or "",
            artists=g.get("artists") or "",
            album=g.get("album") or "",
            log=log_mgr.log,
        )
        return {"ok": True, "guess": g, "message": "已按路径猜测写入标签"}
    return {"ok": True, "guess": g}


@app.post("/api/music/install")
def api_music_install(body: dict = None):
    body = body or {}

    def job():
        from music_search import install_musicdl
        idx = str(body.get("mirror") or cfg.data.get("pip_mirror") or "")
        install_musicdl(log=log_mgr.log, mirror=idx, force=bool(body.get("force")))
    threading.Thread(target=job, daemon=True).start()
    return {"ok": True, "message": "正在后台安装 musicdl，进度见运行日志"}


SEARCH_MAX_PER_SOURCE = 100   # 单个平台单类内容一次最多取回
SEARCH_MAX_TOTAL = 300        # 聚合搜索一次最多返回条数
# YouTube 搜索排序参数（实测 sp=CAM 为播放量倒序；sp=CAI 为平台侧「上传时间」，
# 但 YouTube 对热门关键词常按综合返回，故发布时间排序不保证生效，界面已注明）
_YT_SEARCH_SP = {"views": "CAM", "newest": "CAI"}
# B 站搜索排序：综合 / 点击量（播放数）/ 最新（发布时间），实测三者均生效
_BILI_SEARCH_ORDER = {"relevance": "totalrank", "views": "click", "newest": "pubdate"}


def _ts_to_date(ts) -> str:
    """Unix 时间戳 → YYYY-MM-DD；拿不到就返回空串，前端不显示该项。"""
    try:
        n = int(ts)
    except Exception:
        return ""
    if n <= 0:
        return ""
    return datetime.fromtimestamp(n).strftime("%Y-%m-%d")


def _to_int(v) -> int:
    try:
        return int(float(v))
    except Exception:
        return 0


def _yt_search_target(q: str, sort: str, n: int) -> str:
    """YouTube 搜索入口：默认 ytsearchN（综合排序），需要平台侧排序时改用 results?sp= 链接"""
    sp = _YT_SEARCH_SP.get(sort)
    if sp:
        return f"https://www.youtube.com/results?search_query={quote(q)}&sp={sp}"
    return f"ytsearch{n}:{q}"


@app.post("/api/search")
def api_search(body: SearchBody):
    """聚合搜索：多平台 + 内容类型（视频/频道/合集）+ 平台侧排序"""
    q = (body.query or "").strip()
    if not q:
        raise HTTPException(400, "请输入关键词")
    limit = max(1, min(int(body.limit or 30), SEARCH_MAX_PER_SOURCE))
    plat = (body.platform or "all").lower()
    ctype = (body.content_type or "all").lower()
    sort = (body.sort or "relevance").lower()
    if sort not in ("relevance", "views", "newest"):
        sort = "relevance"
    results = []
    seen = set()
    notes: List[dict] = []   # 某个平台「为什么这条是空的」，前端固定显示，不混进结果里

    def _add(item: dict):
        key = (item.get("platform"), item.get("id") or item.get("url"))
        if not key[1] or key in seen:
            return
        seen.add(key)
        results.append(item)

    # ---- YouTube via yt-dlp ----
    if plat in ("youtube", "all"):
        yqueries = []
        if ctype in ("all", "video"):
            yqueries.append(("video", limit, q))
        if ctype in ("all", "playlist"):
            yqueries.append(("playlist", min(20, limit), q + " playlist"))
        if ctype in ("all", "channel"):
            yqueries.append(("channel", min(12, limit), q + " channel"))
        for kind, want, term in yqueries:
            search_url = _yt_search_target(term, sort, want)
            try:
                opts = engine._ydl_opts(cfg.data, for_info=True, url=search_url)
                opts["extract_flat"] = True
                opts["skip_download"] = True
                opts["quiet"] = True
                opts["playlistend"] = want
                import yt_dlp
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(search_url, download=False)
                for e in (info.get("entries") or [])[:want]:
                    if not e:
                        continue
                    eid = e.get("id") or ""
                    link = e.get("webpage_url") or e.get("url") or ""
                    etype = e.get("_type") or kind
                    if eid and (not link.startswith("http") or ("youtube.com" not in link and "youtu.be" not in link)):
                        if etype == "playlist" or kind == "playlist":
                            link = f"https://www.youtube.com/playlist?list={eid}"
                        elif etype == "channel" or kind == "channel":
                            link = f"https://www.youtube.com/channel/{eid}" if eid.startswith("UC") else f"https://www.youtube.com/@{eid}"
                        else:
                            link = f"https://www.youtube.com/watch?v={eid}"
                    dur = e.get("duration_string") or ""
                    if not dur and e.get("duration"):
                        try:
                            sec = int(e.get("duration"))
                            dur = f"{sec // 60}:{sec % 60:02d}"
                        except Exception:
                            dur = str(e.get("duration") or "")
                    thumbs = e.get("thumbnails") or []
                    thumb = e.get("thumbnail") or (thumbs[-1].get("url") if thumbs else "")
                    views = e.get("view_count") or e.get("views") or ""
                    _add({
                        "platform": "youtube",
                        "id": eid,
                        "title": e.get("title") or "",
                        "url": link,
                        "uploader": e.get("uploader") or e.get("channel") or e.get("uploader_id") or "",
                        "duration": dur,
                        "thumbnail": thumb,
                        "content_type": "playlist" if (kind == "playlist" or etype == "playlist") else ("channel" if (kind == "channel" or etype == "channel") else "video"),
                        "views": views,
                        "views_num": _to_int(views),
                        "publish_date": _ts_to_date(e.get("release_timestamp") or e.get("timestamp")),
                        "description": (e.get("description") or "")[:120],
                    })
            except Exception as ex:
                log_mgr.log(f"搜索 youtube/{kind} 失败: {ex}", "warning",
                            k="srv.search.yt_failed",
                            kv={"kind": kind, "ex": str(ex)})

    # ---- Bilibili official API (video / bilibili_user / media_bangumi etc.) ----
    if plat in ("bilibili", "all"):
        proxy = resolve_proxy(source="bilibili")
        kw = _bili_request_kwargs(proxy=proxy, for_search=True)
        type_map = []
        if ctype in ("all", "video"):
            type_map.append(("video", "video"))
        if ctype in ("all", "channel"):
            type_map.append(("channel", "bili_user"))
        if ctype in ("all", "playlist"):
            type_map.append(("playlist", "media_ft"))  # 合集/影视
            type_map.append(("playlist", "media_bangumi"))
        for content_label, search_type in type_map:
            try:
                page_size = min(limit, 50)
                order = _BILI_SEARCH_ORDER.get(sort, "totalrank")
                batch_all: List[dict] = []
                page = 1
                while len(batch_all) < limit and page <= 6:
                    api = (
                        f"https://api.bilibili.com/x/web-interface/search/type"
                        f"?search_type={search_type}&keyword={quote(q)}"
                        f"&page={page}&page_size={page_size}&order={order}"
                    )
                    j = requests.get(api, **kw).json() or {}
                    if j.get("code") not in (0, None):
                        log_mgr.log(f"B站搜索 {search_type} API code={j.get('code')} msg={j.get('message')}", "warning",
                                    k="srv.search.bili_api_code",
                                    kv={"t": search_type, "c": j.get("code"), "m": j.get("message")})
                        break
                    batch = ((j.get("data") or {}).get("result")) or []
                    batch_all.extend(batch)
                    if len(batch) < page_size:
                        break
                    page += 1
                for it in batch_all[:limit]:
                    if search_type == "video":
                        bvid = it.get("bvid") or ""
                        if not bvid:
                            continue
                        title = re.sub(r"<[^>]+>", "", it.get("title") or "")
                        cover = it.get("pic") or it.get("cover") or ""
                        if cover.startswith("//"):
                            cover = "https:" + cover
                        elif cover.startswith("http://"):
                            cover = "https://" + cover[7:]
                        _add({
                            "platform": "bilibili",
                            "id": bvid,
                            "title": title or bvid,
                            "url": f"https://www.bilibili.com/video/{bvid}",
                            "uploader": it.get("author") or "",
                            "duration": it.get("duration") or "",
                            "thumbnail": cover,
                            "content_type": "video",
                            "views": it.get("play") or "",
                            "views_num": _to_int(it.get("play")),
                            "publish_date": _ts_to_date(it.get("pubdate")),
                            "description": re.sub(r"<[^>]+>", "", it.get("description") or "")[:120],
                        })
                    elif search_type == "bili_user":
                        mid = it.get("mid") or it.get("uid")
                        if not mid:
                            continue
                        uname = it.get("uname") or str(mid)
                        face = it.get("upic") or it.get("face") or ""
                        if face.startswith("//"):
                            face = "https:" + face
                        elif face.startswith("http://"):
                            face = "https://" + face[7:]
                        _add({
                            "platform": "bilibili",
                            "id": str(mid),
                            "title": uname,
                            "url": f"https://space.bilibili.com/{mid}",
                            "uploader": uname,
                            "duration": "",
                            "thumbnail": face,
                            "content_type": "channel",
                            "views": it.get("fans") or "",
                            "views_num": _to_int(it.get("fans")),
                            "publish_date": "",
                            "description": (it.get("usign") or "")[:120],
                        })
                    else:
                        # media
                        media_id = it.get("media_id") or it.get("season_id") or it.get("id")
                        title = re.sub(r"<[^>]+>", "", it.get("title") or it.get("org_title") or "")
                        cover = it.get("cover") or it.get("pic") or ""
                        if cover.startswith("//"):
                            cover = "https:" + cover
                        elif cover.startswith("http://"):
                            cover = "https://" + cover[7:]
                        link = it.get("goto_url") or it.get("url") or ""
                        if not link and media_id:
                            link = f"https://www.bilibili.com/bangumi/media/md{media_id}"
                        if not link:
                            continue
                        _add({
                            "platform": "bilibili",
                            "id": str(media_id or link),
                            "title": title or str(media_id),
                            "url": link,
                            "uploader": it.get("staff") or "",
                            "duration": "",
                            "thumbnail": cover,
                            "content_type": "playlist",
                            "views": it.get("play") or "",
                            "views_num": _to_int(it.get("play")),
                            "publish_date": _ts_to_date(it.get("pubtime") or it.get("publish_time")),
                            "description": re.sub(r"<[^>]+>", "", it.get("desc") or it.get("description") or "")[:120],
                        })
            except Exception as ex:
                log_mgr.log(f"B站搜索 {search_type} 失败: {ex}", "warning",
                            k="srv.search.bili_failed",
                            kv={"t": search_type, "ex": str(ex)})

        # bilisearch 仅在官方结果不足时补充；412 且已有结果时不刷 WARNING
        if ctype in ("all", "video"):
            bili_cnt = sum(1 for r in results if r.get("platform") == "bilibili")
            if bili_cnt < max(3, min(limit // 2, 10)):
                try:
                    search_url = f"bilisearch{min(limit, 30)}:{q}"
                    opts = engine._ydl_opts(cfg.data, for_info=True, url=search_url)
                    opts["extract_flat"] = True
                    opts["skip_download"] = True
                    opts["quiet"] = True
                    opts["no_warnings"] = True
                    import yt_dlp
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        info = ydl.extract_info(search_url, download=False)
                    for e in (info.get("entries") or [])[:limit]:
                        if not e:
                            continue
                        eid = e.get("id") or ""
                        title = (e.get("title") or "").strip()
                        if not title or title == "未知":
                            continue
                        link = e.get("webpage_url") or e.get("url") or ""
                        if eid and not link.startswith("http"):
                            link = f"https://www.bilibili.com/video/{eid}"
                        thumbs = e.get("thumbnails") or []
                        thumb = e.get("thumbnail") or (thumbs[-1].get("url") if thumbs else "")
                        _add({
                            "platform": "bilibili",
                            "id": eid,
                            "title": title,
                            "url": link,
                            "uploader": e.get("uploader") or "",
                            "duration": e.get("duration_string") or "",
                            "thumbnail": thumb,
                            "content_type": "video",
                            "views": e.get("view_count") or "",
                            "views_num": _to_int(e.get("view_count")),
                            "publish_date": _ts_to_date(e.get("release_timestamp") or e.get("timestamp")),
                            "description": "",
                        })
                except Exception as ex:
                    msg = str(ex)
                    if bili_cnt == 0:
                        log_mgr.log(f"bilisearch 失败: {ex}", "warning",
                                    k="srv.search.bilisearch_failed", kv={"ex": str(ex)})
                    else:
                        # 官方已有结果，412 等失败只记 info，避免日志弹窗干扰
                        log_mgr.log(f"bilisearch 跳过（已有 {bili_cnt} 条官方结果）", "info",
                                    k="srv.search.bilisearch_skipped", kv={"n": bili_cnt})

    # ---- Douyin: 仅真实抖音结果（禁止 YouTube 结果冒充 DOUYIN）----
    if plat in ("douyin", "all") and ctype in ("all", "video"):
        douyin_got = 0
        try:
            dy = api_douyin_search(q, min(12, limit))
            for e in (dy.get("results") or []):
                u = (e.get("url") or "").lower()
                if "douyin.com" not in u and "iesdouyin.com" not in u:
                    continue
                e["platform"] = "douyin"
                _add(e)
                douyin_got += 1
            if douyin_got == 0:
                risk = dy.get("risk") or {}
                why = risk.get("human") or dy.get("note") or "接口没有给出可用的抖音条目"
                # 冷却期内复述的那次，原因里已经写了还剩多少秒、且这次根本没发请求，
                # 再补一句「已自动降速」就成了自相矛盾
                if dy.get("throttle") and not dy.get("skipped"):
                    th = dy["throttle"]
                    why += f"（已自动降速：{th.get('host')} 同时只跑 1 个，冷却 {th.get('cooldown', 0):.0f}s）"
                note = {"platform": "douyin", "kind": risk.get("kind") or "unknown", "text": why}
                if risk.get("action"):
                    note["action"] = risk["action"]
                notes.append(note)   # 具体原因已由 api_douyin_search 写过日志，这里只透传给界面
        except Exception as ex:
            r = risk_control.classify_failure_text(ex)
            why = risk_control.describe(r) or f"{type(ex).__name__}: {ex}"
            notes.append({"platform": "douyin", "kind": r["kind"], "text": why})
            if r.get("action"):
                notes[-1]["action"] = r["action"]
            log_mgr.log(f"抖音搜索失败: {ex}｜{why}", "warning",
                        k="srv.search.douyin_failed", kv={"ex": str(ex), "why": why})

    # 前端 content_type 二次过滤（all 不过滤）
    if ctype in ("video", "channel", "playlist"):
        results = [r for r in results if r.get("content_type") == ctype]

    total = len(results)
    # 播放量：各平台都返回数值，可跨平台合并排序。
    # 发布时间：YouTube 扁平搜索不带发布时间字段，若在此合并排序会把 YouTube 结果整体挤到底部，
    # 因此只沿用各平台原生排序返回的分块顺序，由平台侧 order/sp 决定先后。
    if sort == "views":
        results.sort(key=lambda r: (r.get("views_num") or 0), reverse=True)
    results = results[:SEARCH_MAX_TOTAL]

    return {
        "results": results,
        "count": len(results),
        "total": total,
        "truncated": total > len(results),
        "sort": sort,
        "notes": notes,
    }



@app.get("/api/sync/export")
def api_sync_export():
    """导出配置+订阅+历史为 JSON"""
    payload = {
        "version": 1,
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "config": {k: v for k, v in cfg.data.items() if "token" not in k.lower()},
        "subscriptions": sub_mgr.list(),
        "history": history_mgr.get()[:100],
    }
    return payload


class SyncImportBody(BaseModel):
    config: Optional[dict] = None
    subscriptions: Optional[list] = None
    history: Optional[list] = None
    merge: bool = True


@app.post("/api/sync/import")
def api_sync_import(body: SyncImportBody):
    if body.config:
        for k, v in body.config.items():
            if k in cfg.DEFAULTS or k in cfg.data:
                cfg.data[k] = v
        cfg.save()
    if body.subscriptions is not None:
        if body.merge:
            existing = {s.get("url") for s in sub_mgr.list()}
            for s in body.subscriptions:
                if s.get("url") and s["url"] not in existing:
                    try:
                        sub_mgr.add(s["url"], s.get("title") or "")
                    except Exception:
                        pass
        else:
            with sub_mgr._lock:
                sub_mgr.subs = list(body.subscriptions)
            sub_mgr.save()
    if body.history is not None and not body.merge:
        with history_mgr._lock:
            history_mgr.history = list(body.history)
        history_mgr.save()
    elif body.history and body.merge:
        for h in reversed(body.history[:50]):
            history_mgr.add(h)
    return {"ok": True}



# ---------- 直播监控 ----------
class LiveMonitorBody(BaseModel):
    url: str = ""
    id: str = ""


def _load_live_monitors() -> list:
    if LIVE_MONITORS_FILE.exists():
        try:
            with open(LIVE_MONITORS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def _save_live_monitors(items: list):
    try:
        with open(LIVE_MONITORS_FILE, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _patch_live_monitor(mid: str, **fields):
    """只改一个监控记录的几个字段。开录/收尾/转码分别在不同线程里发生，
    每次都重新读盘再合并，才不会把别的线程刚写的状态覆盖掉。"""
    items = _load_live_monitors()
    hit = False
    for x in items:
        if x.get("id") == mid:
            x.update(fields)
            hit = True
    if hit:
        _save_live_monitors(items)
    return hit


# 每房间能覆盖的录制口径：容器和画质都用首页那套值，界面与这里不能各写一份
_LIVE_FMTS = ("", "mkv", "mp4", "webm")
_LIVE_QUALITIES = ("", "best", "4K", "1440p", "1080p", "720p", "480p", "360p")
_LIVE_MAX_MINUTES = 1440


def _live_effective_minutes(*vals) -> int:
    """录制时长上限：任务/房间自己设了非零值就按它，否则退回软件设置里的默认值。返回 0 表示不限时长。"""
    for v in vals:
        try:
            n = int(v or 0)
        except (TypeError, ValueError):
            continue
        if n > 0:
            return min(n, _LIVE_MAX_MINUTES)
    return 0


def _hhmm(v) -> str:
    """时段写成 HH:MM 才算数，其余一律当没填"""
    mt = re.match(r"^(\d{1,2}):(\d{2})$", str(v or "").strip())
    if not mt:
        return ""
    h, mi = int(mt.group(1)), int(mt.group(2))
    if h > 23 or mi > 59:
        return ""
    return f"{h:02d}:{mi:02d}"


def _live_window(m: dict):
    """定时监控窗：两端都填才算区间（开始晚于结束按跨零点处理），否则全天盯"""
    a, b = _hhmm(m.get("win_start")), _hhmm(m.get("win_end"))
    if not a or not b:
        return True, ""
    cur = datetime.now().strftime("%H:%M")
    ok = (a <= cur <= b) if a <= b else (cur >= a or cur <= b)
    return ok, f"{a}–{b}"


@app.get("/api/live/monitors")
def api_live_monitors():
    return {"monitors": _load_live_monitors()}


@app.post("/api/live/monitors/add")
def api_live_monitor_add(body: LiveMonitorBody):
    url = normalize_url((body.url or "").strip())
    if not url.startswith("http"):
        raise HTTPException(400, "无效链接")
    items = _load_live_monitors()
    if any(x.get("url") == url for x in items):
        return {"ok": True, "item": next(x for x in items if x.get("url") == url)}
    item = {
        "id": uuid.uuid4().hex[:10],
        "url": url,
        "status": "等待开播",
        "added_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "last_live": False,
        # 每房间录制口径，空值一律表示「跟随软件设置」
        "fmt": "",
        "video_quality": "",
        "auto_transcode": "",
        "max_minutes": 0,
        "win_start": "",
        "win_end": "",
    }
    items.insert(0, item)
    _save_live_monitors(items)
    return {"ok": True, "item": item}


class LiveMonitorSetBody(BaseModel):
    """一个直播房间的录制设置。字段留空（None）表示这一项不改，传空串表示恢复「跟随软件设置」。"""
    id: str = ""
    fmt: Optional[str] = None
    video_quality: Optional[str] = None
    auto_transcode: Optional[str] = None
    max_minutes: Optional[int] = None
    win_start: Optional[str] = None
    win_end: Optional[str] = None


@app.post("/api/live/monitors/set")
def api_live_monitor_set(body: LiveMonitorSetBody):
    """保存每房间的录制设置：输出容器 / 画质 / 录完自动转码 / 最长录制时长 / 定时监控窗"""
    items = _load_live_monitors()
    m = next((x for x in items if x.get("id") == body.id), None)
    if m is None:
        raise HTTPException(404, "监控不存在")
    notes: List[str] = []
    if body.fmt is not None:
        v = (body.fmt or "").strip().lower()
        if v in _LIVE_FMTS:
            m["fmt"] = v
        else:
            notes.append("输出容器只能用 跟随软件设置 / mkv / mp4 / webm，所填的这份没采用")
    if body.video_quality is not None:
        v = (body.video_quality or "").strip()
        if v in _LIVE_QUALITIES:
            m["video_quality"] = v
        else:
            notes.append("画质档位不在可选清单里，没采用")
    if body.auto_transcode is not None:
        v = (body.auto_transcode or "").strip()
        if not v:
            m["auto_transcode"] = ""
        elif v in TRANSCODE_PRESETS:
            m["auto_transcode"] = v
        else:
            notes.append("转码预设不存在（可用预设见文件页的转码下拉），没采用")
    if body.max_minutes is not None:
        try:
            mm = int(body.max_minutes)
        except (TypeError, ValueError):
            mm = -1
        if mm < 0 or mm > _LIVE_MAX_MINUTES:
            notes.append(f"最长录制时长要写在 0–{_LIVE_MAX_MINUTES} 分钟之间（0 = 不限时长），没采用")
        else:
            m["max_minutes"] = mm
    for key, name in (("win_start", "监控开始时间"), ("win_end", "监控结束时间")):
        raw = getattr(body, key)
        if raw is None:
            continue
        s = str(raw).strip()
        if not s:
            m[key] = ""
            continue
        got = _hhmm(s)
        if got:
            m[key] = got
        else:
            notes.append(f"{name}要写成 HH:MM（24 小时制，例如 20:30），没采用")
    if m.get("win_start") and m.get("win_end") and m["win_start"] == m["win_end"]:
        notes.append("监控时段的开始与结束相同，会全时段都不录制，已清空该时段")
        m["win_start"] = ""
        m["win_end"] = ""
    elif bool(m.get("win_start")) != bool(m.get("win_end")):
        notes.append("监控时段要同时填开始与结束才生效，目前仍按全天监控")
    _save_live_monitors(items)
    return {"ok": True, "item": m, "notes": notes, "monitors": items}


@app.post("/api/live/monitors/remove")
def api_live_monitor_remove(body: LiveMonitorBody):
    items = [x for x in _load_live_monitors() if x.get("id") != body.id]
    _save_live_monitors(items)
    return {"ok": True}


# url -> last auto-start timestamp，防止失败后每 30s 狂开录制
_live_start_cooldown: Dict[str, float] = {}


def _has_active_live_task_for_url(url: str) -> bool:
    """是否已有针对该直播间的进行中录制任务（重启后据此决定是否补录）"""
    u = (url or "").strip().rstrip("/")
    room = extract_bilibili_live_room_id(u) or ""
    active = {
        TaskStatus.DOWNLOADING.value,
        TaskStatus.QUEUED.value,
        TaskStatus.PAUSED.value,
    }
    for t in queue.tasks.values():
        if t.status not in active:
            continue
        tu = (t.url or "").strip().rstrip("/")
        if tu == u:
            return True
        if room and room in tu:
            return True
        if t.is_live and u in tu:
            return True
    return False


def _live_start_on_cooldown(url: str, sec: float = 180.0) -> bool:
    """同一房间自动开录冷却（失败后避免每 30 秒重开）"""
    key = (url or "").strip().rstrip("/")
    room = extract_bilibili_live_room_id(key) or key
    t0 = _live_start_cooldown.get(room) or _live_start_cooldown.get(key) or 0
    return (time.time() - t0) < sec


def _mark_live_started(url: str):
    key = (url or "").strip().rstrip("/")
    room = extract_bilibili_live_room_id(key) or key
    now = time.time()
    _live_start_cooldown[key] = now
    _live_start_cooldown[room] = now


@app.post("/api/live/monitors/pause")
def api_live_monitor_pause(body: LiveMonitorBody):
    """暂停指定监控的自动录制"""
    items = _load_live_monitors()
    for m in items:
        if m.get("id") == body.id or (body.url and m.get("url") == body.url):
            m["paused"] = True
            m["status"] = "录制已暂停"
    _save_live_monitors(items)
    return {"ok": True, "monitors": items}


@app.post("/api/live/monitors/resume")
def api_live_monitor_resume(body: LiveMonitorBody):
    """恢复监控自动录制（若正在直播会在下次扫描开录）"""
    items = _load_live_monitors()
    for m in items:
        if m.get("id") == body.id or (body.url and m.get("url") == body.url):
            m["paused"] = False
            m["last_live"] = False  # 允许重新触发开录
            m["status"] = "等待开播"
    _save_live_monitors(items)
    # 立即扫一次
    return api_live_monitor_scan()


@app.post("/api/live/monitors/scan")
def api_live_monitor_scan():
    """检测监控房间是否开播；开播且当前无录制任务则自动加入队列（兼容重启）"""
    items = _load_live_monitors()
    started = 0
    for m in items:
        url = m.get("url") or ""
        try:
            is_live_now = False
            status_text = "等待开播"
            # B站：走官方 API，更准确
            if "live.bilibili.com" in url.lower():
                info_b = check_bilibili_live(url)
                is_live_now = bool(info_b.get("live"))
                status_text = info_b.get("status_text") or status_text
                if info_b.get("title"):
                    m["title"] = info_b["title"]
            else:
                info = engine.get_info(url, cfg.data)
                if info:
                    is_live_now = bool(
                        info.get("is_live")
                        or info.get("live_status") in ("is_live", "live", 1, "1")
                    )
                    status_text = "直播中" if is_live_now else "等待开播"
                    if info.get("title"):
                        m["title"] = info.get("title")
            already = _has_active_live_task_for_url(url)
            paused = bool(m.get("paused"))
            cooling = _live_start_on_cooldown(url, 180.0)
            in_win, win_text = _live_window(m)
            if is_live_now and not already and not paused and not cooling and not in_win:
                # 正在播但不在设定的监控时段内：只报状态，不开录
                m["status"] = f"直播中(不在监控时段 {win_text})" if win_text else "直播中"
                m["last_live"] = True
            elif is_live_now and not already and not paused and not cooling:
                # 重启后 last_live 可能仍为 True，但任务已不在，需补开录制
                ids = queue.add_urls([url], {
                    "is_live": True,
                    "skip_downloaded": False,
                    "allow_playlist": False,
                    "format": m.get("fmt") or cfg.data.get("format", "mkv"),
                    "video_quality": m.get("video_quality") or cfg.data.get("video_quality", "best"),
                    "live_max_minutes": int(m.get("max_minutes") or 0),
                })
                if ids:
                    m["rec_task"] = ids[0]
                    m["rec_started"] = datetime.now().isoformat(timespec="seconds")
                    m.pop("rec_done", None)
                    m.pop("rec_transcode", None)
                    m.pop("rec_out", None)
                    _room_cfg = []
                    if m.get("fmt"):
                        _room_cfg.append("容器 " + str(m["fmt"]))
                    if m.get("video_quality"):
                        _room_cfg.append("画质 " + str(m["video_quality"]))
                    _cap = _live_effective_minutes(m.get("max_minutes"), cfg.data.get("live_max_minutes"))
                    if _cap:
                        _room_cfg.append(f"最长 {_cap} 分钟")
                    if m.get("auto_transcode"):
                        _room_cfg.append("录完转 " + str(
                            (TRANSCODE_PRESETS.get(m["auto_transcode"]) or {}).get("label", m["auto_transcode"])))
                    if _room_cfg:
                        log_mgr.log("本房间录制口径：" + " · ".join(_room_cfg))
                _mark_live_started(url)
                m["status"] = "录制中"
                m["last_live"] = True
                m["paused"] = False
                started += 1
                log_mgr.log(f"监控开播自动录制: {url}",
                            k="srv.live.auto_record_started", kv={"url": url})
            elif is_live_now and not already and not paused and cooling:
                m["status"] = "冷却中(防重复开录)"
                m["last_live"] = True
                try:
                    _notify_enqueue("live", "直播开播",
                                    f"🔴 直播开播，已开始录制\n{m.get('title') or url}\n{url}")
                except Exception:
                    pass
            elif is_live_now and already:
                m["status"] = "录制中"
                m["last_live"] = True
            elif is_live_now and paused:
                m["status"] = "录制已暂停"
                m["last_live"] = True
            elif is_live_now:
                m["status"] = status_text or "直播中"
                m["last_live"] = True
            else:
                m["status"] = status_text or "等待开播"
                m["last_live"] = False
                # 下播后清除暂停，下次开播可自动录
                m["paused"] = False
        except Exception as e:
            m["status"] = "检测失败"
            log_mgr.log(f"直播监控检测失败 {url}: {e}", "warning",
                        k="srv.live.check_failed", kv={"url": url, "e": str(e)})
    _save_live_monitors(items)
    return {"ok": True, "started": started, "monitors": items}


def _submit_live_transcode(mid: str, src: str, preset_id: str):
    """录完的自动转码放独立线程跑：一场直播的成品可能有几 GB，不能占用 30 秒一次的扫描。"""
    def work():
        ok, out, err = _run_transcode(src, preset_id, False)
        if ok:
            log_mgr.log(f"直播录完自动转码完成: {Path(out).name}")
            _patch_live_monitor(mid, rec_transcode="已完成", rec_out=out)
        else:
            log_mgr.log(f"直播录完自动转码失败: {err}", "warning")
            _patch_live_monitor(mid, rec_transcode="失败", rec_err=(err or "")[-200:])
    threading.Thread(target=work, daemon=True).start()


def _live_active_status(t) -> bool:
    return t is not None and t.status in (
        TaskStatus.DOWNLOADING.value, TaskStatus.QUEUED.value, TaskStatus.PAUSED.value)


def _live_used_seconds(t) -> float:
    """这一场已经录了多久。还没记开始时间（排在队里没开跑）时算 0，避免一入队就被收掉。"""
    if t is None or not (t.started_at or "").strip():
        return 0.0
    try:
        return max(0.0, (datetime.now() - datetime.fromisoformat(t.started_at)).total_seconds())
    except Exception:
        return 0.0


def _live_recording_tick():
    """每房间设置的执行环节：录满最长时长就收，这一场结束就按设置自动转码。
    和扫描分开跑，因为「开播」只决定要不要开录，收尾要看的是任务本身的状态。"""
    monitors = _load_live_monitors()
    gcap = cfg.data.get("live_max_minutes")
    for m in monitors:
        tid = m.get("rec_task") or ""
        if not tid:
            continue
        t = queue.tasks.get(tid)
        mm = _live_effective_minutes(m.get("max_minutes"), gcap)
        if mm > 0 and _live_active_status(t):
            if _live_used_seconds(t) >= mm * 60:
                try:
                    queue.end_live_tasks([tid], reason=f"已录满 {mm} 分钟，自动结束并保存")
                    log_mgr.log(f"本房间已录满 {mm} 分钟，自动结束录制并保存成品：{(t.title or t.url)[:60]}",
                                k="srv.live.room_full_stop",
                                kv={"mm": mm, "who": (t.title or t.url)[:60]})
                except Exception as e:
                    log_mgr.log(f"录满自动结束失败: {e}", "warning",
                                k="srv.live.full_stop_failed", kv={"e": str(e)})
                # 录满就维持「暂停」：这条直播还没下播时不该立刻又开录下一场，
                # 否则「最长录制 N 分钟」会变成「每 N 分钟重开一场」。
                # 扫描到房间下播时会自己解除暂停（见 api_live_monitor_scan 的 else 分支），下一场照常自动录。
                _patch_live_monitor(m.get("id"), paused=True, status=f"已录满 {mm} 分钟并自动停止")
                continue
        if t is not None and not _live_active_status(t) and not m.get("rec_done"):
            fields = {"rec_done": True, "rec_status": t.status, "rec_task": ""}
            fp = (t.filepath or "").strip()
            got_file = bool(fp) and (
                t.status in (TaskStatus.FINISHED.value, TaskStatus.STOPPED.value))
            if got_file:
                fields["rec_file"] = fp
                p = (m.get("auto_transcode") or "").strip()
                if p and p in TRANSCODE_PRESETS:
                    fields["rec_transcode"] = "转码中"
                    _submit_live_transcode(m.get("id"), fp, p)
                else:
                    fields["rec_transcode"] = ""
            else:
                fields["rec_transcode"] = ""
            _patch_live_monitor(m.get("id"), **fields)
    # 手动「开始录制」的那几场没有房间设置可挂，只看任务自己带的时长和全局默认
    tied = {m.get("rec_task") for m in monitors if m.get("rec_task")}
    for t in list(queue.tasks.values()):
        if not t.is_live or t.id in tied or not _live_active_status(t):
            continue
        mm = _live_effective_minutes((getattr(t, "_opts", {}) or {}).get("live_max_minutes"), gcap)
        if mm <= 0 or _live_used_seconds(t) < mm * 60:
            continue
        try:
            queue.end_live_tasks([t.id], reason=f"已录满 {mm} 分钟，自动结束并保存")
            log_mgr.log(f"已录满 {mm} 分钟，自动结束录制并保存成品：{(t.title or t.url)[:60]}",
                        k="srv.live.full_stop",
                        kv={"mm": mm, "who": (t.title or t.url)[:60]})
        except Exception as e:
            log_mgr.log(f"录满自动结束失败: {e}", "warning",
                        k="srv.live.full_stop_failed", kv={"e": str(e)})


# -------------------- 直播监控定时扫描 --------------------
_live_monitor_stop = False
_live_monitor_thread = None


# -------------------- 防风控档位 --------------------
RISK_PRESETS = {
    "fast": {"label": "快速", "risk_delay_sec": 0.5, "risk_cooldown_429": 30, "risk_api_rate": 8, "sub_scan_delay_sec": 3, "risk_max_per_host": 4},
    "standard": {"label": "标准", "risk_delay_sec": 1.0, "risk_cooldown_429": 60, "risk_api_rate": 4, "sub_scan_delay_sec": 10, "risk_max_per_host": 2},
    "safe": {"label": "安全", "risk_delay_sec": 2.0, "risk_cooldown_429": 120, "risk_api_rate": 2, "sub_scan_delay_sec": 20, "risk_max_per_host": 1},
    "extreme": {"label": "极端安全", "risk_delay_sec": 4.0, "risk_cooldown_429": 300, "risk_api_rate": 1, "sub_scan_delay_sec": 40, "risk_max_per_host": 1},
}


class RiskPresetBody(BaseModel):
    preset: str = "standard"


@app.get("/api/risk/presets")
def api_risk_presets():
    return {"presets": RISK_PRESETS, "current": cfg.data.get("risk_preset") or "standard"}


@app.post("/api/risk/preset")
def api_risk_apply_preset(body: RiskPresetBody):
    key = (body.preset or "standard").strip().lower()
    if key not in RISK_PRESETS:
        raise HTTPException(400, "未知档位")
    p = RISK_PRESETS[key]
    cfg.data["risk_preset"] = key
    for k, v in p.items():
        if k == "label":
            continue
        cfg.data[k] = v
    cfg.save()
    return {"ok": True, "preset": key, "applied": p}


# -------------------- 企业微信通知 --------------------
_wecom_token_cache = {"token": "", "expires": 0}


def wecom_get_token() -> str:
    if not cfg.data.get("wecom_enabled"):
        return ""
    corp_id = (cfg.data.get("wecom_corp_id") or "").strip()
    secret = (cfg.data.get("wecom_corp_secret") or "").strip()
    if not corp_id or not secret:
        return ""
    now = time.time()
    if _wecom_token_cache["token"] and _wecom_token_cache["expires"] > now + 60:
        return _wecom_token_cache["token"]
    try:
        r = requests.get(
            "https://qyapi.weixin.qq.com/cgi-bin/gettoken",
            params={"corpid": corp_id, "corpsecret": secret},
            timeout=12,
        )
        data = r.json() or {}
        token = data.get("access_token") or ""
        if token:
            _wecom_token_cache["token"] = token
            _wecom_token_cache["expires"] = now + int(data.get("expires_in") or 7200)
        return token
    except Exception as e:
        log_mgr.log(f"企业微信 token 失败: {e}", "warning")
        return ""


def wecom_send_detail(text: str) -> tuple:
    """发一条企业微信文本消息，返回 (成功, 失败原因)。"""
    if not cfg.data.get("wecom_enabled"):
        return False, "企业微信没启用"
    token = wecom_get_token()
    agent_id = cfg.data.get("wecom_agent_id")
    if not token or not agent_id:
        return False, ("CorpID / Secret 换不到 access_token" if not token else "AgentId 没填")
    try:
        r = requests.post(
            f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={token}",
            json={
                "touser": (cfg.data.get("wecom_touser") or "@all").strip(),
                "msgtype": "text",
                "agentid": int(agent_id),
                "text": {"content": text[:2000]},
                "safe": 0,
            },
            timeout=15,
        )
        data = r.json() or {}
        if data.get("errcode") != 0:
            log_mgr.log(f"企业微信发送失败: {data}", "warning")
            # 缓存的 token 过期时（40014/42001/41001）别把它带进下一次重试：
            # 那样 outbox 的每一次重试都会撞上同一个已经作废的票，一直失败到被丢弃。
            if data.get("errcode") in (40014, 42001, 41001):
                _wecom_token_cache["token"], _wecom_token_cache["expires"] = "", 0
            return False, f"errcode {data.get('errcode')}：{(data.get('errmsg') or '')[:120]}"
        return True, ""
    except Exception as e:
        log_mgr.log(f"企业微信异常: {e}", "warning")
        return False, f"请求没发出去：{e}"


def wecom_send(text: str, flag: str = "") -> bool:
    if flag and not cfg.data.get(flag, True):
        return False
    return wecom_send_detail(text)[0]


@app.post("/api/storage/test")
def api_storage_test():
    """测试 NAS 路径与 WebDAV 连通性"""
    result = {"nas": None, "webdav": None}
    # NAS
    if cfg.data.get("storage_nas_enabled"):
        nas = (cfg.data.get("storage_nas_path") or "").strip()
        try:
            p = Path(nas)
            p.mkdir(parents=True, exist_ok=True)
            test = p / ".md_storage_test"
            test.write_text("ok", encoding="utf-8")
            test.unlink(missing_ok=True)
            result["nas"] = {"ok": True, "path": nas}
        except Exception as e:
            result["nas"] = {"ok": False, "error": str(e)}
    # WebDAV
    if cfg.data.get("storage_webdav_enabled"):
        url = (cfg.data.get("storage_webdav_url") or "").strip()
        user = cfg.data.get("storage_webdav_user") or ""
        password = cfg.data.get("storage_webdav_pass") or ""
        try:
            auth = (user, password) if user else None
            # NAS 常用自签证书，按全局「跳过 SSL 校验」设置走，否则会把证书问题误报成地址错
            vfy = not cfg.data.get("nocheckcertificate", True)
            r = requests.request("PROPFIND", url, auth=auth, timeout=20, headers={"Depth": "0"}, verify=vfy)
            # 一些服务器用 GET
            if r.status_code >= 400:
                r = requests.get(url, auth=auth, timeout=20, verify=vfy)
            result["webdav"] = {
                "ok": r.status_code < 500,
                "status": r.status_code,
                "url": url,
            }
        except Exception as e:
            result["webdav"] = {"ok": False, "error": str(e)}
    return result


@app.post("/api/wecom/test")
def api_wecom_test():
    ok = wecom_send("🔔 MediaDownloader 测试消息\n企业微信通知已连通。")
    if not ok:
        raise HTTPException(400, "发送失败，请检查 CorpID / Secret / AgentId")
    return {"ok": True}


# 通知 outbox 的读数与操作。发送本身在后台线程里跑，这两个 POST 只改表 + 踢一脚，
# 所以界面点「立即重试」不会对着一个 15 秒超时的请求转圈。
@app.get("/api/notify/outbox")
def api_notify_outbox():
    return _outbox_payload()


@app.post("/api/notify/outbox/retry")
def api_notify_outbox_retry():
    return dict(_outbox_payload(), queued=_outbox_mark_due())


@app.post("/api/notify/outbox/clear")
def api_notify_outbox_clear():
    return {"ok": True, "removed": _outbox_clear_all()}


# -------------------- B站收藏 / 关注 / 稍后再看 --------------------
def _bili_need_login_hint():
    return "需要有效的 B站 Cookie（SESSDATA）。请在设置中配置浏览器 Cookie 或扫码登录。"


@app.get("/api/favorites/bili/folders")
def api_bili_fav_folders():
    """B站收藏夹列表"""
    kw = _bili_request_kwargs()
    try:
        r = requests.get(
            "https://api.bilibili.com/x/v3/fav/folder/created/list-all?up_mid=0",
            **kw,
        )
        # 若 up_mid=0 无效，先取当前用户 mid
        j = r.json() or {}
        if j.get("code") != 0:
            # 尝试 nav 拿 mid
            nav = requests.get("https://api.bilibili.com/x/web-interface/nav", **kw)
            navj = nav.json() or {}
            mid = ((navj.get("data") or {}).get("mid")) or 0
            if not mid:
                raise HTTPException(401, _bili_need_login_hint())
            r = requests.get(
                f"https://api.bilibili.com/x/v3/fav/folder/created/list-all?up_mid={mid}",
                **kw,
            )
            j = r.json() or {}
        if j.get("code") != 0:
            raise HTTPException(400, j.get("message") or _bili_need_login_hint())
        data = j.get("data") or {}
        folders = []
        for it in (data.get("list") or []):
            folders.append({
                "id": it.get("id"),
                "title": it.get("title") or "",
                "media_count": it.get("media_count") or 0,
                "attr": it.get("attr"),
            })
        return {"folders": folders}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


FAV_FOLDER_ALL_CAP = 500   # 收藏夹一次最多取回条数
FOLLOWINGS_ALL_CAP = 2000  # 关注列表一次最多取回条数


def _paged_gather(worker: Callable[[int], Optional[List[dict]]], pages: List[int]) -> tuple:
    """按页取数并顺序拼接。单页异常只标记失败（调用方降级为 partial），已取到的部分不丢。"""
    from concurrent.futures import ThreadPoolExecutor

    def safe(pn: int):
        try:
            return worker(pn) or []
        except Exception:
            return None

    items: List[dict] = []
    failed = False
    if pages:
        with ThreadPoolExecutor(max_workers=min(6, len(pages))) as ex:
            for got in ex.map(safe, pages):
                if got is None:
                    failed = True
                    continue
                items.extend(got)
    return items, failed


def _bili_fav_folder_page(media_id: int, pn: int, ps: int, kw: dict) -> dict:
    r = requests.get(
        f"https://api.bilibili.com/x/v3/fav/resource/list?media_id={media_id}&pn={pn}&ps={ps}&order=mtime",
        **kw,
    )
    j = r.json() or {}
    if j.get("code") != 0:
        raise HTTPException(400, j.get("message") or "获取失败")
    data = j.get("data") or {}
    items = []
    for it in (data.get("medias") or []):
        bvid = it.get("bvid") or ""
        cover = it.get("cover") or ""
        if cover.startswith("//"):
            cover = "https:" + cover
        items.append({
            "id": bvid or str(it.get("id") or ""),
            "title": it.get("title") or "",
            "url": f"https://www.bilibili.com/video/{bvid}" if bvid else "",
            "uploader": (it.get("upper") or {}).get("name") or "",
            "thumbnail": cover,
            "duration": it.get("duration") or 0,
            "platform": "bilibili",
        })
    info = data.get("info")
    return {
        "items": items,
        "has_more": bool(data.get("has_more")),
        "media_count": (info.get("media_count") if isinstance(info, dict) else None) or len(items),
    }


@app.get("/api/favorites/bili/folder-items")
def api_bili_fav_folder_items(media_id: int, pn: int = 1, ps: int = 20, fetch_all: bool = False):
    """某收藏夹内视频。B 站该接口单页最多 20 条，fetch_all=true 时并发取完整个收藏夹"""
    kw = _bili_request_kwargs()
    try:
        first = _bili_fav_folder_page(media_id, pn, ps, kw)
        if not fetch_all:
            return first
        items = list(first["items"])
        total = int(first.get("media_count") or len(items))
        size = 20
        pages = list(range(pn + 1, -(-total // size) + 1))
        allowed = max(0, (FAV_FOLDER_ALL_CAP - len(items)) // size)
        truncated = len(pages) > allowed
        more, failed = _paged_gather(lambda p: _bili_fav_folder_page(media_id, p, size, kw)["items"], pages[:allowed])
        items.extend(more)
        return {
            "items": items[:FAV_FOLDER_ALL_CAP],
            "has_more": False,
            "media_count": total,
            "partial": bool(truncated or failed),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/favorites/bili/toview")
def api_bili_toview():
    """稍后再看"""
    kw = _bili_request_kwargs()
    try:
        r = requests.get("https://api.bilibili.com/x/v2/history/toview/web", **kw)
        j = r.json() or {}
        if j.get("code") != 0:
            raise HTTPException(400, j.get("message") or _bili_need_login_hint())
        data = j.get("data") or {}
        items = []
        for it in (data.get("list") or []):
            bvid = it.get("bvid") or ""
            cover = it.get("pic") or ""
            if cover.startswith("//"):
                cover = "https:" + cover
            items.append({
                "id": bvid,
                "title": it.get("title") or "",
                "url": f"https://www.bilibili.com/video/{bvid}" if bvid else "",
                "uploader": (it.get("owner") or {}).get("name") or "",
                "thumbnail": cover,
                "duration": it.get("duration") or 0,
                "platform": "bilibili",
            })
        return {"items": items, "count": len(items), "total": int(data.get("count") or len(items)),
                "partial": len(items) < int(data.get("count") or 0)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


def _bili_followings_page(mid, pn: int, ps: int, kw: dict) -> Tuple[List[dict], int]:
    r = requests.get(
        f"https://api.bilibili.com/x/relation/followings?vmid={mid}&pn={pn}&ps={ps}",
        **kw,
    )
    j = r.json() or {}
    if j.get("code") != 0:
        raise HTTPException(400, j.get("message") or "获取关注列表失败")
    data = j.get("data") or {}
    items = []
    for it in (data.get("list") or []):
        face = it.get("face") or ""
        if face.startswith("//"):
            face = "https:" + face
        m = it.get("mid")
        items.append({
            "id": str(m),
            "title": it.get("uname") or str(m),
            "url": f"https://space.bilibili.com/{m}",
            "uploader": it.get("uname") or "",
            "thumbnail": face,
            "description": it.get("sign") or "",
            "platform": "bilibili",
            "content_type": "channel",
        })
    return items, int(data.get("total") or len(items))


@app.get("/api/favorites/bili/followings")
def api_bili_followings(pn: int = 1, ps: int = 50, fetch_all: bool = False):
    """关注的 UP 主。B 站按页返回，fetch_all=true 时按 total 取完（上限 FOLLOWINGS_ALL_CAP）"""
    kw = _bili_request_kwargs()
    try:
        nav = requests.get("https://api.bilibili.com/x/web-interface/nav", **kw)
        mid = ((nav.json() or {}).get("data") or {}).get("mid")
        if not mid:
            raise HTTPException(401, _bili_need_login_hint())
        items, total = _bili_followings_page(mid, pn, ps, kw)
        if not fetch_all:
            return {"items": items, "total": total}
        pages = list(range(pn + 1, -(-total // ps) + 1))
        allowed = max(0, (FOLLOWINGS_ALL_CAP - len(items)) // ps)
        truncated = len(pages) > allowed
        more, failed = _paged_gather(
            lambda p: _bili_followings_page(mid, p, ps, kw)[0], pages[:allowed])
        items.extend(more)
        return {"items": items, "total": total, "partial": bool(truncated or failed)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


class FavDownloadBody(BaseModel):
    urls: List[str]


@app.post("/api/favorites/download")
def api_fav_download(body: FavDownloadBody):
    urls = [u.strip() for u in (body.urls or []) if u and u.strip().startswith("http")]
    if not urls:
        raise HTTPException(400, "无有效链接")
    ids = queue.add_urls(urls, {
        "video_quality": cfg.data.get("video_quality", "best"),
        "audio_quality": cfg.data.get("audio_quality", "best"),
        "format": cfg.data.get("format", "mkv"),
        "skip_downloaded": True,
        "allow_playlist": False,
    })
    return {"ok": True, "count": len(ids), "ids": ids}


def _yt_flat_playlist(url: str, limit: int = 200) -> Tuple[List[dict], int]:
    """用 yt-dlp 扁平拉取播放列表（需 YouTube Cookie）；返回 (条目, 播放列表总条数)"""
    opts = engine._ydl_opts(cfg.data, for_info=True, url=url)
    opts["extract_flat"] = "in_playlist"
    opts["skip_download"] = True
    opts["quiet"] = True
    opts["no_warnings"] = True
    opts["playlistend"] = limit
    import yt_dlp
    items = []
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False) or {}
    total = int(info.get("playlist_count") or 0)
    for e in (info.get("entries") or [])[:limit]:
        if not e:
            continue
        eid = e.get("id") or ""
        link = e.get("url") or e.get("webpage_url") or ""
        if eid and not str(link).startswith("http"):
            link = f"https://www.youtube.com/watch?v={eid}"
        thumbs = e.get("thumbnails") or []
        thumb = e.get("thumbnail") or (thumbs[-1].get("url") if thumbs else "")
        items.append({
            "id": eid,
            "title": e.get("title") or eid,
            "url": link,
            "uploader": e.get("uploader") or e.get("channel") or "",
            "thumbnail": thumb,
            "duration": e.get("duration_string") or e.get("duration") or "",
            "platform": "youtube",
            "content_type": "video",
        })
    return items, max(total, len(items))


@app.get("/api/favorites/youtube/liked")
def api_yt_liked(limit: int = 200):
    """YouTube 喜欢的视频（playlist=LL，需登录 Cookie）"""
    try:
        items, total = _yt_flat_playlist("https://www.youtube.com/playlist?list=LL", limit=limit)
        return {"items": items, "count": len(items), "total": total, "partial": len(items) < total}
    except Exception as e:
        raise HTTPException(400, f"获取失败（请配置 YouTube Cookie）: {e}")


@app.get("/api/favorites/youtube/watchlater")
def api_yt_watchlater(limit: int = 200):
    """YouTube 稍后再看（playlist=WL）"""
    try:
        items, total = _yt_flat_playlist("https://www.youtube.com/playlist?list=WL", limit=limit)
        return {"items": items, "count": len(items), "total": total, "partial": len(items) < total}
    except Exception as e:
        raise HTTPException(400, f"获取失败（请配置 YouTube Cookie）: {e}")


@app.get("/api/favorites/youtube/playlist")
def api_yt_playlist(url: str, limit: int = 200):
    """加载任意 YouTube 播放列表链接"""
    u = (url or "").strip()
    if "list=" not in u and "youtube.com" not in u and "youtu.be" not in u:
        raise HTTPException(400, "请提供有效的 YouTube 播放列表链接")
    try:
        items, total = _yt_flat_playlist(u, limit=limit)
        return {"items": items, "count": len(items), "total": total, "url": u,
                "partial": len(items) < total}
    except Exception as e:
        raise HTTPException(400, f"加载播放列表失败: {e}")


# -------------------- B站扫码登录 --------------------
def _make_qr_data_url(text: str) -> str:
    """生成二维码 PNG data URL；优先 qrcode 库，失败则返回空由前端渲染"""
    try:
        import base64
        import io
        import qrcode
        qr = qrcode.QRCode(version=None, box_size=8, border=2)
        qr.add_data(text)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:
        return ""


@app.get("/api/bili/qr/generate")
def api_bili_qr_generate():
    """生成 B站登录二维码（含页内可显示的图片）"""
    try:
        r = requests.get(
            "https://passport.bilibili.com/x/passport-login/web/qrcode/generate",
            headers=dict(_BILI_HEADERS),
            timeout=12,
        )
        j = r.json() or {}
        if j.get("code") != 0:
            raise HTTPException(400, j.get("message") or "生成二维码失败")
        data = j.get("data") or {}
        url = data.get("url") or ""
        return {
            "url": url,
            "qrcode_key": data.get("qrcode_key") or "",
            "qr_image": _make_qr_data_url(url) if url else "",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


class BiliQrPollBody(BaseModel):
    qrcode_key: str


@app.post("/api/bili/qr/poll")
def api_bili_qr_poll(body: BiliQrPollBody):
    """轮询扫码状态；成功则写入 bilibili cookies 文件"""
    key = (body.qrcode_key or "").strip()
    if not key:
        raise HTTPException(400, "缺少 qrcode_key")
    try:
        r = requests.get(
            "https://passport.bilibili.com/x/passport-login/web/qrcode/poll",
            params={"qrcode_key": key},
            headers=dict(_BILI_HEADERS),
            timeout=12,
        )
        j = r.json() or {}
        data = j.get("data") or {}
        code = data.get("code")
        # 0 成功；86101 未扫；86090 已扫未确认；86038 过期
        if code == 0:
            # 从响应 Set-Cookie 组装 Netscape cookies
            cookie_jar = r.cookies
            # poll 成功时可能需要再请求一次拿完整 cookie
            lines = ["# Netscape HTTP Cookie File", "# Bilibili QR login"]
            for c in cookie_jar:
                domain = c.domain or ".bilibili.com"
                flag = "TRUE" if domain.startswith(".") else "FALSE"
                path = c.path or "/"
                secure = "TRUE" if c.secure else "FALSE"
                expires = str(int(c.expires or 0))
                lines.append(f"{domain}\t{flag}\t{path}\t{secure}\t{expires}\t{c.name}\t{c.value}")
            # 常见关键 cookie 也可能在 data 里没有，依赖 requests cookie
            path = platform_cookie_path("bilibili")
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            pc = dict(cfg.data.get("platform_cookies") or {})
            pc["bilibili"] = {"source": "file", "file": str(path), "browser": "chrome"}
            cfg.data["platform_cookies"] = pc
            cfg.save()
            drop_all_cookie_prefs()   # 刚拿到登录态：之前「这条匿名就被挡」的判定要重新算
            return {"ok": True, "code": 0, "message": "登录成功，Cookie 已保存", "status": "success"}
        msg_map = {86101: "等待扫码", 86090: "已扫码，请在手机确认", 86038: "二维码已过期"}
        return {
            "ok": False,
            "code": code,
            "message": msg_map.get(code, data.get("message") or j.get("message") or str(code)),
            "status": "pending" if code in (86101, 86090) else "expired",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


# -------------------- 网易云音乐扫码登录 --------------------
# 走 music.163.com 网页版点「扫码登录」时自己调的那对公开接口，不碰 weapi/eapi 加密参数，
# 也不伪造任何签名；成功拿到的登录 Cookie 只写进本机 config.json。
_NETEASE_QR_TTL = 300   # 网易云那侧二维码约 5 分钟失效，这边同步清掉会话
_NETEASE_QR_SESSIONS: Dict[str, tuple] = {}   # unikey -> (session, 生成时刻)


def _netease_qr_head() -> Dict[str, str]:
    return {
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
        "Referer": "https://music.163.com/",
        "Origin": "https://music.163.com",
    }


def _netease_qr_trim() -> None:
    now = time.time()
    for k in [k for k, (_s, born) in _NETEASE_QR_SESSIONS.items() if now - born > _NETEASE_QR_TTL]:
        _NETEASE_QR_SESSIONS.pop(k, None)


def _netease_qr_forget(key: str) -> None:
    _NETEASE_QR_SESSIONS.pop(key, None)
    _netease_qr_trim()


@app.get("/api/music/netease/qr/generate")
def api_netease_qr_generate():
    """向网易云取一张登录二维码（这一步不带任何凭据，只是拿一个待确认的 key）"""
    sess = requests.Session()
    sess.headers.update(_netease_qr_head())
    try:
        j = (sess.post("https://music.163.com/api/login/qrcode/unikey",
                       data={"type": "1"}, timeout=12).json() or {})
    except Exception as e:
        raise HTTPException(500, f"向网易云取二维码没成功：{type(e).__name__}: {str(e)[:120]}")
    key = str(j.get("unikey") or "")
    if j.get("code") != 200 or not key:
        raise HTTPException(400, f"网易云没给二维码：{j.get('message') or '返回码 %s' % j.get('code')}")
    _netease_qr_trim()
    _NETEASE_QR_SESSIONS[key] = (sess, time.time())
    qr_url = f"https://music.163.com/login?codekey={key}"
    return {"url": qr_url, "qrcode_key": key, "qr_image": _make_qr_data_url(qr_url),
            "ttl_sec": _NETEASE_QR_TTL}


class NeteaseQrPollBody(BaseModel):
    qrcode_key: str


@app.post("/api/music/netease/qr/poll")
def api_netease_qr_poll(body: NeteaseQrPollBody):
    """问一次扫码结果；确认成功就把登录 Cookie 存进网易云那一格"""
    key = (body.qrcode_key or "").strip()
    if not key:
        raise HTTPException(400, "缺少 qrcode_key")
    entry = _NETEASE_QR_SESSIONS.get(key)
    if not entry:
        return {"ok": False, "status": "expired", "code": 800, "message": "二维码已过期，请重新获取"}
    sess, born = entry
    if time.time() - born > _NETEASE_QR_TTL:
        # 二维码那边早就凉了，别再拿它去问网易云，直接叫用户重新生成
        _netease_qr_forget(key)
        return {"ok": False, "status": "expired", "code": 800, "message": "二维码已过期，请重新获取"}
    try:
        j = (sess.post("https://music.163.com/api/login/qrcode/client/login",
                       data={"key": key, "type": "1"}, timeout=12).json() or {})
    except Exception as e:
        # 网络抖一下不该把二维码判死，留着 key 让用户再点一次
        return {"ok": False, "status": "pending", "code": None,
                "message": f"没问到网易云的结果（{type(e).__name__}），可再点一次「检查扫码状态」"}
    code = j.get("code")
    if code == 803:
        pairs = {c.name: c.value for c in sess.cookies if c.value}
        _netease_qr_forget(key)
        missing = music_cookie_missing("netease", pairs)
        if missing:
            return {"ok": False, "status": "failed", "code": code,
                    "message": "手机上已确认，但网易云没回登录凭证（缺 " + "、".join(missing)
                               + "），请重新扫码或改用粘贴 Cookie"}
        got = set_music_cookie("netease", _cookie_pairs_to_text(pairs), via="扫码登录")
        return {"ok": True, "status": "success", "code": code, "message": "登录成功，网易云 Cookie 已保存",
                "items": music_cookie_status(), **got}
    _NETEASE_QR_MSG = {801: "等待扫码", 802: "已扫码，请在手机上确认", 800: "二维码已失效，请重新获取"}
    if code == 800:
        _netease_qr_forget(key)
    return {"ok": False, "code": code,
            "message": _NETEASE_QR_MSG.get(code) or j.get("message") or f"网易云返回码 {code}",
            "status": "pending" if code in (801, 802) else "expired"}


# -------------------- 文件在线播放 / 打包 --------------------
@app.get("/api/files/stream")
def api_files_stream(path: str):
    """在线播放/预览下载目录中的媒体文件"""
    root = Path(cfg.data.get("download_dir") or DEFAULT_DOWNLOAD_DIR).resolve()
    target = (root / path).resolve()
    if not str(target).startswith(str(root)) or not target.is_file():
        raise HTTPException(404, "文件不存在")
    media_types = {
        ".mp4": "video/mp4", ".webm": "video/webm", ".mkv": "video/x-matroska",
        ".mov": "video/quicktime", ".flv": "video/x-flv", ".ts": "video/mp2t",
        ".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".flac": "audio/flac",
        ".wav": "audio/wav", ".aac": "audio/aac", ".ogg": "audio/ogg",
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
        ".gif": "image/gif", ".webp": "image/webp",
    }
    mt = media_types.get(target.suffix.lower(), "application/octet-stream")
    return FileResponse(target, media_type=mt, filename=target.name)


class ZipBody(BaseModel):
    path: str = ""
    name: str = ""


@app.post("/api/files/zip")
def api_files_zip(body: ZipBody):
    """打包下载目录中的文件夹为 zip"""
    root = Path(cfg.data.get("download_dir") or DEFAULT_DOWNLOAD_DIR).resolve()
    rel = (body.path or "").strip()
    target = (root / rel).resolve() if rel else root
    if not str(target).startswith(str(root)) or not target.exists():
        raise HTTPException(404, "路径不存在")
    if target.is_file():
        # 单文件：直接返回
        return FileResponse(target, filename=target.name)
    zip_name = (body.name or target.name or "archive").strip() or "archive"
    zip_name = re.sub(r"[^\w\u4e00-\u9fff\-]+", "_", zip_name)[:40]
    out = root / f"_pack_{zip_name}_{uuid.uuid4().hex[:6]}.zip"
    try:
        with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            if target.is_dir():
                for p in target.rglob("*"):
                    if p.is_file() and not p.name.startswith("."):
                        zf.write(p, arcname=str(p.relative_to(target)))
            else:
                zf.write(target, arcname=target.name)
        return FileResponse(out, filename=f"{zip_name}.zip", media_type="application/zip")
    except Exception as e:
        if out.exists():
            try:
                out.unlink()
            except Exception:
                pass
        raise HTTPException(500, str(e))


# -------------------- 真·抖音搜索（轻量 HTML/接口尝试） --------------------
def _load_netscape_cookies(path: str) -> dict:
    cookies = {}
    try:
        p = Path(path)
        if not p.exists():
            return cookies
        for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) >= 7:
                cookies[parts[5]] = parts[6]
    except Exception:
        pass
    return cookies


def _douyin_cookies() -> dict:
    cookies = {}
    try:
        pc = (cfg.data.get("platform_cookies") or {}).get("douyin") or {}
        cf = (pc.get("file") or str(platform_cookie_path("douyin"))).strip()
        cookies.update(_load_netscape_cookies(cf))
        # 也尝试全局 cookies
        g = (cfg.data.get("cookie_file") or str(DEFAULT_COOKIE_FILE)).strip()
        if g and g != cf:
            cookies.update(_load_netscape_cookies(g))
    except Exception:
        pass
    return cookies


def _parse_douyin_aweme_list(data: dict, limit: int) -> list:
    results = []
    seen = set()

    def _add_aweme(aweme: dict):
        if not isinstance(aweme, dict):
            return
        aweme_id = str(aweme.get("aweme_id") or aweme.get("id") or "")
        if not aweme_id or aweme_id in seen:
            return
        seen.add(aweme_id)
        desc = aweme.get("desc") or aweme.get("preview_title") or aweme_id
        author = ""
        try:
            author = (aweme.get("author") or {}).get("nickname") or ""
        except Exception:
            author = ""
        cover = ""
        try:
            for key in ("cover", "origin_cover", "dynamic_cover"):
                node = (aweme.get("video") or {}).get(key) or {}
                urls = node.get("url_list") or []
                if urls:
                    cover = urls[0]
                    break
            if not cover:
                imgs = aweme.get("images") or []
                if imgs and isinstance(imgs[0], dict):
                    cover = (imgs[0].get("url_list") or [""])[0]
        except Exception:
            cover = ""
        results.append({
            "platform": "douyin",
            "id": aweme_id,
            "title": desc,
            "url": f"https://www.douyin.com/video/{aweme_id}",
            "uploader": author,
            "thumbnail": cover,
            "content_type": "video",
            "duration": "",
            "views": str((aweme.get("statistics") or {}).get("play_count") or ""),
            "views_num": _to_int((aweme.get("statistics") or {}).get("play_count")),
            "publish_date": _ts_to_date(aweme.get("create_time")),
        })

    # 多种响应结构
    for key in ("data", "aweme_list", "business_data"):
        arr = data.get(key)
        if isinstance(arr, list):
            for it in arr:
                if not isinstance(it, dict):
                    continue
                _add_aweme(it.get("aweme_info") or it.get("aweme") or it)
                if len(results) >= limit:
                    return results
    # 嵌套 data.list
    try:
        inner = (data.get("data") or {})
        if isinstance(inner, dict):
            for k in ("data", "aweme_list", "business_data"):
                arr = inner.get(k)
                if isinstance(arr, list):
                    for it in arr:
                        if isinstance(it, dict):
                            _add_aweme(it.get("aweme_info") or it.get("aweme") or it)
                        if len(results) >= limit:
                            return results
    except Exception:
        pass
    return results


RISK_SEVERITY = (
    risk_control.RATE_LIMITED, risk_control.BOT_CHALLENGE, risk_control.LOGIN_REQUIRED,
    risk_control.API_REJECT, risk_control.DENIED, risk_control.NOT_FOUND,
    risk_control.NETWORK, risk_control.EMPTY, risk_control.UNKNOWN,
)


def pick_risk_reason(reasons: List[dict]) -> dict:
    """多次尝试里挑一条最能说明问题的判定（不是最后一条，也不是第一条）。"""
    if not reasons:
        return {}
    for k in RISK_SEVERITY:
        for r in reasons:
            if r.get("kind") == k:
                if not r.get("describe"):
                    r["describe"] = risk_control.describe(r)
                return r
    return reasons[-1]


# 「这一平台的登录态刚被站点当场挡过」的标记，只保留到程序关闭。
# 留的是平台、时间、域名与判定话术：Cookie 内容是本机私有凭据、链接里带视频 id，两者都不进这里。
# 刻意不去读 Netscape 文件里的 expires —— 站点普遍不给登录凭据真实有效期（会话 Cookie 常是 0），
# 按它报「快过期」只会是噪声；而「下载当场被判定为需要登录」是已经发生的事实。
_LOGIN_FLAGS: Dict[str, Dict[str, str]] = {}
_LOGIN_FLAGS_LOCK = threading.Lock()


def _login_flag_mark(url: str, r: Dict, task_id: str = "") -> Dict:
    """记下「这个平台刚被判定为需要登录」；同平台重复挡只刷新那一条，不叠加。"""
    plat = detect_platform(url) if url else ""
    if not plat or plat == "default":
        return {}
    try:
        host = urlsplit(url).netloc.lower()
    except Exception:
        host = ""
    with _LOGIN_FLAGS_LOCK:
        fresh = plat not in _LOGIN_FLAGS
        item = {
            "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "kind": str(r.get("kind") or ""),
            "brief": str(r.get("brief") or r.get("human") or ""),
            "action": str(r.get("action") or ""),
            "host": host,
            "task_id": (task_id or "")[:8],
        }
        _LOGIN_FLAGS[plat] = item
    # 一批任务里同一个站能连挡几十次，只在头一次说一句话
    if fresh:
        log_mgr.log(f"Cookie 登录态标记：{PLATFORM_LABELS.get(plat, plat)} 有下载被判定为需要登录"
                    + (f"（{host}）" if host else "")
                    + "，重新导入这一平台的 Cookie 即可清除；本标记只保留到程序关闭", "warning")
    return dict(item)


def _login_flag_clear(platform: str) -> None:
    with _LOGIN_FLAGS_LOCK:
        _LOGIN_FLAGS.pop(str(platform or ""), None)


def _login_flag_snapshot() -> Dict[str, Dict[str, str]]:
    with _LOGIN_FLAGS_LOCK:
        return {k: dict(v) for k, v in _LOGIN_FLAGS.items()}


def risk_note_for_failure(raw: str, url: str = "", task_id: str = "") -> str:
    """把下载失败的原始报错翻成「挡在哪一步、现在该做什么」。

    原话一个字不改地留在前面，这里只补一句原因和动作 —— 认不出来就回空串，不编原因。
    """
    if not raw:
        return ""
    r = risk_control.classify_failure_text(raw)
    if r.get("kind") in ("", risk_control.UNKNOWN):
        return ""
    if r.get("kind") == risk_control.LOGIN_REQUIRED:
        _login_flag_mark(url, r, task_id)
    note = f"原因：{r.get('brief') or r['human']}" + (f"；{r['action']}" if r.get("action") else "")
    # 429 在下载循环里已经打过一次降速标记，这里别再叠加 strike；补的是它没看见的那几类
    if r.get("throttle") and "429" not in raw and url and cfg.data.get("adaptive_throttle", True):
        try:
            th = HOST_THROTTLE.hit(url, cooldown=float(cfg.data.get("risk_cooldown_429") or 60)) or {}
        except Exception:
            th = {}
        if th:
            note += f"（该域名 {th['host']} 已自动降速：同时只跑 1 个，冷却 {th['cooldown']:.0f}s）"
            if task_id:
                log_mgr.log(f"[{task_id[:8]}] 按失败原因降速：{th['host']} 第 {th['strikes']} 次命中", "warning")
    return note


def _douyin_search_in_cooldown(q: str, cd: Dict, has_cookie: bool) -> Dict:
    """降速冷却还没过：复述上一次的判定，一条请求都不再发。"""
    last = _DY_LAST_BLOCK
    left = int(round(float(cd.get("left") or 0)))
    base = str(last.get("describe") or last.get("human") or "上次向抖音取结果被站点挡下了")
    why = f"{base}（该站点正在降速冷却，还剩 {left}s，本次没有再向它发请求）"
    action = str(last.get("action") or "")
    log_mgr.log(
        f"抖音搜索跳过 q={q}：{cd.get('host')} 冷却还剩 {left}s"
        f"（第 {cd.get('strikes')} 次命中），上次判定 {last.get('kind') or '未知'}",
        "warning",
    )
    return {
        "results": [],
        "count": 0,
        "note": f"无结果：{why}" + (f"。{action}" if action else ""),
        "has_cookie": has_cookie,
        "risk": {
            "kind": last.get("kind") or "",
            "code": last.get("code") or "",
            "server_msg": last.get("server_msg") or "",
            "human": why,
            "action": action,
            "evidence": last.get("evidence") or [],
            "via": last.get("via") or "",
        },
        "throttle": dict(cd),
        "attempts": [],
        "skipped": True,
    }


DY_SEARCH_HOST_URL = "https://www.douyin.com/"
# 冷却期内直接复述上一次的判定，不再重复向站点发请求：
# 只打点不认账的话，用户多点几次搜索就只是把该域的降速越叠越长。
_DY_LAST_BLOCK: Dict[str, object] = {}


@app.get("/api/douyin/search")
def api_douyin_search(q: str, limit: int = 12):
    """抖音关键词搜索：多接口 + HTML 解析兜底，需 Cookie。

    每次请求都过一次 risk_control 分类：「要登录」「被当成脚本访问」「限流」
    「接口自己拒了」和「真的没结果」是五件不同的事，不能都写成「无结果」。
    """
    q = (q or "").strip()
    if not q:
        raise HTTPException(400, "请输入关键词")
    limit = max(1, min(int(limit or 12), 30))
    results = []
    prx = requests_proxies(source="douyin")
    cookies = _douyin_cookies()
    from urllib.parse import quote as _urlquote

    # 冷却还没过就复述上一次判定，一条请求都不发：这里只 peek 不 hit，
    # 否则「多点几次搜索」会把该域降速一次比一次叠得长，而那恰恰是用户唯一还能做的动作。
    cd = HOST_THROTTLE.peek(DY_SEARCH_HOST_URL)
    if cd and _DY_LAST_BLOCK:
        return _douyin_search_in_cooldown(q, cd, bool(cookies))

    try:
        step_delay = max(0.0, float(cfg.data.get("risk_delay_sec") or 0))
    except Exception:
        step_delay = 0.0
    reasons: List[dict] = []
    throttle_info: Dict = {}

    def _note_attempt(tag: str, resp):
        """把一次 HTTP 往来交给分类器，返回 (判定结果, 解析出的 JSON)。"""
        try:
            j, parsed = resp.json(), True
        except Exception:
            j, parsed = {}, False
        if not isinstance(j, dict):
            j = {}
        ra = 0.0
        try:
            ra = float((getattr(resp, "headers", {}) or {}).get("retry-after") or 0)
        except Exception:
            ra = 0.0
        d = risk_control.classify_http(
            status=int(getattr(resp, "status_code", 0) or 0),
            content_type=str((getattr(resp, "headers", {}) or {}).get("content-type") or ""),
            text=str(getattr(resp, "text", "") or ""),
            json_data=j or None,
            json_seen=parsed,
            cookie_names=[c.name for c in (getattr(resp, "cookies", None) or [])],
            retry_after=ra,
        )
        d["via"] = tag
        d["describe"] = risk_control.describe(d)
        reasons.append(d)
        if d.get("throttle") and cfg.data.get("adaptive_throttle", True) and not throttle_info:
            throttle_info.update(HOST_THROTTLE.hit(
                "https://www.douyin.com/",
                cooldown=float(cfg.data.get("risk_cooldown_429") or 60),
            ) or {})
        return d, j

    headers_list = [
        {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Referer": "https://www.douyin.com/search/" + _urlquote(q),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
        },
        {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
            "Referer": "https://www.douyin.com/",
            "Accept": "application/json, text/plain, */*",
        },
    ]
    apis = [
        (
            "api1",
            "https://www.douyin.com/aweme/v1/web/general/search/single/"
            f"?device_platform=webapp&aid=6383&channel=channel_pc_web"
            f"&search_channel=aweme_general&keyword={_urlquote(q)}&search_source=normal_search"
            f"&query_correct_type=1&is_filter_search=0&from_group_id=&offset=0&count={limit}"
        ),
        (
            "api2",
            "https://www.douyin.com/aweme/v1/web/search/item/"
            f"?device_platform=webapp&aid=6383&keyword={_urlquote(q)}&count={limit}&offset=0"
        ),
    ]
    first_try = True
    for headers in headers_list:
        if results:
            break
        kw = {"timeout": 18, "headers": headers}
        if cookies:
            kw["cookies"] = cookies
        if prx:
            kw["proxies"] = prx
        for tag, api in apis:
            if not first_try and step_delay:
                time.sleep(step_delay)   # 遵守「风控与加速」的节奏设置，别一次把接口刷完
            first_try = False
            try:
                resp = requests.get(api, **kw)
                _d, j = _note_attempt(tag, resp)
                got = _parse_douyin_aweme_list(j, limit)
                if got:
                    results.extend(got)
                    break
            except Exception as e:
                reasons.append({"via": tag, "kind": risk_control.NETWORK,
                                "human": "请求没走通", "server_msg": str(e)[:200],
                                "throttle": False, "code": "", "action": "", "evidence": []})
                continue

    # HTML 搜索页兜底：只在「带着 Cookie」时才试 —— 实测没有 Cookie 时这一趟拿到的
    # 是字节的 JS 校验页（Set-Cookie: __ac_nonce，正文只有 byted_acrawler 脚本），必然零结果。
    if not results and cookies:
        try:
            if step_delay:
                time.sleep(step_delay)
            kw = {"timeout": 18, "headers": headers_list[0]}
            if cookies:
                kw["cookies"] = cookies
            if prx:
                kw["proxies"] = prx
            page = requests.get(f"https://www.douyin.com/search/{_urlquote(q)}", **kw)
            _note_attempt("html", page)
            text = page.text or ""
            # 常见嵌入：aweme_id":"7xxxxxxxxxxxxx"
            ids = re.findall(r'"aweme_id"\s*:\s*"(\d{6,})"', text)
            if not ids:
                ids = re.findall(r"/video/(\d{15,})", text)
            seen = set()
            for aid in ids:
                if aid in seen:
                    continue
                seen.add(aid)
                results.append({
                    "platform": "douyin",
                    "id": aid,
                    "title": f"{q} · {aid}",
                    "url": f"https://www.douyin.com/video/{aid}",
                    "uploader": "",
                    "thumbnail": "",
                    "content_type": "video",
                    "duration": "",
                    "views": "",
                })
                if len(results) >= limit:
                    break
        except Exception as e:
            reasons.append({"via": "html", "kind": risk_control.NETWORK,
                            "human": "请求没走通", "server_msg": str(e)[:200],
                            "throttle": False, "code": "", "action": "", "evidence": []})

    risk = pick_risk_reason(reasons)
    note = "ok"
    risk_kind = risk.get("kind") or ""
    if results and risk_kind not in ("", risk_control.EMPTY, risk_control.UNKNOWN):
        # 前面被挡过、后面某个入口通了：结论按实际结果走，但被挡的那次要留痕
        log_mgr.log(f"抖音搜索部分入口被挡（{risk_kind}），已由其它入口取回 {len(results)} 条", "info")
    if not results:
        why = risk.get("describe") or "接口没有返回条目，也没给出可判定的原因"
        note = f"无结果：{why}" + (f"。{risk.get('action')}" if risk.get("action") else "")
        if throttle_info:
            note += (f"（已自动降速：{throttle_info.get('host')} 同时只跑 1 个，"
                     f"冷却 {throttle_info.get('cooldown', 0):.0f}s）")
            # 记住这次判定：冷却期内的下一次搜索直接复述它，不再去敲站点的门
            _DY_LAST_BLOCK.update({
                "kind": risk.get("kind") or "",
                "code": risk.get("code") or "",
                "server_msg": risk.get("server_msg") or "",
                "human": risk.get("human") or "",
                "describe": why,
                "action": risk.get("action") or "",
                "evidence": risk.get("evidence") or [],
                "via": risk.get("via") or "",
            })
        log_mgr.log(
            f"抖音搜索无结果 q={q}：{why}"
            + (f"｜依据 {','.join(risk.get('evidence') or [])}" if risk.get("evidence") else "")
            + (f"｜已降速 {throttle_info.get('host')}" if throttle_info else "")
            + (f"（{throttle_info.get('cooldown', 0):.0f}s）" if throttle_info else ""),
            "warning" if risk.get("throttle") or risk.get("kind") in (
                risk_control.BOT_CHALLENGE, risk_control.RATE_LIMITED) else "info",
        )
    return {
        "results": results[:limit],
        "count": len(results[:limit]),
        "note": note,
        "has_cookie": bool(cookies),
        "risk": {
            "kind": risk.get("kind") or "",
            "code": risk.get("code") or "",
            "server_msg": risk.get("server_msg") or "",
            "human": risk.get("describe") or "",
            "action": risk.get("action") or "",
            "evidence": risk.get("evidence") or [],
            "via": risk.get("via") or "",
        },
        "throttle": throttle_info,
        "attempts": [{"via": r.get("via"), "kind": r.get("kind"), "code": r.get("code")}
                     for r in reasons],
    }


def start_live_monitor_scheduler():
    """后台定时检测监控房间是否开播（默认每 30 秒）"""
    global _live_monitor_stop, _live_monitor_thread
    if _live_monitor_thread and _live_monitor_thread.is_alive():
        return

    def loop():
        global _live_monitor_stop
        while not _live_monitor_stop:
            try:
                items = _load_live_monitors()
                if items:
                    # 有监控时才扫，避免空转日志
                    api_live_monitor_scan()
                # 录满自动收 + 录完自动转码：手动开的录制没有监控可挂，所以每轮都要跑
                try:
                    _live_recording_tick()
                except Exception as e:
                    try:
                        log_mgr.log(f"直播录制收尾检查异常: {e}", "warning",
                                    k="srv.live.tick_error", kv={"e": str(e)})
                    except Exception:
                        pass
            except Exception as e:
                try:
                    log_mgr.log(f"直播监控定时扫描异常: {e}", "warning",
                                k="srv.live.scan_error", kv={"e": str(e)})
                except Exception:
                    pass
            # 分段 sleep，便于快速停止
            for _ in range(6):  # ~30s
                if _live_monitor_stop:
                    return
                time.sleep(5)

    _live_monitor_stop = False
    _live_monitor_thread = threading.Thread(target=loop, daemon=True)
    _live_monitor_thread.start()
    log_mgr.log("直播监控定时扫描已启动（约每 30 秒）", k="srv.live.scheduler_started")


def start_telegram_command_poller():
    """后台轮询 Telegram 消息，实现远程命令"""
    def loop():
        while True:
            try:
                if tg_notifier.enabled() and cfg.data.get("telegram_commands_enabled", True):
                    tg_notifier.poll_once(queue=queue, sub_mgr=sub_mgr)
            except Exception as e:
                try:
                    log_mgr.log(f"TG 命令轮询异常: {e}", "warning")
                except Exception:
                    pass
            time.sleep(3)

    t = threading.Thread(target=loop, daemon=True)
    t.start()
    log_mgr.log("Telegram 远程命令轮询已启动")



# ==================== 网页嗅探 / 资源库 / RSS / 转码 ====================
# This module is merged into server.py

_MEDIA_URL_RE = re.compile(
    r'(?i)(https?://[^\s"\'<>\\]+?\.(?:m3u8|mpd|mp4|flv|webm|m4a|mp3|aac|ogg|ts|mkv|mov)(?:\?[^\s"\'<>\\]*)?)'
)
_SRC_RE = re.compile(
    r'(?is)<(?:video|audio|source|iframe)[^>]+(?:src|data-src)=["\']([^"\']+)["\']'
)
_HREF_RE = re.compile(
    r'(?is)<a[^>]+href=["\']([^"\']+\.(?:mp4|m3u8|flv|webm|mp3|m4a|mkv)(?:\?[^"\']*)?)["\']'
)


def _abs_url(base: str, u: str) -> str:
    from urllib.parse import urljoin
    if not u:
        return ""
    u = u.strip()
    if u.startswith("//"):
        return "https:" + u
    if u.startswith("http"):
        return u
    return urljoin(base, u)


def sniff_page_media(page_url: str, proxy: str = "", timeout: int = 25) -> List[dict]:
    """本地嗅探：拉取网页 HTML + 正则提取媒体链接，并用 yt-dlp 辅助探测。"""
    page_url = normalize_url((page_url or "").strip())
    if not page_url.startswith("http"):
        raise ValueError("无效链接")
    results = []
    seen = set()

    def add(url: str, kind: str = "", source: str = "html", title: str = ""):
        url = _abs_url(page_url, url)
        if not url or not url.startswith("http"):
            return
        url = url.split("#")[0]
        key = url.split("?")[0].lower()
        if url in seen:
            return
        seen.add(url)
        seen.add(key)
        low = url.lower()
        if not kind:
            if ".m3u8" in low:
                kind = "hls"
            elif ".mpd" in low:
                kind = "dash"
            elif any(x in low for x in (".mp3", ".m4a", ".aac", ".ogg")):
                kind = "audio"
            elif any(x in low for x in (".mp4", ".flv", ".webm", ".mkv", ".ts", ".mov")):
                kind = "video"
            else:
                kind = "media"
        results.append({
            "url": url,
            "kind": kind,
            "source": source,
            "title": title or "",
        })

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    proxies = http_proxies(page_url, proxy)
    html = ""
    try:
        r = requests.get(
            page_url, headers=headers, proxies=proxies, timeout=timeout, verify=False
        )
        r.raise_for_status()
        r.encoding = r.apparent_encoding or r.encoding or "utf-8"
        html = r.text or ""
    except Exception as e:
        log_mgr.log(f"嗅探拉取页面失败: {e}", "warning")

    if html:
        for m in _MEDIA_URL_RE.finditer(html):
            add(m.group(1), source="regex")
        for m in _SRC_RE.finditer(html):
            add(m.group(1), source="tag")
        for m in _HREF_RE.finditer(html):
            add(m.group(1), source="href")
        for m in re.finditer(
            r'["\'](?:url|playUrl|play_url|videoUrl|video_url|src|stream|m3u8)["\']\s*:\s*["\'](https?://[^"\']+)["\']',
            html,
            re.I,
        ):
            add(m.group(1), source="json")

    try:
        opts = engine._ydl_opts(cfg.data, for_info=True, url=page_url)
        opts["extract_flat"] = "in_playlist"
        opts["skip_download"] = True
        opts["quiet"] = True
        opts["no_warnings"] = True
        import yt_dlp

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(page_url, download=False)
        if info:
            title = info.get("title") or ""
            if info.get("url") and not info.get("entries"):
                add(info.get("url"), kind="direct", source="ytdlp", title=title)
            for f in info.get("formats") or []:
                u = f.get("url") or ""
                if not u:
                    continue
                vcodec = f.get("vcodec") or "none"
                acodec = f.get("acodec") or "none"
                kind = "video" if vcodec != "none" else ("audio" if acodec != "none" else "media")
                proto = f.get("protocol") or ""
                if "m3u8" in proto:
                    kind = "hls"
                note = f.get("format_note") or f.get("format_id") or ""
                h = f.get("height") or ""
                t = f"{title} [{note} {h}p]".strip() if title else note
                add(u, kind=kind, source="ytdlp-format", title=t)
            for e in info.get("entries") or []:
                if not e:
                    continue
                eu = e.get("url") or e.get("webpage_url") or ""
                et = e.get("title") or title
                if eu:
                    add(eu, kind="entry", source="ytdlp-entry", title=et)
            results.insert(
                0,
                {
                    "url": info.get("webpage_url") or page_url,
                    "kind": "page",
                    "source": "ytdlp",
                    "title": title or page_url,
                    "note": "可用 yt-dlp 整页下载",
                },
            )
    except Exception as e:
        log_mgr.log(f"嗅探 yt-dlp: {e}", "info")

    order = {
        "page": 0,
        "hls": 1,
        "dash": 2,
        "video": 3,
        "audio": 4,
        "direct": 5,
        "entry": 6,
        "media": 7,
    }
    results.sort(key=lambda x: order.get(x.get("kind"), 9))
    return results[:80]



class SniffBody(BaseModel):
    url: str


@app.post("/api/sniff")
def api_sniff(body: SniffBody):
    try:
        items = sniff_page_media(body.url)
    except Exception as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "count": len(items), "items": items}


def _is_junk_sniff_url(url: str) -> bool:
    """过滤埋点 / 过长假 URL，避免把 data.bilibili.com/log 当视频下。"""
    if not url or not isinstance(url, str):
        return True
    if not url.startswith("http"):
        return True
    low = url.lower()
    if "data.bilibili.com/log" in low or "/log/web" in low:
        return True
    if len(url) > 2500:
        return True
    if "mpd_list" in low and "data.bilibili" in low:
        return True
    # 明显非媒体
    if re.search(r"\.(js|css|png|jpe?g|gif|svg|woff2?)(\?|$)", low):
        return True
    return False


def _cdn_host_score(url: str) -> int:
    """优先官方 bilivideo / upos，降低第三方 edge 域名（易 403）。"""
    low = (url or "").lower()
    score = 0
    if "pbp/data" in low or "bvc.bilivideo.com/pbp" in low:
        return -100
    if "mountaintoys" in low or ".edge." in low:
        score -= 50
    if re.search(r":\d{4,5}/", low):  # 非标端口镜像
        score -= 20
    if "upos-sz-" in low or "upos-hz-" in low:
        score += 30
    if "bilivideo.com" in low and "mcdn.bilivideo" not in low:
        score += 25
    if "mcdn.bilivideo" in low:
        score += 5
    if "akamaized" in low or "cn-hljheb" in low or "cn-" in low:
        score += 15
    return score


def _pick_bili_m4s_pair(urls: List[str]) -> Optional[tuple]:
    """从嗅探列表中挑 1 条视频 m4s + 1 条音频 m4s（官方 CDN 优先）。"""
    vids, auds = [], []
    for u in urls:
        low = u.lower()
        if ".m4s" not in low and "bilivideo" not in low and "upos-" not in low:
            continue
        if "pbp/data" in low:
            continue
        if re.search(r"[-_](30280|30002|30277|30112|30216|30232)[-_.?]", low) or "30280" in low:
            auds.append(u)
        else:
            vids.append(u)
    if not vids and not auds:
        return None
    vids.sort(key=_cdn_host_score, reverse=True)
    auds.sort(key=_cdn_host_score, reverse=True)
    v = vids[0] if vids else None
    a = auds[0] if auds else None
    if v and a:
        return (v, a)
    return None


def _load_bili_cookie_header() -> str:
    """从平台 cookie 文件拼 Cookie 头，降低 m4s 403。"""
    try:
        pc = (cfg.data.get("platform_cookies") or {}).get("bilibili") or {}
        path = (pc.get("file") or "").strip() or str(platform_cookie_path("bilibili"))
        if not path or not Path(path).exists():
            # 全局 cookies.txt
            g = (cfg.data.get("cookie_file") or "").strip()
            if g and Path(g).exists():
                path = g
            else:
                return ""
        pairs = []
        for line in Path(path).read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) >= 7:
                domain, name, val = parts[0], parts[5], parts[6]
                if "bilibili" in domain or domain.startswith("."):
                    pairs.append(f"{name}={val}")
        # 常用关键
        keys = ("SESSDATA", "bili_jct", "DedeUserID", "buvid3", "buvid4", "sid")
        preferred = [p for p in pairs if any(p.startswith(k + "=") for k in keys)]
        rest = [p for p in pairs if p not in preferred]
        return "; ".join((preferred + rest)[:30])
    except Exception:
        return ""


def _sniff_looks_hls(u: str) -> bool:
    """嗅探到的地址是不是 HLS（含 master.txt / index-*.txt 伪装）。"""
    low = (u or "").lower()
    return (
        ".m3u8" in low
        or "/hls/" in low
        or "/hls3/" in low
        or ".urlset" in low
        or bool(re.search(r"(master|index|playlist)[^/]*\.(txt|m3u)(\?|$)", low))
    )


def _sniff_enqueue(urls, opts: dict) -> dict:
    """嗅探 / 外部扩展推来的直链按类型分派入队：HLS 走专用引擎，B站 m4s 走音视合并，其余走通用队列。"""
    urls = urls or []
    if isinstance(urls, str):
        urls = [urls]
    urls = [u.strip() for u in urls if isinstance(u, str) and u.strip().startswith("http")]
    urls = [u for u in urls if not _is_junk_sniff_url(u)]
    if not urls:
        raise HTTPException(
            400,
            "无有效媒体链接（已过滤埋点/过长 URL）。请确认扩展抓到的是 bilivideo.com 的 m4s/mp4，而不是 data.bilibili.com/log",
        )
    opts = dict(opts or {})
    # 嗅探到的 HLS（含 master.txt / index-*.txt 伪装）默认走专用引擎
    if any(_sniff_looks_hls(u) for u in urls):
        opts.setdefault("use_hls_engine", True)
        opts.setdefault("direct_cdn", False)
        # 同一批里若有 master，丢掉 index/playlist，避免重复任务卡在 10%
        masters = [u for u in urls if re.search(r"master\.(txt|m3u8|m3u)(\?|$)", u, re.I)]
        if masters:
            urls = masters
            log_mgr.log(f"嗅探 HLS：仅保留 master（{len(urls)} 条），忽略 index 子列表",
                        k="srv.sniff.hls_master_only", kv={"n": len(urls)})

    # B站 DASH：若同时有视频+音频 m4s，走合并任务（与「嗅探合并下载」一致）
    pair = _pick_bili_m4s_pair(urls)
    if pair and (opts.get("bilibili_m4s") or any(".m4s" in u.lower() for u in urls)):
        v_url, a_url = pair
        out_dir = opts.get("download_dir") or cfg.data.get("download_dir") or str(DEFAULT_DOWNLOAD_DIR)
        proxy = task_proxy_override(opts)
        tid = str(uuid.uuid4())
        title = safe_filename_component(
            opts.get("title") or f"bilibili_{tid[:8]}", 60
        )
        # 备用镜像：同列表里其余 video/audio
        alt_v, alt_a = [], []
        for u in urls:
            low = u.lower()
            if u in (v_url, a_url) or "pbp" in low:
                continue
            if re.search(r"[-_](30280|30002|30277)[-_.?]", low) or "30280" in low:
                alt_a.append(u)
            elif ".m4s" in low or "bilivideo" in low:
                alt_v.append(u)
        task = DownloadTask(
            id=tid,
            url=v_url,
            title=title,
            status=TaskStatus.QUEUED.value,
            created_at=datetime.now().isoformat(timespec="seconds"),
        )
        task._opts = opts  # type: ignore
        queue.tasks[tid] = task
        log_mgr.log(
            f"[{tid[:8]}] B站 m4s 合并 video_score={_cdn_host_score(v_url)} "
            f"audio_score={_cdn_host_score(a_url)} alt_a={len(alt_a)}",
            k="srv.sniff.bili_m4s_pair",
            kv={"tid": tid[:8], "video_score": _cdn_host_score(v_url),
                "audio_score": _cdn_host_score(a_url), "alt_a": len(alt_a)})
        threading.Thread(
            target=_run_sniff_merge_task,
            kwargs={
                "task_id": tid,
                "video_url": v_url,
                "audio_url": a_url,
                "title": title,
                "out_dir": out_dir,
                "proxy": proxy,
                "alt_audio_urls": alt_a,
                "alt_video_urls": alt_v,
            },
            daemon=True,
        ).start()
        return {"ok": True, "ids": [tid], "count": 1, "mode": "bilibili_m4s_merge"}

    # 单条直链：仍加入队列（yt-dlp / http）
    # 纯 m4s 单轨无法播放，提示用户多选音视频
    only_m4s = all(".m4s" in u.lower() for u in urls)
    if only_m4s and len(urls) == 1:
        log_mgr.log("警告: 仅一条 m4s（可能是纯视频或纯音频轨），播放可能无声或无画面", "warning",
                    k="srv.sniff.only_one_m4s")

    ids = queue.add_urls(urls, opts)
    return {"ok": True, "ids": ids, "count": len(ids)}


@app.post("/api/sniff/download")
def api_sniff_download(body: dict):
    return _sniff_enqueue(body.get("urls") or [], dict(body.get("options") or {}))


def _download_url_to_file(url: str, dest: Path, proxy: str = "", referer: str = "") -> None:
    """HTTP 直链下载（嗅探 CDN / 合并轨）。优先 curl_cffi 模拟浏览器 TLS，降低 403。"""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
        "Accept": "*/*",
        "Accept-Encoding": "identity",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Connection": "keep-alive",
        "Origin": "https://www.bilibili.com",
        "Referer": referer or "https://www.bilibili.com",
    }
    low = (url or "").lower()
    if "bilibili" in low or "bilivideo" in low or "upos-" in low or ".m4s" in low:
        headers["Referer"] = referer or "https://www.bilibili.com"
        headers["Origin"] = "https://www.bilibili.com"
        ck = _load_bili_cookie_header()
        if ck:
            headers["Cookie"] = ck
    proxies = http_proxies(url, proxy)
    dest.parent.mkdir(parents=True, exist_ok=True)

    if _impersonate_on():
        try:
            r, fp = _impersonate_get(
                url, headers=headers, timeout=180, proxies=proxies, stream=True
            )
            try:
                with open(dest, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1024 * 256):
                        if chunk:
                            f.write(chunk)
            finally:
                try:
                    r.close()
                except Exception:
                    pass
            if dest.stat().st_size > 0:
                log_mgr.log(f"直链下载 TLS 指纹={fp}")
                return
        except Exception:
            pass  # 回退 requests

    with requests.get(
        url,
        headers=headers,
        proxies=proxies,
        stream=True,
        timeout=180,
        verify=False,
        allow_redirects=True,
    ) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 256):
                if chunk:
                    f.write(chunk)


def _merge_video_audio_with_ffmpeg(
    video_path: Path,
    audio_path: Path,
    out_path: Path,
    log: Callable = print,
) -> bool:
    """用 ffmpeg 无损合并视频+音频。"""
    ff = ffmpeg_mgr.find()
    if not ff:
        log("未找到 ffmpeg，无法合并", "error")
        return False
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ff, "-y", "-err_detect", "ignore_err",
        "-i", str(video_path),
        "-i", str(audio_path),
        "-c", "copy",
        "-map", "0:v:0",
        "-map", "1:a:0?",
        str(out_path),
    ]
    try:
        kw: dict = {"capture_output": True, "timeout": 3600}
        if sys.platform == "win32":
            kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        r = subprocess.run(cmd, **kw)
        if r.returncode != 0:
            err = (r.stderr or b"").decode("utf-8", errors="ignore")[-500:]
            log(f"ffmpeg 合并失败: {err}", "error")
            return False
        return out_path.exists() and out_path.stat().st_size > 0
    except Exception as e:
        log(f"ffmpeg 合并异常: {e}", "error")
        return False


def _run_sniff_merge_task(
    task_id: str,
    video_url: str,
    audio_url: str,
    title: str,
    out_dir: str,
    proxy: str = "",
    alt_audio_urls: Optional[List[str]] = None,
    alt_video_urls: Optional[List[str]] = None,
):
    """后台：下载视频轨 + 音频轨并合并。音轨 403 时尝试备用 URL。"""
    task = queue.tasks.get(task_id)
    if not task:
        return
    tmp_dir = Path(out_dir) / "_merge_tmp" / task_id[:8]
    try:
        task.status = TaskStatus.DOWNLOADING.value
        task.progress = 5
        task.title = title or "嗅探合并下载"
        safe = safe_filename_component(title or "merged", 60)
        video_tmp = tmp_dir / "video.m4s"
        audio_tmp = tmp_dir / "audio.m4s"
        out_path = Path(out_dir) / f"{safe}.mkv"

        def try_download(urls: List[str], dest: Path, label: str) -> bool:
            last = None
            for u in urls:
                if not u:
                    continue
                try:
                    log_mgr.log(f"[{task_id[:8]}] {label}: {_cdn_host_score(u)} {u[:80]}…")
                    _download_url_to_file(u, dest, proxy=proxy, referer="https://www.bilibili.com")
                    if dest.exists() and dest.stat().st_size > 1024:
                        return True
                except Exception as e:
                    last = e
                    log_mgr.log(f"[{task_id[:8]}] {label} 失败: {e}", "warning")
            if last:
                raise last
            return False

        v_list = [video_url] + [u for u in (alt_video_urls or []) if u != video_url]
        v_list = sorted(set(v_list), key=_cdn_host_score, reverse=True)
        a_list = [audio_url] + [u for u in (alt_audio_urls or []) if u != audio_url]
        a_list = sorted(set(a_list), key=_cdn_host_score, reverse=True)

        log_mgr.log(f"[{task_id[:8]}] 开始下载视频轨…",
                    k="srv.sniff.video_start", kv={"tid": task_id[:8]})
        task.progress = 10
        try_download(v_list, video_tmp, "视频轨")
        task.progress = 45
        log_mgr.log(f"[{task_id[:8]}] 视频轨完成，开始下载音频轨…",
                    k="srv.sniff.video_done_audio_start", kv={"tid": task_id[:8]})
        audio_ok = False
        try:
            audio_ok = try_download(a_list, audio_tmp, "音频轨")
        except Exception as e:
            log_mgr.log(f"[{task_id[:8]}] 全部音频轨失败（将仅保留视频）: {e}", "warning",
                        k="srv.sniff.all_audio_failed", kv={"tid": task_id[:8], "e": str(e)})

        task.progress = 75
        if audio_ok:
            log_mgr.log(f"[{task_id[:8]}] 开始 ffmpeg 合并…",
                        k="srv.sniff.merge_start", kv={"tid": task_id[:8]})
            ok = _merge_video_audio_with_ffmpeg(video_tmp, audio_tmp, out_path, log=log_mgr.log)
        else:
            # 仅视频：复制为 mkv/mp4 容器尝试
            out_path = Path(out_dir) / f"{safe}_video_only.mp4"
            try:
                shutil.copy2(video_tmp, out_path)
                ok = out_path.exists()
                log_mgr.log(f"[{task_id[:8]}] 仅视频轨已保存（无声）: {out_path.name}", "warning",
                            k="srv.sniff.video_only_saved",
                            kv={"tid": task_id[:8], "name": out_path.name})
            except Exception:
                ok = False

        if ok:
            task.status = TaskStatus.FINISHED.value
            task.progress = 100
            task.filepath = str(out_path)
            task.title = out_path.name
            log_mgr.log(f"[{task_id[:8]}] 完成: {out_path.name}",
                        k="srv.sniff.done", kv={"tid": task_id[:8], "name": out_path.name})
            try:
                queue.history.add({
                    "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "url": video_url,
                    "title": task.title,
                    "status": "finished",
                    "filepath": str(out_path),
                })
            except Exception:
                pass
        else:
            task.status = TaskStatus.FAILED.value
            task.error_msg = "合并/保存失败，请查看日志"
    except Exception as e:
        task.status = TaskStatus.FAILED.value
        task.error_msg = str(e)[:200]
        log_mgr.log(f"[{task_id[:8]}] 嗅探合并失败: {e}", "error",
                    k="srv.sniff.merge_failed", kv={"tid": task_id[:8], "e": str(e)})
    finally:
        try:
            if tmp_dir.exists():
                shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            pass
        with queue.lock:
            queue.running = max(0, queue.running - 1)
        queue._pump()


@app.post("/api/sniff/download_merge")
def api_sniff_download_merge(body: dict):
    """
    选择一条视频轨 + 一条音频轨，下载后自动用 ffmpeg 合并为 mkv。
    body: { video_url, audio_url, title? }
    """
    video_url = (body.get("video_url") or "").strip()
    audio_url = (body.get("audio_url") or "").strip()
    title = (body.get("title") or "").strip()
    if not video_url.startswith("http") or not audio_url.startswith("http"):
        raise HTTPException(400, "需要有效的 video_url 和 audio_url")
    if not ffmpeg_mgr.find():
        raise HTTPException(400, "未找到 ffmpeg，请先在设置中更新/安装 FFmpeg")

    cfg_data = cfg.data
    out_dir = body.get("download_dir") or cfg_data.get("download_dir") or str(DEFAULT_DOWNLOAD_DIR)
    proxy = task_proxy_override(body)

    tid = str(uuid.uuid4())
    task = DownloadTask(
        id=tid,
        url=video_url,
        title=title or "嗅探合并中…",
        status=TaskStatus.QUEUED.value,
    )
    task._opts = {"merge_sniff": True}  # type: ignore
    queue.tasks[tid] = task
    with queue.lock:
        queue.running += 1
    threading.Thread(
        target=_run_sniff_merge_task,
        args=(tid, video_url, audio_url, title, out_dir, proxy),
        daemon=True,
    ).start()
    return {"ok": True, "id": tid, "count": 1}


# ----- 浏览器 CDP 网络嗅探（对齐下蛋：连接 Chrome 监听页面加载的媒体） -----
_MEDIA_HINTS = (
    ".m3u8", ".mpd", ".mp4", ".flv", ".webm", ".m4a", ".mp3", ".aac", ".ts", ".m4s",
    "mime=video", "mime=audio", "content-type=video", "content-type=audio",
    "/video/", "/audio/", "googlevideo.com", "bilivideo", "bytefcdn", "xhscdn",
)


def _looks_like_media_url(url: str, mime: str = "") -> bool:
    low = (url or "").lower()
    mime = (mime or "").lower()
    if any(x in mime for x in ("video/", "audio/", "mpegurl", "dash+xml", "application/vnd.apple")):
        return True
    if any(h in low for h in _MEDIA_HINTS):
        return True
    return False


class BrowserSniffer:
    """通过 Chrome DevTools Protocol 监听网络请求，捕获页面真实加载的媒体。"""

    def __init__(self):
        self.lock = threading.Lock()
        self.running = False
        self.port = 9222
        self.mode = ""  # attach | launch
        self.page_url = ""
        self.resources: Dict[str, dict] = {}
        self._ws = None
        self._thread = None
        self._stop = threading.Event()
        self._proc = None
        self._msg_id = 0
        self.status = "idle"
        self.error = ""

    def _next_id(self) -> int:
        self._msg_id += 1
        return self._msg_id

    def _find_chrome(self) -> Optional[str]:
        candidates = []
        if sys.platform == "win32":
            pf = os.environ.get("PROGRAMFILES", r"C:\Program Files")
            pf86 = os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
            local = os.environ.get("LOCALAPPDATA", "")
            candidates = [
                str(Path(pf) / "Google/Chrome/Application/chrome.exe"),
                str(Path(pf86) / "Google/Chrome/Application/chrome.exe"),
                str(Path(local) / "Google/Chrome/Application/chrome.exe"),
                str(Path(pf) / "Microsoft/Edge/Application/msedge.exe"),
                str(Path(pf86) / "Microsoft/Edge/Application/msedge.exe"),
                str(Path(local) / "Microsoft/Edge/Application/msedge.exe"),
            ]
        elif sys.platform == "darwin":
            candidates = [
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
                "/Applications/Chromium.app/Contents/MacOS/Chromium",
            ]
        else:
            for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge"):
                p = shutil.which(name)
                if p:
                    candidates.append(p)
        for c in candidates:
            if c and Path(c).exists():
                return c
        return None

    def _cdp_http(self, path: str = "/json/version"):
        r = requests.get(f"http://127.0.0.1:{self.port}{path}", timeout=3)
        r.raise_for_status()
        return r.json()

    def _get_browser_ws_url(self) -> str:
        ver = self._cdp_http("/json/version")
        ws = ver.get("webSocketDebuggerUrl") or ""
        if not ws:
            raise RuntimeError("无法获取浏览器 CDP WebSocket 地址")
        return ws

    def _add_resource(self, url: str, mime: str = "", method: str = "", status: int = 0, source: str = ""):
        if not url or not url.startswith("http"):
            return
        if url.startswith("data:") or url.startswith("blob:"):
            return
        if not _looks_like_media_url(url, mime):
            return
        with self.lock:
            if url in self.resources:
                rec = self.resources[url]
                if mime and not rec.get("mime"):
                    rec["mime"] = mime
                if status:
                    rec["status"] = status
                return
            low = url.lower()
            kind = "media"
            if ".m3u8" in low or "mpegurl" in (mime or "").lower():
                kind = "hls"
            elif ".mpd" in low or "dash" in (mime or "").lower():
                kind = "dash"
            elif (mime or "").startswith("audio") or any(x in low for x in (".mp3", ".m4a", ".aac")):
                kind = "audio"
            elif (mime or "").startswith("video") or any(x in low for x in (".mp4", ".flv", ".webm", ".ts", ".m4s")):
                kind = "video"
            self.resources[url] = {
                "url": url,
                "kind": kind,
                "mime": mime or "",
                "method": method or "",
                "status": status or 0,
                "source": "browser-cdp",
                "title": title or "",
                "ts": datetime.now().strftime("%H:%M:%S"),
            }

    def _listen_loop(self, ws_url: str):
        try:
            import websocket
        except ImportError:
            self.error = "缺少 websocket-client，请 pip install websocket-client"
            self.status = "error"
            self.running = False
            return

        def on_message(ws, message):
            try:
                msg = json.loads(message)
            except Exception:
                return
            method = msg.get("method") or ""
            params = msg.get("params") or {}
            if method == "Network.requestWillBeSent":
                req = params.get("request") or {}
                url = req.get("url") or ""
                self._add_resource(url, method=req.get("method") or "GET")
            elif method == "Network.responseReceived":
                resp = params.get("response") or {}
                url = resp.get("url") or ""
                mime = resp.get("mimeType") or ""
                status = int(resp.get("status") or 0)
                self._add_resource(url, mime=mime, status=status)
            elif method == "Target.attachedToTarget":
                sid = params.get("sessionId")
                if sid and self._ws:
                    try:
                        mid = self._next_id()
                        self._ws.send(json.dumps({
                            "id": mid, "method": "Network.enable",
                            "sessionId": sid,
                        }))
                        mid = self._next_id()
                        self._ws.send(json.dumps({
                            "id": mid, "method": "Target.setAutoAttach",
                            "params": {
                                "autoAttach": True,
                                "waitForDebuggerOnStart": False,
                                "flatten": True,
                            },
                            "sessionId": sid,
                        }))
                    except Exception:
                        pass

        def on_error(ws, err):
            err_s = str(err) if err is not None else "unknown"
            log_mgr.log(f"CDP 嗅探错误: {err_s}", "warning",
                        k="srv.sniff.cdp_error", kv={"err": err_s})
            self.error = err_s
            self.status = "error"
            # 出错后自动停止，避免反复重连刷日志
            self._stop.set()
            self.running = False
            try:
                if self._ws:
                    self._ws.close()
            except Exception:
                pass

        def on_close(ws, *a):
            if self._stop.is_set():
                if self.status != "error":
                    self.status = "stopped"
            else:
                self.status = "closed"
            self.running = False

        def on_open(ws):
            self.status = "listening"
            self.error = ""
            # 浏览器级：发现 target + 自动 attach + Network.enable
            cmds = [
                {"id": self._next_id(), "method": "Target.setDiscoverTargets", "params": {"discover": True}},
                {
                    "id": self._next_id(),
                    "method": "Target.setAutoAttach",
                    "params": {
                        "autoAttach": True,
                        "waitForDebuggerOnStart": False,
                        "flatten": True,
                    },
                },
                {"id": self._next_id(), "method": "Network.enable", "params": {}},
            ]
            for c in cmds:
                ws.send(json.dumps(c))
            # 已有页面也 enable network
            try:
                tabs = self._cdp_http("/json")
                if isinstance(tabs, list):
                    for t in tabs:
                        if t.get("type") == "page" and t.get("webSocketDebuggerUrl"):
                            # 通过 Target.attachToTarget
                            ws.send(json.dumps({
                                "id": self._next_id(),
                                "method": "Target.attachToTarget",
                                "params": {"targetId": t.get("id"), "flatten": True},
                            }))
            except Exception:
                pass
            log_mgr.log(f"浏览器 CDP 嗅探已启动 port={self.port}",
                        k="srv.sniff.cdp_started", kv={"port": self.port})

        self._ws = websocket.WebSocketApp(
            ws_url,
            on_open=on_open,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
        )
        while not self._stop.is_set():
            try:
                self._ws.run_forever(ping_interval=20, ping_timeout=10)
            except Exception as e:
                self.error = str(e)
                self.status = "error"
                log_mgr.log(f"CDP 嗅探异常退出: {e}", "warning",
                            k="srv.sniff.cdp_crashed", kv={"e": str(e)})
                self._stop.set()
                break
            if self._stop.is_set():
                break
            # 非主动停止时若连接断开，短暂等待后不再无限重连
            if self.status == "error":
                break
            time.sleep(1)
            break  # 断开后不再自动重连，避免错误刷屏
        self.running = False
        if self.status not in ("error", "stopped"):
            self.status = "closed"

    def start_attach(self, port: int = 9222) -> dict:
        if self.running:
            return self.snapshot()
        self.port = int(port or 9222)
        self.mode = "attach"
        self.error = ""
        self.resources.clear()
        self._stop.clear()
        try:
            ws_url = self._get_browser_ws_url()
        except Exception as e:
            raise RuntimeError(
                f"无法连接本机 Chrome CDP (端口 {self.port})。\n"
                f"请先用调试模式启动浏览器，例如：\n"
                f'chrome.exe --remote-debugging-port={self.port}\n'
                f"或点击「启动托管浏览器」。\n详情: {e}"
            )
        self.running = True
        self.status = "connecting"
        self._thread = threading.Thread(target=self._listen_loop, args=(ws_url,), daemon=True)
        self._thread.start()
        return self.snapshot()

    def start_launch(self, port: int = 9222, url: str = "", use_profile: bool = False) -> dict:
        if self.running:
            return self.snapshot()
        chrome = self._find_chrome()
        if not chrome:
            raise RuntimeError("未找到 Chrome / Edge，请安装或改用「连接已有浏览器」")
        self.port = int(port or 9222)
        self.mode = "launch"
        self.page_url = url or "about:blank"
        self.error = ""
        self.resources.clear()
        self._stop.clear()
        user_data = APP_DIR / "browser_sniff_profile"
        user_data.mkdir(parents=True, exist_ok=True)
        args = [
            chrome,
            f"--remote-debugging-port={self.port}",
            "--remote-allow-origins=*",
            "--no-first-run",
            "--no-default-browser-check",
            f"--user-data-dir={user_data}" if use_profile or True else "",
            self.page_url,
        ]
        args = [a for a in args if a]
        try:
            # 若端口已被占用，直接 attach
            try:
                self._cdp_http("/json/version")
                log_mgr.log(f"端口 {self.port} 已有调试浏览器，改为连接",
                            k="srv.sniff.attach_existing", kv={"port": self.port})
                return self.start_attach(self.port)
            except Exception:
                pass
            self._proc = subprocess.Popen(
                args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            # 等待 CDP 就绪
            for _ in range(30):
                time.sleep(0.4)
                try:
                    self._get_browser_ws_url()
                    break
                except Exception:
                    continue
            else:
                raise RuntimeError("浏览器已启动但 CDP 未就绪")
        except Exception as e:
            self.running = False
            raise RuntimeError(f"启动浏览器失败: {e}")
        return self.start_attach(self.port)

    def stop(self) -> dict:
        self._stop.set()
        try:
            if self._ws:
                self._ws.close()
        except Exception:
            pass
        self.running = False
        self.status = "stopped"
        # 不强制杀浏览器进程（用户可能还在用）
        return self.snapshot()

    def clear(self):
        with self.lock:
            self.resources.clear()

    def snapshot(self) -> dict:
        with self.lock:
            items = list(self.resources.values())
        order = {"hls": 0, "dash": 1, "video": 2, "audio": 3, "media": 4}
        items.sort(key=lambda x: (order.get(x.get("kind"), 9), x.get("ts") or ""))
        tabs = []
        try:
            raw = self._cdp_http("/json")
            if isinstance(raw, list):
                for t in raw:
                    if t.get("type") == "page":
                        tabs.append({
                            "title": t.get("title") or "",
                            "url": t.get("url") or "",
                            "id": t.get("id") or "",
                        })
        except Exception:
            pass
        return {
            "running": self.running,
            "status": self.status,
            "mode": self.mode,
            "port": self.port,
            "error": self.error,
            "count": len(items),
            "items": items,
            "tabs": tabs,
        }


browser_sniffer = BrowserSniffer()


@app.get("/api/sniff/browser/status")
def api_sniff_browser_status():
    return browser_sniffer.snapshot()


@app.post("/api/sniff/browser/start")
def api_sniff_browser_start(body: dict = None):
    """
    开始浏览器嗅探。
    mode=attach 连接已开启远程调试的 Chrome
    mode=launch 由本程序拉起 Chrome（独立资料目录）
    """
    body = body or {}
    mode = (body.get("mode") or "launch").lower()
    port = int(body.get("port") or 9222)
    url = (body.get("url") or "").strip()
    try:
        if mode == "attach":
            return {"ok": True, **browser_sniffer.start_attach(port)}
        return {"ok": True, **browser_sniffer.start_launch(port, url=url)}
    except Exception as e:
        raise HTTPException(400, str(e))


@app.post("/api/sniff/browser/stop")
def api_sniff_browser_stop():
    return {"ok": True, **browser_sniffer.stop()}


@app.post("/api/sniff/browser/clear")
def api_sniff_browser_clear():
    browser_sniffer.clear()
    return {"ok": True, **browser_sniffer.snapshot()}


# ---------------- 猫抓（cat-catch）对接 ----------------
# cat-catch 是 GPL-3.0 的浏览器资源嗅探扩展，它自己没有服务端接口，
# 只在「设置 → 发送数据」里把嗅到的资源 POST 到用户填的地址。这里就是那个地址。
# 只按它公开文档写的请求体形状对接，未引用其任何代码；官方文档写明该功能
# 「测试中，不同版本 JSON 结构会有差异」，因此对 data 的形状一律容错。
CATCATCH_RULES_FILE = APP_DIR / "catcatch_rules.json"
_CATCATCH_KEY_TTL = 3600.0
_catcatch_keys: Dict[str, dict] = {}
_catcatch_stat: Dict[str, Any] = {"received": 0, "dropped": 0, "keys": 0, "last": ""}
_catcatch_lock = threading.Lock()


def _catcatch_port() -> int:
    try:
        return int(os.environ.get("MEDIADOWNLOADER_PORT") or 8765)
    except Exception:
        return 8765


def _load_catcatch_rules() -> List[dict]:
    if CATCATCH_RULES_FILE.exists():
        try:
            data = json.loads(CATCATCH_RULES_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return [r for r in data if isinstance(r, dict)]
        except Exception:
            pass
    return []


def _save_catcatch_rules(rules: List[dict]) -> None:
    CATCATCH_RULES_FILE.write_text(
        json.dumps(rules, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _catcatch_match(url: str) -> tuple:
    """按导入的猫抓正则规则决定这条地址收不收。返回 (收不收, 规则标注的扩展名, 命中规则名)。"""
    rules = _load_catcatch_rules()
    if not rules:
        return True, "", ""
    ext, hit = "", ""
    for r in rules:
        pat = str(r.get("regex") or "")
        if not pat or not r.get("enabled", True):
            continue
        try:
            matched = re.search(pat, url, re.I)
        except re.error:
            continue  # 界面上那条会标红，这里不重复报
        if not matched:
            continue
        if r.get("blacklist"):
            return False, "", str(r.get("name") or pat)
        if not ext:
            ext = str(r.get("ext") or "")
        hit = str(r.get("name") or pat)
    return True, ext, hit


def _hls_key_to_hex(raw) -> str:
    """猫抓的密钥是 base64 串（有时是字节数组），而 ffmpeg / N_m3u8DL-RE 要 16 进制。"""
    if isinstance(raw, (list, tuple)):
        try:
            return bytes(int(x) & 0xFF for x in raw).hex()
        except Exception:
            return ""
    s = str(raw or "").strip()
    if not s:
        return ""
    if re.fullmatch(r"[0-9a-fA-F]{16,128}", s):
        return s.lower()
    try:
        import base64
        data = base64.b64decode(s + "=" * (-len(s) % 4))
    except Exception:
        return ""
    return data.hex() if 0 < len(data) <= 64 else ""


def _catcatch_items(data) -> List[dict]:
    """猫抓请求体里的 data：对象、数组、字符串化 JSON、裸链接这几种版本形状都收下。"""
    if isinstance(data, str):
        s = data.strip()
        if s[:1] in ("{", "["):
            try:
                return _catcatch_items(json.loads(s))
            except Exception:
                return []
        return [{"url": s}] if s.startswith("http") else []
    if isinstance(data, dict):
        return [data]
    if isinstance(data, list):
        out: List[dict] = []
        for x in data:
            out.extend(_catcatch_items(x))
        return out
    return []


@app.post("/api/catcatch/push")
async def api_catcatch_push(request: Request):
    """猫抓「发送数据」的接收端。无论成败都回 200 + {ok}，报错只写运行日志，不打密钥与 Cookie 内容。"""
    try:
        raw = (await request.body()).decode("utf-8", errors="ignore")
    except Exception:
        raw = ""
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {"data": payload}
    action = str(payload.get("action") or "").strip().lower()
    tab_id = str(payload.get("tabId") if payload.get("tabId") is not None else "") or "-"

    if action in ("addkey", "key"):
        hexk = _hls_key_to_hex(payload.get("data"))
        if not hexk:
            log_mgr.log("猫抓推送：密钥格式没认出来（要 base64 或 16 进制），本条已忽略", "warning",
                        k="srv.catcatch.key_rejected")
            return {"ok": False, "msg": "密钥格式不识别（要 base64 或 16 进制）"}
        with _catcatch_lock:
            _catcatch_keys[tab_id] = {"hex": hexk, "ts": time.time()}
            _catcatch_stat["keys"] += 1
        log_mgr.log(
            f"猫抓推送：收到 HLS 解密钥 {len(hexk) // 2} 字节（标签页 {tab_id}），"
            f"1 小时内推来的 m3u8 自动带上",
            k="srv.catcatch.key_received",
            kv={"bytes": len(hexk) // 2, "tab": tab_id},
        )
        return {"ok": True, "action": "addKey"}

    items = _catcatch_items(payload.get("data", payload))
    results, dropped = [], 0
    for it in items:
        url = str(it.get("url") or it.get("link") or "").strip()
        if not url.startswith("http"):
            continue
        keep, ext_tag, rule_name = _catcatch_match(url)
        if not keep:
            dropped += 1
            with _catcatch_lock:
                _catcatch_stat["dropped"] += 1
            log_mgr.log(f"猫抓推送：黑名单规则「{rule_name}」挡下 {url[:120]}", "warning",
                        k="srv.catcatch.blocked_by_rule", kv={"rule": rule_name, "url": url[:120]})
            continue
        hdrs = it.get("requestHeaders") or it.get("headers") or {}
        opts: dict = {"skip_plugins": True}  # 推来的已是真实媒体地址，不必再走插件解析
        ref = str(hdrs.get("referer") or hdrs.get("referrer") or it.get("href") or "").strip()
        ck = str(hdrs.get("cookie") or "").strip()
        ua = str(hdrs.get("userAgent") or hdrs.get("user-agent") or "").strip()
        if ref:
            opts["referer"] = ref
        if ck:
            opts["cookie"] = ck
        if ua:
            opts["user_agent"] = ua
        nm = str(it.get("name") or "").strip()
        if nm:
            opts["title"] = safe_filename_component(
                re.sub(r"\.[A-Za-z0-9]{1,5}$", "", nm) or nm, 60
            )
        note = []
        if ref:
            note.append("带 Referer")
        if ck:
            note.append(f"带 Cookie（{len(ck)} 字）")
        if ext_tag:
            note.append(f"规则标注 .{ext_tag}")
        if _sniff_looks_hls(url):
            with _catcatch_lock:
                k = _catcatch_keys.get(tab_id)
            if k and time.time() - float(k.get("ts") or 0) < _CATCATCH_KEY_TTL:
                opts["hls_key"] = k["hex"]
                note.append("带上刚才收到的解密钥")
        try:
            r = _sniff_enqueue([url], opts)
            results.append({"url": url[:200], "ok": True, "ids": r.get("ids") or []})
            if note:
                log_mgr.log(f"猫抓推送：入队 {url[:120]}（{'、'.join(note)}）",
                            k="srv.catcatch.queued_note",
                            kv={"url": url[:120], "note": "、".join(note)})
            else:
                log_mgr.log(f"猫抓推送：入队 {url[:120]}",
                            k="srv.catcatch.queued", kv={"url": url[:120]})
        except HTTPException as e:
            results.append({"url": url[:200], "ok": False, "msg": str(e.detail)})
            log_mgr.log(f"猫抓推送：{url[:120]} 没能入队：{e.detail}", "error",
                        k="srv.catcatch.enqueue_rejected",
                        kv={"url": url[:120], "msg": str(e.detail)})
        except Exception as e:
            results.append({"url": url[:200], "ok": False, "msg": str(e)})
            log_mgr.log(f"猫抓推送：{url[:120]} 入队异常：{e}", "error",
                        k="srv.catcatch.enqueue_failed", kv={"url": url[:120], "e": str(e)})
    with _catcatch_lock:
        _catcatch_stat["received"] += len(results)
        _catcatch_stat["last"] = (
            f"{datetime.now().strftime('%H:%M:%S')} 收到 {len(results)} 条，挡下 {dropped} 条"
            if results or dropped
            else _catcatch_stat.get("last", "")
        )
    if not results and not dropped:
        log_mgr.log("猫抓推送：请求体里没有可用的媒体链接（请求体模板或 ${action} 可能填错了）", "warning")
    return {
        "ok": bool(results),
        "received": len(results),
        "dropped": dropped,
        "results": results,
    }


@app.get("/api/catcatch/status")
def api_catcatch_status():
    """界面用：接收端地址、要填进猫抓的请求体模板、已导入规则与最近接收统计。"""
    with _catcatch_lock:
        waiting = sum(
            1 for v in _catcatch_keys.values() if time.time() - float(v.get("ts") or 0) < _CATCATCH_KEY_TTL
        )
    return {
        "ok": True,
        "endpoint": f"http://127.0.0.1:{_catcatch_port()}/api/catcatch/push",
        "body_template": '{"action": "${action}", "data": ${data}, "tabId": "${tabId}"}',
        "rules": _load_catcatch_rules(),
        "stat": dict(_catcatch_stat),
        "keys_waiting": waiting,
    }


def _collect_regex_rules(node, _depth: int = 0) -> List[dict]:
    """在猫抓导出的配置 JSON 里递归找出带 regex 字段的规则对象，不猜它的存储键名。"""
    out: List[dict] = []
    if _depth > 6:
        return out
    if isinstance(node, str):
        s = node.strip()
        if s[:1] in ("{", "["):
            try:
                out.extend(_collect_regex_rules(json.loads(s), _depth + 1))
            except Exception:
                pass
        return out
    if isinstance(node, dict):
        rx = node.get("regex")
        # regex 的值必须是字符串才算一条规则：猫抓的规则数组本身就可能挂在这个键名下，
        # 只看「有没有这个键」会把整只容器当成一条规则，里面真正的规则反而一条都进不来。
        if isinstance(rx, str) and rx.strip():
            return [node]
        for v in node.values():
            out.extend(_collect_regex_rules(v, _depth + 1))
    elif isinstance(node, list):
        for v in node:
            out.extend(_collect_regex_rules(v, _depth + 1))
    return out


@app.post("/api/catcatch/import-config")
def api_catcatch_import_config(body: dict = None):
    """导入猫抓「设置 → 导入/导出配置」导出的 txt（全量配置 JSON）里的正则规则。"""
    body = body or {}
    text = str(body.get("text") or "")
    if not text.strip():
        raise HTTPException(400, "内容为空：请把猫抓导出的 cat-catch-版本-日期.txt 全文粘进来，或用下面的选文件")
    try:
        conf = json.loads(text)
    except Exception as e:
        raise HTTPException(400, f"这不是合法的 JSON（{e}）：请确认选的是猫抓自己导出的配置文件")
    found = _collect_regex_rules(conf)
    if not found:
        raise HTTPException(400, "这份配置里没有正则规则：先在猫抓「设置 → 正则规则」里加几条规则再导出")
    rules = _load_catcatch_rules()
    have = {(str(r.get("regex") or ""), bool(r.get("blacklist"))) for r in rules}
    added, dup, bad = 0, 0, []
    for r in found:
        pat = str(r.get("regex") or "").strip()
        black = bool(r.get("blackList") or r.get("blacklist"))
        try:
            re.compile(pat)
        except re.error as e:
            bad.append({"regex": pat[:80], "reason": str(e)})
            continue
        if (pat, black) in have:
            dup += 1
            continue
        have.add((pat, black))
        state = str(r.get("state", "1")).strip().lower()
        rules.append({
            "name": str(r.get("name") or "")[:60],
            "regex": pat,
            "ext": str(r.get("ext") or "").strip()[:16],
            "blacklist": black,
            "enabled": state not in ("0", "false", "off"),
            "source": "cat-catch",
        })
        added += 1
    _save_catcatch_rules(rules)
    log_mgr.log(
        f"导入猫抓配置：正则规则 {len(found)} 条 → 新增 {added}、重复跳过 {dup}、正则非法 {len(bad)}",
        k="srv.catcatch.rules_imported",
        kv={"found": len(found), "added": added, "dup": dup, "bad": len(bad)},
    )
    return {"ok": True, "found": len(found), "added": added, "duplicated": dup,
            "invalid": bad, "total": len(rules)}


def _catcatch_rule_update(body: dict, action: str) -> dict:
    body = body or {}
    try:
        idx = int(body.get("index"))
    except Exception:
        raise HTTPException(400, "缺少规则编号")
    rules = _load_catcatch_rules()
    if not 0 <= idx < len(rules):
        raise HTTPException(400, f"规则编号 {idx} 已失效，请刷新页面")
    if action == "delete":
        gone = rules.pop(idx)
        log_mgr.log(f"删除猫抓规则「{str(gone.get('name') or gone.get('regex'))[:60]}」",
                    k="srv.catcatch.rule_deleted",
                    kv={"rule": str(gone.get("name") or gone.get("regex"))[:60]})
    else:
        rules[idx]["enabled"] = not rules[idx].get("enabled", True)
    _save_catcatch_rules(rules)
    return {"ok": True, "rules": rules}


@app.post("/api/catcatch/rules/toggle")
def api_catcatch_rules_toggle(body: dict = None):
    return _catcatch_rule_update(body, "toggle")


@app.post("/api/catcatch/rules/delete")
def api_catcatch_rules_delete(body: dict = None):
    return _catcatch_rule_update(body, "delete")


@app.post("/api/catcatch/rules/clear")
def api_catcatch_rules_clear():
    n = len(_load_catcatch_rules())
    _save_catcatch_rules([])
    log_mgr.log(f"清空猫抓规则（原有 {n} 条）",
                k="srv.catcatch.rules_cleared", kv={"n": n})
    return {"ok": True, "rules": []}


LIBRARY_CACHE = APP_DIR / "library_cache.json"


def _ffprobe_bin() -> str:
    """返回 ffprobe 路径；空串表示本机没有 —— 校验时这意味着「没法判」，不是「文件坏了」。"""
    ff = ffmpeg_mgr.find()
    probe = str(Path(ff).with_name("ffprobe.exe" if sys.platform == "win32" else "ffprobe")) if ff else ""
    if probe and Path(probe).exists():
        return probe
    return shutil.which("ffprobe") or ""


def _ffprobe_info(path: Path) -> dict:
    probe = _ffprobe_bin()
    if not probe:
        return {}
    try:
        cmd = [
            probe, "-v", "quiet", "-print_format", "json",
            "-show_format", "-show_streams", str(path),
        ]
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30,
            encoding="utf-8", errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        if r.returncode != 0:
            return {}
        data = json.loads(r.stdout or "{}")
        duration = 0.0
        width = height = 0
        vcodec = acodec = ""
        try:
            duration = float((data.get("format") or {}).get("duration") or 0)
        except Exception:
            pass
        for s in data.get("streams") or []:
            disp = s.get("disposition") or {}
            ctype = s.get("codec_type")
            if ctype == "video" and not width and not disp.get("attached_pic"):
                width = int(s.get("width") or 0)
                height = int(s.get("height") or 0)
                vcodec = s.get("codec_name") or ""
            if ctype == "audio" and not acodec:
                acodec = s.get("codec_name") or ""
        return {
            "duration": duration,
            "width": width,
            "height": height,
            "vcodec": vcodec,
            "acodec": acodec,
            "size": path.stat().st_size,
            "format": (data.get("format") or {}).get("format_name") or path.suffix.lstrip("."),
        }
    except Exception:
        return {}


# 常见容器魔数（当前只用来认「这确实是个媒体容器」，认不出不判失败）
_MAGIC_CONTAINERS = (
    (b"\x1aE\xdf\xa3", "matroska/webm"),
    (b"RIFF", "avi/wav"),
    (b"OggS", "ogg"),
    (b"fLaC", "flac"),
    (b"ID3", "mp3"),
    (b"\xff\xfb", "mp3"),
    (b"\xff\xf3", "mp3"),
    (b"\xff\xf2", "mp3"),
    (b"FORM", "aiff"),
    (b"\x30\x26\xb2\x75", "asf/wmv"),
    (b"\x00\x00\x01\xba", "mpeg-ps"),
    (b"\x00\x00\x01\xb3", "mpeg"),
)


def _looks_like_html(head: bytes) -> bool:
    t = head[:600].decode("latin-1", "ignore").lstrip("\ufeff\x00\r\n\t ").lower()
    return t.startswith("<!doctype html") or t.startswith("<html") or t.startswith("<head") or "<head" in t[:300]


def sniff_media_format(path: Path) -> str:
    """看文件头猜容器，认不出返回空串。"""
    try:
        with Path(path).open("rb") as f:
            head = f.read(400)
    except OSError:
        return ""
    if head[4:8] == b"ftyp":
        return "mp4/mov"
    if head[:1] == b"G" and head[188:189] == b"G":
        return "mpeg-ts"
    for magic, name in _MAGIC_CONTAINERS:
        if head.startswith(magic):
            return name
    return ""


def verify_media_file(path) -> str:
    """下载结束后的体检：工具正常退出 ≠ 文件能播。返回空串表示通过，否则是一句能直接给人看的原因。

    宁可漏判也不误杀：没有 ffprobe、格式认不出、时长读不出，一律当通过。
    """
    p = Path(path)
    if not p.is_file():
        return "工具报告成功，但目标文件不存在"
    size = p.stat().st_size
    if size == 0:
        return "文件为 0 字节"
    if size < 1024:
        return f"文件只有 {size} 字节，不像一次完整下载"
    try:
        with p.open("rb") as f:
            head = f.read(4096)
    except OSError as e:
        return f"文件读不出来：{str(e)[:80]}"
    named = risk_control.describe_downloaded_bytes(head)
    if named:
        return named
    if _looks_like_html(head):
        return "内容其实是网页而不是媒体（多半是被站点拦下或缺少登录 Cookie）"
    probe = _ffprobe_bin()
    if not probe:
        return ""
    kind = sniff_media_format(p)
    try:
        r = subprocess.run(
            [probe, "-v", "error", "-show_format", "-show_streams", "-of", "json", str(p)],
            capture_output=True, text=True, timeout=60,
            encoding="utf-8", errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
    except Exception:
        return ""
    if r.returncode != 0:
        err = re.sub(r"\x1b\[[0-9;]*m", "", (r.stderr or "")).strip().replace("\n", " ")
        return ("文件无法解析，很可能不完整或已损坏"
                + (f"（文件头是 {kind}，容器没问题、数据被截断）" if kind else "")
                + (f"：{err[:120]}" if err else ""))
    try:
        data = json.loads(r.stdout or "{}")
    except Exception:
        return ""
    streams = data.get("streams") or []
    if not any(s.get("codec_type") in ("video", "audio") for s in streams):
        return "文件里没有任何音视频流"
    try:
        dur = float((data.get("format") or {}).get("duration") or 0)
    except Exception:
        dur = 0.0
    if 0 < dur < 0.5 and size > 2_000_000:
        return f"只有 {dur:.2f} 秒却有 {size // 1024 // 1024}MB，像是被截断的下载"
    return ""


def tier_readback(path, want_q, listed_max: int = 0, audio_only: bool = False) -> str:
    """成品回读：文件真实高度对一下用户选的档位，对不上就说清是谁的问题。返回空串=不用多说。

    为什么单独做这一步：在 10-13 之前，「成功」只代表进程退出码 0 加文件能播。
    那次 4K 静默降成 1080p 就是从这儿漏过去的 —— 卡片写着「成功」，谁也没看出
    实际下到的是清单末尾那条 1080p 渐进流。话术必须点名是谁的问题，
    只说「没到 4K」等于把上游不给和本地选错混成一句。
    """
    if audio_only:
        return ""
    want_h = quality_height_cap(want_q)
    if not want_h:
        return ""          # 选的是 best：没有上限可比，实得多少算多少
    try:
        got_h = int((_ffprobe_info(Path(path)) or {}).get("height") or 0) if path else 0
    except Exception:
        got_h = 0
    if not got_h:
        return ""          # 读不到高度（没 ffprobe、成品其实是音频）不瞎判
    # 编码按 16 对齐会多出一几十行（2176 / 1088 这类），差一点不算偏差，否则天天误报
    if abs(got_h - want_h) <= max(16, int(want_h * 0.05)):
        return ""
    listed = int(listed_max or 0)
    if got_h > want_h:
        return (f"所选 {want_q}，成品 {got_h}p：高度上限没拦住"
                "（自定义参数或站点只给这一条流的时候会这样，体积也比预期大）")
    if listed >= want_h:
        return (f"所选 {want_q}，成品只有 {got_h}p：清单里明明有 {listed}p，"
                "差在选择/合并这一段，不是上游不给")
    if listed > got_h:
        return (f"所选 {want_q}，成品 {got_h}p：上游清单最高只到 {listed}p，"
                f"而它比实得的还高一档，这一档没下满")
    if listed > 0:
        return f"所选 {want_q}，成品 {got_h}p：上游清单最高就到这儿，这一档它给不了"
    return f"所选 {want_q}，成品 {got_h}p：解析清单已过期，判不出上游给到哪儿"


# ---------- 成品校验值核对（期望 MD5/SHA 比对）----------
# 只认 hashlib 已有的这四个：界面那侧允许 sha256 / SHA-256 / SHA2-256 各种写法，
# 由 normalize_hash_algo 收成同一个名字，长度对不上就是「不是这个算法」。
_HASH_ALGOS = {"md5": 32, "sha1": 40, "sha256": 64, "sha512": 128}
_HASH_LABELS = {"md5": "MD5", "sha1": "SHA-1", "sha256": "SHA-256", "sha512": "SHA-512"}
# 站点页面和磁力参数常写成 sha-256=xxx / MD5: xxx，收进来先把这层前缀剥掉
_HASH_PREFIX_RE = re.compile(r"^(?:md5|sha[-_]?(?:1|2(?:[-_]?2)?(?:56|12)|512)|checksum|哈希|校验值|摘要)\s*[:=/]\s*", re.I)
# 只写 sha / sha2 这种半截名字时不猜：交给长度反推，猜错会得到一句假警报
_HASH_ALGO_MAP = {
    "md5": "md5",
    "sha1": "sha1",
    "sha256": "sha256", "sha2256": "sha256",
    "sha512": "sha512", "sha2512": "sha512",
}


def normalize_hash_algo(text) -> str:
    """SHA-256 / sha256 / sha2-256 → sha256；认不出或写 auto → 空串（按长度反推）。"""
    key = re.sub(r"[^0-9a-z]", "", str(text or "").lower())
    if not key or key == "auto":
        return ""
    return _HASH_ALGO_MAP.get(key, "")


def normalize_hash_expect(value, algo="auto") -> Tuple[str, str, str]:
    """界面/接口交来的期望校验值 → (小写 hex, 算法, 一句问题说明)。hex 为空 = 没让核对。

    算法可以明说，也可以由长度反推（32/40/64/128 各对应一家）。两边都给了却对不上时报错，
    不静默按其中一边算 —— 那是复制漏了字符最常见的样子，硬算只会得到一句「对不上」，
    把人往「下载坏了」那条路上带去。
    """
    raw = str(value or "").strip()
    if not raw:
        return "", "", ""
    raw = _HASH_PREFIX_RE.sub("", raw).strip()
    cleaned = re.sub(r"[\s;:\-]", "", raw).lower()
    if not cleaned:
        return "", "", "期望校验值是空的"
    if not re.fullmatch(r"[0-9a-f]+", cleaned):
        bad = next(ch for ch in cleaned if ch not in "0123456789abcdef")
        return "", "", (f"期望校验值里有不是十六进制的字符（「{bad}」，整串 {len(cleaned)} 位）："
                        "摘要只有 0-9 和 a-f，Base64 那种写法（sha256=xxxx= 这样）这里收不了，请先换成十六进制")
    by_len = {v: k for k, v in _HASH_ALGOS.items()}.get(len(cleaned), "")
    named = normalize_hash_algo(algo)
    if named and len(cleaned) != _HASH_ALGOS[named]:
        return "", "", (f"算法选了 {_HASH_LABELS[named]}，那串应该是 {_HASH_ALGOS[named]} 位十六进制字符，"
                        f"可这串只有 {len(cleaned)} 位：多半是复制的时候漏了头或尾"
                        + (f"，看着更像 {_HASH_LABELS[by_len]}" if by_len else ""))
        return "", "", (f"算法选了 {_HASH_LABELS[named]}（要 {_HASH_ALGOS[named]} 位），"
                        f"可这串是 {len(cleaned)} 位，更像 {_HASH_LABELS[by_len]}："
                        "要么算法点错了，要么复制的时候漏了字符")
    final = named or by_len
    if not final:
        return "", "", (f"认不出这串期望校验值：{len(cleaned)} 个十六进制字符，而 "
                        + "、".join(f"{_HASH_LABELS[a]} 是 {_HASH_ALGOS[a]} 位" for a in _HASH_ALGOS)
                        + "；请点明算法，或换成完整的一串")
    return cleaned, final, ""


def _hash_short(hexed: str) -> str:
    """摘要缩写给人看：头 8 尾 6，中间一个省略号。全长贴进界面会把卡片挤成一长条。"""
    h = str(hexed or "")
    if len(h) <= 16:
        return h
    return f"{h[:8]}…{h[-6:]}"


def hash_media_file(path, algo: str) -> str:
    """对成品算一次摘要（1MB 分块，几个 G 的片也不会整份读进内存）。读不出来返回空串。"""
    if algo not in _HASH_ALGOS:
        return ""
    try:
        h = hashlib.new(algo)
        with Path(path).open("rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
    except Exception:
        return ""
    return h.hexdigest()


def hash_rewrite_steps(cfg_like: dict, kind: str = "link") -> List[str]:
    """这一单下完还会不会有人改动成品字节 —— 决定期望校验值可不可比。

    这条链默认就会动字节：容器按所选档位无损 remux 一遍、封面/元数据/章节/字幕往轨道里塞、
    SponsorBlock 剪片头、按时间点选段，每一步都重写文件。所以拿发布方给的 MD5 去对
    站内解析下来的成品，对不上是应该的，不是下载坏了。磁力/种子是 aria2 原样落盘，不算重写。
    """
    if kind == "torrent":
        return []
    c = cfg_like or {}
    steps: List[str] = []
    fmt = str(c.get("format") or "").strip().lower()
    if fmt in ("mp3", "m4a", "flac", "wav", "opus", "aac", "ogg"):
        steps.append(f"抽成音频（{fmt}）")
    elif fmt in ("mp4", "mkv", "webm"):
        steps.append(f"封装成 {fmt}")
    if c.get("audio_only"):
        steps.append("仅下载音频")
    if c.get("embed_thumb"):
        steps.append("内嵌封面")
    if c.get("embed_meta"):
        steps.append("内嵌元数据")
    if c.get("embed_chapters"):
        steps.append("内嵌章节")
    if c.get("embed_sub"):
        steps.append("内嵌字幕")
    if str(c.get("sponsorblock") or "off").lower() != "off":
        steps.append("按 SponsorBlock 处理广告段")
    if str(c.get("download_section") or "").strip():
        steps.append("按时间点选段")
    if c.get("use_hls_engine"):
        steps.append("HLS 专用引擎合并")
    if c.get("local_ai_transcribe") or c.get("local_ai_translate"):
        steps.append("本地转写/翻译写字幕")
    return steps


def hash_readback(path, want_hex: str, algo: str, steps: List[str]) -> Tuple[str, str, str]:
    """成品摘要对一遍期望值 → (结论 ok/bad/unknown, 实算摘要, 那句要上屏的话)。

    一致时返回空串（不占卡片一行，只在运行日志留一句），
    对不上才说话，并且分两种说：本机刚重写过成品的，怪不到下载头上。
    """
    want = str(want_hex or "").lower()
    if not want or algo not in _HASH_ALGOS:
        return "", "", ""
    got = hash_media_file(path, algo)
    if not got:
        return ("unknown", "",
                f"想按 {_HASH_LABELS[algo]} 核对校验值，但成品读不出来（被移走或没有读权限），这一项没法判")
    label = _HASH_LABELS[algo]
    if got == want:
        return "ok", got, ""
    both = f"期望 {label} {_hash_short(want)}，成品实算 {_hash_short(got)}"
    if steps:
        return ("bad", got,
                f"校验值对不上：{both}。这一单下完在本机还过了「{'、'.join(steps)}」这几步，"
                "成品是被重写过一遍的文件，和上游那份原文件的摘要本来就不会相同 —— "
                "这一项要对磁力/种子或原样落盘的直链才有意义（或者先把这几步关掉再下）")
    return ("bad", got,
            f"校验值对不上：{both}：这份文件不是期望的那一支"
            "（上游给错、下载被截断、算法点错都算在这条里）；文件已保留，没删")


def scan_library(root=None) -> List[dict]:
    base = Path(root or cfg.data.get("download_dir") or DEFAULT_DOWNLOAD_DIR)
    if not base.is_dir():
        return []
    # 音频口径取 music_search 那份（下载链真会产出 flac/opus/ogg；这里少一个就扫不到成品）
    from music_search import MUSIC_AUDIO_EXTS, audio_file_meta
    audio_ext = {e for e in MUSIC_AUDIO_EXTS if e != ".webm"}   # webm 在本页按视频处理
    media_ext = {".mp4", ".mkv", ".webm", ".flv", ".ts", ".mov", ".avi"} | audio_ext
    items = []
    # 回收目录里的东西不算成品：那是按龄清理挪出去等真删的，媒体库继续列它就是幽灵行
    files = [p for p in base.rglob("*")
             if p.is_file() and p.suffix.lower() in media_ext and not p.name.startswith(".")
             and CL_TRASH_DIRNAME not in p.parts]
    files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    for p in files[:500]:
        try:
            st = p.stat()
        except Exception:
            continue
        is_audio = p.suffix.lower() in audio_ext
        ameta = audio_file_meta(str(p), log=log_mgr.log) if is_audio else {}
        meta = {} if (is_audio and ameta.get("duration_s")) else _ffprobe_info(p)
        try:
            rel = str(p.relative_to(base))
        except Exception:
            rel = p.name
        row = {
            "path": str(p),
            "name": p.name,
            "rel": rel,
            "size": st.st_size,
            "mtime": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            "ext": p.suffix.lower().lstrip("."),
            "duration": meta.get("duration") or ameta.get("duration_s") or 0,
            "width": meta.get("width") or 0,
            "height": meta.get("height") or 0,
            "vcodec": meta.get("vcodec") or "",
            "acodec": meta.get("acodec") or ameta.get("codec") or "",
            "kind": "audio" if is_audio else "video",
        }
        if is_audio:
            row.update({
                "title": ameta.get("title") or "",
                "artists": ameta.get("artists") or "",
                "album": ameta.get("album") or "",
                "bit_depth": ameta.get("bit_depth") or 0,
                "sample_rate": ameta.get("sample_rate") or 0,
                "channels": ameta.get("channels") or 0,
                "bitrate_kbps": ameta.get("bitrate_kbps") or 0,
                "lossless": bool(ameta.get("lossless")),
                "quality": ameta.get("quality") or "",
                "has_cover": bool(ameta.get("has_cover")),
            })
        items.append(row)
    try:
        LIBRARY_CACHE.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass
    return items


@app.get("/api/library")
def api_library(refresh: int = 0):
    if not refresh and LIBRARY_CACHE.exists():
        try:
            items = json.loads(LIBRARY_CACHE.read_text(encoding="utf-8"))
            return {"ok": True, "items": items, "cached": True}
        except Exception:
            pass
    items = scan_library()
    return {"ok": True, "items": items, "cached": False}


@app.post("/api/library/scan")
def api_library_scan():
    items = scan_library()
    return {"ok": True, "count": len(items), "items": items}


RSS_FILE = APP_DIR / "rss_feeds.json"


def _load_rss() -> list:
    if RSS_FILE.exists():
        try:
            return json.loads(RSS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def migrate_rss_to_subs() -> int:
    """旧 RSS 源并进「订阅」统一管理 → 搬走的条数。

    已见集合直接当追新游标用，搬家后不会把老条目当成新增再下一遍；
    旧文件改名保留，不删数据。
    """
    feeds = _load_rss()
    if not feeds:
        return 0
    moved = 0
    for f in feeds:
        url = str(f.get("url") or "")
        if not url:
            continue
        try:
            item = sub_mgr.add(url, str(f.get("title") or url), "", "rss")
        except Exception as e:
            log_mgr.log(f"RSS 源「{f.get('title') or url}」并入订阅失败：{e}", "warning")
            continue
        with sub_mgr._lock:
            s = next((x for x in sub_mgr.subs if x.get("id") == item.get("id")), None)
            if s is not None:
                s["last_ids"] = list(f.get("seen_ids") or [])[:300]
                s["last_check"] = str(f.get("last_scan") or "")
                s["auto_download"] = bool(f.get("auto_download"))
        sub_mgr.save()
        moved += 1
    try:
        RSS_FILE.rename(RSS_FILE.with_name(RSS_FILE.name + ".migrated"))
    except Exception as e:
        log_mgr.log(f"RSS 旧文件改名失败（订阅已并入 {moved} 源，可手动删 {RSS_FILE.name}）：{e}", "warning",
                    k="srv.rss.migrate_rename_failed",
                    kv={"moved": moved, "file": RSS_FILE.name, "e": str(e)})
    if moved:
        log_mgr.log(f"RSS 订阅搬家：{moved} 个源已并入「订阅」页统一管理，已见记录一并带过去不会重复下载",
                    k="srv.rss.migrate_done", kv={"moved": moved})
    return moved


def parse_rss_feed(feed_url: str, proxy: str = "") -> dict:
    headers = {"User-Agent": "MediaDownloaderRSS/1.0"}
    proxies = http_proxies(feed_url, proxy)
    r = requests.get(feed_url, headers=headers, proxies=proxies, timeout=20, verify=False)
    r.raise_for_status()
    text = r.text
    import xml.etree.ElementTree as ET
    root = ET.fromstring(text)

    def local(tag):
        return tag.split("}")[-1] if tag else ""

    channel_title = feed_url
    entries = []
    if local(root.tag) == "rss" or root.find("channel") is not None:
        ch = root.find("channel") if local(root.tag) == "rss" else root
        if ch is None:
            ch = root
        t = ch.find("title")
        if t is not None and t.text:
            channel_title = t.text.strip()
        for item in ch.findall("item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            guid = (item.findtext("guid") or link or title).strip()
            pub = (item.findtext("pubDate") or "").strip()
            enclosure = ""
            enc = item.find("enclosure")
            if enc is not None:
                enclosure = enc.get("url") or ""
            if not enclosure:
                for c in item:
                    if local(c.tag) in ("content", "group"):
                        u = c.get("url") or ""
                        if u:
                            enclosure = u
                            break
            entries.append({
                "id": guid,
                "title": title,
                "link": link,
                "published": pub,
                "enclosure": enclosure,
            })
    else:
        for c in root:
            if local(c.tag) == "title" and c.text:
                channel_title = c.text.strip()
        for entry in root:
            if local(entry.tag) != "entry":
                continue
            title = link = guid = pub = enclosure = ""
            for c in entry:
                ln = local(c.tag)
                if ln == "title" and c.text:
                    title = c.text.strip()
                elif ln == "id" and c.text:
                    guid = c.text.strip()
                elif ln == "link":
                    href = c.get("href") or ""
                    rel = c.get("rel") or "alternate"
                    typ = c.get("type") or ""
                    if rel == "enclosure" or typ.startswith("audio") or typ.startswith("video"):
                        enclosure = href
                    elif not link:
                        link = href
                elif ln in ("updated", "published") and c.text:
                    pub = c.text.strip()
            entries.append({
                "id": guid or link or title,
                "title": title,
                "link": link,
                "published": pub,
                "enclosure": enclosure,
            })
    return {"title": channel_title, "entries": entries}


TRANSCODE_PRESETS = {
    "mp4": {
        "label": "转 MP4（重编码 + AAC，编码器见设置）",
        "args": ["-c:v", "libx264", "-preset", "fast", "-crf", "23", "-c:a", "aac", "-b:a", "192k"],
        "ext": ".mp4",
    },
    "mp4_1080": {
        "label": "转 MP4 并限制 1080p",
        "args": ["-vf", "scale=-2:1080", "-c:v", "libx264", "-preset", "fast", "-crf", "23", "-c:a", "aac", "-b:a", "192k"],
        "ext": ".mp4",
    },
    "audio_mp3": {
        "label": "抽取音频 MP3",
        "args": ["-vn", "-c:a", "libmp3lame", "-q:a", "2"],
        "ext": ".mp3",
    },
    "audio_m4a": {
        "label": "抽取音频 M4A",
        "args": ["-vn", "-c:a", "aac", "-b:a", "192k"],
        "ext": ".m4a",
    },
    "mkv_copy": {
        "label": "封装为 MKV (无重编码)",
        "args": ["-c", "copy"],
        "ext": ".mkv",
    },
    "flv_to_mp4": {
        "label": "FLV/TS -> MP4 (优先 copy)",
        "args": ["-c", "copy", "-bsf:a", "aac_adtstoasc"],
        "ext": ".mp4",
    },
}


@app.get("/api/transcode/presets")
def api_transcode_presets():
    return {
        "presets": [
            {"id": k, "label": v["label"], "ext": v["ext"]}
            for k, v in TRANSCODE_PRESETS.items()
        ]
    }


@app.get("/api/video/encoders")
def api_video_encoders(refresh: bool = False):
    """本机每个候选编码器起不起得来、起不来为什么，以及按当前设置排出来的降级链。"""
    return _video_encoders_payload(bool(refresh))


class TranscodeBody(BaseModel):
    path: str
    preset: str = "mp4"
    delete_source: bool = False


def _run_transcode(src_path: str, preset_id: str, delete_source: bool = False):
    """按预设转码一个文件，返回 (是否成功, 成品路径, 错误文字)。
    界面按钮和直播录完的自动转码都走这里，免得两条路的口径不一样。

    预设里写死的那串 libx264 会换成设置里排出来的编码器链，一个不行换下一个；
    `-c copy` 和抽音频那几条预设不重编视频，原样走，不受这项设置影响。
    """
    src = Path(src_path)
    if not src.is_file():
        return False, "", "文件不存在: " + str(src)
    preset = TRANSCODE_PRESETS.get(preset_id) or TRANSCODE_PRESETS["mp4"]
    ff = ffmpeg_mgr.find(ffmpeg_mgr.manual_path)
    if not ff:
        return False, "", "未找到 FFmpeg"
    out = src.with_suffix(preset["ext"])
    if out.resolve() == src.resolve():
        out = src.with_name(src.stem + "_out" + preset["ext"])
    base = list(preset["args"])

    def _attempt(args: List[str], mult: float = 1.0) -> tuple:
        cmd = [ff, "-y", "-i", str(src)] + list(args) + [str(out)]
        budget = int(3600 * max(1.0, float(mult)))
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=budget,
                               encoding="utf-8", errors="replace",
                               creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
        except subprocess.TimeoutExpired:
            out.unlink(missing_ok=True)
            return False, f"转码跑了 {budget} 秒被掐断（编码器太慢可以把档位调快）"
        if r.returncode == 0 and out.is_file():
            return True, ""
        # 半成品不留：换编码器是从头编一遍，留着上一次的残件只会让人误判
        out.unlink(missing_ok=True)
        return False, (r.stderr or r.stdout or "")[-500:]

    def _with_encoder(enc: dict) -> List[str]:
        # copy 失败要重编时按 mp4 预设那套参数走（音频也重编成 AAC），只换视频编码器那一段
        return _swap_encoder(list(TRANSCODE_PRESETS["mp4"]["args"]), enc["args"])

    try:
        if _preset_needs_encoder(base):
            chain = _video_encode_chain(23)
            log_mgr.log(f"开始转码: {src.name}（{preset['label']} · 用 {chain[0]['label']}）")
            err, done = "", False
            for idx, enc in enumerate(chain):
                ok, err = _attempt(_swap_encoder(base, enc["args"]), enc["timeout_mult"])
                if ok:
                    done = True
                    if idx:
                        log_mgr.log(f"转码改用了 {enc['label']}: {out.name}")
                    break
                rest = chain[idx + 1:]
                if rest:
                    why1 = " ".join((err or "").split())[-140:]
                    log_mgr.log(f"转码用 {enc['label']} 没成（{why1}），换 {rest[0]['label']} 重来", "warning")
            if not done:
                return False, "", "转码失败: " + (err or "")[-300:]
        else:
            ok, err = _attempt(base)
            if not ok and preset_id == "flv_to_mp4":
                # copy 失败说明流本身不合规格，退回重编码再试一次（编码器同样听设置的）
                chain = _video_encode_chain(23)
                for enc in chain:
                    ok, err = _attempt(_with_encoder(enc), enc["timeout_mult"])
                    if ok:
                        break
            if not ok:
                return False, "", "转码失败: " + (err or "")[-300:]
        if delete_source and out.is_file() and src.resolve() != out.resolve():
            try:
                src.unlink()
            except Exception:
                pass
        return True, str(out), ""
    except Exception as e:
        return False, "", str(e)


@app.post("/api/transcode")
def api_transcode(body: TranscodeBody):
    if not Path(body.path).is_file():
        raise HTTPException(400, "文件不存在")
    ok, out, err = _run_transcode(body.path, body.preset, body.delete_source)
    if not ok:
        if err == "文件不存在":
            raise HTTPException(400, err)
        if err.startswith("未找到"):
            raise HTTPException(400, err)
        raise HTTPException(500, err)
    log_mgr.log(f"转码完成: {Path(out).name}",
                k="srv.transcode.done", kv={"name": Path(out).name})
    return {"ok": True, "path": out, "name": Path(out).name}



# -------------------- 插件 / aria2 / 命名队列 API --------------------
# GET /api/plugins 在上方「文件与目录」段已注册（返回 list_url_plugins()，含 description / priority）


@app.post("/api/plugins/test")
def api_plugins_test(body: dict):
    url = (body.get("url") or "").strip()
    if not url:
        raise HTTPException(400, "缺少 url")
    result = try_resolve_with_plugins(
        url, {"proxy": proxy_arg(url), "log": log_mgr.log}
    )
    return {"ok": True, "resolved": result}


@app.get("/api/aria2/status")
def api_aria2_status():
    """直链加速和磁力/种子都问这里：RPC 通不通、aria2c 在哪、是不是程序自己拉起来的。"""
    rpc = cfg.data.get("aria2_rpc") or "http://127.0.0.1:6800/jsonrpc"
    out = {"ok": True, "enabled": bool(cfg.data.get("aria2_enabled")),
           "online": False, "rpc": rpc}
    try:
        out["online"] = bool(_bt_client(dict(cfg.data)).ping())
    except Exception as e:
        out["error"] = str(e)
    try:
        import aria2_daemon
        out["binary"] = aria2_daemon.find_binary(str(cfg.data.get("aria2_bin") or ""), APP_DIR, is_native_binary)
        out["daemon"] = aria2_daemon.owned()
    except Exception as e:
        out["binary_error"] = str(e)
    out["autostart"] = bool(cfg.data.get("aria2_autostart", True))
    if not out["online"] and out["autostart"]:
        # 「检测 aria2」点了就该把该拉起的人拉起来；拉不动时把原因带回去，
        # 界面才不至于只说一句「RPC 无应答」却不知道下一步做什么
        ok_ensure, why_ensure = bt_ensure(dict(cfg.data), lambda m, level="info": log_mgr.log(m, level))
        out["ensure"] = {"ok": bool(ok_ensure), "why": str(why_ensure or "")}
        if ok_ensure:
            out["online"] = True
            # 拉起之后重读一次归属：不然是「刚刚明明是我们起的，界面却说不是本程序启的」
            try:
                import aria2_daemon
                out["daemon"] = aria2_daemon.owned()
            except Exception:
                pass
    with _BT_WATCH_LOCK:
        out["seeding"] = len(_BT_WATCH)
    return out


class TorrentSelectBody(BaseModel):
    task_id: str
    indices: List[int]  # aria2 的文件序号，从 1 起


class TorrentStopBody(BaseModel):
    ids: List[str] = []   # 任务 ID
    gids: List[str] = []  # aria2 任务号：程序没管过的那些（重启前就在做种）只有这个
    all: bool = False     # 界面按「全部停止做种」时才传 true


def _torrent_store_dir() -> Path:
    # 上传的种子与 aria2 会话同属本机数据，放在整目录排除打包的 torrent_state 下
    d = Path(APP_DIR) / "torrent_state" / "uploads"
    d.mkdir(parents=True, exist_ok=True)
    return d


@app.post("/api/torrent/upload")
async def api_torrent_upload(file: UploadFile = File(...)):
    """收一个本地 .torrent：存下来并回一条能直接入队的 file:// 链接。

    文件名按内容哈希，同一个种子重复上传会落回同一个路径，去重那条逻辑才认得出是同一份内容。
    """
    name = Path(str(file.filename or "")).name
    if not name.lower().endswith(".torrent"):
        raise HTTPException(400, "只接受 .torrent 种子文件")
    data = await file.read()
    if not data:
        raise HTTPException(400, "种子文件是空的")
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(400, f"种子文件 {len(data) // 1024} KB，超过 10 MB 上限，不太像正常种子")
    if not data.startswith(b"d8:"):
        raise HTTPException(400, "这个文件的开头不是种子格式（bencode），可能改了后缀名")
    ident = torrent_bytes_identity(data)
    safe = safe_filename_component(name[:-8], 60)
    store = _torrent_store_dir()
    dest = store / f"{safe}.torrent"
    # 同名但内容不同的两个种子不能互相覆盖，否则先前那条任务的种子就被换了
    if dest.exists() and torrent_file_identity(str(dest)) != ident:
        dest = store / f"{safe}-{ident[:6]}.torrent"
    try:
        dest.write_bytes(data)
    except OSError as e:
        raise HTTPException(500, f"种子存不下来：{type(e).__name__}: {str(e)[:120]}")
    url = dest.as_uri()
    log_mgr.log(f"[界面] 收到种子文件 {name} → {dest.name}")
    return {"ok": True, "url": url, "path": str(dest), "name": dest.stem, "size": len(data)}


@app.post("/api/torrent/select")
def api_torrent_select(body: TorrentSelectBody):
    """改选种子里要下的文件：序号从 1 起，全不选就拒绝（aria2 会当成「全都要」）。"""
    t = queue.tasks.get(body.task_id or "")
    if not t or not t.gid:
        raise HTTPException(404, "这个任务还没有交给 aria2（还没拿到种子元数据），改不了文件选择")
    idx = sorted({int(i) for i in (body.indices or []) if int(i) > 0})
    if not idx:
        raise HTTPException(400, "至少要选一个文件")
    if t.status not in (TaskStatus.QUEUED.value, TaskStatus.DOWNLOADING.value, TaskStatus.PAUSED.value):
        raise HTTPException(400, f"任务已经是「{t.status}」，这时候改选文件没有意义")
    ac = _bt_client(dict(cfg.data))
    # aria2 认的是 select-file="1,3"（序号列表本身）；写成 select-file=true + index=… 会被当场拒绝
    ok = ac.change_option(t.gid, {"select-file": ",".join(str(i) for i in idx)})
    if not ok:
        raise HTTPException(500, "aria2 没有接受这次改选（RPC 无应答或任务已不在）")
    try:
        t.files = bt_file_list(ac.get_files(t.gid))
        # aria2 改选要下一秒才反映到 getFiles 的 selected 上，紧跟着读会看到旧值；
        # 这次改选已经被 aria2 接受，清单就按点名的那几个写，界面别回一个反的
        want = set(idx)
        for f in t.files:
            f["selected"] = f["index"] in want
    except Exception as e:
        log_mgr.log(f"改选后读文件清单失败：{e}", "warning")
    log_mgr.log(f"[界面] 任务 {t.id[:8]} 改选 {len(idx)} 个文件")
    return {"ok": True, "files": t.files, "count": len(idx)}


@app.get("/api/torrent/seeding")
def api_torrent_seeding():
    """正在做种的清单。以 aria2 的记录为准：列表里删掉任务行会连上传一起停，「清除已完成」不会。

    名字取种子里的 info.name（实测做种中的任务 tellStatus 就带 bittorrent），
    速率、peer 数、tracker 数一律当场问 aria2——本程序管的和不是本程序起的那一栏口径要一样。
    """
    with _BT_WATCH_LOCK:
        items = list(_BT_WATCH.items())
    live = {}
    note = ""
    ac = _bt_client(dict(cfg.data))
    if not ac.ping():
        # 页面一打开就轮询这里。RPC 没人应答时先把「自动拉起」这条路走一遍，
        # 拉不动才把原因写出来 —— 否则界面上永远是一行 urllib 的原文
        ok_ensure, why_ensure = bt_ensure(dict(cfg.data), lambda m, level="info": log_mgr.log(m, level))
        if not ok_ensure:
            note = "读 aria2 活动任务失败：" + str(why_ensure or "")
    if not note:
        try:
            for st in ac.tell_active(["gid", "status", "totalLength", "completedLength", "uploadLength",
                                      "uploadSpeed", "seedingTime", "numSeeders", "numPeers", "bittorrent"]):
                gid = str(st.get("gid") or "")
                if gid:
                    live[gid] = st
        except Exception as e:
            note = f"读 aria2 活动任务失败：{aria2_err_cn(e, dict(cfg.data))}"

    def _row_fields(st: dict) -> dict:
        """把 aria2 的一条任务读数摊成界面要的字段。

        只写这次真读到的：aria2 少了哪个键就留空，别拿 0 顶上去——0 会被界面当成「没 peer」。
        """
        bt = st.get("bittorrent") or {}
        got = {"torrent_name": str(((bt.get("info") or {}).get("name")) or ""),
               "aria2_status": str(st.get("status") or "")}
        if bt.get("announceList") is not None:
            got["tracker_count"] = len(bt["announceList"])
        if st.get("completedLength") is not None:
            up = int(st.get("uploadLength") or 0)
            dl = max(1, int(st.get("completedLength") or 0))
            got.update({"uploaded": up, "share_ratio": round(up / dl, 3)})
        for key, name in (("uploadSpeed", "upload_speed"), ("numPeers", "num_peers"),
                          ("numSeeders", "num_seeders")):
            if st.get(key) is not None:
                got[name] = str(st.get(key))
        if st.get("seedingTime") is not None:
            try:
                got["seed_seconds"] = int(float(st.get("seedingTime") or 0))
            except (TypeError, ValueError):
                pass
        return got

    out = []
    for gid, w in items:
        t = queue.tasks.get(w.get("task_id") or "")
        row = {"gid": gid, "task_id": w.get("task_id") or "", "name": w.get("name") or "",
               "managed": True, "seed_ratio_want": w.get("ratio"), "seed_time_want": w.get("seconds")}
        if t:
            row.update({"title": t.title, "uploaded": t.uploaded, "share_ratio": round(t.share_ratio, 3),
                        "seed_seconds": t.seed_seconds, "status": t.status})
        st = live.get(gid)
        if st:
            got = _row_fields(st)
            row.update({k: v for k, v in got.items() if k != "torrent_name"})
            if got["torrent_name"]:
                row["name"] = got["torrent_name"]   # 种子给的名字比「挑出来的那个文件」更能代表整份内容
            row["in_queue"] = True
        else:
            # 不在活动队列不等于没了：被暂停的做种任务 aria2 就是不列进 tellActive（实测）。
            # 补一次 tellStatus 才分得清是暂停、已结束还是出错；读不到就留空，不写 0 假装量过
            row.update({"in_queue": False})
            try:
                st2 = ac.tell_status(gid, ["status", "totalLength", "completedLength", "uploadLength",
                                           "seedingTime", "uploadSpeed", "numSeeders", "numPeers",
                                           "bittorrent"])
            except Exception:
                st2 = {}
            if st2.get("status"):
                got = _row_fields(st2)
                row.update({k: v for k, v in got.items() if k != "torrent_name"})
                if got["torrent_name"]:
                    row["name"] = got["torrent_name"]
        out.append(row)
    # 也列出 aria2 里我们没管过的做种任务（比如程序重启前就挂在 aria2 上的），否则界面看不见就停不掉
    known = {str(r["gid"]) for r in out}
    for gid, st in live.items():
        if gid in known or not st.get("bittorrent"):
            continue
        row = {"gid": gid, "task_id": "", "managed": False, "in_queue": True}
        row.update(_row_fields(st))
        name = row.get("torrent_name") or ""
        if not name:
            try:
                fl = bt_file_list(ac.get_files(gid))
                name = Path(str(fl[0].get("path") or "")).name if fl else ""
            except Exception:
                name = ""
        row["name"] = name or str((st.get("bittorrent") or {}).get("infoHash") or gid)[:16]
        row["title"] = row["name"] if name else "（不是这个程序起的做种）"
        out.append(row)
    return {"ok": True, "items": out, "count": len(out), "note": note}


def _task_by_gid(gid: str) -> Optional[DownloadTask]:
    for t in queue.tasks.values():
        if t.gid and t.gid == gid:
            return t
    return None


@app.post("/api/torrent/stop-seed")
def api_torrent_stop_seed(body: TorrentStopBody):
    """停做种（已经下好的文件不动）。范围靠 ids（任务）或 gids（aria2 任务号）点名，all=true 才全停。"""
    ids = {i for i in (body.ids or []) if i}
    gids = {g for g in (body.gids or []) if g}
    with _BT_WATCH_LOCK:
        picked = set(gids)
        for gid, w in _BT_WATCH.items():
            if body.all or w.get("task_id") in ids:
                picked.add(gid)
    if body.all:
        # 看护表只记这个程序管过的；aria2 里还挂着别的一些（比如上次运行留下的、或元数据下完后另起一段的）
        # 「全部停止做种」如果只管登记表里的，界面列得出来却停不掉
        try:
            ac0 = _bt_client(dict(cfg.data))
            for st in ac0.tell_active(["gid", "status", "totalLength", "completedLength", "bittorrent"]):
                gid = str(st.get("gid") or "")
                total = int(st.get("totalLength") or 0)
                done = int(st.get("completedLength") or 0)
                if gid and st.get("bittorrent") and total and done >= total:
                    picked.add(gid)
        except Exception as e:
            log_mgr.log(f"停做种前列 aria2 活动任务失败：{e}", "warning")
    if not picked:
        return {"ok": True, "stopped": 0, "message": "没有点到在做种的任务"}
    ac = _bt_client(dict(cfg.data))
    n = 0
    for gid in sorted(picked):
        try:
            ac.remove(gid)
        except Exception as e:
            log_mgr.log(f"停止做种失败（{gid[:10]}）：{e}", "warning")
            continue
        with _BT_WATCH_LOCK:
            w = _BT_WATCH.pop(gid, None) or {}
        t = queue.tasks.get(w.get("task_id") or "") or _task_by_gid(gid)
        if t:
            t.seeding = False
            # 停完还挂着「一直做种（要停就在…）」就成了假话，这行跟着改口
            t.resume_hint = "做种已手动停止，已下载的文件不动"
        n += 1
        log_mgr.log(f"[界面] 手动停止做种：{(t.title if t else w.get('name')) or gid[:10]}")
    return {"ok": True, "stopped": n, "message": f"已停止 {n} 个做种任务"}


class BtLimitBody(BaseModel):
    task_id: str = ""
    gid: str = ""
    download: Optional[str] = None   # 写成 1M / 512K；"0" 或空字符串 = 取消限速
    upload: Optional[str] = None


def _bt_speed_arg(field: str, raw) -> str:
    """把界面传来的限速收成 aria2 认的写法；"0" 是「取消限速」，别的形状不对就当场顶回去。"""
    s = str(raw or "").strip().upper()
    if s in ("", "0"):
        return "0"
    got = bt_trackers.norm_speed(s)
    if not got:
        raise HTTPException(400, f"{field} 要写成 1M / 512K / 纯字节数（0=不限），现在收到的是「{s[:24]}」")
    return got


@app.get("/api/bt/trackers")
def api_bt_trackers():
    """现在会注入给新任务的 tracker：来源抓到多少、手动填了哪几条、最终生效几条。这一步不联网。"""
    c = dict(cfg.data)
    st = bt_trackers.status(c, APP_DIR)
    got, note = bt_trackers.effective(c, APP_DIR)  # 不给 getter：只吃已缓存的，读接口不能顺手联网
    return {"ok": True, "sources": st["sources"], "cache_time": st["cache_time"],
            "manual": st["manual"], "effective": got, "count": len(got), "note": note,
            "max": int(c.get("bt_tracker_max") or 0),
            "auto_update": bool(c.get("bt_tracker_auto_update", True))}


@app.post("/api/bt/trackers/refresh")
def api_bt_trackers_refresh():
    """立刻去抓一遍来源。哪个来源没抓到就点名说哪个，不能回一个空列表当作「更新完成」。"""
    c = dict(cfg.data)
    urls = bt_trackers.sources_to_urls(c.get("bt_tracker_sources") or "")
    if not urls:
        raise HTTPException(400, "来源地址是空的：先在设置里填一行一个的列表网址")
    data = bt_trackers.refresh(APP_DIR, urls, lambda u: http_get_bytes(u, timeout=20))
    srcs = data.get("sources") or {}
    bad = [(u, (v or {}).get("error") or "") for u, v in srcs.items() if not (v or {}).get("ok")]
    got, note = bt_trackers.effective(c, APP_DIR)
    log_mgr.log(f"[界面] 更新 tracker 列表：来源抓到 {len(urls) - len(bad)}/{len(urls)} 个，"
                f"现在一共 {len(got)} 条" + (f"（{note}）" if note else ""))
    return {"ok": not bad, "count": len(got), "sources": len(urls),
            "failed": [{"url": u, "error": e} for u, e in bad], "note": note,
            "time": data.get("time") or "",
            "message": (f"抓到 {len(got)} 条 tracker，下一个新任务就会带上" if got
                        else "一条都没抓到：看看来源地址能否访问，或先手动填几条")}


@app.post("/api/bt/limit")
def api_bt_limit(body: BtLimitBody):
    """改某个任务的上传/下载限速。

    aria2 这两条是真能免重启改的（实测下载中和正在做种的都改得动，改完 getOption 就是新值），
    但它的回话不能信：同一套 API 对改不动的键照样回 OK。所以这里改完必须读回，界面上写的是读回来的值。
    """
    t = queue.tasks.get(body.task_id or "")
    gid = (t.gid if t and t.gid else (body.gid or "")).strip()
    if not gid:
        raise HTTPException(404, "这个任务还没有交给 aria2（没有任务号），改不了限速")
    opts = {}
    if body.download is not None:
        opts["max-download-limit"] = _bt_speed_arg("下载限速", body.download)
    if body.upload is not None:
        opts["max-upload-limit"] = _bt_speed_arg("上传限速", body.upload)
    if not opts:
        raise HTTPException(400, "要改哪一路？下载限速或上传限速至少给一个（0=不限）")
    ac = _bt_client(dict(cfg.data))
    ok, why = ac.change_option_detail(gid, opts)
    if not ok:
        # 实测两种拒绝分得开：还在 aria2 但已离开下载队列（complete/error/removed）回
        # 「Cannot change option for GID#…」，任务号整个没了才回「GID … is not found」。
        # 光甩原文用户看不出为什么改不动，所以先读回 aria2 那边的状态再说话。
        st = ""
        try:
            st = str((ac.tell_status(gid, ["status"]) or {}).get("status") or "")
        except Exception:
            pass
        if "not found" in (why or "").lower():
            extra = "这个任务号已经不在 aria2 里了（程序或 aria2 重启过、任务被删掉）"
        elif st:
            extra = (f"它在 aria2 里现在是「{st}」，已经移出活动队列——"
                     "实测只有还在下载、排队、暂停或正在做种的任务能改限速")
        else:
            extra = "aria2 读不到这个任务的状态"
        raise HTTPException(500, f"aria2 没有接受这次改限速：{extra}。原话：{why}")
    back = ac.get_option(gid)
    actual = {k: str(back.get(k, "")) for k in opts}
    # aria2 读回来的限速一律是字节数（发 1M 回 1048576），所以要比字节而不是比字符串
    if any(k not in back or bt_trackers.to_bytes(actual[k]) != bt_trackers.to_bytes(v)
           for k, v in opts.items()):
        # 回了 OK 却没改值：这种情况只能报实际值，不能对用户说改好了
        return {"ok": False, "gid": gid, "wanted": opts, "actual": actual,
                "message": "aria2 回了 OK，但读回来的值和要改的不一样："
                           + "、".join(f"{k} 现在是 {actual[k] or '读不到'}" for k in opts)}
    if t:
        t.resume_hint = ((t.resume_hint or "") + "｜限速 下%s 上%s" % (
            opts.get("max-download-limit") or "不变", opts.get("max-upload-limit") or "不变"))[:120]
    log_mgr.log(f"[界面] 任务 {gid[:10]} 限速改为："
                + "、".join(f"{k}={v}" for k, v in opts.items()))
    return {"ok": True, "gid": gid, "actual": actual,
            "message": "限速已生效（下 %s / 上 %s）" % (
                opts.get("max-download-limit") or "不变", opts.get("max-upload-limit") or "不变")}



class BtRuleTestBody(BaseModel):
    """试跑自动分类：给名字、给一条磁力/种子链接，或给一条普通下载链接。"""
    name: str = ""
    url: str = ""


@app.post("/api/torrent/rules/test")
def api_torrent_rules_test(body: BtRuleTestBody):
    """照现在存着的规则试一遍「会命中哪条、存到哪个目录」。不建任务、不改设置。

    自动分类是批量生效的：一条规则写歪，之后所有撞上它的种子都落到别处，事后翻目录才发现就晚了。
    所以这里给界面一个当场验证的入口，并且把「用的是哪个名字、名字从哪来」一并回出去——
    磁力在元数据到手前根本没有名字可比，这点必须让用户看见，而不是给个空结果让人猜。

    普通下载链接（http/https）也收：这一类只有「链接规则」问得到，回话里会写明它走的是哪一档，
    以及为什么它不吃「都不命中时存到」那个兜底目录。
    """
    c = dict(cfg.data)
    rules = [r for r in (c.get("bt_auto_rules") or []) if isinstance(r, dict)]
    base = str(c.get("download_dir") or DEFAULT_DOWNLOAD_DIR)
    url = str(body.url or "").strip()
    nm = str(body.name or "").strip()
    probe_url = ""
    ref = None
    kind = "name"          # name = 只给了个名字；bt = 磁力/种子；url = 普通下载链接
    if url:
        ref = parse_torrent_ref(url)
        if ref:
            name, whence = bt_rule_name(ref, log_mgr.log)
            probe_url = url          # 磁力/种子：先问名字规则，没中再问链接规则
            kind = "bt"
        elif url.lower().startswith(("http://", "https://")):
            name, whence = "", "普通下载链接（这一类没有种子名可比，只问链接规则）"
            probe_url = url
            kind = "url"
        else:
            raise HTTPException(400, "这条既不是磁力（magnet:）、本机 .torrent，也不是 http(s) 链接")
    elif nm:
        name, whence = nm, "界面现填的名字"
    else:
        raise HTTPException(400, "要试什么？写一个种子名字，或贴一条磁力 / 种子 / 普通下载链接")
    is_bt = kind == "bt"
    if not rules:
        return {"ok": True, "matched": None, "name": name, "name_from": whence, "dir": base,
                "message": "还没配规则：任何任务都先存到默认下载目录"}
    hit, why = _rule_decide(name, probe_url, rules)
    if hit:
        sub = str(hit.get("subdir") or "")
        target = str(Path(base) / sub) if sub else base
        return {"ok": True, "matched": hit, "why": why, "name": name, "name_from": whence,
                "dir": target,
                "message": (f"会存到 {target}" if sub
                            else f"{why}，但这条规则没填子目录 → 仍存默认目录 {base}")}
    fb, _fb_bad = bt_rule_subdir(c.get("bt_auto_fallback"))
    has_url_rules = any(str(r.get("scope") or "name") == "url" for r in rules)
    asked = "名字与链接的规则" if (has_url_rules and is_bt) else (
        "链接规则" if kind == "url" else "名字规则")
    if is_bt and not name:
        tail = f"兜到 {Path(base) / fb}" if fb else "仍存默认目录"
        return {"ok": True, "matched": None, "name": "", "name_from": whence,
                "dir": str(Path(base) / fb) if fb else base,
                "message": f"这条现在还没有可比的名字（{whence}），{asked}都没命中 → {tail}"}
    if kind == "url":
        return {"ok": True, "matched": None, "name": name, "name_from": whence, "dir": base,
                "message": "链接规则一条都没命中 → 存默认目录（「都不命中时存到」那个兜底只管磁力 / 种子）"}
    if fb:
        return {"ok": True, "matched": None, "name": name, "name_from": whence,
                "dir": str(Path(base) / fb),
                "message": f"{asked}都没命中 → 按兜底目录存到 {Path(base) / fb}"}
    return {"ok": True, "matched": None, "name": name, "name_from": whence, "dir": base,
            "message": f"{asked}都没命中，也没配兜底目录 → 存默认目录"}


@app.get("/api/clipboard")
def api_clipboard_status():
    """界面每 2 秒问一次：开关开没开、有没有刚发现还没处理的链接。

    读到的链接只在这里经 loopback 交给本机浏览器，不写日志、不落任何状态文件；
    开关关着时连待定内容都不交出（默认关必须是真关，不是只停线程）。
    """
    enabled = bool(cfg.data.get("clipboard_watch"))
    with _clip_lock:
        pend = dict(_clip_state["pending"]) if (_clip_state["pending"] and enabled) else None
        info = {"checks": _clip_state["checks"], "hits": _clip_state["hits"],
                "error": _clip_state["error"] if enabled else "",
                "supported": sys.platform == "win32", "since": _clip_state["since"]}
    return {"ok": True, "enabled": enabled, "pending": pend, "poll_sec": CLIP_POLL_SEC, **info}


@app.post("/api/clipboard/clear")
def api_clipboard_clear():
    """用户已经表过态（加入或忽略），这一条就翻篇；不看内容、也不留记录。

    「加入」也只是把链接填回输入框，之后要不要解析、要不要入队仍然归用户按。
    """
    with _clip_lock:
        _clip_state["pending"] = None
    return {"ok": True}


@app.get("/api/queues")
def api_named_queues():
    names = list(cfg.data.get("named_queues") or ["default", "night", "subscribe", "sniff"])
    counts = {n: 0 for n in names}
    for t in queue.tasks.values():
        qn = t.queue_name or "default"
        counts[qn] = counts.get(qn, 0) + 1
    return {"ok": True, "queues": names, "counts": counts}


@app.post("/api/queues/set")
def api_set_task_queue(body: dict):
    ids = body.get("ids") or []
    name = (body.get("queue_name") or "default").strip() or "default"
    for tid in ids:
        t = queue.tasks.get(tid)
        if t:
            t.queue_name = name
    return {"ok": True}


# -------------------- SSE 实时推送 --------------------
# 思路：不去改每一处进度回调，而是后台线程按固定节拍做「快照 + 签名比对」，
# 只有界面会变形的字段变了才推一帧。丢帧无所谓：下一帧就是最新状态，前端还留着轮询兜底。

SSE_TICK_SEC = 0.6
SSE_PROG_STATUSES = ("downloading",)
# progress/speed/eta/elapsed 秒秒在跳，若把它们算进结构签名，state 每拍都要重发整张表
SSE_VOLATILE_KEYS = ("progress", "speed", "eta", "elapsed_sec")


class SSEHub:
    def __init__(self, maxsize: int = 8):
        self._clients: List[ThreadQueue] = []
        self._lock = threading.Lock()
        self._maxsize = maxsize
        self.dropped = 0

    def subscribe(self) -> ThreadQueue:
        q = ThreadQueue(maxsize=self._maxsize)
        with self._lock:
            self._clients.append(q)
        return q

    def unsubscribe(self, q) -> None:
        with self._lock:
            try:
                self._clients.remove(q)
            except ValueError:
                pass

    def clients(self) -> int:
        with self._lock:
            return len(self._clients)

    def publish(self, topic: str, payload) -> None:
        if not topic:
            return
        item = (topic, payload)
        with self._lock:
            targets = list(self._clients)
        for q in targets:
            try:
                q.put_nowait(item)
            except QueueFull:
                self.dropped += 1  # 客户端太慢：丢这帧，下帧补上
            except Exception:
                pass


SSE_HUB = SSEHub()


def _sse_pack(topic: str, payload) -> str:
    return f"event: {topic}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _sse_state() -> dict:
    return {
        "tasks": queue.list_tasks(sort_by="queue"),
        "running": queue.running,
        "paused": bool(queue.paused),
        "pending": len(queue.pending),
        "throttle": HOST_THROTTLE.snapshot(),
        "window": queue.window_status(),
    }


def _sse_state_sig(state: dict) -> str:
    """结构签名：任务增删、改名、换队列、变状态才算变；进度交给 prog 主题。
    throttle 的剩余秒数每拍都在掉，所以只带不签。定时窗同理只签「开没开、压了几条」，
    还有几分钟到点这种事界面自己按 resume_at 倒数，不必为此每推一帧整张任务表。"""
    slim = [{k: v for k, v in t.items() if k not in SSE_VOLATILE_KEYS} for t in state["tasks"]]
    w = state.get("window") or {}
    wkey = {
        "open": w.get("open"),
        "resume_at": w.get("resume_at"),
        "held": w.get("held"),
        "queues": [{"name": q.get("name"), "open": q.get("open"), "held": q.get("held")}
                   for q in (w.get("queues") or [])],
    }
    return json.dumps(
        {"t": slim, "r": state["running"], "p": state["paused"], "n": state["pending"], "w": wkey},
        ensure_ascii=False,
        sort_keys=True,
    )


def _sse_prog() -> dict:
    rows = {}
    for t in queue.tasks.values():
        if t.status in SSE_PROG_STATUSES:
            row = {
                "progress": t.progress,
                "speed": t.speed,
                "eta": t.eta,
                "elapsed_sec": _sse_elapsed(t),
            }
            # 卡片上的清晰度/大小/封面只在这些字段有值时才进包，避免推送签名无谓变化
            if t.res_label:
                row["res_label"] = t.res_label
            if t.total_bytes:
                row["total_bytes"] = t.total_bytes
                row["done_bytes"] = t.done_bytes
            if t.thumbnail:
                row["thumbnail"] = t.thumbnail
            rows[t.id] = row
    return {"rows": rows, "running": queue.running, "pending": len(queue.pending)}


def _sse_elapsed(t) -> int:
    if not t.started_at:
        return 0
    try:
        t0 = datetime.fromisoformat(t.started_at)
        return max(0, int((datetime.now() - t0).total_seconds()))
    except Exception:
        return 0


def _sse_logs_after(cursor: int):
    with log_mgr._lock:
        fresh = [e for e in log_mgr.entries if int(e.get("seq") or 0) > cursor]
    return fresh[:200]


def _sse_hardsub() -> list:
    with HARDSUB_LOCK:
        return [{k: v for k, v in j.items() if k != "proc"} for j in HARDSUB_JOBS.values()]


def _sse_loop():
    state_sig = prog_sig = hard_sig = ""
    log_cursor = 0
    while True:
        try:
            if SSE_HUB.clients() == 0:
                time.sleep(1.0)
                continue
            st = _sse_state()
            sig = _sse_state_sig(st)
            if sig != state_sig:
                state_sig = sig
                SSE_HUB.publish("state", st)

            pr = _sse_prog()
            psig = json.dumps(pr, ensure_ascii=False, sort_keys=True)
            if psig != prog_sig:
                prog_sig = psig
                SSE_HUB.publish("prog", pr)

            fresh = _sse_logs_after(log_cursor)
            if fresh:
                log_cursor = max(int(e.get("seq") or 0) for e in fresh)
                SSE_HUB.publish("logs", fresh)

            hs = _sse_hardsub()
            hsig = json.dumps(hs, ensure_ascii=False, sort_keys=True)
            if hsig != hard_sig:
                hard_sig = hsig
                SSE_HUB.publish("hardsub", hs)
        except Exception as e:
            try:
                log_mgr.log(f"SSE 广播异常: {e}", "warning")
            except Exception:
                pass
        time.sleep(SSE_TICK_SEC)


_sse_thread: Optional[threading.Thread] = None
_sse_start_lock = threading.Lock()
# main() 起服务前把 uvicorn.Server 放这儿：收到退出信号后 should_exit 立刻变 True，
# SSE 生成器看见就主动收流。拖着不收的话 uvicorn 要等满 timeout_graceful_shutdown
# 再 cancel，控制台会打出 CancelledError 堆栈 —— 看着像崩溃，其实只是关闭阶段的噪声。
_UVICORN_SERVER = None


def start_sse_broadcaster():
    global _sse_thread
    with _sse_start_lock:
        if _sse_thread and _sse_thread.is_alive():
            return _sse_thread
        _sse_thread = threading.Thread(target=_sse_loop, daemon=True, name="sse-broadcaster")
        _sse_thread.start()
        return _sse_thread


@app.get("/api/events")
async def api_events(request: Request):
    """任务队列 / 日志 / 硬字幕进度的服务端推送。EventSource 断开后会自动重连。"""
    start_sse_broadcaster()
    q = SSE_HUB.subscribe()

    async def gen():
        idle = 0.0
        try:
            yield _sse_pack("hello", {"ok": True, "tick_sec": SSE_TICK_SEC, "ts": time.time()})
            yield _sse_pack("state", _sse_state())
            while True:
                if _UVICORN_SERVER is not None and _UVICORN_SERVER.should_exit:
                    break
                if await request.is_disconnected():
                    break
                sent = 0
                while sent < 20:
                    try:
                        topic, payload = q.get_nowait()
                    except QueueEmpty:
                        break
                    sent += 1
                    yield _sse_pack(topic, payload)
                if sent:
                    idle = 0.0
                    continue
                await asyncio.sleep(0.2)
                idle += 0.2
                if idle >= 5.0:  # 反代/浏览器会掐空闲连接，靠注释行续命
                    idle = 0.0
                    yield ": ping\n\n"
        finally:
            SSE_HUB.unsubscribe(q)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@app.get("/api/events/stats")
def api_events_stats():
    return {"ok": True, "clients": SSE_HUB.clients(), "dropped": SSE_HUB.dropped, "tick_sec": SSE_TICK_SEC}


def _probe_host(host: str) -> str:
    """预检之后要拿哪个地址去问 /api/health：绑 0.0.0.0 / :: 时那个地址不能当客户端目标。"""
    h = str(host or "").strip()
    return "127.0.0.1" if h in ("", "0.0.0.0", "::", "*", "::ffff") else h


def port_taken(host: str, port: int) -> bool:
    """启动前先自己试绑一次。撞端口时 uvicorn 抛的是 Errno 10048，那行很容易被人看成「卡住了」
       —— 这台程序启动成功后控制台本来就只有横幅四行，不再打任何字。"""
    import socket
    fam = socket.AF_INET6 if ":" in str(host or "") else socket.AF_INET
    s = socket.socket(fam, socket.SOCK_STREAM)
    try:
        s.bind((host, int(port)))
        return False
    except OSError as e:
        # 只认「地址被占」；别的错（地址写错之类）留给 uvicorn 自己报，别在这里替它下结论
        return getattr(e, "errno", None) in (errno.EADDRINUSE, 10048)
    finally:
        s.close()


def port_taken_by_us(host: str, port: int, timeout_s: float = 1.5) -> bool:
    """占着这个端口的是不是本程序另一台：只有 /api/health 答 {ok:true} 才算。
       认这一条是因为「已经开着一台，再开第二台」是最常见的撞车，那种情况该劝人用原来那台，
       而不是让人去关一个他找不到的程序。/api/health 只读内存里的队列计数，不会顺手跑 ffmpeg。"""
    try:
        with requests.get("http://%s:%d/api/health" % (_probe_host(host), int(port)),
                          timeout=timeout_s) as r:
            return bool(r.ok) and bool(r.json().get("ok"))
    except Exception:
        return False


def _boot_ready_announcer(host: str, port: int) -> None:
    """服务真答话了再打「已就绪」那一行：横幅在 uvicorn 绑定之前就打了，光看它不知道端口起来了没有。"""
    def _run():
        t0 = time.time()
        while time.time() - t0 < 60:
            if port_taken_by_us(host, port, timeout_s=1.0):
                print("  服务已就绪：http://%s:%d 现在能访问了（这个窗口保持开着；Ctrl+C 停止）"
                      % (_probe_host(host), int(port)), flush=True)
                return
            time.sleep(0.3)
        # 60 秒还没答话：多半是端口没起来（上面已经拦过一道），这里不再补一句，免得和真错误信息打架

    threading.Thread(target=_run, daemon=True).start()


def main():
    import uvicorn

    global _UVICORN_SERVER

    host = os.environ.get("MEDIADOWNLOADER_HOST") or "127.0.0.1"
    try:
        port = int(os.environ.get("MEDIADOWNLOADER_PORT") or 8765)
    except ValueError:
        port = 8765
    if port_taken(host, port):
        by_us = port_taken_by_us(host, port)
        tip = ("  这台机器上已经开着一个多媒体下载器：http://%s:%d 就是它，直接用那一个就行。"
               % (_probe_host(host), port)) if by_us else \
              ("  端口 %d 被别的程序占着（占它的不是本程序，它没答 /api/health）。" % port)
        print("=" * 50)
        print("  多媒体下载器 Web 版 (Element Plus) —— 没能启动")
        print(tip)
        print("  要让这一台也起来：设环境变量 MEDIADOWNLOADER_PORT 换个端口再启动。")
        print("=" * 50)
        log_mgr.log("端口 %d 已被占用，本次启动退出（%s）"
                    % (port, "同一台机器上已有一个实例在跑" if by_us else "被别的程序占着"), "warning")
        raise SystemExit(1)

    # 启动时按配置放宽 SSL（解决 bytefcdn 等 Hostname mismatch）
    if cfg.data.get("nocheckcertificate", True) is not False:
        try:
            import ssl as _ssl
            _ssl._create_default_https_context = _ssl._create_unverified_context
            log_mgr.log("已关闭全局 SSL 证书校验（nocheckcertificate）")
        except Exception:
            pass

    start_live_monitor_scheduler()
    start_telegram_command_poller()
    start_notify_outbox()
    start_clipboard_watch()
    start_cleanup_scheduler()
    try:
        migrate_rss_to_subs()
    except Exception as e:
        log_mgr.log(f"RSS 源并入订阅失败: {e}", "warning")
    # 启动时加载监控；若仍在直播且无进行中任务，自动开录
    def _boot_live_monitors():
        try:
            time.sleep(2)  # 等服务与队列就绪
            items = _load_live_monitors()
            log_mgr.log(f"已加载直播监控 {len(items)} 个房间，开始检测开播…",
                        k="srv.live.boot_loaded", kv={"n": len(items)})
            if items:
                r = api_live_monitor_scan()
                log_mgr.log(f"启动扫描完成，新开录制 {r.get('started', 0)} 路",
                            k="srv.live.boot_scan_done", kv={"started": r.get("started", 0)})
        except Exception as e:
            log_mgr.log(f"启动时刷新直播监控失败: {e}", "warning",
                        k="srv.live.boot_failed", kv={"e": str(e)})

    threading.Thread(target=_boot_live_monitors, daemon=True).start()

    # 打开程序就查一遍组件上游版本：查一次要两三秒，放后台线程，界面只读结果
    def _boot_component_check():
        try:
            time.sleep(3)  # 等接口与配置就绪，别把查询压在启动路径上
            if not cfg.data.get("components_auto_check"):
                return
            _comp_check_start()
        except Exception as e:
            log_mgr.log(f"启动时自动检测组件更新失败: {e}", "warning")

    threading.Thread(target=_boot_component_check, daemon=True).start()

    # PO Token 服务端就在 tools/ 里，门控开着却没人在听时由程序补拉一次。
    # 放后台线程：node 起来要一两秒，不该压在启动路径上；拉不起来也只是那行状态变灰，不影响别的功能
    def _boot_pot_server():
        try:
            time.sleep(2)
            if not cfg.data.get("po_provider_enabled"):
                return
            po_token_health(force=True)
        except Exception as e:
            log_mgr.log(f"启动时拉起 PO Token 服务端失败: {e}", "warning")

    threading.Thread(target=_boot_pot_server, daemon=True).start()
    log_mgr.log(f"Web 服务启动 | FFmpeg={ffmpeg_mgr.version()} | yt-dlp={engine.check_ytdlp()}")
    print("=" * 50)
    print("  多媒体下载器 Web 版 (Element Plus)")
    print(f"  打开浏览器访问: http://{host}:{port}")
    print("=" * 50)
    # 横幅之后 uvicorn 那句「Uvicorn running on」是 INFO，被下面的 log_level="warning" 压掉了，
    # 所以健康启动的控制台到这四行就没字了 —— 看着跟卡住一模一样。补一句真答过话的为准
    _boot_ready_announcer(host, port)
    # 自己持有 uvicorn.Server（而不是 uvicorn.run）是为了把 should_exit 交给 SSE 流看，
    # shutdown 时生成器主动收流，就不会再走「等满 timeout_graceful_shutdown 再 cancel」那条路。
    # timeout_graceful_shutdown 本身仍是容器/服务化的必需项：没有它 docker stop 会等满超时被 SIGKILL，
    # 下面 finally 里的 BT 守护收尾根本轮不到执行。
    _UVICORN_SERVER = uvicorn.Server(uvicorn.Config(
        app, host=host, port=port, log_level="warning", timeout_graceful_shutdown=5))
    try:
        _UVICORN_SERVER.run()
    except KeyboardInterrupt:
        pass  # uvicorn.run 原本也吞这一下：capture_signals 收尾会把信号重放出来
    finally:
        _bt_daemon_stop()
    if not _UVICORN_SERVER.started:  # 与 uvicorn.run 的启动失败退出码保持一致
        raise SystemExit(3)


if __name__ == "__main__":
    main()
