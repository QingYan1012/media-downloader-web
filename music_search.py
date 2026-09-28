"""
musicdl 2.x 完整适配层 — 对齐官方 MusicClient API。

覆盖能力:
  - 多平台并行搜索 MusicClient.search(keyword)
  - 按源下载 MusicClient.download(song_infos)
  - 歌单解析 MusicClient.parseplaylist(url)
  - 每源 work_dir / cookies / search_size / proxy / threading
  - 列出 REGISTERED_MODULES
  - 内存缓存 SongInfo，下载时精确命中（避免仅靠歌名重搜）

回退: yt-dlp ytsearch / scsearch
"""
from __future__ import annotations

import json
import inspect
import subprocess
import sys
import threading
import time
import traceback
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

# 官方默认源
DEFAULT_SOURCES = [
    "MiguMusicClient",
    "NeteaseMusicClient",
    "QQMusicClient",
    "AppleMusicClient",
    "SpotifyMusicClient",
]

# 常用扩展源（可在 UI 勾选）
EXTRA_CN_SOURCES = [
    "KugouMusicClient",
    "BilibiliMusicClient",
    "BodianMusicClient",
    "FiveSingMusicClient",
    "SodaMusicClient",
    "StreetVoiceMusicClient",
    "MOOVMusicClient",
]

GLOBAL_SOURCES = [
    "YouTubeMusicClient",
    "SoundCloudMusicClient",
    "SpotifyMusicClient",
    "AppleMusicClient",
    "DeezerMusicClient",
    "QobuzMusicClient",
    "TIDALMusicClient",
    "JamendoMusicClient",
    "AudiusMusicClient",
    "FMAMusicClient",
    "JooxMusicClient",
    "JioSaavnMusicClient",
    "CCMixterMusicClient",
    "SunoMusicClient",
]

RADIO_SOURCES = [
    "XimalayaMusicClient",
    "LizhiMusicClient",
    "QingtingMusicClient",
    "LRTSMusicClient",
]

# 界面固定可选源（含国际/有声，重启不丢）
_UI_SOURCE_BASE = (
    list(DEFAULT_SOURCES)
    + list(EXTRA_CN_SOURCES)
    + ["YouTubeMusicClient", "SoundCloudMusicClient", "SpotifyMusicClient", "AppleMusicClient", "XimalayaMusicClient"]
)



# 多源并行策略默认值（可被 API / 配置覆盖）
PARALLEL_STRATEGY_DEFAULT = {
    "mode": "parallel",          # parallel | sequential
    "search_size": 12,           # 每源条数
    "max_retries": 3,
    "connect_timeout": 10,
    "read_timeout": 30,
    "threads_per_source": 5,     # 单源内部线程
    "order": "as_is",            # as_is | cn_first | global_first
    "dedupe": "global",          # off | source | global
    "per_source_budget": 300,    # 单源搜索的墙钟上限（秒），0=不限
    # Spotify 这类只列曲名的条目，下载时按曲名去哪些源取地址。默认值同下面的
    # TRACK_MATCH_SOURCES（取址快而稳的那批），全部源都可选，界面上可见可改。
    "match_sources": ["NeteaseMusicClient", "QQMusicClient", "MiguMusicClient",
                      "KugouMusicClient", "KuwoMusicClient"],
}


CN_SOURCE_HINTS = ("Migu", "Netease", "QQ", "Kuwo", "Qianqian", "Kugou", "Bilibili", "Ximalaya", "FiveSing", "Bodian")
GLOBAL_SOURCE_HINTS = ("YouTube", "SoundCloud", "Spotify", "Apple", "Deezer", "TIDAL", "Qobuz", "Jamendo")

SOURCE_PRESETS = {
    "default": list(DEFAULT_SOURCES),
    "cn": ["MiguMusicClient","NeteaseMusicClient","QQMusicClient","KuwoMusicClient","QianqianMusicClient"] + list(EXTRA_CN_SOURCES),
    "global": list(GLOBAL_SOURCES),
    "radio": list(RADIO_SOURCES),
    "all_common": list(DEFAULT_SOURCES) + list(EXTRA_CN_SOURCES) + ["YouTubeMusicClient", "SoundCloudMusicClient"],
}

# 界面可选源 = 基础候选 ∪ 各预设里出现过的源。少一个就会出现「预设说选了、界面上却没有对应复选框」。
UI_SOURCE_OPTIONS: List[str] = []
for _s in _UI_SOURCE_BASE + [x for v in SOURCE_PRESETS.values() for x in v]:
    if _s not in UI_SOURCE_OPTIONS:
        UI_SOURCE_OPTIONS.append(_s)
del _s

# SongInfo 会话缓存: id -> SongInfo 对象
_SONG_CACHE: Dict[str, Any] = {}
_LAST_SEARCH_STATS: Dict[str, int] = {}
# 上一次搜索的诊断信息：{budget, elapsed, errors:{源: 人话原因}}
_LAST_SEARCH_DIAG: Dict[str, Any] = {}
_CACHE_LOCK = threading.Lock()
_MAX_CACHE = 500


def musicdl_available() -> bool:
    try:
        from musicdl import musicdl
        return hasattr(musicdl, "MusicClient")
    except Exception:
        return False


def list_registered_sources() -> List[str]:
    try:
        from musicdl.modules import MusicClientBuilder
        keys = list(MusicClientBuilder.REGISTERED_MODULES.keys())
        return sorted(keys)
    except Exception:
        return list(DEFAULT_SOURCES) + list(EXTRA_CN_SOURCES) + list(GLOBAL_SOURCES)


def normalize_source_name(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return s
    if s.endswith("MusicClient") or s.endswith("Client"):
        return s
    mapping = {
        "netease": "NeteaseMusicClient", "qq": "QQMusicClient", "qqmusic": "QQMusicClient",
        "kugou": "KugouMusicClient", "kuwo": "KuwoMusicClient", "migu": "MiguMusicClient",
        "qianqian": "QianqianMusicClient", "bilibili": "BilibiliMusicClient",
        "youtube": "YouTubeMusicClient", "soundcloud": "SoundCloudMusicClient",
        "spotify": "SpotifyMusicClient", "apple": "AppleMusicClient",
        "ximalaya": "XimalayaMusicClient", "lizhi": "LizhiMusicClient",
        "soda": "SodaMusicClient", "joox": "JooxMusicClient",
        "qobuz": "QobuzMusicClient", "tidal": "TIDALMusicClient",
        "deezer": "DeezerMusicClient", "audius": "AudiusMusicClient",
        "fivesing": "FiveSingMusicClient", "bodian": "BodianMusicClient",
    }
    low = s.lower().replace(" ", "").replace("音乐", "")
    if low in mapping:
        return mapping[low]
    return s[0].upper() + s[1:] + "MusicClient"


def canonical_sources(raws) -> List[str]:
    """先归一化再去重：['Spotify','SpotifyMusicClient'] 是同一个源，
    不去重就会让 musicdl 把同一个平台搜两遍（耗时翻倍、结果全是重复）。"""
    out: List[str] = []
    seen = set()
    for s in raws or []:
        n = normalize_source_name(str(s or ""))
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out


def _merge_strategy(strategy: Optional[dict] = None) -> dict:
    out = dict(PARALLEL_STRATEGY_DEFAULT)
    if strategy:
        for k, v in strategy.items():
            if v is not None and k in out:
                out[k] = v
    # 类型规范化
    out["search_size"] = max(1, min(40, int(out.get("search_size") or 12)))
    out["max_retries"] = max(0, min(5, int(out.get("max_retries") or 3)))
    out["connect_timeout"] = max(3, min(60, int(out.get("connect_timeout") or 10)))
    out["read_timeout"] = max(5, min(120, int(out.get("read_timeout") or 30)))
    out["threads_per_source"] = max(1, min(16, int(out.get("threads_per_source") or 5)))
    try:
        out["per_source_budget"] = max(0, min(1800, int(out.get("per_source_budget") or 0)))
    except (TypeError, ValueError):
        out["per_source_budget"] = int(PARALLEL_STRATEGY_DEFAULT["per_source_budget"])
    mode = str(out.get("mode") or "parallel").lower()
    out["mode"] = mode if mode in ("parallel", "sequential") else "parallel"
    order = str(out.get("order") or "as_is").lower()
    out["order"] = order if order in ("as_is", "cn_first", "global_first") else "as_is"
    dedupe = str(out.get("dedupe") or "global").lower()
    out["dedupe"] = dedupe if dedupe in ("off", "source", "global") else "global"
    ms = out.get("match_sources")
    out["match_sources"] = canonical_sources(ms) if isinstance(ms, (list, tuple)) else []
    return out


def _order_sources(srcs: List[str], order: str) -> List[str]:
    if order == "as_is" or not srcs:
        return list(srcs)
    def is_cn(s: str) -> bool:
        return any(h in s for h in CN_SOURCE_HINTS)
    def is_global(s: str) -> bool:
        return any(h in s for h in GLOBAL_SOURCE_HINTS)
    cn = [s for s in srcs if is_cn(s)]
    gl = [s for s in srcs if is_global(s) and s not in cn]
    other = [s for s in srcs if s not in cn and s not in gl]
    if order == "cn_first":
        return cn + other + gl
    if order == "global_first":
        return gl + other + cn
    return list(srcs)




SIDE_CAR_EXTS = (".lrc", ".jpg", ".jpeg", ".png", ".webp", ".gif", ".txt", ".cue", ".nfo")


def _same_file(a: Any, b: Any) -> bool:
    """两个路径指的是不是同一个文件。

    归档里三处「删掉重复的那一份」都必须先问过它：源与目标撞成同一个文件时
    （成品本来就在目标目录里），按字符串判重会删掉自己 —— 返回值照样非空，
    上层只当这一首成功了。
    """
    import os
    try:
        pa, pb = str(a), str(b)
        if os.path.normcase(os.path.abspath(pa)) == os.path.normcase(os.path.abspath(pb)):
            return True
        return os.path.exists(pa) and os.path.exists(pb) and os.path.samefile(pa, pb)
    except Exception:
        return False


def collect_and_promote_downloads(cache_root: str, final_dir: str, log: Callable = print,
                                  since: float = 0.0,
                                  only: Optional[List[Any]] = None) -> List[str]:
    """把 _musicdl_cache 内新下的音视频搬到 final_dir，返回最终路径；并清 pkl。
    since>0 时只搬该时间戳之后写入的文件，避免把历史遗留文件当成本次结果。

    only 给了文件清单时改为按那个顺序逐个搬，返回值与 only 一一对应（搬不上的位置是 ""）——
    调用方要靠下标把文件对回缓存 id 才写得了正确的文件名/歌词/标签，而按 mtime 扫出来的是
    并发下载的完成顺序，对不上。
    """
    import shutil
    from pathlib import Path as _P
    cache = _P(cache_root)
    final = _P(final_dir)
    final.mkdir(parents=True, exist_ok=True)
    paths: List[str] = []
    audio_ext = {".mp3", ".flac", ".m4a", ".aac", ".ogg", ".wav", ".opus"}
    aligned = only is not None
    candidates: List[Any] = []
    if aligned:
        candidates = [_P(str(p)) if p else None for p in only]
    else:
        if not cache.exists():
            cleanup_musicdl_pkl(str(final), log=log)
            cleanup_musicdl_pkl(str(cache), log=log)
            return paths
        # 按修改时间取最近的音频（本次下载）
        for p in cache.rglob("*"):
            if p.is_file() and p.suffix.lower() in audio_ext and p.stat().st_mtime >= since:
                candidates.append(p)
        candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    # 去重：同大小+近似名只留一个；对齐模式下重复的那首要指到第一首的最终路径上
    seen: Dict[tuple, str] = {}
    for p in candidates:
        if p is None or not p.is_file():
            if aligned:
                paths.append("")
            continue
        key = (p.stat().st_size, p.name.replace(" (1)", "").replace("(1)", ""))
        if key in seen:
            kept = seen[key]
            if not (kept and _same_file(p, Path(kept))):
                try:
                    p.unlink(missing_ok=True)
                except Exception:
                    pass
            if aligned:
                paths.append(kept)
            continue
        seen[key] = ""
        dest = final / p.name
        if dest.exists():
            # 已存在同名则跳过重复
            if dest.stat().st_size == p.stat().st_size:
                if _same_file(p, dest):
                    # 成品本来就在目标目录里（源＝目标）。这里若按「重复」删源，
                    # 删掉的就是这首歌自己 —— 归档会返回一个指向空气的路径，
                    # 上层只当成功，最后只剩歌词文件留在原地。
                    seen[key] = str(dest)
                    paths.append(str(dest))
                    continue
                try:
                    p.unlink(missing_ok=True)
                except Exception:
                    pass
                seen[key] = str(dest)
                paths.append(str(dest))
                continue
            dest = final / f"{p.stem}_{int(p.stat().st_mtime)}{p.suffix}"
        try:
            sidecars = [s for s in (p.with_suffix(e) for e in SIDE_CAR_EXTS) if s.is_file()]
            sidecars += [s for s in p.parent.glob(p.stem + ".*") if s.is_file() and s.suffix.lower() in SIDE_CAR_EXTS]
            shutil.move(str(p), str(dest))
            seen[key] = str(dest)
            paths.append(str(dest))
            log(f"已归档: {dest.name}")
            # 同 stem 封面/歌词
            for side in {s.resolve(): None for s in sidecars}:
                sd = final / side.name
                if sd.exists() and sd.stat().st_size == side.stat().st_size:
                    if not _same_file(side, sd):
                        try:
                            side.unlink(missing_ok=True)
                        except Exception:
                            pass
                    continue
                try:
                    shutil.move(str(side), str(sd))
                except Exception:
                    pass
        except Exception as e:
            log(f"归档失败 {p.name}: {e}", "warning")
            seen[key] = str(p)
            paths.append(str(p))
    cleanup_musicdl_pkl(str(cache), log=log)
    cleanup_musicdl_pkl(str(final), log=log)
    n_empty = cleanup_empty_dirs(cache, log=log)
    if n_empty:
        log(f"已清理空缓存目录 × {n_empty}")
    return paths


def cleanup_empty_dirs(root: "Path", log: Callable = print) -> int:
    """归档完成后，递归删除 _musicdl_cache 下留空的客户端/批次子目录（不删 root 本身）。"""
    from pathlib import Path as _P
    root = _P(root)
    if not root.exists():
        return 0
    n = 0
    # 按深度从深到浅排序，保证先删子目录再判断父目录是否也空了
    dirs = sorted((d for d in root.rglob("*") if d.is_dir()), key=lambda d: len(d.parts), reverse=True)
    for d in dirs:
        try:
            if not any(d.iterdir()):
                d.rmdir()
                n += 1
        except Exception:
            pass
    return n


def cleanup_musicdl_pkl(root: str, log: Callable = print) -> int:
    """删除 musicdl 产生的 search/download_results.pkl，释放空间。"""
    n = 0
    root_p = Path(root)
    if not root_p.exists():
        return 0
    for name in ("search_results.pkl", "download_results.pkl"):
        for f in root_p.rglob(name):
            try:
                f.unlink(missing_ok=True)
                n += 1
            except Exception:
                pass
    if n:
        log(f"已清理 musicdl 缓存 pkl × {n}")
    return n


# 绝对路径：相对名会跟着进程的工作目录走，从别处启动就会把工具有关文件撒到工具文件夹外面
MUSICDL_OUTPUTS = str(Path(__file__).resolve().parent / "musicdl_outputs")


_CACHE_LEAF = "_musicdl_cache"


def musicdl_cache_dir(base: str = "") -> str:
    """musicdl 的中间目录（搜索结果 pkl、还没归档的临时成品）。工具自己的东西不写进用户的下载目录，
    统一落在工具文件夹的 musicdl_outputs 下；按 base 的末级名分格，批量下载与试听各扫各的目录，
    不会把对方的文件当成本次的成果。
    幂等：调用方常把本函数的结果再传回来，重复拼接会让写入目录与归档扫描目录对不上，
    成品只能烂在缓存里。"""
    root = Path(MUSICDL_OUTPUTS) / _CACHE_LEAF
    leaf = Path(base).name if base else ""
    if leaf and leaf not in (_CACHE_LEAF, Path(MUSICDL_OUTPUTS).name):
        root = root / leaf
    try:
        root.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return str(root)

def _harden_console_encoding(log: Callable = print) -> None:
    """让 stdout/stderr 编不出的字符变成 '?'，而不是抛 UnicodeEncodeError。

    musicdl 的下载进度条带 SpinnerColumn（rich），Rich 在 Progress 退出时还会把最后一帧
    braille 转圈符（⠸ 之类）写进 stdout。Windows 上服务把 stdout 重定向到日志文件后，这个流
    按系统 GBK 编码，撞上编不出的字符就当场抛错 —— 而它发生在文件已经下完、还没归档的时候，
    等于把整片成品丢在 _musicdl_cache 里（实测 50 首的一批 6 片里炸了 3 片）。编码本身不动，
    只把 errors 换成 replace，进度条照常写日志。
    """
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        if stream is None or not hasattr(stream, "reconfigure"):
            continue
        if getattr(stream, "errors", None) == "replace":
            continue
        try:
            stream.reconfigure(errors="replace")
        except Exception as e:
            log(f"{name} 无法设为编码容错，musicdl 进度条可能中断下载: {e}", "warning")

def _build_client(
    sources: List[str],
    *,
    work_dir: str = MUSICDL_OUTPUTS,
    search_size: int = 8,
    cookies: Optional[str] = None,
    proxy: str = "",
    proxy_for: Optional[Callable[[str], str]] = None,
    strategy: Optional[dict] = None,
    log: Callable = print,
):
    from musicdl import musicdl

    # 三条 musicdl 路径（搜索 / 解析歌单 / 下载）都从这里建客户端，进度条写 stdout 的风险统一先兜住
    _harden_console_encoding(log)
    st = _merge_strategy(strategy)
    # 调用方可覆盖 search_size
    if search_size and not (strategy and strategy.get("search_size")):
        st["search_size"] = max(1, min(40, int(search_size)))

    srcs = [normalize_source_name(s) for s in sources if s]
    if not srcs:
        srcs = list(DEFAULT_SOURCES)
    srcs = _order_sources(srcs, st["order"])

    init_cfg: Dict[str, dict] = {}
    for src in srcs:
        cfg: dict = {
            "search_size_per_source": st["search_size"],
            "disable_print": True,
            "work_dir": musicdl_cache_dir(work_dir),
            "max_retries": st["max_retries"],
        }
        if cookies:
            cfg["default_search_cookies"] = cookies
            cfg["default_download_cookies"] = cookies
            cfg["default_parse_cookies"] = cookies
            # Apple Music 完整音轨需要 media-user-token
            if "Apple" in src and "media-user-token" in cookies:
                cfg["media-user-token"] = cookies
                cfg["use_wrapper"] = True
        init_cfg[src] = cfg

    to = (st["connect_timeout"], st["read_timeout"])
    # 注意：timeout 绝不能放进 requests_overrides。musicdl 内部大量
    # requests.get(..., timeout=10, **request_overrides)（含 lrclib 歌词补全）会因
    # 重复关键字抛 TypeError，且被上层 suppress 吞掉——症状就是下载没有歌词。
    requests_overrides: Dict[str, dict] = {}
    for src in srcs:
        ov: dict = {"verify": False}
        prx = _proxies_of(_source_proxy(src, proxy, proxy_for))
        if prx:
            ov["proxies"] = prx
        requests_overrides[src] = ov

    clients_threadings = {src: st["threads_per_source"] for src in srcs}

    try:
        kwargs = dict(
            music_sources=srcs,
            init_music_clients_cfg=init_cfg,
            requests_overrides=requests_overrides or {},
        )
        # clients_threadings 在部分 musicdl 版本可用
        try:
            client = musicdl.MusicClient(**kwargs, clients_threadings=clients_threadings)
        except TypeError:
            client = musicdl.MusicClient(**kwargs)
    except Exception as e:
        log(f"MusicClient 初始化失败: {e}", "error")
        raise
    _apply_default_timeout(client, to, proxy, proxy_for)
    return client


def _apply_default_timeout(client: Any, timeout: tuple, proxy: str = "",
                           proxy_for: Optional[Callable[[str], str]] = None) -> None:
    """给 musicdl 的客户端补默认超时 + 代理，它自己两样都不写。

    parseplaylist 一进来就用 `self.session.head(链接)` 再逐曲 `session.get`，直连不
    通的海外站点能挂到操作系统超时为止；代理不注入到这里就等于"搜索能出国、解析出不
    了国" —— MusicClient 那层的 requests_overrides 只在它自己分发时传，我们直接调
    单源客户端时必须自己带。
    """

    def _defaults(name: str) -> Dict[str, Any]:
        px = proxy if proxy_for is None else (proxy_for(name) or "")
        d: Dict[str, Any] = {}
        if timeout:
            d["timeout"] = timeout
        prx = _proxies_of(px)
        if prx:
            d["proxies"] = prx
        d["verify"] = False
        return d

    for src_name, mc in (getattr(client, "music_clients", None) or {}).items():
        defaults = _defaults(str(src_name))
        for name in ("get", "post"):
            fn = getattr(mc, name, None)
            if not callable(fn):
                continue

            def wrapped(url, _fn=fn, _d=defaults, **kw):
                for k, v in _d.items():
                    kw.setdefault(k, v)
                return _fn(url, **kw)

            setattr(mc, name, wrapped)
        sess = getattr(mc, "session", None)
        if sess is None:
            continue
        for name in ("get", "post", "head"):
            fn = getattr(sess, name, None)
            if not callable(fn):
                continue

            def wrapped_req(url, _fn=fn, _d=defaults, **kw):
                for k, v in _d.items():
                    kw.setdefault(k, v)
                return _fn(url, **kw)

            try:
                setattr(sess, name, wrapped_req)
            except Exception:
                pass


def _cache_song(song: Any) -> str:
    sid = str(uuid.uuid4())
    with _CACHE_LOCK:
        if len(_SONG_CACHE) >= _MAX_CACHE:
            # 丢弃一半最旧
            for k in list(_SONG_CACHE.keys())[: _MAX_CACHE // 2]:
                _SONG_CACHE.pop(k, None)
        _SONG_CACHE[sid] = song
    return sid


def get_cached_song(sid: str) -> Any:
    with _CACHE_LOCK:
        return _SONG_CACHE.get(sid)


def set_cached_song(sid: str, song: Any) -> None:
    """原地替换某个缓存 id 的内容 —— 占位条目匹配到真 SongInfo 后，调用方手里的 id 不用换。"""
    with _CACHE_LOCK:
        _SONG_CACHE[sid] = song


def _dur_seconds(v: Any) -> int:
    """"202" / "3:22" / "0:3:22" / 202.4 → 秒；认不出来返回 0（0 = 没有时长信息，不参与比较）。"""
    s = str(v if v is not None else "").strip()
    if not s or s in ("-1", "-:-:-", "--:--:--"):
        return 0
    if ":" in s:
        parts = s.split(":")
        try:
            return int(round(sum(float(p or 0) * 60 ** (len(parts) - 1 - i)
                                 for i, p in enumerate(parts))))
        except ValueError:
            return 0
    try:
        return int(round(float(s)))
    except ValueError:
        return 0


def _hms(ms: Any) -> str:
    """毫秒 → "3:22" / "1:02:03"，取不到就返回空串。"""
    try:
        sec = int(round(float(ms) / 1000))
    except (TypeError, ValueError):
        return ""
    if sec <= 0:
        return ""
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _songinfo_to_dict(song: Any, source: str) -> dict:
    def g(*names, default=""):
        if isinstance(song, dict):
            for n in names:
                if song.get(n) not in (None, ""):
                    return song.get(n)
            return default
        for n in names:
            v = getattr(song, n, None)
            if v not in (None, ""):
                return v
        return default

    title = str(g("song_name", "songname", "title", "name") or "未知")
    artists = g("singers", "artists", "singer", "artist") or ""
    if isinstance(artists, (list, tuple)):
        artists = ", ".join(str(a) for a in artists)
    artists = str(artists)
    duration = g("duration", "interval") or ""
    album = str(g("album") or "")
    cover = str(g("cover_url", "album_pic", "cover") or "")
    quality = str(g("ext", "file_size", "filesize", "quality") or "")
    url = str(g("download_url", "url", "songurl", "link") or "")
    if not url:
        raw = g("raw_data", default={}) or {}
        if isinstance(raw, dict):
            dl = raw.get("download") or {}
            if isinstance(dl, dict):
                url = str(dl.get("url") or dl.get("path") or "")
    src_full = str(g("source") or source)
    if not src_full.endswith("Client") and source.endswith("Client"):
        src_full = source
    src_short = src_full.replace("MusicClient", "").replace("Client", "")
    cache_id = _cache_song(song)
    # 来源列不能只写 src_short：Spotify 那半边只有元数据，音频是转链站从 YouTube 抽回来的，
    # 界面上标「Spotify」会让用户以为成品是 Spotify 母带。
    org = audio_origin(song)
    return {
        "id": cache_id,
        "title": title,
        "artists": artists,
        "duration": duration,
        "duration_s": _dur_seconds(g("duration_s", default=0) or duration),
        "album": album,
        "source": src_short,
        "real_source": org["label"],
        "unofficial": org["unofficial"],
        "reupload_suspect": org["reupload"],
        "origin_reasons": org["reasons"],
        "musicdl_source": src_full if "Client" in src_full else f"{src_full}MusicClient",
        "url": url,
        "quality": quality,
        "cover": cover,
        "can_musicdl_download": True,
        "has_episodes": bool(g("episodes", default=None)),
    }



try:
    from zhconv import convert as _zh_convert
except Exception:
    _zh_convert = None


def _to_simplified(s: str) -> str:
    if not _zh_convert or not s:
        return s
    return _zh_convert(s, "zh-cn")


def _norm_text(s: str) -> str:
    import re
    # 匹配判定是精确相等，繁體歌名/歌手在简体曲库里必然对不上，先统一成简体
    s = _to_simplified((s or "").strip().lower())
    # 全角转半角、去括号附属名、空白
    s = s.replace("（", "(").replace("）", ")")
    s = re.sub(r"\([^)]*\)|（[^）]*）", " ", s)
    s = re.sub(r"[\[\]【】]", " ", s)
    for w in ("官方", "正式版", "完整版", "live", "live版", "现场", "伴奏", "纯音乐", "dj版", "翻自"):
        s = s.replace(w, " ")
    s = re.sub(r"[\s\-_·•.,，。!！?？/\\]+", "", s)
    return s


def _quality_score(q: str) -> int:
    q = (q or "").lower()
    if "flac" in q or "ape" in q or "wav" in q:
        return 100
    if "320" in q or "hires" in q or "hi-res" in q:
        return 80
    if "192" in q or "m4a" in q or "aac" in q:
        return 50
    if "128" in q or "mp3" in q:
        return 30
    if "ogg" in q:
        return 20
    return 10


# ── 音质要求：用户在界面上点名的格式 / 位深 / 采样率 / 码率 ──────────────
#
# musicdl 每一源取哪一档音质写死在它自己的阶梯里（网易云 MUSIC_QUALITIES =
# jymaster…standard、酷我 (22000,'flac')/(320,'mp3')、酷狗 hires/lossless/exhigh），
# 建客户端时没有任何参数能钉住它。所以这里的「要求」只做两件做得到的小事：
# ① 同一首歌在多个候选里挑时，达标的排到前面（跨平台搜索结果里常同时有 128k 与无损）；
# ② 挑完/下完把实际档位与要求差多少写明上屏，勾了「不达标不下」才整首跳过。
# 绝不假装这个开关能让平台吐出更高的一档 —— 拿不到就是拿不到，说清楚比静默降级有用。
QUALITY_FORMAT_OPTIONS = (
    ("", "不限"),
    ("lossless", "仅无损（flac / ape / wav）"),
    ("mp3", "MP3"),
    ("m4a", "M4A / AAC"),
)
QUALITY_BIT_DEPTH_OPTIONS = (0, 16, 24)
QUALITY_SAMPLE_RATE_OPTIONS = (0, 44100, 48000, 96000)
QUALITY_BITRATE_OPTIONS = (0, 128, 192, 320)
LOSSLESS_EXTS = ("flac", "ape", "wav", "alac", "aiff", "aif", "dsf", "dff", "tak", "tta", "wv")
QUALITY_SPEC_DEFAULT: Dict[str, Any] = {"format": "", "min_bit_depth": 0,
                                        "min_sample_rate": 0, "min_bitrate": 0, "strict": False}


def norm_quality_spec(spec: Any) -> dict:
    """清洗界面传来的要求；非法值一律退回「不限」，不会因为一个坏字符串让整批判歪。"""
    out = dict(QUALITY_SPEC_DEFAULT)
    if not isinstance(spec, dict):
        return out
    fmt = str(spec.get("format") or "").strip().lower()
    out["format"] = fmt if fmt in {f for f, _ in QUALITY_FORMAT_OPTIONS} else ""
    for key, allowed in (("min_bit_depth", QUALITY_BIT_DEPTH_OPTIONS),
                         ("min_sample_rate", QUALITY_SAMPLE_RATE_OPTIONS),
                         ("min_bitrate", QUALITY_BITRATE_OPTIONS)):
        val = _meta_int(spec.get(key))
        out[key] = val if val in allowed else 0
    out["strict"] = bool(spec.get("strict"))
    return out


def quality_spec_active(spec: Any) -> bool:
    """有没有真提要求。全默认时下面那些判断一律跳过，免得给每一行白打一遍标。"""
    s = norm_quality_spec(spec)
    return bool(s["format"] or s["min_bit_depth"] or s["min_sample_rate"] or s["min_bitrate"])


def _khz(rate: Any) -> str:
    """采样率的写法：44100 → 44.1、48000 → 48（整数就不带小数点）。"""
    try:
        v = float(rate) / 1000.0
    except (TypeError, ValueError):
        return ""
    return f"{v:.1f}".rstrip("0").rstrip(".")


def quality_spec_label(spec: Any) -> str:
    """把人话写回来：「无损、24bit 以上、96kHz 以上」。没提要求时回空串。"""
    s = norm_quality_spec(spec)
    parts = []
    if s["format"] == "lossless":
        parts.append("无损")
    elif s["format"]:
        parts.append(s["format"].upper())
    if s["min_bit_depth"]:
        parts.append(f"{s['min_bit_depth']}bit 以上")
    if s["min_sample_rate"]:
        parts.append(f"{_khz(s['min_sample_rate'])}kHz 以上")
    if s["min_bitrate"]:
        parts.append(f"{s['min_bitrate']}k 以上")
    return "、".join(parts)


def row_audio_facts(row: Any) -> dict:
    """从任意一种行里抠出音质事实：搜索结果、本地索引、musicdl 的 SongInfo、文件元数据。

    各处的键名与详略都不一样（参照行有 bit_depth/sampling_rate，搜索行只有一个
    quality 字符串如「flac 24bit」或「320k」），所以这里统一抠成一份；抠不到的留 0，
    调用方据此判「不知道」而不是「不达标」。
    """
    import re
    r = row if isinstance(row, dict) else {}
    q = str(r.get("quality") or "").strip().lower()
    ext = str(r.get("ext") or "").strip().lower().lstrip(".")
    if not ext:
        for k in ("tag_type", "codec"):
            v = str(r.get(k) or "").strip().lower().lstrip(".")
            if v and v not in ("id3", "vorbiscomments", "apev2", "mp4"):
                ext = v
                break
    if not ext:
        pth = str(r.get("path") or r.get("save_path") or "")
        if pth:
            ext = Path(pth).suffix.lower().lstrip(".")
    if not ext or ext in ("m4a", "aac"):
        m = re.search(r"\b(flac|ape|wav|mp3|m4a|aac|ogg|opus|wma|dsf|dff|aiff|tak|tta|wv)\b", q)
        if m:
            ext = m.group(1)
    bits = _meta_int(r.get("bit_depth"))
    if not bits:
        m = re.search(r"(\d{2})\s*bit", q)
        bits = int(m.group(1)) if m else 0
    rate = _meta_int(r.get("sample_rate") or r.get("sampling_rate"))
    if not rate:
        m = re.search(r"(\d+(?:\.\d+)?)\s*khz", q)
        rate = int(float(m.group(1)) * 1000) if m else 0
    kbps = _meta_int(r.get("bitrate_kbps"))
    if not kbps:
        m = re.search(r"(\d{2,4})\s*k(?:bps)?\b", q)
        kbps = int(m.group(1)) if m else 0
    lossless = bool(r.get("lossless")) or ext in LOSSLESS_EXTS or "flac" in q or "lossless" in q
    # 「320k」这类只带码率的标注虽然没写容器，但有码率必然是有损 —— 格式这一维算知道，
    # 否则勾了「仅无损」的行会被判成「没给出格式」而放过去。
    format_known = bool(ext or lossless or kbps)
    return {"ext": ext, "bit_depth": bits, "sample_rate": rate, "bitrate_kbps": kbps,
            "lossless": bool(lossless), "format_known": format_known,
            "known": bool(ext or bits or rate or kbps or q)}


def quality_facts_label(facts: dict) -> str:
    """把一份事实写成一行：「无损 flac 24bit/96kHz」「MP3 320k」。什么都没有回空串。"""
    if not facts or not facts.get("known"):
        return ""
    head = ("无损 " if facts["lossless"] else "") + (facts["ext"].upper() if facts["ext"] else "")
    tail = []
    if facts.get("bit_depth"):
        tail.append(f"{facts['bit_depth']}bit")
    if facts.get("sample_rate"):
        tail.append(f"{_khz(facts['sample_rate'])}kHz")
    if facts.get("bitrate_kbps") and not facts.get("lossless"):
        tail.append(f"{facts['bitrate_kbps']}k")
    s = " ".join(x for x in (head.strip(), "/".join(tail)) if x)
    return s


def quality_against_spec(facts: dict, spec: Any) -> dict:
    """逐维核对。拿不到的那一维不参与卡人（与打分闸门同一口径），但会记进 unknown，
    好让界面上写「没核到」而不是「已确认达标」。

    state：ok=已确认达标 / low=已确认不达标 / unknown=信息不足 / none=没提要求。
    """
    s = norm_quality_spec(spec)
    if not quality_spec_active(s):
        return {"state": "none", "note": "", "unknown": [], "spec": s, "want": ""}
    if isinstance(facts, dict) and "known" not in facts:
        facts = row_audio_facts(facts)
    want = quality_spec_label(s)
    bad: List[str] = []
    unknown: List[str] = []
    if s["format"] == "lossless":
        if facts["lossless"]:
            pass
        elif not facts.get("format_known"):
            unknown.append("格式")
        else:
            bad.append("不是无损")
    elif s["format"]:
        if not facts["ext"]:
            unknown.append("格式")
        elif facts["ext"] != s["format"]:
            bad.append(f"格式是 {facts['ext'].upper() if facts['ext'] else '未知'}，不是 {s['format'].upper()}")
    if s["min_bit_depth"]:
        if not facts["bit_depth"]:
            unknown.append("位深")
        elif facts["bit_depth"] < s["min_bit_depth"]:
            bad.append(f"{facts['bit_depth']}bit 低于要求 {s['min_bit_depth']}bit")
    if s["min_sample_rate"]:
        if not facts["sample_rate"]:
            unknown.append("采样率")
        elif facts["sample_rate"] < s["min_sample_rate"]:
            bad.append(f"{_khz(facts['sample_rate'])}kHz 低于要求 {_khz(s['min_sample_rate'])}kHz")
    if s["min_bitrate"] and not facts["lossless"]:
        # 无损不看码率这一维：16bit/44.1kHz 的 flac 本来就在 900kbps 以上，
        # 而平台常不给无损文件报码率，按码率卡它只会把最好的那一档判成不达标。
        if not facts["bitrate_kbps"]:
            unknown.append("码率")
        elif facts["bitrate_kbps"] < s["min_bitrate"]:
            bad.append(f"{facts['bitrate_kbps']}k 低于要求 {s['min_bitrate']}k")
    have = quality_facts_label(facts)
    if bad:
        return {"state": "low", "note": f"{have or '档位未知'}，低于要求 {want}：" + "；".join(bad),
                "unknown": unknown, "spec": s, "want": want, "have": have}
    if unknown:
        return {"state": "unknown", "note": f"平台没给出{'、'.join(unknown)}，这一维没核到",
                "unknown": unknown, "spec": s, "want": want, "have": have}
    return {"state": "ok", "note": "", "unknown": [], "spec": s, "want": want, "have": have}


def annotate_quality_spec(rows: List[dict], spec: Any) -> List[dict]:
    """给搜索结果行打上 quality_state / quality_note / quality_have，界面据此标注。

    参照行（只读元数据）与本地行不参与：前者本来就不是可下的成品，后者的档位已经在
    quality 列里由真标签算出来了。
    """
    s = norm_quality_spec(spec)
    if not quality_spec_active(s):
        return rows or []
    for r in rows or []:
        if not isinstance(r, dict) or r.get("reference_only") or r.get("is_local"):
            continue
        qa = quality_against_spec(row_audio_facts(r), s)
        r["quality_state"] = qa["state"]
        r["quality_note"] = qa["note"]
        r["quality_have"] = qa.get("have") or ""
    return rows or []


def song_spec_facts(song: Any) -> dict:
    """musicdl 的 SongInfo 在**下载之前**能知道的音质事实（平台标注，不是成品文件真值）。

    musicdl 的 `bitrate` 是 bps（它直接抄 mutagen 的 `tag.bitrate`），而界面要求和成品标签都按
    kbps 说话，所以这里换算；平台自己的档位名（网易云的 lossless / hires）不在 SongInfo 上，
    只在 `raw_data["quality"]` 里，当作补充线索一起抠 —— 认不出的档位名会落回「不知道」，
    而不知道永远不判不达标。
    """
    kbps = _meta_int(song_field(song, "bitrate"))
    if kbps >= 1000:
        kbps //= 1000
    raw = _song_field(song, "raw_data")
    q = " ".join(x for x in (str(_song_field(song, "ext")),
                             str(raw.get("quality") or "") if isinstance(raw, dict) else "") if x)
    return row_audio_facts({"quality": q, "bitrate_kbps": kbps,
                            "sample_rate": _meta_int(song_field(song, "samplerate")),
                            "path": str(_song_field(song, "save_path", "filepath"))})


def ref_compare(facts: dict, ref: dict) -> dict:
    """把一行的音质事实与 Qobuz / Tidal 官方曲库那一行比一比 —— **只比元数据**。

    参照行的音频锁在对方有意设的校验后面，这里不取令牌、不绕校验，比的就是曲库里写着的
    无损标记 / 位深 / 采样率。
    state：none=没有可比对的参照 / same=与参照同档 / below=低于参照 /
    unknown=参照或成品这一维读不出来（读不出来不判低于，与打分闸门同一口径）。
    """
    if not isinstance(ref, dict) or not ref:
        return {"state": "none", "note": "", "want": "", "have": ""}
    rf = row_audio_facts(ref) if "known" not in ref else ref
    f = row_audio_facts(facts) if isinstance(facts, dict) and "known" not in facts else (facts or {})
    want = quality_facts_label(rf) or "参照未标注档位"
    have = quality_facts_label(f)
    if not f.get("known"):
        return {"state": "unknown", "note": f"这一行没有档位信息，无法与参照（{want}）比对",
                "want": want, "have": ""}
    bad: List[str] = []
    unk: List[str] = []
    if rf["lossless"]:
        if not f["lossless"]:
            bad.append("参照是无损，这一条不是")
    elif not rf.get("format_known"):
        unk.append("格式")
    if rf["bit_depth"]:
        if not f["bit_depth"]:
            unk.append("位深")
        elif f["bit_depth"] < rf["bit_depth"]:
            bad.append(f"位深 {f['bit_depth']}bit 低于参照 {rf['bit_depth']}bit")
    if rf["sample_rate"]:
        if not f["sample_rate"]:
            unk.append("采样率")
        elif f["sample_rate"] < rf["sample_rate"]:
            bad.append(f"采样率 {_khz(f['sample_rate'])}kHz 低于参照 {_khz(rf['sample_rate'])}kHz")
    tail = f"（{'、'.join(unk)}参照里有、这一条没有）" if unk else ""
    if bad:
        return {"state": "below", "note": f"低于参照 {want}：" + "；".join(bad) + tail,
                "want": want, "have": have}
    if unk:
        return {"state": "unknown", "note": f"{tail.strip('（）')}，只能确认没低于参照 {want}",
                "want": want, "have": have}
    return {"state": "same", "note": f"与参照 {want} 同档", "want": want, "have": have}


def annotate_reference_compare(rows: List[dict], refs: List[dict]) -> List[dict]:
    """给每条可下载的结果标上「与无损参照比一比」的结论（ref_state / ref_note）。

    先过同一道打分闸门：参照里那条时长都对不上的，结论是「没有可比对的参照」而不是
    「低于参照」—— 那是两版录音，不是音质差。参照行与本地行自己不标。
    """
    pool = [r for r in (refs or []) if isinstance(r, dict) and r.get("reference_only")]
    if not pool:
        return rows or []
    for r in rows or []:
        if not isinstance(r, dict) or r.get("reference_only") or r.get("is_local"):
            continue
        best: Optional[dict] = None
        best_key: tuple = ()
        time_reject = False
        for c in pool:
            sc = track_score(r, c)
            if sc["reject"]:
                time_reject = time_reject or "时长" in sc["reject"]
                continue
            if sc["score"] < MATCH_ACCEPT:
                continue
            key = (sc["score"], _quality_score(str(c.get("quality") or "")))
            if best is None or key > best_key:
                best, best_key = c, key
        if best is None:
            r["ref_state"] = "none"
            r["ref_note"] = ("参照里有同名曲但时长对不上，不是同一版录音"
                             if time_reject else "无损参照里没有这首歌")
            continue
        qa = ref_compare(row_audio_facts(r), best)
        r["ref_state"] = qa["state"]
        r["ref_note"] = qa["note"]
        r["ref_id"] = str(best.get("id") or "")
        r["ref_isrc"] = str(best.get("isrc") or "")
    return rows or []


def check_quality(paths: List[str], *, spec: Any = None, use_reference: bool = False,
                  proxy: str = "", log: Callable = print) -> List[dict]:
    """逐份成品读它**自己**的标签，报实际档位，再对照音质要求与（可选）无损参照。

    参照那一步只查 Qobuz / Tidal 官方曲库的元数据，音频锁在对方有意设的校验后面，这里不碰；
    参照查不到或查挂了都不影响「实际档位」这一份结论。
    """
    s = norm_quality_spec(spec)
    out: List[dict] = []
    for p in paths or []:
        p = str(p)
        row: Dict[str, Any] = {"path": p, "name": Path(p).name, "title": "", "artists": "",
                               "duration_s": 0, "have": "", "state": "missing", "note": "",
                               "ref_state": "", "ref_note": "", "reader": ""}
        out.append(row)
        if not Path(p).is_file():
            row["note"] = "文件不在了（可能被移走或改名）"
            continue
        try:
            meta = audio_file_meta(p, log=log)
        except Exception as e:
            row["state"] = "unknown"
            row["note"] = f"读不出文件标签：{type(e).__name__}: {e}"
            continue
        row["title"] = str(meta.get("title") or "")
        row["artists"] = str(meta.get("artists") or "")
        row["duration_s"] = int(meta.get("duration_s") or 0)
        row["reader"] = str(meta.get("reader") or "")
        facts = row_audio_facts(meta)
        row["have"] = quality_facts_label(facts)
        qa = quality_against_spec(facts, s)
        row["state"] = qa["state"]
        row["note"] = qa["note"] or (row["have"] and f"实际 {row['have']}" or "文件里没有档位标签")
        if not use_reference:
            continue
        want = {"title": row["title"] or Path(p).stem, "artists": row["artists"],
                "duration_s": row["duration_s"]}
        # 参照比对要看的就是成品自己的标签：不带 facts 进去，结论永远停在「这一行没有档位信息」
        want.update({k: v for k, v in facts.items() if k != "known"})
        try:
            refs = flacref_search(f"{row['artists']} {row['title']}".strip() or Path(p).stem,
                                  limit=5, proxy=proxy, log=log)
        except Exception as e:
            refs = []
            row["ref_note"] = f"无损参照查询失败：{type(e).__name__}: {e}"
        if refs:
            annotate_reference_compare([want], refs)
        row["ref_state"] = str(want.get("ref_state") or ("none" if refs else ""))
        row["ref_note"] = row["ref_note"] or str(want.get("ref_note") or "")
        row["ref_isrc"] = str(want.get("ref_isrc") or "")
    return out


def _song_fingerprint(item: dict, *, within_source: bool = False) -> str:
    import re
    title = _norm_text(str(item.get("title") or ""))
    # 先按分隔符切开再逐段归一：整串过 _norm_text 会先把逗号/斜杠吃掉，切不开就排不了序，
    # 「A,B」和「B,A」会算成两首歌。口径与 _track_key 一致。
    arts = ",".join(sorted(a for a in (_norm_text(x) for x in re.split(r"[/,，、;；&]",
                             str(item.get("artists") or ""))) if a))
    fp = f"{title}|{arts}"
    if within_source:
        fp = f"{item.get('source') or ''}|{fp}"
    return fp


def dedupe_results(items: list, mode: str = "global") -> list:
    """
    off: 不去重
    source: 仅源内去重（同平台同歌只留一条）
    global: 跨源去重（同歌多平台只留品质更高的一条，并记录 alt_sources）
    """
    mode = (mode or "global").lower()
    if mode == "off" or not items:
        return items
    within = mode == "source"
    best = {}  # fp -> index in out
    out = []
    for it in items:
        fp = _song_fingerprint(it, within_source=within)
        if not fp or fp == "|":
            out.append(it)
            continue
        if fp not in best:
            best[fp] = len(out)
            it = dict(it)
            it["alt_sources"] = []
            out.append(it)
            continue
        # 冲突：保留品质更高；同品质保留先出现（源顺序已由 order 决定）
        prev = out[best[fp]]
        if _quality_score(it.get("quality") or "") > _quality_score(prev.get("quality") or ""):
            alts = list(prev.get("alt_sources") or [])
            alts.append(prev.get("source") or "")
            if prev.get("source") and prev.get("source") != it.get("source"):
                pass
            merged = dict(it)
            # 保留其它源标记
            alt_set = [a for a in alts if a and a != merged.get("source")]
            if prev.get("source") and prev.get("source") != merged.get("source"):
                if prev.get("source") not in alt_set:
                    alt_set.append(prev.get("source"))
            merged["alt_sources"] = alt_set
            out[best[fp]] = merged
        else:
            src = it.get("source") or ""
            if src and src != prev.get("source"):
                alts = list(prev.get("alt_sources") or [])
                if src not in alts:
                    alts.append(src)
                    prev["alt_sources"] = alts
    return out


def _ingest_search_raw(raw, results, source_stats):
    if not isinstance(raw, dict):
        return
    for source, songs in raw.items():
        n = len(songs or [])
        key = str(source).replace("MusicClient", "")
        source_stats[key] = source_stats.get(key, 0) + n
        for song in songs or []:
            results.append(_songinfo_to_dict(song, str(source)))


class _ErrCapture:
    """截下 musicdl 吞进自家日志的报错。

    各家源的 _search 都是 `except Exception as err: self.logger_handle.error(...)` 然后
    返回空列表，MusicClient.search 外面又套了一层 suppress —— 0 条时上层什么都拿不到，
    只能干巴巴地报"网络/地区/Cookie/API"。这个代理挂在客户端实例的 logger_handle 上
    （每个源单独建客户端，所以捕获不会串味），原文留给上层翻译。
    """

    def __init__(self, inner):
        self._inner = inner
        self.msgs: List[str] = []

    def error(self, message, *a, **kw):
        self.msgs.append(str(message))
        return self._inner.error(message, *a, **kw)

    def __getattr__(self, name):
        return getattr(self._inner, name)


def _search_err_cn(src: str, text: str, proxy: str = "") -> str:
    """把捕获到的一行 musicdl 报错翻成能照着做的中文。

    不复用 _net_err_cn：它的措辞是给"用户贴了个海外歌单链接"写的，还会带上
    "Exception: " 这种没用的前缀。这里只知道某源内部失败了，说得越具体越好。
    """
    import re
    body = str(text or "").strip()
    m = re.search(r"\(Error:\s*(.+?)\)\s*$", body, re.S)
    if m:
        body = m.group(1).strip()
    low = body.lower()
    mh = re.search(r"host='([^']+)'", body)
    target = f"{mh.group(1)} " if mh else "该站点"
    if "429" in low or "too many requests" in low or "rate limit" in low:
        return f"{target}限流（HTTP 429），稍后再搜或少勾几个源"
    if "403" in low or "forbidden" in low or "captcha" in low:
        return f"{target}风控（HTTP 403/验证码），多半要登录 Cookie 或稍后再试"
    if "401" in low or "unauthorized" in low or "invalid token" in low:
        return f"{target}令牌失效（接口变更或缺登录 Cookie）"
    if "getaddrinfo" in low or "failed to resolve" in low or "nodetorename" in low:
        reason = f"{target}域名解析失败（本机 DNS）"
    elif "timed out" in low or "timeout" in low:
        reason = f"{target}连接超时"
    elif "ssl" in low or "certificate" in low:
        return "HTTPS 握手失败（证书或 TLS 版本问题，常见于网络抖动，重搜一次）"
    elif "connection" in low or "refused" in low or "unreachable" in low:
        reason = f"{target}连不上"
    else:
        return body[:160]
    if src in OVERSEAS_PLAYLIST_SOURCES:
        if proxy == PROXY_DIRECT:
            reason += "（按平台策略正在直连，在设置的「按平台代理」里把它改成走代理）"
        elif _real_proxy(proxy):
            reason += "（设置的代理节点不通该平台）"
        elif _system_proxy():
            reason += "（系统代理已生效仍不通，多半是代理节点不通该平台）"
        else:
            reason += "（国内直连通常不通，在设置里填 HTTP 代理）"
    return reason


def _source_reach_reason(src: str, proxy: str) -> str:
    """0 条且 musicdl 一行报错都没留 —— 只能自己探一次网络层。

    只探海外平台：国内源空结果多半真是没匹配，为它多花几秒探测还把"需要代理"的话吓到
    网易云用户，不值当。
    """
    if src not in OVERSEAS_PLAYLIST_SOURCES:
        return ""
    hosts = tuple(PLAYLIST_API_HOSTS.get(src) or ()) + tuple(PLAYLIST_HOSTS.get(src) or ())
    if not hosts:
        return ""
    return _unreachable_reason(f"https://{hosts[-1]}", proxy, timeout=5.0,
                               extra_hosts=hosts[:-1])


def _zero_result_reason(src: str, box: dict, *, budget: int, proxy: str) -> str:
    """一个源返回 0 条时的结论：超预算 > 上游报错 > 网络探测 > 兜底。"""
    if box.get("stopped") == "budget":
        tail = "该平台逐曲取址慢，可以只勾它单独搜" if "Spotify" in src or "Apple" in src \
            else "可以把策略里的每源预算调大"
        return f"{budget}s 内没跑完，本次已放弃等待（{tail}）"
    for msg in reversed(box.get("errs") or []):
        reason = _search_err_cn(src, msg, proxy)
        if reason:
            return reason
    return _source_reach_reason(src, proxy) or "该源返回 0 条（无匹配、需登录 Cookie 或地区限制）"


def _search_one_source(
    src: str,
    keyword: str,
    *,
    st: dict,
    work_dir: str,
    cookies: str,
    proxy: str,
) -> tuple:
    """跑一个源的搜索，返回 (条目 dict 列表, 上游报错原文列表)；任何异常都不外抛。"""
    songs: List[dict] = []
    errs: List[str] = []
    try:
        client = _build_client(
            [src],
            work_dir=work_dir or MUSICDL_OUTPUTS,
            search_size=st["search_size"],
            cookies=cookies or None,
            proxy=proxy,
            strategy=st,
            log=lambda *a, **k: None,
        )
    except Exception as e:
        return [], [f"{type(e).__name__}: {e}"]
    try:
        cap = _ErrCapture(client.logger_handle)
        client.logger_handle = cap
        for mc in (getattr(client, "music_clients", None) or {}).values():
            mc.logger_handle = cap
        _ingest_search_raw(client.search(keyword=keyword), songs, {})
        errs.extend(cap.msgs)
    except Exception as e:
        errs.append(f"{type(e).__name__}: {e}")
    return songs, errs


def _run_source_searches(
    srcs: List[str],
    keyword: str,
    *,
    st: dict,
    work_dir: str,
    cookies: str,
    proxy: str,
    log: Callable = print,
    proxy_for: Optional[Callable[[str], str]] = None,
) -> tuple:
    """每源一条线程 + 每源墙钟预算。返回 (结果, 计数表, 原因表, 耗时)。

    原来一次 MusicClient.search 把 N 个源整个交给 musicdl 排队：Spotify 逐曲取址能拖到
    280s，别的源早出结果也得陪着转圈，而且异常被它吞在内部。这里自己分发 —— 总耗时从
    "最慢那个源跑完为止"变成 min(最慢源, 每源预算)，到点放弃的源还得说清为什么。
    """
    budget = int(st.get("per_source_budget") or 0)
    srcs = canonical_sources(srcs)  # 同一个源搜两遍只会让耗时翻倍、结果重复
    # 只勾一两个源时，用户要的就是那两个源 —— 按整轮预算砍掉等于把答案丢掉，
    # 而且 0 条原因里劝的「只勾它单独搜」也会变成假话。这时放宽到 5 分钟。
    if budget and len(srcs) <= 2:
        wider = max(budget, 300)
        if wider != budget:
            log(f"每源预算 {budget}s → {wider}s：只勾了 {len(srcs)} 个源，按整轮预算砍等于把答案丢掉")
            budget = wider
            st["per_source_budget"] = wider  # 回写，搜索后的 diag 才报真正生效的预算
    boxes: Dict[str, dict] = {s: {"songs": [], "errs": [], "done": False} for s in srcs}

    def _px(src: str) -> str:
        return _source_proxy(src, proxy, proxy_for)

    def _spawn(src: str) -> threading.Thread:
        def _t():
            box = boxes[src]
            try:
                box["songs"], box["errs"] = _search_one_source(
                    src, keyword, st=st, work_dir=work_dir, cookies=cookies, proxy=_px(src)
                )
            except BaseException as e:  # noqa: BLE001 —— 兜底，别让一条线程掀桌
                box["errs"] = [f"{type(e).__name__}: {e}"]
            box["done"] = True

        th = threading.Thread(target=_t, daemon=True)
        th.start()
        return th

    started = time.time()
    if st["mode"] == "sequential":
        for src in srcs:
            th = _spawn(src)
            t0 = time.time()
            while th.is_alive():
                th.join(0.4)
                if th.is_alive() and budget and time.time() - t0 >= budget:
                    boxes[src]["stopped"] = "budget"
                    break
            log(f"  [{src.replace('MusicClient', '')}] "
                f"{len(boxes[src]['songs'])} 条 · {int(time.time() - started)}s")
    else:
        for s in srcs:
            _spawn(s)
        while any(not b["done"] for b in boxes.values()):
            if budget and time.time() - started >= budget:
                for s, b in boxes.items():
                    if not b["done"]:
                        b["stopped"] = "budget"
                break
            time.sleep(0.3)

    results: List[dict] = []
    stats: Dict[str, int] = {}
    errors: Dict[str, str] = {}
    for src in srcs:
        name = src.replace("MusicClient", "")
        box = boxes[src]
        n = len(box["songs"])
        stats[name] = n
        results.extend(box["songs"])
        if n == 0:
            reason = _zero_result_reason(src, box, budget=budget, proxy=_px(src))
            if reason:
                errors[name] = reason
    return results, stats, errors, round(time.time() - started, 1)


def search_music(
    keyword: str,
    *,
    sources: Optional[List[str]] = None,
    limit: int = 10,
    work_dir: str = "",
    cookies: str = "",
    proxy: str = "",
    proxy_for: Optional[Callable[[str], str]] = None,
    include_ytdlp: bool = True,
    strategy: Optional[dict] = None,
    search_type: str = "song",
    hide_unavailable: bool = True,
    include_local: bool = False,
    local_root: str = "",
    include_reference: bool = False,
    reference_proxy: str = "",
    quality_spec: Any = None,
    log: Callable = print,
) -> List[Dict[str, Any]]:
    keyword = (keyword or "").strip()
    if not keyword:
        return []
    st = _merge_strategy(strategy)
    # limit 与 strategy.search_size 取较大，保证每源条数
    limit = max(1, min(40, int(limit or st["search_size"])))
    if strategy is None or strategy.get("search_size") is None:
        st["search_size"] = limit
    results: List[Dict[str, Any]] = []

    source_stats = {}
    global _LAST_SEARCH_STATS, _LAST_SEARCH_DIAG
    _LAST_SEARCH_STATS = {}
    _LAST_SEARCH_DIAG = {"budget": st["per_source_budget"], "elapsed": 0.0, "errors": {}}
    if musicdl_available():
        srcs = sources or list(DEFAULT_SOURCES)
        srcs = _order_sources(canonical_sources(srcs), st["order"])
        log(
            f"音乐搜索策略: mode={st['mode']} order={st['order']} "
            f"size={st['search_size']} retries={st['max_retries']} "
            f"timeout={st['connect_timeout']}/{st['read_timeout']}s "
            f"threads={st['threads_per_source']} 每源预算={st['per_source_budget'] or '不限'}s "
            f"源={len(srcs)}"
        )
        if proxy_for is not None:
            # 自动模式到底怎么判的要看得到，否则"为什么网易云没走代理"只能猜
            log("每源代理: " + ", ".join(
                f"{s.replace('MusicClient', '')}={_proxy_label(proxy_for(s))}" for s in srcs
            ))
        try:
            songs, source_stats, source_errors, elapsed = _run_source_searches(
                srcs,
                keyword,
                st=st,
                work_dir=work_dir,
                cookies=cookies,
                proxy=proxy,
                log=log,
                proxy_for=proxy_for,
            )
            results.extend(songs)
            log(
                f"musicdl 搜索完成: {len(results)} 条 · {elapsed}s | "
                + ", ".join(f"{k}:{v}" for k, v in source_stats.items())
            )
            _LAST_SEARCH_STATS = dict(source_stats)
            _LAST_SEARCH_DIAG = {
                "budget": st["per_source_budget"],
                "elapsed": elapsed,
                "errors": dict(source_errors),
            }
            for name, reason in source_errors.items():
                log(f"  [{name}] 0 条：{reason}", "warning")
        except Exception as e:
            log(f"musicdl.search 失败: {e}", "warning")
    else:
        log("musicdl 不可用，仅 yt-dlp 回退", "warning")

    if include_ytdlp and len(results) < limit:
        yt = _ytdlp_music_search(keyword, limit=min(8, limit), log=log)
        seen = {(r.get("title"), r.get("artists")) for r in results}
        for item in yt:
            key = (item.get("title"), item.get("artists"))
            if key in seen:
                continue
            seen.add(key)
            results.append(item)

    before = len(results)
    results = dedupe_results(results, st.get("dedupe", "global"))
    if before != len(results):
        log(f"去重({st.get('dedupe')}): {before} → {len(results)} 条")

    stype = (search_type or "song").lower()
    if stype == "album":
        for it in results:
            it["search_type"] = "album"
    elif stype == "playlist":
        for it in results:
            it["search_type"] = "playlist"

    if include_local and local_root:
        try:
            loc = search_local_music(keyword, local_root, limit=min(20, limit), log=log)
            results = loc + results
            log(f"本地命中: {len(loc)}")
        except Exception as e:
            log(f"本地搜索失败: {e}", "warning")

    if hide_unavailable:
        n0 = len(results)
        results = filter_search_results(results, hide_unavailable=True)
        if len(results) != n0:
            log(f"过滤不可用/付费: {n0} → {len(results)}")

    ref_rows: List[dict] = []
    if include_reference and (search_type or "song").lower() == "song":
        try:
            ref = flacref_search(keyword, limit=limit, proxy=reference_proxy, log=log)
        except Exception as e:
            log(f"无损参照查询失败：{e}", "warning")
            ref = []
        if ref:
            # 整份参照都留着：同一首歌的那条会因为"本平台已有"被挤出 results，
            # 但核对成品音质要的恰恰就是它，不能跟着一起丢。
            ref_rows = ref
            have = {_song_fingerprint(r) for r in results}
            extra = [r for r in ref if _song_fingerprint(r) not in have]
            results = results + extra
            log(f"无损参照: {len(ref)} 条，其中 {len(extra)} 条本平台搜索结果里没有")

    annotate_quality_spec(results, quality_spec)
    annotate_reference_compare(results, ref_rows)
    return results


# --------------------------------------------------------------- 无损元数据参照源
# flacdownloader.com 的 /api/qobuz/search、/api/tidal/search 只要带 User-Agent 就回 200，
# 给的是 Qobuz/Tidal 官方曲库的 ISRC、精确时长、位深/采样率和官方链接 —— 恰好是我们自己
# 那批源最缺的东西（musicdl 的 Qobuz/Tidal 源要 X-User-Auth-Token，没账号就是 0 条）。
# 音频那一步它锁在 /prepare + Cloudflare 人机校验后面（前端遇 403 就重取校验令牌），
# 那是人家有意设的门槛，所以这里**只借它查、不借它下**：参照行标 reference_only，
# 界面上勾不动，也不会被喂进下载和匹配链路。
FLACREF_BASE = "https://flacdownloader.com"
FLACREF_PLATFORMS = ("qobuz", "tidal")
FLACREF_LABELS = {"qobuz": "Qobuz", "tidal": "Tidal"}


def _flacref_get(platform: str, query: str, offset: int, *, proxy: str = "",
                 timeout: float = 12.0) -> List[dict]:
    import requests
    kwargs: Dict[str, Any] = {
        "params": {"q": query, "offset": offset},
        "timeout": timeout,
        "headers": {"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
    }
    if proxy:
        kwargs["proxies"] = {"http": proxy, "https": proxy}
    resp = requests.get(f"{FLACREF_BASE}/api/{platform}/search", **kwargs)
    resp.raise_for_status()
    data = resp.json()
    rows = data.get("tracks") if isinstance(data, dict) else None
    return [r for r in (rows or []) if isinstance(r, dict)]


def _flacref_int(v: Any) -> int:
    try:
        return int(float(str(v).strip()))
    except (TypeError, ValueError):
        return 0


def _flacref_row(platform: str, raw: dict) -> dict:
    """把 Qobuz/Tidal 的一行元数据折成搜索表的形状。拿不到曲名就丢弃这行。"""
    title = str(raw.get("title") or "").strip()
    if not title:
        return {}
    dur_s = _flacref_int(raw.get("durationMs")) // 1000
    tags = [str(t).upper() for t in (raw.get("tags") or [])]
    lossless = bool(raw.get("lossless") or raw.get("hires") or "LOSSLESS" in tags)
    bits = _flacref_int(raw.get("bitDepth"))
    rate = _flacref_int(raw.get("samplingRate"))
    quality = ""
    if lossless:
        quality = "flac" + (f" {bits}bit" if bits >= 16 else "")
    label = FLACREF_LABELS.get(platform, platform.capitalize())
    return {
        "id": f"ref:{platform}:{raw.get('id')}",
        "title": title,
        "artists": str(raw.get("artist") or raw.get("albumArtist") or "").strip(),
        "duration": f"{dur_s // 60}:{dur_s % 60:02d}" if dur_s else "",
        "duration_s": dur_s,
        "album": str(raw.get("album") or "").strip(),
        "source": f"{label}·参照",
        "real_source": f"{label} 官方曲库元数据（音频不从这里取）",
        "unofficial": False,
        "reupload_suspect": False,
        "origin_reasons": [],
        "musicdl_source": "",
        "url": str(raw.get("url") or ""),
        "quality": quality,
        "cover": str(raw.get("cover") or ""),
        "isrc": str(raw.get("isrc") or "").strip(),
        "version": str(raw.get("version") or "").strip(),
        "date": str(raw.get("date") or "").strip(),
        "label": str(raw.get("label") or "").strip(),
        "lossless": lossless,
        "bit_depth": bits,
        "sampling_rate": rate,
        "reference_only": True,
        "can_musicdl_download": False,
    }


def flacref_search(keyword: str, *, platforms=FLACREF_PLATFORMS, limit: int = 10,
                   proxy: str = "", log: Callable = print) -> List[dict]:
    """查 Qobuz/Tidal 官方曲库的元数据（参照用，不下音频）。单平台挂了不影响另一个。"""
    keyword = (keyword or "").strip()
    if not keyword:
        return []
    out: List[dict] = []
    per = max(1, min(int(limit or 10), 25))
    for p in platforms or ():
        p = str(p).strip().lower()
        if p not in FLACREF_LABELS:
            continue
        try:
            rows = _flacref_get(p, keyword, 0, proxy=proxy)
        except Exception as e:
            log(f"无损参照 {FLACREF_LABELS.get(p, p)} 查询失败：{type(e).__name__}: {e}", "warning")
            continue
        n = 0
        for raw in rows:
            row = _flacref_row(p, raw)
            if not row:
                continue
            out.append(row)
            n += 1
            if n >= per:
                break
        log(f"无损参照 {FLACREF_LABELS.get(p, p)}: {n} 条")
    return dedupe_results(out, "global") if out else out


# --------------------------------------------------------------- 歌单解析分流
# musicdl 的 MusicClient.parseplaylist 会把每个源的异常 suppress 掉，还会让所有源都去
# head 一遍同一个 URL —— 直连不通的站点能把每个源逐个拖超时，最后只剩"0 首"。
# 所以这里按域名只找那一个负责源，并把异常翻成人话。域名表照抄 musicdl modules/utils/hosts.py。

PLAYLIST_HOSTS: Dict[str, tuple] = {
    "NeteaseMusicClient": ("music.163.com", "163cn.tv"),
    "QQMusicClient": ("y.qq.com", "music.qq.com"),
    "KugouMusicClient": ("kugou.com",),
    "FiveSingMusicClient": ("5sing.kugou.com",),
    "MiguMusicClient": ("migu.cn",),
    "KuwoMusicClient": ("kuwo.cn",),
    "BodianMusicClient": ("bodian.kuwo.cn", "h5app.kuwo.cn"),
    "AppleMusicClient": ("music.apple.com", "itunes.apple.com", "apple.com"),
    "SpotifyMusicClient": ("open.spotify.com", "spotify.com", "spotify.link"),
    "SodaMusicClient": ("douyin.com", "qishui.com"),
    "StreetVoiceMusicClient": ("streetvoice.cn",),
    "MOOVMusicClient": ("moov.hk", "moov-music.com"),
    "SoundCloudMusicClient": ("soundcloud.com",),
    "DeezerMusicClient": ("deezer.com",),
    "QobuzMusicClient": ("qobuz.com",),
    "TIDALMusicClient": ("tidal.com",),
    "JooxMusicClient": ("joox.com",),
    "JioSaavnMusicClient": ("jiosaavn.com", "saavn.com"),
    "JamendoMusicClient": ("jamendo.com",),
    "AudiusMusicClient": ("audius.co",),
    "FMAMusicClient": ("freemusicarchive.org",),
    "CCMixterMusicClient": ("ccmixter.org",),
    "SunoMusicClient": ("suno.com", "suno.ai"),
    "QianqianMusicClient": ("music.91q.com", "music.taihe.com", "music.baidu.com"),
}

# 这些平台的歌单 musicdl 压根没实现 parseplaylist，只能交给 yt-dlp
YTDLP_PLAYLIST_HOSTS: Dict[str, tuple] = {
    "youtube": ("youtube.com", "youtu.be", "music.youtube.com"),
    "bilibili": ("bilibili.com", "b23.tv"),
    "ximalaya": ("ximalaya.com",),
}

# yt-dlp 也认这些平台的歌单（抽取器在册且能用）。这些平台可以把"先秒出曲目"当默认。
# Spotify 绝不能放进来：yt-dlp 把 open.spotify.com 归进 extractor/unsupported.py 的
# DRM 站点，直接抛 "[DRM] ... NOT be supported"，对它承诺兜底就是骗人。
YTDLP_PLAYLIST_SOURCES = {
    "NeteaseMusicClient", "QQMusicClient", "SoundCloudMusicClient",
    "JioSaavnMusicClient", "StreetVoiceMusicClient", "JamendoMusicClient",
    "AudiusMusicClient",
}

# 这些平台 musicdl 能试、yt-dlp 却彻底不认（无抽取器 / 抽取器标 BROKEN / DRM 硬拒），
# 只能等 musicdl 逐曲跑完，提前放弃就等于解析失败。
MUSICDL_ONLY_SOURCES = {
    "KugouMusicClient", "FiveSingMusicClient", "MiguMusicClient", "KuwoMusicClient",
    "BodianMusicClient", "AppleMusicClient", "SpotifyMusicClient", "SodaMusicClient",
    "MOOVMusicClient", "DeezerMusicClient", "QobuzMusicClient", "TIDALMusicClient",
    "JooxMusicClient", "FMAMusicClient", "CCMixterMusicClient", "SunoMusicClient",
    "QianqianMusicClient",
}

# 国内直连通常不通的平台：只有它们 0 首时才提醒"没填代理"，别拿这话去吓网易云用户。
OVERSEAS_PLAYLIST_SOURCES = {
    "AppleMusicClient", "SpotifyMusicClient", "SoundCloudMusicClient", "DeezerMusicClient",
    "QobuzMusicClient", "TIDALMusicClient", "JooxMusicClient", "MOOVMusicClient",
    "StreetVoiceMusicClient", "JioSaavnMusicClient", "JamendoMusicClient",
    "AudiusMusicClient", "FMAMusicClient", "CCMixterMusicClient", "SunoMusicClient",
}
OVERSEAS_YTDLP_ONLY = {"youtube"}

_LAST_PLAYLIST_DIAG: Dict[str, Any] = {}


def _url_host(url: str) -> str:
    try:
        from urllib.parse import urlparse
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def _match_host_table(host: str, table: Dict[str, tuple]) -> str:
    """最长后缀优先：5sing.kugou.com 归 FiveSing，不该被 kugou.com 抢走。"""
    if not host:
        return ""
    best, best_len = "", 0
    for key, hosts in table.items():
        for h in hosts:
            if len(h) > best_len and (host == h or host.endswith("." + h)):
                best, best_len = key, len(h)
    return best


def _normalize_playlist_url(url: str) -> tuple:
    """把"浏览器里能打开、musicdl 却不认"的链接改写成它要求的写法。"""
    from urllib.parse import parse_qs, urlparse
    host = _url_host(url)
    p = urlparse(url)
    if _match_host_table(host, PLAYLIST_HOSTS) == "NeteaseMusicClient" and "#" not in url:
        pid = (parse_qs(p.query).get("id") or [""])[0]
        if pid and "playlist" in p.path:
            return f"https://music.163.com/#/playlist?id={pid}", "网易云链接已改写为 #/playlist?id= 写法"
    if _match_host_table(host, PLAYLIST_HOSTS) == "KugouMusicClient" and "special/single/" not in p.path:
        import re
        q = parse_qs(p.query)
        pid = next(iter(q.get("scene_id") or q.get("id") or []), "")
        if not pid:
            nums = re.findall(r"(\d{5,})", p.path)
            pid = nums[0] if nums else ""
        if pid:
            return f"https://www.kugou.com/yy/special/single/{pid}.html", "酷狗链接已改写为 special/single 写法"
    return url, ""


# 汽水/抖音的域名在歌单表里（它能开歌单页），可同一个域名下 99% 的链接是单视频或主页 ——
# 那些当订阅源该走 yt-dlp 那条分支，不能被认成音乐歌单。
_MUSIC_VIDEO_PATH_HOSTS = ("douyin.com", "qishui.com")
_MUSIC_PLAYLIST_PATH_HINTS = ("playlist", "songlist", "mix", "collection", "music.")


def playlist_owner(url: str) -> str:
    """这条 http 链接归哪个音乐平台的歌单页管 → 源名（如 NeteaseMusicClient）；不是歌单返回 ""。"""
    u = str(url or "").strip()
    if not u.startswith("http"):
        return ""
    u, _ = _normalize_playlist_url(u)
    owner = _match_host_table(_url_host(u), PLAYLIST_HOSTS)
    if not owner:
        return ""
    low = u.lower()
    host = _url_host(low)
    if any(host == h or host.endswith("." + h) for h in _MUSIC_VIDEO_PATH_HOSTS) \
            and not any(w in low for w in _MUSIC_PLAYLIST_PATH_HINTS):
        return ""
    return owner


def music_playlist_hosts() -> List[str]:
    """所有能开音乐歌单域名（订阅页据此显示来源标签，最终判定仍以 playlist_owner 为准）。"""
    return sorted({h for hosts in PLAYLIST_HOSTS.values() for h in hosts})


def _net_err_cn(e: Exception) -> str:
    s = f"{type(e).__name__}: {e}"
    low = s.lower()
    if "getaddrinfo failed" in low or "name or service not known" in low or "failed to resolve" in low or "nodetorename" in low:
        return "域名解析失败（检查链接是否写对，或本机 DNS）"
    if "timed out" in low or "timeout" in low:
        return "连不上该站点（海外平台国内直连通常不通，请在设置里填 HTTP 代理）"
    if "ssl" in low or "certificate" in low:
        return "HTTPS 握手失败（证书或 TLS 版本问题）"
    if "drm" in low:
        return "yt-dlp 把这个站点归为 DRM 保护站点、直接拒收（Spotify 就是这种），只能等 musicdl 逐曲取址"
    if "connection" in low or "refused" in low or "unreachable" in low:
        return "连不上该站点（检查网络，海外平台需要代理）"
    return s[:160]


# 网页域名打不开 ≠ 解析不了：musicdl 的解析请求走的是各家 API 域名。实测本机
# open.spotify.com 的 TCP 直连超时，而 api-partner / accounts 两个域名 300ms 就通 ——
# 只看网页域名预检会把能解析的歌单一刀切掉（用户连撞 4 次"连不上该站点"）。
PLAYLIST_API_HOSTS: Dict[str, tuple] = {
    "SpotifyMusicClient": ("api-partner.spotify.com", "accounts.spotify.com"),
    "AppleMusicClient": ("itunes.apple.com", "amp-api.music.apple.com"),
    "SoundCloudMusicClient": ("api-v2.soundcloud.com", "w.soundcloud.com"),
    "DeezerMusicClient": ("api.deezer.com",),
    "QobuzMusicClient": ("www.qobuz.com", "streaming.qobuz.com"),
    "TIDALMusicClient": ("api.tidal.com", "login.tidal.com"),
    "JioSaavnMusicClient": ("api.saavn.com", "www.jiosaavn.com"),
    "NeteaseMusicClient": ("music.163.com", "interface3.music.163.com"),
    "QQMusicClient": ("c.y.qq.com", "u.y.qq.com"),
    "KugouMusicClient": ("mobiapi.cloudodk.com", "complexsearch.kugou.com"),
    "MiguMusicClient": ("migu.music.cn", "na.migu.cn"),
    "KuwoMusicClient": ("search.kuwo.cn", "ningmixsilu.kuwo.cn"),
}


def _system_proxy() -> str:
    """返回 OS/环境变量里已生效的 HTTP(S) 代理（没有则 ""）。

    本机实测：应用设置里没填代理，注册表却挂着 127.0.0.1:7897，requests/urllib 会自动走
    它 —— 这时再劝用户「去设置里填 HTTP 代理」是错的，真正该查的是代理节点通不通。
    """
    try:
        import urllib.request
        px = urllib.request.getproxies() or {}
    except Exception:
        return ""
    return str(px.get("https") or px.get("http") or "")


# 调用方（server 的平台代理策略）用这个哨兵表示"该源必须直连"：本机系统代理常在，
# 不显式禁用就会把网易云/QQ 音乐也一起绕进去，节点一抖整次搜索全 0 条。
PROXY_DIRECT = "direct"


def _proxies_of(proxy: str) -> Optional[dict]:
    """proxy 参数 → requests 的 proxies（"" = 不干预，跟随环境）。"""
    if proxy == PROXY_DIRECT:
        return {"http": None, "https": None}
    if proxy:
        return {"http": proxy, "https": proxy}
    return None


def _proxy_label(proxy: str) -> str:
    """给日志用的一行结论。"""
    if proxy == PROXY_DIRECT:
        return "直连"
    return "代理" if proxy else "跟随系统"


def _source_proxy(src: str, proxy: str, proxy_for: Optional[Callable[[str], str]] = None) -> str:
    """该源实际用的代理值：有 resolver 就问它，否则沿用一个值。"""
    return proxy if proxy_for is None else (proxy_for(src) or "")


def _real_proxy(proxy: str) -> str:
    """判"有没有代理在用"时把直连哨兵当没有。"""
    return "" if not proxy or proxy == PROXY_DIRECT else proxy


def _probe_http_ok(url: str, proxy: str, timeout: float) -> bool:
    return not _unreachable_reason(url, proxy, timeout=timeout)


def _unreachable_reason(url: str, proxy: str, timeout: float = 8.0,
                        extra_hosts=()) -> str:
    """只判网络层：能连上返回 ""。HTTP 4xx/5xx 一律算通，交给平台自己的解析去说。

    extra_hosts 是平台真正的解析域名 —— 网页域名不通、API 域名通，就不该判死。
    """
    try:
        import requests
        kwargs = dict(timeout=(min(4.0, timeout), timeout), verify=False, stream=True,
                      allow_redirects=True, headers={"User-Agent": "Mozilla/5.0"})
        prx = _proxies_of(proxy)
        if prx:
            kwargs["proxies"] = prx
        r = requests.get(url, **kwargs)
        r.close()
        return ""
    except Exception as e:
        reason = _net_err_cn(e)
    for h in extra_hosts:
        if _probe_http_ok(f"https://{h}", proxy, min(5.0, timeout)):
            return ""
    if "代理" in reason and not _real_proxy(proxy) and _system_proxy():
        reason = "连不上该站点（系统代理已在生效仍连不上，多半是代理节点不通该平台）"
    return reason


def _playlist_exists_note(owner: str, url: str, proxy: str) -> str:
    """musicdl 把 Spotify 内部的异常全吞了（parse 里 except Exception: return []），
    0 首时分不清"歌单根本不存在/是私有"还是"逐曲取址失败"。用它自己的免登录公开接口
    判一次，前端才给得出下一步动作。
    """
    if owner != "SpotifyMusicClient":
        return ""
    try:
        import requests
        kwargs = dict(params={"url": url}, timeout=(4, 8), verify=False,
                      headers={"User-Agent": "Mozilla/5.0"})
        prx = _proxies_of(proxy)
        if prx:
            kwargs["proxies"] = prx
        r = requests.get("https://open.spotify.com/oembed", **kwargs)
        if r.status_code == 200:
            title = str((r.json() or {}).get("title") or "").strip()
            return f"公开接口能查到这个歌单「{title or '无标题'}」，卡住的是逐曲取址"
        if r.status_code in (404, 410):
            return "公开接口查不到这个歌单：ID 不对，或是需登录才可见的私有歌单"
        return f"公开接口返回 HTTP {r.status_code}，暂时确认不了歌单是否存在"
    except Exception as e:
        return f"确认不了歌单是否存在（{type(e).__name__}）"


def _call_with_budget(fn: Callable, budget: int, default: Any = None) -> tuple:
    """在预算内跑 fn()，返回 (结果, 是否超时)；超时后那条 daemon 线程随它去。

    musicdl 逐曲取址、yt-dlp 撞墙重连都能把一次解析拖成几分钟，而这两条路都是同步
    HTTP 请求 —— 不封顶就等于让前端一直转圈。
    """
    box: Dict[str, Any] = {}

    def _run():
        try:
            box["v"] = fn()
        except BaseException as e:  # noqa: BLE001 —— 原样带回主线程再翻译
            box["e"] = e

    th = threading.Thread(target=_run, daemon=True)
    th.start()
    th.join(max(5, int(budget)))
    if th.is_alive():
        return default, True
    if "e" in box:
        raise box["e"]
    return box.get("v", default), False


def _parse_playlist_via_musicdl(
    source: str,
    url: str,
    *,
    work_dir: str = "",
    cookies: str = "",
    proxy: str = "",
    log: Callable = print,
    budget: int = 300,
) -> tuple:
    """直接调单个源的 parseplaylist —— 绕开 MusicClient 那层 suppress(Exception)。

    budget 是必须的：musicdl 逐曲去第三方接口取地址，几百首的歌单能量十几分钟，
    超时后返回空 + 原因，让上层去试 yt-dlp，别把 HTTP 请求挂死。
    """
    try:
        client = _build_client(
            [source],
            work_dir=work_dir or MUSICDL_OUTPUTS,
            search_size=5,
            cookies=cookies or None,
            proxy=proxy,
            # musicdl 逐曲去第三方接口取地址，30 首就是 30 轮。用默认的
            # 3 次重试 × 10s 连接超时，一个酷狗歌单能量到 400s，前端只能干转圈。
            strategy={"mode": "parallel", "max_retries": 1, "connect_timeout": 4,
                      "read_timeout": 12, "threads_per_source": 5, "dedupe": "off"},
            log=log,
        )
        sub = (getattr(client, "music_clients", None) or {}).get(source)
        if sub is None:
            return [], f"{source} 未能初始化（musicdl 版本过旧？点「更新 musicdl」）"
        # MusicClient 分发时是 parseplaylist(url, request_overrides=...)；我们绕开它
        # 直接调单源，不传就等于让 spotify/apple 的解析全程裸连。
        ovr: Dict[str, Any] = {"verify": False}
        prx = _proxies_of(proxy)
        if prx:
            ovr["proxies"] = prx
        try:
            accepts_ovr = "request_overrides" in inspect.signature(sub.parseplaylist).parameters
        except (TypeError, ValueError):
            accepts_ovr = False

        songs, timed_out = _call_with_budget(
            lambda: sub.parseplaylist(url, request_overrides=ovr) if accepts_ovr else sub.parseplaylist(url),
            budget, default=[],
        )
        if timed_out:
            return [], f"{source} 逐曲取址超过 {budget}s 还没解析完（歌单太大）"
    except Exception as e:
        # musicdl 所有源的收尾行都引用了循环变量 idx：歌单里一首没取到时必抛
        # UnboundLocalError，看着像代码坏了，实际是"这个 ID 取不到曲目"。
        if isinstance(e, UnboundLocalError):
            return [], "歌单里没取到任何曲目（链接里的歌单 ID 可能不对，或该平台需要 Cookie/登录）"
        return [], _net_err_cn(e)
    out = []
    for song in songs or []:
        src = str(getattr(song, "source", None) or source)
        out.append(_songinfo_to_dict(song, src))
    return out, ""


# ------------------------------------------------- Spotify 大歌单：只列曲目
# musicdl 的 Spotify 源把"取地址"塞在解析阶段：每首都去 spotubedl 那类第三方接口跑一遍，
# 还把整首歌的字节先拉下来（modules/sources/spotify.py::_parsewithspotubedlapi）。
# 196 首就是 196 轮，900s 预算必然爆掉，用户最后只看到"0 首"。
# 可"这张歌单里有哪些歌"根本不需要取地址 —— Spotify 自己的 pathfinder 公开接口（免登录）
# 一次请求就带回整张歌单的标题/歌手/时长/封面。于是解析阶段只列曲目，音频地址推到用户
# 真的勾了下载之后，再按曲名去别的平台匹配（见下面的 resolve_placeholders）。

SPOTIFY_PAGE_SIZE = 300
SPOTIFY_LIST_LIMIT = 1000
SPOTIFY_LIST_BUDGET = 240
# persisted-query 的 sha256 要下完整个 web-player JS 包才搜得到（本机实测 ~45s），而它只跟
# Spotify 的前端版本走 —— 缓存住，翻页和第二张歌单就不必再付这笔钱。
SPOTIFY_HASH_TTL = 6 * 3600
_SPOTIFY_HASH: Dict[str, Any] = {"value": "", "ts": 0.0}

# 默认匹配源：这几个平台的地址是自己家的 CDN，搜到就能下、几秒一首。Spotify/Apple 并非取不到
# 地址（musicdl 走第三方转链，单曲实测能下），只是每首约十秒且时常失败，所以不进默认、只作可选。
TRACK_MATCH_SOURCES = ["NeteaseMusicClient", "QQMusicClient", "MiguMusicClient",
                       "KugouMusicClient", "KuwoMusicClient"]
TRACK_MATCH_BUDGET = 1500
# Spotify/Apple 的音频地址要经第三方转链才拿得到，一首约十秒；1500s 只够搜几十首，后半程
# 整批落在「本轮没轮到搜」里。勾了这两个源时整轮预算放宽到 3000s。
TRACK_MATCH_BUDGET_RELAY = 3000
TRACK_MATCH_WORKERS = 3
# 时长容差：曲名+歌手都对上时，过去一律放宽 60s，可 30 秒的单曲跟 90 秒的版本也能算"同一首"。
# 改成绝对值与比例两者取严，再留一个下限容纳平台间固有的尾差/编码差。
TRACK_DUR_TOL_ABS = 60
TRACK_DUR_TOL_PCT = 0.12
TRACK_DUR_TOL_FLOOR = 20
# 只对上曲名、歌手不同（含歌手字段写法差异）时，时长必须几乎一致才敢认
TRACK_DUR_TOL_STRICT = 5
# 一次 client.download() 是阻塞的，整批 50 首要十几分钟且中途一个文件都不落最终目录 —— 用户
# 只能看到"没反应"。切成小片，每片下完立刻归档到模板路径，文件页马上能看到成品。
DOWNLOAD_CHUNK = 6


def _spotify_playlist_id(url: str) -> str:
    """取 /playlist/<id>；intl-ja 这类前缀路径也在里面。取不到说明链接指的不是歌单页。"""
    from urllib.parse import urlparse
    segs = [s for s in (urlparse(url).path or "").split("/") if s]
    for i, seg in enumerate(segs[:-1]):
        if seg == "playlist":
            return segs[i + 1]
    return ""


def _spotify_hash(session: Any, js_pack: str, ovr: dict, force: bool = False) -> str:
    from musicdl.modules.utils.spotifyutils import SpotifyMusicClientPlaylistUtils as PU
    now = time.time()
    if not force and _SPOTIFY_HASH["value"] and now - _SPOTIFY_HASH["ts"] < SPOTIFY_HASH_TTL:
        return _SPOTIFY_HASH["value"]
    try:
        h = str(PU.getsha256hash(session, js_pack, request_overrides=ovr) or "")
    except Exception:
        h = ""
    if h:
        _SPOTIFY_HASH["value"], _SPOTIFY_HASH["ts"] = h, now
    return h


def _spotify_fetch_page(session: Any, tokens: dict, sha: str, playlist_id: str,
                        offset: int, limit: int, ovr: dict) -> dict:
    """报文照抄 musicdl 的 fetchplaylist，只把指纹改成参数 —— 缓存和过期重算才插得进去
    （它自己每页都现算一次，翻页就成了每页 45s）。
    """
    from musicdl.modules.utils.spotifyutils import SpotifyMusicClientUtils as SU
    payload = {
        "operationName": "fetchPlaylist",
        "variables": {"uri": f"spotify:playlist:{playlist_id}", "offset": offset,
                      "limit": limit, "enableWatchFeedEntrypoint": False},
        "extensions": {"persistedQuery": {"version": 1, "sha256Hash": sha}},
    }
    headers = {
        "User-Agent": SU.COMMON_HEADERS.get("User-Agent", "Mozilla/5.0"),
        "Sec-Ch-Ua": SU.COMMON_HEADERS.get("Sec-Ch-Ua", ""),
        "Authorization": f"Bearer {tokens['access']}",
        "Client-Token": tokens["client"],
        "Spotify-App-Version": tokens["version"],
        "Content-Type": "application/json;charset=UTF-8",
    }
    r = session.post("https://api-partner.spotify.com/pathfinder/v2/query", headers=headers,
                     json=payload, timeout=(6, 30), **ovr)
    r.raise_for_status()
    return r.json() or {}


def _spotify_track_fields(entry: dict) -> dict:
    """pathfinder 的一行曲目 → 我们的条目 dict。不是歌（播客单集、有声书）返回 {}。"""
    data = ((entry or {}).get("itemV2") or {}).get("data") or \
           ((entry or {}).get("item") or {}).get("data") or {}
    if not isinstance(data, dict) or str(data.get("__typename") or "Track") != "Track":
        return {}
    title = str(data.get("name") or "").strip()
    if not title:
        return {}
    artists = ", ".join([
        str(((a or {}).get("profile") or {}).get("name") or "").strip()
        for a in ((data.get("artists") or {}).get("items") or [])
        if ((a or {}).get("profile") or {}).get("name")
    ])
    album_obj = data.get("albumOfTrack") or {}
    dur = data.get("trackDuration") or data.get("duration") or {}
    ms = (dur or {}).get("totalMilliseconds") or 0
    covers = (album_obj.get("coverArt") or {}).get("sources") or []
    cover = ""
    if covers:
        try:
            cover = str(max(covers, key=lambda c: int(c.get("width") or 0)).get("url") or "")
        except Exception:
            cover = str((covers[0] or {}).get("url") or "")
    # musicdl 只在 parse 里补 song_link，我们自己翻页时没有，只能从 uri/id 拼
    page_url = str((entry or {}).get("song_link") or "")
    if not page_url:
        tid = str(data.get("id") or "").strip()
        if not tid:
            uri = str(data.get("uri") or "")
            parts = uri.split(":")
            tid = parts[2] if uri.startswith("spotify:track:") and len(parts) > 2 else ""
        if tid:
            page_url = f"https://open.spotify.com/track/{tid}"
    return {
        "id": "",
        "title": title,
        "artists": artists,
        "album": str(album_obj.get("name") or ""),
        "duration": _hms(ms),
        "duration_s": _dur_seconds(float(ms or 0) / 1000),
        "source": "Spotify",
        # 界面来源列不能光写 Spotify：这一行没有音频地址，曲子是下载时按曲名去别的平台取的
        "real_source": "Spotify（无官方音频）",
        "unofficial": True,
        "musicdl_source": "SpotifyMusicClient",
        # 留空：Spotify 那条是歌单网页地址，拿去给 yt-dlp 只会被按 DRM 拒收。
        # 音频地址要等下载时按曲名在 TRACK_MATCH_SOURCES 里匹配到才拿得到。
        "url": "",
        "page_url": page_url,
        "quality": "",
        "cover": cover,
        "can_musicdl_download": False,
        "needs_match": True,
    }


def list_spotify_playlist(url: str, *, proxy: str = "", log: Callable = print,
                          limit: int = SPOTIFY_LIST_LIMIT) -> tuple:
    """免登录列出 Spotify 歌单曲目。返回 (曲目, 歌单名, 错误原因)；只查元数据，不碰音频地址。"""
    pid = _spotify_playlist_id(url)
    if not pid:
        return [], "", "链接里没有 /playlist/<id>，不是 Spotify 歌单页"
    try:
        import requests
        from musicdl.modules.utils.spotifyutils import SpotifyMusicClientUtils as SU
    except Exception as e:
        return [], "", f"musicdl 不可用：{type(e).__name__}: {e}"
    ovr: Dict[str, Any] = {"verify": False}
    prx = _proxies_of(proxy)
    if prx:
        ovr["proxies"] = prx
    session = requests.Session()
    try:
        sd = SU.getsessiondata(session, request_overrides=ovr)
        secret = SU.getlatesttotpsecret()
        tok = SU.getaccesstoken(session, SU.generatetotp(secret["secret"]), secret["version"],
                                request_overrides=ovr)
        access = str(tok.get("accessToken") or "")
        if not access:
            return [], "", "Spotify 没发访问令牌（多半是被限流，稍后再试或换个代理节点）"
        version = str(sd.get("clientVersion") or "")
        tokens = {
            "access": access, "version": version,
            "client": str(SU.getclienttoken(session, version, tok.get("clientId") or "",
                                            sd.get("deviceId") or "",
                                            request_overrides=ovr) or ""),
        }
    except Exception as e:
        return [], "", f"连不上 Spotify 的公开接口：{_net_err_cn(e)}"

    tried: set = set()
    for attempt in (1, 2):
        sha = _spotify_hash(session, str(sd.get("jsPack") or ""), ovr, force=(attempt == 2))
        if not sha or sha in tried:
            break
        tried.add(sha)
        items: List[dict] = []
        name, total, offset, stale = "", 0, 0, False
        try:
            while offset < min(max(1, int(limit)), SPOTIFY_LIST_LIMIT):
                page = _spotify_fetch_page(session, tokens, sha, pid, offset,
                                           min(SPOTIFY_PAGE_SIZE, int(limit) - offset), ovr)
                pl = (page.get("data") or {}).get("playlistV2") or {}
                if page.get("errors") and not pl:
                    stale = True
                    break
                content = pl.get("content") or {}
                name = name or str(pl.get("name") or "")
                try:
                    total = int(content.get("totalCount") or 0) or total
                except (TypeError, ValueError):
                    pass
                rows = content.get("items") or []
                offset += len(rows)
                for row in rows:
                    d = _spotify_track_fields(row)
                    if d:
                        items.append(d)
                if not len(rows) or (total and offset >= total):
                    break
        except Exception as e:
            return items, name, f"Spotify 歌单接口出错：{_net_err_cn(e)}"
        if not stale:
            if not items:
                return [], name, ("Spotify 认这张歌单，但里面没有可下载的歌"
                                  "（空歌单，或全是播客单集/有声书）")
            for it in items:
                it["id"] = _cache_song(it)     # 占位条目也进缓存：下载时才换成真 SongInfo
            log(f"Spotify 歌单「{name or pid}」共 {total or len(items)} 首，列出 {len(items)} 首")
            return items, name, ""
        _SPOTIFY_HASH["value"] = ""            # 接口说指纹不对（Spotify 刚发过版）→ 重算再来
    return [], "", "Spotify 接口指纹取不到（它的前端刚改版，或被代理节点干扰），列不出曲目"


def _dur_close(want_dur: int, got_dur: int) -> bool:
    """两个时长算不算「同一首歌」级别的接近；缺一侧时长就不参与判断。"""
    if not want_dur or not got_dur:
        return True
    tol = min(TRACK_DUR_TOL_ABS,
              max(TRACK_DUR_TOL_FLOOR, round(want_dur * TRACK_DUR_TOL_PCT)))
    return abs(want_dur - got_dur) <= tol


def _track_norm(s: Any) -> str:
    """轻量归一：只抹平大小写、全角括号、空白和逗号/斜杠旁的空格。

    这里故意不用 _norm_text —— 它会连括注和「live / 现场 / 伴奏」这类版本词一起剥掉，
    那录音室版和现场版就成了"同名"，合并后其中一版会直接从列表里消失。
    """
    import re
    s = _to_simplified(str(s if s is not None else "").strip().lower())
    s = s.replace("（", "(").replace("）", ")")
    s = re.sub(r"\s+", " ", s)
    return re.sub(r"\s*([,/、])\s*", r"\1", s)


def _track_key(item: Any) -> str:
    """曲名 + 排序后的歌手；曲名为空返回空串，表示这行不参与合并。"""
    import re
    title = _track_norm(_song_field(item, "song_name", "title", "name"))
    if not title:
        return ""
    v = _song_field(item, "singers", "artists", "artist")
    parts = (list(v) if isinstance(v, (list, tuple))
             else re.split(r"[/,，、;；&]", str(v or "")))
    arts = ",".join(sorted(a for a in (_track_norm(x) for x in parts) if a))
    return f"{title}|{arts}"


def _track_dur_s(item: Any) -> int:
    return _dur_seconds(_song_field(item, "duration_s") or _song_field(item, "duration"))


def _track_clusters(items: list) -> List[List[int]]:
    """把一排曲目归成「同一首歌」的组，返回每组在原列表里的下标，组内第一个是保留行。

    判重口径与下载匹配一致：曲名+歌手相同，再要时长落在 _dur_close 容差内 —— 现场版、
    重制版同名但时长差得远，不能当成一首。缺时长的一侧（列表只给了歌名）仍与同名合并。
    给下标而不是给条目本身：调用方手上往往是 cache id 列表，要能把保留项对齐回那个 id。
    """
    items = items or []
    groups: List[List[int]] = []
    keys: List[str] = []
    durs: List[int] = []
    for idx, it in enumerate(items):
        key = _track_key(it)
        if not key:
            groups.append([idx])
            keys.append("")
            durs.append(0)
            continue
        dur = _track_dur_s(it)
        for gi, gk in enumerate(keys):
            if gk == key and _dur_close(durs[gi], dur):
                groups[gi].append(idx)
                break
        else:
            groups.append([idx])
            keys.append(key)
            durs.append(dur)
    return groups


def merge_duplicate_tracks(items: list, log: Optional[Callable] = None) -> list:
    """列表合并：同一首歌排了两遍，界面只留一行并标 ×N，下载也只下一遍。"""
    items = list(items or [])
    groups = _track_clusters(items)
    dup_rows = [g for g in groups if len(g) > 1]
    if not dup_rows:
        return items
    for g in dup_rows:
        row = items[g[0]]
        if isinstance(row, dict):
            row["dup_count"] = len(g)
        else:
            try:
                row.dup_count = len(g)      # type: ignore[attr-defined]
            except Exception:
                pass
    if log:
        n = sum(len(g) - 1 for g in dup_rows)
        log(f"歌单里有 {n} 首与前面的重复（同一首歌被加过多次），已合并成一行，下载只下一遍")
    return [items[g[0]] for g in groups]


def drop_duplicate_tracks(items: list) -> tuple:
    """下载入口的兜底：清单里排了两遍的歌只留第一遍，返回 (保留下标集合, 被跳过清单)。"""
    groups = _track_clusters(items)
    kept = {g[0] for g in groups}
    skipped = [{"title": str(_song_field(items[g[0]], "song_name", "title", "name") or "").strip()
                        or "（无曲名）",
                "count": len(g)} for g in groups if len(g) > 1]
    return kept, skipped


# ---- 同曲打分闸门的参数 ----------------------------------------------------
# 做法借鉴 spotDL 的匹配模块（spotdl/utils/matching.py，MIT 许可），阈值按中文曲库另定。
MATCH_NAME_MIN = 60       # 曲名相似度下限：低于它就是两首歌
MATCH_ARTIST_MIN = 70     # 歌手相似度下限：华语同名翻唱太多，这一维最值钱
MATCH_TIME_MIN = 25       # 时长相似度下限（约等于差 14 秒）
MATCH_TIME_SOFT = 50      # 曲名不完全相同时要求的时长下限（约等于差 7 秒）
MATCH_ACCEPT = 85         # 录取线：过了才算「同一首」

# 出现这些字样就说明是另一版录音，不是歌单上标注的那一条
VERSION_TAGS = ("live", "现场", "演唱会", "concert", "unplugged", "不插电", "acoustic",
                "伴奏", "纯音乐", "instrumental", "karaoke", "remix", "重混", "dj",
                "slowed", "加速", "加快", "慢速", "翻唱", "cover", "demo", "小样",
                "试听", "片段", "预告", "清唱", "a cappella")


def _version_tags(raw: Any):
    """这条曲名里带了哪些版本词。英文词按边界找，免得 "adjust" 里冒出个 "dj"。"""
    import re
    s = _to_simplified(str(raw or "")).lower()
    hit = set()
    for w in VERSION_TAGS:
        if re.fullmatch(r"[a-z' ]+", w):
            if re.search(r"(?<![a-z])" + re.escape(w) + r"(?![a-z])", s):
                hit.add(w)
        elif w in s:
            hit.add(w)
    return frozenset(hit)


def _sim_ratio(a: str, b: str) -> float:
    """0~100 的相似度：中文字符级比，再补一次乱序比对，最后按长度比例封顶。

    封顶是必须的：「莫问归期」整头含着「归期」，不封顶就能冒充同一首歌。
    """
    from difflib import SequenceMatcher
    if not a or not b:
        return 0.0
    if a == b:
        return 100.0
    best = SequenceMatcher(None, a, b).ratio() * 100
    best = max(best, SequenceMatcher(None, "".join(sorted(a)), "".join(sorted(b))).ratio() * 100)
    sa, sb = set(a), set(b)
    best = max(best, len(sa & sb) / len(sa | sb) * 100)
    best = min(best, 100.0 * min(len(a), len(b)) / max(len(a), len(b)))
    return round(min(100.0, best), 1)


def _time_score(want_dur: int, got_dur: int) -> Optional[float]:
    """时长的相似度：差 0s=100、差 7s≈50、差 14s≈25。缺一侧时长返回 None（不参与判断）。"""
    from math import exp
    if not want_dur or not got_dur:
        return None
    return round(min(100.0, exp(-0.1 * abs(want_dur - got_dur)) * 100), 1)


def _artist_list(raw: Any) -> List[str]:
    """把歌手串切成归一后的名字列表；括号和 feat./ft. 这类合作标记先劈开。"""
    import re
    s = _to_simplified(str(raw or ""))
    s = re.sub(r"(?i)(feat\.?|ft\.?|featuring|with|合作)", " ", s)
    return [t for t in (_norm_text(x) for x in re.split(r"[/,，、;；&()（）\-]", s)) if t]


def _score_artists(want_raw: Any, cand_raw: Any) -> float:
    """歌手维度的相似度。缺一侧歌手名就返回 100 —— 判不了就不拿这一维卡人。"""
    from difflib import SequenceMatcher
    wa, ca = _artist_list(want_raw), _artist_list(cand_raw)
    if not wa or not ca:
        return 100.0
    if sorted(wa) == sorted(ca):
        return 100.0
    if all(any(w == c or w in c or c in w for c in ca) for w in wa):
        return 95.0        # 标注里的歌手在成品里全找得着（「周杰伦」↔「周杰伦, Jay Chou」）
    def _ratio(x, y):
        return SequenceMatcher(None, x, y).ratio() * 100
    main = max((_ratio(w, c) for w in wa[:2] for c in ca[:2]), default=0.0)
    per = sum(max(_ratio(w, c) for c in ca) for w in wa) / len(wa)
    return round(min(100.0, max(main, per)), 1)


def _pick_track_match(want: dict, cands: List[dict],
                      notes: Optional[List[str]] = None,
                      require_artist: bool = False,
                      quality_spec: Any = None) -> dict:
    """从一次搜索结果里挑「就是这首歌」的那条 —— 逐条打分，取过线的最高分。

    判定口径借鉴 spotDL 的匹配模块（`spotdl/utils/matching.py`，MIT）：曲名、歌手、时长分开打分，
    再过几条硬阈值，任何一条不过就不算同一首；这里只借做法，阈值按中文曲库另定。
    两条老的快捷判定保留：曲名+歌手归一后完全相同（时长只要在容差内）和同名但歌手写法不同时
    相差不到 5 秒 —— 收紧成纯打分把它们都判丢过，那两种是实际能下对的。
    给 notes 就把被拒原因写进去，上层那句「没找到」才说得出是被哪一维挡的。

    quality_spec 只改「几条都过线时选哪一条」：达标的排前面，判不了档位的居中，明确不达标的垫底；
    只有要求里勾了「不达标不下」才把不达标的候选整条挡掉。没提要求时排序与原来完全一致。
    """
    spec = norm_quality_spec(quality_spec)
    use_spec = quality_spec_active(spec)
    best: Optional[dict] = None
    best_key: tuple = ()
    for c in cands or []:
        if not isinstance(c, dict):
            continue
        sc = track_score(want, c, require_artist=require_artist)
        why = sc["reject"]
        if not why and sc["score"] < MATCH_ACCEPT:
            why = (f"最像的一条只有 {sc['score']:.0f} 分（曲名 {sc['name']:.0f}"
                   f"/歌手 {sc['artist']:.0f}），没到 {MATCH_ACCEPT} 分录取线")
        qa = quality_against_spec(row_audio_facts(c), spec) if use_spec else None
        if not why and qa is not None and qa["state"] == "low" and spec["strict"]:
            label = (str(c.get("title") or "") or "（无曲名）")[:20]
            why = f"「{label}」是同一首歌但{qa['note']}（已勾「不达标不下」）"
        if why:
            if notes is not None and len(notes) < 4:
                notes.append(why)
            continue
        # 达标 > 判不了 > 明确不达标：判不了不卡人，但也不能让它压过一条确认达标的
        rank = 0 if qa is None else {"ok": 2, "unknown": 1, "low": 0}.get(qa["state"], 1)
        key = (sc["score"], rank, _quality_score(str(c.get("quality") or "")))
        if best is None or key > best_key:
            best, best_key = c, key
    return best or {}


def track_score(want: dict, cand: dict, *, require_artist: bool = False) -> dict:
    """给「搜索结果里的这一条是不是歌单上的那一首」打分。

    返回 score（综合分）、name/artist/time（三个维度）、reject（被硬挡下来的理由，空串表示没被挡）。
    缺哪一侧的数据就不拿那一侧卡人：没时长就只按曲名+歌手判，缺歌手名同理。
    require_artist 是给「下载目录里已经有这一首」用的：那里同名不同人多半真是两版录音（原版与翻唱），
    不能只看曲名相同、时长差不多就认同一首；跨平台找歌时仍按老口径，歌手写法常不同。
    """
    want_title = str(want.get("title") or "")
    cand_title = str(cand.get("title") or "")
    w_norm = _norm_text(want_title)
    c_norm = _norm_text(cand_title)
    want_dur = int(want.get("duration_s") or 0) or _dur_seconds(want.get("duration"))
    got_dur = int(cand.get("duration_s") or 0) or _dur_seconds(cand.get("duration"))
    t_score = _time_score(want_dur, got_dur)
    # 只有「成品比标注多出版本词」才当另一版录音：歌单标了 Live 而曲库这条没写后缀，多半就是
    # 同一条录音（曲库常省后缀），那个方向不拦。反过来放过去就等于给用户库里塞一条现场版。
    extra_ver = _version_tags(cand_title) - _version_tags(want_title)
    name = 100.0 if (w_norm and w_norm == c_norm) else _sim_ratio(w_norm, c_norm)
    artist = _score_artists(want.get("artists"), cand.get("artists"))
    same_song = bool(w_norm) and _song_fingerprint(want) == _song_fingerprint(cand)
    out = {"score": 0.0, "name": name, "artist": artist, "time": t_score, "reject": ""}
    diff = abs(want_dur - got_dur) if want_dur and got_dur else 0

    def reject(why: str) -> dict:
        out["reject"] = why
        return out

    if same_song and not extra_ver and _dur_close(want_dur, got_dur):
        out["score"] = 100.0
        return out
    if not extra_ver and w_norm and w_norm == c_norm and want_dur and got_dur \
            and diff <= TRACK_DUR_TOL_STRICT \
            and (not require_artist or artist >= MATCH_ARTIST_MIN):
        out["score"] = 96.0
        return out
    label = (cand_title or want_title)[:20] or "（无曲名）"
    if extra_ver:
        return reject(f"「{label}」成品标了{'、'.join(sorted(extra_ver))}，与标注的不是同一版录音")
    if same_song:
        return reject(f"「{label}」时长差 {diff}s，超出容差")
    if not w_norm:
        return reject("歌单这一行没有曲名，无法比对")
    if name <= MATCH_NAME_MIN:
        return reject(f"曲名「{label}」与「{want_title[:20]}」不像同一首（相似度 {name:.0f}）")
    if artist < MATCH_ARTIST_MIN:
        if w_norm == c_norm:
            return reject(f"同名「{label}」歌手不同" + (f"、时长差 {diff}s" if diff else ""))
        return reject(f"「{label}」歌手对不上（相似度 {artist:.0f}）")
    if t_score is not None:
        if t_score < MATCH_TIME_MIN:
            return reject(f"「{label}」时长差 {diff}s，不可能是同一版")
        if w_norm != c_norm and t_score < MATCH_TIME_SOFT:
            return reject(f"「{label}」曲名不完全相同、时长又差 {diff}s，不算同一首")
    # 时长只当闸门、不当加分项：两首不同的歌恰好同长太常见，让它参与加分会把不像的抬进来
    out["score"] = min(100.0, (name + artist) / 2)
    return out


def _resolve_placeholder(cid: str, item: dict, *, srcs: List[str], work_dir: str,
                         cookies: str, proxy_for: Optional[Callable[[str], str]],
                         st: dict, rejects: Optional[dict] = None,
                         quality_spec: Any = None) -> str:
    """按「歌手 + 曲名」在别的平台找同一首歌，找到就把缓存里的占位换成真 SongInfo。

    quality_spec 只影响「几条都判定为同一首时选哪一条」，不改变是不是同一首的判定。
    """
    query = f"{str(item.get('artists') or '').strip()} {str(item.get('title') or '').strip()}".strip()
    if not query:
        return ""
    notes: List[str] = []
    for src in srcs:
        try:
            songs, _errs = _search_one_source(
                src, query, st=st, work_dir=work_dir, cookies=cookies,
                proxy=_source_proxy(src, "", proxy_for),
            )
        except Exception:
            continue
        hit = _pick_track_match(item, songs, notes, quality_spec=quality_spec)
        if not hit:
            continue
        real = get_cached_song(str(hit.get("id") or ""))
        if real is None:
            continue
        # 真结果来自另一个平台的搜索，没有"这首歌在原歌单里排第几"的概念 —— 把占位行上的序号搬过去
        carry_archive_fields(item, real)
        set_cached_song(cid, real)
        return src.replace("MusicClient", "")
    if rejects is not None and notes:
        rejects[cid] = notes[:2]
    return ""


def pick_play_url(song: Any) -> str:
    """从一行结果里挑出可以直接播/探测的地址（试听与换源探测共用这一份口径）。"""
    names = ("download_url", "song_url", "play_url", "url", "music_url",
             "audio_url", "listen_url")
    if song is None:
        return ""
    for n in names:
        v = song.get(n) if isinstance(song, dict) else getattr(song, n, None)
        if v and str(v).startswith("http"):
            return str(v)
    raw = song.get("raw_data") if isinstance(song, dict) else getattr(song, "raw_data", None)
    if isinstance(raw, dict):
        for key in ("download", "play", "url", "musicUrl", "music_url"):
            sub = raw.get(key)
            if isinstance(sub, dict):
                u = sub.get("url") or sub.get("path") or sub.get("play_url")
                if u and str(u).startswith("http"):
                    return str(u)
            elif sub and str(sub).startswith("http"):
                return str(sub)
    return ""


def switch_song_source(cid: str, *, sources: List[str], work_dir: str, cookies: str = "",
                       proxy_for: Optional[Callable[[str], str]] = None,
                       current_source: str = "", st: Optional[dict] = None) -> dict:
    """给一行结果换一条来路：在给定源里按打分闸门找更像的那一条，换掉缓存里那一行并探一次可播。

    找到才会改写缓存（之后勾选下载用的就是新来路）；找不到保持原样，把被哪一维挡的回填进 reason。
    """
    song = get_cached_song(cid)
    if song is None:
        return {"ok": False, "reason": "缓存里查不到这一行（页面重新搜索后再试）"}
    want = want_from_song(song)
    if not want["title"]:
        return {"ok": False, "reason": "这一行没有曲名，无法与其他平台的结果比对"}
    cur = str(current_source or "").strip()
    cur_full = cur if "Client" in cur else (f"{cur}MusicClient" if cur else "")
    srcs = [s for s in canonical_sources(sources or []) if s != cur_full]
    if not srcs:
        return {"ok": False, "reason": "没有可换的源（候选源里只剩当前这一个）"}
    rejects: Dict[str, List[str]] = {}
    st = _merge_strategy(st or {})
    st.update({"mode": "sequential", "search_size": 8, "max_retries": 1,
               "connect_timeout": 4, "read_timeout": 10})
    proxy = ""
    to = _resolve_placeholder(cid, want, srcs=srcs, work_dir=work_dir, cookies=cookies,
                             proxy_for=proxy_for or (lambda _s: proxy), st=st, rejects=rejects)
    out = {"ok": False, "from": str(current_source or ""), "to": to,
           "title": want["title"], "reason": "", "score": 0}
    if not to:
        notes = rejects.get(cid) or []
        out["reason"] = ("其他源里没有过闸门的结果"
                         + ("：" + "；".join(notes) if notes else ""))
        return out
    new = get_cached_song(cid)
    if new is None:
        out["reason"] = "换源后取不到结果，清单已保持原样"
        out["to"] = ""
        return out
    # 不能拿 _songinfo_to_dict 造这一行：它会 _cache_song 另铸一个 uuid，界面上这一行的 id
    # 就和缓存里被换掉的那条对不上号，之后勾选下载会直接「缓存失效」。
    src_full = str(song_field(new, "source") or to)
    if not src_full.endswith("Client"):
        src_full = f"{src_full}MusicClient" if src_full else to
    org = audio_origin(new)
    row = {
        "title": song_field(new, "song_name", "title", "name"),
        "artists": song_field(new, "singers", "artists", "artist"),
        "album": song_field(new, "album"),
        "duration": song_field(new, "duration"),
        "duration_s": _dur_seconds(song_field(new, "duration_s") or song_field(new, "duration")),
        "url": pick_play_url(new),
        "cover": song_field(new, "cover_url", "album_pic", "cover"),
        "quality": song_field(new, "ext", "quality"),
        "source": src_full.replace("MusicClient", "").replace("Client", ""),
        "musicdl_source": src_full,
        "real_source": org.get("label") or "",
        "unofficial": bool(org.get("unofficial")),
        "can_musicdl_download": True,
    }
    out["score"] = round(track_score(want, row)["score"])
    out["row"] = row
    url = row["url"]
    if url:
        try:
            pr = range_probe(url)
            out["size"] = pr.get("size") or 0
            out["accept_ranges"] = bool(pr.get("accept_ranges"))
        except Exception as e:
            out["probe_error"] = str(e)[:120]
    out["ok"] = True
    return out


def log_name_list(log: Callable, header: str, names: List[str],
                   level: str = "warning", per_line: int = 10) -> None:
    """整份名单全部上屏。以前只报前 12 首，用户照着核以为就少这几首，实际还差着一串。"""
    log(f"{header}：", level)
    for i in range(0, len(names), max(1, int(per_line))):
        log("、".join(names[i:i + max(1, int(per_line))]), level)


MUSIC_AUDIO_EXTS = (".mp3", ".flac", ".m4a", ".aac", ".ogg", ".wav", ".opus", ".webm")


def song_field(song: Any, *names: str) -> str:
    """从 SongInfo 对象或占位 dict 里取第一个非空字段（列表按 `, ` 拼）。"""
    for n in names:
        v = song.get(n) if isinstance(song, dict) else getattr(song, n, None)
        if v not in (None, ""):
            if isinstance(v, (list, tuple)):
                return ", ".join(str(a) for a in v)
            return str(v)
    return ""


def want_from_song(song: Any) -> dict:
    """把一行结果（SongInfo 对象或占位 dict）归一成打分闸门要的比对样本。"""
    # 占位条目（歌单只列出曲名那种）时长直接记在 duration_s 上，真 SongInfo 才是 "3:22" 这种字符串
    dur = _dur_seconds(song_field(song, "duration_s"))
    if not dur:
        dur = _dur_seconds(song_field(song, "duration", "song_duration", "length"))
    return {
        "title": song_field(song, "song_name", "title", "name").strip(),
        "artists": song_field(song, "singers", "artists", "artist").strip(),
        "duration_s": dur,
        "quality": song_field(song, "quality"),
    }


def find_existing_local_songs(wants: List[dict], root: str, *, log: Callable = print) -> List[tuple]:
    """下载目录里是否**已经有这一首** —— 按同曲打分闸门判，不按文件名。

    文件名判重在两处会失灵：同一首歌在不同平台的文件名写法不同（歌手分隔符、扩展名），
    以及改了命名模板之后老成品对不上号。这两种都会让「跳过已下载」形同虚设，
    同一首隔几天再下一份，最后落成套 `_1` 副本。
    判不出来的行（没有曲名、目录里没有音频）一律放行，不拦下载。
    这里传 ``ttl=0`` 强制当场重扫：刚下完的那首不能被上次那份旧索引遮住，否则隔天又下一份套 `_1` 的副本。
    返回 [(下标, 已有文件路径, 分数, 已有曲名)]。
    """
    rows = [r for r in local_music_snapshot(root, log=log, ttl=0)
            if str(r.get("title") or "").strip()]
    if not rows:
        return []
    pool_all: List[dict] = []
    for r in rows:
        pool_all.append(r)
        # 没有标签的行，曲名是按文件名猜的：下载器的默认模板是「曲名 - 歌手」，
        # 文件名兜底却按「歌手 - 曲名」拆，方向正好相反。再投一份对调的候选，
        # 否则同一首成品认不出来，隔几天又下一份。带标签的行方向可信，不必翻倍。
        if not r.get("tagged") and str(r.get("artists") or "").strip():
            pool_all.append({**r, "title": r["artists"], "artists": r["title"]})
    out: List[tuple] = []
    for i, w in enumerate(wants or []):
        if not w or not str(w.get("title") or "").strip():
            continue
        want_dur = int(w.get("duration_s") or 0)
        # 两侧都有时长时先按时长削候选：整目录逐条跑相似度会把这个判断拖成十几秒
        pool = [r for r in pool_all
                if not want_dur or _dur_close(want_dur, int(r.get("duration_s") or 0))]
        if not pool:
            continue
        hit = _pick_track_match(w, pool, require_artist=True)
        if hit.get("path"):
            out.append((i, str(hit["path"]),
                        round(track_score(w, hit, require_artist=True)["score"]),
                        str(hit.get("title") or "")))
    return out


def promote_music_file(src: Any, dest: Any, log: Callable = print) -> Any:
    """把成品挪到模板算出的目标路径并返回该路径。

    目标已经有一份时**整只替换**并写明新旧字节数，绝不另存 `曲名_1.mp3` —— 同名就是同一首，
    留两份正是用户说的「重复下载」。
    """
    from pathlib import Path as _P
    src, dest = _P(str(src)), _P(str(dest))
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        try:
            old_n, new_n = dest.stat().st_size, src.stat().st_size
        except OSError:
            old_n = new_n = -1
        log(f"{dest.name}：目录里已经有一份（{old_n} 字节），这次这份 {new_n} 字节，"
            "已用这次的替换，没有另存副本")
    src.replace(dest)
    return dest


def resolve_placeholders(pairs: List[tuple], *, sources: Optional[List[str]] = None,
                         work_dir: str = "", cookies: str = "", proxy: str = "",
                         proxy_for: Optional[Callable[[str], str]] = None,
                         log: Callable = print,
                         report: Optional[dict] = None,
                         quality_spec: Any = None) -> int:
    """把"只有曲名"的占位条目就地换成能下载的那条。返回命中条数。pairs 是 [(cache_id, dict)]。

    这一步只在用户真的勾了下载时才跑 —— 解析阶段谁都不该为用不上的歌付取址时间。

    report 传字典时回填本轮结论（missed / unsearched / budget），界面对完账要列清单。
    quality_spec 是界面上的「音质要求」：同一首歌在几个源里档位不同时优先取达标的那条。
    """
    from concurrent.futures import CancelledError, ThreadPoolExecutor, as_completed
    # 匹配源就按用户勾的原样用，不再替用户否决平台：Spotify/Apple 的取址要经第三方转链
    # （musicdl 的 spotify.py 每首打 spotubedl / spotisaver 一类接口，把整首字节拉回内存），
    # 慢且常失败，但并非"给不了音频地址"。只有完全没指定时才回落，且必须写明。
    srcs = canonical_sources(sources or [])
    if not srcs:
        srcs = list(TRACK_MATCH_SOURCES)
        log("没指定匹配源，已回落到默认匹配源："
            f"{'、'.join(s.replace('MusicClient', '') for s in srcs)}", "warning")
    relay = [s.replace('MusicClient', '') for s in srcs
             if s in ("SpotifyMusicClient", "AppleMusicClient")]
    budget = TRACK_MATCH_BUDGET_RELAY if relay else TRACK_MATCH_BUDGET
    if relay:
        log(f"匹配源含 {'、'.join(relay)}：这两个源要经第三方转链取址，"
            f"每首约十秒且时常失败，整单会明显变慢（整轮预算放宽到 {budget}s）")
    st = _merge_strategy({})
    st.update({"mode": "sequential", "search_size": 8, "max_retries": 1,
               "connect_timeout": 4, "read_timeout": 10})
    total = len(pairs)
    log(f"开始按曲名匹配 {total} 首：{'/'.join(s.replace('MusicClient', '') for s in srcs)}"
        f"（每首搜到就停，整轮最长 {budget}s）")
    spec_label = quality_spec_label(quality_spec)
    if spec_label:
        log(f"本次音质要求：{spec_label}"
            + ("，同一首歌有多个候选时优先取达标的那条；全都不达标就不下这一首"
               if norm_quality_spec(quality_spec)["strict"]
               else "，同一首歌有多个候选时优先取达标的那条；全都不达标则按最高音质取"))
    titles = {cid: str(item.get("title") or "?") for cid, item in pairs}
    hit_ids: set = set()
    hit_srcs: Dict[str, int] = {}
    done = 0
    timed_out = False
    unsearched: set = set()   # 预算用尽时被取消、本轮根本没搜的曲目
    rejects: Dict[str, List[str]] = {}   # cid → 候选被拒的原因（时长差 / 同名不同人）
    with ThreadPoolExecutor(max_workers=TRACK_MATCH_WORKERS) as pool:
        futs = {
            pool.submit(_resolve_placeholder, cid, item, srcs=srcs, work_dir=work_dir,
                        cookies=cookies, proxy_for=proxy_for or (lambda _s: proxy), st=st,
                        rejects=rejects, quality_spec=quality_spec): cid
            for cid, item in pairs
        }
        started = time.time()
        for fut in as_completed(futs):
            cid = futs[fut]
            done += 1
            skipped_this_round = False
            try:
                src = str(fut.result() or "")
            except CancelledError:
                # 预算用尽后 f.cancel() 掉的：这首本轮压根没搜过，说"没找到"是假结论
                src, skipped_this_round = "", True
                unsearched.add(cid)
            except Exception:
                src = ""
            if src:
                hit_ids.add(cid)
                hit_srcs[src] = hit_srcs.get(src, 0) + 1
            verdict = src or ("本轮没轮到搜" if skipped_this_round else "没找到")
            why = "" if (src or skipped_this_round) else "；".join(rejects.get(cid) or [])
            log(f"匹配 {done}/{total}：{titles.get(cid, '?')} → {verdict}"
                + (f"（{why}）" if why else ""))
            if not timed_out and time.time() - started > budget:
                timed_out = True
                for f in futs:
                    f.cancel()
                log(f"按曲名匹配超过 {budget}s，剩下的不再搜了", "warning")
    if hit_srcs:
        log("按曲名匹配成功 " + "、".join(f"{k} {v} 首" for k, v in hit_srcs.items())
            + f"（共 {total} 首待匹配）")
    src_names = '/'.join(s.replace('MusicClient', '') for s in srcs)
    lazy = [titles[cid] for cid, _item in pairs if cid in unsearched]
    missed = [titles[cid] for cid, _item in pairs
              if cid not in hit_ids and cid not in unsearched]
    if lazy:
        log_name_list(log, f"有 {len(lazy)} 首本轮没轮到搜（整轮超过 {budget}s 就停了），"
                            "不是没找到，再下一次或改用取址快的默认匹配源即可", lazy)
    if missed:
        log_name_list(log, f"有 {len(missed)} 首在 {src_names} 里按曲名没找到同一首歌，"
                            "已跳过", missed)
    if report is not None:
        report.update({"total": total, "matched": len(hit_ids), "budget": budget,
                       "sources": src_names, "missed": missed, "unsearched": lazy})
    return len(hit_ids)


def _ytdlp_playlist_parse(
    url: str,
    *,
    source_label: str = "",
    proxy: str = "",
    log: Callable = print,
    limit: int = 300,
) -> tuple:
    """YouTube/Bilibili/喜马拉雅这类 musicdl 没有 parseplaylist 的平台走这里。

    返回 (曲目, 错误原因)：失败时由调用方决定是当兜底告警还是最终报错，别在这里
    抢先打 error —— 快列模式下后面还有 musicdl 要试。
    """
    out: List[dict] = []
    try:
        import yt_dlp
    except Exception as e:
        return out, f"yt-dlp 不可用，无法解析该歌单: {e}"
    opts = {
        "quiet": True, "skip_download": True, "extract_flat": "in_playlist",
        "playlistend": max(1, int(limit)), "noplaylist": False,
        "socket_timeout": 12, "extractor_retries": 1,
    }
    if proxy == PROXY_DIRECT:
        opts["proxy"] = ""      # yt-dlp 的空串就是强制直连
    elif proxy:
        opts["proxy"] = proxy
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        return out, f"yt-dlp 解析歌单失败: {_net_err_cn(e)}"
    entries = (info or {}).get("entries") or []
    base = str((info or {}).get("webpage_url") or url)
    for e in entries:
        if not e:
            continue
        vid = str(e.get("id") or "")
        link = str(e.get("url") or e.get("webpage_url") or "")
        if not link.startswith("http"):
            if source_label == "youtube" and vid:
                link = f"https://www.youtube.com/watch?v={vid}"
            elif source_label == "bilibili" and vid:
                link = f"https://www.bilibili.com/video/{vid}"
            else:
                link = base
        out.append({
            "id": "",
            "title": e.get("title") or vid or "未知",
            # extract_flat 的子条目常常没有 uploader。宁可空着，也别拿歌单归属方
            # （网易云那种官方号）当每首歌的歌手 —— 整列都是「网易云音乐」等于假数据。
            "artists": (e.get("uploader") or e.get("channel") or e.get("artist")
                        or e.get("creator") or ""),
            "duration": e.get("duration") or e.get("duration_string") or "",
            "album": str((info or {}).get("title") or ""),
            "source": source_label or "ytdlp",
            "musicdl_source": "",
            "url": link,
            "quality": "audio",
            "cover": str(e.get("thumbnail") or ""),
            "can_musicdl_download": False,
        })
    if out:
        log(f"yt-dlp 歌单解析: {len(out)} 首")
        return out, ""
    return out, "yt-dlp 没列出任何曲目（该平台的歌单它可能不认，或链接指向的是单曲/专辑）"


def parse_playlist(
    playlist_url: str,
    *,
    sources: Optional[List[str]] = None,
    work_dir: str = "",
    cookies: str = "",
    proxy: str = "",
    log: Callable = print,
    limit: int = 300,
    budget: int = 0,
    ytdlp_budget: int = 90,
    prefer: str = "fast",
) -> List[Dict[str, Any]]:
    """按域名找到真正负责这个歌单的源，逐源解析并把失败原因写进日志。

    不能再用 MusicClient.parseplaylist：它对每个源 suppress(Exception)，还会让所有源
    都去 head 一遍这个 URL —— 直连不通的 Spotify 链接能把六个源逐个拖超时，最后
    只剩一句"歌单解析: 0 首"。

    prefer="fast"：yt-dlp 认的平台先用它列曲目（一首歌一秒级），因为 musicdl 是逐曲
    去第三方接口取地址，50 首就要几分钟，而这段时间用户只能干看着转圈；想要 flac/
    歌词再切 "quality"。yt-dlp 不认的平台（酷狗/咪咕/Spotify…）没得选，只能 musicdl。
    """
    global _LAST_PLAYLIST_DIAG
    url = (playlist_url or "").strip()
    diag: Dict[str, Any] = {"url": url, "route": "", "engine": "", "prefer": prefer or "fast",
                            "attempts": [], "notes": [], "hint": ""}
    _LAST_PLAYLIST_DIAG = diag
    if not url.startswith("http"):
        diag["hint"] = "链接不是一个 http(s) 地址"
        log("歌单链接无效", "error")
        return []

    url, note = _normalize_playlist_url(url)
    if note:
        log(note)
    host = _url_host(url)
    owner = _match_host_table(host, PLAYLIST_HOSTS)
    yt_only = _match_host_table(host, YTDLP_PLAYLIST_HOSTS)
    diag["route"] = owner or yt_only or "ytdlp"
    if not budget:
        budget = 900

    def _try_musicdl() -> List[Dict[str, Any]]:
        started = time.time()
        got, err = _parse_playlist_via_musicdl(
            owner, url, work_dir=work_dir, cookies=cookies, proxy=proxy, log=log,
            budget=budget,
        )
        diag["attempts"].append({
            "source": owner, "count": len(got), "error": err,
            "seconds": round(time.time() - started, 1),
        })
        if got:
            diag["engine"] = "musicdl"
        if err:
            diag["hint"] = err
        return got

    def _try_ytdlp() -> List[Dict[str, Any]]:
        label = yt_only or (owner[:-len("MusicClient")].lower() if owner.endswith("MusicClient") else "")
        started = time.time()
        got, timed_out = _call_with_budget(
            lambda: _ytdlp_playlist_parse(url, source_label=label, proxy=proxy, log=log, limit=limit),
            ytdlp_budget, default=([], ""),
        )
        got, err = got if not timed_out else ([], f"yt-dlp 解析超过 {ytdlp_budget}s 已中止（该站点直连不通？）")
        diag["attempts"].append({
            "source": "yt-dlp", "count": len(got), "error": err,
            "seconds": round(time.time() - started, 1),
        })
        if got:
            diag["engine"] = "yt-dlp"
            diag["route"] = "yt-dlp"
        elif err and not diag["hint"]:
            diag["hint"] = err
        return got

    def _try_spotify_list() -> List[Dict[str, Any]]:
        started = time.time()
        res, timed_out = _call_with_budget(
            lambda: list_spotify_playlist(url, proxy=proxy, log=log),
            SPOTIFY_LIST_BUDGET, default=([], "", ""),
        )
        got, name, err = (res if not timed_out
                          else ([], "", f"Spotify 列曲目超过 {SPOTIFY_LIST_BUDGET}s 已中止"))
        if name:
            diag["name"] = name
        diag["attempts"].append({
            "source": "spotify-list", "count": len(got), "error": err,
            "seconds": round(time.time() - started, 1),
        })
        if got:
            diag["engine"] = "spotify-list"
        elif err:
            diag["hint"] = err
        return got

    items: List[Dict[str, Any]] = []
    can_ytdlp = bool(yt_only) or owner in YTDLP_PLAYLIST_SOURCES
    checked = {normalize_source_name(s) for s in (sources or []) if s}
    if owner and checked and owner not in checked:
        log(f"已自动启用 {owner}（搜索源里没勾它，但歌单域名归它管）")
    unreachable = _unreachable_reason(url, proxy, extra_hosts=PLAYLIST_API_HOSTS.get(owner, ()))
    if unreachable:
        # 网络层就不通，两条引擎都白搭 —— 直接说清楚，别再各等一轮超时。
        diag["attempts"].append({"source": diag["route"] or "ytdlp", "count": 0, "error": unreachable})
        diag["hint"] = f"{diag['route'] or host or '该站点'} 歌单解析跳过：{unreachable}"
        log(f"歌单解析: 0 首 —— {diag['hint']}", "error")
        return items

    if owner and not musicdl_available():
        log("musicdl 未安装，只能用 yt-dlp 解析该歌单", "warning")
        can_ytdlp = True
    elif not owner:
        log(f"{host or '该链接'} 没有对应的 musicdl 歌单源，改用 yt-dlp 解析", "warning")

    if owner == "SpotifyMusicClient" and prefer != "quality":
        log("Spotify 只列曲目（一次请求拿整张歌单的曲名/歌手/时长，不逐曲取址）；"
            "勾选下载时再按曲名去网易云、QQ 音乐这些平台匹配音频地址")
        items = _try_spotify_list()
        if not items and musicdl_available():
            log(f"只列曲目没成功（{diag['hint']}），退回 musicdl 逐曲取址", "warning")
            diag["hint"] = ""
            items = _try_musicdl()
    elif can_ytdlp and prefer != "quality":
        log(f"先用 yt-dlp 快速列出 {owner or host or '该歌单'} 的曲目（走链接下载）；"
            "要 flac/歌词可切「高音质逐曲取址」")
        items = _try_ytdlp()
        if not items and owner and musicdl_available():
            log(f"yt-dlp 没能列出曲目（{diag['hint']}），改用 musicdl 逐曲取址", "warning")
            diag["hint"] = ""
            items = _try_musicdl()
    elif owner:
        only_note = ("该平台 yt-dlp 不认（Spotify/Apple 这类还会被 yt-dlp 按 DRM 直接拒收）"
                     if owner in MUSICDL_ONLY_SOURCES and not yt_only else
                     f"超过 {budget}s 会改用 yt-dlp 快速列曲目")
        log(f"开始解析 {owner} 歌单：逐曲取地址，几十首通常要 1-3 分钟；{only_note}"
            + ("（当前为高音质模式）" if prefer == "quality" and can_ytdlp else ""))
        items = _try_musicdl()
        if not items and can_ytdlp:
            items = _try_ytdlp()
    else:
        items = _try_ytdlp()

    if not items and owner:
        notes = []
        exists = _playlist_exists_note(owner, url, proxy)
        if exists:
            diag["exists"] = exists
        if owner in MUSICDL_ONLY_SOURCES:
            notes.append("该平台 yt-dlp 不认，只能靠 musicdl 逐曲取址")
        if not _real_proxy(proxy) and not exists and (owner in OVERSEAS_PLAYLIST_SOURCES or yt_only in OVERSEAS_YTDLP_ONLY):
            if proxy == PROXY_DIRECT:
                notes.append("平台策略让该平台直连，海外平台直连通常取不到曲目（设置里改成走代理）")
            elif _system_proxy():
                notes.append("系统代理已生效仍取不到曲目，多半是代理节点不通该平台")
            else:
                notes.append("本机没填 HTTP 代理，海外平台直连通常取不到曲目")
        diag["notes"] = notes
        base = diag["hint"] or f"{owner} 没返回任何曲目"
        # hint 会被当成 toast 直接读出来：只留「原因 + 最 actionable 的一条」，其余进 notes
        diag["hint"] = f"{base}｜{exists}" if exists else base
    secs = sum(float(a.get("seconds") or 0) for a in diag["attempts"])
    if items:
        diag["hint"] = ""
        if not diag.get("name") and diag.get("engine") == "yt-dlp":
            # 这条分支把歌单标题写进了每行的 album（子条目常常没有自己的专辑名）
            diag["name"] = str(items[0].get("album") or "")
        n_before = len(items)
        items = merge_duplicate_tracks(items, log=log)
        diag["dup_merged"] = n_before - len(items)
        stamp_track_index(items)
    cost = f"，耗时 {secs:.0f}s" if secs >= 1 else ""
    if items:
        log(f"歌单解析: {len(items)} 首（{diag['engine'] or diag['route']}{cost}）")
    else:
        tail = ("（" + "；".join(diag["notes"]) + "）") if diag["notes"] else ""
        log(f"歌单解析: 0 首 —— {diag['hint'] or '各源都没返回曲目'}{tail}（{diag['route']}{cost}）", "error")
    return items


def _song_field(song: Any, *names) -> Any:
    """SongInfo 对象和占位 dict 都吃得下的取值。"""
    for n in names:
        v = song.get(n) if isinstance(song, dict) else getattr(song, n, None)
        if v not in (None, ""):
            return v
    return ""


# ── 成品音频的真实来路（界面来源列 / 下载日志 / 搬运版守门共用）──────────
# musicdl 的 Spotify 源没有官方音频通路（它自己的 spotify.py 里那句
# "TODO: Solve DRM Issues in Spotify" 就是这件事）：音频是逐首打第三方转链站取回来的，
# 而那些站普遍是去 YouTube 找同名视频抽音。所以界面上写「Spotify」的一行，音频并不来自 Spotify。
_RELAY_SITES = {
    "spotubedl.com": "spotubedl",
    "musicfab.io": "musicfab",
    "savemytracks.com": "SaveMyTracks",
    "spotidown.me": "spotidown",
    "spotsaver.net": "spotsaver",
    "spotisaver.net": "spotisaver",
    "spotify-downloads.com": "spotify-downloads",
    "rapidapi.com": "RapidAPI spotify-downloader9",
}
# Spotify / Apple 只给元数据与清单，不给音频
NO_AUDIO_PLATFORMS = ("Spotify", "Apple")
# 编码首尾补齐一般差 1 秒以内，再多就说明取回来的不是同一版录音
REUPLOAD_DUR_TOL_S = 3


def _url_host(u: Any) -> str:
    s = str(u or "")
    if "://" not in s:
        return ""
    try:
        from urllib.parse import urlsplit
        return (urlsplit(s).hostname or "").lower()
    except Exception:
        return ""


def _is_youtube(host: str) -> bool:
    return host.endswith("youtube.com") or host == "youtu.be"


def _walk_urls(node: Any, depth: int = 0):
    """把 raw_data 里所有 http(s) 串挖出来 —— 各家转链站把 YouTube 直链藏在不同键名里。"""
    if depth > 4:
        return
    if isinstance(node, str):
        if node.startswith("http"):
            yield node
    elif isinstance(node, dict):
        for v in node.values():
            yield from _walk_urls(v, depth + 1)
    elif isinstance(node, (list, tuple)):
        for v in node:
            yield from _walk_urls(v, depth + 1)


def _meta_get(node: dict, *keys) -> str:
    for k in keys:
        v = node.get(k)
        if isinstance(v, (list, tuple)):
            v = ", ".join(str(x.get("name") if isinstance(x, dict) else x) for x in v)
        if v not in (None, "", []):
            return str(v).strip()
    return ""


def _meta_dur(node: dict) -> int:
    """时长：键名带 ms 的按毫秒、其余按秒；读不出返回 0 表示不参与比较。"""
    if not isinstance(node, dict):
        return 0
    for k in ("duration_ms", "durationMs", "duration", "audio_length_sec", "length"):
        v = node.get(k)
        if v in (None, ""):
            continue
        try:
            num = float(v)
            if k.endswith("ms"):
                num /= 1000.0
        except (TypeError, ValueError):
            num = float(_dur_seconds(v))
        if num > 0:
            return int(round(num))
    return 0


def _spotify_meta(song: Any) -> dict:
    """Spotify 自己标的元数据（raw_data['search'] 那半边）。"""
    raw = _song_field(song, "raw_data") or {}
    sp = raw.get("search") if isinstance(raw, dict) else None
    for _ in range(3):
        if isinstance(sp, dict) and isinstance(sp.get("item"), dict):
            sp = sp["item"]
        elif isinstance(sp, dict) and isinstance(sp.get("data"), dict):
            sp = sp["data"]
        else:
            break
    if not isinstance(sp, dict):
        return {}
    return {"title": _meta_get(sp, "name", "title"),
            "artists": _meta_get(sp, "artists", "artist", "singer", "singers"),
            "dur": _meta_dur(sp)}


def audio_origin(song: Any, want: Optional[dict] = None) -> dict:
    """这条成品的音频到底从哪来、像不像搬运版。

    want 传用户点开的那一行（Spotify 歌单里的曲名/歌手/时长）；搜索路径没有 want，
    就退回 raw_data['search'] 里 Spotify 自标的元数据。国内平台命中时两样都没有，
    来源就是它自己，official 为真。
    reupload（搬运版）只看元数据对不对得上：音频经转链站从 YouTube 抽回来说是 Spotify/Apple
    的常态，那份只进 unofficial / youtube / label，不当搬运版，否则整张歌单一首都下不到。
    返回 {platform, via, youtube, official, unofficial, reupload, mismatch[], label, reasons[]}
    """
    src = str(_song_field(song, "source") or "").replace("MusicClient", "").replace("Client", "")
    got_title = str(_song_field(song, "song_name", "title", "name") or "")
    got_artists = _song_field(song, "singers", "artists", "singer", "artist")
    if isinstance(got_artists, (list, tuple)):
        got_artists = ", ".join(str(a) for a in got_artists)
    got_dur = int(_song_field(song, "duration_s") or 0) or _dur_seconds(_song_field(song, "duration"))

    urls = list(_walk_urls(_song_field(song, "raw_data") or {}))
    url = str(_song_field(song, "download_url", "url") or "")
    via = _RELAY_SITES.get(_url_host(url), "")
    yt = ""
    for u in ([url] + urls):
        h = _url_host(u)
        if not h:
            continue
        if not yt and _is_youtube(h):
            yt = u
        if not via and h in _RELAY_SITES:
            via = _RELAY_SITES[h]

    reasons: List[str] = []
    unofficial = src in NO_AUDIO_PLATFORMS or bool(via) or bool(yt)
    if src in NO_AUDIO_PLATFORMS:
        reasons.append(f"{src} 不给出音频，这条是经{via or '第三方转链站'}取回的")
    if yt and src != "YouTube":
        reasons.append(f"音频实际取自 YouTube（{yt}）")
    canon = dict(want or {}) or _spotify_meta(song)
    mismatch: List[str] = []
    if canon.get("title") and _norm_text(got_title) != _norm_text(str(canon["title"])):
        mismatch.append(f"曲名对不上：成品「{got_title}」≠ 标注「{canon['title']}」")
    if canon.get("artists") and _norm_text(str(got_artists)) != _norm_text(str(canon["artists"])):
        mismatch.append(f"歌手对不上：成品「{got_artists}」≠ 标注「{canon['artists']}」")
    cd = int(canon.get("dur") or canon.get("duration_s") or 0)
    if cd and got_dur and abs(cd - got_dur) > REUPLOAD_DUR_TOL_S:
        mismatch.append(f"时长差 {abs(cd - got_dur)}s（标注 {cd}s / 成品 {got_dur}s）")
    reasons += mismatch
    # 转链到 YouTube 不算搬运版：Spotify/Apple 压根没有官方音频通路，拦掉它等于整张歌单下不到歌。
    # 只有"取回来的元数据对不上用户点开的那一行"才是另一版录音，那种才守得住。
    chain = ""
    if unofficial:
        chain = f"{src} → YouTube" if yt else (f"{src} → {via}" if via else f"{src}（无官方音频）")
    return {"platform": src, "via": via, "youtube": yt, "official": not unofficial,
            "unofficial": unofficial, "reupload": bool(mismatch), "mismatch": mismatch,
            "label": chain or src, "reasons": reasons}


def _tb_is_stdlib(line: str) -> bool:
    """标准库/线程池的帧：报错现场它们只会占坑，不指认调用方。"""
    low = line.lower()
    if "<frozen " in low:
        return True
    return ("\\lib\\" in low or "/lib/" in low) and "site-packages" not in low


def _tb_tail(depth: int = 3) -> str:
    """最近一次异常的调用栈尾部，压成一行写进日志。

    线上只留 str(e) 的话，像"[WinError 2] …"这种一句话报错指不出是谁调的 makedirs，
    同一个症状可能对应好几条路径；留最后几帧才查得动。但 os.makedirs 自己递归的三帧
    （全在 <frozen os> 里）会把真正传坏路径的那一帧顶出窗口，所以先剔掉标准库帧。
    """
    frames = [ln.strip() for ln in traceback.format_exc().splitlines()
              if ln.strip().startswith("File ")]
    keep = [ln for ln in frames if not _tb_is_stdlib(ln)] or frames
    return " <- ".join(keep[-max(1, int(depth)):])


def _path_is_inside(base: str, target: str) -> bool:
    """target 目录是否落在 base 里面（大小写/斜杠不敏感）。"""
    import os
    if not base or not target:
        return False
    try:
        b = os.path.normcase(os.path.abspath(base))
        t = os.path.normcase(os.path.abspath(target))
    except Exception:
        return False
    return t == b or t.startswith(b.rstrip("\\/") + os.sep)


def _download_dir_ok(base: str, target: str) -> bool:
    """落点是否合法：在下载目录里，或在工具自己的输出目录里。

    只认下载目录是不够的 —— musicdl 每首歌自带的 work_dir 是缓存格子，而它自 1.2.7 包后补
    起搬到 MUSICDL_OUTPUTS 底下、不再位于下载目录内。按旧口径判会把每个正常落点都当成
    「要甩出下载目录」，然后把 work_dir 改写成下载目录根，成品直接落在根上、
    归档时源路径与目标路径撞成同一个文件（见 collect_and_promote_downloads）。
    """
    return _path_is_inside(base, target) or _path_is_inside(MUSICDL_OUTPUTS, target)


_EXT_PREFIXES = ("\\\\?\\", "\\\\.\\")     # Windows 的「别解析这条路」前缀，交给 makedirs 必炸


def _has_ext_prefix(p: str) -> bool:
    return str(p or "").startswith(_EXT_PREFIXES)


def _planned_save_path(s: Any) -> tuple:
    """问 musicdl 本人：这首歌下载时会用哪条路径落盘。返回 (路径, 报错原文)。

    必须读它的 save_path 属性，不能再自己 os.path.join 猜 —— 猜出来的那条永远合不来，
    线上那批就是这么漏的：守卫一条警告没发，下载却照样炸。读的时候要原样还回去：
    属性在 _save_path 为空时会顺手把名字钉上，同名避让那一步得留给 musicdl 下载时自己走。
    """
    was_none = getattr(s, "_save_path", None) is None
    try:
        return str(getattr(s, "save_path", "") or ""), ""
    except Exception as e:
        return "", f"{type(e).__name__}: {e}"
    finally:
        if was_none:
            s._save_path = None


def _guard_song_paths(items: List[Any], out_dir: str, log: Callable = print) -> int:
    r"""把每首歌的落点钉回缓存格子里，返回改写条数。必须在交给 download() 之前跑。

    musicdl 下载第一句就是 work_dir = os.path.dirname(save_path) 再 IOUtils.touchdir(它)，
    目录字符串不对它就当场 FileNotFoundError，而且它是在线程池里跑的 —— 一首歌炸，整片六首
    跟着中断。实测：路径带上 \\?\ 前缀时这句必炸（WinError 2），而 pathvalidate 会把反斜杠
    改成斜杠，所以日志里看到的是 '\\\\?\\H:/' 这种形状；盘根 H:\\ 本身反倒建得出来。前缀从
    哪儿来的我们没复现出来，所以判定不猜来源：直接照它下载时的原话试一遍，试不过就收回。
    """
    import os
    try:
        from musicdl.modules.utils.misc import IOUtils
        def _try_mkdir(d):
            IOUtils.touchdir(d)
    except Exception:
        def _try_mkdir(d):            # musicdl 不在，就只按路径形状判，不做真 mkdir
            return None
    cache_cell = musicdl_cache_dir(out_dir)
    n = 0
    for s in items:
        if isinstance(s, dict):        # 没匹配上的占位，压根不会下载
            continue
        name = str(getattr(s, "song_name", "") or "")
        wd = str(getattr(s, "work_dir", "") or "") or cache_cell
        raw = str(getattr(s, "_save_path", "") or "")
        stem = name.lstrip("/\\").strip()
        reason, bad = ("", "")
        if stem != name.strip():
            reason, bad = "曲名带路径分隔符", name
        elif _has_ext_prefix(wd):
            reason, bad = "路径带 Windows 扩展前缀", wd
        else:
            planned, err = _planned_save_path(s)
            target = os.path.dirname(planned or raw) if (planned or raw) else wd
            if err:
                reason, bad = f"musicdl 自己算落点就报错：{err}", planned or wd
            elif _has_ext_prefix(target):
                reason, bad = "落点带 Windows 扩展前缀", planned
            elif not _download_dir_ok(out_dir, target):
                reason, bad = "落在下载目录与工具输出目录之外", planned
            else:
                try:
                    _try_mkdir(target)     # 与它下载时同一句：这儿炸就等于那儿炸
                except Exception as e:
                    reason, bad = f"musicdl 建这个目录会失败：{type(e).__name__}: {e}", target
        if not reason:
            continue
        s.song_name = stem or "未知曲目"
        if not _download_dir_ok(out_dir, wd) or _has_ext_prefix(wd):
            s.work_dir = cache_cell    # 收回格子，不是收回下载目录：归档只认格子（见 #126）
        s._save_path = None            # 交回 musicdl 重算：同名避让那套逻辑还得留着它
        n += 1
        renamed = (f"，曲名改成「{s.song_name[:24]}」" if s.song_name != name.strip() else "")
        log(f"曲目「{name[:24] or '（空）'}」{reason}（{str(bad)[:90] or '（空）'}），"
            f"落点收回 {cache_cell}{renamed}", "warning")
        # 收回之后还得再试一次：万一原样重算还是炸，就别再交给 musicdl 了，直接钉一条我们
        # 自己拼的短路径，宁可名字难看一点也不能带走整片。
        again, _ = _planned_save_path(s)
        try:
            _try_mkdir(os.path.dirname(again) if again else s.work_dir)
        except Exception as e:
            ext = str(getattr(s, "ext", "") or ".mp3").lstrip(".") or ".mp3"
            pinned = os.path.join(s.work_dir, f"{s.song_name[:60] or '未知曲目'} - "
                                              f"{getattr(s, 'identifier', '') or n}.{ext}")
            s._save_path = pinned      # 钉死：musicdl 只会再按长度 legalize 一次
            log(f"曲目「{name[:24] or '（空）'}」收回后仍建不出目录（{type(e).__name__}: {e}），"
                f"已直接钉死落点 {pinned[:90]}", "error")
    return n


def _name_key(text) -> str:
    """曲名与文件名比对前先归一：musicdl 落盘时把非法字符换成下划线，路径过长还会截断，
    差一个分隔符就不算同一首歌的话，对位就只能靠猜了。"""
    import re
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", str(text or "").lower())


def _file_name_part(stem) -> str:
    r"""「曲名 - 标识符 (1)」削成「曲名」。只削最后一段，且要求那半截像标识符 ——
    曲名自己也可能带「 - 」，全按第一个分隔符切会把歌名切掉。"""
    import re
    base = re.sub(r"\s*\(\d+\)\s*$", "", str(stem or "").strip())
    head, sep, tail = base.rpartition(" - ")
    if sep and re.fullmatch(r"[\w.\-]{3,}", tail.strip()):
        return head
    return base


def _name_match(stem, key: str, *, prefix: bool = False) -> bool:
    """这个文件名算不算「{key} 这首歌」的。prefix 那一轮只在前缀唯一命中时才认：
    「Aimer」和「Aimer Vivre」只差一个词，认松了就是把别人的歌安过来。"""
    a = _name_key(_file_name_part(stem))
    if not a or not key:
        return False
    return a == key or (prefix and a.startswith(key))


def _pair_paths_by_name(piece, real_by_dir, used, *, log: Callable = print) -> List[str]:
    """把这一片真正落盘的成品按曲名对回各自的行，返回与 piece 同长的清单（认不出的位置留空）。

    原来这一步是「计划路径不在盘上，就从同一个目录里顺手指一个没用过的文件」。可 musicdl 的
    download() 是线程池按完成顺序把副本交回来的，同一批三首以上、完成顺序一不等于清单顺序，
    指到的就是别人的成品 —— 文件名、歌词、标签都是这一行的，音频却是那一首的，
    当场还看不出任何毛病（实测 2026-09-24 收藏整单 4 首，四份音频整个倒了过来）。
    所以只认名字对得上的；对不上就留空，让上层按「这首没下成」报错，不再拿别人的文件顶上。
    """
    out: List[str] = [""] * len(piece)
    taken = set(str(x) for x in used)
    pool = [c for cs in real_by_dir.values() for c in cs]
    pend: List[tuple] = []
    for pos, (_i, s) in enumerate(piece):
        key = _name_key(_song_field(s, "song_name", "songname", "title", "name"))
        sp = str(_song_field(s, "save_path", "filepath"))
        if sp and sp not in taken and Path(sp).is_file() and _name_match(Path(sp).stem, key):
            out[pos] = sp
            taken.add(sp)
            continue
        pend.append((pos, key, str(Path(sp).parent) if sp else ""))
    for round_prefix in (False, True):
        left: List[tuple] = []
        for pos, key, parent in pend:
            if not key:
                continue          # 连曲名都没有，指哪个都是猜
            hits = [c for c in pool if c not in taken and _name_match(Path(c).stem, key,
                                                                      prefix=round_prefix)]
            near = [c for c in hits if str(Path(c).parent) == parent] or hits
            if near and len(near) == 1:
                out[pos] = near[0]
                taken.add(near[0])
            elif near and not round_prefix:
                left.append((pos, key, parent))     # 同名多条：先让别的行挑完再回头
            # 前缀轮还是一条都不中 → 就留空，下面会点名报出来
        pend = left
        if not pend:
            break
    used.clear()
    used.update(taken)
    return out


def download_songs(
    cache_ids: List[str],
    *,
    work_dir: str = "",
    cookies: str = "",
    proxy: str = "",
    proxy_for: Optional[Callable[[str], str]] = None,
    log: Callable = print,
    match_sources: Optional[List[str]] = None,
    on_result: Optional[Callable[[int, str], Any]] = None,
    chunk: int = DOWNLOAD_CHUNK,
    match_report: Optional[dict] = None,
    block_reupload: bool = False,
    quality_spec: Any = None,
) -> List[str]:
    """按缓存 id 精确下载（官方 download）。返回列表与 cache_ids 一一对应，下不上的位置是 ""。

    match_sources 只在条目是"只列了曲名"的占位（Spotify 大歌单）时用：那时才按曲名去这些
    平台搜同一首歌，命中才取地址 —— 解析阶段不给用户点开的歌付取址时间。
    match_report 传字典时由那一轮回填结论（哪些没找到、哪些没轮到搜），界面结束时要列清单。

    block_reupload 打开时，取回来的成品若和用户点开的那一行对不上（曲名/歌手/时长差超容差，
    即另一版录音的搬运版）就不下，当场记入日志并在结束时列清单。注意它不拦"经转链站从
    YouTube 取回"这件事本身：Spotify/Apple 没有官方音频通路，拦掉等于整张歌单下不到歌。

    下载按 chunk 首一片推进，每片一完成就归档并把路径交给 on_result(下标, 路径)，
    让成品在整批跑完之前就出现在最终目录里；chunk<=0 表示一次下完整批。
    """
    if not musicdl_available():
        log("musicdl 不可用", "error")
        return []
    results: List[str] = ["" for _ in cache_ids]

    def _notify(i: int, path: str) -> None:
        results[i] = path or ""
        if on_result is None:
            return
        try:
            on_result(i, results[i])
        except Exception as e:
            log(f"下载收尾（第 {i + 1} 首）: {e}", "warning")

    objs: List[Any] = []
    for cid in cache_ids:
        s = get_cached_song(cid)
        if s is None:
            log(f"缓存失效: {cid[:8]}", "warning")
        objs.append(s)
    spec = norm_quality_spec(quality_spec)
    spec_on = quality_spec_active(spec)
    spec_want = quality_spec_label(spec)
    if spec_on:
        log(f"本次音质要求：{spec_want}｜档位由平台决定，这个要求只能用于「几条候选里挑达标的那条」"
            "与下完之后的核对"
            + ("；勾了「不达标不下」，取到的成品确认不达标就不下" if spec["strict"] else ""))
    qa_skipped: List[tuple] = []      # 平台标注的档位已确认不达标，且勾了「不达标不下」
    qa_low: List[tuple] = []          # 成品落盘后读元数据核对：确实低于要求
    qa_unknown: List[tuple] = []      # 成品读不出某一维：只报「没核到」，不判不达标
    pend = [(i, cache_ids[i], o) for i, o in enumerate(objs)
            if isinstance(o, dict) and o.get("needs_match")]
    # 占位匹配成功后 objs[i] 会换成命中平台那条，Spotify 标的那份曲名/时长只留在占位里。
    # 判"取回来的是不是用户点开的那首歌"要有基准，所以先按着下标存一份。
    want_by_idx: Dict[int, dict] = {}
    for i, o in enumerate(objs):
        if isinstance(o, dict):
            want_by_idx[i] = {
                "title": str(o.get("title") or ""), "artists": str(o.get("artists") or ""),
                "dur": int(o.get("duration_s") or _dur_seconds(o.get("duration")))}
    if pend:
        resolve_placeholders([(cid, o) for _i, cid, o in pend], sources=match_sources,
                             work_dir=work_dir, cookies=cookies, proxy=proxy,
                             proxy_for=proxy_for, log=log, report=match_report,
                             quality_spec=spec)
        for i, cid, _o in pend:
            objs[i] = get_cached_song(cid)
    songs = []
    todo: List[tuple] = []            # [(cache_ids 下标, SongInfo)] —— 分片要靠下标对回报答
    sources_needed = set()
    origin_by_idx: Dict[int, dict] = {}
    blocked: List[tuple] = []
    for i, s in enumerate(objs):
        if s is None:
            _notify(i, "")
            continue
        if isinstance(s, dict):        # 占位没匹配到任何平台 —— 这首下不了，已经汇总过了
            objs[i] = None
            _notify(i, "")
            continue
        org = audio_origin(s, want_by_idx.get(i))
        origin_by_idx[i] = org
        if block_reupload and org["reupload"]:
            blocked.append((i, org))
            log(f"疑似搬运版，按开关不下：「{song_field(s, 'song_name', 'title', 'name') or '（未知曲名）'}」"
                f"—— {'；'.join(org['mismatch'])}", "warning")
            objs[i] = None
            _notify(i, "")
            continue
        if spec_on and spec["strict"]:
            # 只按平台标注判：标注里没有的那一维不算不达标（否则「仅无损」会把
            # 所有没自报档位的源全部跳过，那就是拿「不知道」当「不合格」用了）
            qa = quality_against_spec(song_spec_facts(s), spec)
            if qa["state"] == "low":
                qa_skipped.append((i, qa))
                log(f"档位不达标，按勾选不下：「{song_field(s, 'song_name', 'title', 'name') or '（未知曲名）'}」"
                    f"—— {qa['note']}", "warning")
                objs[i] = None
                _notify(i, "")
                continue
        songs.append(s)
        todo.append((i, s))
        src = str(_song_field(s, "source"))
        if src:
            sources_needed.add(src if src.endswith("Client") else normalize_source_name(src))
    if not songs:
        _why = []
        if blocked:
            _why.append(f"{len(blocked)} 首被搬运版开关拦下")
        if qa_skipped:
            _why.append(f"{len(qa_skipped)} 首被「不达标不下」拦下")
        log("没有有效曲目可下载"
            + (f"（{'，'.join(_why)}，原因见上面几行）" if _why else ""),
            "warning")
        return results
    srcs = list(sources_needed) or list(DEFAULT_SOURCES)
    out_dir = work_dir or MUSICDL_OUTPUTS
    _guard_song_paths(songs, out_dir, log)

    def _finish_one(i: int, path: str) -> None:
        song = get_cached_song(cache_ids[i])
        title = str(_song_field(song, "song_name", "songname", "title", "name"))
        artists = _song_field(song, "singers", "artists", "singer", "artist")
        if isinstance(artists, (list, tuple)):
            artists = ", ".join(str(a) for a in artists)
        cover = str(_song_field(song, "cover_url", "album_pic", "cover"))
        lyric = str(_song_field(song, "lyric", "lyrics", "lrc"))
        lyric_url = str(_song_field(song, "lyric_url", "lrc_url"))
        if not lyric.strip():
            # musicdl 内置歌词补全（lrclib）主要覆盖欧美曲库，Apple/Spotify 等全球源
            # 下载华语歌曲时常匹配不到，这里用网易云公开接口兜底再试一次
            fallback = fetch_lyric_fallback_cn(title, str(artists or ""))
            if fallback:
                lyric = fallback
                log("歌词: lrclib 未命中，已用网易云兜底匹配成功")
        try:
            save_lyrics_and_cover(
                path,
                lyrics_text=lyric,
                lyrics_url=lyric_url,
                cover_url=cover,
                embed=False,
                log=log,
            )
        except Exception as e:
            log(f"歌词/封面处理: {e}", "warning")
        org = origin_by_idx.get(i) or audio_origin(song, want_by_idx.get(i))
        q_note = ""
        if spec_on:
            # 下载前只能信平台标注，成品落盘后读它自己的标签才是真值
            try:
                qa = quality_against_spec(row_audio_facts(audio_file_meta(path, log=log)), spec)
            except Exception as e:
                qa = {"state": "", "note": f"核对失败：{e}"}
            if qa["state"] == "low":
                qa_low.append((i, qa))
                q_note = f"｜{qa['note']}"
            elif qa["state"] == "unknown":
                qa_unknown.append((i, qa))
                q_note = f"｜{qa['note']}"
        log(f"musicdl 已下载: {Path(path).name}"
            + (f"｜音频来源 {org['label']}" if org.get("unofficial") else "")
            + (f"｜{'；'.join(org['reasons'])}" if org.get("reasons") else "")
            + q_note)

    try:
        started_at = time.time() - 1
        client = _build_client(
            srcs,
            work_dir=out_dir,
            search_size=5,
            cookies=cookies or None,
            proxy=proxy,
            proxy_for=proxy_for,
            log=log,
        )
        size = len(todo) if not chunk or chunk <= 0 else max(1, int(chunk))
        pieces = [todo[o:o + size] for o in range(0, len(todo), size)]
        log(f"开始下载 {len(todo)} 首"
            + (f"：每 {size} 首一片，每片下完立刻归档到 {out_dir}，不用等整批"
               if len(pieces) > 1 else ""))
        n_ok = 0
        n_done = 0

        def _salvage_paths(piece) -> List[str]:
            """download() 抛异常时的兜底：从缓存里把这一片已经落盘的成品找回来。

            拿不到 musicdl 的返回值，就只能按每首歌自己的 save_path / work_dir 去对；
            work_dir 在 musicdl 内部会被 sanitize 成斜杠形式，所以两边都 normcase 再比。
            """
            import os as _os
            _nc = _os.path.normcase
            cache = Path(musicdl_cache_dir(out_dir))
            exts = {".mp3", ".flac", ".m4a", ".aac", ".ogg", ".wav", ".opus"}
            by_dir: Dict[str, List[Path]] = {}
            try:
                fresh = [p for p in cache.rglob("*")
                         if p.is_file() and p.suffix.lower() in exts
                         and p.stat().st_mtime >= started_at]
            except Exception:
                fresh = []
            for p in fresh:
                by_dir.setdefault(_nc(str(p.parent)), []).append(p)
            taken: set = set()
            found: List[str] = []
            for _i, s in piece:
                sp = str(_song_field(s, "save_path", "filepath"))
                if sp and Path(sp).is_file():
                    found.append(sp)
                    taken.add(_nc(sp))
                    continue
                name = str(_song_field(s, "song_name", "songname", "title", "name"))
                parent = _nc(str(Path(sp).parent)) if sp else _nc(
                    str(_song_field(s, "work_dir")))
                hit = next((c for c in by_dir.get(parent, [])
                            if _nc(str(c)) not in taken and c.stem.startswith(name)), None)
                if hit is None:
                    hit = next((c for d in by_dir.values() for c in d
                                if _nc(str(c)) not in taken and name
                                and c.stem.startswith(name)), None)
                if hit is not None:
                    taken.add(_nc(str(hit)))
                    found.append(str(hit))
                else:
                    found.append("")
            return found

        for pi, piece in enumerate(pieces, 1):
            dl_error = ""
            try:
                downloaded = client.download(song_infos=[s for _i, s in piece]) or []
            except Exception as e:
                # musicdl 的 download() 已知会在「文件已经落盘、结果还没返回」之间抛错
                # （进度条收尾写编不出的字符、建某首歌的目录时 WinError 2）。以前整片直接
                # 放弃，成品就烂在 _musicdl_cache 里 —— 所以这里只记错，随后照旧归档。
                dl_error = f"{type(e).__name__}: {e}"
                log(f"第 {pi}/{len(pieces)} 片下载中断: {dl_error}"
                    f"｜栈尾 {_tb_tail()}｜改从缓存里找已经下好的文件", "error")
                downloaded = []
            if not downloaded and not dl_error:
                log(f"第 {pi}/{len(pieces)} 片一首都没下下来"
                    f"（{len(piece)} 首要取址：链接过期、需 Cookie 或被地区限制）", "error")
            # 按下标对位归档：调用方拿 paths[i] 配 ids[i] 写文件名/歌词/标签，而并发下载的
            # 完成顺序跟这个无关，对不上就会把别人的名字安到这首歌上。
            #
            # 不能直接用 objs 里的 save_path：那是搜索时算的"计划路径"，同名歌会被 musicdl 排成
            # "xxx (1).flac"；真正落盘的是 musicdl 内部那份副本的路径，两者字符串不一样，
            # 直接拿去搬就是一片"文件不存在"。所以用 downloaded（副本们）按目录建索引来对位 ——
            # musicdl 给每首歌单开一个带时间戳的目录，目录名本身就够唯一定位了。
            real_by_dir: Dict[str, List[str]] = {}
            for s in downloaded:
                rp = str(_song_field(s, "save_path", "filepath"))
                if rp and Path(rp).is_file():
                    real_by_dir.setdefault(str(Path(rp).parent), []).append(rp)
            used: set = set()
            if dl_error:
                src_paths: List[str] = _salvage_paths(piece)
                # 一首歌的路径炸了，musicdl 的线程池会让整片一起收摊：缓存里没有成品的那些
                # 歌其实压根没下过。逐首单独重试一次，一首坏路径最多带走它自己。
                n_before = sum(1 for p in src_paths if p)
                for k, (_i, s) in enumerate(piece):
                    if src_paths[k]:
                        continue
                    try:
                        client.download(song_infos=[s])
                    except Exception:
                        pass
                    src_paths[k] = _salvage_paths([(_i, s)])[0]
                n_retry = sum(1 for p in src_paths if p) - n_before
                if n_retry:
                    log(f"第 {pi}/{len(pieces)} 片逐首重试补回 {n_retry} 首", "warning")
            else:
                src_paths = _pair_paths_by_name(piece, real_by_dir, used, log=log)
                lost = [(i, _song_field(s, "song_name", "songname", "title", "name"))
                        for (i, s), p in zip(piece, src_paths) if not p]
                if lost:
                    log_name_list(log,
                                  f"有 {len(lost)} 首在缓存里认不出哪个文件是它自己（文件名对不上曲名），"
                                  "这一首按没下成算，不敢拿同目录里剩下的文件顶上——"
                                  "宁可少一首，也不能把别人的歌安到这个名字上",
                                  [f"「{str(t or '（空曲名）')[:40]}」" for _i, t in lost],
                                  level="error")
            n_real = sum(len(v) for v in real_by_dir.values())
            if not dl_error and n_real > len(used):
                log(f"musicdl 报了 {n_real} 首下载成功，只有 {len(used)} 首找到成品文件"
                    f"（其余在缓存里没有，可能是同名歌被覆盖）", "warning")
            try:
                paths = collect_and_promote_downloads(musicdl_cache_dir(out_dir), out_dir,
                                                      log=log, since=started_at, only=src_paths)
            except Exception as e:
                log(f"归档: {e}", "warning")
                paths = [p if p and Path(p).is_file() else "" for p in src_paths]
                try:
                    cleanup_musicdl_pkl(out_dir, log=log)
                except Exception:
                    pass
            paths = list(paths or [])
            paths += [""] * (len(piece) - len(paths))
            if dl_error:
                log(f"第 {pi}/{len(pieces)} 片中断后从缓存救回 "
                    f"{sum(1 for p in paths if p)}/{len(piece)} 首", "warning")
            for (i, _s), path in zip(piece, paths):
                if path and not Path(path).is_file():
                    # 归档返回了路径、文件却不在 —— 报「已下载」就是假成功，
                    # 界面上只会剩下歌词而看不见歌（本轮 6 首丢的就是这个形状）。
                    log(f"归档后文件不见了：{Path(path).name}（这一首按失败算，"
                        f"目录里没有留下成品）", "error")
                    path = ""
                if path:
                    n_ok += 1
                    _finish_one(i, path)
                _notify(i, path)
            n_done += len(piece)
            if len(pieces) > 1:
                log(f"下载进度 {n_done}/{len(todo)} 首（成功 {n_ok} 首，已归档 {pi}/{len(pieces)} 片）")
        if blocked:
            log_name_list(log, f"以下 {len(blocked)} 首被判为搬运版（取回的元数据和歌单标注对不上），本次未下载",
                          [f"「{song_field(get_cached_song(cache_ids[i]), 'song_name', 'title', 'name') or '（未知曲名）'}」"
                           f"（{'；'.join(o['mismatch'])}）" for i, o in blocked])
        if qa_skipped:
            log_name_list(log, f"以下 {len(qa_skipped)} 首在下载前按平台标注就不满足本次音质要求（{spec_want}），未下载",
                          [f"「{song_field(get_cached_song(cache_ids[i]), 'song_name', 'title', 'name') or '（未知曲名）'}」"
                           f"（{q['note']}）" for i, q in qa_skipped])
        if spec_on:
            if qa_low:
                log_name_list(log, f"以下 {len(qa_low)} 首成品读元数据后确认低于本次要求（{spec_want}）",
                              [f"「{Path(results[i]).name if results[i] else (song_field(get_cached_song(cache_ids[i]), 'song_name', 'title', 'name') or '（未知曲名）')}」"
                               f"（{q['note']}）" for i, q in qa_low])
            if qa_unknown:
                log_name_list(log, f"另有 {len(qa_unknown)} 首成品有一维读不出来，无法核对（读不出不等于不达标）",
                              [f"「{song_field(get_cached_song(cache_ids[i]), 'song_name', 'title', 'name') or '（未知曲名）'}」"
                               f"（{q['note']}）" for i, q in qa_unknown], level="info")
            if not qa_low and not qa_unknown:
                log(f"音质核对：{n_ok} 首成品逐首读过元数据，没有低于本次要求（{spec_want}）的")
        return results
    except Exception as e:
        log(f"musicdl.download 失败: {e}｜栈尾 {_tb_tail()}", "error")
        try:
            cleanup_musicdl_pkl(work_dir or MUSICDL_OUTPUTS, log=log)
            cleanup_musicdl_pkl(musicdl_cache_dir(work_dir or MUSICDL_OUTPUTS), log=log)
        except Exception:
            pass
        return []


def download_via_musicdl(
    title: str,
    artists: str = "",
    source: str = "",
    *,
    save_dir: str = "",
    cookies: str = "",
    proxy: str = "",
    log: Callable = print,
) -> Optional[str]:
    """无缓存时：搜索匹配后下载第一首。"""
    srcs = [source] if source else list(DEFAULT_SOURCES)
    items = search_music(
        f"{artists} {title}".strip(),
        sources=srcs,
        limit=5,
        work_dir=save_dir,
        cookies=cookies,
        proxy=proxy,
        include_ytdlp=False,
        log=log,
    )
    if not items:
        return None
    # 优先标题匹配
    pick = items[0]
    for it in items:
        if title and title.lower() in (it.get("title") or "").lower():
            pick = it
            break
    paths = download_songs(
        [pick["id"]],
        work_dir=save_dir,
        cookies=cookies,
        proxy=proxy,
        log=log,
    )
    return paths[0] if paths else "ok"


def _ytdlp_music_search(keyword: str, limit: int = 8, log: Callable = print) -> List[dict]:
    out: List[dict] = []
    try:
        import yt_dlp
    except Exception as e:
        log(f"yt-dlp 不可用: {e}", "warning")
        return out
    for prefix, source in (("ytsearch", "youtube"), ("scsearch", "soundcloud")):
        q = f"{prefix}{limit}:{keyword}"
        try:
            opts = {"quiet": True, "skip_download": True, "extract_flat": True, "noplaylist": True}
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(q, download=False)
            for e in (info or {}).get("entries") or []:
                if not e:
                    continue
                vid = e.get("id") or ""
                url = e.get("url") or e.get("webpage_url") or ""
                if source == "youtube" and vid and not str(url).startswith("http"):
                    url = f"https://www.youtube.com/watch?v={vid}"
                out.append({
                    "id": "",
                    "title": e.get("title") or keyword,
                    "artists": e.get("uploader") or e.get("channel") or "",
                    "duration": e.get("duration") or e.get("duration_string") or "",
                    "album": "",
                    "source": source,
                    "musicdl_source": "",
                    "url": url,
                    "quality": "audio",
                    "cover": "",
                    "can_musicdl_download": False,
                })
        except Exception as e:
            log(f"{source} 搜索失败: {e}", "warning")
    return out


def install_musicdl(log: Callable = print, mirror: str = "", force: bool = False) -> str:
    # 便携包出包时已把 musicdl 铺进 runtime —— 先说清楚，别让人白点一次「安装」
    if not force:
        try:
            import musicdl  # noqa: F401
            import zhconv  # noqa: F401
            log("musicdl 已内置，无需安装（要升级到最新版请点「更新 musicdl」）")
            return "ok"
        except Exception:
            pass
    from pkg_update import pip_install

    ok, res = pip_install(["musicdl", "zhconv"], log=log, mirror=mirror)
    return "ok" if ok else f"failed: {res}"


# ── 文件名模板 / 付费过滤 / Range / 歌词封面 / 本地索引 ──────────

def safe_path_component(s: str, max_len: int = 80) -> str:
    import re
    s = (s or "").strip() or "unknown"
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", s)
    s = s.replace("..", "_").strip(" .")
    return (s[:max_len] or "unknown")


# 归档命名（Emby / Jellyfin 按目录读曲库）多给的四个字段。各平台在原始返回里的键名各写各的，
# 所以先取结果行自带的，再按候选键名去 raw_data["search"] 里找第一个有值的。
ARCHIVE_TRACK_KEYS = ("track_index", "position", "song_index", "songIndex",
                      "track", "track_number", "trackNumber")
ARCHIVE_DISC_KEYS = ("disc", "disc_num", "disc_no", "disk", "disk_num", "cd", "cd_num")
ARCHIVE_DATE_KEYS = ("publish_time", "publishTime", "pub_time", "pubdate", "pub_date",
                     "release_date", "releaseDate", "release_time", "releaseTime", "a_time")


def _raw_search(song: Any) -> Any:
    """平台搜索/歌单接口回的那条原始 JSON —— musicdl 把它塞在 raw_data["search"]。"""
    raw = song.get("raw_data") if isinstance(song, dict) else getattr(song, "raw_data", None)
    return raw.get("search") if isinstance(raw, dict) else None


def _meta_walk(obj: Any, keys: tuple, depth: int = 0) -> str:
    """限深找候选键：网易云把发布时间写在 album.publishTime，QQ 写在条目自己身上，形状差很多。"""
    import re
    if depth > 3 or obj is None:
        return ""
    if isinstance(obj, dict):
        for k in keys:
            v = obj.get(k)
            if isinstance(v, (int, float, str)) and str(v).strip() not in ("", "0"):
                return re.sub(r"\s+", " ", str(v)).strip()[:40]
        for v in obj.values():
            if isinstance(v, (dict, list)):
                got = _meta_walk(v, keys, depth + 1)
                if got:
                    return got
    elif isinstance(obj, list):
        for v in obj[:3]:
            got = _meta_walk(v, keys, depth + 1)
            if got:
                return got
    return ""


def _num_prefix(v: Any) -> str:
    """'12' / 12 / '第3首' → '12' / '3'；没有数字前缀就返回空。"""
    import re
    m = re.search(r"\d+", str(v if v is not None else "").strip())
    return m.group(0) if m else ""


def _norm_date(v: Any) -> str:
    """平台写的时间归成 YYYY-MM-DD；认不出来返回空 —— 宁可少一层目录，也别写出怪文件名。"""
    import re
    from datetime import datetime
    s = str(v if v is not None else "").strip()
    if not s:
        return ""
    if re.fullmatch(r"\d{12,13}", s):       # 毫秒时间戳
        s = str(int(s) // 1000)
    if re.fullmatch(r"\d{10}", s):          # 秒时间戳
        try:
            return datetime.fromtimestamp(int(s)).strftime("%Y-%m-%d")
        except Exception:
            return ""
    if re.fullmatch(r"\d{8}", s):           # 20050101
        y, mo, d = int(s[:4]), int(s[4:6]), int(s[6:8])
        return f"{y}-{mo:02d}-{d:02d}" if 1 <= mo <= 12 and 1 <= d <= 31 else ""
    # 2005-01-01 / 2005.1.1 / 2005/1/1 / 2005年1月1日：月、日给到几位算几位
    m = re.match(r"(19|20)\d{2}[-/.年](\d{1,2})(?:[-/.月](\d{1,2}))?", s)
    if m:
        y, mo = s[:4], int(m.group(2))
        d = int(m.group(3)) if m.group(3) else 0
        if 1 <= mo <= 12 and 1 <= d <= 31:
            return f"{y}-{mo:02d}-{d:02d}"
        if 1 <= mo <= 12 and not d:
            return f"{y}-{mo:02d}"
        return ""
    return s[:4] if re.fullmatch(r"(19|20)\d{2}\D*", s) else ""   # 只写得出年份就按年份归档


def song_archive_meta(song: Any) -> dict:
    """一行结果（SongInfo 对象或占位 dict）能给出的归档字段，取不到的键留空。"""
    raw = _raw_search(song)
    track = _num_prefix(song_field(song, *ARCHIVE_TRACK_KEYS) or _meta_walk(raw, ARCHIVE_TRACK_KEYS))
    disc = _num_prefix(song_field(song, *ARCHIVE_DISC_KEYS) or _meta_walk(raw, ARCHIVE_DISC_KEYS))
    date = _norm_date(song_field(song, *ARCHIVE_DATE_KEYS) or _meta_walk(raw, ARCHIVE_DATE_KEYS))
    return {"track": track, "disc": disc, "year": date[:4], "date": date}


def stamp_track_index(items: List[Dict[str, Any]]) -> None:
    """给歌单每一行标上「第几首」—— {track} 要序号，而平台返回的行大多不带。

    原地改写：行 dict 和缓存里那条真结果都要写。收尾重命名读的是缓存里那一条
    （占位行匹配成功后也是把真结果换回同一个缓存槽），只写 dict 等于没写。
    平台自己给了碟片序号的行不动 —— 那是专辑曲目表上的编号，比列表位置可信。
    """
    for n, row in enumerate(items):
        if not isinstance(row, dict) or str(row.get("track_index") or "").strip():
            continue
        song = get_cached_song(str(row.get("id") or ""))
        if song is not None and song_archive_meta(song)["track"]:
            continue
        row["track_index"] = str(n + 1)
        if song is None or isinstance(song, dict):
            continue
        try:
            setattr(song, "track_index", n + 1)
        except Exception:
            pass   # SongInfo 带 __slots__ 之类挡着：行 dict 上有号，匹配轮照样能带过去


def carry_archive_fields(src: Any, dst: Any) -> None:
    """把占位行上的归档字段搬到换回来的真结果上：源平台不知道这首歌在原歌单里排第几。"""
    if not isinstance(src, dict):
        return
    for k in ("track_index", "disc"):
        v = src.get(k)
        if v in (None, "") or getattr(dst, k, None) not in (None, ""):
            continue
        try:
            setattr(dst, k, v)
        except Exception:
            pass


def _pad_num(v: Any) -> str:
    """序号补零：Emby / Jellyfin 按文件名排序，不补零会出现 1、10、11、2。"""
    n = _num_prefix(v)
    if not n:
        return ""
    return n.zfill(2) if len(n) <= 2 else n.zfill(3)


def _tidy_segment(s: str) -> str:
    """占位取不到值时，模板里的连接符会孤零零留在行头行尾（"- 晴天"），这里一并削掉。"""
    import re
    s = str(s or "").strip()
    s = re.sub(r"^[\s\-_—.、,，]+", "", s)
    s = re.sub(r"[\s\-_—.、,，]+$", "", s)
    return s.strip()


def format_music_path(
    template: str,
    *,
    title: str = "",
    artists: str = "",
    album: str = "",
    source: str = "",
    sid: str = "",
    ext: str = "mp3",
    base_dir: str = "",
    track: Any = "",
    disc: Any = "",
    year: Any = "",
    date: Any = "",
) -> Path:
    """
    模板示例: {artist}/{album}/{name} - {artist}
    占位: name artist album source id ext
          track disc year date（Emby / Jellyfin 归档用，序号自动补零成 01）

    取不到值的归档字段一律当空处理（不像 {album} 会兜一层 Unknown）：整段空掉的目录不建，
    文件名行首行尾孤零零的连接符（"- 晴天" / "03 - "）削掉，
    认不出的占位符（打错的 {track_no}）也不会原样变成文件名的一部分。
    """
    tpl = (template or "{name} - {artist}").strip()
    ext = (ext or "mp3").lstrip(".")
    date_s = _norm_date(date) if str(date or "").strip() else ""
    year_s = _num_prefix(year) or date_s[:4]
    mapping = {
        "name": safe_path_component(title),
        "title": safe_path_component(title),
        "artist": safe_path_component(artists),
        "artists": safe_path_component(artists),
        "album": safe_path_component(album or "Unknown"),
        "source": safe_path_component(source or "music"),
        "id": safe_path_component(sid or "x", 32),
        "ext": ext,
        "track": _pad_num(track),
        "disc": _pad_num(disc),
        "year": year_s,
        "date": date_s,
    }
    out = tpl
    for k, v in mapping.items():
        out = out.replace("{" + k + "}", v)
    # 打错的占位符（{track_no}）宁可丢掉，也别让花括号进文件名
    out = re_sub_placeholders(out)
    segs = [s for s in (_tidy_segment(x) for x in out.replace("\\", "/").split("/")) if s]
    if not segs:
        segs = [mapping["name"]]
    if not segs[-1].lower().endswith("." + ext.lower()):
        segs[-1] = _tidy_segment(segs[-1] + "." + ext)
    parts = [safe_path_component(s, 120) for s in segs]
    rel = Path(*parts) if parts else Path(f"{mapping['name']}.{ext}")
    base = Path(base_dir) if base_dir else Path(".")
    return base / rel


def re_sub_placeholders(s: str) -> str:
    """清掉映射里没有的 {xxx}：花括号是合法文件名字符，留着只会让人以为模板生效了。"""
    import re
    return re.sub(r"\{[^{}]{0,20}\}", "", s)


def is_likely_unavailable(item: dict) -> bool:
    """粗过滤：付费/无版权/空链。"""
    title = (item.get("title") or "").lower()
    q = (item.get("quality") or "").lower()
    url = (item.get("url") or "").strip()
    flags = (item.get("flags") or item.get("note") or item.get("vip") or "")
    if isinstance(flags, bool) and flags:
        return True
    blob = f"{title} {q} {flags}".lower()
    for w in ("付费", "vip专享", "无版权", "下架", "无法播放", "需购买", "数字专辑"):
        if w in blob:
            return True
    if item.get("paid") or item.get("pay") or item.get("need_pay"):
        return True
    # 无任何可下载标识且无 url、无 cache
    if not item.get("can_musicdl_download") and not url and not item.get("id"):
        return True
    return False


def filter_search_results(items: list, *, hide_unavailable: bool = True) -> list:
    if not hide_unavailable:
        return items
    out = []
    for it in items:
        if is_likely_unavailable(it):
            it = dict(it)
            it["unavailable"] = True
            # 仍返回但标记；调用方可以选择过滤
            continue
        out.append(it)
    return out


def range_probe(url: str, timeout: float = 12.0) -> dict:
    """HEAD/Range 探测大小与粗略码率信息。"""
    import urllib.request
    info = {"url": url, "size": 0, "content_type": "", "accept_ranges": False, "bitrate_kbps": None}
    if not url or not str(url).startswith("http"):
        return info
    try:
        req = urllib.request.Request(
            url,
            method="HEAD",
            headers={"User-Agent": "Mozilla/5.0"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            headers = {k.lower(): v for k, v in resp.headers.items()}
            cl = headers.get("content-length") or "0"
            info["size"] = int(cl) if str(cl).isdigit() else 0
            info["content_type"] = headers.get("content-type") or ""
            info["accept_ranges"] = "bytes" in (headers.get("accept-ranges") or "").lower()
    except Exception:
        # 试 Range
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0", "Range": "bytes=0-0"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                headers = {k.lower(): v for k, v in resp.headers.items()}
                cr = headers.get("content-range") or ""
                # bytes 0-0/12345
                if "/" in cr:
                    total = cr.split("/")[-1]
                    if total.isdigit():
                        info["size"] = int(total)
                info["accept_ranges"] = True
                info["content_type"] = headers.get("content-type") or ""
        except Exception:
            pass
    return info


def _norm_music_text(s: str) -> str:
    import re
    import unicodedata
    s = unicodedata.normalize("NFKC", str(s or "")).lower()
    return re.sub(r"[\s·.、,，&\-_/()（）\[\]【】'\"“”‘’:：!！?？*]+", "", s)


def fetch_lyric_fallback_cn(song_name: str, singers: str = "", timeout: float = 10.0) -> str:
    """当 musicdl 自带歌词补全（lrclib）未命中时的兜底：走网易云公开搜索+歌词接口，
    用于中文/华语歌曲（Apple/Spotify 等全球源常见此问题）。
    只接受歌名完全一致、且歌手名有交集的结果——翻唱/钢琴版的歌词比没有歌词更误导人。
    找不到时返回空字符串，不抛异常。"""
    import re
    import urllib.request
    import urllib.parse
    if not song_name:
        return ""
    headers = {"User-Agent": "Mozilla/5.0"}
    want_title = _norm_music_text(song_name)
    want_artists = {_norm_music_text(a) for a in re.split(r"[,/、&;；]", str(singers or "")) if _norm_music_text(a)}
    try:
        search_url = "https://music.163.com/api/search/get/web?" + urllib.parse.urlencode(
            {"type": 1, "s": f"{song_name} {singers}".strip(), "limit": 10}
        )
        req = urllib.request.Request(search_url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore"))
        songs = ((data.get("result") or {}).get("songs") or [])
        picked = None
        for s in songs:
            if _norm_music_text(s.get("name") or "") != want_title:
                continue
            cand_artists = {
                _norm_music_text(a.get("name") or "")
                for a in (s.get("artists") or [])
                if isinstance(a, dict)
            }
            if not want_artists or (want_artists & cand_artists):
                picked = s
                break
        if not picked or not picked.get("id"):
            return ""
        lyric_url = "https://interface3.music.163.com/api/song/lyric?" + urllib.parse.urlencode(
            {"id": picked["id"], "lv": 1, "kv": 1, "tv": -1}
        )
        req2 = urllib.request.Request(lyric_url, headers=headers)
        with urllib.request.urlopen(req2, timeout=timeout) as resp2:
            ldata = json.loads(resp2.read().decode("utf-8", errors="ignore"))
        lrc = ((ldata.get("lrc") or {}).get("lyric") or "").strip()
        return lrc if lrc and lrc not in ("NULL", "None") else ""
    except Exception:
        return ""


def fetch_url_bytes(url: str, timeout: float = 30.0, retries: int = 1) -> bytes:
    """取字节，失败重试一次。

    封面/歌词是附属产物，走的却是同一个代理；实测同一批下载里连续两次
    "SSL: UNEXPECTED_EOF_WHILE_READING"，隔几秒用同一批 URL 又能全部取到 —— 抖动，
    不是链接错。
    """
    import urllib.request
    last: Exception = RuntimeError("未执行")
    for i in range(max(0, int(retries)) + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except Exception as e:
            last = e
            if i < retries:
                time.sleep(1.5)
    raise last


def save_lyrics_and_cover(
    audio_path: str,
    *,
    lyrics_text: str = "",
    lyrics_url: str = "",
    cover_url: str = "",
    embed: bool = False,
    log: Callable = print,
) -> dict:
    """保存同名 .lrc / 封面；可选 ffmpeg 内嵌。"""
    p = Path(audio_path)
    out = {"lrc": "", "cover": "", "embedded": False}
    if not p.is_file():
        return out
    # lyrics
    lrc_body = lyrics_text or ""
    if not lrc_body and lyrics_url:
        try:
            lrc_body = fetch_url_bytes(lyrics_url).decode("utf-8", errors="ignore")
        except Exception as e:
            log(f"歌词下载失败: {e}", "warning")
    if lrc_body.strip():
        lrc_path = p.with_suffix(".lrc")
        lrc_path.write_text(lrc_body, encoding="utf-8")
        out["lrc"] = str(lrc_path)
        log(f"歌词: {lrc_path.name}")
    # cover
    cover_path = None
    if cover_url and str(cover_url).startswith("http"):
        try:
            data = fetch_url_bytes(cover_url)
            ext = ".jpg"
            if ".png" in cover_url.lower():
                ext = ".png"
            elif ".webp" in cover_url.lower():
                ext = ".webp"
            cover_path = p.with_name(p.stem + ext)
            cover_path.write_bytes(data)
            out["cover"] = str(cover_path)
            log(f"封面: {cover_path.name}")
        except Exception as e:
            log(f"封面下载失败: {e}", "warning")
    if embed and (out["lrc"] or out["cover"]):
        try:
            tmp = p.with_name(p.stem + ".embed" + p.suffix)
            cmd = ["ffmpeg", "-y", "-i", str(p)]
            if out["cover"]:
                cmd += ["-i", out["cover"]]
            # 简化：仅贴封面
            if out["cover"]:
                cmd += [
                    "-map", "0", "-map", "1",
                    "-c", "copy",
                    "-disposition:v:0", "attached_pic",
                    str(tmp),
                ]
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                if r.returncode == 0 and tmp.is_file():
                    tmp.replace(p)
                    out["embedded"] = True
                    log("已内嵌封面")
                else:
                    if tmp.exists():
                        tmp.unlink(missing_ok=True)
        except Exception as e:
            log(f"内嵌元数据失败: {e}", "warning")
    return out


def parse_lrc_words(lrc_text: str, *, offset_ms: float = 0.0) -> list:
    """
    高精度 LRC 解析：
    - 支持 [mm:ss.xx] / [mm:ss.xxx] / [mm:ss]
    - 逐字 [t]字[t]字 与 <mm:ss.xx>字
    - 自动推算 end（下一句 start）；末句默认 +4s
    - offset_ms 整体平移（校准）
    返回 [{start, end, text, words:[{start, text}]}]
    """
    import re
    line_re = re.compile(r"\[(\d{1,2}):(\d{2})(?:[\.:](\d{1,3}))?\]")
    word_angle = re.compile(r"<(\d{1,2}):(\d{2})(?:[\.:](\d{1,3}))?>([^<]*)")

    def to_sec(m, s, frac) -> float:
        if not frac:
            ms = 0.0
        elif len(frac) <= 2:
            # centiseconds .xx → 百分之一秒
            ms = int(frac.ljust(2, "0")[:2]) * 10.0
        else:
            ms = int(frac.ljust(3, "0")[:3])
        return int(m) * 60 + int(s) + ms / 1000.0

    offset = float(offset_ms or 0) / 1000.0
    rows = []
    for raw in (lrc_text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        raw = raw.strip()
        if not raw or raw.startswith("[ti:") or raw.startswith("[ar:") or raw.startswith("[al:") or raw.startswith("[by:") or raw.startswith("[offset:"):
            # 文件级 offset
            if raw.lower().startswith("[offset:"):
                try:
                    val = raw.split(":", 1)[1].rstrip("]").strip()
                    offset += float(val) / 1000.0
                except Exception:
                    pass
            continue

        times = list(line_re.finditer(raw))
        if not times:
            continue

        # 逐字：多个 [t]字
        parts = []
        pos = 0
        for m in times:
            if m.start() > pos and parts:
                pass
            parts.append(m)
        # 提取每个时间戳后的文本直到下一个 [
        word_items = []
        for i, m in enumerate(times):
            start_txt = m.end()
            end_txt = times[i + 1].start() if i + 1 < len(times) else len(raw)
            chunk = raw[start_txt:end_txt]
            # 去掉可能的 ]
            chunk = chunk.strip()
            if chunk:
                word_items.append((to_sec(m.group(1), m.group(2), m.group(3)), chunk))

        # 尖括号逐字
        angled = list(word_angle.finditer(raw))
        if len(angled) >= 2:
            words = []
            for m in angled:
                st = to_sec(m.group(1), m.group(2), m.group(3)) + offset
                tx = (m.group(4) or "").strip()
                if tx:
                    words.append({"start": round(st, 3), "text": tx})
            if words:
                text = "".join(w["text"] for w in words)
                rows.append({
                    "start": words[0]["start"],
                    "end": round(words[-1]["start"] + 0.35, 3),
                    "text": text,
                    "words": words,
                })
            continue

        if len(word_items) >= 2 and all(len(tx) <= 8 for _, tx in word_items):
            # 更像逐字
            words = [{"start": round(st + offset, 3), "text": tx} for st, tx in word_items]
            text = "".join(w["text"] for w in words)
            rows.append({
                "start": words[0]["start"],
                "end": round(words[-1]["start"] + 0.35, 3),
                "text": text,
                "words": words,
            })
            continue

        # 行级：同一行多个时间戳共享同一歌词正文
        content = line_re.sub("", raw).strip()
        content = re.sub(r"</?[^>]+>", "", content).strip()
        if not content:
            continue
        for m in times:
            st = round(to_sec(m.group(1), m.group(2), m.group(3)) + offset, 3)
            rows.append({"start": st, "end": st + 4.0, "text": content, "words": []})

    rows.sort(key=lambda x: x["start"])
    # 去重相同 start+text
    deduped = []
    seen = set()
    for r in rows:
        key = (r["start"], r["text"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(r)
    rows = deduped
    for i in range(len(rows) - 1):
        nxt = rows[i + 1]["start"]
        if rows[i]["end"] > nxt:
            rows[i]["end"] = round(max(rows[i]["start"] + 0.05, nxt), 3)
        # 空隙过大时，本句最长 8s
        if rows[i]["end"] - rows[i]["start"] > 8:
            rows[i]["end"] = round(rows[i]["start"] + 8, 3)
    if rows:
        rows[-1]["end"] = round(rows[-1]["start"] + max(2.0, min(6.0, rows[-1]["end"] - rows[-1]["start"])), 3)
    return rows


def shift_lrc_text(lrc_text: str, offset_ms: float) -> str:
    """整体平移 LRC 时间戳并写回文本。"""
    import re
    line_re = re.compile(r"\[(\d{1,2}):(\d{2})(?:[\.:](\d{1,3}))?\]")

    def repl(m):
        frac = m.group(3)
        if not frac:
            ms = 0
            width = 2
        elif len(frac) <= 2:
            ms = int(frac.ljust(2, "0")[:2]) * 10
            width = 2
        else:
            ms = int(frac.ljust(3, "0")[:3])
            width = 3
        total = int(m.group(1)) * 60000 + int(m.group(2)) * 1000 + ms + int(offset_ms)
        if total < 0:
            total = 0
        mm, rem = divmod(total, 60000)
        ss, milli = divmod(rem, 1000)
        if width <= 2:
            return f"[{mm:02d}:{ss:02d}.{milli // 10:02d}]"
        return f"[{mm:02d}:{ss:02d}.{milli:03d}]"

    return line_re.sub(repl, lrc_text or "")


def auto_tag_audio(
    audio_path: str,
    *,
    title: str = "",
    artists: str = "",
    album: str = "",
    cover_path: str = "",
    log: Callable = print,
) -> bool:
    """用 mutagen 写入基础标签；封面可选。"""
    pth = Path(audio_path)
    if not pth.is_file():
        return False
    try:
        from mutagen.easyid3 import EasyID3
        from mutagen.id3 import ID3, APIC, ID3NoHeaderError
        from mutagen.flac import FLAC, Picture
        from mutagen.mp4 import MP4, MP4Cover
    except ImportError:
        log("自动标签需要 mutagen: pip install mutagen", "warning")
        return False
    suf = pth.suffix.lower()
    try:
        if suf == ".mp3":
            try:
                tags = EasyID3(str(pth))
            except Exception:
                ID3().save(str(pth))
                tags = EasyID3(str(pth))
            if title:
                tags["title"] = title
            if artists:
                tags["artist"] = artists
            if album:
                tags["album"] = album
            tags.save()
            if cover_path and Path(cover_path).is_file():
                id3 = ID3(str(pth))
                mime = "image/jpeg"
                if str(cover_path).lower().endswith(".png"):
                    mime = "image/png"
                id3.delall("APIC")
                id3.add(APIC(encoding=3, mime=mime, type=3, desc="Cover", data=Path(cover_path).read_bytes()))
                id3.save(v2_version=3)
        elif suf == ".flac":
            audio = FLAC(str(pth))
            if title:
                audio["title"] = title
            if artists:
                audio["artist"] = artists
            if album:
                audio["album"] = album
            if cover_path and Path(cover_path).is_file():
                pic = Picture()
                pic.type = 3
                pic.mime = "image/png" if str(cover_path).lower().endswith(".png") else "image/jpeg"
                pic.data = Path(cover_path).read_bytes()
                audio.clear_pictures()
                audio.add_picture(pic)
            audio.save()
        elif suf in (".m4a", ".mp4"):
            audio = MP4(str(pth))
            if title:
                audio["\xa9nam"] = [title]
            if artists:
                audio["\xa9ART"] = [artists]
            if album:
                audio["\xa9alb"] = [album]
            if cover_path and Path(cover_path).is_file():
                data = Path(cover_path).read_bytes()
                fmt = MP4Cover.FORMAT_PNG if str(cover_path).lower().endswith(".png") else MP4Cover.FORMAT_JPEG
                audio["covr"] = [MP4Cover(data, imageformat=fmt)]
            audio.save()
        else:
            return False
        log(f"自动标签: {pth.name}")
        return True
    except Exception as e:
        log(f"自动标签失败: {e}", "warning")
        return False





def musicbrainz_search_recordings(
    title: str = "",
    artist: str = "",
    *,
    duration_ms: int = 0,
    limit: int = 8,
    log: Callable = print,
) -> List[dict]:
    """
    MusicBrainz 录音检索 + 简单打分（标题/艺人/时长）。
    遵守 ≤1 req/s；User-Agent 必填。
    """
    import urllib.parse
    import urllib.request
    import time

    parts = []
    if title:
        parts.append(f'recording:"{title}"')
    if artist:
        parts.append(f'artist:"{artist}"')
    if not parts:
        return []
    query = " AND ".join(parts)
    api = (
        "https://musicbrainz.org/ws/2/recording?query="
        + urllib.parse.quote(query)
        + f"&fmt=json&limit={max(1, min(25, limit))}"
    )
    req = urllib.request.Request(
        api,
        headers={"User-Agent": "MediaDownloader/2.6 (local; music-tagger)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        log(f"MusicBrainz 搜索失败: {e}", "warning")
        return []

    results = []
    for rec in data.get("recordings") or []:
        arts = ", ".join(
            (c.get("name") or (c.get("artist") or {}).get("name") or "")
            for c in (rec.get("artist-credit") or [])
        )
        releases = rec.get("releases") or []
        album = releases[0].get("title") if releases else ""
        release_id = releases[0].get("id") if releases else ""
        length = int(rec.get("length") or 0)
        score = float(rec.get("score") or 0)
        # 时长接近加分（±3s）
        if duration_ms and length:
            diff = abs(duration_ms - length)
            if diff <= 1500:
                score += 15
            elif diff <= 3000:
                score += 8
            elif diff > 15000:
                score -= 10
        results.append({
            "id": rec.get("id"),
            "title": rec.get("title"),
            "artists": arts,
            "album": album,
            "length": length,
            "release_id": release_id,
            "score": score,
            "isrcs": rec.get("isrcs") or [],
        })
    results.sort(key=lambda x: -x.get("score", 0))
    return results


def cover_art_front_url(release_mbid: str) -> str:
    """Cover Art Archive 封面（307 到实际图）；无则空串。"""
    if not release_mbid:
        return ""
    return f"https://coverartarchive.org/release/{release_mbid}/front-500"


def musicbrainz_enrich_and_tag(
    audio_path: str,
    *,
    title: str = "",
    artists: str = "",
    album: str = "",
    duration_ms: int = 0,
    download_cover: bool = True,
    log: Callable = print,
) -> dict:
    """
    检索 MB → 选最高分 → mutagen 写标签 → 可选下封面。
    """
    out = {"ok": False, "matched": None, "cover": "", "message": ""}
    hits = musicbrainz_search_recordings(
        title=title, artist=artists, duration_ms=duration_ms, limit=6, log=log,
    )
    if not hits:
        out["message"] = "MusicBrainz 无匹配"
        return out
    best = hits[0]
    out["matched"] = best
    # 轻微限流
    import time
    time.sleep(1.05)

    cover_path = ""
    if download_cover and best.get("release_id"):
        url = cover_art_front_url(best["release_id"])
        try:
            data = fetch_url_bytes(url, timeout=25)
            if data and len(data) > 1000:
                cp = Path(audio_path).with_name(Path(audio_path).stem + ".jpg")
                # CAA 可能是 jpeg
                cp.write_bytes(data)
                cover_path = str(cp)
                out["cover"] = cover_path
                log(f"CAA 封面: {cp.name}")
        except Exception as e:
            log(f"封面获取失败: {e}", "warning")

    ok = auto_tag_audio(
        audio_path,
        title=best.get("title") or title,
        artists=best.get("artists") or artists,
        album=best.get("album") or album,
        cover_path=cover_path,
        log=log,
    )
    out["ok"] = ok
    out["message"] = f"已匹配 {best.get('title')} — {best.get('artists')} (score={best.get('score')})"
    return out


def search_album(
    keyword: str,
    *,
    sources: Optional[List[str]] = None,
    limit: int = 10,
    work_dir: str = "",
    cookies: str = "",
    proxy: str = "",
    proxy_for: Optional[Callable[[str], str]] = None,
    strategy: Optional[dict] = None,
    log: Callable = print,
) -> List[Dict[str, Any]]:
    """
    专辑搜索：优先 musicdl 若支持 album；否则关键词加「专辑」并标记。
    """
    kw = (keyword or "").strip()
    if not kw:
        return []
    # 尝试带专辑后缀搜索
    items = search_music(
        kw + " 专辑",
        sources=sources,
        limit=limit,
        work_dir=work_dir,
        cookies=cookies,
        proxy=proxy,
        proxy_for=proxy_for,
        include_ytdlp=False,
        strategy=strategy,
        log=log,
    )
    for it in items:
        it["search_type"] = "album"
        it["album"] = it.get("album") or kw
    return items


# ── 音频文件元数据（标签 / 时长 / 位深 / 内嵌封面与歌词）────────

LOCAL_AUDIO_EXTS = (".mp3", ".flac", ".m4a", ".aac", ".ogg", ".opus", ".wav", ".wma", ".ape")
_LOCAL_COVER_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif")
_LOCAL_LRC_EXTS = (".lrc", ".txt", ".lyric")
_LOSSLESS_HINTS = ("flac", "alac", "pcm", "tta", "ape", "wavpack", "truehd", "wave", "aiff")

# 键 = 路径|字节数|修改时间；文件没动过就不重复解析（重启后扫一遍即回填）
_LOCAL_META_CACHE: Dict[str, dict] = {}


def find_ffprobe() -> str:
    """随包 tools\\ffprobe.exe 与 PATH 里的都行；找不到回空串，调用方自行降级。"""
    import shutil
    hit = shutil.which("ffprobe") or shutil.which("ffprobe.exe")
    if hit:
        return hit
    name = "ffprobe.exe" if sys.platform == "win32" else "ffprobe"
    bundled = Path(__file__).resolve().parent / "tools" / name
    return str(bundled) if bundled.is_file() else ""


def _meta_int(v: Any) -> int:
    try:
        return int(round(float(v)))
    except (TypeError, ValueError):
        return 0


def _fmt_mmss(seconds: int) -> str:
    return f"{seconds // 60}:{seconds % 60:02d}" if seconds > 0 else ""


def _probe_bit_depth(p: Path) -> dict:
    """ffprobe 只补 mutagen 没给出来的那几项：时长/码率/采样率/位深/编码。"""
    exe = find_ffprobe()
    if not exe:
        return {}
    try:
        r = subprocess.run(
            [exe, "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", str(p)],
            capture_output=True, text=True, timeout=20,
            encoding="utf-8", errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        if r.returncode != 0:
            return {}
        data = json.loads(r.stdout or "{}")
    except Exception:
        return {}
    fmt = data.get("format") or {}
    out: Dict[str, Any] = {}
    try:
        out["duration_s"] = int(round(float(fmt.get("duration") or 0)))
    except (TypeError, ValueError):
        out["duration_s"] = 0
    br = _meta_int(fmt.get("bit_rate"))
    if br:
        out["bitrate_kbps"] = round(br / 1000)
    for s in data.get("streams") or []:
        if s.get("codec_type") != "audio":
            continue
        out["codec"] = str(s.get("codec_name") or "").lower()
        out["sample_rate"] = _meta_int(s.get("sample_rate"))
        out["channels"] = _meta_int(s.get("channels"))
        out["bit_depth"] = _meta_int(s.get("bits_per_raw_sample")) or _meta_int(s.get("bits_per_sample"))
        if not out["duration_s"]:
            out["duration_s"] = _meta_int(s.get("duration"))
        break
    return {k: v for k, v in out.items() if v}


_TITLE_KEYS = ("title", "TIT2", "\xa9nam")
_ARTIST_KEYS = ("artist", "albumartist", "TPE1", "TOPE", "\xa9ART")
_ALBUM_KEYS = ("album", "TALB", "\xa9alb")
_LYRIC_KEYS = ("lyrics", "LYRICS", "\xa9lyr")
# 歌词在不同工具手里有三种落点：Vorbis 的 LYRICS、MP4 的 ©lyr、ID3 的 USLT 或 TXXX:USLT
_LYRIC_WORDS = ("lyric", "uslt", "歌词")


def _tag_first(tags: Any, names: tuple) -> str:
    for n in names:
        try:
            v = tags.get(n) if tags else None
        except Exception:
            v = None
        if v is None:
            continue
        if isinstance(v, (list, tuple)):
            v = ", ".join(str(x).strip() for x in v if str(x).strip())
        s = str(v).strip()
        if s:
            return s
    return ""


def _cover_in_tags(tags: Any) -> bool:
    if tags is None:
        return False
    try:
        if tags.get("covr"):
            return True
        return any(str(k).startswith("APIC") for k in tags.keys())
    except Exception:
        return False


def _is_lyric_key(k: Any) -> bool:
    ks = str(k)
    if ks in _LYRIC_KEYS or ks.startswith("USLT"):
        return True
    if ks.startswith("TXXX"):
        desc = ks.split(":", 1)[1].lower() if ":" in ks else ""
        return any(w in desc for w in _LYRIC_WORDS)
    return False


def _lyric_in_tags(tags: Any) -> bool:
    if tags is None:
        return False
    try:
        keys = list(tags.keys())
    except Exception:
        return False
    for k in keys:
        if not _is_lyric_key(k):
            continue
        try:
            v = tags.get(k)
        except Exception:
            continue
        if isinstance(v, (list, tuple)):
            v = " ".join(str(x) for x in v)
        if str(v).strip():
            return True
    return False


def _meta_key(p: Path) -> str:
    """缓存键：路径 + 字节数 + 修改时间；文件没动过就认定元数据还是那份。"""
    try:
        st = p.stat()
        return f"{p}|{st.st_size}|{int(st.st_mtime)}"
    except Exception:
        return ""


def audio_file_meta(path: str, *, use_cache: bool = True, log: Callable = print) -> dict:
    """读一个音频文件自带的元数据；文件名猜的只当兜底。

    mutagen 能给的都从 mutagen 拿（一次解析、无子进程），只有位深这类它给不出的
    才问 ffprobe；两者都拿不到就返回空字段，让调用方按文件名继续。
    """
    p = Path(str(path))
    key = _meta_key(p) if use_cache else ""
    if key and key in _LOCAL_META_CACHE:
        return dict(_LOCAL_META_CACHE[key])

    meta: Dict[str, Any] = {"title": "", "artists": "", "album": "", "duration": "", "duration_s": 0,
                            "quality": "", "bitrate_kbps": 0, "sample_rate": 0, "bit_depth": 0,
                            "channels": 0, "codec": "", "tag_type": "", "lossless": False,
                            "has_cover": False, "has_lyrics": False, "reader": ""}
    mf = None
    try:
        from mutagen import File as _MFile
        mf = _MFile(str(p))
        meta["reader"] = "mutagen" if mf is not None else ""
    except ImportError:
        meta["reader"] = ""
        log(f"未安装 mutagen，{p.name} 的标签改由 ffprobe 探测", "warning")
    except Exception:
        mf = None
        meta["reader"] = ""

    if mf is not None:
        tags = getattr(mf, "tags", None)
        meta["title"] = _tag_first(tags, _TITLE_KEYS)
        meta["artists"] = _tag_first(tags, _ARTIST_KEYS)
        meta["album"] = _tag_first(tags, _ALBUM_KEYS)
        meta["has_cover"] = bool(getattr(mf, "pictures", None)) or _cover_in_tags(tags)
        meta["has_lyrics"] = _lyric_in_tags(tags)
        meta["tag_type"] = type(mf).__name__.lower()
        meta["codec"] = meta["tag_type"]
        info = getattr(mf, "info", None)
        if info is not None:
            meta["duration_s"] = _meta_int(getattr(info, "length", 0))
            meta["bitrate_kbps"] = round(_meta_int(getattr(info, "bitrate", 0)) / 1000)
            meta["sample_rate"] = _meta_int(getattr(info, "sample_rate", 0))
            meta["bit_depth"] = _meta_int(getattr(info, "bits_per_sample", 0))

    probe = {}
    if not meta["bit_depth"] or not meta["sample_rate"] or not meta["duration_s"]:
        probe = _probe_bit_depth(p)
        for k, v in probe.items():
            if k == "reader" or not v:
                continue
            if not meta.get(k) or k == "codec":
                meta[k] = v
    if probe:
        meta["reader"] = "+".join(x for x in (meta["reader"], "ffprobe") if x)

    blob = f"{meta['codec']} {meta['tag_type']} {p.suffix.lower()}"
    meta["lossless"] = any(h in blob for h in _LOSSLESS_HINTS) or (
        meta["bit_depth"] >= 16 and not meta["bitrate_kbps"])
    if meta["lossless"]:
        meta["quality"] = "flac" + (f" {meta['bit_depth']}bit" if meta["bit_depth"] >= 16 else "")
    elif meta["bitrate_kbps"]:
        meta["quality"] = f"{meta['bitrate_kbps']}k"
    else:
        meta["quality"] = p.suffix.lower().lstrip(".")
    meta["duration"] = _fmt_mmss(meta["duration_s"])

    if key:
        _LOCAL_META_CACHE[key] = dict(meta)
    return dict(meta)


def _sibling_media(p: Path, exts) -> str:
    for e in exts:
        q = p.with_suffix(e)
        if q.is_file():
            return str(q)
    return ""


def audio_embedded_cover(path: str) -> tuple:
    """取出音频内嵌的封面图片，返回 (字节, mime)；没有则 ("", "")。"""
    try:
        from mutagen import File as _MFile
        mf = _MFile(str(path))
    except Exception:
        return "", ""
    if mf is None:
        return "", ""
    found = []
    for pic in (getattr(mf, "pictures", None) or []):
        data = getattr(pic, "data", None)
        if data:
            found.append((bytes(data), str(getattr(pic, "mime", "") or "").strip()))
    tags = getattr(mf, "tags", None)
    if tags is not None:
        try:
            keys = list(tags.keys())
        except Exception:
            keys = []
        for k in keys:
            if not str(k).startswith("APIC"):
                continue
            frame = tags.get(k)
            data = getattr(frame, "data", None)
            if data:
                found.append((bytes(data), str(getattr(frame, "mime", "") or "").strip()))
    if not found:
        return "", ""
    # 有些文件把 1x1 占位图当封面，选最大的那张
    data, mime = max(found, key=lambda x: len(x[0]))
    return data, (mime if mime.startswith("image/") else "image/jpeg")


def audio_embedded_lyrics(path: str) -> str:
    """取音频内嵌歌词文本；mutagen 的键名随容器不同，几套都试一遍。"""
    try:
        from mutagen import File as _MFile
        mf = _MFile(str(path))
    except Exception:
        return ""
    if mf is None:
        return ""
    tags = getattr(mf, "tags", None)
    if tags is None:
        return ""
    found = []
    try:
        keys = list(tags.keys())
    except Exception:
        keys = []
    for k in keys:
        if not _is_lyric_key(k):
            continue
        try:
            v = tags.get(k)
        except Exception:
            continue
        if isinstance(v, (list, tuple)):
            v = "\n".join(str(x) for x in v if str(x).strip())
        s = str(v or "").strip()
        if s:
            found.append(s)
    if not found:
        return ""
    return max(found, key=len)


# 本地索引里要落盘、又能整体回填内存缓存的那几项
_META_ROW_KEYS = ("title", "artists", "album", "duration", "duration_s", "quality",
                  "bitrate_kbps", "sample_rate", "bit_depth", "channels", "codec",
                  "tag_type", "lossless", "has_cover", "has_lyrics", "reader", "tagged")


def _warm_meta_cache(old_items: List[dict]) -> int:
    """把上次索引里「文件没动过」的行灌回内存缓存，省掉整轮重复解析。"""
    n = 0
    for it in old_items or []:
        if not all(k in it for k in _META_ROW_KEYS):
            continue
        path = str(it.get("path") or "")
        key = f"{path}|{it.get('size')}|{it.get('mtime')}"
        if not path or key in _LOCAL_META_CACHE or _meta_key(Path(path)) != key:
            continue
        _LOCAL_META_CACHE[key] = {k: it.get(k) for k in _META_ROW_KEYS}
        n += 1
    return n


# ── 本地音乐索引（快照 + TTL + 后台刷新）────────────────────
# 索引文件落在程序目录，不落被扫描的目录：那是用户的下载目录， generated 文件不该留在那儿。
_LOCAL_INDEX_DIR = Path(__file__).resolve().parent / "local_index"
_LEGACY_INDEX_NAME = "local_music_index.json"
# 这段时间内搜索直接用现成的那份索引，不重扫目录；过期的先回旧的那份，重扫放后台
LOCAL_INDEX_TTL_S = 300
# 「扫描本地库」最多等多久后台那份在跑的扫描，超过就退回旧索引（上千首的目录也够扫完了）
_LOCAL_SCAN_JOIN_S = 90.0
_LOCAL_SNAP: Dict[str, dict] = {}
_LOCAL_SNAP_LOCK = threading.Lock()
_LOCAL_SCANNING: set = set()


def _index_key(root: str) -> str:
    import hashlib
    raw = str(root or "").strip().strip('"')
    try:
        # absolute() 不碰文件系统，也就不会像 resolve() 那样在 Windows 上冒出 \\?\ 前缀
        raw = str(Path(raw).absolute())
    except Exception:
        pass
    raw = raw.replace("\\", "/").rstrip("/").lower()
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def local_index_path(root: str) -> Path:
    """这一份索引落在程序目录的哪个文件 —— 界面提示与打包排除都问它。"""
    return _LOCAL_INDEX_DIR / f"local_music_index_{_index_key(root)}.json"


def _migrate_legacy_index(root: str, dst: Path) -> None:
    """老版本把索引写在被扫描的目录里；读到就把这份搬走，不留垃圾也不重解析。

    搬走时把旧文件的时间一起带过去：那是一份一小时前扫出来的索引，
    如果新文件的 mtime 变成"现在"，TTL 就再也判不出它旧，重扫永远不会发生。
    """
    old = Path(root) / _LEGACY_INDEX_NAME
    if not old.is_file():
        return
    import os
    try:
        st = old.stat()
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not dst.exists():
            dst.write_bytes(old.read_bytes())
            os.utime(dst, (st.st_atime, st.st_mtime))
        old.unlink()
    except Exception:
        pass


def _read_snapshot(root: str) -> Optional[dict]:
    path = local_index_path(root)
    _migrate_legacy_index(root, path)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if isinstance(data, list):                      # 老格式：整个文件就是条目数组，扫描时刻按文件时间算
        return {"items": data, "ts": path.stat().st_mtime}
    if isinstance(data, dict) and isinstance(data.get("items"), list):
        return {"items": data["items"],
                "ts": float(data.get("scanned_at") or path.stat().st_mtime)}
    return None


def save_local_index(root: str, items: list) -> Path:
    path = local_index_path(root)
    ts = time.time()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"root": str(root), "scanned_at": ts,
                                "count": len(items), "items": items},
                               ensure_ascii=False, indent=0), encoding="utf-8")
    with _LOCAL_SNAP_LOCK:
        _LOCAL_SNAP[_index_key(root)] = {"items": list(items), "ts": ts}
    return path


def load_local_index(root: str) -> List[dict]:
    snap = _read_snapshot(root)
    return list(snap["items"]) if snap else []


def _scan_and_save(root: str, log: Callable, *, join_wait: float = 0.0) -> Optional[List[dict]]:
    """真扫一遍目录并落盘。同一个目录同时只让一个扫描在跑。

    ``join_wait`` 是给「扫描本地库」那个按钮的：后台正好在扫同一份时，等它扫完并直接
    拿它刚落好的那份，而不是退回旧索引 —— 按了按钮界面却没变，比多等几秒更难看。
    """
    key = _index_key(root)
    _migrate_legacy_index(root, local_index_path(root))   # 顺手清掉老版本留在这个目录里的索引
    deadline = time.time() + max(0.0, join_wait)
    waited = False
    while True:
        with _LOCAL_SNAP_LOCK:
            idle = key not in _LOCAL_SCANNING
            if idle:
                _LOCAL_SCANNING.add(key)
        if idle:
            break
        waited = True
        if time.time() >= deadline:
            return None
        time.sleep(0.2)
    if waited and join_wait > 0:
        with _LOCAL_SNAP_LOCK:
            mem = _LOCAL_SNAP.get(key)
        if mem:
            return list(mem["items"])          # 等到的那次扫描已经把新索引落好了
    try:
        items = scan_local_music(root, log=log)
        save_local_index(root, items)
        return items
    except Exception as e:
        log(f"本地索引刷新失败: {e}", "warning")
        return None
    finally:
        with _LOCAL_SNAP_LOCK:
            _LOCAL_SCANNING.discard(key)


def local_music_snapshot(root: str, *, log: Callable = print,
                         ttl: float = LOCAL_INDEX_TTL_S, force: bool = False) -> List[dict]:
    """本地索引的统一读法：TTL 内直接用现成的那份，过期先回上次结果、重扫放后台。

    判重那一步要精确（刚下完的歌不能当成不存在），那里传 ``ttl=0`` 让它当场重扫。
    """
    key = _index_key(root)
    now = time.time()
    if not force and ttl > 0:
        with _LOCAL_SNAP_LOCK:
            mem = _LOCAL_SNAP.get(key)
        if mem and now - float(mem.get("ts") or 0) <= ttl:
            return list(mem["items"])
        snap = _read_snapshot(root)
        if snap:
            with _LOCAL_SNAP_LOCK:
                _LOCAL_SNAP[key] = snap
            if now - float(snap.get("ts") or 0) <= ttl:
                return list(snap["items"])
            threading.Thread(target=_scan_and_save, args=(root, log), daemon=True).start()
            return list(snap["items"])              # 秒开：先用上次那份
    # force：后台正好在扫同一份就等它，别退回旧索引；非 force 的并发读仍然各走各的，不排队
    items = _scan_and_save(root, log, join_wait=_LOCAL_SCAN_JOIN_S if force else 0.0)
    if items is not None:
        return items
    with _LOCAL_SNAP_LOCK:
        mem = _LOCAL_SNAP.get(key)
    if mem:
        return list(mem["items"])
    return []


def refresh_local_snapshot(root: str, *, log: Callable = print) -> None:
    """刚下完歌：后台重扫一遍，下次搜索/判重就看得见这份新成品。"""
    threading.Thread(target=_scan_and_save, args=(root, log), daemon=True).start()


def search_local_music(keyword: str, root: str, limit: int = 30,
                       log: Callable = print) -> List[dict]:
    kw = (keyword or "").strip().lower()
    items = local_music_snapshot(root, log=log)
    if not kw:
        return items[:limit]
    out = []
    for it in items:
        blob = f"{it.get('title','')} {it.get('artists','')} {it.get('album','')}".lower()
        if kw in blob:
            out.append(it)
        if len(out) >= limit:
            break
    return out


def scan_local_music(root: str, log: Callable = print) -> List[dict]:
    root_p = Path(root)
    if not root_p.is_dir():
        return []
    warmed = _warm_meta_cache(load_local_index(root))
    items = []
    parsed = 0
    from urllib.parse import quote as q
    for p in sorted(root_p.rglob("*")):
        if not p.is_file() or p.name.startswith(".") or p.suffix.lower() not in LOCAL_AUDIO_EXTS:
            continue
        try:
            st = p.stat()
        except Exception:
            continue
        key = _meta_key(p)
        fresh = bool(key) and key in _LOCAL_META_CACHE
        if not fresh:
            parsed += 1
        meta = audio_file_meta(str(p))
        stem = p.stem
        f_artist, f_title = "", stem
        if " - " in stem:
            a, b = stem.split(" - ", 1)
            f_artist, f_title = a.strip(), b.strip()
        cover = _sibling_media(p, _LOCAL_COVER_EXTS)
        lyrics = _sibling_media(p, _LOCAL_LRC_EXTS)
        row = {
            "id": f"local:{p}",
            "title": meta["title"] or f_title,
            "artists": meta["artists"] or f_artist,
            "album": meta["album"] or (p.parent.name if p.parent != root_p else ""),
            "tagged": bool(meta["title"] or meta["artists"] or meta["album"]),
            "duration": meta["duration"],
            "source": "local",
            "musicdl_source": "",
            "url": str(p),
            "quality": meta["quality"],
            "cover": cover,
            "cover_url": (f"/api/files/stream?path={q(str(cover))}" if cover
                          else (f"/api/music/local_cover?path={q(str(p))}"
                                if meta["has_cover"] else "")),
            "lyrics_path": lyrics,
            "can_musicdl_download": False,
            "is_local": True,
            "size": st.st_size,
            "mtime": int(st.st_mtime),
            "path": str(p),
        }
        for k in _META_ROW_KEYS:
            if k not in ("title", "artists", "album", "duration", "quality", "tagged"):
                row[k] = meta.get(k)
        items.append(row)
    cached = len(items) - parsed
    log(f"本地音乐扫描: {len(items)} 首 @ {root}"
        f"（其中 {cached} 首元数据走缓存，未变动不重解析；索引回填 {warmed} 首）")
    return items


# ── AcoustID / Chromaprint 指纹识别 ──────────────────────────

def find_fpcalc() -> str:
    import shutil
    hit = shutil.which("fpcalc") or shutil.which("fpcalc.exe")
    if hit:
        return hit
    # 「一键配置 PATH」只写用户注册表，已经在跑的进程读不到，所以要能直接用随包那一份
    bundled = Path(__file__).resolve().parent / "chromaprint" / "fpcalc.exe"
    return str(bundled) if bundled.is_file() else ""


def fpcalc_fingerprint(audio_path: str, log: Callable = print) -> dict:
    """
    调用 Chromaprint fpcalc 生成指纹。
    返回 {duration, fingerprint, raw}；失败则空。
    """
    import json as _json
    path = Path(audio_path)
    if not path.is_file():
        return {}
    bin_path = find_fpcalc()
    if not bin_path:
        log("未找到 fpcalc（Chromaprint）。请安装后加入 PATH。", "warning")
        return {}
    try:
        r = subprocess.run(
            [bin_path, "-json", str(path)],
            capture_output=True, text=True, timeout=300,
        )
        if r.returncode != 0:
            # 部分版本用 -text
            r2 = subprocess.run(
                [bin_path, "-text", str(path)],
                capture_output=True, text=True, timeout=300,
            )
            if r2.returncode != 0:
                log(f"fpcalc 失败: {(r.stderr or r2.stderr or '')[:200]}", "warning")
                return {}
            # DURATION=xx\nFINGERPRINT=yy
            duration, fp = 0.0, ""
            for line in (r2.stdout or "").splitlines():
                if line.startswith("DURATION="):
                    try:
                        duration = float(line.split("=", 1)[1])
                    except Exception:
                        pass
                elif line.startswith("FINGERPRINT="):
                    fp = line.split("=", 1)[1].strip()
            return {"duration": duration, "fingerprint": fp, "raw": r2.stdout}
        data = _json.loads(r.stdout or "{}")
        return {
            "duration": float(data.get("duration") or 0),
            "fingerprint": data.get("fingerprint") or "",
            "raw": data,
        }
    except Exception as e:
        log(f"fpcalc 异常: {e}", "warning")
        return {}


def _acoustid_err_text(e) -> str:
    """把 AcoustID 的错误原文取出来：只回 HTTP 状态码看不出是 Key 的问题。"""
    import urllib.error

    body = ""
    try:
        if isinstance(e, urllib.error.HTTPError):
            raw = json.loads(e.read().decode("utf-8", "ignore"))
            body = str((raw.get("error") or {}).get("message") or raw.get("status") or "")
    except Exception:
        body = ""
    code = getattr(e, "code", None) or "错误"
    return f"HTTP {code}：{body}" if body else str(e)


def acoustid_key_check(api_key: str, log: Callable = print) -> str:
    """拿一条假指纹先问一次：/v2/lookup 只认「应用」的 client key，填成账户的 user key 会被拒。"""
    import urllib.error
    import urllib.parse
    import urllib.request

    if not api_key:
        return "未填写 AcoustID Key"
    qs = urllib.parse.urlencode({
        "client": api_key, "meta": "recordings", "duration": 1, "fingerprint": "AQAA",
    })
    req = urllib.request.Request(
        "https://api.acoustid.org/v2/lookup?" + qs,
        headers={"User-Agent": "MediaDownloader/2.6 (local; acoustid)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            json.loads(resp.read().decode("utf-8", "ignore"))
        return ""
    except urllib.error.HTTPError as e:
        txt = _acoustid_err_text(e)
        if "api key" in txt.lower():
            return (f"AcoustID 拒绝了这个 Key（{txt}）。/v2/lookup 要的是「应用」的 client key，"
                    "在 https://acoustid.org/manage/client 注册一个应用获取；"
                    "登录账户后看到的 user API key 不能用于此处")
        return f"AcoustID 返回 {txt}"
    except Exception as e:
        return f"连不上 AcoustID：{str(e)[:160]}"


def acoustid_lookup(
    fingerprint: str,
    duration: float,
    *,
    api_key: str,
    log: Callable = print,
) -> List[dict]:
    """
    AcoustID lookup → 候选 recording（含 score、title、artist、mbid）。
    """
    import urllib.parse
    import urllib.request
    if not fingerprint or not api_key:
        return []
    qs = urllib.parse.urlencode({
        "client": api_key,
        "meta": "recordings+releasegroups+compress",
        "duration": int(round(float(duration) or 0)),
        "fingerprint": fingerprint,
    })
    url = "https://api.acoustid.org/v2/lookup?" + qs
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "MediaDownloader/2.6 (local; acoustid)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore"))
    except urllib.error.HTTPError as e:
        log(f"AcoustID 查询失败: {_acoustid_err_text(e)}", "warning")
        return []
    except Exception as e:
        log(f"AcoustID 查询失败: {e}", "warning")
        return []
    if data.get("status") != "ok":
        log(f"AcoustID 状态: {data.get('status')} {data.get('error')}", "warning")
        return []
    out = []
    for res in data.get("results") or []:
        score = float(res.get("score") or 0)
        for rec in res.get("recordings") or []:
            arts = ", ".join(
                a.get("name") or ""
                for a in (rec.get("artists") or [])
            )
            rgs = rec.get("releasegroups") or []
            album = (rgs[0].get("title") if rgs else "") or ""
            out.append({
                "score": score,
                "recording_id": rec.get("id") or "",
                "title": rec.get("title") or "",
                "artists": arts,
                "album": album,
                "acoustid": res.get("id") or "",
            })
    out.sort(key=lambda x: -x.get("score", 0))
    return out


def fingerprint_and_tag(
    audio_path: str,
    *,
    api_key: str,
    min_score: float = 0.5,
    download_cover: bool = True,
    log: Callable = print,
) -> dict:
    """
    方案 A：fpcalc → AcoustID → mutagen 写标签（+ 可选 CAA 封面）。
    """
    out = {"ok": False, "message": "", "matches": [], "fpcalc": bool(find_fpcalc())}
    if not api_key:
        out["message"] = "请在设置中填写 AcoustID API Key（https://acoustid.org/api-key）"
        return out
    fp = fpcalc_fingerprint(audio_path, log=log)
    if not fp.get("fingerprint"):
        out["message"] = "指纹计算失败（需安装 fpcalc / Chromaprint）"
        return out
    matches = acoustid_lookup(
        fp["fingerprint"], fp.get("duration") or 0, api_key=api_key, log=log,
    )
    out["matches"] = matches[:5]
    if not matches or matches[0].get("score", 0) < min_score:
        out["message"] = f"无高置信匹配（最佳 score={matches[0]['score'] if matches else 0:.2f}）"
        return out
    best = matches[0]
    cover_path = ""
    # 用 recording 再查 MB 拿 release 封面（可选，限流）
    if download_cover and best.get("recording_id"):
        try:
            import time
            import urllib.request
            time.sleep(1.05)
            api = f"https://musicbrainz.org/ws/2/recording/{best['recording_id']}?inc=releases&fmt=json"
            req = urllib.request.Request(
                api, headers={"User-Agent": "MediaDownloader/2.6 (local; acoustid)"},
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                rec = json.loads(resp.read().decode("utf-8", errors="ignore"))
            releases = (rec.get("recording") or {}).get("releases") or []
            rid = releases[0].get("id") if releases else ""
            if rid:
                time.sleep(1.05)
                url = cover_art_front_url(rid)
                data = fetch_url_bytes(url, timeout=25)
                if data and len(data) > 1000:
                    cp = Path(audio_path).with_name(Path(audio_path).stem + ".jpg")
                    cp.write_bytes(data)
                    cover_path = str(cp)
        except Exception as e:
            log(f"指纹路径封面: {e}", "warning")

    ok = auto_tag_audio(
        audio_path,
        title=best.get("title") or "",
        artists=best.get("artists") or "",
        album=best.get("album") or "",
        cover_path=cover_path,
        log=log,
    )
    out["ok"] = ok
    out["message"] = (
        f"AcoustID 匹配 score={best.get('score'):.2f}: "
        f"{best.get('title')} — {best.get('artists')}"
    )
    return out


def brainztag_style_guess(path: str) -> dict:
    """
    方案 D 轻量思路：从路径/文件名猜测 artist/album/title（类似 brainztag）。
    不调用外部 CLI，纯启发式。
    """
    pth = Path(path)
    title = pth.stem
    artists, album = "", ""
    # 目录名常为 "Artist - Album"
    parent = pth.parent.name
    if " - " in parent:
        a, b = parent.split(" - ", 1)
        artists, album = a.strip(), b.strip()
    if " - " in title:
        a, b = title.split(" - ", 1)
        if not artists:
            artists = a.strip()
        title = b.strip()
    # 去曲序号 01. 01-
    import re
    title = re.sub(r"^\d{1,3}[\s.\-_]+", "", title).strip()
    return {"title": title, "artists": artists, "album": album}

