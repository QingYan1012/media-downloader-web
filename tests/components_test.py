r"""组件页三版本 + 入队前 preflight + 上游版本自动检测的离线自检。

全程不联网、不起服务、不碰 config.json：随包清单指向 Temp 文件，依赖状态与 pip 查询都用假对象顶掉。
反向验证同样做了 —— 依赖齐全时必须一条错都不报，否则「检查通过」只是空跑。

跑法：`python tests/components_test.py`
"""
from __future__ import annotations

import atexit
import importlib.util
import json
import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pkg_update as P  # noqa: E402
import server as S  # noqa: E402

FAILED: list[str] = []
TMP = Path(tempfile.mkdtemp(prefix="md_components_test_"))
atexit.register(shutil.rmtree, TMP, True)   # 自检只在 Temp 里造东西，退出就带走


def ck(name: str, cond, extra=""):
    ok = bool(cond)
    if not ok:
        FAILED.append(name)
    print(("PASS " if ok else "FAIL ") + name + (f"  [{extra}]" if extra else ""))


# ---------------------------------------------------------------- 1. 上游最新版解析
print("== A. 从 pip 输出里认最新版 ==")
ck("A1 LATEST 行优先",
   P._parse_index_latest("musicdl (2.14.0)\nAvailable versions: ...\n  LATEST:    2.14.0\n") == "2.14.0")
ck("A2 没有 LATEST 行时读首行的括号",
   P._parse_index_latest("mutagen (1.48.1)\nAvailable versions: 1.48.1, 1.47.0\n") == "1.48.1")
ck("A3 报错输出不炸、也不硬给版本",
   P._parse_index_latest("ERROR: No matching distribution found for foo") == "")
ck("A4 空输出给空串", P._parse_index_latest("") == "")

_calls: list[str] = []


def fake_latest(pkg: str, mirror: str = "", timeout: int = 20):
    _calls.append(pkg)
    return ("9.9.9", "official") if pkg != "bad" else ("", "没查到（网络不通）")


_real_latest = P.latest_version
P.latest_version = fake_latest
try:
    r = P.latest_versions(["musicdl", "mutagen", "musicdl", "", "bad"], mirror="")
    ck("A5 批量查询去重后逐个返回结果", r["musicdl"]["version"] == "9.9.9" and _calls.count("musicdl") == 1,
       f"{_calls}")
    ck("A6 空包名不参与查询", "" not in _calls)
    ck("A7 单个查不到只影响它自己，且把原因带着",
       r["bad"]["version"] == "" and "网络不通" in r["bad"]["error"] and r["mutagen"]["version"] == "9.9.9")
finally:
    P.latest_version = _real_latest

# ---------------------------------------------------------------- 2. 随包清单读取
print("== B. components_bundled.json 的读取与失效 ==")
man = TMP / "components_bundled.json"
man.write_text(json.dumps({"app": "1.2.7", "built": "2026-09-20 10:00",
                           "pip": {"musicdl": "2.13.11", "yt-dlp": "2026.8.19", "fpcalc-none": ""},
                           "tools": {"ffmpeg.exe": "7.1", "yt-dlp.exe": "2026.8.19"}},
                          ensure_ascii=False), encoding="utf8")
_real_manifest_file = S.BUNDLED_FILE
S.BUNDLED_FILE = man
S._bundled_cache.update(mtime=None, data={})
try:
    ck("B1 读到包内清单", S.bundled_manifest().get("app") == "1.2.7")
    ck("B2 tools 优先于 pip（yt-dlp 行认的是包内 exe）",
       S._bundled_version(S.bundled_manifest(), {"tool": "yt-dlp.exe", "pkg": "yt-dlp"}) == "2026.8.19")
    ck("B3 没有 tools 项才回落 pip",
       S._bundled_version(S.bundled_manifest(), {"tool": "", "pkg": "musicdl"}) == "2.13.11")
    ck("B4 清单里没这一项就是空串（界面据此不显示「随包」）",
       S._bundled_version(S.bundled_manifest(), {"tool": "nope.exe", "pkg": "nope"}) == "")
    ck("B5 清单值为空的项不算版本",
       S._bundled_version(S.bundled_manifest(), {"tool": "", "pkg": "fpcalc-none"}) == "")
    man.write_text(json.dumps({"app": "1.3.0", "pip": {}, "tools": {}}), encoding="utf8")
    S._bundled_cache["mtime"] = None      # 换文件靠 mtime 失效，这里只验缓存会重读
    ck("B6 清单换版后重读，不端着旧的", S.bundled_manifest().get("app") == "1.3.0")
    S.BUNDLED_FILE = TMP / "does-not-exist.json"
    ck("B7 源码运行没有清单 → 空 dict（界面上不出现「随包」）", S.bundled_manifest() == {})
    S.BUNDLED_FILE = TMP
    ck("B8 清单路径是目录也不会炸", S.bundled_manifest() == {})
finally:
    S.BUNDLED_FILE = _real_manifest_file
    S._bundled_cache.update(mtime=None, data={})

# ---------------------------------------------------------------- 3. /api/components 的返回形状
print("== C. 组件接口给出的三个版本字段 ==")


class FakeFFmpeg:
    manual_path = ""

    def __init__(self, found=True):
        self._found = found

    def find(self, manual=""):
        return str(TMP) if self._found else None

    def version(self):
        return "7.1" if self._found else "未找到"


class FakeEngine:
    def check_ytdlp(self):
        return "2026.8.19 (local)"


class FakeCfg:
    def __init__(self, data):
        self.data = data

    def get(self, k, default=None):
        return self.data.get(k, default)


class FakeQueue:
    called = False

    def add_urls(self, urls, opts):
        FakeQueue.called = True
        return [f"t{i}" for i in range(len(urls))]


_real = (S.ffmpeg_mgr, S.engine, S.whisper_status, S.find_n_m3u8dl, S.cfg, S.pkg_update, S.log_mgr)
_real_latest_cache = dict(S._latest_cache)
man.write_text(json.dumps({"app": "1.2.7", "built": "2026-09-20 10:00",
                           "pip": {"musicdl": "2.13.11", "yt-dlp": "2026.8.19"},
                           "tools": {"ffmpeg.exe": "7.1", "yt-dlp.exe": "2026.8.19"}},
                          ensure_ascii=False), encoding="utf8")
S.ffmpeg_mgr = FakeFFmpeg()
S.engine = FakeEngine()
S.whisper_status = lambda: {"faster_whisper": False, "cli": "", "label": "未安装"}
S.find_n_m3u8dl = lambda: ""
S.cfg = FakeCfg({"pip_mirror": "", "github_mirror": "", "download_dir": str(TMP), "write_sub_files": False})
S.log_mgr = type("L", (), {"log": staticmethod(lambda *a, **k: None)})()
S.BUNDLED_FILE = man
S._bundled_cache.update(mtime=None, data={})
S._latest_cache.update(ts=0.0, mirror=None, data={})
S.pkg_update = type("PU", (), {
    "PIP_PACKAGES": [{"name": "musicdl", "label": "musicdl（音乐搜索 / 歌词 / 封面）"}],
    "PIP_MIRRORS": P.PIP_MIRRORS,
    "installed_version": staticmethod(lambda n: "2.13.11"),
    "pip_available": staticmethod(lambda: True),
    "pip_version": staticmethod(lambda: "24.0"),
    "latest_versions": staticmethod(lambda names, mirror="": {n: {"version": "9.9.9", "source": "official",
                                                                  "error": ""} for n in names}),
})()
try:
    d = S.api_components()
    bykey = {i["key"]: i for i in d["items"]}
    ck("C1 每行都给 active / bundled / latest，且不再有含糊的 version 字段",
       all({"active", "bundled", "latest"} <= set(i) and "version" not in i for i in d["items"]),
       str(sorted(bykey["ffmpeg"])))
    ck("C2 默认不查上游（点按钮才查）", all(i["latest"] == "" for i in d["items"]) and not d["latest_checked"])
    ck("C3 随包版本按行对上：ffmpeg 取 tools、musicdl 取 pip",
       bykey["ffmpeg"]["bundled"] == "7.1" and bykey["musicdl"]["bundled"] == "2.13.11")
    ck("C4 反向验证：清单里没有的项 bundled 为空（N_m3u8DL-RE 这行不会凭空冒出随包版本）",
       bykey["n_m3u8dl"]["bundled"] == "")
    ck("C5 FFmpeg 找到时绿点，active 就是它自报的版本号",
       bykey["ffmpeg"]["ok"] is True and bykey["ffmpeg"]["active"] == "7.1")
    S.ffmpeg_mgr = FakeFFmpeg(found=False)
    d2 = S.api_components()
    ck("C6 缺 FFmpeg 时 ok=False、active 写「未找到」",
       [i for i in d2["items"] if i["key"] == "ffmpeg"][0]["ok"] is False
       and [i for i in d2["items"] if i["key"] == "ffmpeg"][0]["active"] == "未找到")
    d3 = S.api_components(latest="1")
    ck("C7 点「查询最新版本」后每行带上 latest，并标明本次查过",
       {i["key"]: i["latest"] for i in d3["items"]}.get("musicdl") == "9.9.9" and d3["latest_checked"],
       str(d3["items"][4] if len(d3["items"]) > 4 else d3["items"]))
    ck("C8 不在 PyPI 的工具行没有 latest，也不报错",
       [i for i in d3["items"] if i["key"] == "ffmpeg"][0]["latest"] == "")
    S.pkg_update = type("PU", (), {
        "PIP_PACKAGES": [{"name": "musicdl", "label": "musicdl"}],
        "PIP_MIRRORS": P.PIP_MIRRORS,
        "installed_version": staticmethod(lambda n: "2.13.11"),
        "pip_available": staticmethod(lambda: True),
        "pip_version": staticmethod(lambda: "24.0"),
        "latest_versions": staticmethod(lambda names, mirror="": {
            n: {"version": "", "source": "", "error": "没查到（所有候选源都失败）：Timeout"} for n in names}),
    })()
    S._latest_cache.update(ts=0.0, mirror=None, data={})
    d4 = S.api_components(latest="1")
    row = [i for i in d4["items"] if i["key"] == "musicdl"][0]
    ck("C9 查不到最新版时把原因交给界面，而不是留一行空白",
       row["latest"] == "" and "Timeout" in row["latest_note"], row["latest_note"])
    ck("C10 包信息随清单一起报出来", d["bundled"]["app"] == "1.2.7" and d["bundled"]["built"] == "2026-09-20 10:00",
       str(d["bundled"]))

    # 缓存：第二次点按钮不该再问一遍 pip
    hits: list[int] = []
    S.pkg_update = type("PU", (), {
        "PIP_PACKAGES": [{"name": "musicdl", "label": "musicdl"}],
        "PIP_MIRRORS": P.PIP_MIRRORS,
        "installed_version": staticmethod(lambda n: "2.13.11"),
        "pip_available": staticmethod(lambda: True),
        "pip_version": staticmethod(lambda: "24.0"),
        "latest_versions": staticmethod(lambda names, mirror="": (hits.append(1), {
            n: {"version": "9.9.9", "source": "official", "error": ""} for n in names})[1]),
    })()
    S._latest_cache.update(ts=0.0, mirror=None, data={})
    S.api_components(latest="1")
    S.api_components(latest="1")
    ck("C11 上游版本查询 10 分钟内只跑一次（页面重复点不该反复问 pip）", len(hits) == 1, str(hits))
finally:
    S.ffmpeg_mgr, S.engine, S.whisper_status, S.find_n_m3u8dl, S.cfg, S.pkg_update, S.log_mgr = _real
    S._latest_cache.update(_real_latest_cache)
    S.BUNDLED_FILE = _real_manifest_file
    S._bundled_cache.update(mtime=None, data={})

# ---------------------------------------------------------------- 4. 入队前 preflight
print("== D. 入队前的依赖/目录检查 ==")
YTDLP_OK = "2026.8.19 (local)"
YTDLP_NO = "not found"
N_M3U8 = "H:\\x\\N_m3u8DL-RE.exe"
TELETHON = importlib.util.find_spec("telethon") is not None
YOUTUBE = ["https://www.youtube.com/watch?v=aaaaaaaaaaa"]
OPTS_FULL = {"embed_sub": True, "write_sub_files": False, "embed_thumb": True, "embed_meta": True,
             "embed_chapters": True, "sponsorblock": "off", "format": "mkv", "download_section": "",
             "local_ai_transcribe": False, "use_hls_engine": False, "download_dir": str(TMP)}
OPTS_BARE = dict(OPTS_FULL, embed_sub=False, embed_thumb=False, embed_meta=False, embed_chapters=False,
                 format="mp4")
LOGS: list[tuple] = []


class FakeLogMgr:
    def log(self, msg, level="info", k="", kv=None):   # k/kv 是 #55 后端运行日志的键，桩不收
        LOGS.append((level, msg))


def preflight(urls, opts, ff=True, ytdlp=YTDLP_OK, whisper=None, nm=N_M3U8, cfgd=None):
    keep = (S.ffmpeg_mgr, S.engine, S.whisper_status, S.find_n_m3u8dl, S.cfg, S.log_mgr)
    S.ffmpeg_mgr = FakeFFmpeg(found=ff)
    S.engine = type("E", (), {"check_ytdlp": lambda self: ytdlp})()
    S.whisper_status = lambda: whisper or {"faster_whisper": True, "cli": ""}
    S.find_n_m3u8dl = lambda: nm
    S.cfg = FakeCfg(cfgd or {"download_dir": str(TMP), "write_sub_files": False})
    S.log_mgr = FakeLogMgr()
    try:
        return S.download_preflight(urls, opts)
    finally:
        S.ffmpeg_mgr, S.engine, S.whisper_status, S.find_n_m3u8dl, S.cfg, S.log_mgr = keep


errs, warns = preflight(YOUTUBE, OPTS_FULL)
ck("D1 反向验证：依赖齐全、目录可写 → 一条错都不报（否则 preflight 只是空跑）", errs == [] and warns == [], str(errs))

errs, warns = preflight(YOUTUBE, OPTS_FULL, ytdlp=YTDLP_NO)
ck("D2 没有 yt-dlp 时当场回错并指名安装入口", any("yt-dlp" in e and "组件与依赖" in e for e in errs), str(errs))

errs, warns = preflight(["tgmt://abc"], dict(OPTS_FULL))
ck("D3 tgmt:// 不该被 yt-dlp 检查拦住（它走 Telegram 会话）",
   not any("yt-dlp" in e for e in errs), str(errs))
ck("D4 telethon 的判定跟着真实环境走：装了不报错、没装就指名安装",
   any("telethon" in e for e in errs) is (not TELETHON), str(errs))

errs, warns = preflight(YOUTUBE, OPTS_FULL, ff=False)
ck("D5 缺 FFmpeg + 这单要嵌字幕/嵌封面/mkv 封装 → 拦住并列出具体哪几件事",
   any("FFmpeg" in e and "嵌入字幕" in e and "嵌入封面" in e for e in errs), str(errs))

errs, warns = preflight(YOUTUBE, OPTS_BARE, ff=False)
ck("D6 只是会降质的不拦：不嵌字幕、mp4 直下 → 只出一条警告日志",
   errs == [] and len(warns) == 1 and "FFmpeg" in warns[0], f"{errs} / {warns}")

errs, warns = preflight(YOUTUBE, dict(OPTS_FULL, local_ai_transcribe=True), whisper={"faster_whisper": False, "cli": ""})
ck("D7 勾了本地转写却没装 faster-whisper → 拦，且说清体积代价在安装入口里",
   any("faster-whisper" in e and "转写" in e for e in errs), str(errs))

errs, warns = preflight(YOUTUBE, dict(OPTS_FULL, use_hls_engine=True), nm="")
ck("D8 指定 HLS 专用引擎却找不到 N_m3u8DL-RE → 拦", any("N_m3u8DL-RE" in e for e in errs), str(errs))

errs, warns = preflight(YOUTUBE, dict(OPTS_FULL, download_dir=str(TMP / "sub" / "deep")))
ck("D9 下载目录不存在会自动建出来（不当错报）", errs == [], str(errs))
ck("D10 建目录用的是入队时指定的目录", (TMP / "sub" / "deep").is_dir())

bad_dir = TMP / "afile"
bad_dir.write_text("x", encoding="utf8")
errs, warns = preflight(YOUTUBE, dict(OPTS_FULL, download_dir=str(bad_dir / "sub")))
ck("D11 目录写不进去（磁盘没了/路径指向文件）当场回错，带着原始异常",
   any("写不进去" in e and "sub" in e for e in errs), str(errs))

probe_left = list(TMP.rglob(".md_write_probe"))
ck("D12 写入探测文件用完就删，不留半路产物", probe_left == [], str(probe_left))

# api_download 只在检查通过时才建任务
print("== E. 检查没过就不会有任务 ==")
_real_cfg, _real_queue = S.cfg, S.queue
S.cfg = FakeCfg({"download_dir": str(TMP), "write_sub_files": False})
S.queue = FakeQueue()
body = S.AddUrlsBody(urls=YOUTUBE, **{k: v for k, v in OPTS_FULL.items() if k in S.AddUrlsBody.model_fields})
keep = (S.ffmpeg_mgr, S.engine, S.whisper_status, S.find_n_m3u8dl, S.log_mgr)
S.ffmpeg_mgr = FakeFFmpeg(found=False)
S.engine = type("E", (), {"check_ytdlp": lambda self: YTDLP_OK})()
S.whisper_status = lambda: {"faster_whisper": True, "cli": ""}
S.find_n_m3u8dl = lambda: N_M3U8
S.log_mgr = FakeLogMgr()
try:
    try:
        S.api_download(body)
        raised = None
    except Exception as e:                      # HTTPException
        raised = e
    ck("E1 缺 FFmpeg 时接口回 400 并带着那句人话", getattr(raised, "status_code", None) == 400
       and "FFmpeg" in str(getattr(raised, "detail", "")), str(raised))
    ck("E2 任务压根没创建", FakeQueue.called is False)
    ck("E3 这次拒绝写进运行日志（不是只有弹窗）",
       any(lvl == "error" and "入队前检查未通过" in m for lvl, m in LOGS), str(LOGS[-2:]))
    S.ffmpeg_mgr = FakeFFmpeg(found=True)
    r = S.api_download(body)
    ck("E4 依赖补齐后同一批链接照常入队", r["ok"] is True and r["added"] == 1 and FakeQueue.called is True, str(r))
finally:
    S.ffmpeg_mgr, S.engine, S.whisper_status, S.find_n_m3u8dl, S.log_mgr = keep
    S.cfg, S.queue = _real_cfg, _real_queue

# ---------------------------------------------------------------- 5. 一键更新
print("== F. 一键更新：分发口径、串行、进度收尾 ==")
BUSY_LOG: list[tuple] = []


class BusyLog:
    def log(self, msg, level="info", k="", kv=None):
        # 签名跟着 LogManager.log 走（#55 加了可选的 k/kv），收下来不动断言
        BUSY_LOG.append((level, msg))


class StubFFmpegUpdate:
    manual_path = ""

    def __init__(self, ret=True):
        self.ret = ret
        self.calls = 0

    def find(self, manual=""):
        return str(TMP)

    def version(self):
        self.calls += 1
        return "7.1"

    def update(self):
        return self.ret


def stub_pkg_update(install=None):
    return type("PU", (), {
        "PIP_PACKAGES": [{"name": "musicdl", "label": "musicdl（音乐搜索 / 歌词 / 封面）"},
                         {"name": "mutagen", "label": "mutagen"}],
        "PIP_MIRRORS": P.PIP_MIRRORS,
        "installed_version": staticmethod(lambda n: "2.13.11"),
        "pip_available": staticmethod(lambda: True),
        "pip_version": staticmethod(lambda: "24.0"),
        "pip_install": staticmethod(install or (lambda pkgs, log=print, mirror="", timeout=600: (True, "official"))),
    })()


def with_stubs(ff_ret=True, ytdlp_ret="updated", nm_ret="成功 2.6.0", wsp_ret="已安装 base", pip_ret=(True, "official")):
    """把五个真安装动作全部换成桩，只留下「按 key 分发 + 各自的成功口径」这条链。"""
    called: list[str] = []
    keep = (S.ffmpeg_mgr, S.engine, S.update_n_m3u8dl, S.update_whisper, S.pkg_update, S.log_mgr)

    def _setup():
        S.ffmpeg_mgr = StubFFmpegUpdate(ff_ret)
        S.engine = type("E", (), {"check_ytdlp": lambda self: "2026.8.19 (local)",
                                  "update_ytdlp": lambda self: (called.append("ytdlp"), ytdlp_ret)[1]})()
        S.update_n_m3u8dl = lambda log=print: (called.append("n_m3u8dl"), nm_ret)[1]
        S.update_whisper = lambda log=print, model="base": (called.append("whisper"), wsp_ret)[1]
        S.pkg_update = stub_pkg_update(lambda pkgs, log=print, mirror="", timeout=600:
                                       (called.append("pip:" + ",".join(pkgs)), pip_ret)[1])
        S.log_mgr = BusyLog()
    _setup()
    return called, keep


def ck_one(tag, key, want_ok, want_called, stub, want_msg=""):
    called, keep = stub
    try:
        ok, msg = S._comp_update_one(key, "", lambda m, level="info": None)
        ck(tag, ok is want_ok and called == want_called and (want_msg in str(msg)),
           f"{ok} / {called} / {str(msg)[:60]}")
    finally:
        S.ffmpeg_mgr, S.engine, S.update_n_m3u8dl, S.update_whisper, S.pkg_update, S.log_mgr = keep


_real_comp_all = dict(S._COMP_ALL)
S._COMP_ALL.update({"results": []})
try:
    ck_one("F1 FFmpeg：认 update() 的布尔，说明里带回当前版本", "ffmpeg", True, [],
           with_stubs(ff_ret=True), "当前 7.1")
    ck_one("F2 FFmpeg：update() 回 False 就是失败（不靠文案猜）", "ffmpeg", False, [],
           with_stubs(ff_ret=False))
    ck_one("F3 yt-dlp：updated 与 updated (pip) 都算成功，并带回当前版本", "ytdlp", True, ["ytdlp"],
           with_stubs(ytdlp_ret="updated (pip)"), "2026.8.19")
    ck_one("F4 yt-dlp：反向验证——回的是报错原文就不算成功", "ytdlp", False, ["ytdlp"],
           with_stubs(ytdlp_ret="下载失败：连接被重置"), "连接被重置")
    ck_one("F5 N_m3u8DL-RE：只认它自己那句「成功」开头，原话透传", "n_m3u8dl", True, ["n_m3u8dl"],
           with_stubs(nm_ret="成功 2.6.0 -> N_m3u8DL-RE.exe"), "N_m3u8DL-RE.exe")
    ck_one("F6 faster-whisper：failed 前缀算失败", "faster-whisper", False, ["whisper"],
           with_stubs(wsp_ret="failed: pip 安装超时"), "pip 安装超时")
    ck_one("F7 faster-whisper：不带 failed 前缀的返回（含模型标签）算成功", "faster-whisper", True, ["whisper"],
           with_stubs(wsp_ret="已安装 base"), "已安装 base")
    ck_one("F8 Python 依赖：走 pip_install 并带回它的源", "musicdl", True, ["pip:musicdl"],
           with_stubs(pip_ret=(True, "https://mirrors...")), "https://mirrors")
    ck_one("F9 Python 依赖：pip 回 False 时不谎报成功", "mutagen", False, ["pip:mutagen"],
           with_stubs(pip_ret=(False, "没查到（所有候选源都失败）")), "候选源")

    # 串行：任一时刻只有一项在跑
    print("== F10 串行与进度 ==")
    live = {"now": 0, "max": 0}
    seq: list[str] = []

    def serial_one(key, mirror, log):
        live["now"] += 1
        live["max"] = max(live["max"], live["now"])
        seq.append(key)
        time.sleep(0.02)
        live["now"] -= 1
        return True, "桩"

    keep_one = S._comp_update_one
    keep_log = S.log_mgr
    S._comp_update_one = serial_one
    S.log_mgr = BusyLog()
    BUSY_LOG.clear()
    try:
        S._COMP_ALL.update({"running": True, "total": 3, "done": 0, "current": "", "results": []})
        S._comp_update_all(["ytdlp", "ffmpeg", "musicdl"], "")
        st = dict(S._COMP_ALL)
        ck("F10 一项一项跑：同一时刻在跑的项数恒为 1", st["running"] is False and live["max"] == 1, str(live))
        ck("F11 跑的顺序就是界面挑出来的顺序", seq == ["ytdlp", "ffmpeg", "musicdl"], str(seq))
        ck("F12 收尾把 running 清掉（否则界面永远发不起下一批）",
           st["running"] is False and st["current"] == "" and st["done"] == 3, str(st))
        ck("F13 每项都留了一行结果，界面能报「成功几项」",
           [r["key"] for r in st["results"]] == seq and all(r["ok"] for r in st["results"]), str(st["results"]))
        ck("F14 结束行写清完成数", any("一键更新结束：完成 3/3 项" in m for _, m in BUSY_LOG), str(BUSY_LOG[-1]))

        seq.clear()

        def half_bad(key, mirror, log):
            if key == "ffmpeg":
                raise RuntimeError("磁盘满了")
            return key != "musicdl", f"{key} 自己说的原因"

        S._comp_update_one = half_bad
        BUSY_LOG.clear()
        S._COMP_ALL.update({"running": True, "total": 3, "done": 0, "current": "", "results": []})
        S._comp_update_all(["ytdlp", "ffmpeg", "musicdl"], "")
        st = dict(S._COMP_ALL)
        ck("F15 中途一项抛异常，后面那项照常跑（不是一坏全停）",
           st["done"] == 3 and [r["key"] for r in st["results"]] == ["ytdlp", "ffmpeg", "musicdl"], str(st))
        frow = [r for r in st["results"] if r["key"] == "ffmpeg"][0]
        ck("F16 抛异常的那项按失败记账，并带着异常类型",
           frow["ok"] is False and "RuntimeError" in frow["msg"], str(frow))
        ck("F17 失败原因原样上屏（界面摘要用的就是这一句）",
           [r for r in st["results"] if r["key"] == "musicdl"][0]["msg"] == "musicdl 自己说的原因")
        ck("F18 结束行点名几项失败，不写「全部成功」",
           any("完成 3/3 项" in m and "失败 2 项" in m for _, m in BUSY_LOG), str(BUSY_LOG[-1]))

        # 外层自己坏了（日志都写不进）也要清 running
        class BoomLog:
            def log(self, msg, level="info", k="", kv=None):
                if "开始 FFmpeg" in msg:
                    raise OSError("日志写不下去了")

        S._comp_update_one = serial_one
        S.log_mgr = BoomLog()
        seq.clear()
        S._COMP_ALL.update({"running": True, "total": 2, "done": 0, "current": "", "results": []})
        S._comp_update_all(["ytdlp", "ffmpeg"], "")
        ck("F19 反向验证：这一轮自己被异常打断时，running 仍然被清掉",
           S._COMP_ALL["running"] is False and seq == ["ytdlp"], str(S._COMP_ALL))
        # 并发数计数本身可信（否则 F10 是空跑）
        live["now"] = live["max"] = 0

        def par(key, mirror, log):
            return serial_one(key, mirror, log)

        ths = [threading.Thread(target=par, args=(k, "", None)) for k in ["a", "b", "c"]]
        [t.start() for t in ths]
        [t.join() for t in ths]
        ck("F20 反向验证：同一时刻真有两项在跑时，上面那个计数会报 >1（证明 F10 测的是串行本身）",
           live["max"] > 1, str(live))
    finally:
        S._comp_update_one = keep_one
        S.log_mgr = keep_log

    # ---- 接口层：校验、挡驾、随 /api/components 带出进度
    print("== F21 接口 ==")
    started = threading.Event()
    keep_run = S._comp_update_all
    keep2 = (S.log_mgr, S.pkg_update, S.ffmpeg_mgr, S.engine, S.whisper_status, S.n_m3u8dl_version)
    S._comp_update_all = lambda keys, mirror: started.wait(5)
    S.log_mgr = BusyLog()
    S.pkg_update = stub_pkg_update()
    S.ffmpeg_mgr = StubFFmpegUpdate()
    S.engine = type("E", (), {"check_ytdlp": lambda self: YTDLP_OK})()
    S.whisper_status = lambda: {"faster_whisper": True, "cli": "", "label": "已安装 base"}
    S.n_m3u8dl_version = lambda: "2.6.0"
    try:
        def expect_400(keys, tag):
            try:
                S.api_components_update_all({"keys": keys})
                ck(tag, False, "没抛 HTTPException")
            except Exception as e:
                ck(tag, getattr(e, "status_code", None) == 400, str(e))

        expect_400(["nope-pkg"], "F21 不认识的条目直接 400，并点名是哪几个")
        expect_400(["ytdlp", "nope"], "F22 混着一个不认识的条目也整批拒掉（不偷偷跳过）")
        expect_400([], "F23 空清单 400（不给它一次空跑的机会）")
        expect_400(None, "F24 keys 缺失也不炸")
        S._COMP_ALL.update({"running": False, "total": 0, "done": 0, "current": "", "results": [], "started": ""})
        r = S.api_components_update_all({"keys": ["ytdlp", "musicdl"]})
        ck("F25 正常提交：立刻返回、标记在跑、并把条目数报回去",
           r["ok"] is True and r["update_all"]["running"] is True and r["update_all"]["total"] == 2, str(r))
        r2 = S.api_components_update_all({"keys": ["ytdlp"]})
        ck("F26 已有一批在跑时不再开第二批，且回一句解释（不是 500）",
           r2["ok"] is False and "已经有一批更新在跑" in r2["message"], str(r2))
        d = S.api_components()
        ck("F27 进度随 GET /api/components 一起带出（界面不另开接口）",
           d["update_all"]["running"] is True and d["update_all"]["total"] == 2, str(d["update_all"]))
        d["update_all"]["running"] = False
        ck("F28 带出的是副本：改返回值改不动真状态", S._COMP_ALL["running"] is True)
        started.set()
        time.sleep(0.2)
    finally:
        S._comp_update_all = keep_run
        S.log_mgr, S.pkg_update, S.ffmpeg_mgr, S.engine, S.whisper_status, S.n_m3u8dl_version = keep2
finally:
    S._COMP_ALL.update({"running": False, "total": 0, "done": 0, "current": "", "results": [], "started": ""})
    S._COMP_ALL.update(_real_comp_all)

# ---------------------------------------------------------------- 6. 打开程序时的自动检测
print("== G. 上游版本自动检测：判定口径、后台跑法与接口 ==")

# G0 版本比较器：这套规则必须和界面里的 verCmp 一致（'2026.8.19 (local)'、'未安装' 都要能比）
ck("G0a 上游更高算有新版", S._ver_newer("2026.8.19 (local)", "2026.9.1") is True)
ck("G0b 版本相同不算有新版", S._ver_newer("2.13.11", "2.13.11") is False)
ck("G0c 上游反而更旧（本机已自行升过）不算有新版", S._ver_newer("1.48.1", "1.47.0") is False)
ck("G0d 段数不等时补零比较：1.2 < 1.2.3", S._ver_newer("1.2", "1.2.3") is True)
ck("G0e 反过来 1.2.3 不比 1.2 新", S._ver_newer("1.2.3", "1.2") is False)
ck("G0f 本机没版本号（未安装）时上游版就是新的", S._ver_newer("未安装", "1.2.0") is True)
ck("G0g 上游没版本号一律不给结论（不许拿'未安装'当最新版）", S._ver_newer("1.0", "") is False)
ck("G0h 反向验证：把两串写成同一串时判定为假（证明比的是数字不是字符串真假）",
   S._ver_newer("2026.9.1", "2026.9.1") is False and S._ver_newer("2026.9.10", "2026.9.9") is False)

# 真实 PIP_PACKAGES 里就有 yt-dlp：tools\ 的 exe 与 pip 包是两行、同一个 pkg 名，判定要各算各的
PIP3 = [{"name": "yt-dlp", "label": "yt-dlp Python 包（tools\\ 里没有 exe 时才用它）"},
        {"name": "musicdl", "label": "musicdl（音乐搜索）"},
        {"name": "mutagen", "label": "mutagen"},
        {"name": "nohelib", "label": "nohelib（没装的）"},
        {"name": "nolatest", "label": "nolatest（查不到上游版）"}]
INSTALLED = {"musicdl": "2.13.11", "mutagen": "1.48.1", "nohelib": "", "nolatest": "1.0.0",
             "yt-dlp": ""}
LATEST = {"musicdl": "2.13.11", "mutagen": "1.47.0", "nohelib": "3.0.0",
          "yt-dlp": "2026.9.1", "faster-whisper": "1.2.0"}
GLATEST_CALLS: list[int] = []
GSLOW = [0.0]
GLOGS: list[tuple] = []


def g_stub_pkg(latest_map=None):
    lm = latest_map or LATEST

    def _latest(names, mirror=""):
        GLATEST_CALLS.append(1)
        if GSLOW[0]:
            time.sleep(GSLOW[0])
        return {n: {"version": lm.get(n, ""), "source": "official",
                    "error": "" if lm.get(n) else "没查到"} for n in names}

    return type("PU", (), {
        "PIP_PACKAGES": PIP3,
        "PIP_MIRRORS": P.PIP_MIRRORS,
        "installed_version": staticmethod(lambda n: INSTALLED.get(n, "")),
        "pip_available": staticmethod(lambda: True),
        "pip_version": staticmethod(lambda: "24.0"),
        "latest_versions": staticmethod(_latest),
    })()


def g_env(auto=True, latest_map=None, boom=False):
    """把 G 段用到的真对象全部换成桩，返回 (要还原的原件, 恢复函数)。"""
    keep = (S.ffmpeg_mgr, S.engine, S.whisper_status, S.n_m3u8dl_version, S.cfg, S.pkg_update, S.log_mgr)
    keep_cache = dict(S._latest_cache)
    keep_state = dict(S._COMP_CHECK)

    def _restore():
        S.ffmpeg_mgr, S.engine, S.whisper_status, S.n_m3u8dl_version, S.cfg, S.pkg_update, S.log_mgr = keep
        S._latest_cache.update(keep_cache)
        S._COMP_CHECK.clear()
        S._COMP_CHECK.update(keep_state)
        GSLOW[0] = 0.0

    S.ffmpeg_mgr = FakeFFmpeg()
    S.engine = FakeEngine()
    S.whisper_status = lambda: {"faster_whisper": False, "cli": "", "label": "未安装"}
    S.n_m3u8dl_version = lambda: ""
    S.cfg = FakeCfg({"pip_mirror": "", "github_mirror": "",
                     "components_auto_check": auto, "download_dir": str(TMP)})
    S.pkg_update = g_stub_pkg(latest_map)
    S.log_mgr = FakeLogMgr()
    LOGS.clear()
    S._latest_cache.update(ts=0.0, mirror=None, data={})
    S._COMP_CHECK.update(status="idle", started="", finished="", available=[], error="")
    return _restore


def g_wait(sec=6.0):
    end = time.time() + sec
    while time.time() < end and S._COMP_CHECK["status"] == "running":
        time.sleep(0.05)
    return dict(S._COMP_CHECK)


_restore = g_env()
try:
    d = S.api_components(latest="1")
    avail = S._comp_available_updates(d["items"])
    ck("G1 只有「已装 + 上游确实更高」的进可更新名单",
       [a["key"] for a in avail] == ["ytdlp"], str([a["key"] for a in avail]))
    ck("G2 版本相同 / 上游更旧 / 查不到最新版都不算可更新",
       all(a["key"] not in ("musicdl", "mutagen") for a in avail))
    ck("G3 没装的（nohelib、faster-whisper）不算「有更新」：不然每次开机都催同一件事",
       all(a["key"] not in ("nohelib", "faster-whisper") for a in avail), str(avail))
    ck("G4 不在 PyPI 的 FFmpeg / N_m3u8DL-RE 不参与判定",
       all(a["key"] not in ("ffmpeg", "n_m3u8dl") for a in avail))
    ck("G4b 查不到上游版的已装组件不算可更新（不拿空白当新版）",
       all(a["key"] != "nolatest" for a in avail), str([a["key"] for a in avail]))
    ck("G4c 同一个包的两行各算各的：exe 那行有新版、pip 那行没装 → 只报 exe 那行",
       [a["key"] for a in avail] == ["ytdlp"]
       and {i["key"]: i["ok"] for i in d["items"]}["yt-dlp"] is False
       and {i["key"]: i["active"] for i in d["items"]}["yt-dlp"] == "未安装",
       str([a["key"] for a in avail]))
    ck("G5 可更新条目带着「当前 → 最新」，弹窗直接用",
       avail[0]["current"] == "2026.8.19 (local)" and avail[0]["latest"] == "2026.9.1", str(avail[:1]))
    ck("G6 接口默认不查上游，检测要显式发起",
       all(i["latest"] == "" for i in S.api_components()["items"]) and S._COMP_CHECK["status"] == "idle")

    # 后台检测：发起后立刻返回，结果靠轮
    print("== G7 后台一次检测的完整往返 ==")
    GLATEST_CALLS.clear()
    GSLOW[0] = 0.5          # 让真 worker 在联网那一步停一下，才能确证接口没有等它
    t0 = time.time()
    r = S.api_components_update_check(S.CompCheckBody(force=True))
    spent = time.time() - t0
    GSLOW[0] = 0.0
    ck("G7a 发起后马上返回 running，不把请求卡在联网上",
       r["status"] == "running" and spent < 0.3, f"{spent:.2f}s / {r['status']}")
    st = g_wait()
    ck("G7b 后台跑完落到 done，并记下完成时间与结果",
       st["status"] == "done" and st["finished"] and [a["key"] for a in st["available"]] == ["ytdlp"], str(st))
    ck("G7c 一次检测只问一遍 pip（批量查，不一个包问一次）", len(GLATEST_CALLS) == 1, str(GLATEST_CALLS))
    ck("G7d 日志留了一行可更新数",
       any("检测上游版本：1 个组件有可更新版本" in m for _, m in LOGS), str(LOGS[-1:]))
    g = S.api_components_update_check_get()
    ck("G7e GET 回的是同一份状态，并带着开关",
       g["status"] == "done" and g["auto_check"] is True and len(g["available"]) == 1, str(g)[:120])
    ck("G7f GET /api/components 也顺带把检测结果带出（界面不必多问一次）",
       S.api_components()["update_check"]["status"] == "done"
       and S.api_components()["auto_check"] is True)
    cp = S._comp_check_state()
    cp["available"].clear()
    ck("G7g 反向验证：改返回值改不动真状态（available 是副本，不是引用）",
       len(S._COMP_CHECK["available"]) == 1, str(S._COMP_CHECK["available"]))

    # 正在跑时重复发起不该重复联网
    print("== G8 幂等与收尾 ==")
    _restore()
    _restore = g_env()
    hold = [threading.Event()]
    keep_worker = S._comp_check_worker
    n_run: list[int] = []

    def slow_worker():
        n_run.append(1)
        hold[0].wait(5)
        S._COMP_CHECK.update(status="done", finished="t", available=[], error="")

    S._comp_check_worker = slow_worker
    try:
        S.api_components_update_check(S.CompCheckBody())
        a = S._comp_check_start()
        b = S._comp_check_start()
        ck("G8a 已有一批在跑时不再开第二批（界面轮询不会把同一个查询打很多遍）",
           len(n_run) == 1 and a["status"] == "running" and b["status"] == "running", str(n_run))
        hold[0].set()
        g_wait()
        ck("G8b 跑完后状态确实离开 running（否则界面永远等不到结果）",
           S._COMP_CHECK["status"] == "done" and len(n_run) == 1, str(n_run))
        hold[0] = threading.Event()     # 换一只没置位的闩，第二批才会停在 running 供断言
        c = S._comp_check_start()
        ck("G8c 收尾之后能再起一批（不是一次性的）",
           len(n_run) == 2 and c["status"] == "running", str(n_run))
        hold[0].set()
        g_wait()
    finally:
        S._comp_check_worker = keep_worker

    # ---- 强制刷新是否真的作废了 10 分钟缓存（不让真线程回填，只验「发起」这一侧）
    print("== G8d/G8e 缓存与 force ==")
    keep_w2 = S._comp_check_worker
    S._comp_check_worker = lambda: None
    try:
        S._COMP_CHECK.update(status="idle")
        S._latest_cache.update(ts=time.time(), mirror="", data={"x": 1})
        S._comp_check_start(force=True)
        ck("G8d force 会把 10 分钟缓存作废（「立即检测」必须看到真上游）", S._latest_cache["ts"] == 0.0)
        S._COMP_CHECK.update(status="idle")
        S._latest_cache.update(ts=time.time(), mirror="", data={"x": 1})
        S._comp_check_start()
        ck("G8e 不 force 时保留缓存（自动检测不该反复问 pip）", S._latest_cache["ts"] != 0.0)
    finally:
        S._comp_check_worker = keep_w2
        S._COMP_CHECK.update(status="idle")

    # 全部最新：一条都不报
    print("== G9 全部最新 / 检测失败 ==")
    _restore()
    _restore = g_env(latest_map={"musicdl": "2.13.11", "mutagen": "1.48.1", "yt-dlp": "2026.8.19"})
    S.api_components_update_check(S.CompCheckBody())
    st = g_wait()
    ck("G9a 全是最新时 available 为空，日志说「都是最新」",
       st["status"] == "done" and st["available"] == []
       and any("已在用组件都是最新" in m for _, m in LOGS), str(st))
    _restore()
    _restore = g_env()
    S.pkg_update = type("PU", (), {
        "PIP_PACKAGES": PIP3, "PIP_MIRRORS": P.PIP_MIRRORS,
        "installed_version": staticmethod(lambda n: ""),
        "pip_available": staticmethod(lambda: True), "pip_version": staticmethod(lambda: ""),
        "latest_versions": staticmethod(lambda names, mirror="": (_ for _ in ()).throw(OSError("全部源都超时"))),
    })()
    S.api_components_update_check(S.CompCheckBody())
    st = g_wait()
    ck("G9c 查询抛异常时状态记 error 并带着异常类型（界面要显示原因，不能卡在 running）",
       st["status"] == "error" and "OSError" in st["error"], str(st))
    ck("G9d 失败也写一行 warning 日志",
       any(lvl == "warning" and "检测上游版本失败" in m for lvl, m in LOGS), str(LOGS[-1:]))

    # 开关关掉：检测结果不再自动弹窗
    print("== G10 开关 ==")
    _restore()
    _restore = g_env(auto=False)
    ck("G10a 关掉自动检测后接口把 auto_check 回成 False（界面据此不弹窗，但仍可手动检测）",
       S.api_components_update_check_get()["auto_check"] is False)
    ck("G10b 关掉开关不影响「立即检测」本身", S._comp_check_start()["status"] == "running")
    st = g_wait()
    ck("G10c 手动检测照样出结果", st["status"] == "done" and len(st["available"]) == 1, str(st))
    _restore()
    _restore = g_env()
    ck("G10d 默认配置里这个开关是开的（新装机第一次打开就会查）",
       S.ConfigManager.DEFAULTS["components_auto_check"] is True)
    ck("G10e 开关能存进配置：ConfigBody 收了它（不然是静默丢弃）",
       "components_auto_check" in S.ConfigBody.model_fields)
finally:
    _restore()

print()
print("FAILED:", ", ".join(FAILED) if FAILED else "none")
sys.exit(1 if FAILED else 0)
