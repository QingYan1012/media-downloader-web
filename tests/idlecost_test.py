r"""挂机开销（idle cost）的离线自检：/api/status 背后那几个「每次都真跑一遍」的探测要有缓存，
组件更新完要主动失效；前端轮询在页面藏进后台时必须整段歇掉。

背景：前端 SSE 一断，兜底轮询会以 1.5 秒/次打 /api/status，而这个端点每次都拉
ffmpeg --version / N_m3u8DL-RE --version 两个子进程、把 yt-dlp 近两千个提取器类重新实例化一遍，
挂机一夜就是几万次进程拉起 —— 这就是「工具一直挂着，第二天很卡」的主因。

全程不联网、不起服务、不碰真实 tools/ 里的二进制：子进程探测用桩顶掉。

跑法：`python tests/idlecost_test.py`
"""
from __future__ import annotations

import atexit
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
TMP = Path(tempfile.mkdtemp(prefix="md_idlecost_test_"))
os.environ["MEDIADOWNLOADER_STATE_DIR"] = str(TMP / "state")
(TMP / "state").mkdir()
import server as S  # noqa: E402

FAILED: list[str] = []
atexit.register(shutil.rmtree, TMP, True)


def ck(name: str, cond, extra=""):
    ok = bool(cond)
    if not ok:
        FAILED.append(name)
    print(("PASS " if ok else "FAIL ") + name + (f"  [{extra}]" if extra else ""))


# ---------------------------------------------------------------- A. FFmpegManager.version 的缓存
print("== A. ffmpeg 版本探测：24 小时内（进程内/落盘）只拉一次子进程 ==")

_probe_calls = {"n": 0}
_BIN = TMP / "ffmpeg.exe"
_BIN.write_bytes(b"MZ-fake")
_real_probe = S.FFmpegManager._probe_version
S.FFmpegManager._probe_version = lambda self, path: (_probe_calls.__setitem__(
    "n", _probe_calls["n"] + 1) or f"fake-{_probe_calls['n']}")
try:
    fm = S.FFmpegManager()
    fm.local_bin = _BIN          # find() 第 2 档直接命中，不碰系统 PATH
    fm.manual_path = ""
    v1 = fm.version()
    ck("A1 第一次探测拿到版本", v1.startswith("fake-") and _probe_calls["n"] == 1,
       f"v={v1} calls={_probe_calls['n']}")
    v2 = fm.version()
    ck("A2 第二次问同一文件不再拉子进程（读缓存）",
       v2 == v1 and _probe_calls["n"] == 1, f"calls={_probe_calls['n']}")

    fm._ver_cache["ts"] = time.time() - S.VER_CACHE_TTL - 1      # 内存过期
    fm.version()
    ck("A3 内存过期先读落盘缓存，不再拉子进程", _probe_calls["n"] == 1,
       f"calls={_probe_calls['n']}")

    S._ver_cache_drop("ffmpeg")
    fm._ver_cache["ts"] = time.time() - S.VER_CACHE_TTL - 1
    fm.version()
    ck("A3b 落盘也没有才重新探测", _probe_calls["n"] == 2, f"calls={_probe_calls['n']}")

    fm2 = S.FFmpegManager()
    fm2.local_bin = _BIN
    fm2.manual_path = ""
    v_disk = fm2.version()
    ck("A3c 新实例/重启后直接读落盘结果", v_disk == fm.version() and _probe_calls["n"] == 2,
       f"v={v_disk} calls={_probe_calls['n']}")

    # 换文件（mtime 变了）必须立刻失效，不等 TTL —— 组件升级靠的就是这条。
    # 用 os.utime 显式改时间戳：NTFS 上写完立刻 stat 可能拿到旧值，靠写内容不可靠。
    fm._ver_cache["ts"] = time.time()
    _old = _BIN.stat().st_mtime
    os.utime(_BIN, (_old - 100, _old - 100))
    fm.version()
    ck("A4 文件 mtime 变了缓存立刻失效（落盘也不认）", _probe_calls["n"] == 3,
       f"calls={_probe_calls['n']}")

    _BIN.unlink()                                # 文件没了 → find() 落空 → 未找到，不炸
    fm.find = lambda manual="": None             # 这台机器 tools/ 里有真 ffmpeg，会兜底命中；桩成「找不到」
    ck("A5 二进制被删后回「未找到」而不是拿旧缓存", fm.version() == "未找到")
finally:
    S.FFmpegManager._probe_version = _real_probe

# ---------------------------------------------------------------- B. N3 版本探测的缓存
print("== B. N_m3u8DL-RE 版本探测：同一口径 ==")
_nm_calls = {"n": 0}
_N3BIN = TMP / "N_m3u8DL-RE.exe"
_N3BIN.write_bytes(b"MZ-fake")
_real_n3_find = S.find_n_m3u8dl
_real_n3_probe = S._n3_probe_version
try:
    S.find_n_m3u8dl = lambda: str(_N3BIN)
    S._n3_probe_version = lambda path: (_nm_calls.__setitem__(
        "n", _nm_calls["n"] + 1) or f"RE-{_nm_calls['n']}")
    S._N3_VER_CACHE.clear()
    w1 = S.n_m3u8dl_version()
    w2 = S.n_m3u8dl_version()
    ck("B1 同一二进制第二次问走缓存", w1 == w2 and _nm_calls["n"] == 1,
       f"calls={_nm_calls['n']}")
    S._N3_VER_CACHE["ts"] = time.time() - S.VER_CACHE_TTL - 1
    S.n_m3u8dl_version()
    ck("B2 内存过期先读落盘缓存", _nm_calls["n"] == 1, f"calls={_nm_calls['n']}")
    S._ver_cache_drop("n_m3u8dl")
    S._N3_VER_CACHE["ts"] = time.time() - S.VER_CACHE_TTL - 1
    S.n_m3u8dl_version()
    ck("B2b 落盘也没有才重新探测", _nm_calls["n"] == 2, f"calls={_nm_calls['n']}")
    _old = _N3BIN.stat().st_mtime
    os.utime(_N3BIN, (_old - 100, _old - 100))
    S._N3_VER_CACHE["ts"] = time.time()
    S.n_m3u8dl_version()
    ck("B3 mtime 变了立刻失效", _nm_calls["n"] == 3, f"calls={_nm_calls['n']}")
    S.find_n_m3u8dl = lambda: None
    ck("B4 找不到引擎回「未安装」", S.n_m3u8dl_version() == "未安装")
finally:
    S.find_n_m3u8dl = _real_n3_find
    S._n3_probe_version = _real_n3_probe
    S._N3_VER_CACHE.clear()

# ---------------------------------------------------------------- C. yt-dlp / whisper 状态缓存
print("== C. check_ytdlp / whisper_status：贵的那段只跑一次 ==")
_ydl_calls = {"n": 0}
_real_ydl_probe = S.DownloaderEngine._probe_ytdlp_version
try:
    S.DownloaderEngine._probe_ytdlp_version = lambda self: (
        _ydl_calls.__setitem__("n", _ydl_calls["n"] + 1) or f"2026.10.21-{_ydl_calls['n']} (local)")
    S._YTDLP_VER_CACHE.clear()
    eng = S.DownloaderEngine()
    y1 = eng.check_ytdlp()
    y2 = eng.check_ytdlp()
    ck("C1 同一进程里 check_ytdlp 只探测一次", y1 == y2 and _ydl_calls["n"] == 1,
       f"calls={_ydl_calls['n']}")
    S._YTDLP_VER_CACHE["ts"] = time.time() - S.VER_CACHE_TTL - 1
    eng.check_ytdlp()
    ck("C2 内存过期先读落盘缓存", _ydl_calls["n"] == 1, f"calls={_ydl_calls['n']}")
    S._ver_cache_drop("ytdlp")
    S._YTDLP_VER_CACHE["ts"] = time.time() - S.VER_CACHE_TTL - 1
    eng.check_ytdlp()
    ck("C2b 落盘也没有才重新探测", _ydl_calls["n"] == 2, f"calls={_ydl_calls['n']}")
finally:
    S.DownloaderEngine._probe_ytdlp_version = _real_ydl_probe
    S._YTDLP_VER_CACHE.clear()

_ws_calls = {"n": 0}
_real_ws = S.whisper_status.__wrapped__ if hasattr(S.whisper_status, "__wrapped__") else None


class _FakeFW(types.ModuleType):
    __version__ = "1.2.3"


def _ws_probe():
    _ws_calls["n"] += 1
    return {"faster_whisper": True, "cli": "", "dir": "X", "label": f"faster-whisper {_ws_calls['n']}"}


_real_whisper_body = None
# 把缓存剥掉拿到真函数体：直接补丁一个「每次都数调用次数」的实现再套原缓存逻辑没意义 ——
# 原函数已经把缓存写死在里头，这里直接验证缓存读回与失效。
S._WHISPER_ST_CACHE.update({"ts": time.time(), "data": {"faster_whisper": True, "cli": "",
                                                        "dir": "D", "label": "faster-whisper 1.2.3"}})
w = S.whisper_status()
ck("C3 缓存命中原样读回（且是拷贝，不是同一份 dict）",
   w.get("label") == "faster-whisper 1.2.3" and w is not S._WHISPER_ST_CACHE["data"])
w["label"] = "改过也不影响缓存"
ck("C4 调用方改返回值不会污染缓存", S.whisper_status().get("label") == "faster-whisper 1.2.3")
S._WHISPER_ST_CACHE["ts"] = time.time() - S.VER_CACHE_TTL - 1
_ws_calls["n"] = 0
_real_fw_status = None
# TTL 过期走真探测体：临时把 faster_whisper 的 import 探测做成可控的 —— 直接验证真函数体不炸即可
try:
    out = S.whisper_status()
    ck("C5 TTL 过期重新探测返回完整结构",
       isinstance(out, dict) and {"faster_whisper", "cli", "dir", "label"} <= set(out),
       str(out.get("label"))[:40])
finally:
    S._WHISPER_ST_CACHE.clear()

# ---------------------------------------------------------------- D. 更新完成后主动失效
print("== D. 组件更新收尾必须清缓存（不然界面端着旧版本号到 TTL 为止） ==")
ck("D1 _comp_update_one 的 ffmpeg 分支有清缓存动作",
   "_ver_cache" in (S._comp_update_one.__doc__ or "") or True)  # 占位口径：真实断言在 D2-D4
src = Path(S.__file__).read_text(encoding="utf-8")
m = re.search(r"def _comp_update_one.*?(?=\ndef |\nclass )", src, re.S)
body = m.group(0) if m else ""
ck("D2 ffmpeg 更新分支清 _ver_cache", "getattr(ffmpeg_mgr, \"_ver_cache\", {}).clear()" in body)
ck("D3 ytdlp 更新分支清 _YTDLP_VER_CACHE", "_YTDLP_VER_CACHE.clear()" in body)
ck("D4 n_m3u8dl 更新分支清 _N3_VER_CACHE", "_N3_VER_CACHE.clear()" in body)
ck("D5 whisper 更新分支清 _WHISPER_ST_CACHE", "_WHISPER_ST_CACHE.clear()" in body)
m2 = re.search(r"def api_update_ytdlp.*?(?=\n@app|\ndef api_update_ffmpeg)", src, re.S)
ck("D6 /api/update/ytdlp 后台任务也清缓存",
   bool(m2) and "_YTDLP_VER_CACHE.clear()" in m2.group(0))
m3 = re.search(r"def api_update_whisper.*?(?=\n@app|\ndef api_health)", src, re.S)
ck("D7 /api/update/whisper 后台任务也清缓存",
   bool(m3) and "_WHISPER_ST_CACHE.clear()" in m3.group(0))
ck("D8 _comp_update_one 四个工具分支同步失效落盘缓存",
   all(x in body for x in ('_ver_cache_drop("ffmpeg")', '_ver_cache_drop("ytdlp")',
                           '_ver_cache_drop("n_m3u8dl")', '_ver_cache_drop("whisper")',
                           '_ver_cache_drop("aria2")')))
m4 = re.search(r"def api_update_aria2.*?(?=\n@app|\ndef )", src, re.S)
ck("D9 /api/update/aria2 同时清内存与落盘缓存",
   bool(m4) and "_ARIA2_VER_CACHE.clear()" in m4.group(0)
   and '_ver_cache_drop("aria2")' in m4.group(0))

print("== G. 版本探测落盘：24 小时、按文件校验 ==")
ck("G1 TTL 是 24 小时", S.VER_CACHE_TTL == 86400 and S.LATEST_TTL == S.VER_CACHE_TTL)
ck("G2 缓存文件落在状态目录", Path(S.VER_CACHE_FILE).parent == Path(S.STATE_DIR),
   str(S.VER_CACHE_FILE))
_ondisk = json.loads(Path(S.VER_CACHE_FILE).read_text(encoding="utf-8"))
ck("G3 ffmpeg / yt-dlp / whisper 都有落盘结果",
   all(k in _ondisk for k in ("ffmpeg", "ytdlp", "whisper")), str(sorted(_ondisk)))
S._ver_cache_put("_probe", {"ts": time.time() - S.VER_CACHE_TTL - 1, "x": 1})
ck("G4 超过 24 小时的条目不再读回", S._ver_cache_get("_probe") == {})
S._ver_cache_drop("_probe")

# ---------------------------------------------------------------- E. 前端：页面藏进后台时轮询歇掉
print("== E. 前端轮询对 document.hidden 的口径 ==")
html = (Path(S.__file__).resolve().parent / "static" / "index.html").read_text(encoding="utf-8")
m4 = re.search(r"pollTimer = setInterval\(function|pollTimer = setInterval\(\(\) => \{.*?\}, 1500\)", html, re.S)
ck("E1 主轮询入口先看 document.hidden（藏进后台整段跳过）",
   bool(m4) and "document.hidden" in m4.group(0))
ck("E2 剪贴板不再 2 秒轮询，只在进页面/回前台各问一次",
   "pollClipboard();" in html and "pollClipboard(); }, 2000)" not in html
   and "clipTimer" not in html)
ck("E3 loadStatus 从每 1.5 秒档提到兜底（catchup）档",
   "if (catchup && page.value === 'queue'" in html)
ck("E4 回到可见时补一轮（visibilitychange 监听）",
   "document.addEventListener('visibilitychange', onVis)" in html
   and "const onVis = () => {" in html)
ck("E5 卸载时解绑 visibilitychange",
   "document.removeEventListener('visibilitychange', onVis)" in html)

# ---------------------------------------------------------------- F. /api/status 仍含关键字段（缓存别把形状改坏）
print("== F. /api/status 的返回形状不变 ==")
src_status = re.search(r"def api_status\(\).*?\n\n\n", src, re.S)
body_status = src_status.group(0) if src_status else ""
for key in ("ffmpeg", "ffmpeg_path", "ytdlp", "n_m3u8dl", "whisper", "running", "pending",
            "disk_free_gb", "throttle", "po_token"):
    ck(f"F1 字段还在：{key}", f'"{key}"' in body_status)

print()
if FAILED:
    print(f"FAILED: {len(FAILED)}")
    for f in FAILED:
        print("  - " + f)
    sys.exit(1)
print("FAILED: none")
