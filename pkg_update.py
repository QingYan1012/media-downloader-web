"""组件 / 依赖的统一更新入口。

两类东西：
- 二进制工具（yt-dlp.exe、ffmpeg、N_m3u8DL-RE）：从 GitHub release 拉，直连不通时按镜像前缀依次试。
- Python 依赖（musicdl、mutagen、edge-tts…）：用 pip 装，按镜像源依次试。
便携包内嵌的 runtime 也带 pip，所以对方在网页里点「更新」就能自己升级，不用重新发包。
"""
from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from typing import Callable, Dict, List, Sequence, Tuple

# 空串 = 官方直连；国内网络按顺序往后退
PIP_MIRRORS: List[str] = [
    "",
    "https://pypi.tuna.tsinghua.edu.cn/simple",
    "https://mirrors.aliyun.com/pypi/simple/",
    "https://mirrors.ustc.edu.cn/pypi/simple",
]

# 拼在 GitHub 原始链接前面的加速前缀（同样空串 = 直连）
GITHUB_MIRRORS: List[str] = [
    "",
    "https://ghproxy.net/",
    "https://mirror.ghproxy.com/",
    "https://gh.ddlc.top/",
]

# 只在设置页「一键获取可用镜像」里参与测速的额外候选。
# 不进上面的回退链：回退链越长，真下载时逐个失败等待越久。
PIP_MIRROR_EXTRA: List[str] = [
    "https://mirrors.huaweicloud.com/repository/pypi/simple",
    "https://mirrors.cloud.tencent.com/pypi/simple",
    "https://mirrors.163.com/pypi/simple",
    "https://pypi.doubanio.com/simple",
]
GITHUB_MIRROR_EXTRA: List[str] = [
    "https://gh-proxy.com/",
    "https://ghfast.top/",
    "https://hub.gitmirror.com/",
]

# 测速结果给人看的名字（认不出来就直接显示地址）
MIRROR_NAMES = {
    "https://pypi.tuna.tsinghua.edu.cn/simple": "清华 TUNA",
    "https://mirrors.aliyun.com/pypi/simple/": "阿里云",
    "https://mirrors.ustc.edu.cn/pypi/simple": "中科大 USTC",
    "https://mirrors.huaweicloud.com/repository/pypi/simple": "华为云",
    "https://mirrors.cloud.tencent.com/pypi/simple": "腾讯云",
    "https://mirrors.163.com/pypi/simple": "网易",
    "https://pypi.doubanio.com/simple": "豆瓣",
    "https://ghproxy.net/": "ghproxy",
    "https://mirror.ghproxy.com/": "mirror.ghproxy",
    "https://gh.ddlc.top/": "ddlc",
    "https://gh-proxy.com/": "gh-proxy",
    "https://ghfast.top/": "ghfast",
    "https://hub.gitmirror.com/": "gitmirror",
}

# 网页「组件与依赖」面板里可点更新的 Python 依赖
# cn = 面板上给人看的那一行中文（用户看用途，不看包名）；label 留全名，日志与悬停提示用
PIP_PACKAGES: List[dict] = [
    {"name": "yt-dlp", "cn": "解析规则（Python 包）",
     "label": "yt-dlp Python 包（tools\\ 里没有 exe 时才用它）"},
    {"name": "musicdl", "cn": "音乐搜索 / 歌词 / 封面", "label": "musicdl（音乐搜索 / 歌词 / 封面）"},
    {"name": "zhconv", "cn": "繁简归一",
     "label": "zhconv（匹配前繁简归一，不装则繁體歌单在简体曲库里匹配不上）"},
    {"name": "mutagen", "cn": "音频标签写入", "label": "mutagen（音频标签写入）"},
    {"name": "edge-tts", "cn": "字幕配音", "label": "edge-tts（配音合成）"},
    {"name": "deep-translator", "cn": "字幕机翻", "label": "deep-translator（字幕翻译）"},
    {"name": "telethon", "cn": "Telegram 私有频道", "label": "telethon（Telegram 私有/受限频道会话）"},
    {"name": "python-socks", "cn": "Telegram 走 SOCKS5",
     "label": "python-socks（telethon 走 SOCKS5 代理要装）"},
    {"name": "cryptg", "cn": "Telegram 加密加速",
     "label": "cryptg（telethon 加密加速，不装会退回纯 Python、Telegram 操作明显变慢）"},
    {"name": "psutil", "cn": "录制收尾收进程",
     "label": "psutil（结束直播录制时收掉拉流的 ffmpeg 子进程，不装则成品可能一直变大、删不掉）"},
    {"name": "numpy", "cn": "音频分析基础库", "label": "numpy（音频分析 / 说话人分离）"},
    {"name": "librosa", "cn": "节拍 / 响度 / 调性",
     "label": "librosa（音频分析：节拍 / 响度 / 调性，会带 numba，体积较大）"},
    {"name": "faster-whisper", "cn": "本地转写", "label": "faster-whisper（本地转写，体积大）"},
    {"name": "bgutil-ytdlp-pot-provider", "cn": "YouTube 取票插件",
     "label": "bgutil PO Token 插件（yt-dlp 要票的客户端靠它取票；服务端不在这里）"},
]


def _emit(log: Callable, msg: str, level: str = "info") -> None:
    """log 可能是 print（不接 level），也可能是 log_mgr.log(msg, level)。"""
    if log is print:
        print(msg)
        return
    try:
        log(msg, level)
    except TypeError:
        log(msg)


def pip_available() -> bool:
    return importlib.util.find_spec("pip") is not None


def pip_version() -> str:
    try:
        import pip

        return getattr(pip, "__version__", "") or ""
    except Exception:
        return ""


def installed_version(pkg: str) -> str:
    try:
        from importlib.metadata import version

        return version(pkg)
    except Exception:
        return ""


def _parse_index_latest(out: str) -> str:
    """从 `pip index versions` 的输出里取最新版：优先 LATEST 行，回落首行「包名 (版本)」。"""
    m = re.search(r"LATEST:\s*([^\s]+)", out)
    if m:
        return m.group(1).strip()
    m = re.match(r"\s*\S+\s+\(([^)]+)\)", out)
    return m.group(1).strip() if m else ""


def latest_version(pkg: str, mirror: str = "", timeout: int = 20) -> Tuple[str, str]:
    """查某个包的上游最新版。返回 (版本号, 命中的源或失败原因)。

    问 pip 本人要索引版本，而不是自己拼 PyPI 的 JSON 接口 —— 这样设置里的镜像照样生效。
    只试「用户镜像 → 官方直连」两个候选：镜像链再长也只会把组件页多卡几分钟。
    """
    if not pip_available():
        return "", "当前 Python 环境没有 pip"
    last = ""
    for idx in mirror_order(mirror)[:2]:
        cmd = [sys.executable, "-m", "pip", "index", "versions", pkg,
               "--disable-pip-version-check", "--no-input"]
        if idx:
            cmd += ["-i", idx]
        try:
            r = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            out = (r.stdout or "") + (r.stderr or "")
            ver = _parse_index_latest(out)
            if ver:
                return ver, idx or "official"
            last = out.strip().replace("\n", " ")[-160:]
        except Exception as e:
            last = f"{type(e).__name__}: {str(e)[:120]}"
    return "", f"没查到（{'所有候选源都失败' if last else '无输出'}）：{last}"


def latest_versions(pkgs: Sequence[str], mirror: str = "") -> Dict[str, dict]:
    """并发查一批包的最新版；单个失败只影响它自己那一行。"""
    from concurrent.futures import ThreadPoolExecutor

    names = [p for p in dict.fromkeys(pkgs) if p]
    if not names:
        return {}
    with ThreadPoolExecutor(max_workers=min(5, len(names))) as ex:
        rows = list(ex.map(lambda n: (n, *latest_version(n, mirror)), names))
    return {n: {"version": v, "source": src, "error": "" if v else src}
            for n, v, src in rows}


def mirror_order(user_mirror: str = "") -> List[str]:
    """用户指定的镜像排第一，其余候选按内置顺序补在后面。"""
    m = (user_mirror or "").strip()
    out = [m] if m else []
    out.extend(x for x in PIP_MIRRORS if x != m)
    return out


def github_url_candidates(url: str, user_mirror: str = "") -> List[str]:
    """GitHub 直连 + 各镜像前缀的候选顺序：用户镜像 → 直连 → 内置镜像。"""
    if not url.startswith("http"):
        return [url]
    m = (user_mirror or "").strip()
    order = ([m] if m else []) + [""] + [x for x in GITHUB_MIRRORS if x and x != m]
    seen, uniq = set(), []
    for prefix in order:
        u = (prefix.rstrip("/") + "/" + url) if prefix else url
        if u not in seen:
            seen.add(u)
            uniq.append(u)
    return uniq


def _probe_target(kind: str, mirror: str) -> str:
    """给每个候选镜像挑一个体积极小、必定存在的真实地址来测。"""
    m = (mirror or "").strip()
    if kind == "pypi":
        return (m or "https://pypi.org/simple").rstrip("/") + "/six/"
    return (m.rstrip("/") + "/" if m else "") + "https://github.com/octocat/Hello-World/raw/master/README"


def probe_mirrors(kind: str = "pypi", timeout: float = 6.0) -> List[dict]:
    """并发实测内置镜像：能不能连通、多少毫秒。空串代表官方直连。"""
    import time
    from concurrent.futures import ThreadPoolExecutor

    import requests

    cands = []
    for m in (PIP_MIRRORS + PIP_MIRROR_EXTRA if kind == "pypi" else GITHUB_MIRRORS + GITHUB_MIRROR_EXTRA):
        if m not in cands:
            cands.append(m)

    def one(m: str) -> dict:
        url = _probe_target(kind, m)
        t0 = time.time()
        ok, code = False, ""
        try:
            r = requests.get(url, timeout=timeout, stream=True, verify=False)
            ok, code = r.status_code < 400, r.status_code
            r.close()
        except Exception as e:
            code = type(e).__name__
        named = MIRROR_NAMES.get(m)
        plain = m or ("官方源" if kind == "pypi" else "直连 GitHub")
        return {
            "mirror": m,
            "label": plain,
            "named": (named + " · " + m) if named else plain,
            "ok": ok,
            "code": code,
            "ms": int((time.time() - t0) * 1000),
        }

    with ThreadPoolExecutor(max_workers=max(1, min(8, len(cands)))) as ex:
        rows = list(ex.map(one, cands))
    rows.sort(key=lambda x: (not x["ok"], x["ms"]))
    return rows


def pip_install(
    pkgs: Sequence[str] | str,
    log: Callable = print,
    mirror: str = "",
    timeout: int = 600,
) -> Tuple[bool, str]:
    """pip install -U，按镜像源依次回退。返回 (是否成功, 实际用的源或错误)。"""
    names = [pkgs] if isinstance(pkgs, str) else [p for p in pkgs if p]
    names = [p for p in names if p]
    if not names:
        return False, "未指定包名"
    if not pip_available():
        return False, "当前 Python 环境没有 pip：便携包请确认 runtime\\ 完整，或用本机 Python 跑源码版"
    last = ""
    order = mirror_order(mirror)
    for i, idx in enumerate(order, 1):
        cmd = [sys.executable, "-m", "pip", "install", "-U",
               "--disable-pip-version-check", "--no-input", "--no-warn-script-location",
               *names]
        if idx:
            cmd += ["-i", idx]
        _emit(log, f"pip 更新 {', '.join(names)} …（第 {i}/{len(order)} 个源：{idx or '官方直连'}）")
        try:
            r = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            if r.returncode == 0:
                _emit(log, f"{', '.join(names)} 已更新（源：{idx or '官方直连'}）")
                return True, idx or "official"
            last = (r.stderr or r.stdout or "")[-400:]
        except Exception as e:
            last = str(e)[:400]
        _emit(log, f"该源没成功：{last[-200:]}", "warning")
    return False, f"所有源都失败，最后一次输出：{last}"
