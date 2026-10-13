"""磁力/种子的 Tracker 列表：只存来源地址，列表正文一律运行时抓取，绝不打进发布包。

参照 qBittorrent-Enhanced-Edition 的做法——它同样不把 tracker 正文写死在源码里，
而是运行时从公开维护的列表更新。这些列表本身是 GPL 许可的产物，内嵌进我们的包会
连带把许可问题带进来；所以这里只保留 URL 与维护者署名（CREDITS.md 鸣谢），
抓回来的正文只落在本机 torrent_state/ 下（打包时整目录排除）。
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Sequence, Tuple

# 默认来源：公开维护、纯文本一行一个 announce URI
DEFAULT_SOURCES = [
    {"url": "https://raw.githubusercontent.com/ngosang/trackerslist/master/trackers_all.txt",
     "label": "ngosang/trackerslist"},
    {"url": "https://raw.githubusercontent.com/XIU2/TrackersListCollection/master/all.txt",
     "label": "XIU2/TrackersListCollection"},
]

_ANNOUNCE = re.compile(r"^https?://[^\s/,/?#]+(?::\d+)?(?:/[^\s]*)?$", re.I)
_SPEED = re.compile(r"^\d+(\.\d+)?([KMGB])?$", re.I)


def is_announce(uri: str) -> bool:
    """只收 http/https 的 announce 地址：带空格、带凭据、非这两类的一律不要（会拖垮整轮 announce）。"""
    u = str(uri or "").strip()
    if not u or " " in u or "@" in u or len(u) > 300:
        return False
    return bool(_ANNOUNCE.match(u))


def _as_text(text) -> str:
    """抓回来的列表是字节（http_get_bytes 的返回），不先解码就会变成 "b'http://...'" 那种字面量。

    这一步不能省：实测直接喂 bytes 时 parse_list 一条都认不出来，整份 tracker 清单会静默变空。
    """
    if isinstance(text, (bytes, bytearray, memoryview)):
        return bytes(text).decode("utf-8", "replace")
    return str(text or "")


def parse_list(text) -> List[str]:
    """把一行一个（或逗号分隔）的列表文本读成 URI 清单：注释行、空行、非法项丢掉。"""
    out: List[str] = []
    for chunk in _as_text(text).replace(";", "\n").splitlines():
        line = chunk.strip()
        if not line or line.startswith("#"):
            continue
        for part in line.split(","):
            u = part.strip()
            if is_announce(u):
                out.append(u)
    return out


def sources_to_urls(text) -> List[str]:
    """设置里的来源文本 → 干净的 http(s) URL 清单（一行一个，丢掉非 URL 的行）。"""
    out = []
    for line in _as_text(text).splitlines():
        u = line.strip()
        if u and not u.startswith("#") and u.lower().startswith(("http://", "https://")) and " " not in u:
            if u not in out:
                out.append(u)
    return out


def merge_lists(groups: Sequence[Sequence[str]], cap: int) -> List[str]:
    """按组顺序去重合并，凑满 cap 条就停：手动填的要排在抓来的前面。"""
    out: List[str] = []
    seen = set()
    for g in groups:
        for u in g:
            if u in seen:
                continue
            seen.add(u)
            out.append(u)
            if cap and len(out) >= cap:
                return out
    return out


def norm_speed(value) -> str:
    """限速值原样交给 aria2（它认 1M / 512K / 纯字节数）；只把明显不合法的挡掉。"""
    s = str(value or "").strip().upper()
    if not s or s in ("0", "0M", "0K"):
        return ""
    if not _SPEED.match(s):
        return ""
    return s


def to_bytes(value) -> int:
    """把限速值换算成字节数——比对「改成功了没」必须走这一步。

    实测：给 aria2 的 max-download-limit=1M，getOption 读回来是 1048576；改 512K 读回 524288。
    两边不换成同一单位就永远判成「没改成功」，界面就会谎报失败。空/0 都算 0（不限速）。
    """
    s = _as_text(value).strip().upper()
    if not s:
        return 0
    m = re.match(r"^(\d+(?:\.\d+)?)([KMGB])?$", s)
    if not m:
        return -1  # 形状不对，交给调用方判
    return int(float(m.group(1)) * {"K": 1024, "M": 1024 ** 2, "G": 1024 ** 3}.get(m.group(2) or "", 1))


def cache_path(app_dir) -> Path:
    return Path(app_dir) / "torrent_state" / "trackers_cache.json"


def load_cache(app_dir) -> dict:
    p = cache_path(app_dir)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_cache(app_dir, data: dict) -> bool:
    """落盘失败不算错：抓到的列表还在内存里，下次照样能写。"""
    p = cache_path(app_dir)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        return True
    except Exception:
        return False


def fetch_sources(urls: Sequence[str], getter: Callable[[str], bytes], timeout: int = 20) -> dict:
    """逐个来源抓正文。一个来源挂了不影响别的，但失败原因要留住——界面得说清是哪儿没抓到。"""
    res = {}
    for u in urls:
        try:
            res[u] = {"ok": True, "trackers": parse_list(getter(u)), "error": ""}
        except Exception as e:
            res[u] = {"ok": False, "trackers": [], "error": f"{type(e).__name__}: {str(e)[:160]}"}
    return res


def refresh(app_dir, source_urls: Sequence[str], getter: Callable[[str], bytes],
            timeout: int = 20) -> dict:
    """抓一遍并写缓存；整个表按来源存，方便回看每个来源贡献了多少条。"""
    data = {"time": datetime.now().isoformat(timespec="seconds"),
            "sources": fetch_sources(source_urls, getter, timeout)}
    save_cache(app_dir, data)
    return data


def effective(cfg: dict, app_dir, getter: Callable[[str], bytes] = None,
             log: Callable = lambda *a, **k: None) -> Tuple[List[str], str]:
    """这一趟要用的 tracker 清单 = 手动填的 + 缓存里抓来的，按 bt_tracker_max 截断。

    开了自动更新且给了抓取函数时，这里才真的联网；没网或抓不动就用上一次缓存的，
    并把原因写进 note——不能悄悄少注入或者假装更新过。
    """
    manual = parse_list(cfg.get("bt_trackers"))
    cap = int(cfg.get("bt_tracker_max") or 0)
    urls = sources_to_urls(cfg.get("bt_tracker_sources") or "")
    cache = load_cache(app_dir)
    srcs = cache.get("sources") or {}
    note = ""
    if getter is not None and urls and cfg.get("bt_tracker_auto_update", True):
        stale = [u for u in urls if not (srcs.get(u) or {}).get("ok")]
        if stale or not cache:
            fresh = refresh(app_dir, urls, getter)
            if fresh != cache:
                cache = fresh
                srcs = cache.get("sources") or {}
    elif not cache and urls and getter is None:
        note = "没有取列表的函数，只能用手动填的那几条"
    fetched: List[str] = []
    bad: List[str] = []
    for u in urls:
        one = srcs.get(u) or {}
        if one.get("ok"):
            fetched.extend(str(x) for x in (one.get("trackers") or []))
        else:
            bad.append(u)
    got = merge_lists([manual, fetched], cap)
    if not got:
        note = "一条 tracker 都没有：填手动列表，或者检查来源地址能不能访问"
    elif bad:
        note = f"{len(bad)} 个来源这次没抓到（先用抓到的 {len(got)} 条顶上）"
    if cap and len(manual) + len(fetched) > cap:
        note = (note + f"；超出上限，只取前 {cap} 条" if note else f"按上限只取前 {cap} 条")
    return got, note


def status(cfg: dict, app_dir) -> dict:
    """给界面看的来源与缓存概况：不联网，只把已经抓到的东西摊开。"""
    urls = sources_to_urls(cfg.get("bt_tracker_sources") or "")
    cache = load_cache(app_dir)
    srcs = cache.get("sources") or {}
    rows = []
    for u in urls:
        one = srcs.get(u) or {}
        rows.append({"url": u,
                     "label": next((s["label"] for s in DEFAULT_SOURCES if s["url"] == u), ""),
                     "fetched": bool(one), "ok": bool(one.get("ok")),
                     "count": len(one.get("trackers") or []), "error": one.get("error") or ""})
    return {"sources": rows, "cache_time": cache.get("time") or "",
            "manual": parse_list(cfg.get("bt_trackers"))}
